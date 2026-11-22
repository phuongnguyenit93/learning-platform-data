# So sánh ghi từng hàng, ghi theo nhóm và SQL nhiều hàng

Khi ứng dụng Spring Data Relational R2DBC phải lưu nhiều bản ghi, cách tổ chức thao tác ghi ảnh hưởng tới throughput, độ trễ, bộ nhớ, transaction và cách xử lý lỗi. Gọi save cho từng entity là cách dễ hiểu và phù hợp với nhiều luồng nghiệp vụ. Tuy nhiên, nếu ghi hàng nghìn hoặc hàng triệu hàng, chi phí tạo statement, bind tham số và trao đổi dữ liệu với database có thể trở thành nút thắt.

Có nhiều chiến lược để ghi dữ liệu:

- **Ghi từng hàng:** mỗi entity được lưu bằng một thao tác insert/update riêng.
- **Ghi theo nhóm ở tầng ứng dụng:** gom một số entity thành chunk rồi xử lý tuần tự hoặc có giới hạn concurrency.
- **Batch statement:** dùng cùng một SQL statement với nhiều bộ bind parameters thông qua API R2DBC như Statement.add(), nếu driver hỗ trợ.
- **SQL nhiều hàng:** một câu INSERT chứa nhiều bộ VALUES.
- **Bulk loading chuyên dụng:** dùng cơ chế nạp dữ liệu hàng loạt riêng của database khi khối lượng đủ lớn và nghiệp vụ phù hợp.

Các cách này không đồng nghĩa với nhau. Đặc biệt, tên phương thức saveAll không bảo đảm Spring Data sẽ tạo một câu INSERT nhiều hàng hoặc một batch ở mức driver. Cần hiểu implementation, driver và database đang dùng trước khi chọn chiến lược.

Bài học này so sánh hiệu năng và semantics của từng cách, minh họa cách tổ chức reactive flow, cách chia chunk, transaction, backpressure, xử lý lỗi, giới hạn bind parameters, generated ID và cách đo hiệu năng trên database thật.

## 1. Những khái niệm cần phân biệt

Trước khi so sánh, cần tách ba khái niệm thường bị gọi chung là “batch”.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Nhóm dữ liệu ở tầng ứng dụng | Gom nhiều entity thành một collection để xử lý cùng lúc. | buffer(500) rồi xử lý mỗi chunk. |
| Batch statement | Gửi một SQL statement cùng nhiều bộ tham số. | R2DBC Statement.bind(...).add()...execute(). |
| SQL nhiều hàng | Một câu INSERT chứa nhiều tuple VALUES. | INSERT INTO t(a,b) VALUES (...), (...). |
| Bulk loading | API nạp dữ liệu tối ưu riêng của database. | COPY trong PostgreSQL hoặc cơ chế bulk load tương ứng. |

Gom entity thành List không tự động tạo batch statement. Gọi repository.saveAll(list) cũng không đảm bảo driver nhận một lệnh bulk. Ngược lại, một câu INSERT nhiều hàng là một statement duy nhất dù ứng dụng tạo nó từ một collection.

### Các tầng trong đường ghi dữ liệu

~~~mermaid
flowchart TD
    A[Publisher of entities] --> B[Application grouping]
    B --> C{Write strategy}
    C --> D[Save each entity]
    C --> E[Repeated statement batch]
    C --> F[Multi-row INSERT]
    C --> G[Database bulk loader]
    D --> H[R2DBC driver]
    E --> H
    F --> H
    G --> I[Database bulk protocol]
    H --> J[(Database)]
    I --> J
~~~

Mỗi chiến lược có điểm mạnh và giới hạn riêng. Không nên chỉ so sánh số dòng code; cần xem số lần thực thi, round trip, transaction scope, kích thước dữ liệu và semantics khi lỗi.

## 2. Ghi từng hàng bằng repository.save

Đây là cách trực tiếp nhất: với mỗi entity, gọi repository.save và nối publisher vào reactive chain.

~~~java
public Flux<Person> saveOneByOne(Flux<Person> people) {
    return people.concatMap(repository::save);
}
~~~

concatMap xử lý mỗi phần tử theo thứ tự: đợi thao tác save của entity hiện tại hoàn tất rồi mới chuyển sang entity tiếp theo. Cách này giúp kiểm soát concurrency và thứ tự dễ hơn.

Nếu dữ liệu đến từ một collection nhỏ:

~~~java
return Flux.fromIterable(people)
    .concatMap(repository::save);
~~~

### Ưu điểm

- Code đơn giản, dễ đọc và dễ debug.
- Mỗi entity được mapping và lưu theo cơ chế repository chuẩn.
- Dễ lấy entity đã lưu, bao gồm generated ID hoặc version được cập nhật.
- Dễ gắn logic riêng cho từng entity.
- Dễ xác định bản ghi nào thất bại khi xử lý tuần tự.
- Dễ áp dụng kiểm tra domain trước hoặc sau mỗi lần ghi.

### Hạn chế

- Thường tạo một thao tác SQL riêng cho mỗi entity.
- Có thể phát sinh nhiều lần execute và nhiều lần trao đổi với database.
- Chi phí network, statement preparation và transaction coordination có thể lớn.
- Throughput có thể thấp khi latency giữa ứng dụng và database cao.

Ghi từng hàng vẫn có thể hiệu quả với số lượng nhỏ, dữ liệu không đều hoặc logic nghiệp vụ phức tạp. Không nên tối ưu batch trước khi đo thấy thao tác ghi là nút thắt.

### Lưu ý về transaction

Nếu không có transaction bao quanh toàn bộ publisher, từng câu lệnh có thể được commit theo chế độ autocommit hoặc transaction riêng do driver/database quản lý. Nếu hàng thứ 50 lỗi, 49 hàng trước có thể đã được ghi.

Nếu toàn bộ publisher được bọc trong một reactive transaction, các lệnh có thể tham gia cùng transaction đó. Khi một lỗi thoát khỏi transaction boundary, transaction có thể rollback toàn bộ. Điều này làm thay đổi semantics và thời gian giữ lock.

## 3. saveAll không đồng nghĩa với một lệnh bulk insert

ReactiveCrudRepository cung cấp saveAll để lưu nhiều entity:

~~~java
Flux<Person> saveAll(Iterable<Person> entities);

Flux<Person> saveAll(Publisher<Person> entities);
~~~

API này mô tả kết quả nghiệp vụ là lưu nhiều entity. Nó không phải cam kết rằng implementation sẽ tạo một SQL INSERT nhiều hàng hoặc dùng R2DBC Statement.add().

Trong nhiều implementation Spring Data R2DBC, saveAll xử lý từng entity bằng cách gọi logic save cho từng phần tử, thường theo thứ tự tuần tự. Chi tiết có thể thay đổi theo phiên bản và implementation repository. Hãy xem source/version cụ thể nếu hiệu năng của đường này quan trọng.

Ví dụ:

~~~java
return repository.saveAll(people);
~~~

Cách gọi ngắn gọn nhưng không cho biết số SQL statement hoặc round trip. Không được kết luận rằng 1.000 entity sẽ trở thành một câu INSERT gồm 1.000 VALUES.

### Khi nào saveAll phù hợp?

- Tập dữ liệu vừa phải.
- Muốn dùng mapping và lifecycle behavior của Spring Data.
- Cần nhận từng entity đã lưu.
- Chưa có bằng chứng về bottleneck ở tầng database round trip.
- Repository implementation hiện tại đáp ứng throughput.

### Khi nào cần cách khác?

- Import hàng chục nghìn hoặc hàng triệu dòng.
- Đã đo thấy thời gian chờ database/network chiếm phần lớn.
- Cần kiểm soát chunk size.
- Cần giảm số lần execute.
- Có thể chấp nhận một SQL cụ thể theo database vendor.
- Cần một quy trình import có checkpoint, retry và idempotency.

Đừng thay saveAll bằng SQL bulk chỉ dựa trên giả định. Hãy đo baseline và xác nhận semantics cần giữ lại như auditing, callbacks, generated ID, optimistic locking và converters.

## 4. Ghi theo nhóm ở tầng ứng dụng

Ghi theo nhóm có nghĩa là gom một luồng dữ liệu thành các chunk có kích thước giới hạn. Chunk có thể được xử lý bằng repository, batch statement hoặc SQL nhiều hàng.

Ví dụ gom 500 entity một lần:

~~~java
public Flux<Person> saveInChunks(Flux<Person> source) {
    return source
        .buffer(500)
        .concatMap(chunk ->
            repository.saveAll(chunk)
        );
}
~~~

Đoạn code trên giới hạn số entity được gom vào một chunk trước khi gọi saveAll. Nó **không tự biến saveAll thành một SQL batch**. Nếu implementation saveAll lưu từng entity, mỗi chunk vẫn gồm nhiều lần lưu riêng.

### Vì sao cần chunk?

- Giới hạn bộ nhớ khi nguồn dữ liệu lớn hoặc không giới hạn.
- Tạo đơn vị công việc có thể theo dõi.
- Có thể commit theo từng chunk.
- Dễ ghi checkpoint sau mỗi chunk.
- Giảm rủi ro giữ transaction quá lâu.
- Tạo điểm retry rõ ràng khi import có idempotency.

### Chọn chunk size

Chunk quá nhỏ làm tăng số lần điều phối và có thể không tận dụng được batch. Chunk quá lớn làm tăng bộ nhớ, kích thước statement, thời gian transaction và lượng dữ liệu phải retry khi lỗi.

Không có chunk size tối ưu chung. Có thể bắt đầu với một vài giá trị như 100, 250, 500 hoặc 1.000 hàng, sau đó benchmark trên workload thực tế.

Các yếu tố cần xét:

- Số cột và kích thước mỗi hàng.
- Giới hạn bind parameters của database/driver.
- Kích thước packet hoặc statement.
- Latency mạng.
- Bộ nhớ heap và backpressure.
- Thời gian xử lý/commit một chunk.
- Mức độ cạnh tranh lock với workload khác.

### Chunk và transaction theo từng nhóm

Nếu mỗi chunk phải nguyên tử riêng, có thể bọc publisher của chunk bằng TransactionalOperator:

~~~java
public Flux<Person> saveChunked(
        Flux<Person> source,
        TransactionalOperator transaction) {

    return source
        .buffer(500)
        .concatMap(chunk ->
            transaction.transactional(
                repository.saveAll(chunk)
            )
        );
}
~~~

Mỗi chunk được xử lý trong một transaction riêng theo transaction manager. Nếu chunk thứ ba lỗi, hai chunk trước có thể đã commit; chunk thứ ba rollback; chunk sau không được xử lý nếu lỗi truyền ra ngoài.

Nếu bọc transaction ở ngoài toàn bộ publisher:

~~~java
return transaction.transactional(
    source.buffer(500)
        .concatMap(repository::saveAll)
);
~~~

thì toàn bộ các chunk nằm trong một transaction lớn. Điều này tăng atomicity toàn bộ nhưng có thể kéo dài transaction, giữ connection và lock lâu hơn. Chọn theo yêu cầu nghiệp vụ, không chỉ theo hiệu năng.

## 5. concatMap, flatMap và concurrency

Reactive operator quyết định số thao tác ghi có thể đang chạy đồng thời.

### concatMap: tuần tự

~~~java
return source.concatMap(repository::save);
~~~

- Mỗi lần chỉ xử lý một save ở downstream.
- Giữ thứ tự phát theo nguồn.
- Dễ dự đoán thứ tự và failure boundary.
- Throughput có thể bị giới hạn bởi latency của từng thao tác.

### flatMap: có concurrency

~~~java
return source.flatMap(repository::save, 8);
~~~

- Có thể có tối đa số publisher con đang hoạt động theo concurrency đã cấu hình.
- Kết quả có thể phát không theo thứ tự nguồn.
- Có thể tăng throughput khi database và pool còn khả năng xử lý.
- Có thể gây tranh chấp connection, lock và tài nguyên.
- Không tạo một batch SQL.

flatMap với concurrency 8 vẫn thường là các thao tác save riêng biệt. Nó tăng số công việc đồng thời, không biến chúng thành một statement nhiều hàng.

### flatMapSequential

~~~java
return source.flatMapSequential(repository::save, 8);
~~~

Có thể chạy các publisher con đồng thời nhưng phát kết quả theo thứ tự nguồn. Việc giữ thứ tự phát kết quả không đồng nghĩa database đã thực thi hoặc commit theo đúng thứ tự đó.

### Chọn concurrency

Bắt đầu với concurrency thấp và tăng dần trong benchmark. Không đặt concurrency rất lớn để “ép” database nhanh hơn. Nếu connection pool có 10 connection mà ứng dụng phát hàng nghìn save đồng thời, phần lớn công việc chỉ chờ tài nguyên và tạo áp lực bộ nhớ.

Khi nhiều câu lệnh chạy trên cùng một transaction connection, driver/database có thể không hỗ trợ thực thi song song trên connection đó. Trong transaction, dùng concatMap hoặc tuần tự hóa command trừ khi đã xác nhận khả năng của driver.

## 6. Batch statement với R2DBC Statement.add()

R2DBC SPI có API Statement.add() để thêm một bộ tham số vào cùng một statement. Ý tưởng là tạo SQL một lần, bind bộ giá trị thứ nhất, gọi add(), rồi bind bộ giá trị tiếp theo trước khi execute.

Ví dụ ở mức R2DBC SPI với PostgreSQL positional bind markers:

~~~java
Statement statement = connection.createStatement(
    "INSERT INTO people (first_name, email) VALUES ($1, $2)"
);

statement
    .bind(0, "Ada Lovelace")
    .bind(1, "ada@example.test")
    .add();

statement
    .bind(0, "Grace Hopper")
    .bind(1, "grace@example.test");

Publisher<? extends Result> results = statement.execute();
~~~

Ví dụ dùng marker positional của PostgreSQL; driver khác có thể dùng marker khác. API Statement.add() và khả năng thực thi batch phải được kiểm tra theo R2DBC driver cụ thể.

### add() làm gì?

- Giữ SQL statement cố định.
- Đưa bộ bind hiện tại vào batch.
- Cho phép bind bộ tham số tiếp theo.
- Execute statement với các bộ tham số đã tích lũy.

Batch statement khác với SQL nhiều hàng. Một batch có thể là cùng một câu INSERT được thực hiện với nhiều bộ tham số. SQL nhiều hàng là một câu INSERT chứa nhiều tuple VALUES.

### Không phải driver nào cũng tối ưu giống nhau

R2DBC SPI định nghĩa abstraction nhưng cách driver gửi batch tới server phụ thuộc implementation. Có driver hỗ trợ batch hiệu quả; có driver hoặc loại statement có giới hạn; có thể có khác biệt về generated values và rowsUpdated.

Không suy ra rằng Statement.add() luôn tạo đúng một network round trip hoặc luôn nhanh hơn multi-row INSERT. Hãy kiểm tra tài liệu driver và đo thực tế.

### Tích hợp với Spring transaction

Nếu tự dùng Connection và Statement, cần quản lý vòng đời connection đúng cách. Trong transaction do Spring quản lý, không tự mở connection mới rồi mong statement tham gia transaction hiện tại. Dùng connection được transaction infrastructure quản lý hoặc một custom repository implementation tích hợp đúng với connection binding/transaction context.

Nếu không cần điều khiển Statement.add() trực tiếp, ưu tiên API Spring Data được hỗ trợ và chỉ viết custom persistence code khi benchmark cho thấy cần thiết.

## 7. SQL nhiều hàng với INSERT ... VALUES

SQL nhiều hàng ghi nhiều tuple trong một câu INSERT:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada Lovelace', 'ada@example.test'),
    ('Grace Hopper', 'grace@example.test'),
    ('Katherine Johnson', 'katherine@example.test');
~~~

Cách này giảm số lần execute so với gửi một INSERT riêng cho từng hàng. Database parse và thực thi một câu lệnh chứa nhiều hàng.

Khi dùng tham số bind, ví dụ hai hàng:

~~~java
databaseClient.sql("""
    INSERT INTO people (first_name, email)
    VALUES
        (:name0, :email0),
        (:name1, :email1)
    """)
    .bind("name0", "Ada Lovelace")
    .bind("email0", "ada@example.test")
    .bind("name1", "Grace Hopper")
    .bind("email1", "grace@example.test")
    .fetch()
    .rowsUpdated();
~~~

Spring DatabaseClient hỗ trợ named parameter và chuyển đổi sang bind marker phù hợp driver. Ví dụ minh họa SQL cố định hai hàng; nếu số hàng động, ứng dụng phải tạo phần placeholder theo số lượng và bind mọi giá trị tương ứng.

### Chỉ tạo cấu trúc placeholder từ số lượng

Khi tạo SQL động, chỉ nối các dấu placeholder và identifier đã được whitelist. Không nối trực tiếp giá trị từ client vào SQL.

Ví dụ ý tưởng tạo placeholder:

~~~java
String values = IntStream.range(0, rows.size())
    .mapToObj(i -> "(:name" + i + ", :email" + i + ")")
    .collect(Collectors.joining(", "));

String sql = """
    INSERT INTO people (first_name, email)
    VALUES %s
    """.formatted(values);
~~~

Sau đó bind từng name/email bằng API DatabaseClient. Tên bảng/cột vẫn phải cố định hoặc đến từ allowlist. Các giá trị dữ liệu luôn được bind, không nối vào SQL text.

### Giới hạn bind parameters

Nếu mỗi hàng có C cột bind và database giới hạn tổng số parameter là P, số hàng tối đa theo giới hạn này không vượt quá:

\[
N \leq \left\lfloor \frac{P}{C} \right\rfloor
\]

Đây chỉ là giới hạn lý thuyết theo số bind parameter. Cần dành chỗ cho các tham số bổ sung và tuân theo giới hạn thực tế của database, driver, statement size và packet size.

Một INSERT có 500 hàng và 8 cột cần khoảng 4.000 giá trị bind. Với 5.000 hàng, số bind có thể lên tới 40.000. Database hoặc driver có thể từ chối trước khi đạt giới hạn lý thuyết khác.

### Generated ID và RETURNING

Một số database hỗ trợ RETURNING để trả ID hoặc các cột đã sinh:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada Lovelace', 'ada@example.test'),
    ('Grace Hopper', 'grace@example.test')
RETURNING id, first_name, email;
~~~

Khả năng RETURNING và cách R2DBC driver expose kết quả phụ thuộc database. Nếu cần ghép kết quả trở lại input, không giả định thứ tự row trả về luôn tương ứng thứ tự input trừ khi database/documentation bảo đảm. Nên dùng business key ổn định hoặc một correlation token có thể truy vấn.

## 8. Bulk loading chuyên dụng của database

Với khối lượng rất lớn, database thường cung cấp cơ chế nạp dữ liệu riêng có throughput cao hơn insert thông thường.

Ví dụ:

- PostgreSQL có lệnh/protocol COPY.
- Một số hệ quản trị có bulk insert, load data hoặc import utility riêng.
- Một số dịch vụ database hỗ trợ nạp file từ object storage.

Bulk loader có thể giảm đáng kể chi phí parse statement và bind từng hàng. Tuy nhiên, nó thường có semantics, API và yêu cầu format riêng.

Cần cân nhắc:

- Cơ chế bulk có bypass hoặc xử lý khác với trigger, constraint, default và index không?
- Dữ liệu lỗi được báo theo hàng hay cả file?
- Có hỗ trợ transaction/rollback không?
- Có thể stream dữ liệu từ nguồn mà không nạp toàn bộ file vào heap không?
- Có thể resume từ checkpoint không?
- Có cần quyền database đặc biệt hoặc file access trên server không?

Bulk loading phù hợp với import/export lớn, ETL hoặc nạp dữ liệu nền. Nó không phải lựa chọn mặc định cho request HTTP ghi một vài entity.

## 9. So sánh hiệu năng

Bảng dưới đây mô tả xu hướng thường gặp, không phải cam kết số lần round trip cụ thể của mọi driver:

| Chiến lược | Số lần execute ở mức ứng dụng | Khả năng giảm round trip | Độ phức tạp | Phù hợp |
| --- | --- | --- | --- | --- |
| Save từng hàng | Thường một execute cho mỗi hàng. | Thấp. | Thấp. | Lưu ít bản ghi, logic riêng từng entity. |
| saveAll | Phụ thuộc implementation; có thể vẫn save từng hàng. | Không được bảo đảm. | Thấp. | API repository chuẩn, tập dữ liệu vừa phải. |
| Chunk + saveAll | Nhiều save trong từng chunk. | Không tự giảm nếu implementation vẫn từng hàng. | Trung bình. | Kiểm soát memory và transaction scope. |
| flatMap concurrency | Nhiều save đồng thời. | Có thể tăng throughput nhờ overlap latency, không phải batching. | Trung bình. | I/O độc lập, database/pool còn capacity. |
| Statement.add batch | Một statement với nhiều bộ bind. | Có thể giảm số lần execute/round trip. | Cao hơn. | Cùng SQL lặp lại nhiều lần, driver hỗ trợ. |
| Multi-row INSERT | Một câu SQL chứa nhiều VALUES. | Thường giảm execute và round trip. | Trung bình/cao. | Insert nhiều hàng cùng cấu trúc. |
| Bulk loader | API/protocol nạp chuyên dụng. | Có thể cao nhất ở workload lớn. | Cao. | Import/ETL rất lớn, database hỗ trợ. |

Không có một phương pháp luôn nhanh nhất. Với batch nhỏ, chi phí tạo SQL động hoặc custom code có thể lớn hơn lợi ích. Với batch rất lớn, một câu SQL khổng lồ có thể vượt giới hạn packet/parameter và làm tăng memory.

### Các yếu tố ảnh hưởng

1. **Network latency:** càng xa database, giảm số lần trao đổi thường càng có lợi.
2. **Statement preparation:** SQL lặp lại có thể tận dụng prepared statement hoặc driver cache.
3. **Mapping:** reflection/conversion/callback có thể chiếm CPU ứng dụng.
4. **Index và constraint:** mỗi hàng vẫn phải cập nhật index và kiểm tra constraint.
5. **Transaction log:** ghi lớn tạo lượng WAL/redo log đáng kể.
6. **Lock contention:** transaction lớn giữ lock lâu hơn và có thể chặn workload khác.
7. **Connection pool:** concurrency quá cao làm pool cạn.
8. **Payload size:** hàng có JSON/BLOB lớn làm tăng packet và heap.
9. **Database load:** CPU, I/O và replication lag có thể trở thành bottleneck.

## 10. Backpressure và bộ nhớ khi xử lý dữ liệu lớn

Reactive không có nghĩa là có thể giữ một lượng dữ liệu vô hạn trong bộ nhớ. Operator buffer tạo collection cho mỗi chunk; nếu nguồn phát nhanh hơn khả năng ghi, cần kiểm soát lượng dữ liệu được giữ.

Ví dụ:

~~~java
return source
    .buffer(500)
    .concatMap(this::writeChunk);
~~~

concatMap đợi chunk hiện tại hoàn tất trước khi xử lý chunk tiếp theo. Điều này giới hạn số chunk đang được xử lý ở downstream.

Nếu dùng:

~~~java
return source
    .buffer(500)
    .flatMap(this::writeChunk, 4);
~~~

có thể có tối đa bốn chunk đang được xử lý đồng thời theo concurrency. Memory tối thiểu cho chunk có thể xấp xỉ concurrency nhân chunk size, chưa tính buffer nội bộ, dữ liệu đang phát và object overhead.

### Không collectList toàn bộ nguồn lớn

Tránh:

~~~java
return source.collectList()
    .flatMapMany(repository::saveAll);
~~~

Nếu source có hàng triệu entity, collectList giữ tất cả trong heap trước khi bắt đầu lưu. Dùng buffer(chunkSize) để giới hạn dữ liệu đang gom.

### Giới hạn nguồn dữ liệu

Nếu nguồn là file, stream message hoặc cursor, đảm bảo nguồn cũng đọc theo từng phần. Nếu trước đó đã load toàn bộ dữ liệu vào List, buffer phía sau không thể giảm bộ nhớ đã dùng.

Backpressure phải được duy trì xuyên suốt từ nguồn đọc tới downstream ghi. Tránh tạo subscription độc lập hoặc dùng queue không giới hạn để nối producer và writer.

## 11. Transaction và tính nguyên tử

Hiệu năng ghi cần được xem cùng semantics transaction.

### Không có transaction bao quanh toàn bộ

Các thao tác ghi có thể hoàn tất độc lập. Nếu một hàng lỗi sau nhiều hàng thành công, dữ liệu trước đó có thể vẫn tồn tại.

Phù hợp khi:

- Mỗi hàng độc lập.
- Có thể chấp nhận partial success.
- Có cơ chế retry hoặc checkpoint theo hàng/chunk.
- Import lớn cần tiến độ lâu dài.

### Một transaction cho toàn bộ import

~~~java
return transaction.transactional(
    source.concatMap(repository::save)
);
~~~

Nếu lỗi truyền ra khỏi transaction boundary, toàn bộ công việc có thể rollback. Đổi lại, transaction có thể kéo dài, giữ connection và lock lâu, tăng log và ảnh hưởng workload khác.

Phù hợp khi toàn bộ tập dữ liệu phải thành công hoặc thất bại cùng nhau và kích thước có giới hạn.

### Một transaction cho mỗi chunk

~~~java
return source
    .buffer(500)
    .concatMap(chunk ->
        transaction.transactional(
            repository.saveAll(chunk)
        )
    );
~~~

Mỗi chunk là một đơn vị commit riêng. Đây thường là điểm cân bằng giữa atomicity và throughput cho import lớn, nhưng cần có checkpoint để biết chunk nào đã commit.

Nếu chunk 8 thất bại, chunk 1–7 có thể đã commit. Retry phải nhận diện chunk đã xử lý để tránh duplicate.

### Transaction không tự biến save thành batch

@Transactional hoặc TransactionalOperator chỉ xác định transaction boundary. Chúng không thay đổi số SQL statement. Một transaction chứa 1.000 lần repository.save vẫn có thể thực thi 1.000 INSERT riêng.

## 12. Xử lý lỗi và partial success

Các chiến lược ghi có semantics lỗi khác nhau:

| Chiến lược | Khi một hàng lỗi | Trạng thái các hàng khác |
| --- | --- | --- |
| Từng hàng, không có transaction lớn | Publisher tuần tự thường dừng ở lỗi đầu tiên. | Hàng trước có thể đã commit. |
| Từng hàng trong transaction lớn | Lỗi thoát boundary có thể rollback toàn bộ. | Các hàng trước rollback theo transaction. |
| Chunk, transaction từng chunk | Chunk lỗi rollback; luồng có thể dừng. | Chunk trước đã commit; chunk sau chưa chạy. |
| Statement batch | Driver/database quyết định chi tiết báo lỗi batch. | Có thể có khác biệt về partial execution; cần test. |
| Multi-row INSERT | Thường lỗi ở statement khiến statement thất bại theo semantics database. | Các hàng trong statement thường thuộc cùng kết quả statement; transaction ngoài vẫn quyết định commit. |
| Bulk loader | Phụ thuộc API, chế độ lỗi và transaction của database. | Có thể dừng cả batch hoặc báo lỗi theo hàng. |

Không dựa vào giả định “batch lỗi thì không có hàng nào được ghi” nếu chưa xác nhận driver/database và transaction mode. Kiểm tra kết quả rowsUpdated, SQLSTATE, transaction state và dữ liệu sau lỗi.

### Không nuốt lỗi một cách tùy tiện

Ví dụ nguy hiểm:

~~~java
return source.flatMap(repository::save)
    .onErrorResume(error -> Mono.empty());
~~~

Cách này có thể biến lỗi ghi thành completion bình thường và khiến caller tưởng toàn bộ dữ liệu đã lưu. Nếu cần partial success, hãy biểu diễn kết quả rõ ràng:

~~~java
record RowWriteResult(
    int inputIndex,
    boolean saved,
    String errorCode
) {}
~~~

Mỗi hàng hoặc chunk có thể trả success/failure result, đồng thời ghi lại index hoặc business key để người vận hành xác định dữ liệu cần xử lý lại.

## 13. Retry và idempotency cho import

Retry là cần thiết khi gặp lỗi transient như deadlock hoặc connection interruption. Tuy nhiên, timeout có thể xảy ra sau khi database đã thực hiện insert nhưng trước khi ứng dụng nhận kết quả. Retry mù quáng có thể tạo bản ghi trùng.

Thiết kế import nên có:

- Business key ổn định hoặc idempotency key.
- Unique constraint ở database.
- Checkpoint theo chunk hoặc offset nguồn.
- Trạng thái import job và số hàng đã xử lý.
- Quy tắc xử lý duplicate rõ ràng.
- Retry có giới hạn và backoff.
- Khả năng tiếp tục từ chunk chưa commit.

Ví dụ upsert có thể giúp thao tác lặp an toàn, nhưng cú pháp và semantics khác nhau giữa database. Cần xác định khi trùng key thì bỏ qua, cập nhật hay báo conflict. Không dùng upsert nếu nó âm thầm ghi đè dữ liệu mới hơn.

### Retry toàn chunk hay từng hàng?

- Nếu chunk nằm trong một transaction và transaction rollback hoàn toàn, retry cả chunk có thể phù hợp.
- Nếu thao tác có thể partial commit, retry từng hàng hoặc dùng idempotency key.
- Nếu bulk API có checkpoint riêng, dùng cơ chế resume mà database hỗ trợ.
- Không retry SQL grammar, mapping hoặc constraint lỗi dữ liệu như thể đó là lỗi transient.

## 14. Generated ID, auditing và lifecycle behavior

Repository save có thể thực hiện mapping và entity callback theo cơ chế Spring Data. Khi chuyển sang custom batch SQL, một số behavior cần được tái tạo hoặc xác nhận.

Các câu hỏi:

- ID do database sinh có được trả về cho từng hàng không?
- @Version có được tăng và optimistic locking có được áp dụng không?
- BeforeConvert/BeforeSave/AfterSave callback có chạy không?
- Auditing fields có được điền không?
- Custom converters có được dùng cho từng bind parameter không?
- Entity trả về có phản ánh giá trị database default/trigger không?
- Có cần RETURNING để lấy generated columns không?

Custom SQL qua DatabaseClient không tự động bảo đảm toàn bộ entity lifecycle behavior như repository save. Nếu chuyển sang batch để tăng throughput, hãy xác định rõ behavior nào phải giữ và tự thực hiện phần còn thiếu ở application/persistence layer.

Với nhiều hàng có generated ID, không ghép ID trả về với input chỉ bằng vị trí nếu database/driver không đảm bảo thứ tự. Dùng correlation key ổn định nếu cần map kết quả.

## 15. Giới hạn kích thước batch và SQL

Một batch cần nằm trong giới hạn của nhiều tầng:

- Giới hạn bind parameter của database.
- Giới hạn statement length hoặc packet size.
- Giới hạn message/frame của driver.
- Heap memory để tạo SQL và giữ bind values.
- Thời gian parse/plan/execute.
- Transaction timeout.
- Giới hạn số hàng hoặc payload của bulk API.

Nếu một row có C cột bind và chunk có N hàng, tổng bind parameter xấp xỉ N × C, cộng các tham số khác. Chọn N sao cho không vượt giới hạn thực tế và còn khoảng an toàn.

SQL nhiều hàng càng lớn càng có thể làm parse time và memory tăng. Batch statement lặp cùng SQL có thể giảm phần SQL text lặp lại nhưng vẫn cần giữ các bộ binding. Bulk loader có thể phù hợp hơn khi dữ liệu rất lớn.

Đừng dùng một chunk size duy nhất cho mọi loại entity. Một hàng có 5 cột nhỏ khác nhiều so với hàng có 40 cột, JSON lớn hoặc binary payload.

## 16. Khi nào chọn chiến lược nào?

Có thể dùng bảng quyết định sau:

| Tình huống | Lựa chọn khởi đầu |
| --- | --- |
| Ghi một vài entity trong request | repository.save |
| Ghi số lượng vừa phải, cần mapping chuẩn | repository.saveAll, sau khi hiểu implementation |
| Stream nhiều entity và cần giới hạn memory | buffer(chunkSize) + concatMap |
| Cần concurrency cho các thao tác độc lập | flatMap với concurrency thấp, được đo và giới hạn |
| Lặp lại cùng một INSERT nhiều lần, driver hỗ trợ batch | R2DBC Statement.add() |
| Nhiều hàng cùng schema, cần giảm execute | Multi-row INSERT |
| Import dữ liệu rất lớn, database có bulk protocol | Bulk loading chuyên dụng |
| Cần partial success và resume | Chunk transaction + checkpoint + idempotency |
| Toàn bộ dữ liệu phải nguyên tử | Một transaction lớn nếu kích thước và thời gian phù hợp |

Hãy bắt đầu từ semantics nghiệp vụ rồi mới tối ưu cách gửi SQL. Ví dụ, nếu cần mỗi dòng được xác nhận độc lập và có thể retry riêng, một bulk statement duy nhất có thể không phù hợp dù throughput cao hơn.

## 17. Đo hiệu năng đúng cách

Không đánh giá chiến lược chỉ bằng thời gian chạy một lần trên laptop. Benchmark nên phản ánh kích thước dữ liệu, network và concurrency thực tế.

Các chỉ số nên thu thập:

- Rows per second.
- Tổng thời gian import.
- p50/p95/p99 latency cho mỗi chunk.
- Số statement execute và round trip nếu quan sát được.
- Connection pool acquisition time và active connections.
- CPU và memory phía ứng dụng.
- CPU, I/O, lock wait và transaction log phía database.
- Error rate, retry count và số hàng partial success.
- Replication lag nếu database có replica.

### So sánh công bằng

Khi so sánh từng hàng, saveAll, Statement.add và multi-row SQL:

1. Dùng cùng database version, driver và schema.
2. Dùng cùng số hàng và cùng kích thước row.
3. Giữ index, constraint và trigger giống nhau.
4. Dùng cùng transaction semantics.
5. Warm up connection pool và prepared statement nếu cần.
6. Chạy nhiều lần và lấy số liệu ổn định.
7. Kiểm tra dữ liệu sau import, không chỉ thời gian.
8. Thử dưới concurrency tương tự production.
9. Đo cả latency và resource consumption.
10. Thử các chunk size khác nhau.

Nếu một phương pháp chạy nhanh hơn chỉ vì bỏ auditing, constraint hoặc transaction, đó không phải so sánh tương đương.

## 18. Kiểm thử từng chiến lược

Repository test bằng @DataR2dbcTest phù hợp cho save/saveAll và mapping. Custom batch hoặc multi-row SQL cần integration test trên driver/database mục tiêu.

Các trường hợp nên xác nhận:

- Số hàng được insert đúng.
- Generated ID được trả về hoặc có thể tra cứu.
- Duplicate key và constraint lỗi đúng như dự kiến.
- Lỗi giữa chunk có tạo partial success hay rollback theo yêu cầu.
- Retry cùng chunk không tạo duplicate.
- Batch statement driver thực sự hỗ trợ.
- Multi-row SQL không vượt bind parameter/packet limit.
- Transaction rollback đúng khi publisher lỗi.
- Dữ liệu được đọc lại và mapping đúng.
- Callback/auditing có chạy hoặc được xử lý thay thế rõ ràng.

Ví dụ test multi-row insert theo DatabaseClient:

~~~java
@Test
void insertsMultiplePeopleWithOneStatement() {
    String suffix = UUID.randomUUID().toString();

    StepVerifier.create(
        databaseClient.sql("""
            INSERT INTO people (first_name, email)
            VALUES (:name0, :email0), (:name1, :email1)
            """)
            .bind("name0", "Ada")
            .bind("email0", "ada-" + suffix + "@example.test")
            .bind("name1", "Grace")
            .bind("email1", "grace-" + suffix + "@example.test")
            .fetch()
            .rowsUpdated()
    )
    .expectNext(2L)
    .verifyComplete();
}
~~~

Ví dụ giả định driver trả rowsUpdated dưới dạng Long và schema không có trigger thay đổi số hàng được báo. Điều chỉnh kiểu assert theo driver/API đang dùng.

## 19. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nghĩ saveAll là một INSERT nhiều hàng | Nhầm API lưu nhiều entity với bulk SQL. | Xem implementation và đo số statement. |
| buffer rồi gọi saveAll nhưng vẫn chậm | Chỉ gom dữ liệu ở ứng dụng; saveAll vẫn có thể ghi từng entity. | Dùng batch/multi-row SQL khi phù hợp. |
| Tăng flatMap concurrency quá cao | Pool và database bị quá tải. | Giới hạn concurrency và benchmark. |
| flatMap làm thay đổi thứ tự | Các publisher con hoàn tất không theo thứ tự nguồn. | Dùng concatMap nếu thứ tự là yêu cầu. |
| Một chunk quá lớn | Vượt bind/packet limit hoặc tốn heap. | Giảm chunk size và đo. |
| Một transaction bao trùm import quá lâu | Giữ connection/lock và tạo log lớn. | Transaction theo chunk nếu nghiệp vụ cho phép. |
| Batch lỗi nhưng không biết hàng nào | Batch API chỉ trả lỗi tổng thể hoặc driver không có chi tiết per-row. | Lưu business key, chia chunk nhỏ và ghi failure report. |
| Retry tạo duplicate | Timeout xảy ra sau khi insert đã commit. | Idempotency key và unique constraint. |
| Generated ID ghép sai entity | Giả định thứ tự RETURNING luôn giống input. | Dùng correlation key và xác minh semantics driver. |
| Custom SQL bỏ qua callback/auditing | Đường SQL thuần không đi qua toàn bộ entity lifecycle. | Thực hiện metadata cần thiết rõ ràng và test. |
| Dữ liệu mất khi process restart | Chưa có checkpoint hoặc trạng thái import bền vững. | Lưu tiến độ theo chunk và resume an toàn. |

## 20. Quy trình chọn và triển khai chiến lược ghi

Khi cần tăng tốc ghi nhiều hàng bằng R2DBC, hãy làm theo trình tự:

1. **Xác định yêu cầu nghiệp vụ:** toàn bộ phải atomic hay cho phép partial success?
2. **Đo baseline:** ghi từng hàng hoặc saveAll hiện tại và thu thập throughput/latency.
3. **Kiểm tra implementation:** xác nhận saveAll thực thi theo cách nào trong phiên bản đang dùng.
4. **Giới hạn nguồn:** dùng buffer để không giữ toàn bộ dataset trong memory.
5. **Chọn cách gửi:** save từng hàng, concurrency có giới hạn, Statement.add, multi-row INSERT hoặc bulk loader.
6. **Chọn transaction scope:** toàn bộ import hay từng chunk.
7. **Tính giới hạn:** bind parameter, packet, statement size, memory và timeout.
8. **Thiết kế lỗi/retry:** idempotency, checkpoint, partial success và failure report.
9. **Giữ behavior cần thiết:** generated ID, converters, callbacks, auditing và optimistic locking.
10. **Integration test:** chạy trên database/driver thực tế và xác nhận dữ liệu sau ghi.
11. **Benchmark:** thay đổi một yếu tố mỗi lần, đo throughput và tài nguyên.
12. **Theo dõi production:** giám sát pool, query latency, lock, error rate và import progress.

Ghi từng hàng là lựa chọn rõ ràng và phù hợp với workload nhỏ hoặc logic riêng cho từng entity. Ghi theo nhóm giúp giới hạn memory và tổ chức transaction, nhưng bản thân việc gom chunk không làm giảm số SQL statement. Statement.add và SQL nhiều hàng có thể giảm số lần execute/round trip khi driver/database hỗ trợ; bulk loading dành cho import rất lớn. Chọn chiến lược theo semantics atomicity, khả năng retry và behavior persistence cần giữ, sau đó benchmark trên đúng driver và database thay vì giả định một API có tên “batch” luôn tạo ra đường ghi tối ưu.

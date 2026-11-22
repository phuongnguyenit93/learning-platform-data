# SQL chèn nhiều hàng và giới hạn của từng hệ quản trị

Khi cần ghi nhiều bản ghi bằng Spring Data Relational R2DBC, một câu INSERT nhiều hàng có thể giảm số lần gửi lệnh tới database so với việc thực hiện một INSERT cho từng entity. Tuy nhiên, số hàng có thể đưa vào một câu lệnh không vô hạn. Giới hạn bind parameter, kích thước packet, độ dài SQL, bộ nhớ ứng dụng, transaction, cú pháp riêng của database và khả năng của R2DBC driver đều ảnh hưởng tới kích thước batch.

Cú pháp phổ biến là:

~~~sql
INSERT INTO products (name, price, status)
VALUES
    ('Keyboard', 49.90, 'ACTIVE'),
    ('Mouse', 19.90, 'ACTIVE'),
    ('Monitor', 229.00, 'ACTIVE');
~~~

Trong ứng dụng, không nối giá trị trực tiếp vào SQL như ví dụ minh họa. Hãy tạo placeholder và bind từng giá trị. Tên bảng/cột phải cố định hoặc được chọn từ allowlist phía server.

Bài học này giải thích cách xây dựng multi-row INSERT bằng DatabaseClient, cách phân biệt nó với R2DBC Statement.add(), cách tính giới hạn bind parameters và packet, sự khác biệt giữa PostgreSQL, MySQL/MariaDB, SQL Server, SQLite và Oracle, cách chọn chunk size, xử lý generated keys, transaction, lỗi và kiểm thử trên database thật.

## 1. Multi-row INSERT là gì?

Multi-row INSERT chèn nhiều tuple vào cùng một câu lệnh:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada Lovelace', 'ada@example.test'),
    ('Grace Hopper', 'grace@example.test'),
    ('Katherine Johnson', 'katherine@example.test');
~~~

Nếu có N hàng và mỗi hàng có C cột dữ liệu được bind, tổng số bind parameter xấp xỉ:

\[
P = N \times C
\]

Nếu statement còn có K parameter dùng chung, tổng là:

\[
P = N \times C + K
\]

Do đó, nếu database/driver cho phép tối đa Pmax parameter, số hàng tối đa theo riêng giới hạn parameter là:

\[
N_{max} = \left\lfloor \frac{P_{max} - K}{C} \right\rfloor
\]

Đây chỉ là một giới hạn. Số hàng thực tế còn bị giới hạn bởi packet size, SQL text size, số hàng tối đa theo cú pháp vendor, memory, thời gian thực thi và transaction budget.

### So sánh với ghi từng hàng

Giả sử cần insert 1.000 hàng, mỗi hàng có 5 cột:

- Ghi từng hàng: thường có 1.000 lần thực thi INSERT.
- Multi-row INSERT: có thể chia thành 10 statement, mỗi statement 100 hàng.
- Statement batch: có thể gửi cùng một SQL statement với 1.000 bộ bind, tùy driver.
- Bulk loader: dùng giao thức nạp dữ liệu riêng của database.

Multi-row INSERT thường giảm số lần execute và round trip. Nhưng nó không làm database bỏ qua index, constraint, trigger, WAL/redo log hoặc chi phí ghi dữ liệu thực tế.

## 2. Multi-row INSERT khác gì saveAll và Statement.add()?

Các cơ chế sau thường bị gọi chung là batch nhưng có semantics khác nhau.

| Cơ chế | Cách hoạt động | Có phải một SQL chứa nhiều VALUES? |
| --- | --- | --- |
| repository.save từng entity | Gọi logic save cho từng entity. | Không. |
| repository.saveAll | API lưu nhiều entity; implementation có thể vẫn lưu từng entity. | Không được bảo đảm. |
| buffer(chunk) + saveAll | Gom dữ liệu ở tầng ứng dụng rồi gọi saveAll. | Không tự động. |
| R2DBC Statement.add() | Nhiều bộ bind cho cùng một statement, nếu driver hỗ trợ. | Không nhất thiết. |
| Multi-row INSERT | Một câu INSERT chứa nhiều tuple VALUES. | Có. |
| Bulk loading | Dùng protocol/API nạp dữ liệu riêng. | Không nhất thiết dùng INSERT. |

Tên saveAll không phải cam kết rằng Spring Data phát một câu INSERT nhiều hàng. Nếu muốn giảm số tuple trong một statement, cần kiểm soát câu SQL hoặc dùng API batch mà driver hỗ trợ.

### Khi nào chọn cách nào?

- Lưu vài entity trong request: repository.save thường đơn giản nhất.
- Lưu một tập vừa phải, cần Spring Data mapping: saveAll sau khi xác nhận implementation và hiệu năng.
- Cần một câu INSERT với nhiều tuple: DatabaseClient và multi-row VALUES.
- Cùng SQL được thực thi nhiều lần: cân nhắc Statement.add() nếu driver hỗ trợ.
- Import rất lớn: cân nhắc bulk loader như PostgreSQL COPY hoặc cơ chế tương ứng.

## 3. Dùng DatabaseClient cho multi-row INSERT

DatabaseClient cho phép tạo SQL với số lượng tuple xác định và bind các giá trị. Ví dụ cố định hai hàng:

~~~java
Mono<Integer> insertTwoPeople(
        DatabaseClient databaseClient,
        String firstEmail,
        String secondEmail) {

    return databaseClient.sql("""
        INSERT INTO people (first_name, email)
        VALUES (:name0, :email0), (:name1, :email1)
        """)
        .bind("name0", "Ada Lovelace")
        .bind("email0", firstEmail)
        .bind("name1", "Grace Hopper")
        .bind("email1", secondEmail)
        .fetch()
        .rowsUpdated();
}
~~~

Các giá trị email và name được bind. SQL text chỉ chứa tên bảng, tên cột và placeholder cố định.

### Tạo số tuple động

Khi số hàng thay đổi theo chunk, tạo placeholder theo số index. Chỉ số index do ứng dụng tạo, không lấy SQL fragment từ request.

~~~java
Mono<Long> insertPeople(
        DatabaseClient databaseClient,
        List<PersonInput> people) {

    if (people.isEmpty()) {
        return Mono.just(0L);
    }

    String tuples = IntStream.range(0, people.size())
        .mapToObj(i -> "(:name" + i + ", :email" + i + ")")
        .collect(Collectors.joining(", "));

    String sql = """
        INSERT INTO people (first_name, email)
        VALUES %s
        """.formatted(tuples);

    DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(sql);

    for (int i = 0; i < people.size(); i++) {
        PersonInput person = people.get(i);
        spec = spec
            .bind("name" + i, person.name())
            .bind("email" + i, person.email());
    }

    return spec.fetch()
        .rowsUpdated()
        .map(Integer::longValue);
}
~~~

Đoạn code minh họa với hai cột không null. Với field nullable, DatabaseClient không nhận null qua bind thông thường; dùng bindNull với kiểu Java tương ứng:

~~~java
spec = spec.bindNull("nickname" + i, String.class);
~~~

Cần chọn kiểu bind đúng với mapping và driver. Với enum, JSON, array hoặc value object, có thể cần converter hoặc kiểu dữ liệu đặc thù.

### Các quy tắc an toàn

- Tên bảng/cột nằm cố định trong code hoặc đến từ allowlist.
- Chỉ số placeholder được sinh từ số hàng.
- Mọi dữ liệu đều bind.
- Không nối giá trị name/email vào SQL text.
- Từ chối hoặc xử lý rõ danh sách rỗng.
- Giới hạn kích thước chunk trước khi tạo SQL.
- Không tạo một câu SQL không giới hạn từ toàn bộ file import.

## 4. Bind parameter và cách tính số hàng tối đa

Giả sử mỗi hàng có 8 cột bind, statement có thêm 2 parameter dùng chung và giới hạn driver/database là 2.100 parameter:

\[
N_{max} = \left\lfloor \frac{2100 - 2}{8} \right\rfloor = 262
\]

262 hàng là mức tối đa theo riêng giới hạn parameter trong ví dụ. Không nên mặc định chọn đúng mức này vì còn overhead và giới hạn khác. Có thể bắt đầu thấp hơn rồi benchmark.

### Tính theo nhiều giới hạn

Kích thước chunk an toàn nên xét đồng thời:

\[
N \leq \min(
N_{parameters},
N_{packet},
N_{statement},
N_{vendor},
N_{application}
)
\]

Trong đó:

- Nparameters: giới hạn bind parameters chia cho số parameter mỗi hàng.
- Npacket: giới hạn packet/message chia cho kích thước payload trung bình.
- Nstatement: giới hạn độ dài SQL và thời gian parse.
- Nvendor: giới hạn số hàng/cú pháp của hệ quản trị.
- Napplication: giới hạn memory, latency và transaction do ứng dụng đặt ra.

Các giới hạn packet không thể tính chính xác chỉ từ kích thước Java object. Cần tính cả protocol overhead, encoding, tên parameter và SQL text.

### Không dùng con số tối đa làm chunk size mặc định

Nếu database cho phép 2.100 parameter, không có nghĩa batch 2.100 parameter là tối ưu. Statement lớn có thể tốn thời gian parse, chiếm memory, tạo transaction dài và làm lỗi một chunk ảnh hưởng nhiều hàng hơn.

Hãy chọn mức thấp hơn giới hạn kỹ thuật, đo throughput và p95/p99 latency rồi điều chỉnh.

## 5. Giới hạn và đặc điểm của PostgreSQL

PostgreSQL hỗ trợ multi-row VALUES:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada', 'ada@example.test'),
    ('Grace', 'grace@example.test');
~~~

Có thể trả generated values bằng RETURNING:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada', 'ada@example.test'),
    ('Grace', 'grace@example.test')
RETURNING id, first_name, email;
~~~

### Bind parameter limit

PostgreSQL extended query protocol sử dụng trường đếm parameter có độ rộng 16 bit; giới hạn thường được nhắc tới là 65.535 parameter cho một prepared/extended statement. Đây là giới hạn protocol, không phải khuyến nghị tạo một statement với hàng chục nghìn parameter.

Với 10 cột bind mỗi hàng, giới hạn lý thuyết theo parameter là khoảng 6.553 hàng, trước khi tính giới hạn statement size, memory, packet và driver.

### RETURNING

RETURNING hữu ích khi cần ID hoặc cột do database sinh. Với multi-row INSERT, kết quả có thể chứa nhiều row. Nếu cần ghép kết quả về đúng input, nên có business key/correlation key rõ ràng; không mặc định thứ tự row trả về luôn tương ứng thứ tự input trừ khi semantics database/driver đã được xác nhận.

### COPY cho import lớn

Với dữ liệu rất lớn, PostgreSQL COPY thường hiệu quả hơn tạo một INSERT khổng lồ. COPY có API/protocol riêng, cách truyền dữ liệu và semantics riêng. R2DBC SPI không cung cấp một API COPY portable; cần driver hoặc thư viện PostgreSQL-specific được hỗ trợ.

COPY phù hợp với ETL/import lớn. Nếu cần domain validation, generated IDs, callbacks hoặc per-row error mapping, phải thiết kế các bước bổ sung.

## 6. Giới hạn và đặc điểm của MySQL/MariaDB

MySQL và MariaDB hỗ trợ multi-row INSERT:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada', 'ada@example.test'),
    ('Grace', 'grace@example.test'),
    ('Katherine', 'katherine@example.test');
~~~

Có thể dùng cú pháp upsert theo vendor, ví dụ ON DUPLICATE KEY UPDATE của MySQL/MariaDB. Đây là cú pháp riêng và semantics cập nhật khi trùng key cần được xác định rõ.

### max_allowed_packet

Một giới hạn quan trọng là kích thước packet. max_allowed_packet cấu hình kích thước message mà client/server chấp nhận. Một multi-row INSERT có thể bị từ chối khi SQL text cộng bind values vượt giới hạn packet.

Giá trị mặc định và mức tối đa phụ thuộc phiên bản, server configuration và client/driver. Không hard-code một con số dùng chung cho mọi MySQL/MariaDB. Kiểm tra cấu hình server thực tế và driver.

### Prepared statement parameters

Giao thức prepared statement của MySQL biểu diễn số parameter bằng trường đếm 16 bit, nhưng packet size, statement size và driver behavior thường là giới hạn thực tế cần theo dõi cùng lúc. Không chỉ dựa vào một con số parameter để chọn batch size.

### Generated IDs

Với AUTO_INCREMENT, driver có thể cung cấp generated value theo khả năng của R2DBC implementation. Không tự suy ra mọi ID trong multi-row insert bằng cách lấy ID đầu rồi cộng 1: concurrent insert, auto increment increment/offset, trigger và cấu hình server có thể làm giả định đó sai.

Nếu cần map generated IDs chính xác về input, hãy dùng API generated values mà driver hỗ trợ hoặc query lại bằng unique business key.

## 7. Giới hạn và đặc điểm của SQL Server

SQL Server hỗ trợ table value constructor trong INSERT:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada', 'ada@example.test'),
    ('Grace', 'grace@example.test');
~~~

### Giới hạn 1.000 row trong INSERT ... VALUES

SQL Server giới hạn table value constructor dùng trực tiếp trong INSERT ... VALUES ở mức 1.000 row cho một statement. Table value constructor được dùng như derived table trong một số ngữ cảnh SELECT có semantics giới hạn khác, nhưng không nên chuyển cú pháp một cách máy móc mà chưa xem execution plan và tài liệu phiên bản.

### Giới hạn 2.100 parameter

SQL Server có giới hạn 2.100 parameter cho stored procedure và function; giới hạn parameter của các statement được thực thi qua driver cũng là một ràng buộc thực tế cần xác minh với provider/version. Khi dùng prepared statement có nhiều bind marker, nên giữ tổng parameter dưới mức 2.100 để tránh lỗi giới hạn.

Với 10 cột bind mỗi hàng, mức lý thuyết theo 2.100 parameter chỉ khoảng 210 hàng, thấp hơn giới hạn 1.000 row của VALUES. Giới hạn parameter thường trở thành yếu tố quyết định trước.

### OUTPUT INSERTED

SQL Server dùng OUTPUT INSERTED để trả generated values:

~~~sql
INSERT INTO people (first_name, email)
OUTPUT INSERTED.id, INSERTED.first_name
VALUES
    ('Ada', 'ada@example.test'),
    ('Grace', 'grace@example.test');
~~~

Cú pháp này khác RETURNING của PostgreSQL. Cần kiểm tra driver có hỗ trợ trả generated rows trong R2DBC statement hay không.

### Bulk copy và table-valued parameters

Với import lớn hoặc dữ liệu được gửi theo cấu trúc bảng, SQL Server có các cơ chế như bulk copy và table-valued parameters. Khả năng sử dụng từ R2DBC phụ thuộc driver/thư viện. Có thể cần một đường tích hợp vendor-specific thay vì cố biểu diễn mọi workload bằng một câu INSERT rất lớn.

## 8. Giới hạn và đặc điểm của SQLite

SQLite hỗ trợ multi-row VALUES:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada', 'ada@example.test'),
    ('Grace', 'grace@example.test');
~~~

Một giới hạn quan trọng là số host parameter trong một prepared statement.

- SQLite trước phiên bản 3.32.0 thường có default SQLITE_MAX_VARIABLE_NUMBER là 999.
- Từ SQLite 3.32.0, default thường là 32.766.
- Giá trị thực tế có thể được thay đổi lúc compile bằng SQLITE_MAX_VARIABLE_NUMBER hoặc giảm ở runtime bằng sqlite3_limit.

Đây là giới hạn cấu hình/compile-time, không phải con số bất biến cho mọi bản SQLite.

### Ví dụ tính batch

Nếu SQLite đang dùng giới hạn 999 variable và mỗi hàng có 6 bind parameter:

\[
N_{max} = \left\lfloor \frac{999}{6} \right\rfloor = 166
\]

Nếu binary dùng giới hạn 32.766, mức lý thuyết cao hơn nhiều. Ứng dụng nên kiểm tra version/build thực tế hoặc chọn chunk bảo thủ tương thích với môi trường triển khai.

### SQLite và concurrency

SQLite là database embedded, không có mô hình connection server giống PostgreSQL. Ghi đồng thời có thể bị giới hạn bởi locking và journal mode. Tăng số connection không đồng nghĩa tăng write throughput tuyến tính.

Với workload ghi cạnh tranh, cân nhắc serialize writer, chia transaction và dùng busy timeout phù hợp. Test trên đúng driver và SQLite build của ứng dụng.

## 9. Oracle: cú pháp và chiến lược khác biệt

Không nên giả định mọi database hỗ trợ cùng cú pháp:

~~~sql
INSERT INTO table_name (a, b)
VALUES (...), (...);
~~~

Các phiên bản Oracle truyền thống thường dùng multi-table insert syntax như INSERT ALL hoặc các chiến lược INSERT ... SELECT/array binding thay vì cú pháp multi-row VALUES giống PostgreSQL/MySQL. Khả năng cú pháp thay đổi theo phiên bản Oracle; xác nhận tài liệu phiên bản database đang triển khai.

Ví dụ INSERT ALL:

~~~sql
INSERT ALL
    INTO people (first_name, email) VALUES ('Ada', 'ada@example.test')
    INTO people (first_name, email) VALUES ('Grace', 'grace@example.test')
SELECT 1 FROM dual;
~~~

Đây là cú pháp Oracle-specific. Mỗi INTO là một target insert trong cùng statement.

### Array binding/batch execution

Với nhiều hàng có cùng SQL shape, array binding hoặc batch execution của driver có thể phù hợp hơn tạo một câu SQL rất dài. Với R2DBC, cần xác minh driver Oracle hỗ trợ Statement.add() và generated values như thế nào.

### IN-list limit không phải multi-row INSERT limit

Oracle có các giới hạn riêng cho số expression trong IN list theo phiên bản; giới hạn này không được đồng nhất với số row của INSERT ALL hoặc số bind parameter của prepared statement. Khi xây dựng query IN, hãy kiểm tra phiên bản cụ thể và chia danh sách hoặc dùng collection/table mechanism phù hợp.

Không lấy giới hạn IN-list làm chunk size cho INSERT.

## 10. Bảng so sánh nhanh giữa các hệ quản trị

| Database | Multi-row insert | Giới hạn thường cần kiểm tra | Cách trả generated values / bulk |
| --- | --- | --- | --- |
| PostgreSQL | VALUES (...), (...) | Extended protocol có giới hạn 65.535 bind parameters; thêm statement/memory/driver limits. | RETURNING; COPY cho import lớn. |
| MySQL | VALUES (...), (...) | max_allowed_packet, statement size và prepared parameter count. | AUTO_INCREMENT/driver generated values; bulk/load utilities. |
| MariaDB | VALUES (...), (...) | max_allowed_packet và giới hạn driver/server version. | AUTO_INCREMENT; bulk/load utilities. |
| SQL Server | VALUES (...), (...) | 1.000 row trong INSERT VALUES; 2.100 parameter là giới hạn quan trọng. | OUTPUT INSERTED; bulk copy/TVP. |
| SQLite | VALUES (...), (...) | SQLITE_MAX_VARIABLE_NUMBER: mặc định phổ biến 999 trước 3.32.0, 32.766 từ 3.32.0; build có thể khác. | last_insert_rowid/driver support; transaction batch. |
| Oracle | Cú pháp phụ thuộc version; INSERT ALL/array binding là lựa chọn truyền thống. | Bind, SQL size và giới hạn expression/IN-list riêng theo version. | RETURNING/array binding và cơ chế bulk của driver. |

Các con số trên là mốc kỹ thuật thường gặp, không phải cấu hình đảm bảo cho mọi bản phân phối hoặc driver. Luôn xác minh server version, build options, driver version, protocol và cấu hình thực tế.

## 11. Giới hạn packet và kích thước SQL

Ngay cả khi parameter count còn dưới giới hạn, statement vẫn có thể quá lớn.

Kích thước message phụ thuộc:

- Độ dài SQL text và số placeholder.
- Kích thước chuỗi UTF-8.
- Kích thước JSON/BLOB/binary.
- Kiểu dữ liệu được encode.
- Protocol framing và metadata.
- Driver có tạo bản sao buffer trong memory hay không.

Ví dụ, 500 hàng với 3 cột số nhỏ khác rất nhiều so với 500 hàng có một JSON document vài trăm KB.

### MySQL packet

MySQL/MariaDB có max_allowed_packet. Nếu statement hoặc packet vượt cấu hình, server/driver có thể trả lỗi packet quá lớn hoặc connection bị đóng tùy trường hợp. Kiểm tra cả cấu hình client/server và driver.

### PostgreSQL message và statement

PostgreSQL có giới hạn protocol parameter count, nhưng statement text và message size cũng chịu giới hạn thực tế về memory, protocol và server. Không dùng 65.535 parameter làm mục tiêu batch.

### SQL Server và SQLite

SQL Server có giới hạn row constructor/parameter. SQLite có host parameter limit theo build/runtime. Trong cả hai, statement size và thời gian thực thi vẫn có thể trở thành giới hạn trước khi chạm parameter cap.

## 12. Chọn chunk size có kiểm soát

Chunk size nên dựa trên giới hạn thấp nhất trong các giới hạn liên quan, sau đó giảm thêm để tạo headroom.

Một công thức định hướng:

\[
N_{chunk} = \min(
\lfloor P_{safe}/C \rfloor,
N_{packet},
N_{vendor},
N_{memory},
N_{latency}
)
\]

Trong đó:

- Psafe là ngân sách parameter thấp hơn giới hạn tuyệt đối.
- C là số cột/parameter mỗi row.
- Npacket là số row phù hợp packet budget.
- Nvendor là giới hạn cú pháp của database.
- Nmemory là số row ứng dụng có thể giữ an toàn.
- Nlatency là số row có thể xử lý trong transaction/request budget.

Ví dụ với SQL Server, 8 cột bind mỗi hàng và ngân sách 1.800 parameter:

\[
N_{chunk} \leq \lfloor 1800/8 \rfloor = 225
\]

Có thể bắt đầu ở 100 hoặc 150 hàng, đo rồi tăng. Không cần sát giới hạn 2.100.

### Chunk size phụ thuộc row shape

Không dùng cùng một chunk size cho tất cả bảng. Bảng có 4 cột nhỏ có thể dùng chunk lớn hơn bảng có 30 cột, JSON lớn hoặc binary data.

Nếu một chunk bị rollback, toàn bộ chunk có thể phải retry. Chunk lớn hơn cũng làm phạm vi lỗi và thời gian transaction lớn hơn.

## 13. Xử lý danh sách rỗng và null

Danh sách rỗng không nên tạo SQL:

~~~sql
INSERT INTO people (name, email) VALUES
~~~

Trả Mono.just(0L) hoặc Mono.empty theo contract của repository helper.

Field nullable cần bind null với kiểu Java rõ ràng:

~~~java
spec = spec.bindNull("middleName0", String.class);
~~~

Không dùng bind("middleName0", null) nếu API không chấp nhận null. Với enum hoặc kiểu custom, cần chọn Java type/converter phù hợp.

Nếu một hàng có dữ liệu không hợp lệ, quyết định trước khi tạo statement:

- Reject toàn bộ chunk.
- Loại riêng row không hợp lệ và ghi failure report.
- Chia nhỏ để tìm row gây lỗi.
- Dùng staging table để kiểm tra dữ liệu trước khi chuyển sang bảng chính.

Không âm thầm bỏ row mà không báo số lượng và lý do.

## 14. Generated IDs và kết quả insert

Multi-row INSERT có thể tạo nhiều ID. Cách lấy ID khác nhau giữa database và driver:

| Database | Cơ chế phổ biến |
| --- | --- |
| PostgreSQL | RETURNING id, ... |
| SQL Server | OUTPUT INSERTED.id |
| MySQL/MariaDB | AUTO_INCREMENT và generated values theo driver |
| SQLite | last_insert_rowid cho connection; driver-specific behavior cho batch |
| Oracle | RETURNING INTO hoặc array/batch binding tùy API |

R2DBC SPI có Statement.returnGeneratedValues(...) trong các phiên bản hỗ trợ, nhưng driver phải triển khai capability tương ứng. Kiểm tra driver version và integration test, không giả định API portable sẽ trả toàn bộ generated IDs cho mọi multi-row statement.

### Không suy ra ID bằng phép cộng

Không lấy generated ID đầu tiên rồi tự cộng 1 cho các hàng tiếp theo. ID sequence/identity có thể bị ảnh hưởng bởi concurrent inserts, increment/offset, rollback, trigger, cache và cấu hình database.

Nếu cần liên kết kết quả với input, dùng business key duy nhất hoặc correlation key được lưu cùng row. Khi database trả nhiều row qua RETURNING/OUTPUT, map theo key ổn định thay vì chỉ dựa vào vị trí.

## 15. Transaction và atomicity

Một multi-row INSERT thường là một statement. Nếu statement thất bại, database xử lý statement theo semantics của nó. Tuy nhiên, kết quả cuối cùng còn phụ thuộc transaction, constraint, trigger và database engine.

Các lựa chọn:

### Một statement cho một chunk

Mỗi chunk là một statement. Nếu không có transaction bao toàn bộ import, các chunk trước có thể đã commit khi chunk sau thất bại.

### Một transaction cho nhiều chunk

~~~java
return transactionalOperator.transactional(
    Flux.fromIterable(chunks)
        .concatMap(this::insertChunk)
);
~~~

Nếu lỗi thoát khỏi transaction boundary, toàn bộ các chunk trong transaction có thể rollback. Đổi lại, transaction kéo dài và giữ connection/lock lâu hơn.

### Một transaction cho mỗi chunk

~~~java
return Flux.fromIterable(chunks)
    .concatMap(chunk ->
        transactionalOperator.transactional(insertChunk(chunk))
    );
~~~

Mỗi chunk commit độc lập. Khi chunk sau lỗi, chunk trước vẫn có thể đã commit. Cần checkpoint/idempotency để retry an toàn.

### Transaction không tự làm batch

Bọc 1.000 lệnh save trong một transaction không biến chúng thành một multi-row INSERT. Transaction kiểm soát atomicity, không thay đổi số SQL statement.

## 16. Constraint, upsert và xử lý duplicate

Multi-row INSERT có thể gặp một hàng vi phạm UNIQUE, CHECK hoặc FOREIGN KEY. Cách database xử lý statement và transaction phụ thuộc vendor.

Các cú pháp upsert phổ biến:

- PostgreSQL: ON CONFLICT ... DO NOTHING/DO UPDATE.
- MySQL/MariaDB: ON DUPLICATE KEY UPDATE.
- SQL Server: có thể dùng UPDATE/INSERT có điều kiện hoặc cơ chế phù hợp; cần cẩn trọng với MERGE theo version/semantics.
- SQLite: ON CONFLICT.
- Oracle: MERGE hoặc cơ chế insert/update phù hợp.

Không dùng một cú pháp upsert chung cho mọi database. Quy định rõ duplicate sẽ bị bỏ qua, cập nhật hay trả conflict. Upsert có thể ghi đè dữ liệu mới hơn nếu điều kiện cập nhật không đủ chặt.

### Một row lỗi có thể ảnh hưởng cả statement

Nếu một tuple vi phạm constraint, multi-row statement có thể thất bại. Đừng mặc định các tuple hợp lệ khác vẫn được ghi. Hãy kiểm tra trên database mục tiêu.

Nếu cần per-row success/failure, chia chunk nhỏ, validate trước hoặc dùng staging table để phân loại lỗi. Không nuốt exception rồi báo toàn bộ batch thành công.

## 17. Dynamic SQL an toàn

Tạo số lượng tuple động là cần thiết, nhưng chỉ phần placeholder được sinh từ count. Không cho client điều khiển table, column hoặc SQL expression.

Ví dụ an toàn:

~~~java
String tupleSql = IntStream.range(0, rows.size())
    .mapToObj(i -> "(:name" + i + ", :price" + i + ")")
    .collect(Collectors.joining(", "));

String sql = """
    INSERT INTO products (name, price)
    VALUES %s
    """.formatted(tupleSql);
~~~

Tên bảng products và tên cột name, price là cố định. Các giá trị name/price được bind.

Nếu phải chọn table theo tenant hoặc archive, map key sang allowlist server-side. Không nối request.tableName hoặc request.sort vào SQL.

### Không dùng escaping thay bind

Không tự thêm quote quanh chuỗi rồi nối vào SQL. Dấu quote, backslash, encoding và dialect có quy tắc riêng. Bind parameter là cơ chế đúng cho value.

## 18. Khi nào nên dùng Statement.add()?

R2DBC SPI Statement.add() cho phép thêm bộ bind hiện tại vào batch của cùng statement. Ví dụ khái quát:

~~~java
Statement statement = connection.createStatement(
    "INSERT INTO people (first_name, email) VALUES ($1, $2)"
);

statement
    .bind(0, "Ada")
    .bind(1, "ada@example.test")
    .add();

statement
    .bind(0, "Grace")
    .bind(1, "grace@example.test");

Publisher<? extends Result> results = statement.execute();
~~~

Ví dụ dùng marker positional của PostgreSQL. Driver khác có thể dùng marker khác.

Statement.add() khác multi-row VALUES:

- Multi-row: một SQL INSERT chứa nhiều tuple.
- Statement.add(): một SQL statement có nhiều binding set.
- Driver quyết định cách batch được gửi và thực thi.
- Generated values và rowsUpdated có thể khác giữa driver.

Không giả định Statement.add() luôn nhanh hơn multi-row INSERT hoặc luôn chỉ tạo một network round trip. Đo với driver/database thực tế.

Khi tự lấy Connection, quản lý close/transaction đúng cách. Trong Spring-managed transaction, dùng connection được transaction infrastructure quản lý; không tự mở connection riêng rồi kỳ vọng nó tham gia transaction hiện tại.

## 19. Bulk loading khi multi-row INSERT không còn phù hợp

Khi dữ liệu rất lớn, bulk loader thường hiệu quả hơn việc tạo SQL với hàng chục nghìn tuple.

Ví dụ theo database:

- PostgreSQL: COPY.
- MySQL/MariaDB: LOAD DATA hoặc công cụ import phù hợp.
- SQL Server: Bulk Copy API.
- Oracle: SQL*Loader, array binding hoặc cơ chế bulk của driver.
- SQLite: transaction với prepared statement lặp lại hoặc import theo chunk; SQLite không có server bulk protocol giống PostgreSQL.

Bulk loading có thể cần file format, quyền đặc biệt hoặc driver-specific API. Kiểm tra semantics trigger, constraint, default, generated key và transaction. Đây là lựa chọn cho ETL/import lớn, không phải mặc định cho một request HTTP nhỏ.

## 20. Tối ưu khi nguồn dữ liệu nằm trong database

Nếu dữ liệu cần insert được tạo từ một query khác trong cùng database, có thể dùng INSERT ... SELECT thay vì tải rows về ứng dụng rồi gửi lại:

~~~sql
INSERT INTO archived_orders (id, customer_id, status, total)
SELECT id, customer_id, status, total
FROM orders
WHERE created_at < :cutoff;
~~~

Cách này giảm round trip và tránh chuyển dữ liệu qua application heap. Nó vẫn cần transaction, index và kiểm soát số row bị ảnh hưởng.

Với PostgreSQL, có thể dùng CTE/RETURNING khi cần xử lý tiếp. Với database khác, cú pháp và khả năng khác nhau. Giá trị cutoff vẫn bind; tên bảng/cột là cấu trúc cố định.

## 21. Kiểm thử multi-row INSERT trên database thật

Dùng Testcontainers để kiểm tra trên database vendor mục tiêu. Test cần xác nhận:

- SQL syntax của multi-row VALUES.
- Bind parameter được ánh xạ đúng.
- Số row bị ảnh hưởng.
- Generated IDs hoặc RETURNING/OUTPUT.
- Constraint khi một tuple lỗi.
- Chunk size không vượt parameter/packet limit.
- Transaction rollback/commit theo yêu cầu.
- Null và custom type mapping.
- Duplicate/upsert semantics.

Ví dụ integration test với DatabaseClient:

~~~java
@Test
void insertsSeveralRowsInOneStatement() {
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
    .expectNext(2)
    .verifyComplete();
}
~~~

Kiểu rowsUpdated có thể là Integer/Long tùy API version; assertion cần khớp kiểu thực tế của Spring Data R2DBC đang dùng.

Sau insert, đọc lại theo suffix để xác nhận cả hai hàng. Không chỉ kiểm tra rowsUpdated vì trigger hoặc conflict policy có thể ảnh hưởng semantics.

### Test giới hạn

Không cần test hàng triệu row trong mọi build. Có thể có test nhỏ kiểm tra chunking logic và một integration/performance test riêng cho kích thước gần ngưỡng đã chọn.

Khi kiểm tra giới hạn vendor, dùng database version và configuration tương ứng. Đừng suy ra kết quả từ H2 nếu production là SQL Server hoặc SQLite.

## 22. Benchmark và chọn chunk size

Đo các phương án trên cùng schema, index, constraint, driver và transaction semantics:

1. repository.save tuần tự.
2. repository.saveAll.
3. buffer + saveAll.
4. Statement.add().
5. Multi-row INSERT.
6. Bulk loader nếu có.

Thu thập:

- Rows/second.
- Tổng thời gian import.
- p50/p95/p99 latency mỗi chunk.
- CPU và heap phía ứng dụng.
- Database CPU/I/O.
- Connection pool active/pending/acquire duration.
- Transaction duration và lock wait.
- Error/retry count.
- Replication lag nếu có.

Chạy nhiều lần, warm up connection pool và prepared statements, dùng cùng payload. Không so sánh một cách ghi có transaction với một cách không transaction rồi kết luận chỉ dựa trên throughput.

### Tăng chunk size từng bước

Bắt đầu ở mức nhỏ, ví dụ 50 hoặc 100 hàng, rồi thử 200, 500, 1.000 tùy row shape và vendor. Quan sát điểm throughput không còn tăng hoặc latency/error tăng mạnh. Chọn mức thấp hơn điểm giới hạn để có headroom.

Đây là các giá trị thử nghiệm, không phải khuyến nghị cố định cho mọi database.

## 23. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Too many bind parameters | N × C vượt giới hạn driver/database. | Giảm chunk size theo parameter budget. |
| Packet too large | SQL/bind payload vượt max packet/message. | Giảm chunk hoặc dùng bulk loader. |
| SQL statement too long | Tạo một câu VALUES quá lớn. | Chia chunk và đo parse time. |
| SQL syntax error trên Oracle | Dùng cú pháp multi-row VALUES không phù hợp version. | Dùng INSERT ALL/array binding theo vendor. |
| SQL Server báo quá nhiều row constructor | Vượt 1.000 row trong INSERT VALUES. | Chia chunk hoặc dùng cơ chế bulk phù hợp. |
| SQLite variable number exceeded | Vượt SQLITE_MAX_VARIABLE_NUMBER của build. | Giảm số row hoặc kiểm tra compile/runtime limit. |
| Duplicate làm cả chunk lỗi | Một tuple vi phạm UNIQUE. | Validate, chia nhỏ hoặc dùng upsert đúng semantics. |
| Generated ID ghép sai | Giả định ID liên tiếp hoặc thứ tự RETURNING. | Dùng generated values được driver hỗ trợ/correlation key. |
| saveAll không nhanh hơn | Implementation vẫn lưu từng entity. | Dùng multi-row hoặc batch sau khi benchmark. |
| Transaction quá dài | Chunk quá lớn hoặc toàn import trong một transaction. | Commit theo chunk nếu nghiệp vụ cho phép. |
| Memory tăng cao | Tạo SQL và bind toàn bộ dataset. | Stream và buffer có giới hạn. |
| Retry tạo duplicate | Timeout sau commit nhưng trước response. | Idempotency key và unique constraint. |

## 24. Quy trình triển khai multi-row INSERT an toàn

Khi thêm multi-row insert cho một repository/use case:

1. **Xác định database và driver:** ghi rõ vendor, version và R2DBC driver.
2. **Kiểm tra cú pháp:** VALUES nhiều hàng, INSERT ALL, OUTPUT, RETURNING hoặc cơ chế riêng.
3. **Đếm parameter mỗi row:** tính số bind thực tế, kể cả field bổ sung.
4. **Đọc giới hạn vendor:** parameter, row constructor, packet, statement và IN-list riêng biệt.
5. **Chọn chunk size có headroom:** không lấy giới hạn tuyệt đối làm mặc định.
6. **Tạo placeholder động an toàn:** chỉ tạo từ số index, không nối dữ liệu vào SQL.
7. **Bind mọi value:** dùng bindNull cho null và converter cho kiểu đặc biệt.
8. **Quy định generated values:** test RETURNING/OUTPUT hoặc driver generated values.
9. **Chọn transaction scope:** toàn import hay từng chunk; xác định partial success.
10. **Thiết kế duplicate/retry:** unique key, upsert và checkpoint.
11. **Integration test:** dùng Testcontainers đúng database production.
12. **Benchmark:** đo throughput, latency, memory và pool.
13. **Theo dõi production:** statement size, acquire timeout, error và import progress.

Multi-row INSERT giảm số lần execute bằng cách đưa nhiều tuple vào một câu lệnh, nhưng kích thước an toàn phụ thuộc số bind parameter, packet, statement, cú pháp vendor và row shape. PostgreSQL, MySQL/MariaDB, SQL Server, SQLite và Oracle có các giới hạn và cách trả generated values khác nhau; không có một batch size portable cho tất cả. Hãy dùng placeholder và bind value, tính chunk theo giới hạn thấp nhất, kiểm tra transaction/error semantics trên database thật và chỉ chuyển sang bulk loader khi workload đủ lớn để xứng đáng với độ phức tạp bổ sung.

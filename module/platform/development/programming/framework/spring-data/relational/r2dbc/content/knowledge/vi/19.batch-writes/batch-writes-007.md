# Nhận định danh sinh ra và xử lý lỗi của từng nhóm

Khi ghi nhiều bản ghi vào cơ sở dữ liệu bằng Spring Data R2DBC, ứng dụng thường cần nhận lại định danh do database sinh ra và biết nhóm dữ liệu nào đã ghi thành công, nhóm nào thất bại. Đây là hai yêu cầu liên quan nhưng khác nhau: generated ID giúp liên kết bản ghi vừa tạo với dữ liệu đầu vào, còn chiến lược xử lý lỗi xác định phạm vi rollback, cách cô lập bản ghi lỗi và khả năng tiếp tục xử lý các nhóm còn lại.

Không nên giả định mọi cách ghi nhiều bản ghi đều có cùng hành vi. `saveAll` của Repository, một câu SQL insert nhiều dòng, và một `Statement` batch dùng `add()` là những cách thực thi khác nhau. Khả năng trả generated values và cách driver báo lỗi cũng phụ thuộc hệ quản trị, R2DBC driver và phiên bản đang dùng.

Thiết kế tốt cần xác định rõ đơn vị thành công: từng bản ghi, từng batch hay toàn bộ job. Từ đó chọn cách lấy ID, ranh giới transaction, cơ chế retry và cấu trúc kết quả để người gọi biết chính xác điều gì đã xảy ra.

## 1. Ba cách ghi nhiều bản ghi thường gặp

Trong Spring Data R2DBC, có thể ghi nhiều entity theo một số cách:

| Cách ghi | Cơ chế | Đặc điểm cần lưu ý |
|---|---|---|
| `repository.saveAll(...)` | Gửi một publisher hoặc iterable entity qua Repository | API thuận tiện; không nên mặc định luôn tạo một câu SQL batch ở driver |
| Nhiều lần `save`/`insert` | Mỗi entity được lưu bằng một thao tác reactive | Dễ biết entity nào lỗi; có thể tốn nhiều round trip nếu không gom hợp lý |
| Một câu `INSERT ... VALUES (...), (...)` | Một statement chứa nhiều bộ giá trị | Có thể trả nhiều ID bằng `RETURNING` ở database hỗ trợ; lỗi constraint thường làm cả statement thất bại |
| R2DBC SPI `Statement.add()` | Một statement được thực thi với nhiều bộ binding | Là batch ở cấp driver; hỗ trợ generated values và hành vi lỗi phụ thuộc driver |

`saveAll` là API ở mức Repository, không phải cam kết về một lần round trip hay một batch statement. Cách triển khai cụ thể phụ thuộc Spring Data release train. Nếu hiệu năng batch quan trọng, hãy kiểm tra SQL/driver thực tế hoặc dùng cơ chế batch phù hợp với driver.

## 2. Xác định định danh nào cần nhận lại

Trước khi ghi batch, hãy phân biệt các loại định danh:

- **Generated ID:** khóa chính do database cấp, ví dụ identity hoặc sequence.
- **Business key:** mã nghiệp vụ như `order_no`, SKU hoặc mã nhân viên.
- **Correlation key:** khóa dùng để ghép kết quả trả về với đúng phần tử đầu vào của batch.
- **Idempotency key:** khóa giúp nhận diện một yêu cầu ghi đã được xử lý, tránh tạo bản ghi trùng khi retry.

Các khóa này có thể là cùng một cột nếu mô hình nghiệp vụ phù hợp, nhưng thường có mục đích khác nhau. Generated ID có thể không biết trước khi insert. Correlation key phải có sẵn trước khi gửi batch để ứng dụng ghép kết quả một cách đáng tin cậy.

Ví dụ đầu vào:

```java
public record PersonInput(
    String requestKey,
    String name,
    String email
) {}
```

Kết quả sau khi ghi:

```java
public record PersonCreated(
    String requestKey,
    Long id
) {}
```

`requestKey` có thể là UUID do ứng dụng tạo cho từng phần tử. Khi database trả cả `id` và `request_key`, ứng dụng ghép được ID mới với đúng input mà không phải đoán theo thứ tự trả về.

## 3. Vì sao không nên ghép ID theo vị trí trong danh sách?

Một cách làm dễ mắc lỗi là giả định ID được trả về theo đúng thứ tự đầu vào rồi ghép hai danh sách theo index:

```java
// Không nên giả định điều này nếu driver/database không cam kết thứ tự.
for (int i = 0; i < inputs.size(); i++) {
    result.put(inputs.get(i), generatedIds.get(i));
}
```

Thứ tự hàng được database trả về không phải lúc nào cũng được bảo đảm chỉ vì thứ tự insert. Với batch statement, cách driver biểu diễn từng `Result` cũng có thể khác. Một driver có thể trả kết quả theo từng lần thực thi, driver khác có giới hạn về generated values hoặc không hỗ trợ trả key cho batch.

Giải pháp chắc chắn hơn là đưa một correlation key vào dữ liệu ghi và yêu cầu database trả lại khóa đó cùng generated ID. Khi dùng PostgreSQL, có thể dùng `RETURNING`:

```sql
INSERT INTO person (request_key, name, email)
VALUES
    (:key0, :name0, :email0),
    (:key1, :name1, :email1),
    (:key2, :name2, :email2)
RETURNING id, request_key;
```

Sau đó ánh xạ theo `request_key`:

```java
public record PersonCreated(String requestKey, Long id) {}

public Flux<PersonCreated> insertPeople(List<PersonInput> inputs) {
    return databaseClient.sql("""
            INSERT INTO person (request_key, name, email)
            VALUES
                (:key0, :name0, :email0),
                (:key1, :name1, :email1),
                (:key2, :name2, :email2)
            RETURNING id, request_key
            """)
        .bind("key0", inputs.get(0).requestKey())
        .bind("name0", inputs.get(0).name())
        .bind("email0", inputs.get(0).email())
        .bind("key1", inputs.get(1).requestKey())
        .bind("name1", inputs.get(1).name())
        .bind("email1", inputs.get(1).email())
        .bind("key2", inputs.get(2).requestKey())
        .bind("name2", inputs.get(2).name())
        .bind("email2", inputs.get(2).email())
        .map((row, metadata) -> new PersonCreated(
            row.get("request_key", String.class),
            row.get("id", Long.class)
        ))
        .all();
}
```

Ví dụ SQL minh họa batch cố định ba phần tử và dùng cú pháp PostgreSQL `RETURNING`. Khi số phần tử thay đổi, lớp truy cập dữ liệu có thể tạo số bộ placeholder tương ứng từ số lượng phần tử, nhưng tên placeholder phải do code sinh theo chỉ số; mọi giá trị vẫn phải bind. Không ghép trực tiếp dữ liệu người dùng vào SQL.

Nếu không thể lưu correlation key trong bảng, hãy xem xét một staging table hoặc một business key duy nhất có sẵn. Chỉ ghép theo thứ tự khi tài liệu database/driver bảo đảm rõ thứ tự đó và integration test xác nhận hành vi ở phiên bản đang triển khai.

## 4. Nhận ID khi dùng ReactiveCrudRepository.saveAll

Với CRUD thông thường, `ReactiveCrudRepository` có `saveAll` nhận `Iterable` hoặc `Publisher` tùy API. Publisher kết quả phát ra các entity đã được lưu; nếu ID được database sinh và driver hỗ trợ, entity trả về có thể mang ID mới.

```java
@Table("person")
public record Person(
    @Id Long id,
    String requestKey,
    String name,
    String email
) {}

public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {
}
```

```java
public Flux<PersonCreated> createAll(List<PersonInput> inputs) {
    List<Person> entities = inputs.stream()
        .map(input -> new Person(
            null,
            input.requestKey(),
            input.name(),
            input.email()
        ))
        .toList();

    return personRepository.saveAll(entities)
        .map(saved -> new PersonCreated(saved.requestKey(), saved.id()));
}
```

Ở cách này, mỗi entity được trả về mang cả correlation key và ID. Không cần tự lấy `MAX(id)` hoặc tính ID tiếp theo. Tuy nhiên, hãy kiểm tra cách `saveAll` được thực hiện trong phiên bản Spring Data đang dùng; API này không bảo đảm một SQL multi-row insert hoặc một driver batch duy nhất.

Nếu cần bắt lỗi riêng từng phần tử, `saveAll` như một publisher có thể phát lỗi và kết thúc chuỗi khi một thao tác thất bại. Đừng giả định publisher tự bỏ qua hàng lỗi rồi tiếp tục. Hãy chọn ranh giới transaction và cách xử lý lỗi phù hợp với yêu cầu từng bản ghi hay từng nhóm.

## 5. Ghi từng entity và giữ kết quả thành công/thất bại

Nếu cần cô lập lỗi ở cấp bản ghi, có thể xử lý từng entity bằng `concatMap` và chuyển kết quả thành một kiểu outcome:

```java
public sealed interface RowOutcome {
    record Success(String requestKey, Long generatedId) implements RowOutcome {}
    record Failure(String requestKey, String errorCode) implements RowOutcome {}
}
```

```java
public Flux<RowOutcome> createIndividually(List<PersonInput> inputs) {
    return Flux.fromIterable(inputs)
        .concatMap(input -> {
            Person person = new Person(
                null,
                input.requestKey(),
                input.name(),
                input.email()
            );

            return personRepository.save(person)
                .map(saved -> (RowOutcome) new RowOutcome.Success(
                    input.requestKey(), saved.id()))
                .onErrorResume(error -> Mono.just(
                    new RowOutcome.Failure(
                        input.requestKey(),
                        classify(error)
                    )
                ));
        });
}
```

`concatMap` xử lý lần lượt từng phần tử, giúp giới hạn concurrency và giữ thứ tự phát outcome theo input. Cách này dễ xác định phần tử nào thành công hoặc lỗi, nhưng thường tạo nhiều thao tác database hơn một batch thực sự.

Nếu cần mỗi phần tử có transaction riêng, hãy bọc thao tác của từng phần tử bằng `TransactionalOperator` rồi mới bắt lỗi ở bên ngoài transaction đó. Khi một insert lỗi, transaction của phần tử đó được rollback trước khi chuỗi tiếp tục phần tử tiếp theo.

```java
public Flux<RowOutcome> createIndividually(List<PersonInput> inputs) {
    return Flux.fromIterable(inputs)
        .concatMap(input -> {
            Mono<Person> insert = personRepository.save(new Person(
                null,
                input.requestKey(),
                input.name(),
                input.email()
            ));

            return transactionalOperator.transactional(insert)
                .map(saved -> (RowOutcome) new RowOutcome.Success(
                    input.requestKey(), saved.id()))
                .onErrorResume(error -> Mono.just(
                    new RowOutcome.Failure(input.requestKey(), classify(error))
                ));
        });
}
```

Không đặt `onErrorResume` bên trong một transaction chung rồi kỳ vọng database tiếp tục sau lỗi constraint. Một số database, như PostgreSQL, đánh dấu transaction ở trạng thái lỗi sau statement thất bại; các statement tiếp theo sẽ không chạy thành công cho tới khi rollback. Bắt lỗi bên ngoài ranh giới transaction giúp rollback hoàn tất trước khi xử lý phần tử kế tiếp.

## 6. Chia dữ liệu thành batch có kích thước giới hạn

Không nên đưa một danh sách không giới hạn vào một statement hoặc một transaction. Chia input thành các nhóm nhỏ giúp kiểm soát:

- Số bind parameter và giới hạn của database/driver.
- Kích thước gói dữ liệu truyền qua mạng.
- Bộ nhớ dùng để giữ input và kết quả generated ID.
- Thời gian giữ connection và lock.
- Phạm vi rollback khi một nhóm thất bại.

Ví dụ chia thành nhóm 200 phần tử:

```java
Flux<List<PersonInput>> batches = Flux.fromIterable(inputs)
    .buffer(200);
```

Kích thước 200 chỉ là ví dụ. Giá trị phù hợp phụ thuộc số cột mỗi hàng, giới hạn parameter, latency, tải database và driver. Hãy đo với dữ liệu gần thực tế.

Để xử lý tuần tự từng batch:

```java
return Flux.fromIterable(inputs)
    .buffer(200)
    .concatMap(batch -> insertBatch(batch));
```

`concatMap` chỉ bắt đầu batch tiếp theo sau khi batch hiện tại hoàn tất. Nếu database đủ khả năng và nghiệp vụ cho phép, có thể dùng `flatMap` với concurrency giới hạn, nhưng cần tính đến số connection, lock và thứ tự kết quả.

## 7. Nhận generated values với R2DBC SPI Statement.add

R2DBC SPI cho phép tạo một `Statement`, bind nhiều bộ giá trị và gọi `add()` để thêm các bộ binding vào batch. `Statement.returnGeneratedValues(...)` có thể yêu cầu driver trả các giá trị do database sinh ra.

Ví dụ khung thao tác trực tiếp với SPI:

```java
public Mono<List<Long>> insertBatchIds(List<PersonInput> batch) {
    if (batch.isEmpty()) {
        return Mono.just(List.of());
    }

    return Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> {
            Statement statement = connection.createStatement("""
                INSERT INTO person (request_key, name, email)
                VALUES ($1, $2, $3)
                """);

            statement.returnGeneratedValues("id");

            for (int i = 0; i < batch.size(); i++) {
                PersonInput item = batch.get(i);
                statement.bind(0, item.requestKey())
                    .bind(1, item.name())
                    .bind(2, item.email());

                if (i < batch.size() - 1) {
                    statement.add();
                }
            }

            return Flux.from(statement.execute())
                .concatMap(result -> Flux.from(
                    result.map((row, metadata) -> row.get("id", Long.class))
                ))
                .collectList();
        },
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
```

Ví dụ minh họa cấu trúc batch ở cấp SPI: mỗi bộ binding được thêm bằng `add()` trước khi bind bộ tiếp theo; bộ cuối cùng vẫn là bộ binding hiện tại khi gọi `execute()`. Chỉ số bind trong SPI bắt đầu từ 0. Đoạn code yêu cầu driver trả cột `id`, vì vậy kết quả chỉ là danh sách ID.

**Quan trọng:** hỗ trợ generated values cho batch, số `Result` phát ra, cách nhóm hàng trả về và khả năng ánh xạ từng ID về đúng input phụ thuộc driver/database. Không được mặc định đoạn code này chạy giống nhau trên mọi R2DBC driver. Hãy kiểm tra tài liệu của driver và integration test trên phiên bản cụ thể. Nếu cần ghép ID với input một cách portable hơn, dùng một correlation key được trả về cùng ID qua câu SQL `RETURNING`/`OUTPUT` mà database hỗ trợ.

Ví dụ trên tạo connection trực tiếp từ `ConnectionFactory` và đóng connection sau thao tác. Nếu cần tham gia reactive transaction do Spring quản lý, không tự lấy một connection độc lập như vậy rồi giả định nó tự tham gia transaction context. Hãy dùng cơ chế lấy connection được Spring quản lý hoặc thiết kế transaction trực tiếp trên connection theo đúng SPI; với thao tác thông thường, `DatabaseClient` và `TransactionalOperator` thường dễ tích hợp hơn.

## 8. Một câu multi-row INSERT có RETURNING

Một lựa chọn khác là tạo một câu insert có nhiều bộ giá trị. Với PostgreSQL:

```sql
INSERT INTO person (request_key, name, email)
VALUES
    ('req-a', 'An', 'an@example.test'),
    ('req-b', 'Binh', 'binh@example.test')
RETURNING id, request_key;
```

Trong ứng dụng, giá trị phải được bind thay vì viết literal từ input:

```java
public Flux<PersonCreated> insertTwo(
        PersonInput first,
        PersonInput second) {

    return databaseClient.sql("""
            INSERT INTO person (request_key, name, email)
            VALUES (:key0, :name0, :email0),
                   (:key1, :name1, :email1)
            RETURNING id, request_key
            """)
        .bind("key0", first.requestKey())
        .bind("name0", first.name())
        .bind("email0", first.email())
        .bind("key1", second.requestKey())
        .bind("name1", second.name())
        .bind("email1", second.email())
        .map((row, metadata) -> new PersonCreated(
            row.get("request_key", String.class),
            row.get("id", Long.class)
        ))
        .all();
}
```

Kết quả được ghép bằng `request_key`, không dựa vào thứ tự trả về. Đây là một câu SQL duy nhất nên trên PostgreSQL, lỗi constraint ở một hàng thường làm cả statement thất bại; không có danh sách một phần các hàng insert thành công từ cùng statement đó.

Đối với database khác, cú pháp lấy lại ID có thể là `OUTPUT`, `RETURNING` hoặc cơ chế khác. Cần tách SQL theo dialect hoặc dùng generated values của SPI khi driver hỗ trợ.

## 9. Phân biệt lỗi ở cấp bản ghi, batch và job

Trước khi xử lý lỗi, hãy xác định phạm vi mà hệ thống xem là đơn vị thành công:

| Phạm vi | Ý nghĩa | Hành vi khi một phần tử lỗi |
|---|---|---|
| Từng bản ghi | Mỗi input độc lập | Chỉ rollback bản ghi đó, tiếp tục bản ghi khác nếu transaction tách riêng |
| Từng batch | Các input trong một nhóm là một đơn vị | Rollback toàn bộ batch nếu một thao tác trong nhóm lỗi |
| Toàn bộ job | Tất cả batch phải thành công cùng nhau | Một lỗi có thể rollback toàn bộ công việc nếu mọi thao tác nằm trong một transaction |

Không có lựa chọn đúng cho mọi tình huống. Import dữ liệu độc lập thường cần ghi nhận lỗi từng bản ghi hoặc từng batch để tiếp tục. Chuyển tiền hoặc ghi một aggregate có thể yêu cầu all-or-nothing. Một job migration có thể cần transaction lớn hoặc checkpoint theo từng phân đoạn tùy quy mô.

## 10. Phân loại lỗi trước khi quyết định retry

Không phải lỗi nào cũng nên retry. Có thể chia thành các nhóm:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, sai định dạng, giá trị ngoài miền | Kiểm tra trước khi gửi database; đánh dấu input lỗi |
| Vi phạm constraint | Unique, foreign key, NOT NULL, CHECK | Không retry nguyên trạng; sửa dữ liệu hoặc ghi nhận conflict |
| Lỗi tạm thời | Deadlock, serialization failure, lỗi kết nối ngắn hạn | Có thể retry có giới hạn nếu thao tác an toàn và transaction đã rollback |
| Quá tải hoặc timeout | Pool hết connection, database quá tải, query timeout | Backoff, giới hạn concurrency và quan sát tải trước khi retry |
| Lỗi cấu hình/lập trình | Sai SQL, thiếu cột, bind sai kiểu, thiếu quyền | Sửa code/cấu hình; retry thường không có ích |
| Kết quả không xác định | Mất kết nối sau khi server có thể đã commit | Tra cứu bằng idempotency key trước khi gửi lại |

Với R2DBC, lỗi có thể xuất hiện dưới dạng exception từ driver hoặc exception đã được Spring dịch. Tùy driver, có thể đọc SQL state hoặc mã lỗi để phân loại. Không nên phụ thuộc duy nhất vào chuỗi thông báo lỗi vì nội dung có thể thay đổi theo driver và phiên bản.

Một số SQLSTATE thường gặp trong PostgreSQL:

| SQLSTATE | Ý nghĩa |
|---|---|
| `23505` | Unique violation |
| `23503` | Foreign key violation |
| `23502` | Not-null violation |
| `23514` | Check constraint violation |
| `40001` | Serialization failure |
| `40P01` | Deadlock detected |

Các mã này là ví dụ PostgreSQL; hệ quản trị khác có mã và cách phân loại riêng. Trong Spring, lỗi constraint thường có thể được chuyển thành nhóm `DataIntegrityViolationException`, còn lỗi tạm thời có thể thuộc nhóm `TransientDataAccessException`, nhưng cần kiểm tra exception cụ thể mà driver và translator tạo ra.

## 11. Transaction theo từng batch

Một chiến lược phổ biến là mỗi batch có một transaction riêng. Nếu batch thất bại, rollback batch đó; các batch trước đã commit và các batch sau vẫn có thể được xử lý.

```java
public record BatchOutcome(
    long batchNumber,
    int attempted,
    List<PersonCreated> inserted,
    String errorCode
) {}
```

```java
public Flux<BatchOutcome> importInBatches(
        Flux<PersonInput> source,
        int batchSize) {

    return source
        .buffer(batchSize)
        .index()
        .concatMap(indexed -> {
            long batchNumber = indexed.getT1();
            List<PersonInput> batch = indexed.getT2();

            return transactionalOperator.transactional(
                    insertBatch(batch)
                )
                .map(inserted -> new BatchOutcome(
                    batchNumber,
                    batch.size(),
                    inserted,
                    null
                ))
                .onErrorResume(error -> Mono.just(new BatchOutcome(
                    batchNumber,
                    batch.size(),
                    List.of(),
                    classify(error)
                )));
        });
}
```

`insertBatch(batch)` đại diện cho thao tác batch trả về danh sách kết quả có ID. `TransactionalOperator` bao publisher của batch; `onErrorResume` nằm sau ranh giới transaction để lỗi được truyền qua transaction manager và kích hoạt rollback trước khi biến thành `BatchOutcome` thất bại.

Khi `onErrorResume` bắt lỗi sau transaction, batch hiện tại được ghi nhận thất bại và `concatMap` có thể tiếp tục batch kế tiếp. Cách này tạo kết quả một phần giữa các batch: batch trước có thể đã commit, batch lỗi rollback, batch sau tiếp tục. Đây là hành vi cần được chấp nhận rõ trong hợp đồng import.

Không đặt `onErrorResume` bên trong `transactionalOperator.transactional(...)` nếu mục đích là rollback toàn bộ batch khi có lỗi. Nếu lỗi bị nuốt trước khi transaction manager nhìn thấy, transaction có thể được commit trong trạng thái không như mong muốn hoặc database đã ở trạng thái failed.

## 12. Transaction theo từng bản ghi

Nếu yêu cầu là bản ghi hợp lệ vẫn được ghi dù bản ghi khác trong cùng input list lỗi, mỗi bản ghi có thể có transaction riêng:

```java
public Flux<RowOutcome> importRowsIndependently(
        Flux<PersonInput> source) {

    return source.concatMap(input -> {
        Mono<Person> write = personRepository.save(new Person(
            null,
            input.requestKey(),
            input.name(),
            input.email()
        ));

        return transactionalOperator.transactional(write)
            .map(saved -> (RowOutcome) new RowOutcome.Success(
                input.requestKey(), saved.id()))
            .onErrorResume(error -> Mono.just(
                new RowOutcome.Failure(input.requestKey(), classify(error))
            ));
    });
}
```

Ưu điểm là xác định chính xác phần tử nào thất bại và phần tử nào thành công. Nhược điểm là nhiều transaction và nhiều round trip hơn. Nếu dữ liệu lớn, có thể xử lý theo batch nhỏ hoặc dùng cơ chế staging để cân bằng hiệu năng và khả năng cô lập lỗi.

## 13. Vì sao không nên dùng onErrorContinue để bỏ qua lỗi batch?

`onErrorContinue` có thể trông hấp dẫn vì muốn bỏ qua một phần tử lỗi và tiếp tục luồng. Tuy nhiên, với thao tác database, nó không tự bảo đảm:

- Statement lỗi đã được rollback.
- Transaction vẫn ở trạng thái có thể tiếp tục.
- Driver đã giải phóng hoặc reset trạng thái connection.
- Các phần tử trước trong cùng batch đã commit độc lập.
- Generated IDs được ghép đúng với input còn lại.

Một lỗi constraint trong transaction PostgreSQL có thể khiến toàn bộ transaction chuyển sang trạng thái aborted. Tiếp tục gửi statement khác trên cùng transaction sẽ thất bại cho đến khi rollback. Vì vậy, hãy dùng transaction theo batch hoặc theo record, để lỗi đi ra khỏi ranh giới transaction, rollback hoàn tất rồi mới tiếp tục.

`onErrorResume` cũng không tự tạo transaction boundary. Vị trí đặt operator rất quan trọng: bắt lỗi sau transaction để bảo đảm transaction manager nhìn thấy lỗi và rollback trước.

## 14. Cô lập bản ghi lỗi trong một batch thất bại

Nếu một batch gồm 500 bản ghi và một bản ghi vi phạm unique constraint, batch transaction có thể rollback cả 500. Để tìm phần tử lỗi, có một số chiến lược:

**Kiểm tra trước khi ghi:** xác thực định dạng, trường bắt buộc và các quy tắc có thể kiểm tra ở ứng dụng. Đây không thay thế constraint ở database vì dữ liệu có thể thay đổi đồng thời.

**Chia đôi batch (bisection):** sau khi một batch thất bại do lỗi dữ liệu, chia nhóm thành hai nửa và thử lại từng nửa trong transaction độc lập. Tiếp tục chia cho tới khi tìm được phần tử hoặc nhóm nhỏ gây lỗi. Cách này giảm số lần thử so với ghi từng bản ghi ngay từ đầu, nhưng chỉ phù hợp khi thao tác retry an toàn và lỗi có tính xác định.

**Fallback từng bản ghi:** nếu batch thất bại, rollback rồi thử từng input trong transaction riêng để xác định chính xác lỗi. Cách này đơn giản nhưng có thể chậm khi batch lớn.

**Savepoint:** trong một transaction, có thể tạo savepoint trước nhóm nhỏ rồi rollback về savepoint khi nhóm lỗi, nếu database và driver hỗ trợ. Hỗ trợ savepoint và trạng thái connection phải được kiểm tra theo driver. Không nên giả định mọi R2DBC driver hỗ trợ giống nhau.

Không dùng bisection hoặc fallback retry cho lỗi kết nối diện rộng, deadlock liên tục hay lỗi cấu hình. Khi lỗi là hệ thống, chia batch nhỏ hơn có thể làm tăng tải mà không giải quyết nguyên nhân.

## 15. Retry an toàn và idempotency key

Một lỗi timeout hoặc mất kết nối có thể xảy ra sau khi database đã thực hiện insert nhưng trước khi ứng dụng nhận được phản hồi. Lúc này ứng dụng không biết chắc dữ liệu đã commit hay chưa. Gửi lại cùng input có thể tạo bản ghi trùng nếu không có cơ chế idempotency.

Một cách phổ biến là lưu `request_key` duy nhất:

```sql
CREATE TABLE person (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    request_key UUID NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL
);
```

Khi retry, ứng dụng có thể tra cứu theo `request_key` trước hoặc dùng upsert phù hợp với database. Với PostgreSQL:

```sql
INSERT INTO person (request_key, name, email)
VALUES (:requestKey, :name, :email)
ON CONFLICT (request_key)
DO UPDATE SET name = EXCLUDED.name,
              email = EXCLUDED.email
RETURNING id, request_key;
```

Ví dụ này dùng `ON CONFLICT` của PostgreSQL. Nếu request key đã tồn tại, câu lệnh cập nhật hàng hiện tại rồi trả lại ID; tùy nghiệp vụ, có thể chọn `DO NOTHING` và truy vấn lại. Hãy quyết định rõ liệu retry cùng key nhưng payload khác có được phép cập nhật hay phải báo conflict.

Chỉ retry lỗi được xác định là tạm thời, có giới hạn số lần, exponential backoff và jitter. Không retry lỗi dữ liệu như unique violation nếu input không thay đổi. Với deadlock hoặc serialization failure, có thể retry toàn bộ transaction nếu nghiệp vụ và thao tác có tính idempotent.

## 16. Sequence và identity có thể tạo khoảng trống ID

Không nên giả định ID sinh ra liên tục hoặc rollback sẽ trả lại số đã cấp. Nhiều database dùng sequence/identity có thể tiêu thụ giá trị ngay cả khi transaction rollback. Vì vậy, sau batch lỗi có thể xuất hiện khoảng trống trong dãy ID.

Ví dụ, một batch lấy các ID 101, 102, 103 nhưng transaction rollback; batch tiếp theo có thể nhận 104, 105. Điều này bình thường và không biểu thị dữ liệu bị thiếu hoặc lỗi.

Không dùng `MAX(id) + 1`, không tự suy ra ID của từng input từ ID đầu tiên và không dùng khoảng cách giữa hai ID làm số bản ghi thành công. Hãy đọc ID database trả về và ghép bằng correlation key.

## 17. Chọn một statement nhiều dòng hay driver batch?

Hai cách này khác nhau về phạm vi lỗi và khả năng trả kết quả:

| Tiêu chí | Multi-row INSERT | R2DBC SPI Statement batch |
|---|---|---|
| Số statement SQL | Một câu chứa nhiều bộ VALUES | Một statement với nhiều bộ binding qua `add()` |
| Generated IDs | Database như PostgreSQL có thể trả nhiều hàng bằng `RETURNING` | `returnGeneratedValues` phụ thuộc hỗ trợ của driver và cách kết quả được phát |
| Ghép ID với input | Dễ nếu `RETURNING` cả correlation key | Cần kiểm tra driver; không giả định thứ tự hoặc một Result cho mỗi input |
| Lỗi constraint | Thường cả câu lệnh thất bại như một đơn vị | Hành vi khi một phần tử lỗi phụ thuộc driver và transaction |
| Kích thước SQL | Câu SQL và số bind tăng theo số hàng | SQL cố định, nhiều bộ binding ở SPI |
| Tính portable | Cú pháp multi-row phổ biến nhưng `RETURNING` khác theo database | API batch chung hơn, nhưng generated keys vẫn phụ thuộc driver |

Chọn theo khả năng của database/driver, kích thước batch và yêu cầu kết quả. Nếu cần mapping ID chính xác và database hỗ trợ `RETURNING`, multi-row insert có correlation key thường dễ hiểu. Nếu cần dùng batch SPI để giảm overhead, phải kiểm tra kỹ hành vi generated values và lỗi của driver.

## 18. Xử lý kết quả batch thành công và thất bại

Không nên chỉ trả một số tổng số hàng thành công nếu hệ thống cần điều tra và retry. Một kết quả import nên thể hiện:

- Batch number hoặc import job ID.
- Số phần tử được thử.
- Số phần tử thành công.
- Danh sách correlation key và generated ID thành công.
- Danh sách correlation key thất bại cùng mã lỗi có thể xử lý.
- Batch có được retry hay không và số lần retry.
- Thời gian bắt đầu/kết thúc và thời lượng.

Ví dụ mô hình kết quả:

```java
public record ImportReport(
    String jobId,
    int attempted,
    int succeeded,
    int failed,
    List<PersonCreated> created,
    List<RowFailure> failures
) {}

public record RowFailure(
    String requestKey,
    String errorCode,
    boolean retryable
) {}
```

Không đưa toàn bộ payload nhạy cảm hoặc thông tin kết nối vào error report. Dùng correlation key để tra log và dữ liệu nguồn. Nếu số lỗi lớn, lưu chi tiết vào bảng lỗi hoặc file kết quả thay vì giữ toàn bộ danh sách trong bộ nhớ.

## 19. Giới hạn concurrency khi xử lý nhiều batch

`concatMap` xử lý tuần tự, dễ dự đoán và hữu ích khi cần giữ thứ tự. `flatMap` có thể chạy nhiều batch đồng thời, nhưng cần giới hạn concurrency:

```java
Flux.fromIterable(inputs)
    .buffer(200)
    .flatMap(this::insertBatch, 4);
```

Giá trị concurrency 4 chỉ là ví dụ. Tăng concurrency có thể cải thiện throughput khi database còn tài nguyên, nhưng cũng tăng số connection đang dùng, lock contention, bộ nhớ và nguy cơ deadlock. Nếu mỗi batch mở transaction riêng, mỗi transaction có thể cần một connection.

Đừng dùng `parallel()` hoặc `flatMap` không giới hạn cho thao tác ghi database chỉ vì API reactive. Hãy đo pool utilization, acquire latency, query latency và lỗi trước khi tăng concurrency.

## 20. Ghi checkpoint để tiếp tục import sau sự cố

Với job import lớn, có thể lưu trạng thái từng batch:

| Trường | Ý nghĩa |
|---|---|
| `job_id` | Định danh lần import |
| `batch_no` | Số thứ tự nhóm |
| `status` | `PENDING`, `PROCESSING`, `SUCCEEDED`, `FAILED` |
| `attempted_count` | Số phần tử trong batch |
| `success_count` | Số phần tử thành công |
| `failure_count` | Số phần tử lỗi |
| `started_at`, `completed_at` | Thời điểm xử lý |
| `error_code` | Nhóm lỗi nếu thất bại |

Checkpoint giúp tiến trình có thể tiếp tục từ batch chưa hoàn tất thay vì gửi lại toàn bộ dữ liệu. Tuy nhiên, cập nhật checkpoint và ghi dữ liệu cần có chiến lược nhất quán. Có thể ghi trạng thái `PROCESSING` trước, rồi commit dữ liệu cùng trạng thái `SUCCEEDED` trong cùng transaction nếu checkpoint nằm cùng database. Nếu job chết sau khi commit dữ liệu nhưng trước khi đánh dấu hoàn tất, idempotency key giúp lần chạy lại nhận diện bản ghi đã tồn tại.

Với dữ liệu rất lớn, tránh giữ toàn bộ generated ID trong bộ nhớ. Có thể ghi mapping `request_key -> generated_id` vào bảng kết quả import theo batch.

## 21. Kiểm thử generated ID và lỗi theo batch

Integration test nên bao gồm cả trường hợp thành công và lỗi:

1. Ghi một batch hợp lệ và xác nhận mỗi input có generated ID.
2. Xác nhận ID được ghép với đúng `requestKey`, không dựa vào thứ tự ngẫu nhiên.
3. Ghi batch có một phần tử vi phạm unique constraint và xác nhận phạm vi rollback đúng thiết kế.
4. Kiểm tra batch sau có tiếp tục hay không khi batch trước thất bại.
5. Kiểm tra `saveAll` trong phiên bản Spring Data đang dùng có hành vi lỗi và thứ tự phát kết quả như tài liệu.
6. Kiểm tra driver hỗ trợ `Statement.add()` và `returnGeneratedValues` cho kiểu batch cụ thể.
7. Kiểm tra multi-row `RETURNING`/`OUTPUT` trên database đích.
8. Kiểm tra ID có thể có khoảng trống sau rollback và ứng dụng không dựa vào ID liên tiếp.
9. Mô phỏng lỗi kết nối sau khi server có thể đã commit; xác nhận retry bằng idempotency key không tạo dữ liệu trùng.
10. Kiểm tra concurrency, transaction timeout, rollback và giải phóng connection.

Testcontainers hoặc database test cùng loại production là lựa chọn phù hợp. H2 có thể khác PostgreSQL, SQL Server hoặc Oracle về generated values, batch execution, transaction error state và cú pháp trả kết quả.

## 22. Quy trình triển khai ghi nhiều bản ghi

Một quy trình có thể áp dụng cho import hoặc bulk create:

**Bước 1 — Chuẩn hóa input.** Kiểm tra dữ liệu, tạo correlation key và idempotency key nếu cần retry.

**Bước 2 — Chọn cách ghi.** Dùng `saveAll` cho CRUD thuận tiện, multi-row insert khi database hỗ trợ trả kết quả phù hợp, hoặc `Statement.add()` khi cần batch ở cấp SPI.

**Bước 3 — Chọn cách nhận ID.** Dùng entity trả về từ Repository, `RETURNING`/`OUTPUT`, hoặc `Statement.returnGeneratedValues`; luôn kiểm tra hỗ trợ của driver.

**Bước 4 — Ghép kết quả.** Ưu tiên correlation key được trả về cùng generated ID. Không suy ra ID bằng `MAX(id)` hoặc giả định ID liên tiếp.

**Bước 5 — Chia nhóm.** Chọn batch size theo giới hạn parameter, payload, latency và thời gian transaction.

**Bước 6 — Định nghĩa đơn vị rollback.** Chọn transaction theo record, batch hay toàn job dựa trên yêu cầu nghiệp vụ.

**Bước 7 — Phân loại lỗi.** Tách lỗi dữ liệu, constraint, lỗi tạm thời, timeout và lỗi cấu hình; chỉ retry loại phù hợp.

**Bước 8 — Ghi kết quả từng nhóm.** Lưu số lượng, generated IDs, correlation keys, lỗi và checkpoint cần thiết.

**Bước 9 — Kiểm thử trên database thật.** Xác nhận hành vi generated values, batch error, rollback và idempotency với đúng driver.

## 23. Kết luận

Ghi nhiều bản ghi trong Spring Data R2DBC cần một chiến lược rõ ràng cho cả generated ID và lỗi. `saveAll` thuận tiện cho CRUD nhưng không bảo đảm một SQL batch; multi-row insert có thể trả nhiều ID qua `RETURNING`/`OUTPUT`; R2DBC SPI `Statement.add()` cung cấp batch binding nhưng generated values và hành vi lỗi phụ thuộc driver.

Để ghép ID chính xác, hãy trả về correlation key cùng generated ID thay vì dựa vào thứ tự hoặc tính liên tiếp của sequence. Để xử lý lỗi, xác định đơn vị rollback là record, batch hay job; bắt lỗi sau ranh giới transaction; chỉ retry lỗi tạm thời với thao tác idempotent; và ghi outcome cho từng nhóm. Integration test trên đúng database/driver là cách xác nhận các giả định về batch, generated values và transaction trước khi vận hành.

# Phân biệt `saveAll` với thao tác SQL theo lô

Spring Data Relational R2DBC cung cấp `saveAll(...)` để lưu nhiều entity thông qua repository. Ở tầng thấp hơn, R2DBC SPI và database cũng hỗ trợ các cách thực thi nhiều lần ghi như batch statement, câu lệnh `INSERT` nhiều hàng hoặc lệnh bulk update. Những cách này đều có thể xử lý nhiều bản ghi, nhưng không có cùng ngữ nghĩa và không bảo đảm cùng một mức tối ưu.

Điểm cần phân biệt là **lưu nhiều entity qua vòng đời ánh xạ** và **gửi một thao tác SQL theo lô tới database**. `saveAll` làm việc với entity: Spring Data xác định trạng thái mới/cũ, ánh xạ property, áp dụng conversion và các callback phù hợp, rồi thực hiện insert/update cho từng entity. Một batch SQL làm việc ở tầng statement/driver: ứng dụng chuẩn bị câu SQL và nhiều bộ tham số để driver thực thi theo cơ chế batch được hỗ trợ.

Vì vậy, gọi `saveAll` không đồng nghĩa với việc framework luôn tạo một câu `INSERT` duy nhất hoặc một batch network round-trip. Nếu mục tiêu là lưu entity với lifecycle của Spring Data, `saveAll` thường phù hợp. Nếu mục tiêu là throughput cao cho dữ liệu đồng nhất và có thể kiểm soát SQL, batch statement hoặc multi-row SQL có thể hiệu quả hơn, nhưng ứng dụng phải tự chịu trách nhiệm cho các quy tắc mapping, auditing, version và generated values mà đường entity-oriented thường xử lý.

## 1. Ba khái niệm thường bị gọi chung là “batch”

Trong ứng dụng R2DBC, từ “batch” có thể chỉ ít nhất ba cách làm khác nhau:

| Cách làm | Cơ chế | Đơn vị thao tác |
| --- | --- | --- |
| `repository.saveAll(...)` | Spring Data lưu từng entity qua repository persistence path | Một entity cho mỗi lần xử lý save; không mặc định là SQL batch |
| `Statement.add()` | R2DBC SPI gom nhiều bộ giá trị bind cho cùng một SQL statement | Một câu SQL với nhiều bộ tham số |
| Multi-row SQL | Một câu SQL chứa nhiều nhóm `VALUES` hoặc một lệnh bulk | Một câu SQL tác động nhiều hàng |

Ngoài ra, R2DBC SPI có `Batch` được tạo từ `Connection.createBatch()` để thực thi nhiều câu SQL. API này khác với `Statement.add()`: `Statement.add()` dành cho nhiều bộ tham số của cùng một statement, còn `Batch` gom các câu SQL. Khả năng hỗ trợ và giới hạn phụ thuộc driver.

Ví dụ minh họa:

```java
// Repository: lưu nhiều entity qua Spring Data.
Flux<Customer> saved = customerRepository.saveAll(customers);
```

```java
// R2DBC SPI: cùng một INSERT, nhiều bộ bind.
Statement statement = connection.createStatement(
        "INSERT INTO customer (id, name) VALUES ($1, $2)"
);
statement.bind(0, 1L).bind(1, "Lan").add();
statement.bind(0, 2L).bind(1, "Minh");
Publisher<? extends Result> result = statement.execute();
```

```sql
-- Một câu lệnh INSERT chứa nhiều hàng.
INSERT INTO customer (id, name)
VALUES (1, 'Lan'), (2, 'Minh'), (3, 'An');
```

Ba ví dụ đều có thể tạo ra ba hàng, nhưng đường thực thi, callback, cách bind, kết quả trả về và mức hỗ trợ của driver khác nhau.

## 2. `saveAll` làm gì?

Reactive repository cung cấp các overload phổ biến:

```java
Flux<S> saveAll(Iterable<S> entities);

Flux<S> saveAll(Publisher<S> entityStream);
```

API cụ thể phụ thuộc interface và phiên bản Spring Data, nhưng ý nghĩa chung là nhận nhiều entity và phát ra các entity sau khi lưu. `saveAll` là API ở tầng repository, không phải một cam kết rằng database sẽ nhận một câu SQL batch duy nhất.

Trong triển khai repository R2DBC thông dụng, các entity được đưa qua logic `save` tương ứng, thường theo thứ tự tuần tự bằng toán tử như `concatMap`. Mỗi entity có thể được phân loại là mới hay đã tồn tại rồi đi qua thao tác insert hoặc update riêng. Chi tiết nội bộ có thể thay đổi theo phiên bản Spring Data; khi cần dựa vào batching để đạt hiệu năng, hãy kiểm tra implementation/version đang dùng và đo với driver thật.

Ví dụ:

```java
public Flux<Customer> createCustomers(List<Customer> customers) {
    return customerRepository.saveAll(customers);
}
```

Publisher trả về phát các entity sau khi từng thao tác save hoàn tất. Vì publisher reactive thường lazy, việc gọi `saveAll` mới tạo pipeline; database bắt đầu xử lý khi publisher được subscribe bởi controller WebFlux, `StepVerifier` hoặc tầng tiêu thụ khác.

### `saveAll` vẫn áp dụng newness detection

Mỗi entity được lưu theo trạng thái persistence của nó. Tùy entity:

- Nếu entity mới, Spring Data thực hiện insert.
- Nếu entity đã tồn tại, Spring Data thực hiện update.
- Nếu entity triển khai `Persistable`, `isNew()` có thể quyết định trạng thái.
- Nếu entity có `@Version`, version tham gia nhận diện trạng thái và optimistic locking.
- Nếu không có `Persistable` hoặc `@Version`, identifier `@Id` thường được dùng để xác định entity mới/cũ.

Do đó, một `saveAll` có thể chứa cả entity mới và entity cũ. Nó không nhất thiết tương ứng với một batch insert đồng nhất.

### Entity lifecycle, conversion và callback

Vì `saveAll` đi qua persistence path của entity, các thao tác save có thể sử dụng:

- Mapping metadata để xác định table, column và identifier.
- `R2dbcCustomConversions` để chuyển kiểu domain sang kiểu driver/store.
- Entity lifecycle callbacks phù hợp như callback trước khi convert/lưu và sau khi lưu.
- Auditing như `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy` nếu được cấu hình.
- Optimistic locking thông qua `@Version`.
- Generated ID hoặc giá trị do database trả về, theo khả năng driver và thao tác.

Điều này giúp `saveAll` thuận tiện khi mỗi entity cần đi qua cùng quy tắc persistence của ứng dụng. Tuy nhiên, nó cũng có thể tạo nhiều lần xử lý mapping và nhiều câu lệnh database hơn một bulk SQL.

## 3. Ví dụ `saveAll` với entity mới

Giả sử bảng `customer` dùng ID tự sinh:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    status VARCHAR(30) NOT NULL
);
```

Entity:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    private String status;

    public Customer(String name, String status) {
        this.name = name;
        this.status = status;
    }

    // Constructor/getter cần thiết cho mapping và ứng dụng.
}
```

Repository:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
```

Lưu nhiều entity:

```java
List<Customer> customers = List.of(
        new Customer("Lan", "ACTIVE"),
        new Customer("Minh", "ACTIVE"),
        new Customer("An", "PENDING")
);

Flux<Customer> savedCustomers = customerRepository.saveAll(customers);
```

Khi pipeline được subscribe, Spring Data nhận diện các entity chưa có ID là mới, thực hiện insert và phát ra entity sau lưu. Hãy dùng các entity được phát ra để lấy ID do database sinh:

```java
return customerRepository.saveAll(customers)
        .doOnNext(saved -> log.info("Saved customer id={}", saved.getId()));
```

Không nên giả định object đầu vào luôn được cập nhật tại chỗ. Với entity bất biến, Spring Data có thể tạo instance mới chứa ID; ngay cả với entity mutable, kết quả phát ra là giá trị nên được dùng sau persistence.

## 4. `saveAll` không bảo đảm là một SQL batch

Một hiểu lầm thường gặp là:

```java
customerRepository.saveAll(customers);
```

đồng nghĩa với:

```sql
INSERT INTO customer (name, status)
VALUES
    ('Lan', 'ACTIVE'),
    ('Minh', 'ACTIVE'),
    ('An', 'PENDING');
```

Không thể suy ra điều đó chỉ từ tên `saveAll`. API repository mô tả việc lưu tất cả entity. Triển khai thông dụng xử lý từng entity qua logic `save`, và mỗi lần có thể phát một statement riêng. Việc driver có tối ưu nội bộ hay không là chi tiết implementation, không phải cam kết portable của `saveAll`.

Hệ quả có thể gồm:

- Nhiều statement được chuẩn bị/thực thi thay vì một statement nhiều hàng.
- Mỗi entity có thể đi qua callback, conversion và newness detection riêng.
- Generated ID/version có thể được trả về cho từng entity.
- Thời gian hoàn thành tăng theo số entity và round-trip database.
- Backpressure có thể điều tiết quá trình tiêu thụ publisher, nhưng không tự biến các statement thành một batch.

Nếu mục tiêu là giảm số lần gửi statement tới database, hãy dùng API batch hoặc multi-row SQL mà driver/database hỗ trợ, sau khi xác định rõ các lifecycle behavior cần giữ.

## 5. `Iterable` và `Publisher` overload của `saveAll`

Hai overload phục vụ hai nguồn dữ liệu khác nhau.

### Nguồn là `Iterable`

```java
List<Customer> customers = loadCustomers();
return customerRepository.saveAll(customers);
```

Danh sách đã tồn tại trong bộ nhớ trước khi gọi repository. Nếu danh sách lớn, ứng dụng phải giữ các entity trong heap trước khi bắt đầu tiêu thụ publisher. Phù hợp khi số lượng vừa phải và dữ liệu đã được tạo/đọc thành collection.

### Nguồn là `Publisher`

```java
Flux<Customer> customerStream = readCustomersFromSource();
return customerRepository.saveAll(customerStream);
```

Nguồn publisher cho phép cung cấp entity theo luồng. Nó phù hợp với pipeline reactive và có thể tận dụng backpressure từ upstream. Tuy nhiên, nếu upstream tự materialize toàn bộ dữ liệu vào một `List`, lợi ích về bộ nhớ không còn.

Publisher đầu vào cần phát entity theo thứ tự và nhịp mà pipeline có thể tiêu thụ. Trong implementation tuần tự thường gặp, mỗi entity được save xong trước khi xử lý entity kế tiếp. Nếu cần kiểm soát batch size, chia nguồn thành các chunk hữu hạn thay vì gom toàn bộ nguồn không giới hạn.

## 6. SQL batch qua `Statement.add()`

R2DBC SPI định nghĩa `Statement.add()` để thêm một bộ giá trị bind vào batch của cùng một câu SQL. Cách này hữu ích khi nhiều bản ghi có cùng hình dạng câu lệnh, ví dụ nhiều hàng cùng insert vào một bảng với cùng tập cột.

Ví dụ dùng PostgreSQL marker `$1`, `$2`:

```java
Statement statement = connection.createStatement(
        "INSERT INTO customer (id, name) VALUES ($1, $2)"
);

statement.bind(0, 101L).bind(1, "Lan").add();
statement.bind(0, 102L).bind(1, "Minh").add();
statement.bind(0, 103L).bind(1, "An");

Publisher<? extends Result> results = statement.execute();
```

Index của `bind` trong R2DBC SPI bắt đầu từ 0, dù marker PostgreSQL trong SQL bắt đầu bằng `$1`. `add()` lưu bộ bind hiện tại vào batch và cho phép cung cấp bộ giá trị tiếp theo. Bộ giá trị cuối cùng được giữ để thực thi khi gọi `execute()`.

### Điều kiện để dùng Statement batch

- Các bản ghi cần thực thi cùng một câu SQL hoặc cùng hình dạng statement.
- Mỗi bộ bind phải cung cấp đủ tham số với kiểu tương thích.
- Driver phải hỗ trợ `Statement.add()` cho statement/kiểu dữ liệu đang dùng.
- Cú pháp placeholder phải đúng với driver.
- Ứng dụng phải quản lý connection và tiêu thụ `Result` đúng vòng đời.

Không phải driver nào cũng hỗ trợ mọi hình thức batch giống nhau. Một số driver có giới hạn về generated values, kiểu dữ liệu, số bộ bind hoặc cách trả update count. Cần kiểm tra tài liệu driver và chạy integration test với phiên bản database thực tế.

### Đọc kết quả batch

`Statement.execute()` trả publisher của `Result`. Có thể đọc số hàng được cập nhật:

```java
Flux<Long> updateCounts = Flux.from(statement.execute())
        .concatMap(result -> Flux.from(result.getRowsUpdated()));
```

Số lượng `Result`, cách biểu diễn update count và khả năng trả generated values phụ thuộc driver. Không nên giả định luôn nhận đúng một result cho mỗi bộ bind hoặc luôn có generated key theo cùng thứ tự nếu driver không cam kết điều đó.

## 7. Quản lý connection khi dùng R2DBC SPI trực tiếp

Khi dùng `Statement.add()` trực tiếp, ứng dụng chịu trách nhiệm lấy và giải phóng connection. Với reactive code, cần bảo đảm `close()` được gọi khi hoàn tất, lỗi hoặc hủy subscription. `usingWhen` là một lựa chọn để quản lý tài nguyên bất đồng bộ:

```java
public Mono<Long> insertBatch(List<CustomerInput> customers) {
    if (customers.isEmpty()) {
        return Mono.just(0L);
    }

    return Mono.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> {
                Statement statement = connection.createStatement(
                        "INSERT INTO customer (id, name) VALUES ($1, $2)"
                );

                for (int i = 0; i < customers.size(); i++) {
                    CustomerInput customer = customers.get(i);
                    statement.bind(0, customer.id())
                            .bind(1, customer.name());

                    if (i < customers.size() - 1) {
                        statement.add();
                    }
                }

                return Flux.from(statement.execute())
                        .concatMap(result -> Flux.from(result.getRowsUpdated()))
                        .reduce(0L, Long::sum);
            },
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

Đây là ví dụ minh họa với PostgreSQL và driver hỗ trợ `Statement.add()`. Nó giả định danh sách batch đã nằm trong bộ nhớ, ID được cung cấp sẵn và driver hỗ trợ kiểu bind tương ứng. Nếu ID do database sinh hoặc cần trả generated values, phải kiểm tra API/codec của driver và thiết kế cách tiêu thụ kết quả phù hợp.

`usingWhen` đóng connection ở các đường hoàn tất, lỗi và cancel. Nếu dùng connection pool, `close()` thường trả connection về pool. Trong ứng dụng Spring Data thông thường, ưu tiên `DatabaseClient`, `R2dbcEntityTemplate` hoặc repository khi chúng đã đáp ứng yêu cầu; thao tác SPI trực tiếp tăng trách nhiệm quản lý tài nguyên và phụ thuộc driver.

## 8. `Connection.createBatch()` khác `Statement.add()`

R2DBC SPI còn có `Connection.createBatch()` để tạo một batch gồm nhiều câu SQL:

```java
Batch batch = connection.createBatch();
batch.add("UPDATE customer SET status = 'INACTIVE' WHERE id = 1");
batch.add("UPDATE customer SET status = 'INACTIVE' WHERE id = 2");

Publisher<? extends Result> results = batch.execute();
```

`Batch` phù hợp với nhiều câu SQL cần thực thi trong một batch, nhưng API này không cung cấp cơ chế bind parameter như `Statement`. Không nối dữ liệu người dùng trực tiếp vào chuỗi SQL để tạo batch; làm vậy có nguy cơ SQL injection và lỗi escaping. Với cùng một câu lệnh có nhiều bộ giá trị, `Statement.add()` phù hợp hơn vì vẫn dùng bind parameters.

| API | SQL | Tham số |
| --- | --- | --- |
| `Statement` | Một câu SQL | Bind một bộ giá trị |
| `Statement.add()` | Một câu SQL lặp lại | Nhiều bộ giá trị bind cho cùng statement |
| `Connection.createBatch()` | Nhiều câu SQL | Không có bind parameter API như `Statement` |

Driver có thể hỗ trợ các API này ở mức khác nhau. Đừng giả định batch sẽ luôn được gửi thành đúng một network packet; đó là chi tiết của driver và giao thức.

## 9. Multi-row INSERT: một câu lệnh ghi nhiều hàng

Nếu tất cả bản ghi có cùng tập cột, một câu `INSERT` có thể chứa nhiều nhóm `VALUES`:

```sql
INSERT INTO customer (id, name, status)
VALUES
    (:id1, :name1, :status1),
    (:id2, :name2, :status2),
    (:id3, :name3, :status3);
```

Trong `DatabaseClient`, có thể bind các named parameter của câu SQL đã được xây dựng cho số hàng cố định:

```java
Mono<Long> insertThree(CustomerInput a, CustomerInput b, CustomerInput c) {
    return databaseClient.sql("""
                INSERT INTO customer (id, name, status)
                VALUES
                    (:id1, :name1, :status1),
                    (:id2, :name2, :status2),
                    (:id3, :name3, :status3)
                """)
            .bind("id1", a.id())
            .bind("name1", a.name())
            .bind("status1", a.status())
            .bind("id2", b.id())
            .bind("name2", b.name())
            .bind("status2", b.status())
            .bind("id3", c.id())
            .bind("name3", c.name())
            .bind("status3", c.status())
            .fetch()
            .rowsUpdated();
}
```

Đây là một SQL statement nhiều hàng, không phải `Statement.add()`. Số placeholder tăng theo số hàng và database có giới hạn số bind parameter, kích thước statement hoặc packet. Với số hàng biến động, ứng dụng phải xây dựng SQL có cấu trúc an toàn và bind từng giá trị; không được ghép trực tiếp dữ liệu đầu vào vào SQL.

Multi-row insert có thể giảm số statement/round-trip, nhưng có những giới hạn:

- Các hàng thường cần cùng tập cột và cấu trúc values.
- Số bind parameter tăng theo số hàng và số cột.
- Generated ID/returning có thể có semantics riêng theo database.
- Một lỗi constraint có thể làm cả statement thất bại.
- Cú pháp và giới hạn khác nhau giữa database.

Nếu database hỗ trợ `INSERT ... RETURNING`, có thể lấy dữ liệu trả về, nhưng cách mapping nhiều generated rows phải được viết rõ và kiểm thử theo driver.

## 10. Bulk UPDATE/DELETE và `@Modifying`

Không phải batch nào cũng là insert. Nếu cần cập nhật nhiều hàng theo cùng một điều kiện, một câu SQL bulk có thể hiệu quả hơn việc tải từng entity rồi gọi save:

```java
@Modifying
@Query("UPDATE customer SET status = :newStatus WHERE last_login < :cutoff")
Mono<Integer> deactivateDormantCustomers(
        @Param("newStatus") String newStatus,
        @Param("cutoff") Instant cutoff
);
```

Hoặc dùng `DatabaseClient`:

```java
Mono<Long> deactivateDormantCustomers(Instant cutoff) {
    return databaseClient.sql("""
                UPDATE customer
                SET status = :status,
                    last_modified = :modifiedAt
                WHERE last_login < :cutoff
                """)
            .bind("status", "INACTIVE")
            .bind("modifiedAt", Instant.now())
            .bind("cutoff", cutoff)
            .fetch()
            .rowsUpdated();
}
```

Một lệnh bulk có thể tác động hàng nghìn hàng mà không tạo entity cho từng hàng. Nhưng các hàng không đi qua entity lifecycle riêng:

- Entity callback không tự chạy cho từng hàng.
- Auditing phải được thể hiện trong SQL nếu cần cập nhật.
- `@Version` không tự thêm điều kiện optimistic locking hoặc tăng version.
- Object đã đọc trước đó có thể trở nên stale.
- Kết quả thường là update count, không phải danh sách entity đã lưu.

Bulk update phù hợp khi quy tắc có thể biểu đạt rõ trong SQL và ứng dụng không cần callback theo từng entity. Nếu mỗi hàng cần logic domain khác nhau, có thể cần xử lý entity riêng hoặc chia thành các nhóm thao tác.

## 11. Transaction và tính nguyên tử của nhiều lần ghi

Không nên suy luận rằng gọi một phương thức `saveAll` là toàn bộ dữ liệu chắc chắn được commit hoặc rollback như một đơn vị. Nếu yêu cầu all-or-nothing, hãy đặt chuỗi ghi trong reactive transaction phù hợp.

Ví dụ:

```java
@Transactional
public Mono<List<Customer>> saveCustomers(List<Customer> customers) {
    return customerRepository.saveAll(customers)
            .collectList();
}
```

Khi publisher được subscribe trong transaction context do Spring quản lý, các thao tác repository tham gia transaction theo cấu hình phù hợp. Nếu một thao tác lỗi, transaction có thể rollback các thay đổi database trong transaction đó. Hành vi cuối cùng còn phụ thuộc database, driver và transaction manager.

Với SPI trực tiếp, nếu cần một batch nằm trong transaction, connection phải thuộc transaction đó. Không tự lấy một connection mới ngoài transaction context rồi kỳ vọng thao tác sẽ tham gia transaction do Spring quản lý. Khi dùng Spring transaction, ưu tiên để Spring quản lý connection qua factory/transaction manager phù hợp hoặc dùng `TransactionalOperator`.

### Không tự subscribe trong service

Không nên:

```java
@Transactional
public Mono<Void> saveAllCustomers(List<Customer> customers) {
    customerRepository.saveAll(customers).subscribe();
    return Mono.empty();
}
```

`subscribe()` tạo subscription riêng, có thể tách khỏi transaction context của publisher trả về. Caller cũng không chờ được toàn bộ quá trình ghi và không nhận lỗi qua publisher trả về. Hãy trả publisher thực sự đại diện cho công việc:

```java
@Transactional
public Mono<Void> saveAllCustomers(List<Customer> customers) {
    return customerRepository.saveAll(customers).then();
}
```

## 12. Lỗi giữa batch và retry

Khi ghi nhiều bản ghi, cần quyết định hành vi nếu một phần tử lỗi.

### `saveAll` không có transaction bao quanh

Nếu mỗi thao tác được thực thi riêng và không nằm trong transaction chung, các entity trước lỗi có thể đã được ghi thành công. Khi một entity tiếp theo lỗi, publisher phát error và dừng chuỗi; những ghi trước đó không tự động được hoàn tác chỉ vì cả `Flux` thất bại.

### Có transaction bao quanh

Nếu toàn bộ thao tác nằm trong transaction reactive và lỗi làm transaction rollback, các thay đổi database trong transaction có thể được hoàn tác cùng nhau. Điều này tạo tính nguyên tử nhưng transaction dài có thể giữ connection và lock lâu hơn.

### Batch statement hoặc multi-row SQL

Một lỗi trong batch có thể làm driver/database dừng ở một phần tử, báo lỗi cho cả batch hoặc cung cấp kết quả theo cách riêng. Một multi-row `INSERT` thường là một statement, nhưng semantics transaction/constraint vẫn do database quyết định. Hãy kiểm tra driver để biết update count và hành vi partial failure.

### Retry có thể ghi trùng

Nếu retry toàn bộ một batch insert sau lỗi mạng, một số hàng có thể đã được database ghi trước khi client nhận được lỗi. Gửi lại có thể tạo duplicate key hoặc lặp tác dụng phụ nếu thao tác không idempotent.

Đối với ghi quan trọng:

- Dùng khóa duy nhất hoặc business key để chống ghi trùng.
- Thiết kế upsert/idempotency key nếu database hỗ trợ và nghiệp vụ phù hợp.
- Chỉ retry lỗi tạm thời có thể phục hồi.
- Giới hạn số lần retry và có backoff.
- Xác định rõ thao tác nào an toàn khi chạy lại.

Không đặt `retry` một cách máy móc quanh batch ghi mà chưa phân tích khả năng database đã thực thi một phần hoặc hoàn tất trước khi kết nối bị lỗi.

## 13. Chia dữ liệu thành chunk

Đưa hàng triệu entity vào một `List` rồi gọi `saveAll` hoặc tạo một statement batch khổng lồ có thể tiêu tốn nhiều bộ nhớ, vượt giới hạn tham số hoặc giữ transaction quá lâu. Có thể chia publisher thành các chunk hữu hạn:

```java
public Mono<Long> saveInChunks(Flux<Customer> source, int batchSize) {
    if (batchSize < 1 || batchSize > 1000) {
        return Mono.error(new IllegalArgumentException("batchSize không hợp lệ"));
    }

    return source
            .buffer(batchSize)
            .concatMap(batch -> customerRepository.saveAll(batch).count())
            .reduce(0L, Long::sum);
}
```

`buffer(batchSize)` tạo từng danh sách hữu hạn. `concatMap` xử lý lần lượt từng chunk, giúp không chạy tất cả batch đồng thời. Ví dụ này vẫn gọi `saveAll` cho từng chunk; nó không tự biến mỗi chunk thành SQL batch. Mục đích của chunking ở đây là giới hạn lượng entity được giữ trong bộ nhớ và điều tiết công việc.

Nếu mỗi chunk cần một transaction riêng, có thể bọc thao tác chunk bằng transaction operator hoặc cấu trúc service phù hợp. Khi dùng một transaction bao trùm toàn bộ nguồn, dù đã chunk, transaction vẫn có thể kéo dài tới khi toàn bộ nguồn hoàn tất.

### `concatMap` và `flatMap` không đồng nghĩa với batch

```java
source.concatMap(customerRepository::save);
```

thực hiện các publisher save tuần tự. Trong khi:

```java
source.flatMap(customerRepository::save, 8);
```

có thể chạy tối đa một số thao tác save đồng thời. Cả hai đều có thể tạo nhiều statement riêng; `flatMap` tăng concurrency chứ không tự gom statement thành batch.

Concurrency cao có thể làm tăng áp lực lên connection pool và database, làm thứ tự hoàn thành khác thứ tự đầu vào. Chọn concurrency theo năng lực hệ thống và yêu cầu thứ tự; không xem nó là thay thế cho batching thực sự.

## 14. Kích thước batch và giới hạn database

Batch càng lớn không phải lúc nào cũng càng nhanh. Một batch lớn có thể giảm số lần gửi nhưng làm tăng:

- Bộ nhớ cần để giữ entity, parameter và result.
- Kích thước statement/packet truyền qua mạng.
- Số bind parameter trong một statement.
- Thời gian giữ transaction, lock và connection.
- Chi phí rollback nếu một phần batch thất bại.
- Độ trễ của phần tử đầu tiên vì phải chờ gom đủ batch.

Batch quá nhỏ lại làm tăng overhead gửi statement và round-trip. Kích thước phù hợp phụ thuộc số cột, kích thước payload, giới hạn driver/database, độ trễ mạng và workload ghi.

Một số nguyên tắc:

1. Bắt đầu với batch vừa phải và đo thực tế.
2. Giữ số bind parameter dưới giới hạn database/driver.
3. Giới hạn payload tổng thể, nhất là khi có JSON hoặc dữ liệu nhị phân lớn.
4. Tránh giữ connection và transaction lâu hơn cần thiết.
5. Theo dõi latency, throughput, lỗi, pool acquire time và database load.
6. Kiểm thử với dữ liệu và kích thước gần production.

Không có một con số batch size tối ưu áp dụng cho mọi R2DBC driver và database.

## 15. Generated ID và kết quả của batch

Với `saveAll`, mỗi entity được xử lý theo entity persistence path. Khi database sinh ID và driver hỗ trợ trả generated values, Spring Data có thể phát ra entity có ID sau khi lưu. Điều này thuận tiện khi tầng ứng dụng cần tiếp tục xử lý từng entity đã lưu.

Với batch `Statement.add()` hoặc multi-row SQL, generated values phức tạp hơn:

- Driver có hỗ trợ `returnGeneratedValues` cho batch hay không?
- Có trả một result cho mỗi bộ bind hay một result tổng hợp?
- Thứ tự generated values có được bảo đảm khớp thứ tự input không?
- Có hỗ trợ `RETURNING` cho multi-row statement không?
- Làm thế nào ánh xạ từng ID trả về với bản ghi nguồn?

Đây là các câu hỏi phụ thuộc driver/database. Không nên giả định batch luôn trả generated ID theo cách giống `saveAll`. Nếu cần ID/version cho từng entity, hãy kiểm tra khả năng driver và viết integration test. Nếu driver không cung cấp semantics đáng tin cậy, có thể dùng ID do ứng dụng cấp hoặc chọn entity-oriented save.

## 16. Auditing, callbacks và optimistic locking

Sự khác biệt lifecycle là lý do quan trọng để chọn `saveAll` hay SQL batch.

### Auditing

Khi `saveAll` đi qua entity persistence path và auditing được cấu hình, các property như `@CreatedDate`/`@LastModifiedDate` có thể được cập nhật theo callback cho từng entity.

Batch SQL không tự chạy callback auditing. Nếu cần timestamp hoặc actor, câu lệnh phải ghi chúng tường minh:

```sql
INSERT INTO customer (id, name, created_at, last_modified_at)
VALUES ($1, $2, $3, $3);
```

### Optimistic locking

Entity có `@Version` có thể được cập nhật với điều kiện version và tăng version qua entity persistence path được hỗ trợ. Một statement batch tự viết không tự đọc annotation `@Version`. Nếu cần optimistic locking, phải đưa version mong đợi vào điều kiện và tăng version trong SQL.

### Callbacks và domain logic

Callback trước/sau lưu, conversion và logic nằm trong entity/service không tự chạy chỉ vì SQL batch tác động cùng bảng. Bulk SQL phù hợp khi logic có thể được biểu diễn trong câu lệnh và không cần lifecycle từng entity. Nếu callback là một phần bắt buộc của nghiệp vụ, dùng entity path hoặc thực hiện rõ logic tương đương trước khi batch.

## 17. SQL batch và bảo mật tham số

Luôn bind dữ liệu thay vì nối chuỗi:

```java
statement.bind(0, customer.id())
        .bind(1, customer.name());
```

Không làm:

```java
String sql = "INSERT INTO customer(name) VALUES ('" + customer.name() + "')";
```

Nối dữ liệu có thể làm hỏng câu SQL khi chứa dấu nháy, gây lỗi encoding và tạo SQL injection. `Statement.add()` cho phép dùng cùng câu SQL với nhiều bộ bind nên thường là lựa chọn tốt hơn khi driver hỗ trợ.

Với multi-row SQL có số hàng động, cần tạo cấu trúc placeholder một cách an toàn, còn giá trị vẫn phải bind riêng. Không dùng dữ liệu người dùng để tạo tên cột, bảng hoặc fragment SQL nếu chưa kiểm tra với danh sách cho phép.

## 18. So sánh chi tiết `saveAll` và SQL batch

| Tiêu chí | `saveAll` | `Statement.add()` / multi-row SQL |
| --- | --- | --- |
| Tầng API | Spring Data repository | R2DBC SPI hoặc SQL API |
| Đầu vào | Entity | Bộ tham số hoặc SQL nhiều hàng |
| Newness detection | Có theo từng entity | Không tự có |
| Insert và update hỗn hợp | Có thể xử lý theo trạng thái entity | Phải thiết kế statement/nhóm riêng |
| Mapping metadata | Dựa trên entity mapping | SQL và kiểu bind do ứng dụng kiểm soát |
| Custom conversions | Có qua Spring Data conversions | Thường phải bind kiểu driver hỗ trợ hoặc chuyển đổi trước |
| Entity callbacks | Có thể chạy theo lifecycle persistence | Không tự chạy |
| Auditing | Có thể áp dụng nếu cấu hình | Phải ghi tường minh |
| `@Version` | Có thể áp dụng optimistic locking | Phải tự thêm điều kiện/tăng version |
| Generated ID | Có thể phát entity sau lưu với ID | Phụ thuộc khả năng returning/generated values của driver |
| SQL statement | Thường có thao tác cho từng entity | Có thể gom nhiều bộ bind/các hàng trong một lần thực thi |
| Số round-trip | Có thể nhiều lần | Có thể giảm, tùy driver và SQL |
| Kết quả | Entity được lưu | Result/update count hoặc hàng trả về |
| Tính portable | Cao hơn ở tầng Spring Data | Phụ thuộc dialect và driver nhiều hơn |
| Kiểm soát SQL | Thấp hơn | Cao hơn |
| Phù hợp | CRUD entity và lifecycle behavior | Dữ liệu đồng nhất, bulk operation, throughput |

## 19. Chọn cách nào trong từng tình huống?

### Chọn `saveAll` khi

- Đầu vào đã là các entity Spring Data cần lưu.
- Có thể trộn entity mới và entity đã tồn tại.
- Cần generated ID/version và entity kết quả.
- Cần auditing, callbacks hoặc custom conversion của Spring Data.
- Số lượng dữ liệu vừa phải và sự đơn giản của repository quan trọng hơn tối ưu batch cấp thấp.
- Muốn giữ code ít phụ thuộc driver/database.

### Chọn `Statement.add()` khi

- Nhiều hàng có cùng cấu trúc SQL.
- Cần bind nhiều bộ tham số cho một statement.
- Driver hỗ trợ batch parameter sets.
- Có thể tự quản lý connection, kết quả và vòng đời tài nguyên.
- Có thể tự xử lý auditing/version/generated values nếu cần.

### Chọn multi-row SQL khi

- Database hỗ trợ cú pháp insert nhiều hàng hoặc bulk statement phù hợp.
- Các hàng có cùng tập cột.
- Muốn giảm số statement và round-trip.
- Số hàng và số bind parameter nằm trong giới hạn.
- Có thể kiểm soát generated values và lỗi constraint.

### Chọn bulk UPDATE/DELETE khi

- Nhiều hàng cần thay đổi theo cùng một predicate.
- Có thể mô tả logic trực tiếp trong SQL.
- Không cần entity lifecycle cho từng hàng.
- Kết quả update count đủ để phục vụ nghiệp vụ hoặc có thể đọc lại khi cần.

### Chọn chunked `saveAll` khi

- Nguồn dữ liệu lớn và không muốn giữ tất cả entity trong bộ nhớ.
- Vẫn cần entity lifecycle của Spring Data.
- Muốn giới hạn lượng công việc và transaction theo từng nhóm.
- Chấp nhận rằng mỗi entity vẫn có thể được ghi bằng statement riêng.

## 20. Kiểm thử và đo hiệu năng

Không nên chọn SQL batch chỉ dựa trên giả định “batch luôn nhanh hơn”. Hãy đo cùng một dữ liệu đầu vào với các cách triển khai phù hợp.

### Kiểm thử tính đúng

- `saveAll` lưu đúng số entity mới và phát entity có ID khi database sinh khóa.
- `saveAll` xử lý entity đã tồn tại theo newness detection.
- Callback/auditing/version được áp dụng trên entity path như cấu hình.
- `Statement.add()` thực thi đủ bộ tham số và trả update count theo driver.
- Multi-row insert tạo đúng số hàng và xử lý constraint đúng.
- Batch lỗi giữa chừng có hành vi đúng với transaction boundary.
- Generated values được ánh xạ đúng nếu nghiệp vụ cần.
- Retry không tạo duplicate hoặc lặp tác dụng phụ ngoài dự kiến.
- Chunking không làm mất, lặp hoặc đảo dữ liệu ngoài yêu cầu.

Ví dụ kiểm thử repository:

```java
StepVerifier.create(customerRepository.saveAll(customers).collectList())
        .assertNext(saved -> {
            assertThat(saved).hasSize(3);
            assertThat(saved).allMatch(customer -> customer.getId() != null);
        })
        .verifyComplete();
```

Với batch SPI, integration test nên chạy bằng đúng driver và database, không chỉ mock `Statement`, vì mock không chứng minh driver hỗ trợ `add()` hoặc generated values.

### Đo hiệu năng

So sánh ít nhất:

1. `saveAll` với cùng danh sách entity.
2. `saveAll` theo chunk có kích thước hữu hạn.
3. `Statement.add()` nếu driver hỗ trợ.
4. Multi-row insert với kích thước batch phù hợp.

Ghi nhận:

- Tổng thời gian và throughput (rows/second).
- Latency của từng chunk/batch.
- Số statement/round-trip nếu có thể quan sát.
- CPU và memory của ứng dụng.
- CPU, I/O, lock và connection load của database.
- Số connection đang mượn, pending acquire và thời gian chờ pool.
- Tỷ lệ lỗi, retry và số hàng thực sự ghi được.

Đo với cùng schema, index, constraint, transaction semantics và dữ liệu. So sánh một phương án có auditing/version với một phương án bỏ qua chúng là so sánh hai yêu cầu khác nhau; phải bảo đảm các cách đo thực hiện cùng quy tắc nghiệp vụ.

## 21. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `saveAll` chậm khi số entity lớn | Có nhiều thao tác save/statement riêng | Đo số round-trip; cân nhắc batch hoặc multi-row SQL nếu lifecycle không bắt buộc |
| Nghĩ `saveAll` tự tạo một SQL batch | Nhầm API lưu nhiều entity với driver batch | Kiểm tra implementation/version; dùng SPI batch nếu cần bảo đảm cách thực thi |
| `Statement.add()` không hoạt động | Driver không hỗ trợ hoặc bind set không đúng thứ tự | Kiểm tra driver, marker và semantics `add()` |
| Batch thiếu hàng cuối | Gọi `add()` sai vị trí hoặc không thực thi bộ bind cuối | Kiểm tra cách thêm parameter set theo SPI/driver |
| Generated ID không được trả về | Driver không hỗ trợ generated values cho batch hoặc cách dùng sai | Kiểm tra `returnGeneratedValues`/`RETURNING` và integration test |
| Auditing không cập nhật trong bulk SQL | Direct SQL không đi qua entity callback | Ghi timestamp/actor trong SQL hoặc dùng entity persistence |
| Version không tăng | Batch tự viết bỏ qua `@Version` | Tự thêm điều kiện và tăng version hoặc dùng entity path |
| Batch lỗi nhưng một phần hàng vẫn tồn tại | Không có transaction chung hoặc driver có partial failure semantics | Xác định transaction boundary và kiểm tra kết quả driver |
| Retry tạo duplicate | Batch có thể đã được thực thi trước khi lỗi truyền về | Dùng idempotency/unique key và retry có kiểm soát |
| Pool cạn khi chạy nhiều batch đồng thời | Concurrency quá cao hoặc connection/transaction giữ lâu | Giới hạn concurrency, chunk và thời gian giữ connection |
| Bộ nhớ tăng mạnh | Materialize toàn bộ nguồn hoặc batch quá lớn | Dùng Publisher, buffer theo chunk và tránh collect toàn bộ không cần thiết |
| Update count không như dự kiến | Driver trả count theo result/batch semantics riêng | Đọc `Result.getRowsUpdated()` và kiểm tra tài liệu driver |

## 22. Quy trình triển khai ghi nhiều bản ghi

Một quy trình thực tế có thể gồm:

1. Xác định đầu vào là entity cần đi qua mapping lifecycle hay dữ liệu thuần để bulk SQL.
2. Xác định có entity mới/cũ hỗn hợp hay không.
3. Liệt kê yêu cầu auditing, callback, conversion, generated ID và optimistic locking.
4. Kiểm tra driver có hỗ trợ `Statement.add()`, multi-row SQL hoặc bulk API mong muốn.
5. Xác định transaction boundary: toàn bộ batch hay từng chunk.
6. Chọn kích thước chunk/batch theo giới hạn bind, packet, memory và thời gian transaction.
7. Bind parameter an toàn; không nối dữ liệu đầu vào vào SQL.
8. Tiêu thụ publisher và quản lý connection cho cả đường hoàn tất, lỗi và cancel.
9. Kiểm thử partial failure, retry, duplicate key và generated values.
10. Benchmark bằng workload gần production rồi điều chỉnh batch size/concurrency.

## 23. Ghi nhớ

- `saveAll` là API lưu nhiều entity qua Spring Data; không phải cam kết rằng database nhận một SQL batch duy nhất.
- Trong triển khai repository R2DBC thông dụng, `saveAll` xử lý từng entity qua logic save; mỗi entity có thể tạo statement riêng. Kiểm tra phiên bản nếu dựa vào chi tiết triển khai.
- `saveAll` giữ các hành vi entity-oriented như newness detection, mapping, conversion, callback, auditing và optimistic locking theo cấu hình/hỗ trợ.
- `Statement.add()` gom nhiều bộ bind cho cùng một SQL statement; driver phải hỗ trợ.
- `Connection.createBatch()` gom nhiều câu SQL và khác với `Statement.add()`; API batch không cung cấp bind parameters như Statement.
- Multi-row `INSERT` là một câu SQL có nhiều nhóm `VALUES`, có giới hạn bind/packet và cú pháp theo database.
- Bulk UPDATE/DELETE có thể tác động nhiều hàng trong một lệnh nhưng không tự chạy entity callbacks, auditing hoặc `@Version`.
- `concatMap` tuần tự và `flatMap` tăng concurrency; cả hai không tự biến các thao tác riêng lẻ thành SQL batch.
- Chunking giới hạn bộ nhớ và kích thước công việc; chunk `saveAll` vẫn có thể thực hiện từng save riêng.
- Nếu cần all-or-nothing, xác định reactive transaction rõ ràng; đừng suy luận tính nguyên tử chỉ từ tên `saveAll`.
- Retry batch ghi có thể tạo duplicate nếu database đã thực thi trước khi client nhận lỗi; thiết kế idempotency và unique constraint.
- Dùng entity kết quả từ `saveAll` để nhận generated ID/version; với SQL batch, generated values phụ thuộc driver và cần kiểm thử.
- Đo throughput, latency, round-trip, memory, pool và database load trước khi chọn batch size.

Khi ghi nhiều bản ghi bằng Spring Data R2DBC, hãy chọn API dựa trên ngữ nghĩa cần giữ. `saveAll` phù hợp khi muốn Spring Data lưu từng entity theo mapping lifecycle. `Statement.add()` và multi-row SQL phù hợp khi dữ liệu có cấu trúc đồng nhất và ứng dụng có thể quản lý trực tiếp batch, transaction, auditing, version cùng generated values. Việc gọi đúng tên API chưa đủ để biết hiệu năng; cần kiểm tra driver và đo cách thực thi thực tế.

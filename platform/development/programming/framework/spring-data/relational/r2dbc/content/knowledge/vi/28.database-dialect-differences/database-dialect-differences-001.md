# Đánh giá mức hỗ trợ R2DBC của hệ quản trị và trình điều khiển

Khi chọn database cho một ứng dụng Spring Data R2DBC, không thể chỉ hỏi hệ quản trị có hỗ trợ R2DBC hay không. R2DBC là một SPI ở phía ứng dụng Java; hệ quản trị vẫn giao tiếp qua giao thức và khả năng riêng của nó, còn R2DBC driver chịu trách nhiệm triển khai SPI và chuyển các thao tác thành lệnh mà database hiểu. Spring Data R2DBC tiếp tục dựa vào driver, metadata và dialect để ánh xạ entity, tạo SQL và xử lý các kiểu dữ liệu.

Vì vậy, mức hỗ trợ thực tế là kết quả của nhiều thành phần cùng tương thích: phiên bản database server, R2DBC driver, R2DBC SPI, Spring Framework, Spring Data Relational/R2DBC, Spring Boot và Java. Một driver có thể kết nối thành công nhưng chưa chắc hỗ trợ đầy đủ các kiểu dữ liệu, generated values, transaction, cancellation, pooling hoặc các tính năng SQL mà ứng dụng cần.

Đánh giá đúng cần đi từ yêu cầu nghiệp vụ đến khả năng của database và driver, sau đó xác nhận bằng integration test trên đúng tổ hợp phiên bản dự kiến triển khai. Bài học này trình bày cách lập ma trận tương thích, nhận diện giới hạn ở từng lớp, thiết kế thử nghiệm và đưa ra quyết định kỹ thuật có căn cứ.

## 1. R2DBC là gì và thành phần nào chịu trách nhiệm?

R2DBC (Reactive Relational Database Connectivity) định nghĩa một SPI cho ứng dụng Java truy cập database quan hệ theo mô hình reactive. SPI cung cấp các abstraction như `ConnectionFactory`, `Connection`, `Statement`, `Result`, `Row` và `RowMetadata`. Driver cụ thể triển khai các abstraction đó cho một hệ quản trị và giao thức tương ứng.

Một hệ quản trị không nhất thiết phải triển khai trực tiếp R2DBC. Thông thường driver chạy trong ứng dụng, nói chuyện với database qua giao thức native hoặc giao thức mà sản phẩm cung cấp, rồi phơi bày API R2DBC cho code Java.

```text
Spring application
       |
       v
Spring Data R2DBC
  - Repository
  - R2dbcEntityTemplate
  - Mapping / dialect
       |
       v
R2DBC SPI
  - ConnectionFactory
  - Connection / Statement
  - Result / Row
       |
       v
Vendor R2DBC driver
  - protocol handling
  - type conversion
  - parameter binding
  - transaction integration
       |
       v
Database server
  - SQL engine
  - data types
  - constraints / indexes
  - transactions / isolation
```

Các lớp có trách nhiệm khác nhau:

- **Database server:** quyết định cú pháp SQL, kiểu dữ liệu, transaction, isolation, constraint, generated column, locking và các tính năng riêng của hệ quản trị.
- **R2DBC driver:** triển khai SPI, quản lý giao thức, chuyển đổi kiểu, bind tham số, đọc kết quả, xử lý lỗi và tương tác với server.
- **R2DBC SPI:** định nghĩa hợp đồng API chung để ứng dụng sử dụng driver theo cách thống nhất.
- **Spring Data R2DBC:** cung cấp repository, mapping entity, conversion, dialect và các abstraction truy vấn dựa trên SPI.
- **Spring Boot:** hỗ trợ auto-configuration, dependency management, cấu hình `ConnectionFactory`, pool và các thành phần liên quan.

Một lỗi có thể xuất phát từ bất kỳ lớp nào. Ví dụ, server hỗ trợ JSONB nhưng driver không chuyển kiểu đó thuận tiện; driver hỗ trợ transaction nhưng Spring Data dialect chưa biểu diễn một cú pháp riêng; hoặc Spring Boot quản lý một phiên bản driver không tương thích với phiên bản server đang chạy.

## 2. Đánh giá theo tổ hợp phiên bản, không theo tên sản phẩm

Không nên ghi kết luận đơn giản như “Database X hỗ trợ R2DBC”. Kết luận cần gắn với một tổ hợp phiên bản cụ thể.

Một ma trận tương thích nên có ít nhất các thành phần:

| Thành phần | Thông tin cần ghi nhận | Vì sao quan trọng |
|---|---|---|
| Database product | Tên sản phẩm và phiên bản server | Quyết định SQL, data type, transaction và feature có sẵn |
| R2DBC driver | Artifact, version, nhà phát hành | Quyết định khả năng kết nối và triển khai SPI |
| R2DBC SPI | Version API mà driver triển khai | Quyết định hợp đồng giữa ứng dụng và driver |
| Spring Boot | Version BOM/parent | Quản lý dependency và auto-configuration |
| Spring Framework | Version | Ảnh hưởng `DatabaseClient`, transaction và reactive integration |
| Spring Data Relational | Version | Ảnh hưởng mapping, dialect, repository và conversion |
| Java runtime | JDK version | Ảnh hưởng bytecode, TLS, driver và thư viện phụ thuộc |
| Pool implementation | R2DBC Pool và version nếu dùng | Ảnh hưởng acquire, validation, lifecycle và metrics |

Ví dụ một file ghi nhận môi trường:

```yaml
database:
  product: PostgreSQL
  server-version: "<version-tested>"
driver:
  artifact: "io.r2dbc:r2dbc-postgresql"
  version: "<version-tested>"
framework:
  spring-boot: "<version-tested>"
  spring-data-relational: "<managed-version>"
  r2dbc-spi: "<resolved-version>"
runtime:
  java: "<jdk-version>"
pool:
  artifact: "io.r2dbc:r2dbc-pool"
  version: "<resolved-version>"
```

Các placeholder phải được thay bằng phiên bản thật từ dependency lock/BOM và môi trường triển khai. Không tự chọn driver version mới nhất một cách độc lập với Spring Boot BOM; hãy kiểm tra dependency management và release notes của từng thành phần.

### 2.1. Spring Boot BOM và dependency convergence

Spring Boot thường quản lý phiên bản tương thích của Spring Framework, Spring Data và các thư viện tích hợp. Khi thêm driver, nên bắt đầu từ dependency được khuyến nghị cho phiên bản Boot của dự án. Nếu override version, cần có lý do và kiểm tra toàn bộ dependency tree.

Các vấn đề thường gặp khi phiên bản lệch nhau:

- Driver biên dịch với SPI version khác API mà runtime cung cấp.
- Một tính năng mapping trong Spring Data cần API chưa có trong driver cũ.
- Pool và driver có hành vi lifecycle không tương thích.
- Driver nâng phiên bản thay đổi conversion hoặc exception mapping.
- JDK hoặc TLS provider không đáp ứng yêu cầu của driver/server.

Hãy lưu kết quả dependency resolution trong build output hoặc SBOM để có thể tái tạo tổ hợp đã kiểm thử.

### 2.2. Tách khả năng được công bố và khả năng đã xác nhận

Tài liệu driver cho biết tính năng được thiết kế hỗ trợ; integration test mới xác nhận hành vi của đúng phiên bản và cấu hình đang dùng. Nên phân loại mỗi mục trong ma trận:

- **Documented:** tài liệu driver/server tuyên bố hỗ trợ.
- **Tested:** đã có test tự động chạy thành công trên tổ hợp phiên bản cụ thể.
- **Limited:** có hỗ trợ nhưng có điều kiện hoặc hạn chế đã biết.
- **Unsupported:** không hỗ trợ hoặc không đáp ứng yêu cầu.
- **Unknown:** chưa có bằng chứng đủ tin cậy.

Không biến `Unknown` thành `Supported` chỉ vì một câu lệnh đơn giản chạy được.

## 3. Kiểm tra driver có triển khai R2DBC SPI phù hợp

### 3.1. ConnectionFactory và metadata

Ứng dụng thường tạo kết nối thông qua `ConnectionFactory`. Có thể lấy metadata để kiểm tra tên driver và tên database mà driver công bố:

```java
ConnectionFactory connectionFactory = ...;

ConnectionFactoryMetadata metadata = connectionFactory.getMetadata();
log.info("R2DBC driver: {}", metadata.getName());
```

Metadata này hữu ích để ghi nhận môi trường và hỗ trợ Spring Data phân giải dialect. Tuy nhiên, tên driver hoặc metadata không phải bằng chứng rằng mọi feature đều hoạt động. Nó chỉ là thông tin nhận diện ở mức SPI.

### 3.2. Kiểm tra khả năng tạo connection và thực thi câu lệnh

Một smoke test nên xác nhận:

1. `ConnectionFactory` được tạo với URL, credential và TLS settings đúng.
2. Có thể acquire connection.
3. Có thể tạo statement và bind parameter.
4. Có thể thực thi câu lệnh và đọc `Result`.
5. Connection được đóng/trả lại đúng cách khi hoàn tất hoặc lỗi.

Ví dụ kiểm tra đơn giản:

```java
Mono<Long> databaseCheck(ConnectionFactory factory) {
    return Mono.usingWhen(
            Mono.from(factory.create()),
            connection -> Mono.from(connection
                            .createStatement("SELECT 1").execute())
                    .flatMap(result -> Mono.from(result.map(
                            (row, metadata) -> row.get(0, Long.class)))),
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close()));
}
```

`Mono.usingWhen` quản lý việc đóng connection khi publisher hoàn tất, phát lỗi hoặc bị hủy. Trong ứng dụng Spring Data thông thường, ưu tiên để `DatabaseClient`, `R2dbcEntityTemplate` hoặc Repository quản lý connection thay vì tự acquire trực tiếp.

### 3.3. Kiểm tra cancellation

Reactive API cần phản ứng đúng khi subscriber hủy subscription. Hãy kiểm tra việc hủy một truy vấn đang chạy có giải phóng hoặc đưa connection về trạng thái hợp lệ không, driver có gửi cancel request tới server không và server có tiếp tục thực thi câu lệnh trong nền hay không.

Cancellation không phải lúc nào cũng dừng ngay công việc phía server; hành vi phụ thuộc driver và database protocol. Với query dài hoặc stream kết quả lớn, cần xác nhận tài nguyên được thu hồi và không để connection bị kẹt sau khi client disconnect.

## 4. Kiểm tra dialect của Spring Data R2DBC

Spring Data R2DBC dùng `R2dbcDialect` để xử lý khác biệt giữa các hệ quản trị, chẳng hạn cách tạo bind marker, kiểu dữ liệu được hỗ trợ và các chi tiết SQL cần thiết cho mapping.

Dialect thường được phân giải từ `ConnectionFactory`:

```java
R2dbcDialect dialect = DialectResolver.getDialect(connectionFactory);
```

Việc phân giải thành công cho biết Spring Data nhận diện được một dialect tương ứng. Nó không bảo đảm mọi tính năng riêng của database đều được abstraction hóa.

### 4.1. Những gì cần kiểm tra ở dialect

- Bind marker được tạo đúng với driver, ví dụ positional hoặc named marker sau bước mở rộng của framework.
- Kiểu dữ liệu scalar và conversion mặc định phù hợp.
- Generated ID được xử lý đúng theo dialect/driver.
- SQL do Template tạo có cú pháp phù hợp với database.
- Paging, limit/offset và các thao tác update/delete được hỗ trợ.
- Các kiểu đặc thù hoặc mapping tùy chỉnh không xung đột conversion mặc định.

### 4.2. Dialect không phải bộ chuyển đổi mọi SQL

Dialect không biến mọi câu SQL của database A thành SQL tương đương của database B. Nếu ứng dụng dùng JSON operator, CTE đặc thù, full-text search, array function, stored procedure hoặc hint riêng, câu SQL đó vẫn có thể phụ thuộc hệ quản trị cụ thể.

Khi cần tính di động, ưu tiên các thao tác Spring Data hỗ trợ chung và hạn chế SQL đặc thù ở một lớp query riêng. Khi cần khai thác feature riêng, ghi rõ database mục tiêu và thêm test dành cho dialect đó.

## 5. Đánh giá mức hỗ trợ kiểu dữ liệu

Khả năng mapping kiểu dữ liệu là một trong những điểm khác biệt lớn giữa driver. Không chỉ kiểm tra kiểu Java và kiểu SQL có cùng tên; cần xác nhận cách bind, đọc, null, precision, timezone và giá trị biên.

### 5.1. Các nhóm kiểu cần kiểm tra

| Nhóm | Ví dụ SQL | Kiểu Java thường gặp | Câu hỏi cần xác nhận |
|---|---|---|---|
| Số nguyên | `SMALLINT`, `INTEGER`, `BIGINT` | `Short`, `Integer`, `Long` | Có overflow hoặc chuyển kiểu ngầm không? |
| Số thập phân | `NUMERIC`, `DECIMAL` | `BigDecimal` | Precision/scale có được giữ nguyên? |
| Boolean | `BOOLEAN`, kiểu tương đương | `Boolean` | Có khác biệt true/false và null? |
| Chuỗi | `VARCHAR`, `CHAR`, `TEXT` | `String` | Unicode, collation và giới hạn độ dài? |
| Binary | `BLOB`, `BYTEA`, `VARBINARY` | `byte[]`, `ByteBuffer` hoặc kiểu driver | Có tải toàn bộ vào memory hay hỗ trợ stream? |
| Ngày | `DATE` | `LocalDate` | Có chuyển timezone không? |
| Thời gian | `TIME`, `TIMESTAMP` | `LocalTime`, `LocalDateTime` | Có giữ độ chính xác và timezone? |
| Timestamp có timezone | `TIMESTAMPTZ` hoặc tương đương | `Instant`, `OffsetDateTime` | Driver chuẩn hóa offset thế nào? |
| UUID | `UUID` hoặc kiểu native | `UUID` | Có cần converter không? |
| JSON | `JSON`, `JSONB` hoặc text | `String`, `Json`, object tùy driver | Có bind kiểu native và đọc đúng không? |
| Array | SQL array | array/collection hoặc kiểu driver | Có hỗ trợ bind, đọc và null element? |
| Enum native | enum type riêng | enum Java hoặc `String` | Mapping theo tên, label hay ordinal? |
| Spatial | geometry/geography | kiểu driver hoặc thư viện chuyên biệt | SRID, binary format và operator? |

Không phải driver nào cũng hỗ trợ tất cả nhóm trên theo cùng cách. Với kiểu đặc thù, kiểm tra tài liệu driver và viết converter Spring Data nếu cần.

### 5.2. Kiểm tra precision và scale

Với `DECIMAL(19, 4)`, thử các giá trị:

- Giá trị nhỏ nhất và lớn nhất trong precision cho phép.
- Giá trị có đủ chữ số thập phân.
- Giá trị có nhiều chữ số hơn scale.
- Số âm, số 0 và giá trị rất nhỏ.
- Giá trị null nếu cột cho phép.

Xác nhận driver không chuyển `BigDecimal` qua `double` gây mất chính xác. Nếu database tự làm tròn hoặc từ chối scale vượt giới hạn, ghi rõ quy tắc đó trong domain validation.

### 5.3. Kiểm tra timezone và độ chính xác timestamp

Kiểm tra cách database và driver xử lý `Instant`, `OffsetDateTime`, `LocalDateTime`:

- Thời điểm có được lưu và đọc lại đúng instant không?
- Offset có được giữ hay được chuẩn hóa về UTC?
- Database lưu đến microsecond, millisecond hay precision khác?
- DST và timezone session có ảnh hưởng không?
- Driver trả về kiểu Java nào khi đọc cùng cột?

Không dùng `LocalDateTime` như một instant tuyệt đối nếu nghiệp vụ cần xác định thời điểm toàn cầu. Quy định rõ timezone ở schema, session và application.

### 5.4. Kiểm tra JSON, array và enum native

Các kiểu này thường có khác biệt lớn giữa database:

- JSON có thể được lưu dưới dạng text, JSON native hoặc binary JSON.
- Array có thể hỗ trợ nhiều chiều, null element hoặc chỉ một tập kiểu phần tử.
- Enum native có thể yêu cầu kiểu bind đặc biệt và mapping theo label.

Hãy thử cả hai chiều ghi/đọc, điều kiện truy vấn trên kiểu dữ liệu, null, dữ liệu cũ và migration thay đổi schema. Nếu dùng `R2dbcCustomConversions`, kiểm tra converter được áp dụng trong Repository/Template và không giả định nó tự áp dụng cho mọi lệnh bind thủ công của `DatabaseClient`.

## 6. Parameter binding và kiểu dữ liệu null

Driver phải chuyển bind marker và giá trị Java sang tham số phù hợp với server. Cần xác nhận:

- Named parameter có được framework mở rộng đúng thành marker của driver không?
- Positional binding có giữ đúng thứ tự không?
- `bindNull` có cần kiểu Java rõ ràng không?
- Collection/array có được mở rộng hoặc bind thành kiểu native không?
- Kiểu custom có cần converter hoặc codec riêng không?
- Giá trị lớn có vượt giới hạn protocol hoặc parameter count không?

Ví dụ dùng `DatabaseClient`:

```java
return databaseClient.sql("""
        SELECT id, email
        FROM customers
        WHERE status = :status
          AND deleted_at IS NULL
        """)
        .bind("status", status)
        .map((row, metadata) -> new CustomerSummary(
                row.get("id", Long.class),
                row.get("email", String.class)))
        .all();
```

Với tham số null, dùng API bind null có kiểu:

```java
spec.bindNull("optionalCode", String.class);
```

Không gọi `bind(name, null)` nếu API yêu cầu `bindNull`. Kiểu đích quan trọng vì server cần biết kiểu tham số khi giá trị không có dữ liệu.

### 6.1. SQL injection và identifier

Bind parameter dành cho giá trị, không dành cho tên bảng, tên cột hoặc từ khóa SQL. Nếu sort hoặc cột filter có thể chọn động, dùng enum/whitelist. Không nối trực tiếp dữ liệu request vào SQL.

### 6.2. Placeholder expansion cho collection

Một số API Spring hỗ trợ mở rộng collection thành nhiều bind marker trong mệnh đề `IN`; chi tiết phụ thuộc API và phiên bản. Kiểm tra cách xử lý list rỗng, list rất lớn và giới hạn số parameter của database. Nếu driver có kiểu array native và query phù hợp, có thể dùng cách bind array riêng; đừng giả định cú pháp của mọi hệ quản trị giống nhau.

## 7. Transaction, isolation và savepoint

Driver có thể kết nối thành công và thực hiện `SELECT` nhưng vẫn có khác biệt về transaction behavior. Hãy đánh giá các tình huống quan trọng với nghiệp vụ.

### 7.1. Commit và rollback

Kiểm tra transaction manager có thể:

- Bắt đầu transaction.
- Thực hiện nhiều statement trên cùng transaction connection.
- Commit khi publisher hoàn tất thành công.
- Rollback khi publisher phát lỗi.
- Trả connection về pool ở trạng thái hợp lệ sau commit/rollback.

Ví dụ Spring reactive transaction:

```java
@Transactional
public Mono<OrderEntity> createOrder(OrderEntity order) {
    return inventoryRepository.reserve(order)
            .then(orderRepository.save(order));
}
```

Integration test cần xác nhận nếu `reserve` thành công nhưng `save` thất bại, thay đổi inventory có rollback theo transaction hay không.

### 7.2. Isolation level

Kiểm tra database và driver hỗ trợ các isolation level mà ứng dụng yêu cầu, ví dụ `READ_COMMITTED`, `REPEATABLE_READ` hoặc `SERIALIZABLE`. Tên và hành vi thực tế có thể khác giữa sản phẩm. Cần xác nhận hiện tượng đọc bẩn, đọc không lặp lại, phantom read và serialization failure theo database.

Không giả định cùng tên isolation có hành vi giống hệt ở mọi hệ quản trị. Hãy kiểm tra tài liệu sản phẩm và viết test concurrency cho nghiệp vụ quan trọng.

### 7.3. Savepoint và nested transaction

Nếu ứng dụng cần savepoint hoặc nested transaction semantics, kiểm tra driver và database có hỗ trợ API/cú pháp tương ứng hay không. Không suy ra hỗ trợ nested transaction chỉ từ việc `@Transactional` hoạt động.

### 7.4. Concurrent statement trên một connection

Trong reactive transaction, nhiều repository call có thể cùng tham gia một transaction và dùng chung connection. Một số driver không cho phép nhiều statement thực thi đồng thời trên cùng connection. Nếu cần thứ tự, dùng `concatMap` hoặc nối publisher tuần tự; nếu cần song song, đánh giá việc tách transaction/connection và hệ quả atomicity.

## 8. Generated values, identity và RETURNING

Ứng dụng thường cần nhận ID hoặc giá trị do database sinh sau insert. Khả năng này phụ thuộc SQL dialect, driver và server.

Hãy thử:

- Identity/sequence key được trả về có đúng kiểu Java không?
- Có thể lấy nhiều generated values cùng lúc không?
- Trigger có sửa giá trị trước khi trả kết quả không?
- Generated/computed columns có xuất hiện trong result không?
- Driver hỗ trợ `RETURNING` hoặc cơ chế generated values tương đương không?
- `save` trả về entity có chứa giá trị mới hay cần select lại?

Ví dụ PostgreSQL có thể sử dụng:

```sql
INSERT INTO customers (email)
VALUES (:email)
RETURNING id, email, created_at;
```

`RETURNING` là tính năng/cú pháp theo database, không phải bảo đảm portable cho mọi hệ quản trị. Nếu ứng dụng dùng nhiều database, cần abstraction riêng hoặc triển khai query theo dialect. Nếu chỉ cần generated ID, kiểm tra hỗ trợ mặc định của Spring Data R2DBC trước khi tự viết SQL.

## 9. CLOB/BLOB, streaming và dữ liệu lớn

Với dữ liệu lớn như file, tài liệu hoặc binary payload, không chỉ kiểm tra có đọc/ghi được hay không. Cần biết driver tải toàn bộ dữ liệu vào bộ nhớ hay cung cấp streaming, giới hạn kích thước, cách xử lý cancellation và thời gian giữ connection.

Các câu hỏi cần trả lời:

- Có hỗ trợ kiểu LOB của database không?
- Dữ liệu được biểu diễn bằng `byte[]`, `ByteBuffer`, `Blob`, `Clob` hoặc kiểu riêng nào?
- Có thể stream theo chunk hay phải materialize toàn bộ?
- Khi subscriber hủy giữa chừng, tài nguyên LOB và connection có được giải phóng không?
- Có giới hạn kích thước parameter/result không?
- Có khác biệt giữa lưu binary trực tiếp và lưu object storage ngoài database không?

Nếu driver chỉ hỗ trợ materialize dữ liệu lớn, cần giới hạn kích thước và đánh giá memory footprint. Không giữ connection lâu trong khi gửi file chậm tới HTTP client nếu có thể tách quá trình đọc/stream hoặc dùng storage chuyên biệt.

## 10. Connection pool, TLS và vận hành

Một driver được hỗ trợ ở local chưa chắc đáp ứng yêu cầu vận hành production. Cần kiểm tra:

- Tạo và đóng connection đúng cách.
- Acquire timeout và connection validation.
- Idle/lifetime eviction.
- Phản ứng khi database restart hoặc network bị ngắt.
- TLS mode, certificate validation và hostname verification.
- Authentication method, secret rotation và credential refresh.
- Metrics cho active, idle, pending connection và acquire latency.
- Logging/observability không làm lộ credential hoặc query parameter nhạy cảm.
- Failover, DNS change hoặc endpoint chuyển vùng nếu kiến trúc cần.

### 10.1. Pool không sửa được driver không ổn định

Pool quản lý connection, nhưng không khắc phục được lỗi giao thức, rò rỉ tài nguyên trong driver hoặc mapping sai kiểu. Nếu connection thường xuyên bị đánh dấu invalid, hãy xem log driver, lỗi server và release notes trước khi tăng pool.

### 10.2. Failover và reconnect

Khi database failover hoặc connection bị ngắt, driver/pool cần phát lỗi có thể hiểu được và không trả connection hỏng cho request khác. Kiểm tra hành vi khi:

- Server restart.
- Network timeout hoặc reset.
- Connection idle lâu hơn server timeout.
- DNS/endpoint thay đổi.
- Credential hết hạn hoặc bị rotate.

Không retry mọi lỗi vô điều kiện. Với thao tác ghi, cần xử lý trường hợp client mất kết nối sau khi database đã commit nhưng trước khi nhận acknowledgement; idempotency key hoặc kiểm tra trạng thái có thể cần thiết.

## 11. Khả năng SQL và tính năng riêng của hệ quản trị

R2DBC SPI cung cấp cách thực thi statement chung, nhưng SQL vẫn phụ thuộc database. Hãy lập danh sách các tính năng thực tế mà ứng dụng sử dụng:

- `LIMIT/OFFSET` hoặc cú pháp phân trang tương đương.
- CTE và recursive CTE.
- Window functions.
- `RETURNING` hoặc generated values.
- `INSERT ... ON CONFLICT`, `MERGE` hoặc upsert tương đương.
- JSON/JSONB operators.
- Array, enum native và spatial types.
- Full-text search.
- Stored procedure/function.
- Advisory lock, row lock và locking clause.
- Partial index, expression index và generated columns.

Đánh giá cả server lẫn driver. Server có thể hỗ trợ một cú pháp nhưng driver vẫn cần hỗ trợ bind/đọc kiểu kết quả liên quan. Spring Data dialect có thể không trừu tượng hóa feature đó; khi đó SQL tùy chỉnh vẫn có thể dùng được nhưng làm tăng phụ thuộc vào database cụ thể.

### 11.1. Repository derivation không bao phủ mọi SQL

Derived query method phù hợp với truy vấn theo property và các predicate phổ biến. Nếu cần CTE, window function hoặc operator đặc thù, dùng `@Query`, `DatabaseClient` hoặc custom repository. Đây là giới hạn của abstraction truy vấn, không nhất thiết là giới hạn của driver.

### 11.2. Đánh giá upsert

Không có một cú pháp upsert duy nhất được mọi database hỗ trợ. Nếu nghiệp vụ phụ thuộc upsert nguyên tử, chọn cách triển khai theo dialect và kiểm thử cạnh tranh. Tránh mẫu `SELECT` kiểm tra tồn tại rồi `INSERT` vì hai request có thể cùng vượt qua bước kiểm tra; unique constraint vẫn cần thiết.

## 12. Exception mapping và observability

Driver chuyển lỗi server/protocol thành exception ở tầng R2DBC; Spring có thể chuyển một số lỗi thành `DataAccessException` phù hợp. Cần kiểm tra các nhóm lỗi:

- Unique/primary key violation.
- Foreign key violation.
- Not-null/check constraint violation.
- Deadlock và lock timeout.
- Serialization failure.
- Connection refused, reset hoặc timeout.
- Authentication/TLS failure.
- Cancelled query.
- Conversion hoặc unsupported data type.

Đánh giá xem exception có giữ SQL state/vendor code và cause hay không, vì Service có thể cần phân biệt duplicate key với các lỗi integrity khác. Không viết logic nghiệp vụ dựa trên chuỗi message của driver nếu có mã lỗi ổn định hơn.

Metrics và tracing nên cho phép quan sát:

- Query latency theo nhóm query.
- Connection acquire latency và pending borrowers.
- Số lỗi theo loại.
- Số lần timeout/cancel.
- Transaction duration và rollback.
- Số hàng trả về và kích thước payload nếu cần.

## 13. Ma trận kiểm thử khả năng hỗ trợ

Một ma trận có thể được tổ chức theo tính năng và bằng chứng:

| Nhóm | Thử nghiệm tối thiểu | Kết quả cần ghi |
|---|---|---|
| Kết nối | Acquire, execute `SELECT 1`, close | Pass/fail, latency, driver metadata |
| CRUD | Insert, select, update, delete | Mapping và số hàng bị ảnh hưởng |
| Bind parameter | String, number, null, collection | Kiểu bind và giới hạn |
| Generated ID | Insert không cung cấp ID | ID trả về và kiểu Java |
| Default | Bỏ cột, explicit null, `DEFAULT` | Giá trị lưu thực tế |
| Data types | Decimal, temporal, UUID, JSON, array, binary | Round-trip và precision |
| Transactions | Commit, rollback, multi-statement | Trạng thái cuối trong database |
| Isolation | Hai transaction đọc/ghi đồng thời | Hiện tượng quan sát được |
| Concurrency | Nhiều query và nhiều request | Pool, latency, throughput |
| Cancellation | Hủy query/stream giữa chừng | Resource cleanup và server behavior |
| Large result | Đọc nhiều hàng/LOB | Memory, backpressure, connection duration |
| Error mapping | Constraint, timeout, disconnect | Exception type, SQL state, cause |
| Failover | Restart/network reset | Recovery, lỗi và retry behavior |
| Security | TLS, auth, secret rotation | Handshake, certificate, reconnect |
| Spring mapping | Repository, Template, converters | Entity mapping và generated values |

Mỗi dòng cần ghi phiên bản database, driver, Spring Boot/Data, JDK, cấu hình và môi trường test. Nếu một test chỉ chạy trên H2 trong khi production dùng database khác, nó không chứng minh driver production hỗ trợ tính năng đó.

## 14. Xây dựng integration test đúng môi trường

### 14.1. Dùng database tương ứng với production

Test với database in-memory có ích cho một số logic nhưng không thay thế integration test trên hệ quản trị thực tế. Khác biệt có thể xuất hiện ở SQL syntax, data type, generated keys, transaction isolation, collation và exception mapping.

Có thể dùng container database trong CI để tạo môi trường lặp lại. Container image nên pin version; không dùng tag thay đổi theo thời gian nếu cần kết quả có thể tái tạo.

### 14.2. Test qua Spring Data và test qua SPI

Nên có hai lớp thử nghiệm:

- **Driver/SPI test:** xác nhận hành vi thấp nhất như connection, bind, result, cancellation và transaction.
- **Spring Data integration test:** xác nhận repository, `R2dbcEntityTemplate`, dialect, custom conversions, auditing, generated values và mapping entity.

Nếu test SPI thành công nhưng repository mapping thất bại, vấn đề có thể nằm ở Spring Data dialect hoặc metadata entity. Nếu test SPI đã thất bại, cần tập trung vào driver/server/configuration trước.

### 14.3. Ví dụ kiểm thử repository reactive

```java
@DataR2dbcTest
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void insertsAndReadsCustomer() {
        CustomerEntity customer = new CustomerEntity(
                null, "an@example.com", "An");

        StepVerifier.create(repository.save(customer)
                .flatMap(saved -> repository.findById(saved.id())))
                .assertNext(found -> {
                    assertThat(found.id()).isNotNull();
                    assertThat(found.email()).isEqualTo("an@example.com");
                })
                .verifyComplete();
    }
}
```

Đây là ví dụ cấu trúc test; cần cung cấp schema, `ConnectionFactory` và test configuration đúng database mục tiêu. Với nhiều database, có thể chạy cùng bộ test contract trên từng driver bằng profile hoặc pipeline CI riêng.

### 14.4. Kiểm thử concurrency và transaction

Các bài test quan trọng nên có hai hoặc nhiều connection/transaction thực sự để mô phỏng cạnh tranh. Không dùng một mock repository để kết luận database isolation hoặc optimistic locking hoạt động đúng.

Kiểm tra cả kết quả dữ liệu cuối cùng, không chỉ exception. Một thao tác phát lỗi nhưng một phần dữ liệu đã commit ngoài transaction vẫn có thể gây lỗi nghiệp vụ.

## 15. Quy trình đánh giá một database/driver mới

Có thể tiến hành theo các bước sau:

1. Liệt kê các tính năng SQL và data type mà ứng dụng thực sự sử dụng.
2. Xác định database product/version và driver R2DBC cụ thể.
3. Kiểm tra tài liệu driver, release notes, SPI version và ma trận tương thích với Spring Boot/Spring Data.
4. Khóa dependency bằng BOM hoặc version catalog; ghi lại dependency tree.
5. Tạo `ConnectionFactory`, kiểm tra metadata và chạy smoke test.
6. Xác nhận dialect được Spring Data phân giải đúng.
7. Thử CRUD, bind parameter, null và custom conversion.
8. Thử identity, default, generated column, trigger và giá trị trả về.
9. Thử transaction, rollback, isolation và concurrency.
10. Thử cancellation, large result, LOB và pool saturation nếu workload cần.
11. Thử TLS, authentication, reconnect, failover và observability.
12. Chạy integration test trên đúng server version trong CI.
13. Ghi từng tính năng thành Documented, Tested, Limited, Unsupported hoặc Unknown.
14. Quyết định chấp nhận, chấp nhận có điều kiện hoặc không dùng dựa trên yêu cầu bắt buộc và rủi ro còn lại.

## 16. Tiêu chí ra quyết định

Một driver có thể phù hợp cho ứng dụng CRUD thông thường nhưng chưa phù hợp cho workload streaming LOB, JSON native hoặc transaction phức tạp. Không nên đánh giá “hỗ trợ tốt” bằng một điểm số chung mà không xét mức quan trọng của từng tính năng.

Có thể phân loại tiêu chí:

### Bắt buộc

- Kết nối ổn định với database version đang dùng.
- Spring Boot/Spring Data nhận diện được driver và dialect.
- CRUD, bind parameter, kiểu dữ liệu cốt lõi và transaction cần thiết hoạt động đúng.
- Pool, timeout, TLS và authentication đáp ứng yêu cầu production.
- Các test concurrency và rollback quan trọng vượt qua.

### Quan trọng nhưng có thể có phương án thay thế

- JSON/array/native enum.
- Generated values ngoài ID.
- CTE/window function hoặc tính năng riêng.
- Streaming LOB và cancellation.
- Metrics chi tiết hoặc failover nâng cao.

Nếu thiếu một tính năng quan trọng nhưng có thể thay bằng SQL riêng, converter hoặc một service khác, ghi rõ chi phí và giới hạn. Nếu thiếu tính năng bắt buộc như transaction behavior hoặc kiểu dữ liệu cốt lõi, không nên chấp nhận chỉ vì smoke test thành công.

### Vận hành và vòng đời hỗ trợ

Đánh giá tốc độ phát hành bản vá, mức hoạt động của dự án driver, cách báo lỗi bảo mật, release cadence, tài liệu, ví dụ và khả năng hỗ trợ production. Một driver có tính năng đầy đủ nhưng không còn được duy trì có thể là rủi ro dài hạn.

## 17. Những hiểu lầm thường gặp

### Database có giao thức native là tự động có R2DBC

R2DBC thường được triển khai bởi driver phía Java. Server không nhất thiết triển khai SPI. Cần chọn driver phù hợp với database.

### Kết nối được nghĩa là mọi feature đều được hỗ trợ

Kết nối và `SELECT 1` chỉ xác nhận đường kết nối cơ bản. Nó không kiểm tra transaction, kiểu dữ liệu, cancellation, generated values hay pool behavior.

### Có R2DBC driver nghĩa là Spring Data hỗ trợ mọi tính năng

Driver triển khai SPI; Spring Data còn cần dialect và mapping phù hợp. SQL đặc thù vẫn có thể cần `DatabaseClient` hoặc custom repository.

### Driver reactive làm database không bị giới hạn tài nguyên

Non-blocking I/O giảm việc chiếm thread khi chờ I/O, nhưng database vẫn có giới hạn connection, CPU, I/O, lock và memory. Cần giới hạn concurrency và tối ưu query.

### H2 test pass chứng minh PostgreSQL/MySQL/SQL Server hoạt động giống nhau

Mỗi database có SQL, type system, transaction semantics và driver khác nhau. Test production dialect trên database mục tiêu.

### Spring Data dialect tự chuyển mọi câu SQL riêng

Dialect hỗ trợ những khác biệt mà framework biết. SQL tự viết vẫn phụ thuộc cú pháp và tính năng của database.

### Mọi generated value đều có trong entity trả về từ save

Driver/dialect có thể chỉ trả ID hoặc một tập giá trị. Kiểm tra result thực tế; đọc lại entity nếu cần.

### Retry giải quyết mọi lỗi connection

Retry không sửa được lỗi schema, mapping, authentication hoặc thao tác ghi không idempotent. Cần phân loại lỗi và giới hạn retry.

## 18. Checklist đánh giá

- [ ] Đã ghi chính xác database product và server version.
- [ ] Đã ghi driver artifact/version và R2DBC SPI version.
- [ ] Spring Boot, Spring Framework, Spring Data và Java runtime nằm trong tổ hợp đã xác nhận.
- [ ] Dependency tree không có SPI/driver version conflict ngoài dự kiến.
- [ ] `ConnectionFactory` khởi tạo và metadata được nhận diện đúng.
- [ ] Spring Data phân giải đúng dialect.
- [ ] CRUD và parameter binding hoạt động trên database mục tiêu.
- [ ] Null, collection, decimal, temporal, UUID, JSON/array và binary được kiểm tra theo nhu cầu.
- [ ] Generated ID, default, trigger và computed column được kiểm tra.
- [ ] Transaction commit/rollback và isolation đáp ứng nghiệp vụ.
- [ ] Cancellation, streaming và LOB được kiểm tra nếu workload cần.
- [ ] Pool, timeout, TLS, authentication và reconnect đáp ứng vận hành.
- [ ] Exception mapping giữ đủ thông tin để xử lý và chẩn đoán.
- [ ] SQL đặc thù và các giới hạn portability đã được ghi nhận.
- [ ] Integration test chạy trên đúng database/driver version trong CI.
- [ ] Từng feature được đánh dấu Documented, Tested, Limited, Unsupported hoặc Unknown.

## 19. Kết luận kỹ thuật

Đánh giá mức hỗ trợ R2DBC cần xem database, driver, SPI, Spring Data dialect và cấu hình vận hành như một tổ hợp. Một driver có thể cung cấp kết nối reactive nhưng vẫn có giới hạn về kiểu dữ liệu, generated values, cancellation, transaction hoặc các tính năng riêng của database. Ngược lại, một tính năng server có sẵn chưa chắc được driver hoặc Spring Data ánh xạ thuận tiện.

Hãy bắt đầu từ workload và tính năng ứng dụng cần, lập ma trận phiên bản, kiểm tra tài liệu driver, sau đó xác nhận bằng integration test trên database thật. Ghi lại cả những điểm được hỗ trợ, giới hạn và chưa xác minh. Cách đánh giá dựa trên bằng chứng này giúp chọn driver phù hợp, tránh nhầm lẫn giữa khả năng của server và abstraction của framework, đồng thời giảm rủi ro khi nâng cấp hoặc thay đổi hệ quản trị.

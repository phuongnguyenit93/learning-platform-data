# Đọc `Row`, `RowMetadata` và ánh xạ kết quả thủ công

Khi dùng SQL trực tiếp với Spring Data Relational R2DBC, ứng dụng thường cần tự chuyển kết quả database thành DTO, projection hoặc cấu trúc dữ liệu nghiệp vụ. Hai abstraction quan trọng ở tầng R2DBC SPI là `Row` và `RowMetadata`: `Row` cung cấp giá trị của một hàng kết quả, còn `RowMetadata` mô tả các cột trong result set. Spring `DatabaseClient` đưa hai đối tượng này vào callback `map((row, metadata) -> ...)`, giúp ánh xạ từng hàng ngay trong reactive pipeline.

Ánh xạ thủ công phù hợp khi câu SQL có join, aggregate, alias phức tạp hoặc kết quả không khớp trực tiếp với một entity. Cần đọc đúng kiểu dữ liệu, xử lý SQL `NULL`, dùng alias ổn định, không giữ `Row` sau callback và để publisher quản lý vòng đời kết quả. `RowMetadata` hữu ích để kiểm tra cấu trúc cột và chẩn đoán mapping; nó không phải dữ liệu của hàng và cũng không tự chuyển đổi giá trị.

## 1. `Row` và `RowMetadata` là gì?

R2DBC SPI biểu diễn kết quả của một câu truy vấn bằng `Result`. Khi result chứa các hàng dữ liệu, ứng dụng có thể ánh xạ từng hàng qua `Row` cùng metadata tương ứng.

| Kiểu | Vai trò | Dùng khi nào? |
| --- | --- | --- |
| `Result` | Đại diện kết quả thực thi một statement | Tiêu thụ rows hoặc số hàng bị ảnh hưởng |
| `Row` | Cung cấp giá trị của một hàng cụ thể | Đọc cột theo tên hoặc vị trí và kiểu Java mong muốn |
| `RowMetadata` | Mô tả các cột của result set | Kiểm tra tên cột, kiểu, metadata và thứ tự cột |
| `ColumnMetadata` | Mô tả một cột trong result set | Xem tên, kiểu Java/native type và precision/scale nếu driver cung cấp |

Ví dụ một query:

```sql
SELECT id, email, display_name
FROM customer
WHERE active = TRUE;
```

Mỗi hàng trả về có một `Row`. Metadata mô tả các cột `id`, `email`, `display_name`, trong khi `Row` chứa giá trị cụ thể như `42`, `an@example.com`, `An Nguyen`.

`RowMetadata` thường giống nhau cho các hàng của cùng một result set. Không nên coi metadata là dữ liệu của một customer cụ thể; nó mô tả hình dạng kết quả.

## 2. Ánh xạ thủ công bằng `DatabaseClient`

`DatabaseClient` là API của Spring Framework để thực thi SQL reactive. Phương thức `map` nhận callback với `Row` và `RowMetadata`, sau đó trả về một `FetchSpec<T>` có thể tiêu thụ bằng `all()`, `one()` hoặc `first()`.

Ví dụ:

```java
public Flux<CustomerSummary> findActiveCustomers() {
    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE active = :active
            ORDER BY id
            """)
            .bind("active", true)
            .map((row, metadata) -> new CustomerSummary(
                    row.get("id", Long.class),
                    row.get("email", String.class),
                    row.get("display_name", String.class)))
            .all();
}
```

Trong ví dụ, callback nhận từng hàng và tạo `CustomerSummary`. `all()` trả `Flux<CustomerSummary>`, vì vậy dữ liệu được phát theo reactive stream. Không cần tự gọi `subscribe()` hoặc lưu các `Row` vào một collection.

Ánh xạ được thực hiện ngay trong callback. Đây là nơi thích hợp để đọc các giá trị cần thiết, kiểm tra null và tạo DTO/entity mà ứng dụng sở hữu.

## 3. Đọc cột theo tên bằng `Row.get(String, Class<T>)`

`Row` cung cấp cách đọc giá trị theo tên cột:

```java
Long id = row.get("id", Long.class);
String email = row.get("email", String.class);
BigDecimal balance = row.get("balance", BigDecimal.class);
```

Tham số thứ nhất là tên cột hoặc alias trong result set; tham số thứ hai là kiểu Java mong muốn. Driver chịu trách nhiệm cung cấp giá trị tương thích với kiểu được yêu cầu.

Đọc theo tên dễ hiểu và ít phụ thuộc thứ tự cột trong câu `SELECT`. Tuy nhiên, tên phải khớp với metadata của result set. Với join có nhiều cột trùng tên như `id`, nên đặt alias riêng để tránh mơ hồ.

## 4. Đọc cột theo vị trí bằng `Row.get(int, Class<T>)`

Có thể đọc theo chỉ số cột:

```java
Long id = row.get(0, Long.class);
String email = row.get(1, String.class);
String displayName = row.get(2, String.class);
```

Index của `Row` bắt đầu từ 0 và theo thứ tự cột trong result set. Cách này có thể hữu ích trong mapping hiệu năng cao hoặc khi tên cột không thuận tiện, nhưng code phụ thuộc chặt vào thứ tự `SELECT`.

Ví dụ nếu query thay đổi thứ tự:

```sql
SELECT email, id, display_name
FROM customer;
```

mapping theo index cũ sẽ đọc nhầm cột. Nếu dùng index, hãy giữ `SELECT` và mapping cạnh nhau, viết test cho thứ tự cột và tránh `SELECT *`.

## 5. Chọn kiểu Java tương thích với cột SQL

Kiểu được truyền vào `row.get(...)` cần tương thích với kiểu dữ liệu mà driver hỗ trợ. Một số kiểu thường gặp:

| Kiểu SQL phổ biến | Kiểu Java thường dùng |
| --- | --- |
| `SMALLINT` | `Short` hoặc kiểu số tương thích do driver hỗ trợ |
| `INTEGER` | `Integer` |
| `BIGINT` | `Long` |
| `NUMERIC` / `DECIMAL` | `BigDecimal` |
| `BOOLEAN` | `Boolean` |
| `VARCHAR` / `TEXT` | `String` |
| `UUID` | `UUID` nếu driver hỗ trợ |
| `DATE` | `LocalDate` |
| `TIME` | `LocalTime` |
| `TIMESTAMP` | Thường là `LocalDateTime` |
| `TIMESTAMP WITH TIME ZONE` | Kiểu thời gian có offset phù hợp với driver, thường `OffsetDateTime` trên PostgreSQL R2DBC |
| `BINARY` / `VARBINARY` | `byte[]` hoặc kiểu buffer theo driver |

Bảng trên là hướng dẫn phổ biến, không phải cam kết chuyển đổi giống nhau trên mọi database. Kiểu SQL, driver, codec và phiên bản R2DBC quyết định kiểu Java được hỗ trợ. Hãy kiểm tra tài liệu driver và chạy integration test với đúng database production.

Không yêu cầu `Long.class` khi driver chỉ cung cấp `Integer` nếu driver không hỗ trợ chuyển đổi đó. Nếu cần chuyển đổi số, đọc kiểu gốc tương thích rồi chuyển rõ ràng trong Java, đồng thời kiểm tra overflow.

## 6. SQL `NULL` và giá trị Java `null`

Một cột SQL có thể chứa `NULL`. Khi đọc bằng `row.get(...)`, giá trị trả về có thể là Java `null`. Vì vậy, với cột nullable, hãy dùng wrapper/reference type thay vì primitive.

Ví dụ:

```java
Integer age = row.get("age", Integer.class);
Boolean verified = row.get("verified", Boolean.class);
OffsetDateTime deletedAt = row.get("deleted_at", OffsetDateTime.class);
```

Nếu cột có SQL `NULL`, biến tương ứng có thể là `null`. Không dùng `int`, `boolean`, `long` làm kiểu đích trực tiếp vì primitive không thể biểu diễn null.

DTO có thể biểu diễn nullable field bằng wrapper:

```java
public record CustomerProfile(
        Long id,
        String email,
        Integer age,
        Boolean verified,
        OffsetDateTime deletedAt
) {
}
```

Nếu domain yêu cầu giá trị không null, kiểm tra và phát lỗi mapping rõ ràng thay vì để `NullPointerException` xuất hiện ở một đoạn code xa callback.

## 7. Viết helper đọc giá trị bắt buộc và tùy chọn

Có thể tạo helper nhỏ để thể hiện rõ nullability:

```java
private static <T> T required(
        Row row,
        String column,
        Class<T> type) {

    T value = row.get(column, type);
    if (value == null) {
        throw new IllegalStateException(
                "Required database column is NULL: " + column);
    }
    return value;
}

private static <T> T nullable(
        Row row,
        String column,
        Class<T> type) {

    return row.get(column, type);
}
```

Sử dụng:

```java
CustomerSummary customer = new CustomerSummary(
        required(row, "id", Long.class),
        required(row, "email", String.class),
        nullable(row, "display_name", String.class));
```

Helper `required` giúp lỗi schema/data không bị biến thành null âm thầm. Trong ứng dụng thực tế, exception có thể là một mapping exception riêng để log và xử lý nhất quán.

Không đưa giá trị cột nhạy cảm vào thông báo lỗi. Tên cột thường đủ để chẩn đoán; không log toàn bộ row.

## 8. Dùng `RowMetadata` để xem cấu trúc result set

`RowMetadata` cung cấp thông tin về các cột, ví dụ danh sách metadata, tra cứu theo index hoặc tên và kiểm tra cột có tồn tại.

Ví dụ log tên và kiểu Java của cột:

```java
private void logColumns(RowMetadata metadata) {
    metadata.getColumnMetadatas().forEach(column ->
            log.debug("column={}, javaType={}",
                    column.getName(),
                    column.getJavaType().getName()));
}
```

Một số metadata còn cung cấp kiểu native, precision, scale và thông tin nullability tùy driver. Không phải mọi database/driver đều cung cấp mọi thuộc tính với cùng mức độ chi tiết.

`RowMetadata` hữu ích khi:

- Chẩn đoán sai alias hoặc tên cột.
- Kiểm tra kết quả query tùy biến.
- Xây mapping linh hoạt dựa trên projection đã biết.
- Ghi nhận kiểu cột trong môi trường debug.
- Xác minh một query trả đúng shape mà code mong đợi.

Không nên log metadata cho mọi row trong production nếu không cần thiết. Metadata thường lặp lại cho cùng result set; log một lần hoặc chỉ bật ở mức debug.

## 9. Tra cứu `ColumnMetadata` theo tên hoặc index

Có thể lấy metadata của một cột cụ thể:

```java
ColumnMetadata idColumn = metadata.getColumnMetadata("id");
ColumnMetadata firstColumn = metadata.getColumnMetadata(0);

String columnName = idColumn.getName();
Class<?> javaType = idColumn.getJavaType();
Type nativeType = idColumn.getType();
```

Tên các method và kiểu metadata cần khớp với phiên bản R2DBC SPI đang dùng. `getType()` mô tả kiểu theo abstraction SPI; `getJavaType()` cho biết kiểu Java mà driver liên kết với cột. Metadata native có thể là kiểu riêng của driver.

Nếu cần kiểm tra cột có tồn tại:

```java
if (!metadata.contains("display_name")) {
    throw new IllegalStateException("Missing display_name column");
}
```

`contains` và tra cứu theo tên có semantics phụ thuộc metadata/driver, đặc biệt với identifier được quote hoặc tên cột viết hoa. Dùng alias chữ thường đơn giản và thống nhất để giảm vấn đề casing.

## 10. Dùng metadata để kiểm tra projection mong đợi

Với query tùy biến, có thể xác minh các cột bắt buộc trước khi map:

```java
private void requireColumns(RowMetadata metadata, String... names) {
    for (String name : names) {
        if (!metadata.contains(name)) {
            throw new IllegalStateException(
                    "Query result is missing column: " + name);
        }
    }
}
```

Sau đó:

```java
return databaseClient.sql("""
        SELECT id, email, display_name
        FROM customer
        WHERE id = :id
        """)
        .bind("id", id)
        .map((row, metadata) -> {
            requireColumns(metadata, "id", "email", "display_name");
            return new CustomerSummary(
                    required(row, "id", Long.class),
                    required(row, "email", String.class),
                    nullable(row, "display_name", String.class));
        })
        .one();
```

Đối với SQL cố định trong code, metadata shape thường được kiểm soát bằng query và integration test. Runtime validation hữu ích hơn với query được tạo từ nhiều projection hợp lệ hoặc SQL do cấu hình nội bộ quyết định. Không cần lặp lại kiểm tra metadata nặng ở mọi row nếu đã xác minh cấu trúc một lần cho result set.

## 11. Ánh xạ DTO từ kết quả join

Một truy vấn join có thể trả cột từ nhiều bảng. Nếu cả hai bảng đều có `id`, `name`, cần alias để tránh trùng tên:

```sql
SELECT
    c.id AS customer_id,
    c.email AS customer_email,
    c.display_name AS customer_name,
    o.id AS order_id,
    o.order_number AS order_number,
    o.total AS order_total
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE c.id = :customerId
ORDER BY o.id;
```

DTO:

```java
public record CustomerOrderRow(
        Long customerId,
        String customerEmail,
        String customerName,
        Long orderId,
        String orderNumber,
        BigDecimal orderTotal
) {
}
```

Mapping:

```java
return databaseClient.sql(sql)
        .bind("customerId", customerId)
        .map((row, metadata) -> new CustomerOrderRow(
                required(row, "customer_id", Long.class),
                required(row, "customer_email", String.class),
                nullable(row, "customer_name", String.class),
                nullable(row, "order_id", Long.class),
                nullable(row, "order_number", String.class),
                nullable(row, "order_total", BigDecimal.class)))
        .all();
```

Vì dùng `LEFT JOIN`, các cột phía `orders` có thể null khi customer chưa có order. Mapping phải dùng kiểu nullable cho `orderId`, `orderNumber` và `orderTotal`. Không dùng primitive `long` hoặc `double` cho các cột đó.

## 12. Gộp nhiều hàng join thành một aggregate

Query join một customer với nhiều order có thể phát nhiều hàng lặp thông tin customer. Có thể ánh xạ mỗi hàng thành một row DTO rồi gom thành aggregate:

```java
public record CustomerWithOrderRow(
        Long customerId,
        String customerEmail,
        Long orderId,
        String orderNumber
) {
}

public record CustomerWithOrders(
        Long customerId,
        String email,
        List<OrderSummary> orders
) {
}
```

Nếu query được sắp xếp theo customer ID, có thể dùng `collectMultimap` hoặc một reducer để nhóm dữ liệu. Ví dụ đơn giản cho tập dữ liệu có giới hạn:

```java
return findCustomerOrderRows(customerId)
        .collectList()
        .flatMap(rows -> {
            if (rows.isEmpty()) {
                return Mono.empty();
            }

            CustomerWithOrderRow first = rows.get(0);
            List<OrderSummary> orders = rows.stream()
                    .filter(row -> row.orderId() != null)
                    .map(row -> new OrderSummary(
                            row.orderId(), row.orderNumber()))
                    .toList();

            return Mono.just(new CustomerWithOrders(
                    first.customerId(), first.customerEmail(), orders));
        });
```

`collectList()` gom toàn bộ kết quả vào bộ nhớ. Cách này phù hợp khi một customer có số order được giới hạn. Với kết quả rất lớn, dùng grouping theo thứ tự hoặc batch có giới hạn; không gom không giới hạn chỉ để tạo object aggregate.

## 13. `RowMetadata` và tên cột có alias

Khi dùng alias:

```sql
SELECT c.id AS customer_id, o.id AS order_id
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id;
```

mapping nên dùng đúng alias:

```java
Long customerId = row.get("customer_id", Long.class);
Long orderId = row.get("order_id", Long.class);
```

Không dựa vào tên cột gốc nếu query đã đặt alias. Với database có quy tắc chuyển casing của identifier, alias không quote có thể được chuyển thành chữ thường hoặc chữ hoa. Dùng alias đơn giản không quote và kiểm tra metadata trong integration test.

Tránh `SELECT *` trong query join vì:

- Có thể có nhiều cột cùng tên.
- Thêm cột vào bảng có thể làm thay đổi shape result.
- Mapping theo index dễ bị lệch.
- Ứng dụng đọc nhiều dữ liệu hơn cần thiết.

Liệt kê rõ cột và alias giúp mapping ổn định hơn.

## 14. Ánh xạ kết quả aggregate

Query aggregate thường trả một hàng với kiểu số hoặc giá trị nullable:

```sql
SELECT COUNT(*) AS customer_count,
       AVG(age) AS average_age,
       MAX(created_at) AS latest_customer
FROM customer
WHERE active = :active;
```

DTO:

```java
public record CustomerStatistics(
        Long customerCount,
        BigDecimal averageAge,
        OffsetDateTime latestCustomer
) {
}
```

Mapping:

```java
return databaseClient.sql(sql)
        .bind("active", true)
        .map((row, metadata) -> new CustomerStatistics(
                row.get("customer_count", Long.class),
                row.get("average_age", BigDecimal.class),
                row.get("latest_customer", OffsetDateTime.class)))
        .one();
```

`COUNT(*)` thường trả số không khi không có hàng, trong khi `AVG` và `MAX` có thể trả SQL `NULL`. Hãy dùng wrapper/reference type cho aggregate có thể null và kiểm tra kiểu mà driver cung cấp. Không mặc định mọi database trả `COUNT` cùng một kiểu Java.

## 15. Chọn `all()`, `one()` hay `first()`

Sau khi gọi `map`, `DatabaseClient` cho phép chọn cách tiêu thụ kết quả:

| API | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `all()` | `Flux<T>` | Phát tất cả hàng đã map |
| `one()` | `Mono<T>` | Mong đợi tối đa một hàng; nhiều hàng là lỗi cardinality |
| `first()` | `Mono<T>` | Lấy hàng đầu tiên nếu có và không yêu cầu nguồn chỉ có một hàng |

Ví dụ:

```java
Mono<CustomerSummary> byId = databaseClient.sql(
                "SELECT id, email FROM customer WHERE id = :id")
        .bind("id", id)
        .map((row, metadata) -> new CustomerSummary(
                row.get("id", Long.class),
                row.get("email", String.class)))
        .one();
```

Nếu query có thể trả nhiều hàng nhưng code chỉ cần hàng đầu tiên, dùng `first()` cùng `ORDER BY` rõ ràng. Không dùng `one()` cho query không bảo đảm uniqueness. Ngược lại, nếu nghiệp vụ yêu cầu đúng một hàng, hãy giữ `one()` để phát hiện dữ liệu bất thường thay vì âm thầm bỏ các hàng còn lại.

## 16. Mapping thủ công bằng R2DBC SPI `Result.map`

Khi làm việc trực tiếp với R2DBC SPI, `Statement.execute()` phát `Result`. Có thể map từng result:

```java
Statement statement = connection.createStatement("""
        SELECT id, email, display_name
        FROM customer
        WHERE active = $1
        ORDER BY id
        """);

statement.bind(0, true);

Flux<CustomerSummary> customers = Flux.from(statement.execute())
        .concatMap(result -> Flux.from(result.map((row, metadata) ->
                new CustomerSummary(
                        row.get("id", Long.class),
                        row.get("email", String.class),
                        row.get("display_name", String.class)))));
```

Ở tầng SPI, marker SQL và cách bind phụ thuộc driver. PostgreSQL thường dùng `$1` trong SQL và index 0 trong `Statement.bind(0, value)`. Không sao chép marker của PostgreSQL sang driver dùng `?` hoặc cú pháp khác.

`Result.map(...)` trả publisher các giá trị đã ánh xạ. Cần tiêu thụ result theo hợp đồng R2DBC SPI; không bỏ publisher của `Result.map` và không giữ `Row` để dùng sau khi mapper đã kết thúc.

## 17. Quản lý connection khi dùng SPI trực tiếp

Với `DatabaseClient`, Spring quản lý việc lấy và release connection. Khi dùng `ConnectionFactory` trực tiếp, ứng dụng phải đóng connection trong mọi trường hợp complete, error và cancel.

Ví dụ dùng `Flux.usingWhen`:

```java
public Flux<CustomerSummary> findActiveCustomersDirect() {
    return Flux.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> {
                Statement statement = connection.createStatement("""
                        SELECT id, email, display_name
                        FROM customer
                        WHERE active = $1
                        """);
                statement.bind(0, true);

                return Flux.from(statement.execute())
                        .concatMap(result -> Flux.from(result.map(
                                (row, metadata) -> new CustomerSummary(
                                        row.get("id", Long.class),
                                        row.get("email", String.class),
                                        row.get("display_name", String.class)))));
            },
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

`usingWhen` gắn cleanup với complete, error và cancellation. Đây là trách nhiệm của code SPI trực tiếp; không tự đóng connection do Spring transaction manager đang quản lý.

Nếu ứng dụng cần transaction, connection lifecycle và transaction begin/commit/rollback phải được quản lý đúng. Với code thông thường, `DatabaseClient` hoặc Spring Data repository giảm đáng kể rủi ro quản lý tài nguyên thủ công.

## 18. `Row` chỉ nên được đọc trong callback mapping

Không giữ `Row` trong field, collection hoặc publisher khác để đọc sau:

```java
// Không nên: giữ Row để xử lý sau callback.
List<Row> rows = new ArrayList<>();

return databaseClient.sql("SELECT id, email FROM customer")
        .map((row, metadata) -> {
            rows.add(row);
            return row;
        })
        .all();
```

`Row` là view do driver quản lý trên một hàng kết quả. Lifetime và backing memory của nó phụ thuộc driver; sau khi callback/result được tiêu thụ, không được giả định đối tượng còn hợp lệ.

Hãy đọc ngay các giá trị cần thiết và tạo object độc lập:

```java
return databaseClient.sql("SELECT id, email FROM customer")
        .map((row, metadata) -> new CustomerSummary(
                row.get("id", Long.class),
                row.get("email", String.class)))
        .all();
```

DTO được tạo từ giá trị đã đọc có thể được truyền tiếp trong pipeline. Không chuyển `Row` hoặc `RowMetadata` ra khỏi callback để xử lý bất đồng bộ sau đó.

## 19. Không giữ `RowMetadata` như một phần dữ liệu nghiệp vụ

Metadata mô tả cấu trúc result set, không đại diện cho schema domain lâu dài. Không lưu `RowMetadata` vào entity hoặc cache nghiệp vụ.

Nếu cần thông tin cột để debug hoặc xây một projection động, hãy trích xuất giá trị đơn giản như tên cột, kiểu Java và precision/scale trong callback rồi tạo một cấu trúc metadata do ứng dụng sở hữu. Tránh giữ object metadata do driver cung cấp sau khi result kết thúc trừ khi driver tài liệu hóa rõ lifetime.

## 20. Mapping timestamp và timezone

Thời gian là nguồn lỗi mapping phổ biến vì kiểu SQL khác nhau:

- `DATE` biểu diễn ngày, thường map sang `LocalDate`.
- `TIME` biểu diễn giờ trong ngày, thường map sang `LocalTime`.
- `TIMESTAMP` không có timezone, thường map sang `LocalDateTime`.
- `TIMESTAMP WITH TIME ZONE` có semantics phụ thuộc database; PostgreSQL R2DBC thường hỗ trợ `OffsetDateTime`.

Ví dụ:

```java
OffsetDateTime createdAt = row.get("created_at", OffsetDateTime.class);
LocalDateTime scheduledAt = row.get("scheduled_at", LocalDateTime.class);
LocalDate birthDate = row.get("birth_date", LocalDate.class);
```

Không chuyển một timestamp không timezone thành `Instant` mà không xác định timezone nghiệp vụ. Nếu database lưu thời điểm UTC, hãy thống nhất kiểu và quy tắc chuyển đổi ở schema, driver và domain.

Kiểm thử giá trị có offset, DST và precision của timestamp trên database mục tiêu. Một số driver cắt bớt fractional seconds theo precision cột.

## 21. Mapping số tiền và kiểu số chính xác

Với `NUMERIC`/`DECIMAL`, ưu tiên `BigDecimal`:

```java
BigDecimal total = row.get("total", BigDecimal.class);
```

Không dùng `double` cho số tiền vì floating-point có thể không biểu diễn chính xác một số thập phân. Nếu cần scale cố định, kiểm tra precision/scale trong schema và áp dụng quy tắc làm tròn ở domain/service.

Với `COUNT`, `SUM` hoặc số lớn, kiểm tra kiểu Java mà driver trả về. Không ép `Long` sang `Integer` nếu có nguy cơ overflow. Khi chuyển kiểu, dùng các phương thức kiểm tra như `Math.toIntExact(...)` hoặc xác minh range.

## 22. Mapping enum

Database có thể lưu enum dưới dạng `VARCHAR`, mã số hoặc kiểu enum native. Cách an toàn thường là đọc giá trị lưu trữ rồi chuyển đổi qua một hàm domain rõ ràng:

```java
String statusValue = row.get("status", String.class);
OrderStatus status = OrderStatus.valueOf(statusValue);
```

Nếu database có giá trị cũ hoặc không biết, `valueOf` sẽ ném `IllegalArgumentException`. Có thể dùng parser có kiểm soát để phát mapping exception rõ ràng, nhưng không tự chuyển mọi giá trị lạ thành một trạng thái hợp lệ mà không có chính sách.

Nếu database dùng mã không trùng tên enum Java, tạo map tường minh:

```java
private OrderStatus toOrderStatus(String value) {
    return switch (value) {
        case "P" -> OrderStatus.PENDING;
        case "C" -> OrderStatus.COMPLETED;
        case "X" -> OrderStatus.CANCELLED;
        default -> throw new IllegalArgumentException(
                "Unknown order status code");
    };
}
```

## 23. Mapping JSON, array và kiểu dữ liệu đặc thù

Một số database hỗ trợ JSON/JSONB, array, spatial hoặc kiểu native. R2DBC driver có thể cung cấp codec riêng cho các kiểu này. Cách đọc có thể là `String`, `Json`, `List`, `Array` hoặc kiểu cụ thể tùy driver.

Ví dụ với PostgreSQL JSONB, có thể đọc theo kiểu mà driver hỗ trợ rồi parse thành DTO bằng thư viện JSON của ứng dụng. Không giả định mọi driver đều map JSONB trực tiếp sang `Map<String, Object>`.

Với dữ liệu JSON:

1. Xác minh kiểu Java driver cung cấp.
2. Đọc giá trị trong callback mapping.
3. Parse bằng `ObjectMapper`/codec đã cấu hình.
4. Xử lý JSON null, SQL NULL và JSON không hợp lệ thành các trường hợp riêng.
5. Giới hạn kích thước payload và không log dữ liệu nhạy cảm.

Với array, kiểm tra cách driver biểu diễn và cách release resource nếu dùng kiểu buffer đặc thù. Ưu tiên chuyển sang cấu trúc Java do ứng dụng sở hữu trước khi rời callback.

## 24. Phân biệt SQL `NULL`, JSON `null` và giá trị thiếu

Ba trường hợp có ý nghĩa khác nhau:

- SQL `NULL`: cột không có giá trị trong database; `row.get(...)` thường trả Java `null`.
- JSON `null`: một giá trị null nằm bên trong tài liệu JSON; cột JSON vẫn có thể không phải SQL NULL.
- Cột không có trong result set: query không select cột đó hoặc alias không đúng; đây là lỗi shape query, không phải giá trị null.

Ví dụ:

```sql
SELECT
    NULL::text AS sql_null_value,
    '{"nickname": null}'::jsonb AS json_document;
```

Khi mapping, `sql_null_value` có thể là Java null; `json_document` là một JSON value chứa property null. Không dùng `row.get(...) == null` để kết luận JSON property bên trong cũng null.

Nếu API cần phân biệt field không được select, field SQL NULL và JSON null, DTO cần biểu diễn rõ trạng thái thay vì dùng một `String` nullable cho tất cả.

## 25. Mapping lỗi và validation kết quả

Mapping callback có thể phát sinh lỗi khi:

- Tên cột hoặc alias không tồn tại.
- Driver không hỗ trợ kiểu Java yêu cầu.
- Cột SQL NULL nhưng domain bắt buộc non-null.
- Giá trị không thể chuyển sang enum/domain type.
- Dữ liệu database vi phạm invariant mà ứng dụng mong đợi.
- JSON hoặc dữ liệu đặc thù không parse được.

Không nên bắt mọi exception rồi trả DTO mặc định:

```java
// Không nên: che giấu lỗi mapping.
return databaseClient.sql(sql)
        .map((row, metadata) -> {
            try {
                return mapCustomer(row);
            } catch (Exception error) {
                return CustomerSummary.empty();
            }
        })
        .all();
```

Hãy để lỗi mapping đi qua reactive pipeline hoặc chuyển thành exception có ngữ cảnh mà không che nguyên nhân:

```java
return databaseClient.sql(sql)
        .map((row, metadata) -> {
            try {
                return mapCustomer(row);
            } catch (RuntimeException error) {
                throw new CustomerRowMappingException(
                        "Cannot map customer query result", error);
            }
        })
        .all();
```

Không đưa dữ liệu row nhạy cảm vào message. Có thể log query name, alias và exception class để chẩn đoán.

## 26. Mapping và `R2dbcCustomConversions`

Spring Data Relational có `MappingR2dbcConverter` và `R2dbcCustomConversions` để chuyển đổi giữa kiểu domain và kiểu lưu trữ khi dùng mapping infrastructure của Spring Data.

Khi dùng repository hoặc `R2dbcEntityTemplate` với entity mapping, Spring Data có thể áp dụng custom converters đã cấu hình. Nhưng callback thủ công:

```java
databaseClient.sql(sql)
        .map((row, metadata) -> new DomainObject(
                row.get("custom_value", String.class)))
        .all();
```

đang đọc trực tiếp qua `Row.get`. Đừng giả định `R2dbcCustomConversions` tự được áp dụng cho mọi lời gọi `Row.get`. Nếu domain type cần conversion riêng, có thể đọc kiểu cơ sở mà driver hỗ trợ rồi gọi converter/service mapping tường minh, hoặc dùng mapping converter Spring Data theo API phù hợp.

Ví dụ chuyển string code thành value object:

```java
String rawCode = row.get("account_code", String.class);
AccountCode accountCode = AccountCode.of(rawCode);
```

Nếu cần dùng `MappingR2dbcConverter` trực tiếp, hãy kiểm tra API của phiên bản Spring Data Relational hiện tại và cấu hình converter đúng với mapping context/conversions của ứng dụng. Không tạo converter mới không đồng bộ với cấu hình entity mapping.

## 27. Khi nào dùng mapping tự động, khi nào mapping thủ công?

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| CRUD theo aggregate/entity đã khai báo `@Table` | Repository hoặc `R2dbcEntityTemplate` |
| Query trả một entity tương đối trực tiếp | Mapping entity của Spring Data |
| Projection DTO từ một số cột | `DatabaseClient.map(...)` hoặc projection phù hợp |
| Join nhiều bảng với alias riêng | Mapping thủ công sang row DTO rồi nhóm nếu cần |
| Aggregate, window function hoặc SQL đặc thù | `DatabaseClient`/SPI và mapping thủ công |
| Kiểu native cần codec đặc biệt | Driver codec hoặc custom conversion có kiểm soát |
| Cần kiểm soát statement/result ở mức thấp | R2DBC SPI `Statement` và `Result.map` |

Mapping thủ công không phải lúc nào cũng tốt hơn. Với CRUD entity thông thường, mapping tự động giảm boilerplate và tận dụng metadata/conversion của Spring Data. Dùng callback thủ công khi query shape thực sự cần nó.

## 28. Tránh `SELECT *` và mapping phụ thuộc schema ngoài ý muốn

`SELECT *` khiến mapping phụ thuộc toàn bộ cột hiện có. Khi schema thêm cột, kết quả có thể thay đổi và làm lộ dữ liệu không cần thiết. Trong join, `SELECT *` còn tạo tên cột trùng nhau.

Nên liệt kê rõ projection:

```sql
SELECT
    c.id AS customer_id,
    c.email AS customer_email,
    c.display_name AS customer_name
FROM customer c
WHERE c.id = :id;
```

Lợi ích:

- Mapping có hợp đồng rõ ràng.
- Giảm dữ liệu truyền từ database.
- Tránh đọc cột nhạy cảm không cần thiết.
- Alias ổn định giữa các bảng.
- Test có thể xác minh shape result cụ thể.

## 29. Metadata không thay thế schema migration

`RowMetadata` mô tả result set của câu query hiện tại. Nó không phải công cụ quản lý schema, migration hoặc validation toàn bộ database.

Không dùng metadata của một query để kết luận mọi bảng có cùng kiểu hoặc mọi instance ứng dụng đã được migration. Nếu query trả cột sai kiểu, hãy kiểm tra schema migration, SQL expression/cast và driver codec. Metadata chỉ giúp quan sát những gì query thực sự trả về.

## 30. Mapping kết quả khi dùng `DatabaseClient` với `Result` nhiều phần

Ở mức `DatabaseClient`, API `map` đã làm việc với `Result` và cung cấp `Row` cho callback. Khi dùng SPI trực tiếp, một statement có thể phát nhiều `Result`, ví dụ khi chạy batch hoặc một số statement nhiều phần. Hãy tiêu thụ tất cả result theo đúng semantics và không bỏ qua publisher trả về từ `Result.map`.

Ví dụ query đơn giản thường có một result chứa các hàng. Với batch/update, có thể cần đọc `getRowsUpdated()` thay vì `map` rows. Không cố map một kết quả update không có row thành DTO.

## 31. Phân biệt row result với số hàng bị ảnh hưởng

Một `SELECT` thường trả rows; `INSERT`, `UPDATE`, `DELETE` thường cung cấp số hàng bị ảnh hưởng. `DatabaseClient` hỗ trợ:

```java
Mono<Long> updated = databaseClient.sql("""
        UPDATE customer
        SET active = :active
        WHERE id = :id
        """)
        .bind("active", false)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
```

Không dùng `Row`/`RowMetadata` để đọc kết quả của một update nếu statement không trả result rows. Nếu database hỗ trợ `RETURNING`, câu lệnh có thể trả rows:

```sql
UPDATE customer
SET active = FALSE
WHERE id = :id
RETURNING id, active;
```

Khi đó có thể map returned rows như một query. Cú pháp `RETURNING` phụ thuộc database.

## 32. Đọc metadata để chẩn đoán kiểu cột

Trong debug, có thể in metadata cột:

```java
private void describe(RowMetadata metadata) {
    for (ColumnMetadata column : metadata.getColumnMetadatas()) {
        log.debug(
                "name={}, javaType={}, nativeType={}, precision={}, scale={}",
                column.getName(),
                column.getJavaType().getName(),
                column.getNativeTypeMetadata(),
                column.getPrecision(),
                column.getScale());
    }
}
```

Các giá trị precision/scale hoặc native metadata có thể không có hoặc phụ thuộc driver. Kiểm tra nullability trước khi dereference metadata optional nếu API/driver cho phép thiếu. Không dùng log metadata để ghi dữ liệu row.

## 33. Mapping linh hoạt bằng index và metadata

Một số công cụ nội bộ cần biến result set thành cấu trúc tổng quát như `Map<String, Object>`. Có thể duyệt metadata để biết tên cột, sau đó đọc giá trị theo index với kiểu Java mà metadata công bố:

```java
private Map<String, Object> toMap(Row row, RowMetadata metadata) {
    Map<String, Object> values = new LinkedHashMap<>();

    for (int index = 0; index < metadata.getColumnMetadatas().size(); index++) {
        ColumnMetadata column = metadata.getColumnMetadata(index);
        Object value = row.get(index, column.getJavaType());
        values.put(column.getName(), value);
    }

    return values;
}
```

Đây là mapping tổng quát có giới hạn. Một số driver có thể trả kiểu Java hoặc metadata native cần xử lý đặc biệt; `getJavaType()` không đảm bảo mọi kiểu có thể được serialize trực tiếp. Cần kiểm tra các kiểu như `Blob`, `Clob`, buffer, array và JSON riêng.

Với cột trùng tên, `Map<String,Object>` có thể ghi đè giá trị trước. Dùng alias duy nhất hoặc key có namespace. Không dùng mapping tổng quát này làm DTO domain chính nếu cấu trúc kết quả đã biết.

## 34. Cẩn thận khi dùng `getColumnMetadatas()` và tên cột động

Nếu result set có nhiều cột, lấy metadata một lần rồi dùng danh sách đó để duyệt index. Tránh gọi reflection hoặc tạo class động cho mỗi row trong một result lớn nếu không có nhu cầu.

Tên cột đến từ SQL do ứng dụng kiểm soát. Nếu query được tạo động từ input, vẫn phải allowlist identifier; metadata không biến SQL động không an toàn thành an toàn.

## 35. Kiểm thử mapping thủ công

Mapping thủ công nên được kiểm thử với database và driver thực tế. Một số lỗi chỉ xuất hiện khi driver chuyển đổi kiểu hoặc trả metadata theo dialect cụ thể.

Các trường hợp nên kiểm tra:

1. Mapping theo tên alias và theo index.
2. Cột SQL NULL vào DTO nullable.
3. Cột bắt buộc null phát lỗi mapping rõ ràng.
4. Join có cột trùng tên nhưng alias riêng.
5. `LEFT JOIN` không có hàng ở phía phải.
6. Aggregate trả null hoặc zero theo semantics SQL.
7. Timestamp có/không timezone và precision.
8. Numeric lớn, decimal scale và overflow.
9. Enum code không hợp lệ.
10. JSON/array/native type theo codec driver.
11. Query trả thiếu alias hoặc đổi kiểu cột.
12. Publisher bị cancel giữa result và resource được cleanup.

## 36. Ví dụ integration test cho mapping

Giả sử query trả một customer có `display_name` null:

```java
@SpringBootTest
class CustomerRowMappingTest {

    @Autowired
    CustomerQueryRepository queryRepository;

    @Test
    void mapsNullableColumn() {
        StepVerifier.create(queryRepository.findSummaryById(10L))
                .assertNext(customer -> {
                    assertThat(customer.id()).isEqualTo(10L);
                    assertThat(customer.displayName()).isNull();
                })
                .verifyComplete();
    }
}
```

Test này xác minh mapping của SQL NULL vào reference type. Fixture phải tạo dữ liệu có chủ đích và query phải select đúng alias. Với driver production, chạy test trên Testcontainers hoặc database test tương thích.

## 37. Ví dụ kiểm tra `RowMetadata`

Có thể test metadata shape thông qua `DatabaseClient`:

```java
Mono<List<String>> columnNames = databaseClient.sql("""
        SELECT id AS customer_id, email AS customer_email
        FROM customer
        WHERE id = :id
        """)
        .bind("id", 10L)
        .map((row, metadata) -> metadata.getColumnMetadatas().stream()
                .map(ColumnMetadata::getName)
                .toList())
        .one();
```

Ví dụ minh họa cách đọc danh sách tên cột từ metadata; vì query có thể không trả hàng, callback mapping không chạy và publisher có thể hoàn tất rỗng. Nếu chỉ muốn kiểm tra metadata độc lập với row data, cần chọn một query chắc chắn trả ít nhất một hàng hoặc dùng test SQL phù hợp với database.

Không viết test phụ thuộc thứ tự cột nếu mapping dùng tên và thứ tự không phải một phần của hợp đồng. Ngược lại, nếu mapping dùng index, thứ tự phải được kiểm tra rõ.

## 38. Debug lỗi `Column ... not found`

Khi `row.get("column_name", ...)` lỗi vì không tìm thấy cột, kiểm tra:

- SQL có select cột đó không.
- Alias chính xác là gì.
- Database có chuyển casing của identifier không.
- Query join có alias trùng tên không.
- Có dùng tên property Java thay cho tên alias SQL không.
- Có thay đổi query hoặc projection mà chưa cập nhật mapper không.

Một cách nhanh là in `metadata.getColumnMetadatas()` trong môi trường test/debug để xem tên thực tế. Sau đó sửa alias hoặc mapping; không bắt exception rồi trả null vì điều đó che lỗi hợp đồng giữa SQL và code.

## 39. Debug lỗi kiểu không tương thích

Khi `row.get("amount", BigDecimal.class)` hoặc `row.get("created_at", OffsetDateTime.class)` lỗi, kiểm tra:

- Kiểu SQL thực tế của biểu thức/cột.
- Kiểu Java mà `ColumnMetadata.getJavaType()` công bố.
- Codec/driver có hỗ trợ kiểu yêu cầu không.
- Query có cast sang kiểu khác không.
- Cột có phải expression/aggregate thay vì cột gốc không.
- Kiểu timestamp có timezone hay không.
- Version của driver có thay đổi conversion behavior không.

Đừng ép kiểu bằng cast không an toàn hoặc đổi mọi lỗi thành null. Có thể dùng `CAST(...)` trong SQL nếu conversion nên do database thực hiện, hoặc đọc kiểu cơ sở tương thích rồi chuyển đổi tường minh trong Java.

## 40. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng sai tên cột/alias | Mapping lỗi hoặc đọc nhầm | Dùng alias ổn định và kiểm tra metadata |
| Dùng sai kiểu Java trong `row.get` | Driver không chuyển đổi được | Chọn kiểu tương thích hoặc convert tường minh |
| Dùng primitive cho cột nullable | Không biểu diễn được SQL NULL | Dùng wrapper/reference type |
| Giữ `Row` ngoài callback | Có thể đọc resource đã hết lifetime | Map ngay sang DTO/domain object |
| Giữ `RowMetadata` như domain state | Phụ thuộc object driver và result lifecycle | Trích xuất thông tin cần thiết thành kiểu ứng dụng |
| Dùng index nhưng thay đổi thứ tự SELECT | Mapping lệch cột | Dùng tên/alias hoặc test thứ tự projection |
| Dùng `SELECT *` trong join | Trùng tên, mapping khó ổn định | Liệt kê cột và alias riêng |
| Nhầm SQL NULL với JSON null | Sai semantics dữ liệu | Xử lý SQL null và JSON null riêng |
| Dùng `one()` cho query nhiều hàng | Cardinality error | Dùng `all()` hoặc `first()` theo nghiệp vụ |
| Dùng `first()` không có ORDER BY | Kết quả không ổn định | Thêm thứ tự rõ hoặc query unique |
| Nghĩ `R2dbcCustomConversions` áp dụng cho `Row.get` thủ công | Conversion không chạy như mong đợi | Đọc kiểu cơ sở và convert rõ hoặc dùng mapping converter |
| Bỏ qua publisher `Result.map` | Không tiêu thụ hàng | Nối publisher bằng `concatMap`/operator phù hợp |
| Không đóng connection khi dùng SPI | Connection leak | Dùng `usingWhen` hoặc lifecycle tương đương |
| Log toàn bộ row để debug | Có thể lộ dữ liệu nhạy cảm | Log tên cột/kiểu và correlation ID |

## 41. Quy trình ánh xạ kết quả thủ công

Khi viết một query SQL trực tiếp, hãy thực hiện theo trình tự:

1. Liệt kê rõ các cột cần trả về, tránh `SELECT *`.
2. Đặt alias duy nhất, dễ đọc, nhất là khi join nhiều bảng.
3. Chọn `DatabaseClient.map((row, metadata) -> ...)` cho mapping ở tầng Spring.
4. Đọc theo tên cột khi muốn mapping dễ bảo trì; dùng index khi có lý do và kiểm soát thứ tự.
5. Chọn kiểu Java tương thích với database/driver.
6. Xử lý SQL NULL bằng wrapper/reference type và kiểm tra cột bắt buộc.
7. Dùng `RowMetadata` để kiểm tra tên, kiểu và shape khi cần.
8. Chuyển `Row` thành DTO/domain object ngay trong callback.
9. Chọn `all()`, `one()` hoặc `first()` theo cardinality nghiệp vụ.
10. Nếu dùng SPI trực tiếp, tiêu thụ `Result.map` và đóng connection ở complete/error/cancel.
11. Kiểm tra timestamp, numeric, enum, JSON và native type theo driver.
12. Viết integration test với schema và R2DBC driver tương thích production.

## 42. Nguyên tắc thực hành

- `Row` chứa giá trị của một hàng; `RowMetadata` mô tả các cột của result set.
- Dùng `DatabaseClient.map((row, metadata) -> ...)` để ánh xạ thủ công trong reactive pipeline.
- Đọc theo tên/alias để code dễ bảo trì; dùng index khi kiểm soát chặt thứ tự `SELECT`.
- Chọn kiểu Java mà driver hỗ trợ; kiểm thử với đúng database/driver.
- Dùng wrapper/reference type cho cột có thể SQL NULL.
- Dùng `RowMetadata` để xem tên, kiểu Java/native và precision/scale khi cần chẩn đoán.
- Alias riêng các cột trùng tên trong join.
- Tránh `SELECT *`; chỉ lấy cột cần thiết.
- Không giữ `Row` hoặc metadata driver ra ngoài callback/result lifecycle.
- Chuyển JSON, enum, timestamp và kiểu native bằng codec/conversion có chủ đích.
- Không giả định `R2dbcCustomConversions` tự áp dụng cho `Row.get` thủ công.
- Chọn `all`, `one` hoặc `first` đúng cardinality và thêm `ORDER BY` khi cần kết quả ổn định.
- Khi dùng R2DBC SPI trực tiếp, tiêu thụ `Result` và cleanup connection trên complete/error/cancel.
- Không che lỗi mapping bằng DTO mặc định hoặc null âm thầm.
- Kiểm thử shape result, nullability, kiểu dữ liệu, join và cancellation trên driver thực tế.

## 43. Kết luận

`Row` và `RowMetadata` là hai thành phần cốt lõi khi ánh xạ kết quả SQL trực tiếp trong Spring Data Relational R2DBC. `Row` cho phép đọc giá trị theo tên hoặc index với kiểu Java mong muốn; `RowMetadata` cung cấp thông tin về tên cột, kiểu và các thuộc tính metadata mà driver hỗ trợ. `DatabaseClient.map(...)` giúp chuyển từng hàng thành DTO ngay trong reactive pipeline, còn R2DBC SPI `Result.map(...)` cung cấp khả năng tương tự ở tầng thấp hơn.

Để mapping ổn định, hãy liệt kê cột rõ ràng, dùng alias duy nhất, chọn kiểu Java tương thích, xử lý SQL NULL bằng reference type và không giữ `Row` sau callback. Dùng metadata để chẩn đoán shape result, không thay thế schema migration hoặc validation domain. Với code SPI trực tiếp, quản lý việc tiêu thụ result và đóng connection trên mọi terminal signal. Integration test trên đúng database/driver sẽ xác nhận các chi tiết kiểu dữ liệu và codec mà mock không thể mô phỏng.

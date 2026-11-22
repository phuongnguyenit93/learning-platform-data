# Ánh xạ mã giá trị, enum đặc thù và kiểu định danh riêng

Trong **Spring Data Relational JDBC**, domain model không nhất thiết phải dùng cùng kiểu dữ liệu hoặc cùng giá trị với database. Ứng dụng có thể dùng enum có mã nghiệp vụ ổn định, value object cho identifier, hoặc kiểu domain riêng trong khi bảng vẫn lưu `VARCHAR`, `BIGINT`, `UUID` hay một kiểu scalar khác.

Cơ chế chính để làm việc này là **custom conversion**. Spring Data JDBC sử dụng converter để chuyển kiểu Java thành giá trị relational khi ghi và chuyển ngược lại khi đọc. Với enum đặc thù, converter có thể lưu mã như `N`, `P`, `X` thay vì tên enum. Với kiểu định danh riêng, converter có thể ánh xạ `CustomerId` sang `Long` trong database nhưng vẫn giữ kiểu `CustomerId` an toàn trong Java.

Bài học trình bày cách ánh xạ mã giá trị, enum có code riêng, identifier dạng value object, cách đăng ký converter, xử lý dữ liệu cũ và kiểm thử hai chiều đọc/ghi.

## 1. Vì sao cần ánh xạ giá trị domain sang kiểu database?

Trong domain, một giá trị có thể mang ý nghĩa phong phú hơn cách database lưu nó.

Ví dụ trạng thái đơn hàng:

```java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

Nếu lưu tên enum trực tiếp, cột có thể chứa `NEW`, `PAID`, `CANCELLED`. Cách này đơn giản, nhưng database bị phụ thuộc vào tên constant trong Java. Nếu code đổi tên `CANCELLED` thành `VOIDED`, dữ liệu cũ có thể không còn được đọc như mong đợi.

Một cách khác là gán mã lưu trữ ổn định:

| Domain value | Database code | Ý nghĩa |
|---|---|---|
| `NEW` | `N` | Đơn hàng mới |
| `PAID` | `P` | Đã thanh toán |
| `CANCELLED` | `X` | Đã hủy |

Java dùng tên enum dễ đọc, còn database lưu mã ngắn và ổn định. Tương tự, thay vì truyền `Long` ở mọi nơi, domain có thể dùng `CustomerId` để tránh nhầm ID khách hàng với ID đơn hàng.

Các nhu cầu thường gặp:

- Lưu enum bằng mã nghiệp vụ thay vì `Enum.name()`.
- Đọc mã legacy hoặc mã do hệ thống ngoài định nghĩa.
- Dùng value object như `CustomerId`, `OrderId`, `TenantId`.
- Ánh xạ UUID hoặc kiểu định danh riêng sang kiểu JDBC.
- Giữ kiểu dữ liệu domain rõ ràng trong repository và service.
- Tách cách biểu diễn trong Java khỏi schema lưu trữ.

## 2. Custom converter trong Spring Data JDBC

Spring Data JDBC dựa trên Spring Conversion Service và hệ thống custom conversions của Spring Data Relational. Converter mô tả cách chuyển đổi giữa một kiểu Java và một kiểu scalar mà JDBC/database có thể lưu.

Hai chiều quan trọng:

- **Writing converter:** chuyển kiểu domain/Java sang kiểu ghi được vào database.
- **Reading converter:** chuyển giá trị đọc từ database thành kiểu domain/Java.

Ví dụ:

```java
@WritingConverter
public class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.getCode();
    }
}
```

```java
@ReadingConverter
public class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
```

Các annotation thuộc `org.springframework.data.convert`:

- `@WritingConverter`
- `@ReadingConverter`

Interface `Converter` thuộc `org.springframework.core.convert.converter`.

Annotation hướng chuyển đổi giúp Spring Data phân biệt converter đọc và converter ghi, đặc biệt khi kiểu nguồn/đích phổ biến như `String`, `Long` hoặc `Integer` có thể tham gia nhiều conversion khác nhau.

### 2.1. Một converter thường biểu diễn một giá trị scalar

Một converter như `OrderStatus -> String` phù hợp vì một enum được lưu trong một cột `VARCHAR`.

Một converter như `CustomerId -> Long` phù hợp vì một identifier value object được lưu trong một cột `BIGINT`.

Nếu một domain object cần nhiều cột độc lập, ví dụ địa chỉ gồm đường, thành phố và mã bưu chính, converter scalar không phải lựa chọn tự nhiên. Hãy cân nhắc `@Embedded` để flatten các property hoặc mô hình hóa một bảng riêng nếu dữ liệu có lifecycle độc lập.

### 2.2. Converter không phải JPA AttributeConverter

Spring Data JDBC dùng converter của Spring Data, không dùng cơ chế JPA `AttributeConverter` hay annotation `@Convert`.

Không áp dụng máy móc ví dụ:

```java
// Đây là API JPA, không phải cách đăng ký converter của Spring Data JDBC.
@Convert(converter = OrderStatusConverter.class)
private OrderStatus status;
```

Trong Spring Data JDBC, hãy triển khai `Converter<S, T>`, đánh dấu hướng đọc/ghi và đăng ký với cấu hình Spring Data JDBC.

## 3. Ánh xạ enum bằng mã riêng

Bắt đầu bằng enum có code rõ ràng:

```java
import java.util.Arrays;

public enum OrderStatus {

    NEW("N"),
    PAID("P"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        return Arrays.stream(values())
                .filter(status -> status.code.equals(code))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown order status code: " + code
                ));
    }
}
```

Code lưu trữ là một phần hợp đồng dữ liệu. Hãy chọn code ổn định, dễ migration và không phụ thuộc thứ tự constant.

Không nên dùng `ordinal()` để lưu enum. Nếu enum hiện tại có thứ tự `NEW`, `PAID`, `CANCELLED`, ordinal tương ứng là `0`, `1`, `2`. Khi thêm hoặc sắp xếp lại constant, ý nghĩa số có thể thay đổi và dữ liệu cũ bị diễn giải sai.

### 3.1. Writing converter

Converter ghi lấy code từ enum:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.getCode();
    }
}
```

Khi entity có `status = OrderStatus.PAID`, converter ghi giá trị `P` vào cột.

### 3.2. Reading converter

Converter đọc nhận code từ database rồi tìm enum tương ứng:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
```

Nếu database chứa `P`, domain nhận `OrderStatus.PAID`.

Nếu database chứa code không được nhận diện, ví dụ `Z`, ví dụ trên chủ động báo lỗi. Đây là lựa chọn fail-fast để phát hiện dữ liệu sai hoặc phiên bản ứng dụng chưa hỗ trợ code mới.

### 3.3. Vì sao cần cả hai chiều?

Chỉ đăng ký writing converter thì ứng dụng có thể ghi code đúng nhưng không đọc lại được enum theo code. Chỉ đăng ký reading converter thì đọc được dữ liệu nhưng lúc save có thể dùng conversion mặc định hoặc không tìm thấy converter mong muốn.

Với một kiểu domain được lưu vào một kiểu scalar, hãy định nghĩa và đăng ký cả hai chiều nếu ứng dụng cần đọc lẫn ghi.

### 3.4. Cột database

Schema ví dụ:

```sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(40) NOT NULL,
    status_code VARCHAR(8) NOT NULL
);
```

Entity:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_code")
    private String orderCode;

    @Column("status_code")
    private OrderStatus status;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderCode, OrderStatus status) {
        this.orderCode = orderCode;
        this.status = status;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

`@Column("status_code")` quyết định tên cột. Converter quyết định giá trị enum được biểu diễn như thế nào. Hai trách nhiệm này độc lập.

## 4. Đăng ký custom converters

Trong cấu hình Spring Data JDBC, có thể mở rộng `AbstractJdbcConfiguration` và cung cấp danh sách converter qua `userConverters()`.

Ví dụ:

```java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new OrderStatusWritingConverter(),
                new OrderStatusReadingConverter()
        );
    }
}
```

Spring Data JDBC sử dụng các converter đã đăng ký trong conversion infrastructure của module. Nếu dự án có cấu hình JDBC riêng hoặc phiên bản module khác, hãy xác nhận method extension point và package tương ứng trong dependency đang dùng.

Không đăng ký lặp cùng converter qua nhiều cơ chế cấu hình. Một nguồn cấu hình rõ ràng giúp tránh khó đoán khi có nhiều converter cùng nguồn/đích.

### 4.1. Khi nào dùng @ReadingConverter và @WritingConverter?

Dùng annotation theo chiều dữ liệu:

| Converter | Annotation | Hướng |
|---|---|---|
| `OrderStatus -> String` | `@WritingConverter` | Domain → database |
| `String -> OrderStatus` | `@ReadingConverter` | Database → domain |
| `CustomerId -> Long` | `@WritingConverter` | Value object → scalar |
| `Long -> CustomerId` | `@ReadingConverter` | Scalar → value object |

Đặc biệt quan trọng với `String -> Enum` hoặc `Long -> CustomerId`, vì kiểu scalar nguồn thường được dùng cho nhiều mapping khác.

## 5. Đọc code cũ và xử lý unknown code

Trong hệ thống đang chạy, database có thể chứa nhiều thế hệ code. Ví dụ trước đây ứng dụng dùng `C` cho cancelled, sau đó hợp đồng tích hợp chuyển sang `X`.

Có thể cho reading converter hiểu cả code cũ và code mới, trong khi writing converter chỉ ghi code chuẩn hiện tại:

```java
public enum OrderStatus {

    NEW("N"),
    PAID("P"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        return switch (code) {
            case "N" -> NEW;
            case "P" -> PAID;
            case "X", "C" -> CANCELLED;
            default -> throw new IllegalArgumentException(
                    "Unsupported order status: " + code
            );
        };
    }
}
```

Trong ví dụ, code `C` vẫn được đọc thành `CANCELLED`, nhưng khi ghi lại, converter luôn ghi `X`.

Đây là kỹ thuật hỗ trợ migration theo giai đoạn. Tuy nhiên, alias code cũ nên có kế hoạch loại bỏ:

1. Triển khai reading converter hiểu cả code cũ và mới.
2. Chuyển writer sang ghi code mới.
3. Migration dữ liệu cũ nếu cần.
4. Kiểm tra log/metric để biết còn code cũ hay không.
5. Gỡ alias cũ sau khi dữ liệu và các writer đã được cập nhật.

Không nên âm thầm map mọi code lạ thành một trạng thái mặc định nếu điều đó có thể che giấu lỗi dữ liệu. Nếu nghiệp vụ cần trạng thái `UNKNOWN`, hãy định nghĩa nó rõ ràng và quyết định có được phép ghi ngược hay không.

## 6. Enum mặc định và enum có mã nghiệp vụ

Nếu không có custom converter, Spring Data thường có thể ánh xạ enum qua tên constant theo conversion mặc định. Ví dụ `OrderStatus.PAID` được lưu như `PAID`.

| Cách lưu | Giá trị trong cột | Hệ quả |
|---|---|---|
| Tên enum mặc định | `PAID` | Dễ đọc, nhưng gắn với tên constant |
| Mã enum riêng | `P` | Code có thể ổn định khi đổi tên constant |
| Ordinal | `1` | Không nên dùng vì phụ thuộc thứ tự constant |

Khi database schema đã lưu tên enum, việc chuyển sang code riêng là một migration dữ liệu. Chỉ thêm converter mà không chuyển dữ liệu hiện có có thể khiến reading converter không hiểu các giá trị cũ.

Ví dụ migration:

```sql
UPDATE orders
SET status_code = CASE status_code
    WHEN 'NEW' THEN 'N'
    WHEN 'PAID' THEN 'P'
    WHEN 'CANCELLED' THEN 'X'
    ELSE status_code
END;
```

Điều chỉnh tên bảng/cột và transaction strategy theo database thực tế. Trước migration, thống kê những giá trị hiện có và quyết định cách xử lý code ngoài dự kiến.

## 7. Kiểu định danh riêng bằng value object

Dùng `Long` cho mọi ID khiến các giá trị cùng kiểu dễ bị truyền nhầm:

```java
void assignCustomer(Long customerId, Long orderId) {
    // Compiler không ngăn việc truyền nhầm hai Long.
}
```

Có thể tạo kiểu riêng cho từng định danh:

```java
public record CustomerId(Long value) {

    public CustomerId {
        if (value == null || value <= 0) {
            throw new IllegalArgumentException(
                    "CustomerId must be a positive number"
            );
        }
    }
}
```

```java
public record OrderId(Long value) {

    public OrderId {
        if (value == null || value <= 0) {
            throw new IllegalArgumentException(
                    "OrderId must be a positive number"
            );
        }
    }
}
```

Giờ chữ ký service rõ hơn:

```java
void assignCustomer(CustomerId customerId, OrderId orderId) {
    // Hai kiểu ID khác nhau, không thể truyền nhầm trực tiếp.
}
```

`CustomerId` và `OrderId` đều bọc `Long`, nhưng compiler xem chúng là hai kiểu khác nhau.

### 7.1. Writing converter cho CustomerId

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class CustomerIdWritingConverter
        implements Converter<CustomerId, Long> {

    @Override
    public Long convert(CustomerId source) {
        return source.value();
    }
}
```

### 7.2. Reading converter cho CustomerId

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class CustomerIdReadingConverter
        implements Converter<Long, CustomerId> {

    @Override
    public CustomerId convert(Long source) {
        return new CustomerId(source);
    }
}
```

Đăng ký hai converter này cùng các converter enum trong `userConverters()`:

```java
@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new OrderStatusWritingConverter(),
                new OrderStatusReadingConverter(),
                new CustomerIdWritingConverter(),
                new CustomerIdReadingConverter()
        );
    }
}
```

### 7.3. Dùng kiểu định danh riêng trên @Id

Entity có thể dùng wrapper ID:

```java
@Table("customers")
public class Customer {

    @Id
    private CustomerId id;

    @Column("display_name")
    private String displayName;

    protected Customer() {
    }

    public Customer(CustomerId id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public CustomerId getId() {
        return id;
    }
}
```

Repository khai báo đúng kiểu ID:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, CustomerId> {
}
```

Schema vẫn có thể dùng scalar:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(160) NOT NULL
);
```

Khi Spring Data JDBC đọc cột `id`, reading converter tạo `CustomerId`. Khi ghi entity, writing converter lấy giá trị `Long` bên trong để bind vào cột `BIGINT`.

Ví dụ này dùng ID được ứng dụng cung cấp. Nếu dùng database-generated identity với wrapper ID, hãy kiểm thử riêng generated-key assignment với database, driver và phiên bản Spring Data JDBC của dự án. Khả năng chuyển đổi giá trị khi bind query không tự chứng minh mọi cơ chế sinh ID đều hỗ trợ wrapper type theo cùng cách.

### 7.4. Query theo custom ID

Khi repository dùng `CustomerId`, API vẫn nhận kiểu định danh domain:

```java
Optional<Customer> findById(CustomerId id);
```

Một property reference tới khách hàng cũng có thể dùng kiểu wrapper:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private OrderId id;

    @Column("customer_id")
    private CustomerId customerId;
}
```

Repository có thể tìm theo property:

```java
List<PurchaseOrder> findByCustomerId(CustomerId customerId);
```

Spring Data JDBC dùng converter để biểu diễn `CustomerId` thành kiểu scalar tương ứng với cột `customer_id`, khi conversion đã được đăng ký và mapping được cấu hình phù hợp.

## 8. AggregateReference với custom ID type

Khi một aggregate tham chiếu tới aggregate root khác, có thể dùng `AggregateReference` để thể hiện rõ loại đích và kiểu ID.

Ví dụ:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private OrderId id;

    @Column("customer_id")
    private AggregateReference<Customer, CustomerId> customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(OrderId id, CustomerId customerId) {
        this.id = id;
        this.customer = AggregateReference.to(customerId);
    }
}
```

Cột database vẫn có thể là:

```sql
customer_id BIGINT NOT NULL REFERENCES customers(id)
```

`AggregateReference<Customer, CustomerId>` biểu diễn ID tham chiếu tới aggregate `Customer`; nó không tự tải toàn bộ customer object và không tạo cascade persistence.

Khi dùng custom ID wrapper trong reference, hãy kiểm thử cả hai chiều:

- Ghi aggregate order và xác nhận `customer_id` chứa giá trị scalar.
- Đọc order và xác nhận reference chứa `CustomerId`.
- Query theo reference hoặc ID bằng API phù hợp với phiên bản Spring Data JDBC.

Không giả định converter `CustomerId <-> Long` đã đăng ký là đủ cho mọi custom type hoặc mọi cách dùng reference mà không kiểm thử mapping thực tế.

## 9. Kiểu ID khác: UUID và mã định danh chuỗi

Không phải identifier nào cũng là `Long`.

### 9.1. UUID

Nếu domain dùng UUID wrapper:

```java
public record TenantId(UUID value) {
    public TenantId {
        Objects.requireNonNull(value);
    }
}
```

Và database có cột UUID, converter có thể chuyển:

- `TenantId -> UUID` khi ghi.
- `UUID -> TenantId` khi đọc.

Ví dụ:

```java
@WritingConverter
public class TenantIdWritingConverter
        implements Converter<TenantId, UUID> {

    @Override
    public UUID convert(TenantId source) {
        return source.value();
    }
}
```

```java
@ReadingConverter
public class TenantIdReadingConverter
        implements Converter<UUID, TenantId> {

    @Override
    public TenantId convert(UUID source) {
        return new TenantId(source);
    }
}
```

Khả năng JDBC driver trả UUID dưới dạng `UUID`, `String` hoặc kiểu vendor-specific có thể khác nhau. Nếu driver trả kiểu khác, cần converter đúng source type hoặc RowMapper tùy chỉnh.

### 9.2. Mã định danh chuỗi

Một domain có thể dùng mã như `CUS-2026-00042`:

```java
public record CustomerNumber(String value) {
    public CustomerNumber {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer number is required"
            );
        }
    }
}
```

Converter có thể ánh xạ `CustomerNumber <-> String`. Database lưu `VARCHAR`, còn service không phải truyền chuỗi tự do ở mọi nơi.

Hãy phân biệt ID kỹ thuật (primary key) với business identifier. Một business identifier có thể có unique constraint nhưng không nhất thiết là `@Id` của aggregate.

## 10. Converter và nullability

Converter nên tập trung chuyển đổi giá trị hợp lệ. Với SQL NULL, conversion infrastructure thường giữ giá trị null theo quy tắc null handling của Spring; không nên dựa vào việc converter luôn nhận được `null`.

Ví dụ nếu `status_code` nullable:

- Entity dùng `OrderStatus` có thể nhận null nếu domain cho phép.
- Nếu domain bắt buộc có trạng thái, schema nên dùng `NOT NULL` và dữ liệu cần được backfill.
- Nếu muốn biểu diễn trạng thái chưa xác định, có thể dùng một enum constant riêng hoặc giữ property nullable theo quyết định domain.

Đối với wrapper ID:

- Primary key thường phải NOT NULL.
- Foreign key tùy quan hệ có thể nullable nếu reference là tùy chọn.
- Constructor của value object có thể từ chối null; khi đó schema và dữ liệu phải bảo đảm giá trị tồn tại.

Ví dụ:

```sql
customer_id BIGINT NULL
```

có thể biểu diễn reference tùy chọn. Nếu entity dùng `CustomerId` non-nullable, hãy bảo đảm mapping và domain constructor xử lý trạng thái vắng mặt theo đúng ý nghĩa nghiệp vụ; đừng ép `NULL` thành ID giả như `0`.

## 11. Converter nên xử lý dữ liệu không hợp lệ thế nào?

Converter đọc là ranh giới giữa dữ liệu database và kiểu domain. Nếu dữ liệu không hợp lệ, có một số chính sách:

| Chính sách | Cách làm | Khi phù hợp |
|---|---|---|
| Fail fast | Ném exception với code không nhận diện | Dữ liệu phải thuộc tập code đã định nghĩa |
| Legacy alias | Chấp nhận nhiều code cũ/mới khi đọc | Đang migration theo giai đoạn |
| UNKNOWN | Ánh xạ code lạ sang enum `UNKNOWN` | Domain cho phép trạng thái chưa biết và caller xử lý được |
| Quarantine/repair | Ghi nhận dữ liệu lỗi và xử lý qua job riêng | Dữ liệu ngoại lai cần điều tra |

Nếu dùng `UNKNOWN`, hãy quyết định:

- Có cho phép ghi `UNKNOWN` trở lại database không?
- Có được phép thực hiện domain action trên trạng thái này không?
- Có cần lưu nguyên code lạ để không mất thông tin khi round-trip không?

Một enum chỉ có `UNKNOWN` sẽ làm mất code gốc nếu converter không giữ giá trị đó ở nơi khác. Với hệ thống cần forward compatibility, đôi khi một value object chứa raw code phù hợp hơn enum đóng.

### 11.1. Đưa ngữ cảnh vào lỗi conversion

Lỗi converter nên chứa giá trị không hợp lệ và loại dữ liệu, nhưng tránh đưa thông tin nhạy cảm vào log. Ví dụ:

```java
throw new IllegalArgumentException(
        "Unknown OrderStatus code: " + source
);
```

Nếu mã có thể chứa dữ liệu bí mật, dùng thông báo tổng quát và log có kiểm soát.

## 12. Converter cho nhiều kiểu domain

Một cấu hình có thể đăng ký nhiều cặp converter:

```java
@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new OrderStatusWritingConverter(),
                new OrderStatusReadingConverter(),
                new CustomerIdWritingConverter(),
                new CustomerIdReadingConverter(),
                new OrderIdWritingConverter(),
                new OrderIdReadingConverter(),
                new TenantIdWritingConverter(),
                new TenantIdReadingConverter()
        );
    }
}
```

Để tránh cấu hình phình to:

- Đặt converter gần kiểu domain hoặc trong package persistence adapter.
- Dùng tên class mô tả rõ hướng đọc/ghi.
- Không tạo nhiều converter trùng source/target nếu không có lý do.
- Dùng annotation hướng chuyển đổi cho converter scalar.
- Viết test riêng cho từng cặp converter quan trọng.
- Chỉ đăng ký converter thật sự được mapping sử dụng.

Nếu nhiều identifier wrapper cùng bọc `Long`, không tạo một generic converter `Long -> Object` để suy đoán loại ID. Hãy dùng converter cụ thể `Long -> CustomerId`, `Long -> OrderId` để giữ kiểu đích rõ ràng.

## 13. Converter Spring Data JDBC và JdbcTemplate trực tiếp

Một điểm dễ nhầm: converter đăng ký cho Spring Data JDBC thuộc conversion infrastructure của Spring Data mapping. Nó không biến mọi lệnh `JdbcTemplate` thành lệnh tự hiểu mọi domain type.

Ví dụ aggregate repository có thể map `OrderStatus` theo converter đã đăng ký. Nhưng khi gọi trực tiếp:

```java
jdbcTemplate.update(
        "UPDATE orders SET status_code = ? WHERE id = ?",
        status,
        orderId
);
```

không nên giả định `JdbcTemplate` sẽ tự sử dụng custom conversion của Spring Data JDBC cho `OrderStatus`.

Với direct JDBC, truyền giá trị scalar tường minh:

```java
jdbcTemplate.update(
        "UPDATE orders SET status_code = ? WHERE id = ?",
        status.getCode(),
        orderId
);
```

Tương tự với wrapper ID:

```java
jdbcTemplate.queryForObject(
        "SELECT display_name FROM customers WHERE id = ?",
        String.class,
        customerId.value()
);
```

Hoặc viết `PreparedStatementSetter`, `RowMapper` hay `SqlParameterSource` để điều khiển chuyển đổi.

Ranh giới cần nhớ:

- Repository/`JdbcAggregateTemplate`: Spring Data JDBC mapping và custom conversions.
- `JdbcTemplate`: JDBC API trực tiếp; caller chịu trách nhiệm bind/extract kiểu dữ liệu.
- `@Query`: SQL được Spring Data JDBC thực thi qua repository infrastructure; kiểm tra mapping và parameter conversion theo phiên bản.

## 14. Migration khi thay đổi enum code hoặc identifier representation

Thay đổi code lưu trữ là thay đổi hợp đồng dữ liệu, cần kế hoạch tương thích.

Ví dụ cột hiện tại lưu `PAID`, muốn chuyển sang `P`.

Một chiến lược migration an toàn có thể gồm:

1. Cập nhật reading converter để hiểu cả `PAID` và `P`.
2. Triển khai writer mới chỉ ghi `P`.
3. Kiểm tra mọi ứng dụng/worker cùng ghi bảng đã dùng writer mới.
4. Chạy migration cập nhật các hàng cũ.
5. Kiểm tra số lượng code cũ còn lại.
6. Gỡ hỗ trợ đọc code cũ trong một release sau.

Với identifier, chuyển từ `Long` sang UUID hoặc business ID có thể ảnh hưởng foreign key, index, API và tích hợp. Không chỉ thay kiểu Java và converter; phải migration schema và dữ liệu có thứ tự, bảo đảm các FK được cập nhật nhất quán.

Nếu hệ thống có nhiều phiên bản ứng dụng chạy song song, cần giữ khả năng đọc/ghi tương thích trong giai đoạn rollout.

## 15. Kiểm thử converter và repository mapping

Nên kiểm thử ở hai mức: converter đơn lẻ và integration test với database.

### 15.1. Unit test enum converter

```java
class OrderStatusConverterTest {

    private final OrderStatusWritingConverter writer =
            new OrderStatusWritingConverter();

    private final OrderStatusReadingConverter reader =
            new OrderStatusReadingConverter();

    @Test
    void writesStableCode() {
        assertThat(writer.convert(OrderStatus.PAID))
                .isEqualTo("P");
    }

    @Test
    void readsStableCode() {
        assertThat(reader.convert("P"))
                .isEqualTo(OrderStatus.PAID);
    }

    @Test
    void rejectsUnknownCode() {
        assertThatThrownBy(() -> reader.convert("Z"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
```

Unit test xác nhận quy tắc code độc lập với database. Với legacy alias, thêm test cho từng alias cần hỗ trợ.

### 15.2. Unit test identifier converter

```java
class CustomerIdConverterTest {

    @Test
    void convertsIdToDatabaseScalar() {
        CustomerIdWritingConverter writer =
                new CustomerIdWritingConverter();

        assertThat(writer.convert(new CustomerId(42L)))
                .isEqualTo(42L);
    }

    @Test
    void convertsDatabaseScalarToId() {
        CustomerIdReadingConverter reader =
                new CustomerIdReadingConverter();

        assertThat(reader.convert(42L))
                .isEqualTo(new CustomerId(42L));
    }
}
```

### 15.3. Integration test round-trip

Một repository test có thể xác nhận converter đã được đăng ký đúng:

```java
@DataJdbcTest
class PurchaseOrderConversionTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void storesEnumCodeAndReadsDomainEnum() {
        PurchaseOrder order =
                new PurchaseOrder("PO-100", OrderStatus.PAID);

        PurchaseOrder saved = orders.save(order);

        String storedCode = jdbc.queryForObject(
                "SELECT status_code FROM orders WHERE id = ?",
                String.class,
                saved.getId()
        );

        assertThat(storedCode).isEqualTo("P");

        PurchaseOrder loaded = orders.findById(saved.getId())
                .orElseThrow();

        assertThat(loaded.getStatus()).isEqualTo(OrderStatus.PAID);
    }
}
```

Test này kiểm tra hai hướng:

- Khi save, database nhận code `P`.
- Khi load, entity nhận `OrderStatus.PAID`.

Tên constructor/getter và kiểu ID trong test cần khớp entity thật của dự án.

### 15.4. Integration test custom identifier

Với `CustomerId`, kiểm tra:

1. Save entity có ID `new CustomerId(42L)`.
2. Database lưu scalar `42`.
3. `findById(new CustomerId(42L))` tìm được entity.
4. Entity được đọc có ID kiểu `CustomerId`.
5. Query method nhận custom ID hoạt động đúng.
6. Nếu dùng generated ID, test riêng generated-key path trên database/driver thật.

### 15.5. Kiểm tra dữ liệu không hợp lệ

Chèn trực tiếp code không được hỗ trợ:

```sql
INSERT INTO orders (id, order_code, status_code)
VALUES (999, 'PO-999', 'Z');
```

Sau đó đọc qua repository. Xác nhận ứng dụng xử lý theo chính sách đã chọn: fail fast, UNKNOWN hoặc legacy mapping. Không để dữ liệu lỗi chỉ xuất hiện ở production mới được phát hiện.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Enum lưu tên constant thay vì code | Chưa đăng ký writing converter hoặc converter không được module nhận | Kiểm tra `userConverters()` và chiều converter |
| Đọc code `P` thất bại | Thiếu reading converter hoặc code chưa được hỗ trợ | Đăng ký converter đọc và kiểm tra dữ liệu |
| Converter `String -> Enum` bị mơ hồ | Chưa đánh dấu `@ReadingConverter` | Đánh dấu đúng chiều đọc |
| Save được nhưng reload lỗi | Có writing converter nhưng thiếu reading converter | Đăng ký cả hai chiều |
| Đổi tên enum làm dữ liệu cũ lỗi | Database lưu `Enum.name()` | Dùng code ổn định và migration dữ liệu |
| Dùng ordinal khiến trạng thái đổi nghĩa | Thứ tự enum đã thay đổi | Dùng code tường minh, không lưu ordinal |
| Custom ID không map được | Chưa đăng ký converter hoặc kiểu đích không được nhận diện | Đăng ký cặp converter cụ thể và test repository |
| Repository generic ID vẫn dùng `Long` | Chữ ký repository không khớp kiểu ID domain | Dùng `CrudRepository<Entity, CustomerId>` |
| `AggregateReference` không chuyển đúng ID | Converter/reference mapping chưa được kiểm chứng | Test save/load reference với đúng version |
| Direct JdbcTemplate không hiểu enum | Spring Data custom conversion không tự áp dụng cho JDBC API trực tiếp | Bind `status.getCode()` hoặc viết mapper/setter |
| Unknown code bị map sai | Reading converter dùng default không rõ ràng | Chọn fail-fast, alias hoặc UNKNOWN có chủ đích |
| Generated wrapper ID không được gán | Generated-key path khác conversion scalar thông thường | Test driver/version; cân nhắc ID ứng dụng cấp hoặc kiểu ID persistence riêng |

## 17. Nguyên tắc thiết kế

Khi thiết kế custom value mapping:

- **Tách domain value khỏi storage representation.** Enum và identifier có thể có kiểu Java riêng trong khi database lưu scalar.
- **Dùng code ổn định cho enum.** Không dùng ordinal và tránh phụ thuộc lâu dài vào tên constant.
- **Đăng ký đủ hai chiều.** Reading converter tạo domain value; writing converter tạo database value.
- **Đánh dấu hướng chuyển đổi.** Dùng `@ReadingConverter` và `@WritingConverter` để tránh mơ hồ.
- **Dùng wrapper cho identifier.** `CustomerId`, `OrderId` giúp ngăn truyền nhầm các ID cùng kiểu scalar.
- **Giữ converter nhỏ và cụ thể.** Mỗi cặp source/target phải có ý nghĩa rõ.
- **Xử lý code lạ có chủ đích.** Fail-fast, legacy alias hoặc UNKNOWN đều cần quy tắc nghiệp vụ.
- **Phân biệt Spring Data mapping với JdbcTemplate.** Direct JDBC cần bind/extract scalar tường minh.
- **Migration là một phần của thay đổi mapping.** Converter mới phải tương thích với dữ liệu đang có trong giai đoạn rollout.
- **Kiểm thử round-trip trên database.** Xác nhận giá trị vật lý, giá trị domain, nullability và generated ID behavior.

Với Spring Data Relational JDBC, custom converters giúp domain model giữ được kiểu và ý nghĩa riêng mà không buộc schema phải lưu đúng cách biểu diễn của Java. Enum có code ổn định giúp dữ liệu bền vững khi đổi tên constant; value object ID giúp chữ ký repository và service an toàn hơn. Hãy định nghĩa rõ cả chiều đọc lẫn ghi, đăng ký converter đúng module, migration dữ liệu khi đổi hợp đồng và kiểm thử với database thực tế.

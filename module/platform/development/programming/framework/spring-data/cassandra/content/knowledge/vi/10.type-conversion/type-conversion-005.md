# Chuyển đổi kiểu giá trị nghiệp vụ sang kiểu CQL trong Spring Data Cassandra

## 1. Bài toán: Java có value object, Cassandra có kiểu lưu trữ

Trong **Spring Data Cassandra**, ứng dụng Java thường dùng những kiểu biểu đạt ý nghĩa nghiệp vụ, chẳng hạn `OrderAmount`, `CurrencyCode`, `CustomerCode` hoặc `Measurement`. Các kiểu đó có quy tắc tạo đối tượng, so sánh và kiểm tra dữ liệu riêng. Trong khi đó, **Apache Cassandra** lưu mỗi cột theo một kiểu CQL như `decimal`, `text`, `uuid`, `timestamp` hoặc user-defined type (UDT).

Ví dụ, nghiệp vụ hóa đơn muốn lưu **tổng tiền 125000,50 VND**:

- Trong Java, `OrderAmount` đóng gói `BigDecimal` và quy tắc độ chính xác; `CurrencyCode` đảm bảo mã tiền tệ có định dạng thống nhất.
- Trong Cassandra, bảng có thể lưu `total_amount decimal` và `currency_code text`.
- Khi lưu, Spring Data cần chuyển từ **value object → giá trị mà CQL/driver có thể ghi**.
- Khi đọc, Spring Data cần chuyển từ **giá trị CQL/driver → value object đã được kiểm tra hợp lệ**.

Đó là nhiệm vụ của **type conversion**, thường được thực hiện bằng cơ chế chuyển đổi mặc định hoặc **custom converters** của Spring Data Cassandra. Bài này tập trung vào **chuyển đổi kiểu giá trị nghiệp vụ sang kiểu CQL**, thuộc chương **Chuyển đổi kiểu** của module `SPRING_DATA_CASSANDRA`.

Sau bài học, bạn sẽ có thể:

1. Nhận diện khi nào mapper mặc định đủ dùng và khi nào nên viết converter.
2. Thiết kế cặp converter **ghi và đọc** cho một value object.
3. Đăng ký converter vào `CassandraCustomConversions` và sử dụng với entity, repository, `CassandraTemplate`.
4. Giữ đúng độ chính xác số, đơn vị, múi giờ, giá trị `null` và định danh khóa.
5. Kiểm thử **round-trip** Java ↔ CQL, đồng thời nhận ra những vấn đề conversion **không thể giải quyết** như partition key sai, consistency hoặc paging không phù hợp.

## 2. Phân biệt ba tầng chuyển đổi dữ liệu

~~~mermaid
flowchart LR
    A[Entity Java: OrderAmount] --> B[Spring Data Cassandra Mapping Converter]
    B --> C[Giá trị Java cơ sở: BigDecimal]
    C --> D[Java driver và CQL codec]
    D --> E[(Cassandra: decimal)]
    E --> D
    D --> C
    C --> B
    B --> A
~~~

| Tầng | Công việc | Ví dụ |
| --- | --- | --- |
| **Domain/value object** | Diễn đạt ràng buộc và ý nghĩa nghiệp vụ | `OrderAmount` phải được chuẩn hóa về 2 chữ số thập phân |
| **Spring Data mapping/conversion** | Ánh xạ field entity, chuyển object sang kiểu dữ liệu Java mà driver hiểu | `OrderAmount` ↔ `BigDecimal` |
| **Java driver codec** | Mã hóa/giải mã giá trị Java sang wire protocol CQL | `BigDecimal` ↔ CQL `decimal` |

Annotation `@Table`, `@Column`, `@PrimaryKey` giúp Spring Data biết **lưu ở bảng/cột nào**. Annotation `@CassandraType` có thể chỉ rõ **kiểu CQL mong muốn** của thuộc tính. Custom converter giúp Spring Data biết **biến một kiểu Java tùy biến thành giá trị lưu trữ và ngược lại**.

Các thành phần này **không đồng nghĩa**:

- `Converter<OrderAmount, BigDecimal>` giải quyết phép biến đổi **đối tượng domain ↔ Java type cơ sở** ở tầng Spring Data.
- `@CassandraType(type = CassandraType.Name.DECIMAL)` chỉ ra **kiểu CQL decimal** của cột.
- Driver codec quản lý việc biểu diễn `BigDecimal` theo giao thức Cassandra. Bạn thường **không cần tự viết codec** khi kiểu lưu trữ đã được driver hỗ trợ.
- Câu CQL chạy qua `CqlSession` trực tiếp thường dùng **driver codec**, không tự áp dụng các converter tùy biến của `MappingCassandraConverter` như khi lưu entity qua repository/template.

Đây là điểm quan trọng khi ứng dụng đồng thời dùng `CassandraRepository`, `CassandraTemplate` và CQL trực tiếp.

## 3. Bản đồ kiểu Java và kiểu CQL thường gặp

Trước khi thêm custom converter, kiểm tra khả năng mapping sẵn có của Spring Data Cassandra và driver theo phiên bản đang dùng.

| CQL | Kiểu Java thường dùng | Điều cần chú ý |
| --- | --- | --- |
| `text` / `varchar` | `String` | Dữ liệu có quy tắc chuẩn hóa/validation nghiệp vụ nên được đóng gói thành value object ở tầng domain |
| `ascii` | `String` | Chỉ dành cho chuỗi ASCII; không dùng cho tên tiếng Việt có dấu |
| `boolean` | `Boolean` | Phân biệt `false` và `null` nếu business cần trạng thái “chưa biết” |
| `int` | `Integer` | Giới hạn số nguyên 32-bit |
| `bigint` | `Long` | Giới hạn số nguyên 64-bit; không nhầm với Java `BigInteger` |
| `varint` | `BigInteger` | Số nguyên độ dài biến thiên; đánh giá kích thước/lưu trữ |
| `decimal` | `BigDecimal` | Giữ phần thập phân; tránh đi qua `double` khi xử lý tiền |
| `float` / `double` | `Float` / `Double` | Số dấu phẩy động; không phù hợp với yêu cầu tiền tệ chính xác tuyệt đối |
| `uuid` | `UUID` | Kiểu định danh UUID thông thường |
| `timeuuid` | `UUID` có quy tắc version phù hợp | Dùng time UUID hợp lệ; không coi UUID ngẫu nhiên v4 là timeuuid |
| `date` | `LocalDate` | Ngày lịch không mang thời gian/múi giờ |
| `time` | `LocalTime` | Thời gian trong ngày, không mang ngày/múi giờ |
| `timestamp` | `Instant` hoặc kiểu thời gian được mapper hỗ trợ | CQL timestamp có độ chính xác mili giây; chú ý quy tắc chuyển đổi |
| `blob` | `ByteBuffer` / `byte[]` theo hỗ trợ | Kiểm soát kích thước, copy mutable buffer và cách codec xử lý |
| `list<text>`, `set<uuid>`, `map<text,text>` | `List<String>`, `Set<UUID>`, `Map<String,String>` | Kiểu phần tử và kích thước collection phải phù hợp access pattern |
| `frozen<address_type>` | Lớp Java `@UserDefinedType` | UDT có schema riêng trong keyspace, converter và mapping cần tương thích |

**Không nên tự định nghĩa converter chỉ để đổi `BigDecimal` thành `String` rồi lưu ở `text`** nếu dữ liệu vẫn cần so sánh/truy vấn số ở CQL. Kiểu lưu trữ quyết định ngữ nghĩa truy vấn và khả năng thao tác. Ví dụ, thứ tự từ điển của `"100"` và `"20"` khác thứ tự số.

## 4. Bắt đầu từ schema thiết kế theo truy vấn

Giả sử ứng dụng cần tìm hóa đơn **theo ID**:

~~~sql
-- Trong keyspace đã chuẩn bị theo topology thử nghiệm.
CREATE TABLE IF NOT EXISTS orders_by_id (
    order_id uuid PRIMARY KEY,
    total_amount decimal,
    currency_code text,
    state text,
    created_at timestamp
);
~~~

Schema này có các lựa chọn có chủ đích:

1. `order_id` là primary key, dùng để tìm một hóa đơn cụ thể.
2. `total_amount` dùng **`decimal`**, phù hợp dữ liệu tiền cần độ chính xác xác định.
3. `currency_code` dùng `text` vì đây là **mã**, không phải phép toán số.
4. `state` minh họa trạng thái nghiệp vụ; có thể ánh xạ bằng `String` hoặc value object khác.
5. `created_at` dùng `timestamp`, phù hợp lưu **thời điểm**.

Trong hệ thống cần liệt kê hóa đơn theo khách hàng và ngày, có thể cần bảng khác như `orders_by_customer_day` với partition key phù hợp. **Type converter không tạo chỉ mục, không chọn partition key và không cải thiện truy vấn CQL sai mô hình**.

Một kiểu `Money` gồm cả số tiền và loại tiền có thể là **aggregate value object** ở tầng domain. Tuy nhiên bảng minh họa lưu nó trong **hai cột**. Converter dạng `Converter<Money, BigDecimal>` **không tự tách một object thành hai cột**; ta sẽ biểu diễn hai thành phần thành **hai field được mapping**. Nếu cần một cột duy nhất chứa cấu trúc, cân nhắc UDT và `@UserDefinedType` với schema phù hợp.

## 5. Thiết kế value object nghiệp vụ bất biến

### 5.1. Amount: ràng buộc độ chính xác ngay khi tạo

Lớp dưới đây lưu số tiền với **2 chữ số thập phân**. Đây là **quy tắc minh họa của ứng dụng**, không phải quy tắc chung cho mọi tiền tệ; nhiều hệ thống có đơn vị tiền/đơn vị đo với số chữ số thập phân khác nhau.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class OrderAmount {
    private final BigDecimal value;

    public OrderAmount(BigDecimal value) {
        Objects.requireNonNull(value, "value");
        // Từ chối giá trị có thêm chữ số có ý nghĩa, không tự làm tròn âm thầm.
        this.value = value.setScale(2, RoundingMode.UNNECESSARY);
    }

    public BigDecimal value() {
        return value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderAmount)) return false;
        OrderAmount that = (OrderAmount) other;
        return value.equals(that.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}
~~~

**Vì sao dùng `setScale(2, RoundingMode.UNNECESSARY)`?** Nó chấp nhận `125.5` thành `125.50` nhưng từ chối `125.555`, vì giảm xuống hai chữ số sẽ làm mất dữ liệu. Sau chuẩn hóa, `BigDecimal.equals` và `hashCode` nhất quán với quy tắc scale của value object. Nếu nghiệp vụ cần làm tròn, hãy chọn chính sách làm tròn **rõ ràng trước khi tạo value object**, không ngầm làm tròn trong converter.

Lớp không có setter và giữ `BigDecimal` bất biến. Số âm có thể hợp lệ cho hoàn tiền hoặc bút toán điều chỉnh; nếu nghiệp vụ cấm số âm, thêm quy tắc kiểm tra ở **domain constructor** chứ không gán mặc định chung cho mọi hệ thống.

### 5.2. CurrencyCode: chuẩn hóa mã

~~~java
import java.util.Locale;
import java.util.Objects;

public final class CurrencyCode {
    private final String value;

    public CurrencyCode(String raw) {
        Objects.requireNonNull(raw, "raw");
        String normalized = raw.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "Currency code must be three ASCII letters");
        }
        this.value = normalized;
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof CurrencyCode)) return false;
        return value.equals(((CurrencyCode) other).value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}
~~~

Kiểm tra `[A-Z]{3}` chỉ kiểm tra **định dạng**, **không khẳng định đó là mã ISO 4217 tồn tại**. Nếu cần kiểm tra tập mã hợp lệ, dùng danh mục chính thức hoặc dữ liệu danh mục do ứng dụng quản lý. Việc đổi `"vnd"` thành `"VND"` là chính sách canonicalization của domain.

### 5.3. Vì sao nên chuyển đổi từ value object, không lấy String ở mọi nơi?

Nếu mọi service thao tác trực tiếp `String currency` và `BigDecimal amount`, rất dễ bỏ quên validation hoặc chuẩn hóa. Đóng gói quy tắc trong constructor giúp mọi đường tạo giá trị, bao gồm dữ liệu đọc từ database, tuân thủ **cùng một định nghĩa nghiệp vụ**. Conversion sau đó chỉ còn nhiệm vụ biến giá trị đã hợp lệ thành kiểu cơ sở và ngược lại.

## 6. Viết cặp converter đọc/ghi bằng Spring Data

Spring Data hỗ trợ interface `org.springframework.core.convert.converter.Converter<S,T>`. Hai annotation đánh dấu hướng:

- **`@WritingConverter`:** được dùng khi **ghi** đối tượng domain xuống giá trị phù hợp với Cassandra.
- **`@ReadingConverter`:** được dùng khi **đọc** giá trị từ Cassandra thành object domain.

### 6.1. Chuyển OrderAmount ↔ BigDecimal

~~~java
import java.math.BigDecimal;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class OrderAmountWritingConverter
        implements Converter<OrderAmount, BigDecimal> {

    @Override
    public BigDecimal convert(OrderAmount source) {
        return source.value();
    }
}

@ReadingConverter
public final class OrderAmountReadingConverter
        implements Converter<BigDecimal, OrderAmount> {

    @Override
    public OrderAmount convert(BigDecimal source) {
        return new OrderAmount(source);
    }
}
~~~

**Chiều ghi:** `OrderAmount(BigDecimal("125000.50"))` → `BigDecimal("125000.50")` → CQL `decimal`.

**Chiều đọc:** CQL `decimal` → `BigDecimal("125000.50")` → `OrderAmount`. Constructor domain tiếp tục thực hiện kiểm tra scale và validation.

Nếu dữ liệu cũ có scale/dải giá trị **không tuân thủ quy tắc mới**, phép đọc có thể ném ngoại lệ khi tạo `OrderAmount`. Đây là **tín hiệu không tương thích dữ liệu**, cần migration hoặc chiến lược xử lý dữ liệu legacy; không nên âm thầm bắt ngoại lệ rồi thay bằng `0`.

### 6.2. Chuyển CurrencyCode ↔ String

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class CurrencyCodeWritingConverter
        implements Converter<CurrencyCode, String> {

    @Override
    public String convert(CurrencyCode source) {
        return source.value();
    }
}

@ReadingConverter
public final class CurrencyCodeReadingConverter
        implements Converter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String source) {
        return new CurrencyCode(source);
    }
}
~~~

Nếu database lưu `"vnd"` từ trước, `CurrencyCodeReadingConverter` sẽ đưa về `"VND"`. Điều này giúp value object chuẩn hóa, nhưng **không tự sửa dữ liệu đã lưu trong Cassandra**. Những yêu cầu như lọc theo chính xác `currency_code = 'VND'` vẫn phải xét tình trạng dữ liệu gốc nếu từng có mã không thống nhất.

### 6.3. Tại sao khai báo rõ hướng converter?

Với các cặp chuyển đổi giữa kiểu đơn giản và domain object, Spring Data có thể khó suy luận hướng nếu nhiều chuyển đổi liên quan kiểu native như `String`, `BigDecimal`. Annotation `@ReadingConverter` và `@WritingConverter` làm rõ intent, giảm nguy cơ framework áp dụng chuyển đổi ở hướng không mong muốn. Khi có nhiều value object cùng chuyển từ `String`, **kiểu đích của property** giúp phân biệt phép đọc; vẫn cần test đúng các field trong entity.

## 7. Đăng ký converter vào CassandraCustomConversions

Định nghĩa các converter thôi chưa đủ; Spring Data Cassandra phải biết chúng khi tạo **`MappingCassandraConverter`**. Một cách đăng ký thường dùng là khai báo bean `CassandraCustomConversions`.

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.convert.CassandraCustomConversions;

@Configuration(proxyBeanMethods = false)
public class DomainCassandraConversionsConfig {

    @Bean
    public CassandraCustomConversions cassandraCustomConversions() {
        return new CassandraCustomConversions(List.of(
            new OrderAmountWritingConverter(),
            new OrderAmountReadingConverter(),
            new CurrencyCodeWritingConverter(),
            new CurrencyCodeReadingConverter()
        ));
    }
}
~~~

Ví dụ minh họa cách đăng ký thường gặp trong Spring Data Cassandra. **API khởi tạo và cách Spring Boot tích hợp bean custom conversions có thể thay đổi theo phiên bản**: cần đối chiếu bộ Spring Boot/Spring Data Cassandra của dự án và kiểm chứng với một bài test tích hợp. Nếu dự án đã có bean `CassandraCustomConversions`, hãy **bổ sung các converter mới vào cấu hình chung** thay vì khai báo một bean trùng tên hoặc ghi đè danh sách converter đang dùng.

Nếu ứng dụng tự định nghĩa `MappingCassandraConverter` hoặc nhiều bean `CassandraTemplate`, cần bảo đảm **đúng converter instance được gắn vào đúng mapping converter/template**. Có nhiều session tới các keyspace khác nhau không tự bảo đảm các template sử dụng cùng cấu hình custom conversions.

~~~mermaid
flowchart TD
    A[DomainCassandraConversionsConfig] --> B[CassandraCustomConversions]
    B --> C[MappingCassandraConverter]
    C --> D[CassandraTemplate]
    D --> E[Repository dùng CassandraTemplate]
    D --> F[CQL qua Java driver]
~~~

**Phân biệt rõ:** custom converters được Spring Data áp dụng trong **luồng mapping của nó**. Nếu một service gọi `CqlSession.execute(...)` trực tiếp với tham số `OrderAmount` mà không tự chuyển, driver không tự nhận biết `OrderAmount` chỉ vì bean Spring `CassandraCustomConversions` tồn tại.

## 8. Entity ánh xạ đúng kiểu CQL

Một entity Java có thể giữ **value object ở các thuộc tính** và chỉ rõ kiểu Cassandra ở những cột cần thiết:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.CassandraType;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderRow {

    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("total_amount")
    @CassandraType(type = CassandraType.Name.DECIMAL)
    private OrderAmount totalAmount;

    @Column("currency_code")
    @CassandraType(type = CassandraType.Name.TEXT)
    private CurrencyCode currencyCode;

    @Column("state")
    private String state;

    @Column("created_at")
    private Instant createdAt;

    public OrderRow() {
    }

    public OrderRow(UUID orderId, OrderAmount totalAmount,
                    CurrencyCode currencyCode, String state,
                    Instant createdAt) {
        this.orderId = orderId;
        this.totalAmount = totalAmount;
        this.currencyCode = currencyCode;
        this.state = state;
        this.createdAt = createdAt;
    }

    public UUID getOrderId() { return orderId; }
    public OrderAmount getTotalAmount() { return totalAmount; }
    public CurrencyCode getCurrencyCode() { return currencyCode; }
    public String getState() { return state; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

Class này minh họa trường bất biến theo **quy ước sử dụng** (không có setter công khai). Mapper vẫn cần cơ chế tạo/gán entity phù hợp; ví dụ có constructor không tham số và field không `final` để đơn giản hóa việc ánh xạ. Nếu yêu cầu entity bất biến hoàn toàn, có thể dùng constructor binding khi được hỗ trợ và kiểm thử với phiên bản Spring Data thực tế.

| Thuộc tính Java | Đích CQL | Chuyển đổi cần thiết |
| --- | --- | --- |
| `UUID orderId` | `order_id uuid` | Mapping/codec mặc định |
| `OrderAmount totalAmount` | `total_amount decimal` | Custom viết `OrderAmount → BigDecimal`, đọc `BigDecimal → OrderAmount` |
| `CurrencyCode currencyCode` | `currency_code text` | Custom viết `CurrencyCode → String`, đọc `String → CurrencyCode` |
| `String state` | `state text` | Mapping/codec mặc định |
| `Instant createdAt` | `created_at timestamp` | Mapping thời gian phù hợp driver/Spring Data, có giới hạn độ chính xác |

**Lưu ý:** `@CassandraType` là phần thông tin mapping CQL. Việc converter được gọi chính xác ra sao còn phụ thuộc phiên bản và cấu hình `CassandraCustomConversions`. Cần kiểm chứng cả *Java value đã đọc* lẫn *raw CQL value đã lưu*, không chỉ gọi `save` thành công.

## 9. Lưu và đọc qua repository, CassandraTemplate, CqlSession

### 9.1. Repository: conversion đi cùng mapping

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderRepository
        extends CassandraRepository<OrderRow, UUID> {
}
~~~

Trong một service/test có `OrderRepository repository` đã được inject:

~~~java
UUID id = UUID.randomUUID();
OrderRow order = new OrderRow(
    id,
    new OrderAmount(new BigDecimal("125000.50")),
    new CurrencyCode("vnd"),
    "CREATED",
    Instant.parse("2026-11-25T02:00:00Z")
);

repository.save(order);
OrderRow loaded = repository.findById(id).orElseThrow();

assertEquals(new OrderAmount(new BigDecimal("125000.50")),
             loaded.getTotalAmount());
assertEquals(new CurrencyCode("VND"), loaded.getCurrencyCode());
~~~

Đoạn này dùng các kiểu Java/JUnit tương ứng và yêu cầu Cassandra/schema đã chuẩn bị. Nó kiểm tra phép biến đổi hai chiều ở mức repository. Những thay đổi ở dữ liệu CQL thực tế vẫn cần được đối chiếu bằng truy vấn độc lập khi test.

### 9.2. CassandraTemplate dùng cùng quy tắc nếu chung converter

~~~java
import org.springframework.data.cassandra.core.CassandraOperations;

public class OrderService {
    private final CassandraOperations operations;

    public OrderService(CassandraOperations operations) {
        this.operations = operations;
    }

    public OrderRow load(UUID id) {
        return operations.selectOneById(id, OrderRow.class);
    }

    public OrderRow insert(OrderRow order) {
        return operations.insert(order);
    }
}
~~~

`CassandraTemplate` triển khai `CassandraOperations` và đi qua mapping converter tương ứng khi thao tác entity. Tuy nhiên các lệnh CQL dạng chuỗi thuần, raw row mapping hoặc các thành phần dùng `CqlSession` trực tiếp có thể đi qua **đường chuyển đổi khác**. Test chính xác loại thao tác bạn dùng trong production.

### 9.3. Raw CQL dùng kiểu được driver hỗ trợ

Khi gọi Java driver 4.x trực tiếp, chuẩn bị statement và bind `BigDecimal`/`String`:

~~~java
PreparedStatement ps = session.prepare(
    "INSERT INTO orders_by_id " +
    "(order_id, total_amount, currency_code, state, created_at) " +
    "VALUES (?, ?, ?, ?, ?)"
);

OrderAmount amount = new OrderAmount(new BigDecimal("125000.50"));
CurrencyCode currency = new CurrencyCode("VND");

session.execute(ps.bind(
    id,
    amount.value(),        // BigDecimal, không bind thẳng OrderAmount
    currency.value(),      // String, không bind thẳng CurrencyCode
    "CREATED",
    Instant.parse("2026-11-25T02:00:00Z")
));
~~~

Ví dụ cần `session` đã được cấu hình và import driver classes. Khi dùng CQL có tên bảng không chỉ rõ keyspace, `CqlSession` phải chọn đúng keyspace mặc định; trong ứng dụng nhiều keyspace nên cân nhắc CQL `keyspace.table` đầy đủ.

**Không tự nối input vào câu CQL**. Bind parameter bảo vệ tính đúng đắn của kiểu và tránh những vấn đề injection, đồng thời giảm chi phí prepare lặp lại.

## 10. Những ranh giới không thể bỏ qua

### 10.1. Precision, scale, rounding của số thập phân

Không đi qua `double` khi chuyển một lượng tiền có yêu cầu chính xác:

~~~java
// Nên làm khi nhận input dạng chuỗi số thập phân:
new OrderAmount(new BigDecimal("0.10"));

// Tránh đường đi không cần thiết qua số dấu phẩy động:
new OrderAmount(new BigDecimal(0.1));
~~~

Giá trị của `new BigDecimal(0.1)` phản ánh sai số biểu diễn số thực nhị phân, thường không phù hợp với quy tắc scale chính xác. Nếu domain cần làm tròn, hãy định nghĩa rõ ở **cửa nhận dữ liệu** rồi kiểm tra kết quả. Spring converter không thể tự biết độ chính xác hợp lệ của tất cả đồng tiền hoặc đơn vị đo.

Một điểm khác: `BigDecimal.equals` so sánh cả scale, vì thế `1.0` và `1.00` có thể không bằng nhau về `equals` dù `compareTo` bằng 0. Bằng cách canonicalize trong constructor, `OrderAmount` giữ một quy tắc xác định. Điều này đặc biệt quan trọng khi value object còn được dùng làm key trong `Map` hoặc tập hợp.

### 10.2. Timestamp, UTC và độ chính xác

CQL `timestamp` biểu diễn một **thời điểm**, không lưu tên múi giờ ban đầu. `Instant` phù hợp với một mốc thời gian tuyệt đối; ngược lại `LocalDateTime` không mang timezone và cần quy tắc chuyển đổi rõ ràng trước khi thành một thời điểm.

CQL timestamp có **độ chính xác mili giây**. Nếu Java `Instant` chứa nano giây, dữ liệu đọc lại sau round-trip có thể khác giá trị đầu vào ở phần lẻ nhỏ hơn một mili giây. Để so sánh chính xác, chuẩn hóa trước khi ghi:

~~~java
import java.time.temporal.ChronoUnit;

Instant normalized = rawInstant.truncatedTo(ChronoUnit.MILLIS);
~~~

Không tự cộng/trừ múi giờ bằng tay để “sửa” thời điểm. Chọn `Instant` lưu trữ ở UTC và chỉ định timezone khi hiển thị là cách thường phù hợp; nếu nghiệp vụ lưu **giờ địa phương theo lịch**, có thể cần lưu thêm zone ID và quy tắc xử lý.

### 10.3. Null khác UNSET và cột chưa có dữ liệu

Converter thường nhận **giá trị non-null**; không nên dựa vào giả định rằng `convert(null)` sẽ được framework gọi cho mọi thao tác. Với Cassandra:

- **`null` trong một mutation CQL** có thể được hiểu là xóa giá trị/ghi tombstone.
- **UNSET** (ở ngữ cảnh driver/statement hỗ trợ) thường mang nghĩa không thay đổi cột hiện có.
- `null` trong entity có thể được mapper xử lý khác nhau giữa `insert`, `update`, template và option cấu hình.
- Với value object nullable, cần thiết kế xem “không có giá trị” khác “xóa giá trị” hay không.

Nếu cần **partial update**, kiểm tra chính xác CQL được tạo và hành vi null/unset của phiên bản thư viện đang dùng. Đừng mặc định `repository.save(entity có field null)` luôn giữ nguyên dữ liệu cũ.

### 10.4. Validation và dữ liệu không hợp lệ

Một converter đọc có thể gặp dữ liệu cũ như `currency_code = 'INVALID'` hoặc `total_amount` có nhiều chữ số thập phân hơn quy tắc mới. Nên:

1. Phát hiện lỗi **tại ranh giới chuyển đổi**, nêu được field/bản ghi liên quan mà không lộ dữ liệu nhạy cảm.
2. Phân biệt dữ liệu legacy cần migration với lỗi nhập liệu mới.
3. Không âm thầm tạo giá trị thay thế khiến sổ sách sai.
4. Có kế hoạch backfill và compatibility nếu nhiều phiên bản ứng dụng đọc cùng dữ liệu.

Không nên đưa I/O mạng, tra cứu ngoại bộ hoặc logic có tác dụng phụ vào converter: nó có thể được gọi nhiều lần khi mapping trang kết quả hoặc retry truy vấn.

### 10.5. Giới hạn conversion cho primary key

Chuyển một `CustomerId`/`OrderId` nghiệp vụ sang `UUID` có thể hợp lý, nhưng phải đảm bảo:

- **Một giá trị nghiệp vụ luôn cho cùng một giá trị CQL**, không dùng random ID hoặc timestamp tại thời điểm convert.
- Converter đọc và ghi nhất quán, không làm mất bit/độ chính xác.
- Mọi thành phần của **partition key và clustering key** có giá trị chuẩn, bất biến, không null.
- Nếu thay đổi quy tắc chuẩn hóa khóa, bạn có thể làm **đổi vị trí logic của dữ liệu**; cần migration/chuyển hàng thay vì chỉ cập nhật converter.

Ví dụ, `new CustomerId(UUID)` là một wrapper tốt; converter ghi `UUID` và đọc `CustomerId` có thể áp dụng theo cùng mô hình `OrderAmount`. Ngược lại, converter dùng `UUID.randomUUID()` mỗi lần ghi sẽ phá khả năng truy vấn lại chính dữ liệu đã lưu.

### 10.6. Conversion và hiệu năng

Converter chạy cho từng giá trị được ánh xạ và có thể được gọi rất nhiều lần khi đọc danh sách lớn hoặc paging. Vì vậy:

- Giữ phép chuyển đổi **nhẹ, thuần, không có I/O**, tránh parse regex phức tạp lặp lại nếu có thể chuẩn bị trước.
- Chọn kiểu CQL phù hợp thay vì serialization toàn bộ domain thành một chuỗi JSON chỉ để “dễ chuyển đổi” trong khi vẫn cần lọc, phân trang và tính toán.
- Đo latency thực tế của CQL, kích thước row/partition, mức GC, CPU mapper và số object được tạo khi tải lớn.
- Tối ưu từ **access pattern và partition key** trước khi tối ưu vi mô trong getter/converter.

Conversion không khắc phục hot partition, consistency level không phù hợp, tombstone, timeout hoặc paging qua nhiều partition.

## 11. Khi nào cần custom conversion, UDT hoặc driver TypeCodec?

| Nhu cầu | Cơ chế thường phù hợp | Giới hạn |
| --- | --- | --- |
| Bao `decimal` trong domain `OrderAmount` | **Spring Data custom converters** | Phải đăng ký và kiểm thử cả chiều đọc/ghi |
| Bao `text` trong `CurrencyCode` | **Spring Data custom converters** | Phải thống nhất chuẩn hóa dữ liệu cũ |
| Lưu object nhiều trường vào **một cột có cấu trúc** | **UDT** với `@UserDefinedType` và mapping tương ứng | Cần `CREATE TYPE`, quản lý schema/frozen và kiểm tra phiên bản |
| Một domain aggregate gồm nhiều cột khác nhau | **Ánh xạ nhiều field** hoặc converter/mapping thiết kế riêng có kiểm chứng | `Converter<Money, BigDecimal>` không tự viết thêm cột `currency_code` |
| Java driver cần mã hóa **một kiểu Java mới** trực tiếp sang kiểu CQL | **Driver TypeCodec** tùy yêu cầu | Hoạt động ở tầng driver; khác Spring Data custom converters |
| Cần đổi cả kiểu dữ liệu CQL của cột đã tồn tại | **Schema/data migration** | Không thể chỉ thay annotation để tự đổi dữ liệu cluster |

**Chọn lớp thấp nhất đủ đáp ứng nhu cầu:** nếu Java driver đã hiểu `BigDecimal` và Cassandra lưu `decimal`, converter ở Spring Data thường là đủ để dùng value object. Chỉ viết TypeCodec khi thật sự cần điều khiển tầng mã hóa của driver và đã đánh giá tính tương thích, không chỉ vì có một lớp Java mới.

## 12. Kiểm thử đúng cách: từ unit test đến Cassandra thật

### 12.1. Unit test converter có tính đối xứng

~~~java
@Test
void amountConvertersRoundTrip() {
    OrderAmount amount = new OrderAmount(new BigDecimal("125000.50"));

    BigDecimal stored =
        new OrderAmountWritingConverter().convert(amount);
    OrderAmount restored =
        new OrderAmountReadingConverter().convert(stored);

    assertEquals(new BigDecimal("125000.50"), stored);
    assertEquals(amount, restored);
}

@Test
void currencyCodeIsCanonicalized() {
    CurrencyCode input = new CurrencyCode(" vnd ");

    String stored =
        new CurrencyCodeWritingConverter().convert(input);
    CurrencyCode restored =
        new CurrencyCodeReadingConverter().convert(stored);

    assertEquals("VND", stored);
    assertEquals(input, restored);
}

@Test
void amountRejectsUnexpectedFraction() {
    assertThrows(ArithmeticException.class,
        () -> new OrderAmount(new BigDecimal("12.345")));
}
~~~

Các đoạn test cần import `org.junit.jupiter.api.Test`, assertions, `BigDecimal` và các lớp domain/converter. Unit test giúp xác nhận luật nghiệp vụ và hợp đồng hai chiều, nhưng **không chứng minh Spring Data đã đăng ký đúng converter, chọn đúng kiểu CQL hoặc driver đã ghi đúng cột**.

### 12.2. Test tích hợp repository và CQL thô

Tạo một keyspace thử nghiệm có `orders_by_id` và khởi động Spring Boot kết nối tới Cassandra. Test theo các bước:

1. Đảm bảo bean `CassandraCustomConversions` có đủ converter và template/repository đang dùng chính mapping converter đó.
2. Tạo `OrderRow` với `OrderAmount("125000.50")` và `CurrencyCode("vnd")`.
3. Ghi bằng repository; đọc lại bằng `findById` rồi kiểm tra value object tương đương.
4. Đọc **trực tiếp CQL qua driver** để xác minh giá trị lưu dưới dạng `decimal` và `text`:

~~~java
PreparedStatement select = session.prepare(
    "SELECT total_amount, currency_code " +
    "FROM orders_by_id WHERE order_id = ?"
);
Row raw = session.execute(select.bind(id)).one();
assertNotNull(raw);
assertEquals(new BigDecimal("125000.50"),
             raw.getBigDecimal("total_amount"));
assertEquals("VND", raw.getString("currency_code"));
~~~

5. Thử **giá trị null**, amount có quá nhiều chữ số thập phân, currency code sai, và dữ liệu legacy không chuẩn. Xác định hành vi mong muốn là từ chối, migration hay quy tắc tương thích rõ ràng.
6. Với `createdAt` có nano giây, kiểm tra vòng đọc/ghi timestamp sau chuẩn hóa mili giây.
7. Thử ứng dụng có **hai template** nếu dự án dùng nhiều keyspace; kiểm tra converter hoạt động trong đúng phạm vi.

### 12.3. Ma trận kiểm tra sau thay đổi converter

| Trường hợp | Câu hỏi cần trả lời |
| --- | --- |
| Ghi object hợp lệ | CQL nhận đúng giá trị kiểu cơ sở chưa? |
| Đọc lại bằng repository | Có tái tạo được value object cùng ngữ nghĩa không? |
| Đọc bằng raw driver | Giá trị Cassandra thực tế có khớp domain đã chuẩn hóa không? |
| Tham số bind trực tiếp | Đã chuyển thành kiểu driver hiểu chưa? |
| Dữ liệu cũ | Converter mới có đọc được mọi giá trị hợp lệ trước đó không? |
| Null/unset | Ghi thiếu và xóa giá trị có phân biệt đúng không? |
| Phép chuyển đổi ở khóa | Có giữ nguyên identity và khả năng tìm lại row không? |
| Nhiều template/keyspace | Converter được áp dụng ở đúng mapping context chưa? |
| Đọc nhiều trang | Chuyển đổi có gây chi phí CPU/GC hoặc lỗi ở giữa trang không? |

## 13. Bài thực hành tổng hợp và câu hỏi tự kiểm tra

**Đề bài:** xây dựng một ứng dụng Spring Boot lưu hóa đơn theo `order_id`, nhưng toàn bộ service làm việc với `OrderAmount` và `CurrencyCode` thay vì `BigDecimal`/`String` trần.

Hướng triển khai:

1. Tạo bảng `orders_by_id` với `total_amount decimal` và `currency_code text`.
2. Viết value object bất biến, chuẩn hóa scale 2 chữ số và mã tiền tệ chữ hoa.
3. Viết `@WritingConverter` và `@ReadingConverter` cho từng value object.
4. Đăng ký trong `CassandraCustomConversions`, bảo đảm không làm mất converter có sẵn của dự án.
5. Ánh xạ `OrderRow`, dùng `OrderRepository` để ghi và đọc.
6. Đối chiếu raw CQL để chứng minh dữ liệu thật sự được lưu ở kiểu `decimal` và `text`.
7. Test giá trị legacy, timeout, đổi kiểu/scale và xử lý null; phân biệt lỗi converter với lỗi CQL/cluster.
8. Đo đọc nhiều hàng theo paging và giải thích tại sao converter không thay thế thiết kế partition key hay consistency.

Tự trả lời:

1. Vì sao domain `OrderAmount` nên được lưu thành `decimal` thay vì `double` hoặc `text`?
2. `@WritingConverter` và `@ReadingConverter` khác nhau ở đâu?
3. Vì sao phải đăng ký converter vào `CassandraCustomConversions`?
4. Vai trò của `@CassandraType` khác với vai trò của custom converter thế nào?
5. Khi dùng `CqlSession.execute(...)` trực tiếp, có mặc định bind được `OrderAmount` không?
6. Vì sao `new BigDecimal(0.1)` là lựa chọn không phù hợp để biểu diễn 0,10 chính xác?
7. CQL `timestamp` khác gì `Instant` có độ chính xác nano giây?
8. Null và UNSET có phải cùng một thao tác trong Cassandra?
9. Vì sao converter đọc có thể thất bại sau khi bổ sung validation mới?
10. Nếu một domain object cần lưu vào hai cột, có thể chỉ viết `Converter<Money, BigDecimal>` là đủ không?
11. Nếu converter dùng để biểu diễn partition key, quy tắc ổn định nào bắt buộc phải giữ?
12. Test repository thành công đã đủ chứng minh dữ liệu CQL đúng chưa?

**Ghi nhớ:** chuyển đổi kiểu trong **Spring Data Cassandra** nối hai mô hình: **value object mang quy tắc nghiệp vụ của Java** và **kiểu lưu trữ CQL**. Hãy chọn kiểu CQL có ngữ nghĩa phù hợp, tạo converter hai chiều thuần và có thể kiểm thử, đăng ký đúng mapping context, kiểm tra dữ liệu thực tế trên Cassandra. Những quyết định về partition key, consistency, paging và hiệu năng vẫn cần được giải quyết ở tầng thiết kế phân tán.

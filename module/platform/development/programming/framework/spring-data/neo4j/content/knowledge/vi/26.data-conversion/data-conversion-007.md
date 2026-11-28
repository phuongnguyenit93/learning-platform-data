# Kiểu tiền tệ, enum đặc thù và lựa chọn biểu diễn cho truy vấn

Khi lưu dữ liệu tiền tệ hoặc enum vào Neo4j, cần chọn cách biểu diễn dựa trên cả hai yêu cầu: giữ đúng ý nghĩa của giá trị trong Java và hỗ trợ các truy vấn Cypher mà ứng dụng cần. Một kiểu Java giàu ngữ nghĩa như `BigDecimal`, `Currency` hoặc enum tùy chỉnh không phải lúc nào cũng tương ứng trực tiếp với một kiểu property native trong Neo4j.

Trong module `SPRING_DATA_NEO4J`, Spring Data Neo4j cung cấp nhiều conversion mặc định và cho phép bổ sung converter. Ví dụ, `BigDecimal` được ánh xạ thành property kiểu String, enum mặc định được lưu bằng tên hằng enum, còn kiểu `Currency` cần được chuyển đổi tường minh. Với dữ liệu cần lọc hoặc sắp xếp số học, nên lưu số tiền ở dạng số nguyên theo đơn vị nhỏ nhất cùng mã tiền tệ và scale; không nên dựa vào chuỗi thập phân hoặc số floating point làm nguồn dữ liệu tài chính chuẩn.

## 1. Tách kiểu domain khỏi kiểu property của Neo4j

Java có nhiều kiểu biểu diễn dữ liệu phong phú. Neo4j lưu property bằng các kiểu như Boolean, Integer, Float, String, Date, LocalTime, LocalDateTime, DateTime, Duration và Point. Neo4j không có property type `DECIMAL` với độ chính xác thập phân tùy ý.

Spring Data Neo4j đóng vai trò chuyển đổi giữa kiểu domain và kiểu mà Neo4j Driver hỗ trợ. Ví dụ theo conversion mặc định của Spring Data Neo4j 8.2:

| Kiểu Java | Kiểu property Cypher | Ý nghĩa cần chú ý |
|---|---|---|
| `BigDecimal` | `STRING` | Giữ biểu diễn thập phân nhưng không còn là số để so sánh số học trực tiếp |
| `BigInteger` | `STRING` | Không thể dùng trực tiếp toán tử số học của Cypher như với INTEGER |
| `Enum` | `STRING` | Lưu tên hằng enum thông qua `name()` |
| `String` | `STRING` | Phù hợp với mã, trạng thái, ký hiệu và văn bản |
| `Long` | `INTEGER` | Phù hợp với số nguyên 64-bit như số tiền theo đơn vị nhỏ nhất |
| `Double` | `FLOAT` | Số thực nhị phân 64-bit, có sai số biểu diễn |

Vì vậy, lựa chọn kiểu lưu trữ phải xét đến cách truy vấn. Một giá trị `BigDecimal` có thể round-trip qua converter mặc định, nhưng nếu được lưu dưới dạng String thì `WHERE amount > $minimum` thực hiện so sánh chuỗi, không phải so sánh tiền tệ theo giá trị số.

## 2. BigDecimal mặc định được lưu thành String

Spring Data Neo4j có conversion mặc định cho `java.math.BigDecimal` sang property String và chuyển ngược lại khi đọc entity. Điều này hữu ích khi cần giữ biểu diễn thập phân trong domain mà không muốn tự viết converter.

Ví dụ entity:

```java
import java.math.BigDecimal;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Invoice")
public class Invoice {

    @Id
    @GeneratedValue
    private Long id;

    private BigDecimal amount;

    protected Invoice() {
    }

    public Invoice(BigDecimal amount) {
        this.amount = amount;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
```

Khi entity được lưu, property `amount` được biểu diễn thành chuỗi. Ví dụ các giá trị `9.50`, `12.00` và `100.00` vẫn là String trong Neo4j.

### Vì sao không dùng chuỗi để so sánh tiền?

So sánh chuỗi theo thứ tự từ điển không tương đương so sánh số. Chẳng hạn, chuỗi `"100.00"` có thể đứng trước `"20.00"` theo thứ tự từ điển vì ký tự đầu tiên `1` nhỏ hơn `2`, trong khi 100 lớn hơn 20 về mặt số học.

```cypher
MATCH (i:Invoice)
WHERE i.amount > '20.00'
RETURN i.amount
ORDER BY i.amount;
```

Truy vấn trên lọc và sắp xếp String. Kết quả không có ngữ nghĩa so sánh tiền tệ mong muốn. Không dùng trực tiếp toán tử `>`, `<`, `ORDER BY` trên property BigDecimal đã được lưu thành chuỗi để thực hiện nghiệp vụ tài chính.

Cypher có thể chuyển String thành FLOAT bằng `toFloat()`, nhưng FLOAT là số thực nhị phân 64-bit. Phép chuyển đổi này hữu ích cho phân tích gần đúng hoặc dữ liệu đo lường, không phải cách lưu trữ chuẩn cho số tiền cần tính toán chính xác. Hãy chọn một biểu diễn số nguyên hoặc mô hình thập phân có scale rõ ràng.

## 3. Mô hình tiền tệ bằng amountMinor, currency và scale

Một cách biểu diễn dễ truy vấn là lưu số tiền dưới dạng số nguyên theo đơn vị nhỏ nhất của currency. Ví dụ:

| Tiền tệ | Giá trị hiển thị | Đơn vị nhỏ nhất | Giá trị lưu |
|---|---:|---|---:|
| USD | 12.34 | cent (2 chữ số thập phân) | 1234 |
| JPY | 1200 | yen (0 chữ số thập phân) | 1200 |
| BHD | 12.345 | fils (3 chữ số thập phân) | 12345 |

Khi dùng cách này, cần lưu mã tiền tệ và scale đi cùng số nguyên. Scale xác định cách khôi phục giá trị thập phân; mã tiền tệ xác định đơn vị và ngăn việc so sánh các đồng tiền khác nhau như thể chúng có cùng giá trị.

Value object trong Java:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;

public record Money(long minorUnits, Currency currency, int scale) {

    public Money {
        if (currency == null || scale < 0) {
            throw new IllegalArgumentException("Currency and a non-negative scale are required");
        }
    }

    public static Money of(BigDecimal amount, Currency currency) {
        if (amount == null || currency == null) {
            throw new IllegalArgumentException("Amount and currency are required");
        }
        int scale = currency.getDefaultFractionDigits();
        if (scale < 0) {
            throw new IllegalArgumentException(
                "Currency requires an explicit scale: " + currency.getCurrencyCode()
            );
        }

        return of(amount, currency, scale);
    }

    public static Money of(BigDecimal amount, Currency currency, int scale) {
        if (amount == null || currency == null || scale < 0) {
            throw new IllegalArgumentException("Amount, currency and a non-negative scale are required");
        }
        BigDecimal normalized = amount.setScale(scale, RoundingMode.UNNECESSARY);
        long minorUnits = normalized.movePointRight(scale).longValueExact();
        return new Money(minorUnits, currency, scale);
    }

    public BigDecimal toBigDecimal() {
        return BigDecimal.valueOf(minorUnits, scale);
    }
}
```

`RoundingMode.UNNECESSARY` làm cho dữ liệu có nhiều chữ số thập phân hơn currency cho phép bị từ chối thay vì âm thầm làm tròn. `longValueExact()` cũng từ chối giá trị vượt phạm vi `long`. Nếu nghiệp vụ cho phép làm tròn, hãy chọn và ghi rõ quy tắc như `HALF_EVEN` hoặc `HALF_UP` ở tầng domain trước khi lưu.

`Currency.getDefaultFractionDigits()` trả số chữ số thập phân mặc định của currency ISO mà JDK nhận diện. Với currency không có số chữ số mặc định (`-1`), tài sản số hoặc đơn vị tùy chỉnh, cần truyền scale theo chính sách domain thay vì tự suy đoán.

### Entity lưu các thành phần riêng biệt

Trong entity Neo4j, lưu từng thành phần thành property riêng:

```java
import java.util.Currency;
import org.springframework.data.neo4j.core.convert.ConvertWith;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Invoice")
public class Invoice {

    @Id
    @GeneratedValue
    private Long id;

    private long amountMinor;
    private int amountScale;
    private Currency currency;

    @ConvertWith(converter = PaymentStatusConverter.class)
    private PaymentStatus status;

    protected Invoice() {
    }

    public Money amount() {
        return new Money(amountMinor, currency, amountScale);
    }

    public void setAmount(Money amount) {
        this.amountMinor = amount.minorUnits();
        this.amountScale = amount.scale();
        this.currency = amount.currency();
    }

    public PaymentStatus getStatus() {
        return status;
    }
}
```

Trong ví dụ này, `Money` là value object của domain; các field thực sự được Spring Data Neo4j ánh xạ là `amountMinor`, `amountScale` và `currency`. Cách này giúp Cypher truy cập trực tiếp từng property, đồng thời domain vẫn làm việc với `BigDecimal` và `Currency` ở API của nó.

## 4. Chuyển đổi Currency thành mã ISO

`java.util.Currency` không phải property type native của Neo4j và không nằm trong danh sách conversion mặc định của Spring Data Neo4j 8.2. Một cách phù hợp là chuyển `Currency` thành mã ISO 4217 dạng String, ví dụ `USD`, `VND`, `JPY`.

Không lưu ký hiệu hiển thị như `$` hoặc `đ` làm định danh currency. Ký hiệu có thể trùng giữa nhiều currency hoặc thay đổi theo locale. Mã ISO ổn định hơn và có thể được dùng trực tiếp trong điều kiện Cypher.

### Viết GenericConverter

Khi cần sử dụng `Currency` ở nhiều entity, có thể đăng ký converter toàn cục thông qua `Neo4jConversions`:

```java
import java.util.Currency;
import java.util.Set;

import org.neo4j.driver.Value;
import org.neo4j.driver.Values;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.GenericConverter;

public class CurrencyValueConverter implements GenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(
            new ConvertiblePair(Currency.class, Value.class),
            new ConvertiblePair(Value.class, Currency.class)
        );
    }

    @Override
    public Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType
    ) {
        if (source == null) {
            return null;
        }

        if (Currency.class.isAssignableFrom(sourceType.getType())) {
            Currency currency = (Currency) source;
            return Values.value(currency.getCurrencyCode());
        }

        if (Value.class.isAssignableFrom(sourceType.getType())) {
            Value value = (Value) source;
            return Currency.getInstance(value.asString());
        }

        throw new IllegalArgumentException(
            "Unsupported conversion from " + sourceType + " to " + targetType
        );
    }
}
```

Converter ghi currency thành Neo4j Driver `Value` chứa mã ISO và khôi phục lại bằng `Currency.getInstance(...)`. Nếu dữ liệu chứa mã currency không hợp lệ, việc đọc sẽ báo lỗi thay vì tạo một đối tượng currency không xác định.

### Đăng ký trong Neo4jConversions

```java
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.convert.Neo4jConversions;

@Configuration
public class Neo4jConversionConfiguration {

    @Bean
    Neo4jConversions neo4jConversions() {
        return new Neo4jConversions(Set.of(new CurrencyValueConverter()));
    }
}
```

Bean `Neo4jConversions` bổ sung converter tùy chỉnh vào tập conversion của Spring Data Neo4j. Sau khi đăng ký, field `Currency currency` trong entity được lưu thành property String chứa currency code. Với một kiểu chỉ dùng ở một field, có thể cân nhắc converter riêng cho property thay vì đăng ký toàn cục.

## 5. Enum mặc định và nguy cơ đổi tên hằng

Spring Data Neo4j mặc định chuyển enum thành String bằng `Enum.name()` và đọc lại bằng `Enum.valueOf()`. Ví dụ:

```java
public enum PaymentStatus {
    PENDING,
    SETTLED,
    REFUNDED
}
```

Node có thể lưu:

```cypher
(:Invoice {status: 'PENDING'})
```

Cách này đơn giản, dễ đọc và truy vấn được bằng Cypher:

```cypher
MATCH (i:Invoice)
WHERE i.status = 'PENDING'
RETURN i;
```

Tuy nhiên, tên enum trở thành dữ liệu persistence. Nếu đổi `PENDING` thành `WAITING_FOR_PAYMENT`, dữ liệu cũ vẫn chứa `PENDING`; `Enum.valueOf("PENDING")` sẽ không tìm thấy hằng tương ứng nếu hằng cũ đã bị xóa. Đổi tên enum có thể cần migration dữ liệu.

Nếu enum là một phần hợp đồng dữ liệu lâu dài, nên dùng mã ổn định độc lập với tên hằng trong Java.

## 6. Enum có mã lưu trữ ổn định

Khai báo enum có code riêng:

```java
import java.util.Arrays;

public enum PaymentStatus {
    PENDING("pending"),
    SETTLED("settled"),
    REFUNDED("refunded");

    private final String code;

    PaymentStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static PaymentStatus fromCode(String code) {
        return Arrays.stream(values())
            .filter(status -> status.code.equals(code))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException(
                "Unknown payment status code: " + code
            ));
    }
}
```

Ở đây, tên hằng có thể được đổi trong Java mà giá trị persistence vẫn là `pending`, `settled` hoặc `refunded`, miễn là code không thay đổi. Code nên được xem như một phần schema dữ liệu: không tái sử dụng code cũ cho ý nghĩa mới.

### Viết Neo4jPersistentPropertyConverter

`@ConvertWith` cho phép gắn converter vào đúng property cần chuyển đổi:

```java
import org.neo4j.driver.Value;
import org.neo4j.driver.Values;
import org.springframework.data.neo4j.core.convert.Neo4jPersistentPropertyConverter;

public class PaymentStatusConverter
        implements Neo4jPersistentPropertyConverter<PaymentStatus> {

    @Override
    public Value write(PaymentStatus source) {
        return source == null ? Values.NULL : Values.value(source.code());
    }

    @Override
    public PaymentStatus read(Value source) {
        return PaymentStatus.fromCode(source.asString());
    }
}
```

Trên entity:

```java
@ConvertWith(converter = PaymentStatusConverter.class)
private PaymentStatus status;
```

Converter chỉ áp dụng cho property `status`, không làm thay đổi cách lưu các enum khác trong ứng dụng. `write()` trả `Values.NULL` khi giá trị Java là `null`; `read()` nhận Neo4j `Value` và khôi phục enum từ code.

Nếu code trong graph không còn được enum nhận diện, converter báo lỗi để phát hiện dữ liệu cũ hoặc dữ liệu không hợp lệ. Khi đổi code, hãy viết migration chuyển giá trị cũ sang giá trị mới trước khi triển khai enum mới.

## 7. Converter ảnh hưởng thế nào đến truy vấn?

Conversion của property và conversion của tham số query có liên quan nhưng không phải mọi loại query đều tự chuyển đổi giống nhau.

Với `@ConvertWith`, Spring Data Neo4j áp dụng conversion cho property và các tham số repository gắn với property đó trong derived query và Query by Example. Conversion này không tự động được áp dụng cho query dạng chuỗi khai báo bằng `@Query`.

Vì vậy, với Cypher tùy chỉnh, hãy truyền code đã chuẩn hóa rõ ràng:

```java
import java.util.List;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface InvoiceRepository extends Neo4jRepository<Invoice, Long> {

    @Query("""
        MATCH (i:Invoice)
        WHERE i.status = $statusCode
        RETURN i
        ORDER BY i.amountMinor
        """)
    List<Invoice> findByStatusCode(@Param("statusCode") String statusCode);
}
```

Gọi repository bằng code:

```java
List<Invoice> pending = invoiceRepository.findByStatusCode(
    PaymentStatus.PENDING.code()
);
```

Ở đây, tham số có kiểu `String` vì Cypher đang so khớp property đã lưu dưới dạng code. Không truyền `PaymentStatus.PENDING.name()` nếu dữ liệu được lưu bằng code riêng.

Tương tự với `Neo4jClient`, bind giá trị đã chuẩn hóa:

```java
import org.springframework.data.neo4j.core.Neo4jClient;

neo4jClient.query("""
        MATCH (i:Invoice)
        WHERE i.status = $statusCode
        RETURN count(i) AS total
        """)
    .bind(PaymentStatus.PENDING.code()).to("statusCode")
    .fetchAs(Long.class)
    .mappedBy((typeSystem, record) -> record.get("total").asLong())
    .one()
    .orElse(0L);
```

Điều này làm rõ hợp đồng giữa domain và Cypher: Java enum được chuyển thành code ở ranh giới truy vấn, còn Neo4j chỉ làm việc với String.

## 8. Truy vấn tiền tệ theo amountMinor và currency

Khi entity dùng `amountMinor`, `amountScale` và `currency`, Cypher có thể lọc theo currency, scale và khoảng số nguyên:

```cypher
MATCH (i:Invoice)
WHERE i.currency = $currencyCode
  AND i.amountScale = $scale
  AND i.amountMinor >= $minimumMinor
RETURN i
ORDER BY i.amountMinor;
```

Ví dụ, để tìm hóa đơn từ 12.34 USD trở lên:

```java
String currencyCode = "USD";
int scale = 2;
long minimumMinor = 1234L;
```

Điều kiện currency và scale bảo đảm chỉ so sánh những số nguyên có cùng đơn vị. Không so sánh `amountMinor` của USD với `amountMinor` của JPY hoặc BHD mà không chuẩn hóa về cùng currency và cùng quy tắc quy đổi.

Repository có thể khai báo query như sau:

```java
import java.util.List;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

// Phương thức nằm trong InvoiceRepository.
@Query("""
    MATCH (i:Invoice)
    WHERE i.currency = $currencyCode
      AND i.amountScale = $scale
      AND i.amountMinor >= $minimumMinor
    RETURN i
    ORDER BY i.amountMinor
    """)
List<Invoice> findInvoicesAtLeast(
    @Param("currencyCode") String currencyCode,
    @Param("scale") int scale,
    @Param("minimumMinor") long minimumMinor
);
```

Nếu dùng một chính sách currency ISO cố định, scale có thể lấy từ `Currency.getDefaultFractionDigits()` ở tầng domain. Việc lưu scale riêng vẫn giúp dữ liệu tự mô tả và giữ nguyên cách diễn giải nếu quy tắc currency hoặc loại tài sản thay đổi.

### Index cho điều kiện tìm kiếm

Nếu truy vấn thường xuyên lọc theo currency và scale rồi tìm khoảng amount, có thể tạo composite range index:

```cypher
CREATE RANGE INDEX invoice_currency_scale_amount_idx IF NOT EXISTS
FOR (i:Invoice)
ON (i.currency, i.amountScale, i.amountMinor);
```

Thứ tự property trong composite index có ý nghĩa. Hai điều kiện đầu là equality, property cuối là range. Hãy đo bằng `PROFILE` trên dữ liệu đại diện và xác nhận index đã ở trạng thái `ONLINE`; không tạo index cho mọi tổ hợp filter nếu workload thực tế không cần.

## 9. Chọn cách biểu diễn theo nhu cầu

| Cách lưu | Ưu điểm | Giới hạn | Nên dùng khi |
|---|---|---|---|
| `BigDecimal` mặc định thành String | Giữ domain type quen thuộc; conversion có sẵn | So sánh và sắp xếp trong Cypher là theo chuỗi | Lưu giá trị để đọc/hiển thị hoặc truy vấn bằng equality chuỗi có kiểm soát |
| `Double` / FLOAT | Có toán tử số học và range query trực tiếp | Sai số số thực nhị phân | Dữ liệu phân tích gần đúng, không dùng làm sổ cái tài chính |
| `amountMinor` INTEGER + currency code + scale | So sánh số nguyên chính xác trong phạm vi kiểu; index range được | Phải chuẩn hóa scale và không so sánh khác currency trực tiếp | Giá, hóa đơn, thanh toán, số dư và các truy vấn số học |
| Một chuỗi Money ghép như `USD:12.34` | Đóng gói được nhiều thành phần vào một property | Khó lọc, sắp xếp và index riêng từng thành phần | Chỉ lưu snapshot để hiển thị hoặc trao đổi, không cần truy vấn từng thành phần |
| Node hoặc relationship properties riêng | Có thể gắn currency/amount vào một quan hệ hoặc lịch sử giá | Mô hình phức tạp hơn | Giá thay đổi theo thời gian, theo sản phẩm, khu vực hoặc theo giao dịch |

Nếu một sản phẩm có nhiều mức giá theo cửa hàng hoặc theo khoảng thời gian, có thể mô hình giá thành node `Price` hoặc `@RelationshipProperties` trên quan hệ thích hợp. Mỗi giá cần lưu amount, currency, scale, hiệu lực từ thời điểm nào và ngữ cảnh áp dụng. Khi đó, không nhồi nhiều mức giá vào một String hoặc một Map khó truy vấn.

## 10. Migration khi đổi kiểu hoặc mã lưu trữ

Thay đổi cách biểu diễn là thay đổi hợp đồng dữ liệu giữa ứng dụng và graph. Ví dụ, chuyển từ `BigDecimal` String sang `amountMinor` INTEGER cần migration có kiểm soát:

1. Xác định định dạng String hiện tại và currency áp dụng cho từng node.
2. Chọn quy tắc scale và rounding thống nhất.
3. Chuyển từng giá trị sang `amountMinor`, `amountScale` và `currency`.
4. Kiểm tra số node chuyển đổi thành công, giá trị âm, giá trị vượt phạm vi `long` và dữ liệu không hợp lệ.
5. Chạy đối chiếu tổng số tiền theo từng currency trước và sau migration.
6. Chỉ chuyển query và ứng dụng sang field mới khi dữ liệu đã được xác minh.
7. Xóa field cũ sau khi không còn phiên bản ứng dụng nào đọc nó.

Với enum, nếu trước đây lưu `PENDING` và chuyển sang `pending`, hãy cập nhật dữ liệu trước hoặc hỗ trợ cả code cũ lẫn mới trong giai đoạn chuyển tiếp. Không đổi đồng thời tên enum, code persistence và ý nghĩa nghiệp vụ mà không có migration.

## 11. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| `BigDecimal` query range cho kết quả sai | Property đã được lưu dưới dạng String | Dùng amountMinor INTEGER hoặc mô hình số có scale rõ ràng |
| `ORDER BY amount` sắp xếp bất thường | Đang sắp xếp String thập phân | Sắp xếp `amountMinor` trong cùng currency và scale |
| So sánh hai số tiền khác currency | Bỏ điều kiện currency | Luôn lọc cùng currency hoặc quy đổi bằng tỷ giá có thời điểm và nguồn xác định |
| Giá trị tiền bị làm tròn âm thầm | Converter hoặc service áp dụng rounding không được quy định | Chọn `RoundingMode` rõ ràng và validate trước khi lưu |
| `longValueExact()` báo lỗi | Giá trị vượt phạm vi `long` | Giới hạn miền giá trị hoặc chọn mô hình số khác có kiểm soát |
| Không đọc được enum sau khi đổi tên hằng | Neo4j vẫn chứa tên enum cũ | Giữ tên ổn định hoặc migration sang code độc lập |
| Enum code không được khôi phục | `fromCode()` không nhận diện giá trị trong graph | Kiểm tra dữ liệu, hỗ trợ alias chuyển tiếp hoặc chạy migration |
| `@Query` không tự chuyển enum thành code tùy chỉnh | Custom property converter không áp dụng cho string-based query | Truyền `status.code()` hoặc mã String tường minh |
| `Currency.getInstance()` báo lỗi | Currency code không phải mã ISO hợp lệ | Validate code đầu vào và chuẩn hóa chữ hoa |
| Index không được dùng | Query thiếu property theo thứ tự composite index hoặc index chưa ONLINE | Kiểm tra predicate, `SHOW INDEXES` và `PROFILE` |

## 12. Tự kiểm tra

1. Spring Data Neo4j 8.2 lưu `BigDecimal` mặc định thành kiểu Cypher nào?
2. Vì sao property String chứa `"100.00"` không thể dùng để so sánh tiền theo số học?
3. Vì sao nên lưu mã currency thay vì ký hiệu hiển thị như `$`?
4. `amountMinor` cần đi cùng những thông tin nào để khôi phục số tiền?
5. Vì sao phải từ chối hoặc quy định rõ rounding khi số chữ số thập phân vượt scale của currency?
6. Enum mặc định được lưu bằng tên nào và rủi ro gì xảy ra khi đổi tên hằng?
7. `@ConvertWith` khác converter đăng ký toàn cục trong `Neo4jConversions` ở phạm vi áp dụng như thế nào?
8. Vì sao custom converter không tự áp dụng cho tham số của string-based `@Query`?
9. Khi nào nên tạo composite range index trên currency, scale và amountMinor?

Hãy chọn biểu diễn theo cách dữ liệu sẽ được truy vấn. `BigDecimal` mặc định của Spring Data Neo4j phù hợp khi cần lưu và khôi phục giá trị dưới dạng String; enum mặc định lưu tên hằng, còn enum có code ổn định cần converter phù hợp. Với tiền tệ cần lọc và sắp xếp số học, hãy lưu số nguyên theo đơn vị nhỏ nhất cùng currency và scale, bind code tường minh trong Cypher tùy chỉnh, và kiểm tra index bằng kế hoạch thực thi.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2 — Conversions and custom converters](https://docs.spring.io/spring-data/neo4j/reference/appendix/conversions.html)
- [Spring Data Neo4j — `Neo4jPersistentPropertyConverter` API](https://docs.spring.io/spring-data/neo4j/docs/current/api/org/springframework/data/neo4j/core/convert/Neo4jPersistentPropertyConverter.html)
- [Spring Data Neo4j — `ConvertWith` API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/convert/ConvertWith.html)
- [Neo4j Cypher Manual — Property values and types](https://neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/)
- [Neo4j Cypher Manual — Create range and composite indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)

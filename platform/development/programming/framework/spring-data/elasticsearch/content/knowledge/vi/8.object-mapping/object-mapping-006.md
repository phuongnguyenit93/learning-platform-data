# Xử lý enum, tiền tệ và kiểu giá trị nghiệp vụ

Entity trong ứng dụng thường chứa nhiều kiểu dữ liệu ngoài chuỗi và số cơ bản: trạng thái dạng enum, tiền tệ, mã sản phẩm, email, khoảng thời gian hoặc các value object do nghiệp vụ định nghĩa. Khi lưu những giá trị này vào Elasticsearch, cần xác định rõ dữ liệu nào được lưu, mapping nào phù hợp và cách chuyển đổi giữa kiểu Java với document.

Spring Data Elasticsearch sử dụng mapping metadata và conversion service để chuyển đổi entity thành document rồi đọc document trở lại entity. Với kiểu đơn giản, framework đã có nhiều quy tắc chuyển đổi mặc định. Với kiểu nghiệp vụ tùy chỉnh, ứng dụng có thể dùng converter hoặc một document model riêng để kiểm soát cấu trúc dữ liệu.

## 1. Mô hình chuyển đổi giữa Java và Elasticsearch

Khi gọi `repository.save(entity)`, Spring Data Elasticsearch chuyển các thuộc tính Java thành dữ liệu document theo mapping. Khi đọc document, quá trình chuyển đổi diễn ra theo chiều ngược lại.

~~~mermaid
flowchart TD
    A["Domain object / Entity Java"] --> B["MappingElasticsearchConverter"]
    B --> C["CustomConversions và mapping metadata"]
    C --> D["Elasticsearch document"]
    D --> E["Elasticsearch index"]
    E --> F["Document được đọc"]
    F --> G["MappingElasticsearchConverter"]
    G --> H["Domain object / Entity Java"]
~~~

Có ba nhóm dữ liệu thường gặp:

| Nhóm | Ví dụ | Cách xử lý thường dùng |
|---|---|---|
| Kiểu cơ bản | String, Integer, Boolean, BigDecimal | Mapping field phù hợp |
| Kiểu có quy ước sẵn | Enum, UUID, ngày giờ | Dùng conversion mặc định và kiểm tra mapping |
| Kiểu nghiệp vụ tùy chỉnh | ProductCode, EmailAddress, Money, Quantity | Custom converter hoặc document projection |

Điều quan trọng là tách biệt **kiểu dữ liệu trong domain model** và **cách biểu diễn trong Elasticsearch**. Domain model phục vụ quy tắc nghiệp vụ; document model phục vụ truy vấn, lọc, sắp xếp và thống kê.

## 2. Lưu enum trong Elasticsearch

Enum biểu diễn một tập giá trị hữu hạn, chẳng hạn trạng thái đơn hàng:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED,
    REFUNDED
}
~~~

Trong Elasticsearch, trạng thái thường được lưu dưới dạng chuỗi và mapping kiểu `keyword`, vì ứng dụng cần lọc theo đúng một trạng thái:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class OrderDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private OrderStatus status;

    // Constructors, getters and setters
}
~~~

Spring Data Elasticsearch hỗ trợ chuyển đổi enum thành giá trị chuỗi theo quy tắc conversion mặc định. Với enum Java thông thường, giá trị được biểu diễn theo tên hằng số. Ví dụ `OrderStatus.PAID` được lưu thành `"PAID"`.

Có thể truy vấn trạng thái bằng `term`:

~~~json
{
  "query": {
    "term": {
      "status": "PAID"
    }
  }
}
~~~

Dùng `keyword` giúp Elasticsearch coi trạng thái là một giá trị nguyên vẹn. Nếu dùng `text`, analyzer có thể xử lý chuỗi theo cách không cần thiết đối với một enum.

### Vì sao không nên lưu enum bằng ordinal?

Không nên lưu vị trí số của enum như `0`, `1`, `2`:

~~~java
public enum OrderStatus {
    PENDING,   // 0
    PAID,      // 1
    CANCELLED  // 2
}
~~~

Nếu sau này thêm hoặc sắp xếp lại hằng số, cùng một số có thể mang ý nghĩa khác. Document cũ khi đọc bằng code mới có thể bị hiểu sai.

Lưu tên hoặc mã ổn định giúp dữ liệu dễ đọc và ít phụ thuộc vào thứ tự khai báo enum. Tuy nhiên, đổi tên hằng số cũng là thay đổi schema dữ liệu nếu tên đó đã được lưu trong index.

## 3. Enum có mã nghiệp vụ riêng

Trong một số hệ thống, tên enum trong Java không phải giá trị muốn lưu. Ví dụ, API hoặc hệ thống cũ dùng mã `"P"` cho trạng thái đã thanh toán thay vì `"PAID"`.

Có thể định nghĩa enum với mã riêng:

~~~java
public enum OrderStatus {

    PENDING("P"),
    PAID("S"),
    CANCELLED("C"),
    REFUNDED("R");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException(
                "Unknown order status code: " + code
        );
    }
}
~~~

Nếu cần lưu mã riêng, hãy đăng ký converter hai chiều thay vì phụ thuộc vào tên hằng số.

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class OrderStatusWriteConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.getCode();
    }
}
~~~

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class OrderStatusReadConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

`@WritingConverter` đánh dấu converter dùng khi ghi entity thành document. `@ReadingConverter` đánh dấu converter dùng khi đọc giá trị từ document thành kiểu Java.

Cần bảo đảm mọi mã đang tồn tại trong index đều được `fromCode` nhận diện. Nếu có mã không còn hợp lệ, nên xử lý bằng chính sách tương thích dữ liệu rõ ràng thay vì âm thầm gán sang trạng thái mặc định.

## 4. Đăng ký custom conversions

Spring Data Elasticsearch cung cấp `ElasticsearchCustomConversions` để đăng ký converter dùng trong quá trình mapping.

Ví dụ cấu hình:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.core.convert.ElasticsearchCustomConversions;

@Configuration
public class ElasticsearchConversionConfig {

    @Bean
    ElasticsearchCustomConversions elasticsearchCustomConversions() {
        return new ElasticsearchCustomConversions(List.of(
                new OrderStatusWriteConverter(),
                new OrderStatusReadConverter(),
                new ProductCodeWriteConverter(),
                new ProductCodeReadConverter()
        ));
    }
}
~~~

Spring Data sử dụng các converter được đăng ký trong `ElasticsearchCustomConversions` khi chuyển đổi giá trị. Hãy đặt cấu hình này trong application context để mapping converter của Elasticsearch nhận được các chuyển đổi cần thiết.

Khi một converter có thể được hiểu theo nhiều chiều, các annotation `@WritingConverter` và `@ReadingConverter` giúp xác định mục đích rõ ràng. Cũng cần tránh đăng ký nhiều converter cạnh tranh cho cùng một cặp kiểu nguồn và kiểu đích.

Tên package và cơ chế cấu hình cụ thể nên được đối chiếu với phiên bản Spring Data Elasticsearch đang dùng; không trộn converter của MongoDB, JPA hoặc hệ thống persistence khác vào conversion registry của Elasticsearch.

## 5. Kiểu giá trị nghiệp vụ (Value Object)

Value object là kiểu dữ liệu mô tả một khái niệm nghiệp vụ bằng giá trị và quy tắc của nó. Ví dụ:

- `ProductCode`: mã sản phẩm hợp lệ.
- `EmailAddress`: địa chỉ email đã chuẩn hóa.
- `Money`: số tiền đi cùng đơn vị tiền tệ.
- `Quantity`: số lượng cùng đơn vị đo.

Một value object thường đóng gói validation và hành vi để tránh việc mọi nơi trong ứng dụng tự xử lý chuỗi hoặc số thô.

Ví dụ mã sản phẩm:

~~~java
import java.util.Objects;

public record ProductCode(String value) {

    public ProductCode {
        Objects.requireNonNull(value, "value must not be null");

        if (!value.matches("[A-Z0-9-]{3,30}")) {
            throw new IllegalArgumentException(
                    "Invalid product code: " + value
            );
        }
    }
}
~~~

Trong domain model, dùng `ProductCode` giúp thể hiện rõ đây là mã sản phẩm đã được kiểm tra, thay vì một `String` bất kỳ.

Tuy nhiên, Elasticsearch cần biểu diễn giá trị này dưới dạng dữ liệu có thể lập chỉ mục. Nếu mã sản phẩm được dùng để lọc chính xác, cách lưu thường là chuỗi kiểu `keyword`.

## 6. Custom converter cho value object đơn giản

Với một value object có thể biểu diễn bằng một scalar, chẳng hạn `ProductCode`, ta có thể chuyển đổi giữa object và `String`.

Converter khi ghi:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class ProductCodeWriteConverter
        implements Converter<ProductCode, String> {

    @Override
    public String convert(ProductCode source) {
        return source.value();
    }
}
~~~

Converter khi đọc:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class ProductCodeReadConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        return new ProductCode(source);
    }
}
~~~

Entity có thể khai báo:

~~~java
@Field(type = FieldType.Keyword)
private ProductCode productCode;
~~~

Khi ghi, `ProductCode("KB-1001")` được chuyển thành chuỗi `"KB-1001"`. Khi đọc, chuỗi được chuyển lại thành `ProductCode`, và constructor thực hiện validation.

Cách này phù hợp với value object có một biểu diễn scalar rõ ràng. Nếu value object gồm nhiều thành phần cần truy vấn riêng, không nên nén toàn bộ thành một chuỗi duy nhất.

## 7. Lưu tiền tệ và số tiền

Tiền tệ không chỉ là một con số. Giá trị tiền cần đi cùng mã tiền tệ, ví dụ:

- `19.99 USD`
- `500000 VND`
- `2500 JPY`

Hai số tiền có cùng giá trị số nhưng khác currency không thể được coi là cùng một giá trị. Ví dụ `100 USD` và `100 JPY` không có cùng sức mua.

Không nên chỉ lưu số tiền vào một field numeric rồi bỏ mất currency code. Cũng không nên lưu cả chuỗi `"19.99 USD"` vào một field text nếu cần range query, sort hoặc aggregation theo số tiền.

Một biểu diễn document dễ truy vấn là tách số tiền và mã tiền tệ thành hai field:

~~~json
{
  "priceAmount": 1999,
  "priceCurrency": "USD"
}
~~~

Trong ví dụ này, `priceAmount` biểu diễn số tiền theo đơn vị nhỏ nhất của currency (minor units), còn `priceCurrency` lưu mã ISO 4217.

### Vì sao dùng minor units?

Lưu tiền bằng số nguyên theo đơn vị nhỏ nhất giúp tránh sai số làm tròn khi chuyển đổi giữa các kiểu số dấu phẩy động.

Ví dụ:

| Currency | Số chữ số thập phân thông dụng | Số tiền | Minor units |
|---|---:|---:|---:|
| USD | 2 | 19.99 | 1999 |
| VND | 0 | 500000 | 500000 |
| JPY | 0 | 2500 | 2500 |
| KWD | 3 | 12.345 | 12345 |

Số chữ số thập phân phụ thuộc currency. Java `Currency` cung cấp `getDefaultFractionDigits()` cho các mã tiền tệ ISO được hỗ trợ.

Nếu domain chỉ dùng một currency có scale cố định, có thể dùng `scaled_float` với `scalingFactor` phù hợp. Nhưng khi hỗ trợ nhiều currency có số chữ số thập phân khác nhau, minor units cùng currency code là cách biểu diễn rõ ràng hơn.

## 8. Domain Money và document projection

Domain có thể dùng value object riêng:

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {

    public Money {
        Objects.requireNonNull(amount, "amount must not be null");
        Objects.requireNonNull(currency, "currency must not be null");

        int fractionDigits = currency.getDefaultFractionDigits();
        if (fractionDigits < 0) {
            throw new IllegalArgumentException(
                    "Unsupported currency fraction digits: " + currency
            );
        }

        amount = amount.setScale(fractionDigits);
    }
}
~~~

Trong thực tế, cách làm tròn phải là quy tắc nghiệp vụ được xác định rõ. Ví dụ trên sử dụng `setScale` với rounding mode mặc định là `UNNECESSARY`; nếu số tiền có phần lẻ vượt quá số chữ số được phép, phép chuyển đổi sẽ thất bại thay vì âm thầm làm tròn.

Một document model riêng biểu diễn tiền bằng minor units:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Long)
    private Long priceMinorUnits;

    @Field(type = FieldType.Keyword)
    private String priceCurrency;

    // Các field khác và getter/setter
}
~~~

Chuyển từ domain `Money` sang document:

~~~java
import java.math.BigDecimal;
import java.util.Currency;

public final class MoneyDocumentMapper {

    private MoneyDocumentMapper() {
    }

    public static long toMinorUnits(Money money) {
        int fractionDigits =
                money.currency().getDefaultFractionDigits();

        if (fractionDigits < 0) {
            throw new IllegalArgumentException(
                    "Unsupported currency: " + money.currency()
            );
        }

        return money.amount()
                .movePointRight(fractionDigits)
                .longValueExact();
    }

    public static Money toMoney(
            long minorUnits,
            String currencyCode
    ) {
        Currency currency = Currency.getInstance(currencyCode);
        int fractionDigits = currency.getDefaultFractionDigits();

        if (fractionDigits < 0) {
            throw new IllegalArgumentException(
                    "Unsupported currency: " + currencyCode
            );
        }

        BigDecimal amount =
                BigDecimal.valueOf(minorUnits, fractionDigits);

        return new Money(amount, currency);
    }
}
~~~

`longValueExact()` bảo đảm không âm thầm bỏ phần thập phân hoặc tràn số khi chuyển đổi. Nếu amount không thể biểu diễn chính xác bằng minor units của currency, phép chuyển đổi sẽ báo lỗi.

Document projection tách biệt cấu trúc lưu trữ khỏi domain model. Khi mapping có nhiều field phục vụ tìm kiếm, đây thường là cách dễ kiểm soát hơn việc cố chuyển một object phức tạp thành một scalar.

### Lọc theo tiền tệ và khoảng giá

Khi tìm sản phẩm có giá từ 10 đến 100 USD, query cần lọc currency và range của minor units:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "priceCurrency": "USD"
          }
        },
        {
          "range": {
            "priceMinorUnits": {
              "gte": 1000,
              "lte": 10000
            }
          }
        }
      ]
    }
  }
}
~~~

Không nên so sánh `priceMinorUnits` giữa các currency khác nhau mà không quy đổi. `1000` minor units của USD là 10 USD, nhưng với JPY lại có ý nghĩa 1000 JPY. Nếu cần thống kê liên tiền tệ, cần một giá trị quy đổi có currency đích, tỷ giá và thời điểm quy đổi rõ ràng.

Elasticsearch phù hợp để tìm kiếm và lọc trên projection tiền tệ. Hệ thống kế toán hoặc nguồn dữ liệu giao dịch vẫn nên giữ quy tắc tính toán tiền chính xác và dữ liệu có thẩm quyền.

## 9. Khi nào nên dùng custom converter, khi nào nên dùng document model riêng?

Có hai chiến lược chính:

| Tình huống | Chiến lược phù hợp |
|---|---|
| Value object biểu diễn bằng một chuỗi hoặc số | Custom converter scalar |
| Enum cần lưu mã ổn định riêng | Custom read/write converter |
| Value object có nhiều thành phần cần truy vấn riêng | Document model hoặc mapping object |
| Money cần lọc theo amount và currency | Tách field numeric và currency code |
| Domain model khác đáng kể cấu trúc Elasticsearch | Document projection và mapper |
| Chỉ cần lưu/đọc một kiểu đơn giản đã được Spring hỗ trợ | Dùng conversion mặc định |

Custom converter phù hợp khi muốn giữ kiểu domain mạnh nhưng cách lưu có thể biểu diễn bằng một giá trị đơn giản.

Document model riêng phù hợp khi cấu trúc index được tối ưu cho truy vấn và có thể khác cấu trúc domain. Nó cũng giúp tránh việc annotation Elasticsearch lan rộng vào các domain class dùng chung cho nhiều tầng ứng dụng.

## 10. Tương thích dữ liệu khi thay đổi enum hoặc value object

Dữ liệu đã lưu trong Elasticsearch tồn tại độc lập với phiên bản code hiện tại. Vì vậy, thay đổi cách chuyển đổi có thể ảnh hưởng document cũ.

### Đổi tên enum constant

Nếu trước đây lưu `"PAID"` nhưng code mới đổi tên thành `"SETTLED"`, document cũ vẫn chứa `"PAID"`. Converter đọc mới cần hỗ trợ giá trị cũ trong giai đoạn chuyển đổi hoặc dữ liệu cần được cập nhật/reindex.

### Đổi mã enum

Nếu mã `"P"` đổi thành `"S"`, cần xác định cách đọc cả hai mã trong giai đoạn migration và cách cập nhật document cũ.

### Đổi cấu trúc Money

Nếu trước đây lưu `price` thành chuỗi, sau đó chuyển thành `priceMinorUnits` và `priceCurrency`, cần một bước migration để chuyển đổi document cũ. Chỉ thay Java class không làm thay đổi dữ liệu đã index.

### Thay đổi validation của value object

Nếu constructor mới từ chối một giá trị cũ, việc đọc document có thể thất bại. Cần kiểm tra dữ liệu hiện tại, hỗ trợ định dạng cũ trong thời gian chuyển đổi hoặc làm sạch dữ liệu trước khi áp dụng quy tắc mới.

Một chiến lược an toàn là dùng index version mới, reindex dữ liệu qua mapper chuyển đổi và chuyển alias sang index mới sau khi kiểm tra kết quả.

## 11. Các lỗi thường gặp

### Lưu enum bằng ordinal

Thứ tự enum thay đổi có thể khiến số cũ mang ý nghĩa khác. Hãy lưu tên hoặc mã ổn định.

### Dùng field text cho enum

Enum thường được dùng trong filter hoặc terms aggregation. Mapping `keyword` phù hợp hơn.

### Ghi enum bằng mã nhưng không có converter đọc ngược

Ghi `"P"` nhưng converter đọc chỉ biết `"PAID"` sẽ khiến mapping thất bại khi đọc document. Cần triển khai cả chiều ghi và chiều đọc.

### Lưu tiền nhưng bỏ currency code

Số tiền không có đơn vị tiền tệ là dữ liệu không đầy đủ. Hãy lưu currency code cùng amount.

### Dùng double cho phép tính tiền chính xác

Số dấu phẩy động nhị phân có thể không biểu diễn chính xác một số thập phân. Dùng `BigDecimal` trong domain và chọn cách biểu diễn document có quy tắc precision rõ ràng.

### So sánh minor units giữa các currency

Minor units phụ thuộc số chữ số thập phân của currency. Luôn lọc currency tương ứng trước khi so sánh amount hoặc thực hiện quy đổi có kiểm soát.

### Chuyển value object nhiều field thành một chuỗi

Nếu cần lọc theo từng thành phần, lưu chúng thành field riêng hoặc object mapping. Một chuỗi gộp làm mất khả năng truy vấn có cấu trúc.

### Không kiểm tra document cũ sau khi đổi converter

Converter mới có thể không đọc được định dạng cũ. Cần kiểm tra dữ liệu thực tế và lập kế hoạch migration.

## 12. Quy trình thiết kế conversion cho entity

Khi đưa một kiểu nghiệp vụ vào Spring Data Elasticsearch, có thể làm theo các bước:

1. Xác định kiểu domain và các invariant mà constructor/value object phải bảo vệ.
2. Quyết định dữ liệu sẽ lưu thành scalar, object hay nhiều field riêng.
3. Chọn mapping phù hợp với truy vấn: `keyword` cho enum/mã, numeric cho amount, field riêng cho currency.
4. Dùng conversion mặc định khi nó đáp ứng đúng định dạng dữ liệu.
5. Viết converter hai chiều cho value object scalar hoặc enum có mã riêng.
6. Đăng ký converter trong `ElasticsearchCustomConversions`.
7. Với value object nhiều thành phần, cân nhắc document projection để kiểm soát mapping.
8. Kiểm tra dữ liệu ghi ra document và đọc ngược về domain object.
9. Xác định cách xử lý document cũ khi tên enum, mã hoặc cấu trúc value object thay đổi.
10. Kiểm tra query thực tế trên các field sau khi lập chỉ mục.

## Kết luận

Enum thường được lưu dưới dạng chuỗi `keyword`; nếu cần mã nghiệp vụ ổn định, hãy dùng custom read/write converter. Value object scalar như `ProductCode` có thể chuyển đổi hai chiều qua chuỗi. Tiền tệ cần lưu cả amount và currency code; dùng minor units hoặc một numeric representation có precision được xác định rõ để phục vụ range query và sort. Khi domain model khác cấu trúc tìm kiếm, document projection giúp kiểm soát dữ liệu Elasticsearch mà không làm mất ý nghĩa nghiệp vụ.

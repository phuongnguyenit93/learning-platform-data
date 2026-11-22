# Custom converter cho kiểu dữ liệu nghiệp vụ trong Spring Data MongoDB

## 1. Bài toán: kiểu dữ liệu đúng trong Java nhưng lưu xuống MongoDB chưa như mong muốn

Giả sử ứng dụng quản lý hóa đơn có một kiểu nghiệp vụ **Money**. Trong Java, số tiền không nên chỉ là **double**, vì cần giữ giá trị thập phân chính xác, mã tiền tệ và các bất biến của domain.

Một hóa đơn:

~~~text
Invoice INV-100
  customer = C-17
  total = Money(19.90, USD)
~~~

Khi lưu MongoDB, nhóm phát triển muốn tài liệu BSON có cấu trúc rõ ràng:

~~~javascript
{
  _id: "INV-100",
  customerId: "C-17",
  total: {
    amount: NumberDecimal("19.90"),
    currency: "USD"
  }
}
~~~

Nhưng domain Java có thể dùng các kiểu phức tạp, bất biến, thư viện ngoài hoặc có tên trường không khớp BSON. Nếu cứ để framework tự ánh xạ, kết quả có thể không đúng hợp đồng dữ liệu mong muốn, chẳng hạn giá trị tiền thành string, nhiều trường nội bộ bị lưu, hoặc một object Java bị phân rã theo cách phụ thuộc vào cấu trúc lớp.

**Custom converter** trong **Spring Data MongoDB** giúp quyết định cách chuyển đổi giữa **kiểu nghiệp vụ** và **kiểu giá trị lưu trữ BSON/MongoDB**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Hiểu vai trò **MappingMongoConverter** và cơ chế ánh xạ mặc định.
2. Phân biệt **reading converter** và **writing converter**.
3. Xây kiểu value object nghiệp vụ và chuyển đổi sang BSON bằng **Converter<S, T>**.
4. Đăng ký converter qua **MongoCustomConversions** trong Spring Boot/Spring Data.
5. Sử dụng **Decimal128** đúng cách cho tiền tệ, tránh **double** làm sai số.
6. Truy vấn/index trên giá trị đã chuyển đổi và hiểu điểm khác biệt giữa entity properties với trường BSON.
7. So sánh custom converter với **@Field(targetType)**, DTO mapping và property-scoped converters.
8. Quản lý lỗi đọc dữ liệu cũ, schema evolution và migration.
9. Tránh converter toàn cục quá rộng, định dạng mất thông tin, xung đột hoặc tính toán nghiệp vụ ngoài phạm vi persistence.
10. Thiết kế unit/integration tests và đo chi phí chuyển đổi khi có hàng triệu documents.

## 2. Custom converter nằm ở đâu trong luồng dữ liệu?

Một thao tác save hoặc find qua Spring Data:

~~~text
                         APPLICATION / DOMAIN
                     Invoice { total: Money }
                                |
                                v
                      MongoRepository / MongoTemplate
                                |
                                v
                       MappingMongoConverter
                         |           |
                 Mapping metadata    MongoCustomConversions
                 @Id, @Field, ...    custom read/write converters
                         |           |
                         +-----+-----+
                               |
                               v
                    org.bson.Document / BSON
                               |
                               v
                        MongoDB Java Driver
                               |
                               v
                    MongoDB collection: invoices
~~~

Theo chiều đọc, đường đi đảo lại:

~~~text
BSON returned by MongoDB
      |
      v
MongoDB Driver
      |
      v
MappingMongoConverter + ReadingConverter
      |
      v
Invoice with Money value object
~~~

**MappingMongoConverter** thực hiện mapping dữ liệu của Spring Data MongoDB. **MongoCustomConversions** là registry các conversion rules được MappingMongoConverter sử dụng khi gặp những cặp kiểu mà bạn đã đăng ký phù hợp.

### 2.1. Default mapping đã làm được những gì?

Trước khi viết converter, Spring Data MongoDB đã hỗ trợ nhiều thao tác:

- Mapping Java object tới BSON document dựa trên field/property metadata.
- Chuyển đổi các kiểu phổ biến: String, numeric primitives/wrappers, collections, maps, enum và nhiều kiểu ngày giờ được hỗ trợ.
- Áp dụng **@Id**, **@Field**, **@Transient**, custom field names và type metadata theo cấu hình.
- Dùng constructor/record support cho immutable domain types trong những phiên bản phù hợp.
- Chuyển đổi những property types được MongoDB native mapping và Spring conversion service hỗ trợ.

Vì vậy không nhất thiết phải có custom converter cho mọi Java record hay class.

### 2.2. Khi nào thật sự cần custom converter?

Những nhu cầu phù hợp:

| Value object | Java representation | BSON representation mong muốn |
|---|---|---|
| **Money** | BigDecimal + currency code | Embedded document với Decimal128 và string. |
| **EmailAddress** | Kiểu tự validate | Một string canonical. |
| **PhoneNumber** | Parsed number + country code | String E.164 đã chuẩn hóa. |
| **BusinessStatus** | Enum/domain code | Stable external code string. |
| **GeoCoordinate** | Lat/lon có invariant | Embedded point hoặc GeoJSON đúng schema. |
| **BookingPeriod** | Start/end và quy tắc interval | Hai timestamp có tên/định dạng cố định. |
| **EncryptedValue** | Value object bảo vệ dữ liệu | Ciphertext + key/version metadata theo thiết kế an toàn. |

Lý do chính là **kiểm soát hợp đồng persistence**, không phải chỉ để giảm số dòng code.

### 2.3. Converter không thay thế mọi lớp khác

Phân biệt:

~~~text
HTTP JSON serializer:
  Java object <-> JSON request/response

DTO/domain mapper:
  API DTO <-> business/domain object

Spring Data MongoDB converter:
  domain property/entity <-> BSON storage value
~~~

Một custom MongoDB converter **không tự điều chỉnh JSON API** của Jackson, không chuyển dữ liệu trong Kafka, không thay đổi schema của một database SQL khác và không tự viết migration cho documents cũ.

### 2.4. Loại giá trị nguồn và đích quan trọng

Spring Data phân biệt **native MongoDB store types** với **domain types**. Các cặp mà cả nguồn và đích đều là kiểu lưu trữ native có thể gây mơ hồ về hướng chuyển đổi.

Ví dụ:

~~~text
String -> BigDecimal
BigDecimal -> String
~~~

Không nên đăng ký bừa các conversions toàn cục mà không hiểu nơi áp dụng. Sử dụng **@ReadingConverter** hoặc **@WritingConverter** để xác định ý định và tránh làm lệch mapping các thuộc tính khác.

## 3. Chọn hợp đồng dữ liệu BSON trước khi viết converter

Một converter tốt phải có **data contract** rõ:

~~~text
Java type:
  Money { BigDecimal amount, String currencyCode }

BSON storage:
  total.amount   -> Decimal128
  total.currency -> string ISO currency code

Validation:
  currency is recognized and normalized
  amount is a decimal value within Decimal128 range
  no silent rounding or FX conversion
~~~

### 3.1. Vì sao không dùng double cho tiền?

Số nhị phân IEEE-754 double không thể biểu diễn chính xác tất cả phân số thập phân:

~~~java
double value = 0.1 + 0.2;
System.out.println(value); // thường in 0.30000000000000004
~~~

Trong kế toán/thanh toán, **BigDecimal** là lựa chọn thông dụng để biểu diễn amount trong domain. MongoDB có kiểu **BSON Decimal128** cho decimal chính xác trong phạm vi precision/exponent mà nó hỗ trợ.

**BigDecimal không có phạm vi vô hạn khi đổi sang Decimal128**: Decimal128 giới hạn precision và exponent. Converter phải xử lý lỗi nếu value không biểu diễn được, thay vì âm thầm đổi sang double hoặc cắt chữ số.

### 3.2. Vì sao cần lưu currency?

~~~text
19.90 USD
19.90 EUR
19.90 JPY
~~~

Ba con số không thể được xem như cùng một giá trị tiền. Một Money object nên giữ **amount + currency**, và mọi phép cộng/so sánh xuyên currencies phải theo rule nghiệp vụ riêng.

**Converter không được tự tra tỷ giá ngoại tệ** khi đọc/ghi: tỷ giá thay đổi theo thời gian, khiến round-trip không ổn định và việc đọc database có side effects.

### 3.3. Hai thiết kế lưu tiền thường gặp

**Thiết kế A — Decimal128 amount + currency:**

~~~javascript
total: {
  amount: NumberDecimal("19.90"),
  currency: "USD"
}
~~~

Ưu điểm: giữ giá trị thập phân và có thể dùng toán tử so sánh/aggregation numeric của MongoDB trong phạm vi cùng currency.

**Thiết kế B — minorUnits + currency:**

~~~javascript
total: {
  minorUnits: NumberLong("1990"),
  currency: "USD"
}
~~~

Ưu điểm: integer arithmetic cho những amount trong phạm vi 64-bit. Tuy nhiên **không phải currency nào cũng có hai chữ số sau dấu thập phân**; JPY, KWD, VND và các quy tắc business khác có minor-unit exponent riêng. Quy đổi đòi hỏi validation/rounding policy và tránh overflow.

Hai mô hình đều có trade-offs. Trong bài này, ta chọn **Decimal128 + ISO currency code** để minh họa custom converter một cách minh bạch.

### 3.4. Cấu trúc BSON quyết định query và index

Khi total là document có hai fields:

~~~javascript
db.invoices.createIndex({
  tenantId: 1,
  "total.currency": 1,
  "total.amount": 1
});
~~~

Bạn có thể lọc invoices cùng currency rồi so amount. Nếu tự chuyển amount thành string, numeric range queries và sort sẽ có semantics khác: **"100" đứng trước hay sau "20" theo thứ tự chuỗi không tương đương so số**.

Hãy chọn định dạng lưu trữ **trước khi phát triển cả một tập query/index**, thay vì thay converter sau khi đã có dữ liệu production mà không migration.

## 4. Tạo kiểu nghiệp vụ Money bất biến

Ví dụ dùng Java 17+ và Spring Data MongoDB có hỗ trợ records/value objects. Tách domain type khỏi chi tiết BSON: **Money không cần biết Decimal128 hay Document**.

~~~java
package com.example.billing.domain;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Locale;
import java.util.Objects;

public record Money(BigDecimal amount, String currencyCode) {

    public Money {
        Objects.requireNonNull(amount, "amount is required");
        Objects.requireNonNull(currencyCode, "currency is required");

        currencyCode = currencyCode.trim()
                .toUpperCase(Locale.ROOT);

        if (!currencyCode.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "Currency code must have three letters");
        }

        Currency.getInstance(currencyCode);
    }

    public static Money of(String decimal, String currency) {
        return new Money(new BigDecimal(decimal), currency);
    }
}
~~~

### 4.1. Vì sao value object không phụ thuộc MongoDB?

Domain có thể:

~~~java
Money price = Money.of("19.90", "usd");
Money tax = Money.of("1.99", "USD");
~~~

Money giữ được business semantics dù ứng dụng về sau chuyển một phần dữ liệu sang SQL, event stream hoặc external API.

Các quyết định như **không cho âm**, **scale tối đa hai số thập phân** hoặc **làm tròn thuế** phụ thuộc sản phẩm và currency; không tự ép chúng vào class ví dụ khi chưa có business contract. Với JPY hay KWD, scale cố định bằng 2 có thể sai.

### 4.2. Bất biến về currency

Trong record compact constructor, biến tham số **currencyCode** được chuẩn hóa trước khi record field được gán.

~~~text
Input:
  Money(19.90, "usd")

Domain:
  amount       = 19.90
  currencyCode = "USD"
~~~

Chuẩn hóa tại domain boundary giúp converter giữ nhiệm vụ chuyển representation thay vì vừa chuyển vừa tùy tiện đổi business values.

### 4.3. BigDecimal.equals và scale

~~~java
new BigDecimal("19.90").equals(
        new BigDecimal("19.9")
); // false: scale differs

new BigDecimal("19.90").compareTo(
        new BigDecimal("19.9")
); // 0: numerically equal
~~~

Nếu business coi hai amount tương đương, cần quy định **normalization/equality policy**. Bài ví dụ giữ nguyên BigDecimal representation để dễ thấy round-trip; không tự gọi stripTrailingZeros gây thay đổi scale ngầm.

## 5. Writing converter: Money → BSON Document

Converter triển khai **org.springframework.core.convert.converter.Converter**, đánh dấu **@WritingConverter** để Spring Data biết quy tắc dùng khi **ghi**.

~~~java
package com.example.billing.persistence;

import com.example.billing.domain.Money;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

import java.util.Objects;

@WritingConverter
public final class MoneyWriteConverter
        implements Converter<Money, Document> {

    @Override
    public Document convert(Money source) {
        Objects.requireNonNull(source, "source");

        return new Document(
                "amount",
                new Decimal128(source.amount())
        ).append(
                "currency",
                source.currencyCode()
        );
    }
}
~~~

Khi gọi:

~~~java
Money money = Money.of("19.90", "USD");

Document stored = new MoneyWriteConverter().convert(money);
~~~

Giá trị BSON mong muốn:

~~~javascript
{
  amount: NumberDecimal("19.90"),
  currency: "USD"
}
~~~

### 5.1. Decimal128 không phải BigDecimal vô giới hạn

~~~java
new Decimal128(source.amount());
~~~

chuyển BigDecimal sang **BSON Decimal128**, vốn có giới hạn precision và exponent. Giá trị vượt phạm vi có thể làm conversion thất bại.

**Không** dùng cách chữa cháy:

~~~java
// Không nên: có thể mất độ chính xác thập phân.
double approximate = source.amount().doubleValue();
~~~

Nếu nghiệp vụ thật sự cần precision lớn hơn Decimal128, cần thiết kế persistence khác (chẳng hạn decimal string có kiểm soát hoặc integer encoding), và xem lại nhu cầu query/index numeric.

### 5.2. Vì sao converter nên thuần?

Một write converter tốt:

- Không gọi REST API hoặc database khác.
- Không lấy tỷ giá thời gian thực.
- Không tự tính thuế.
- Không dùng thời điểm hiện tại để sinh currency amount.
- Không làm thay đổi Money object gốc.
- Không sửa các fields ngoài phạm vi value object.

Lý tưởng là **deterministic**: cùng Money và cùng schema version cho ra cùng BSON representation.

### 5.3. Không để converter âm thầm sửa dữ liệu

Chẳng hạn **19.999 USD** không được tự động thành **20.00 USD** chỉ vì lớp converter thích hai chữ số thập phân. Nếu nghiệp vụ cần làm tròn, hãy làm rõ ở domain/application service với rounding policy được duyệt.

## 6. Reading converter: BSON Document → Money

Chiều đọc chuyển MongoDB document nhỏ thành domain value object.

~~~java
package com.example.billing.persistence;

import com.example.billing.domain.Money;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

import java.util.Objects;

@ReadingConverter
public final class MoneyReadConverter
        implements Converter<Document, Money> {

    @Override
    public Money convert(Document source) {
        Objects.requireNonNull(source, "source");

        Object rawAmount = source.get("amount");
        Object rawCurrency = source.get("currency");

        if (!(rawAmount instanceof Decimal128 decimal)) {
            throw new IllegalArgumentException(
                    "Expected BSON Decimal128 in total.amount");
        }

        if (!(rawCurrency instanceof String currency)) {
            throw new IllegalArgumentException(
                    "Expected string in total.currency");
        }

        return new Money(
                decimal.bigDecimalValue(),
                currency
        );
    }
}
~~~

### 6.1. Vì sao không ép kiểu trực tiếp?

Đoạn code thiếu kiểm tra:

~~~java
Decimal128 amount =
        (Decimal128) source.get("amount");
~~~

có thể phát sinh **ClassCastException** thiếu ngữ cảnh nếu production có một document cũ lưu amount dưới kiểu string/double.

Kiểm tra tường minh như ví dụ giúp phân biệt:

- Field thiếu.
- Dữ liệu có kiểu BSON không mong muốn.
- Phiên bản schema cũ.
- Dữ liệu hỏng hoặc bị ghi ngoài ứng dụng.

### 6.2. Null và field thiếu

Khi toàn bộ property **total** là null hoặc không có, Spring mapping có thể xử lý ở cấp property mà không gọi converter cho null. Đây là điểm **khác** với một subdocument có:

~~~javascript
total: {
  currency: "USD"
}
~~~

Trường hợp này được chuyển vào reader nhưng thiếu amount, nên reader cần từ chối, dùng default có kiểm soát hoặc xử lý schema-version migration tùy hợp đồng.

**Đừng tự đổi missing amount thành 0** nếu không có quy tắc nghiệp vụ: có thể biến dữ liệu hỏng thành một hóa đơn trông hợp lệ.

### 6.3. Round-trip contract

Một property của custom converter nên thỏa:

~~~text
Money
  --write--> BSON Document
  --read---> Money
~~~

Với value hợp lệ, kỳ vọng amount/currency không mất thông tin. Tuy nhiên **round-trip của object** và **equality của bytes BSON** là hai điều khác nhau: có thể đổi field order, subtype hoặc scale nếu schema policy cho phép.

### 6.4. Converter strict và backward compatibility

Reader ở trên cố ý **strict**: chỉ chấp nhận Decimal128. Nếu collection còn documents cũ có amount là string, cần **kế hoạch migration hoặc một phiên bản reader có compatibility window**. Không nên nới reader để nhận mọi kiểu không kiểm soát, vì có thể che lỗi writer mới.

## 7. Đăng ký Money converters với MongoCustomConversions

Hai class có annotation chưa đủ nếu ứng dụng không đưa chúng vào registry mapping.

Trong Spring Boot/Spring Data MongoDB:

~~~java
package com.example.billing.config;

import com.example.billing.persistence.MoneyReadConverter;
import com.example.billing.persistence.MoneyWriteConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

import java.util.List;

@Configuration
public class MongoConversionConfiguration {

    @Bean
    MongoCustomConversions mongoCustomConversions() {
        return new MongoCustomConversions(
                List.of(
                        new MoneyWriteConverter(),
                        new MoneyReadConverter()
                )
        );
    }
}
~~~

Khi **MongoTemplate/MongoRepository** sử dụng MappingMongoConverter được cấu hình từ Spring context này, Money sẽ được chuyển theo converters đã đăng ký.

### 7.1. Quan hệ giữa annotation và registry

- **@WritingConverter** xác định hướng Money → Document.
- **@ReadingConverter** xác định hướng Document → Money.
- **MongoCustomConversions** đăng ký các converter instances.
- **MappingMongoConverter** áp dụng registry khi cần chuyển giá trị.
- **MongoTemplate/MongoRepository** dùng mapping converter tương ứng trong các thao tác persistence.

Một converter có **@Component** hoặc xuất hiện trong classpath **không đồng nghĩa** mọi ứng dụng Spring Data sẽ tự nhận nó vào MongoCustomConversions. Đăng ký chính thức cần theo cấu hình framework đang dùng.

### 7.2. Nếu ứng dụng đã có MongoCustomConversions

Không tạo bean mới rồi vô tình **bỏ mất những converters đang hoạt động**. Gom danh sách vào cấu hình hiện tại hoặc dùng extension point của phiên bản Spring Data đang chạy.

Khi tự cấu hình **MongoMappingContext**, **MappingMongoConverter** hoặc **MongoTemplate**, cần kiểm tra registry custom conversions đã được gắn vào instance thực tế hay chưa; một bean tồn tại nhưng không được converter sử dụng sẽ không có tác dụng.

### 7.3. Không tạo registry mới cho mỗi request

MongoCustomConversions là cấu hình mapping dùng chung, không phải object cần khởi tạo mỗi lần gọi save/find. Converter nên **stateless, thread-safe** và không giữ state phụ thuộc request/tenant trong instance.

### 7.4. Phạm vi của global registration

Vì MoneyWriteConverter là converter toàn cục theo cặp kiểu **Money → Document**, mọi property Money dùng cùng mapping framework có thể được áp dụng quy tắc này.

Nếu chỉ một field Money cần cách lưu khác, cân nhắc **property-scoped converter** hoặc tách thành những domain types có ý nghĩa khác. Đừng thêm một converter global thứ hai cho cùng cặp Money/Document rồi dựa vào thứ tự đăng ký không được kiểm soát.

### 7.5. Version và Boot auto-configuration

Code dùng **MongoCustomConversions(List<...>)** là kiểu cấu hình phổ biến ở nhiều phiên bản Spring Data MongoDB. APIs/extension points có thể thay đổi qua các major versions. Kiểm tra đúng **Spring Boot/Spring Data MongoDB version** của dự án, đặc biệt nếu đang dùng một cấu hình tự tạo MongoTemplate/MongoClient thay vì Boot auto-configuration.

## 8. Dùng Money trong entity và MongoRepository

### 8.1. Entity Invoice

~~~java
package com.example.billing.persistence;

import com.example.billing.domain.Money;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

public class Invoice {
    // Nội dung hoàn chỉnh sẽ dùng @Document ở class.
}
~~~

Đối với một entity thực:

~~~java
package com.example.billing.persistence;

import com.example.billing.domain.Money;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "invoices")
public class Invoice {

    @Id
    private String id;

    private String tenantId;
    private String customerId;
    private Money total;

    protected Invoice() {
        // Constructor dành cho mapping framework.
    }

    public Invoice(
            String id,
            String tenantId,
            String customerId,
            Money total) {
        this.id = id;
        this.tenantId = tenantId;
        this.customerId = customerId;
        this.total = total;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public Money getTotal() {
        return total;
    }
}
~~~

Ở entity này, Spring Data quản lý id/tenantId/customerId theo mapping mặc định và dùng custom converter cho **total**.

**Lưu ý về id:** với **@Id String**, Spring Data có các quy tắc chuyển chuỗi ObjectId-compatible sang ObjectId trong những cấu hình điển hình. Nếu business yêu cầu giữ chính xác string BSON **_id**, cân nhắc **@MongoId(FieldType.STRING)** theo version hoặc thiết kế ID rõ ràng và kiểm tra raw stored BSON. Ví dụ **INV-100** không phải chuỗi hex ObjectId.

### 8.2. Repository

~~~java
package com.example.billing.persistence;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface InvoiceRepository
        extends MongoRepository<Invoice, String> {
}
~~~

Lưu:

~~~java
Invoice invoice = new Invoice(
        "INV-100",
        "tenant-a",
        "C-17",
        Money.of("19.90", "USD")
);

repository.save(invoice);
~~~

Đọc:

~~~java
Invoice found = repository.findById("INV-100")
        .orElseThrow();

Money total = found.getTotal();
System.out.println(total.amount());       // 19.90
System.out.println(total.currencyCode()); // USD
~~~

Không cần gọi MoneyReadConverter hoặc MoneyWriteConverter thủ công từ repository service: **MappingMongoConverter** áp dụng chúng khi framework đọc/ghi.

### 8.3. Document lưu trong MongoDB

Về mặt logic:

~~~javascript
{
  _id: "INV-100",
  tenantId: "tenant-a",
  customerId: "C-17",
  total: {
    amount: NumberDecimal("19.90"),
    currency: "USD"
  }
}
~~~

Đây là **hình dạng dữ liệu minh họa**; tùy cấu hình, Spring Data có thể lưu thêm **_class** hoặc type hints ở entity level. Custom converter Money trả Document gồm hai trường định nghĩa trong converter, không tự thêm Java class name vào mỗi Money field.

### 8.4. Đổi tên property bằng @Field

Nếu:

~~~java
@Field(name = "total_value")
private Money total;
~~~

thì field path trong MongoDB trở thành **total_value.amount** và **total_value.currency**. Converter Money chỉ điều khiển cấu trúc **bên trong** value, còn tên field chứa value do entity mapping quyết định.

Khi truy vấn bằng MongoTemplate với domain property paths, MappingMongoConverter/QueryMapper có thể thực hiện mapping tên fields theo metadata. Với raw driver query, phải dùng tên BSON đúng.

### 8.5. Object bất biến và constructor mapping

Value object Money là record bất biến. **Invoice** có thể dùng mutable fields hoặc constructor binding theo Spring Data version. Custom converter phù hợp với immutable value objects vì khi đọc nó **khởi tạo một Money mới** từ BSON, không cần setters trên Money.

Không dùng reflection/setAccessible thủ công để chỉnh Money record sau khi constructor chạy.

## 9. Truy vấn và index sau khi dùng custom converter

Converter quyết định cách bytes được lưu; MongoDB query engine làm việc với **BSON thực**, không hiểu domain type Money của Java.

### 9.1. Lọc theo currency và amount

Trong mongosh:

~~~javascript
db.invoices.find({
  tenantId: "tenant-a",
  "total.currency": "USD",
  "total.amount": {
    $gte: NumberDecimal("100.00")
  }
});
~~~

Đây là so sánh **numeric Decimal128** trong một currency xác định.

### 9.2. Tương đương qua MongoTemplate

~~~java
import com.example.billing.persistence.Invoice;
import org.bson.types.Decimal128;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import java.math.BigDecimal;
import java.util.List;

public final class InvoiceSearch {
    private final MongoTemplate template;

    public InvoiceSearch(MongoTemplate template) {
        this.template = template;
    }

    public List<Invoice> findLargeUsdInvoices(String tenantId) {
        Query query = new Query(
                Criteria.where("tenantId").is(tenantId)
                        .and("total.currency").is("USD")
                        .and("total.amount").gte(
                                new Decimal128(
                                        new BigDecimal("100.00")
                                )
                        )
        );

        return template.find(query, Invoice.class);
    }
}
~~~

Chọn **Decimal128** tường minh trong Criteria ví dụ để BSON comparison type rõ. Nếu dự án dùng property aliases, property value converters hoặc conventions khác, cần xác nhận **QueryMapper thực tế biến query thành BSON gì**.

### 9.3. Index phù hợp

~~~javascript
db.invoices.createIndex({
  tenantId: 1,
  "total.currency": 1,
  "total.amount": 1
});
~~~

Với query equality tenantId + currency và range amount, compound index là ứng viên hợp lý. Nhưng không mặc định tối ưu nếu workloads khác: phải kiểm tra **explain**, index size, write cost và cardinality.

### 9.4. Không so sánh số tiền của các currencies khác nhau trực tiếp

~~~javascript
db.invoices.find({
  "total.amount": { $gte: NumberDecimal("100.00") }
});
~~~

Một truy vấn toàn collection như trên về BSON thì hợp lệ, nhưng về **nghiệp vụ** có thể vô nghĩa khi dữ liệu trộn USD, VND, JPY...

Nên:

- Giới hạn currency trong predicate, hoặc
- Chuyển đổi sang reporting currency với tỷ giá và thời điểm xác định ở một pipeline/business process được thiết kế rõ.

Đừng để converter Money bí mật đổi currency khi ghi.

### 9.5. Exact object equality khác field range query

Nếu:

~~~java
Criteria.where("total").is(Money.of("19.90", "USD"));
~~~

Spring Data có thể dùng custom converter cho toàn bộ value trong query, tùy path và query mapping. Nhưng **embedded BSON document equality** có semantics về cấu trúc và thứ tự fields khác so với predicates trên từng subfield.

Để lọc theo amount/currency, nên viết predicates có ý nghĩa rõ ràng trên **total.amount** và **total.currency**, đặc biệt khi schema có thể thêm field mới như **schemaVersion**.

### 9.6. MongoTemplate update và raw driver

Ví dụ update qua Spring Data:

~~~java
import org.springframework.data.mongodb.core.query.Update;

Update update = new Update()
        .set("total", Money.of("29.90", "USD"));
~~~

Các Spring Data update paths thông thường dùng mapping converter/UpdateMapper khi cần chuyển domain values. **Tuy nhiên**, viết trực tiếp với Java Driver:

~~~java
mongoTemplate.getCollection("invoices")
        .updateOne(filter, rawUpdateBson);
~~~

là sử dụng native driver API: một raw BSON Document được xây thủ công **không tự đi qua quy tắc mapping Money như khi lưu Invoice qua repository**.

Trong codebase lớn, cần thống nhất thao tác nào đi qua Spring Data mapping và thao tác nào dùng raw driver, nhất là bulk updates, aggregation pipelines, scripts và migrations.

### 9.7. Aggregation trên kiểu dữ liệu đã chuyển đổi

Khi lưu Decimal128, aggregation MongoDB có thể dùng:

~~~javascript
db.invoices.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      "total.currency": "USD"
    }
  },
  {
    $group: {
      _id: "$total.currency",
      totalAmount: {
        $sum: "$total.amount"
      },
      invoiceCount: {
        $sum: 1
      }
    }
  }
]);
~~~

Một aggregation output có schema riêng (**_id**, **totalAmount**, **invoiceCount**). Reading converter Money không tự biến mọi aggregation result thành Invoice; hãy map vào DTO/projection thích hợp.

Nếu stored amount là String, **$sum** không có numeric semantics mong muốn. Đây là một lý do chọn BSON type ngay từ đầu.

### 9.8. Query optimization sau conversion

Không kết luận một converter “làm query chậm” chỉ vì sau khi đổi data format, index bị mất hiệu quả. Hãy phân biệt:

1. **Serialization cost** trong Java process.
2. **Document size/index key size** sau conversion.
3. **MongoDB query plan** trên BSON values.
4. **Network transfer**.
5. **Result materialization** từ Document thành domain objects.

Đo riêng từng lớp khi tối ưu hệ thống lớn.

## 10. Trường hợp chỉ cần @Field(targetType), không cần custom converter

Nếu business entity chỉ có **BigDecimal** field và mục đích duy nhất là lưu thành BSON Decimal128, có thể đơn giản hơn:

~~~java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

public class ProductPrice {

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    // Constructor, getters/setters...
}
~~~

Trong các phiên bản Spring Data MongoDB hỗ trợ, **@Field(targetType = FieldType.DECIMAL128)** hướng dẫn mapping về kiểu BSON mong muốn cho field.

### 10.1. Khi chọn @Field(targetType)

Phù hợp khi:

- Domain type đã được Spring Data hỗ trợ.
- Chỉ muốn chỉ rõ **store type**.
- Không cần gộp nhiều fields thành một custom BSON structure.
- Không có parsing/validation đặc thù nằm ngoài domain.

### 10.2. Khi chọn custom converter

Phù hợp khi:

- Domain là kiểu value object riêng (Money, EmailAddress...).
- Cần chuyển nhiều thuộc tính thành một storage value.
- Cần format ổn định khác mapping mặc định.
- Cần logic đọc legacy representation hoặc kiểm soát type/validation.

### 10.3. So sánh

| Bài toán | Lựa chọn cân nhắc |
|---|---|
| BigDecimal field → Decimal128 | **@Field(targetType)** thường đủ. |
| Money gồm amount + currency → embedded Document | **Custom read/write converter**. |
| REST DTO → entity | DTO mapper/service, không phải Mongo converter. |
| JSON response Money → string | Jackson serializer, không phải Mongo converter. |
| Một field cụ thể cần conversion khác | Property value converter khi version hỗ trợ. |
| Đổi toàn bộ dữ liệu MongoDB cũ | Data migration + compatibility reader. |
| Validate business transaction | Domain/service, không phải persistence converter. |

## 11. Converter cho value object lưu thành String

Không phải mọi value object đều cần một BSON subdocument.

Ví dụ **EmailAddress** trong domain có validation/normalization, nhưng MongoDB chỉ cần một string:

~~~java
public record EmailAddress(String canonical) {
    public EmailAddress {
        if (canonical == null || canonical.isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }
        canonical = canonical.trim();
        // Business validation policy belongs to this type/service.
    }
}
~~~

Writing converter:

~~~java
@WritingConverter
public final class EmailWriteConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.canonical();
    }
}
~~~

Reading converter:

~~~java
@ReadingConverter
public final class EmailReadConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

Những class này giả định imports tương ứng của **org.springframework.data.convert**, **org.springframework.core.convert.converter** và domain package. Đăng ký hai converter vào MongoCustomConversions giống ví dụ Money.

### 11.1. Vì sao String → EmailAddress cần @ReadingConverter?

**String** là native store type trong MongoDB. Nếu một converter nhận String, framework cần biết nó được dùng để **đọc** từ BSON string sang EmailAddress, tránh mơ hồ về hướng.

Điều này **không** có nghĩa mọi String fields sẽ thành EmailAddress: target Java property type cụ thể quyết định conversion cần thực hiện.

### 11.2. Không cố chuyển mọi String thành value object

Một converter toàn cục **String → String** để “chuẩn hóa mọi field” thường là ý tưởng nguy hiểm, vì nó có thể thay đổi tên người dùng, mã hash, IDs, JSON payload và nhiều fields khác.

Đặt validation/normalization trong **domain-specific types** hoặc property-specific mapping để hạn chế phạm vi.

### 11.3. Canonicalization phải có hợp đồng

Ví dụ email case normalization không đơn giản là lower-case mọi ký tự trong mọi ngữ cảnh; quy tắc domain cần tính đến ý nghĩa local-part, Unicode/IDN và chính sách thực tế.

Vì vậy ví dụ EmailAddress chỉ trim, không tự nhận là một email parser/normalizer production đầy đủ.

## 12. Custom converter cho mã trạng thái nghiệp vụ ổn định

Enum Java mặc định có thể được lưu bằng tên enum. Nếu ứng dụng đổi tên hằng số trong code, documents cũ có thể khó đọc.

Ví dụ một domain yêu cầu mã lưu trữ ổn định:

~~~text
OrderStatus in Java:
  NEW
  CONFIRMED
  CANCELLED

BSON:
  "N"
  "C"
  "X"
~~~

### 12.1. Enum chứa business code

~~~java
package com.example.orders.domain;

public enum OrderStatus {
    NEW("N"),
    CONFIRMED("C"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        for (OrderStatus item : values()) {
            if (item.code.equals(code)) {
                return item;
            }
        }
        throw new IllegalArgumentException(
                "Unknown order status code: " + code
        );
    }
}
~~~

### 12.2. Writer và reader

~~~java
@WritingConverter
public final class OrderStatusWriteConverter
        implements Converter<OrderStatus, String> {
    @Override
    public String convert(OrderStatus source) {
        return source.code();
    }
}
~~~

~~~java
@ReadingConverter
public final class OrderStatusReadConverter
        implements Converter<String, OrderStatus> {
    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

Imports theo package của **Converter**, **@ReadingConverter** và **@WritingConverter** đã được dùng trong ví dụ Money.

### 12.3. Đổi tên enum không tự đổi dữ liệu

Giả sử sau này Java đổi **CONFIRMED** thành **APPROVED**, nhưng mã storage vẫn **"C"**. Converter giữ backward compatibility nếu mapping code được giữ ổn định:

~~~text
MongoDB "C"
    -> OrderStatus.APPROVED
~~~

Đó là mục tiêu của **stable persistent code**. Tuy nhiên không tự sử dụng lại code "C" cho trạng thái nghiệp vụ khác, vì dữ liệu lịch sử sẽ bị diễn giải sai.

### 12.4. Unknown status: fail fast hay UNKNOWN?

Nếu reading converter gặp **"Z"**, có các chiến lược:

- **Fail fast** và báo dữ liệu không tương thích.
- Chuyển thành một trạng thái **UNKNOWN** nếu domain có định nghĩa rõ.
- Quarantine và migration những records không nhận diện.

Không tự coi "Z" là NEW hoặc CANCELLED để ứng dụng tiếp tục chạy, vì có thể gây hành động nghiệp vụ sai.

## 13. Global converter và property-specific converter

Global custom converter phù hợp khi **mọi Money đều phải lưu theo cùng một định dạng**. Nhưng đôi khi một loại Java được dùng cho nhiều mục đích lưu khác nhau.

Ví dụ:

~~~text
Invoice.total:
  Money -> Document(amount Decimal128, currency)

AnalyticsSnapshot.totalNormalized:
  Money -> custom summary form
~~~

Đăng ký hai converters global cùng **Money → Document** sẽ tạo xung đột/khó đoán nếu bạn không kiểm soát selection.

### 13.1. Property value converters

Một số phiên bản Spring Data hỗ trợ **PropertyValueConverter** và annotation **@ValueConverter** cho conversion gắn vào một property cụ thể.

Ý tưởng:

~~~text
Global:
  Money -> standard BSON object

Field-specific:
  Only AnalyticsSnapshot.totalNormalized
    -> special persisted value format
~~~

Các interface, context types, registry và constructor signatures cho property converters phụ thuộc **Spring Data Commons/MongoDB version**. Khi dùng, xem tài liệu của version thực tế để đăng ký converter đúng property; không đoán API từ một ví dụ phiên bản khác.

### 13.2. Khi nào tách thành domain type khác?

Nếu hai fields mang hai ý nghĩa nghiệp vụ thực sự khác nhau, có thể nên dùng hai types:

~~~java
record Money(BigDecimal amount, String currencyCode) {}
record ReportingMoney(BigDecimal amount, String reportingCurrency) {}
~~~

Đây là ví dụ về **đặt tên loại dữ liệu**, không phải gợi ý tạo lại Money mà bỏ validation. Một kiểu riêng với invariant riêng giúp conversion global ít mơ hồ hơn.

### 13.3. @Field(targetType) cũng property-scoped

Trường **BigDecimal amount** muốn lưu Decimal128 nhưng BigDecimal fields khác giữ mapping mặc định thì **@Field(targetType = FieldType.DECIMAL128)** có thể là lựa chọn gọn hơn global converter BigDecimal → Decimal128.

Không thay đổi representation của **tất cả BigDecimal trong mọi collections** chỉ để sửa một property.

## 14. Converter và ngày giờ, thời gian, UUID

Những business types liên quan thời gian thường cần xác định **timezone và precision policy**, không chỉ đổi class.

### 14.1. Instant và BSON Date

MongoDB BSON Date biểu diễn một timestamp tính theo **milliseconds từ Unix epoch (UTC)**. Java **Instant** có thể có precision đến nanoseconds.

Khi convert Instant sang BSON Date, precision dưới milliseconds có thể không được giữ. Nếu domain cần nanosecond precision, phải thiết kế representation khác (ví dụ lưu thêm fraction/nanos, với schema rõ).

### 14.2. LocalDateTime không mang timezone

~~~java
LocalDateTime.of(2026, 11, 14, 9, 30)
~~~

không mô tả một instant duy nhất trên toàn cầu. Muốn lưu như timestamp UTC, phải có **ZoneId** và quy tắc chuyển đổi rõ.

Một custom converter kiểu:

~~~text
LocalDateTime -> Date
~~~

nếu âm thầm lấy **system default timezone** của server có thể làm dữ liệu đọc khác nhau giữa development và production hoặc sau deploy ở region khác.

### 14.3. Date-only domain type

Ngày sinh, ngày đặt lịch theo business location hoặc ngày giao hàng có thể nên được biểu diễn bằng **LocalDate** và một storage policy rõ, tránh biến thành UTC Date lúc 00:00 rồi đọc lệch ngày ở timezone khác.

Một số Spring Data/JDK time conversions đã có sẵn, nên không viết converter trùng lặp khi chưa hiểu semantics mặc định.

### 14.4. UUID representation

MongoDB BSON Binary có nhiều subtype/UUID representation lịch sử. Không tùy tiện tạo converter **UUID ↔ byte[]** nếu driver đã có cơ chế cấu hình uuidRepresentation. Khi migrate từ legacy UUID representations, cần xác minh data type và endian/byte order tương ứng.

Một conversion sai có thể lưu được dữ liệu nhưng không query ra ID trước đó.

### 14.5. Timezone conversion không phải FX conversion

Việc convert timezone trong persistence cũng cần deterministic rules. Không lấy thời gian hiện tại để giải nghĩa một **LocalDateTime lịch sử**. Với thông tin đặt lịch cần giữ business timezone, có thể lưu cả:

~~~javascript
{
  startsAtUtc: ISODate("2026-11-14T02:30:00Z"),
  zoneId: "Asia/Ho_Chi_Minh"
}
~~~

Đây là ví dụ lưu cả instant và timezone identifier; exact contract phụ thuộc ứng dụng, DST semantics và mục tiêu tìm kiếm.

## 15. Null, optional fields và các giá trị không hợp lệ

### 15.1. Ba trường hợp cần phân biệt

~~~javascript
// A: field missing
{ _id: "A" }

// B: explicit null
{ _id: "B", total: null }

// C: malformed subdocument
{ _id: "C", total: { currency: "USD" } }
~~~

Nếu domain yêu cầu total non-null:

- A/B là **vi phạm data contract** hoặc legacy state cần xử lý.
- C là malformed representation; reader nên báo lỗi rõ.

Một converter **Document → Money** chỉ kiểm tra C khi nó được gọi với Document; A/B có thể do property mapping xử lý mà không vào converter.

### 15.2. Không đặt default âm thầm

Tránh:

~~~java
// Không nên nếu domain chưa định nghĩa:
if (source.get("amount") == null) {
    return Money.of("0", "USD");
}
~~~

Default sai có thể làm báo cáo tiền tệ, thuế hoặc thanh toán không chính xác.

### 15.3. Validation ở đâu?

| Quy tắc | Nơi phù hợp |
|---|---|
| Currency code hợp lệ | Domain Money constructor. |
| Amount không âm cho loại hóa đơn nhất định | Invoice business invariant/service. |
| BSON amount là Decimal128 | Reading converter. |
| Query chỉ truy cập đúng tenant | Authorization/service/repository query. |
| Currency conversion theo ngày tỷ giá | Business service rõ thời điểm/rate. |
| Legacy field migration | Migration job/compatibility reader. |
| HTTP JSON validation | API DTO/validation layer. |

Converter không phải một **business transaction validator**. Nó không tự kiểm tra quyền user, balance tài khoản hay gọi hệ thống ngoài.

### 15.4. Exception cần có thông tin phù hợp

Nếu reader gặp data lỗi, báo:

~~~text
Expected BSON Decimal128 at total.amount
~~~

Thay vì:

~~~text
Failed
~~~

Nhưng tránh log toàn bộ tài liệu hóa đơn, địa chỉ hoặc thông tin khách hàng. Có thể log collection, sanitized document identifier, field path, converter version và error category theo chính sách bảo mật.

### 15.5. Fail-fast và dịch vụ có legacy data

Trong môi trường mixed schema, fail-fast có thể làm một số documents cũ không đọc được. Có thể chọn:

1. Phát hành reader hỗ trợ hai định dạng trong thời gian chuyển đổi.
2. Migrate dữ liệu cũ theo batch an toàn.
3. Đo tỷ lệ documents legacy còn lại.
4. Chỉ sau đó bỏ compatibility reader.

Không mặc định một tolerant reader được giữ mãi; nó có thể che các writes sai định dạng mới trong nhiều năm.

## 16. Schema evolution: đổi converter không tự đổi documents cũ

Giả sử hệ thống phiên bản 1 lưu:

~~~javascript
{
  _id: "INV-OLD",
  total: {
    amount: "19.90",
    currency: "USD"
  }
}
~~~

Phiên bản 2 lưu:

~~~javascript
{
  _id: "INV-NEW",
  total: {
    amount: NumberDecimal("19.90"),
    currency: "USD"
  }
}
~~~

**Đổi MoneyWriteConverter trong code không migrate những documents đã lưu**. Reader mới chỉ chấp nhận Decimal128 nên có thể thất bại với INV-OLD.

### 16.1. Mixed BSON types nguy hiểm ở đâu?

~~~text
total.amount:
  some documents: BSON String
  others:         BSON Decimal128
~~~

Tác động:

- Query numeric **$gte: NumberDecimal("100.00")** không hoạt động như mong đợi với field string.
- Sort và aggregation có thể bị diễn giải khác theo BSON types.
- Index chứa các kiểu key không đồng nhất.
- Reader strict lỗi trên dữ liệu legacy.
- Old application instances có thể không đọc được data mới.

Converter deployment cần được quản lý như **schema migration**, không chỉ Java refactor.

### 16.2. Expand → migrate → contract

~~~text
Phase 1 — Expand:
  Deploy compatible reader:
    Decimal128 -> Money
    known legacy String -> Money

Phase 2 — New writes:
  Writer emits only Decimal128.
  Monitor invalid/legacy records.

Phase 3 — Migrate:
  Batch convert old String values to Decimal128.
  Use idempotent conditional updates.

Phase 4 — Verify:
  Check remaining legacy types and business queries.

Phase 5 — Contract:
  Remove legacy reader after approval.
~~~

Trong rolling deployment có nhiều service versions, phải kiểm tra **backward compatibility hai chiều** trước khi đổi định dạng writes.

### 16.3. Reader tương thích tạm thời

Thay reader strict trong migration window bằng:

~~~java
@ReadingConverter
public final class CompatibleMoneyReadConverter
        implements Converter<Document, Money> {

    @Override
    public Money convert(Document source) {
        Object rawAmount = source.get("amount");
        Object rawCurrency = source.get("currency");

        if (!(rawCurrency instanceof String currency)) {
            throw new IllegalArgumentException(
                    "Invalid total.currency type");
        }

        if (rawAmount instanceof Decimal128 decimal) {
            return new Money(decimal.bigDecimalValue(), currency);
        }

        if (rawAmount instanceof String legacyAmount) {
            return new Money(
                    new BigDecimal(legacyAmount),
                    currency
            );
        }

        throw new IllegalArgumentException(
                "Unsupported total.amount type");
    }
}
~~~

Đoạn code sử dụng imports tương ứng của Money, Document, Decimal128, BigDecimal, Converter và ReadingConverter.

Chỉ nhận **những legacy types đã được khảo sát và đồng ý**. Không tự nhận mọi BSON double/long và tự thay đổi precision. Không đăng ký cả reader strict và compatible cho cùng **Document → Money** rồi mong framework chọn ngẫu nhiên.

### 16.4. Đếm documents còn lưu kiểu cũ

Trong mongosh với quyền read:

~~~javascript
db.invoices.countDocuments({
  "total.amount": { $type: "string" }
});
~~~

Cần khảo sát cả malformed fields và records chưa có total. Không chạy bulk update production khi chưa có change approval, backup và dự trù I/O/replication.

### 16.5. Conditional migration

Một worker xử lý theo batch:

~~~text
Read legacy invoice and version
  -> parse String strictly to BigDecimal
  -> validate currency/amount
  -> convert to Decimal128
  -> update with condition on old value/version
  -> record success/failure/skip
  -> retry idempotently
~~~

Ví dụ update một document đã xác minh:

~~~javascript
db.invoices.updateOne(
  {
    _id: "INV-OLD",
    "total.amount": "19.90"
  },
  {
    $set: {
      "total.amount": NumberDecimal("19.90")
    }
  }
);
~~~

Predicate cũ giúp giảm nguy cơ ghi đè thay đổi concurrent. Ở quy mô lớn, migration cần cursor, batching, progress checkpoints, rate limit, error handling và rollback plan.

### 16.6. Schema version field

Khi representation phức tạp:

~~~javascript
total: {
  schemaVersion: 2,
  amount: NumberDecimal("19.90"),
  currency: "USD"
}
~~~

Version giúp reader xử lý formats đã biết; nhưng cả writer/reader, index, queries và migration đều phải cập nhật tương ứng. Ví dụ converter đầu bài chưa có version field nhằm giữ cấu trúc đơn giản.

### 16.7. Rollback binary không rollback BSON

Sau khi writer phát hành Decimal128, ứng dụng cũ chỉ biết String có thể fail nếu rollback phiên bản Java.

Thiết kế release ordering:

1. Đưa compatible reader tới mọi instances trước.
2. Chuyển writer sau khi old readers đã được thay.
3. Migrate/backfill theo batch.
4. Verify data và dependent consumers.
5. Bỏ legacy format khi đủ điều kiện.

Tính cả các consumers sử dụng raw driver, aggregation/reporting và scripts không đi qua MappingMongoConverter.

## 17. _class, type hints và polymorphic value objects

Spring Data MongoDB có thể lưu **_class** type hints cho mapped objects tùy cấu hình.

~~~javascript
{
  _id: "INV-100",
  _class: "com.example.billing.persistence.Invoice",
  total: {
    amount: NumberDecimal("19.90"),
    currency: "USD"
  }
}
~~~

### 17.1. Custom converter tự quản schema con

Nếu **MoneyWriteConverter** trả một Document thủ công, Spring Data không còn áp dụng default field-by-field mapping của Money trong bước đó.

~~~text
Default object mapping:
  inspect Money fields and annotations

Custom Money -> Document:
  converter explicitly emits amount and currency
~~~

Đây là ưu điểm để schema ổn định, nhưng cũng là trách nhiệm cập nhật converter khi persistence contract đổi.

### 17.2. Không phụ thuộc class name như business type code

Fully qualified Java class name thay đổi theo refactor. Spring Data có **@TypeAlias** và custom type mappers khi cần, nhưng một long-lived business schema nên cân nhắc **explicit stable discriminator**.

Ví dụ:

~~~javascript
{
  kind: "CARD",
  version: 1,
  last4: "1234"
}
~~~

Khi đọc **PaymentMethod**, reader dựa trên **kind/version** và validation rõ, không đoán type theo sự hiện diện của trường last4 hoặc phụ thuộc trực tiếp package name.

### 17.3. Polymorphism có migration contract

Đổi **kind: "CARD"** thành **"CREDIT_CARD"** cũng cần compatibility hoặc migration. Không tái sử dụng code đã phát hành cho semantic khác.

## 18. Converter và bảo mật dữ liệu

### 18.1. Converter không phải authorization layer

~~~text
Who can read this invoice?
  -> authentication + tenant/owner authorization

How is Money persisted?
  -> MappingMongoConverter and custom converters
~~~

Custom converter không nên phụ thuộc authenticated principal để quyết định record có được đọc không: nó có thể chạy trong batch/background, không có request context và không thay thế query scoping.

### 18.2. Không tự chế encryption

Nếu cần encrypted value object, phải dùng crypto/KMS được kiểm chứng, authenticated encryption, key/nonce lifecycle, rotation và recovery planning.

~~~text
Base64 encoding != encryption
XOR with a hardcoded key != secure encryption
String reversal != encryption
~~~

Spring Data converter không biến một thuật toán yếu thành cơ chế bảo mật.

### 18.3. Log lỗi chuyển đổi một cách an toàn

Nên ghi:

~~~text
collection=invoices
field=total.amount
error=BSON_TYPE_MISMATCH
schemaVersion=unknown
traceId=...
~~~

Không log nguyên bản hóa đơn, email, số tài khoản hoặc BSON có dữ liệu nhạy cảm. Dùng sanitized identifiers/correlation IDs theo chính sách.

### 18.4. Pure conversion và ngoại lệ có thiết kế

Converter gọi mạng hoặc dùng thời điểm ngẫu nhiên có thể khó retry, khó test và sinh kết quả không nhất quán. Nếu mã hóa cần randomness/nonce, đó là ngoại lệ phải được thiết kế rõ và an toàn; không áp dụng side effects tùy tiện vào mọi persistence conversion.

## 19. Kiểm thử custom converter theo nhiều cấp

Vì converter nằm ở ranh giới domain/BSON, kiểm thử cần xác nhận cả **value round-trip** và **stored BSON**. Một unit test qua trực tiếp hai converter chưa chứng minh Spring context thực sự đã đăng ký chúng.

### 19.1. Unit test Money → Document → Money

Ví dụ với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.billing.domain.Money;
import com.example.billing.persistence.MoneyReadConverter;
import com.example.billing.persistence.MoneyWriteConverter;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

public class MoneyConverterTest {

    private final MoneyWriteConverter writer =
            new MoneyWriteConverter();
    private final MoneyReadConverter reader =
            new MoneyReadConverter();

    @Test
    void shouldRoundTripAmountAndCurrency() {
        Money original = Money.of("19.90", "usd");

        Document bson = writer.convert(original);
        Money restored = reader.convert(bson);

        assertEquals("USD", restored.currencyCode());
        assertEquals(0,
                original.amount().compareTo(restored.amount()));
        assertEquals(original, restored);
    }

    @Test
    void shouldStoreAmountAsDecimal128() {
        Document bson = writer.convert(
                Money.of("19.90", "USD"));

        assertInstanceOf(
                Decimal128.class,
                bson.get("amount"));
        assertEquals("USD", bson.getString("currency"));
    }

    @Test
    void shouldRejectUnsupportedBsonType() {
        Document legacy = new Document(
                "amount", "19.90")
                .append("currency", "USD");

        assertThrows(
                IllegalArgumentException.class,
                () -> reader.convert(legacy));
    }

    @Test
    void shouldKeepSmallDecimalExact() {
        Money money = new Money(
                new BigDecimal("0.00000001"), "USD");

        Money restored = reader.convert(writer.convert(money));

        assertEquals(0,
                new BigDecimal("0.00000001")
                        .compareTo(restored.amount()));
    }
}
~~~

Các tests kiểm tra:

- Amount không bị convert qua double.
- Currency được chuẩn hóa.
- BSON type đúng Decimal128.
- Reader strict từ chối legacy String.
- Decimal value round-trip.

**Lưu ý:** scale/equality policy cần được xác nhận riêng theo domain. Một assertion dùng compareTo() kiểm tra numeric equality; assertion Object.equals() có thể quan tâm cả BigDecimal scale.

### 19.2. Negative cases nên có

| Input | Expected behavior |
|---|---|
| Null amount | Domain construction bị từ chối. |
| Null/blank currency | Domain construction bị từ chối. |
| Invalid ISO currency code | Domain construction bị từ chối. |
| BSON amount là String trong strict reader | Conversion error. |
| BSON amount thiếu | Conversion error. |
| BSON currency thiếu | Conversion error. |
| BSON amount không biểu diễn được Decimal128 | Writer không được làm tròn âm thầm. |
| Embedded field total null | Domain/entity null policy được xử lý ở cấp mapping/service. |
| Unknown schemaVersion | Reject hoặc compatibility policy rõ. |

Một input âm hoặc scale khác không tự sai: chúng phụ thuộc invariant nghiệp vụ đã định nghĩa. Tránh test những quy tắc domain chưa tồn tại.

### 19.3. Integration test: MongoTemplate lưu và đọc thật

**@DataMongoTest** tạo slice test của Spring Data MongoDB theo Spring Boot version. Cần cấu hình một MongoDB test instance riêng (ví dụ Testcontainers hoặc service test được kiểm soát).

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.billing.config.MongoConversionConfiguration;
import com.example.billing.domain.Money;
import com.example.billing.persistence.Invoice;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import(MongoConversionConfiguration.class)
public class InvoiceMongoMappingTest {

    @Autowired
    private MongoTemplate template;

    @Test
    void shouldPersistAndLoadMoney() {
        Invoice invoice = new Invoice(
                "INV-TEST-100",
                "tenant-test",
                "C-TEST",
                Money.of("19.90", "USD")
        );

        template.save(invoice);

        Document raw = template.getCollection("invoices")
                .find(new Document("_id", "INV-TEST-100"))
                .first();

        assertNotNull(raw);

        Document total = raw.get("total", Document.class);
        assertNotNull(total);
        assertInstanceOf(
                Decimal128.class,
                total.get("amount"));

        Invoice restored = template.findById(
                "INV-TEST-100", Invoice.class);
        assertNotNull(restored);
        assertEquals(invoice.getTotal(), restored.getTotal());
    }
}
~~~

Trong ví dụ, **raw getCollection()** được dùng có chủ đích để xem BSON đúng như lưu ở database, không qua MappingMongoConverter khi đọc document.

### 19.4. Test context phải dùng đúng registry

Một test có converter classes trên classpath nhưng không import/configure **MongoCustomConversions** có thể không sử dụng converter như ứng dụng production.

Kiểm tra:

- Spring context đã load MongoConversionConfiguration chưa?
- Có MongoTemplate/MongoMappingConverter khác do app tạo thủ công không?
- Có nhiều MongoDB connections/databases và chỉ một connection dùng converter?
- Repository có sử dụng cùng mapping context không?

Nếu test chạy được nhưng stored amount là string thay vì Decimal128, cần điều tra **cấu hình mapping** thay vì chỉ xác nhận MoneyWriteConverter unit test pass.

### 19.5. Test query và index behavior

Integration test nên:

1. Seed invoices có 19.90, 100.00, 120.00 trong USD.
2. Seed một invoice 1.000 trong VND.
3. Query USD amount >= 100.00.
4. Xác nhận chỉ trả các USD invoices hợp lệ.
5. Xem explain với dataset phù hợp để đánh giá index.

Test query theo nested BSON fields sẽ phát hiện lỗi đổi **amount từ Decimal128 thành String** mà unit test domain-only có thể bỏ sót.

### 19.6. Test schema migration

Một integration test migration:

~~~text
Seed old BSON String amount.
Deploy compatibility reader.
Read old amount into Money.
Write back with new converter.
Check raw BSON amount is Decimal128.
Run business query.
Verify amount/currency values were preserved.
~~~

Không chỉ test new writes; production thường chứa lịch sử nhiều năm.

### 19.7. Test precision và boundary values

Chọn nhiều amount:

~~~text
0
0.01
19.90
-1.50 (nếu domain cho phép)
12345678901234567890.1234
0.00000000000000000001
value beyond Decimal128 precision/range
~~~

Expected behavior của out-of-range value phải là lỗi rõ ràng hoặc một policy đã thiết kế, không silent fallback sang double.

### 19.8. Test side effects và thread-safety

Nếu converter có state mutable như:

~~~java
private String lastCurrency;
~~~

nhiều requests đồng thời có thể ảnh hưởng nhau. Một converter dùng chung cần **stateless**, nhất là khi Spring service tải nhiều records song song.

Unit tests có thể chạy concurrent calls trên cùng converter instance để phát hiện mutable shared state, nhưng **không cần thêm state** chỉ để test.

## 20. Hiệu năng khi custom conversion áp dụng cho nhiều documents

Một query:

~~~text
Find 10,000 invoices
   -> map 10,000 BSON documents
   -> instantiate 10,000 Money objects
   -> create BigDecimal objects
~~~

Chi phí converter thường nhỏ so với network/disk cho những truy vấn vừa phải, nhưng ở tốc độ rất cao hoặc mỗi document chứa nhiều value objects, chi phí object allocations và GC có thể đáng kể.

### 20.1. Tránh parse nặng trên mọi record

Không dùng:

~~~text
Every MoneyReadConverter call:
  read configuration from disk
  open network connection
  compile regex and complex parser
  fetch exchange rate
~~~

Các lookup tốn chi phí và business dependencies không nên nằm trong converter. Domain validation nhẹ, BSON type checks và primitive transformations thường phù hợp.

### 20.2. Projection để không materialize dữ liệu không cần

Nếu API chỉ cần invoice ID và status, không cần đọc toàn bộ Money/nested items của hàng triệu records:

~~~javascript
db.invoices.find(
  { tenantId: "tenant-a" },
  { _id: 1, status: 1 }
);
~~~

Trong Spring Data, có thể dùng projection/DTO query phù hợp. Điều này giảm network bytes và object mapping workload. **Không đưa một Money field vào projection rồi bỏ phần currency** nếu DTO/domain vẫn kỳ vọng value object đầy đủ.

### 20.3. Query/filter trước khi materialize

~~~text
MongoDB $match / indexed query
    -> fewer BSON documents over network
    -> fewer Java objects and custom conversions
~~~

Custom converter không thay thế index/filter/sort design. Một full collection scan trả triệu documents về Java rồi lọc trong memory thường kém hơn đẩy predicate phù hợp xuống MongoDB.

### 20.4. Đo riêng serialization overhead

Khi hiệu năng giảm sau thêm converter, phân biệt:

| Thành phần | Cách điều tra |
|---|---|
| Database query time | explain và MongoDB metrics. |
| Network transfer | Bytes returned, latency, routing. |
| Mapping converter CPU | Java profiler/JFR. |
| Object allocations/GC | JFR, allocation/GC metrics. |
| Index/data size | $collStats, $indexStats. |
| Application request latency | Traces/Micrometer. |

Đừng vội tối ưu converter bằng pooling mutable objects khi bottleneck thực là query có COLLSCAN.

### 20.5. Bulk writes và converter

Spring Data bulk operations có mapping behavior phụ thuộc API cụ thể. Một số raw/BSON-oriented operations không nhất thiết đi qua cùng entity conversion pipeline.

Trước khi đưa bulk ingest vào production:

- Kiểm tra stored BSON types của một sample.
- Xác nhận amount/currency không bị đổi representation.
- Đảm bảo các records không bypass domain validation cần thiết.
- Test error handling, retry/idempotency.

### 20.6. Reactive MongoDB

Trong ứng dụng **ReactiveMongoTemplate/ReactiveMongoRepository**, custom conversion vẫn là thao tác mapping dữ liệu, nhưng **không nên block reactive threads** bằng network/filesystem I/O trong converter.

Một converter sync, stateless và không I/O thường phù hợp hơn một converter tự gọi service khác. Nếu conversion đòi hỏi async I/O, hãy tách nó ra business/reactive pipeline ở chỗ hợp lý thay vì biến method convert() thành một operation blocking.

### 20.7. Index footprint của representation

Money lưu dưới embedded Document:

~~~javascript
{ amount: NumberDecimal("19.90"), currency: "USD" }
~~~

có storage footprint khác:

~~~javascript
{ minorUnits: NumberLong("1990"), currency: "USD" }
~~~

và khác:

~~~javascript
{ amount: "19.90 USD" }
~~~

Chọn định dạng vì correctness và query semantics trước, sau đó benchmark thực tế về index bytes, compression và write cost. Đừng đổi representation chỉ vì một document mẫu ít hơn vài bytes nếu nó làm hỏng numeric query.

## 21. Các lỗi thường gặp và cách chẩn đoán

### 21.1. Viết converter nhưng quên đăng ký

Triệu chứng:

~~~text
Unit test MoneyWriteConverter succeeds
MongoRepository.save() stores an unexpected structure
~~~

Nguyên nhân có thể là **MongoCustomConversions chưa được cấu hình vào MappingMongoConverter thực sự đang được dùng**.

Hướng xác định:

1. Kiểm tra configuration class có trong component scan/import không.
2. Xem có nhiều MongoTemplates/clients được tạo thủ công không.
3. Kiểm tra converter pair có được đăng ký vào MongoCustomConversions không.
4. Tạo integration test với raw BSON readback.

### 21.2. Chỉ khai báo @WritingConverter

Nếu writer tạo:

~~~javascript
total: {
  amount: NumberDecimal("19.90"),
  currency: "USD"
}
~~~

nhưng không có reader phù hợp, Spring Data có thể thử default object mapping hoặc gặp lỗi mapping tùy domain type/constructors. Với custom format, nên thiết kế rõ **cả hai chiều**.

### 21.3. Chỉ khai báo @ReadingConverter

Reader nhận Document → Money đúng, nhưng writer mặc định có thể ghi amount theo mapping khác. Khi đó records mới không nhất quán với records cũ.

**Đừng kiểm thử chiều đọc đơn lẻ** rồi coi persistence contract hoàn chỉnh.

### 21.4. Trộn BigDecimal, Decimal128, double và String

MongoDB có nhiều BSON numeric types, nhưng một Money schema phải chỉ rõ kiểu chấp nhận.

~~~text
amount: NumberDecimal("19.90")  -> intended
amount: "19.90"                 -> legacy string
amount: 19.9                    -> floating double representation
amount: NumberLong("1990")      -> maybe minorUnits, not 19.90
~~~

Các giá trị có thể trông gần giống khi in nhưng **semantics khác nhau**. Không tự đọc NumberLong(1990) thành 1990.00 USD khi dữ liệu cũ thực sự định nghĩa 1990 minor units.

### 21.5. Dùng BigDecimal.doubleValue() trong writer

~~~java
// Anti-pattern: loss of decimal precision.
new Document("amount", money.amount().doubleValue());
~~~

Nếu schema yêu cầu Decimal128, dùng **new Decimal128(BigDecimal)** với validation/failure behavior rõ.

### 21.6. Đặt rules về tỷ giá/thuế trong converter

~~~text
On read:
  fetch current FX rate
  convert USD to VND
~~~

Lần đọc hôm nay và tuần sau cho cùng document có thể tạo số tiền khác. Đây là business operation cần **rate/time/source** rõ, không phải persistence conversion.

### 21.7. Register hai converters cho cùng cặp kiểu

~~~text
Money -> Document, implementation A
Money -> Document, implementation B
~~~

Nếu không có cơ chế disambiguation/property scope rõ ràng, kết quả khó bảo đảm và dễ gây xung đột. Dùng một persistence contract canonical hoặc property-specific converter nếu cần.

### 21.8. Converter lấy thông tin từ ThreadLocal request

~~~text
MoneyWriteConverter reads currentTenant from ThreadLocal
~~~

Background job/async/reactive processing có thể không có context tương ứng. Không nhúng tenantId hoặc quyền sở hữu bằng cách đọc request context trong converter; entity/service phải cung cấp đúng metadata đã xác thực.

### 21.9. Quên @ReadingConverter/@WritingConverter

Khi nguồn và đích có thể là native BSON/simple types, Spring Data có thể không xác định đúng hướng. Annotations làm intent rõ và tránh các converter gây tác dụng phụ không mong muốn.

### 21.10. Dùng raw driver rồi mong custom converter tự chạy

~~~java
mongoTemplate.getCollection("invoices")
        .insertOne(rawDocument);
~~~

Ở đây bạn gửi raw BSON Document qua MongoDB driver. **MoneyWriteConverter không tự sửa rawDocument**. Nếu codebase có cả repository và raw driver, cần giao ước rõ về BSON types.

### 21.11. Quên tên field BSON đã được @Field đổi

Nếu entity:

~~~java
@Field(name = "total_value")
private Money total;
~~~

raw query trên MongoDB phải dùng **total_value.amount**, không phải **total.amount**. Spring Data mapped property path có thể hỗ trợ translate khi đi qua QueryMapper, nhưng raw scripts/queries dùng schema thực.

### 21.12. Quên migration khi thay converter

Writer phiên bản mới không sửa records cũ. Production có thể đồng thời có String và Decimal128. Cần kiểm soát rollout, legacy reader và data migration.

### 21.13. Tự coi missing field là 0

Thiếu total.amount có thể là lỗi dữ liệu hoặc một trạng thái business incomplete. Trả 0 không có business rule có thể làm sai doanh thu và kiểm toán.

### 21.14. Bỏ currency khi projection

~~~javascript
db.invoices.find(
  {},
  { "total.amount": 1 }
);
~~~

Nếu kết quả được map vào Invoice/Money đầy đủ, currency thiếu làm reader không thể tạo value object đúng. Hãy dùng DTO/projection có semantics phù hợp thay vì ép một subdocument thiếu fields thành Money.

### 21.15. Dựa vào toString() để lưu domain value

~~~java
money.toString()
~~~

có thể tạo output như **Money[amount=19.90, currencyCode=USD]**, vốn không phải storage schema ổn định. toString phục vụ debug, không phải persistence contract.

### 21.16. Dùng locale formatting khi lưu số

~~~text
"1,234.56"
"1.234,56"
~~~

Đây là những conventions hiển thị khác nhau. BSON amount không nên phụ thuộc locale của máy server. Sử dụng Decimal128 hoặc canonical decimal representation rõ.

### 21.17. Tự thay đổi BigDecimal scale

Nếu converter stripTrailingZeros hoặc setScale theo rounding mode tùy ý, round-trip có thể thay đổi representation; với domain cần exact scale, đó có thể là breaking change.

### 21.18. Không xử lý out-of-range Decimal128

BigDecimal có thể biểu diễn giá trị mà Decimal128 không hỗ trợ. Nếu writer ném exception khi production gặp giá trị này, service cần trả error có kiểm soát và không báo save thành công.

### 21.19. _class và package refactor

Không mặc định Java fully qualified class name là identifier nghiệp vụ bất biến. Xem type aliases hoặc explicit stable codes theo nhu cầu polymorphism.

### 21.20. Converter chậm vì network/IO

Một database read trả 10.000 documents có thể gọi converter 10.000 lần. Network request trong convert() sẽ nhân latency và phá vỡ assumptions về threading. Giữ converter local, rẻ và deterministic.

### 21.21. Test chỉ giá trị dễ

Nếu test chỉ **19.90 USD**, có thể bỏ sót:

- Amount rất lớn/nhỏ.
- Precision boundary.
- Currency code bất thường.
- Field missing/null.
- Data legacy.
- Query sort/range.
- Record với value object ở nested collection/list.

### 21.22. Nhầm converter với JSON serializer

Spring Data converter có thể lưu đúng BSON trong database, nhưng Jackson khi trả REST vẫn serialize Money theo cấu trúc record JSON. Muốn đổi JSON contract, dùng Jackson configuration/DTO mapping riêng.

### 21.23. Thay đổi kiểu index mà không đánh giá query

Nếu đổi amount từ String sang Decimal128, các phép so sánh range có thể khác và old index chứa mixed types. Cần migrate, kiểm tra explain và index behavior; không tự đổi index/hint mù quáng.

### 21.24. Không xem xét backups và rollback

Nếu migration chỉnh hàng triệu invoices, phải có backup/recovery plan và audit. Rollback code không tự undo BSON migration đã commit.

## 22. Bảng quyết định khi thiết kế persistence cho value object

| Câu hỏi | Nếu có | Hướng xem xét |
|---|---|---|
| Java type đã map được tự nhiên? | Có | Ưu tiên default mapping. |
| Chỉ cần BigDecimal → Decimal128 ở một field? | Có | @Field(targetType). |
| Cần format cụ thể cho value object gồm nhiều fields? | Có | Custom converters hai chiều. |
| Chỉ một property cần format khác các property cùng type? | Có | PropertyValueConverter/version-specific support. |
| Chỉ HTTP API cần output khác? | Có | DTO/Jackson serializer. |
| Dữ liệu cũ có format khác? | Có | Compatibility reader + migration. |
| Value cần conversion theo tỷ giá/secret/time? | Có | Business/crypto workflow tách biệt, không converter thuần. |
| Cần sort/filter numeric trên MongoDB? | Có | Chọn BSON numeric type phù hợp. |
| Cần chuẩn hóa code enum ổn định? | Có | Domain code converter hoặc mapping rõ. |
| Cần polymorphism? | Có | Discriminator/version schema có thể migrate. |
| Chỉ cần đổi property name? | Có | @Field(name=...). |
| Cần đổi schema cả collection? | Có | Data migration và release coordination. |

### 22.1. Một workflow thiết kế converter

~~~text
Identify business invariant
          |
          v
Define Java domain type
          |
          v
Choose BSON contract + example document
          |
          v
Check built-in mapping / @Field support
          |
          v
If needed, implement WritingConverter
          |
          v
Implement ReadingConverter + error policy
          |
          v
Register in MongoCustomConversions
          |
          v
Unit round-trip + integration raw BSON
          |
          v
Query/index compatibility test
          |
          v
Migration/rollout plan if stored data exists
          |
          v
Monitor conversion failures and performance
~~~

### 22.2. Những quyết định phải được ghi thành tài liệu

Với mỗi converter, nên ghi:

- Domain type và cấu trúc dữ liệu.
- BSON storage type/fields và ví dụ.
- Null/missing field policy.
- Numeric precision/rounding policy.
- Schema version/backward compatibility.
- Hướng reading/writing, registry scope.
- Index/query semantics.
- Migration và rollback strategy.
- Error handling/observability.
- Owner của data contract.

Một converter ít dòng nhưng không có hợp đồng dữ liệu có thể gây lỗi kéo dài khi nhiều microservices cùng đọc một collection.

## 23. Lab: thực hành trên MongoDB thử nghiệm

Chỉ thực hành trên một **database test riêng**. Các bước nhằm giúp người học quan sát schema, không yêu cầu kết nối production.

### 23.1. Chuẩn bị

1. Tạo Spring Boot project có dependency **spring-boot-starter-data-mongodb** phù hợp version.
2. Sử dụng Java 17+ cho ví dụ Money record.
3. Kết nối một MongoDB test instance đã được cấp quyền.
4. Tạo các class Money, MoneyWriteConverter và MoneyReadConverter.
5. Tạo bean MongoCustomConversions.
6. Tạo Invoice entity và InvoiceRepository.

Không hardcode production credentials. Dùng application configuration/secret injection phù hợp.

### 23.2. Ghi một invoice

~~~java
repository.save(new Invoice(
        "INV-LAB-001",
        "tenant-lab",
        "customer-lab",
        Money.of("125.75", "USD")
));
~~~

### 23.3. Kiểm tra BSON thô trong mongosh

~~~javascript
use billing_lab

db.invoices.findOne({ _id: "INV-LAB-001" });
~~~

Kỳ vọng trong **total**:

~~~javascript
{
  amount: NumberDecimal("125.75"),
  currency: "USD"
}
~~~

Entity mapping có thể lưu thêm _class tùy configuration. Nếu amount hiện là String, kiểm tra registry, domain converter và cấu hình MongoTemplate.

### 23.4. Đọc lại domain object

~~~java
Invoice invoice = repository
        .findById("INV-LAB-001")
        .orElseThrow();

System.out.println(invoice.getTotal().amount());
System.out.println(invoice.getTotal().currencyCode());
~~~

Kỳ vọng: amount tương đương 125.75 và currency là USD.

### 23.5. Thêm một amount để query

~~~java
repository.save(new Invoice(
        "INV-LAB-002",
        "tenant-lab",
        "customer-lab",
        Money.of("300.00", "USD")
));
~~~

Chạy:

~~~javascript
db.invoices.find({
  tenantId: "tenant-lab",
  "total.currency": "USD",
  "total.amount": { $gte: NumberDecimal("200.00") }
});
~~~

Kỳ vọng tìm INV-LAB-002, không phải INV-LAB-001.

### 23.6. Thử dữ liệu cũ ở test database

~~~javascript
db.invoices.insertOne({
  _id: "INV-LAB-LEGACY",
  tenantId: "tenant-lab",
  customerId: "customer-lab",
  total: {
    amount: "19.90",
    currency: "USD"
  }
});
~~~

Reader strict trong bài sẽ từ chối String amount. Đây là cơ sở để quan sát **schema migration problem** và thử compatibility reader trong môi trường riêng.

### 23.7. Quan sát integration test

Lưu ý phân biệt:

~~~text
repository.findById(...)
  -> BSON converted to Invoice/Money

mongoTemplate.getCollection("invoices").find(...)
  -> raw BSON Document via MongoDB driver
~~~

Hai cách đọc trả những kiểu Java khác nhau vì đi qua những tầng mapping khác nhau.

### 23.8. Kiểm tra index

~~~javascript
db.invoices.createIndex({
  tenantId: 1,
  "total.currency": 1,
  "total.amount": 1
});

db.invoices.find({
  tenantId: "tenant-lab",
  "total.currency": "USD",
  "total.amount": { $gte: NumberDecimal("100.00") }
}).explain("executionStats");
~~~

Với vài documents trong lab, COLLSCAN vẫn có thể được planner chọn. **Không lấy execution time nhỏ trên lab làm benchmark production**.

### 23.9. Cleanup

Khi đã hoàn tất, cleanup **chỉ database test được sở hữu** theo quy trình môi trường. Không dùng dropDatabase trên production hay một database chia sẻ của người khác.

## 24. Bài tập thực hành

### Bài 1 — Vẽ lại conversion pipeline

Vẽ luồng **Invoice → MongoRepository → MappingMongoConverter → MoneyWriteConverter → Document → MongoDB**. Vẽ chiều đọc tương ứng. Giải thích ở bước nào application domain type trở thành BSON.

### Bài 2 — Thiết kế value object

Viết một record **Money(BigDecimal amount, String currencyCode)**. Chuẩn hóa currencyCode và từ chối null. Thảo luận vì sao không nên dùng double.

### Bài 3 — BSON contract

Định nghĩa chính xác BSON document cho Money 19.90 USD. Ghi rõ kiểu amount là **Decimal128**, không phải String/double, và currency là mã ISO.

### Bài 4 — WritingConverter

Viết **Converter<Money, Document>** với @WritingConverter. Chuyển amount qua Decimal128 và currencyCode qua String.

### Bài 5 — ReadingConverter

Viết **Converter<Document, Money>** với @ReadingConverter. Reader phải từ chối khi amount không phải Decimal128 hoặc currency không phải String.

### Bài 6 — MongoCustomConversions

Tạo @Configuration bean đăng ký cả hai converters Money. Giải thích vì sao chỉ đặt annotation lên class chưa bảo đảm registry đã nhận converter.

### Bài 7 — Invoice entity

Viết Invoice entity có **id, tenantId, customerId, Money total** và sử dụng MongoRepository. Giải thích trường total được lưu như thế nào.

### Bài 8 — Quan sát BSON thô

Sau repository.save(invoice), dùng raw driver collection hoặc mongosh để xem **total.amount**. Làm thế nào chứng minh database thực sự lưu BSON Decimal128?

### Bài 9 — @Field(targetType)

Một entity chỉ có **BigDecimal amount** và muốn lưu Decimal128. Viết giải pháp dùng **@Field(targetType = FieldType.DECIMAL128)** và giải thích khi nào không cần custom converter.

### Bài 10 — Query numeric

Viết MongoTemplate Query lấy invoices thuộc tenant-a, currency USD và amount >= 100.00. Giải thích lý do predicate phải có currency.

### Bài 11 — Compound index

Thiết kế index hỗ trợ query ở Bài 10. Chạy explain trên dữ liệu đại diện và chỉ ra metrics keys/docs examined cần quan sát.

### Bài 12 — Aggregation numeric

Viết aggregation tính tổng amount của invoices USD theo tenant. Vì sao không được cộng USD, EUR và VND thành một tổng không quy đổi?

### Bài 13 — Legacy string

Một số documents cũ có **total.amount: "19.90"**. Reader strict trong bài sẽ gặp gì? Đề xuất migration từng giai đoạn tránh breaking rollout.

### Bài 14 — Compatibility reader

Viết reader chấp nhận **Decimal128** và một **decimal string** hợp lệ, từ chối double và unknown types. Thử đầu vào malformed.

### Bài 15 — Migration conditional update

Thiết kế updateOne chỉ đổi String amount sang Decimal128 nếu document còn chứa giá trị cũ. Vì sao predicate cũ giúp tránh concurrent overwrite?

### Bài 16 — Versioned schema

Thêm **schemaVersion: 2** vào total. Cần thay đổi gì trong writer, reader, legacy migration và query dùng embedded document equality?

### Bài 17 — Enum status code

Viết enum **PaymentState** có stable codes: NEW="N", PAID="P", FAILED="F". Xây reading/writing converters từ enum sang BSON String.

### Bài 18 — Unknown enum

Reader nhận code **"Z"** không có trong enum. So sánh hai chiến lược: fail-fast và UNKNOWN. Khi nào một chiến lược có thể che business error?

### Bài 19 — EmailAddress

Xây một domain type EmailAddress với validation phù hợp và converters EmailAddress ↔ String. Vì sao cần @ReadingConverter để làm rõ hướng String → EmailAddress?

### Bài 20 — Hai properties cùng Java type

Hai fields Money cần hai storage formats khác nhau. Bạn sẽ dùng một converter global, property-specific converter hay tách domain type? Giải thích quyết định theo ý nghĩa nghiệp vụ.

### Bài 21 — Round-trip test

Viết JUnit test:

~~~text
Money("19.90","USD")
    -> write()
    -> Document with Decimal128
    -> read()
    -> equal Money
~~~

Kiểm tra amount, currency và BSON type, không chỉ string output.

### Bài 22 — Null và missing fields

Đánh giá ba documents:

~~~javascript
{ _id: "A" }
{ _id: "B", total: null }
{ _id: "C", total: { currency: "USD" } }
~~~

Converter được gọi trong trường hợp nào? Domain nên có policy gì khi total bắt buộc?

### Bài 23 — Decimal128 overflow

BigDecimal có precision/range lớn hơn Decimal128. Khi writer không biểu diễn được, bạn sẽ làm gì? Vì sao không được tự động chuyển qua double?

### Bài 24 — Mixed BSON query

Trong collection có amount là String và Decimal128. Điều gì xảy ra khi query numeric range? Mô tả kiểm thử giúp phát hiện lỗi.

### Bài 25 — JSON khác BSON

API muốn trả:

~~~json
{"total":"19.90 USD"}
~~~

nhưng MongoDB muốn lưu embedded document. Nên dùng converter MongoDB hay DTO/Jackson serializer cho JSON output? Giải thích.

### Bài 26 — Java String _id

Với @Id String, trường hợp chuỗi có hình dạng ObjectId hex và chuỗi "INV-100" có thể khác nhau ra sao? Khi nào cần @MongoId(FieldType.STRING)?

### Bài 27 — Polymorphic payment method

Thiết kế BSON format cho CardPayment và BankTransfer có **kind** và **schemaVersion** ổn định. Đề xuất reader xử lý unknown kind.

### Bài 28 — LocalDateTime và timezone

Nếu converter dùng system default timezone để ghi LocalDateTime thành BSON Date, một deploy sang region khác có thể xảy ra lỗi gì? Đề xuất representation có zone/UTC rõ.

### Bài 29 — UUID legacy

Một database lưu UUID theo binary representation cũ. Vì sao tự viết converter UUID ↔ byte[] không kiểm tra subtype/representation có thể làm lookup sai?

### Bài 30 — Raw driver bypass

Một batch job dùng **mongoTemplate.getCollection().insertOne(rawDocument)**. Có cần kỳ vọng MoneyWriteConverter tự chạy không? Thiết kế convention bảo đảm cùng BSON contract cho batch và repository.

### Bài 31 — Partial projection

Một projection chỉ lấy **total.amount** rồi map thành Invoice với Money. Điều gì có thể xảy ra khi thiếu currency? Đề xuất DTO hoặc projection đúng semantics.

### Bài 32 — Property rename

Entity đổi **total** thành **@Field("total_value")**. Viết query MongoDB tương ứng và phân biệt raw BSON paths với Java property paths.

### Bài 33 — Conversion performance

Find trả 500.000 invoices. Những chi phí nào thuộc MongoDB query, network, Java mapping, BigDecimal allocation và GC? Thiết kế cách đo từng lớp.

### Bài 34 — Reactive conversion

Một reactive service đặt REST call tra tỷ giá trong Converter.convert(). Vì sao đây là thiết kế gây blocking và khó retry? Đề xuất tách business workflow.

### Bài 35 — Security boundaries

Money converter chuẩn hóa currency. Có đủ để bảo đảm tenant A không đọc hóa đơn tenant B không? Phải thêm những controls nào ở service/query/API?

### Bài 36 — Integration test

Viết một Spring Data MongoDB integration test lưu Invoice bằng MongoTemplate, đọc raw Document qua getCollection và xác nhận total.amount là Decimal128; sau đó findById để round-trip.

### Bài 37 — Rollback

Phiên bản ứng dụng mới ghi Decimal128, phiên bản cũ chỉ đọc String. Trình bày thứ tự deploy và rollback plan để không làm các instances cũ fail.

### Bài 38 — Converter registration conflict

Hai bean MongoCustomConversions khác nhau được tạo bởi các configuration modules. Làm sao đảm bảo tất cả converters cần thiết được đăng ký đúng MappingMongoConverter?

### Bài 39 — Format thay đổi và index

Một service đổi amount từ string sang Decimal128. Ngoài unit test converter, cần đánh giá những queries/indexes/aggregations nào?

### Bài 40 — Viết persistence design note

Soạn bản thiết kế lưu một business value object tùy chọn (Money, PhoneNumber, BookingPeriod), bao gồm:

~~~text
Domain invariants and Java type
Raw BSON format with types
Reading/Writing conversion
Spring registration scope
Query and index requirements
Null/invalid/legacy handling
Migration and rollback plan
Unit + integration tests
Performance and security concerns
~~~

Một thiết kế tốt phải chứng minh **dữ liệu đọc/ghi hai chiều đúng, truy vấn theo BSON có ý nghĩa và không phá dữ liệu đã tồn tại**.

## 25. Câu hỏi ôn tập

1. **MappingMongoConverter** giữ vai trò gì giữa MongoRepository và MongoDB Driver?
2. **MongoCustomConversions** là gì?
3. Khi nào default object mapping đã đủ và không cần custom converter?
4. Phân biệt writing converter và reading converter.
5. Vì sao **@WritingConverter** và **@ReadingConverter** quan trọng khi converter liên quan native/simple types?
6. **org.bson.Document** khác entity **@Document** ở chỗ nào?
7. Vì sao Money thường dùng BigDecimal thay vì double?
8. BSON Decimal128 có giới hạn precision/exponent không?
9. Domain Money nên chứa currencyCode vì sao?
10. Decimal128+currency có ưu/nhược gì so với minorUnits+currency?
11. Vì sao không nên dùng String "19.90 USD" nếu cần numeric range queries?
12. MoneyWriteConverter của bài chuyển thành BSON fields nào?
13. MoneyReadConverter làm gì nếu amount là String trong strict mode?
14. Converter được đăng ký vào MongoTemplate/MongoRepository qua cơ chế nào?
15. Chỉ thêm @Component vào converter có bảo đảm MongoCustomConversions tự nhận nó không?
16. Điều gì xảy ra nếu app có một MongoTemplate tùy chỉnh không dùng registry đã cấu hình?
17. Sự khác biệt giữa **@Field(targetType=DECIMAL128)** và Money custom converter là gì?
18. Khi nào dùng property-specific conversion thay vì global conversion?
19. Vì sao không đăng ký nhiều converters cùng cặp Money → Document không có quy tắc chọn?
20. Khi @Field đổi tên total thành total_value, raw BSON query path là gì?
21. Vì sao Money converter không tự đổi JSON serialization của REST API?
22. Tại sao query trên total.amount cần quan tâm currency?
23. Vì sao embedded BSON equality và predicates trên nested fields có semantics khác nhau?
24. MongoDB aggregation **$sum** dùng BSON numeric amount, không dùng Java Money trực tiếp, có đúng không?
25. Raw MongoDB Java Driver insertOne có tự chạy Spring converter không?
26. Spring Data Update.set với domain value cần kiểm chứng điều gì?
27. Domain constructor nên validate các bất biến nào?
28. Converter có nên tự lấy tỷ giá và thời gian hiện tại khi ghi tiền không?
29. Vì sao nên giữ converter stateless và thread-safe?
30. Null total, missing total và malformed total khác nhau ra sao?
31. Reader có nên tự thay missing amount bằng zero không?
32. Vì sao data migration cần đi cùng thay đổi writer/reader?
33. Expand → migrate → contract giải quyết rủi ro gì?
34. Mixed BSON String/Decimal128 ảnh hưởng query/index thế nào?
35. Khi rollout writer mới, vì sao old application instances có thể không đọc được dữ liệu mới?
36. schemaVersion field giúp quản lý conversion thế nào?
37. Một type discriminator ổn định khác Java _class name ở điểm nào?
38. Tại sao local date-time cần timezone policy khi lưu BSON Date?
39. MongoDB BSON Date có lưu nanoseconds chính xác như Instant không?
40. Vì sao UUID binary representation cần được xác định rõ khi migrate?
41. Integration test cần kiểm tra raw BSON type như thế nào?
42. Unit test converter pass có chứng minh Spring context đăng ký converter đúng không?
43. Vì sao phải test Decimal128 boundary, malformed fields và legacy formats?
44. Một projection thiếu currency có thể khiến reader Money thất bại ra sao?
45. Converter có phải nơi tốt để kiểm soát tenant authorization không?
46. Reactive converter có nên gọi blocking REST service không?
47. Những metrics nào giúp phân biệt DB query cost và Java conversion cost?
48. Khi đổi Money representation, vì sao cần xem index/storage overhead?
49. Backup và rollback schema cần xem xét khi nào?
50. Một persistence contract đủ tin cậy cần những phần nào ngoài code converter?

## 26. Checklist triển khai custom converter trong dự án

### 26.1. Thiết kế domain

- [ ] Domain type có ý nghĩa nghiệp vụ riêng, không chỉ là wrapper không cần thiết.
- [ ] Invariants được mô tả và validate rõ.
- [ ] Numeric precision, scale và currency policy xác định trước.
- [ ] Domain type không phụ thuộc BSON/driver nếu không có lý do chính đáng.
- [ ] Immutable values không bị chỉnh sửa ngầm trong converter.

### 26.2. Thiết kế storage schema

- [ ] Có ví dụ BSON document và **kiểu dữ liệu** của từng field.
- [ ] Có naming convention và versioning policy.
- [ ] Có quyết định rõ cho null/missing/malformed fields.
- [ ] Có query/sort/index requirements dựa trên BSON type thật.
- [ ] Không dùng String thay numeric nếu cần arithmetic/range query.
- [ ] Đã xem built-in mapping hoặc @Field(targetType) có đủ không.

### 26.3. Triển khai converter

- [ ] WritingConverter chuyển domain thành đúng store type.
- [ ] ReadingConverter tạo domain đúng và từ chối unknown types theo policy.
- [ ] Không silent rounding/lossy conversions.
- [ ] Không I/O/network/FX calculation trong convert().
- [ ] Không mutable shared state hoặc request context dependency.
- [ ] Converter direction annotations được dùng khi cần.
- [ ] Registration scope đúng, không có converter trùng cạnh tranh.

### 26.4. Cấu hình Spring

- [ ] MongoCustomConversions được tạo/đăng ký đúng.
- [ ] MappingMongoConverter thực sự dùng registry đó.
- [ ] MongoTemplate và MongoRepository dùng mapping context mong muốn.
- [ ] Có nhiều connections/templates thì từng template đã được kiểm tra.
- [ ] Configuration phù hợp Spring Boot/Spring Data version.

### 26.5. Kiểm thử

- [ ] Unit round-trip và BSON type test.
- [ ] Null/missing/malformed/legacy negative tests.
- [ ] BigDecimal boundary và precision tests.
- [ ] Integration test lưu/đọc qua MongoTemplate hoặc repository.
- [ ] Raw BSON readback xác nhận stored representation.
- [ ] Query/index/aggregation tests theo BSON semantics.
- [ ] Projection và nested value tests khi có.
- [ ] Test với data cũ và multiple application versions khi migration.

### 26.6. Triển khai production

- [ ] Đã khảo sát stored data types hiện hữu.
- [ ] Có release ordering và backward-compatible reader.
- [ ] Có migration idempotent, có thể theo dõi tiến độ.
- [ ] Backup/recovery và rollback plan phù hợp.
- [ ] Những consumers raw BSON đã được thông báo.
- [ ] Logging không lộ dữ liệu nhạy cảm.
- [ ] Conversion failures/latency được giám sát.
- [ ] Index/storage/write impact đã được đánh giá.

## 27. Tổng kết

Custom converter là một công cụ quan trọng của Spring Data MongoDB khi hệ thống có **business value objects** cần một định dạng persistence rõ ràng, khác hoặc chặt chẽ hơn mapping mặc định.

### 27.1. Ba lớp trách nhiệm

~~~text
Domain Money
  -> preserves business meaning:
     amount, currency, invariants

MoneyWriteConverter / MoneyReadConverter
  -> preserves storage contract:
     Decimal128, String, field structure

MongoRepository / MongoTemplate + MappingMongoConverter
  -> integrates persistence lifecycle:
     save, read, query mapping
~~~

Không lẫn lộn:

- Business conversion như FX/thuế với persistence conversion.
- REST/JSON serialization với BSON mapping.
- Object conversion với data migration.
- Numeric storage format với cách hiển thị tiền tệ ở UI.
- Field-level serialization với authorization.

### 27.2. Một sơ đồ triển khai hoàn chỉnh

~~~text
              Design domain value object
                        |
                        v
                  Define BSON schema
                        |
              +---------+----------+
              |                    |
              v                    v
       Default/@Field enough?   Custom format needed?
              |                    |
              v                    v
      Use simple mapping     Write/Read converters
              |                    |
              +---------+----------+
                        |
                        v
               MongoCustomConversions
                        |
                        v
               Spring Data MongoDB
                        |
                        v
          Unit + integration + raw BSON tests
                        |
                        v
        Query/index and backward compatibility
                        |
                        v
           Versioned rollout/migration if needed
                        |
                        v
               Production monitoring
~~~

### 27.3. Những nguyên tắc cần nhớ

1. **Tự động mapping trước, custom converter khi có yêu cầu cụ thể.**
2. **Định nghĩa BSON contract trước khi viết converter**: tên field, store type, schema version và null handling.
3. **Reading và writing là hai chiều riêng**; không mặc định một chiều sẽ tự suy ra chiều còn lại.
4. **Đăng ký rõ qua MongoCustomConversions** và kiểm tra MongoTemplate/MongoRepository thật sự dùng nó.
5. **BigDecimal → Decimal128** giữ numeric semantics tốt hơn double/string trong domain tiền tệ, với giới hạn precision cần kiểm soát.
6. **Không tự quy đổi tiền tệ hoặc làm tròn trong converter** khi domain chưa quy định.
7. **Query và index làm việc trên BSON thực**, không chỉ kiểu Java.
8. **@Field(targetType)** có thể đủ cho trường hợp chỉ muốn một field BigDecimal lưu Decimal128.
9. **Global converter có phạm vi rộng**; nếu chỉ một field cần format riêng, xem property-specific conversion hoặc tách domain type.
10. **Dữ liệu cũ không tự migrate** khi code đổi; cần expand → migrate → contract và kế hoạch rollback.
11. **Xác nhận raw stored BSON trong integration tests**, không chỉ unit test converter.
12. **Giữ converter stateless, predictable và không blocking I/O**, nhất là trong ứng dụng reactive hoặc có throughput cao.
13. **Không dựa trên _class/package names làm business schema nếu cần ổn định lâu dài**.
14. **Các phép đo performance phải tách database, network và Java object mapping**.
15. **An toàn dữ liệu và tenant authorization nằm ngoài converter**, cần được bảo vệ bởi service/query/database policy.

### Tài liệu chính thức để tra cứu theo phiên bản

- [Spring Data MongoDB — Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html) — cách đăng ký converter và các kiểu chuyển đổi.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html) — object mapping, metadata, constructors và type hints.
- [Spring Data MongoDB — Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping.html) — tổng quan mapping support.
- [Spring Data Commons — Custom Conversions](https://docs.spring.io/spring-data/commons/reference/custom-conversions.html) — hướng chuyển đổi và registry.
- [Spring Data MongoDB — Property Converters](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/property-converters.html) — conversion ở property scope khi version hỗ trợ.
- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — Decimal128, String, Date, Binary và những kiểu BSON khác.
- [MongoDB Decimal128](https://www.mongodb.com/docs/manual/reference/bson-types/#decimal128-bson-data-type) — các giới hạn/đặc tính của decimal.
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/) — lựa chọn BSON field paths/indexes.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — raw driver APIs và BSON mapping.
- [Spring Boot Data Access](https://docs.spring.io/spring-boot/reference/data/nosql.html) — auto-configuration và MongoDB integration.

**Kết luận:** Custom converter chỉ tốt khi nó biến một **domain value rõ nghĩa** thành một **BSON contract rõ ràng, ổn định và kiểm thử được**. Việc viết vài dòng Converter<Money, Document> mới là bước khởi đầu; độ tin cậy lâu dài nằm ở registration đúng, dữ liệu Decimal128 chính xác, query/index tương thích, khả năng đọc legacy records và quy trình migration có kiểm soát.









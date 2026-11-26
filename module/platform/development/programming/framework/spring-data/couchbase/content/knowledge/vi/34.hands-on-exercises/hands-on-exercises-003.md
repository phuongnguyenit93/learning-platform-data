# Ánh xạ tài liệu lồng nhau và bộ chuyển đổi tiền tệ hoặc thời gian trong Spring Data Couchbase

> **Chương:** Bài thực hành  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase bằng Spring Data với document mapping, repository, `CouchbaseTemplate` và SQL++; áp dụng bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để kiểm soát hiệu năng, tính nhất quán và khả năng vận hành.

## 1. Mục tiêu và kết quả đầu ra

Bài lab xây dựng **dịch vụ đặt hàng** có một document gốc chứa **khách hàng tại thời điểm mua**, **địa chỉ giao hàng**, **danh sách dòng hàng**, **giá tiền**, **tổng tiền** và **thời điểm tạo đơn**. Trọng tâm là cách Spring Data Couchbase ánh xạ **cây đối tượng Java** sang JSON lồng nhau, đồng thời sử dụng **custom converters** khi kiểu Java và biểu diễn lưu trữ khác nhau.

Hoàn thành bài, bạn sẽ có thể:

1. Phân biệt root document với embedded object, nested array và liên kết tham chiếu bằng ID.
2. Thiết kế aggregate `PurchaseOrderDocument` chứa `CustomerSnapshot`, `ShippingAddress` và `List<OrderLine>`.
3. Ánh xạ `@Id`, `@Version`, `@Document`, `@Scope`, `@Collection` và `@Field` đúng cấp.
4. Thiết kế value object `Money` với `BigDecimal`, `Currency` và quy tắc làm tròn **không mất dữ liệu**.
5. Xây dựng hai chiều `@WritingConverter` và `@ReadingConverter` cho `Money ↔ String`.
6. Cân nhắc custom conversion `OffsetDateTime ↔ String` theo chính sách **UTC** và ISO-8601.
7. Đăng ký các converter trong `CouchbaseCustomConversions` và kiểm tra round-trip khi đọc/ghi.
8. Tạo đơn, đọc lại theo ID, cập nhật với CAS, so JSON stored và Java object.
9. Tìm theo trường nested và array bằng SQL++, hiểu điều kiện về GSI và scan consistency.
10. Viết unit test, integration test, migration test, phân loại lỗi converter, currency/time-zone.
11. Nhận biết giới hạn của embedded snapshots, thay đổi schema, precision, TTL và business invariants.
12. Chuyển bài thực hành thành checklist nghiệm thu an toàn trước production.

### 1.1. Những gì sẽ xuất hiện trong Couchbase

~~~json
{
  "order_no": "PO-20261125-001",
  "status": "CREATED",
  "customer": {
    "customer_code": "CUS001",
    "display_name": "Nguyen Van A"
  },
  "shipping_address": {
    "city": "Da Nang",
    "country_code": "VN",
    "address_line": "12 Example Street"
  },
  "items": [
    {
      "line_no": 1,
      "sku": "BOOK001",
      "quantity": 2,
      "unit_price": "USD|12.30"
    },
    {
      "line_no": 2,
      "sku": "PEN001",
      "quantity": 1,
      "unit_price": "USD|1.40"
    }
  ],
  "total": "USD|26.00",
  "placed_at": "2026-11-25T03:00:00Z",
  "placed_at_epoch_ms": 1795575600000
}
~~~

Document ID được lưu ở Couchbase metadata, ví dụ `po::LAB1::PO-20261125-001`. Spring Data có thể thêm discriminator `_class` và các trường hệ thống tùy cấu hình; JSON trên là **biểu diễn nghiệp vụ mục tiêu**, không phải dump byte-for-byte đã xác nhận từ một cluster đang chạy.

Giá `unit_price` và `total` được converter thành **chuỗi canonical**. `placed_at` lưu thời điểm tuyệt đối theo UTC; `placed_at_epoch_ms` là trường số phục vụ lọc/sắp xếp thời gian có chính sách rõ. Vì tiền đã lưu dạng chuỗi, không dùng SQL++ `SUM(total)` trực tiếp; phần sau phân tích khi nào nên đổi schema.

### 1.2. Phạm vi cố ý giới hạn

- Dùng **bucket riêng cho lab**, không chạy vào production.
- Không lấy giá sản phẩm hoặc tỷ giá từ request người dùng một cách thiếu kiểm chứng.
- Một order là một document/aggregate: sửa nhiều embedded lines cùng một lần replace root.
- Chỉ tính tổng các dòng **cùng currency**; không tự quy đổi USD và VND.
- Không làm payment, inventory reservation hoặc event publishing thật trong bài này.
- Không khẳng định snippets đã được build: cần kiểm tra chính xác Spring Boot, Spring Data Couchbase, Java SDK và Couchbase Server version trong dự án.
- Thực hành với Java 21 hoặc JDK đáp ứng Spring Boot version được chọn.

## 2. Tài liệu lồng nhau và aggregate boundary

Trong Couchbase, document JSON có thể chứa objects, arrays, numbers, strings và booleans. Spring Data Couchbase mapping biến nested POJOs thành nested JSON, không tự tạo một collection mới cho mỗi lớp.

~~~mermaid
flowchart TB
    Root["PurchaseOrderDocument<br/>@Document / @Id / @Version"]
    Customer["CustomerSnapshot<br/>Embedded object"]
    Address["ShippingAddress<br/>Embedded object"]
    Items["List<OrderLine><br/>JSON array"]
    L1["OrderLine #1<br/>sku, quantity, Money"]
    L2["OrderLine #2<br/>sku, quantity, Money"]
    Total["Money total<br/>Custom conversion"]
    Time["OffsetDateTime placedAt<br/>UTC conversion"]
    Root --> Customer
    Root --> Address
    Root --> Items
    Root --> Total
    Root --> Time
    Items --> L1
    Items --> L2
~~~

Với một document root:

- `@Id` áp dụng cho **root key**, không tự cấp Couchbase ID cho `OrderLine`.
- `@Version` bảo vệ CAS của **toàn root document**, không cấp CAS độc lập từng dòng.
- Nested objects được lưu **cùng document**; một KV replace root có tính atomic đối với document đó.
- Update một phần dữ liệu có thể làm bằng **sub-document operations** khi phù hợp, nhưng bài đầu tiên dùng mapping root để hiểu converter và CAS.
- Nếu order có vài chục lines, embed thường hợp lý. Nếu có hàng trăm nghìn lines, tài liệu phình lớn, hot-document và contention có thể khiến thiết kế không phù hợp.

### 2.1. Khi nào snapshot thay vì tham chiếu?

`CustomerSnapshot` lưu tên/mã khách **tại lúc tạo đơn**. Nếu khách đổi tên sau một tháng, order cũ vẫn thể hiện thông tin đã dùng trong giao dịch.

Nếu muốn mỗi lần hiển thị phải lấy **hồ sơ khách hàng hiện tại**, có thể giữ `customerId` tham chiếu đến collection khách hàng; việc cập nhật nhiều documents không có join tự động kiểu ORM quan hệ. Có thể dùng KV multi-get hoặc SQL++ JOIN tùy use case/index, nhưng đó là lựa chọn thiết kế khác.

| Thiết kế | Ưu điểm | Đánh đổi |
|---|---|---|
| Embedded snapshot | Đọc order theo ID lấy đủ thông tin một lần; trạng thái lịch sử ổn định | Dữ liệu lặp, thay đổi hồ sơ không tự cập nhật order cũ |
| ID reference | Dữ liệu hồ sơ tập trung | Nhiều reads/joins; phải xử lý liên kết hỏng |
| Kết hợp snapshot + ID | Có lịch sử và biết entity nguồn | Cần quy tắc khi nguồn bị xóa/đổi |

### 2.2. Giới hạn document size và hot key

Couchbase có giới hạn kích thước document và ràng buộc hiệu năng; không nhúng lịch sử vô hạn vào một document. Khi nhiều writers cùng sửa các dòng của một order, cả root dùng chung CAS, nên tần suất conflict tăng. Chọn ranh giới aggregate theo **nhu cầu đọc/ghi nguyên tử** và khối lượng thực tế, không chỉ vì JSON hỗ trợ lồng nhau.

## 3. Sơ đồ luồng chuyển đổi Java ↔ JSON

~~~mermaid
flowchart LR
    HTTP["POST /orders"]
    Service["OrderService<br/>Validate/tính tiền"]
    Mapping["Spring Data<br/>MappingCouchbaseConverter"]
    Converter["CustomConversions<br/>Money / OffsetDateTime"]
    KV["Couchbase Data Service<br/>JSON document"]
    HTTP --> Service --> Mapping
    Mapping -->|"Money ↔ String"| Converter
    Converter --> Mapping
    Mapping --> KV
    KV -->|"Get theo @Id"| Mapping
    Mapping --> Service
~~~

Hai hành vi cần phân biệt:

1. **Object mapping mặc định:** `CustomerSnapshot`, `ShippingAddress`, `OrderLine` thành JSON object/array tương ứng.
2. **Custom conversion:** trường kiểu `Money` trở thành một **scalar string**, không được mapper tự ghi thành object `{currency, amount}`.

Nếu register converter sai hoặc quên reading converter, có thể ghi được nhưng đọc lại bị lỗi. Vì vậy test **round-trip với dữ liệu thật trong lab** là acceptance criterion bắt buộc, không chỉ compile.

## 4. Chuẩn bị môi trường Spring Boot và Couchbase

### 4.1. Project

Qua Spring Initializr, chọn:

- Spring Web.
- Spring Data Couchbase.
- Jakarta Bean Validation.
- Spring Boot Starter Test.

Ví dụ dependencies trong `pom.xml` do Initializr tạo (giữ nguyên parent/BOM của phiên bản Spring Boot đã chọn):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-couchbase</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là **fragment**, không phải POM build được độc lập. Chọn đúng Spring Boot BOM để tránh ép phiên bản Spring Data/SDK không tương thích.

### 4.2. Cấu trúc source đề xuất

~~~text
src/main/java/com/example/po/
  PurchaseOrderApplication.java
  Money.java
  MoneyToStringConverter.java
  StringToMoneyConverter.java
  OffsetDateTimeToStringConverter.java
  StringToOffsetDateTimeConverter.java
  CouchbaseMappingConfiguration.java
  CustomerSnapshot.java
  ShippingAddress.java
  OrderLine.java
  PurchaseOrderDocument.java
  PurchaseOrderRepository.java
  CreateOrderRequest.java
  PurchaseOrderResponse.java
  PurchaseOrderService.java
  PurchaseOrderController.java
  PurchaseOrderExceptionHandler.java
src/main/resources/
  application.yml
src/test/java/com/example/po/
  MoneyConversionTest.java
  TimeConversionTest.java
  PurchaseOrderMappingIT.java
~~~

Các snippets Java dùng package `com.example.po`. Lớp public/record public cần được đặt vào tệp đúng tên theo quy tắc Java.

### 4.3. Tạo keyspace ở lab

~~~text
Bucket: commerce_lab
Scope: sales
Collection: purchase_orders

Một document key:
po::LAB1::PO-20261125-001
~~~

Dùng Couchbase Web Console hoặc công cụ quản trị được cho phép để tạo bucket/scope/collection. Chỉ cần Data Service để CRUD KV theo ID. Nếu muốn tìm theo `status`, `sku` hay thời điểm qua SQL++, cần Query/Index Service và GSI.

Không tự động chạy DDL hoặc tạo primary index khi mỗi Spring Boot instance khởi động. Quy trình triển khai index nên tách khỏi quyền runtime.

### 4.4. Cấu hình `application.yml`

~~~yaml
spring:
  couchbase:
    connection-string: "${CB_CONNECTION_STRING}"
    username: "${CB_USERNAME}"
    password: "${CB_PASSWORD}"
  data:
    couchbase:
      bucket-name: commerce_lab

server:
  port: 8080
~~~

Ví dụ `CB_CONNECTION_STRING=couchbase://127.0.0.1` ở local. Với Capella, sử dụng `couchbases://...`, cấu hình TLS/certificate chain đúng cách. Tài khoản Spring Boot chỉ cần quyền Data Reader/Writer và Query phù hợp keyspace của ứng dụng; **không dùng admin credentials production**.

~~~java
package com.example.po;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PurchaseOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(PurchaseOrderApplication.class, args);
    }
}
~~~

## 5. Vì sao không dùng `double` cho tiền?

`double` lưu số thực nhị phân, không biểu diễn chính xác tất cả số thập phân. Những phép cộng tiền có thể dẫn tới sai số hoặc cách làm tròn thiếu kiểm soát.

~~~java
// Minh họa đặc tính floating point; KHÔNG dùng làm tiền:
System.out.println(0.1d + 0.2d == 0.3d); // false
~~~

Dùng `BigDecimal`, khởi tạo từ **chuỗi** chứ không `new BigDecimal(0.1)`. Ngoài số tiền cần có **đơn vị tiền tệ**; `12.30 USD` khác `12.30 EUR`.

### 5.1. Lựa chọn biểu diễn tiền khi lưu JSON

| Biểu diễn JSON | Ví dụ | Lợi ích | Hạn chế |
|---|---|---|---|
| JSON number | `12.30` | Dễ truy vấn numeric | Parser/client có thể mất precision; cần ràng buộc scale |
| JSON string | `"USD|12.30"` | Giữ decimal chính xác, gọn; custom conversion rõ | Không trực tiếp làm numeric range/SUM |
| Object có amount string | `{"currency":"USD","amount":"12.30"}` | Dễ đọc, mở rộng schema | Vẫn phải parse amount thành decimal |
| Object minor units | `{"currency":"USD","minorUnits":1230}` | Integer arithmetic và numeric query theo minor units | Phải xử lý fraction digits từng currency, giới hạn `long` và scale |

Bài chọn **Money ↔ String** để làm rõ cơ chế custom conversions. Đối với báo cáo giá, lọc khoảng tiền hoặc tổng hợp SQL++ quy mô lớn, thiết kế object có numeric minor units **có thể tốt hơn**. Không coi chuỗi `USD|12.30` là cấu trúc lưu trữ duy nhất đúng.

### 5.2. `Currency` không phải dịch vụ tỷ giá

`Currency.getInstance("USD")` chỉ biểu diễn mã tiền tệ và thông tin fraction digits; nó **không** cho tỷ giá USD/VND. Custom converter cũng chỉ **serialize/deserialize**, không quy đổi tiền. Giao dịch ngoại tệ cần nguồn FX rate, thời điểm lấy tỷ giá, rounding và audit riêng.

## 6. Value object `Money` kiểm soát scale, currency và phép cộng

~~~java
package com.example.po;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

public record Money(Currency currency, BigDecimal amount) {

    public Money {
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(amount, "amount");

        int digits = currency.getDefaultFractionDigits();
        if (digits < 0) {
            throw new IllegalArgumentException(
                "Currency không có fraction digits xác định");
        }

        // Không tự làm tròn giá được gửi vào.
        // Chỉ cho phép các số có thể biểu diễn đúng ở scale đó.
        amount = amount.setScale(
            digits, RoundingMode.UNNECESSARY);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Giá đơn vị không được âm trong lab này");
        }
        if (amount.precision() > 18) {
            throw new IllegalArgumentException(
                "Số tiền vượt giới hạn precision của lab");
        }
    }

    public static Money of(
            String currencyCode, String decimalAmount) {
        return new Money(
            Currency.getInstance(currencyCode),
            new BigDecimal(decimalAmount)
        );
    }

    public Money multiply(int quantity) {
        if (quantity < 1) {
            throw new IllegalArgumentException(
                "quantity phải dương");
        }
        return new Money(
            currency,
            amount.multiply(BigDecimal.valueOf(quantity))
        );
    }

    public Money add(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Không cộng hai currency khác nhau");
        }
        return new Money(currency, amount.add(other.amount));
    }

    public static Money zero(Currency currency) {
        return new Money(currency, BigDecimal.ZERO);
    }
}
~~~

### 6.1. Nguyên tắc không làm tròn ngầm

`Money.of("USD","12.345")` phải lỗi vì USD có hai fraction digits và `12.345` không thể được biểu diễn chính xác ở scale 2. `Money.of("USD","12.300")` được chấp nhận vì phần dư chỉ là các chữ số 0; `RoundingMode.UNNECESSARY` chứng minh không mất giá trị.

Nếu nghiệp vụ cần làm tròn VAT/khuyến mãi, bước làm tròn phải **tường minh trước khi khởi tạo Money**, kèm policy `HALF_EVEN`/`HALF_UP` do business quyết định. Không cài một quy tắc rounding ngầm trong reading converter.

### 6.2. Ví dụ USD và VND

~~~java
Money usd = Money.of("USD", "12.30");
Money vnd = Money.of("VND", "150000");

Money line = usd.multiply(2); // 24.60 USD
Money total = line.add(Money.of("USD", "1.40"));
// 26.00 USD

// Không hợp lệ: currency khác nhau.
total.add(vnd); // IllegalArgumentException
~~~

Currency có 0 fraction digits như VND không đồng nghĩa mọi giá trong thực tế phải được mô tả bằng số nguyên theo tất cả hệ thống, nhưng **đây là policy lab** dựa trên ISO default fraction digits. Nếu cần tài khoản kế toán có scale tùy từng tiền, hãy định nghĩa policy khác và migration tests.

### 6.3. Cẩn trọng tràn số và định dạng đầu vào

`BigDecimal` chính xác nhưng không có giới hạn độ lớn mặc định; vì thế lab hạn chế `precision <= 18`. Production còn cần giới hạn giá mỗi dòng, số lượng, tổng đơn và chống người dùng gửi chuỗi cực dài (DoS). Khi đọc JSON, không parse chuỗi decimal bằng `double` rồi chuyển sang `BigDecimal`.

## 7. Chọn wire format ổn định cho Money

Converter sử dụng định dạng:

~~~text
<ISO_4217_CURRENCY_CODE>|<PLAIN_DECIMAL_AMOUNT>

Ví dụ:
USD|12.30
VND|150000
EUR|4.50
~~~

Giả sử cả hai chiều dùng format cố định. Không lưu ký hiệu `$`, dấu phân cách hàng nghìn, dấu phẩy locale hoặc chuỗi dịch như “12,30 USD”.

| Thuộc tính | Chính sách |
|---|---|
| Currency | `Currency.getCurrencyCode()`, không lấy ký hiệu địa phương |
| Decimal | `BigDecimal.toPlainString()`, không qua floating point |
| Separator | Ký tự `|`, một lần duy nhất |
| Scale | Chuẩn hóa theo currency fraction digits của lab |
| Lỗi parse | Báo lỗi có nguyên nhân, không thay bằng 0 |
| Version format | Coi `USD|12.30` là schema v1; thay đổi phải có migration |
| Query | Chuỗi không được dùng trực tiếp cho tính toán numeric SQL++ |

### 7.1. Tránh việc format phụ thuộc locale

`String.format(Locale.US,...)` hoặc `NumberFormat` có thể thêm dấu nhóm/số thập phân theo locale. Dữ liệu lưu trữ nên dùng **canonical machine format**, còn giao diện người dùng mới format cho người xem theo `Locale`.

### 7.2. Chuyển đổi không nên có business side effects

Converter không được gọi API tỷ giá, đọc trạng thái khác trong database, ghi log có PII hoặc tạo timestamp mới. Nó phải là phép biến đổi **thuần và có tính quyết định** đối với cùng một giá trị.

## 8. Viết converter `Money → String`

~~~java
package com.example.po;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class MoneyToStringConverter
        implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.currency().getCurrencyCode()
            + "|" + source.amount().toPlainString();
    }
}
~~~

Ví dụ:

~~~java
Money price = Money.of("USD", "12.30");
String stored = new MoneyToStringConverter().convert(price);
// "USD|12.30"
~~~

Không ép `source.amount().doubleValue()`; thao tác đó có thể mất precision. Converter cũng không làm tròn lại, vì constructor `Money` đã thực thi policy.

### 8.1. Vì sao cần `@WritingConverter`?

Spring Data có hai hướng chuyển đổi: Java domain → JSON store và JSON store → Java domain. Annotation giúp framework nhận biết ý định, đặc biệt khi có nhiều converter cho các kiểu có thể xem là đơn giản. Nó **không** tự đăng ký converter; vẫn cần cung cấp `CouchbaseCustomConversions` ở cấu hình.

## 9. Đọc converter `String → Money`

~~~java
package com.example.po;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class StringToMoneyConverter
        implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        if (source == null) {
            throw new IllegalArgumentException(
                "Không thể đọc Money từ null");
        }

        int separator = source.indexOf('|');
        if (separator != 3 ||
                separator != source.lastIndexOf('|')) {
            throw new IllegalArgumentException(
                "Money phải có dạng CCC|amount");
        }

        String code = source.substring(0, separator);
        String decimal = source.substring(separator + 1);

        if (!code.matches("[A-Z]{3}") ||
                !decimal.matches("[0-9]+(\\.[0-9]+)?")) {
            throw new IllegalArgumentException(
                "Money lưu trữ không đúng định dạng");
        }

        // Không fallback thành zero nếu dữ liệu cũ/corrupt.
        return Money.of(code, decimal);
    }
}
~~~

Một số trường hợp:

~~~text
"USD|12.30"      -> Money(USD, 12.30)
"VND|150000"     -> Money(VND, 150000)
"USD|12.345"     -> Lỗi scale
"usd|12.30"      -> Lỗi code không canonical
"USD|-12.30"     -> Lỗi theo policy giá không âm
"USD|NaN"        -> Lỗi
"USD|1,234.56"   -> Lỗi (không chứa locale separator)
"USD|12.30|BAD"  -> Lỗi
~~~

### 9.1. Vì sao phải từ chối dữ liệu sai?

Nếu database chứa `"USD|abc"`, converter im lặng trả `Money.zero(USD)` sẽ tạo **sai lệch tài chính rất khó phát hiện**. Lỗi mapping phải được ghi nhận, phân loại và xử lý theo data migration/repair. API có thể trả 5xx với correlation ID an toàn; không tiết lộ toàn bộ document cho người dùng.

### 9.2. Null, missing và backward compatibility

Một legacy document có thể thiếu trường `unit_price`. Với Spring Data mapping, field missing/null có thể không gọi converter mà tạo giá trị null trên property. Vì vậy:

- Service phải kiểm tra required nested fields trước tính tiền.
- Migration phải bổ sung dữ liệu thiếu hoặc đặt business default có kiểm soát.
- Không giả định converter chạy với mọi null.
- Trong bài, `Money` bắt buộc không-null khi tạo và đọc OrderLine mới.

## 10. Thời điểm: `OffsetDateTime`, `Instant` và múi giờ

Khi API nói “đặt lúc 10 giờ”, cần phân biệt:

- **Instant:** một mốc thời gian tuyệt đối trên trục UTC.
- **OffsetDateTime:** ngày/giờ kèm UTC offset như `+07:00`.
- **ZonedDateTime:** ngày/giờ kèm `ZoneId` (ví dụ `Asia/Ho_Chi_Minh`) và quy tắc DST nếu vùng có áp dụng.
- **LocalDateTime:** không chứa múi giờ/offset; **không đủ** để xác định một instant trên toàn cầu.
- **Long epoch milliseconds:** số mili-giây từ epoch UTC; có độ chính xác mili-giây, không lưu đủ nanoseconds.

Bài chọn giữ một `OffsetDateTime` trong Java nhưng persist **ISO-8601 UTC** khi ghi. Tức hai values `2026-11-25T10:00:00+07:00` và `2026-11-25T03:00:00Z` là **cùng một instant**, sau write/read sẽ đều trả về offset `Z`.

Nếu sản phẩm cần bảo toàn **offset gốc** hoặc timezone do người dùng chọn, phải lưu thêm `originalOffset`/`zoneId` riêng. Converter UTC ở đây chủ đích **không bảo toàn offset hiển thị ban đầu**.

### 10.1. Đừng nhầm định dạng hiển thị với thứ tự thời gian

ISO-8601 strings có thể có số chữ số fraction khác nhau; sort theo chuỗi không phải lúc nào cũng tương đương sort theo instant nếu biểu diễn không đồng nhất. Trong JSON mục tiêu, `placed_at_epoch_ms` hỗ trợ lọc/sắp xếp theo time numeric ở độ chính xác mili-giây, còn `placed_at` giữ timestamp ISO.

Nếu cần nanosecond precision trong query, lưu riêng `epochSecond` và `nanoAdjustment` hoặc biểu diễn numeric có quy ước hơn, không hứa epoch milliseconds giữ đủ precision.

## 11. `OffsetDateTime ↔ String` với canonical UTC

### 11.1. Writing converter

~~~java
package com.example.po;

import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class OffsetDateTimeToStringConverter
        implements Converter<OffsetDateTime, String> {

    @Override
    public String convert(OffsetDateTime value) {
        return DateTimeFormatter.ISO_INSTANT
                .format(value.toInstant());
    }
}
~~~

`ISO_INSTANT` sinh UTC string, giữ nanosecond precision của `Instant` khi biểu diễn cần thiết. Nó không giữ nguyên input offset, đúng theo chính sách bài.

### 11.2. Reading converter

~~~java
package com.example.po;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class StringToOffsetDateTimeConverter
        implements Converter<String, OffsetDateTime> {

    @Override
    public OffsetDateTime convert(String source) {
        return Instant.parse(source)
                .atOffset(ZoneOffset.UTC);
    }
}
~~~

### 11.3. Test hai input tương đương offset

~~~java
OffsetDateTime vietnam = OffsetDateTime.parse(
    "2026-11-25T10:00:00+07:00");
OffsetDateTime utc = OffsetDateTime.parse(
    "2026-11-25T03:00:00Z");

var writing = new OffsetDateTimeToStringConverter();
var reading = new StringToOffsetDateTimeConverter();

assert writing.convert(vietnam)
        .equals(writing.convert(utc));

OffsetDateTime restored =
    reading.convert(writing.convert(vietnam));

assert restored.toInstant().equals(vietnam.toInstant());
assert restored.getOffset().equals(ZoneOffset.UTC);
~~~

Đây là **minh họa Java assertions**, chưa phải test JUnit hoàn chỉnh. Kiểm tra round-trip theo `toInstant()`, không yêu cầu offset ban đầu bằng offset sau khi canonicalize.

### 11.4. Có luôn cần custom converter cho thời gian?

Không. Một số phiên bản Spring Data Couchbase/SDK hỗ trợ các kiểu ngày giờ nhất định thông qua built-in conversions. Nếu mapping mặc định đã đáp ứng chính sách storage của dự án, không cần custom converter. Bài dùng custom converter **để khóa rõ UTC string representation**, và yêu cầu kiểm chứng nó thực sự được chọn qua `CouchbaseCustomConversions`.

## 12. Đăng ký `CouchbaseCustomConversions` ở Spring Boot

Tạo một bean quản lý các bộ chuyển đổi:

~~~java
package com.example.po;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.couchbase.core.convert.CouchbaseCustomConversions;

@Configuration
public class CouchbaseMappingConfiguration {

    @Bean
    public CouchbaseCustomConversions customConversions() {
        return new CouchbaseCustomConversions(List.of(
            new MoneyToStringConverter(),
            new StringToMoneyConverter(),
            new OffsetDateTimeToStringConverter(),
            new StringToOffsetDateTimeConverter()
        ));
    }
}
~~~

**Kiểm tra tương thích:** với cấu hình Spring Boot/Spring Data Couchbase cụ thể, xem bean custom conversions có được đưa vào `MappingCouchbaseConverter` đang dùng không. Nếu dự án đã tự kế thừa `AbstractCouchbaseConfiguration` và override `customConversions()`, hãy **tích hợp vào đúng một cấu hình**, tránh đăng ký bean/converters trùng.

### 12.1. Cảnh báo “converter quá rộng”

Một `Converter<String, Object>` có thể can thiệp quá nhiều kiểu đích và gây lỗi khó tìm. Các converter trong bài được khóa rõ `Money ↔ String` và `OffsetDateTime ↔ String`.

Đặc biệt, `StringToMoneyConverter` chỉ nên chạy khi **kiểu property đích thực sự là Money**. Bài integration test sẽ kiểm tra các thuộc tính String khác như `sku`, `city`, `status` không bị biến thành Money.

### 12.2. Đăng ký đúng nhưng dữ liệu sai vẫn có thể lỗi

Nếu trường `unit_price` trong JSON cũ là object `{"currency":"USD","amount":12.3}`, converter `String → Money` **không** thể tự hiểu object đó. Phải có migration hoặc adapter đọc legacy schema; không ngầm giả định framework tự đổi mọi dạng JSON sang String.

## 13. Embedded POJO: `CustomerSnapshot`

Một snapshot không có `@Document` hoặc `@Id` riêng. Nó nằm trong root JSON, không được lưu thành document độc lập.

~~~java
package com.example.po;

import org.springframework.data.couchbase.core.mapping.Field;

public class CustomerSnapshot {

    @Field("customer_code")
    private String customerCode;

    @Field("display_name")
    private String displayName;

    public CustomerSnapshot() {}

    public CustomerSnapshot(String code, String name) {
        this.customerCode = code;
        this.displayName = name;
    }

    public String getCustomerCode() { return customerCode; }
    public void setCustomerCode(String customerCode) {
        this.customerCode = customerCode;
    }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Tương ứng JSON:

~~~json
{
  "customer_code": "CUS001",
  "display_name": "Nguyen Van A"
}
~~~

Nếu một customer đổi tên, snapshot trong đơn cũ **không tự cập nhật**. Đây là mục đích của snapshot lịch sử, không phải dấu hiệu mapping lỗi.

### 13.1. `@Field` chỉ đổi tên property trong JSON

`@Field("display_name")` ánh xạ `displayName` sang key `display_name`. Nó không yêu cầu SQL++ join và không cấp một document ID mới. Tránh đổi alias tùy tiện sau khi đã có dữ liệu: nếu tài liệu cũ chứa `display_name`, bản code mới chỉ đọc `name` mà không có migration thì giá trị có thể null.

## 14. Embedded `ShippingAddress`

~~~java
package com.example.po;

import org.springframework.data.couchbase.core.mapping.Field;

public class ShippingAddress {

    @Field("address_line")
    private String addressLine;

    @Field("city")
    private String city;

    @Field("country_code")
    private String countryCode;

    public ShippingAddress() {}

    public ShippingAddress(
            String addressLine, String city, String countryCode) {
        this.addressLine = addressLine;
        this.city = city;
        this.countryCode = countryCode;
    }

    public String getAddressLine() { return addressLine; }
    public void setAddressLine(String addressLine) {
        this.addressLine = addressLine;
    }

    public String getCity() { return city; }
    public void setCity(String city) {
        this.city = city;
    }

    public String getCountryCode() { return countryCode; }
    public void setCountryCode(String countryCode) {
        this.countryCode = countryCode;
    }
}
~~~

Tương ứng:

~~~json
{
  "address_line": "12 Example Street",
  "city": "Da Nang",
  "country_code": "VN"
}
~~~

### 14.1. Địa chỉ là dữ liệu nhạy cảm

Dữ liệu mẫu dùng địa chỉ giả. Trên production, cần phân quyền khi đọc, hạn chế log/trace, áp retention policy và cân nhắc mã hóa, masking theo quy định. Embedded object không mặc nhiên an toàn hơn tham chiếu.

### 14.2. Không biến địa chỉ thành key

Document ID của purchase order là định danh nghiệp vụ ổn định. Địa chỉ có thể thay đổi và chứa PII, nên không nên nhúng vào ID. Việc cập nhật địa chỉ trong một order document là một mutation của root aggregate.

## 15. Array embedded `List<OrderLine>` và converter Money

~~~java
package com.example.po;

import org.springframework.data.couchbase.core.mapping.Field;

public class OrderLine {

    @Field("line_no")
    private int lineNo;

    @Field("sku")
    private String sku;

    @Field("quantity")
    private int quantity;

    @Field("unit_price")
    private Money unitPrice;

    public OrderLine() {}

    public OrderLine(
            int lineNo, String sku,
            int quantity, Money unitPrice) {
        this.lineNo = lineNo;
        this.sku = sku;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public int getLineNo() { return lineNo; }
    public void setLineNo(int lineNo) {
        this.lineNo = lineNo;
    }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public int getQuantity() { return quantity; }
    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }

    public Money getUnitPrice() { return unitPrice; }
    public void setUnitPrice(Money unitPrice) {
        this.unitPrice = unitPrice;
    }
}
~~~

Với hai lines, JSON:

~~~json
[
  {
    "line_no": 1,
    "sku": "BOOK001",
    "quantity": 2,
    "unit_price": "USD|12.30"
  },
  {
    "line_no": 2,
    "sku": "PEN001",
    "quantity": 1,
    "unit_price": "USD|1.40"
  }
]
~~~

**Điểm đáng quan sát:** Spring Data mặc định map `OrderLine` thành object trong array; nhưng trường `unitPrice` kiểu `Money` được chuyển qua converter thành **string** `USD|12.30`.

### 15.1. Không tạo document riêng cho từng line

Một list bên trong root là một mảng JSON, không phải một tập các Couchbase documents với IDs tách biệt. `lineNo` là số thứ tự nghiệp vụ, không phải `@Id`. Những operations trên root phải tuân thủ document-level CAS nếu nhiều writers có thể sửa danh sách.

### 15.2. Null và nested collection

Nếu một dòng có `unitPrice == null`, một số luồng mapping có thể lưu null hoặc bỏ property tùy config; converter có thể không được gọi. Trong service, validate trước khi insert. Tránh cho phép `items = null` nếu business yêu cầu tối thiểu một sản phẩm.

## 16. Root `PurchaseOrderDocument` ánh xạ toàn bộ aggregate

~~~java
package com.example.po;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("purchase_orders")
public class PurchaseOrderDocument {

    @Id
    private String id;

    @Version
    private Long version;

    @Field("order_no")
    private String orderNumber;

    @Field("status")
    private String status;

    @Field("customer")
    private CustomerSnapshot customer;

    @Field("shipping_address")
    private ShippingAddress shippingAddress;

    @Field("items")
    private List<OrderLine> items = new ArrayList<>();

    @Field("total")
    private Money total;

    @Field("placed_at")
    private OffsetDateTime placedAt;

    @Field("placed_at_epoch_ms")
    private long placedAtEpochMs;

    public PurchaseOrderDocument() {}

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public Long getVersion() { return version; }
    public void setVersion(Long version) {
        this.version = version;
    }

    public String getOrderNumber() { return orderNumber; }
    public void setOrderNumber(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public CustomerSnapshot getCustomer() { return customer; }
    public void setCustomer(CustomerSnapshot customer) {
        this.customer = customer;
    }

    public ShippingAddress getShippingAddress() {
        return shippingAddress;
    }
    public void setShippingAddress(
            ShippingAddress shippingAddress) {
        this.shippingAddress = shippingAddress;
    }

    public List<OrderLine> getItems() { return items; }
    public void setItems(List<OrderLine> items) {
        this.items = items;
    }

    public Money getTotal() { return total; }
    public void setTotal(Money total) { this.total = total; }

    public OffsetDateTime getPlacedAt() { return placedAt; }
    public void setPlacedAt(OffsetDateTime placedAt) {
        this.placedAt = placedAt;
    }

    public long getPlacedAtEpochMs() {
        return placedAtEpochMs;
    }
    public void setPlacedAtEpochMs(long value) {
        this.placedAtEpochMs = value;
    }
}
~~~

### 16.1. Phân biệt field name Java và tên JSON

| Java property | JSON key | Kiểu JSON |
|---|---|---|
| `id` | KV document ID (metadata) | Không mặc định là field business trong body |
| `version` | CAS metadata | Không mặc định là field JSON thường |
| `orderNumber` | `order_no` | String |
| `customer` | `customer` | Object |
| `shippingAddress` | `shipping_address` | Object |
| `items` | `items` | Array |
| `unitPrice` trong line | `unit_price` | String do converter |
| `total` | `total` | String do converter |
| `placedAt` | `placed_at` | UTC ISO string do converter |
| `placedAtEpochMs` | `placed_at_epoch_ms` | Number |

### 16.2. Vì sao `@Version Long` không phải integer counter?

Spring Data Couchbase sử dụng CAS (compare-and-swap) token từ Couchbase để optimistic locking. Nó là **opaque version** của document, không phải số cập nhật cộng một. Không tự gán `version=1,2,3` hoặc tự tăng tại service. Nếu REST trả CAS cho JavaScript client, dùng **String** thay vì JSON number để tránh mất precision với số 64-bit.

### 16.3. Một lỗi mapping thường gặp

Nếu quên `@Collection("purchase_orders")`, Entity có thể được truy cập từ collection mặc định khác theo configuration; write có thể thành công nhưng SQL++ query vào collection mong muốn không thấy document. Kiểm tra bucket/scope/collection ở mỗi đường Repository, Template và SDK direct.

## 17. DTO đầu vào: không cho caller định giá tùy ý

Để tập trung vào nested mapping, API nhận SKU/quantity; giá lấy từ **catalog do server kiểm soát**.

~~~java
package com.example.po;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;

public record CreatePurchaseOrderRequest(
    @NotBlank
    @Pattern(regexp = "[A-Za-z0-9_-]{3,40}")
    String orderNumber,

    @NotBlank
    @Pattern(regexp = "[A-Za-z0-9_-]{3,40}")
    String customerCode,

    @NotBlank
    @Size(max = 120)
    String customerName,

    @Valid @NotNull
    AddressInput address,

    @Valid @NotEmpty @Size(max = 50)
    List<LineInput> items
) {}

record AddressInput(
    @NotBlank @Size(max = 160) String addressLine,
    @NotBlank @Size(max = 80) String city,
    @NotBlank @Pattern(regexp = "[A-Z]{2}") String countryCode
) {}

record LineInput(
    @NotBlank
    @Pattern(regexp = "[A-Za-z0-9_-]{3,40}")
    String sku,
    @Min(1) @Max(1000)
    int quantity
) {}
~~~

### 17.1. Bean Validation là lớp ngoài, service vẫn cần domain validation

`@Valid` kiểm tra cơ bản của HTTP JSON; business logic phải kiểm tra số dòng, trùng SKU, currency và tổng tiền. Nếu code được gọi từ batch/consumer không qua Spring MVC, validation ở controller không tự động bảo vệ. Không tin client gửi `total` hay `unitPrice`.

### 17.2. Số lượng và tổng giá

Để tránh overflow/business bypass, giới hạn `quantity` và số lines. Trong lab, tổng là `Money.zero(USD)` cộng từng `unitPrice.multiply(quantity)`. Production có thể cần giảm giá, thuế, shipping fee, phân bổ rounding; đây là những thành phần nghiệp vụ có policy riêng.

## 18. Catalog giả lập và phép tính tổng đúng currency

Một catalog nhỏ nằm trong Java code để buổi lab không cần gọi hệ thống giá bên ngoài:

~~~java
package com.example.po;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class LabPriceCatalog {

    private final Map<String, Money> prices = Map.of(
        "BOOK001", Money.of("USD", "12.30"),
        "PEN001",  Money.of("USD", "1.40"),
        "BOX001",  Money.of("USD", "5.00")
    );

    public Money priceOf(String normalizedSku) {
        Money value = prices.get(normalizedSku);
        if (value == null) {
            throw new IllegalArgumentException(
                "SKU không tồn tại trong catalog lab");
        }
        return value;
    }
}
~~~

Với hai BOOK001 và một PEN001:

~~~text
2 × USD 12.30 = USD 24.60
1 × USD  1.40 = USD  1.40
Total          = USD 26.00
~~~

### 18.1. Tại sao tính tổng ở service, không phải converter?

Converter chỉ thực hiện **đổi biểu diễn**, không nên biết chính sách về giá, promotion hoặc discount. Tổng tiền nên tính từ data đã được business kiểm tra, sau đó dùng converter để lưu. Trộn logic vào converter khiến việc đọc lại document có thể vô tình tính tổng khác với lúc ghi.

### 18.2. Snapshot giá khác catalog giá hiện tại

Nếu sau một tuần giá BOOK001 tăng, order đã lưu vẫn phải giữ unitPrice **tại thời điểm tạo**, không tự tính lại từ catalog khi đọc. Đó là lý do lưu snapshot unitPrice trong từng line.

## 19. Repository và Template theo root entity

~~~java
package com.example.po;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface PurchaseOrderRepository
        extends CouchbaseRepository<PurchaseOrderDocument, String> {
}
~~~

Với KV theo ID:

~~~java
PurchaseOrderDocument current = repository
    .findById("po::LAB1::PO-20261125-001")
    .orElseThrow();
~~~

Đường này lấy nguyên aggregate document; Spring Data mapping converter sẽ giải mã nested objects/arrays, Money và timestamp.

Muốn biểu đạt create-only rõ ràng:

~~~java
PurchaseOrderDocument saved = template
    .insertById(PurchaseOrderDocument.class)
    .one(candidate);
~~~

Muốn cập nhật đã có với CAS:

~~~java
PurchaseOrderDocument current = repository
    .findById(id).orElseThrow();

current.setStatus("CONFIRMED");

// @Version đã được ánh xạ từ CAS khi đọc.
PurchaseOrderDocument confirmed =
    repository.save(current);
~~~

### 19.1. `repository.save` có semantics phụ thuộc state

Entity mới với `version == null` và entity đã lưu có version khác nhau đối với new-entity detection. Bài chọn Template `insertById` cho Create vì thể hiện **không ghi đè** nếu ID đã tồn tại; dùng Repository `save` cho update đã đọc cùng CAS. Cả hai đường cần integration tests theo dependency version thực tế.

### 19.2. Template operation-level controls

Nếu môi trường có đủ Data nodes/replicas cho synchronous durability, có thể chọn trên một operation:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;

PurchaseOrderDocument saved = template
    .insertById(PurchaseOrderDocument.class)
    .withDurability(DurabilityLevel.MAJORITY)
    .one(candidate);
~~~

Điều này chỉ quyết định điều kiện xác nhận mutation, **không tạo replica tự động** và không bảo đảm chống mọi failure modes. Một-node lab/0 replica không chứng minh HA.

## 20. PurchaseOrderService: dựng nested graph, tính tiền và ghi nguyên tử

Service phía dưới cố ý giữ mọi input normalization, validation và calculation **trước** lệnh KV insert; converter vẫn chỉ làm đổi biểu diễn.

~~~java
package com.example.po;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Currency;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.stereotype.Service;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;
    private final CouchbaseTemplate template;
    private final LabPriceCatalog catalog;

    public PurchaseOrderService(
            PurchaseOrderRepository repository,
            CouchbaseTemplate template,
            LabPriceCatalog catalog) {
        this.repository = repository;
        this.template = template;
        this.catalog = catalog;
    }

    public PurchaseOrderDocument create(
            String tenantId, CreatePurchaseOrderRequest request) {

        String tenant = normalizeCode(tenantId);
        String orderNo = normalizeCode(request.orderNumber());
        String customerCode =
            normalizeCode(request.customerCode());

        if (!tenant.matches("[A-Z0-9_-]{2,32}")) {
            throw new IllegalArgumentException(
                "Tenant ID không hợp lệ");
        }
        if (request.address() == null ||
                request.items() == null ||
                request.items().isEmpty()) {
            throw new IllegalArgumentException(
                "Thiếu địa chỉ hoặc danh sách hàng");
        }
        if (request.items().size() > 50) {
            throw new IllegalArgumentException(
                "Có quá nhiều dòng hàng");
        }

        Set<String> seenSkus = new HashSet<>();
        List<OrderLine> lines = new ArrayList<>();

        Money total = Money.zero(
            Currency.getInstance("USD"));

        int lineNo = 1;
        for (LineInput input : request.items()) {
            if (input == null) {
                throw new IllegalArgumentException("Null line");
            }

            String sku = normalizeCode(input.sku());
            if (!sku.matches("[A-Z0-9_-]{3,40}") ||
                    input.quantity() < 1 ||
                    input.quantity() > 1000 ||
                    !seenSkus.add(sku)) {
                throw new IllegalArgumentException(
                    "SKU/quantity không hợp lệ hoặc trùng");
            }

            Money unitPrice = catalog.priceOf(sku);
            total = total.add(
                unitPrice.multiply(input.quantity()));

            lines.add(new OrderLine(
                lineNo++, sku,
                input.quantity(), unitPrice));
        }

        OffsetDateTime placedAt =
            OffsetDateTime.now(ZoneOffset.UTC);

        PurchaseOrderDocument candidate =
            new PurchaseOrderDocument();

        candidate.setId("po::" + tenant + "::" + orderNo);
        candidate.setOrderNumber(orderNo);
        candidate.setStatus("CREATED");

        candidate.setCustomer(new CustomerSnapshot(
            customerCode, request.customerName().trim()));

        candidate.setShippingAddress(new ShippingAddress(
            request.address().addressLine().trim(),
            request.address().city().trim(),
            request.address().countryCode()));

        candidate.setItems(lines);
        candidate.setTotal(total);
        candidate.setPlacedAt(placedAt);
        candidate.setPlacedAtEpochMs(
            placedAt.toInstant().toEpochMilli());

        // Atomic INSERT một root document bao gồm embedded content.
        return template
            .insertById(PurchaseOrderDocument.class)
            .one(candidate);
    }

    public PurchaseOrderDocument get(
            String tenantId, String orderNumber) {
        String tenant = normalizeCode(tenantId);
        String no = normalizeCode(orderNumber);
        String id = "po::" + tenant + "::" + no;
        PurchaseOrderDocument found =
            repository.findById(id).orElseThrow(() ->
                new NotFound("Không tìm thấy đơn hàng"));

        // Chỉ là cross-check; không thay authorization.
        if (!id.equals(found.getId())) {
            throw new IllegalStateException(
                "Document ID mismatch");
        }
        return found;
    }

    public PurchaseOrderDocument confirm(
            String tenantId, String orderNumber,
            String expectedVersion) {
        PurchaseOrderDocument current =
            get(tenantId, orderNumber);

        if (!String.valueOf(current.getVersion())
                .equals(expectedVersion)) {
            throw new Conflict(
                "Phiên bản đơn hàng đã đổi");
        }
        if (!"CREATED".equals(current.getStatus())) {
            throw new Conflict(
                "Trạng thái không cho phép confirm");
        }

        current.setStatus("CONFIRMED");
        // Repository save dùng @Version/CAS theo mapping.
        return repository.save(current);
    }

    public static class Conflict extends RuntimeException {
        public Conflict(String message) { super(message); }
    }

    public static class NotFound extends RuntimeException {
        public NotFound(String message) { super(message); }
    }

    private static String normalizeCode(String input) {
        if (input == null) {
            throw new IllegalArgumentException(
                "Mã không được null");
        }
        return input.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

### 20.1. Vì sao dùng `insertById` cho cả graph?

Tất cả fields của order nằm trong cùng **một document** nên một KV insert tạo nguyên body một cách atomic. Không cần “insert customer snapshot rồi insert items” bằng nhiều mutations độc lập. Nhưng **tính đúng đắn của tổng tiền** vẫn do service bảo đảm; Couchbase không tự so `total` với từng line.

### 20.2. CAS bảo vệ hai writers trên root

Hai requests cùng đọc phiên bản A, cùng muốn thay status. Khi một request đã commit, request còn lại dùng CAS cũ sẽ bị optimistic locking conflict (hoặc exception được framework dịch). Không bỏ CAS rồi `upsert` nếu muốn ngăn lost update. `@Version` chỉ bảo vệ root; một array item không có CAS riêng.

### 20.3. Giới hạn của mã service minh họa

- Chưa có authorization; tenantId từ HTTP không được tin trong production.
- Chưa có tax, discount, shipping fee, refund hoặc price version.
- `customerName` và `addressLine` cần validation ở service nếu gọi ngoài MVC; ở đây có DTO annotations nhưng service chỉ kiểm tra một số ràng buộc.
- Service đã dùng `Conflict` và `NotFound` cho hai nhóm lỗi trạng thái/không tìm thấy; production vẫn cần kiểm chứng error mapping và HTTP 409/404 trên đường REST thực tế.
- Thời gian mặc định `OffsetDateTime.now(UTC)` phụ thuộc clock node. Muốn integration tests deterministic nên inject `java.time.Clock`.
- Không có idempotent HTTP create: orderNo ổn định và insert-only ngăn overwrite cùng ID, nhưng muốn replay cùng payload trả 200 cần bổ sung fingerprint/command policy riêng.

## 21. Response DTO và mapper: chuyển Money ra HTTP an toàn

Không trả nguyên `PurchaseOrderDocument` như một public REST contract. Với số tiền, response dùng decimal **String**, tách currency để client không phải parse `USD|26.00` và không vô tình đi qua `double`.

~~~java
package com.example.po;

import java.util.List;

public record PurchaseOrderResponse(
    String documentId,
    String orderNumber,
    String status,
    String customerCode,
    String customerName,
    AddressView address,
    List<LineView> items,
    String totalAmount,
    String currency,
    String placedAt,
    long placedAtEpochMs,
    String version
) {}

record AddressView(
    String addressLine,
    String city,
    String countryCode
) {}

record LineView(
    int lineNo,
    String sku,
    int quantity,
    String unitPrice,
    String currency
) {}
~~~

Mapper:

~~~java
package com.example.po;

import java.time.format.DateTimeFormatter;

public final class PurchaseOrderPresenter {
    private PurchaseOrderPresenter() {}

    public static PurchaseOrderResponse from(
            PurchaseOrderDocument order) {
        ShippingAddress a = order.getShippingAddress();

        var lines = order.getItems().stream()
            .map(line -> new LineView(
                line.getLineNo(),
                line.getSku(),
                line.getQuantity(),
                line.getUnitPrice().amount().toPlainString(),
                line.getUnitPrice()
                    .currency().getCurrencyCode()
            ))
            .toList();

        return new PurchaseOrderResponse(
            order.getId(), order.getOrderNumber(),
            order.getStatus(),
            order.getCustomer().getCustomerCode(),
            order.getCustomer().getDisplayName(),
            new AddressView(
                a.getAddressLine(), a.getCity(),
                a.getCountryCode()),
            lines,
            order.getTotal().amount().toPlainString(),
            order.getTotal().currency().getCurrencyCode(),
            DateTimeFormatter.ISO_INSTANT.format(
                order.getPlacedAt().toInstant()),
            order.getPlacedAtEpochMs(),
            String.valueOf(order.getVersion())
        );
    }
}
~~~

### 21.1. Vì sao version là String?

`@Version Long` đại diện CAS 64-bit từ Couchbase. JavaScript `Number` không biểu diễn chính xác mọi 64-bit integer. REST nên trả CAS dưới dạng String để caller chuyển lại **nguyên văn** khi cập nhật, không làm `version+1`.

### 21.2. Vì sao không trả luôn `Money` ra JSON?

Converter của Spring Data Couchbase áp dụng cho **persistence mapping**; Jackson serializer của Spring Web **không tự dùng cùng CouchbaseCustomConversions**. Nếu trả entity/Money trực tiếp, HTTP JSON có thể có shape khác JSON trong Couchbase. Tách DTO làm rõ hợp đồng giữa database và API.

## 22. Controller và kết quả REST

~~~java
package com.example.po;

import java.net.URI;
import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/tenants/{tenantId}/purchase-orders")
public class PurchaseOrderController {
    private final PurchaseOrderService service;

    public PurchaseOrderController(
            PurchaseOrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<PurchaseOrderResponse> create(
            @PathVariable String tenantId,
            @Valid @RequestBody CreatePurchaseOrderRequest body) {
        var saved = service.create(tenantId, body);
        return ResponseEntity.created(
            URI.create("/tenants/" + tenantId.toUpperCase()
                + "/purchase-orders/"
                + saved.getOrderNumber())
        ).body(PurchaseOrderPresenter.from(saved));
    }

    @GetMapping("/{orderNo}")
    public PurchaseOrderResponse get(
            @PathVariable String tenantId,
            @PathVariable String orderNo) {
        return PurchaseOrderPresenter.from(
            service.get(tenantId, orderNo));
    }

    @PostMapping("/{orderNo}/confirm")
    public PurchaseOrderResponse confirm(
            @PathVariable String tenantId,
            @PathVariable String orderNo,
            @RequestHeader("If-Match") String version) {
        return PurchaseOrderPresenter.from(
            service.confirm(tenantId, orderNo, version));
    }
}
~~~

Một handler minh họa ánh xạ lỗi domain:

~~~java
package com.example.po;

import com.couchbase.client.core.error.DocumentExistsException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class PurchaseOrderExceptionHandler {
    @ExceptionHandler(PurchaseOrderService.NotFound.class)
    public ResponseEntity<ProblemDetail> missing(Exception e) {
        return problem(HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND");
    }

    @ExceptionHandler({
        PurchaseOrderService.Conflict.class,
        OptimisticLockingFailureException.class,
        DocumentExistsException.class,
        DuplicateKeyException.class
    })
    public ResponseEntity<ProblemDetail> conflict(Exception e) {
        return problem(HttpStatus.CONFLICT, "ORDER_CONFLICT");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ProblemDetail> invalid(Exception e) {
        return problem(HttpStatus.BAD_REQUEST, "INVALID_ORDER");
    }

    private ResponseEntity<ProblemDetail> problem(
            HttpStatus status, String code) {
        ProblemDetail body =
            ProblemDetail.forStatusAndDetail(
                status, "Yêu cầu không thể hoàn tất.");
        body.setProperty("code", code);
        return ResponseEntity.status(status).body(body);
    }
}
~~~

**Giới hạn:** Spring Data có thể dịch/bọc SDK exceptions; cần chạy integration tests để kiểm tra duplicate và optimistic-lock mapping thực tế. Đừng catch mọi database exception thành 409. Một `IllegalArgumentException` từ legacy converter bị bọc trong lỗi mapping phải được xem là lỗi dữ liệu/5xx, không phải 400 của caller; production cần domain-specific exception phân loại rõ.

### 22.1. HTTP status kỳ vọng

| Thao tác | HTTP | Ý nghĩa |
|---|---:|---|
| Create hợp lệ | 201 | Insert một root có nested fields |
| Get theo ID | 200 | Trả DTO qua mapping/read converters |
| Confirm với CAS hiện hành | 200 | Status được update |
| Order ID trùng | 409 | Insert-only, không upsert |
| CAS cũ | 409 | Writer phải đọc lại |
| Không thấy order | 404 | KV ID không có |
| Input sai | 400 | Bean Validation/domain checks |
| Converter đọc dữ liệu cũ sai | 5xx/triage | Không trả zero money hoặc false 404 |

### 22.2. Kiểm tra tenant ở production

Lab dùng tenant từ URL để tạo key và chỉ làm cross-check khi đọc. Ở production, tenant phải được xác thực từ principal và áp quyền ở cả KV paths, SQL++ filters và các endpoints. Một ID có prefix tenant **không phải** cơ chế authorization hoàn chỉnh.

## 23. Thử HTTP và so raw JSON với POJO

### 23.1. POST tạo order

~~~http
POST /tenants/LAB1/purchase-orders HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{
  "orderNumber": "PO-20261125-001",
  "customerCode": "CUS001",
  "customerName": "Nguyen Van A",
  "address": {
    "addressLine": "12 Example Street",
    "city": "Da Nang",
    "countryCode": "VN"
  },
  "items": [
    {"sku": "BOOK001", "quantity": 2},
    {"sku": "PEN001", "quantity": 1}
  ]
}
~~~

Kỳ vọng `201 Created` và response có:

~~~json
{
  "documentId": "po::LAB1::PO-20261125-001",
  "orderNumber": "PO-20261125-001",
  "status": "CREATED",
  "totalAmount": "26.00",
  "currency": "USD",
  "placedAt": "2026-11-25T03:00:00Z",
  "version": "<CAS_TOKEN>"
}
~~~

Response mẫu chỉ trích một số fields; API thực tế còn `address`, `items`, customer, epoch milliseconds. Timestamp/CAS thật do lúc chạy server quyết định, không hardcode từ ví dụ.

### 23.2. GET theo ID

~~~http
GET /tenants/LAB1/purchase-orders/PO-20261125-001 HTTP/1.1
Host: localhost:8080
~~~

Kỳ vọng `200 OK`, nested address/items được tái dựng và `unitPrice`/`total` qua reading converter không mất scale.

### 23.3. Quan sát raw document trong Couchbase lab

Tìm key `po::LAB1::PO-20261125-001` ở bucket `commerce_lab`, scope `sales`, collection `purchase_orders`. Kiểm tra:

- `shipping_address` là JSON object.
- `items` là JSON array gồm đúng hai embedded objects.
- `unit_price` là string `"USD|12.30"`, không phải object.
- `total` là string `"USD|26.00"`.
- `placed_at` có UTC ISO string.
- `placed_at_epoch_ms` là JSON number.
- `id` và CAS là metadata, không bắt buộc xuất hiện như fields trong body.
- `_class` có thể được Spring Data thêm để lưu type information.

Không chỉ assert HTTP response: Jackson có serialization riêng, nên **phải xem đúng raw storage representation** để chứng minh custom Couchbase converters được sử dụng.

### 23.4. Confirm với version nhận được

~~~http
POST /tenants/LAB1/purchase-orders/PO-20261125-001/confirm HTTP/1.1
Host: localhost:8080
If-Match: <VERSION_FROM_GET>
~~~

Kỳ vọng status `CONFIRMED` và CAS mới. Gửi lại version cũ phải bị từ chối; không bỏ CAS để ghi đè root.

## 24. SQL++ query theo nested object và array

KV `repository.findById` đọc theo ID không cần GSI. Nhưng tìm theo thành phố hoặc SKU trong `items` là SQL++ query cần index tương ứng.

### 24.1. Chỉ mục theo thành phố

~~~sql
CREATE INDEX ix_po_city_status
ON `commerce_lab`.`sales`.`purchase_orders`
    (shipping_address.city, status);
~~~

~~~sql
SELECT META(o).id AS documentId,
       o.order_no, o.status, o.shipping_address.city
FROM `commerce_lab`.`sales`.`purchase_orders` AS o
WHERE o.shipping_address.city = "Da Nang"
  AND o.status = "CREATED"
LIMIT 20;
~~~

Lưu ý SQL++ dùng **field JSON** `shipping_address.city`, không phải Java `shippingAddress.city`. Đừng tự tạo primary index trên production chỉ vì thiếu index phù hợp.

### 24.2. Chỉ mục và truy vấn ANY trong array

~~~sql
CREATE INDEX ix_po_items_sku
ON `commerce_lab`.`sales`.`purchase_orders`
    (DISTINCT ARRAY i.sku FOR i IN items END);
~~~

~~~sql
SELECT META(o).id AS documentId, o.order_no
FROM `commerce_lab`.`sales`.`purchase_orders` AS o
WHERE ANY i IN o.items
      SATISFIES i.sku = "BOOK001"
      END
LIMIT 20;
~~~

Đây là **array index** tương ứng với một số predicate `ANY`. Kiểm tra `EXPLAIN` và planner ở version cụ thể; không hứa chỉ mục được chọn tự động trong mọi câu query/biến thể.

### 24.3. UNNEST để đọc từng line

~~~sql
SELECT o.order_no,
       item.line_no, item.sku,
       item.quantity, item.unit_price
FROM `commerce_lab`.`sales`.`purchase_orders` AS o
UNNEST o.items AS item
WHERE item.sku = "BOOK001"
LIMIT 20;
~~~

`UNNEST` có thể tạo nhiều kết quả từ một order. Không tự map projection này thành một `PurchaseOrderDocument` đầy đủ nếu không reconstruct nested items.

### 24.4. Cần phân biệt đường KV và SQL++

- `findById`: đọc toàn aggregate theo document key.
- Query theo `status`/`city`: SQL++ Query Service + GSI, cần index và scan consistency.
- `REQUEST_PLUS`: đợi index theo mốc query, có thể tăng p99/timeout.
- Durability: điều kiện majority/persistence của mutation, **không** tự buộc GSI mới.

## 25. Khi cần truy vấn giá tiền hoặc thời điểm

### 25.1. Thời gian lưu string và epoch millis

Để lọc theo thời gian trong lab, chỉ mục numeric:

~~~sql
CREATE INDEX ix_po_status_time
ON `commerce_lab`.`sales`.`purchase_orders`
    (status, placed_at_epoch_ms);
~~~

~~~sql
SELECT META(o).id AS id,
       o.order_no, o.placed_at
FROM `commerce_lab`.`sales`.`purchase_orders` AS o
WHERE o.status = "CREATED"
  AND o.placed_at_epoch_ms >= 1795575600000
  AND o.placed_at_epoch_ms <  1795662000000
ORDER BY o.placed_at_epoch_ms
LIMIT 100;
~~~

Mốc epoch ở ví dụ là cửa sổ UTC minh họa. Với yêu cầu từ múi giờ địa phương, dùng `ZoneId` và Java time API tính instant boundaries, không cộng giờ thủ công qua DST.

**Đánh đổi:** `placedAtEpochMs` là field dư thừa, cần được sinh từ **cùng một instant** với `placedAt`. Nó không lưu nanoseconds; nếu business cần precision cao hơn, thiết kế schema riêng.

### 25.2. Money string không thích hợp cho SQL++ numeric aggregation

~~~text
total = "USD|26.00"   // string, không phải JSON number
~~~

Không dùng `SUM(o.total)` hoặc so chuỗi `"USD|9.00" > "USD|100.00"` để tính tiền. Nếu báo cáo/sort/range quan trọng, cân nhắc schema:

~~~json
{
  "total": {
    "currency": "USD",
    "minor_units": 2600
  }
}
~~~

Trong USD minor units 2600 tương ứng 26.00; với currency fraction digits khác thì phép đổi khác. Cần chỉ mục và không được cộng số của hai currencies khác nhau.

### 25.3. Custom conversion không phải duy nhất lựa chọn

Nếu cần query sâu vào `money.currency` và `money.minorUnits`, thay vì scalar converter, có thể tạo embedded `MoneyJson` với fields rõ ràng hoặc converter đến store-native object đã được version kiểm chứng. Chọn schema theo **cách sẽ truy vấn**, không chỉ theo sự tiện lợi của Java value object.

## 26. Schema evolution và đọc legacy documents

Một deploy trước có thể lưu:

~~~json
{
  "unit_price": {"currency": "USD", "amount": 12.30}
}
~~~

Deploy mới muốn:

~~~json
{
  "unit_price": "USD|12.30"
}
~~~

`StringToMoneyConverter` không tự biến object cũ thành string. Quy trình migration an toàn:

1. Inventory những schema versions và field types hiện có.
2. Quy định canonical representation chính thức.
3. Thêm reader có khả năng xử lý legacy, **nếu** cần rolling upgrade.
4. Backfill dữ liệu theo runbook, không parse qua double gây sai số.
5. Test round-trip các records cũ/mới và malformed.
6. Giám sát conversion exceptions trong deploy.
7. Chỉ gỡ tương thích sau khi xác minh migration và rollback.

### 26.1. Đừng sửa alias mà quên dữ liệu cũ

Đổi `@Field("unit_price")` thành `@Field("price")` không tự rename field trong Couchbase documents. Tương tự, thay package/class hoặc type discriminator có thể ảnh hưởng mapping. Schema evolution cần test với dữ liệu tồn tại, không chỉ các documents vừa được tạo mới.

### 26.2. Không biến dữ liệu hỏng thành tiền bằng 0

Nếu đọc `"USD|abc"`, converter nên fail; tự trả `Money.zero(USD)` có thể biến dữ liệu bị lỗi thành đơn hàng “miễn phí”. Có thể cô lập record, alert, data repair có audit; không sửa lén trong read path.

### 26.3. Legacy timestamp

Một số records cũ có offset khác Z, hoặc ngày giờ địa phương không kèm zone. Với format có offset, có thể parse rồi canonicalize về UTC khi biết instant. Với `LocalDateTime` không có zone, không tự gắn UTC nếu không biết timezone nguồn; cần quy tắc migration từ business.

## 27. Null, missing và sai kiểu ở nested JSON

| Dữ liệu lưu trữ | Điều có thể xảy ra | Phản ứng đúng |
|---|---|---|
| Thiếu `customer` | Java field null | Không trả thành công cho order bắt buộc có customer |
| `items: []` | Empty list | Business validation từ chối |
| `unit_price: null` | Converter có thể không chạy | Reject/triage, không default 0 |
| `unit_price: "USD|abc"` | Parse failure | Fail rõ, giữ evidence |
| `unit_price` cũ là object | Kiểu không khớp String converter | Migration/legacy reader |
| `placed_at` thiếu | Timestamp null | Quyết định migration policy |
| `placed_at_epoch_ms` không khớp | Sort/filter time sai | Kiểm tra/recompute |
| Field lạ thêm trong JSON | Mapper có thể bỏ qua | Quyết định forward compatibility |
| `_class` khác kỳ vọng | Type resolution có thể sai | Test mapping theo version |

### 27.1. Validation MVC không bảo vệ SDK direct writes

Một API khác dùng Java SDK trực tiếp có thể ghi document không tuân theo annotation Bean Validation của DTO. Cần hạn chế write paths và quy định schema contract, không trông chờ database tự enforce các business invariants.

### 27.2. CAS áp dụng cho cả root

Hai writers cùng đọc root rồi sửa các nested fields khác nhau vẫn có thể gặp CAS conflict. Đó là trade-off của aggregate một document. Nếu document quá “hot”, cân nhắc command routing hoặc tách aggregate; không tự bật upsert để khỏi thấy conflict.

## 28. Unit test converters: Round-trip và lỗi tài chính

~~~java
package com.example.po;

import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class MoneyConversionTest {
    private final MoneyToStringConverter writer =
        new MoneyToStringConverter();
    private final StringToMoneyConverter reader =
        new StringToMoneyConverter();

    @Test
    void usdRoundTripPreservesPrecision() {
        Money expected = Money.of("USD", "12.30");
        String stored = writer.convert(expected);

        assertEquals("USD|12.30", stored);
        Money actual = reader.convert(stored);
        assertEquals(expected, actual);
        assertEquals(new BigDecimal("12.30"), actual.amount());
        assertEquals(2, actual.amount().scale());
    }

    @Test
    void vndRoundTripIsIntegerInLabPolicy() {
        Money vnd = Money.of("VND", "150000");
        assertEquals("VND|150000", writer.convert(vnd));
        assertEquals(vnd, reader.convert("VND|150000"));
    }

    @Test
    void fractionalLossIsRejected() {
        assertThrows(ArithmeticException.class, () ->
            Money.of("USD", "12.345"));
    }

    @Test
    void malformedStoredValueIsRejected() {
        for (String raw : new String[]{
            "USD|abc", "usd|12.30",
            "USD|-1.00", "USD|1,000.00",
            "USD|1.00|X"
        }) {
            assertThrows(RuntimeException.class, () ->
                reader.convert(raw));
        }
    }

    @Test
    void totalIsExactAndCurrencySafe() {
        Money total = Money.of("USD", "12.30")
            .multiply(2)
            .add(Money.of("USD", "1.40"));

        assertEquals(Money.of("USD", "26.00"), total);
        assertThrows(IllegalArgumentException.class, () ->
            total.add(Money.of("VND", "1000")));
    }
}
~~~

Time converter test:

~~~java
package com.example.po;

import static org.junit.jupiter.api.Assertions.*;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class TimeConversionTest {
    @Test
    void twoOffsetsRepresentSameInstantInStorage() {
        var writer = new OffsetDateTimeToStringConverter();
        var reader = new StringToOffsetDateTimeConverter();

        var vietnam = OffsetDateTime.parse(
            "2026-11-25T10:00:00+07:00");
        var utc = OffsetDateTime.parse(
            "2026-11-25T03:00:00Z");

        assertEquals(writer.convert(vietnam),
                     writer.convert(utc));

        var restored = reader.convert(
            writer.convert(vietnam));

        assertEquals(vietnam.toInstant(),
                     restored.toInstant());
        assertEquals(ZoneOffset.UTC,
                     restored.getOffset());
    }
}
~~~

Các test trên chứng minh **hàm Java converter**; chưa chứng minh MappingCouchbaseConverter thực sự áp chúng vào từng nested property. Phần tiếp theo cần test với **bucket Couchbase lab thật**.

## 29. Integration test: Spring Data round-trip và raw Couchbase JSON

Unit test converter không phát hiện được các lỗi như:

- Bean `CouchbaseCustomConversions` không được MappingCouchbaseConverter sử dụng.
- `@Field` alias bị viết sai, dữ liệu nằm ở key khác.
- List embedded objects không được map như mong đợi.
- Một trường `Money` bị lưu dưới dạng object thay vì String.
- `OffsetDateTime` dùng built-in conversion khác custom converter.
- `@Scope`/`@Collection` trỏ sai keyspace.

Vì thế cần chạy integration test **chỉ trên bucket Couchbase lab**, đọc qua cả Spring Data và Java SDK raw JSON.

### 29.1. Test mapping từ object sang JSON và ngược lại

~~~java
package com.example.po;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@EnabledIfEnvironmentVariable(
    named = "RUN_CB_IT", matches = "true")
class PurchaseOrderMappingIT {

    @Autowired
    PurchaseOrderService service;

    @Autowired
    PurchaseOrderRepository repository;

    @Autowired
    Cluster cluster;

    @Test
    void nestedMappingAndCustomConvertersRoundTrip() {
        String suffix = UUID.randomUUID()
            .toString().substring(0, 8).toUpperCase();
        String orderNo = "IT-" + suffix;

        var request = new CreatePurchaseOrderRequest(
            orderNo,
            "CUS001",
            "Nguyen Van A",
            new AddressInput(
                "12 Example Street", "Da Nang", "VN"),
            List.of(
                new LineInput("BOOK001", 2),
                new LineInput("PEN001", 1)
            )
        );

        PurchaseOrderDocument saved =
            service.create("LAB1", request);
        String id = saved.getId();

        Collection sdkCollection = cluster
            .bucket("commerce_lab")
            .scope("sales")
            .collection("purchase_orders");

        try {
            // 1. Spring Data đọc round-trip:
            PurchaseOrderDocument loaded =
                repository.findById(id).orElseThrow();

            assertEquals("Da Nang",
                loaded.getShippingAddress().getCity());
            assertEquals("CUS001",
                loaded.getCustomer().getCustomerCode());
            assertEquals(2, loaded.getItems().size());
            assertEquals(Money.of("USD", "12.30"),
                loaded.getItems().get(0).getUnitPrice());
            assertEquals(Money.of("USD", "26.00"),
                loaded.getTotal());
            assertEquals(
                loaded.getPlacedAt().toInstant().toEpochMilli(),
                loaded.getPlacedAtEpochMs()
            );

            // 2. SDK đọc nguyên JSON để xác minh wire format:
            JsonObject raw = sdkCollection
                .get(id)
                .contentAsObject();

            assertEquals("USD|26.00",
                raw.getString("total"));
            assertEquals("USD|12.30",
                raw.getArray("items")
                    .getObject(0)
                    .getString("unit_price"));
            assertEquals("Da Nang",
                raw.getObject("shipping_address")
                    .getString("city"));
            assertEquals(Instant.parse(
                    raw.getString("placed_at")),
                loaded.getPlacedAt().toInstant());
            assertEquals(
                Long.valueOf(
                    loaded.getPlacedAtEpochMs()),
                raw.getLong("placed_at_epoch_ms")
            );
        } finally {
            try {
                sdkCollection.remove(id);
            } catch (DocumentNotFoundException ignored) {
                // Test cleanup khi document đã bị xóa.
            }
        }
    }
}
~~~

**Đây là code mẫu chưa được thực thi trong STEP 4.** Để chạy, cần cluster/credentials/bucket/scope/collection thật của môi trường thử nghiệm, Java SDK và Spring Data versions tương thích. `@EnabledIfEnvironmentVariable` tránh bật test theo mặc định, nhưng không thay environment allowlist hoặc RBAC.

### 29.2. Vì sao đọc raw qua SDK?

Khi đi qua Spring Data, cả reading và writing converters có thể che một lỗi tương thích trong lưu trữ: Java object vẫn “trông đúng” sau một số fallback nhưng dữ liệu ngoài hệ thống lại thấy shape khác. Đọc raw JSON giúp assert chính xác rằng `unit_price` là **string** và `placed_at` là string UTC, đúng hợp đồng schema.

### 29.3. Thêm test legacy/corruption vào lab riêng

Seed một document giả có `unit_price="USD|bad"`. Khi Repository đọc, hệ thống phải báo conversion error thay vì trả 0. Test cần cô lập data và cleanup dù mapper lỗi; không bơm dữ liệu hỏng vào production để chứng minh exception.

### 29.4. Không đồng nhất HTTP/Jackson với Couchbase mapping

Một HTTP controller có thể trả `Money` dưới dạng `{"currency": "...", "amount": ...}` khi dùng Jackson, trong khi raw DB là `"USD|12.30"`. Đây là hai contracts khác nhau. Test `MockMvc`/HTTP có thể cần thêm để bảo đảm DTO ngoài mạng ổn định, nhưng không thay raw storage test.

## 30. CAS và concurrency test trên root aggregate

Hai writers cùng đọc một order version `V1`:

~~~text
A: đọc V1, đổi status thành CONFIRMED.
B: đọc V1, đổi shipping_address.city thành Hanoi.
A: save với CAS V1 -> thành công, root có CAS V2.
B: save với CAS V1 -> phải bị từ chối, không ghi đè A.
~~~

Bài chọn root aggregate một document: CAS dùng ở cấp root, bất kể writer sửa nested property nào.

### 30.1. JUnit test optimistic locking

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.dao.OptimisticLockingFailureException;

// Giả sử repo và ID được tạo ở lab.
// Chạy trong integration test có cleanup và data isolation.
PurchaseOrderDocument writerA =
    repository.findById(id).orElseThrow();
PurchaseOrderDocument writerB =
    repository.findById(id).orElseThrow();

writerA.setStatus("CONFIRMED");
repository.save(writerA);

writerB.getShippingAddress().setCity("Hanoi");

assertThrows(OptimisticLockingFailureException.class, () ->
    repository.save(writerB)
);
~~~

Tên exception cụ thể có thể được framework dịch/bọc tùy version; integration test phải xác nhận lỗi thực tế. Đừng bỏ CAS hoặc chuyển sang `upsert` để “làm test xanh”.

### 30.2. Chọn cách sửa khi conflict

- Đọc root document mới nhất.
- So trạng thái và business invariants.
- Quyết định có merge bản địa chỉ mới vào trạng thái đã `CONFIRMED` hay không.
- Nếu hợp lệ, dùng CAS mới trong **một mutation mới**; không tự động cập nhật cả body stale.
- Đặt retry budget và giới hạn concurrency với hot order.

### 30.3. Sub-document operations không tự miễn CAS

Couchbase hỗ trợ thay đổi một đường dẫn JSON bên trong document qua sub-document APIs. Chúng có thể giảm kích thước payload và cho phép một số update paths hiệu quả hơn, nhưng vẫn phải hiểu atomicity/last-writer/CAS và logic tiền. Không dùng sub-document tùy tiện để sửa `items[0].unit_price` mà quên cập nhật `total`.

## 31. Reactive extension: cùng schema, khác execution model

Trong ứng dụng reactive, có thể dùng `ReactiveCouchbaseRepository` hoặc `ReactiveCouchbaseTemplate` nếu Spring Data version hỗ trợ. Những converters cần được áp vào **mapping layer** của pipeline tương ứng.

~~~java
package com.example.po;

import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;

public interface ReactivePurchaseOrderRepository
        extends ReactiveCouchbaseRepository<
            PurchaseOrderDocument, String> {
}
~~~

Ví dụ readback reactive:

~~~java
reactiveRepository.findById(id)
    .map(PurchaseOrderPresenter::from);
~~~

### 31.1. Không gọi `block()` trên event loop

Nếu Controller dùng WebFlux và vẫn gọi `CouchbaseTemplate` blocking, có thể gây block event loop. Chọn stack đồng nhất hoặc tách scheduler/adapter cẩn thận; tốt hơn dùng API reactive từ đầu khi yêu cầu throughput/latency đòi hỏi.

### 31.2. Retry không làm dữ liệu tự hợp lệ

`Mono.retryWhen` có thể resubscribe và thực hiện mutation lại. Khi mutation bị timeout ambiguous, operation có thể đã commit dù response mất. Không tạo `orderNo`/document ID mới ở mỗi retry và không viết side effects trong callback có thể replay. Converter vẫn phải thuần, không call FX API hoặc tạo timestamp lúc đọc.

### 31.3. Reactive mapping cũng cần integration test

Một unit test `MoneyToStringConverter` không chứng minh reactive repository path sử dụng cùng custom conversions nếu dự án có nhiều `CouchbaseMappingContext`/converter beans tùy chỉnh. Test đường thật trên lab, kiểm tra raw JSON như synchronous path.

## 32. Observability, bảo mật và tác động vận hành

### 32.1. Metrics đề xuất

| Nhóm | Metric/quan sát | Câu hỏi |
|---|---|---|
| Mapping | `po_mapping_error_total` | Dữ liệu nào đọc không được? |
| Conversion | `po_money_parse_error_total` | Có malformed hoặc legacy money? |
| Validation | `po_invalid_input_total` | SKU/quantity/address sai? |
| CAS | `po_optimistic_conflict_total` | Root document có bị hot không? |
| Latency | KV `insert/get/replace` p95/p99 | Data Service có chậm không? |
| SQL++ | Query p95/p99 và index state | GSI/index plan có vấn đề không? |
| Payload | Document bytes, item count | Aggregate có phình lớn không? |
| Time | Epoch mismatch count | Có writer bỏ cập nhật derived field không? |
| Business | Tổng tiền không bằng lines | Có path ghi bypass service không? |
| Durability | Errors/ambiguous outcomes | Có vấn đề quorum/persistence không? |

Đây là **tên metric do ứng dụng có thể đặt**, không khẳng định Couchbase Server tự phát những tên trên.

### 32.2. Log thông tin đủ chẩn đoán nhưng không lộ PII

~~~text
event=PURCHASE_ORDER_READ_FAILED
requestId=req-123
tenant=LAB1
documentIdHash=redacted
fieldPath=items[0].unit_price
errorCategory=MONEY_PARSE_ERROR
schemaVersion=1
sdkVersion=observed
action=REQUIRES_DATA_REPAIR
~~~

Không log customer display name, địa chỉ, raw document body hoặc credentials. Phần field path/error category đủ cho SRE biết lỗi conversion nằm ở giá tiền, không nhầm với thiếu Index Service.

### 32.3. Security

- Runtime account RBAC giới hạn bucket/scope/collection.
- TLS và secret manager, không đưa credential vào source.
- Tenant authorization bắt buộc trên cả KV và SQL++ paths.
- API response dùng DTO hạn chế thông tin khách hàng/địa chỉ theo role.
- Converter đọc string có kiểm tra độ dài/format, tránh parse input vô hạn.
- Không expose lỗi parser raw cho caller như một JSON data leak.
- Dữ liệu snapshot có thể nằm trong nhiều orders, cần retention/masking/erasure policy phù hợp.

### 32.4. Quản lý thời gian và business clock

- Khi cần deterministic test, inject `Clock` thay cho gọi `now()` trực tiếp.
- Nên lưu UTC instant cho sự kiện đã xảy ra.
- Nếu muốn lên lịch cho 09:00 ở timezone người dùng, cần giữ `ZoneId` và xử lý DST.
- Một bảng lưu `placedAtEpochMs` dư phải được kiểm chứng khớp `placedAt`.
- Không đồng nhất server time và business source-of-truth time trong hệ thống có clocks lệch lớn.

## 33. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| `unit_price` thành object thay vì string | Converter chưa được register/chọn | Read raw JSON; bean `CouchbaseCustomConversions` |
| Ghi thành công nhưng đọc lỗi | Thiếu ReadingConverter hoặc legacy format | Unit + integration round-trip |
| Tiền bị `12.299999...` | Dùng double trước BigDecimal | Kiểm tra đầu vào và phép tính |
| Giá 12.345 bị reject | Scale vượt USD policy | Xác minh rounding rule thay vì bỏ validation |
| Tổng 25.99 thay vì 26.00 | Tính floating point hoặc thiếu một line | Dùng Money.multiply/add và assert |
| VND bị ghi `150000.00` | Scale policy không theo currency | Kiểm tra normalized Money |
| `placed_at` sai giờ 7 tiếng | Parse/format không thống nhất timezone | So `toInstant()` và UTC |
| Dữ liệu gốc offset +07:00 nhưng đọc ra Z | Canonical UTC cố ý | Nếu cần offset gốc, lưu riêng |
| SQL++ tìm SKU không thấy | Index lag, sai ARRAY index, sai field alias | Raw KV, `EXPLAIN`, index state |
| `findById` không tìm thấy | Sai bucket/scope/collection/key | So `@Scope`/`@Collection` và key |
| CAS mismatch khi confirm | Writer khác đã thay root | Reload/re-evaluate state machine |
| Spring đọc legacy object thành lỗi Money | Converter chỉ nhận string | Backfill hoặc reader tương thích |
| Index scan consistency timeout | GSI đang chậm/catch-up | Query metrics, không tăng KV durability mù |
| UI thấy sai decimal formatting | HTTP formatter/locale | Không sửa wire/storage format vì UI |
| Report giá không SUM được | `total` lưu String | Thiết kế numeric minor-units field |
| App chạy nhưng không dùng converter | Đăng ký sai config/multiple contexts | Raw JSON IT và bean inspection |

### 33.1. Phân loại lỗi mapping với lỗi hạ tầng

Một `DataAccessException` bọc conversion error không có nghĩa Data node down. Một 404 theo KV ID không đồng nghĩa Index Service lag. Phân tách errors theo path: validation, conversion, KV, query/index, CAS và durability.

## 34. Năm case studies

### 34.1. Case A — Giá bị sai do dùng double

**Bối cảnh:** code tính tổng bằng `double` rồi tạo `new BigDecimal(doubleValue)`, báo cáo xuất số thập phân dài.

**Lỗi:** nhầm floating point nhị phân với decimal chính xác.

**Sửa:** nguồn giá là chuỗi decimal hoặc minor units; `Money.of("USD", "12.30")` và phép cộng `BigDecimal`. Chỉ round khi business đã có policy.

**Test:** tổng hai BOOK001 và một PEN001 phải chính xác `USD|26.00`.

### 34.2. Case B — Converter ghi được nhưng không đọc được

**Bối cảnh:** team đăng ký `MoneyToStringConverter` nhưng quên `StringToMoneyConverter` hoặc bean không được mapper dùng.

**Lỗi:** có code write, không có đường read/round-trip tương thích.

**Sửa:** đăng ký cả hai converters, unit test mỗi chiều và raw JSON integration test, bao gồm nested `items[0].unit_price`.

**Test:** Repository `findById` trả `Money.of("USD","12.30")`, raw SDK thấy `"USD|12.30"`.

### 34.3. Case C — Sai giờ khi chuyển giữa UTC và local

**Bối cảnh:** yêu cầu tạo lúc 10:00 +07 nhưng lưu/đọc lại như 10:00Z, lệch bảy tiếng.

**Lỗi:** xử lý `LocalDateTime` không kèm zone như thể là instant.

**Sửa:** dùng `OffsetDateTime.toInstant()` rồi ISO UTC khi lưu; lúc hiển thị theo timezone người dùng mới convert.

**Test:** `2026-11-25T10:00:00+07:00` và `2026-11-25T03:00:00Z` phải có cùng instant.

### 34.4. Case D — Đổi alias làm dữ liệu “biến mất”

**Bối cảnh:** deploy mới đổi `@Field("shipping_address")` thành `@Field("shippingAddress")` nhưng không migrate documents cũ.

**Lỗi:** framework đọc từ key JSON mới, trong khi dữ liệu lịch sử nằm ở key cũ.

**Sửa:** giữ alias, hoặc triển khai version-aware reader/backfill có test. Không kết luận document mất khi KV ID vẫn tồn tại.

**Test:** đọc được cả record cũ và mới trong giai đoạn rollout được phê duyệt.

### 34.5. Case E — Hai writers làm mất thay đổi nested

**Bối cảnh:** A sửa địa chỉ, B sửa items dựa trên cùng snapshot; B save root stale, ghi đè thay đổi A.

**Lỗi:** bỏ `@Version` hoặc dùng `upsert` không điều kiện.

**Sửa:** CAS/optimistic locking, reload/merge theo state machine, kiểm tra invariants khi sửa line và total.

**Test:** hai writers cùng CAS cũ không thể cùng âm thầm thành công và làm mất cập nhật đã commit.

## 35. Bài tập nâng cao

### Bài A — Vẽ object graph

Vẽ PurchaseOrderDocument và ba embedded classes. Annotation nào đặt ở root, annotation nào đặt trên field nested? `@Id` của line có ý nghĩa gì?

### Bài B — Nested mapping

Từ POJO `shippingAddress.city`, xác định JSON path và SQL++ expression cần dùng để query. Vì sao phải tôn trọng `@Field` alias?

### Bài C — Tiền chính xác

Vì sao `new BigDecimal(0.1)` không phù hợp? Viết test `2 × 12.30 + 1 × 1.40 = 26.00 USD`.

### Bài D — Currency conflict

Cho `Money(USD,12.30)` và `Money(VND,150000)`. Có được cộng trực tiếp không? Nếu cần FX conversion, cần những thông tin audit nào?

### Bài E — Converter hai chiều

Viết `MoneyToStringConverter` và `StringToMoneyConverter`, test malformed `USD|abc` và `USD|12.345`. Tại sao không default thành zero?

### Bài F — Thời điểm và offset

Viết hai timestamp cùng instant với offset khác nhau. Giải thích vì sao canonical UTC không giữ offset gốc và cách lưu `ZoneId` nếu cần.

### Bài G — Bean wiring

Custom converter unit test pass nhưng raw JSON vẫn là object; bạn cần kiểm tra những bean/configuration và đường write nào?

### Bài H — Legacy schema

Dữ liệu cũ có `unit_price={"currency":"USD","amount":12.3}`; bản mới mong đợi `"USD|12.30"`. Hãy thiết kế migration có fallback/rollback.

### Bài I — Array SQL++

Viết query tìm order chứa SKU BOOK001 dùng `ANY ... SATISFIES`; đề xuất index phù hợp và kiểm tra `EXPLAIN`.

### Bài J — Time range

Nếu UI chọn một ngày theo `Asia/Ho_Chi_Minh`, hãy dùng `ZoneId` tạo start/end instants rồi query `placed_at_epoch_ms`. Vì sao không hardcode +07 trong logic dùng cho mọi vùng?

### Bài K — CAS

Hai writers sửa các fields nested khác nhau nhưng dùng cùng CAS. Vì sao vẫn conflict? Chọn retry/merge strategy phù hợp.

### Bài L — Tiền trong analytics

Thiết kế JSON object có `currency` và `minor_units` để SQL++ sum/filter. Kiểm tra cách biểu diễn VND, USD và overflow.

### Bài M — Query freshness

Một KV `get` thấy order mới nhưng SQL++ `NOT_BOUNDED` chưa thấy. Đây có phải durability failure? Khi nào dùng `REQUEST_PLUS`?

### Bài N — Test fixture

Viết `@SpringBootTest` có cờ `RUN_CB_IT`, tạo nested order, đọc qua repository và SDK raw JSON, cleanup theo ID. Vì sao chỉ unit test converters chưa đủ?

### Bài O — Domain validation

Thêm luật không cho duplicate SKU trong một order và giới hạn tổng tiền. Phải đặt ở converter hay service? Vì sao?

### Bài P — Security

Thiết kế tenant isolation cho cả KV ID, SQL++ query và HTTP authorization; tại sao prefix ID không thay security policy?

## 36. Checklist nghiệm thu

- [ ] Lab Couchbase riêng, bucket/scope/collection được cấp đúng quyền.
- [ ] Spring Boot BOM/SDK/Spring Data version tương thích.
- [ ] Không có credential hoặc PII thật trong source/test data.
- [ ] Root `PurchaseOrderDocument` có `@Document`, `@Id`, `@Version`, `@Scope`, `@Collection`.
- [ ] Embedded POJOs không bị nhầm là documents độc lập.
- [ ] `@Field` aliases đúng với JSON contract và SQL++ paths.
- [ ] `items` là JSON array, `shipping_address` là JSON object.
- [ ] `Money` dùng `BigDecimal` và `Currency`, không dùng double.
- [ ] Scale và rounding policy rõ, không làm tròn ngầm.
- [ ] Không cộng các đơn vị tiền tệ khác nhau khi chưa có FX policy.
- [ ] `@WritingConverter` Money → String được register.
- [ ] `@ReadingConverter` String → Money được register.
- [ ] `OffsetDateTime` lưu UTC có parser/writer nhất quán.
- [ ] Kiểm tra việc canonical UTC không giữ original offset.
- [ ] `placed_at_epoch_ms` được sinh từ cùng instant với `placed_at`.
- [ ] Bean `CouchbaseCustomConversions` thực sự được mapping layer dùng.
- [ ] Unit test round-trip, malformed value, scale và currency mismatch pass khi chạy.
- [ ] Integration test đọc lại qua Repository/Template và raw SDK JSON pass khi chạy.
- [ ] Giá unitPrice trong nested array lưu đúng `USD|...`.
- [ ] Tổng tiền bằng phép cộng từng dòng cùng currency.
- [ ] Create-only không bị upsert overwrite đơn cùng ID.
- [ ] Update/confirm sử dụng CAS, không bỏ kiểm tra version.
- [ ] SQL++ nested path và ARRAY index được kiểm tra `EXPLAIN` trên lab.
- [ ] Không dùng SQL++ `NOT_BOUNDED` để kết luận KV insert chưa tồn tại.
- [ ] Không cố `SUM` trực tiếp trên field Money string.
- [ ] Có kế hoạch schema migration cho legacy nested formats.
- [ ] Lỗi converter không bị biến thành zero hoặc che bằng catch-all.
- [ ] DTO/Controller không lộ raw entity, CAS dưới dạng JSON number hoặc PII tùy ý.
- [ ] Tenant authorization áp dụng trên cả read/write/query.
- [ ] Metrics nhận diện conversion, CAS, KV và Query errors riêng.
- [ ] Không tự thao tác production để chạy thí nghiệm, build/test thuộc bước thực thi sau.

## 37. Tổng kết

**Spring Data Couchbase ánh xạ một document JSON lồng nhau thành một object graph Java**, với `@Document`/`@Id`/`@Version` ở root và các POJO embedded nằm trong cùng aggregate. `@Field` giúp đổi tên JSON keys, còn `@Scope`/`@Collection` chọn đúng keyspace. Một KV insert/replace của root áp dụng cho cả nested object/array, trong khi CAS giúp phát hiện ghi đè cạnh tranh.

Custom converters là cầu nối khi domain type không phù hợp trực tiếp với JSON storage schema. Bài dùng `Money(BigDecimal, Currency)` lưu thành string canonical `"USD|12.30"`, và `OffsetDateTime` lưu theo UTC ISO-8601. Để đúng, phải có **cả writing và reading converters**, đăng ký ở `CouchbaseCustomConversions`, giữ format deterministic và **kiểm thử raw JSON lẫn round-trip entity**. Không dùng double hoặc default giá lỗi thành zero.

Một schema dùng chuỗi Money dễ bảo toàn decimal nhưng không thích hợp cho numeric SQL++ aggregation; thời gian UTC string bảo vệ instant nhưng không giữ offset người dùng và có thể cần epoch field để query range. Việc chọn định dạng phải dựa vào **nghiệp vụ, truy vấn, precision, migration và vận hành**, không chỉ vào khả năng serialize.

## Tài liệu tham khảo chính thức

1. [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Document`, `@Id`, `@Field`, `@Version` và mapping rules.
2. [Spring Data Couchbase — Collection Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): `@Scope`, `@Collection` và keyspace selection.
3. [Spring Data Couchbase — Template and Direct Operations](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): KV insert/find/replace, operation overrides.
4. [Spring Data Couchbase — CouchbaseCustomConversions API](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/core/convert/CouchbaseCustomConversions.html): cấu hình converters.
5. [Spring Data Commons — ReadingConverter](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/convert/ReadingConverter.html): hướng đọc từ store.
6. [Spring Data Commons — WritingConverter](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/convert/WritingConverter.html): hướng ghi ra store.
7. [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): document ID, CAS, mutation options và raw JsonObject.
8. [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): Index Service/Query Service và consistency.
9. [Couchbase Server — SQL++ Array Indexing](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/indexing-arrays.html): `ANY`, `UNNEST` và array indexes.
10. [Spring Boot — Couchbase Configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html): application properties và auto-configuration.
11. [Java SE — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): precision, scale, rounding.
12. [Java SE — OffsetDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/OffsetDateTime.html): UTC offset và absolute instant.

**Phạm vi:** STEP 4 là viết Markdown và kiểm tra ghi/đọc kỹ thuật. Snippets Java/JUnit/SQL++ chưa được build hoặc chạy trên cluster thật. Cần kiểm chứng đúng SDK/Spring Data/Server versions, converter bean wiring, legacy compatibility và security trước khi áp dụng; vòng Content QA/refactor chuyên môn thuộc STEP 6 riêng.







# Kiểm thử đọc–ghi đối xứng cùng dữ liệu từ phiên bản cũ

> **Chương:** Chuyển đổi dữ liệu  
> **Module:** `SPRING_DATA_MONGODB`

Một ứng dụng có thể đọc và ghi MongoDB ổn định trong phiên bản hiện tại nhưng vẫn lỗi khi mở những document được lưu từ nhiều năm trước. Ví dụ: phiên bản cũ lưu số tiền dưới dạng chuỗi `"129.50"`; phiên bản mới dùng BSON `Decimal128`. Nếu bài kiểm thử chỉ tạo object mới, gọi `save()` rồi `findById()`, cả hai thao tác đều đi qua cùng quy tắc chuyển đổi mới và có thể **không phát hiện** dữ liệu cũ đã mất khả năng đọc.

Vì thế, **kiểm thử đọc–ghi đối xứng** (*round-trip testing*) cần được kết hợp với **kiểm thử tương thích ngược bằng dữ liệu phiên bản cũ** (*legacy fixture / golden data*). Ta kiểm tra cả ba câu hỏi: dữ liệu cũ còn đọc đúng không, đối tượng mới có ghi theo định dạng đích không, và dữ liệu sau khi ghi có đọc lại đúng ngữ nghĩa không.

Bài nằm trong module `SPRING_DATA_MONGODB`: sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác qua `MongoTemplate` hoặc repository. Các kết quả kiểm thử này cũng là nền tảng trước khi thay đổi truy vấn, aggregation, index, transaction, reactive access hoặc chẩn đoán hiệu năng trong một hệ thống có dữ liệu thực.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt round-trip theo **đối tượng**, round-trip theo **BSON** và kiểm thử **tương thích dữ liệu cũ**.
2. Tạo fixture MongoDB chứa kiểu BSON đúng như phiên bản đã triển khai trước đó, không vô tình tái tạo fixture qua converter hiện tại.
3. Xây dựng `@ReadingConverter` và `@WritingConverter` khi kiểu lưu trữ đã đổi; đăng ký converter cho `MappingMongoConverter`.
4. Kiểm tra tính tương đương về **ngữ nghĩa** thay vì luôn so sánh hai document nguyên trạng bằng `equals`.
5. Phát hiện nguy cơ mất field khi `save`, thay đổi `_id`/`_class`, sai thời gian, sai kiểu số, không tương thích query/index và migration không lặp lại an toàn.

## 2. Định nghĩa chính xác các loại kiểm thử

Gọi:

- `R₂`: thao tác đọc BSON thành model Java của phiên bản 2.
- `W₂`: thao tác ghi model Java thành BSON của phiên bản 2.
- `L₁`: BSON đã thực sự được ghi bằng phiên bản 1.
- `x`: một object hợp lệ của model hiện hành.
- `≈`: tương đương theo **hợp đồng nghiệp vụ**, có thể bỏ qua các khác biệt đã được chấp nhận như field metadata, thứ tự field và độ chính xác dưới mili giây.

Cần xác minh các quan hệ sau:

```text
(A) Round-trip đối tượng mới:
    R₂(W₂(x)) ≈ x

(B) Đọc dữ liệu phiên bản cũ:
    R₂(L₁) = trạng thái nghiệp vụ được mong đợi

(C) Chuyển dữ liệu cũ sang cách ghi mới:
    R₂(W₂(R₂(L₁))) ≈ R₂(L₁)

(D) Ghi canonical lặp lại (khi có yêu cầu):
    W₂(R₂(W₂(R₂(L₁)))) ≈ W₂(R₂(L₁))
```

**Không nên yêu cầu** `W₂(R₂(L₁)) == L₁` theo từng byte hoặc toàn bộ field: phiên bản mới có thể chuẩn hóa kiểu BSON, đổi thứ tự field, bổ sung `_class`, bỏ field legacy hoặc đặt tên field mới. Mục tiêu là giữ **đúng ý nghĩa** và biết rõ những thay đổi định dạng nào là có chủ đích.

| Phép kiểm tra | Đầu vào | Điều phát hiện |
| --- | --- | --- |
| New round-trip | Object Java tạo bằng model mới | Lỗi converter đọc/ghi và precision trong phiên bản mới |
| Legacy read | BSON nguyên trạng từ hệ cũ | Không đọc được kiểu cũ, sai default hoặc mất trường |
| Legacy → canonical → read | BSON cũ, ghi lại bằng writer mới | Đổi kiểu BSON sai, dữ liệu bị làm tròn hoặc mất ngữ nghĩa |
| Query compatibility | Document cũ và mới cùng collection | Điều kiện `find`, sort, index hoặc aggregation cho kết quả khác |
| Full persistence test | MongoDB thật/isolated test instance | Hành vi `save`, ID, callback, auditing, optimistic locking, codec/driver |

Một bộ kiểm thử chất lượng cần cả kiểm thử converter ở mức bộ nhớ và kiểm thử tích hợp với MongoDB; hai lớp này bổ sung cho nhau.

## 3. Tình huống xuyên suốt: từ số tiền dạng chuỗi sang Decimal128

Giả sử phiên bản cũ của hệ thống hóa đơn lưu:

```javascript
// v1: kiểu lưu trữ cũ.
{
  _id: "INV-2024-001",
  status: "PAID",
  total: "129.50",                  // BSON String
  paid_at: ISODate("2024-06-01T02:30:00.123Z"),
  legacy_note: "import-batch-07"    // field cũ model mới không còn
}
```

Phiên bản mới muốn lưu `total` bằng **BSON Decimal128**, giữ `_id` ổn định, vẫn lưu `paid_at` là BSON Date và có model Java bất biến:

```javascript
// v2: định dạng đích.
{
  _id: "INV-2024-001",
  status: "PAID",
  total: NumberDecimal("129.50"),  // BSON Decimal128
  paid_at: ISODate("2024-06-01T02:30:00.123Z")
}
```

Hai document **khác BSON type** nhưng cùng mang ý nghĩa hóa đơn đã thanh toán 129,50 đơn vị tiền với thời điểm `2024-06-01T02:30:00.123Z`. Mục tiêu kiểm thử là chắc chắn phiên bản mới hiểu dữ liệu v1 và ghi đúng quy ước v2.

### 3.1. Vì sao chọn Decimal128?

Sử dụng `double` cho tiền có thể làm phát sinh sai số dấu phẩy động. Nếu nghiệp vụ hỗ trợ giá trị thập phân, `Decimal128` là lựa chọn lưu trữ có độ chính xác thập phân được xác định; cũng có thể lưu số nguyên đơn vị nhỏ nhất tùy miền nghiệp vụ. Phải **chọn một hợp đồng duy nhất** cho từng field.

Với `BigDecimal`, khả năng mapping mặc định sang BSON có thể khác theo phiên bản Spring Data MongoDB; không nên phụ thuộc giả định “framework luôn lưu BigDecimal thành Decimal128”. Ở ví dụ này, ta **đăng ký converter tường minh** để kiểm soát giá trị BSON đích.

### 3.2. Quyết định về field cũ trước khi viết test

Field `legacy_note` minh họa một vấn đề khác với chuyển đổi số tiền: liệu thông tin cũ có cần được bảo toàn khi ứng dụng mới ghi đè hóa đơn?

- Nếu không cần giữ, có thể chuyển hoặc xóa field đó **có kế hoạch** trong migration.
- Nếu bắt buộc giữ, phải đưa vào model/đường ghi hoặc dùng update có chọn lọc thay vì viết lại toàn bộ document.
- Nếu chưa có quyết định nghiệp vụ, **không được coi việc field bị mất là “round-trip thành công”** chỉ vì số tiền vẫn đúng.

Hợp đồng kiểm thử nên tách rõ **dữ liệu phải giữ**, **dữ liệu có thể chuẩn hóa** và **dữ liệu được phép loại bỏ**.

## 4. Model Java hiện hành

Ta dùng một value object `Money` để làm rõ quy tắc chuyển đổi và tránh xử lý chuỗi tiền ở mọi service.

File `Money.java`:

```java
package com.example.invoice;

import java.math.BigDecimal;
import java.util.Objects;

public record Money(BigDecimal value) {
    public Money {
        Objects.requireNonNull(value, "value");
    }
}
```

File `Invoice.java`:

```java
package com.example.invoice;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "invoices")
public record Invoice(
    @Id String id,
    String status,
    @Field("total") Money total,
    @Field("paid_at") Instant paidAt
) {}
```

Ở đây `Money` đại diện một số tiền đã được xác định đơn vị/tiền tệ theo quy ước của bài. Hệ thống thực tế cần thêm đồng tiền (`currency`) hoặc tên đơn vị, tránh cộng trừ các đồng tiền không cùng loại. Hệ thống cũng cần kiểm tra giới hạn, thang số (`scale`) và điều kiện âm/dương theo nghiệp vụ; các quy tắc đó không được tự ý suy từ định dạng BSON.

Định danh `"INV-2024-001"` không có dạng 24 ký tự hex, nên Spring Data sẽ không nhầm nó với chuỗi ObjectId hợp lệ. Với ID có thể biểu diễn dưới dạng ObjectId, phải kiểm tra rõ kiểu BSON `_id` đã tồn tại và cách annotation `@Id` chuyển đổi.

## 5. Converter đọc cũ, đọc mới và ghi chuẩn

Tạo **hai converter đọc** để hỗ trợ giá trị `total` ở cả dạng BSON String và Decimal128, cùng **một converter ghi** cho v2.

### 5.1. Đọc số tiền từ BSON String phiên bản cũ

File `LegacyMoneyReadConverter.java`:

```java
package com.example.invoice;

import java.math.BigDecimal;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class LegacyMoneyReadConverter
        implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        return new Money(new BigDecimal(source));
    }
}
```

`BigDecimal(String)` giữ giá trị thập phân chính xác của chuỗi như `"129.50"`. Dữ liệu thiếu hợp lệ (`"N/A"`, ký hiệu tiền tệ, dấu phẩy không thống nhất) sẽ phát sinh lỗi và cần chính sách rõ ràng: fail-fast, ghi nhận vào danh sách lỗi migration hoặc dùng parser được chuẩn hóa theo nguồn. Không nên âm thầm trả `BigDecimal.ZERO` cho dữ liệu không đọc được.

### 5.2. Đọc BSON Decimal128 phiên bản mới

File `DecimalMoneyReadConverter.java`:

```java
package com.example.invoice;

import org.bson.types.Decimal128;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class DecimalMoneyReadConverter
        implements Converter<Decimal128, Money> {

    @Override
    public Money convert(Decimal128 source) {
        return new Money(source.bigDecimalValue());
    }
}
```

Không phải mọi giá trị Decimal128 đều chuyển được thành `BigDecimal` hữu hạn theo cách này: ví dụ NaN/Infinity cần quy tắc xử lý riêng. Khi hệ thống chỉ chấp nhận giá trị tiền hữu hạn, nên để dữ liệu không hợp lệ bị phát hiện trong kiểm thử thay vì tự biến đổi thành số khác.

### 5.3. Ghi theo định dạng v2

File `MoneyWriteConverter.java`:

```java
package com.example.invoice;

import org.bson.types.Decimal128;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyWriteConverter
        implements Converter<Money, Decimal128> {

    @Override
    public Decimal128 convert(Money source) {
        return new Decimal128(source.value());
    }
}
```

Nếu `BigDecimal` có độ chính xác hoặc số mũ vượt phạm vi Decimal128, thao tác tạo `Decimal128` có thể không thành công. Đó là lý do cần thêm test giá trị biên và kiểm tra độ chính xác trước khi lưu.

### 5.4. Đăng ký converter đúng cách

Annotation `@ReadingConverter` và `@WritingConverter` khai báo **hướng chuyển đổi**, nhưng các class converter **không tự được Spring Data đăng ký chỉ nhờ component scan**. Đăng ký các instance trong `MongoCustomConversions`:

```java
package com.example.invoice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

@Configuration(proxyBeanMethods = false)
public class MoneyMongoConversionConfig {

    @Bean
    MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(adapter -> {
            adapter.registerConverter(new LegacyMoneyReadConverter());
            adapter.registerConverter(new DecimalMoneyReadConverter());
            adapter.registerConverter(new MoneyWriteConverter());
        });
    }
}
```

Với ứng dụng Spring Boot sử dụng cấu hình MongoDB tự động thông thường, bean `MongoCustomConversions` có thể được Spring Data/Boot dùng để xây `MappingMongoConverter`. Nếu dự án đã khai báo bean conversions, mapping converter hoặc `MongoTemplate` tùy chỉnh, phải **gộp** các converter vào cấu hình đang có và xác minh template thực tế sử dụng chúng. Không tạo bean mới tùy tiện khiến các converter khác bị mất.

Một hướng khác khi dùng cấu hình thuần Spring Data là đăng ký qua `AbstractMongoClientConfiguration.configureConverters(...)`. API cụ thể và chiến lược auto-configuration cần đối chiếu với phiên bản dependency dự án.

## 6. Kiểm thử trong bộ nhớ với MappingMongoConverter

Đây là vòng kiểm thử rẻ, nhanh và có giá trị để phát hiện những lỗi mapping cơ bản. Nó dùng `MongoConverter.read(...)` và `write(...)` trực tiếp trên `org.bson.Document`, **không gọi MongoDB server**. Dưới đây là ví dụ dùng Spring Boot Test slice để lấy đúng converter của ứng dụng.

### 6.1. Tạo legacy fixture đúng kiểu BSON

Trong Java:

```java
package com.example.invoice;

import java.time.Instant;
import java.util.Date;
import org.bson.Document;

public final class LegacyInvoiceFixtures {
    private LegacyInvoiceFixtures() {}

    public static Document invoiceV1() {
        return new Document("_id", "INV-2024-001")
            .append("status", "PAID")
            .append("total", "129.50")
            .append(
                "paid_at",
                Date.from(Instant.parse("2024-06-01T02:30:00.123Z"))
            )
            .append("legacy_note", "import-batch-07");
    }
}
```

Ở fixture này, `total` thật sự là Java String để driver lưu BSON String, còn `paid_at` là `java.util.Date` nên mã hóa thành BSON Date. Fixture **không được tạo bằng `Invoice` và converter v2**, vì làm như vậy sẽ bỏ qua chính định dạng cũ cần kiểm tra.

Trong dự án thực tế, nên lấy thêm các trường hợp đại diện từ bản ghi đã được ghi bởi ứng dụng cũ (đã ẩn danh dữ liệu nhạy cảm), lưu kèm phiên bản schema và lý do tồn tại của từng mẫu. Không chỉ tạo fixture theo trí nhớ về hệ thống cũ.

### 6.2. Kiểm tra ba thuộc tính: đọc cũ, ghi chuẩn, đọc lại

```java
package com.example.invoice;

import java.math.BigDecimal;
import java.time.Instant;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
@Import(MoneyMongoConversionConfig.class)
class InvoiceConverterCompatibilityTest {

    @Autowired
    MongoTemplate template;

    @Test
    void readsLegacyAndWritesCanonicalDecimal128() {
        Document legacy = LegacyInvoiceFixtures.invoiceV1();

        Invoice restored = template.getConverter()
            .read(Invoice.class, legacy);

        assertThat(restored.id()).isEqualTo("INV-2024-001");
        assertThat(restored.status()).isEqualTo("PAID");
        assertThat(restored.total().value())
            .isEqualByComparingTo(new BigDecimal("129.50"));
        assertThat(restored.paidAt()).isEqualTo(
            Instant.parse("2024-06-01T02:30:00.123Z"));

        Document canonical = new Document();
        template.getConverter().write(restored, canonical);

        assertThat(canonical.get("total"))
            .isInstanceOf(Decimal128.class);
        assertThat(canonical.get("legacy_note")).isNull();
        assertThat(canonical.get("paid_at"))
            .isInstanceOf(java.util.Date.class);

        Invoice secondRead = template.getConverter()
            .read(Invoice.class, canonical);
        assertThat(secondRead).isEqualTo(restored);
    }
}
```

Trong mẫu này, sự vắng mặt của `legacy_note` ở canonical chỉ là **quan sát về model ví dụ**; không phải một yêu cầu chung rằng hệ thống được phép xóa field cũ. Nếu `legacy_note` phải được giữ, cần sửa model hoặc đường cập nhật và thay assertion tương ứng.

Để chạy `@DataMongoTest`, project phải có các dependency test phù hợp và cấu hình MongoDB test instance khi test context cần kết nối. Riêng hai lệnh `read`/`write` trên converter không cần server phản hồi, nhưng Spring test context có thể vẫn khởi tạo MongoDB infrastructure. Kiểm thử bằng bộ nhớ này **chưa** xác minh hành vi persistence hoặc lifecycle callback của `save`.

### 6.3. Kiểm tra round-trip theo ngữ nghĩa thay vì hình dạng thô

Với dữ liệu v1:

- `legacy.get("total")` là `String`.
- `canonical.get("total")` phải là `Decimal128`.
- `restored.total().value()` và giá trị sau vòng đọc lại phải bằng nhau về số.
- `_id` và `paid_at` phải mang cùng giá trị định danh/thời điểm.

So sánh hai `Document` bằng `equals` sẽ thất bại có chủ đích vì `String("129.50")` khác `Decimal128("129.50")`. Test nên so sánh **ngữ nghĩa đã xác định**. Với `BigDecimal`, có thể dùng `compareTo`/AssertJ `isEqualByComparingTo` nếu quy tắc nghiệp vụ coi `129.5` và `129.50` là cùng số; nếu scale có ý nghĩa trong hóa đơn, cần assert cả scale.

## 7. Kiểm thử tích hợp: chèn dữ liệu cũ qua driver rồi đọc bằng Spring Data

Đây là bước quan trọng vì converter thuần không kiểm tra toàn bộ đường đi từ server, BSON codec, transaction, callback và cơ chế `save`.

### 7.1. Seed bằng API driver thay vì repository

Repository hiện hành sẽ ghi theo **quy ước v2**. Để mô phỏng dữ liệu thực sự đã lưu trước khi nâng cấp, chèn fixture bằng MongoDB Java driver:

```java
package com.example.invoice;

import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
@Import(MoneyMongoConversionConfig.class)
class InvoiceDatabaseCompatibilityTest {

    @Autowired
    MongoTemplate template;

    @Test
    void canReadLegacyFromMongoAndPersistInNewFormat() {
        var collection = template.getCollection("invoices");
        Document legacy = LegacyInvoiceFixtures.invoiceV1();
        collection.insertOne(legacy);

        // Đọc đường truy cập thật của ứng dụng:
        Invoice current = template.findById(
            "INV-2024-001", Invoice.class);

        assertThat(current).isNotNull();
        assertThat(current.total().value())
            .isEqualByComparingTo(new BigDecimal("129.50"));

        // Trong database TEST cô lập: save ghi lại entity v2.
        template.save(current);

        Document stored = collection.find(
            new Document("_id", "INV-2024-001")).first();

        assertThat(stored).isNotNull();
        assertThat(stored.get("total"))
            .isInstanceOf(Decimal128.class);
        assertThat(stored.get("_id"))
            .isEqualTo("INV-2024-001");

        Invoice loadedAgain = template.findById(
            "INV-2024-001", Invoice.class);
        assertThat(loadedAgain).isEqualTo(current);
    }
}
```

**Chạy test này trên MongoDB dành riêng cho kiểm thử**, chẳng hạn instance Testcontainers được cấu hình cho Spring test context, không trỏ vào database thật. Trong suite hoàn chỉnh, nên có định danh duy nhất và cleanup để hai lần chạy độc lập không đụng vào nhau.

`template.save(current)` trên document đã tồn tại có thể ghi thay thế document theo representation của model mới. Vì `Invoice` không ánh xạ `legacy_note`, field đó có nguy cơ **biến mất** sau `save`. Đây là behavior phải kiểm tra riêng; mẫu test trên tập trung vào chuyển đổi `total` và vẫn chưa khẳng định việc xóa field cũ là an toàn.

### 7.2. Nếu cần giữ các field không biết đến

Khi chính sách yêu cầu giữ `legacy_note` hoặc các field do dịch vụ khác ghi, một cách là cập nhật **chỉ field cần đổi**:

```java
import org.bson.types.Decimal128;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public void normalizeTotalField(
        MongoTemplate template, String invoiceId,
        String legacyTotal) {
    Decimal128 newTotal = new Decimal128(
        new java.math.BigDecimal(legacyTotal));

    template.updateFirst(
        Query.query(Criteria.where("_id").is(invoiceId)),
        new Update().set("total", newTotal),
        "invoices"
    );
}
```

Đặt phương thức minh họa này trong một class service/utility phù hợp. Trong hệ thống thật, việc lấy `legacyTotal` từ ngoài cần đối chiếu với trạng thái mới nhất trong database để tránh **ghi đè một giá trị vừa được cập nhật đồng thời**. Có thể dùng điều kiện so khớp giá trị/phiên bản cũ, điều khiển concurrency, transaction hoặc migration worker tuần tự theo yêu cầu.

Phương thức trên chỉ cập nhật `total` và giữ các field khác của document, nhưng nó cũng **bỏ qua một số callback và cơ chế ánh xạ toàn entity** so với `save`. Vì vậy cần test đúng đường cập nhật được chọn.

### 7.3. Repository có thể kiểm tra cùng hợp đồng

Nếu đã có:

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface InvoiceRepository
        extends MongoRepository<Invoice, String> {}
```

ta có thể kiểm tra cả `repository.findById("INV-2024-001")` và `repository.save(invoice)`. Repository và `MongoTemplate` có thể dùng cùng mapping infrastructure, nhưng query derivation, callback, optimistic locking và cách viết update cần được xác minh theo đường truy cập **ứng dụng thực sự sử dụng**.

## 8. Các dạng không đối xứng cần quyết định trước

Không phải mọi khác biệt đều là bug. Quan trọng là phân loại:

| Biến đổi | Có thể chấp nhận khi nào? | Kiểm thử cần có |
| --- | --- | --- |
| `"129.50"` (String) → `Decimal128("129.50")` | Đã quyết định chuẩn hóa kiểu tiền | BSON đích đúng type; giá trị số không đổi |
| `Instant` nanosecond → BSON Date millisecond | Độ phân giải mili giây được cho phép | So sánh sau chuẩn hóa/truncate, không đòi giữ nanosecond |
| `@Id String` ↔ BSON ObjectId | ID cũ thực sự theo quy ước ObjectId | Kiểm tra kiểu `_id` và đường query ID với cả hai dạng |
| Thiếu field `status` cũ → giá trị mặc định | Default nghiệp vụ được xác nhận | Assert dữ liệu thiếu và dữ liệu `null` riêng rẽ |
| Enum `PENDING_APPROVAL` cũ đổi thành `WAITING` | Có mapping tương thích đã định nghĩa | Từng giá trị enum cũ và không biết trước |
| `_class` FQCN cũ → alias mới | Reader biết cách giải cả dữ liệu cũ và mới | Tải root/nested subtype, cả sau khi restart |
| `legacy_note` biến mất | Chính sách cho phép loại bỏ | Assert chủ đích, không để mất âm thầm |
| `LocalDateTime` cũ → `Instant` mới | Múi giờ nguồn của dữ liệu cũ xác định được | Kiểm thử offset, DST và các giá trị mơ hồ |

### 8.1. Số và độ chính xác

Giả sử v1 dùng `double` hoặc chuỗi chứa nhiều chữ số. Việc chuyển sang `Decimal128` không thể phục hồi những chữ số đã mất vì v1 lưu dưới dạng nhị phân dấu phẩy động. Bài test phải xác định giá trị kỳ vọng theo **thực tế lưu trữ**, không giả định mọi sai số lịch sử đều được sửa.

Với số nguyên `int` sang `long`, cần kiểm tra giá trị lớn hơn giới hạn 32 bit khi ghi v2 và đọc BSON `Int32` cũ. Với tiền, tránh tự động convert một giá trị chuỗi sai định dạng thành `0`.

### 8.2. Thời gian

BSON Date lưu epoch milliseconds UTC. Nếu v1 lưu `paid_at` là BSON Date, mapping `Instant` có thể giữ cùng thời điểm với độ phân giải mili giây. Nếu v1 lưu chuỗi giờ địa phương thiếu timezone, không thể chuyển thành instant chính xác nếu thiếu thông tin vùng địa lý/múi giờ nguồn.

Lưu ý đặc biệt với `LocalDateTime`: converter mặc định của Spring Data cho kiểu local có thể dùng timezone mặc định của máy, còn driver Java Time codec có quy tắc UTC. Đổi cấu hình codec/converter có thể làm **cùng BSON Date được diễn giải khác**. Test phải chạy với timezone khác nhau hoặc ít nhất khóa quy ước chuyển đổi trong code.

### 8.3. Null, field bị thiếu và field không còn tồn tại

Trong BSON, ba trạng thái sau có thể có ý nghĩa nghiệp vụ khác nhau:

```javascript
// Field không được ghi:
{ _id: "A" }

// Field hiện diện với BSON null:
{ _id: "B", discountCode: null }

// Field chứa chuỗi rỗng:
{ _id: "C", discountCode: "" }
```

Không nên gộp ba trường hợp trước khi biết ý nghĩa nghiệp vụ. Đối với Java primitive như `long`, giá trị thiếu có thể thành mặc định hoặc gây lỗi theo cách mapping/constructor; sử dụng wrapper `Long` hoặc value object có validation thường giúp phát hiện dữ liệu thiếu rõ hơn. Test cả trường hợp thiếu, `null`, rỗng, giá trị sai kiểu.

### 8.4. _class và kế thừa

Nếu các document cũ có `_class: "com.old.package.InvoiceEvent"` nhưng package Java mới đã bị đổi, alias hoặc class mapping mới **không tự động bảo đảm** đọc được mọi chuỗi type hint cũ. Test cần có fixture root và nested với type hint thực tế; nếu cần có converter/migration hoặc tương thích lớp cũ, phải lập kế hoạch riêng.

## 9. Ma trận fixture theo phiên bản

Thay vì chỉ dùng một document “đẹp”, hãy lập tập fixture có nguồn gốc và kỳ vọng cụ thể:

| Fixture | BSON cũ | Kỳ vọng ở phiên bản mới |
| --- | --- | --- |
| `invoice-v1-string-total` | `total` là String, `paid_at` là Date | Đọc thành `Money`, ghi lại thành Decimal128 |
| `invoice-v2-decimal-total` | `total` là Decimal128 | Đọc/ghi không đổi giá trị |
| `invoice-v1-missing-status` | Thiếu `status` | Xử lý theo default/validation được định nghĩa |
| `invoice-v1-invalid-total` | `total: "N/A"` | Lỗi được phát hiện và chẩn đoán; không đổi thành 0 |
| `invoice-v1-unknown-field` | Có `legacy_note` | Bảo toàn hoặc loại bỏ theo chính sách đã thống nhất |
| `invoice-v1-old-class` | `_class` là FQCN cũ | Mapping được hoặc có migration có thể kiểm chứng |
| `invoice-v1-timezone` | Chuỗi local date-time, không offset | Chỉ chuyển khi biết timezone nguồn; không tự đoán |
| `invoice-v2-extreme-amount` | Giá trị sát giới hạn Decimal128 | Quy định xử lý chính xác hoặc từ chối |

Nên lưu các fixture cùng test code ở dạng Extended JSON đã ghi rõ kiểu (`$numberDecimal`, `$date`, `$oid`...) hoặc xây dựng bằng `Document`/kiểu BSON Java như ví dụ. Dữ liệu lấy từ production phải được ẩn danh, bỏ secrets và bảo đảm không chứa thông tin cá nhân.

**Golden fixture phải bất biến theo phiên bản:** nếu test đang xác nhận v1 vẫn đọc được, không sửa fixture v1 cho phù hợp converter v2 chỉ để test xanh. Khi định dạng thay đổi, **thêm** fixture và expectation mới; giữ những fixture lịch sử vẫn thuộc phạm vi hỗ trợ.

## 10. Migration: đọc hai dạng, ghi một dạng

Một chiến lược nâng cấp thường an toàn hơn là **reader tương thích nhiều phiên bản, writer chỉ ghi định dạng mới**.

```text
Trong giai đoạn chuyển tiếp

             ┌── BSON v1 (String total) ──┐
MongoDB ─────┤                             ├── Reader v2 ──> Invoice
             └── BSON v2 (Decimal128) ────┘                     │
                                                               ▼
                                                      Writer v2
                                                               │
                                                               ▼
                                                      BSON v2 (Decimal128)
```

Quy trình triển khai gợi ý:

1. **Thống kê dữ liệu cũ:** các kiểu BSON, null/missing, `_class`, ID, thời gian và phân bố giá trị.
2. **Chốt hợp đồng canonical:** tên field, kiểu BSON, ý nghĩa, scale và cách xử lý dữ liệu không hợp lệ.
3. **Triển khai reader hỗ trợ cả v1 và v2:** kiểm tra bằng golden fixtures và test integration.
4. **Triển khai writer v2:** bảo đảm mọi bản ghi mới được tạo ở định dạng mới.
5. **Migration từng nhóm:** nếu cần chuẩn hóa dữ liệu cũ, dùng tiến trình có checkpoint, log kết quả và chạy lại an toàn.
6. **Đối soát:** so sánh số document, tổng tiền hợp lệ, lỗi parse, dữ liệu còn dạng cũ và truy vấn nghiệp vụ.
7. **Thu hẹp hỗ trợ legacy:** chỉ bỏ converter v1 sau khi dữ liệu phù hợp đã được chuyển hết và các ứng dụng cũ không còn chạy.

Khi có nhiều instance chạy song song trong lúc rolling deployment, cần nghĩ đến **writer v2 và reader v1 tồn tại đồng thời**. “Ứng dụng mới đọc được dữ liệu cũ” không đồng nghĩa “ứng dụng cũ đọc được dữ liệu mới”. Nếu cần cả hai chiều, hãy thiết kế trình tự rollout, dual-write/feature flag hoặc duy trì định dạng cũ trong giai đoạn chuyển tiếp.

### 10.1. Thống kê BSON type trước khi migration

```javascript
db.invoices.aggregate([
  {
    $group: {
      _id: { $type: "$total" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
```

Đếm các dạng `string`, `decimal`, `null`, `missing` và kiểu khác giúp xác định dữ liệu nào cần chuyển. Nên thống kê thêm giá trị lỗi và phiên bản schema nếu có.

### 10.2. Xem trước khả năng chuyển dữ liệu bằng aggregation chỉ đọc

```javascript
db.invoices.aggregate([
  { $match: { total: { $type: "string" } } },
  {
    $project: {
      total: 1,
      candidateDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $limit: 50 }
])
```

Đây là **pipeline đọc** để khảo sát; nếu `candidateDecimal` là null với một giá trị chuỗi khác null, cần kiểm tra lý do parse thất bại. Trong migration thật, không nên bỏ qua những giá trị bị lỗi vì chúng làm thay đổi tổng hợp tiền.

### 10.3. Chạy lại an toàn (idempotency)

Một migration chuyển chuỗi thành Decimal128 chỉ nên tác động đến document có `total` kiểu String và cần có kết quả kiểm đếm. Nếu chạy lại sau khi hoàn tất, số document phù hợp điều kiện sẽ bằng 0; không được nhân đôi số tiền hoặc thay đổi bản ghi đã chuyển.

Đối với update có thể xảy ra đồng thời với ứng dụng, cần thiết kế điều kiện CAS/`@Version` hoặc chiến lược khóa/trình tự phù hợp. Transaction có thể hữu ích khi thay đổi nhiều document phải nhất quán, nhưng không tự giải quyết việc parser hiểu sai định dạng legacy.

## 11. Kiểm thử truy vấn và aggregation sau khi đổi kiểu BSON

Một hệ thống có thể đọc đúng từng hóa đơn nhưng **báo cáo bị sai** khi collection còn lẫn String và Decimal128. Ví dụ:

```javascript
db.invoices.find({
  total: { $gte: NumberDecimal("100.00") }
})
```

Đừng giả định truy vấn số sẽ xử lý chuỗi `"129.50"` như số 129,50. MongoDB so sánh theo BSON type và quy tắc type bracketing, còn sort trên chuỗi có thể theo thứ tự từ điển. Một truy vấn dựa trên Decimal128 có thể không chọn được những document vẫn giữ String.

Các phép kiểm tra phải có:

- **Filter:** một hóa đơn cũ và một hóa đơn mới cùng số tiền có xuất hiện cùng kết quả nghiệp vụ không?
- **Sort:** thứ tự lớn–nhỏ của tổng tiền có đúng khi dữ liệu gồm nhiều kiểu?
- **Aggregation:** `$sum` và các toán tử số có bỏ qua/làm lệch phần dữ liệu cũ không?
- **Index:** index có phục vụ đúng filter/range sau khi chuyển kiểu không? Có cần rebuild/thay đổi thiết kế index?
- **Query mapping:** tiêu chí Java theo value object `Money` có được custom converter chuyển thành giá trị BSON đúng không?

Trong giai đoạn trộn định dạng, có thể tạm chuẩn hóa bằng aggregation có xử lý lỗi hoặc giới hạn rõ các query nào đọc dữ liệu cũ. Không nên quảng bá kết quả thống kê là chính xác nếu vẫn còn document không thể quy đổi và chưa được đối soát.

Thử `explain("executionStats")` trên truy vấn đại diện sau migration, theo dõi `totalDocsExamined`, `totalKeysExamined` và số record trả về. Converter tương thích ngược giải quyết ánh xạ object, nhưng không tự tối ưu hoặc sửa logic aggregation phía database.

## 12. Tương thích với repository, reactive access và transaction

`MongoRepository` và `MongoTemplate` thường dùng cùng metadata mapping và custom conversions của ApplicationContext. Vì thế lỗi chuyển đổi có thể ảnh hưởng cả hai, nhưng không phải mọi đường thao tác đều chạy giống nhau: partial update, aggregation result mapping, raw driver và query projection có thể đi qua các bước khác nhau.

### 12.1. Raw driver không tự chạy Spring converter

Lệnh:

```java
template.getCollection("invoices")
    .insertOne(LegacyInvoiceFixtures.invoiceV1());
```

đi qua MongoDB Java driver để ghi BSON, **không** gọi `MoneyWriteConverter` vì đầu vào là `Document`. Đây chính là điều mong muốn khi seed legacy fixture. Ngược lại:

```java
template.insert(new Invoice(
    "INV-NEW-001",
    "PAID",
    new Money(new java.math.BigDecimal("129.50")),
    java.time.Instant.parse("2026-11-20T02:00:00Z")
));
```

đi qua mapping của Spring Data, nên `MoneyWriteConverter` phải xuất ra Decimal128. Hai đường ghi cần có test phân biệt.

### 12.2. Reactive access

Nếu dự án dùng `ReactiveMongoTemplate`/`ReactiveMongoRepository`, nguyên tắc tương thích BSON không đổi. Test reactive cần đăng ký cùng chiến lược chuyển đổi và xác nhận publisher thực sự được subscribe (ví dụ bằng `StepVerifier`):

```java
// Khi đã có ReactiveMongoTemplate reactiveTemplate,
// Invoice fixture theo thiết kế bên trên và kết nối test phù hợp:
StepVerifier.create(
    reactiveTemplate.findById("INV-2024-001", Invoice.class)
)
    .assertNext(invoice -> {
        assertThat(invoice.total().value())
            .isEqualByComparingTo("129.50");
    })
    .verifyComplete();
```

Đoạn này là **phần thân kiểm thử minh họa**: cần import `reactor.test.StepVerifier` và AssertJ, khởi tạo reactive template bằng cấu hình test, seed BSON v1 trước bằng driver hoặc reactive driver. Reactive API không tự làm dữ liệu v1 trở nên tương thích nếu converter chưa được đăng ký.

### 12.3. Transaction và optimistic locking

Nếu entity có `@Version`, lần `save` sau khi đọc document cũ có thể liên quan đến cách field version cũ được lưu/thiếu, việc tăng version và lỗi `OptimisticLockingFailureException`. Kiểm thử migration phải kiểm tra điều kiện đồng thời thực tế chứ không giả định chỉ cần đọc rồi save là an toàn.

Transaction nhiều document cần MongoDB deployment phù hợp và configuration Spring Data thích hợp; transaction **không** sửa lỗi chuyển đổi giữa kiểu BSON String và Decimal128. Nếu migration chỉ update một field trong một document, tính nguyên tử của update đơn document và điều kiện ghi phù hợp thường là nền tảng trước khi cân nhắc transaction phức tạp hơn.

## 13. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách xác minh/sửa |
| --- | --- | --- |
| Test `save→findById` mới luôn xanh, production không đọc được dữ liệu cũ | Chưa seed BSON legacy | Tạo golden fixture bằng BSON/driver và assert legacy read |
| Đọc được tiền nhưng lọc `total >= 100` sai | Collection lẫn String/Decimal128 | Kiểm tra `$type`, query, sort, aggregation và migration |
| `@ReadingConverter` không chạy | Chưa đăng ký instance hoặc template đang dùng converter khác | Kiểm tra `MongoCustomConversions` và bean `MongoTemplate` thực tế |
| Converter đọc chạy nhưng ghi thành kiểu cũ | Thiếu `@WritingConverter` hoặc writer chưa chuẩn hóa | Kiểm tra BSON thô sau write/save |
| Kiểm thử thất bại vì `129.5 != 129.50` | So sánh `BigDecimal.equals` bao gồm scale | Chọn quy tắc so sánh số/scale phù hợp nghiệp vụ |
| Thời gian lệch khi chạy ở server khác | Legacy local time không có zone hoặc converter dùng system default | Khóa `ZoneId`, test timezone và dữ liệu gốc |
| Đọc v1 rồi save làm mất `legacy_note` | `save` thay thế representation của entity mới | Dùng partial update hoặc giữ field theo hợp đồng |
| Đổi ID từ string sang ObjectId khiến lookup lỗi | Khác BSON type `_id` | Kiểm tra raw BSON, converter ID và cả hai kiểu fixture |
| Đổi package khiến `_class` cũ không phân giải | Metadata class name/alias cũ không còn | Test root/nested polymorphism, migration hoặc tương thích reader |
| Migration chạy lại làm thay số liệu | Không có điều kiện/idempotency | Lọc theo BSON type/phiên bản, checkpoint và đối soát |
| Test converter thành công nhưng lưu thật lỗi | Codec, callback, index, schema validator hoặc transaction chưa được kiểm thử | Bổ sung test MongoDB instance cô lập |

## 14. Quy trình làm việc trước một lần nâng cấp Spring Data MongoDB

1. **Chụp lại hợp đồng dữ liệu hiện hành và cũ:** collection, field, BSON type, ID, `_class`, version, null/missing và các quy tắc tiền/thời gian.
2. **Tạo bộ golden fixtures bất biến:** bao gồm ít nhất một bản ghi chuẩn, một bản ghi ở biên, một bản ghi lỗi/thiếu field và một bản ghi legacy có field không còn trong model mới.
3. **Viết assertion nghiệp vụ:** các giá trị nào phải giữ tuyệt đối, những khác biệt định dạng nào được chuẩn hóa và khi nào phải từ chối.
4. **Kiểm thử converter thuần:** `read(v1)`, `write(v2)`, `read(write(read(v1)))` và idempotency canonical.
5. **Kiểm thử tích hợp với database:** seed bằng driver, đọc qua `MongoTemplate` và repository, save/update, rồi đọc raw BSON và truy vấn nghiệp vụ.
6. **Đo tương thích vận hành:** query/filter/sort/aggregation/index, các đường truy cập reactive, callback, auditing và concurrency phù hợp phạm vi thực tế.
7. **Lập kế hoạch rolling deployment:** reader/writer của bản cũ và mới cần chạy đồng thời ra sao?
8. **Triển khai migration có kiểm soát:** có backup, checkpoint, đối soát giá trị, thống kê lỗi và phương án quay lui.
9. **Chỉ ngừng hỗ trợ legacy khi đã xác nhận:** không còn document cần converter cũ hoặc có chính sách giữ lại đã được chấp thuận.

## 15. Bài tập thực hành

Một ứng dụng quản lý thanh toán đang nâng cấp qua ba phiên bản:

- **V1:** `total` là String `"250000"`, `paidAt` là chuỗi thời gian địa phương `"2023-05-12 09:00:00"`, thiếu `currency`.
- **V2:** `totalMinor` là `Long`; `paidAt` là BSON Date; thêm `currency = "VND"`.
- **V3:** `total` là Decimal128 theo đơn vị tiền chính; `paidAt` vẫn là BSON Date; có quy tắc nghiệp vụ cần giữ currency.

Hãy đề xuất ma trận kiểm thử để trả lời:

1. Có thể chuyển chuỗi giờ địa phương V1 thành `Instant` nếu chưa biết zone không?
2. Việc chuyển `250000` từ đơn vị đồng sang giá trị thập phân tiền chính cần quy tắc chia/nhân thế nào, và ai xác nhận?
3. Fixture nào phải giữ nguyên để chứng minh V3 đọc được dữ liệu V1/V2?
4. Khi write canonical V3, kiểu BSON và currency phải như thế nào?
5. Nếu V2 vẫn chạy cùng V3 trong rolling deployment, nó có thể đọc bản ghi do V3 vừa tạo không?
6. Khi tổng hợp doanh thu, những bản ghi còn ở định dạng V1 có bị bỏ sót không?

**Hướng giải:** không được tự đoán múi giờ V1 nếu không có ngữ cảnh đáng tin cậy; ghi rõ quy tắc chuyển đơn vị tiền trước khi triển khai; giữ fixture V1/V2 dưới dạng BSON ban đầu, viết reader hỗ trợ từng dạng; dùng một writer canonical được kiểm chứng; kiểm tra cả khả năng đọc dữ liệu mới từ ứng dụng cũ nếu rolling deployment đòi hỏi. Đối soát tổng giá trị trước/sau migration bằng quy tắc tiền tệ thống nhất.

## 16. Tài liệu tham khảo

- Spring Data MongoDB — [Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html): `@ReadingConverter`, `@WritingConverter`, đăng ký converters và kiểu BSON.
- Spring Data MongoDB — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `MappingMongoConverter` và quy tắc ánh xạ domain ↔ BSON.
- Spring Data MongoDB — [Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): hành vi `save`/replace/update, `@Version` và thao tác ghi.
- MongoDB — [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): String, Decimal128, Date và các kiểu BSON khác.
- MongoDB — [`$type`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/): kiểm kê kiểu thực tế của field.

## Ghi nhớ

Kiểm thử `read(write(x))` với model mới là cần thiết nhưng **chưa đủ**. Để bảo vệ dữ liệu thực tế qua các lần nâng cấp, hãy kiểm thử **`read_v2(legacyBson)`**, **`read_v2(write_v2(read_v2(legacyBson)))`** và hành vi persistence/query trên MongoDB. Dùng golden fixture đúng kiểu BSON, định nghĩa rõ tương đương nghiệp vụ, đăng ký converter đọc và ghi tường minh, kiểm tra field có thể mất khi `save`, rồi đối soát sau migration. Đối với hệ thống Spring Data MongoDB có lịch sử dữ liệu dài, đây là lớp bảo vệ quan trọng trước khi refactor mapping và triển khai phiên bản mới.

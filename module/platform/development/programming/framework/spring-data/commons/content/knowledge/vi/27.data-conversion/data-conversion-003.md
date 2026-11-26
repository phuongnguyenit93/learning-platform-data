# Phân biệt chiều chuyển đổi khi cả hai kiểu đều là kiểu đơn giản

## 1. Bài toán: String → Long đang phục vụ chiều nào?

Một converter có chữ ký:

```java
Converter<String, Long>
```

chỉ cho biết source là `String` và target là `Long`. Chữ ký đó chưa đủ để diễn đạt mục đích persistence.

Nó có thể được dùng để:

- Đọc chuỗi từ store và tạo giá trị `Long` cho model Java.
- Lấy chuỗi từ model Java và ghi số `Long` xuống store.

Nếu cả `String` và `Long` đều là kiểu đơn giản được store hỗ trợ, framework không thể suy ra duy nhất vai trò đọc hay ghi chỉ từ việc đầu nào là kiểu native.

Spring Data Commons cung cấp hai annotation để khai báo mục đích khi đăng ký custom conversion:

```java
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;
```

Điểm quan trọng là **chiều persistence được xác định theo dòng dữ liệu giữa store và model**, không theo tên kiểu hoặc tên class converter.

## 2. Tách chiều Java khỏi chiều persistence

### 2.1. Source và target là chiều của hàm convert

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

Với `Converter<String, Long>`:

```text
String → Long
```

Annotation không đảo chữ ký này.

### 2.2. Reading và writing là vai trò trong ánh xạ

```text
READ:
Giá trị từ store → converter → giá trị cho model Java

WRITE:
Giá trị từ model Java → converter → giá trị cho store
```

Cùng một chữ ký có thể phục vụ một trong hai vai trò:

| Khai báo | Source thuộc phía nào? | Target thuộc phía nào? |
| --- | --- | --- |
| `@ReadingConverter Converter<String, Long>` | Chuỗi đọc từ store | Số dùng trong model |
| `@WritingConverter Converter<String, Long>` | Chuỗi trong model | Số ghi xuống store |
| `@ReadingConverter Converter<Long, String>` | Số đọc từ store | Chuỗi dùng trong model |
| `@WritingConverter Converter<Long, String>` | Số trong model | Chuỗi ghi xuống store |

Không có quy tắc “String luôn là dữ liệu database” hoặc “Long luôn là dữ liệu domain”.

Ví dụ, một mã nghiệp vụ được ứng dụng biểu diễn bằng `String` nhưng hệ thống cũ lưu bằng số có thể cần:

```text
Ghi: String của domain → Long của store
Đọc: Long của store → String của domain
```

Ngược lại, một thuộc tính numeric của domain được lưu thành chuỗi lại cần cặp converter theo chiều khác.

## 3. Kiểu đơn giản phải được hiểu theo store

“Kiểu đơn giản” trong mapping không chỉ là Java primitive.

Một store có thể hỗ trợ trực tiếp các kiểu như:

- `String`.
- `Long`, `Integer`, `Boolean`.
- Kiểu ngày giờ hoặc binary cụ thể.
- Các kiểu đặc thù do driver và module cung cấp.

Tập kiểu được hỗ trợ phụ thuộc module, driver, custom conversions và phiên bản.

Trong một trường hợp dễ suy luận:

```text
Money của domain → Decimal128 của MongoDB
```

một phía là kiểu domain riêng, phía còn lại là kiểu lưu trữ được store hiểu. Hạ tầng có thêm cơ sở để phân loại converter.

Nhưng với:

```text
String ↔ Long
```

cả hai đầu có thể đều là native/simple type. Việc xét “đầu nào được store hỗ trợ” không còn xác định được một vai trò duy nhất.

### SimpleTypeHolder và CustomConversions

Ở mức abstraction của Commons:

- Metadata về simple types giúp mapper phân biệt giá trị đơn giản với object cần ánh xạ cấu trúc.
- `CustomConversions` quản lý các conversion được đăng ký và thông tin chiều đọc/ghi.
- Module store cung cấp tập kiểu và các conversion tích hợp của nó.

Đánh dấu một kiểu là simple không tự tạo ra converter. Có converter Java cũng chưa có nghĩa converter đã nằm trong registry persistence mà ứng dụng thực sự sử dụng.

Không suy khả năng của MongoDB từ tập kiểu của JDBC hoặc ngược lại.

## 4. Vai trò của @ReadingConverter và @WritingConverter

### 4.1. Khai báo vai trò rõ ràng

```java
@ReadingConverter
public final class SomeReadingConverter
        implements Converter<StoreValue, DomainValue> {
    // ...
}
```

```java
@WritingConverter
public final class SomeWritingConverter
        implements Converter<DomainValue, StoreValue> {
    // ...
}
```

Các tên `StoreValue` và `DomainValue` ở đây là ký hiệu minh họa vai trò.

Annotation giúp Spring Data phân loại converter khi xây dựng thông tin custom read/write conversion. Điều này đặc biệt cần thiết khi cả source và target đều là kiểu native.

### 4.2. Annotation không tự làm những việc sau

Hai annotation không tự:

- Đảo source và target.
- Sinh converter ngược.
- Đưa class vào registry persistence.
- Giới hạn converter cho một field có tên cụ thể.
- Tạo schema hoặc thay đổi kiểu dữ liệu đang lưu.
- Thay thế việc kiểm tra conversion thực tế của store.

Đánh dấu `Converter<String, Long>` bằng `@WritingConverter` không tạo ra `Converter<Long, String>` cho chiều đọc.

Cũng không nên gắn cả hai annotation để tránh phải xác định mục đích. Nếu một cặp cần dùng cho cả hai vai trò trong một thiết kế cụ thể, đó phải là lựa chọn có chủ đích và có kiểm thử.

### 4.3. Đây không phải cơ chế khóa mọi lời gọi convert

Annotation được Spring Data sử dụng để mô tả vai trò đăng ký custom conversion. Nó không làm method `convert` biết mình đang được gọi từ một luồng đọc hay ghi.

Code sau vẫn là lời gọi Java thông thường:

```java
Long value = new DecimalNumberWritingConverter().convert("1250");
```

Ngoài ra, một `ConversionService` tổng quát có thể có các converter tích hợp hoặc fallback khác. Vì vậy, không diễn giải `@WritingConverter` thành cam kết “trên toàn ứng dụng, cặp kiểu này tuyệt đối không thể xuất hiện trong chiều đọc”.

Cần kiểm tra chính mapper và đường gọi đang sử dụng. Annotation xác định vai trò trong registry Spring Data, không phải một cơ chế kiểm soát truy cập.

## 5. Ví dụ: chuỗi số của domain được lưu thành Long

Giả sử ứng dụng dùng mã ngoài dưới dạng chuỗi canonical, còn store yêu cầu lưu số nguyên 64-bit không âm.

Hợp đồng:

- Domain: `"1250"`.
- Store: `1250L`.
- Không chấp nhận số âm, dấu cộng, khoảng trắng hoặc số có zero ở đầu.
- Giá trị phải nằm trong miền không âm của `long`.

Quy tắc canonical tránh trường hợp `"001250"` bị biến thành `"1250"` sau một vòng lưu–đọc.

Ví dụ này minh họa sự mơ hồ của hai kiểu đơn giản. Cặp `String ↔ Long` có phạm vi rất rộng; phần sau trình bày cách dùng một kiểu domain riêng để thu hẹp tác động.

### 5.1. Converter ghi

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class DecimalNumberWritingConverter
        implements Converter<String, Long> {

    @Override
    public Long convert(String source) {
        if (source == null
                || !source.matches("0|[1-9][0-9]*")) {
            throw new IllegalArgumentException(
                    "Expected a canonical non-negative decimal number");
        }

        return Long.valueOf(source);
    }
}
```

`Long.valueOf` từ chối giá trị vượt phạm vi 64-bit. Không dùng phép ép kiểu có thể làm mất dữ liệu.

Chiều nghiệp vụ:

```text
Giá trị model "1250"
    → DecimalNumberWritingConverter
    → Long 1250 cho store
```

### 5.2. Converter đọc

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class DecimalNumberReadingConverter
        implements Converter<Long, String> {

    @Override
    public String convert(Long source) {
        if (source == null || source < 0) {
            throw new IllegalArgumentException(
                    "Expected a non-negative Long");
        }

        return source.toString();
    }
}
```

Chiều nghiệp vụ:

```text
Long 1250 từ store
    → DecimalNumberReadingConverter
    → giá trị model "1250"
```

Hai converter có chữ ký ngược nhau và annotation khác nhau vì hợp đồng domain/store khác nhau ở mỗi chiều.

### 5.3. Null không phải một mã mặc định

Các method trên kiểm tra null nếu được gọi trực tiếp. Trong nhiều đường conversion tiêu chuẩn, null được hạ tầng xử lý mà không gọi converter cho giá trị không null.

Do đó, không dựa vào `convert(null)` để tự động tạo `0L` hoặc chuỗi rỗng cho mọi field thiếu dữ liệu.

Phải xác định riêng:

- Field có nullable không?
- Field không tồn tại khác field có giá trị null như thế nào?
- Constructor của domain có chấp nhận null không?
- Mapper xử lý dữ liệu thiếu ra sao?

Converter không thay thế toàn bộ chính sách nullability của model.

## 6. Đăng ký trong đúng registry của store

### 6.1. Annotation không làm converter tự được phát hiện

Một class có `@ReadingConverter` hoặc `@WritingConverter` vẫn cần được đăng ký theo cơ chế của module.

Tương tự:

- Bean `Converter` của Spring MVC không tự chứng minh persistence sử dụng nó.
- `@Component` trên converter không bảo đảm mọi mapper tự thêm nó vào registry.
- Một `ConversionService` tự tạo trong test không nhất thiết là conversion service bên trong store converter.

Cần đi tới đúng điểm cấu hình của Spring Data MongoDB, JDBC, R2DBC hoặc module đang sử dụng.

### 6.2. Ví dụ cấu hình MongoDB

Với nhánh Spring Data MongoDB có API `MongoCustomConversions.create`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

@Configuration
public class MongoConversionConfiguration {

    @Bean
    public MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(adapter -> {
            adapter.registerConverter(
                    new DecimalNumberWritingConverter());
            adapter.registerConverter(
                    new DecimalNumberReadingConverter());
        });
    }
}
```

Đưa cấu hình vào đúng cơ chế tạo converter của ứng dụng. Nếu đang dùng một base configuration hoặc một `MongoTemplate` tự tạo, cần kết nối custom conversions với converter mà template đó thực sự sử dụng.

Với nhánh có API cấu hình khác, dùng hook hoặc constructor tương ứng của nhánh đó. Không tạo thêm một converter song song rồi chỉ kiểm tra converter mới trong test.

### 6.3. Khi tự dựng MappingMongoConverter

Fixture hoặc cấu hình thủ công cần thống nhất registry và mapping context:

```java
MongoCustomConversions conversions =
        MongoCustomConversions.create(adapter -> {
            adapter.registerConverter(
                    new DecimalNumberWritingConverter());
            adapter.registerConverter(
                    new DecimalNumberReadingConverter());
        });

MongoMappingContext context = new MongoMappingContext();
context.setSimpleTypeHolder(
        conversions.getSimpleTypeHolder());
context.afterPropertiesSet();

MappingMongoConverter converter =
        new MappingMongoConverter(
                NoOpDbRefResolver.INSTANCE,
                context);

converter.setCustomConversions(conversions);
converter.afterPropertiesSet();
```

Các class thuộc package MongoDB tương ứng được trình bày đầy đủ trong ví dụ test bên dưới.

Việc cung cấp `SimpleTypeHolder` đặc biệt quan trọng khi custom conversion khiến một value object của domain được xử lý như một giá trị đơn giản, thay vì một object con cần mapping cấu trúc.

Fixture này không cần kết nối database nếu chỉ kiểm tra document conversion và không sử dụng DBRef.

## 7. Hệ quả của converter toàn cục String → Long

Đăng ký converter ghi theo source `String` không mang nghĩa “chỉ áp dụng cho thuộc tính externalNumber”.

Giả sử model có:

```java
public record LegacyDocument(
        String externalNumber,
        String description) {
}
```

Dữ liệu:

```text
externalNumber = "1250"
description    = "Notebook"
```

Một converter ghi `String → Long` toàn cục có thể trở thành ứng viên cho các thuộc tính chuỗi khác trong đường mapping. Khi gặp `"Notebook"`, quy tắc numeric sẽ thất bại.

Các field ID dạng chuỗi, tên người dùng, email và chuỗi bên trong object con cũng cần được xem xét theo đường mapping thực tế.

### Những cách xử lý không giải quyết đúng phạm vi

Không nên sửa converter thành:

```java
// Không phải giải pháp giới hạn converter cho một field.
// Nếu chuỗi không phải số thì trả 0.
```

Điều đó chỉ thay lỗi rõ ràng bằng việc làm sai dữ liệu.

Cũng không tạo một converter `String → Object` trả về lúc thì chuỗi, lúc thì số để né hợp đồng kiểu mà chưa thiết kế rõ hành vi mapping.

Các lựa chọn phù hợp hơn là:

- Dùng value object riêng cho mã ngoài.
- Dùng property-level conversion nếu module và phiên bản hỗ trợ.
- Thực hiện chuyển đổi tường minh trong adapter khi chỉ một đường tích hợp cần nó.

## 8. Thu hẹp bằng value object

### 8.1. Kiểu domain

```java
public record ExternalNumber(String value) {

    public ExternalNumber {
        if (value == null
                || !value.matches("0|[1-9][0-9]*")) {
            throw new IllegalArgumentException(
                    "Invalid external number");
        }

        Long.parseLong(value);
    }
}
```

Constructor xác nhận cùng hợp đồng numeric ngay khi tạo domain value. Nếu mã ngoài phải giữ zero ở đầu hoặc có thể vượt `long`, cần chọn một biểu diễn lưu trữ khác.

### 8.2. Converter ghi có source hẹp

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class ExternalNumberWritingConverter
        implements Converter<ExternalNumber, Long> {

    @Override
    public Long convert(ExternalNumber source) {
        return Long.valueOf(source.value());
    }
}
```

### 8.3. Converter đọc có target hẹp

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class ExternalNumberReadingConverter
        implements Converter<Long, ExternalNumber> {

    @Override
    public ExternalNumber convert(Long source) {
        return new ExternalNumber(source.toString());
    }
}
```

Model:

```java
public record ScopedLegacyDocument(
        ExternalNumber externalNumber,
        String description) {
}
```

Bây giờ:

```text
ExternalNumber("1250") → Long 1250
String "Notebook"     → vẫn là chuỗi theo mapping thông thường
```

Đăng ký cặp converter mới **thay cho** cặp `String ↔ Long` rộng trong cấu hình ứng dụng này. Giữ cả cặp rộng lẫn cặp hẹp sẽ không tự loại bỏ tác động lên các thuộc tính chuỗi khác.

Việc dùng value object cũng làm cho API repository hoặc query có thể thể hiện đúng ý nghĩa của tham số, thay vì dùng `String` cho mọi loại dữ liệu.

## 9. Kiểm thử đúng cả vai trò lẫn dữ liệu thực tế

### 9.1. Test trực tiếp chỉ chứng minh thuật toán

Có thể kiểm tra:

```java
assertEquals(
        Long.valueOf(1250L),
        new DecimalNumberWritingConverter().convert("1250"));

assertEquals(
        "1250",
        new DecimalNumberReadingConverter().convert(1250L));
```

Nhưng test này chưa chứng minh:

- Annotation được registry nhận diện.
- Converter đã đăng ký trong mapper.
- Model không bị ghi thành cấu trúc khác.
- Kiểu native trong document đúng.
- Những field không liên quan không bị ảnh hưởng.

Cần kiểm thử qua converter persistence thực tế.

### 9.2. Fixture MongoDB minh họa cặp hai kiểu đơn giản

Model dùng trong test chỉ có một field để cô lập ví dụ converter rộng:

```java
public record LegacyNumberDocument(String externalNumber) {
}
```

Ví dụ sử dụng JUnit Jupiter và phiên bản MongoDB mapping có hỗ trợ record:

```java
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.convert.MappingMongoConverter;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;
import org.springframework.data.mongodb.core.convert.NoOpDbRefResolver;
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class DecimalNumberMappingTest {

    private MappingMongoConverter converter;

    @BeforeEach
    void setUp() throws Exception {
        MongoCustomConversions conversions =
                MongoCustomConversions.create(adapter -> {
                    adapter.registerConverter(
                            new DecimalNumberWritingConverter());
                    adapter.registerConverter(
                            new DecimalNumberReadingConverter());
                });

        MongoMappingContext context = new MongoMappingContext();
        context.setSimpleTypeHolder(
                conversions.getSimpleTypeHolder());
        context.setInitialEntitySet(
                Set.of(LegacyNumberDocument.class));
        context.afterPropertiesSet();

        converter = new MappingMongoConverter(
                NoOpDbRefResolver.INSTANCE,
                context);
        converter.setCustomConversions(conversions);
        converter.afterPropertiesSet();
    }

    @Test
    void writesDomainStringAsNativeLong() {
        Document target = new Document();

        converter.write(
                new LegacyNumberDocument("1250"),
                target);

        assertTrue(
                target.get("externalNumber") instanceof Long);
        assertEquals(
                Long.valueOf(1250L),
                target.get("externalNumber"));
    }

    @Test
    void readsNativeLongAsDomainString() {
        Document source =
                new Document("externalNumber", 1250L);

        LegacyNumberDocument restored =
                converter.read(
                        LegacyNumberDocument.class,
                        source);

        assertEquals(
                "1250",
                restored.externalNumber());
    }

    @Test
    void rejectsLossyDomainRepresentation() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new DecimalNumberWritingConverter()
                        .convert("001250"));
    }
}
```

Fixture đọc được tạo độc lập bằng raw `Document`, không chỉ lấy kết quả của chính converter ghi. Nhờ đó có thể phát hiện sự khác nhau giữa schema cần có và một round-trip tự nhất quán nhưng sai biểu diễn.

Các file Java trong ví dụ được hiểu là những đơn vị source tương ứng trong project kiểm thử, không phải nhiều public class ghép vào cùng một file.

### 9.3. Với value object, thêm kiểm tra phạm vi

Khi chuyển sang cặp converter hẹp, một test quan trọng là:

```text
Input:
externalNumber = ExternalNumber("1250")
description    = "Notebook"

Document:
externalNumber có giá trị Long 1250
description vẫn có giá trị String "Notebook"
```

Test phải dùng registry chỉ chứa cặp tùy biến mong muốn. Không để cấu hình test vô tình giữ converter rộng từ một configuration khác.

### 9.4. Cùng giá trị số chưa chắc cùng kiểu runtime

Trong MongoDB, số nguyên có thể có biểu diễn 32-bit hoặc 64-bit. Raw fixture:

```java
new Document("externalNumber", 1250)
```

khác với:

```java
new Document("externalNumber", 1250L)
```

Cặp `Converter<Long, ...>` không nên được mặc định là đã kiểm chứng mọi đầu vào `Integer`, `Double` hoặc `Decimal128`.

Nếu dữ liệu lịch sử có nhiều kiểu numeric, phải thiết kế conversion và test cho từng kiểu liên quan. Không mở source thành `Number` rồi bỏ qua vấn đề phần thập phân, tràn số hoặc mất chính xác.

## 10. Query, projection và thao tác ghi khác

### 10.1. Query cần dùng cùng biểu diễn lưu trữ

Nếu field được lưu bằng `Long`, một truy vấn raw với chuỗi `"1250"` có thể không tương đương truy vấn với số `1250L`.

Repository và query mapper có thể áp dụng conversion dựa trên metadata thuộc tính. Nhưng native query hoặc native driver có thể không đi qua cùng đường conversion.

Cần kiểm tra:

- Derived query có chuyển đúng tham số không?
- Template query có dùng metadata entity không?
- Update có ánh xạ giá trị theo thuộc tính không?
- Raw document hoặc native client có bỏ qua conversion không?

Không chỉ chứng minh `save` ghi đúng rồi coi mọi truy vấn cũng đúng.

### 10.2. Kiểu lưu quyết định ngữ nghĩa so sánh

Chuỗi và số có thể có thứ tự khác nhau:

```text
Theo chuỗi: "10" đứng trước "2"
Theo số:    2 nhỏ hơn 10
```

Đổi biểu diễn lưu từ chuỗi sang số có thể ảnh hưởng:

- Sort.
- Điều kiện khoảng.
- Index và dữ liệu index hiện có.
- Kiểu tham số truy vấn.
- Dữ liệu lịch sử chưa được migration.

Converter không tự migration toàn bộ collection hoặc bảng.

### 10.3. Projection cũng có target type

Một projection trả `String` có thể có nhu cầu conversion khác projection trả `Long` hoặc value object.

Khả năng dựng DTO phụ thuộc dữ liệu được chọn, target type và mapper của module. Không dùng việc entity đọc được làm bằng chứng mọi DTO constructor cũng nhận đúng kiểu.

Nếu một DTO chỉ phục vụ hiển thị, cân nhắc định dạng ở tầng phù hợp thay vì thay conversion persistence toàn ứng dụng.

## 11. Các store khác áp dụng cấu hình riêng

| Ngữ cảnh | Điều cần dùng hoặc kiểm tra |
| --- | --- |
| Spring Data MongoDB | Mongo custom conversions, document converter và query mapping tương ứng |
| Spring Data JDBC | JDBC custom conversions, kiểu cột/driver và metadata cần cho chiều ghi |
| Spring Data R2DBC | R2DBC custom conversions và kiểu giá trị do driver reactive cung cấp |
| Spring Data JPA | Cơ chế của JPA provider, như `AttributeConverter`, khi phù hợp |
| Spring MVC hoặc binding request | Conversion service của web, khác registry persistence |
| Native driver | Quy tắc chuyển đổi của driver hoặc adapter do ứng dụng tự quản lý |

Không coi `@WritingConverter` là yêu cầu chung buộc mọi module ghi cùng một kiểu vật lý.

Ví dụ, trong JDBC có trường hợp cần thông tin kiểu SQL ngoài giá trị Java. Trong MongoDB cần quan tâm BSON type. Trong JPA, converter được provider quản lý không tự được cấu hình chỉ bằng annotation đọc/ghi của Commons.

Trước khi dùng ví dụ cho một module khác, xác định lại:

1. Source runtime là kiểu nào?
2. Target runtime phải là kiểu nào?
3. Registry nào được mapper sử dụng?
4. Annotation nào có hiệu lực trong đường đó?
5. Thao tác query/update có đi qua converter hay không?

## 12. Trường hợp cùng source và target type

Một converter như:

```text
String → String
```

còn khó phân biệt hơn vì chữ ký không thể hiện thay đổi biểu diễn kiểu.

Ngay cả khi có annotation đọc/ghi, phạm vi của một converter theo kiểu vẫn không tự thu hẹp đến một field cụ thể. Ngoài ra, một đường mapper có thể xử lý giá trị đã đúng kiểu theo cách không giống đường custom conversion mà ứng dụng kỳ vọng.

Không dùng converter cùng kiểu toàn cục như một cách ngầm biến đổi mọi chuỗi nếu nghiệp vụ chỉ liên quan một thuộc tính.

Nên cân nhắc:

- Value object riêng.
- Property-level converter được module hỗ trợ.
- Logic chuyển đổi tường minh tại ranh giới tích hợp.

Sau đó kiểm thử qua đúng mapper để xác nhận converter thực sự được gọi.

## 13. Lỗi thường gặp và chẩn đoán

| Biểu hiện | Khả năng cần xem xét | Hướng kiểm tra |
| --- | --- | --- |
| Converter chạy trực tiếp nhưng persistence không dùng | Chưa đăng ký hoặc đăng ký nhầm context | Kiểm tra custom conversions của mapper thật |
| Dữ liệu bị đổi kiểu ở chiều ngoài dự kiến | Converter native-to-native chưa được phân loại rõ | Xem annotation đọc/ghi và cặp source/target |
| Thêm annotation nhưng không thay đổi gì | Annotation không tự đăng ký hoặc API đang bỏ qua mapper | Xác định đường gọi thực tế |
| Tên/email bắt đầu lỗi sau khi thêm converter | Cặp String → Long quá rộng | Chuyển sang value object hoặc conversion theo property |
| Đọc số nhỏ được, số khác lỗi | Runtime type hoặc phạm vi numeric khác fixture | Kiểm tra Integer/Long/decimal và giới hạn |
| Mã có zero đầu bị thay đổi | Lưu mã định danh bằng số làm mất biểu diễn | Chốt lại hợp đồng domain và kiểu lưu |
| Ghi đúng nhưng tìm không ra | Query dùng kiểu tham số khác biểu diễn lưu | Kiểm tra query mapping và raw request |
| Null trở thành lỗi constructor | Mapping thiếu dữ liệu không được converter tạo default | Kiểm tra nullability và creator |
| Unit test PASS, ứng dụng lỗi | Fixture không dùng conversion configuration thực tế | Thêm integration test với mapper ứng dụng |
| Đổi converter làm dữ liệu cũ không đọc được | Chưa có chính sách tương thích hoặc migration | Chuẩn bị raw fixture lịch sử |
| String → String không chạy như dự kiến | Đường mapper xử lý cùng kiểu hoặc phạm vi không phù hợp | Dùng cơ chế theo property và kiểm chứng |

Khi chẩn đoán, ghi lại module, phiên bản, class runtime của source, target mong muốn và thao tác đang thực hiện. Tên Java của field không đủ để giải thích converter nào được chọn.

## 14. Bài thực hành

Một hệ thống lưu mã khách hàng dưới dạng số 64-bit, trong khi ứng dụng muốn biểu diễn mã theo một domain type riêng.

Thực hiện:

1. Mô tả rõ chiều store → domain và domain → store.
2. Viết cặp converter với annotation phù hợp.
3. Đăng ký trong custom conversions của store đã chọn.
4. Tạo raw fixture có đúng runtime type.
5. Kiểm tra riêng chiều đọc và chiều ghi.
6. Kiểm tra mã 0, mã lớn nhất hợp lệ, giá trị vượt phạm vi và mã có zero đầu.
7. Thêm một thuộc tính chuỗi thông thường và chứng minh nó không bị đổi.
8. Kiểm tra query theo mã bằng API ứng dụng thực sự sử dụng.
9. Xác định cách xử lý dữ liệu cũ đang lưu bằng kiểu khác.

Tiêu chí hoàn thành là giải thích được vì sao mỗi converter được phân loại là đọc hoặc ghi, registry nào sử dụng nó và những thuộc tính nào có thể chịu tác động.

Khi cả hai đầu đều là kiểu đơn giản, chữ ký converter không còn đủ để diễn đạt vai trò persistence. Khai báo chiều rõ ràng, đăng ký đúng mapper và thu hẹp kiểu domain giúp conversion trở thành một hợp đồng có thể kiểm chứng.

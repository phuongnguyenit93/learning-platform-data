# ConversionService, Converter và vai trò của CustomConversions

Một thuộc tính trong domain không nhất thiết có cùng kiểu với giá trị được lưu. Ứng dụng có thể dùng `ProductCode` để biểu diễn mã sản phẩm, trong khi database hoặc document chỉ lưu một chuỗi như `"SKU-0042"`. Khi ghi và đọc, cần một hợp đồng chuyển đổi rõ ràng giữa hai biểu diễn này.

Bài học thuộc chương **Chuyển đổi dữ liệu** của **Spring Data Commons**. Trọng tâm là phân biệt ba thành phần: `Converter` mô tả một phép chuyển đổi, `ConversionService` thực hiện chuyển đổi theo kiểu, và `CustomConversions` cung cấp cấu hình cùng metadata chuyển đổi cho hạ tầng Spring Data. Việc tích hợp cuối cùng vẫn phụ thuộc module và kho dữ liệu đang sử dụng.

## 1. Ba abstraction nằm ở hai tầng thư viện

Các kiểu chính nằm trong những package sau:

```java
org.springframework.core.convert.converter.Converter
org.springframework.core.convert.ConversionService
org.springframework.data.convert.CustomConversions
```

Hai kiểu đầu thuộc Spring Framework. Kiểu thứ ba thuộc Spring Data Commons.

| Thành phần | Câu hỏi nó giải quyết | Vai trò chính |
| --- | --- | --- |
| `Converter<S, T>` | Chuyển một giá trị kiểu `S` thành `T` bằng cách nào? | Chứa logic cho một hướng chuyển đổi |
| `ConversionService` | Có thể chuyển từ kiểu này sang kiểu kia không, và thực hiện ra sao? | Tra cứu và thực hiện những phép chuyển đổi đã đăng ký |
| `CustomConversions` | Những converter nào thuộc cấu hình persistence, dùng khi đọc hay ghi, và ảnh hưởng metadata kiểu như thế nào? | Quản lý tập chuyển đổi cùng thông tin cần cho mapping của Spring Data |

`CustomConversions` không phải một phiên bản khác của `ConversionService`. Nó không thay thế API `convert(...)` bằng một cách gọi tương tự để chuyển từng giá trị nghiệp vụ.

Cũng không đồng nhất `ConversionService` với converter của cả một store. Một thành phần như Mongo mapping converter hoặc relational converter còn xử lý metadata entity, thuộc tính, tên lưu trữ và quá trình tạo object; chuyển đổi giá trị chỉ là một phần trong công việc đó.

## 2. Nhìn luồng đọc và ghi từ góc độ domain

Giả sử thuộc tính Java là `ProductCode`, còn biểu diễn mà store nhận là `String`:

```text
GHI:
Entity có ProductCode
        |
        | mapping của store
        v
Converter<ProductCode, String>
        |
        v
Chuỗi được giao cho tầng lưu trữ

ĐỌC:
Chuỗi do tầng lưu trữ cung cấp
        |
        v
Converter<String, ProductCode>
        |
        | mapping và tạo object của store
        v
Entity có ProductCode
```

Trong mô hình này, “reading” và “writing” được xác định theo chiều tương tác với kho dữ liệu:

- **Writing:** từ kiểu domain sang kiểu biểu diễn được store hỗ trợ.
- **Reading:** từ kiểu store cung cấp sang kiểu domain.

Đó không phải chiều HTTP request và response. Một converter ghi persistence không tự trở thành serializer JSON hoặc converter dành cho tham số URL.

Kiểu biểu diễn cũng không nhất thiết là chuỗi. Nó có thể là một kiểu số, kiểu thời gian, kiểu binary hoặc một kiểu đặc thù mà driver và module hỗ trợ. Lựa chọn đó phải phù hợp với khả năng của store.

## 3. Xây dựng một value object có hợp đồng rõ ràng

Ví dụ dùng Java hỗ trợ record:

```java
import java.util.Objects;

public record ProductCode(String value) {

    public ProductCode {
        Objects.requireNonNull(value, "product code is required");
        if (!value.matches("[A-Z]{3}-[0-9]{4}")) {
            throw new IllegalArgumentException(
                    "product code must look like SKU-0042"
            );
        }
    }
}
```

Hợp đồng của `ProductCode` gồm:

- Không chấp nhận null.
- Ba chữ cái viết hoa, dấu gạch nối và bốn chữ số.
- Không tự cắt khoảng trắng hoặc đổi chữ thường thành chữ hoa.

Quyết định cuối cùng giúp minh họa một phép chuyển đổi có thể round-trip chính xác. Nếu domain có quy tắc chuẩn hóa khác, cần mô tả và kiểm thử quy tắc đó thay vì để converter âm thầm sửa dữ liệu.

Một value object không tự biết cách lưu vào mọi database. Nó diễn đạt giá trị trong domain; converter hoặc cơ chế mapping phù hợp sẽ diễn đạt giá trị đó ở ranh giới persistence.

## 4. Converter mô tả một hướng chuyển đổi

Hợp đồng rút gọn của Spring Framework là:

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

Với value object trên, có thể viết hai implementation riêng. Mỗi public type nằm trong một tệp Java riêng.

### 4.1. Từ domain sang chuỗi lưu trữ

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class ProductCodeWritingConverter
        implements Converter<ProductCode, String> {

    @Override
    public String convert(ProductCode source) {
        return source.value();
    }
}
```

### 4.2. Từ chuỗi lưu trữ về domain

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class ProductCodeReadingConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        return new ProductCode(source);
    }
}
```

Hai annotation thuộc Spring Data:

```java
org.springframework.data.convert.WritingConverter
org.springframework.data.convert.ReadingConverter
```

Chúng làm rõ vai trò của converter khi được hạ tầng `CustomConversions` phân tích. Chúng không tự đăng ký converter vào mọi `ConversionService` hoặc mọi repository trong ứng dụng.

### 4.3. Không có chiều ngược tự động

Đăng ký `Converter<ProductCode, String>` không làm `Converter<String, ProductCode>` tự xuất hiện. Nhiều phép chuyển đổi thậm chí không có nghịch đảo duy nhất.

Ví dụ, nếu khi ghi chỉ giữ một chuỗi đã chuẩn hóa và bỏ thông tin ban đầu, không thể kỳ vọng lúc đọc luôn khôi phục đúng nguyên trạng đầu vào.

Với hai converter của bài, mục tiêu có thể viết là:

```text
read(write(productCode)) bằng productCode
```

Mục tiêu này hợp lý vì `ProductCode` và chuỗi lưu trữ giữ cùng thông tin. Không áp dụng nó máy móc cho mọi converter có làm tròn số, thay đổi độ chính xác hoặc loại bỏ dữ liệu.

## 5. ConversionService thực hiện các phép chuyển đã đăng ký

`ConversionService` cung cấp những thao tác như:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);
```

Đây là dạng rút gọn để minh họa, không phải toàn bộ API và annotation nullability của một phiên bản cụ thể. API còn có các biến thể dùng thông tin kiểu chi tiết hơn, hữu ích khi cần xét generic hoặc metadata của thuộc tính.

Một ví dụ độc lập với store:

```java
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService service = new DefaultConversionService();
service.addConverter(new ProductCodeWritingConverter());
service.addConverter(new ProductCodeReadingConverter());

ProductCode original = new ProductCode("SKU-0042");

String stored = service.convert(original, String.class);
ProductCode restored = service.convert(stored, ProductCode.class);

System.out.println(stored);               // SKU-0042
System.out.println(original.equals(restored)); // true
```

Ví dụ chứng minh hai converter hoạt động trong instance `service` vừa cấu hình. Nó chưa chứng minh MongoDB, JDBC, R2DBC hoặc JPA của ứng dụng đang dùng instance đó.

### 5.1. API đọc và API đăng ký là hai hợp đồng

Biến có kiểu `ConversionService` cho phép kiểm tra và chuyển đổi. Việc thêm converter thuộc API đăng ký, chẳng hạn `ConverterRegistry`:

```java
org.springframework.core.convert.converter.ConverterRegistry
```

`DefaultConversionService` có khả năng đăng ký converter, nên ví dụ có thể gọi `addConverter(...)`. Một component chỉ cần thực hiện chuyển đổi thường có thể phụ thuộc vào interface `ConversionService`, thay vì yêu cầu quyền thay đổi registry.

Nên hoàn tất đăng ký ở giai đoạn cấu hình. Converter dùng chung cần an toàn khi được gọi đồng thời; các implementation không giữ trạng thái thay đổi như ví dụ thường dễ kiểm soát hơn.

### 5.2. canConvert không kiểm tra mọi giá trị đầu vào

Sau khi đăng ký, lời gọi:

```java
service.canConvert(String.class, ProductCode.class);
```

có thể trả true. Điều đó nói rằng có một đường chuyển đổi cho cặp kiểu, không nói rằng mọi chuỗi đều hợp lệ.

Ví dụ:

```java
service.convert("invalid", ProductCode.class);
```

vẫn thất bại vì constructor của `ProductCode` từ chối dữ liệu. Lỗi khi chuyển một giá trị và lỗi không có converter là hai tình huống khác nhau; framework có thể bọc nguyên nhân bên trong một exception chuyển đổi.

Không dùng `canConvert(...)` như phép validation cho từng mã sản phẩm.

### 5.3. Metadata generic của converter cần đủ rõ

Các lớp cụ thể như `Converter<ProductCode, String>` giúp hạ tầng nhận diện cặp kiểu. Khi đăng ký một lambda vào registry, nên cung cấp kiểu nguồn và đích nếu cơ chế suy luận metadata không có đủ thông tin:

```java
service.addConverter(
        ProductCode.class,
        String.class,
        ProductCode::value
);
```

Đây là một cách đăng ký thay cho writing converter trong một registry phù hợp, không phải yêu cầu đăng ký trùng cả hai cách. Với cấu hình persistence cần phân loại đọc và ghi, lớp converter có annotation giúp hợp đồng rõ ràng hơn.

## 6. CustomConversions bổ sung điều gì cho Spring Data?

Mapping persistence cần nhiều thông tin hơn câu hỏi “gọi hàm nào để đổi giá trị”. Nó còn phải biết một kiểu là giá trị đơn của store hay một object nên được phân rã thành các thuộc tính.

`CustomConversions` là nơi tổng hợp và phân tích những thông tin như:

- Tập converter tùy chỉnh của ứng dụng.
- Những chuyển đổi và kiểu đơn mà store hỗ trợ.
- Những cặp chuyển đổi dùng ở chiều đọc hoặc chiều ghi.
- Kiểu đích ghi tùy chỉnh của một kiểu domain.
- Thông tin simple type cần cho mapping context.

Nó cũng có thể đăng ký các converter được quản lý vào một `ConverterRegistry` thông qua `registerConvertersIn(...)`. Đó là một phần tích hợp của hạ tầng; vẫn cần store mapping được cấu hình sử dụng đúng metadata tương ứng.

### 6.1. Simple type không chỉ là primitive của Java

Trong ngữ cảnh mapping, simple type là một giá trị mà hạ tầng xử lý như một đơn vị theo khả năng của store và cấu hình chuyển đổi. Nó không giới hạn ở `int`, `long` hoặc những primitive khác.

Với writing converter từ `ProductCode` sang một kiểu lưu trữ đơn như `String`, cấu hình conversions có thể giúp mapping nhận diện `ProductCode` là một giá trị đơn được chuyển đổi, thay vì tiếp tục phân rã nó như một object có thuộc tính `value`.

Đây là khác biệt quan trọng giữa:

```text
Chỉ thêm converter vào một ConversionService bất kỳ
```

và:

```text
Đăng ký converter qua hạ tầng CustomConversions của store,
để mapping và conversion dùng cùng một cấu hình
```

Nếu chỉ chỉnh conversion service mà mapping context vẫn dùng metadata không tương ứng, object có thể bị phân loại hoặc ánh xạ theo một cấu trúc khác với mong muốn.

### 6.2. CustomConversions có metadata về chiều chuyển đổi

Trong API phù hợp, có thể kiểm tra những câu hỏi dạng:

```java
customConversions.hasCustomWriteTarget(ProductCode.class, String.class);
customConversions.hasCustomReadTarget(String.class, ProductCode.class);
```

Những phép kiểm tra này nói về tập chuyển đổi tùy chỉnh đã được cấu hình, không thay cho việc thực hiện một phép chuyển giá trị.

Không dùng kết quả `canConvert(...)` của một conversion service độc lập để kết luận rằng store đã nhận diện đúng chiều đọc, chiều ghi hoặc simple type của một domain property.

### 6.3. Cấu hình phải giữ được nền tảng của store

Module có thể cung cấp một kiểu conversions chuyên biệt và tích hợp các converter mặc định, kiểu đơn, dialect hoặc hỗ trợ driver cần thiết.

Khi thêm converter ứng dụng, dùng điểm mở rộng mà module hỗ trợ. Không tùy tiện thay toàn bộ cấu hình store bằng một danh sách trống rồi chỉ thêm converter của mình; việc đó có thể làm mất những chuyển đổi nền mà mapping đang cần.

Cũng không mặc định `CustomConversions` là một bean toàn cục duy nhất cho mọi store. Một ứng dụng có nhiều loại repository có thể có những hạ tầng mapping và registry khác nhau.

## 7. Vì sao cần ReadingConverter và WritingConverter?

Hạ tầng có thể suy luận chiều dựa trên việc một kiểu có phải kiểu đơn của store hay không. Tuy nhiên, một cặp kiểu có thể mơ hồ, nhất là khi cả nguồn và đích đều là kiểu mà store vốn hỗ trợ.

Ví dụ, một phép chuyển `String` sang `Long` có thể được nghĩ đến ở cả chiều đọc lẫn ghi tùy dữ liệu nguồn và hợp đồng domain. Không nên để một converter rộng như vậy vô tình thay đổi mọi thuộc tính có cùng cặp kiểu.

Annotation giúp khai báo ý định:

```java
@ReadingConverter
```

hoặc:

```java
@WritingConverter
```

Nhưng chúng không biến một cặp kiểu không phù hợp thành khả năng lưu trữ hợp lệ. Store và driver vẫn phải nhận được kiểu đích mà chúng hỗ trợ, hoặc cần thêm cơ chế tích hợp chuyên biệt của module.

Ngoài ra, annotation không phải cơ chế đăng ký. Chỉ đặt `@WritingConverter` trên lớp rồi để lớp không được đưa vào cấu hình conversions thì persistence chưa có lý do sử dụng nó.

## 8. Ví dụ tích hợp riêng với Spring Data MongoDB

Ví dụ này minh họa một module cụ thể, không phải cấu hình dùng chung cho mọi repository. Với phiên bản Spring Data MongoDB hỗ trợ API `MongoCustomConversions.create(...)`, có thể khai báo:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

@Configuration(proxyBeanMethods = false)
class MongoConversionConfiguration {

    @Bean
    MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(adapter -> {
            adapter.registerConverter(new ProductCodeWritingConverter());
            adapter.registerConverter(new ProductCodeReadingConverter());
        });
    }
}
```

Điều kiện quan trọng là Mongo mapping converter của ứng dụng phải được cấu hình dùng bean conversions này. Cách tích hợp phụ thuộc ứng dụng dùng auto-configuration hay tự cấu hình mapping converter.

Nếu dự án đã có một cấu hình Mongo conversions hoặc đang mở rộng lớp cấu hình của module, hãy bổ sung tại điểm mở rộng hiện có thay vì tạo thêm nhiều bean cạnh tranh. Tên phương thức, factory API và điểm mở rộng phải tương thích với phiên bản thực tế.

Một entity minh họa:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("products")
public record ProductDocument(
        @Id String id,
        ProductCode code,
        String name
) {
}
```

Khi mapping và converters đã được tích hợp đúng, mục tiêu lưu là field `code` có biểu diễn chuỗi:

```json
{
  "code": "SKU-0042",
  "name": "Bàn phím"
}
```

JSON trên chỉ minh họa hai field liên quan; không mô tả toàn bộ document, ID hoặc metadata bổ sung mà cấu hình store có thể ghi.

Khi đọc lại, converter chiều đọc khôi phục `ProductCode`. Nếu dữ liệu hiện có lưu `code` dưới một cấu trúc khác, chẳng hạn object chứa field `value`, thêm converter mới không tự chuyển đổi toàn bộ document cũ. Cần một hợp đồng tương thích hoặc migration riêng.

### 8.1. Converter bean chưa chắc đã được persistence sử dụng

Trong một ứng dụng có Spring container, một object là bean không có nghĩa nó đã được đăng ký ở mọi registry.

Không suy ra rằng thêm `@Component` vào converter sẽ tự làm mọi store dùng converter đó. Một cấu hình hoặc auto-configuration cụ thể có thể hỗ trợ thu thập bean, nhưng cần dựa vào cơ chế của đúng module và ứng dụng.

Cách kiểm chứng có giá trị là ghi và đọc qua repository hoặc template đã cấu hình, rồi quan sát biểu diễn lưu trữ cùng kiểu domain được khôi phục.

## 9. Giới hạn theo module: đặc biệt phân biệt với JPA

| Ngữ cảnh | Cách tiếp cận cần xem xét |
| --- | --- |
| Spring Data MongoDB | Mongo custom conversions và mapping converter của module |
| Spring Data JDBC hoặc R2DBC | Conversions, kiểu dữ liệu driver và điểm mở rộng của relational module tương ứng |
| Spring Data JPA, chuyển đổi thuộc tính entity | Cơ chế của JPA/provider, thường là `AttributeConverter` khi phù hợp |
| Web binding hoặc application service | Conversion service của chính ngữ cảnh đó |
| JSON serialization | Cấu hình serializer/deserializer tương ứng |

Đặc biệt, hai kiểu sau không phải một interface:

```java
org.springframework.core.convert.converter.Converter
jakarta.persistence.AttributeConverter
```

Một converter core được đưa vào `CustomConversions` không tự trở thành JPA attribute converter. Ngược lại, một JPA attribute converter không tự được đăng ký vào conversion service dùng cho tham số web.

Tương tự, khả năng chuyển đổi một value object thành `String` không có nghĩa một driver bất kỳ nhận mọi object domain mà không cần cấu hình thêm.

Ở đường truy vấn, việc chuyển đổi giá trị điều kiện, giá trị ghi và kết quả projection còn tùy query mapper hoặc API của module. Cần kiểm tra riêng use case; không kết luận rằng một converter đọc entity sẽ tự sửa mọi DTO mapping hoặc mọi truy vấn native.

## 10. Chuyển đổi kiểu không thay thế việc tạo object và mapping tên

Ba công việc sau liên quan nhưng khác nhau:

```text
Tên lưu trữ -> thuộc tính Java
Kiểu giá trị nguồn -> kiểu thuộc tính hoặc đối số creator
Các giá trị đã chuẩn bị -> entity hoặc DTO
```

Ví dụ, một cột hoặc field có tên `product_code` cần được ánh xạ tới property `code`. Converter `String -> ProductCode` giải quyết kiểu của giá trị, không tự sửa một cấu hình tên property sai.

Nếu persistence creator cần `code` nhưng query không cung cấp nó, converter cũng không tự truy vấn lại để tìm dữ liệu còn thiếu.

Tương tự, constructor của entity vẫn có invariant riêng. Sau khi chuyển đổi thành `ProductCode`, hạ tầng còn phải cấp các thuộc tính khác và dựng entity theo cơ chế được hỗ trợ.

Nếu object có vẻ được lưu dưới cấu trúc lạ, cần kiểm tra cả mapping metadata và conversions. Nếu lỗi nằm ở tên tham số creator hoặc dữ liệu không đủ, chỉ thêm converter thường không giải quyết đúng nguyên nhân.

## 11. Null, dữ liệu không hợp lệ và tính ổn định của converter

### 11.1. Null không mặc định đi qua convert như giá trị thông thường

Trong cơ chế conversion của Spring, null thường được xử lý ở tầng conversion service hoặc mapping; không thiết kế một `Converter<S, T>` với giả định nó chắc chắn được gọi cùng `source == null` cho mọi property thiếu.

Vì vậy, việc converter không chấp nhận null không tự đặt ra chính sách nullability cho toàn entity. Nếu một property bắt buộc, cần hợp đồng domain và mapping phù hợp. Nếu property tùy chọn, cần xác định null được giữ hoặc biểu diễn thế nào trong store.

Không dùng converter mã sản phẩm để âm thầm thay null bằng `"SKU-0000"`. Điều đó biến dữ liệu chưa biết thành một mã có vẻ hợp lệ và có thể làm nhiều bản ghi dùng chung một giá trị giả.

### 11.2. Dữ liệu sai phải được phân biệt với thiếu converter

Có ba nhóm lỗi thường gặp:

| Nhóm lỗi | Ví dụ | Nơi cần kiểm tra |
| --- | --- | --- |
| Không có đường chuyển đổi | Chưa đăng ký `String -> ProductCode` | Registry và cấu hình conversions thực tế |
| Có converter nhưng dữ liệu sai | Store chứa `"not-a-code"` | Hợp đồng dữ liệu và nguyên nhân từ converter |
| Converter chạy nhưng mapping vẫn sai | Property bị map nhầm tên hoặc creator thiếu dữ liệu | Mapping metadata, query và object instantiation |

Không bắt mọi exception rồi trả một value object mặc định. Cách đó làm mất khả năng phân biệt lỗi cấu hình với dữ liệu cũ không hợp lệ.

### 11.3. Converter nên tập trung vào biểu diễn giá trị

Converter dùng chung nên tránh phụ thuộc vào trạng thái thay đổi của request, phiên làm việc hoặc thứ tự được gọi. Những implementation như ví dụ chỉ đọc đầu vào và tạo đầu ra nên dễ dùng đồng thời hơn.

Cũng nên tránh gọi repository từ converter để tải thêm dữ liệu. Nếu một phép chuyển kiểu âm thầm thực hiện I/O, một query đọc nhiều entity có thể phát sinh thêm nhiều truy vấn, tạo vòng phụ thuộc hoặc làm hành vi khó dự đoán.

Nếu nghiệp vụ cần enrichment hoặc phối hợp nhiều nguồn dữ liệu, hãy thể hiện bằng service, fragment hoặc một bước xử lý riêng có hợp đồng rõ ràng.

## 12. Phạm vi converter là một quyết định thiết kế

Một converter đăng ký theo cặp kiểu có thể ảnh hưởng đến nhiều property dùng cùng kiểu trong phạm vi mapping đã cấu hình.

Ví dụ, `ProductCode -> String` có phạm vi khá rõ vì kiểu domain diễn đạt một ý nghĩa cụ thể. Ngược lại, một converter chung `String -> String` để trim mọi giá trị có thể thay đổi cả mã, mô tả và dữ liệu mà khoảng trắng có ý nghĩa.

Nếu hai property cùng kiểu Java cần biểu diễn khác nhau, cân nhắc:

- Tách thành các value object có ý nghĩa riêng.
- Dùng cơ chế chuyển đổi theo property nếu module hỗ trợ.
- Viết mapping tường minh tại ranh giới thích hợp.

Không tạo nhiều converter cùng cặp kiểu rồi dựa vào thứ tự quét bean như một cơ chế chọn theo tên property. `Converter<S, T>` đơn giản không nhận tên property làm tham số của `convert(S source)`.

Nếu cần metadata thuộc tính hoặc chuyển đổi có điều kiện, hãy chọn API mở rộng được hỗ trợ cho yêu cầu đó và kiểm tra cách module tích hợp; đừng gán thêm khả năng cho interface đơn giản này.

## 13. Kiểm chứng từ logic chuyển đổi đến persistence thực tế

Có thể chia thành ba mức, mỗi mức xác nhận một điều khác nhau.

### 13.1. Logic converter

Với hai converter của bài:

```java
ProductCodeWritingConverter writer = new ProductCodeWritingConverter();
ProductCodeReadingConverter reader = new ProductCodeReadingConverter();

ProductCode code = new ProductCode("SKU-0042");

assertEquals("SKU-0042", writer.convert(code));
assertEquals(code, reader.convert("SKU-0042"));
assertEquals(code, reader.convert(writer.convert(code)));
```

Các assertion minh họa cách dùng framework kiểm thử như JUnit. Cần thêm dữ liệu không hợp lệ để xác nhận nó không bị sửa âm thầm.

### 13.2. Registry và metadata conversions

Xác nhận service đúng phạm vi đã nhận hai hướng chuyển đổi. Với persistence, xác nhận conversions của module nhận diện custom read/write target và mapping context dùng cấu hình tương ứng.

Không chỉ kiểm tra một `DefaultConversionService` được tạo riêng trong test rồi kết luận cấu hình repository đã đúng.

### 13.3. Đọc và ghi qua store

Với module đã chọn, kiểm tra:

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Lưu entity chứa `ProductCode` | Giá trị được lưu theo kiểu và cấu trúc dự kiến |
| Đọc entity đó | Property được khôi phục thành `ProductCode` đúng giá trị |
| Đọc dữ liệu lưu từ trước | Hợp đồng cũ được hỗ trợ rõ ràng hoặc bị từ chối có nguyên nhân |
| Property null hoặc thiếu | Đúng chính sách nullability của domain và store |
| Dùng value object trong điều kiện query | Query mapper của module xử lý giá trị đúng nếu use case đó được hỗ trợ |
| Dùng DTO hoặc projection | Kiểu kết quả được tạo theo đúng hợp đồng của API tương ứng |

Quan sát biểu diễn lưu trữ rất hữu ích. Chỉ thấy object đọc lại bằng object ban đầu chưa chứng minh store đã lưu chuỗi thay vì một object con, vì một cấu hình khác cũng có thể round-trip theo cấu trúc khác.

## 14. Bài tập thực hành

Trong một dự án đã cấu hình module Spring Data cụ thể:

1. Tạo value object `ProductCode` với hợp đồng dữ liệu rõ ràng.
2. Viết hai converter riêng cho chiều đọc và chiều ghi.
3. Đăng ký chúng vào một conversion service độc lập để quan sát chuyển đổi giá trị.
4. Đăng ký tiếp qua cơ chế custom conversions của đúng module persistence, giữ lại cấu hình nền của store.
5. Lưu một entity, kiểm tra biểu diễn bên ngoài rồi đọc lại value object.
6. Thử một chuỗi sai định dạng và phân biệt lỗi dữ liệu với thiếu converter.
7. Thử property null hoặc thiếu nếu mô hình và store hỗ trợ; không giả định converter sẽ luôn nhận null.
8. Giải thích vì sao đăng ký converter cho web hoặc tạo một service trong unit test chưa bảo đảm repository sử dụng nó.

Cách sử dụng đúng bắt đầu từ việc tách ba trách nhiệm: **converter định nghĩa phép biến đổi**, **conversion service thực hiện các phép biến đổi đã đăng ký**, còn **custom conversions nối tập chuyển đổi với metadata và hạ tầng persistence của Spring Data**. Hợp đồng cuối cùng phải được kiểm chứng trên đúng module và kiểu kho dữ liệu của ứng dụng.

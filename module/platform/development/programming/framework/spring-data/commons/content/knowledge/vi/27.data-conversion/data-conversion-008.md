# Chuyển đổi theo kiểu hoặc theo thuộc tính trong phạm vi hỗ trợ

## 1. Chọn phạm vi chuyển đổi từ yêu cầu dữ liệu

Trong chương **Chuyển đổi dữ liệu** của module `SPRING_DATA_COMMONS`, cần phân biệt hai yêu cầu có vẻ giống nhau nhưng có phạm vi khác nhau:

- Mọi giá trị `ProductCode` đi qua mapper đang cấu hình đều dùng một biểu diễn lưu trữ thống nhất.
- Chỉ thuộc tính `CatalogEntry.supplierReference` cần dùng định dạng riêng, còn các thuộc tính `String` khác vẫn giữ cách lưu thông thường.

Yêu cầu thứ nhất phù hợp với chuyển đổi **theo kiểu**. Yêu cầu thứ hai phù hợp với chuyển đổi **theo thuộc tính**, nếu module và phiên bản store đang sử dụng tích hợp cơ chế này.

Ví dụ, hệ thống cần lưu mã sản phẩm như một chuỗi và thêm tiền tố định dạng `v1:` cho mã tham chiếu nhà cung cấp. Một document mong muốn có thể là:

```json
{
  "code": "P-204",
  "supplierReference": "v1:SUP-204",
  "displayLabel": "Bộ linh kiện 204"
}
```

Trong domain, `code` là value object `ProductCode`, còn `supplierReference` và `displayLabel` đều là `String`. Không nên đăng ký một converter `String -> String` cho toàn bộ mapping chỉ để xử lý riêng `supplierReference`.

Bài học tập trung vào abstraction dùng chung của Spring Data Commons: hợp đồng converter, phạm vi đăng ký, metadata thuộc tính và cách xác định giới hạn tích hợp. Các ví dụ cấu hình MongoDB bên dưới được đánh dấu cụ thể; chúng không phải cấu hình dùng chung cho mọi repository Spring Data.

## 2. Phân biệt các abstraction

| Thành phần | Vai trò | Phạm vi cần hiểu |
| --- | --- | --- |
| `Converter<S, T>` | Chuyển giá trị từ kiểu nguồn sang kiểu đích | Cặp kiểu trong conversion service được cấu hình |
| `@ReadingConverter` | Đánh dấu hướng từ biểu diễn store về domain | Hướng đọc của custom conversion |
| `@WritingConverter` | Đánh dấu hướng từ domain sang biểu diễn store | Hướng ghi của custom conversion |
| `CustomConversions` | Quản lý đăng ký converter và thông tin kiểu chuyển đổi | Hạ tầng mapping sử dụng cấu hình đó |
| `PropertyValueConverter<DV, SV, C>` | Chuyển giá trị một thuộc tính giữa domain và store | Thuộc tính được chọn trong mapper có hỗ trợ |
| `@ValueConverter` | Khai báo converter cho thuộc tính | Metadata mà store phải nhận biết và xử lý |
| `PropertyValueConversions` | Tra cứu converter tương ứng với persistent property | Hạ tầng tích hợp chuyển đổi theo thuộc tính |
| `ValueConversionContext` | Cung cấp persistent property và khả năng chuyển đổi theo context | Ngữ cảnh do store cung cấp |

`Converter` là SPI chuyển đổi của Spring Framework. Trong đường gọi qua conversion service, đối số truyền vào `convert` được bảo đảm khác null; implementation cần an toàn khi dùng đồng thời và có thể báo dữ liệu không hợp lệ bằng ngoại lệ phù hợp. [Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html).

Một converter có thể được dùng bởi nhiều tầng khác nhau. Vì vậy, converter đăng ký cho HTTP binding, cấu hình ứng dụng hoặc một conversion service tự tạo không đương nhiên trở thành converter của persistence mapper. Cần xác định đúng thành phần nào đang thực hiện việc chuyển đổi.

## 3. Chuyển đổi theo kiểu: ProductCode và String

### 3.1. Value object trong domain

Ví dụ dùng Java record để giữ mã sản phẩm như một giá trị bất biến:

```java
import java.util.Objects;

public record ProductCode(String value) {

    public ProductCode {
        Objects.requireNonNull(value, "Product code is required");
        if (value.isBlank()) {
            throw new IllegalArgumentException("Product code must not be blank");
        }
    }
}
```

Ví dụ này giữ nguyên nội dung đầu vào. Nó không tự đổi chữ hoa, xóa khoảng trắng hoặc sửa mã vì các phép chuẩn hóa ấy cần là quyết định nghiệp vụ rõ ràng. Nhờ đó, hợp đồng chuyển đổi có thể được mô tả đơn giản: lưu nguyên chuỗi mà domain đang giữ, rồi tái tạo value object từ chuỗi đã lưu.

### 3.2. Hai hướng chuyển đổi riêng biệt

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class ProductCodeWriteConverter
        implements Converter<ProductCode, String> {

    @Override
    public String convert(ProductCode source) {
        return source.value();
    }
}
```

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class ProductCodeReadConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        return new ProductCode(source);
    }
}
```

Hai lớp có trách nhiệm khác nhau:

```text
Ghi: ProductCode("P-204") -> "P-204"
Đọc: "P-204"             -> ProductCode("P-204")
```

Với các giá trị hợp lệ, mong đợi `read(write(value))` bằng `value` theo phép so sánh giá trị. Điều này không đồng nghĩa đối tượng sau khi đọc phải có cùng địa chỉ trong bộ nhớ.

Spring Data dùng kiểu nguồn, kiểu đích và khả năng lưu kiểu native của store để xác định hướng chuyển đổi. Khi cả hai kiểu đều có thể là kiểu native, cần làm rõ hướng bằng annotation phù hợp. Annotation về hướng không thay thế việc đăng ký converter vào mapper. [Custom Conversions](https://docs.spring.io/spring-data/commons/reference/custom-conversions.html).

### 3.3. “Theo kiểu” có phạm vi đến đâu?

Trong mapper sử dụng cặp converter này, mọi vị trí được mapper xử lý như `ProductCode` đều là ứng viên áp dụng cùng một biểu diễn. Phạm vi đó rộng hơn một field cụ thể nhưng vẫn gắn với hạ tầng mapping đã nhận cấu hình, không phải mọi đối tượng Java trong JVM.

Việc đăng ký custom write conversion còn có thể khiến `CustomConversions` coi kiểu domain đó là simple type. Vì vậy, đừng mặc nhiên mong mapper tiếp tục lưu `ProductCode` như một object lồng có trường `value`. [CustomConversions](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/convert/CustomConversions.html).

Một hệ quả thiết kế trong ví dụ là: nếu `code` đã được lưu thành chuỗi, đường dẫn truy vấn kiểu `code.value` không còn mô tả cấu trúc dữ liệu đã lưu. Cần thiết kế truy vấn theo mapping thực tế.

Nếu cùng `ProductCode` phải có hai biểu diễn khác nhau tùy thuộc tính, một đăng ký theo kiểu duy nhất có thể quá rộng. Khi đó, xem xét property conversion được store hỗ trợ, hoặc làm rõ mô hình bằng các kiểu domain khác nhau nếu chúng đại diện những khái niệm khác nhau.

## 4. Chuyển đổi theo thuộc tính: chỉ đổi supplierReference

### 4.1. Hợp đồng PropertyValueConverter

Chữ ký khái niệm:

```java
PropertyValueConverter<DV, SV, C>
```

Trong đó:

- `DV` là kiểu giá trị trong domain.
- `SV` là kiểu giá trị thuộc biểu diễn store.
- `C` là context chuyển đổi phù hợp với store.

Ví dụ này dùng `String` ở cả hai phía nhưng thay đổi định dạng ở một thuộc tính được chọn. `read` chuyển từ store về domain; `write` chuyển từ domain sang store. Hợp đồng còn có `readNull` và `writeNull` để xử lý null riêng. [PropertyValueConverter](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/convert/PropertyValueConverter.html).

### 4.2. Converter có định dạng rõ ràng

```java
import org.springframework.data.convert.PropertyValueConverter;
import org.springframework.data.convert.ValueConversionContext;

public final class VersionedReferenceConverter
        implements PropertyValueConverter<
                String, String, ValueConversionContext<?>> {

    private static final String PREFIX = "v1:";

    @Override
    public String write(String value, ValueConversionContext<?> context) {
        return PREFIX + value;
    }

    @Override
    public String read(String value, ValueConversionContext<?> context) {
        if (!value.startsWith(PREFIX)) {
            throw new IllegalArgumentException(
                    "Unsupported supplier reference format");
        }
        return value.substring(PREFIX.length());
    }
}
```

Converter không giữ trạng thái thay đổi theo entity. Nó cũng không gọi repository, không đọc thông tin người dùng và không ghi log giá trị tham chiếu.

Các phép biến đổi cụ thể:

| Giá trị domain | Giá trị lưu | Giá trị đọc lại |
| --- | --- | --- |
| `SUP-204` | `v1:SUP-204` | `SUP-204` |
| Chuỗi rỗng | `v1:` | Chuỗi rỗng |
| `v1:SUP-204` | `v1:v1:SUP-204` | `v1:SUP-204` |

Dòng cuối cho thấy domain vẫn có thể chứa chính tiền tố đó như một phần dữ liệu. Converter tháo đúng một lớp định dạng khi đọc và thêm đúng một lớp khi ghi. Đường ghi nhận giá trị domain; truyền nhầm chuỗi đã mã hóa lưu trữ vào đường ghi sẽ làm dữ liệu có thêm một lớp tiền tố.

Đây là ví dụ về định dạng lưu trữ có phiên bản, không phải cơ chế bảo mật. Đầu đọc cố ý từ chối dữ liệu thiếu tiền tố để lỗi định dạng được nhìn thấy. Nếu kho dữ liệu đang chứa các chuỗi cũ chưa có tiền tố, cần thiết kế tương thích hoặc migration trước khi triển khai.

### 4.3. Khai báo ở đúng thuộc tính

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.convert.ValueConverter;

public class CatalogEntry {

    @Id
    private String id;

    private ProductCode code;

    @ValueConverter(VersionedReferenceConverter.class)
    private String supplierReference;

    private String displayLabel;

    public CatalogEntry() {
    }

    // Getter và setter được lược bớt để tập trung vào mapping.
}
```

`@ValueConverter` mô tả converter cho thuộc tính được đánh dấu. Annotation này yêu cầu xem tài liệu của store để biết chi tiết hỗ trợ và cách cung cấp instance converter. Chỉ việc import được annotation từ Commons chưa chứng minh persistence provider đang thực thi nó. [ValueConverter](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/convert/ValueConverter.html).

Khi mapper hỗ trợ và đã nhận cấu hình phù hợp, `supplierReference` dùng `VersionedReferenceConverter`, còn `displayLabel` không bị đổi bởi converter đó. Đây là lý do chọn phạm vi thuộc tính thay vì đăng ký một converter áp dụng chung cho kiểu `String`.

## 5. Đăng ký và tích hợp với store

### 5.1. Không nhầm annotation về hướng với đăng ký

`@ReadingConverter` và `@WritingConverter` mô tả vai trò của converter, không phải yêu cầu tự động quét mọi lớp converter vào persistence mapper. Tương tự, một bean converter tồn tại trong container chưa đủ để kết luận mapping đang sử dụng nó.

Quá trình tích hợp cần nối đủ các mắt xích:

```text
Converter theo kiểu
  -> cấu hình CustomConversions của store
  -> mapper thực tế được repository hoặc template sử dụng

Converter theo thuộc tính
  -> metadata thuộc tính hoặc registry
  -> PropertyValueConversions và factory phù hợp
  -> mapper của store có tích hợp cơ chế này
```

Sơ đồ mô tả trách nhiệm cấu hình, không khẳng định một thứ tự ưu tiên cố định giữa mọi loại converter trong mọi module.

### 5.2. Ví dụ cấu hình Spring Data MongoDB

Trong ứng dụng MongoDB sử dụng cấu hình tự động tiếp nhận bean `MongoCustomConversions`, có thể khai báo hai converter theo kiểu như sau:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

@Configuration(proxyBeanMethods = false)
public class CatalogConversionConfiguration {

    @Bean
    MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(adapter -> {
            adapter.registerConverter(new ProductCodeReadConverter());
            adapter.registerConverter(new ProductCodeWriteConverter());
        });
    }
}
```

Nếu ứng dụng tự tạo `MappingMongoConverter`, phải nối cấu hình conversions vào đúng instance converter đó theo cơ chế khởi tạo của ứng dụng. Không tạo thêm một mapper độc lập rồi cho rằng repository sẽ tự chuyển sang dùng nó. Spring Data MongoDB có điểm cấu hình converter riêng và tài liệu mô tả việc đăng ký vào hạ tầng mapping của MongoDB. [MongoDB Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html).

Trong cấu hình MongoDB hỗ trợ property conversion, annotation ở `CatalogEntry.supplierReference` được xử lý qua cơ chế property converter. Nếu thay đổi cấu hình property conversions mặc định, cần bảo đảm cấu hình mới vẫn phục vụ đúng các khai báo đang dùng.

### 5.3. Đăng ký theo thuộc tính bằng chương trình

Nếu không muốn đặt annotation trong domain, có thể đăng ký theo lớp chủ sở hữu và tên thuộc tính. Ví dụ sau là **phương án thay thế** cho annotation ở `supplierReference` trong ứng dụng MongoDB:

```java
import org.springframework.data.convert.PropertyValueConversions;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;
import org.springframework.data.mongodb.core.mapping.MongoPersistentProperty;

PropertyValueConversions propertyConversions =
        PropertyValueConversions.<MongoPersistentProperty>simple(registrar -> {
            registrar.registerConverter(
                    CatalogEntry.class,
                    "supplierReference",
                    new VersionedReferenceConverter());
        });

MongoCustomConversions conversions = MongoCustomConversions.create(adapter -> {
    adapter.registerConverter(new ProductCodeReadConverter());
    adapter.registerConverter(new ProductCodeWriteConverter());
    adapter.setPropertyValueConversions(propertyConversions);
});
```

Đoạn mã tạo cấu hình cần được trả về hoặc nối vào mapper tại điểm cấu hình thực tế; biến local `conversions` tự nó chưa đăng ký gì vào ứng dụng. `PropertyValueConversions` cung cấp tra cứu theo persistent property, còn registrar dùng để xây dựng đăng ký cho thuộc tính được chọn. [PropertyValueConversions](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/convert/PropertyValueConversions.html), [PropertyValueConverterRegistrar](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/convert/PropertyValueConverterRegistrar.html).

Trong ví dụ này, bỏ annotation của `supplierReference` nếu chọn registry làm nguồn cấu hình. Tránh khai báo cùng một thuộc tính theo nhiều cách rồi dựa vào một thứ tự ghi đè chưa được xác định.

Tài liệu property conversion của MongoDB cũng nêu giới hạn đăng ký: không dùng dot notation như `address.street` để tự điều hướng qua thuộc tính lồng. Cần đăng ký converter ở kiểu thực sự sở hữu thuộc tính tương ứng. [MongoDB Property Converters](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/property-converters.html).

## 6. Context và vòng đời converter

`ValueConversionContext` cung cấp persistent property đang được xử lý. Ví dụ có thể lấy tên thuộc tính để xây thông báo lỗi có ý nghĩa:

```java
String propertyName = context.getProperty().getName();
```

Context còn có API đọc và ghi để ủy quyền cho chuyển đổi theo ngữ cảnh của store. Không nên suy rằng nó luôn cung cấp toàn bộ entity chủ sở hữu, mọi field kế bên, transaction hiện tại hoặc danh tính người dùng. Các mở rộng cụ thể thuộc về implementation của store. [ValueConversionContext](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/convert/ValueConversionContext.html).

Chỉ gọi chuyển đổi qua context khi hiểu rõ biểu diễn đầu vào và kiểu đích. Converter tự gọi lại một đường chuyển đổi dẫn về chính nó có thể tạo vòng lặp; gọi lại mà không có nhu cầu cũng làm khó xác định nơi dữ liệu bị thay đổi.

Về cách cung cấp instance, `PropertyValueConverterFactory` có các cơ chế tạo đơn giản, tra cứu thông qua bean factory, kết hợp factory và cache. Factory đơn giản hỗ trợ constructor không tham số hoặc enum; dependency injection đòi hỏi cấu hình factory thích hợp. [PropertyValueConverterFactory](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/convert/PropertyValueConverterFactory.html).

Ví dụ `VersionedReferenceConverter` không khai báo constructor nên có constructor không tham số phù hợp. Nếu đổi sang converter cần một dịch vụ cấu hình, việc thêm constructor có tham số phải đi kèm thay đổi cách cung cấp instance.

Hãy coi converter là thành phần có thể được dùng lại giữa nhiều lời gọi. Không lưu entity hiện tại, tenant hiện tại hoặc kết quả tạm vào field mutable của converter. Đặt dữ liệu tạm trong local variable và giữ phép chuyển đổi có kết quả xác định theo hợp đồng đã chọn.

## 7. Null, dữ liệu thiếu và hợp đồng khứ hồi

Đối với `PropertyValueConverter`, phương thức `read` và `write` xử lý giá trị khác null; `readNull` và `writeNull` là các hook riêng, mặc định giữ null. Vì vậy converter tiền tố ở trên không cần tự nối tiền tố cho null.

Cần tách các trường hợp:

| Trạng thái | Quyết định cần có |
| --- | --- |
| Domain nhận null | Có được phép lưu không; mapper bỏ thuộc tính hay ghi null? |
| Store chứa null | Trả null hay áp dụng chính sách đặc biệt? |
| Store không có thuộc tính | Mapping và khởi tạo entity xử lý thế nào? |
| Chuỗi rỗng | Là dữ liệu hợp lệ hay vi phạm domain? |
| Chuỗi sai định dạng | Báo lỗi, đọc theo định dạng cũ hay thực hiện migration? |

Null, thuộc tính vắng mặt và chuỗi rỗng không phải ba tên gọi cho cùng một trạng thái. Chính sách mapper bỏ qua một field có thể khiến converter không được gọi theo cách người viết dự đoán. Cần kiểm chứng bằng dữ liệu lưu thực tế và module store đang dùng.

Với ví dụ:

- `ProductCode` không cho phép null hoặc chuỗi trắng bên trong value object; chính thuộc tính `code` có được phép null hay không là quy tắc của entity và mapping.
- `VersionedReferenceConverter` phân biệt null với chuỗi rỗng, đồng thời từ chối chuỗi không có định dạng `v1:`.
- Việc thay null bằng một chuỗi sentinel cần bảo đảm sentinel không trùng dữ liệu hợp lệ và có quy tắc đọc ngược tương ứng.

Ngoài phép `read(write(domainValue))`, hãy xem cả chiều `write(read(storedValue))`. Nếu converter chuẩn hóa dữ liệu, chiều thứ hai có thể làm thay đổi biểu diễn cũ dù ý nghĩa nghiệp vụ giữ nguyên. Sự thay đổi đó phải là quyết định có chủ đích, đặc biệt khi đọc rồi lưu lại một entity cũ.

## 8. Ranh giới của repository, truy vấn và cập nhật

Một phép lưu rồi đọc thành công chỉ xác nhận một phần đường mapping. Các đường khác có thể đi qua mapper khác, thiếu metadata thuộc tính hoặc bỏ qua mapping hoàn toàn.

### 8.1. Tham số truy vấn

Giả sử repository có phương thức:

```java
List<CatalogEntry> findBySupplierReference(String supplierReference);
```

Domain truyền `SUP-204`, còn store giữ `v1:SUP-204`. Để truy vấn khớp, đường query mapping phải xử lý giá trị đúng theo cấu hình của thuộc tính. Không suy từ việc `save` đã chạy converter rằng mọi dạng truy vấn đều làm điều tương tự.

Cần xác minh riêng derived query, Query by Example, query khai báo và truy vấn tạo bằng template trong phạm vi sản phẩm thực sự dùng. Dữ liệu raw có thể khác dữ liệu domain; tự thêm `v1:` tại service trong khi query mapper cũng thêm tiền tố sẽ tạo ra giá trị hai lớp và không tìm thấy bản ghi.

### 8.2. Sắp xếp và toán tử

Store sắp xếp và so sánh theo biểu diễn đã lưu cùng quy tắc của store. Chuyển một số sang chuỗi có thể làm thứ tự từ điển khác thứ tự số học. Một phép chuyển đổi không bảo toàn thứ tự cũng không thể tự bảo đảm ý nghĩa cho toán tử khoảng.

Định dạng tiền tố trong ví dụ không chứng minh được rằng mọi toán tử `contains`, regex, range hoặc sắp xếp đều giữ nguyên ý nghĩa domain. Phân trang chỉ chia kết quả; nó không sửa được một điều kiện truy vấn đã so sánh sai biểu diễn.

### 8.3. Cập nhật trực tiếp, projection và dữ liệu raw

| Đường thao tác | Điều cần xác minh |
| --- | --- |
| Lưu và đọc entity | Đúng converter, kiểu đích và quy tắc null |
| Partial update hoặc bulk update | Có metadata thuộc tính và có áp dụng converter không? |
| Projection hoặc kết quả tổng hợp | Kết quả có đi qua mapping thuộc tính domain hay mapper khác? |
| Native query, raw document hoặc driver trực tiếp | Có bỏ qua mapping của Spring Data không? |
| Script import dữ liệu | Có tuân thủ cùng định dạng lưu trữ không? |

Đọc một raw document để quan sát `v1:SUP-204` không phải lỗi converter: đó chính là biểu diễn lưu trữ của ví dụ. Ngược lại, nếu một đường ghi raw đưa thẳng `SUP-204` vào store, đầu đọc nghiêm ngặt sẽ từ chối dữ liệu đó.

Chuyển đổi dữ liệu cũng không thay thế auditing. Việc điền người tạo, người sửa hoặc thời điểm cập nhật cần abstraction và cấu hình auditing phù hợp; converter nên tập trung vào biểu diễn giá trị.

## 9. Hiểu đúng “trong phạm vi hỗ trợ”

Spring Data Commons cung cấp hợp đồng dùng chung; module store quyết định mức tích hợp vào đường đọc, ghi và truy vấn.

| Môi trường | Cách tiếp cận |
| --- | --- |
| Mapper Spring Data có hỗ trợ custom conversion theo kiểu | Đăng ký vào cấu hình conversions của mapper đó |
| Mapper có hỗ trợ property value conversion | Dùng annotation hoặc registry được module tiếp nhận |
| Persistence của JPA | Dùng cơ chế attribute conversion của Jakarta Persistence và provider |
| JDBC, R2DBC hoặc module store khác | Xem API đăng ký và giới hạn của đúng module, đúng phiên bản |
| JSON của HTTP API | Dùng serializer/deserializer hoặc mapping DTO tương ứng |
| Thư viện gọi driver trực tiếp | Tự áp dụng hợp đồng biểu diễn hoặc nối converter vào pipeline phù hợp |

Với JPA, `AttributeConverter<X, Y>` định nghĩa chuyển đổi giữa kiểu thuộc tính entity và kiểu basic dùng cho biểu diễn cột; `@Convert` điều khiển áp dụng theo thuộc tính. Đây là cơ chế của Jakarta Persistence, không phải cách đổi tên cho `PropertyValueConverter`. [Jakarta Persistence AttributeConverter](https://jakarta.ee/specifications/webprofile/11/apidocs/jakarta/persistence/AttributeConverter.html).

Vì vậy, không chuyển nguyên cấu hình `MongoCustomConversions` sang ứng dụng JPA, cũng không chỉ thêm `@ValueConverter` rồi kỳ vọng provider JPA tự hiểu. Với ID, version, quan hệ hoặc các kiểu mapping đặc biệt, phải tuân thủ thêm giới hạn của cơ chế chuyển đổi đang dùng.

Khi xác định hỗ trợ, cần trả lời ba câu hỏi: phiên bản này có API không, mapper đang chạy có tích hợp API đó không, và đường thao tác cụ thể có đi qua phần tích hợp ấy không. Có đủ lớp trong dependency mới chỉ trả lời câu hỏi đầu tiên.

## 10. Kiểm chứng trong một bài thực hành

Một bài thực hành có ý nghĩa cần quan sát cả domain và biểu diễn store. Các tình huống sau có thể dùng khi xây kiểm thử cho ứng dụng tích hợp thực tế:

| Tình huống | Kết quả mong muốn trong ví dụ |
| --- | --- |
| Chuyển `ProductCode("P-204")` rồi đọc lại | Khôi phục value object bằng giá trị ban đầu |
| Lưu `supplierReference = "SUP-204"` | Store giữ `v1:SUP-204` |
| Lưu `displayLabel = "Bộ linh kiện 204"` | Thuộc tính không nhận tiền tố |
| Đọc supplier reference có tiền tố | Domain nhận phần dữ liệu sau một lớp `v1:` |
| Đọc chuỗi thiếu tiền tố | Báo định dạng không được hỗ trợ |
| Lưu và đọc null hoặc chuỗi rỗng | Theo đúng chính sách đã công bố cho từng thuộc tính |
| Tìm kiếm bằng giá trị domain | Khớp biểu diễn store trên đường query mapping được hỗ trợ |
| Ghi qua đường raw | Chỉ thành công về mặt hợp đồng nếu dữ liệu tuân thủ định dạng |

Kiểm tra converter riêng lẻ giúp xác nhận phép biến đổi. Kiểm tra qua repository hoặc template giúp xác nhận đăng ký, metadata và đường mapping. Hai mức này trả lời những câu hỏi khác nhau; một lời gọi trực tiếp `new ProductCodeWriteConverter().convert(...)` không chứng minh mapper đã sử dụng converter.

Nên thêm một thuộc tính cùng kiểu nhưng không được cấu hình chuyển đổi để phát hiện phạm vi quá rộng. Ví dụ, nếu `displayLabel` cũng có `v1:`, hãy tìm một converter `String -> String` hoặc một cấu hình mapping chung đã vô tình áp dụng.

Với dữ liệu tồn tại từ trước, lấy mẫu biểu diễn cũ, giá trị biên và định dạng lỗi. Không che lỗi bằng cách trả một mã rỗng: điều đó làm entity có vẻ đọc thành công nhưng đã mất thông tin.

## 11. Lựa chọn trong các tình huống thường gặp

| Nhu cầu | Lựa chọn ban đầu | Lý do |
| --- | --- | --- |
| Mã sản phẩm có cùng định dạng ở mọi nơi mapper sử dụng | Value object và converter theo kiểu | Hợp đồng biểu diễn gắn với khái niệm domain |
| Một thuộc tính String có định dạng riêng | Property conversion khi store hỗ trợ | Giữ các thuộc tính String khác ngoài phạm vi |
| Không thể sửa lớp domain | Registry theo thuộc tính khi có tích hợp | Tách cấu hình khỏi annotation trong model |
| Thay đổi toàn bộ cấu trúc aggregate | Thiết kế mapping riêng hoặc converter cho cấu trúc lớn, sau khi cân nhắc | Converter cấp giá trị có thể không đủ mô tả quan hệ dữ liệu |
| Đổi dạng trình bày ngày giờ trên API | DTO và serialization | Nhu cầu thuộc lớp giao tiếp |
| Store thiếu property conversion cần thiết | Tách value object, adapter hoặc cơ chế mapping riêng của store | Chọn một điểm mở rộng có hỗ trợ thực tế |

Không đăng ký thêm nhiều converter trùng cặp kiểu chỉ để thử xem converter nào được chọn. Làm rõ phạm vi, hướng chuyển đổi và mapper tiêu thụ trước khi bổ sung implementation.

Chuyển đổi theo kiểu phù hợp khi biểu diễn là thuộc tính ổn định của một kiểu domain. Chuyển đổi theo thuộc tính phù hợp khi quy tắc gắn với một vị trí cụ thể trong mô hình. Cả hai chỉ có hiệu lực khi đã được nối vào đúng hạ tầng mapping, và tính đúng đắn phải bao phủ cả dữ liệu lưu lẫn các đường truy vấn mà ứng dụng sử dụng.

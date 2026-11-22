# Khởi tạo mapper và lựa chọn cách cấu hình theo phiên bản

Trong Jackson, `ObjectMapper` là điểm vào quen thuộc của tầng data binding: nó chuyển đối tượng Java thành dữ liệu và đọc dữ liệu để tạo lại đối tượng. Tuy nhiên, cách khởi tạo và cấu hình mapper phụ thuộc đáng kể vào major version đang dùng. Jackson 2.x cho phép cấu hình trực tiếp trên mapper; Jackson 3.x chuyển sang mô hình builder và mapper bất biến.


Khi xây dựng một ứng dụng, cần xác định đồng thời phiên bản Jackson, phiên bản Java, định dạng dữ liệu, các module cần đăng ký và thời điểm cấu hình hoàn tất. Một đoạn code khởi tạo đúng với Jackson 2 có thể không biên dịch hoặc có hành vi khác khi chuyển sang Jackson 3.

## 1. ObjectMapper được khởi tạo để làm gì?

`ObjectMapper` phối hợp nhiều thành phần để thực hiện serialization và deserialization:

- **Factory** tạo parser để đọc dữ liệu và generator để ghi dữ liệu. Với JSON, thành phần này thường là `JsonFactory`.
- **Configuration** quyết định cách Jackson phát hiện thuộc tính, xử lý giá trị thiếu/null, định dạng ngày giờ, enum, unknown property và nhiều quy tắc khác.
- **Modules** bổ sung serializer, deserializer, annotation introspector hoặc quy tắc binding cho những kiểu Java và thư viện cụ thể.
- **Cache** lưu thông tin serializer/deserializer đã được tạo để tái sử dụng trong các lần đọc/ghi tiếp theo.

Luồng sử dụng phổ biến:

```text
Khởi tạo factory (nếu cần cấu hình streaming)
             |
             v
Khởi tạo mapper / builder
             |
             +---- cấu hình feature
             |
             +---- đăng ký module
             |
             +---- cấu hình visibility, naming, date/time...
             |
             v
           build()
             |
             v
Mapper sẵn sàng đọc và ghi dữ liệu
             |
       +-----+-----+
       |           |
       v           v
  ObjectReader  ObjectWriter
  (đọc)         (ghi)
```

Với JSON đơn giản, mapper mặc định thường đủ để bắt đầu. Khi ứng dụng có kiểu dữ liệu đặc biệt, hợp đồng API riêng hoặc yêu cầu định dạng cụ thể, cần cấu hình thêm trước khi đưa mapper vào sử dụng.

## 2. Khởi tạo và cấu hình trong Jackson 2.x

Jackson 2.x vẫn là nhánh được sử dụng rộng rãi trong nhiều hệ thống hiện hữu. Các package Java thường bắt đầu bằng `com.fasterxml.jackson`, ví dụ `com.fasterxml.jackson.databind.ObjectMapper`.

### 2.1. Khởi tạo mapper mặc định

Cách ngắn nhất là gọi constructor không tham số:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
```

Mapper này dùng cấu hình mặc định và factory JSON mặc định. Có thể sử dụng ngay để đọc/ghi các kiểu Java mà Jackson đã hỗ trợ:

```java
String json = mapper.writeValueAsString(order);
Order restored = mapper.readValue(json, Order.class);
```

Đây là lựa chọn phù hợp cho ví dụ nhỏ hoặc khi hợp đồng dữ liệu không cần tùy chỉnh. Trong ứng dụng thực tế, mapper thường được tạo một lần, cấu hình đầy đủ rồi tái sử dụng qua dependency injection hoặc một thành phần dùng chung.

### 2.2. Cấu hình trực tiếp trên ObjectMapper

Trong Jackson 2.x, mapper có các phương thức như `enable()`, `disable()`, `configure()`, `registerModule()`, `setDateFormat()` và `setSerializationInclusion()`.

```java
ObjectMapper mapper = new ObjectMapper();

mapper.enable(SerializationFeature.INDENT_OUTPUT);
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
mapper.registerModule(new JavaTimeModule());
```

Cách này dễ đọc và vẫn được hỗ trợ trong dòng 2.x. Nó đặc biệt thường gặp trong code cũ hoặc khi làm việc với phiên bản trước 2.10.

Điểm cần giữ đúng là **hoàn tất mọi cấu hình trước lần đọc hoặc ghi đầu tiên**. `ObjectMapper` của Jackson 2.x có thể được dùng an toàn đồng thời khi đã cấu hình xong, nhưng thay đổi cấu hình sau khi mapper bắt đầu hoạt động không an toàn. Những luồng xử lý khác nhau có thể quan sát cấu hình khác nhau hoặc gặp lỗi do cache đã được tạo theo cấu hình cũ.

Không nên để một request tùy ý gọi `mapper.enable(...)` hoặc `mapper.registerModule(...)` trên mapper singleton dùng chung. Nếu mỗi thao tác cần chính sách khác nhau, hãy xem `ObjectReader` và `ObjectWriter` ở phần sau.

### 2.3. Dùng Builder từ Jackson 2.10 trở lên

Từ Jackson 2.10, có thể cấu hình mapper theo Builder API. Với JSON, builder chuyên biệt là `JsonMapper.builder()`:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

JsonMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .enable(SerializationFeature.INDENT_OUTPUT)
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();
```

Các thao tác cấu hình được gom trước lời gọi `build()`. Nhờ đó, người đọc dễ nhận ra mapper được tạo với những chính sách nào và mapper không bị đưa vào sử dụng trước khi cấu hình hoàn tất.

Builder API cũng là lựa chọn thuận tiện khi dự án dự kiến nâng cấp lên Jackson 3. Cú pháp khởi tạo và nhiều lời gọi cấu hình qua builder tương đồng với 3.x, dù mapper được tạo bởi Jackson 2.x vẫn giữ khả năng cấu hình trực tiếp để bảo đảm tương thích ngược.

**Lưu ý:** Builder trong Jackson 2.x không biến `ObjectMapper` thành đối tượng bất biến hoàn toàn. Sau `build()`, các phương thức cấu hình trực tiếp trên mapper vẫn tồn tại. Vì vậy vẫn phải tuân thủ nguyên tắc cấu hình trước khi dùng.

### 2.4. Đăng ký module tường minh hoặc tự khám phá

Nếu ứng dụng cần hỗ trợ Java Time, có thể đăng ký `JavaTimeModule`:

```java
JsonMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .build();
```

Nếu có nhiều module hỗ trợ trên classpath và muốn Jackson tự tìm các module có metadata service provider, Jackson 2.x cung cấp:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.findAndRegisterModules();
```

Hai cách có mục đích khác nhau:

- Đăng ký tường minh cho biết rõ mapper đang sử dụng module nào, dễ kiểm soát và phù hợp khi muốn cấu hình xác định.
- Tự khám phá thuận tiện khi ứng dụng có nhiều module tùy theo classpath. Kết quả phụ thuộc những artifact thực tế có mặt và metadata của chúng.

Không nên mặc định rằng chỉ cần thêm một dependency là mọi mapper tự tạo đều đã đăng ký module. Cần kiểm tra mapper được sử dụng trong luồng xử lý thực tế.

### 2.5. Tạo mapper với factory đã cấu hình

Đôi khi ứng dụng cần điều chỉnh hành vi ở tầng streaming, chẳng hạn cho phép cú pháp JSON mở rộng hoặc bật kiểm tra duplicate key. Có thể tạo `JsonFactory` bằng builder rồi truyền vào mapper:

```java
JsonFactory factory = JsonFactory.builder()
        .enable(JsonReadFeature.ALLOW_JAVA_COMMENTS)
        .build();

JsonMapper mapper = JsonMapper.builder(factory)
        .enable(SerializationFeature.INDENT_OUTPUT)
        .build();
```

Builder cho `JsonFactory` có từ Jackson 2.10. Việc cấu hình factory và mapper giải quyết hai lớp khác nhau:

- Factory điều khiển cách parser/generator đọc và ghi token.
- Mapper điều khiển cách token được ánh xạ với object Java.

Chỉ cấu hình factory khi ứng dụng thực sự cần thay đổi hành vi streaming. Nếu nhu cầu chỉ là format output, xử lý unknown property hoặc đăng ký module, cấu hình mapper là đủ.

## 3. Khởi tạo và cấu hình trong Jackson 3.x

Jackson 3 là major version mới, có thay đổi về package, dependency, API và giá trị mặc định. Các component 3.x yêu cầu Java 17 trở lên. Do đó, nâng phiên bản không chỉ là thay số version trong Gradle hoặc Maven.

### 3.1. Builder là cách cấu hình chính

Jackson 3 vẫn cho phép tạo mapper mặc định bằng constructor không tham số:

```java
ObjectMapper mapper = new ObjectMapper();
```

Tuy nhiên, khi cần tùy chỉnh, hãy sử dụng builder:

```java
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.SerializationFeature;
import tools.jackson.databind.json.JsonMapper;

JsonMapper mapper = JsonMapper.builder()
        .enable(SerializationFeature.INDENT_OUTPUT)
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();
```

Trong Jackson 3, `ObjectMapper`, `JsonMapper` và các factory tương ứng là những đối tượng bất biến. Không cấu hình bằng cách gọi setter hoặc `enable()/disable()` trực tiếp trên mapper sau khi đã tạo. Thay vào đó, cấu hình trên builder rồi gọi `build()`.

Cách tổ chức này tạo ra mapper có cấu hình cố định. Mapper có thể được chia sẻ giữa nhiều luồng mà không lo một luồng vô tình thay đổi chính sách của các luồng còn lại.

### 3.2. Tạo mapper theo định dạng cụ thể

Jackson 3 khuyến nghị dùng mapper gắn với định dạng. Với JSON, dùng `JsonMapper`:

```java
JsonMapper jsonMapper = JsonMapper.builder()
        .enable(SerializationFeature.INDENT_OUTPUT)
        .build();
```

Với XML, dùng `XmlMapper`:

```java
XmlMapper xmlMapper = XmlMapper.builder()
        .build();
```

Với YAML, dùng `YAMLMapper`:

```java
YAMLMapper yamlMapper = YAMLMapper.builder()
        .build();
```

Từ Jackson 3, không tạo một `ObjectMapper` chung rồi truyền factory của định dạng khác vào như cách thường thấy trong code 2.x:

```java
// Mẫu cũ trong Jackson 2.x:
ObjectMapper mapper = new ObjectMapper(new YAMLFactory());
```

Hãy chuyển sang mapper chuyên biệt tương ứng. Điều này làm rõ định dạng mà mapper chịu trách nhiệm và giữ cho API binding khớp với streaming backend của nó.

### 3.3. Cấu hình Java Time trong Jackson 3

Trong Jackson 2.x, ứng dụng thường thêm `jackson-datatype-jsr310` và đăng ký `JavaTimeModule` để hỗ trợ `java.time`. Jackson 3 đã tích hợp hỗ trợ Java Time vào `jackson-databind`, nên không cần thêm dependency hoặc đăng ký module riêng cho khả năng cơ bản này.

Cấu hình ngày giờ trong Jackson 3 sử dụng `DateTimeFeature`:

```java
import tools.jackson.databind.cfg.DateTimeFeature;
import tools.jackson.databind.json.JsonMapper;

JsonMapper mapper = JsonMapper.builder()
        .disable(DateTimeFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();
```

Trong Jackson 3, `WRITE_DATES_AS_TIMESTAMPS` đã chuyển từ `SerializationFeature` sang `DateTimeFeature` và mặc định là `false`, nghĩa là ngày giờ thường được ghi dưới dạng văn bản. Đoạn code trên thể hiện chính sách tường minh; nếu chấp nhận mặc định của Jackson 3 thì không cần gọi `disable()`.

Tương tự, hỗ trợ `Optional` và tự phát hiện tên tham số constructor cũng được tích hợp trong `databind` ở Jackson 3. Khi nâng cấp, cần rà soát và loại bỏ dependency/đăng ký của các module Java 8 cũ nếu chúng không còn được cung cấp cho major version mới.

### 3.4. Cấu hình factory bằng Builder

Factory trong Jackson 3 cũng bất biến. Nếu cần điều chỉnh cách parser/generator hoạt động, hãy cấu hình factory trước rồi truyền factory đã build vào mapper:

```java
JsonFactory factory = JsonFactory.builder()
        .enable(JsonReadFeature.ALLOW_JAVA_COMMENTS)
        .build();

JsonMapper mapper = JsonMapper.builder(factory)
        .enable(SerializationFeature.INDENT_OUTPUT)
        .build();
```

Không lấy factory từ một mapper đang chạy rồi sửa cấu hình để ảnh hưởng đến các thao tác sau đó. Khi cần chính sách streaming khác, hãy tạo factory mới bằng builder và tạo mapper mới từ factory đó.

### 3.5. Tạo cấu hình mới từ mapper hiện có

Vì mapper Jackson 3 bất biến, không thể thay đổi cấu hình của mapper hiện có. Có thể dùng `rebuild()` để lấy builder khởi đầu từ cấu hình hiện tại:

```java
JsonMapper compactMapper = JsonMapper.builder()
        .disable(SerializationFeature.INDENT_OUTPUT)
        .build();

JsonMapper prettyMapper = compactMapper.rebuild()
        .enable(SerializationFeature.INDENT_OUTPUT)
        .build();
```

`rebuild()` tạo builder mới. Khi gọi `build()`, Jackson tạo một mapper khác; `compactMapper` vẫn giữ nguyên cấu hình cũ.

Trong Jackson 2.x, `ObjectMapper.copy()` là cách thường dùng để tạo bản sao có cấu hình riêng. Phương thức này đã bị loại bỏ trong Jackson 3; hãy dùng builder hoặc `rebuild()` để tạo mapper có chính sách khác.

## 4. Những khác biệt cấu hình đáng chú ý giữa 2.x và 3.x

Khi chuyển major version, code có thể vẫn biên dịch sau khi đổi package nhưng kết quả JSON thay đổi vì default configuration đã thay đổi. Một số khác biệt dễ quan sát:

| Hành vi | Jackson 2.x | Jackson 3.x |
|---|---|---|
| Cấu hình mapper | Có thể cấu hình trực tiếp; Builder API có từ 2.10 | Cấu hình qua builder; mapper bất biến |
| Yêu cầu Java | Baseline của dòng 2.x là Java 8 | Java 17 trở lên |
| Package chính | `com.fasterxml.jackson.*` | `tools.jackson.*`, ngoại trừ annotation package dùng lại từ 2.x |
| `FAIL_ON_UNKNOWN_PROPERTIES` | Mặc định bật | Mặc định tắt |
| `FAIL_ON_TRAILING_TOKENS` | Mặc định tắt | Mặc định bật |
| Ghi ngày giờ dạng timestamp | `WRITE_DATES_AS_TIMESTAMPS` mặc định bật | `DateTimeFeature.WRITE_DATES_AS_TIMESTAMPS` mặc định tắt |
| Tích hợp Java 8 types | Thường đăng ký module JDK 8/JSR-310 riêng | Các hỗ trợ này được tích hợp trong `databind` |
| Mapper định dạng | Có thể truyền factory định dạng vào `ObjectMapper`; mapper chuyên biệt cũng có sẵn | Phải dùng mapper chuyên biệt như `JsonMapper`, `XmlMapper`, `YAMLMapper` |
| Tạo cấu hình khác | Có thể dùng `copy()` hoặc tạo mapper khác | Dùng builder hoặc `rebuild()`; `copy()` đã bị loại bỏ |

Các thay đổi default có thể ảnh hưởng trực tiếp đến hợp đồng API:

- Nếu Jackson 2 từ chối một thuộc tính lạ nhưng Jackson 3 bỏ qua thuộc tính đó, nguyên nhân có thể là `FAIL_ON_UNKNOWN_PROPERTIES`.
- Nếu Jackson 2 đọc thành công một JSON object rồi bỏ qua token dư ở cuối input, Jackson 3 có thể từ chối input đó vì `FAIL_ON_TRAILING_TOKENS` được bật mặc định.
- Nếu Jackson 2 ghi ngày giờ thành số nhưng Jackson 3 ghi thành chuỗi ISO-8601, nguyên nhân có thể là thay đổi mặc định và vị trí cấu hình của `WRITE_DATES_AS_TIMESTAMPS`.
- Nếu thứ tự thuộc tính JSON thay đổi, cần kiểm tra `MapperFeature.SORT_PROPERTIES_ALPHABETICALLY` và `@JsonPropertyOrder`.

Không nên dựa vào default để xác định hợp đồng dữ liệu quan trọng. Với trường ngày giờ, enum, unknown property hoặc thứ tự thuộc tính, hãy cấu hình tường minh khi hệ thống tích hợp yêu cầu một biểu diễn ổn định.

### 4.1. Dùng Jackson 2 defaults để hỗ trợ quá trình chuyển đổi

Jackson 3 cung cấp builder hỗ trợ một phần cấu hình mặc định của Jackson 2:

```java
JsonMapper mapper = JsonMapper.builderWithJackson2Defaults()
        .enable(SerializationFeature.INDENT_OUTPUT)
        .build();
```

Cách này hữu ích khi nâng cấp một hệ thống lớn và muốn giảm số khác biệt mặc định phải xử lý trong một lần. Tuy nhiên, đây không phải chế độ tương thích toàn phần: nó không khôi phục API đã bị xóa, package cũ, các tên class đã đổi hoặc những thay đổi không được builder này bao phủ.

Sau khi bật compatibility defaults, vẫn phải chạy kiểm thử trên dữ liệu thực tế và cấu hình rõ các hành vi quan trọng của ứng dụng.

## 5. Chọn cách cấu hình theo nhu cầu sử dụng

Không phải mọi khác biệt cấu hình đều cần tạo một mapper mới. Jackson cung cấp các mức cấu hình khác nhau để chọn đúng phạm vi tác động.

### 5.1. Cấu hình toàn cục trên mapper

Dùng cấu hình mapper cho chính sách ổn định của một nhóm xử lý, chẳng hạn:

- Module serializer/deserializer dùng chung.
- Quy tắc đặt tên và phát hiện thuộc tính.
- Chính sách xử lý unknown property.
- Quy tắc ngày giờ, timezone và enum.
- Mix-in hoặc annotation introspector.
- Factory và feature ở tầng streaming.

Với Jackson 2.x, tạo mapper rồi cấu hình xong trước lần đọc/ghi đầu tiên. Với Jackson 3.x, cấu hình tất cả trên builder và chỉ chia sẻ mapper sau khi `build()` hoàn tất.

Nếu hai nhóm API có hợp đồng dữ liệu khác nhau rõ rệt, ví dụ một API cần strict validation còn một API phải tương thích với payload legacy, nên tạo hai mapper có cấu hình riêng. Điều này giúp chính sách của nhóm này không vô tình ảnh hưởng nhóm khác.

### 5.2. Dùng ObjectReader và ObjectWriter cho từng thao tác

`ObjectReader` và `ObjectWriter` là các đối tượng cấu hình bất biến, nhẹ và có thể tạo từ mapper để áp dụng chính sách theo từng thao tác.

Ví dụ tạo writer in đẹp JSON và reader cho một kiểu cụ thể:

```java
ObjectWriter prettyWriter = mapper.writerWithDefaultPrettyPrinter();

ObjectReader orderReader = mapper.readerFor(Order.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

String json = prettyWriter.writeValueAsString(order);
Order restored = orderReader.readValue(json);
```

Cách này phù hợp khi cần thay đổi một số feature cho một lần đọc/ghi mà không làm thay đổi mapper dùng chung. Có thể tạo reader/writer theo request hoặc theo use case mà không phải khởi tạo lại toàn bộ mapper.

Tuy nhiên, reader/writer không thay thế mapper riêng khi cần thay đổi cấu trúc binding sâu như tập serializer/deserializer, mix-in hoặc module. Những trường hợp đó nên dùng mapper được cấu hình riêng.

### 5.3. Khi nào cần nhiều mapper?

Có thể tách mapper theo ranh giới hợp đồng dữ liệu:

| Nhu cầu | Cách tổ chức phù hợp |
|---|---|
| Cùng một JSON contract cho toàn ứng dụng | Một mapper dùng chung, cấu hình hoàn chỉnh từ đầu |
| Chỉ khác pretty print hoặc một feature khi đọc | Dùng `ObjectReader` / `ObjectWriter` |
| Hai API có quy tắc unknown property khác nhau | Reader riêng nếu chỉ khác feature đọc; mapper riêng nếu khác sâu hơn |
| Một nhóm kiểu cần serializer/deserializer riêng | Mapper có module riêng |
| Cùng object cần JSON và XML | `JsonMapper` và `XmlMapper` riêng |
| Cùng định dạng nhưng có hai hợp đồng không tương thích | Hai mapper riêng với cấu hình được đặt tên rõ ràng |

Không tạo mapper mới trong mỗi lần gọi service hoặc mỗi HTTP request nếu cấu hình giống nhau. Việc tạo mapper thường xuyên làm mất lợi ích cache và tăng chi phí khởi tạo.

## 6. Quản lý dependency và phiên bản

Cấu hình mapper chỉ hoạt động đúng khi các artifact Jackson trên classpath tương thích. Không nên tự chọn version độc lập cho `jackson-core`, `jackson-databind`, module datatype và module dataformat.

### 6.1. Jackson 2.x

Artifact của Jackson 2.x thường dùng groupId bắt đầu bằng `com.fasterxml.jackson`. Ví dụ với Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:<jackson-2-version>"))

    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-xml")
}
```

BOM giúp các artifact thuộc cùng hệ sinh thái dùng bộ phiên bản tương thích. Khi dự án đã dùng Spring Boot hoặc một BOM quản lý Jackson, nên ưu tiên version do dependency management của nền tảng chọn, trừ khi có lý do kỹ thuật rõ ràng để override.

### 6.2. Jackson 3.x

Các artifact chính của Jackson 3.x chuyển sang groupId `tools.jackson`; ví dụ:

```kotlin
dependencies {
    implementation(platform("tools.jackson:jackson-bom:<jackson-3-version>"))

    implementation("tools.jackson.core:jackson-databind")
    implementation("tools.jackson.dataformat:jackson-dataformat-xml")
}
```

Jackson 3 sử dụng lại artifact/package annotation 2.x. Nếu cần khai báo tường minh, `jackson-annotations` vẫn thuộc groupId `com.fasterxml.jackson.core`; thông thường dependency này được kéo theo từ các artifact cần thiết và được BOM quản lý.

Không trộn ngẫu nhiên artifact Jackson 2 và 3 trong cùng một đường binding. Vì package và API khác nhau, class thuộc `com.fasterxml.jackson.databind` không thể được dùng thay cho class `tools.jackson.databind`. Khi nâng cấp, kiểm tra dependency tree để phát hiện phiên bản 2.x bị kéo vào gián tiếp.

### 6.3. Chọn major version cho dự án

Có thể cân nhắc theo các tiêu chí sau:

| Tình huống | Hướng lựa chọn |
|---|---|
| Ứng dụng phải chạy trên Java 8 hoặc nền tảng chưa đáp ứng Java 17 | Tiếp tục dùng Jackson 2.x tương thích với nền tảng |
| Ứng dụng hiện hữu đang được framework quản lý bằng Jackson 2.x | Giữ phiên bản do framework hỗ trợ; lên kế hoạch migration riêng |
| Dự án mới chạy Java 17+ và các thư viện tích hợp hỗ trợ Jackson 3 | Ưu tiên đánh giá Jackson 3.x |
| Cần nhánh có thời gian hỗ trợ dài | Chọn nhánh LTS đang được dự án Jackson hỗ trợ, kiểm tra trạng thái trên trang Releases |
| Cần phiên bản mới nhất hoặc tính năng mới | Có thể chọn nhánh stable mới hơn, nhưng phải chấp nhận chu kỳ hỗ trợ và kiểm thử nâng cấp tương ứng |

Theo chính sách phát hành được công bố của Jackson, các nhánh LTS trong giai đoạn 3.x và 2.x được chỉ rõ trên trang release/versioning; không nên suy luận rằng mọi minor mới nhất đều là LTS. Hãy kiểm tra trạng thái nhánh trước khi khóa phiên bản trong dự án.

Nếu ứng dụng dùng Spring Boot hoặc framework tương tự, phiên bản Jackson tương thích với framework là một tiêu chí bắt buộc. Hãy để framework quản lý mapper mặc định nếu nó đã cung cấp auto-configuration. Tùy biến thông qua cơ chế builder/customizer mà phiên bản framework hỗ trợ; tránh tạo một `new ObjectMapper()` độc lập rồi dùng rải rác trong controller và service, vì các mapper đó có thể bỏ qua module hoặc chính sách mà framework đã cấu hình.

## 7. Lưu ý khi chuyển từ Jackson 2.x sang 3.x

Migration cần rà soát cả dependency, import, cấu hình và dữ liệu đầu ra.

1. **Nâng baseline Java lên 17.** Jackson 3.x yêu cầu JDK 17.
2. **Đổi groupId và package.** Phần lớn `com.fasterxml.jackson.*` chuyển sang `tools.jackson.*`. Ngoại lệ quan trọng là `com.fasterxml.jackson.annotation`, vẫn được Jackson 3 dùng.
3. **Kiểm tra annotation thuộc databind.** Ví dụ `@JsonSerialize`, `@JsonDeserialize`, `@JsonNaming` chuyển sang package `tools.jackson.databind.annotation`; nếu giữ import cũ, chúng có thể bị Jackson 3 bỏ qua.
4. **Chuyển cấu hình sang builder.** Thay các lời gọi cấu hình trực tiếp trên mapper/factory bằng `JsonMapper.builder()`, `XmlMapper.builder()`, `JsonFactory.builder()` và `build()`.
5. **Chọn mapper đúng định dạng.** Chuyển `new ObjectMapper(new YAMLFactory())` sang `YAMLMapper`, tương tự với XML và các định dạng khác.
6. **Bỏ đăng ký các module Java 8 đã tích hợp.** Rà soát `jackson-datatype-jdk8`, `jackson-datatype-jsr310` và `jackson-module-parameter-names`.
7. **Rà soát API đã đổi tên hoặc bị loại bỏ.** Ví dụ `ObjectMapper.copy()` không còn; `JsonProcessingException` được thay bằng `JacksonException`; nhiều feature và kiểu dữ liệu đã được đổi tên hoặc chuyển package.
8. **So sánh default behavior.** Kiểm tra unknown property, trailing token, ngày giờ, enum, thứ tự thuộc tính và các kiểu dữ liệu quan trọng.
9. **Kiểm thử bằng payload đại diện.** Kiểm tra cả chiều ghi và đọc, bao gồm payload legacy, null, field thiếu, field thừa, enum không nhận diện, timezone và dữ liệu lồng nhau.

Có thể nâng cấp theo từng bước: trước tiên dùng Builder API và làm rõ cấu hình trong Jackson 2.x, sau đó kiểm tra dependency/framework hỗ trợ Jackson 3, cuối cùng đổi package và xử lý các khác biệt API/default. Cách này giúp thu hẹp phạm vi nguyên nhân nếu dữ liệu đầu ra thay đổi.

## 8. Những lỗi cấu hình thường gặp

**Cấu hình mapper sau khi đã dùng.** Trong Jackson 2.x, điều này phá vỡ giả định thread-safe và có thể khiến cache không còn tương ứng với cấu hình mong muốn. Trong Jackson 3.x, API cấu hình trực tiếp đã bị loại bỏ. Hãy hoàn tất cấu hình ở builder hoặc tạo một mapper mới.

**Tạo mapper riêng lẻ ở nhiều nơi.** Những mapper này có thể không cùng module, timezone hoặc chính sách xử lý dữ liệu. Nên gom việc tạo mapper vào một cấu hình tập trung hoặc sử dụng mapper bean của framework.

**Cho rằng Builder của Jackson 2 đã làm mapper bất biến.** Builder API có từ 2.10 giúp khởi tạo có cấu trúc, nhưng mapper 2.x vẫn cho phép thay đổi trực tiếp. Chỉ Jackson 3 mới áp dụng mô hình bất biến cho mapper và factory.

**Đổi dependency nhưng giữ nguyên import.** Jackson 3 chuyển package chính sang `tools.jackson`. Một số annotation vẫn thuộc `com.fasterxml.jackson.annotation`, nhưng annotation từ databind có package mới. Thay thế hàng loạt thiếu chọn lọc có thể làm sai import.

**Chỉ kiểm tra compile mà không kiểm tra JSON.** Thay đổi default có thể không gây lỗi biên dịch nhưng làm payload khác trước. Cần có kiểm thử hợp đồng serialization/deserialization, đặc biệt khi JSON là giao diện giữa nhiều service.

**Override riêng lẻ từng artifact.** Các module Jackson cần tương thích với nhau. Hãy dùng BOM hoặc dependency management của framework thay vì pin từng version không đồng bộ.

## 9. Quy trình chọn và khởi tạo mapper

Khi bắt đầu cấu hình một mapper mới, có thể đi theo trình tự:

1. **Xác định môi trường:** Java version, Jackson major version, framework và dependency management đang dùng.
2. **Chọn định dạng:** JSON dùng `JsonMapper`; XML dùng `XmlMapper`; YAML dùng `YAMLMapper`; định dạng khác dùng mapper/factory chuyên biệt tương ứng.
3. **Chọn kiểu khởi tạo:** Jackson 2.10+ nên ưu tiên Builder API; Jackson 3.x dùng Builder cho mọi cấu hình tùy chỉnh.
4. **Đăng ký module cần thiết:** chỉ thêm module mà major version hiện tại yêu cầu; kiểm tra module đã được framework tự đăng ký hay chưa.
5. **Khai báo chính sách quan trọng:** unknown fields, trailing tokens, ngày giờ, timezone, enum, null và naming.
6. **Build một lần và tái sử dụng:** mapper được dùng chung sau khi cấu hình xong; dùng reader/writer cho khác biệt theo từng thao tác.
7. **Kiểm thử dữ liệu thực tế:** xác nhận JSON/XML/YAML đầu ra và khả năng đọc lại đúng theo hợp đồng.

Ví dụ, một dịch vụ Java 17 dùng Jackson 3 để trao đổi JSON có thể khởi tạo mapper như sau:

```java
JsonMapper mapper = JsonMapper.builder()
        .enable(SerializationFeature.INDENT_OUTPUT)
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
        .build();
```

Nếu cùng dịch vụ còn xuất XML, hãy tạo một `XmlMapper` riêng với builder của XML. Nếu một endpoint cần bỏ qua unknown property trong một thao tác cụ thể, tạo `ObjectReader` riêng thay vì thay đổi mapper dùng chung.

## 10. Kết luận

Cách khởi tạo mapper phản ánh cách Jackson quản lý cấu hình và vòng đời của đối tượng. Trong Jackson 2.x, `new ObjectMapper()` cùng cấu hình trực tiếp vẫn phổ biến, còn Builder API từ 2.10 giúp gom cấu hình và chuẩn bị cho migration. Trong Jackson 3.x, mapper và factory bất biến nên mọi cấu hình tùy chỉnh phải đi qua builder; mapper theo định dạng cũng cần được chọn rõ ràng.

Khi chọn cách cấu hình, hãy dựa trên major version, phiên bản Java, framework và hợp đồng dữ liệu. Cấu hình ổn định ở cấp mapper, cấu hình theo thao tác ở `ObjectReader`/`ObjectWriter`, và tách mapper khi hợp đồng thực sự khác nhau. Quan trọng nhất là kiểm thử kết quả serialize/deserialize thay vì giả định hai major version có cùng default.

## Tài liệu tham khảo

- [Jackson Project — phiên bản, release và BOM](https://github.com/FasterXML/jackson)
- [Jackson 3 Migration Guide](https://github.com/FasterXML/jackson/blob/main/jackson3/MIGRATING_TO_JACKSON_3.md)
- [Jackson 2.10 ObjectMapper API](https://javadoc.io/static/com.fasterxml.jackson.core/jackson-databind/2.10.0/com/fasterxml/jackson/databind/ObjectMapper.html)
- [Jackson 2.10 JsonMapper.Builder API](https://www.javadoc.io/static/com.fasterxml.jackson.core/jackson-databind/2.10.0/com/fasterxml/jackson/databind/json/JsonMapper.Builder.html)
- [Jackson 3 DateTimeFeature API](https://javadoc.io/doc/tools.jackson.core/jackson-databind/latest/tools/jackson/databind/cfg/DateTimeFeature.html)


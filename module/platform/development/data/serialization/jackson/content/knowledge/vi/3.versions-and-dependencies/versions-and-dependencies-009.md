# Nhận diện khác biệt API trước khi sử dụng ví dụ của dòng phiên bản khác

Một ví dụ Jackson có thể đúng với phiên bản mà tác giả sử dụng nhưng không biên dịch hoặc cho kết quả khác khi đưa vào dự án hiện tại. Nguyên nhân có thể nằm ở package, Maven coordinates, tên lớp/phương thức, cách cấu hình, kiểu exception hoặc giá trị mặc định đã thay đổi giữa các dòng phiên bản.

Với Jackson, cần đặc biệt phân biệt **1.x, 2.x và 3.x**. Jackson 1.x là dòng cũ dùng namespace `org.codehaus.jackson`; Jackson 2.x dùng `com.fasterxml.jackson`; Jackson 3.x dùng phần lớn namespace `tools.jackson`. Jackson 3 là một major version có thay đổi API và yêu cầu Java 17 trở lên. Vì vậy, không thể lấy một đoạn code 2.x rồi chỉ thay số version dependency thành 3.x và kỳ vọng mọi thứ hoạt động.

## 1. Bắt đầu bằng việc xác định chính xác phiên bản dự án

Trước khi sao chép ví dụ, hãy tìm câu trả lời cho ba câu hỏi:

1. Dự án đang sử dụng Jackson major version nào: 1.x, 2.x hay 3.x?
2. Dependency thực tế đến từ đâu: khai báo trực tiếp, BOM, Spring Boot dependency management hay một thư viện kéo theo bắc cầu?
3. Ví dụ được viết cho phiên bản nào, và API được sử dụng có tồn tại trong phiên bản đích hay không?

Không nên suy luận phiên bản Jackson chỉ từ phiên bản Java hoặc Spring Boot. Một ứng dụng có thể nhận Jackson qua dependency management của framework; một thư viện khác cũng có thể đưa thêm Jackson vào dependency graph. Cần xem cấu hình và dependency đã được Gradle/Maven phân giải.

### 1.1. Nhận diện qua Maven coordinates

Các dòng hiện đại có thể được nhận diện nhanh qua groupId:

| Dòng Jackson | GroupId tiêu biểu | Java package tiêu biểu |
|---|---|---|
| Jackson 1.x | `org.codehaus.jackson` | `org.codehaus.jackson...` |
| Jackson 2.x | `com.fasterxml.jackson.core` | `com.fasterxml.jackson...` |
| Jackson 3.x | `tools.jackson.core` | `tools.jackson...` |

Với Jackson 3, các module data format thường dùng groupId tương ứng dưới `tools.jackson.dataformat`. Có một ngoại lệ quan trọng: `jackson-annotations` vẫn thuộc dòng 2.x và giữ group/package `com.fasterxml.jackson.core` / `com.fasterxml.jackson.annotation`. Vì vậy, không thể thay mọi chuỗi `com.fasterxml.jackson` bằng `tools.jackson` một cách máy móc.

Ví dụ dependency Gradle minh họa việc chọn một dòng phiên bản. Thay `<2.x-version>` hoặc `<3.x-version>` bằng version/BOM mà dự án đã quyết định sử dụng:

```groovy
// Jackson 2.x
dependencies {
    implementation platform("com.fasterxml.jackson:jackson-bom:<2.x-version>")
    implementation "com.fasterxml.jackson.core:jackson-core"
    implementation "com.fasterxml.jackson.core:jackson-databind"
}
```

```groovy
// Jackson 3.x
dependencies {
    implementation platform("tools.jackson:jackson-bom:<3.x-version>")
    implementation "tools.jackson.core:jackson-core"
    implementation "tools.jackson.core:jackson-databind"
}
```

BOM giúp các module trong cùng hệ Jackson dùng những phiên bản tương thích. Không nên tự gán các version khác nhau cho `jackson-core`, `jackson-databind` và module mở rộng nếu không có lý do rõ ràng. Nếu Spring Boot hoặc một platform khác đã quản lý BOM, hãy kiểm tra cơ chế quản lý đó trước khi thêm một BOM xung đột.

### 1.2. Kiểm tra dependency đã được phân giải

Khai báo trong `build.gradle` chưa chắc phản ánh đầy đủ phiên bản runtime. Một thư viện khác có thể kéo Jackson vào theo dependency bắc cầu; Gradle cũng có thể chọn version khác sau khi giải quyết xung đột.

Với Gradle, có thể kiểm tra:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để xem lý do một dependency được chọn, dùng `dependencyInsight` với đúng configuration và module cần kiểm tra:

```bash
./gradlew dependencyInsight \
  --dependency jackson-core \
  --configuration runtimeClasspath
```

Với Maven:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson,tools.jackson
```

Khi đọc kết quả, chú ý cả groupId lẫn version. Chỉ nhìn tên artifact `jackson-core` là chưa đủ vì Jackson 2 và Jackson 3 đều có artifact cùng tên nhưng tọa độ và package khác nhau.

## 2. Phân biệt khác biệt giữa các major version

### 2.1. Jackson 1.x, 2.x và 3.x có namespace khác nhau

Đây là dấu hiệu đầu tiên khi một đoạn code không tìm thấy class:

```java
// Jackson 1.x
import org.codehaus.jackson.map.ObjectMapper;

// Jackson 2.x
import com.fasterxml.jackson.databind.ObjectMapper;

// Jackson 3.x
import tools.jackson.databind.ObjectMapper;
```

Nếu ví dụ dùng `org.codehaus.jackson`, nó thuộc dòng 1.x. Không nên sửa từng import một cách tùy tiện; hãy tìm tài liệu hoặc ví dụ tương ứng với major version dự án đang dùng.

Với Jackson 2 sang 3, nhiều package được chuyển từ `com.fasterxml.jackson` sang `tools.jackson`. Tuy nhiên, `jackson-annotations` vẫn là ngoại lệ và một số annotation thuộc Databind cũng cần được xử lý riêng. Hãy kiểm tra package của từng annotation thay vì chạy thay thế hàng loạt trên toàn bộ source.

### 2.2. Jackson 3 yêu cầu Java 17 trở lên

Jackson 3 đặt baseline Java 17. Nếu dự án đang build hoặc chạy trên Java 8, 11 hay một runtime thấp hơn 17, việc đổi dependency sang Jackson 3 sẽ không phải là một thay đổi độc lập. Cần đánh giá khả năng nâng JDK và các thư viện liên quan trước.

Một ví dụ trên blog có thể dùng `var`, record, text block hoặc API JDK mới. Những cú pháp/API đó có thể yêu cầu Java cao hơn baseline của Jackson. Hãy phân biệt yêu cầu của chính Jackson với yêu cầu riêng của đoạn code minh họa.

### 2.3. Jackson 3 không phải bản nâng cấp tương thích nhị phân của Jackson 2

Jackson 2.x vẫn có thể được duy trì song song với Jackson 3.x trên cùng classpath vì chúng dùng groupId và package khác nhau. Điều đó hữu ích cho quá trình chuyển đổi từng phần, nhưng không có nghĩa object của hai dòng có thể thay thế trực tiếp cho nhau.

Ví dụ, một thư viện nhận `com.fasterxml.jackson.core.JsonParser` không tự động nhận được `tools.jackson.core.JsonParser`. Dù cả hai cùng đại diện cho parser JSON, chúng là hai kiểu Java khác nhau. Khi API của thư viện công khai nhận/trả kiểu Jackson, cần kiểm tra thư viện đó đã hỗ trợ major version nào.

## 3. Nhận diện các thay đổi API thường gặp từ Jackson 2 sang 3

Jackson 3 loại bỏ các API deprecated của dòng 2.x, đổi tên một số lớp/phương thức và thay đổi cách cấu hình. Bảng sau là các ví dụ có khả năng gặp khi sao chép code cũ.

| Khu vực | Jackson 2.x | Jackson 3.x |
|---|---|---|
| Package Core | `com.fasterxml.jackson.core...` | `tools.jackson.core...` |
| Package Databind | `com.fasterxml.jackson.databind...` | `tools.jackson.databind...` |
| JSON factory | `com.fasterxml.jackson.core.JsonFactory` | `tools.jackson.core.json.JsonFactory` |
| Token tên field | `JsonToken.FIELD_NAME` | `JsonToken.PROPERTY_NAME` |
| Đọc nội dung token | `parser.getText()` | `parser.getString()` |
| Tên field hiện tại | `parser.getCurrentName()` | `parser.currentName()` |
| Vị trí parser | `getCurrentLocation()` / `getTokenLocation()` | `currentLocation()` / `currentTokenLocation()` |
| Tên field khi ghi | `generator.writeFieldName(name)` | `generator.writeName(name)` |
| Ghi POJO từ generator | `generator.writeObject(value)` | `generator.writePOJO(value)` |
| Exception gốc | `JsonProcessingException` | `JacksonException` |
| Exception đọc | `JsonParseException` | `StreamReadException` |
| Exception ghi | `JsonGenerationException` | `StreamWriteException` |

Các tên mới phản ánh cách Jackson 3 chuẩn hóa thuật ngữ theo property và tách rõ API streaming tổng quát khỏi phần triển khai JSON. Khi gặp một tên không khớp, tra migration guide và Javadoc của đúng version thay vì tự đoán tên thay thế.

### 3.1. Ví dụ parser ở Jackson 2.x

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

import java.io.IOException;

public class Jackson2ReadExample {
    public void read(String json) throws IOException {
        JsonFactory factory = new JsonFactory();

        try (JsonParser parser = factory.createParser(json)) {
            JsonToken token;
            while ((token = parser.nextToken()) != null) {
                if (token == JsonToken.FIELD_NAME) {
                    System.out.println("Name: " + parser.getCurrentName());
                } else if (token == JsonToken.VALUE_STRING) {
                    System.out.println("Value: " + parser.getText());
                }
            }
        }
    }
}
```

### 3.2. Cùng thao tác ở Jackson 3.x

```java
import tools.jackson.core.JsonParser;
import tools.jackson.core.JsonToken;
import tools.jackson.core.json.JsonFactory;

import java.io.IOException;

public class Jackson3ReadExample {
    public void read(String json) throws IOException {
        JsonFactory factory = JsonFactory.builder().build();

        try (JsonParser parser = factory.createParser(json)) {
            JsonToken token;
            while ((token = parser.nextToken()) != null) {
                if (token == JsonToken.PROPERTY_NAME) {
                    System.out.println("Name: " + parser.currentName());
                } else if (token == JsonToken.VALUE_STRING) {
                    System.out.println("Value: " + parser.getString());
                }
            }
        }
    }
}
```

Hai ví dụ có cùng mục đích nhưng dùng đúng package, token và accessor của từng dòng. `try-with-resources` vẫn có ích để đóng parser và tài nguyên liên quan. Việc khai báo `throws IOException` trong ví dụ cũng có thể cần thiết cho thao tác đóng stream; không nên suy luận rằng mọi lỗi I/O của JDK đều biến mất chỉ vì exception do Jackson phát sinh đã đổi sang unchecked.

### 3.3. Ví dụ ghi property

Trong Jackson 2.x, tên thuộc tính thường được ghi bằng `writeFieldName()`:

```java
// Jackson 2.x
generator.writeStartObject();
generator.writeFieldName("name");
generator.writeString("An");
generator.writeEndObject();
```

Ở Jackson 3.x, API dùng `writeName()`:

```java
// Jackson 3.x
generator.writeStartObject();
generator.writeName("name");
generator.writeString("An");
generator.writeEndObject();
```

Không chỉ tên method, kiểu import của `JsonGenerator` cũng phải khớp với dòng Jackson mà dependency cung cấp.

## 4. Khác biệt về cách cấu hình và vòng đời object

### 4.1. Factory và mapper ở Jackson 2.x

Trong Jackson 2.x, có thể cấu hình `JsonFactory` hoặc `ObjectMapper` trực tiếp bằng các phương thức cấu hình. Builder đã xuất hiện ở một số API từ các phiên bản 2.x, nhưng các object vẫn giữ khả năng cấu hình trực tiếp vì yêu cầu tương thích ngược.

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.ObjectMapper;

JsonFactory factory = new JsonFactory();
factory.enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);

ObjectMapper mapper = new ObjectMapper(factory);
mapper.findAndRegisterModules();
```

Đây là kiểu ví dụ có thể xuất hiện trong tài liệu 2.x. Trước khi dùng, vẫn phải kiểm tra version cụ thể vì một số method đã deprecated ở các minor release cuối của dòng 2.x.

### 4.2. Factory và mapper ở Jackson 3.x

Trong Jackson 3, `JsonFactory` và `ObjectMapper` được thiết kế immutable. Cấu hình phải hoàn tất qua builder trước khi tạo instance:

```java
import tools.jackson.core.StreamReadFeature;
import tools.jackson.core.json.JsonFactory;
import tools.jackson.databind.json.JsonMapper;

JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();

JsonMapper mapper = JsonMapper.builder(factory)
        .build();
```

Sau khi build, không cấu hình lại instance bằng các setter/enable/disable theo kiểu cũ. Nếu cần cấu hình khác, tạo instance mới từ builder hoặc dùng `rebuild()` để lấy builder dựa trên cấu hình hiện tại.

Jackson 3 vẫn cho phép `new ObjectMapper()` trong một số trường hợp, nhưng `JsonMapper.builder().build()` là cách khởi tạo JSON mapper được khuyến nghị. Khi làm việc với format cụ thể như YAML hoặc XML, dùng mapper subtype tương ứng thay vì truyền factory của format khác vào constructor `ObjectMapper` chung.

### 4.3. Feature enum cũng thay đổi

Trong Jackson 2.x, code cũ có thể bật feature trực tiếp từ `JsonParser.Feature` hoặc `JsonGenerator.Feature`. Jackson 3 tách feature dùng chung cho stream và feature riêng của JSON:

| Jackson 2.x | Jackson 3.x |
|---|---|
| `JsonParser.Feature` | `StreamReadFeature` và `JsonReadFeature` |
| `JsonGenerator.Feature` | `StreamWriteFeature` và `JsonWriteFeature` |

Khi chuyển một cấu hình, cần xác định feature đó thuộc hành vi stream chung hay cú pháp JSON riêng. Không phải mọi constant cũ đều có tên hoặc vị trí tương ứng một-một. Đối chiếu Javadoc/migration guide cho đúng constant trước khi sửa.

## 5. Exception và cách xử lý lỗi có thể làm ví dụ cũ không còn phù hợp

Jackson 2.x dùng `JsonProcessingException` làm exception gốc cho các lỗi xử lý JSON. Kiểu này thuộc hệ checked exception vì kế thừa `IOException`; nhiều ví dụ khai báo `throws JsonProcessingException` hoặc bắt exception này.

Trong Jackson 3, exception gốc được đổi thành `JacksonException` và các exception do Jackson phát sinh là unchecked (`RuntimeException`). Một số kiểu thường gặp được đổi tên:

| Jackson 2.x | Jackson 3.x |
|---|---|
| `JsonProcessingException` | `JacksonException` |
| `JsonMappingException` | `DatabindException` |
| `JsonParseException` | `StreamReadException` |
| `JsonGenerationException` | `StreamWriteException` |

Điều này ảnh hưởng đến chữ ký method và các khối `catch`:

```java
// Jackson 2.x: JsonProcessingException là checked exception
try {
    mapper.readValue(json, MyDto.class);
} catch (JsonProcessingException ex) {
    // xử lý lỗi JSON
}
```

```java
// Jackson 3.x: JacksonException là unchecked exception
try {
    mapper.readValue(json, MyDto.class);
} catch (JacksonException ex) {
    // vẫn có thể bắt lỗi cụ thể hoặc lỗi gốc của Jackson
}
```

Jackson 3 không bắt buộc khai báo `throws JacksonException`. Tuy nhiên, không nên xóa mọi `throws IOException` hoặc `catch (IOException)` một cách tự động: các API I/O của JDK và thao tác đóng stream vẫn có thể phát sinh lỗi I/O riêng. Hãy phân biệt exception của Jackson với exception của nguồn/đích dữ liệu.

## 6. Cùng compile được chưa chắc cho cùng kết quả

Khác biệt giữa các dòng phiên bản không chỉ là tên class hay method. Jackson 3 thay đổi một số default configuration. Code có thể biên dịch thành công nhưng kết quả serialization/deserialization thay đổi.

Một số thay đổi đáng kiểm tra khi chuyển từ 2.x sang 3.x:

| Thiết lập | Jackson 2.x | Jackson 3.x | Ảnh hưởng có thể thấy |
|---|---|---|---|
| `FAIL_ON_UNKNOWN_PROPERTIES` | Bật mặc định | Tắt mặc định | JSON có field lạ có thể được chấp nhận thay vì báo lỗi |
| `FAIL_ON_TRAILING_TOKENS` | Tắt mặc định | Bật mặc định | Nội dung thừa sau giá trị JSON có thể bị từ chối |
| `FAIL_ON_NULL_FOR_PRIMITIVES` | Tắt mặc định | Bật mặc định | Giá trị `null` cho thuộc tính primitive như `int` có thể làm deserialize thất bại |
| `WRITE_DATES_AS_TIMESTAMPS` | Bật mặc định | Tắt mặc định | Date/time có thể được ghi thành chuỗi thay vì timestamp |
| `SORT_PROPERTIES_ALPHABETICALLY` | Tắt mặc định | Bật mặc định | Thứ tự property khi serialize POJO có thể thay đổi |

Các thiết lập trên chủ yếu thuộc Jackson Databind. Chúng cho thấy cần kiểm tra cả hành vi runtime, không chỉ compile. Đặc biệt, không nên dựa vào thứ tự property trong JSON nếu thứ tự đó không được quy định bằng cấu hình hoặc annotation rõ ràng.

Khi ứng dụng phụ thuộc vào hành vi cũ, hãy cấu hình lại có chủ đích và viết kiểm thử cho hợp đồng JSON thực tế. Không nên bật lại toàn bộ default cũ mà chưa biết mỗi thay đổi có ảnh hưởng đến dữ liệu nào.

## 7. Cẩn thận với package annotation khi chuyển sang Jackson 3

Đây là một ngoại lệ dễ gây lỗi khó phát hiện.

- `@JsonProperty`, `@JsonFormat` và các annotation thuộc `jackson-annotations` tiếp tục dùng package `com.fasterxml.jackson.annotation`.
- Một số annotation thuộc Databind như `@JsonSerialize`, `@JsonDeserialize`, `@JsonNaming` và `@JsonPOJOBuilder` vẫn có import dưới `com.fasterxml.jackson.databind.annotation` theo hướng dẫn migration.

Nếu classpath vẫn chứa `jackson-databind` 2.x theo dependency bắc cầu, một số import annotation cũ có thể khiến source biên dịch nhưng Jackson 3 không nhận diện annotation như mong đợi. Vì vậy, sau migration cần kiểm tra dependency tree và từng annotation thực sự được xử lý bởi module nào.

Không áp dụng thay thế chuỗi toàn cục `com.fasterxml.jackson` thành `tools.jackson` rồi kết luận đã hoàn tất migration. Cách an toàn là chuyển dependency, kiểm tra package theo loại annotation, rồi chạy test serialization/deserialization cho các DTO quan trọng.

## 8. Quy trình kiểm tra một ví dụ tìm được trên Internet

Khi gặp đoạn code trong blog, Stack Overflow, video hoặc tài liệu cũ, hãy làm theo trình tự sau:

1. **Tìm version của ví dụ.** Kiểm tra Maven coordinates, import, README, `pom.xml`, `build.gradle` hoặc phần khai báo môi trường trong bài viết. Nếu không có version, xem đó là thông tin chưa xác định.
2. **Đối chiếu version dự án.** Kiểm tra dependency trực tiếp, BOM và dependency bắc cầu bằng `dependencies` hoặc `dependencyInsight`.
3. **So sánh package/import.** Nhận diện namespace 1.x, 2.x hoặc 3.x. Với Jackson 3, chú ý vị trí mới của `JsonFactory` và các ngoại lệ annotation.
4. **Kiểm tra tên API.** Đối chiếu token, method, feature enum và exception với Javadoc của đúng version.
5. **Kiểm tra cách cấu hình.** Xác định object còn mutable hay phải tạo bằng builder. Kiểm tra cấu hình có bị gọi sau khi instance đã được chia sẻ hay không.
6. **Kiểm tra yêu cầu JDK và module.** Đảm bảo runtime hỗ trợ baseline của thư viện và các module mở rộng có cùng major line.
7. **Kiểm tra thay đổi hành vi.** So sánh default có ảnh hưởng đến JSON đầu vào/đầu ra, nhất là unknown properties, trailing tokens, null cho primitive, date/time và thứ tự property.
8. **Chạy ví dụ tối thiểu trong dự án thật.** Compile với dependency đã phân giải, chạy một input đại diện và kiểm tra output/exception. Sau đó mới đưa cách làm vào luồng nghiệp vụ.

Nếu bài viết không ghi version và không thể xác định từ code, hãy tìm ví dụ thay thế có version rõ ràng. Không nên sửa theo phỏng đoán nhiều API cùng lúc vì sẽ khó xác định thay đổi nào thực sự cần thiết.

## 9. Đọc lỗi để khoanh vùng sai khác phiên bản

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| `package com.fasterxml.jackson... does not exist` | Dependency 2.x không có trên compile classpath, hoặc ví dụ dùng namespace khác với dependency hiện tại |
| `package tools.jackson... does not exist` | Ví dụ 3.x đang được dùng với dependency 2.x, hoặc dependency 3.x chưa được thêm đúng |
| `cannot find symbol: FIELD_NAME` | Ví dụ dùng token của Jackson 2.x trong code Jackson 3.x; kiểm tra `PROPERTY_NAME` |
| `cannot find symbol: getText()` | Ví dụ cũ đang dùng accessor đã được thay bằng `getString()` trong Jackson 3 |
| `cannot find symbol: writeFieldName()` | Kiểm tra API ghi tên property `writeName()` của Jackson 3 |
| Lỗi liên quan builder/setter | Có thể đang dùng cách cấu hình mutable của 2.x với object immutable của 3.x |
| Không bắt được exception theo cách cũ | Kiểm tra exception class mới và thay đổi checked/unchecked |
| Code biên dịch nhưng JSON khác | Kiểm tra default configuration và module/annotation thực tế được nạp |

Thông báo compiler chỉ là điểm bắt đầu. Với lỗi runtime, hãy kiểm tra stack trace, version thực tế của từng module và dữ liệu đầu vào/đầu ra để xác định nguyên nhân.

## 10. Tài liệu cần đối chiếu

Ưu tiên tài liệu của chính dự án Jackson và Javadoc khớp với dependency đã phân giải:

- [Jackson Project — các dòng phiên bản và release](https://github.com/FasterXML/jackson): phân biệt nhánh 2.x và 3.x, trạng thái phát hành và các repository thành phần.
- [Jackson 2.x to 3.x Migration Guide](https://github.com/FasterXML/jackson/blob/main/jackson3/MIGRATING_TO_JACKSON_3.md): package/groupId, API bị loại bỏ, đổi tên, builder, exception và thay đổi default.
- [Jackson Release 3.0](https://github.com/FasterXML/jackson/wiki/Jackson-Release-3.0): tổng quan thay đổi lớn và các hạng mục tương thích.
- [Javadoc Jackson Core 2.22](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/2.22.0/index.html) và [Javadoc Jackson Core 3.2](https://javadoc.io/doc/tools.jackson.core/jackson-core/3.2.0/index.html): kiểm tra chính xác package, method và enum của từng dòng.

Javadoc của nhánh mới nhất không tự động mô tả API của dependency cũ. Nếu dự án đang dùng 2.15, hãy mở Javadoc 2.15; nếu đang dùng 3.0, hãy mở Javadoc 3.0. Chọn đúng version trong tài liệu là một phần của việc đọc ví dụ có trách nhiệm.

## 11. Ghi nhớ

Khi sử dụng một ví dụ Jackson từ dòng phiên bản khác, hãy xác định version trước rồi mới điều chỉnh code. Kiểm tra đồng thời dependency, package, API, cách cấu hình, exception và default behavior. Jackson 2 và 3 có thể cùng tồn tại trên classpath, nhưng kiểu Java, API và hợp đồng hành vi của chúng không thể được xem là thay thế trực tiếp. Một ví dụ chỉ thực sự phù hợp khi nó được đối chiếu với dependency đã phân giải và chạy được trong môi trường của dự án.

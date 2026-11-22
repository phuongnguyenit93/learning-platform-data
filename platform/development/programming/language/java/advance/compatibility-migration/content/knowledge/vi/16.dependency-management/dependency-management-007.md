# Shading, relocation và ảnh hưởng tới reflection hoặc service metadata

Trong các hệ thống Java lớn, một ứng dụng có thể dùng nhiều thư viện yêu cầu các phiên bản khác nhau của cùng một dependency. Xung đột phiên bản xảy ra khi classpath chỉ cung cấp một bản class nhưng có nhiều thành phần mong đợi chữ ký hoặc hành vi khác nhau. Khi không thể thống nhất phiên bản thư viện, nhóm phát triển đôi khi sử dụng **shading** và **relocation** để đóng gói dependency vào artifact và đổi namespace của các lớp.

Giải pháp này hữu ích, nhưng cũng mang rủi ro khi nâng JDK, nâng framework hoặc thay đổi mô hình class loading. **Reflection, ServiceLoader, file META-INF/services, manifest và các metadata theo tên class** có thể không được cập nhật đồng bộ với bytecode. Ứng dụng có thể biên dịch thành công và vượt qua unit test cơ bản nhưng vẫn thất bại khi một plugin, driver hay provider đặc biệt được kích hoạt ở production.

Bài học thuộc chương **Quản lý dependency** trong module **Java Advance Compatibility Migration**. Trọng tâm là hiểu sự khác nhau giữa shading và relocation, xác định những ranh giới mà phép đổi tên không tự xử lý, sử dụng công cụ đóng gói đúng phạm vi và kiểm chứng artifact sau biến đổi.

## 1. Kết quả học tập

Sau bài học này, người học có thể:

- Phân biệt fat JAR, shading, relocation, dependency exclusion, version alignment và class-loader isolation.
- Giải thích relocation thay đổi tên class/package trong bytecode như thế nào.
- Nhận diện rủi ro từ `Class.forName`, custom class loader, annotation và cấu hình chứa tên lớp.
- Giải thích cơ chế SPI/`ServiceLoader` và tại sao `META-INF/services` phải được gộp và biến đổi phù hợp.
- Kiểm tra các resource đặc biệt: manifest, Spring metadata, logging plugin cache, resource bundle, JNI và multi-release JAR.
- Hiểu ví dụ cấu hình Maven Shade Plugin và Gradle Shadow cùng giới hạn của resource transformer.
- Đánh giá ảnh hưởng đến public API, binary compatibility, JPMS, Java serialization và SBOM.
- Thiết lập một quy trình migration có báo cáo, kiểm thử runtime và khả năng rollback.

## 2. Vì sao xuất hiện nhu cầu shading?

### 2.1. Xung đột dependency trên classpath

Giả sử ứng dụng có các dependency:

```text
payment-service
├── gateway-sdk
│   └── com.vendor:json-core:1.x
└── report-sdk
    └── com.vendor:json-core:2.x
```

Hai phiên bản đều cung cấp `com.vendor.json.Parser`. Một class loader thông thường không tạo hai bản class độc lập chỉ dựa trên Maven coordinates. Khi build tool chọn một version, một thành phần có thể thấy method mà nó kỳ vọng không tồn tại ở runtime.

Triệu chứng có thể bao gồm:

- `NoSuchMethodError` nếu chữ ký method cần gọi không có trong class thực tế.
- `NoClassDefFoundError` khi class chỉ có ở một bản dependency.
- `IllegalAccessError` hoặc lỗi khác do API/runtime thay đổi.
- Hành vi sai âm thầm nếu method còn tên nhưng semantics khác.
- Lỗi class loading khi plugin hoặc application server đưa JAR vào một thứ tự khác.

Điều quan trọng là xác định **class thực tế được nạp từ JAR nào**; cây dependency ở build time không phải lúc nào cũng phản ánh toàn bộ runtime, nhất là khi có container, agent hoặc thư viện được cài thủ công.

### 2.2. Không nên chọn shading ngay lập tức

Trước khi dùng shading, hãy cân nhắc:

1. **Version alignment:** nâng các SDK lên những phiên bản sử dụng chung dependency được hỗ trợ.
2. **Dependency management/constraints:** chọn phiên bản chung sau khi đã xác nhận compatibility.
3. **Exclusion:** loại dependency dư thừa hoặc trùng không cần thiết.
4. **Thay API hoặc cập nhật framework:** bỏ phiên bản thư viện cũ thực sự không còn hỗ trợ JDK mục tiêu.
5. **Class-loader isolation:** nếu có mô hình plugin/application server cho phép nạp bản riêng mà vẫn giữ shared API ổn định.
6. **Shading + relocation:** khi các cách trên không khả thi và có lý do rõ ràng để duy trì hai namespace khác nhau.

Shading không sửa lỗi của dependency gốc. Nếu phiên bản cũ có lỗ hổng hoặc không hỗ trợ JDK mới, đổi package không làm code trở nên an toàn hoặc tương thích.

## 3. Phân biệt fat JAR, shading và relocation

### 3.1. Fat JAR hoặc uber JAR

Fat JAR là một JAR chứa mã ứng dụng và nội dung của nhiều dependency:

```text
application-all.jar
├── com/example/app/Main.class
├── com/vendor/json/Parser.class
├── com/vendor/codec/Encoder.class
└── META-INF/...
```

Kỹ thuật này giúp phân phối dễ dàng. Nhưng nếu hai dependency cùng có entry `com/vendor/json/Parser.class`, công cụ phải giải quyết trùng entry. Chỉ gộp JAR **không** đảm bảo hai phiên bản class có thể cùng tồn tại.

### 3.2. Shading

Trong Java build ecosystem, *shading* thường là quá trình đưa các thư viện phụ thuộc vào artifact được đóng gói, có thể kèm theo các bước lọc class, gộp resource và đổi tên package.

**Shading không tự động đồng nghĩa với relocation.** Có thể tạo shaded/fat artifact mà mọi package vẫn mang tên gốc. Muốn cô lập namespace thường cần khai báo relocation cụ thể.

### 3.3. Relocation

Relocation đổi tên package/class và các tham chiếu bytecode mà plugin nhận diện được.

Ví dụ:

```text
Trước:
  com.vendor.json.Parser
  com.vendor.json.Node

Sau:
  com.example.payment.internal.shaded.json.Parser
  com.example.payment.internal.shaded.json.Node
```

Như vậy:

```text
gateway-sdk  --> com.example.payment.internal.shaded.json.Parser (1.x)
report-sdk   --> com.vendor.json.Parser                         (2.x)
```

Hai bản Parser lúc này là **hai kiểu Java khác nhau**. Từ đây phát sinh giới hạn quan trọng: một object thuộc kiểu đã relocate không thể được dùng như object kiểu chưa relocate chỉ vì hai implementation xuất phát từ một source library.

### 3.4. So sánh các lựa chọn

| Kỹ thuật | Lợi ích | Giới hạn |
| --- | --- | --- |
| Alignment | Giảm số version cần duy trì. | Các consumer có thể không tương thích cùng một version. |
| Exclusion | Loại dependency dư hoặc sai. | Có thể làm thư viện thiếu class cần thiết. |
| Fat JAR | Triển khai một artifact thuận tiện. | Không tự xử lý class trùng tên. |
| Shading | Đóng gói và biến đổi artifact. | Có thể làm mất/đổi sai resource. |
| Relocation | Tạo namespace riêng. | Không tự biến đổi mọi tên class trong dữ liệu. |
| Class-loader isolation | Cô lập phiên bản theo loader. | Shared API và object crossing boundary vẫn phức tạp. |

## 4. Relocation sửa bytecode nhưng không phải mọi dữ liệu

### 4.1. Các tham chiếu bytecode được nhận diện

Một công cụ relocation thích hợp thường xử lý những phần như:

- Tên class trong class file và đường dẫn entry `.class`.
- Tham chiếu tới class cha, interface, field và method.
- JVM descriptor chứa tên class.
- Một số generic signature và annotation chứa type reference.
- Những metadata có cấu trúc mà plugin cụ thể hỗ trợ.

Ví dụ source:

```java
import com.vendor.json.Parser;

Parser parser = new Parser();
```

Compiler đưa tham chiếu class vào bytecode theo cấu trúc mà công cụ có thể phân tích. Sau relocation, lời gọi có thể tham chiếu đến `com.example.payment.internal.shaded.json.Parser`.

Mức độ biến đổi cụ thể phụ thuộc phiên bản plugin và định dạng class file. Khi nâng JDK, plugin xử lý bytecode cũng phải hỗ trợ class file version của JDK mục tiêu.

### 4.2. Chuỗi tên class không phải type reference

Xét:

```java
String providerName = configuration.getProperty("parser.provider");
Class<?> providerType = Class.forName(providerName);
Object provider = providerType.getDeclaredConstructor().newInstance();
```

Giá trị `parser.provider` có thể nằm trong file cấu hình production, biến môi trường hoặc database. Plugin build không biết nó là gì trong từng môi trường.

Ngay cả khi tên class là string literal:

```java
Class.forName("com.vendor.json.FastParser");
```

cũng không nên giả định mọi plugin/phiên bản sẽ tự động đổi string constant. Một số công cụ có cơ chế viết lại một số chuỗi; cấu hình khác có thể giữ nguyên chúng nhằm tránh phá dữ liệu không phải FQCN. **Phải kiểm tra artifact và kịch bản thực thi thực tế.**

### 4.3. Những vị trí khác chứa tên class/package

```text
Bytecode:
  Lcom/vendor/json/Parser;

Configuration:
  parser.provider=com.vendor.json.FastParser

SPI resource path:
  META-INF/services/com.vendor.spi.ParserProvider

SPI resource body:
  com.vendor.impl.DefaultParserProvider

Resource:
  com/vendor/json/defaults.properties

Serialized payload:
  {"@class":"com.vendor.json.Parser"}

JNI binding:
  tên hàm native dựa vào package/class Java
```

Không thể giả định một rule đổi package sẽ tự xử lý mọi vị trí trên. Cần chọn một cơ chế migration cho từng loại metadata.

## 5. Reflection và nạp lớp động sau relocation

### 5.1. Vì sao `Class.forName` gây lỗi?

Giả sử JAR trước relocation có:

```text
com.vendor.json.FastSerializer
```

Một file properties chứa:

```properties
serializer.class=com.vendor.json.FastSerializer
```

Sau relocation, trong JAR chỉ còn:

```text
com.example.payment.internal.shaded.json.FastSerializer
```

Nếu cấu hình chưa đổi, lệnh:

```java
Class<?> type = Class.forName(
        settings.getProperty("serializer.class"));
```

có thể ném `ClassNotFoundException`. Không có lời gọi Java thông thường nào để plugin tự cập nhật tên class nằm trong file cấu hình ngoài build.

### 5.2. Reflection thông qua framework

Một ứng dụng không trực tiếp dùng `Class.forName` vẫn có thể phụ thuộc reflection qua:

- Dependency injection container.
- ORM và entity scanning.
- Serializer/deserializer.
- Proxy/AOP framework.
- Web framework và annotation scanning.
- Test framework, mocking tool hoặc bytecode generator.
- Plugin manager.

Nếu package được scan là `com.vendor.json`, class sau relocation có thể biến mất khỏi phạm vi scan. Nếu annotation chứa chuỗi FQCN, plugin có thể không sửa. Nếu framework dùng cache metadata được sinh sẵn, cache có thể vẫn trỏ đến tên cũ.

Vì vậy, không thể kết luận an toàn chỉ bằng việc tìm kiếm `Class.forName` trong source ứng dụng.

### 5.3. Custom ClassLoader

Ví dụ một plugin manager:

```java
Class<?> pluginType = pluginLoader.loadClass(
        configuredImplementation);
```

Cần kiểm tra cả:

1. Tên class trong config còn là tên cũ không?
2. Class relocated có tồn tại trong JAR đúng không?
3. JAR nằm ở classpath/module path mà loader thực sự đọc không?
4. Loader có lọc package hoặc child-first/parent-first policy không?
5. Có một bản API chung ở host mà plugin phải implement không?

Một class xuất hiện trong JAR nhưng không được loader mong đợi nhìn thấy vẫn có thể gây `ClassNotFoundException`.

### 5.4. Reflection sâu và JPMS

Relocation không phải cách tự động bỏ qua hạn chế truy cập của Java Platform Module System.

Một framework có thể nạp đúng class nhưng gặp:

```text
java.lang.reflect.InaccessibleObjectException
```

khi gọi `setAccessible(true)` lên field hoặc constructor trong package của named module chưa được open. Trong trường hợp này phải điều tra `opens` hoặc `--add-opens`, không dùng relocation để suy ra rằng mọi quyền truy cập được phép.

### 5.5. Dữ liệu lâu dài chứa FQCN

Tên class có thể đã nằm trong:

- JSON polymorphic type metadata.
- XML hoặc mapping file.
- Database record và configuration service.
- Cache key hoặc job descriptor.
- Java serialization stream.
- Các message do service khác tạo.
- Giao thức nội bộ của plugin.

Nếu dữ liệu lịch sử chứa tên cũ, artifact mới có thể đọc sai hoặc không đọc được. Cần thiết kế alias, adapter hoặc migration schema có kiểm soát, thay vì tìm-thay chuỗi một cách mù quáng.

## 6. Java SPI và `META-INF/services`

### 6.1. ServiceLoader tìm implementation như thế nào?

Trên classpath truyền thống, SPI thường có file:

```text
META-INF/services/com.vendor.spi.CompressionProvider
```

Nội dung chứa FQCN của implementation:

```text
com.vendor.impl.FastCompressionProvider
com.vendor.impl.SafeCompressionProvider
```

Ứng dụng gọi:

```java
ServiceLoader<CompressionProvider> providers =
        ServiceLoader.load(CompressionProvider.class);

for (CompressionProvider provider : providers) {
    provider.initialize();
}
```

Java tìm provider theo service interface và resource configuration; bản thân file `META-INF/services/*` là **metadata văn bản** trong JAR. Nó không tự đổi theo tên bytecode.

### 6.2. Phải cập nhật cả đường dẫn và nội dung khi phù hợp

Giả sử relocate:

```text
com.vendor.spi.CompressionProvider
  => com.example.shaded.spi.CompressionProvider

com.vendor.impl.FastCompressionProvider
  => com.example.shaded.impl.FastCompressionProvider
```

Khi **service interface cũng được relocate**, metadata tương ứng có thể cần thành:

```text
META-INF/services/com.example.shaded.spi.CompressionProvider

Nội dung:
com.example.shaded.impl.FastCompressionProvider
```

Nhưng nếu **service interface là shared API và không được relocate**, tên resource phải giữ:

```text
META-INF/services/com.vendor.spi.CompressionProvider

Nội dung:
com.example.shaded.impl.FastCompressionProvider
```

Đó là lý do không thể áp dụng một rule thay thế tên file metadata mà không biết kiến trúc shared API.

### 6.3. Hậu quả nếu resource chưa được xử lý

| Tình huống | Hậu quả có thể |
| --- | --- |
| Provider class đã đổi tên, nội dung descriptor còn tên cũ | `ServiceConfigurationError` hoặc provider không được nạp. |
| Service interface đổi tên, filename descriptor còn tên cũ | `ServiceLoader` không tìm đúng cấu hình service. |
| Gộp JAR làm mất một descriptor | Một số provider biến mất khỏi danh sách. |
| Provider implements một bản interface bị relocate, consumer dùng bản không relocate | Kiểu không tương thích; có thể phát sinh `ServiceConfigurationError`. |
| JAR/provider không được nạp bởi loader/module graph phù hợp | `ServiceLoader` không tìm thấy implementation. |

### 6.4. Gộp nhiều `META-INF/services`

Hai thư viện có thể cùng chứa:

```text
META-INF/services/java.sql.Driver
```

Một file đăng ký provider A, file kia đăng ký provider B. Nếu fat JAR chỉ giữ một resource khi entry trùng tên, provider của thư viện còn lại có thể bị mất.

Một **service resource transformer** phù hợp có thể hợp nhất danh sách provider. Tuy nhiên, cần kiểm tra nó cũng áp dụng mapping relocation đúng đối với provider class và service interface (nếu có). Khả năng cụ thể phụ thuộc plugin/version.

Không nên dùng nối file thuần văn bản cho mọi resource vì các định dạng khác nhau có cách xử lý duplicate key và class names khác nhau.

### 6.5. Kiểm thử SPI bằng hành vi runtime

Một test phù hợp không chỉ kiểm tra JAR chứa class. Nó cần thực sự tìm provider:

```java
import java.util.ServiceLoader;

public final class ServiceProbe {
    public static void check() {
        boolean found = false;

        for (CompressionProvider provider :
                ServiceLoader.load(CompressionProvider.class)) {
            System.out.println(provider.getClass().getName());
            found = true;
        }

        if (!found) {
            throw new IllegalStateException(
                "Không tìm thấy CompressionProvider");
        }
    }
}
```

Nếu interface cũng relocate, `CompressionProvider` trong test phải là interface **thực tế của artifact cuối**. Test nên xác nhận provider bắt buộc, không chỉ số lượng lớn hơn 0, và gọi thử một nghiệp vụ để phát hiện implementation không hoạt động.

## 7. Các resource và metadata khác

### 7.1. Manifest

`META-INF/MANIFEST.MF` có thể chứa:

```text
Main-Class: com.example.app.Main
Automatic-Module-Name: com.example.app
Premain-Class: com.example.agent.Agent
Agent-Class: com.example.agent.Agent
```

Những tên class và module liên quan cần đúng với artifact sau đóng gói. Khi gộp nhiều JAR, không thể giữ tất cả manifest gốc một cách vô điều kiện. Cần cấu hình manifest của artifact đầu ra và kiểm tra điểm khởi chạy thực tế.

### 7.2. Spring metadata

Một số resource có thể chứa tên class hoặc danh sách implementation:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring.handlers
META-INF/spring.schemas
```

Các file này không cùng một định dạng. Một số là properties với key đặc biệt, một số là danh sách class hoặc URL schema. Việc nối file đơn giản có thể làm mất hoặc ghi đè thông tin nếu key trùng; việc relocate bytecode cũng không đảm bảo tên class trong metadata được cập nhật.

Với framework cụ thể, cần chọn transformer tương thích với phiên bản framework và kiểm tra nội dung resource cuối cùng.

### 7.3. Logging plugin descriptors

Một số logging framework dùng service metadata hoặc plugin cache được tạo trong build. Ví dụ, Log4j 2 có thể chứa metadata plugin cache trong `META-INF`. Nếu shadowing bỏ file cache, gộp sai hoặc giữ tên class cũ, một appender/layout chỉ dùng trong production có thể không được phát hiện.

Không xử lý resource cache nhị phân bằng cách append văn bản. Cần transformer hoặc bước regenerate theo tài liệu của đúng phiên bản framework.

### 7.4. Resource đường dẫn tương đối và tuyệt đối

Ví dụ:

```java
Parser.class.getResourceAsStream("defaults.properties");
```

Resource này được tìm tương đối với package của `Parser`. Nếu class được relocate nhưng file properties không chuyển theo, lời gọi có thể trả về `null`.

Trường hợp khác:

```java
Parser.class.getClassLoader().getResourceAsStream(
        "com/vendor/json/defaults.properties");
```

Đây là đường dẫn resource trong chuỗi. Dù class đã relocate, string path có thể vẫn là tên cũ. Cần kiểm tra cả hai kiểu lookup.

### 7.5. ResourceBundle

`ResourceBundle` có thể tìm một base name như `com.vendor.i18n.Labels`, tương ứng các file:

```text
com/vendor/i18n/Labels.properties
com/vendor/i18n/Labels_vi.properties
```

Sau relocation, base name hoặc đường dẫn resource có thể không còn khớp. Cần bảo đảm mapping và test locale thực tế, thay vì chỉ thử ngôn ngữ mặc định.

### 7.6. Native/JNI

Một thư viện JNI có thể ánh xạ tên package/class Java sang tên native symbol hoặc quá trình registration. Relocate Java class mà không đổi native binding có thể gây `UnsatisfiedLinkError`.

Nếu dependency chứa JNI/JNA, native extraction hoặc thư viện theo kiến trúc hệ điều hành, cần kiểm thử trên platform được hỗ trợ. Không mặc định relocation an toàn chỉ vì Java class được đổi tên thành công.

## 8. Java serialization và giao thức truyền dữ liệu

### 8.1. Java Object Serialization

Dữ liệu Java Object Serialization có thể ghi tên class trong class descriptor. Nếu trước đây một stream chứa class `com.vendor.model.Record`, sau relocation chỉ còn `com.example.shaded.model.Record`, quá trình deserialize stream cũ có thể thất bại.

Giữ cùng `serialVersionUID` không tự động sửa tên class. Nếu cần đọc dữ liệu cũ, phải thiết kế compatibility/migration ở ranh giới serialization và kiểm tra an toàn của deserialization.

### 8.2. JSON/XML polymorphism

Một số serializer ghi tên lớp vào dữ liệu:

```json
{
  "@class": "com.vendor.model.Record",
  "id": 17
}
```

Nếu producer mới xuất tên shaded còn consumer cũ vẫn mong tên original (hoặc ngược lại), hai hệ thống có thể không tương thích dù JSON hợp lệ.

Nên ưu tiên schema identifier ổn định không gắn với package implementation. Nếu đã có dữ liệu cũ, dùng mapping có whitelist, versioning và migration có backup; không tự cho phép deserialize class tùy ý từ input không tin cậy.

### 8.3. Cache và database

Cache value hoặc database record có thể lưu FQCN để chọn decoder, job handler hay plugin. Các dữ liệu này thường nằm ngoài build artifact nên relocation tool không thể sửa tự động.

Khi thay đổi package, hãy kiểm kê dữ liệu đang tồn tại và phối hợp triển khai nhiều phiên bản nếu cần. Tránh release mà code mới chỉ đọc được tên mới trong khi dữ liệu lịch sử vẫn mang tên cũ.

## 9. Maven Shade Plugin: ví dụ cấu hình

### 9.1. Relocation và service transformer

Ví dụ Maven sau dùng một phiên bản plugin minh họa; dự án phải chọn và khóa **phiên bản thực tế đã được xác minh hỗ trợ JDK và build tool của mình**:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-shade-plugin</artifactId>
      <version>3.6.1</version>
      <executions>
        <execution>
          <phase>package</phase>
          <goals>
            <goal>shade</goal>
          </goals>
          <configuration>
            <relocations>
              <relocation>
                <pattern>com.vendor.json</pattern>
                <shadedPattern>
                  com.example.payment.internal.shaded.json
                </shadedPattern>
              </relocation>
            </relocations>
            <transformers>
              <transformer implementation=
                "org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
              <transformer implementation=
                "org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                <mainClass>com.example.payment.Main</mainClass>
              </transformer>
            </transformers>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```

Ý nghĩa:

- `relocations` mô tả nguồn/đích của package prefix.
- `ServicesResourceTransformer` phục vụ xử lý `META-INF/services`, trong đó có việc gộp provider; cần đọc và kiểm tra behavior thực tế theo phiên bản plugin.
- `ManifestResourceTransformer` giúp xác định entry point cho artifact.
- Không có transformer mặc định nào nên được coi là giải pháp tổng quát cho mọi Spring metadata, logging cache hoặc cấu hình nằm ngoài JAR.

Nếu thư viện chỉ cần shading một dependency cụ thể, cần kiểm soát danh sách artifact đưa vào và phạm vi relocation, tránh relocate những package public API hoặc shared SPI ngoài ý muốn.

### 9.2. `minimizeJar` và reflection

Một số cấu hình Maven Shade có chức năng giảm kích thước JAR bằng phân tích sử dụng class. Với hệ thống dùng reflection, `ServiceLoader` hoặc plugin nạp động, class chỉ được tìm qua chuỗi/cấu hình có thể trông như “không được sử dụng” ở phân tích tĩnh.

Nếu class bị loại, ứng dụng sẽ hỏng khi đường nạp động đó xảy ra. Trong migration, ưu tiên artifact đầy đủ và chức năng đúng, rồi chỉ bật tối ưu loại class sau khi có test và danh sách giữ lại rõ ràng.

### 9.3. Signed JAR

Shading làm thay đổi bytecode/resource nên chữ ký số của JAR gốc có thể không còn hợp lệ. Những entry như:

```text
META-INF/*.SF
META-INF/*.RSA
META-INF/*.DSA
```

cần được xử lý theo chiến lược đóng gói và bảo mật. Loại metadata chữ ký cũ khỏi artifact đầu ra không đồng nghĩa đã xác thực artifact mới. Nếu tổ chức yêu cầu signature/provenance, cần thực hiện quy trình ký lại và kiểm tra sau build.

## 10. Gradle Shadow: ví dụ cấu hình

Với dự án đã cài đặt plugin Shadow tương thích và có task `shadowJar`, ví dụ Gradle Groovy DSL:

```groovy
tasks.named('shadowJar') {
    relocate(
        'com.vendor.json',
        'com.example.payment.internal.shaded.json'
    )

    mergeServiceFiles()
}
```

Điểm cần chú ý:

- `relocate` đổi namespace được chỉ định.
- `mergeServiceFiles` phục vụ hợp nhất service descriptors theo khả năng plugin.
- Tài nguyên framework đặc thù có thể cần transformer bổ sung.
- Plugin và Gradle cần tương thích với phiên bản JDK chạy build.
- Khi publish thư viện, cần quyết định rõ artifact shadow và dependency metadata của consumer.

Không suy luận rằng task `shadowJar` thành công thì file cấu hình ngoài artifact hoặc class được nạp bằng chuỗi đều đã được rewrite.

## 11. Đặc điểm riêng khi dùng JPMS

### 11.1. Unnamed module và classpath

Một executable fat JAR chạy bằng:

```bash
java -jar application-all.jar
```

thường sử dụng classpath cho các lớp ứng dụng. Trong mô hình này, JPMS vẫn áp dụng với các module JDK, nhưng package visibility giữa JAR legacy không được mô tả như các explicit named modules.

Reflection, SPI và resource vẫn phải kiểm tra riêng. Không có `module-info.java` không có nghĩa không có lỗi class loading.

### 11.2. Automatic module và tên module

Nếu đặt shaded JAR không có explicit module descriptor lên module path, JAR có thể được xử lý như automatic module. Tên module đến từ `Automatic-Module-Name` hoặc được suy ra từ tên file.

Relocation package **không đồng nghĩa tự đổi tên module**. Nếu consumer dùng `requires com.vendor.lib` mà artifact mới mang module name khác, module resolution có thể thất bại.

Kiểm tra module metadata thực tế:

```bash
jar --describe-module --file path/to/shaded-library.jar
```

### 11.3. Explicit module descriptor

Gộp nội dung của nhiều modular JAR vào một artifact không có nghĩa nhiều `module-info.class` có thể cùng tồn tại như một module descriptor hợp lệ duy nhất. Các descriptor có thể có:

- `requires` và module name khác nhau.
- `exports` và `opens` khác nhau.
- `uses`/`provides` khác nhau.
- Ranh giới package và policy access riêng.

Cần quyết định rõ artifact cuối là classpath, automatic module hay explicit named module. Nếu cần module descriptor mới, phải thiết kế và kiểm tra lại module graph; không chỉ copy metadata nguyên trạng.

### 11.4. Multi-release JAR

Một dependency có thể có:

```text
META-INF/versions/9/...
META-INF/versions/17/...
```

Khi shading, công cụ phải hỗ trợ class biến thể theo JDK. Nếu chỉ biến đổi lớp ở root mà bỏ sót lớp theo version, artifact có thể hoạt động trên JDK 11 nhưng lỗi ở JDK 17.

Kiểm tra manifest `Multi-Release`, đường dẫn variant và chạy test trên các JDK thuộc phạm vi hỗ trợ.

### 11.5. Split package

Relocation đôi khi giúp tránh split package nhưng cũng có thể tạo ra split package khác nếu rule thiếu nhất quán. Kiểm tra package layout, module graph, version dependency và class loader thực tế trước khi tuyên bố mô hình modular đã hoạt động đúng.

## 12. Public API và binary compatibility

### 12.1. Khi kiểu dependency lộ ra ngoài API

Ví dụ thư viện công khai:

```java
public com.vendor.json.Document parse(String source);
```

Nếu relocation đổi return type thành `com.example.shaded.json.Document`, public method descriptor có thể thay đổi. Client binary đã được biên dịch trước đó có thể gặp `NoSuchMethodError`; source client cũng phải sửa import và kiểu dữ liệu.

Tốt hơn, dùng DTO hoặc interface do thư viện sở hữu:

```java
public ParseResult parse(String source);
```

Với adapter phù hợp, implementation detail có thể chuyển sang namespace shaded mà không làm mọi client phải phụ thuộc package nội bộ.

### 12.2. Shared API giữa host và plugin

Trong plugin architecture, host và plugin thường phải dùng **cùng một interface runtime**. Nếu relocate cả shared SPI vào plugin JAR, class của plugin không còn implement đúng kiểu mà host đang chờ.

Ví dụ:

```text
Host:   com.example.spi.PaymentPlugin
Plugin: com.example.internal.shaded.spi.PaymentPlugin
```

Đây là hai kiểu khác nhau. Cần xác định package không được relocate:

- Host/plugin SPI.
- DTO truyền qua boundary.
- API application server hoặc framework dùng chung.
- Public API đã cam kết với consumer.

Chỉ relocate phần implementation dependency cần cô lập nếu có thể.

### 12.3. POM và module metadata của artifact xuất bản

Nếu thư viện publish shaded JAR, metadata dependency (POM/Gradle Module Metadata) phải phản ánh dependency nào được embed và dependency nào vẫn phải tải riêng.

Một số cấu hình tạo dependency-reduced POM. Nếu bỏ nhầm dependency còn cần ở runtime, consumer có thể thiếu class. Nếu vừa embed vừa khai báo transitive dependency gốc, consumer có thể nhận hai bản và phát sinh xung đột mới.

Hãy kiểm thử artifact từ **một dự án consumer riêng**, thay vì chỉ chạy build của dự án sản xuất JAR.

## 13. Security, license và SBOM

### 13.1. Đổi tên package không xóa CVE

Nếu thư viện `json-core:1.x` có lỗ hổng, mã của nó vẫn tồn tại sau khi đổi tên package. Một số công cụ phân tích dependency có thể không nhận ra nguồn gốc khi JAR đã được gộp và đổi namespace.

Vì vậy cần giữ:

- Maven coordinates hoặc định danh gốc.
- Phiên bản và checksum dependency được embed.
- Rule relocation và phiên bản plugin.
- License, NOTICE và attribution.
- SBOM thể hiện các thành phần đã nhúng.
- Quy trình kiểm tra CVE cho thư viện gốc và artifact cuối.

Ưu tiên nâng dependency lên phiên bản đã sửa trước khi dùng shading như biện pháp tương thích.

### 13.2. Reproducibility và provenance

Tạo shaded artifact có thể thay đổi thứ tự entry, timestamp hoặc metadata theo plugin/build environment. Đối với release cần kiểm chứng, nên cố định input, plugin, dependency và cấu hình đóng gói.

Nếu artifact phải được ký, ký sau khi biến đổi theo chính sách; không dựa vào signature cũ của JAR đã bị rewrite.

### 13.3. Reflection và class name từ dữ liệu không tin cậy

Khi hệ thống nạp class theo tên trong cấu hình hoặc payload, cần giới hạn danh sách class/provider được phép. Không mở rộng cơ chế dynamic loading một cách tùy tiện để “hỗ trợ cả tên cũ và mới”, đặc biệt với deserialization hoặc plugin nhận dữ liệu không đáng tin cậy.

## 14. Kiểm tra artifact sau shading

### 14.1. Liệt kê entry thực tế

```bash
jar tf target/application-all.jar
```

Kiểm tra:

- Class đã đổi đường dẫn đúng chưa.
- Class tên cũ còn tồn tại ngoài dự kiến không.
- `META-INF/services` còn đủ không.
- Resource framework, bundle và manifest có còn không.
- Có entry trùng hoặc package được merge sai không.
- Các biến thể multi-release có mặt không.

### 14.2. Xem tên class và method descriptor

```bash
javap -classpath target/application-all.jar \
  -p -s com.example.payment.internal.shaded.json.Parser
```

Nếu class không tìm thấy hoặc public API đổi ngoài dự kiến, cần điều tra rule relocation và phạm vi shaded artifact.

### 14.3. Kiểm tra service descriptors thủ công

Mở từng entry `META-INF/services/<service-interface-thực-tế>` trong archive rồi đối chiếu với class trong JAR:

- Filename có trùng với interface runtime không?
- Provider name còn đúng sau relocation không?
- Provider implements đúng interface không?
- Có bị mất provider trong lúc merge không?
- Có provider của dependency không được đóng gói không?

Cần phân biệt việc *service interface* đã relocate và *chỉ provider* relocate, vì hai trường hợp có quy tắc filename khác nhau.

### 14.4. Xác định class loader tại runtime

Khi cần điều tra sâu, có thể in:

```java
static void printOrigin(Class<?> type) {
    System.out.println("Class: " + type.getName());
    System.out.println("Module: " + type.getModule());
    System.out.println("Loader: " + type.getClassLoader());

    var domain = type.getProtectionDomain();
    var source = domain == null ? null : domain.getCodeSource();
    System.out.println("CodeSource: " +
        (source == null ? "unknown" : source.getLocation()));
}
```

Với dynamic class generation, `CodeSource` có thể không có dữ liệu. Đây là thông tin chẩn đoán bổ sung, không thay thế việc kiểm tra class loader, module graph và metadata.

## 15. Quy trình migration đề xuất

### Bước 1: Chụp baseline

Ghi lại dependency graph, JDK vendor/version, build plugin version, classpath/module path, class loader, lỗi xung đột, các service/provider hiện có và luồng nghiệp vụ liên quan.

Thu thập artifact gốc để có thể so sánh sau thay đổi.

### Bước 2: Xác định chính xác mục tiêu

Shading để tạo executable JAR khác với shading để chạy đồng thời hai phiên bản. Nếu chỉ muốn triển khai thuận tiện, không nhất thiết phải relocate.

Với mục tiêu giải quyết conflict, xác định rõ dependency nào cần namespace riêng và API nào phải giữ chung.

### Bước 3: Lập bản đồ class và metadata

| Thành phần | Trước | Sau dự kiến | Kiểm tra thêm |
| --- | --- | --- | --- |
| Class implementation | `com.vendor.json.Parser` | `com.example.shaded.json.Parser` | Bytecode, reflection. |
| Service interface | `com.vendor.spi.Provider` | Giữ hoặc relocate theo contract | Tên file `META-INF/services`. |
| Provider class | `com.vendor.impl.ProviderImpl` | Tên relocated | Nội dung descriptor. |
| Resource | `com/vendor/json/defaults.properties` | Giữ/chuyển theo cách lookup | `getResource`/`ResourceBundle`. |
| Framework metadata | Spring/logging/config | Transformer đặc thù | Scan/cache và startup. |
| Public API | `com.vendor.json.Document` | Ưu tiên giữ qua adapter | Source/binary compatibility. |

Không chỉ khảo sát file trong repository nếu production có cấu hình remote, plugin directory hoặc database chứa class name.

### Bước 4: Chọn công cụ và rule có giới hạn

Khóa phiên bản Maven Shade/Gradle Shadow. Chọn:

- Namespace prefix đủ hẹp.
- Bộ resource transformer phù hợp.
- Quy tắc giữ shared API.
- Chính sách manifest, signature, license, native và multi-release JAR.
- Cách publish shaded artifact và dependency metadata.

Không bật việc loại bỏ class theo phân tích tĩnh trước khi có kiểm thử các đường nạp động.

### Bước 5: Build và kiểm tra JAR cuối

Xem `jar tf`, manifest, service descriptors và class relocated. Đừng xem một lần package thành công là bằng chứng metadata hợp lệ.

### Bước 6: Kiểm thử đường nạp động

Bao gồm:

- `Class.forName` với cấu hình thực tế.
- `ServiceLoader` và tập provider bắt buộc.
- Dependency injection, ORM, serializer và component scanning.
- Resource lookup và ResourceBundle.
- Plugin cài/nạp sau startup.
- Dữ liệu serialized lịch sử nếu có.
- JNI/native theo platform hỗ trợ.

### Bước 7: Kiểm thử consumer và JDK mục tiêu

Với thư viện public, build một client riêng và kiểm tra cả source/binary compatibility theo cam kết. Với JDK migration, test các runtime trong ma trận hỗ trợ, đặc biệt khi có JPMS hoặc multi-release JAR.

### Bước 8: Security và phát hành

Cập nhật SBOM, license/NOTICE, checksum, signature, dependency metadata và hướng dẫn rollback. Ghi lại relocation mapping để nhóm vận hành có thể giải thích class name trong stack trace khi sự cố xảy ra.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Điều tra |
| --- | --- | --- |
| `ClassNotFoundException` với tên cũ | Config/reflection chưa đổi tên. | So sánh FQCN trong config, JAR và class loader. |
| `ServiceConfigurationError` | Descriptor trỏ provider thiếu hoặc interface không tương thích. | Mở `META-INF/services` và kiểm tra implementation. |
| `ServiceLoader` trả về rỗng | File metadata bị mất hoặc module/provider chưa được nạp. | Kiểm tra resource merge, SPI và module graph. |
| `NoSuchMethodError` | Conflict dependency hoặc public descriptor đổi. | So sánh JAR runtime và `javap -s`. |
| `ClassCastException` | Hai bản class/shared API không cùng danh tính runtime. | In class loader, module và tên class. |
| `MissingResourceException` | Base name/resource path sau relocation không khớp. | Kiểm tra bundle và cách lookup. |
| `NullPointerException` khi đọc resource | `getResourceAsStream` trả về `null`. | Kiểm tra resource có nằm trong JAR và đúng path không. |
| Framework không tìm thấy component | Metadata, package scan hoặc plugin cache chưa được sửa. | Xác minh config/transformer của framework. |
| `UnsatisfiedLinkError` | JNI/native mapping bị đổi tên hoặc thư viện native thiếu. | Kiểm tra native binding và platform. |
| `java -jar` không chạy | Manifest `Main-Class` sai hoặc thiếu. | Kiểm tra manifest của artifact cuối. |
| Lỗi chỉ xuất hiện trên một JDK | Multi-release class/JPMS hoặc plugin bytecode không phù hợp. | Kiểm tra versioned entries và test matrix. |
| SCA không báo thư viện lỗi | Dependency đã embed và đổi package nên khó nhận diện. | Kiểm tra SBOM, coordinates gốc, mã đóng gói. |

Không nên chữa mọi lỗi bằng cách thêm `--add-opens`, thêm JAR hoặc bật skip verification. Phân loại trước: **đổi tên, mất metadata, thiếu class, phân giải module hay API không tương thích**.

## 17. Bài thực hành tình huống SPI sau relocation

### 17.1. Bối cảnh

Một plugin sử dụng `ServiceLoader<CompressionProvider>`. Interface `com.example.spi.CompressionProvider` là shared API của host và phải giữ nguyên. Implementation cũ `com.vendor.impl.FastProvider` được relocate thành `com.example.plugin.shaded.impl.FastProvider`.

### 17.2. Trạng thái mong muốn của artifact

```text
Class:
  com/example/plugin/shaded/impl/FastProvider.class

Service metadata:
  META-INF/services/com.example.spi.CompressionProvider

Nội dung service file:
  com.example.plugin.shaded.impl.FastProvider
```

**Không** đổi tên service file thành `META-INF/services/com.example.plugin.shaded.spi.CompressionProvider` nếu interface shared API không được relocate.

### 17.3. Test tối thiểu

Ở runtime, gọi `ServiceLoader.load(CompressionProvider.class)`, xác nhận tìm thấy `FastProvider` rồi thực thi nghiệp vụ nén/giải nén hoặc phương thức chức năng phù hợp.

Test không được chỉ kiểm tra class tồn tại bằng `Class.forName`. Class có trong JAR nhưng service descriptor sai vẫn khiến SPI thất bại.

### 17.4. Tình huống lỗi

Nếu service file vẫn ghi `com.vendor.impl.FastProvider` sau khi class đã đổi tên, `ServiceLoader` có thể báo lỗi provider class không tồn tại. Nếu service file bị loại khi đóng gói, iterator có thể không tìm ra provider. Nếu plugin relocate cả interface shared API, provider có thể không còn implement kiểu mà host đang yêu cầu.

Đây là ba lỗi khác nhau cần được phân biệt để chọn cách sửa.

## 18. Checklist trước khi phát hành

- [ ] Đã xác nhận lý do shading và đã cân nhắc version alignment/exclusion.
- [ ] Đã phân định namespace implementation cần relocate và shared API phải giữ.
- [ ] Đã khóa phiên bản plugin và quy tắc build có thể tái tạo.
- [ ] Đã xác định những tên class được dùng qua reflection và cấu hình bên ngoài.
- [ ] Đã kiểm tra filename lẫn provider name của `META-INF/services`.
- [ ] Đã gộp service descriptor mà không làm mất provider.
- [ ] Đã xử lý manifest và metadata framework đặc thù.
- [ ] Đã kiểm tra resource relative/absolute lookup và ResourceBundle.
- [ ] Đã đánh giá JNI/native library, signed JAR và multi-release JAR.
- [ ] Đã xác định ảnh hưởng đến Java serialization và dữ liệu chứa FQCN.
- [ ] Đã kiểm tra JPMS/module path nếu sản phẩm dùng named/automatic module.
- [ ] Đã kiểm tra source/binary compatibility và POM khi publish cho consumer.
- [ ] Đã đọc cấu trúc artifact cuối thay vì chỉ tin build log.
- [ ] Đã chạy integration test cho ServiceLoader, reflection, scanning và plugin.
- [ ] Đã ghi dependency gốc đã embed trong SBOM, license/NOTICE và báo cáo bảo mật.
- [ ] Đã có phương án rollback, mapping relocation và người chịu trách nhiệm.

## 19. Kết luận

**Shading** giúp đóng gói các dependency; **relocation** giúp tạo namespace riêng để giảm xung đột tên class. Nhưng Java còn sử dụng tên class/package trong reflection, `ServiceLoader`, `META-INF/services`, manifest, resource, config, serialization và các cơ chế plugin. Những phần này có thể không được cập nhật chỉ bằng một rule đổi tên bytecode.

Trong Java Advance Compatibility Migration, tiêu chí hoàn thành không phải “đã tạo được một JAR”, mà là **artifact mới tìm được đúng class, giữ đủ provider, đọc đúng resource và tiếp tục đáp ứng contract đối với consumer trên JDK mục tiêu**. Hãy coi relocation là phép biến đổi có phạm vi, có kiểm thử runtime và có hồ sơ dependency rõ ràng, thay vì giải pháp che giấu xung đột để lại rủi ro lâu dài.

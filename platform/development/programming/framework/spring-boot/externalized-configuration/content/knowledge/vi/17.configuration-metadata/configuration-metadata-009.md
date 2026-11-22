# Kiểm tra metadata trong JAR và phân biệt metadata với kiểm tra lúc chạy

## 1. Mục tiêu bài học

Spring Boot cung cấp cơ chế **Externalized Configuration** để giá trị cấu hình không bị gắn cứng vào mã Java. Với `@ConfigurationProperties`, những khóa như `gateway.connect-timeout` hoặc `gateway.max-attempts` được liên kết vào một đối tượng cấu hình có kiểu.

Khi dự án phát triển, một nhu cầu khác xuất hiện: người viết `application.yml` muốn được IDE **gợi ý đúng tên thuộc tính**, biết thuộc tính có kiểu gì, được dùng để làm gì, có giá trị mặc định nào và đã bị đánh dấu không nên sử dụng hay chưa.

Spring Boot giải quyết phần lớn nhu cầu hỗ trợ công cụ này bằng **configuration metadata** — thường được đóng gói trong tệp:

```text
META-INF/spring-configuration-metadata.json
```

Metadata có thể được sinh lúc biên dịch từ các lớp `@ConfigurationProperties` nhờ `spring-boot-configuration-processor`, đồng thời có thể được bổ sung bằng metadata thủ công.

Điều quan trọng nhất của bài này là **không nhầm metadata với cơ chế kiểm tra hợp lệ lúc chạy**:

- **Metadata** mô tả cấu hình để công cụ như IDE hỗ trợ gợi ý, tài liệu và cảnh báo.
- **Binder** thực sự đọc các nguồn thuộc tính, chuyển kiểu và tạo bean `@ConfigurationProperties` trong quá trình chạy ứng dụng.
- **Validation** kiểm tra những yêu cầu bắt buộc, giới hạn số, định dạng hoặc bất biến nghiệp vụ.
- Sự tồn tại của một khóa trong JSON metadata **không tự tạo khóa đó trong Spring Environment**, không bảo đảm có giá trị thực tế và không làm ứng dụng tự từ chối mọi khóa gõ sai.

Sau bài này, bạn có thể đọc metadata trong JAR, xác định metadata được sinh từ module nào, lý giải sự khác nhau giữa gợi ý của IDE và lỗi lúc khởi động, đồng thời xây dựng một ví dụ kiểm thử cả hai khía cạnh.

## 2. Một ví dụ thực tế

Giả sử ứng dụng có cấu hình:

```yaml
# src/main/resources/application.yml
gateway:
  base-url: "https://gateway.example.invalid"
  connect-timeout: 5s
  max-attempts: 3
  enabled: true
```

Lớp Java tương ứng:

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxAttempts,
        boolean enabled) {
}
```

Có hai câu hỏi hoàn toàn khác nhau:

1. Khi người dùng gõ `gateway.connect-` trong IDE, làm sao IDE biết có khóa `gateway.connect-timeout`?
2. Khi người dùng viết `gateway.connect-timeout=wrong` rồi chạy ứng dụng, ai sẽ phát hiện `wrong` không thể trở thành `Duration`?

**Câu 1 liên quan tới configuration metadata và năng lực IDE. Câu 2 liên quan tới configuration binding/conversion khi chạy.**

Nếu thêm ràng buộc `@Min(1)` cho `maxAttempts`, giá trị `-3` có thể được chuyển thành `int` nhưng sau đó bị từ chối bởi **Bean Validation**. Đây lại là một cơ chế khác với việc có JSON metadata.

## 3. Configuration metadata là gì?

Configuration metadata là dữ liệu có cấu trúc, thường ở định dạng JSON, mô tả các nhóm và thuộc tính cấu hình của một module.

Một tệp metadata có thể chứa ba mảng quan trọng:

```json
{
  "groups": [],
  "properties": [],
  "hints": []
}
```

Ý nghĩa tổng quát:

| Thành phần | Vai trò |
| --- | --- |
| `groups` | Mô tả những nhóm thuộc tính hoặc tiền tố cấu hình |
| `properties` | Mô tả các khóa cấu hình cụ thể, kiểu dữ liệu, mô tả, mặc định... |
| `hints` | Gợi ý các giá trị hoặc cách nhập thích hợp cho một thuộc tính |

Không phải tệp metadata nào cũng có đầy đủ mọi trường hoặc cả ba mảng. Nội dung phụ thuộc vào mã nguồn, annotation processor, metadata bổ sung và quá trình build.

Một minh họa:

```json
{
  "groups": [
    {
      "name": "gateway",
      "type": "com.example.configdemo.GatewayProperties",
      "sourceType": "com.example.configdemo.GatewayProperties"
    }
  ],
  "properties": [
    {
      "name": "gateway.base-url",
      "type": "java.net.URI",
      "sourceType": "com.example.configdemo.GatewayProperties",
      "description": "Địa chỉ dịch vụ gateway."
    },
    {
      "name": "gateway.connect-timeout",
      "type": "java.time.Duration",
      "sourceType": "com.example.configdemo.GatewayProperties",
      "description": "Thời gian chờ kết nối gateway."
    },
    {
      "name": "gateway.max-attempts",
      "type": "java.lang.Integer",
      "sourceType": "com.example.configdemo.GatewayProperties",
      "description": "Số lần thử tối đa."
    }
  ],
  "hints": []
}
```

Đây là **ví dụ minh họa cấu trúc**, không phải cam kết JSON mà một phiên bản annotation processor cụ thể sẽ sinh ra chính xác từng trường. Một số metadata tự động có thể không chứa `description` nếu mã Java không cung cấp thông tin đủ để suy ra mô tả.

## 4. Phân biệt tên, kiểu, mô tả và giá trị mặc định

Trong phần tử của `properties`, bạn có thể gặp các trường:

- `name`: khóa cấu hình theo dạng chuẩn, ví dụ `gateway.connect-timeout`.
- `type`: tên kiểu Java tương ứng, ví dụ `java.time.Duration`.
- `description`: văn bản giúp người đọc hiểu ý nghĩa thuộc tính.
- `sourceType`: kiểu Java khai báo hoặc tạo ra thuộc tính.
- `sourceMethod`: thông tin phương thức nguồn trong những trường hợp phù hợp.
- `defaultValue`: giá trị mặc định được metadata mô tả, nếu có thể xác định.
- `deprecation`: thông tin về việc không nên tiếp tục sử dụng thuộc tính cũ, nếu có.

Ví dụ:

```json
{
  "name": "gateway.connect-timeout",
  "type": "java.time.Duration",
  "description": "Thời gian chờ kết nối tới gateway.",
  "defaultValue": "5s"
}
```

**Cực kỳ quan trọng:** trường `defaultValue` trong tệp JSON là **thông tin mô tả**, không phải lời yêu cầu runtime binder bắt buộc lấy `5s` làm mặc định.

Để runtime thực sự có mặc định, ứng dụng cần cung cấp mặc định qua một cơ chế hỗ trợ, chẳng hạn:

```yaml
gateway:
  connect-timeout: 5s
```

hoặc đối với constructor binding:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        @DefaultValue("5s") Duration connectTimeout) {
}
```

Thay đổi riêng JSON metadata mà không thay đổi nguồn cấu hình hoặc logic binding **không nhất thiết làm runtime nhận giá trị đó**.

Tương tự, mô tả `"Phải lớn hơn 0"` chỉ là tài liệu; muốn ràng buộc thật thì cần Bean Validation hoặc kiểm tra trong constructor.

## 5. Tạo metadata bằng spring-boot-configuration-processor

Spring Boot cung cấp công cụ **annotation processor**:

```text
org.springframework.boot:spring-boot-configuration-processor
```

Công cụ này phân tích các lớp cấu hình và tạo metadata **trong lúc biên dịch**, không phải lúc ứng dụng đang phục vụ yêu cầu.

Một quy trình khái quát:

```text
Java source:
  @ConfigurationProperties(prefix="gateway")
                     |
                     v
        Java annotation processing
                     |
          spring-boot-configuration-processor
                     |
                     v
   META-INF/spring-configuration-metadata.json
                     |
                     v
                 JAR
                     |
                     v
           IDE / developer tooling
```

Quy trình khác với:

```text
application.yml + environment + CLI
                     |
                     v
              Runtime Binder
                     |
                     v
          GatewayProperties bean
```

Cùng một lớp `GatewayProperties` có thể tham gia cả hai đường đi, nhưng metadata sinh lúc build và binding lúc chạy là hai công đoạn riêng biệt.

### 5.1. Khai báo với Maven

Trong dự án Spring Boot dùng Maven, có thể cấu hình:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

Cách này phổ biến với dự án theo cơ chế quản lý dependency của Spring Boot. Trong những build tùy biến, annotation processing có thể được cấu hình qua `maven-compiler-plugin` và `annotationProcessorPaths`.

Vì hành vi của compiler plugin, version Java và cách quản lý processor có thể khác nhau, hãy xác nhận annotation processing thực sự được kích hoạt trong build đang dùng, thay vì mặc định rằng chỉ thêm dependency vào `pom.xml` luôn đủ trong mọi thiết lập.

Build:

```bash
./mvnw clean package
```

Hoặc nếu dự án không có Maven Wrapper:

```bash
mvn clean package
```

Với Maven build thông thường, metadata của module có thể xuất hiện ở:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

Nếu không thấy, hãy kiểm tra xem lớp `@ConfigurationProperties` có được biên dịch trong module này không và processor có được chạy không.

### 5.2. Khai báo với Gradle

Trong Gradle Groovy DSL:

```groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
```

Khi dùng Spring Boot plugin và dependency management phù hợp, phiên bản processor có thể được quản lý cùng phiên bản Boot.

Build:

```bash
./gradlew clean build
```

Hoặc nếu chỉ cần tạo executable JAR:

```bash
./gradlew bootJar
```

Các đường dẫn build phụ thuộc vào phiên bản và cấu hình Gradle. Metadata sinh bởi Java annotation processing thường nằm trong đầu ra class/resource của module và được đưa vào JAR khi đóng gói đúng cách.

Nếu dự án dùng Kotlin, KAPT hoặc KSP và cấu hình các processor khác, cách khai báo processor không nhất thiết giống `annotationProcessor` của Java. Khi đó cần tuân theo cấu hình build dành cho ngôn ngữ và công cụ tương ứng.

## 6. Viết lớp ConfigurationProperties để sinh metadata

Một ví dụ Java dùng record:

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        URI baseUrl,
        @DefaultValue("5s") Duration connectTimeout,
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("true") boolean enabled) {
}
```

Khi build với processor, metadata có thể mô tả các khóa:

```text
gateway.base-url
gateway.connect-timeout
gateway.max-attempts
gateway.enabled
```

Tên thuộc tính Java camelCase như `connectTimeout` được biểu diễn bằng tên cấu hình chuẩn dạng kebab-case `connect-timeout`.

Processor giúp IDE biết loại dữ liệu mong muốn. Ví dụ:

- `gateway.base-url` có kiểu `URI`.
- `gateway.connect-timeout` có kiểu `Duration`.
- `gateway.max-attempts` có kiểu số nguyên.
- `gateway.enabled` có kiểu Boolean.

Một mô tả tốt cũng quan trọng: kiểu `Duration` nói rằng giá trị là thời lượng, nhưng không nói **thời gian chờ cho giai đoạn kết nối tới hệ thống nào**. Có thể thêm Javadoc phù hợp hoặc metadata bổ sung để giải thích ý nghĩa nghiệp vụ.

### 6.1. Có @ConfigurationProperties chưa chắc có JSON

Chỉ thêm:

```java
@ConfigurationProperties(prefix = "gateway")
```

vào mã Java không bảo đảm tự tạo tệp metadata. Annotation processor phải thực sự chạy trong giai đoạn biên dịch.

Điều đó không đồng nghĩa annotation không hoạt động ở runtime: **binding cấu hình vẫn có thể hoạt động khi metadata không được sinh**, miễn là lớp được đăng ký và những điều kiện liên kết cấu hình khác được đáp ứng.

Vì vậy, khi IDE không gợi ý thuộc tính nhưng ứng dụng vẫn chạy, cần kiểm tra processor và JAR đầu ra trước khi kết luận Spring Boot không đọc được cấu hình.

## 7. Kiểm tra đầu ra của processor trước khi đóng gói

Sau khi build Maven, kiểm tra tệp:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

Trên Linux/macOS:

```bash
ls -l target/classes/META-INF/spring-configuration-metadata.json
cat target/classes/META-INF/spring-configuration-metadata.json
```

Với PowerShell:

```powershell
Get-Item .\target\classes\META-INF\spring-configuration-metadata.json
Get-Content .\target\classes\META-INF\spring-configuration-metadata.json -Raw
```

Trường hợp dùng Gradle, đường dẫn cụ thể có thể khác, ví dụ một đường dẫn bên trong `build/classes/java/main/META-INF/`.

Ở bước này, bạn đang kiểm tra **kết quả biên dịch của module**, chưa chắc là nội dung cuối cùng trong JAR được triển khai.

Một tệp metadata xuất hiện ở thư mục build nhưng bị loại khỏi khâu packaging, hoặc một JAR cũ chưa được build lại, đều có thể khiến bản phát hành không chứa thông tin bạn mong muốn.

## 8. Kiểm tra metadata trong JAR thông thường

Một JAR thư viện Java tiêu chuẩn có thể có cấu trúc:

```text
my-config-library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── spring-configuration-metadata.json
└── com/
    └── example/
        └── config/
            └── GatewayProperties.class
```

Dùng công cụ `jar` của JDK để liệt kê các mục bên trong:

```bash
jar tf my-config-library.jar
```

Tìm riêng metadata trên Linux/macOS:

```bash
jar tf my-config-library.jar | grep 'spring-configuration-metadata.json'
```

Trên PowerShell:

```powershell
jar tf .\my-config-library.jar |
    Select-String 'spring-configuration-metadata\.json'
```

Trong thư viện JAR thông thường, đường dẫn thường là:

```text
META-INF/spring-configuration-metadata.json
```

Nếu đường dẫn có mặt, kiểm tra nội dung JSON thay vì chỉ nhìn tên file. Tệp rỗng, tệp thiếu nhóm thuộc tính hoặc tệp từ một phiên bản cũ có thể không cung cấp gợi ý IDE như kỳ vọng.

Lệnh `jar tf` chỉ **liệt kê entry**, không tự xác nhận JSON có đúng schema hoặc phản ánh mã nguồn hiện tại.

## 9. Kiểm tra metadata trong Spring Boot executable JAR

Một ứng dụng được đóng gói bởi Maven/Gradle Spring Boot plugin thường tạo **executable JAR** có cấu trúc khác JAR thư viện tiêu chuẩn.

Minh họa:

```text
my-app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/configdemo/...
    │   ├── application.yml
    │   └── META-INF/
    │       └── spring-configuration-metadata.json
    └── lib/
        ├── spring-boot-....jar
        ├── spring-boot-autoconfigure-....jar
        └── other-dependency.jar
```

Vì vậy metadata do **module ứng dụng** tạo ra thường nằm ở:

```text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

Lệnh kiểm tra:

```bash
jar tf target/my-app.jar | grep 'spring-configuration-metadata.json'
```

Trên PowerShell:

```powershell
jar tf .\target\my-app.jar |
    Select-String 'spring-configuration-metadata\.json'
```

Nếu muốn đọc trực tiếp nội dung và máy đã cài tiện ích `unzip`:

```bash
unzip -p target/my-app.jar \
  BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

Lệnh này in nội dung entry ra stdout, không cần giải nén toàn bộ JAR. Đường dẫn cần trùng **chính xác tên entry** mà `jar tf` đã báo.

Nếu không có `unzip`, bạn có thể dùng `jar xf` trong một thư mục tạm để trích entry cụ thể rồi mở bằng trình đọc JSON; tránh giải nén vào thư mục nguồn dự án khi có nguy cơ ghi đè file hiện hữu.

### 9.1. Vì sao JAR thư viện và Boot JAR có đường dẫn khác nhau?

Đối với thư viện Java thông thường, các class và resource thường ở root của JAR.

Đối với Boot executable JAR, class/resource của ứng dụng thường nằm trong `BOOT-INF/classes/`, còn dependency JAR nằm trong `BOOT-INF/lib/`.

Cấu trúc này giải thích vì sao một lệnh tìm chính xác root `META-INF/spring-configuration-metadata.json` có thể không thấy metadata của ứng dụng khi thực tế tệp nằm dưới `BOOT-INF/classes/META-INF/`.

Không nên đồng nhất mọi dạng phân phối Spring Boot — có thể có plain JAR, executable JAR, WAR, layered JAR hoặc bố trí tùy chỉnh. Hãy dùng `jar tf` để quan sát cấu trúc thật của artifact.

## 10. Metadata nằm trong dependency JAR

Một ứng dụng có thể phụ thuộc vào thư viện:

```text
acme-client-spring-boot-starter.jar
```

Thư viện ấy khai báo các khóa:

```text
acme.client.endpoint
acme.client.timeout
acme.client.retries
```

Metadata của các khóa có thể nằm trong **JAR dependency**, không phải metadata của chính module ứng dụng.

Với Boot executable JAR, các dependency thường được đóng gói dưới:

```text
BOOT-INF/lib/acme-client-spring-boot-starter.jar
```

**Chi tiết cần nhớ:** `jar tf my-app.jar` liệt kê các entry của **JAR ngoài**, bao gồm tên tệp JAR phụ thuộc. Nó **không tự mở sâu vào từng JAR lồng bên trong** để liệt kê metadata ở root của mỗi dependency.

Vì vậy, nếu `jar tf my-app.jar | grep spring-configuration-metadata.json` chỉ thấy metadata của ứng dụng, không thể kết luận các dependency không có metadata.

Để kiểm tra metadata dependency, có thể:

1. Tìm JAR của dependency trong cache Maven/Gradle, rồi chạy `jar tf` trên chính JAR đó.
2. Trích một JAR dependency từ `BOOT-INF/lib/` ra thư mục tạm, sau đó chạy `jar tf` với JAR vừa trích.
3. Kiểm tra nội dung artifact thư viện được xuất bản, nếu có sẵn.

Một dependency có thể có metadata kể cả khi module ứng dụng không sinh metadata của riêng nó. Ngược lại, metadata của ứng dụng có thể đầy đủ nhưng dependency mà IDE đang dùng lại là một phiên bản cũ.

## 11. Phân biệt metadata của ứng dụng và metadata của thư viện

Khi thấy một tệp metadata, hãy trả lời ba câu hỏi:

**1. Artifact nào chứa tệp đó?**

- Module ứng dụng?
- JAR thư viện chung do nhóm tự phát triển?
- Spring Boot starter của bên thứ ba?
- Một dependency transitively included?

**2. Nội dung metadata mô tả nhóm khóa nào?**

- `gateway.*` của chính ứng dụng?
- `spring.datasource.*` thuộc cơ chế auto-configuration?
- `server.*` của embedded server?
- `acme.client.*` của thư viện bên ngoài?

**3. Ứng dụng đang chạy phiên bản artifact nào?**

Một file metadata đúng trong mã nguồn nhưng JAR triển khai lại cũ sẽ không giúp giải thích trạng thái runtime. Và JAR runtime có metadata mới cũng không bảo đảm IDE đã cập nhật index hoặc đang sử dụng cùng phiên bản dependency.

Cần tránh nhầm hai kết luận:

- “Có metadata trong một JAR” nghĩa là **artifact đó chứa dữ liệu mô tả cấu hình**.
- “Ứng dụng đang dùng bean cấu hình của module đó” còn phụ thuộc vào **class path, cơ chế đăng ký bean, auto-configuration và trạng thái runtime**.

Không có phép suy diễn tự động từ kết luận thứ nhất sang kết luận thứ hai.

## 12. Kiểm tra JSON metadata cụ thể

Ví dụ một tệp metadata rút gọn:

```json
{
  "groups": [
    {
      "name": "payment",
      "type": "com.example.configdemo.PaymentProperties",
      "sourceType": "com.example.configdemo.PaymentProperties"
    }
  ],
  "properties": [
    {
      "name": "payment.base-url",
      "type": "java.net.URI",
      "description": "URL của cổng thanh toán."
    },
    {
      "name": "payment.max-attempts",
      "type": "java.lang.Integer",
      "description": "Số lần gọi lại tối đa.",
      "defaultValue": 3
    },
    {
      "name": "payment.mode",
      "type": "com.example.configdemo.PaymentMode",
      "description": "Chế độ xử lý thanh toán."
    }
  ],
  "hints": [
    {
      "name": "payment.mode",
      "values": [
        {"value": "sandbox", "description": "Dùng môi trường thử nghiệm."},
        {"value": "live", "description": "Dùng môi trường thật."}
      ]
    }
  ]
}
```

Khi xem JSON:

- Tên `payment.max-attempts` cho biết khóa chuẩn.
- `type` chỉ định kiểu Java tương ứng.
- `description` là lời giải thích cho người viết cấu hình.
- `defaultValue` mô tả giá trị mặc định đã biết hoặc do metadata bổ sung cung cấp.
- `hints.values` gợi ý các lựa chọn khi nhập `payment.mode`.

**Hints không đồng nghĩa enum constraint lúc chạy.** Nếu metadata gợi ý `sandbox` và `live`, một giá trị khác chỉ bị runtime từ chối khi kiểu đích, converter hoặc validator thực sự không chấp nhận nó. Không nên coi một danh sách hint trong JSON là danh sách kiểm soát quyền hoặc tập giá trị bắt buộc của mọi trường hợp.

## 13. Thêm mô tả bằng Javadoc

Tài liệu tốt giúp giảm lỗi vận hành. Annotation processor có thể sử dụng thông tin mô tả từ mã nguồn phù hợp để đưa vào metadata.

Ví dụ:

```java
package com.example.configdemo;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "cache")
public class CacheProperties {

    /**
     * Thời gian giữ dữ liệu trong cache trước khi hết hạn.
     */
    private Duration ttl = Duration.ofMinutes(10);

    /**
     * Số lượng phần tử tối đa trong cache.
     */
    private int maxEntries = 500;

    public Duration getTtl() {
        return ttl;
    }

    public void setTtl(Duration ttl) {
        this.ttl = ttl;
    }

    public int getMaxEntries() {
        return maxEntries;
    }

    public void setMaxEntries(int maxEntries) {
        this.maxEntries = maxEntries;
    }
}
```

Khi annotation processor phân tích lớp cấu hình này, metadata có thể phản ánh kiểu dữ liệu và những mô tả liên quan. Việc sinh mô tả cụ thể phụ thuộc vào kiểu khai báo, Javadoc, processor và quá trình build.

Nếu metadata không chứa mô tả mong muốn, hãy kiểm tra JSON thật được sinh ra; không nên giả định mọi Javadoc ở mọi vị trí sẽ tự động xuất hiện.

Có thể viết metadata bổ sung để cập nhật hoặc làm rõ thông tin khi cần.

## 14. Bổ sung metadata thủ công

Spring Boot hỗ trợ một tệp bổ sung thường có tên:

```text
META-INF/additional-spring-configuration-metadata.json
```

Trong một dự án Maven/Gradle tiêu chuẩn, có thể đặt nó tại:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Ví dụ:

```json
{
  "properties": [
    {
      "name": "gateway.connect-timeout",
      "description": "Thời gian chờ để thiết lập kết nối tới gateway."
    },
    {
      "name": "gateway.mode",
      "description": "Chế độ hoạt động của gateway."
    }
  ],
  "hints": [
    {
      "name": "gateway.mode",
      "values": [
        {
          "value": "sandbox",
          "description": "Dùng cho môi trường thử nghiệm."
        },
        {
          "value": "live",
          "description": "Dùng cho môi trường thật."
        }
      ]
    }
  ]
}
```

Khi cấu hình processor hoạt động đúng, dữ liệu bổ sung có thể được kết hợp vào metadata sinh ra để mở rộng mô tả hoặc cung cấp những hint mà processor không suy ra được.

**Không nhầm hai file:**

| Tệp | Mục đích |
| --- | --- |
| `spring-configuration-metadata.json` | Metadata đầu ra được công cụ sử dụng, thường do processor tạo |
| `additional-spring-configuration-metadata.json` | Nguồn metadata bổ sung để processor kết hợp vào đầu ra |

Chỉ tạo `additional-spring-configuration-metadata.json` không đảm bảo bean runtime sẽ có một thuộc tính mới; bạn vẫn cần mã binding tương ứng hoặc cơ chế xử lý cấu hình thực tế.

Ngoài ra, nếu module đang đóng gói một bản metadata đã cũ và processor không chạy, tệp bổ sung có thể không được hợp nhất vào metadata chính như mong đợi. Hãy kiểm tra artifact cuối cùng sau khi build.

## 15. Metadata bổ sung không tạo chức năng runtime

Giả sử bạn thêm:

```json
{
  "properties": [
    {
      "name": "gateway.allow-unsafe-calls",
      "type": "java.lang.Boolean",
      "description": "Cho phép cuộc gọi không an toàn.",
      "defaultValue": false
    }
  ]
}
```

vào nguồn metadata bổ sung. Sau đó IDE có thể gợi ý một khóa với tên trên nếu metadata được sinh và tích hợp.

Nhưng điều đó **không tạo ra**:

```java
boolean allowUnsafeCalls;
```

trong một bean `@ConfigurationProperties`, cũng không khiến service tự đổi hành vi.

Tương tự, đặt `defaultValue: false` chỉ mô tả một mặc định cho công cụ. Nếu binder không nhận biết property này hoặc mã không sử dụng nó, nội dung metadata không biến thành giá trị cấu hình runtime.

Vì vậy phải kiểm tra ba lớp độc lập:

1. **Metadata:** IDE/công cụ có thông tin về khóa?
2. **Binding:** bean runtime có thành phần tương ứng và được đăng ký?
3. **Nghiệp vụ:** service có thật sự sử dụng giá trị đó?

Một hệ thống có metadata đẹp nhưng logic ứng dụng không đọc thuộc tính vẫn không tạo ra tính năng tương ứng.

## 16. Metadata có vai trò gì đối với IDE?

Nhiều IDE và extension có thể đọc Spring configuration metadata để:

- Gợi ý tên thuộc tính lúc chỉnh sửa `application.yml` hoặc `application.properties`.
- Hiển thị mô tả hoặc kiểu giá trị.
- Đưa ra gợi ý về giá trị có sẵn, ví dụ enum hoặc danh sách hint.
- Cảnh báo một số khóa không còn được khuyến nghị sử dụng.
- Phát hiện một số tên cấu hình lạ trong phạm vi metadata mà công cụ nhận biết.

**Đây là chức năng của công cụ phát triển**, không phải lời cam kết rằng chính Spring Boot runtime sẽ chạy cùng một bộ quy tắc kiểm tra.

Có những khác biệt thực tế:

- IDE A có thể hiểu metadata của dependency tốt hơn IDE B.
- Một extension có thể cần được bật hoặc cập nhật.
- Sau khi thêm processor, IDE có thể phải đồng bộ dependency hoặc rebuild để nhận file mới.
- Cảnh báo “unknown property” trong IDE có thể là **false positive** với thuộc tính động hoặc thuộc tính do thư viện cung cấp mà metadata chưa được nạp.
- Không có cảnh báo IDE không đồng nghĩa cấu hình runtime hợp lệ.

Khi kiểm tra một vấn đề về autocomplete, nên xác minh IDE đang mở **đúng module, classpath và phiên bản JAR**. Khi kiểm tra vấn đề ứng dụng khởi động, nên xem **Runtime Environment, binder và validation**.

## 17. Cảnh báo thuộc tính deprecated trong metadata

Metadata cũng có thể mô tả một thuộc tính đã cũ:

```json
{
  "name": "gateway.legacy-timeout",
  "type": "java.time.Duration",
  "description": "Tên timeout cũ.",
  "deprecation": {
    "level": "warning",
    "reason": "Thuộc tính cũ được thay bằng connect-timeout.",
    "replacement": "gateway.connect-timeout"
  }
}
```

Thông tin này có thể giúp IDE hiển thị cảnh báo và gợi ý tên thay thế.

Cần phân biệt:

- **Metadata deprecation:** tín hiệu cho công cụ phát triển và tài liệu.
- **`@Deprecated` trong Java:** dấu hiệu API Java không còn được khuyến nghị.
- **Runtime rejection:** việc ứng dụng thực sự từ chối một khóa cũ.

Không thể kết luận rằng một thuộc tính được đánh dấu deprecated trong metadata sẽ tự gây lỗi lúc khởi động. Thư viện có thể tiếp tục hỗ trợ khóa cũ để giữ tương thích, hoặc có chính sách riêng cho việc từ chối.

Khi muốn loại bỏ một thuộc tính, hãy thực hiện thay đổi ở mã binding hoặc quy trình kiểm tra runtime thích hợp, đồng thời cập nhật metadata để hỗ trợ người dùng di chuyển.

## 18. Metadata không bảo đảm runtime validation

Xét metadata:

```json
{
  "properties": [
    {
      "name": "worker.max-threads",
      "type": "java.lang.Integer",
      "description": "Số luồng phải nằm trong khoảng 1..32."
    }
  ]
}
```

Một người viết:

```properties
worker.max-threads=-10
```

Nếu bean Java chỉ có:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

thì số `-10` vẫn là một `int` hợp lệ về kiểu. Chỉ vì metadata có câu “1..32” **không có nghĩa** Spring Boot tự áp dụng giới hạn đó.

Muốn từ chối lúc khởi động, dùng Bean Validation:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @Min(1) @Max(32) int maxThreads) {
}
```

Dự án Spring Boot 3.x cần một Bean Validation provider phù hợp, thường được cung cấp qua `spring-boot-starter-validation`.

Khi giá trị `-10` được binder chuyển thành số nguyên, validation có thể từ chối và làm context khởi tạo thất bại.

**Metadata không thay thế `@Validated`, `@Min`, `@NotBlank`, `@NotNull`, `@Valid` hoặc những ràng buộc trong constructor.**

## 19. Ví dụ runtime: ràng buộc cấu hình thực sự

Tệp:

```yaml
# application.yml
payment:
  endpoint: "https://pay.example.invalid"
  max-retries: 4
```

Record:

```java
package com.example.configdemo;

import java.net.URI;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        @NotNull URI endpoint,
        @Min(1) int maxRetries) {
}
```

Lớp ứng dụng:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

Trong trường hợp:

```properties
payment.max-retries=0
```

runtime binder có thể chuyển `0` thành `int`, nhưng validator từ chối do vi phạm `@Min(1)`.

Không cần đọc file `spring-configuration-metadata.json` ở runtime để thực hiện kiểm tra này. Spring sử dụng thông tin từ annotation trên kiểu cấu hình và cơ chế Bean Validation đã được thiết lập.

Nếu bỏ annotation processor nên metadata không còn sinh, Bean Validation vẫn có thể hoạt động. Nếu bỏ `@Validated` hoặc validation provider, việc metadata vẫn tồn tại không tự thay thế cơ chế validation.

## 20. Bốn tình huống dễ nhầm

Hãy xem bảng:

| Tình huống | Metadata có? | Runtime có thể bind/validate? |
| --- | --- | --- |
| Có processor, có `@ConfigurationProperties`, có validation | Có thể có | Có, nếu bean được đăng ký và provider hoạt động |
| Không có processor, vẫn có `@ConfigurationProperties` | Có thể thiếu | Vẫn có thể bind bình thường |
| Có metadata thủ công, không có bean/runtime xử lý | Có | Không tự xuất hiện tính năng/binding |
| Có metadata nhưng giá trị sai ràng buộc runtime | Có | Có thể bị từ chối khi bind/validate |

Kết luận: **metadata, đăng ký bean, chuyển đổi kiểu và validation có mối quan hệ nhưng không thể dùng sự tồn tại của một thành phần để khẳng định thành phần khác đã hoạt động**.

## 21. Metadata và kiểm tra khóa viết sai

Giả sử bean chờ đợi:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

Metadata có tên:

```text
worker.max-threads
```

Nhưng YAML viết:

```yaml
worker:
  max-threds: 8
```

IDE có metadata thích hợp **có thể** cảnh báo `max-threds` không được nhận diện. Nhưng nếu IDE không cảnh báo hoặc một người chỉnh YAML bằng trình soạn thảo văn bản không hỗ trợ metadata, runtime có thể vẫn bỏ qua thuộc tính lạ theo cấu hình binding mặc định.

Để giúp runtime từ chối khóa không được bind trong phạm vi bean, có thể cân nhắc:

```java
@ConfigurationProperties(
        prefix = "worker",
        ignoreUnknownFields = false)
public record WorkerProperties(int maxThreads) {
}
```

Với một khóa sai nằm trong prefix `worker` mà binder thực sự nhìn thấy, chế độ này có thể khiến quá trình binding thất bại thay vì im lặng bỏ qua.

**Nhưng vẫn có giới hạn:**

- Đây không phải trình quét toàn bộ các khóa trong tất cả PropertySource.
- Lỗi ở chính prefix, ví dụ `wroker.max-threads`, có thể nằm ngoài phạm vi bean được bind.
- Một số namespace có map hoặc khóa động, nên “khóa lạ” có thể thực sự là dữ liệu hợp lệ.
- Chỉ khi bean được đăng ký và được bind thì quy tắc mới phát huy tác dụng.
- Tệp cấu hình không được nạp do profile chưa hoạt động cũng không được kiểm tra trong lần chạy ấy.

Vì vậy, metadata IDE và `ignoreUnknownFields = false` **bổ trợ** nhau, nhưng cả hai chưa đủ để chứng minh mọi tệp cho mọi môi trường không có lỗi gõ tên.

## 22. Metadata không thay thế kiểm thử cấu hình theo profile

Giả sử dự án có:

```text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
```

Tệp `application-prod.yml`:

```yaml
worker:
  max-threads: -2
```

Metadata có thể ghi rõ `worker.max-threads` là số nguyên và chứa mô tả “Giới hạn 1..32”. Tuy nhiên metadata không tự mở và kiểm tra mọi tệp theo profile trước khi deployment.

Nếu chạy ứng dụng chỉ với profile `dev`, `application-prod.yml` có thể không được nạp. Validation runtime của cấu hình `prod` vì thế cũng không được kích hoạt ở lần chạy `dev`.

Để kiểm tra cấu hình production, cần khởi động hoặc thử bind với nguồn/profile tương ứng, chẳng hạn trong môi trường test:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Nếu `WorkerProperties` có `@Validated @Min(1)` và bean được đăng ký, runtime sẽ có cơ hội phát hiện giá trị `-2` khi profile `prod` tạo nên giá trị có hiệu lực.

Không nên đưa secrets thật vào ví dụ/test hoặc log toàn bộ đối tượng cấu hình để chẩn đoán.

## 23. Kiểm thử binding và validation bằng ApplicationContextRunner

Spring Boot Test cung cấp `ApplicationContextRunner` để xây dựng một ApplicationContext nhỏ và cấp giá trị cấu hình cho nó.

Ví dụ bean:

```java
package com.example.configdemo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @NotBlank String queueName,
        @Min(1) @Max(32) int maxThreads) {
}
```

Test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class WorkerPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void acceptsValidConfiguration() {
        runner.withPropertyValues(
                "worker.queue-name=orders",
                "worker.max-threads=8"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            WorkerProperties properties =
                    context.getBean(WorkerProperties.class);
            assertThat(properties.queueName()).isEqualTo("orders");
            assertThat(properties.maxThreads()).isEqualTo(8);
        });
    }

    @Test
    void rejectsInvalidThreadCount() {
        runner.withPropertyValues(
                "worker.queue-name=orders",
                "worker.max-threads=-5"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Test
    void rejectsMissingQueueName() {
        runner.withPropertyValues(
                "worker.max-threads=8"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class TestConfiguration {
    }
}
```

Test này **không kiểm tra file metadata có nằm trong JAR hay không**. Nó kiểm tra một thứ khác, thực tế hơn ở runtime: binder có tạo được bean với dữ liệu đúng và từ chối dữ liệu sai ràng buộc không?

Ngược lại, việc mở JSON metadata để tìm tên `worker.queue-name` không chứng minh bài test trên sẽ chạy thành công nếu provider validation bị thiếu hoặc bean chưa được đăng ký.

Hai loại kiểm tra phục vụ hai mục đích độc lập.

## 24. Kiểm tra file metadata trong pipeline build

Trong CI/CD, một dự án có thể thêm bước kiểm tra cấu trúc artifact. Mục đích là tránh phát hành thư viện cấu hình mà công cụ phát triển không thể khám phá thuộc tính.

Quy trình gợi ý:

1. Build module chứa `@ConfigurationProperties`.
2. Xác nhận processor đã tạo `spring-configuration-metadata.json`.
3. Xác nhận JSON không rỗng và có nhóm/thuộc tính quan trọng.
4. Tạo JAR.
5. Kiểm tra file metadata nằm trong chính artifact sẽ phát hành.
6. Chạy test runtime binding/validation độc lập.

Ví dụ các lệnh Java phổ thông:

```bash
./mvnw clean package
jar tf target/my-app.jar
```

Trong CI sử dụng Linux và có công cụ `unzip`:

```bash
unzip -p target/my-app.jar \
  BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

Trong Windows PowerShell, dùng `jar tf ... | Select-String ...` để xác nhận entry.

Nếu dự án tạo **library JAR** thay vì Boot executable JAR, đường dẫn thường là `META-INF/spring-configuration-metadata.json`. Script CI nên biết loại artifact mục tiêu hoặc kiểm tra entry thực tế, không mã hóa cứng một đường dẫn cho mọi dự án.

Nên coi bước kiểm tra metadata là **kiểm tra artifact/tooling**, còn bước kiểm thử validation là **kiểm tra hành vi runtime**. Cả hai có thể hiện diện trong pipeline nhưng kết quả không thay thế nhau.

## 25. Thêm kiểm tra JSON trong quá trình build

Khi cần xác nhận tên thuộc tính đã xuất hiện, có thể đọc JSON bằng một công cụ phù hợp.

Giả sử trong pipeline Linux có `jq`:

```bash
unzip -p target/my-app.jar \
  BOOT-INF/classes/META-INF/spring-configuration-metadata.json \
  | jq -r '.properties[]?.name'
```

Lệnh này liệt kê tên property trong metadata của module ứng dụng bên trong Boot executable JAR.

Có thể tìm riêng:

```bash
unzip -p target/my-app.jar \
  BOOT-INF/classes/META-INF/spring-configuration-metadata.json \
  | jq -e '.properties[]? | select(.name == "gateway.connect-timeout")'
```

Nếu lệnh thứ hai không tìm thấy property, cần xem lại:

- Lớp cấu hình có được processor xử lý không?
- Tên prefix hoặc thành phần Java có đúng không?
- Processor có chạy trong module hiện tại không?
- JAR đang kiểm tra có phải artifact mới build không?
- Metadata nằm trong ứng dụng hay trong JAR dependency khác?

Không nên chỉnh sửa thủ công trực tiếp JAR chỉ để thêm một JSON rồi kết luận tính năng runtime đã được bổ sung. Nếu nguồn metadata thiếu, sửa build/mã nguồn và build lại artifact một cách tái lập.

## 26. Phân biệt metadata với spring-autoconfigure-metadata.properties

Trong hệ sinh thái Spring Boot, bạn có thể gặp các tệp khác cũng nằm dưới `META-INF`, chẳng hạn:

```text
META-INF/spring-autoconfigure-metadata.properties
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Những tệp này phục vụ những phần khác của cơ chế auto-configuration hoặc đăng ký các lớp cấu hình tự động, không phải tài liệu mô tả danh sách các property mà IDE sẽ đề xuất.

Không nên đồng nhất:

| Tệp | Vai trò khái quát |
| --- | --- |
| `spring-configuration-metadata.json` | Mô tả nhóm và property cho công cụ cấu hình |
| `additional-spring-configuration-metadata.json` | Nguồn metadata bổ sung khi build |
| `spring-autoconfigure-metadata.properties` | Metadata hỗ trợ cơ chế auto-configuration trong những phiên bản/cách tổ chức phù hợp |
| `AutoConfiguration.imports` | Danh sách lớp auto-configuration được công bố bởi một module |

Một dự án có thể chứa tất cả hoặc chỉ một vài tệp. Sự tồn tại của file này không chứng minh file kia đã được sinh.

Khi một IDE không gợi ý `gateway.connect-timeout`, hãy kiểm tra **configuration metadata JSON**, không đi tìm tên property trong danh sách auto-configuration class.

## 27. Không nên đọc metadata JSON bằng ứng dụng để tự tạo cấu hình

Một sai lầm thiết kế là xem metadata như nguồn cấu hình runtime rồi tự đọc nó để dựng giá trị.

Ví dụ, không nên mặc định rằng:

```text
spring-configuration-metadata.json
       |
       v
Spring Boot tự đọc defaultValue và đặt vào Environment
```

Cơ chế đúng trong ứng dụng thông thường là:

```text
application.yml / CLI / Environment
       |
       v
Spring Environment
       |
       v
ConfigurationProperties Binder
       |
       v
Bean cấu hình
```

Trong khi đó:

```text
@ConfigurationProperties ở source code
       |
       v
Annotation processor lúc build
       |
       v
spring-configuration-metadata.json
       |
       v
IDE/tooling tham khảo
```

Vì metadata chủ yếu là **mô tả**, việc tự xây cơ chế runtime đọc `defaultValue` từ JSON thường tạo thêm sự phức tạp và có nguy cơ xung đột với thứ tự ưu tiên của Spring.

Nếu muốn default thật, dùng một nguồn cấu hình hợp lệ, `@DefaultValue`, mặc định field theo JavaBean binding hoặc cơ chế được Spring Boot hỗ trợ cho kiểu bean của bạn.

## 28. Nếu file metadata không có trong JAR thì sao?

Một số nguyên nhân thường gặp:

### 28.1. Không khai báo configuration processor

Dự án chỉ có `spring-boot-starter` và `@ConfigurationProperties`, nhưng không cấu hình `spring-boot-configuration-processor`.

**Cách xử lý:** thêm processor theo công cụ build và chạy lại compile.

### 28.2. Annotation processing bị tắt

IDE hoặc compiler có thể được cấu hình bỏ qua annotation processing.

**Cách xử lý:** kiểm tra thiết lập biên dịch, processor path và log build. Ưu tiên xác nhận bằng build tái lập từ Maven/Gradle, không chỉ nhìn trạng thái IDE.

### 28.3. Kiểm tra nhầm JAR

Module ứng dụng có thể là `my-app.jar`, còn cấu hình được khai báo trong module `my-common-config.jar`.

**Cách xử lý:** tìm đúng module chứa lớp `@ConfigurationProperties` và kiểm tra artifact tương ứng.

### 28.4. Tìm sai vị trí trong Boot JAR

Bạn tìm ở `META-INF/` root nhưng thực tế metadata của ứng dụng nằm dưới `BOOT-INF/classes/META-INF/`.

**Cách xử lý:** dùng `jar tf` để xem cấu trúc thực.

### 28.5. Metadata nằm trong nested dependency

Ứng dụng phụ thuộc vào starter có metadata trong JAR của starter.

**Cách xử lý:** mở JAR dependency trực tiếp; lệnh `jar tf` trên outer Boot JAR không mở sâu mọi nested JAR.

### 28.6. Processor chạy nhưng không thấy kiểu muốn mô tả

Có thể lớp không được compiler xử lý trong module đang build, tên annotation sai, module source set khác, quá trình build bỏ qua nguồn, hoặc một số pattern khó suy luận tự động.

**Cách xử lý:** kiểm tra class thật được build, annotation processor path, cấu hình incremental build và metadata đầu ra trước khi đóng gói.

### 28.7. JAR được phát hành là bản cũ

Một pipeline có cache hoặc task packaging không chạy lại, khiến file metadata bên trong artifact không phản ánh mã mới.

**Cách xử lý:** clean build khi cần, xác định artifact theo version/checksum và kiểm tra đúng file chuẩn bị triển khai.

## 29. Nếu có metadata nhưng IDE vẫn không gợi ý thì sao?

Hãy xử lý theo thứ tự sau:

1. Xác nhận file metadata nằm trong module/JAR thực sự được IDE dùng.
2. Xác nhận JSON có đúng `properties[].name` mà bạn kỳ vọng.
3. Kiểm tra project đã import/sync Maven hoặc Gradle sau khi thêm processor.
4. Kiểm tra support Spring Boot của IDE/extension có được bật không.
5. Kiểm tra đúng file cấu hình và cú pháp (YAML, Properties) mà công cụ hỗ trợ.
6. Kiểm tra dependency version đang dùng bởi IDE.
7. Nếu cần, rebuild hoặc refresh index theo chức năng IDE.
8. Đừng xem việc không có autocomplete là lỗi runtime nếu ứng dụng vẫn bind đúng.

Một số thuộc tính cấu hình được tạo động hoặc do framework khác xử lý nên không có metadata để gợi ý. Đây không nhất thiết là lỗi.

Nếu IDE cảnh báo khóa không tồn tại nhưng runtime nhận giá trị, có thể IDE đang thiếu metadata hoặc có metadata chưa cập nhật. Ngược lại, IDE gợi ý khóa nhưng runtime không nhận có thể do bean chưa được kích hoạt, sai profile, thiếu dependency, hoặc cấu hình bị nguồn khác ghi đè.

## 30. Phân biệt cảnh báo tên khóa và lỗi chuyển đổi kiểu

Xét cấu hình:

```yaml
gateway:
  connect-timeout: "not-a-duration"
```

Metadata có thể nói `gateway.connect-timeout` là `java.time.Duration`. IDE có thể phát hiện định dạng không phù hợp nếu công cụ hỗ trợ quy tắc tương ứng, nhưng runtime vẫn phải thực hiện binding thật.

Khi chạy, binder không thể chuyển `not-a-duration` thành `Duration` theo cách thông thường và có thể làm context khởi tạo thất bại.

Ngược lại:

```yaml
gateway:
  connect-timout: 5s
```

đây là **tên khóa sai**. IDE có metadata có thể gợi ý tên đúng; runtime binder có thể bỏ qua khóa lạ theo chính sách mặc định, hoặc từ chối nếu bạn bật strict binding và khóa nằm trong phạm vi được kiểm soát.

Cuối cùng:

```yaml
gateway:
  max-attempts: -5
```

tên khóa đúng, kiểu `int` đúng, nhưng giá trị có thể vi phạm yêu cầu nghiệp vụ nếu có `@Min(1)`.

Ba tình huống cần ba hướng chẩn đoán khác nhau.

## 31. Những hiểu lầm cần tránh

### 31.1. “Có metadata JSON nghĩa là cấu hình đã được Spring nạp”

Sai. Metadata chủ yếu dành cho tooling; nạp cấu hình thực tế thuộc `Environment` và Config Data.

### 31.2. “IDE biết tên property thì runtime chắc chắn có bean”

Sai. Một property có metadata có thể thuộc module không được kích hoạt ở runtime, thuộc auto-configuration có điều kiện hoặc phiên bản khác.

### 31.3. “Đổi defaultValue trong metadata sẽ đổi mặc định runtime”

Sai. Cần sửa mặc định thực sự ở nguồn cấu hình hoặc cơ chế binder/constructor.

### 31.4. “Metadata đã nêu giới hạn số nên Bean Validation không cần thiết”

Sai. Mô tả giới hạn không tự thực thi `@Min` hay `@Max`.

### 31.5. “JAR không có metadata nghĩa là @ConfigurationProperties không chạy”

Không nhất thiết. Runtime binder không cần metadata JSON để hoạt động.

### 31.6. “jar tf app.jar sẽ tự tìm trong mọi JAR dependency”

Sai. `jar tf` chỉ liệt kê entry của JAR được mở; nested JAR cần được kiểm tra riêng.

### 31.7. “Thêm additional-spring-configuration-metadata.json là đủ để IDE và runtime cùng hiểu thuộc tính”

Không nhất thiết. Processor/build phải hợp nhất dữ liệu; runtime vẫn cần logic binding hoặc xử lý thuộc tính.

### 31.8. “Cảnh báo IDE là kết quả validation runtime”

Không phải. IDE có thể phân tích tĩnh theo metadata còn runtime dựa vào bean và dữ liệu có hiệu lực.

### 31.9. “Có metadata thì mọi profile đã được kiểm tra”

Sai. Metadata không chạy tất cả profile. Runtime kiểm tra những nguồn được nạp trong lần khởi động cụ thể.

### 31.10. “Mọi phần tử trong hints là tập giá trị cứng”

Không nhất thiết. Hints có thể là danh sách gợi ý. Quy tắc chấp nhận thật phải nằm ở kiểu đích, converter hoặc validator.

## 32. Quy trình điều tra lỗi theo câu hỏi

| Câu hỏi của nhóm phát triển | Nơi cần kiểm tra |
| --- | --- |
| IDE không autocomplete `gateway.*` | Processor, metadata JSON, module/JAR, IDE |
| Không thấy metadata trong executable JAR | `jar tf`, `BOOT-INF/classes/META-INF/` |
| Metadata của starter không thấy trong outer JAR | Kiểm tra chính nested dependency JAR |
| Thuộc tính không được runtime bind | Bean registration, prefix, Config Data, profile |
| Giá trị bind không đúng | PropertySource precedence, chuyển đổi kiểu |
| Giá trị âm nhưng ứng dụng không báo lỗi | Bean Validation hoặc constructor invariant |
| Khóa typo không làm khởi động thất bại | Strict unknown field và test cấu hình |
| Metadata có default nhưng runtime nhận null/0 | Mặc định thực tế trong YAML/Java/binder |
| IDE và runtime báo kết quả khác nhau | Kiểm tra version, classpath và phạm vi mỗi cơ chế |

Mục tiêu là **chọn đúng tầng để xử lý**. Sửa JSON metadata không giải quyết lỗi một bean không được đăng ký; thêm `@Validated` cũng không làm IDE tự có danh sách property nếu processor chưa sinh metadata.

## 33. Bài tập A: tìm đúng đường dẫn trong JAR

Một Boot executable JAR có cấu trúc:

```text
BOOT-INF/classes/com/example/configdemo/GatewayProperties.class
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
BOOT-INF/lib/acme-starter.jar
```

**Câu hỏi 1:** metadata do module ứng dụng sinh nằm ở đâu?

**Đáp án:** `BOOT-INF/classes/META-INF/spring-configuration-metadata.json`.

**Câu hỏi 2:** có thể kết luận `acme-starter.jar` không có metadata chỉ vì kết quả `jar tf app.jar` không liệt kê `acme-starter.jar!/META-INF/...` không?

**Không.** Metadata của thư viện có thể nằm bên trong JAR dependency. Cần kiểm tra JAR đó riêng.

## 34. Bài tập B: metadata có biến thành mặc định runtime không?

Một JSON metadata chứa:

```json
{
  "properties": [
    {
      "name": "task.batch-size",
      "type": "java.lang.Integer",
      "defaultValue": 100
    }
  ]
}
```

Record:

```java
@ConfigurationProperties(prefix = "task")
public record TaskProperties(int batchSize) {
}
```

Không có `task.batch-size` trong các nguồn cấu hình.

**Câu hỏi:** có thể chắc chắn runtime nhận `batchSize=100` chỉ vì JSON có `defaultValue:100` không?

**Đáp án:** không. Metadata là dữ liệu mô tả, không phải một nguồn default có hiệu lực của binder. Cần khai báo mặc định qua YAML, `@DefaultValue` hoặc cách hỗ trợ khác.

## 35. Bài tập C: metadata có thay validation không?

Metadata mô tả:

```json
{
  "properties": [
    {
      "name": "task.max-attempts",
      "type": "java.lang.Integer",
      "description": "Giá trị phải nằm trong khoảng 1 đến 10."
    }
  ]
}
```

Nhưng record chỉ khai báo:

```java
@ConfigurationProperties(prefix = "task")
public record TaskProperties(int maxAttempts) {
}
```

Với `task.max-attempts=-7`, có chắc ứng dụng báo lỗi chỉ nhờ câu mô tả trong JSON?

**Không.** Giá trị `-7` là số nguyên hợp lệ. Cần validation như `@Min(1) @Max(10)` hoặc kiểm tra constructor để ngăn giá trị sai miền.

## 36. Bài tập D: phân biệt lỗi tên với lỗi giá trị

Record:

```java
@Validated
@ConfigurationProperties(
        prefix = "mail",
        ignoreUnknownFields = false)
public record MailProperties(
        @NotBlank String sender,
        @Min(1) int retryCount) {
}
```

Xét:

**Trường hợp 1:**

```yaml
mail:
  sender: "ops"
  retry-count: many
```

**Trường hợp 2:**

```yaml
mail:
  sender: "ops"
  retry-coutn: 3
```

**Trường hợp 3:**

```yaml
mial:
  sender: "ops"
  retry-count: 3
```

Đáp án:

1. Tên `retry-count` đúng, nhưng `many` không chuyển được thành `int`.
2. `retry-coutn` sai trong prefix `mail`; strict binding có thể phát hiện là khóa chưa được liên kết.
3. Sai prefix `mial`; quy tắc unknown field của bean `mail` không bảo đảm phát hiện một khóa nằm ngoài prefix. Validation các trường bắt buộc có thể phát hiện dữ liệu thiếu.

Nếu bean không được đăng ký hoặc validator không hoạt động, các kiểm tra mong đợi có thể không xảy ra, dù metadata tồn tại.

## 37. Bài tập E: đề xuất một pipeline đầy đủ

Một nhóm phát hành thư viện `acme-gateway-starter` cho nhiều dự án khác. Họ muốn IDE có autocomplete và ứng dụng từ chối timeout không hợp lệ.

Một thiết kế hợp lý gồm:

1. Định nghĩa `@ConfigurationProperties(prefix = "acme.gateway")` với kiểu `Duration`.
2. Khai báo annotation processor để sinh `spring-configuration-metadata.json`.
3. Bổ sung mô tả/hints nếu cần bằng nguồn metadata bổ sung.
4. Đóng gói và xác nhận file metadata có trong JAR phát hành.
5. Đăng ký bean cấu hình theo cơ chế đúng của Spring Boot.
6. Thêm validation hoặc kiểm tra constructor để ngăn timeout không hợp lệ.
7. Viết test binding với giá trị hợp lệ và sai.
8. Tích hợp kiểm tra artifact vào CI.

**Câu hỏi:** bước nào phục vụ chủ yếu IDE, bước nào phục vụ runtime?

**Đáp án:** bước 2–4 phục vụ metadata/tooling và kiểm tra artifact; bước 5–7 phục vụ runtime binding/validation; bước 1 tạo hợp đồng Java làm nền tảng cho cả hai.

## 38. Ghi nhớ

- Configuration metadata của Spring Boot thường nằm trong **`META-INF/spring-configuration-metadata.json`**.
- `spring-boot-configuration-processor` sinh metadata **lúc biên dịch**, từ những cấu hình mà processor phân tích được.
- Trong một **library JAR**, metadata thường nằm ở `META-INF/`; trong **Boot executable JAR**, metadata của ứng dụng thường ở `BOOT-INF/classes/META-INF/`.
- Các dependency JAR trong `BOOT-INF/lib/` có thể có metadata riêng; `jar tf` của outer JAR không tự mở sâu chúng.
- Metadata mô tả `groups`, `properties`, `hints` và các thông tin như tên, kiểu, mô tả, mặc định, deprecation.
- `additional-spring-configuration-metadata.json` là nguồn bổ sung cho quá trình tạo metadata, **không phải** một cách tạo property runtime.
- IDE có thể sử dụng metadata cho autocomplete và cảnh báo, nhưng phạm vi và tính chính xác phụ thuộc công cụ, module, classpath và phiên bản.
- **Có metadata không đồng nghĩa với runtime validation.** `@ConfigurationProperties` binding, chuyển đổi kiểu, `@Validated` và Bean Validation mới quyết định việc chấp nhận dữ liệu trong lần chạy.
- Nội dung `defaultValue` hoặc `description` trong JSON không tự đặt giá trị runtime hay thực thi ràng buộc.
- Kiểm tra artifact metadata và kiểm thử cấu hình lúc chạy là **hai bước độc lập, bổ sung cho nhau**. Dùng cả hai để cải thiện trải nghiệm phát triển và độ tin cậy khi triển khai.

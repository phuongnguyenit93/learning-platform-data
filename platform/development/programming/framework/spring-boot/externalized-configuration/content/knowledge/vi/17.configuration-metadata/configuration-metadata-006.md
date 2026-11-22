# Metadata cho kiểu lồng nhau và `@NestedConfigurationProperty` trong Spring Boot

## 1. Vấn đề bài học giải quyết

Spring Boot hỗ trợ binding cấu hình có cấu trúc từ `application.yaml`, `application.properties`, biến môi trường và dòng lệnh vào các đối tượng Java qua `@ConfigurationProperties`. Một nhóm cấu hình thường có nhiều cấp:

```yaml
portal:
  title: "Metadata Lab"
  http:
    host: "127.0.0.1"
    port: 8088
  mail:
    host: "mail.example.test"
    port: 2525
```

Ứng dụng có thể đọc được cả `portal.http.host` và `portal.mail.host`. Tuy nhiên, nếu `http` dùng một nested record khai báo **bên trong** record cha, còn `mail` dùng một record ở **file Java riêng**, IDE đôi khi gợi ý nhóm `portal.http.*` đầy đủ nhưng lại thiếu `portal.mail.*`. Nguyên nhân có thể nằm ở **configuration metadata được sinh lúc biên dịch**, không phải ở bản thân quá trình binding runtime.

Spring Boot cung cấp bộ xử lý annotation:

```text
org.springframework.boot:spring-boot-configuration-processor
```

để tạo file metadata:

```text
META-INF/spring-configuration-metadata.json
```

Metadata giúp IDE và công cụ phát triển biết tên property, kiểu Java, mô tả, default, deprecation và gợi ý giá trị. Annotation `@NestedConfigurationProperty` giúp processor nhận diện một property có **kiểu con bên ngoài class/record cha** là một nhóm nested cần khám phá, thay vì một scalar value.

Sau bài này, bạn có thể:

1. Phân biệt rõ **cấu hình runtime** với **configuration metadata**.
2. Hiểu cấu trúc `groups`, `properties` và `hints` của JSON metadata.
3. Thiết lập Gradle/Maven để chạy annotation processor.
4. Viết nested record/class được processor tự nhận diện.
5. Dùng `@NestedConfigurationProperty` cho record component hoặc field có type con độc lập.
6. Giải thích vì sao annotation không thay thế `@ConfigurationProperties`, constructor binding hay Bean Validation.
7. Nắm giới hạn metadata với List, Map và những key/index động.
8. Nhận biết tác dụng của annotation với Spring AOT và GraalVM native image.
9. Chạy ví dụ Java 21, Spring Boot 3.3, Gradle và đối chiếu metadata với giá trị Binder tạo ra.
10. Chẩn đoán trường hợp thiếu autocomplete, lỗi binding hoặc lỗi build metadata mà không lẫn chúng với nhau.

**Ngữ cảnh:** Java 21 và Spring Boot 3.3.x. Các host và nhãn trong ví dụ là dữ liệu giả lập. Bài thuộc nhóm **Metadata cấu hình** của chủ đề **Spring Boot Externalized Configuration**.

## 2. Metadata khác dữ liệu runtime như thế nào?

Hãy tưởng tượng trong module có một record:

```java
@ConfigurationProperties(prefix = "portal")
public record PortalProperties(String title) {}
```

Ở môi trường phát triển:

```yaml
portal:
  title: "Development"
```

Ở môi trường production, biến môi trường có thể cấp một giá trị khác. Runtime Binder sử dụng thứ tự ưu tiên của các `PropertySource` để chọn **giá trị hiệu lực**. Metadata thì chỉ mô tả rằng `portal.title` là một khóa cấu hình hỗ trợ kiểu `String`.

| Câu hỏi | Runtime binding | Configuration metadata |
| --- | --- | --- |
| Ứng dụng hiện dùng title nào? | `Environment`, Binder, các nguồn runtime | Không quyết định |
| File dev có ghi đè file nền không? | Có theo profile và precedence | Không quyết định |
| `title` có type gì? | Dựa trên component Java | Có thể mô tả `java.lang.String` |
| IDE có gợi ý `portal.title` không? | Không trực tiếp | Metadata giúp IDE |
| Group `portal.http` có những khóa nào? | Binder có thể bind object con | Processor có thể liệt kê group/properties |
| Có default nghiệp vụ không? | Code/config runtime quyết định | Metadata có thể mô tả một default được phát hiện |
| Khi nào sinh file? | Lấy cấu hình khi ứng dụng khởi động | Sinh lúc compile |
| Có chứa secret thật không? | Phụ thuộc nguồn runtime | Không nên chứa secret; có thể lộ default nếu code dùng secret làm constant |

**Điểm cốt lõi:** file metadata không phải một tệp `application.yaml` khác. Nó không đưa `portal.mail.host` vào `Environment`, không mở server, không đăng ký bean và không xác minh quyền truy cập.

Vì metadata chủ yếu là hợp đồng cho các công cụ, một ứng dụng JVM **có thể bind cấu hình đúng dù thiếu metadata**. Trường hợp build GraalVM native image có ngoại lệ liên quan đến AOT reflection hints sẽ được giải thích riêng ở mục 18.

### 2.1. Metadata tạo ra lợi ích gì cho người dùng thư viện?

Một Spring Boot starter thường có hàng chục cấu hình. Người dùng chỉ cần nhập trong IDE:

```properties
my.starter.
```

là IDE có thể gợi ý những khóa hợp lệ nếu dependency JAR chứa metadata phù hợp. Họ không phải đọc toàn bộ source code của starter để đoán tên field.

Do đó, nếu module của bạn được chia sẻ cho nhiều dự án, metadata đầy đủ là một phần quan trọng của trải nghiệm tích hợp. Nó **bổ sung** cho reference documentation và integration tests chứ không thay thế chúng.

## 3. Định dạng `spring-configuration-metadata.json`

Spring Boot chuẩn hóa ba nhóm thông tin chính:

```json
{
  "groups": [],
  "properties": [],
  "hints": []
}
```

- `groups`: không gian tên/nhóm lồng nhau, ví dụ `portal`, `portal.http`, `portal.mail`.
- `properties`: những property cụ thể có tên đầy đủ, ví dụ `portal.http.port`.
- `hints`: các gợi ý giá trị và provider cho một property, dùng cho công cụ hỗ trợ nhập liệu.

Ví dụ **minh họa rút gọn** (không phải cam kết về mọi thuộc tính tùy chọn mà processor phát ra):

```json
{
  "groups": [
    {
      "name": "portal",
      "type": "dev.example.metadata.PortalProperties"
    },
    {
      "name": "portal.http",
      "type": "dev.example.metadata.PortalProperties$Http"
    },
    {
      "name": "portal.mail",
      "type": "dev.example.metadata.Mail"
    }
  ],
  "properties": [
    {
      "name": "portal.title",
      "type": "java.lang.String"
    },
    {
      "name": "portal.http.host",
      "type": "java.lang.String"
    },
    {
      "name": "portal.http.port",
      "type": "java.lang.Integer"
    },
    {
      "name": "portal.mail.host",
      "type": "java.lang.String"
    },
    {
      "name": "portal.mail.port",
      "type": "java.lang.Integer"
    }
  ],
  "hints": []
}
```

Kết quả thực còn có thể bao gồm `sourceType`, `sourceMethod`, `description`, `defaultValue`, `deprecation` và nhiều trường khác. Thứ tự entries, cách biểu diễn type và các trường tùy chọn phụ thuộc source Java và processor. Khi quan sát metadata, **so sánh các tên property và group cần thiết**, không phụ thuộc vào byte-for-byte JSON mẫu.

### 3.1. Group không nhất thiết là một property scalar

Group:

```text
portal.mail
```

cho biết có nhóm property ở dưới, chẳng hạn:

```text
portal.mail.host
portal.mail.port
```

Nó không mặc nhiên có nghĩa bạn được viết:

```properties
portal.mail=mail.example.test:2525
```

và Binder sẽ tự hiểu chuỗi đó là cả `Mail` object. Muốn một scalar đặc biệt bind vào object phức tạp, cần converter phù hợp. Metadata group và runtime converter là hai cơ chế khác nhau.

### 3.2. `description` và `defaultValue`

Một property metadata có thể chứa:

```json
{
  "name": "portal.http.port",
  "type": "java.lang.Integer",
  "description": "Port of the demonstration HTTP listener."
}
```

`description` giúp IDE giải thích ý nghĩa của property. `defaultValue` chỉ được sinh khi processor nhận diện một default từ code hoặc nguồn metadata thủ công; **chỉ có metadata default không có nghĩa Binder đọc JSON này để cấp default runtime**.

Vì vậy, default thực tế phải được thiết kế ở cấu hình nền, field initializer, constructor binding `@DefaultValue` hoặc cơ chế runtime hợp lệ khác, không phải do metadata tự tạo.

### 3.3. `hints` không phải validation

Ví dụ:

```json
{
  "hints": [
    {
      "name": "portal.mode",
      "values": [
        {"value": "simple"},
        {"value": "advanced"}
      ]
    }
  ]
}
```

Đây là gợi ý cho công cụ. Nó không tự từ chối giá trị `"other"`. Khi runtime chỉ cho phép `simple` hoặc `advanced`, bạn cần enum, validation hoặc converter tương ứng.

## 4. Processor tự nhận diện nested class và nested record

Xét root record có một type `Http` ở bên trong:

```java
package dev.example.metadata;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "portal")
public record PortalProperties(
        String title,
        Http http
) {
    public record Http(String host, int port) {}
}
```

Annotation processor nhận ra `Http` là **nested type** được khai báo trong root và có thể tạo group:

```text
portal.http
```

và các properties:

```text
portal.http.host
portal.http.port
```

Không cần `@NestedConfigurationProperty` cho `http` trong tình huống này.

YAML:

```yaml
portal:
  title: "Metadata Lab"
  http:
    host: "127.0.0.1"
    port: 8088
```

Tương ứng Java:

```java
String bindHost = properties.http().host();
int bindPort = properties.http().port();
```

Trong Java, nested record là một **kiểu Java**; mỗi `Http` là một object với dữ liệu riêng. Nó không tương đương với một **static field** được tiêm giá trị cấu hình. Việc không nên dùng `@Value` trên static field là vấn đề khác.

### 4.1. Class JavaBean lồng nhau

Cơ chế metadata tương tự có thể nhận diện một static nested class:

```java
@ConfigurationProperties(prefix = "legacy")
public class LegacyProperties {

    private Server server = new Server();

    public Server getServer() {
        return server;
    }

    public void setServer(Server server) {
        this.server = server;
    }

    public static class Server {
        private String host;
        private int port;

        public String getHost() { return host; }
        public void setHost(String host) { this.host = host; }

        public int getPort() { return port; }
        public void setPort(int port) { this.port = port; }
    }
}
```

Processor có thể phát hiện `legacy.server.host` và `legacy.server.port`. Còn runtime Binder cần object có cách khởi tạo và accessor phù hợp. **Metadata discovery không tạo setter thay cho JavaBean của bạn.**

Nên dùng `static nested class` hoặc nested record khi có thể, vì non-static inner class cần tham chiếu đến instance bên ngoài và phức tạp hơn cho construction/binding.

## 5. Kiểu con ở bên ngoài root: tình huống cần annotation

Giả sử có một record `Mail` riêng ở file `Mail.java`:

```java
package dev.example.metadata;

public record Mail(
        String host,
        int port
) {}
```

Root dùng:

```java
@ConfigurationProperties(prefix = "portal")
public record PortalProperties(
        String title,
        Mail mail
) {}
```

`Mail` **không nằm bên trong** root `PortalProperties`. Khi sinh metadata, processor không mặc định mở rộng mọi kiểu class ngoài thành nested groups; chúng có thể là những value objects được convert từ scalar. Do đó, processor cần tín hiệu về ý nghĩa của property `mail`.

Dùng:

```java
import org.springframework.boot.context.properties.NestedConfigurationProperty;

@ConfigurationProperties(prefix = "portal")
public record PortalProperties(
        String title,
        @NestedConfigurationProperty Mail mail
) {}
```

Annotation cho processor hiểu:

```text
portal.mail
    |
    +-- portal.mail.host
    +-- portal.mail.port
```

thay vì diễn giải `mail` là một đơn vị giá trị `Mail` không cần khai thác các component.

### 5.1. Vị trí sử dụng hợp lệ trong Spring Boot 3.3

API 3.3 của `@NestedConfigurationProperty` có target:

- `FIELD`.
- `RECORD_COMPONENT`.

Vì vậy:

**Đúng cho record:**

```java
public record PortalProperties(
        @NestedConfigurationProperty Mail mail
) {}
```

**Đúng cho POJO field:**

```java
@NestedConfigurationProperty
private Mail mail;
```

**Không đúng ý định khi đặt trên class `Mail`** như một class-level annotation, vì annotation nói về **property trong root** được đối xử như nhóm nested.

Tài liệu API của một số phiên bản Spring Boot mới có thể bổ sung target khác; khi dùng Boot 3.3, hãy theo đúng annotation target của 3.3.

### 5.2. `@NestedConfigurationProperty` không đăng ký bean

Annotation này không thay:

```java
@ConfigurationProperties(prefix = "portal")
```

và cũng không đăng ký root bean vào context. Root cần được đăng ký bằng một cách hợp lệ, ví dụ:

```java
@ConfigurationPropertiesScan
```

hoặc:

```java
@EnableConfigurationProperties(PortalProperties.class)
```

Đối tượng `Mail` trong ví dụ là **nested value object** được tạo như component của root. Không cần đặt `@Component` lên `Mail` chỉ để nó trở thành nested object.

### 5.3. Annotation có thay đổi binding JVM không?

Javadoc Spring Boot 3.3 nói rõ `@NestedConfigurationProperty` **không tác động trực tiếp đến quy trình binding**. Một `Mail` record bên ngoài root có thể vẫn được JVM Binder tạo đúng từ `portal.mail.host` và `portal.mail.port` nếu Java types và cấu hình hợp lệ.

Vì thế:

- **Thiếu metadata** không chứng minh runtime binding chắc chắn lỗi.
- **Có metadata** không chứng minh bean root đã được tạo thành công.
- **Thêm annotation** không thay cơ chế chọn nguồn, không làm đổi profile, không sinh default runtime và không mở quyền truy cập.

Có một ngoại lệ quan trọng đối với AOT/native image được giải thích ở mục 17. Nó liên quan đến **khám phá cấu trúc để tạo reflection hints**, không phải thay luật binding JVM.

## 6. So sánh các kiểu khai báo

| Kiểu Java | Vai trò cấu hình | Annotation cần cho metadata |
| --- | --- | --- |
| `PortalProperties.Http` nested record | Nhóm `portal.http` | Thường tự suy ra |
| `PortalProperties.Http` static nested POJO | Nhóm `portal.http` | Thường tự suy ra |
| `Mail` record trong file riêng | Nhóm `portal.mail` | Nên thêm trên record component |
| `ExternalMail` POJO ngoài root | Nhóm con thuộc root | Nên thêm trên field |
| `Duration timeout` | Scalar được convert | Không cần nested annotation |
| `URI baseUrl` | Scalar được convert | Không cần nested annotation |
| `List<Mail> providers` | Collection | Annotation không liệt kê từng index |
| `Map<String,Mail> providers` | Map | Annotation không liệt kê từng key động |
| `String code` có custom converter bên ngoài | Scalar | Không biến nó thành group nếu contract là scalar |

Như vậy, quyết định dùng annotation phải dựa trên **ý nghĩa của property**: nó đại diện cho một nhóm nhiều property con hay một giá trị đơn?

## 7. List và Map không tự sinh metadata cho từng phần tử

Một model:

```java
@ConfigurationProperties(prefix = "portal")
public record PortalProperties(
        List<Mail> providers,
        Map<String, Mail> mailboxes
) {}
```

có thể nhận:

```yaml
portal:
  providers:
    - host: "first.example.test"
      port: 2525
    - host: "second.example.test"
      port: 2526
  mailboxes:
    support:
      host: "support.example.test"
      port: 2527
    alerts:
      host: "alerts.example.test"
      port: 2528
```

Runtime có thể diễn giải các khóa như:

```text
portal.providers[0].host
portal.providers[1].port
portal.mailboxes.support.host
portal.mailboxes.alerts.port
```

Nhưng metadata là mô hình tĩnh. Processor thường tạo property đại diện:

```text
portal.providers
portal.mailboxes
```

với generic type, thay vì khai báo mọi index `0`, `1`, `2`, ... hoặc mọi map key có thể tồn tại.

Dạng minh họa:

```json
{
  "name": "portal.providers",
  "type": "java.util.List<dev.example.metadata.Mail>"
}
```

`@NestedConfigurationProperty` **không tác dụng với Collection và Map theo hướng làm chúng sinh thêm index/key metadata**: Spring Boot đã nhận diện những kiểu container này qua type system.

Vì vậy, không thêm annotation vào `List<Mail>` chỉ để kỳ vọng file JSON chứa `portal.providers[0].host`. Các IDE có thể tự khai thác generic type để đưa ra gợi ý phức tạp hơn, nhưng chuyện đó tùy công cụ.

### 7.1. Map key đặc biệt là vấn đề binding khác

Với key map chứa dấu slash, có thể dùng:

```yaml
portal:
  labels:
    "[/health/ready]": "internal"
```

Bracket notation giúp giữ nguyên key đặc biệt khi Binder xử lý property names. Đây là vấn đề về **đường dẫn key tại runtime**, không phải về nested metadata annotation.

## 8. Thiết lập Gradle annotation processor

Bộ xử lý metadata cần xuất hiện trên đường annotation processing khi Java compiler chạy.

`settings.gradle`:

```groovy
rootProject.name = 'nested-metadata-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Điểm quyết định:

```groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
```

`implementation` phù hợp cho code runtime, còn `annotationProcessor` là cấu hình của Java compile để processor được gọi. Đừng chỉ thêm processor vào một dependency không tham gia annotation-processing path rồi mong file metadata xuất hiện.

Dùng Gradle Wrapper của project (`gradlew`, `gradlew.bat`) được tạo từ Spring Initializr. Nếu repository dùng version catalog hoặc convention plugins, hãy giữ cách quản lý dependency của repository.

### 8.1. Maven tương ứng

Trong dự án Maven dùng Spring Boot dependency management, có thể khai báo:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

Tùy cấu hình `maven-compiler-plugin` và JDK, annotation processor paths có thể được khai báo riêng. Điều quan trọng là processor **thực sự chạy ở module chứa source `@ConfigurationProperties`**, chứ không chỉ xuất hiện ở một dependency của một module khác.

## 9. Project lab đầy đủ

Cấu trúc:

```text
nested-metadata-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/metadata/
    │   │   ├── MetadataApplication.java
    │   │   ├── PortalProperties.java
    │   │   └── Mail.java
    │   └── resources/
    │       └── application.yaml
    └── test/
        └── java/dev/example/metadata/
            ├── PortalPropertiesTest.java
            └── GeneratedMetadataTest.java
```

Ứng dụng chạy console, không cần database, HTTP server hoặc Kubernetes. Nó quan sát một root record, một nested record tự nhận diện và một external record dùng annotation.

### 9.1. `PortalProperties.java`

```java
package dev.example.metadata;

import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.NestedConfigurationProperty;

/**
 * Configuration for a small portal application.
 *
 * @param title public display title
 * @param http HTTP listener options
 * @param mail mail delivery options
 * @param regions configured region codes
 * @param labels non-sensitive labels
 */
@ConfigurationProperties(prefix = "portal")
public record PortalProperties(
        String title,
        Http http,
        @NestedConfigurationProperty Mail mail,
        List<String> regions,
        Map<String, String> labels
) {
    /**
     * HTTP options belonging to the portal configuration.
     *
     * @param host demonstration bind address
     * @param port demonstration listener port
     */
    public record Http(
            String host,
            int port
    ) {}
}
```

Trong code thực, các dòng `*/` khi hiển thị README được thay bằng cú pháp kết thúc Javadoc hợp lệ.

**Giải thích:**

- Root gắn `@ConfigurationProperties(prefix="portal")`.
- `Http` nằm trong root nên processor tự khám phá nhóm `portal.http`.
- `Mail` ở file riêng nên component `mail` có `@NestedConfigurationProperty`.
- `regions` và `labels` là collection/map; không có annotation nested.
- Root record có các component Java camelCase nếu tên gồm nhiều từ; YAML dùng tên canonical kebab-case.
- Với Java record, Javadoc ở khai báo record dùng `@param` giúp processor trích xuất description của từng component.

### 9.2. `Mail.java`

```java
package dev.example.metadata;

/**
 * Mail settings for the training application.
 *
 * @param host host of the test mail service
 * @param port port of the test mail service
 */
public record Mail(
        String host,
        int port
) {}
```

Record `Mail` không cần là một Spring bean riêng. Khi Binder tạo `PortalProperties`, nó có thể tạo một instance `Mail` làm component bên trong root.

Nếu `Mail` nằm ở một dependency đã compile thay vì source đang được xử lý, annotation processor có thể không có đầy đủ Javadoc/source metadata của nó. Khi cần mô tả bổ sung, cân nhắc metadata thủ công.

### 9.3. `MetadataApplication.java`

```java
package dev.example.metadata;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class MetadataApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataApplication.class, args);
    }

    @Bean
    ApplicationRunner report(PortalProperties settings) {
        return args -> {
            System.out.println("=== NESTED METADATA LAB ===");
            System.out.println("title = " + settings.title());
            System.out.println("http.host = "
                    + settings.http().host());
            System.out.println("http.port = "
                    + settings.http().port());
            System.out.println("mail.host = "
                    + settings.mail().host());
            System.out.println("mail.port = "
                    + settings.mail().port());
            System.out.println("regions = " + settings.regions());
            System.out.println("labels = " + settings.labels());
        };
    }
}
```

`@ConfigurationPropertiesScan` đăng ký root record để Binder tạo bean cấu hình. Nó **khác** với `spring-boot-configuration-processor`: scan hoạt động với Spring application runtime; processor chạy khi compile và sinh JSON.

Đừng dùng một metadata file như bằng chứng rằng Bean đã được đăng ký; và đừng dùng việc Bean được inject thành công như bằng chứng rằng IDE đã nhận được metadata JSON.

### 9.4. `application.yaml`

```yaml
spring:
  main:
    web-application-type: none

portal:
  title: "Metadata Lab"
  http:
    host: "127.0.0.1"
    port: 8088
  mail:
    host: "mail.example.test"
    port: 2525
  regions:
    - ap-southeast-1
    - eu-west-1
  labels:
    team: education
    stage: sandbox
```

Những đường property có ý nghĩa:

```text
portal.title
portal.http.host
portal.http.port
portal.mail.host
portal.mail.port
portal.regions
portal.labels
```

Các giá trị đều chỉ dùng cho bài học, không tạo kết nối thực đến `mail.example.test`. Bài mẫu không nên đưa secret hoặc credential vào metadata, log hoặc repository.

## 10. Chạy thử runtime binding

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Những dòng đáng quan sát:

```text
=== NESTED METADATA LAB ===
title = Metadata Lab
http.host = 127.0.0.1
http.port = 8088
mail.host = mail.example.test
mail.port = 2525
regions = [ap-southeast-1, eu-west-1]
labels = {team=education, stage=sandbox}
```

Thứ tự in các phần tử `Map` có thể khác nhau; điều quan trọng là nội dung mỗi key.

Chạy lại với đối số:

```bash
./gradlew bootRun --args='--portal.mail.host=smtp.example.test --portal.mail.port=3025'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--portal.mail.host=smtp.example.test --portal.mail.port=3025"
```

Kỳ vọng:

```text
mail.host = smtp.example.test
mail.port = 3025
```

CLI có thể ghi đè YAML cho hai khóa đó trong trường hợp thông thường. Metadata không thay đổi khi bạn chạy với một giá trị CLI khác, bởi metadata mô tả **schema**, không phải snapshot giá trị.

## 11. Build và kiểm tra metadata JSON

Biên dịch lại bằng Gradle:

macOS/Linux:

```bash
./gradlew clean compileJava
```

Windows:

```powershell
.\gradlew.bat clean compileJava
```

Trong project Java/Gradle thông thường, annotation processor ghi file tại:

```text
build/classes/java/main/META-INF/spring-configuration-metadata.json
```

Nếu Gradle được tùy biến class output directory, vị trí có thể khác. Trong Maven, vị trí thường là:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

Đọc file:

Bash:

```bash
cat build/classes/java/main/META-INF/spring-configuration-metadata.json
```

PowerShell:

```powershell
Get-Content 'build/classes/java/main/META-INF/spring-configuration-metadata.json' -Raw
```

Tìm tên group/property:

```text
portal
portal.http
portal.mail
portal.title
portal.http.host
portal.http.port
portal.mail.host
portal.mail.port
portal.regions
portal.labels
```

Một số tên là group; một số là property. `portal.regions` và `portal.labels` thường có metadata type collection/map chứ không chứa từng key/index runtime.

Tìm nhanh bằng Bash:

```bash
grep -n '"name"' \
  build/classes/java/main/META-INF/spring-configuration-metadata.json
```

Hoặc PowerShell:

```powershell
Select-String -Path 'build/classes/java/main/META-INF/spring-configuration-metadata.json' `
  -Pattern 'portal.http|portal.mail|portal.regions|portal.labels'
```

**Không so sánh JSON đầy đủ bằng một chuỗi literal** nếu không có lý do: processor có thể bổ sung `sourceType`, `description` hoặc sắp xếp entries khác nhau. Tập trung vào schema quan trọng.

### 11.1. File metadata trong executable JAR

Sau:

```bash
./gradlew bootJar
```

metadata thuộc ứng dụng thường nằm trong executable JAR dưới:

```text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

Metadata của một dependency JAR thông thường nằm ở:

```text
META-INF/spring-configuration-metadata.json
```

Vị trí trong archive khác nhau vì cấu trúc executable JAR của Spring Boot. IDE thường sử dụng metadata trong artifact/dependencies khi biết classpath dự án. Nếu metadata không có trong JAR, kiểm tra build và packaging, không chỉ kiểm tra code Java.

## 12. Thí nghiệm A: nested record được suy ra tự động

Trong `PortalProperties`:

```java
Http http
```

không có annotation nested, nhưng vì `Http` được khai báo **trong** root, processor có thể sinh `portal.http` cùng `portal.http.host`/`portal.http.port`.

Điều cần quan sát là **metadata JSON** sau compile. Việc runner in `http.host` đúng là bằng chứng runtime binding thành công, nhưng nó không trực tiếp kiểm tra những entries của metadata.

Nếu refactor `Http` từ nested record thành `HttpSettings.java` nằm file riêng, bạn nên xem lại annotation ở component `http`. Đây là một tình huống phổ biến khiến gợi ý IDE biến mất sau khi tách code, dù Java application vẫn có thể chạy.

## 13. Thí nghiệm B: external record và annotation

Trong root:

```java
@NestedConfigurationProperty Mail mail
```

annotation cho processor tín hiệu rõ về nhóm `portal.mail`.

Trên **một bản thử nghiệm**, có thể tạm bỏ annotation rồi chạy:

```bash
./gradlew clean compileJava
```

Quan sát metadata. Theo quy tắc discovery, type bên ngoài root có thể không được thu thập như nested group khi thiếu annotation.

Sau đó chạy JVM bằng:

```bash
./gradlew bootRun
```

Nếu runtime vẫn bind `Mail` được, kết quả ấy không mâu thuẫn: annotation không thay đổi thuật toán binding JVM thông thường.

Khôi phục annotation để metadata có cấu trúc rõ và để AOT/native image có đủ thông tin khám phá. Không sửa trực tiếp `build/classes/.../spring-configuration-metadata.json` bằng tay; nó là file sinh ra và có thể bị overwrite ở lần compile kế tiếp.

## 14. Thí nghiệm C: List, Map và metadata hữu hạn

Với:

```java
List<String> regions,
Map<String, String> labels
```

processor có thể sinh:

```text
portal.regions
portal.labels
```

nhưng không cần sinh sẵn:

```text
portal.regions[0]
portal.regions[1]
portal.labels.team
portal.labels.stage
```

Các key/index như vậy có thể tồn tại ở runtime, nhưng tập giá trị khả dĩ là động. Annotation nested không ép processor liệt kê vô hạn index hoặc map key.

Vì vậy, nếu IDE không gợi ý cụ thể `portal.regions[2]`, đừng vội kết luận type collection không được bind hoặc thiếu annotation. Kiểm tra metadata type của `portal.regions` và thử runtime bằng một `List<String>` bean có kiểu.

## 15. Javadoc để có `description`

Đối với JavaBean field, Javadoc ở field có thể được dùng để sinh `description`. Với **Java record**, Spring Boot hướng dẫn mô tả record components bằng `@param` trong Javadoc khai báo record, vì record không có các field tường minh như JavaBean thông thường.

Ví dụ:

```java
/**
 * Outgoing mail configuration.
 *
 * @param host DNS host name of the outbound mail service
 * @param port TCP port for the outbound mail service
 */
public record Mail(String host, int port) {}
```

Description tốt nên:

- Nói rõ property dùng cho mục đích gì.
- Nêu đơn vị khi đó là size, duration hoặc port.
- Diễn đạt ngắn gọn, có ngữ nghĩa.
- Không chứa token, password hoặc giá trị bí mật thật.
- Không chỉ nhắc lại tên biến bằng các từ tương tự.
- Phân biệt rõ một cấu hình dùng cho demo với cấu hình production.

Nếu record nằm ở một dependency đã compile, annotation processor của module tiêu thụ có thể không nhìn thấy Javadoc source. Với một property cần mô tả công khai, cân nhắc thêm metadata bổ sung thay vì sửa trực tiếp artifact sinh ra.

### 15.1. Vì sao description không tự có?

Một trường tên `timeout` không cho biết đó là thời gian kết nối, thời gian đọc hay tổng thời gian chờ. Processor không thể suy ra hợp đồng nghiệp vụ từ tên property. Javadoc cung cấp thông tin mà tên/tipo Java không có.

Nhưng description vẫn không phải validation: nếu timeout phải dương, cần constraint hoặc quy tắc runtime khác.

## 16. Manual metadata và hints

Khi processor không thể tự lấy description/default hoặc khi cần gợi ý giá trị cho IDE, Spring Boot hỗ trợ file:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Ví dụ:

```json
{
  "properties": [
    {
      "name": "portal.mail.host",
      "description": "Host name for the outbound mail service."
    }
  ],
  "hints": [
    {
      "name": "portal.mode",
      "values": [
        {
          "value": "simple",
          "description": "Use the minimal configuration."
        },
        {
          "value": "advanced",
          "description": "Enable advanced configuration options."
        }
      ]
    }
  ]
}
```

Những mô tả/hints này giúp IDE khi tác giả nhập cấu hình. `portal.mode` là một key minh họa cho một option có thể được khai báo riêng trong ứng dụng; **hint không tự tạo runtime property hoặc validation**.

Nếu một thuộc tính đã được processor phát hiện, một số thông tin bổ sung có thể override description, default hoặc deprecation của metadata sinh tự động. Nếu property chưa tồn tại trong source type, metadata thủ công có thể bổ sung entry để mô tả một key được xử lý bằng cơ chế khác.

### 16.1. Gradle: quan hệ `compileJava` và `processResources`

Nếu bạn dùng additional metadata JSON, cần đảm bảo file resource có mặt khi annotation processor chạy. Theo hướng dẫn Spring Boot, có thể thêm:

```groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
```

Đối với lab **không có additional file**, phần này không bắt buộc. Không nên thêm task phụ tùy tiện nếu build hiện có đã xử lý resources và annotation processing đúng cách.

Sau khi thêm file thủ công, chạy lại:

```bash
./gradlew clean compileJava
```

và đọc metadata được sinh để xem nội dung đã được kết hợp.

### 16.2. Default trong metadata không tạo default runtime

Giả sử bạn thêm:

```json
{
  "properties": [
    {
      "name": "portal.mail.port",
      "defaultValue": 2525
    }
  ]
}
```

Thông tin này mô tả default cho IDE, nhưng Binder **không đọc JSON metadata làm nguồn property runtime**. Nếu muốn `Mail.port` có default 2525, cần thiết kế ở file cấu hình nền, constructor default theo cơ chế Spring Boot hoặc một cách binding runtime rõ ràng.

Không dùng metadata như nơi lưu secret hoặc endpoint production bắt buộc phải ẩn.

## 17. Spring AOT và GraalVM native image

Đây là điểm cần trình bày chính xác khi nói annotation không làm thay đổi binding:

- Trên JVM thông thường, `@NestedConfigurationProperty` không điều khiển trực tiếp Binder.
- Spring Boot AOT phân tích các type cấu hình để sinh reflection hints cho native image.
- Khi kiểu nested **không phải inner/nested class**, Spring Boot 3.3 hướng dẫn dùng `@NestedConfigurationProperty` để giúp AOT phát hiện type con.
- Thiếu annotation trong trường hợp này có thể khiến nested property không bind được trong native image, dù một JVM test chạy thành công.

Ví dụ:

```java
@ConfigurationProperties(prefix = "portal")
public record PortalProperties(
        String title,
        @NestedConfigurationProperty Mail mail
) {}
```

Annotation được đặt trên **record component**. Với POJO constructor-bound, đặt trên field thích hợp theo API Spring Boot 3.3. Khi build native image, cần kiểm tra những reflection hints được sinh và chạy đường startup/native test thực tế.

**Không nên nói** annotation “chỉ phục vụ IDE trong mọi hình thức build”. Nó là một tín hiệu về cấu trúc, và đường AOT có thể phụ thuộc vào tín hiệu đó.

Mặt khác, annotation không thay các runtime hints dành cho loại reflection tùy ý của thư viện khác. Nó phục vụ configuration properties nested discovery, không phải cơ chế cấp quyền reflection tổng quát.

## 18. Integration test cho runtime binding

Tạo `src/test/java/dev/example/metadata/PortalPropertiesTest.java`:

```java
package dev.example.metadata;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "portal.title=From Test",
        "portal.http.port=9088",
        "portal.mail.host=mail.test.example",
        "portal.mail.port=3025"
})
class PortalPropertiesTest {

    @Autowired
    PortalProperties properties;

    @Test
    void bindsNestedObjects() {
        assertEquals("From Test", properties.title());

        assertNotNull(properties.http());
        assertEquals("127.0.0.1", properties.http().host());
        assertEquals(9088, properties.http().port());

        assertNotNull(properties.mail());
        assertEquals("mail.test.example",
                properties.mail().host());
        assertEquals(3025, properties.mail().port());

        assertEquals("education",
                properties.labels().get("team"));
    }
}
```

Chạy:

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

Test cho thấy Binder đã chọn giá trị có hiệu lực từ test properties và YAML rồi tạo `PortalProperties`. Nó **không chứng minh** JSON metadata chứa các nhóm cần thiết; phải có một kiểm tra riêng.

### 18.1. Test file metadata

Tạo `src/test/java/dev/example/metadata/GeneratedMetadataTest.java`:

```java
package dev.example.metadata;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

class GeneratedMetadataTest {

    @Test
    void containsExpectedNestedNames() throws Exception {
        try (InputStream stream = getClass().getClassLoader()
                .getResourceAsStream(
                        "META-INF/spring-configuration-metadata.json")) {
            assertNotNull(stream,
                    "Configuration metadata resource is missing");

            String json = new String(
                    stream.readAllBytes(), StandardCharsets.UTF_8);

            assertTrue(json.contains("portal.http.host"));
            assertTrue(json.contains("portal.http.port"));
            assertTrue(json.contains("portal.mail.host"));
            assertTrue(json.contains("portal.mail.port"));
        }
    }
}
```

Test này chỉ kiểm tra sự hiện diện của tên, không assert chính xác `groups` và `properties` arrays. Muốn kiểm tra schema chi tiết, cần parse JSON thành object và assert theo array tương ứng.

Nếu dự án có nhiều dependency cùng cung cấp resource tên `spring-configuration-metadata.json`, việc tải resource qua classloader có thể chọn nhầm artifact. Khi đó, viết kiểm tra vào **file output cụ thể của module** thay vì dựa trên resource name duy nhất.

## 19. Phân loại lỗi thường gặp

### 19.1. IDE không gợi ý external nested type

**Hiện tượng:** `portal.http.host` được gợi ý nhưng `portal.mail.host` không.

**Khả năng:** Processor tự nhận nested `Http`, còn external `Mail` thiếu `@NestedConfigurationProperty`, hoặc metadata processor chưa chạy đúng.

**Cách xử lý:** đặt annotation lên component `mail`, kiểm tra `annotationProcessor` trong Gradle, compile lại, xem JSON và reload project trong IDE nếu cần.

### 19.2. Không có file metadata

**Hiện tượng:** `compileJava` thành công nhưng không thấy `spring-configuration-metadata.json`.

**Khả năng:** Processor chưa được khai báo trên annotation-processing path, annotation processing bị tắt, hoặc bạn đang xem sai module/output directory.

**Cách xử lý:** kiểm tra dependency `annotationProcessor`, chạy `./gradlew clean compileJava`, rồi đọc đúng class output của module. IDE vẫn có thể gợi ý property Spring Boot có sẵn từ dependency khác; đó không phải bằng chứng metadata của module này tồn tại.

### 19.3. Có metadata nhưng bean không bind

**Hiện tượng:** IDE biết `portal.mail.host` nhưng bean `PortalProperties` không tồn tại hoặc giá trị null.

**Khả năng:** Chưa đăng ký root, YAML không được nạp, prefix sai, profile chưa bật, property source ưu tiên khác đang tác động, kiểu không convert được hoặc thiếu constructor/accessor.

**Cách xử lý:** kiểm tra `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`, thông báo lỗi Binder và runtime sources. Không trông chờ `@NestedConfigurationProperty` tự sửa những vấn đề đó.

### 19.4. JVM chạy được, native image lỗi

**Hiện tượng:** JVM integration test xanh nhưng native executable không bind một kiểu con ngoài root.

**Khả năng:** AOT không nhận diện nested type và thiếu reflection hints.

**Cách xử lý:** đặt annotation tại field/record component, rebuild native/AOT, kiểm tra type cấu hình và đường native startup. Không quy lỗi cho YAML khi type đã bind thành công trên JVM.

### 19.5. Dùng annotation lên `List` nhưng JSON thiếu index

Đây không phải lỗi: collection/map được mô tả theo type. Các index và key thực tế do người vận hành cung cấp không phải một tập hữu hạn để processor phát hành sẵn.

### 19.6. Default trong JSON không có tác dụng

Metadata mô tả, không cấp runtime value. Cần default trong config/binding thực hoặc một cơ chế explicit.

### 19.7. Thiếu description của record component

Với record, kiểm tra `@param` Javadoc. Với type ở dependency đã compile, processor có thể không nhìn thấy source. Nếu cần, thêm `additional-spring-configuration-metadata.json`.

### 19.8. File bổ sung không được merge

Kiểm tra đường dẫn resource, JSON hợp lệ, quan hệ compile/resources và module chứa file. Không sửa metadata sinh ra trong `build/classes` bằng tay, vì sẽ bị tạo lại.

### 19.9. Tên property có dấu chấm sai cấp

`portal.mail-host` và `portal.mail.host` mô tả hai cấu trúc khác nhau. Dấu chấm chia namespace; dấu gạch nối phân tách từ trong một phần tên. Đặt tên canonical thống nhất trong YAML, Java model và metadata.

### 19.10. Metadata trùng một tên

Định dạng có thể xuất hiện những entries trùng tên khi nhiều nguồn type công bố cùng prefix. Cần xem type/source context thay vì chỉ đếm số dòng `"name"`. Tuy nhiên, trong một thư viện dùng lại, nên giữ ownership prefix rõ ràng để người dùng không nhận gợi ý xung đột.

## 20. Bảng quyết định nhanh

| Tình huống | Thiết kế phù hợp | Cần kiểm tra gì? |
| --- | --- | --- |
| Nested record nằm trong root | Giữ nested record | JSON có group con |
| POJO static nested class | Getter/setter và type nested rõ ràng | Metadata và runtime |
| Record external được dùng như object con | `@NestedConfigurationProperty` trên component | JSON group + AOT |
| External POJO field | Annotation trên field | JSON + Binder |
| Collection | `List<T>`/`Map<K,V>` đúng kiểu | Metadata collection và binding |
| Scalar `Duration` | Conversion chuẩn | Không gắn nested |
| Scalar `URI` | Conversion chuẩn | Không gắn nested |
| Config object trong một dependency | Metadata của module sở hữu hoặc bổ sung | JAR có JSON |
| Manual description/hint | Additional JSON | Merge vào output |
| Native image | Annotation + AOT hints + native test | Không chỉ test JVM |

Dùng bảng này để lựa chọn **đúng mức annotation** thay vì đánh dấu mọi field có type phức tạp.

## 21. Checklist triển khai cấu hình lồng nhau

1. Đặt prefix rõ ràng, ví dụ `portal`.
2. Liệt kê schema mong đợi: `portal.http.host`, `portal.mail.port`.
3. Chọn type nested record/class cho nhóm có các key cố định.
4. Với type được khai báo trong root, tận dụng khả năng auto-discovery.
5. Với type bên ngoài root, đánh dấu `@NestedConfigurationProperty` ở nơi tham chiếu.
6. Không dùng annotation nested để giải quyết vấn đề map/list indexing.
7. Đăng ký root configuration properties đúng cách.
8. Thêm configuration processor vào annotation-processing path.
9. Cung cấp Javadoc có ích, `@param` cho record components.
10. Biên dịch lại và xem file metadata JSON ở đúng module.
11. Kiểm tra `groups` và `properties` riêng, tránh nhầm namespace với scalar.
12. Chạy runtime test để xác nhận object graph được bind.
13. Kiểm tra precedence nếu giá trị runtime khác mong đợi.
14. Với project thư viện/starter, xác nhận metadata đã đóng gói trong JAR.
15. Với GraalVM native build, kiểm tra AOT discovery và native executable.
16. Không ghi secret vào default, hints hoặc Javadoc.
17. Không dùng metadata như runtime validation.
18. Khi refactor schema, giữ test để phát hiện mất autocomplete hoặc đổi tên key.

## 22. Bài tập tự luyện

### Bài A — Tạo nhóm tự động

Cho:

```java
@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
        String title,
        Export export
) {
    public record Export(String format, String directory) {}
}
```

Hãy dự đoán `groups` và `properties` nào processor có thể tạo. Vì sao không cần annotation nested trên `export`?

### Bài B — Tách type ra file ngoài

Nếu chuyển `Export` thành `ExportSettings.java`, hãy sửa declaration root để metadata còn mô tả các khóa:

```text
reports.export.format
reports.export.directory
```

Nên đặt annotation tại type `ExportSettings` hay tại component đang dùng type đó?

### Bài C — Javadoc cho record

Viết Javadoc `@param` cho `ExportSettings(format, directory)` để mô tả các kiểu giá trị dự kiến. Vì sao chỉ viết Javadoc ở class tổng quát có thể không đủ để công cụ hiểu mỗi property?

### Bài D — List of objects

Cho:

```java
List<Endpoint> endpoints
```

Hãy dự đoán JSON có thể chứa key `gateway.endpoints` nhưng không cần chứa những `gateway.endpoints[0].host`, `[1].host`. Giải thích vì sao metadata là mô hình tĩnh hữu hạn.

### Bài E — Test hai trách nhiệm

Viết một integration test cho Binder nhận `portal.mail.port=3025`, rồi một test đọc metadata chứa `portal.mail.port`. Vì sao kết quả một test không suy ra kết quả test còn lại?

### Bài F — Native image

Một record ngoài root bind thành công ở JVM nhưng thiếu giá trị khi chạy native image. Liệt kê những điểm cần kiểm tra: annotation placement, AOT generated hints, kiểu Java, artifact, source property và integration test.

### Bài G — Additional hints

Tạo `additional-spring-configuration-metadata.json` cung cấp gợi ý `portal.mode=simple|advanced`. Test rằng file metadata cuối có hints. Giải thích vì sao runtime vẫn phải validate giá trị `portal.mode` nếu đây là ràng buộc bắt buộc.

### Bài H — Refactor nhưng không đổi schema

Có `PortalProperties.Http` nested record, bạn muốn tách thành `HttpSettings` độc lập để nhiều module dùng chung. Thiết kế root mới sao cho key `portal.http.host` giữ nguyên. Bạn cần kiểm tra thêm điều gì ngoài việc ứng dụng khởi động được?

## 23. Câu hỏi tự kiểm tra

**1.** Metadata được tạo lúc nào, bởi công cụ nào?

**2.** Metadata có phải một PropertySource mà Binder đọc giá trị runtime không?

**3.** Ba mảng chính của file JSON metadata là gì?

**4.** Một nested record bên trong root thường có cần `@NestedConfigurationProperty` không?

**5.** Một record ở file riêng được dùng như nhóm con cần ghi annotation ở đâu?

**6.** Target của annotation trong Boot 3.3 là gì?

**7.** Vì sao JVM có thể bind được dù chưa thêm annotation?

**8.** Khi build native image, thiếu annotation có thể ảnh hưởng gì?

**9.** `List<Mail>` có được annotation mở rộng thành metadata từng `[0]`, `[1]` không?

**10.** Có thể dùng metadata thay `@ConfigurationPropertiesScan` không?

**11.** Thêm processor vào `implementation` đã luôn đủ để Gradle chạy nó chưa?

**12.** Sau `compileJava`, cần kiểm tra file nào?

**13.** Với record, dùng gì để tạo description cho component?

**14.** `additional-spring-configuration-metadata.json` được dùng khi nào?

**15.** Default value trong metadata có làm Binder tự cấp default runtime không?

**16.** IDE thiếu gợi ý có đồng nghĩa runtime binding chắc chắn lỗi không?

**17.** Một type `Duration` có cần đánh dấu nested không?

**18.** Tại sao phải có cả runtime test và metadata test khi refactor?

### Gợi ý đáp án

1. Khi biên dịch, bằng Spring Boot configuration annotation processor.
2. Không.
3. `groups`, `properties`, `hints`.
4. Thường không, vì processor tự nhận nested type.
5. Ở field hoặc record component tham chiếu type đó.
6. `FIELD` và `RECORD_COMPONENT` trong 3.3.
7. Vì annotation không thay thuật toán binding JVM thông thường.
8. AOT có thể thiếu reflection hints cho external nested type.
9. Không, collections/maps được mô tả riêng.
10. Không, metadata không đăng ký bean.
11. Không; dùng `annotationProcessor` đúng với Gradle Java plugin.
12. `META-INF/spring-configuration-metadata.json` trong class output module.
13. Javadoc `@param` trên record declaration.
14. Bổ sung description/default/hints khi tự động phát hiện không đủ.
15. Không.
16. Không, phải kiểm tra cả runtime.
17. Không, `Duration` là scalar có conversion chuẩn.
18. Chúng xác minh hai trách nhiệm độc lập.

## 24. Áp dụng vào dự án thật

Tư duy kiến trúc của bài:

```text
MÔ TẢ SCHEMA CHO IDE

Java types + @ConfigurationProperties
              |
              +-- nested type trong root
              |       -> tự nhận diện
              |
              +-- external nested type
              |       -> @NestedConfigurationProperty
              |
              +-- List / Map
              |       -> mô tả collection
              |
              v
 spring-boot-configuration-processor
              |
              v
 META-INF/spring-configuration-metadata.json
              |
              v
       IDE / metadata tooling
```

Đường runtime là:

```text
application.yaml / environment / CLI
                 |
                 v
             Environment
                 |
                 v
     @ConfigurationProperties Binder
                 |
                 v
         PortalProperties
                 |
        +--------+--------+
        |                 |
      Http               Mail
        |                 |
        +--------+--------+
                 |
                 v
          ApplicationRunner
```

Hai đường có chung Java schema nhưng giải quyết hai vấn đề khác nhau. Khi thiếu gợi ý IDE, xem processor, annotation placement và metadata JSON. Khi bean nhận giá trị sai, xem prefix, property sources, conversion, profile và validation. Khi native image lỗi, bổ sung kiểm tra AOT reflection hints.

**Kết luận:** `@NestedConfigurationProperty` là tín hiệu cho một property có **external nested type**, giúp Spring Boot nhận diện nhóm trong metadata và hỗ trợ AOT. Dùng annotation ở đúng field/record component, không nhầm với bean registration hoặc runtime default, và luôn tách kiểm tra metadata khỏi kiểm tra binding.

### Tài liệu tham khảo

- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html).
- [Spring Boot 3.3 — Metadata Format](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html).
- [Spring Boot 3.3 — Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html).
- [Spring Boot 3.3 — `@NestedConfigurationProperty` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/NestedConfigurationProperty.html).
- [Spring Boot 3.3 — Advanced Native Image Topics](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html).
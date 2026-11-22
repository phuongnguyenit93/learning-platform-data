# Sinh metadata bằng spring-boot-configuration-processor

Trong dự án Spring Boot có nhiều lớp `@ConfigurationProperties`, người phát triển cần biết những khóa cấu hình nào được hỗ trợ, kiểu dữ liệu của từng khóa là gì, mô tả ra sao và có những giá trị gợi ý nào. Nếu phải đọc từng class Java mới biết `app.mail.connect-timeout` hoặc `app.storage.max-size`, trải nghiệm viết `application.yml` sẽ khó khăn và dễ sai tên.

Thư viện **`spring-boot-configuration-processor`** giải quyết vấn đề này bằng cách chạy **annotation processing ở thời điểm biên dịch** và tạo ra tệp JSON metadata có đường dẫn:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Các công cụ hỗ trợ Spring Boot trong IDE có thể đọc metadata để cung cấp **gợi ý tên khóa, kiểu dữ liệu, mô tả, giá trị mặc định và một số lựa chọn hợp lệ** khi chỉnh sửa file cấu hình.

Điều quan trọng nhất: **metadata không phải cơ chế nạp hoặc bind cấu hình lúc chạy**. Bean `@ConfigurationProperties` vẫn được Spring Boot Binder xử lý thông qua `Environment`. Configuration processor chỉ hỗ trợ công cụ phát triển và mô tả cấu hình tốt hơn.

Bài học dùng Spring Boot 3.3.x và Java 21; hướng dẫn từ khai báo dependency, tạo lớp cấu hình, biên dịch, đọc JSON sinh ra, bổ sung metadata tùy chỉnh, khắc phục lỗi và kiểm thử.

## 1. Phân biệt configuration metadata và cấu hình ứng dụng

Có ba khái niệm dễ nhầm:

| Thành phần | Mục đích | Thời điểm |
| --- | --- | --- |
| `application.yml` hoặc `application.properties` | Cung cấp giá trị thuộc tính thực tế | Khi ứng dụng nạp cấu hình |
| `@ConfigurationProperties` | Khai báo object Java để bind thuộc tính theo prefix | Khi Spring Boot tạo bean cấu hình |
| `spring-boot-configuration-processor` | Phân tích khai báo cấu hình và sinh tệp mô tả JSON | Lúc biên dịch Java |
| `spring-configuration-metadata.json` | Chứa thông tin hỗ trợ IDE/documentation | Được IDE/build tool đọc |
| `additional-spring-configuration-metadata.json` | Bổ sung thông tin mà processor không thể tự suy ra | Được kết hợp trong quá trình sinh metadata |

Ví dụ, lớp Java khai báo:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String host, int port) {
}
~~~

File `application.yml` cung cấp:

~~~yaml
app:
  mail:
    host: mail.example.org
    port: 2525
~~~

Configuration processor có thể sinh các tên property dạng `app.mail.host` và `app.mail.port`. Khi IDE nhận metadata, nó có thể gợi ý các tên đó.

Nhưng metadata **không chứa các giá trị triển khai bí mật** như mật khẩu SMTP hoặc token production; và không được xem là một hệ thống quản lý secret. Giá trị hiệu lực lúc chạy vẫn đến từ các PropertySource.

## 2. Vì sao nên dùng configuration processor?

Các lợi ích phổ biến:

- **Autocomplete:** IDE gợi ý `app.mail.host` hoặc `app.mail.connect-timeout` khi viết `application.yml`.
- **Phát hiện lỗi đánh máy sớm:** người đọc có thể nhận ra `app.mail.conect-timeout` không nằm trong danh sách được mô tả.
- **Hiển thị kiểu:** IDE biết một property là `java.time.Duration`, `java.lang.String`, enum hay collection.
- **Mô tả tại chỗ:** Javadoc hoặc metadata thủ công giúp người dùng hiểu ý nghĩa của khóa.
- **Khả năng khám phá:** người vận hành và nhóm phát triển có thể liệt kê các thuộc tính do module cung cấp.
- **Hỗ trợ thư viện chung:** nếu một library Spring Boot cung cấp nhiều cấu hình tùy biến, đóng gói metadata giúp dự án sử dụng library có gợi ý IDE tốt hơn.

Đây là **lợi ích về trải nghiệm phát triển**. Không nên cho rằng processor làm ứng dụng chạy nhanh hơn, tự sửa cấu hình sai hoặc bảo đảm mọi thuộc tính được xác thực.

## 3. Thêm dependency với Maven

Nếu dự án sử dụng Maven và Spring Boot dependency management, thêm vào `pom.xml`:

~~~xml
<dependencies>
    <!-- Những dependency thông thường của ứng dụng... -->

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-configuration-processor</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

`optional>true</optional>` thường được dùng để không yêu cầu các dự án khác kéo theo processor như một dependency runtime/transitive thông thường. Đây là công cụ build, không phải một thành phần mà business service cần inject ở runtime.

Khi dùng Spring Boot parent/BOM phù hợp, phiên bản dependency được quản lý theo Spring Boot. Nếu dự án không sử dụng dependency management, phải cung cấp version tương thích với phiên bản Boot đang dùng.

Thử biên dịch:

~~~bash
./mvnw clean compile
~~~

Trên Windows PowerShell có thể chạy:

~~~powershell
.\mvnw.cmd clean compile
~~~

Sau biên dịch, xem metadata được sinh ra ở:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

Trong một số cấu hình build, file trung gian có thể nằm ở vị trí khác trước khi được copy sang output classes. Hãy xem kết quả build thực tế thay vì giả định mọi dự án đều có cùng cấu trúc thư mục.

### Nếu dùng maven-compiler-plugin với annotationProcessorPaths

Một số dự án cấu hình riêng danh sách annotation processors:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-configuration-processor</artifactId>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là ví dụ định hướng; các phiên bản plugin/processor và cơ chế quản lý version phải khớp với dự án. Nếu build của bạn dùng `annotationProcessorPaths` tường minh, cần bảo đảm processor Spring Boot **thực sự nằm trong đường dẫn xử lý annotation**. Chỉ thêm dependency theo cách không được compiler sử dụng có thể dẫn tới việc không sinh metadata.

Không cần áp dụng cùng lúc mọi kiểu cấu hình Maven chỉ vì thấy nhiều ví dụ trên mạng. Chọn một cách quản lý processor phù hợp với Maven setup hiện tại.

## 4. Thêm dependency với Gradle Groovy DSL

Với dự án Gradle đã có plugin Java và Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Cấu hình `annotationProcessor` đặt dependency trên **annotation processor path của tác vụ compileJava**, đúng với mục đích tạo metadata lúc biên dịch.

Chạy:

~~~bash
./gradlew clean compileJava
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean compileJava
~~~

Thư mục output thường có dạng:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

Đường dẫn chính xác có thể phụ thuộc cấu hình Gradle hoặc plugin. Khi đóng gói Boot JAR, metadata có thể xuất hiện dưới:

~~~text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
~~~

### Gradle Kotlin DSL

Nếu dự án dùng `build.gradle.kts`:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")

    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

Ví dụ trên giả định phiên bản dependency được dự án quản lý bằng plugin/BOM thích hợp. Nếu không, thêm version phù hợp với phiên bản Spring Boot.

### Phân biệt implementation và annotationProcessor

- `implementation`: các dependency mã Java cần khi compile và chạy.
- `annotationProcessor`: các thư viện xử lý annotation lúc compile.
- `testAnnotationProcessor`: processor dành riêng cho mã test, chỉ khi cần.

Với `spring-boot-configuration-processor`, nên khai báo ở annotation processor path thay vì đưa nó vào runtime classpath chỉ để IDE có gợi ý. Processor không cần được tạo bean để hoạt động.

## 5. Tạo một @ConfigurationProperties record được processor phân tích

Ví dụ một ứng dụng gửi thông báo. Tạo enum:

~~~java
package com.example.notification.config;

public enum DeliveryChannel {
    EMAIL,
    SMS,
    WEBHOOK
}
~~~

Tạo record:

~~~java
package com.example.notification.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * Các thiết lập gửi thông báo của ứng dụng.
 *
 * @param enabled có cho phép gửi thông báo hay không
 * @param channel kênh gửi mặc định
 * @param connectTimeout thời gian chờ kết nối tới nhà cung cấp
 * @param retry cấu hình thử gửi lại
 */
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("EMAIL") DeliveryChannel channel,
        @DefaultValue("3s") Duration connectTimeout,
        @DefaultValue Retry retry) {

    /**
     * Thiết lập retry.
     *
     * @param maxAttempts số lần thử tối đa
     * @param delay khoảng chờ giữa các lần thử
     */
    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("200ms") Duration delay) {
    }
}
~~~

Các tên thuộc tính mong đợi gồm:

~~~text
app.notification.enabled
app.notification.channel
app.notification.connect-timeout
app.notification.retry.max-attempts
app.notification.retry.delay
~~~

Ý nghĩa:

- `prefix = "app.notification"` định nghĩa gốc của nhóm.
- `enabled` là kiểu boolean.
- `channel` là enum `DeliveryChannel`.
- `connectTimeout` là `Duration`; tên chuẩn trong config là `connect-timeout`.
- `retry` là một record lồng nhau.
- `@DefaultValue` phục vụ Binder khi thuộc tính thiếu; processor có thể biểu diễn thông tin default phù hợp trong metadata tùy cách phát hiện và hỗ trợ phiên bản.
- JavaDoc cung cấp mô tả hữu ích cho metadata/IDE khi processor có thể trích xuất theo cấu trúc mã hiện tại.

Ví dụ trong `application.yml`:

~~~yaml
app:
  notification:
    channel: WEBHOOK
    connect-timeout: 5s
    retry:
      max-attempts: 5
      delay: 500ms
~~~

Các giá trị từ file chỉ là **giá trị cấu hình runtime**. Processor có thể sinh metadata mà không cần chạy Spring Boot hoặc đọc giá trị production trong file này.

## 6. Đăng ký configuration properties bean là bước riêng

Một record `@ConfigurationProperties` cần được Spring Boot đăng ký để có thể inject như bean.

Lớp ứng dụng:

~~~java
package com.example.notification;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class NotificationApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotificationApplication.class, args);
    }
}
~~~

Với record nằm dưới package ứng dụng, `@ConfigurationPropertiesScan` tìm và đăng ký nó.

Một cách khác:

~~~java
@EnableConfigurationProperties(NotificationProperties.class)
~~~

được đặt trên lớp configuration thích hợp, với import `org.springframework.boot.context.properties.EnableConfigurationProperties`.

**Phân biệt rõ:**

- `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`: giúp tạo bean configuration properties khi ứng dụng chạy.
- `spring-boot-configuration-processor`: chạy trong quá trình biên dịch và tạo JSON metadata.

Có thể tạo metadata cho một class ngay cả khi ứng dụng hiện tại chưa đăng ký bean đó để sử dụng. Ngược lại, ứng dụng vẫn có thể bind thành công khi không cài processor nhưng sẽ thiếu thông tin gợi ý do processor sinh.

## 7. Kiểm tra metadata vừa được tạo

Sau khi thêm processor và biên dịch thành công, tìm:

~~~text
META-INF/spring-configuration-metadata.json
~~~

ở output classes.

Với Maven:

~~~bash
./mvnw clean compile
~~~

Sau đó mở:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

Với Gradle:

~~~bash
./gradlew clean compileJava
~~~

Sau đó xem:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

Ví dụ cấu trúc JSON **minh họa**:

~~~json
{
  "groups": [
    {
      "name": "app.notification",
      "type": "com.example.notification.config.NotificationProperties",
      "sourceType": "com.example.notification.config.NotificationProperties"
    }
  ],
  "properties": [
    {
      "name": "app.notification.enabled",
      "type": "java.lang.Boolean",
      "description": "Có cho phép gửi thông báo hay không."
    },
    {
      "name": "app.notification.connect-timeout",
      "type": "java.time.Duration",
      "description": "Thời gian chờ kết nối tới nhà cung cấp."
    }
  ],
  "hints": []
}
~~~

Đây là **ví dụ rút gọn về định dạng**, không phải cam kết tệp được sinh có chính xác từng field hay kiểu chuỗi như vậy. Processor có thể xuất thêm `sourceType`, `defaultValue`, thông tin deprecation, nhiều property nested và metadata liên quan khác; giá trị thực tế phụ thuộc định nghĩa Java và phiên bản processor.

Điểm cần kiểm tra là các tên như `app.notification.enabled` và `app.notification.connect-timeout` được nhận diện. Nếu một khóa không xuất hiện, xem lại annotation, package, kiểu cấu trúc, quá trình compile và khả năng processor được thực thi.

### Quan sát Boot JAR

Với ứng dụng đóng gói Spring Boot executable JAR, metadata của mã ứng dụng thường được đặt dưới lớp resource của app:

~~~text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
~~~

Có thể dùng:

~~~bash
jar tf build/libs/notification-app.jar
~~~

và tìm đường dẫn có tên `spring-configuration-metadata.json`. Tên file JAR là minh họa; thay bằng đường dẫn build tạo ra thực tế.

Không yêu cầu runtime phải tự đọc JSON này để Binder hoạt động. IDE hoặc công cụ ngoài sử dụng metadata theo nhu cầu.

## 8. Định dạng metadata: groups, properties và hints

Một file metadata chuẩn thường có ba mảng quan trọng:

~~~json
{
  "groups": [],
  "properties": [],
  "hints": []
}
~~~

### 8.1. groups: nhóm thuộc tính

Một group mô tả một prefix cấu hình, chẳng hạn:

~~~json
{
  "name": "app.notification",
  "type": "com.example.notification.config.NotificationProperties",
  "sourceType": "com.example.notification.config.NotificationProperties"
}
~~~

Khi một module có nhiều class được đánh dấu `@ConfigurationProperties`, metadata có thể liệt kê nhiều groups.

Các group có thể phản ánh một class và một số cấu trúc lồng nhau. Đừng giả định chỉ có đúng một group cho một file Java.

### 8.2. properties: từng thuộc tính được hỗ trợ

Ví dụ:

~~~json
{
  "name": "app.notification.connect-timeout",
  "type": "java.time.Duration",
  "description": "Thời gian chờ kết nối tới dịch vụ gửi thông báo.",
  "sourceType": "com.example.notification.config.NotificationProperties"
}
~~~

Thông tin có thể gồm:

- `name`: tên property ở dạng chuẩn.
- `type`: kiểu Java.
- `description`: mô tả có ích cho người dùng.
- `sourceType` hoặc `sourceMethod`: nguồn khai báo trong mã nếu có.
- `defaultValue`: giá trị mặc định khi có thể suy ra.
- `deprecation`: thông tin khóa đã cũ, có thể bao gồm cách thay thế.

Không phải mọi field đều bắt buộc có trong từng entry. Nếu metadata không chứa `description`, IDE có thể vẫn gợi ý tên và kiểu nhưng thiếu phần giải thích.

### 8.3. hints: gợi ý giá trị và provider

Một hint có thể mô tả những giá trị được đề xuất cho một tên property:

~~~json
{
  "name": "app.notification.channel",
  "values": [
    {
      "value": "EMAIL",
      "description": "Gửi qua email."
    },
    {
      "value": "SMS",
      "description": "Gửi qua SMS."
    },
    {
      "value": "WEBHOOK",
      "description": "Gửi qua HTTP webhook."
    }
  ]
}
~~~

IDE có thể sử dụng hints để gợi ý lựa chọn. Với property enum, công cụ và processor có thể suy ra các giá trị từ kiểu enum; nhưng metadata thủ công hữu ích khi muốn mô tả rõ hoặc khi property là String có danh sách giá trị đề xuất.

**Một hint không nhất thiết là validation runtime.** Nếu Java field là `String`, chỉ tạo hint `EMAIL`/`SMS` không làm Binder từ chối các chuỗi khác. Muốn hạn chế giá trị runtime, dùng enum hoặc validation phù hợp.

## 9. JavaDoc giúp tạo mô tả hữu ích

Configuration metadata sẽ dễ sử dụng hơn nếu mỗi property có mô tả rõ ràng về ý nghĩa, đơn vị và tình huống dùng.

Ví dụ với JavaBean:

~~~java
package com.example.notification.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.gateway")
public class GatewayProperties {

    /** Thời gian chờ kết nối đến gateway. */
    private Duration connectTimeout = Duration.ofSeconds(3);

    /** Tên hệ thống hiển thị trong log và dashboard. */
    private String serviceName = "notification-service";

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public String getServiceName() {
        return serviceName;
    }

    public void setServiceName(String serviceName) {
        this.serviceName = serviceName;
    }
}
~~~

Processor có thể trích mô tả từ JavaDoc của các field/getter thích hợp. Với record, JavaDoc ở record và các `@param` tương ứng giúp làm rõ ý nghĩa component theo cơ chế và phiên bản processor hỗ trợ.

Nên viết mô tả tập trung vào **ý nghĩa nghiệp vụ**, thay vì chỉ lặp tên field:

- Tốt: “Thời gian tối đa chờ kết nối tới gateway; dùng đơn vị như 500ms hoặc 3s.”
- Chưa hữu ích: “Connect timeout của gateway.”

Không đưa secret, token hoặc dữ liệu vận hành nhạy cảm vào JavaDoc hay metadata. Metadata có thể được đóng gói cùng artifact và đọc bởi IDE/công cụ của người dùng thư viện.

### JavaDoc không nên mang giá trị môi trường thật

Nếu một default chỉ hợp lệ với local development, đừng dùng mô tả kiểu “Mật khẩu mặc định là secret123”. Thay vào đó nói rõ property phải được cung cấp bằng nguồn bí mật của môi trường triển khai và cách kiểm tra trường bắt buộc.

## 10. Giá trị mặc định trong metadata

Một số default có thể được processor phát hiện ở thời điểm compile, chẳng hạn field initializer đơn giản hoặc `@DefaultValue` trong constructor binding khi được phiên bản processor hỗ trợ.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") int concurrency,
        @DefaultValue("true") boolean enabled) {
}
~~~

Dù metadata có thể mô tả defaults, cơ chế runtime vẫn là:

- Nếu property tồn tại, Binder dùng giá trị hiệu lực từ các nguồn.
- Nếu property vắng mặt, Binder có thể dùng `@DefaultValue` thích hợp.
- Metadata **không phải nơi quyết định giá trị runtime**; không cần đặt `defaultValue` thủ công trong JSON chỉ để làm cho ứng dụng dùng default.

Ví dụ bổ sung metadata:

~~~json
{
  "properties": [
    {
      "name": "app.worker.concurrency",
      "type": "java.lang.Integer",
      "description": "Số worker được cấu hình.",
      "defaultValue": 4
    }
  ]
}
~~~

Với JSON metadata, `defaultValue` là thông tin cho công cụ phát triển. Nó **không tự tạo** default trong Binder nếu Java code hoặc nguồn cấu hình không cung cấp giá trị tương ứng.

Đừng dựa vào metadata sinh ra để xác định default chính xác của một biểu thức có logic runtime phức tạp, ví dụ default được tính từ CPU count, một bean khác hoặc trạng thái hệ thống. Compiler không thể suy luận mọi giá trị chỉ biết khi ứng dụng chạy.

## 11. additional-spring-configuration-metadata.json dùng để làm gì?

Không phải mọi property đều được processor suy ra đầy đủ từ annotation. Ví dụ:

- Một property được đọc trực tiếp bằng `Environment.getProperty(...)`.
- Một cấu hình String cần gợi ý các giá trị được hỗ trợ.
- Cần mô tả thêm cho property mà processor chưa tạo ra mô tả hữu ích.
- Một số metadata cần cung cấp `deprecation` hoặc thông tin chuyển đổi tên khóa.

Spring Boot hỗ trợ file bổ sung:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Tạo file JSON này trong source resources của dự án. Ví dụ:

~~~json
{
  "properties": [
    {
      "name": "app.notification.webhook-secret-ref",
      "type": "java.lang.String",
      "description": "Tên tham chiếu đến secret cấu hình webhook, không phải nội dung secret."
    }
  ],
  "hints": [
    {
      "name": "app.notification.channel",
      "values": [
        {
          "value": "EMAIL",
          "description": "Gửi email."
        },
        {
          "value": "SMS",
          "description": "Gửi tin nhắn SMS."
        },
        {
          "value": "WEBHOOK",
          "description": "Gửi HTTP webhook."
        }
      ]
    }
  ]
}
~~~

Khi build chạy processor và phát hiện file bổ sung, các thông tin thích hợp được **kết hợp với metadata được sinh tự động** thành kết quả cho công cụ phát triển. Đối với một số khóa chưa được processor phát hiện, file bổ sung giúp chúng vẫn xuất hiện trong metadata.

### Tại sao cần đặt đúng đường dẫn?

Tên file và vị trí `META-INF` có ý nghĩa riêng. Không đặt file bổ sung thành `additional-spring-configuration-metadata.yml` hoặc ở thư mục root rồi kỳ vọng processor tự nhận.

Nên tạo bằng đúng tên:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

và chạy lại compile. Trong các build tùy biến, nếu tài nguyên chưa có mặt trước khi processor hoạt động, có thể cần kiểm tra thứ tự tác vụ xử lý resources để processor đọc được file đúng lúc.

### Không dùng additional metadata để khai báo giá trị môi trường

Ví dụ:

~~~json
{
  "properties": [
    {
      "name": "app.payment.password",
      "defaultValue": "real-password"
    }
  ]
}
~~~

không phải cách cấp mật khẩu an toàn, cũng không phải cách để Spring Boot đọc password tại runtime. Metadata có thể được người khác xem và không dùng để quản lý secrets.

## 12. Cung cấp value hints cho thuộc tính String

Giả sử ứng dụng muốn người dùng chọn một provider:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(String provider) {
}
~~~

Vì `provider` là String, IDE không biết chắc những giá trị nào nên gợi ý. Có thể tạo metadata bổ sung:

~~~json
{
  "hints": [
    {
      "name": "app.payment.provider",
      "values": [
        {
          "value": "sandbox",
          "description": "Provider mô phỏng dùng trong môi trường phát triển."
        },
        {
          "value": "internal",
          "description": "Provider nội bộ."
        },
        {
          "value": "external",
          "description": "Provider bên ngoài."
        }
      ]
    }
  ]
}
~~~

Khi người dùng viết:

~~~yaml
app:
  payment:
    provider: sandbox
~~~

IDE có thể gợi ý `sandbox`, `internal` hoặc `external`. Nhưng nếu code chỉ có `String provider` mà không validation, Binder vẫn có thể chấp nhận `other`.

Nếu tập giá trị phải thực sự bị giới hạn, enum là lựa chọn rõ ràng:

~~~java
public enum PaymentProvider {
    SANDBOX,
    INTERNAL,
    EXTERNAL
}
~~~

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(PaymentProvider provider) {
}
~~~

Metadata hỗ trợ phát triển; **kiểu enum và validation** mới giúp bảo đảm một lựa chọn runtime phù hợp.

## 13. Value providers và gợi ý nâng cao

Trong metadata, `hints` còn có thể chứa `providers`, cho phép IDE sử dụng cơ chế gợi ý động theo những loại giá trị đã được nhận biết.

Ví dụ về hình dạng dữ liệu:

~~~json
{
  "hints": [
    {
      "name": "app.storage.directory",
      "providers": [
        {
          "name": "any"
        }
      ]
    }
  ]
}
~~~

Đây chỉ là ví dụ cú pháp provider trong metadata. Spring Boot định nghĩa một số provider/hint thông dụng với các tham số riêng; công cụ IDE có thể hỗ trợ một phần, toàn bộ hoặc bỏ qua tùy tính năng.

**Không tự sáng tạo tên provider** mà chưa kiểm tra tài liệu metadata của phiên bản được sử dụng. Với những lựa chọn hữu hạn như `sandbox`, `internal`, `external`, danh sách `values` tường minh thường đơn giản hơn.

Metadata không bắt buộc phải có `hints`. Nếu property đã dùng enum, các công cụ có thể dựa vào kiểu để cung cấp gợi ý.

## 14. Metadata cho nested configuration properties

Nhóm property thường có nhiều cấp:

~~~yaml
app:
  mail:
    smtp:
      host: smtp.example.org
      port: 2525
    retry:
      max-attempts: 3
      backoff: 500ms
~~~

Record:

~~~java
package com.example.configdemo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        Smtp smtp,
        Retry retry) {

    public record Smtp(String host, int port) {
    }

    public record Retry(int maxAttempts, Duration backoff) {
    }
}
~~~

Processor có thể tạo metadata cho những tên như:

~~~text
app.mail.smtp.host
app.mail.smtp.port
app.mail.retry.max-attempts
app.mail.retry.backoff
~~~

### Khi nested type là một class riêng

Với các lớp cấu hình không lồng về mặt khai báo Java, processor có thể cần chỉ dẫn rằng một field có kiểu custom là **nested configuration**, chứ không phải một giá trị scalar. Spring Boot hỗ trợ annotation:

~~~java
import org.springframework.boot.context.properties.NestedConfigurationProperty;
~~~

Ví dụ trên JavaBean:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    @NestedConfigurationProperty
    private RetryProperties retry = new RetryProperties();

    public RetryProperties getRetry() {
        return retry;
    }

    public void setRetry(RetryProperties retry) {
        this.retry = retry;
    }
}
~~~

`RetryProperties` là class cấu hình khác do dự án định nghĩa, có các getter/setter thích hợp. Annotation `@NestedConfigurationProperty` **chủ yếu hỗ trợ mô hình metadata cho nested property**, không phải là điều kiện duy nhất quyết định Binder có liên kết được một nested object hay không.

Với inner type hoặc kiểu lồng thông thường được processor nhận diện, không nhất thiết phải thêm annotation này. Sử dụng khi có lý do rõ ràng và theo khuyến nghị của Spring Boot.

## 15. Metadata cho @ConfigurationProperties từ thư viện dùng chung

Một library có thể định nghĩa:

~~~java
@ConfigurationProperties(prefix = "acme.client")
public record AcmeClientProperties(
        String baseUrl,
        Duration timeout) {
}
~~~

Và dùng processor trong chính module library. Khi library được compile và đóng gói, metadata nằm trong JAR để các dự án phụ thuộc có thể được IDE hỗ trợ với prefix `acme.client`.

Cấu trúc thư viện có thể như sau:

~~~text
acme-client-spring-boot/
├── src/main/java/com/acme/client/AcmeClientProperties.java
├── src/main/resources/META-INF/additional-spring-configuration-metadata.json
└── build.gradle
~~~

Sau build:

~~~text
META-INF/spring-configuration-metadata.json
~~~

được đóng gói trong artifact kết quả.

Đây là lý do annotation processor không chỉ hữu ích với ứng dụng chạy trực tiếp. Nó có giá trị lớn cho **starter**, thư viện cấu hình và các module dùng lại trong nhiều dự án.

### Metadata không tự đăng ký bean library

Nếu một thư viện chỉ đóng gói JSON metadata nhưng không có cấu hình Spring đăng ký `AcmeClientProperties`, IDE vẫn có thể gợi ý tên khóa, còn Spring Boot runtime chưa chắc có bean được bind.

Thư viện cần một cơ chế đăng ký phù hợp như auto-configuration và `@EnableConfigurationProperties` trong ngữ cảnh cần thiết. Đó là thiết kế runtime riêng, không phải trách nhiệm của metadata processor.

## 16. Kết hợp Lombok với configuration processor

Một số dự án dùng Lombok để sinh getter/setter hoặc constructor:

~~~java
@Getter
@Setter
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private boolean enabled;
    private int maxEntries;
}
~~~

Với mã trên, phần lớn phương thức accessor có thể được Lombok sinh trong quá trình annotation processing. Nếu Spring Boot configuration processor chạy trước khi Lombok cung cấp thông tin cần thiết, metadata có thể không đầy đủ hoặc không nhận diện đúng cấu trúc.

Khi dùng Lombok:

- Bảo đảm cả **Lombok** và **Spring Boot configuration processor** đều có trong annotation processor path phù hợp.
- Chú ý thứ tự xử lý nếu build tool/plugin yêu cầu, để processor của Spring Boot nhìn thấy cấu trúc mà Lombok tạo ra.
- Kiểm tra tệp metadata thực tế sau compile, đừng chỉ xem IDE có nhận getter/setter hay không.
- Nếu Java 21 và các thuộc tính đơn giản, record hoặc class với accessor tường minh có thể giảm sự phụ thuộc vào thứ tự của nhiều processor.

Ví dụ Gradle Groovy DSL ở mức dependency:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Đây là ví dụ cấu hình annotation processor path; phiên bản cần được quản lý phù hợp với dự án. Không cần thêm Lombok nếu mã của bạn dùng record và không có Lombok.

## 17. Những lý do khiến metadata không được sinh

### 17.1. Chưa thêm processor vào compiler

Triệu chứng: ứng dụng chạy được và bind được `@ConfigurationProperties` nhưng không thấy `META-INF/spring-configuration-metadata.json` sau compile.

Hướng xử lý: kiểm tra `pom.xml` hoặc `build.gradle`, bảo đảm `spring-boot-configuration-processor` thực sự tham gia annotation processing.

### 17.2. Chưa compile lại sau thay đổi

Processor chạy khi biên dịch. Nếu chỉ lưu file Java rồi mở metadata cũ, JSON có thể chưa cập nhật.

Hướng xử lý:

~~~bash
./mvnw clean compile
~~~

hoặc:

~~~bash
./gradlew clean compileJava
~~~

và xem file output vừa được tạo.

### 17.3. Tắt annotation processing trong IDE/build

Nếu compiler hoặc IDE được cấu hình tắt xử lý annotation, processor không chạy trong lần compile đó.

Hướng xử lý: kiểm tra cấu hình annotation processing của build và IDE. Ưu tiên **build CLI tái lập được** trước; IDE có thể dùng build tool hoặc cơ chế build riêng.

### 17.4. Class không có @ConfigurationProperties thích hợp

Ví dụ:

~~~java
@Component
public class MailService {

    @Value("${app.mail.host}")
    private String host;
}
~~~

Processor không tự suy ra một **nhóm configuration properties** đầy đủ từ mọi `@Value` rải rác. Nếu muốn metadata tốt cho nhóm cấu hình, chuyển sang `@ConfigurationProperties` hoặc bổ sung metadata thủ công cho key thực sự cần gợi ý.

### 17.5. Prefix không đúng hoặc không chuẩn

~~~java
@ConfigurationProperties(prefix = "app.notification")
~~~

khác với:

~~~yaml
app:
  notifications:
    enabled: true
~~~

Số nhiều `notifications` và số ít `notification` là hai prefix khác nhau. Metadata sinh theo Java, không tự sửa YAML sai tên.

Nên sử dụng tên canonical dạng lowercase kebab-case, ví dụ `app.notification.connect-timeout`.

### 17.6. Cấu trúc nested không được nhận diện

Nếu nested class là kiểu Java tách rời, thiếu chỉ dẫn hoặc accessor cần thiết, processor có thể không suy ra các property con như mong muốn. Cân nhắc `@NestedConfigurationProperty` khi phù hợp và kiểm tra JSON thực tế.

### 17.7. Lombok hoặc processor khác ảnh hưởng thứ tự

Nếu các accessor/constructor được sinh ở compile time, Spring Boot processor cần nhìn thấy cấu trúc phù hợp. Kiểm tra annotation processor path, thứ tự xử lý và tương thích version.

### 17.8. Tìm sai vị trí output

Với Maven có thể nằm dưới `target/classes/META-INF`; với Gradle thường là `build/classes/java/main/META-INF`. Khi đóng gói Boot executable JAR, tài nguyên ứng dụng thường nằm dưới `BOOT-INF/classes/META-INF`. Đừng tìm duy nhất ở `src/main/resources` để kết luận metadata không được sinh.

### 17.9. JSON additional metadata không hợp lệ

Nếu `additional-spring-configuration-metadata.json` có dấu phẩy thừa, sai ngoặc hoặc cấu trúc không phù hợp, quá trình kết hợp metadata có thể lỗi hoặc bỏ qua dữ liệu.

Hãy kiểm tra JSON bằng parser/linter, sửa đúng cấu trúc `properties`/`hints` và compile lại.

### 17.10. IDE chưa cập nhật chỉ mục

Nếu file metadata đã có mà IDE chưa gợi ý:

- Kiểm tra hỗ trợ Spring Boot configuration metadata của IDE và plugin đang dùng.
- Thử đồng bộ lại dự án từ Maven/Gradle.
- Kiểm tra module chứa metadata có nằm trong dependency path của module đang sửa config không.
- Kiểm tra key đang nhập nằm trong prefix thực tế của metadata.
- Nếu cần, cho IDE tải lại project/index theo hướng dẫn của IDE.

Sự thiếu autocomplete **không đủ chứng minh** file metadata không tồn tại. Hãy phân biệt lỗi build metadata với lỗi IDE đọc và hiển thị metadata.

## 18. Metadata và deprecated properties

Khi đổi tên property công khai, ví dụ chuyển từ:

~~~text
app.mail.legacy-timeout
~~~

sang:

~~~text
app.mail.connect-timeout
~~~

người dùng ứng dụng hoặc thư viện cần biết khóa cũ đã không còn được khuyến nghị.

Configuration metadata có thể chứa thông tin deprecation:

~~~json
{
  "properties": [
    {
      "name": "app.mail.legacy-timeout",
      "type": "java.time.Duration",
      "description": "Tên cấu hình cũ cho thời gian chờ kết nối.",
      "deprecation": {
        "reason": "Đổi sang tên rõ ràng về kết nối.",
        "replacement": "app.mail.connect-timeout"
      }
    }
  ]
}
~~~

Với một class configuration properties sử dụng JavaBean getter, Spring Boot có `@DeprecatedConfigurationProperty` để bổ sung thông tin deprecation trong những trường hợp thích hợp, ví dụ khi property đã được đánh dấu deprecated.

**Lưu ý:** metadata deprecation giúp IDE cảnh báo và gợi ý thay thế; nó không tự làm alias runtime từ tên cũ sang tên mới. Muốn vẫn hỗ trợ property cũ lúc chạy, cần thiết kế tương thích và xử lý rõ trong mã ứng dụng hoặc binding logic phù hợp.

Không đặt cả hai key vào metadata rồi cho rằng Binder tự biết cách ưu tiên giữa chúng.

## 19. Cách kiểm tra file JSON được sinh một cách có hệ thống

Một trình tự tối thiểu cho dự án Java:

1. Xác nhận class được đánh dấu `@ConfigurationProperties` với prefix đúng.
2. Xác nhận dependency processor có trong build và được đặt vào annotation processor path.
3. Thực hiện clean compile bằng Maven/Gradle.
4. Tìm `META-INF/spring-configuration-metadata.json` trong output classes.
5. Mở JSON và kiểm tra tên các group/property mong đợi.
6. Nếu cần, thêm JavaDoc hoặc `additional-spring-configuration-metadata.json`.
7. Compile lại và kiểm tra metadata đã kết hợp.
8. Đồng bộ IDE và thử autocomplete trong `application.yml`.

Ví dụ kiểm tra bằng JDK tool:

~~~bash
jar tf build/libs/notification-app.jar
~~~

Sau đó tìm chuỗi `spring-configuration-metadata.json` trong danh sách tệp JAR.

Hoặc xem file JSON trực tiếp bằng trình soạn thảo hay script đọc file. Nếu muốn tự động hóa trong CI, có thể viết test hoặc script phân tích JSON để xác nhận các property quan trọng xuất hiện mà không phụ thuộc vào IDE.

### Phân biệt kiểm tra metadata với kiểm thử binding

Kiểm tra JSON chỉ chứng minh processor mô tả property. Để chứng minh runtime bind được cấu hình, viết test `ApplicationContextRunner` hoặc integration test với `@EnableConfigurationProperties` tương ứng.

Hai phép kiểm tra bổ sung cho nhau nhưng không thay thế nhau.

## 20. Kiểm thử runtime với ApplicationContextRunner

Giả sử record:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        boolean enabled,
        DeliveryChannel channel,
        Duration connectTimeout) {
}
~~~

Một test:

~~~java
package com.example.notification;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import com.example.notification.config.DeliveryChannel;
import com.example.notification.config.NotificationProperties;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class NotificationPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BindingConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(NotificationProperties.class)
    static class BindingConfiguration {
    }

    @Test
    void bindsValuesFromEnvironment() {
        runner.withPropertyValues(
                "app.notification.enabled=true",
                "app.notification.channel=EMAIL",
                "app.notification.connect-timeout=5s")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    NotificationProperties properties =
                            context.getBean(NotificationProperties.class);

                    assertThat(properties.enabled()).isTrue();
                    assertThat(properties.channel())
                            .isEqualTo(DeliveryChannel.EMAIL);
                    assertThat(properties.connectTimeout())
                            .isEqualTo(Duration.ofSeconds(5));
                });
    }
}
~~~

Test giả định dự án có `spring-boot-starter-test`, JUnit Jupiter và AssertJ.

Nếu bỏ dependency processor nhưng giữ phần cấu hình runtime và registration đúng, test binding vẫn có thể chạy thành công. Đó là một bằng chứng trực quan rằng **processor không phải thành phần runtime của Binder**.

Ngược lại, metadata có thể được sinh đầy đủ nhưng runtime không bind đúng vì file YAML sai prefix hoặc bean chưa đăng ký. Luôn kiểm tra đúng vấn đề đang xử lý.

## 21. Bảng phân biệt một số annotation liên quan

| Annotation/cấu hình | Công dụng |
| --- | --- |
| `@ConfigurationProperties(prefix = "...")` | Khai báo nhóm thuộc tính cần bind và nguồn cho processor |
| `@ConfigurationPropertiesScan` | Quét, đăng ký bean configuration properties |
| `@EnableConfigurationProperties` | Đăng ký cụ thể các class configuration properties |
| `@DefaultValue` | Đặt mặc định cho tham số constructor/record khi Binder không tìm thấy property |
| `@NestedConfigurationProperty` | Hỗ trợ mô tả nested property với processor trong một số trường hợp |
| `@DeprecatedConfigurationProperty` | Mô tả property deprecated/replacement trong metadata |
| `@Validated` | Kích hoạt kiểm tra Bean Validation cho configuration properties |
| `@ConfigurationPropertiesBinding` | Đăng ký converter dành riêng cho binding cấu hình |
| `annotationProcessor(...)` (Gradle) | Đưa processor vào quá trình compileJava |
| `spring-boot-configuration-processor` | Công cụ sinh metadata JSON |

Đừng dùng `@NestedConfigurationProperty` như một biện pháp thay thế `@NotNull`/validation. Cũng đừng xem `@DeprecatedConfigurationProperty` là công cụ tự động đổi tên khóa runtime.

## 22. Tổ chức metadata cho module lớn

Giả sử một dự án có ba nhóm cấu hình:

~~~text
app.mail.*
app.storage.*
app.payment.*
~~~

Có thể tạo ba class riêng:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(...) {}

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(...) {}

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(...) {}
~~~

Processor sẽ xử lý các class có annotation phù hợp và tạo metadata tương ứng trong output.

Một cấu trúc source:

~~~text
src/main/
├── java/com/example/config/
│   ├── MailProperties.java
│   ├── StorageProperties.java
│   └── PaymentProperties.java
└── resources/
    ├── application.yml
    └── META-INF/
        └── additional-spring-configuration-metadata.json
~~~

Không cần một file `additional-spring-configuration-metadata.json` riêng cho mỗi class. File bổ sung của module có thể mô tả nhiều property và hint, trong khi processor tổng hợp thông tin cho các class trong module.

Nên đặt mô tả gần nguồn Java khi có thể; chỉ đưa vào additional JSON những chi tiết không biểu đạt thuận tiện qua annotation/Javadoc, chẳng hạn giá trị hint cho String hoặc property động.

## 23. Những hiểu nhầm thường gặp

### “Cài processor sẽ tự bật @ConfigurationProperties”

Sai. Processor chỉ sinh metadata lúc compile. Muốn có bean cấu hình ở runtime phải đăng ký qua cơ chế Spring Boot phù hợp.

### “Không có processor thì Spring Boot không đọc được application.yml”

Sai. Spring Boot vẫn đọc Config Data và Binder vẫn có thể bind giá trị vào object cấu hình. Chỉ thiếu metadata hỗ trợ phát triển.

### “Metadata là nơi khai báo giá trị mặc định cho ứng dụng”

Không hoàn toàn. Metadata có thể mô tả `defaultValue` cho công cụ, nhưng không phải nguồn runtime để Binder tự dùng. Đặt mặc định trong Java (`@DefaultValue`, field initializer) hoặc cấu hình theo thiết kế.

### “Mọi @Value sẽ được processor liệt kê tự động”

Không. Processor chủ yếu dựa trên cấu trúc configuration properties và có giới hạn về việc phát hiện các property đọc thủ công. Với khóa cần bổ sung, có thể tạo `additional-spring-configuration-metadata.json`.

### “IDE gợi ý được nghĩa là key chắc chắn hợp lệ lúc chạy”

Không. Hint có thể tồn tại cho String mà không có validation; prefix có thể khác profile; property có thể bị nguồn khác ghi đè. Metadata không xác minh trạng thái runtime.

### “Thêm metadata deprecation sẽ tự chuyển khóa cũ sang khóa mới”

Không. Đây là thông tin cho IDE/công cụ. Logic tương thích runtime phải được xây dựng riêng nếu cần.

### “Cần đưa processor vào JAR runtime để hoạt động”

Không. Processor được chạy trong quá trình compile. File metadata có thể được đóng gói để IDE hoặc công cụ khác đọc; runtime Binder không cần bản thân processor.

## 24. Bài tập thực hành

### Bài 1 — Tạo dependency processor

Với dự án Spring Boot Maven, thêm `spring-boot-configuration-processor` với `optional=true`. Chạy `./mvnw clean compile` rồi tìm tệp `target/classes/META-INF/spring-configuration-metadata.json`.

Nếu dùng Gradle, đặt dependency trong cấu hình `annotationProcessor` và chạy `./gradlew clean compileJava`.

### Bài 2 — Sinh metadata cho record

Tạo:

~~~java
@ConfigurationProperties(prefix = "demo.worker")
public record WorkerProperties(
        @DefaultValue("4") int concurrency,
        @DefaultValue("true") boolean enabled) {
}
~~~

Compile rồi tìm các property `demo.worker.concurrency` và `demo.worker.enabled` trong JSON.

### Bài 3 — Viết JavaDoc cho thuộc tính

Tạo một JavaBean `@ConfigurationProperties(prefix="demo.cache")` với field `Duration ttl` và JavaDoc mô tả “Thời gian sống tối đa của bản ghi cache”. Compile và tìm phần description của `demo.cache.ttl` trong metadata.

### Bài 4 — Bổ sung hint cho String

Một property `demo.export.format` có kiểu String, hỗ trợ các giá trị `csv`, `json`, `xml`. Viết `additional-spring-configuration-metadata.json` với `hints` chứa ba giá trị và mô tả ngắn. Compile lại rồi kiểm tra JSON đầu ra.

### Bài 5 — Nested properties

Tạo record `DemoMailProperties(Smtp smtp)` với nested `Smtp(host,port)`. Kiểm tra metadata có các tên `demo.mail.smtp.host` và `demo.mail.smtp.port`.

### Bài 6 — Phân biệt metadata và runtime

Tạo một class `@ConfigurationProperties` hợp lệ, biên dịch có metadata nhưng cố ý không đăng ký class vào Spring context. Giải thích vì sao file JSON vẫn có thể chứa property, trong khi inject bean runtime chưa chắc thành công.

### Bài 7 — Giải quyết thiếu autocomplete

Sau khi compile, file JSON đã chứa `demo.worker.concurrency` nhưng IDE không gợi ý. Hãy kiểm tra plugin Spring Boot, việc import module, đồng bộ Maven/Gradle và cache/index của IDE thay vì sửa annotation một cách ngẫu nhiên.

### Bài 8 — Deprecated property

Một API cấu hình cũ `demo.mail.legacy-timeout` được thay bằng `demo.mail.connect-timeout`. Tạo metadata deprecation với `replacement` và giải thích vì sao điều đó không tự cung cấp runtime alias.

### Bài 9 — Test phát hiện lỗi tên property

Record chờ `demo.worker.concurrency` nhưng YAML có `demo.worker.concurency`. Giải thích sự khác biệt giữa cảnh báo autocomplete của IDE, lỗi thực tế khi bind và validation bắt buộc.

### Bài 10 — Phân biệt giá trị cấu hình với gợi ý giá trị

Metadata hint cho `demo.export.format` có `csv` và `json`. Nếu field Java là String, Binder có tự từ chối `txt` không? **Đáp án:** không phải chỉ vì hint; cần enum hoặc validation nếu muốn giới hạn giá trị.

## 25. Tổng kết

`spring-boot-configuration-processor` là công cụ **annotation processing tại thời điểm biên dịch** để tạo `META-INF/spring-configuration-metadata.json` từ các khai báo cấu hình trong mã Java. Metadata giúp IDE gợi ý tên khóa, kiểu, mô tả, default và hints, rất hữu ích với những ứng dụng và thư viện Spring Boot có nhiều `@ConfigurationProperties`.

Với Maven, thêm dependency processor phù hợp và bảo đảm Maven Compiler thực thi annotation processing. Với Gradle, sử dụng cấu hình `annotationProcessor`. Sau compile, kiểm tra tệp JSON trong output classes hoặc artifact và bổ sung `src/main/resources/META-INF/additional-spring-configuration-metadata.json` khi cần hints/thông tin không thể suy ra tự động.

**Giữ tách biệt hai trách nhiệm:** processor sinh metadata để hỗ trợ công cụ; Spring Boot Binder cùng cơ chế đăng ký configuration properties và validation mới quyết định hành vi cấu hình lúc chạy.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Spring Boot 3.3 — Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html)
- [Spring Boot 3.3 — Metadata Format](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html)
- [Spring Boot 3.3 — Manual Hints](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/manual-hints.html)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)

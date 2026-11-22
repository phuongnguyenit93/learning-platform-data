# Truyền thuộc tính JVM bằng -D và vị trí trước -jar

Khi triển khai ứng dụng Spring Boot dưới dạng tệp JAR, có nhiều cách đưa cấu hình vào tiến trình Java: ghi trong `application.properties` hoặc `application.yml`, đặt biến môi trường, truyền đối số Spring Boot `--key=value`, hoặc truyền **JVM system property** qua tham số `-Dkey=value`. Trong các cách này, `-D` có một quy tắc cú pháp đặc biệt quan trọng: **phải nằm trong vùng tùy chọn của lệnh `java`, tức ở trước `-jar` và tên tệp JAR**.

Bài này giải thích cú pháp `-D`, vị trí của nó trong lệnh khởi động, sự khác biệt giữa system property của JVM và biến môi trường hệ điều hành, cách Spring Boot đưa giá trị đó vào `Environment`, các quy tắc ghi đè, cách truyền trên shell/IDE/Gradle/container, và quy trình xử lý lỗi khi `-D` không phát huy tác dụng.

## 1. Hình dung đường đi của một thuộc tính JVM

~~~text
Terminal / script / container runtime
      |
      |  java -Dserver.port=9091 -jar app.jar
      v
Java launcher
      |
      |  nhận -Dserver.port=9091 trước -jar
      v
JVM system properties
      |
      |  System.getProperty("server.port") -> "9091"
      v
Spring Boot chuẩn bị Environment
      |
      |  Java system properties là một PropertySource
      v
Environment.getProperty("server.port") -> "9091"
      |
      v
Spring Boot liên kết giá trị vào cấu hình web server
      |
      v
Ứng dụng phục vụ HTTP tại cổng 9091
~~~

Hai ý chính:

1. **`-D` là tùy chọn của Java launcher/JVM.** Nó cần được Java xử lý trước khi chuyển quyền điều khiển cho ứng dụng.
2. **Spring Boot đọc system properties như một nguồn cấu hình.** Khi key trùng với một key mà Spring Boot hoặc mã ứng dụng tiêu thụ, giá trị có thể tác động đến ứng dụng.

Không phải key tùy ý nào cũng tự kích hoạt hành vi. Chẳng hạn `-Dapp.feature.enabled=true` chỉ cung cấp một giá trị; ứng dụng cần có mã hoặc bean đọc `app.feature.enabled` thì tính năng tương ứng mới thay đổi.

## 2. Cú pháp chính xác của -D

Dạng cơ bản:

~~~bash
java -Dten.thuoc.tinh=gia-tri -jar duong-dan/ung-dung.jar
~~~

Ví dụ với Spring Boot:

~~~bash
java -Dserver.port=9091 -jar order-service.jar
~~~

Dấu `-D` đứng liền trước tên key, giữa key và value là dấu `=`, không có khoảng trắng quanh `=` trong cùng một đối số.

Một số ví dụ hợp lệ:

~~~bash
java -Dspring.profiles.active=dev -jar order-service.jar

java -Dserver.port=9091 -Dspring.application.name=order-service -jar order-service.jar

java -Dapp.client.connect-timeout=2s -Dapp.feature.audit-enabled=true -jar order-service.jar
~~~

Mỗi `-Dkey=value` là một tùy chọn JVM riêng. Chúng thường được đặt liên tiếp trước `-jar`, nhưng vẫn có thể nằm xen giữa các tùy chọn JVM hợp lệ khác, miễn là tất cả được Java launcher hiểu **trước** phần chọn ứng dụng để chạy.

Có thể mô tả cấu trúc lệnh:

~~~text
java [tùy chọn JVM] -jar <jar-file> [đối số ứng dụng]
     ^^^^^^^^^^^^^        ^^^^^^^^  ^^^^^^^^^^^^^^^
      vị trí -D           tên JAR   ví dụ --server.port=9091
~~~

Trong các tình huống thông dụng, `-jar` chỉ rõ rằng Java sẽ thực thi ứng dụng có entry point trong JAR. **Các phần sau tên JAR là đối số chuyển cho chương trình**, không còn là danh sách tùy chọn JVM được Java launcher xử lý như phần trước.

## 3. Vị trí trước -jar: đúng và sai

### Đúng: Java nhận -D trước khi chạy JAR

~~~bash
java -Dserver.port=9091 -jar order-service.jar
~~~

Java đặt system property `server.port` thành chuỗi `9091`. Spring Boot có thể đọc thuộc tính đó và cấu hình cổng HTTP, nếu ứng dụng có embedded web server phù hợp và không bị nguồn ưu tiên cao hơn ghi đè.

### Sai: đặt -D sau tên JAR

~~~bash
java -jar order-service.jar -Dserver.port=9091
~~~

Ở đây, `-Dserver.port=9091` đã nằm trong vùng **đối số của ứng dụng**. Java launcher không dùng nó để thiết lập JVM system property. Mã `System.getProperty("server.port")` không nhận `9091` từ vị trí này chỉ vì đối số có chữ `-D`.

Spring Boot mặc định nhận các đối số tùy chọn dạng **hai dấu gạch** `--key=value`. Vì vậy, nếu muốn đặt cấu hình Spring Boot ở **sau JAR**, dùng:

~~~bash
java -jar order-service.jar --server.port=9091
~~~

Đó là **command-line property của Spring Boot**, không phải system property JVM. Hai lệnh sau có thể tạo ra cùng một giá trị cấu hình Spring Boot trong tình huống đơn giản, nhưng được xử lý bởi **hai cơ chế khác nhau**:

~~~bash
# JVM system property: -D ở trước -jar
java -Dserver.port=9091 -jar order-service.jar

# Spring Boot application argument: -- ở sau tên JAR
java -jar order-service.jar --server.port=9091
~~~

Nếu một framework hoặc mã ứng dụng có logic tự phân tích đối số `-D...` sau JAR, đó là hành vi riêng của chương trình ấy; không nên dựa vào nó như quy tắc chung của Java hay Spring Boot.

### Sai khác dễ nhầm: vị trí ngay sau -jar

~~~bash
java -jar -Dserver.port=9091 order-service.jar
~~~

Trong dạng lệnh này, vị trí ngay sau `-jar` dành cho **tên tệp JAR**. Đây không phải cách truyền `-D` cho JVM; lệnh có thể thất bại vì Java hiểu sai mục tiêu chạy. Cách rõ ràng là đặt `-Dserver.port=9091` trước `-jar`.

## 4. Có thể dùng nhiều -D trong cùng một lệnh

Không cần ghép nhiều thuộc tính vào một chuỗi dài theo cú pháp properties:

~~~bash
java \
  -Dspring.profiles.active=prod \
  -Dserver.port=9091 \
  -Dapp.client.connect-timeout=1500ms \
  -Dapp.feature.audit-enabled=true \
  -jar order-service.jar
~~~

Dấu `\` cuối dòng trên là cách nối lệnh của shell Unix-like, **không phải cú pháp độc lập của Java**. Lệnh tương đương trên một dòng:

~~~bash
java -Dspring.profiles.active=prod -Dserver.port=9091 -Dapp.client.connect-timeout=1500ms -Dapp.feature.audit-enabled=true -jar order-service.jar
~~~

Nếu dùng PowerShell, có thể viết một dòng như trên. Khi muốn ngắt dòng trong PowerShell, dấu nối lệnh là backtick của PowerShell, không phải dấu `\` kiểu Bash. Với Windows Command Prompt, cú pháp nối dòng lại khác. Vì vậy ví dụ một dòng thường dễ sao chép và ít phụ thuộc shell hơn.

Các thuộc tính có thể phục vụ những mục đích khác nhau:

| System property | Ai sử dụng | Minh họa |
| --- | --- | --- |
| `spring.profiles.active` | Spring Boot xử lý profile | `dev`, `prod` |
| `server.port` | Spring Boot web server configuration | `9091` |
| `spring.application.name` | Spring Boot/application metadata | `order-service` |
| `app.client.connect-timeout` | Bean cấu hình riêng của ứng dụng | `1500ms` |
| `user.timezone` | Các thành phần Java/JDK liên quan đến múi giờ mặc định | `UTC` |

Không phải property nào bắt đầu bằng `java.`, `user.` hoặc `app.` cũng được Spring Boot xử lý cùng một cách. Những key của JVM/JDK có thể ảnh hưởng đến runtime ngay cả khi mã Spring Boot không trực tiếp đọc chúng.

## 5. -D và biến môi trường không phải cùng một cơ chế

Trong ngữ cảnh cấu hình ứng dụng, có ba nguồn thường được nhắc cùng nhau:

1. **Biến môi trường của hệ điều hành**: tên và giá trị được tiến trình kế thừa từ môi trường chạy.
2. **JVM system properties**: key/value thuộc `System.getProperties()` của tiến trình Java, thường được thiết lập bằng `-D`.
3. **Đối số ứng dụng Spring Boot**: tham số `--key=value` được truyền vào hàm `main(String[] args)` và được Spring Boot đọc.

Ví dụ cùng muốn đặt cổng 9091:

~~~bash
# A. Linux/macOS: biến môi trường
SERVER_PORT=9091 java -jar order-service.jar

# B. JVM system property
java -Dserver.port=9091 -jar order-service.jar

# C. Spring Boot command-line argument
java -jar order-service.jar --server.port=9091
~~~

Ba cách có thể làm ứng dụng Spring Boot dùng cổng 9091, nhưng nơi lưu giá trị và cơ chế đọc là khác nhau.

| Khía cạnh | Biến môi trường | JVM -D | Spring Boot -- |
| --- | --- | --- | --- |
| Ví dụ | `SERVER_PORT=9091` | `-Dserver.port=9091` | `--server.port=9091` |
| Ai nhận đầu tiên | Môi trường tiến trình | Java launcher/JVM | Hàm main/ứng dụng |
| Java thuần đọc bằng | `System.getenv("SERVER_PORT")` | `System.getProperty("server.port")` | `args[]` hoặc parser riêng |
| Spring Boot đọc trong Environment | Có, dưới dạng system environment | Có, dưới dạng Java system properties | Có, nếu xử lý command-line properties được bật |
| Vị trí với -jar | Ngoài câu lệnh Java hoặc do shell cấp | Trước `-jar` | Sau tên JAR |

Cần hiểu đúng: **`System.getenv("SERVER_PORT")` không đọc giá trị do `-Dserver.port=9091` tạo ra**. Ngược lại, **`System.getProperty("server.port")` không tự đọc `SERVER_PORT`**. Spring Boot cung cấp `Environment` để thống nhất tra cứu giữa các nguồn theo cơ chế của nó.

Biến môi trường có tên như `SERVER_PORT` thường được Spring Boot ánh xạ theo quy tắc tên thuộc tính của môi trường. Đối với các nhóm cấu hình phức tạp, nên dùng tên key canonical `kebab-case` trong properties và các quy tắc đặt tên biến môi trường theo tài liệu Spring Boot.

## 6. Java system property là gì?

Mỗi tiến trình JVM có tập system properties biểu diễn bởi lớp `java.lang.System`. Có thể đọc một key:

~~~java
String port = System.getProperty("server.port");
System.out.println(port);
~~~

Trong một chương trình Java không cần Spring, thử ví dụ:

~~~java
public class SystemPropertyDemo {
    public static void main(String[] args) {
        System.out.println("server.port = "
            + System.getProperty("server.port"));
        System.out.println("feature = "
            + System.getProperty("app.feature.enabled"));
    }
}
~~~

Biên dịch:

~~~bash
javac SystemPropertyDemo.java
~~~

Chạy:

~~~bash
java -Dserver.port=9091 -Dapp.feature.enabled=true SystemPropertyDemo
~~~

Kết quả minh họa:

~~~text
server.port = 9091
feature = true
~~~

Đối với chạy theo class thay vì JAR, `-D` cũng phải đứng trong phần tùy chọn Java **trước tên class chính**:

~~~bash
java -Dserver.port=9091 -cp build/classes/java/main com.example.demo.Main
~~~

Nếu đặt `-Dserver.port=9091` sau `com.example.demo.Main`, nó sẽ là đối số của chương trình, chứ không phải tùy chọn Java launcher. Như vậy quy tắc chung là **`-D` phải ở trước mục tiêu chạy**: tên class chính, tên module hay `-jar` tùy kiểu lệnh Java đang sử dụng.

### Khác gì với giá trị cấu hình Spring Boot?

`System.getProperty("server.port")` đọc trực tiếp **JVM system properties**. Nó không đi qua mọi nguồn cấu hình của Spring Boot. Trong khi đó, `Environment.getProperty("server.port")` đọc giá trị hiệu lực theo thứ tự `PropertySource` mà Spring đã thiết lập.

Vì thế, khi một key được khai báo trong `application.yml` nhưng không có JVM `-D`, có thể xảy ra:

~~~text
System.getProperty("server.port")      -> null
Environment.getProperty("server.port") -> "8080"
~~~

Đó là hành vi bình thường: tệp YAML được Spring Boot nạp vào `Environment`, nhưng không có yêu cầu tự động sao chép mọi key YAML vào `System.getProperties()`.

Ngược lại, khi truyền `-Dserver.port=9091`, lệnh `System.getProperty("server.port")` có thể trả `9091`, còn `Environment` có thể trả giá trị khác nếu tồn tại một property source có độ ưu tiên cao hơn, chẳng hạn đối số Spring Boot `--server.port=8085`.

## 7. Ví dụ Spring Boot đọc thuộc tính từ -D

Giả sử `src/main/resources/application.properties` có:

~~~properties
spring.application.name=order-service
server.port=8080

app.client.connect-timeout=3s
app.feature.audit-enabled=false
~~~

Tạo một component đọc cấu hình hiệu lực:

~~~java
import java.time.Duration;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RuntimeSettingsReader {
    private final Environment environment;

    public RuntimeSettingsReader(Environment environment) {
        this.environment = environment;
    }

    public Duration clientTimeout() {
        return environment.getProperty(
            "app.client.connect-timeout", Duration.class);
    }

    public boolean auditEnabled() {
        return Boolean.TRUE.equals(environment.getProperty(
            "app.feature.audit-enabled", Boolean.class, false));
    }
}
~~~

Chạy JAR:

~~~bash
java -Dserver.port=9091 -Dapp.client.connect-timeout=1s -Dapp.feature.audit-enabled=true -jar order-service.jar
~~~

Nếu không có nguồn cao ưu tiên hơn ghi đè, kết quả các key mà Spring Boot nhìn thấy là:

| Key | application.properties | JVM -D | Giá trị hiệu lực |
| --- | --- | --- | --- |
| `server.port` | `8080` | `9091` | `9091` |
| `app.client.connect-timeout` | `3s` | `1s` | `1s` |
| `app.feature.audit-enabled` | `false` | `true` | `true` |

Cần lưu ý: `-Dapp.feature.audit-enabled=true` **chỉ có tác dụng nghiệp vụ khi ứng dụng sử dụng thuộc tính này**. Đối với `server.port`, Spring Boot web server có cơ chế sử dụng sẵn trong loại ứng dụng web phù hợp. Đối với key `app.*`, bạn phải tự định nghĩa consumer.

## 8. Đọc nhóm -D bằng @ConfigurationProperties

Với một nhóm key có cùng prefix, bean có kiểu giúp tránh rải tên chuỗi trong khắp mã:

~~~properties
# application.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
app.client.max-retries=2
~~~

Khai báo:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

Đăng ký bean cấu hình trong ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderServiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderServiceApplication.class, args);
    }
}
~~~

Chạy:

~~~bash
java -Dapp.client.base-url=https://internal.example.test -Dapp.client.connect-timeout=500ms -Dapp.client.max-retries=5 -jar order-service.jar
~~~

Binder có thể ánh xạ các key canonical như `base-url`, `connect-timeout`, `max-retries` sang `baseUrl`, `connectTimeout` và `maxRetries`. Các giá trị `500ms` hoặc `5` được chuyển thành `Duration` và `int` phù hợp. Đối tượng `ClientProperties` đại diện cho **giá trị hiệu lực**, không chỉ dữ liệu từ file mặc định.

Bản thân định dạng `-D` không mang kiểu `Duration` hay `boolean`. Các value được đưa vào tập system properties dưới dạng chuỗi; Spring Boot quyết định phép chuyển kiểu khi nó bind các giá trị vào thuộc tính Java.

## 9. -Dspring.profiles.active: chọn profile trước khi nạp cấu hình theo profile

Một trường hợp rất phổ biến là truyền active profile ở thời điểm khởi động:

~~~bash
java -Dspring.profiles.active=dev -jar order-service.jar
~~~

Khi đó Spring Boot biết cần xét profile `dev`. Nếu có `application-dev.yml` hoặc tài liệu Config Data được kích hoạt bởi `dev`, chúng có thể được nạp theo cơ chế cấu hình.

Ví dụ tệp cơ sở:

~~~yaml
# application.yml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
~~~

Tệp theo profile:

~~~yaml
# application-dev.yml
app:
  client:
    base-url: http://localhost:8090
    connect-timeout: 500ms
~~~

Chạy:

~~~bash
java -Dspring.profiles.active=dev -jar order-service.jar
~~~

Nếu không có nguồn cao hơn ghi đè các key client, ứng dụng dùng giá trị dành cho `dev`. Đối số JVM `-Dspring.profiles.active=dev` là cách hợp lệ để quyết định profile từ **nguồn khởi động**, giúp tránh phải đặt `spring.profiles.active` trong chính tài liệu profile-specific.

Một cách tương đương về ý định đối với Spring Boot là:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Tuy nhiên, cách thứ hai là **Spring Boot application argument**. Nếu ứng dụng cần đọc trực tiếp `System.getProperty("spring.profiles.active")`, thì chỉ truyền `--spring.profiles.active=dev` không tự bảo đảm system property JVM có giá trị. Với phần lớn mã Spring Boot, dùng `Environment.getActiveProfiles()` hoặc cấu hình đã bind là phù hợp hơn.

## 10. Quy tắc precedence khi nhiều nguồn cùng đặt một key

Giả sử `application.yml` có:

~~~yaml
server:
  port: 8080
~~~

Tiến trình có biến môi trường:

~~~bash
SERVER_PORT=8081
~~~

Và chạy bằng:

~~~bash
java -Dserver.port=8082 -jar order-service.jar --server.port=8083
~~~

Trong tình huống Spring Boot thông thường, nếu không có thiết lập đặc biệt về thứ tự property source, chuỗi ưu tiên tương ứng khiến giá trị hiệu lực là **8083**:

| Nguồn | Giá trị `server.port` | Vai trò trong ví dụ |
| --- | --- | --- |
| `application.yml` | `8080` | Giá trị mặc định của ứng dụng |
| Biến môi trường `SERVER_PORT` | `8081` | Ghi đè cấu hình tệp |
| Java system property `-Dserver.port` | `8082` | Ghi đè biến môi trường |
| Đối số Spring Boot `--server.port` | `8083` | Ghi đè các nguồn trên |

Bảng này minh họa các nguồn thường gặp, không phải toàn bộ danh sách precedence của Spring Boot. Test properties, `SPRING_APPLICATION_JSON`, DevTools, cấu hình import và các cơ chế khác có thể tham gia khi phù hợp.

Nhận định quan trọng: **`-D` có ưu tiên cao hơn file cấu hình thông thường, nhưng không phải luôn là nguồn cuối cùng thắng mọi giá trị**. Nếu đối số `--key=value` đang có độ ưu tiên cao hơn, `Environment` có thể trả một value khác với `System.getProperty(key)`.

## 11. Dấu cách và dấu nháy khi value chứa nhiều từ

`-Dkey=value` phải được shell chuyển thành **một đối số** cho Java launcher. Nếu value chứa dấu cách, hãy quote cả tùy chọn:

~~~bash
java "-Dapp.display-name=Order Service" -jar order-service.jar
~~~

Đây là cách dễ hiểu, phù hợp với các shell phổ biến. Trong Bash, có thể dùng dấu nháy đơn để bảo vệ nội dung khỏi nhiều phép mở rộng của shell:

~~~bash
java '-Dapp.display-name=Order Service' -jar order-service.jar
~~~

Với PowerShell, dạng có dấu nháy cũng giúp biểu đạt ý định truyền giá trị chứa khoảng trắng:

~~~powershell
java '-Dapp.display-name=Order Service' -jar order-service.jar
~~~

Java nhận key `app.display-name` và value `Order Service` sau khi shell xử lý phần quote theo đúng quy tắc của nó.

Đừng chèn khoảng trắng quanh dấu `=` trong dạng cơ bản:

~~~bash
# Không đúng dạng một tùy chọn JVM duy nhất
java -Dserver.port = 9091 -jar order-service.jar
~~~

Shell có thể tách thành nhiều đối số, làm Java nhận một tùy chọn khác với dự định hoặc hiểu sai vị trí ứng dụng.

### Cẩn trọng với ký tự đặc biệt

Các ký tự `$`, `&`, `;`, `*`, dấu nháy, backslash và nhiều ký tự khác có thể có ý nghĩa riêng với shell. Câu lệnh sau có thể không truyền value như bạn tưởng nếu không quote:

~~~bash
java -Dapp.url=https://example.test/search?x=1&y=2 -jar order-service.jar
~~~

Trong một số shell, ký tự `&` có tác dụng điều khiển tiến trình. Cách biểu đạt an toàn hơn là quote đối số theo cú pháp shell đang dùng:

~~~bash
java '-Dapp.url=https://example.test/search?x=1&y=2' -jar order-service.jar
~~~

Chọn quy tắc quote phù hợp với Bash, PowerShell, CMD hoặc công cụ triển khai thực tế. Trong những tệp cấu hình dạng YAML của container, phần tử của mảng command/args thường được truyền trực tiếp như các đối số, không đi qua shell, trừ khi bạn chủ động chạy qua `sh -c` hoặc cơ chế tương tự.

## 12. Truyền bằng script Bash và PowerShell

### Bash: đặt biến trong script rồi truyền -D

~~~bash
#!/usr/bin/env bash

APP_PORT=9091
APP_PROFILE=dev

java "-Dserver.port=$APP_PORT" "-Dspring.profiles.active=$APP_PROFILE" -jar order-service.jar
~~~

Shell mở rộng biến `APP_PORT` và `APP_PROFILE` trước khi gọi Java. Java launcher chỉ thấy các đối số như `-Dserver.port=9091` và `-Dspring.profiles.active=dev`. Đây vẫn là **system properties**, dù giá trị gốc của chúng được lưu trong các biến của shell.

Nếu muốn dùng **biến môi trường trực tiếp**, có thể export `SERVER_PORT` hoặc `SPRING_PROFILES_ACTIVE` rồi chạy Java mà không thêm `-D`. Hai con đường khác nhau nhưng Spring Boot đều có thể đọc.

### PowerShell: tạo biến rồi gọi Java

~~~powershell
$appPort = "9091"
$appProfile = "dev"

java "-Dserver.port=$appPort" "-Dspring.profiles.active=$appProfile" -jar order-service.jar
~~~

Chuỗi đặt trong dấu nháy kép được PowerShell nội suy biến. Sau nội suy, Java nhận mỗi `-Dkey=value` dưới dạng một argument. Nếu cần gửi literal chứa ký tự đặc biệt trong PowerShell, điều chỉnh cách quote cho phù hợp.

### Windows CMD: ví dụ một dòng

~~~bat
java "-Dserver.port=9091" "-Dspring.profiles.active=dev" -jar order-service.jar
~~~

CMD có quy tắc xử lý dấu nháy và biến môi trường khác Bash/PowerShell. Nếu chạy qua batch file, tên biến theo cú pháp `%NAME%`; không copy nguyên `$NAME` từ Bash sang CMD.

## 13. Truyền -D trong IDE: JVM arguments khác program arguments

Nhiều IDE có hai ô riêng khi cấu hình chạy ứng dụng Java hoặc Spring Boot:

- **VM options / JVM arguments:** tham số gửi cho Java launcher/JVM.
- **Program arguments / application arguments:** tham số gửi cho chương trình `main(String[] args)`.

Nếu muốn dùng `-Dserver.port=9091`, đặt nó trong **VM options**, ví dụ:

~~~text
-Dserver.port=9091
-Dspring.profiles.active=dev
~~~

Nếu muốn dùng Spring Boot command-line properties `--server.port=9091`, đặt chúng trong **Program arguments**:

~~~text
--server.port=9091
--spring.profiles.active=dev
~~~

Đặt `-D...` trong Program arguments tương tự lỗi đặt sau tên JAR: JVM sẽ không tự biến nó thành system property.

Ví dụ một run configuration của IDE có thể được diễn đạt:

| Vùng cấu hình | Giá trị |
| --- | --- |
| Main class | `com.example.orders.OrderServiceApplication` |
| VM options | `-Dserver.port=9091 -Dspring.profiles.active=dev` |
| Program arguments | `--app.client.connect-timeout=500ms` |

Trong trường hợp này, cổng và profile đến từ JVM system properties, còn timeout đến từ Spring Boot application arguments. Giá trị hiệu lực vẫn chịu quy tắc ưu tiên cấu hình nếu cùng key được định nghĩa từ nhiều nguồn.

## 14. Truyền -D khi chạy qua Gradle bootRun

Nếu chạy trực tiếp một JAR bằng `java -jar`, thứ tự tham số dễ quan sát. Với `bootRun` của Spring Boot Gradle plugin, **Gradle là tiến trình khởi chạy một JVM ứng dụng riêng** theo cấu hình task, nên cần phân biệt tùy chọn JVM của Gradle và JVM của ứng dụng.

Ví dụ:

~~~bash
./gradlew -Dserver.port=9091 bootRun
~~~

Dòng này đặt system property `server.port` cho tiến trình JVM dùng để chạy Gradle. **Không nên giả định** thuộc tính đó sẽ tự động được chuyển vào JVM của ứng dụng do task `bootRun` fork. Kết quả phụ thuộc task/plugin có cấu hình chuyển tiếp system properties hay không.

Cách rõ ràng hơn nếu muốn chuyển một **application argument của Spring Boot** qua bootRun là:

~~~bash
./gradlew bootRun --args='--server.port=9091'
~~~

Lệnh trên đặt tham số chương trình `--server.port=9091` cho Spring Boot, không phải `-D` JVM.

Nếu thực sự muốn đặt **JVM system property** cho JVM mà `bootRun` chạy, có thể cấu hình JVM arguments của task trong Gradle Groovy DSL:

~~~groovy
tasks.named('bootRun') {
    jvmArgs '-Dserver.port=9091'
    jvmArgs '-Dspring.profiles.active=dev'
}
~~~

Khi Gradle chạy task `bootRun`, các tùy chọn `-D` được chuyển thành JVM arguments của ứng dụng. Đây là một ví dụ minh họa cách cấu hình task `JavaExec`/`BootRun`; cấu hình Gradle thực tế của dự án có thể có quy ước riêng, vì vậy phải đặt đoạn DSL vào đúng project/module sở hữu task.

Đừng nhầm `--args='--...'` của Gradle với `-D...` của Gradle. Một cái truyền đối số cho chương trình, còn cái kia đặt thuộc tính JVM của tiến trình Gradle trừ khi task chuyển tiếp.

## 15. Dùng -D với Docker hoặc container

Với một JAR chạy trong Docker, có thể đặt JVM option trực tiếp trong `ENTRYPOINT` dạng mảng:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app

COPY build/libs/order-service.jar /app/order-service.jar

ENTRYPOINT ["java", "-Dserver.port=9091", "-Dspring.profiles.active=prod", "-jar", "/app/order-service.jar"]
~~~

Dạng mảng truyền từng phần tử thành một đối số của chương trình. `-Dserver.port=9091` và `-Dspring.profiles.active=prod` nằm **trước `-jar`**, nên Java launcher xử lý chúng.

Nếu lỡ viết:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/order-service.jar", "-Dserver.port=9091"]
~~~

thì `-Dserver.port=9091` được chuyển thành đối số ứng dụng; không phải system property do Java launcher thiết lập.

Đối với container triển khai ở nhiều môi trường, hardcode profile hoặc port ngay trong image có thể làm cùng một image khó tái sử dụng. Một cách khác là cấp môi trường lúc chạy:

~~~bash
docker run --rm -e SERVER_PORT=9091 -e SPRING_PROFILES_ACTIVE=prod order-service:latest
~~~

Biến môi trường này được Spring Boot nhận qua system environment nếu container/image chạy ứng dụng đúng cách. Đây là cơ chế riêng với JVM `-D`; không cần thêm `-D` chỉ để mọi biến môi trường có hiệu lực.

Trong Kubernetes, phần `command`/`args` có thể quy định những đối số cho container runtime. Nếu danh sách bắt đầu bằng `java`, bảo đảm các phần tử `-D...` được đặt trước `-jar`. Nếu chỉ ghi `args` mà image có `ENTRYPOINT` sẵn, hãy hiểu chính xác lệnh cuối được tạo ra trước khi kết luận `-D` nằm ở vị trí nào.

## 16. JAVA_TOOL_OPTIONS, JDK_JAVA_OPTIONS và JAVA_OPTS

Có thể bạn thấy các tên biến như `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` hoặc `JAVA_OPTS` trong tài liệu triển khai. Chúng **không có ý nghĩa giống nhau**.

- **`JAVA_TOOL_OPTIONS`:** một số tùy chọn JVM, trong đó có system property `-D`, có thể được JVM tiếp nhận từ biến môi trường này. Phạm vi và hạn chế phụ thuộc cách khởi tạo JVM.
- **`JDK_JAVA_OPTIONS`:** trên các phiên bản JDK hỗ trợ, Java launcher có thể nhận những tùy chọn bổ sung từ biến môi trường này, với các giới hạn cho những option chọn mục tiêu ứng dụng.
- **`JAVA_OPTS`:** đây **không phải** cơ chế mà bản thân lệnh `java` mặc định tự động đọc theo một chuẩn chung. Nhiều script, image hoặc công cụ triển khai có quy ước dùng tên biến này, nhưng chỉ có hiệu lực nếu entrypoint/script của hệ thống chủ động chèn nội dung của nó vào lệnh Java.

Ví dụ người vận hành có thể thiết lập:

~~~bash
export JAVA_TOOL_OPTIONS='-Duser.timezone=UTC'
java -jar order-service.jar
~~~

Trong môi trường JVM hỗ trợ, thuộc tính `user.timezone` có thể được đưa vào JVM mà không cần ghi trực tiếp trên dòng lệnh. Tuy nhiên, với một bài học yêu cầu **nắm chắc vị trí `-D` trước `-jar`**, dạng tường minh sau dễ quan sát và gỡ lỗi hơn:

~~~bash
java -Duser.timezone=UTC -jar order-service.jar
~~~

Không truyền tên biến bí mật hoặc giá trị mật khẩu bằng một cơ chế chỉ vì nó hỗ trợ `-D`. Những giá trị trong command-line, script, cấu hình container hay log có thể bị lộ qua công cụ quan sát tiến trình hoặc lịch sử lệnh. Dùng hệ thống quản lý secrets và quyền truy cập phù hợp khi triển khai thật.

## 17. System properties có thay đổi được sau khi JVM khởi động không?

Có thể đọc và thay system properties bằng Java API:

~~~java
System.setProperty("app.feature.enabled", "true");
String value = System.getProperty("app.feature.enabled");
~~~

Điều này **không có nghĩa Spring Boot sẽ tự khởi tạo lại những bean đã bind cấu hình**. Một bean `@ConfigurationProperties` thường được bind trong vòng đời khởi tạo, còn việc nạp Config Data theo profile là công việc của giai đoạn startup. Nếu bạn thay một system property sau khi ứng dụng chạy, mã `System.getProperty` hoặc một consumer đọc `Environment` vào thời điểm mới có thể thấy thay đổi trong tình huống phù hợp, nhưng những quyết định bean hoặc cấu hình đã áp dụng từ trước không tự động bị tính lại.

Cũng cần phân biệt system properties trong **cùng một tiến trình JVM**. Nếu hai ứng dụng Java chạy trong hai process độc lập, mỗi process có `System.getProperties()` riêng. Cấu hình `-D` của process A không trực tiếp ghi đè process B.

Đối với các thuộc tính JDK được đọc rất sớm, việc thay sau startup có thể không thay đổi hành vi đã được khởi tạo. Vì thế hãy xem `-D` như cấu hình khởi động có chủ đích, không như cơ chế cập nhật động toàn bộ ứng dụng.

## 18. Lỗi thường gặp và cách sửa

### Lỗi 1 — Đặt -D sau JAR

~~~bash
# Sai nếu muốn tạo JVM system property
java -jar order-service.jar -Dserver.port=9091
~~~

**Sửa:**

~~~bash
java -Dserver.port=9091 -jar order-service.jar
~~~

Nếu mục tiêu chỉ là cung cấp một property cho Spring Boot, có thể chọn:

~~~bash
java -jar order-service.jar --server.port=9091
~~~

### Lỗi 2 — Có khoảng trắng sau -D

~~~bash
# Sai dạng tùy chọn
java -D server.port=9091 -jar order-service.jar
~~~

**Sửa:** viết liền `-Dserver.port=9091`, không tách thành hai argument.

### Lỗi 3 — Nhầm key của system property và biến môi trường

~~~bash
java -DSERVER_PORT=9091 -jar order-service.jar
~~~

Lệnh này tạo một **system property tên `SERVER_PORT`**, không tạo biến môi trường `SERVER_PORT`. Không nên suy luận nó tương đương `-Dserver.port=9091` chỉ vì hai cách viết nhìn gần giống nhau. Khi truyền system property cho Spring Boot, hãy ưu tiên tên canonical:

~~~bash
java -Dserver.port=9091 -jar order-service.jar
~~~

Khi dùng biến môi trường, đặt tên biến theo quy tắc riêng của system environment:

~~~bash
SERVER_PORT=9091 java -jar order-service.jar
~~~

### Lỗi 4 — Dùng -D ở Gradle rồi cho rằng bootRun luôn nhận được

~~~bash
./gradlew -Dspring.profiles.active=dev bootRun
~~~

Dòng này cấu hình JVM dùng bởi Gradle, không tự chứng minh JVM chạy Spring Boot nhận property. **Sửa:** truyền `--spring.profiles.active=dev` qua `bootRun --args` hoặc cấu hình `jvmArgs` của `bootRun`.

### Lỗi 5 — Gửi -D vào Program arguments của IDE

VM options và Program arguments là hai vùng khác nhau. **Sửa:** chuyển `-D...` sang VM options, hoặc đổi thành `--key=value` trong Program arguments nếu mục tiêu là Spring Boot property.

### Lỗi 6 — Không quote value có dấu cách hoặc ký tự shell đặc biệt

~~~bash
java -Dapp.display-name=Order Service -jar order-service.jar
~~~

Shell có thể tách `Service` thành argument riêng, làm câu lệnh bị hiểu sai. **Sửa:**

~~~bash
java "-Dapp.display-name=Order Service" -jar order-service.jar
~~~

### Lỗi 7 — Bị nguồn khác ghi đè

~~~bash
java -Dserver.port=9091 -jar order-service.jar --server.port=9092
~~~

Dù `System.getProperty("server.port")` có thể trả `9091`, Spring Boot `Environment` trong ví dụ thường dùng `9092` do command-line property ưu tiên hơn. **Sửa:** kiểm tra tất cả nguồn và quyền ưu tiên, thay vì kết luận `-D` không được Java đọc.

### Lỗi 8 — Truyền key ứng dụng nhưng không có mã tiêu thụ

~~~bash
java -Dapp.feature.special-mode=true -jar order-service.jar
~~~

Không có cơ chế tự động nào bảo đảm tính năng `special-mode` xuất hiện nếu ứng dụng không có code, điều kiện hoặc bean dùng key này. **Sửa:** xác định consumer và cách binding tương ứng.

### Lỗi 9 — Truyền giá trị không hợp kiểu

~~~bash
java -Dserver.port=not-a-port -jar order-service.jar
~~~

Lệnh có thể hợp cú pháp Java, nhưng Spring Boot không thể chuyển chuỗi đó thành cổng mạng hợp lệ. **Sửa:** dùng value đúng kiểu và phạm vi, ví dụ một số cổng TCP hợp lệ.

## 19. Tự kiểm chứng bằng System.getProperty và Environment

Một bài thực hành giúp xác định vấn đề nằm ở Java launcher hay Spring Boot.

Thêm một bean trong ứng dụng thử nghiệm:

~~~java
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class PropertyProbeConfiguration {

    @Bean
    CommandLineRunner printPortSources(Environment environment) {
        return args -> {
            System.out.println("JVM system property server.port = "
                + System.getProperty("server.port"));
            System.out.println("Spring Environment server.port = "
                + environment.getProperty("server.port"));
        };
    }
}
~~~

Chỉ dùng probe với key không nhạy cảm. Không in toàn bộ `System.getProperties()` hoặc mọi property của `Environment` vào log production: chúng có thể chứa token, đường dẫn, thông tin hệ thống hoặc dữ liệu bí mật.

### Thí nghiệm A — chỉ có giá trị trong tệp

~~~properties
# application.properties
server.port=8080
~~~

Chạy:

~~~bash
java -jar order-service.jar
~~~

Kết quả có thể là:

~~~text
JVM system property server.port = null
Spring Environment server.port = 8080
~~~

Điều này cho thấy Spring Boot có cấu hình `server.port` từ tệp dù JVM không có system property mang tên đó.

### Thí nghiệm B — -D đúng vị trí

~~~bash
java -Dserver.port=9091 -jar order-service.jar
~~~

Kết quả minh họa:

~~~text
JVM system property server.port = 9091
Spring Environment server.port = 9091
~~~

### Thí nghiệm C — -D nằm sau JAR

~~~bash
java -jar order-service.jar -Dserver.port=9091
~~~

Nếu `application.properties` vẫn chứa `server.port=8080`, kết quả minh họa là:

~~~text
JVM system property server.port = null
Spring Environment server.port = 8080
~~~

Kết quả thể hiện Java launcher không nhận `-D` ở vùng đối số ứng dụng. Giá trị thực còn phụ thuộc những nguồn khác có mặt trong process.

### Thí nghiệm D — hai nguồn cạnh tranh

~~~bash
java -Dserver.port=9091 -jar order-service.jar --server.port=9092
~~~

Kết quả minh họa:

~~~text
JVM system property server.port = 9091
Spring Environment server.port = 9092
~~~

Bảng A–D cho phép truy ra chính xác nơi phát sinh khác biệt: JVM có nhận `-D` không, Spring Boot có đọc được nguồn khác không, và giá trị cuối cùng do precedence quyết định thế nào.

## 20. Các câu hỏi tự luyện

**Câu 1.** Lệnh nào đúng để JVM nhận system property `spring.profiles.active=prod`?

~~~bash
# A
java -jar app.jar -Dspring.profiles.active=prod

# B
java -Dspring.profiles.active=prod -jar app.jar
~~~

**Đáp án:** B. `-D` nằm trước `-jar`.

**Câu 2.** Hai lệnh sau có tạo cùng kiểu nguồn cấu hình không?

~~~bash
java -Dserver.port=9091 -jar app.jar
java -jar app.jar --server.port=9091
~~~

**Đáp án:** không. Lệnh đầu tạo JVM system property, lệnh sau tạo Spring Boot application argument. Trong một ứng dụng Spring Boot chuẩn, cả hai có thể dẫn đến cổng 9091 nếu không có nguồn ghi đè, nhưng nguồn của chúng khác nhau.

**Câu 3.** Vì sao lệnh này không đồng nghĩa với truyền biến môi trường `SERVER_PORT`?

~~~bash
java -DSERVER_PORT=9091 -jar app.jar
~~~

**Đáp án:** nó thiết lập một system property có tên `SERVER_PORT`. Biến môi trường thuộc `System.getenv` và được cấp bằng cơ chế của hệ điều hành/process.

**Câu 4.** Trong `application.properties` có `app.client.connect-timeout=3s`; lệnh khởi động:

~~~bash
java -Dapp.client.connect-timeout=500ms -jar app.jar
~~~

Nếu không có nguồn cao hơn, `Environment.getProperty("app.client.connect-timeout")` trả về gì?

**Đáp án:** `500ms`. Spring Boot nhận system property và đặt nguồn đó cao hơn file cấu hình thông thường.

**Câu 5.** Nếu thêm vào cuối câu lệnh trên `--app.client.connect-timeout=1s` thì giá trị hiệu lực dự kiến là gì?

**Đáp án:** `1s` trong tình huống Spring Boot mặc định, do command-line property có ưu tiên cao hơn JVM system property.

**Câu 6.** Vì sao `./gradlew -Dserver.port=9091 bootRun` chưa phải bằng chứng rằng Spring Boot lắng nghe cổng 9091?

**Đáp án:** `-D` có thể đang đặt cho JVM của Gradle; task `bootRun` chạy ứng dụng ở một JVM riêng. Phải truyền JVM args cho `bootRun` hoặc dùng `bootRun --args='--server.port=9091'`.

**Câu 7.** Với Java thuần chạy qua class name, cú pháp nào đúng?

~~~bash
java -Dapp.mode=test -cp out com.example.Main
~~~

**Đáp án:** đúng; `-D` đứng trước tên main class, còn `-cp out` cung cấp classpath.

**Câu 8.** Cách nào đọc system property JVM trực tiếp?

~~~java
System.getProperty("server.port");
System.getenv("SERVER_PORT");
~~~

**Đáp án:** lời gọi đầu. Lời gọi thứ hai đọc biến môi trường hệ điều hành.

## 21. Bảng ghi nhớ nhanh

| Nhu cầu | Mẫu thực hiện |
| --- | --- |
| Truyền JVM property khi chạy JAR | `java -Dkey=value -jar app.jar` |
| Truyền nhiều system properties | `java -Da=1 -Db=2 -jar app.jar` |
| Chọn Spring profile qua JVM | `java -Dspring.profiles.active=prod -jar app.jar` |
| Đặt cổng qua JVM | `java -Dserver.port=9091 -jar app.jar` |
| Truyền Spring Boot argument sau JAR | `java -jar app.jar --server.port=9091` |
| Đọc JVM property trong Java | `System.getProperty("server.port")` |
| Đọc biến môi trường trong Java | `System.getenv("SERVER_PORT")` |
| Đọc giá trị hiệu lực trong Spring | `environment.getProperty("server.port")` |
| Truyền qua VM options của IDE | `-Dserver.port=9091` |
| Truyền program argument của IDE | `--server.port=9091` |
| Truyền argument cho bootRun | `./gradlew bootRun --args='--server.port=9091'` |
| Truyền -D cho JVM của bootRun | Cấu hình `jvmArgs '-Dserver.port=9091'` trong task |
| Đặt -D trong Docker ENTRYPOINT | `["java", "-Dserver.port=9091", "-jar", "/app/app.jar"]` |

Quy tắc có thể áp dụng ngay khi đọc lệnh chạy:

> **Để Java launcher thiết lập system property, viết `java -Dkey=value -jar app.jar`. Để Spring Boot nhận đối số ứng dụng, viết `java -jar app.jar --key=value`. Muốn kiểm chứng, so sánh `System.getProperty(key)` với `Environment.getProperty(key)` và xét thứ tự ưu tiên nguồn.**

Khi tách rõ **biến môi trường**, **JVM system property** và **Spring Boot command-line property**, bạn có thể chọn đúng cách truyền cấu hình, đặt tham số đúng vị trí và xác định nguyên nhân nếu ứng dụng không nhận giá trị mong đợi.

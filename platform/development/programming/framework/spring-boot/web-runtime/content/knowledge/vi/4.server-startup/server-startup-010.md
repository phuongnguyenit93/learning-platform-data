# Chẩn đoán thiếu WebServerFactory hoặc cổng đã được sử dụng

## 1. Mục tiêu và cách đọc lỗi khởi động

Spring Boot có thể khởi tạo thành công nhiều bean ứng dụng nhưng vẫn không mở được HTTP server. Hai nhóm lỗi dễ gặp khi chạy ứng dụng web là:

1. **Thiếu WebServerFactory**: ApplicationContext cần tạo embedded HTTP server nhưng không tìm thấy bean factory có khả năng tạo server tương ứng với loại web application.
2. **Cổng hoặc địa chỉ không bind được**: factory và embedded server đã được chọn, nhưng tiến trình không thể lắng nghe trên địa chỉ IP/cổng được yêu cầu.

Hai lỗi đều có thể dẫn đến ApplicationContext startup failed, nhưng **nguyên nhân gốc và hướng xử lý khác nhau**. Không nên kết luận chỉ từ dòng cuối như Application run failed. Hãy đọc chuỗi Caused by, xác định Servlet hay Reactive stack, rồi kiểm tra dependency và trạng thái cổng theo đúng thứ tự.

Bài này dùng Spring Boot 3.3.x với Java 17+, tập trung vào embedded web server trong ứng dụng Spring MVC và Spring WebFlux. Ví dụ Gradle và lệnh chạy là các tình huống học tập độc lập; cần điều chỉnh đường dẫn và cổng nếu dự án của bạn khác cấu trúc minh họa.

Sau bài học, bạn có thể:

- Phân biệt thiếu ServletWebServerFactory và ReactiveWebServerFactory.
- Giải thích khi nào Boot tạo factory và vì sao một dependency bị loại có thể làm ứng dụng không khởi động.
- Đọc đúng nguyên nhân một lỗi bind port thay vì chỉ dựa vào thông báo chung.
- Tìm tiến trình đang lắng nghe cổng trên Windows, Linux và macOS.
- Sửa cấu hình hoặc dependency, khởi động lại và kiểm chứng bằng một HTTP request thật.
- Tránh những cách chữa giả như vô tình tắt web server hoặc giết nhầm tiến trình.

## 2. Mô hình: từ ApplicationContext đến socket lắng nghe

Khi SpringApplication.run bắt đầu, Boot xác định loại ứng dụng web, xử lý cấu hình, tạo ApplicationContext, dựng các bean và khởi động server nếu loại ứng dụng cần server.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["SpringApplication.run"] --> B{"WebApplicationType?"}
    B -->|SERVLET| C["Servlet web ApplicationContext"]
    B -->|REACTIVE| D["Reactive web ApplicationContext"]
    B -->|NONE| E["Non-web context; không mở HTTP server"]
    C --> F["Tìm ServletWebServerFactory"]
    D --> G["Tìm ReactiveWebServerFactory"]
    F --> H{"Có factory phù hợp?"}
    G --> I{"Có factory phù hợp?"}
    H -->|Không| J["Lỗi thiếu WebServerFactory"]
    I -->|Không| J
    H -->|Có| K["Tạo embedded server"]
    I -->|Có| K
    K --> L{"Bind địa chỉ và cổng thành công?"}
    L -->|Không| M["BindException / Port already in use / lỗi địa chỉ"]
    L -->|Có| N["Server lắng nghe và tiếp nhận HTTP request"]
~~~

**WebServerFactory là factory tạo embedded web server, không phải controller, service hay repository**. Với Servlet stack, Boot thường dùng một ServletWebServerFactory để tạo server như Tomcat. Với reactive stack, Boot cần ReactiveWebServerFactory, ví dụ factory dành cho Reactor Netty.

Các class và bean liên quan:

| Loại ứng dụng | Factory Boot cần | Ví dụ triển khai thông dụng | Pipeline HTTP |
| --- | --- | --- | --- |
| SERVLET / Spring MVC | org.springframework.boot.web.servlet.server.ServletWebServerFactory | TomcatServletWebServerFactory | Servlet container, Filter chain, DispatcherServlet |
| REACTIVE / WebFlux | org.springframework.boot.web.reactive.server.ReactiveWebServerFactory | NettyReactiveWebServerFactory | Reactive HTTP server, WebFilter, DispatcherHandler |
| NONE | Không yêu cầu embedded web server factory | Không áp dụng | Không tự phục vụ HTTP |

Có factory vẫn chưa bảo đảm cổng sẽ mở thành công: hệ điều hành có thể từ chối bind sau khi server được tạo. Ngược lại, lỗi thiếu factory có thể xuất hiện **trước** bước bind cổng, nên chuyển server.port sang 8081 không giải quyết thiếu dependency.

## 3. Nhận diện hai nhóm lỗi qua thông điệp

### 3.1 Thiếu WebServerFactory

Thông báo thường gặp trong Servlet application có ý nghĩa tương đương:

~~~text
Unable to start ServletWebServerApplicationContext due to missing ServletWebServerFactory bean.
~~~

Với reactive application, thông điệp tương ứng liên quan đến ReactiveWebServerApplicationContext và ReactiveWebServerFactory.

Thông điệp này nói rằng context đang được khởi động theo một web application type cần embedded server, nhưng Spring không có bean factory thích hợp. Cần kiểm tra:

- Boot đang dùng SERVLET hay REACTIVE?
- Có dependency starter/server nào trên runtimeClasspath?
- Có loại embedded server mặc định rồi quên thay bằng server khác không?
- Có cấu hình exclude auto-configuration hoặc bean/condition đặc biệt không?
- Ứng dụng bị ép web application type không phù hợp với classpath không?

Không suy ra rằng cổng đã bị chiếm: nếu chưa tạo được server, tiến trình chưa đến bước mở cổng.

### 3.2 Cổng đã được sử dụng hoặc bind thất bại

Spring Boot có thể báo:

~~~text
Web server failed to start. Port 8080 was already in use.
~~~

Chuỗi nguyên nhân bên dưới có thể chứa:

~~~text
java.net.BindException: Address already in use
~~~

Thông điệp và cách bọc exception thực tế phụ thuộc server, hệ điều hành và thời điểm lỗi. Một số log cũng có WebServerException, Unable to start embedded Tomcat hoặc lỗi khi start bean webServerStartStop; cần xem **nguyên nhân sâu nhất** để biết có thực sự là lỗi bind.

Những nguyên nhân khác không nên gộp thành “cổng đã được sử dụng”:

- Permission denied: tiến trình không có quyền bind địa chỉ/cổng.
- Cannot assign requested address: server.address trỏ đến IP không thuộc máy hoặc môi trường container.
- Port không hợp lệ hoặc cấu hình không parse được: lỗi cấu hình, không phải xung đột tiến trình.
- Network unreachable hoặc connect refused ở phía client: có thể server chưa chạy, bind sai interface hoặc có vấn đề mạng; chưa đủ chứng minh cổng bị chiếm.

### 3.3 Bảng phân biệt nhanh

| Dấu hiệu | Thiếu factory | Bind port thất bại |
| --- | --- | --- |
| Lúc xảy ra | Khi web context cần bean để tạo server | Khi server đang cố mở socket |
| Từ khóa trong log | missing ServletWebServerFactory / ReactiveWebServerFactory bean | Port ... already in use, BindException, failed to bind |
| Kiểm tra ưu tiên | WebApplicationType, runtimeClasspath, auto-configuration | server.port, server.address, tiến trình LISTEN |
| Đổi port có giúp không? | Không | Có thể, nếu lỗi thật sự là xung đột cổng |
| Thêm starter web server có giúp không? | Có thể, nếu thiếu server implementation | Không giải quyết port đang bị chiếm |
| Mục tiêu sau sửa | Có factory đúng cho stack | Bind thành công và HTTP endpoint hoạt động |

## 4. Bước đầu tiên: đọc exception chain đúng cách

Một log khởi động có thể dài hàng trăm dòng. Hãy ưu tiên:

1. Ghi lại dòng Failure Analysis hoặc dòng mô tả Web server failed to start, nếu có.
2. Tìm Caused by sâu nhất có liên quan, đặc biệt BindException hoặc lỗi missing factory.
3. Xác định chính xác port, địa chỉ, loại server và web stack đang chạy.
4. Kiểm tra có lỗi sớm hơn khiến bean factory không được khởi tạo hay không.
5. Chỉ sau khi phân loại lỗi mới sửa cấu hình hoặc dependency.

Ví dụ hai mô tả tình huống minh họa:

~~~text
Tình huống A:
ApplicationContext cần ServletWebServerFactory nhưng không có bean tương ứng.
=> Kiểm tra embedded Servlet server dependency và auto-configuration.

Tình huống B:
Tomcat/Netty đã được cấu hình nhưng không bind được 0.0.0.0:8080.
=> Kiểm tra tiến trình đang LISTEN trên port 8080 và server.address.
~~~

Đây là diễn giải chẩn đoán, không phải hai stack trace chuẩn cần khớp từng ký tự. Nếu exception gốc khác hai tình huống trên, hãy xử lý đúng nguyên nhân thực tế thay vì ép nó vào một trong hai nhóm.

## 5. Chẩn đoán thiếu ServletWebServerFactory

### 5.1 Điều kiện bình thường

Với một Spring Boot Servlet application đơn giản, dependency thường có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

spring-boot-starter-web thông thường kéo Spring MVC và embedded Tomcat. Spring Boot dùng ServletWebServerFactoryAutoConfiguration với các điều kiện phù hợp để cấu hình một ServletWebServerFactory. Nếu ứng dụng tự định nghĩa factory được hỗ trợ, auto-configuration mặc định có thể nhường quyền.

Khi Boot chọn SERVLET nhưng không tạo được factory, hãy kiểm tra dự án có từng loại Tomcat, Jetty hoặc Undertow đi không.

### 5.2 Ví dụ loại embedded Tomcat mà không bổ sung server khác

Cấu hình minh họa tạo rủi ro thiếu factory:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
}
~~~

Nếu không có embedded Servlet server khác được cung cấp, một ứng dụng được Boot nhận diện là SERVLET sẽ không có factory mặc định để khởi động HTTP server. Việc loại Tomcat chỉ phù hợp khi có server thay thế hoặc khi đóng gói triển khai theo cơ chế khác đã được chủ động thiết kế.

Cách sửa thường gặp: **bỏ exclude** để dùng Tomcat mặc định, hoặc bổ sung một Servlet server starter phù hợp. Ví dụ chọn Jetty:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

Không thêm nhiều embedded server starter chỉ để “chắc chắn có một cái”. Khi dùng lựa chọn khác Tomcat, đọc yêu cầu version và cấu hình tương ứng với Spring Boot đang dùng.

### 5.3 Kiểm tra dependency thực tế

Dự án Gradle nên kiểm tra **runtimeClasspath**, vì web server phải hiện diện lúc chạy:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tập trung vào các dependency như:

~~~text
spring-boot-starter-web
spring-boot-starter-tomcat
spring-boot-starter-jetty
spring-boot-starter-undertow
spring-webmvc
jakarta.servlet-api
~~~

Đây là danh sách dấu hiệu để kiểm tra; không phải mọi dependency đều cần có đồng thời.

Để xem một dependency được kéo vào từ đâu:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
~~~

Nếu dependency chỉ xuất hiện trong testImplementation hoặc compileOnly, chưa chắc nó nằm trong runtime classpath của ứng dụng. Đồng thời kiểm tra các lệnh exclude ở project, dependency management, convention plugin và việc dùng custom runtime configuration.

### 5.4 Đọc Condition Evaluation Report

Khi dependency có vẻ đúng nhưng factory vẫn thiếu, xem các điều kiện auto-configuration:

~~~bash
./gradlew bootRun --args='--debug'
~~~

Tham số --debug ở đây được truyền **vào Spring Boot app** qua --args, nhờ đó ứng dụng có thể in Condition Evaluation Report khi khởi động. Đọc phần liên quan đến:

- ServletWebServerFactoryAutoConfiguration
- Những auto-configuration cụ thể của Tomcat/Jetty/Undertow
- @ConditionalOnClass, @ConditionalOnWebApplication, @ConditionalOnMissingBean
- Các exclude auto-configuration mà ứng dụng đã khai báo

Không nên tự tạo ServletWebServerFactory bean nếu chưa xác định vì sao auto-configuration chuẩn bị bỏ qua. Trong phần lớn ứng dụng thông thường, sửa dependency hoặc loại web application phù hợp sẽ rõ ràng và ít rủi ro hơn.

## 6. Chẩn đoán thiếu ReactiveWebServerFactory

Với một reactive HTTP application, cấu hình thông thường:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

spring-boot-starter-webflux thường có Reactor Netty server. Khi Boot chọn REACTIVE, reactive web context cần ReactiveWebServerFactory thích hợp.

Ví dụ loại Reactor Netty starter:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }
}
~~~

Nếu Boot đang chạy REACTIVE và không có một reactive-capable HTTP server implementation khác, việc thiếu factory có thể khiến khởi động thất bại. Không kết luận WebFlux chỉ cần reactor-core: reactive operator và runtime HTTP server là những vai trò khác nhau.

Để điều tra:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-starter-reactor-netty --configuration runtimeClasspath
~~~

Đồng thời kiểm tra ReactiveWebServerFactoryAutoConfiguration trong Condition Evaluation Report và xem ứng dụng có bị ép sang REACTIVE hay không.

## 7. Xem lại Servlet hay Reactive khi có cả MVC và WebFlux

Khi spring-boot-starter-web và spring-boot-starter-webflux cùng hiện diện trên classpath, **Spring Boot mặc định ưu tiên Spring MVC / SERVLET**. Lý do phổ biến là ứng dụng MVC cần WebClient nhưng không muốn đổi HTTP server stack.

Do đó:

- Có WebClient hoặc Mono/Flux không chứng minh ứng dụng đang chạy reactive server.
- Nếu cả hai starter đều có, hãy kiểm tra thực tế Boot chọn SERVLET hay REACTIVE.
- Dùng spring.main.web-application-type=reactive khi chủ động muốn ứng dụng reactive và đã chuẩn bị dependency/server tương ứng.
- Dùng spring.main.web-application-type=none chỉ khi ứng dụng thật sự không cần HTTP server; đó **không phải** cách sửa hợp lý cho một service được yêu cầu phục vụ REST API.

Ví dụ cấu hình web application type:

~~~properties
spring.main.web-application-type=reactive
~~~

Nếu dự án có cả MVC và WebFlux nhưng lại dùng điều kiện loại trừ server không đúng, lỗi factory có thể là hệ quả gián tiếp của lựa chọn stack. Hãy giải quyết nhất quán cả **loại application context** lẫn **server implementation**.

## 8. Chẩn đoán cổng đã được sử dụng

### 8.1 Xác định cổng và địa chỉ thật sự

Spring Boot thường dùng cổng 8080 nếu không cấu hình khác. Giá trị có thể được đặt trong application.properties/application.yml, environment, profile, command-line arguments hoặc nguồn cấu hình được ưu tiên cao hơn.

Ví dụ:

~~~properties
server.port=8080
server.address=127.0.0.1
~~~

server.address là địa chỉ interface mà web server cố bind. Nếu không đặt, server thường lắng nghe trên các interface phù hợp theo mặc định của môi trường.

Trước khi sửa, kiểm tra log để biết cổng bị lỗi có đúng là 8080 không. Một số ứng dụng chạy nhiều context hoặc Actuator management server ở cổng khác; khi đó cần kiểm tra cả management.server.port và endpoint tương ứng nếu có.

### 8.2 Windows PowerShell

Để tìm kết nối đang ở trạng thái LISTEN trên port 8080:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 8080 |
    Select-Object LocalAddress, LocalPort, State, OwningProcess
~~~

Sau khi có PID, xem tiến trình:

~~~powershell
Get-Process -Id 12345
~~~

Thay 12345 bằng OwningProcess thực tế. Nếu cần đối chiếu đầy đủ command line trên môi trường cho phép:

~~~powershell
Get-CimInstance Win32_Process -Filter "ProcessId = 12345" |
    Select-Object ProcessId, Name, CommandLine
~~~

Trên hệ thống Windows thiếu cmdlet Get-NetTCPConnection, có thể dùng:

~~~powershell
netstat -ano -p tcp | findstr :8080
~~~

Khi đọc netstat, chú ý dòng LISTENING và PID; những kết nối ESTABLISHED hoặc TIME_WAIT không tự chứng minh có tiến trình đang lắng nghe cổng đó. Nếu thiếu quyền xem tiến trình của người dùng khác, hãy hỏi người quản trị thay vì đoán chủ sở hữu.

### 8.3 Linux

Dùng ss để kiểm tra listening socket:

~~~bash
ss -ltnp 'sport = :8080'
~~~

Có thể cần quyền cao hơn để xem PID/process thuộc người dùng khác. Lệnh khác:

~~~bash
lsof -nP -iTCP:8080 -sTCP:LISTEN
~~~

Nếu không tìm thấy tiến trình nghe 8080 nhưng ứng dụng vẫn báo bind failed, kiểm tra server.address, namespace/container, IPv4/IPv6 và nội dung exception gốc.

### 8.4 macOS

~~~bash
lsof -nP -iTCP:8080 -sTCP:LISTEN
~~~

Output hiển thị PID cùng tên process nếu hệ thống cho phép. Không dùng danh sách kết nối client đang kết nối ra ngoài để khẳng định một port local đã bị server khác chiếm.

### 8.5 Kiểm tra trước khi dừng một tiến trình

Nếu PID là một ứng dụng Java khác, có thể đó là phiên bản service đang chạy hoặc một tiến trình do IDE/Gradle khởi động trước đó. Xác định tên process, command line và mục đích sử dụng trước khi dừng.

Đối với ứng dụng chạy bằng IDE, dùng nút Stop hoặc cơ chế lifecycle của IDE. Với terminal Gradle hoặc java -jar, dừng tiến trình đang chạy bằng cơ chế thích hợp, ví dụ Ctrl+C trong chính terminal đó. Tránh giết PID ngẫu nhiên hoặc dừng service của người khác chỉ để giải phóng cổng.

## 9. Ba cách xử lý xung đột port

### Cách A: Dừng đúng tiến trình cũ

Phù hợp khi tiến trình đó là phiên bản ứng dụng thử nghiệm đang chạy dư. Sau khi dừng, kiểm tra port đã được giải phóng rồi khởi động lại.

### Cách B: Chuyển ứng dụng sang port khác

Trong application.properties:

~~~properties
server.port=8081
~~~

Hoặc truyền tham số khi chạy:

~~~bash
./gradlew bootRun --args='--server.port=8081'
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--server.port=8081"
~~~

Cần cập nhật URL client, reverse proxy, health check hoặc cấu hình service discovery nếu môi trường yêu cầu port cố định.

### Cách C: Dùng cổng động khi chạy thử/test

~~~properties
server.port=0
~~~

Khi đó hệ điều hành chọn một port khả dụng. Đây là lựa chọn hữu ích cho test hoặc ứng dụng chạy cục bộ nhiều instance, nhưng client cần biết **port thực tế** mà server đã chọn. Không thể tiếp tục giả định URL localhost:8080. Với Spring Boot integration test, có thể dùng RANDOM_PORT và đọc @LocalServerPort.

Chuyển sang 8081 hoặc 0 chỉ giải quyết tình huống port collision nếu địa chỉ và quyền bind hợp lệ. Nếu lỗi là Cannot assign requested address hoặc Permission denied, cần xử lý nguyên nhân địa chỉ/quyền trước.

## 10. Ví dụ chạy được: tái hiện lỗi port rồi khắc phục

Ví dụ tạo một Spring Boot MVC application nhỏ, trả chuỗi READY tại /healthz. Java 17+; Gradle tương thích Spring Boot 3.3.x.

Cấu trúc:

~~~text
boot-server-diagnostics/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/demo/BootServerDiagnosticsApplication.java
~~~

File settings.gradle:

~~~groovy
rootProject.name = 'boot-server-diagnostics'
~~~

File build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

File src/main/java/com/example/demo/BootServerDiagnosticsApplication.java:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BootServerDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootServerDiagnosticsApplication.class, args);
    }
}

@RestController
class HealthController {

    @GetMapping(value = "/healthz", produces = MediaType.TEXT_PLAIN_VALUE)
    public String healthz() {
        return "READY";
    }
}
~~~

Hai class nằm trong cùng package, nên component scan của Spring Boot nhận được controller. build.gradle đã có embedded Tomcat thông qua starter-web. Đây là ví dụ ứng dụng độc lập; không cần database hoặc Actuator.

### 10.1 Build và chạy instance đầu

Trong thư mục project:

~~~bash
gradle bootJar
~~~

Chạy instance A:

~~~bash
java -jar build/libs/boot-server-diagnostics-0.0.1-SNAPSHOT.jar --server.port=8080
~~~

Giữ terminal này chạy. Trong terminal thứ hai:

~~~bash
curl -s http://127.0.0.1:8080/healthz
~~~

Body kỳ vọng:

~~~text
READY
~~~

### 10.2 Tái hiện port collision

Giữ A đang lắng nghe 8080. Mở terminal thứ ba và chạy **chính JAR đó** với cùng port:

~~~bash
java -jar build/libs/boot-server-diagnostics-0.0.1-SNAPSHOT.jar --server.port=8080
~~~

Instance B không thể bind thêm listening socket giống instance A ở cùng địa chỉ/cổng, nên thông thường Boot sẽ báo port 8080 already in use hoặc lỗi bind tương đương. Đây là kết quả dự kiến của thí nghiệm; log cụ thể phụ thuộc hệ điều hành và server.

Bây giờ cho B chạy port khác:

~~~bash
java -jar build/libs/boot-server-diagnostics-0.0.1-SNAPSHOT.jar --server.port=8081
~~~

Xác minh:

~~~bash
curl -s http://127.0.0.1:8081/healthz
~~~

Body kỳ vọng:

~~~text
READY
~~~

Nếu cả hai instance đang chạy và mỗi instance bind cổng khác nhau, bạn đã xác minh thay đổi port giải quyết đúng nhóm xung đột cổng.

### 10.3 Tái hiện rủi ro thiếu factory

Sửa riêng dependency starter-web trong ví dụ thành:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
}
~~~

Không khai báo server thay thế. Build và chạy lại ứng dụng. Nếu classpath còn đủ để Boot chọn SERVLET nhưng không có embedded Servlet server implementation, bạn có thể gặp lỗi thiếu ServletWebServerFactory. Phản hồi từ IDE, test hoặc custom configuration có thể khác tùy classpath; không gán trước một exception cố định khi chưa xem log.

Sửa bằng cách **khôi phục dependency starter-web ban đầu**, hoặc bổ sung một embedded Servlet server starter thay thế phù hợp. Khi khởi động lại, request /healthz phải nhận READY.

**Giới hạn của thí nghiệm**: Không sửa dependency trong một ứng dụng production để cố tình gây lỗi. Mục đích là nhận diện sự khác nhau giữa lỗi tạo server và lỗi bind cổng.

## 11. Khi đổi cổng vẫn thất bại

Nếu đã đổi 8080 sang 8081 nhưng lỗi vẫn xuất hiện, hãy kiểm tra thêm:

- **Địa chỉ IP không tồn tại**: server.address có thể trỏ tới địa chỉ không được gán cho host/container. Kiểm tra interface hiện có, rồi bind vào địa chỉ hợp lệ.
- **Cổng bị chiếm ở địa chỉ khác nhau hoặc IPv6/IPv4**: một tiến trình nghe 0.0.0.0 hoặc :: có thể tương tác với các bind trên interface cụ thể tùy hệ điều hành và cấu hình. Đọc đúng LocalAddress trong lệnh liệt kê socket.
- **Quyền bind bị từ chối**: một số cổng hoặc chính sách bảo mật của hệ điều hành hạn chế tiến trình. Không giải quyết bằng cách thêm quyền cao hơn nếu một port thường như 8080 đã đủ đáp ứng yêu cầu.
- **Tham số bị ghi đè**: lệnh truyền --server.port=8081 nhưng nguồn cấu hình có ưu tiên cao hơn trong tình huống cụ thể hoặc tiến trình khác vẫn sử dụng 8081; kiểm tra cấu hình cuối cùng ứng dụng nhận.
- **Khởi động nhiều server trong cùng tiến trình**: cần xem parent/child context, management server, hoặc cấu hình tạo nhiều listener.
- **Test chạy song song**: các bài integration test cùng bind một port cố định có thể tranh nhau. Ưu tiên RANDOM_PORT hoặc quản lý tài nguyên test.
- **Lỗi không nằm ở port**: server có thể tạo bean thất bại trước khi bind. Đọc lại Caused by.

Lệnh curl tới một endpoint không tồn tại có thể nhận HTTP 404. Đây không phải bằng chứng server không khởi động; trái lại, phản hồi HTTP 404 từ đúng tiến trình cho thấy HTTP server đã nhận request nhưng không có mapping cho URL đó. Kiểm chứng đúng endpoint /healthz sẽ rõ ràng hơn.

## 12. Container, Docker và cổng host

Trong container có ít nhất hai địa chỉ/cổng cần phân biệt:

- **Container port**: ứng dụng Java thực sự bind bên trong network namespace của container, ví dụ 8080.
- **Host port**: cổng mà Docker publish ra máy host, ví dụ 18080 khi dùng -p 18080:8080.

Nếu một container đang publish host port 8080, Docker có thể từ chối khởi chạy container khác với cùng host port dù hai ứng dụng bên trong dùng container port riêng. Đây là lỗi publish/bind phía Docker host, không nhất thiết là exception BeanFactory của ứng dụng.

Ví dụ dùng một port host khác:

~~~bash
docker run --rm -p 18080:8080 my-boot-image
~~~

Điều kiện: image my-boot-image đã tồn tại và ứng dụng thực sự lắng nghe port 8080 trên interface có thể truy cập từ container network. Nếu ứng dụng chỉ bind 127.0.0.1 bên trong container, Docker port publishing có thể không truy cập được từ host như mong đợi.

Để kiểm tra container đang chạy và mapping port:

~~~bash
docker ps
~~~

Nếu lỗi xuất phát từ một proxy, orchestration platform hoặc cơ chế publish port, hãy xem log của thành phần đó, không chỉ log Spring Boot.

## 13. Kiểm tra integration test và môi trường phát triển

### 13.1 SpringBootTest dùng RANDOM_PORT

Một integration test web có thể chọn port động để tránh cạnh tranh cổng:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HealthControllerTest {

    @LocalServerPort
    private int port;

    @Test
    void shouldRespondFromStartedServer() {
        String body = RestClient.create()
                .get()
                .uri("http://127.0.0.1:" + port + "/healthz")
                .retrieve()
                .body(String.class);

        assertThat(body).isEqualTo("READY");
    }
}
~~~

Cần bổ sung dependency test phù hợp:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Test dùng REST client trong Spring Framework 6.1 (có trong Spring Boot 3.3.x) và yêu cầu ứng dụng ví dụ từ mục 10. Đây là bài test đầy đủ để kiểm tra HTTP server đã mở cổng động và endpoint trả nội dung mong đợi; không cần giả định port 8080 luôn trống.

### 13.2 Một số test không nên cần mở server

Nếu chỉ kiểm tra logic của service, có thể dùng unit test không khởi động Spring context. Nếu chỉ kiểm tra một slice của web controller, dùng cơ chế web slice test khi phù hợp. Không nên mở embedded server chỉ vì test một method thuần Java.

Một test bị cấu hình ép spring.main.web-application-type=servlet hoặc reactive nhưng loại các dependency server tương ứng có thể gặp lỗi factory. Hãy đối chiếu annotation test, properties và classpath thực tế trước khi quy lỗi cho production code.

## 14. Cách ghi log và quan sát để tìm nguyên nhân

Hãy giữ lại thông tin đủ cho việc chẩn đoán:

- Web application type dự kiến (SERVLET hay REACTIVE).
- Tên embedded server đang được chọn nếu đã xác định.
- Port và address dự kiến; profile và cấu hình liên quan.
- Dòng root cause từ exception chain, không chỉ Application run failed.
- Dependency runtime cho server implementation.
- Trạng thái port LISTEN và PID chủ sở hữu trên môi trường tương ứng.
- Kết quả HTTP request sau khi sửa.

Có thể bật báo cáo điều kiện Spring Boot khi chạy trong môi trường thử nghiệm:

~~~bash
./gradlew bootRun --args='--debug'
~~~

Tham số --debug có thể tạo nhiều log; khi chia sẻ log, xóa token, password, credential, connection string hoặc dữ liệu nhạy cảm. Lưu ý: Spring Boot Actuator chỉ có khi dự án thêm dependency và cấu hình tương ứng; không cần Actuator để xác nhận server qua /healthz trong ví dụ.

## 15. Quy trình xử lý sự cố theo thứ tự

~~~mermaid
flowchart TD
    A["Application run failed"] --> B["Đọc root cause"]
    B --> C{"Có missing WebServerFactory?"}
    C -->|Có| D["Xác định SERVLET hay REACTIVE"]
    D --> E["Kiểm tra runtimeClasspath và exclude"]
    E --> F["Kiểm tra auto-configuration conditions"]
    F --> G["Bổ sung/chỉnh server dependency hoặc web type phù hợp"]
    C -->|Không| H{"Có BindException / Port in use?"}
    H -->|Có| I["Xác định server.port và server.address"]
    I --> J["Liệt kê LISTEN socket / PID"]
    J --> K["Dừng đúng instance cũ hoặc đổi port/address"]
    H -->|Không| L["Phân tích nguyên nhân khác trong stack trace"]
    G --> M["Khởi động lại"]
    K --> M
    L --> M
    M --> N{"Có HTTP response từ đúng endpoint?"}
    N -->|Có| O["Xác minh tình huống đã khắc phục"]
    N -->|Không| B
~~~

Dùng quy trình sau trong một sự cố thực tế:

1. Đọc log và **phân loại**: thiếu factory, bind port, hay lỗi khác.
2. Nếu thiếu factory, xác nhận loại web application và dependency/auto-configuration. Không đổi port theo cảm tính.
3. Nếu bind thất bại, xác nhận port + address và kiểm tra listening process ở **đúng môi trường** chạy app.
4. Thực hiện một thay đổi có chủ đích: sửa dependency, sửa web type, dừng đúng instance cũ, hoặc đổi port/address.
5. Khởi động lại chỉ một instance cần kiểm chứng.
6. Gửi request HTTP tới endpoint rõ ràng, kiểm tra status, body và port thực tế.
7. Ghi nhận nguyên nhân và cách ngăn tái diễn, đặc biệt các exclude dependency và việc dùng port cố định trong test.

## 16. Những nhầm lẫn thường gặp

- **Đổi server.port để sửa missing factory**: không hiệu quả vì lỗi xảy ra trước khi bind socket.
- **Thêm Servlet web starter cho ứng dụng phải chạy reactive**: có thể khiến Boot chọn SERVLET nếu cả hai starter cùng hiện diện; cần xác định rõ web application type.
- **Dùng spring.main.web-application-type=none để “chạy được”**: cách này tắt web server; không phù hợp nếu API phải phục vụ request.
- **Cho rằng có Tomcat trong dependency tree là chắc chắn Boot đã dùng Tomcat**: phải kiểm tra runtime classpath, auto-configuration và server thực tế.
- **Cho rằng port 8080 lỗi ở mọi môi trường**: mỗi host/container network namespace có tài nguyên port khác nhau.
- **Giết PID đầu tiên thấy trong netstat**: PID có thể thuộc service quan trọng hoặc người dùng khác.
- **Coi lỗi 404 là server startup failure**: 404 có thể là kết quả bình thường khi server đã chạy nhưng route không tồn tại.
- **Coi mọi connection refused là port already in use**: refused thường biểu thị không có listener khả dụng tại địa chỉ/cổng đích.
- **Quên test dùng port cố định**: nhiều integration test song song dễ va chạm; dùng RANDOM_PORT nếu không có yêu cầu port cụ thể.
- **Chỉ xem dòng cuối của stack trace**: dòng Caused by sâu hơn có thể phân biệt lỗi bean và lỗi network.

## 17. Tóm tắt

**Thiếu WebServerFactory** nghĩa là Spring Boot không có factory embedded server tương ứng với Servlet hoặc Reactive web context. Kiểm tra web application type, dependency trên runtimeClasspath, exclude và auto-configuration; khôi phục hoặc thay thế server starter phù hợp.

**Port already in use / bind failed** nghĩa là server cố lắng nghe trên một địa chỉ/cổng không dùng được. Xác định port, address và listener thực tế; dừng đúng tiến trình cũ hoặc chọn cổng hợp lệ rồi kiểm chứng lại.

Trong cả hai trường hợp, bằng chứng cuối cùng không chỉ là log “Started ...”: hãy gọi đúng HTTP endpoint và xác nhận status/body qua cổng mà tiến trình thật sự lắng nghe.

## 18. Tài liệu tham khảo

- Spring Boot 3.3 — Embedded Web Servers: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html

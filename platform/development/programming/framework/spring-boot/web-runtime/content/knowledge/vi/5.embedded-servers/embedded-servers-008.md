# Tùy chỉnh JettyServletWebServerFactory hoặc UndertowServletWebServerFactory

Trong ứng dụng **Spring Boot Servlet**, máy chủ HTTP nhúng (embedded web server) được tạo cùng với ApplicationContext khi ứng dụng khởi động. Với \`spring-boot-starter-web\`, lựa chọn mặc định thường là **Tomcat**. Nếu ứng dụng cần chạy **Jetty** hoặc **Undertow**, ta thay đổi dependency để Spring Boot chọn đúng loại máy chủ, sau đó tùy chỉnh factory tương ứng khi các thuộc tính cấu hình sẵn không đáp ứng yêu cầu.

Hai lớp cần phân biệt:

- **JettyServletWebServerFactory** tạo và cấu hình web server Servlet dựa trên Jetty.
- **UndertowServletWebServerFactory** tạo và cấu hình web server Servlet dựa trên Undertow.

Cả hai đều triển khai cơ chế Servlet web server của Spring Boot. Chúng **không phải** là controller, servlet do ứng dụng tự viết hoặc công tắc để chuyển Spring MVC thành WebFlux. Cách tích hợp an toàn thường là tạo bean **WebServerFactoryCustomizer<T>** với kiểu factory cụ thể, rồi để Spring Boot tiếp tục quản lý vòng đời web server.

## 1. Khi nào cần tùy chỉnh web server factory?

Trước hết, xác định mục tiêu thực tế:

| Yêu cầu | Cách xử lý nên xét đầu tiên |
|---|---|
| Đổi cổng HTTP | \`server.port\` |
| Đổi context path của ứng dụng Servlet | \`server.servlet.context-path\` |
| Bật SSL/TLS, HTTP/2 hoặc timeout đã có thuộc tính chuẩn | Các thuộc tính \`server.*\` tương ứng và cấu hình hạ tầng |
| Giới hạn thread pool của Jetty | \`server.jetty.threads.*\` khi đủ nhu cầu |
| Chọn số I/O thread và worker thread của Undertow | \`server.undertow.threads.*\` khi đủ nhu cầu |
| Điều chỉnh API nội bộ của Jetty \`Server\`, connector hoặc thread pool | \`JettyServletWebServerFactory.addServerCustomizers(...)\` |
| Điều chỉnh trực tiếp \`Undertow.Builder\` | \`UndertowServletWebServerFactory.addBuilderCustomizers(...)\` |
| Điều chỉnh chi tiết triển khai Servlet của Undertow | DeploymentInfo customizer khi thật sự cần |
| Cấu hình ServletContext, filter, listener hoặc servlet | Cơ chế Servlet của Spring Boot, ví dụ ServletContextInitializer, FilterRegistrationBean |

**Nguyên tắc lựa chọn:** ưu tiên \`application.yml\` cho cấu hình thông dụng, dễ thay đổi theo môi trường. Dùng \`WebServerFactoryCustomizer\` khi phải truy cập API riêng của server. Chỉ định nghĩa hẳn một factory bean nếu thực sự cần thay đổi cách xây dựng factory; cách này đòi hỏi hiểu những tùy chỉnh mặc định mà Spring Boot thường tự áp dụng.

## 2. Chọn Jetty hoặc Undertow đúng cách

Các customizer chỉ có ý nghĩa khi classpath chứa thư viện server phù hợp và Spring Boot thực sự đang tạo đúng loại Servlet web server.

### 2.1. Dùng Jetty thay Tomcat

Với Gradle Groovy DSL, trong dự án đã có Spring Boot plugin và quản lý dependency:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

Spring MVC vẫn là framework xử lý HTTP request; chỉ embedded Servlet server đổi từ Tomcat sang Jetty. Tên class hỗ trợ cấu hình là:

~~~java
org.springframework.boot.web.embedded.jetty.JettyServletWebServerFactory
~~~

### 2.2. Dùng Undertow thay Tomcat

Cấu hình tương đương cho Undertow:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-undertow'
}
~~~

Factory sử dụng:

~~~java
org.springframework.boot.web.embedded.undertow.UndertowServletWebServerFactory
~~~

**Hai đoạn Gradle trên là hai phương án thay thế**, không phải dependency cần khai báo đồng thời. Tránh giữ cả Tomcat, Jetty và Undertow trong classpath nếu không có lý do rõ ràng; việc có nhiều server factory có thể làm khó xác định server nào được chọn. Không giả định rằng chỉ thêm \`spring-boot-starter-jetty\` là đủ để loại bỏ Tomcat đã được \`spring-boot-starter-web\` kéo vào.

Đây là nội dung về **Servlet stack**. Nếu ứng dụng dùng \`spring.main.web-application-type=reactive\` và WebFlux, cơ chế factory là reactive web server factory, không dùng hai lớp Servlet factory nêu trên để cấu hình server phản ứng.

## 3. WebServerFactoryCustomizer hoạt động như thế nào?

Spring Boot thường tự cấu hình một bean \`ServletWebServerFactory\` phù hợp với classpath. Trong quá trình tạo web server, các bean \`WebServerFactoryCustomizer\` có thể điều chỉnh factory **trước khi web server thực sự khởi động**.

Ví dụ biểu diễn luồng chính:

~~~text
Dependencies trên classpath
        |
        v
Spring Boot chọn ServletWebServerFactory tương ứng
        |
        v
Áp dụng các WebServerFactoryCustomizer có kiểu tương thích
        |
        v
Factory tạo Jetty Server hoặc Undertow server
        |
        v
Embedded server bắt đầu lắng nghe HTTP
~~~

Một bean khai báo là \`WebServerFactoryCustomizer<JettyServletWebServerFactory>\` chỉ nhắm tới Jetty factory tương ứng; nó không biến một Undertow factory thành Jetty. Tương tự, customizer riêng của Undertow chỉ tác động khi factory Undertow được sử dụng.

Spring Boot cũng có những customizer để áp dụng thuộc tính \`server.*\`. Nếu vừa đặt một giá trị trong properties vừa gán chính thuộc tính đó bằng mã customizer, hai thao tác có thể chồng lên nhau. Khi thực sự có nhiều customizer, thứ tự thực thi có thể ảnh hưởng kết quả; hãy quy định rõ thứ tự qua \`@Order\` hoặc \`Ordered\` khi cần và kiểm tra cấu hình cuối cùng. Cách đơn giản nhất là **mỗi thông số có một nơi sở hữu duy nhất**.

Các ví dụ dưới đây dùng Spring Boot 3.x với Java 17 trở lên và là **các lựa chọn triển khai riêng biệt**. Chúng cần được đặt vào dự án Spring Boot đã cấu hình với starter đúng server.

## 4. Ví dụ tùy chỉnh JettyServletWebServerFactory

Jetty quản lý HTTP connector, connection và thread pool. Một nhu cầu thường gặp là điều chỉnh mức tối đa của thread pool sau khi đã đo tải.

Tạo tệp \`src/main/java/demo/web/JettyServerConfiguration.java\`:

~~~java
package demo.web;

import org.eclipse.jetty.util.thread.QueuedThreadPool;
import org.springframework.boot.web.embedded.jetty.JettyServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class JettyServerConfiguration {

    @Bean
    WebServerFactoryCustomizer<JettyServletWebServerFactory>
            jettyThreadPoolCustomizer() {

        return factory -> factory.addServerCustomizers(server -> {
            if (server.getThreadPool() instanceof QueuedThreadPool pool) {
                pool.setMaxThreads(160);
            }
        });
    }
}
~~~

Giải thích:

1. \`@Configuration\` đưa lớp cấu hình vào Spring ApplicationContext.
2. \`@Bean\` đăng ký một customizer dành riêng cho \`JettyServletWebServerFactory\`.
3. \`addServerCustomizers(...)\` cung cấp hook nhận đối tượng \`org.eclipse.jetty.server.Server\` khi Jetty được tạo.
4. \`server.getThreadPool()\` trả về thread pool thực tế của Jetty.
5. \`instanceof QueuedThreadPool\` kiểm tra kiểu trước khi gọi \`setMaxThreads(160)\`, tránh ép kiểu mù khi ứng dụng dùng một thread pool khác.

**160 là giá trị minh họa**, không phải ngưỡng tối ưu. Jetty có thể dùng cấu hình thread pool khác tùy phiên bản hoặc custom code; nếu thread pool không phải \`QueuedThreadPool\`, nhánh ví dụ không thực hiện thay đổi. Trong hệ thống cần bảo đảm bắt buộc một kiểu thread pool, hãy kiểm tra và báo lỗi cấu hình rõ ràng thay vì âm thầm giả định cast luôn thành công.

Cần giữ \`maxThreads\` hợp lý so với \`minThreads\`, CPU, bộ nhớ stack và khả năng của dependency phía dưới. Thêm thread không tự tăng tốc truy vấn SQL hoặc dịch vụ HTTP đang quá tải.

### 4.1. Cấu hình tương đương bằng properties khi đủ dùng

Nếu chỉ muốn chỉnh giới hạn thread của Jetty và phiên bản Spring Boot hỗ trợ, nên đặt trong \`application.yml\`:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /demo
  jetty:
    threads:
      min: 8
      max: 160
~~~

Các giá trị này minh họa việc giới hạn thread và đường dẫn. Với cùng mục tiêu, chỉ cần **một** trong hai cách chỉnh max thread: property hoặc Java customizer. Không khai báo trùng mà không xác định thứ tự áp dụng.

Cổng và context path áp dụng cho Servlet web server nói chung. Context path \`/demo\` khiến một endpoint mapping \`/ping\` được truy cập qua \`/demo/ping\`, nếu ứng dụng không có cấu hình URL khác can thiệp.

### 4.2. Khi cần tùy chỉnh Jetty chuyên sâu

Jetty còn có connector, connection factory, TLS/ALPN, thread pool và các handler của riêng nó. Có thể sử dụng \`addServerCustomizers\` để truy cập Jetty \`Server\`, nhưng các API connector/handler thay đổi theo phiên bản Jetty. Vì thế:

- Xác định phiên bản Jetty mà Spring Boot starter đang quản lý.
- Dùng API của đúng phiên bản, không chép mã Jetty 9/10/11 cho Jetty 12 mà không kiểm tra.
- Không vô tình thay thế handler hoặc connector do Spring Boot cấu hình, làm mất servlet mapping, HTTPS hoặc HTTP/2.
- Với thông số đã có \`server.*\` property, ưu tiên property thay vì tự chỉnh connector.
- Chạy integration test với HTTP/TLS thật sau khi đổi cấu hình.

Cấu hình thread pool là ví dụ đơn giản để học hook Jetty; thay đổi connector hoặc TLS production cần thêm kiểm chứng tương thích và kiểm thử tích hợp.

## 5. Ví dụ tùy chỉnh UndertowServletWebServerFactory

Undertow dùng một số **I/O thread** để xử lý sự kiện I/O và **worker thread** để xử lý phần công việc được chuyển sang worker. Số lượng hai loại thread là hai giới hạn khác nhau. Không thực hiện tác vụ blocking dài trực tiếp trên I/O thread; code xử lý Servlet thông thường được Undertow điều phối theo mô hình của server.

Tạo tệp \`src/main/java/demo/web/UndertowServerConfiguration.java\` trong **phương án dùng Undertow**:

~~~java
package demo.web;

import org.springframework.boot.web.embedded.undertow.UndertowServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UndertowServerConfiguration {

    @Bean
    WebServerFactoryCustomizer<UndertowServletWebServerFactory>
            undertowThreadCustomizer() {

        return factory -> factory.addBuilderCustomizers(builder -> {
            builder.setIoThreads(4);
            builder.setWorkerThreads(64);
        });
    }
}
~~~

Giải thích:

1. Spring Boot đăng ký customizer cho \`UndertowServletWebServerFactory\`.
2. \`addBuilderCustomizers(...)\` nhận callback đối với \`Undertow.Builder\`.
3. \`setIoThreads(4)\` cấu hình bốn I/O thread trong ví dụ.
4. \`setWorkerThreads(64)\` cấu hình số worker thread minh họa.
5. Spring Boot tiếp tục tạo và khởi động Undertow từ builder đã được tùy chỉnh.

Các con số cần được đo trên máy và workload thực tế. Nếu giảm I/O thread quá thấp, throughput mạng có thể bị ảnh hưởng; nếu tăng worker thread quá cao, JVM có thể tiêu tốn nhiều bộ nhớ stack và CPU cho chuyển ngữ cảnh, đồng thời dồn tải lớn lên DB.

### 5.1. Ưu tiên properties khi chỉ điều chỉnh số thread

Ví dụ \`application.yml\` cho Undertow:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /demo
  undertow:
    threads:
      io: 4
      worker: 64
~~~

Nếu chỉ cần hai thiết lập này, properties đủ rõ và dễ thay đổi theo môi trường. Khi dùng customizer để chỉnh sâu hơn, cần tránh đặt giá trị tương tự ở hai nơi mà không kiểm tra kết quả thực tế.

### 5.2. Các điểm mở rộng khác của Undertow

Factory Undertow còn có các hook chuyên biệt:

- **addBuilderCustomizers**: tùy chỉnh \`Undertow.Builder\`, chẳng hạn các tùy chọn I/O hoặc network do API Undertow hỗ trợ.
- **addDeploymentInfoCustomizers**: điều chỉnh \`DeploymentInfo\` của Servlet deployment khi cần tích hợp chức năng đặc thù.
- Các cấu hình chung của Servlet factory: cổng, context path, session, SSL và những customizer mặc định của Spring Boot.

Không nên chỉnh \`DeploymentInfo\` chỉ để đăng ký một \`Filter\` hoặc \`Servlet\` thông thường: Spring Boot đã có \`FilterRegistrationBean\`, \`ServletRegistrationBean\` và \`ServletContextInitializer\` phục vụ những nhu cầu đó.

## 6. Ví dụ ứng dụng kiểm tra web server

Để kiểm tra server đang phục vụ request, có thể thêm một Spring Boot entry point và controller dùng chung cho **một trong hai phương án** Jetty hoặc Undertow.

Tệp \`src/main/java/demo/web/DemoWebApplication.java\`:

~~~java
package demo.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoWebApplication.class, args);
    }
}
~~~

Tệp \`src/main/java/demo/web/PingController.java\`:

~~~java
package demo.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Khi dùng \`server.port=8080\` và \`server.servlet.context-path=/demo\`, chạy ứng dụng từ dự án Gradle đã có Spring Boot plugin:

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể dùng \`gradlew.bat bootRun\`. Trong terminal khác:

~~~bash
curl -i http://localhost:8080/demo/ping
~~~

Với ứng dụng chỉ gồm endpoint minh họa, không có Spring Security hoặc filter thay đổi response, kết quả mong đợi là **HTTP 200** và response body:

~~~text
pong
~~~

HTTP headers có thể khác nhau tùy server và môi trường; không nên khẳng định một bộ header cố định. Nếu cổng 8080 đã bị chiếm hoặc một cấu hình khác ghi đè \`server.port\`, ứng dụng cần cổng khác phù hợp.

**Lưu ý khi tổ chức mã:** chọn **một** dependency server và **một** class cấu hình riêng cho server đã chọn. Nếu build chỉ có starter Jetty nhưng vẫn để source code import \`UndertowServletWebServerFactory\`, Java có thể không biên dịch do thiếu thư viện Undertow trên classpath. Hai ví dụ là hai phương án triển khai độc lập.

## 7. Khi nào tạo trực tiếp factory bean?

Ngoài tạo \`WebServerFactoryCustomizer\`, Spring Boot cho phép người phát triển định nghĩa một bean \`JettyServletWebServerFactory\` hoặc \`UndertowServletWebServerFactory\`:

~~~java
// Fragment minh họa: đặt trong @Configuration khi thật sự muốn
// tự sở hữu toàn bộ việc tạo Jetty factory.
@Bean
JettyServletWebServerFactory customJettyFactory() {
    return new JettyServletWebServerFactory();
}
~~~

Đây là **fragment**, chỉ biên dịch khi có các import, class cấu hình và dependency Jetty thích hợp. Khi định nghĩa factory trực tiếp, Spring Boot có thể không còn cần tạo factory mặc định. Các customizer vẫn có thể được áp dụng, nhưng người viết phải hiểu cấu hình và constructor của factory tự cung cấp.

Không cần tạo bean factory chỉ để đổi port hoặc thread pool. Tạo một factory riêng có thể dẫn đến:

- Vô tình bỏ qua lựa chọn factory mặc định hoặc thay đổi cách xử lý auto-configuration.
- Tạo nhiều bean cùng loại \`ServletWebServerFactory\`, dẫn đến lỗi thiếu tính duy nhất hoặc xung đột.
- Bỏ sót các bước cấu hình connector hoặc resource khi thay đổi sâu.
- Làm bài test sử dụng port ngẫu nhiên hoặc cấu hình SSL hoạt động khác dự kiến.

Vì vậy, trong phần lớn ứng dụng nên giữ factory do Boot tạo và chỉ đăng ký customizer. Nếu phải cung cấp factory thủ công, thử đầy đủ HTTP, HTTPS, context path, Servlet registration, filters, lifecycle và tắt server.

## 8. Thứ tự tùy chỉnh và phạm vi của từng thuộc tính

Các giá trị được cấu hình ở nhiều lớp:

1. **Environment/ConfigData:** \`application.yml\`, profile, biến môi trường, command-line.
2. **Spring Boot server properties:** ánh xạ các giá trị \`server.*\` vào factory.
3. **WebServerFactoryCustomizer:** thay đổi factory dựa trên điều kiện hoặc API riêng.
4. **Server-specific customizers:** callback của Jetty \`Server\` hoặc Undertow \`Builder\` khi server thực tế được dựng.
5. **Hạ tầng bên ngoài:** reverse proxy, load balancer, service mesh, ingress, firewall và giới hạn cổng/network.

Không thể đảm bảo một cấu hình ở lớp sau luôn “thắng” cấu hình trước trong mọi triển khai nếu thứ tự các customizer không được quản lý. Khi có nhiều nguồn thay đổi cùng thông số, kết quả có thể phụ thuộc thứ tự áp dụng. Ghi rõ nguồn sở hữu, dùng \`@Order\` khi cần và kiểm tra giá trị/behavior thực tế bằng integration test.

### Cấu hình chung cho Jetty và Undertow

Một số thuộc tính Spring Boot vẫn dùng chung cho các Servlet web server:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /demo
    session:
      timeout: 30m
  shutdown: graceful
~~~

Nhưng những thuộc tính mang tiền tố \`server.jetty.*\` chỉ nhắm tới Jetty, còn \`server.undertow.*\` chỉ nhắm tới Undertow. Một thuộc tính \`server.tomcat.*\` sẽ không thay đổi Undertow chỉ vì ứng dụng từng dùng Tomcat.

Giá trị session timeout ở ví dụ cần được lựa chọn theo nghiệp vụ. Graceful shutdown hỗ trợ ứng dụng hoàn thành request đang xử lý trong điều kiện cho phép; deadline dừng thực tế còn chịu ảnh hưởng của \`spring.lifecycle.timeout-per-shutdown-phase\` và môi trường chạy.

## 9. Khác biệt giữa Jetty và Undertow khi điều chỉnh tài nguyên

Các số thread trong ví dụ là **giới hạn thực thi**, không phải mục tiêu tăng càng cao càng tốt.

| Khía cạnh | Jetty | Undertow |
|---|---|---|
| Factory cho Servlet | JettyServletWebServerFactory | UndertowServletWebServerFactory |
| API tùy chỉnh riêng thường gặp | Jetty Server, connector, thread pool | Undertow.Builder, DeploymentInfo |
| Thread tuning | Jetty thread pool, giới hạn min/max | I/O thread và worker thread |
| Cấu hình thông dụng | \`server.jetty.threads.*\` | \`server.undertow.threads.*\` |
| Điểm cần đo | Thread busy, queue, connector, CPU và latency | I/O/worker saturation, CPU, latency và tài nguyên downstream |

Tăng thread có thể cải thiện throughput ở một số workload nhưng cũng có thể tăng cạnh tranh lock, tiêu thụ bộ nhớ stack và làm connection pool DB bị đẩy đến giới hạn. Đặc biệt, không nên coi 200 worker thread là 200 truy vấn DB có thể thực thi đồng thời nếu Hikari pool chỉ có 10 connection.

Để điều chỉnh hợp lý:

1. Xác định tải dự kiến, request/giây, concurrency, p95/p99 latency và tỷ lệ lỗi.
2. Đo CPU, heap, thread, connection pool, thời gian GC và độ trễ DB/API ngoài.
3. Thay đổi từng thông số có bằng chứng là bottleneck.
4. Tăng tải dần và so sánh trước/sau; xem đồng thời lỗi timeout, queue và sức chịu đựng của dependency.
5. Luôn có giới hạn tài nguyên ở tầng container và cấu hình shutdown phù hợp.

Đừng sao chép nguyên các giá trị 4 I/O threads, 64 workers hay 160 Jetty threads vào production mà chưa đo.

## 10. Tác động tới TLS, HTTP/2, proxy và Servlet pipeline

Đổi embedded server thường giữ được Spring MVC controller/service vì chúng làm việc thông qua Servlet abstraction, nhưng phần cấu hình server-specific có thể thay đổi:

**TLS/HTTPS:** ưu tiên \`server.ssl.*\` hoặc cơ chế certificate/secret của hạ tầng. Khi tự tạo connector, cần giữ đủ cấu hình TLS, timeout và protocol; không ghi private key/keystore password vào source code.

**HTTP/2:** cần kiểm tra hỗ trợ của phiên bản Jetty/Undertow, JDK, TLS/ALPN và starter. Không mặc định mọi server/connector đều hỗ trợ cùng một cách thiết lập HTTP/2; kiểm thử bằng HTTP client thật.

**Reverse proxy:** proxy có thể giữ kết nối, giới hạn header/body, đưa thêm \`Forwarded\`/\`X-Forwarded-*\` và có timeout khác backend. Khi thay web server, kiểm tra forwarding headers, scheme HTTPS, redirect, client IP, cookie và request URI theo cách triển khai thực tế.

**Servlet pipeline:** filters, listeners, Spring Security, servlet mappings và session vẫn cần được kiểm thử. Nếu customizer thay đổi context path hoặc connector, endpoint có thể đổi đường dẫn hoặc cổng dù controller không thay.

**WebSocket, streaming và upload:** không giả định hai server luôn giống nhau về buffer, timeout, giới hạn request và hỗ trợ protocol. Cần thử các trường hợp kết nối lâu, upload lớn, streaming response và đóng kết nối bất thường.

## 11. Kiểm thử và xác minh server đang dùng

### 11.1. Kiểm tra dependency trước

Trong dự án Gradle, xem dependency thực tế:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm starter Jetty/Undertow và kiểm tra rằng Tomcat không còn được kéo vào ngoài ý muốn. Nếu dùng Spring Boot plugin với build logic nhiều module, chọn đúng subproject tương ứng; không giả định lệnh chạy tại root luôn truy vấn đúng module.

### 11.2. Quan sát log và endpoint

Khởi động ứng dụng, xem log khởi động web server và lỗi cấu hình. Jetty và Undertow thường có thông tin riêng trong log; đừng chỉ dựa vào tên class đã import để kết luận server đang chạy.

Gọi endpoint thực qua \`curl -i\`, kiểm tra status/body, context path và cổng. Khi đã bật HTTPS hoặc HTTP/2, thử đúng protocol ở client. Với timeout và concurrency, cần bài kiểm thử tải có thể tái lập.

### 11.3. Kiểm thử integration thực sự

Một unit test \`@WebMvcTest\` chỉ tập trung vào MVC slice, thường không khởi động embedded server thật; nó không đủ để chứng minh Jetty connector hoặc Undertow worker thread đã được áp dụng. Dùng \`@SpringBootTest(webEnvironment = RANDOM_PORT)\` hoặc chạy JAR thật để kiểm tra hành vi mạng và lifecycle.

**Lưu ý:** nếu Java customizer cưỡng ép một cổng cụ thể bằng \`factory.setPort(8080)\`, nó có thể làm mất ý nghĩa của cấu hình port ngẫu nhiên trong test tùy thứ tự customizer. Với những giá trị chung như port, ưu tiên đặt qua \`server.port\` và không ghi đè trong customizer đặc thù.

Kiểm tra kết quả cuối cùng bằng cấu hình thực tế và đo thông số runtime, không chỉ test rằng bean customizer tồn tại.

## 12. Những lỗi thường gặp

### Lỗi 1: Thêm Jetty starter nhưng không loại Tomcat

Hệ classpath có nhiều Servlet web server. Ứng dụng có thể khởi động bằng server không mong muốn hoặc gặp lỗi cấu hình tùy cách phụ thuộc được lắp ráp.

**Khắc phục:** kiểm tra \`runtimeClasspath\`, exclude \`spring-boot-starter-tomcat\` khỏi \`starter-web\`, rồi chỉ thêm server đã chọn.

### Lỗi 2: Nhầm Servlet factory với Reactive server

Một dự án WebFlux muốn thêm JettyServletWebServerFactory để thay Reactor Netty nhưng ứng dụng đang là reactive ApplicationContext.

**Khắc phục:** xác định \`WebApplicationType\` và dùng factory/server phù hợp với web stack. Hai factory trong bài dành cho Servlet.

### Lỗi 3: Bean customizer không chạy

Có thể do loại web server thực tế khác, class cấu hình không được scan, bean bị điều kiện loại bỏ hoặc thiếu dependency.

**Khắc phục:** xem component scan, ApplicationContext, effective classpath và log; nếu cần, log có kiểm soát khi customizer được gọi. Đừng tự kết luận bean tồn tại là server đã dùng đúng factory.

### Lỗi 4: Cấu hình cùng thuộc tính ở hai nơi

Có cả \`server.jetty.threads.max\` và \`setMaxThreads(...)\` với giá trị khác nhau, hoặc hai customizer cùng sửa cổng.

**Khắc phục:** xác định nguồn sở hữu, bỏ khai báo trùng hoặc quản lý \`@Order\` có chủ đích; xác minh server thực chạy đúng giá trị mong muốn.

### Lỗi 5: Điều chỉnh thread pool quá mức

Quá nhiều thread làm tăng memory footprint và chuyển ngữ cảnh; quá ít thread làm request chờ lâu.

**Khắc phục:** phân tích tải, thread dump, pool saturation và giới hạn DB; đo p95/p99 latency trước/sau khi đổi.

### Lỗi 6: Tạo factory bean thủ công khi chỉ cần customizer

Tự tạo factory có thể thay thế auto-configuration, làm mất một phần hành vi kỳ vọng hoặc tạo xung đột bean.

**Khắc phục:** dùng \`WebServerFactoryCustomizer<JettyServletWebServerFactory>\` hay \`WebServerFactoryCustomizer<UndertowServletWebServerFactory>\` để điều chỉnh factory Spring Boot đang quản lý.

### Lỗi 7: Lấy ví dụ API từ sai phiên bản Jetty

Jetty có thay đổi đáng kể giữa các phiên bản. Phương thức hoặc connector API từng dùng có thể không còn tương thích.

**Khắc phục:** kiểm tra phiên bản Jetty đang được Spring Boot BOM quản lý, tra API đúng phiên bản và chạy compile/integration test.

### Lỗi 8: Test chỉ kiểm tra controller

Endpoint unit test pass nhưng connector bị cấu hình sai, HTTPS không hoạt động hoặc customizer hoàn toàn không được chạy.

**Khắc phục:** chạy integration test có embedded server thật, thử cổng/path/TLS và smoke test trên môi trường triển khai.

### Lỗi 9: Quên giới hạn ngoài ứng dụng

Cổng, timeout, request size và TLS có thể bị chặn hoặc thay đổi bởi ingress, proxy, firewall hay container.

**Khắc phục:** kiểm tra cả hạ tầng bên ngoài và ứng dụng, nhất là forwarding headers, idle timeout và readiness/liveness probe.

## 13. Checklist khi triển khai

- Chọn **Servlet stack** và chỉ một embedded server chính: Jetty hoặc Undertow.
- Exclude Tomcat khỏi starter-web và thêm đúng starter thay thế.
- Đặt port, context path, SSL và thông số phổ biến trong \`application.yml\` nếu đủ dùng.
- Tạo customizer có generic type chính xác cho **JettyServletWebServerFactory** hoặc **UndertowServletWebServerFactory** khi cần API riêng.
- Dùng Jetty Server customizer hoặc Undertow Builder/DeploymentInfo customizer đúng nhu cầu; tránh thay đổi toàn bộ factory.
- Kiểm tra các bean/configuration customizer được scan và thứ tự nếu nhiều nơi sửa cùng một giá trị.
- Bảo toàn Servlet mapping, Spring Security, filters, session, TLS, HTTP/2 và forwarding khi thay server.
- Kiểm tra dependency tree, startup log, HTTP endpoint, port/context path và runtime metrics.
- Kiểm thử tải có giới hạn, quan sát p95/p99 latency, CPU, thread pool, DB pool và timeout.
- Kiểm tra graceful shutdown, cấu hình probe và giới hạn tài nguyên ở môi trường triển khai.

**Kết luận:** \`JettyServletWebServerFactory\` và \`UndertowServletWebServerFactory\` là điểm mở rộng để cấu hình embedded **Servlet** server theo loại server đã chọn. Hãy dùng properties cho cấu hình có sẵn, dùng **WebServerFactoryCustomizer** khi cần chỉnh API đặc thù, xác nhận đúng dependency và kiểm thử trên web server thật.
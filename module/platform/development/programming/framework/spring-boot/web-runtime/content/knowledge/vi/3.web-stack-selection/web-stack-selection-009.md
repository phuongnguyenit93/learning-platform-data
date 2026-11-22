# Quan hệ giữa web stack và các máy chủ được hỗ trợ theo phiên bản Spring Boot

## 1. Mục tiêu và phạm vi

Trong Spring Boot, chọn **web stack** và chọn **HTTP server** là hai quyết định có liên quan nhưng không đồng nhất. Web stack quyết định mô hình xử lý request, API và kiểu lập trình; HTTP server tiếp nhận kết nối mạng và cung cấp môi trường chạy. Danh sách server được Spring Boot cấu hình, kiểm thử và hỗ trợ chính thức lại **phụ thuộc vào phiên bản Spring Boot**.

Bài này tập trung vào Spring MVC (Servlet) và Spring WebFlux (reactive), Tomcat, Jetty, Undertow, Reactor Netty, starter dependency, Servlet API và các thay đổi khi nâng cấp từ Spring Boot 2.7 qua 3.x lên 4.x. Các bảng là **ma trận tương thích do Spring Boot công bố cho những mốc phiên bản cụ thể**, không phải cam kết rằng mọi phiên bản bất kỳ của một server đều dùng được với mọi bản Boot.

## 2. Ba lớp cần phân biệt

1. **Web stack:** Spring MVC sử dụng mô hình Servlet; Spring WebFlux xây dựng trên API reactive như Mono, Flux và các adapter HTTP không đồng bộ. Đây là lựa chọn về mô hình phát triển ứng dụng.
2. **Embedded server:** Tomcat, Jetty, Undertow hoặc Reactor Netty là runtime HTTP được ứng dụng mang theo khi chạy dạng executable jar. Server nhận socket, TLS, HTTP và chuyển tiếp dữ liệu cho framework.
3. **Phiên bản Spring Boot:** quy định starter, auto-configuration, factory/adapter, các phiên bản dependency được quản lý bởi BOM và tập server được hỗ trợ/kiểm thử cùng thời điểm.

Các cặp server–stack có thể khác nhau:

| Server | Là Servlet container? | Có thể chạy MVC theo cách được Boot hỗ trợ? | Có thể làm server WebFlux? |
|---|---|---|---|
| Tomcat | Có | Có | Có, qua reactive adapter |
| Jetty | Có | Có | Có, qua reactive adapter |
| Undertow | Có | Có trong Boot 2.7–3.5 | Có trong Boot 2.7–3.5 |
| Reactor Netty | Không | Không phải Servlet server cho Spring MVC | Có; là lựa chọn WebFlux mặc định |

**Quan trọng:** ô “Có” trong bảng này luôn phải kết hợp với phiên bản Boot cụ thể; từ Boot 4.x, Undertow không còn nằm trong danh sách embedded server được Spring Boot hỗ trợ chính thức. Spring WebFlux chạy trên Tomcat/Jetty không tự biến thành Spring MVC. Reactor Netty là HTTP server reactive, còn Netty cũng có thể xuất hiện trong dependency của HTTP client; có Netty trên classpath không tự chứng minh Netty đang nhận request.

Về mặc định, Spring MVC đi với Tomcat, còn WebFlux đi với Reactor Netty. Nếu cả dependency MVC và WebFlux cùng có mặt, Spring Boot thường chọn ứng dụng kiểu Servlet/MVC theo quy tắc tự động xác định web application type. Nhiều dự án MVC cố ý dùng WebClient để gọi dịch vụ ngoài mà vẫn giữ MVC làm web stack. Để triển khai WebFlux thật sự, cần kiểm tra application type và starter đang dùng, không suy luận từ việc có Mono/Flux trong một controller.

## 3. Ma trận hỗ trợ Servlet server theo phiên bản

Bảng dưới đây dựa trên mục **System Requirements / Servlet Containers** của tài liệu chính thức từng phiên bản, hiển thị dòng server được Spring Boot hỗ trợ **ở mốc phát hành ghi trong cột đầu**.

| Spring Boot | Java tối thiểu | Tomcat | Jetty | Undertow | Mức Servlet API tương ứng |
|---|---:|---|---|---|---|
| 2.7.18 | 8 | 9.0 | 9.4 hoặc 10.0 | 2.0 | Tomcat 4.0; Jetty 9.4: 3.1, Jetty 10: 4.0; Undertow 4.0 |
| 3.0.13 | 17 | 10.1 | 11.0 | 2.3 | Tomcat 6.0; Jetty 5.0; Undertow 6.0 |
| 3.1.12 | 17 | 10.1 | 11.0 | 2.3 | Tomcat 6.0; Jetty 5.0; Undertow 6.0 |
| 3.2.10 | 17 | 10.1 | 12.0 | 2.3 | Servlet 6.0 cho cả ba lựa chọn |
| 3.3.x–3.5.x (ví dụ 3.5.16) | 17 | 10.1 | 12.0 | 2.3 | Servlet 6.0 cho cả ba lựa chọn |
| 4.0.x–4.1.x (ví dụ 4.1.2) | 17 | 11.0.x | 12.1.x | Không được liệt kê hỗ trợ | Servlet 6.1 cho Tomcat và Jetty |

Một vài lưu ý khi đọc ma trận:

- **2.7.x:** Boot sử dụng Spring Framework 5 và Servlet API thuộc namespace javax.servlet. Jetty 9.4 chỉ hỗ trợ Servlet 3.1 trong khi Jetty 10 hỗ trợ Servlet 4.0; vì vậy cùng một bản Boot có thể có nhiều mức Servlet API tùy container.
- **3.0–3.1:** Boot chuyển sang Spring Framework 6 và namespace jakarta.servlet. Dù Tomcat 10.1 và Undertow 2.3 ở Servlet 6.0, Jetty 11 chỉ ở Servlet 5.0. Không được đánh đồng “Boot 3” với “mọi container đều là Servlet 6”.
- **3.2–3.5:** Jetty chuyển sang dòng 12.0 và có Servlet 6.0 trong cấu hình được Boot hỗ trợ.
- **4.0–4.1:** Boot dùng Spring Framework 7, Servlet API 6.1 và chỉ liệt kê Tomcat 11.0.x, Jetty 12.1.x làm embedded Servlet container. Undertow 2.3 của Boot 3.x không phải lựa chọn nâng cấp mặc định sang Boot 4.
- **Chi tiết patch có thể thay đổi:** Boot BOM khóa các phiên bản dependency cụ thể để vá lỗi và bảo mật. “Tomcat 10.1” là một **nhánh phiên bản**, không phải chỉ dẫn cố định một patch. Muốn biết bản patch thực tế, phải xem dependency tree hoặc runtime.
- **Mốc 3.0.0 khác 3.0.13:** các bản rất đầu của dòng 3.0 từng có tổ hợp container khác; khi cần thông tin chính xác hãy dùng tài liệu của **đúng bản** đang vận hành. Không dùng một bảng cho toàn bộ lịch sử của một dòng lớn nếu từng patch có thay đổi.

“Embedded server được hỗ trợ” không đồng nghĩa với “cứ deploy WAR lên mọi server cùng tên”. Deploy WAR bên ngoài còn phụ thuộc vào cấp Servlet API, package javax/jakarta, runtime Java, classpath và hướng dẫn tương thích riêng của bản Boot. Ví dụ Boot 4 cần cân nhắc Servlet 6.1, còn Boot 2.7 sử dụng javax.servlet; không thể đơn giản mang WAR cũ sang Tomcat 11.

## 4. Ma trận server WebFlux theo phiên bản

WebFlux **không bắt buộc** chạy trên Reactor Netty. Spring Boot có adapter để chạy WebFlux qua các server hỗ trợ khác theo từng phiên bản.

| Dòng Spring Boot | WebFlux mặc định | Các server WebFlux nhúng được Boot hỗ trợ |
|---|---|---|
| 2.7.x | Reactor Netty | Reactor Netty, Tomcat, Jetty, Undertow |
| 3.0.x–3.5.x | Reactor Netty | Reactor Netty, Tomcat, Jetty, Undertow |
| 4.0.x–4.1.x | Reactor Netty | Reactor Netty, Tomcat, Jetty |

Cần đọc song song hai bảng: **Servlet container version** chỉ mô tả Tomcat/Jetty/Undertow trong môi trường Servlet; bản thân Reactor Netty không thực thi Servlet API và vì vậy không có hàng trong bảng Servlet containers của tài liệu System Requirements.

Tại Boot 4.x, Servlet stack hỗ trợ Tomcat hoặc Jetty, WebFlux có thể dùng Reactor Netty hoặc Tomcat/Jetty. Sự khác biệt giữa Servlet và reactive nằm ở pipeline xử lý, backpressure và mô hình lập trình; không thể đánh giá mô hình nào “nhanh hơn” chỉ từ tên web server. Khi dùng JDBC hoặc thư viện chặn (blocking) trong luồng reactive, cần xử lý đúng đặc tính blocking dù server có hỗ trợ reactive.

## 5. Quan hệ với starter dependency và auto-configuration

Spring Boot cung cấp starter để chọn stack và server mà không phải lắp thủ công hàng chục thư viện.

| Bản Boot | Starter cho Spring MVC | Starter cho WebFlux | Server mặc định |
|---|---|---|---|
| 2.7.x–3.5.x | spring-boot-starter-web | spring-boot-starter-webflux | MVC: Tomcat; WebFlux: Reactor Netty |
| 4.0.x–4.1.x | spring-boot-starter-webmvc (khuyến nghị) | spring-boot-starter-webflux | MVC: Tomcat; WebFlux: Reactor Netty |

Trong Boot 4.x, starter **spring-boot-starter-web** cũ vẫn tồn tại nhưng đã bị đánh dấu deprecated, ưu tiên **spring-boot-starter-webmvc** cho dự án mới. Vì vậy một ví dụ Maven dùng starter-web cho Boot 3.5 không nên sao chép máy móc sang Boot 4.1 khi có starter mới rõ nghĩa hơn.

Mô hình cấu hình thường gặp:

~~~text
Maven/Gradle dependencies
    -> Spring Boot auto-configuration và BOM
        -> chọn web application type: SERVLET hoặc REACTIVE
            -> tạo WebServerFactory phù hợp với server đã chọn
                -> tạo và khởi động embedded HTTP server
                    -> MVC DispatcherServlet hoặc WebFlux HTTP handler
~~~

Với Spring MVC, Spring Boot tạo ServletWebServerApplicationContext và ServletWebServerFactory thích hợp. Với WebFlux, Spring Boot sử dụng ReactiveWebServerApplicationContext và ReactiveWebServerFactory tương ứng. Việc dự án có class Netty hoặc Tomcat trong dependency tree chưa đủ để kết luận server nào được tạo: phải xem dependency, auto-configuration, application type và log/runtime thực tế.

Khi hoán đổi server, phải **loại server mặc định khỏi dependency của starter** và thêm starter mới phù hợp. Nếu chỉ thêm Jetty bên cạnh Tomcat, có thể tạo classpath lẫn nhiều server factory, gây hành vi khó kiểm soát hoặc lỗi khởi động.

## 6. Cấu hình minh họa: Spring MVC trên Spring Boot 3.5

Giả sử dự án Maven đã dùng Spring Boot 3.5.x qua parent/BOM. Để chạy MVC trên **Jetty 12.0** thay vì Tomcat, phần dependencies có thể viết như sau:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
        <exclusions>
            <exclusion>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-tomcat</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jetty</artifactId>
    </dependency>
</dependencies>
~~~

Spring Boot BOM chọn phiên bản Jetty tương thích, không cần tự điền version Jetty. Đổi sang Undertow ở Boot 3.5 chỉ bằng cách thay dependency Jetty trong ví dụ thành **spring-boot-starter-undertow** (vẫn loại Tomcat); đối chiếu phiên bản Undertow do BOM quản lý.

Trong Gradle Groovy DSL cho Boot 3.5, mẫu tương đương:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

Đây là trích đoạn của build đã có plugin Spring Boot và quản lý dependency. Không chạy riêng một trích đoạn XML/Groovy như một chương trình hoàn chỉnh.

## 7. Cấu hình minh họa: Spring MVC trên Spring Boot 4.1

Với Spring Boot 4.1.x, sử dụng **spring-boot-starter-webmvc** và Jetty 12.1:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
        <exclusions>
            <exclusion>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-tomcat</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jetty</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ Gradle Groovy DSL, cũng dành cho dự án đã cấu hình plugin và BOM Spring Boot 4.1:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webmvc') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

Không sao chép spring-boot-starter-undertow từ cấu hình 3.5 sang 4.1: Undertow không còn là embedded server được liệt kê hỗ trợ trong Boot 4.1. Nếu ứng dụng yêu cầu đặc tính riêng của Undertow, hãy kiểm tra giải pháp thay thế được hỗ trợ, tương thích API và vòng đời thư viện trước khi nâng cấp.

## 8. Đổi HTTP server trong WebFlux

Với WebFlux, starter mặc định là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Trong Boot 3.5 và 4.1, nó thường đưa **spring-boot-starter-reactor-netty** vào runtime. Để dùng WebFlux trên Jetty (trích đoạn Maven của dự án có BOM Spring Boot tương ứng):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
        <exclusions>
            <exclusion>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-reactor-netty</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jetty</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ này đổi **server nhận request** của WebFlux. Nếu ứng dụng còn sử dụng WebClient hoặc thư viện client dùng Reactor Netty, cần kiểm tra lại HTTP client connector và các dependency; thay server không bắt buộc phải thay HTTP client. Có thể vẫn cần Netty trong classpath để chạy client trong khi web server là Jetty. Tương tự, nếu muốn đổi WebFlux sang Tomcat, dùng starter-tomcat tương ứng và loại starter-reactor-netty mặc định. Ở Boot 4.x, các lựa chọn chính thức cho WebFlux chỉ gồm Reactor Netty, Tomcat và Jetty.

## 9. Ví dụ Java kiểm chứng stack và server

Ví dụ Java 17+ dưới đây là một ứng dụng Spring Boot tối giản. Đặt tại **src/main/java/com/example/demo/WebServerDemo.java** trong project Maven/Gradle có đúng một starter MVC hoặc WebFlux phù hợp; các API controller được cả hai stack nhận diện. Server được quyết định bởi starter đã cấu hình, không phải nội dung controller.

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class WebServerDemo {
    public static void main(String[] args) {
        SpringApplication.run(WebServerDemo.class, args);
    }
}

@RestController
class ProbeController {
    @GetMapping("/probe")
    String probe() {
        return "ok";
    }
}
~~~

Chương trình cần classpath Spring Boot, vì vậy không thể chạy chỉ bằng javac WebServerDemo.java. Với Maven Wrapper của dự án Spring Boot đã cấu hình đúng parent và starter:

~~~bash
./mvnw spring-boot:run
~~~

Kiểm tra bằng terminal khác (server mặc định port 8080):

~~~bash
curl -sS http://localhost:8080/probe
~~~

Response body dự kiến chính xác là **ok** (không kèm newline do controller trả String). Header phản hồi, cổng và thông báo startup có thể khác theo phiên bản/đường cấu hình; không suy luận runtime là Jetty hoặc Tomcat chỉ từ response body. Để chủ động đổi port, có thể đặt trong **src/main/resources/application.properties**:

~~~properties
server.port=9090
~~~

Khi đó gọi http://localhost:9090/probe. Lệnh curl với port 8080 sẽ không còn đúng nếu không có proxy hoặc service khác đang lắng nghe.

## 10. Xác minh phiên bản thật sự tại build và runtime

Cần xác minh tối thiểu bốn điều: **Boot version, web stack, server được chọn và version của server**. Nên làm theo thứ tự:

1. Xem spring-boot-starter-parent/BOM, version của Spring Boot Gradle plugin hoặc output của dependency management để biết Boot được quản lý ở phiên bản nào.
2. Xem dependency graph: starter-web hoặc webmvc cho MVC, starter-webflux cho WebFlux; phát hiện trùng Tomcat/Jetty/Undertow/Reactor Netty.
3. Đối chiếu bảng System Requirements của **đúng Boot version**: version major của server và mức Servlet API.
4. Khởi động ứng dụng và quan sát log/context/runtime thực tế; gửi HTTP request kiểm tra endpoint. Nếu cần, dùng integration test để xác minh môi trường kết nối đầy đủ.

Với Maven Wrapper:

~~~bash
./mvnw dependency:tree
~~~

Với Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Trong output, tìm spring-boot-starter-web, spring-boot-starter-webmvc, spring-boot-starter-webflux, spring-boot-starter-tomcat, spring-boot-starter-jetty, spring-boot-starter-undertow và spring-boot-starter-reactor-netty. Với Gradle, các lệnh trên áp dụng cho wrapper Unix/macOS; trên Windows có thể dùng gradlew.bat. Các dependency bị exclude hoặc đánh dấu conflict resolution cần được xem trên cấu hình runtimeClasspath chứ không chỉ đọc danh sách khai báo ban đầu.

Lúc ứng dụng khởi động, log thường cho biết embedded server và cổng đang lắng nghe. Tuy nhiên chuỗi log cụ thể thay đổi theo Boot version, logger và mức log, nên kiểm tra tên server/factory trong thông tin runtime thay vì phụ thuộc vào một chuỗi cố định.

## 11. Các tình huống thực tế

### Tình huống A: Đang ở Boot 3.5 và muốn dùng Undertow

Có thể dùng Spring MVC hoặc WebFlux với Undertow 2.3 vì cả hai cách chạy này nằm trong danh sách server hỗ trợ của Boot 3.5. Loại Tomcat mặc định nếu là MVC; hoặc Reactor Netty mặc định nếu là WebFlux. Đảm bảo không còn nhiều server factory bị nạp cùng lúc.

### Tình huống B: Nâng cấp ứng dụng Undertow từ Boot 3.5 sang Boot 4.1

Đây là thay đổi **môi trường chạy**, không chỉ đổi số version của dependency. Boot 4.1 chỉ liệt kê embedded Tomcat 11.0.x và Jetty 12.1.x cho Servlet stack. Hãy chọn server thay thế, rà soát code cấu hình phụ thuộc Undertow, kiểm tra package Jakarta Servlet và mức Servlet 6.1, thay starter, chạy lại integration test cho request routing, filter, cookie/session, HTTPS, timeout và graceful shutdown.

### Tình huống C: Dự án dùng WebClient nhưng muốn giữ Spring MVC

Có thể giữ starter MVC và bổ sung thư viện/client phù hợp để dùng WebClient gọi HTTP ra ngoài. Không nên mặc định kết luận server trở thành Reactor Netty vì thấy Netty trong dependency. Boot thường ưu tiên Servlet web application type khi cả MVC và WebFlux có mặt.

### Tình huống D: Chuyển WAR Boot 2.7 lên Boot 3.x hoặc 4.x

Phải đổi các API javax.servlet.* liên quan sang jakarta.servlet.* khi nâng lên Spring Boot 3+, rà soát phiên bản Java, Spring Framework, security/filter và Servlet container đích. Boot 4.x cần kiểm tra Servlet API 6.1 khi triển khai trong external container, cũng như các thay đổi dependency/auto-configuration tương ứng. Embedded jar và external WAR là hai cách đóng gói, không nên áp dụng trực tiếp ma trận embedded cho external server.

## 12. Các hiểu nhầm cần tránh

- **“WebFlux = Netty”:** Sai. Reactor Netty là mặc định, nhưng WebFlux cũng có thể chạy trên Tomcat/Jetty ở Boot 4.x, và cả Undertow ở Boot 3.x.
- **“Tomcat có mặt là MVC”:** Sai. Tomcat còn có thể phục vụ WebFlux qua reactive adapter.
- **“Boot 3 dùng một phiên bản Jetty”:** Sai. Boot 3.0/3.1 dùng Jetty 11 (Servlet 5.0), từ Boot 3.2 dùng Jetty 12 (Servlet 6.0).
- **“Cứ thêm starter Jetty là đổi server”:** Sai. Phải loại starter server mặc định và kiểm tra dependency graph.
- **“Reactor Netty nằm trong dependency là server thật”:** Chưa chắc. Nó có thể phục vụ WebClient, trong khi embedded server thực tế là Tomcat hoặc Jetty.
- **“Thấy server cùng major là Boot hỗ trợ”:** Sai. Chỉ những phối hợp được tài liệu đúng bản Boot công bố mới thuộc phạm vi hỗ trợ chính thức. Version patch, Servlet API, Java và BOM vẫn quan trọng.
- **“Undertow dùng được ở Boot 3 nên Boot 4 cũng vậy”:** Sai. Các tài liệu 4.x hiện chỉ liệt kê Tomcat và Jetty cho Servlet, thêm Reactor Netty cho reactive.
- **“Nâng từ 2.7 chỉ cần đổi Tomcat”:** Sai. Namespace Servlet đổi từ javax sang jakarta, Java tối thiểu đổi, và hệ sinh thái Spring Framework cũng nâng phiên bản.

## 13. Quy trình lựa chọn có thể áp dụng

1. **Chốt Spring Boot version** theo lifecycle, yêu cầu tương thích và chính sách nâng cấp của dự án.
2. **Chọn stack:** MVC cho mô hình Servlet thông dụng; WebFlux khi kiến trúc thật sự cần pipeline reactive và các dependency không chặn được thiết kế phù hợp.
3. **Lấy danh sách server được tài liệu đúng version cho phép:** Boot 3.5 có Tomcat/Jetty/Undertow cho Servlet, WebFlux thêm Reactor Netty; Boot 4.1 có Tomcat/Jetty cho Servlet, WebFlux thêm Reactor Netty.
4. **Chọn một server mặc định hoặc được hỗ trợ:** ưu tiên starter chính thức và BOM, hạn chế tự override version server trừ khi có căn cứ kiểm thử.
5. **Kiểm tra Servlet API/Jakarta/Java:** đặc biệt với ứng dụng WAR và quá trình nâng cấp major.
6. **Kiểm tra dependency graph, chạy ứng dụng, kiểm thử HTTP/TLS/session/filter và quan sát log**, rồi mới kết luận cấu hình chạy đúng server yêu cầu.

## Tài liệu chính thức để đối chiếu

- Spring Boot 2.7.18 — System Requirements: https://docs.spring.io/spring-boot/docs/2.7.18/reference/html/getting-started.html
- Spring Boot 3.0.13 — System Requirements: https://docs.spring.io/spring-boot/docs/3.0.13/reference/html/getting-started.html
- Spring Boot 3.1.12 — System Requirements: https://docs.spring.io/spring-boot/docs/3.1.12/reference/html/getting-started.html
- Spring Boot 3.2.10 — System Requirements: https://docs.spring.io/spring-boot/docs/3.2.10/reference/html/getting-started.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 3.5 — Embedded Web Servers: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 4.1 — System Requirements: https://docs.spring.io/spring-boot/4.1/system-requirements.html
- Spring Boot 4.1 — Embedded Web Servers: https://docs.spring.io/spring-boot/4.1/how-to/webserver.html
- Spring Boot 4.1 — Servlet Web Applications: https://docs.spring.io/spring-boot/4.1/reference/web/servlet.html
- Spring Boot 4.1 — Reactive Web Applications: https://docs.spring.io/spring-boot/4.1/reference/web/reactive.html
- Spring Boot 4.1 — Build Systems / Starters: https://docs.spring.io/spring-boot/4.1/reference/using/build-systems.html

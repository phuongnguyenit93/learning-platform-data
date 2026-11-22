# ServletWebServerFactory và ReactiveWebServerFactory trong Spring Boot

## 1. Bài học giải quyết điều gì?

Khi chạy một ứng dụng Spring Boot Web, ta thường chỉ gọi `SpringApplication.run(...)` rồi thấy Tomcat hoặc Reactor Netty khởi động. Vậy ai tạo máy chủ HTTP, chuyển cấu hình `server.port` thành cổng lắng nghe, và nối máy chủ với Spring MVC hoặc WebFlux?

Hai giao diện cốt lõi trả lời câu hỏi đó là:

- **`ServletWebServerFactory`**: tạo web server nhúng cho ứng dụng dựa trên **Servlet / Spring MVC**.
- **`ReactiveWebServerFactory`**: tạo web server nhúng cho ứng dụng **Reactive / Spring WebFlux**.

Cả hai đều là *factory*: chúng tạo đối tượng máy chủ `WebServer` cho `ApplicationContext`, còn Spring Boot quản lý thời điểm khởi động, dừng, cấu hình và gắn pipeline xử lý HTTP.

**Mục tiêu sau bài này:** nhận biết hai đường khởi động server; phân biệt “web stack” với “sản phẩm HTTP server”; hiểu tham số của `getWebServer(...)`; biết khi nào sửa `application.yml`, khi nào dùng `WebServerFactoryCustomizer`; chẩn đoán được lỗi sai factory, sai dependency hoặc trùng cổng.

> **Phiên bản ví dụ:** mã chạy độc lập bên dưới dùng Spring Boot **4.1.x**, Java 17 trở lên. Spring Boot 3.5 vẫn có cùng ý tưởng nhưng **tên package của các factory đã khác**; bảng đối chiếu ở mục 9 chỉ rõ sự khác nhau. Không trộn import của hai dòng phiên bản.

## 2. Factory, WebServer và web stack là ba vai trò khác nhau

- **Web stack** xác định mô hình tiếp nhận và xử lý HTTP: Spring MVC dựa vào Servlet, còn WebFlux dựa vào `HttpHandler` và cơ chế reactive.
- **Web server** là tiến trình/thành phần mở cổng mạng và tiếp nhận kết nối: Tomcat, Jetty, Reactor Netty... Một server như Tomcat có thể phục vụ cả ứng dụng MVC lẫn WebFlux theo cách tích hợp khác nhau.
- **Factory** là giao diện để Spring Boot tạo, tùy biến và gắn server tương ứng với stack đã chọn. Nó không phải `@RestController`, không tự định nghĩa route và cũng không xử lý từng request của nghiệp vụ.

Cả hai factory kế thừa `WebServerFactory`, và trả về `org.springframework.boot.web.server.WebServer`. Đối tượng `WebServer` có các thao tác vòng đời như `start()`, `stop()` và `getPort()`. Trong ứng dụng Boot chuẩn, **không tự gọi** `factory.getWebServer(...)` trong hàm `main`: `ApplicationContext` đảm nhiệm việc tạo và quản lý đối tượng đó.

### Chữ ký cốt lõi

~~~java
// Ý nghĩa chữ ký API trong Spring Boot 4.x, không phải chương trình Java độc lập:
public interface ServletWebServerFactory extends WebServerFactory {
    WebServer getWebServer(ServletContextInitializer... initializers);
}

public interface ReactiveWebServerFactory extends WebServerFactory {
    WebServer getWebServer(HttpHandler httpHandler);
}
~~~

Hai chữ ký khác nhau ở **thứ được gắn vào server**:

1. `ServletContextInitializer...` khởi tạo Servlet context, cho phép Boot đăng ký Servlet, Filter, Listener, ví dụ `DispatcherServlet` của Spring MVC. Có thể có nhiều initializer.
2. `HttpHandler` là điểm vào HTTP thống nhất của Spring WebFlux. Boot tạo/cung cấp handler rồi đưa vào factory reactive; server cụ thể sẽ chuyển request đến handler này.

Factory tạo server đã được cấu hình nhưng chưa phải là lời hứa “request phục vụ được ngay lập tức”. Boot điều phối `start()` trong vòng đời refresh của context; chỉ sau khi server sẵn sàng thì HTTP mới có thể được phục vụ bình thường.

## 3. Hai luồng khởi động song song

~~~text
Servlet: SpringApplication
   -> WebApplicationType.SERVLET
   -> ServletWebServerApplicationContext
   -> ServletWebServerFactory (Tomcat/Jetty...)
   -> getWebServer(ServletContextInitializer...)
   -> ServletContext + DispatcherServlet + Filter
   -> WebServer.start() -> HTTP request -> Spring MVC

Reactive: SpringApplication
   -> WebApplicationType.REACTIVE
   -> ReactiveWebServerApplicationContext
   -> ReactiveWebServerFactory (Netty/Tomcat/Jetty...)
   -> getWebServer(HttpHandler)
   -> WebFlux HttpHandler / WebHandler chain
   -> WebServer.start() -> HTTP request -> WebFlux
~~~

Trình tự khái quát khi khởi động:

1. `SpringApplication` suy ra `WebApplicationType` từ classpath, trừ khi ứng dụng cấu hình/đặt rõ loại.
2. Boot tạo loại `ApplicationContext` phù hợp và kích hoạt auto-configuration của stack đang dùng.
3. Auto-configuration tạo **một factory phù hợp** nếu chưa có bean do ứng dụng cung cấp và các điều kiện classpath thỏa mãn.
4. Boot bind thuộc tính `server.*`, áp dụng các bean `WebServerFactoryCustomizer`, sau đó context gọi `getWebServer(...)`.
5. Đường servlet đăng ký các thành phần Servlet; đường reactive gắn `HttpHandler`; context khởi động `WebServer` trong quá trình refresh.
6. Sau khi server sẵn sàng, Boot có thể công bố `WebServerInitializedEvent`. Khi đóng context, Boot dừng server; trong ứng dụng thông thường, không cần tự quản lý `start()/stop()`.

Chi tiết triển khai tùy phiên bản và server cụ thể, nhưng trách nhiệm giữa **context → factory → web server → bộ xử lý HTTP** vẫn là chìa khóa đọc log và debug.

## 4. Bảng so sánh chính xác

| Tiêu chí | `ServletWebServerFactory` | `ReactiveWebServerFactory` |
|---|---|---|
| Stack chính | Servlet / Spring MVC | Reactive / Spring WebFlux |
| Context tạo server | `ServletWebServerApplicationContext` | `ReactiveWebServerApplicationContext` |
| Phương thức | `getWebServer(ServletContextInitializer...)` | `getWebServer(HttpHandler)` |
| Đối tượng đưa vào server | Các initializer đăng ký Servlet/Filter/Listener | `HttpHandler` chuyển tiếp request cho WebFlux |
| Server thường gặp trong Boot 4.x | Tomcat, Jetty | Reactor Netty, Tomcat, Jetty |
| Factory cụ thể minh họa | `TomcatServletWebServerFactory`, `JettyServletWebServerFactory` | `NettyReactiveWebServerFactory`, `TomcatReactiveWebServerFactory`, `JettyReactiveWebServerFactory` |
| Cách tùy biến chung | `WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>` | `WebServerFactoryCustomizer<ConfigurableReactiveWebServerFactory>` |

**Đừng đồng nhất “reactive” với “Netty”.** Netty là HTTP server mặc định của starter WebFlux, không phải định nghĩa của ReactiveWebServerFactory. WebFlux cũng có thể chạy với Tomcat hoặc Jetty thông qua adapter. Tương tự, “Tomcat” không tự chứng minh ứng dụng đang dùng MVC: phải nhìn loại context, stack và factory.

### Boot chọn loại nào?

- Với starter MVC và các thư viện tương ứng, Boot thường chọn `SERVLET`.
- Với starter WebFlux, và không có cơ sở để Boot chọn MVC, Boot thường chọn `REACTIVE`.
- Khi **cả Spring MVC và WebFlux cùng xuất hiện** trên classpath, Boot mặc định ưu tiên **MVC / SERVLET**. Nhiều dự án MVC thêm WebFlux chỉ để dùng `WebClient`; điều đó không tự chuyển server sang reactive.
- Có thể đặt `spring.main.web-application-type=reactive`, `servlet` hoặc `none` (hoặc dùng `SpringApplication.setWebApplicationType(...)`), nhưng cần có đủ thư viện và bean tương ứng. Ép loại web không tự bổ sung dependency còn thiếu.

## 5. Cấu hình thông thường: ưu tiên thuộc tính trước

Ví dụ `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8085
  address: 127.0.0.1
  shutdown: graceful
spring:
  main:
    web-application-type: servlet
~~~

`server.port` và `server.address` áp dụng cho server đang chạy, không phụ thuộc việc phía dưới là factory servlet hay reactive. `shutdown: graceful` yêu cầu cơ chế dừng êm có hỗ trợ theo phiên bản/server. Trường `spring.main.web-application-type` chỉ cần khi thật sự muốn ghi đè cơ chế tự nhận diện.

Một số cổng có ý nghĩa khác nhau:

- `server.port=8080`: mặc định cho ứng dụng web chạy độc lập nếu không cấu hình gì.
- `server.port=0`: nhờ hệ điều hành cấp cổng đang trống; lấy **cổng thực** từ `WebServerInitializedEvent` hoặc môi trường test sau khi server đã khởi tạo. Không suy đoán cổng từ cấu hình 0.
- `server.port=-1`: tắt các HTTP endpoint trong khi vẫn có thể tạo web application context; khác với chế độ `web-application-type=none`, vốn không tạo web server của ứng dụng.
- Nếu cổng đã bị tiến trình khác chiếm, server có thể fail với lỗi bind/`PortInUseException`; đó không nhất thiết là lỗi factory.

Đối với tùy chọn riêng từng server, dùng các namespace được tài liệu phiên bản hỗ trợ, ví dụ `server.tomcat.*`, `server.jetty.*` hoặc `server.netty.*`. Không giả định mọi thuộc tính của Tomcat tồn tại ở Netty.

## 6. Thực hành A — factory của ứng dụng Servlet/MVC

Tạo **dự án riêng** dùng Spring Boot 4.1.x, Java 17+ và Gradle, thêm dependency MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
}
~~~

Với dự án có Spring Boot Gradle plugin và dependency management do Spring Initializr tạo sẵn, đặt tệp sau tại `src/main/java/demo/servlet/ServletFactoryDemo.java`:

~~~java
package demo.servlet;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.server.servlet.ConfigurableServletWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ServletFactoryDemo {

    public static void main(String[] args) {
        SpringApplication.run(ServletFactoryDemo.class, args);
    }

    @GetMapping("/stack")
    public String stack() {
        return "SERVLET: Spring MVC";
    }

    @Bean
    WebServerFactoryCustomizer<ConfigurableServletWebServerFactory> servletPort() {
        return factory -> factory.setPort(9091);
    }
}
~~~

Chạy từ thư mục gốc dự án bằng `./gradlew bootRun` trên macOS/Linux hoặc `gradlew.bat bootRun` trên Windows. Khi server đã khởi động, mở terminal khác:

~~~bash
curl -s http://localhost:9091/stack
~~~

Phần **nội dung HTTP response body** mong đợi là:

~~~text
SERVLET: Spring MVC
~~~

Giải thích:

- Starter MVC đưa Servlet stack và server nhúng phù hợp vào classpath (mặc định là Tomcat).
- Boot tạo `ServletWebServerFactory` tương ứng và cung cấp các `ServletContextInitializer`, trong đó có cơ chế đăng ký `DispatcherServlet`.
- Bean `WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>` nhận factory **trước khi server chạy** và đặt cổng 9091. Nó không trực tiếp mở socket và không tạo server thứ hai.
- `@GetMapping` chạy qua Spring MVC; response là chuỗi văn bản trả về từ handler.

Giá trị cổng ở đây được cố ý đặt bằng code để quan sát customizer; trong ứng dụng thực tế, **`server.port` thường đơn giản và dễ cấu hình theo môi trường hơn**. Nếu vừa cấu hình cổng trong file vừa dùng customizer sửa cổng, cần hiểu thứ tự các customizer và chọn một nguồn cấu hình rõ ràng.

## 7. Thực hành B — factory của ứng dụng Reactive/WebFlux

Tạo **một dự án khác** cũng dùng Spring Boot 4.1.x, Java 17+ và Gradle, nhưng chỉ dùng starter WebFlux:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Đặt tệp `src/main/java/demo/reactive/ReactiveFactoryDemo.java`:

~~~java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.server.reactive.ConfigurableReactiveWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class ReactiveFactoryDemo {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveFactoryDemo.class, args);
    }

    @GetMapping("/stack")
    public Mono<String> stack() {
        return Mono.just("REACTIVE: Spring WebFlux");
    }

    @Bean
    WebServerFactoryCustomizer<ConfigurableReactiveWebServerFactory> reactivePort() {
        return factory -> factory.setPort(9092);
    }
}
~~~

Chạy `./gradlew bootRun` hoặc `gradlew.bat bootRun`, rồi gửi request:

~~~bash
curl -s http://localhost:9092/stack
~~~

Response body mong đợi:

~~~text
REACTIVE: Spring WebFlux
~~~

Giải thích:

- Starter WebFlux mặc định dùng Reactor Netty; Boot tạo `NettyReactiveWebServerFactory`, một hiện thực của `ReactiveWebServerFactory`.
- WebFlux xây dựng `HttpHandler` và factory gắn nó vào HTTP server reactive. Khi request đến, WebFlux chuyển tiếp đến handler trả về `Mono<String>`.
- Customizer dùng `ConfigurableReactiveWebServerFactory` để đặt cổng 9092 theo API chung. Với tùy biến chuyên biệt cho Netty mới cần `WebServerFactoryCustomizer<NettyReactiveWebServerFactory>` và các API Netty tương ứng.
- `Mono` thể hiện kết quả bất đồng bộ ở tầng handler; một phương thức trả về `Mono` **không tự chứng minh** ứng dụng đang dùng reactive web server nếu toàn bộ ứng dụng vẫn được cấu hình theo MVC.

**Hai chương trình ở mục 6–7 là hai ứng dụng độc lập.** Không đặt hai starter và hai class `main` vào cùng dự án khi mục đích chỉ là so sánh factory. Trong Boot 3.5, thay import như mục 9 và dùng starter MVC là `spring-boot-starter-web`.

## 8. Khi nào dùng customizer, khi nào tự khai báo factory?

Thứ tự lựa chọn an toàn, dễ bảo trì:

1. **`application.properties` hoặc `application.yml`** cho cổng, địa chỉ bind, nén, TLS và các tùy chọn đã được Boot hỗ trợ.
2. **`WebServerFactoryCustomizer<T>`** khi cần cấu hình bằng mã hoặc có tính năng riêng của Tomcat/Jetty/Netty chưa được expose qua properties. Chọn `T` theo stack hoặc loại factory cụ thể.
3. **Tự khai báo bean `ServletWebServerFactory` hoặc `ReactiveWebServerFactory`** chỉ khi cần thay hẳn cách tạo server hoặc chọn hiện thực đặc biệt. Bean này có thể khiến auto-configuration mặc định lùi lại; các customizer của Boot vẫn có thể được áp dụng cho factory do bạn cung cấp.

Ví dụ chỉ minh họa cấu hình, **không phải chương trình tự chạy**:

~~~java
// Bean đặt trong một @Configuration của ứng dụng MVC:
@Bean
WebServerFactoryCustomizer<ConfigurableServletWebServerFactory> commonServerSettings() {
    return server -> server.setPort(9091);
}
~~~

**Lưu ý vòng đời:** customizer thường được gọi qua `BeanPostProcessor` khá sớm khi context chưa hoàn tất. Tránh phụ thuộc vào bean khởi tạo muộn hoặc làm network I/O phức tạp trong `customize(...)`. Đừng mở server bằng tay trong customizer; việc start/stop là trách nhiệm của Boot.

Nếu cố khai báo đồng thời nhiều factory phù hợp với cùng context, hoặc factory không hợp với loại web application, ứng dụng có thể lỗi khi tìm factory để khởi tạo. Hãy để auto-configuration làm việc trừ khi bạn thực sự có lý do thay thế.

## 9. Quan trọng khi đọc tài liệu hoặc code giữa Boot 3.5 và 4.x

Tên giao diện và ý tưởng tương đồng, **nhưng package đã đổi ở Spring Boot 4**:

| Thành phần | Spring Boot 3.5 | Spring Boot 4.x |
|---|---|---|
| `ServletWebServerFactory` | `org.springframework.boot.web.servlet.server.ServletWebServerFactory` | `org.springframework.boot.web.server.servlet.ServletWebServerFactory` |
| `ConfigurableServletWebServerFactory` | `org.springframework.boot.web.servlet.server.ConfigurableServletWebServerFactory` | `org.springframework.boot.web.server.servlet.ConfigurableServletWebServerFactory` |
| `ReactiveWebServerFactory` | `org.springframework.boot.web.reactive.server.ReactiveWebServerFactory` | `org.springframework.boot.web.server.reactive.ReactiveWebServerFactory` |
| `ConfigurableReactiveWebServerFactory` | `org.springframework.boot.web.reactive.server.ConfigurableReactiveWebServerFactory` | `org.springframework.boot.web.server.reactive.ConfigurableReactiveWebServerFactory` |
| `TomcatServletWebServerFactory` | `org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory` | `org.springframework.boot.tomcat.servlet.TomcatServletWebServerFactory` |
| `NettyReactiveWebServerFactory` | `org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory` | `org.springframework.boot.reactor.netty.NettyReactiveWebServerFactory` |
| MVC starter thường dùng | `spring-boot-starter-web` | `spring-boot-starter-webmvc` (starter cũ `-web` chuyển tiếp/đã được thay thế) |

Trong Boot 3.5 còn có hiện thực Undertow; danh sách server hỗ trợ có thể thay đổi qua major version. Khi sao chép code cấu hình chuyên biệt, hãy kiểm tra **phiên bản starter và package thực tế** của project trước khi thay import hoặc thay server.

## 10. Quan sát và chẩn đoán khi server không khởi động

| Triệu chứng | Gợi ý kiểm tra | Cách xử lý |
|---|---|---|
| `Missing ServletWebServerFactory bean` hoặc thông báo không có servlet web server factory | Ứng dụng đang ở `SERVLET` nhưng không có factory phù hợp; starter/container bị exclude hoặc auto-configuration bị tắt | Kiểm tra dependency tree, starter MVC, điều kiện auto-config và `spring.main.web-application-type` |
| `Missing ReactiveWebServerFactory bean` | `REACTIVE` được chọn nhưng thiếu starter/server phù hợp hoặc cấu hình tự động bị vô hiệu | Xác nhận `spring-boot-starter-webflux` và HTTP server reactive; tìm bean factory bị loại |
| Dùng WebFlux nhưng log cho thấy `ServletWebServerApplicationContext`/Tomcat servlet | Hai starter MVC và WebFlux cùng có mặt, Boot ưu tiên MVC | Xem lại mục tiêu kiến trúc; loại starter MVC nếu chỉ cần WebFlux, hoặc chủ động chọn type với dependency đúng |
| Không bind được `8080`/`9091` | Cổng đã được sử dụng hoặc bind address không hợp lệ | Đổi `server.port`, giải phóng cổng, hoặc dùng port 0 khi test |
| Đặt `server.port=8085` nhưng chạy ở cổng khác | Customizer khác ghi đè, biến môi trường hoặc tham số dòng lệnh có độ ưu tiên cao hơn | Kiểm tra nguồn cấu hình và thứ tự customizer |
| `getWebServer()` trả server nhưng request chưa vào được | Factory chỉ cung cấp server; chưa đến giai đoạn `start()` hoặc context startup thất bại | Kiểm tra exception khởi động, lifecycle, log “Started”, readiness |
| Lỗi `ClassNotFoundException` cho import factory | Copy code khác major version hoặc thiếu module/server starter | Đối chiếu bảng package Boot 3.5/4.x, sửa đúng dependency, không dùng import chéo |

**Cách xem cổng thực khi server đã sẵn sàng:** quan sát log hoặc đăng ký listener `WebServerInitializedEvent` rồi đọc `event.getWebServer().getPort()`. Trong test web chạy cổng ngẫu nhiên có thể dùng `@LocalServerPort` theo API test của phiên bản đang dùng. Tránh đọc cổng thực quá sớm trong quá trình tạo bean.

**Thứ tự debug nên theo:** xác định `WebApplicationType` → xác định starter và server trên classpath → xem factory bean/context đúng stack chưa → xem cấu hình/customizer → xem lỗi bind và lifecycle. Đọc stack trace từ **nguyên nhân gốc** trước khi thay bean factory.

## 11. Bài tập tự kiểm tra

1. Ứng dụng có cả starter MVC và WebFlux, nhưng chỉ muốn dùng `WebClient`: Boot thường chọn factory nào? **Đáp án:** factory Servlet, vì MVC được ưu tiên khi cả hai stack cùng hiện diện.
2. Reactor Netty có phải điều kiện bắt buộc của `ReactiveWebServerFactory` không? **Không.** Reactive factory cũng có hiện thực cho Tomcat/Jetty ở phiên bản hỗ trợ.
3. Vì sao chữ ký servlet nhận `ServletContextInitializer...`, còn reactive nhận `HttpHandler`? **Vì** một bên khởi tạo Servlet context và các thành phần đăng ký theo Servlet API, bên kia đưa pipeline xử lý HTTP của WebFlux vào server.
4. Muốn đổi 8080 sang 9090 ở các môi trường mà không biên dịch lại, sửa gì? **`server.port`** trong cấu hình hoặc biến môi trường, thay vì tự tạo factory.
5. Khi nào cần biết `WebServer.start()`? **Khi giải thích vòng đời và debug** thời điểm server sẵn sàng; mã ứng dụng Boot thông thường không gọi nó trực tiếp.

## 12. Tài liệu tham chiếu

- Spring Boot — [Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html): chọn server, cổng, customizer, factory bean.
- Spring Boot — [Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): WebFlux, HTTP server và customizer.
- Javadoc Boot 4.x — [ServletWebServerFactory](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/web/server/servlet/ServletWebServerFactory.html), [ReactiveWebServerFactory](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/web/server/reactive/ReactiveWebServerFactory.html).
- Javadoc Boot 3.5 — [ServletWebServerApplicationContext](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.html), [ConfigurableReactiveWebServerFactory](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/reactive/server/ConfigurableReactiveWebServerFactory.html).

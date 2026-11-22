# Phân biệt cấu hình máy chủ web với cấu hình tầng xử lý yêu cầu

## 1. Hai tầng cấu hình khác nhau

Một ứng dụng Spring Boot web có hai nhóm cấu hình thường bị nhầm lẫn:

1. **Cấu hình máy chủ web (web server/container):** quyết định ứng dụng lắng nghe ở đâu và container tiếp nhận kết nối HTTP như thế nào. Ví dụ: port, địa chỉ bind, TLS, compression, giới hạn connection/thread, graceful shutdown và session.
2. **Cấu hình tầng xử lý yêu cầu (request-processing layer):** quyết định Spring nhận diện request nào, chọn controller/handler nào, áp dụng filter/interceptor/security ra sao, bind dữ liệu request, chuyển đổi response và xử lý exception thế nào.

Hai tầng liên quan nhưng không thay thế nhau. Đổi port không thay đổi URL mapping của controller. Thêm MVC interceptor không mở port, không cấu hình TLS và không tăng số kết nối mà Tomcat chấp nhận. Đặt context path không tạo controller; controller mapping không cấu hình connector.

Bài này dùng **Spring Boot 3.3.x, Java 17+ và Spring MVC trên Servlet stack** làm ví dụ chính, sau đó đối chiếu với WebFlux. Mục tiêu là chọn đúng extension point, đọc đúng auto-configuration và kiểm thử đúng tầng.

## 2. Luồng xử lý một HTTP request

Với Spring MVC chạy trên embedded Tomcat, luồng điển hình:

~~~text
Client
  |
  v
Network socket / TLS / HTTP connector
  |
  v
Embedded servlet container (Tomcat)
  |
  v
Servlet Filter chain
  |  - Spring Security FilterChainProxy
  |  - application filters
  v
DispatcherServlet
  |
  v
HandlerMapping ----> tìm controller/handler phù hợp
  |
  v
HandlerAdapter
  |
  v
Controller method
  |  - argument resolution
  |  - validation
  |  - business service
  v
Return-value handling / HttpMessageConverter
  |
  v
Servlet response -> Filter chain -> Connector -> Client
~~~

Các nhánh khác trong luồng:

- Không tìm thấy handler: Spring MVC có thể trả 404 hoặc chuyển qua resource/error handling tùy cấu hình.
- Controller hoặc argument resolver ném exception: HandlerExceptionResolver và @ControllerAdvice có thể xử lý.
- Interceptor có callback trước/sau handler và khi request hoàn tất; nó chạy sau khi MVC đã chọn handler.
- Servlet Filter chạy ở tầng Servlet container, trước DispatcherServlet theo mapping/order của filter, nên có thể bao phủ request không đi qua controller.
- TLS handshake, socket, connector limits và server thread pool nằm trước Spring MVC; controller không cấu hình được các phần này.

Sơ đồ là đường đi điển hình. Error dispatch, static resources, async request, servlet khác và management context có thể có đường xử lý riêng.

## 3. Cấu hình máy chủ web: port, connector và vòng đời server

### 3.1. Các property phổ biến

| Property | Tác động | Ví dụ |
|---|---|---|
| **server.port** | Port HTTP mà embedded server lắng nghe | 8080 |
| **server.address** | Network interface để bind | 127.0.0.1 |
| **server.servlet.context-path** | Prefix chung của ứng dụng Servlet | /shop |
| **server.compression.enabled** | Bật nén response ở server | true |
| **server.compression.mime-types** | MIME type được nén | application/json |
| **server.compression.min-response-size** | Ngưỡng kích thước response | 2KB |
| **server.shutdown** | Chính sách shutdown server | graceful |
| **server.ssl.*** | TLS certificate, key, protocol và SSL settings | theo certificate |
| **server.tomcat.threads.max** | Giới hạn thread xử lý của Tomcat | 200 (ví dụ) |
| **server.tomcat.max-connections** | Số connection tối đa Tomcat chấp nhận | theo tải |
| **server.tomcat.accept-count** | Hàng đợi connection khi đạt giới hạn | theo tải |
| **server.servlet.session.timeout** | Thời hạn session Servlet | 30m |

Tên và giá trị property phụ thuộc server. Nhóm server.tomcat.* chỉ có ý nghĩa khi embedded server là Tomcat; Jetty và Undertow có namespace riêng. Không copy thông số thread/connection của Tomcat sang server khác.

Ví dụ cấu hình:

~~~yaml
server:
  port: 8080
  address: 0.0.0.0
  compression:
    enabled: true
    min-response-size: 2KB
    mime-types:
      - application/json
      - text/html
  shutdown: graceful
  servlet:
    context-path: /shop
    session:
      timeout: 30m
~~~

Khi cấu hình này được dùng, controller có mapping /orders/{id} được gọi qua path /shop/orders/42. Prefix /shop đến từ Servlet context path; nó không phải một phần của @RequestMapping. Port 8080 và địa chỉ bind 0.0.0.0 quyết định nơi client kết nối.

### 3.2. Phân biệt port, context path và controller mapping

Giả sử:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /shop
~~~

Controller:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderView find(@PathVariable long id) {
        return new OrderView(id, "ACCEPTED");
    }
}
~~~

Request đầy đủ là http://localhost:8080/shop/orders/42:

- **localhost:8080:** địa chỉ và port server.
- **/shop:** context path của ứng dụng Servlet.
- **/orders/42:** mapping do Spring MVC/controller khai báo.

Nếu đổi server.port thành 9090, URL đổi port nhưng mapping vẫn là /orders/42. Nếu đổi context path thành /api, prefix URL thay đổi nhưng controller không cần đổi mapping. Nếu đổi @RequestMapping, route thay đổi nhưng connector vẫn lắng nghe cùng port.

Đừng đặt server.servlet.context-path vào MVC interceptor để thêm prefix; interceptor không chịu trách nhiệm định tuyến ở cấp container.

### 3.3. TLS, compression và connection limits

Các thao tác sau thuộc server/container:

- TLS handshake và lựa chọn certificate.
- HTTP connector, keep-alive, max connections, accept queue.
- Server worker threads và giới hạn request concurrency.
- Nén response ở tầng server.
- Graceful shutdown và thời gian chờ request đang xử lý.
- Servlet session/cookie ở container.

Nếu HTTPS không hoạt động, kiểm tra server.ssl.*, certificate/key, protocol, port và reverse proxy trước. Sửa controller hoặc MVC converter không thể sửa TLS handshake.

Nếu server quá tải, quan sát connection, queue, thread pool, request duration và downstream dependency. Tăng server.tomcat.threads.max không tự làm database hoặc service downstream nhanh hơn; tăng thread có thể làm tăng áp lực lên dependency và bộ nhớ.

### 3.4. Tùy biến server factory

Khi property có sẵn không đủ, Spring Boot cho phép tùy biến factory trước khi server được tạo. Với Servlet stack, extension point thường dùng là WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>.

~~~java
package example.web;

import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.servlet.server.ConfigurableServletWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ServerFactoryConfiguration {

    @Bean
    WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>
            servletServerCustomizer() {
        return factory -> factory.setPort(9090);
    }
}
~~~

Đây là một cấu hình Java hoàn chỉnh về mặt API cho Servlet web application có Spring Boot Web. Khi customizer được áp dụng, factory dùng port 9090. Nếu đồng thời khai báo server.port, hãy xác định nguồn cấu hình và thứ tự áp dụng để tránh hai nơi cùng sở hữu một quyết định. Với cổng thay đổi theo môi trường, property thường rõ ràng hơn việc hard-code trong customizer.

Khi thật sự cần Tomcat API, dùng WebServerFactoryCustomizer<TomcatServletWebServerFactory> và connector/context customizer phù hợp. Đừng đưa code Tomcat vào cấu hình dùng chung cho Jetty hoặc Undertow.

**Thời điểm:** server factory customizer chạy trong quá trình chuẩn bị web server, trước khi server bắt đầu nhận request. Nó không phải callback cho mỗi HTTP request.

## 4. Cấu hình tầng xử lý yêu cầu trong Spring MVC

### 4.1. DispatcherServlet và các thành phần MVC

Spring Boot auto-configures Spring MVC khi ứng dụng dùng Servlet web stack và các điều kiện phù hợp. Các thành phần quan trọng:

- **DispatcherServlet:** front controller nhận request và điều phối xử lý.
- **HandlerMapping:** tìm handler phù hợp với request.
- **HandlerAdapter:** gọi handler đã chọn.
- **HandlerInterceptor:** hook trước/sau handler và sau khi request hoàn tất.
- **HttpMessageConverter:** đọc request body và ghi response body, ví dụ JSON.
- **HandlerExceptionResolver / @ControllerAdvice:** xử lý exception trong quá trình MVC.
- **WebMvcConfigurer:** extension point để bổ sung interceptor, formatter, converter, argument resolver, CORS mapping và cấu hình MVC khác.

Các extension point này thay đổi cách Spring xử lý request sau khi request đã đến Servlet container. Chúng không thay port, TLS, connector hoặc server thread pool.

### 4.2. Controller và request mapping

Controller khai báo route và hành vi ứng dụng:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderView find(@PathVariable long id) {
        return new OrderView(id, "ACCEPTED");
    }
}

record OrderView(long id, String status) {}
~~~

Spring MVC tìm method phù hợp qua HandlerMapping, rồi HandlerAdapter gọi method. Path variable id được resolve và convert sang kiểu long. Object trả về được ghi response bằng message converter, thường là JSON nếu Jackson có mặt và content negotiation phù hợp.

Đây là cấu hình tầng ứng dụng/request, không phải cấu hình web server.

### 4.3. WebMvcConfigurer: tùy biến MVC

Ví dụ đăng ký interceptor:

~~~java
package example.web;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
class MvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new RequestTraceInterceptor())
                .addPathPatterns("/orders/**");
    }

    static class RequestTraceInterceptor implements HandlerInterceptor {

        @Override
        public boolean preHandle(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler) {
            request.setAttribute("request-start-nanos", System.nanoTime());
            response.setHeader("X-Mvc-Interceptor", "applied");
            return true;
        }
    }
}
~~~

Interceptor trên chỉ áp dụng cho handler path /orders/**. Nó thêm request attribute và response header để minh họa thời điểm MVC đã chọn handler. Nó không chạy như một network connector và không thay đổi cổng server.

Nếu muốn một thao tác bao phủ cả request không có MVC handler, static resource hoặc servlet khác, hãy xem Servlet Filter thay vì MVC interceptor.

### 4.4. Servlet Filter: nằm trước DispatcherServlet

Filter là cơ chế Servlet chuẩn. Nó có thể kiểm tra request/response trước khi request đi vào DispatcherServlet, hoặc sau khi chain trả về. Ví dụ đăng ký filter:

~~~java
package example.web;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.web.filter.OncePerRequestFilter;

@Configuration(proxyBeanMethods = false)
class FilterConfiguration {

    @Bean
    FilterRegistrationBean<OncePerRequestFilter> requestMarkerFilter() {
        OncePerRequestFilter filter = new OncePerRequestFilter() {
            @Override
            protected void doFilterInternal(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    FilterChain filterChain)
                    throws ServletException, IOException {
                response.setHeader("X-Request-Filter", "applied");
                filterChain.doFilter(request, response);
            }
        };

        FilterRegistrationBean<OncePerRequestFilter> registration =
                new FilterRegistrationBean<>();
        registration.setFilter(filter);
        registration.addUrlPatterns("/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }
}
~~~

Filter minh họa áp dụng cho URL pattern được đăng ký. filterChain.doFilter chuyển request sang filter tiếp theo hoặc servlet. Nếu không gọi nó, filter có thể chủ động kết thúc request; điều này phải được làm có chủ đích.

Không dùng filter tùy tiện để thay controller mapping hoặc business authorization. Với authentication/authorization, dùng Spring Security filter chain. Filter order có thể ảnh hưởng thứ tự thực thi; không dựa vào thứ tự component scan.

### 4.5. Filter và HandlerInterceptor khác nhau

| Tiêu chí | Servlet Filter | Spring MVC HandlerInterceptor |
|---|---|---|
| Nằm ở đâu? | Servlet container | Spring MVC |
| Thời điểm | Trước/sau servlet theo filter chain | Sau khi MVC chọn handler, quanh handler execution |
| Phạm vi | URL pattern/servlet mapping | Handler mapping/path pattern |
| Request không vào controller | Có thể chạy nếu mapping khớp | Không chạy nếu không có MVC handler tương ứng |
| Thường dùng | Security, request wrapping, correlation ID, CORS ở servlet layer | Logic liên quan MVC handler, locale/context hoặc timing |
| Cấu hình | Filter, FilterRegistrationBean, Spring Security | WebMvcConfigurer.addInterceptors |

Spring Security sử dụng Servlet Filter chain (thông qua FilterChainProxy) để bảo vệ request. Không coi HandlerInterceptor là lớp thay thế Spring Security, đặc biệt khi cần bảo vệ static resources, error dispatch, servlet khác hoặc luồng không đi qua MVC handler.

## 5. Cấu hình khác nhau giữa Spring MVC và WebFlux

Không phải mọi ứng dụng Spring Boot web đều chạy Servlet stack.

| Khía cạnh | Spring MVC / Servlet | Spring WebFlux / Reactive |
|---|---|---|
| Server phổ biến | Tomcat, Jetty, Undertow | Reactor Netty, Tomcat/Jetty reactive support |
| Server factory | Servlet web server factory | Reactive web server factory |
| Front controller | DispatcherServlet | DispatcherHandler |
| Filter | jakarta.servlet.Filter | WebFilter |
| MVC config | WebMvcConfigurer | WebFluxConfigurer |
| Controller | MVC handler method | Reactive handler method, thường trả Mono/Flux |
| Blocking I/O | Mô hình Servlet truyền thống có thể dùng blocking | Tránh blocking trên event-loop; ưu tiên reactive/non-blocking API |

Một cấu hình dùng WebMvcConfigurer không tùy biến WebFlux. Tương tự, jakarta.servlet.Filter không phải WebFlux WebFilter.

Trong WebFlux, request đi qua reactive HTTP server, WebFilter chain và DispatcherHandler. Có thể dùng WebServerFactoryCustomizer<ConfigurableReactiveWebServerFactory> để tùy biến reactive server factory, nhưng không dùng Servlet-specific factory. Nếu classpath chứa cả MVC và WebFlux, xác định loại application context mà Spring Boot đã chọn thay vì suy đoán từ một dependency riêng lẻ.

## 6. Ví dụ ứng dụng Spring Boot 3.3: đặt đúng cấu hình vào đúng tầng

Một project tối thiểu có thể dùng các dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Ứng dụng:

~~~java
package example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebExampleApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebExampleApplication.class, args);
    }
}
~~~

Controller:

~~~java
package example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderView find(@PathVariable long id) {
        return new OrderView(id, "ACCEPTED");
    }
}

record OrderView(long id, String status) {}
~~~

Cấu hình server trong application.yml:

~~~yaml
server:
  port: 8080
  compression:
    enabled: true
    min-response-size: 2KB
~~~

Cấu hình Filter và MVC interceptor ở phần trước có thể đặt trong package được component scan phát hiện. Nếu thêm server factory customizer đặt port 9090, giá trị đó sẽ là một nguồn cấu hình bổ sung; hãy bỏ một trong hai nguồn hoặc quy định rõ chính sách để tránh xung đột.

Sau khi chạy ứng dụng, request:

~~~bash
curl -i http://localhost:8080/orders/42
~~~

Response minh họa (thứ tự header có thể khác):

~~~http
HTTP/1.1 200
Content-Type: application/json
X-Request-Filter: applied
X-Mvc-Interceptor: applied

{"id":42,"status":"ACCEPTED"}
~~~

Header filter được thêm ở Servlet Filter; header interceptor được thêm sau khi Spring MVC đã chọn handler. JSON được tạo từ controller return value và message converter. Port 8080 đến từ server configuration.

## 7. Property nào thuộc tầng nào?

| Nhu cầu | Cấu hình/extension point phù hợp | Không nên dùng |
|---|---|---|
| Đổi port lắng nghe | server.port hoặc server factory customizer | @RequestMapping, interceptor |
| Bind vào interface cụ thể | server.address | MVC CORS mapping |
| Prefix chung cho ứng dụng Servlet | server.servlet.context-path | Thêm prefix trong mỗi controller |
| TLS/certificate | server.ssl.* hoặc reverse proxy/ingress theo kiến trúc | Controller, HttpMessageConverter |
| Nén response ở server | server.compression.* hoặc proxy | HandlerInterceptor |
| Giới hạn Tomcat threads/connections | server.tomcat.* hoặc Tomcat factory customizer | @Async, MVC interceptor |
| Route request đến controller | @RequestMapping / HandlerMapping | server.port |
| Thay đổi JSON serialization | Jackson configuration / HttpMessageConverter / builder customizer | Tomcat connector |
| Thêm logic trước servlet | Servlet Filter / FilterRegistrationBean | WebMvcConfigurer |
| Logic quanh MVC handler | HandlerInterceptor / WebMvcConfigurer | Server factory customizer |
| Authentication/authorization | Spring Security SecurityFilterChain | MVC interceptor tự viết |
| Xử lý exception controller | @ControllerAdvice / HandlerExceptionResolver | Connector error page cho mọi trường hợp |
| Thêm formatter/converter MVC | WebMvcConfigurer | WebServerFactoryCustomizer |

### Context path và management path

server.servlet.context-path ảnh hưởng ứng dụng Servlet chính. Actuator có management base path riêng, và management server có thể chạy port riêng qua management.server.port. Đây là cấu hình management web server/context, không phải mapping controller nghiệp vụ. Khi dùng port riêng, cần bảo vệ management endpoint bằng network policy và security phù hợp.

## 8. Đọc auto-configuration theo đúng tầng

Trong Spring Boot 3.3, các auto-configuration quan trọng của Servlet web application gồm:

- **ServletWebServerFactoryAutoConfiguration:** tạo/cấu hình Servlet web server factory và tích hợp customizer.
- **DispatcherServletAutoConfiguration:** đăng ký DispatcherServlet và các thành phần liên quan.
- **WebMvcAutoConfiguration:** cấu hình Spring MVC, message converters, resource handling và MVC infrastructure khi điều kiện phù hợp.

Tên class giúp định hướng nơi đọc source, nhưng không nên suy luận property cụ thể chỉ từ tên auto-configuration. Tìm property metadata, condition annotation, bean method và customizer thực tế trong version đang dùng.

Khi điều tra một thay đổi:

1. Xác định property thuộc prefix server.*, spring.mvc.*, spring.web.* hay một API bean cụ thể.
2. Tìm auto-configuration/bean chịu trách nhiệm.
3. Kiểm tra classpath, property conditions và user bean conditions.
4. Xác định nó tác động vào factory/container hay MVC infrastructure.
5. Xác định callback chạy lúc khởi tạo server, lúc dựng MVC context hay cho từng request.
6. Kiểm thử bằng công cụ tương ứng với tầng đó.

Ví dụ server.port được tiêu thụ bởi server factory; spring.mvc.* thường ảnh hưởng MVC infrastructure; @RequestMapping được xử lý bởi handler mapping. Đổi nhầm prefix thường không tạo lỗi compile mà chỉ khiến ứng dụng không có hành vi mong đợi.

## 9. Kiểm thử đúng tầng: MockMvc và RANDOM_PORT

### 9.1. MockMvc kiểm tra tầng xử lý request

MockMvc chạy Spring MVC qua mock servlet API, không mở socket thật và không khởi động embedded server như HTTP listener thực tế. Nó phù hợp để test:

- Request mapping/controller.
- Filter và interceptor trong test context.
- Argument binding, validation và message conversion.
- Spring Security authorization.
- Exception handling và response status/body.

Ví dụ:

~~~java
package example.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderMvcTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void requestPassesThroughFilterAndMvcInterceptor() throws Exception {
        mockMvc.perform(get("/orders/42"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-Filter", "applied"))
                .andExpect(header().string("X-Mvc-Interceptor", "applied"))
                .andExpect(content().json(
                        "{"id":42,"status":"ACCEPTED"}"));
    }
}
~~~

Với cấu hình Filter và MVC interceptor ở phần trước, test xác nhận cả hai tầng request-processing được áp dụng cho request MVC. Nó **không chứng minh** TLS, connector, port, server threads, network binding hoặc reverse proxy hoạt động.

### 9.2. RANDOM_PORT kiểm tra embedded server thật

Dùng @SpringBootTest(webEnvironment = RANDOM_PORT) để Spring khởi động embedded server trên một port khả dụng và gửi HTTP request thực:

~~~java
package example.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class EmbeddedServerTests {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    @Test
    void embeddedServerAcceptsHttpRequest() {
        ResponseEntity<String> response =
                http.getForEntity("/orders/42", String.class);

        assertThat(port).isPositive();
        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(response.getBody())
                .contains(""id":42")
                .contains(""status":"ACCEPTED"");
        assertThat(response.getHeaders().getFirst("X-Request-Filter"))
                .isEqualTo("applied");
    }
}
~~~

Test này khởi động web server thật trong JVM và kiểm tra HTTP qua port được cấp. Nó hữu ích để xác nhận connector và request pipeline phối hợp. Tuy nhiên RANDOM_PORT không kiểm tra port cố định trong production, DNS, load balancer, firewall, TLS termination ngoài ứng dụng hoặc network policy triển khai.

### 9.3. Chọn test theo câu hỏi

| Câu hỏi cần xác minh | Test phù hợp |
|---|---|
| Controller mapping có trả JSON đúng không? | MockMvc |
| Filter/Interceptor có áp dụng không? | MockMvc |
| Security rule trả 401/403/200 đúng không? | MockMvc + Spring Security Test |
| Embedded server có start và nhận HTTP không? | RANDOM_PORT + TestRestTemplate/WebTestClient |
| Property server port được bind vào factory không? | ApplicationContextRunner/factory test hoặc RANDOM_PORT phù hợp |
| TLS certificate và handshake có đúng không? | Integration test HTTPS với certificate test |
| Reverse proxy/ingress/firewall có định tuyến đúng không? | Deployment/environment test |
| Thread pool/connection limit có đáp ứng tải không? | Load test và observability trên server thực |

Đừng dùng một MockMvc test để kết luận connector hoặc TLS đã đúng. Ngược lại, một smoke test RANDOM_PORT thành công không chứng minh mọi controller validation, security role hoặc exception mapping đều đã được kiểm tra đầy đủ.

## 10. Quy trình chẩn đoán: lỗi ở server hay request-processing?

### Triệu chứng A: Không thể kết nối tới ứng dụng

Kiểm tra:

- Application startup log: embedded server đã start chưa, port thực tế là bao nhiêu?
- server.port, server.address và port mapping container.
- Port có bị process khác chiếm không?
- Docker/Kubernetes Service, port-forward, firewall, ingress và security group.
- TLS/certificate/protocol nếu kết nối HTTPS.
- Management port có bị nhầm với application port không?

Nếu không mở được TCP connection, việc sửa controller mapping hoặc interceptor thường không giải quyết nguyên nhân.

### Triệu chứng B: Kết nối được nhưng nhận 404

Kiểm tra:

- Context path (ví dụ /shop).
- Controller package có được component scan không?
- @RequestMapping và HTTP method có đúng không?
- HandlerMapping có đăng ký endpoint không?
- Static resource handler hoặc servlet mapping có chiếm path không?
- Reverse proxy có rewrite prefix không?

404 thường nằm ở routing/request layer hoặc proxy mapping, không phải lỗi port listener nếu đã kết nối được và nhận HTTP response.

### Triệu chứng C: Nhận 401 hoặc 403

Kiểm tra Spring Security filter chain, authentication provider, role/authority, CSRF (đặc biệt request ghi), và thứ tự SecurityFilterChain. MVC interceptor không phải công cụ thay thế security filter chain.

### Triệu chứng D: Request chậm hoặc timeout

Tách thời gian ở các đoạn:

- Kết nối/TLS/queue và server thread availability.
- Filter/security.
- Controller/service.
- Database hoặc downstream HTTP call.
- Serialization và response write.

Đừng mặc định tăng server threads. Nếu database connection pool đã bão hòa, thêm server threads có thể làm hàng đợi database dài hơn. Dùng metrics và trace để tìm đoạn nghẽn.

### Triệu chứng E: Controller đúng nhưng response format sai

Kiểm tra HttpMessageConverter, Jackson modules/customizers, content negotiation, produces, Accept header, formatter và @ControllerAdvice. Đây là MVC response-processing, không phải server connector.

## 11. Lỗi thường gặp

- **Đổi port bằng @RequestMapping:** route mapping không điều khiển socket listener; dùng server.port hoặc server factory customizer.
- **Dùng WebMvcConfigurer để bật HTTPS:** TLS thuộc server/connector hoặc reverse proxy, không thuộc MVC interceptor/configurer.
- **Nhầm context path với controller path:** server.servlet.context-path thêm prefix cho ứng dụng Servlet; @RequestMapping khai báo path của handler.
- **Dùng Filter và Interceptor thay thế nhau:** filter chạy ở Servlet chain; interceptor gắn với MVC handler. Chọn theo phạm vi request cần xử lý.
- **Dùng HandlerInterceptor làm lớp bảo mật duy nhất:** Security nên đặt ở Spring Security filter chain; interceptor không bao phủ mọi loại request/servlet dispatch.
- **Dùng Servlet Filter trong WebFlux:** WebFlux dùng WebFilter; Servlet API không phải reactive filter API.
- **Đặt Tomcat-specific customizer vào cấu hình dùng chung:** cấu hình chỉ chạy được với Tomcat; cân nhắc interface server-agnostic hoặc tách theo classpath.
- **Cho rằng @Order trên customizer thay đổi thứ tự request:** nó chỉ có tác dụng trong cơ chế sắp xếp tương ứng; callback phải được consumer gọi và server customizer không phải request interceptor.
- **Dùng MockMvc để kiểm tra port/TLS:** MockMvc không mở network socket; dùng RANDOM_PORT hoặc test HTTPS/deployment phù hợp.
- **Tăng thread pool để chữa mọi timeout:** xem downstream pools, CPU, memory, queue và latency trước.
- **Nhầm management port với application port:** management.server.port dành cho management server khi cấu hình riêng; server.port là port ứng dụng chính.
- **Đổi base path để sửa 404 mà không xem proxy/context path:** kiểm tra toàn bộ URL từ client đến controller.
- **Đăng ký cùng một filter hai lần:** tránh vừa @Component vừa FilterRegistrationBean cho cùng instance/logic nếu không có chủ đích; kiểm tra mapping và order.
- **Tạo custom MVC configuration rồi vô tình thay thế auto-config:** triển khai WebMvcConfigurer để mở rộng khi có thể; chỉ dùng @EnableWebMvc khi chủ động muốn kiểm soát cấu hình MVC và hiểu các auto-configuration mặc định sẽ thay đổi.

## 12. Câu hỏi tự kiểm tra

1. Muốn đổi ứng dụng lắng nghe từ port 8080 sang 9090. Dùng gì? **server.port hoặc WebServerFactoryCustomizer.**
2. Muốn mọi URL ứng dụng có prefix /shop. Dùng gì? **server.servlet.context-path** trên Servlet stack.
3. Muốn URL /orders/{id} gọi controller method. Dùng gì? **@RequestMapping/@GetMapping và Spring MVC HandlerMapping.**
4. Muốn thêm header cho mọi request qua Servlet filter mapping. Dùng gì? **Servlet Filter hoặc FilterRegistrationBean.**
5. Muốn chạy logic trước/sau một MVC controller handler cụ thể. Dùng gì? **HandlerInterceptor đăng ký qua WebMvcConfigurer.**
6. Muốn bảo vệ endpoint bằng authentication/authorization. Dùng gì? **Spring Security SecurityFilterChain**, không chỉ MVC interceptor.
7. MockMvc test thành công có chứng minh port/TLS hoạt động không? **Không.** Nó không mở embedded server/network listener.
8. Muốn kiểm tra embedded server thật nhận HTTP. Dùng gì? **SpringBootTest với RANDOM_PORT và TestRestTemplate/WebTestClient.**
9. Dự án dùng WebFlux có thể tái sử dụng WebMvcConfigurer và jakarta.servlet.Filter không? **Không.** Dùng WebFluxConfigurer và WebFilter phù hợp.
10. Muốn cấu hình thread pool Tomcat. Thuộc tầng nào? **Server/container**, dùng server.tomcat.* hoặc Tomcat-specific factory customizer.
11. Muốn thay JSON serialization của response. Thuộc tầng nào? **MVC message conversion/Jackson**, không phải connector.
12. Request kết nối được nhưng 404. Nên kiểm tra gì? **Context path, controller mapping, HandlerMapping, component scan và proxy rewrite**, không bắt đầu bằng tăng port/thread.

## 13. Tài liệu tham khảo chính thức (Spring Boot 3.3)

- [Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html#web.servlet.embedded-container): cấu hình embedded Servlet container, server factory và server customizer.
- [Spring MVC](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): auto-configuration MVC và mở rộng bằng WebMvcConfigurer.
- [Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): nhóm server.*, spring.mvc.* và management properties.
- [WebServerFactoryCustomizer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/server/WebServerFactoryCustomizer.html): extension point tùy biến web server factory.
- [ConfigurableServletWebServerFactory API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/server/ConfigurableServletWebServerFactory.html): factory API cho Servlet web server.
- [Spring Framework — HandlerInterceptor](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-interceptor.html): interceptor trong Spring MVC handler execution.
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): filter và tích hợp Servlet request processing.
- [Spring Boot — Testing Web Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): MockMvc, random port và kiểm thử web application.
- [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): kiến trúc reactive web, WebFilter và WebFluxConfigurer.

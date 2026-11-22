# WebServerFactoryCustomizer và thời điểm áp dụng cấu hình

## 1. Mục tiêu và bối cảnh

Spring Boot có thể tự tạo máy chủ HTTP nhúng (embedded web server) khi ứng dụng chạy theo web stack Servlet hoặc Reactive. Thông thường chỉ cần các thuộc tính `server.*` trong `application.properties` hoặc `application.yml` để cấu hình cổng, địa chỉ lắng nghe, HTTPS, HTTP/2, compression và những đặc tính được hỗ trợ.

Khi cần can thiệp ở mức factory, Spring Boot cung cấp giao diện:

```java
org.springframework.boot.web.server.WebServerFactoryCustomizer<T extends WebServerFactory>
```

Đây là functional interface với một phương thức:

```java
void customize(T factory);
```

Bean triển khai interface này nhận một web server factory tương thích để chỉnh cấu hình **trước khi web server được tạo và khởi động**. Trọng tâm của bài là hiểu chính xác customizer tác động lên đối tượng nào, vào lúc nào, thứ tự áp dụng với cấu hình `server.*`, cùng cách sử dụng và kiểm tra an toàn.

## 2. Phân biệt WebServerFactory, WebServer và WebServerFactoryCustomizer

| Thành phần | Vai trò | Thời điểm quan trọng |
|---|---|---|
| `WebServerFactory` | Factory tạo máy chủ nhúng, ví dụ Tomcat hoặc Reactor Netty | Được khởi tạo thành bean trong quá trình refresh context |
| `ConfigurableWebServerFactory` | Interface mở rộng factory với các cấu hình chung như port, address, SSL, error pages | Các setter phải được áp dụng trước khi factory tạo server |
| `WebServerFactoryCustomizer<T>` | Callback chỉnh factory phù hợp với kiểu `T` | Được gọi khi BeanPostProcessor xử lý factory bean, trước khi server được khởi tạo |
| `WebServer` | Đối tượng đại diện máy chủ đã được cấu hình, có các thao tác start/stop và đọc port | Được factory tạo và quản lý trong lifecycle của web context |
| `WebServerInitializedEvent` | Sự kiện báo máy chủ đã sẵn sàng; có thể đọc port thực tế | Sau khi server được khởi tạo, phù hợp để quan sát kết quả |

Điểm cốt lõi: **Customizer sửa factory, không trực tiếp sửa một máy chủ đang chạy**. Gọi `factory.setPort(9090)` tác động lên cấu hình mà factory dùng khi tạo server; nó không tương đương đổi cổng của socket đã bind ở runtime.

Một customizer không phải là Spring MVC `HandlerInterceptor`, Servlet `Filter` hay WebFlux `WebFilter`. Những thành phần đó chạy khi xử lý HTTP request; customizer chạy trong giai đoạn bootstrap.

## 3. Luồng khởi động và thời điểm áp dụng

Sơ đồ khái quát:

```text
SpringApplication.run(...)
        |
Chuẩn bị Environment / đọc application.properties, profile, biến môi trường
        |
Tạo ApplicationContext và đăng ký bean definitions
        |
Đăng ký các BeanPostProcessor cần thiết
        |
Tạo web server factory bean
        |
WebServerFactoryCustomizerBeanPostProcessor
  -> tìm các WebServerFactoryCustomizer phù hợp
  -> sắp xếp theo order
  -> gọi customize(factory)
        |
Factory đã được tùy chỉnh
        |
Web application context dùng factory để tạo WebServer
        |
Server bind/listen/start theo lifecycle của Spring Boot
        |
WebServerInitializedEvent (biết port thực tế)
        |
ApplicationReadyEvent sau khi ứng dụng hoàn tất khởi động
```

`WebServerFactoryCustomizerBeanPostProcessor` là cơ chế quan trọng. Đây là `BeanPostProcessor` chuyên áp dụng các customizer cho bean thuộc loại `WebServerFactory`. Callback customizer được thực hiện ở giai đoạn **trước khởi tạo hoàn tất của factory bean**, khi lifecycle Spring vẫn đang ở rất sớm.

Các hệ quả thực tế:

1. Khi `customize(factory)` chạy, web server chưa ở trạng thái sẵn sàng phục vụ request. Phù hợp để thay đổi port, address, connector, error page hoặc các tùy chọn tạo server.
2. Bean nghiệp vụ, database, JPA và một số auto-configuration khác có thể chưa hoàn tất khởi tạo. Không nên để customizer phụ thuộc vào nhiều bean nặng.
3. Nếu muốn điều chỉnh dữ liệu trước khi Spring bind `server.*`, hãy xử lý ở lớp cấu hình hoặc Environment phù hợp. Nếu muốn biết **port thực tế sau khi bind**, lắng nghe sự kiện server initialized.
4. Thay đổi cấu hình sau thời điểm server đã được tạo thường không tự động làm cấu hình của server đang chạy được áp dụng lại. Đổi port, SSL hoặc connector thường cần khởi động lại theo quy trình vận hành.

Các mốc trong sơ đồ là khái quát cho quá trình khởi động bình thường của Spring Boot; những bước chi tiết có thể khác nhau theo embedded server, phiên bản Boot, web stack và auto-configuration.

## 4. Ví dụ cơ bản với ConfigurableWebServerFactory

`ConfigurableWebServerFactory` là abstraction chung cho cả nhiều loại factory Servlet và Reactive. Với nhu cầu cấu hình đơn giản, dùng kiểu chung giúp tránh ràng buộc với một server cụ thể.

Tạo lớp `WebServerConfiguration.java` trong package được Spring Boot component-scan:

```java
package com.example.demo;

import org.springframework.boot.web.server.ConfigurableWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class WebServerConfiguration {

    @Bean
    WebServerFactoryCustomizer<ConfigurableWebServerFactory> portCustomizer() {
        return factory -> factory.setPort(9090);
    }
}
```

Ví dụ trên áp dụng cho Spring Boot 3.x và 4.x với các import chung đã hiển thị. Phương thức `@Bean` trả một lambda là `WebServerFactoryCustomizer<ConfigurableWebServerFactory>`. Khi Boot chuẩn bị factory, callback đặt cổng 9090 trước khi server được tạo.

Để kiểm tra bằng một ứng dụng Spring Boot có dependency web và controller đơn giản, có thể dùng:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PingController {

    @GetMapping("/ping")
    String ping() {
        return "pong";
    }
}
```

Khởi động bằng lệnh phù hợp với project Maven Spring Boot:

```bash
./mvnw spring-boot:run
```

Sau khi ứng dụng khởi động:

```bash
curl -s http://localhost:9090/ping
```

Body response mong đợi:

```text
pong
```

Các đoạn Java trên là các lớp đặt trong một **project Spring Boot đã có class main `@SpringBootApplication` và dependency web tương ứng**; không phải chương trình Java độc lập chạy bằng `javac` đơn lẻ. Nếu có cấu hình server khác ghi đè cùng thuộc tính ở thứ tự customizer muộn hơn, cổng thực tế có thể khác; khi đó cần kiểm tra thứ tự customizer.

Lưu ý: dùng customizer để sửa port chỉ nhằm minh họa API. Với nhu cầu đổi cổng thông thường, cấu hình `server.port=9090` đơn giản và dễ bảo trì hơn.

## 5. Ưu tiên cấu hình thuộc tính trước khi viết customizer

Nên bắt đầu bằng các cấu hình chuẩn:

```properties
server.port=9090
server.address=127.0.0.1
server.compression.enabled=true
```

Ví dụ trên yêu cầu server bind vào loopback (chỉ truy cập từ máy local) với port 9090 và bật compression theo khả năng của server. Trong production, giá trị `server.address` cần phù hợp kiến trúc mạng và reverse proxy.

Một số nhóm cấu hình phổ biến:

- `server.port`: cổng HTTP chính.
- `server.address`: địa chỉ mạng mà server lắng nghe.
- `server.ssl.*`: cấu hình TLS khi HTTPS được triển khai trực tiếp ở ứng dụng.
- `server.http2.enabled`: yêu cầu bật HTTP/2 khi web server và transport hỗ trợ.
- `server.compression.*`: bật và cấu hình nén response.
- `server.tomcat.*`, `server.jetty.*`: tùy chọn dành cho server cụ thể, tùy phiên bản Boot.

`WebServerFactoryCustomizer` hữu ích khi cần API đặc thù của embedded server mà property có sẵn không cung cấp, như thêm connector, tùy chỉnh tài nguyên server hay các hook cấu hình sâu hơn. Tránh tạo nhiều customizer để làm việc đã giải quyết rõ ràng bằng properties.

## 6. Thứ tự customizer và xung đột cấu hình

Spring Boot cũng sử dụng `WebServerFactoryCustomizer` nội bộ để áp dụng các thuộc tính `server.*`. Theo tài liệu embedded web server, các customizer do Boot tự đăng ký có thứ tự **0**; thông thường chúng chạy trước customizer của người dùng, trừ khi bạn chủ động chỉ định order khác.

Có thể điều khiển thứ tự bằng `@Order` hoặc `Ordered`. Quy ước: **số order nhỏ hơn chạy sớm hơn**. Với các customizer cùng sửa một trường, giá trị do callback thực thi **sau cùng** thường là giá trị còn lại trên factory, nếu không có bước cấu hình khác ghi đè về sau.

Ví dụ minh họa:

```java
package com.example.demo;

import org.springframework.boot.web.server.ConfigurableWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(100)
public class ExplicitPortCustomizer
        implements WebServerFactoryCustomizer<ConfigurableWebServerFactory> {

    @Override
    public void customize(ConfigurableWebServerFactory factory) {
        factory.setPort(9090);
    }
}
```

Giả sử `application.properties` có:

```properties
server.port=8080
```

Trong setup thông thường, customizer do Boot đăng ký với order 0 áp dụng port 8080 trước; `ExplicitPortCustomizer` order 100 chạy sau và đổi factory sang 9090. Đây là ví dụ minh họa quan hệ thứ tự, không phải cách khuyến nghị để quản lý cấu hình môi trường.

Ngược lại, nếu customizer chạy trước customizer mặc định, giá trị `server.port` có thể ghi đè giá trị được đặt trước đó. Vì vậy, khi quan sát thấy thuộc tính không có hiệu lực hoặc server bind port ngoài dự kiến, hãy kiểm tra:

1. Các property source và giá trị `server.port` cuối cùng của `Environment`.
2. Có bao nhiêu `WebServerFactoryCustomizer` phù hợp với factory.
3. `@Order` hoặc `Ordered` của mỗi customizer.
4. Có customizer nào cùng sửa port hoặc address hay không.
5. Server hoặc context thực tế đang được khởi tạo.

Nếu nhiều customizer có cùng order thì không nên dựa vào thứ tự ngẫu nhiên để quyết định ai ghi cuối. Hãy định nghĩa rõ thứ tự hoặc hợp nhất logic cấu hình.

## 7. Customizer chuyên biệt theo embedded server

Các abstraction và API chi tiết khác nhau tùy server được chọn:

| Môi trường | Factory thường gặp | Ghi chú |
|---|---|---|
| Spring MVC + Tomcat | `TomcatServletWebServerFactory` | Có API riêng để tùy chỉnh Tomcat |
| Spring MVC + Jetty | `JettyServletWebServerFactory` | Có API riêng cho Jetty |
| Spring WebFlux + Reactor Netty | `NettyReactiveWebServerFactory` | Cấu hình reactive server Reactor Netty |
| Spring WebFlux + Tomcat/Jetty | Factory reactive tương ứng | Phụ thuộc server adapter và starter/configuration |

Kiểu generic `T` của `WebServerFactoryCustomizer<T>` quan trọng: customizer cho Tomcat factory không phải callback tùy biến tất cả các loại server. Nếu ứng dụng chuyển từ Tomcat sang Jetty, customizer gắn chặt với Tomcat cần được xem xét hoặc thay thế.

Đối với Spring Boot 3.x, import Tomcat factory thường là:

```java
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
```

Ở Spring Boot 4.x, package Tomcat factory được tổ chức lại, ví dụ:

```java
import org.springframework.boot.tomcat.servlet.TomcatServletWebServerFactory;
```

Mã nguồn của project phải sử dụng import đúng với phiên bản Spring Boot đang chạy. Không sao chép một import version-specific mà không đối chiếu dependency.

Ví dụ chỉ minh họa bản chất customizer cho Tomcat, với `TomcatServletWebServerFactory` được import theo phiên bản tương ứng:

```java
@Component
class TomcatContextPathCustomizer
        implements WebServerFactoryCustomizer<TomcatServletWebServerFactory> {

    @Override
    public void customize(TomcatServletWebServerFactory factory) {
        factory.setContextPath("/internal");
    }
}
```

Các import Spring phù hợp là `org.springframework.stereotype.Component` và `org.springframework.boot.web.server.WebServerFactoryCustomizer`. Với cấu hình context path, trong ứng dụng bình thường nên ưu tiên `server.servlet.context-path=/internal`; ví dụ dùng API Tomcat nhằm cho thấy cách chỉ chọn một factory. Đoạn code này là minh họa phụ thuộc import đã chỉ rõ, không phải tệp Java đầy đủ.

## 8. Những giới hạn về lifecycle và dependency

### 8.1. BeanPostProcessor được gọi rất sớm

Javadoc của `WebServerFactoryCustomizer` cảnh báo customizer thường được gọi bởi `WebServerFactoryCustomizerBeanPostProcessor` trong giai đoạn rất sớm của `ApplicationContext`. Đưa các bean khởi tạo nặng vào constructor customizer có thể kéo theo việc tạo chúng quá sớm.

Cấu trúc nên tránh:

```java
@Component
class RiskyServerCustomizer
        implements WebServerFactoryCustomizer<ConfigurableWebServerFactory> {

    private final ExpensiveDatabaseService databaseService;

    RiskyServerCustomizer(ExpensiveDatabaseService databaseService) {
        this.databaseService = databaseService;
    }

    @Override
    public void customize(ConfigurableWebServerFactory factory) {
        // Truy vấn database để quyết định cấu hình server.
    }
}
```

Đoạn này minh họa mùi thiết kế; `ExpensiveDatabaseService` là lớp giả định. Không nên để việc dựng server phụ thuộc vào kết nối cơ sở dữ liệu hoặc các thành phần JPA cần khởi tạo sau.

Cách an toàn hơn là dùng `Environment`, `@ConfigurationProperties` đơn giản hoặc một cấu hình được cung cấp từ lúc khởi động. Nếu buộc phải tra một dependency khác, hãy cân nhắc lookup lazy theo hướng dẫn API, nhưng vẫn tránh khởi tạo các bean phức tạp trong callback.

### 8.2. @PostConstruct không phải nơi đảm bảo thay đổi cấu hình server

`@PostConstruct` chạy khi một bean cụ thể được khởi tạo, không bảo đảm có mặt trước lúc factory được customizer xử lý. Vì vậy, không nên dùng `@PostConstruct` của controller/service để đổi port, connector hoặc SSL đang thuộc trách nhiệm khởi tạo embedded server.

Tương tự, `ApplicationRunner`, `CommandLineRunner` và `ApplicationReadyEvent` xuất hiện ở giai đoạn muộn so với việc cấu hình factory. Chúng phù hợp để thực hiện công việc ứng dụng sau bootstrap, không phù hợp để quyết định các thuộc tính nền tảng của socket đang lắng nghe.

### 8.3. Gọi customize không tương đương thay cấu hình runtime

Sau khi server đã tạo và bind port, thay giá trị của một object factory hoặc thay `Environment` không tự động đổi listener đang chạy. Các thiết lập có thể thay đổi động hay không phụ thuộc server và API cụ thể; với cổng chính và cấu hình TLS, cách an toàn và phổ biến là triển khai cấu hình mới rồi khởi động lại.

## 9. Port 0, port -1 và thời điểm đọc port thực tế

Hai giá trị đặc biệt của `server.port`:

```properties
server.port=0
```

Giá trị 0 yêu cầu hệ điều hành cấp một port còn trống. Trước khi server bind, customizer chỉ biết giá trị cấu hình là 0, không thể suy ra chính xác port sẽ được cấp.

```properties
server.port=-1
```

Giá trị -1 được Spring Boot dùng để vô hiệu hóa HTTP endpoint chính trong khi vẫn tạo web application context. Khác với `spring.main.web-application-type=none`, giá trị này không chuyển toàn bộ ứng dụng thành non-web context.

Khi cần đọc port thực tế, hãy lắng nghe `WebServerInitializedEvent`, ví dụ với Spring Boot 4.x:

```java
package com.example.demo;

import org.springframework.boot.web.server.context.WebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ListeningPortReporter {

    @EventListener
    public void onWebServerReady(WebServerInitializedEvent event) {
        System.out.println("HTTP port: " + event.getWebServer().getPort());
    }
}
```

Ở Spring Boot 3.x, import của sự kiện tương ứng là:

```java
import org.springframework.boot.web.context.WebServerInitializedEvent;
```

Đây là ví dụ dành cho project Spring Boot web đang chạy. Khi cấu hình port 0, output có dạng `HTTP port: <port thực tế>`; số cụ thể phụ thuộc hệ điều hành tại thời điểm chạy nên không thể ghi cứng.

Nếu project có cả application web server và management web server riêng (Actuator với `management.server.port` khác), có thể có nhiều context hoặc sự kiện tương ứng. Nên phân biệt server/context trước khi kết luận cổng nào thuộc về ứng dụng chính.

Trong test với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, `@LocalServerPort` là cách thuận tiện để nhận port HTTP thực tế. Không nên cố inject port runtime trong lúc customizer đang chạy, vì lúc đó server chưa hoàn tất khởi tạo.

## 10. Servlet, Reactive, NONE và trường hợp không áp dụng

- **SERVLET:** Boot thường tạo `ServletWebServerFactory`. Các customizer tương thích factory đó có thể chỉnh Tomcat, Jetty và những cấu hình servlet server được hỗ trợ.
- **REACTIVE:** Boot thường tạo `ReactiveWebServerFactory`. Có thể customizer qua abstraction chung hoặc qua factory reactive chuyên biệt, tùy runtime.
- **NONE:** không có embedded web server cần dựng trong context. Do đó customizer không có web server factory thích hợp để chạy.
- **WAR triển khai lên servlet container bên ngoài:** hạ tầng ngoài quản lý server/listener. Customizer dành cho embedded factory không phải công cụ để cấu hình Tomcat/Jetty do bên ngoài vận hành.

Nếu ứng dụng đi qua ingress, reverse proxy hoặc load balancer, port public ở gateway có thể khác port của embedded server. Cấu hình `factory.setPort(...)` thay đổi cổng listen phía ứng dụng, không tự đổi listener hoặc routing của gateway.

## 11. Kiểm thử và debug

### 11.1. Xác minh sau khi khởi động

- Quan sát log embedded server xem port được bind và loại server.
- Gọi endpoint thật bằng `curl` hoặc test HTTP client.
- Với port 0, đọc port từ `WebServerInitializedEvent` hoặc dùng `@LocalServerPort` trong integration test.
- Nếu muốn kiểm tra startup code chạy vào customizer, đặt breakpoint tại `customize(factory)` và xem loại factory thực tế.

Ví dụ:

```bash
curl -i http://localhost:9090/ping
```

Nếu ứng dụng ví dụ có `PingController` và port thực sự là 9090, response phải có body `pong`. Nếu không kết nối được, kiểm tra startup log, port bind, host và cấu hình profile.

### 11.2. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Customizer không được gọi | Lớp không được scan, không khai báo bean, generic không khớp factory đang chạy, ứng dụng không có embedded factory | Kiểm tra component scan, bean registration, classpath và web application type |
| `server.port` không đúng như mong đợi | Nhiều customizer ghi cùng thuộc tính; order hoặc profile/config khác | Xác định customizer nào chạy cuối và giá trị Environment thực tế |
| Startup lỗi vì dependency chưa sẵn sàng | Customizer phụ thuộc sớm vào DataSource, JPA hay bean nặng | Dùng cấu hình đơn giản hoặc lazy lookup hợp lý |
| Đổi port trong `ApplicationReadyEvent` không có hiệu lực | Server đã tạo và bind listener trước đó | Chuyển cấu hình sang property hoặc factory customizer trước startup |
| Lắng nghe port 0 nhưng không biết port | Cổng chỉ được cấp khi bind socket | Dùng `WebServerInitializedEvent` hoặc `@LocalServerPort` trong test |
| Chuyển Tomcat sang Jetty làm mất customization | Customizer generic gắn với loại Tomcat cụ thể | Viết customizer cho abstraction chung hoặc Jetty factory phù hợp |
| Cổng public khác `factory.setPort` | Reverse proxy, container mapping, ingress hoặc load balancer | Kiểm tra từng chặng mạng và cấu hình deployment |
| Cấu hình mới không tác động lên server đang chạy | Customizer chỉ áp dụng khi tạo embedded server | Khởi động lại/triển khai lại theo quy trình hệ thống |

### 11.3. Cách chọn giải pháp đúng theo nhu cầu

| Nhu cầu | Nơi cấu hình phù hợp |
|---|---|
| Đổi port, bind address, compression phổ thông | `application.properties` hoặc `application.yml` |
| Can thiệp tùy chọn factory không được expose bằng properties | `WebServerFactoryCustomizer<T>` |
| Thiết lập servlet filter/registration | `FilterRegistrationBean`, `ServletRegistrationBean` hoặc cơ chế annotation phù hợp |
| Xử lý request/controller | Spring MVC/WebFlux handler, filter, interceptor theo stack |
| Quan sát port thực sau khi server sẵn sàng | `WebServerInitializedEvent` |
| Chạy tác vụ sau khi app startup xong | `ApplicationRunner`, `CommandLineRunner`, `ApplicationReadyEvent` |
| Cấu hình server do hạ tầng ngoài quản lý | Cấu hình reverse proxy, ingress, servlet container hoặc runtime triển khai |

## 12. Checklist thiết kế

1. Xác định project dùng Servlet hay Reactive và embedded server nào.
2. Kiểm tra đã có property `server.*` cho nhu cầu chưa.
3. Chỉ tạo customizer khi cần tác động lên factory trước khi tạo server.
4. Dùng generic factory chung nếu chỉ cần API chung; dùng class server-specific khi cần tùy chỉnh chuyên biệt.
5. Đảm bảo bean được scan/đăng ký; xem `@Order` khi nhiều customizer sửa cùng thuộc tính.
6. Hạn chế phụ thuộc vào những bean khởi tạo nặng trong customizer.
7. Nếu cần port thực tế, lấy sau khi server initialized; không lấy khi `customize` đang chạy.
8. Kiểm tra tính tương thích package giữa Spring Boot 3.x và 4.x.
9. Xác minh server đã bind theo cấu hình và hoạt động qua HTTP test.
10. Ghi rõ đâu là cổng embedded server, đâu là cổng reverse proxy/management.

## 13. Ghi nhớ

`WebServerFactoryCustomizer` là hook của **giai đoạn khởi tạo embedded web server**, được áp dụng lên **factory bean** qua `WebServerFactoryCustomizerBeanPostProcessor` **trước khi server bắt đầu chạy**. Thứ tự callback ảnh hưởng đến cấu hình khi nhiều customizer cùng thay đổi một giá trị. Để đặt cấu hình thông thường, ưu tiên `server.*`; để quan sát port thực sau khi khởi động, dùng `WebServerInitializedEvent`. Tránh phụ thuộc sớm vào JPA, DataSource hay các bean nặng và đừng xem customizer là cơ chế cấu hình động cho listener đang chạy.

## 14. Tài liệu tham khảo

- Spring Boot Reference — Embedded Web Servers: https://docs.spring.io/spring-boot/how-to/webserver.html
- WebServerFactoryCustomizer Javadoc: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/server/WebServerFactoryCustomizer.html
- WebServerFactoryCustomizerBeanPostProcessor Javadoc: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/server/WebServerFactoryCustomizerBeanPostProcessor.html
- ConfigurableWebServerFactory Javadoc: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/server/ConfigurableWebServerFactory.html
- WebServerInitializedEvent Javadoc (Spring Boot 4.x): https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/server/context/WebServerInitializedEvent.html
- WebServerInitializedEvent Javadoc (Spring Boot 3.x): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/context/WebServerInitializedEvent.html

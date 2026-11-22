# Ranh giới giữa thuộc tính Spring Boot và API riêng của máy chủ

Một ứng dụng Spring Boot chạy web thường dùng **máy chủ nhúng** (embedded server): Tomcat, Jetty hoặc Undertow đối với mô hình Servlet; ngoài ra còn có các lựa chọn phù hợp với mô hình reactive. Có hai cách chính để cấu hình máy chủ nhúng:

1. **Thuộc tính do Spring Boot cung cấp**: đặt trong application.yml, application.properties, biến môi trường hoặc tham số chạy. Spring Boot đọc, kiểm tra kiểu dữ liệu và chuyển các giá trị có hỗ trợ thành thiết lập trên máy chủ.
2. **API riêng của máy chủ**: mã Java trực tiếp tác động lên factory, connector, handler, context, thread pool, listener hoặc các đối tượng cấu hình do Tomcat/Jetty/Undertow cung cấp.

Ranh giới không nằm ở chỗ một cấu hình có đơn giản hay phức tạp. Nó nằm ở **ai sở hữu hợp đồng cấu hình**. Với thuộc tính Spring Boot, ứng dụng phụ thuộc vào hợp đồng cấu hình của Boot. Với API máy chủ, ứng dụng phụ thuộc trực tiếp vào API và vòng đời của máy chủ cụ thể.

Nguyên tắc sử dụng: **tìm thuộc tính Spring Boot trước; nếu không đáp ứng được mới dùng WebServerFactoryCustomizer và API của máy chủ; tự khai báo cả WebServerFactory chỉ là phương án cuối cùng.**

## 1. Sơ đồ trách nhiệm

~~~text
application.yml / environment / CLI
              |
              v
Spring Environment + property binding
              |
              v
Spring Boot ServerProperties và các customizer
              |
              v
ServletWebServerFactory
  |             |             |
  v             v             v
Tomcat         Jetty        Undertow
  |             |             |
  v             v             v
Connector /   Server /      Builder /
Context       Handler       Listener
              |
              v
       HTTP request runtime
~~~

Đường đi phía trên cho thấy vì sao một số thuộc tính dùng được với nhiều container, còn một số thuộc tính chỉ có ý nghĩa khi container tương ứng đang chạy. Spring Boot không nhất thiết bộc lộ mọi setter, listener và hook của máy chủ qua property.

Phân biệt thêm:

- **Spring MVC** sở hữu mapping của controller, argument resolver, converter, exception handler và các phần của request processing ở tầng framework.
- **Servlet container** sở hữu HTTP connector, chấp nhận kết nối, queue, worker thread, nhiều thiết lập TLS và vòng đời container.
- **Spring Boot** lắp ghép các thành phần và chuyển những thuộc tính đã hỗ trợ xuống tầng phù hợp.
- **Ứng dụng** quyết định giá trị cấu hình theo môi trường, customizer bổ sung và các ràng buộc về bảo mật, hiệu năng.

Không nên dùng API Tomcat để sửa một hành vi vốn do Spring MVC sở hữu, ví dụ cách ánh xạ JSON response, chỉ vì ứng dụng chạy trên Tomcat.

## 2. Ba lớp cấu hình và ví dụ

| Lớp | Ví dụ | Tính di động | Khi nào dùng |
|---|---|---|---|
| Thuộc tính chung của Boot | server.port, server.compression.enabled, server.ssl.*, server.shutdown | Tương đối cao giữa các container được hỗ trợ, dù chi tiết triển khai có thể khác | Nhu cầu phổ biến có property chính thức |
| Thuộc tính Boot theo container | server.tomcat.threads.max, server.jetty.threads.max, server.undertow.threads.io | Gắn với một server cụ thể | Cần điều chỉnh tính năng container đã được Boot expose |
| API của server | TomcatServletWebServerFactory.addAdditionalTomcatConnectors, Jetty server customizer, Undertow builder customizer | Thấp; phụ thuộc server và phiên bản | Cần hook hoặc cấu trúc mà thuộc tính Boot chưa diễn tả được |

Một tên bắt đầu bằng server.tomcat.* vẫn là **thuộc tính Spring Boot**, dù hiệu lực của nó dành riêng cho Tomcat. Ngược lại, một lệnh gọi org.apache.catalina.connector.Connector là **API Tomcat**, dù được thực thi trong một Spring Boot bean.

Sự phân biệt này quan trọng khi nâng cấp: các property có vòng đời hỗ trợ và metadata của Spring Boot; API máy chủ chịu ảnh hưởng trực tiếp từ phiên bản Tomcat, Jetty hoặc Undertow mà Boot quản lý.

## 3. Thuộc tính Boot chung: ưu tiên đầu tiên

Các thiết lập thường gặp trong ứng dụng Spring MVC dùng embedded server:

~~~yaml
server:
  port: 8080
  address: 127.0.0.1
  servlet:
    context-path: /demo
    session:
      timeout: 30m
      cookie:
        http-only: true
  compression:
    enabled: true
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Ý nghĩa:

- server.port chọn cổng HTTP chính; mặc định thường là 8080.
- server.address giới hạn địa chỉ interface mà máy chủ bind. Ví dụ 127.0.0.1 chỉ phục vụ trên loopback của máy chạy.
- server.servlet.context-path thêm prefix cho URL của ứng dụng Servlet. Khi cấu hình /demo, endpoint /ping được truy cập qua /demo/ping.
- server.servlet.session.timeout đặt thời gian session không hoạt động.
- server.servlet.session.cookie.http-only cấu hình cookie phiên do container quản lý.
- server.compression.enabled bật hỗ trợ nén response theo ngưỡng và quy tắc liên quan. Không có nghĩa mọi response đều được nén.
- server.shutdown=graceful yêu cầu máy chủ hỗ trợ graceful shutdown; thời gian đóng còn phụ thuộc server, request đang chạy và timeout của lifecycle.
- spring.lifecycle.timeout-per-shutdown-phase giới hạn thời gian chờ cho một pha dừng lifecycle.

Đây là các ví dụ thuộc Boot 3.5.x. Khi dùng phiên bản khác, hãy kiểm tra danh sách Common Application Properties của chính phiên bản đó. Không nên giả định mọi tên property đều tồn tại hoặc có cùng mặc định ở tất cả phiên bản.

### 3.1. Điều kiện hỗ trợ vẫn có vai trò

Có property không có nghĩa mọi môi trường thực hiện cùng một cơ chế vật lý. Ví dụ:

- server.http2.enabled bật hỗ trợ HTTP/2 khi server, TLS và môi trường đáp ứng điều kiện tương ứng.
- server.max-http-request-header-size định nghĩa giới hạn ở mức Boot, nhưng mỗi HTTP server có thể diễn giải kích thước request line và các header theo cách khác nhau.
- server.ssl.* cấu hình TLS cho connector chính theo những khả năng đã được Boot hỗ trợ; TLS termination ở reverse proxy là một kiến trúc khác.
- Giá trị của một số pool hoặc thread property có thể không còn tác động như dự kiến khi bật virtual threads hoặc đổi runtime.

Sau khi cấu hình, cần kiểm thử hành vi thực tế của máy chủ và xác nhận bằng thông tin vận hành. Không nên chỉ thấy property đã được đọc rồi kết luận connector đang chạy đúng cấu hình.

## 4. Thuộc tính Boot theo từng server

Boot có namespace riêng để expose các tính năng server-specific mà nhiều ứng dụng cần.

### 4.1. Tomcat

~~~yaml
server:
  tomcat:
    threads:
      max: 200
      min-spare: 10
    accept-count: 100
    max-connections: 8192
    connection-timeout: 10s
    accesslog:
      enabled: true
~~~

Ví dụ này dùng các property thuộc nhóm server.tomcat.*. Chúng có ý nghĩa khi Tomcat là embedded servlet server đang được sử dụng. Các giá trị minh họa không phải khuyến nghị tối ưu cho mọi hệ thống; phải cân nhắc CPU, memory, số lượng request đồng thời, thời gian chờ I/O và load test.

Một số điểm dễ nhầm:

- threads.max là giới hạn worker thread theo mô hình thực thi tương ứng; Spring Boot 3.5 ghi rõ thuộc tính này không có tác dụng theo cách thông thường khi virtual threads được bật.
- accept-count liên quan hàng đợi kết nối khi giới hạn xử lý đã tới ngưỡng, không tương đương tổng số request mà hệ thống chịu được.
- max-connections không đồng nghĩa số luồng xử lý request.
- connection-timeout không phải timeout tổng thời gian chạy một controller.
- accesslog ghi request ở tầng container; cần quản lý thông tin nhạy cảm, rotation và dung lượng lưu trữ.

### 4.2. Jetty

~~~yaml
server:
  jetty:
    threads:
      max: 200
      min: 8
    connection-idle-timeout: 30s
~~~

Đây là các property của Jetty được Spring Boot expose trong nhánh server.jetty.*. Thay Tomcat bằng Jetty nhưng giữ nguyên server.tomcat.threads.max không khiến Jetty có cùng giới hạn. Các tên và ngữ nghĩa của pool khác nhau, nên cần xem lại tài liệu Jetty thay vì máy móc sao chép con số.

### 4.3. Undertow

~~~yaml
server:
  undertow:
    threads:
      io: 4
      worker: 32
~~~

Các thuộc tính server.undertow.threads.io và server.undertow.threads.worker điều chỉnh các nhóm thread khác nhau của Undertow. Tách I/O thread và worker thread có ý nghĩa quan trọng đối với xử lý blocking. Giá trị minh họa cần được đo đạc trước khi áp dụng trong sản xuất.

Một ứng dụng chỉ nên giữ lại cấu hình có ý nghĩa với server thực tế. Property không áp dụng cho container được chọn có thể bị bỏ qua hoặc tạo cảm giác sai rằng hệ thống đã được tối ưu.

## 5. Ranh giới của Boot property: phạm vi và hợp đồng

Thuộc tính Boot là một **bề mặt cấu hình có chủ đích**. Khi Boot công bố server.tomcat.threads.max, nó chủ động nhận trách nhiệm bind, validate ở mức được hỗ trợ và áp dụng thiết lập đó thông qua factory/customizer thích hợp.

Boot không hứa rằng:

1. Mọi tính năng của Tomcat/Jetty/Undertow đều có property tương ứng.
2. Một property chung được triển khai tuyệt đối giống nhau trên mọi server.
3. Property có thể thay đổi live mà không restart.
4. Một property của Tomcat sẽ tương đương tên hay giá trị với property của Jetty.
5. Tất cả API riêng của container ổn định qua nâng cấp major version.

Không nên tự phát minh khóa như server.tomcat.some-advanced-switch rồi kỳ vọng Boot tự động nhận. Các khóa ngoài metadata do Boot hỗ trợ không tự động gọi setter của Tomcat. Nếu muốn có khóa cấu hình do ứng dụng sở hữu, hãy khai báo namespace riêng như app.server.* và viết mã @ConfigurationProperties cùng customizer áp dụng nó.

### 5.1. Khi nào property có thể không đủ?

Ví dụ những yêu cầu thường dẫn đến API cấp thấp:

- Bổ sung một HTTP connector thứ hai cho cùng embedded Tomcat, với cổng và chính sách riêng.
- Gắn một Valve, handler, lifecycle listener hoặc hook đặc thù mà Boot chưa cung cấp property phù hợp.
- Cấu hình một tính năng mới của server đang dùng trước khi Boot cung cấp lớp abstraction cho tính năng đó.
- Thiết lập khác nhau cho nhiều connector, thay vì chỉ thay một giá trị toàn cục.
- Cần một customizer áp dụng logic có điều kiện phức tạp mà một property đơn lẻ không mô tả được.

Trước khi chọn API, phải xác minh **không có property hoặc abstraction cấp cao hơn** giải quyết được yêu cầu. Ví dụ muốn thay cổng chính, hãy dùng server.port; không cần sửa Connector trực tiếp.

## 6. WebServerFactoryCustomizer: lối vào cấp thấp được Boot hỗ trợ

Spring Boot cung cấp interface WebServerFactoryCustomizer để ứng dụng can thiệp vào **factory trước khi embedded server khởi động**.

Một customizer đơn giản cho Tomcat:

~~~java
package com.example.boundary;

import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.stereotype.Component;

@Component
public class TomcatBoundaryCustomizer
        implements WebServerFactoryCustomizer<TomcatServletWebServerFactory> {

    @Override
    public void customize(TomcatServletWebServerFactory factory) {
        // Có thể thêm connector, context customizer hoặc valve ở đây.
    }
}
~~~

Đây là ví dụ cấu trúc; nó cố ý chưa thay đổi runtime. Loại tham số generic là TomcatServletWebServerFactory, vì vậy customizer này dành cho embedded Tomcat ở **Servlet stack**.

Các factory tương ứng:

| Web stack | Tomcat | Jetty | Undertow | Reactor Netty |
|---|---|---|---|---|
| Servlet | TomcatServletWebServerFactory | JettyServletWebServerFactory | UndertowServletWebServerFactory | Không dùng cho Servlet stack |
| Reactive | TomcatReactiveWebServerFactory | JettyReactiveWebServerFactory | UndertowReactiveWebServerFactory | NettyReactiveWebServerFactory |

Tên factory và package import có thể khác giữa các major version của Boot. Các đoạn Java trong bài dùng API của **Spring Boot 3.5.x**, không nên chuyển nguyên import sang Spring Boot 4.x khi chưa đối chiếu tài liệu phiên bản.

### 6.1. Cấu hình phần nào của factory?

- Factory chung có thể quản lý những đặc điểm như cổng, bind address và SSL đã được abstraction cung cấp.
- TomcatServletWebServerFactory cho phép thêm Tomcat connector, context customizer và các extension thuộc Tomcat.
- JettyServletWebServerFactory cho phép dùng Jetty-specific server customization.
- UndertowServletWebServerFactory cho phép cấu hình builder hoặc deployment của Undertow.
- Các API sâu hơn như Tomcat Connector, Jetty ServerConnector hoặc Undertow Builder thuộc dependency của từng server.

Dùng customizer không làm đổi Spring MVC thành WebFlux. Ngược lại, chọn một factory cho reactive stack là một lựa chọn web server khác, cần hiểu rõ mô hình ứng dụng đang chạy.

### 6.2. Đừng tạo lại factory khi chưa cần

Nếu tự khai báo bean ServletWebServerFactory hoặc TomcatServletWebServerFactory, Spring Boot có thể nhường chỗ cho bean đó thay vì tạo factory mặc định. Các customizer tự cấu hình của Boot vẫn có thể được áp dụng cho factory do ứng dụng tạo, vì vậy đây không phải cách đáng tin để "vô hiệu hóa tất cả mặc định".

Việc tự tạo factory kéo theo trách nhiệm phải giữ lại các tùy chỉnh mong muốn như SSL, compression, session, access log và các integration khác. **Hãy ưu tiên WebServerFactoryCustomizer** để thêm phần riêng cần thiết và vẫn tận dụng cấu hình mặc định.

## 7. Ví dụ chạy được: cổng chính dùng property, cổng phụ dùng Tomcat API

Bài toán: một ứng dụng Spring MVC chạy trên Tomcat có HTTP connector chính ở cổng **8080** và cần thêm một connector HTTP thử nghiệm ở **8081** để minh họa ranh giới cấu hình. Cổng chính dùng server.port. Cổng thứ hai được bổ sung qua TomcatServletWebServerFactory vì yêu cầu nhiều connector là tính năng riêng của Tomcat.

**Phạm vi ví dụ:** Spring Boot 3.5.16, Java 17+, Maven, Spring MVC, embedded Tomcat. Hai cổng HTTP trong ví dụ chỉ dành cho môi trường học tập/local; triển khai thật cần quy hoạch TLS, firewall, bind address và chính sách truy cập.

Cấu trúc dự án:

~~~text
server-boundary-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/boundary/
    │   ├── BoundaryApplication.java
    │   ├── PingController.java
    │   └── AdditionalConnectorConfiguration.java
    └── resources/application.yml
~~~

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>server-boundary-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>server-boundary-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Starter Web dùng embedded Tomcat mặc định. Maven parent quản lý các phiên bản dependency tương thích, tránh chỉ định riêng phiên bản Tomcat không cần thiết.

### 7.2. BoundaryApplication.java

~~~java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
~~~

Đặt lớp khởi động cùng package gốc với các controller/configuration để component scan tìm thấy chúng.

### 7.3. PingController.java

~~~java
package com.example.boundary;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping(value = "/ping", produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }
}
~~~

Endpoint trả một chuỗi cố định để xác minh hai connector phục vụ cùng một ứng dụng MVC.

### 7.4. application.yml: phần thuộc Spring Boot

~~~yaml
server:
  port: 8080
  tomcat:
    threads:
      max: 64
~~~

server.port đặt cổng chính theo hợp đồng Boot. server.tomcat.threads.max là một property do Boot cung cấp dành riêng cho Tomcat; nó vẫn thuộc **lớp cấu hình Spring Boot**, không phải lời gọi trực tiếp của ứng dụng tới Tomcat API.

### 7.5. AdditionalConnectorConfiguration.java: phần thuộc Tomcat API

~~~java
package com.example.boundary;

import org.apache.catalina.connector.Connector;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("extra-connector")
public class AdditionalConnectorConfiguration {

    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory>
            extraTomcatConnector() {

        return factory -> {
            Connector connector =
                    new Connector("org.apache.coyote.http11.Http11NioProtocol");
            connector.setPort(8081);
            factory.addAdditionalTomcatConnectors(connector);
        };
    }
}
~~~

Giải thích:

1. @Profile("extra-connector") chỉ kích hoạt cấu hình khi profile extra-connector được bật, tránh vô tình mở cổng thử nghiệm.
2. WebServerFactoryCustomizer nhận TomcatServletWebServerFactory do Boot tạo.
3. org.apache.catalina.connector.Connector là API của Tomcat, không phải abstraction chung của Spring Boot.
4. Http11NioProtocol tạo HTTP/1.1 NIO connector.
5. addAdditionalTomcatConnectors bổ sung connector 8081 bên cạnh connector chính 8080.
6. Các Spring MVC controller vẫn được phục vụ bởi cùng ứng dụng, không nhân đôi ApplicationContext hay tạo máy chủ riêng bằng tay.

Đây là điểm ranh giới quan sát được: YAML mô tả cổng HTTP chính; mã Java mô tả một khả năng bổ sung chuyên biệt của Tomcat.

### 7.6. Build và chạy

Từ thư mục gốc dự án, cần JDK 17+ và Maven:

~~~bash
mvn -q -DskipTests package
java -jar target/server-boundary-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=extra-connector
~~~

Ở một terminal khác:

~~~bash
curl -sS http://localhost:8080/ping
curl -sS http://localhost:8081/ping
~~~

Body của mỗi response là:

~~~text
pong
~~~

Khi chạy **không** bật profile extra-connector, ứng dụng chỉ chủ động tạo connector chính do Boot quản lý; customizer bổ sung connector 8081 không được đăng ký.

~~~bash
java -jar target/server-boundary-demo-0.0.1-SNAPSHOT.jar
~~~

Nếu cổng 8080 hoặc 8081 đang bị tiến trình khác chiếm, ứng dụng có thể không khởi động được. Hãy giải phóng cổng hoặc thay thông số của ví dụ trong môi trường học tập. Với production, không mở thêm HTTP port mà chưa đánh giá đường truyền TLS và network exposure.

## 8. Điều gì xảy ra khi đổi Tomcat sang Jetty hoặc Undertow?

**server.port** vẫn là thuộc tính Boot chung, nhưng đoạn cấu hình dùng TomcatServletWebServerFactory và Connector không còn phù hợp để điều chỉnh Jetty hay Undertow.

Đổi embedded server thường đòi hỏi thay dependency starter; ví dụ với Maven cho MVC, loại trừ spring-boot-starter-tomcat từ spring-boot-starter-web và thêm spring-boot-starter-jetty hoặc spring-boot-starter-undertow. Phiên bản và khả năng hỗ trợ phụ thuộc BOM của Spring Boot đang dùng.

Cần sửa cấu hình theo ba bước:

1. **Giữ property chung** mà server mới có hỗ trợ, như server.port, server.servlet.context-path hoặc server.compression.enabled.
2. **Chuyển nhóm property chuyên biệt**: không dùng server.tomcat.threads.max để điều chỉnh thread pool của Jetty. Kiểm tra server.jetty.* hoặc server.undertow.* tương ứng.
3. **Rà soát mọi import và bean server-specific**: một customizer với generic TomcatServletWebServerFactory không thể thay thế tùy ý bằng Jetty/Undertow; API và cách tạo connector khác nhau. Đặc biệt, khi đã bỏ dependency Tomcat, mã tham chiếu trực tiếp lớp Tomcat có thể không còn biên dịch hoặc load được.

Đặt các customizer gắn server trong package/module riêng, bật khi đúng container được chọn và có integration test cho mỗi cấu hình hỗ trợ. Dùng conditional configuration hoặc profile chỉ khi chúng thực sự tương ứng với môi trường của ứng dụng.

## 9. Cách Spring Boot áp dụng property và customizer

Trong Spring Boot 3.5, các WebServerFactoryCustomizer do Boot tự cấu hình thường có thứ tự **0**. Customizer do ứng dụng khai báo mặc định có thể chạy sau, trừ khi khai báo order khác. Điều này có nghĩa là thay đổi bằng mã có khả năng tác động lên giá trị đã được Boot đặt từ property.

Không nên cùng lúc:

- Đặt server.port=8080 trong YAML.
- Viết customizer khác gọi factory.setPort(9000).
- Kỳ vọng cả hai đều đúng.

Tùy thứ tự thực thi, kết quả cuối cùng có thể là một giá trị bị ghi đè. Khi thuộc tính chính thức đã đáp ứng yêu cầu, hãy để property là nguồn cấu hình duy nhất cho hành vi đó.

Nếu ứng dụng cần nhiều customizer:

- Dùng @Order hoặc Ordered khi thứ tự thực sự là một phần của thiết kế.
- Giữ các customizer độc lập, tránh cùng thay một thuộc tính.
- Ghi rõ customizer nào tạo connector, cấu hình TLS, thêm listener hoặc áp dụng policy.
- Kiểm tra runtime sau khởi động vì cấu hình từ proxy và môi trường có thể ảnh hưởng kết quả.

Một WebServerFactoryCustomizer thường chạy trong giai đoạn khởi động trước khi server bắt đầu phục vụ request. Việc thay application.yml sau khi server đã chạy không tự khiến Connector mới xuất hiện; cần cơ chế restart/reconfiguration được hỗ trợ riêng.

## 10. Không nhầm API máy chủ với API của Servlet và Spring MVC

Một số nhu cầu nên được xử lý ở tầng framework hoặc Servlet thay vì chỉnh connector:

| Nhu cầu | Lớp nên xem trước |
|---|---|
| Thay đường dẫn endpoint | @RequestMapping, @GetMapping của Spring MVC |
| Thêm interceptor | WebMvcConfigurer |
| Thêm Filter cho request | FilterRegistrationBean hoặc Servlet Filter |
| Thêm Servlet riêng | ServletRegistrationBean |
| Tùy chỉnh xử lý exception | @ControllerAdvice |
| Đổi JSON serialization | Jackson configuration hoặc HTTP message converter |
| Giới hạn upload | spring.servlet.multipart.* và validation phù hợp |
| Đổi cổng, session timeout, SSL | server.* trong Boot |
| Thêm Tomcat connector | TomcatServletWebServerFactory/Connector API |

Ví dụ, muốn ghi log thời gian xử lý ở tầng request MVC thì interceptor hoặc filter thường rõ ràng hơn so với tự thêm Tomcat Valve. Chỉ cần Valve khi thực sự muốn hook container và chấp nhận phụ thuộc Tomcat.

Cũng cần phân biệt **server-side configuration** với **HTTP client configuration**. RestClient, RestTemplate hoặc WebClient khi ứng dụng gọi upstream dùng kết nối và timeout riêng. Thay server.tomcat.connection-timeout không tự chỉnh timeout của WebClient outbound.

## 11. TLS, proxy và nhiều connector

### 11.1. SSL/TLS của connector chính

Spring Boot cung cấp server.ssl.* và khả năng cấu hình SSL bundle trong các phiên bản hỗ trợ. Nên dùng property/SSL bundle cho nhu cầu TLS thông thường.

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:server.p12
    key-store-type: PKCS12
~~~

Đoạn trên chỉ minh họa **các khóa cấu hình**; để chạy được phải có keystore thật và secret/trust configuration phù hợp. Không đưa password khóa bí mật vào Git.

Điểm quan trọng: connector thứ hai được tạo trực tiếp bằng API Tomcat trong ví dụ mục 7 là **HTTP connector riêng**. Nó không tự nhiên kế thừa đầy đủ mọi chính sách SSL/TLS của connector chính. Muốn thêm HTTPS connector phải cấu hình connector/TLS theo API tương ứng hoặc dùng kiến trúc proxy quản lý TLS. Cần kiểm tra cả cổng phụ trong đánh giá bảo mật.

### 11.2. Reverse proxy và forwarded headers

Khi ứng dụng nằm sau Nginx, ingress hoặc load balancer, có thể cấu hình server.forward-headers-strategy theo kiến trúc. Với Tomcat, Boot còn có các thuộc tính server.tomcat.remoteip.* để điều chỉnh cách tin cậy và diễn giải header do proxy gửi.

Chỉ tin tưởng forwarded headers đến từ proxy kiểm soát được. Nếu mọi client đều có thể tự gửi X-Forwarded-For hoặc X-Forwarded-Proto mà ứng dụng tin hoàn toàn, URL, scheme hoặc địa chỉ IP dùng cho xác thực/ghi log có thể bị giả mạo.

Nếu property hiện có đủ, đừng tự thêm một Tomcat RemoteIpValve với cấu hình trùng lặp. Một lớp proxy xử lý header sai có thể gây redirect loop, cookie không đúng Secure hoặc thông tin audit sai.

### 11.3. Management port không phải cổng ứng dụng thứ hai

Khi dùng Spring Boot Actuator, management.server.port có thể mở endpoint quản trị trên cổng riêng trong những cấu hình phù hợp. Đây là cơ chế quản trị của Boot, không đồng nghĩa với việc thêm một application connector khác để phục vụ toàn bộ controller.

Nếu yêu cầu chỉ là tách health/metrics cho vận hành, nên cân nhắc property Actuator. Không cần tạo thêm Tomcat connector chỉ để mô phỏng management port.

## 12. Triển khai JAR nhúng và WAR bên ngoài khác nhau

**Executable JAR với embedded server:** ứng dụng sở hữu vòng đời factory, connector và quá trình mở cổng. Các property server.* và WebServerFactoryCustomizer áp dụng theo cơ chế embedded server của Boot.

**WAR triển khai vào Tomcat/Jetty bên ngoài:** container bên ngoài thường do người vận hành cấu hình. Ứng dụng không tự tạo connector của host như khi chạy embedded JAR. Những cấu hình như cổng HTTP, thread pool và TLS của standalone Tomcat thuộc quyền quản trị của server bên ngoài. Không nên kỳ vọng bean TomcatServletWebServerFactory của ứng dụng WAR sẽ thay cổng của toàn bộ external Tomcat.

Các thành phần ở tầng Spring MVC, Servlet Filter, controller và một số cấu hình Servlet application vẫn có thể hoạt động theo cách phù hợp với môi trường WAR. Nhưng ranh giới vận hành của máy chủ đã chuyển sang platform/container bên ngoài.

## 13. Kiểm thử để xác minh ranh giới

### 13.1. Kiểm thử giá trị property

Dùng integration test của Spring Boot với WebEnvironment.RANDOM_PORT để biết ứng dụng khởi động embedded server thành công và endpoint trả đúng nội dung. Lúc này Boot yêu cầu hệ điều hành cấp cổng ngẫu nhiên; cổng thực tế không nhất thiết là giá trị cấu hình cố định trong application.yml.

Ví dụ test trong dự án có spring-boot-starter-test:

~~~java
package com.example.boundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PingHttpTest {

    @Autowired
    private TestRestTemplate rest;

    @Test
    void ping() {
        String body = rest.getForObject("/ping", String.class);
        assertThat(body).isEqualTo("pong");
    }
}
~~~

Bổ sung dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Không bật profile extra-connector trong test này để tránh cố định cổng 8081 khi nhiều test chạy song song.

### 13.2. Kiểm thử customizer riêng của Tomcat

Khi bật profile extra-connector trong môi trường integration chuyên biệt:

1. Khởi động ứng dụng và xác nhận cổng chính 8080 đáp ứng /ping.
2. Xác nhận cổng phụ 8081 cũng đáp ứng /ping.
3. Tắt profile hoặc bỏ customizer, xác nhận chính ứng dụng này không tạo connector phụ nữa.
4. Khi đổi Tomcat sang Jetty, phải loại bỏ/thay cấu hình Tomcat-specific và chạy lại các test khởi động.
5. Dùng socket/HTTP client từ bên ngoài tiến trình để kiểm tra cổng thực tế; đừng chỉ xác nhận bean đã tồn tại.

Kiểm thử đầu cuối phải chạy trên đúng server và dependency version dự kiến đưa lên môi trường triển khai. Unit test chỉ gọi customize(factory) không thể thay thế hoàn toàn việc khởi tạo và bind connector thật.

### 13.3. Quan sát runtime

Một số cách hữu ích:

- Đọc log startup của Spring Boot để biết server nào đang chạy và cổng chính.
- Bật --debug khi cần phân tích Condition Evaluation Report để biết auto-configuration được chọn hoặc bị back-off.
- Nếu cần giám sát Tomcat qua MBeans, kiểm tra property server.tomcat.mbeanregistry.enabled thay vì tự bật qua API khi Boot đã có property.
- Dùng HTTP request hoặc công cụ kiểm tra cổng để xác nhận listener thực tế.
- Với performance tuning, đo thread pool, connection, latency p95/p99 và error rate dưới tải, không chỉ dựa vào cấu hình tĩnh.

Với server.port=0, cổng thật được cấp khi server khởi động; có thể lấy qua thông tin runtime hoặc WebServerInitializedEvent thay vì đọc lại property server.port và giả định đó là cổng đã bind.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đặt server.tomcat.threads.max nhưng Jetty vẫn dùng mặc định | Đang chạy Jetty, property thuộc Tomcat | Chuyển sang property server.jetty.* tương ứng, kiểm thử hành vi |
| Tự khai báo key server.* nhưng không có tác dụng | Boot không hỗ trợ key đó hoặc không có code bind riêng | Tra danh sách properties của phiên bản; với tùy biến riêng dùng app.* + @ConfigurationProperties và customizer |
| server.port và customizer đặt hai cổng khác nhau | Hai nguồn cùng cấu hình một thuộc tính | Chọn property làm nguồn duy nhất nếu đã được Boot hỗ trợ |
| Ứng dụng không khởi động vì port in use | Cổng chính hoặc phụ đã bị chiếm | Kiểm tra cả 8080 và 8081, đổi cổng hoặc dừng tiến trình khác |
| Đổi Tomcat sang Jetty thì build fail | Mã vẫn import TomcatServletWebServerFactory hoặc Connector | Thay module/customizer theo server đang dùng |
| Bean WebServerFactory tự viết làm mất mặc định | Đã thay factory auto-config và quên xử lý tích hợp liên quan | Ưu tiên WebServerFactoryCustomizer; so sánh cấu hình trước và sau |
| Cấu hình TLS có tác dụng ở cổng chính nhưng cổng phụ vẫn HTTP | Connector phụ tự tạo không kế thừa cấu hình SSL | Cấu hình TLS riêng hoặc đặt sau proxy theo thiết kế |
| server.max-http-request-header-size cho kết quả khác giữa server | Server áp dụng giới hạn theo cách khác | Đọc tài liệu server, test request thực tế |
| Điều chỉnh Tomcat thread pool không cải thiện tốc độ | Bottleneck ở database, I/O hoặc virtual-thread configuration | Đo tải thật, kiểm tra giới hạn ngoài server |
| Chỉnh server.port trong WAR nhưng không đổi port Tomcat ngoài | External container sở hữu connector | Cấu hình server bên ngoài |
| Gửi X-Forwarded-* giả làm sai scheme/IP | Proxy trust configuration quá rộng | Chỉ tin proxy đã xác minh, kiểm tra server.forward-headers-strategy |
| Thêm management.server.port nhưng endpoint ứng dụng không xuất hiện ở đó | Management port dành cho endpoint quản trị | Dùng connector ứng dụng riêng khi thực sự cần, với security phù hợp |

## 15. Quy trình ra quyết định

Trước khi thêm mã phụ thuộc Tomcat/Jetty/Undertow:

1. **Viết rõ hành vi mong muốn:** cổng, timeout, TLS, thread pool, Valve, listener, hay nhiều connector?
2. **Kiểm tra Boot property chính thức:** tra Common Application Properties đúng phiên bản.
3. **Xác định web stack và server:** Servlet hay reactive; Tomcat, Jetty, Undertow hay Reactor Netty?
4. **Ưu tiên property phù hợp:** chung server.* hoặc riêng server.tomcat.*, server.jetty.*, server.undertow.*.
5. **Nếu thiếu property, tìm extension point:** WebServerFactoryCustomizer với factory đúng loại; đối chiếu API server thực tế.
6. **Giữ phạm vi tối thiểu:** tránh tự tạo lại factory, tránh thay đổi cùng một giá trị ở hai nơi, dùng profile khi tính năng chỉ dành cho một môi trường.
7. **Kiểm thử với server thật:** cổng, TLS, forwarded headers, concurrency, shutdown và lỗi khởi động.
8. **Ghi rõ chi phí di chuyển:** thư viện và API nào sẽ phải sửa khi nâng Boot hoặc thay container.

Một cách tự kiểm tra hữu ích: nếu bỏ dependency Tomcat mà cấu hình vẫn có ý nghĩa, nhiều khả năng đó là thuộc tính/abstraction ở mức Boot. Nếu mã bắt buộc import org.apache.catalina.* và cần các chi tiết Connector/Valve, đó là phần do API Tomcat sở hữu.

## 16. Ghi nhớ

**Spring Boot property** là hợp đồng cấu hình do Boot công bố, bind và áp dụng vào runtime. Nhóm server.* là bề mặt ưu tiên; nhóm server.tomcat.*, server.jetty.* và server.undertow.* dù chuyên biệt vẫn thuộc hợp đồng của Boot.

**API máy chủ** là lớp điều khiển trực tiếp các đối tượng riêng như Tomcat Connector, Jetty ServerConnector hoặc Undertow Builder. Khi cần khả năng chưa có property, WebServerFactoryCustomizer giúp bổ sung điều chỉnh trong vòng đời embedded server. Đổi lại, ứng dụng phải chịu trách nhiệm về tính tương thích phiên bản, bảo mật, thứ tự cấu hình, các cổng phụ và kiểm thử triển khai.

Trong công việc thực tế: **property trước, customizer sau, tự thay thế factory cuối cùng**. Giữ ranh giới này giúp hệ thống dễ vận hành và nâng cấp mà vẫn dùng được các khả năng chuyên sâu khi thật sự cần.

## Tài liệu chính thức để đối chiếu theo phiên bản

- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html)

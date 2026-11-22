# Tùy chỉnh TomcatServletWebServerFactory và connector

## 1. Bối cảnh: Spring Boot quản lý embedded Tomcat như thế nào?

Trong ứng dụng Spring Boot chạy theo mô hình Servlet, máy chủ HTTP có thể được đóng gói ngay trong ứng dụng thay vì triển khai file WAR vào một Tomcat độc lập. Với spring-boot-starter-web và dependency Tomcat mặc định, Spring Boot tạo một Tomcat nhúng, cấu hình các thành phần cần thiết rồi khởi động nó cùng ApplicationContext.

Thành phần quan trọng là **TomcatServletWebServerFactory**, một triển khai của ServletWebServerFactory dành riêng cho Tomcat. Factory nhận các thiết lập như cổng HTTP, context path, SSL, connector customizer, context customizer và các tùy chọn Tomcat trước khi tạo TomcatWebServer. Trong tình huống thông thường, Spring Boot tự cấu hình factory; ứng dụng chỉ cần cung cấp property hoặc customizer phù hợp.

**Connector** là thành phần của Tomcat tiếp nhận kết nối mạng theo một protocol nhất định, chẳng hạn HTTP/1.1. Nó quản lý cổng lắng nghe, cấu hình giao thức, thời gian chờ kết nối, số kết nối và việc chuyển các request hợp lệ vào engine xử lý của Tomcat. Connector không phải một Spring MVC controller, không phải REST endpoint và cũng không tương đương một ApplicationContext.

Một sơ đồ khái quát:

~~~text
Spring Boot application
  |
  +-- ServletWebServerApplicationContext
  |     |
  |     +-- TomcatServletWebServerFactory (cấu hình trước khi start)
  |             |
  |             +-- TomcatWebServer / Tomcat runtime
  |                     |
  |                     +-- Service
  |                     |     +-- Connector :8080 -> HTTP/1.1
  |                     |     +-- Connector :8081 -> HTTP/1.1 (nếu tự thêm)
  |                     |     |
  |                     |     +-- Engine -> Host -> Web Context
  |                     |
  |                     +-- Servlet filters / DispatcherServlet
  |                                       |
  |                                       +-- Spring MVC controller
  |                                               |
  |                                               +-- service/repository
  |
  +-- WebServerFactoryCustomizer bean(s)
        |
        +-- Điều chỉnh factory/connector trước khi tạo server
~~~

Đường đi thực tế có thêm socket, protocol handler, adapter, security filter, valve, async servlet processing và các lớp hạ tầng khác. Sơ đồ chỉ nhấn mạnh ranh giới: **factory tạo/cấu hình server; connector tiếp nhận giao thức mạng; Servlet và Spring MVC xử lý request**.

### 1.1. Các lớp cần phân biệt

| Thành phần | Vai trò | Trường hợp cần quan tâm |
|---|---|---|
| ServletWebServerFactory | Hợp đồng tạo embedded Servlet web server | Muốn hiểu cách Boot chọn Tomcat/Jetty/Undertow |
| TomcatServletWebServerFactory | Factory dành cho embedded Tomcat | Muốn thêm connector hoặc dùng hook riêng của Tomcat |
| WebServerFactoryCustomizer<T> | Callback thay đổi factory trước khi server khởi động | Cách mở rộng được ưu tiên cho cấu hình bằng code |
| TomcatConnectorCustomizer | Callback thay đổi Connector mà factory tạo | Chỉnh cấu hình connector HTTP chính |
| TomcatProtocolHandlerCustomizer | Callback tùy chỉnh protocol handler | Khi phải truy cập cấu hình giao thức nằm dưới Connector |
| org.apache.catalina.connector.Connector | Một connector thực của Tomcat | Thêm HTTP listener thứ hai, cấu hình scheme/port |
| TomcatContextCustomizer | Callback tùy chỉnh web Context | Cài đặt tính chất Servlet context đặc thù |
| TomcatWebServer | Đối tượng điều khiển vòng đời máy chủ đã tạo | Startup, stop, port thực tế và tích hợp với Boot |

TomcatServletWebServerFactory áp dụng cho **Servlet stack**, thường là Spring MVC. Khi chạy WebFlux theo mô hình reactive, loại factory và vòng đời web server có thể khác; không sao chép nguyên cấu hình Servlet cho ứng dụng reactive chỉ vì nó cũng có Tomcat trên classpath.

### 1.2. Điều kiện trước khi tùy chỉnh

- Ứng dụng phải thật sự chạy với embedded Tomcat Servlet. Nếu đã thay starter Tomcat bằng Jetty/Undertow thì customizer dành riêng cho Tomcat không có factory phù hợp để áp dụng.
- Trong ứng dụng Servlet thông thường, tránh khai báo thêm một factory bean thứ hai. Spring Boot đã tạo factory mặc định và hệ sinh thái customizer được thiết kế để điều chỉnh nó.
- Nếu deploy WAR vào Tomcat bên ngoài, cấu hình connector thuộc quyền quản lý của Tomcat bên ngoài. Một factory nhúng trong ứng dụng không điều khiển cổng của container đó.
- Cấu hình phải được thực hiện trước khi connector khởi động. Đổi property hoặc chỉnh đối tượng factory sau khi máy chủ chạy không đồng nghĩa Tomcat sẽ đổi listener ngay lập tức.
- API lớp factory/protocol có thể thay đổi theo phiên bản Spring Boot và Tomcat. Kiểm tra đúng tài liệu của phiên bản đang chạy khi dùng tùy chọn nâng cao.

## 2. Chọn cách cấu hình theo mức độ cần thiết

Trong đa số ứng dụng, nên bắt đầu bằng application.yml hoặc application.properties. Spring Boot đã cung cấp rất nhiều property cho server.port, server.address, SSL, Servlet session, thread pool, timeout, connection limit và access log. Khi có property phù hợp thì cách đó dễ vận hành hơn: có thể thay đổi theo môi trường và đọc cấu hình tập trung mà không cần biên dịch code.

| Nhu cầu | Cách phù hợp | Lý do |
|---|---|---|
| Đổi cổng HTTP chính | server.port | Ngắn gọn, hỗ trợ profile/environment |
| Chọn network interface | server.address | Tránh hardcode trong Java |
| Đổi context path | server.servlet.context-path | Là đặc tính ứng dụng Servlet |
| Max threads, max connections, accept queue | server.tomcat.* | Boot đã hỗ trợ binding và customizer |
| Cấu hình SSL/TLS listener chính | server.ssl.* hoặc SSL bundle | Dùng cơ chế SSL chính thức của Boot |
| Điều chỉnh một thuộc tính Connector không có property | WebServerFactoryCustomizer<TomcatServletWebServerFactory> | Có thể gọi API Tomcat trực tiếp, phạm vi hẹp |
| Thay đổi protocol handler của connector chính | TomcatConnectorCustomizer hoặc TomcatProtocolHandlerCustomizer | Tác động đúng tầng protocol |
| Mở thêm cổng HTTP/HTTPS trên cùng Tomcat | addAdditionalTomcatConnectors | Cấu hình thêm Connector mới |
| Tùy chỉnh web Context, Valve | Factory hook tương ứng | Trường hợp thực sự đòi hỏi Tomcat-specific behavior |
| Tự kiểm soát việc tạo Tomcat factory | Khai báo ServletWebServerFactory bean riêng | Giải pháp nâng cao, cần kiểm tra các auto-customizer |

Tránh chuyển mọi property thành Java customizer. Một bean hardcode setPort(9000) có thể vô tình ghi đè giá trị server.port đã được cấu hình theo môi trường; thứ tự thực thi các customizer cũng trở thành một phần cần kiểm tra.

## 3. Cấu hình Tomcat thông dụng bằng application.yml

Ví dụ cho ứng dụng Spring MVC đã có starter web:

~~~yaml
server:
  port: 8080
  address: 0.0.0.0
  servlet:
    context-path: /api
  tomcat:
    threads:
      max: 200
      min-spare: 10
    max-connections: 8192
    accept-count: 100
    connection-timeout: 20s
    keep-alive-timeout: 20s
    max-keep-alive-requests: 100
~~~

Giá trị ở đây chỉ để minh họa các thuộc tính; không phải cấu hình được khuyến nghị cho mọi production workload. Các phiên bản Boot khác nhau có thể thay đổi danh sách property và giá trị mặc định. Trước khi thay đổi, đo tài nguyên, lưu lượng, độ trễ và giới hạn kết nối thực tế.

Giải thích các nhóm:

- **server.port**: cổng HTTP chính do factory tạo. Nếu đặt 0, hệ điều hành chọn một cổng còn trống khi khởi động, hữu ích trong integration test.
- **server.address**: địa chỉ mạng server bind vào. 0.0.0.0 lắng nghe trên các giao diện IPv4 phù hợp; dùng 127.0.0.1 khi muốn giới hạn truy cập nội bộ máy. Cần xét riêng IPv6 và cấu hình môi trường thực tế.
- **server.servlet.context-path**: tiền tố URL của ứng dụng Servlet. Với /api, controller ánh xạ /hello sẽ được truy cập qua /api/hello.
- **server.tomcat.threads.max**: số worker thread tối đa trong cấu hình thread pool phù hợp. Không đồng nghĩa với số kết nối tối đa hoặc số request mỗi giây. Với virtual threads, một số tùy chọn truyền thống của pool có thể không còn tác dụng như trước.
- **server.tomcat.threads.min-spare**: lượng worker thread rảnh tối thiểu mà Tomcat có thể duy trì theo mô hình thread pool thông thường.
- **server.tomcat.max-connections**: mức kết nối được Tomcat chấp nhận và xử lý đồng thời. Không nên coi đây là mức concurrency nghiệp vụ hoặc DB connection pool.
- **server.tomcat.accept-count**: giới hạn độ dài hàng đợi kết nối đang chờ khi khả năng tiếp nhận của server đã chạm giới hạn; hệ điều hành có thể áp dụng backlog thực tế khác.
- **server.tomcat.connection-timeout**: thời gian chờ phù hợp ở giai đoạn đọc request trên kết nối mới. Đây không phải timeout tổng của controller hoặc query database.
- **server.tomcat.keep-alive-timeout**: thời gian chờ request HTTP tiếp theo trên kết nối keep-alive.
- **server.tomcat.max-keep-alive-requests**: giới hạn số request có thể được phục vụ trước khi kết nối keep-alive phải đóng, theo ngữ nghĩa của Tomcat.

Không tăng max-connections, threads.max và accept-count đồng loạt chỉ vì thấy 5xx. Nếu bottleneck là connection pool DB, query chậm hoặc client downstream bị timeout, việc mở rộng queue có thể chỉ khiến request xếp hàng lâu hơn và tiêu tốn thêm bộ nhớ.

## 4. Tùy chỉnh connector chính bằng WebServerFactoryCustomizer

Khi cần điều chỉnh thuộc tính không có property Boot tương ứng, có thể đăng ký WebServerFactoryCustomizer cho TomcatServletWebServerFactory. Cách này vẫn để Spring Boot sở hữu việc tạo factory và áp dụng các cấu hình mặc định.

Ví dụ sau cấu hình thời gian timeout cho xử lý Servlet async trên connector được factory tạo. File src/main/java/dev/example/web/TomcatConnectorConfig.java:

~~~java
package dev.example.web;

import java.time.Duration;

import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TomcatConnectorConfig {

    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory>
            primaryConnectorCustomizer() {

        return factory -> factory.addConnectorCustomizers(connector -> {
            connector.setAsyncTimeout(Duration.ofSeconds(20).toMillis());
        });
    }
}
~~~

Đây là lớp hoàn chỉnh để đặt trong một ứng dụng Spring Boot Servlet có embedded Tomcat. Java 17+ dùng được. Ở ví dụ này, code không tự tạo một ServletWebServerFactory mới; callback chỉ bổ sung customizer cho connector mặc định.

Giải thích đường gọi:

1. Spring Boot tìm thấy bean WebServerFactoryCustomizer.
2. Khi chuẩn bị embedded Tomcat, callback customize nhận TomcatServletWebServerFactory.
3. addConnectorCustomizers đăng ký callback áp dụng lên Connector do factory tạo.
4. Trước khi Tomcat phục vụ lưu lượng, callback cấu hình thuộc tính của Connector.
5. Sau đó Tomcat khởi động theo vòng đời của ApplicationContext.

**Async timeout** của connector liên quan đến xử lý Servlet bất đồng bộ, không phải bảo đảm mọi endpoint luôn trả trong 20 giây. Một controller blocking, một JDBC query hoặc một lời gọi HTTP client có timeout riêng. Cần cấu hình và xử lý timeout ở đúng tầng.

### 4.1. Tùy chỉnh protocol handler theo đúng kiểu

Khi cần can thiệp sâu hơn vào HTTP protocol, Connector cho phép truy cập getProtocolHandler(). Với cấu hình HTTP/1.1 thông dụng của embedded Tomcat, handler có thể là một triển khai của AbstractHttp11Protocol.

Ví dụ minh họa, có thể đặt trong callback addConnectorCustomizers của ví dụ trước:

~~~java
factory.addConnectorCustomizers(connector -> {
    if (connector.getProtocolHandler()
            instanceof org.apache.coyote.http11.AbstractHttp11Protocol<?> http) {
        http.setMaxKeepAliveRequests(120);
        http.setConnectionTimeout(15_000);
    }
});
~~~

Đây là đoạn trích cần biến factory có kiểu TomcatServletWebServerFactory đã được cung cấp bởi customizer bên ngoài. Nó không phải Java class độc lập để chạy trực tiếp.

Sử dụng kiểm tra instanceof để tránh ép một handler không tương thích thành AbstractHttp11Protocol. Nếu ứng dụng yêu cầu bắt buộc phải dùng HTTP/1.1, có thể chủ động báo lỗi khi loại handler không đúng thay vì bỏ qua âm thầm. Nếu cấu hình này đã có property tương ứng, hãy cân nhắc đặt property thay vì gọi protocol handler thủ công.

TomcatServletWebServerFactory còn có addProtocolHandlerCustomizers cho trường hợp cần đăng ký TomcatProtocolHandlerCustomizer trực tiếp. Chọn connector-level hoặc protocol-level hook theo đúng thứ phải tùy chỉnh; không nên cùng lúc thiết lập một tham số qua nhiều kênh gây khó xác định giá trị cuối.

### 4.2. Đừng nhầm với cách thay factory bằng bean mới

Có thể tự khai báo bean TomcatServletWebServerFactory hoặc ServletWebServerFactory, nhưng đó là hướng đi nâng cao. Spring Boot sẽ không tạo cùng loại factory mặc định khi đã có bean thích hợp, và người triển khai phải hiểu cách các auto-customizer còn lại áp dụng vào factory mới.

Ví dụ khai báo một factory mới chỉ để đổi port thường không cần thiết:

~~~java
// Không cần cách này nếu mục tiêu chỉ là đổi server.port:
@Bean
TomcatServletWebServerFactory customFactory() {
    return new TomcatServletWebServerFactory(9000);
}
~~~

Đoạn này chỉ minh họa đối tượng, không phải cấu hình đầy đủ cần đưa vào production. Một @Bean tự tạo có thể làm thay đổi lựa chọn web server và các điểm mở rộng đang sử dụng. Trước hết dùng server.port hoặc WebServerFactoryCustomizer và chỉ thay factory khi có nhu cầu kiến trúc cụ thể.

## 5. Thêm một HTTP connector trên cổng thứ hai

Một Tomcat Service có thể chứa nhiều Connector. Ví dụ, ứng dụng chính dùng cổng 8080 và cần thêm cổng 8081 để chạy thử nội bộ. Spring Boot 3.3 hỗ trợ factory.addAdditionalTomcatConnectors(Connector...).

File src/main/java/dev/example/web/ExtraTomcatConnectorConfig.java:

~~~java
package dev.example.web;

import java.time.Duration;

import org.apache.catalina.connector.Connector;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ExtraTomcatConnectorConfig {

    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory>
            additionalHttpConnectorCustomizer() {

        return factory -> {
            Connector additional =
                    new Connector("org.apache.coyote.http11.Http11NioProtocol");

            additional.setPort(8081);
            additional.setScheme("http");
            additional.setSecure(false);
            additional.setURIEncoding("UTF-8");
            additional.setAsyncTimeout(Duration.ofSeconds(20).toMillis());

            factory.addAdditionalTomcatConnectors(additional);
        };
    }
}
~~~

Đây là lớp hoàn chỉnh để đưa vào ứng dụng Spring Boot MVC có embedded Tomcat. Không cần khai báo thêm Tomcat hoặc DispatcherServlet. Hai cổng thuộc cùng Tomcat/web application nên thường dẫn đến cùng các Servlet mappings, filter chain và controller. Chẳng hạn controller GET /hello có thể được gọi qua cả localhost:8080/hello và localhost:8081/hello nếu không có context path và cả hai cổng đều truy cập được.

**Điểm rất dễ bỏ sót:** Các TomcatConnectorCustomizer được đăng ký qua addConnectorCustomizers **không tự áp dụng cho connector bổ sung** được thêm bằng addAdditionalTomcatConnectors. Nếu connector 8081 cần timeout, URI encoding, giới hạn protocol hoặc SSL riêng, phải cấu hình nó bằng đối tượng Connector/protocol handler tương ứng. Không giả định chính sách cấu hình của cổng chính tự được sao chép sang cổng phụ.

### 5.1. Cấu hình cổng bổ sung bằng property ứng dụng

Hardcode 8081 tiện cho ví dụ nhưng có thể gây xung đột trong môi trường container hoặc nhiều instance. Trong dự án thật, có thể đưa cổng vào property riêng:

~~~yaml
server:
  port: 8080

app:
  server:
    extra-http-port: 8081
~~~

Sau đó sử dụng @Value hoặc @ConfigurationProperties để đọc giá trị và quyết định có bật connector phụ theo môi trường hay không. Nên kiểm tra giá trị cổng (thường 1–65535), phát hiện trùng server.port, kiểm soát bind address và chỉ mở cổng trên hạ tầng mạng khi có yêu cầu rõ ràng.

Nếu mục đích chỉ là tách cổng Actuator/health, hãy xem management.server.port và management.endpoints.web.* trước khi tự thêm Connector. Cổng quản trị có thể cần chính sách bảo mật, định tuyến và network policy khác với cổng nghiệp vụ.

### 5.2. Connector phụ không tự tạo một ứng dụng thứ hai

Việc thêm Connector là thêm cổng/ngõ vào mạng cho **cùng một Tomcat service/web context**. Nó không tự sinh thêm ApplicationContext, không tạo một nhóm controller thứ hai và cũng không tách resource pool theo cổng.

Nếu cần API nội bộ với danh sách endpoint, quyền truy cập hoặc lifecycle hoàn toàn khác, một Connector bổ sung không đủ để tạo ranh giới bảo mật hay triển khai độc lập. Cần xét kiến trúc riêng: cổng quản trị do Boot hỗ trợ, security filter chain thích hợp, reverse proxy policy hoặc dịch vụ riêng.

### 5.3. Tại sao thêm connector không tự chuyển HTTP sang HTTPS?

Các phương thức setScheme("http") và setSecure(false) mô tả ngữ nghĩa request trên connector này; chúng không bật TLS hay redirect. Khi cổng chính được bật TLS bằng server.ssl.*, connector HTTP bổ sung vẫn là HTTP nếu không tự cấu hình SSL. Cả hai cổng có thể cùng đi vào ứng dụng, nhưng đường truyền và chính sách an toàn khác nhau.

Không tự đưa connector HTTP bổ sung ra Internet khi nghiệp vụ yêu cầu TLS. Với production, ưu tiên cơ chế TLS/SSL chính thức của Boot hoặc kết thúc TLS ở reverse proxy/load balancer đáng tin cậy; nếu bắt buộc cấu hình thêm connector HTTPS, cần xử lý SSLHostConfig, chứng chỉ, private key, protocol/cipher và kiểm thử handshake trên chính connector đó.

## 6. Ví dụ Spring Boot có thể chạy thử hai cổng

Để kiểm chứng thực tế, giả sử đã có một dự án Spring Boot 3.x dùng Java 17+ và Gradle với dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Trong cùng package hoặc package con của class @SpringBootApplication, thêm ExtraTomcatConnectorConfig ở mục 5. Tạo controller src/main/java/dev/example/web/HelloController.java:

~~~java
package dev.example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "hello from embedded Tomcat";
    }
}
~~~

Nếu ứng dụng đã có main class @SpringBootApplication quét package dev.example.web, chỉ cần bổ sung hai file cấu hình và controller vào project. Nếu tạo dự án mới, có thể dùng main class sau:

~~~java
package dev.example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Tệp phải tên DemoApplication.java và nằm đúng package. Ví dụ giả định build.gradle đã có Spring Boot plugin và repository Maven phù hợp; dependency snippet trên không tự tạo thành một dự án Gradle hoàn chỉnh.

Đặt application.yml:

~~~yaml
server:
  port: 8080
~~~

Chạy ứng dụng từ thư mục dự án:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng gradlew.bat bootRun. Ở terminal khác, kiểm tra:

~~~bash
curl -i http://localhost:8080/hello
curl -i http://localhost:8081/hello
~~~

Trong điều kiện chạy thành công, cả hai request trả HTTP 200 và body:

~~~text
hello from embedded Tomcat
~~~

Ví dụ không yêu cầu output headers giống hệt nhau giữa các môi trường. Nếu controller có context path như /api, cần gọi /api/hello trên cả hai cổng. Nếu ứng dụng có Spring Security, các filter và cấu hình authorization có thể thay đổi kết quả thành 401/403; điều này không đồng nghĩa connector không mở.

Để kiểm tra socket đang LISTEN trên Linux:

~~~bash
ss -ltn
~~~

Hoặc trên Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName localhost -Port 8080
Test-NetConnection -ComputerName localhost -Port 8081
~~~

TCP connect thành công chỉ chứng minh cổng đang nhận kết nối. curl đến endpoint kiểm tra thêm đường HTTP/Servlet/controller. Để kết luận ứng dụng đủ điều kiện phục vụ, cần đánh giá readiness và các dependency bắt buộc riêng.

### 6.1. Thử xung đột cổng

Nếu một tiến trình khác đang chiếm 8081, connector bổ sung có thể không khởi động được. Không bỏ qua lỗi startup rồi cho rằng ứng dụng vẫn phục vụ đúng hai cổng. Kiểm tra log và port ownership, xác nhận container báo lỗi hay có cổng nào vẫn hoạt động, sau đó đổi cổng theo cấu hình môi trường.

Với một container có nhiều cổng, còn phải cấu hình Docker port publishing, Kubernetes containerPort/Service targetPort, security group hoặc firewall. Tomcat mở cổng trong container chưa đồng nghĩa bên ngoài truy cập được.

## 7. Hiểu kỹ các giới hạn kết nối và thread

Tùy chỉnh connector thường liên quan hiệu năng, nhưng cần phân biệt các giới hạn:

| Thiết lập | Giới hạn cái gì? | Không đồng nghĩa với |
|---|---|---|
| threads.max | Số worker thread xử lý theo cơ chế thread pool tương ứng | Số TCP connection và request mỗi giây |
| max-connections | Số kết nối Tomcat chấp nhận/xử lý cùng lúc | Số JDBC connection hoặc request đang chạy trong controller |
| accept-count | Độ dài hàng đợi kết nối khi giới hạn tiếp nhận đã đạt | Hàng đợi toàn bộ request ở Spring MVC |
| connection-timeout | Thời gian chờ đọc request trên kết nối ở tầng connector | Timeout của database hoặc toàn bộ giao dịch |
| keep-alive-timeout | Thời gian duy trì kết nối nhàn rỗi chờ request kế tiếp | Timeout của request nghiệp vụ đang thực thi |
| max-keep-alive-requests | Số request tối đa phục vụ trên một kết nối keep-alive | Tổng số request toàn ứng dụng |
| async timeout | Thời gian chờ xử lý Servlet asynchronous phù hợp | Bao quát mọi timeout blocking |
| DB connection pool max | Số connection DB được cấp bởi pool | Số kết nối TCP đến Tomcat |

Giả sử service có 500 request/giây và mỗi request đồng bộ bị giữ khoảng 0,4 giây. Ước lượng ban đầu cho số request đồng thời là 500 × 0,4 = 200 request đang xử lý/đợi (giả định ổn định, không tính burst). Điều này giúp hình dung áp lực với worker threads, nhưng không thể dùng nó một mình để chốt threads.max. Cần đo p95/p99 latency, blocking I/O, DB pool, CPU và tải đỉnh.

Nếu quá nhiều thread cùng gọi database có pool nhỏ, thread có thể xếp hàng chờ pool; tăng worker thread vô hạn sẽ không tạo thêm DB capacity. Nếu max-connections quá cao, số socket, buffer và file descriptor cũng tiêu tốn tài nguyên. Nếu accept-count quá nhỏ dưới tải burst, client có thể gặp lỗi kết nối; nếu quá lớn, request có thể phải chờ lâu và vượt timeout ở phía client.

Trong môi trường Java 21 hỗ trợ virtual threads, cần xác nhận phiên bản Spring Boot/Tomcat, cấu hình bật virtual threads và metric tương ứng trước khi áp dụng trực tiếp các giả định của platform-thread pool. Các giới hạn kết nối, DB pool, CPU và timeout vẫn tồn tại dù thread model khác.

### 7.1. Keep-alive là tối ưu có chi phí

HTTP keep-alive giúp tái sử dụng TCP connection, giảm kết nối mới và có thể giảm chi phí handshake. Nhưng connection nhàn rỗi vẫn dùng tài nguyên; keep-alive timeout quá dài khi có nhiều client có thể tăng số socket thường trú.

Lưu lượng có reverse proxy thường có hai tầng kết nối: client ↔ proxy và proxy ↔ Tomcat. Cần kiểm tra timeout, idle settings và connection reuse ở cả hai. Nếu proxy giữ kết nối lâu hơn Tomcat, lỗi connection reset có thể xuất hiện khi proxy định tái sử dụng connection đã bị server đóng.

Không tự động tăng keep-alive timeout để giải quyết controller xử lý chậm; hai loại timeout có vai trò khác nhau.

## 8. SSL/TLS, reverse proxy và forwarded headers

Một lỗi vận hành phổ biến là ứng dụng chạy HTTP sau proxy TLS, nhưng tạo URL redirect hoặc cookie security không phù hợp với URL bên ngoài. Connector nhận HTTP từ proxy thường thấy scheme=http và local port là 8080, trong khi browser truy cập https://example.com. Spring Boot có cơ chế xử lý forwarded headers và cấu hình tích hợp container.

Tùy môi trường có thể sử dụng:

~~~yaml
server:
  forward-headers-strategy: native
~~~

Hoặc chọn cơ chế framework khi phù hợp. Cấu hình cần đi kèm giới hạn **proxy đáng tin cậy** để client bên ngoài không thể tự giả mạo X-Forwarded-* gây sai scheme, host, địa chỉ IP hoặc redirect. Khi dùng Tomcat native, cần hiểu RemoteIpValve và các thiết lập proxy trust tương ứng.

Các lưu ý:

- server.ssl.* cấu hình TLS cho connector chính được Boot quản lý; một connector tự thêm không tự thừa hưởng toàn bộ TLS của cổng chính.
- Nếu termination TLS nằm ở ingress/load balancer, lưu lượng đến ứng dụng có thể là HTTP trong mạng nội bộ; vẫn cần chính sách network và forwarded headers rõ ràng.
- Nếu cả HTTP và HTTPS listener tồn tại, quyết định redirect hay chặn HTTP phải được cấu hình và kiểm thử. Việc có cổng HTTPS không tự làm HTTP redirect.
- Dùng server.servlet.session.cookie.secure, SameSite và các chính sách cookie phù hợp khi ứng dụng xử lý session; không dựa vào setSecure trên Connector như sự thay thế cho toàn bộ chính sách session.
- Không mở AJP hoặc connector quản trị ra mạng công khai nếu không có lý do và bảo vệ tương ứng.

### 8.1. Bổ sung connector cho nội bộ có thể thay đổi bề mặt tấn công

Connector thứ hai là một listener mạng mới, có thể vô tình mở toàn bộ controller và filter chain ứng dụng. Hãy xem xét:

- Bind address và firewall/network policy của từng port.
- TLS và xác thực cần thiết trên từng đường vào.
- Khả năng bypass reverse proxy đang chịu trách nhiệm rate limit, WAF, authentication hoặc request-size limits.
- Log, metric và monitoring theo từng cổng để phát hiện truy cập ngoài dự kiến.
- Quyền truy cập vào health, Actuator và endpoint nội bộ.

Spring Security ở Servlet filter chain thường vẫn áp dụng cho request đi qua cùng web context, nhưng các biện pháp bảo vệ tại reverse proxy không tự áp dụng nếu client kết nối thẳng vào cổng phụ. Thiết kế theo đường đi thực tế của request.

## 9. Factory hook khác Connector hook ở đâu?

TomcatServletWebServerFactory có các điểm mở rộng chuyên biệt:

| Hook | Đối tượng tác động | Tình huống |
|---|---|---|
| addConnectorCustomizers | Connector được factory cấu hình | Thuộc tính listener chính, URI/async timeout |
| addProtocolHandlerCustomizers | ProtocolHandler của connector được factory cấu hình | Điều chỉnh HTTP/1.1 protocol chi tiết |
| addAdditionalTomcatConnectors | Connector mới được bổ sung vào Tomcat | Mở thêm HTTP/TLS listener |
| addContextCustomizers | Tomcat Context | Cấu hình web application context |
| addContextValves | Tomcat Context Valve | Xử lý ở tầng pipeline của context |
| addEngineValves | Tomcat Engine Valve | Xử lý trước khi chuyển xuống host/context theo pipeline |
| addContextLifecycleListeners | Listener cho vòng đời context | Quan sát/customize lifecycle đặc thù |

Một **Valve** là thành phần của pipeline Tomcat; một **Servlet Filter** là thành phần Servlet API; còn Spring MVC HandlerInterceptor nằm sâu hơn trong DispatcherServlet. Ba loại này khác vòng đời, điểm chặn và khả năng cấu hình. Với authentication, validation, header handling, logging hoặc chính sách ứng dụng phổ biến, nên ưu tiên cơ chế Spring Security, Filter, HandlerInterceptor hoặc framework-level facility nếu chúng đáp ứng yêu cầu, rồi mới dùng Valve riêng của Tomcat.

Ví dụ không nên tự cài đặt xử lý CORS bằng Valve chỉ vì muốn truy cập connector. Spring MVC/Spring Security đã có cấu hình CORS và bảo mật tương ứng. Tương tự, giới hạn nội dung upload cần xét cả reverse proxy, Servlet multipart resolver và server limits, không giải quyết bằng cách tăng một tham số HTTP connector đơn lẻ.

## 10. Thứ tự áp dụng customizer và tránh xung đột

Spring Boot có các customizer từ auto-configuration (ví dụ bind ServerProperties) và có thể có customizer do ứng dụng khai báo. Nếu nhiều customizer thay đổi cùng một giá trị, thứ tự thực thi ảnh hưởng cấu hình cuối cùng. Không nên dựa vào một thứ tự ngẫu nhiên hoặc chỉ nhìn giá trị trong application.yml mà bỏ qua code đang ghi đè.

Một quy trình an toàn:

1. Tập hợp các nơi cấu hình server: application.yml/properties, profile, environment variable, Spring Cloud config nếu có, WebServerFactoryCustomizer, Connector customizer, protocol customizer.
2. Chọn một nguồn chính cho từng tham số và ghi rõ vì sao cần override.
3. Nếu có nhiều customizer, dùng thứ tự tường minh khi thật sự cần và tránh ghi đè cùng property từ hai nơi.
4. Khởi động ứng dụng bằng đúng profile/deployment config.
5. Kiểm tra socket, HTTP response, metric và giá trị runtime thực tế.
6. Kiểm thử lại khi nâng cấp Spring Boot hoặc Tomcat.

Nếu một starter/thư viện được thêm vào application và nó cũng cung cấp WebServerFactoryCustomizer, hãy rà soát hành vi cuối trước khi quy lỗi cho Tomcat. Thứ tự và nguồn cấu hình là nguyên nhân phổ biến khiến giá trị runtime khác file YAML.

## 11. Quan sát, đo tải và xác minh kết quả tuning

Một ứng dụng startup thành công chưa chứng minh connector tuning hiệu quả. Kiểm tra từng loại bằng chứng:

**Cấu hình và endpoint:** log port, xác nhận interface đang LISTEN bằng ss/netstat, chạy curl trên từng port, kiểm tra status, redirect, HTTP scheme và TLS handshake nếu có. Nếu có context path, mọi request phải dùng đúng prefix.

**Hành vi timeout:** mô phỏng client gửi request chậm, kết nối idle và endpoint async trong môi trường test. Đừng dùng một lệnh curl nhanh để suy ra connection timeout hoặc keep-alive timeout đã hoạt động đúng.

**Tải và tài nguyên:** chạy load test với lượng connection, keep-alive, concurrency và latency gần điều kiện production. Theo dõi CPU, heap, GC pause, thread count, open file descriptors, connection count, error rate và latency p50/p95/p99.

**Downstream:** theo dõi DB connection pool, HTTP client pool, queue length, network errors và timeout. Tăng max-connections trong Tomcat không xử lý được lỗi do connection pool của service downstream.

**Spring Boot Actuator/Micrometer:** dùng /actuator/health và /actuator/metrics nếu được bật và bảo vệ phù hợp. Tên metric và điều kiện xuất hiện phụ thuộc phiên bản, registry và cấu hình Tomcat MBean registry. Tránh giả định một metric sẽ luôn có sẵn trên mọi hệ thống.

**Triển khai:** test rolling update, graceful shutdown, readiness, số lượng connector sau startup và khả năng reclaim port khi JVM dừng. Cổng phụ phải được xét trong manifest, firewall và monitoring nếu có.

### 11.1. Kiểm tra với request có Host hoặc forwarded header

Ở môi trường có proxy, có thể kiểm tra thêm:

~~~bash
curl -i http://localhost:8080/hello
curl -i http://localhost:8081/hello
curl -i -H 'X-Forwarded-Proto: https' http://localhost:8080/hello
~~~

Lệnh thứ ba chỉ để quan sát khi đã xác định chính sách proxy trust; không nên bật tin tưởng mọi forwarded header rồi dùng endpoint công khai để kiểm thử. Với redirect, kiểm tra Location header; với session kiểm tra Secure/SameSite; với authentication kiểm tra chính sách cho từng đường đi.

## 12. Các lỗi thường gặp và hướng chẩn đoán

### 12.1. Customizer không chạy

**Triệu chứng:** ứng dụng vẫn dùng giá trị mặc định dù có bean WebServerFactoryCustomizer<TomcatServletWebServerFactory>.

**Kiểm tra:** ứng dụng thật sự sử dụng embedded Servlet Tomcat hay Jetty/Undertow; bean có nằm trong component scan không; cấu hình điều kiện có bật không; có startup khác profile không; các customizer sau đó có ghi đè giá trị không. Với ứng dụng WebFlux, không áp dụng mặc định logic của Servlet factory.

### 12.2. Port phụ không mở

**Triệu chứng:** cổng 8080 hoạt động nhưng 8081 không LISTEN.

**Kiểm tra:** addAdditionalTomcatConnectors có được gọi trong quá trình tạo factory không; Connector có port hợp lệ không; cổng đã bị chiếm chưa; bind address, firewall, container port publishing và log khởi động. Không chỉ nhìn đường dẫn /hello mà bỏ qua việc cổng chưa được xuất bản ra host.

### 12.3. Connector phụ có timeout khác cổng chính

**Nguyên nhân thường gặp:** addConnectorCustomizers áp dụng cho connector factory tạo, không tự áp dụng cho connector thêm bằng addAdditionalTomcatConnectors. Cần cấu hình trực tiếp Connector phụ và protocol handler của nó. Kiểm thử từng listener với một request/connection thích hợp.

### 12.4. Server báo đã khởi động nhưng API chưa sẵn sàng

Cổng mở chứng minh listener đang hoạt động, chưa chứng minh ApplicationRunner đã hoàn tất, dependency quan trọng đã sẵn sàng hoặc readiness probe đã UP. Kiểm tra /actuator/health/readiness, log lifecycle, database và downstream. Không coi “Tomcat started on port” là tiêu chí duy nhất để đưa instance vào load balancer.

### 12.5. Thêm cổng HTTP làm lộ API nội bộ

Khi thêm cổng, tất cả handler trong cùng Servlet web context có thể truy cập qua cổng đó. Nếu authentication, rate limit hay TLS chỉ tồn tại ở reverse proxy phía trước cổng chính, cổng phụ có thể tạo đường vòng. Hạn chế network, thiết lập bảo vệ theo connector và kiểm tra toàn bộ endpoint được mở.

### 12.6. Tăng threads.max nhưng vẫn timeout

Timeout có thể đến từ database pool, lock, external HTTP client, synchronous processing hoặc CPU. Theo dõi thread dump, DB pool wait, request queue, GC và latency. Nếu sử dụng Java 21 virtual threads, còn cần xác minh cấu hình thread model thực tế để tránh kết luận sai về threads.max.

### 12.7. Kết nối bị reset khi keep-alive

Proxy hoặc client có thể cố tái sử dụng kết nối đã bị Tomcat đóng. So sánh keep-alive/idle timeout ở client, proxy và Tomcat; kiểm tra retry behavior có idempotency và connection pooling. Không kéo dài mọi timeout vô hạn vì có nguy cơ tăng số socket nhàn rỗi.

### 12.8. HTTP 400/431/413 khi gửi request lớn

Lỗi có thể liên quan kích thước header, body, số parameter, URL, giới hạn multipart hoặc proxy. Xác định tầng từ chối request trước khi đổi max header size hoặc giới hạn connector. Nới giới hạn cần tính tới memory, denial-of-service risk và quy định API.

### 12.9. Port phụ hiển thị redirect sang HTTP dù bên ngoài dùng HTTPS

Nguyên nhân có thể là thiếu proxy forwarding config, cấu hình SSL/secure/scheme khác nhau giữa connector, hoặc không tin proxy đúng cách. Kiểm tra trực tiếp Host, X-Forwarded-Proto, Location, cookie và security chain theo từng listener. Không tự cấu hình trust tất cả client để sửa redirect.

### 12.10. Cố thay embedded Tomcat bằng một instance tự tạo

Tự tạo Tomcat object không phối hợp đúng với Spring Boot Servlet context có thể làm mất auto-registration của Servlet, Filter, listener hoặc cấu hình Boot. Trước khi viết một factory mới, xác định liệu property, WebServerFactoryCustomizer hoặc factory hook đã giải quyết được nhu cầu chưa.

## 13. Tình huống lựa chọn cách tùy chỉnh

**Tình huống A — Chỉ muốn chạy port 9090.** Dùng server.port=9090 hoặc biến môi trường tương ứng. Không cần TomcatServletWebServerFactory bean, addConnectorCustomizers hay Connector mới.

**Tình huống B — Muốn tăng số worker thread ở ứng dụng xử lý request blocking.** Bắt đầu với server.tomcat.threads.max, đo tải thật, DB pool và latency. Nếu ứng dụng dùng virtual threads, xác nhận tác dụng của setting trước. Không tăng vô hạn.

**Tình huống C — Một sản phẩm cần thêm cổng HTTP nội bộ 8081.** Dùng WebServerFactoryCustomizer và addAdditionalTomcatConnectors, cấu hình riêng connector mới và chặn network truy cập ngoài. Kiểm tra endpoint, security, logs và health trên cả hai port.

**Tình huống D — Muốn HTTP và HTTPS cùng trên một Tomcat.** Thường dùng server.ssl.* cho listener chính, rồi bổ sung connector khác có cấu hình rõ ràng nếu cần. Việc có hai connector không đồng nghĩa tự redirect HTTP sang HTTPS. Hãy kiểm tra TLS, policy chuyển hướng, cookie và forwarded headers.

**Tình huống E — Muốn thêm access log và request diagnostics.** Xem server.tomcat.accesslog.* và Spring Boot logging/Micrometer trước. Nếu yêu cầu chỉ ở tầng HTTP controller, interceptor/filter thường dễ kiểm thử và ít gắn chặt với Tomcat hơn một Valve.

**Tình huống F — Muốn quản lý health/metrics trên cổng khác.** Xem management.server.port và các thiết lập Actuator. Dùng thêm Connector ứng dụng chỉ khi thật sự cần chia sẻ cùng Servlet context trên nhiều cổng.

**Tình huống G — Muốn giới hạn URI encoding hoặc async timeout đặc thù.** Kiểm tra server.tomcat.uri-encoding và timeout property trước; chỉ khi thiếu khả năng biểu diễn mới dùng TomcatConnectorCustomizer hoặc protocol handler customizer.

## 14. Checklist trước khi đưa cấu hình vào production

- [ ] Xác nhận ứng dụng dùng Servlet và embedded Tomcat, không dùng container bên ngoài.
- [ ] Kiểm tra dependency tree, phiên bản Spring Boot/Tomcat và factory thực tế.
- [ ] Ưu tiên server.* / server.tomcat.* / server.ssl.* cho các tùy chọn có sẵn.
- [ ] Chỉ thêm WebServerFactoryCustomizer khi cần API Tomcat đặc thù.
- [ ] Mọi Connector phụ có port/bind address/protocol/timeout/SSL riêng được xác định rõ.
- [ ] Không giả định addConnectorCustomizers của connector chính áp dụng cho connector phụ.
- [ ] Kiểm tra xung đột cổng và network exposure trong Docker/Kubernetes/firewall.
- [ ] Kiểm tra reverse proxy, trusted forwarded headers, HTTPS, redirect và security.
- [ ] Tách riêng HTTP listener, Servlet Filter, Spring Security và MVC controller trong thiết kế.
- [ ] Không đánh đồng maxConnections, maxThreads, acceptCount và DB pool.
- [ ] Load test và kiểm tra p95/p99 latency, CPU, GC, threads, connection count và downstream.
- [ ] Kiểm tra readiness/liveness, graceful shutdown và lỗi startup.
- [ ] Có khả năng rollback cấu hình và đo trước/sau mỗi thay đổi.
- [ ] Ghi rõ nơi cấu hình cuối cùng khi nhiều customizer cùng ảnh hưởng một tham số.

## 15. Nguyên tắc cần nhớ

TomcatServletWebServerFactory là **điểm cấu hình và tạo embedded Tomcat** trong Spring Boot Servlet. Connector là **đầu vào mạng** của Tomcat. Spring MVC controller là **tầng xử lý HTTP nghiệp vụ**. Ba khái niệm phục vụ các mục đích khác nhau, nên thay đổi ở đúng tầng.

Với cấu hình thông dụng, dùng application.yml là rõ ràng và dễ vận hành nhất. Với cấu hình không có property Boot tương ứng, WebServerFactoryCustomizer<TomcatServletWebServerFactory> là điểm mở rộng được hỗ trợ. Khi muốn thêm một listener, sử dụng addAdditionalTomcatConnectors và cấu hình trực tiếp Connector bổ sung; customizer của connector mặc định không được tự áp dụng cho connector này.

Bất kỳ thay đổi nào về port, thread, connection, timeout, HTTP/HTTPS hay proxy đều cần được kiểm tra bằng kết quả thực tế, chứ không chỉ bằng log startup. Đo đúng tầng, giới hạn tài nguyên hợp lý và đảm bảo security trước khi triển khai sẽ giúp ứng dụng có behavior rõ ràng và dễ bảo trì.

## 16. Tài liệu tham khảo

- Spring Boot 3.3 — Servlet Web Applications (mục Embedded Servlet Container Support và Programmatic Customization): https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Embedded Web Servers, Enable Multiple Connectors with Tomcat: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — API TomcatServletWebServerFactory: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/embedded/tomcat/TomcatServletWebServerFactory.html
- Apache Tomcat 10.1 — HTTP Connector Configuration: https://tomcat.apache.org/tomcat-10.1-doc/config/http.html

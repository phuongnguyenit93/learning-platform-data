# Thứ tự WebServerFactoryCustomizer và quan hệ với cấu hình `server.*` trong Spring Boot

## 1. Vấn đề cần hiểu

Spring Boot cho phép cấu hình máy chủ HTTP nhúng theo hai cách phổ biến: khai báo các thuộc tính `server.*` trong cấu hình ứng dụng, và viết bean `WebServerFactoryCustomizer` để can thiệp bằng mã Java vào factory tạo web server. Khi cả hai cùng thay đổi một thuộc tính, ví dụ cổng lắng nghe, kết quả phụ thuộc vào **thứ tự customizer được áp dụng lên factory**.

Câu hỏi cần giải đáp:
- `server.port`, `server.address`, `server.servlet.context-path` và `server.tomcat.*` được áp dụng ở giai đoạn nào?
- `@Order` và `Ordered` chi phối thứ tự thực thi customizer như thế nào?
- Giá trị `server.port` từ `application.properties`, environment variable hoặc command line có ưu tiên tuyệt đối trước mã Java không?
- Nếu nhiều customizer cùng gọi `setPort`, cấu hình cuối cùng là gì?
- Làm thế nào xác nhận giá trị cấu hình, giá trị trên factory và cổng HTTP thực tế?
- Customizer khác nhau thế nào giữa Servlet MVC, WebFlux và các engine Tomcat, Jetty, Undertow, Reactor Netty?

Ví dụ Java trong bài nhắm vào **Spring Boot 3.5.x + Java 17+ + `spring-boot-starter-web`**. Trong Spring Boot 4, một số package và tên module đã thay đổi; kiểm tra API đúng phiên bản thay vì sao chép nguyên import 3.x sang 4.x.

## 2. Trước hết: `server.*` và `WebServerFactoryCustomizer` không cùng một loại ưu tiên

Một giá trị cấu hình đi qua hai giai đoạn logic:

1. **Giải quyết thuộc tính:** Spring Boot gom nhiều `PropertySource` vào `Environment`. Quy tắc ưu tiên nguồn cấu hình chọn ra giá trị hiện hành cho key như `server.port`.
2. **Áp dụng lên web server factory:** Các thành phần cấu hình tự động dùng giá trị đã bind trong `ServerProperties` để chỉnh factory. Các bean `WebServerFactoryCustomizer` khác cũng có thể chỉnh cùng factory trước khi factory tạo server thật.

Có thể hình dung:

~~~text
application.properties, application.yaml
environment variables, system properties, CLI arguments
                      |
                      v
        Spring Environment / PropertySources
                      |
           @ConfigurationProperties
                      |
                      v
          ServerProperties (server.*)
                      |
                      v
   WebServerFactoryCustomizer tự động (order 0)
                      |
                      v
   WebServerFactoryCustomizer do ứng dụng cung cấp
          (có thể sớm hơn hoặc muộn hơn)
                      |
                      v
           WebServerFactory cuối cùng
                      |
                 getWebServer()
                      |
                      v
     Tomcat / Jetty / Undertow / Reactor Netty chạy
~~~

Đây là sơ đồ khái niệm, không phải cam kết từng bean được tạo ở một thời điểm cố định. Cấu hình máy chủ còn có các customizer đặc thù của từng container và những bước diễn ra khi tạo connector hoặc khởi động server.

**Phân biệt hai câu hỏi:** “Key `server.port` nhận giá trị nào trong `Environment`?” là câu hỏi về ưu tiên `PropertySource`; “máy chủ cuối cùng lắng nghe ở cổng nào?” còn phụ thuộc vào các can thiệp lập trình lên factory.

## 3. Cấu hình `server.*` từ Environment và ServerProperties

Spring Boot có cơ chế `@ConfigurationProperties` để bind các thuộc tính liên quan đến server từ `Environment` vào cấu trúc cấu hình như `ServerProperties`. Một số key thường dùng:

| Thuộc tính | Ý nghĩa | Lưu ý |
|---|---|---|
| `server.port` | Cổng HTTP chính, thường mặc định 8080 | `0` yêu cầu chọn cổng ngẫu nhiên còn trống; `-1` tắt HTTP endpoints nhưng vẫn giữ web context trong một số tình huống |
| `server.address` | Địa chỉ mạng mà server bind | Xem xét khi chạy trong container, trên localhost hoặc sau reverse proxy |
| `server.servlet.context-path` | Context path cho ứng dụng Servlet | Thuộc tính dành cho Servlet; không áp đặt cơ học cho WebFlux |
| `server.ssl.*` | Chứng chỉ, khóa, giao thức và các thiết lập HTTPS | Thay đổi SSL phải xét cả việc tạo connector và tài liệu phiên bản |
| `server.http2.enabled` | Cho phép HTTP/2 nếu engine và môi trường đáp ứng | Hiệu lực tùy hỗ trợ của engine/TLS |
| `server.compression.*` | Cấu hình nén phản hồi | Đừng giả định mọi response đều được nén |
| `server.tomcat.*` | Tùy chọn riêng Tomcat | Chỉ có ý nghĩa cho Tomcat và đúng phiên bản |
| `server.jetty.*` | Tùy chọn riêng Jetty | Không dùng để cấu hình Tomcat |
| `server.netty.*` | Tùy chọn áp dụng cho Reactor Netty khi được hỗ trợ | Xem metadata cấu hình phiên bản đang chạy |

Ví dụ `src/main/resources/application.properties`:

~~~properties
server.port=8085
server.servlet.context-path=/demo
server.compression.enabled=true
~~~

Khi không có customizer khác thay đổi cổng, ứng dụng Servlet thường phục vụ tại `http://localhost:8085/demo`.

Spring Boot hỗ trợ relaxed binding: `server.port` có thể nhận giá trị từ biến môi trường `SERVER_PORT`. Command line `--server.port=9090` thường ưu tiên hơn cấu hình trong file. Tuy vậy, sau khi `Environment` đã chọn một giá trị, mã Java chạy muộn trên factory vẫn có thể thay thế giá trị áp dụng lên **server thực**, nếu can thiệp cùng thuộc tính.

### 3.1. Ví dụ phân biệt hai tầng ưu tiên

Giả sử:
- File `application.properties` khai báo `server.port=8085`.
- Khởi động bằng `--server.port=9090`.
- `Environment.getProperty("server.port")` trả `9090` theo thứ tự ưu tiên thuộc tính.
- Customizer có thứ tự muộn gọi `factory.setPort(9191)`.

Kết quả thông thường: `ServerProperties` mang cổng cấu hình 9090, nhưng server chạy ở **9191**. Đây không phải lỗi binding. Mã customizer đã chủ động thay đổi factory sau khi thông số cấu hình được áp dụng.

## 4. Cơ chế áp dụng WebServerFactoryCustomizer

`WebServerFactoryCustomizer<T extends WebServerFactory>` có một phương thức `customize(T factory)`. Bean post-processor của Spring Boot thu thập những customizer phù hợp với kiểu factory đang được tạo, sắp xếp theo quy tắc order, sau đó gọi `customize` trước khi factory khởi tạo web server.

### 4.1. Thứ tự tăng dần: số nhỏ chạy trước

Trong hệ sinh thái Spring, các quy tắc phổ biến là:

- `Ordered.HIGHEST_PRECEDENCE` hoặc giá trị âm nhỏ hơn: ưu tiên rất cao, chạy sớm.
- `@Order(-100)`: thường chạy trước `@Order(0)`.
- `@Order(0)`: chạy giữa các giá trị âm và dương.
- `@Order(100)`: chạy sau `@Order(0)`.
- `Ordered.LOWEST_PRECEDENCE`: ưu tiên thấp, thường chạy muộn.

**Giá trị order nhỏ hơn nghĩa là được thực thi trước**, không có nghĩa có quyền ghi đè mạnh hơn. Nếu hai customizer gọi cùng một setter trên cùng factory, người thực thi **sau** thường quyết định giá trị còn lại ở thuộc tính đó, trừ khi bước xử lý khác trong container tiếp tục thay đổi kết quả.

### 4.2. Thứ tự customizer có sẵn của Spring Boot

Tài liệu chính thức Spring Boot về embedded servers cho biết các `WebServerFactoryCustomizer` do Boot auto-configure có **order `0`** và được xử lý trước customizer người dùng không khai báo thứ tự rõ ràng. Do vậy:

| Bean | Order | Kỳ vọng đối với `server.port` |
|---|---:|---|
| Customizer ứng dụng có `@Order(-100)` | -100 | Chạy sớm, thiết lập của nó có thể bị customizer tự động order 0 thay thế |
| Customizer cấu hình server do Boot tạo | 0 | Áp dụng thông số đã bind từ `ServerProperties` |
| Customizer ứng dụng có `@Order(100)` | 100 | Chạy muộn hơn order 0, có thể đổi `setPort` |
| Customizer không chỉ định `@Order` / `Ordered` | Thường tương đương ưu tiên thấp | Tài liệu Boot bảo đảm customizer tự động order 0 được xử lý trước các bean ứng dụng không chỉ định order |

Nếu nhiều customizer có **cùng một order**, không nên phụ thuộc vào việc bean nào tình cờ được liệt kê hoặc tạo trước. Hãy khai báo thứ tự khác nhau cho các customizer thực sự phụ thuộc lẫn nhau hoặc loại bỏ các setter xung đột.

### 4.3. Các cách khai báo thứ tự

Tùy kiểu bean có thể dùng:

~~~java
@Component
@Order(100)
class LatePortCustomizer
        implements WebServerFactoryCustomizer<ConfigurableServletWebServerFactory> {
    @Override
    public void customize(ConfigurableServletWebServerFactory factory) {
        factory.setPort(9191);
    }
}
~~~

Đây là ví dụ class đặt trong dự án Spring Boot 3.x có các import tương ứng; bản hoàn chỉnh ở mục tiếp theo.

Hoặc triển khai trực tiếp `Ordered`:

~~~java
class OrderedPortCustomizer
        implements WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>,
                   Ordered {
    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void customize(ConfigurableServletWebServerFactory factory) {
        factory.setPort(9191);
    }
}
~~~

Mẫu thứ hai chỉ được tham gia áp dụng khi class được đăng ký làm bean Spring. Không nhầm order của factory customizer với `FilterRegistrationBean.setOrder`, thứ tự Spring Security filter chain, `@Order` của advice hoặc thứ tự `ApplicationRunner`: đó là các cơ chế riêng.

## 5. Ví dụ Java 17+ chạy được: customizer sớm, cấu hình tự động, customizer muộn

Tạo một dự án **Spring Boot 3.5.x** dùng Java 17 trở lên và dependency `spring-boot-starter-web` (Tomcat nhúng mặc định). Đặt `application.properties` như sau:

~~~properties
server.port=8085
server.servlet.context-path=/demo
~~~

Tạo file `src/main/java/example/web/CustomizerOrderApplication.java`:

~~~java
package example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.servlet.server.ConfigurableServletWebServerFactory;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CustomizerOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomizerOrderApplication.class, args);
    }

    @Bean
    ApplicationListener<WebServerInitializedEvent> portObserver(Environment env) {
        return event -> System.out.printf(
                "CHECK configured=%s actual=%d%n",
                env.getProperty("server.port"),
                event.getWebServer().getPort());
    }
}

@Component
@Order(-100)
class EarlyPortCustomizer
        implements WebServerFactoryCustomizer<ConfigurableServletWebServerFactory> {

    @Override
    public void customize(ConfigurableServletWebServerFactory factory) {
        factory.setPort(7001);
        System.out.println("EARLY: setPort(7001)");
    }
}

@Component
@Order(100)
class LatePortCustomizer
        implements WebServerFactoryCustomizer<ConfigurableServletWebServerFactory> {

    @Override
    public void customize(ConfigurableServletWebServerFactory factory) {
        factory.setPort(9191);
        System.out.println("LATE: setPort(9191)");
    }
}

@RestController
class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Khởi động bằng wrapper của build tool:

~~~bash
./mvnw spring-boot:run
# hoặc:
./gradlew bootRun
~~~

Ba dòng do code minh họa tự in ra được kỳ vọng có thứ tự như sau (các dòng log Spring Boot thông thường có thể xen giữa):

~~~text
EARLY: setPort(7001)
LATE: setPort(9191)
CHECK configured=8085 actual=9191
~~~

Kiểm tra HTTP:

~~~bash
curl -s http://localhost:9191/demo/ping
~~~

Body:

~~~text
pong
~~~

**Giải thích chính xác:**

1. `EarlyPortCustomizer` có order -100, nên gọi `setPort(7001)` trước customizer tự động order 0.
2. Customizer cấu hình của Boot áp dụng `server.port=8085`, thay thế giá trị cổng sớm 7001 trên factory.
3. `LatePortCustomizer` order 100 tiếp tục `setPort(9191)`, nên factory cuối cùng mang cổng 9191.
4. `Environment` vẫn biết `server.port=8085`; customizer Java không ghi lại `Environment`.
5. `server.servlet.context-path=/demo` vẫn hoạt động do customizer trên chỉ đổi port. Request tới `/demo/ping` trả `pong`.

Nếu muốn quan sát trạng thái thiếu customizer muộn, **loại bean `LatePortCustomizer` khỏi project thử nghiệm và khởi động lại**. Khi đó customizer tự động áp dụng `server.port=8085` sau early order -100, nên server thông thường lắng nghe ở 8085. Đây là thay đổi ví dụ để học, không cần sửa cấu hình sản phẩm thật.

### 5.1. Thử với command line

Chạy:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--server.port=8099
~~~

Nếu cú pháp truyền tham số được wrapper/plugin Maven trong project hỗ trợ như ví dụ, `Environment.getProperty("server.port")` sẽ là 8099. Tuy nhiên `LatePortCustomizer` vẫn gọi `setPort(9191)`, nên server vẫn dùng 9191. Kiểm tra bằng dòng `CHECK` và HTTP request thật.

Lệnh đóng gói thuần Java tương đương sau khi đã tạo executable JAR:

~~~bash
java -jar target/my-app.jar --server.port=8099
~~~

Trong câu lệnh cuối, `target/my-app.jar` đại diện cho **tên file JAR được build thật**; thay bằng tên thực tế. Mục tiêu là minh họa thứ tự `PropertySource` khác thứ tự customizer.

## 6. Bảng kết quả khi nhiều customizer xung đột

Giả sử cùng có `server.port=8085` và không có customizer khác sau những bước được liệt kê:

| Các thao tác trên cùng factory | Giá trị cổng thường thu được | Giải thích |
|---|---:|---|
| Chỉ cấu hình `server.port` | 8085 | Customizer Boot dùng ServerProperties |
| `@Order(-100)` setPort(7001), rồi Boot order 0 | 8085 | Boot ghi cổng muộn hơn |
| Boot order 0, rồi `@Order(100)` setPort(9191) | 9191 | Customizer ứng dụng ghi muộn |
| Early -100, Boot 0, Late 100 | 9191 | Thứ tự cuối của setter quyết định |
| Hai customizer cùng `@Order(100)` thiết lập hai port khác nhau | Không nên dự đoán | Cần định nghĩa thứ tự rõ hoặc bỏ xung đột |
| Một customizer đặt port, customizer khác chỉ thêm connector | Phụ thuộc API server cụ thể | Nhiều connector khác nhau có thể lắng nghe nhiều cổng |

Bảng chỉ minh họa xung đột của **một setter trên một factory**. Với SSL, HTTP/2, context path, thread pool hoặc connector customizer, việc “last setter wins” có thể chưa đủ mô tả vì API có thể cộng dồn callback, thay đối tượng, hoặc áp dụng biến đổi ở giai đoạn tạo server.

## 7. Phân biệt factory-level và container-level customizer

Một project có thể đồng thời sử dụng:
- `WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>`: thay đổi các thông số chung của factory Servlet như port, address, context path trong phạm vi API hỗ trợ.
- `WebServerFactoryCustomizer<TomcatServletWebServerFactory>`: thay đổi factory cụ thể của Tomcat; không chạy với factory Jetty.
- `TomcatConnectorCustomizer` hoặc các callback container-specific: can thiệp đối tượng connector khi Tomcat được dựng từ factory.
- `WebServerFactoryCustomizer<ConfigurableReactiveWebServerFactory>`: dành cho factory reactive, khác với Servlet.
- `WebServerFactoryCustomizer<NettyReactiveWebServerFactory>`: cụ thể cho Reactor Netty.

Một customizer generic theo loại Servlet chỉ áp dụng cho factory đúng kiểu; nó **không phải** interceptor chung cho cả MVC và WebFlux. Cùng ứng dụng có `spring-boot-starter-webflux` trên classpath không tự bảo đảm request được phục vụ bằng WebFlux khi starter-web cũng có mặt; cần biết `WebApplicationType` thực tế.

Thứ tự `@Order` ở factory-level chi phối thứ tự gọi các **bean factory customizer phù hợp**. Nó không tự quyết định thứ tự của callback Tomcat được factory thực thi lúc tạo connector, hay thứ tự filter trong request pipeline. Với customizer dạng `add*Customizer`, kết quả có thể phụ thuộc thứ tự các callback được thêm vào và cơ chế của server engine.

## 8. Khi nào ưu tiên `server.*`, khi nào viết customizer?

**Ưu tiên cấu hình khai báo `server.*`** khi đã có key chính thức:
- Port, address, compression, SSL, HTTP/2.
- Các thông số servlet hoặc container-specific đã được Boot công bố.
- Cần phân biệt dev/staging/prod qua profile, environment variable, ConfigMap hoặc deployment chart.

**Chỉ dùng customizer Java** khi thuộc tính chính thức không thể biểu diễn yêu cầu:
- Bổ sung connector hoặc chỉnh một setting native của Tomcat/Jetty/Netty.
- Áp dụng quy tắc động phụ thuộc một bean cấu hình chuyên biệt.
- Tích hợp một extension server engine không có key tương ứng.

Khi customizer Java cần một giá trị cấu hình động, hãy định nghĩa property nghiệp vụ riêng và bind nó vào một bean `@ConfigurationProperties`, sau đó truyền rõ vào customizer. Tránh hard-code port làm mất khả năng cấu hình qua `server.port`, trừ khi việc ghi đè được yêu cầu và được kiểm thử rõ ràng.

Ví dụ minh họa trong lớp có `Environment` (fragment, cần import và đăng ký thành bean):

~~~java
@Override
public void customize(ConfigurableServletWebServerFactory factory) {
    Integer override = environment.getProperty(
            "demo.embedded-server.override-port", Integer.class);
    if (override != null) {
        factory.setPort(override);
    }
}
~~~

Ở đoạn này `environment` là một field được inject trong constructor. Nếu không có key `demo.embedded-server.override-port`, customizer không đổi port và `server.port` vẫn có hiệu lực. Với ứng dụng lớn nên dùng type-safe configuration thay vì truy cập `Environment` phân tán.

## 9. Các trường hợp cần đặc biệt cẩn thận

### 9.1. Port ngẫu nhiên `server.port=0`

`server.port=0` yêu cầu hệ điều hành cấp cổng còn trống; cổng thực tế chỉ được biết sau khi server được tạo/khởi động. Nếu một customizer muộn đặt cố định `setPort(9191)`, yêu cầu random port bị thay thế, có thể khiến test chạy song song xung đột cổng.

Để lấy cổng thật trong runtime, sử dụng `WebServerInitializedEvent` và `event.getWebServer().getPort()`. Với integration test Spring Boot có thể dùng `@LocalServerPort` khi được cấu hình `@SpringBootTest(webEnvironment = RANDOM_PORT)`. Không lấy `server.port` từ `Environment` và xem nó luôn là cổng đang lắng nghe.

### 9.2. `management.server.port` và nhiều web contexts

Nếu Actuator management server chạy trên cổng tách biệt, hệ thống có thể có thêm context hoặc web server khác. Hãy xác định bean customizer nào áp dụng trong từng context, và phân biệt `server.port` với `management.server.port`. Một `ApplicationListener<WebServerInitializedEvent>` có thể nhận hơn một sự kiện trong cấu hình nhiều server; phải nhận biết context đang phát sự kiện. Không suy ra một cổng từ sự kiện đầu tiên mà bỏ qua management server.

### 9.3. SSL, HTTP/2 và nhiều connector

`server.ssl.*`, `server.http2.enabled` có thể liên quan đến cài đặt native và callback ở bước tạo server. Việc thêm HTTP connector phụ khi đã bật HTTPS không thể thực hiện chỉ bằng cách khai báo hai giá trị `server.port`; cần API server-specific và kiểm thử. Không dùng mẹo đổi `setPort` để thay thế một cấu hình nhiều connector.

### 9.4. Thay bean WebServerFactory

Khai báo một bean `ServletWebServerFactory` hoặc `ReactiveWebServerFactory` riêng có thể khiến auto-configured factory của Boot rút lui. Tuy nhiên **các customizer của Boot vẫn có thể được áp dụng lên factory tự tạo**. Vì vậy không nên giả định bean factory tùy chỉnh tự động bỏ qua mọi `server.*`. Kiểm thử trường hợp này trên phiên bản Boot và engine đang dùng.

### 9.5. Đổi cấu hình trong runtime

Giá trị `server.port` trong property source thay đổi sau khi server đã khởi động không đồng nghĩa socket đang lắng nghe tự chuyển cổng. Factory customizer thường chạy trong pha tạo/khởi động factory, không phải một controller điều chỉnh server liên tục. Đổi cổng, TLS hoặc connector thường đòi hỏi quy trình reconfiguration/restart an toàn được server engine hỗ trợ.

## 10. Cách xác minh và gỡ lỗi sự khác biệt cấu hình

Bắt đầu bằng ba giá trị **khác nhau về bản chất**:

1. **Giá trị trong Environment:** `environment.getProperty("server.port")`.
2. **Giá trị áp dụng cho factory:** quan sát trong customizer tương ứng, log từng setter ở môi trường thử nghiệm hoặc debug trong bean post-processor.
3. **Giá trị server thực:** `WebServerInitializedEvent.getWebServer().getPort()` hoặc một HTTP request tới cổng đang hoạt động.

Để tìm nguyên nhân:
- Kiểm tra `application.properties`, profile-specific configs, environment variable `SERVER_PORT`, JVM system property và CLI argument.
- Xác nhận process dùng web stack và container nào; generic type của customizer có phù hợp không.
- Liệt kê các bean `WebServerFactoryCustomizer` đang tồn tại (chỉ trong công cụ debug có quyền truy cập context).
- Kiểm tra `@Order` / `Ordered` của từng bean và nơi setter cùng thuộc tính được gọi.
- Tìm `setPort`, `setAddress`, `setContextPath`, `addConnectorCustomizer`, `addServerCustomizers`.
- Đọc startup log của container, kiểm tra OS port hoặc gửi request HTTP thực tế.
- Chú ý cả môi trường chạy trong Docker/Kubernetes: port bind trong tiến trình khác host port được publish hoặc service port bên ngoài.

Actuator `/actuator/env` và `/actuator/configprops` (nếu được bật và cấp quyền) có thể giúp tìm nguồn thuộc tính và giá trị bind. **Chúng không tự chứng minh giá trị port đã được customizer áp dụng lên server cuối**. Không công khai các endpoint quản trị hoặc bí mật cấu hình chỉ để debug.

### 10.1. Một test tích hợp hữu ích

Với ví dụ ở mục 5, có thể chạy ứng dụng và gửi request:

~~~bash
curl -i http://localhost:9191/demo/ping
~~~

Kết quả mong đợi: phản hồi HTTP 200 với body `pong` nếu không có proxy/port collision và cấu hình đúng như ví dụ. Kiểm tra thêm:
- Cổng 8085 không phải cổng chính đang lắng nghe của ví dụ cuối.
- Dòng `CHECK` cho biết cấu hình 8085 nhưng cổng thực 9191.
- Nếu bỏ customizer muộn, port dự kiến trở về 8085.
- Nếu chạy test random port, cần loại bỏ hoặc vô hiệu hóa customizer hard-code trước khi kỳ vọng cơ chế cấp port ngẫu nhiên.

Đối với automated integration test, ưu tiên đưa flag override vào một cấu hình riêng cho test hoặc thiết kế customizer không cứng cổng khi test; đo cổng thật qua `@LocalServerPort`, rồi gửi HTTP request đến cổng đó. Test chỉ assert `Environment.getProperty("server.port")` có thể bỏ sót lỗi customizer ghi đè.

## 11. Những lỗi thường gặp

1. **Nhầm `@Order(-100)` là “ưu tiên ghi đè cao nhất”.** Số nhỏ chạy trước, nên giá trị có thể bị bean order 0 đặt lại.
2. **Tin rằng `server.port` luôn thắng mọi setter Java.** Thực tế property binding và factory customization là hai giai đoạn.
3. **Cho rằng thứ tự liệt kê bean trong source quyết định thứ tự.** Cần `Ordered` hoặc `@Order` rõ ràng.
4. **Hai customizer cùng order và cùng sửa một thuộc tính.** Không nên phụ thuộc thứ tự bằng nhau.
5. **Chỉnh nhầm factory loại khác.** Customizer Servlet không điều khiển Reactor Netty reactive factory.
6. **Nhầm factory customizer với servlet Filter order hoặc Tomcat connector callback order.** Các cơ chế thực thi khác nhau.
7. **Ghi đè `server.port=0` trong test.** Làm mất cổng ngẫu nhiên, khiến CI test không ổn định.
8. **Xem `Environment` là bằng chứng server đang chạy ở cổng đó.** Phải kiểm tra `WebServerInitializedEvent` hoặc HTTP thực.
9. **Hard-code cổng trong shared library.** Có thể vô tình làm mất cấu hình triển khai và tạo xung đột trên máy chủ.
10. **Thay factory bean nhưng nghĩ auto-customizer ngừng chạy.** Customizer được áp dụng lên factory phù hợp, kể cả factory tự định nghĩa.
11. **Cố gắng cấu hình hai connector bằng một `server.port`.** Phải dùng server-specific API và kiểm chứng.
12. **Chỉ thay property runtime và chờ server tự đổi cổng.** Startup binding không phải cơ chế hot reload socket.

## 12. Checklist trước khi dùng customizer trong dự án

- [ ] Đã tìm trong Spring Boot configuration metadata xem `server.*` có đủ cho yêu cầu không.
- [ ] Đã phân biệt giá trị được giải quyết từ `PropertySource` với giá trị factory sau customizers.
- [ ] Đã xác định chính xác web stack và kiểu factory generic phù hợp.
- [ ] Đã kiểm tra các auto-configured customizers order 0 trên phiên bản đang dùng.
- [ ] Đã khai báo thứ tự customizer ứng dụng bằng số khác nhau nếu cần phụ thuộc.
- [ ] Đã tránh nhiều setter xung đột cùng một thông số hoặc ghi rõ chủ sở hữu của thông số đó.
- [ ] Đã kiểm tra trường hợp `server.port=0`, profile test, management port và nhiều connector.
- [ ] Đã xác minh cổng thực qua `WebServerInitializedEvent` hoặc HTTP request.
- [ ] Đã kiểm thử các key `server.ssl.*`, `server.tomcat.*` hoặc `server.netty.*` với engine đúng loại.
- [ ] Đã ghi rõ phạm vi áp dụng và hành vi khi đổi version Spring Boot.

## 13. Kết luận

Với Spring Boot, `server.*` cung cấp cấu hình khai báo, được giải quyết từ `Environment` và áp dụng lên factory nhờ auto-configuration. **Các `WebServerFactoryCustomizer` của Boot có order 0; customizer ứng dụng chạy sau có thể ghi đè thuộc tính trên factory mà không thay đổi giá trị gốc trong Environment.** Số order nhỏ chạy trước; nếu cùng setter được gọi nhiều lần, cần kiểm tra thứ tự thực thi và bước tạo server. Ưu tiên `server.*` cho những tùy chọn đã có, dùng customizer Java cho tính năng chưa được hỗ trợ, và luôn xác nhận cấu hình hiệu lực trên web server thực.

## Tài liệu tham khảo

- Spring Boot 3.5, Embedded Web Servers: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5, Servlet Web Applications (Programmatic Customization): https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5, Reactive Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5, Externalized Configuration: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html

# Hệ quả của việc thay toàn bộ WebServerFactory bean thay vì bổ sung WebServerFactoryCustomizer

## 1. Bối cảnh: Spring Boot tạo máy chủ nhúng như thế nào?

Trong ứng dụng Spring Boot dùng embedded HTTP server, framework không khởi động Tomcat, Jetty hay Reactor Netty bằng một lời gọi ngẫu nhiên trong controller. Spring Boot tạo một **web server factory bean**, áp dụng cấu hình lên factory, sau đó yêu cầu factory tạo và khởi động máy chủ. Vì vậy cần phân biệt:

- **Factory bean**: đối tượng chịu trách nhiệm tạo web server, ví dụ `TomcatServletWebServerFactory` cho Spring MVC dùng Tomcat.
- **`WebServerFactoryCustomizer<T>`**: callback thay đổi một factory **đã có** trước khi máy chủ được khởi động. Callback không phải là web server và thông thường không tạo factory mới.
- **Auto-configuration**: Spring Boot dựa vào classpath, loại web application và những bean đang có để tạo factory mặc định phù hợp, rồi cung cấp các customizer cho nhiều thiết lập chung.
- **Web server**: Tomcat/Jetty/Netty thực tế nhận kết nối HTTP sau giai đoạn khởi tạo.

Với Servlet stack, `ServletWebServerApplicationContext` cần một `ServletWebServerFactory` phù hợp. Với reactive stack, `ReactiveWebServerApplicationContext` sử dụng `ReactiveWebServerFactory`. Các factory của hai loại này không thay thế cho nhau.

Lựa chọn thông thường là để Boot tạo factory và cấu hình bằng `application.properties`/`application.yaml`. Khi cần API đặc thù của container mà chưa có property, bổ sung một `WebServerFactoryCustomizer`. **Chỉ tự tạo bean factory nếu thật sự cần kiểm soát cách tạo server**, chẳng hạn thay factory implementation hoặc tùy biến những điểm mở rộng mà customizer không đáp ứng được.

## 2. Hai cách mở rộng hoạt động khác nhau

### Cách A: Giữ factory mặc định và thêm customizer

~~~text
Classpath + WebApplicationType
          |
          v
Spring Boot tự cấu hình factory phù hợp
          |
          v
BeanPostProcessor áp dụng customizers của Boot
          |
          v
Áp dụng customizers của ứng dụng (theo thứ tự)
          |
          v
Tạo embedded server và khởi động
~~~

Ứng dụng bổ sung **một bước cấu hình**. Boot vẫn sở hữu việc chọn factory mặc định. Những tính năng sẵn có của Spring Boot và các customizer khác tiếp tục tham gia theo cơ chế bình thường.

### Cách B: Khai báo bean factory riêng

~~~text
Ứng dụng khai báo @Bean ServletWebServerFactory
          |
          v
Factory auto-configuration của Boot nhường chỗ
          |
          v
Factory do ứng dụng tạo trở thành ứng viên khởi tạo
          |
          v
Các WebServerFactoryCustomizer phù hợp vẫn được áp dụng
          |
          v
Tạo embedded server và khởi động
~~~

**Điểm kỹ thuật rất dễ nhầm:** theo tài liệu chính thức, khi khai báo `WebServerFactory` của riêng mình, factory mà Spring Boot thường tạo sẽ bị thay thế, **nhưng các customizer tự động của Spring Boot vẫn được áp dụng cho custom factory khi phù hợp**. Không đúng khi khẳng định “thay factory làm mọi thiết lập `server.*` mất hiệu lực”. Kết quả phụ thuộc vào loại factory, các giao diện nó triển khai, tập customizer phù hợp và thứ tự thay đổi cấu hình.

| Khía cạnh | Thêm `WebServerFactoryCustomizer` | Tự khai báo `WebServerFactory` |
|---|---|---|
| Ai tạo factory? | Boot tự tạo | Ứng dụng tạo |
| Factory mặc định của Boot? | Giữ lại | Auto-configuration nhường chỗ khi bean phù hợp đã tồn tại |
| Customizer mặc định của Boot? | Vẫn chạy | **Vẫn chạy** nếu áp dụng được với factory mới |
| Nguy cơ sai loại factory | Thấp khi generic đúng server/stack | Cao hơn: có thể tạo factory không thuộc stack đang chạy |
| Tương thích khi nâng version | Thường dễ hơn | Phải rà soát constructor, package, hooks, API container |
| Khả năng kiểm soát | Các setter/hook mà factory cung cấp | Có thể đổi cả implementation hoặc subclass |
| Mức độ sở hữu vòng đời | Chủ yếu cấu hình | Gánh thêm trách nhiệm bảo đảm factory tuân thủ hợp đồng |
| Trường hợp phù hợp | Đổi một vài hành vi của server | Trường hợp đặc biệt không thể giải bằng property/customizer |

## 3. Hệ quả thứ nhất: làm auto-configuration mặc định lùi lại

Spring Boot dùng các điều kiện như `@ConditionalOnMissingBean` để quyết định có tạo bean server factory mặc định hay không. Khi một bean `ServletWebServerFactory` hợp lệ được khai báo bởi ứng dụng, nhánh tạo factory mặc định thường không còn cần thiết. Tương tự, với WebFlux cần xét nhánh `ReactiveWebServerFactory`.

Điều này **không đồng nghĩa với việc tất cả auto-configuration khác biến mất**. Ví dụ Spring MVC mapping, message converter, filter/servlet registration và các tính năng auto-configured khác có những điều kiện riêng. Spring Boot vẫn có thể tạo những bean đó, nhưng chúng chỉ hoạt động đúng nếu custom factory hỗ trợ mô hình khởi động và hợp đồng tương ứng.

Hệ quả thực tế của việc dùng một factory tự viết:

1. Một số hành vi khởi tạo mặc định gắn với implementation mà Boot thường chọn có thể không còn được kế thừa nếu ứng dụng đổi hẳn loại factory.
2. Ứng dụng phải bảo đảm factory được tạo với dependency, API server và phiên bản tương thích.
3. Nếu subclass hoặc implementation không thực hiện đúng `getWebServer(...)` và không áp dụng các `ServletContextInitializer`, việc đăng ký DispatcherServlet, filter, session listener hoặc endpoint có thể không đầy đủ.
4. Nếu có nhiều bean cùng đủ điều kiện làm web server factory, ứng dụng có thể không xác định được duy nhất factory để sử dụng và khởi động thất bại.

**Điểm cần kiểm chứng:** hành vi sẽ khác nhau giữa `new TomcatServletWebServerFactory()` (vẫn là factory chuẩn của Boot, nhận các customizer phù hợp) và một `ServletWebServerFactory` hoàn toàn tự xây (có thể thiếu giao diện cấu hình mà một số customizer yêu cầu). Không được gom hai tình huống này thành cùng một mức rủi ro.

## 4. Hệ quả thứ hai: customizer vẫn chạy, nhưng kết quả có thể bất ngờ

Spring Boot áp dụng `WebServerFactoryCustomizer` qua `WebServerFactoryCustomizerBeanPostProcessor` **trước khi server khởi động**. Factory do ứng dụng khai báo vẫn đi qua cơ chế này. Các customizer của Boot thường có order bằng 0 và chạy trước customizer do ứng dụng định nghĩa, trừ khi ứng dụng đặt thứ tự rõ ràng khác.

Hệ quả của thứ tự:

- Nếu Boot đọc `server.port=9090` và đặt port cho factory, sau đó customizer của ứng dụng đặt `factory.setPort(9191)`, cổng cuối cùng có thể là 9191. Khi kiểm tra cấu hình, phải xem **toàn bộ customizer** thay vì chỉ nhìn `application.properties`.
- Nếu một customizer thêm `TomcatConnectorCustomizer`, còn customizer khác dùng setter thay thế toàn bộ collection thay vì thêm vào, các callback đã đăng ký có thể bị mất. Ưu tiên API dạng `add...` khi thực sự muốn bổ sung.
- Generic `WebServerFactoryCustomizer<TomcatServletWebServerFactory>` chỉ nhắm đến Tomcat Servlet factory tương thích. Nó không tự áp dụng cho Jetty, Netty hay Tomcat Reactive factory.
- Customizer chạy rất sớm trong lifecycle của ApplicationContext, nên việc eager inject quá nhiều bean nghiệp vụ vào customizer có thể kéo theo khởi tạo sớm ngoài mong đợi. Tài liệu API khuyên cân nhắc lazy lookup nếu cần dependency.

Vì vậy, khái niệm “auto-configured customizers vẫn chạy” **không bảo đảm kết quả cuối tự động đúng**. Nó yêu cầu các customizer tương thích và không ghi đè nhau sai thứ tự.

## 5. Hệ quả thứ ba: tăng nguy cơ lệch cấu hình và đặc tính runtime

Các cấu hình thường được Spring Boot xử lý gồm:

| Nhóm | Property ví dụ | Điều cần xem xét khi thay factory |
|---|---|---|
| Cổng và địa chỉ | `server.port`, `server.address` | Factory mới có phải kiểu configurable và nhận customizer chung không? |
| HTTPS/TLS | `server.ssl.*` | Có hỗ trợ SSL bundle/certificate và connector phù hợp không? |
| HTTP/2 | `server.http2.enabled` | Container và cách tạo connector có đáp ứng yêu cầu không? |
| Compression | `server.compression.*` | Custom factory có áp dụng thiết lập đúng hay không? |
| Session | `server.servlet.session.*` | Áp dụng đúng nếu là Servlet stack và factory hỗ trợ tương ứng |
| Context path | `server.servlet.context-path` | Áp dụng trên Servlet web server, không phải mọi reactive server |
| Forward headers | `server.forward-headers-strategy` | Kiểm tra khi đặt sau proxy/load balancer |
| Graceful shutdown | `server.shutdown`, `spring.lifecycle.timeout-per-shutdown-phase` | Kiểm tra server có lifecycle/shutdown được tích hợp đúng |
| Container-specific | `server.tomcat.*`, `server.jetty.*` | Chỉ có ý nghĩa với container tương ứng |
| Observability | Actuator, metrics, access log | Phụ thuộc server implementation, đăng ký registry và cấu hình tương ứng |

Nhiều property trên vẫn có thể hoạt động với custom factory tiêu chuẩn vì Boot giữ các auto-configured customizer. Rủi ro xuất hiện khi ứng dụng tự tạo factory **không tương thích**, tự ghi đè lại giá trị sau khi Boot xử lý, hoặc thay đổi đường tạo server để bỏ qua các extension hooks. Cách đúng là **kiểm tra chức năng tại runtime**, không kết luận dựa trên việc có hoặc không có một dòng property trong file.

Ví dụ: server khởi động thành công ở cổng mới chỉ xác minh networking cơ bản; nó **chưa chứng minh** TLS, header proxy, access log, graceful shutdown hay actuator metrics đã đúng. Các thay đổi liên quan bảo mật cần kiểm tra đường request thật và cấu hình SSL/proxy được áp dụng.

## 6. Hệ quả thứ tư: phụ thuộc phiên bản Spring Boot và server

Factory là API của Spring Boot, và tên package của lớp factory có thể thay đổi qua major version.

| Thành phần | Spring Boot 3.5 | Spring Boot 4.1 |
|---|---|---|
| Tomcat Servlet factory | `org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory` | `org.springframework.boot.tomcat.servlet.TomcatServletWebServerFactory` |
| Customizer interface | `org.springframework.boot.web.server.WebServerFactoryCustomizer` | `org.springframework.boot.web.server.WebServerFactoryCustomizer` |
| Servlet factory interface | `org.springframework.boot.web.servlet.server.ServletWebServerFactory` | `org.springframework.boot.web.server.servlet.ServletWebServerFactory` |
| Servlet/Tomcat | Tomcat 10.1 và Jakarta Servlet 6.0 | Tomcat 11.0.x và Jakarta Servlet 6.1 |

Ví dụ viết cho Boot 3.5 dùng nguyên import `TomcatServletWebServerFactory` cũ có thể không biên dịch được với Boot 4.1. Tự tạo custom factory, đặc biệt subclass override protected hook, càng làm ứng dụng phụ thuộc vào API nội bộ/thay đổi lớn của container. Khi nâng cấp major, cần đối chiếu API javadoc và dependency BOM chính xác thay vì chỉ đổi số version trong Maven/Gradle.

Với WebFlux cũng có quy tắc tương tự: `ReactiveWebServerFactory` và server factory cụ thể (Reactor Netty, Tomcat Reactive, Jetty Reactive) là các loại riêng. Cấu hình Servlet factory trong một ứng dụng REACTIVE sẽ không phải cách thay factory của WebFlux. Trong Boot 3.5, Undertow vẫn là embedded server được hỗ trợ; đến Boot 4.x danh sách chính thức chỉ còn Tomcat/Jetty và Reactor Netty cho reactive. Không nên mang code tạo Undertow factory từ 3.x lên 4.x nếu chưa xác minh phạm vi hỗ trợ.

## 7. Phương án nên dùng: property trước, customizer khi cần

Nếu chỉ muốn đổi cổng, timeout, session hoặc cấu hình được hỗ trợ, dùng property để giữ code đơn giản. Ví dụ `src/main/resources/application.properties`:

~~~properties
server.port=9090
server.compression.enabled=true
server.shutdown=graceful
~~~

Nếu cần thay đổi lập trình bằng API Tomcat, thêm **customizer bean** mà không tự khai báo factory. Ví dụ sau dành cho Spring Boot 3.5, Java 17+, Servlet stack dùng `spring-boot-starter-web`, embedded Tomcat mặc định.

Lưu tại `src/main/java/com/example/factorydemo/FactoryDemoApplication.java`:

~~~java
package com.example.factorydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FactoryDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FactoryDemoApplication.class, args);
    }
}

@RestController
class ProbeController {
    @GetMapping("/probe")
    String probe() {
        return "factory-ok";
    }
}

@Configuration(proxyBeanMethods = false)
class TomcatTuningConfiguration {
    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory> tomcatCustomizer() {
        return factory -> factory.addConnectorCustomizers(
                connector -> connector.setMaxPostSize(1_048_576));
    }
}
~~~

Giải thích ví dụ:

- `@SpringBootApplication` bật component scan và auto-configuration từ package hiện tại. Spring Boot nhận diện Servlet web application, tạo Tomcat Servlet factory.
- `@Bean` trả về một `WebServerFactoryCustomizer`, **không tạo bean ServletWebServerFactory**. Factory của Boot vẫn tồn tại.
- `addConnectorCustomizers(...)` bổ sung callback cấu hình cho Tomcat Connector; `setMaxPostSize(1_048_576)` giới hạn kích thước POST body **khi Tomcat dùng body để phân tích form parameters**. Đây không phải giới hạn chung cho mọi JSON request body; không dùng nó thay cho validation/giới hạn upload cần thiết.
- Trong dự án thực tế, nếu đã có `server.tomcat.max-http-form-post-size` đáp ứng nhu cầu thì property vẫn đơn giản hơn code.
- Cổng HTTP được ví dụ đặt bằng `server.port=9090`; callback không can thiệp vào cổng này.

Chạy trong thư mục project Maven đã có Spring Boot 3.5.x parent/BOM, starter-web và Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Trong Windows PowerShell, có thể dùng `mvnw.cmd spring-boot:run`. Gọi:

~~~bash
curl -sS http://localhost:9090/probe
~~~

Body response chính xác do controller tạo:

~~~text
factory-ok
~~~

Các dòng log startup phụ thuộc môi trường, nên không coi chúng là stdout cố định. Nếu `server.port=9090` không đặt, dùng cổng mặc định thông thường là 8080.

## 8. Phương án thay factory bean: chỉ dùng khi thật sự cần

Trong cùng một project Boot 3.5, **thay thế** `TomcatTuningConfiguration` bên trên bằng cấu hình sau để minh họa cách khai báo factory. Không chạy đồng thời hai ví dụ như hai cách cấu hình độc lập khi đang so sánh tác dụng.

~~~java
package com.example.factorydemo;

import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ManualTomcatFactoryConfiguration {
    @Bean
    ServletWebServerFactory servletWebServerFactory() {
        return new TomcatServletWebServerFactory();
    }
}
~~~

Đây là lớp cấu hình bổ sung, lưu ở file `ManualTomcatFactoryConfiguration.java` cùng package với ứng dụng ở ví dụ trước; nó không phải một chương trình Java tự chạy riêng.

Khi bean `ServletWebServerFactory` này tồn tại:

1. Spring Boot **không cần tạo factory Tomcat mặc định khác** theo nhánh auto-configuration thông thường.
2. `WebServerFactoryCustomizerBeanPostProcessor` **vẫn áp dụng** các customizer tương thích với factory `TomcatServletWebServerFactory` mà ứng dụng vừa tạo.
3. Do đó `server.port=9090`, SSL hoặc compression **có thể vẫn được áp dụng đúng** bởi những customizer của Boot. Không xem thành công của việc khai báo bean là bằng chứng rằng tất cả property bị vô hiệu hóa.
4. Ứng dụng đã nhận trách nhiệm tạo và bảo trì factory: nếu thay sang một implementation khác hoặc override hooks, cần kiểm tra lại toàn bộ cơ chế tích hợp.
5. Nếu chỉ muốn `setMaxPostSize` hoặc thêm Tomcat connector customizer, việc tự tạo factory như trên là thay đổi quá rộng; nên quay về phương án `WebServerFactoryCustomizer`.

Ví dụ không nên nhân bản factory trong cùng một context:

~~~java
// Minh họa sai về mặt thiết kế: hai bean cùng là ServletWebServerFactory.
@Bean
ServletWebServerFactory firstFactory() {
    return new TomcatServletWebServerFactory();
}

@Bean
ServletWebServerFactory secondFactory() {
    return new TomcatServletWebServerFactory();
}
~~~

Đoạn này là **trích đoạn minh họa lỗi**, không phải ứng dụng hoàn chỉnh. Servlet web application context cần tìm được một server factory phù hợp; nếu có nhiều ứng viên `ServletWebServerFactory`, quá trình khởi động có thể thất bại vì không xác định được factory duy nhất.

Một tình huống khác là ứng dụng khai báo `ServletWebServerFactory` nhưng tạo bean `NettyReactiveWebServerFactory` cho WebFlux, hoặc ngược lại. Hai stack có contract riêng; muốn đổi HTTP server hãy thay starter/dependency đúng stack và để Boot tự chọn factory, trừ khi có yêu cầu đặc biệt.

## 9. Cách xác minh thay đổi an toàn

Không nên dừng kiểm thử sau khi thấy tiến trình “Started” trong log. Kiểm tra tối thiểu:

1. **Factory duy nhất:** ApplicationContext có đúng một `ServletWebServerFactory` cho Servlet app, hoặc đúng một `ReactiveWebServerFactory` cho reactive app.
2. **Đúng loại container:** factory thực tế là Tomcat/Jetty/Netty như dự kiến. Kiểm tra dependency tree và log runtime.
3. **Property còn hiệu lực:** thử port, context path, HTTP/2, compression và TLS tùy nhu cầu thực tế; chú ý xem customizer tự viết có override property không.
4. **Đăng ký web component:** controller, `Filter`, `ServletContextInitializer` và session listener vẫn hoạt động.
5. **Vòng đời:** khởi động, shutdown, graceful shutdown và cleanup resource.
6. **Observability:** Actuator health, server metrics, access log/trace header nếu hệ thống sử dụng.
7. **Cấu hình phiên bản:** Java runtime, Boot BOM, phiên bản Tomcat/Jetty, javax/jakarta, import API đúng major.

Ví dụ JUnit Jupiter dành cho **cùng project Boot 3.5 ở mục 7**. File `src/test/java/com/example/factorydemo/FactoryRuntimeTest.java`:

~~~java
package com.example.factorydemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ApplicationContext;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FactoryRuntimeTest {
    @Autowired
    ApplicationContext context;

    @LocalServerPort
    int port;

    @Test
    void factoryAndHttpEndpointWork() throws Exception {
        Map<String, ServletWebServerFactory> factories =
                context.getBeansOfType(ServletWebServerFactory.class);
        assertEquals(1, factories.size());
        assertInstanceOf(TomcatServletWebServerFactory.class,
                factories.values().iterator().next());
        assertTrue(port > 0);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port + "/probe"))
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("factory-ok", response.body());
    }
}
~~~

Để chạy test, dự án cần `spring-boot-starter-test` và JUnit Jupiter theo Boot BOM:

~~~bash
./mvnw test
~~~

`RANDOM_PORT` cấp cổng thực tế cho test; kiểm tra `@LocalServerPort` đáng tin hơn giả định app đang nghe 9090. Với môi trường cấu hình context path khác rỗng, đường URL test phải thêm context path phù hợp. Khi test các tính năng SSL/TLS, compression hoặc filter, cần có test riêng gửi request có đủ điều kiện cần thiết.

Nếu muốn tìm nguyên nhân Boot không còn tự tạo factory mặc định, dùng `debug=true` hoặc chạy ứng dụng với `--debug` để xem Condition Evaluation Report; tìm các auto-configuration liên quan `ServletWebServerFactory`/`ReactiveWebServerFactory` và lý do condition matched hoặc did not match. Có thể tra thông tin qua Actuator conditions khi endpoint được bật và cấp quyền phù hợp. Không dựa vào một chuỗi log duy nhất vì tên class và thông điệp thay đổi theo Boot version.

## 10. Những hiểu nhầm thường gặp

- **“Tạo bean factory riêng làm Boot ngừng chạy mọi customizer.”** Sai. Tài liệu Spring Boot nói các auto-configured customizer vẫn áp dụng cho custom factory. Cần phân biệt *factory auto-configuration back off* với *customizer mechanism*.
- **“Chỉ cần new TomcatServletWebServerFactory là tương đương mọi mặt với factory mặc định.”** Không được giả định. Nếu ứng dụng chuyển implementation, thêm subclass/hook hoặc thay thứ tự, hành vi có thể khác; phải kiểm thử theo cấu hình thực tế.
- **“Dùng một `@Bean` khác tên thì Boot vẫn tạo thêm factory mặc định.”** Điều kiện thường dựa trên **kiểu bean** chứ không chỉ tên; cung cấp `ServletWebServerFactory` phù hợp có thể khiến factory mặc định nhường chỗ.
- **“Đặt `server.port` là giá trị cuối cùng trong mọi trường hợp.”** Không chắc. Customizer có order chạy sau có thể đổi port; kiểm tra actual listener.
- **“Customizer typed Tomcat sẽ chạy trên Jetty.”** Sai. Generic type và concrete factory quyết định callback có được áp dụng.
- **“Tạo nhiều factory để Boot chọn ngẫu nhiên.”** Sai. Web application context cần một factory phù hợp, nhiều ứng viên có thể làm khởi động thất bại.
- **“Mất metrics/TLS là hậu quả chắc chắn khi khai báo custom factory.”** Không chính xác. Với implementation chuẩn và auto customizers phù hợp, các tính năng này có thể tiếp tục hoạt động. Cần test thay vì suy luận.
- **“WebServerFactoryCustomizer tương đương WebMvcConfigurer.”** Sai. `WebServerFactoryCustomizer` cấu hình embedded HTTP server; `WebMvcConfigurer` cấu hình Spring MVC, ví dụ interceptor, formatter và CORS mapping. Hai cơ chế mở rộng khác tầng.
- **“Cùng một class Tomcat factory dùng được nguyên import ở Boot 3 và 4.”** Sai. Package thay đổi theo major version; API phụ thuộc BOM cụ thể.

## 11. Quy trình quyết định và rà soát PR

Để tùy biến embedded server, thực hiện theo thứ tự:

1. **Viết rõ yêu cầu:** thay port, TLS, connector, thread pool, graceful shutdown, lifecycle hay factory implementation?
2. **Thử property:** tìm `server.*` và property riêng của container trước.
3. **Dùng customizer nếu cần code:** chọn generic theo đúng factory, ưu tiên API `add...`, tránh phụ thuộc bean nghiệp vụ khởi tạo sớm và kiểm soát order.
4. **Chỉ tạo factory bean khi cần thay cách tạo server:** chứng minh vì sao property và customizer không đủ; xác minh single factory, contract, classpath và loại web app.
5. **Kiểm thử hành vi đầy đủ:** HTTP, TLS, proxy, request body, filter/session, logging, metrics và startup/shutdown phù hợp với phạm vi thay đổi.
6. **Rà soát khi nâng Boot:** kiểm tra package, javadoc, supported server, Java/Servlet API và BOM.

Một PR thay factory nên mô tả cụ thể những gì factory cũ không hỗ trợ, những customizer nào vẫn chạy, bộ test xác nhận không mất behavior và cách rollback. Nếu chỉ có một tham số Tomcat cần bổ sung, `WebServerFactoryCustomizer` là phương án dễ kiểm soát và bảo trì hơn.

## Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Embedded Web Servers, Configure the Web Server: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 4.1 — Embedded Web Servers: https://docs.spring.io/spring-boot/how-to/webserver.html
- Spring Boot 3.5 — Servlet Web Applications, Programmatic Customization: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 4.1 — Servlet Web Applications: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot 4.1 — `WebServerFactoryCustomizer` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/server/WebServerFactoryCustomizer.html
- Spring Boot 3.5 — `TomcatServletWebServerFactory` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/embedded/tomcat/TomcatServletWebServerFactory.html
- Spring Boot 4.1 — `TomcatServletWebServerFactory` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/tomcat/servlet/TomcatServletWebServerFactory.html

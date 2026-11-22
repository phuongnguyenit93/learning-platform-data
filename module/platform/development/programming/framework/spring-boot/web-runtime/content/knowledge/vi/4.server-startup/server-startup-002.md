# Vai trò của cấu hình tự động trong tạo `WebServerFactory` (Spring Boot 3.3.x)

## 1. Vấn đề cần hiểu khi khởi động máy chủ

Trong ứng dụng Spring Boot dạng web, lập trình viên thường chỉ khai báo `spring-boot-starter-web` hoặc `spring-boot-starter-webflux`, viết lớp có `@SpringBootApplication` rồi gọi `SpringApplication.run(...)`. Máy chủ HTTP vẫn được tạo và khởi động dù ứng dụng không tự viết mã `new Tomcat()`, `new Jetty()` hay `new Netty()`.

Phần kết nối hai phía chính là **auto-configuration**: Spring Boot dựa trên loại ứng dụng web, thư viện có trên classpath, các bean đã tồn tại và thuộc tính cấu hình để đăng ký **một bean `WebServerFactory` thích hợp**. Sau đó **web application context** sử dụng factory ấy để tạo và quản lý **đối tượng `WebServer` thực tế**.

Cần phân biệt ba thành phần:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Auto-configuration | Quyết định có đăng ký factory bean nào và cung cấp các customizer liên quan hay không | `ServletWebServerFactoryAutoConfiguration`, `ReactiveWebServerFactoryAutoConfiguration` |
| `WebServerFactory` | Giữ cấu hình cần thiết và **tạo** máy chủ theo yêu cầu của context | `TomcatServletWebServerFactory`, `NettyReactiveWebServerFactory` |
| `WebServer` | Đại diện cho máy chủ đã được tạo, có vòng đời `start()`/`stop()` và cổng đang sử dụng | Adapter máy chủ nhúng do factory trả về |

**Factory không phải chính máy chủ đang lắng nghe cổng.** Có bean factory chưa đồng nghĩa máy chủ đã mở socket; bước tạo và khởi động còn nằm trong vòng đời refresh/start của application context.

## 2. Chuỗi khởi động: ai tạo factory và ai dùng nó?

Với ứng dụng web nhúng thông thường, luồng khái niệm là:

```text
SpringApplication.run(...)
    |
    +--> Suy ra WebApplicationType (SERVLET / REACTIVE / NONE)
    |
    +--> Tạo loại ApplicationContext tương ứng
    |
    +--> Đọc cấu hình ứng dụng và xử lý auto-configuration
    |      |
    |      +--> Kiểm tra điều kiện (classpath, web type, bean hiện có)
    |      +--> Đăng ký ServletWebServerFactory hoặc ReactiveWebServerFactory
    |      +--> Bind server.* và áp dụng WebServerFactoryCustomizer
    |
    +--> Context refresh: tìm factory phù hợp
    |      |
    |      +--> factory.getWebServer(...) tạo WebServer nhúng
    |      +--> Gắn handler/ServletContextInitializer tương ứng
    |
    +--> Hoàn tất vòng đời khởi động máy chủ
           |
           +--> Máy chủ bắt đầu nhận HTTP request
           +--> Phát sự kiện WebServerInitializedEvent phù hợp
```

Đây là **luồng trách nhiệm**, không phải một danh sách phương thức Java được gọi liên tục theo đúng tên như trên.

Các mốc quan trọng:

1. `@SpringBootApplication` bao gồm khả năng bật auto-configuration. Spring Boot nạp danh sách lớp auto-configuration do framework cung cấp và đánh giá điều kiện của chúng.
2. `SpringApplication` chọn web application type; loại context thích hợp được tạo, ví dụ `AnnotationConfigServletWebServerApplicationContext` hoặc `AnnotationConfigReactiveWebServerApplicationContext`.
3. Trong lúc refresh context, các bean definition auto-configuration và bean customizer được xử lý. Factory cần có trước khi context sử dụng nó để tạo máy chủ.
4. Với Servlet, `ServletWebServerApplicationContext` tìm **một** `ServletWebServerFactory`, gọi `getWebServer(...)` cùng các `ServletContextInitializer`. Với Reactive, `ReactiveWebServerApplicationContext` dùng `ReactiveWebServerFactory` cùng `HttpHandler`.
5. Context quản lý vòng đời máy chủ; việc server sẵn sàng được thông báo qua `ServletWebServerInitializedEvent` hoặc `ReactiveWebServerInitializedEvent` (đều thuộc họ `WebServerInitializedEvent`).

**Điểm then chốt:** auto-configuration chủ yếu **đăng ký và tùy biến factory bean**; application context mới là nơi **yêu cầu factory tạo `WebServer`** và điều phối vòng đời nó. Không nên quy toàn bộ việc khởi động máy chủ cho một lớp auto-configuration.

## 3. Spring Boot quyết định Servlet hay Reactive như thế nào?

| Loại ứng dụng | Tình huống thông thường | Context | Kiểu factory cần tìm |
| --- | --- | --- | --- |
| `SERVLET` | Có Spring MVC/Servlet stack, thường từ `spring-boot-starter-web` | `ServletWebServerApplicationContext` | `ServletWebServerFactory` |
| `REACTIVE` | Có WebFlux mà không có Spring MVC, thường từ `spring-boot-starter-webflux` | `ReactiveWebServerApplicationContext` | `ReactiveWebServerFactory` |
| `NONE` | Không phải ứng dụng web hoặc chủ động chọn chế độ không web | Context thông thường | Không cần factory máy chủ HTTP nhúng |

Nếu cùng có Spring MVC và WebFlux trên classpath, Spring Boot thường chọn **SERVLET** theo cách suy luận mặc định. Không thể chỉ nhìn thấy Reactor Netty trong dependencies rồi kết luận ứng dụng đang chạy theo mô hình Reactive.

Có thể chủ động cấu hình:

```properties
# Không tạo web application context và không chạy HTTP server nhúng
spring.main.web-application-type=none
```

Thiết lập này khác với `server.port=-1`: giá trị `-1` ngừng mở HTTP endpoint nhưng vẫn cho phép tạo web application context trong trường hợp cần thiết. `server.port=0` lại yêu cầu chọn một cổng còn trống; nó không vô hiệu hóa máy chủ.

## 4. Nhánh Servlet: `ServletWebServerFactoryAutoConfiguration`

Ở Spring Boot 3.3.x, lớp auto-configuration chính nằm trong package:

```java
org.springframework.boot.autoconfigure.web.servlet.ServletWebServerFactoryAutoConfiguration
```

Các điều kiện và cơ chế quan trọng:

- `@ConditionalOnWebApplication(type = SERVLET)`: chỉ áp dụng cho ứng dụng Servlet.
- `@ConditionalOnClass(jakarta.servlet.ServletRequest.class)`: chỉ áp dụng khi API Servlet cần thiết tồn tại trên classpath.
- `@EnableConfigurationProperties(ServerProperties.class)`: bật binding cấu hình máy chủ từ `server.*`.
- Import các cấu hình máy chủ nhúng Tomcat, Jetty, Undertow; cấu hình con sử dụng điều kiện trên classpath và **back off khi đã có `ServletWebServerFactory` phù hợp**.
- Đăng ký infrastructure để các `WebServerFactoryCustomizer` được áp dụng cho factory, cùng các customizer mặc định của Spring Boot.

Với dependencies mặc định của `spring-boot-starter-web`:

```text
spring-boot-starter-web
    -> spring-boot-starter-tomcat
       -> thư viện Tomcat/Servlet cần thiết
    -> điều kiện Servlet + Tomcat khớp
    -> bean TomcatServletWebServerFactory
    -> ServletWebServerApplicationContext sử dụng bean
    -> WebServer nhúng dựa trên Tomcat
```

Nếu thay Tomcat bằng Jetty hoặc Undertow đúng cách trong dependency graph, factory tương ứng có thể được tạo mà không cần viết lại logic khởi động của ứng dụng.

Ví dụ kiểu factory thông dụng:

| Container trên classpath | Factory nhánh Servlet |
| --- | --- |
| Tomcat | `TomcatServletWebServerFactory` |
| Jetty | `JettyServletWebServerFactory` |
| Undertow | `UndertowServletWebServerFactory` |

**Không nhầm `DispatcherServlet` với `ServletWebServerFactory`.** `DispatcherServlet` xử lý định tuyến request trong Spring MVC; factory tạo container HTTP và liên quan đến cổng, connector, context path, SSL, v.v. Spring MVC auto-configuration và web-server-factory auto-configuration là hai phần phối hợp nhưng khác trách nhiệm.

## 5. Nhánh Reactive: `ReactiveWebServerFactoryAutoConfiguration`

Ở Spring Boot 3.3.x, lớp tương ứng là:

```java
org.springframework.boot.autoconfigure.web.reactive.ReactiveWebServerFactoryAutoConfiguration
```

Lớp này chỉ áp dụng khi `@ConditionalOnWebApplication(type = REACTIVE)` và các API Reactive cần thiết có mặt, đồng thời cung cấp `ServerProperties`, customizer và các cấu hình máy chủ nhúng phù hợp.

`spring-boot-starter-webflux` mặc định đem theo Reactor Netty. Khi đó đường đi phổ biến là:

```text
spring-boot-starter-webflux
    -> spring-boot-starter-reactor-netty
    -> ReactiveWebServerFactoryAutoConfiguration
    -> NettyReactiveWebServerFactory
    -> ReactiveWebServerApplicationContext
    -> WebServer phục vụ HttpHandler của WebFlux
```

Nhánh Reactive cũng có các factory tương ứng khi dùng Tomcat, Jetty hoặc Undertow thay cho Reactor Netty:

| Container | Factory nhánh Reactive |
| --- | --- |
| Reactor Netty | `NettyReactiveWebServerFactory` |
| Tomcat | `TomcatReactiveWebServerFactory` |
| Jetty | `JettyReactiveWebServerFactory` |
| Undertow | `UndertowReactiveWebServerFactory` |

`ReactiveWebServerFactory` không phải một dạng `ServletWebServerFactory`. Đặt factory thuộc stack khác vào context hiện tại không giải quyết được yêu cầu bean của context đó. Tương tự, dùng WebFlux **không đồng nghĩa** server luôn là Netty; cần xem cả dependencies và web application type.

## 6. Cơ chế điều kiện và nguyên tắc “back off”

Auto-configuration mang tính **có điều kiện**, không cưỡng ép mọi ứng dụng dùng Tomcat.

Giả sử ứng dụng đã có bean `ServletWebServerFactory` do người viết cung cấp. Cấu hình nhà cung cấp factory mặc định của Boot sẽ **nhường chỗ** theo nguyên tắc `@ConditionalOnMissingBean`, thay vì cố tạo thêm một bean mặc định cùng vai trò. Các customizer của Boot vẫn có thể tác động lên custom factory đó.

Ba lớp quyết định cần phân biệt:

1. **Web application type:** context hiện tại cần Servlet factory, Reactive factory hay không cần factory?
2. **Classpath:** thư viện máy chủ nào có mặt để cấu hình tương ứng đủ điều kiện hoạt động?
3. **Bean registry:** đã có bean factory do ứng dụng hoặc thư viện khác định nghĩa chưa, có một factory phù hợp duy nhất không?

Ví dụ tình huống:

| Tình huống | Kết quả dự kiến |
| --- | --- |
| `starter-web` với Tomcat mặc định; không khai báo factory riêng | Boot cung cấp `TomcatServletWebServerFactory` |
| `starter-web` thay Tomcat bằng Jetty hợp lệ | Boot cung cấp factory Jetty |
| `starter-webflux` với Reactor Netty và loại web là Reactive | Boot cung cấp `NettyReactiveWebServerFactory` |
| Khai báo một Servlet factory bean riêng trong ứng dụng Servlet | Cấu hình factory mặc định nhường chỗ; context sử dụng bean được cung cấp |
| Bắt buộc `web-application-type=none` | Không cần tạo máy chủ web nhúng |
| Dùng context Servlet nhưng thiếu tất cả Servlet web-server factory thích hợp | Khởi động có thể thất bại do thiếu bean factory cần thiết |
| Có nhiều factory cùng loại được đăng ký trái kỳ vọng | Context không thể lựa chọn một factory duy nhất và khởi động có thể thất bại |

`@ConditionalOnMissingBean` không có nghĩa “Spring Boot luôn sửa được mọi dependency xung đột”. Nếu thêm đồng thời nhiều container hoặc tự đăng ký nhiều bean cùng vai trò, phải kiểm tra thực tế các condition match và kết quả bean registry.

## 7. `ServerProperties` và customizer tác động vào factory khi nào?

Cấu hình từ `application.properties`, `application.yml`, biến môi trường hoặc command-line arguments được hợp nhất trong `Environment`. Boot bind nhóm thuộc tính `server.*` vào `ServerProperties` và dùng các `WebServerFactoryCustomizer` để áp dụng cấu hình chung/riêng lên factory **trước khi factory được dùng để tạo server**.

Ví dụ cho ứng dụng Spring MVC:

```yaml
# src/main/resources/application.yml
server:
  port: 9090
  servlet:
    context-path: /api
```

Khi đó đường dẫn controller `@GetMapping("/ping")` được truy cập qua `http://localhost:9090/api/ping`. `server.servlet.context-path` thuộc Servlet; không áp dụng máy móc nó cho WebFlux chạy Netty.

Các cách cấu hình theo mức ưu tiên sử dụng:

1. Dùng `server.*` cho nhu cầu thường gặp: cổng, địa chỉ bind, SSL, nén HTTP, các cấu hình riêng như `server.tomcat.*`.
2. Thêm `WebServerFactoryCustomizer<T>` khi cần thay đổi factory bằng Java, đặc biệt tùy chọn mà `server.*` chưa biểu đạt được.
3. Cung cấp factory bean riêng khi cần thay thế cách tạo máy chủ ở mức sâu hơn. Cách này làm tăng trách nhiệm duy trì cấu hình và tương tác với customizer mặc định.

`WebServerFactoryCustomizerBeanPostProcessor` là cơ chế áp dụng customizer lên factory bean khi bean được khởi tạo. Vì vậy customizer không đơn thuần là đoạn code chạy sau khi HTTP server đã nhận request.

## 8. Bài thực hành: quan sát factory do Boot tạo

Ví dụ dưới đây dùng **Java 21 và Spring Boot 3.3.13** (phù hợp Java 17+). Đây là ứng dụng độc lập có thể chạy với Gradle Wrapper, không cần tự khai báo factory.

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

**`src/main/java/com/example/demo/WebRuntimeApplication.java`**

```java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class WebRuntimeApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @Bean
    ApplicationRunner inspectWebServerFactory(ApplicationContext context) {
        return args -> {
            Map<String, ServletWebServerFactory> factories =
                    context.getBeansOfType(ServletWebServerFactory.class);

            System.out.println("Factory count: " + factories.size());
            factories.values().forEach(factory ->
                    System.out.println("Factory: "
                            + factory.getClass().getSimpleName()));

            int actualPort =
                    ((WebServerApplicationContext) context).getWebServer().getPort();
            System.out.println("Port: " + actualPort);
        };
    }
}
```

**`src/main/resources/application.properties`**

```properties
server.port=9090
server.servlet.context-path=/api
```

**Chạy và gọi HTTP** (tại thư mục dự án có Gradle Wrapper):

```bash
./gradlew bootRun
```

Trong những dòng log khác của Spring Boot, chương trình tự in các dòng sau khi khởi động với dependency Tomcat mặc định và cổng 9090 không bị chiếm:

```text
Factory count: 1
Factory: TomcatServletWebServerFactory
Port: 9090
```

Ở một terminal khác:

```bash
curl -s http://localhost:9090/api/ping
```

Nội dung response body chính xác là `pong` (không có ký tự xuống dòng do endpoint trả về chuỗi `"pong"`).

**Giải thích kết quả:** `starter-web` cung cấp các thư viện Servlet/Tomcat; auto-configuration đăng ký một `TomcatServletWebServerFactory`; context dùng factory tạo Tomcat nhúng; `ApplicationRunner` chạy khi context đã khởi động nên đọc được loại factory và cổng thực tế. Lệnh `curl` kiểm chứng máy chủ đang phục vụ request.

Lưu ý: `Factory count: 1` là kết quả của cấu hình ví dụ này, không phải cam kết rằng mọi ứng dụng đều chỉ có một bean factory trong mọi trường hợp. Để xác định port khi dùng `server.port=0`, hãy đọc `WebServer.getPort()` sau khi server khởi động hoặc lắng nghe `WebServerInitializedEvent`, không suy từ giá trị cấu hình bằng 0.

### Thực hành thay đổi factory mà không tự thay thế factory bean

Thêm lớp sau vào cùng package `com.example.demo`:

**`src/main/java/com/example/demo/ServerTuning.java`**

```java
package com.example.demo;

import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.servlet.server.ConfigurableServletWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ServerTuning {

    @Bean
    WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>
            useAnotherPort() {
        return factory -> factory.setPort(9191);
    }
}
```

Vì customizer mặc định của Boot thường chạy trước customizer tự khai báo không đặt order, ví dụ này ghi đè cổng 9090 trong `application.properties`; sau khi khởi động lại, `Port: 9191` và endpoint ở `http://localhost:9191/api/ping`. Đừng sao chép việc đặt cổng cố định theo hai nơi vào dự án thật nếu không có lý do: chỉ dùng property thường dễ bảo trì hơn.

Nếu cần chủ động điều khiển thứ tự giữa nhiều customizer, dùng `@Order`/`Ordered` có chủ đích và kiểm tra tác động cuối cùng. Auto-configured customizers có order `0`; thứ tự customizer do người dùng tạo phụ thuộc cấu hình order thực tế.

## 9. Thay container vẫn giữ cùng mô hình khởi động

Ví dụ với Gradle, thay mặc định Tomcat trong Servlet stack bằng Jetty:

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
```

Sau khi refresh dependencies và khởi động lại, factory mong đợi là `JettyServletWebServerFactory`. Không cần sửa controller, `SpringApplication.run(...)` hoặc tự gọi `factory.getWebServer(...)`: auto-configuration làm công việc lựa chọn factory và Servlet context vẫn điều phối lifecycle.

Phải loại bỏ container không dùng khỏi dependency graph một cách nhất quán; chỉ thêm starter Jetty mà giữ Tomcat là cách dễ tạo classpath khó hiểu. Phiên bản container được quản lý qua dependency management tương thích với phiên bản Spring Boot.

## 10. Chẩn đoán khi máy chủ không được tạo hoặc không khởi động

Nên kiểm tra theo thứ tự **loại ứng dụng → thư viện → condition → bean factory → cấu hình cổng → lỗi của server**.

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Ứng dụng chạy như chương trình console, không mở HTTP port | `WebApplicationType.NONE` hoặc thiếu web starter | Kiểm tra `spring.main.web-application-type`, `starter-web`/`starter-webflux` và dependency tree |
| Servlet context báo thiếu `ServletWebServerFactory` | Không có container nhúng phù hợp; loại bỏ Tomcat nhưng chưa thêm Jetty/Undertow; auto-config bị exclude | Kiểm tra classpath và condition report; bổ sung container hợp lệ hoặc xem lại exclude |
| WebFlux context báo thiếu `ReactiveWebServerFactory` | Thiếu reactor-netty hoặc reactive container tương thích | Kiểm tra reactive starter, dependencies và web application type |
| Context báo nhiều factory hoặc không chọn được factory duy nhất | Tự đăng ký nhiều factory bean hoặc thư viện bổ sung factory không dự kiến | Liệt kê các bean thuộc interface tương ứng; giữ đúng một factory có thể sử dụng |
| Có factory nhưng khởi động HTTP thất bại | Cổng đang bị chiếm, quyền bind, SSL/connector cấu hình sai | Đọc root cause (`BindException`, lỗi SSL...) và giá trị port/address thực tế |
| Chỉnh `server.port` mà ứng dụng vẫn dùng cổng khác | Profile/env/CLI ưu tiên cao hơn hoặc customizer can thiệp | Kiểm tra cấu hình hiệu lực và `WebServerFactoryCustomizer` |
| Thêm WebFlux nhưng ứng dụng vẫn chạy Servlet | Có Spring MVC trên classpath nên Boot mặc định chọn Servlet | Kiểm tra dependency tree và WebApplicationType, chọn stack có chủ đích |

Cách bật báo cáo điều kiện trong môi trường phát triển:

```bash
./gradlew bootRun --args='--debug'
```

Trong `CONDITIONS EVALUATION REPORT`, tìm `ServletWebServerFactoryAutoConfiguration` hoặc `ReactiveWebServerFactoryAutoConfiguration` ở phần positive/negative matches. Quan sát **vì sao điều kiện khớp hoặc không khớp**, không chỉ nhìn tên container xuất hiện trong log. Có thể dùng Actuator `/actuator/conditions` khi đã cài và chủ động expose endpoint cho môi trường phù hợp.

Khi viết test, lưu ý `@SpringBootTest(webEnvironment = RANDOM_PORT)` thường tạo máy chủ thật trên cổng ngẫu nhiên, còn các test dạng mock web context không đồng nghĩa mở socket. Việc tồn tại bean controller hay test HTTP mock không tự chứng minh factory đã tạo server thật.

## 11. Các hiểu nhầm cần tránh

1. **“`@SpringBootApplication` trực tiếp khởi tạo Tomcat.”** Không chính xác: annotation kích hoạt cơ chế cấu hình; factory được đăng ký theo điều kiện, context sử dụng factory để tạo server.
2. **“`WebServerFactory` và `WebServer` là một.”** Factory là công cụ tạo/cấu hình; `WebServer` là đối tượng được tạo và quản lý vòng đời.
3. **“Cứ thêm WebFlux là dùng Netty.”** Sai nếu có Spring MVC và Boot chọn Servlet, hoặc nếu reactive stack thay container.
4. **“Khai báo `server.port` là tạo bean factory.”** Property chỉ cung cấp dữ liệu cấu hình; factory còn cần auto-configuration/bean definition thỏa điều kiện.
5. **“Tự khai báo factory thì Boot không còn tham gia cấu hình.”** Các factory mặc định có thể nhường chỗ, nhưng auto-configured customizers vẫn có thể áp dụng lên bean do người dùng cung cấp.
6. **“`@EnableWebMvc` là điều kiện để chạy embedded Tomcat.”** Không phải. `@EnableWebMvc` thay đổi cách cấu hình Spring MVC; trách nhiệm tạo embedded server thuộc cấu hình web-server factory và application context.
7. **“Context refresh xong là mọi cổng chắc chắn sử dụng được.”** Khởi động có thể thất bại do bind port hoặc cấu hình server; phải quan sát sự kiện khởi tạo thành công, log và lỗi gốc.

## 12. Tự kiểm tra kiến thức

- Nếu loại bỏ `spring-boot-starter-tomcat` nhưng không thêm server tương đương, nhánh auto-configuration Servlet cần bean nào và vì sao khởi động có thể lỗi?
- Tại sao một `TomcatServletWebServerFactory` bean có thể đã tồn tại trước khi `WebServer` bắt đầu nhận HTTP request?
- Thay `server.port=8080` bằng `server.port=0` tác động đến customizer và giá trị cổng thực tế như thế nào?
- Vì sao `WebServerFactoryCustomizer` thường là lựa chọn tốt hơn việc viết một factory bean mới chỉ để đổi port?
- Với cả `starter-web` và `starter-webflux`, bạn sẽ kiểm tra gì trước khi kết luận factory nào được dùng?

**Kiến thức cốt lõi:** auto-configuration đảm bảo ứng dụng web nhận được factory thích hợp theo điều kiện và áp dụng cấu hình; **web application context** dùng factory đó để tạo, khởi động và quản lý máy chủ nhúng. Chỉ cần phân biệt rõ *chọn factory*, *tùy biến factory* và *vận hành server* là có thể lần theo hầu hết lỗi ở giai đoạn khởi động HTTP.

### Tài liệu tham khảo (API và hướng dẫn Spring Boot 3.3)

- Servlet web applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Embedded web servers: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Servlet factory auto-configuration API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/ServletWebServerFactoryAutoConfiguration.html
- Reactive factory auto-configuration API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/ReactiveWebServerFactoryAutoConfiguration.html
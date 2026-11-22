# Phân biệt cấu hình Spring Framework với tự cấu hình Spring Boot trong WebFlux

## 1. Hai lớp cấu hình giải quyết hai việc khác nhau

**Spring WebFlux là một phần của Spring Framework.** Framework cung cấp mô hình lập trình reactive, các thành phần xử lý HTTP, controller annotation, functional endpoint, codec, handler mapping và API cấu hình. Để những thành phần đó hoạt động, ứng dụng cần một cách khởi tạo và lắp ráp chúng.

**Spring Boot bổ sung cơ chế auto-configuration**: dựa trên dependency, loại ứng dụng, các bean đã khai báo và properties để tự tạo nhiều thành phần cần thiết. Boot còn tích hợp server nhúng, cấu hình mặc định, quản lý properties và các tiện ích vận hành.

Vì thế, khi nói “cấu hình WebFlux bằng Spring Framework” thường đang nói đến việc **chủ động bật và tùy biến hạ tầng WebFlux**. Khi nói “Spring Boot auto-configure WebFlux” là nói Boot **tự kích hoạt và kết hợp hạ tầng Framework cùng các tích hợp của Boot**.

Có thể nhìn theo hai lớp:

~~~text
Ứng dụng (Controller / RouterFunction / Service)
                    |
                    v
        Spring WebFlux (Framework)
  HandlerMapping, HandlerAdapter, codecs,
  exception handling, WebFilter, HttpHandler...
                    |
                    v
        HTTP server runtime
  Reactor Netty / Tomcat / Jetty ...
                    |
                    v
          Network / HTTP clients

Spring Boot bổ sung:
  - nhận diện reactive web application và classpath
  - tự cấu hình WebFlux infrastructure
  - server nhúng và server properties
  - codec, static resources, WebJars, error defaults
  - điều kiện để lùi khi ứng dụng tự cung cấp cấu hình
~~~

**Spring Boot không thay thế Spring WebFlux.** Boot gọi và cấu hình các thành phần của Framework, giúp ứng dụng bắt đầu nhanh hơn. Một ứng dụng Framework thuần vẫn có thể dùng WebFlux, nhưng người phát triển phải tự quản lý nhiều bước khởi tạo hơn.

## 2. Cấu hình WebFlux ở cấp Spring Framework

Ở cấp Framework, Java configuration có thể dùng `@EnableWebFlux`:

~~~java
@Configuration
@EnableWebFlux
public class WebConfig {
}
~~~

`@EnableWebFlux` nhập cấu hình `DelegatingWebFluxConfiguration`, dựa trên `WebFluxConfigurationSupport`. Cấu hình này đăng ký các thành phần hạ tầng cần thiết để xử lý controller có annotation và functional endpoint, đồng thời cung cấp các mặc định phù hợp với dependency có trên classpath (ví dụ JSON codec khi có thư viện tương ứng).

Sau khi bật hạ tầng, có thể triển khai `WebFluxConfigurer` để tùy biến:

~~~java
@Configuration
@EnableWebFlux
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                  .maxInMemorySize(512 * 1024);
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedMethods("GET", "POST");
    }
}
~~~

Ví dụ đặt giới hạn bộ nhớ cho HTTP message codecs ở 512 KiB và khai báo CORS cho đường dẫn `/api/**`. Đây là **mẫu cấu hình Framework**; cần các import `org.springframework.context.annotation.*`, `org.springframework.web.reactive.config.*` và `org.springframework.http.codec.ServerCodecConfigurer`.

### WebFluxConfigurer làm gì?

`WebFluxConfigurer` là một tập callback để bổ sung cấu hình cho hạ tầng WebFlux. Các điểm tùy biến thường gặp:

| Callback | Mục đích |
| --- | --- |
| `configureHttpMessageCodecs` | Thêm, điều chỉnh hoặc thay thế reader/writer cho JSON, text, binary và các media type |
| `addFormatters` | Đăng ký converter và formatter cho dữ liệu request |
| `configureContentTypeResolver` | Điều chỉnh cách xác định media type theo `Accept` hoặc chiến lược khác |
| `addCorsMappings` | Cấu hình CORS toàn cục theo URL |
| `configureViewResolvers` | Khai báo view resolver cho ứng dụng trả HTML/template |
| `configurePathMatching` | Điều chỉnh quy tắc khớp đường dẫn |
| `configureArgumentResolvers` | Đăng ký resolver cho tham số controller trong các trường hợp cần thiết |
| `configureBlockingExecution` | Cấu hình executor cho controller method được xem là blocking ở phiên bản Framework hỗ trợ API này |
| `getValidator` | Chọn validator dùng chung cho WebFlux |

Không phải ứng dụng nào cũng cần override tất cả callback. Nên chỉ cấu hình phần có yêu cầu cụ thể để giữ các mặc định Framework hữu ích.

### Nếu không dùng Spring Boot thì còn cần gì?

`@EnableWebFlux` bật hạ tầng Spring WebFlux, nhưng **không tự cung cấp toàn bộ server runtime và bootstrap của một ứng dụng chạy độc lập**. Ứng dụng Framework thuần cần:

1. Các dependency Spring cần thiết như `spring-webflux`, `spring-context` và Reactor.
2. Một HTTP server tương thích, ví dụ Reactor Netty, Tomcat reactive hoặc Jetty reactive, cùng dependency tương ứng.
3. Một Spring `ApplicationContext` để đăng ký controller, router và cấu hình.
4. Cách nối `HttpHandler` của WebFlux với server runtime và quản lý lifecycle start/stop của server.

Ví dụ cấu hình Framework thuần:

~~~java
package com.example.web;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
@EnableWebFlux
@ComponentScan(basePackages = "com.example.web")
public class FrameworkWebFluxConfig implements WebFluxConfigurer {
}
~~~

Đây là **class cấu hình**, không phải chương trình server chạy độc lập. Nó bật infrastructure và scan controller; phần bootstrap HTTP server vẫn phải được ứng dụng tự lắp ráp hoặc cung cấp bởi một nền tảng khác. Khi dùng Framework trực tiếp, bạn chịu trách nhiệm rõ hơn về dependency server, cổng lắng nghe, cấu hình TLS, lifecycle và tích hợp runtime.

## 3. Spring Boot auto-configuration làm gì?

Trong ứng dụng Boot, dependency thường dùng là `spring-boot-starter-webflux`. Starter kéo theo các thành phần cần thiết cho WebFlux và mặc định cung cấp Reactor Netty làm reactive embedded server. Boot cũng hỗ trợ các server reactive khác như Tomcat và Jetty khi thay dependency phù hợp.

Một ứng dụng Boot điển hình:

~~~java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` bao gồm khả năng component scan và bật auto-configuration. Khi classpath và loại ứng dụng phù hợp, Boot tự cấu hình WebFlux. Thông thường không cần tự khai báo `@EnableWebFlux`.

Auto-configuration WebFlux được áp dụng theo điều kiện, ví dụ:

- Ứng dụng được nhận diện là **reactive web application**.
- Các class WebFlux cần thiết có trên classpath.
- Chưa có cấu hình WebFlux nền tảng do ứng dụng tự cung cấp.

Cơ chế điều kiện giúp Boot tránh đăng ký lại hạ tầng khi người phát triển đã tự cấu hình. Tên class và package nội bộ có thể thay đổi theo major version Boot; điều cần hiểu là nguyên tắc **conditional auto-configuration**.

### Boot bổ sung những gì?

Spring Boot cung cấp thêm nhiều tích hợp trên mặc định của Framework:

- **Codec properties và customizers:** cấu hình HTTP reader/writer, giới hạn bộ nhớ, JSON/Jackson và các codec theo properties hoặc bean tùy biến.
- **Static resources:** tự phục vụ nội dung trong các thư mục classpath như `/static`, `/public`, `/resources`, `/META-INF/resources` theo cấu hình.
- **WebJars và welcome page:** hỗ trợ tài nguyên WebJars và trang chào mặc định.
- **Embedded reactive server:** tự tạo server và cấu hình cổng, SSL, compression cùng các thuộc tính server phổ biến.
- **Error handling:** cung cấp xử lý lỗi mặc định cho HTTP response; ứng dụng có thể bổ sung `ErrorAttributes`, `ErrorWebExceptionHandler` hoặc các cơ chế phù hợp khác.
- **Properties và tích hợp hệ sinh thái:** gắn cấu hình WebFlux với `application.properties`/`application.yaml`, logging, metrics, actuator và các auto-configuration liên quan.

Ví dụ, thay vì tự tạo server và tự cấu hình cổng, có thể đặt:

~~~properties
server.port=8081
spring.webflux.static-path-pattern=/assets/**
spring.http.codecs.max-in-memory-size=512KB
~~~

Tên property và cách hỗ trợ có thể khác giữa các phiên bản Boot. Hãy tra tài liệu đúng version của dự án trước khi sử dụng property mới.

## 4. Quan hệ giữa @EnableWebFlux và WebFluxConfigurer trong Spring Boot

Đây là điểm quan trọng nhất khi chuyển từ cấu hình Framework sang Boot.

### Muốn giữ auto-configuration của Boot: chỉ implement WebFluxConfigurer

Trong Boot, nếu chỉ muốn bổ sung cấu hình, khai báo một `@Configuration` implement `WebFluxConfigurer` **mà không gắn `@EnableWebFlux`**:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.http.codec.ServerCodecConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebFluxCustomization implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                  .maxInMemorySize(512 * 1024);
    }
}
~~~

Boot vẫn quản lý WebFlux infrastructure, embedded server, static resources và các tích hợp auto-configured; callback của ứng dụng bổ sung thay đổi vào cấu hình đó.

### Gắn @EnableWebFlux: ứng dụng tự kiểm soát hạ tầng WebFlux

Nếu khai báo:

~~~java
@Configuration
@EnableWebFlux
public class WebFluxCustomization implements WebFluxConfigurer {
}
~~~

`@EnableWebFlux` nhập `WebFluxConfigurationSupport` thông qua `DelegatingWebFluxConfiguration`. Boot nhận thấy ứng dụng đã cung cấp cấu hình WebFlux nền tảng nên **WebFlux auto-configuration lùi lại**. Bạn chịu trách nhiệm nhiều hơn cho cấu hình WebFlux và các tích hợp mặc định mà auto-configuration cung cấp.

Điều đó **không có nghĩa toàn bộ Spring Boot bị tắt**: các auto-configuration khác không liên quan vẫn có thể hoạt động. Phạm vi cần chú ý là hạ tầng WebFlux và các phần Boot gắn trực tiếp với nó.

### So sánh nhanh

| Cách khai báo trong Boot | Kết quả |
| --- | --- |
| Không khai báo `WebFluxConfigurer`, không `@EnableWebFlux` | Boot tự cấu hình WebFlux theo mặc định |
| Implement `WebFluxConfigurer`, không `@EnableWebFlux` | Giữ Boot auto-configuration và bổ sung callback tùy biến |
| Gắn `@EnableWebFlux` | Ứng dụng bật cấu hình Framework; WebFlux auto-configuration của Boot lùi lại |
| Tự khai báo bean hạ tầng cấp thấp | Có thể khiến một phần auto-configuration lùi tùy điều kiện bean; phải kiểm tra điều kiện và các bean phụ thuộc |

Không cần thêm `@EnableWebFlux` chỉ vì muốn override codec, CORS hoặc formatter trong một ứng dụng Boot thông thường.

## 5. Ví dụ Java 17+ chạy được với Spring Boot

Ví dụ này dùng **Spring Boot 3.5.0 và Java 17+**. Mục tiêu là khởi động WebFlux bằng auto-configuration, thêm một controller và tùy biến codec bằng `WebFluxConfigurer` mà không bật `@EnableWebFlux`.

Cấu trúc dự án:

~~~text
webflux-boot-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/demo/
                ├── DemoApplication.java
                ├── GreetingController.java
                └── WebFluxCustomization.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-boot-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

File `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/demo/GreetingController.java`:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class GreetingController {

    @GetMapping("/hello")
    public Mono<Map<String, String>> hello() {
        return Mono.just(Map.of("message", "Hello WebFlux"));
    }
}
~~~

File `src/main/java/com/example/demo/WebFluxCustomization.java`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebFluxCustomization implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                  .maxInMemorySize(512 * 1024);
    }
}
~~~

Chạy trong thư mục `webflux-boot-demo` với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Gọi endpoint ở terminal khác:

~~~bash
curl http://localhost:8080/hello
~~~

Body JSON dự kiến:

~~~json
{"message":"Hello WebFlux"}
~~~

Điều cần quan sát:

1. `spring-boot-starter-webflux` đưa WebFlux và reactive server runtime vào classpath.
2. `@SpringBootApplication` bật cơ chế auto-configuration.
3. Boot khởi tạo server mặc định ở cổng 8080 và lắp ráp các thành phần WebFlux.
4. Component scan phát hiện `GreetingController`; framework ánh xạ `GET /hello`.
5. `WebFluxCustomization` được phát hiện như một cấu hình tùy biến; vì **không có `@EnableWebFlux`**, Boot vẫn giữ WebFlux auto-configuration.
6. Controller trả `Mono`; framework ghi kết quả thành JSON qua codec đã cấu hình.

Đây là ứng dụng Boot hoàn chỉnh. Không cần tự tạo `HttpHandler`, `ReactorHttpHandlerAdapter`, gọi `HttpServer.bindNow()` hay quản lý server lifecycle bằng tay.

## 6. Cùng ý tưởng khi dùng Spring Framework thuần

Nếu không dùng Boot, class cấu hình Framework thường cần bật WebFlux rõ ràng:

~~~java
package com.example.web;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.web.reactive.config.EnableWebFlux;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.http.codec.ServerCodecConfigurer;

@Configuration
@EnableWebFlux
@ComponentScan(basePackages = "com.example.web")
public class FrameworkWebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                  .maxInMemorySize(512 * 1024);
    }
}
~~~

Cấu hình này thực hiện hai việc: bật hạ tầng WebFlux của Framework và đăng ký tùy biến codec. Khi chạy ứng dụng thật, cần tạo `ApplicationContext`, nối `HttpHandler` với server runtime tương thích và quản lý start/stop. Những phần đó thường được Boot tự động làm khi dùng `spring-boot-starter-webflux`.

So sánh các trách nhiệm:

| Trách nhiệm | Framework thuần | Spring Boot |
| --- | --- | --- |
| Bật WebFlux infrastructure | `@EnableWebFlux` hoặc cấu hình nâng cao | Boot auto-config theo điều kiện |
| Tùy biến codec/CORS/formatter | `WebFluxConfigurer` | `WebFluxConfigurer` hoặc Boot properties/customizer |
| Đăng ký controller | `ApplicationContext`, component scan hoặc bean | Component scan từ `@SpringBootApplication` |
| Chọn và thêm server | Tự thêm dependency/runtime | Starter mặc định cung cấp server, có thể thay thế |
| Khởi tạo HTTP handler/server | Tự lắp ráp và quản lý lifecycle | Boot tạo embedded server và nối infrastructure |
| Quản lý properties phổ biến | Tự xây dựng cấu hình | `application.properties`/`application.yaml` và typed properties |

## 7. Chọn đúng dependency và loại ứng dụng

Để chạy WebFlux server bằng Boot, thường thêm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Nếu ứng dụng chỉ muốn dùng **`WebClient`** làm HTTP client reactive trong một ứng dụng Spring MVC, có thể vẫn thấy `spring-boot-starter-webflux` trong classpath. Khi cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng có mặt, Spring Boot **mặc định chọn Spring MVC**, vì nhiều ứng dụng MVC chỉ thêm WebFlux để dùng `WebClient`.

Nếu thực sự muốn chạy WebFlux server trong trường hợp có cả hai starter, cần chủ động chọn loại ứng dụng reactive, ví dụ:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);
application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
~~~

Đây là cách khởi động thay thế trong class main; không nhất thiết phải dùng nếu dự án chỉ có `spring-boot-starter-webflux`. Trong dự án thực tế, nên kiểm tra dependency tree để biết starter MVC có được kéo vào gián tiếp bởi một dependency khác hay không.

Boot mặc định dùng Reactor Netty cho `spring-boot-starter-webflux`; vẫn có thể dùng server reactive khác nếu loại bỏ dependency server mặc định và thêm starter tương ứng. Chọn server là quyết định runtime, không phải do `@EnableWebFlux` tự quyết định.

## 8. Khi nào cần kiểm tra auto-configuration?

Khi một bean hoặc cấu hình không xuất hiện như mong đợi, hãy kiểm tra theo thứ tự:

1. **Classpath:** có `spring-webflux`, codec và server runtime phù hợp không?
2. **Loại ứng dụng:** Boot đang khởi chạy reactive hay servlet application?
3. **Điều kiện auto-configuration:** một bean hạ tầng đã tồn tại khiến WebFlux auto-config lùi lại không?
4. **Annotation:** có `@EnableWebFlux` ở một configuration class khác không?
5. **Component scan:** controller và configuration có nằm trong vùng scan của application class không?
6. **Bean tùy biến:** một bean `HandlerMapping`, `WebFluxConfigurationSupport` hoặc thành phần cấp thấp có thay đổi điều kiện mặc định không?
7. **Properties và codec:** giới hạn bộ nhớ, media type, static path hoặc cấu hình server có làm request/response không như mong đợi không?

Có thể bật log condition evaluation khi cần chẩn đoán:

~~~properties
debug=true
~~~

Boot sẽ in báo cáo điều kiện auto-configuration trong quá trình khởi động. Tìm mục liên quan đến WebFlux để biết cấu hình nào match, cấu hình nào back off và lý do.

Trong môi trường phát triển, Actuator `conditions` endpoint cũng có thể giúp kiểm tra condition report nếu endpoint được bật và được bảo vệ phù hợp. Không mở các endpoint quản trị nhạy cảm công khai chỉ để debug.

## 9. Các lỗi thường gặp

1. **Thêm `@EnableWebFlux` vào ứng dụng Boot chỉ để chỉnh codec:** làm WebFlux auto-configuration của Boot lùi lại. Nếu chỉ cần tùy biến, dùng `WebFluxConfigurer` bean mà không thêm annotation.
2. **Cho rằng `WebFluxConfigurer` tự bật WebFlux trong Framework thuần:** interface chỉ là callback. Framework thuần cần bật cấu hình WebFlux bằng `@EnableWebFlux` hoặc chế độ nâng cao.
3. **Cho rằng `@EnableWebFlux` tự khởi động HTTP server:** nó bật infrastructure Framework; server runtime và bootstrap vẫn cần được cung cấp.
4. **Nhầm WebFlux Framework với Spring Boot:** WebFlux thuộc Framework; Boot chỉ cung cấp auto-configuration và tích hợp tiện ích.
5. **Dùng đồng thời hai starter nhưng mong Boot tự chọn WebFlux:** Boot mặc định chọn MVC khi có cả MVC và WebFlux starter; kiểm tra và chọn application type nếu chủ đích là reactive server.
6. **Tự khai báo bean hạ tầng cấp thấp không hiểu điều kiện:** có thể khiến auto-configuration lùi, dẫn đến thiếu codec, handler hoặc tài nguyên tĩnh.
7. **Cấu hình trùng lặp:** vừa tự khai báo infrastructure, vừa thêm `@EnableWebFlux`, vừa dựa vào Boot có thể tạo bean trùng hoặc thay đổi thứ tự handler.
8. **Tưởng mọi property đều thuộc Spring Framework:** nhiều property như `spring.webflux.*` hoặc `server.*` là tiện ích Boot; Framework thuần không tự đọc các property Boot.
9. **Bỏ quên server runtime khi dùng Framework thuần:** có WebFlux classes chưa đủ để mở cổng HTTP.
10. **Cho rằng thêm WebFlux nghĩa mọi thư viện đều non-blocking:** auto-configuration không biến JDBC hoặc SDK blocking thành reactive; cần chọn driver/client phù hợp.
11. **Tùy biến codec mà không xét kích thước payload:** tăng `maxInMemorySize` quá lớn có thể làm tăng bộ nhớ khi nhiều request đồng thời; chọn giới hạn theo dữ liệu và tải.
12. **Không kiểm tra version:** API callback, package, property và auto-configuration có thể thay đổi giữa Spring Framework/Spring Boot major version; đối chiếu tài liệu cùng version dependency.

## 10. Bảng quyết định nhanh

| Tình huống | Cách làm phù hợp |
| --- | --- |
| Dự án Spring Boot WebFlux mới | Thêm `spring-boot-starter-webflux`, dùng `@SpringBootApplication`, để Boot auto-config |
| Chỉ chỉnh codec, CORS, formatter trong Boot | Khai báo `@Configuration` implement `WebFluxConfigurer`, **không** `@EnableWebFlux` |
| Muốn tự kiểm soát toàn bộ WebFlux infrastructure trong Boot | Dùng `@EnableWebFlux` và tự chịu trách nhiệm cho cấu hình WebFlux cần thiết |
| Ứng dụng Spring Framework không có Boot | Dùng `@EnableWebFlux`/cấu hình nâng cao, tự quản lý context, server runtime và bootstrap |
| Dùng `WebClient` trong ứng dụng MVC | Có thể thêm WebFlux dependency; Boot vẫn mặc định chọn MVC nếu cả hai starter có mặt |
| Thay Reactor Netty bằng server reactive khác trong Boot | Thay dependency server bằng starter/runtime tương ứng |
| Không hiểu tại sao Boot không tạo bean WebFlux | Kiểm tra classpath, application type, `@EnableWebFlux`, bean hạ tầng và condition report |

## 11. Câu hỏi tự kiểm tra

**1. Spring WebFlux thuộc Spring Framework hay Spring Boot?** WebFlux thuộc **Spring Framework**. Spring Boot cung cấp auto-configuration và tích hợp để khởi động nó thuận tiện.

**2. `@EnableWebFlux` làm gì?** Bật cấu hình Java của WebFlux bằng cách nhập cấu hình Framework như `DelegatingWebFluxConfiguration`.

**3. `WebFluxConfigurer` có tự bật WebFlux không?** Không. Nó cung cấp callback tùy biến cho infrastructure đã được bật/cung cấp.

**4. Trong Spring Boot, chỉ muốn chỉnh codec thì cần `@EnableWebFlux` không?** Không. Khai báo `WebFluxConfigurer` mà không thêm `@EnableWebFlux` để giữ auto-configuration của Boot.

**5. Vì sao `@EnableWebFlux` có thể làm WebFlux auto-configuration của Boot lùi lại?** Vì annotation nhập cấu hình nền tảng WebFlux; điều kiện auto-configuration của Boot chỉ áp dụng khi chưa có cấu hình nền tảng tương ứng.

**6. Framework thuần có tự tạo embedded Reactor Netty server không?** Không theo cơ chế auto-configuration của Boot. Ứng dụng cần thêm runtime và tự bootstrap server.

**7. Boot cung cấp thêm gì ngoài infrastructure Framework?** Starter, server nhúng, codec/customizer, static resources, WebJars, properties và error handling mặc định cùng các tích hợp hệ sinh thái.

**8. Nếu có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot chọn gì mặc định?** Spring MVC; có thể chủ động chọn `WebApplicationType.REACTIVE` nếu thực sự muốn WebFlux server.

**9. `@EnableWebFlux` có tắt toàn bộ Spring Boot không?** Không. Nó làm WebFlux auto-configuration lùi lại; các auto-configuration khác vẫn có thể hoạt động.

**10. Khi nào nên dùng Framework thuần?** Khi cần tự kiểm soát việc bootstrap và cấu hình hạ tầng, hoặc tích hợp vào nền tảng runtime đã có. Với ứng dụng server thông thường, Boot giảm đáng kể công việc lắp ráp.

**Ghi nhớ:** Spring Framework cung cấp **WebFlux infrastructure và API cấu hình**. `@EnableWebFlux` bật hạ tầng đó; `WebFluxConfigurer` cho phép tùy biến. Spring Boot tự động kích hoạt và tích hợp hạ tầng dựa trên dependency, application type, bean và properties. Trong ứng dụng Boot, hãy dùng `WebFluxConfigurer` **không có `@EnableWebFlux`** cho các tùy biến thông thường; chỉ bật `@EnableWebFlux` khi chủ đích tự kiểm soát cấu hình WebFlux.

**Tài liệu chính thức:** [Spring Framework — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html), [Spring Boot — Reactive Web Applications and WebFlux Auto-configuration](https://docs.spring.io/spring-boot/reference/web/reactive.html), [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html).
# Nhận diện ứng dụng reactive khi có đồng thời phụ thuộc Spring MVC và WebFlux

> **Phạm vi:** Khởi tạo và kiểm chứng **Spring Boot 3.x + Spring Security 6.x** trong module Spring Security reactive. Bài tập trung vào **web stack đang chạy thực sự** khi trên classpath có cả Spring MVC lẫn Spring WebFlux. Các đoạn Java dùng Java 17+ trong dự án Spring Boot có dependency tương ứng; không phải Java SE độc lập chạy bằng `javac`.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao thêm `spring-boot-starter-webflux` **không tự biến** một ứng dụng Spring MVC thành reactive web server.
2. Dự đoán kết quả Spring Boot chọn `SERVLET` hay `REACTIVE` trong các tổ hợp dependency thông thường.
3. Kiểm chứng loại ứng dụng thực tế bằng `ApplicationContext`, điều kiện auto-configuration và dấu hiệu security chain, thay vì suy đoán từ tên starter, Netty hay kiểu trả về `Mono`.
4. Chủ động khởi động WebFlux khi thật sự cần, rồi chọn đúng bộ API Spring Security cho reactive.
5. Viết kiểm thử để ngăn ứng dụng reactive vô tình trở thành MVC sau khi dependency thay đổi.

## 1. Bẫy phổ biến: có cả hai starter nhưng ứng dụng vẫn là MVC

Giả sử `build.gradle` của một ứng dụng Spring Boot khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Trong điều kiện auto-detection mặc định, **Spring Boot chọn Spring MVC (Servlet)** khi cả Spring MVC và WebFlux có mặt. Đây là hành vi có chủ đích: nhiều ứng dụng MVC chỉ bổ sung WebFlux để sử dụng HTTP client reactive `WebClient` mà không muốn đổi web stack phía server.

Vì vậy, các mệnh đề sau **không tương đương**:

- “Có dependency `spring-webflux`” ≠ “server chạy WebFlux”.
- “Có bean `WebClient`” ≠ “controller đi qua `DispatcherHandler`”.
- “Controller trả về `Mono<T>` hoặc `Flux<T>`” ≠ “server là WebFlux”; Spring MVC cũng hỗ trợ xử lý một số reactive return types trên nền Servlet.
- “Log có Reactor Netty/Netty trong classpath” ≠ “request HTTP do reactive server xử lý”.
- “Dùng `@RestController`” ≠ “chọn MVC hay WebFlux”; cùng annotation có thể dùng ở cả hai.

**Điểm cần nhớ:** loại **web application** được xác lập khi Spring Boot tạo application context. Tại thời điểm đó, starter và cấu hình bootstrap quyết định hạ tầng HTTP phía server; Spring Security sẽ đi theo hạ tầng đang thực sự chạy.

### 1.1 Ba giá trị WebApplicationType

`org.springframework.boot.WebApplicationType` có ba giá trị:

| Giá trị | Ý nghĩa | Dấu hiệu thường gặp |
| --- | --- | --- |
| `SERVLET` | Ứng dụng web dựa trên Servlet | Spring MVC, `DispatcherServlet`, `HttpSecurity` và servlet filter chain |
| `REACTIVE` | Ứng dụng web reactive | Spring WebFlux, `DispatcherHandler`, `ServerHttpSecurity` và reactive web filter chain |
| `NONE` | Không khởi động web server theo mô hình web ứng dụng | CLI/batch/job không có HTTP server do Boot tạo |

Với ứng dụng Boot thông thường không ép loại web: chỉ có starter WebFlux → `REACTIVE`; chỉ có starter Web MVC → `SERVLET`; có cả hai → `SERVLET`. Đây là **quy tắc mặc định**, có thể bị ghi đè bằng lựa chọn tường minh của ứng dụng.

## 2. MVC, WebFlux và Security khác nhau ở tầng nào?

| Khía cạnh | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| Dispatcher xử lý request | `DispatcherServlet` | `DispatcherHandler` |
| Web server context của Spring Boot | `ServletWebServerApplicationContext` | `ReactiveWebServerApplicationContext` |
| Bảo mật request | Servlet `Filter` / `FilterChainProxy` | Reactive `WebFilter` / `WebFilterChainProxy` |
| Cấu hình bảo mật web | `HttpSecurity` tạo `SecurityFilterChain` | `ServerHttpSecurity` tạo `SecurityWebFilterChain` |
| Annotation bật bảo mật | `@EnableWebSecurity` | `@EnableWebFluxSecurity` |
| Khai báo authorization | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| Truy cập context bảo mật | `SecurityContextHolder` gắn với execution thread theo cách Servlet | `ReactiveSecurityContextHolder` qua Reactor Context |
| User details khi cần | `UserDetailsService` | `ReactiveUserDetailsService` |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| HTTP client có thể dùng | `RestClient`, `RestTemplate` hoặc `WebClient` | `WebClient` là lựa chọn phù hợp cho non-blocking pipeline |

**Lưu ý:** nền WebFlux có thể chạy trên Reactor Netty **hoặc** một server/container tương thích khác như Tomcat/Jetty bằng cơ chế adapter. Tên server không phải phép thử quyết định; hãy kiểm tra application context và request pipeline.

Trong reactive stack, việc gọi API chặn luồng (`block()`, JDBC đồng bộ trên event-loop) có thể phá lợi ích của non-blocking. Tuy nhiên, đổi dependency thành WebFlux **không tự động** làm mọi thư viện hay truy vấn trở thành non-blocking.

## 3. Kiểm tra dependency trước khi chạy

Trong một dự án Spring Boot dùng Gradle, quan sát dependency tại **runtimeClasspath**, không chỉ dòng khai báo trực tiếp.

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
```

Trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat`.

Ý nghĩa:

- `spring-webmvc` có mặt → hạ tầng Spring MVC khả dụng. Nếu `spring-webflux` cũng có mặt, Boot mặc định ưu tiên MVC.
- `spring-webflux` có mặt → khả năng dùng WebFlux và `WebClient`, **chưa kết luận** server đang chạy reactive.
- `spring-boot-starter-web` thường kéo theo `spring-webmvc` và Servlet web server starter.
- `spring-boot-starter-webflux` thường kéo theo `spring-webflux` và Reactor Netty starter.
- Một thư viện bên thứ ba hoặc shared module có thể thêm `spring-webmvc` theo dạng transitive; `dependencyInsight` giúp truy ra đường đi.

Nếu dự định làm WebFlux thuần, bước đầu hợp lý là **loại starter MVC không cần thiết từ module ứng dụng** và kiểm tra runtime classpath sau khi Gradle resolve. Nếu phải giữ cả hai vì mục tiêu cụ thể, cần chọn `REACTIVE` rõ ràng ở bootstrap.

**Đừng loại trừ dependency của thư viện khác một cách mù quáng.** Xác định thành phần nào cần Spring MVC và kiểm tra ảnh hưởng trước khi `exclude`; việc xóa một transitive dependency có thể làm hỏng phần mềm đang phụ thuộc nó.

## 4. Phép thử có thể tái hiện: đọc đúng loại ApplicationContext

Đây là một cách kiểm tra **runtime** trực tiếp. Trong ứng dụng Spring Boot 3.x đã thêm các starter trong mục 1, tạo tệp:

`src/main/java/com/example/webstack/WebStackDemoApplication.java`

```java
package com.example.webstack;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class WebStackDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebStackDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner reportWebStack(ApplicationContext context) {
        return args -> {
            String stack;
            if (context instanceof ReactiveWebServerApplicationContext) {
                stack = "REACTIVE";
            } else if (context instanceof ServletWebServerApplicationContext) {
                stack = "SERVLET";
            } else {
                stack = "OTHER";
            }

            System.out.println("WEB_STACK=" + stack);
            System.out.println("CONTEXT_CLASS="
                + context.getClass().getName());
        };
    }
}
```

**Giải thích mã:**

- `ApplicationRunner` chạy sau khi Spring Boot khởi tạo context thành công.
- `ReactiveWebServerApplicationContext` và `ServletWebServerApplicationContext` biểu thị **loại context server thực tế**. Hai lớp là tín hiệu mạnh hơn việc nhìn thấy class `DispatcherHandler` trên classpath.
- Nhánh `OTHER` dành cho trường hợp không khởi tạo web server thông thường, ví dụ `WebApplicationType.NONE`; không vội quy kết đây là lỗi reactive.
- Dòng `CONTEXT_CLASS` giúp người học nhìn thấy class cụ thể (thường bắt đầu bằng `AnnotationConfig...`). Với những ứng dụng tạo nhiều context, hãy bảo đảm đang quan sát **application context của web server chính**, không phải management context hay test slice.

Chạy bằng Gradle wrapper:

```bash
./gradlew bootRun
```

Với **cả hai starter** và không có cấu hình ép stack, dòng kiểm chứng phải là:

```text
WEB_STACK=SERVLET
```

Spring Boot còn in log khởi động và dòng `CONTEXT_CLASS=...`; khối trên chỉ nêu **dòng kết luận** để tránh trình bày giả toàn bộ stdout vốn thay đổi theo phiên bản và môi trường.

### 4.1 Tại sao không chỉ tìm DispatcherHandler?

`DispatcherHandler` là một lớp thuộc thư viện `spring-webflux`, nên việc `Class.forName(...)` thành công chỉ chứng minh JAR có trên classpath. Thậm chí số bean của một loại nào đó có thể bị ảnh hưởng bởi cấu hình thủ công, test slice hoặc context khác.

Khi phải kết luận “ứng dụng HTTP chính đang chạy kiểu nào”, ưu tiên:

1. Kiểu `ApplicationContext` runtime thực tế.
2. Loại auto-configuration được kích hoạt và request dispatcher đang sử dụng.
3. Chuỗi security filter và cách xử lý request có hoạt động đúng stack hay không.
4. Starter/classpath như dấu hiệu **giải thích nguyên nhân**, không phải bằng chứng cuối cùng.

## 5. Cách chủ động chọn WebFlux khi cần giữ cả MVC và WebFlux

### 5.1 Khai báo bằng application.yml

Khi hai starter vẫn phải tồn tại, đặt trong `src/main/resources/application.yml`:

```yaml
spring:
  main:
    web-application-type: reactive
```

Sau đó khởi động lại cùng ứng dụng. Với server factory và cấu hình tương thích, dòng quan sát thay đổi thành:

```text
WEB_STACK=REACTIVE
```

Thuộc tính `spring.main.web-application-type` được Spring Boot xử lý khi tạo context; đặt nó đúng nơi cấu hình bootstrap được nạp. Kiểm tra các profile, biến môi trường, command-line args và cấu hình được triển khai vì nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị.

Có thể truyền ngay tại lệnh chạy để khảo sát, không cần đổi cấu hình chung:

```bash
./gradlew bootRun --args='--spring.main.web-application-type=reactive'
```

Trên Windows PowerShell, chạy lệnh tương ứng với `.\gradlew.bat`. Nếu project có logic bootRun riêng, kiểm tra cách truyền tham số vào chương trình Java.

### 5.2 Chọn bằng mã khởi động

Khi không muốn dựa vào file cấu hình, đặt `WebApplicationType` trước `run()`:

```java
package com.example.webstack;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebStackDemoApplication {
    public static void main(String[] args) {
        SpringApplication app =
            new SpringApplication(WebStackDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.REACTIVE);
        app.run(args);
    }
}
```

Đây là **cách viết thay thế phần `main`** của ví dụ trước, không đặt hai class có cùng tên trong một package. Nếu muốn giữ `ApplicationRunner` dùng để quan sát, giữ bean probe ở một `@Configuration` riêng hoặc trong chính class này.

### 5.3 Quyết định thiết kế nên ưu tiên

Nếu server thực sự là WebFlux và không có chức năng server MVC, **nên bỏ `spring-boot-starter-web`** khỏi ứng dụng, tránh phụ thuộc không cần thiết và tránh sự cố đổi stack khi nâng cấp. Ép `REACTIVE` khi vẫn giữ nhiều hạ tầng Servlet là lựa chọn hợp lệ nhưng phải kiểm tra auto-configuration, dependency compatibility và cấu hình security khi deploy.

Nếu cần **MVC server + WebClient** để gọi dịch vụ khác, hãy giữ mặc định `SERVLET`. `WebClient` là thư viện HTTP client; dùng nó không đòi hỏi phải chuyển toàn bộ HTTP server sang WebFlux.

## 6. Vì sao lựa chọn web stack tác động trực tiếp đến Spring Security?

Spring Security có hai **bộ cấu hình dành cho hai runtime khác nhau**:

| Nếu app thực tế là... | Bean cấu hình đúng | DSL và pipeline |
| --- | --- | --- |
| `SERVLET` | `SecurityFilterChain` | `HttpSecurity`, `authorizeHttpRequests`, Servlet filter chain |
| `REACTIVE` | `SecurityWebFilterChain` | `ServerHttpSecurity`, `authorizeExchange`, `WebFilter` |

Không xem hai bean này là biến thể có thể thay thế tự do. Một cấu hình reactive dùng `@EnableWebFluxSecurity` không tự làm một ứng dụng MVC chuyển WebFlux, và một `SecurityFilterChain` servlet không tự bảo vệ request đi qua reactive web filter chain. Khi Spring Boot chọn sai loại, cấu hình security bạn định áp dụng có thể không khởi tạo, khởi tạo sai cách hoặc bị bộ security khác thay thế; **phải kiểm tra runtime và request thực tế**, không chỉ thấy source có annotation.

### 6.1 Cấu hình minh họa cho reactive stack

Khi ứng dụng **đã được xác nhận** chạy WebFlux, cấu hình:

```java
package com.example.webstack;

import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain applicationSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

**Các ý chính:**

- `@ConditionalOnWebApplication(type = REACTIVE)` là lớp bảo vệ để config này chỉ tham gia khi app đang có reactive web context. Nó **không phải lệnh chuyển loại web**.
- `@EnableWebFluxSecurity` bật hạ tầng Spring Security cho WebFlux. `SecurityWebFilterChain` được áp dụng như reactive `WebFilter`.
- `authorizeExchange` làm việc với `ServerWebExchange`; `pathMatchers("/public/**")` cho phép route public, các route còn lại phải xác thực.
- `httpBasic` ở đây chỉ để demo cơ chế authentication đơn giản; hệ thống production có thể dùng session/OIDC hoặc JWT Resource Server tùy bài toán.
- Cấu hình này **không tắt CSRF**. Đối với browser dùng cookie, giữ CSRF; chỉ cân nhắc tắt trên API Bearer-only đã xác định rõ.
- Nếu còn cấu hình servlet `@EnableWebSecurity`/`SecurityFilterChain` trong project, hãy xác định phạm vi active và loại bỏ cấu hình lệch stack. Đừng duy trì hai policy khác nhau rồi giả định cả hai cùng được áp dụng.

Để sử dụng các lớp trên, cần `spring-boot-starter-security`; bài demo thuần WebFlux có thể dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Hai nhóm dependency trên là **hình thức chuẩn hóa đơn giản hơn** cho một ứng dụng WebFlux server. Tên class bảo mật và API trong ví dụ thuộc Spring Security 6.x / Spring Boot 3.x.

### 6.2 Nếu chủ động ở lại với Servlet

Một ứng dụng MVC dùng `WebClient` vẫn cấu hình security phía server theo MVC:

```java
package com.example.webstack;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain servletSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(requests -> requests
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

Đây là **phương án thay thế** khi app chọn MVC, không dùng đồng thời với cấu hình `ReactiveSecurityConfig` ở cùng ứng dụng để suy ra stack. Việc `WebClient` có trong project không làm cho `HttpSecurity` trở thành `ServerHttpSecurity`.

## 7. Ba nguồn bằng chứng khi chẩn đoán sự cố

### 7.1 ApplicationContext là bằng chứng chính

Các type kiểm tra trong mục 4 tồn tại ở Spring Boot 3.x:

- `org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext`
- `org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext`

Chúng nói lên context được tạo để chạy reactive hay servlet HTTP server. Nếu test chạy một context khác với ứng dụng production, kết luận chỉ đúng trong phạm vi test đó.

### 7.2 Auto-configuration condition report

Chạy ứng dụng khi chẩn đoán với tham số:

```bash
./gradlew bootRun --args='--debug'
```

Xem **Conditions Evaluation Report** về `WebFluxAutoConfiguration`, `WebMvcAutoConfiguration`, `ReactiveWebServerFactoryAutoConfiguration`, `ServletWebServerFactoryAutoConfiguration` và các security auto-configurations tương ứng. Tên/điều kiện chính xác có thể khác theo Boot version; hãy đọc điều kiện match hoặc không match trong log.

Nếu dùng Spring Boot Actuator, endpoint `/actuator/conditions` có thể cung cấp báo cáo tương tự khi được cấu hình và cấp quyền phù hợp. Không mở các endpoint chẩn đoán nhạy cảm ra Internet công cộng. **Không suy luận chỉ từ có class WebFlux trên classpath**; đọc điều kiện thực tế đã match.

### 7.3 Log web server, dispatcher và filter chain

Trong cấu hình starter mặc định thường thấy MVC cùng Tomcat và WebFlux cùng Reactor Netty. Tuy nhiên, WebFlux có thể dùng Tomcat/Jetty làm HTTP server, vì vậy **Tomcat xuất hiện không luôn đồng nghĩa MVC**. Nhận diện dispatcher:

- MVC: `DispatcherServlet` và `FilterChainProxy` của Servlet Security.
- WebFlux: `DispatcherHandler` và `WebFilterChainProxy` của Reactive Security.

Các class trong dependency không đủ chứng minh request đã đi qua chúng. Quan sát context/bean **đang hoạt động**, log filter được sử dụng và phản hồi của request kiểm thử.

## 8. Kiểm thử ngăn đổi stack ngoài ý muốn

Nếu yêu cầu kiến trúc của module là **reactive server**, thêm integration test khởi tạo ứng dụng thật và assert loại context. Ví dụ trong tệp `src/test/java/com/example/webstack/ReactiveWebStackTest.java`:

```java
package com.example.webstack;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.context.ApplicationContext;

@SpringBootTest(
    classes = WebStackDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.main.web-application-type=reactive"
)
class ReactiveWebStackTest {

    @Autowired
    ApplicationContext context;

    @Test
    void webApplicationContextIsReactive() {
        assertThat(context)
            .isInstanceOf(ReactiveWebServerApplicationContext.class);
    }
}
```

Dependency test tương ứng trong Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chạy:

```bash
./gradlew test --tests '*ReactiveWebStackTest'
```

**Giới hạn quan trọng của test trên:** `properties = "spring.main.web-application-type=reactive"` ép stack **chỉ trong test**. Test chứng minh cách chạy khi đã ép reactive, nhưng **không chứng minh cấu hình deploy mặc định sẽ chọn reactive**. Để chống regression thực sự, có thêm test không ép `web-application-type`, dùng đúng production configuration và assert `ReactiveWebServerApplicationContext`. Nếu bạn giữ cả hai starter có chủ đích, đặt cấu hình reactive ở profile/default production tương ứng rồi kiểm tra test nạp **cùng nguồn cấu hình**.

Ví dụ test xác nhận **mặc định** (tách thành file `DefaultWebStackTest.java`):

```java
package com.example.webstack;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;

@SpringBootTest(
    classes = WebStackDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class DefaultWebStackTest {

    @Autowired
    ApplicationContext context;

    @Test
    void defaultStackIsServletWhenBothStartersArePresent() {
        assertThat(context)
            .isInstanceOf(ServletWebServerApplicationContext.class);
    }
}
```

Test `DefaultWebStackTest` chỉ đúng khi cả hai starter có mặt **và không có cấu hình khác ép REACTIVE**. Nếu `application.yml` đã chứa `spring.main.web-application-type=reactive`, test này **phải đổi kỳ vọng** thành reactive hoặc tách sang dự án/profile fixture để chứng minh đúng hành vi default. Hai test ở đây minh họa **hai chế độ có chủ ý**, không yêu cầu luôn giữ cả hai class khi policy của dự án chỉ cho phép một chế độ.

Để tránh test bị sai do context mock/slice:

- `@WebFluxTest` chỉ dựng một lát cắt WebFlux, có thể không phản ánh cách toàn ứng dụng production chọn web stack.
- `WebTestClient` có thể bind trực tiếp controller/router mà không mở real server; một request test pass chưa chứng minh Boot production là WebFlux.
- `@SpringBootTest(webEnvironment=RANDOM_PORT)` gần với runtime hơn; vẫn cần kiểm tra properties/profile/launcher giống đường chạy production.
- Với app được ép WebFlux, kiểm tra thêm `SecurityWebFilterChain` hoạt động trên endpoint thực và quyền truy cập đúng như thiết kế.

## 9. Kịch bản A/B/C để tự thực hành

| Kịch bản | Dependencies có mặt | Cấu hình ứng dụng | Kỳ vọng `WEB_STACK` |
| --- | --- | --- | --- |
| A | `starter-webflux`, không có `starter-web` | Không ép `web-application-type` | `REACTIVE` |
| B | Cả `starter-web` và `starter-webflux` | Không ép `web-application-type` | `SERVLET` |
| C | Cả `starter-web` và `starter-webflux` | `spring.main.web-application-type=reactive` | `REACTIVE` |
| D | `starter-web`, không có `starter-webflux` | Không ép `web-application-type` | `SERVLET` |
| E | Không có web server starter phù hợp | Tùy cấu hình | Có thể `NONE` hoặc lỗi startup nếu ép stack mà thiếu server factory |

**Thứ tự thực hành:**

1. Tạo project Boot 3.x Java 17+ và đặt class probe mục 4.
2. Chạy riêng chỉ với `starter-webflux` và ghi nhận `WEB_STACK=REACTIVE`.
3. Bổ sung `starter-web`; chạy lại và thấy `WEB_STACK=SERVLET`.
4. Giữ cả hai nhưng đặt `spring.main.web-application-type=reactive`; chạy lại và thấy `WEB_STACK=REACTIVE`.
5. Bỏ property rồi thay main bằng phiên bản `setWebApplicationType(REACTIVE)`; xác nhận cùng kết quả.
6. Khi thêm `starter-security`, kiểm tra chain theo đúng stack bằng endpoint được bảo vệ. Một request không xác thực nên bị chặn theo policy; một request có credential/role phù hợp phải qua kiểm tra đúng, không để kết quả status mặc định che lỗi cấu hình.

Kỳ vọng A/B/C/D giả định starter tạo được web server phù hợp, không có cấu hình launcher/profile đặc biệt hoặc bean custom thay đổi hành vi.

### 9.1 Các câu hỏi tự kiểm tra

**Câu 1:** Dự án có MVC + WebFlux, controller trả về `Mono<String>`. Có kết luận server đang reactive được không?

**Đáp:** Không. Spring Boot mặc định ưu tiên MVC khi cả hai hiện diện. Phải kiểm tra `ApplicationContext` hoặc auto-configuration runtime.

**Câu 2:** Sau khi thêm `WebClient` vào ứng dụng MVC, cần đổi sang `@EnableWebFluxSecurity` không?

**Đáp:** Không. `WebClient` là HTTP client; security server vẫn dùng `HttpSecurity` / `SecurityFilterChain` trong servlet stack.

**Câu 3:** Log có “Tomcat started”. Có thể chắc chắn WebFlux không hoạt động không?

**Đáp:** Không. WebFlux có thể dùng servlet container với adapter; cần kiểm tra context và dispatcher.

**Câu 4:** Đặt `@SpringBootTest(properties="spring.main.web-application-type=reactive")` và test qua. Đã bảo đảm ứng dụng production reactive chưa?

**Đáp:** Chưa. Property chỉ áp dụng cho test đó; kiểm tra bootstrap và profile khi deploy.

**Câu 5:** App đang MVC nhưng copy code `SecurityWebFilterChain` từ tài liệu reactive. Hệ quả?

**Đáp:** Không thể giả định reactive security sẽ bảo vệ HTTP request MVC. Có thể startup fail hoặc policy mong muốn không active. Dùng đúng security stack, kiểm tra context và hành vi request.

## 10. Các lỗi phổ biến và cách khắc phục

1. **Chỉ nhìn tên starter WebFlux:** liệt kê dependency chưa chứng minh runtime. Dùng `ApplicationRunner` đọc context, kết hợp condition report.
2. **Tưởng mọi `Mono` là non-blocking WebFlux:** Spring MVC cũng có thể nhận reactive return type; xác minh dispatcher và kiểm tra chỗ gọi blocking.
3. **Thấy Netty JAR rồi kết luận Netty đang nhận request:** classpath khác với web server thực tế. Kiểm tra context/web server factory và startup logs.
4. **Đặt `@EnableWebFlux` để “ép” web application type:** annotation này điều chỉnh cấu hình WebFlux, **không phải** cơ chế chọn `WebApplicationType` của Boot; còn có thể vô tình bỏ các customization từ Boot.
5. **Dùng sai security DSL:** `authorizeHttpRequests`/`HttpSecurity` thuộc Servlet; `authorizeExchange`/`ServerHttpSecurity` thuộc reactive. Không trộn loại bean/config.
6. **Nạp cả security config Servlet và Reactive mà không kiểm tra điều kiện:** dễ tạo policy không mong đợi, bean thiếu hoặc khởi động thất bại. Dùng điều kiện theo web type và tách module khi hợp lý.
7. **Dùng `@WebFluxTest` làm bằng chứng cho server production:** test slice không nói lên cách Boot bootstraps toàn bộ app. Viết integration test dùng context thật.
8. **Ép REACTIVE nhưng để thư viện chỉ hỗ trợ Servlet điều khiển request:** có thể lỗi startup hoặc chức năng không hoạt động. Rà các filter, listener, servlet integration và migration riêng.
9. **Loại nhầm transitive dependency:** kiểm tra `dependencyInsight` và người tiêu thụ trước khi exclude.
10. **Không test sau khi đổi starter:** thay đổi classpath có thể đổi context và toàn bộ Spring Security auto-configuration. Thiết lập regression test xác minh loại web stack **và** route/authorization policy.

## 11. Checklist trước khi gọi ứng dụng là “Spring Security reactive”

- [ ] Đã phân biệt nhu cầu **WebFlux HTTP server** với nhu cầu chỉ dùng reactive `WebClient`.
- [ ] Đã xác định runtime classpath có `spring-webmvc` / `spring-webflux` và lý do xuất hiện.
- [ ] `ApplicationContext` của web server chính là `ReactiveWebServerApplicationContext`; không dựa riêng vào kiểu `Mono` hay tên server.
- [ ] Nếu giữ cả MVC và WebFlux, đã chọn `REACTIVE` tường minh và xác minh config được nạp ở môi trường triển khai.
- [ ] Spring Security server sử dụng `SecurityWebFilterChain` / `ServerHttpSecurity`, cùng authentication/authorization được thử bằng HTTP request.
- [ ] Nếu muốn WebFlux thuần, đã xem xét gỡ `spring-boot-starter-web` và các thành phần Servlet không dùng.
- [ ] Kiểm thử khởi chạy toàn ứng dụng xác minh chính **production web stack**, không chỉ kiểm tra một test slice hay ép property riêng ở test.

**Kết luận:** Khi có cả Spring MVC và WebFlux, mặc định **Boot chạy MVC**. Ở bài học Spring Security reactive, điều kiện đủ để gọi đúng hệ thống “reactive web application” là chứng minh **runtime WebFlux thật sự được kích hoạt** và security chain đang chạy đúng theo `ServerHttpSecurity`/`SecurityWebFilterChain`. Classpath và kiểu trả về reactive chỉ là dữ kiện hỗ trợ chẩn đoán.

### Tham khảo chính thức

- [Spring Boot — Reactive Web Applications (quy tắc hai starter)](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot — Testing Spring Boot Applications (Detecting Web Application Type)](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Framework — WebFlux Overview và hỗ trợ server](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Boot 3.3 API — ReactiveWebServerApplicationContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/reactive/context/ReactiveWebServerApplicationContext.html)
- [Spring Boot 3.3 API — ServletWebServerApplicationContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.html)

# Cấu hình endpoint matcher và SecurityWebFilterChain trong ứng dụng Reactive

## 1. Mục tiêu và mô hình cần hiểu

Một ứng dụng Spring WebFlux có thể phục vụ cả API nghiệp vụ và các endpoint vận hành của Actuator. Hai nhóm này thường có chính sách khác nhau: bộ kiểm tra tình trạng cần đọc `health` mà không đăng nhập, còn người vận hành phải có quyền riêng để đọc số liệu.

Trong Spring Security, **xác thực** trả lời “người gửi yêu cầu là ai”; **phân quyền** trả lời “người đó có được làm việc này không”. **Bộ so khớp (matcher)** xác định yêu cầu nào thuộc một chính sách. **Chuỗi bộ lọc bảo mật (`SecurityWebFilterChain`)** chứa các bước bảo mật áp dụng cho những yêu cầu được chọn.

Sau bài này, bạn cần làm được ba việc:

- Chọn đúng các endpoint Actuator bằng `EndpointRequest` của nhánh Reactive.
- Tách chính sách Actuator và API bằng hai `SecurityWebFilterChain`, có thứ tự và chuỗi bao phủ phần còn lại.
- Kiểm chứng chính sách bằng WebTestClient và các lệnh HTTP, kể cả sau khi đổi đường dẫn Actuator.

Ví dụ dùng **Java 21, Spring Boot 3.3.13 và Spring Security 6.3.x do Boot quản lý**. Đây là một dự án Maven độc lập để học cơ chế; không cần chép cấu hình xây dựng của một dự án khác. Dùng đúng tài liệu 3.3 khi đối chiếu vì tên gói và một số thuộc tính có thể khác ở các thế hệ Boot mới.

## 2. Chọn đúng hệ API cho WebFlux

Ứng dụng Reactive dùng bộ lọc `WebFilter`, không dùng chuỗi Servlet Filter. Cặp kiểu tương ứng là:

| Vai trò | Spring WebFlux trong bài | Spring MVC/Servlet |
| --- | --- | --- |
| Cấu hình bảo mật | `ServerHttpSecurity` | `HttpSecurity` |
| Kiểu bean chuỗi bảo mật | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Kiểu matcher | `ServerWebExchangeMatcher` | `RequestMatcher` |
| Quy tắc phân quyền | `authorizeExchange` | `authorizeHttpRequests` |
| Annotation bật cấu hình tường minh | `@EnableWebFluxSecurity` | `@EnableWebSecurity` |

Trong Boot 3.3, import đúng cho Actuator Reactive là:

```java
import org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest;
```

Hai lớp `EndpointRequest` của Servlet và Reactive có cùng tên đơn giản. Import nhầm nhánh `.servlet` tạo ra matcher sai kiểu dù tên phương thức trông giống nhau.

Dự án mẫu dùng `spring-boot-starter-webflux`, `spring-boot-starter-actuator` và `spring-boot-starter-security`. Không thêm `spring-boot-starter-web` vào ví dụ: khi cùng có hai bộ khởi tạo web, cần xác minh ứng dụng thực sự đang chạy theo mô hình nào. Thuộc tính `spring.main.web-application-type: reactive` bên dưới làm lựa chọn của bài thực hành trở nên tường minh. Xem [cấu hình WebFlux của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html#web.security.spring-webflux).

## 3. Hai tầng so khớp: chọn chuỗi trước, chọn quyền sau

Đọc cấu hình theo thứ tự sau:

```text
Yêu cầu HTTP
    |
    +-- Xét các SecurityWebFilterChain theo @Order tăng dần
    |       |
    |       +-- securityMatcher khớp đầu tiên -> chọn đúng một chuỗi
    |
    +-- Trong chuỗi đã chọn:
            xác thực nếu có thông tin đăng nhập
            kiểm tra các bộ lọc liên quan, chẳng hạn CSRF
            áp dụng quy tắc authorizeExchange phù hợp
            cho qua hoặc từ chối
```

### 3.1. securityMatcher xác định phạm vi của cả chuỗi

`securityMatcher(EndpointRequest.toAnyEndpoint())` đặt phạm vi chuỗi là các endpoint Actuator mà matcher nhận diện. Nó không tự yêu cầu đăng nhập hay cấp vai trò.

Chuỗi `@Order(1)` được xét trước chuỗi `@Order(2)`. Khi một chuỗi đã được chọn, yêu cầu không chạy tiếp qua chuỗi sau để tìm một quyền dễ hơn. Vì vậy, tài khoản bị từ chối trong chuỗi Actuator sẽ không “rơi xuống” chuỗi API để thử lại.

### 3.2. authorizeExchange quyết định quyền bên trong chuỗi

Các quy tắc cụ thể phải đứng trước `anyExchange()`. Trong chuỗi Actuator của bài:

1. Khớp endpoint `health` thì cho phép truy cập không cần đăng nhập.
2. Những yêu cầu khác **đã được chuỗi Actuator nhận** phải có vai trò `OPS`.

`anyExchange()` ở đây chỉ là phần còn lại của chuỗi đã chọn, không có nghĩa là mọi URL trong toàn ứng dụng.

Chuỗi thứ hai không khai báo `securityMatcher`, nên nhận mọi yêu cầu còn lại. Nó cho phép `GET /api/ping`, còn những yêu cầu khác phải được xác thực. Đây là chuỗi bao phủ phần còn lại, thường gọi là **fallback**.

Nếu đặt chuỗi bao phủ mọi yêu cầu lên trước, chuỗi Actuator không còn cơ hội được chọn. Nếu chỉ khai báo chuỗi có matcher hẹp mà bỏ chuỗi bao phủ phần còn lại, bạn có thể để các URL ngoài phạm vi không được chuỗi Spring Security nào bảo vệ. Không dựa vào giả định Boot sẽ tự tạo một chính sách bổ sung sau khi đã tự khai báo chuỗi.

Cơ chế chọn một chuỗi theo thứ tự được mô tả trong [Multiple Chains Support của Spring Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html#_multiple_chains_support); ví dụ bên dưới cố định dependency theo Boot 3.3 để tránh vô tình dùng API mới.

## 4. EndpointRequest so với đường dẫn viết cố định

`EndpointRequest` sử dụng thông tin vị trí endpoint của Actuator, phù hợp khi muốn chính sách gắn với **endpoint**, thay vì một chuỗi URL cố định.

| Cách tạo matcher | Ý nghĩa |
| --- | --- |
| `EndpointRequest.toAnyEndpoint()` | Các endpoint Actuator, bao gồm endpoint khám phá liên kết tại đường dẫn gốc |
| `EndpointRequest.to(HealthEndpoint.class)` | Endpoint `health` |
| `EndpointRequest.to("health", "info")` | Chọn bằng ID endpoint, không phải URL |
| `EndpointRequest.toLinks()` | Chỉ endpoint khám phá liên kết |
| `EndpointRequest.toAnyEndpoint().excluding(HealthEndpoint.class)` | Loại `health` khỏi phạm vi matcher này |
| `EndpointRequest.toAnyEndpoint().excludingLinks()` | Loại endpoint khám phá liên kết khỏi phạm vi matcher này |

`to("health")` nhận ID `health`, không nhận `"/actuator/health"`. Không dùng ID endpoint làm bằng chứng rằng endpoint đã được bật hoặc công bố ra HTTP: đó là cấu hình khác.

`pathMatchers("/actuator/**")` có thể phù hợp khi chủ ý bảo vệ một không gian URL. Tuy nhiên, nếu đổi đường dẫn gốc sang `/manage`, quy tắc cố định này không tự chuyển sang URL mới. `EndpointRequest` giúp chính sách đi theo ánh xạ endpoint. Nó cũng không đồng nghĩa với “mọi URL có tiền tố /actuator”: một URL không tồn tại dưới tiền tố đó có thể được chuỗi khác tiếp nhận.

Một bẫy thường gặp là loại `health` khỏi `securityMatcher` để cố công khai nó. **Loại khỏi matcher không phải cấp quyền**: `health` sẽ được xét ở chuỗi kế tiếp; nếu chuỗi đó yêu cầu đăng nhập thì nó vẫn bị bảo vệ. Ví dụ chính giữ `health` trong phạm vi Actuator và cấp `permitAll()` ngay trong chuỗi đó.

Matcher endpoint cũng không nên được hiểu là chỉ khớp đúng một URL lá. Khi công khai `health`, hãy tính cả các đường dẫn con/nhóm sức khỏe mà ứng dụng thực sự công bố. Nếu chính sách chỉ cho phép một đường dẫn kiểm tra rất cụ thể, hãy thiết kế matcher chi tiết và kiểm thử cả các đường dẫn con cần hạn chế.

Định nghĩa các phương thức nằm trong [Javadoc EndpointRequest Reactive 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/reactive/EndpointRequest.html).

## 5. Ví dụ hoàn chỉnh: health công khai, số liệu yêu cầu OPS

Chính sách cần đạt:

| Tài nguyên | Chưa đăng nhập | Tài khoản reader, vai trò USER | Tài khoản ops, vai trò OPS |
| --- | --- | --- | --- |
| `GET /actuator/health` | Được đọc | Được đọc | Được đọc |
| `GET /actuator/info` | 401 | 403 | Được đọc |
| `GET /actuator/metrics` | 401 | 403 | Được đọc |
| `GET /actuator` | 401 | 403 | Được đọc liên kết |
| `GET /api/ping` | Được đọc | Được đọc | Được đọc |
| `GET /api/private` | 401 | Được đọc | Được đọc |

Các cột có tài khoản giả định mật khẩu đúng. Gửi thông tin đăng nhập sai có thể bị bộ lọc xác thực từ chối ngay cả trên tài nguyên `permitAll()`; `permitAll()` không tắt bộ lọc xác thực.

### 5.1. Cấu trúc dự án

```text
reactive-actuator-security/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── DemoApplication.java
    │   │   └── SecurityConfig.java
    │   └── resources/application.yml
    └── test/java/example/
        ├── SecurityPolicyTest.java
        └── RemappedEndpointTest.java
```

### 5.2. pom.xml

Dùng Maven 3.6.3+ và JDK 21. Boot quản lý các phiên bản Spring; không tự gán một phiên bản Spring Security khác cho dự án này.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>reactive-actuator-security</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

### 5.3. src/main/resources/application.yml

```yaml
spring:
  main:
    web-application-type: reactive

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: never
      show-components: never
```

Cấu hình trên chỉ công bố `health`, `info`, `metrics` qua HTTP. **Công bố endpoint (exposure) khác với cấp quyền truy cập**: danh sách include tạo khả năng truy cập qua HTTP; chuỗi bảo mật quyết định ai được truy cập. Mặc định chỉ `health` được công bố qua HTTP.

`show-details: never` và `show-components: never` giữ phản hồi sức khỏe ở mức tổng quát. Công khai endpoint không có nghĩa là phải công khai cấu trúc nội bộ. Nếu thay đổi hai thuộc tính này, cần đánh giá lại dữ liệu mà người chưa đăng nhập sẽ nhận. Xem [Exposing Endpoints và Health Information của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 5.4. src/main/java/example/DemoApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @RestController
    static class ApiController {
        @GetMapping("/api/ping")
        Mono<String> ping() {
            return Mono.just("pong");
        }

        @GetMapping("/api/private")
        Mono<String> privateMessage() {
            return Mono.just("private-ok");
        }
    }
}
```

Hai API nhỏ tạo bằng chứng rằng chuỗi bao phủ phần còn lại đang hoạt động: một API công khai, một API cần đăng nhập. `Mono.just` ở đây chỉ tạo dữ liệu trong bộ nhớ; không có thao tác chặn luồng hay truy vấn cơ sở dữ liệu.

### 5.5. src/main/java/example/SecurityConfig.java

```java
package example;

import org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {
    @Bean
    @Order(1)
    SecurityWebFilterChain actuatorChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeExchange(exchanges -> exchanges
                        .matchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
                        .anyExchange().hasRole("OPS"))
                .httpBasic(withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain applicationChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/ping").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var ops = User.withUsername("ops")
                .password(encoder.encode("ops-pass"))
                .roles("OPS")
                .build();
        var reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(ops, reader);
    }
}
```

Đọc cấu hình này theo từng trách nhiệm:

- `actuatorChain` chỉ nhận yêu cầu Actuator. `health` công khai; số liệu, thông tin và liên kết khám phá cần `OPS`.
- `applicationChain` nhận những yêu cầu còn lại. Quy tắc `GET /api/ping` không cấp quyền cho các phương thức HTTP khác trên cùng đường dẫn.
- `httpBasic(withDefaults())` được cấu hình trên **cả hai chuỗi** vì hai phạm vi đều cần xử lý thông tin đăng nhập Basic. Một cơ chế xác thực nằm trong chuỗi này không tự xuất hiện trong chuỗi khác.
- `MapReactiveUserDetailsService` cung cấp hai người dùng trong bộ nhớ cho bài thực hành. PasswordEncoder tạo giá trị mật khẩu đã băm; chuỗi đã băm có thể khác qua mỗi lần khởi động do muối ngẫu nhiên.
- `.roles("OPS")` tạo authority `ROLE_OPS`; `.hasRole("OPS")` kiểm tra authority đó. Nếu dùng `hasAuthority`, giá trị tương ứng là `"ROLE_OPS"`.

Tên và mật khẩu trong mã chỉ phục vụ việc chạy ví dụ tại máy học. Khi áp dụng vào hệ thống thật, dùng nguồn danh tính và cấu hình bí mật phù hợp; Basic phải đi qua HTTPS để bảo vệ thông tin đăng nhập trên đường truyền. Mã hóa Base64 của Basic không phải mã hóa bảo mật.

Cấu hình không tắt CSRF và không bật form login. Các thử nghiệm chính dùng GET nên không cần token CSRF. Việc tự khai báo chuỗi bảo mật thay chính sách truy cập mặc định bằng chính sách do ứng dụng sở hữu; không có nghĩa là mọi dịch vụ xác thực mặc định cũng tự biến mất. Ở đây, bean `MapReactiveUserDetailsService` làm nguồn người dùng trở nên tường minh.

## 6. Chạy ứng dụng và kiểm chứng qua HTTP

Tại thư mục chứa `pom.xml`:

```bash
mvn clean test
mvn spring-boot:run
```

Giữ tiến trình ứng dụng chạy, rồi mở terminal thứ hai. Hoặc đóng gói và chạy JAR:

```bash
mvn package
java -jar target/reactive-actuator-security-1.0.0.jar
```

Chỉ chạy một cách tại một thời điểm để tránh tranh cổng 8080. Đây là chương trình Spring có dependency, nên dùng Maven biên dịch và giải quyết classpath; gọi riêng `javac DemoApplication.java` sẽ không tự tải các thư viện.

### 6.1. Quan sát nội dung đơn giản

Các lệnh dưới dùng Bash. Nếu chạy PowerShell trên Windows, dùng `curl.exe` để tránh alias; với các lệnh bỏ nội dung phản hồi ở mục tiếp theo, đổi `/dev/null` thành `NUL`.

```bash
curl -s http://localhost:8080/actuator/health
```

Trong dự án mẫu, khi tình trạng ứng dụng là UP, nội dung JSON là:

```json
{"status":"UP"}
```

Đây là nội dung phản hồi HTTP, không phải stdout từ phương thức `main`. Không giả định hệ thống thật luôn UP: tình trạng sức khỏe còn phụ thuộc các thành phần được kiểm tra.

API công khai:

```bash
curl -s http://localhost:8080/api/ping
```

```text
pong
```

API yêu cầu đăng nhập:

```bash
curl -s -u reader:reader-pass http://localhost:8080/api/private
```

```text
private-ok
```

`curl` không tự thêm ký tự xuống dòng cho các nội dung này; code fence chỉ trình bày nội dung.

### 6.2. Kiểm tra mã trạng thái

Chạy sáu lệnh dưới theo thứ tự:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/actuator/metrics
curl -s -o /dev/null -w "%{http_code}\n" -u reader:reader-pass http://localhost:8080/actuator/metrics
curl -s -o /dev/null -w "%{http_code}\n" -u ops:ops-pass http://localhost:8080/actuator/metrics
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/private
curl -s -o /dev/null -w "%{http_code}\n" -u reader:reader-pass http://localhost:8080/api/private
curl -s -o /dev/null -w "%{http_code}\n" -u ops:ops-pass http://localhost:8080/actuator
```

Kết quả mong đợi:

```text
401
403
200
401
200
200
```

Ba dòng đầu phân biệt xác thực và phân quyền:

1. Không có danh tính phù hợp: 401, cần xác thực.
2. Có danh tính hợp lệ nhưng thiếu vai trò: 403, bị từ chối quyền.
3. Có vai trò `OPS`: 200.

Nếu thấy chuyển hướng 302, hãy kiểm tra xem có chuỗi khác bật form login hoặc có cơ chế xử lý lỗi tùy chỉnh hay không. Mẫu này dùng HTTP Basic và không bật form login.

Phản hồi `/actuator/metrics` chứa danh sách tên số liệu; danh sách cụ thể phụ thuộc thời điểm và môi trường. Không dùng một danh sách cố định làm kết quả kiểm thử.

## 7. Kiểm thử tích hợp bằng WebTestClient

Hai tệp sau nạp đầy đủ ngữ cảnh Spring Boot theo WebFlux nhưng dùng môi trường MOCK: WebTestClient gửi yêu cầu HTTP mô phỏng trong cùng tiến trình, không mở cổng mạng. Yêu cầu vẫn đi qua WebFilter, matcher, xác thực Basic bằng nguồn người dùng của ứng dụng và phân quyền; không giả lập danh tính đã đăng nhập.

### 7.1. src/test/java/example/SecurityPolicyTest.java

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class SecurityPolicyTest {
    @Autowired
    WebTestClient client;

    @Test
    void healthIsPublic() {
        client.get().uri("/actuator/health").exchange()
                .expectStatus().isOk()
                .expectBody().jsonPath("$.status").isEqualTo("UP");
    }

    @Test
    void metricsRequiresAuthentication() {
        client.get().uri("/actuator/metrics").exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCannotReadMetrics() {
        client.get().uri("/actuator/metrics")
                .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void opsCanReadMetrics() {
        client.get().uri("/actuator/metrics")
                .headers(headers -> headers.setBasicAuth("ops", "ops-pass"))
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.names").isArray();
    }

    @Test
    void discoveryLinksRequireOps() {
        client.get().uri("/actuator")
                .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
                .exchange().expectStatus().isForbidden();
        client.get().uri("/actuator")
                .headers(headers -> headers.setBasicAuth("ops", "ops-pass"))
                .exchange().expectStatus().isOk();
    }

    @Test
    void fallbackProtectsApplication() {
        client.get().uri("/api/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
        client.get().uri("/api/private").exchange()
                .expectStatus().isUnauthorized();
        client.get().uri("/api/private")
                .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("private-ok");
    }

    @Test
    void unexposedEndpointIsStillAbsentAfterAuthentication() {
        client.get().uri("/actuator/env")
                .headers(headers -> headers.setBasicAuth("ops", "ops-pass"))
                .exchange().expectStatus().isNotFound();
    }

    @Test
    void wrongPasswordFailsAuthentication() {
        client.get().uri("/actuator/metrics")
                .headers(headers -> headers.setBasicAuth("ops", "wrong-pass"))
                .exchange().expectStatus().isUnauthorized();
    }
}
```

`readerCannotReadMetrics` là kiểm thử quan trọng: nếu Actuator vô tình rơi vào chuỗi chỉ yêu cầu `authenticated()`, người dùng `reader` sẽ nhận 200 và kiểm thử thất bại.

Kiểm thử `unexposedEndpointIsStillAbsentAfterAuthentication` dùng tài khoản hợp lệ để thấy 404 của `env`, vì endpoint đó không được công bố trong cấu hình mẫu. Nếu thử URL này khi chưa đăng nhập, chuỗi bao phủ phần còn lại có thể trả 401 trước khi ứng dụng xử lý đến bước tìm handler. Vì vậy không kết luận endpoint tồn tại chỉ từ mã 401, cũng không kết luận 403 luôn là thiếu vai trò.

### 7.2. src/test/java/example/RemappedEndpointTest.java

Kiểm thử thứ hai đổi đường dẫn gốc và đổi ánh xạ riêng của health mà không sửa `SecurityConfig`.

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        properties = {
                "management.endpoints.web.base-path=/manage",
                "management.endpoints.web.path-mapping.health=live"
        })
@AutoConfigureWebTestClient
class RemappedEndpointTest {
    @Autowired
    WebTestClient client;

    @Test
    void healthMatcherFollowsEndpointMapping() {
        client.get().uri("/manage/live").exchange()
                .expectStatus().isOk();
        client.get().uri("/actuator/health")
                .headers(headers -> headers.setBasicAuth("ops", "ops-pass"))
                .exchange().expectStatus().isNotFound();
    }

    @Test
    void roleRuleAlsoFollowsNewBasePath() {
        client.get().uri("/manage/metrics")
                .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
                .exchange().expectStatus().isForbidden();
        client.get().uri("/manage/metrics")
                .headers(headers -> headers.setBasicAuth("ops", "ops-pass"))
                .exchange().expectStatus().isOk();
    }
}
```

Chạy lại:

```bash
mvn test
```

Bộ ví dụ có 10 phương thức kiểm thử: 8 trong `SecurityPolicyTest`, 2 trong `RemappedEndpointTest`. Điều kiện thành công là không có failure/error; không cần khớp toàn bộ log khởi động.

Nếu chỉ gọi controller trực tiếp hoặc dùng client không đi qua chuỗi Spring Security, bạn có thể thấy 200 và tưởng chính sách đúng. Kiểm thử trong cùng tiến trình ở đây kiểm tra cấu hình ứng dụng, ánh xạ endpoint và chuỗi bảo mật. Các lệnh curl ở mục 6 bổ sung việc kiểm tra máy chủ HTTP đang chạy; bộ kiểm thử MOCK không chứng minh việc bind cổng, proxy hay TLS.

## 8. Thay đổi đường dẫn và các ranh giới cần giữ

### 8.1. Đổi đường dẫn Actuator

Để thử thủ công, giữ các thuộc tính khác và bổ sung **bên trong khối `management.endpoints.web` hiện có**, không tạo khóa `management` trùng:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
      path-mapping:
        health: live
      exposure:
        include: health,info,metrics
```

Khi đó dùng `/manage/live`, `/manage/metrics` và `/manage`. Chính sách matcher theo endpoint vẫn phải giữ nguyên: health công khai, metrics cần OPS. Với người đã xác thực, URL cũ `/actuator/health` không còn handler tương ứng và trả 404 trong ví dụ này.

Nếu ứng dụng có `spring.webflux.base-path`, một cổng quản trị riêng, proxy viết lại đường dẫn hoặc context quản trị riêng, hãy kiểm thử URL thực tế và cổng thực tế trong cấu hình đó. Ví dụ chính sử dụng một cổng, không chứng minh sẵn cho mọi cách triển khai. Tách cổng quản trị cũng không thay thế xác thực, phân quyền hay kiểm soát truy cập mạng.

### 8.2. Không nhầm công khai health với công khai mọi dữ liệu sức khỏe

Một matcher theo `HealthEndpoint` có thể bao phủ cả các đường dẫn con của endpoint. Khi thêm nhóm sức khỏe hoặc công bố trạng thái từng thành phần, kiểm tra phản hồi của từng URL đó bằng người chưa đăng nhập. Hai thuộc tính ẩn chi tiết trong mẫu là lựa chọn có chủ ý, không phải tác dụng của `permitAll()`.

Endpoint khám phá liên kết tại `/actuator` cũng có chính sách riêng trong mẫu: nó thuộc `toAnyEndpoint()` và yêu cầu OPS. Công khai health không kéo theo công khai trang liên kết.

### 8.3. Quyền truy cập không thay thế CSRF

Với yêu cầu thay đổi trạng thái như POST đến endpoint `loggers`, có tài khoản và vai trò đúng vẫn có thể nhận 403 khi thiếu token CSRF. Cần phân biệt lỗi CSRF với lỗi phân quyền trước khi sửa vai trò.

Mẫu giữ CSRF mặc định. Không tắt CSRF cho toàn ứng dụng chỉ để một lệnh POST chạy được. Việc điều chỉnh CSRF cần dựa vào cơ chế xác thực, cách trình duyệt gửi thông tin đăng nhập và phạm vi chuỗi; dùng HTTP Basic không tự làm mọi rủi ro CSRF biến mất. Xem [CSRF trong môi trường WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html).

### 8.4. Giữ luồng Reactive không bị chặn

`ServerWebExchangeMatcher` trả kết quả theo mô hình Reactive. Nếu tự viết matcher hoặc dịch vụ xác thực, không gọi `block()`, ngủ luồng hay truy vấn JDBC đồng bộ ngay trên luồng xử lý yêu cầu. Các matcher tích hợp sẵn đủ cho bài này; không cần thêm thuật toán kiểm tra URL thủ công hay tự giải mã header Basic.

## 9. Lỗi phổ biến và hướng chẩn đoán

| Hiện tượng | Điểm cần kiểm tra |
| --- | --- |
| Không biên dịch được khi truyền EndpointRequest | Kiểm tra import có phải `.security.reactive.EndpointRequest`; builder có phải `ServerHttpSecurity` |
| health bất ngờ yêu cầu đăng nhập | Kiểm tra thứ tự chuỗi, quy tắc permitAll, và việc có loại health khỏi securityMatcher hay không |
| reader đọc được metrics | Kiểm tra chuỗi bao phủ mọi URL có đứng trước chuỗi Actuator; quy tắc có chỉ dùng authenticated hay không |
| OPS vẫn nhận 403 khi GET metrics | Kiểm tra authority thực tế; hasRole("OPS") cần ROLE_OPS, không phải authority OPS |
| Chỉ sau khi đổi base-path mới sai quyền | Tìm matcher viết cố định đường dẫn; kiểm tra test đổi đường dẫn |
| API ngoài Actuator mất bảo vệ | Kiểm tra có chuỗi bao phủ phần còn lại và có chính sách cuối cùng hay không |
| Không thấy metrics dù đăng nhập đúng | Kiểm tra dependency Actuator, enablement, exposure và URL thực tế trước khi sửa quyền |
| POST nhận 403 nhưng GET hoạt động | Kiểm tra CSRF, phương thức HTTP và quyền của chính thao tác đó |
| Tài nguyên permitAll vẫn trả 401 | Thử bỏ header đăng nhập sai; bộ lọc xác thực vẫn hoạt động |
| /actuator/env trả 401 khi ẩn exposure | Chuỗi bảo mật có thể chặn trước bước tìm handler; thử bằng danh tính hợp lệ để kiểm tra 404 |

Khi chẩn đoán, theo một yêu cầu cụ thể qua ba câu hỏi: **chuỗi nào được chọn, danh tính nào được xác thực, quy tắc quyền nào áp dụng**. Sau đó mới kiểm tra handler và nội dung phản hồi. Có thể bật log bảo mật ở môi trường học để quan sát, nhưng không ghi thông tin đăng nhập hay token vào log.

## 10. Bài thực hành tự kiểm tra

1. Chạy cả hai lớp kiểm thử. Giải thích vì sao `reader` đọc được `/api/private` nhưng không đọc được `/actuator/metrics`.
2. Tạm đổi thứ tự hai chuỗi trong dự án thực hành. Dự đoán điều gì xảy ra với health và quyền đọc metrics, rồi dùng kiểm thử để xác nhận. Khôi phục thứ tự sau khi thử.
3. Đổi đường dẫn gốc và ánh xạ health như mục 8. Chứng minh chính sách quyền giữ nguyên mà không sửa tên URL trong `SecurityConfig`.
4. Thử loại health khỏi matcher của chuỗi Actuator. Giải thích chuỗi nào tiếp nhận nó và vì sao loại khỏi matcher không tương đương permitAll.
5. Thử truy cập một URL Actuator không được công bố bằng yêu cầu ẩn danh rồi bằng tài khoản hợp lệ. Giải thích vì sao hai mã trạng thái có thể khác nhau.

Bạn hiểu đúng cấu hình khi có thể dự đoán đường đi của từng yêu cầu qua **chọn chuỗi → xác thực → phân quyền**, và chứng minh dự đoán bằng kiểm thử HTTP trên cấu hình thực tế.

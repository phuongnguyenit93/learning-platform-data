# NoOpServerRequestCache và tránh lưu yêu cầu trong API không dùng phiên

## 1. Vấn đề cần giải quyết

Một ứng dụng Spring WebFlux có thể phục vụ hai loại luồng truy cập khác nhau:

- **Website có đăng nhập tương tác:** người dùng mở trang được bảo vệ, ứng dụng chuyển sang trang login, rồi sau khi login thành công đưa người dùng quay lại địa chỉ đã yêu cầu.
- **HTTP API không dùng phiên (stateless API):** client gửi credentials hoặc Bearer token trên từng request, nhận mã HTTP phù hợp và tự quyết định bước tiếp theo; server không cần nhớ URL mà client đã gọi trước khi xác thực.

Spring Security có cơ chế **saved request** cho trường hợp thứ nhất. Nó ghi nhớ một request bị ngắt bởi bước authentication để sau khi xác thực có thể tiếp tục hoặc chuyển hướng tới địa chỉ tương ứng. Tuy nhiên, với API stateless, cơ chế này thường không cần thiết và có thể vô tình tạo phụ thuộc vào WebSession hoặc cookie nếu lựa chọn request cache không phù hợp.

**\`NoOpServerRequestCache\`** là implementation của \`ServerRequestCache\` dành cho WebFlux, cố ý **không lưu, không tìm lại, không khôi phục request**. Spring Security mô tả nó là một request cache “không làm gì”, dùng cho ứng dụng stateless.

Bài học tập trung vào vai trò của lớp này trong **cấu hình bảo mật** Spring Security Reactive; đồng thời chỉ rõ vì sao **tắt request cache không tự biến toàn bộ ứng dụng thành stateless**.

Sau bài này bạn có thể:

1. Giải thích saved request hoạt động trong login flow và vì sao stateless API không cần hành vi đó.
2. Phân biệt \`ServerRequestCache\` với \`ServerSecurityContextRepository\`, HTTP response cache, Reactor Context và cơ chế lưu token.
3. Cấu hình \`NoOpServerRequestCache\` qua \`ServerHttpSecurity\` cho \`SecurityWebFilterChain\`.
4. Chạy một API WebFlux Java 17+, kiểm tra hành vi HTTP 200/401 và xác nhận mỗi request cần credentials mới.
5. Kiểm thử trực tiếp hợp đồng no-op, nhận diện các lỗi cấu hình session, CSRF, redirect, nhiều security chain và lỗi “dùng \`NoOp\` nhưng vẫn thấy cookie”.

## 2. Saved request là gì?

Giả sử một website sử dụng form login:

~~~text
(1) Browser: GET /account/orders
                    |
                    v
(2) Chưa xác thực --> chuyển sang /login
                    |
                    v
(3) Người dùng đăng nhập
                    |
                    v
(4) Login thành công --> quay về /account/orders
~~~

Để làm được bước (4), ứng dụng có thể lưu địa chỉ request ban đầu. Trong Spring Security WebFlux, \`ServerRequestCache\` là abstraction cho cơ chế đó. Một số implementation:

- \`WebSessionServerRequestCache\`: lưu thông tin request trong WebSession.
- \`CookieServerRequestCache\`: lưu URI được yêu cầu trong cookie theo cơ chế tương ứng.
- \`NoOpServerRequestCache\`: không lưu request.

**Không phải “lưu toàn bộ HTTP request để thực thi lại bất kỳ lúc nào”.** Mục đích chủ yếu là hỗ trợ URL/chuyển hướng trong quy trình bị ngắt bởi authentication. Không được hiểu saved request là nơi lưu an toàn body của một giao dịch POST, một command hay dữ liệu nghiệp vụ nhạy cảm để tự động chạy lại.

Với SPA/mobile client hoặc service-to-service API dùng Bearer token, luồng thường là:

~~~text
(1) Client: GET /api/orders
             Authorization: (thiếu / token không hợp lệ)
                    |
                    v
(2) Server: 401 Unauthorized
                    |
                    v
(3) Client tự lấy/cập nhật token theo authentication flow
                    |
                    v
(4) Client gửi request mới với token hợp lệ
                    |
                    v
(5) Server: response 200 + dữ liệu được phép xem
~~~

Server không cần ghi nhớ \`/api/orders\` thay client. Nếu muốn gửi lại request sau khi đăng nhập, client quản lý trạng thái giao diện và tự tạo request mới theo nghiệp vụ.

### 2.1. Vì sao không nên giữ saved request trong API không dùng phiên?

Việc lưu URL chỉ để phục vụ redirect có thể tạo ra những hệ quả không mong muốn:

- Dùng tài nguyên server/cookie cho một bước không có trong hợp đồng HTTP API.
- Kéo theo việc đọc hoặc ghi WebSession trong khi hệ thống mong muốn mỗi request độc lập.
- Khi client mong đợi 401 JSON, logic điều hướng sau đăng nhập khiến luồng khó dự đoán hơn.
- Khó kiểm tra sự tách biệt giữa các request và các instance khi ứng dụng scale ngang.
- Dễ gây nhầm lẫn: đã lưu URI trước login không đồng nghĩa đã lưu authentication hay có quyền truy cập sau login.

**Giới hạn:** nếu ứng dụng không sử dụng nhánh nào có hành vi save request, tác động runtime của thay đổi có thể nhỏ. Lý do cấu hình \`NoOpServerRequestCache\` vẫn hữu ích là thể hiện rõ chính sách: “không duy trì saved-request state cho security flow này”.

## 3. Bốn loại trạng thái dễ bị nhầm lẫn

| Cơ chế | Lưu/trả lời điều gì? | API/đối tượng tiêu biểu | Có bị vô hiệu chỉ vì dùng NoOpServerRequestCache? |
| --- | --- | --- | --- |
| **Saved request** | URI/request trước khi login để có thể quay lại sau xác thực | \`ServerRequestCache\` | **Có:** riêng chức năng saved request dùng cache này |
| **Authentication persistence** | \`SecurityContext\` được lưu/tải giữa các request | \`ServerSecurityContextRepository\` | **Không** |
| **Reactor Context** | Context gắn với **subscription hiện tại**, gồm security context của request | \`ReactiveSecurityContextHolder\` | **Không** |
| **HTTP response cache** | Dữ liệu response cho browser/proxy/CDN hoặc cache ứng dụng | \`Cache-Control\`, CDN, Redis, v.v. | **Không** |

Phân biệt quan trọng nhất là hai interface:

~~~java
// Hai API khác nhau; chữ ký minh họa, không phải một chương trình độc lập.

// Saved request:
ServerRequestCache requestCache;

// Persistence của SecurityContext:
ServerSecurityContextRepository securityContextRepository;
~~~

\`NoOpServerRequestCache\` thuộc package:

~~~text
org.springframework.security.web.server.savedrequest
~~~

Trong khi \`NoOpServerSecurityContextRepository\` thuộc package:

~~~text
org.springframework.security.web.server.context
~~~

Hai lớp tên gần giống nhau nhưng **không thay thế cho nhau**. Một lớp vô hiệu việc lưu request để replay/redirect; lớp còn lại vô hiệu việc lưu và tải \`SecurityContext\` qua repository. Có thể cấu hình cả hai cho một API stateless, nhưng vẫn phải xem xét riêng session của các thành phần khác.

### 3.1. Stateless là một thuộc tính của toàn bộ thiết kế

Một API không dùng phiên thường có những đặc điểm:
- Client gửi thông tin xác thực cần thiết **trên từng request**.
- Server không dựa vào session login trước đó để cho phép truy cập.
- Các request có thể được xử lý trên các instance khác nhau mà không cần chia sẻ phiên authentication.
- Quyết định quyền dựa vào danh tính/quyền được xác minh trên request hiện tại và dữ liệu nghiệp vụ liên quan.

Tuy vậy, “stateless authentication” **không có nghĩa** ứng dụng không dùng database, cache sản phẩm, log, rate limit hoặc bất kỳ state nào. Cơ sở dữ liệu vẫn có thể quản lý đơn hàng/tài khoản; hệ thống vẫn có thể lưu danh sách token bị thu hồi hoặc trạng thái nghiệp vụ theo yêu cầu. Điều cần tránh là phụ thuộc vào **session request trước để xác thực request hiện tại** mà không chủ định.

## 4. NoOpServerRequestCache thực sự làm gì?

\`NoOpServerRequestCache\` implements \`ServerRequestCache\` và cung cấp instance dùng chung qua:

~~~java
NoOpServerRequestCache.getInstance()
~~~

Ba phương thức trong interface:

| Phương thức | Kết quả có ý nghĩa khi dùng NoOp |
| --- | --- |
| \`Mono<Void> saveRequest(ServerWebExchange exchange)\` | Hoàn thành mà không lưu request |
| \`Mono<URI> getRedirectUri(ServerWebExchange exchange)\` | \`Mono.empty()\`: không có URI đã lưu để chuyển hướng |
| \`Mono<ServerHttpRequest> removeMatchingRequest(ServerWebExchange exchange)\` | \`Mono.empty()\`: không có request cũ để lấy ra/loại bỏ |

Do đó, một request chưa xác thực **không** được no-op cache giữ lại để tiếp tục sau khi client đăng nhập. Spring Security vẫn có thể chọn HTTP 401 hoặc chuyển hướng tới login tùy **authentication entry point** đã cấu hình; chính \`NoOpServerRequestCache\` không tự quyết định status hoặc redirect.

Một cách đọc đúng về hành vi này:

~~~text
ServerRequestCache.saveRequest(exchange)
                  |
            NoOp: hoàn thành
                  |
            Không tạo saved request

ServerRequestCache.getRedirectUri(exchange)
                  |
            NoOp: Mono.empty()
                  |
            Không có URI cũ để khôi phục
~~~

Trong Reactive Streams, \`Mono.empty()\` là một publisher hoàn thành không có giá trị, **không phải** \`null\` và cũng không phải lỗi. Các method vẫn thuộc API reactive để được compose với filter chain.

### 4.1. NoOp khác gì “cache trống tạm thời”?

Một cache session mới tạo hôm nay có thể chưa lưu request, nhưng nó **có khả năng lưu trong tương lai** khi flow gọi \`saveRequest\`. NoOp cố ý không giữ state dù có người gọi \`saveRequest\` nhiều lần.

Vì vậy, dùng \`NoOpServerRequestCache\` giúp chính sách ổn định trước những thay đổi về nhánh login/entry point nếu sau này có thành phần gọi tới request cache đã cấu hình.

## 5. Vị trí trong security filter chain

Spring Security Reactive thường hoạt động qua \`SecurityWebFilterChain\`, được cấu hình bằng \`ServerHttpSecurity\`:

~~~text
HTTP request
     |
     v
SecurityWebFilterChain
     |
     +--> Authentication (Bearer / Basic / mechanism phù hợp)
     |
     +--> Khi cần xác thực mà chưa có credentials hợp lệ:
     |         |
     |         +--> Hành vi entry point (401 hoặc redirect tùy cấu hình)
     |         |
     |         +--> Nếu flow liên quan đến saved request:
     |                     ServerRequestCache
     |                     |
     |                     +--> NoOp: không lưu
     |
     +--> Authorization: kiểm tra authorities/quyền nghiệp vụ
     |
     v
WebFlux Handler --> Mono/Flux --> HTTP response
~~~

Đây là **sơ đồ khái niệm**, không mô tả đầy đủ vị trí từng WebFilter hay mọi nhánh authentication. Request cache có thể được các phần của login flow hoặc các filter liên quan đến replay/redirect sử dụng. Một request HTTP Basic hoặc Bearer API đơn giản có thể trả 401 trực tiếp mà không cần cơ chế lưu request.

**Điểm cần nhớ:** \`NoOpServerRequestCache\` không phải một “custom authentication filter” chạy độc lập trước controller. Đây là một **strategy** mà các thành phần Spring Security có thể sử dụng khi xử lý saved request. Cấu hình nó ở đúng \`SecurityWebFilterChain\`.

## 6. Cấu hình chuẩn: request cache no-op

Dành cho Spring Security WebFlux 6.x, cú pháp cấu hình tường minh:

~~~java
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;

// Trong SecurityWebFilterChain đã khai báo:
.requestCache(cache ->
        cache.requestCache(NoOpServerRequestCache.getInstance()))
~~~

Cú pháp được truyền trực tiếp vào \`ServerHttpSecurity\`; dùng lambda là kiểu cấu hình phù hợp với các bản Spring Security hiện đại.

Một cách khác khi chắc chắn không cần bất cứ chức năng request-cache nào trong chain:

~~~java
// Đoạn cấu hình thay thế:
.requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
~~~

Hai cách cùng phục vụ mục tiêu **không dùng saved request** trong chain, nhưng ý nghĩa cấu hình khác nhau: cách đầu chỉ định một implementation no-op; cách sau vô hiệu hẳn phần cấu hình request cache. Nếu mục tiêu bài học là dùng và quan sát \`NoOpServerRequestCache\`, chọn cách đầu.

**Tránh nhầm API:** \`HttpSecurity\` + \`NullRequestCache\` là cách gọi quen thuộc của Servlet/Spring MVC. Với WebFlux, sử dụng \`ServerHttpSecurity\` + \`NoOpServerRequestCache\`. Không mang \`HttpSessionRequestCache\`, \`SecurityFilterChain\` hay Servlet \`Filter\` sang WebFlux để cấu hình cho ứng dụng reactive.

## 7. Ví dụ Java 17+ chạy được: API không lưu saved request

Ví dụ dưới đây dùng Spring Boot **3.3.13**, Spring Security 6.x, Java 17 và Gradle. Nó chủ động bật HTTP Basic để thử bằng \`curl\`; Basic là cơ chế dễ quan sát HTTP 401, không phải lựa chọn mặc định cho API sản xuất. Authentication sử dụng in-memory user chỉ trong demo.

**Mục tiêu kiểm chứng:**
- Người dùng chưa có credentials bị từ chối ở endpoint bảo vệ.
- Người có credentials đúng được xử lý trên request hiện tại.
- Một request mới **không gửi credentials** vẫn bị từ chối, dù trước đó có request thành công.
- Không có saved request để tự động redirect/replay từ cache.
- Code phân biệt rõ request-cache no-op và security-context repository no-op.

Cấu trúc dự án:

~~~text
noop-request-cache-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── ApiController.java
    └── test/java/demo/
        └── NoOpCacheContractTest.java
~~~

### 7.1. Gradle

**\`settings.gradle\`**

~~~groovy
rootProject.name = 'noop-request-cache-demo'
~~~

**\`build.gradle\`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

\`spring-boot-starter-webflux\` cung cấp HTTP WebFlux; \`spring-boot-starter-security\` cung cấp Spring Security Reactive; \`reactor-test\` hỗ trợ kiểm tra Publisher bằng \`StepVerifier\`. Các dependency có version cụ thể tương thích thông qua cơ chế dependency management của Spring Boot.

### 7.2. Application

**\`src/main/java/demo/DemoApplication.java\`**

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.3. Security configuration

**\`src/main/java/demo/SecurityConfig.java\`**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/public").permitAll()
                        .anyExchange().authenticated()
                )
                .requestCache(cache ->
                        cache.requestCache(NoOpServerRequestCache.getInstance())
                )
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}localpass")
                .roles("USER")
                .build();

        return new MapReactiveUserDetailsService(reader);
    }
}
~~~

**Giải thích từng lựa chọn:**

1. \`authorizeExchange\`: \`/api/public\` không yêu cầu đăng nhập; các đường dẫn còn lại yêu cầu xác thực. Quy tắc \`anyExchange()\` tạo một chính sách mặc định rõ ràng.
2. \`requestCache(... NoOpServerRequestCache.getInstance())\`: không giữ request cũ để chuyển hướng/replay sau khi login.
3. \`securityContextRepository(NoOpServerSecurityContextRepository.getInstance())\`: không dùng repository để lưu/tải SecurityContext **giữa các request**. Authentication vẫn có thể tồn tại trong Reactor Context của **request hiện tại**.
4. \`httpBasic\`: client đưa username/password trên từng request; Spring Security xác thực khi nhận credentials.
5. \`formLogin(...disable)\`: không dùng trang đăng nhập HTML trong API demo.
6. \`MapReactiveUserDetailsService\`: cung cấp user \`reader\` trong bộ nhớ để học; không phải kho user production.

**Quan trọng:** \`NoOpServerRequestCache\` và \`NoOpServerSecurityContextRepository\` giải quyết **hai loại state khác nhau**. Cấu hình cả hai nhằm làm rõ mô hình demo; không thể thay lớp này bằng lớp kia.

**An toàn:** \`{noop}\` cố ý bỏ qua password hashing, chỉ dành cho thí nghiệm local. Basic credentials là Base64, không phải mã hóa; không sử dụng trên HTTP không TLS ở môi trường thật. Dùng HTTPS và password encoder phù hợp khi triển khai. Ví dụ chỉ thực hiện HTTP GET, không thực hiện thao tác thay đổi trạng thái. Không tắt CSRF chỉ vì ứng dụng có đường dẫn \`/api\`; cơ chế browser credential, cookie và endpoint ghi dữ liệu quyết định chính sách CSRF phù hợp.

### 7.4. Controller

**\`src/main/java/demo/ApiController.java\`**

~~~java
package demo;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/private")
    public Mono<String> privateEndpoint() {
        return Mono.just("private");
    }

    @GetMapping("/api/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> "user:"
                        + context.getAuthentication().getName());
    }
}
~~~

Handler trả Publisher và không tự \`block()\`/\`subscribe()\`. \`ReactiveSecurityContextHolder\` lấy authentication trong context của pipeline request sau khi credentials được xác thực; không đòi hỏi phải lưu context vào session.

### 7.5. Chạy thử và so sánh status

Ở thư mục dự án, chạy:

~~~bash
gradle bootRun
~~~

Nếu dự án có Gradle Wrapper, có thể dùng \`./gradlew bootRun\`. Mặc định server nghe cổng 8080; terminal khác chạy:

~~~bash
# 1. Public endpoint
curl -i http://localhost:8080/api/public

# 2. Protected endpoint, không credentials
curl -i http://localhost:8080/api/private

# 3. Protected endpoint, cung cấp credentials đúng
curl -i -u reader:localpass http://localhost:8080/api/private

# 4. Request hoàn toàn mới, lại không có credentials
curl -i http://localhost:8080/api/private

# 5. Đọc principal của request hiện tại
curl -i -u reader:localpass http://localhost:8080/api/me

# 6. Mật khẩu sai
curl -i -u reader:wrong http://localhost:8080/api/private
~~~

| Lệnh | Status mong đợi | Body/ý nghĩa |
| --- | --- | --- |
| 1 | **200 OK** | \`public\` |
| 2 | **401 Unauthorized** | Cần credentials; HTTP Basic có thể gửi \`WWW-Authenticate\` |
| 3 | **200 OK** | \`private\` |
| 4 | **401 Unauthorized** | Request trước thành công **không** đăng nhập cho request mới |
| 5 | **200 OK** | \`user:reader\` |
| 6 | **401 Unauthorized** | Thông tin xác thực không hợp lệ |

Phần thân lỗi và tập header có thể khác nhau theo phiên bản cấu hình Spring Security; những kết quả chính cần xác minh là **HTTP status và body của các response thành công**.

**Không suy luận quá mức từ \`curl\`:** việc không thấy redirect là đúng với HTTP Basic entry point, nhưng riêng quan sát đó **chưa chứng minh** NoOp cache hoạt động; Basic có thể không cần redirect dù đang dùng cache khác. Test trực tiếp trong phần kế tiếp sẽ kiểm tra hợp đồng no-op.

## 8. Unit test hợp đồng NoOpServerRequestCache

Ví dụ test này kiểm tra chính xác việc \`NoOpServerRequestCache\` không lưu hoặc khôi phục request. Nó bổ sung cho kiểm thử HTTP; **không phải** một integration test chứng minh toàn bộ security chain hoặc mọi thành phần session đã tắt.

**\`src/test/java/demo/NoOpCacheContractTest.java\`**

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;
import org.springframework.security.web.server.savedrequest.ServerRequestCache;
import org.springframework.web.server.ServerWebExchange;

import reactor.test.StepVerifier;

class NoOpCacheContractTest {

    @Test
    void noOpCacheDoesNotSaveOrReturnRequests() {
        ServerRequestCache cache = NoOpServerRequestCache.getInstance();

        ServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/private")
        );

        StepVerifier.create(cache.saveRequest(exchange))
                .verifyComplete();

        StepVerifier.create(cache.getRedirectUri(exchange))
                .verifyComplete();

        StepVerifier.create(cache.removeMatchingRequest(exchange))
                .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Với mã và dependencies đã trình bày, test kỳ vọng **PASS**. \`verifyComplete()\` trên publisher trả \`Mono<URI>\` hoặc \`Mono<ServerHttpRequest>\` xác nhận nó hoàn thành **không có \`onNext\`**: nghĩa là không có URI/request đã lưu. Nó cũng xác nhận \`saveRequest\` hoàn thành không lỗi.

Đây là kiểm thử nhỏ nhưng trúng hợp đồng của NoOp. Khi muốn chứng minh **security chain đang dùng đúng instance**, cần thêm integration test với cấu hình Spring Security đã khởi tạo, hoặc kiểm tra cấu hình bean và request thực tế theo môi trường chạy. Test trên chỉ tạo NoOp trực tiếp, không tự xác nhận security chain đã lựa chọn nó.

## 9. Cấu hình API dùng JWT Bearer token

Trong API dùng OAuth2 Resource Server, hướng cấu hình thường là:

~~~java
// Đoạn minh họa để đặt trong bean SecurityWebFilterChain.
// Cần cấu hình hợp lệ cho issuer/JWK của hệ thống nhận token.
return http
        .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .anyExchange().authenticated()
        )
        .requestCache(cache ->
                cache.requestCache(NoOpServerRequestCache.getInstance()))
        .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
        .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
        .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .build();
~~~

**Đoạn này là một biến thể cấu hình, không phải chương trình độc lập.** Ứng dụng cần dependency Resource Server, cấu hình xác thực JWT thật (ví dụ issuer/JWK phù hợp), cách kiểm tra issuer/audience/chữ ký/hạn dùng, ánh xạ scopes/authorities, và chính sách lỗi được duyệt. Không coi một Bearer token bất kỳ là hợp lệ chỉ vì đã tắt request cache.

Hình thức client:

~~~bash
curl -i \
  -H "Authorization: Bearer <access-token-hop-le>" \
  http://localhost:8080/api/private
~~~

Lệnh trên là **mẫu cú pháp**, cần token thật do nhà cung cấp danh tính hợp lệ cấp; không thể chạy thành công chỉ với chuỗi minh họa. Khi triển khai, tránh log token vào terminal history nếu môi trường chia sẻ hoặc nhạy cảm. Token phải được xác minh trên **mỗi request**; nếu thiếu hoặc không hợp lệ, endpoint bảo vệ phải bị từ chối, thông thường là 401.

### 9.1. Có nên luôn tắt session khi dùng JWT?

Nếu API thực sự độc lập và không có login form/cookie authentication, request cache no-op cùng security context repository no-op là hai bước cấu hình hữu ích. Nhưng đánh giá stateless toàn diện còn cần xem:
- Có filter/controller nào gọi \`exchange.getSession()\` và ghi dữ liệu?
- CSRF token repository có dùng WebSession/cookie?
- OAuth2 Login hoặc các bước authorize/redirect của browser có cần lưu trạng thái?
- Hệ thống có sử dụng Spring Session hay cơ chế persistence khác không?
- Có component ngoài Spring Security tạo session cho nhu cầu riêng không?

**NoOp request cache không tự chứng minh “zero cookie, zero WebSession”.** Cũng không tự vô hiệu mọi CSRF token, logout, CORS, authentication entry point, HTTP response cache hoặc việc tạo cookie bởi các phần khác.

## 10. Khi không nên dùng NoOpServerRequestCache

Một website có login form thường muốn người dùng quay lại trang họ đang mở trước khi login. Nếu cấu hình no-op, có thể **mất chức năng trở lại trang trước đó**. Ví dụ:

~~~text
GET /checkout  --> chưa đăng nhập --> login
Login thành công
    |
    +--> Có saved request: có thể quay lại /checkout
    |
    +--> NoOp: không có saved request để lấy lại URL
                    --> dùng URL mặc định hoặc logic điều hướng khác
~~~

Không nên áp dụng no-op vô điều kiện cho toàn bộ hệ thống vừa có API vừa có web login tương tác.

Cách thiết kế rõ ràng là dùng **nhiều \`SecurityWebFilterChain\`** với \`securityMatcher\` và \`@Order\` nếu cần chính sách khác nhau theo route:
- Chain dành cho \`/api/**\`: Bearer/Basic theo hợp đồng API, no-op request cache.
- Chain dành cho website: form/OAuth2 login và saved request nếu trải nghiệm yêu cầu quay lại trang trước đăng nhập.

Cần xác định matcher chính xác; Spring Security chọn chain phù hợp theo thứ tự. Một chain “match tất cả” đặt quá sớm có thể nuốt request API và khiến cấu hình no-op của chain dự định không được áp dụng. Đừng chỉ nhìn bean tồn tại rồi kết luận mọi route đều dùng nó.

## 11. Những sai lầm phổ biến

### Sai lầm 1: Dùng NoOpServerRequestCache và tuyên bố “API hoàn toàn stateless”

**Vì sao sai?** Request cache chỉ quản lý saved request. Authentication repository, CSRF token repository, OAuth2 login, WebSession của code khác hoặc các filter khác vẫn có thể giữ state.

**Cách đúng:** xác định đầy đủ những thành phần ghi/đọc session của toàn bộ API. Với authentication giữa request, xem \`NoOpServerSecurityContextRepository\` và loại cơ chế cookie login nếu không sử dụng. Kiểm tra thực tế qua chuỗi HTTP request mới.

### Sai lầm 2: Dùng NoOpServerSecurityContextRepository nhưng để request cache lưu session

Hai repository/strategy độc lập. Có thể không giữ authenticated user giữa request mà vẫn giữ URL yêu cầu trước login qua request cache khác. Muốn stateless API, xét **cả hai**.

### Sai lầm 3: Tưởng request cache là cache dữ liệu response

\`NoOpServerRequestCache\` không tắt \`Cache-Control\` của Spring Security, không xóa cache Redis và không cấm CDN lưu response. Cache-Control/security headers cần cấu hình, kiểm thử và thiết kế theo dữ liệu thực tế.

### Sai lầm 4: Tưởng NoOp sẽ buộc mọi trường hợp thiếu token trả 401

Status 401, 302, 403 hoặc response tùy authentication entry point, authorization, route và mechanism. No-op cache chỉ quyết định **không giữ saved request**. Một ứng dụng vẫn có thể redirect tới login nếu form login được bật.

### Sai lầm 5: Dùng Servlet API cho WebFlux

Không dùng \`NullRequestCache\` của Servlet, \`HttpSecurity\` hoặc \`HttpSessionRequestCache\` để cấu hình request cache của \`SecurityWebFilterChain\`. Trong WebFlux dùng \`ServerHttpSecurity\` và \`ServerRequestCache\`.

### Sai lầm 6: Disable CSRF bằng phản xạ

“REST API” không tự đồng nghĩa “không cần CSRF”. Nếu trình duyệt tự gửi credential như cookie/session hoặc HTTP Basic, các thao tác thay đổi trạng thái có thể cần bảo vệ CSRF. Chỉ quyết định tắt CSRF sau khi xem **cách credentials được gửi** và mô hình đe dọa, đặc biệt với browser.

### Sai lầm 7: Chỉ kiểm tra request có đăng nhập rồi suy ra request cache no-op

Request có credentials hợp lệ có thể trả 200 với nhiều cấu hình request cache khác nhau. Phải kiểm tra hợp đồng no-op hoặc hành vi saved request/redirect đúng ngữ cảnh; đừng dùng mỗi một status 200 làm bằng chứng.

### Sai lầm 8: Lẫn state của client với state của server

SPA có thể nhớ route trước login trong browser storage hoặc router state. Việc này không chứng minh Spring Security phía server đã lưu request. Với stateless API, client tự quản lý flow phù hợp là bình thường.

### Sai lầm 9: Tự viết WebFilter để xóa session cho mọi request

Không cần thêm filter tự động thao tác session khi đã có các strategy cấu hình phù hợp. Một filter “xóa session” tùy tiện có thể phá vỡ flow browser và không giải quyết nguồn tạo state. Hãy cấu hình đúng request cache, security-context repository, authentication mechanism và các session consumer cụ thể.

## 12. Quy trình kiểm tra một API thật

Dùng checklist thực tế theo thứ tự:

1. **Xác định loại client:** trình duyệt có login form hay API caller đưa token mỗi request?
2. **Xác định security chain:** route này khớp bean \`SecurityWebFilterChain\` nào và thứ tự matcher ra sao?
3. **Kiểm tra request cache:** chain có cấu hình \`NoOpServerRequestCache\` hoặc disable request cache theo chủ đích không?
4. **Kiểm tra SecurityContext repository:** có lưu/tải authentication từ WebSession không?
5. **Kiểm tra authentication:** HTTP Basic, Bearer JWT hay cookie? Mỗi request phải mang gì?
6. **Kiểm tra entry point:** request thiếu authentication trả 401 API hay redirect HTML?
7. **Kiểm tra thành phần session khác:** CSRF, OAuth2 login, \`exchange.getSession()\`, Spring Session, code nghiệp vụ.
8. **Kiểm tra HTTP độc lập:** gửi request không credentials, có credentials, sau đó request mới không credentials; đối chiếu status.
9. **Kiểm tra no-op trực tiếp:** \`saveRequest\` hoàn thành, \`getRedirectUri\` và \`removeMatchingRequest\` không phát giá trị.
10. **Kiểm tra phân quyền thật:** user hợp lệ nhưng thiếu authority phải bị từ chối đúng chính sách; kiểm tra quyền sở hữu tài nguyên ở service nếu có.

### 12.1. Phân biệt triệu chứng và nguyên nhân

| Quan sát | Kết luận có thể đưa ra | Điều không thể kết luận |
| --- | --- | --- |
| Thiếu token → 401 | Authentication entry point đang từ chối request | Chưa chứng minh request cache no-op |
| Request có token → 200 | Token/credentials có thể đã được chấp nhận | Chưa chứng minh không lưu session |
| Request tiếp theo không credentials → 401 | Không có authentication được dùng lại cho request đó | Không chứng minh không có cookie do phần khác tạo |
| Test NoOp trả empty publisher | NoOp không lưu/trả lại request theo hợp đồng | Chưa chứng minh mọi chain đã gắn đúng instance |
| Response có \`Set-Cookie\` | Một thành phần nào đó đang tạo cookie | Không thể đổ lỗi ngay cho request cache |
| Response có \`Cache-Control\` | Có chính sách HTTP caching/header | Không liên quan trực tiếp đến saved-request cache |

### 12.2. Lưu ý về hiệu năng và tính ổn định

No-op cache tránh lưu request vì không cần saved-request flow; nó **không** tự tăng tốc xác thực JWT, tự giảm số truy vấn database hay thay thế giới hạn tốc độ. Hệ thống vẫn phải kiểm soát tài nguyên cho decoding/validation token, authorization và dữ liệu nghiệp vụ.

Nếu chuyển từ session login sang Bearer token, việc thay đổi request cache chỉ là một phần. Cần kiểm tra client migration, logout/revocation, expiration, clock skew, key rotation, quyền truy cập đối tượng và cách xử lý lỗi. Không khẳng định “stateless là không có rủi ro bảo mật”.

## 13. Câu hỏi tự kiểm tra

1. Người dùng mở \`/checkout\` rồi được redirect sang login. Trong quy trình này, saved request dùng để làm gì?
2. Khi dùng \`NoOpServerRequestCache\`, kết quả của \`getRedirectUri(exchange)\` sau \`saveRequest(exchange)\` là gì? Vì sao?
3. Vì sao \`NoOpServerRequestCache\` khác \`NoOpServerSecurityContextRepository\`?
4. Một API JWT vẫn có thể tạo \`WebSession\` sau khi đã cấu hình no-op request cache không? Thành phần nào cần kiểm tra thêm?
5. Vì sao response \`401 Unauthorized\` không đủ để chứng minh \`NoOpServerRequestCache\` đang hoạt động?
6. Khi nào \`NoOpServerRequestCache\` làm xấu đi trải nghiệm của người dùng website?
7. Tại sao không nên tắt CSRF chỉ vì đã đặt \`NoOpServerRequestCache\`?
8. Với nhiều \`SecurityWebFilterChain\`, vì sao matcher và \`@Order\` ảnh hưởng việc áp dụng cấu hình no-op?

**Gợi ý đáp án:**
- (1) Để có thể quay lại URL trước login.
- (2) \`Mono.empty()\`: không có URI đã lưu.
- (3) Một lớp ngăn saved request, lớp kia ngăn lưu/tải SecurityContext giữa request qua repository.
- (4) Có; xem CSRF, OAuth2 login, WebSession của controller/filter hoặc cơ chế khác.
- (5) Status do authentication entry point quyết định; no-op chỉ điều khiển saved request.
- (6) Khi website cần quay về trang trước login.
- (7) CSRF phụ thuộc cách browser gửi credentials và endpoint thay đổi trạng thái.
- (8) Chỉ chain thực sự khớp request mới chi phối yêu cầu đó.

## 14. Tổng kết

**\`NoOpServerRequestCache\` dành cho Spring Security WebFlux giúp vô hiệu hành vi lưu và khôi phục request trước authentication.** Trong API không dùng phiên, client chịu trách nhiệm gửi lại request với credentials hợp lệ, nên không cần server ghi nhớ URL để redirect sau login.

Để có kiến trúc stateless đúng, phân biệt rõ:
- Saved-request state → \`ServerRequestCache\` / \`NoOpServerRequestCache\`.
- Authentication persistence → \`ServerSecurityContextRepository\` / \`NoOpServerSecurityContextRepository\`.
- Danh tính trong **request hiện tại** → authentication filter và \`ReactiveSecurityContextHolder\`.
- Trạng thái do browser, CSRF, OAuth2 Login, thành phần WebSession hoặc hệ thống khác tạo → cấu hình và kiểm thử riêng.

Chọn no-op theo **hợp đồng API**, giữ security chain dễ kiểm chứng và không suy luận “không có session” chỉ từ một dòng cấu hình.

### Tài liệu tham khảo chính thức

- Spring Security Javadoc — \`NoOpServerRequestCache\`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/savedrequest/NoOpServerRequestCache.html
- Spring Security Javadoc — \`ServerRequestCache\`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/savedrequest/ServerRequestCache.html
- Spring Security Javadoc — \`ServerHttpSecurity.RequestCacheSpec\`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.RequestCacheSpec.html
- Spring Security Javadoc — \`NoOpServerSecurityContextRepository\`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html
- Spring Security Reference — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
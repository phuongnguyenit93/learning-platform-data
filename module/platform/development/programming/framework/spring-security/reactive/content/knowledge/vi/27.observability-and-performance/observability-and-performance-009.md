# Giới hạn timeout, kết nối và số tác vụ chờ ở các ranh giới bên ngoài — Spring Security Reactive

## 1. Mục tiêu và bối cảnh

Sau bài này, bạn có thể cấu hình timeout theo từng giai đoạn, giới hạn số connection đang dùng và số request được phép chờ; đặt giới hạn in-flight cho toàn bộ external operation; xử lý timeout, quá tải và cancellation theo cách reactive; kiểm thử các tình huống provider chậm/hỏng; và theo dõi số liệu để điều chỉnh giới hạn mà không làm suy yếu xác thực hoặc phân quyền.

Trong Spring WebFlux + Spring Security, một request có thể phải gọi Identity Provider, OAuth2 token introspection endpoint, JWK endpoint, API phân quyền (PDP), profile/entitlement service, Redis, database hoặc LDAP. Dùng Reactor/Netty giúp không giữ một thread chờ mỗi response HTTP; **reactive không có nghĩa số request, connection, hàng đợi và bộ nhớ tự động được giới hạn**.

~~~text
Incoming request
   -> Spring Security WebFilterChain (xác thực/phân quyền)
   -> Controller / service
   -> [Giới hạn số external calls đang xử lý]
   -> [Chờ acquire connection từ pool]
   -> [TCP/TLS connection]
   -> [Gửi request, chờ response, decode body]
   -> response hoặc lỗi được ánh xạ rõ ràng
~~~

Để chống nghẽn, phải có giới hạn ở **ba chiều riêng biệt**:

- **Thời gian:** request phải được hoàn thành/hủy trước deadline; phân biệt chờ pool, TCP connect, TLS, response và tổng thời gian nghiệp vụ.
- **Kết nối:** downstream không được bị mở quá nhiều socket/HTTP connections.
- **Tác vụ chờ:** cả connection-acquire queue và các business operations chờ đến lượt phải có trần hoặc chính sách từ chối.

Nếu remote call phục vụ quyết định security, lỗi timeout/connection **không được biến thành quyết định cấp quyền**.

## 2. Những giới hạn thực sự có hiệu lực ở đâu?

| Công cụ | Phạm vi bảo vệ | Điều nó không bảo vệ |
| --- | --- | --- |
| `ConnectionProvider.maxConnections(N)` | Connection đang dùng trong mỗi connection pool/remote endpoint | Tổng số request toàn ứng dụng; các pending operations |
| `pendingAcquireMaxCount(N)` | Số yêu cầu *đang chờ lấy connection* | Công việc chưa đến bước acquire; queue scheduler |
| `pendingAcquireTimeout(Duration)` | Thời gian một acquire được phép chờ | DNS/TCP/TLS, response và business processing |
| `ChannelOption.CONNECT_TIMEOUT_MILLIS` | TCP connect | DNS, TLS handshake, body |
| `HttpClient.responseTimeout(Duration)` | Timeout phản hồi/đọc network response | Thời gian xếp hàng trong pool và deadline toàn bộ |
| `Mono.timeout(Duration)` | Deadline khi subscribe đến khi `Mono` phát kết quả/hoàn tất | Không đảo ngược side effect đã xảy ra bên ngoài |
| `Semaphore.tryAcquire()` | Số lời gọi đang giữ permit; có thể fail-fast | Không tự giới hạn socket của thư viện bên thứ ba |
| `Flux.flatMap(mapper, concurrency)` | Số publisher con được subscribe đồng thời **trong một pipeline** | Tổng concurrency của hàng nghìn pipeline |
| `Schedulers.newBoundedElastic(...)` | Số thread/tác vụ xếp hàng cho bridge blocking | Socket/pool và deadline thực của blocking client |

**Phân biệt ba hàng đợi:** (1) hàng đợi HTTP request ở ingress/proxy, (2) hàng đợi pending acquire của Reactor Netty, (3) hàng đợi task của scheduler cho client blocking. Chúng không thay thế nhau.

### Ví dụ về time budget

Giả sử endpoint có ngân sách khoảng 2 giây dành cho outbound profile lookup:

- `pendingAcquireTimeout = 200 ms`: không đợi socket quá lâu.
- `CONNECT_TIMEOUT_MILLIS = 300`: không đợi TCP connect quá lâu.
- `responseTimeout = 1.200 ms`: chặn kết nối có phản hồi mạng quá chậm.
- `bodyToMono(Profile.class).timeout(1.800 ms)`: deadline bao lấy toàn pipeline lấy profile.

Các số này chỉ để minh họa; chúng **không** phải một bộ cấu hình chuẩn. DNS, TLS, retries và overhead còn tốn thời gian; outer timeout có thể cắt sớm. Với `Flux` liên tục phát phần tử, `timeout(Duration)` là giới hạn khoảng im lặng giữa các tín hiệu, không nhất thiết là tổng thời gian stream. Chọn deadline từ SLA và độ trễ p95/p99 thực tế.

Reactor Netty pooling thường tính theo remote host:port; HTTP/2 có thể multiplex nhiều stream trên một connection nên không nên đồng nhất tuyệt đối `maxConnections` với số request. Với nhiều replica, tổng connection đến một nhà cung cấp có thể gần bằng tổng giới hạn mỗi replica.

## 3. Ví dụ Java 17+ có thể chạy: Spring Security và profile API bên ngoài

Ví dụ dùng dự án Gradle Spring Boot 3.x đã có plugin Java và Spring Boot dependency management. Cần các dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
tasks.register('runMockProfileProvider', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.boundary.MockProfileProvider'
}
~~~

Tất cả Java source nằm trong package `com.example.boundary`. HTTP Basic và tài khoản cố định ở đây **chỉ để chạy thử localhost**; production phải dùng hệ thống authentication và credential-management thực.

### 3.1. Bootstrap và security chain

File `src/main/java/com/example/boundary/BoundaryDemoApplication.java`:

~~~java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryDemoApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/boundary/DemoSecurityConfig.java`:

~~~java
package com.example.boundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class DemoSecurityConfig {
    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http.authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/current-profile").authenticated()
                        .anyExchange().permitAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    // Fixture CHỈ CHO LOCAL DEMO. Không dùng {noop} trong production.
    @Bean
    MapReactiveUserDetailsService demoUsers() {
        UserDetails fast = User.withUsername("demo")
                .password("{noop}demo123").roles("USER").build();
        UserDetails slow = User.withUsername("slow")
                .password("{noop}slow123").roles("USER").build();
        return new MapReactiveUserDetailsService(fast, slow);
    }
}
~~~

Một request ẩn danh đến endpoint được Spring Security trả **401** trước khi dùng outbound client. Nếu đã xác thực và profile provider lỗi, đó là lỗi availability của một request đã xác thực: không tự sửa thành 401 hay tự sinh identity.

### 3.2. WebClient riêng: pool, pending queue, connect và response timeout

File `src/main/java/com/example/boundary/ExternalClientConfig.java`:

~~~java
package com.example.boundary;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
class ExternalClientConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider profileConnectionProvider() {
        return ConnectionProvider.builder("profile-pool")
                .maxConnections(8)
                .pendingAcquireMaxCount(8)
                .pendingAcquireTimeout(Duration.ofMillis(200))
                .maxIdleTime(Duration.ofSeconds(20))
                .metrics(true)
                .build();
    }

    @Bean("profileWebClient")
    WebClient profileWebClient(
            WebClient.Builder builder,
            ConnectionProvider profileConnectionProvider,
            @Value("${external.profile.base-url:http://127.0.0.1:9011}")
                    String baseUrl) {

        HttpClient httpClient = HttpClient.create(profileConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
                .responseTimeout(Duration.ofMillis(1200));

        return builder.baseUrl(baseUrl)
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .codecs(c -> c.defaultCodecs().maxInMemorySize(128 * 1024))
                .build();
    }
}
~~~

Ý nghĩa cụ thể: tối đa 8 connections mỗi pool key, tối đa 8 lượt pending-acquire (không phải 8 business requests), mỗi lượt chỉ chờ 200 ms để lấy connection. `maxIdleTime` không thay thế timeout nghiệp vụ. `maxInMemorySize` giới hạn buffer giải mã response, tránh việc upstream trả body khổng lồ gây tăng bộ nhớ. `WebClient.Builder` từ Spring Boot giữ các customizer/observation có sẵn trong context. `metrics(true)` giúp phát số liệu Reactor Netty khi có Micrometer registry.

Với HTTPS còn phải xét DNS, TLS handshake và proxy. `CONNECT_TIMEOUT_MILLIS` đo TCP connect, không mặc nhiên gồm các giai đoạn này. Khi chỉnh sửa client, phải xác định đúng client thật: cấu hình `profileWebClient` **không tự áp dụng** cho HTTP client nội bộ dùng bởi OIDC/JWK/introspection hoặc SDK khác.

### 3.3. Bulkhead nonblocking và deadline trên toàn request

File `src/main/java/com/example/boundary/ExternalProfileClient.java`:

~~~java
package com.example.boundary;

import java.time.Duration;
import java.util.concurrent.Semaphore;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Service
public class ExternalProfileClient {
    private final WebClient webClient;
    private final Semaphore permits;
    private final Duration deadline;

    @Autowired
    public ExternalProfileClient(
            @Qualifier("profileWebClient") WebClient webClient) {
        this(webClient, 12, Duration.ofMillis(1800));
    }

    // Cho phép kiểm thử capacity và deadline nhỏ.
    ExternalProfileClient(WebClient webClient,
                          int maxInFlight, Duration deadline) {
        this.webClient = webClient;
        this.permits = new Semaphore(maxInFlight);
        this.deadline = deadline;
    }

    public Mono<Profile> fetch(String subject) {
        return Mono.defer(() -> {
            if (!permits.tryAcquire()) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "Profile boundary is busy"));
            }

            return webClient.get()
                    .uri(uri -> uri.path("/profiles/{subject}")
                            .build(subject))
                    .retrieve()
                    .onStatus(
                            status -> status.value() == 404,
                            response -> Mono.just(new ResponseStatusException(
                                    HttpStatus.NOT_FOUND, "Profile not found")))
                    .onStatus(
                            HttpStatusCode::isError,
                            response -> Mono.just(new ResponseStatusException(
                                    HttpStatus.SERVICE_UNAVAILABLE,
                                    "Profile provider rejected the request")))
                    .bodyToMono(Profile.class)
                    .switchIfEmpty(Mono.error(new ResponseStatusException(
                            HttpStatus.SERVICE_UNAVAILABLE,
                            "Empty profile response")))
                    .timeout(deadline)
                    .onErrorMap(
                            ex -> !(ex instanceof ResponseStatusException),
                            ex -> new ResponseStatusException(
                                    HttpStatus.SERVICE_UNAVAILABLE,
                                    "Profile provider unavailable", ex))
                    .doFinally(signal -> permits.release());
        });
    }

    public record Profile(String id, String displayName) {}
}
~~~

Tại sao đặt `tryAcquire()` trong `Mono.defer`? Việc tạo một `Mono` chưa thực hiện network call; chỉ khi subscribe mới giành permit. `tryAcquire()` không block event-loop: khi 12 request đang giữ slot, request mới nhận lỗi nhanh thay vì chờ trong hàng đợi vô hạn. `doFinally` chạy khi hoàn tất, lỗi hoặc **cancel**, tránh rò rỉ permit khi client timeout/hủy request. Không dùng `Semaphore.acquire()`, `Thread.sleep()` hay `.block()` trên event-loop.

Đây là một bulkhead **theo JVM/service instance**. 12 in-flight calls bao gồm cả đang đợi connection, đang kết nối và đang đọc response. Con số 8 connections, 8 pending acquire và 12 in-flight là các hạn mức **độc lập**, không phải cam kết “12 = 8 + 4” ở mọi thời điểm.

Trong ví dụ, mọi lỗi chưa được ánh xạ bằng `ResponseStatusException` được đổi thành 503 cho dễ quan sát; khi triển khai thật nên **phân loại riêng** connect timeout, acquire timeout, pool pending overflow, HTTP 5xx, decode lỗi và lỗi code để không che lỗi lập trình.

### 3.4. Controller nhận principal đã xác thực

File `src/main/java/com/example/boundary/ProfileController.java`:

~~~java
package com.example.boundary;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ProfileController {
    private final ExternalProfileClient profiles;

    ProfileController(ExternalProfileClient profiles) {
        this.profiles = profiles;
    }

    @GetMapping("/api/current-profile")
    Mono<ExternalProfileClient.Profile> currentProfile(
            Mono<Principal> principal) {
        return principal.flatMap(p -> profiles.fetch(p.getName()));
    }
}
~~~

Với ứng dụng OIDC thật, nên dùng khóa định danh tin cậy (thường kết hợp issuer và subject) thay vì giả định `Principal.getName()`/email/displayName luôn bất biến. Trong ví dụ, Basic Auth có username xác định sẵn để dễ mô phỏng.

### 3.5. Provider giả lập để thấy timeout

File `src/main/java/com/example/boundary/MockProfileProvider.java`:

~~~java
package com.example.boundary;

import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.netty.http.server.HttpServer;

public class MockProfileProvider {
    public static void main(String[] args) {
        var server = HttpServer.create()
                .host("127.0.0.1")
                .port(9011)
                .route(routes -> routes
                        .get("/profiles/demo", (req, res) ->
                                res.header("Content-Type", "application/json")
                                        .sendString(Mono.just(
                                                "{\"id\":\"demo\","
                                                + "\"displayName\":\"Demo User\"}")))
                        .get("/profiles/slow", (req, res) ->
                                res.header("Content-Type", "application/json")
                                        .sendString(
                                                Mono.delay(Duration.ofSeconds(3))
                                                        .map(tick ->
                                                                "{\"id\":\"slow\","
                                                                + "\"displayName\":\"Slow User\"}"))))
                .bindNow();

        System.out.println("Mock provider: http://127.0.0.1:9011");
        server.onDispose().block();
    }
}
~~~

Ở hai terminal độc lập:

~~~bash
# Terminal 1
./gradlew runMockProfileProvider

# Terminal 2
./gradlew bootRun
~~~

Trên Windows PowerShell thay `./gradlew` bằng `.\gradlew.bat`, sau đó gọi:

~~~bash
curl -i http://localhost:8080/api/current-profile
curl -i -u demo:demo123 http://localhost:8080/api/current-profile
curl -i -u slow:slow123 http://localhost:8080/api/current-profile
~~~

| Tình huống | Kỳ vọng |
| --- | --- |
| Không có authentication | **401** từ Spring Security, không gọi provider |
| Tài khoản `demo`, provider nhanh | **200** và JSON `{"id":"demo","displayName":"Demo User"}` |
| Tài khoản `slow`, provider trả sau 3 giây | **503** vì response timeout/deadline |

Đừng dùng cặp user/password demo, `{noop}` hoặc HTTP localhost làm mẫu cấu hình production.

## 4. Kiểm thử deadline, quá tải và release khi cancel

Test bằng `ExchangeFunction` giả trả response sau một khoảng thời gian: nó kiểm tra chính xác logic permit/deadline của service nhưng **không** tạo connection vật lý, vì vậy không thay cho integration test pool.

File `src/test/java/com/example/boundary/ExternalProfileClientTest.java`:

~~~java
package com.example.boundary;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class ExternalProfileClientTest {
    private WebClient fakeServer(Duration delay) {
        return WebClient.builder()
                .exchangeFunction(request ->
                        Mono.delay(delay).map(ignored ->
                                ClientResponse.create(HttpStatus.OK)
                                        .header(HttpHeaders.CONTENT_TYPE,
                                                MediaType.APPLICATION_JSON_VALUE)
                                        .body("{\"id\":\"demo\","
                                                + "\"displayName\":\"Demo User\"}")
                                        .build()))
                .build();
    }

    private void expect503(Throwable ex) {
        assertThat(ex).isInstanceOf(ResponseStatusException.class);
        assertThat(((ResponseStatusException) ex).getStatusCode())
                .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
    }

    @Test
    void slowProviderExceedsOverallDeadline() {
        var client = new ExternalProfileClient(
                fakeServer(Duration.ofMillis(250)),
                1, Duration.ofMillis(50));

        StepVerifier.create(client.fetch("demo"))
                .expectErrorSatisfies(this::expect503)
                .verify();
    }

    @Test
    void fullBulkheadRejectsFastAndCancelReturnsPermit() {
        var client = new ExternalProfileClient(
                fakeServer(Duration.ofMillis(250)),
                1, Duration.ofSeconds(1));

        Disposable first = client.fetch("demo").subscribe();
        try {
            StepVerifier.create(client.fetch("demo"))
                    .expectErrorSatisfies(this::expect503)
                    .verify();
        } finally {
            first.dispose();
        }

        StepVerifier.create(client.fetch("demo"))
                .assertNext(profile ->
                        assertThat(profile.id()).isEqualTo("demo"))
                .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests 'com.example.boundary.ExternalProfileClientTest'
~~~

Khi cấu hình đầy đủ, kỳ vọng **2 test PASS**. Test thứ hai chứng minh lời gọi sau khi hủy request trước có thể tiếp tục đi qua bulkhead. Những test này **không đo `maxConnections`**; muốn xác minh pool thì cần Reactor Netty `HttpServer` thật trên port ngẫu nhiên, gửi đủ request đồng thời và kiểm tra active/pending/acquire failure.

## 5. Giới hạn fan-out và blocking boundaries

### 5.1. Fan-out nhiều call trong cùng một pipeline

~~~java
Flux<Entitlement> permissions =
        Flux.fromIterable(entitlementIds)
                .flatMap(id -> entitlementClient.fetch(id), 8);
~~~

Đây là **đoạn minh họa** khi ứng dụng đã định nghĩa `Entitlement`, `entitlementIds` và `entitlementClient`. `flatMap(..., 8)` giữ tối đa 8 publisher con được subscribe đồng thời trong pipeline này; nó **không** giới hạn tổng các pipeline từ nhiều request người dùng. Dùng thêm giới hạn tại client/service giống ví dụ trên. Khi bắt buộc bảo toàn thứ tự kết quả, cân nhắc `flatMapSequential` hoặc mô hình phù hợp.

### 5.2. Cầu nối sang API blocking

Với thư viện LDAP/JDBC/SDK chỉ có giao diện blocking, hãy tách thread riêng:

~~~java
Scheduler blockingScheduler =
        Schedulers.newBoundedElastic(4, 20, "directory-io");

Mono<DirectoryUser> user =
        Mono.fromCallable(() -> blockingDirectory.findById(userId))
                .subscribeOn(blockingScheduler)
                .timeout(Duration.ofSeconds(2));
~~~

Đoạn minh họa cần các biến/class `blockingDirectory`, `DirectoryUser`, `userId` có sẵn và imports `reactor.core.scheduler.Scheduler`, `Schedulers`, `reactor.core.publisher.Mono`. `newBoundedElastic(4, 20, ...)` tối đa 4 backing threads và giới hạn task được xếp **trên mỗi backing thread** theo API Reactor; khi đầy có thể ném `RejectedExecutionException`. Hãy quản lý `dispose()` scheduler. `timeout()` hủy subscription nhưng **không bảo đảm** dừng ngay một lệnh blocking IO không hỗ trợ interrupt. Bắt buộc đặt timeout của driver/SDK và giới hạn connection riêng.

## 6. Liên hệ trực tiếp đến Spring Security Reactive

Có hai nhánh quyết định cần phân biệt:

**Đã xác thực rồi mới gọi dịch vụ ngoài.** Profile lookup fail được báo lỗi availability như 503. Không tự đổi username, không tự sinh role, không coi upstream timeout là tài khoản chưa xác thực.

**Dịch vụ ngoài là nguồn xác thực hoặc quyết định quyền.** Ví dụ opaque-token introspection, JWK key refresh, OIDC UserInfo hoặc PDP. Nếu provider lỗi hoặc không lấy được bằng chứng xác thực, **không cấp quyền mặc định**. Đây là mẫu sai:

~~~java
// SAI: Khi không hỏi được PDP lại cho truy cập!
return remoteDecision.onErrorReturn(new AuthorizationDecision(true));
~~~

Ví dụ trên chỉ để nhận diện anti-pattern, không phải code cần dùng. Hãy xử lý fail closed, phân biệt từ chối thật với unavailable và giữ hợp đồng HTTP đúng:

| Trạng thái | Ý nghĩa |
| --- | --- |
| **401 Unauthorized** | Request chưa được xác thực hoặc credential không hợp lệ |
| **403 Forbidden** | Đã xác thực nhưng chính sách không cho phép |
| **503 Service Unavailable** (nếu exception mapping hỗ trợ) | Không thể hoàn thành một phụ thuộc ngoài; request không được cho qua |

Một custom reactive authorization manager có thể phát sinh exception cần được ánh xạ tại đúng lớp filter/exception handler; không giả định mọi lỗi tự biến thành 503. Đừng dùng `onErrorResume(error -> Mono.just(true))` hoặc `onErrorReturn(AuthorizationDecision(true))` trong đường xác minh quyền. Nếu token/permission được cache, cần xác định TTL, key rotation và yêu cầu thu hồi quyền, không “cache vĩnh viễn” để tránh gọi IdP.

**Cấu hình đúng client.** `profileWebClient` chỉ áp dụng tới service ví dụ. Khi dùng `oauth2ResourceServer().jwt()`, `oauth2ResourceServer().opaqueToken()` hay `oauth2Login()`, Spring Security có thể tự tạo decoder, introspector, metadata/JWK HTTP client. Xác định component thực hiện outbound call rồi cấu hình nó bằng hook hỗ trợ ở phiên bản ứng dụng (ví dụ custom `ReactiveOpaqueTokenIntrospector` hoặc `ReactiveJwtDecoder`). Đổi settings của WebClient bất kỳ không có nghĩa introspection/JWK đã được bảo vệ.

## 7. Retry, cancellation và tải dồn

- Retry có giới hạn nhỏ và backoff/jitter **chỉ** với lỗi tạm thời và operation có thể gọi lại an toàn; retry phải nằm trong tổng deadline.
- Không retry do bulkhead/queue quá tải chỉ để tăng thêm tải. Không retry POST tạo side effect nếu thiếu idempotency key.
- Khi `Mono.timeout` hủy subscription, upstream có thể đã xử lý xong thay đổi; cancel **không rollback** giao dịch ở provider.
- Giới hạn theo instance không phải toàn hệ thống. Chẳng hạn 5 replicas có pool 8 connections mỗi cái có thể tạo tổng khoảng 40 connections tới cùng một provider (thay đổi theo remote host và giao thức).
- Với token introspection/PDP đặc biệt quan trọng, không thử “fail open” chỉ để bảo vệ availability.
- Không log Bearer/refresh token, cookie, client secret, raw principal claims hoặc dữ liệu nhạy cảm. Dùng trace ID/correlation ID và tên downstream có tập giá trị hữu hạn.

## 8. Quan sát và điều chỉnh giới hạn bằng metrics

Khi Reactor Netty metrics, Actuator và Micrometer registry được bật đầy đủ, hãy đo:

| Metric/nhóm quan sát | Ý nghĩa |
| --- | --- |
| `reactor.netty.connection.provider.active.connections` | Socket active có sát pool max lâu không |
| `reactor.netty.connection.provider.idle.connections` | Socket còn sẵn sàng reuse |
| `reactor.netty.connection.provider.pending.connections` | Pending acquisition có tăng và không thoát không |
| Pool acquire duration và timeout/rejection count | Có nghẽn trước khi gọi provider không |
| HTTP client response time p50/p95/p99; 4xx/5xx | Provider chậm hay lỗi chức năng |
| 503 tại boundary; in-flight/cancel count | Fail-fast và release permit có hoạt động không |
| Server request latency p95/p99, error ratio | Ảnh hưởng cuối cùng tới người dùng |
| Queue và thread active của blocking scheduler | Có task xếp chờ quá lâu không |

Tên series xuất ra phụ thuộc Reactor Netty/Micrometer/version/registry và nhãn. Xác nhận metrics có số liệu thật; không suy đoán rằng chỉ thêm Actuator đã tự bật Prometheus endpoint. Tag theo `downstream=profile`, outcome, timeout stage hoặc status class; **không** tag mỗi username/token/URL có ID vì cardinality cao.

Cách chọn số:

1. Đo throughput đến từng upstream và latency trung bình, p95, p99 dưới tải bình thường và khi chậm.
2. Áp dụng **Little's Law** như một ước lượng cho hệ thống tương đối ổn định: `L ≈ λ × W`. Nếu trung bình 40 calls/s và thời gian trung bình 0,2 giây, khoảng 8 calls sẽ đang xử lý trung bình. Công thức dùng **mean**, không tự thay bằng p95 để tính chắc chắn.
3. Chọn pool và bulkhead từ mức tải thực, headroom cho burst và năng lực upstream; pending queue nhỏ giúp fail-fast thay vì giữ request vô vọng.
4. Load test khi provider cố ý chậm, mất kết nối, trả 5xx hoặc treo đọc body; quan sát memory, queue, socket, latency, throughput và recovery.
5. Thử nhiều replicas và xác nhận tổng connection/rate không vượt thỏa thuận với nhà cung cấp.

## 9. Ma trận thử nghiệm khi tích hợp thật

| Tình huống | Hành vi mong đợi | Kiểm tra thêm |
| --- | --- | --- |
| Request thiếu authentication | 401 | Không outbound call |
| Đã authenticated, upstream nhanh | 200 | Data đúng, connection được reuse |
| Upstream chậm hơn deadline | 503 | Permit release, không chờ vô hạn |
| Không connect được | 503 | TCP deadline áp dụng |
| Hết bulkhead permit | 503 nhanh | Không block event-loop |
| Hết connection nhưng pending còn chỗ | Đợi acquire tối đa thời hạn | Metrics pending tăng rồi giảm |
| Pending acquisition đầy | Lỗi nhanh | Queue được giới hạn |
| Client cancel | Giải phóng permit | Không leak in-flight |
| PDP/introspection lỗi | Không cấp quyền | Có lỗi/deny rõ nguyên nhân |
| Nhiều request đồng thời | Memory ổn, tail latency có giới hạn | Không retry storm |
| Nhiều instances | Tổng socket/rate trong ngân sách | Kiểm tra quota chung |

## 10. Sai lầm phổ biến

1. **Chỉ cấu hình `responseTimeout`:** request vẫn có thể chờ hàng đợi lấy connection quá lâu. Thêm `pendingAcquireTimeout` và outer deadline.
2. **Chỉ tăng `maxConnections`:** đẩy nghẽn sang downstream, tăng số socket. Đo khả năng xử lý của provider trước.
3. **Pending queue không giới hạn:** khi nghẽn, bộ nhớ và độ trễ có thể tiếp tục tăng. Đặt `pendingAcquireMaxCount` hữu hạn và thêm admission control.
4. **Đặt permit trước khi subscribe:** tạo Publisher mà chưa dùng đã chiếm slot. Dùng `Mono.defer`.
5. **Không trả permit khi cancel:** dễ dẫn đến hệ thống tự khóa sau nhiều timeout. Dùng `doFinally` và test cancellation.
6. **Chạy blocking SDK trên event-loop:** tách scheduler bounded và driver timeout.
7. **Coi 401/403/503 như nhau:** che mất lỗi hạ tầng hoặc khiến client xử lý sai.
8. **Fail open khi kiểm tra quyền không gọi được:** tạo lỗi phân quyền nghiêm trọng; phải fail closed.
9. **Không xem metric pending:** active connections sát trần chưa đủ giải thích; cần đo pending, acquire latency và 503.
10. **Áp pool/timeout vào nhầm `WebClient`:** introspector/JWK decoder có thể dùng client khác.
11. **Retry không có ngân sách:** tăng tải ngay khi provider suy yếu, kéo dài p99.
12. **Giả định cancel dừng blocking IO/rollback ở phía ngoài:** cần timeout thật của SDK và idempotency.

## Tài liệu tham khảo chính thức

- [Reactor Netty — HTTP Client: Connection Pool và Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Reactor Core — Schedulers API (boundedElastic)](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html)
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)

Khi thiết kế một ranh giới ngoài cho ứng dụng bảo mật reactive, phải đồng thời trả lời được: **chờ tối đa bao lâu, mở tối đa bao nhiêu kết nối, nhận tối đa bao nhiêu tác vụ, sẽ từ chối thế nào khi đầy, và kiểm chứng điều đó bằng số liệu nào**.
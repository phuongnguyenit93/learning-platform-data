# Đo độ trễ xác thực, phân quyền và lời gọi nhà cung cấp danh tính trong Spring Security WebFlux

## 1. Vì sao cần đo riêng từng giai đoạn?

Trong ứng dụng Spring Security dùng WebFlux, một yêu cầu HTTP có thể đi qua việc đọc Bearer token hoặc session, xác thực danh tính (authentication), quyết định quyền truy cập (authorization), rồi mới chạy nghiệp vụ. Một số cơ chế còn giao tiếp với nhà cung cấp danh tính (Identity Provider, IdP). Độ trễ tổng của endpoint không chỉ ra giai đoạn gây chậm; nếu chỉ nhìn `http.server.requests`, ta rất dễ tối ưu nhầm nơi.

Mục tiêu của bài là xác định đúng phạm vi từng phép đo, gắn metrics/traces vào luồng reactive, đọc được p50/p95/p99 và phân biệt chậm do ứng dụng với chậm do IdP, trong khi vẫn giữ nguyên hành vi bảo mật.

| Đại lượng | Điểm bắt đầu và kết thúc hợp lý | Giải thích |
| --- | --- | --- |
| HTTP end-to-end | Máy chủ bắt đầu xử lý request → hoàn tất response | Có cả security, handler, I/O, serialization; dùng để đối chiếu tổng thể. |
| Xác thực (`authentication`) | Đăng ký thực thi bước xác thực → nhận `Authentication`, lỗi hoặc kết thúc rỗng | Bao gồm kiểm tra credential/token và các phụ thuộc của đúng cơ chế đang dùng. |
| Phân quyền (`authorization`) | Thực thi `ReactiveAuthorizationManager.check(...)` → có quyết định, lỗi hoặc kết thúc rỗng | Đo chính sách của endpoint được gắn bộ đo; không mặc nhiên bao phủ method security. |
| Gọi IdP | Bắt đầu thao tác token introspection/token exchange/userinfo/JWK fetch → hoàn tất thao tác | Có thể bao gồm mạng, xử lý response, retry và timeout tùy vị trí instrument. |

Đối với ứng dụng **Resource Server xác thực JWT**, việc xác minh chữ ký thường thực hiện tại chỗ sau khi khóa công khai đã được tải và cache; không được giả định mỗi request đều gọi IdP. Với **opaque token introspection**, request thường phát sinh lời gọi mạng đến IdP nếu không có cache bổ sung. **OAuth2 Login/OIDC** lại có các bước trao đổi authorization code, lấy userinfo hoặc refresh token: đây là những điểm gọi IdP khác, xảy ra theo thời điểm của luồng đăng nhập/refresh chứ không nhất thiết trên mọi request API.

## 2. Chọn ranh giới đo để tránh số liệu sai

Dòng xử lý khái quát:

```text
Client request
  -> WebFlux/WebFilter chain
  -> xác thực: SecurityContext / Bearer token / ReactiveAuthenticationManager
       -> (nếu có) introspection, JWK retrieval hoặc lời gọi IdP
  -> phân quyền: ReactiveAuthorizationManager
  -> handler + database + API bên ngoài
  -> HTTP response
```

Các khoảng trên có thể **lồng nhau**: thời gian introspection nằm trong thời gian authentication, và cả hai nằm trong request nếu thực thi trong request đó. Vì vậy không cộng số đo IdP với số đo authentication rồi kết luận đó là tổng security; phép cộng sẽ tính trùng.

Đối với Reactor `Mono`/`Flux`, publisher thường *lazy*. Thời điểm tạo pipeline bằng `Mono.just(...)` hoặc gọi phương thức xây dựng pipeline không nhất thiết là lúc công việc thực sự chạy. Bắt đầu đồng hồ tại **subscription**, ghi nhận khi complete/error/cancel; tránh bắt đầu từ lúc assembly. Dùng `Mono.defer(...)` và `doFinally(...)` để đo cả đường thành công, lỗi và hủy subscription. Không dùng `block()` hoặc `Thread.sleep()` trên event-loop để “đo chính xác”; chúng phá vỡ đặc tính nonblocking và tạo ra độ trễ giả.

Quy ước đơn vị: Micrometer `Timer` ghi thời lượng bằng đơn vị cơ sở thích hợp và chuyển đổi ở hệ xuất metrics; với Prometheus thường thấy tên `..._seconds` và histogram buckets tính bằng giây. Luôn ghi rõ đơn vị trên dashboard.

## 3. Bắt đầu từ metrics có sẵn

Với Spring Boot 3.3 / Spring Security 6.x, có thể dùng Spring Boot Actuator, Micrometer và Prometheus:

```groovy
// build.gradle — dự án đã dùng Spring Boot dependency management
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

```yaml
# application.yml — phần quan sát; endpoint metrics cần được bảo vệ tại môi trường thật
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

- Quan sát `http.server.requests` trước để xác định route, status, traffic và latency tổng. Hãy nhóm theo URI template, tránh route thô chứa ID.
- Với `WebClient` tự tạo, dùng `WebClient.Builder` được Spring Boot inject để nhận HTTP client observation `http.client.requests`; `WebClient.create(...)` tự tạo có thể bỏ qua cấu hình instrumentation của Boot. Không suy luận rằng mọi client HTTP nội bộ do Spring Security tạo ra đều sử dụng `WebClient.Builder` của ứng dụng.
- Cần đo **ranh giới bảo mật** cụ thể thì thêm `Timer` riêng vào component đang xử lý xác thực/phân quyền/introspection. HTTP client metric và timer của component trả lời các câu hỏi khác nhau; cùng một outbound request có thể góp mặt trong cả hai.

Ví dụ sử dụng HTTP client được Boot instrument tự động (dành cho lời gọi ứng dụng tự quản lý):

```java
@Bean
WebClient idpWebClient(WebClient.Builder builder) {
    return builder.baseUrl("https://identity.example.org").build();
}
```

Đo HTTP client qua cách này chỉ bao phủ các request thực sự được gửi bằng `idpWebClient`. Với token introspection do Spring Security quản lý, hãy instrument `ReactiveOpaqueTokenIntrospector` như ví dụ tiếp theo để biết thời gian của chính thao tác đó.

## 4. Mã Java đo riêng authorization và IdP introspection

Ví dụ sau là **một tệp Java hoàn chỉnh về mặt cấu trúc**, dùng Spring Boot 3.3 + Spring Security 6.x và các dependency ở trên. Tệp `ReactiveSecurityLatencyConfig.java` cấu hình bảo vệ `/reports/**` bằng scope `reports.read`; đồng thời đo thời gian quyết định quyền truy cập và thời gian thực hiện opaque-token introspection. URI và thông tin kết nối IdP được cung cấp qua cấu hình của ứng dụng tại thời gian chạy.

```java
package example.security;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Function;
import java.util.function.Supplier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorityReactiveAuthorizationManager;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityLatencyConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, MeterRegistry meters) {

        ReactiveAuthorizationManager<AuthorizationContext> rule =
                AuthorityReactiveAuthorizationManager.hasAuthority(
                        "SCOPE_reports.read");

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/reports/**")
                        .access((authentication, context) ->
                                measure(
                                        meters,
                                        "authorization",
                                        decision -> decision.isGranted()
                                                ? "granted" : "denied",
                                        () -> rule.check(authentication, context)))
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }

    @Bean
    ReactiveOpaqueTokenIntrospector opaqueTokenIntrospector(
            MeterRegistry meters,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
                    String introspectionUri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
                    String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
                    String clientSecret) {

        ReactiveOpaqueTokenIntrospector delegate =
                new SpringReactiveOpaqueTokenIntrospector(
                        introspectionUri, clientId, clientSecret);

        return token -> measure(
                meters,
                "idp_introspection",
                principal -> "valid",
                () -> delegate.introspect(token));
    }

    // Chỉ sử dụng khi đã gắn manager trả về vào luồng xác thực thật.
    static ReactiveAuthenticationManager timedAuthenticationManager(
            ReactiveAuthenticationManager delegate, MeterRegistry meters) {
        return authentication -> measure(
                meters,
                "authentication",
                result -> "authenticated",
                () -> delegate.authenticate(authentication));
    }

    private static <T> Mono<T> measure(
            MeterRegistry meters,
            String stage,
            Function<? super T, String> classifyValue,
            Supplier<Mono<T>> operation) {

        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(meters);
            AtomicReference<String> outcome =
                    new AtomicReference<>("empty");

            return Mono.defer(operation)
                    .doOnNext(value ->
                            outcome.set(classifyValue.apply(value)))
                    .doOnError(error -> outcome.set("error"))
                    .doFinally(signal -> {
                        String finalOutcome = signal == SignalType.CANCEL
                                ? "cancel" : outcome.get();

                        sample.stop(Timer.builder("security.stage.duration")
                                .description("Reactive security stage latency")
                                .tag("stage", stage)
                                .tag("outcome", finalOutcome)
                                .publishPercentileHistogram()
                                .register(meters));
                    });
        });
    }
}
```

Giải thích các điểm quan trọng:

1. `Mono.defer(...)` bắt đầu `Timer.Sample` tại subscription. Mỗi subscription có sample và `AtomicReference` riêng; nhiều request đồng thời không dùng chung trạng thái đo.
2. `doOnNext` phân loại kết quả: `authorization` là `granted`/`denied`; introspection thành công là `valid`; authentication thành công là `authenticated`. `doOnError` đo lỗi, `doFinally` bao gồm cả `cancel`. `empty` có nghĩa publisher không phát giá trị; với `ReactiveAuthenticationManager` đây có thể là “không hỗ trợ loại Authentication”, **không** nên tự đổi thành lỗi mật khẩu.
3. `delegate` thực thi chính sách hoặc introspection gốc. Bọc bằng timer không được đổi quyết định hay nuốt exception. Không bao giờ gắn token, username, `sub`, URL có query nhạy cảm hay exception message làm metric tag.
4. `opaqueTokenIntrospector` là bean mà Resource Server sử dụng cho luồng opaque token. Do đó `idp_introspection` đo operation thực sự; nó thường là một phần của authentication. Phương thức `timedAuthenticationManager` là cách bọc manager **khi ứng dụng chủ động cấu hình manager đó vào filter/flow xác thực**; chỉ khai báo một method hoặc bean mà framework không dùng sẽ không tạo metric authentication. Ví dụ đang chạy chỉ gắn trực tiếp đo authorization và introspection.
5. `publishPercentileHistogram()` tạo các bucket để tính percentile trên Prometheus; việc tạo histogram có chi phí bộ nhớ và time series. Với vài giá trị `stage`/`outcome` cố định như trên chi phí kiểm soát được, nhưng cần đánh giá tài nguyên trước khi áp dụng rộng.

Để cấu hình introspection cho đoạn Java, dùng các thuộc tính `spring.security.oauth2.resourceserver.opaquetoken.introspection-uri`, `client-id` và `client-secret` (đặt secret qua secret manager/biến môi trường). Spring sẽ sử dụng cấu hình này khi tạo `ReactiveOpaqueTokenIntrospector`; với bean tùy biến ở ví dụ, các giá trị được inject vào constructor. URI phải trỏ đến endpoint introspection hợp lệ của IdP; nếu không có IdP thật, ứng dụng không thể xác thực opaque token thật.

**Giới hạn quan sát:** lớp trên không đo mọi authentication mechanism. Với JWT hãy instrument `ReactiveJwtDecoder.decode(...)` hoặc manager của pipeline JWT tương ứng; với OAuth2 Login hãy đo đúng token-response client, userinfo client hoặc bước refresh token. Khi instrument `@PreAuthorize`/method security, dùng một ranh giới khác để tách khỏi HTTP authorization. Mỗi công cụ đo phải được lắp đúng nơi component thực sự được gọi.

## 5. Phân biệt thời gian gọi IdP với thời gian authentication

IdP có nhiều endpoint và đặc điểm khác nhau:

| Dòng xử lý | Lời gọi có thể xảy ra | Vị trí nên đo | Cách diễn giải |
| --- | --- | --- | --- |
| API + opaque Bearer token | Introspection endpoint | `ReactiveOpaqueTokenIntrospector.introspect` | Độ trễ kiểm tra token qua mạng; thất bại mạng khác với token bị từ chối. |
| API + JWT | JWKS fetch/refresh khi cache thiếu, miss hoặc hết hạn | Decoder và client tải khóa | Đa số request có thể xác minh offline; tách “cache warm” và “cache miss”. |
| OAuth2 Login/OIDC | Authorization-code exchange, userinfo | Reactive OAuth2 token client / OIDC user service thực tế | Chủ yếu trên callback login; không so trực tiếp với request API thông thường. |
| Refresh token | Token endpoint | Reactive authorized-client provider/token-response client | Phân biệt refresh và xác thực request kế tiếp. |

Nếu cần đo chính xác thời gian mạng tới IdP, instrument client thực sự được dùng và xác định phép đo bắt đầu/kết thúc ở đâu (ví dụ nhận response headers hay tiêu thụ xong body). Bộ đo `introspect` ở trên bao phủ **toàn bộ thao tác introspection**, gồm xử lý phản hồi. Nếu có retry, thời gian đo có thể gồm nhiều lần thử và backoff; cần thêm counter cho attempts/timeouts để biết nguyên nhân.

Với Reactor Netty/WebClient, xem thêm connection pool, DNS/TLS/connect latency và timeout. P95 IdP cao có thể do pool chờ kết nối, mạng, giới hạn tốc độ, retry hoặc chính IdP. Đừng lập luận “IdP chậm” chỉ từ một timer tổng khi chưa kiểm tra các chặng này.

## 6. Xem metrics và tính p95 đúng cách

Sau khi gửi traffic đủ đại diện, xem `/actuator/prometheus` trên môi trường được cấp quyền. Tên metric từ mã ở trên thường có dạng `security_stage_duration_seconds_count`, `..._sum` và `..._bucket` khi dùng Prometheus registry; mỗi series có nhãn `stage` và `outcome`. Ví dụ:

```promql
# Tốc độ gọi introspection, tính theo số lần/giây
sum(rate(security_stage_duration_seconds_count{
  stage="idp_introspection"
}[5m]))

# Trung bình thời gian introspection, tính bằng giây
sum(rate(security_stage_duration_seconds_sum{
  stage="idp_introspection"
}[5m]))
/
sum(rate(security_stage_duration_seconds_count{
  stage="idp_introspection"
}[5m]))

# p95 authorization, tính từ histogram buckets
histogram_quantile(
  0.95,
  sum by (le) (
    rate(security_stage_duration_seconds_bucket{
      stage="authorization"
    }[5m])
  )
)
```

PromQL minh họa ở đây gộp mọi `outcome`; dashboard thực tế nên so sánh `granted`/`denied` và `error` riêng khi cần. Histogram percentile dựa trên cửa sổ quan sát và bucket, là xấp xỉ; p99 từ tập rất ít mẫu dễ dao động. Tránh lấy trung bình các giá trị p95 của từng instance để ra “p95 toàn hệ thống”; hãy gộp bucket theo `le` rồi tính `histogram_quantile`.

Bộ chỉ số tối thiểu nên có: request rate, error/deny rate, p50/p95/p99 theo stage, độ trễ IdP, số timeout/retry, độ trễ tổng HTTP, số request đang thực thi và dấu hiệu event-loop/connection pool bị quá tải. Chỉ tạo dimension hữu hạn như `stage`, `outcome`, `provider` với tên provider cho phép; không tạo per-user/per-token series.

## 7. Distributed tracing giúp tìm request chậm

Metrics trả lời “hệ thống chậm ở đâu, với tỷ lệ bao nhiêu”; tracing trả lời “request cụ thể chậm vì chặng nào”. Khi có Micrometer Observation và OpenTelemetry/Zipkin/OTLP được cấu hình, dùng trace/span để ghép đường vào ứng dụng và outbound calls. Một trace hữu ích có thể hiển thị:

```text
http.server GET /reports/{id}           260 ms
  authn/opaque-introspection            185 ms
    outbound POST /oauth2/introspect    179 ms
  authz/check-scope                       2 ms
  handler + downstream                   65 ms
```

**Các số trên chỉ minh họa**, không phải output của Java ở trên. Đường thực thi có thể lồng nhau, có khoảng trống hoặc chạy song song. Không cộng độ dài span con với span cha; phân tích critical path và thời gian độc quyền nếu muốn gán nguyên nhân.

Trong reactive pipeline, trace context được truyền theo Reactor Context khi instrumentation được cấu hình đúng. Không trông cậy vào `ThreadLocal`/MDC thủ công xuyên mọi `publishOn` hay `flatMap`; thread có thể thay đổi. Cũng không đưa Bearer token, raw credential hoặc thông tin cá nhân vào tên span/attribute.

## 8. Thiết kế kịch bản kiểm thử phép đo

Chạy cùng một route với lưu lượng có kiểm soát và quan sát đồng thời HTTP, security metrics và traces. Các ca cần phân biệt:

1. **Token hợp lệ, scope đủ:** introspection thành công; authorization `granted`; phản hồi handler thành công (nếu handler hoạt động đúng). Kiểm tra mỗi lần operation thực thi có đúng sample.
2. **Token hợp lệ nhưng thiếu scope:** introspection có thể thành công; authorization `denied`; endpoint thường trả `403`. Không gắn trạng thái “error” cho quyết định deny thông thường.
3. **Token không hợp lệ/hết hạn:** introspection có thể kết thúc bằng lỗi xác thực, client thường nhận `401`; quyền truy cập có thể không được đánh giá, vì pipeline đã dừng trước authorization. Phân biệt lỗi token với outage của IdP.
4. **IdP phản hồi chậm, timeout hoặc 5xx:** `idp_introspection` tăng latency hoặc `error`; request có thể lỗi, tùy chính sách xử lý. Đo cả timeout, retry và connection pool; không tắt kiểm tra bảo mật để đạt latency.
5. **Request bị client hủy:** `doFinally(CANCEL)` phải ghi nhận `cancel`. Nếu có retry, `timeout` hoặc `cache` trong Reactor, vị trí đặt phép đo quyết định thời gian chờ nào được tính.
6. **JWT cold/warm cache (nếu dùng JWT):** kiểm tra lần tải JWK ban đầu, cache hit, refresh/rotation; không quy mọi lần xác thực JWT thành một HTTP call tới IdP.

Với test load, duy trì cùng tỷ lệ token hợp lệ/không hợp lệ, kích thước JWT, tỷ lệ cache hit, mức concurrency và cấu hình connection pool khi so sánh trước/sau. Warm-up JVM, Reactor Netty và JWK cache trước khi kết luận về steady-state. Test đường lỗi và đo số sample để tránh chỉ thu thập request thành công.

## 9. Diễn giải và xử lý nút thắt

| Dấu hiệu | Giả thuyết cần kiểm chứng | Hướng xử lý |
| --- | --- | --- |
| HTTP p95 cao, authn/authz/IdP thấp | Handler, DB, downstream, serialization | Xem trace, kết nối và thread scheduling. |
| Authentication p95 cao, IdP introspection cũng cao | Chờ mạng/IdP, timeout, retry, pool | Kiểm tra p95 outbound, connect/TLS và giới hạn dịch vụ; đánh giá chiến lược token phù hợp yêu cầu thu hồi. |
| Authorization p95 cao | Chính sách tính toán nặng, gọi DB/API trong rule | Đo từng lookup, tối ưu truy cập I/O theo reactive, kiểm tra caching/quyền dữ liệu. |
| JWT latency chỉ tăng khi rotate JWK | Cache miss, tải JWKS hoặc key rotation | Kiểm tra cache, cấu hình mạng, timeout và quy trình rotation. |
| Chỉ p99 tăng khi concurrency cao | Queueing, pool cạn, blocking event-loop, GC | Kiểm tra event-loop, BlockHound khi phù hợp, connection pool và hồ sơ CPU/GC. |

Không đưa phép gọi chặn như JDBC blocking, `RestTemplate` sync, `Thread.sleep` hay `block()` vào event-loop. Nếu buộc phải dùng thư viện blocking, cần cô lập phù hợp (chẳng hạn `Schedulers.boundedElastic()`), đo riêng chi phí chờ và lập kế hoạch chuyển sang API nonblocking. Cache kết quả xác thực/phân quyền phải có chính sách TTL, thu hồi, phạm vi người dùng và tính nhất quán phù hợp; tối ưu latency không được làm yếu kiểm soát truy cập.

## 10. Các lỗi đo đạc thường gặp

- **Bắt đầu timer lúc tạo `Mono`:** ghi cả thời gian trước subscription hoặc bỏ sót retry; phải đo tại `defer` và hiểu operator nằm trước/sau `retry`.
- **Chỉ đo `doOnSuccess`:** không bao phủ error và cancel; `Mono.doOnSuccess` còn được gọi với `null` khi complete rỗng. Dùng `doFinally` và phân loại kết quả rõ ràng.
- **Nhầm `401`, `403` và IdP outage:** 401 thường liên quan thiếu/sai xác thực, 403 là đã xác thực nhưng bị từ chối quyền; lỗi hạ tầng IdP có cách ánh xạ riêng. Không gộp chúng vào một “authentication failed” metric.
- **Gắn timer ở manager không được framework dùng:** không có sample hoặc thiếu toàn bộ request; xác minh path wiring thật của JWT, opaque token và OAuth2 login.
- **Gắn raw URL, user ID, token, scope động làm tag:** bùng nổ cardinality và có nguy cơ rò dữ liệu. Giới hạn nhãn, che bí mật và không log Authorization header.
- **Lấy tổng các timer lồng nhau:** double count thời gian introspection. Dùng trace để xem quan hệ cha–con, không cộng tùy ý.
- **Diễn giải một mẫu đơn lẻ như SLO:** percentile cần cửa sổ, khối lượng mẫu và phân đoạn traffic phù hợp; đo cả throughput, error rate và concurrency.
- **Bật endpoint quan sát công khai:** metrics/traces có thể tiết lộ tên route/hạ tầng. Phải kiểm soát quyền truy cập, retention, sampling và chi phí lưu trữ.

## 11. Tiêu chí hoàn thành

Một hệ thống đo đạt yêu cầu khi: mỗi stage có ranh giới và đơn vị được ghi rõ; timer chạy tại subscription và dừng trên success/error/cancel; các nhãn an toàn, hữu hạn; có số liệu HTTP tổng để đối chiếu; phân biệt JWT offline với introspection và các bước OAuth2 login; có test cho grant/deny/invalid token/IdP timeout; và dashboard p95 có đủ lưu lượng, không đếm trùng span/timer.

**Tài liệu gốc để đối chiếu API:** [Spring Security — WebFlux authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html), [Spring Security — reactive OAuth2 resource server](https://docs.spring.io/spring-security/reference/reactive/oauth2/), [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html), [Spring Framework — Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html).
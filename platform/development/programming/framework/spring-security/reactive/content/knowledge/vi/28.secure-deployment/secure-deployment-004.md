# Giới hạn quyền của tài khoản dịch vụ và access token trong Spring Security WebFlux

## 1. Bối cảnh, mục tiêu và kết quả cần đạt

Trong hệ thống Spring Security **reactive** (WebFlux), nhiều lời gọi API không xuất phát từ trình duyệt hoặc người dùng cuối mà từ scheduler, worker, pipeline CI/CD, microservice và tác vụ nền. Các thành phần này phải có **danh tính máy** (*service account/workload identity*) và **quyền tối thiểu**. Một service account chỉ nên được phép thực hiện đúng nghiệp vụ được giao, trong môi trường được giao, trên API và tài nguyên được giao, bằng access token có thời hạn thích hợp.

Ví dụ nhất quán trong bài:

- `report-reader-prod` chỉ được gọi `GET /api/reports/**` với scope `reports.read`.
- `job-runner-prod` chỉ được gọi `POST /api/jobs` với scope `jobs.submit`.
- `billing-worker-prod` cần quyền thanh toán riêng và không được mặc nhiên sử dụng endpoint báo cáo/job.
- Một caller có token đúng chữ ký nhưng sai `aud`, thiếu scope, sai client identity hoặc vượt tenant đều phải bị từ chối theo đúng lớp kiểm tra.

Bảo vệ được thiết kế theo nhiều lớp:

~~~text
Workload -> xác thực với Authorization Server / IdP
         -> nhận access token giới hạn issuer/audience/scope/expiry
         -> kết nối TLS đến Spring WebFlux API
         -> Resource Server kiểm tra token thật
         -> SecurityWebFilterChain kiểm tra route/method và authority
         -> policy xác minh service identity
         -> service/domain kiểm tra tenant, đối tượng và hành động
         -> xử lý nghiệp vụ hoặc trả 401/403 phù hợp
~~~

Một access token hợp lệ về mặt chữ ký **không** tự động cho quyền thực hiện mọi thao tác. Mọi API có thể bị gọi trực tiếp, bỏ qua UI và các giới hạn mà caller tự áp đặt; quyết định cuối cùng phải nằm ở **server**.

## 2. Hiểu đúng service account, OAuth2 client và access token

| Thành phần | Ý nghĩa | Sai lầm cần tránh |
| --- | --- | --- |
| Service account / workload identity | Danh tính của tiến trình, workload hoặc dịch vụ | Dùng chung một tài khoản admin cho mọi dịch vụ |
| OAuth2 client registration | `client_id`, cơ chế xác thực client, grant và scope được phê duyệt | Coi `client_id` là secret hoặc chỉ dựa vào client ID tự khai |
| Client credentials grant | Máy lấy access token bằng cách xác thực với Authorization Server, thường không có người dùng tham gia | Dùng mật khẩu người dùng hoặc tài khoản nhân viên cho daemon |
| Access token | Quyền truy cập hạn chế tại resource server | Xem nó là “vé vĩnh viễn”, hoặc dùng ID token thay access token |
| Scope | Phạm vi quyền do authorization server cấp, ví dụ `reports.read` | Coi scope là đủ để bỏ qua quyền tenant/resource |
| Role/authority | Mô hình quyền mà resource server áp dụng | Tự đồng nhất scope với mọi role nội bộ |
| `iss`, `aud`, `exp`, `nbf` | Issuer, API đích, hạn sử dụng, thời điểm bắt đầu hiệu lực | Chỉ decode JWT Base64 mà không validate |
| `client_id`, `azp`, `sub` | Claim liên quan client/subject tùy nhà cung cấp | Giả định các claim luôn tồn tại và có cùng ý nghĩa |

Với **OAuth2 client credentials**, máy xác thực trực tiếp với IdP để nhận access token thuộc quyền của chính client. Token thường dùng dạng bearer: người chiếm được token có thể gọi API trong thời gian token còn hiệu lực, trừ khi hệ thống áp dụng các ràng buộc bổ sung như mTLS/DPoP hoặc cơ chế thu hồi. Do đó **TTL ngắn + scope nhỏ + audience hẹp + bí mật được bảo vệ** là bộ nền tảng.

Mỗi IdP có hợp đồng claim riêng. Ví dụ trong bài dùng JWT chứa `client_id` do issuer ký; nếu IdP dùng `azp`, `sub` hoặc claim khác, phải xác nhận ngữ nghĩa và cách issuer cấp token trước khi viết policy. Tuyệt đối không dựa vào `X-Client-Id`, query parameter, JSON body hoặc claim tự decode trước khi xác minh chữ ký làm bằng chứng caller có quyền.

Access token có thể là **JWT** hoặc **opaque token**. JWT cần decoder, thuật toán và JWKS tin cậy; opaque token cần introspection tin cậy. Spring Security WebFlux hỗ trợ cả hai theo cấu hình resource server tương ứng. Ví dụ Java phần sau dành cho JWT.

## 3. Ma trận quyền tối thiểu và mô hình đe dọa

Trước khi tạo service account, liệt kê **chủ thể – hành động – tài nguyên – môi trường – thời hạn**. Mỗi quyền phải có lý do nghiệp vụ và chủ sở hữu rõ ràng.

| Workload | API cho phép | Scope cần có | Điều kiện bổ sung |
| --- | --- | --- | --- |
| `report-reader-prod` | GET `/api/reports/**` | `reports.read` | Chỉ báo cáo được phép, đúng tenant |
| `job-runner-prod` | POST `/api/jobs` | `jobs.submit` | Chỉ job type và tenant được cấp |
| `billing-worker-prod` | API thanh toán được phê duyệt | `payments.process` | Giới hạn loại giao dịch và tài khoản |
| `report-reader-staging` | API staging | `reports.read` tại staging | Không truy cập prod dù trùng tên scope |
| Workload chưa khai báo | Không endpoint nào | Không có | Bị từ chối mặc định |

Dưới đây là những lớp giới hạn phải có, không lớp nào thay thế hoàn toàn lớp khác:

1. **Workload identity**: danh tính riêng cho mỗi ứng dụng hoặc chức năng. Khi hai chức năng có mức nhạy cảm khác nhau, tách danh tính/registration. Không chia sẻ super-account.
2. **Môi trường**: prod, staging và dev tách tài khoản, endpoint issuer, audience, secret, chính sách. CI thử nghiệm không được nhận secret prod mặc định.
3. **Phương thức và route**: phân biệt GET/POST/PATCH/DELETE. Một client đọc báo cáo không cần và không được sở hữu quyền sửa/xóa.
4. **Scope nghiệp vụ**: scope nhỏ như `reports.read` hoặc `jobs.submit`; tránh `api.full_access`, `admin`, `*` nếu không có nhu cầu thật và phê duyệt rõ.
5. **Audience**: access token của Resource Server A không thể dùng tại Resource Server B. Kiểm `aud` ngay cả khi JWT được ký bởi issuer chung.
6. **Dữ liệu**: quyền với `tenant-A` không mở quyền với `tenant-B`. Phải xác minh quyền trên đối tượng cụ thể ở service/repository/policy engine.
7. **Vòng đời**: token ngắn hạn, có cách thu hồi, rotation credential, offboarding account và audit truy cập.

Ví dụ kẻ tấn công chiếm access token của `report-reader-prod`: nếu token chỉ có scope đọc, audience đúng API báo cáo, TTL ngắn và quyền theo tenant, thiệt hại được giới hạn. Nếu đó là token dùng chung có quyền `admin` trên nhiều API, một sự cố nhỏ có thể thành sự cố toàn hệ thống.

**Deny by default** là yêu cầu cốt lõi: endpoint mới, hành động chưa được phê duyệt hoặc workload không nằm trong allowlist phải bị từ chối; không đổi `denyAll()` thành `permitAll()` để chữa tạm 403.

## 4. Validate access token: authentication trước, authorization sau

Spring Resource Server chỉ nên tạo `Authentication` tin cậy sau khi access token được xác minh. Với JWT cần xét:

- **Chữ ký/thuật toán**: chỉ dùng thuật toán, khóa, JWKS của issuer tin cậy. Không tin header `alg` hay `jku` của token để tự đổi nơi lấy khóa.
- **Issuer (`iss`)**: chỉ nhận token của IdP được cấu hình cho môi trường hiện tại.
- **Audience (`aud`)**: token phải định danh chính API cần bảo vệ. Đây là điều kiện thường bị bỏ sót nếu chỉ cấu hình issuer.
- **Thời gian (`exp`, `nbf`)**: token còn hạn và đã tới thời điểm sử dụng; xác định clock skew rõ ràng.
- **Scope/authorities**: issuer cấp đúng scope được cấp phép; server ánh xạ scope sang authority theo contract (mặc định thường có tiền tố `SCOPE_`).
- **Caller identity**: claim xác thực như `client_id` có thể giúp ràng buộc caller cụ thể, nhưng chỉ theo ngữ nghĩa nhà phát hành thật.
- **Đối tượng nghiệp vụ**: policy server kiểm tra quyền tenant/resource; JWT không tự cho phép hành động chỉ vì tồn tại một claim.
- **Loại token**: ID token OIDC không được dùng thay access token của API. Không dùng refresh token làm HTTP Bearer đến resource server.

Khi thiếu Bearer token hoặc token không thể xác thực, thông thường HTTP trả **401 Unauthorized**, có challenge Bearer. Khi token được xác thực nhưng thiếu quyền, thường trả **403 Forbidden**. Đừng biến lỗi claim/issuer/signature thành anonymous success hoặc fallback `permitAll`. Với resource được ẩn, một số API có thể trả 404 theo hợp đồng tránh lộ tồn tại tài nguyên; phải có policy và test nhất quán.

Một JWT đã được phát hành có thể tiếp tục hợp lệ cho đến `exp` dù client secret vừa được xoay hoặc tài khoản bị khóa, tùy cách IdP/resource server xử lý thu hồi. Cần chọn TTL, denylist theo `jti`, introspection hoặc token revocation model thích hợp. Không mặc định “xóa secret” sẽ tự hủy mọi JWT đã phát.

## 5. Mẫu Resource Server cho Spring Security WebFlux

Ví dụ dùng Java 17+, Spring Boot 3.3.x, Spring Security 6.x. Nó chứng minh đồng thời **issuer + audience + scope + client identity + route/method**. Đặt trong file `src/main/java/example/security/MachineApiSecurity.java` của ứng dụng có `spring-boot-starter-webflux`, `spring-boot-starter-security` và `spring-boot-starter-oauth2-resource-server`.

~~~java
package example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;

@Configuration
@EnableWebFluxSecurity
public class MachineApiSecurity {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
            // Chỉ tắt CSRF khi toàn bộ API dùng bearer header,
            // không dùng cookie/session đăng nhập trong browser.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .access(allowOnly("report-reader-prod", "reports.read"))
                .pathMatchers(HttpMethod.POST, "/api/jobs")
                    .access(allowOnly("job-runner-prod", "jobs.submit"))
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    private static ReactiveAuthorizationManager<AuthorizationContext>
        allowOnly(String expectedClientId, String requiredScope) {

        return (authentication, context) -> authentication
            .map(auth -> {
                if (!(auth instanceof JwtAuthenticationToken jwtAuth)
                        || !jwtAuth.isAuthenticated()) {
                    return new AuthorizationDecision(false);
                }

                Jwt jwt = jwtAuth.getToken();  // JWT đã được decoder xác minh
                boolean correctClient = expectedClientId.equals(
                    jwt.getClaimAsString("client_id"));
                String requiredAuthority = "SCOPE_" + requiredScope;
                boolean correctScope = jwtAuth.getAuthorities().stream()
                    .anyMatch(a -> requiredAuthority.equals(
                        a.getAuthority()));

                return new AuthorizationDecision(correctClient && correctScope);
            })
            .defaultIfEmpty(new AuthorizationDecision(false));
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> requiredAudience = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Required audience is missing", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            requiredAudience));
        return decoder;
    }
}
~~~

Cấu hình minh họa:

~~~yaml
app:
  security:
    issuer: https://identity.example.test/issuer
    audience: reports-jobs-api
~~~

Các domain/giá trị trên chỉ là mẫu; khi triển khai phải điền issuer thực, audience thật và cấu hình TLS/JWK discovery phù hợp.

Cách đọc cấu hình:

- `GET /api/reports/**` chỉ chấp nhận JWT từ issuer đã khai báo, có audience đúng, `client_id=report-reader-prod` và authority `SCOPE_reports.read`.
- `POST /api/jobs` yêu cầu `client_id=job-runner-prod` và `SCOPE_jobs.submit`.
- `anyExchange().denyAll()` từ chối method/route khác, kể cả endpoint mới. Nếu cần health endpoint, khai báo matcher ngoại lệ có chủ ý và giới hạn dữ liệu công bố.
- `allowOnly` kiểm tra `JwtAuthenticationToken`; ứng dụng sử dụng opaque token phải có chính sách tương đương trên principal của opaque token. Không tự bỏ điều kiện `client_id` khi IdP chưa cung cấp claim.
- `JwtValidators.createDefaultWithIssuer` cung cấp kiểm tra issuer và các kiểm tra mặc định, còn validator bổ sung bắt buộc audience đúng. Việc token có chữ ký được xác minh bởi decoder với nguồn khóa tin cậy.
- Scope `reports.read` thường chuyển thành `SCOPE_reports.read` bằng converter mặc định. Nếu IdP dùng claim khác hoặc format khác, cấu hình converter theo hợp đồng đã xác minh và kiểm thử; không tự tin mọi token đều có `scope`.
- `csrf(...disable)` thích hợp cho API thuần bearer và không dùng credential tự động kèm request từ browser. Với ứng dụng hỗn hợp browser/session, cần duy trì CSRF ở phần dùng cookie và tách cấu hình SecurityWebFilterChain theo matcher phù hợp.

Ràng buộc `client_id` này là ví dụ cho IdP phát claim đó vào **access token**. Ở nhà cung cấp khác, có thể cần claim khác, claim-to-authority mapping hoặc policy engine; không lấy tên service từ request body/header để quyết định.

## 6. Outbound client credentials: chỉ gửi token đúng API đích

Một microservice có thể vừa là Resource Server cho inbound traffic vừa là OAuth2 Client khi gọi outbound. **Hai vai trò khác nhau**: Resource Server kiểm token incoming; OAuth2 Client lấy token cho destination đúng quyền.

Một job chạy nền dùng grant `client_credentials` và registration `reports-reader` chỉ xin `reports.read`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          corporate-idp:
            token-uri: https://identity.example.test/oauth2/token
        registration:
          reports-reader:
            provider: corporate-idp
            authorization-grant-type: client_credentials
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            scope: reports.read
~~~

Biến môi trường là mẫu cấu hình. Trong triển khai thật, nạp secret từ secret manager hoặc cơ chế workload identity/federation do nền tảng và IdP hỗ trợ; tránh commit secret vào Git, baked container image hoặc in cấu hình secrets ra log. Authorization Server phải giới hạn scope tối đa mà client được phép xin: `scope=*` trong request của kẻ tấn công không được tự nâng quyền.

Với ứng dụng **không có browser session** (cron/worker), dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`. File `src/main/java/example/security/OutboundMachineClient.java` sau yêu cầu `spring-boot-starter-oauth2-client`:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OutboundMachineClient {

    @Bean
    ReactiveOAuth2AuthorizedClientManager machineAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService clients) {
        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, clients);
        manager.setAuthorizedClientProvider(
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build());
        return manager;
    }

    @Bean
    WebClient reportsWebClient(
            ReactiveOAuth2AuthorizedClientManager machineAuthorizedClientManager) {
        var oauth =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                machineAuthorizedClientManager);
        return WebClient.builder()
            .baseUrl("https://reports-api.example.test")
            .filter(oauth)
            .build();
    }
}
~~~

Để dùng registration cụ thể **chỉ khi cần**, gọi từ một service đã inject WebClient:

~~~java
// Đoạn method trong service có trường WebClient reportsWebClient.
// Import reactor.core.publisher.Mono và WebClient ở class chứa method.
public Mono<String> readDailyReport(WebClient reportsWebClient) {
    return reportsWebClient.get()
        .uri("/api/reports/daily")
        .attributes(
            org.springframework.security.oauth2.client.web.reactive
                .function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction
                .clientRegistrationId("reports-reader"))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

Đoạn cuối là **một method minh họa**, không phải file Java độc lập. Trong code thực tế có thể import static method `clientRegistrationId` để tránh tên dài. Một WebClient được gắn authorization filter không có nghĩa mọi URL đều được phép nhận token; cố định đích gọi, tránh cho caller kiểm soát URI tuyệt đối hoặc redirect làm lộ header. Không cấu hình default registration có quyền rộng cho WebClient dùng chung mọi destination. Định nghĩa một registration/API riêng khi các downstream cần scopes hoặc audience khác nhau.

Tránh tự động chuyển tiếp Bearer token inbound ra outbound. Token của người dùng/dịch vụ A có thể sai audience tại dịch vụ B. Nếu thật sự cần truyền quyền “on behalf of” người dùng, dùng token exchange hoặc cơ chế ủy quyền chính thức từ IdP để nhận token mới giới hạn subject/audience/scope; không giả định token relay thuần là an toàn.

## 7. Authorization theo dữ liệu và Reactor Context

Security WebFlux quyết định quyền ở HTTP layer, nhưng nghiệp vụ phải xét cả **resource ownership**. Ví dụ:

~~~text
POST /api/jobs
Body: { "tenantId": "tenant-B", "type": "EXPORT" }

Verified JWT:
  client_id = job-runner-prod
  scope     = jobs.submit
  tenant    = tenant-A
  aud       = reports-jobs-api

HTTP-level: caller hợp lệ để POST /api/jobs
Domain-level: từ chối vì caller không có quyền trên tenant-B
~~~

Không tin `tenantId` từ body để chứng minh quyền. Tầng service phải đối chiếu claims đã xác minh với tenant/ACL/policy store do server kiểm soát, đồng thời giới hạn job type, mức dữ liệu và các side effect. Nên đặt kiểm tra gần thao tác đọc/ghi dữ liệu để tránh **IDOR / broken object-level authorization**. Với thao tác có nhiều bước, cần tránh race giữa kiểm tra quyền và ghi dữ liệu nếu trạng thái có thể thay đổi.

Với reactive processing, principal/security context đi qua **Reactor Context**. Không đọc nhầm `SecurityContextHolder` dựa vào ThreadLocal rồi cho rằng danh tính sẽ được bảo toàn trên mọi `flatMap`, `publishOn` hoặc tác vụ async. Dùng `ReactiveSecurityContextHolder` hoặc argument injection từ Spring Security trong phạm vi phù hợp; kiểm tra trường hợp Publisher subscribe ngoài request scope. Nếu dùng `@EnableReactiveMethodSecurity` và `@PreAuthorize`, cần test đúng biểu thức và kiểu `Mono`/`Flux` trả về, tránh đánh đồng method-level security với validation thực tế của tenant/resource.

Một token được xác thực khi mở SSE/stream dài **không** mặc nhiên được kiểm lại trên mỗi phần tử. Nếu chính sách đòi thu hồi tức thời hoặc kiểm tra quyền theo thời gian thực, cần thiết kế cơ chế recheck hoặc chặn thời lượng stream có chủ đích; TTL ngắn đơn thuần không nhất thiết đóng kết nối đã bắt đầu.

## 8. Test chính sách quyền bằng WebTestClient và token thật

Cần hai lớp test tách biệt:

1. **Policy test** sử dụng Spring Security Test `mockJwt()` để mô phỏng principal đáng tin và chứng minh route/scope/client ID bị từ chối hoặc cho phép. Công cụ này **bỏ qua JWT signature/expiry/issuer/audience validation**.
2. **Decoder/integration test** dùng JWT thực ký bằng test key và issuer/audience phù hợp, xác minh token hết hạn, sai issuer/audience, sai chữ ký, algorithm/JWK không được chấp nhận. Dùng clock cố định hoặc token ngoài clock-skew một khoảng đủ lớn để tránh flaky test.

Ví dụ `src/test/java/example/security/MachineApiSecurityTest.java` trong ứng dụng Spring Boot 3.3 có `spring-boot-starter-test` và `spring-security-test`:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@WebFluxTest(
    controllers = MachineApiSecurityTest.Api.class,
    properties = {
        "app.security.issuer=https://identity.example.test/issuer",
        "app.security.audience=reports-jobs-api"
    })
@Import(MachineApiSecurity.class)
class MachineApiSecurityTest {

    @Autowired
    WebTestClient client;

    @MockBean
    ReactiveJwtDecoder decoder;

    @Test
    void missingBearerTokenReturns401() {
        client.get().uri("/api/reports/daily")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongClientCannotSubmitWithCorrectScope() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim("client_id", "unknown-service"))
                .authorities(new SimpleGrantedAuthority("SCOPE_jobs.submit")))
            .post().uri("/api/jobs")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void correctClientCannotReadWithoutReportsPermission() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim("client_id", "job-runner-prod"))
                .authorities(new SimpleGrantedAuthority("SCOPE_jobs.submit")))
            .get().uri("/api/reports/daily")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void jobRunnerWithCorrectPermissionCanSubmit() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim("client_id", "job-runner-prod"))
                .authorities(new SimpleGrantedAuthority("SCOPE_jobs.submit")))
            .post().uri("/api/jobs")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("queued");
    }

    @RestController
    static class Api {
        @GetMapping("/api/reports/daily")
        Mono<String> report() {
            return Mono.just("daily");
        }

        @PostMapping("/api/jobs")
        Mono<String> submit() {
            return Mono.just("queued");
        }
    }
}
~~~

Test trên dùng `@MockBean` phù hợp Boot 3.3; khi nâng cấp Boot thì dùng API mock hỗ trợ ở phiên bản đích. Nó kiểm tra **authorization**, không chứng minh tính hợp lệ crypto hay `exp`. Bổ sung case client đúng nhưng thiếu scope; scope đúng nhưng danh tính client sai; nhận token staging vào prod; JWT `aud` của API khác; token hết hạn; issuer sai; `nbf` ở tương lai; route mới/method DELETE; tenant của workload khác; endpoint lộ qua chain matcher khác. 

Một bảng hồi quy thực tế:

| Case | Kỳ vọng |
| --- | --- |
| Không Bearer token | 401 |
| Token hết hạn, sai signature hoặc issuer | 401, không chạy handler |
| Token đúng issuer nhưng sai audience | 401 |
| Token hợp lệ, không có scope cần thiết | 403 |
| Scope đúng, client ID không được cấp | 403 |
| Đúng client/scope nhưng method POST vào endpoint chỉ cho GET | 403 |
| Đúng client/scope nhưng tenant/resource khác | 403 hoặc 404 theo policy công khai |
| Client staging gọi API prod | Bị chặn bởi issuer/audience/policy môi trường |
| Mọi điều kiện cho phép | 2xx đúng body/side effect mong đợi |
| Chạy token cũ khi đã thu hồi credential | Tùy cơ chế TTL/denylist/introspection, phải test như thiết kế |
| JWKS hoặc IdP mất kết nối | Không chuyển sang mặc định cho phép |

Với test permission theo tenant, dùng ít nhất hai tenant có resource độc lập. Test chỉ chứng minh thành công tenant A không đủ để kết luận tenant B đã được bảo vệ. Khi kiểm tra decoder, không nhầm `@WithMockUser`, `mockJwt()` hoặc mocked `ReactiveJwtDecoder` với kiểm thử xác minh chữ ký JWT thực.

## 9. Vận hành service account, access token và secret an toàn

Một chính sách phân quyền đúng trong code vẫn có thể thất bại ở deployment nếu credential tồn tại quá lâu hoặc rò rỉ. Áp dụng quy trình sau.

**Tạo/cấp quyền:** mỗi account có owner, môi trường, client ID, phạm vi công việc, audience, allowed scopes và ngày review. IdP phải áp giới hạn scope theo client registration; caller không thể xin quyền cao hơn chỉ bằng request `scope=*`. Dùng credential client mạnh theo IdP: client secret được bảo vệ, `private_key_jwt`, mTLS hoặc workload identity federation khi khả thi.

**Lưu trữ/sử dụng:** ưu tiên secret manager, secret volume/mount hoặc identity token ngắn hạn do platform phát. Không commit secret, access token, refresh token, private key vào Git, Dockerfile, image, test fixture, console log hoặc đường dẫn URL. Chỉ gửi Bearer token qua TLS tới host đã kiểm soát. Tránh logging full request headers và body có token. Khi lấy token cho WebClient, tránh phơi token trong exception hoặc tracing span.

**Rotation:** lên lịch xoay secret và signing key với overlap theo hợp đồng hệ thống; xoay JWKS phải giữ khả năng verify các token hợp lệ đang sống nếu chính sách yêu cầu. Test rotation trước khi bật production. Không mặc định rotate client secret sẽ thu hồi ngay JWT đã phát hành.

**Thu hồi/offboarding:** khi workload bị giải thể hoặc nghi lộ, thu hồi registration/secret, loại scope, xóa deployment binding, điều tra nhật ký. Xác định token tự chứa có hết hiệu lực ngay hay không; dùng TTL ngắn, introspection hoặc denylist nếu cần tác động tức thời.

**Audit/monitoring:** log thời điểm, route, quyết định 401/403/2xx, service identity đã xác minh, issuer, audience hợp lệ, tenant và correlation ID với mức dữ liệu an toàn. Không ghi nguyên token để “tiện debug”; không đưa claim PII/secret thừa vào JWT. Theo dõi tăng đột biến 403, caller mới dùng scope cao, token của staging gọi prod, thay đổi permission và các lần cấp token bất thường.

**Rà soát định kỳ:** so scope được cấp với chức năng đang chạy, gỡ quyền không dùng, tách account nếu workload phình phạm vi, cập nhật chủ sở hữu và cách khôi phục khẩn cấp. Quyền của tài khoản dịch vụ cần được kiểm tra cùng code review và quy trình deploy.

Các lỗi phổ biến cần tránh: bật `anyExchange().permitAll()` trong production; chỉ dựa vào gateway mà bỏ kiểm tra server; dùng JWT đã decode chưa verify; tin `client_id` ở header do caller gửi; chia sẻ một Bearer token toàn hệ thống; dùng audience quá rộng; copy token của inbound request sang outbound không giới hạn; cho worker dùng quyền admin để tránh lỗi 403; log toàn bộ `Authorization` header; và giả định khóa/secret bị xóa sẽ ngay lập tức vô hiệu hóa mọi JWT đã phát hành.

## 10. Checklist và tiêu chí đạt

- [ ] Account/service identity tách theo chức năng và môi trường; không dùng chung super-account.
- [ ] Có bảng principal–method–route–scope–audience–tenant/resource được phê duyệt.
- [ ] Resource Server kiểm signature hoặc introspection, issuer, audience, expiry, not-before.
- [ ] Claim `client_id`/identity được xác định theo hợp đồng của IdP, không từ caller tự khai.
- [ ] HTTP authorization mặc định deny; policy giới hạn cả service ID và authority.
- [ ] Scope không được nhầm với quyền đối với mọi tenant hay resource.
- [ ] OAuth2 Client chỉ xin scope cần và chỉ gắn token với API đúng audience.
- [ ] Secret/token bảo vệ bởi TLS và quản lý credential, TTL, rotation, revocation phù hợp.
- [ ] Log và telemetry có redaction; có giám sát caller/quyền bất thường.
- [ ] Test có 401, 403, cross-service, cross-tenant, wrong audience, token quá hạn và endpoint mới.
- [ ] Test Spring `mockJwt()` tách bạch với test decoder JWT thật.
- [ ] Không bỏ bảo vệ CSRF của phần browser dùng cookie khi ứng dụng có nhiều security chain.

**Bài học chính:** một service account chỉ được làm việc đã được giao khi **danh tính được xác minh**, **token được ràng buộc đúng issuer/audience/thời gian**, **scope đủ nhưng không vượt**, **HTTP route được allow có điều kiện**, và **tầng dữ liệu chặn truy cập sai chủ sở hữu/tenant**. WebFlux phải thực thi những kiểm tra này trong luồng xử lý reactive của server, không dựa vào client hoặc một token “hợp lệ” chung chung.

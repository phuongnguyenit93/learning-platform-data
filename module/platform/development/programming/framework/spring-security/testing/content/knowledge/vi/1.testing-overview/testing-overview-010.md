# Lộ trình học từ người dùng giả lập đến kiểm thử tích hợp đầu cuối

## Mục tiêu học tập

Khi bắt đầu kiểm thử Spring Security, cách nhanh nhất thường là tạo một người dùng giả lập bằng `@WithMockUser` hoặc `jwt()` rồi kiểm tra endpoint được phép hay bị từ chối. Cách này rất hữu ích, nhưng nó chỉ chứng minh một phần của hệ thống: quyết định phân quyền sau khi danh tính đã được thiết lập.

Một chiến lược kiểm thử đầy đủ cần đi từ quy tắc nhỏ, qua method security và HTTP, đến xác minh credential/token, tích hợp identity provider và cuối cùng là luồng người dùng thực tế. Mỗi tầng có chi phí và khả năng quan sát khác nhau.

Sau bài học này, bạn có thể:

- Xây dựng lộ trình kiểm thử tăng dần từ unit test đến end-to-end (E2E).
- Chọn đúng thời điểm dùng `@WithMockUser`, `SecurityContext`, `MockMvc`, `WebTestClient`, JWT/OAuth2/OIDC mock.
- Bổ sung test xác thực thực với password, JWT decoder hoặc opaque-token introspection.
- Kiểm tra tích hợp với identity provider (IdP), session, cookie, redirect và browser khi rủi ro yêu cầu.
- Quyết định test nào chạy thường xuyên, test nào chạy ở pipeline tích hợp hoặc trước release.
- Tránh lặp lại cùng một tổ hợp quyền ở tầng E2E tốn kém khi unit/integration test đã bao phủ tốt quy tắc đó.

Bài thuộc module **SPRING_SECURITY_TESTING**: kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Tư duy lộ trình: tăng mức chân thực theo rủi ro

Không có một loại test duy nhất trả lời mọi câu hỏi. Hãy hình dung các tầng kiểm thử như một thang tăng dần:

~~~mermaid
flowchart TD
    U["1. Unit: policy / converter / validator"] --> M["2. Method security: bean Spring + mock principal"]
    M --> H["3. HTTP trong process: MockMvc / WebTestClient"]
    H --> A["4. Xác thực thật: password / JWT / introspection"]
    A --> I["5. Integration: IdP stub, database, broker, downstream"]
    I --> E["6. End-to-end: server thật + browser/client thật"]
~~~

Ở các tầng đầu, test chạy nhanh, cô lập nguyên nhân và có thể thử nhiều tổ hợp đầu vào. Ở các tầng sau, test quan sát được nhiều thành phần phối hợp hơn, nhưng chi phí thiết lập, độ trễ và khả năng lỗi do môi trường cũng tăng.

| Tầng | Câu hỏi chính | Công cụ điển hình | Bằng chứng |
| --- | --- | --- | --- |
| Unit | Quy tắc hoặc phép chuyển đổi có đúng không? | JUnit, AssertJ, Mockito | Policy, converter, validator trả kết quả đúng. |
| Method security | Spring có chặn lời gọi bean theo principal không? | Spring Test, `@WithMockUser`, `SecurityContext` | Proxy/interceptor cho phép hoặc từ chối phương thức. |
| HTTP trong process | Filter/WebFilter và hợp đồng HTTP có đúng không? | `MockMvc`, `WebTestClient` | Status, body, headers, URL authorization, CSRF. |
| Xác thực thực | Credential/token có được kiểm tra không? | HTTP Basic/form login, `JwtDecoder`, `OpaqueTokenIntrospector` | Sai password/token bị từ chối; token hợp lệ tạo đúng principal. |
| Integration | Ứng dụng có phối hợp đúng với IdP và hạ tầng không? | IdP stub/test realm, database, broker, WireMock/MockWebServer | Protocol, HTTP exchange, transaction, session, event. |
| E2E | Người dùng có hoàn thành luồng thực tế an toàn không? | Server thật, browser automation hoặc HTTP client thật | Login, redirect, cookie, quyền và thao tác nghiệp vụ xuyên hệ thống. |

**Nguyên tắc chọn tầng:** dùng tầng thấp nhất có thể quan sát được cơ chế đang cần kiểm chứng; thêm tầng cao hơn khi rủi ro nằm ở sự tích hợp giữa các thành phần hoặc hành vi bên ngoài.

## 2. Bước 1 — Unit test quy tắc và thành phần bảo mật

Bắt đầu bằng các quy tắc có đầu vào/đầu ra rõ ràng. Ví dụ, người duyệt phải thuộc đúng tenant và đơn hàng phải đang chờ duyệt.

~~~java
record Order(String id, String tenantId, String status) {}

final class ApprovalPolicy {

    boolean canApprove(
            String tenantId,
            boolean hasApprovalAuthority,
            Order order) {
        return hasApprovalAuthority
            && order != null
            && tenantId.equals(order.tenantId())
            && "PENDING_REVIEW".equals(order.status());
    }
}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ApprovalPolicyTest {

    private final ApprovalPolicy policy = new ApprovalPolicy();
    private final Order pending = new Order(
        "ORD-42", "store-a", "PENDING_REVIEW");

    @Test
    void approverInSameTenantCanApprovePendingOrder() {
        assertThat(policy.canApprove("store-a", true, pending)).isTrue();
    }

    @Test
    void userWithoutApprovalAuthorityIsDenied() {
        assertThat(policy.canApprove("store-a", false, pending)).isFalse();
    }

    @Test
    void approverFromAnotherTenantIsDenied() {
        assertThat(policy.canApprove("store-b", true, pending)).isFalse();
    }

    @Test
    void alreadyApprovedOrderCannotBeApprovedAgain() {
        Order approved = new Order("ORD-42", "store-a", "APPROVED");
        assertThat(policy.canApprove("store-a", true, approved)).isFalse();
    }
}
~~~

Unit test này chạy nhanh và cho biết điều kiện nào làm quyết định thay đổi. Nó chưa chứng minh Spring Security tạo authority đúng, service gọi policy đúng hay endpoint thực sự được bảo vệ.

Các thành phần khác cũng phù hợp với unit test:

- Converter ánh xạ claim JWT như `scope` hoặc `roles` thành `GrantedAuthority`.
- Validator kiểm tra issuer, audience hoặc claim tùy biến.
- Quy tắc ownership/tenant.
- Hàm chuẩn hóa username, trạng thái tài khoản hoặc chính sách thời hạn.
- Thành phần quyết định quyền tùy biến như `AuthorizationManager`.

Khi unit test đã bao phủ nhiều trường hợp dữ liệu, không cần nhân tất cả trường hợp đó lên thành hàng trăm test HTTP. Hãy chọn một số ca đại diện để xác minh các thành phần được nối với nhau đúng.

## 3. Bước 2 — Method security với người dùng giả lập

Sau khi quy tắc thuần Java đúng, kiểm tra Spring có áp dụng annotation bảo mật trên bean thật không.

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class ApprovalService {

    @PreAuthorize("hasAuthority('orders:approve')")
    public String approve(String orderId) {
        return "approved:" + orderId;
    }
}
~~~

Bật method security trong ứng dụng Servlet:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Test lấy bean từ Spring context và sử dụng principal giả lập:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.*;

@SpringBootTest
class ApprovalMethodSecurityTest {

    @Autowired
    ApprovalService approvalService;

    @Test
    @WithMockUser(username = "mai", authorities = "orders:approve")
    void approverCanCallService() {
        assertThat(approvalService.approve("ORD-42"))
            .isEqualTo("approved:ORD-42");
    }

    @Test
    @WithMockUser(username = "linh", authorities = "orders:read")
    void readerCannotCallService() {
        assertThatThrownBy(() -> approvalService.approve("ORD-42"))
            .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Ở tầng này, test chứng minh proxy/interceptor method security đang hoạt động với authority trong `SecurityContext`. Nó không kiểm tra HTTP matcher, CSRF, password, JWT signature hoặc login protocol.

Hãy nhớ:

- Gọi bean do Spring quản lý, không dùng `new ApprovalService()`.
- Kiểm tra cả principal đủ quyền và principal thiếu quyền.
- Bật `@EnableMethodSecurity`.
- Nếu có lời gọi nội bộ qua `this.method()`, kiểm tra riêng vì lời gọi có thể bỏ qua proxy.

Với method security Reactive, bật `@EnableReactiveMethodSecurity`, thiết lập authentication trong Reactor Context và subscribe publisher bằng `StepVerifier`. Không lấy `SecurityContextHolder` theo ThreadLocal làm nguồn principal trong code Reactive.

## 4. Bước 3 — HTTP trong process với principal giả lập

Đây là tầng để xác nhận request thực sự đi qua filter chain hoặc WebFilter chain, đúng matcher, authorization và handler.

### 4.1. Servlet với MockMvc

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ApprovalHttpSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "mai", authorities = "orders:approve")
    void approverCanPostApproval() throws Exception {
        mvc.perform(post("/api/orders/ORD-42/approve")
                .with(csrf()))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "linh", authorities = "orders:read")
    void readerIsForbidden() throws Exception {
        mvc.perform(post("/api/orders/ORD-42/approve")
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousIsUnauthorized() throws Exception {
        mvc.perform(post("/api/orders/ORD-42/approve")
                .with(csrf()))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Ví dụ giả định ứng dụng dùng HTTP Basic/resource-server style entry point trả `401` cho anonymous và CSRF đang bật. Nếu dùng form login, anonymous có thể nhận redirect; điều chỉnh assertion theo hợp đồng thực tế.

Trong test phân quyền POST, token CSRF hợp lệ được thêm vào cả hai request. Nhờ đó, user thiếu authority bị từ chối ở bước phân quyền thay vì bị chặn trước bởi CSRF filter.

Nếu tự dựng MockMvc bằng `MockMvcBuilders.webAppContextSetup(...)`, hãy áp dụng `springSecurity()`. Với `@AutoConfigureMockMvc(addFilters = false)`, filter bị tắt và test không còn xác nhận hành vi filter chain.

### 4.2. Reactive với WebTestClient

Với ứng dụng WebFlux, gắn client vào application context và áp dụng security configurer:

~~~java
@BeforeEach
void setUp() {
    client = WebTestClient.bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
}
~~~

Test principal giả lập:

~~~java
client.mutateWith(mockUser("mai")
        .authorities(new SimpleGrantedAuthority("orders:approve")))
    .mutateWith(csrf())
    .post().uri("/api/orders/ORD-42/approve")
    .exchange()
    .expectStatus().isOk();

client.mutateWith(mockUser("linh")
        .authorities(new SimpleGrantedAuthority("orders:read")))
    .mutateWith(csrf())
    .post().uri("/api/orders/ORD-42/approve")
    .exchange()
    .expectStatus().isForbidden();
~~~

Các ví dụ này kiểm tra quyết định authorization với authentication giả lập. Nếu client gọi server đang chạy ở cổng thật, mock principal trong tiến trình test không tự truyền qua HTTP; cần gửi credential/token thật.

### 4.3. Những assertion cần có ở tầng HTTP

Không chỉ assert status. Với endpoint nhạy cảm, hãy kiểm tra thêm:

- Response body và các trường không được tiết lộ.
- Content type, cache headers và security headers theo hợp đồng.
- CSRF với request làm thay đổi trạng thái.
- Database state và event/outbox khi có tác động nghiệp vụ.
- Ca được phép, thiếu quyền và anonymous.
- Cùng URL nhưng khác HTTP method nếu chính sách khác nhau.

Ở tầng này, `jwt()`/`mockJwt()`, `opaqueToken()`/`mockOpaqueToken()`, `oauth2Login()`/`oidcLogin()` rất hữu ích để tạo principal. Tuy nhiên, chúng không xác minh token hoặc protocol bên ngoài.

## 5. Bước 4 — Xác thực credential và token thực

Khi câu hỏi là “server có kiểm tra bằng chứng danh tính đúng không?”, hãy bỏ mock principal và gửi credential/token qua cơ chế xác thực thực tế.

### 5.1. Password hoặc HTTP Basic

Ví dụ với Servlet và HTTP Basic đã được cấu hình:

~~~java
@Test
void validPasswordIsAccepted() throws Exception {
    mvc.perform(get("/api/me")
            .with(httpBasic("linh", "correct-test-password")))
        .andExpect(status().isOk());
}

@Test
void wrongPasswordIsRejected() throws Exception {
    mvc.perform(get("/api/me")
            .with(httpBasic("linh", "wrong-password")))
        .andExpect(status().isUnauthorized());
}
~~~

Các request này đi qua filter/provider xác thực HTTP Basic trong test context. Điều kiện là ứng dụng có user store, password encoder và security configuration tương ứng.

Với form login, test cần gửi request đăng nhập thực tế qua filter login, giữ session/cookie và kiểm tra trạng thái sau login. `@WithMockUser` không thể thay thế bài test đó.

### 5.2. JWT đã ký và bearer token thật

Một test JWT thực gửi token qua header:

~~~java
@Test
void signedBearerTokenIsAcceptedByDecoder() throws Exception {
    String token = signedTokenFixture.validTokenWithOrdersRead();

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isOk());
}

@Test
void tokenSignedByUnknownKeyIsRejected() throws Exception {
    String token = signedTokenFixture.tokenSignedByAnotherKey();

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
~~~

Fixture tạo cặp khóa chỉ dùng cho test. Decoder của ứng dụng tin public key tương ứng. Các test bổ sung nên tạo token có chữ ký hợp lệ nhưng từng claim sai để kiểm tra riêng:

- `exp` đã hết hạn hoặc `nbf` nằm trong tương lai.
- `iss` không đúng issuer được tin.
- `aud` không chứa audience của API.
- Claim scope/role thiếu hoặc được ánh xạ sai.
- Key ID không tồn tại hoặc khóa ký không được tin.

Mock `jwt()` kiểm tra phân quyền sau khi có principal. Bearer header với decoder thật mới kiểm tra việc server xác minh token.

### 5.3. Opaque token và introspection

Với opaque token, gửi bearer token để `OpaqueTokenIntrospector` thực hiện HTTP introspection. Có thể dùng HTTP stub cục bộ để trả các trường hợp:

- `active: true` kèm scope cần thiết.
- `active: true` nhưng thiếu scope.
- `active: false`.
- Introspection endpoint timeout hoặc trả lỗi.
- Phản hồi thiếu dữ liệu bắt buộc hoặc sai định dạng.

Test này kiểm tra resource server gọi introspection và xử lý response đúng. Nó không chứng minh authorization server bên ngoài đang vận hành đúng; muốn kiểm tra provider thật cần môi trường integration riêng.

### 5.4. OAuth2 và OIDC login

Dùng `oauth2Login()`/`oidcLogin()` để kiểm tra logic ứng dụng sau đăng nhập. Để xác minh authorization code flow, callback, `state`, `nonce`, ID token signature và UserInfo, cần test với IdP stub hoặc môi trường test của IdP.

## 6. Bước 5 — Integration test với IdP và các hệ thống phụ thuộc

Khi nhiều thành phần cần phối hợp, dựng test integration có kiểm soát:

- Resource server thật của ứng dụng.
- IdP stub hoặc test realm.
- Database test.
- Message broker hoặc outbox nếu có.
- HTTP mock server cho downstream service.
- Cấu hình key, issuer, audience và client registration dành riêng cho test.

### 6.1. Ví dụ tích hợp JWT với JWKS endpoint giả lập

Một JWKS stub có thể công bố public key test. Ứng dụng được cấu hình dùng issuer/JWK Set URI trỏ tới stub. Test tạo JWT ký bằng private key tương ứng rồi gửi bearer token qua HTTP.

Kịch bản nên có:

| Kịch bản | Token/JWKS | Kỳ vọng |
| --- | --- | --- |
| Key hợp lệ | JWKS có public key phù hợp, JWT ký bằng private key tương ứng | Request được xác thực. |
| Chữ ký sai | JWT ký bằng key khác | Bị từ chối. |
| Key ID không tồn tại | Header `kid` không có trong JWKS | Bị từ chối. |
| Xoay khóa | JWKS cập nhật key mới theo kịch bản | Decoder xử lý cache/refresh theo cấu hình. |
| Issuer sai | Chữ ký hợp lệ nhưng `iss` khác | Bị từ chối. |

Stub giúp kiểm tra cách ứng dụng tải key và xử lý phản hồi mạng. Nó không thay thế hợp đồng hoặc kiểm thử vận hành của IdP production.

### 6.2. Kiểm tra OAuth2/OIDC authorization code flow

Nếu ứng dụng dùng login qua browser, integration test có thể dựng IdP giả lập với authorization endpoint, token endpoint và JWKS/UserInfo endpoint. Luồng kiểm tra gồm:

1. Truy cập trang yêu cầu đăng nhập.
2. Xác nhận ứng dụng redirect đến authorization endpoint với client ID và redirect URI đúng.
3. IdP stub trả callback có authorization code và state.
4. Ứng dụng kiểm tra state, đổi code lấy token.
5. Ứng dụng xác minh ID token và lấy user claims nếu cần.
6. Session/cookie được tạo theo cấu hình.
7. Request tiếp theo dùng session và được phân quyền đúng.

Các bước này quan sát được sự phối hợp giữa redirect, callback, token client, decoder và session. Chúng cần thiết khi lỗi protocol có rủi ro cao; không cần chạy toàn bộ flow cho mọi biến thể quyền nếu các quyết định phân quyền đã được kiểm tra ở tầng thấp hơn.

### 6.3. Kiểm tra side effect xuyên transaction

Với thao tác nhạy cảm, test integration nên quan sát:

- Database đã thay đổi sau khi request được cho phép.
- Outbox/event chỉ được tạo đúng lúc.
- Không phát event nghiệp vụ khi request bị từ chối.
- Downstream call không xảy ra với user thiếu quyền.
- Security audit event vẫn được ghi nếu chính sách yêu cầu.
- Retry không tạo tác động trùng lặp.

Dùng database/broker test hoặc stub phù hợp. Không chỉ mock mọi phụ thuộc nếu mục tiêu là kiểm tra transaction hoặc serialization thực tế.

## 7. Bước 6 — End-to-end với server và client thực

E2E kiểm tra luồng xuyên ứng dụng ở mức gần với người dùng nhất. Đây là tầng có chi phí cao nhất và thường dễ bị ảnh hưởng bởi cấu hình môi trường, timing, mạng và dữ liệu dùng chung.

Một kịch bản browser E2E cho ứng dụng dùng OIDC có thể là:

1. Mở trang quản trị yêu cầu đăng nhập.
2. Browser được redirect đến IdP test.
3. Đăng nhập bằng tài khoản test có role admin.
4. IdP redirect về callback của ứng dụng.
5. Ứng dụng tạo session/cookie đúng thuộc tính.
6. Admin mở báo cáo và thấy dữ liệu được phép.
7. Đăng xuất; session không còn được chấp nhận.
8. Đăng nhập bằng user thường.
9. User thường không thể mở báo cáo quản trị và không nhận dữ liệu nhạy cảm.

Với E2E, kiểm tra cả giao diện và response/network khi cần. Ví dụ browser automation có thể xác nhận người dùng thường thấy trang access denied, nhưng assertion ở API hoặc database vẫn hữu ích để bảo đảm không có side effect.

### 7.1. E2E không thay thế các tầng thấp

Nếu có 20 role và 30 endpoint, không nên chạy toàn bộ 600 tổ hợp qua browser. Hãy:

- Bao phủ mọi quy tắc nhỏ và tổ hợp dữ liệu ở unit test.
- Bao phủ annotation, URL authorization và CSRF ở method/HTTP test.
- Bao phủ token validation và protocol quan trọng ở integration test.
- Chọn một số luồng quan trọng nhất cho E2E: login, logout, truy cập tài nguyên nhạy cảm, tenant isolation và một thao tác thay đổi trạng thái.

E2E trả lời câu hỏi “các thành phần khi triển khai có phối hợp được không?”, còn test thấp hơn giúp xác định nhanh “quy tắc nào sai?”.

## 8. Lộ trình áp dụng theo từng giai đoạn

Có thể triển khai theo thứ tự sau trong một dự án Spring Security:

| Giai đoạn | Công việc | Điều kiện hoàn thành |
| --- | --- | --- |
| 1. Chốt policy | Liệt kê subject, action, resource, role/scope, tenant và điều kiện trạng thái. | Có ma trận allow/deny rõ ràng. |
| 2. Unit | Test policy, converter, validator, ownership. | Các quy tắc và trường hợp biên được bao phủ. |
| 3. Method | Test bean Spring với principal giả lập. | `@PreAuthorize`/method security cho phép và từ chối đúng. |
| 4. HTTP mock | Test MockMvc/WebTestClient, matcher, CSRF, body, headers. | Filter/WebFilter chain đúng và có ca negative. |
| 5. Authentication | Test password, signed JWT hoặc introspection thật qua server. | Credential/token sai bị từ chối, hợp lệ tạo đúng principal. |
| 6. Integration | Test IdP stub, JWKS, callback, session, DB/event. | Các thành phần phối hợp theo hợp đồng. |
| 7. E2E | Test browser/client qua server thật. | Các luồng người dùng quan trọng hoạt động an toàn. |

Không cần đợi hoàn thành toàn bộ tầng thấp mới viết một E2E smoke test đầu tiên. Nhưng trước khi mở rộng E2E, nên có các test thấp hơn để lỗi được định vị nhanh.

## 9. Ma trận quyết định: dùng loại test nào cho câu hỏi nào?

| Câu hỏi | Tầng nên dùng | Có cần principal giả lập? |
| --- | --- | --- |
| Policy ownership có đúng không? | Unit | Không cần Spring Security context. |
| Converter có ánh xạ scope đúng không? | Unit converter | Tạo `Jwt` trong bộ nhớ. |
| `@PreAuthorize` có chặn service không? | Method security | Có, bằng `@WithMockUser` hoặc context phù hợp. |
| URL admin có từ chối user thường không? | HTTP MockMvc/WebTestClient | Có, bằng user mock. |
| CSRF có chặn request thiếu token không? | HTTP test | Có thể dùng user mock, thay đổi CSRF token. |
| Password sai có bị từ chối không? | Authentication integration | Không; gửi password qua cơ chế thật. |
| JWT chữ ký sai có bị từ chối không? | Resource server integration | Không; gửi bearer token đã ký sai. |
| Opaque token inactive có bị từ chối không? | Introspection integration | Không; gọi introspection stub hoặc provider test. |
| OIDC callback/state/nonce có đúng không? | Protocol integration/E2E | Không; chạy flow với IdP stub/test. |
| Cookie, redirect, browser session có đúng không? | E2E | Không; dùng browser/client thực. |

## 10. Tổ chức test trong CI/CD

Một pipeline hợp lý có thể chia theo thời gian và phụ thuộc:

| Nhóm chạy | Nội dung | Thời điểm gợi ý |
| --- | --- | --- |
| Fast tests | Unit policy/converter/validator và method security nhẹ. | Mỗi commit hoặc pull request. |
| Web security tests | MockMvc/WebTestClient, allow/deny, CSRF, response contract. | Mỗi pull request. |
| Authentication integration | JWT decoder, introspection stub, password/provider, JWKS. | Pull request hoặc pipeline integration. |
| System integration | IdP test realm, database/broker, callback/session. | Pipeline tích hợp hoặc trước release. |
| E2E smoke | Login, logout, một số đường truy cập quan trọng. | Sau deploy môi trường test/staging và trước release. |
| Extended E2E | Browser/device/role combinations có rủi ro cao. | Theo lịch hoặc trước thay đổi lớn. |

Để pipeline ổn định:

- Dùng tài khoản, key và token chỉ dành cho test.
- Không lưu secret production trong test fixture.
- Tạo dữ liệu cô lập theo test hoặc run ID.
- Dọn session, database và message sau test.
- Không phụ thuộc thứ tự chạy test.
- Ghi log đủ để chẩn đoán nhưng không in password, bearer token hoặc secret.
- Phân biệt lỗi test assertion với lỗi hạ tầng IdP/network.
- Giữ test E2E ít nhưng có giá trị cao; không biến chúng thành bản sao chậm của unit test.

## 11. Những lỗi thường gặp khi xây lộ trình

### 11.1. Chỉ dùng @WithMockUser cho mọi thứ

Mock user không kiểm tra login, password, JWT signature, introspection hay OIDC protocol. Giữ nó cho phân quyền và logic sau xác thực; thêm test xác thực thực khi cần.

### 11.2. Đẩy mọi tổ hợp lên E2E

E2E chậm và khó chẩn đoán. Dùng unit và HTTP test để bao phủ tổ hợp role/scope/ownership; E2E chỉ tập trung vào luồng xuyên hệ thống quan trọng.

### 11.3. Chỉ test 200

Một user đủ quyền nhận `200` không chứng minh user thiếu quyền bị chặn. Mỗi chính sách quan trọng cần ít nhất một ca được phép và một ca bị từ chối.

### 11.4. Không phân biệt token mock và token thực

`jwt()`/`mockJwt()` thiết lập authentication. Gửi bearer header qua decoder mới kiểm tra xác minh token. Opaque token cũng cần phân biệt principal mock với introspection HTTP.

### 11.5. Không kiểm tra side effect

Status `403` không đủ nếu database đã đổi hoặc event nghiệp vụ đã phát. Kiểm tra trạng thái, outbox và downstream call theo kiến trúc.

### 11.6. Chạy E2E phụ thuộc môi trường không ổn định

IdP, mạng và browser có thể gây lỗi không liên quan đến logic. Dùng stub ở integration để kiểm soát phản hồi; giữ một số E2E smoke trên môi trường test ổn định để kiểm tra cấu hình triển khai.

## 12. Bài thực hành tổng hợp

Với một API quản lý đơn hàng có role user, authority `orders:approve` và đăng nhập OIDC, xây dựng lộ trình sau:

1. Viết unit test cho policy ownership, tenant và trạng thái đơn.
2. Bật method security và test service bằng `@WithMockUser` với approver và reader.
3. Dùng MockMvc kiểm tra endpoint POST, CSRF, response body và side effect cho phép/từ chối.
4. Dùng WebTestClient để kiểm tra tương đương nếu ứng dụng có WebFlux.
5. Gửi password sai/đúng qua login mechanism thật trong test context.
6. Tạo JWT test ký bằng key test; kiểm tra chữ ký, issuer, audience, expiration và scope qua decoder.
7. Dùng introspection stub cho opaque token nếu ứng dụng hỗ trợ loại token này.
8. Dựng IdP test/stub để kiểm tra authorization code callback, state, nonce, ID token và session.
9. Viết E2E smoke cho admin và user thường: login, xem tài nguyên, logout và kiểm tra quyền.
10. Đưa các tầng vào pipeline theo tốc độ và mức phụ thuộc; lưu lại test nào là bằng chứng cho cơ chế nào.

**Tiêu chí hoàn thành:** với mỗi rủi ro, bạn giải thích được test ở tầng nào bao phủ nó, test đó dùng principal giả lập hay credential/token thực, và vì sao cần hoặc không cần thêm một tầng cao hơn.

## 13. Ghi nhớ

Lộ trình kiểm thử Spring Security nên đi từ quy tắc nhỏ đến hành vi tích hợp: unit test policy/converter, method security với principal giả lập, HTTP test bằng MockMvc/WebTestClient, xác thực credential/token thực, integration với IdP và cuối cùng là E2E trên server/browser thực.

`@WithMockUser`, `jwt()`, `mockJwt()` và các tiện ích OAuth2/OIDC giúp kiểm tra quyết định sau khi authentication đã được dựng. Chúng không thay thế kiểm tra password, chữ ký JWT, introspection hoặc protocol login. Khi cần bằng chứng cho những bước đó, hãy gửi credential/token qua cơ chế xác thực thực tế hoặc chạy integration flow phù hợp.

Không phải mọi trường hợp đều cần chạy ở tầng cao nhất. Hãy để unit test bao phủ nhiều tổ hợp quy tắc, HTTP test xác minh filter và hợp đồng, integration test xác minh giao tiếp giữa thành phần, còn E2E tập trung vào những luồng người dùng có rủi ro cao. Một lộ trình tốt cho biết **đã kiểm chứng điều gì, ở tầng nào và phần nào vẫn cần bằng chứng bổ sung**.

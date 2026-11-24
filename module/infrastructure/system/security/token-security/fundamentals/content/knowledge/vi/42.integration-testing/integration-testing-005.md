# Test resource server với opaque token

## 1. Mục tiêu và phạm vi

Opaque access token là token mà resource server không tự giải mã nội dung như JWT. Token thường là một chuỗi định danh khó đoán; authorization server giữ trạng thái và cung cấp endpoint introspection để resource server hỏi token có còn active hay không, thuộc subject/client nào và được cấp những quyền gì. **Test resource server với opaque token** kiểm tra đường đi từ HTTP request mang Bearer token, qua xác thực/introspection, đến ánh xạ scope và quyết định truy cập API.

Trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học đặt trọng tâm vào mô hình tin cậy và vòng đời token: resource server chỉ tin kết quả introspection từ authorization server đã cấu hình; token phải còn hiệu lực, đúng đối tượng nhận và đủ scope; việc thu hồi, cache, timeout và lỗi kết nối phải được kiểm soát. Kiểm thử tích hợp cần chứng minh cả trường hợp được phép lẫn bị từ chối, đồng thời xác nhận request không tạo side effect khi thiếu quyền.

Sau bài này, người học có thể:

- Giải thích vai trò của opaque access token và RFC 7662 Token Introspection.
- Cấu hình Spring Security Resource Server để xác thực opaque token qua introspection.
- Viết test ở lớp authorization bằng principal giả lập và test tích hợp gọi endpoint introspection giả lập.
- Kiểm tra token active/inactive, thiếu scope, sai audience, hết hạn, introspection timeout và lỗi xác thực client.
- Đánh giá ảnh hưởng của cache introspection đến thời gian thu hồi token.
- Bảo vệ client secret, bearer token và dữ liệu introspection trong test, log và CI.

## 2. Opaque token và luồng introspection

Opaque token không mang một payload JWT mà resource server có thể tin cậy để tự đọc. Resource server gửi token đến introspection endpoint của authorization server qua một kết nối được bảo vệ. Authorization server xác thực resource server, tra cứu trạng thái token và trả metadata. Một phản hồi RFC 7662 thường có trường **active**; các trường như **scope**, **client_id**, **sub**, **aud**, **iss**, **exp** hoặc **token_type** có thể xuất hiện tùy issuer và cấu hình.

Ví dụ minh họa phản hồi active:

~~~json
{
  "active": true,
  "scope": "orders.read orders.cancel",
  "client_id": "orders-web",
  "sub": "user-184",
  "aud": ["orders-api"],
  "iss": "https://auth.example.test",
  "exp": 1795431600,
  "token_type": "Bearer"
}
~~~

Đây là dữ liệu giả lập để giải thích cấu trúc, không phải token hay response dùng trong môi trường thật. Resource server chỉ được tin metadata nhận qua introspection đã xác thực với authorization server đúng cấu hình. Không nhận claim do client gửi riêng trong header hoặc body để thay thế kết quả introspection.

### 2.1 Luồng xử lý

~~~mermaid
sequenceDiagram
    participant C as API Client
    participant R as Resource Server
    participant A as Authorization Server
    participant P as Protected API
    C->>R: Request + Bearer opaque token
    R->>R: Trích xuất token, kiểm tra cấu hình
    R->>A: POST introspection (token + client authentication)
    A->>A: Xác minh client, tra cứu trạng thái token
    A-->>R: active + metadata (scope, sub, aud...)
    alt Token active và hợp lệ
        R->>R: Tạo Authentication, ánh xạ authorities
        R->>R: Kiểm tra audience và policy API
        alt Có đủ scope và quyền dữ liệu
            R->>P: Thực thi nghiệp vụ
            P-->>C: Response thành công
        else Thiếu scope hoặc không được phép
            R-->>C: 403 Forbidden (theo hợp đồng)
        end
    else Token inactive hoặc không xác minh được
        R-->>C: Authentication failure
    end
~~~

Một số điểm tin cậy quan trọng:

1. Client gửi token đến resource server; token không được gửi đến endpoint tùy ý.
2. Resource server dùng TLS và cơ chế client authentication đã cấu hình để gọi introspection endpoint.
3. Authorization server quyết định token active hay inactive; resource server không tự suy đoán trạng thái từ hình dạng chuỗi token.
4. Resource server chuyển scope từ response đã xác minh thành authority theo mapping rõ ràng.
5. Endpoint vẫn kiểm tra audience/resource, quyền dữ liệu, tenant và quy tắc nghiệp vụ theo policy.

Introspection trả về active không tự động có nghĩa token được phép gọi mọi API. Ví dụ, token active nhưng audience chỉ là **billing-api** không phù hợp với **orders-api**. Tương tự, token active có scope **orders.read** không được dùng để hủy đơn hàng nếu API yêu cầu **orders.cancel**.

## 3. Chuẩn bị hợp đồng kiểm thử

Trước khi viết test, xác định các điều kiện chấp nhận:

| Thành phần | Hợp đồng cần xác định |
| --- | --- |
| Introspection URI | HTTPS endpoint thuộc authorization server tin cậy |
| Client authentication | Basic, client assertion hoặc phương thức đã được hệ thống cấu hình |
| Token | Access token opaque trong môi trường test; không dùng refresh token hoặc ID token để gọi resource API |
| Active | Chỉ token được issuer xác nhận active mới đi tiếp |
| Scope | Quy ước phân tách scope và cách chuyển thành authority |
| Audience/resource | Resource server phải xác minh token dành cho API hiện tại |
| Subject/client | Metadata đã xác minh dùng cho principal và audit |
| Expiration | Kiểm tra exp theo hợp đồng; issuer cũng phải trả active=false khi token hết hiệu lực |
| Cache | TTL, khóa cache, invalidation và hành vi sau revoke |
| Lỗi hạ tầng | Timeout, TLS failure, 401/403/5xx từ introspection phải có hành vi fail-closed hoặc policy được phê duyệt rõ |

Không phải mọi authorization server đều trả mọi trường metadata. Hãy căn cứ vào hợp đồng introspection thực tế. Nếu resource server cần audience hoặc issuer để bảo vệ ranh giới tin cậy, phải bảo đảm issuer trả trường đó và ứng dụng kiểm tra; đừng mặc định framework sẽ tự xác minh mọi claim chỉ vì phản hồi có chứa chúng.

### 3.1 Ma trận test tối thiểu

| ID | Introspection / request | Kết quả kỳ vọng |
| --- | --- | --- |
| OP-01 | Không có Authorization header | 401 Unauthorized |
| OP-02 | Bearer token không hợp lệ, issuer trả active=false | Không xác thực; thường là 401 |
| OP-03 | active=true, có scope đọc, gọi API đọc | Qua authorization nếu audience và policy khác hợp lệ |
| OP-04 | active=true, thiếu scope bắt buộc | 403 Forbidden theo hợp đồng |
| OP-05 | active=true, scope gần giống nhưng không đúng | Bị từ chối |
| OP-06 | active=true, audience sai | Bị từ chối bởi audience validation |
| OP-07 | active=true nhưng exp đã qua | Bị từ chối theo hợp đồng; issuer nên trả inactive |
| OP-08 | Introspection trả 401 do resource server xác thực sai | Không cấp quyền; báo lỗi cấu hình an toàn |
| OP-09 | Introspection timeout hoặc 5xx | Không cấp quyền khi chưa xác minh; response theo exception policy |
| OP-10 | Scope đủ nhưng subject không sở hữu tài nguyên | 403 hoặc 404 theo policy |
| OP-11 | Token bị revoke sau khi đã cache | Bị từ chối sau thời hạn cache/invalidation được cam kết |
| OP-12 | Introspection response thiếu/sai kiểu scope | Không tự cấp authority; xử lý theo schema validation |

Các status ở bảng là kỳ vọng phổ biến; API có thể chuẩn hóa response khác. Riêng lỗi hạ tầng introspection không nên bị đánh đồng với token inactive. Có thể trả 5xx/503 để thể hiện dependency không sẵn sàng, hoặc dùng entry point chuẩn của ứng dụng; điều bắt buộc là request không được âm thầm cấp quyền khi chưa xác minh được token.

## 4. Cấu hình Resource Server với Spring Security

Spring Security hỗ trợ opaque token thông qua cấu hình Resource Server. Một cấu hình minh họa:

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/orders/*/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            );
        return http.build();
    }
}
~~~

Cấu hình endpoint và thông tin client có thể được cung cấp qua properties:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.internal/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Giá trị secret phải đến từ secret manager hoặc biến môi trường được bảo vệ. Không commit secret vào source control, không đặt secret thật trong test fixture, không in cấu hình nhạy cảm ra CI log. Trong môi trường test, dùng credential giả riêng.

Với cấu hình mặc định của Spring Security, scope trong principal được ánh xạ thành authority có tiền tố **SCOPE_**. Ví dụ **orders.read** thành **SCOPE_orders.read**. Nếu issuer dùng claim khác, trả scope dưới dạng mảng hoặc cần kiểm tra audience riêng, cấu hình một **OpaqueTokenIntrospector** phù hợp thay vì giả định mapping mặc định đáp ứng tất cả yêu cầu.

Ví dụ lớp kiểm tra audience bằng introspection principal:

~~~java
import java.util.List;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

final class AudienceCheckingIntrospector implements OpaqueTokenIntrospector {
    private final OpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = delegate;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);
        Object rawAudience = principal.getAttribute("aud");

        boolean matches = rawAudience instanceof String value
                && expectedAudience.equals(value);
        if (rawAudience instanceof List<?> values) {
            matches = values.contains(expectedAudience);
        }
        if (!matches) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error("invalid_token", "Audience is not accepted", null));
        }
        return principal;
    }
}
~~~

Đây là ví dụ minh họa cần điều chỉnh theo kiểu dữ liệu audience mà issuer cam kết. Có hệ thống trả audience dạng chuỗi, có hệ thống trả danh sách; không nên tự ép kiểu mọi dữ liệu không rõ schema. Nếu ứng dụng cần kiểm tra issuer, expiration hoặc tenant bổ sung, hãy thực hiện cùng lớp validation theo hợp đồng. Việc kiểm tra audience phải được triển khai rõ ràng và có test; không dựa vào ví dụ cấu hình mặc định ở trên để suy ra framework đã làm thay.

## 5. Test authorization nhanh bằng opaqueToken() của Spring Security

Trước khi kiểm tra HTTP introspection thật, có thể test authorization layer bằng test support của Spring Security. Request post-processor **opaqueToken()** tạo một Authentication giả lập cho test; nó không gọi authorization server. Vì vậy, cách này phù hợp để kiểm tra endpoint, authority và response, nhưng không kiểm tra giao thức introspection, client authentication, TLS hoặc mapping response thật.

Ví dụ controller:

~~~java
@RestController
class OrderController {
    @GetMapping("/orders")
    List<String> listOrders() {
        return List.of("ORD-100");
    }

    @PostMapping("/orders/{id}/cancel")
    ResponseEntity<Void> cancel(@PathVariable String id) {
        return ResponseEntity.noContent().build();
    }
}
~~~

Test với MockMvc:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OpaqueTokenAuthorizationTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsReadWithReadScope() throws Exception {
        mockMvc.perform(get("/orders")
                .with(opaqueToken()
                    .authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void rejectsCancelWhenOnlyReadScopeIsPresent() throws Exception {
        mockMvc.perform(post("/orders/ORD-100/cancel")
                .with(opaqueToken()
                    .authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowsCancelWithCancelScope() throws Exception {
        mockMvc.perform(post("/orders/ORD-100/cancel")
                .with(opaqueToken()
                    .authorities(new SimpleGrantedAuthority("SCOPE_orders.cancel"))))
            .andExpect(status().isNoContent());
    }
}
~~~

Tùy phiên bản Spring Security, các overload builder có thể khác đôi chút; dùng đúng phiên bản dependency của dự án. Test này đặt authority trực tiếp nên không chứng minh introspection response đã được chuyển thành authority đúng. Cần thêm test introspector và test tích hợp HTTP ở các phần tiếp theo.

## 6. Test introspection endpoint bằng HTTP giả lập

Để kiểm tra resource server thực sự gọi introspection, dùng một HTTP server giả lập như WireMock trong test. WireMock nhận request POST, kiểm tra client authentication và trả JSON theo RFC 7662. MockMvc vẫn gửi request đến resource server trong cùng Spring application, nhưng introspection đi qua HTTP thật tới WireMock.

### 6.1 Dependency test

Ví dụ Maven dependency (chọn phiên bản tương thích với Spring Boot/Spring Security của dự án):

~~~xml
<dependency>
    <groupId>org.wiremock</groupId>
    <artifactId>wiremock</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dự án quản lý dependency qua BOM, ưu tiên version đã được BOM kiểm soát. Không tự nâng version framework chỉ để chạy ví dụ này.

### 6.2 Khởi tạo WireMock và cấu hình properties

~~~java
import static com.github.tomakehurst.wiremock.client.WireMock.*;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

class OpaqueTokenHttpIntegrationTest {
    static final WireMockServer introspectionServer =
            new WireMockServer(options().dynamicPort());

    static {
        introspectionServer.start();
    }

    @AfterAll
    static void stopServer() {
        introspectionServer.stop();
    }

    @DynamicPropertySource
    static void resourceServerProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri",
            () -> introspectionServer.baseUrl() + "/introspect");
        registry.add(
            "spring.security.oauth2.resourceserver.opaquetoken.client-id",
            () -> "orders-resource-server");
        registry.add(
            "spring.security.oauth2.resourceserver.opaquetoken.client-secret",
            () -> "test-only-secret");
    }
}
~~~

Trong test suite thực tế, bảo đảm WireMock đã start trước khi Spring tạo application context. Khối khởi tạo tĩnh ở ví dụ trên làm điều đó trước khi DynamicPropertySource cung cấp URL. Nếu context cache giữa các test class, không dừng server khi context vẫn còn được tái sử dụng; có thể dùng một JUnit extension hoặc test resource dùng chung để quản lý lifecycle.

### 6.3 Stub response active và kiểm tra request

~~~java
import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OpaqueTokenHttpIntegrationTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void introspectsOpaqueTokenAndAllowsRead() throws Exception {
        introspectionServer.stubFor(post(urlEqualTo("/introspect"))
            .withBasicAuth("orders-resource-server", "test-only-secret")
            .withRequestBody(containing("token=opaque-read-token"))
            .willReturn(okJson("""
                {
                  "active": true,
                  "sub": "user-184",
                  "client_id": "orders-web",
                  "scope": "orders.read",
                  "aud": ["orders-api"],
                  "exp": 1795431600
                }
                """)));

        mockMvc.perform(get("/orders")
                .header("Authorization", "Bearer opaque-read-token"))
            .andExpect(status().isOk());

        introspectionServer.verify(1, postRequestedFor(urlEqualTo("/introspect"))
            .withBasicAuth("orders-resource-server", "test-only-secret"));
    }
}
~~~

Đây là skeleton để ghép vào class test ở mục trước; trong mã thực tế không khai báo hai class cùng tên. Cần bảo đảm import WireMock static đúng package của phiên bản được chọn. Request body introspection thường là form URL encoded; không phụ thuộc thứ tự field trong body khi viết matcher. Ví dụ dùng giá trị token giả định, không phải credential thật.

Kiểm thử response active có scope đọc chưa đủ. Cần stub response active nhưng thiếu scope và xác nhận API từ chối:

~~~java
introspectionServer.stubFor(post(urlEqualTo("/introspect"))
    .withBasicAuth("orders-resource-server", "test-only-secret")
    .withRequestBody(containing("token=opaque-read-only"))
    .willReturn(okJson("""
        {
          "active": true,
          "sub": "user-184",
          "scope": "orders.read",
          "aud": ["orders-api"],
          "exp": 1795431600
        }
        """)));

mockMvc.perform(post("/orders/ORD-100/cancel")
        .header("Authorization", "Bearer opaque-read-only"))
    .andExpect(status().isForbidden());
~~~

Test này chứng minh resource server không nhầm **active=true** với "được phép mọi thao tác". Token đã xác thực nhưng thiếu authority **SCOPE_orders.cancel**, nên endpoint bị từ chối.

### 6.4 Test token inactive và thiếu Bearer token

Phản hồi inactive thường tối giản:

~~~json
{"active": false}
~~~

Với token inactive, resource server phải từ chối xác thực và không chạy controller nghiệp vụ. Với request không có Authorization header, resource server thường không gọi introspection vì không có token để kiểm tra; xác minh không phát request introspection nếu đó là kỳ vọng của kiến trúc.

Không trả nguyên nội dung introspection response cho client. Thông tin như subject, client ID, scope, issuer và expiration chỉ phục vụ quyết định nội bộ hoặc audit theo chính sách.

## 7. Test audience, expiration và dữ liệu introspection không hợp lệ

### 7.1 Audience sai

Một opaque token active vẫn có thể được cấp cho resource khác. Nếu **orders-api** chỉ chấp nhận audience **orders-api**, response có **aud=["billing-api"]** phải bị từ chối.

Test cần xác nhận:

- Introspection trả active=true.
- Audience không chứa resource server hiện tại.
- Audience validator từ chối trước khi controller thực thi.
- Không có side effect và response không tiết lộ metadata nhạy cảm.

Spring Security không nên được giả định tự kiểm tra audience trong mọi cấu hình opaque token. Nếu audience là một ranh giới bảo mật của hệ thống, hãy triển khai validator/introspector rõ ràng và test nó.

### 7.2 Expiration

Authorization server thường dùng exp để xác định token còn hiệu lực và trả **active=false** sau khi token hết hạn. Resource server cũng có thể kiểm tra exp trong principal nếu hợp đồng yêu cầu. Không dựa vào thời điểm hết hạn do client gửi. Với test, dùng timestamp cố định đã qua và xác nhận issuer stub trả inactive hoặc validator từ chối.

Khi dùng thời gian trong test, tránh hardcode một timestamp phụ thuộc ngày chạy nếu muốn test tái lập. Có thể tạo timestamp từ Clock cố định trong test, hoặc đặt một giá trị đã hết hạn rõ ràng. Đồng bộ clock giữa các hệ thống là yêu cầu vận hành quan trọng.

### 7.3 Scope thiếu, sai kiểu hoặc rỗng

Introspection có thể trả scope dạng chuỗi:

~~~json
{"active":true,"scope":"orders.read orders.cancel"}
~~~

Nếu hệ thống issuer cam kết scope là chuỗi, response có scope là object hoặc số phải bị từ chối hoặc xử lý theo quy tắc schema đã định. Không biến lỗi parse thành tập quyền rỗng một cách âm thầm rồi vẫn cho qua request. Scope rỗng có thể là token active nhưng không được cấp quyền nào; request cần scope cụ thể vẫn phải bị từ chối.

Kiểm tra so khớp theo token scope đã tách thành các authority hoàn chỉnh. Không dùng tìm chuỗi con kiểu "scope string chứa orders.read" nếu cách làm đó có thể nhận nhầm **orders.read.admin** hoặc **not-orders.read**.

## 8. Test lỗi introspection và fail-closed

Các lỗi cần mô phỏng:

| Lỗi | Điều cần kiểm tra |
| --- | --- |
| HTTP 401/403 | Client resource server cấu hình sai hoặc mất quyền introspection; không cấp quyền |
| HTTP 429 | Xử lý rate limit, backoff và cảnh báo; không lặp request vô hạn |
| HTTP 500/503 | Dependency lỗi; request không được xác thực thành công chỉ vì lỗi |
| Timeout | Có timeout hữu hạn, không giữ thread/request vô thời hạn |
| DNS/TLS/connect failure | Không bỏ qua xác minh; phát metric/log an toàn |
| JSON lỗi hoặc response không có active | Không coi là active mặc định |
| Response quá chậm | Theo dõi latency và bảo vệ tài nguyên của resource server |

**Fail-closed** nghĩa là khi không thể xác minh token, hệ thống không cấp quyền dựa trên phỏng đoán hoặc metadata không đáng tin. Response HTTP cụ thể có thể là 401, 503 hoặc một mã đã chuẩn hóa; hãy chọn theo hợp đồng và exception handling của ứng dụng. Không biến timeout thành 403 insufficient_scope vì scope chưa được xác minh.

Kiểm thử timeout có thể dùng WireMock delay hoặc fault. Đặt timeout của HTTP client trong cấu hình resource server để test không bị treo. Xác nhận thời gian phản hồi nằm trong giới hạn, request không đi vào nghiệp vụ và có tín hiệu vận hành để phát hiện dependency lỗi.

Không log raw token khi ghi lỗi introspection. Log an toàn có thể gồm request/correlation ID, endpoint service name, latency, status upstream, reason code và fingerprint token đã được bảo vệ nếu policy cho phép.

## 9. Cache introspection và thu hồi token

Introspection cho phép authorization server phản ánh trạng thái token tập trung, nhưng cache có thể làm chậm hiệu lực thu hồi. Ví dụ, resource server cache **active=true** trong 60 giây; authorization server revoke token ở giây thứ 10; resource server có thể tiếp tục chấp nhận token cho đến khi cache hết hạn hoặc bị invalidation.

Thiết kế cache cần xác định:

- Cache theo fingerprint token (không lưu raw token làm cache key nếu không cần).
- TTL không vượt quá thời hạn còn lại của token và phù hợp mức độ rủi ro.
- Cache negative/inactive có TTL riêng; tránh làm chậm việc token vừa được cấp.
- Invalidation khi có sự kiện revoke nếu hệ thống hỗ trợ.
- Giới hạn kích thước và chống cache pollution từ token ngẫu nhiên.
- Xử lý khi cache backend lỗi; không dùng dữ liệu hết hạn tùy tiện như thể còn tin cậy.

Ma trận test cache:

| Bước | Hành động | Kỳ vọng |
| --- | --- | --- |
| 1 | Request với token active lần đầu | Gọi introspection, cache kết quả theo policy |
| 2 | Request lại trước TTL | Có thể dùng cache, không gọi issuer nếu cache hit được thiết kế |
| 3 | Revoke token ở authorization server | Trạng thái issuer đổi sang inactive |
| 4 | Request trước khi cache hết hạn | Kết quả theo cam kết revocation latency/invalidation |
| 5 | Invalidation hoặc TTL kết thúc | Resource server gọi introspection lại |
| 6 | Request tiếp theo | Token inactive bị từ chối |

Không tuyên bố revoke có hiệu lực tức thời nếu hệ thống không có push invalidation hoặc kiểm tra trạng thái mỗi request. Cần ghi rõ giới hạn độ trễ thu hồi và chọn TTL theo rủi ro của token. Với thao tác đặc quyền, TTL ngắn hoặc không cache có thể phù hợp hơn; phải cân nhắc tải lên authorization server.

## 10. Bảo mật dữ liệu và độ tin cậy của test

Opaque token vẫn là bearer credential: ai có token có thể sử dụng token theo quyền và thời hạn của nó nếu không có sender constraint. Do đó:

- Không ghi token vào log, test report, exception, screenshot hoặc artifact CI.
- Không dùng access token production hoặc client secret production trong test.
- Dùng token giả có entropy phù hợp hoặc fixture riêng cho môi trường thử nghiệm; không tái sử dụng token giữa các môi trường.
- Bảo vệ introspection client credential và chỉ cấp quyền introspection cần thiết.
- Dùng TLS khi resource server gọi authorization server; kiểm tra chứng thư và hostname theo cấu hình.
- Giới hạn truy cập introspection endpoint; không công khai endpoint để bất kỳ ai cũng có thể tra cứu token.
- Không trả response introspection hoặc metadata đầy đủ cho API client.
- Dùng test data giả cho subject/client; hạn chế PII trong report.

Khi cần correlation trong log, dùng event/request ID hoặc fingerprint HMAC được quản lý khóa. Fingerprint cũng là dữ liệu có thể liên kết hoạt động nên phải giới hạn quyền truy cập và thời gian lưu. Không dùng SHA-256 trần cho token có entropy/format không được bảo đảm; keyed HMAC giúp giảm khả năng dò đoán và cần quản lý phiên bản khóa.

## 11. Tổ chức test suite theo tầng

Không nên gom mọi kiểm tra vào một bài end-to-end chậm. Có thể chia:

| Tầng | Thành phần | Mục tiêu |
| --- | --- | --- |
| Unit | Audience validator, scope mapper, policy | Kiểm tra logic thuần và schema |
| Web/security slice | MockMvc + opaqueToken() | Kiểm tra endpoint và authority |
| Introspector test | OpaqueTokenIntrospector với HTTP stub | Kiểm tra parsing, active, client authentication và mapping |
| Application integration | Spring context + WireMock + MockMvc | Kiểm tra filter chain, introspection HTTP và API |
| End-to-end | Authorization server test thật + resource server | Kiểm tra cấu hình liên hệ thống và vòng đời token |
| Resilience | Timeout, 429, 5xx, cache/revoke | Kiểm tra lỗi hạ tầng và giới hạn rủi ro |

Các tầng có thể dùng chung test fixture nhưng cần phân biệt rõ test nào gọi issuer thật, test nào chỉ giả lập principal. Khi test fail, report nên ghi endpoint, loại tình huống, status upstream, status API, latency và correlation ID. Không in token hoặc client secret.

## 12. Ví dụ kịch bản hoàn chỉnh

Một ứng dụng quản lý đơn hàng dùng **orders-api** làm resource server. Authorization server phát opaque access token cho **orders-web**. API đọc đơn hàng cần **orders.read**; API hủy đơn cần **orders.cancel**. Token fixture ban đầu active, audience **orders-api**, scope **orders.read**.

Kịch bản:

1. Gửi GET danh sách đơn hàng với token đọc. Introspection trả active=true và scope **orders.read**; API trả thành công.
2. Gửi POST hủy đơn với cùng token. Introspection xác nhận token active, nhưng policy yêu cầu **orders.cancel**; API trả 403 và đơn hàng không đổi trạng thái.
3. Dùng token active có scope **orders.cancel** và audience **orders-api**. API qua scope check; kết quả còn phụ thuộc quyền trên đơn hàng và trạng thái nghiệp vụ.
4. Đổi response introspection của token đầu thành active=false. API từ chối xác thực; controller không chạy.
5. Đổi audience thành **billing-api**. Audience validator từ chối dù active=true và scope đúng.
6. Làm introspection timeout. Resource server không cấp quyền, request kết thúc theo exception policy và có tín hiệu dependency failure.
7. Cache token active rồi revoke ở issuer. Xác minh thời gian token còn được chấp nhận đúng với cam kết TTL/invalidation.

Kết quả test cần chứng minh: resource server chỉ sử dụng metadata từ introspection đáng tin; active token vẫn phải vượt qua audience, scope và policy dữ liệu; khi không thể xác minh, API không cho thực thi nghiệp vụ.

## 13. Checklist hoàn tất

- [ ] Cấu hình đúng introspection URI và client authentication cho môi trường test.
- [ ] Không lưu client secret hoặc opaque token thật trong source control/CI.
- [ ] Test request không có token và token inactive.
- [ ] Test active token có scope đủ và active token thiếu scope.
- [ ] Test audience sai, expiration và response introspection thiếu/sai kiểu dữ liệu.
- [ ] Test client authentication lỗi, timeout, 429 và 5xx.
- [ ] Kiểm tra scope được ánh xạ đúng thành authority.
- [ ] Xác minh request bị từ chối không tạo side effect hoặc gọi downstream.
- [ ] Kiểm tra cache hit/miss, TTL, invalidation và độ trễ thu hồi.
- [ ] Đảm bảo lỗi introspection không dẫn đến cấp quyền mặc định.
- [ ] Log/report không chứa raw token, Authorization header hoặc secret.
- [ ] Phân biệt test dùng opaqueToken() giả lập với test thực sự gọi introspection HTTP.

## Tài liệu tham khảo

- **RFC 7662 — OAuth 2.0 Token Introspection:** giao thức introspection, yêu cầu bảo vệ endpoint và trường active.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách gửi access token dạng Bearer và xử lý lỗi resource access.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** access token, scope, client authentication và token endpoint.
- **RFC 8693 — OAuth 2.0 Token Exchange:** phát hành token mới với ngữ cảnh audience/scope khác.
- **Spring Security Reference — OAuth 2.0 Resource Server, Opaque Token:** cấu hình introspection và ánh xạ scope thành authority.
- **Spring Security Reference — Testing OAuth 2.0:** request post-processors cho JWT và opaque token trong kiểm thử.

Một resource server dùng opaque token an toàn phải xác minh trạng thái token qua authorization server tin cậy, kiểm tra audience và scope theo hợp đồng, xử lý lỗi dependency theo hướng không cấp quyền khi chưa xác minh, đồng thời giới hạn ảnh hưởng của cache đến thu hồi. Bộ integration test tốt tái hiện được những điều kiện đó qua HTTP introspection và chứng minh API không thực thi nghiệp vụ khi token không đáp ứng policy.

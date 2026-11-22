# Metrics theo endpoint, grant type, client và kết quả xử lý

Authorization Server xử lý các request có ảnh hưởng trực tiếp đến quyền truy cập: đăng nhập, xin authorization code, cấp token, refresh token, introspection và thu hồi token. Khi chỉ theo dõi CPU, bộ nhớ hoặc số request HTTP tổng thể, nhóm vận hành khó biết grant type nào đang lỗi, client nào có tỷ lệ thất bại cao hoặc endpoint nào có độ trễ tăng bất thường.

Với module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, metrics cần phản ánh được hoạt động quản lý client, consent, cấp token, PKCE, refresh token, bảo vệ endpoint và ký khóa. Bài thuộc chương **Quan sát và kiểm toán**, hướng dẫn thiết kế metrics theo bốn chiều: endpoint, grant type, client và kết quả xử lý. Các số liệu này giúp phát hiện sự cố giao thức và hỗ trợ vận hành mà không làm lộ token hay dữ liệu định danh người dùng.

## 1. Xác định câu hỏi vận hành trước khi tạo metrics

Một bộ metrics hữu ích phải trả lời được các câu hỏi cụ thể:

- Endpoint nào nhận nhiều request nhất và endpoint nào có độ trễ p95/p99 cao?
- Grant type nào có tỷ lệ lỗi tăng, chẳng hạn **authorization_code**, **client_credentials** hay **refresh_token**?
- Client nào đang gửi nhiều request thất bại, hoặc có dấu hiệu retry quá mức?
- Request thành công, bị từ chối do lỗi client, lỗi grant hay lỗi server chiếm tỷ lệ bao nhiêu?
- Lưu lượng thay đổi như thế nào sau khi triển khai phiên bản mới, thay đổi cấu hình client hoặc xoay signing key?

Nên chuẩn hóa bốn chiều thành các tag có tập giá trị hữu hạn:

| Chiều | Giá trị ví dụ | Quy tắc |
|---|---|---|
| **endpoint** | **authorize**, **token**, **introspect**, **revoke**, **userinfo**, **jwks** | Ánh xạ từ endpoint đã cấu hình, không dùng URL tùy ý |
| **grant_type** | **authorization_code**, **client_credentials**, **refresh_token**, **other**, **none** | Chỉ giữ các grant type đã biết |
| **client** | **browser_public**, **orders_service**, **admin_console**, **unresolved** | Ánh xạ client ID đã đăng ký sang nhãn vận hành ổn định |
| **outcome** | **success**, **redirect**, **client_error**, **server_error**, **exception**, **other** | Gom status thành nhóm có ý nghĩa |

Ví dụ một dòng metrics có thể đại diện cho request token endpoint dùng Client Credentials của service client và hoàn tất thành công. Một dòng khác có thể biểu diễn refresh token grant bị từ chối. Khi lọc theo bốn tag, dashboard có thể so sánh các luồng mà không cần đọc token hoặc payload nhạy cảm.

**redirect** là kết quả bình thường ở authorization endpoint vì server thường chuyển trình duyệt đến trang đăng nhập, consent hoặc callback. Với token endpoint, kết quả thành công thường là HTTP 2xx; lỗi giao thức thường là 4xx. Không nên gộp mọi status khác 2xx thành cùng một lỗi mà không xét đặc điểm endpoint.

## 2. Dùng Spring Boot Actuator và Micrometer

Spring Boot Actuator cung cấp endpoint quản trị, còn Micrometer cung cấp API ghi Counter, Timer và Gauge. Với Authorization Server chạy Spring Boot 3, có thể thêm Actuator và Prometheus registry:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Nếu dự án dùng Maven, thêm các dependency tương đương với cùng phiên bản Spring Boot BOM. Không tự ghim phiên bản Micrometer khác với phiên bản do Spring Boot quản lý nếu không có lý do tương thích rõ ràng.

Cấu hình endpoint quản trị trong profile vận hành:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        oauth.server.endpoint.requests: true
~~~

**/actuator/metrics** hỗ trợ kiểm tra meter trong lúc phát triển; **/actuator/prometheus** xuất số liệu theo định dạng Prometheus. Chỉ cho phép hệ thống giám sát nội bộ truy cập endpoint quản trị. Không mở metrics endpoint công khai cùng với API người dùng nếu chưa có lớp xác thực và network policy phù hợp.

Với request duration, dùng Timer thay vì chỉ tăng Counter. Timer tự ghi số lần đo và tổng thời gian, đồng thời có thể xuất histogram để tính percentile. Các tag cần có mặt ngay khi tạo meter; không thêm tag động sau đó.

## 3. Chuẩn hóa endpoint, grant type, client và outcome

Trước khi ghi metrics, chuyển dữ liệu request thành các nhãn có giới hạn:

- Endpoint lấy từ danh sách route OAuth/OIDC đã cấu hình. Ví dụ **/oauth2/token** thành **token**, **/oauth2/authorize** thành **authorize**.
- Grant type lấy từ **grant_type** ở token request. Với authorization endpoint, **response_type=code** có thể được ánh xạ thành **authorization_code**; endpoint không gắn grant type dùng **none**.
- Client được ánh xạ từ RegisteredClient sang nhãn đã định nghĩa trong cấu hình vận hành. Không dùng trực tiếp mọi giá trị **client_id** do request gửi lên làm tag.
- Outcome được xác định từ status sau khi filter chain xử lý xong: 2xx là **success**, 3xx là **redirect**, 4xx là **client_error**, 5xx là **server_error**; exception không được xử lý thành response là **exception**.

Ví dụ bảng ánh xạ client:

~~~java
Map<String, String> clientMetricLabels = Map.of(
        "browser-public-client", "browser_public",
        "orders-service", "orders_service",
        "admin-console", "admin_console"
);
~~~

Client chưa được nhận diện hoặc không thuộc allowlist được gán **unresolved**. Với confidential client dùng HTTP Basic, **client_id** thường nằm trong Authorization header chứ không nằm ở form parameter. Vì vậy, khi xác thực thành công, hãy lấy RegisteredClient từ authentication do Spring Authorization Server tạo ra. Với request lỗi trước khi xác thực xong, nhãn client có thể là **unresolved**; không cố ghi raw credential để làm dashboard chi tiết hơn.

## 4. Đo request OAuth/OIDC bằng filter

Các endpoint token và authorization của Spring Authorization Server được xử lý bởi security filter chain, không phải Spring MVC controller thông thường. Một cách tích hợp là thêm **OncePerRequestFilter** vào đúng Authorization Server SecurityFilterChain, trước client authentication filter để đo được cả request xác thực thất bại. Filter chỉ ghi metrics cho các route được allowlist.

Ví dụ dưới đây đo thời gian xử lý, đồng thời gắn endpoint, grant type, client và outcome:

~~~java
public final class OAuthEndpointMetricsFilter extends OncePerRequestFilter {

    private static final Map<String, String> ENDPOINTS = Map.of(
            "/oauth2/authorize", "authorize",
            "/oauth2/token", "token",
            "/oauth2/introspect", "introspect",
            "/oauth2/revoke", "revoke",
            "/oauth2/jwks", "jwks",
            "/userinfo", "userinfo"
    );

    private static final Set<String> GRANT_TYPES = Set.of(
            "authorization_code",
            "client_credentials",
            "refresh_token",
            "urn:ietf:params:oauth:grant-type:token-exchange"
    );

    private final MeterRegistry meterRegistry;
    private final Map<String, String> clientMetricLabels;

    public OAuthEndpointMetricsFilter(
            MeterRegistry meterRegistry,
            Map<String, String> clientMetricLabels) {
        this.meterRegistry = meterRegistry;
        this.clientMetricLabels = Map.copyOf(clientMetricLabels);
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !ENDPOINTS.containsKey(request.getServletPath());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String endpoint = ENDPOINTS.get(request.getServletPath());
        String grantType = resolveGrantType(request, endpoint);
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "exception";

        try {
            filterChain.doFilter(request, response);
            outcome = resolveOutcome(response.getStatus());
        } catch (IOException | ServletException | RuntimeException ex) {
            outcome = "exception";
            throw ex;
        } finally {
            String client = resolveClientLabel(request);
            sample.stop(Timer.builder("oauth.server.endpoint.requests")
                    .description("OAuth and OIDC endpoint request duration")
                    .tag("endpoint", endpoint)
                    .tag("grant_type", grantType)
                    .tag("client", client)
                    .tag("outcome", outcome)
                    .register(meterRegistry));
        }
    }

    private String resolveGrantType(
            HttpServletRequest request, String endpoint) {
        if ("authorize".equals(endpoint)) {
            return "code".equals(request.getParameter("response_type"))
                    ? "authorization_code" : "other";
        }
        if (!"token".equals(endpoint)) {
            return "none";
        }
        String requestedGrant = request.getParameter("grant_type");
        return requestedGrant != null && GRANT_TYPES.contains(requestedGrant)
                ? requestedGrant : "other";
    }

    private String resolveClientLabel(HttpServletRequest request) {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication instanceof OAuth2ClientAuthenticationToken clientAuth
                && clientAuth.isAuthenticated()
                && clientAuth.getRegisteredClient() != null) {
            String clientId = clientAuth.getRegisteredClient().getClientId();
            return clientMetricLabels.getOrDefault(clientId, "unresolved");
        }

        String requestedClientId = request.getParameter("client_id");
        if (requestedClientId == null || requestedClientId.isBlank()) {
            return "unresolved";
        }
        return clientMetricLabels.getOrDefault(requestedClientId, "unresolved");
    }

    private String resolveOutcome(int status) {
        if (status >= 200 && status < 300) return "success";
        if (status >= 300 && status < 400) return "redirect";
        if (status >= 400 && status < 500) return "client_error";
        if (status >= 500) return "server_error";
        return "other";
    }
}
~~~

Các import chính gồm **java.util.Map**, **java.util.Set**, **io.micrometer.core.instrument.MeterRegistry**, **Timer**, **jakarta.servlet.FilterChain**, **ServletException**, **HttpServletRequest**, **HttpServletResponse**, **org.springframework.web.filter.OncePerRequestFilter**, **Authentication**, **SecurityContextHolder** và **OAuth2ClientAuthenticationToken** từ package **org.springframework.security.oauth2.server.authorization.authentication**. Filter được thêm bằng **OAuth2ClientAuthenticationFilter** từ package **org.springframework.security.oauth2.server.authorization.web.authentication**. Đoạn cấu hình giới hạn cardinality dùng **io.micrometer.core.instrument.config.MeterFilter** và **org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer**.

Danh sách **ENDPOINTS** là ví dụ cho endpoint URI mặc định. Nếu ứng dụng thay đổi URI trong **AuthorizationServerSettings**, hãy cập nhật bảng ánh xạ theo cấu hình thực tế. Không dùng toàn bộ **request.getRequestURI()** làm tag vì URL không nhận diện có thể tạo ra vô số giá trị.

Trong ví dụ, **OAuth2ClientAuthenticationToken** cho phép lấy RegisteredClient sau khi client authentication thành công. Với request lỗi trước bước xác thực, filter chỉ có thể dùng client_id không đáng tin cậy từ request nếu nó có mặt và ánh xạ qua allowlist; còn lại dùng **unresolved**. Điều này tránh gắn một danh tính đã xác thực cho request chỉ mới khai báo client ID.

Đặt filter trong Authorization Server SecurityFilterChain, trước **OAuth2ClientAuthenticationFilter**:

~~~java
http.addFilterBefore(
        oauthEndpointMetricsFilter,
        OAuth2ClientAuthenticationFilter.class
);
~~~

Chỉ thêm filter vào chain xử lý endpoint Authorization Server. Nếu filter được khai báo thành bean Filter trong Spring Boot, hãy tắt đăng ký servlet container tự động bằng **org.springframework.boot.web.servlet.FilterRegistrationBean#setEnabled(false)** rồi thêm thủ công vào security chain. Nếu không, filter có thể chạy hai lần hoặc chạy ngoài phạm vi bảo mật dự kiến.

Filter mẫu đo toàn bộ request đến các route đã allowlist. Khi thêm endpoint mới hoặc endpoint tùy chỉnh, hãy bổ sung ánh xạ tĩnh và test tương ứng. Với OIDC logout hoặc các endpoint đặc thù khác, xác định rõ route và outcome hợp lệ trước khi thêm vào cùng meter.

## 5. Giới hạn cardinality và bảo vệ dữ liệu nhạy cảm

Micrometer tạo meter cho mỗi tổ hợp tag. Nếu có 8 endpoint, 5 grant type, 100 client và 5 outcome, một meter có thể phát sinh đến 20.000 tổ hợp trước khi tính thêm các tag khác. Khi client ID, user ID hoặc URL tùy ý được đưa vào tag, số meter có thể tăng không kiểm soát và làm tăng RAM, chi phí Prometheus cũng như thời gian truy vấn.

Áp dụng các quy tắc sau:

- Chỉ dùng endpoint, grant type và outcome từ tập giá trị allowlist.
- Chỉ dùng nhãn client đã chuẩn hóa; đặt giới hạn số client được đưa vào dashboard chi tiết.
- Không dùng subject, username, email, tenant ID, session ID hoặc địa chỉ IP làm tag.
- Không dùng access token, refresh token, authorization code, client secret, state, code verifier hoặc nội dung request làm tag hay log field.
- Không dùng redirect URI, query string, exception message hoặc chuỗi lỗi tự do làm tag.
- Không thêm scope hoặc tổ hợp scope vào tag nếu không có nhu cầu đo lường rõ ràng; dùng log/audit đã lọc dữ liệu hoặc báo cáo riêng khi cần.

Có thể đặt giới hạn tag client ở cấp MeterRegistry:

~~~java
@Bean
MeterRegistryCustomizer<MeterRegistry> oauthMetricCardinalityLimit() {
    return registry -> registry.config().meterFilter(
            MeterFilter.maximumAllowableTags(
                    "oauth.server.endpoint.requests",
                    "client",
                    30,
                    MeterFilter.deny()
            )
    );
}
~~~

**MeterFilter** là lớp bảo vệ bổ sung. Nó không thay thế việc chuẩn hóa tag trước khi ghi. Nếu số client hợp lệ lớn hơn giới hạn, hãy chọn một nhóm client quan trọng để gắn nhãn riêng và gom phần còn lại thành **other_client**, đồng thời cung cấp một báo cáo riêng cho phân tích theo client nếu cần.

Metrics là số liệu tổng hợp. Audit log là bản ghi từng sự kiện cần truy vết. Nếu cần biết ai đã chấp thuận consent hoặc client nào đã bị thu hồi, ghi audit event có kiểm soát quyền truy cập, retention và masking. Không cố biến metrics thành kho lưu trữ sự kiện chi tiết bằng cách đưa định danh cá nhân vào tag.

## 6. Đọc metrics trong Prometheus

Micrometer Timer có thể được Prometheus registry xuất thành các series như:

- **oauth_server_endpoint_requests_seconds_count**: tổng số lần đo.
- **oauth_server_endpoint_requests_seconds_sum**: tổng thời gian xử lý.
- **oauth_server_endpoint_requests_seconds_bucket**: histogram thời gian theo bucket.

Tên metric được chuyển từ dấu chấm sang dấu gạch dưới và đơn vị thời gian được biểu diễn bằng giây. Có thể dùng các truy vấn PromQL sau.

**Tốc độ request theo endpoint, grant type, client và kết quả:**

~~~promql
sum by (endpoint, grant_type, client, outcome) (
  rate(oauth_server_endpoint_requests_seconds_count[5m])
)
~~~

**Độ trễ p95 theo endpoint và grant type:**

~~~promql
histogram_quantile(
  0.95,
  sum by (le, endpoint, grant_type) (
    rate(oauth_server_endpoint_requests_seconds_bucket[5m])
  )
)
~~~

**Tỷ lệ request lỗi của các endpoint OAuth/OIDC:**

~~~promql
sum(
  rate(oauth_server_endpoint_requests_seconds_count{
    outcome=~"client_error|server_error|exception"
  }[5m])
)
/
clamp_min(
  sum(rate(oauth_server_endpoint_requests_seconds_count[5m])),
  0.000001
)
~~~

**Tỷ lệ lỗi theo client:**

~~~promql
sum by (client) (
  rate(oauth_server_endpoint_requests_seconds_count{
    outcome=~"client_error|server_error|exception"
  }[5m])
)
/
clamp_min(
  sum by (client) (
    rate(oauth_server_endpoint_requests_seconds_count[5m])
  ),
  0.000001
)
~~~

Với truy vấn tỷ lệ lỗi, cần chọn đúng nhóm endpoint và outcome cho dashboard. Một redirect 302 ở authorization endpoint thường là một phần bình thường của luồng đăng nhập, không nên tính là lỗi. Tương tự, một số lỗi 4xx có thể là request sai thông tin từ client; chúng vẫn là lỗi giao thức cần quan sát nhưng không nhất thiết là lỗi availability của server.

## 7. Thiết kế dashboard theo nhu cầu vận hành

Một dashboard có thể chia thành bốn khu vực:

| Khu vực | Biểu đồ | Câu hỏi cần trả lời |
|---|---|---|
| Tổng quan endpoint | Request rate và p95/p99 theo endpoint | Lưu lượng và độ trễ đang tăng ở đâu? |
| Grant type | Request rate và tỷ lệ lỗi theo grant | Client Credentials, Authorization Code hay Refresh Token gặp vấn đề? |
| Client | Top client theo request rate và lỗi | Client nào retry nhiều hoặc gửi request không hợp lệ? |
| Outcome | Success, redirect, client_error, server_error, exception | Lỗi đến từ request, xác thực, grant processing hay server? |

Đối với token endpoint, theo dõi riêng Client Credentials và Refresh Token vì chúng có mô hình xác thực và vòng đời khác nhau. Một đợt tăng **invalid_client** có thể liên quan đến secret bị xoay mà client chưa cập nhật; tăng **invalid_grant** có thể liên quan đến authorization code hết hạn, PKCE verifier sai hoặc refresh token bị replay. Metrics tổng hợp giúp phát hiện xu hướng, còn audit event và log đã masking hỗ trợ điều tra từng trường hợp.

Nên có dashboard so sánh trước và sau mỗi lần triển khai. Nếu request rate giữ nguyên nhưng p95 tăng đột ngột, kiểm tra dependency như database, key store, DNS, introspection hoặc JWKS. Nếu chỉ một client có lỗi tăng, kiểm tra cấu hình client, secret rotation và retry policy của client đó trước khi quy kết lỗi cho toàn bộ Authorization Server.

## 8. Thiết lập cảnh báo có ngữ cảnh

Không nên cảnh báo chỉ vì số lượng 4xx tăng tuyệt đối, bởi một số client có thể gửi request không hợp lệ trong quá trình hoạt động bình thường. Hãy kết hợp tỷ lệ, lưu lượng tối thiểu và thời gian kéo dài:

- **Server error:** cảnh báo khi tỷ lệ server_error hoặc exception vượt ngưỡng trong vài phút và có đủ request để kết luận.
- **Độ trễ token endpoint:** cảnh báo khi p95 vượt SLO đã thống nhất trong một cửa sổ liên tục.
- **Client failure spike:** cảnh báo theo client đã allowlist khi client_error tăng bất thường so với baseline.
- **Traffic drop:** cảnh báo khi lưu lượng authorization/token giảm đột ngột nếu hệ thống có mức tải dự kiến.
- **Unresolved client spike:** cảnh báo khi request không xác định client tăng mạnh, có thể chỉ ra cấu hình client lỗi hoặc request dò quét.

Ví dụ một biểu thức PromQL đơn giản cho tỷ lệ server error:

~~~promql
sum(rate(oauth_server_endpoint_requests_seconds_count{
  outcome=~"server_error|exception"
}[5m]))
/
clamp_min(
  sum(rate(oauth_server_endpoint_requests_seconds_count[5m])),
  0.000001
)
> 0.02
~~~

Ngưỡng 2% chỉ là giá trị minh họa. Chọn ngưỡng thực tế dựa trên SLO, traffic nền, loại endpoint và mức độ ảnh hưởng. Không áp cùng ngưỡng cho mọi endpoint: authorization endpoint có thể có redirect bình thường, còn token endpoint cần tỷ lệ lỗi giao thức và server error được phân tích riêng.

## 9. Kiểm thử metrics

Metrics phải được kiểm tra như một phần của cấu hình quan sát. Dùng **SimpleMeterRegistry** trong unit test hoặc registry đang được cấu hình trong Spring test context. Một bài test token endpoint thành công có thể xác minh Timer được tạo với đúng tag:

~~~java
Timer timer = meterRegistry.find("oauth.server.endpoint.requests")
        .tags(
                "endpoint", "token",
                "grant_type", "client_credentials",
                "client", "orders_service",
                "outcome", "success"
        )
        .timer();

assertThat(timer).isNotNull();
assertThat(timer.count()).isEqualTo(1);
assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isGreaterThanOrEqualTo(0);
~~~

Tạo thêm các bài kiểm thử cho:

- Token request dùng grant type không được biết: tag phải là **other**, không sinh tag tùy ý.
- Request đến authorization endpoint có **response_type=code**: grant tag là **authorization_code**.
- Request authorization chuyển hướng đến login/consent: outcome là **redirect**.
- Client hợp lệ: tag client là nhãn đã cấu hình, không phải client ID thô.
- Client không xác thực được: tag client là **unresolved** nếu không thể xác định danh tính đáng tin cậy.
- Token endpoint trả 4xx hoặc 5xx: outcome phản ánh đúng nhóm status.
- Request đến URL ngoài allowlist: filter không ghi meter OAuth endpoint.
- Filter chỉ chạy một lần trong Authorization Server SecurityFilterChain, không bị servlet container đăng ký thêm lần nữa.

Kiểm tra endpoint **/actuator/prometheus** để bảo đảm meter có thể scrape được. Đồng thời xác minh response metrics không chứa access token, refresh token, authorization code, client secret, username hoặc email.

## 10. Kết hợp metrics, log và audit

Ba loại dữ liệu này phục vụ các câu hỏi khác nhau:

| Nguồn | Mục đích | Nội dung phù hợp |
|---|---|---|
| Metrics | Xu hướng và sức khỏe tổng thể | Count, duration, endpoint, grant type, nhãn client, outcome |
| Application log | Chẩn đoán lỗi kỹ thuật | Correlation ID, mã lỗi đã chuẩn hóa, exception class, dependency status |
| Audit event | Truy vết hành động bảo mật | Client đã xác thực, hành động cấp/thu hồi/consent, thời điểm, kết quả và actor phù hợp |

Không ghi token hoặc secret vào bất kỳ nguồn nào. Với log, dùng correlation ID để nối request giữa các service. Với audit event, giới hạn quyền đọc và đặt retention theo chính sách. Với metrics, chỉ giữ tag có cardinality thấp để có thể lưu trữ và truy vấn lâu dài.

## 11. Checklist triển khai

- Actuator và Micrometer registry được cấu hình theo phiên bản Spring Boot của ứng dụng.
- Các endpoint OAuth/OIDC được ánh xạ thành nhãn tĩnh và có thể cập nhật khi endpoint URI thay đổi.
- Grant type chỉ nhận giá trị đã allowlist; giá trị không xác định được gom vào **other**.
- Client ID được ánh xạ thành nhãn vận hành ổn định; request chưa xác thực dùng **unresolved**.
- Outcome phân biệt success, redirect, client error, server error và exception.
- Timer ghi cả request count và duration; histogram được bật cho các meter cần percentile.
- Cardinality được giới hạn ở cấp thiết kế và có MeterFilter bảo vệ bổ sung.
- Metrics endpoint chỉ được Prometheus hoặc hệ thống giám sát nội bộ truy cập.
- Dashboard có thể lọc theo endpoint, grant type, client và outcome.
- Cảnh báo phân biệt lỗi giao thức của client với lỗi availability của server.
- Unit/integration test xác minh tag, outcome, endpoint allowlist và không rò rỉ dữ liệu nhạy cảm.

Khi metrics được chuẩn hóa theo bốn chiều này, nhóm vận hành có thể xác định nhanh endpoint hoặc grant type đang gặp vấn đề, khoanh vùng client liên quan và theo dõi tác động của thay đổi cấu hình. Kết hợp số liệu tổng hợp với log và audit event đã kiểm soát sẽ tạo nền tảng quan sát đủ sâu cho Authorization Server đang chạy thực tế.

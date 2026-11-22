# Tạo giao diện consent hiển thị client và các scope được yêu cầu

## 1. Mục tiêu và bối cảnh

Khi xây dựng **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** với **Spring Security**, **Spring Authorization Server** và **Spring Boot**, trang **consent** là nơi người dùng xem ứng dụng nào xin quyền truy cập và cân nhắc những **scope** nào sẽ được chấp thuận. Đây là một bước quan trọng của Authorization Code Flow: người dùng cần hiểu mình đang cho phép ứng dụng làm gì, còn Authorization Server phải kiểm tra quyết định đó trong ngữ cảnh authorization request hợp lệ.

Ví dụ: người dùng Alice đăng nhập vào Authorization Server tại <code>https://auth.example.com</code>. Ứng dụng <code>orders-web</code> yêu cầu <code>orders.read</code> và <code>orders.write</code> để gọi Orders API. Trên màn hình consent, Alice nên thấy tên ứng dụng đã đăng ký, mô tả từng quyền bằng tiếng Việt, những quyền đã cấp trước đây nếu có, cùng hai lựa chọn **Chấp thuận** và **Từ chối**. Việc hiển thị UI hoặc gửi biểu mẫu không được biến scope do browser tự khai thành quyền được cấp.

Sau bài học, bạn có thể:

1. Giải thích lúc nào Authorization Server yêu cầu consent và dữ liệu nào cần hiển thị.
2. Dùng <code>OAuth2AuthorizationEndpointConfigurer.consentPage()</code> để chọn một trang consent tùy chỉnh.
3. Tạo một Spring MVC controller và template Thymeleaf thể hiện client, scope được yêu cầu và scope đã được chấp thuận.
4. Gửi quyết định bằng HTTP POST về đúng Authorization Endpoint với <code>client_id</code>, <code>state</code> và các tham số <code>scope</code>.
5. Phân biệt consent state, OAuth client state và CSRF token của form HTTP.
6. Phòng chống hiển thị sai quyền, XSS, CSRF, giả mạo client, giả mạo scope và consent không hợp lệ.
7. Kiểm thử toàn bộ luồng Authorization Code + PKCE/OIDC thay vì chỉ kiểm thử template.

**Phạm vi phiên bản:** Ví dụ dùng những API thường gặp của Spring Authorization Server 1.x, gồm <code>OAuth2AuthorizationServerConfigurer.authorizationServer()</code>, <code>HttpSecurity.with(...)</code> và <code>consentPage(...)</code>. Các bản Spring Security tích hợp Authorization Server mới hơn có thể đổi package hoặc cách cấu hình. Những code block dưới đây là ví dụ học tập có chủ đích lược bỏ import và các bean hạ tầng không trực tiếp liên quan đến consent.

## 2. Luồng consent trong Authorization Code Flow

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Alice (Browser)
    participant C as orders-web (OAuth Client)
    participant AS as Authorization Endpoint
    participant UI as Custom Consent UI
    participant R as RegisteredClientRepository
    participant CS as OAuth2AuthorizationConsentService
    C->>U: Chuyển hướng để xin quyền
    U->>AS: GET /oauth2/authorize + client_id, scope, state, PKCE
    AS->>R: Kiểm tra client, grant, redirect_uri và scope
    AS-->>U: Yêu cầu đăng nhập nếu chưa xác thực
    U->>AS: Tiếp tục authorization sau login
    AS->>CS: Tra consent đã lưu
    AS-->>U: 302 /oauth2/consent?client_id=...&scope=...&state=...
    U->>UI: GET /oauth2/consent
    UI->>R: Lấy tên client từ đăng ký đáng tin cậy
    UI->>CS: Lấy scopes đã cấp trước đây
    UI-->>U: HTML với scopes và lựa chọn Chấp thuận/Từ chối
    U->>AS: POST /oauth2/authorize với quyết định
    AS->>AS: Xác minh session, state, client và quyền hợp lệ
    AS->>CS: Lưu/cập nhật consent nếu hợp lệ
    AS-->>U: Redirect về client với code hoặc lỗi
~~~

Consent là bước **sau khi xác thực End-User** và kiểm tra authorization request. Hệ thống không nhất thiết hiện trang này mỗi lần: nếu đã có consent đủ phạm vi và chính sách cho phép tái sử dụng, Authorization Server có thể bỏ qua. Nếu người dùng từ chối, server phải xử lý một kết quả không được cấp quyền theo giao thức thay vì phát code như khi chấp thuận.

### 2.1. Consent, authentication và authorization là các quyết định khác nhau

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| User authentication | Ai đang đăng nhập? | Alice đã đăng nhập thành công. |
| Client registration | Client được yêu cầu scope nào? | <code>orders-web</code> có <code>orders.read</code>, <code>orders.write</code>. |
| Consent | Alice đã đồng ý scope nào cho client đó? | Alice chọn <code>orders.read</code>. |
| Authorization policy | Quyền đó hiện được phép theo chính sách không? | Tài khoản Alice không bị khóa và có thể yêu cầu quyền đọc. |
| Token issuance | Token nào được cấp, với phạm vi nào? | Access token chỉ có các scope hợp lệ đã cấp. |
| Resource authorization | Alice có được đọc đơn hàng cụ thể không? | Orders API kiểm tra quyền trên order 123. |

Consent không cấp quyền sở hữu mọi tài nguyên, không chứng minh client đã được đăng ký đúng và không tự tạo một phiên đăng nhập. Với **Client Credentials**, thường không có End-User đứng trước UI consent; quyền service client được quản lý bằng đăng ký client và chính sách máy chủ.

### 2.2. Khi nào cần hỏi consent?

Việc hiển thị có thể phụ thuộc <code>ClientSettings.requireAuthorizationConsent(true)</code>, consent trước đó, scope mới trong request, chính sách OIDC và các extension đang sử dụng. Đừng tự giả định <code>requireAuthorizationConsent(true)</code> đồng nghĩa “hiện trang ở tất cả request”; cũng đừng cho client tự yêu cầu một scope chưa đăng ký rồi hiển thị như thể nó hợp lệ.

## 3. Thiết kế thông tin trên màn hình consent

Mục đích đầu tiên của trang là giúp người dùng trả lời được **“Ứng dụng nào đang yêu cầu quyền gì?”**.

| Thông tin | Nguồn phù hợp | Cách trình bày |
| --- | --- | --- |
| Tên ứng dụng | <code>RegisteredClient.getClientName()</code> | “Orders Portal”, được escape HTML. |
| ID ứng dụng | <code>RegisteredClient.getClientId()</code> | <code>orders-web</code> để hỗ trợ nhận diện. |
| Người dùng đang đăng nhập | <code>Principal</code>/<code>Authentication</code> phía Authorization Server | Tài khoản đang sử dụng, đặc biệt khi có nhiều account. |
| Scope cần xét duyệt | Danh sách <code>scope</code> do Authorization Server chuyển đến custom consent page, sau khi kiểm tra với client registration | Checkbox từng quyền, nhãn rõ ràng. |
| Mô tả scope | Danh mục mô tả do server quản lý | “Xem đơn hàng được phép xem”, không chỉ <code>orders.read</code>. |
| Consent cũ | <code>OAuth2AuthorizationConsentService</code> theo client record ID và principal | Nhóm “Quyền đã cấp trước đây”. |
| Quyết định | Form chấp thuận và từ chối | Không ẩn lựa chọn từ chối hoặc chọn hộ mọi quyền. |

### 3.1. Viết tên quyền thân thiện nhưng trung thực

| Scope kỹ thuật | Tên hiển thị | Diễn giải |
| --- | --- | --- |
| <code>orders.read</code> | Xem đơn hàng | Đọc các đơn hàng mà người dùng được phép truy cập. |
| <code>orders.write</code> | Chỉnh sửa đơn hàng | Tạo hoặc cập nhật đơn hàng trong phạm vi được phép. |
| <code>profile</code> | Hồ sơ cơ bản | Yêu cầu thông tin hồ sơ có thể được cung cấp theo OIDC. |
| <code>email</code> | Địa chỉ email | Yêu cầu thông tin email khi có và được phép cung cấp. |
| <code>openid</code> | Đăng nhập bằng tài khoản này | Yêu cầu xác thực OIDC, không phải quyền ghi API. |

Nhãn scope phải được xem xét theo quyền thật của Resource Server. Không mô tả <code>orders.read</code> là “Xem tất cả đơn hàng” khi API vẫn giới hạn theo sở hữu/tenant. Scope OIDC <code>email</code> không bảo đảm mọi token sẽ có email claim; OIDC scope và thông tin phát hành thực tế còn phụ thuộc chính sách/consent.

### 3.2. Client name không tự chứng minh thương hiệu

<code>getClientName()</code> là **metadata trong RegisteredClient**, thường do quản trị viên đăng ký hoặc người quản lý client nhập. Với các client bên thứ ba, không hiển thị logo/domain hoặc dấu “Đã xác minh” chỉ dựa trên tên hiển thị. Nếu có logo và website, chúng cần được rà soát, lưu ở nguồn đã phê duyệt và kiểm soát URL; tránh tải ảnh bên ngoài do client tự chỉ định trong lúc render consent.

## 4. Cấu hình trang consent tùy chỉnh bằng Java DSL

### 4.1. Đăng ký client yêu cầu consent

Ví dụ phần thiết lập của một <code>RegisteredClient</code>:

~~~java
RegisteredClient ordersClient = RegisteredClient
    .withId("orders-web-record-001")
    .clientId("orders-web")
    // Cấu hình authentication method, grant và redirect URI thực tế.
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .scope(OidcScopes.OPENID)
    .scope(OidcScopes.PROFILE)
    .scope("orders.read")
    .scope("orders.write")
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .requireAuthorizationConsent(true)
        .build())
    .build();
~~~

Đây là **đoạn trích minh họa**, chưa phải RegisteredClient hoàn chỉnh để chạy. Cần thêm redirect URI hợp lệ, client authentication phù hợp loại client và các service/key của Authorization Server. Với public client, không nhúng secret trong trình duyệt/mobile. PKCE và consent bảo vệ hai khía cạnh riêng; PKCE không thay consent.

### 4.2. Cấu hình SecurityFilterChain

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server -> server
                .authorizationEndpoint(endpoint ->
                    endpoint.consentPage("/oauth2/consent"))
                .oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .exceptionHandling(exceptions -> exceptions
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)))
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/oauth2/consent")
                    .authenticated()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Giải thích:** <code>getEndpointsMatcher()</code> chọn các endpoint giao thức thực sự do Authorization Server quản lý, bao gồm <code>/oauth2/authorize</code>. Custom controller <code>GET /oauth2/consent</code> do **chain web** bảo vệ và cần một người dùng đã đăng nhập. Spring Authorization Server sẽ điều hướng đến URI trong <code>consentPage()</code> khi cần, nhưng **không tự tạo controller hay template tùy chỉnh**.

Không dùng <code>securityMatcher("/oauth2/**")</code> thay <code>getEndpointsMatcher()</code> một cách tùy ý: cách này có thể bắt nhầm URL của trang consent hoặc bỏ sót endpoint OIDC ở những đường dẫn khác. Dùng <code>@Order</code> để đặt chain endpoint cụ thể trước chain fallback.

Trong ví dụ này, <code>oauth2ResourceServer().jwt()</code> phục vụ các endpoint OIDC cần JWT/Bearer khi tính năng tương ứng được bật; yêu cầu <code>JwtDecoder</code> phù hợp. Các bean <code>RegisteredClientRepository</code>, authorization/consent service, user authentication, JWK và OIDC infrastructure phải được cấu hình riêng.

### 4.3. Đường dẫn hiển thị và đường dẫn nhận quyết định

| Bước | Method/path | Người xử lý |
| --- | --- | --- |
| Bắt đầu xin quyền | <code>GET /oauth2/authorize</code> | Authorization Endpoint của Spring Authorization Server. |
| Hiển thị form | <code>GET /oauth2/consent</code> | Spring MVC controller và Thymeleaf template do ứng dụng viết. |
| Gửi quyết định consent | <code>POST /oauth2/authorize</code> | Authorization Endpoint của Spring Authorization Server. |

**Lưu ý:** Giá trị <code>/oauth2/authorize</code> là path mặc định. Nếu thay đổi bằng <code>AuthorizationServerSettings</code>, form phải POST tới **<code>getAuthorizationEndpoint()</code>** thực tế; không hard-code path cũ.

## 5. Ba tham số của URL consent

Theo API <code>OAuth2AuthorizationEndpointConfigurer.consentPage()</code>, Authorization Server redirect tới consent page với các tham số <code>client_id</code>, <code>scope</code>, <code>state</code>. Ví dụ:

~~~http
HTTP/1.1 302 Found
Location: /oauth2/consent?client_id=orders-web&scope=orders.read%20orders.write&state=opaque-consent-state
~~~

| Tham số | Ý nghĩa |
| --- | --- |
| <code>client_id</code> | Client ID ở mức giao thức, dùng để tra RegisteredClient. |
| <code>scope</code> | Danh sách scope của ngữ cảnh consent, phân tách bằng khoảng trắng. |
| <code>state</code> | Token tương quan/chống giả mạo của **bước consent** do Authorization Server chuyển tới; phải gửi lại nguyên vẹn. |

Những dữ liệu này được đặt trong URL nên **không tin tưởng trực tiếp**. Người dùng có thể sửa query. Controller dùng chúng để hiển thị, nhưng khi POST, Authorization Server phải ràng buộc lại với authorization request chưa hoàn tất, phiên người dùng và chính sách đã lưu.

### 5.1. Ba giá trị dễ bị nhầm

1. **OAuth client state**: do client sinh ở yêu cầu <code>/oauth2/authorize</code> ban đầu; client so sánh với state trong redirect kết quả.
2. **Consent state**: do Authorization Server chuyển tới <code>/oauth2/consent</code>, dùng để nối quyết định của người dùng với authorization đang chờ; **không được thay bằng OAuth client state**.
3. **Servlet CSRF token**: thường được Spring Security cung cấp dưới attribute <code>_csrf</code>, bảo vệ POST form ở những URL nằm trong phạm vi CSRF filter.

Consent state và CSRF token của Servlet **không phải một giá trị**, dù tài liệu API mô tả consent state là cơ chế chống CSRF cho chính luồng consent. Nếu form cần CSRF token của Servlet thì truyền cả hai theo đúng chức năng.

### 5.2. Không hiển thị tất cả scope đã đăng ký như thể đang được yêu cầu

<code>RegisteredClient.getScopes()</code> trả về mọi scope client có thể xin. Request hiện tại có thể chỉ xin một tập con. Ví dụ client được đăng ký <code>orders.read</code>, <code>orders.write</code>, <code>reports.export</code>, nhưng redirect chỉ có <code>orders.read</code>: UI chỉ nên cho phép xét duyệt scope thực sự thuộc ngữ cảnh consent, không thêm <code>reports.export</code> vào checkbox.

## 6. Controller Spring MVC lấy thông tin client và các scope

Controller dưới đây chỉ **chuẩn bị dữ liệu hiển thị**; khi người dùng submit, nó **không** trực tiếp gọi <code>OAuth2AuthorizationConsentService.save()</code> và cũng **không** tự phát authorization code. Đầu vào và scope được kiểm tra lại khi Authorization Endpoint tiếp nhận POST.

~~~java
@Controller
public class ConsentPageController {

    private static final Map<String, String> TITLES = Map.of(
        "openid", "Đăng nhập bằng tài khoản này",
        "profile", "Hồ sơ cơ bản",
        "email", "Địa chỉ email",
        "orders.read", "Xem đơn hàng",
        "orders.write", "Chỉnh sửa đơn hàng"
    );

    private static final Map<String, String> DESCRIPTIONS = Map.of(
        "openid", "Xác thực bằng OpenID Connect.",
        "profile", "Yêu cầu thông tin hồ sơ được phép cung cấp.",
        "email", "Yêu cầu thông tin email theo chính sách.",
        "orders.read", "Đọc các đơn hàng bạn được phép xem.",
        "orders.write", "Cập nhật các đơn hàng bạn được phép sửa."
    );

    private final RegisteredClientRepository clients;
    private final OAuth2AuthorizationConsentService consentService;

    public ConsentPageController(
            RegisteredClientRepository clients,
            OAuth2AuthorizationConsentService consentService) {
        this.clients = clients;
        this.consentService = consentService;
    }

    @GetMapping("/oauth2/consent")
    public String consentPage(
            Principal principal,
            @RequestParam("client_id") String clientId,
            @RequestParam("scope") String scopeParameter,
            @RequestParam("state") String consentState,
            Model model,
            HttpServletResponse response) {

        // Chain web đã yêu cầu Authentication; kiểm tra phòng vệ.
        if (principal == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        RegisteredClient client = clients.findByClientId(clientId);
        if (client == null || !StringUtils.hasText(consentState)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }

        Set<String> requestedScopes = Arrays.stream(
                scopeParameter.split("\\s+"))
            .filter(StringUtils::hasText)
            .collect(Collectors.toCollection(LinkedHashSet::new));

        // Chỉ kiểm tra cho việc render; AS phải xác thực POST độc lập.
        if (!client.getScopes().containsAll(requestedScopes)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }

        OAuth2AuthorizationConsent previous = consentService.findById(
            client.getId(), principal.getName());

        Set<String> approved = previous == null
            ? Set.of()
            : previous.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(authority -> authority.startsWith("SCOPE_"))
                .map(authority -> authority.substring("SCOPE_".length()))
                .filter(client.getScopes()::contains)
                .collect(Collectors.toSet());

        List<ScopeItem> newScopes = requestedScopes.stream()
            .filter(scope -> !approved.contains(scope))
            .map(ConsentPageController::scopeItem)
            .toList();

        List<ScopeItem> previousScopes = approved.stream()
            .sorted()
            .map(ConsentPageController::scopeItem)
            .toList();

        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setHeader(HttpHeaders.PRAGMA, "no-cache");

        model.addAttribute("clientName", client.getClientName());
        model.addAttribute("clientId", client.getClientId());
        model.addAttribute("consentState", consentState);
        model.addAttribute("userName", principal.getName());
        model.addAttribute("newScopes", newScopes);
        model.addAttribute("previousScopes", previousScopes);

        return "oauth2-consent";
    }

    private static ScopeItem scopeItem(String scope) {
        return new ScopeItem(
            scope,
            TITLES.getOrDefault(scope, "Phạm vi: " + scope),
            DESCRIPTIONS.getOrDefault(
                scope, "Quyền kỹ thuật cần được mô tả và xét duyệt.")
        );
    }

    public record ScopeItem(
        String value, String title, String description) {}
}
~~~

Các import không được trình bày để tập trung vào logic. <code>ScopeItem</code> là Java record dùng với Java 17+. <code>newScopes</code> chỉ có những scope hiện tại chưa có trong consent đã lưu; <code>previousScopes</code> hiển thị riêng những quyền đã được đồng ý trước đây. Việc dữ liệu UI được chia nhóm **không** thay thế ngữ nghĩa kết hợp consent cũ và quyết định mới của Authorization Server.

Một số lưu ý về controller:

- <code>clients.findByClientId(clientId)</code> tra client theo **OAuth client ID**, nhưng <code>consentService.findById(client.getId(), principal.getName())</code> phải dùng **registered client record ID**.
- <code>Principal</code> phải đến từ <code>Authentication</code> đã được xác minh bởi server; không lấy username từ query để tra consent của người khác.
- Nếu không nhận diện được scope trong danh mục mô tả, production nên từ chối đăng ký scope chưa được phê duyệt thay vì để người dùng phỏng đoán ý nghĩa.
- <code>Cache-Control: no-store</code> tránh cache thông tin consent nhạy cảm trong trình duyệt/proxy; nên cấu hình thêm CSP, Referrer-Policy và kiểm soát frame.
- Khi có multi-tenancy, principal name phải có quy ước ID ổn định/không va chạm giữa các tenant. Cùng tên <code>alice</code> ở hai tổ chức không được dùng chung consent.

**Giới hạn quan trọng:** Controller chưa thể chứng minh state thuộc đúng authorization request; framework xác nhận điều này tại bước POST. Dữ liệu ở GET chỉ để render. Không sử dụng controller này để cho phép một client tự yêu cầu toàn bộ quyền đã đăng ký bằng cách sửa URL.

## 7. Template Thymeleaf cho consent page

Đặt template trong ứng dụng Spring Boot, ví dụ <code>src/main/resources/templates/oauth2-consent.html</code>. Ở bước viết bài học này, nội dung template chỉ được trình bày bên trong Markdown; không tạo file source khác.

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="referrer" content="no-referrer">
    <title>Đồng ý cấp quyền</title>
</head>
<body>
<main>
    <header>
        <h1>Xem xét quyền truy cập</h1>
        <p>
            Ứng dụng
            <strong th:text="${clientName}">Orders Portal</strong>
            (<code th:text="${clientId}">orders-web</code>)
            đang yêu cầu quyền.
        </p>
        <p>
            Bạn đang đăng nhập bằng
            <strong th:text="${userName}">alice</strong>.
        </p>
    </header>

    <!-- FORM CHẤP THUẬN: POST về Authorization Endpoint mặc định. -->
    <form method="post" th:action="@{/oauth2/authorize}">
        <input type="hidden" name="client_id" th:value="${clientId}">
        <input type="hidden" name="state" th:value="${consentState}">

        <!-- Dùng nếu Servlet CSRF filter áp dụng.
             Không nhầm _csrf với consent state. -->
        <input th:if="${_csrf != null}"
               type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">

        <fieldset>
            <legend>Quyền cần xét duyệt</legend>
            <p th:if="${#lists.isEmpty(newScopes)}">
                Không có quyền mới trong danh sách này.
            </p>
            <div th:each="item : ${newScopes}">
                <label>
                    <input type="checkbox" name="scope"
                           th:value="${item.value()}">
                    <strong th:text="${item.title()}">Xem đơn hàng</strong>
                </label>
                <p th:text="${item.description()}">
                    Đọc đơn hàng bạn được phép xem.
                </p>
            </div>
        </fieldset>

        <section th:if="${!#lists.isEmpty(previousScopes)}">
            <h2>Quyền đã cấp trước đây</h2>
            <ul>
                <li th:each="item : ${previousScopes}"
                    th:text="${item.title()}">Xem đơn hàng</li>
            </ul>
        </section>

        <button type="submit"
                th:disabled="${#lists.isEmpty(newScopes)}">
            Chấp thuận quyền đã chọn
        </button>
    </form>

    <!-- FORM TỪ CHỐI: không gửi bất kỳ scope nào. -->
    <form method="post" th:action="@{/oauth2/authorize}">
        <input type="hidden" name="client_id" th:value="${clientId}">
        <input type="hidden" name="state" th:value="${consentState}">
        <input th:if="${_csrf != null}"
               type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">
        <button type="submit">Từ chối</button>
    </form>
</main>
</body>
</html>
~~~

### 7.1. Kiểm tra chính xác các trường POST

| Trường | Bắt buộc về mặt luồng | Ý nghĩa |
| --- | --- | --- |
| <code>method="post"</code> | Có | Gửi quyết định consent tới Authorization Endpoint bằng POST. |
| <code>action="/oauth2/authorize"</code> | Có, thay theo settings nếu endpoint đổi | POST tới endpoint giao thức do AS xử lý. |
| <code>client_id</code> | Có | Client đang xin quyền; AS xác minh lại. |
| <code>state</code> | Có | Giá trị consent state từ redirect; AS đối chiếu authorization đang chờ. |
| <code>scope</code> | Có khi chấp thuận scope | Một giá trị cho mỗi checkbox được chọn, có thể lặp tên tham số. |
| <code>_csrf</code> | Theo cấu hình CSRF thực tế | Chống giả mạo form khi filter CSRF của Servlet yêu cầu. |

Ví dụ khi người dùng chọn hai checkbox:

~~~http
POST /oauth2/authorize HTTP/1.1
Content-Type: application/x-www-form-urlencoded

client_id=orders-web&state=opaque-consent-state&
scope=orders.read&scope=orders.write
~~~

Request rút gọn chưa bao gồm CSRF token ở những cấu hình yêu cầu. Trình duyệt gửi dữ liệu theo định dạng form URL encoded; hai <code>scope</code> là **hai giá trị cùng tên**, không phải một chuỗi CSV tự đặt tên.

### 7.2. Form Từ chối

Form từ chối chỉ gửi <code>client_id</code>, <code>state</code> và CSRF token nếu áp dụng, **không có tham số scope**. Với cách xử lý consent thông thường của Spring Authorization Server, điều đó biểu diễn việc người dùng không chấp thuận quyền mới và có thể dẫn đến <code>access_denied</code> trong authorization response. Hãy kiểm thử hành vi của version/customization thực tế, nhất là khi request đã có consent cũ.

Không tự tạo một POST handler mới có quyền phát token, không gửi sẵn <code>scope=orders.write</code> qua hidden input để “cho form luôn hợp lệ” và không coi việc nhấn nút đồng ý là bằng chứng để bỏ qua xác minh state.

### 7.3. Lưu ý về CSRF và Thymeleaf

Trong cấu hình Thymeleaf/Spring Security, <code>th:action</code> có thể tích hợp với <code>RequestDataValueProcessor</code> để tự thêm hidden CSRF input. Ví dụ template hiển thị token khi attribute <code>_csrf</code> hiện diện để minh họa; khi tích hợp thực tế, hãy kiểm tra HTML đã render và **chỉ dùng một cơ chế thêm token phù hợp**, tránh tạo các input trùng lặp không cần thiết.

Một số endpoint Authorization Server được loại trừ khỏi CSRF matcher do configurer giao thức quản lý. Điều đó **không làm consent state trở nên tùy chọn**. Không tắt CSRF trên toàn bộ web/login chỉ vì form consent bị 403; cần xác định đúng filter chain, matcher và endpoint xử lý.

### 7.4. Hiển thị scope OIDC

Các scope <code>openid</code>, <code>profile</code> và <code>email</code> có ngữ nghĩa khác scope quyền API. Không mặc định phải tạo checkbox <code>openid</code> ở mọi consent page: có thể nó được framework xem là điều kiện giao thức và không nằm trong danh sách cần xét duyệt. Chỉ dựa trên tập scope mà Authorization Server chuyển tới cùng chính sách cho các scope tương ứng; đừng tự thêm hidden <code>openid</code> vào POST nếu AS không đưa nó vào ngữ cảnh consent.

## 8. Đảm bảo quyền được cấp không vượt quá yêu cầu

Đối với consent UI, một bất biến cốt lõi là:

~~~text
Scopes được cấp thực tế
  ⊆ Scopes trong authorization request còn chờ
  ∩ Scopes client được phép đăng ký
  ∩ Chính sách quyền của người dùng và hệ thống
  ∩ Quyết định consent hợp lệ
~~~

Đây là biểu diễn logic; OIDC hoặc extension có thể có quy tắc bổ sung. Điều quan trọng là **HTML form không phải nguồn tin cậy**. Nếu một người sửa checkbox bằng DevTools rồi gửi <code>scope=admin.full_access</code>, Authorization Server phải từ chối hoặc không cấp quyền đó dựa trên request/registered client/policy, dù controller GET từng hiển thị dữ liệu hợp lệ.

### 8.1. Chống XSS, giả mạo danh tính client và phishing

- Render client name, principal, scope và mô tả bằng <code>th:text</code>/<code>th:value</code> có escaping; không dùng <code>th:utext</code> cho nội dung không tin cậy.
- Không lấy logo từ một URL tùy ý do client gửi ngay trong authorization request; dùng metadata đã xét duyệt.
- Thiết lập <code>Content-Security-Policy</code>, hạn chế <code>frame-ancestors</code>, <code>Referrer-Policy: no-referrer</code>, HTTPS/HSTS và <code>Cache-Control: no-store</code>.
- Tránh log toàn bộ URL consent vì nó chứa state và thông tin request; không ghi token/secret/cookie vào log.
- Cần có đường dẫn hỗ trợ và thu hồi quyền cho ứng dụng đã kết nối, nhưng đừng đặt một nút “Thu hồi tất cả token” giả mà chỉ xóa record consent.

### 8.2. Ràng buộc state, session và principal

Controller GET chỉ đọc dữ liệu để hiển thị. Authorization Endpoint khi nhận POST cần xác minh consent state tồn tại, liên kết với authorization request phù hợp, client ID đúng, user session đúng và scope hợp lệ. Không chấp thuận POST khi người dùng đã logout, state đã dùng/không còn tồn tại hoặc client ID bị thay đổi.

Đối với hệ thống đa tenant, cặp <code>registeredClientId</code> và <code>principalName</code> phải phân biệt thực thể chính xác; không dùng chung bản ghi consent cho hai người cùng username ở hai tenant.

### 8.3. Không ghi consent từ GET

<code>OAuth2AuthorizationConsent</code> thể hiện các authority đã được người dùng cấp cho registered client. Lúc render trang consent, controller chỉ nên gọi <code>OAuth2AuthorizationConsentService.findById()</code> để tham khảo trạng thái cũ; <code>save()</code> thuộc luồng xử lý kết quả consent hợp lệ phía Authorization Server. Việc ghi <code>SCOPE_orders.write</code> vào record chỉ vì request có giá trị đó sẽ là lỗi **tự động cấp quyền trước khi người dùng đồng ý**.

## 9. Quyền cũ, scope mới và thay đổi trạng thái

### 9.1. Người dùng đã có consent <code>orders.read</code>

Ví dụ consent cũ:

~~~text
registeredClientId = orders-web-record-001
principalName      = user-42
authorities        = {SCOPE_orders.read}
~~~

Khi client xin thêm <code>orders.write</code>, giao diện có thể phân nhóm:

~~~text
Orders Portal (orders-web) muốn truy cập:

Quyền mới:
  [ ] Chỉnh sửa đơn hàng
      Có thể cập nhật các đơn hàng bạn được phép sửa.

Đã cấp trước đây:
  ✓ Xem đơn hàng

[Chấp thuận quyền đã chọn]    [Từ chối]
~~~

Những quyền cũ có thể được tái sử dụng theo chính sách và không nên tự xem là quyền đang được yêu cầu lần đầu. Tuy nhiên, đừng suy ra việc bỏ checkbox quyền cũ trên trang có tác dụng **thu hồi quyền đó**; một chức năng “Quản lý ứng dụng đã kết nối” cần luồng revoke riêng được xác thực.

### 9.2. Không có scope mới nhưng AS vẫn hiện trang

Nếu trang nhận được state hợp lệ mà danh sách quyền mới rỗng, hãy kiểm tra quy tắc OIDC, yêu cầu tái consent, quyền đã cấp trước đây và hành vi của framework theo version. Không tự động hoàn tất authorization trong controller để “bỏ qua màn hình”; hãy xử lý theo chính sách hoặc điều chỉnh logic hiển thị cho rõ ràng.

### 9.3. Thay đổi hoặc thu hồi consent

Nếu người dùng xóa consent đã lưu, request mới có thể cần hỏi lại. Nhưng xóa consent không mặc nhiên làm JWT access token tự hết hạn; nếu mục tiêu là ngắt kết nối tức thời, phải có chiến lược thu hồi refresh token, authorization đang hoạt động và/hoặc access token theo định dạng và khả năng Resource Server.

## 10. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| GET consent trả 404 | Có <code>consentPage()</code> nhưng chưa có MVC controller hoặc template. | Kiểm tra <code>@GetMapping</code>, view name, Thymeleaf resolver. |
| Trang consent bị chuyển tới login liên tục | Session không được giữ, cookie bị chặn, chain web sai hoặc context path/proxy sai. | Kiểm tra chain, session, forwarded headers, SameSite/Secure. |
| POST trả 404 | Form action không đúng Authorization Endpoint. | Đối chiếu <code>AuthorizationServerSettings.getAuthorizationEndpoint()</code>. |
| POST trả 403 | CSRF token không phù hợp với filter chain đang áp dụng. | Kiểm tra CSRF matcher và hidden input; giữ bảo vệ form login. |
| Consent lặp vô tận | Form mất hoặc dùng nhầm consent state, session thay đổi hoặc POST không có scope hợp lệ. | So sánh state redirect consent với state được gửi lại. |
| Form hiện scope không được xin | Hiển thị toàn bộ <code>client.getScopes()</code>. | Đọc danh sách scope của consent redirect và authorization request. |
| Form không cấp scope đã chọn | Dùng input name khác <code>scope</code> hoặc action sai. | Kiểm tra body POST và phản hồi endpoint. |
| Người dùng từ chối nhưng vẫn nhận code | Có hidden scope không mong muốn hoặc xử lý tùy chỉnh bỏ qua consent. | Kiểm tra payload form và test từ chối. |
| Consent bị hỏi mỗi lần | In-memory state mất sau restart, principal/client record ID không ổn định, nhiều node khác kho. | Kiểm tra <code>OAuth2AuthorizationConsentService</code>. |
| Client name hiển thị lạ | Dùng query client_name hoặc dữ liệu không được xét duyệt. | Luôn lấy từ <code>RegisteredClient</code> đáng tin. |
| Trang bị XSS | Render tên client/scope không escape. | Dùng <code>th:text</code>/<code>th:value</code>, CSP và test ký tự đặc biệt. |

Khi debug, cần xem cả ba đoạn: **AS redirect tới GET consent**, **MVC render form**, **POST quay lại AS**. Một HTTP 200 ở trang HTML không chứng minh Authorization Endpoint đã xác minh state và cấp token hợp lệ.

### 10.1. PAR/JAR và các authorization request nâng cao

Với Pushed Authorization Requests (PAR), JWT-Secured Authorization Requests (JAR) hoặc những profile có request object, không nên tự xây lại danh sách scope chỉ từ query nguyên thủy của browser. Hãy dùng cơ chế của Authorization Server và kiểm thử dữ liệu redirect consent trên phiên bản đang triển khai. Một số phiên bản đã có báo cáo về việc danh sách scope không xuất hiện đúng trong custom consent khi kết hợp PAR; đó là lý do cần integration test thay vì tự chèn quyền ẩn vào form.

## 11. Kiểm thử giao diện và quyết định consent

### 11.1. Unit/MVC test cho màn hình

Giả định Spring MVC test đã cấu hình principal test, client <code>orders-web</code> và các repository:

~~~java
@Test
void consentPageShowsTrustedClientAndRequestedScopes() throws Exception {
    mockMvc.perform(get("/oauth2/consent")
            .param("client_id", "orders-web")
            .param("scope", "orders.read")
            .param("state", "example-consent-state")
            .with(user("alice")))
        .andExpect(status().isOk())
        .andExpect(view().name("oauth2-consent"))
        .andExpect(model().attribute("clientId", "orders-web"))
        .andExpect(model().attributeExists("newScopes"));
}

@Test
void consentPageRejectsScopeNotRegisteredForClient() throws Exception {
    mockMvc.perform(get("/oauth2/consent")
            .param("client_id", "orders-web")
            .param("scope", "admin.full_access")
            .param("state", "example-consent-state")
            .with(user("alice")))
        .andExpect(status().isBadRequest());
}
~~~

Đây là test **render UI**, không xác minh consent state thực sự có trong authorization store. Muốn chứng minh an toàn cần test POST thực qua Authorization Endpoint, giữ đúng session và consent state do server phát hành. Với HTML template, thêm test client name chứa <code>&lt;script&gt;</code> để kiểm tra escaping và chắc chắn không xuất hiện checkbox scope ngoài request.

### 11.2. Ma trận integration test

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| User chưa login mở consent page | Phải đăng nhập hoặc bị từ chối; không lộ consent của user khác. |
| Client ID không tồn tại | Không render client giả; phản hồi an toàn. |
| Client chỉ xin một scope trong nhiều scope đã đăng ký | UI chỉ hiển thị quyền thuộc ngữ cảnh consent. |
| Client metadata có ký tự HTML | Dữ liệu được escape; không thực thi script. |
| Alice có <code>orders.read</code> trong consent cũ | Phân biệt quyền đã cấp và quyền mới. |
| Chấp thuận một scope hợp lệ | AS lưu/đọc consent đúng và chỉ cấp quyền hợp lệ. |
| Tự sửa POST gửi scope ngoài request | AS từ chối hoặc không cấp quyền vượt chính sách. |
| Từ chối không chọn scope | Không phát authorization code như khi chấp thuận. |
| Thiếu/sai consent state | Không tiếp tục authorization. |
| State của user khác hoặc form đã dùng lại | Không chấp nhận authorization không còn phù hợp. |
| Thiếu/sai servlet CSRF token khi filter yêu cầu | Bị CSRF filter từ chối. |
| Thay đổi client ID giữa GET/POST | Không cấp quyền cho client khác. |
| Session hết hạn giữa lúc xem và gửi form | Bắt đăng nhập/khởi tạo flow lại theo chính sách. |
| Đổi context path / reverse proxy | Action và redirect được tạo đúng URL công khai. |
| Nhiều instance | Session, authorization state và consent storage nhất quán. |
| PAR/JAR nếu có | Scope và state được đưa tới UI đúng trên version đang dùng. |

### 11.3. Quy trình end-to-end có thể lặp lại

1. Đăng ký client test với <code>requireAuthorizationConsent(true)</code>, redirect URI và scope hợp lệ; tạo test user.
2. Gửi <code>GET /oauth2/authorize</code> gồm <code>response_type=code</code>, <code>client_id</code>, scope, client state và PKCE hợp lệ.
3. Đăng nhập qua chain web, giữ session/cookie.
4. Kiểm tra Authorization Server redirect tới <code>/oauth2/consent</code> với <code>client_id</code>, <code>scope</code> và **consent state do AS sinh**.
5. Render UI và xác minh client name, scope description, danh sách checkbox và quyền đã cấp trước đây nếu có.
6. POST về <code>/oauth2/authorize</code> với đúng consent state, client ID và các scope được chọn, kèm CSRF token nếu cần.
7. Xác minh redirect về **redirect URI đã đăng ký** với authorization code và OAuth client state ban đầu. Đổi code bằng PKCE, kiểm tra access token không có scope thừa.
8. Lặp lại các trường hợp từ chối, sửa scope, sửa client ID, gửi lại state, session thay đổi và CSRF token sai.

Không dùng một unit test của controller hoặc test dùng mock Authentication để tuyên bố flow OAuth2/OIDC đã được bảo vệ hoàn chỉnh. Chính Authorization Endpoint, consent provider và token issuance mới là nơi cần integration test.

## 12. Vận hành consent UI trong production

Trước khi phát hành màn hình cho người dùng thật, cần bảo đảm:

- **Metadata và scope catalog:** tên ứng dụng, logo, domain, mô tả quyền được quản lý và xét duyệt; không để client tự truyền HTML tùy ý.
- **Đồng nhất giao diện:** nhãn rõ ràng, có hỗ trợ keyboard/screen reader, tương phản đủ, responsive và luôn nhìn thấy nút Từ chối.
- **HTTP security:** HTTPS/HSTS, cookie phù hợp, CSP hạn chế script và frame, Referrer-Policy, Cache-Control no-store, XSS/CSRF protection.
- **Session và authorization state:** đủ nhất quán trên nhiều instance; dùng kho lưu trạng thái bền vững khi cần và kiểm soát timeout.
- **Consent persistence:** nếu cần ghi nhớ quyết định sau restart, dùng implementation JDBC hoặc kho bền vững thích hợp; in-memory chỉ phù hợp demo/test.
- **Audit:** ghi principal ID, registered client record ID, scopes đã chọn, thời gian và kết quả; không ghi credential, token hoặc state nguyên văn.
- **Phân biệt revoke:** xóa consent không tự hủy access token/refresh token hiện tại; chức năng ngắt kết nối cần chính sách token riêng.
- **Giám sát:** tỷ lệ chấp thuận/từ chối, lỗi state, CSRF, mismatch scope, lỗi callback và vấn đề proxy.

Màn hình đẹp có thể khiến người dùng tin một ứng dụng nguy hiểm hơn mức đáng tin. Vì vậy, **quy trình xác minh client và mô tả quyền trung thực** là phần bảo mật trực tiếp của consent UI.

## 13. Bài tập thực hành

Một Authorization Server phục vụ ba client:

- <code>customer-portal</code> dùng OIDC và scope <code>openid profile orders.read</code>.
- <code>partner-integration</code> được đăng ký <code>orders.read orders.write</code>, nhưng thường chỉ xin quyền đọc.
- <code>billing-dashboard</code> xin <code>invoices.read</code> và <code>invoices.export</code>.

Hãy thực hiện:

1. Thiết kế mockup trang consent hiển thị tên/ID client, tài khoản đang dùng, các scope mới, quyền đã cấp trước đó và hai lựa chọn.
2. Tạo scope catalog tiếng Việt, phân biệt <code>openid</code>/<code>profile</code> với quyền nghiệp vụ.
3. Cấu hình <code>consentPage("/oauth2/consent")</code>, AS chain và web chain riêng, giải thích vì sao matcher của AS nên dùng <code>getEndpointsMatcher()</code>.
4. Viết MVC controller lấy dữ liệu tin cậy từ <code>RegisteredClientRepository</code> và consent cũ từ <code>OAuth2AuthorizationConsentService</code>.
5. Viết Thymeleaf form POST về Authorization Endpoint với đúng <code>client_id</code>, <code>state</code>, <code>scope</code> và CSRF khi áp dụng; form từ chối không được tự chèn scope.
6. Chứng minh bằng test rằng client đăng ký nhiều scope không làm UI tự hiển thị tất cả scope ở mọi request.
7. Dùng DevTools sửa form để thử <code>admin.full_access</code>, thay state bằng state của user khác, đổi client ID và double-submit.
8. Kiểm thử Alice đã có <code>orders.read</code> nhưng cần thêm <code>orders.write</code>; chỉ phần quyền hợp lệ được xét duyệt và lưu.
9. Xác định cách vận hành consent store, client metadata, multi-tenancy và token revocation khi có nút “Ngắt kết nối”.

Một thiết kế đạt yêu cầu phải chứng minh được **UI hiển thị đúng client và scope cần duyệt**, **người dùng có lựa chọn thực sự** và **Authorization Server xác minh độc lập trước khi cấp code/token**.

## 14. Tài liệu tham khảo

- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): cấu hình Authorization Endpoint và custom consent page.
- [OAuth2AuthorizationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationEndpointConfigurer.html): redirect parameters và yêu cầu POST khi dùng <code>consentPage()</code>.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>RegisteredClient</code>, <code>OAuth2AuthorizationConsent</code>, <code>OAuth2AuthorizationConsentService</code>.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): cấu hình client, security filter chain và authorization flow.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): chính sách route consent.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF filter và token cho form.
- [Thymeleaf + Spring Tutorial](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html): form, biểu thức <code>th:text</code>, <code>th:value</code> và escaping.
- [RFC 6749, §4.1 — Authorization Code Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.1): authorization request, state và scope.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): scope và sự chấp thuận OIDC.

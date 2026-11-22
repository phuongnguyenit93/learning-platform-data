# 9.10. Repository tùy chỉnh: yêu cầu bảo toàn dữ liệu và thời hạn

## 1. Repository trong OAuth2/OIDC callback dùng để làm gì?

Trong Spring Security OAuth 2.0/OIDC Client, một lần **Authorization Code Login** thường gồm hai lượt HTTP riêng biệt tới ứng dụng:

1. Người dùng mở đường dẫn bắt đầu đăng nhập, ví dụ `/oauth2/authorization/corporate`. Spring Security tạo một `OAuth2AuthorizationRequest`, lưu thông tin cần thiết rồi chuyển browser sang Authorization Server.
2. Sau khi người dùng xác thực, provider đưa browser trở lại callback, ví dụ `/login/oauth2/code/corporate?code=...&state=...`. Spring Security phải **tìm lại đúng authorization request trước đó** để kiểm tra correlation và tiếp tục đổi code lấy token.

**Authorization request repository** lưu ngữ cảnh tạm thời của giao dịch nằm giữa hai lượt này. Repository có thể dựa trên session mặc định, một kho chia sẻ như Redis, hoặc một cơ chế khác đáp ứng hợp đồng của Spring Security.

Một repository tùy chỉnh chỉ đúng khi đồng thời bảo đảm hai nhóm yêu cầu:

- **Bảo toàn dữ liệu:** request đọc lại phải giữ đủ thông tin ban đầu để Spring Security xác thực `state`, gửi đúng **PKCE code verifier**, xử lý **OIDC nonce**, xác định đúng `ClientRegistration` và `redirect_uri`, cũng như phục hồi những attributes dùng nội bộ.
- **Bảo toàn vòng đời:** một request có hạn sử dụng rõ ràng, chỉ phục vụ giao dịch đã khởi tạo, không thể được dùng lại sau khi tiêu thụ, không trở thành dữ liệu tồn đọng vô thời hạn và không bị một luồng đăng nhập khác vô tình ghi đè.

Chỉ “lưu được state và trả lại object” là chưa đủ. Nếu custom repository làm mất verifier hoặc nonce, luồng có thể lỗi sau callback hoặc bỏ sót một ràng buộc bảo mật dù bước kiểm tra `state` dường như thành công.

### 1.1. Repository này khác nơi lưu token

| Đối tượng/thành phần | Thời điểm có ý nghĩa | Nội dung chính |
| --- | --- | --- |
| `ClientRegistrationRepository` | Trước và xuyên suốt luồng | Cấu hình client: `clientId`, provider, scopes, grant, endpoints |
| `OAuth2AuthorizationRequest` | Khi chuẩn bị redirect | Yêu cầu cấp quyền của **một giao dịch**, gồm `state`, redirect URI, additional parameters và attributes |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Giữa authorization redirect và callback (Servlet) | Lưu, lấy, xóa **request đang chờ** |
| `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Cùng vai trò trên WebFlux | API reactive lưu, lấy, xóa authorization request |
| `OAuth2AuthorizedClient` | Sau khi được cấp token | `ClientRegistration` cùng access token/refresh token khi có |
| `OAuth2AuthorizedClientService` / repository tương ứng | Sau khi cấp token | Lưu/tải **authorized client**, không thay thế authorization request repository |

Đặc biệt, repository tùy chỉnh ở bài này **không phải nơi lưu access token dài hạn** và không thay thế chức năng quản lý `OAuth2AuthorizedClient`.

## 2. Repository tham gia những bước nào của authorization flow?

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Browser
    participant App as Spring Security OAuth2 Client
    participant Repo as Custom Authorization Request Repository
    participant IdP as OIDC Provider

    User->>App: GET /oauth2/authorization/corporate
    App->>App: Dựng OAuth2AuthorizationRequest
    App->>Repo: save(request + attributes, expiry)
    Repo-->>App: Đã lưu
    App-->>User: 302 /authorize?state=...&code_challenge=...&nonce=...
    User->>IdP: Authorization Request
    IdP-->>User: 302 callback?code=...&state=...
    User->>App: Callback cùng session/correlation
    App->>Repo: load(request by state + session)
    Repo-->>App: Request gốc còn hiệu lực
    App->>Repo: remove/consume(request)
    Repo-->>App: Request đã tiêu thụ
    App->>App: Đối chiếu state, khôi phục verifier/nonce
    App->>IdP: POST /token với code + code_verifier
    IdP-->>App: Token response / ID Token
    App->>App: Xác minh OIDC nonce cùng các claim khác
    App-->>User: Hoàn tất đăng nhập / lỗi
~~~

Sơ đồ biểu diễn các trách nhiệm ở mức logic; thứ tự và phương thức cụ thể do filter, authentication provider và phiên bản Spring Security triển khai quyết định. Điểm then chốt là **callback chỉ có thể tiếp tục nếu repository truy xuất được đúng request gốc còn hiệu lực**.

Một tình huống cần xử lý rõ: người dùng đăng nhập xong nhưng callback đến **sau khi TTL của repository hết hạn**. Khi đó repository phải coi request là không còn hợp lệ, dù authorization code từ provider trông có vẻ đúng. Ứng dụng nên khởi tạo flow mới thay vì nới lỏng kiểm tra correlation để “cứu” callback cũ.

## 3. Interface của Spring Security: Servlet và WebFlux

### 3.1. Servlet/MVC — `AuthorizationRequestRepository`

Trong ngăn xếp Servlet:

~~~java
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

public interface AuthorizationRequestRepository<T extends OAuth2AuthorizationRequest> {
    T loadAuthorizationRequest(HttpServletRequest request);

    void saveAuthorizationRequest(
        T authorizationRequest,
        HttpServletRequest request,
        HttpServletResponse response);

    T removeAuthorizationRequest(
        HttpServletRequest request,
        HttpServletResponse response);
}
~~~

Đoạn interface được lược bỏ các chú thích/chi tiết không cần thiết để nhấn mạnh hợp đồng; đây là chữ ký trọng tâm của API Servlet hiện đại.

- **`saveAuthorizationRequest`:** lưu yêu cầu được tạo **trước khi redirect**. Khi tham số authorization request là `null`, hành vi repository phải tương thích hợp đồng xóa bỏ request của Spring Security.
- **`loadAuthorizationRequest`:** tìm lại request liên quan tới HTTP request hiện tại mà **chưa tiêu thụ**. Nếu không có hoặc không hợp lệ, trả `null`.
- **`removeAuthorizationRequest`:** lấy và loại bỏ request tương ứng để không cho cùng correlation tiếp tục được xử lý lại. Trả request vừa tiêu thụ hoặc `null` nếu không có/hết hạn.

Triển khai mặc định phổ biến là `HttpSessionOAuth2AuthorizationRequestRepository`. Đây là điểm xuất phát tốt cho ứng dụng một phiên đăng nhập thông thường; khi cần hỗ trợ nhiều authorization request song song hoặc thay đổi storage/TTL, mới cần custom repository.

### 3.2. WebFlux — `ServerAuthorizationRequestRepository`

Trong ngăn xếp reactive:

~~~java
import org.springframework.security.oauth2.client.web.server.ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

public interface ServerAuthorizationRequestRepository<T extends OAuth2AuthorizationRequest> {
    Mono<T> loadAuthorizationRequest(ServerWebExchange exchange);

    Mono<Void> saveAuthorizationRequest(
        T authorizationRequest, ServerWebExchange exchange);

    Mono<T> removeAuthorizationRequest(ServerWebExchange exchange);
}
~~~

WebFlux dùng `ServerWebExchange` và Reactor `Mono` thay cho Servlet `HttpServletRequest`/`HttpServletResponse`. Triển khai session thường gặp là `WebSessionOAuth2ServerAuthorizationRequestRepository`.

**Không lấy code Servlet dùng nguyên trong WebFlux.** Cũng không gọi `.block()` trong implementation reactive để dùng JDBC/Redis đồng bộ trên event loop. Nên sử dụng client I/O reactive và xây dựng publisher trả về đúng hợp đồng.

### 3.3. Nơi gắn repository vào cấu hình OAuth2 Login

Ví dụ Servlet:

~~~java
@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationRequestRepository<OAuth2AuthorizationRequest>
                    authorizationRequests) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestRepository(authorizationRequests)));

        return http.build();
    }
}
~~~

Với WebFlux, cấu hình tương ứng nằm trong `ServerHttpSecurity.oauth2Login(...)` và `authorizationRequestRepository(...)` ở phần authorization request resolver/repository của DSL phiên bản tương ứng.

Các đoạn Java trong bài lược bớt `import` thông thường. Khi tích hợp, cần dùng API của đúng phiên bản Spring Security và đúng web stack đang triển khai.

## 4. Phải bảo toàn chính xác những dữ liệu nào?

### 4.1. Không chỉ lưu `state`

`OAuth2AuthorizationRequest` chứa nhiều dữ liệu phục vụ **một lần ủy quyền**. Những trường/nhóm dữ liệu thường cần được bảo toàn:

| Dữ liệu | Lý do phải giữ | Lỗi nếu mất hoặc bị sửa |
| --- | --- | --- |
| `authorizationUri` | Định danh endpoint provider đã dùng khi tạo request | Có thể làm sai provider/flow |
| `authorizationGrantType` / `responseType` | Cho biết luồng authorization code | Không nhất quán với token exchange |
| `clientId` | Ràng buộc vào client ban đầu | Dùng nhầm client hoặc không thể đổi code |
| `redirectUri` | URI callback cụ thể đã được gửi | `invalid_grant` hoặc mismatch khi token exchange |
| `scopes` | Phạm vi đã xin | Mất ngữ cảnh của authorization request |
| `state` | Liên kết callback với request ban đầu | Callback thiếu cơ chế correlation |
| `additionalParameters` | Parameter bổ sung đã gửi provider | Mất `nonce`, PKCE challenge/method hoặc extension quan trọng |
| `attributes` | **Dữ liệu nội bộ** Spring Security/ứng dụng dùng sau redirect | Mất `code_verifier`, thông tin registration hoặc metadata correlation |
| Thời điểm tạo, `expiresAt` | Quản lý tuổi thọ của request | Chấp nhận request cũ hoặc lưu mãi không xóa |
| Ràng buộc session/tenant/browser | Chống dùng chéo giao dịch | Một browser/người dùng khác có thể khôi phục request |

**Đặc biệt quan trọng:** đừng giả định mọi dữ liệu cần giữ đều xuất hiện trong query string authorization URL.

- `additionalParameters` có thể chứa `code_challenge` hoặc tham số OIDC đưa **ra provider**.
- `attributes` là dữ liệu **nội bộ**, có thể chứa PKCE `code_verifier` hoặc metadata giúp xác định registration/flow.
- Giá trị `state` nằm trong cả request ban đầu lẫn callback, nhưng **phải đối chiếu với bản đã lưu**, không chỉ kiểm tra là có mặt.

Những key chính xác và kiểu đối tượng nằm trong `attributes` có thể phụ thuộc cách Spring Security/resolver tùy biến xây dựng request. Khi serial hóa, phải bảo toàn **giá trị và kiểu dữ liệu** cần thiết thay vì ép mọi thứ thành chuỗi.

### 4.2. Nguy hiểm của DTO quá tối giản

Ví dụ DTO sai về mặt thiết kế:

~~~java
record SavedLogin(String state, String clientId, String redirectUri) {}
~~~

DTO này không đủ để phục hồi request với PKCE verifier, OIDC nonce, scopes, các tham số bổ sung hoặc metadata nội bộ. Một số lần login không dùng PKCE có thể tình cờ chạy được, khiến lỗi chỉ bộc lộ khi provider bật PKCE hoặc khi chuyển sang OIDC.

Nếu muốn tạo DTO có schema riêng để lưu JSON/Redis, hãy định nghĩa và phục hồi **toàn bộ những trường cần thiết**, bao gồm các map với kiểu giá trị mà framework cần. Có thể lưu đầy đủ `OAuth2AuthorizationRequest` bằng serializer phù hợp, hoặc chủ động xây schema ánh xạ hai chiều và theo dõi khả năng tương thích khi nâng cấp Spring Security.

**Không lưu mỗi `getAuthorizationRequestUri()` rồi parse query để tái tạo request ở callback**. URL không mang mọi dữ liệu nội bộ; việc parse còn dễ phá vỡ encoding hoặc tạo ra request khác với đối tượng ban đầu.

### 4.3. Khác biệt giữa `state`, OIDC `nonce` và PKCE `code_verifier`

| Giá trị | Được tạo khi nào? | Bên nào nhận? | Đối chiếu ở đâu? |
| --- | --- | --- | --- |
| `state` | Khi bắt đầu authorization | Provider nhận trong authorization request và trả lại trên callback | **Client** so callback với request đã lưu |
| `nonce` | Khi tạo yêu cầu OIDC có nonce | Provider nhận, ID Token có claim nonce tương ứng | **OIDC Client** khi xác minh ID Token |
| `code_verifier` | Khi khởi tạo PKCE | Chỉ Token Endpoint nhận verifier sau callback | **Authorization Server** khi đối chiếu với challenge |
| `code_challenge` | Dẫn xuất từ verifier | Authorization Endpoint nhận | Authorization Server gắn với authorization code |

Ví dụ PKCE với `S256`:

~~~text
code_verifier  = chuỗi ngẫu nhiên đủ mạnh, 43–128 ký tự hợp lệ
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
~~~

**Không lưu mỗi code challenge thay cho verifier**: hai giá trị khác nhau, không thể khôi phục verifier từ hash challenge. Cũng không lấy verifier mới ở callback; provider đã gắn code với challenge từ authorization request trước đó.

Với OIDC, repository hoặc dữ liệu lưu kèm phải giúp client lấy lại **nonce kỳ vọng** của chính yêu cầu xác thực; cách Spring Security xử lý biểu diễn nonce có thể khác nhau theo phiên bản. Khi tự sửa `nonce`, phải bảo đảm bước xác minh ID Token sử dụng giá trị khớp và tiếp tục kiểm tra các claim khác như issuer, audience, thời hạn và chữ ký.

## 5. Bảo toàn thời hạn: TTL, expiry và replay

### 5.1. Vì sao authorization request cần TTL?

Authorization request là **giao dịch ngắn hạn**, tồn tại từ lúc redirect đến khi callback được xử lý. Nếu lưu vô thời hạn:

- Một `state` cũ có thể còn tồn tại lâu hơn thời gian giao dịch đáng lẽ có hiệu lực.
- Dữ liệu PKCE verifier, OIDC nonce và metadata nhạy cảm tồn tại quá lâu.
- Request bị bỏ dở tích tụ trong session/Redis.
- Khó phân biệt một callback được trả về quá muộn với flow đang có hiệu lực.

Một chính sách thực tế có thể dùng TTL ví dụ **10 phút**, điều chỉnh theo trải nghiệm đăng nhập, MFA, timeout của provider và hạ tầng. **10 phút chỉ là giá trị minh họa**, không phải con số cố định trong OAuth2/OIDC hay mặc định bắt buộc của Spring Security.

Khi lưu:

~~~text
createdAt = thời điểm tạo authorization request
expiresAt = createdAt + authorizationRequestTtl
~~~

Khi callback:

~~~text
if request không tồn tại:
    reject

if currentTime >= expiresAt:
    reject và xóa bản lưu đã hết hạn

if state/session/registration không khớp:
    reject

otherwise:
    consume request đúng một lần
    tiếp tục xử lý callback
~~~

Việc so thời điểm nên dùng đồng hồ hệ thống đáng tin cậy của môi trường. Khi ứng dụng phân tán, tất cả instance/Redis cần có đồng bộ thời gian thích hợp; không xây TTL bằng một timestamp từ client browser mà server không xác minh.

### 5.2. TTL của repository không phải thời hạn của token

| Thời hạn | Đối tượng | Ai kiểm soát? |
| --- | --- | --- |
| Authorization request TTL | Request đang chờ callback | Ứng dụng OAuth2 Client/repository |
| Authorization code lifetime | Authorization code do IdP phát | Authorization Server |
| Browser session timeout | Phiên/browser của ứng dụng | Ứng dụng và session store |
| Access token expiration | Access token đã cấp | Authorization Server và Resource Server xác minh |
| Refresh token expiration | Refresh token nếu được cấp | Chính sách Authorization Server/client |

Dù authorization request repository vẫn còn entry, một authorization code đã hết hạn vẫn không đổi thành token được. Ngược lại, provider vừa tạo code hợp lệ nhưng request gốc đã hết TTL tại client thì **client vẫn phải từ chối callback**.

Chọn TTL sao cho phù hợp với flow: quá ngắn làm người dùng nhập MFA lâu bị lỗi; quá dài làm tăng dữ liệu lưu và thời gian một request cũ còn sống. Không được dùng TTL của access token thay cho TTL của authorization request.

### 5.3. “Consume đúng một lần” là yêu cầu khác với TTL

TTL ngăn dùng request quá muộn. **One-time consume** ngăn dùng lại request trước khi nó hết hạn.

Một repository có thể đạt TTL nhưng vẫn sai nếu hai callback đồng thời đều đọc cùng request và đều được chấp nhận. Cần xác định hoạt động “lấy request để xử lý lần cuối và xóa” có tính nguyên tử trong môi trường lưu trữ đang dùng hay không.

~~~text
Bắt đầu: state=S1 còn hạn

Callback A: consume(S1) -> trả request, xóa S1
Callback B: consume(S1) -> không tìm thấy, từ chối

Kết quả mong muốn: chỉ một callback nhận được request để xử lý.
~~~

Nếu storage chỉ có hai thao tác rời `GET` và `DELETE`, trong môi trường nhiều worker có thể xảy ra race. Cần atomic consume như `GETDEL` (khi phù hợp), transaction, compare-and-delete, Lua script hoặc primitive tương đương của hệ thống lưu trữ. Với Spring Security, lưu ý API có thể tách `loadAuthorizationRequest` và `removeAuthorizationRequest`; implementation phải bảo đảm **bước tiêu thụ** là điểm quyết định cuối cùng trước khi chấp nhận callback.

### 5.4. Tại sao cần dọn dữ liệu bỏ dở?

Nhiều người bấm “Đăng nhập” rồi đóng tab, làm callback không bao giờ quay lại. Nếu chỉ xóa khi callback tới, các request đó sẽ tồn tại mãi. Tùy storage:

- Với Redis, dùng **key TTL** cùng ràng buộc `expiresAt` trong payload nếu cần.
- Với session map, xóa entry hết hạn trong lúc đọc/ghi hoặc dùng cleanup thích hợp; TTL của session có thể là giới hạn bổ sung.
- Với database, cần điều kiện `expires_at` khi đọc và một cơ chế cleanup riêng cho các hàng quá hạn.

Không xem việc background cleanup chạy chậm là lý do để chấp nhận expired request. **Validation expiry phải xảy ra ngay trên đường xử lý callback**, còn cleanup có thể diễn ra bất đồng bộ.

## 6. Ví dụ Servlet: custom repository với TTL và một pending request mỗi session

Ví dụ sau cố ý giữ mô hình **một authorization request đang chờ trên mỗi HTTP session** để thấy rõ hợp đồng. Nó minh họa cách lưu **toàn bộ §OAuth2AuthorizationRequest§**, từ chối request quá hạn và xóa sau khi callback được tiêu thụ.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.oauth2.core.endpoint.OAuth2ParameterNames;
import org.springframework.util.StringUtils;

public final class ExpiringSessionAuthorizationRequestRepository
        implements AuthorizationRequestRepository<OAuth2AuthorizationRequest> {

    private static final String SESSION_KEY =
            ExpiringSessionAuthorizationRequestRepository.class.getName() + ".PENDING";

    private final Duration ttl;
    private final Clock clock;

    public ExpiringSessionAuthorizationRequestRepository(
            Duration ttl, Clock clock) {

        if (ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("TTL must be positive");
        }
        this.ttl = ttl;
        this.clock = clock;
    }

    @Override
    public void saveAuthorizationRequest(
            OAuth2AuthorizationRequest authorizationRequest,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (authorizationRequest == null) {
            removeAuthorizationRequest(request, response);
            return;
        }

        if (!StringUtils.hasText(authorizationRequest.getState())) {
            throw new IllegalArgumentException("Authorization request must have state");
        }

        HttpSession session = request.getSession(true);
        StoredRequest stored = new StoredRequest(
                authorizationRequest,
                clock.instant().plus(ttl));

        synchronized (session) {
            session.setAttribute(SESSION_KEY, stored);
        }
    }

    @Override
    public OAuth2AuthorizationRequest loadAuthorizationRequest(
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);
        if (session == null) {
            return null;
        }

        synchronized (session) {
            return readIfValid(session, request);
        }
    }

    @Override
    public OAuth2AuthorizationRequest removeAuthorizationRequest(
            HttpServletRequest request,
            HttpServletResponse response) {

        HttpSession session = request.getSession(false);
        if (session == null) {
            return null;
        }

        synchronized (session) {
            OAuth2AuthorizationRequest original = readIfValid(session, request);

            // Chỉ consume khi state khớp và request còn hiệu lực.
            if (original != null) {
                session.removeAttribute(SESSION_KEY);
            }
            return original;
        }
    }

    private OAuth2AuthorizationRequest readIfValid(
            HttpSession session, HttpServletRequest request) {

        Object attribute = session.getAttribute(SESSION_KEY);
        if (!(attribute instanceof StoredRequest stored)) {
            return null;
        }

        if (!clock.instant().isBefore(stored.expiresAt)) {
            session.removeAttribute(SESSION_KEY);
            return null;
        }

        String incomingState =
                request.getParameter(OAuth2ParameterNames.STATE);

        if (!StringUtils.hasText(incomingState)
                || !stored.request.getState().equals(incomingState)) {
            return null;
        }

        return stored.request;
    }

    private static final class StoredRequest {
        final OAuth2AuthorizationRequest request;
        final Instant expiresAt;

        StoredRequest(
                OAuth2AuthorizationRequest request, Instant expiresAt) {
            this.request = request;
            this.expiresAt = expiresAt;
        }
    }
}
~~~

**Ý nghĩa và giới hạn của ví dụ:**

- Lưu nguyên `OAuth2AuthorizationRequest` nên các trường `additionalParameters` và `attributes` có thể được giữ nguyên trong session.
- `clock` được inject để kiểm soát thời gian một cách rõ ràng; dùng `Clock.systemUTC()` ở production và đồng hồ cố định trong thử nghiệm nếu muốn.
- `request.getSession(false)` ở callback tránh tạo **session mới rỗng** chỉ để “xử lý” callback không có ngữ cảnh.
- Khi state thiếu hoặc sai, `load`/`remove` trả `null`. Không biến state từ callback thành state mới để hợp thức hóa request.
- `remove` xóa request khi tìm đúng request hợp lệ; callback tới lại sẽ không lấy được request cũ.
- `StoredRequest` trong code chỉ là dữ liệu nội bộ của **một JVM/session thông thường**. Nếu session được passivate hoặc lưu phân tán, cần bảo đảm dữ liệu **serializable** với serializer và phiên bản class phù hợp; có thể thay nó bằng DTO serializable và cơ chế bảo toàn toàn bộ request.
- Khóa session chỉ giữ **một pending request**. Đăng nhập ở tab B có thể ghi đè flow tab A. Khi cần hỗ trợ nhiều tab, hãy dùng một map state → record có TTL và quản lý concurrency.
- `synchronized(session)` chỉ minh họa việc phối hợp truy cập cùng một đối tượng session trong một process. **Không bảo đảm atomicity trên nhiều node hoặc khi session wrapper khác nhau**. Đừng dùng ví dụ này nguyên xi như repository phân tán.
- Logic `saveAuthorizationRequest(null, ...)` cần được đặt trong ngữ cảnh hợp đồng của framework. Những implementation có yêu cầu xóa cả các entry khi không có `state` phải tự xác định scope xóa an toàn; ví dụ này chỉ xóa entry của state callback khớp.
- Mục tiêu là minh họa **bảo toàn request và TTL**. Các yêu cầu production như chống ghi đè, hardening session, serial hóa/rotation, nhiều tab và atomic consumption đa instance được trình bày ở phần tiếp theo.

> Trong bài toán thật, lựa chọn repository tùy chỉnh phải dựa trên mô hình deployment và yêu cầu bảo mật. Chỉ thêm TTL bằng cách copy lại một đoạn code session không đủ để giải quyết vấn đề multi-instance.

### 6.1. Gắn repository vào Spring Security Servlet

~~~java
@Configuration
class LoginSecurity {

    @Bean
    AuthorizationRequestRepository<OAuth2AuthorizationRequest>
    authorizationRequestRepository() {
        return new ExpiringSessionAuthorizationRequestRepository(
                Duration.ofMinutes(10),
                Clock.systemUTC());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationRequestRepository<OAuth2AuthorizationRequest> repository)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestRepository(repository)));

        return http.build();
    }
}
~~~

Cấu hình này không thay việc kiểm tra ID Token hay làm token request bằng tay; các thành phần OAuth2 Login chuẩn tiếp tục hoạt động với request đã được repository phục hồi.

Ví dụ `application.yml` cho OIDC client:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile, email
        provider:
          company:
            issuer-uri: https://idp.example.com/realms/staff
~~~

Khi triển khai cần đăng ký redirect URI chính xác tại provider, dùng HTTPS và bảo đảm cookie session của browser quay về được callback.

## 7. Nhiều tab, nhiều flow: key theo state nhưng vẫn phải ràng buộc session

Một session có thể phát sinh nhiều authorization request song song:

~~~text
Tab A:
    state = A1, verifier = VA, nonce = NA
Tab B:
    state = B2, verifier = VB, nonce = NB

Callback tab B -> phải lấy đúng B2, VB, NB
Callback tab A -> phải lấy đúng A1, VA, NA
~~~

Nếu sử dụng một session attribute duy nhất, request B có thể ghi đè request A. Repository tùy chỉnh có thể dùng:

~~~text
session.pendingRequests = {
    state_A1: {
        request: <OAuth2AuthorizationRequest A>,
        createdAt: ...,
        expiresAt: ...
    },
    state_B2: {
        request: <OAuth2AuthorizationRequest B>,
        createdAt: ...,
        expiresAt: ...
    }
}
~~~

Trách nhiệm đi kèm:

1. **Key theo state:** chỉ dùng state khó đoán, đúng định dạng, không nhận key tùy tiện từ browser rồi ghi đè cấu hình client.
2. **Ràng buộc session:** cùng state nhưng khác browser/session không thể tự động nhận request gốc. State là correlation value; việc biết state không nên đủ để lấy mọi metadata qua API công khai.
3. **TTL từng entry:** A có thể hết hạn trong khi B còn hiệu lực.
4. **Consume đúng entry:** callback B chỉ xóa B, không xóa A.
5. **Giới hạn dung lượng:** đặt tối đa số pending requests mỗi session, tránh abuse khiến session hoặc Redis phình vô hạn.
6. **Concurrency:** cấu trúc map, thao tác read/remove và serialization phải an toàn khi request đến đồng thời.
7. **Dọn expired:** xóa các entry đã quá hạn và các entry đã xử lý, có chiến lược cho flow bị bỏ dở.
8. **Không trộn tenant/provider:** request A cho tenant X không được phép tiêu thụ bằng callback/registration của tenant Y.

Ví dụ sơ đồ dữ liệu nhiều tab:

~~~mermaid
flowchart TD
    A[Session của browser] --> M["Pending map (state -> record)"]
    M --> SA["State A1 / Client corporate / TTL A"]
    M --> SB["State B2 / Client partner / TTL B"]
    SA --> RA["OAuth2AuthorizationRequest A<br/>attributes: verifier VA, OIDC context"]
    SB --> RB["OAuth2AuthorizationRequest B<br/>attributes: verifier VB, OIDC context"]
    CA["Callback state=A1"] --> SA
    CB["Callback state=B2"] --> SB
~~~

**Vấn đề khó:** nếu session được lưu trong Redis bởi Spring Session, mutating một `Map` đã lấy bằng `session.getAttribute(...)` không nhất thiết bảo đảm mutation được ghi lại hoặc đồng bộ nguyên tử giữa nhiều process. Phải hiểu chính sách dirty-tracking/serialization của session store, và nếu cần thì thiết kế storage theo **mỗi state một record** với thao tác atomic riêng, thay vì phụ thuộc lock Java trong một instance.

## 8. Thiết kế repository phân tán bằng Redis hoặc database

Khi ứng dụng chạy sau load balancer với nhiều instance, authorization callback có thể tới một node khác node đã tạo request. Một repository gắn với memory local sẽ không đủ, trừ khi có cơ chế session routing/phân phối phù hợp.

### 8.1. Mẫu dữ liệu khi lưu ở Redis

Một cách biểu diễn logic:

~~~text
key:
  oauth2:authrequest:<hash-of-random-state>

value:
  version: 1
  originalAuthorizationRequest: <serialized full request>
  sessionBinding: <server-side session context or protected digest>
  registrationId: "corporate"
  createdAt: 2026-11-16T02:00:00Z
  expiresAt: 2026-11-16T02:10:00Z

redisTTL:
  600 seconds
~~~

Đây là **mô hình dữ liệu**, không phải tên field/serializer có sẵn trong Spring Security. Cần chọn cơ chế serialize/deserialze phù hợp để bảo toàn các kiểu dữ liệu cần thiết của `OAuth2AuthorizationRequest`. `hash-of-random-state` nhằm tránh lưu state raw trong key nếu chính sách yêu cầu; do state đã ngẫu nhiên, điều quan trọng hơn là bảo vệ ngữ cảnh và dữ liệu bên trong record.

**Khi lưu:**

~~~text
save(request, browserContext):
    require strong, nonempty state
    require supported registration/client/provider
    serialized = serializeFullRequest(request)
    record = { serialized, boundContext, createdAt, expiresAt, schemaVersion }
    insertIfAbsent(key(state), record, ttl)
    reject / handle collision safely
~~~

**Khi tải:**

~~~text
load(callback, browserContext):
    state = parseState(callback)
    record = read(key(state))
    if record missing or expired: return absent
    if not validSessionBinding(record, browserContext): return absent
    if not match(record.request.state, state): return absent
    return deserializeFullRequest(record)
~~~

**Khi tiêu thụ:**

~~~text
consume(callback, browserContext):
    atomically:
        find record by state
        verify not expired
        verify browser/session binding
        verify state + intended client/provider context
        delete that record only
        return original request
~~~

Phần **atomically** đặc biệt quan trọng. Với Redis có thể dùng transaction/Lua/primitive phù hợp để thực hiện compare-and-delete nguyên tử. Chỉ lấy `GETDEL` theo state mà **không kiểm tra session binding** có thể làm một request bị tiêu thụ bởi người biết state nhưng không có ngữ cảnh hợp lệ; có thể tạo lỗi DoS hoặc ảnh hưởng correlation. Nếu cần kiểm tra binding và điều kiện hết hạn, hãy đưa việc kiểm tra và xóa vào **cùng thao tác nguyên tử**.

Với database có thể dùng row locking/transaction hoặc câu lệnh kiểu `DELETE ... RETURNING ...` theo điều kiện đủ, tùy engine. Cần kiểm tra transaction isolation, index, unique constraint cho state key và quy trình cleanup record hết hạn.

### 8.2. Tránh phân biệt sai “load” và “consume”

Spring Security gọi repository qua những phương thức chuẩn, nhưng storage có thể cung cấp API nội bộ giàu hơn, ví dụ:

~~~java
interface AuthorizationRequestStore {
    Mono<Void> save(PendingAuthorizationRequest pending);
    Mono<PendingAuthorizationRequest> read(String state, BrowserBinding browser);
    Mono<PendingAuthorizationRequest> consume(
            String state, BrowserBinding browser);
}
~~~

Đây là **abstraction minh họa do ứng dụng tự định nghĩa**, không phải interface của Spring Security. Adapter thực thi `ServerAuthorizationRequestRepository` hoặc `AuthorizationRequestRepository` sẽ ánh xạ các lời gọi framework tới store này.

Mục tiêu là làm rõ trách nhiệm:

- `read` chỉ cho xem dữ liệu còn hiệu lực, không vô tình tiêu thụ.
- `consume` là **điểm kiểm tra và xóa nguyên tử**.
- Các callback đồng thời không được cùng nhận “consume thành công”.
- Không bao giờ khôi phục request bằng state từ callback nếu record gốc đã bị xóa.

Trong một số luồng framework, `load` được gọi trước `remove`. Không nên thay đổi ngữ nghĩa `load` thành “xóa luôn” nếu điều đó khiến `remove` không tìm được request và flow đăng nhập thất bại. Cần phù hợp vòng đời thực tế của filter/provider phiên bản đang chạy.

## 9. Vấn đề serialization: đừng làm mất attributes hoặc thay đổi kiểu

Đây là rủi ro lớn nhất khi chuyển từ session lưu object sang JSON/Redis/database.

Giả sử request có:

~~~text
OAuth2AuthorizationRequest:
    state: "s_M3..."
    clientId: "portal"
    redirectUri: "https://portal.example.com/login/oauth2/code/corporate"
    scopes: ["openid", "profile"]
    additionalParameters:
        code_challenge: "..."
        code_challenge_method: "S256"
        nonce: "..."
    attributes:
        registration_id: "corporate"
        code_verifier: "<random secret>"
        ... other Spring Security / application metadata
~~~

Các tên key bên trong maps phụ thuộc phiên bản/customization; đây chỉ là hình dung cấu trúc. Nếu serializer:

- Bỏ `attributes` hoặc `additionalParameters` vì “không cần hiển thị trên UI”;
- Chuyển `Set<String>` thành một `String` rồi phục hồi sai;
- Chuyển enum, grant type, response type hoặc object lồng nhau thành `Map` không đúng kiểu;
- Không hỗ trợ class/field xuất hiện sau khi nâng cấp Spring Security;
- Lưu toàn bộ request không mã hóa trong kho dữ liệu có người dùng ngoài phạm vi truy cập;
- Tạo lại một object mới với `state` đã bị thay thế;

thì callback có thể mất khả năng xác minh hoặc đổi code theo đúng request.

### 9.1. Những thuộc tính cần có trong schema lưu trữ

| Nhóm dữ liệu | Khuyến nghị thiết kế |
| --- | --- |
| Phiên bản schema | Thêm `version` để biết cách đọc dữ liệu trước/sau nâng cấp |
| Request đầy đủ | Giữ đủ trường cốt lõi, additional parameters và attributes |
| Kiểu dữ liệu | Ánh xạ type tường minh, không chỉ string hóa map tùy ý |
| Thời hạn | Có `createdAt` và `expiresAt`; lưu TTL ở store nếu hỗ trợ |
| Session/tenant binding | Liên kết request với đúng browser/tenant/provider |
| Integrity | Bảo vệ record không bị bên ngoài sửa mà vẫn được client tin cậy |
| Confidentiality | Bảo vệ verifier/metadata nhạy cảm ở nơi lưu |
| Giới hạn kích thước | Ngăn record chứa dữ liệu ngoài dự kiến quá lớn |
| Kịch bản nâng cấp | Chấp nhận hoặc từ chối an toàn record cũ; không đoán kiểu thiếu |

Nếu sử dụng Java serialization trực tiếp, cần cân nhắc rủi ro deserialization, tương thích phiên bản class và chính sách loại dữ liệu có thể được khôi phục. Chỉ deserialize dữ liệu từ nguồn tin cậy và theo serializer có allowlist/types được kiểm soát. Với JSON, whitelist trường/kiểu hợp lệ và tránh polymorphic deserialization không hạn chế.

### 9.2. Có thể chỉ lưu vài field nếu provider không dùng PKCE/nonce không?

Một triển khai quá tối giản có thể **tình cờ hoạt động** với một provider hoặc phiên bản, nhưng trở thành bẫy kỹ thuật khi:

- Provider yêu cầu PKCE.
- Bật OIDC và cần xác minh nonce/claims.
- Chuyển từ một client registration sang nhiều provider.
- Thêm custom authorization request parameter.
- Nâng phiên bản Spring Security khiến metadata nội bộ khác đi.

Vì vậy repository tùy chỉnh cần đặt mục tiêu **bảo toàn hợp đồng của `OAuth2AuthorizationRequest`**, thay vì “lưu đúng những thứ code hiện tại đọc thấy”.

## 10. WebFlux: cấu trúc reactive và vấn đề TTL

Trong WebFlux, việc lấy session và đọc store là bất đồng bộ. Một triển khai dựa trên shared Redis reactive nên trả publisher và tránh blocking:

~~~java
public final class RedisServerAuthorizationRequestRepository
        implements ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest> {

    private final ReactivePendingRequestStore store;

    public RedisServerAuthorizationRequestRepository(ReactivePendingRequestStore store) {
        this.store = store;
    }

    @Override
    public Mono<Void> saveAuthorizationRequest(
            OAuth2AuthorizationRequest authorizationRequest,
            ServerWebExchange exchange) {
        // Tạo record nguyên vẹn có TTL, ràng buộc vào session/browser.
        // authorizationRequest == null: xử lý xóa theo hợp đồng.
        return Mono.error(new UnsupportedOperationException(
                "Implement with a reactive store"));
    }

    @Override
    public Mono<OAuth2AuthorizationRequest> loadAuthorizationRequest(
            ServerWebExchange exchange) {
        // Đọc theo state + browser/session context,
        // từ chối record hết hạn và phục hồi đầy đủ các attributes.
        return Mono.error(new UnsupportedOperationException(
                "Implement with a reactive store"));
    }

    @Override
    public Mono<OAuth2AuthorizationRequest> removeAuthorizationRequest(
            ServerWebExchange exchange) {
        // Consume nguyên tử đúng request, không cho callback thứ hai tái sử dụng.
        return Mono.error(new UnsupportedOperationException(
                "Implement with a reactive store"));
    }
}
~~~

Đây là **khung interface để diễn giải kiến trúc**, không phải implementation có thể dùng ngay. `ReactivePendingRequestStore` là abstraction do ứng dụng tự định nghĩa, còn ba method cần được triển khai đúng với storage cụ thể. Không nên trả `Mono.just(null)` vì Reactor không cho phép null; sử dụng `Mono.empty()` để biểu diễn không có request.

Khi tự viết repository reactive, cần chú ý:

- Dùng `exchange.getSession()` và cơ chế ràng buộc browser đúng ngữ cảnh.
- Trả `Mono` từ driver Redis/database reactive, không gọi `block()` trong event loop.
- Đảm bảo `save` phát ra side effect khi được subscribe; không chỉ tạo một publisher rồi bỏ.
- `remove` phải tiêu thụ record tương ứng và không trả lại request đã quá hạn.
- Chọn TTL của record độc lập với thời hạn access token.
- Nếu storage lỗi, **fail closed**: không cho callback tiếp tục vì “không đọc được state”; log lỗi đã làm sạch và hướng người dùng khởi tạo lại login khi phù hợp.
- Không sử dụng `Mono.cache()` vô hạn cho một entry authorization request, vì có thể giữ lại request sau khi đã bị consume.

### 10.1. WebFlux sử dụng session repository khi nào?

Nếu ứng dụng chỉ cần một hoặc vài provider, chưa cần nhiều pending flows, session WebFlux có thể phù hợp. `WebSessionOAuth2ServerAuthorizationRequestRepository` giúp sử dụng cơ chế WebSession của Spring trong authorization flow.

Chỉ tạo custom repository khi có yêu cầu thực sự như TTL riêng, nhiều tab, session store đặc biệt hoặc sự phân phối giữa nhiều instance. Mỗi tùy biến tăng thêm trách nhiệm về concurrence, serialization, cookie, bảo vệ state và tích hợp filter.

## 11. Security boundaries: session, browser, tenant và provider

Repository dù có TTL vẫn có thể không an toàn nếu không phân biệt được **ai được phép tiêu thụ request nào**.

### 11.1. Session binding

Một authorization request xuất phát từ browser session A phải được ràng buộc với chính session A hoặc một ngữ cảnh tương đương có bảo vệ. Nếu key trong Redis chỉ là `state`, cần thêm kiểm tra rằng callback thuộc **browser/ngữ cảnh ban đầu**.

Không lưu state trong một biến toàn cục kiểu:

~~~java
static OAuth2AuthorizationRequest lastLoginRequest;
~~~

Khi hai người dùng đăng nhập, request sau có thể ghi đè request trước và lộ/nhầm ngữ cảnh. Cũng không dùng một khóa cố định chung cho mọi flow.

### 11.2. Tenant/provider binding

Hệ thống nhiều tenant có thể có nhiều OIDC Provider hoặc client registrations. Khi callback quay lại, cần biết nó thuộc **đúng client registration/provider** đã dùng ở bước authorization request.

Ví dụ:

~~~text
Tenant A:
  registrationId = "tenant-a"
  issuer = https://idp-a.example.com
  state = SA

Tenant B:
  registrationId = "tenant-b"
  issuer = https://idp-b.example.com
  state = SB
~~~

Kết quả callback của tenant A không được dùng để hoàn tất giao dịch tenant B. Ngoài state và session binding, ứng dụng có thể cần các cơ chế chống **authorization-server mix-up** phù hợp với nhiều issuer và tiêu chuẩn/implementation đang dùng.

Một repository tùy chỉnh không nên tra cứu `ClientRegistration` theo một tham số không đáng tin từ callback rồi bỏ qua metadata provider trong authorization request gốc. Cần giữ ràng buộc issuer, registration và các kiểm tra token khác của Spring Security/OIDC.

### 11.3. Open redirect và dữ liệu return URL

Một ứng dụng có thể lưu thêm `returnTo=/orders/123` trong metadata nội bộ. Hãy giới hạn return URL theo domain/path cho phép và không đọc trực tiếp một URL redirect tùy ý từ query của callback.

Dùng `state` như một phương tiện mang return URL chưa được kiểm soát có thể tạo lỗi open redirect hoặc lộ thông tin. Nếu phải lưu thông tin nghiệp vụ, nên ràng buộc nó vào record server-side tương ứng và kiểm tra trước khi redirect sau đăng nhập.

### 11.4. Bảo vệ kho lưu trữ

Authorization request có thể chứa dữ liệu đủ nhạy cảm để cần chính sách bảo vệ, nhất là PKCE verifier và metadata tenant. Với Redis/database:

- Chỉ cấp quyền đọc/ghi cho service liên quan.
- Dùng kết nối TLS khi cần qua mạng.
- Hạn chế ghi nội dung record vào log/monitoring.
- Cân nhắc mã hóa dữ liệu lưu trữ và quản lý khóa theo chính sách hệ thống.
- Không cho API công khai liệt kê pending authorization requests.
- Dọn bản ghi đã hết hạn; thiết lập hạn mức dung lượng và rate limiting hợp lý.

Với cookie-based repository, cần bảo vệ tính toàn vẹn; nếu chứa verifier hoặc metadata nhạy cảm, cân nhắc **mã hóa được xác thực (AEAD)**, cookie `Secure`/`HttpOnly`/`SameSite` phù hợp và cơ chế chống replay. Cookie session do browser giữ **không mặc nhiên bảo vệ nội dung record** chỉ vì nó có `HttpOnly`.

## 12. Thời gian, failure và xử lý retry

### 12.1. Những mốc thời gian cần phân biệt

~~~text
T0  Browser bắt đầu đăng nhập
T1  Repository lưu request, expiresAt = T1 + TTL
T2  Provider xác thực/MFA/consent
T3  Provider trả callback, có code/state
T4  Client đọc request, kiểm tra expiry, consume
T5  Backend đổi code tại Token Endpoint
T6  OIDC client kiểm tra ID Token, xây Authentication
~~~

Nếu callback đến lúc `T3 > expiresAt` thì từ chối, không dựa vào việc authorization code vẫn còn hạn. Nếu request đã được consume ở T4 và token exchange tại T5 thất bại, callback cũ **không được tái sử dụng**; người dùng khởi tạo flow mới.

### 12.2. Lỗi storage tại thời điểm callback

Nếu Redis/session store tạm thời không truy cập được, repository không thể chứng minh callback thuộc request đã lưu. Một lỗi vận hành của store **không cho phép bỏ qua state/expiry**. Ứng dụng có thể trả lỗi đăng nhập tạm thời và hướng người dùng thử lại từ đầu sau khi hạ tầng phục hồi.

Chọn timeout và circuit breaker phù hợp để tránh treo tất cả luồng login khi storage chậm. Tuy nhiên, circuit breaker không được làm cho repository tự cấp request mới từ callback khi không tìm được record gốc.

### 12.3. Khi người dùng bấm Back hoặc refresh callback

Authorization code là credential ngắn hạn, thường dùng **một lần**. Nếu người dùng refresh URL callback:

- Request có thể đã bị consume, nên repository không tìm thấy.
- Authorization code có thể đã được provider đánh dấu đã dùng.
- Kết quả cần là thất bại được xử lý an toàn hoặc chuyển người dùng về trạng thái đăng nhập hiện tại theo chính sách ứng dụng.

Không cố “sửa” bằng cách giữ lại request sau lần xác thực thành công để callback refresh được chấp nhận lại.

### 12.4. Khi người dùng mất session giữa chừng

Ví dụ session timeout 5 phút nhưng MFA có thể mất 8 phút. Repository entry còn trong Redis 10 phút cũng **không đủ** nếu callback không chứng minh được browser session gốc.

Chính sách timeout của browser session, authorization request TTL và login flow phải được thiết kế đồng bộ. Nếu cần hỗ trợ MFA dài, có thể tăng thời gian có giới hạn hoặc áp dụng một cơ chế correlation thay thế có bảo vệ; không cho phép callback thiếu session “dựa vào state” một cách tùy tiện.

## 13. Khi nào dùng implementation mặc định, khi nào cần custom?

| Nhu cầu | Lựa chọn khởi đầu | Khi nào custom có giá trị |
| --- | --- | --- |
| Web app đăng nhập với một vài provider, dùng session | `HttpSessionOAuth2AuthorizationRequestRepository` hoặc bản WebFlux tương ứng | Cần TTL/cleanup hoặc lưu nhiều pending flows |
| Ứng dụng có nhiều instance | Session store chia sẻ hỗ trợ framework | Cần atomic per-state consume hoặc storage độc lập với session |
| Hỗ trợ nhiều tab login trong cùng browser | Xem cách repository mặc định xử lý flow đồng thời | Cần map state → record và TTL riêng từng flow |
| Multi-tenant với nhiều IdP | Repository có thể giữ đầy đủ request/provider context | Cần ràng buộc tenant/issuer và phân quyền truy xuất record |
| Không muốn lưu dữ liệu trên server | Cân nhắc chi phí và rủi ro trước khi dùng cookie | Cần mã hóa/xác thực, chống replay, TTL và xử lý key rotation |
| API chỉ nhận bearer token | Resource Server | Không có authorization redirect/callback nên không cần repository này |
| Backend chỉ dùng `client_credentials` | OAuth2 Client / authorized client manager | Không có authorization code callback nên repository này không cần thiết |

Việc thêm custom repository nên dựa trên **yêu cầu thật**: session mặc định đã có cơ chế lưu request phù hợp với nhiều ứng dụng OAuth2 Login, và mỗi layer tùy chỉnh làm tăng trách nhiệm kiểm soát correlation.

## 14. Những lỗi thiết kế phổ biến

### 14.1. Chỉ serialize `state`/`clientId`

**Biểu hiện:** Browser đến callback với state đúng nhưng Token Endpoint trả `invalid_grant` khi dùng PKCE, hoặc OIDC nonce validation lỗi.

**Nguyên nhân:** Serializer không lưu full request, làm mất verifier, nonce hoặc attributes nội bộ.

**Cách xử lý:** Bảo toàn đầy đủ request hoặc schema được kiểm soát, map hai chiều đúng loại dữ liệu, có cơ chế version migration.

### 14.2. TTL được dùng để dọn nhưng không kiểm tra khi đọc

**Biểu hiện:** Job xóa dữ liệu chạy mỗi 30 phút, trong khi TTL logic chỉ 10 phút; callback ở phút 20 vẫn được xử lý.

**Nguyên nhân:** Code dựa hoàn toàn vào cleanup job thay vì kiểm tra `expiresAt` trên đường callback.

**Cách xử lý:** Kiểm tra expiry khi load/consume, cleanup chỉ giúp tiết kiệm tài nguyên.

### 14.3. `remove` chỉ đọc, không xóa

**Biểu hiện:** Callback cũ có thể được xử lý lại hoặc hai luồng đồng thời cùng lấy được request.

**Nguyên nhân:** Custom repository không triển khai one-time consume.

**Cách xử lý:** Lấy và xóa đúng record, dùng primitive nguyên tử khi nhiều process có thể truy cập cùng state.

### 14.4. Dùng Redis `GETDEL` nhưng không kiểm tra browser binding

**Biểu hiện:** Người biết state có thể khiến entry của browser khác bị tiêu thụ dù không có session tương ứng.

**Nguyên nhân:** Xóa record theo key trước khi xác minh điều kiện ràng buộc.

**Cách xử lý:** So sánh state, browser/session binding, tenant/registration và TTL **trong cùng thao tác nguyên tử** trước khi trả request đã consume.

### 14.5. Dùng một key cố định trong session

**Biểu hiện:** Login ở hai tab làm tab đầu thất bại ngẫu nhiên.

**Nguyên nhân:** Flow B ghi đè flow A.

**Cách xử lý:** Hỗ trợ nhiều pending entries theo state, hoặc chấp nhận có chủ đích mô hình một pending flow và xử lý lỗi phù hợp.

### 14.6. Lưu chỉ trong memory của một instance

**Biểu hiện:** Ứng dụng chạy một node thì đăng nhập được, triển khai nhiều pod thì callback lúc thành công lúc thất bại.

**Nguyên nhân:** Callback không đến node đã lưu request, còn repository không dùng shared storage.

**Cách xử lý:** Shared session store, storage riêng phân tán hoặc kiến trúc routing phù hợp; đảm bảo atomicity và lifecycle.

### 14.7. Kéo dài TTL để “chữa” mọi lỗi

**Biểu hiện:** Đặt TTL vài giờ nhưng vẫn có state mismatch hoặc callback failure.

**Nguyên nhân:** Lỗi thực là mất cookie/session, ghi đè request, wrong redirect URI hoặc PKCE verifier không được lưu.

**Cách xử lý:** Phân tích từng điểm thất bại, chỉnh thời hạn theo nhu cầu thực và giữ kiểm tra correlation.

### 14.8. Dùng dữ liệu từ callback để tái tạo request

**Biểu hiện:** Khi load không tìm thấy, code tự tạo `OAuth2AuthorizationRequest` với state và code từ URL để tiếp tục.

**Nguyên nhân:** Callback được “tin” mà không chứng minh có giao dịch đã khởi tạo.

**Cách xử lý:** **Từ chối callback không có request gốc**, yêu cầu bắt đầu authorization mới.

## 15. Quan sát hệ thống và thử nghiệm hành vi repository

Trong môi trường sản xuất, cần quan sát chính xác **vì sao callback không tìm lại được request** mà không lộ dữ liệu bí mật.

Các event vận hành có thể ghi:

~~~text
auth_request_saved
auth_request_loaded
auth_request_expired
auth_request_not_found
auth_request_state_mismatch
auth_request_consumed
auth_request_storage_failure
callback_token_exchange_failed
callback_oidc_validation_failed
~~~

Gắn correlation ID nội bộ để nối log các bước, nhưng **không ghi raw state, nonce, code verifier, authorization code, token, session cookie hoặc client secret**. Khi cần log `registrationId`, tenant hoặc host, áp dụng giới hạn dữ liệu theo chính sách.

### 15.1. Các hành vi nên được kiểm chứng ở bước kiểm thử ứng dụng

| Tình huống | Kỳ vọng |
| --- | --- |
| Save rồi load cùng state và session trong TTL | Nhận lại request đầy đủ, bao gồm attributes/additionalParameters |
| Callback khác state | Không tìm được request tương ứng |
| Callback ở session khác dù biết state | Không đọc/consume được request của session ban đầu |
| Sau TTL | Load/consume trả không có request; dữ liệu quá hạn được dọn |
| Callback hợp lệ lần đầu | Consume thành công, request bị xóa |
| Callback phát lại lần hai | Không tiêu thụ được request nữa |
| Hai callback đồng thời với cùng state | Tối đa một lần consume thành công |
| Hai tab với state khác nhau | Mỗi tab dùng đúng verifier/nonce; không lẫn nhau nếu thiết kế hỗ trợ |
| PKCE flow | Verifier được giữ nguyên và có mặt trong Token Request |
| OIDC flow có nonce | Nonce đã gửi được liên kết với ID Token để xác minh |
| Serialization round-trip | Request phục hồi đủ và đúng kiểu attributes |
| Restart/rolling deployment | Với shared store, request còn hạn được phục hồi phù hợp phiên bản serializer |
| Request cũ với schema không hỗ trợ | Từ chối an toàn thay vì suy diễn giá trị |
| Session logout/expire | Pending requests được xử lý theo chính sách, không còn đường callback vượt qua binding |
| Storage không truy cập được | Callback thất bại an toàn; không bypass state validation |

Đây là những **tình huống kiểm chứng hành vi thiết kế** để người học hiểu hợp đồng repository; việc triển khai kiểm thử thực tế phụ thuộc storage/framework trong dự án.

### 15.2. Ví dụ dùng đồng hồ có thể điều khiển

Để mô phỏng TTL mà không phải chờ thật, repository nên nhận `Clock` thay vì gọi thời gian hệ thống trực tiếp ở mọi nơi:

~~~java
Clock initialClock = Clock.fixed(
    Instant.parse("2026-11-16T02:00:00Z"), ZoneOffset.UTC);

var repository = new ExpiringSessionAuthorizationRequestRepository(
    Duration.ofMinutes(10),
    initialClock);
~~~

Khi thử nghiệm expiry, có thể tạo repository hoặc clock abstraction điều khiển được để mô phỏng thời điểm sau TTL. Lưu ý nếu clock được truyền là một `Clock.fixed(...)` bất biến, thời gian sẽ không tự tăng; muốn kiểm tra thay đổi thời gian trong cùng instance, cần clock có thể điều chỉnh hoặc cách inject phù hợp.

Không dùng cách `Thread.sleep(600000)` để kiểm thử thời hạn authorization request: vừa chậm, vừa khó tái lập, trong khi TTL là logic có thể kiểm tra bằng đồng hồ giả.

## 16. Câu hỏi và bài tập tình huống

### Câu 1. Callback có `state` và `code` hợp lệ về định dạng, nhưng repository không tìm thấy bản ghi. Có được cho tiếp tục token exchange không?

**Không.** Client phải chứng minh callback thuộc authorization request đã tạo và còn hiệu lực. Nếu không tìm thấy bản gốc, phải từ chối callback và cho phép khởi tạo login mới.

### Câu 2. Vì sao lưu mỗi `code_challenge` trong Redis không đủ cho PKCE?

Vì Token Endpoint cần **`code_verifier` gốc** để xác minh. Challenge thường là hash dẫn xuất từ verifier nên không thể dùng challenge thay cho verifier.

### Câu 3. TTL Redis đã xóa key sau 10 phút. Có cần `expiresAt` trong payload nữa không?

Tùy thiết kế, nhưng ghi rõ `expiresAt` có thể giúp validation ở tầng ứng dụng, quan sát và tương thích khi dữ liệu đi qua nhiều storage. **Ít nhất phải bảo đảm không trả lại entry quá hạn**, dù cleanup/expiration nền chưa kịp chạy.

### Câu 4. Vì sao `GET` rồi `DEL` riêng rẽ có thể không đủ khi hệ thống có nhiều pod?

Hai callback có thể cùng đọc trước khi một pod xóa record. Muốn bảo đảm one-time consume cần thao tác **nguyên tử** hoặc cơ chế concurrency tương đương.

### Câu 5. Nếu callback state đúng nhưng khác browser session thì sao?

Theo thiết kế session-bound, đó là callback không thuộc đúng ngữ cảnh, phải bị từ chối. State không nên là credential duy nhất đủ để truy xuất và tiêu thụ mọi request trong storage.

### Câu 6. Tại sao custom serializer cần lưu `attributes` dù chúng không nằm trong Authorization URL?

Vì Spring Security hoặc ứng dụng có thể giữ **PKCE verifier và metadata nội bộ** trong attributes, phục vụ bước xử lý callback/token exchange. Bỏ attributes có thể làm mất dữ liệu không thể khôi phục.

### Câu 7. Có thể lưu pending request vô thời hạn vì authorization code của provider đã tự hết hạn không?

Không. Authorization request và code có các vòng đời khác nhau. Cần TTL cho request, one-time consume và cleanup dữ liệu bỏ dở.

### Câu 8. Một ứng dụng WebFlux có thể sử dụng nguyên implementation Servlet dựa trên `HttpServletRequest` không?

Không. WebFlux cần `ServerAuthorizationRequestRepository` dùng `ServerWebExchange` và `Mono`; nếu dùng storage bên ngoài, cần I/O reactive và tránh chặn event loop.

### Câu 9. Hai tab đăng nhập với cùng session nhưng khác state bị lỗi xen kẽ. Cần kiểm tra gì?

Kiểm tra repository có lưu **nhiều pending request** hay chỉ một session attribute; nếu cần hỗ trợ nhiều tab, thiết kế map theo state, TTL từng entry và consume đúng entry.

### Câu 10. Tại sao lỗi OIDC nonce có thể bắt nguồn từ repository dù state đã khớp?

Vì nonce là ràng buộc khác với state. Nếu request hoặc metadata nonce cần thiết bị mất/trộn khi serialize hoặc load, ID Token không thể được đối chiếu đúng với yêu cầu xác thực ban đầu.

## 17. Tài liệu tham khảo chính thức

- [Spring Security — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — Advanced OAuth 2.0 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security API — AuthorizationRequestRepository](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/AuthorizationRequestRepository.html)
- [Spring Security API — HttpSessionOAuth2AuthorizationRequestRepository](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/HttpSessionOAuth2AuthorizationRequestRepository.html)
- [Spring Security API — ServerAuthorizationRequestRepository](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/server/ServerAuthorizationRequestRepository.html)
- [Spring Security API — OAuth2AuthorizationRequest](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/endpoint/OAuth2AuthorizationRequest.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)

**Ghi nhớ:** Một custom authorization request repository cần trả về **đúng toàn bộ request gốc** (đặc biệt `state`, PKCE verifier, OIDC correlation và attributes), đúng **browser/session/tenant/provider**, trong đúng **thời hạn**, và chỉ cho phép **tiêu thụ một lần**. Những ràng buộc này phải vẫn đúng khi có nhiều tab, nhiều instance, thay đổi serializer và lỗi mạng. Nếu không bảo đảm được, hãy dùng repository chuẩn của Spring Security hoặc thiết kế storage có cơ chế tương đương trước khi đưa vào production.


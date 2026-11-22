# SecurityContext, principal và thông tin authorization trong mỗi request

> **Chương:** Kiến trúc xử lý  
> **Module:** SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER  
> **Phạm vi:** Kiến trúc xử lý request trong ứng dụng Spring Boot dùng Spring Security và Spring Authorization Server để xây dựng, bảo mật, kiểm thử, vận hành OAuth 2.0/OpenID Connect Authorization Server.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài học, bạn có thể:

1. Giải thích mối quan hệ giữa `SecurityContextHolder`, `SecurityContext`, `Authentication`, `principal` và `GrantedAuthority`.
2. Mô tả cách Spring Security khôi phục, xác thực, phân quyền và dọn dẹp thông tin bảo mật trong **từng HTTP request**.
3. Xác định `Authentication` tại các endpoint của Authorization Server, nhất là sự khác biệt giữa **người dùng** và **client**.
4. Phân biệt **quyền truy cập trong request** với **trạng thái ủy quyền OAuth 2.0 được lưu bền vững**.
5. Truy xuất principal một cách an toàn trong controller, service và JWT Resource Server.
6. Thiết kế và kiểm thử đúng với request dùng session, request dùng Bearer token và luồng chạy bất đồng bộ.

Điểm cốt lõi: **`SecurityContext` cho biết Spring Security đang xem ai là chủ thể xác thực tại thời điểm xử lý request**, còn **quyết định có cho phép thao tác cụ thể hay không** phụ thuộc vào chính sách và dữ liệu nghiệp vụ. Trong Authorization Server, thông tin cấp quyền được lưu qua `OAuth2AuthorizationService` là **một mô hình khác**.

## 2. Các đối tượng cần phân biệt

Trong **Spring Security Servlet stack**, một cấu trúc phổ biến là:

~~~mermaid
flowchart TB
    F["HTTP request"]
    P["FilterChainProxy / SecurityFilterChain"]
    H["SecurityContextHolder<br/>Truy cập context đang gắn với luồng xử lý"]
    C["SecurityContext"]
    A["Authentication"]
    R["principal<br/>Ai đang được xác thực?"]
    D["credentials<br/>Bằng chứng xác thực"]
    G["authorities<br/>Vai trò / quyền mức cao"]
    Z["AuthorizationManager / method security<br/>Quyết định có cho request đi tiếp?"]
    E["Controller / nghiệp vụ"]

    F --> P
    P --> H
    H --> C
    C --> A
    A --> R
    A --> D
    A --> G
    P --> Z
    Z --> E
~~~

| Khái niệm | Ý nghĩa | Không nên nhầm với |
| --- | --- | --- |
| `SecurityContextHolder` | Điểm truy cập `SecurityContext` của luồng xử lý hiện tại theo chiến lược cấu hình | Kho lưu đăng nhập bền vững |
| `SecurityContext` | Container chứa `Authentication` hiện tại | Phiên HTTP hoặc access token |
| `Authentication` | Đại diện thông tin xác thực và quyền của chủ thể tại thời điểm xử lý | Luôn luôn là người dùng cuối |
| `principal` | Đối tượng nhận diện chủ thể được xác thực | Luôn luôn là `UserDetails` hoặc UUID người dùng |
| `credentials` | Bằng chứng dùng khi xác thực, có thể được xóa sau xác thực | Nơi lưu mật khẩu/token để dùng lại |
| `authorities` | Tập `GrantedAuthority` như `ROLE_ADMIN`, `SCOPE_booking.read` | Quyền sở hữu từng bản ghi dữ liệu |
| `SecurityContextRepository` | Cơ chế khôi phục/lưu `SecurityContext` khi cần qua nhiều request | `OAuth2AuthorizationService` |
| `OAuth2Authorization` | Trạng thái một lần ủy quyền/cấp token của OAuth 2.0 | Context của thread xử lý HTTP |
| `OAuth2AuthorizationConsent` | Thông tin consent đã được chấp thuận, gắn client và chủ thể | Quyết định cho phép mọi API request tương lai |
| `AuthorizationDecision` / kết quả authorization | Kết quả đánh giá một quy tắc truy cập tại thời điểm được gọi | Access token hoặc authorization code |

### 2.1. `SecurityContextHolder` là nơi đọc context hiện tại

Trong ứng dụng Spring MVC thông thường, Spring Security sử dụng chiến lược gắn context với **thread** xử lý request (`MODE_THREADLOCAL` theo mặc định). Cách truy xuất phổ biến:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

Câu lệnh này **không tự truy vấn cơ sở dữ liệu người dùng**, không tự kiểm tra chữ ký JWT và không phát hành token. Nó chỉ lấy kết quả xác thực hiện có trong context mà các bộ lọc/cơ chế bảo mật đã thiết lập.

Đặc biệt:

- Trước khi có kết quả xác thực, `getAuthentication()` có thể là `null`.
- Khi anonymous authentication được bật, nó có thể trả một `AnonymousAuthenticationToken`; không được xem token này là bằng chứng người dùng đã đăng nhập thật.
- Sau khi kết thúc request, Spring Security cần **dọn context khỏi thread** để tránh lộ danh tính sang request tiếp theo khi thread trong pool được tái sử dụng.
- Cách truy xuất này dành cho **Servlet/MVC**. Ứng dụng WebFlux dùng ngữ cảnh phản ứng (`ReactiveSecurityContextHolder`), không mặc định áp dụng ThreadLocal.

### 2.2. `Authentication` chứa gì?

Interface `Authentication` thể hiện hai tình huống khác nhau:

1. **Trước khi xác thực:** dữ liệu đầu vào, ví dụ username/password chưa được xác minh, thường có `isAuthenticated() == false`.
2. **Sau khi xác thực:** kết quả được bộ xác thực tin cậy chấp nhận, kèm principal và authorities.

Các phương thức cần biết:

~~~java
Authentication authentication = SecurityContextHolder.getContext()
        .getAuthentication();

if (authentication != null) {
    Object principal = authentication.getPrincipal();
    String name = authentication.getName();
    Collection<? extends GrantedAuthority> authorities =
            authentication.getAuthorities();
    boolean authenticated = authentication.isAuthenticated();
}
~~~

**Không dùng riêng `isAuthenticated()` để chứng minh người dùng thật đã đăng nhập**: token anonymous cũng có thể trả `true`. Khi cần kiểm tra trong code, hãy dùng chính sách authorization của Spring hoặc kết hợp kiểm tra anonymous bằng `AuthenticationTrustResolver`.

`credentials` có thể chứa bằng chứng nhạy cảm trước xác thực; các hệ thống thường xóa thông tin này sau khi xác thực thành công. **Không in `authentication` hay `credentials` nguyên vẹn ra log**.

### 2.3. Principal có nhiều hình dạng

| Ngữ cảnh | Kiểu `Authentication` thường gặp | `getPrincipal()` thường là |
| --- | --- | --- |
| Form login trong Authorization Server | `UsernamePasswordAuthenticationToken` | `UserDetails`, hoặc principal tùy biến |
| OIDC login trong OAuth2 Client | `OAuth2AuthenticationToken` | `OidcUser` trong OIDC |
| OAuth2 Resource Server nhận JWT | `JwtAuthenticationToken` | `Jwt` |
| Resource Server nhận opaque token | `BearerTokenAuthentication` | `OAuth2AuthenticatedPrincipal` |
| Xác thực client tại token endpoint của AS | `OAuth2ClientAuthenticationToken` (thế hệ SAS 1.x) | Principal đại diện **client** theo cơ chế AS |
| Chưa đăng nhập, anonymous bật | `AnonymousAuthenticationToken` | Thường là chuỗi `"anonymousUser"` |

Kiểu thực tế phụ thuộc extension và phiên bản Spring. Đừng viết `(UserDetails) authentication.getPrincipal()` ở một đoạn code được gọi từ nhiều loại endpoint: tại JWT RS principal mặc định là `Jwt`, còn tại token endpoint nó có thể là client.

**`authentication.getName()`** là định danh logic của principal hiện tại: trong JWT Resource Server thường là `sub` theo cấu hình mặc định, trong Client Credentials có thể là client ID. Nó không nhất thiết là email, username hiển thị, khóa chính bảng user hoặc Resource Owner.

## 3. Request đi qua Spring Security như thế nào?

Trong Servlet stack, request đi qua `DelegatingFilterProxy`, `FilterChainProxy` và **một** `SecurityFilterChain` khớp request. Các filter kiểm tra authentication/authorization trước khi request tới controller.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser / Client
    participant F as Security Filter Chain
    participant R as SecurityContextRepository
    participant H as SecurityContextHolder
    participant M as AuthenticationManager / Provider
    participant A as AuthorizationManager
    participant C as Controller

    B->>F: HTTP request
    F->>R: Lấy context theo cấu hình
    R-->>F: SecurityContext có sẵn hoặc rỗng
    F->>H: Thiết lập context cho request
    opt Có thông tin cần xác thực trong request
        F->>M: Xác thực credential / Bearer token
        M-->>F: Authentication đã xác thực hoặc lỗi
        F->>H: Cập nhật Authentication
    end
    F->>A: Kiểm tra truy cập
    alt Được phép
        A-->>F: Chấp nhận
        F->>C: Gọi handler với principal hiện tại
        C-->>B: Response
    else Bị từ chối
        A-->>F: Từ chối
        F-->>B: 401 / 403 hoặc redirect phù hợp
    end
    opt Có thay đổi cần lưu qua các request
        F->>R: Lưu context theo cơ chế được cấu hình
    end
    F->>H: Dọn context khi kết thúc xử lý
~~~

Sơ đồ minh họa vòng đời **logic**, không cố định thứ tự vật lý của từng filter hay cam kết mọi request đều gọi lưu context. Chẳng hạn `SecurityContextHolderFilter` nạp context từ repository nhưng **không tự động lưu**. Khi một luồng xác thực tự quản lý context, mã xác thực cần lưu rõ ràng qua `SecurityContextRepository.saveContext(...)` nếu muốn tái sử dụng qua request sau.

Các bước nhận thức quan trọng:

1. **Chọn filter chain.** Nếu ứng dụng khai báo nhiều `SecurityFilterChain`, chain có matcher phù hợp với request và thứ tự ưu tiên được áp dụng. Không cộng gộp mọi chain vào nhau.
2. **Khởi tạo/khôi phục context.** Repository có thể lấy context từ HTTP session hoặc cơ chế phù hợp; với API stateless thường bắt đầu từ context rỗng.
3. **Xác thực.** Filter đọc username/password, session hay Bearer token tùy endpoint và cấu hình, rồi thiết lập `Authentication`.
4. **Phân quyền.** Spring Security đối chiếu chính sách như `authenticated()` hoặc `hasAuthority(...)`; nghiệp vụ có thể kiểm tra quyền trên tài nguyên.
5. **Kết thúc.** Context không được để rò sang thread tái sử dụng; tính bền qua request, nếu cần, thuộc về repository/session/token chứ không phải biến ThreadLocal.

### 3.1. Vì sao hai request liên tiếp có thể có context khác nhau?

Ví dụ:

- Request `GET /login` ban đầu chưa có user: context có thể rỗng/anonymous.
- Request `POST /login` xác thực thành công: context có `Authentication` người dùng; cơ chế login lưu session phù hợp.
- Request `GET /oauth2/authorize` sau redirect, cùng trình duyệt gửi cookie: user được khôi phục từ session vào context của **request mới**.
- Request `POST /oauth2/token` từ backend Client: request mới có cơ chế xác thực **client**; không nên dựa vào principal của login request trước đó.

Không có một `SecurityContext` toàn cục dùng chung cho mọi người dùng hoặc mọi request. Kể cả khi cùng session được khôi phục, lần xử lý sau vẫn có vòng đời context mới.

## 4. SecurityContext khác thông tin authorization như thế nào?

Trong hệ OAuth 2.0/OIDC, từ “authorization” có **ít nhất ba ý nghĩa**:

| Nhóm thông tin | Câu hỏi trả lời | Vị trí thường gặp | Vòng đời |
| --- | --- | --- | --- |
| **Authentication hiện tại** | Chủ thể của request này là ai, đã xác thực ra sao? | `SecurityContext` / `Authentication` | Gắn với request; có thể được khôi phục từ session hoặc token |
| **Quyết định authorization tại request** | Request hiện tại có được gọi endpoint, phương thức hoặc xem đối tượng này không? | `AuthorizationManager`, `@PreAuthorize`, kiểm tra nghiệp vụ | Đánh giá tại thời điểm request |
| **OAuth2 authorization đã cấp** | Client nào được cấp quyền gì qua grant nào, token/code còn hiệu lực không? | `OAuth2Authorization` trong `OAuth2AuthorizationService` | Có thể tồn tại sau request trong kho lưu phù hợp |
| **Consent đã ghi nhận** | Resource Owner đã chấp thuận những authority/scope nào cho client? | `OAuth2AuthorizationConsent` trong `OAuth2AuthorizationConsentService` | Có thể duy trì qua nhiều request/phiên |

Sơ đồ dữ liệu:

~~~mermaid
flowchart LR
    X["Request /oauth2/authorize<br/>Authentication của user"]
    Y["Spring Authorization Server"]
    C["RegisteredClientRepository<br/>Cấu hình client"]
    O["OAuth2AuthorizationService<br/>Grant, code, token, authorizedScopes"]
    N["OAuth2AuthorizationConsentService<br/>Quyết định chấp thuận"]
    T["Request /oauth2/token<br/>Authentication của client"]
    S["Resource Server<br/>Quyết định truy cập API"]

    X --> Y
    T --> Y
    C <--> Y
    O <--> Y
    N <--> Y
    Y -->|"Phát hành access token"| S
~~~

Ở nhánh **Spring Authorization Server 1.x**, `OAuth2Authorization` chứa các trường như `registeredClientId`, `principalName`, `authorizationGrantType`, `authorizedScopes`, token và attributes. Dữ liệu này được lưu qua `OAuth2AuthorizationService`. Nó **không chính là** `SecurityContextHolder.getContext()`.

Chẳng hạn, client đổi authorization code ở token endpoint sau khi trình duyệt đã rời trang đăng nhập. AS vẫn đối chiếu được thông tin grant và resource owner thông qua **bản ghi `OAuth2Authorization`**, mà không cần “mang nguyên ThreadLocal của request cũ” sang request đổi code.

`OAuth2AuthorizationConsent` thường ghi các quyền đã chấp thuận cho cặp client và resource owner. Đã có consent **không bảo đảm** mọi yêu cầu API sau này được chấp nhận: Resource Server còn phải xác minh token và áp dụng quy tắc nghiệp vụ.

## 5. Phân tích từng request của Authorization Code + PKCE

Giả sử có bốn thành phần:

- **Resource Owner:** người dùng Lan.
- **Client:** ứng dụng `booking-web`.
- **Authorization Server:** `https://auth.example.test`, ứng dụng Spring Boot/Spring Authorization Server.
- **Resource Server:** `https://api.example.test`, một Spring Boot API.

Tên miền `.example.test` và các thông tin dưới đây chỉ dùng minh họa.

### 5.1. Request A — `GET /oauth2/authorize`

Client chuyển hướng trình duyệt tới AS với `client_id`, `response_type=code`, `redirect_uri`, `scope`, `state` và `code_challenge`.

- **Ai gửi HTTP request?** Trình duyệt người dùng.
- **Ai cần được xác thực?** Resource Owner (Lan), theo yêu cầu luồng.
- **Context có gì?** Nếu Lan đã đăng nhập trước đó qua session, có thể khôi phục `Authentication` của Lan; nếu chưa, AS sẽ yêu cầu xác thực.
- **Thông tin authorization gì?** AS tra `RegisteredClientRepository`, kiểm tra tham số OAuth2, client và scopes, đồng thời xác định chính sách consent.
- **Kết quả?** Có thể redirect tới trang đăng nhập, trang consent hoặc trả authorization code.

**Bẫy:** có `client_id` trong query không có nghĩa HTTP request này đã được xác thực bằng client secret. Ở authorization endpoint, hệ thống phải xác minh đăng ký/redirect URI của client, nhưng đây không phải bước thay thế cơ chế xác thực client tại token endpoint.

### 5.2. Request B — `POST /login`

Lan gửi thông tin đăng nhập vào AS.

- Filter login sử dụng `AuthenticationManager` và `AuthenticationProvider` phù hợp.
- Sau xác thực thành công, `Authentication` của Lan được thiết lập trong context.
- Cơ chế login/session lưu context theo cấu hình để request redirect sau đó có thể nhận ra Lan.
- Không tự động cấp access token API chỉ vì form login thành công.

**Bẫy:** không dùng trực tiếp mật khẩu người dùng để đổi token theo cách không được cấp phép; Authorization Code + PKCE tách bước đăng nhập người dùng với bước client đổi code.

### 5.3. Request C — Quay lại `/oauth2/authorize` và consent

Trình duyệt gửi cookie session. AS khôi phục principal Lan, áp dụng chính sách cho client và scope, hiển thị consent nếu cần. Sau khi Lan chấp thuận, AS có thể lưu `OAuth2AuthorizationConsent` và tạo `OAuth2Authorization` chứa trạng thái authorization code/ủy quyền.

Quan hệ quan trọng:

~~~text
SecurityContext tại authorization request
    -> Authentication của Resource Owner (Lan)

OAuth2Authorization được lưu
    -> registeredClientId = booking-web
    -> principalName = định danh của Lan
    -> authorizedScopes = phạm vi thực sự được cấp
    -> authorization code / trạng thái grant
~~~

Request tiếp theo có thể xử lý code nhờ bản ghi grant này. Không cần đọc lại session browser của Lan bằng cùng một thread.

### 5.4. Request D — `POST /oauth2/token`

Backend của `booking-web` gọi token endpoint với `grant_type=authorization_code`, `code`, `redirect_uri` và `code_verifier`. Confidential client còn sử dụng phương thức xác thực client đã đăng ký.

- **Ngữ cảnh xác thực tại token endpoint** có thể đại diện **client** qua `OAuth2ClientAuthenticationToken` hoặc loại tương ứng theo API/phiên bản.
- AS kiểm tra thông tin client; xác minh code, PKCE, redirect URI và bản ghi authorization đã lưu.
- **Resource Owner của grant** được xác định từ dữ liệu `OAuth2Authorization`; không giả định `SecurityContextHolder.getContext().getAuthentication()` của request token đang là Lan.
- AS có thể cấp access token, refresh token theo chính sách và ID token nếu là luồng OIDC hợp lệ.

**Bẫy lớn:** đặt một filter/logging handler dùng chung rồi gọi `getPrincipal()`, sau đó ép về kiểu người dùng Lan, sẽ gây lỗi hoặc ghi nhầm client ID thành user ID ở token endpoint.

### 5.5. Request E — `GET /api/bookings`

Client gọi Resource Server bằng access token:

~~~http
GET /api/bookings HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Ở **Resource Server**, Bearer token được xác minh, sau đó Spring Security tạo `Authentication` phù hợp, thường là `JwtAuthenticationToken` khi dùng JWT. Principal mặc định là đối tượng `Jwt`; các scope hợp lệ thường được ánh xạ thành authority mang tiền tố `SCOPE_`.

API kiểm tra:

1. Token hợp lệ về chữ ký hoặc introspection, issuer, thời hạn và đối tượng nhận (`audience`).
2. Scope/authority phù hợp, ví dụ `SCOPE_booking.read`.
3. Quyền nghiệp vụ: Lan có được đọc những booking cụ thể không?

Không có chuyện Resource Server tự thừa hưởng session hoặc `SecurityContext` của Authorization Server qua mạng.

### 5.6. Request F — OIDC UserInfo (nếu bật)

OIDC UserInfo là **resource được bảo vệ bằng access token**. Request tới endpoint này dùng Bearer token và được xác thực/ủy quyền theo cơ chế phù hợp của AS. Trong request đó, Authentication có thể mang thông tin từ access token; không mặc định là `UsernamePasswordAuthenticationToken` của phiên login ban đầu.

### 5.7. Bảng tổng hợp “ai là principal?”

| Request | Bằng chứng vào | Principal cần suy luận cẩn thận | Dữ liệu authorization quyết định |
| --- | --- | --- | --- |
| `GET /oauth2/authorize` | Session người dùng nếu đã đăng nhập | **Resource Owner** hoặc anonymous/trống | Client registration, scope yêu cầu, consent |
| `POST /login` | Username/password hoặc cơ chế login khác | User sau xác thực | Chính sách login và phiên |
| Consent / authorize tiếp | Session người dùng | **Resource Owner** | Consent, `OAuth2Authorization` |
| `POST /oauth2/token` | Client authentication + code/verifier hoặc grant phù hợp | Thường là **Client** ở bước client authentication; không mặc định là user | Grant/token được lưu, thông tin client |
| `GET /api/... ` tại RS | Access token | Chủ thể từ access token, có thể là user hoặc client | Token claims, audience, scope, quyền nghiệp vụ |
| `GET /userinfo` | Access token | Chủ thể theo cơ chế Bearer | Token hợp lệ, OIDC claims/scope và chính sách |

**Không có một quy tắc “principal luôn là user” áp dụng cho tất cả endpoint.** Ý nghĩa `principal` phụ thuộc loại Authentication và mục đích request.

## 6. Ví dụ đọc principal trong Spring MVC

### 6.1. Nhận `Authentication` trực tiếp trong controller

Trong một controller được bảo vệ bởi Spring Security:

~~~java
@RestController
@RequestMapping("/api")
public class ProfileController {

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of(
            "principalName", authentication.getName(),
            "authenticationType",
                authentication.getClass().getSimpleName()
        );
    }
}
~~~

Mẫu này chỉ minh họa cách truy cập đối tượng xác thực do Spring MVC/Spring Security cung cấp. Endpoint cần được bảo vệ bằng `authenticated()` hoặc chính sách chặt chẽ hơn để đảm bảo `authentication` phù hợp trước khi sử dụng. Trong production, không nên trả chi tiết kỹ thuật về token, authorities hoặc credentials ra API chẩn đoán công khai.

### 6.2. Dùng `@AuthenticationPrincipal` với JWT Resource Server

Khi biết chắc endpoint nằm trên JWT Resource Server:

~~~java
@RestController
@RequestMapping("/api")
public class BookingController {

    private final BookingService bookingService;

    public BookingController(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    @GetMapping("/bookings")
    public List<BookingDto> myBookings(@AuthenticationPrincipal Jwt jwt) {
        String subject = jwt.getSubject();
        return bookingService.findVisibleBookingsForSubject(subject);
    }
}
~~~

Điều kiện để mẫu này phù hợp: request đã được Spring Security Resource Server xác thực bằng JWT, principal là `Jwt` và `sub` có ý nghĩa trong hệ thống của bạn. Không dùng trực tiếp một giá trị `sub` bất kỳ để tìm mọi bản ghi nếu chưa ánh xạ issuer/tenant/user nội bộ và kiểm tra quyền.

Với OIDC Client đăng nhập qua `oauth2Login()`, principal phía Client có thể là `OidcUser`:

~~~java
@GetMapping("/account")
public String account(@AuthenticationPrincipal OidcUser user) {
    return user.getSubject();
}
~~~

**Không hoán đổi** `OidcUser` và `Jwt` giữa hai kiểu endpoint: một bên xử lý OIDC login của **Client**, bên còn lại xử lý Bearer access token của **Resource Server**.

### 6.3. Kiểm tra authority và quyền trên dữ liệu

Tầng HTTP có thể dùng:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .sessionManagement(session ->
            session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/api/bookings/**")
                .hasAuthority("SCOPE_booking.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Ví dụ này giả định ứng dụng **Resource Server độc lập** đã có cấu hình `issuer-uri`, khóa xác minh, các quy tắc audience cần thiết và dependency tương ứng. `SessionCreationPolicy.STATELESS` đảm bảo cơ chế security trong chain này không dùng HTTP session để lấy context. `SecurityContext` vẫn tồn tại **trong thời gian xử lý request**.

Đặt thêm kiểm tra theo đối tượng ở service:

~~~java
@Service
public class BookingAuthorizer {

    private final BookingRepository bookingRepository;

    public BookingAuthorizer(BookingRepository bookingRepository) {
        this.bookingRepository = bookingRepository;
    }

    public boolean canRead(String bookingId, Authentication authentication) {
        if (authentication == null) {
            return false;
        }

        // Minh họa: resolvePrincipal phải xác thực ánh xạ
        // issuer + subject + tenant vào danh tính nội bộ.
        String internalUserId = resolvePrincipal(authentication);
        return bookingRepository.existsVisibleToUser(
            bookingId, internalUserId
        );
    }

    private String resolvePrincipal(Authentication authentication) {
        // Triển khai ánh xạ principal trong ứng dụng thực tế.
        throw new UnsupportedOperationException("Application-specific");
    }
}
~~~

Đoạn `resolvePrincipal` trên là **điểm tích hợp còn phải triển khai**, không phải mã có thể chạy nguyên trạng. Mục đích là cho thấy phạm vi `booking.read` chỉ là một điều kiện; ai được đọc booking nào phải dựa vào dữ liệu và chính sách nghiệp vụ. Với API hoàn chỉnh có thể áp dụng `@PreAuthorize` cùng `@EnableMethodSecurity` hoặc gọi trực tiếp authorizer trong service.

## 7. Session, stateless và tính bền của SecurityContext

### 7.1. Authorization endpoint thường cần phiên đăng nhập người dùng

Các request đăng nhập/consent tương tác với trình duyệt thường dựa vào **session** để nhận diện Resource Owner qua redirect. `SecurityContextRepository` có thể lưu/khôi phục Authentication qua `HttpSession` hoặc kho lưu phù hợp.

Ví dụ đơn giản:

~~~text
Request 1: POST /login
    authentication = Lan
    -> lưu context vào session theo cơ chế login

Request 2: GET /oauth2/authorize
    cookie JSESSIONID
    -> khôi phục authentication của Lan
    -> tiếp tục consent / cấp code

Request 3: POST /oauth2/token (backend Client)
    -> xác thực client và kiểm tra authorization code
    -> KHÔNG cần thừa kế ThreadLocal của Request 2
~~~

Khi tự viết authentication filter/controller, nếu muốn **lưu đăng nhập qua request sau** với `SecurityContextHolderFilter`, việc chỉ gọi `SecurityContextHolder.setContext(...)` thường **không đủ**. Cần dùng `SecurityContextRepository.saveContext(...)` theo cơ chế đang cấu hình. Các filter xác thực có sẵn của Spring Security đã xử lý vấn đề này theo flow của chúng.

### 7.2. Resource Server có thể stateless

JWT Resource Server thường không cần session đăng nhập ở AS. Mỗi request gửi Bearer token; RS kiểm tra token và tạo `Authentication` tương ứng cho request. Kết thúc request, context được dọn.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Resource Server
    participant V as JWT Validator
    participant B as Business Service

    C->>R: Request 1 + access token
    R->>V: Kiểm tra token
    V-->>R: Authentication của Request 1
    R->>B: Kiểm tra scope + quyền dữ liệu
    B-->>R: Kết quả
    R-->>C: Response
    Note over R: Dọn SecurityContext của Request 1

    C->>R: Request 2 + access token
    R->>V: Kiểm tra lại token theo cơ chế cấu hình
    V-->>R: Authentication của Request 2
    R-->>C: Response
~~~

Token có thể vẫn hiệu lực giữa nhiều request, nhưng `SecurityContext` không phải một biến toàn cục được chia sẻ. Với JWT tự xác minh, RS thường không gọi AS ở mỗi request; cơ chế revoke ngay lập tức cần chiến lược bổ sung nếu có yêu cầu.

### 7.3. `OAuth2AuthorizationService` không thay thế session

Một số nhầm lẫn cần tách rõ:

- **HTTP session**: có thể ghi nhận đăng nhập của Resource Owner giữa các request đến AS.
- **`OAuth2AuthorizationService`**: lưu trạng thái của authorization grant và token để cấp, truy vấn hoặc thu hồi theo cơ chế AS.
- **`OAuth2AuthorizationConsentService`**: lưu quyết định consent khi hệ thống yêu cầu.
- **JWT access token**: có thể được RS tự xác minh; token không phải session trong AS.
- **`SecurityContextHolder`**: điểm truy cập Authentication trong request hiện tại; không thay thế bất kỳ kho lưu nào kể trên.

Trong sản phẩm chạy nhiều instance, cần lựa chọn kho lưu bền vững/phân tán cho authorization, consent và phiên đăng nhập (nếu có), cùng chính sách khóa ký/rotation phù hợp. `InMemoryOAuth2AuthorizationService` hữu ích cho phát triển hoặc thử nghiệm; không tự động mang dữ liệu sang một instance khác hay sau khi restart.

## 8. Các lưu ý về thread, async và tính an toàn

### 8.1. ThreadLocal không tự theo tác vụ bất đồng bộ

Trong Servlet stack, chiến lược mặc định của `SecurityContextHolder` gắn context với thread. Khi tự đưa công việc sang `ExecutorService`, `@Async` hoặc thread khác, context của request **không tự động có mặt** như mong đợi.

Đối với công việc cần danh tính người gọi, có thể:

- Truyền **thông tin cần thiết đã được kiểm soát** dưới dạng tham số, ví dụ internal user ID và tenant đã xác thực.
- Dùng cơ chế hỗ trợ truyền security context như `DelegatingSecurityContextRunnable` hoặc `DelegatingSecurityContextExecutor` khi cần truyền `Authentication`.
- Thiết kế hàng đợi/background job với danh tính service riêng, lưu thông tin nghiệp vụ cần thiết thay vì giữ nguyên request context vô thời hạn.

Không thay toàn ứng dụng sang `MODE_GLOBAL` để “dùng được principal mọi nơi”: điều này có thể gây chia sẻ xác thực giữa người dùng khác nhau. `MODE_INHERITABLETHREADLOCAL` cũng cần thận trọng với thread pool và vòng đời tác vụ.

### 8.2. Principal không phải dữ liệu để tin vô điều kiện

Một giá trị lấy từ `Authentication` phải có nguồn xác thực đáng tin cậy và được xử lý đúng ngữ cảnh. Những lỗi phổ biến:

- Đọc user ID trực tiếp từ query/header rồi gán vào principal mà không xác minh.
- Tin `sub` khi không kiểm tra `iss`, `aud` hoặc chữ ký access token.
- Đồng nhất email với ID bất biến trong hệ thống, mặc dù email có thể thay đổi.
- Dùng `authentication.getName()` làm user ID ở token endpoint của Client Credentials.
- Ghi cả JWT, thông tin xác thực client, authorization code, credential hoặc toàn bộ Authentication xuống log.
- Bỏ tenant/object-level authorization chỉ vì principal có role/scope hợp lệ.

### 8.3. Trường hợp anonymous và lỗi HTTP

Ba trạng thái nên tách biệt:

1. **Không xác thực hợp lệ:** thường dẫn đến `401 Unauthorized` khi gọi API yêu cầu xác thực hoặc redirect đến login ở request trình duyệt.
2. **Đã xác thực nhưng không đủ quyền:** thường dẫn đến `403 Forbidden`.
3. **Có quyền endpoint nhưng không có quyền trên bản ghi:** service/authorizer phải từ chối truy cập theo chính sách; không để lộ dữ liệu ngoài quyền.

Quy tắc HTTP có thể khác khi áp dụng error handler, redirect hoặc chính sách che tồn tại đối tượng. Nhưng việc kiểm soát quyền trên dữ liệu luôn phải có ở mức phù hợp.

## 9. Kiểm thử SecurityContext và thông tin authorization

### 9.1. Kiểm tra chính sách MVC/Resource Server

Với `spring-security-test`, có thể giả lập một principal có scope trong MockMvc:

~~~java
mockMvc.perform(get("/api/bookings")
        .with(jwt().jwt(jwt -> jwt.subject("user-123"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_booking.read")
            )))
    .andExpect(status().isOk());
~~~

Kiểm thử này phù hợp để xem **endpoint mapping + authorization** hoạt động như mong đợi khi đã có Authentication tương ứng. Nó **không chứng minh** JWT thật có chữ ký/issuer/audience hợp lệ, vì `jwt()` trong spring-security-test tạo Authentication mô phỏng thay vì chạy toàn bộ quy trình xác minh chữ ký.

Thử thêm các trường hợp đối xứng:

- Không có `jwt()` → request cần xác thực phải bị từ chối.
- JWT giả lập không có `SCOPE_booking.read` → request đọc booking bị từ chối.
- Có scope nhưng booking thuộc người dùng/tenant khác → business authorization từ chối.
- Có issuer, subject hoặc tenant không được ánh xạ → không nhận nhầm quyền của người dùng khác.

### 9.2. Kiểm thử Authorization Server

Các ca quan trọng:

| Bối cảnh | Điều cần xác minh |
| --- | --- |
| Chưa đăng nhập, gọi authorization endpoint | AS dẫn tới login hoặc phản hồi giao thức phù hợp, chưa cấp code cho user chưa xác thực |
| Đăng nhập thành công rồi quay lại authorization endpoint | Context mới khôi phục đúng Resource Owner từ session |
| Client hoặc redirect URI không hợp lệ | AS từ chối, không dựa vào principal người dùng để bỏ qua kiểm tra client |
| Consent chỉ cấp một phần scope | `OAuth2Authorization` lưu `authorizedScopes` chính xác |
| Token endpoint với client hợp lệ + authorization code hợp lệ | AS đối chiếu grant lưu bền vững và xác thực client đúng cách |
| Token endpoint với client khác hoặc `code_verifier` sai | Không cấp access token |
| Client Credentials | Principal/grant có thể liên quan client mà không có user đăng nhập |
| OIDC UserInfo với access token sai/thiếu | Không tiết lộ claim người dùng |

Ở bài kiểm thử tích hợp, hãy dùng application context thật và một kho lưu authorization phù hợp với mục tiêu test. Khi viết test chỉ giả lập `@WithMockUser`, bạn kiểm tra một phần authorization của Spring Security nhưng **chưa kiểm tra đầy đủ** quá trình login, OAuth2 grant, PKCE, token signature hoặc session persistence.

### 9.3. Dùng log để chẩn đoán mà không lộ bí mật

Với một yêu cầu bị từ chối, nên xác định theo trình tự:

1. Request khớp **SecurityFilterChain** nào? Có nhầm chain AS và chain dành cho login/API không?
2. Filter đã nhận thông tin xác thực ở đâu: session cookie, client credentials hay Bearer token?
3. `Authentication` thực tế là lớp nào? `getName()` biểu thị user hay client?
4. Authority đã được tạo/ánh xạ thành các giá trị nào? Có tiền tố `ROLE_`/`SCOPE_` đúng chính sách không?
5. Authorization thất bại ở layer endpoint, method hay quy tắc nghiệp vụ?
6. Token, consent, authorization code đã được lưu/khôi phục theo cấu hình đúng chưa?

Chỉ log metadata tối thiểu như request ID, tên chain, endpoint, loại authentication, tên rule và mã lỗi; không log raw Bearer token, client secret, password, authorization code hay các claim riêng tư không cần thiết.

## 10. Những lỗi kiến trúc thường gặp

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| Xem `SecurityContextHolder` là kho lưu người dùng toàn hệ thống | Lẫn request, rò danh tính giữa thread | Để Spring Security quản lý vòng đời request; dùng repository/session hoặc token khi cần lưu bền |
| Giả định `getPrincipal()` luôn là `UserDetails` | `ClassCastException`, nhầm Client thành User | Kiểm tra loại Authentication và ngữ cảnh endpoint |
| Cho rằng token endpoint vẫn có principal user từ login request | Sai chủ thể, lỗi xử lý code/claim | Dùng mô hình grant được lưu qua `OAuth2AuthorizationService` |
| Đồng nhất `OAuth2Authorization` với `SecurityContext` | Thiết kế trạng thái và persistence sai | Tách context của request khỏi authorization record |
| Chỉ cần `isAuthenticated()==true` là cho phép | Anonymous có thể lọt qua kiểm tra thủ công | Dùng `authenticated()` và chính sách Spring Security phù hợp |
| Chỉ kiểm tra scope mà không kiểm tra booking owner | Truy cập dữ liệu của người khác (BOLA/IDOR) | Kiểm tra object-level access tại service |
| Không lưu context sau xác thực tùy biến | Request tiếp mất login | Dùng đúng `SecurityContextRepository.saveContext(...)` khi cần bền qua request |
| Dùng ThreadLocal principal trong task async không kiểm soát | Principal rỗng/sai hoặc rò qua thread pool | Truyền identity cần thiết hoặc dùng delegating security context đúng vòng đời |
| Tin claims của JWT đã parse mà chưa xác minh | Có thể chấp nhận token giả/sai audience | Xác minh token theo chuẩn và chính sách Resource Server |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao cùng một người dùng có thể có `SecurityContext` khác nhau ở hai request liên tiếp?

**Đáp án:** Mỗi request có vòng đời context riêng. Context có thể được khôi phục từ session hoặc thiết lập từ token, nhưng không có ThreadLocal toàn cục liên tục dùng chung cho mọi request.

**Câu 2.** `GET /oauth2/authorize` và `POST /oauth2/token` có luôn cùng `principal` không?

**Đáp án:** Không. Authorization endpoint thường gắn với Resource Owner; token endpoint cần xác thực client và đối chiếu grant lưu bền vững. Principal hiện tại có thể đại diện client.

**Câu 3.** `OAuth2AuthorizationService` có tác dụng gì nếu `SecurityContextHolder` đã chứa user?

**Đáp án:** Nó lưu authorization grant và token/code cùng metadata qua nhiều request và có thể qua nhiều phiên. Context chứa Authentication của request, không thay thế dữ liệu grant.

**Câu 4.** JWT đã được xác thực, có `SCOPE_booking.read`, vậy có thể đọc mọi booking không?

**Đáp án:** Không. Resource Server phải kiểm tra đối tượng nhận, scope và quyền sở hữu/tenant trên từng dữ liệu theo chính sách.

**Câu 5.** `@WithMockUser` hoặc `jwt()` trong MockMvc chứng minh chữ ký JWT production hợp lệ chưa?

**Đáp án:** Chưa. Chúng hỗ trợ kiểm thử rule xử lý Authentication giả lập. Phải có test tích hợp xác minh token thật/metadata/khóa nếu muốn chứng minh giao thức end-to-end.

**Câu 6.** Khi tự viết login controller và muốn người dùng còn đăng nhập ở request sau, chỉ `SecurityContextHolder.setContext(...)` đã đủ chưa?

**Đáp án:** Không nhất thiết. Với cơ chế explicit-save, cần lưu vào `SecurityContextRepository` theo đúng cấu hình; các filter login tiêu chuẩn xử lý phần này theo flow của chúng.

## 12. Kết luận và tài liệu tham khảo

Đối với mỗi request, hãy trả lời theo thứ tự: **request vào chain nào; cơ chế nào tạo Authentication; principal hiện tại là user hay client; authorities có ý nghĩa gì; và quy tắc nào quyết định quyền truy cập?** Khi request thuộc Authorization Server, phải hỏi thêm **grant và consent nào đã được lưu**, vì `OAuth2Authorization` không phải là `SecurityContext`.

Trong Spring Boot/Spring Security và Spring Authorization Server, phân biệt được các lớp này sẽ giúp xử lý chính xác login, consent, authorization code, token endpoint, OIDC UserInfo, Resource Server, kiểm thử và vận hành mà không đánh đồng phiên đăng nhập người dùng với trạng thái cấp token.

Tài liệu chính thức để kiểm tra API theo đúng phiên bản dự án:

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)

Các ví dụ dựa trên khái niệm Spring Security Servlet và nhánh Spring Authorization Server 1.x; nếu ứng dụng dùng thế hệ Spring Security có Authorization Server tích hợp, cần đối chiếu class, API và package theo tài liệu của phiên bản cụ thể.


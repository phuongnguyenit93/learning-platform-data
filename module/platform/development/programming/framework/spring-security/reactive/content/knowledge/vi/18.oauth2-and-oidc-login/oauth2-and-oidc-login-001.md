# Vai trò ứng dụng WebFlux khi dùng OAuth2 Login và OpenID Connect

**Module:** Spring Security – reactive (Spring WebFlux)  
**Phần:** Đăng nhập OAuth2/OIDC  
**Mục tiêu:** Xác định chính xác ứng dụng WebFlux đóng **vai trò OAuth 2.0 Client / OpenID Connect Relying Party**, hiểu nó làm gì trong Authorization Code flow, phân biệt ứng dụng với Authorization Server/Identity Provider và Resource Server, cấu hình `oauth2Login()`, quản lý principal/session/token và kiểm thử đúng ranh giới.

Một ứng dụng Spring WebFlux có nút **“Đăng nhập với Google”** không tự trở thành nơi phát token hoặc xác thực mật khẩu Google. Nó đóng vai trò **Client** của một Authorization Server và, khi dùng OpenID Connect, đóng vai trò **Relying Party (RP)** tin vào thông tin xác thực đã được **OpenID Provider (OP)** kiểm chứng. WebFlux chuyển hướng trình duyệt sang OP, xử lý callback chứa authorization code, trao đổi code lấy token **ở phía server**, xác minh danh tính theo giao thức và tạo `Authentication` cho phiên cục bộ của ứng dụng.

**Ghi nhớ:** `oauth2Login()` giải quyết **đăng nhập cho ứng dụng web**. `oauth2Client()` hỗ trợ **gọi API bên ngoài bằng access token**. `oauth2ResourceServer()` dùng khi **chính API của bạn nhận Bearer token từ client**. Các chức năng có thể cùng tồn tại trong một hệ thống nhưng **không tương đương**. Phát token, quản lý phiên SSO và quản lý credential gốc của người dùng thuộc **Authorization Server/OP/IdP** (hoặc một sản phẩm như Spring Authorization Server riêng).

## 1. Bản đồ vai trò: ai làm việc gì?

Trong OAuth 2.0 có các vai trò Resource Owner, Client, Authorization Server, Resource Server. OpenID Connect (OIDC) bổ sung lớp đăng nhập danh tính: OpenID Provider (OP), Relying Party (RP), ID Token và các cơ chế kiểm tra danh tính.

| Vai trò | Nhiệm vụ chính | Ví dụ trong tình huống WebFlux Login |
| --- | --- | --- |
| Resource Owner / End User | Người có tài khoản, thao tác đăng nhập và cấp quyền theo flow | Người dùng mở website của bạn |
| **OAuth2 Client** | Yêu cầu authorization, nhận callback, trao đổi authorization code, quản lý access token được cấp | **Ứng dụng Spring WebFlux của bạn** |
| **OIDC Relying Party (RP)** | Dựa vào xác thực từ OP, xác minh ID Token, tạo user principal cho website | **Cũng chính ứng dụng WebFlux khi scope có `openid`** |
| Authorization Server (AS) | Quản lý authorization request, cấp authorization code và OAuth2 access/refresh token | Dịch vụ Google Identity / IdP doanh nghiệp |
| OpenID Provider (OP) | AS hỗ trợ OIDC, xác thực người dùng và phát `id_token`, có thể cung cấp UserInfo | Google hoặc OP được tổ chức tin cậy cấu hình |
| Resource Server | Bảo vệ API/resource bằng cách kiểm Bearer access token được gửi vào | API CRM, báo cáo, dữ liệu riêng |
| Browser (user agent) | Theo redirect giữa RP và OP, lưu cookie của từng site theo chính sách | Chrome/Firefox của người dùng |
| API Gateway/BFF | Nếu có, đại diện hoặc bảo vệ ranh giới browser/backend | Gateway trước WebFlux, không tự là OP |

**Trả lời đúng câu hỏi của bài:** Khi bạn viết `http.oauth2Login(...)` trong **Spring WebFlux**, ứng dụng thông thường là **OAuth2 Client và OIDC RP**, không phải OP, Authorization Server hay nhất thiết là Resource Server. Việc nó có thể đồng thời đóng vai trò khác phải được cấu hình/triển khai một cách có chủ đích.

### 1.1. So sánh ba cấu hình thường bị nhầm

| Spring Security WebFlux DSL | Vai trò mà nó phục vụ | Dữ liệu chính đi vào | Kết quả |
| --- | --- | --- | --- |
| `oauth2Login(Customizer.withDefaults())` | Web app login / RP | Callback `code` + `state`, trao đổi với OP | `OAuth2AuthenticationToken`, thường với `OidcUser`; session website |
| `oauth2Client(Customizer.withDefaults())` | OAuth2 Client để lấy/dùng access token | Client registration, authorized client/grants | Access token cho outbound `WebClient` |
| `oauth2ResourceServer(oauth -> oauth.jwt(...))` | Resource Server | Inbound `Authorization: Bearer ...` | Xác minh token JWT, tạo Authentication cho API |
| Spring Authorization Server (project riêng) | Authorization Server/OP nếu cấu hình OIDC | Login/consent/token requests | Cấp token, metadata/JWK endpoints, các protocol endpoints |

`oauth2Login` **là một tính năng của OAuth2 Client**, không phải chức năng hoàn toàn tách khỏi OAuth2 Client. Tuy nhiên bật `oauth2Client` **một mình** không tự cung cấp màn hình đăng nhập người dùng.

### 1.2. Ví dụ hai hệ thống trong cùng sản phẩm

Một website `https://portal.example.test` dùng WebFlux, người dùng đăng nhập qua OP. Sau đó server portal cần gọi `https://reports.example.test` để lấy báo cáo của người dùng:

```text
        Browser (SESSION cookie của portal)
                  |
                  v
      +-------------------------+
      | Spring WebFlux Portal   |
      | OAuth2 Client / OIDC RP |
      | OAuth2 Login            |
      | WebSession + Principal  |
      +-------+-----------+-----+
              |           |
  Code flow   |           | Access token trong outbound request
              v           v
       +-----------+   +----------------+
       | OIDC OP / |   | Reports API    |
       | IdP / AS  |   | Resource Server|
       +-----------+   +----------------+
```

Browser không nhất thiết sở hữu access token. Trong kiểu ứng dụng web server-side (BFF), access/refresh token thường được client backend quản lý và WebFlux dùng **session cookie** để nhận diện browser. Khi WebFlux gọi Reports API, nó có thể đính Bearer token **ở server-side outbound call**. Hai đường “browser → portal” và “portal → Reports API” có cơ chế credential khác nhau.

## 2. Phân biệt OAuth 2.0 và OpenID Connect

**OAuth 2.0** là framework cấp quyền truy cập tài nguyên. `access_token` nhằm cho **Resource Server** chấp nhận trong phạm vi được cấp; nó **không tự cung cấp chuẩn đăng nhập danh tính đầy đủ** chỉ vì tồn tại.

**OpenID Connect 1.0** xây trên OAuth 2.0 và dùng scope `openid` để yêu cầu đăng nhập chuẩn hóa. Trong flow phù hợp, OP phát **ID Token** chứa claims về sự kiện xác thực và end user. Ứng dụng RP kiểm ID Token theo quy tắc OIDC trước khi dựa vào `sub`/claims đó làm danh tính.

| Giá trị | Dùng để làm gì? | Ai nên sử dụng? | Không nên làm |
| --- | --- | --- | --- |
| `authorization_code` | Grant ngắn hạn để Client đổi token ở token endpoint | WebFlux backend theo code flow | Không dùng code làm session hoặc gọi API |
| `state` | Liên kết authorization response với request khởi tạo, chống login CSRF/mix-up theo flow | OAuth2 Client/RP | Không coi như access token |
| `code_verifier`/`code_challenge` (PKCE) | Ràng buộc người đổi code phải giữ verifier; hạn chế code interception | Client + Authorization Server | Không dùng PKCE thay xác minh `state`, `nonce` hoặc client registration |
| `nonce` (OIDC) | Liên kết ID Token với phiên authentication request, giảm replay/substitution | RP và OP theo profile | Không tự tạo rồi bỏ qua kiểm tra |
| **`id_token`** | Chứng cứ xác thực danh tính cho **RP**, thường là JWT ký số | RP/Client | **Không gửi làm access token** tới API |
| **`access_token`** | Credential cho API/resource server theo `scope`/`aud` | OAuth2 Client gửi cho Resource Server | Không dùng bừa để chứng minh login |
| `refresh_token` (nếu cấp) | Xin access token mới tại AS theo policy | Client được phép giữ | Không gửi cho Resource Server/browser nếu không cần |
| Browser session cookie | Duy trì authentication **cục bộ tại website WebFlux** | Browser và RP | Không suy ra cookie = access token |

### 2.1. Chỉ thêm scope openid đã thay đổi điều gì?

Spring Security OAuth2 Login nhìn vào registration/scopes. Khi registration dùng `openid`, luồng được xử lý theo OIDC: RP có `OidcUser`/`OidcIdToken` và service như `OidcReactiveOAuth2UserService`. Nếu nhà cung cấp không hỗ trợ OIDC và không có scope `openid`, OAuth2 Login có thể dựa trên OAuth2 UserInfo service và `OAuth2User`; lúc đó **không có chuẩn ID Token OIDC**. Cả hai trường hợp có thể tạo `OAuth2AuthenticationToken` cho website, nhưng độ tin cậy của claims và cách lấy thuộc tính khác nhau.

Chỉ nhận `email` hoặc `name` từ một endpoint OAuth2 không chứng minh user đã được xác thực theo OIDC. Email có thể đổi; `sub` (kết hợp `iss` đáng tin) ổn định hơn khi làm định danh nội bộ. Không dùng email trần làm key phân biệt duy nhất trên mọi provider/tenant.

## 3. Chu trình đăng nhập OIDC Authorization Code flow

Giả sử registrationId là `google`:

```text
(1) Browser -> WebFlux:
    GET /oidc/me  [chưa có SESSION đăng nhập]
        |
        v
(2) WebFlux Security:
    chưa authenticated -> redirect trang /login
    hoặc link trực tiếp /oauth2/authorization/google
        |
        v
(3) WebFlux OAuth2 Client:
    tạo authorization request:
      response_type=code
      client_id=...
      redirect_uri=https://portal.../login/oauth2/code/google
      scope=openid profile email
      state=...
      nonce=... (OIDC)
      PKCE params nếu được cấu hình/yêu cầu
    lưu context tương quan request trong WebSession/repository
        |
        v
(4) Browser theo redirect tới Google/OP authorization endpoint:
    user login/consent ở OP (không gửi password Google cho WebFlux)
        |
        v
(5) OP -> Browser -> WebFlux callback:
    GET /login/oauth2/code/google?code=...&state=...
        |
        v
(6) WebFlux OAuth2 Login filter:
    kiểm state/session + code flow
    backend POST code tới OP token endpoint qua HTTPS
    nhận access_token + id_token (+ optional refresh_token)
    xác minh OIDC ID Token theo provider/config
    (claims/nonce/JWS/issuer/audience/time theo flow)
    có thể gọi UserInfo nếu cần và được hỗ trợ
        |
        v
(7) Spring Security:
    tạo OidcUser / OAuth2AuthenticationToken
    lưu/khôi phục SecurityContext theo WebSession config
    quản lý OAuth2AuthorizedClient token liên quan
    redirect người dùng trở lại saved request hoặc success URL
        |
        v
(8) Browser GET /oidc/me với cookie phiên của portal:
    Spring Security nạp Authentication của phiên portal
    endpoint trả thông tin an toàn, không xuất token
```

**Đường mặc định cần nhớ:**

- Bắt đầu flow: `/oauth2/authorization/{registrationId}`, ví dụ `/oauth2/authorization/google`.
- Callback nhận code: `/login/oauth2/code/{registrationId}`, ví dụ `/login/oauth2/code/google`.
- Trang chọn provider: thường `/login` được Spring Security sinh khi có registration phù hợp.
- Redirect URI phía OP **phải khớp chính xác** callback RP đã đăng ký; các lỗi scheme/host/port/path là nguyên nhân phổ biến khiến Google/OP từ chối.

Các endpoint trên do security WebFilters xử lý; không cần tự viết controller `@GetMapping("/login/oauth2/code/google")` để đổi code thành token. **Không đặt client secret vào browser/JavaScript.**

### 3.1. Vai trò browser khác vai trò WebFlux

Browser đưa user tới OP và quay về RP; **backend WebFlux** mới thực hiện token exchange bằng `authorization_code` (trong kiểu confidential web client). Browser có thể thấy `code`/`state` trong callback URL ngắn hạn, nhưng không nên nhận client secret/refresh token. Spring Security quản lý correlation và authentication processing; code minh họa không cần tự parse callback vào controller hoặc copy code ra log.

### 3.2. state, nonce và PKCE không phải một biến

- **`state`:** Liên kết flow khởi tạo và callback, phát hiện callback không được yêu cầu. Nếu user mở hai tab đăng nhập, session/correlation phải đúng; không bỏ kiểm `state` để “sửa” lỗi callback.
- **`nonce`:** OIDC RP gửi nonce theo policy và so sánh với claim trong ID Token, giảm rủi ro replay/thay token. Không tự vô hiệu hóa nonce validation.
- **PKCE:** Nếu client/OP dùng PKCE, authorization request mang `code_challenge` và token request mang `code_verifier`. Với public clients, PKCE đặc biệt quan trọng; confidential clients cũng nên dùng nơi hỗ trợ/chính sách yêu cầu. Không giả định mọi cấu hình Spring/version tự phát PKCE giống nhau; kiểm request thực và provider registration.
- **HTTPS + exact redirect URI:** Bảo vệ code/token khỏi rò rỉ, giảm open redirect; không dùng wildcard redirect URI tùy tiện.

**Nếu thiếu hoặc sai `state`:** callback phải không được công nhận là login hoàn tất. Nếu ID Token sai `iss`/`aud`/chữ ký/thời gian/`nonce`: không được tạo authenticated session hợp lệ. Không “bỏ xác minh chữ ký” để chạy được một flow gặp lỗi.

## 4. Spring Security WebFlux cung cấp những thành phần nào?

| Component | Trách nhiệm | Không nên hiểu nhầm |
| --- | --- | --- |
| `ServerHttpSecurity.oauth2Login(...)` | Cài reactive OAuth2/OIDC browser-login flow | Không biến RP thành AS/OP |
| `ReactiveClientRegistrationRepository` | Lưu/tra `ClientRegistration` theo registrationId, client id, provider endpoints, scopes | Không phải database tài khoản người dùng |
| `ClientRegistration` | Mô tả app đã đăng ký với OP/AS | Không chứa session đăng nhập của từng user |
| `ServerOAuth2AuthorizationRequestResolver` và authorization-request repository | Tạo/lưu authorization request, giúp đối chiếu `state`/flow | Không lưu business transaction |
| `OAuth2AuthenticationToken` | Authentication sau OAuth2/OIDC login | Không đồng nhất với `JwtAuthenticationToken` của Resource Server |
| `OidcUser` / `OidcIdToken` | Principal và ID Token đã xử lý trong OIDC flow | Không phải Bearer token cho mọi API |
| `DefaultReactiveOAuth2UserService` | Lấy user attributes cho OAuth2 non-OIDC | Không tự thực hiện đăng nhập bằng OIDC ID Token |
| `OidcReactiveOAuth2UserService` | Xử lý OIDC user, có thể gọi UserInfo | Không phát access token |
| `ServerSecurityContextRepository` / WebSession | Duy trì Authentication cục bộ giữa các browser HTTP requests | Không phải nơi OP quản lý phiên SSO |
| `OAuth2AuthorizedClient` | Ghép client registration + principal name + access token/optional refresh token | Không phải profile người dùng công khai |
| `ServerOAuth2AuthorizedClientRepository` / `ReactiveOAuth2AuthorizedClientService` | Lưu/đọc authorized clients theo thiết kế | Không tự thu hồi mọi token khi local logout |
| `ReactiveOAuth2AuthorizedClientManager` | Điều phối cấp/làm mới authorized client tokens khi được cấu hình | Không thay ứng dụng xác minh quyền domain |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Đính Bearer token cho **outbound WebClient** một cách có chủ đích | Không nên tự đính token cho mọi URL |
| `OAuth2ResourceServerSpec` | Bảo vệ **inbound** API bằng Bearer | Không phải cách tự động tạo website login |

### 4.1. Ba dạng dữ liệu dễ bị đặt nhầm chỗ

**ClientRegistration** là cấu hình của ứng dụng với provider (client ID, secret, endpoints, scopes, redirect URI). Một app có thể có nhiều registrations, ví dụ Google và IdP nội bộ.

**SecurityContext** trả lời “browser request này đang được ứng dụng coi là người nào?”. Trong website session-based, context thường được giữ trong WebSession và có thể đọc từ `ReactiveSecurityContextHolder`.

**OAuth2AuthorizedClient** trả lời “ứng dụng đang giữ authorization/token nào liên quan đến registration và principal này để gọi API?”. Access/refresh token nằm trong lớp này theo provider policy và storage. Không gửi nó vào JSON profile trả về cho browser. Một application có thể có session đăng nhập nhưng chưa có token mới cho một API khác, hoặc có token nhưng session đã bị vô hiệu hóa; lifecycle cần quản lý riêng.

### 4.2. Reactor Context vẫn là nguồn Authentication trong pipeline

WebFlux xử lý request trên non-blocking pipeline. Khi đọc principal ở service, dùng `ReactiveSecurityContextHolder` hoặc method parameter được Spring hỗ trợ, **không** lấy người dùng từ biến static hoặc `ThreadLocal SecurityContextHolder` của Servlet:

```java
Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
```

Đây là fragment cần import. Một WebFlux thread có thể phục vụ nhiều user xen kẽ; Reactor Context là gắn với subscription/request. Tránh gọi `subscribe()` tách rời hoặc `block()` trong handler.

## 5. Sau login, Authentication có phải access token không?

**Không.** Sau OAuth2/OIDC login, Spring Security thường có `OAuth2AuthenticationToken` với principal `OAuth2User` hoặc `OidcUser`. Website có thể dùng session cookie `SESSION` để duy trì Authentication giữa các HTTP requests. Access token được giữ trong authorized client store để WebFlux **gọi API** nếu business cần.

So sánh:

| Tình huống | Cookie/Authorization inbound đến WebFlux | Authentication thường gặp | Bên kiểm tra credential |
| --- | --- | --- | --- |
| User đang dùng website RP đã login OIDC | `Cookie: SESSION=...` | `OAuth2AuthenticationToken` với `OidcUser` | WebFlux đọc WebSession/SecurityContext đã thiết lập |
| API Resource Server nhận JWT | `Authorization: Bearer ...` | `JwtAuthenticationToken` | JWT decoder kiểm token |
| API Resource Server nhận opaque token | `Authorization: Bearer ...` | `BearerTokenAuthentication` | Introspection/opaque token validator |
| Browser sử dụng HTTP Basic | `Authorization: Basic ...` | `UsernamePasswordAuthenticationToken` hoặc dạng theo manager | Basic authentication manager |
| OP/IdP xử lý login của user | Credential/trạng thái OP riêng | Theo OP implementation | OP, **không phải WebFlux RP** |

Cùng một user có thể có **session SSO ở OP** và **session cục bộ ở RP**. Logout cục bộ thường kết thúc một phiên RP, không tự động kết thúc SSO ở OP hoặc thu hồi access/refresh token. Cần cơ chế OIDC RP-Initiated Logout/Back-Channel Logout và revocation riêng khi yêu cầu sản phẩm đòi hỏi.

## 6. Mô hình Java 17 độc lập: nhận diện vai trò bằng ngôn ngữ rõ ràng

Trước khi cấu hình framework, thử chương trình nhỏ dưới đây. Nó không thực hiện OAuth2/OIDC thật và không xác minh JWT; chỉ mô tả vai trò của các thành phần.

Lưu `OAuth2RoleDemo.java`:

```java
import java.util.List;

public class OAuth2RoleDemo {
    record Component(String name, String role) {}

    public static void main(String[] args) {
        List<Component> architecture = List.of(
            new Component("Browser", "User Agent"),
            new Component("WebFlux Portal", "OAuth2 Client / OIDC RP"),
            new Component("Identity Provider", "Authorization Server / OP"),
            new Component("Reports API", "Resource Server")
        );

        architecture.forEach(component ->
            System.out.println(component.name() + " -> " + component.role())
        );
    }
}
```

Chạy với JDK 17+:

```bash
javac OAuth2RoleDemo.java
java OAuth2RoleDemo
```

**Stdout chính xác:**

```text
Browser -> User Agent
WebFlux Portal -> OAuth2 Client / OIDC RP
Identity Provider -> Authorization Server / OP
Reports API -> Resource Server
```

Đây là bài tập phân loại, không phải OAuth2 implementation. **Đừng** tự viết code trao đổi authorization code hoặc tự verify ID Token chỉ bằng decode Base64; phần tiếp theo dùng Spring Security thực.

## 7. Ứng dụng Spring Boot WebFlux Java 17+ có cấu hình OAuth2/OIDC Login

Ta xây website WebFlux có các đường:

- `GET /` công khai, trả `public-home`.
- `GET /oidc/me` yêu cầu người dùng đã đăng nhập **theo OIDC**, trả JSON gồm `sub`, registration ID và loại principal, **không trả raw ID Token/access token**.
- `GET /oidc/admin` chỉ cho `ROLE_ADMIN`, minh họa rằng login thành công **chưa đủ** để có role nghiệp vụ.
- `POST /oidc/preferences` mô phỏng một mutation dùng WebSession, vì thế **vẫn cần CSRF token**.
- Trang `/login` và authorization-start `/oauth2/authorization/google` do Spring Security sinh/xử lý.
- Callback `/login/oauth2/code/google` do Spring Security WebFilter xử lý.
- Logout cục bộ giữ cơ chế mặc định; OP logout chỉ được cấu hình thêm nếu provider hỗ trợ (phần 11).

**Điều kiện chạy:** Có thể khởi động app với dummy client id/secret, xem trang login và bắt đầu redirect, chạy các test `mockOidcLogin()` **không gọi OP thật**. Muốn **hoàn tất đăng nhập Google thật**, phải có OAuth client ID/secret hợp lệ được cấp bởi Google, cấu hình redirect URI trùng khớp và kết nối tới provider. Không tuyên bố login thật chạy được với dummy credential.

### 7.1. Cấu trúc project

```text
webflux-oidc-rp/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/oidc/
    │   │   ├── OidcRpApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ProfileController.java
    │   └── resources/application.properties
    └── test/java/demo/oidc/
        └── OidcRpTests.java
```

Ví dụ dùng **Java 17+, Maven và Spring Boot 3.5.7**. Đó là một mốc dependency cho giáo trình; khi triển khai thật phải chọn phiên bản còn được hỗ trợ, có bản vá bảo mật. Không thêm `spring-boot-starter-web` vì bài dùng WebFlux, không phải Servlet MVC.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webflux-oidc-rp</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.2. Properties: ClientRegistration tên google

`src/main/resources/application.properties`:

```properties
spring.application.name=webflux-oidc-rp
server.port=8080

# CommonOAuth2Provider.GOOGLE cung cấp mặc định các endpoint phổ biến.
# Thay bằng client ID/secret thật qua môi trường trước khi login thật.
spring.security.oauth2.client.registration.google.client-id=${GOOGLE_CLIENT_ID:training-client-not-valid}
spring.security.oauth2.client.registration.google.client-secret=${GOOGLE_CLIENT_SECRET:training-secret-not-valid}
spring.security.oauth2.client.registration.google.authorization-grant-type=authorization_code
spring.security.oauth2.client.registration.google.scope=openid,profile,email
spring.security.oauth2.client.registration.google.redirect-uri={baseUrl}/login/oauth2/code/{registrationId}
```

`${...}` trong nguồn Markdown được thay thành cú pháp Spring property placeholder `${...}` ở nội dung đã lưu. Các giá trị mặc định `training-...-not-valid` chỉ giúp cấu hình có định dạng; **không phải credential thật**. Khi đổi sang provider doanh nghiệp, đặt `spring.security.oauth2.client.registration.<id>.provider=<providerId>` và `spring.security.oauth2.client.provider.<providerId>.issuer-uri=https://trusted-idp.example/...` theo OIDC Discovery. Chỉ trust issuer/metadata/JWK của provider được duyệt.

**Với Google:** Đăng ký redirect URI **chính xác** `http://localhost:8080/login/oauth2/code/google` cho local test trong Google Cloud Console (chính sách của nhà cung cấp có thể hạn chế loại URI/client). Khi chạy qua HTTPS/Ingress, `{baseUrl}` cần phản ánh host/scheme đúng; chỉ nhận forwarded headers từ proxy đáng tin, không tin tùy tiện `X-Forwarded-Host` từ Internet.

### 7.3. Application entry point

`src/main/java/demo/oidc/OidcRpApplication.java`:

```java
package demo.oidc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcRpApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcRpApplication.class, args);
    }
}
```

### 7.4. SecurityConfig: website là OIDC RP

`src/main/java/demo/oidc/SecurityConfig.java`:

```java
package demo.oidc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/", "/signed-out").permitAll()
                .pathMatchers("/login",
                    "/oauth2/authorization/**",
                    "/login/oauth2/code/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/oidc/admin")
                    .hasRole("ADMIN")
                .pathMatchers("/oidc/**").authenticated()
                .anyExchange().denyAll())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            // CSRF mặc định vẫn bật cho browser session POST.
            .build();
    }
}
```

**Đọc config:**

1. `@EnableWebFluxSecurity` bật reactive security WebFilters. `ServerHttpSecurity` là DSL của WebFlux; tránh lẫn với `HttpSecurity`/`SecurityFilterChain` Servlet.
2. `oauth2Login` cung cấp authorization code + OIDC login cho website; `oauth2Client` cho authorized-client integration, ví dụ `WebClient` gọi upstream.
3. Đường login start và callback được permit để filter chuyên trách xử lý flow; không cấp quyền `/oidc/**` cho người chưa đăng nhập.
4. `/oidc/admin` đòi `ROLE_ADMIN`. OIDC login **không tự tạo role ADMIN cho mọi tài khoản**; bạn phải thiết kế mapping role tin cậy theo policy doanh nghiệp nếu cần.
5. `anyExchange().denyAll()` chặn route chưa định nghĩa. Mặc định CSRF cho POST session vẫn được giữ, không gọi `csrf.disable()` chỉ vì website có OAuth2.
6. App là OAuth2 Client/RP. **Không** thấy cấu hình phát JWT, token endpoint của AS, hoặc `oauth2ResourceServer(jwt)` cho inbound bearer.

### 7.5. Controller: chỉ trả thông tin cần thiết của OidcUser

`src/main/java/demo/oidc/ProfileController.java`:

```java
package demo.oidc;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class ProfileController {

    public record IdentityView(
        String subject,
        String registrationId,
        String principalType
    ) {}

    @GetMapping(value = "/", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicHome() {
        return Mono.just("public-home");
    }

    @GetMapping(value = "/signed-out",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> signedOut() {
        return Mono.just("signed-out");
    }

    @GetMapping(value = "/oidc/me",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<IdentityView> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(authentication -> {
                if (!(authentication instanceof OAuth2AuthenticationToken oauth)
                        || !(oauth.getPrincipal() instanceof OidcUser oidc)) {
                    return Mono.error(new ResponseStatusException(
                        HttpStatus.FORBIDDEN, "OIDC login required"));
                }

                // Không trả raw id_token, access_token, refresh_token
                // hay tất cả OIDC claims cho browser.
                return Mono.just(new IdentityView(
                    oidc.getSubject(),
                    oauth.getAuthorizedClientRegistrationId(),
                    "OIDC_USER"
                ));
            });
    }

    @GetMapping(value = "/oidc/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> admin() {
        return Mono.just("admin-only");
    }

    @PostMapping(value = "/oidc/preferences",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> preferences() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(name -> "saved:" + name);
    }
}
```

`OidcUser.getSubject()` là định danh từ ID Token theo OP; nếu ứng dụng hỗ trợ nhiều OP/tenant, hãy lưu identity khóa theo **(issuer, subject)** chứ không dựa riêng vào email. API demo trả `subject` vì mục tiêu học; production cần phân loại PII và giới hạn response theo quyền.

**Không bao giờ** trả `OidcUser.getIdToken().getTokenValue()` hoặc `OAuth2AuthorizedClient.getAccessToken().getTokenValue()` trong profile response chỉ để tiện debug. Token là credential/có claims nhạy cảm. Nếu cần quan sát, log metadata an toàn (issuer, registrationId, status), không log token.

## 8. Kiểm thử không cần OP thật bằng mockOidcLogin và WebTestClient

Có **hai lớp test** cần phân biệt:

- **In-memory WebFlux security test**: `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` và `mutateWith(mockOidcLogin())` mô phỏng Authentication/authorized client, chứng minh controller và authorization policy hoạt động. Nó **không** đi ra Internet, không đổi authorization code thật, không tự xác minh token từ OP.
- **End-to-end với OP thật hoặc mock OP đúng giao thức**: browser đi qua `/oauth2/authorization/google`, `state`/`nonce`/PKCE được quản lý đúng, OP gọi callback, backend đổi code, verify ID Token/JWK/claims và lập session. Cần môi trường OP phù hợp, không thể chỉ mock một OidcUser rồi coi đã kiểm chứng toàn bộ OAuth2.

Thêm dependency `spring-security-test` như `pom.xml` ở trên. Vì `mockOidcLogin()` làm việc ở **WebTestClient bound to application context**, không dùng một HTTP client gọi server thật rồi tưởng mutator có thể tự giả session ở đầu server.

`src/test/java/demo/oidc/OidcRpTests.java`:

```java
package demo.oidc;

import java.net.URI;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Login;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class OidcRpTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicHomeIsAccessibleWithoutLogin() {
        client.get().uri("/")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public-home");
    }

    @Test
    void anonymousProtectedResourceNeedsLogin() {
        client.get().uri("/oidc/me")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION,
                location -> assertTrue(location.contains("/login")));
    }

    @Test
    void generatedLoginPageContainsGoogleAuthorizationLink() {
        client.get().uri("/login")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .value(html -> assertTrue(
                html.contains("/oauth2/authorization/google")));
    }

    @Test
    void authorizationStartRedirectsToProviderWithState() {
        client.get().uri("/oauth2/authorization/google")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION, location -> {
                URI destination = URI.create(location);
                assertEquals("https", destination.getScheme());
                assertEquals("accounts.google.com", destination.getHost());
                assertNotNull(destination.getRawQuery());
                assertTrue(destination.getRawQuery()
                    .contains("response_type=code"));
                assertTrue(destination.getRawQuery()
                    .contains("state="));
                assertTrue(destination.getRawQuery()
                    .contains("client_id="));
            });
    }

    @Test
    void mockOidcPrincipalIsVisibleToReactiveController() {
        client.mutateWith(mockOidcLogin())
            .get().uri("/oidc/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("user")
            .jsonPath("$.principalType").isEqualTo("OIDC_USER")
            .jsonPath("$.registrationId").exists();
    }

    @Test
    void plainOAuth2UserIsNotAccidentallyTreatedAsOidcUser() {
        client.mutateWith(mockOAuth2Login())
            .get().uri("/oidc/me")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void oidcLoginDoesNotAutomaticallyGrantAdminRole() {
        client.mutateWith(mockOidcLogin())
            .get().uri("/oidc/admin")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void explicitlyMappedAdminAuthorityCanEnterAdminRoute() {
        client.mutateWith(mockOidcLogin().authorities(
                new SimpleGrantedAuthority("ROLE_ADMIN")))
            .get().uri("/oidc/admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-only");
    }

    @Test
    void oidcBrowserPostWithoutCsrfIsRejected() {
        client.mutateWith(mockOidcLogin())
            .post().uri("/oidc/preferences")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void oidcBrowserPostWithCsrfIsAccepted() {
        client.mutateWith(mockOidcLogin())
            .mutateWith(csrf())
            .post().uri("/oidc/preferences")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("saved:user");
    }
}
```

Chạy:

```bash
mvn test
```

**Mục tiêu: 10 bài test** với project trên trong môi trường phù hợp. Đây là ví dụ để người học chạy; **không khẳng định đã chạy Maven hoặc đã thử login Google trong hệ thống của bạn**. Khi gặp version-specific differences, đọc response/debug output và đối chiếu API Spring Security phiên bản tương ứng. Trường hợp generated login page hoặc Google endpoint thay đổi do provider/framework thì điều chỉnh expected condition theo cấu hình được kiểm chứng, không thay rule quyền cho test xanh.

### 8.1. Điều mà bộ test chứng minh, và điều không chứng minh

| Test | Chứng minh | Không chứng minh |
| --- | --- | --- |
| Public 200 / anonymous redirect | Routing và yêu cầu login trong WebFlux chain | Người dùng đã đăng nhập ở OP |
| Generated login page / authorization start | Registration ID `google` được liên kết tới authorization endpoint; URL có `state` | OP thực sự cấp code hợp lệ |
| `mockOidcLogin()` trả subject | Controller xử lý `OidcUser` đúng trong Reactor/Authentication context | ID Token của nhà cung cấp đã được xác minh thật |
| `mockOAuth2Login()` bị từ chối ở OIDC-only endpoint | Phân biệt `OAuth2User` và `OidcUser` | Tất cả provider hỗ trợ OIDC |
| Default role bị 403 / test role ADMIN được 200 | Authorization rule hoạt động | Provider claims được map thành ADMIN trong production |
| POST thiếu/có CSRF | Cookie-style web mutation còn CSRF protection | Cross-site browser/proxy production luôn đúng |

Đặc biệt, `mockOidcLogin()` cố ý **bỏ qua token exchange/cryptographic verification**. Đừng dùng test đó thay cho bộ e2e về `state`/`nonce`/PKCE, issuer/audience, callback URI, token expiry, logout và OP failure cases. Test thật phải dùng một OP kiểm thử tin cậy hoặc môi trường sandbox/provider đã đăng ký.

## 9. Chạy thử đăng nhập OIDC với Google thật

### 9.1. Chuẩn bị

- Tạo OAuth2 **Web application client** trên provider; lấy `client-id` và `client-secret`, quản lý secret trong environment/secret store.
- Đăng ký authorized redirect URI **chính xác** `http://localhost:8080/login/oauth2/code/google` khi thử local. Với production, dùng HTTPS và base URL được kiểm soát.
- Nếu provider yêu cầu OAuth consent screen/test users, cấu hình theo môi trường; đọc chính sách provider và scope được phê duyệt.
- Khởi động app với environment variables thật:

```bash
# Bash/Linux/macOS:
export GOOGLE_CLIENT_ID='your-issued-client-id'
export GOOGLE_CLIENT_SECRET='your-issued-client-secret'
mvn spring-boot:run
```

Trên PowerShell:

```powershell
$env:GOOGLE_CLIENT_ID = "your-issued-client-id"
$env:GOOGLE_CLIENT_SECRET = "your-issued-client-secret"
mvn spring-boot:run
```

Hai chuỗi `your-issued-...` là **placeholder phải thay** từ provider; không nên copy nguyên. Với môi trường tổ chức, dùng secret manager thay vì gõ credential thật vào shell history. Không commit `client-secret` vào Git hoặc gửi qua trình duyệt.

### 9.2. Hành trình trên browser

1. Trong cửa sổ ẩn danh, mở `http://localhost:8080/oidc/me`. Chưa có local authentication → browser đi tới `/login`.
2. Chọn provider Google (hoặc mở `http://localhost:8080/oauth2/authorization/google`). Trong DevTools/Network, xem `302` sang authorization endpoint của Google; URI có `client_id`, `redirect_uri`, `response_type=code`, `scope=openid...`, `state` và có thể có `nonce`/PKCE parameters.
3. Đăng nhập ở **OP/Google** và hoàn tất consent theo policy. Browser được redirect về callback `/login/oauth2/code/google?code=...&state=...`.
4. WebFlux Security kiểm flow, gọi token endpoint của OP **server-to-server**, xử lý ID Token/UserInfo và tạo local session. Browser trở lại `/oidc/me`.
5. Body `/oidc/me` hiển thị JSON có `subject` và `registrationId`; **không** hiển thị raw tokens. Kiểm session cookie đã được đặt với policy phù hợp.
6. Gọi `/oidc/admin` với tài khoản OIDC bình thường; nhận **403** nếu chưa có mapping authority `ROLE_ADMIN`. Điều này là đúng: danh tính đã xác thực không tự cấp quyền admin.
7. Thử `POST /oidc/preferences` không token CSRF: nhận **403**. Chỉ request được tạo đúng từ giao diện cùng origin có CSRF token hợp lệ mới được phép, với session đang authenticated.
8. Logout cục bộ rồi truy cập `/oidc/me` bằng session cũ: phải yêu cầu đăng nhập lại. Nếu OP SSO session còn, việc khởi tạo đăng nhập lại có thể diễn ra nhanh mà không yêu cầu password; đó **không** chứng minh local logout thất bại.

**Không** mở thử callback bằng cách tự ghép `?code=fake&state=fake` rồi mong login thành công. Authorization code là one-time credential được cấp bởi OP cho client, gắn với flow, redirect URI và correlation state.

### 9.3. curl chỉ dùng để quan sát giai đoạn bắt đầu

```bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/oidc/me
curl -i http://localhost:8080/login
curl -i http://localhost:8080/oauth2/authorization/google
```

Kỳ vọng: public 200, protected redirect, login page 200 HTML, authorization-start redirect tới Google (khi config hợp lệ). `curl` không mặc định giữ cookies giữa các lệnh hoặc thực hiện người dùng login/consent ở provider. **Không lấy một HTTP 302 làm bằng chứng đã xác thực OIDC thành công.** Dùng browser/cookie jar và một IdP kiểm thử thực để kiểm full flow.

## 10. OAuth2AuthorizedClient: WebFlux dùng access token gọi Resource Server

Sau khi đăng nhập, ứng dụng RP đôi khi cần gọi API khác. `OAuth2AuthorizedClient` chứa registration, principal name và OAuth access token (có thể thêm refresh token) để OAuth2 Client dùng. Spring Security có `ReactiveOAuth2AuthorizedClientManager` và `ServerOAuth2AuthorizedClientExchangeFilterFunction` cho outbound `WebClient`.

**Fragment tích hợp WebClient** (không phải file bắt buộc cho project demo vì cần resource server thật):

```java
@Bean
WebClient protectedApiClient(
        ReactiveOAuth2AuthorizedClientManager manager) {

    ServerOAuth2AuthorizedClientExchangeFilterFunction filter =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder()
        .filter(filter)
        .build();
}
```

Để chọn **authorized client đúng** cho một request, có thể nhận tham số controller:

```java
@GetMapping("/oidc/external-profile")
Mono<String> external(
        @RegisteredOAuth2AuthorizedClient("google")
        OAuth2AuthorizedClient authorizedClient) {

    return protectedApiClient.get()
        .uri("https://openidconnect.googleapis.com/v1/userinfo")
        .attributes(
            ServerOAuth2AuthorizedClientExchangeFilterFunction
                .oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class);
}
```

Đây là **fragment riêng**, cần bean WebClient, các import/đường URL API được phê duyệt, consent/scope và xử lý lỗi. Không phải mọi provider/scope cho phép gọi URL trong ví dụ. Một số provider trả UserInfo tự động trong login; không phải lúc nào ứng dụng cần tự gọi lại. Nếu token `openid profile email` không có scope cho API nghiệp vụ khác thì resource server đó có thể từ chối.

**Cảnh báo:** Tránh `filter.setDefaultOAuth2AuthorizedClient(true)` trên WebClient dùng chung để gọi các host bất kỳ: mặc định đó có thể gửi token của người dùng tới mọi outbound request thông qua client ấy. Chỉ định authorized client và endpoint đáng tin cậy; dùng WebClient tách biệt theo integration, validate host/scheme và không chuyển access token sang dịch vụ không được cấp audience/scope.

### 10.1. Quy tắc lưu token và quản lý session

- `ServerSecurityContextRepository`/WebSession: giữ Authentication cho website; browser giữ cookie phiên theo policy, không giữ raw refresh token ở cookie trừ thiết kế riêng có review.
- `ServerOAuth2AuthorizedClientRepository`/`ReactiveOAuth2AuthorizedClientService`: quản lý authorized client theo principal/registration, giữ access/refresh token ở backend theo policy. In-memory repository chỉ thích hợp demo/scope nhỏ; hệ nhiều node cần lưu trữ an toàn, lifecycle và encryption phù hợp.
- `ReactiveOAuth2AuthorizedClientManager`: khi được cấu hình với providers hỗ trợ, có thể refresh expired access token; **không giả định** mọi OP đều cấp refresh token hoặc refresh luôn thành công.
- Local logout: dọn SecurityContext/session theo config, đồng thời đánh giá liệu authorized clients/refresh tokens cần xóa/revoke ở provider; không đương nhiên.
- Không log `access_token`, `refresh_token`, `id_token`, `code`, raw `state`/`nonce` hoặc client secret. Hạn chế quyền đọc token store, backup và tracing baggage.

## 11. Đăng xuất: RP session khác OP SSO session

Khi browser POST `/logout` có CSRF, Spring Security có thể thực hiện **local logout** để xóa authentication của RP. Nhưng **OP session** và access/refresh tokens có lifecycle khác nhau:

- Local logout của WebFlux không tự làm OP đăng xuất mọi thiết bị.
- Access token JWT đã phát có thể vẫn được Resource Server chấp nhận tới `exp` nếu xác minh offline và không kiểm revocation.
- Refresh token có thể vẫn hợp lệ tới khi hết hạn/rotation/revocation theo chính sách OP.
- **OIDC RP-Initiated Logout** nếu OP hỗ trợ discovery `end_session_endpoint` cho phép RP yêu cầu browser đi tới OP để kết thúc phiên OP.
- **OIDC Back-Channel Logout** nếu hai bên cấu hình có thể giúp OP gửi Logout Token để RP dọn session tương ứng, không phải bearer-token revocation.

**Fragment biến thể** để thêm RP-Initiated Logout vào bean `SecurityWebFilterChain` (không chạy song song như bean chain thứ hai có cùng matcher):

```java
OidcClientInitiatedServerLogoutSuccessHandler oidcLogout =
    new OidcClientInitiatedServerLogoutSuccessHandler(
        reactiveClientRegistrationRepository);

oidcLogout.setPostLogoutRedirectUri("{baseUrl}/signed-out");

return http
    .authorizeExchange(ex -> ex
        .pathMatchers("/", "/signed-out").permitAll()
        .anyExchange().authenticated())
    .oauth2Login(Customizer.withDefaults())
    .logout(logout -> logout.logoutSuccessHandler(oidcLogout))
    .build();
```

Cần import `OidcClientInitiatedServerLogoutSuccessHandler` từ package `org.springframework.security.oauth2.client.oidc.web.server.logout` và `ReactiveClientRegistrationRepository`. **Chỉ bật khi provider thực sự hỗ trợ** `end_session_endpoint` và đã cho phép `post_logout_redirect_uri`. Với Google ví dụ, không nên mặc định chuẩn OIDC logout endpoint luôn có sẵn cho cùng registration; kiểm discovery/provider documentation trước.

**Chống CSRF cho logout:** Với browser sử dụng session cookie, logout thực sự qua POST cần token CSRF đúng theo Spring Security config. Đừng đổi thành GET có side effect chỉ để dễ viết link.

## 12. Các vấn đề bảo mật cần thiết của một Relying Party

### 12.1. Redirect URI và forwarded headers

`redirect_uri` ở authorization request phải trùng URI RP đã đăng ký ở OP. Khi chạy sau reverse proxy, URL được framework dựng từ scheme/host/port/path có thể sai nếu không cấu hình forwarded headers đáng tin. Không cho client ngoài Internet tự chèn `Forwarded`/`X-Forwarded-Host` được ứng dụng tin vô điều kiện; đó là nguy cơ open redirect và callback tới host lạ.

### 12.2. Phân quyền sau đăng nhập

OIDC chứng minh user đã được OP xác thực; nó **không tự quyết định quyền nghiệp vụ ở app**. `OidcUser` có `sub`, `email`, các claims và authorities đã được mapper cấp theo config. Khi cần role ADMIN/tenant quyền tài liệu, phải map từ nguồn tin cậy, kiểm issuer, claim mapping và domain policy; không tin header `X-Role` hay email domain chưa kiểm chứng.

Trong code example `/oidc/admin` yêu cầu `ROLE_ADMIN` để nhấn mạnh: đăng nhập được 200 ở `/oidc/me` **không** có nghĩa vào được admin route.

### 12.3. Không dùng ID Token như access token

`id_token` dành cho **client/RP** xác minh authentication. Resource Server API thường yêu cầu **access token** đúng audience, scopes và validation. Gửi ID Token tới API như bearer chỉ vì JWT có chữ ký là sai mục đích. Cũng không nên lấy email ID Token làm quyền duy nhất truy cập dữ liệu của mọi tenant.

### 12.4. XSS và CSRF khác nhau

Session cookie RP được browser tự gửi theo cookie rules, do đó các POST thay đổi trạng thái vẫn cần CSRF protection dù login bằng OAuth2/OIDC. XSS có thể thực hiện thao tác hợp lệ theo session hoặc làm lộ dữ liệu/token JavaScript-accessible; CSP, output encoding, cookie Secure/HttpOnly/SameSite và hạn chế script là lớp bảo vệ bổ sung, không thay `state`/`nonce`/CSRF.

### 12.5. Nhiều provider, account linking và multi-tenant

Một user có cùng email tại hai provider **không mặc nhiên là cùng identity**. Dùng tuple **`issuer + subject`** làm khóa liên kết tương ứng và quy trình account linking có xác nhận rõ. Tránh cho phép attacker ghép account nhờ email chưa verified; mapping role cho multi-tenant phải kiểm issuer/tenant allowlist và claim integrity.

### 12.6. Authorization code và token không được log/đưa vào URL ngoài ý định

`code` là grant ngắn hạn một lần và có thể nằm ở callback query, nên access logs/analytics/proxy phải redaction. Không gửi access/refresh/ID tokens qua query string, referer, lỗi HTTP, browser localStorage nếu policy không cho. Cấu hình cookie session phù hợp, rotate session ID khi authentication, timeout/logout và central session storage nếu nhiều app instances.

### 12.7. PKCE, nonce, state và issuer validation

Không tắt `state`, `nonce`, JWS ID Token validation, issuer/audience/time checks để “debug cho login được”. PKCE cải thiện chống code interception khi đúng flow, nhưng không thay việc kiểm state/redirect URI. Đổi provider/client type sẽ ảnh hưởng yêu cầu PKCE/client authentication: đối chiếu metadata và cấu hình thực.

### 12.8. Credential của Client khác credential của User

`client-id` định danh ứng dụng (không phải bí mật). `client-secret` hoặc private-key client authentication chứng minh **client** với AS theo phương pháp đã đăng ký, không phải mật khẩu của người dùng. Password/đăng nhập user ở OP, còn WebFlux giữ configuration client của mình. Không bỏ client secret vào HTML hoặc JavaScript của public SPA.

## 13. Những lỗi triển khai phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Cách phân tích/sửa |
| --- | --- | --- |
| Click login nhưng không tới provider | `registrationId` sai, chưa có `ReactiveClientRegistrationRepository`, URL initiate sai | Kiểm `/oauth2/authorization/google`, registration và chain matcher |
| Provider báo `redirect_uri_mismatch` | Base URL/URI khác giá trị đã đăng ký | So scheme, host, port, path **chính xác**, kiểm proxy trusted |
| Callback có code nhưng login thất bại | State/session mất, code hết hạn/đã dùng, client credentials sai, token endpoint/ID Token validation lỗi | Giữ cookie, so correlation và log metadata an toàn |
| Browser quay vòng login liên tục | WebSession cookie không được giữ, SameSite/Secure/domain/path không phù hợp | DevTools xem Set-Cookie/request Cookie, proxy và session store |
| Login thành công nhưng API Bearer endpoint nhận 401 | `OAuth2AuthenticationToken` của website không phải Bearer access token inbound | Tách role RP và Resource Server; client outbound dùng authorized client |
| User OIDC login rồi admin vẫn 403 | Thiếu quyền/mapper `ROLE_ADMIN` | Đây có thể là đúng; kiểm policy và nguồn role tin cậy |
| `OidcUser` null sau OAuth2 provider khác | Provider không hỗ trợ OIDC, không có scope `openid` | Dùng `OAuth2User` cho provider OAuth-only hoặc provider OIDC có scope phù hợp |
| `@AuthenticationPrincipal` lấy name bất ngờ | UserInfo/ID Token `sub`/username mapping khác nhau | Dùng issuer+sub ổn định; kiểm claim mapping |
| Token refresh không hoạt động | OP không cấp refresh, token store thiếu refresh token, config authorized client manager sai | Kiểm scopes/grant/policy, đừng log refresh token |
| Có login thành công nhưng request POST 403 | CSRF thiếu/sai, không phải chắc chắn thiếu role | Kiểm WebFlux CSRF token/session và request method |
| Logout RP nhưng đăng nhập lại không hỏi password | OP SSO session vẫn sống | Đánh giá RP-Initiated/Back-Channel Logout, không kết luận local logout sai |
| `WebClient` gửi token tới host không mong muốn | Dùng default authorized client trên WebClient chia sẻ | Chỉ định `oauth2AuthorizedClient` theo request và host allowlist |
| Các callback qua gateway có HTTP/hostname sai | Forwarded headers/ingress config không đúng | Chỉ trust proxy, cấu hình base URL và public TLS |
| Nhiều provider trùng email gây lẫn user | Dùng email thay khóa issuer+sub | Kiểm account linking, issuer/subject và email_verified theo policy |

### 13.1. Không dùng các API Servlet khi bài là WebFlux

| Servlet MVC | WebFlux reactive |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| `OidcClientInitiatedLogoutSuccessHandler` | `OidcClientInitiatedServerLogoutSuccessHandler` |
| `SecurityContextHolder` thread-based | `ReactiveSecurityContextHolder` Reactor Context |

Tên giống nhau không có nghĩa có thể copy code 1:1. Đặt dependency `spring-boot-starter-webflux` và import packages đúng stack, tránh trộn Servlet login filter với reactive app.

## 14. Checklist kiến trúc OIDC RP trước production

1. Xác định app là OAuth2 Client/OIDC RP; ghi rõ provider/AS và các Resource Servers mà client cần gọi.
2. Chỉ tin provider issuer đã phê duyệt; dùng `ClientRegistration` và OIDC Discovery/JWKS/HTTPS đúng chuẩn.
3. Đăng ký exact redirect URI; kiểm proxy và các forwarded headers với trust boundary rõ.
4. Dùng Authorization Code flow; bật/kiểm state, nonce, PKCE theo client type/provider chính sách.
5. Bảo vệ client secret/private key ở backend, không đưa vào frontend/repository/log.
6. Xác minh ID Token chữ ký, issuer, audience, expiry, nonce theo OIDC; không tự decode Base64 rồi tin claims.
7. Phân biệt `id_token` (login RP), `access_token` (Resource Server), `refresh_token` (refresh tại AS), `SESSION` (RP local auth).
8. Lưu WebSession/SecurityContext và authorized clients theo thiết kế an toàn cho hệ nhiều instance, có timeout/rotation/revocation policy.
9. Không tự gửi token ra browser/API không đúng audience; dùng `ServerOAuth2AuthorizedClientExchangeFilterFunction` có chọn đúng authorized client.
10. Đặt authorization/role/tenant/ownership ở service; OIDC login thành công không đồng nghĩa admin.
11. Giữ CSRF trên mutations của browser cookie-auth; thêm CSP, cookie hardening, session fixation, XSS defense.
12. Xác định local logout khác OP logout và token revocation, tùy yêu cầu chọn RP-initiated/back-channel/token revoke.
13. Test in-memory với `mockOidcLogin` **và** integration thật với OP sandbox: state, PKCE, code exchange, ID Token claims, session, logout.
14. Giám sát lỗi redirect, state mismatch, token exchange và timeout bằng correlation ID nhưng **không log credential**.
15. Khi nâng Spring Security/Boot, đối chiếu endpoint defaults, callback, user service, cookie và authorized-client persistence rồi chạy regression tests.

## 15. Câu hỏi tự đánh giá

**1.** Khi Spring WebFlux sử dụng `oauth2Login()` để “Login with Google”, nó là Authorization Server không?  
**Không.** Nó là **OAuth2 Client và OIDC RP**; Google/OP thực hiện xác thực người dùng và phát token.

**2.** Vì sao phải khai báo `scope=openid`?  
Scope này đưa flow vào **OpenID Connect**, cho phép dùng ID Token và `OidcUser` theo OIDC; nếu provider không OIDC thì không thể tự tạo hành vi OIDC bằng cách đổi tên scope.

**3.** Authorization code được xử lý ở đâu?  
Browser mang code về callback `/login/oauth2/code/{registrationId}`; Spring Security ở **backend** kiểm state và trao đổi code tại token endpoint. Controller ứng dụng không cần tự gọi endpoint này.

**4.** `id_token` và `access_token` có khác nhau không?  
**Có.** ID Token dành cho RP xác minh login; access token dành cho Resource Server bảo vệ API. Không dùng ID Token thay access token.

**5.** User login OIDC thành công rồi `GET /oidc/admin` trả 403. Đây có phải lỗi OAuth2 Login không?  
**Không nhất thiết.** Authentication thành công nhưng role ADMIN chưa được cấp/mapping; đây là authorization theo nghiệp vụ.

**6.** `OAuth2AuthenticationToken` có giống `JwtAuthenticationToken` không?  
**Không.** Một loại thể hiện login OAuth2/OIDC của web app; loại kia thường dùng khi Resource Server xác thực inbound JWT Bearer.

**7.** Khi WebFlux gọi upstream API thay người dùng, token nên được đính ở đâu?  
Trong **outbound WebClient Authorization: Bearer** thông qua authorized client được chọn và đúng resource/audience/scope; không tự xuất token ra browser profile.

**8.** Local logout có tự đóng SSO tại OP và thu hồi mọi access token không?  
**Không.** Cần chọn thêm OIDC RP-Initiated/Back-Channel Logout và/hoặc revocation policy khi có yêu cầu.

**9.** Vì sao một post-login website vẫn cần CSRF token khi POST?  
Browser xác thực website bằng session cookie tự gửi. OIDC login không loại bỏ rủi ro CSRF của browser mutations.

**10.** `mockOidcLogin()` đã chứng minh ID Token từ OP được verify thật chưa?  
**Chưa.** Nó tạo principal giả trong test harness để kiểm controller/security rules. Cần integration với OP thật/mock OP đúng giao thức để test code exchange và validation.

### Tài liệu chính thức

- Spring Security 6.5, *OAuth2 WebFlux Overview*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security 6.5, *OAuth2 Login Core Configuration*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/core.html
- Spring Security 6.5, *OAuth2 Login Advanced Configuration*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/advanced.html
- Spring Security, *Reactive OAuth2 Client / Authorized Client Features*: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html
- Spring Security, *Testing OAuth 2.0 in WebFlux*: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security, *OIDC Logout for Reactive*: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Authorization Code Grant, RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- Proof Key for Code Exchange, RFC 7636: https://www.rfc-editor.org/rfc/rfc7636
- OAuth 2.0 Security Best Current Practice, RFC 9700: https://www.rfc-editor.org/rfc/rfc9700

**Tóm lại:** WebFlux có `oauth2Login()` là **OAuth2 Client và OIDC RP**: chuyển hướng browser tới OP, nhận callback code, đổi token và xác minh danh tính, rồi giữ `Authentication` cho phiên website. Nó **không tự phát token hay xác thực password của OP**. Tách ID Token, access token, refresh token và session; dùng `oauth2Client` khi gọi Resource Server, `oauth2ResourceServer` khi API tự nhận Bearer; luôn kiểm role, CSRF, session/logout và provider trust boundary.
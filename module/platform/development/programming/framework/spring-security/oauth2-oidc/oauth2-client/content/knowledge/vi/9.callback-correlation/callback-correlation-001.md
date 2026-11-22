# 9.1. AuthorizationRequestRepository và việc lưu request ban đầu

## 1. Vì sao phải lưu authorization request trước khi redirect?

Trong **Spring Security OAuth 2.0 OIDC Client** chạy trên Servlet stack, quá trình đăng nhập bằng **Authorization Code** không kết thúc trong một HTTP request. Ứng dụng nhận yêu cầu bắt đầu đăng nhập, chuyển browser sang Authorization Server/Identity Provider (IdP), rồi một lúc sau mới nhận callback trở về. Hai lần browser gọi ứng dụng có thể cách nhau nhiều giây, thậm chí nhiều phút.

Giả sử người dùng đang ở `https://portal.example.com/orders` và chọn đăng nhập bằng nhà cung cấp có `registrationId=company`. Ứng dụng tạo một `OAuth2AuthorizationRequest` rồi redirect browser đến IdP. Khi browser quay lại, Spring Security cần biết:

- Callback thuộc **lần đăng nhập nào** và client registration nào?
- Giá trị `state` trả về có đúng giá trị đã phát hành không?
- `redirect_uri`, scope và tham số ban đầu là gì?
- Nếu sử dụng **PKCE**, `code_verifier` bí mật được giữ ở đâu để đổi authorization code?
- Callback này đã được xử lý lần nào chưa, hay đang bị phát lại?

Đó là vai trò của **`AuthorizationRequestRepository<OAuth2AuthorizationRequest>`**: lưu trạng thái của **yêu cầu ủy quyền ban đầu** ở phía client trước khi rời ứng dụng, rồi tìm và tiêu thụ trạng thái ấy khi callback đến.

**Không lưu request ban đầu** thì chỉ nhìn vào `?code=...&state=...` từ browser thường không đủ để liên kết nó với một giao dịch hợp lệ. Chỉ có authorization code cũng không đủ để khôi phục an toàn PKCE verifier, registration và ngữ cảnh ban đầu.

> **Phạm vi:** Bài này nói về repository của **authorization request** trong Spring Security **Servlet OAuth2/OIDC Login**. Nó khác repository lưu Access Token sau khi cấp quyền và khác `RequestCache` lưu URL người dùng muốn truy cập trước khi đăng nhập.

## 2. Một lượt đăng nhập có hai chặng và một điểm nối

### 2.1. Chặng đi: tạo, lưu, rồi chuyển browser

Người dùng mở URL bắt đầu login:

~~~http
GET /oauth2/authorization/company HTTP/1.1
Host: portal.example.com
~~~

Spring Security chọn `ClientRegistration` tên `company`, dựng authorization request với `response_type=code`, `client_id`, `scope`, `redirect_uri`, `state` và các tham số mở rộng như PKCE/nonce khi được sử dụng.

Trước khi trả HTTP 302, **repository lưu request**:

~~~text
Browser -> Spring Security
              |
              v
       OAuth2AuthorizationRequest
              |
              v
       AuthorizationRequestRepository.save(...)
              |
              v
HTTP 302 Location: https://id.example.com/authorize?response_type=code&...
~~~

Với repository mặc định, thông tin này nằm trong **HTTP session phía server**. Browser thường chỉ giữ một session cookie dùng tham chiếu đến session đó, chứ không nhận nguyên đối tượng `OAuth2AuthorizationRequest`.

### 2.2. Chặng về: đối chiếu và tiêu thụ

Sau khi người dùng đăng nhập và chấp thuận quyền, IdP đưa browser về:

~~~http
GET /login/oauth2/code/company?code=AUTHORIZATION_CODE&state=STATE_VALUE HTTP/1.1
Host: portal.example.com
Cookie: JSESSIONID=EXAMPLE_SESSION_ID
~~~

Spring Security lấy thông tin request ban đầu bằng repository, đối chiếu `state` và tiếp tục đổi authorization code lấy token. Trong quá trình xử lý callback, request đã lưu cần được **loại bỏ/tiêu thụ** theo ngữ nghĩa của repository để hạn chế tái sử dụng.

~~~mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant F as OAuth2AuthorizationRequestRedirectFilter
    participant R as AuthorizationRequestRepository
    participant A as Authorization Server / OIDC Provider
    participant L as OAuth2LoginAuthenticationFilter
    B->>F: GET /oauth2/authorization/company
    F->>F: Resolve ClientRegistration, tạo request/state/PKCE
    F->>R: saveAuthorizationRequest(authRequest,...)
    R-->>F: Đã lưu request theo ngữ cảnh browser
    F-->>B: 302 đến authorization endpoint
    B->>A: Đăng nhập và consent
    A-->>B: 302 callback?code=...&state=...
    B->>L: GET /login/oauth2/code/company?code=...&state=...
    L->>R: removeAuthorizationRequest(request,response)
    R-->>L: Authorization request phù hợp state, hoặc null
    alt Request hợp lệ
        L->>A: Đổi code tại token endpoint, dùng PKCE nếu có
        A-->>L: Access Token (+ ID Token nếu OIDC)
        L-->>B: Đăng nhập thành công / thiết lập session
    else Không có request tương ứng
        L-->>B: Lỗi xác thực, không cấp login mới
    end
~~~

Nếu người dùng **từ chối consent**, provider có thể redirect về callback kèm `error=access_denied` và `state`. Spring Security vẫn phải xử lý response trong ngữ cảnh authorization request đã phát ra; callback lỗi không phải lý do để bỏ qua correlation.

## 3. Chính xác là lưu những thông tin gì?

`OAuth2AuthorizationRequest` của Spring Security mô tả giao dịch **trước khi có authorization code**. Nó có các trường/cấu trúc như:

| Thuộc tính của authorization request | Vai trò | Có cần khôi phục ở callback? |
| --- | --- | --- |
| `authorizationUri` | Authorization endpoint của provider | Xác định ngữ cảnh yêu cầu ban đầu |
| `responseType` | Thường là `code` với Authorization Code flow | Kiểm tra cấu trúc yêu cầu |
| `clientId` | Client đã được đăng ký với provider | Liên kết callback với đúng client |
| `redirectUri` | Callback URI của client đã sử dụng khi xin code | Được dùng lại khi đổi code nếu giao thức yêu cầu |
| `scopes` | Quyền mà client đã yêu cầu | Cung cấp ngữ cảnh scope/grant |
| `state` | Giá trị ngẫu nhiên dùng ghép yêu cầu và phản hồi | **Bắt buộc đối chiếu** |
| `additionalParameters` | Tham số gửi đến authorization endpoint như `code_challenge`, `nonce` khi áp dụng | Phục vụ luồng đã khởi tạo |
| `attributes` | Thuộc tính nội bộ để framework tiếp tục xử lý | Có thể chứa registration ID, dữ liệu PKCE hoặc thông tin hỗ trợ khác |
| `authorizationRequestUri` | URL authorization đầy đủ đã dựng | Dùng ở chặng redirect |

Một minh họa khái niệm của bản ghi được lưu:

~~~text
OAuth2AuthorizationRequest
  authorizationUri: https://id.example.com/oauth2/authorize
  responseType: code
  clientId: portal-web
  redirectUri: https://portal.example.com/login/oauth2/code/company
  scopes: [openid, profile, email]
  state: randomly-generated-state
  additionalParameters:
    code_challenge: ...
    code_challenge_method: S256
    nonce: ...                 # nếu có trong giao dịch OIDC
  attributes:
    registration_id: company  # framework dùng để xác định client
    code_verifier: ...        # nếu PKCE được bật, cần giữ kín
~~~

Đây là **mô hình diễn giải**, không phải một định dạng lưu trữ chính thức hay khóa thuộc tính ổn định cho mọi phiên bản Spring Security. Các giá trị PKCE, nonce và thuộc tính nội bộ phụ thuộc vào cơ chế request resolver/cấu hình đang dùng.

**AuthorizationRequestRepository lưu request ban đầu, không lưu token được cấp sau login.** Access Token và Refresh Token thuộc `OAuth2AuthorizedClient` cùng hệ thống `OAuth2AuthorizedClientRepository`/`OAuth2AuthorizedClientService`.

### 3.1. State là chìa khóa correlation

`state` là chuỗi khó đoán được sinh cho mỗi giao dịch. Spring Security gửi state trong authorization request, sau đó authorization server trả lại đúng giá trị trong callback theo quy tắc của giao thức.

Ví dụ:

~~~text
Chặng đi:
  /oauth2/authorization/company
  -> save(request với state = "sG1...v8")
  -> IdP nhận state = "sG1...v8"

Chặng về:
  /login/oauth2/code/company?code=...&state=sG1...v8
  -> repository tìm request thuộc giao dịch đó
  -> xác thực tiếp

Nếu callback mang state = "other-state":
  -> không có request khớp -> login thất bại
~~~

`state` là **giá trị ràng buộc giao dịch**, không phải tên người dùng, Access Token, authorization code hay đường dẫn redirect tùy ý. Không dùng nó để chứa dữ liệu nhạy cảm ở dạng đọc được hoặc tin rằng chỉ thấy state trong query là đủ để cấp phiên.

### 3.2. Tại sao cần giữ PKCE verifier?

Với PKCE, client tạo một `code_verifier` ngẫu nhiên và gửi `code_challenge` đã biến đổi vào authorization request:

~~~text
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
~~~

Ở chặng đi, browser/IdP nhận **challenge**, không nên nhận **verifier**. Khi callback đến, client cần verifier gốc để gửi đến token endpoint cùng authorization code.

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=CODE_VALUE&code_verifier=ORIGINAL_VERIFIER
~~~

Nếu custom repository chỉ lưu `state` và bỏ qua những thuộc tính PKCE liên quan thì bước đổi code có thể thất bại với `invalid_grant` hoặc lỗi tương đương. **Phải lưu và khôi phục nguyên vẹn `OAuth2AuthorizationRequest` cần thiết cho luồng**, không tự xây một bản ghi chỉ có ba trường `client_id`, `scope` và `state` rồi hy vọng framework tự phục hồi mọi thứ.

PKCE có thể cần cấu hình tùy theo loại client, phiên bản Spring Security và provider. Đừng giả định mọi client registration tự bật PKCE theo cùng một cách; kiểm tra việc cấu hình nếu sản phẩm yêu cầu PKCE S256.

### 3.3. State, nonce và session cookie không thay thế nhau

| Thành phần | Được sinh/lưu ở đâu? | Mục tiêu chính |
| --- | --- | --- |
| **`state`** | Authorization request; trả qua callback | Gắn response với transaction bắt đầu trước đó, giảm nguy cơ login CSRF và nhầm giao dịch |
| **`code_verifier`** | Giữ kín trong ngữ cảnh client | Chứng minh client đổi code là bên đã khởi tạo PKCE |
| **`nonce`** trong OIDC | Yêu cầu OIDC và giao dịch xác thực | Gắn ID Token với yêu cầu xác thực, giúp chống phát lại |
| **Session cookie** | Browser giữ một tham chiếu session | Giúp backend tìm đúng session đang chứa request, nếu dùng repository mặc định |
| **Authorization code** | Provider trả ở callback thành công | Đổi lấy token tại token endpoint; ngắn hạn, một lần dùng |

`state` không thay thế việc xác minh `nonce` của ID Token. PKCE không thay việc kiểm tra state hoặc ràng buộc callback với phiên. Browser session cookie không chứng minh một callback hợp lệ nếu state không khớp.

## 4. Giao diện AuthorizationRequestRepository của Spring Security Servlet

Trong Spring Security, kiểu tổng quát là:

~~~java
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
~~~

Ba thao tác cốt lõi có thể hình dung theo giao diện:

~~~java
public interface AuthorizationRequestRepository<T extends OAuth2AuthorizationRequest> {

    T loadAuthorizationRequest(HttpServletRequest request);

    void saveAuthorizationRequest(
        T authorizationRequest,
        HttpServletRequest request,
        HttpServletResponse response
    );

    T removeAuthorizationRequest(
        HttpServletRequest request,
        HttpServletResponse response
    );
}
~~~

Đoạn mã diễn giải hợp đồng API; các import Servlet tương ứng trong Spring Security hiện đại là `jakarta.servlet.http.HttpServletRequest` và `HttpServletResponse`.

| Phương thức | Khi được dùng | Trách nhiệm của implementation |
| --- | --- | --- |
| `saveAuthorizationRequest(...)` | Sau khi Spring tạo authorization request, trước redirect | Lưu request cùng thông tin cần để truy xuất đúng browser/giao dịch |
| `loadAuthorizationRequest(request)` | Khi cần đọc lại request từ callback | Trả request hợp lệ tương ứng, hoặc `null` nếu không có |
| `removeAuthorizationRequest(request,response)` | Khi callback phải tiêu thụ request đã lưu | Lấy request phù hợp và xóa/đánh dấu tiêu thụ một cách an toàn |

Mỗi phương thức làm việc với `HttpServletRequest` để nhận cookie, session và các tham số callback. `HttpServletResponse` cho phép implementation cập nhật session/cookie ở lúc lưu hoặc xóa. Repository **không tự thực hiện token exchange** và cũng không tự quyết định người dùng có được truy cập tài nguyên nghiệp vụ không.

### 4.1. Tách trách nhiệm với các thành phần khác

| Thành phần | Tác vụ |
| --- | --- |
| `OAuth2AuthorizationRequestResolver` | **Tạo** authorization request từ registration và request HTTP |
| `OAuth2AuthorizationRequestRedirectFilter` | Khởi động authorization flow, lưu request rồi redirect browser |
| `AuthorizationRequestRepository` | **Lưu / tìm / tiêu thụ** request ban đầu |
| `OAuth2LoginAuthenticationFilter` | Xử lý callback, nối request ban đầu với response, xác thực login |
| OAuth2/OIDC authentication provider | Đổi code, xác minh token/ID Token và tạo kết quả xác thực |
| `OAuth2AuthorizedClientRepository` | Lưu authorized client và token sau khi được cấp quyền |
| `RequestCache` / `SavedRequest` | Nhớ URL trang người dùng muốn truy cập trước khi đăng nhập |
| `SecurityContextRepository` | Lưu/ngữ cảnh Authentication sau khi đăng nhập |

Đặc biệt, **`RequestCache` và `AuthorizationRequestRepository` là hai kho dữ liệu khác nhau**:

- RequestCache có thể giữ URL `/orders` để người dùng đăng nhập xong được quay về trang họ muốn mở.
- AuthorizationRequestRepository giữ authorization request với `state`, redirect URI và dữ liệu PKCE cần để hoàn tất callback.
- Thất lạc SavedRequest có thể khiến ứng dụng không quay về đúng trang đích; thất lạc AuthorizationRequest có thể làm **đăng nhập không hoàn tất**.

## 5. Repository mặc định: HttpSessionOAuth2AuthorizationRequestRepository

Với Spring Security Servlet OAuth2 Login thông thường, implementation mặc định là **`HttpSessionOAuth2AuthorizationRequestRepository`**:

~~~java
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;

HttpSessionOAuth2AuthorizationRequestRepository repository =
    new HttpSessionOAuth2AuthorizationRequestRepository();
~~~

Implementation này sử dụng **`HttpSession`** để lưu authorization request chờ callback và so khớp `state` khi tìm lại. Mô hình dữ liệu:

~~~text
Browser
  Cookie: JSESSIONID=SESSION_ABC
         |
         v
Application / Session store
  SESSION_ABC
    pending OAuth2AuthorizationRequest
      state: sG1...v8
      registration: company
      redirect_uri: ...
      PKCE context: ...
~~~

Tên cookie có thể là `JSESSIONID`, `SESSION` hoặc tên tùy cấu hình Servlet/Spring Session. Các khóa session attribute nội bộ do Spring Security quản lý; **không nên phụ thuộc vào tên attribute riêng tư** để viết logic nghiệp vụ.

### 5.1. Ưu điểm của lưu phía server

- Không phải đưa toàn bộ `OAuth2AuthorizationRequest` và PKCE verifier ra browser.
- Có thể dùng vòng đời session để giới hạn thời gian chờ callback.
- Dữ liệu giữ cùng ngữ cảnh browser đang khởi tạo login.
- Tích hợp với Spring Security mặc định, ít mã tùy biến và được framework xử lý state/callback.

### 5.2. Điều kiện để chặng về tìm được session

Browser phải mang đúng session cookie trở về **cùng ứng dụng và ngữ cảnh** đã lưu request. Những vấn đề sau dễ làm session mất:

| Hiện tượng | Ảnh hưởng |
| --- | --- |
| Cookie bị chặn, xóa hoặc không gửi khi callback | Backend không tìm thấy session/request ban đầu |
| Session hết hạn trước khi user hoàn tất login | Request chờ callback không còn |
| Reverse proxy làm đổi hostname/scheme/port/cookie path | Browser không gửi đúng cookie hoặc redirect URI không khớp |
| Load balancer đưa callback đến node không có session | Callback không tìm thấy request nếu không có session sharing/sticky routing |
| Người dùng mở callback ở browser khác hoặc chế độ private khác | Không có cùng session nên không khôi phục được request |
| Một lần login mới thay thế trạng thái chờ trước đó | Callback cũ có thể không còn khớp; tùy repository và cơ chế lưu |

Đây là lý do callback có `state` hợp lệ về mặt chuỗi nhưng không tìm được request trên server vẫn phải thất bại; cần cả **state đúng và ngữ cảnh lưu trữ đúng**.

## 6. Cấu hình repository trong Spring Security Servlet

### 6.1. Cấu hình OAuth2/OIDC Client cơ bản

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-provider:
            issuer-uri: https://id.example.com/realms/company
~~~

Khai báo trên minh họa một OIDC provider có discovery metadata. Thay issuer, client ID, secret bằng cấu hình thực tế; client secret phải được lưu an toàn. Redirect URI của client phải được đăng ký chính xác tại provider.

### 6.2. Dùng repository mặc định một cách tường minh

Nếu ứng dụng không có yêu cầu lưu trữ đặc biệt, Spring Security đã cung cấp repository dựa trên session. Có thể cấu hình tường minh để nhìn rõ nơi kết nối:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuth2LoginSecurityConfig {

    @Bean
    AuthorizationRequestRepository<OAuth2AuthorizationRequest>
            authorizationRequestRepository() {
        return new HttpSessionOAuth2AuthorizationRequestRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationRequestRepository<OAuth2AuthorizationRequest> repository)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestRepository(repository)))
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Điểm cấu hình chính:

~~~java
.oauth2Login(oauth2 -> oauth2
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestRepository(repository)))
~~~

Đây là DSL Servlet của Spring Security dùng `HttpSecurity` và `SecurityFilterChain`, không phải `ServerHttpSecurity` trong WebFlux. Cấu hình repository qua DSL giúp các thành phần tham gia flow OAuth2 Login phối hợp với cùng cơ chế lưu/đọc authorization request.

Nếu không tùy biến, bạn có thể bỏ bean repository và đoạn `authorizationRequestRepository(repository)`; Spring Security vẫn dùng cơ chế mặc định của OAuth2 Login. **Không bắt buộc tự định nghĩa repository chỉ để bật login OIDC.**

### 6.3. Điểm bắt đầu và điểm callback mặc định

| URL | Chức năng |
| --- | --- |
| `/oauth2/authorization/company` | Bắt đầu authorization flow cho registration `company` |
| Authorization URI của IdP | Browser đăng nhập/consent tại provider |
| `/login/oauth2/code/company` | Callback mặc định để Spring Security xử lý code hoặc OAuth2 error |

Nếu muốn thay URL bắt đầu hoặc callback, cần đồng bộ `authorizationEndpoint().baseUri(...)`, `redirectionEndpoint().baseUri(...)`, cấu hình `redirect-uri` của registration và URI được phép tại IdP. Đổi một phía có thể làm callback không đến filter hoặc provider từ chối `redirect_uri`.

**Không tạo controller tự xử lý `/login/oauth2/code/company`** chỉ để đọc `code` và `state` nếu đang dùng `oauth2Login()` chuẩn. Việc này dễ làm trùng route hoặc bỏ qua các kiểm tra bảo mật do Spring Security quản lý.

## 7. Những điều xảy ra khi callback không tìm thấy request ban đầu

### 7.1. Lỗi “authorization request not found”

Nếu callback đến nhưng repository không khôi phục được request, Spring Security có thể báo lỗi tương tự:

~~~text
OAuth2AuthenticationException:
  [authorization_request_not_found]
~~~

Tên lỗi và thông điệp cụ thể có thể thay đổi theo version hoặc cách exception được bọc. Ý nghĩa là **không có authorization request phù hợp với callback hiện tại**.

Những nguyên nhân phổ biến:

1. **Session cookie không trở lại** sau khi browser chuyển sang IdP.
2. **Session expired** do người dùng mất nhiều thời gian ở màn hình consent.
3. **State mismatch**, chẳng hạn callback bị sửa đổi, đến từ luồng khác hoặc bị phát lại.
4. **Multi-node không chia sẻ session**: chặng đi được lưu ở node A, callback được gửi đến node B.
5. **Nhiều tab/luồng đăng nhập đồng thời**: cách lưu hiện tại không giữ đủ các request chờ để xử lý độc lập.
6. **Repository tùy chỉnh không nhất quán**: chặng đi lưu bằng key/cookie khác chặng về, hoặc không khôi phục đầy đủ attributes.
7. **Domain, cookie path, SameSite hoặc reverse proxy không phù hợp** với redirect/callback.

Đừng “sửa” lỗi này bằng cách chấp nhận callback không có request ban đầu hoặc bỏ kiểm tra state. Việc đó làm mất liên kết bảo mật giữa yêu cầu khởi tạo và response.

### 7.2. Bảng chẩn đoán theo dấu hiệu

| Triệu chứng | Khả năng cần xem | Hướng xử lý |
| --- | --- | --- |
| Login trên localhost ổn, sau deploy lỗi callback | HTTPS/proxy/cookie/hostname khác môi trường local | Kiểm tra public base URL, trusted forwarded headers, cookie attributes và redirect URI |
| Browser ở chế độ ẩn danh không hoàn tất nhưng browser thường được | Cookie bị giới hạn hoặc session không tồn tại/không được gửi | Kiểm tra browser storage policy và callback URL thực tế |
| Một tab đăng nhập được, hai tab thỉnh thoảng lỗi | Nhiều authorization request cùng session tác động lẫn nhau | Xem cách repository hỗ trợ các request đang chờ; cân nhắc giải pháp quản lý nhiều state |
| Lỗi chỉ xuất hiện trên nhiều instance | Session nằm cục bộ trong một node | Dùng shared session store hoặc kiến trúc routing/session phù hợp |
| Lỗi sau khi người dùng ở IdP quá lâu | Session và request đã hết hạn | Điều chỉnh thời gian phù hợp; cung cấp cách thử lại có chủ đích |
| Callback lỗi `invalid_grant` sau khi đã tìm request | Authorization code hết hạn/đã dùng, redirect URI hoặc PKCE sai | Kiểm tra token exchange; không quy mọi lỗi về repository |
| Provider trả `error=access_denied` | Người dùng hoặc chính sách từ chối quyền | Xử lý login failure/UX, vẫn giữ correlation của response |
| Callback bị gửi hai lần | Request đã bị tiêu thụ hoặc code đã dùng một lần | Lần sau phải thất bại; không cho phép reuse |

### 7.3. `state` có tác dụng gì với callback lỗi?

Authorization server có thể trả:

~~~text
/login/oauth2/code/company?error=access_denied&state=ORIGINAL_STATE
~~~

Ứng dụng cần diễn giải rằng giao dịch **không được cấp quyền**, nhưng không được tin toàn bộ query chỉ vì có chuỗi `access_denied`. Thông tin callback đi qua browser và phải được đặt trong ngữ cảnh authentication request đã phát hành.

Một `AuthenticationFailureHandler` có thể hiển thị trang giải thích sự cố, nhưng **không thay thế AuthorizationRequestRepository hoặc cơ chế so khớp state**. Nếu request ban đầu không tồn tại, handler không được tự tạo principal hay authorized client mới.

## 8. Session cookie, SameSite và callback từ IdP

### 8.1. Vì sao cookie lại quan trọng?

HTTP session phía server thường được truy cập bằng session ID nằm trong cookie của browser. Khi browser đi đến IdP rồi quay lại `portal.example.com`, cookie phải được gửi để repository nhìn thấy đúng dữ liệu đã lưu.

Một cookie session minh họa:

~~~http
Set-Cookie: JSESSIONID=OPAQUE_SESSION_ID; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

- **`HttpOnly`** giúp JavaScript phía browser không đọc được cookie qua `document.cookie`.
- **`Secure`** yêu cầu cookie được gửi qua HTTPS (với những ngoại lệ/hành vi phát triển local tùy trình duyệt).
- **`SameSite=Lax`** thường phù hợp cho callback **top-level GET** từ IdP sang client, nhưng cần kiểm tra đúng kiểu response.
- **`Path` và `Domain`** quyết định cookie được gửi cho URL nào.

Khi callback dùng **`response_mode=form_post`** hoặc các luồng POST cross-site, chính sách SameSite có thể cần khác với callback GET thông thường. Không đổi cookie sang `SameSite=None` bừa bãi; nếu thật sự cần cross-site cookie, phải cân nhắc `Secure`, CSRF và chính sách trình duyệt/provider. Chọn cấu hình cookie dựa trên **response mode thực tế** và kiến trúc sản phẩm.

### 8.2. Reverse proxy và domain công khai

Nếu browser nhìn thấy `https://portal.example.com` nhưng backend thực sự chạy `http://internal-app:8080` sau reverse proxy, cần cấu hình trusted proxy/forwarded headers và public base URL chính xác.

Nếu Spring tạo `redirect_uri=http://internal-app:8080/login/oauth2/code/company`, provider có thể từ chối callback. Nếu cookie được phát hành với `Domain` hoặc `Path` sai, callback không tìm thấy session. Đây là hai lỗi khác nhau nhưng thường cùng xuất hiện sau khi deploy.

Đảm bảo:

- Provider đăng ký chính xác HTTPS redirect URI công khai.
- Ứng dụng chỉ tin forwarded headers từ reverse proxy do tổ chức quản lý.
- Cookie session có domain, path, Secure, SameSite phù hợp.
- Callback đến đúng instance/session store có trạng thái chờ.

## 9. Lưu session khi ứng dụng có nhiều instance

`HttpSessionOAuth2AuthorizationRequestRepository` lưu dữ liệu vào `HttpSession`. Với một instance Spring Boot, HTTP session có thể lưu tại memory của Servlet container. Khi chạy nhiều instance sau load balancer, có hai hướng:

| Cách triển khai | Cơ chế | Đánh đổi |
| --- | --- | --- |
| Sticky session | Browser thường được đưa về cùng instance | Đơn giản nhưng phụ thuộc routing, kém linh hoạt khi node lỗi hoặc rolling deploy |
| Shared/distributed session | Nhiều instance đọc chung session store như Redis qua Spring Session | Phù hợp scale-out; cần vận hành Redis, bảo mật kết nối, TTL và serialization |

Một lựa chọn trong ứng dụng Spring Boot Servlet là **Spring Session** kết hợp Redis. Khi session được quản lý tập trung, repository mặc định vẫn thao tác với `HttpSession`, còn Spring Session chịu trách nhiệm ánh xạ session vào kho dùng chung.

Ví dụ dependency Gradle theo bộ Spring Boot được quản lý phiên bản:

~~~groovy
dependencies {
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Ví dụ cấu hình kết nối và session timeout cho môi trường test:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
server:
  servlet:
    session:
      timeout: 15m
~~~

Đây là ví dụ ý tưởng triển khai, không phải cấu hình production đầy đủ. Tùy Spring Boot/Spring Session version, có thể cần starter/config khác, xác thực Redis, TLS, namespace session, serialization và secret store. Không hard-code mật khẩu Redis trong repository.

### 9.1. Đồng bộ thời hạn lưu trữ

Khi một authorization request đã hết hạn sử dụng, phải từ chối callback đến muộn. HTTP session timeout, thời gian sống authorization code tại IdP và TTL lưu request tùy chỉnh nên có quan hệ hợp lý với trải nghiệm đăng nhập, nhưng **không cần kéo dài session vô hạn** chỉ để không mất state.

Nếu lưu request bằng một kho ngoài session, cần có TTL riêng và cơ chế xóa khi đã tiêu thụ, nhằm tránh dữ liệu PKCE và trạng thái chờ tồn tại lâu hơn cần thiết.

### 9.2. Tính tương thích khi serialize session

Nếu dùng distributed session, thư viện lưu trữ có thể serialize/deserialize session attributes. Repository tùy chỉnh phải bảo đảm các kiểu dữ liệu lưu trong session tương thích với serialization của hệ thống đã chọn. Không đưa object HTTP request/response, socket hay bean application không thể serialize vào attributes của `OAuth2AuthorizationRequest`.

Khi deploy nhiều version song song, thay đổi cách lưu object trong session có thể ảnh hưởng khả năng đọc state giữa các instance. Đây là một phần của kiến trúc session migration, không giải quyết bằng cách bỏ state verification.

## 10. Nhiều tab, nhiều provider và nhiều yêu cầu đang chờ

Người dùng có thể mở hai tab:

~~~text
Tab A:
  /oauth2/authorization/company
  state = A123

Tab B:
  /oauth2/authorization/partner
  state = B456

Sau đó callback đến theo thứ tự:
  /login/oauth2/code/company?state=A123&code=...
  /login/oauth2/code/partner?state=B456&code=...
~~~

Một implementation repository phải quyết định có cho phép **nhiều authorization request chưa hoàn tất trong cùng session** hay không. Với cấu trúc chỉ có một request chờ, yêu cầu B có thể thay thế A, khiến callback A không tìm thấy state. Việc xử lý cụ thể tùy phiên bản repository/cách tùy biến; **không mặc định rằng mọi session repository hỗ trợ nhiều tab độc lập**.

Nếu sản phẩm cần login/link account từ nhiều tab đồng thời, có thể thiết kế repository lưu **nhiều request được khóa bởi state** cùng ràng buộc session, giới hạn số request chờ và có TTL. Khi callback đến, implementation phải tìm theo đúng state, **tiêu thụ nguyên tử đúng request** và giữ các request còn lại.

Ngược lại, nếu sản phẩm chỉ cho phép một giao dịch đăng nhập ở mỗi browser session, có thể chọn hành vi một request chờ nhưng cần hiển thị lỗi an toàn và cách bắt đầu lại khi người dùng điền nhiều tab.

### 10.1. Không được dùng state toàn cục

Một phản ví dụ:

~~~java
// SAI: mọi người dùng chia sẻ một biến, có race condition và rò rỉ giao dịch.
private static OAuth2AuthorizationRequest lastAuthorizationRequest;
~~~

Nếu lưu request kiểu này, user B có thể ghi đè state của user A; callback của hai người khác nhau sẽ tranh chấp cùng object. Tối thiểu phải ràng buộc với **session/browser** và **state**, không lưu trong singleton field không có định danh.

### 10.2. Vì sao dùng state làm key vẫn chưa đủ?

Nếu custom repository lưu trên Redis bằng key dạng `oauth2:state:<state>`, callback có state chưa hẳn đã chứng minh browser là bên khởi tạo login. Một hệ thống an toàn còn cần ràng buộc request với session/browser context ban đầu, chống attacker dùng state của chính họ để tạo login CSRF cho phiên người khác.

Thiết kế tốt cần:

1. State ngẫu nhiên có độ khó đoán cao, sinh riêng từng authorization request.
2. Bản ghi được liên kết với phiên/bối cảnh browser khởi tạo.
3. TTL đủ ngắn và giới hạn số request đang chờ.
4. Tra cứu đúng state **và** đúng phiên/binding, không chỉ so khớp query tự gửi.
5. Xóa/đánh dấu tiêu thụ nguyên tử để callback lặp lại không tái sử dụng.
6. Giữ nguyên các thuộc tính PKCE và OIDC cần thiết.

## 11. Khi nào nên viết AuthorizationRequestRepository riêng?

Repository mặc định dùng session phù hợp đa số ứng dụng web server-side. Custom repository có thể có ích khi:

- Ứng dụng yêu cầu nhiều authorization flow đồng thời trong một browser session.
- Cần lưu trạng thái chờ trong kho bên ngoài với mô hình phân vùng/TTL riêng.
- Có yêu cầu quản lý callback stateless đặc biệt, nhưng vẫn phải bảo đảm ràng buộc giao dịch và PKCE.
- Có yêu cầu migration hoặc liên thông session giữa nhiều hệ thống với thiết kế kiểm soát chặt.

Trước khi tự viết, đánh giá xem **Spring Session + repository mặc định** đã giải quyết nhu cầu scale-out chưa. Tùy biến cơ chế lưu OAuth2 request đòi hỏi hiểu rõ contract, trạng thái callback và bảo mật.

### 11.1. Skeleton của custom repository

Một custom repository cần implement interface:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

public final class CustomAuthorizationRequestRepository
        implements AuthorizationRequestRepository<OAuth2AuthorizationRequest> {

    @Override
    public OAuth2AuthorizationRequest loadAuthorizationRequest(
            HttpServletRequest request) {
        // Tìm đúng bản ghi theo session/binding + state.
        // Không trả request thuộc browser khác.
        throw new UnsupportedOperationException("Cần triển khai cơ chế lưu an toàn");
    }

    @Override
    public void saveAuthorizationRequest(
            OAuth2AuthorizationRequest authorizationRequest,
            HttpServletRequest request,
            HttpServletResponse response) {
        // Lưu toàn bộ request cần cho callback, kèm TTL và session binding.
        // Xử lý trường hợp authorizationRequest == null theo contract.
        throw new UnsupportedOperationException("Cần triển khai cơ chế lưu an toàn");
    }

    @Override
    public OAuth2AuthorizationRequest removeAuthorizationRequest(
            HttpServletRequest request,
            HttpServletResponse response) {
        // Tìm và tiêu thụ đúng bản ghi, chống gọi callback lặp lại.
        throw new UnsupportedOperationException("Cần triển khai cơ chế lưu an toàn");
    }
}
~~~

Đây là **khung API giải thích trách nhiệm**, cố ý chưa phải implementation chạy được. Không sao chép và deploy skeleton này; cần thiết kế đầy đủ session binding, TTL, concurrency, bảo vệ bí mật, khả năng khôi phục PKCE và chiến lược xóa dữ liệu. Với nhu cầu thông thường, dùng repository có sẵn an toàn và đơn giản hơn.

### 11.2. Vì sao cookie-based repository khó hơn tưởng tượng?

Một số hệ thống muốn lưu authorization request trong cookie để giảm nhu cầu session server-side. Nhưng cookie do **browser giữ và gửi trở lại**, có thể bị sửa, chép, phát lại hoặc bị lộ qua cấu hình sai.

Nếu chọn cookie-based repository, phải đánh giá:

| Yêu cầu | Nguy cơ nếu bỏ qua |
| --- | --- |
| Chống sửa đổi nội dung (integrity) | Attacker thay registration, redirect URI hoặc thông tin correlation |
| Bảo mật dữ liệu nhạy cảm (confidentiality) | PKCE verifier/attributes có thể bị lộ nếu chỉ Base64 encode |
| Ràng buộc với browser/transaction | Login CSRF hoặc thay chéo giao dịch |
| Hạn dùng, giới hạn kích thước cookie | Cookie tồn tại lâu, tràn kích thước header hoặc bị cắt |
| `HttpOnly`, `Secure`, `SameSite`, domain/path | Script hoặc request ngoài ý muốn nhận được cookie |
| Rotation và xóa cookie sau callback | Trạng thái cũ có thể bị phát lại |
| Key management khi ký/mã hóa | Khó tương thích giữa node; lộ key ảnh hưởng toàn bộ giao dịch |

**Base64 encode không phải mã hóa hoặc chữ ký bảo vệ dữ liệu.** Không tự triển khai một repository lưu JSON/Java object trong cookie rồi chỉ so state mà không có tính toàn vẹn, bảo mật và replay protection.

Thực tế, một **server-side session store** thường là lựa chọn hợp lý cho ứng dụng Spring MVC có login OIDC.

## 12. Tương tác với FailureHandler và SuccessHandler

`AuthenticationSuccessHandler` và `AuthenticationFailureHandler` quyết định browser sẽ nhận phản hồi gì sau khi quá trình đăng nhập hoàn tất hay thất bại; repository quyết định **ngữ cảnh của callback có hợp lệ để xử lý hay không**.

| Tình huống | AuthorizationRequestRepository | Kết quả phía ứng dụng |
| --- | --- | --- |
| Callback có code, state đúng, token hợp lệ | Khôi phục/tiêu thụ request ban đầu | Có thể tạo Authentication, gọi SuccessHandler |
| Callback `error=access_denied` thuộc yêu cầu hợp lệ | Giao dịch vẫn có ngữ cảnh để xử lý lỗi | Thông báo login/cấp quyền chưa thành công |
| Callback không có request phù hợp | Không thể khôi phục ngữ cảnh | Không tự tạo Authentication; dùng failure path thích hợp |
| Callback lặp lại sau lần thành công | Request đã tiêu thụ, code một lần dùng | Từ chối xử lý lại; không cấp phiên mới từ code cũ |
| Đã đăng nhập nhưng user mở URL cần quyền cao hơn | Không nhất thiết khởi tạo OAuth2 login lại | Chính sách `AccessDeniedHandler`/authorization của app |

Phân biệt với `AccessDeniedHandler`: callback `error=access_denied` của provider là **lỗi OAuth2 authorization/login**, còn HTTP 403 khi người dùng đã đăng nhập nhưng không có quyền xem một tài nguyên là **lỗi authorization của ứng dụng**. Hai trường hợp cần UX và cơ chế xử lý khác nhau.

## 13. Quan sát và chẩn đoán mà không làm lộ state

Khi hỗ trợ vận hành, có thể đo những sự kiện sau dưới dạng **metadata tối thiểu**:

~~~text
oauth2_authorization_started
  registration_id=company
  correlation_id=<internal-safe-id>

oauth2_callback_processed
  registration_id=company
  outcome=success
  correlation_id=<internal-safe-id>

oauth2_callback_failed
  registration_id=company
  reason=authorization_request_not_found
  correlation_id=<internal-safe-id>
~~~

Đây là format minh họa, không phải output mặc định của Spring Security. **Không ghi** `state`, `code`, `code_verifier`, `nonce`, cookie session, ID Token, Access Token, Refresh Token hoặc toàn bộ callback URL vào log/analytics. Nếu dùng correlation ID nội bộ để điều tra, sinh và quản lý nó độc lập với credential giao thức, có TTL và chính sách truy cập phù hợp.

Khi chẩn đoán lỗi `authorization_request_not_found`, nên xem theo chuỗi:

1. Có request đi vào `/oauth2/authorization/{registrationId}` và lưu thành công không?
2. Browser có nhận session cookie lúc chặng đi không?
3. Callback có đến đúng hostname/path và mang cookie của cùng session không?
4. Session có tồn tại trên node xử lý callback, thời hạn còn hợp lệ không?
5. Response có `state` đúng với giao dịch khởi tạo không?
6. Có flow mới, nhiều tab hoặc callback lặp khiến request cũ bị thay/thải không?
7. Có custom repository, cookie attribute hoặc reverse proxy làm lệch hành vi không?

Đây là **quy trình suy luận khi debug runtime**, không phải lý do để bypass bất kỳ bước bảo mật nào. Không dùng cách “nếu không có request thì cứ đổi code thử” vì token endpoint có thể từ chối và ứng dụng còn mất khả năng kiểm tra login CSRF.

## 14. Bài tập tình huống

### Tình huống A: Đăng nhập thành công trên một máy

Browser gọi `/oauth2/authorization/company`. Spring Security lưu authorization request trong session `S1`. IdP trả `code` cùng `state` tương ứng, browser mang cookie của `S1` về. Repository tìm và tiêu thụ đúng request, framework tiếp tục token exchange.

**Điểm học:** callback phải được nối với request ban đầu, không chỉ dựa trên code hoặc hostname provider.

### Tình huống B: Người dùng xóa cookie khi đang ở IdP

Authorization request vẫn nằm trong session cũ trên server nhưng browser không còn tham chiếu đến session ấy. Callback mang `state` đúng nhưng không tìm được request ban đầu.

**Kết quả phù hợp:** login thất bại, ứng dụng cho phép người dùng chủ động bắt đầu lại. Không cố tìm request trên toàn bộ session store chỉ bằng state rồi cấp login.

### Tình huống C: Hai tab cùng khởi tạo login

Tab A và B tạo hai state khác nhau trên một session. Nếu repository chỉ giữ một pending request, callback của tab đến trước có thể không còn bản ghi.

**Cách thiết kế:** khi nghiệp vụ đòi hỏi nhiều flow đồng thời, dùng repository có khả năng lưu nhiều request theo state và session binding, xử lý TTL và single-use. Nếu không hỗ trợ, đưa ra lỗi/UX phù hợp cho flow bị thay thế.

### Tình huống D: Chạy ba instance sau load balancer

Node A lưu request trong memory session, callback đến node C. Node C không có dữ liệu.

**Cách thiết kế:** shared session store như Spring Session Redis hoặc chiến lược session routing được kiểm soát; không lưu authorization request vào biến global hoặc tắt state validation.

### Tình huống E: Callback `state` khác giá trị đã lưu

Browser gửi `state=WRONG_VALUE`, nhưng session có request `state=ORIGINAL_VALUE`.

**Kết quả phù hợp:** repository không trả request cho giao dịch sai, Spring Security không hoàn tất login. Đừng cập nhật state trong session cho “khớp” với callback bên ngoài.

### Tình huống F: PKCE bật nhưng custom repository bỏ attributes

Client chỉ lưu client ID, redirect URI và state. Khi callback đến, Spring Security không khôi phục được verifier gốc.

**Kết quả:** token exchange có thể thất bại. Repository phải giữ nguyên các thuộc tính cần thiết của `OAuth2AuthorizationRequest`, kể cả dữ liệu PKCE được framework lưu nội bộ.

### Tình huống G: Provider trả `error=access_denied`

User từ chối consent hoặc provider không chấp thuận yêu cầu. Browser trở về với error và state, không có code thành công.

**Kết quả phù hợp:** không tạo authorized client/token mới; xử lý lỗi trong ngữ cảnh request ban đầu và hiển thị trang giải thích, tránh redirect lặp vô hạn.

### Tình huống H: OAuth2 login đã thành công, nhưng trang đích không được phục hồi

Framework xác thực hợp lệ và principal đã có, nhưng người dùng bị đưa về trang chủ thay vì URL `/orders` ban đầu.

**Phân tích:** authorization request đã được khôi phục, nên lỗi có thể nằm ở `RequestCache`, `SavedRequest`, success handler hoặc chính sách redirect sau login. Không nhầm nó với lỗi `AuthorizationRequestRepository`.

## 15. Tài liệu tham khảo

- Spring Security — Servlet OAuth 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth 2.0 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — AuthorizationRequestRepository Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/AuthorizationRequestRepository.html
- Spring Security — HttpSessionOAuth2AuthorizationRequestRepository Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/HttpSessionOAuth2AuthorizationRequestRepository.html
- OAuth 2.0 Authorization Framework (RFC 6749): https://www.rfc-editor.org/rfc/rfc6749
- Proof Key for Code Exchange (RFC 7636): https://www.rfc-editor.org/rfc/rfc7636
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html

## 16. Tổng kết luồng lưu request ban đầu

~~~text
GET /oauth2/authorization/company
  -> OAuth2AuthorizationRequestResolver
       tạo OAuth2AuthorizationRequest
       (client, redirect, scopes, state, PKCE context...)
  -> AuthorizationRequestRepository.saveAuthorizationRequest(...)
  -> HTTP 302 sang IdP

Browser đăng nhập / consent tại IdP
  -> GET /login/oauth2/code/company?code=...&state=...
  -> OAuth2LoginAuthenticationFilter
       gọi repository để lấy và tiêu thụ request chờ
       đối chiếu giao dịch/state
       dùng lại PKCE verifier, redirect URI và registration tương ứng
  -> Token endpoint
  -> OIDC validation / OAuth2 login
  -> Session Authentication và OAuth2AuthorizedClient

Nếu không tìm thấy request hoặc state không khớp
  -> fail closed: không tạo login/token mới từ callback.
~~~

**`AuthorizationRequestRepository` là mắt xích correlation giữa chặng đi và chặng về của OAuth2/OIDC Authorization Code flow.** Với ứng dụng Spring MVC thông thường, `HttpSessionOAuth2AuthorizationRequestRepository` là lựa chọn mặc định phù hợp. Khi mở rộng sang nhiều node, nhiều tab hoặc cách lưu khác, cần giữ nguyên các nguyên tắc **ràng buộc session, đối chiếu state, bảo vệ PKCE verifier, giới hạn TTL và tiêu thụ một lần** để không đánh mất bảo đảm an toàn của Spring Security.

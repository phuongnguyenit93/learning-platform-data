# 7.7. SecurityContext, HttpSession và principal sau đăng nhập

## Mục tiêu bài học

Trong ứng dụng Servlet sử dụng **Spring Security OAuth 2.0 Client và OpenID Connect (OIDC) Login**, sau khi OpenID Provider (OP) xác thực người dùng và trả authorization code, Spring Security cần chuyển kết quả giao thức thành **trạng thái đăng nhập của ứng dụng**. Ba khái niệm quan trọng nhất là:

- **`SecurityContext`:** chứa đối tượng `Authentication` của request/ngữ cảnh bảo mật.
- **`HttpSession`:** có thể duy trì trạng thái đăng nhập qua nhiều HTTP request trong ứng dụng web Servlet.
- **Principal:** biểu diễn chủ thể đã được xác thực; với OIDC Login, thường là một `OidcUser` chứa ID token và các claim đã được xử lý.

Sau bài này, bạn có thể giải thích vòng đời của ba thành phần, đọc thông tin người dùng sau OIDC Login, phân biệt phiên ứng dụng với phiên Single Sign-On (SSO) ở OP và tránh nhầm trạng thái đăng nhập với access token dùng gọi API.

## 1. Một lần đăng nhập OIDC và nhiều HTTP request

Giả sử một ứng dụng **Employee Portal** viết bằng Spring Boot có một trang `/profile` yêu cầu đăng nhập. OP của doanh nghiệp quản lý tài khoản nhân viên.

Lần đầu trình duyệt truy cập trang:

1. Spring Security thấy request chưa có người dùng được xác thực.
2. Ứng dụng chuyển trình duyệt sang OP để thực hiện OIDC Authorization Code.
3. Người dùng xác thực tại OP; trình duyệt quay về callback của Spring Security cùng authorization code.
4. Spring Security đổi code lấy token, xác minh kết quả OIDC và tạo đối tượng `Authentication`.
5. Ứng dụng duy trì kết quả xác thực theo cơ chế session để các request tiếp theo nhận biết người dùng đã đăng nhập.

Khi người dùng tải lại `/profile`, **không cần trao đổi authorization code và kiểm tra ID token từ đầu trên mọi request**. Ứng dụng có thể khôi phục trạng thái đăng nhập từ phiên Servlet nếu phiên còn hợp lệ và cấu hình cho phép.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant APP as Spring Boot Servlet App
    participant OP as OpenID Provider
    U->>B: Mở /profile
    B->>APP: GET /profile, chưa có phiên hợp lệ
    APP-->>B: 302 bắt đầu OIDC Login
    B->>OP: Authorization Request
    OP->>U: Xác thực / consent nếu cần
    OP-->>B: Redirect cùng code và state
    B->>APP: GET /login/oauth2/code/corporate
    APP->>OP: Đổi code lấy token
    OP-->>APP: ID token + access token (nếu cấp)
    Note over APP: Tạo Authentication chứa OidcUser
    Note over APP: Lưu SecurityContext theo cấu hình
    APP-->>B: Response và session cookie
    B->>APP: GET /profile, gửi session cookie
    Note over APP: Khôi phục SecurityContext
    APP-->>B: Nội dung /profile theo principal
~~~

Điểm cần phân biệt: **OIDC xác thực người dùng tại OP** và **Spring Security duy trì trạng thái đăng nhập cục bộ tại ứng dụng** là hai công việc liên quan nhưng không đồng nhất.

## 2. Ba lớp trạng thái sau OIDC Login

| Thành phần | Câu hỏi nó trả lời | Tồn tại ở đâu? | Điều không nên nhầm |
|---|---|---|---|
| `Authentication` | Ai đang được Spring Security xác thực, có authority nào? | Bên trong `SecurityContext` | Không phải ID token hay access token |
| `SecurityContext` | Ngữ cảnh bảo mật hiện tại chứa `Authentication` nào? | Thường được gắn với luồng xử lý request; có thể lưu/khôi phục qua repository | Không đồng nghĩa toàn bộ `HttpSession` |
| `HttpSession` | Những trạng thái server nào cần được giữ qua nhiều request của cùng phiên? | Máy chủ Servlet hoặc kho session tích hợp | Không phải phiên đăng nhập tại OP |
| `OidcUser` | Principal OIDC là ai, ID token và claim nào liên quan? | Là principal của `Authentication` sau OIDC Login | Không thay thế cơ chế phân quyền nghiệp vụ |
| `OAuth2AuthorizedClient` | Client đã nhận access token/refresh token nào trong ngữ cảnh cấp quyền? | Kho lưu authorized client riêng | Không phải `SecurityContext` hoặc principal |

Có thể hình dung:

~~~text
HttpSession (nếu dùng session để duy trì đăng nhập)
└── SecurityContext
    └── Authentication
        ├── principal -> OidcUser
        │   ├── OidcIdToken
        │   ├── OidcUserInfo (nếu có)
        │   └── claims / attributes
        ├── authorities
        └── authenticated = true
~~~

Đây là **sơ đồ khái niệm**, không phải mô tả mọi thuộc tính hoặc cấu trúc lưu trữ của phiên. Spring Security sử dụng các abstraction và repository để khôi phục/lưu trạng thái; ứng dụng không nên phụ thuộc trực tiếp vào cấu trúc nội bộ của session.

## 3. `SecurityContext` là gì?

### 3.1. `SecurityContext` chứa `Authentication`

Interface trung tâm là:

~~~java
org.springframework.security.core.context.SecurityContext
~~~

Nó cung cấp việc đọc/ghi `Authentication`:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

Với request đã đăng nhập, `authentication` thường chứa thông tin principal và các authority đã được Spring Security xác lập.

Các phương thức của `Authentication` thường được quan tâm:

| API | Ý nghĩa |
|---|---|
| `getPrincipal()` | Chủ thể được xác thực; với OIDC Login thường là `OidcUser` |
| `getAuthorities()` | Các `GrantedAuthority` được ánh xạ cho principal |
| `getName()` | Tên định danh theo implementation của `Authentication` |
| `isAuthenticated()` | Trạng thái xác thực của đối tượng |
| `getCredentials()` | Dữ liệu chứng thực nếu có; không dùng như nguồn để đọc mật khẩu |
| `getDetails()` | Thông tin bổ sung theo cơ chế xác thực |

**`Authentication.isAuthenticated()` không đồng nghĩa người dùng có quyền truy cập mọi chức năng.** Việc cho phép truy cập còn dựa trên request matcher, authority, role, điều kiện nghiệp vụ và các kiểm tra khác.

### 3.2. Vai trò của `SecurityContextHolder`

`SecurityContextHolder` cho phép mã đang chạy trong request truy cập `SecurityContext` tương ứng.

Trong ứng dụng Servlet thông dụng, `SecurityContextHolder` sử dụng chiến lược gắn context với **thread đang xử lý request** (mặc định là `MODE_THREADLOCAL`).

Hệ quả:

- Controller, service và các thành phần Spring Security trên cùng luồng xử lý có thể lấy authentication hiện tại.
- Khi request kết thúc, framework dọn ngữ cảnh để không vô tình sử dụng Authentication của request trước trên thread được server tái sử dụng.
- **ThreadLocal không tự duy trì đăng nhập giữa hai HTTP request.** Muốn giữ trạng thái phải có repository/session hoặc một cơ chế xác thực lại trên từng request.
- Nếu tự tạo luồng, dùng `@Async` hoặc thực thi công việc ngoài luồng request, **không mặc định context được truyền sang luồng mới**. Cần dùng cơ chế truyền ngữ cảnh được Spring Security hỗ trợ, ví dụ các wrapper `DelegatingSecurityContext...`, khi thực sự cần.

Tránh tự thay đổi `SecurityContextHolder` sang cơ chế chia sẻ toàn cục cho cả ứng dụng web. Làm như vậy có nguy cơ khiến principal của một request được nhìn thấy từ request khác.

### 3.3. `SecurityContext` trong một request có vòng đời ra sao?

Ở mức khái niệm:

~~~mermaid
flowchart TD
    A["HTTP request đến ứng dụng Servlet"] --> B["Spring Security Filter Chain"]
    B --> C["SecurityContextRepository khôi phục context nếu có"]
    C --> D["SecurityContextHolder cho luồng request"]
    D --> E["Authentication / Authorization filters"]
    E --> F["Controller và Service dùng principal"]
    F --> G["Hoàn thành response"]
    G --> H["Lưu context nếu có thay đổi theo cơ chế cấu hình"]
    H --> I["Dọn SecurityContextHolder của request"]
~~~

Chi tiết filter và thời điểm lưu phụ thuộc phiên bản/cấu hình Spring Security. Với Spring Security 6, `SecurityContextHolderFilter` tập trung vào **đọc/thiết lập context**; khi ứng dụng tự thiết lập Authentication theo cơ chế tùy biến, có thể cần **gọi lưu context tường minh** qua `SecurityContextRepository`. Những filter đăng nhập do Spring Security cung cấp, như OAuth2 Login, xử lý việc lưu kết quả xác thực theo luồng của framework.

Trong một số cấu hình hoặc phiên bản cũ hơn, bạn có thể gặp `SecurityContextPersistenceFilter`. Đừng dựa vào giả định “chỉ gọi `SecurityContextHolder.setContext(...)` thì mọi phiên bản sẽ tự lưu session” khi tự cài xác thực.

## 4. `HttpSession` giữ trạng thái đăng nhập như thế nào?

### 4.1. HTTP là giao thức request độc lập

Giả sử browser thực hiện:

~~~http
GET /profile HTTP/1.1
Host: portal.example.com
~~~

Ở mỗi request, server phải biết client đang dùng phiên nào. Servlet container có thể quản lý một `HttpSession` và cấp session identifier cho browser bằng cookie, thường có tên:

~~~http
Set-Cookie: JSESSIONID=<opaque-session-id>; Path=/; HttpOnly; Secure
~~~

Các request tiếp theo gửi cookie:

~~~http
GET /profile HTTP/1.1
Host: portal.example.com
Cookie: JSESSIONID=<opaque-session-id>
~~~

Cookie minh họa ở đây chứa **mã định danh phiên**, không phải `OidcUser` hoặc toàn bộ `SecurityContext`. Session data thường được lưu phía server hoặc kho dữ liệu session được ứng dụng tích hợp.

Trong thực tế, cookie có thể có tên, thuộc tính và cơ chế lưu trữ khác tùy Servlet container, Spring Session và cấu hình triển khai.

### 4.2. Từ `HttpSession` đến `SecurityContextRepository`

Spring Security không buộc controller tự thao tác với `HttpSession` để đọc trạng thái xác thực. Nó sử dụng abstraction:

~~~java
org.springframework.security.web.context.SecurityContextRepository
~~~

Trong cấu hình Servlet có session, implementation như `HttpSessionSecurityContextRepository` có thể lưu một `SecurityContext` vào `HttpSession` để khôi phục sau đó. Khóa session mặc định thường gặp là:

~~~text
SPRING_SECURITY_CONTEXT
~~~

Ở các phiên bản hiện đại, `DelegatingSecurityContextRepository` có thể kết hợp nhiều kho, chẳng hạn `RequestAttributeSecurityContextRepository` và `HttpSessionSecurityContextRepository`, để đáp ứng các tình huống dispatch và lưu theo session.

**Không nên viết business logic đọc thẳng `session.getAttribute("SPRING_SECURITY_CONTEXT")`.** Hãy lấy `Authentication` qua tham số controller, `@AuthenticationPrincipal` hoặc các API Spring Security. Cấu trúc session nội bộ có thể thay đổi theo cấu hình.

### 4.3. Vì sao session lưu được đăng nhập qua nhiều request?

Khi OIDC Login thành công, `Authentication` được tạo và đặt vào `SecurityContext`; trong một ứng dụng web session-based, kết quả được lưu qua `SecurityContextRepository` phù hợp.

Ở request sau:

1. Browser gửi session cookie.
2. Servlet container hoặc kho session tìm `HttpSession` tương ứng.
3. Spring Security khôi phục context, rồi đặt context vào `SecurityContextHolder` cho request đó.
4. Filter authorization thấy request đã có Authentication hợp lệ và cho đi tiếp nếu quyền phù hợp.
5. Controller có thể lấy `OidcUser` mà không cần tự gọi lại OP.

Nếu cookie không được gửi, session hết hạn, bị hủy hoặc kho session không còn dữ liệu, ứng dụng có thể coi request là chưa đăng nhập. Khi đó có thể bắt đầu lại luồng OIDC Login.

### 4.4. Session có được tạo ở tất cả request không?

Không nhất thiết. Chính sách tạo session có thể ảnh hưởng:

| `SessionCreationPolicy` | Hành vi cơ bản |
|---|---|
| `ALWAYS` | Spring Security luôn tạo session |
| `IF_REQUIRED` | Chỉ tạo session khi cần |
| `NEVER` | Spring Security không tự tạo session, nhưng có thể dùng session đã tồn tại |
| `STATELESS` | Spring Security không tạo và không dùng `HttpSession` để lấy `SecurityContext` |

Ứng dụng **Servlet OIDC Login tương tác** thường cần trạng thái qua browser redirect, ví dụ giữ Authorization Request gốc và `state` để xác minh callback, đồng thời lưu phiên sau đăng nhập.

Đặt `SessionCreationPolicy.STATELESS` một cách máy móc lên cùng filter chain xử lý `oauth2Login()` có thể phá vỡ các giả định của luồng đăng nhập mặc định. Nếu muốn một kiến trúc không có session, phải thiết kế rõ cách lưu authorization request, bảo vệ callback và duy trì/xác thực trạng thái phù hợp; không chỉ đổi một enum.

## 5. Điều gì được lưu trong session trước và sau callback?

Trong OIDC Authorization Code có **hai loại trạng thái liên quan nhưng khác nhau**.

### 5.1. Trước khi người dùng đăng nhập thành công

Khi bắt đầu authorization request, Spring Security phải nhớ đủ dữ liệu để đối chiếu callback:

- Registration mà client đang sử dụng.
- Giá trị `state` và dữ liệu authorization request cần thiết.
- `nonce`/PKCE khi tham gia OIDC/Authorization Code phù hợp.
- Có thể cả URL gốc người dùng yêu cầu, để chuyển hướng trở lại sau đăng nhập.

Với cấu hình mặc định phổ biến, `HttpSessionOAuth2AuthorizationRequestRepository` lưu Authorization Request trong `HttpSession` để truy xuất khi callback được gửi về.

Trạng thái này **chưa có nghĩa là người dùng đã được xác thực trong ứng dụng**.

### 5.2. Sau khi callback OIDC thành công

Spring Security đã:

- Đối chiếu state và các điều kiện bảo vệ authorization response.
- Trao đổi authorization code lấy token tại token endpoint.
- Kiểm tra kết quả OIDC theo các quy tắc thích hợp.
- Xây đối tượng principal OIDC và Authentication.
- Lưu Authentication trong SecurityContext, theo cách mà ứng dụng có thể dùng ở request tiếp theo.

Ví dụ minh họa các loại trạng thái:

| Giai đoạn | Trạng thái | Ý nghĩa |
|---|---|---|
| Bắt đầu login | `OAuth2AuthorizationRequest` | Dữ liệu cho luồng chuyển hướng và xác minh callback |
| Nhận callback thành công | `Authentication` với `OidcUser` | Danh tính đã được OP xác thực và Spring Security chấp nhận |
| Sau login | `SecurityContext` | Ngữ cảnh bảo mật được lưu/khôi phục giữa các request |
| Khi cần gọi API | `OAuth2AuthorizedClient` | Token được cấp cho client/principal theo ngữ cảnh |

Không suy luận rằng vì các trạng thái này cùng có thể liên quan đến session nên chúng được lưu trong cùng một attribute hay có cùng vòng đời.

## 6. Principal sau OIDC Login là đối tượng nào?

### 6.1. `OAuth2AuthenticationToken` và `OidcUser`

Khi OIDC Login thành công trong ứng dụng Servlet, `Authentication` thường có kiểu:

~~~java
org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken
~~~

Principal của nó thường là một implementation của:

~~~java
org.springframework.security.oauth2.core.oidc.user.OidcUser
~~~

Ví dụ quan hệ đối tượng:

~~~text
SecurityContext
└── OAuth2AuthenticationToken
    ├── principal: OidcUser
    │   ├── idToken: OidcIdToken
    │   ├── userInfo: OidcUserInfo (nếu có)
    │   └── claims, attributes
    ├── authorities: Collection<GrantedAuthority>
    ├── authorizedClientRegistrationId: corporate
    └── authenticated: true
~~~

`OidcUser` kế thừa các khả năng của `OAuth2User` và cung cấp các phương thức OIDC như:

| Phương thức | Thông tin |
|---|---|
| `getIdToken()` | Đối tượng `OidcIdToken` sau khi được xử lý |
| `getUserInfo()` | Đối tượng `OidcUserInfo` nếu provider và luồng có trả |
| `getClaims()` | Các claim OIDC được Spring Security cung cấp cho principal |
| `getSubject()` | Subject (`sub`) theo định danh OIDC |
| `getIssuer()` hoặc `getIdToken().getIssuer()` | Issuer của ID token, tùy API đang dùng |
| `getEmail()` | Claim email nếu có |
| `getFullName()` | Claim tên nếu có |
| `getAuthorities()` | Authorities đã được ánh xạ cho principal |

Các claim `email`, `name`, `picture` và thông tin hồ sơ khác **có thể không tồn tại** hoặc thay đổi theo provider/scope/chính sách. Không dùng tên hiển thị làm khóa định danh tài khoản.

### 6.2. Định danh ổn định: `iss` kết hợp `sub`

OIDC cung cấp hai claim đặc biệt quan trọng:

- `iss`: issuer phát hành ID token.
- `sub`: định danh của End-User trong phạm vi issuer.

Nếu ứng dụng hỗ trợ nhiều provider, hai người khác nhau có thể có cùng chuỗi `sub` ở hai issuer. Vì vậy, một khóa liên kết tài khoản nội bộ thường dựa trên **cặp `iss` + `sub`**.

Ví dụ:

~~~text
Issuer A: https://id.example.com/realms/employees
Subject:  10042

Issuer B: https://id.example.com/realms/partners
Subject:  10042
~~~

Đây không mặc nhiên là cùng người. Ngược lại, cùng một người có thể có `sub` khác nhau giữa các client khi OP sử dụng pairwise subject identifier.

Dữ liệu đăng nhập OIDC chứng minh danh tính theo OP đã được tin cậy, **không tự động chứng minh người dùng có quyền phê duyệt mọi giao dịch trong Portal**.

### 6.3. Principal OIDC và principal OAuth 2.0 thuần

Không phải mọi OAuth 2.0 Login đều tạo `OidcUser`:

| Tình huống | Principal thường gặp |
|---|---|
| Đăng nhập OIDC với `openid` và ID token hợp lệ | `OidcUser` |
| OAuth 2.0 Login không sử dụng OIDC | `OAuth2User` hoặc implementation tương ứng |
| Form Login do Spring Security quản lý | `UserDetails`, chuỗi username hoặc principal tùy cấu hình |
| JWT Resource Server nhận bearer token | `Jwt`/`JwtAuthenticationToken` theo cơ chế JWT |
| Custom authentication | Principal do AuthenticationProvider của ứng dụng định nghĩa |

Vì vậy, controller nhận `@AuthenticationPrincipal OidcUser` chỉ phù hợp nếu đường dẫn đó được bảo vệ bằng cơ chế OIDC Login hoặc có quy tắc rõ ràng cho những cách đăng nhập khác.

## 7. Đọc principal đúng cách trong Spring MVC

### 7.1. Lấy `OidcUser` bằng `@AuthenticationPrincipal`

Giả sử ứng dụng chỉ cho phép truy cập endpoint `/me` sau khi OIDC Login thành công:

~~~java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    CurrentUserResponse me(
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication) {

        String registrationId =
                authentication instanceof OAuth2AuthenticationToken oauth
                        ? oauth.getAuthorizedClientRegistrationId()
                        : null;

        List<String> authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList();

        return new CurrentUserResponse(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                user.getFullName(),
                registrationId,
                authorities
        );
    }

    record CurrentUserResponse(
            String issuer,
            String subject,
            String displayName,
            String registrationId,
            List<String> authorities) {}
}
~~~

Giải thích:

1. `@AuthenticationPrincipal` lấy principal từ Authentication đang có trong SecurityContext.
2. Với OIDC Login, principal là `OidcUser`, cho phép đọc issuer và subject.
3. Tham số `Authentication` cho phép xem authorities và thông tin đăng nhập.
4. `getAuthorizedClientRegistrationId()` giúp biết cấu hình client nào đã được dùng để đăng nhập.
5. `displayName` có thể `null` nếu OP không cung cấp claim tên.

Endpoint này chỉ trả các thông tin minh họa. Trong hệ thống thật, nên cân nhắc tối thiểu hóa dữ liệu cá nhân trả ra ngoài và không trả nguyên ID token, access token hoặc refresh token cho browser.

**Giả định quan trọng của ví dụ:** `/me` chỉ được truy cập bằng OIDC Login. Nếu hệ thống cho phép đồng thời Form Login, Basic hoặc bearer token trên cùng endpoint, cần xử lý trường hợp principal không phải `OidcUser` thay vì cast mặc định.

### 7.2. Lấy `Authentication` trực tiếp

Spring MVC có thể đưa `Authentication` đang hoạt động vào method parameter:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SecurityStatusController {

    @GetMapping("/who-am-i")
    public String whoAmI(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Với endpoint yêu cầu xác thực, ví dụ minh họa giúp đọc tên principal. **`authentication.getName()` không nhất thiết bằng email**; nó phụ thuộc implementation và thuộc tính tên được cấu hình. Với OIDC, nếu cần khóa định danh bền vững, lấy `iss` + `sub` từ token OIDC đã xác minh.

### 7.3. Lấy `SecurityContext` qua `SecurityContextHolder`

Trong service chạy cùng luồng xử lý request:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public class CurrentAuthenticationLookup {

    public Authentication currentAuthentication() {
        return SecurityContextHolder.getContext().getAuthentication();
    }
}
~~~

Cách này hữu ích ở nơi không có cơ chế inject principal trực tiếp, nhưng cũng tạo sự phụ thuộc vào ngữ cảnh bảo mật hiện thời. Đối với logic nghiệp vụ dễ kiểm thử, truyền user identifier hoặc Authentication một cách tường minh từ lớp web/service thường rõ ràng hơn.

Không giữ một `Authentication` trong biến `static` hay cache dùng chung để tái sử dụng cho các request. Làm vậy có thể làm lộ danh tính và quyền giữa người dùng.

### 7.4. Đọc `HttpSession` khi thật sự cần

Trong Servlet API:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LocalSessionController {

    @GetMapping("/session-present")
    public SessionState sessionState(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        return new SessionState(session != null);
    }

    record SessionState(boolean sessionPresent) {}
}
~~~

`request.getSession(false)` trả `null` nếu không có session hiện hữu; khác với `request.getSession()`, vốn có thể tạo session mới.

Endpoint chỉ dùng để minh họa trạng thái session. **Việc có `HttpSession` không tự chứng minh người dùng đã được xác thực**, vì session có thể tồn tại từ trước login để chứa authorization request, CSRF token, request cache hoặc dữ liệu ứng dụng khác.

Không cần đọc trực tiếp session để xác định quyền truy cập; Spring Security authorization đã xử lý Authentication theo filter chain.

## 8. Cấu hình Servlet OIDC Login và phiên trong Spring Security

### 8.1. Thêm dependency và registration

Với Spring Boot Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Một cấu hình client OIDC minh họa:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-oidc:
            issuer-uri: https://id.example.com/realms/employees
~~~

`corporate` là registration ID dùng trong đường dẫn `/oauth2/authorization/corporate`. `issuer-uri` là định danh OP đáng tin cậy mà Spring sử dụng để lấy provider metadata theo cơ chế discovery phù hợp.

Cấu hình này giả định client đã được đăng ký ở OP; giá trị `client-secret` được nạp từ nguồn bí mật của môi trường, không ghi trực tiếp vào source control.

### 8.2. Bật đăng nhập OIDC và session khi cần

Ví dụ Servlet Security Filter Chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(requests -> requests
                        .requestMatchers("/", "/error", "/assets/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
                .logout(logout -> logout.logoutSuccessUrl("/"))
                .build();
    }
}
~~~

Ý nghĩa:

- `authorizeHttpRequests(...)` yêu cầu Authentication cho các URL được bảo vệ.
- `oauth2Login()` kích hoạt luồng login OAuth 2.0/OIDC và callback tương ứng.
- `SessionCreationPolicy.IF_REQUIRED` cho phép tạo session khi flow cần duy trì trạng thái.
- `logout(...)` dùng cơ chế logout cục bộ của Spring Security; nó không mặc định kết thúc phiên tại OP.

Sau login thành công, ứng dụng thường giữ `SecurityContext` trong một cơ chế persistence dựa trên `HttpSession` để request tiếp theo khôi phục Authentication.

Không cần viết controller xử lý `/login/oauth2/code/corporate` khi đang dùng callback mặc định của Spring Security. Framework có filter chuyên trách cho token exchange, xác minh kết quả login và thiết lập Authentication.

### 8.3. Cấu hình thời hạn và cookie của session

Một ví dụ cấu hình Spring Boot cho môi trường chạy HTTPS:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

Các điểm cần biết:

- `timeout` đặt khoảng bất hoạt của session theo cấu hình Servlet/Spring Boot; không phải `exp` của ID token hay access token.
- `HttpOnly` giúp ngăn JavaScript thông thường đọc session cookie; không tự giải quyết mọi rủi ro XSS hoặc CSRF.
- `Secure` yêu cầu browser chỉ gửi cookie qua HTTPS.
- `SameSite=Lax` có thể phù hợp với nhiều luồng redirect đăng nhập top-level GET, nhưng cần đánh giá các redirect, browser và flow thực tế.
- Nếu có reverse proxy, ứng dụng phải hiểu đúng scheme/host public bằng cấu hình proxy đáng tin cậy.

Ở môi trường local chỉ dùng HTTP, `secure: true` có thể khiến browser không gửi cookie theo cách bạn mong muốn; cần thiết lập theo môi trường, không hạ thấp cấu hình production để né lỗi local.

### 8.4. Bật CSRF protection cho tương tác dựa trên cookie

Khi browser tự động gửi session cookie, những request thay đổi trạng thái có thể bị tấn công CSRF nếu không được bảo vệ. Spring Security cung cấp CSRF protection mặc định cho các phương thức không an toàn trong nhiều cấu hình Servlet.

Điểm cần nhớ:

- Đừng tắt CSRF toàn bộ chỉ vì sử dụng OIDC.
- Luồng authorization có `state` giúp liên kết callback với yêu cầu đã khởi tạo; nó không thay thế mọi CSRF protection cho form/action nghiệp vụ.
- Với form logout theo cơ chế CSRF mặc định, thường phải gửi **POST kèm CSRF token**; không chỉ đặt một liên kết GET `/logout` và mặc định nó sẽ thực hiện logout ngay.

## 9. `OAuth2AuthorizedClient` và token: đừng nhầm với session principal

### 9.1. Ai giữ access token sau đăng nhập?

Trong quá trình Authorization Code, OP có thể trả:

- **ID token**: giúp RP xác thực End-User.
- **Access token**: dùng để truy cập các Resource Server/API được cấp quyền.
- **Refresh token**: có thể được cấp theo grant, scope và chính sách của OP.

Spring Security quản lý thông tin client đã được cấp quyền bằng:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClient
~~~

Đối tượng này liên kết một `ClientRegistration` với principal/ngữ cảnh ủy quyền và access token, kèm refresh token nếu có.

Đây là **trạng thái OAuth authorized client**, khác với `OidcUser` hoặc `SecurityContext`.

### 9.2. Hai kho lưu khác trách nhiệm

| Cơ chế | Dữ liệu chính | Mục đích |
|---|---|---|
| `SecurityContextRepository` | `SecurityContext`, `Authentication` | Khôi phục danh tính/trạng thái đăng nhập |
| `OAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClient` theo ngữ cảnh request/principal | Quản lý authorized client dùng cho request HTTP |
| `OAuth2AuthorizedClientService` | Authorized client theo registration/principal | Lưu, tìm và loại bỏ token theo abstraction service |

Authorized client có thể được lưu trong session hoặc một kho khác tùy cách Spring Security được cấu hình. **Không giả định access token nhất định nằm trong attribute `SPRING_SECURITY_CONTEXT`**. Việc có Authentication trong session cũng không có nghĩa access token còn hiệu lực cho mọi API.

### 9.3. Đọc trạng thái authorized client

Ví dụ endpoint kiểm tra có access token cho registration đã dùng:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OAuthClientStatusController {

    @GetMapping("/authorized-client-status")
    String status(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient client) {

        return "registrationId=" + client.getClientRegistration().getRegistrationId()
                + ", tokenPresent=" + (client.getAccessToken() != null);
    }
}
~~~

Ví dụ này dành cho request có authorized client được lưu và tra cứu thành công. Trong hệ thống thật, nên xử lý trường hợp thiếu authorized client theo cấu hình, tránh trả giá trị token ra API hoặc log.

Muốn gọi API khác, client sử dụng access token phù hợp với **audience/scope** của API; Resource Server vẫn tự xác minh token và phân quyền. Không gửi ID token tới API thay access token.

### 9.4. Mất session và hết hạn token là hai sự kiện khác nhau

Ví dụ một người dùng đã login:

- HttpSession còn 20 phút trước khi hết hạn do không hoạt động.
- ID token có một thời hạn riêng.
- Access token có thể hết hạn sớm hơn session và cần refresh hoặc xin lại theo chính sách.
- OP có thể duy trì SSO lâu hơn session của Portal.

Do đó:

- **Session còn sống** không bảo đảm access token còn dùng được.
- **Access token còn sống** không có nghĩa phiên đăng nhập cục bộ chưa bị logout.
- **ID token hết hạn** không tự động tương đương HttpSession bị hủy ngay lập tức trong mọi cấu hình session-based.
- **Đăng xuất Portal** không nhất thiết thu hồi mọi access token đã phát hành hoặc chấm dứt SSO tại OP.

Cần thiết kế riêng chính sách phiên ứng dụng, vòng đời token, token revocation và OIDC logout khi nghiệp vụ yêu cầu.

## 10. Phân biệt phiên Portal với phiên SSO tại OP

### 10.1. Hai phiên có người quản lý khác nhau

**Phiên Portal** thường là `HttpSession` trên phía ứng dụng, phục vụ việc nhận diện người dùng qua các request đến Portal.

**Phiên OP/SSO** do OpenID Provider quản lý, quyết định browser có phải xác thực lại khi bắt đầu một OIDC Authorization Request mới hay không.

Ví dụ:

~~~text
10:00  Người dùng đăng nhập OP và Portal
10:30  HttpSession tại Portal hết hạn
10:31  Truy cập /profile, Portal khởi động OIDC Login mới
10:31  OP vẫn có phiên SSO, có thể trả kết quả mà không hỏi mật khẩu lại
10:31  Portal tạo phiên đăng nhập mới
~~~

Người dùng có thể thấy trải nghiệm “vẫn đang đăng nhập” nhờ SSO, dù Portal đã tạo **session mới**.

### 10.2. Logout cục bộ

Với Spring Security Servlet, logout tiêu chuẩn thường thực hiện:

1. Hủy/invalidates phiên cục bộ theo cấu hình.
2. Xóa `Authentication` và `SecurityContext`.
3. Dẫn người dùng đến logout success URL.

Tuy nhiên, browser có thể vẫn có phiên SSO hợp lệ tại OP. Khi truy cập lại một trang được bảo vệ, Portal có thể chuyển sang OP và người dùng đăng nhập lại nhanh chóng nhờ SSO.

Muốn kết thúc phiên tại OP, cần sử dụng cơ chế logout OIDC mà nhà cung cấp hỗ trợ, chẳng hạn **RP-Initiated Logout**. Đây là luồng bổ sung cần cấu hình rõ ràng; không nên kỳ vọng chỉ gọi logout local tự động đăng xuất OP và mọi client khác.

### 10.3. Chuyển tài khoản OIDC

Nếu Portal hỗ trợ nhiều tài khoản:

- Không dùng email trong `login_hint` như bằng chứng tài khoản mới.
- Khi quay về từ OP, xác minh ID token và lấy `iss` + `sub` thực tế.
- Thay thế trạng thái đăng nhập cục bộ một cách nhất quán, không giữ dữ liệu request/session nghiệp vụ của tài khoản cũ.
- Không sử dụng lại `OAuth2AuthorizedClient` hoặc access token của principal cũ cho tài khoản mới.
- Có thể yêu cầu OP hiển thị chọn tài khoản bằng `prompt=select_account` nếu provider hỗ trợ; vẫn phải kiểm tra danh tính sau callback.

**Session isolation** đặc biệt quan trọng khi một browser dùng nhiều tài khoản trên cùng Portal.

## 11. Session fixation và bảo vệ session

### 11.1. Session fixation là gì?

Session fixation là tình huống kẻ tấn công tìm cách khiến nạn nhân đăng nhập với một session identifier mà kẻ tấn công đã biết hoặc kiểm soát được.

Sau khi người dùng login thành công, ứng dụng nên thay đổi định danh session hoặc thực hiện cơ chế tương đương để session trước xác thực không bị tái sử dụng với đặc quyền mới.

Spring Security Servlet cung cấp **session fixation protection**; trên Servlet container hỗ trợ, chiến lược mặc định thường sử dụng đổi session ID (`changeSessionId`).

Sơ đồ:

~~~text
Trước đăng nhập:
session ID = abc123     (session có thể lưu authorization request)

Sau đăng nhập thành công:
session ID = xyz789     (định danh phiên thay đổi)
SecurityContext = Authentication đã được xác thực
~~~

Giá trị chỉ là minh họa. Ứng dụng không nên tự phát minh thuật toán thay session ID nếu đang sử dụng Spring Security và Servlet container đúng chuẩn.

### 11.2. Cookie và HTTPS

Bảo vệ session bao gồm:

- Dùng HTTPS cho ứng dụng và callback OIDC.
- Bật các thuộc tính cookie như `HttpOnly` và `Secure` ở production khi phù hợp.
- Đánh giá `SameSite` theo luồng cross-site redirect thực tế.
- Không đưa session ID vào URL, log hoặc response body.
- Đặt thời gian bất hoạt hợp lý; có cơ chế hết hạn/thu hồi khi cần.
- Tránh lưu dữ liệu bí mật không cần thiết vào HttpSession.
- Nếu session được chia sẻ trên nhiều instance, bảo vệ kho session và quyền truy cập giữa các service.

`HttpOnly` không ngăn browser tự gửi cookie trong request, nên ứng dụng session-based vẫn cần cơ chế CSRF đúng cách.

### 11.3. Đăng nhập không đồng nghĩa được phân quyền mọi hành động

Ví dụ portal có:

- `/profile`: nhân viên đăng nhập nào cũng được xem hồ sơ của chính họ.
- `/orders/123/approve`: chỉ người được chỉ định hoặc có authority phù hợp được duyệt đơn.
- `/admin/users`: giới hạn quản trị viên.

Có `OidcUser` hợp lệ và `Authentication.isAuthenticated() == true` chỉ chứng minh trạng thái xác thực. Còn **authorization** phải được kiểm tra bằng Spring Security và quy tắc nghiệp vụ.

Authorities có thể đến từ scope hoặc mapping claim tùy provider và cấu hình. Spring Security **không tự hiểu mọi claim tùy biến từ OP là role nghiệp vụ của ứng dụng**.

## 12. So sánh ứng dụng web session-based với API stateless

Một kiến trúc có thể có đồng thời:

- **Web UI** dùng OIDC Login và `HttpSession`.
- **REST API** nhận `Authorization: Bearer <access_token>` và xác thực theo từng request.

Hai luồng khác nhau ở cách tạo Authentication:

| Đặc điểm | Web OIDC Login (Servlet session-based) | Bearer-token Resource Server (stateless thường gặp) |
|---|---|---|
| Nguồn trạng thái | Session cookie và SecurityContext được khôi phục | Bearer token gửi trong request |
| Bắt đầu xác thực | Browser redirect tới OP | Client/API caller đã có token |
| Principal điển hình | `OidcUser` | `Jwt`/`JwtAuthenticationToken` hoặc principal tương ứng |
| Duy trì đăng nhập | Có thể dùng `HttpSession` | Thường xác thực token mỗi request |
| Client ID và redirect URI | Cần cho OIDC Login | Không phải yêu cầu của việc nhận JWT thuần |
| CSRF | Quan trọng khi browser tự gửi session cookie | Đánh giá theo việc API có dùng credential tự động/cookie không |

Có thể tách hai nhóm endpoint bằng **nhiều `SecurityFilterChain`** nếu dự án vừa phục vụ UI vừa cung cấp API. Mỗi chain cần matcher và cấu hình authentication/session tương ứng; không nên áp `STATELESS` cho toàn bộ ứng dụng nếu web OIDC Login vẫn cần session.

### 12.1. Một cấu hình minh họa tách API và Web

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SeparateChainsSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .oauth2ResourceServer(resource -> resource
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error", "/assets/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
                .build();
    }
}
~~~

Đây là **ví dụ kiến trúc**, yêu cầu thêm `spring-boot-starter-oauth2-resource-server` và cấu hình JWT Resource Server phù hợp nếu muốn chạy phần `/api/**`. API chain chỉ thích hợp để tắt CSRF theo cách minh họa khi API thực sự chỉ dùng bearer token qua header, không dùng cookie hoặc credential tự động của browser.

Web chain giữ CSRF protection tiêu chuẩn; OIDC Login có thể dựa trên session. Trường hợp API cũng được truy cập bằng cookie, phải đánh giá CSRF riêng thay vì sao chép cấu hình `disable()`.

## 13. Sự khác nhau giữa request thread và công việc bất đồng bộ

### 13.1. `SecurityContextHolder` không tự đi theo mọi thread

Ví dụ controller đã có `OidcUser` và khởi chạy tác vụ qua executor:

~~~text
Request thread:
SecurityContextHolder -> Alice

Worker thread:
SecurityContextHolder -> không tự có Alice
~~~

Vì `SecurityContextHolder` mặc định dùng ThreadLocal, việc tự tạo thread hoặc chạy callback trên executor khác **không tự động sao chép context**.

Spring Security có những cơ chế như:

- `DelegatingSecurityContextRunnable`.
- `DelegatingSecurityContextCallable`.
- `DelegatingSecurityContextExecutor`.
- Các tích hợp tương ứng cho tác vụ bất đồng bộ, tùy môi trường.

Nếu cần thực thi thay mặt một người dùng trong background job, phải xác định rõ danh tính và quyền của công việc đó. Đôi khi cách tốt hơn là truyền **user ID và dữ liệu nghiệp vụ cần thiết** vào job thay vì duy trì cả SecurityContext sống lâu sau request.

### 13.2. Không dùng `MODE_INHERITABLETHREADLOCAL` như giải pháp chung

Cơ chế ThreadLocal kế thừa có thể chuyển context sang thread con trong một số tình huống, nhưng thread pool tái sử dụng worker phức tạp hơn; việc truyền ngữ cảnh không kiểm soát có nguy cơ lẫn danh tính. Hãy sử dụng cơ chế tích hợp có vòng đời rõ ràng nếu yêu cầu thực sự cần bảo toàn SecurityContext.

## 14. Những lỗi dễ gặp trong thực tế

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Sau callback OIDC thành công, request tiếp theo lại bị redirect login | Session/cookie không được duy trì; cấu hình stateless; SecurityContext không được lưu | Kiểm tra cookie, session policy, repository, reverse proxy và log redirect |
| Controller `@AuthenticationPrincipal OidcUser` nhận `null` | Request chưa xác thực, principal thuộc loại khác, hoặc endpoint không dùng OIDC Login | Xem SecurityFilterChain, Authentication và phương thức đăng nhập thực tế |
| `authentication.getName()` khác email | Username attribute / principal representation khác email | Dùng `iss` + `sub` cho liên kết tài khoản |
| Session tồn tại nhưng không có Authentication hợp lệ | Session có thể được tạo trước login hoặc context đã bị xóa | Đừng dùng “session != null” làm điều kiện đăng nhập |
| Reload lại trang vẫn login dù token đã cũ | HttpSession và token có lifecycle độc lập | Xem thời hạn session, cơ chế authorized client và chính sách freshness |
| Logout xong mở trang lại vào được ngay | OP vẫn giữ SSO | Phân biệt local logout với OIDC RP-Initiated Logout |
| Hai tài khoản bị lẫn dữ liệu | Session/token/authorized client bị dùng chung không đúng principal | Kiểm tra định danh `iss` + `sub`, cache key và account switching |
| Access token không còn hiệu lực nhưng giao diện vẫn đang đăng nhập | SecurityContext còn, authorized client/token khác trạng thái | Xem expiry/refresh của token và yêu cầu API |
| Sau custom authentication, request tiếp theo mất login | Context chỉ đặt vào Holder mà chưa được repository lưu theo cấu hình hiện tại | Kiểm tra SecurityContextRepository và chiến lược lưu của Spring Security 6 |
| Nhiều node server khiến login lúc được lúc mất | Session không được chia sẻ hoặc cookie/routing không nhất quán | Xem session store, sticky routing khi cần, encryption/serialization và cookie |
| Tạo async task thấy principal trống | Context gắn với request thread | Dùng cơ chế truyền SecurityContext hoặc truyền dữ liệu nghiệp vụ an toàn |
| API bearer nhận 302 chuyển sang OP | API matcher bị áp web login chain | Tách API Resource Server chain với web session chain |

### 14.1. Quan sát request mà không để lộ bí mật

Khi xử lý sự cố, có thể xem:

- Request đi vào chain nào và được bảo vệ bằng cách nào.
- Authentication có tồn tại hay không; kiểu Authentication/principal.
- Registration ID nào được dùng để đăng nhập.
- Có session hợp lệ được browser gửi hay không.
- Session timeout, cookie attributes và policy cấu hình.
- Sự khác nhau giữa public URL và URL nội bộ khi chạy sau proxy.

**Không ghi** giá trị session ID, cookie, authorization code, client secret, ID token, access token hoặc refresh token vào log. Nếu cần liên kết sự kiện để điều tra, sử dụng correlation ID riêng không phải credential.

### 14.2. Khi custom login hoặc AuthenticationProvider

Với login flow do framework cung cấp, Spring Security thực hiện nhiều bước lưu context và session protection. Nhưng nếu ứng dụng tự dựng một `Authentication` và đặt vào `SecurityContextHolder`, việc đó **chưa bảo đảm** context sẽ tồn tại ở request kế tiếp.

Trong Spring Security 6, việc lưu context theo cơ chế rõ ràng có thể yêu cầu gọi `SecurityContextRepository.saveContext(context, request, response)` với repository đang được cấu hình. Cũng cần áp dụng những biện pháp session fixation và kiểm tra xác thực tương ứng.

Thay vì tự tái tạo OIDC callback, hãy ưu tiên `oauth2Login()` và các extension point Spring Security cung cấp, như authorization request resolver, OIDC user service hoặc authentication success handler, để giữ luồng xác thực nhất quán.

## 15. Câu hỏi tình huống

### Tình huống A: nhận diện người dùng ở một controller

**Yêu cầu:** sau OIDC Login, trang hồ sơ cần định danh ổn định để truy vấn dữ liệu nội bộ.

**Cách xử lý:** lấy `OidcUser` qua `@AuthenticationPrincipal`, đọc `iss` và `sub` của ID token đã được Spring Security xử lý, sau đó ánh xạ cặp này sang tài khoản nội bộ. Tên/email có thể hiển thị nhưng không nên là khóa duy nhất để xác định danh tính.

### Tình huống B: người dùng đã login nhưng API trả 401

**Yêu cầu:** Portal hiển thị người dùng đã đăng nhập, nhưng khi gọi Inventory API bằng access token thì API báo 401.

**Cách xử lý:** kiểm tra OAuth2AuthorizedClient, thời hạn access token, khả năng refresh, issuer/audience/scope mà API chấp nhận và cách request gắn bearer token. **Không xóa `SecurityContext` một cách mặc định** chỉ vì một API bên ngoài từ chối token; hai trạng thái có vòng đời và quy tắc khác nhau.

### Tình huống C: muốn API stateless và web session-based

**Yêu cầu:** `/api/**` nhận bearer JWT, còn `/dashboard` đăng nhập qua OIDC.

**Cách xử lý:** cấu hình các SecurityFilterChain phù hợp với request matcher. Chain API xác thực bearer token với chính sách stateless khi đúng kiến trúc; chain web dùng OIDC Login và session. Tránh để API bị bắt chuyển hướng sang OP khi thiếu token.

### Tình huống D: logout nhưng người dùng vào lại không nhập mật khẩu

**Yêu cầu:** sau khi bấm logout ở Portal, người dùng quay lại `/dashboard` và thấy đăng nhập nhanh trở lại.

**Cách xử lý:** kiểm tra phiên ứng dụng đã bị xóa đúng cách chưa. Nếu có, đây có thể là SSO còn tồn tại ở OP. Khi nghiệp vụ cần logout toàn hệ thống, tích hợp OIDC logout theo khả năng provider thay vì nhầm local logout với OP logout.

## 16. Tự kiểm tra kiến thức

**Câu 1.** `SecurityContextHolder` mặc định giữ context bằng ThreadLocal. Vậy làm sao request sau vẫn biết người dùng đã login?

**Đáp án:** Spring Security khôi phục SecurityContext từ `SecurityContextRepository` được cấu hình, thường liên quan `HttpSession` trong web login session-based. ThreadLocal chỉ cung cấp context cho luồng request hiện tại.

**Câu 2.** Có session cookie có đồng nghĩa đã được xác thực không?

**Đáp án:** Không. Session có thể tồn tại trước login để chứa authorization request, request cache hoặc dữ liệu khác. Phải dựa trên Authentication của SecurityContext và chính sách authorization.

**Câu 3.** Với OIDC Login, principal thường là gì?

**Đáp án:** `OidcUser`, thường bên trong một `OAuth2AuthenticationToken`. Người dùng được xác định tin cậy bằng issuer và subject từ ID token đã được xác minh.

**Câu 4.** Có `OidcUser` thì access token cho API có luôn ở `SecurityContext` không?

**Đáp án:** Không nên giả định. Token được quản lý qua `OAuth2AuthorizedClient` và các repository/service dành cho authorized client; cách lưu trữ tùy cấu hình.

**Câu 5.** Session tại Portal hết hạn có đồng nghĩa phiên SSO tại OP cũng hết hạn không?

**Đáp án:** Không. Chúng là hai phiên do hai hệ thống quản lý. Khi quay lại Portal, browser có thể bắt đầu một login flow mới mà OP vẫn nhận ra người dùng nhờ SSO.

**Câu 6.** Có nên đặt `SessionCreationPolicy.STATELESS` cho cùng chain đang dùng OIDC Authorization Code Login mặc định không?

**Đáp án:** Không nên đổi một cách máy móc. Flow redirect cần quản lý state và callback, còn web login thường cần session sau khi xác thực. Nếu muốn thiết kế stateless, phải có kiến trúc và repository phù hợp.

**Câu 7.** Vì sao không nên dùng `SecurityContextHolder` trực tiếp trong thread pool để suy ra principal từ request ban đầu?

**Đáp án:** Context mặc định gắn với thread request. Worker thread không tự nhận context; thread pool còn tái sử dụng thread. Cần cơ chế truyền ngữ cảnh được hỗ trợ hoặc truyền dữ liệu nghiệp vụ phù hợp.

**Câu 8.** Một controller biết người dùng đã đăng nhập bằng `Authentication.isAuthenticated()`. Điều đó có đủ để cho phép duyệt một đơn hàng bất kỳ không?

**Đáp án:** Không. Phải áp quyền truy cập tài nguyên và các quy tắc nghiệp vụ riêng. Xác thực và phân quyền là hai trách nhiệm khác nhau.

## Ghi nhớ

- **`SecurityContext` chứa `Authentication`; Authentication chứa principal và authorities.** Sau OIDC Login, principal thường là `OidcUser` trong `OAuth2AuthenticationToken`.
- **`SecurityContextHolder` cung cấp context trong luồng request**, còn `SecurityContextRepository` có thể lưu/khôi phục context giữa các request; với web login Servlet thông dụng, cơ chế này thường dựa trên **`HttpSession`**.
- **`HttpSession` là phiên của ứng dụng**, khác phiên SSO của OP, thời hạn ID token và vòng đời access token.
- **`OidcUser` biểu diễn người dùng đã xác thực theo OIDC**; khi liên kết tài khoản, ưu tiên cặp **`iss` + `sub`** thay vì tên hoặc email.
- **`OAuth2AuthorizedClient` quản lý token đã được cấp** để gọi API và không đồng nhất với SecurityContext.
- Với hệ thống vừa có web login vừa có API bearer, hãy cấu hình filter chain, session policy và các cơ chế bảo mật cho từng kiểu request.

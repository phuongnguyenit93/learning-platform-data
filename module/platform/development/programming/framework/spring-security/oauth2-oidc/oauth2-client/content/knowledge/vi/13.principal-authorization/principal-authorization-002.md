# 13.2. OAuth2User, OidcUser và truy cập attributes hoặc claims

## 1. Bối cảnh: người dùng đăng nhập xong thì Spring Security cung cấp đối tượng nào?

Trong ứng dụng **Spring Security OAuth 2.0/OIDC Client**, việc đăng nhập qua một nhà cung cấp như Google, GitHub hoặc hệ thống SSO doanh nghiệp thường được cấu hình bằng `oauth2Login()`. Khi đăng nhập thành công, Spring Security tạo một `Authentication` đại diện cho người dùng hiện tại. Bên trong authentication có **principal**, là đối tượng chứa những thông tin danh tính đã được hệ thống đăng nhập xử lý.

Hai kiểu principal quan trọng:

- **`OAuth2User`:** đại diện người dùng đăng nhập qua chức năng OAuth2 Login. Thông tin người dùng thường được lấy từ một endpoint của provider, ví dụ UserInfo endpoint hoặc API riêng như GitHub. Những trường trả về được gọi là **attributes**; cấu trúc có thể khác nhau giữa các provider.
- **`OidcUser`:** đại diện người dùng đăng nhập bằng **OpenID Connect (OIDC)**, là lớp mở rộng chuẩn hóa việc xác thực danh tính dựa trên OAuth 2.0. Ngoài các attributes, principal này cung cấp **ID Token**, **OIDC claims** và có thể có **UserInfo**.

Vì `OidcUser` **mở rộng `OAuth2User`**, có thể xử lý một `OidcUser` thông qua interface `OAuth2User` khi chỉ cần thông tin chung. Tuy nhiên, nếu cần `sub`, `iss`, ID Token và OIDC claims có ý nghĩa chuẩn hóa, hãy dùng API của `OidcUser`.

> **Điểm cần nhớ:** `OAuth2User` và `OidcUser` là **principal của người dùng đăng nhập vào ứng dụng**; chúng không đồng nghĩa với access token, không phải nơi gửi bearer token để gọi API và không tự biến một ứng dụng thành Resource Server.

### 1.1. Phân biệt ba lớp dữ liệu xuất hiện sau login

| Dữ liệu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Principal** | `OAuth2User` hoặc `OidcUser` | Danh tính và attributes/claims mà Spring Security đưa vào `Authentication` |
| **Authentication** | `OAuth2AuthenticationToken` | Chứa principal, authorities và đăng ký OAuth2 client liên quan |
| **Authorized client** | `OAuth2AuthorizedClient` | Chứa `ClientRegistration` và access token, có thể có refresh token |

Một controller đọc `OidcUser.getEmail()` **không cần** đọc access token. Ngược lại, để backend gọi API khác thay mặt người dùng, ứng dụng cần truy xuất **authorized client** và gửi access token đúng cách. Không nên lấy ID Token làm bearer token cho API.

## 2. Đường đi từ OIDC Provider đến principal

Ví dụ nhân viên đăng nhập một portal qua OIDC Provider:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant P as Spring Boot Portal
    participant I as OIDC Provider
    participant S as SecurityContext / Session

    U->>P: Mở /oauth2/authorization/corporate
    P-->>U: Redirect authorization request
    U->>I: Đăng nhập, MFA, consent (nếu cần)
    I-->>U: Callback authorization code
    U->>P: GET callback?code=...&state=...
    P->>I: Token Request
    I-->>P: ID Token + Access Token (+ token khác nếu có)
    P->>P: Kiểm tra ID Token: chữ ký, iss, aud, exp, nonce...
    opt UserInfo được sử dụng
        P->>I: GET UserInfo với access token
        I-->>P: UserInfo claims
    end
    P->>P: Tạo OidcUser và Authentication
    P->>S: Lưu SecurityContext theo cấu hình
    P-->>U: Session cookie / trang ứng dụng
    U->>P: GET /me với session cookie
    P->>S: Tải Authentication hiện tại
    S-->>P: Principal: OidcUser
    P-->>U: Thông tin người dùng được phép hiển thị
~~~

Luồng trên minh họa **OIDC Authorization Code** trong ứng dụng web có session. Với OAuth2 Login không sử dụng OIDC, principal có thể là `OAuth2User` được tạo từ API người dùng của provider; không có ID Token OIDC theo hợp đồng chuẩn.

**Quan trọng:** Spring Security chỉ nên tạo principal OIDC đáng tin cậy sau khi các bước xác thực và kiểm tra token thích hợp hoàn tất. Nếu tự viết code lấy JWT payload bằng Base64 rồi tạo principal từ JSON chưa kiểm tra chữ ký, bạn đã bỏ qua cơ chế xác thực quan trọng.

## 3. So sánh trực tiếp `OAuth2User` và `OidcUser`

| Tiêu chí | `OAuth2User` | `OidcUser` |
| --- | --- | --- |
| Mục đích | Principal người dùng đăng nhập qua OAuth2 Login | Principal người dùng đăng nhập qua **OpenID Connect** |
| Quan hệ kiểu | Interface cơ bản | **Mở rộng `OAuth2User`** |
| Dữ liệu người dùng | `getAttributes()`: map thuộc tính theo provider | `getAttributes()` và `getClaims()`: các dữ liệu claims OIDC |
| Tên principal | `getName()` | `getName()`; có thể truy cập `getSubject()` |
| Quyền Spring Security | `getAuthorities()` | `getAuthorities()` |
| ID Token | Không được bảo đảm bởi interface | `getIdToken()` |
| UserInfo chuẩn OIDC | Không được bảo đảm | `getUserInfo()` nếu có dữ liệu UserInfo |
| Getter OIDC chuẩn | Không có sẵn theo interface | `getEmail()`, `getFullName()`, `getSubject()`, v.v. |
| Định danh người dùng | Provider-specific, phụ thuộc tên attribute | `iss` + `sub` là cặp định danh chuẩn để liên kết chủ thể |
| Ví dụ thường gặp | OAuth2 Login với GitHub provider | OIDC Login với Google hoặc corporate OIDC Provider |
| Có chứa bearer token để gọi API? | **Không** | **Không**; ID Token trong OIDC principal có mục đích khác |

Một `OidcUser` cũng có `getAttributes()` vì nó là `OAuth2User`. Tuy nhiên, nên dùng getter OIDC chuẩn hoặc truy cập claim từ `getIdToken()`/`getUserInfo()` khi nghiệp vụ cần rõ **nguồn gốc** và **ý nghĩa** của từng claim.

### 3.1. `OAuth2User` không tự chuẩn hóa mọi attribute

Ví dụ provider A trả:

~~~json
{
  "id": 4172,
  "login": "linhdev",
  "name": "Linh Nguyen",
  "avatar_url": "https://example.test/avatar/4172"
}
~~~

Provider B trả:

~~~json
{
  "user_id": "u-9001",
  "display_name": "Linh N.",
  "email_address": "linh@example.test"
}
~~~

Hai payload trên chỉ là ví dụ thuộc tính do provider cung cấp. Spring Security có thể đưa chúng vào `OAuth2User.getAttributes()`, nhưng **không có một chuẩn OAuth 2.0 chung buộc mọi provider đặt user ID ở `id`, `user_id` hay `sub`**.

Do vậy cần sử dụng `ClientRegistration`/`registrationId` và **hợp đồng API của từng provider** để biết attribute nào là định danh ổn định. Đừng mặc định `getAttribute("email")` luôn có giá trị.

### 3.2. OIDC chuẩn hóa nhiều claims nhưng vẫn có trường tùy chọn

OIDC Core định nghĩa các claims như:

- `sub`: định danh subject tại issuer.
- `iss`: issuer đã phát hành ID Token.
- `aud`: audience được phát hành cho token, thường chứa client ID.
- `exp`, `iat`: thời điểm hết hạn và phát hành.
- `nonce`: giá trị liên kết yêu cầu xác thực, nếu được dùng.
- `name`, `given_name`, `family_name`, `preferred_username`: thông tin hồ sơ tùy khả năng/scope.
- `email`, `email_verified`: địa chỉ email và trạng thái xác minh, khi được provider phát hành.

Các claims hồ sơ **không nhất thiết xuất hiện** chỉ vì ứng dụng đã yêu cầu scope `profile` hoặc `email`. Chính sách consent, khả năng của provider, cấu hình release claims và dữ liệu tài khoản ảnh hưởng kết quả.

## 4. Những interface và class cần biết

Trong Spring Security:

~~~java
// Principal chung của OAuth2 Login
org.springframework.security.oauth2.core.user.OAuth2User

// Principal OIDC
org.springframework.security.oauth2.core.oidc.user.OidcUser

// Thông tin ID Token và UserInfo
org.springframework.security.oauth2.core.oidc.OidcIdToken
org.springframework.security.oauth2.core.oidc.OidcUserInfo

// Authentication sau OAuth2 Login
org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken
~~~

Những phương thức quan trọng:

~~~java
// OAuth2User
Map<String, Object> attributes = oauth2User.getAttributes();
Collection<? extends GrantedAuthority> authorities = oauth2User.getAuthorities();
String name = oauth2User.getName();
Object rawEmail = oauth2User.getAttributes().get("email");

// OidcUser
OidcIdToken idToken = oidcUser.getIdToken();
OidcUserInfo userInfo = oidcUser.getUserInfo();  // có thể null
Map<String, Object> claims = oidcUser.getClaims();
String subject = oidcUser.getSubject();
String email = oidcUser.getEmail();              // có thể null
~~~

Code minh họa biến `oauth2User` và `oidcUser` đã được lấy từ một `Authentication` hợp lệ. Với `OidcUser`, thông tin được trình bày qua API claim accessor, giúp code ít phụ thuộc tên key khi đọc các claims chuẩn.

### 4.1. Các implementation mặc định

- **`DefaultOAuth2User`:** triển khai `OAuth2User` với attributes map, authorities và key dùng làm principal name.
- **`DefaultOidcUser`:** triển khai `OidcUser` với ID Token, UserInfo (khi có), authorities và cơ chế lấy principal name.
- **`OAuth2UserAuthority`:** authority đại diện thuộc tính người dùng được tải qua OAuth2 UserInfo/provider API.
- **`OidcUserAuthority`:** authority chứa thông tin ID Token và UserInfo để hỗ trợ mapping quyền trong login flow.

Những class này nằm bên dưới cấu hình Spring Security. Trong business code, ưu tiên phụ thuộc interface `OAuth2User`/`OidcUser` thay vì cast vào implementation cụ thể nếu không cần.

## 5. Truy cập `OAuth2User` trong Spring MVC/Servlet

Ví dụ một web app dùng OAuth2 Login với GitHub. Khi đăng nhập thành công, controller có thể nhận principal thông qua annotation:

~~~java
@RestController
class ProfileController {

    @GetMapping("/api/me/oauth2")
    Map<String, Object> currentOAuth2User(
            @AuthenticationPrincipal OAuth2User user) {

        if (user == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        Map<String, Object> attributes = user.getAttributes();

        Object rawLogin = attributes.get("login");
        String login = rawLogin instanceof String value ? value : "";

        Object rawName = attributes.get("name");
        String displayName = rawName instanceof String value ? value : "";

        return Map.of(
            "principalName", user.getName(),
            "login", login,
            "displayName", displayName
        );
    }
}
~~~

Các kiểu được import tương ứng từ Spring Web, Spring Security và Java. Ví dụ giả định provider trả attributes với key `login` và `name` như một số cấu hình GitHub. Với provider khác, phải thay key theo hợp đồng dữ liệu thực tế.

**Tại sao dùng `instanceof String`?** `getAttributes()` trả `Map<String, Object>`; giá trị có thể là String, Number, Boolean, List hoặc Map. Việc ép thẳng `(String) attributes.get("id")` có thể gây `ClassCastException` nếu provider trả ID dưới dạng số.

### 5.1. Đọc attribute trực tiếp

`OAuth2User` hỗ trợ truy cập qua key:

~~~java
String displayName = user.getAttribute("name");
Object externalId = user.getAttribute("id");
~~~

Method `getAttribute(...)` thuận tiện khi đã biết chính xác kiểu dữ liệu. Trong code có yêu cầu ổn định và phải xử lý nhiều provider, có thể đọc từ map rồi kiểm tra kiểu tường minh trước khi chuyển sang mô hình domain.

Nếu thuộc tính có cấu trúc lồng nhau:

~~~json
{
  "profile": {
    "displayName": "Linh",
    "locale": "vi"
  }
}
~~~

cần truy cập lồng theo cấu trúc đúng hoặc tạo adapter/DTO provider-specific. Đừng giả định mọi claim đều phẳng hoặc đều là String.

### 5.2. Đọc principal qua `Authentication`

Controller Servlet cũng có thể nhận `Authentication`:

~~~java
@GetMapping("/api/me/authentication")
Map<String, Object> authenticationDetails(Authentication authentication) {

    Object principal = authentication.getPrincipal();

    if (!(principal instanceof OAuth2User oauth2User)) {
        throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
    }

    String registrationId = "unknown";
    if (authentication instanceof OAuth2AuthenticationToken oauth2) {
        registrationId = oauth2.getAuthorizedClientRegistrationId();
    }

    return Map.of(
        "registrationId", registrationId,
        "principalName", oauth2User.getName(),
        "attributeKeys", oauth2User.getAttributes().keySet()
    );
}
~~~

`OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` giúp biết người dùng đăng nhập bằng registration nào, ví dụ `github`, `google` hoặc `corporate`. Giá trị đó hữu ích khi ứng dụng hỗ trợ nhiều provider và mỗi provider có cách định danh user khác nhau.

**Không dùng registration ID làm ID của người dùng:** `corporate` là khóa cấu hình OAuth2 Client, nhiều người dùng có thể cùng đăng nhập qua registration đó.

### 5.3. Sử dụng `SecurityContextHolder` ở lớp service Servlet

Trong code đồng bộ, có thể đọc authentication hiện tại:

~~~java
@Service
class CurrentUserService {

    OAuth2User currentUser() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !(authentication.getPrincipal() instanceof OAuth2User user)) {
            throw new IllegalStateException(
                "Current principal is not an OAuth2 user");
        }

        return user;
    }
}
~~~

Lớp service chỉ dùng kiểu này khi thật sự cần gắn với security context của request. Trong kiến trúc tách biệt, truyền **ID tài khoản nội bộ** đã được xác minh vào business service thường giúp code dễ kiểm thử và tránh phụ thuộc framework.

**Lưu ý về thread:** `SecurityContextHolder` trong Servlet thường dùng context gắn với thread theo chính sách cấu hình. Khi chuyển sang asynchronous executor/thread khác, không được giả định context tự truyền tới mọi thread. Cần dùng cơ chế propagation do Spring Security hỗ trợ hoặc truyền thông tin tối thiểu cần thiết theo cách an toàn.

## 6. Truy cập `OidcUser` và các claims chuẩn

Giả sử ứng dụng dùng OIDC Provider với scope `openid profile email`. Một ID Token minh họa:

~~~json
{
  "iss": "https://idp.example.com/realms/staff",
  "sub": "47db8e71-2f39-4a84-8112-6326290ad7f2",
  "aud": "employee-portal",
  "exp": 1920000300,
  "iat": 1920000000,
  "name": "Linh Nguyen",
  "preferred_username": "linh.nguyen",
  "email": "linh@example.test",
  "email_verified": true
}
~~~

Payload trên chỉ minh họa các claim; không phải một ID Token hoàn chỉnh, có chữ ký hoặc giá trị thời gian để dùng trong thực tế.

Khi Spring Security xác minh thành công ID Token và tạo `OidcUser`, controller có thể:

~~~java
@RestController
class OidcProfileController {

    @GetMapping("/api/me/oidc")
    Map<String, Object> currentOidcUser(
            @AuthenticationPrincipal OidcUser user) {

        if (user == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        String email = user.getEmail();
        String fullName = user.getFullName();

        return Map.of(
            "subject", user.getSubject(),
            "name", fullName == null ? "" : fullName,
            "email", email == null ? "" : email,
            "emailVerified", Boolean.TRUE.equals(user.getEmailVerified())
        );
    }
}
~~~

Ví dụ sử dụng các getter OIDC chuẩn. `getEmail()` và `getFullName()` có thể trả `null` khi provider không công bố claim. Vì `Map.of(...)` không nhận giá trị null, code chuyển field tùy chọn sang chuỗi rỗng trước khi tạo map.

**Vấn đề nghiệp vụ:** `emailVerified=false` trong đoạn code trên cũng là cách biểu diễn khi claim `email_verified` **vắng mặt**. Nếu cần phân biệt ba trạng thái “đã xác minh / chưa xác minh / provider không công bố”, hãy giữ `Boolean` nullable hoặc một trường trạng thái riêng, thay vì ép `null` thành `false`.

### 6.1. Getter chuẩn và map claims

Một `OidcUser` thường có thể dùng theo hai cách:

~~~java
String subject = user.getSubject();
String preferredUsername = user.getPreferredUsername();
String email = user.getEmail();

Object department = user.getClaims().get("department");
Object assurance = user.getClaims().get("acr");
~~~

Các getter `getSubject()`, `getPreferredUsername()`, `getEmail()` giúp code dễ đọc với các claim chuẩn. Với **custom claim** như `department`, `tenant_id` hoặc `roles`, cần dùng map và xử lý kiểu dữ liệu theo cấu hình IdP.

Ví dụ custom claim dạng danh sách:

~~~json
{
  "department": "engineering",
  "roles": ["viewer", "editor"],
  "tenant_id": "tenant-a"
}
~~~

Cách đọc an toàn:

~~~java
Object rawRoles = user.getClaims().get("roles");

List<String> roles = rawRoles instanceof List<?> list
    ? list.stream()
          .filter(String.class::isInstance)
          .map(String.class::cast)
          .toList()
    : List.of();
~~~

**Không tự động coi `roles` là quyền của Spring Security**. Đây chỉ là một claim có thể được provider phát hành. Để dùng nó trong `hasRole(...)` hoặc `@PreAuthorize(...)`, ứng dụng cần **ánh xạ thành `GrantedAuthority`** theo chính sách tin cậy của hệ thống.

### 6.2. Phân biệt `getClaims()`, `getAttributes()`, ID Token và UserInfo

Một `OidcUser` cung cấp nhiều cách xem dữ liệu:

~~~java
Map<String, Object> attributes = user.getAttributes();
Map<String, Object> principalClaims = user.getClaims();

OidcIdToken idToken = user.getIdToken();
Map<String, Object> idTokenClaims = idToken.getClaims();

OidcUserInfo userInfo = user.getUserInfo();
Map<String, Object> userInfoClaims =
    userInfo == null ? Map.of() : userInfo.getClaims();
~~~

Ý nghĩa:

- `getIdToken().getClaims()`: claims có trong **ID Token đã được kiểm tra** theo luồng OIDC.
- `getUserInfo().getClaims()`: claims từ **UserInfo Endpoint** nếu Spring Security đã gọi và provider trả dữ liệu tương ứng. `getUserInfo()` có thể là `null`.
- `getClaims()`/`getAttributes()` trên principal: dạng dữ liệu OIDC mà implementation đã trình bày cho ứng dụng; có thể bao gồm thông tin từ ID Token và UserInfo theo cách Spring Security xây principal.

Khi một nghiệp vụ cần biết claim **đến từ ID Token hay UserInfo**, hãy đọc trực tiếp từ `idTokenClaims` hoặc `userInfoClaims`. Đừng dựa vào giả định mọi provider luôn trả cùng field ở cả hai nơi hoặc thứ tự hợp nhất của chúng là hợp đồng nghiệp vụ.

**UserInfo không phải luôn được gọi.** Một số provider chỉ cung cấp các claims cần thiết trong ID Token; một số ứng dụng không có access token thích hợp hoặc không cấu hình/dùng UserInfo. Chưa có UserInfo không đồng nghĩa ID Token không hợp lệ.

### 6.3. Tại sao thông tin trong UserInfo cần được gắn với đúng subject?

UserInfo là một nguồn bổ sung attributes về người dùng. Dữ liệu này phải thuộc **đúng người dùng đã được xác thực trong ID Token**, đặc biệt subject `sub`. Spring Security/OIDC client cần bảo đảm sự liên kết theo giao thức trước khi coi UserInfo là thông tin của cùng chủ thể.

Nếu tự triển khai fetch UserInfo bên ngoài framework, cần giữ ràng buộc subject, token và provider; không chỉ gọi một URL bất kỳ rồi dùng JSON trả về để ghi đè danh tính đã xác thực.

## 7. `getName()`, `sub`, email và định danh bền vững

Đây là phần quan trọng nhất khi ánh xạ login bên ngoài sang tài khoản nội bộ.

### 7.1. `getName()` không luôn là username dễ đọc

`OAuth2User.getName()` là tên định danh mà implementation/configuration principal chọn. Với một số provider, nó có thể đến từ `id`; với provider khác, từ `login` hoặc `sub` tùy cấu hình.

Trong OIDC, `OidcUser.getName()` thường dựa trên `sub` trong cấu hình mặc định, nhưng ứng dụng có thể đặt **name attribute key** khác. Vì thế **không nên viết logic domain mặc định cho rằng `getName()` luôn là email hoặc giá trị dễ hiển thị**.

Ví dụ:

~~~text
OAuth2User:
    getName()             = "4172"
    attributes["login"]    = "linhdev"

OidcUser:
    getName()             = "47db8e71-2f39-4a84-8112-6326290ad7f2"
    getSubject()          = "47db8e71-2f39-4a84-8112-6326290ad7f2"
    getFullName()         = "Linh Nguyen"
    getPreferredUsername()= "linh.nguyen"
~~~

Lấy `getFullName()` hoặc một display name được kiểm soát để hiển thị UI. Để liên kết tài khoản, dùng **định danh subject ổn định** theo hợp đồng provider.

### 7.2. Với OIDC, dùng cặp issuer + subject

OIDC định danh người dùng bằng claim `sub` **trong phạm vi issuer `iss`**. Hai provider khác nhau có thể phát cùng giá trị `sub` cho những người khác nhau. Hơn nữa, một provider có thể triển khai **pairwise subject identifier**, tạo `sub` khác nhau cho những client/sector khác nhau.

Vì vậy cặp logic an toàn để lập bảng liên kết tài khoản nội bộ là:

~~~text
(issuer, subject)  →  internalUserId

("https://idp.example.com/realms/staff",
 "47db8e71-2f39-4a84-8112-6326290ad7f2")
    →  92041
~~~

Ví dụ Java:

~~~java
record ExternalIdentity(String issuer, String subject) {}

ExternalIdentity externalIdentity(OidcUser user) {
    Object rawIssuer = user.getIdToken().getClaims().get("iss");

    if (!(rawIssuer instanceof String issuer)
            || issuer.isBlank()
            || user.getSubject() == null
            || user.getSubject().isBlank()) {
        throw new IllegalStateException("OIDC identity is incomplete");
    }

    return new ExternalIdentity(issuer, user.getSubject());
}
~~~

Code chỉ tạo khóa liên kết, không thay thế việc Spring Security xác minh ID Token. Không dùng đoạn này để chấp nhận một JWT do client gửi chưa được kiểm tra chữ ký và claims.

Với ứng dụng đa tenant, có thể phải ràng buộc thêm **tenant hoặc ClientRegistration** theo chính sách liên kết nội bộ, nhất là khi provider phát pairwise subject hoặc nhiều tenant dùng cấu hình IdP khác nhau.

### 7.3. Email không phải định danh bất biến

Email có thể đổi tên, bị thu hồi rồi cấp lại, không được provider xác minh, không được trả về hoặc có cùng giá trị trong nhiều nguồn danh tính.

Vì vậy:

- **Không mặc định dùng `email` làm primary key** để liên kết một OIDC principal với tài khoản nội bộ.
- Nếu sử dụng email cho chức năng yêu cầu địa chỉ đã xác minh, kiểm tra `email_verified` (nếu provider cung cấp), độ tin cậy và chính sách của provider.
- Không tự động gộp hai tài khoản chỉ vì chúng có cùng email mà chưa có quy trình account linking an toàn.
- Nếu cần đổi email của tài khoản nội bộ, kiểm tra quyền cập nhật độc lập với việc token chứa một claim mới.

Đối với OAuth2 Login **không OIDC**, ứng dụng cần chọn ID provider-specific ổn định cùng registration/provider identifier, ví dụ `(registrationId, providerUserId)`, và hiểu chính sách của provider về vòng đời ID đó.

### 7.4. Tách display name và identity

Một mô hình domain đơn giản:

~~~java
record CurrentUserProfile(
    String internalUserId,
    String displayName,
    String email
) {}
~~~

Một service ánh xạ `ExternalIdentity` thành `internalUserId` rồi lấy hồ sơ từ database nội bộ. Phần UI hiển thị `displayName`, `email` đã qua chính sách, trong khi authorization dựa vào **account ID nội bộ và quyền đã được hệ thống cấp**.

Đừng dùng trực tiếp `name` hoặc `preferred_username` làm điều kiện phân quyền nhạy cảm, ví dụ “ai có name == admin thì là admin”.

## 8. Spring Boot: OAuth2 Login và OIDC Login cùng tồn tại

### 8.1. Dependency chung

Trong ứng dụng Spring MVC/Servlet:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

### 8.2. Đăng ký một OAuth2 provider và một OIDC provider

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          github:
            client-id: ${GITHUB_CLIENT_ID}
            client-secret: ${GITHUB_CLIENT_SECRET}
            scope:
              - read:user
              - user:email

          corporate:
            provider: company-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

        provider:
          company-oidc:
            issuer-uri: https://idp.example.com/realms/staff
~~~

Khi chạy ứng dụng:

- `/oauth2/authorization/github` bắt đầu đăng nhập qua GitHub với cách trả attributes theo nhà cung cấp.
- `/oauth2/authorization/corporate` bắt đầu đăng nhập OIDC qua provider doanh nghiệp, yêu cầu scope `openid` và tạo OIDC principal nếu luồng thành công.
- Callback mặc định của Spring Security OAuth2 Login thường là `/login/oauth2/code/{registrationId}`; đăng ký redirect URI tương ứng tại mỗi provider.
- Client secret được lấy từ cấu hình môi trường/secret manager; không commit giá trị thật vào Git.

Ví dụ `SecurityFilterChain`:

~~~java
@Configuration
class LoginSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/css/**", "/js/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Cùng một cấu hình `oauth2Login()` có thể hỗ trợ OAuth2 Login và OIDC Login tùy registration/provider. **Kiểu principal cuối cùng phụ thuộc giao thức và dữ liệu provider**, không chỉ tên endpoint `/login`.

## 9. Một controller xử lý cả `OAuth2User` và `OidcUser`

Khi ứng dụng hỗ trợ nhiều provider, có thể dùng `OAuth2User` làm kiểu chung, sau đó phân nhánh cho OIDC:

~~~java
@RestController
class UnifiedProfileController {

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {

        if (authentication == null
                || !(authentication.getPrincipal() instanceof OAuth2User user)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        String registrationId = authentication instanceof OAuth2AuthenticationToken token
            ? token.getAuthorizedClientRegistrationId()
            : "unknown";

        if (user instanceof OidcUser oidc) {
            String subject = oidc.getSubject();
            String email = oidc.getEmail();

            return Map.of(
                "kind", "oidc",
                "registrationId", registrationId,
                "subject", subject,
                "email", email == null ? "" : email
            );
        }

        Object rawProviderId = user.getAttributes().get("id");

        return Map.of(
            "kind", "oauth2",
            "registrationId", registrationId,
            "providerId", rawProviderId == null ? "" : rawProviderId.toString(),
            "principalName", user.getName()
        );
    }
}
~~~

Đây là ví dụ **phân nhánh kiểu principal**, không phải adapter hoàn chỉnh cho mọi OAuth2 provider. Với GitHub có thể chọn `id`; provider khác có thể không có trường này. Trong code thực tế, xây dựng **adapter theo `registrationId`**, rồi ánh xạ sang một định danh nội bộ nhất quán.

### 9.1. Khi nào dùng `instanceof OidcUser`?

Có ích khi:

- Một ứng dụng nhận cả GitHub OAuth2 Login và corporate OIDC Login.
- Một endpoint cần trả UI profile dùng chung nhưng có thêm thông tin chuẩn OIDC nếu sẵn có.
- Business layer cần xử lý riêng issuer + subject cho OIDC, và provider-specific user ID cho nguồn không OIDC.
- Cần truy cập ID Token hoặc UserInfo để chẩn đoán một claim không có trong principal chung.

Nếu một endpoint **chỉ phục vụ OIDC**, dùng tham số `@AuthenticationPrincipal OidcUser user` trực tiếp thường rõ ràng hơn.

### 9.2. Tránh cast không kiểm tra

Không nên viết:

~~~java
OidcUser user = (OidcUser) authentication.getPrincipal();
~~~

nếu cùng ứng dụng hỗ trợ cả OAuth2 và OIDC provider. Một principal loại `DefaultOAuth2User` không thể cast thành `OidcUser`.

Dùng:

~~~java
Object principal = authentication.getPrincipal();

if (principal instanceof OidcUser oidcUser) {
    // Chỉ xử lý claims OIDC ở đây.
}
~~~

Hoặc yêu cầu endpoint OIDC-only qua cấu hình/hợp đồng rõ ràng để tránh lỗi kiểu dữ liệu khi provider login thay đổi.

## 10. Truy cập principal bằng `@AuthenticationPrincipal`

Annotation `org.springframework.security.core.annotation.AuthenticationPrincipal` cho phép Spring inject principal đã được xác thực vào handler:

~~~java
@GetMapping("/me/name")
String currentName(@AuthenticationPrincipal OAuth2User user) {
    return user.getName();
}
~~~

Trong ứng dụng sử dụng OIDC:

~~~java
@GetMapping("/me/subject")
String currentSubject(@AuthenticationPrincipal OidcUser user) {
    return user.getSubject();
}
~~~

Chú ý:

- Annotation trích principal từ security context, **không tự chạy OAuth2 authorization flow**.
- Nếu chưa đăng nhập hoặc principal không đúng kiểu, tham số có thể là `null` theo cách argument resolver xử lý, nên endpoint phải được bảo vệ và/hoặc có kiểm tra rõ ràng.
- `@AuthenticationPrincipal(errorOnInvalidType = true)` có thể giúp bộc lộ lỗi khi principal không đúng kiểu mong đợi, nhưng vẫn cần thiết kế endpoint theo loại authentication cho phép.
- Tránh truy cập dữ liệu nhạy cảm từ principal rồi trả nguyên bản ra API công khai.

### 10.1. Dùng SpEL để lấy một attribute

Spring Security hỗ trợ expression trên `@AuthenticationPrincipal`:

~~~java
@GetMapping("/me/email")
String email(
        @AuthenticationPrincipal(expression = "attributes['email']")
        String email) {

    return email == null ? "" : email;
}
~~~

Expression này đọc key `email` từ `getAttributes()` của principal hiện tại. Nó tiện cho handler rất đơn giản nhưng có hạn chế:

- Field có thể không tồn tại hoặc có kiểu khác String.
- Provider có thể đổi schema, trong khi expression là chuỗi nằm rải rác trong controller.
- Nếu phải phân biệt claim đến từ ID Token hay UserInfo, nên truy cập `OidcUser` tường minh.
- Nếu giá trị ảnh hưởng nghiệp vụ bảo mật, nên đi qua một identity adapter/domain service thay vì xử lý toàn bộ trong annotation expression.

### 10.2. `Principal` kiểu Java không giống `OAuth2User`

Một method có thể nhận `java.security.Principal` hoặc `Authentication`. `Principal.getName()` chỉ cung cấp tên. `Authentication` còn cho phép đọc `getAuthorities()`, `getPrincipal()` và kiểu authentication hiện tại.

Để đọc claims chuyên biệt, lấy principal với đúng kiểu hoặc dùng `@AuthenticationPrincipal`. Đừng ép `Principal` trực tiếp thành `OidcUser` khi chưa biết đối tượng là gì.

## 11. Truy cập principal trong Spring WebFlux

WebFlux sử dụng security context theo **reactive context**. Các khái niệm `OAuth2User`/`OidcUser` vẫn giống nhau, nhưng cách đọc authentication trong code xử lý bất đồng bộ phải phù hợp Reactor.

### 11.1. Cấu hình OAuth2 Login reactive

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~java
@Configuration
@EnableWebFluxSecurity
class WebFluxLoginSecurity {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/assets/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

### 11.2. Dùng `@AuthenticationPrincipal` trong handler WebFlux

~~~java
@RestController
class ReactiveProfileController {

    @GetMapping("/api/me/oidc")
    Mono<Map<String, String>> me(@AuthenticationPrincipal OidcUser user) {

        if (user == null) {
            return Mono.error(
                new ResponseStatusException(HttpStatus.UNAUTHORIZED));
        }

        return Mono.just(Map.of(
            "subject", user.getSubject(),
            "email", user.getEmail() == null ? "" : user.getEmail()
        ));
    }
}
~~~

Annotation trích principal khi WebFlux xử lý request được xác thực. Vì đọc vài claim từ object hiện có là tác vụ nhẹ, ví dụ sử dụng `Mono.just(...)` mà không yêu cầu thực hiện I/O.

Nếu cần truy vấn database hoặc API ngoài để gắn với tài khoản nội bộ, dùng **reactive repository/WebClient** và kết hợp bằng `flatMap`/`map`, tránh `.block()` trên event loop.

### 11.3. Dùng `ReactiveSecurityContextHolder` trong reactive service

Nếu cần truy cập context bên trong chuỗi reactive:

~~~java
@Service
class ReactiveCurrentUserService {

    Mono<String> currentOidcSubject() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getPrincipal)
            .ofType(OidcUser.class)
            .map(OidcUser::getSubject);
    }
}
~~~

Nếu không có authentication OIDC hợp lệ, chuỗi có thể rỗng. Tầng HTTP hoặc business service phải quyết định trả `401`, sử dụng identity flow khác hoặc phản hồi phù hợp.

**Không dùng `SecurityContextHolder.getContext()` trong WebFlux rồi giả định principal của reactive request luôn nằm trong `ThreadLocal` hiện tại.** Reactor chuyển luồng và sử dụng Context riêng; dùng `ReactiveSecurityContextHolder` hoặc injection của WebFlux.

## 12. Attributes, claims và mô hình dữ liệu: xử lý kiểu an toàn

Provider có thể trả JSON với nhiều kiểu dữ liệu:

~~~json
{
  "sub": "u-123",
  "email": "linh@example.test",
  "email_verified": true,
  "age": 27,
  "roles": ["viewer", "editor"],
  "address": {
    "country": "VN"
  }
}
~~~

Sau khi được parse, `getAttributes()`/`getClaims()` có thể chứa:

- `String` cho subject/email.
- `Boolean` cho `email_verified`.
- `Number` cho một số field số.
- `Collection` cho danh sách.
- `Map` cho object lồng nhau.

Một số claims chuẩn có API accessor được chuyển đổi/chuẩn hóa bởi Spring Security. Đối với custom claims, **đừng giả định tất cả luôn có kiểu String**.

Ví dụ helper đọc chuỗi:

~~~java
static Optional<String> stringClaim(
        Map<String, Object> claims, String name) {

    Object value = claims.get(name);
    return value instanceof String text && !text.isBlank()
        ? Optional.of(text)
        : Optional.empty();
}
~~~

Ví dụ helper đọc danh sách chuỗi:

~~~java
static List<String> stringListClaim(
        Map<String, Object> claims, String name) {

    Object value = claims.get(name);

    if (!(value instanceof Collection<?> values)) {
        return List.of();
    }

    return values.stream()
        .filter(String.class::isInstance)
        .map(String.class::cast)
        .toList();
}
~~~

Các helper trên minh họa cách đọc data linh hoạt, **không có nghĩa mọi claim sai kiểu nên được âm thầm bỏ qua**. Với claim bắt buộc của một quyết định bảo mật, dữ liệu thiếu/sai kiểu cần làm yêu cầu thất bại an toàn hoặc được xử lý theo policy rõ ràng.

### 12.1. Chuẩn hóa thông tin ở ranh giới hệ thống

Thay vì để mọi controller đọc trực tiếp các key của GitHub, Google, corporate IdP, nên định nghĩa một mô hình nội bộ:

~~~java
record LoginIdentity(
    String provider,
    String issuer,
    String externalSubject,
    String displayName,
    String email,
    boolean emailVerified
) {}
~~~

Sau đó triển khai adapter theo registration:

~~~text
OAuth2User (GitHub attributes)
          \
           --> Provider identity adapter --> LoginIdentity
          /
OidcUser (OIDC claims)
~~~

Adapter chịu trách nhiệm:

1. Xác định provider bằng `registrationId`/issuer đã được cấu hình.
2. Chọn đúng field làm external user ID.
3. Kiểm tra required claims và kiểu dữ liệu.
4. Áp dụng chính sách email verification / account linking.
5. Ánh xạ sang tài khoản nội bộ.
6. Chỉ xuất những trường cần thiết cho UI và business service.

Việc chuẩn hóa giúp tránh lặp lại logic provider-specific trong nhiều controller và giảm lỗi khi thay đổi provider.

## 13. Principal và phân quyền: attributes/claims có tự biến thành roles không?

**Không.** `OAuth2User.getAuthorities()` và `OidcUser.getAuthorities()` trả các **`GrantedAuthority` mà Spring Security gắn vào `Authentication`**. Chúng không nhất thiết trùng với nội dung field `roles` trong claims.

Sau OAuth2 Login, Spring Security thường có các authority đại diện user profile, ví dụ `OAuth2UserAuthority` hoặc `OidcUserAuthority`; tùy grant/scopes/configuration có thể có authority dạng `SCOPE_...`. Nhưng một endpoint yêu cầu:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void deleteReport(Long id) {
    // ...
}
~~~

chỉ hoạt động khi authentication chứa authority tương ứng như `ROLE_ADMIN` theo quy ước, và khi **method security** đã được bật. `email`, `preferred_username` hoặc một claim `roles` bất kỳ **không tự động** trở thành `ROLE_ADMIN`.

### 13.1. Xem authorities hiện có

~~~java
@GetMapping("/api/me/authorities")
List<String> authorities(Authentication authentication) {

    return authentication.getAuthorities().stream()
        .map(GrantedAuthority::getAuthority)
        .toList();
}
~~~

Endpoint chỉ nên phục vụ mục đích phù hợp với quyền truy cập; **không trả toàn bộ claims/attributes nhạy cảm** chỉ để debug. Một quyền được cấp cho tài khoản nội bộ có thể đến từ database hoặc chính sách doanh nghiệp và không được thể hiện ở claim của provider.

### 13.2. Ánh xạ quyền từ claim của provider khi được phép

Spring Security hỗ trợ `GrantedAuthoritiesMapper` trong OAuth2 Login để chuyển các authority liên quan đến principal thành authority ứng dụng. Ví dụ ID Token của OIDC Provider **được hệ thống tin cậy** có custom claim `roles`:

~~~java
@Configuration
class OAuth2AuthorityMapping {

    @Bean
    GrantedAuthoritiesMapper userAuthoritiesMapper() {
        return existingAuthorities -> {
            Set<GrantedAuthority> mapped =
                new HashSet<>(existingAuthorities);

            for (GrantedAuthority authority : existingAuthorities) {
                if (authority instanceof OidcUserAuthority oidcAuthority) {
                    Object rawRoles =
                        oidcAuthority.getIdToken().getClaims().get("roles");

                    if (rawRoles instanceof Collection<?> roles
                            && roles.contains("report-reader")) {
                        mapped.add(new SimpleGrantedAuthority(
                            "ROLE_REPORT_READER"));
                    }
                }
            }

            return mapped;
        };
    }
}
~~~

Ví dụ dựa trên giả định provider có phát claim `roles` ở **ID Token**, và giá trị `report-reader` đã được tổ chức kiểm soát. Các class tương ứng gồm `GrantedAuthoritiesMapper`, `GrantedAuthority`, `SimpleGrantedAuthority` và `OidcUserAuthority` trong Spring Security. Phần `import` được lược bỏ.

**Hạn chế quan trọng:**

- `roles` **không phải claim chuẩn bắt buộc** trong ID Token. Provider có thể đưa vào UserInfo hoặc custom claim khác; cần xác định schema thật.
- Đừng dùng `email` hoặc display name để suy ra quyền admin.
- Chỉ tin những claim được phát hành bởi **issuer đúng**, dành cho client đúng và đã qua validation.
- Quyền nghiệp vụ quan trọng có thể cần tra database nội bộ để kiểm soát thu hồi ngay, không phụ thuộc mọi quyền nằm trong ID Token.
- Nếu thay đổi authorities theo phiên đăng nhập, **quyền có thể cũ** cho đến khi authentication/session được cập nhật. Cần chính sách đồng bộ hoặc reauthorization phù hợp.
- Nếu dùng `@PreAuthorize`, cần bật method security, ví dụ `@EnableMethodSecurity` trong ứng dụng Servlet thích hợp.

### 13.3. Phân biệt scope và role

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **OAuth2 scope** | Phạm vi quyền mà client xin/được cấp đối với API hoặc dữ liệu | `profile`, `email`, `reports.read` |
| **OIDC claim** | Thông tin về user/authentication trong ID Token/UserInfo | `sub`, `email_verified`, `department` |
| **Spring Security authority** | Quyền mà authorization engine của ứng dụng kiểm tra | `ROLE_ADMIN`, `SCOPE_reports.read` |
| **Domain role** | Quyền nghiệp vụ được hệ thống nội bộ quản lý | `report_manager`, `billing_approver` |

Các lớp này có thể được ánh xạ với nhau theo chính sách, nhưng **không được coi là tương đương mặc định**. Một scope `openid` không cấp quyền quản trị ứng dụng; email đã được xác minh cũng không tạo quyền đọc dữ liệu mật.

## 14. Khi nào đọc ID Token, khi nào đọc UserInfo, khi nào gọi API khác?

Một `OidcUser` có thể cung cấp sẵn các claims cần hiển thị thông tin đăng nhập. Nếu cần dữ liệu ngoài phạm vi OIDC profile (ví dụ số đơn hàng, lịch làm việc), có thể phải gọi **Resource Server** khác với access token phù hợp.

| Nhu cầu | Nguồn thích hợp | Lưu ý |
| --- | --- | --- |
| Xác định chủ thể đã đăng nhập | OIDC `iss` + `sub` từ ID Token đã xác minh | Định danh ổn định theo issuer |
| Hiển thị tên/email người dùng | `OidcUser` claims hoặc UserInfo khi có | Có thể thiếu; tuân thủ privacy |
| Đọc account ID provider OAuth2 không OIDC | `OAuth2User` attributes theo provider | Mapping provider-specific |
| Lấy danh sách projects của người dùng | Business API/Resource Server | Dùng access token đúng audience/scopes |
| Lấy quyền nội bộ của ứng dụng | Domain authorization service/database hoặc policy mapping | Không mặc định dùng email/claims tùy ý |
| Xác minh token được phép gọi REST API của mình | OAuth2 Resource Server | Khác với việc đọc OIDC principal trong web login |

Đối với backend cần gọi API thay người dùng, có thể lấy `OAuth2AuthorizedClient` thông qua các thành phần Spring Security OAuth2 Client. **Không gửi `OidcUser.getIdToken().getTokenValue()` như access token** tới API; ID Token có audience là client và phục vụ xác thực danh tính ở client.

### 14.1. Vì sao không trả nguyên `getAttributes()` qua REST API?

Một số provider đưa vào attributes các trường không dành cho UI công khai: internal IDs, nhóm, flags, số điện thoại, metadata định danh, locale hoặc cấu hình tài khoản. Việc trả nguyên map:

~~~java
return user.getAttributes();
~~~

có thể tiết lộ dữ liệu mà frontend không cần. Tốt hơn là trả một **DTO/record whitelisted** gồm `displayName`, `avatarUrl` hoặc những trường mà ứng dụng được phép hiển thị.

Với ID Token và UserInfo, cũng không nên log hay serialize toàn bộ claims vô hạn định. Nếu cần audit, chọn đúng trường, áp dụng retention và hạn chế truy cập.

## 15. Tùy biến principal: username attribute, user service và role mapping

### 15.1. `user-name-attribute` cho OAuth2 provider không OIDC

Một provider có thể trả user ID ở key `id` hoặc `user_id`. Trong cấu hình provider, Spring Boot/Spring Security cho phép khai báo key dùng làm tên principal trong trường hợp tương ứng, ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner-auth
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            scope: profile.read
        provider:
          partner-auth:
            authorization-uri: https://auth.partner.example/authorize
            token-uri: https://auth.partner.example/token
            user-info-uri: https://api.partner.example/me
            user-name-attribute: account_id
~~~

Cấu hình trên minh họa OAuth2 provider có API trả `account_id`. Endpoint và scope phải được thay bằng hợp đồng thật của provider. `user-name-attribute` giúp Spring xác định giá trị `getName()`, **không biến `account_id` thành subject OIDC** hoặc bảo đảm claim luôn có.

### 15.2. Tùy biến `OAuth2UserService`

Nếu provider cần xử lý đặc biệt khi tải attributes, Spring Security có điểm mở rộng:

~~~java
OAuth2UserService<OAuth2UserRequest, OAuth2User>
~~~

Trong ứng dụng Servlet, có thể tích hợp user service tùy chỉnh vào:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .userService(customOAuth2UserService)
    )
);
~~~

Ví dụ này giả định `customOAuth2UserService` là bean đã được tạo. User service cần gọi delegate chuẩn hoặc xử lý response theo hợp đồng provider, giữ nguyên các ràng buộc token và không tự tin nguồn dữ liệu chưa xác minh.

Với OIDC có interface và implementation chuyên dụng, như `OAuth2UserService<OidcUserRequest, OidcUser>` và `OidcUserService`, được cấu hình qua nhánh `oidcUserService(...)` ở những phiên bản Spring Security tương ứng:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(customOidcUserService)
    )
);
~~~

Khi tùy biến, cần cẩn trọng:

- Không bypass xác minh ID Token, nonce hoặc UserInfo subject binding.
- Giữ chính sách username/subject nhất quán.
- Không đổi principal name thành email chỉ để tiện UI nếu hệ thống đang dùng tên đó làm identity key.
- Tách logic mapping domain user với những request I/O ngoài không cần thiết.
- Xử lý lỗi IdP/UserInfo đúng cách thay vì chấp nhận dữ liệu thiếu tin cậy.

### 15.3. `DefaultOidcUser` và tùy chọn tên principal

`DefaultOidcUser` có các constructor cho phép chỉ định một key làm principal name khi hệ thống cần. Nếu thay default name attribute sang `preferred_username` hoặc một field khác, cần bảo đảm field thực sự tồn tại và hiểu hậu quả với account linkage, session mapping và audit.

Cách an toàn trong nhiều ứng dụng là **giữ `sub` làm định danh ổn định** trong domain, đồng thời có một `displayName` riêng để hiển thị. Đừng thay principal name chỉ vì ID OIDC khó đọc.

## 16. Principal trong session và dữ liệu có thể thay đổi

Trong web app dùng OAuth2 Login với session:

1. Spring Security xác thực người dùng, tạo `Authentication` chứa principal.
2. Ứng dụng lưu context theo session policy.
3. Các request tiếp theo có thể đọc **principal đã lưu**, ngay cả khi profile ở IdP vừa được chỉnh sửa.

Điều này ảnh hưởng đến:

- **Tên/email:** người dùng đổi email ở IdP không đảm bảo `OidcUser.getEmail()` của session hiện tại lập tức cập nhật.
- **Nhóm/role:** người dùng bị thu hồi quyền ở IdP không chắc authorities đã cache trong session được thay ngay.
- **Avatar/tên hiển thị:** có thể cần cơ chế cập nhật hồ sơ hoặc tái đăng nhập theo nhu cầu.
- **Account disabled:** nếu hệ thống cần vô hiệu hóa tài khoản ngay lập tức, phải có policy nội bộ, session invalidation hoặc revalidation phù hợp.

**Đừng dùng một claim đã đọc ở thời điểm login làm bằng chứng không bao giờ thay đổi** cho các quyết định nhạy cảm về sau. Cân nhắc quyền nội bộ được truy vấn ở thời điểm request khi cần hiệu lực thu hồi nhanh.

### 16.1. Người dùng đăng nhập nhiều provider

Một người có thể liên kết cả tài khoản corporate OIDC và GitHub OAuth2 vào cùng user nội bộ. Cần quy trình account linking:

~~~text
corporate (issuer + sub) ─┐
                          ├── internalUserId = 92041
github (provider + id) ───┘
~~~

Không tự động gộp hai external identities chỉ vì cùng email hiển thị. Tài khoản GitHub/OIDC cần được **xác minh** và liên kết qua quy trình được phép. Mỗi identity provider có quy tắc ID riêng và có thể khác về độ tin cậy.

## 17. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân phổ biến | Hướng kiểm tra |
| --- | --- | --- |
| `@AuthenticationPrincipal OidcUser` là `null` | User chưa xác thực, đăng nhập OAuth2 không OIDC hoặc authentication type khác | Kiểm tra security chain, provider, scope `openid` và principal thực |
| `ClassCastException: DefaultOAuth2User ... OidcUser` | Ép mọi principal thành OIDC | Dùng `instanceof` hoặc phân vùng endpoint |
| `getAttribute("email")` trả `null` | Provider không cấp email, thiếu consent/scope, key khác | Kiểm tra payload provider và cấu hình claims |
| `getEmail()` trả `null` dù đăng nhập OIDC | Email là claim tùy chọn; IdP không release | Kiểm tra ID Token/UserInfo và policy IdP |
| `getName()` là số/UUID thay vì username | Default name attribute key là provider ID hoặc `sub` | Dùng displayName riêng; kiểm tra `user-name-attribute` |
| `getUserInfo()` là `null` | UserInfo không được gọi hoặc provider không cấp | Kiểm tra provider, scopes và OIDC user service |
| Claim `roles` tồn tại nhưng `hasRole('ADMIN')` bị từ chối | Chưa map claim thành `GrantedAuthority` hoặc role khác | Kiểm tra authorities thực và policy mapping |
| `ROLE_ADMIN` vẫn tồn tại sau khi admin bị thu hồi | Session/authentication cũ chưa cập nhật | Kiểm tra refresh/revalidation/session invalidation |
| Account bị liên kết sai sau đổi email | Dùng email làm external identity key | Dùng OIDC issuer+subject hoặc provider ID ổn định |
| UserInfo và ID Token khác `sub` | Lỗi/mismatch nguồn danh tính, custom fetch sai | Dừng xử lý; giữ kiểm tra OIDC subject binding |
| WebFlux service đọc principal sai | Dùng ThreadLocal context trong chuỗi reactive | Dùng `ReactiveSecurityContextHolder` hoặc injection đúng |
| API yêu cầu bearer token nhưng app chỉ có OIDC principal | Nhầm login principal với authorized client | Lấy access token từ OAuth2 authorized client và gửi đúng audience |
| `Map.of(...)` gây `NullPointerException` | Field optional như email/name là null | Xử lý field vắng mặt trước khi tạo Map |
| `ClassCastException` khi đọc `id` | Provider trả số, code ép String | Kiểm tra kiểu trong attributes map |
| Login không tạo `OidcUser` | Provider không thực sự hỗ trợ OIDC hoặc request thiếu scope `openid` | Kiểm tra discovery, grant và OIDC configuration |

### 17.1. Cách quan sát principal có kiểm soát

Trong môi trường phát triển, kiểm tra **tên class principal**, registration ID và danh sách **keys** (không phải values) của attributes:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null
        && authentication.getPrincipal() instanceof OAuth2User user) {

    String principalType = user.getClass().getSimpleName();
    Set<String> attributeKeys = user.getAttributes().keySet();

    // Dùng debugger hoặc log đã kiểm soát theo chính sách môi trường.
}
~~~

Việc xem keys thường ít nhạy cảm hơn log cả attributes, nhưng vẫn nên áp dụng chính sách telemetry, giới hạn và loại bỏ thông tin không cần thiết. Đặc biệt **không log raw ID Token, access token, refresh token, email/phone nếu không có lý do, session cookie hoặc client secret**.

### 17.2. Phân biệt authentication và authorization failure

- **401 Unauthorized** thường xảy ra khi chưa xác thực hoặc token/credential không được chấp nhận.
- **403 Forbidden** thường xảy ra khi đã xác thực nhưng không đủ authorities/quyền.
- Một người dùng có `OidcUser` hợp lệ **không đồng nghĩa** họ được phép gọi mọi endpoint.
- Một API Resource Server từ chối access token là bài toán khác với `OidcUser.getClaims()` trong portal.

Nếu method `@PreAuthorize("hasRole('ADMIN')")` từ chối, kiểm tra authorities đang gắn với authentication, chính sách role mapping và trạng thái user nội bộ. Không cố thêm `ROLE_ADMIN` vào mọi user chỉ để endpoint hoạt động.

## 18. Tình huống thực hành

### Tình huống A — Đăng nhập bằng Google OIDC, cần hiển thị email

**Bài toán:** Trang hồ sơ muốn hiển thị email người dùng sau login.

**Cách làm:** Inject `OidcUser` rồi gọi `getEmail()`, xử lý null, và chỉ hiển thị theo chính sách bảo vệ dữ liệu. Nếu nghiệp vụ yêu cầu email đã xác minh, kiểm tra claim `email_verified` với nguồn IdP đáng tin.

**Không làm:** dùng email làm primary key duy nhất của tài khoản nội bộ hoặc tự động coi email là quyền quản trị.

### Tình huống B — Đăng nhập bằng GitHub OAuth2, `OidcUser` không được inject

**Bài toán:** Controller ban đầu sử dụng `@AuthenticationPrincipal OidcUser` nhưng với GitHub login thì principal không đúng kiểu.

**Cách làm:** Dùng `OAuth2User`, đọc attributes từ GitHub, xác định stable ID theo provider và xây adapter phù hợp. Nếu ứng dụng hỗ trợ nhiều provider, dùng `instanceof OidcUser` cho nhánh OIDC.

**Không làm:** ép `DefaultOAuth2User` thành `OidcUser` hoặc coi một OAuth2 provider thường là OIDC nếu không có giao thức OIDC.

### Tình huống C — Corporate IdP thêm claim `department`

**Bài toán:** UI cần hiển thị tên phòng ban từ token/UserInfo.

**Cách làm:** Đọc `user.getClaims().get("department")`, kiểm tra kiểu và xử lý thiếu dữ liệu. Nếu yêu cầu biết claim phát ra từ ID Token hay UserInfo, đọc từng nguồn một. Ánh xạ sang DTO nội bộ.

**Không làm:** coi `department="security"` là quyền admin nếu chưa có chính sách authorization.

### Tình huống D — Quyền bị thu hồi nhưng session vẫn truy cập được

**Bài toán:** IdP bỏ user khỏi nhóm quản trị, nhưng `authentication.getAuthorities()` vẫn còn `ROLE_ADMIN`.

**Cách làm:** Xem thời điểm user login, cơ chế mapping authorities và vòng đời session. Nếu yêu cầu thu hồi ngay, áp dụng revalidation/lookup quyền nội bộ hoặc invalidation; không dựa vào claims đã chụp tại login.

### Tình huống E — Một nhân viên có nhiều tài khoản SSO, email trùng nhau

**Bài toán:** Hai issuer trả cùng email nhưng `sub` khác nhau.

**Cách làm:** Gắn external identity bằng **issuer + subject**, chỉ hợp nhất thành user nội bộ khi đi qua account-linking được cho phép. Email có thể dùng làm gợi ý, không phải bằng chứng hai danh tính giống nhau.

### Tình huống F — Backend cần gọi Orders API sau khi login

**Bài toán:** Có `OidcUser` rồi, developer muốn gửi `user.getIdToken().getTokenValue()` làm bearer token tới Orders API.

**Cách làm:** Lấy access token được cấp cho Orders API qua `OAuth2AuthorizedClient`/manager và HTTP client OAuth2, rồi để Orders API với vai trò Resource Server kiểm tra audience, scope và chữ ký/introspection. ID Token phục vụ xác thực danh tính client, không phải credential API mặc định.

### Tình huống G — WebFlux request dùng `SecurityContextHolder` nhưng principal null

**Bài toán:** Reactive service truy cập context trong thread khác sau `flatMap`.

**Cách làm:** Dùng `ReactiveSecurityContextHolder.getContext()` hoặc truyền identity vào reactive chain từ controller; không suy luận context có mặt trên mọi ThreadLocal khi Reactor chuyển scheduler.

## 19. Câu hỏi ôn tập

**Câu 1. `OidcUser` có phải một loại `OAuth2User` không?**

Có. `OidcUser` mở rộng `OAuth2User` và bổ sung các API OIDC như `getIdToken()`, `getUserInfo()` và các claim accessors.

**Câu 2. Với GitHub OAuth2 Login, có thể luôn inject `OidcUser` không?**

Không. Một OAuth2 provider không sử dụng OIDC có thể trả principal kiểu `OAuth2User`/`DefaultOAuth2User`. Sử dụng đúng interface và kiểm tra kiểu.

**Câu 3. `getAttributes()` và `getClaims()` khác nhau ở đâu?**

`getAttributes()` là map dữ liệu chung của `OAuth2User`; `OidcUser` còn có OIDC claims và các getter chuẩn. Khi cần biết nguồn, đọc `getIdToken().getClaims()` hoặc `getUserInfo().getClaims()` nếu UserInfo tồn tại.

**Câu 4. Có nên dùng email làm khóa duy nhất để liên kết OIDC identity với user nội bộ?**

Không nên. Email có thể thay đổi hoặc được tái cấp. Cặp **issuer + subject** từ ID Token đã xác minh thường là cơ sở định danh chuẩn.

**Câu 5. Claim `email_verified=true` có tự động cấp quyền `ROLE_USER` hoặc `ROLE_ADMIN` không?**

Không. Xác minh email và phân quyền là hai việc khác nhau; mapping authorities cần chính sách tường minh.

**Câu 6. Một ID Token có `sub` và `iss` hợp lệ về định dạng có tự chứng minh danh tính không?**

Không. Token phải được Spring Security/OIDC client xác minh chữ ký, issuer, audience, thời hạn, nonce khi có và các ràng buộc liên quan.

**Câu 7. `OidcUser.getUserInfo()` có luôn khác null không?**

Không. Điều này phụ thuộc provider, scope, cấu hình và việc UserInfo được sử dụng. Ứng dụng phải xử lý thiếu UserInfo.

**Câu 8. `getName()` có luôn trả email dễ đọc không?**

Không. Nó phụ thuộc name attribute key/implementation. Với OIDC có thể là `sub`, còn display name là trường khác.

**Câu 9. Trong WebFlux, dùng gì để lấy security context trong reactive service?**

Dùng `ReactiveSecurityContextHolder` hoặc injection/parameter theo reactive framework. Tránh phụ thuộc ThreadLocal context khi Reactor chuyển luồng.

**Câu 10. Access token nằm ở `OidcUser` hay `OAuth2AuthorizedClient`?**

Access token gắn với **`OAuth2AuthorizedClient`**; `OidcUser` đại diện người dùng và có API đọc ID Token/claims.

**Câu 11. Vì sao không trả toàn bộ `getAttributes()` trong endpoint `/api/me`?**

Vì có thể chứa dữ liệu người dùng/metadata nhạy cảm hoặc không cần cho frontend. Hãy trả DTO với những trường đã được cho phép.

**Câu 12. Claim `roles=["editor"]` trong ID Token có tự động làm `hasRole("EDITOR")` thành true không?**

Không. Ứng dụng phải có `GrantedAuthoritiesMapper` hoặc cơ chế mapping quyền nội bộ tương ứng, bảo đảm issuer/claims đáng tin và quy ước authority đúng.

## 20. Tài liệu tham khảo chính thức

- [Spring Security Reference — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security Reference — Advanced OAuth 2.0 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security Reference — OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security API — OAuth2User](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/user/OAuth2User.html)
- [Spring Security API — OidcUser](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/oidc/user/OidcUser.html)
- [Spring Security API — DefaultOAuth2User](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/user/DefaultOAuth2User.html)
- [Spring Security API — DefaultOidcUser](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/oidc/user/DefaultOidcUser.html)
- [Spring Security API — OAuth2AuthenticationToken](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/authentication/OAuth2AuthenticationToken.html)
- [Spring Security API — OidcUserAuthority](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/oidc/user/OidcUserAuthority.html)
- [OpenID Connect Core 1.0 — ID Token và Standard Claims](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Core 1.0 — Subject Identifier Types](https://openid.net/specs/openid-connect-core-1_0.html#SubjectIDTypes)

**Ghi nhớ:** `OAuth2User` cung cấp **attributes** theo nhà cung cấp; `OidcUser` mở rộng nó với **ID Token và claims OIDC**. Dùng `@AuthenticationPrincipal` hoặc `Authentication` để đọc principal, xử lý field tùy chọn và kiểu dữ liệu an toàn. Với OIDC, liên kết danh tính nội bộ bằng **issuer + subject**, dùng claims để lấy thông tin hồ sơ theo chính sách và **ánh xạ authorities tường minh** khi cần phân quyền. Principal đã đăng nhập, access token để gọi API và role nghiệp vụ là những trách nhiệm khác nhau.


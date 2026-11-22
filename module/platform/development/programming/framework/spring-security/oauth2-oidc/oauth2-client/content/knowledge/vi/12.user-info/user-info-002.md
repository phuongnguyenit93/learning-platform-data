# 12.2. `OidcUserService` và quá trình tải OIDC UserInfo

Trong **Spring Security OAuth 2.0/OIDC Client**, đăng nhập bằng OpenID Connect (OIDC) không chỉ là chuyển người dùng tới nhà cung cấp danh tính rồi nhận access token. Client cần **xác minh ID Token**, xác định người dùng đang đăng nhập và có thể **tải thêm hồ sơ** từ **UserInfo Endpoint**. Trên Servlet stack, thành phần **`OidcUserService`** giữ vai trò quan trọng trong bước xây dựng principal `OidcUser` từ ID Token cùng những claim được phép lấy qua UserInfo.

Bài học này giải thích `OidcUserService` hoạt động ở đâu trong luồng OAuth2 Login, khi nào UserInfo được tải, cách đối chiếu `sub` giữa ID Token và UserInfo, cách Spring biểu diễn dữ liệu bằng `OidcUser`/`OidcUserInfo`, và những điểm cần lưu ý khi tùy biến service trong ứng dụng thực tế.

> **Trọng tâm:** ID Token chứng minh kết quả xác thực theo OIDC; UserInfo cung cấp claim hồ sơ được cấp phép. `OidcUserService` kết hợp dữ liệu để tạo người dùng đã đăng nhập, **không được bỏ qua việc xác minh danh tính hoặc dùng UserInfo như một nguồn tin độc lập không kiểm soát**.

## 1. Đặt `OidcUserService` vào đúng luồng đăng nhập

Với Authorization Code Flow, ứng dụng Spring Security là một **OIDC Relying Party**: nó tin một OpenID Provider (OP) đã đăng ký, chứ không tự kiểm tra mật khẩu của người dùng.

Một phiên đăng nhập Servlet phổ biến gồm:

1. Người dùng tới `/oauth2/authorization/company` hoặc truy cập một tài nguyên cần đăng nhập.
2. Spring Security tạo authorization request, chứa `client_id`, `redirect_uri`, `scope=openid ...`, `state` và các tham số bảo vệ flow thích hợp.
3. Trình duyệt được chuyển đến Authorization Endpoint của OP.
4. OP xác thực người dùng và trả authorization code về callback của Spring, thường là `/login/oauth2/code/company`.
5. Spring trao đổi authorization code tại Token Endpoint, nhận access token và ID Token.
6. Spring **xác minh ID Token** theo các quy tắc OIDC liên quan như chữ ký, issuer, audience, thời gian và nonce khi áp dụng.
7. **`OidcUserService`** xử lý yêu cầu tải hồ sơ; nếu đủ điều kiện, dùng access token gọi **UserInfo Endpoint**.
8. Spring kiểm tra dữ liệu UserInfo thuộc **cùng subject `sub`** với ID Token, xây dựng `OidcUser` và hoàn tất `Authentication`.
9. Ứng dụng dùng principal này để hiển thị tên, email, ảnh hoặc kết hợp với nguồn quyền nội bộ cho authorization.

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant C as Spring Security Client
    participant OP as OpenID Provider

    U->>B: Mở ứng dụng
    B->>C: GET /oauth2/authorization/company
    C-->>B: 302 tới Authorization Endpoint
    B->>OP: Authorization Request (openid, state, PKCE...)
    OP->>U: Đăng nhập/consent
    OP-->>B: 302 callback?code=...&state=...
    B->>C: GET /login/oauth2/code/company
    C->>OP: POST Token Endpoint, đổi code
    OP-->>C: access_token + id_token (+ refresh_token?)
    C->>C: Xác minh ID Token và các claim giao thức
    C->>C: Gọi OidcUserService.loadUser(...)
    opt UserInfo endpoint khả dụng và chính sách yêu cầu tải
        C->>OP: GET UserInfo, Authorization: Bearer access_token
        OP-->>C: JSON với sub, name, email...
        C->>C: Đối chiếu sub của UserInfo với ID Token
    end
    C->>C: Tạo OidcUser, ánh xạ authorities
    C-->>B: Hoàn tất đăng nhập, tạo phiên/redirect
```

**Điểm phân biệt:** `OidcUserService` không phải lớp gửi authorization code tới Token Endpoint và cũng không phải lớp xử lý redirect từ trình duyệt. Nó làm việc **sau khi Client đã có ID Token và access token phù hợp** trong quá trình đăng nhập.

## 2. `OidcUserService` là gì?

Lớp `OidcUserService` thuộc package:

```java
org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService
```

Về hợp đồng, nó triển khai một `OAuth2UserService` chuyên cho OpenID Connect:

```java
OAuth2UserService<OidcUserRequest, OidcUser>
```

Phương thức chính:

```java
OidcUser loadUser(OidcUserRequest userRequest)
    throws OAuth2AuthenticationException;
```

Trong đó:

| Thành phần | Ý nghĩa |
|---|---|
| `OidcUserRequest` | Đầu vào chứa thông tin ClientRegistration, access token, ID Token và các dữ liệu token response cần thiết |
| `OidcUserService` | Có thể tải UserInfo và xây dựng OIDC principal dựa trên dữ liệu đã được nhận/xác minh |
| `OidcUserInfo` | Đối tượng biểu diễn claim UserInfo, khi có dữ liệu được tải |
| `OidcUser` | Principal OIDC ứng dụng nhận sau đăng nhập thành công |
| `DefaultOidcUser` | Triển khai `OidcUser` phổ biến, tập hợp authorities, ID Token và UserInfo |
| `OidcUserAuthority` | Authority đặc trưng cho OIDC, có thể mang thông tin claim ID Token/UserInfo |
| `DefaultOAuth2UserService` | Thành phần thường được dùng để gọi UserInfo Endpoint bằng access token và đọc OAuth2 user attributes |

Các kiểu dữ liệu này thuộc **Spring Security OAuth2 Client**, không phải các controller hay service nghiệp vụ do dự án tự viết.

### 2.1. Phân biệt `OidcUserService` và `DefaultOAuth2UserService`

| Đặc điểm | `OidcUserService` | `DefaultOAuth2UserService` |
|---|---|---|
| Nhiệm vụ | Xử lý đăng nhập OIDC, kết hợp ID Token với UserInfo | Tải thông tin người dùng từ một UserInfo/user attributes endpoint theo OAuth2 |
| Đầu vào | `OidcUserRequest` | `OAuth2UserRequest` |
| Đầu ra | `OidcUser` | `OAuth2User` |
| Có ID Token OIDC làm cơ sở? | Có | Không phải yêu cầu cốt lõi |
| Ví dụ | Google/Keycloak OIDC Login | GitHub OAuth2 Login thông thường |
| Quan hệ | Có thể **ủy quyền việc gọi UserInfo** cho một OAuth2UserService bên trong | Có thể được `OidcUserService` sử dụng làm thành phần tải UserInfo |

Đừng nhầm `DefaultOAuth2UserService` với ID Token validator. Một HTTP call UserInfo trả JSON thành công **không đủ** để chứng minh có phiên đăng nhập OIDC hợp lệ.

### 2.2. `OidcUserService` khác với quản lý tài khoản nội bộ

`OidcUserService` trả một principal cho Spring Security. Nó không tự động:

- Tạo bản ghi người dùng trong database nghiệp vụ.
- Gán quyền `ROLE_ADMIN` cho người dùng có email theo một domain.
- Đồng bộ toàn bộ thông tin hồ sơ giữa nhiều hệ thống.
- Xác định một nhân viên còn thuộc tổ chức hay đã nghỉ việc.
- Tự gọi lại UserInfo Endpoint ở mọi request tiếp theo.
- Giữ mọi claim luôn mới trong suốt tuổi thọ HTTP session.

Nếu ứng dụng cần user provisioning, đồng bộ profile hay ánh xạ quyền, cần thiết kế các service nghiệp vụ riêng, có ranh giới dữ liệu và chính sách lỗi rõ ràng.

## 3. `OidcUserRequest` có những thông tin nào?

Sau khi Token Endpoint trả về response hợp lệ trong luồng OIDC, Spring Security tạo một `OidcUserRequest` để service xử lý.

Về ý nghĩa, đối tượng này cung cấp:

| Dữ liệu | Cách truy cập thường gặp | Dùng làm gì? |
|---|---|---|
| Registration của Client | `getClientRegistration()` | Xác định provider, endpoints, issuer và Client đã đăng ký |
| Access token | `getAccessToken()` | Dùng gọi UserInfo Endpoint khi thích hợp |
| ID Token | `getIdToken()` | Xác định subject và claim OIDC đã được xác minh |
| Tham số bổ sung của token response | `getAdditionalParameters()` | Phục vụ các phần mở rộng khi được hỗ trợ |

Ví dụ logic minh họa:

```java
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;

void inspectRequest(OidcUserRequest request) {
    String registrationId =
        request.getClientRegistration().getRegistrationId();

    OidcIdToken idToken = request.getIdToken();
    OAuth2AccessToken accessToken = request.getAccessToken();

    String subject = idToken.getSubject();

    // Chỉ dùng cho minh họa; không log tokenValue ở production.
    System.out.println("registrationId=" + registrationId);
    System.out.println("subject present=" + (subject != null));
    System.out.println("access token type=" +
        accessToken.getTokenType().getValue());
}
```

Trong thực tế, không cần tự khởi tạo `OidcUserRequest` để chạy flow mặc định; Spring Security đưa nó tới `OidcUserService` tại đúng thời điểm.

**Không đưa raw `getAccessToken().getTokenValue()` hoặc `getIdToken().getTokenValue()` vào log.** Các giá trị này là thông tin bảo mật hoặc chứa claim có tính riêng tư.

## 4. ID Token và UserInfo: hai nguồn dữ liệu khác nhau

OIDC Client thường nhận các claim ở hai vị trí:

1. **ID Token:** JWT được OP phát hành và Client xác minh. Nó chứa claim giao thức bắt buộc như `iss`, `sub`, `aud`, `exp` và `iat`.
2. **UserInfo response:** claim hồ sơ được OP cung cấp qua HTTP endpoint khi Client có access token hợp lệ và được phép truy cập.

Một ID Token có thể chỉ chứa:

```json
{
  "iss": "https://id.example.test/realms/company",
  "sub": "user-782",
  "aud": "spring-web-client",
  "exp": 1794794700,
  "iat": 1794791100
}
```

UserInfo response tương ứng có thể có:

```json
{
  "sub": "user-782",
  "name": "Nguyễn Thị Lan",
  "preferred_username": "lan.nguyen",
  "picture": "https://cdn.example.test/avatars/782.png",
  "email": "lan@example.test",
  "email_verified": true,
  "locale": "vi-VN"
}
```

Các giá trị chỉ minh họa. `sub` xuất hiện ở **cả hai nguồn** và phải chỉ tới cùng một chủ thể.

### 4.1. Vì sao không đặt mọi claim trong ID Token?

ID Token được thiết kế để chứng minh kết quả xác thực cho Client, không nhất thiết là bản sao đầy đủ của hồ sơ. Việc tách UserInfo giúp OP có thể:

- Chỉ cung cấp các trường theo consent và scope đã được cấp.
- Trả những thuộc tính không cần đặt trực tiếp trong ID Token.
- Áp dụng chính sách tiết lộ thông tin ở UserInfo Endpoint.
- Giảm số lượng claim mà Client phải nhận trong một token vốn dùng cho xác thực.

Tuy nhiên, UserInfo không phải “kênh nhận chắc chắn mọi claim”. Provider có thể thiếu dữ liệu, không được phép chia sẻ hoặc không hỗ trợ endpoint.

### 4.2. UserInfo có bắt buộc cho mọi đăng nhập OIDC không?

**Không.** Một OIDC Login có thể thành công mà không tải UserInfo nếu ID Token và các bước xác minh cần thiết hợp lệ. Có những provider chủ động trả một số claim hồ sơ trong ID Token; cũng có provider không công bố UserInfo Endpoint trong metadata.

Nếu Client cần email nhưng không thấy trong ID Token, bước tiếp theo là kiểm tra **cấu hình UserInfo**, scope và provider; không mặc định là Spring đã làm sai.

## 5. UserInfo Endpoint được gọi thế nào?

Theo OIDC, Client có thể sử dụng access token để yêu cầu thông tin người dùng. Một HTTP request phổ biến:

```http
GET /realms/company/protocol/openid-connect/userinfo HTTP/1.1
Host: id.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Accept: application/json
```

Phản hồi minh họa:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "sub": "user-782",
  "name": "Nguyễn Thị Lan",
  "email": "lan@example.test",
  "email_verified": true
}
```

**Access token** là credential để gọi UserInfo; **ID Token** không được dùng thay thế làm Bearer token cho endpoint này.

Đối với Spring Security Servlet OAuth2 Login, việc gọi UserInfo thông thường được thực hiện qua thành phần OAuth2UserService mà `OidcUserService` sử dụng. Ứng dụng không cần tự viết một `RestTemplate` call ở controller chỉ để đăng nhập theo flow mặc định.

### 5.1. Tham số được gửi ở đâu?

- Tham số `scope` đã được yêu cầu ở Authorization Endpoint; Provider cấp những quyền phù hợp.
- Access token được nhận từ **Token Endpoint**.
- Khi gọi UserInfo, Client đưa access token vào HTTP `Authorization` header theo cơ chế Bearer khi provider hỗ trợ.
- Response UserInfo có thể chứa claim theo OIDC Standard Claims và provider-specific claims.
- `sub` trong UserInfo phải trùng `sub` của ID Token.

Không đặt access token trong query string như `/userinfo?access_token=...`. Việc đưa credential vào URL mở rộng nguy cơ rò rỉ qua log, browser, proxy và hệ thống quan sát.

### 5.2. UserInfo response có thể là JSON hay JWT?

OIDC định nghĩa phản hồi UserInfo dạng JSON thông thường và còn có thể hỗ trợ phản hồi được ký/mã hóa theo cấu hình/provider. **Không mặc định mọi Spring Security Client tự xử lý mọi biến thể bảo vệ UserInfo mà một provider có thể phát hành**.

Nếu OP trả UserInfo dạng JWT có chữ ký/mã hóa hoặc nội dung đặc thù, cần kiểm tra hỗ trợ của Spring Security phiên bản đang dùng và yêu cầu registration/metadata tương ứng. Không bỏ qua việc kiểm tra chữ ký chỉ để có thể parse payload; cũng không biến JSON lấy từ mạng thành thông tin đã được xác minh nếu thiếu cơ chế kiểm soát danh tính.

## 6. Khi nào `OidcUserService` quyết định tải UserInfo?

Đây là điểm rất dễ gây nhầm lẫn khi tích hợp IdP.

`OidcUserService` chỉ có thể tải UserInfo khi có dữ liệu và điều kiện cần thiết, chẳng hạn:

- `ClientRegistration` cung cấp **UserInfo Endpoint URI** (qua OIDC discovery hoặc cấu hình provider).
- Access token hợp lệ, có thể được dùng để gọi UserInfo.
- Chính sách của OIDC user service trong phiên bản/cấu hình hiện tại cho phép tải UserInfo.
- Những scope được cấp và cấu hình tương ứng phù hợp với việc yêu cầu hồ sơ.
- Nhà cung cấp thực sự chấp nhận request và trả dữ liệu theo hợp đồng UserInfo.

Trong cấu hình mặc định của nhiều phiên bản Spring Security, service xem xét các scope chuẩn liên quan hồ sơ như **`profile`, `email`, `address`, `phone`** khi quyết định có gọi UserInfo hay không. Khả năng tùy biến điều kiện tải phụ thuộc API của phiên bản Spring Security đang sử dụng.

### 6.1. Scope `openid` không đồng nghĩa luôn gọi UserInfo

Ví dụ:

```yaml
scope:
  - openid
```

Cấu hình này yêu cầu **đăng nhập OIDC**, nhưng không tự khẳng định cần tải đầy đủ hồ sơ. Trong các cấu hình mặc định phổ biến, nếu không có scope liên quan hồ sơ hoặc không có endpoint, UserInfo có thể **không được gọi**.

Nếu ứng dụng cần tên và email:

```yaml
scope:
  - openid
  - profile
  - email
```

Lúc đó service có thể tải UserInfo nếu provider công bố endpoint và các điều kiện khác thỏa mãn. Tuy nhiên, **scope được yêu cầu không bảo đảm claim sẽ xuất hiện**. Để biết chắc hành vi, cần đối chiếu scope thực sự được cấp, metadata và chính sách của provider.

### 6.2. Các scope hồ sơ OIDC phổ biến

| Scope | Claim thường được yêu cầu | Lưu ý |
|---|---|---|
| `openid` | Phát sinh yêu cầu xác thực OIDC và ID Token | Không phải lời hứa cung cấp đầy đủ profile |
| `profile` | `name`, `given_name`, `family_name`, `picture`, `locale`, `preferred_username`, ... | Claim có thể thiếu hoặc provider không công bố |
| `email` | `email`, `email_verified` | Email có thể thiếu, thay đổi hoặc chưa được xác minh |
| `address` | `address` | Thường là object có nhiều trường con |
| `phone` | `phone_number`, `phone_number_verified` | Không chứng minh đã dùng số điện thoại làm MFA |

Ví dụ ứng dụng chỉ cần hiển thị tên/email không nhất thiết nên xin `address` và `phone`. Áp dụng **nguyên tắc dữ liệu tối thiểu** để tránh truy cập thông tin người dùng vượt nhu cầu.

### 6.3. ID Token có `name` rồi thì có nhất thiết cần UserInfo?

Không. Nếu nhà cung cấp đã đưa đủ claim cần thiết vào ID Token và quy trình xác minh OIDC thành công, ứng dụng có thể không cần thêm một HTTP request chỉ để lấy trùng dữ liệu. Tuy nhiên, **quyết định gọi UserInfo là hành vi của OidcUserService theo cấu hình**, không tự động biến mất chỉ vì bạn nhìn thấy `name` trong ID Token.

Nếu cần giảm độ trễ hoặc tránh phụ thuộc endpoint, hãy xem điểm tùy biến của phiên bản Spring Security và khả năng provider. Không chặn UserInfo một cách mù quáng khi ứng dụng thật sự phụ thuộc claim chỉ tồn tại ở đó.

## 7. Kiểm tra `sub`: ràng buộc UserInfo với ID Token

**Đây là một ràng buộc bảo mật quan trọng nhất của OIDC UserInfo.**

Theo OpenID Connect Core, claim **`sub`** trong phản hồi UserInfo **phải giống chính xác** subject identifier trong ID Token. Client cần xác minh điều kiện đó; nếu không trùng, **không được sử dụng UserInfo response**.

Ví dụ đúng:

```text
ID Token:
  iss = https://id.example.test
  sub = user-782

UserInfo:
  sub = user-782

=> Cùng subject theo OP
```

Ví dụ sai:

```text
ID Token:
  iss = https://id.example.test
  sub = user-782

UserInfo:
  sub = user-999

=> Mismatch: phải từ chối dữ liệu UserInfo
```

Vấn đề không phải chỉ hiển thị sai tên. Nếu Client tin UserInfo thuộc người khác, kẻ tấn công có thể lợi dụng sự nhầm lẫn để đánh tráo hồ sơ, email hoặc quyền của người dùng.

### 7.1. Tại sao email không thay thế `sub`?

Giả sử:

```json
{
  "sub": "user-782",
  "email": "lan@example.test"
}
```

Email có thể đổi, không tồn tại, không xác minh, hoặc bị tái sử dụng. Trong OIDC, định danh ổn định cần dựa vào **issuer và subject**:

```text
(iss, sub)
```

Ví dụ:

```text
("https://id.example.test/realms/company", "user-782")
```

Khi hỗ trợ nhiều OP hoặc nhiều tenant, chỉ dùng `sub` trần cũng chưa đủ: hai issuer khác nhau có thể cấp cùng một giá trị `sub` cho hai chủ thể hoàn toàn khác nhau.

### 7.2. Không “tự sửa” `sub` để bỏ qua lỗi

Nếu UserInfo trả subject không trùng ID Token, **không được** viết code:

```java
// SAI: sửa claim nhận từ mạng để ép cho giống ID Token.
userInfoClaims.put("sub", idToken.getSubject());
```

Cách đó che mất lỗi định danh và vô hiệu hóa cơ chế bảo vệ. Cần điều tra provider, token, cấu hình tenant hoặc UserInfo endpoint bị trỏ sai. Không bỏ qua exception hoặc lấy mọi claim khác từ response sai subject.

### 7.3. Spring Security giúp xác minh thế nào?

Trong đường đi OIDC Login thông thường, `OidcUserService` kiểm tra UserInfo response gắn với ID Token subject. Khi tùy biến service hoặc tự thay nội bộ UserInfo loader, **phải duy trì các kiểm tra bảo mật** mà framework thực hiện.

Không coi một custom implementation đơn giản “HTTP GET rồi Map JSON thành user” là tương đương `OidcUserService` mặc định nếu nó bỏ qua đối chiếu `sub` và các điều kiện OIDC.

## 8. Từ `OidcUserInfo` đến `OidcUser`

Khi đủ điều kiện, service đưa ID Token và UserInfo vào một `OidcUser`, thường là `DefaultOidcUser`. Principal này cho ứng dụng giao diện truy cập:

- `getIdToken()`: ID Token được lưu trong principal.
- `getUserInfo()`: dữ liệu UserInfo nếu đã tải; có thể là `null`.
- `getClaims()`: tập claim do principal OIDC biểu diễn, có thể tổng hợp từ ID Token và UserInfo.
- `getSubject()`: subject theo OIDC.
- `getAuthorities()`: các `GrantedAuthority` sau khi Spring Security tạo/mapping.
- `getName()`: tên principal theo attribute được cấu hình, thường dựa trên `sub`.

### 8.1. Một ví dụ so sánh ba nguồn

ID Token:

```json
{
  "iss": "https://id.example.test",
  "sub": "u-123",
  "aud": "spring-client",
  "iat": 1794791100,
  "exp": 1794794700
}
```

UserInfo:

```json
{
  "sub": "u-123",
  "name": "Nguyễn Thị Lan",
  "email": "lan@example.test",
  "email_verified": true
}
```

Principal trong ứng dụng:

```text
OidcUser:
  subject = u-123
  idToken = {iss, sub, aud, iat, exp, ...}
  userInfo = {sub, name, email, email_verified}
  claims = dữ liệu OIDC mà Spring cung cấp từ các nguồn tương ứng
  authorities = tập GrantedAuthority theo cấu hình xác thực
```

Không phụ thuộc vào thứ tự merge của các claim khi một tên xuất hiện ở cả ID Token và UserInfo với giá trị khác nhau. Nếu dự án cần biết rõ một trường đến từ đâu, hãy đọc **riêng `getIdToken()` và `getUserInfo()`**, rồi quy định cách sử dụng nhất quán.

### 8.2. `getUserInfo()` có thể là null

Một lỗi phổ biến:

```java
// Có thể NullPointerException nếu không có UserInfo.
String email = user.getUserInfo().getEmail();
```

Cách đọc an toàn:

```java
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

String emailFromUserInfo(OidcUser user) {
    OidcUserInfo userInfo = user.getUserInfo();
    if (userInfo == null) {
        return null;
    }
    return userInfo.getClaimAsString("email");
}
```

Không có `OidcUserInfo` **không tự động có nghĩa đăng nhập lỗi**. Có thể provider không công bố endpoint, service không cần tải hoặc dữ liệu đã đủ trong ID Token.

### 8.3. Địa chỉ, điện thoại và giá trị Boolean

Một UserInfo response có thể chứa:

```json
{
  "sub": "u-123",
  "email": "lan@example.test",
  "email_verified": true,
  "phone_number": "+84901234567",
  "phone_number_verified": false,
  "address": {
    "formatted": "12 Đường A, Thành phố Hồ Chí Minh",
    "locality": "Thành phố Hồ Chí Minh",
    "country": "VN"
  }
}
```

Lưu ý về kiểu dữ liệu:

- `email_verified` và `phone_number_verified` là **Boolean** khi được trả đúng chuẩn; có thể vắng mặt.
- `address` là **object**, không phải luôn là String.
- `phone_number` là dữ liệu cá nhân; không nên hiển thị/log nếu không có mục đích.
- Có số điện thoại không đồng nghĩa người dùng đã làm MFA.
- Một provider không nhất thiết có đủ mọi claim trong phạm vi đã cấp.

Kiểm tra `Boolean.TRUE.equals(value)` khi chính sách nghiệp vụ yêu cầu provider đã xác minh một thuộc tính; không nên coi việc thiếu claim giống với một lời khẳng định chắc chắn từ provider.

## 9. Đọc thông tin OIDC trong Spring MVC

Ứng dụng có thể nhận principal bằng `@AuthenticationPrincipal` sau khi OAuth2 Login thành công:

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        if (user == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("subject", user.getSubject());
        result.put("issuer", user.getIdToken().getIssuer().toString());

        String displayName = user.getClaimAsString("name");
        if (displayName != null) {
            result.put("displayName", displayName);
        }

        String email = user.getClaimAsString("email");
        if (email != null) {
            result.put("email", email);
        }

        Boolean emailVerified = user.getClaimAsBoolean("email_verified");
        if (emailVerified != null) {
            result.put("emailVerified", emailVerified);
        }

        OidcUserInfo userInfo = user.getUserInfo();
        result.put("userInfoLoaded", userInfo != null);
        return result;
    }
}
```

Ví dụ phản hồi:

```json
{
  "subject": "user-782",
  "issuer": "https://id.example.test/realms/company",
  "displayName": "Nguyễn Thị Lan",
  "email": "lan@example.test",
  "emailVerified": true,
  "userInfoLoaded": true
}
```

Đây là endpoint **chỉ dành cho người đã xác thực**; cần đặt quy tắc `authenticated()` trong SecurityFilterChain. Với môi trường production, không cần trả `issuer` hay `userInfoLoaded` nếu UI không dùng tới. Không bao giờ trả toàn bộ `user.getClaims()` cho mọi frontend một cách mặc định, vì claim có thể chứa dữ liệu cá nhân hoặc thông tin nội bộ không cần thiết.

### 9.1. Phân biệt nguồn của từng claim khi cần debug

```java
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

void inspectSources(OidcUser user) {
    Object idTokenEmail = user.getIdToken().getClaim("email");

    OidcUserInfo userInfo = user.getUserInfo();
    Object userInfoEmail =
        userInfo == null ? null : userInfo.getClaim("email");

    // Chỉ minh họa nguồn dữ liệu, không in email thật ra log.
    boolean inIdToken = idTokenEmail != null;
    boolean inUserInfo = userInfoEmail != null;
}
```

Cách này giúp xác định “email có trong ID Token”, “email đến từ UserInfo”, hoặc “cả hai đều thiếu”. Trong log vận hành, nên ghi **sự có mặt/thiếu claim** thay vì giá trị PII.

## 10. Cấu hình Spring Boot để dùng OIDC UserInfo

Một `ClientRegistration` điển hình:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company:
            issuer-uri: https://id.example.test/realms/company
```

Giải thích:

- `openid` xác định yêu cầu OIDC.
- `profile`, `email` yêu cầu nhóm claim liên quan hồ sơ.
- `issuer-uri` giúp Spring tìm metadata của OpenID Provider, gồm các endpoint và JWKS khi provider hỗ trợ discovery.
- `client-id` và `client-secret` thuộc registration riêng của ứng dụng, không phải dữ liệu UserInfo.
- `redirect-uri` là callback để hoàn tất authorization code flow, không phải UserInfo Endpoint.

Provider công bố metadata tại một đường dẫn well-known phù hợp với issuer, ví dụ với Keycloak realm:

```text
https://id.example.test/realms/company/.well-known/openid-configuration
```

Nội dung có thể chứa:

```json
{
  "issuer": "https://id.example.test/realms/company",
  "authorization_endpoint": "https://id.example.test/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://id.example.test/realms/company/protocol/openid-connect/token",
  "userinfo_endpoint": "https://id.example.test/realms/company/protocol/openid-connect/userinfo",
  "jwks_uri": "https://id.example.test/realms/company/protocol/openid-connect/certs"
}
```

Các URL chỉ để minh họa. Spring không thể tự suy ra UserInfo Endpoint đáng tin nếu metadata sai hoặc bị giới hạn. Cần kiểm tra issuer và cấu hình provider thực tế.

### 10.1. Bật OAuth2 Login

Với ứng dụng Spring MVC/Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Khi login OIDC thành công, ứng dụng có thể truy cập `OidcUser` trong SecurityContext. Không cần viết custom `OidcUserService` nếu mặc định đã đáp ứng đúng provider và nhu cầu đọc claim.

### 10.2. Nếu provider không hỗ trợ discovery

Khi provider cho phép tích hợp OIDC nhưng không cung cấp metadata mà Spring có thể tự tìm, có thể cấu hình các endpoint thủ công:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          manual-oidc:
            provider: custom-op
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          custom-op:
            authorization-uri: https://op.example.test/oauth2/authorize
            token-uri: https://op.example.test/oauth2/token
            jwk-set-uri: https://op.example.test/oauth2/keys
            user-info-uri: https://op.example.test/oauth2/userinfo
            user-name-attribute: sub
```

Các endpoint phải lấy từ **tài liệu/đăng ký nhà cung cấp đáng tin** và thống nhất issuer/JWK/signing algorithms với ID Token thực tế. Không tự coi một OAuth2 provider có `/userinfo` là OIDC provider nếu nó không phát hành và xác minh ID Token theo tiêu chuẩn.

Một cấu hình sai UserInfo endpoint có thể làm login lỗi hoặc trả thông tin của sai hệ thống. Với OIDC provider có discovery chính xác, `issuer-uri` vẫn là cách cấu hình thường dễ bảo trì hơn.

## 11. Tùy biến `OidcUserService` qua `userInfoEndpoint`

Nhiều ứng dụng chỉ cần behavior mặc định. Khi cần bổ sung logic cho user principal — ví dụ ánh xạ role từ hệ thống nghiệp vụ hoặc kiểm soát các trường được hiển thị — Spring Security cho phép cung cấp một `OAuth2UserService<OidcUserRequest, OidcUser>` riêng.

Cấu hình Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser> customOidcUserService)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(userInfo -> userInfo
                    .oidcUserService(customOidcUserService)
                )
            );

        return http.build();
    }
}
```

Trong mã Java, interface `OAuth2UserService` nằm ở package `org.springframework.security.oauth2.client.userinfo`. Dù tên method DSL chứa `userInfoEndpoint`, service tùy biến vẫn nằm trong flow xử lý **OIDC user principal**, không phải một HTTP controller.

### 11.1. Đừng thay toàn bộ flow khi chỉ muốn thêm logic nhỏ

Cách phù hợp là **ủy quyền việc xử lý OIDC mặc định** cho một `OidcUserService`, rồi chỉ thay đổi phần cần thiết.

Ví dụ dưới đây xây dựng thêm authorities từ một **nguồn quyền nội bộ tin cậy**. Những API lookup là abstraction do ứng dụng triển khai, không phải tính năng có sẵn của Spring Security.

```java
import java.util.HashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class EnrichingOidcUserService
        implements OAuth2UserService<OidcUserRequest, OidcUser> {

    private final OidcUserService delegate = new OidcUserService();
    private final InternalEntitlementService entitlements;

    public EnrichingOidcUserService(InternalEntitlementService entitlements) {
        this.entitlements = entitlements;
    }

    @Override
    public OidcUser loadUser(OidcUserRequest request) {
        // Giữ cơ chế OIDC/UserInfo của Spring Security, gồm kiểm tra sub.
        OidcUser original = delegate.loadUser(request);

        String issuer = original.getIdToken().getIssuer().toString();
        String subject = original.getSubject();

        Set<GrantedAuthority> authorities =
            new HashSet<>(original.getAuthorities());

        // Nguồn quyền nội bộ phải được xác thực và quản trị độc lập.
        if (entitlements.isApplicationAdmin(issuer, subject)) {
            authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
        }

        if (original.getUserInfo() == null) {
            return new DefaultOidcUser(authorities, original.getIdToken());
        }

        return new DefaultOidcUser(
            authorities,
            original.getIdToken(),
            original.getUserInfo()
        );
    }

    public interface InternalEntitlementService {
        boolean isApplicationAdmin(String issuer, String subject);
    }
}
```

Đăng ký bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

@Bean
OAuth2UserService<OidcUserRequest, OidcUser> customOidcUserService(
        EnrichingOidcUserService.InternalEntitlementService entitlements) {
    return new EnrichingOidcUserService(entitlements);
}
```

Điều kiện để ví dụ hoạt động: dự án phải có một triển khai `InternalEntitlementService` thật sự, chẳng hạn service truy xuất bảng thành viên/role của ứng dụng với cơ chế xác thực và authorization phù hợp. Không suy ra `ROLE_ADMIN` chỉ vì UserInfo có email domain công ty hoặc một claim tùy ý do người dùng có thể thay đổi.

### 11.2. Vì sao phải giữ delegate?

`OidcUserService` mặc định chịu trách nhiệm quan trọng cho OIDC UserInfo, gồm logic tải dữ liệu và kiểm tra tính nhất quán chủ thể. Khi custom code chỉ cần gán role, cách ủy quyền giúp không vô tình bỏ sót hành vi bảo mật.

Nếu thay bằng một implementation tự gọi `/userinfo` và tự tạo `OidcUser`, lập trình viên phải xử lý thêm rất nhiều khía cạnh: HTTP errors, token type, claim types, subject matching, security exceptions và tương thích phiên bản. Không nên làm điều đó chỉ để bổ sung một quyền nội bộ.

### 11.3. Đừng trộn claim từ nguồn không tin cậy vào authorities

Ví dụ nguy hiểm:

```java
// KHÔNG NÊN: dùng email/claim profile làm bằng chứng quyền admin.
if (user.getClaimAsString("email").endsWith("@company.test")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
```

Email có thể thiếu, không được xác minh, thay đổi, hoặc provider không áp dụng chính sách tổ chức mà ứng dụng giả định. Ngay cả `email_verified=true` không tự chứng minh tư cách nhân viên hay quyền quản trị. Hãy dùng một hệ quyền đã được quản lý, với khóa liên kết danh tính ổn định `(iss, sub)`.

## 12. Tùy biến bước gọi UserInfo khi provider đặc thù

`OidcUserService` có thể ủy quyền việc tải UserInfo cho một `OAuth2UserService<OAuth2UserRequest, OAuth2User>` bên trong. Ở những phiên bản Spring Security phù hợp, có thể thay thành phần này bằng `setOauth2UserService(...)` khi cần HTTP client settings hoặc chuẩn hóa dữ liệu từ một provider hợp lệ.

Ví dụ cấu hình một delegate mặc định cho OIDC:

```java
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;

OidcUserService service = new OidcUserService();

DefaultOAuth2UserService userInfoLoader =
    new DefaultOAuth2UserService();

service.setOauth2UserService(userInfoLoader);
```

Ví dụ chỉ minh họa **điểm mở rộng**; khi không có tùy biến, việc tạo `DefaultOAuth2UserService` mới như trên không đem lại lợi ích đáng kể.

Các nhu cầu tùy biến có thể gồm:

- Giới hạn timeout kết nối tới UserInfo Endpoint trong hạ tầng có yêu cầu SLO cụ thể.
- Tương thích với một kiểu HTTP response được provider hỗ trợ nhưng cần chuyển đổi có kiểm soát.
- Áp dụng cơ chế telemetry chỉ ghi metadata, không ghi token hoặc PII.
- Chọn cách xử lý một endpoint đặc thù mà provider công bố.

**Không** dùng custom loader để biến UserInfo response sai `sub` thành hợp lệ. Việc so sánh subject vẫn phải được thực hiện đúng. Nếu provider trả dữ liệu không theo OIDC, cần xử lý lỗi tích hợp với provider chứ không tự gỡ chốt bảo mật.

### 12.1. UserInfo không phải lúc nào cũng cần tải

Một số phiên bản Spring Security cho phép cấu hình điều kiện quyết định khi nào tải UserInfo hoặc các scope được coi là có quyền truy cập. **Tên method và hành vi mặc định thay đổi theo nhánh phiên bản**, vì vậy trước khi sử dụng các API tùy biến như chính sách retrieve UserInfo, cần kiểm tra Javadoc của **đúng bản Spring Security** đang dùng.

Nếu nhà cung cấp không có UserInfo Endpoint mà vẫn phát hành ID Token hợp lệ, không nên cố tạo UserInfo URI giả để lấy thêm claim. Nếu ứng dụng thật sự cần dữ liệu hồ sơ, hãy xác định cách lấy dữ liệu được OP/API công bố và quyền token cần thiết.

### 12.2. Giới hạn thời gian gọi UserInfo

HTTP request UserInfo xảy ra trong quá trình đăng nhập. Nếu endpoint chậm hoặc không phản hồi, người dùng có thể thấy login kéo dài hoặc thất bại dù Token Endpoint đã trả token.

Vì vậy trong hệ thống production, cần xem xét:

- Timeout kết nối và đọc dữ liệu phù hợp.
- Retry có giới hạn và chỉ khi an toàn.
- Circuit breaker/telemetry khi hợp lý.
- Phân biệt lỗi tạm thời 5xx với lỗi xác thực 401/403.
- Chính sách có thể cho phép đăng nhập bằng ID Token khi UserInfo không cần thiết, nhưng phải được thiết kế rõ ràng.
- Không nuốt lỗi `sub` mismatch hoặc lỗi xác minh ID Token để “giữ trải nghiệm”.

Không lặp request UserInfo vô hạn nếu token không có quyền hoặc provider từ chối. Cũng không nên tự động loại bỏ UserInfo khỏi bước login khi những claim của nó là điều kiện để ứng dụng ra quyết định quan trọng.

## 13. Ánh xạ claim và quyền: phân biệt authentication với authorization

Sau khi service trả `OidcUser`, Spring có thể tạo các authorities như `OidcUserAuthority` và những scope authorities phù hợp với cơ chế OAuth2 Login. Nhưng **OIDC `profile`, `email`, `address`, `phone` không tự gán quyền kinh doanh**.

Cần tách ba tầng:

| Tầng | Đầu vào | Kết luận được phép |
|---|---|---|
| **Authentication** | ID Token đã xác minh | Có một chủ thể `(iss, sub)` đã xác thực theo OP |
| **Profile** | ID Token/UserInfo claims | Dữ liệu hồ sơ mà OP đã chia sẻ |
| **Authorization** | Vai trò/phân quyền được quản trị theo chính sách ứng dụng | Người dùng có được làm hành động `X` hay không |

Ví dụ:

```text
ID Token: sub = user-782
UserInfo: email = lan@example.test, email_verified = true
Database ứng dụng:
  (iss, sub) -> accountId = 1001
  accountId 1001 -> roles = [READER]
```

Ứng dụng có thể hiển thị email từ UserInfo và chỉ cấp quyền `READER` theo database. Không gán `ADMIN` chỉ từ email.

### 13.1. Claim tùy biến của provider có thể dùng được không?

Có thể, nếu hợp đồng và mức tin cậy của provider cho phép. Một số IdP doanh nghiệp đưa claim `groups`, `roles` hoặc `department` vào token hay UserInfo. Tuy nhiên, cần xác định:

- Claim được phát hành bởi issuer nào?
- Claim lấy từ ID Token đã xác minh hay UserInfo đã kiểm tra subject?
- Provider nào được phép cấp giá trị này?
- Cơ chế cập nhật hoặc thu hồi quyền có đủ nhanh?
- Có ánh xạ tenant và application client đúng không?
- Quyền trong claim có đúng nghĩa với quyền nghiệp vụ của ứng dụng không?

Một claim String chứa `"admin"` không nên mặc nhiên trở thành `ROLE_ADMIN` nếu chưa có hợp đồng ủy quyền và ánh xạ được kiểm soát.

## 14. UserInfo trong ứng dụng có nhiều provider

Một ứng dụng có thể hỗ trợ Google OIDC, Keycloak OIDC và GitHub OAuth2 Login:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope: [openid, profile, email]

          company:
            provider: keycloak-company
            client-id: ${COMPANY_CLIENT_ID}
            client-secret: ${COMPANY_CLIENT_SECRET}
            scope: [openid, profile, email]

          github:
            client-id: ${GITHUB_CLIENT_ID}
            client-secret: ${GITHUB_CLIENT_SECRET}
            scope: [read:user, user:email]

        provider:
          keycloak-company:
            issuer-uri: https://id.example.test/realms/company
```

Trong ví dụ này:

- Google/Keycloak với `openid` theo OIDC có thể tạo `OidcUser` và đi qua `OidcUserService`.
- GitHub OAuth App thông thường dùng OAuth2 login, principal có thể là `OAuth2User` chứ không phải `OidcUser`.
- Địa chỉ UserInfo, tên claim và chính sách truy cập của mỗi provider khác nhau.
- Không ép mọi `Authentication#getPrincipal()` thành `OidcUser` khi ứng dụng hỗ trợ cả OAuth2 không OIDC.

### 14.1. Phân biệt principal bằng kiểu và registration ID

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;

void describe(Authentication authentication) {
    if (!(authentication instanceof OAuth2AuthenticationToken oauth)) {
        return;
    }

    String registrationId = oauth.getAuthorizedClientRegistrationId();
    OAuth2User principal = oauth.getPrincipal();

    if (principal instanceof OidcUser oidc) {
        String issuer = oidc.getIdToken().getIssuer().toString();
        String subject = oidc.getSubject();
        // Dùng (issuer, subject) làm khóa danh tính OIDC.
    } else {
        String providerSpecificId = principal.getName();
        // Ánh xạ ID theo provider/registration đã được tin cậy.
    }
}
```

Ví dụ là một method minh họa; biến local không được log bừa bãi trong production. Nếu tài khoản OAuth2 không OIDC đến từ GitHub, hãy dùng provider và ID do GitHub cấp theo hợp đồng của API; không tự tạo issuer OIDC giả chỉ để thống nhất dữ liệu.

## 15. Claim có thể cũ: UserInfo không phải tự động đồng bộ liên tục

`OidcUserService` thường được gọi trong **quá trình đăng nhập** hoặc xác thực qua OAuth2/OIDC theo flow mà Spring kích hoạt. Khi HTTP session đã được thiết lập, principal có thể tồn tại trong session. Điều đó có nghĩa:

- Người dùng đổi tên trên OP sau khi đăng nhập nhưng giao diện vẫn hiển thị tên cũ.
- Email mới được xác minh ở IdP nhưng `OidcUser` trong session còn snapshot cũ.
- Một role nội bộ bị thu hồi nhưng session vẫn có authority được gán tại lúc đăng nhập nếu ứng dụng không có chiến lược cập nhật.
- Access token có thể hết hạn trong khi HTTP session vẫn còn; hai vòng đời khác nhau.

### 15.1. Nếu cần dữ liệu hồ sơ cập nhật thì làm gì?

Tùy nhu cầu:

1. **Dữ liệu chỉ dùng cho hiển thị:** có thể cập nhật khi người dùng đăng nhập lại hoặc theo TTL hồ sơ do ứng dụng quy định.
2. **Dữ liệu cần đồng bộ định kỳ:** dùng cơ chế backend được cho phép, API thích hợp và quản lý access/refresh token an toàn.
3. **Quyền nhạy cảm:** nên kiểm tra tại nguồn quyền tin cậy ở thời điểm tác vụ, không phụ thuộc duy nhất role snapshot trong session.
4. **Dữ liệu cá nhân nghiệp vụ:** xác định hệ thống nào là nguồn sự thật; không đồng nhất UserInfo profile với hồ sơ giao hàng/hóa đơn.

Không tự gọi UserInfo ở mỗi request một cách mặc định: việc này tăng độ trễ, rate limit, khả năng thất bại và chi phí. Nếu cần refresh token để gọi UserInfo sau login, hãy dùng hạ tầng `OAuth2AuthorizedClient`/`OAuth2AuthorizedClientManager` phù hợp.

### 15.2. UserInfo và `OAuth2AuthorizedClient` là hai việc khác nhau

`OAuth2AuthorizedClient` lưu liên kết ClientRegistration với access token và có thể refresh token đã cấp. `OidcUser` chứa thông tin người dùng đã được xác thực. Cả hai liên quan trong login nhưng không phải một:

```text
OAuth2AuthorizedClient
  -> registration
  -> access token
  -> refresh token (nếu được cấp)

OidcUser
  -> ID Token
  -> UserInfo (nếu tải)
  -> claims / authorities / subject
```

Làm mới access token qua `OAuth2AuthorizedClientManager` **không tự động cập nhật mọi claim** trong `OidcUser` đã lưu trong HTTP session. Nếu ứng dụng muốn cập nhật principal, cần một chiến lược rõ ràng, không chỉ gọi refresh rồi nghĩ hồ sơ tự thay đổi.

## 16. Lỗi thường gặp ở UserInfo và cách khoanh vùng

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Đăng nhập OIDC thành công nhưng `getUserInfo() == null` | Endpoint không được công bố, service không gọi theo scope/chính sách | Kiểm tra discovery metadata, scope được cấp, phiên bản `OidcUserService` |
| Có `openid` nhưng thiếu `email` | Không xin `email`, IdP không công bố hoặc email nằm ở UserInfo chưa được gọi | Kiểm tra scope, ID Token và UserInfo riêng |
| UserInfo trả `401 Unauthorized` | Access token không hợp lệ, sai audience/loại token hoặc provider không cho phép UserInfo | Kiểm tra Token Endpoint, UserInfo URI, token sử dụng và quyền |
| UserInfo trả `403 Forbidden` | Token thiếu scope/quyền hoặc chính sách IdP từ chối | Kiểm tra quyền được cấp và cấu hình consent |
| UserInfo báo `sub` mismatch | UserInfo và ID Token thuộc chủ thể khác, sai tenant/endpoint hoặc provider lỗi | **Không dùng dữ liệu**; kiểm tra issuer, endpoint, token và cấu hình Client |
| UserInfo trả HTML/XML thay vì JSON | URL sai hoặc provider trả trang lỗi/proxy | Kiểm tra Content-Type, endpoint và lỗi HTTP |
| UserInfo chậm làm login chậm | Endpoint mạng chậm, timeout chưa phù hợp, retry quá nhiều | Đặt timeout, quan sát latency, kiểm tra availability |
| `OidcUser` có `name` nhưng `getUserInfo()` null | Name có thể nằm trong ID Token | Đọc nguồn ID Token/UserInfo riêng thay vì đoán |
| `email_verified` bị hiểu là String | Provider trả kiểu sai hoặc custom mapper ép kiểu | Kiểm tra Boolean, chính sách mapping |
| `address` bị ép về String | Claim chuẩn là object | Xử lý map/structured claim |
| Login Google được nhưng GitHub cast `OidcUser` lỗi | GitHub OAuth App không dùng OIDC principal | Xử lý theo kiểu `OAuth2User`/`OidcUser` |
| Custom service làm mất authorities/scope | Tạo `DefaultOidcUser` mới nhưng không giữ authorities cũ | Delegate và kế thừa `getAuthorities()` |
| Đăng nhập thất bại sau khi tùy biến user loader | Custom HTTP/claim mapping bỏ kiểm tra hoặc thay endpoint sai | Kiểm tra cấu hình delegate và lỗi chính xác |
| Email/role không cập nhật khi session còn | `OidcUser` là snapshot lúc login | Thiết kế đồng bộ hồ sơ và phân quyền riêng |
| API nghiệp vụ trả 401 sau login | Access token hết hạn hoặc không đúng resource | Phân biệt refresh access token với tải UserInfo |

### 16.1. Thứ tự tìm lỗi hợp lý

1. **Xác nhận OIDC Login có thành công không.** Nếu ID Token không qua chữ ký/issuer/audience/nonce, UserInfo chưa phải vấn đề chính.
2. **Xác nhận ClientRegistration.** `registrationId`, issuer và metadata của provider có đúng không?
3. **Kiểm tra UserInfo Endpoint.** Metadata có `userinfo_endpoint` không, host và URL có đúng không?
4. **Kiểm tra scope được cấp.** Không chỉ nhìn các scope đã cấu hình trong YAML.
5. **Xác định UserInfo có được gọi không.** Quan sát HTTP status/latency ở mức an toàn, tránh log token.
6. **Nếu đã gọi, kiểm tra response.** Content-Type, HTTP status, cấu trúc JSON, claim `sub`.
7. **Đối chiếu `sub` với ID Token.** Nếu mismatch, dừng dùng response và sửa vấn đề nguồn.
8. **Kiểm tra ứng dụng đọc claim đúng nguồn/kiểu chưa.** `email_verified` Boolean, `address` object, `getUserInfo()` có thể null.
9. **Nếu claim dùng cho quyền, xác minh nguồn thẩm quyền.** Không nhầm thông tin hồ sơ với authorization.

### 16.2. Debug nhưng không làm lộ thông tin nhạy cảm

Trong môi trường phát triển có thể bật log Spring Security ở mức phù hợp:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Những dữ liệu có thể hữu ích khi chẩn đoán mà không phải ghi toàn bộ token:

```text
registrationId=company
userinfoEndpointConfigured=true
userinfoRequestAttempted=true
userinfoHttpStatus=200
userinfoSubMatchesIdToken=true
userinfoContainsEmail=true
```

Không log `Authorization: Bearer <token>`, raw ID Token, refresh token, userinfo JSON đầy đủ, cookie phiên, email, số điện thoại hoặc địa chỉ. Nếu cần chia sẻ ví dụ với nhóm hỗ trợ, tạo dữ liệu giả và che toàn bộ credentials.

## 17. Bảo mật và quyền riêng tư khi tải hồ sơ

### 17.1. Nguyên tắc tối thiểu hóa dữ liệu

Cần hỏi trước khi xin scope: chức năng nào thật sự cần claim đó?

- Trang chào mừng có thể chỉ cần `name` hoặc `preferred_username`.
- Gửi email thông báo cần `email` và có thể cần trạng thái `email_verified`.
- Giao hàng có thể cần địa chỉ, nhưng địa chỉ UserInfo chưa chắc là địa chỉ giao hàng được xác nhận.
- Số điện thoại có thể là PII nhạy cảm, không xin nếu không có mục đích sử dụng.

Đừng tự động đưa `user.getClaims()` vào response cho frontend; chỉ lấy các trường phục vụ giao diện hoặc nghiệp vụ theo chính sách.

### 17.2. Bảo vệ UserInfo Endpoint và access token

UserInfo phải được gọi qua kết nối HTTPS và tới endpoint của provider đã được cấu hình/khám phá từ nguồn đáng tin.

- Không cho người dùng tự đưa một URL UserInfo bất kỳ để backend gọi (nguy cơ SSRF).
- Không gửi access token tới endpoint ngoài allowlist provider.
- Không đưa access token lên URL query.
- Không sao chép token vào log hoặc hệ thống quan sát.
- Khi dùng custom loader, giữ nguyên kiểm tra subject và xử lý lỗi phù hợp.
- Không chấp nhận dữ liệu UserInfo từ issuer hoặc tenant khác một cách tùy tiện.

### 17.3. Chứng minh email và số điện thoại

Claim `email_verified=true` hoặc `phone_number_verified=true` là tuyên bố từ provider về việc họ đã thực hiện xác minh theo quy trình của họ. Nó không tự chứng minh:

- Người dùng là nhân viên đang làm việc tại một tổ chức.
- Địa chỉ email/số điện thoại không thể thay đổi.
- Người dùng đã hoàn tất MFA trong phiên đăng nhập hiện tại.
- Người dùng được phép xem dữ liệu hoặc thực hiện tác vụ quản trị.

Nếu ứng dụng dùng các claim này làm điều kiện nghiệp vụ, phải định nghĩa rõ mức tin cậy và quyết định authorization riêng.

## 18. Bài thực hành

### Bài tập 1: UserInfo có được tải khi chỉ có `openid`?

Cấu hình:

```yaml
scope: [openid]
```

Sau login, `OidcUser#getUserInfo()` trả `null`.

**Câu hỏi:** có thể kết luận OIDC Login thất bại không?

**Gợi ý đáp án:** Không. ID Token có thể đã được xác minh và principal đã được tạo; service không nhất thiết gọi UserInfo trong cấu hình này. Nếu cần profile, kiểm tra scope, metadata provider và chính sách tải của phiên bản Spring Security.

### Bài tập 2: Thiếu email trong ID Token

ID Token chỉ có `iss`, `sub`, `aud`, `exp`, `iat`. UserInfo có `email` và `email_verified`.

**Câu hỏi:** nên đọc email từ đâu?

**Gợi ý đáp án:** Sau khi Spring Security hoàn tất OIDC Login và xác minh UserInfo đúng subject, ứng dụng có thể đọc `OidcUser#getClaimAsString("email")` hoặc `getUserInfo()` nếu muốn truy nguồn. Không suy luận rằng thiếu email trong ID Token là lỗi xác thực.

### Bài tập 3: Mismatch `sub`

```text
ID Token: sub = u-100
UserInfo: sub = u-200
```

**Đáp án:** Không sử dụng UserInfo. Không ép `sub` về `u-100`, không lấy email từ response này. Cần kiểm tra access token, UserInfo Endpoint, tenant và lỗi provider.

### Bài tập 4: Provider trả số điện thoại nhưng không có trạng thái verified

UserInfo:

```json
{
  "sub": "u-100",
  "phone_number": "+84901234567"
}
```

**Đáp án:** Không mặc định số đã được xác minh. Nếu chức năng đòi số điện thoại verified, cần kiểm tra `phone_number_verified` theo Boolean và xử lý trường hợp thiếu claim.

### Bài tập 5: Tùy biến quyền từ nguồn nội bộ

Ứng dụng muốn gán `ROLE_ADMIN` cho tài khoản nội bộ, nhưng email đăng nhập có thể thay đổi.

**Gợi ý đáp án:** Dùng `(iss, sub)` liên kết tới tài khoản nội bộ và truy vấn role tại hệ quyền đáng tin. Custom `OidcUserService` có thể delegate để giữ flow UserInfo rồi bổ sung `GrantedAuthority` từ quyền nội bộ, thay vì map role theo email.

### Bài tập 6: UserInfo không cập nhật sau khi đổi profile

Người dùng đổi ảnh trên OP trong khi session ứng dụng vẫn còn.

**Gợi ý đáp án:** `OidcUser` có thể giữ snapshot từ lần login. Ứng dụng cần quyết định cơ chế cập nhật rõ ràng (đăng nhập lại, refresh profile theo TTL hoặc API phù hợp). Làm mới access token không tự động làm mới mọi claim của principal.

### Bài tập 7: Chẩn đoán độ trễ login

Token Endpoint trả nhanh nhưng tổng thời gian đăng nhập tăng 4 giây. Quan sát thấy UserInfo Endpoint thường mất 3,8 giây.

**Gợi ý đáp án:** Đo latency ở bước UserInfo, xem timeout/availability, scope cần thiết và liệu dữ liệu có thể lấy từ ID Token theo chính sách hay không. Không tắt kiểm tra `sub` hoặc xác minh ID Token để giảm thời gian.

## 19. Những điểm cần ghi nhớ

| Điều cần nhớ | Ý nghĩa thực hành |
|---|---|
| `OidcUserService` xử lý OIDC user principal | Nó nằm sau quá trình nhận và xác minh ID Token trong OAuth2 Login |
| `OidcUserRequest` chứa ID Token và access token | Access token có thể dùng gọi UserInfo; ID Token xác nhận danh tính |
| UserInfo không luôn bắt buộc | Endpoint/scope/chính sách có thể khiến service không gọi UserInfo |
| `sub` phải khớp chính xác | Không dùng UserInfo khi subject khác ID Token |
| `OidcUser#getUserInfo()` có thể null | Luôn xử lý thiếu UserInfo |
| `getClaims()` có thể chứa dữ liệu từ nhiều nguồn | Dùng `getIdToken()`/`getUserInfo()` khi cần xác định nguồn cụ thể |
| `OAuth2User` khác `OidcUser` | OAuth2 login không OIDC không mặc định có ID Token |
| Claim profile khác authority nghiệp vụ | Email hoặc `profile` không tự tạo `ROLE_ADMIN` |
| Tùy biến nên giữ delegate | Giữ cách gọi UserInfo và kiểm tra OIDC của Spring |
| UserInfo thường là snapshot lúc login | Không tự động đồng bộ hồ sơ trong suốt HTTP session |
| Access token/response chứa dữ liệu nhạy cảm | Không log token hoặc trả toàn bộ claim cho frontend |
| OIDC discovery giúp giảm cấu hình thủ công | Dùng đúng `issuer-uri`/metadata của provider đáng tin |

## 20. Tài liệu tham khảo

1. [OpenID Connect Core 1.0 — UserInfo Endpoint](https://openid.net/specs/openid-connect-core-1_0.html#UserInfo): ý nghĩa endpoint, bearer access token, claim và yêu cầu `sub`.
2. [OpenID Connect Core 1.0 — UserInfo Response](https://openid.net/specs/openid-connect-core-1_0.html#UserInfoResponse): mô hình response và đối chiếu subject với ID Token.
3. [OpenID Connect Core 1.0 — Standard Claims](https://openid.net/specs/openid-connect-core-1_0.html#StandardClaims): `profile`, `email`, `address`, `phone` và các claim chuẩn.
4. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer metadata và `userinfo_endpoint`.
5. [Spring Security Reference — OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): flow OAuth2/OIDC Login, `ClientRegistration` và `OidcUser`.
6. [Spring Security Reference — Advanced OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): tùy chỉnh user service qua `userInfoEndpoint`.
7. [Spring Security API — OidcUserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserService.html): hợp đồng `loadUser` và điểm mở rộng OIDC UserInfo.
8. [Spring Security API — OidcUserRequest](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserRequest.html): ID Token, access token và ClientRegistration.
9. [Spring Security API — OidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html): truy cập claims, ID Token và UserInfo.
10. [Spring Security API — DefaultOidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/DefaultOidcUser.html): principal OIDC mặc định.
11. [Spring Security API — DefaultOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/DefaultOAuth2UserService.html): thành phần lấy dữ liệu người dùng từ UserInfo endpoint.

**Tổng kết:** `OidcUserService` kết nối quá trình đăng nhập OIDC đã xác minh với việc lấy hồ sơ qua UserInfo. ID Token cho biết chủ thể nào đã đăng nhập, còn UserInfo cung cấp những claim hồ sơ được chia sẻ khi có quyền và endpoint phù hợp. Ứng dụng nên giữ nguyên cơ chế đối chiếu `sub`, xử lý trường hợp UserInfo vắng mặt, dùng `(iss, sub)` để liên kết danh tính, và chỉ mở rộng service khi có yêu cầu thật sự — không đánh đổi độ an toàn của OIDC lấy sự tiện lợi khi đọc profile.

# 11.13. Giới hạn việc tái sử dụng ID Token trong các luồng gọi API

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, sau khi người dùng đăng nhập thành công, ứng dụng có thể nhận cùng lúc **ID token** và **access token**. Hai token này có thể đều trông như một chuỗi JWT, đều chứa claim `iss`, `sub` và `exp`, nhưng chúng có **mục đích, audience và quy tắc kiểm tra khác nhau**.

**ID token được OpenID Provider (OP) phát hành để Relying Party (RP) tiêu thụ kết quả xác thực của End-User.** Khi ứng dụng cần gọi một API được bảo vệ, thông thường nó phải sử dụng **access token dành cho Resource Server**. Việc gửi ID token như bearer token đến API có thể tạo lỗi thiết kế về kiểm tra đối tượng nhận token, phân quyền và chống token substitution.

Sau bài học, bạn có thể:

- Phân biệt vai trò của ID token, access token, refresh token và cookie phiên ứng dụng.
- Giải thích vì sao **ID token hợp lệ tại RP không đương nhiên hợp lệ tại API**.
- Phân tích `aud`, `azp`, `iss`, `nonce`, `exp` và vì sao kiểm tra chữ ký đơn thuần chưa đủ.
- Nhận biết rủi ro **token substitution**, confused deputy, lộ claim cá nhân và tái sử dụng bearer credential.
- Sử dụng `OAuth2AuthorizedClient` trong Spring Security để lấy **access token** khi gọi API.
- Cấu hình JWT Resource Server kiểm tra issuer, audience và scope/authority của **access token**.
- Hiểu khi nào cần token exchange hoặc cơ chế ủy quyền giữa các service; không tự biến ID token thành access token.
- Xác định các giới hạn của replay protection, session và cơ chế logout.

## 1. Bài toán thực tế: sau login, phải gửi token nào đến API?

Giả sử hệ thống có ba thành phần:

- **Employee Portal**: ứng dụng web Spring Boot, đóng vai OAuth 2.0 Client và OIDC Relying Party.
- **Corporate Identity Provider**: OpenID Provider/Authorization Server, nơi nhân viên đăng nhập.
- **Orders API**: Resource Server cung cấp danh sách đơn hàng và thao tác quản lý đơn.

Portal sử dụng OIDC Authorization Code flow. Sau callback thành công, OP có thể trả:

~~~text
ID token:       eyJhbGciOi... (chỉ là ví dụ)
Access token:   eyJhbGciOi... hoặc một chuỗi opaque
Refresh token:  có thể có hoặc không, tùy grant và chính sách
~~~

Portal cần thực hiện hai nhiệm vụ khác nhau:

1. **Nhận diện người dùng đã đăng nhập tại Portal**: Spring Security xử lý và xác minh ID token, tạo principal `OidcUser` và `Authentication`.
2. **Lấy đơn hàng qua Orders API**: Portal gửi **access token được cấp cho API** trong header `Authorization: Bearer ...`.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Nhân viên
    participant B as Trình duyệt
    participant P as Employee Portal / RP
    participant OP as OpenID Provider
    participant API as Orders API / Resource Server
    U->>B: Mở Portal
    B->>P: Yêu cầu trang cần đăng nhập
    P-->>B: Chuyển hướng OIDC Authorization Code
    B->>OP: Authentication Request
    OP->>U: Xác thực / consent khi cần
    OP-->>B: Redirect cùng authorization code
    B->>P: Callback với code và state
    P->>OP: Đổi code lấy token
    OP-->>P: ID token + access token
    Note over P: Kiểm tra ID token và tạo OidcUser
    P->>API: Authorization: Bearer ACCESS_TOKEN
    Note over API: Xác minh access token và quyền API
    API-->>P: Dữ liệu đơn hàng
    P-->>B: Hiển thị kết quả
~~~

Điểm cần tránh là thay lời gọi API trong sơ đồ bằng:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <ID_TOKEN>
~~~

Trong mô hình OAuth/OIDC thông thường, đây là **sử dụng sai mục đích ID token**. Một ID token được phát hành cho `Employee Portal` không phải giấy phép gọi mọi API của doanh nghiệp.

## 2. ID token chứng minh điều gì?

### 2.1. ID token là kết quả xác thực dành cho RP

Trong OpenID Connect, ID token thường là một JWT có chữ ký do OP phát hành. Một payload ví dụ:

~~~json
{
  "iss": "https://idp.example.com/realms/company",
  "sub": "employee-1288",
  "aud": "employee-portal",
  "iat": 1800000000,
  "exp": 1800003600,
  "auth_time": 1799999900,
  "nonce": "nonce-of-authorization-request",
  "email": "alice@example.com"
}
~~~

Đây là dữ liệu minh họa, **không phải token thật** và các mốc thời gian không dùng để chạy ứng dụng.

Các claim cho biết:

| Claim | Ý nghĩa trong OIDC | Lưu ý |
|---|---|---|
| `iss` | OP đã phát hành token | RP phải tin cậy và xác minh issuer |
| `sub` | Định danh End-User trong phạm vi issuer | Khi liên kết user, thường dùng cặp `iss` + `sub` |
| `aud` | Audience nhận ID token, phải bao gồm client ID của RP | Không tự suy ra là audience của API |
| `iat` | Thời điểm phát hành token | Không đồng nghĩa thời điểm người dùng xác thực |
| `exp` | Thời điểm hết hạn token | Hạn thời gian không thay thế phân quyền |
| `auth_time` | Thời điểm người dùng được xác thực, nếu có | Dùng cho chính sách freshness |
| `nonce` | Liên kết ID token với Authentication Request khi dùng | Không phải cơ chế một lần cho lời gọi API |
| `email` | Thuộc tính hồ sơ có thể được cấp | Không phải khóa định danh bất biến hay quyền nghiệp vụ |

RP kiểm tra chữ ký hoặc cơ chế bảo vệ token theo flow, issuer, audience, thời gian hiệu lực và các điều kiện OIDC như nonce khi áp dụng.

**Giá trị của ID token nằm ở việc RP có cơ sở xác thực người dùng**, chứ không phải vì nó là một JWT có thể được mọi service giải mã.

### 2.2. ID token có thể chứa dữ liệu hồ sơ, nhưng không bắt buộc

OIDC có các scope như `openid`, `profile` và `email`. Tùy OP, các claim hồ sơ có thể có trong ID token, được trả qua UserInfo Endpoint hoặc không được cung cấp theo chính sách.

Không nên dựa vào email trong ID token để:

- Cấp toàn bộ quyền xem đơn hàng.
- Xác định người dùng thuộc tenant nào mà không đối chiếu chính sách.
- Cho phép thanh toán, phê duyệt hoặc truy cập dữ liệu khách hàng.
- Liên kết hai tài khoản từ hai issuer chỉ vì email giống nhau.

ID token chứa **thông tin xác thực và claim định danh**, không phải một bộ quyền API chuẩn hóa.

### 2.3. ID token có thể được dùng nhiều lần trong nội bộ RP?

RP có thể dùng thông tin ID token đã xác minh để:

- Xác định principal OIDC sau đăng nhập.
- Liên kết tài khoản nội bộ theo `iss` + `sub`.
- Đọc các claim đã được xử lý, nếu nghiệp vụ cần.
- Xem `auth_time`, `acr` hoặc `amr` để đánh giá chính sách xác thực khi các claim có mặt.
- Thực hiện các phần khác của giao thức OIDC có quy định riêng, ví dụ dùng `id_token_hint` trong một cơ chế logout được OP hỗ trợ.

Việc **đọc lại thông tin đã được xác thực trong RP** khác với việc **gửi ID token thô đến một API như bearer credential**.

ID token không phải một “vé truy cập vạn năng”. Khi ứng dụng chia thành nhiều backend/service, mỗi service cần mô hình tin cậy và token dành riêng cho điểm nhận đó.

## 3. So sánh ID token, access token, refresh token và session

| Đối tượng | Đối tượng sử dụng chính | Mục đích | Có dùng làm bearer credential gọi API nghiệp vụ? |
|---|---|---|---|
| **ID token** | OIDC Relying Party | Truyền kết quả xác thực End-User | **Không theo mô hình OAuth Resource Server thông thường** |
| **Access token** | Resource Server | Cho phép truy cập tài nguyên theo quyền được cấp | **Có**, nếu token phù hợp API |
| **Refresh token** | OAuth client tại token endpoint | Xin access token mới theo chính sách AS | Không |
| **Session cookie của Portal** | Browser và Portal | Duy trì phiên ứng dụng web | Không dùng thay access token cho API bên ngoài |
| **Authorization code** | Client và token endpoint | Đổi token một lần trong flow | Không |

**Không đánh giá token chỉ bằng định dạng.** ID token của OIDC là JWT, nhưng access token có thể là JWT hoặc chuỗi opaque tùy AS. Hai JWT có thể có chữ ký hợp lệ bởi cùng OP nhưng có mục đích và audience khác nhau.

### 3.1. Access token dành cho Resource Server

Một access token dạng JWT, khi AS/RS sử dụng định dạng này, có thể có payload minh họa:

~~~json
{
  "iss": "https://idp.example.com/realms/company",
  "sub": "employee-1288",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1800000000,
  "exp": 1800001800
}
~~~

Ở ví dụ:

- `iss` cho biết AS phát hành token.
- `aud` cho biết Resource Server mục tiêu.
- `scope` mô tả quyền truy cập được cấp theo cách mà AS/RS thống nhất.
- `exp` giới hạn thời gian sử dụng.
- `sub` có thể phản ánh người dùng, nhưng ngữ nghĩa phụ thuộc grant và token profile.

**Đây vẫn chỉ là payload minh họa.** API phải xác minh token thật bằng cơ chế mà AS và Resource Server đã thiết lập, không chỉ decode JSON.

### 3.2. Access token cũng không tự động cho mọi quyền

Access token hợp lệ về chữ ký và thời gian vẫn có thể bị API từ chối vì:

- Audience không phải API đang nhận.
- Thiếu `orders.read` hoặc quyền nghiệp vụ cần thiết.
- Token thuộc issuer/tenant không được tin cậy.
- Token dành cho một loại tài nguyên khác.
- Người dùng không có quyền xem đơn hàng cụ thể.

Một API đúng nên phân biệt **xác thực token** và **phân quyền hành động**.

### 3.3. Refresh token không thay thế ID token hay access token

Refresh token chỉ dành cho quá trình làm mới quyền truy cập theo chính sách của Authorization Server. Không đưa refresh token vào header `Authorization` khi gọi API nghiệp vụ.

Spring Security quản lý thông tin access/refresh token qua `OAuth2AuthorizedClient` và các thành phần quản lý token, không phải bằng cách dùng ID token làm token dự phòng.

## 4. Audience: lý do quan trọng nhất không dùng nhầm ID token

### 4.1. `aud` là “token này được phát hành cho ai?”

Giả sử cùng một OP cấp hai token:

~~~text
ID token:
  aud = employee-portal

Access token:
  aud = orders-api
  scope = orders.read
~~~

Khi Portal tiêu thụ ID token, client ID `employee-portal` là audience thích hợp theo OIDC. Khi Orders API nhận access token, nó phải kiểm tra audience dành cho mình, ví dụ `orders-api`.

Nếu Orders API chấp nhận ID token có `aud=employee-portal` chỉ vì chữ ký hợp lệ, API đã **bỏ qua ranh giới đối tượng nhận token**.

### 4.2. Chữ ký hợp lệ chưa đủ

Giả sử API chỉ làm:

~~~text
1. JWT có chữ ký hợp lệ? Có.
2. JWT chưa hết hạn? Có.
3. Cho phép request.
~~~

Cách kiểm tra này bỏ sót những câu hỏi quan trọng:

- Token do issuer mà API tin cậy phát hành không?
- **Audience có dành cho API không?**
- Đây có phải token có loại và ngữ nghĩa **access token** mà API chấp nhận?
- Scope, authority và quyền nghiệp vụ có phù hợp không?
- Token có bị thu hồi hoặc vi phạm chính sách riêng của AS/RS không?

Việc cùng dùng JWK Set của một OP **không làm mọi JWT do OP ký trở nên hoán đổi được**.

### 4.3. `azp` không cấp quyền cho API

Trong một số ID token có nhiều audience, OP có thể phát hành claim `azp` (*authorized party*) để chỉ bên được ủy quyền. Việc xuất hiện `azp` có quy tắc kiểm tra riêng trong OIDC.

Không được suy luận:

> Token có `azp=employee-portal` nên Orders API có thể tin token đó để cấp quyền.

`azp` không phải scope API và không biến ID token thành access token. API vẫn cần token với audience/loại phù hợp và quyền được cấp.

### 4.4. Nếu client ID và audience API vô tình trùng nhau thì sao?

Một hệ thống có thể cấu hình không rõ ràng khiến API và RP dùng cùng một chuỗi audience. Lúc đó kiểm tra `aud` đơn lẻ **có thể chưa đủ** để phân biệt token phục vụ đăng nhập với token phục vụ API.

Cần thiết kế rõ:

- Audience riêng của Resource Server.
- Token profile hoặc dấu hiệu phân loại token mà AS công bố và API được cấu hình kiểm tra.
- Phạm vi quyền cho API và mapping authority.
- Quy tắc issuer, client, tenant và resource riêng.
- Chính sách từ chối token không có ngữ nghĩa access token.

Với profile **JWT Access Token for OAuth 2.0** theo RFC 9068, token có quy tắc định dạng/kiểm tra riêng, gồm cách đánh dấu loại token. Tuy nhiên, **không phải mọi provider đều phát hành JWT access token theo RFC 9068**, nên không hard-code quy tắc `typ=at+jwt` cho mọi AS mà không xác nhận profile thực tế.

## 5. Những rủi ro khi dùng ID token làm API bearer token

### 5.1. Token substitution / token confusion

**Token substitution** xảy ra khi một thành phần nhận một loại token có mục đích khác như thể đó là access token hợp lệ.

Ví dụ:

1. Một client OIDC nhận ID token dành cho chính client đó.
2. Client gửi ID token đến API.
3. API chấp nhận vì chỉ kiểm tra issuer và chữ ký.
4. API cho phép truy cập dù AS chưa cấp access token dành cho API và chưa xét scope API.

Đây là lỗi ranh giới tin cậy. Một chữ ký đáng tin cậy **không đủ để xác định mục đích của token**.

### 5.2. Confused deputy

API đóng vai một bên được tin tưởng xử lý dữ liệu. Nếu API nhận chứng thư dành cho một bên khác mà không kiểm tra intended audience, nó có thể bị lợi dụng để thực hiện hành động ngoài phạm vi người gọi được cấp.

Chẳng hạn một ID token dùng để đăng nhập Portal không nên được Orders API coi là quyền đọc toàn bộ đơn hàng. Quyền đọc đơn hàng phải được thể hiện bằng cơ chế authorization mà AS/RS và ứng dụng đã thiết kế.

### 5.3. Thiếu scope hoặc quyền tài nguyên

ID token thường tập trung vào các claim như `sub`, `nonce`, `auth_time`, `acr`, `email`. Nó không có cùng hợp đồng với access token về scope và audience API.

Ngay cả khi ID token chứa một claim có tên `roles`, API không được tự suy ra claim đó cấp quyền nghiệp vụ. Cần xác định:

- Claim được phát hành theo ngữ nghĩa gì?
- Nó thuộc người dùng, client hay OP?
- API có được phép sử dụng claim đó để phân quyền không?
- Có giới hạn tenant, loại tài nguyên và hành động cụ thể không?

### 5.4. Lộ dữ liệu cá nhân không cần thiết

ID token có thể chứa email, tên, thông tin xác thực hoặc metadata người dùng mà API không cần.

Gửi ID token đến nhiều service làm tăng:

- Số thành phần có quyền nhìn thấy claim.
- Số nơi token có thể bị log hoặc lưu.
- Nguy cơ tiết lộ thông tin trong tracing và debugging.
- Khả năng token được dùng ngoài mục đích ban đầu.

Một access token dành cho API cũng cần được bảo vệ, nhưng có thể được AS thiết kế với claim và quyền **phù hợp hơn với Resource Server**.

### 5.5. Tái sử dụng bearer credential

Nếu API chấp nhận ID token như bearer token, ai lấy được chuỗi này có thể tìm cách dùng lại nó trong thời hạn token còn hiệu lực.

OIDC `nonce` không làm ID token trở thành token API dùng một lần. `exp` hạn chế thời gian nhưng không ngăn token bị phát lại trong khoảng thời gian đó.

Chi tiết về replay protection nằm ở phần tiếp theo.

## 6. Mục đích của ID token trong Spring Security OIDC Login

### 6.1. Spring Security xây `OidcUser` sau login

Trong Servlet application, một OIDC Login thành công thường tạo:

~~~text
SecurityContext
└── OAuth2AuthenticationToken
    ├── principal: OidcUser
    │   ├── idToken: OidcIdToken
    │   ├── userInfo: OidcUserInfo (nếu có)
    │   └── claims / attributes
    ├── authorities
    └── registrationId
~~~

Mục đích của ID token ở đây là giúp RP **xác thực người dùng và xây principal**. Spring Security dùng kết quả này cho việc xác thực phiên ứng dụng.

### 6.2. Ví dụ đọc danh tính OIDC

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    Profile me(@AuthenticationPrincipal OidcUser user) {
        return new Profile(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                user.getFullName());
    }

    record Profile(String issuer, String subject, String displayName) {}
}
~~~

Ví dụ giả định endpoint chỉ được truy cập sau OIDC Login. Nếu ứng dụng hỗ trợ nhiều loại authentication, cần xử lý principal theo kiểu thực tế.

`displayName` có thể vắng mặt. Khi liên kết user nội bộ, thông thường nên dùng **`iss` + `sub`**, tránh dùng email hoặc tên làm khóa duy nhất.

**Không trả nguyên `user.getIdToken().getTokenValue()` cho frontend** chỉ để hiển thị tên hay gửi tiếp sang một API. Controller có thể trả các dữ liệu hồ sơ thực sự cần thiết.

### 6.3. `SecurityContext` không phải kho access token cho API

Spring Security tách các khái niệm:

| Thành phần | Vai trò |
|---|---|
| `OidcUser` / `OidcIdToken` | Principal và thông tin kết quả xác thực OIDC |
| `SecurityContext` / `Authentication` | Trạng thái xác thực của request/phiên ứng dụng |
| `ClientRegistration` | Cấu hình OAuth client và provider |
| `OAuth2AuthorizedClient` | Kết nối registration/principal với access token và refresh token nếu có |
| `OAuth2AuthorizedClientManager` | Điều phối xin, dùng hoặc làm mới token theo cơ chế được cấu hình |

Nếu cần gọi API, hãy sử dụng **authorized client/access token** thay vì lấy ID token từ `OidcUser`.

## 7. Spring Boot: cấu hình một OIDC Client để gọi API

### 7.1. Dependency client

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

### 7.2. Client registration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company-oidc:
            issuer-uri: https://idp.example.com/realms/company
~~~

Ở ví dụ:

- `corporate` là registration ID nội bộ Spring Security.
- Scope `openid` yêu cầu OIDC Login.
- `orders.read` là scope API **giả định**, chỉ hoạt động nếu AS và Orders API thực sự hỗ trợ.
- Client secret được cung cấp từ môi trường bảo mật, không hard-code trong mã nguồn.
- Redirect URI phải khớp callback đã đăng ký tại OP.

**Yêu cầu `orders.read` không đảm bảo AS sẽ cấp token có quyền đó**; client và user có thể còn phụ thuộc consent, audience và chính sách.

### 7.3. Bật OIDC Login và OAuth client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

Ở đây:

- `oauth2Login()` phục vụ đăng nhập người dùng.
- `oauth2Client()` cung cấp hỗ trợ OAuth client cho việc dùng token ở request đi ra.
- `authorizeHttpRequests(...)` bảo vệ các URL Portal.

Việc bật `oauth2Client()` **không tự làm mọi API chấp nhận token**, cũng không tự bảo đảm access token vừa cấp có audience phù hợp với Orders API.

## 8. Gọi API bằng access token từ `OAuth2AuthorizedClient`

### 8.1. Ví dụ trong controller Servlet

Sau OIDC Login, Spring Security có thể tra cứu authorized client tương ứng với registration và principal. Ví dụ:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersProxyController {

    private final RestClient ordersApi =
            RestClient.create("https://orders-api.example.com");

    @GetMapping("/orders/proxy")
    String orders(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient authorizedClient) {

        String accessToken =
                authorizedClient.getAccessToken().getTokenValue();

        return ordersApi.get()
                .uri("/api/orders")
                .headers(headers -> headers.setBearerAuth(accessToken))
                .retrieve()
                .body(String.class);
    }
}
~~~

Đây là ví dụ Spring Framework 6.1+ minh họa rõ token được gửi đi là:

~~~java
authorizedClient.getAccessToken().getTokenValue()
~~~

**Không phải:**

~~~java
oidcUser.getIdToken().getTokenValue()
~~~

Lời gọi API thực tế phải bảo đảm access token còn hiệu lực, có audience/scope phù hợp và được quản lý bằng `OAuth2AuthorizedClientManager` hoặc tích hợp HTTP client thích hợp nếu cần tự động refresh/reauthorize. Ví dụ thủ công trên tập trung vào **chọn đúng loại token**; không phải mô hình xử lý toàn bộ lỗi token, retry hoặc refresh cho production.

### 8.2. Nếu đã đăng nhập mà không có access token dùng được cho API

Có thể xảy ra khi:

- Client chỉ được cấp scope OIDC cơ bản.
- Access token được cấp cho UserInfo hoặc API khác, không phải Orders API.
- AS từ chối scope `orders.read`.
- Token đã hết hạn hoặc bị thu hồi.
- Access token là opaque và API đang cố kiểm tra bằng cơ chế JWT.
- API yêu cầu một token với resource/audience khác.

Không lấy ID token ra để “thay thế tạm”. Cần điều chỉnh cấu hình client, scope, audience/resource indicator hoặc quy trình cấp token theo giao thức được AS hỗ trợ.

### 8.3. Sử dụng client manager hoặc HTTP integration

Trong ứng dụng lớn, nên dùng các thành phần của Spring Security như:

- `OAuth2AuthorizedClientManager` để điều phối authorize/reauthorize.
- `OAuth2AuthorizedClientService` hoặc `OAuth2AuthorizedClientRepository` để quản lý trạng thái token theo registration và principal.
- Tích hợp OAuth 2.0 với `RestClient` hoặc `WebClient` phù hợp phiên bản Spring Security để gắn access token vào request đi ra.

Cách đó giúp tập trung quản lý token và giảm việc tự ghép header ở mỗi controller. Dù chọn cơ chế nào, phải kiểm tra **token thực sự dành cho API đích**.

## 9. Phía Resource Server phải xác minh điều gì?

### 9.1. Nhận bearer access token

Orders API mong đợi request:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <ACCESS_TOKEN_FOR_ORDERS_API>
~~~

API phải có chính sách tin cậy rõ:

1. Xác thực token bằng JWT signature hoặc introspection theo loại token.
2. Kiểm tra issuer hợp lệ.
3. Kiểm tra thời gian hiệu lực.
4. Kiểm tra **audience/resource** dành cho Orders API.
5. Kiểm tra loại token/profile khi hệ thống cung cấp cơ chế phân biệt.
6. Kiểm tra scope/authority và phân quyền nghiệp vụ.
7. Xử lý token không hợp lệ theo hợp đồng API, không chuyển hướng sang OIDC login web.

### 9.2. Dependency JWT Resource Server

Với Maven Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Ví dụ cấu hình issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/company
~~~

**`spring.security.oauth2.resourceserver.jwt.issuer-uri` khác `spring.security.oauth2.client.provider.*.issuer-uri`.** Cấu hình trước phục vụ API nhận token; cấu hình sau phục vụ OAuth client/OIDC RP.

Nếu access token là chuỗi opaque, Resource Server cần cơ chế introspection thích hợp thay cho cố decode JWT.

### 9.3. SecurityFilterChain của API

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders.read")
                        .anyRequest().denyAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .oauth2ResourceServer(resource -> resource
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Ví dụ giả định AS phát JWT access token và Spring Security chuyển scope `orders.read` thành authority `SCOPE_orders.read`. Cách mapping thực tế phụ thuộc claim `scope`/`scp` hoặc converter riêng nếu provider dùng định dạng khác.

**Cấu hình trên chưa minh họa kiểm tra audience**. Với Spring Security, cần kiểm tra audience theo cấu hình phù hợp; chỉ cấu hình issuer, chữ ký và thời gian thường **chưa đủ** để ngăn nhầm token với audience khác.

### 9.4. Bổ sung audience validation

Ví dụ Resource Server yêu cầu JWT access token có audience `orders-api`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class OrdersTokenValidationConfig {

    private static final String ISSUER =
            "https://idp.example.com/realms/company";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = token ->
                token.getAudience().contains("orders-api")
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Access token audience is not orders-api",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime,
                        audience));

        return decoder;
    }
}
~~~

Đoạn code cho thấy **API thực hiện kiểm tra issuer/time và audience**; cơ chế decoder còn xác minh chữ ký JWT bằng khóa được lấy theo cấu hình issuer/metadata phù hợp. Đây là ví dụ minh họa, cần được ghép với policy scope, token type/profile và quyền nghiệp vụ của hệ thống thật.

**Nếu ID token có `aud=employee-portal`**, nó không thỏa `aud=orders-api` và bị từ chối. Nếu hệ thống có audience chồng lấn giữa ID token và access token, cần bổ sung kiểm tra đặc tính **access token** theo profile của nhà cung cấp, thay vì tin một audience trùng lặp.

### 9.5. Phân biệt 401 và 403

Một API có thể phản hồi:

| Tình huống | Phản hồi thường phù hợp |
|---|---|
| Không có token hoặc token không hợp lệ, sai issuer/audience, hết hạn | **401 Unauthorized** |
| Token đã được xác thực hợp lệ nhưng thiếu quyền cho thao tác | **403 Forbidden** |

Ví dụ client đã được xác thực bằng access token nhưng thiếu `orders.read` thường bị từ chối ở bước authorization. Mã HTTP cụ thể còn phụ thuộc cấu hình authentication entry point và access denied handler, nhưng nguyên tắc là **không cấp quyền chỉ vì có một JWT hợp lệ về chữ ký**.

## 10. Chống token substitution khi cùng issuer ký nhiều loại JWT

### 10.1. Chia sẻ JWKS không có nghĩa mọi token đều cùng mục đích

Một OP có thể ký:

- ID token cho client.
- JWT access token cho một hoặc nhiều Resource Server.
- Những JWT hoặc assertion khác cho các giao thức riêng.

Resource Server có thể tìm khóa xác minh từ cùng `jwks_uri`. Nhưng khóa ký chỉ chứng minh token được một issuer tương ứng phát hành và nội dung chưa bị sửa, **không chứng minh token dành cho Resource Server đang nhận**.

Ngoài chữ ký, API phải thực thi **issuer, audience, loại token, scope và quyền**.

### 10.2. Token type và profile

Nếu AS phát hành JWT access token theo **RFC 9068**, nó có đặc điểm nhận diện và các quy tắc xác minh dành cho OAuth access token. Ví dụ profile có thể sử dụng header `typ` nhận diện access token.

Tuy nhiên:

- Không phải mọi access token là JWT.
- Không phải mọi JWT access token tuân RFC 9068.
- Một số provider dùng claim hoặc metadata riêng để phân loại token.
- ID token và access token có thể có claim chung như `iss` và `sub`.

Vì vậy, hãy xác nhận **token profile mà Resource Server được phép nhận**. Không tự đặt điều kiện loại token chỉ dựa trên tên claim nếu chưa thống nhất với AS.

### 10.3. Đừng dùng `authenticated()` làm toàn bộ chính sách API

Nếu API cấu hình nhận bất kỳ JWT hợp lệ nào từ cùng issuer nhưng không kiểm tra audience, loại token và scope, rồi chỉ đặt:

~~~java
.anyRequest().authenticated()
~~~

thì một JWT đúng chữ ký nhưng sai mục đích có nguy cơ bị coi là đủ để truy cập endpoint.

Thay vào đó, xác định audience dành cho API, kiểm tra token profile và quyền phù hợp cho từng endpoint. Các quy tắc `hasAuthority("SCOPE_...")` có thể hữu ích nhưng **không thay thế audience validation**.

## 11. Replay: ID token có thể bị sử dụng lại như bearer nếu API chấp nhận sai

### 11.1. OIDC nonce không phải bộ đếm dùng một lần của API

`nonce` được RP tạo trong Authentication Request và kiểm tra trong ID token theo quy tắc OIDC. Nó giúp ràng buộc token với yêu cầu xác thực.

Nhưng giả sử ID token chứa:

~~~json
{
  "nonce": "NONCE_A",
  "aud": "employee-portal",
  "exp": 1800003600
}
~~~

Nếu một API chấp nhận ID token này như bearer token, việc nonce từng khớp với một Authentication Request **không làm các lời gọi API tiếp theo trở thành one-time-use**.

API không có dữ liệu Authorization Request gốc của RP để xác minh ý nghĩa nonce theo đúng ngữ cảnh. Cố sử dụng nonce như idempotency key cho API thường là sai mô hình.

### 11.2. `exp` giới hạn thời gian, không ngăn replay trong thời gian hợp lệ

Một token có thể được phát lại nhiều lần trước khi hết hạn. `exp` chỉ nói token không còn được chấp nhận sau một thời điểm theo chính sách xác minh.

Tương tự:

- `iat` cho biết thời điểm phát hành, không phải counter.
- `auth_time` cho biết sự kiện xác thực, không phải dấu kiểm “đã dùng”.
- `jti` nếu có có thể dùng làm identifier trong một số cơ chế replay detection chuyên biệt, nhưng **việc ID token có `jti` không tự làm token single-use**.

Muốn chống replay API cần một thiết kế xác thực và ủy quyền API phù hợp, không chỉ dựa trên claim OIDC.

### 11.3. Authorization code single-use khác ID token

Trong Authorization Code flow, **authorization code** bị giới hạn một lần trao đổi tại AS. ID token là kết quả xác thực được RP sử dụng theo ngữ cảnh riêng của giao thức; nó không mặc nhiên có cơ chế consume-once cho mỗi lần đọc claim.

Không suy ra từ việc code chỉ dùng một lần rằng ID token không thể bị copy và gửi lại nếu một API sai thiết kế chấp nhận nó.

### 11.4. Access token bearer cũng có nguy cơ replay

Đổi từ ID token sang access token đúng mục đích **không có nghĩa mọi nguy cơ replay biến mất**.

Một bearer access token bị lộ có thể bị sử dụng lại trong thời hạn còn hiệu lực. Những biện pháp có thể cân nhắc gồm:

- Giảm scope và giới hạn audience.
- Dùng TTL hợp lý và lưu token an toàn.
- Bảo vệ bằng HTTPS, không ghi token vào log.
- Áp chính sách thu hồi và refresh theo AS.
- Sử dụng sender-constrained access token như **mTLS** hoặc **DPoP** khi AS/RS/client hỗ trợ.
- Thực thi phân quyền tài nguyên và idempotency tại API.

DPoP và mTLS là các cơ chế có yêu cầu giao thức riêng; không được chỉ đổi tên một header rồi cho rằng token đã được ràng buộc với người gửi.

## 12. Nếu một backend khác cần xác nhận người dùng đã đăng nhập thì sao?

### 12.1. Không truyền ID token qua các service như “bằng chứng chung”

Giả sử Portal gọi Service A, rồi A gọi Service B. Cách thiết kế yếu:

~~~text
Browser -> Portal (OIDC login)
Portal -> Service A (gửi ID token của Portal)
Service A -> Service B (chuyển tiếp cùng ID token)
Service B -> Database
~~~

Cả A và B đều đang sử dụng một ID token có audience dành cho Portal, làm mờ ranh giới tin cậy và quyền.

Một mô hình phù hợp hơn:

~~~text
Browser -> Portal: session cookie của Portal
Portal -> Service A: access token dành cho Service A
Service A -> Service B: token dành cho B qua delegation/exchange nếu cần
~~~

Nếu Service B cần danh tính người dùng, token dành cho B phải thể hiện điều đó theo mô hình được AS và B tin cậy. Không tự biến email hoặc `sub` được chép trong HTTP header thành một chứng thư xác thực mới.

### 12.2. Token exchange khi cần đổi audience

Một số hệ thống hỗ trợ **OAuth 2.0 Token Exchange** (RFC 8693) hoặc cơ chế on-behalf-of theo nhà cung cấp để client hoặc service nhận token khác dành cho downstream API.

Flow có thể là:

~~~mermaid
flowchart LR
    A["Portal có token hợp lệ cho ngữ cảnh hiện tại"] --> B["Authorization Server: token exchange / delegation"]
    B --> C["Access token mới có audience Service B"]
    C --> D["Service B xác minh token và quyền"]
~~~

Điều kiện:

- AS phải **hỗ trợ** token exchange hoặc cơ chế delegation tương ứng.
- Client/service phải được phép thực hiện exchange.
- Token nguồn, audience, scope và danh tính phải đáp ứng chính sách AS.
- Token mới phải được Resource Server đích xác minh đúng loại và quyền.

**RFC 8693 định nghĩa các loại subject token có thể bao gồm ID token trong một số trường hợp**, nhưng điều đó **không cho phép gửi ID token trực tiếp đến API như bearer access token**. Nếu AS và profile triển khai thực sự chấp nhận ID token làm assertion đầu vào cho một token exchange, ID token được gửi tới **token endpoint của AS theo hợp đồng exchange**, rồi AS mới quyết định có cấp access token cho Resource Server hay không.

Không giả định mọi OP hỗ trợ token exchange hoặc mọi ID token có thể dùng để exchange.

### 12.3. Service-to-service không có người dùng

Nếu một background service gọi API bằng danh tính ứng dụng, có thể dùng grant `client_credentials` khi AS cho phép.

Ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: company-auth
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope:
              - reports.read
        provider:
          company-auth:
            token-uri: https://idp.example.com/oauth2/token
~~~

Grant `client_credentials` cấp token cho client/service theo policy; **không chứng minh một End-User đã đăng nhập bằng OIDC**. Không lấy ID token của nhân viên bất kỳ để làm token cho tác vụ nền.

## 13. Browser, SPA, BFF và session

### 13.1. Ứng dụng server-side / Backend for Frontend

Với mô hình **Backend for Frontend (BFF)**:

1. Browser đăng nhập qua OIDC Authorization Code.
2. Backend Spring Security nhận token trong luồng back channel.
3. Backend xác minh ID token và duy trì `SecurityContext`/session.
4. Browser gửi session cookie đến BFF cho request của ứng dụng.
5. BFF dùng **access token dành cho API** để gọi Resource Server.

~~~text
Browser
  |
  | Session cookie (HttpOnly, Secure, SameSite phù hợp)
  v
Spring Boot BFF
  | OAuth access token đúng audience/scope
  v
Resource Server
~~~

Mô hình này giúp tránh phải trả ID token thô về browser rồi yêu cầu frontend tự dùng ID token để gọi API.

BFF vẫn cần các bảo vệ session, cookie, HTTPS và CSRF thích hợp; session cookie cũng là một credential cần bảo vệ.

### 13.2. SPA gọi API trực tiếp

Trong SPA trực tiếp gọi API, client OAuth thường cần một **access token dành cho API**, với cơ chế Authorization Code + PKCE và các chính sách token phù hợp.

Không lấy ID token từ kết quả đăng nhập rồi gắn vào mọi fetch request chỉ vì nó sẵn có trong thư viện OIDC frontend.

Ví dụ không nên dùng:

~~~javascript
const idToken = oidcUser.id_token;

fetch("https://orders-api.example.com/api/orders", {
  headers: { Authorization: "Bearer " + idToken }
});
~~~

Một luồng đúng hơn lấy token API từ cơ chế authorized client mà thư viện/provider hỗ trợ, sau đó dùng access token có audience/scope phù hợp. Cách lưu token trong browser và quản lý refresh phụ thuộc kiến trúc bảo mật SPA.

### 13.3. Session tại Portal và token API là hai vòng đời khác nhau

Có thể đồng thời xảy ra:

- Session Portal còn hợp lệ.
- ID token của lượt login ban đầu đã hết hạn.
- Access token dành cho API đã hết hạn và cần refresh.
- OP vẫn có phiên SSO cho browser.
- API đã thu hồi quyền `orders.read`.

Do đó **session còn sống không bảo đảm access token API còn hiệu lực**, và **access token còn hiệu lực không có nghĩa người dùng được phép thực hiện mọi tác vụ**. Cần xử lý từng lớp theo chính sách riêng.

## 14. Những ngoại lệ và tích hợp đặc thù cần hiểu đúng

### 14.1. API xác thực bằng ID token theo profile riêng của nhà cung cấp

Một số hạ tầng hoặc sản phẩm có cơ chế nhận **ID token được phát hành có audience đặt đúng service** làm identity assertion để gọi một endpoint cụ thể. Đây là **hợp đồng xác thực đặc thù của nền tảng/provider**, không phải quy tắc mặc định của mọi OAuth 2.0 Resource Server.

Trong trường hợp đó, hệ thống phải định nghĩa rõ:

- Issuer nào được tin cậy.
- Audience nào là chính service.
- Loại token và nguồn cấp token nào được chấp nhận.
- Quyền truy cập được quyết định từ đâu.
- Hạn thời gian, TLS, logging và replay risk.
- Cách backend xác thực token và phân quyền tài nguyên.

Không suy luận từ ngoại lệ này rằng **ID token OIDC được phát hành cho một web client bất kỳ** có thể được gửi tới mọi API.

### 14.2. Backend nhận ID token để thiết lập phiên riêng

Một số kiến trúc cho phép một backend **nhận một identity assertion** từ một nguồn đã xác định rồi thiết lập session ứng dụng, ví dụ một luồng sign-in được thiết kế riêng.

Nếu sử dụng ID token trong một giao thức như vậy, backend phải:

- Có hợp đồng rõ về client/audience/issuer được phép.
- Kiểm tra chữ ký, thời gian, claim và điều kiện replay thích hợp.
- Không coi token chỉ là bearer access token cho mọi endpoint.
- Tách bước **xác thực người dùng** khỏi việc **cấp quyền truy cập API**.

Đây là quyết định kiến trúc riêng. Với Spring Security OIDC Login thông thường, framework đã thực hiện luồng xác thực qua callback; không cần phát lại ID token đến một API tùy ý để “xác minh thêm”.

### 14.3. `id_token_hint` trong OIDC không phải access token

Một ứng dụng có thể sử dụng `id_token_hint` ở một số endpoint OIDC như RP-Initiated Logout khi provider hỗ trợ. Mục đích là gợi ý về phiên/danh tính liên quan theo giao thức logout.

Điều đó **không làm ID token trở thành credential cho Orders API**. Mỗi endpoint có hợp đồng riêng và phải được sử dụng theo đúng mục đích.

## 15. Thực hành phân tích lỗi 401 và 403

### 15.1. ID token bị API từ chối vì audience

Giả sử client vô tình gửi:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <ID_TOKEN_AUD_EMPLOYEE_PORTAL>
~~~

Orders API kiểm tra audience `orders-api` và nhận thấy ID token có audience `employee-portal`.

**Kết quả mong muốn:** token không đáp ứng điều kiện xác thực của API; từ chối, thường là 401.

Cách sửa: dùng **access token dành cho Orders API**, không xóa audience validator.

### 15.2. Access token hợp lệ nhưng thiếu scope

Client gửi access token có `aud=orders-api`, nhưng scope chỉ là `orders.list` trong khi endpoint cần `orders.read`.

**Kết quả mong muốn:** API xác thực token xong vẫn từ chối quyền; thường là 403 nếu token hợp lệ nhưng thiếu authority yêu cầu.

Cách sửa: xem lại scope được AS cấp và policy API. Không chuyển sang ID token hoặc thêm authority giả ở Resource Server để vượt qua lỗi.

### 15.3. Dùng một ID token có chữ ký hợp lệ từ sai tenant

Giả sử công ty có:

~~~text
Issuer nhân viên:
https://idp.example.com/realms/employees

Issuer đối tác:
https://idp.example.com/realms/partners
~~~

Một JWT có chữ ký hợp lệ từ issuer đối tác không mặc nhiên được API nhân viên chấp nhận. API phải cấu hình issuer được tin cậy và cách phân biệt tenant phù hợp.

Ngay cả khi email trong token thuộc cùng domain, nó không tự chứng minh tài khoản có quyền tương ứng.

### 15.4. API đang dùng `authenticated()` nhưng không kiểm tra audience

Nếu API nhận JWT từ chung OP, chỉ kiểm tra chữ ký/issuer/time và dùng:

~~~java
.anyRequest().authenticated()
~~~

thì thiếu một phần policy quan trọng. Cần bổ sung kiểm tra audience/token profile và quyền cho resource.

Không nên sửa theo hướng cho mọi OIDC client token được chấp nhận để “dễ tích hợp”.

## 16. Quy trình thiết kế an toàn cho luồng gọi API

### Bước 1. Xác định vai trò từng service

Vẽ rõ:

- **RP/OIDC Client** nào xác thực người dùng?
- **Authorization Server** nào cấp access token?
- **Resource Server** nào nhận token?
- API cần xử lý user delegation hay service identity?

Không dùng một tên “JWT” để gom các loại token khác mục đích.

### Bước 2. Đăng ký audience và scope cần thiết

Thống nhất với AS/RS:

- API identifier hoặc audience/resource URI.
- Scope/authority mà endpoint yêu cầu.
- Loại access token: JWT hay opaque.
- Token profile và cơ chế xác minh.
- Cách xin quyền thay mặt user hoặc client.
- Chính sách consent, refresh và thu hồi token.

### Bước 3. Spring Security Client quản lý access token

Dùng `ClientRegistration`, `OAuth2AuthorizedClient` và các integration phù hợp để xin token và gọi API.

Không đưa `OidcIdToken.getTokenValue()` vào bearer header của API theo thói quen.

### Bước 4. Resource Server kiểm tra token đúng mục đích

Kiểm tra:

- Chữ ký/introspection.
- Issuer.
- Expiry và các điều kiện thời gian.
- **Audience**.
- Token type/profile khi áp dụng.
- Scope/authority.
- Quyền nghiệp vụ theo user/tenant/resource.

### Bước 5. Bảo vệ token và dữ liệu phiên

Bảo vệ secret/token trong server, không ghi vào log, dùng HTTPS, phân biệt vòng đời session với access token. Khi cần chống bearer token replay ở mức cao hơn, xem xét sender-constrained token và chính sách AS/RS tương ứng.

### Bước 6. Khi cần gọi downstream service, thiết kế delegation

Nếu Service A phải gọi Service B thay mặt user, hãy dùng token có audience B thông qua cơ chế delegation/token exchange được AS hỗ trợ. Không forward ID token gốc dành cho RP.

## 17. Những hiểu nhầm thường gặp

**“ID token và access token đều là JWT nên dùng thay nhau được?”**

Không. Định dạng JWT chỉ là cách biểu diễn. Audience, mục đích, quyền và quy tắc kiểm tra khác nhau.

**“API cùng OP với Portal nên có thể tin ID token của Portal?”**

Không chỉ vì cùng OP. API cần access token hoặc một identity assertion theo hợp đồng riêng có audience, loại token và policy phù hợp.

**“ID token đã được Spring Security xác minh rồi, cứ gửi tiếp cho service khác có được không?”**

RP đã xác minh token cho mục đích đăng nhập của RP. Service khác cần cơ chế xác thực/ủy quyền của chính nó; việc RP xác minh không tự mở rộng audience của token.

**“ID token có `email_verified=true` thì đủ quyền đọc dữ liệu?”**

Không. Email verification không phải quyền truy cập tài nguyên. API phải kiểm tra phân quyền theo cơ chế được thiết kế.

**“Có nonce thì ID token không thể bị replay?”**

Không. Nonce liên kết ID token với Authentication Request OIDC; nó không tạo bộ đếm dùng một lần cho API.

**“Access token JWT có chữ ký hợp lệ thì API đã an toàn?”**

Chưa đủ. API còn cần kiểm tra issuer, audience, thời gian, token profile, scope và quyền nghiệp vụ.

**“ID token hết hạn thì HttpSession tại Portal phải tự hết ngay?”**

Không mặc định. Thời hạn ID token và vòng đời session Spring Security có thể khác nhau. Chính sách session của ứng dụng cần được thiết kế riêng.

**“Có thể gửi ID token đến token exchange endpoint?”**

Một số AS/profile cho phép ID token làm input assertion theo OAuth Token Exchange, nhưng điều đó phải được AS hỗ trợ và client được cấp quyền. **Token exchange endpoint khác Resource Server API**.

**“Resource Server có `issuer-uri` là đã tự chặn ID token?”**

Không nên mặc định. Kiểm tra issuer và chữ ký không tự thay thế audience và token-type validation. Cấu hình API phải phản ánh hợp đồng token được chấp nhận.

## 18. Tình huống tự kiểm tra

### Tình huống A: Portal nhận hai token

Client sau login có:

~~~text
ID token:
  aud = portal-web
  sub = alice

Access token:
  aud = orders-api
  scope = orders.read
~~~

**Hỏi:** Token nào dùng gọi Orders API?

**Trả lời:** Access token có audience dành cho `orders-api` và scope thích hợp. ID token dùng để Portal xử lý kết quả xác thực.

### Tình huống B: API nhận ID token có chữ ký hợp lệ

Orders API nhận một JWT có issuer và chữ ký hợp lệ, nhưng `aud=portal-web`.

**Hỏi:** Có thể chỉ vì chữ ký hợp lệ mà cấp quyền không?

**Trả lời:** Không. Audience sai đối tượng nhận, đây không phải access token được cấp cho API. API phải từ chối theo chính sách.

### Tình huống C: Có access token nhưng vẫn bị 403

Token có `aud=orders-api`, nhưng không có `orders.read`.

**Hỏi:** Nên gửi lại ID token để thử không?

**Trả lời:** Không. Cần xem quyền được cấp, scope và chính sách API. ID token không thay thế access token thiếu quyền.

### Tình huống D: ID token có nonce hợp lệ

ID token hợp lệ có `nonce` khớp Authentication Request; một client thử gửi token này đến Orders API nhiều lần.

**Hỏi:** Nonce có làm mỗi request trở thành one-time-use không?

**Trả lời:** Không. Nonce thuộc việc xác minh OIDC ở RP. API cần access token đúng mục đích và các cơ chế replay protection riêng khi cần.

### Tình huống E: Backend gọi thêm service B

Portal có access token dành cho Service A; A cần gọi Service B.

**Hỏi:** A có nên lấy ID token gốc từ Portal rồi forward sang B?

**Trả lời:** Không theo mô hình thông thường. Cần token dành cho B qua một cơ chế delegation hoặc token exchange được AS hỗ trợ, hoặc dùng client identity cho tác vụ không có user.

### Tình huống F: Provider có API đặc thù chấp nhận ID token

Một nền tảng công bố rằng service của họ xác thực caller bằng ID token do issuer cụ thể phát hành với audience là URL service.

**Hỏi:** Điều đó có cho phép dùng mọi OIDC ID token để gọi mọi API không?

**Trả lời:** Không. Đây là hợp đồng xác thực đặc thù. Chỉ sử dụng token có issuer/audience/loại và chính sách mà service quy định; không áp dụng mặc định sang một OAuth Resource Server khác.

## Ghi nhớ

- **ID token dành cho OIDC Relying Party để xác thực người dùng**. Nó không phải access token mặc định để gọi Resource Server.
- **Access token dành cho API** cần được API kiểm tra issuer, audience, thời hạn, token profile, scope và quyền nghiệp vụ theo hợp đồng với AS.
- **Chữ ký JWT hợp lệ chưa đủ để chấp nhận token**: token có thể đúng issuer nhưng sai audience hoặc sai mục đích.
- **Nonce, `exp` và code single-use** không biến ID token thành một bearer credential không thể replay tại API.
- Trong **Spring Security**, dùng `OidcUser`/`OidcIdToken` để xử lý danh tính sau login; dùng `OAuth2AuthorizedClient.getAccessToken()` và cơ chế authorized client manager khi gọi API.
- Token exchange và các provider-specific identity assertion là những hợp đồng riêng. Chỉ sử dụng khi được AS/service hỗ trợ và xác định rõ ranh giới tin cậy.
- Với hệ thống có nhiều service, **không chuyển tiếp ID token gốc từ RP qua các API** như một chứng thư quyền chung; hãy cấp hoặc nhận đúng token dành cho từng Resource Server.

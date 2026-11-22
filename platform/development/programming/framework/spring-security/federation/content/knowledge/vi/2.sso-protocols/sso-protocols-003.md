# Assertion SAML, ID token, access token và service ticket

> **Ngữ cảnh:** Spring Security – Federation / Giao thức SSO. Bốn loại hiện vật này đều có thể xuất hiện quanh một lần đăng nhập tập trung, nhưng **khác nhau về giao thức, mục đích, đối tượng nhận và cách kiểm tra**. Gọi chung chúng là “token đăng nhập” dễ dẫn đến lỗi bảo mật.

## 1. Bức tranh tổng quan: xác thực, ủy quyền và SSO

- **Authentication (xác thực):** “Ai đã đăng nhập, bằng cách nào, khi nào?” Trong SAML Web SSO, bên cung cấp định danh (IdP) phát hành assertion; trong OpenID Connect (OIDC), OpenID Provider phát hành **ID token**.
- **Authorization (cấp quyền truy cập):** “Client nào được phép gọi tài nguyên nào, với phạm vi gì?” OAuth 2.0 sử dụng **access token** làm credential truy cập tài nguyên. Một access token có thể được cấp trong luồng không có người dùng, ví dụ `client_credentials`.
- **Ticket-based SSO:** CAS cấp **service ticket** cho đúng một dịch vụ; dịch vụ phải gửi ticket đó về CAS để xác minh, thường chỉ dùng được một lần.
- **SSO:** Người dùng thường đăng nhập tại IdP/CAS một lần, sau đó có thể đi vào nhiều ứng dụng. Điều này **không có nghĩa** một assertion, ID token, access token hay service ticket có thể tự do dùng lại cho mọi ứng dụng.

Các vai trò thường gặp:

| Vai trò | Ý nghĩa |
| --- | --- |
| User / browser | Người dùng và trình duyệt chuyển hướng, gửi biểu mẫu hoặc mang mã/ticket |
| IdP / OpenID Provider (OP) | Xác thực người dùng, phát hành khẳng định định danh |
| SAML Service Provider (SP) / OIDC Relying Party (RP) | Ứng dụng tin cậy IdP/OP và đăng nhập người dùng |
| OAuth Authorization Server (AS) | Cấp access token theo grant và chính sách |
| OAuth Resource Server (RS) | API nhận access token, kiểm tra token rồi quyết định quyền |
| CAS Server / CAS Service | Máy chủ đăng nhập CAS / ứng dụng nhận service ticket |

Một hệ thống có thể kiêm nhiều vai trò, nhưng **đích nhận phải được kiểm tra theo từng vai trò**.

## 2. Bảng so sánh bốn hiện vật

| Khía cạnh | SAML assertion | OIDC ID token | OAuth 2.0 access token | CAS service ticket |
| --- | --- | --- | --- | --- |
| Giao thức điển hình | SAML 2.0 | OpenID Connect 1.0 | OAuth 2.0 | CAS Protocol |
| Câu hỏi chính | IdP khẳng định điều gì về lần xác thực? | OP xác thực user nào cho client này? | Quyền truy cập tài nguyên nào đã được cấp? | CAS có xác nhận login cho đúng service này không? |
| Đối tượng nhận | SAML SP (entity ID / ACS) | OIDC client (client ID) | Resource server/API | Một CAS service URL |
| Biểu diễn | XML assertion, thường nằm trong SAML Response | JWT (signed; có thể được mã hóa) | Chuỗi opaque hoặc JWT, tùy AS | Chuỗi opaque như `ST-…` |
| Bên phát hành | SAML IdP | OpenID Provider | Authorization Server | CAS Server |
| Trình tự xác minh | XML signature, issuer, điều kiện, subject confirmation, đối tượng nhận, replay | JWS/JOSE, issuer, audience, thời gian, nonce khi áp dụng | JWT: chữ ký + issuer + audience + hạn + quyền; opaque: introspection | Gọi HTTPS đến endpoint CAS để validate ticket cùng `service` |
| Thời hạn/sử dụng | Giới hạn thời gian; cần chống replay | Giới hạn `exp`, cần ràng buộc client/request | Thường ngắn hạn, Bearer có thể dùng nhiều lần khi còn hợp lệ | Ngắn hạn, ràng buộc một service, dùng một lần để validate |
| Dùng trực tiếp gọi API? | Không phải credential API OAuth | **Không** | **Có**, nếu API chấp nhận token và quyền phù hợp | **Không**; dùng để thiết lập phiên của CAS service |

> **Quy tắc nhận diện nhanh:** Assertion/ID token chủ yếu là **bằng chứng về xác thực** cho bên nhận đã định; access token là **credential truy cập tài nguyên**; service ticket là **mã một lần để dịch vụ hỏi lại CAS**.

## 3. SAML assertion: lời khẳng định có cấu trúc XML từ IdP

### 3.1. Assertion khác SAML Response

Trong SAML Web Browser SSO, SP có thể gửi `<samlp:AuthnRequest>` đến IdP. IdP xác thực user rồi tạo `<samlp:Response>`, bên trong thường có một hoặc nhiều `<saml:Assertion>`. Trình duyệt gửi SAML Response về **Assertion Consumer Service (ACS)** của SP, thường qua HTTP POST.

```text
Browser -> SP: yêu cầu trang cần đăng nhập
SP -> Browser -> IdP: AuthnRequest (SP-initiated)
IdP: xác thực user, tạo SAML Response/Assertion
IdP -> Browser -> SP ACS: gửi SAMLResponse
SP: kiểm tra trust + signature + issuer + time + audience + recipient
SP: tạo phiên ứng dụng (ví dụ HttpSession), áp dụng quyền nội bộ
```

**SAML Response** là phong bì giao thức; **SAML assertion** là khẳng định bên trong. Chữ ký có thể bảo vệ Response, assertion hoặc cả hai theo profile/cấu hình tin cậy; không được mặc định chỉ cần thấy một thẻ `Signature` là toàn bộ thông tin mình sử dụng đã được bảo vệ.

### 3.2. Các thành phần cần hiểu

- `Issuer`: thực thể IdP phát hành assertion; phải khớp IdP đã cấu hình tin cậy.
- `Subject` / `NameID`: định danh subject; chính sách ứng dụng quyết định cách ánh xạ đến user nội bộ. `NameID` không phải vai trò/quyền.
- `AuthnStatement`: ngữ cảnh/lần xác thực; có thể có `AuthnInstant`, `SessionIndex` và `AuthnContext`.
- `AttributeStatement`: các thuộc tính như bộ phận, email, nhóm; chúng là **claims**, không tự động tương đương quyền quản trị.
- `Conditions`: giới hạn thời gian `NotBefore`, `NotOnOrAfter` và thường có `AudienceRestriction` chỉ định SP.
- `SubjectConfirmationData`: với bearer SSO, cần kiểm tra `Recipient` (ACS hợp lệ), `InResponseTo` nếu là phản hồi cho AuthnRequest, thời hạn và các điều kiện liên quan.

Ví dụ **rút gọn để đọc cấu trúc**, không phải assertion hợp lệ để triển khai (đã lược chữ ký và các trường bảo mật bắt buộc theo profile):

```xml
<saml:Assertion
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_a123" Version="2.0" IssueInstant="2026-11-07T01:00:00Z">
  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <saml:Subject>
    <saml:NameID>user-123</saml:NameID>
  </saml:Subject>
  <saml:Conditions
    NotBefore="2026-11-07T00:59:00Z"
    NotOnOrAfter="2026-11-07T01:04:00Z">
    <saml:AudienceRestriction>
      <saml:Audience>https://portal.example.org/saml/sp</saml:Audience>
    </saml:AudienceRestriction>
  </saml:Conditions>
</saml:Assertion>
```

Ví dụ minh họa rằng `Audience` trỏ tới **SP**, không phải một API tùy ý. Mốc thời gian chỉ là dữ liệu giả lập; `NotOnOrAfter` là hạn **loại trừ** (không còn hợp lệ tại hoặc sau thời điểm đó).

### 3.3. SP thực sự phải kiểm tra gì?

1. Tin cậy **đúng IdP** bằng metadata/certificate cấu hình; xác minh chữ ký XML trên dữ liệu **đúng là dữ liệu được xử lý** và cấu trúc Reference hợp lệ. Cảnh giác XML signature wrapping: không lấy assertion khác với assertion đã được xác minh.
2. So khớp `Issuer`, SP `entityID`/`AudienceRestriction`, `Destination` của Response, ACS/`Recipient` và `InResponseTo` với request đã phát khi áp dụng. Luồng **IdP-initiated** có thể không có `InResponseTo`; chỉ chấp nhận nếu có chính sách riêng và biện pháp chống replay.
3. Kiểm tra cửa sổ thời gian của assertion/confirmation, chấp nhận clock skew nhỏ có kiểm soát; lưu ID assertion/response theo cửa sổ hợp lệ để ngăn phát lại.
4. Kiểm tra `SubjectConfirmation` đúng phương thức/profile; chỉ sau đó ánh xạ user/attributes thành account và quyền ứng dụng.
5. Dùng HTTPS, khóa và metadata đáng tin cậy; mã hóa assertion (nếu được dùng) bảo vệ bí mật, **không thay thế** việc xác minh chữ ký và điều kiện.

**Sai phổ biến:** chỉ Base64-decode `SAMLResponse` rồi đọc email, hoặc nhận assertion của SP A tại SP B vì “đều cùng một IdP”. Đọc được XML không chứng minh nó hợp lệ hay được cấp cho SP hiện tại.

## 4. OIDC ID token: bằng chứng đăng nhập cho client

OpenID Connect bổ sung **lớp xác thực** lên OAuth 2.0. Với Authorization Code Flow (thường kèm PKCE), browser nhận `code` qua redirect; backend/client đổi code tại token endpoint và nhận `id_token` cùng các token khác theo luồng và chính sách OP.

```text
Browser -> OIDC client: mở trang
Client -> OP: authorization request (client_id, scope=openid, state, PKCE, nonce nếu dùng)
OP: xác thực user
OP -> Browser -> Client redirect URI: authorization code
Client -> OP token endpoint: đổi code (và PKCE code_verifier)
OP -> Client: ID token và thường là access token
Client: kiểm tra ID token, tạo phiên đăng nhập cục bộ
```

### 4.1. Định dạng và claims

ID token là JWT theo OIDC, có dạng `base64url(header).base64url(payload).signature` nếu ký JWS. Ví dụ payload **minh họa sau khi giải mã, không phải token được ký hợp lệ**:

```json
{
  "iss": "https://idp.example.org",
  "sub": "7f2a-user-123",
  "aud": "web-client",
  "iat": 1794013200,
  "exp": 1794013500,
  "nonce": "nonce-from-original-login-request",
  "auth_time": 1794013100
}
```

- `iss`: định danh chính xác của OP/issuer.
- `sub`: subject ổn định trong phạm vi issuer, thường dùng cùng `iss` làm khóa định danh ứng dụng: **(iss, sub)**.
- `aud`: client ID nhận ID token; có thể là mảng. Trường hợp nhiều audience phải xét quy tắc `azp` và tính tin cậy của các audience.
- `iat`, `exp`: lúc phát hành và hết hạn; `auth_time`: thời điểm xác thực user nếu được yêu cầu/trả về.
- `nonce`: khi client gửi nonce, phải kiểm tra giá trị ID token khớp request đã lưu; hỗ trợ chống replay/token injection.
- `acr`, `amr` nếu có: mức/phương thức xác thực; không tự động trao quyền truy cập API.

### 4.2. Kiểm tra trước khi tin ID token

1. Dùng thư viện OIDC đáng tin, xác minh chữ ký với khóa/thuật toán của OP đã tin cậy; không chấp nhận `alg=none`, không tự tin JWT chỉ vì decode thành JSON.
2. So khớp `iss` **chính xác**, `aud` chứa `client_id` của ứng dụng, kiểm tra `azp` khi phải áp dụng; kiểm tra `exp`, `iat` và các giới hạn thời gian liên quan.
3. Liên kết response với đúng login transaction bằng `state`, redirect URI và PKCE. Kiểm tra `nonce` khi được gửi/yêu cầu theo flow; không xem `state` và `nonce` là cùng một trường.
4. Chỉ dùng claims đã xác minh để tạo danh tính/phiên. Email/display name có thể thay đổi và không phải khóa định danh toàn cục; tránh nối user giữa các issuer chỉ bằng email.
5. Kiểm tra `auth_time` khi có yêu cầu login gần đây (`max_age`), cùng các yêu cầu bảo mật riêng của client.

**ID token KHÔNG phải access token.** API không được nhận ID token làm bearer chỉ vì nó có chữ ký JWT hợp lệ: `aud` của nó là **OIDC client**, trong khi API phải đòi token được cấp cho **resource server**. Ngược lại, dùng access token như bằng chứng login đầy đủ cũng không thay cho quy trình OIDC.

## 5. OAuth 2.0 access token: credential gọi resource server

Access token được AS cấp cho **client** theo một grant và chính sách của AS, để client gọi tài nguyên. Token có thể đại diện quyền được ủy quyền bởi người dùng hoặc quyền của chính ứng dụng (ví dụ `client_credentials`); vì vậy “có access token” không luôn có nghĩa “user vừa đăng nhập”.

```http
GET /api/orders HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...example-access-token...
```

Bearer nghĩa là **ai nắm token hợp lệ có thể trình token đó** theo phạm vi quyền của nó. Không đưa token vào URL/query string, log, analytics, lỗi trả ra client hoặc kho lưu trữ công khai.

### 5.1. Access token opaque và JWT

| Dạng | Đặc điểm | Resource server kiểm tra |
| --- | --- | --- |
| Opaque/reference | Chuỗi không có cấu trúc cho client đọc; AS lưu trạng thái hoặc tra cứu | Gọi **token introspection** qua kênh an toàn, nhận `active` và metadata, kiểm tra đối tượng nhận/scope/chính sách |
| JWT access token | Claims nằm trong payload có thể giải mã; phải được ký và kiểm tra | Chữ ký với khóa tin cậy; `iss`, `aud` của **API**, `exp`/`nbf`, chính sách thuật toán, scope/permissions và các ràng buộc cần thiết |

Ví dụ payload JWT access token **minh họa**, không phải chứng chỉ bảo mật hợp lệ:

```json
{
  "iss": "https://idp.example.org",
  "sub": "7f2a-user-123",
  "aud": "orders-api",
  "client_id": "web-client",
  "scope": "orders:read orders:create",
  "iat": 1794013200,
  "exp": 1794013500
}
```

Giả sử API `orders-api` chỉ nhận `aud=orders-api`. Nó không thể thay kiểm tra đó bằng việc thấy `sub`, `email` hoặc `iss` “trông đúng”. `scope` biểu thị quyền được **cấp cho token**, nhưng endpoint vẫn cần quyết định cuối cùng theo policy và tài nguyên cụ thể: quyền `orders:read` chưa chắc cho phép đọc đơn hàng thuộc người khác.

**Lưu ý chuẩn:** RFC 9068 mô tả một **profile JWT access token** có `typ=at+jwt` và quy tắc xác minh cụ thể. Không phải mọi JWT access token đều triển khai profile này; không áp đặt định dạng/claim của RFC 9068 cho một AS không tuyên bố dùng profile đó. OAuth 2.0 không bắt buộc access token luôn là JWT.

### 5.2. Cách resource server xử lý

1. Trích bearer token từ `Authorization` header; từ chối token thiếu/sai định dạng.
2. Xác minh bằng **JWT decoder + validators** phù hợp issuer/audience, hoặc introspection đối với opaque token. Chỉ decode Base64 **không đủ**.
3. Kiểm tra token dành cho đúng API, còn hiệu lực, chưa bị từ chối; kiểm tra scope/permissions trong ngữ cảnh request, tenant và object.
4. Trả **401 Unauthorized** khi token thiếu/không hợp lệ; thường dùng **403 Forbidden** khi danh tính hợp lệ nhưng thiếu quyền. Header `WWW-Authenticate: Bearer` theo ngữ nghĩa OAuth khi phù hợp.

**Access token khác refresh token:** refresh token được client dùng với AS để xin access token mới; không gửi refresh token cho resource server. Cơ chế thu hồi (revoke) JWT không tự xảy ra chỉ vì đã logout: có thể cần hạn ngắn, introspection hoặc cơ chế denylist/revocation.

## 6. CAS service ticket: mã dùng một lần cho đúng dịch vụ

CAS có mô hình ticket riêng. Sau khi người dùng đăng nhập với CAS Server, browser có thể giữ **Ticket Granting Cookie (TGC)** gắn với phiên CAS; CAS Server quản lý **Ticket Granting Ticket (TGT)** ở phía server. Khi vào một ứng dụng CAS (service), CAS cấp một **service ticket (ST)** ngắn hạn, thường có tiền tố `ST-`.

```text
Browser -> Service A: cần đăng nhập
Service A -> Browser -> CAS /login?service=<service-A-URL>
CAS: xác thực user hoặc dùng phiên SSO CAS hiện có
CAS -> Browser -> Service A?ticket=ST-...
Service A -> CAS /serviceValidate?service=<service-A-URL>&ticket=ST-...
CAS -> Service A: authenticationSuccess(user, attributes) hoặc failure
Service A: tạo phiên nội bộ; loại bỏ ticket khỏi URL sau xử lý
```

Điểm khác biệt mang tính quyết định:

- **ST ràng buộc với đúng `service`** đã yêu cầu. Service B không được dùng ticket cấp cho Service A.
- Theo CAS Protocol, **mỗi service ticket chỉ được đưa vào xác minh một lần**; CAS phải vô hiệu hóa nó sau một lần thử validate, kể cả thử thất bại. Ticket đã tiêu thụ hoặc hết hạn không được tái sử dụng.
- Dịch vụ gọi endpoint như `/serviceValidate` hoặc `/p3/serviceValidate` (tùy phiên bản/triển khai) qua **HTTPS** và kiểm tra response thành công/thất bại; không suy ra user chỉ từ chuỗi `ST-...`.
- **TGT/TGC không phải ST.** TGT/TGC hỗ trợ cấp các ST mới nhờ SSO, trong khi ST phục vụ một lần chuyển giao login cho một service.
- CAS còn có **proxy ticket**, dùng cho ủy quyền qua dịch vụ trung gian theo protocol CAS; nó không được tùy tiện xem như OAuth access token và endpoint validate/loại ticket phải phù hợp.

Ví dụ HTTP minh họa, ticket là dữ liệu giả:

```http
GET /cas/serviceValidate?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas&ticket=ST-example-123 HTTP/1.1
Host: sso.example.org
```

Nếu `service` sai, ticket đã dùng hoặc hết hạn, CAS phải trả xác minh thất bại. Trường hợp thành công, service nhận dữ liệu xác thực từ **kết quả validate của CAS**, sau đó ánh xạ user và quyền nội bộ.

## 7. Một người đăng nhập, bốn ranh giới tin cậy khác nhau

Giả sử công ty có một cổng Web, một API đơn hàng và một ứng dụng CAS cũ. IdP và CAS có thể dùng chung thư mục người dùng, nhưng các hiện vật không thể hoán đổi cho nhau:

1. **SAML:** IdP phát assertion cho `https://portal.example.org/saml/sp`. Chỉ SP đã cấu hình tin cậy nhận, kiểm tra và tạo phiên đăng nhập.
2. **OIDC:** OP phát ID token với `aud=web-client`. Ứng dụng Web dùng nó để hoàn thành login và tạo phiên.
3. **OAuth 2.0:** AS phát access token với `aud=orders-api` và `scope=orders:read`. API xác minh token và policy; ID token của `web-client` không thay thế được.
4. **CAS:** CAS phát ST cho `https://legacy.example.org/login/cas`. Ứng dụng legacy gửi ST cùng service URL lên CAS, validate một lần rồi tạo phiên.

Điểm nối giữa các giao thức là **identity federation / account mapping**, không phải “đổi nhãn” trực tiếp các token. Nếu một tổ chức cần token exchange hoặc broker SAML→OIDC, đó là **giao dịch phát hành token mới** theo chính sách tin cậy rõ ràng, không phải đổi tên claim hay copy chuỗi token.

### SSO session, token lifetime và logout

- Phiên IdP/CAS và phiên nội bộ của SP/RP/service là **hai trạng thái khác nhau**; hết hạn một token không nhất thiết kết thúc HttpSession đã tạo.
- Logout ứng dụng không tự đảm bảo logout tại IdP hay ở các ứng dụng còn lại. SAML SLO, OIDC RP-Initiated Logout/front-channel/back-channel logout và CAS SLO có giao thức, giới hạn và mức hỗ trợ riêng.
- Đừng dùng một access token còn hiệu lực làm bằng chứng rằng phiên SSO vẫn đang mở; cũng đừng giả định revoke một access token sẽ xóa phiên đăng nhập web.
- Thiết kế thời hạn, đồng bộ đồng hồ, chống replay, lưu trữ phiên và đăng xuất theo **từng loại hiện vật**.

## 8. Áp dụng trong Spring Security

Spring Security thể hiện rõ **vai trò** của ứng dụng; chọn cấu hình theo luồng cần bảo vệ. Những đoạn sau là các **phương án tích hợp riêng**, không phải các dòng cần ghép chung vào một filter chain.

### 8.1. Ứng dụng Web là OIDC client (RP)

Khai báo dependency OAuth2 Client phù hợp và đăng ký client với OP. Ví dụ Java dùng Spring Security 6+/Spring Boot tương thích; đây là class cấu hình đầy đủ, cần có dependency Spring Security và cấu hình `spring.security.oauth2.client`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLoginSecurity {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

Để OIDC hoạt động, `scope` phải có `openid` và provider/client cần thông tin như `issuer-uri`, `client-id`, `client-secret`/phương thức xác thực phù hợp và redirect URI hợp lệ. Spring Security nhận `OidcUser`/`OidcIdToken` sau login; ứng dụng nên dựa vào validation mặc định của framework và chỉ tùy biến khi có hiểu biết về OIDC. **Không chuyển ID token thành Authorization: Bearer để gọi API.**

### 8.2. API là OAuth 2.0 Resource Server

Đưa dependency resource-server và JOSE vào ứng dụng nếu nhận JWT. Ví dụ cấu hình Spring Boot khi AS cung cấp metadata/JWKS:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org
          audiences: orders-api
```

`issuer-uri` dùng để khám phá khóa và kiểm tra issuer; `audiences` yêu cầu token dành cho API này (kiểm tra hỗ trợ property theo Spring Boot version đang dùng). Filter chain có dạng:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders:read")
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
```

Đoạn trên là **fragment đặt bên trong phương thức cấu hình `HttpSecurity`**, không phải chương trình Java độc lập. Nếu token opaque, chuyển sang phương án `oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(...))` và cấu hình introspection endpoint/credentials theo phiên bản Spring Security. Không tự viết decoder để bỏ qua issuer/audience.

### 8.3. Ứng dụng Web là SAML Service Provider

Dùng hỗ trợ SAML2 Service Provider, cấu hình `RelyingPartyRegistration`/IdP metadata, khóa/certificate tin cậy và ACS; trong `SecurityFilterChain` dùng `saml2Login(Customizer.withDefaults())`. Spring Security xử lý `SAMLResponse` tại ACS (thường `/login/saml2/sso/{registrationId}`) và tạo `Saml2Authentication` sau khi provider xác minh chữ ký, điều kiện và subject. Metadata/đường dẫn cụ thể phụ thuộc phiên bản/cấu hình; cần đồng bộ với phía IdP.

### 8.4. Ứng dụng CAS Service

CAS không sử dụng `oauth2Login()`, `saml2Login()` hay `oauth2ResourceServer()` để validate ST. Tích hợp CAS client/validator phù hợp hệ Spring Security đang dùng, cấu hình CAS login URL, **service URL chính xác**, trust HTTPS và `TicketValidator`. Dịch vụ nhận ticket, gọi CAS validate rồi mới đưa principal vào `SecurityContext`/phiên. Với hệ thống mới, cân nhắc IdP hỗ trợ OIDC/SAML khi cần tích hợp xuyên công nghệ, nhưng không tự thay CAS ST bằng access token.

**Nguyên tắc chung của Spring Security:** thành công ở bước authentication tạo một `Authentication` trong `SecurityContext`; việc có `Authentication` không tự suy ra user được quyền với mọi endpoint. Luôn cấu hình authorization theo request/resource và vai trò.

## 9. Thí nghiệm Java 17+: vì sao audience không thể thay thế nhau?

Chương trình Java thuần bên dưới **chỉ minh họa phép so khớp đối tượng nhận sau khi token đã được xác minh bằng thư viện bảo mật**. Nó **không** giải mã, xác thực chữ ký hoặc chấp nhận token thật và không được dùng làm bộ xác thực production.

Tạo `AudienceBoundaryDemo.java`:

```java
import java.util.Set;

public class AudienceBoundaryDemo {
    private static boolean isFor(Set<String> audiences, String expected) {
        return audiences.contains(expected);
    }

    public static void main(String[] args) {
        Set<String> idTokenAud = Set.of("web-client");
        Set<String> accessTokenAud = Set.of("orders-api");

        System.out.println("ID token -> web client: "
                + isFor(idTokenAud, "web-client"));
        System.out.println("ID token -> orders API: "
                + isFor(idTokenAud, "orders-api"));
        System.out.println("Access token -> orders API: "
                + isFor(accessTokenAud, "orders-api"));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac AudienceBoundaryDemo.java
java AudienceBoundaryDemo
```

Kết quả stdout chính xác:

```text
ID token -> web client: true
ID token -> orders API: false
Access token -> orders API: true
```

Cả ID token và access token đều **có thể là JWT ký hợp lệ** nhưng đối tượng nhận khác nhau. Trong hệ thống thật còn phải xác minh issuer, signature, thời gian, token type, nonce/introspection (tùy giao thức), grant và quyền cụ thể; đoạn demo không thực hiện các kiểm tra đó.

## 10. Các lỗi thường gặp và cách xử lý

| Lỗi | Vì sao sai / biện pháp |
| --- | --- |
| Gửi ID token vào API như access token | `aud` trỏ tới OIDC client; API phải yêu cầu access token dành cho resource server và kiểm tra quyền |
| Chỉ decode JWT/SAML rồi tin claim | Decode không xác minh chữ ký, nguồn phát hành, thời gian, đối tượng nhận hay ràng buộc request |
| API chỉ kiểm tra JWT signature và `exp` | Token ký hợp lệ nhưng cấp cho API/client khác vẫn nguy hiểm; kiểm tra `iss`, `aud` và policy |
| Xem `scope=read` là đủ để đọc mọi record | Scope không thay thế kiểm tra tenant, ownership và authorization theo đối tượng |
| Dùng lại SAML assertion hoặc CAS ST | SAML cần chống replay theo ID/request; CAS ST có hiệu lực validate một lần |
| Nhận ST chỉ vì bắt đầu bằng `ST-` | ST là chuỗi opaque; phải validate online với CAS kèm đúng `service` |
| Sử dụng email làm ID định danh liên hệ giữa các issuer | Email có thể đổi/không verified; dùng khóa ổn định theo issuer + subject và mapping đã kiểm soát |
| Cấu hình logout một nơi rồi nghĩ mọi nơi đã thoát | Phiên IdP/CAS, phiên ứng dụng và token API có vòng đời riêng |
| Cho token vào URL, log hoặc frontend store dễ bị XSS | Bearer credential có thể bị đánh cắp; dùng HTTPS, bảo vệ storage, hạn chế quyền và thời gian |
| Quên kiểm tra `state`/PKCE/`nonce` trong OIDC | Dễ tạo lỗ hổng login CSRF, code interception hoặc token replay; dùng client OIDC chuẩn |

### Cách tự kiểm tra một thiết kế SSO

Với **mỗi credential nhận được**, hãy trả lời đủ bảy câu:

1. Nó thuộc **giao thức** nào, được **phát hành bởi ai** và cho **bên nhận nào**?
2. Nó đang làm chứng cho **xác thực** hay cấp **quyền truy cập tài nguyên**, hay chỉ là ticket để tra cứu?
3. Bộ kiểm tra đáng tin cậy nào xác minh chữ ký/issuer hoặc gọi introspection/CAS validator?
4. Các giới hạn **audience/service, expiry, request binding, replay** được thực thi ở đâu?
5. Subject nào được ánh xạ thành tài khoản nội bộ, và ánh xạ đó có chống lẫn tenant/issuer không?
6. Từ principal đã tin cậy, policy nào quyết định **quyền trên endpoint và từng resource**?
7. Khi logout, revoke hoặc ticket hết hạn, **phiên ứng dụng** và các phiên SSO còn lại sẽ thay đổi thế nào?

Nếu một câu không có câu trả lời, thiết kế chưa đủ rõ để coi credential đó là đáng tin.

## 11. Câu hỏi ôn tập nhanh

**Hỏi:** Cả ID token và access token đều là JWT có chữ ký hợp lệ. Có thay thế nhau được không?  
**Đáp:** Không. Token type, intended audience, mục đích và validation rules khác nhau; API cần access token cấp cho chính nó.

**Hỏi:** Sau CAS login, vì sao service không lưu ST để gửi lại ở mỗi request?  
**Đáp:** ST được dùng để validate một lần và tạo phiên của service; lần validate tiếp theo phải thất bại theo CAS Protocol.

**Hỏi:** Nếu SAML Assertion có `NameID` và `email` thì SP có thể tin luôn không?  
**Đáp:** Không. Phải xác minh signature, issuer, audience, recipient, thời gian, subject confirmation, request binding và chống replay trước khi dùng claims.

**Hỏi:** API nhận opaque access token thì sao kiểm tra?  
**Đáp:** Dùng introspection tin cậy với AS, kiểm tra `active` và metadata quyền/đối tượng nhận theo policy của API.

**Hỏi:** SSO thành công có đồng nghĩa tất cả ứng dụng/API tự động có quyền không?  
**Đáp:** Không. Mỗi ứng dụng tự tạo/duy trì phiên và áp dụng authorization; mỗi resource server kiểm tra quyền của access token.

## Tài liệu chuẩn để tra cứu

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) – định nghĩa ID token và validation.
- [RFC 6749: OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749) và [RFC 6750: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750) – quyền truy cập và cách sử dụng bearer.
- [RFC 9068: JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068) – profile JWT access token.
- [SAML 2.0 Technical Overview (OASIS)](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html) – cấu trúc SAML, browser SSO và ranh giới tin cậy.
- [CAS Protocol Specification (Apereo)](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html) – service ticket và `/serviceValidate`.
- [Spring Security: SAML2 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html), [OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html), [JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html), [Opaque Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html) – các vai trò và cách cấu hình Spring Security.
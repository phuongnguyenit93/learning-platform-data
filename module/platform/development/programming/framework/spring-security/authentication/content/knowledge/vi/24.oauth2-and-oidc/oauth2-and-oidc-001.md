# Phân biệt OAuth 2.0, OpenID Connect và đăng nhập bằng tài khoản ngoài

## 1. Mục tiêu và vấn đề thường gặp

Trong một ứng dụng Spring Security, ba khái niệm sau hay xuất hiện cạnh nhau:

- **OAuth 2.0 (OAuth2)**: khung giao thức **ủy quyền truy cập tài nguyên**. Một ứng dụng có thể nhận quyền truy cập một API thay mặt người dùng, trong phạm vi và thời hạn được cho phép.
- **OpenID Connect (OIDC)**: lớp **xác thực danh tính** xây dựng trên OAuth 2.0. Nó bổ sung cách tiêu chuẩn để ứng dụng biết ai đã đăng nhập tại nhà cung cấp danh tính.
- **Đăng nhập bằng tài khoản ngoài** (social login/federated login, ví dụ “Đăng nhập với Google”): **chức năng sản phẩm** đưa người dùng từ ứng dụng sang một identity provider, nhận kết quả và tạo phiên đăng nhập nội bộ. Chức năng này có thể triển khai bằng OIDC hoặc bằng OAuth 2.0 kết hợp API profile riêng của nhà cung cấp, tùy khả năng thực tế của provider.

Ví dụ: người dùng bấm **Đăng nhập với Google**. Ứng dụng được Google xác minh danh tính qua luồng OIDC, ánh xạ danh tính Google sang tài khoản nội bộ và tạo phiên Spring Security. Cũng có trường hợp ứng dụng xin quyền đọc lịch Google bằng OAuth 2.0 mà **không** đăng nhập người dùng vào ứng dụng. Đây là hai yêu cầu nghiệp vụ khác nhau.

Sau bài học, người đọc cần phân biệt được **quyền truy cập**, **bằng chứng danh tính**, **tài khoản ứng dụng**, **phiên đăng nhập** và vai trò của từng cơ chế trong Spring Security; đọc được Authorization Code flow; cấu hình ví dụ OIDC Login với Java 17+; biết cách tránh mạo danh, liên kết tài khoản nhầm và dùng token sai mục đích.

## 2. So sánh nhanh bằng cùng một câu hỏi

| Khía cạnh | OAuth 2.0 | OpenID Connect | Đăng nhập bằng tài khoản ngoài |
| --- | --- | --- | --- |
| Câu hỏi chính | “Client được phép truy cập tài nguyên nào?” | “Người dùng nào đã được provider xác thực?” | “Người này sẽ đăng nhập vào tài khoản nào của **ứng dụng**?” |
| Mục đích | Delegated authorization | Authentication + identity claims trên OAuth2 | Trải nghiệm và quy trình đăng nhập/liên kết danh tính |
| Chuẩn/đặc tả | Framework OAuth2 và các RFC liên quan | OIDC Core, Discovery và các đặc tả liên quan | Không phải một giao thức duy nhất |
| Bằng chứng trọng tâm | Access token cho resource server | ID token và quy trình xác minh OIDC | Danh tính provider đã xác minh + ánh xạ tài khoản nội bộ |
| Có chuẩn ID token? | **Không**, chỉ OAuth2 không yêu cầu ID token | **Có**, ID token là JWT theo OIDC | Có khi provider dùng OIDC; có thể không khi provider dùng OAuth2-only |
| Thông tin người dùng | Không phải mục tiêu bắt buộc của OAuth2 core | Claims chuẩn: `sub`, `iss`, có thể `name`, `email`… | Tùy provider và chính sách ứng dụng |
| Có tự tạo quyền nội bộ? | Không | Không | Không; ứng dụng tự quyết định quyền |
| Có tự tạo session đăng nhập ứng dụng? | Không | Không bắt buộc | Ứng dụng thường tạo session/cookie sau khi xác thực thành công |

**Điểm dễ nhầm:** Một access token hợp lệ để gọi API **không tự động** chứng minh rằng client đang sở hữu một phiên đăng nhập đáng tin cậy của đúng người dùng. OAuth2 core không đưa ra giao thức đăng nhập người dùng tiêu chuẩn; OIDC định nghĩa rõ authentication request, ID token, subject, issuer và kiểm tra token.

Khi đánh giá một thiết kế, hỏi lần lượt:

1. Ai xác thực người dùng cuối?
2. Ứng dụng nhận bằng chứng gì và kiểm chứng ra sao?
3. Token nào được cấp cho **đối tượng nhận** nào?
4. Danh tính ngoài được nối với tài khoản cục bộ bằng khóa nào?
5. Sau đó ứng dụng duy trì phiên và quyết định quyền truy cập như thế nào?

## 3. OAuth 2.0: ủy quyền truy cập API

### 3.1. Bốn vai trò

OAuth 2.0 thường có bốn vai trò logic:

- **Resource owner:** người hoặc thực thể sở hữu/kiểm soát quyền truy cập tài nguyên.
- **Client:** ứng dụng muốn truy cập tài nguyên; trong ví dụ là ứng dụng quản lý lịch.
- **Authorization server (AS):** máy chủ xin sự đồng ý/cấp quyền và phát hành token cho client.
- **Resource server (RS):** API chứa tài nguyên được bảo vệ, kiểm tra access token để quyết định phục vụ yêu cầu.

Ví dụ: người dùng của một ứng dụng quản lý lịch cho phép ứng dụng **đọc sự kiện lịch** từ API bên ngoài. Client nhận access token có scope tương ứng rồi gọi API. Không có yêu cầu rằng chủ sở hữu lịch phải dùng chính tài khoản bên ngoài đó để đăng nhập vào ứng dụng quản lý lịch.

Một token có scope như `calendar.read` mô tả **phạm vi truy cập** được cấp, không phải “người dùng có quyền ROLE_ADMIN trong hệ thống của tôi”. Scope của provider và authority của ứng dụng là hai không gian chính sách riêng.

### 3.2. Authorization Code flow (kèm PKCE)

Đây là luồng thông dụng khi browser chuyển hướng người dùng sang provider, sau đó backend đổi mã authorization code lấy token.

```text
Browser              Ứng dụng Spring (OAuth client)         Authorization Server       Resource API
  |                               |                                 |                     |
  | -- bắt đầu kết nối tài khoản ->|                                 |                     |
  |                               |-- tạo state, PKCE challenge ---->|                     |
  |<--------------------- redirect đến authorization endpoint -------|                     |
  |---------------------- đăng nhập và đồng ý ---------------------->|                     |
  |<----------------------- redirect code + state -------------------|                     |
  |---- callback code + state ---->|                                 |                     |
  |                               |-- kiểm tra state                |                     |
  |                               |-- đổi code + PKCE verifier ---->|                     |
  |                               |<--------- access token ----------|                     |
  |                               |---- GET API + Bearer token ------------------------->|
  |                               |<---------------------- dữ liệu API -------------------|
  |<--------- kết quả ------------|                                 |                     |
```

*Giải thích các giá trị:*

- `authorization code` là mã ngắn hạn, dùng một lần để đổi token tại token endpoint. **Không** xem nó là user ID hoặc access token.
- `state` giúp liên kết callback với phiên/authorization request ban đầu, chống request giả mạo và một số lỗi trộn phiên/callback. Ứng dụng phải lưu và kiểm tra giá trị này đúng cách.
- `PKCE` gồm `code_verifier` bí mật cho từng giao dịch và `code_challenge` gửi trước đó, giảm nguy cơ kẻ khác đổi được code bị đánh cắp. Với public client, PKCE là yêu cầu bảo vệ đặc biệt quan trọng; nên áp dụng theo khả năng/hướng dẫn hiện hành cả với confidential client.
- `redirect_uri` phải được đăng ký và kiểm soát chặt. Một redirect đến miền không tin cậy có thể làm lộ code hoặc thay đổi đích callback.
- `access token` gửi đến **resource server** theo kênh bảo vệ (thường `Authorization: Bearer ...`); không tự dùng nó để quyết định danh tính đăng nhập của client.
- `refresh token` có thể được cấp để lấy access token mới khi cần; không phải luồng nào/provider nào cũng cấp.

**Ví dụ một access token:** ứng dụng được người dùng cấp quyền đọc danh sách tệp trên hệ thống bên ngoài. Việc sở hữu token đó không nói rằng ứng dụng phải tạo tài khoản mới hoặc tự cấp quyền quản trị cho người dùng trong database cục bộ.

### 3.3. Access token có thể là JWT hoặc opaque

OAuth2 không bắt buộc access token phải là JWT. Một access token có thể là chuỗi opaque cần được kiểm tra qua introspection; cũng có thể là JWT được resource server tự kiểm tra chữ ký và claims, nếu provider triển khai như vậy.

Đối với API, kiểm tra cần phù hợp với nhà phát hành và kiến trúc: token còn hạn, issuer tin cậy, signature/JWK nếu dùng JWT, audience/resource indicator hợp lệ, scope/quyền phù hợp và các điều kiện bảo mật khác. Không chỉ “decode Base64 thành công” rồi tin payload. Một JWT ký đúng nhưng có `aud` dành cho dịch vụ khác **không** được tự động chấp nhận cho API hiện tại.

## 4. OpenID Connect: thêm lớp xác thực danh tính

OIDC mở rộng OAuth2 để **Relying Party (RP)** có thể xác minh danh tính người dùng đã được **OpenID Provider (OP)** xác thực. Thông thường, ứng dụng gửi authorization request với scope chứa `openid`, nhận authorization code, đổi code tại token endpoint và nhận **ID token** bên cạnh các token liên quan đến OAuth2.

ID token là JWT chứa các claims đã được quy định. Những claim quan trọng:

| Claim | Ý nghĩa | Ứng dụng nên làm gì? |
| --- | --- | --- |
| `iss` | Issuer: định danh provider phát hành ID token | So khớp **đúng issuer được cấu hình**; không tự tin tên miền khác |
| `sub` | Subject: định danh người dùng trong không gian issuer | Dùng với `iss` làm khóa nhận dạng bên ngoài trong mô hình OIDC |
| `aud` | Audience: client ID hoặc các audience nhận token | Phải chứa client ID mong đợi của RP |
| `exp` | Thời hạn hết hiệu lực | Không chấp nhận ID token đã hết hạn |
| `iat` | Thời điểm cấp token | Kiểm tra theo yêu cầu giao thức và chính sách |
| `nonce` | Giá trị ràng buộc yêu cầu/ID token khi đã được gửi | So khớp nonce đã gửi để giảm replay và trộn phiên theo flow |
| `auth_time` | Thời điểm xác thực người dùng, khi có | Dùng cho chính sách yêu cầu xác thực lại, nếu thích hợp |
| `email`, `email_verified`, `name`, `picture` | Claims profile tùy chọn | Chỉ dùng khi được cấp; không biến thành khóa đăng nhập/quyền mặc định |

Trước khi tin ID token, client phải dùng cơ chế kiểm chứng OIDC đúng: nhà phát hành, audience, chữ ký/thuật toán, thời hạn và các ràng buộc `nonce`, `azp` hoặc claim liên quan theo flow. Thư viện chuẩn của Spring Security giúp xử lý các bước tương ứng; không nên tự viết đoạn giải mã JWT rồi lấy `sub` mà bỏ kiểm tra chữ ký và issuer.

### 4.1. Phân biệt user identity và user profile

- `sub` xác định subject trong phạm vi `iss`. Một người có thể có **nhiều** subject ở các provider khác nhau; một số OP cung cấp pairwise subject, có thể khác giữa các client theo quy tắc của OP.
- `email` là thuộc tính có thể thay đổi, có thể thiếu hoặc chưa được xác minh. Kể cả `email_verified=true`, email không tự cấp quyền vào tài khoản nội bộ đã tồn tại.
- `name` và `picture` chủ yếu là dữ liệu hiển thị. Không dùng chúng làm khóa liên kết tài khoản.
- `email_verified` chứng minh nhà cung cấp đã áp dụng quy trình xác minh email theo cách của họ, **không** chứng minh email đó có quyền sở hữu một tài khoản cục bộ bất kỳ hay được phép vào một tenant.

Ví dụ ID token **minh họa payload sau khi đã xác thực**, không phải token thật:

```json
{
  "iss": "https://accounts.example-idp.com",
  "sub": "user-93742",
  "aud": "demo-client-id",
  "exp": 1893456000,
  "iat": 1893452400,
  "email": "alice@example.org",
  "email_verified": true
}
```

**Cần lưu cặp `(iss, sub)` thay vì chỉ lưu `sub`.** Nếu ứng dụng hỗ trợ nhiều issuer, cùng một chuỗi `sub` ở hai issuer không biểu thị cùng một người.

### 4.2. UserInfo khác ID token ra sao?

OIDC định nghĩa **UserInfo Endpoint** để lấy thêm claims về người dùng bằng access token phù hợp. UserInfo dùng cho profile; ID token là bằng chứng xác thực dành cho RP. Nếu lấy UserInfo, phải bảo đảm subject trong response khớp subject đã xác thực từ ID token theo quy định của OIDC. Đừng xem phản hồi của một URL hồ sơ bất kỳ là ID token.

OIDC có discovery metadata tại đường dẫn chuẩn và JWK Set để tìm cấu hình provider/khóa xác minh. Ứng dụng nên dùng issuer đã chọn trong cấu hình và thư viện chuẩn; không lấy issuer hoặc JWK URL tùy ý từ request người dùng rồi tải để xác thực.

## 5. Các loại giá trị thường bị nhầm

| Giá trị | Được tạo bởi | Được dùng ở đâu? | Không nên dùng để… |
| --- | --- | --- | --- |
| Authorization code | Authorization server | Client đổi code lấy token | Gọi API hoặc nhận dạng người dùng trực tiếp |
| Access token | Authorization server | Resource server kiểm tra quyền truy cập API | Thay ID token để xác thực login ở RP |
| ID token (OIDC) | OpenID Provider | Relying Party xác nhận người dùng đã đăng nhập | Gọi API không được cấu hình nhận ID token |
| Refresh token | Authorization server, nếu cấp | Client dùng với token endpoint để xin token mới | Gửi tới resource server hoặc frontend không an toàn |
| App session cookie | Ứng dụng | Browser gửi để tiếp tục phiên ứng dụng | Chứng minh quyền truy cập API của provider |
| Local user ID | Ứng dụng | Khóa chính database, audit, quan hệ tài khoản | Thay thế xác minh danh tính của provider |

Hãy tách ba sự kiện:

1. **Người dùng được provider xác thực:** có thể tạo ID token theo OIDC.
2. **Client được cấp quyền gọi API:** client có access token đúng scope/audience.
3. **Ứng dụng đăng nhập người dùng vào hệ thống mình:** ánh xạ danh tính ngoài, áp dụng kiểm tra tài khoản nội bộ, tạo `Authentication` và phiên/cơ chế duy trì phù hợp.

Một sản phẩm có thể thực hiện cả ba, nhưng đó là các bước có điều kiện khác nhau.

## 6. “Login with Google” thực sự làm gì?

Xét chức năng “Đăng nhập bằng tài khoản ngoài” của một website:

```text
Người dùng ở ứng dụng
    |
    | Bấm "Đăng nhập với Google"
    v
Ứng dụng bắt đầu OIDC Authorization Code flow
    |
    v
Google xác thực người dùng (và xử lý consent nếu cần)
    |
    v
Ứng dụng nhận callback; Spring Security xác minh state,
đổi authorization code, kiểm chứng ID token
    |
    v
Lấy issuer + subject từ danh tính đã xác minh
    |
    +-- Tìm thấy identity đã liên kết ---> lấy local_user_id
    |
    +-- Chưa tìm thấy ---------------> chính sách đăng ký / liên kết an toàn
    |
    v
Kiểm tra local user: active? tenant? role? policy?
    |
    v
Tạo Authentication / session của ứng dụng
    |
    v
Người dùng truy cập tính năng theo quyền NỘI BỘ
```

**Đăng nhập ngoài không đồng nghĩa với nhập password vào ứng dụng.** Ứng dụng không nên yêu cầu mật khẩu Google để tự kiểm tra; provider xử lý credential trong giao thức chuyển hướng phù hợp. Ứng dụng thường không bao giờ nhận mật khẩu của provider.

Chức năng này cũng **không tự động chứng minh người dùng có role quản trị nội bộ**. Một ID token có `email=admin@example.org`, kể cả email đã xác minh, vẫn chưa đủ để cấp `ROLE_ADMIN` nếu ứng dụng chưa áp dụng chính sách tài khoản và phân quyền.

### 6.1. Social login có bắt buộc dùng OIDC không?

Không. Nếu provider hỗ trợ OIDC, đây thường là lựa chọn tốt cho **authentication** nhờ ID token/issuer/subject/Discovery chuẩn. Nhưng một số dịch vụ hỗ trợ OAuth2 authorization và API lấy profile theo hợp đồng riêng; ứng dụng có thể dùng flow OAuth2 và truy vấn profile để xây tính năng đăng nhập. Khi đó:

- OAuth2 core tự nó **không** chuẩn hóa bằng chứng đăng nhập.
- Phải kiểm tra rõ provider nào, endpoint profile nào, cách xác định user ID ổn định, phạm vi access token và đường truyền.
- Không giả định sẽ có ID token hoặc claims chuẩn `iss`/`sub` nếu provider không triển khai OIDC.
- Chuẩn hóa identity riêng cho provider, nhưng không tự phát minh giá trị issuer giống OIDC mà không có hợp đồng.

Như vậy “OAuth2 login” trong tên API/framework đôi khi diễn tả **workflow có thể đưa tới login**, không có nghĩa bản thân OAuth2 đã trở thành một giao thức authentication có ID token.

## 7. Ánh xạ tài khoản bên ngoài vào tài khoản nội bộ

Đây là phần hay bị bỏ qua khi chỉ demo bấm nút đăng nhập.

Giả sử database có:

```sql
CREATE TABLE app_user (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE external_identity (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    app_user_id BIGINT NOT NULL REFERENCES app_user(id),
    provider_key VARCHAR(512) NOT NULL,
    provider_subject VARCHAR(255) NOT NULL,
    UNIQUE (provider_key, provider_subject)
);
```

Thiết kế trên là **minh họa schema**, cần bổ sung tenant, audit, chính sách dữ liệu và migration theo hệ thống. Đối với OIDC, `provider_key` thường là **issuer đã xác minh**, còn `provider_subject` là `sub` từ ID token. Với OAuth2-only provider, dùng namespace provider/registration đã kiểm soát và user ID ổn định theo hợp đồng provider (không coi nó là OIDC `sub`).

Quy trình an toàn:

1. Hoàn tất login/nhận identity provider bằng thư viện chính thức; chỉ xử lý thông tin **sau khi** callback, token hoặc response cần thiết đã được xác minh.
2. Tra bảng `external_identity` theo khóa danh tính bên ngoài. Nếu đã tồn tại, lấy `app_user_id` rồi kiểm tra `active`/tenant/quyền trước khi cho đăng nhập.
3. Nếu chưa tồn tại, áp dụng chính sách sản phẩm: tự tạo tài khoản mới nếu được phép, yêu cầu người dùng chọn tạo tài khoản, hoặc đề nghị **liên kết** với một tài khoản nội bộ đang đăng nhập.
4. Khi liên kết, yêu cầu chứng minh quyền kiểm soát cả **phiên tài khoản nội bộ** và **danh tính bên ngoài**; với thao tác nhạy cảm nên có xác thực lại. Ghi bản ghi quan hệ trong transaction, dựa trên UNIQUE constraint để xử lý truy cập đồng thời.
5. Nếu người dùng ngắt liên kết, bảo đảm còn phương thức khôi phục đăng nhập thích hợp, audit thay đổi và thu hồi token khi cần.

**Không tự liên kết hai tài khoản chỉ vì email trùng.** Email có thể được tái sử dụng, thay đổi, bị chuyển quyền quản lý, không có `email_verified` hoặc không chứng minh quan hệ với tài khoản cục bộ. Tính năng “gộp tài khoản” phải có consent/chứng minh sở hữu và chính sách riêng.

**Không trộn quyền ngoài với quyền nội bộ.** Scope `profile`/`email` hoặc provider group claim không mặc nhiên tương đương `ROLE_USER`/`ROLE_ADMIN`. Nếu muốn ánh xạ nhóm IdP vào role, hãy dùng mapping được quản trị, nguồn claim tin cậy và khả năng thu hồi rõ ràng.

### 7.1. Ví dụ hai provider cùng email

Giả sử OIDC provider A cấp `iss=https://idp-a.example`, `sub=123`; provider B cấp `iss=https://idp-b.example`, `sub=123`. Hai account **khác danh tính** dù `sub` trùng. Ngược lại, cùng một người dùng có thể có `sub` khác nhau ở hai provider. Ứng dụng phải nối chúng thông qua một luồng liên kết có kiểm chứng, không phán đoán bằng tên/email.

## 8. Spring Security: ba nhóm tính năng khác nhau

Với Spring Security Servlet (Java 17+, Spring Boot 3.x, Spring Security 6.x), nhìn tên API sau để biết hệ thống đang giải quyết vấn đề nào:

| Spring Security API | Vai trò | Ví dụ |
| --- | --- | --- |
| `http.oauth2Login(...)` | Ứng dụng web đăng nhập bằng provider, hỗ trợ OIDC login và các tích hợp OAuth2 login phù hợp | “Đăng nhập với Google”, tạo authenticated principal/session |
| `http.oauth2Client(...)` + `OAuth2AuthorizedClient` | Ứng dụng làm OAuth2 client, giữ token được cấp để gọi API ngoài theo ủy quyền | Đọc lịch/tệp từ API của provider |
| `http.oauth2ResourceServer(...)` | API của ứng dụng **nhận Bearer access token** và kiểm tra token theo cấu hình | Backend REST chấp nhận JWT/opaque access token |
| `oauth2Login().userInfoEndpoint(...)` | Tùy chỉnh cách lấy và ánh xạ thông tin user sau login | `OAuth2UserService`, `OidcUserService` |
| `OAuth2AuthenticationToken` | Kết quả login trong Spring Security | Có principal, authorities, registration ID |
| `OidcUser` và `OAuth2User` | Principal sau OIDC login hoặc OAuth2 provider profile | Đọc identity/profile theo đúng kiểu |

Cùng một ứng dụng **có thể** vừa login người dùng bằng OIDC vừa dùng authorized client để gọi API của provider; nhưng đừng bật resource server chỉ vì có “Login with Google”. Resource server bảo vệ API bằng các access token **dành cho API ấy**, không lấy ID token của website làm Bearer access token.

Với Spring WebFlux, các tên khái niệm tương tự nhưng dùng `ServerHttpSecurity`/`SecurityWebFilterChain`, và APIs reactive. Ví dụ bên dưới chỉ dành cho Servlet/MVC, không copy `HttpSecurity` vào WebFlux.

## 9. Ví dụ Spring Boot: OIDC Login bằng Google

Ví dụ này xây dựng **một ứng dụng web mẫu dùng login qua Google OIDC**, hiển thị provider registration và subject sau khi đăng nhập. Nó minh họa tích hợp framework; để chạy thật phải có OAuth client ID/secret của một project trong Google Cloud và redirect URI đã đăng ký. Ứng dụng ví dụ chưa có database ánh xạ tài khoản nội bộ, nên **không nên xem là đã hoàn thành chức năng liên kết account trong production**.

### 9.1. Dependencies

Với project Spring Boot 3.x có Gradle plugin và dependency management của Spring Boot, trong `build.gradle` có thể dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-boot-starter-oauth2-client` tích hợp các thư viện OAuth2/OIDC client; với trường hợp chỉ là website login, không cần bắt đầu bằng `spring-boot-starter-oauth2-resource-server`.

### 9.2. Cấu hình client registration

Tạo `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope:
              - openid
              - profile
              - email
```

Ở ví dụ này Spring Boot/Spring Security có cấu hình provider mặc định cho Google. Từ registration ID `google`, Spring Security dùng endpoint tương ứng của provider. Không dùng các giá trị secret giả như thông tin production; lấy từ biến môi trường/secret manager, không commit `client-secret` lên Git.

Đăng ký **redirect URI** trong phần cấu hình OAuth client của provider, ví dụ khi chạy local:

```text
http://localhost:8080/login/oauth2/code/google
```

Mẫu callback mặc định: `{baseUrl}/login/oauth2/code/{registrationId}`. Khi deploy qua reverse proxy phải bảo đảm public `baseUrl` và scheme/host được cấu hình đúng, tránh sai redirect URI. Production cần HTTPS, secret management và cấu hình forwarded headers **chỉ tin proxy được phép**.

Scope `openid` kích hoạt OIDC; `profile`/`email` xin thêm claims có thể được provider trả về theo chính sách. Có scope `email` **không** bảo đảm email luôn có hoặc luôn verified.

### 9.3. SecurityFilterChain

Các file Java đặt trong `src/main/java/com/example/externallogin/`.

**`ExternalLoginApplication.java`**

```java
package com.example.externallogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExternalLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExternalLoginApplication.class, args);
    }
}
```

**`SecurityConfig.java`**

```java
package com.example.externallogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(requests -> requests
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
```

`oauth2Login(...)` cấu hình quy trình redirect/authorization callback, đổi code, nạp thông tin người dùng và xác thực OIDC khi provider/registration phù hợp. Nó không khiến website nhận mật khẩu Google. Mặc định Spring Security có thể sinh trang chọn nhà cung cấp đăng nhập cho các client registration tương ứng.

**Không tắt CSRF vô điều kiện** khi xây website dùng browser session. CSRF, state, SameSite cookies, session fixation, TLS và logout cần được đánh giá theo kiểu ứng dụng. Ví dụ giữ cấu hình mặc định của Spring Security cho các bảo vệ liên quan.

### 9.4. Controller đọc kết quả đăng nhập

**`ProfileController.java`**

```java
package com.example.externallogin;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ProfileController {

    @GetMapping("/")
    public String index() {
        return "Đăng nhập tại /oauth2/authorization/google";
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        if (!(authentication instanceof OAuth2AuthenticationToken login)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        OAuth2User user = login.getPrincipal();
        Map<String, String> result = new LinkedHashMap<>();
        result.put("registrationId", login.getAuthorizedClientRegistrationId());

        if (user instanceof OidcUser oidcUser) {
            result.put("type", "OIDC");
            result.put("issuer", oidcUser.getIdToken().getClaimAsString("iss"));
            result.put("subject", oidcUser.getIdToken().getSubject());
        } else {
            result.put("type", "OAuth2 provider profile");
            result.put("providerUserId", user.getName());
        }

        return result;
    }
}
```

Điểm cần hiểu:

- `OAuth2AuthenticationToken` là authentication được Spring Security tạo sau flow thành công; `getAuthorizedClientRegistrationId()` cho biết client registration được dùng (ví dụ `google`). Đây là **tên cấu hình cục bộ**, không tự nó là issuer.
- Nếu principal là `OidcUser`, ta lấy `iss` và `sub` từ ID token mà framework đã xác minh. Hai giá trị này phù hợp làm khóa tìm tài khoản ngoài trong mô hình OIDC.
- Nếu provider là OAuth2-only, `OAuth2User.getName()` phụ thuộc thuộc tính ID được cấu hình cho provider profile. Nó **không phải** bằng chứng OIDC chuẩn; ứng dụng phải hiểu hợp đồng profile của provider.
- Ví dụ chỉ hiển thị trường định danh tối thiểu, **không** trả access token, refresh token hoặc toàn bộ ID token cho frontend. Trong production, trả local user ID/quyền phù hợp sau khi đã xử lý ánh xạ tài khoản nội bộ.

### 9.5. Chạy thử local

Đặt biến môi trường trong shell phù hợp trước khi chạy project. Trên Linux/macOS:

```bash
export GOOGLE_CLIENT_ID='your-client-id'
export GOOGLE_CLIENT_SECRET='your-client-secret'
./gradlew bootRun
```

Trên PowerShell:

```powershell
$env:GOOGLE_CLIENT_ID = 'your-client-id'
$env:GOOGLE_CLIENT_SECRET = 'your-client-secret'
.\gradlew.bat bootRun
```

Mở URL trên trình duyệt:

```text
http://localhost:8080/oauth2/authorization/google
```

Trang sẽ chuyển hướng tới Google. Sau khi đăng nhập và hoàn tất callback, truy cập:

```text
http://localhost:8080/me
```

Một phản hồi **minh họa cấu trúc** (issuer và subject thực tế tùy provider):

```json
{
  "registrationId": "google",
  "type": "OIDC",
  "issuer": "https://accounts.google.com",
  "subject": "some-provider-subject"
}
```

Đây là response mẫu, không phải output đã chạy từ tài khoản người dùng. **Không** đưa email, subject hoặc secret thực vào bài viết/log production.

## 10. Kiểm thử Spring Security mà không gọi provider thật

Với `spring-security-test`, có thể mô phỏng user đã đăng nhập thông qua `oidcLogin()` để kiểm tra controller và authorization, không cần kết nối với Google thật trong test. Đây là kiểm thử **logic phía ứng dụng sau login**, không kiểm tra HTTP redirect, code exchange hoặc JWK của provider.

Tạo `src/test/java/com/example/externallogin/ProfileControllerTest.java`:

```java
package com.example.externallogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "spring.security.oauth2.client.registration.google.client-id=test-client",
        "spring.security.oauth2.client.registration.google.client-secret=test-secret"
})
@AutoConfigureMockMvc
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void showsValidatedOidcIdentityToAuthenticatedUser() throws Exception {
        mvc.perform(get("/me").with(oidcLogin()
                        .idToken(token -> token
                                .claim("iss", "https://idp.example")
                                .claim("sub", "subject-42"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.type").value("OIDC"))
                .andExpect(jsonPath("$.issuer").value("https://idp.example"))
                .andExpect(jsonPath("$.subject").value("subject-42"));
    }

    @Test
    void protectedEndpointRedirectsAnonymousUserToLogin() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }
}
```

Chạy `./gradlew test` (Windows: `.\gradlew.bat test`) trong project Boot có wrapper. Kết quả **kỳ vọng**: cả hai test pass khi cấu hình phù hợp. Test dùng `oidcLogin()` đưa principal giả lập qua Spring Security Test; **không** thể chứng minh tính xác thực của ID token ở nhà cung cấp. Cần integration test riêng với một OIDC provider giả lập/kiểm soát được, kiểm tra state, callback, chữ ký, issuer, audience, expiry, logout và failure path.

Nếu test callback end-to-end, không dùng kết quả từ `oidcLogin()` để kết luận provider đã bảo vệ state/nonce đúng trong production; test unit/controller và test giao thức có phạm vi khác nhau.

## 11. Tùy chỉnh xử lý account sau login

Tài liệu Spring Security có hai extension point thường gặp:

- `DefaultOAuth2UserService` / `OAuth2UserService<OAuth2UserRequest, OAuth2User>` cho provider OAuth2 profile (không OIDC).
- `OidcUserService` / `OAuth2UserService<OidcUserRequest, OidcUser>` cho OIDC login, khi cần nạp và chuyển đổi user details/claims.

Khi tích hợp database nội bộ, có thể bọc một service mặc định, cho service ấy tải/kiểm tra dữ liệu provider bằng flow chuẩn, rồi **sau khi xác thực thành công** tra bảng `external_identity`, kiểm tra local account và đưa authorities nội bộ vào principal theo chính sách. Với quy trình liên kết, cần xử lý trường hợp chưa có local account bằng trang/flow riêng; không tự cấp role từ email tùy ý.

Mô hình **pseudocode** để làm rõ nghiệp vụ, không phải mã Spring Security chạy độc lập:

```text
verified = springSecurityOidcLoginResult()
identityKey = (verified.issuer, verified.subject)

link = externalIdentityRepository.find(identityKey)
if (link exists) {
    user = localUserRepository.findById(link.localUserId)
    require user.active && tenantPolicyAllows(user)
    issueLocalSessionFor(user)
} else {
    require allowedRegistrationOrExplicitLinkingFlow()
    // Create account or link only after the required proof/consent.
    finishOnboardingOrLink()
}
```

Sở dĩ là pseudocode: API/controller xử lý yêu cầu chưa liên kết, transaction database, principal mapping, exception handling và session persistence phải được thiết kế theo kiến trúc ứng dụng. Đặc biệt, **không** bắt mọi `OAuth2AuthenticationException` rồi tự tạo session khi issuer/subject chưa được xác minh.

## 12. Bảo mật: điều gì có thể sai?

### 12.1. Login CSRF và đánh tráo callback

Nếu ứng dụng không ràng buộc callback với authorization request do chính browser đã khởi tạo, attacker có thể tìm cách làm nạn nhân đăng nhập nhầm account. `state` và cách lưu authorization request an toàn chống loại tấn công này; PKCE bổ sung bảo vệ code; `nonce` của OIDC gắn kết ID token với authentication request khi được dùng. Không bỏ qua cơ chế mặc định chỉ để “đăng nhập được nhanh”.

### 12.2. Nhầm token / nhầm đối tượng nhận

- **ID token** dành cho RP để xác thực người dùng. Không gửi nó thay access token đến API vốn chỉ nhận access token.
- **Access token** dành cho resource server. Một access token của provider khác, hoặc audience không khớp, không phải credential hợp lệ cho API của ứng dụng.
- **Refresh token** nhạy cảm, nên được lưu an toàn phía backend phù hợp với kiểu client; không trả về response JSON cho browser như trường thông tin profile.
- Đừng log token trong URL, query string, exception, access log hoặc analytics.

### 12.3. Nhầm issuer hoặc subject

Nếu ứng dụng chấp nhận ID token từ issuer không nằm trong danh sách tin cậy, hoặc chỉ dùng `sub` mà không gắn issuer, có thể liên kết nhầm tài khoản. Với nhiều provider/tenant, phải định nghĩa danh sách issuer được phép và lưu identity key phân tách.

### 12.4. Nguy cơ khi tự liên kết qua email

Email có thể đổi, bị thu hồi/tái sử dụng, hoặc giống với email của local user mà không chứng minh quyền kiểm soát account nội bộ. Việc tự gộp qua email có thể tạo account takeover. Chỉ liên kết theo chính sách có chứng minh sở hữu, hành động có consent và transaction với unique constraint.

### 12.5. Đăng nhập và phân quyền là hai bước

Login từ bên ngoài chỉ chứng minh người dùng đã hoàn tất flow theo provider. Sau đó vẫn phải kiểm tra account nội bộ, role, tenant, trạng thái suspended/deleted, quy tắc truy cập tài nguyên và các yêu cầu MFA/step-up theo chính sách.

Một người đăng nhập Google thành công **không** mặc nhiên có quyền xem dữ liệu của mọi người có email cùng miền. Cũng không dùng `profile` hay `email` scope làm quyền quản trị.

### 12.6. Session, logout và thu hồi

Sau `oauth2Login()`, Spring Security thường duy trì phiên web qua server-side security context và cookie. Logout khỏi ứng dụng không đương nhiên đăng xuất khỏi Google/IdP; ngược lại, IdP logout không tự phá hủy mọi session ứng dụng. Muốn single logout phải thiết kế theo cơ chế chuẩn/provider hỗ trợ, có redirect và kiểm tra thích hợp. Khi tài khoản nội bộ bị khóa hoặc đổi quyền, ứng dụng cần chính sách cập nhật/thu hồi session tương ứng.

Trong ứng dụng chạy nhiều instance, cần xác định session repository, cookie bảo mật, thời gian sống và chính sách khôi phục login. Nếu dùng frontend SPA không có session backend truyền thống, chọn kiến trúc đăng nhập/token an toàn phù hợp thay vì đơn giản copy flow của MVC.

## 13. Hướng dẫn chọn cơ chế theo nhu cầu

| Nhu cầu thực tế | Thành phần chính | Kết quả mong đợi |
| --- | --- | --- |
| Người dùng bấm “Đăng nhập với Google” trên website | OIDC authorization code + `oauth2Login` + account mapping | User identity đã xác minh → local principal/session |
| Ứng dụng đọc lịch của người dùng ở một dịch vụ khác | OAuth2 client, scopes, access token và refresh nếu có | API call được ủy quyền |
| Mobile app/SPA gọi REST API của backend có token từ trusted AS | Resource server, kiểm tra Bearer access token | API chấp nhận/từ chối dựa trên issuer/audience/scope |
| Nhận danh tính từ nhiều tenant hoặc provider | OIDC issuer validation và ánh xạ `(iss,sub)` | Không lẫn tài khoản giữa providers/tenants |
| Provider chỉ hỗ trợ OAuth2 và API profile riêng | OAuth2 flow + profile API đã xác thực, hợp đồng provider rõ ràng | Đăng nhập ngoài theo tích hợp provider-specific |
| Liên kết Google với tài khoản đã tạo bằng mật khẩu cục bộ | Link flow có re-auth/consent và transaction | Một local user có nhiều external identities hợp lệ |

**Quy tắc chọn:** Nếu ứng dụng cần **biết ai đang đăng nhập**, ưu tiên OIDC với issuer/subject chuẩn khi nhà cung cấp hỗ trợ. Nếu cần **quyền gọi API**, dùng OAuth2 access token theo scope/audience. Nếu cần “đăng nhập bằng tài khoản ngoài”, còn phải thiết kế bước **ánh xạ danh tính vào local account và cấp quyền nội bộ**.

## 14. Câu hỏi tự kiểm tra và tình huống

1. Ứng dụng chỉ nhận access token để đọc Google Calendar. Tại sao đây chưa phải bằng chứng một user đã đăng nhập website? Nếu muốn đăng nhập, cần thêm thành phần nào?
2. ID token có `sub=123` từ issuer A và ID token khác có `sub=123` từ issuer B. Có nên ánh xạ chung một tài khoản? Giải thích.
3. Người dùng có `email_verified=true` với email giống một local admin. Có được tự động cấp `ROLE_ADMIN` hoặc nối account không? Thiết kế quy trình an toàn.
4. Phân biệt cách dùng `ID token` và `access token` khi ứng dụng đồng thời login bằng OIDC và gọi API bên ngoài.
5. Một API Spring Boot nhận Bearer JWT từ client nhưng chỉ bật `oauth2Login()`. Thiếu cơ chế nào để bảo vệ API? Token được chấp nhận phải thỏa những ràng buộc gì?
6. Khi xuất hiện lỗi `redirect_uri_mismatch` hoặc `invalid_state_parameter`, cần kiểm tra các yếu tố nào ở browser session, callback, proxy và provider?
7. Viết integration test với provider kiểm soát được để chứng minh ứng dụng từ chối ID token sai issuer, sai audience, hết hạn và response có state không khớp. Giải thích vì sao test `oidcLogin()` ở mức MVC không đủ.

## 15. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| “OAuth2 = đăng nhập” | Nhầm delegated authorization thành user authentication | Phân biệt OAuth2 và OIDC; xác định mục đích request |
| Gọi API bằng ID token | Token dành sai audience/resource | Dùng access token được cấp cho API |
| Lấy JWT payload rồi tin `sub` | Có thể tin token giả, sai issuer/audience/expiry | Dùng thư viện OIDC/JWT validator đúng flow |
| Chỉ lưu `sub` | Hai issuer có thể cấp cùng sub | Dùng cặp `(iss,sub)` trong OIDC |
| Dùng email làm khóa định danh bất biến | Lẫn tài khoản/chiếm quyền khi email thay đổi | Dùng provider subject; liên kết có chứng minh sở hữu |
| Tự cấp `ROLE_ADMIN` theo scope/email | Lỗi phân quyền ứng dụng | Ánh xạ role từ nguồn nội bộ hoặc policy đã thẩm định |
| Tắt `state`/CSRF/PKCE cho đỡ lỗi | Dễ bị callback tampering/login CSRF/code interception | Sửa đúng cấu hình redirect, session và provider |
| Trả access/refresh token ra response `/me` | Lộ credential có thể gọi API | Chỉ trả metadata cần thiết; lưu token an toàn |
| Giả định logout ứng dụng = logout provider | Người dùng vẫn có phiên IdP và login lại không cần password | Thiết kế rõ session và single logout nếu có |
| Bật `oauth2ResourceServer` để “sửa login” | Nhầm client login với resource-server validation | Bật đúng security capability theo đường đi |
| Không kiểm tra redirect qua reverse proxy | Callback sai host/scheme, có thể mở rộng nguy cơ bảo mật | Cấu hình proxy/forwarded headers từ nguồn tin cậy và URI đã đăng ký |

## 16. Ghi nhớ và tài liệu tham khảo

- **OAuth2 = delegated authorization:** access token phục vụ quyền truy cập tài nguyên.
- **OIDC = authentication trên nền OAuth2:** ID token có issuer, subject và audience, cần được kiểm chứng đúng.
- **Đăng nhập bằng tài khoản ngoài = một flow nghiệp vụ:** xác thực ở provider, ánh xạ người dùng vào hệ thống, kiểm tra quyền và tạo session.
- **Không dùng email/role từ profile một cách mù quáng.** Account linking cần danh tính ổn định và cơ chế chứng minh quyền sở hữu.
- **Spring Security có những capability khác nhau:** `oauth2Login`, `oauth2Client` và `oauth2ResourceServer` phục vụ các vấn đề riêng, dù một hệ thống có thể dùng kết hợp.

Đọc thêm tại tài liệu chuẩn: [Spring Security Servlet OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html), [OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html), [Testing OAuth2/OIDC với MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html), [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html), [OAuth 2.0 Authorization Framework (RFC 6749)](https://www.rfc-editor.org/rfc/rfc6749), [OAuth 2.0 PKCE (RFC 7636)](https://www.rfc-editor.org/rfc/rfc7636) và [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://www.rfc-editor.org/rfc/rfc9700).
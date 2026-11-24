# Subject identifier

## 1. Vì sao cần hiểu subject identifier?

Trong chương **OpenID Connect** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, **subject identifier** là nền tảng giúp ứng dụng biết **người dùng nào đã được OpenID Provider xác thực**, rồi liên kết người dùng đó với một tài khoản nội bộ theo chính sách. Trong OpenID Connect (OIDC), subject identifier được biểu diễn bằng claim **`sub`**.

Giả sử Alice đăng nhập ứng dụng **Shop Web** qua **OpenID Provider (OP)** tại `https://login.example.com`. Sau Authorization Code flow, Shop Web nhận một **ID token** đã được xác minh:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "usr_7Jx3qA2",
  "aud": "shop-web",
  "iat": 1893492000,
  "exp": 1893492300
}
~~~

Đây chỉ là **payload minh họa**, không phải JWT có chữ ký. Trong ứng dụng thật, Shop Web phải xác minh token theo đặc tả OIDC trước khi tin bất kỳ claim nào.

Claim `sub` trả lời câu hỏi:

> **Trong phạm vi issuer đã xác minh, đây là subject nào?**

Nó **không tự trả lời**:

- Alice có email gì, tên hiển thị nào, vai trò admin hay thuộc tenant nào?
- Alice có quyền xem đơn hàng `order-721` hay không?
- ID token có thể dùng làm access token gọi Orders API hay không?
- `sub` ở một issuer khác có chỉ cùng người dùng hay không?

Để tránh nhầm danh tính và ranh giới tin cậy, ứng dụng nên nhận diện một external identity bằng cặp **`(iss, sub)`**, không chỉ một chuỗi `sub` hoặc email.

### 1.1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Đọc và giải thích chính xác ngữ nghĩa, phạm vi duy nhất và tính ổn định của claim `sub`.
2. Hiểu tại sao **`(iss, sub)`** là khóa liên kết external identity và vì sao `sub` không được tự coi là email, username hay quyền truy cập.
3. Phân biệt hai kiểu subject identifier trong OIDC: **`public`** và **`pairwise`**.
4. Hiểu **Sector Identifier**, `sector_identifier_uri`, quan hệ với redirect URI và tác động đến quyền riêng tư.
5. Đối chiếu `sub` của **ID token** và **UserInfo response**, xử lý token substitution và issuer mix-up.
6. Thiết kế mapping user nội bộ, account linking, migration issuer/sector, multi-tenant và đồng bộ dữ liệu an toàn.
7. Viết kiểm thử và ví dụ Java/Spring Security/SQL tránh merge nhầm tài khoản hoặc cấp quyền vượt phạm vi.

## 2. Ngữ nghĩa chuẩn của `sub` trong OIDC

Theo **OpenID Connect Core 1.0**, `sub` là *Subject Identifier*: một định danh **duy nhất cục bộ trong phạm vi Issuer** của End-User và **không được tái cấp cho người dùng khác**. Đây là claim **bắt buộc** trong ID token OIDC.

Các thuộc tính quan trọng:

| Thuộc tính | Điều phải hiểu |
|---|---|
| Tên claim | `sub`, viết thường đúng theo chuẩn |
| Kiểu dữ liệu | Chuỗi (**string**), không phải số nguyên |
| Phạm vi duy nhất | Trong ngữ cảnh **issuer** và cơ chế subject type/sector của OP |
| Tính nhạy với chữ hoa/thường | **Có**: `Alice-7` khác `alice-7` |
| Độ dài | Theo OIDC Core, **không quá 255 ký tự ASCII** |
| Tái cấp cho user khác | **Không được** trong phạm vi nhận diện tương ứng |
| Tính chất định danh cá nhân | **Không nhất thiết** là email, tên thật hoặc số điện thoại |
| Tính chất bí mật | **Không phải mật khẩu/token**; vẫn có thể là dữ liệu liên kết danh tính cần bảo vệ |
| Dùng làm quyền | **Không**; phải kiểm tra authorization riêng |

Ví dụ đúng ở cấp ứng dụng:

~~~text
issuer = https://login.example.com
subject = usr_7Jx3qA2

External identity key:
  (https://login.example.com, usr_7Jx3qA2)
~~~

Ví dụ không nên giả định:

~~~text
sub = alice@example.com  => email luôn đúng/không đổi
sub = 000123             => được parse thành số 123
sub = admin              => role=ADMIN
sub = usr_7Jx3qA2       => cùng user ở mọi issuer
~~~

### 2.1. `sub` là opaque identifier đối với client

Client nên xem subject string là **giá trị opaque**: lưu, so sánh chính xác và không suy diễn cấu trúc nội bộ. Dù hiện tại issuer phát chuỗi dạng `usr_1234`, một ngày nó có thể dùng chuỗi ngẫu nhiên dài hoặc subject pairwise.

Không làm:

~~~java
// SAI: coi subject là số, có thể mất số 0 đầu và sai kiểu dữ liệu.
long userId = Long.parseLong(sub);

// SAI: suy role/tenant từ tiền tố subject không có hợp đồng.
boolean isAdmin = sub.startsWith("admin_");

// SAI: chuẩn hóa subject tùy tiện, có thể gộp hai danh tính.
String normalizedSub = sub.toLowerCase();
~~~

Không được tự trim, lowercase, URL-decode, Unicode-normalize hay cắt chuỗi `sub` trước khi so sánh nếu không có hợp đồng được kiểm soát; cách an toàn là **so sánh giá trị string chính xác do issuer đã được xác minh trả về**.

### 2.2. `sub` không có nghĩa giống nhau giữa các issuer

Hai OP độc lập có thể cùng phát:

~~~json
{"iss":"https://login.company-a.example","sub":"12345"}
~~~

và:

~~~json
{"iss":"https://login.partner-b.example","sub":"12345"}
~~~

Hai cặp này là **hai external identities khác nhau**. Nếu ứng dụng chỉ lưu `sub=12345`, Alice từ OP A có thể bị gắn nhầm vào tài khoản Bob từ OP B.

**Khóa identity tối thiểu ở cấp OIDC là `issuer + subject`**, cùng các kiểm tra token đã hoàn thành. Các thuộc tính bổ sung như tenant/organization/client registration có thể cần cho chính sách ứng dụng, nhưng không được thay thế issuer binding.

### 2.3. `sub` không phải quyền truy cập

Giả sử Shop Web xác minh ID token và tạo session cho Alice:

~~~text
iss = https://login.example.com
sub = usr_7Jx3qA2
local_user_id = 42
~~~

Khi Alice gọi:

~~~http
GET /api/orders/order-999 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <ACCESS_TOKEN>
~~~

Orders API còn phải kiểm tra access token có **issuer, audience, thời gian, scope/token type** đúng và Alice có quyền với **order-999**. `sub` hoặc phiên đăng nhập hợp lệ không tự cho phép đọc mọi đơn hàng.

## 3. ID token, access token và UserInfo: cùng có `sub` nhưng khác vai trò

OIDC xây trên OAuth 2.0, nhưng **xác thực danh tính ở client** và **ủy quyền truy cập resource** là hai mục đích khác nhau:

| Thành phần | Đối tượng sử dụng chính | Vai trò của `sub` |
|---|---|---|
| **ID token** | OIDC client/Relying Party (RP) | Khẳng định subject End-User đã được OP xác thực cho client |
| **UserInfo response** | OIDC client gọi UserInfo endpoint | Cung cấp claims về End-User, bắt buộc có `sub` để đối chiếu |
| **OAuth access token** | Resource Server như Orders API | Có thể có subject theo token profile; là credential **API**, không phải ID token |
| **Refresh token** | Client gửi về AS/token endpoint | Dùng xin access token mới theo grant; không phải object ID của user |
| **Authorization code** | Client đổi code ở token endpoint | Không phải subject identifier |

Không được dùng ID token để gọi Orders API chỉ vì JWT chứa `sub` và có chữ ký đúng. ID token có **audience là client**, trong khi access token phải đáp ứng audience/token profile của resource server.

### 3.1. ID token tối thiểu cần xác minh

Ví dụ payload:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "usr_7Jx3qA2",
  "aud": "shop-web",
  "exp": 1893492300,
  "iat": 1893492000,
  "nonce": "example-random-nonce"
}
~~~

Một OIDC client cần xác minh theo profile:

1. Chữ ký/thuật toán và khóa của **issuer đã tin cậy**, hoặc cơ chế bảo mật ID token tương ứng.
2. `iss` chính xác là issuer đã cấu hình/chọn cho authorization request.
3. `aud` chứa client ID đúng; kiểm tra `azp` khi các điều kiện của OIDC Core yêu cầu.
4. `exp`, `iat` và các điều kiện thời gian khác được áp dụng đúng.
5. `nonce` khớp khi client đã gửi nonce hoặc profile yêu cầu.
6. `sub` hiện diện, có định dạng/giới hạn theo giao thức và được lấy từ **token đã xác minh**.
7. Authorization response đã được gắn với request/phiên hợp lệ bằng state/issuer/PKCE theo luồng đang dùng.

**Không dùng việc decode payload Base64 của JWT làm bằng chứng xác thực.** Trong OIDC, chỉ đọc `sub` sau khi token và ngữ cảnh login đã vượt qua các kiểm tra bắt buộc.

### 3.2. UserInfo response phải có `sub` khớp ID token

Sau khi client xác minh ID token, nó có thể dùng **access token phù hợp** gọi UserInfo endpoint của OP:

~~~http
GET /userinfo HTTP/1.1
Host: login.example.com
Authorization: Bearer <ACCESS_TOKEN_FOR_USERINFO>
Accept: application/json
~~~

Ví dụ response:

~~~json
{
  "sub": "usr_7Jx3qA2",
  "name": "Alice Nguyen",
  "preferred_username": "alice",
  "email": "alice@example.com",
  "email_verified": true
}
~~~

**OIDC Core yêu cầu `sub` trong UserInfo response và client phải kiểm tra `sub` đó khớp chính xác `sub` của ID token** trước khi sử dụng những claims khác. Nếu không khớp, **không được sử dụng UserInfo response** để cập nhật hay đăng nhập user.

~~~text
ID token đã xác minh:
    sub = usr_7Jx3qA2

UserInfo response:
    sub = usr_9Wrong

Decision:
    REJECT UserInfo data
    không ghi name/email/role vào tài khoản hiện tại
~~~

Điều này giúp phát hiện response bị trộn hoặc dùng access token cho sai subject. Kiểm tra `sub` không thay thế TLS, access token protection, signature/UserInfo verification khi profile yêu cầu, hay issuer binding của OP.

### 3.3. Khi không gọi UserInfo thì sao?

OIDC client **không bắt buộc gọi UserInfo endpoint** cho mọi login. ID token đã xác minh có `sub` cần thiết để nhận diện End-User; nhiều ứng dụng chỉ dùng issuer/sub để tạo external identity. UserInfo là nguồn claims bổ sung, cần scope và policy thích hợp.

Không nên tự gọi UserInfo chỉ để lấy email rồi bỏ `sub`. Nếu có gọi, phải đối chiếu `sub` theo chuẩn.

## 4. Hai subject identifier types: public và pairwise

OpenID Connect hỗ trợ hai kiểu subject identifier quan trọng:

- **`public`**: OP cung cấp một subject identifier nhất quán cho cùng End-User đối với các client của OP.
- **`pairwise`**: OP cung cấp subject identifier được xác định theo **Sector Identifier** để giảm khả năng các ứng dụng ở các sector khác nhau liên kết hoạt động của cùng End-User.

Sự khác nhau ảnh hưởng đến **quyền riêng tư, account mapping và tích hợp nhiều ứng dụng**. Nó không làm thay đổi ý nghĩa nền tảng: `sub` vẫn cần được so sánh trong bối cảnh issuer và không được tái gán tùy tiện.

### 4.1. Public subject identifier

Minh họa:

| Issuer | Client | Alice nhận `sub` |
|---|---|---|
| `https://login.example.com` | Shop Web | `usr-alice-83` |
| `https://login.example.com` | Shop Mobile | `usr-alice-83` |
| `https://login.example.com` | Helpdesk Portal | `usr-alice-83` |

Với **public subject**, các client có thể thấy cùng subject string cho Alice trong một OP. Điều này có thể thuận tiện cho hệ sinh thái ứng dụng cùng tổ chức, nhưng cũng tạo khả năng **liên kết dữ liệu giữa những client** nếu họ chia sẻ dữ liệu.

Public `sub` **không nhất thiết là thông tin công khai theo nghĩa có thể đăng lên mạng**. Tên `public` nói về cách identifier được chia sẻ nhất quán giữa các client, không miễn trừ bảo vệ dữ liệu cá nhân và access control.

### 4.2. Pairwise subject identifier

Với pairwise subject, OP tính hoặc ánh xạ `sub` theo **subject nội bộ + Sector Identifier**. Giả sử Alice đăng nhập:

| Issuer | Sector | Subject cấp cho Alice |
|---|---|---|
| `https://login.example.com` | `shop.example.com` | `pws_Ku91X7` |
| `https://login.example.com` | `helpdesk.example.net` | `pws_4hB02Z` |
| `https://login.example.com` | `billing.example.org` | `pws_M5aa92` |

Các giá trị là minh họa, không phải thuật toán chính thức. Những ứng dụng ở **các sector khác nhau** không thể đơn giản dùng `sub` để nối bản ghi cùng Alice, giảm khả năng cross-client tracking khi không có quyền.

Một OP có thể tạo pairwise subject bằng **hàm dẫn xuất mật mã dùng secret/salt** hoặc **bảng ánh xạ riêng**. Nếu dùng hàm dẫn xuất, đầu vào phải được đóng khung/phân tách rõ, khóa và salt được bảo vệ; không chỉ nối email với domain rồi băm SHA-256 không khóa và coi đó là privacy.

### 4.3. Pairwise không có nghĩa luôn khác giữa mọi client

Nếu nhiều client cùng một **Sector Identifier** theo quy tắc OIDC, OP có thể cấp subject identifier nhất quán trong sector đó. Mục tiêu là **phân tách giữa các sector**, không khẳng định mọi `client_id` luôn nhận một chuỗi khác nhau.

Vì thế:

- Không dùng pairwise `sub` để tự kết luận hai login ở hai sector là **hai người khác nhau**.
- Không dùng public `sub` để kết luận dữ liệu có thể chia sẻ giữa các client mà không cần policy.
- Không suy luận same-person giữa hai sector bằng cách so trực tiếp `sub`; cần cơ chế liên kết có căn cứ và quyền.

### 4.4. Chọn kiểu subject nào?

| Bối cảnh | Cân nhắc |
|---|---|
| Nhiều client thuộc cùng một sản phẩm và cần account mapping nhất quán | Public hoặc cùng sector pairwise tùy privacy policy |
| Nhiều ứng dụng không liên quan, cần hạn chế correlation | Pairwise thường phù hợp |
| Ứng dụng phụ thuộc email để nối user | Phải sửa identity model; email không thay `sub` |
| Client chuyển issuer hoặc sector | Cần kế hoạch migration/linking chủ động |
| AS/OP hỗ trợ hai kiểu | Client registration và discovery metadata quyết định kiểu thực tế |

**Không tự đổi kiểu subject khi hệ thống đang vận hành mà không có kế hoạch dữ liệu.** Đổi public sang pairwise có thể khiến `sub` của user thay đổi đối với một số client, dẫn đến tạo tài khoản trùng hoặc mất liên kết nếu ứng dụng không được chuẩn bị.

## 5. Sector Identifier và `sector_identifier_uri`

Trong OIDC pairwise, **Sector Identifier** là ranh giới giúp OP biết các client nào có thể thuộc cùng nhóm nhận diện subject. Hai khái niệm dễ bị nhầm:

1. **Sector Identifier**: danh tính sector mà OP dùng khi tạo pairwise subject.
2. **`sector_identifier_uri`**: một URI HTTPS đăng ký với OP để xác định sector và công bố danh sách redirect URIs của client.

### 5.1. Khi client không đăng ký `sector_identifier_uri`

Theo OpenID Connect Core, với pairwise subject và không có `sector_identifier_uri`, OP dùng **host component của redirect URI đã đăng ký** làm sector identifier. Ví dụ:

~~~text
redirect_uri:
    https://shop.example.com/oidc/callback

host:
    shop.example.com

sector identifier:
    shop.example.com
~~~

Không dùng toàn bộ path `/oidc/callback` làm sector ID theo quy tắc trên. Việc thay một path của cùng host không nhất thiết tạo sector mới, nhưng phải quản lý redirect URI an toàn và đúng client registration.

### 5.2. Khi có nhiều redirect hosts

Nếu client đăng ký redirect URIs trên **nhiều hostname**, và sử dụng pairwise subject, OIDC yêu cầu đăng ký `sector_identifier_uri` theo quy tắc liên quan:

~~~text
Client registration:
  redirect_uris:
    https://shop.example.com/oidc/callback
    https://mobile-callback.example.net/oidc/callback

  sector_identifier_uri:
    https://accounts.example.com/oidc/sector.json
~~~

Ở URI trên, host **`accounts.example.com`** được dùng làm sector identifier. OP truy xuất file HTTPS tại đường dẫn được đăng ký, ví dụ:

~~~json
[
  "https://shop.example.com/oidc/callback",
  "https://mobile-callback.example.net/oidc/callback"
]
~~~

File chứa **JSON array của các redirect URI**; OP phải xác minh các redirect URI đã đăng ký hiện diện theo quy tắc OIDC trước khi chấp nhận registration. Ví dụ chỉ dùng hai URI giả định và không bao hàm đầy đủ yêu cầu đăng ký động của mỗi sản phẩm OP.

### 5.3. Những điều `sector_identifier_uri` không làm

`sector_identifier_uri`:

- **Không** phải token endpoint hay UserInfo endpoint.
- **Không** phải một redirect URI thay thế cho authorization code.
- **Không** phải URL nhận ID token hoặc access token.
- **Không** biến hostname thành bằng chứng Alice có quyền ở mọi tenant.
- **Không** phải nơi client gửi refresh token hay secret.
- **Không** tự cho phép liên kết tài khoản giữa các tổ chức không có quyền.

OP phải xử lý URI đăng ký như **đầu vào có rủi ro SSRF**: HTTPS và danh sách host/đích được phép, chặn IP/endpoint nội bộ không tin cậy, chống redirect sang private network, timeout và giới hạn kích thước dữ liệu. Đừng cho registration do caller nhập chỉ định một URL nội bộ như metadata service để OP fetch mà không kiểm soát.

### 5.4. Thay đổi redirect host hoặc sector URI ảnh hưởng gì?

Giả sử một client ban đầu dùng pairwise với redirect host `shop.example.com`, rồi chuyển callback sang `login.shop-new.example` mà không duy trì sector identifier cũ.

~~~text
Issuer không đổi:
    https://login.example.com

Trước migration:
    sector = shop.example.com
    sub = pws_Ku91X7

Sau migration:
    sector = login.shop-new.example
    sub = pws_SectorChanged
~~~

**Cùng Alice có thể nhận subject khác** vì sector đã thay đổi. Nếu ứng dụng tạo user mới chỉ dựa vào cặp `(iss, sub)` mới, Alice có thể nhìn thấy tài khoản trống hoặc mất liên kết với dữ liệu cũ.

Giải pháp cần được lên kế hoạch trước:

1. Xác định tất cả client registrations và redirect hosts đang ảnh hưởng.
2. Cân nhắc giữ **Sector Identifier ổn định** qua `sector_identifier_uri` được kiểm soát nếu OP và kế hoạch hỗ trợ.
3. Kiểm tra sự ổn định của subject trong môi trường thử nghiệm với user fixtures.
4. Nếu subject bắt buộc đổi, thiết kế **migration mapping qua kênh admin tin cậy hoặc account linking có chứng minh**, không tự nối bằng email.
5. Có kế hoạch rollback, điều tra lỗi đăng nhập và bảo vệ chống account takeover.

Đừng giả định thay `client_id`, redirect host hoặc chuyển nhà cung cấp OP hoàn toàn không ảnh hưởng subject. Tính ổn định phải được kiểm tra theo **issuer + sector + registration policy thực tế**.

### 5.5. Bảo vệ tính ổn định nhưng không làm mất privacy

Một tổ chức có thể muốn nhiều app nội bộ chia sẻ một sector để có cùng subject. Đây là quyết định có tác động đến khả năng **correlation**. Chỉ gom client vào cùng sector khi có mục đích hợp lệ, quản trị đăng ký và chính sách dữ liệu tương ứng.

Không hợp nhất sector của nhiều đối tác chỉ để tiện phân tích hành vi người dùng. Với pairwise, giá trị bảo mật và riêng tư nằm ở việc tôn trọng ranh giới giữa các ứng dụng độc lập.

## 6. `sub` không phải email, username, số điện thoại hay thuộc tính hồ sơ

Đây là một trong những lỗi account mapping phổ biến nhất: dùng email làm khóa thay cho `(iss, sub)`.

### 6.1. Một người dùng có thể thay email nhưng giữ subject

~~~text
Lần đăng nhập 1:
    iss   = https://login.example.com
    sub   = usr_7Jx3qA2
    email = alice@old.example

Lần đăng nhập 2:
    iss   = https://login.example.com
    sub   = usr_7Jx3qA2
    email = alice@new.example

=> Đây có thể vẫn là cùng một external identity.
~~~

Nếu hệ thống coi email là primary key, user có thể bị tạo tài khoản mới hoặc bị mất liên kết tài nguyên. Nếu `sub` không đổi trong issuer/sector và ID token hợp lệ, ứng dụng thường cập nhật **email thuộc tính** theo policy, không tạo một identity khác.

### 6.2. Cùng email không chứng minh cùng external identity

~~~text
Issuer A:
    iss   = https://login.company-a.example
    sub   = A-001
    email = alice@example.com

Issuer B:
    iss   = https://login.partner-b.example
    sub   = B-998
    email = alice@example.com
~~~

Hai bản ghi có thể do cùng Alice sở hữu, nhưng **không thể suy ra an toàn chỉ từ email**. Email có thể:

- Được thay đổi hoặc chuyển giao qua vòng đời tổ chức.
- Được tái cấp cho người khác sau khi tài khoản bị đóng.
- Không được issuer xác minh theo cùng tiêu chuẩn.
- Là email chung hoặc bí danh do nhiều người truy cập.
- Được chuẩn hóa khác nhau giữa các OP.

Ngay cả `email_verified=true` chỉ thể hiện OP đã xác minh claim email theo quá trình của OP tại thời điểm/điều kiện phù hợp; nó **không biến email thành định danh bất biến và duy nhất trên mọi issuer**.

### 6.3. Thuộc tính nào dùng vào việc gì?

| Thuộc tính | Mục đích thích hợp | Có nên làm khóa external identity? |
|---|---|---|
| `iss` + `sub` | Nhận diện subject trong OP đã xác minh | **Có** |
| `email` | Liên lạc, gửi thông báo, hiển thị | **Không** |
| `email_verified` | Tín hiệu về quá trình xác minh email | **Không** |
| `preferred_username` | Tên đăng nhập/hiển thị có thể thay đổi | **Không** |
| `name` | Tên người dùng | **Không** |
| `phone_number` | Thông tin liên lạc có thể thay đổi | **Không** |
| `sid` nếu có | Định danh phiên OIDC theo profile | **Không** |
| `auth_time`, `acr`, `amr` | Ngữ cảnh/thời điểm và phương pháp xác thực | **Không** |
| `client_id`/`azp` | Xác định client/bên được ủy quyền theo profile | **Không** |
| Tenant/organization ID | Đầu vào cho chính sách tenant khi được xác minh | Không thay `(iss, sub)` |

**`sid` khác `sub`:** cùng Alice có thể có nhiều session ID trên các thiết bị; session thay đổi khi đăng nhập/đăng xuất, còn subject dùng để nhận diện End-User theo issuer. Không dùng `sid` làm user PK.

### 6.4. `sub` không nên chứa PII chỉ để tiện nhìn

Một OP có thể chọn giá trị subject không mang ý nghĩa, chẳng hạn chuỗi ngẫu nhiên, để giảm khả năng tiết lộ danh tính cá nhân. Client không nên yêu cầu `sub` phải bằng email hoặc số nhân viên để tiện debug.

Nếu cần log, ưu tiên **internal user ID** hoặc event correlation ID đã được quản lý và giới hạn retention. `sub` vẫn có thể được xem là dữ liệu có khả năng liên kết hoạt động của người dùng, đặc biệt với public subject; không công khai hoặc chia sẻ tùy tiện.

## 7. Nhận diện user nội bộ bằng cặp `(iss, sub)`

Ứng dụng thường có **một bảng user nội bộ** gắn quyền, đơn hàng, preferences và dữ liệu nghiệp vụ, cùng **một bảng external identity** lưu các định danh từ OP.

### 7.1. Mô hình dữ liệu gợi ý

~~~text
local_users
  id
  status
  created_at
  updated_at

external_identities
  id
  user_id             -> local_users.id
  issuer              -> iss đã xác minh
  subject             -> sub chính xác từ OP
  source_registration -> client/connection nếu policy cần
  created_at
  last_seen_at

Unique identity key:
  (issuer, subject)  [trong phạm vi namespace subject đã định nghĩa]
~~~

Ví dụ SQL khái niệm:

~~~sql
CREATE TABLE local_users (
    id BIGINT PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE external_identities (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES local_users(id),
    issuer VARCHAR(1024) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP,
    CONSTRAINT uq_external_identity UNIQUE (issuer, subject)
);
~~~

SQL chỉ minh họa, chưa chứa index, DB collation, transaction hay lifecycle đầy đủ. **Phải dùng collation/so sánh phân biệt chữ hoa-thường** cho `subject` (và so sánh issuer theo định danh cấu hình chính xác), nếu không hai subject `AbC` và `abc` có thể bị DB xem là cùng giá trị.

Với pairwise subject, một ứng dụng có thể gặp nhiều định danh cho cùng End-User ở các sector. Nếu xây một identity directory dùng chung cho nhiều RP, mô hình namespace còn phải tính đến **issuer + sector/client context theo thiết kế OP**, thay vì giả định mọi subject có thể so sánh chéo sector. Khóa `(iss, sub)` chỉ được sử dụng sau khi hiểu đúng phạm vi giá trị `sub` mà OP đã phát.

### 7.2. Luồng đăng nhập an toàn

~~~mermaid
flowchart TD
    A[Client hoàn tất OIDC Authorization Code + PKCE] --> B[Kiểm tra ID token và issuer]
    B --> C{iss, sub hợp lệ và thuộc request này?}
    C -- Không --> X[Từ chối đăng nhập]
    C -- Có --> D[Tra external identity theo issuer + subject]
    D --> E{Đã tồn tại?}
    E -- Có --> F[Load local user và kiểm tra trạng thái]
    E -- Không --> G{Policy cho phép tạo user hoặc liên kết?}
    G -- Không --> Y[Từ chối / yêu cầu onboarding]
    G -- Có --> H[Tạo mapping an toàn trong transaction]
    H --> F
    F --> I[Áp tenant/policy và tạo session ứng dụng]
~~~

Các bước quan trọng:

1. Chỉ nhận `iss`/`sub` từ **ID token đã được thư viện OIDC xác minh**, không từ JSON body/cookie do browser tự gửi.
2. Dùng cặp `(iss, sub)` để tìm **external identity**.
3. Nếu chưa có mapping, áp chính sách **JIT provisioning, mời thành viên hoặc account linking**; không tự ghép dựa trên email trùng.
4. Khi tìm được local user, kiểm tra **trạng thái user, tenant, mối quan hệ tổ chức và quyền truy cập**.
5. Tạo session ứng dụng/đăng nhập nội bộ theo chính sách; không dùng raw ID token làm session cookie không được bảo vệ.

### 7.3. Multi-tenant và subject

Trong một SaaS có nhiều tenant, cùng external subject có thể có membership ở nhiều tenant. Nếu người dùng đăng nhập với `sub=usr_7Jx3qA2`:

~~~text
external_identity:
    issuer = https://login.example.com
    sub = usr_7Jx3qA2
    local_user = 42

tenant_memberships:
    user 42 -> tenant A : viewer
    user 42 -> tenant B : none
~~~

`sub` nhận diện subject, **không quyết định membership hoặc role**. Khi gọi API với tenant B, backend phải kiểm tra membership và quyền trên từng resource, không cho phép chỉ vì người dùng đã xác thực ở issuer tin cậy.

Trong hệ thống mà mỗi tenant có issuer riêng, hai issuer có cùng `sub` càng không được gộp chỉ vì chuỗi giống nhau.

### 7.4. Tránh race khi JIT provisioning

Hai browser tabs có thể hoàn tất login gần nhau:

~~~text
Request A: không thấy mapping (iss, sub)
Request B: không thấy mapping (iss, sub)
Request A: tạo local user 42
Request B: tạo local user 43
=> Có thể có hai tài khoản cho cùng external identity.
~~~

Giải pháp:

- Dùng **unique constraint** thật cho external identity key ở database.
- Tạo mapping trong transaction; xử lý unique conflict bằng **đọc lại mapping đã commit**, không tạo user mới vô hạn.
- Bảo đảm không để local user rác hoặc orphaned record khi một transaction thất bại.
- Không dựa vào distributed cache/SELECT trước insert như biện pháp đồng bộ duy nhất.
- Bảo đảm account linking cũng tuân thủ unique constraint để một external identity không bị chiếm bởi hai local users.

## 8. Account linking: một người dùng có thể có nhiều external identities

Shop Web có thể cho phép Alice đăng nhập bằng nhiều phương thức:

~~~text
Local user 42
  |
  +-- (https://login.example.com, pws_Ku91X7)
  |
  +-- (https://accounts.partner.example, partner-user-445)
  |
  +-- (https://login.enterprise.example, employee-039)
~~~

Ba cặp `(iss, sub)` có thể cùng liên kết tới **một tài khoản nội bộ** chỉ khi ứng dụng đã có quy trình chứng minh người dùng được quyền nối các danh tính đó.

### 8.1. Không tự linking bằng email giống nhau

Ví dụ nguy hiểm:

~~~java
// SAI: email trùng không đủ căn cứ để liên kết external identity.
LocalUser user = users.findByEmail(oidcClaims.email());
externalIdentities.attach(user.id(), issuer, subject);
~~~

Nếu một issuer mới có thể phát email trùng với tài khoản đã tồn tại (hoặc email đã đổi chủ), attacker có thể được gắn vào tài khoản cũ. Ngay cả khi OP cung cấp `email_verified=true`, điều đó không tự chứng minh hai identities có cùng chủ sở hữu ở mọi thời điểm và mọi nhà cung cấp.

**Quy tắc:** matching by email có thể được dùng như **gợi ý giao diện** trong quy trình có xác minh bổ sung, nhưng không nên là thao tác tự động cấp quyền cho tài khoản nội bộ đã có.

### 8.2. Quy trình linking an toàn

Một cách thiết kế:

1. Alice đăng nhập **tài khoản nội bộ đang tồn tại** bằng một phương thức hợp lệ.
2. Alice chủ động chọn **Liên kết nhà cung cấp đăng nhập khác**.
3. Ứng dụng tạo OIDC authorization request riêng với **state, PKCE và issuer binding**, có thể yêu cầu reauthentication/step-up cho hành động nhạy cảm.
4. Sau callback, ứng dụng xác minh ID token mới và thu được cặp `(iss2, sub2)`.
5. Ứng dụng kiểm tra external identity mới **chưa thuộc một local user khác**.
6. Người dùng xác nhận ý định liên kết; backend gắn `(iss2, sub2)` với tài khoản đang đăng nhập trong transaction.
7. Ghi audit không chứa token và cập nhật các chính sách recovery/MFA phù hợp.

**Không** cho một API công khai nhận JSON:

~~~json
{
  "issuer": "https://login.partner.example",
  "subject": "partner-user-445",
  "target_local_user_id": 42
}
~~~

rồi tự nối bản ghi vì caller khai như vậy. Backend phải lấy `issuer` và `sub` từ OIDC login **đã xác minh**, chứng minh quyền sửa liên kết của local user và bảo vệ chống CSRF/session hijacking.

### 8.3. Unlink và tránh khóa mất tài khoản

Khi user gỡ một external identity:

- Yêu cầu xác thực lại khi rủi ro cao, xác nhận đúng connection.
- Kiểm tra account còn **ít nhất một phương thức đăng nhập hoặc recovery** đã được phép.
- Không xóa dữ liệu nghiệp vụ chỉ vì gỡ một identity nếu policy không yêu cầu.
- Kiểm tra session và refresh token liên quan; unlink mapping không tự thu hồi mọi token đã phát hành.
- Giữ audit và cấm tái chiếm identity đang liên kết với tài khoản khác.

Nếu external identity bị OP khóa hoặc xóa, ứng dụng cũng phải xử lý trạng thái provisioning/deprovisioning theo chính sách, không cứ thấy `sub` cũ là cho đăng nhập mãi.

### 8.4. Linking pairwise subjects từ hai sector

Giả sử cùng Alice nhận `pws_A` tại Shop Web và `pws_B` tại Helpdesk vì hai client khác sector. Ứng dụng không thể nối hai bản ghi chỉ bằng phép so `sub`.

Nếu doanh nghiệp có nhu cầu business hợp pháp để liên kết chúng, cần một quy trình:

- Người dùng xác thực hợp lệ vào cả hai ngữ cảnh hoặc
- Có kênh quản trị/identity provisioning được ủy quyền, có bằng chứng và audit rõ.

Việc suy ra cùng user nhờ email hoặc thiết kế một tracking identifier ngầm có thể **phá mục tiêu riêng tư của pairwise subject**. Cần xem xét chính sách dữ liệu và quyền liên kết trước khi triển khai.

## 9. Vòng đời subject identifier: ổn định, xóa tài khoản và migration

`sub` được thiết kế để **ổn định và không tái cấp cho một End-User khác** trong phạm vi hợp đồng của OP. Nhưng điều đó không có nghĩa dữ liệu liên quan user tồn tại vĩnh viễn hoặc mọi thay đổi hạ tầng đều giữ nguyên chuỗi.

### 9.1. Đổi thuộc tính, không đổi subject tùy tiện

Những thay đổi thông thường như:

~~~text
preferred_username: alice -> alice.nguyen
email: alice@old.example -> alice@new.example
name: Alice N. -> Alice Nguyen
~~~

không nên tự làm `sub` đổi theo. Nếu `sub` được tính trực tiếp từ một email có thể thay đổi, OP có nguy cơ vi phạm kỳ vọng về tính ổn định của subject.

Ứng dụng nên đặt quyền và lịch sử nghiệp vụ lên **local user ID**, còn `(iss, sub)` là cách định vị external identity đã xác minh.

### 9.2. Xóa tài khoản và không tái cấp subject

Khi Alice đóng tài khoản ở OP:

- OP có thể dừng xác thực/cho cấp token cho subject đó và xử lý dữ liệu theo chính sách.
- Subject cũ **không được tái cấp cho người dùng khác** theo ràng buộc OIDC.
- Ứng dụng có thể lưu trạng thái tombstone hoặc liên kết lịch sử theo nhu cầu pháp lý/chính sách để ngăn user mới kế thừa dữ liệu.
- Không suy rằng chỉ vì subject không còn ở OP thì tất cả JWT access token offline tại RS đã tự bị thu hồi trước `exp`.

Đừng tái sử dụng `(iss, sub)` để mở lại local account cho một người khác chỉ vì email của người mới giống email cũ.

### 9.3. Thay issuer hoặc hợp nhất IdP

Ví dụ doanh nghiệp chuyển từ:

~~~text
iss = https://login-old.example.com
sub = employee-039
~~~

sang:

~~~text
iss = https://identity-new.example.com
sub = 6b2a8f...
~~~

Đây là **hai external identity keys khác nhau**, ngay cả khi issuer mới giữ nguyên chuỗi subject hoặc cùng đăng ký email.

Kế hoạch migration an toàn:

1. Xác nhận issuer mới, client registration, redirect URI, JWKS và token profile.
2. Thiết kế **mapping old identity → new identity** qua kênh tin cậy, ví dụ tài liệu provisioning được bảo vệ hoặc reauthentication cả hai identities.
3. Di chuyển/đăng ký mappings trong transaction và có kiểm tra xung đột một-một.
4. Giữ khả năng rollback có kiểm soát, tránh tự link bằng email.
5. Giám sát đăng nhập thất bại, provisioning tạo user trùng và cảnh báo privilege escalation.
6. Khi kết thúc, bỏ trust với issuer cũ theo kế hoạch và xử lý token/session còn hạn.

**Không** chỉ thêm URL issuer mới vào allowlist JWT rồi chấp nhận mọi `sub` giống nhau như tài khoản cũ. Nếu key/issuer validation và account mapping bị trộn, có thể xảy ra **issuer confusion hoặc account takeover**.

### 9.4. Pairwise sector migration

Khi thay domain callback hoặc `sector_identifier_uri`, pairwise subject có thể thay. Trước khi đổi:

- Tạo user fixtures và xác minh giá trị sub trước/sau.
- Thống nhất với OP cách giữ ổn định sector nếu có thể.
- Nếu phải đổi, dùng một **mapping do OP hoặc quy trình account linking đáng tin cung cấp**, không reverse-engineer cách OP băm subject.
- Tránh lộ salt/khóa dùng sinh pairwise subject.
- Kiểm tra việc xóa và khôi phục tài khoản không vô tình tạo một subject liên quan user khác.

Nếu OP hỗ trợ nhiều issuer hoặc nhiều môi trường staging/production, không lấy một subject từ staging làm khóa identity cho production trừ khi chính sách và issuer binding được thiết kế rõ.

## 10. Ranh giới OIDC subject và phân quyền API

Một ứng dụng có thể vừa là OIDC **Relying Party** vừa là OAuth **client**, nhưng resource server vẫn có nhiệm vụ riêng. Điều này quan trọng trong module về token security.

### 10.1. Luồng từ đăng nhập đến API

~~~mermaid
sequenceDiagram
    actor A as Alice
    participant C as Shop Web / OIDC Client
    participant OP as OpenID Provider
    participant DB as Local User Database
    participant RS as Orders API
    A->>C: Đăng nhập
    C->>OP: Authorization Code + PKCE
    OP-->>C: ID token + access token đúng grant
    C->>C: Verify ID token iss, sub, aud, exp, signature, nonce
    C->>DB: Find/create mapping (iss, sub) theo policy
    DB-->>C: local_user_id = 42
    C->>RS: Authorization: Bearer <ACCESS_TOKEN>
    RS->>RS: Validate access token issuer, audience, scope, time
    RS->>RS: Authorize principal với order cụ thể
    RS-->>C: 200 hoặc 401/403 theo điều kiện
~~~

Trường hợp access token là JWT theo profile, RS có thể dùng `sub` để biết principal do AS khẳng định. Nhưng **chỉ RS và chính sách cấp token** xác định `sub` đó có mang ý nghĩa End-User, workload hay actor trong grant cụ thể.

### 10.2. `sub` trong OAuth access token không luôn là End-User OIDC

Với `client_credentials`, access token có thể đại diện cho **client/workload** và không có một Alice đang đăng nhập. Profile token có thể sử dụng `sub` cho service principal hoặc có chính sách riêng. Đừng coi mọi access token có `sub` là một OIDC End-User có thể gắn email.

~~~text
Authorization Code + OIDC user:
    sub có thể biểu diễn End-User đã được OP xác thực.

Client Credentials Grant:
    subject/principal có thể biểu diễn workload/client.

Token exchange / delegated call:
    cần phân biệt subject, actor và audience theo profile.
~~~

Nếu hệ thống tự ánh xạ `sub=service-orders` thành người dùng nội bộ rồi áp quyền Alice, có thể tạo **confused deputy**.

### 10.3. Phân biệt authentication và authorization

| Câu hỏi | Kiểm soát đúng |
|---|---|
| Đây có phải ID token OIDC tin cậy cho Shop Web không? | Chữ ký, issuer, audience, thời gian, nonce, profile |
| Đang là End-User nào ở OP? | **`(iss, sub)` của ID token đã xác minh** |
| User nội bộ nào tương ứng? | Bảng external identity mapping và provisioning policy |
| User thuộc tenant nào? | Tenant membership/policy của ứng dụng |
| Access token dùng cho API này được không? | Token type, issuer, audience, expiry và scope |
| User có được đọc order-999 không? | Authorization theo principal, action, resource, tenant và context |
| User có đăng nhập gần đây/MFA không? | `auth_time`, `acr`, `amr`/policy khi được hỗ trợ, không phải chỉ `sub` |

**Subject identifier không phải quyền.** Một `sub` ổn định khiến việc mapping nhất quán hơn, nhưng không chứng minh user được xem mọi dữ liệu liên quan trong hệ thống.

## 11. Bảo vệ quyền riêng tư và quản trị dữ liệu subject

Mặc dù `sub` không phải mật khẩu, nó có thể là **persistent identifier**. Một chuỗi được nhiều hệ thống ghi log có thể trở thành cách liên kết hoạt động của người dùng.

### 11.1. Thu thập tối thiểu

- Chỉ lưu `iss`, `sub`, metadata liên kết và user ID nội bộ thực sự cần cho authentication/account mapping.
- Không bắt buộc lấy email, tên, số điện thoại nếu ứng dụng không cần cho nghiệp vụ.
- Giới hạn việc sao chép subject vào analytics, CDN logs, trace spans và support exports.
- Với public subject, đánh giá rủi ro correlation khi nhiều client chia sẻ cùng identifier.
- Với pairwise, không tạo một master cross-sector tracking key không có cơ sở quyền riêng tư.

### 11.2. Log metadata nhưng không tiết lộ credential

Không log:

~~~text
Authorization: Bearer <ACCESS_TOKEN>
id_token=<SIGNED_ID_TOKEN>
refresh_token=<SECRET>
authorization_code=<CODE>
email=alice@example.com (nếu không cần)
~~~

Có thể ghi, theo chính sách:

~~~text
traceId
issuerId
clientRegistrationId
localUserId (đã quản lý truy cập)
authenticationDecision=ALLOW|DENY
mappingOperation=FOUND|CREATED|LINKED|REJECTED
reasonCategory=ISSUER_MISMATCH|SUB_MISMATCH|ACCOUNT_DISABLED
tenantId khi nghiệp vụ cần và đã có quyền
~~~

Nếu phải correlation qua nhiều log, có thể dùng **HMAC có khóa** trên cặp issuer/subject với quy tắc encoding cố định và khóa do hệ thống bảo vệ, thay vì unsalted hash đơn giản có thể bị đoán. Dù đã băm, định danh giả vẫn có thể là dữ liệu cá nhân; không xem đó là ẩn danh tuyệt đối.

### 11.3. OP không nên dùng thông tin nhạy cảm làm subject dễ đoán

Pairwise subject thường giúp hạn chế linkability giữa các sector. OP không nên vô tình tiết lộ email, mã nhân viên hoặc số điện thoại trực tiếp trong pairwise `sub`, vì như vậy các app vẫn có thể liên kết danh tính bất chấp tên kiểu "pairwise".

Nếu dùng hàm dẫn xuất từ local identifier và sector, cần key/salt được bảo vệ, thuật toán ổn định, collision resistance và chính sách thay khóa/migration. Không phát public account ID ra mọi client khi policy yêu cầu pairwise isolation.

## 12. Java/Spring Security: lấy subject từ OIDC principal đã xác minh

Trong Spring Security, một ứng dụng sử dụng `oauth2Login` với OIDC có thể nhận `OidcUser` sau khi bộ lọc hoàn tất quy trình đăng nhập và kiểm tra ID token. Đừng tự xử lý một JWT string không tin cậy trong controller để lấy subject.

### 12.1. Cấu hình OIDC client

Ví dụ `application.yml` cho web backend:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          shop:
            provider: company
            client-id: shop-web
            client-secret: ${OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://login.example.com
~~~

Ví dụ chỉ minh họa; production cần:

- Client registration và redirect URI chính xác ở OP.
- Client secret/key lưu an toàn, không commit giá trị thật.
- Authorization Code + PKCE S256 theo profile và phiên bản Spring đang dùng.
- Session/CSRF, callback state, nonce/issuer mix-up protection khi áp dụng.
- OP discovery/JWKS tin cậy, kiểm tra ID token đầy đủ.
- Cấu hình role/tenant/provisioning không suy ra từ username hoặc `sub` prefix.

**Client secret không thay PKCE** trong thiết kế yêu cầu cả hai; cũng không được để public browser client giữ một client secret trong JavaScript bundle.

### 12.2. Controller đọc `iss` và `sub` từ OidcUser

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class CurrentUserController {
    private final IdentityService identityService;

    public CurrentUserController(IdentityService identityService) {
        this.identityService = identityService;
    }

    @GetMapping("/api/me")
    public UserProfile me(@AuthenticationPrincipal OidcUser principal) {
        if (principal == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        // Principal được tạo bởi OIDC login pipeline đã được cấu hình.
        OidcIdToken idToken = principal.getIdToken();
        String issuer = idToken.getClaimAsString("iss");
        String subject = idToken.getSubject();

        if (issuer == null || subject == null || subject.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        // Defense-in-depth: OIDC client chuẩn đã phải so sub UserInfo
        // với sub ID token trước khi dùng UserInfo.
        OidcUserInfo userInfo = principal.getUserInfo();
        if (userInfo != null
                && !subject.equals(userInfo.getSubject())) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        return identityService.loadProfileByVerifiedExternalIdentity(
            issuer, subject);
    }
}
~~~

`IdentityService`, `UserProfile` là type do ứng dụng định nghĩa. Đoạn code **không tự thực hiện JWT signature/issuer/audience/nonce validation**: nó dựa vào Spring OAuth2/OIDC login pipeline đã được cấu hình và kiểm thử chính xác. Nếu authentication principal bị tự tạo từ request không tin cậy, giả định này không còn đúng.

**Không** viết endpoint `/login?sub=...` rồi nhận `sub` trong query thay vì OIDC principal. Cũng không tự parse `Authorization: Bearer` bất kỳ thành OIDC ID token nếu API thật sự phải nhận OAuth access token.

### 12.3. Dữ liệu ánh xạ phải giữ chính xác subject string

Tầng service có thể dùng value object:

~~~java
import java.util.Objects;

public record ExternalIdentityKey(String issuer, String subject) {
    public ExternalIdentityKey {
        Objects.requireNonNull(issuer);
        Objects.requireNonNull(subject);

        if (issuer.isBlank() || subject.isEmpty()
                || subject.length() > 255) {
            throw new IllegalArgumentException("Invalid identity key");
        }
    }
}
~~~

Đây là **kiểm tra tối thiểu minh họa**, không thay toàn bộ OIDC validation. Vì OIDC subject giới hạn ASCII và issuer có cú pháp URL, production có thể thêm kiểm tra định dạng đúng chuẩn ở ranh giới nhận dữ liệu **sau** khi đã xác minh token; không nên sửa `issuer`/`subject` cho "đẹp" trước lookup.

Java record giữ `subject` nguyên dạng. Không chuyển thành `long`, không lowercase và không gộp với username. Khi dùng database, phải đảm bảo **unique index phân biệt case**, kể cả khi default collation của DB không phân biệt chữ hoa/thường.

### 12.4. Cấu hình security chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ShopSecurityConfig {
    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/health").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây không phải production config đầy đủ: cần chính sách session, CSRF, cookie, logout, error handling, mapping authorities và OIDC token validation theo phiên bản. Nếu `scope=openid` không được yêu cầu hoặc OP không hỗ trợ OIDC, một OAuth2 principal thông thường **không tương đương** OIDC ID token đã xác minh.

### 12.5. Resource Server dùng access token, không dùng ID token

Orders API có cấu hình riêng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
~~~

Cấu hình issuer là bước đầu; API còn cần expected audience, token type/profile, expiration, scope/authority mapping và kiểm tra quyền nghiệp vụ. Khi AS phát hành opaque access token, API cần introspection hoặc cách kiểm tra được hỗ trợ.

**Không giả định** một `sub` trong access token luôn là End-User có ID token tương ứng, đặc biệt với client credentials hoặc token exchange.

## 13. OIDC discovery, client metadata và issuer binding

OP có thể công bố metadata như `issuer`, `jwks_uri`, `authorization_endpoint`, `token_endpoint` và `subject_types_supported` trong discovery. Client có thể đăng ký `subject_type` và `sector_identifier_uri` theo cơ chế registration được OP hỗ trợ.

Ví dụ **rút gọn** metadata:

~~~json
{
  "issuer": "https://login.example.com",
  "authorization_endpoint": "https://login.example.com/oauth2/authorize",
  "token_endpoint": "https://login.example.com/oauth2/token",
  "jwks_uri": "https://login.example.com/.well-known/jwks.json",
  "subject_types_supported": ["public", "pairwise"]
}
~~~

Đây là ví dụ giải thích, không phải toàn bộ tài liệu discovery hợp lệ. Khả năng OP hỗ trợ subject type **không có nghĩa client đang đăng ký với type đó**; phải biết registration chính xác.

### 13.1. Không lấy trust anchor từ token chưa xác minh

Một lỗi thiết kế nguy hiểm:

~~~java
// SAI: tự tin issuer/URL do token chưa xác minh khai báo.
String issuer = parseJwtWithoutVerification(idToken).get("iss");
String jwksUri = issuer + "/jwks";
PublicKey key = fetchAnyUrl(jwksUri);
trustSubject(parseJwtWithoutVerification(idToken).get("sub"));
~~~

Attacker có thể tạo JWT với issuer do họ kiểm soát, phát khóa tương ứng rồi khiến client tin token giả. Với OIDC, **issuer/client registration phải được chọn và tin cậy trước hoặc được ràng buộc với authorization request**, sau đó token mới được xác minh với metadata/key được phép của issuer đó.

Tránh dynamic JWKS lookup theo một `jku`/`x5u` URL trong JWT header mà không có policy cho phép, vì có thể dẫn đến key confusion và SSRF.

### 13.2. Bảo vệ multi-issuer login

Giả sử Shop Web hỗ trợ:

~~~text
OP A = https://login.company-a.example
OP B = https://login.partner-b.example
~~~

Client cần lưu issuer, client registration, redirect URI, state/PKCE verifier của request gốc. Trong callback, không sử dụng issuer do browser khai để **chọn bất kỳ token endpoint nào**. Đây là điểm cần chống **Authorization Server Mix-Up**; RFC 9207 cung cấp tham số `iss` trong authorization response khi OP và client hỗ trợ.

Sau khi đã xác minh ID token:

~~~text
(OP A, sub=12345) ≠ (OP B, sub=12345)
~~~

Nếu cơ chế đăng nhập không ràng buộc issuer, account lookup `(iss, sub)` cũng có thể sai ngay từ bước **chọn issuer được tin**, không chỉ ở database.

### 13.3. Đừng suy issuer từ email domain

Nếu Alice có `email=alice@company-a.example`, ứng dụng có thể dùng email domain để **gợi ý home realm discovery** theo chính sách, nhưng không được tự suy rằng ID token phải đến từ một URL được ghép từ email string. Issuer dùng xác minh token phải là giá trị tin cậy được cấu hình/chọn qua discovery an toàn.

**Không tạo account mapping trước khi kiểm tra issuer và chữ ký.**

## 14. Những lỗi cụ thể trong triển khai subject identifier

| Sai lầm | Nguy cơ | Hướng sửa |
|---|---|---|
| Chỉ dùng `sub` làm khóa trên nhiều issuer | Gộp nhầm hai người cùng subject string | Dùng `(iss, sub)` từ ID token đã xác minh |
| Dùng email làm khóa chính | Đổi/tái cấp email gây account takeover | Email là claim thuộc tính, không thay subject |
| Tin email_verified để auto-link mọi OP | Quyền xác minh email không đồng nhất | Linking cần bằng chứng và sự đồng ý |
| Parse `sub` thành số | Mất số 0 đầu hoặc sai cú pháp | Giữ opaque string |
| Lowercase `sub` | Gộp hai subject khác case | So sánh case-sensitive |
| Tin JWT chỉ vì payload có `sub` | Token giả có thể được tự tạo | Xác minh issuer/keys/audience/time/nonce |
| Dùng ID token làm Bearer của API | Audience và mục đích sai | Dùng access token đúng resource |
| Không so UserInfo sub với ID token sub | Mix dữ liệu của user khác | So khớp chính xác rồi mới dùng claims |
| Suy pairwise `sub` giống nhau ở mọi sector | Gộp/mất tài khoản | Tôn trọng sector và migration policy |
| Dùng hash email không khóa làm pairwise subject | Linkability và dễ đoán | OP dùng opaque pairwise mapping/KDF bảo vệ |
| Đổi redirect host mà không kiểm tra sector | Pairwise sub thay đổi bất ngờ | Giữ sector hoặc migration có kiểm soát |
| Link hai identities theo email giống nhau | Gắn attacker vào tài khoản cũ | Proof-of-control cả hai hoặc kênh admin tin cậy |
| Bỏ unique constraint khi JIT provisioning | Tạo hai user trong race | DB uniqueness + transaction/retry |
| Dùng DB collation không phân biệt case | Subject khác nhau bị xem là trùng | Cấu hình binary/case-sensitive comparison |
| `sub` đủ để cấp role admin | Privilege escalation | Role/tenant/resource policy riêng |
| Dùng `sid` làm user ID | Session đổi gây mất tài khoản | `sid` là session identifier, `sub` là subject |
| Reassign subject sau khi user bị xóa | User mới kế thừa dữ liệu user cũ | Không tái cấp subject trong phạm vi OP |
| Chấp nhận mọi issuer có JWKS hợp lệ | Issuer confusion | Trust allowlist và issuer binding |
| Log public subject khắp nơi | Tracking/correlation/privacy leak | Data minimization, retention và pseudonymous logs |

## 15. Ma trận kiểm thử OIDC subject identifier

### 15.1. ID token và issuer

| Test | Kết quả mong muốn |
|---|---|
| ID token hợp lệ, đúng issuer, audience và subject | Lấy `(iss, sub)` và tiếp tục mapping |
| ID token không có `sub` | Từ chối theo OIDC validation |
| `sub` không phải string hoặc vượt giới hạn chuẩn | Từ chối |
| JWT decode được nhưng chữ ký sai | Từ chối |
| JWT chữ ký đúng từ issuer khác | Từ chối với client registration hiện tại |
| JWT đúng issuer nhưng aud dành cho client khác | Từ chối |
| JWT hết hạn hoặc iat/nonce sai theo profile | Từ chối |
| Callback được gắn với issuer khác request gốc | Từ chối/mix-up protection |
| `sub=AbC` và `sub=abc` của cùng issuer | Hai subject khác nhau |
| `sub="00123"` và `sub="123"` | Hai subject khác nhau |
| Cùng `sub` nhưng hai issuer khác | Hai external identities khác nhau |

### 15.2. UserInfo và claims thuộc tính

| Test | Kết quả mong muốn |
|---|---|
| UserInfo sub khớp ID token sub | Có thể xử lý claims khác theo policy |
| UserInfo sub khác ID token sub | **Không sử dụng UserInfo response** |
| UserInfo không có sub | Từ chối UserInfo response |
| Email thay đổi, `(iss, sub)` không đổi | Cập nhật email theo policy, không tạo user mới |
| Email trùng ở hai OP khác | Không tự gộp local users |
| email_verified=true của OP lạ | Không tự cấp quyền account linking |
| preferred_username thay đổi | Không thay external identity |
| ID token không có email | Vẫn có thể nhận diện bằng `(iss, sub)` nếu policy cho phép |
| sub dùng làm role/tenant hint | Từ chối suy diễn quyền |

### 15.3. Public, pairwise và sector

| Test | Kết quả mong muốn |
|---|---|
| Public subject cùng OP cho cùng End-User ở hai client | Subject nhất quán theo profile/OP |
| Pairwise subject cùng End-User ở hai sector | Có thể khác; không giả định phải ghép |
| Hai client chung sector theo đăng ký pairwise | Kiểm tra đúng subject behavior được OP bảo đảm |
| Chuyển redirect host không có sector URI ổn định | Phát hiện nguy cơ subject thay đổi |
| Client có nhiều redirect hostname nhưng không có sector_identifier_uri | Registration bị từ chối theo OIDC khi yêu cầu |
| Sector file không liệt kê đầy đủ redirect URI | Registration bị từ chối |
| Sector URI trỏ vào network nội bộ không tin cậy | Chặn SSRF/unsafe fetching |
| Pairwise subject băm trực tiếp từ email | Security/privacy review thất bại |
| Đổi từ public sang pairwise trong production | Có migration plan, không tự gộp bằng email |

### 15.4. Account linking, mapping và API

| Test | Kết quả mong muốn |
|---|---|
| Hai login đồng thời từ cùng `(iss, sub)` | Chỉ một external identity mapping |
| External identity đã gắn local user A, caller muốn gắn B | Từ chối trừ khi có quy trình quản trị an toàn |
| Link provider mới thiếu reauthentication khi policy yêu cầu | Từ chối |
| User bị disable trong local DB nhưng OIDC token hợp lệ | Từ chối session/đăng nhập theo policy |
| User không có tenant membership | Từ chối quyền tenant |
| ID token đúng nhưng gọi API sai audience | Resource server từ chối |
| Access token scope read nhưng đọc resource của user khác | Từ chối theo resource policy |
| Subject cũ bị OP tái cấp cho account khác | Phát hiện vi phạm hợp đồng OP, chặn nguy cơ chiếm account |
| Issuer migration không có mapping đáng tin | Không tự chuyển ownership bằng email |

## 16. Tình huống suy luận

### Tình huống A — Hai issuer cùng `sub`

Một người dùng đăng nhập qua `https://login.a.example` với `sub=5723`. Sau đó có login qua `https://login.b.example`, cũng `sub=5723`.

**Câu hỏi:** Shop Web có thể coi hai phiên là cùng một người không?

**Trả lời:** Không chỉ dựa trên `sub`. Hai keys `(https://login.a.example, 5723)` và `(https://login.b.example, 5723)` khác nhau. Chỉ linking sau khi có bằng chứng và chính sách cho phép; email trùng không tự chứng minh ownership.

### Tình huống B — Email đổi nhưng subject giữ nguyên

Alice cập nhật email từ `alice@old.example` sang `alice@new.example`; OP vẫn trả cùng issuer và `sub`.

**Câu hỏi:** Ứng dụng có nên tạo local user mới không?

**Trả lời:** Không chỉ vì email đổi. Mapping theo `(iss, sub)` vẫn xác định external identity đã có. Email nên được cập nhật như thuộc tính theo policy, và các quy trình xác minh lại email/notification nếu cần.

### Tình huống C — ID token hợp lệ, UserInfo thuộc user khác

ID token chứa `sub=alice-007`, nhưng UserInfo response chứa `sub=bob-002` cùng email của Bob.

**Câu hỏi:** Có thể tin email trong UserInfo vì kết nối HTTPS không?

**Trả lời:** Không. OIDC yêu cầu `sub` của UserInfo **khớp chính xác** `sub` của ID token đã xác minh. Nếu mismatch, không sử dụng UserInfo response; điều tra token/userinfo binding thay vì cập nhật profile.

### Tình huống D — `sub` có chữ hoa

OP trả `sub=AbC-009` cho một user và `sub=abc-009` cho người khác. DB dùng collation không phân biệt case.

**Câu hỏi:** Rủi ro gì?

**Trả lời:** DB có thể coi hai định danh là cùng một key, dẫn đến sai mapping/account takeover. Cần xử lý subject như chuỗi case-sensitive và bảo vệ unique constraint đúng ngữ nghĩa.

### Tình huống E — Chuyển redirect host

Client pairwise trước đây dùng `https://shop.example.com/callback`, sau chuyển sang `https://login.shop-new.example/callback`, không có `sector_identifier_uri`.

**Câu hỏi:** Người dùng có thể mất liên kết tài khoản không?

**Trả lời:** Có thể. OP có thể dùng redirect hostname làm sector identifier, nên pairwise `sub` thay đổi khi sector đổi. Cần quản lý sector ổn định hoặc migration mapping qua kênh đáng tin.

### Tình huống F — Hai client có cùng sector

Shop Web và Shop Mobile được OP đăng ký pairwise trong cùng sector. Nhóm phát triển cho rằng pairwise bắt buộc mọi client nhận một `sub` khác hẳn.

**Câu hỏi:** Giả định đó đúng không?

**Trả lời:** Không. Pairwise ràng buộc với **Sector Identifier**. Các client cùng sector có thể chia sẻ subject identifier theo cơ chế OP; mục tiêu privacy là phân tách giữa các sector. Không thể suy kiểu subject chỉ từ `client_id`.

### Tình huống G — Login thành công nhưng order bị từ chối

Alice có OIDC ID token đúng `iss`, `sub`, `aud` dành cho Shop Web. Ứng dụng gọi Orders API bằng ID token và nhận 401.

**Câu hỏi:** Có nên cấu hình Orders API chấp nhận ID token không?

**Trả lời:** Không. ID token dành cho RP xác thực người dùng. Orders API cần **access token** đúng audience, type và scope; sau đó kiểm tra quyền trên order cụ thể.

### Tình huống H — Attacker tự cung cấp JWT có `sub`

Frontend gửi JSON `{"iss":"https://evil.example","sub":"alice-007"}` và server dùng các giá trị này tìm account.

**Câu hỏi:** Có an toàn không?

**Trả lời:** Không. `iss` và `sub` phải được lấy từ **ID token đã xác minh qua OP tin cậy** trong ngữ cảnh login hợp lệ, không từ request body hoặc JWT tự khai chưa xác thực.

### Tình huống I — Gộp tài khoản bằng email_verified

Account A đăng ký bằng OP công ty; một OP bên thứ ba khác trả `email=alice@example.com` và `email_verified=true`. App tự link vào A.

**Câu hỏi:** Có thể tạo lỗ hổng không?

**Trả lời:** Có. Các OP có quy trình xác minh và vòng đời email khác nhau; email có thể đổi chủ. Account linking cần bằng chứng quyền đối với tài khoản hiện có và external identity mới, kèm transaction/audit.

### Tình huống J — Chuyển nhà cung cấp SSO

Doanh nghiệp di chuyển OP và giữ `sub=employee-039`, nhưng `iss` đổi.

**Câu hỏi:** Có nên giữ nguyên mapping chỉ bằng `sub`?

**Trả lời:** Không. Đây là external identity key mới. Cần mapping migration đáng tin hoặc reauthentication/linking; `sub` trùng không cho phép bỏ issuer binding.

### Tình huống K — Client credentials có `sub`

Orders Worker nhận OAuth access token qua client credentials, trong đó `sub=orders-worker`. Backend tự coi đây là End-User và tải dữ liệu tài khoản người dùng cùng tên.

**Câu hỏi:** Sai ở đâu?

**Trả lời:** `sub` trong access token thuộc token profile/loại grant, không tự là OIDC End-User. Cần phân biệt service principal với user principal và áp quyền workload riêng.

### Tình huống L — Quyền admin được mã hóa trong subject

Một OP trả `sub=admin_alice_007`. Ứng dụng thấy tiền tố `admin_` rồi cho Alice quyền xóa tài khoản.

**Câu hỏi:** Có phù hợp không?

**Trả lời:** Không. Subject là opaque identifier, không phải role. Role/permission phải đến từ nguồn đã tin cậy và được áp theo authorization policy, không suy từ naming convention.

### Tình huống M — Pairwise dùng email hash không khóa

OP tạo `sub=SHA256(email + sector)` và cho rằng mọi client không thể nối danh tính người dùng.

**Câu hỏi:** Có đảm bảo privacy không?

**Trả lời:** Không chắc. Email là dữ liệu có thể đoán và có miền giá trị nhỏ hơn secret ngẫu nhiên; các client có thể thử email phổ biến hoặc thông tin đã biết để liên kết. OP nên dùng mapping opaque hoặc hàm dẫn xuất có key/salt bí mật và thiết kế quyền riêng tư có kiểm chứng.

### Tình huống N — JIT provisioning đồng thời

Hai request callback đã xác thực cùng `(iss, sub)` nhưng cả hai cùng thấy "chưa có user" rồi tạo user ID khác nhau.

**Câu hỏi:** Khắc phục thế nào?

**Trả lời:** Dùng unique constraint ở DB với so sánh đúng case, transaction và xử lý conflict bằng tra lại mapping. Không chỉ kiểm tra tồn tại trước khi insert bằng SELECT.

## 17. Quy trình xử lý sự cố identity mapping

Nếu hệ thống phát hiện tài khoản bị gộp sai, một subject bất thường hoặc OP đổi issuer/sector ngoài kế hoạch, cần xử lý như **vấn đề ranh giới danh tính**, không chỉ là lỗi hiển thị avatar.

### 17.1. Điều tra có thứ tự

1. **Khoanh vùng:** issuer/client registration/sector nào, thời điểm nào và những local users nào bị ảnh hưởng?
2. **Xác minh nguồn token:** login flow, signature/issuer/audience/nonce validation, UserInfo subject check có thực thi không?
3. **Kiểm tra mapping:** unique constraint, DB collation, thao tác link/unlink/JIT provisioning và các migration đã chạy.
4. **Kiểm tra quyền:** những session/access token nào đang hoạt động, tenant memberships và resource accesses đã xảy ra?
5. **Ngăn tiếp tục lỗi:** tạm dừng auto-link hoặc provisioning liên quan, không vội xóa toàn bộ mappings.
6. **Sửa qua kênh tin cậy:** unlink/link lại theo bằng chứng, lưu audit, giữ tính toàn vẹn tài liệu nghiệp vụ.
7. **Xử lý token/session:** revoke hoặc chặn theo thiết kế; JWT offline có thể còn hạn đến `exp` nếu không có denylist/state check.
8. **Phục hồi:** kiểm tra quyền sở hữu tài nguyên và dữ liệu, không chuyển ownership chỉ vì đổi account mapping.

### 17.2. Vì sao sửa bảng mapping thôi có thể chưa đủ?

Nếu Alice từng bị ánh xạ nhầm sang Bob, access token và session đã cấp có thể đã được sử dụng để:

- Đọc đơn hàng của Bob.
- Thay đổi thông tin thanh toán hoặc quyền trên tài nguyên.
- Cấp refresh token/session mới.
- Thực hiện hành động không thể đảo ngược.

Sửa mapping giúp ngăn login mới bị sai, nhưng **không hoàn tác dữ liệu đã bị đọc hoặc hành động đã thực hiện**. Cần kiểm tra audit và phạm vi API access, xử lý incident response theo chính sách.

### 17.3. Kiểm soát thay đổi issuer/sector

Trước khi phát hành thay đổi:

~~~text
Change request:
    old issuer / new issuer
    old sector / new sector
    client registrations bị ảnh hưởng
    expected sub stability
    mapping strategy
    rollback plan
    migration audit
    regression tests
~~~

Đảm bảo privacy/security review và stakeholder approval phù hợp; không coi `sub` như một tên cột có thể thay đổi tùy ý mà không ảnh hưởng identity semantics.

## 18. Checklist kiến trúc OIDC Subject Identifier

1. **Trust:** chỉ nhận OIDC principal/ID token từ issuer được cấu hình tin cậy; kiểm tra signature, audience, thời gian và nonce khi áp dụng.
2. **Identity key:** dùng **`(iss, sub)`** để định danh external identity; không chỉ `sub` hoặc email.
3. **String semantics:** giữ nguyên chuỗi subject, case-sensitive, tối đa 255 ASCII chars theo OIDC; không parse thành số hay dùng prefix làm role.
4. **ID token vs access token:** ID token cho RP; resource server nhận access token đúng issuer/audience/token type.
5. **UserInfo:** yêu cầu `sub` của UserInfo trùng chính xác ID token `sub` trước khi dùng claims khác.
6. **Subject type:** hiểu OP/client dùng `public` hay `pairwise`, không giả định hai kiểu có cùng cross-client behavior.
7. **Sector:** với pairwise, quản lý redirect hosts, `sector_identifier_uri` và danh sách redirect URIs đã đăng ký.
8. **Privacy:** dùng pairwise đúng mục tiêu giảm correlation, bảo vệ OP secret/mapping, không suy identity chéo sector trái policy.
9. **DB mapping:** unique constraint với collation case-sensitive, transaction/JIT provisioning chống race.
10. **Account linking:** không auto-link theo email, username hoặc email_verified; phải có bằng chứng kiểm soát danh tính.
11. **Multi-tenant:** subject không thay tenant membership, role hoặc resource/action policy.
12. **Issuer migration:** đổi issuer là đổi external identity key; cần migration mapping đáng tin.
13. **Sector migration:** tránh đổi sector bất ngờ làm thay pairwise subject; test trước và có rollback.
14. **Lifecycle:** OP không tái cấp subject cho user khác; xử lý deprovisioning/recovery/session/token theo policy.
15. **Logging:** giảm lưu persistent identifiers, không log raw tokens/codes/credentials, áp retention và access controls.
16. **Kiểm thử:** bao phủ issuer mix-up, UserInfo mismatch, pairwise/public, case sensitivity, linking, JIT race và API authorization.

### Nhớ nhanh trong 30 giây

~~~text
OIDC identity:
    issuer + subject = external identity key
    (iss, sub)

NOT identity key:
    email
    preferred_username
    name
    sid
    client_id

public:
    sub nhất quán cho cùng End-User ở một OP theo public mode

pairwise:
    sub được phân tách theo Sector Identifier

UserInfo:
    sub phải bằng sub trong ID token đã xác minh

Resource API:
    cần access token đúng aud/scope + quyền trên resource
~~~

**Kết luận:** `sub` là subject identifier của OIDC, **opaque, case-sensitive và không được tái cấp cho người khác trong phạm vi issuer**. Ứng dụng nhận diện external identity bằng **`(iss, sub)` từ ID token đã xác minh**, tôn trọng cách OP phát `public` hoặc `pairwise` subject, kiểm tra `sub` khi dùng UserInfo và không dùng email/username thay định danh. Bảo vệ subject là bảo vệ ranh giới **ai đang đăng nhập**, nhưng quyết định **người đó được làm gì** vẫn phải dựa trên grant, access token, audience, scope, tenant và authorization trên từng resource.

## Tài liệu tham khảo

- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken): claim `iss`, `sub`, `aud`, thời gian và ID token validation.
- [OpenID Connect Core 1.0 — Subject Identifier Types](https://openid.net/specs/openid-connect-core-1_0.html#SubjectIDTypes): định nghĩa `public`, `pairwise`, Sector Identifier và `sector_identifier_uri`.
- [OpenID Connect Core 1.0 — UserInfo Response](https://openid.net/specs/openid-connect-core-1_0.html#UserInfoResponse): UserInfo `sub` và yêu cầu so khớp với ID token.
- [OpenID Connect Core 1.0 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation): xác minh issuer, audience, chữ ký, thời gian và nonce.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer metadata, JWKS và `subject_types_supported`.
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): `subject_type`, `redirect_uris`, `sector_identifier_uri`.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, refresh token, scope và Authorization Code flow.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE S256 bảo vệ authorization code.
- [RFC 9207 — Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): issuer binding chống mix-up khi hỗ trợ nhiều AS.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): client/issuer binding, token leakage và bảo vệ hiện đại.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token và cách hiểu subject trong token profile.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra opaque access token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token và grant.
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OIDC login và client authentication.
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): JWT/opaque token validation.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): identity management, authentication và các rủi ro liên kết danh tính.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): authorization flow, issuer security và token handling.

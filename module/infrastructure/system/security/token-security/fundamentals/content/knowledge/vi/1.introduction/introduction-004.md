# Issuer, subject, client và resource server

## 1. Vì sao phải phân biệt bốn khái niệm này?

Trong hệ thống dùng token, câu hỏi **“Ai đang gọi API?”** chưa đủ để quyết định cho phép hay từ chối. Ta còn phải biết **ai phát hành token, token đại diện cho ai, ứng dụng nào nhận và dùng token, và API nào được phép chấp nhận token**.

Bốn khái niệm cốt lõi:

| Khái niệm | Câu hỏi cần trả lời | Ý nghĩa trong OAuth 2.0/OIDC |
|---|---|---|
| **Issuer** (bên phát hành) | Ai phát hành token và chịu trách nhiệm về các khẳng định trong token? | Thường là Authorization Server (AS); với OpenID Connect (OIDC), OpenID Provider (OP) phát hành ID token. Trong JWT, thường được biểu diễn bằng claim **iss**. |
| **Subject** (chủ thể) | Token đang nói về thực thể nào? | Thường là người dùng, đôi khi là tài khoản dịch vụ/client. Với JWT và ID token, thường được biểu diễn bằng **sub**. |
| **Client** (ứng dụng khách) | Ứng dụng nào yêu cầu, nhận và sử dụng token? | Ứng dụng web, mobile, SPA, backend hoặc dịch vụ khác; được định danh ở Authorization Server bằng **client_id**. |
| **Resource server** (máy chủ tài nguyên) | API nào bảo vệ dữ liệu và quyết định có chấp nhận request hay không? | Dịch vụ nhận access token, kiểm tra token và áp dụng chính sách truy cập đối với tài nguyên của mình. |

**Issuer là bên phát hành; subject là thực thể được mô tả; client là ứng dụng sử dụng token; resource server là nơi bảo vệ tài nguyên.** Đây là bốn vai trò khác nhau, dù một hệ thống vật lý có thể đảm nhiệm nhiều vai trò.

Trong OAuth 2.0 còn có **resource owner** (chủ sở hữu tài nguyên), thường là người dùng có quyền cho phép ứng dụng truy cập một phạm vi dữ liệu. Resource owner và subject có thể là cùng một người trong luồng đăng nhập thông thường, nhưng không nên xem chúng luôn đồng nhất. **Authentication** trả lời danh tính nào được xác thực; **authorization** quyết định danh tính hoặc ứng dụng đó được làm gì.

## 2. Một ví dụ xuyên suốt

Giả sử công ty xây dựng hệ thống quản lý đơn hàng:

- **Authorization Server/Issuer:** https://login.example.com/realms/shop
- **Subject:** người dùng có định danh nội bộ tại issuer là **user-7821**
- **Client:** ứng dụng **shop-web**, có **client_id** là shop-web
- **Resource Server:** API đơn hàng **https://orders.example.com**

Khi người dùng mở ứng dụng và xem đơn hàng của mình, ứng dụng chuyển họ tới Authorization Server để đăng nhập. Sau khi quy trình cấp quyền hoàn tất, client nhận **access token** rồi gửi token đó cho API đơn hàng. API xác minh token đến từ issuer mà nó tin cậy, được phát hành cho chính API này, còn hiệu lực và có quyền phù hợp trước khi trả dữ liệu.

Ta có thể diễn tả luồng Authorization Code kết hợp PKCE như sau:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client: shop-web
    participant AS as Issuer / Authorization Server
    participant RS as Resource Server: Orders API
    U->>C: Mở trang xem đơn hàng
    C->>AS: Yêu cầu ủy quyền (client_id, scope, PKCE)
    AS->>U: Xác thực và xin đồng ý nếu cần
    AS-->>C: Authorization code qua redirect đã đăng ký
    C->>AS: Đổi code kèm code_verifier
    AS-->>C: Access token (và token khác nếu được cấp)
    C->>RS: GET /orders, Authorization: Bearer access_token
    RS->>RS: Xác thực token, audience, scope và quyền dữ liệu
    RS-->>C: Đơn hàng hoặc lỗi 401/403
    C-->>U: Hiển thị kết quả
~~~

Trong luồng này:

1. **Người dùng không phải client**: người dùng thao tác với ứng dụng, còn ứng dụng shop-web là OAuth client.
2. **Client không phải issuer**: shop-web yêu cầu token; Authorization Server mới quyết định cấp token và ký JWT nếu dùng JWT.
3. **Issuer không mặc nhiên là resource server**: login.example.com phát hành token; orders.example.com xác thực và áp dụng chính sách truy cập.
4. **Subject không mặc nhiên là người đang cầm token**: token mang thông tin về user-7821, nhưng bearer token có thể bị người khác lấy cắp và sử dụng nếu không có cơ chế bảo vệ bổ sung.

Ví dụ này minh họa một cách triển khai. Trong thực tế, client có thể là ứng dụng không có giao diện, một API cũng có thể trở thành client khi gọi API khác, và issuer/resource server có thể cùng được triển khai trong một sản phẩm.

## 3. Issuer: ai chịu trách nhiệm phát hành token?

### 3.1. Issuer là một định danh tin cậy

Trong JWT, claim **iss** xác định bên phát hành. Ví dụ:

~~~json
{
  "iss": "https://login.example.com/realms/shop"
}
~~~

Resource server cần có **danh sách issuer được phép tin cậy được cấu hình trước**. Khi nhận JWT, API kiểm tra giá trị iss có khớp chính xác issuer được cấu hình hay không và xác minh chữ ký bằng khóa thuộc hệ thống tin cậy đó. Thông thường, Authorization Server công bố metadata và bộ khóa công khai JWKS để resource server xác minh các JWT được ký bất đối xứng.

Điều rất quan trọng: **đọc thấy một chuỗi iss trong JWT chưa chứng minh token đến từ issuer đó**. Trước khi chữ ký và các điều kiện liên quan được xác minh, phần header/payload của JWT chỉ là dữ liệu do bên gửi cung cấp. API không nên lấy tùy ý một địa chỉ JWKS từ token chưa được tin cậy rồi tải khóa về để xác thực token đó.

Thông thường, một hệ thống có cấu hình tương tự:

~~~text
trusted_issuer = https://login.example.com/realms/shop
trusted_jwks   = endpoint khóa lấy từ metadata đã tin cậy của issuer
expected_aud   = https://orders.example.com
allowed_algs   = thuật toán ký được cấu hình và hỗ trợ an toàn
~~~

**Chữ ký hợp lệ, issuer hợp lệ và audience hợp lệ đều cần thiết**. Một token do issuer đáng tin cậy ký cho API thanh toán không vì thế được phép dùng tại API đơn hàng.

### 3.2. Issuer, Authorization Server và Identity Provider liên quan thế nào?

- Trong **OAuth 2.0**, Authorization Server chịu trách nhiệm cấp access token cho client sau khi điều kiện cấp quyền được đáp ứng.
- Trong **OIDC**, OpenID Provider (OP) bổ sung lớp xác thực danh tính người dùng trên OAuth 2.0 và phát hành **ID token**. OP thường cũng chính là Authorization Server trong luồng đó.
- **Identity Provider (IdP)** là khái niệm rộng hơn về hệ thống xác thực danh tính. Một IdP có thể được liên kết hoặc triển khai cùng OP/Authorization Server, nhưng không phải mọi thuật ngữ đều đồng nghĩa trong mọi kiến trúc.

Nếu hệ thống chấp nhận nhiều issuer, cùng một chuỗi **sub** từ hai issuer có thể chỉ hai thực thể khác nhau. Do đó, một khóa định danh người dùng ổn định trong ứng dụng đa issuer thường phải xét **cặp (iss, sub)**, cộng thêm ràng buộc tenant nếu mô hình bảo mật yêu cầu.

## 4. Subject: token đại diện cho thực thể nào?

### 4.1. Ý nghĩa của sub

Claim **sub** (subject) xác định chủ thể được mô tả trong phạm vi issuer. Trong hệ thống đăng nhập, sub thường biểu diễn người dùng:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-7821"
}
~~~

Một số nguyên tắc:

- **sub không phải tên hiển thị, email hoặc số điện thoại**. Các thuộc tính này có thể thay đổi hoặc được tái sử dụng; sub được thiết kế để dùng làm định danh trong phạm vi của issuer.
- **Không giả định sub có ý nghĩa toàn cục**. Hai issuer có thể cùng cấp sub là user-7821 nhưng đó là hai danh tính khác nhau.
- Trong OIDC, nhà cung cấp có thể dùng **pairwise subject identifier**: cùng một người dùng có thể có sub khác nhau giữa các client hoặc nhóm client khác nhau để giảm khả năng liên kết danh tính.
- **sub không tự chứng minh quyền đối với một tài nguyên cụ thể**. API vẫn cần kiểm tra phạm vi quyền, quan hệ sở hữu, vai trò và quy tắc nghiệp vụ.

Ví dụ, access token có **sub=user-7821** và **scope=orders:read** chỉ cho thấy token được cấp để đọc đơn hàng trong phạm vi chính sách của hệ thống. API vẫn phải xác nhận đơn hàng số 42 thuộc người dùng đó hoặc người dùng được ủy quyền đọc đơn hàng 42.

### 4.2. Subject không phải lúc nào cũng là người dùng

Với **Client Credentials Grant**, một backend có thể yêu cầu access token để làm việc bằng quyền của chính ứng dụng, không có người dùng tham gia. Tùy cách issuer thiết kế và loại token, chủ thể có thể biểu diễn client, service account hoặc thực thể dịch vụ; cấu trúc claim không phải lúc nào cũng giống token đại diện cho người dùng.

Ví dụ:

~~~text
client_id: inventory-batch
principal: service-account/inventory-batch
scope: inventory:sync
~~~

API phải phân biệt quyền **thay mặt người dùng** với quyền **ứng dụng tự thực hiện**. Không thể chỉ dựa vào việc có claim sub rồi suy ra đây là người dùng đã đăng nhập. Cách nhận biết loại principal, grant hoặc actor phải dựa trên contract token của issuer và dữ liệu đã được xác minh, không dựa vào giá trị do request tự khai báo.

## 5. Client: ứng dụng yêu cầu và sử dụng token

Trong OAuth 2.0, **client** là ứng dụng thực hiện yêu cầu truy cập tài nguyên, thay mặt resource owner hoặc dưới quyền chính nó. Client được đăng ký tại Authorization Server, có thể được cấp **client_id**, các redirect URI cho phép và chính sách scope.

**client_id là định danh của ứng dụng, không phải định danh người dùng và không phải bí mật.** Client ID có thể xuất hiện trong URL ủy quyền và mã nguồn frontend. Khả năng xuất trình client_id không chứng minh request thực sự đến từ ứng dụng đã đăng ký.

### 5.1. Public client và confidential client

| Loại client | Ví dụ | Khả năng bảo vệ thông tin xác thực |
|---|---|---|
| **Public client** | SPA chạy trong trình duyệt, ứng dụng mobile cài trên thiết bị người dùng | Không thể giữ bí mật dài hạn một cách đáng tin cậy; thường dùng Authorization Code + PKCE và các biện pháp bảo vệ token phù hợp. |
| **Confidential client** | Web backend chạy trong hạ tầng máy chủ được kiểm soát | Có thể xác thực với token endpoint bằng phương thức được cấu hình, như client secret, private_key_jwt hoặc mTLS. |

**PKCE** ràng buộc bước đổi authorization code với bên đã tạo yêu cầu ban đầu, giúp giảm nguy cơ mã ủy quyền bị chặn và sử dụng lại. PKCE đặc biệt quan trọng với public client và cũng được khuyến nghị cho nhiều triển khai confidential client. Một client secret nhúng trong ứng dụng mobile hoặc JavaScript tải xuống trình duyệt không phải bí mật đáng tin cậy.

### 5.2. Client và subject khác nhau

Trong ví dụ:

~~~text
client_id = shop-web
sub       = user-7821
~~~

Đây là **ứng dụng shop-web** đang dùng quyền được cấp liên quan đến **người dùng user-7821**. Nếu user-9084 đăng nhập cùng ứng dụng, client_id vẫn là shop-web nhưng sub đổi thành user-9084. Ngược lại, một người dùng có thể đăng nhập qua web và mobile với hai client_id khác nhau.

Không nên đồng nhất **client_id**, claim **azp** và **sub**:

- **client_id** là định danh OAuth client; trong profile JWT access token chuẩn hóa, nó có thể xuất hiện trong payload để chỉ client mà token được cấp cho.
- **azp** (authorized party) là một claim có ngữ nghĩa riêng trong OIDC ID token, được dùng trong những tình huống cụ thể, chẳng hạn ID token có nhiều audience. Không phải mọi access token đều chứa azp.
- **sub** định danh subject. Trong một số luồng dịch vụ, subject có thể tương ứng với client, nhưng không nên mặc định hai trường đồng nghĩa.

## 6. Resource server: API quyết định request có được phép hay không

Resource server bảo vệ tài nguyên, chẳng hạn **GET /orders/42**. Client gửi access token vào request:

~~~http
GET /orders/42 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <ACCESS_TOKEN>
~~~

Token là bằng chứng cấp quyền mà API cần **xác thực trước khi tin vào claims**. Sau đó API phải áp dụng chính sách truy cập phù hợp với tài nguyên đích.

### 6.1. Access token dạng JWT và opaque được kiểm tra khác nhau

**JWT access token** là token có cấu trúc chứa claims và thường có chữ ký. Resource server có thể xác minh cục bộ bằng khóa công khai đáng tin cậy, đồng thời kiểm tra issuer, audience, thời hạn, loại token và quyền. JWT là **định dạng token**, không đồng nghĩa với OAuth và không mặc nhiên là access token.

**Opaque access token** là chuỗi mà client/resource server không cần hiểu nội dung. Resource server thường kiểm tra bằng **token introspection** với Authorization Server hoặc một cơ chế xác minh phía máy chủ được thiết kế tương đương. Với introspection, API phải xác thực để gọi endpoint nếu được yêu cầu và chỉ tin dữ liệu trả về từ endpoint đáng tin cậy.

Ví dụ phản hồi introspection minh họa:

~~~json
{
  "active": true,
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-7821",
  "client_id": "shop-web",
  "aud": "https://orders.example.com",
  "scope": "orders:read",
  "exp": 1790000000
}
~~~

Đây là phản hồi **minh họa**, không phải danh sách trường bắt buộc của mọi introspection endpoint. Ngay cả khi **active=true**, resource server vẫn phải kiểm tra token đúng audience và đủ quyền; trạng thái còn hiệu lực không đồng nghĩa được quyền làm mọi việc.

### 6.2. Chuỗi kiểm tra tối thiểu tại API

Đối với request mang access token, resource server nên thực hiện các nhóm kiểm tra sau, tùy định dạng token và hợp đồng với issuer:

1. **Kiểm tra tính xác thực:** với JWT, chỉ cho phép thuật toán ký phù hợp, xác minh chữ ký bằng khóa của issuer tin cậy; với opaque token, kiểm tra thông qua nguồn xác thực token tin cậy.
2. **Kiểm tra ngữ cảnh phát hành:** issuer phải nằm trong danh sách được chấp nhận; **aud** phải chỉ API hiện tại; token phải đúng loại dự kiến. Không chấp nhận ID token như access token.
3. **Kiểm tra thời gian và trạng thái:** xử lý **exp**, **nbf**, các điều kiện liên quan đến **iat**, độ lệch đồng hồ có kiểm soát và thông tin active/revocation nếu áp dụng.
4. **Kiểm tra quyền:** scope, role/permission hoặc policy được xác minh phải cho phép hành động tương ứng; có thể cần hạn chế theo client, tenant và loại principal.
5. **Kiểm tra đối tượng nghiệp vụ:** subject có quyền trên **đúng đơn hàng, tài khoản, tài liệu hoặc bản ghi** được yêu cầu hay không.

Với ứng dụng Java dùng Spring Security, các bước xác thực token thường thuộc lớp **OAuth2 Resource Server**; còn việc so sánh chủ sở hữu đơn hàng, tổ chức hoặc quyền nghiệp vụ cần được áp dụng tại lớp authorization thích hợp của ứng dụng. Chỉ bật xác thực JWT chưa tự giải quyết mọi quy tắc phân quyền.

Ví dụ pseudocode sau giả sử token đã vượt qua bước xác thực:

~~~text
function readOrder(verifiedAccessToken, orderId):
    require verifiedAccessToken.audiences contains "https://orders.example.com"
    require verifiedAccessToken.scopes contains "orders:read"

    order = database.findOrder(orderId)
    require order exists

    subjectKey = (verifiedAccessToken.issuer, verifiedAccessToken.subject)
    require order.ownerSubjectKey == subjectKey

    return order
~~~

Ví dụ này áp dụng cho quyền đọc đơn hàng của **người dùng sở hữu đơn**. Quyền cho quản trị viên, nhân viên chăm sóc khách hàng hoặc client dạng service account cần các nhánh policy khác được thiết kế rõ ràng; không nên bỏ qua kiểm tra sở hữu chỉ vì token có scope đọc.

## 7. Đọc claims để xác định đúng các vai trò

Giả sử Authorization Server phát hành một JWT access token theo profile có header/payload **minh họa**:

~~~json
{
  "header": {
    "alg": "RS256",
    "typ": "at+jwt",
    "kid": "key-2026-01"
  },
  "payload": {
    "iss": "https://login.example.com/realms/shop",
    "sub": "user-7821",
    "aud": ["https://orders.example.com"],
    "client_id": "shop-web",
    "scope": "orders:read orders:list",
    "iat": 1790000000,
    "exp": 1790000900,
    "jti": "tok-abc-123"
  }
}
~~~

Đây là JSON trình bày header/payload đã giải mã cho mục đích học tập, **không phải JWT hoàn chỉnh được ký**. Các timestamp chỉ là dữ liệu ví dụ.

| Trường | Cách hiểu đúng |
|---|---|
| **iss** | Issuer nào nhận trách nhiệm phát hành token |
| **sub** | Chủ thể được biểu diễn trong token; trong ví dụ là user-7821 |
| **aud** | Resource server/dịch vụ được chỉ định nhận token; ở đây là Orders API |
| **client_id** | Client mà token được cấp cho; ở đây là shop-web |
| **scope** | Các phạm vi truy cập đã được cấp; cần diễn giải theo policy tại API |
| **iat**, **nbf**, **exp** | Thời điểm phát hành, thời điểm bắt đầu có hiệu lực (nếu có) và hết hạn |
| **jti** | Định danh token khi issuer cung cấp; có thể phục vụ kiểm toán hoặc chặn token cụ thể |
| **kid** | Gợi ý chọn khóa xác minh trong tập khóa tin cậy; bản thân kid không chứng minh nguồn gốc |
| **typ** | Gợi ý/phân loại loại JWT khi profile sử dụng; không thể thay thế xác thực chữ ký và claims |

Không phải mọi hệ thống đều phát hành JWT có đúng các trường trên. Claim **client_id** và giá trị typ **at+jwt** phản ánh một profile access token phổ biến; claims tùy biến hoặc tên audience có thể khác theo hợp đồng với issuer. Ứng dụng chỉ được dựa vào các trường mà issuer thực sự cam kết và resource server đã xác minh.

### 7.1. So sánh access token, ID token và refresh token

| Loại token | Nơi dùng chính | Mục đích | Quan hệ với các vai trò |
|---|---|---|---|
| **Access token** | Client gửi tới **resource server** | Gọi API trong phạm vi được cấp | Issuer cấp token; subject/actor tùy loại grant; **audience phải phù hợp resource server** |
| **ID token** (OIDC) | **Client** nhận và xác minh | Chuyển thông tin kết quả xác thực người dùng cho client | Issuer là OP; **sub** là người dùng được xác thực; **aud thường chứa client_id** |
| **Refresh token** | Client gửi về **token endpoint của Authorization Server** | Xin access token mới theo chính sách | Không gửi cho resource server; gắn với client/grant và phải được bảo vệ đặc biệt |

Ví dụ ID token OIDC minh họa:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-7821",
  "aud": "shop-web",
  "iat": 1790000000,
  "exp": 1790000900,
  "nonce": "nonce-from-login-request"
}
~~~

Đối chiếu hai ví dụ: **ID token có audience là client shop-web**, còn **access token có audience là Orders API**. Vì vậy, dùng ID token để gọi API đơn hàng là sai mục đích ngay cả khi ID token có chữ ký hợp lệ. Client phải xác minh ID token theo quy tắc OIDC, bao gồm issuer, audience, thời hạn và nonce khi luồng yêu cầu. Resource server phải xác minh **access token** theo quy tắc API.

Refresh token thường được biểu diễn như một chuỗi bí mật và không cần tự giải mã. Nó phải được gửi tới đúng token endpoint, giữ trong vùng lưu trữ phù hợp với kiến trúc client và được quản lý vòng đời bằng giới hạn thời gian, chính sách thu hồi hoặc rotation. Việc phát hành refresh token phụ thuộc grant và chính sách Authorization Server; không phải client nào cũng được cấp.

## 8. Ranh giới tin cậy giữa issuer, client và resource server

### 8.1. Mối quan hệ tin cậy

**Client ↔ Authorization Server:** client đăng ký định danh, redirect URI, grant, scope và phương thức xác thực thích hợp. Authorization Server kiểm tra các điều kiện cấp token, chứ không cấp mọi scope client tự yêu cầu.

**Authorization Server → Resource Server:** API tin cậy một hoặc nhiều issuer được cấu hình, xác minh token theo JWKS/metadata hoặc introspection, đồng thời ràng buộc audience. Đây là quan hệ phải được thiết lập trong cấu hình triển khai, không suy từ thông tin do client gửi.

**Client → Resource Server:** client mang access token để gọi API. Với **bearer token**, khả năng trình token có thể đủ để sử dụng quyền token trong thời gian còn hiệu lực; vì vậy HTTPS, lưu trữ an toàn và chống rò rỉ rất quan trọng. Token có thể bị đánh cắp dù issuer và chữ ký hoàn toàn hợp lệ.

**Resource Server → tài nguyên:** API quyết định một principal có được thực hiện hành động đối với tài nguyên cụ thể hay không. Quyết định này thường phụ thuộc dữ liệu nội bộ mà issuer không biết, như chủ sở hữu đơn hàng hoặc tư cách thành viên của tổ chức.

### 8.2. Một token dùng cho nhiều API?

Giả sử cùng hệ thống có **Orders API** và **Payments API**. Access token có **aud=https://orders.example.com** phải bị Payments API từ chối, dù cả hai API tin cùng issuer. Điều này giúp giới hạn nơi token bị đánh cắp có thể được sử dụng.

Khi Orders API cần gọi Payments API, Orders API đang đóng thêm vai trò **OAuth client** của dịch vụ tiếp theo. Nó cần access token phù hợp với **audience và scope của Payments API** theo luồng cấp token đã được thiết kế (ví dụ client credentials cho quyền dịch vụ hoặc token exchange/on-behalf-of nếu kiến trúc hỗ trợ). Không nên chuyển tiếp tùy ý access token nhận từ trình duyệt cho một API khác.

## 9. Vòng đời token và tác động đến bốn vai trò

| Giai đoạn | Ai chịu trách nhiệm chính? | Điều cần kiểm soát |
|---|---|---|
| **Đăng ký client** | Authorization Server và đội vận hành | client_id, redirect URI, loại client, grant, scope và phương thức xác thực client |
| **Phát hành** | Issuer / Authorization Server | danh tính hoặc loại principal, client nhận token, audience, scope, thời gian sống, khóa ký |
| **Lưu trữ và gửi** | Client | chống lộ access/refresh token; dùng HTTPS; tránh đưa token vào URL, log, analytics hoặc mã nguồn |
| **Xác minh và phân quyền** | Resource Server | chữ ký/active, issuer, audience, thời hạn, scope, tenant, ownership và policy |
| **Làm mới** | Client và Authorization Server | refresh token, client authentication/PKCE theo luồng, giới hạn quyền, rotation và phát hiện tái sử dụng |
| **Hết hạn/thu hồi** | Authorization Server và Resource Server | chính sách token lifetime, revocation, introspection, danh sách chặn hoặc chiến lược vô hiệu hóa session |

Với JWT access token được resource server xác minh **hoàn toàn offline**, việc issuer thu hồi một refresh token không tự làm các access token đã phát hành biến mất ngay. Token có thể tiếp tục được chấp nhận tới khi hết hạn, trừ khi hệ thống triển khai thêm cơ chế kiểm tra trạng thái hoặc chặn token. Ngược lại, kiểm tra opaque token qua introspection thường cho phép resource server thấy thay đổi trạng thái sớm hơn, phụ thuộc cache và cách vận hành.

Các biện pháp thường phối hợp với nhau: access token sống ngắn; refresh token được lưu cẩn thận và rotation theo chính sách; phát hiện refresh token reuse; giới hạn scope/audience; cơ chế sender-constrained token như **DPoP** hoặc **mTLS** khi phù hợp để giảm khả năng dùng lại token bị đánh cắp. Không biện pháp riêng lẻ nào thay thế được việc resource server kiểm tra quyền nghiệp vụ.

## 10. Sai lầm thường gặp và cách tự kiểm tra

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ giải mã JWT, đọc sub rồi tin ngay | Kẻ tấn công có thể tự tạo payload có sub bất kỳ | Xác minh chữ ký/nguồn xác thực token và toàn bộ điều kiện tin cậy trước khi sử dụng claims |
| Chỉ kiểm tra chữ ký, bỏ qua iss hoặc aud | Token hợp lệ về mật mã nhưng được phát hành bởi bên không được phép hoặc cho API khác | Ràng buộc issuer được cấu hình và audience của API |
| Dùng ID token làm bearer access token | Trộn xác thực đăng nhập với ủy quyền API | Client kiểm tra ID token; API chỉ nhận access token phù hợp |
| Coi client_id là user ID | Gán nhầm quyền của ứng dụng cho người dùng hoặc ngược lại | Phân biệt client, subject và loại principal |
| Có scope là cho đọc mọi bản ghi | Lỗi truy cập ngang quyền, ví dụ đọc đơn hàng của người khác | Kiểm tra thêm ownership, tenant và quyền theo đối tượng |
| Nhúng client secret trong SPA/mobile | Secret bị trích xuất và không còn là bí mật | Thiết kế như public client; dùng Authorization Code + PKCE |
| Dùng access token cho mọi microservice | Token lộ ở một dịch vụ có thể bị dùng ở dịch vụ khác | Dùng audience riêng và cơ chế lấy token cho dịch vụ đích |
| Ghi access/refresh token vào log | Lộ quyền truy cập dù token phát hành đúng | Chỉ ghi metadata cần thiết; che hoặc loại bỏ token thô khỏi log |
| Cho rằng đổi mật khẩu hoặc revoke refresh token luôn vô hiệu JWT đang lưu hành | Các request với JWT còn hạn có thể tiếp tục được chấp nhận | Thiết kế rõ thời gian sống và cơ chế thu hồi access token nếu yêu cầu phản ứng tức thời |

### Tình huống kiểm tra nhanh

Một request gửi JWT đến Orders API với:

~~~text
iss       = https://login.example.com/realms/shop
sub       = user-7821
aud       = https://payments.example.com
client_id = shop-web
scope     = orders:read
exp       = thời điểm trong tương lai
~~~

Giả sử chữ ký hợp lệ và issuer đáng tin, **Orders API vẫn phải từ chối** vì **aud** chỉ Payments API. Scope orders:read không sửa được sai lệch audience.

Nếu audience là Orders API và token có scope orders:read, request đọc đơn hàng thuộc **user-9999** vẫn phải bị từ chối khi user-7821 không được ủy quyền đọc đơn hàng đó. **Token hợp lệ không đồng nghĩa thao tác nghiệp vụ hợp lệ.**

Nếu token có sub đại diện **service account** thay vì người dùng, API cần áp dụng policy dịch vụ tương ứng; không được ép nó vào quy tắc sở hữu của người dùng rồi suy diễn quyền tùy tiện.

### Câu hỏi tự ôn

1. Hai JWT có cùng sub nhưng khác iss có chắc đại diện cùng một người dùng không? **Không.** sub được hiểu trong phạm vi issuer; hệ thống đa issuer phải phân biệt cặp (iss, sub).
2. Một ID token OIDC có aud là shop-web có thể dùng để gọi Orders API không? **Không.** Nó dành cho client xác minh đăng nhập, không phải access token cho Orders API.
3. Client shop-web và resource server Orders API có thể là cùng một chương trình không? **Có.** Vai trò được xác định theo hành vi trong từng tương tác: chương trình là resource server khi nhận token để bảo vệ endpoint và là client khi đi xin token để gọi dịch vụ khác.
4. JWT có chữ ký hợp lệ và scope orders:read đã đủ cấp quyền xem đơn hàng 42 chưa? **Chưa.** API còn phải kiểm tra issuer, audience, loại token, hạn và quyền đối với chính đơn hàng 42.

## 11. Ghi nhớ khi thiết kế hệ thống token

Khi đọc một sơ đồ OAuth/OIDC hoặc một access token, hãy xác định theo đúng thứ tự:

1. **Issuer là ai?** Token có do Authorization Server/OP mà hệ thống tin cậy phát hành và được xác minh đúng cách không?
2. **Subject là ai hoặc cái gì?** Đây là người dùng, service account hay principal khác? Định danh có nằm đúng phạm vi issuer không?
3. **Client nào xin và sử dụng token?** Nó được định danh/xác thực bằng cách nào, giữ token ở đâu và được cấp quyền gì?
4. **Resource server nào nhận token?** Audience có khớp API không, token còn hợp lệ không và policy có cho phép hành động trên tài nguyên cụ thể không?

Mô hình này giúp đọc đúng **iss, sub, client_id, aud và scope**, hiểu vì sao **JWT/opaque** chỉ là những cách biểu diễn hoặc xác minh access token, và phân biệt trách nhiệm của **access token, ID token, refresh token** trong toàn bộ vòng đời xác thực và phân quyền.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): các vai trò resource owner, client, authorization server, resource server.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): issuer, subject, audience và cách xác minh ID token.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): các claim và phân loại JWT access token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái token qua Authorization Server.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh JWT an toàn.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): khuyến nghị bảo vệ authorization code, refresh token và access token.

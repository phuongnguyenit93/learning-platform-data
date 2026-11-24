# Claim biểu diễn sự kiện hoặc thuộc tính nào?

## Mục tiêu học tập

Trong chương **Claims** của học phần bảo mật token, một *claim* là **một phát biểu về một chủ thể, token, quá trình xác thực hoặc ngữ cảnh sử dụng**, do bên phát hành đưa ra. Claim có thể mô tả **thuộc tính** (chẳng hạn định danh chủ thể) hoặc thông tin về **sự kiện** (chẳng hạn thời điểm xác thực đã diễn ra). Nhưng claim là **lời khẳng định được ghi vào dữ liệu**, không phải bản thân sự kiện thực tế, và không phải mặc nhiên là bằng chứng đủ để cấp quyền.

Sau bài này, bạn có thể:

1. Định nghĩa claim trong JWT/OIDC và phân biệt claim về **token**, **chủ thể**, **sự kiện xác thực**, **quyền ủy nhiệm** và **ngữ cảnh ứng dụng**.
2. Giải thích chính xác `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti` và các claim OIDC như `auth_time`, `amr`, `acr`, `email_verified`.
3. Hiểu khác biệt giữa giá trị claim **được ghi nhận lúc phát hành** và trạng thái **đang đúng tại thời điểm gọi API**.
4. Kiểm tra kiểu dữ liệu, ngữ nghĩa và nguồn tin cậy của claim, đặc biệt với access token JWT, ID token và opaque token.
5. Dùng claim làm **đầu vào có kiểm chứng** cho quyết định phân quyền theo scope, audience, tenant và tài nguyên thực tế mà không nhầm nó với quyền tuyệt đối.

## 1. Claim là “phát biểu” chứ không phải “chân lý tự thân”

Trong JWT (JSON Web Token), **claim** là một cặp **tên – giá trị** trong một đối tượng JSON. Nó thể hiện điều mà bên tạo token **khẳng định** về chủ thể hoặc những yếu tố liên quan:

~~~json
{
  "sub": "user-123",
  "email_verified": true,
  "auth_time": 1893455700,
  "aud": "shop-web"
}
~~~

Tạm diễn giải thành lời:

- `sub = user-123`: token mô tả chủ thể có định danh `user-123` **trong không gian định danh của issuer**.
- `email_verified = true`: bên phát hành đã ghi nhận địa chỉ email tương ứng là đã được xác minh theo quy trình của họ; không phải bằng chứng rằng email hiện tại là bất biến hoặc đủ làm quyền quản trị.
- `auth_time = 1893455700`: bên phát hành khẳng định một **sự kiện xác thực người dùng** diễn ra tại thời điểm đó (Unix time), nếu claim này phù hợp với loại token và profile.
- `aud = shop-web`: token dành cho đối tượng nhận `shop-web`; không có nghĩa một API bất kỳ được dùng token.

Điều này làm rõ câu hỏi **“Claim biểu diễn sự kiện hoặc thuộc tính nào?”**: cần biết *claim nói về cái gì*, *ở thời điểm nào*, *issuer nào đang phát biểu* và *người nhận nào được quyền dựa vào phát biểu ấy*.

### Ba điều cần tách bạch

| Cấp độ | Diễn giải | Có đủ để cấp quyền chưa? |
|---|---|---|
| **Giá trị khai báo** | JSON trong payload có `role: "admin"`. | **Không**: bất cứ ai cũng có thể tạo JSON này. |
| **Claim đã xác minh nguồn** | JWT được xác minh bằng khóa tin cậy và claim đúng cấu trúc, đúng issuer/audience. | **Chưa chắc**: token có thể sai mục đích, role đã cũ hoặc không áp dụng cho tài nguyên này. |
| **Quyết định authorization** | API kiểm tra claim phù hợp **cùng** quyền, tenant, trạng thái và đối tượng đang thao tác. | **Có thể cho phép**, nếu toàn bộ chính sách hiện hành được đáp ứng. |

Kể cả với JWT đã ký hợp lệ, `sub` chỉ nhận diện **chủ thể được token mô tả**. Với **bearer token**, nó không chứng minh người đang cầm token là chính chủ thể gốc: token có thể bị đánh cắp và phát lại.

## 2. Các loại thông tin mà claim có thể biểu diễn

Không phải claim nào cũng là “thông tin người dùng”. Một số claim mô tả **token**, một số mô tả **sự kiện**, một số diễn đạt **thuộc tính hoặc điều kiện ủy quyền**.

| Nhóm | Ví dụ | Claim biểu diễn gì? | Điều không được suy ra |
|---|---|---|---|
| **Nguồn phát hành** | `iss` | Danh tính issuer đã phát hành token. | Chuỗi `iss` tự nó không chứng minh issuer thật sự đã ký token. |
| **Chủ thể** | `sub` | Định danh principal/chủ thể do issuer quy định. | Không bảo đảm bên đang gửi request chính là người dùng đó. |
| **Đối tượng nhận** | `aud` | Client hoặc API mà token được hướng tới, tùy loại token. | Không phải danh sách quyền tùy ý cho mọi API cùng hệ thống. |
| **Vòng đời token** | `iat`, `nbf`, `exp`, `jti` | Thời điểm phát hành, khoảng hiệu lực và định danh token. | Không chứng minh phiên hiện tại chưa bị thu hồi hay token không bị phát lại. |
| **Sự kiện xác thực** | `auth_time`, `amr`, `acr` | Lúc xác thực và phương thức/ngữ cảnh xác thực được ghi nhận. | Không khẳng định request hiện tại vừa làm MFA hoặc thiết bị còn an toàn. |
| **Thuộc tính danh tính** | `name`, `email`, `email_verified` | Thông tin được issuer biết hoặc khẳng định về chủ thể. | Không tự là quyền nghiệp vụ hay định danh duy nhất toàn cục. |
| **Ủy quyền truy cập** | `scope`, `roles`, `permissions` | Phạm vi hoặc quyền được phát biểu theo hợp đồng token. | Không tự cho phép xem/sửa mọi bản ghi. |
| **Ngữ cảnh ứng dụng** | `tenant_id`, `department` | Thông tin miền nghiệp vụ được đưa vào token. | Không mặc nhiên là claim chuẩn, tin cậy hoặc còn mới. |

Các nhóm giúp đọc ý nghĩa, **không phải phân loại cứng trong một chuẩn duy nhất**. Cùng một claim có thể ảnh hưởng nhiều bước: `aud` là thông tin về đối tượng nhận nhưng cũng là điều kiện bắt buộc để API quyết định có được chấp nhận token hay không.

## 3. Nhóm claim chuẩn trong JWT: token do ai cấp, cho ai và đến khi nào?

RFC 7519 định nghĩa một số **registered claim names** phổ biến. “Registered” nghĩa là tên và ý nghĩa được đăng ký để các hệ thống hiểu nhất quán; **không có nghĩa mọi JWT đều bắt buộc phải chứa tất cả**. Một profile như JWT access token cho OAuth 2.0 có thể đặt thêm yêu cầu bắt buộc riêng.

### `iss` – issuer

~~~json
{"iss": "https://auth.example.test"}
~~~

**Diễn giải:** token khẳng định issuer là `https://auth.example.test`. Resource Server phải so khớp với **issuer đã được cấu hình tin cậy** và dùng đúng tập khóa/endpoint xác minh của issuer ấy. Không lấy `iss` chưa xác minh làm lý do tự thêm một nhà phát hành mới vào danh sách tin cậy.

### `sub` – subject

~~~json
{"sub": "user-123"}
~~~

**Diễn giải:** token nói về chủ thể `user-123`. Định danh cần được diễn giải trong **phạm vi issuer**; hai issuer khác nhau có thể cùng dùng chuỗi `user-123` cho các chủ thể khác nhau. Với OIDC, cặp **`(iss, sub)`** thường là khóa nhận dạng ổn định hơn email. Trong luồng `client_credentials`, chủ thể có thể là ứng dụng hoặc service principal theo profile, không nhất thiết người dùng cuối.

**Không nhầm** `sub` với `client_id`: `client_id` nhận diện ứng dụng được cấp token, còn `sub` nhận diện chủ thể mà token nói đến theo ngữ nghĩa của issuer.

### `aud` – audience

~~~json
{"aud": "orders-api"}
~~~

Hoặc, nếu profile hỗ trợ nhiều đối tượng nhận:

~~~json
{"aud": ["orders-api", "reporting-api"]}
~~~

**Diễn giải:** token dự kiến được xử lý bởi những đối tượng nhận được nêu. Với **access token**, Resource Server phải thuộc audience được cấp; với **OIDC ID token**, audience thường hướng tới **client ID**, nên ID token không được dùng thay access token của API.

Kiểm tra phải xét đúng kiểu dữ liệu (chuỗi hoặc mảng được cho phép), đúng giá trị và hợp đồng profile. Không kiểm tra bằng cách tìm chuỗi con như `aud.includes("orders")`, vì `another-orders-api` có thể bị chấp nhận nhầm.

### `iat`, `nbf`, `exp` – thời điểm và giới hạn hiệu lực

~~~json
{
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456900
}
~~~

Các giá trị trên là **NumericDate**: số giây tính từ Unix epoch, **không phải mili-giây** của JavaScript `Date.now()`. Chúng diễn đạt:

- **`iat` – issued at:** token được phát hành lúc nào. Đây là phát biểu về **sự kiện cấp token**, không phải lúc người dùng xác thực.
- **`nbf` – not before:** token chưa được chấp nhận trước thời điểm này.
- **`exp` – expiration:** token không được chấp nhận tại hoặc sau thời điểm hết hạn.

Thông thường điều kiện thời gian là `now >= nbf` và `now < exp`, có thể tính một khoảng lệch đồng hồ nhỏ theo chính sách. **`iat` không tự bảo đảm token “mới”**; nếu API cần giới hạn tuổi token, phải có quy tắc riêng.

JWT vẫn có chữ ký hợp lệ sau khi hết hạn: **chữ ký không tự thay thế kiểm tra `exp`**. Token có `exp` ở tương lai cũng không nói rằng tài khoản chưa bị khóa hoặc quyền chưa bị thu hồi.

### `jti` – JWT ID

~~~json
{"jti": "session-a-token-438f"}
~~~

**Diễn giải:** một định danh của JWT, có thể dùng cho log đã được làm sạch dữ liệu, danh sách thu hồi hoặc cơ chế nhận biết phát lại **nếu hệ thống có quy tắc và lưu trạng thái tương ứng**. Chỉ thêm `jti` **không** biến access token thành token dùng một lần và không tự ngăn attacker phát lại bản sao bearer token.

### Bảng nhận diện nhanh

| Claim | Phát biểu về | Kiểu thường gặp theo JWT | Cần kiểm tra gì? |
|---|---|---|---|
| `iss` | Nơi phát hành | Chuỗi | Issuer tin cậy, khóa gắn đúng issuer. |
| `sub` | Chủ thể | Chuỗi | Cách diễn giải theo issuer và profile. |
| `aud` | Người nhận | Chuỗi hoặc mảng chuỗi | Audience dành cho endpoint hiện tại. |
| `exp` | Hạn hết hiệu lực | NumericDate | Không chấp nhận sau `exp`. |
| `nbf` | Thời điểm bắt đầu hiệu lực | NumericDate | Không chấp nhận trước `nbf`. |
| `iat` | Sự kiện phát hành token | NumericDate | Tuổi token nếu chính sách yêu cầu. |
| `jti` | Định danh token | Chuỗi | Chính sách định danh, thu hồi hoặc theo dõi riêng nếu có. |

## 4. Claim về sự kiện xác thực trong OIDC

OIDC đưa các thông tin xác thực danh tính lên trên OAuth 2.0. Trong OIDC, **ID token** được cung cấp cho **client** để biểu diễn kết quả xác thực người dùng. Một số claim giúp client hiểu **khi nào** và **theo cách nào** việc xác thực diễn ra.

Ví dụ **payload ID token minh họa**:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "shop-web",
  "iat": 1893456000,
  "exp": 1893456900,
  "auth_time": 1893455700,
  "amr": ["pwd", "otp"],
  "acr": "urn:example:assurance:strong",
  "nonce": "opaque-client-request-value",
  "email": "user@example.test",
  "email_verified": true
}
~~~

**Lưu ý:** các trường không bắt buộc xuất hiện đồng thời ở mọi ID token. Phần lớn giá trị là ví dụ để học ngữ nghĩa, không phải lời khẳng định rằng `urn:example:assurance:strong` có cấp bảo đảm chuẩn toàn cầu.

### `auth_time` – sự kiện đăng nhập/xác thực diễn ra khi nào?

`auth_time` ghi thời điểm **End-User authentication** do OpenID Provider (OP) báo cáo, tính theo NumericDate. Nó **khác** `iat`:

~~~text
auth_time = 10:00    # Người dùng hoàn tất xác thực
iat       = 10:25    # OP phát hành một ID token sau đó
~~~

Hai thời điểm có thể khác vì phiên đăng nhập tồn tại, token được phát hành lại hoặc các luồng tương tác khác. Nếu nghiệp vụ yêu cầu xác thực gần đây để xác nhận thao tác nhạy cảm, hãy đánh giá `auth_time` và chính sách **reauthentication/step-up**, không đơn giản nhìn `iat` rồi kết luận “mới đăng nhập”.

### `amr` – các phương thức xác thực được sử dụng

`amr` (Authentication Methods References) có thể là mảng chứa những phương thức được sử dụng trong quá trình xác thực, chẳng hạn ví dụ `["pwd", "otp"]`. Ý nghĩa các mã phải theo định nghĩa và hợp đồng của nhà cung cấp; không tự suy rằng mọi giá trị `otp` đều đạt cùng mức bảo đảm hoặc một mã tự động khẳng định MFA đạt chuẩn.

### `acr` – ngữ cảnh/lớp bảo đảm xác thực

`acr` (Authentication Context Class Reference) chỉ lớp ngữ cảnh xác thực mà OP khẳng định đã đáp ứng. Giá trị cụ thể phụ thuộc thỏa thuận giữa client và OP. Ứng dụng cần định nghĩa rõ **lớp nào đủ cho hành động nhạy cảm**, không chỉ kiểm tra claim tồn tại.

### `nonce` – liên kết phản hồi OIDC với yêu cầu

Trong những luồng OIDC sử dụng `nonce`, client tạo giá trị không đoán trước và kiểm tra ID token trả về có **nonce khớp với yêu cầu xác thực ban đầu**. Điều đó giúp liên kết phản hồi với phiên yêu cầu và góp phần giảm một số kiểu phát lại/trộn phản hồi. **`nonce` của ID token không phải cơ chế chống phát lại chung cho mọi bearer access token**.

### `email`, `email_verified` – thuộc tính tại thời điểm nguồn phát hành biết

- `email` là thông tin về địa chỉ email; có thể thay đổi, không nhất thiết duy nhất toàn hệ thống.
- `email_verified` cho biết OP đã thực hiện bước xác minh quyền kiểm soát email theo chính sách tại thời điểm ghi nhận; **không** đồng nghĩa email là chứng chỉ pháp lý, quyền truy cập ứng dụng hoặc định danh bất biến.

Không nên tự động cấp role `admin` vì một địa chỉ email có domain cụ thể nếu không có cơ chế xác minh danh tính/tổ chức và policy rõ ràng. Dùng `(iss, sub)` cho liên kết danh tính ổn định thường phù hợp hơn sử dụng email làm khóa chính.

**Quan trọng:** những claim OIDC này không biến **ID token** thành access token. API nghiệp vụ phải yêu cầu access token có audience/mục đích phù hợp và kiểm tra quyền riêng của API.

## 5. Claim phục vụ ủy quyền trong access token

**Access token** dùng để yêu cầu quyền truy cập **Resource Server**. Claims trong access token JWT, hoặc metadata tương ứng khi introspection opaque token, thường giúp Resource Server xác định **phạm vi được cấp**.

Ví dụ một access token JWT **minh họa**:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "tenant_id": "tenant-a",
  "iat": 1893456000,
  "exp": 1893456900
}
~~~

Các nhóm thông tin khác nhau:

- `sub` và `client_id` nói về **chủ thể** và **client**; không thể hoán đổi.
- `aud` xác định **Resource Server** được phép tiếp nhận.
- `scope` nói về phạm vi ủy quyền đã được cấp theo hợp đồng AS–RS.
- `tenant_id` là claim **đặc thù hệ thống** để giúp đánh giá ngữ cảnh tenant; không phải claim bắt buộc của mọi JWT.

### `scope` khác `role` và `permission`

Giả sử `scope="orders:read"`. Token cho phép client **yêu cầu** thao tác đọc các đơn mà chủ thể được phép truy cập, **không tự cấp quyền đọc mọi đơn hàng**.

| Thông tin | Ví dụ | Ý nghĩa | Chưa đủ kết luận |
|---|---|---|---|
| **Scope** | `orders:read` | Phạm vi truy cập API đã cấp. | Được đọc đơn của người khác. |
| **Role** | `support-agent` | Vai trò nghiệp vụ theo chính sách hệ thống. | Support mọi tenant. |
| **Permission** | `orders:read:any` | Quyền thao tác định nghĩa cụ thể trong ứng dụng. | Bỏ qua ràng buộc tenant/trạng thái dữ liệu. |
| **Ownership** | `order.ownerId == sub` | Quan hệ giữa principal và bản ghi. | Có quyền xóa hoặc hoàn tiền. |

`scope` là tên claim phổ biến trong các **profile JWT access token**, ví dụ RFC 9068; cách biểu diễn có thể khác khi AS và API dùng một hợp đồng khác. `roles`, `permissions`, `tenant_id` là những tên thường gặp ở ứng dụng, **không phải registered JWT claim bắt buộc**. Luôn xác định rõ claim nào được phát hành, có kiểu dữ liệu gì và được phép sử dụng ở đâu.

### Principal, action, resource, context

Một quyết định phân quyền thực tế có thể xem như:

~~~text
authorize(principal, action, resource, context) -> PERMIT hoặc DENY
~~~

Ví dụ:

~~~text
principal: user-123, tenant-a
action:    orders:read
resource:  order-42, owner=user-999, tenant-b
context:   request truy cập từ ứng dụng shop-web
token:     aud=orders-api, scope=orders:read, còn hạn
decision:  DENY nếu không có ủy quyền liên tenant rõ ràng
~~~

Token có thể vượt qua lớp xác minh và vẫn **bị từ chối** ở lớp object-level authorization. Thiếu lớp này dẫn đến rủi ro **BOLA/IDOR** và truy cập chéo tenant.

## 6. Claim có phải là ảnh chụp trạng thái hiện tại không?

Nhiều claim phản ánh thông tin **tại thời điểm issuer ghi nhận hoặc phát hành token**. Một chữ ký hợp lệ về sau chỉ chứng minh token không bị sửa trái phép theo khóa đã tin cậy; nó **không tự cập nhật** nội dung claims khi thế giới thay đổi.

### Tình huống: quyền đã bị thu hồi nhưng JWT còn hạn

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant C as Client
    participant Admin as Người quản trị
    participant API as Orders API
    AS-->>C: JWT có permission=orders:write, exp sau 15 phút
    Admin->>AS: Thu hồi permission của user
    C->>API: Gửi JWT cũ còn hạn
    API->>API: Kiểm tra chữ ký và exp: vẫn hợp lệ
    Note over API: Permission trong JWT có thể là bản chụp đã cũ
    API->>API: Kiểm tra policy/quyền hiện hành nếu nghiệp vụ yêu cầu
    API-->>C: Cho phép hoặc từ chối theo chính sách hiện hành
~~~

Các ví dụ claim có thể **lạc hậu**:

| Claim/thông tin | Điều có thể thay đổi sau khi phát hành | Hướng xử lý |
|---|---|---|
| `roles` / `permissions` | Người dùng mất quyền hoặc bị chuyển bộ phận. | TTL phù hợp; kiểm tra quyền hiện hành với hành động nhạy cảm. |
| `tenant_id` / membership | Chủ thể rời tenant hoặc bị loại khỏi nhóm. | Đối chiếu membership theo chính sách và cô lập tenant phía API. |
| `email` / `email_verified` | Email thay đổi hoặc quyền sở hữu bị thay đổi. | Không dùng email như khóa quyền ổn định; cập nhật nguồn danh tính. |
| `auth_time` / `amr` / `acr` | Bước xác thực cũ không còn đủ “gần đây” cho thao tác mới. | Reauthentication hoặc step-up theo yêu cầu, xác minh kết quả đúng profile. |
| `sub` / trạng thái tài khoản | Tài khoản bị khóa dù subject vẫn là cùng định danh. | Kiểm tra trạng thái phiên/tài khoản hoặc cơ chế thu hồi. |

**JWT tự xác minh cục bộ:** nếu API chỉ kiểm tra chữ ký, issuer, audience và `exp`, access token đã được phát hành có thể vẫn được chấp nhận cho đến khi hết hạn. **Opaque token với introspection:** trạng thái tập trung có thể cập nhật nhanh hơn, nhưng cache introspection vẫn gây độ trễ. Vì vậy cần chính sách TTL, thu hồi và độ tươi của quyền theo mức rủi ro.

### Claim về sự kiện không phải bản ghi audit toàn diện

`iat` cho biết thời điểm token được phát hành; `auth_time` cho biết thời điểm xác thực người dùng do OP khẳng định. Những giá trị này **không thay thế** nhật ký kiểm toán độc lập, lịch sử cập nhật trạng thái, địa chỉ IP đã được xác minh hoặc bằng chứng giao dịch. Một hệ thống cần chứng minh chuỗi sự kiện pháp lý/nghiệp vụ phải có nguồn audit riêng phù hợp.

## 7. Kiểu dữ liệu, tên claim và hợp đồng diễn giải

Payload JSON có thể chứa **chuỗi, số, boolean, mảng, object hoặc null**. Tuy nhiên, từng claim chuẩn hoặc profile có **kiểu và ngữ nghĩa được quy định**. Không tự ép kiểu để làm cho một token sai cấu trúc trở nên được chấp nhận.

Ví dụ:

~~~json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456900,
  "email_verified": true,
  "amr": ["pwd", "otp"],
  "scope": "orders:read orders:write",
  "tenant_id": "tenant-a"
}
~~~

### Các bẫy kiểu dữ liệu

1. `"exp": "1893456900"` là **chuỗi**, không phải NumericDate theo kiểu mà claim `exp` yêu cầu. Không nên tự ngầm chuyển đổi rồi bỏ qua lỗi profile.
2. `"email_verified": "false"` là chuỗi không rỗng; ở một số ngôn ngữ hoặc thư viện, ép sang boolean có thể cho kết quả **true**. Với OIDC, cần xử lý đúng **boolean `false`**.
3. `"aud": "orders-api"` và `"aud": ["orders-api"]` là hai dạng JWT hỗ trợ; chỉ dùng kiểu và cardinality được token profile cho phép.
4. `"scope": "orders:read orders:write"` là chuỗi gồm các giá trị scope cách nhau bằng dấu cách theo cách biểu diễn thường gặp của OAuth/JWT access token profile. Không kiểm tra bằng tìm chuỗi con, ví dụ `scope.includes("orders:read")` có thể nhận nhầm `orders:read:all`.
5. `"roles": ["admin"]` không đồng nghĩa `"roles": "admin"`; app cần hợp đồng kiểu dữ liệu cụ thể thay vì tự đoán.
6. `null`, claim **vắng mặt** và chuỗi rỗng là các trường hợp khác nhau. Nếu một claim cần thiết cho quyết định quyền mà không hiện diện hợp lệ, API phải **từ chối** theo nguyên tắc mặc định không cấp quyền.

### Nhóm tên claim trong JWT

RFC 7519 phân biệt:

| Loại tên | Ý nghĩa | Ví dụ |
|---|---|---|
| **Registered claim names** | Tên được đăng ký với ý nghĩa chuẩn. | `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`. |
| **Public claim names** | Tên do bên sử dụng định nghĩa, nên đăng ký hoặc dùng tên chống xung đột theo quy tắc RFC. | Một tên định danh URI được thiết kế để tránh va chạm. |
| **Private claim names** | Tên do hai hoặc nhiều bên thống nhất sử dụng. | `tenant_id`, `department`, `permissions` trong hợp đồng riêng. |

Với claim đặc thù, cần tài liệu rõ **kiểu**, **nguồn cập nhật**, **độ tươi**, **tính nhạy cảm**, **đối tượng nhận** và **ý nghĩa phân quyền**. Nếu nhiều đội dùng cùng tên `role` với nghĩa khác nhau, dễ xảy ra **claim confusion**. Dùng tên có namespace hoặc quy ước rõ giúp giảm xung đột, nhưng **không thay xác minh và phân quyền**.

## 8. Một claim đáng tin qua những lớp kiểm tra nào?

Trước khi dùng claim, API phải đánh giá **cả token chứa nó**.

~~~mermaid
flowchart TD
    A["Client trình token"] --> B{"Định dạng, loại và kích thước hợp lệ?"}
    B -- Không --> X["401 / Từ chối"]
    B -- Có --> C{"Nguồn xác minh đáng tin cậy?"}
    C -- Không --> X
    C -- Có --> D{"Chữ ký JWT hợp lệ / introspection đáng tin?"}
    D -- Không --> X
    D -- Có --> E{"iss, aud, exp, nbf, token purpose và trạng thái phù hợp?"}
    E -- Không --> X
    E -- Có --> F{"Kiểu và ngữ nghĩa claims cần thiết hợp lệ?"}
    F -- Không --> X
    F -- Có --> G{"Scope, policy hiện hành, quyền trên resource đủ?"}
    G -- Không --> Y["403 / Từ chối"]
    G -- Có --> Z["Cho phép thao tác đúng phạm vi"]
~~~

**Với JWT ký (JWS):** parse/decode Base64URL chỉ giúp đọc payload, **không** xác minh được nguồn phát hành. API cần kiểm tra chữ ký với khóa thuộc issuer đã được cấu hình, giới hạn thuật toán được chấp nhận và kiểm tra các claims. **Với JWT mã hóa (JWE):** giải mã thành công không nhất thiết chứng minh issuer; nếu profile yêu cầu chữ ký, cần xác minh lớp ký tương ứng, ví dụ nested JWT. **Với opaque token:** API lấy trạng thái/metadata từ hệ thống introspection hoặc kho tra cứu đáng tin, không đoán claims từ hình thức token.

Không tự tải khóa ký từ URL hoặc issuer được token chưa xác minh đề xuất; không chấp nhận thuật toán không nằm trong chính sách của API. Cũng không chấp nhận **ID token** hoặc **refresh token** làm access token chỉ vì chúng có những claim quen thuộc.

### Mã giả thực thi ở Resource Server

~~~text
request GET /orders/42 with Bearer <access-token>

policy = trustedConfiguration("orders-api")
verified = verifyTokenForResourceServer(request.token, policy)
    # JWT: trusted issuer/signing key/alg + required claims
    # Opaque: authenticated introspection + active/metadata
if not verified:
    return 401

claims = verified.claims
require claims.audience matches "orders-api"
require claims.tokenType == access_token
require claims.notExpired and claims.notBeforeSatisfied

if "orders:read" not in normalizedGrantedScopes(claims):
    return 403

order = repository.get("42")
if order is absent:
    return 404

principal = verifiedPrincipalFromClaims(claims)
if not canRead(principal, order, currentPolicy):
    return 403  # hoặc 404 theo chính sách bảo vệ sự tồn tại

return 200 with allowed order fields
~~~

Đây là **mã giả về thứ tự kiểm soát**, không phải cú pháp của một thư viện cụ thể. Việc lựa chọn các claim bắt buộc và giá trị mong đợi phải do **hợp đồng với issuer và Resource Server** quy định. JWT có claim `scope` không bắt buộc mọi hệ thống phải tổ chức principal theo đúng cách trên.

## 9. Ví dụ Java: đọc claim đã xác minh, không tự parse token

Sau khi một lớp bảo mật chuẩn của ứng dụng đã xác minh **access token dành cho API này**, service có thể dùng các thuộc tính đã chuẩn hóa để quyết định quyền. Ví dụ sau chỉ minh họa **phần policy Java**, không bao gồm quá trình xác minh JWS/JWE/introspection:

~~~java
import java.util.Objects;
import java.util.Set;

record VerifiedPrincipal(
    String subject,
    String tenantId,
    Set<String> scopes,
    boolean active
) {}

record Order(String id, String ownerId, String tenantId) {}

final class OrderAuthorization {
    static boolean canRead(VerifiedPrincipal principal, Order order) {
        if (principal == null || order == null || !principal.active()) {
            return false;
        }
        if (principal.scopes() == null
                || !principal.scopes().contains("orders:read")) {
            return false;
        }
        if (principal.subject() == null || principal.subject().isBlank()
                || principal.tenantId() == null || principal.tenantId().isBlank()) {
            return false;
        }
        if (!Objects.equals(principal.tenantId(), order.tenantId())) {
            return false;
        }
        return Objects.equals(principal.subject(), order.ownerId());
    }
}
~~~

Lớp dựng `VerifiedPrincipal` **phải** lấy dữ liệu từ kết quả xác minh token, và ở mức rủi ro phù hợp cần kiểm tra trạng thái tài khoản/tenant hiện hành. `Order` phải lấy từ **cơ sở dữ liệu tin cậy**, không dùng đối tượng do client tự khai nhận làm căn cứ ownership. Thao tác `write`, `cancel` hoặc quyền quản trị cần policy riêng; `orders:read` không bao hàm các quyền đó.

### Tại sao không dùng `email` làm định danh chính?

Giả sử một API tạo user từ `email`, rồi cho phép tải dữ liệu của bất kỳ tài khoản có email trùng. Email có thể thay đổi hoặc được tái sử dụng; OP khác nhau có thể báo cùng email, và trạng thái xác minh có ý nghĩa theo chính sách riêng. Với OIDC, nên **liên kết danh tính theo `(iss, sub)` được xác minh**, rồi dùng ID nội bộ để quản lý tài nguyên và quyền. Email vẫn có thể phục vụ hiển thị/liên hệ nhưng không mặc nhiên đủ làm khóa phân quyền.

## 10. Các ngộ nhận về claim thường tạo lỗi bảo mật

| Ngộ nhận | Vì sao sai? | Cách hiểu đúng |
|---|---|---|
| “Có `sub` và `role` trong JWT tức là user đã được xác thực.” | JSON có thể tự tạo; JWT có thể sai chữ ký, issuer, audience hoặc hạn. | Xác minh token bằng chính sách tin cậy trước khi dùng claims. |
| “`iat` là lần đăng nhập gần nhất.” | `iat` là **lúc cấp token**, có thể cách xa `auth_time`. | Dùng `auth_time`/chính sách reauthentication khi cần độ mới xác thực. |
| “`email_verified=true` nghĩa là email luôn đúng và có quyền trong công ty.” | Đó là lời khẳng định của OP theo quy trình xác minh, không là quyền nghiệp vụ. | Liên kết danh tính bền vững và kiểm tra quyền ở hệ thống đích. |
| “`scope=orders:read` cho phép đọc mọi đơn.” | Scope không nói ai sở hữu bản ghi hoặc thuộc tenant nào. | Kiểm tra object-level authorization. |
| “`aud` chứa tên API gần giống thì dùng được.” | So khớp chuỗi con mở rộng audience ngoài dự kiến. | So khớp audience đúng chuẩn và hợp đồng. |
| “`exp` chưa đến thì token chắc chắn chưa bị thu hồi.” | Hết hạn và thu hồi là hai cơ chế khác nhau. | Áp dụng kiểm tra trạng thái/TTL theo yêu cầu. |
| “`jti` có là đã chống replay.” | `jti` chỉ là mã định danh; không có kiểm tra trạng thái tự động. | Phải có cơ chế chống phát lại nếu yêu cầu. |
| “`roles` và `permissions` là claim bắt buộc của mọi JWT.” | Tên có thể là private claims hoặc do profile định nghĩa. | Đọc hợp đồng token/profile từng AS và API. |
| “ID token có `email` nên gửi API thay access token được.” | ID token dành cho client OIDC, audience/mục đích khác. | Resource Server chỉ chấp nhận access token hợp lệ. |
| “Thấy `amr` có `otp` thì mọi thao tác nhạy cảm đều được phép.” | Mức bảo đảm, độ mới, loại giao dịch tùy policy. | Đối chiếu `acr`/`amr`/`auth_time` theo hợp đồng và step-up khi cần. |

## 11. Tình huống tự kiểm tra

**Tình huống A – Token có chữ ký đúng nhưng claim về quyền đã cũ.** Một access token JWT có `roles=["finance-admin"]` và còn hạn 15 phút. Quản trị viên vừa thu hồi role. API chỉ xác minh chữ ký và `exp`, sau đó cho phép hoàn tiền. Điểm yếu nằm ở đâu?

**Giải thích:** Claim phản ánh trạng thái khi token được phát hành. Với thao tác nhạy cảm, hệ thống cần chính sách cập nhật/thu hồi và kiểm tra quyền hiện hành đủ nhanh, thay vì coi role trong token là dữ liệu luôn đúng.

**Tình huống B – Phân biệt thời điểm xác thực với phát hành token.** OIDC ID token có `auth_time=10:00` và `iat=11:00`. Ứng dụng yêu cầu người dùng vừa xác thực lại trong 5 phút trước khi thay đổi mật khẩu. Chỉ kiểm tra `iat` có đủ không?

**Giải thích:** Không. `iat` chỉ nói thời điểm phát hành token. Cần đánh giá `auth_time` và thực hiện lại xác thực hoặc step-up theo chính sách.

**Tình huống C – Claim thiếu hoặc sai kiểu.** API nhận `"exp": "1893456900"` dạng chuỗi. Có nên coi hợp lệ sau khi tự ép kiểu không?

**Giải thích:** Không nên. `exp` là NumericDate theo chuẩn; một token sai kiểu hoặc không đáp ứng profile cần được từ chối theo chính sách xác minh thống nhất.

**Tình huống D – Dùng email để liên kết tài khoản.** Hai issuer phát hành ID token cho hai người khác nhau nhưng cùng email. Có thể coi họ là cùng principal không?

**Giải thích:** Không. Email không phải định danh bất biến toàn cục; trong OIDC, cặp `(iss, sub)` được xác minh là căn cứ liên kết danh tính thích hợp hơn, kết hợp quy tắc quản lý tài khoản nội bộ.

**Tình huống E – Đúng scope nhưng sai tài nguyên.** JWT hợp lệ cho `orders-api` có `scope=orders:read`, chủ thể ở tenant A nhưng order thuộc tenant B. API có trả order không?

**Giải thích:** Không, trừ khi hệ thống có quyền liên tenant được cấp riêng và kiểm tra rõ ràng. Claim scope không thay chính sách trên bản ghi.

**Tình huống F – Bearer token bị sao chép.** Kẻ tấn công lấy được JWT với `sub=user-123`, `jti` và chữ ký hợp lệ. Token chưa hết hạn. Claim `jti` tự ngăn kẻ tấn công gọi API không?

**Giải thích:** Không. Nếu API nhận bearer token thuần túy và không có kiểm soát phát lại/thu hồi, bản sao token có thể được dùng trong phạm vi quyền. Giảm rủi ro bằng TLS, lưu trữ an toàn, không log token, TTL/scope/audience hẹp và cân nhắc DPoP/mTLS khi cần ràng buộc người gửi.

## Checklist khi thiết kế và đọc claims

1. **Định nghĩa ý nghĩa:** mỗi claim đang nói về token, chủ thể, sự kiện xác thực, ngữ cảnh hay quyền nào? Nêu rõ issuer và người nhận.
2. **Định nghĩa kiểu:** `exp`/`iat`/`nbf` là NumericDate, `email_verified` là boolean trong OIDC, `aud` hỗ trợ chuỗi/mảng theo profile, scopes có cấu trúc được quy ước rõ.
3. **Định nghĩa nguồn tin:** chữ ký/JWE/introspection phải được xác minh trước khi dùng dữ liệu; không tin payload tự decode hoặc claim do client tự gửi.
4. **Định nghĩa thời gian:** phân biệt `iat` với `auth_time`, thuộc tính tại thời điểm cấp với trạng thái hiện hành, xác định độ trễ thu hồi cho phép.
5. **Định nghĩa mục đích:** access token dành cho API, ID token dành cho client OIDC, refresh token dùng ở token endpoint; không hoán đổi chỉ vì cùng là JWT.
6. **Định nghĩa ranh giới quyền:** audience đúng API, scope đúng action, principal/tenant/ownership/quyền cụ thể đúng tài nguyên.
7. **Giảm thông tin nhạy cảm:** chỉ đưa claims thật sự cần vào token; JWS ký thông thường đọc được payload và token có thể đi qua log/công cụ trung gian nếu thiết kế sai.
8. **Kiểm thử từ chối:** claim vắng mặt, `null`, sai kiểu, sai issuer/audience, hết hạn, role cũ, sai tenant, token bị thu hồi và bearer token bị phát lại.

## Ghi nhớ

**Claim là một lời khẳng định có cấu trúc, do issuer phát biểu về chủ thể, token, sự kiện xác thực hoặc ngữ cảnh ủy quyền.** `iat` nói về sự kiện phát hành token; `auth_time` nói về sự kiện xác thực người dùng; `sub` và `email` mô tả danh tính/thuộc tính; `aud`, `exp` và `scope` định hướng giới hạn sử dụng. **Lời khẳng định chỉ đáng tin trong đúng mô hình xác minh và đúng thời điểm**, và vẫn phải đi qua chính sách phân quyền đối với tài nguyên thực tế. Không có một claim đơn lẻ nào thay thế toàn bộ việc xác minh token, bảo vệ vòng đời, thu hồi hay chống phát lại.

### Tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 – JSON Web Token Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [OpenID Connect Core 1.0 – ID Token and Standard Claims](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 8176 – Authentication Method Reference Values](https://www.rfc-editor.org/rfc/rfc8176)
- [RFC 9449 – OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)

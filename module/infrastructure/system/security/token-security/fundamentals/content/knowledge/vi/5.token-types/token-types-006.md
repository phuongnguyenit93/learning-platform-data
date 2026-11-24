# Opaque token

Một API nhận được chuỗi `Authorization: Bearer 7Z_tP0...` sẽ làm thế nào để biết chuỗi đó có hợp lệ, thuộc về ai và được phép làm gì? Nếu giá trị này không chứa các claims có thể đọc và xác minh trực tiếp, API cần một **nguồn tin cậy bên ngoài** để diễn giải token. Đó là tình huống thường gặp khi hệ thống dùng **opaque token**.

**Opaque token** là token mà bên nhận không thể hoặc không nên tự diễn giải cấu trúc và ý nghĩa từ chính chuỗi token. Trong triển khai OAuth 2.0 phổ biến, opaque access token là một **chuỗi tham chiếu khó đoán**: Authorization Server (AS) quản lý trạng thái token, còn Resource Server (RS, máy chủ API) xác minh nó bằng **token introspection** hoặc tra cứu ở kho dữ liệu tin cậy.

Bài học thuộc chương **Token types** của module SECURITY_TOKEN_SECURITY_FUNDAMENTALS. Mục tiêu là hiểu cách token được phát hành, sử dụng, kiểm tra, thu hồi và bảo vệ trước nguy cơ bị đánh cắp hoặc phát lại; đồng thời phân biệt rõ opaque token với JWT, access token, refresh token trong OAuth 2.0/OpenID Connect (OIDC).

Sau bài này, bạn có thể giải thích opaque token hoạt động như thế nào, đọc được kết quả introspection, hiểu yêu cầu kiểm tra audience/scope, chọn chiến lược cache/thu hồi hợp lý và tránh coi opaque token là cơ chế tự chống đánh cắp.

## 1. Opaque nghĩa là gì và không có nghĩa là gì?

Từ **opaque** có nghĩa là “không trong suốt” đối với bên tiêu thụ: chuỗi token không có giao kèo định dạng để client hoặc API tự tách lấy claims. Ví dụ minh họa:

~~~text
9r8gkV4mEJYhf4m2T5hyQOxpUV7YFQ6G3v0nTrqWc2M
~~~

Đây chỉ là giá trị giả để minh họa, không phải credential thật. Một triển khai phổ biến tạo chuỗi ngẫu nhiên có entropy cao bằng **bộ sinh số ngẫu nhiên an toàn về mật mã (CSPRNG)** và lưu một bản ghi trạng thái tương ứng ở phía Authorization Server. Các trường như chủ thể, client, scope, audience và thời hạn được lưu hoặc tính toán tại nơi phát hành, không nhất thiết nằm trong chuỗi client đang giữ.

Điểm cần phân biệt:

- **Opaque là tính chất về cách bên nhận nhìn token**, không khẳng định một định dạng nhị phân cụ thể. Một token tự chứa nhưng được mã hóa cũng có thể là opaque đối với bên không có quyền giải mã; token opaque **không bắt buộc** được triển khai bằng database lookup.
- **JWT là định dạng** gồm những phần được mã hóa theo cấu trúc xác định; JWT thông dụng có chữ ký cho phép verifier kiểm tra claims tại chỗ. JWT được ký **không mặc nhiên được mã hóa**, nên payload thường đọc được dù không sửa được mà vẫn giữ chữ ký hợp lệ.
- **Access token là mục đích sử dụng** để gọi Resource Server. Nó có thể là JWT hoặc opaque token.
- **Refresh token là mục đích sử dụng** để xin access token mới tại Authorization Server. Refresh token thường được client xử lý như một chuỗi opaque và **không gửi vào API nghiệp vụ**.
- **Bearer token là phương thức sử dụng credential**: bên nào giữ token hợp lệ có thể dùng nó theo phạm vi được cấp. Opaque access token hoàn toàn có thể là bearer token; opaque **không tự ngăn phát lại**.

Vì vậy, không thể suy luận “opaque = an toàn hơn JWT trong mọi trường hợp” hoặc “opaque = luôn phải gọi database cho mỗi request”. Cách kiểm tra và mức độ bảo vệ phụ thuộc kiến trúc triển khai.

## 2. Mô hình phát hành và xác minh opaque access token

Giả sử ứng dụng đặt hàng có Authorization Server, client và Orders API. Sau một OAuth 2.0 flow phù hợp, Authorization Server cấp một opaque access token cho client. Nó lưu hoặc quản lý thông tin cần thiết để kiểm tra token về sau.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant RS as Orders API (Resource Server)
    C->>AS: OAuth 2.0 flow, nhận ủy quyền
    AS->>AS: Tạo token ngẫu nhiên và trạng thái
    AS-->>C: access_token = opaque string
    C->>RS: GET /orders + Bearer access_token
    RS->>AS: Introspect token (xác thực RS)
    AS-->>RS: active, scope, sub, aud, exp...
    RS->>RS: Kiểm tra chính sách truy cập
    RS-->>C: Kết quả API hoặc từ chối
~~~

Điều cần ghi nhớ trong sơ đồ:

1. **Authorization Server** biết mối liên hệ giữa giá trị opaque token và metadata/trạng thái của nó. Nó có thể lưu tham chiếu, quản lý token tập trung hoặc sử dụng một triển khai tương đương.
2. **Client** chỉ cần giữ và gửi chuỗi theo giao thức; không được tự diễn giải, sửa token hoặc coi mọi token giống nhau.
3. **Resource Server** không thể kiểm tra tính hợp lệ chỉ bằng cách phân tích các ký tự của opaque token. Nó dùng introspection hoặc kho dữ liệu tin cậy được thiết kế cho mục đích xác minh.
4. **Resource Server vẫn quyết định phân quyền** dựa trên kết quả kiểm tra token và dữ liệu của tài nguyên, ví dụ đơn hàng nào thuộc người gọi.

Opaque token thường giúp tập trung kiểm soát trạng thái tại Authorization Server, nhưng có chi phí tra cứu và sự phụ thuộc vào khả năng sẵn sàng của hệ thống xác minh.

## 3. Token introspection theo OAuth 2.0

**OAuth 2.0 Token Introspection (RFC 7662)** định nghĩa cách một bên được ủy quyền, thường là Resource Server, hỏi Authorization Server về trạng thái và metadata của token. Endpoint này phải được bảo vệ; thông thường Resource Server **xác thực với Authorization Server** bằng cơ chế được hai bên thống nhất.

Ví dụ request đến endpoint introspection của issuer (địa chỉ và credential chỉ mang tính minh họa):

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-resource-server-credentials>

token=<opaque-access-token>&token_type_hint=access_token
~~~

Trong đó:

- `token` là credential cần kiểm tra. Giá trị thực phải được gửi qua **HTTPS**, tránh URL query string, log và hệ thống giám sát không bảo vệ.
- `token_type_hint` là **gợi ý** giúp Authorization Server tìm đúng loại token, **không phải** bằng chứng token thuộc loại ấy và không thay bước xác minh ngữ cảnh.
- `Authorization: Basic ...` chỉ minh họa một cách xác thực client của endpoint introspection. Cấu hình thực tế có thể dùng phương thức khác theo yêu cầu issuer; không nhúng secrets vào mã nguồn hoặc tài liệu cấu hình công khai.
- **Introspection endpoint dành cho thành phần được cấp quyền**; không công khai token metadata cho mọi client không xác thực.

Một phản hồi thành công đối với token đang hoạt động có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "client_id": "web-orders",
  "token_type": "Bearer",
  "sub": "user-123",
  "scope": "orders:read",
  "aud": ["orders-api"],
  "iss": "https://auth.example.org",
  "iat": 1899999000,
  "exp": 1900000800
}
~~~

Đây là ví dụ về **metadata**, không phải contract bắt buộc mọi Authorization Server phải trả lại đủ mọi field. `active` là trường cốt lõi; các giá trị còn lại phụ thuộc khả năng và chính sách của issuer. `exp` và `iat` là Unix timestamp (giây). `scope` thường là một chuỗi các scope phân tách bằng dấu cách. `aud` là đối tượng nhận token; API nên có hợp đồng rõ ràng về việc issuer trả claim này hoặc ràng buộc audience theo cách khác đáng tin cậy.

Nếu token hết hạn, bị thu hồi, không được nhận biết hoặc caller không được phép biết thông tin token đó, Authorization Server có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
~~~

**`200 OK` của HTTP introspection không có nghĩa token hợp lệ.** Nó chỉ cho biết request introspection đã được xử lý thành công; Resource Server phải đọc `active`. Với token không hoạt động, không nên dựa vào metadata không được bảo đảm để phân quyền hoặc tiết lộ thông tin nhạy cảm.

Ngược lại, nếu endpoint introspection bị lỗi mạng, trả 5xx hoặc Resource Server không xác thực được, đó là **lỗi của quy trình kiểm tra**, không phải tín hiệu Permit. Với endpoint bảo vệ dữ liệu, chính sách thường là **fail closed**: từ chối yêu cầu hoặc trả lỗi tạm thời, tuyệt đối không coi token hợp lệ chỉ vì không tra cứu được.

### Resource Server phải kiểm tra những gì sau introspection?

Một phản hồi `active=true` **chưa đủ** để cho phép mọi thao tác:

1. **Tin đúng nguồn introspection:** endpoint được cấu hình sẵn theo issuer đáng tin, kết nối bảo mật, xác thực dịch vụ và kiểm soát quyền truy cập phù hợp.
2. **Token đang hoạt động:** `active` đúng kiểu boolean và là `true`; kiểm tra thời gian, loại token và trạng thái bổ sung theo hợp đồng với issuer.
3. **Token dành cho API này:** có `aud` phù hợp hoặc cơ chế ràng buộc Resource Server tương đương do Authorization Server thực thi. Tránh lấy “active” làm lý do chấp nhận token cấp cho API khác.
4. **Scope đủ cho thao tác:** ví dụ GET /orders cần `orders:read`. Scope không tự cho phép đọc đơn hàng của người khác.
5. **Chủ thể và điều kiện nghiệp vụ:** người dùng hoặc client còn quyền trên đối tượng, tenant, trạng thái và quan hệ hiện hành.

Nếu response introspection không có thông tin cần thiết để xác lập audience hoặc principal theo policy, Resource Server phải áp dụng **hợp đồng xác minh đã thiết kế** hoặc từ chối; không tự suy đoán hay bổ sung quyền.

## 4. Introspection không giống JWT signature validation

Hai mô hình có thể cùng hoàn thành yêu cầu xác thực token, nhưng ranh giới tin cậy và nguồn dữ liệu khác nhau:

| Khía cạnh | Opaque access token dạng tham chiếu | JWT access token tự chứa, có chữ ký |
|---|---|---|
| Chuỗi token | Không công bố cấu trúc claims cho bên nhận | Có cấu trúc JWT; payload thường đọc được |
| Xác minh điển hình | Introspection/kho trạng thái được tin cậy | Kiểm chữ ký và claims tại Resource Server |
| Nguồn quyền/trạng thái token | Authorization Server hoặc nơi quản lý trạng thái | Claims khi phát hành; cần bổ sung tra cứu nếu muốn biết trạng thái mới |
| Thu hồi trước khi hết hạn | Có thể thể hiện qua `active=false` ngay ở nguồn | Thường cần denylist, trạng thái bổ sung hoặc chờ hết hạn |
| Tính sẵn sàng khi issuer tạm không phản hồi | Có thể phụ thuộc introspection/cache | Có thể tiếp tục xác minh với key đã cache nếu cấu hình/chính sách cho phép |
| Chi phí mỗi request | Có thể cần request mạng, cache hoặc truy vấn | Thường là chi phí xác minh chữ ký tại chỗ |
| Rủi ro khi token bị đánh cắp | Bearer token vẫn bị phát lại khi còn hoạt động | Bearer token cũng bị phát lại khi còn hiệu lực |
| Khả năng cập nhật quyền hiện hành | Nguồn introspection có thể trả dữ liệu mới | Claims có thể cũ; có thể phải tra quyền hiện hành riêng |

Điểm quan trọng: **JWT và opaque token không phải hai mức độ bảo mật tuyệt đối**. Nếu JWT được introspection thêm hoặc opaque token được cache lâu, khác biệt về thu hồi nhanh sẽ thay đổi. Nếu introspection bị xâm phạm, `active=true` cũng không còn là bằng chứng đáng tin. Cần kiểm soát **cả nguồn phát hành lẫn nguồn xác minh**.

## 5. Access token, refresh token và OIDC trong hệ thống opaque token

Những tên gọi này mô tả các khía cạnh khác nhau của token:

| Khái niệm | Bản chất | Ai nên dùng? | Lưu ý |
|---|---|---|---|
| **Opaque access token** | Access token mà bên nhận không đọc trực tiếp claims | Client gửi đến Resource Server; RS kiểm tra theo cơ chế tin cậy | Có thể dùng Bearer; phải kiểm `aud`, `scope`, trạng thái và quyền tài nguyên |
| **JWT access token** | Access token có định dạng JWT | Client gửi đến Resource Server; RS kiểm chữ ký/claims | Chữ ký không tự thu hồi token trước `exp` |
| **Refresh token** | Credential xin access token mới | Client gửi đến token endpoint của Authorization Server | Không dùng gọi API nghiệp vụ; cần bảo vệ đặc biệt, rotation/thu hồi tùy loại client |
| **OIDC ID token** | Chứng cứ kết quả xác thực danh tính dành cho client/Relying Party | Client xác minh theo OIDC | Không dùng ID token để thay access token cho Resource Server |

Ví dụ, client đăng nhập qua **Authorization Code Flow với PKCE** và nhận:

~~~json
{
  "access_token": "gQ89fV1nXxw7b8...opaque-value...",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "pT2cR3...another-opaque-value...",
  "scope": "orders:read"
}
~~~

Đây là ví dụ giản lược; việc có refresh token phụ thuộc **loại client, flow và chính sách cấp token**. Với OIDC, response còn có thể chứa ID token theo các yêu cầu của flow. `expires_in` là số giây access token có hiệu lực tại thời điểm phát hành. **Refresh token không phải access token dài hạn** và không gửi trong `Authorization` khi gọi Orders API.

Một ứng dụng dùng opaque access token có thể vẫn dùng JWT cho **ID token** và cơ chế khác cho **refresh token**. Đừng suy format và quyền sử dụng chỉ từ tên field hoặc nhìn thấy chuỗi ngẫu nhiên.

## 6. Thu hồi token, đăng xuất và độ trễ khi có cache

Một lý do nhiều hệ thống chọn opaque access token là **khả năng kiểm soát trạng thái tập trung**. Khi Authorization Server vô hiệu hóa bản ghi token, các lần introspection mới có thể trả `active=false`, kể cả token chưa hết thời hạn ban đầu.

**OAuth 2.0 Token Revocation (RFC 7009)** mô tả một endpoint để client yêu cầu thu hồi token theo cơ chế xác thực/chính sách của Authorization Server. Ví dụ:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-client-credentials>

token=<token-to-revoke>&token_type_hint=refresh_token
~~~

`token_type_hint` là gợi ý loại token, không chứng minh token thuộc loại đó. Authorization Server có thể hỗ trợ thu hồi refresh token và access token theo thiết kế; hiệu ứng lan sang token liên quan tùy chính sách và loại token. Request thu hồi thành công không có nghĩa **mọi cache của Resource Server đã được xóa**.

Giả sử:

1. 10:10:00 — Resource Server introspect token và cache `active=true` trong 60 giây.
2. 10:10:15 — Quản trị viên thu hồi token tại Authorization Server.
3. 10:10:30 — Resource Server vẫn có thể chấp nhận phản hồi đã cache nếu chưa hết TTL, **nếu kiến trúc không có invalidation đẩy**.
4. Sau khi cache hết hạn hoặc bị vô hiệu hóa, Resource Server introspect lại và nhận `active=false`.

Các mốc chỉ để minh họa, không phải độ trễ tiêu chuẩn. Thời gian còn chấp nhận token bị thu hồi phụ thuộc **thời điểm cache được tạo, TTL, phương án invalidation và trạng thái hệ thống**.

### Chính sách cache cần trả lời được gì?

- **TTL tối đa bao lâu?** Giới hạn theo mức độ nhạy cảm, khả năng chấp nhận quyền cũ và thời gian còn lại đến `exp` nếu issuer cung cấp. TTL cache không nên kéo dài vượt quá hiệu lực token.
- **Khi cần thu hồi ngay sẽ làm gì?** Có thể không cache phản hồi Permit, dùng cache invalidation/push revocation, kiểm tra trạng thái mỗi lần hoặc sử dụng ranh giới bảo mật bổ sung.
- **Cache key gồm gì?** Tối thiểu phân biệt chính xác token và **ngữ cảnh xác minh** như Resource Server/audience nếu response phụ thuộc caller. Nên dùng định danh băm an toàn để tránh giữ token thô ở cache/log.
- **Cache kết quả inactive ra sao?** Nếu cache âm, cần hiểu trường hợp token mới được phát hành hoặc trạng thái thay đổi và giới hạn TTL; không làm lộ dữ liệu token.
- **Khi introspection lỗi thì sao?** Không biến lỗi kết nối thành `active=true`. Chỉ được sử dụng cache còn hiệu lực theo chính sách an ninh đã định; sau yêu cầu thu hồi khẩn cấp, không dùng cache cũ để bỏ qua lệnh chặn.

**Đăng xuất client** thường gồm xóa thông tin phiên ở client và thu hồi refresh token/phiên theo chính sách. Với access token opaque, nếu có hỗ trợ thu hồi và RS kiểm tra trạng thái đủ mới, token có thể bị chặn sớm. Tuy nhiên **đăng xuất không mặc định có hiệu lực tức thì ở mọi API** khi đã có cache hoặc nhiều bên phát hành.

## 7. Opaque token có chống bị đoán, đánh cắp hoặc phát lại không?

Opaque chỉ mô tả cách token được biểu diễn và kiểm tra. Tính an toàn phụ thuộc vào **độ khó đoán, bí mật khi vận chuyển/lưu trữ và cách kiểm soát vòng đời**.

### 7.1. Không thể đoán token bằng cách thử ngẫu nhiên

Với opaque token dạng tham chiếu, Authorization Server nên dùng **CSPRNG** và đủ entropy để kẻ tấn công không thể dự đoán hoặc brute-force thực tế. Ví dụ, 256 bit entropy từ bộ sinh an toàn là một lựa chọn mạnh phổ biến, nhưng độ dài/định dạng cần phù hợp thiết kế. **Chuỗi dài không đảm bảo entropy cao** nếu được sinh từ timestamp, số đếm, thông tin người dùng hoặc random không an toàn.

Token phải được xử lý như secret; tại nơi lưu trữ, có thể lưu **hash/định danh dẫn xuất một chiều** dùng để tra cứu thay vì bản rõ, nếu kiến trúc cho phép. Cách này làm giảm hậu quả lộ kho dữ liệu, nhưng không thay thế kiểm soát quyền truy cập, bảo vệ backup và giám sát hành vi bất thường. Tránh log toàn bộ token; nếu cần đối soát, dùng ID an toàn hoặc digest được thiết kế để không lộ credential.

### 7.2. Bị đánh cắp bearer token vẫn có thể bị phát lại

Ai lấy được một opaque bearer access token đang hoạt động đều có thể gửi nó đến API phù hợp và được chấp nhận trong phạm vi quyền cho đến khi hết hạn/thu hồi. Introspection **không tự ngăn** hai request đồng thời dùng cùng một token.

Biện pháp quan trọng gồm:

- Bắt buộc **TLS/HTTPS** khi cấp, gửi, introspect và revoke token; không đặt bearer token trong URL query string.
- Dùng **scope và audience tối thiểu**, hạn dùng access token đủ ngắn cho mức rủi ro, giới hạn quyền theo tài nguyên tại Resource Server.
- Bảo vệ nơi lưu token. Với ứng dụng web, cân nhắc **Backend for Frontend (BFF)** hoặc cookie `HttpOnly; Secure; SameSite` phù hợp cùng biện pháp phòng CSRF; không mặc định lưu token lâu dài trong `localStorage` khi rủi ro XSS cao.
- Bảo vệ refresh token nghiêm ngặt hơn vì nó có thể cấp thêm access token. Áp dụng rotation, phát hiện sử dụng lại và/hoặc sender-constraining theo loại client và quy định bảo mật áp dụng.
- Khi cần giảm khả năng sử dụng token bị lộ ở thiết bị khác, cân nhắc **sender-constrained tokens** như DPoP hoặc mTLS khi Authorization Server và Resource Server hỗ trợ; RS phải kiểm chứng bằng chứng sở hữu theo đúng giao thức.

**Không suy rằng opaque token mặc nhiên là token dùng một lần**, có nonce chống phát lại hoặc có ràng buộc thiết bị. Các thuộc tính này phải được thiết kế riêng.

### 7.3. Bảo vệ chính endpoint introspection

Introspection là dịch vụ có thể tiết lộ danh tính, scope và trạng thái token. Do đó:

- Chỉ cho những Resource Server/client được cấp quyền gọi; xác thực và phân quyền caller trên endpoint.
- Dùng TLS, bảo vệ credential của Resource Server, giới hạn quyền introspection theo các token/audience mà caller có trách nhiệm xác minh.
- Áp dụng giới hạn tốc độ, giám sát lượng truy vấn, từ chối truy cập bất thường và không trả metadata nhạy cảm cho caller không được phép.
- Tránh ghi nguyên tham số `token`, request body chứa token, response chứa thông tin cá nhân hoặc các secrets vào log.
- Có cơ chế xử lý sự cố khi Authorization Server, endpoint introspection hoặc thông tin xác thực của Resource Server bị xâm phạm.

Vì mọi quyết định dựa trên kết quả introspection, **một nguồn introspection bị kiểm soát** có thể báo `active=true` sai. Đây là điểm gốc tin cậy cần được bảo vệ như signing key trong hệ thống JWT.

## 8. Thiết kế kiểm tra opaque token tại Resource Server

Ví dụ Orders API có endpoint `GET /orders/{orderId}`. Chính sách:

1. Token phải đang hoạt động và dành cho **orders-api**.
2. Token phải có scope **orders:read**.
3. Chủ thể phải là thành viên hợp lệ trong tenant sở hữu đơn hàng, hoặc có quyền được ủy quyền cụ thể.
4. Nếu token không hợp lệ, từ chối trước khi truy cập dữ liệu; nếu quyền không đủ, từ chối thao tác với tài nguyên.

Pseudocode:

~~~text
getOrder(request):
    token = requireBearerAccessToken(request)
    if token missing:
        return 401 Unauthorized

    metadata = introspectWithTrustedAuthorizationServer(token)
    if introspection unavailable / unauthenticated / malformed:
        return temporary_error_or_deny  # Không fail-open

    if metadata.active != true:
        return 401 Unauthorized

    if not audienceAllowed(metadata, "orders-api"):
        return 401 Unauthorized

    if not isAccessTokenOfExpectedType(metadata):
        return 401 Unauthorized

    if metadata.exp exists and metadata.exp <= now:
        return 401 Unauthorized

    if not hasScope(metadata.scope, "orders:read"):
        return 403 Forbidden

    order = loadOrderUnderTenantBoundary(request.orderId)
    if order absent:
        return 404 Not Found

    if not canReadOrder(metadata.sub, metadata.client_id, order):
        return 403 Forbidden

    return 200 OK + allowedOrderFields(order)
~~~

Đây là mã **minh họa trình tự quyết định**, không phải thư viện bảo mật hoặc quy định HTTP cho mọi API. Hàm `audienceAllowed` cần được xây dựng từ hợp đồng tin cậy với Authorization Server; nếu issuer không trả `aud`, cần một ràng buộc đã được xác minh tương đương thay vì mặc nhiên cho phép. Với client credentials, `sub` có thể đại diện cho client/service; chính sách phải phân biệt chủ thể người dùng với máy.

**Lưu ý về HTTP:** thiếu hoặc access token không hợp lệ thường dẫn tới **401 Unauthorized**, có `WWW-Authenticate: Bearer` theo RFC 6750 khi phù hợp; token hợp lệ nhưng thiếu scope hoặc quyền nghiệp vụ thường dẫn tới **403 Forbidden**. API có thể dùng **404 Not Found** để che giấu sự tồn tại của tài nguyên theo một chính sách nhất quán. Khi introspection gặp sự cố, có thể trả lỗi 5xx/503 hoặc từ chối theo chính sách; tuyệt đối không cho phép truy cập chỉ vì không xác minh được token.

### Phân biệt identity và authorization trong kết quả introspection

Giả sử một response có `active=true`, `sub=user-123`, `scope=orders:read`. Nó xác nhận một access token hoạt động theo issuer, nhưng **không khẳng định user-123 được đọc đơn hàng của user-456**. Resource Server vẫn phải kiểm tra owner, tenant, role, relationship và trạng thái nghiệp vụ từ nguồn đáng tin. Đặc biệt, nếu membership đã bị thu hồi mà token còn hoạt động, kết quả `active` tự nó không thay thế chính sách quyền hiện hành.

## 9. Khi nào nên cân nhắc opaque token?

Opaque access token dạng tham chiếu thường phù hợp khi:

- Cần **thu hồi có hiệu lực sớm** và có thể kiểm tra trạng thái mới ở điểm bảo vệ tài nguyên; mức độ tức thời vẫn phụ thuộc cache/invalidation.
- Cần **kiểm soát tập trung** quyền cấp token hoặc muốn giảm dữ liệu đưa vào chuỗi token trao cho client.
- Có hạ tầng introspection sẵn sàng, được bảo vệ, có khả năng mở rộng và chịu tải theo lưu lượng API.
- Muốn tránh để Resource Server phụ thuộc vào định dạng nội bộ của token; issuer có thể thay cách lưu/diễn giải token nếu giữ hợp đồng introspection.

JWT access token tự chứa có thể phù hợp hơn khi Resource Server cần xác minh độc lập ở nhiều vùng, chi phí gọi introspection lớn và yêu cầu thu hồi tức thời không phải điều kiện ưu tiên. Đây không phải lựa chọn loại trừ vĩnh viễn: một hệ thống có thể dùng opaque token ở luồng nhạy cảm và JWT ở luồng khác, miễn các API kiểm tra đúng audience, loại token và chính sách riêng.

### Những đánh đổi cần đo

| Yếu tố | Câu hỏi cần trả lời trước triển khai |
|---|---|
| **Độ trễ** | Một lần introspection tốn bao lâu? Đường gọi phụ thuộc mạng, timeout và retry thế nào? |
| **Tải** | Nếu 10.000 request/giây đều introspect, Authorization Server có chịu được không? Có cache an toàn được không? |
| **Khả dụng** | Khi introspection ngừng phục vụ, API sẽ từ chối, giảm chức năng hay dùng cache còn hiệu lực theo policy? |
| **Thu hồi** | Từ khi revoke đến khi tất cả API từ chối token tối đa bao lâu? Ai có thể kích hoạt invalidation? |
| **Privacy** | Metadata introspection chứa dữ liệu cá nhân gì? Có giới hạn theo Resource Server và tránh log không? |
| **Phân quyền** | Policy quyền tài nguyên có thể thay đổi nhanh hơn trạng thái token không? Ai là nguồn sự thật? |
| **Ranh giới trust** | API biết introspection của issuer nào được phép dùng, kiểm tra audience/loại token thế nào? |

**Lợi ích “centralized revocation” chỉ thành hiện thực nếu các API thực sự dùng trạng thái đủ mới.** Một opaque token cache `active=true` lâu có thể vẫn được chấp nhận sau khi server đã revoke; ngược lại, JWT với denylist cập nhật nhanh vẫn có thể bị chặn trước khi hết hạn.

## 10. Các lỗi dễ mắc và cách kiểm thử

### Lỗi thiết kế phổ biến

1. **Tự giải mã hoặc suy luận metadata từ opaque token.** Chuỗi opaque không công bố cấu trúc; Resource Server phải dùng cơ chế xác minh đã ký kết với issuer.
2. **Tin HTTP 200 từ introspection mà bỏ qua `active`.** `{"active":false}` vẫn thường đi cùng HTTP 200.
3. **Thấy `active=true` là cho phép mọi API.** Phải ràng buộc audience, loại access token, scope và quyền trên tài nguyên.
4. **Dùng refresh token để gọi API.** Refresh token dành cho luồng đổi token tại Authorization Server, không làm credential Resource Server.
5. **Đặt token trong query string hoặc log.** Token bị lộ qua history, proxy, tracing hoặc hệ thống ghi log có thể bị phát lại.
6. **Cache kết quả Permit mà không tính audience/tenant.** Quyết định có thể bị áp dụng nhầm giữa hai API hoặc tài nguyên.
7. **Fail open khi introspection lỗi.** Không thể xác minh token thì không có bằng chứng cho phép.
8. **Coi revoke là tức thời ở mọi nơi.** Cache, replication và hệ thống phân tán có thể gây độ trễ.
9. **Dùng chuỗi dễ đoán.** ID tuần tự, timestamp hoặc random không đủ mạnh làm tăng rủi ro brute-force.
10. **Không bảo vệ endpoint introspection.** Caller không được ủy quyền có thể khai thác endpoint để kiểm tra hoặc thu thập thông tin token.

### Ma trận kiểm thử hành vi

| Tình huống | Kết quả cần có |
|---|---|
| Token hợp lệ, đúng audience, đủ scope, subject có quyền trên order | Trả tài nguyên được phép |
| Không có token hoặc token không tồn tại | Từ chối với phản hồi xác thực phù hợp |
| Introspection trả HTTP 200 với `active=false` | Không cho truy cập |
| Introspection trả `active=true` nhưng audience là API khác | Từ chối trước policy nghiệp vụ |
| Token hợp lệ nhưng thiếu `orders:read` | Từ chối do thiếu quyền |
| Token đủ scope nhưng user khác owner, không có membership | Từ chối truy cập tài nguyên |
| Token đã revoke nhưng cache vẫn có `active=true` | Kiểm tra khoảng trễ thực tế so với yêu cầu thu hồi |
| Endpoint introspection timeout hoặc trả phản hồi sai cấu trúc | Không fail open, theo dõi lỗi |
| Caller chưa xác thực cố gọi introspection | Không lộ metadata token |
| Một refresh token bị gửi vào endpoint Orders API | Bị từ chối vì sai loại token/ngữ cảnh |

Với Java hoặc framework bất kỳ, nên dùng thư viện OAuth 2.0 Resource Server **đã được duy trì** và khả năng introspection được hỗ trợ. Các bài kiểm thử nên xác minh **kết quả API thực tế và không có side effect** khi bị từ chối, thay vì chỉ kiểm tra một hàm so sánh chuỗi token.

## 11. Câu hỏi tự đánh giá

**1. Opaque token có phải loại access token duy nhất trong OAuth 2.0?** Không. OAuth 2.0 không bắt buộc mọi access token phải có định dạng JWT hay opaque tham chiếu. Định dạng và cơ chế xác minh phụ thuộc hợp đồng giữa Authorization Server và Resource Server.

**2. Tại sao không thể nhìn vào chuỗi opaque token để biết user và scope?** Vì không có giao kèo rằng chuỗi chứa claims có thể diễn giải tại Resource Server. Cần nguồn xác minh tin cậy.

**3. Vì sao HTTP 200 từ introspection chưa đủ để chấp nhận token?** Vì HTTP 200 có thể trả `active=false`. Ngay cả khi `active=true`, API vẫn phải kiểm tra audience, scope và policy tài nguyên.

**4. Opaque token có tự ngăn phát lại khi bị đánh cắp không?** Không. Nếu là bearer token, ai giữ token hợp lệ đều có thể dùng theo phạm vi được cấp. Muốn chống replay cần biện pháp bổ sung như sender-constraining và phát hiện/thu hồi phù hợp.

**5. Thu hồi opaque token có lập tức chặn mọi API không?** Chỉ khi các API thực sự kiểm tra trạng thái đã cập nhật hoặc nhận invalidation đủ nhanh; cache và mạng có thể tạo độ trễ.

**6. Tại sao vẫn phải kiểm tra quyền trên đơn hàng sau introspection?** Trạng thái token và scope không chứng minh quyền với từng đối tượng, tenant hoặc dữ liệu hiện hành của API.

**Ghi nhớ:** **Opaque token tách credential khỏi metadata mà Resource Server cần để quyết định tin và cho phép truy cập.** Authorization Server thường quản lý trạng thái và cung cấp introspection; Resource Server phải kiểm tra `active`, đúng issuer/audience/loại token, scope và quyền nghiệp vụ. Khả năng thu hồi tập trung là một lợi ích lớn, nhưng chỉ đáng tin khi đường introspection được bảo vệ, trạng thái đủ mới và mọi API đều từ chối token không thể xác minh.

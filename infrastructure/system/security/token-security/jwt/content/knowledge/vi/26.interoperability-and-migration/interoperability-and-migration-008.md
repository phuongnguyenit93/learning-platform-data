# Di trú giữa token tham chiếu và JWT theo yêu cầu thu hồi

## 1. Bài toán di trú

Một hệ thống OAuth 2.0 có thể cấp access token dưới dạng token tham chiếu (reference token, thường là opaque token) hoặc JSON Web Token (JWT). Khi cần chuyển đổi giữa hai mô hình, quyết định quan trọng nhất thường không nằm ở cách mã hóa chuỗi token mà ở yêu cầu thu hồi quyền truy cập.

Token tham chiếu thường là một giá trị ngẫu nhiên, không mang claims có thể đọc trực tiếp. Resource server gửi token đến Authorization Server (AS) qua Token Introspection để hỏi token còn hoạt động và được phép dùng cho resource đó hay không. AS có thể kiểm tra trạng thái hiện tại của token, grant, người dùng và chính sách.

JWT access token thường là một JWS tự chứa claims. Resource server có thể xác minh chữ ký, issuer, audience và thời hạn bằng thông tin khóa đã phân phối trước, sau đó đưa ra quyết định mà không cần gọi AS cho mỗi request. Cách này giảm round trip và phụ thuộc trực tuyến, nhưng việc chỉ xác minh chữ ký không cho resource server biết token vừa bị thu hồi sau thời điểm phát hành.

Vì vậy, di trú phải bắt đầu bằng câu hỏi: **Sau khi người dùng đăng xuất, quyền bị thu hồi, tài khoản bị khóa hoặc token bị đánh cắp, hệ thống phải ngừng chấp nhận access token trong bao lâu?**

Nếu yêu cầu là thu hồi gần như tức thời, JWT chỉ được xác minh cục bộ sẽ không đáp ứng yêu cầu đó. Nếu hệ thống chấp nhận một cửa sổ sử dụng còn lại có giới hạn, JWT thời hạn ngắn có thể phù hợp. Nếu cần cả hiệu năng và thu hồi nhanh, có thể kết hợp JWT với một lớp kiểm tra trạng thái hoặc dùng reference token cho các resource nhạy cảm.

## 2. Phân biệt định dạng token và mô hình kiểm tra trạng thái

Không nên đồng nhất “opaque” với “có thể thu hồi ngay” và “JWT” với “không thể thu hồi”. Đây là hai trục thiết kế khác nhau:

- **Định dạng token:** resource server nhìn thấy một chuỗi tham chiếu không tự mô tả hay một cấu trúc JWT có thể xác minh/đọc claims.
- **Mô hình kiểm tra trạng thái:** resource server hỏi AS, tra cứu trạng thái dùng chung, kiểm tra denylist, hoặc chỉ xác minh bằng dữ liệu cục bộ.

JWT vẫn có thể được gửi đến introspection endpoint. Ngược lại, một reference token vẫn có thể được cache ở resource server và do đó không nhất thiết phản ánh trạng thái thu hồi tức thời.

| Cách triển khai | Định dạng | Kiểm tra tại resource server | Thu hồi thực tế |
| --- | --- | --- | --- |
| Reference token với introspection mỗi request | Opaque/reference | Hỏi AS cho từng request | Gần thời gian thực sau khi trạng thái AS và các node được cập nhật |
| Reference token với introspection cache | Opaque/reference | Dùng kết quả cache trong TTL | Có cửa sổ stale tối đa theo cache và độ trễ lan truyền |
| JWT xác minh cục bộ | JWT/JWS | Kiểm tra chữ ký và claims | Không biết việc thu hồi sau phát hành; thường còn hiệu lực đến exp |
| JWT với denylist jti | JWT/JWS | Xác minh chữ ký và tra trạng thái jti | Phụ thuộc độ nhất quán, cache và độ sẵn sàng của denylist |
| JWT với introspection | JWT/JWS | Gửi JWT đến AS | Theo trạng thái AS và chính sách cache |
| JWT với kiểm tra phiên/grant trực tuyến | JWT/JWS | Xác minh JWT rồi kiểm tra trạng thái session/grant | Theo tốc độ cập nhật và truy vấn trạng thái |

OAuth 2.0 không bắt buộc access token phải có một định dạng cụ thể. RFC 9068 chuẩn hóa một profile JWT access token để các AS và resource server có thể trao đổi token theo một hợp đồng claims/validation chung. RFC 7662 chuẩn hóa cách resource server truy vấn trạng thái và metadata của token. Hai chuẩn giải quyết các phần khác nhau của kiến trúc.

## 3. Reference token hoạt động như thế nào?

Reference token thường là một chuỗi khó đoán, được tạo từ nguồn ngẫu nhiên mật mã. Giá trị này hoạt động như một handle trỏ đến bản ghi hoặc trạng thái mà AS quản lý.

Ví dụ luồng:

1. Client nhận access token từ AS.
2. Client gửi token đến resource server trong Authorization header.
3. Resource server xác thực chính nó với introspection endpoint và gửi token cần kiểm tra.
4. AS xác định token có tồn tại, còn hạn, chưa bị thu hồi, đúng resource và còn được cấp quyền hay không.
5. AS trả active=true cùng metadata được phép tiết lộ, hoặc active=false.
6. Resource server chỉ xử lý request khi trạng thái token và authorization policy đều đạt.

### Ví dụ request introspection

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic <resource-server-credentials>
Content-Type: application/x-www-form-urlencoded

token=<reference-access-token>&token_type_hint=access_token
~~~

token_type_hint chỉ là gợi ý giúp AS tìm loại token; nó không thay thế việc xác định và kiểm tra token thực tế.

### Ví dụ response cho token đang hoạt động

~~~json
{
  "active": true,
  "iss": "https://identity.example.test/",
  "sub": "user-42",
  "client_id": "orders-web",
  "aud": ["https://api.example.test/orders"],
  "scope": "orders.read",
  "iat": 1893452400,
  "exp": 1893452700
}
~~~

Ví dụ response cho token không hoạt động:

~~~json
{
  "active": false
}
~~~

RFC 7662 định nghĩa active là boolean bắt buộc. Ý nghĩa cụ thể của trạng thái active do AS quyết định; thông thường token phải được AS phát hành, chưa hết hạn, chưa bị thu hồi và hợp lệ với resource server đang introspect. Với token inactive, AS nên tránh tiết lộ lý do hoặc metadata khác để không làm lộ trạng thái nội bộ.

### Lợi thế về thu hồi

Khi AS đánh dấu token bị thu hồi, một lần introspection mới có thể trả active=false. Resource server không phải đợi chữ ký hết hạn mới biết token không còn được chấp nhận.

Điều này đặc biệt hữu ích khi người dùng đăng xuất hoặc thu hồi consent, quản trị viên khóa tài khoản hoặc thu hồi phiên, refresh token hoặc authorization grant bị thu hồi, token bị lộ và cần vô hiệu hóa nhanh, hoặc quyền và trạng thái nghiệp vụ thay đổi thường xuyên.

### Chi phí vận hành

Mỗi request có thể phát sinh thêm một lần gọi mạng đến AS. Điều đó làm tăng latency, tải introspection endpoint và phụ thuộc vào tính sẵn sàng của AS. Nếu AS gặp sự cố, resource server phải có chính sách rõ ràng cho request không thể xác định trạng thái token.

Reference token cũng vẫn là bearer credential. Kẻ đánh cắp chuỗi token có thể sử dụng nó trong phạm vi được cấp nếu không có sender constraint. Tính opaque không tự làm token chống replay hoặc chống đánh cắp.

## 4. JWT access token hoạt động như thế nào?

JWT access token theo RFC 9068 là token có chữ ký. Resource server xác minh chữ ký bằng khóa của AS, sau đó kiểm tra các claims và token profile. Profile yêu cầu header typ là at+jwt hoặc application/at+jwt, issuer, audience, expiration và các quy tắc xác minh tương ứng.

Ví dụ header:

~~~json
{
  "alg": "RS256",
  "kid": "access-signing-2026-01",
  "typ": "at+jwt"
}
~~~

Ví dụ claims:

~~~json
{
  "iss": "https://identity.example.test/",
  "sub": "user-42",
  "aud": "https://api.example.test/orders",
  "client_id": "orders-web",
  "scope": "orders.read",
  "iat": 1893452400,
  "exp": 1893452700,
  "jti": "at-8e7b2f4d"
}
~~~

Resource server có thể xác minh token cục bộ:

1. Kiểm tra cấu trúc và protected header.
2. Chỉ chấp nhận thuật toán nằm trong allowlist.
3. Lấy public key từ JWKS hoặc metadata của issuer tin cậy.
4. Xác minh chữ ký.
5. Kiểm tra typ, iss, aud, exp và các claims theo profile.
6. Kiểm tra scope và authorization policy cho tài nguyên cụ thể.

Không được chỉ decode payload rồi tin claims. JWT có chữ ký không đồng nghĩa payload được mã hóa; JWS payload có thể đọc được bởi bất kỳ bên nào sở hữu token.

### Lợi thế về hiệu năng và phân tán

Khi khóa công khai đã được cache và token hợp lệ, resource server có thể xác minh mà không gọi AS cho mỗi request. Điều này phù hợp với hệ thống có lưu lượng lớn, nhiều vùng triển khai hoặc yêu cầu giảm phụ thuộc vào dịch vụ trung tâm.

### Giới hạn thu hồi của xác minh cục bộ

Chữ ký chỉ chứng minh token được ký bằng khóa tương ứng và nội dung không bị thay đổi. Nó không chứng minh token chưa bị thu hồi sau khi phát hành.

Nếu token có exp sau 10 phút nữa và AS thu hồi token ngay lúc này, resource server chỉ xác minh chữ ký, issuer, audience và thời gian vẫn có thể chấp nhận token trong phần thời gian còn lại. Việc thu hồi refresh token ngăn cấp access token mới theo grant đó, nhưng không tự động làm mọi JWT access token đã phát hành biến thành invalid tại các resource server xác minh offline.

Vì vậy, thời hạn ngắn chỉ **giới hạn cửa sổ rủi ro**; nó không phải cơ chế thu hồi tức thời.

## 5. RFC 7009 và RFC 7662 giải quyết hai vai trò khác nhau

Hai giao thức thường bị nhầm lẫn:

| Chuẩn | Ai gọi? | Mục đích |
| --- | --- | --- |
| RFC 7009 — Token Revocation | OAuth client gọi AS | Thông báo token không còn cần dùng và yêu cầu AS vô hiệu hóa token |
| RFC 7662 — Token Introspection | Resource server gọi AS | Hỏi trạng thái active và metadata của token trước khi xử lý request |

Revocation endpoint không phải một broadcast tự động đến mọi resource server. Nó cập nhật trạng thái tại AS và các hệ thống liên quan theo chính sách triển khai. Introspection là một cách để resource server biết trạng thái đó.

RFC 7009 quy định AS phản hồi thành công cho yêu cầu thu hồi hợp lệ; client không được suy luận từ response rằng token trước đó chắc chắn tồn tại hay đang active. Việc vô hiệu hóa được thực hiện tại AS, nhưng RFC cũng thừa nhận có thể có độ trễ lan truyền giữa các server.

Theo chính sách của AS:

- Thu hồi refresh token có thể kéo theo thu hồi access token được cấp từ cùng grant; RFC 7009 nêu đây là hành vi SHOULD khi AS hỗ trợ thu hồi access token.
- Thu hồi access token có thể kéo theo thu hồi refresh token liên quan; đây là hành vi MAY.
- Hệ thống cần định nghĩa rõ thu hồi token đơn lẻ, cả grant, session hoặc toàn bộ phiên đăng nhập.

Không nên dùng từ “immediate” như cam kết không có độ trễ nếu trạng thái được sao chép qua nhiều node, cache hoặc region.

## 6. Định nghĩa yêu cầu thu hồi trước khi chọn định dạng

Trước khi di trú, hãy xác định một Service Level Objective (SLO) cho thời gian từ lúc sự kiện thu hồi được xác nhận đến lúc mọi resource server ngừng chấp nhận token liên quan.

| Mức yêu cầu | Mục tiêu minh họa | Mô hình có thể phù hợp |
| --- | --- | --- |
| Rất chặt | Ngừng chấp nhận trong vài giây hoặc theo thời gian propagation đã đo | Introspection không cache hoặc cache cực ngắn; JWT kèm kiểm tra trạng thái trực tuyến nhất quán |
| Có giới hạn | Cửa sổ rủi ro được giới hạn theo một TTL ngắn đã phê duyệt | JWT thời hạn ngắn, kèm thu hồi refresh/grant và cơ chế bổ sung nếu cần |
| Theo vòng đời token | Token cũ có thể tồn tại đến exp | JWT xác minh cục bộ, thời hạn phù hợp, quyền hẹp và sender constraint khi cần |
| Theo từng thao tác nhạy cảm | Hầu hết request xử lý cục bộ, thao tác quan trọng kiểm tra trạng thái mới | JWT cục bộ cộng introspection/authorization online cho thao tác rủi ro cao |

Các mốc thời gian trong bảng chỉ minh họa cách phân loại. Hệ thống phải chọn SLO theo thiệt hại có thể xảy ra, khả năng vận hành và độ trễ thực tế, không lấy một con số chung cho mọi ngành.

### Các sự kiện cần được định nghĩa riêng

- Người dùng nhấn logout ở một thiết bị.
- Quản trị viên thu hồi một phiên đăng nhập cụ thể.
- Người dùng thu hồi consent của client.
- Tài khoản bị khóa hoặc vô hiệu hóa.
- Mật khẩu hoặc yếu tố xác thực bị thay đổi sau sự cố.
- Refresh token bị phát hiện replay.
- Access token bị lộ hoặc nghi ngờ bị đánh cắp.
- Quyền trên một resource hoặc tenant bị thay đổi.

Một logout ở thiết bị A có thể chỉ thu hồi session A hoặc toàn bộ phiên của người dùng. Đây là chính sách nghiệp vụ cần xác định; không thể suy ra chỉ từ việc token là JWT hay opaque.

## 7. So sánh hai mô hình theo yêu cầu thu hồi

| Tiêu chí | Reference token + introspection | JWT xác minh cục bộ |
| --- | --- | --- |
| Kiểm tra token | Tra cứu trạng thái tại AS | Xác minh chữ ký và claims |
| Nhận biết token bị thu hồi | Sau khi trạng thái AS cập nhật và cache hết hạn/được invalidated | Không nhận biết nếu không có kiểm tra trạng thái bổ sung |
| Latency mỗi request | Có round trip nếu không cache | Thấp hơn khi key đã cache |
| Phụ thuộc AS trực tuyến | Cao hơn | Thấp hơn cho bước xác minh mật mã |
| Khả năng hoạt động khi AS gián đoạn | Phụ thuộc cache và fail policy | Có thể tiếp tục xác minh đến khi token hết hạn nếu keys/policy còn hợp lệ |
| Thay đổi quyền hiện tại | Có thể phản ánh qua introspection mới | Claims trong token là snapshot cho đến khi hết hạn |
| Dữ liệu token | Không cần nhúng claims đọc được vào token | Claims trong JWS có thể đọc được |
| Cache | Giảm tải nhưng tạo stale window | Cache JWKS và trạng thái revocation nếu có |
| Mở rộng nhiều resource server | Cần scale AS/introspection hoặc cache | Dễ phân phối public keys, nhưng trạng thái thu hồi phân tán khó hơn |
| Vận hành | Quản lý state, introspection capacity và cache | Quản lý signing keys, TTL, denylist hoặc cơ chế thu hồi bổ sung |

Không có lựa chọn tốt nhất cho mọi hệ thống. Một kiến trúc có thể dùng reference token cho API thanh toán, dữ liệu sức khỏe hoặc thao tác quản trị, đồng thời dùng JWT cho các API đọc ít nhạy cảm cần throughput cao.

## 8. Cache introspection và cửa sổ stale

Cache introspection là đánh đổi giữa hiệu năng và độ mới của trạng thái token.

- TTL ngắn: resource server hỏi AS thường xuyên hơn, trạng thái thu hồi được phản ánh sớm hơn, nhưng tải và latency tăng.
- TTL dài: giảm số lần gọi AS, nhưng resource server có thể tiếp tục chấp nhận token đã bị thu hồi trong thời gian cache còn hiệu lực.
- Không cache: giảm rủi ro stale do cache, nhưng mọi request phụ thuộc vào AS và mạng.

RFC 7662 yêu cầu hệ thống cân nhắc đánh đổi này. Nếu introspection response có exp, response không được cache quá thời điểm exp.

### Xác định giới hạn thu hồi từ cache

~~~text
revocation_visibility_window =
    AS_state_propagation_delay
  + maximum_positive_introspection_cache_ttl
  + resource_server_invalidation_delay
~~~

Đây là ngân sách thời gian cần đo và giới hạn. Không cộng TTL một cách máy móc nếu hệ thống có push invalidation hoặc cache phân tầng; phải đo đường đi thực tế từ thao tác thu hồi đến từng node.

### Quy tắc cache an toàn

1. Không cache response active lâu hơn exp.
2. Không cache kết quả active dài hơn SLO thu hồi đã phê duyệt.
3. Có cơ chế xóa cache theo token, grant hoặc session khi nhận sự kiện thu hồi.
4. Xác định cách xử lý khi event bị mất hoặc node bị tách khỏi mạng.
5. Không dùng cache inactive để suy luận token khác inactive.
6. Tách cache theo issuer và resource server; không chia sẻ kết quả introspection sai audience.
7. Không ghi raw token làm cache key trong log. Có thể dùng digest có kiểm soát cho khóa cache nội bộ.

Nếu AS không truy cập được, không được mặc định coi token là active. Với API nhạy cảm, chính sách thường là fail closed. Nếu cho phép dùng kết quả active đã cache, phải giới hạn theo TTL và SLO đã phê duyệt.

## 9. Các cách bổ sung thu hồi cho JWT

JWT xác minh cục bộ không cung cấp trạng thái thu hồi. Muốn thu hồi trước exp, hệ thống phải bổ sung một nguồn trạng thái hoặc chấp nhận cửa sổ rủi ro cho đến khi token hết hạn.

### 9.1. Access token thời hạn ngắn

Đặt exp gần thời điểm phát hành để giới hạn thời gian token có thể được sử dụng nếu bị lộ hoặc grant bị thu hồi.

Ưu điểm:

- Không cần lưu từng access token trong denylist.
- Resource server có thể xác minh cục bộ.
- Giảm thời gian tồn tại của claims cũ.

Giới hạn:

- Token vẫn còn hiệu lực cho đến khi hết hạn.
- Client phải lấy token mới thường xuyên hơn.
- AS phải xử lý tải phát hành/refresh tương ứng.
- Clock skew và cache key/policy vẫn phải được tính vào SLO.

Không nhầm thời hạn ngắn với thu hồi tức thời.

### 9.2. Denylist theo jti

JWT có thể chứa jti duy nhất. Khi thu hồi token, AS phát sự kiện hoặc ghi một bản ghi denylist cho cặp issuer và jti.

Ví dụ khóa logic:

~~~text
revoked-token:
  issuer: https://identity.example.test/
  jti: at-8e7b2f4d
  revoked_at: 1893452500
  expires_at: 1893452700
~~~

Resource server xác minh chữ ký trước, sau đó kiểm tra token có nằm trong denylist hay không. Bản ghi có thể được xóa sau exp cộng clock skew và thời gian dọn dẹp an toàn.

Ưu điểm:

- Có thể thu hồi từng JWT trước exp.
- Có thể triển khai cho token bị đánh cắp hoặc bị thu hồi khẩn cấp.

Giới hạn:

- Phải lưu và tra cứu trạng thái trên mỗi request hoặc dùng cache có TTL.
- Cần đồng bộ denylist giữa nhiều node/region.
- Nếu event thu hồi bị mất hoặc đến chậm, token có thể được chấp nhận ở node chưa cập nhật.
- Denylist lớn theo số lượng token phát hành và thời hạn token.

Không dùng riêng jti làm khóa toàn cục nếu nhiều issuer cùng tồn tại; cần gắn issuer hoặc namespace tin cậy để tránh va chạm.

### 9.3. Thu hồi theo session hoặc grant

Nếu nhiều access token được cấp từ cùng một phiên, có thể đưa định danh session/grant vào token, ví dụ claim riêng sid hoặc grant_id. Resource server kiểm tra trạng thái session/grant hiện tại.

Khi thu hồi một session, AS đánh dấu session inactive; các JWT mang định danh đó bị từ chối sau khi resource server nhận trạng thái mới.

Ưu điểm:

- Một thao tác có thể vô hiệu hóa nhiều token liên quan.
- Hữu ích cho logout toàn bộ phiên hoặc sự kiện bảo mật tài khoản.

Giới hạn:

- Cần tra cứu trạng thái session/grant hoặc nhận event đồng bộ.
- sid/grant_id là claim ứng dụng; phải định nghĩa issuer, audience, phạm vi và vòng đời.
- Không nên coi một claim session chưa xác minh là bằng chứng trạng thái hiện tại.

### 9.4. Token version hoặc authorization epoch

AS có thể quản lý một phiên bản trạng thái cho chủ thể hoặc grant. JWT mang version tại thời điểm phát hành; resource server so sánh với version hiện tại.

Ví dụ:

~~~json
{
  "sub": "user-42",
  "authz_ver": 17,
  "exp": 1893452700
}
~~~

Khi thu hồi tất cả token của chủ thể hoặc thay đổi trạng thái bảo mật, AS tăng version. Resource server từ chối JWT có version cũ.

Đây là cơ chế tùy biến, không phải claim chuẩn bắt buộc của JWT. Nó vẫn cần truy vấn trạng thái hoặc một cơ chế phân phối version đáng tin cậy; nếu cache version lâu, cửa sổ thu hồi lại xuất hiện.

### 9.5. Introspection cho JWT ở thao tác nhạy cảm

Hệ thống có thể xác minh JWT cục bộ cho request thông thường, nhưng gọi introspection hoặc kiểm tra grant/session trực tuyến trước hành động có rủi ro cao như chuyển tiền, thay đổi quyền hoặc xuất dữ liệu lớn.

Cách này giảm chi phí kiểm tra trực tuyến cho mọi request mà vẫn có điểm kiểm soát trạng thái gần thời gian thực ở thao tác quan trọng.

### 9.6. Sự kiện thu hồi và invalidation phân tán

AS có thể phát sự kiện thu hồi đến gateway, cache và resource server. Mỗi node cập nhật trạng thái cục bộ hoặc xóa cache tương ứng.

Để dùng cơ chế này an toàn, cần xác thực nguồn phát sự kiện và bảo vệ kênh truyền, có event ID và phiên bản trạng thái để xử lý lặp/đến sai thứ tự, retry và durable delivery, dead-letter handling, đối soát định kỳ với AS, đo propagation ở từng vùng, và fail closed khi không thể chứng minh trạng thái đã đồng bộ trong giới hạn cho phép.

Push event không tự động tạo ra tính nhất quán tức thời. Đó là một hệ thống phân tán cần kiểm thử mất kết nối, trễ, duplicate và replay event.

## 10. Chọn mô hình theo mức nhạy cảm của resource

Một hệ thống không nhất thiết phải dùng cùng định dạng access token cho tất cả API.

| Resource hoặc hành động | Mô hình có thể cân nhắc | Lý do |
| --- | --- | --- |
| API đọc danh mục ít nhạy cảm | JWT TTL ngắn, xác minh cục bộ | Throughput cao, cửa sổ rủi ro được giới hạn |
| API hồ sơ cá nhân | JWT với audience hẹp và claim tối thiểu; kiểm tra trạng thái cho thao tác nhạy cảm | Cân bằng hiệu năng và quyền riêng tư |
| API thanh toán hoặc chuyển tiền | Reference token introspection hoặc JWT kèm kiểm tra grant trực tuyến | Thu hồi nhanh và trạng thái quyền hiện tại quan trọng |
| API quản trị | Reference token với cache rất ngắn/không cache hoặc JWT + trạng thái phiên trực tuyến | Quyền cao, hậu quả khi token bị lạm dụng lớn |
| API nội bộ lưu lượng lớn | JWT ngắn hạn, audience cụ thể, sender constraint nếu phù hợp | Giảm phụ thuộc AS, giới hạn replay và phạm vi |
| Tác vụ chạy nền dài hạn | Token riêng cho workload, audience/scope hẹp, refresh/rotation và cơ chế thu hồi grant | Vòng đời dài cần quản lý riêng |

Đây là mẫu thiết kế để đánh giá, không phải quy tắc cứng. Mỗi resource phải có threat model và SLO thu hồi riêng.

## 11. Di trú từ reference token sang JWT

Mục tiêu của chiều di trú này thường là giảm tải introspection, giảm latency hoặc cho phép resource server xác minh độc lập. Trước khi chuyển, phải quyết định cách đáp ứng yêu cầu thu hồi của token mới.

### Giai đoạn 1: kiểm kê

Lập danh sách client đang nhận reference token, resource server đang gọi introspection, issuer/audience/scope/grant, TTL access token và refresh token, sự kiện thu hồi, thời gian propagation, và các API có yêu cầu thu hồi nghiêm ngặt.

Không chỉ đo số lần gọi introspection; cần đo latency, error rate, cache hit ratio và thời gian từ revoke đến khi request bị từ chối.

### Giai đoạn 2: chốt token profile JWT

Thống nhất:

- Profile JWT access token, ưu tiên RFC 9068 nếu phù hợp.
- typ: at+jwt hoặc application/at+jwt.
- iss, sub, aud, exp, iat, jti và các claims cần thiết.
- Thuật toán ký allowlist và cách phân phối public key qua JWKS.
- Quy tắc scope, audience, token type và key rollover.
- Claim riêng cho session/grant/version nếu cần thu hồi theo nhóm.

Không nhúng dữ liệu hồ sơ hoặc quyền không cần thiết. Không dùng ID Token thay cho access token. Resource server phải xác minh chữ ký, issuer, audience, thời hạn và profile trước khi tin claims.

### Giai đoạn 3: chọn cơ chế thu hồi

Chọn một hoặc kết hợp: chấp nhận cửa sổ tối đa đến exp với JWT TTL ngắn; denylist theo iss + jti; kiểm tra session/grant version; introspection cho thao tác nhạy cảm; hoặc sự kiện thu hồi có invalidation và đối soát.

Ghi rõ SLO, độ trễ propagation, hành vi khi trạng thái không truy cập được và bên chịu trách nhiệm vận hành.

### Giai đoạn 4: triển khai verifier trước

Resource server phải có khả năng xác minh JWT mới trước khi AS bắt đầu phát hành. Triển khai public keys, allowlist, token profile, audience và test vectors ở tất cả node.

Kiểm thử cả token hợp lệ lẫn token sai issuer, sai audience, sai typ, chữ ký sai, hết hạn, key chưa được công bố và thuật toán ngoài allowlist.

### Giai đoạn 5: phát hành song song có kiểm soát

Trong giai đoạn tương thích, AS có thể cấp reference token cho client/resource cũ và JWT cho client/resource đã sẵn sàng. Việc chọn định dạng cần được quyết định bởi cấu hình client, resource hoặc profile đã đăng ký.

Không để resource server thử decode một token bất kỳ; nếu decode thất bại thì tự động chuyển sang introspection mà không có quy tắc định tuyến rõ ràng. Cách fallback mơ hồ có thể tạo downgrade path và làm khó điều tra.

Mỗi token phải được xử lý theo đúng validator đã cấu hình. Token không xác định được profile phải bị từ chối.

### Giai đoạn 6: theo dõi và chuyển traffic

Theo dõi tỷ lệ reference token/JWT theo client/resource, JWT validation failure theo iss/aud/typ/kid/alg, số lần gọi introspection còn lại, token bị từ chối do denylist/session revocation, thời gian propagation thu hồi và lỗi client do token hết hạn hoặc refresh không thành công.

Chỉ chuyển thêm client/resource khi SLO thu hồi và validation đều đạt.

### Giai đoạn 7: ngừng reference token cũ

Ngừng phát hành reference token mới cho phạm vi đã di trú. Giữ introspection và trạng thái cũ cho đến khi token reference cuối cùng hết hạn hoặc bị thu hồi, sau đó xóa dữ liệu và secret theo retention policy.

Không xóa bản ghi token cũ chỉ vì AS đã ngừng phát hành. Resource server vẫn có thể nhận token cũ đang còn hiệu lực trong cửa sổ tương thích.

## 12. Di trú từ JWT sang reference token

Chiều di trú này thường được chọn khi cần thu hồi nhanh, cập nhật quyền tức thời hơn, giảm claims bị lộ hoặc đưa trạng thái token về một điểm quản lý tập trung.

### Giai đoạn 1: xây dựng introspection capacity

Trước khi đổi issuer, triển khai introspection endpoint được bảo vệ; xác thực resource server gọi endpoint; dùng TLS và kiểm tra chứng thư máy chủ; chỉ trả metadata mà resource server cần; có rate limit, timeout, circuit breaker và quan sát lỗi; định nghĩa TTL cache theo SLO thu hồi; xác định fail policy khi AS hoặc mạng không sẵn sàng.

Introspection endpoint là endpoint nhạy cảm vì nó nhận token và trả thông tin dùng cho quyết định authorization. Không công khai endpoint cho client cuối hoặc cho bên không được phép introspect token.

### Giai đoạn 2: ánh xạ claims và policy

Xác định các claims JWT hiện tại đang được resource server sử dụng: subject/client, issuer/audience, scope/role/entitlement, tenant/session/grant, thời gian phát hành/hết hạn, sender constraint hoặc confirmation data.

Chuyển chúng thành metadata introspection có schema rõ ràng. Không giả định mọi claim tùy chỉnh trong JWT đều có thể chuyển nguyên xi thành một trường response mà không thay đổi policy.

### Giai đoạn 3: triển khai resource server dùng introspection

Resource server cần gửi reference token đến đúng introspection endpoint của issuer, xác thực resource server với AS, yêu cầu đúng token type nếu profile hỗ trợ, từ chối nếu active không phải boolean true, kiểm tra audience/scope/client/subject và metadata cần thiết, và chỉ cho phép request sau khi cả trạng thái token và authorization policy đều đạt.

Không chỉ kiểm tra active=true rồi bỏ qua audience hoặc quyền. Active là trạng thái token theo AS; resource server vẫn phải xác nhận token được phép truy cập resource và hành động cụ thể.

### Giai đoạn 4: dual validation

Trong thời gian chuyển đổi, resource server có thể phải xử lý JWT cũ và reference token mới. Hai loại token phải được phân tuyến bằng cấu hình hoặc dấu hiệu định dạng đã quy định, không dựa vào fallback tùy tiện.

Với JWT cũ, nếu cần thu hồi trước exp, phải giữ một cơ chế trạng thái như denylist, introspection hoặc session check trong suốt cửa sổ tương thích. Chỉ đổi issuer sang reference token không làm JWT đã phát hành bị vô hiệu hóa.

### Giai đoạn 5: hoàn tất và dọn dẹp

Sau khi JWT cũ hết hạn hoặc đã được thu hồi theo policy, ngừng chấp nhận JWT thuộc profile cũ, gỡ public keys và cache không còn dùng theo lịch rollover, xóa denylist/session state tạm thời sau khi không còn token cần tra cứu, đảm bảo mọi resource server chỉ chấp nhận token profile đã đăng ký, và cập nhật runbook, dashboard cùng kiểm thử hồi quy.

## 13. Dùng OAuth Token Exchange khi cần đổi loại token

RFC 8693 định nghĩa OAuth 2.0 Token Exchange để một client hoặc resource server gửi subject_token đến AS và yêu cầu một security token mới cho resource hoặc ngữ cảnh khác. Kết quả có thể là JWT hoặc loại token khác theo policy.

Ví dụ luồng:

1. Client gửi reference token đến API gateway.
2. Gateway xác thực token đầu vào theo cơ chế được cấu hình.
3. Gateway gọi token exchange để nhận JWT audience hẹp cho backend.
4. Backend xác minh JWT được phát hành cho đúng audience và scope.

Token exchange hữu ích để chuyển đổi dần giữa hệ thống cũ và mới hoặc thu hẹp quyền cho dịch vụ downstream.

### Điểm quan trọng về thu hồi

RFC 8693 không tự tạo liên kết thu hồi chặt giữa token đầu vào và token đầu ra. Trong trường hợp thông thường, việc exchange không làm thay đổi tính hợp lệ của subject_token; token đầu ra là một credential mới. RFC nêu việc lan truyền sự kiện thu hồi có thể phù hợp, nhưng không phải đặc tính chung được giao thức bảo đảm.

Do đó, nếu reference token đầu vào bị thu hồi sau khi gateway đã đổi thành JWT, backend có thể tiếp tục chấp nhận JWT đầu ra đến khi hết hạn nếu nó chỉ xác minh cục bộ.

Muốn bảo toàn yêu cầu thu hồi, deployment phải định nghĩa một trong các cách:

- JWT đầu ra có TTL không vượt quá thời hạn còn lại của token đầu vào và chấp nhận cửa sổ còn lại đó.
- Lưu quan hệ parent-child hoặc grant lineage; khi token đầu vào bị thu hồi, thu hồi các token đầu ra liên quan.
- Gắn session/grant ID vào token đầu ra và kiểm tra trạng thái hiện tại.
- Backend introspect token đầu ra hoặc kiểm tra trạng thái trực tuyến cho thao tác nhạy cảm.
- Dùng reference token đầu ra thay vì JWT nếu cần kiểm soát tập trung.

Không được giả định chỉ vì AS đã xác thực token đầu vào tại thời điểm exchange nên token đầu ra tự động bị vô hiệu hóa khi token đầu vào bị thu hồi.

### Giới hạn quyền trong token exchange

Khi đổi token, xác thực token đầu vào và client thực hiện exchange; giới hạn audience/resource ở đúng backend đích; không mở rộng scope so với quyền mà policy cho phép; ghi nhận subject và actor/delegation nếu ngữ cảnh yêu cầu; đặt thời hạn token đầu ra phù hợp với token đầu vào và policy; quy định cách thu hồi token đầu ra khi grant hoặc token đầu vào bị thu hồi.

## 14. Refresh token và access token phải có vòng đời riêng

Refresh token dùng để lấy access token mới. Việc thu hồi refresh token chủ yếu ngăn việc tiếp tục phát hành token mới theo grant; nó không tự động làm resource server biết một JWT access token đã phát hành bị thu hồi.

RFC 9700 yêu cầu refresh token cho public clients phải được sender-constrain hoặc dùng refresh token rotation để phát hiện replay. Khi rotation phát hiện một refresh token cũ bị dùng lại, AS có thể thu hồi refresh token còn hoạt động của grant liên quan.

Trong thiết kế di trú:

- Access token cần TTL và cơ chế thu hồi phù hợp với resource.
- Refresh token cần bảo vệ, ràng buộc client và rotation hoặc sender constraint theo yêu cầu.
- Revocation của refresh token cần xác định có thu hồi các access token cùng grant hay không.
- Logout cần xác định phạm vi session/grant/device.
- Không lưu refresh token trong access token hoặc claims của JWT.
- Không để client tiếp tục dùng token sau khi đã nhận kết quả thu hồi thành công.

## 15. Sender constraint giảm replay nhưng không thay thế thu hồi

Sender-constrained access token gắn token với một client hoặc khóa cụ thể. RFC 9700 khuyến nghị cân nhắc mTLS (RFC 8705) hoặc DPoP (RFC 9449) để giảm khả năng kẻ đánh cắp token sử dụng token từ một sender khác.

Sender constraint có ích cho cả reference token và JWT. Tuy nhiên, nó không thay thế việc thu hồi:

- Nếu thiết bị hoặc private key của client bị xâm phạm, attacker có thể vẫn tạo proof hợp lệ.
- Khi người dùng logout hoặc grant bị thu hồi, token vẫn cần bị đánh dấu inactive hoặc hết hạn.
- Khi khóa client bị thu hồi, resource server phải biết và cập nhật trạng thái binding.

Vì vậy, sender constraint là một lớp giảm replay; introspection, denylist, session state và expiration vẫn giải quyết bài toán vòng đời/thu hồi.

## 16. Bảo mật introspection và dữ liệu trạng thái

Introspection endpoint phải được bảo vệ tương đương các endpoint nhạy cảm khác:

- Chỉ resource server được phép mới có thể introspect token tương ứng.
- Dùng TLS và xác thực client/resource server.
- Ưu tiên POST để tránh token xuất hiện trong URL, proxy log hoặc browser history.
- Không ghi raw token trong request log, tracing hoặc exception.
- Response inactive chỉ nên tiết lộ active=false nếu không cần thông tin khác.
- Giới hạn các claims trả về theo resource để tránh resource server biết quá nhiều về hệ thống.
- Chống token scanning bằng xác thực và rate limiting.
- Không để client cuối sử dụng introspection endpoint như một cách kiểm tra token tùy ý.

### Bảo vệ kho trạng thái reference token

AS có thể lưu token dưới dạng hash/digest thay vì lưu raw token. Vì reference token cần không thể đoán, giá trị phải có entropy cao và được sinh bằng nguồn ngẫu nhiên mật mã.

Một bản ghi trạng thái có thể chứa:

~~~text
token_digest
client_id
subject_id
grant_id
resource_audience
scope_set
issued_at
expires_at
revoked_at
status
~~~

Không cần lưu claims hoặc dữ liệu cá nhân nhiều hơn mức phục vụ introspection và audit. Hạn chế quyền truy cập vào kho trạng thái và có retention policy cho token đã hết hạn.

## 17. Thiết kế trạng thái khi hệ thống không liên lạc được AS

Đây là một quyết định bảo mật quan trọng khi chuyển từ xác minh JWT offline sang introspection online.

| Tình huống | Hành vi cần quyết định |
| --- | --- |
| Introspection trả active=false | Từ chối token |
| Introspection timeout | Không coi timeout là active=true; áp dụng fail policy |
| AS trả lỗi 5xx | Fail closed cho resource nhạy cảm; có thể dùng cache active còn hạn nếu policy đã phê duyệt |
| Cache active đã hết TTL | Gọi lại AS; không kéo dài TTL âm thầm |
| Event revoke đến chậm | Đo propagation; giữ SLO và có đối soát |
| JWKS endpoint tạm thời lỗi | Có thể dùng public key đã cache còn hiệu lực theo policy, nhưng không bỏ qua validation |
| Denylist không truy cập được | Không mặc định token không bị thu hồi; áp dụng fail policy đã đánh giá |

Không có một chính sách fail-open/fail-closed phù hợp cho mọi hệ thống. Với thanh toán, quản trị hoặc dữ liệu nhạy cảm, tiếp tục cho phép request khi không xác định được trạng thái thu hồi thường tạo rủi ro lớn. Nếu chấp nhận cache để duy trì availability, cần ghi rõ mức stale tối đa và chứng minh nó vẫn nằm trong SLO.

## 18. Kiểm thử di trú và thu hồi

Kiểm thử phải xác nhận hành vi ở nhiều resource server, nhiều node và nhiều vùng, không chỉ kiểm tra một request đơn lẻ.

| Trường hợp | Reference token | JWT local | Kỳ vọng |
| --- | --- | --- | --- |
| Token hợp lệ, đúng audience và scope | Introspection active | Signature/claims hợp lệ | Chấp nhận |
| Token hết hạn | active=false | exp đã qua | Từ chối |
| Token vừa bị revoke | Introspection inactive sau propagation | Chữ ký vẫn đúng nếu không có state check | Xác nhận đúng cửa sổ thu hồi đã định |
| Refresh token bị revoke | AS ngừng cấp mới; access token xử lý theo policy | JWT đã cấp vẫn cần TTL/state check | Không giả định access JWT tự biến mất |
| User logout một session | Trạng thái session/grant inactive | Kiểm tra session/denylist hoặc chờ TTL theo policy | Chỉ thu hồi đúng phạm vi |
| Admin revoke toàn bộ grant | Token cùng grant inactive theo policy | Denylist/epoch/session event áp dụng | Không còn token thuộc grant được chấp nhận sau SLO |
| Introspection cache còn active khi revoke | Có thể stale đến hết TTL nếu không invalidate | Không áp dụng | Đo đúng stale window |
| Introspection endpoint timeout | Fail policy được áp dụng | Không liên quan nếu JWT local | Không tự coi timeout là active |
| JWT nằm trong denylist | Không áp dụng | Từ chối trước authorization | Từ chối |
| Denylist bị mất đồng bộ giữa region | Không áp dụng | Có thể region chấp nhận token | Kiểm thử propagation và fail policy |
| JWT sai iss, aud, typ hoặc chữ ký | Không áp dụng | Từ chối | Không có fallback |
| Reference token không biết | active=false | Không áp dụng | Từ chối |
| Token đầu vào đã revoke rồi thực hiện token exchange | AS từ chối exchange nếu kiểm tra trạng thái hiện tại | Không áp dụng | Không phát hành token đầu ra |
| Token đầu vào bị revoke sau khi exchange | Theo lineage policy | JWT đầu ra có thể còn hiệu lực nếu không liên kết | Thu hồi token con theo SLO đã thiết kế |
| Event revoke bị gửi lặp | Trạng thái vẫn inactive | Denylist/session update idempotent | Không phục hồi trạng thái active |
| Event revoke bị mất | Đối soát AS/cache | Đối soát denylist/session state | Hệ thống phát hiện và khôi phục |
| Cache/JWKS stale khi rollover | Không áp dụng | Dùng key cache theo policy | Không bỏ qua chữ ký hoặc allowlist |

### Kiểm thử tải và khả năng phục hồi

- Đo latency p50/p95/p99 của introspection.
- Đo tải AS khi mọi request đều introspect và khi có cache.
- Mô phỏng AS timeout, DNS lỗi, TLS lỗi và network partition.
- Mô phỏng event revoke bị trễ, mất, lặp hoặc đến sai thứ tự.
- Kiểm thử nhiều node cùng xử lý một token ngay sau revoke.
- Đo thời gian từ revoke API response đến lần cuối cùng một resource server chấp nhận token.
- Kiểm thử cache eviction, restart node và warm-up sau deploy.
- Kiểm tra không có raw token trong log, trace, metrics label hoặc crash dump.

## 19. Chỉ số vận hành cần theo dõi

| Chỉ số | Ý nghĩa |
| --- | --- |
| Introspection request rate | Tải kiểm tra trạng thái tại AS |
| Introspection latency p95/p99 | Độ trễ thêm vào request path |
| Introspection error/timeout rate | Khả năng sẵn sàng của AS và mạng |
| Active cache hit ratio | Mức giảm round trip và độ phụ thuộc cache |
| Revocation propagation lag | Thời gian từ revoke đến khi các node cập nhật |
| Revoked-token acceptance count | Số request token đã revoke vẫn được chấp nhận |
| JWT validation failure by reason | Phát hiện lỗi iss, aud, exp, typ, kid, chữ ký |
| Denylist lookup latency/error | Chi phí và độ sẵn sàng của JWT revocation state |
| Refresh token reuse detections | Tín hiệu replay hoặc client lỗi trong rotation |
| Legacy-token traffic | Tiến độ ngừng định dạng token cũ |

Không đưa raw access token, refresh token, jti hoặc subject trực tiếp vào metric label. Nếu cần tương quan điều tra, dùng mã tham chiếu hoặc digest được bảo vệ và giới hạn retention.

## 20. Các lỗi di trú thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chuyển reference token sang JWT nhưng không có cơ chế thu hồi | Token bị revoke vẫn được chấp nhận đến exp | Chọn TTL, denylist, introspection hoặc session check theo SLO |
| Nghĩ rằng RFC 7009 tự broadcast revoke đến mọi API | Resource server không biết trạng thái mới | Dùng introspection, event invalidation hoặc trạng thái dùng chung |
| Cache introspection quá lâu | Token đã revoke vẫn được chấp nhận | Giới hạn TTL và hỗ trợ invalidation |
| Nghĩ rằng JWT không thể introspect | Bỏ lỡ phương án kiểm tra trạng thái tập trung | Có thể introspect JWT nếu AS hỗ trợ và policy yêu cầu |
| Chỉ revoke refresh token | JWT access token đã phát hành vẫn còn hạn | Thu hồi access token cùng grant theo policy hoặc dùng state check/TTL |
| Dùng jti nhưng không lưu/tra cứu trạng thái | jti không tự tạo khả năng revoke | Triển khai denylist hoặc state store thực sự |
| Denylist chỉ đồng bộ một phần | Một số region tiếp tục chấp nhận token | Kiểm thử consistency, event delivery và đối soát |
| Token exchange nhưng không liên kết token đầu vào/đầu ra | Token con tiếp tục dùng sau khi token cha bị revoke | Định nghĩa lineage và propagation riêng |
| Introspection timeout được coi như active | Request được phép khi trạng thái chưa xác định | Fail policy rõ, thường fail closed với resource nhạy cảm |
| Dual validation bằng cách thử mọi parser | Tạo downgrade path và khó kiểm soát profile | Định tuyến theo cấu hình/token profile, unknown thì reject |
| Dùng chung TTL cho mọi API | API nhạy cảm có cửa sổ rủi ro quá dài | SLO và policy theo từng resource |
| Ghi token vào log để debug | Lộ bearer credential | Redact token và dùng correlation ID |
| Chỉ kiểm thử ở một node | Bỏ sót độ trễ propagation | Kiểm thử multi-node và multi-region |

## 21. Kế hoạch rollback và xử lý sự cố

Trước khi chuyển production, xác định cách rollback mà không làm sống lại token đã thu hồi.

Một kế hoạch rollback cần:

1. Xác định phiên bản issuer/resource server có thể quay lại.
2. Giữ cơ chế kiểm tra trạng thái cho token cũ còn hiệu lực.
3. Không tái kích hoạt refresh token hoặc grant đã bị revoke.
4. Không đưa thuật toán, key hoặc token profile cũ trở lại nếu đã bị loại bỏ vì sự cố bảo mật.
5. Ghi nhận token nào đã phát hành theo từng định dạng, issuer, audience và khoảng thời gian.
6. Có khả năng thu hồi hàng loạt token theo grant/session hoặc jti khi phát hiện lộ lọt.
7. Kiểm tra cache, event consumer và denylist sau rollback.

Nếu reference token hoặc JWT bị lộ, hãy thu hồi token/grant theo phạm vi điều tra, vô hiệu hóa refresh token liên quan, đánh giá các token đầu ra từ token exchange và kiểm tra request đã được thực hiện trong cửa sổ rủi ro.

Không chỉ xoay signing key để giải quyết mọi sự cố JWT. Nếu resource server xác minh token offline, đổi khóa có thể làm mất hiệu lực toàn bộ token được ký bằng khóa cũ nhưng cũng có thể gây gián đoạn lớn; cần phân biệt lộ token, lộ private signing key và lỗi propagation trạng thái.

## 22. Checklist quyết định và triển khai

- [ ] Xác định token nào đang được cấp: reference token, JWT hoặc cả hai.
- [ ] Xác định từng resource server kiểm tra trạng thái online hay local.
- [ ] Định nghĩa SLO thu hồi theo từng loại resource và sự kiện.
- [ ] Đo propagation delay hiện tại, cache TTL và thời gian node nhận sự kiện.
- [ ] Xác định revoke một token, một session, một grant hay toàn bộ tài khoản.
- [ ] Xác định quan hệ giữa access token, refresh token và grant.
- [ ] Nếu dùng JWT, chốt profile, typ, iss, aud, exp, jti, thuật toán và JWKS.
- [ ] Nếu dùng reference token, bảo vệ introspection endpoint, token store và cache.
- [ ] Nếu dùng JWT denylist, tra cứu theo issuer và jti, có retention đến sau exp.
- [ ] Nếu dùng session/version claim, xác định nguồn trạng thái và cách đồng bộ.
- [ ] Định nghĩa fail policy khi AS, denylist hoặc event bus không sẵn sàng.
- [ ] Nếu dùng token exchange, thiết kế lineage và propagation revoke cho token đầu ra.
- [ ] Kiểm thử dual-format và từ chối token không xác định profile.
- [ ] Kiểm thử multi-node, multi-region, cache stale và event mất/lặp.
- [ ] Theo dõi revoked-token acceptance và thời gian propagation.
- [ ] Có rollback plan không tái kích hoạt token/grant đã bị thu hồi.
- [ ] Xóa dữ liệu và khóa cũ sau khi mọi token cũ hết hiệu lực và retention cho phép.

## 23. Sơ đồ quyết định theo yêu cầu thu hồi

~~~mermaid
flowchart TD
    A[Định nghĩa SLO thu hồi] --> B{Cần ngừng chấp nhận gần như tức thời?}
    B -- Có --> C{Có thể phụ thuộc AS hoặc state service trực tuyến?}
    C -- Có --> D[Reference token + introspection cache ngắn hoặc không cache]
    C -- Không --> E[JWT + state check/denylist/event invalidation nhất quán]
    B -- Không --> F{Chấp nhận cửa sổ đến exp?}
    F -- Có --> G[JWT TTL phù hợp + revoke refresh/grant]
    F -- Không --> H[JWT + introspection hoặc kiểm tra session/grant]
    D --> I[Đo propagation và fail policy]
    E --> I
    G --> I
    H --> I
    I --> J[Kiểm thử revoke, outage, cache và nhiều region]
    J --> K{Đạt SLO?}
    K -- Không --> L[Điều chỉnh TTL, cache, state lookup hoặc kiến trúc]
    L --> I
    K -- Có --> M[Di trú theo từng client/resource]
~~~

## 24. Sơ đồ di trú qua token exchange

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway / STS Client
    participant AS as Authorization Server
    participant R as Backend Resource
    C->>G: Request với reference token
    G->>AS: Introspect subject token
    AS-->>G: active=true, scope, aud, exp
    G->>AS: Token Exchange (subject_token)
    AS->>AS: Kiểm tra policy và phát hành token đích
    AS-->>G: JWT audience hẹp
    G->>R: Request với JWT
    R->>R: Verify signature, iss, aud, exp, typ
    Note over AS,R: Revocation của token đầu vào không tự động thu hồi JWT đầu ra
    AS-->>R: Revoke state/event hoặc introspection khi policy yêu cầu
    R->>R: Kiểm tra lineage/session trước thao tác nhạy cảm
~~~

Sơ đồ chỉ mô tả một phương án triển khai. Kênh truyền sự kiện thu hồi và cách backend kiểm tra lineage là quyết định riêng của deployment; RFC 8693 không tự định nghĩa chúng.

## 25. Nguyên tắc cần ghi nhớ

1. Reference token và JWT là hai cách biểu diễn access token; mức độ thu hồi phụ thuộc cách resource server kiểm tra trạng thái.
2. Reference token kết hợp introspection cho AS khả năng quyết định token còn active theo trạng thái hiện tại, nhưng cache và propagation vẫn tạo cửa sổ stale.
3. JWT xác minh cục bộ tối ưu latency và khả năng phân tán, nhưng chữ ký không cho biết token vừa bị thu hồi.
4. RFC 7009 là giao thức client yêu cầu AS thu hồi; RFC 7662 là giao thức resource server hỏi trạng thái.
5. Thu hồi refresh token ngăn cấp token mới; access token đã phát hành cần được xử lý theo policy riêng.
6. TTL ngắn giới hạn cửa sổ rủi ro, không phải cơ chế revoke tức thời.
7. jti chỉ định danh token; denylist hoặc state lookup mới tạo ra khả năng từ chối token trước exp.
8. Session/grant version và event invalidation vẫn cần trạng thái dùng chung, consistency, retry và đối soát.
9. JWT có thể được introspect; reference token có thể bị cache. Không suy ra semantics chỉ từ định dạng.
10. Token exchange không tự tạo liên kết thu hồi giữa subject token và token đầu ra; deployment phải thiết kế lineage nếu cần.
11. Sender constraint giảm replay của token bị đánh cắp nhưng không thay thế revocation.
12. Chọn mô hình theo SLO, độ nhạy của resource, latency, availability và năng lực vận hành; có thể kết hợp nhiều mô hình.

### Tài liệu chuẩn tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, refresh token, grant và token endpoint.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách gửi bearer access token đến protected resource.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation endpoint và xử lý token/grant liên quan.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái active, metadata introspection, bảo vệ endpoint và cache trade-off.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token, typ, claims và validation.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): sender-constrained access token, audience restriction và refresh token rotation.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): subject token, actor token, token exchange và giới hạn về liên kết/revocation propagation.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): chỉ định resource/audience cho access token.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): sender constraint bằng mTLS.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender constraint bằng proof-of-possession ở tầng ứng dụng.

**Kết luận:** Hãy chọn token format sau khi xác định thời gian thu hồi mà từng resource cần đạt. Reference token kết hợp introspection phù hợp khi trạng thái trung tâm phải được kiểm tra thường xuyên; JWT xác minh cục bộ phù hợp khi chấp nhận một cửa sổ hiệu lực có giới hạn hoặc có cơ chế trạng thái bổ sung. Khi di trú hoặc dùng token exchange, phải bảo toàn quan hệ giữa token, session và grant để một sự kiện thu hồi không bị mất ở ranh giới giữa hai định dạng.

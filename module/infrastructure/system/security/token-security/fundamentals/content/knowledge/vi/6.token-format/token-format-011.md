# Parser chặt chẽ và input không hợp lệ

## 1. Vì sao parser token là một ranh giới bảo mật?

Một API nhận access token từ client qua HTTP đang nhận **dữ liệu do bên ngoài kiểm soát**. Token có thể bị cắt ngắn, mã hóa sai, chứa JSON nhập nhằng, khai báo thuật toán không được phép hoặc cố khiến các thành phần trong hệ thống diễn giải khác nhau. Nếu parser dễ dãi, một token bị từ chối ở lớp này có thể được chấp nhận ở lớp khác; nghiêm trọng hơn, ứng dụng có thể cấp quyền dựa trên claims chưa được xác minh.

Trong module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, bài học thuộc chương **Token format**, tập trung vào nguyên tắc:

> **Parse chặt để hiểu một biểu diễn duy nhất; xác minh mật mã và ngữ cảnh tin cậy trước khi coi claims là đáng tin; từ chối khi có lỗi hoặc mơ hồ.**

Ví dụ: `orders-api` chấp nhận OAuth 2.0 JWT access token ký bằng RS256 từ `https://auth.example.test`, audience `orders-api`. Client gửi:

~~~text
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6ImF0K2p3dCJ9.eyJ...<payload>...<signature>
~~~

Một token trông giống JWT **không chứng minh** chữ ký đúng, issuer đáng tin, audience hợp lệ, chưa hết hạn hoặc có scope đủ quyền. Vì vậy hãy phân biệt những việc sau:

| Công đoạn | Câu hỏi | Hành động khi lỗi |
| --- | --- | --- |
| **Nhận bearer credential** | HTTP header có đúng chỗ, đúng scheme, không trùng lặp và nằm trong giới hạn kích thước? | Từ chối request mơ hồ/sai cú pháp |
| **Parse cấu trúc** | Token khớp định dạng đã thỏa thuận? Base64url, UTF-8, JSON, JWS/JWE có hợp lệ? | Từ chối token không đúng định dạng |
| **Kiểm tra khóa và mật mã** | Issuer, thuật toán, khóa đã được tin cậy? Chữ ký hoặc xác thực mã hóa đúng? | Từ chối token không thể xác thực |
| **Validate claims/profile** | `iss`, `aud`, `exp`, `nbf`, `typ`, kiểu dữ liệu và loại token đúng hợp đồng? | Từ chối token không phù hợp |
| **Authorize request** | Scope/role, tenant, quyền sở hữu bản ghi có cho phép thao tác không? | Từ chối thao tác thiếu quyền |

**Parse thành công không có nghĩa là token hợp lệ; token hợp lệ không có nghĩa là request được phép.** Đây là hai ranh giới khác nhau giữa authentication và authorization.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện input sai ở HTTP Bearer, JWT Compact Serialization và JSON claims.
2. Phân biệt xác minh JWT/JWS/JWE với introspection cho opaque token.
3. Thiết lập quy tắc chặt về kích thước, kiểu dữ liệu, thuật toán, issuer, audience và key selection.
4. Giải thích các lỗi **duplicate claims**, **algorithm confusion**, **token confusion**, **parser differential** và **denial of service**.
5. Viết bộ kiểm thử âm (negative tests) và cấu hình Java/Spring Security để từ chối token không hợp lệ mà không lộ credential.

## 2. Xác định hợp đồng trước khi viết parser

Parser an toàn không đoán mọi định dạng. Resource server cần một **hợp đồng đầu vào rõ ràng** với authorization server (AS):

| Thành phần hợp đồng | Ví dụ cho `orders-api` | Nếu không xác định rõ |
| --- | --- | --- |
| Cơ chế sử dụng | `Authorization: Bearer <access_token>` | Nhiều nguồn token bị trộn lẫn |
| Định dạng access token | JWT JWS compact **hoặc** opaque/introspection, được cấu hình trước | Client tự ép API đổi parser theo hình dáng chuỗi |
| Issuer tin cậy | `https://auth.example.test` | Tin token của AS khác |
| Thuật toán ký chấp nhận | RS256 theo thỏa thuận | `alg` do token tự quyết định |
| JWKS hoặc introspection | Endpoint tin cậy do triển khai/metadata đã xác minh cung cấp | SSRF, lấy khóa từ nơi do attacker chỉ định |
| Loại token | OAuth access token, ví dụ JWT profile `typ: at+jwt` | ID token hoặc client assertion được nhận nhầm |
| Audience | `orders-api` | Token cấp cho `billing-api` bị dùng lại |
| Claims và phạm vi | `iss` dạng chuỗi, `exp` NumericDate, `aud` string/array, `scope` theo profile AS | Parser ngầm ép kiểu hoặc mất quyền |
| Giới hạn tài nguyên | Kích thước header/token, JSON depth, số khóa và timeout | Token dài bất thường gây tiêu tốn CPU/RAM |

Nếu API chỉ hỗ trợ JWT ký số, token năm đoạn của JWE phải bị từ chối trừ khi **có cấu hình riêng** hỗ trợ JWE. Nếu API dùng opaque token, **đừng phân tích chuỗi theo dấu chấm để đoán JWT**. Opaque token chỉ có nghĩa đối với AS/introspection đã thỏa thuận; opaque token vẫn có thể chứa ký tự trông giống JWT.

Trong hệ thống đa issuer, client có thể cung cấp `iss` chưa xác minh như một *gợi ý* chọn entry **trong allowlist đã cấu hình**. Không biến `iss` chưa tin cậy thành URL để gọi tùy ý hoặc tự tạo trust configuration. Sau khi chọn candidate, phải xác minh chữ ký, issuer và audience tương ứng.

## 3. Ranh giới đầu tiên: HTTP Authorization

Với OAuth 2.0 bearer access token, cách truyền phổ biến và được khuyến nghị là header:

~~~http
GET /orders/123 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

RFC 6750 định nghĩa bearer authorization scheme; token trong header dùng cú pháp `b64token` chứ **không khẳng định** nội dung là JWT được mã hóa Base64. Các bước parser HTTP nên tuân thủ giao thức:

1. Chỉ nhận token từ các kênh được cấu hình. Thông thường chỉ nhận `Authorization`, không tự động tìm trong query string, cookie hoặc form body.
2. Nếu có nhiều header `Authorization`, nhiều credential trong một header hoặc token xuất hiện đồng thời ở nhiều vị trí, từ chối vì mơ hồ. Gateway và ứng dụng phải có cách xử lý nhất quán.
3. Xác nhận đúng scheme `Bearer` (scheme HTTP không phân biệt hoa thường), dấu phân cách và cú pháp token theo RFC 6750. Không tự thêm `Bearer` nếu client quên scheme.
4. Áp dụng giới hạn kích thước ở edge/proxy và ứng dụng trước khi parse hoặc gọi AS.
5. Không tự log nguyên header khi báo lỗi; không gửi bearer token sang URL do client chỉ định.

Ví dụ input:

| Input | Vấn đề | Kết quả mong đợi |
| --- | --- | --- |
| `Authorization: Bearer abc123` | Cú pháp bearer hợp lệ; token thực tế còn phải được xác minh | Tiếp tục kiểm tra token |
| `Authorization: Basic abc123` | Sai scheme đối với API bearer | Không xử lý như bearer |
| `Authorization: Bearer` | Thiếu token | Từ chối |
| `Authorization: Bearer abc, Bearer xyz` | Nhiều credential nhập vào một giá trị | Từ chối, không chọn đại một token |
| Hai header `Authorization` khác nhau | Nhiều cách diễn giải giữa proxy và backend | Từ chối ở ranh giới tiếp nhận |
| `GET /orders?access_token=abc` | Token trong query dễ lộ qua URL | Không hỗ trợ trừ khi có hợp đồng đặc biệt và kiểm soát rủi ro |
| Header cực lớn | Gây tốn bộ nhớ/CPU hoặc vượt giới hạn hạ tầng | Chặn sớm theo giới hạn được cấu hình |

HTTP cho phép một số biến thể khoảng trắng hợp lệ; **parser chặt không có nghĩa là tự ý vi phạm chuẩn**. Ví dụ RFC 6750 quy định một hoặc nhiều dấu cách (`1*SP`) sau scheme; bộ giải mã nên dùng thư viện HTTP/OAuth tuân thủ chuẩn và cố định chính sách xử lý trường hợp nhập nhằng, thay vì một regex tự viết rồi cho kết quả khác ở gateway.

### 3.1. Cẩn thận với request smuggling và sự không nhất quán

Một API có thể nhận request qua CDN → reverse proxy → gateway → ứng dụng Java. Nếu gateway chọn giá trị `Authorization` đầu tiên còn backend chọn giá trị cuối cùng, hệ thống có thể kiểm tra một token nhưng sử dụng danh tính khác. Mọi lớp cần thống nhất cách chuyển tiếp header, loại bỏ các header danh tính do client tự giả mạo và chặn request có credential trùng lặp hoặc sai cú pháp.

Lỗi này không được giải quyết bằng cách lấy `Authorization`, `X-Auth-Token`, cookie và query rồi “ưu tiên cái nào có trước”. **Số nguồn credential càng nhiều, parser differential càng dễ xảy ra.**

## 4. Phân biệt JWT, JWS, JWE và opaque token

Một JWT có thể được bảo vệ bằng chữ ký/mã xác thực JWS hoặc bằng mã hóa được xác thực JWE. Token bảo vệ theo JWS compact thường có **ba đoạn**, phân cách bằng dấu chấm:

~~~text
BASE64URL(UTF8(JWS Protected Header))
.
BASE64URL(JWS Payload)
.
BASE64URL(JWS Signature)
~~~

JWE compact thường có **năm đoạn** (protected header, encrypted key, initialization vector, ciphertext, authentication tag). **Đếm đoạn chỉ là bước kiểm tra hình thức cho một profile đã biết**, không phải tiêu chí chứng minh token đáng tin. Một số định dạng JWS/JWE có JSON Serialization, và nested JWT cần kiểm tra nhiều lớp; chỉ hỗ trợ chúng khi hợp đồng API quy định rõ.

~~~mermaid
flowchart TD
    T["Credential lấy từ HTTP request"] --> C{"Hợp đồng token của API"}
    C -->|"JWT JWS compact"| S{"Đúng 3 đoạn / base64url / JSON?"}
    C -->|"Opaque"| I["Gửi tới introspection endpoint đáng tin"]
    C -->|"JWE compact được hỗ trợ"| E["Parse 5 đoạn, xác thực và giải mã JWE"]
    S -->|"Không"| REJ["Từ chối"]
    S -->|"Có"| SIG["Xác minh chữ ký bằng khóa đã tin"]
    E --> NEST["Kiểm tra nested token/profile nếu có"]
    SIG --> CLAIMS["Validate claims và ngữ cảnh"]
    NEST --> CLAIMS
    I --> ACTIVE["Kiểm tra active và policy từ AS"]
    CLAIMS --> AUTHZ["Authorize theo scope và tài nguyên"]
    ACTIVE --> AUTHZ
~~~

**Đừng fallback âm thầm:** Nếu JWT sai chữ ký, không được thử coi cùng chuỗi đó là opaque token chỉ để “cứu” xác thực, trừ khi kiến trúc đã thiết kế, ràng buộc rõ nguồn tin cậy và tránh bypass. Nếu một API hỗ trợ nhiều token profile, cơ chế chọn profile phải cố định, không để trường chưa xác thực tùy ý mở rộng danh sách thuật toán, issuer hay endpoint.

### 4.1. Base64url khác Base64 thường

Các đoạn trong JWS compact dùng Base64url (RFC 7515/RFC 4648): bảng ký tự `A-Z`, `a-z`, `0-9`, `-`, `_`; encoding trong JWS compact **không có dấu `=` padding**. Không tự bỏ ký tự lạ, đổi `+`/`/` thành `-`/`_` hoặc silently trim chuỗi để biến input sai thành input được chấp nhận.

Ví dụ các tình huống nên bị từ chối theo hợp đồng JWS compact chuẩn:

~~~text
abc.def                    # Thiếu phần chữ ký
abc.def.ghi.jkl            # Quá nhiều đoạn
abc.def+.ghi               # Payload chứa '+' thay vì base64url
abc.def=.ghi               # Padding không đúng compact encoding
abc..ghi                   # Payload rỗng không phù hợp profile JWT
abc.def.ghi%2F             # Percent-encoding xuất hiện trong token
~~~

Đối với JWS, một phần chữ ký có thể là chuỗi Base64url rỗng trong các ngữ cảnh đặc biệt như unsecured JWS; **JWT access token được bảo vệ bằng chữ ký phải bác bỏ `alg: none` và chữ ký rỗng**. Các ví dụ trên là preflight về biểu diễn, chưa thay thế kiểm tra nội dung JSON và chữ ký.

Một decoder mã hóa chỉ nên được áp dụng **một lần** theo đúng quy tắc. “Decode tới khi nào được” dẫn đến khác biệt giữa các thư viện. Chẳng hạn `%2E` không được xử lý thành dấu chấm mới để làm thay đổi số đoạn JWT, và ký tự Base64 không hợp lệ không được lọc ra rồi tiếp tục.

### 4.2. Bảo toàn chính xác dữ liệu đã ký

Trong JWS, chữ ký gắn với **dãy byte** của input ký theo đặc tả, không phải một đối tượng JSON đã “sắp xếp đẹp”. Không parse JSON rồi stringify lại, chuẩn hóa Unicode, tự sắp khóa hoặc biến đổi khoảng trắng trước khi xác minh. Hai JSON có cùng ý nghĩa đối với ứng dụng có thể có **byte khác nhau**, kéo theo chữ ký khác nhau.

Nên dùng thư viện JOSE đã được kiểm chứng để xác minh trên JWS compact ban đầu. Ứng dụng có thể giải mã header chưa xác minh để tìm `alg`/`kid` nhằm lựa chọn khóa trong trust configuration, nhưng **không bao giờ coi header/payload chưa xác minh là dữ liệu phân quyền**.

### 4.3. Các biến thể không được mặc nhiên chấp nhận

RFC 7797 mô tả JWS với payload không Base64url (`"b64": false`), nhưng **JWT không được sử dụng `b64=false`** theo đặc tả đó. Vì vậy JWT access token nên từ chối cấu hình này, không tự chọn parser đặc biệt dựa trên `b64`. Các JWS extension header trong `crit` phải được thư viện hỗ trợ và xử lý đúng; nếu không hiểu một extension bắt buộc, phải từ chối.

Khi hệ thống được thiết kế để nhận JWE, cần xác minh thuật toán quản lý khóa `alg` và thuật toán mã hóa nội dung `enc` theo allowlist, kiểm tra tính toàn vẹn/tag, rồi validate token ở lớp trong. **Giải mã thành công không tự đồng nghĩa với quyền truy cập hợp lệ**.

## 5. JSON parser: input hợp lệ về cú pháp vẫn có thể nhập nhằng

JWS protected header và JWT claims là các JSON object. Dù ký số hợp lệ, parser vẫn có thể tạo ra kết quả khác nhau khi dữ liệu được các thành phần xử lý không nhất quán.

### 5.1. Duplicate JSON members và duplicate claims

Xét payload:

~~~json
{
  "iss": "https://auth.example.test",
  "aud": "orders-api",
  "scope": "orders.read",
  "scope": "orders.admin",
  "exp": 1795400300
}
~~~

Đây là một biểu diễn JSON có **tên trường lặp lại**. Một parser có thể giữ giá trị đầu, parser khác giữ giá trị cuối. RFC 7519 cho phép JWT parser từ chối duplicate claim names **hoặc** dùng cách xử lý giữ phần tử cuối theo yêu cầu JSON parser nhất định; đối với hệ thống cần tính nhất quán và bảo mật, **khuyến nghị từ chối hoàn toàn duplicate names** theo chính sách của API.

Vấn đề còn khó hơn với tên khóa có Unicode escape:

~~~json
{
  "iss": "https://auth.example.test",
  "\u0069ss": "https://attacker.example.test"
}
~~~

Sau khi giải mã escape, hai tên trên đều là `iss`. Parser kiểm tra duplicate cần so sánh **tên trường sau JSON unescape**, không chỉ so chuỗi nguồn từng byte. Áp dụng cùng chính sách cho cả protected header như `alg`/`kid` và payload claims; nếu phần mềm phía trước với phía sau đọc khác nhau, có thể sinh lỗi parser differential.

### 5.2. UTF-8, Unicode và JSON chuẩn

- JSON trong JWT phải dùng **UTF-8** theo JOSE/JWT. Không chấp nhận chuỗi byte UTF-8 lỗi rồi thay bằng ký tự `�` để tiếp tục xử lý.
- Không ngầm chấp nhận comment kiểu JavaScript, trailing comma, `NaN`, `Infinity`, dấu nháy đơn, hoặc các biến thể JSON5 nếu profile chỉ cho phép JSON chuẩn.
- Nếu xử lý Unicode escape, cần từ chối chuỗi surrogate không hợp lệ và bảo toàn ý nghĩa đã định nghĩa.
- Không tự xóa ký tự điều khiển, BOM hoặc khoảng trắng bên trong token để biến token sai thành hợp lệ; thư viện cần thực thi hợp đồng rõ ràng của từng lớp.
- Các định danh bảo mật như `iss`, `aud`, `sub` và `client_id` không nên bị `trim`, lowercase, decode URL lần hai hoặc Unicode normalize tùy tiện trước khi so khớp.

Ví dụ `https://auth.example.test` và `https://AUTH.example.test/` có thể trông tương đương với một số xử lý URL, nhưng việc kiểm tra `iss` trong JWT cần so sánh **giá trị issuer đúng theo cấu hình** và ngữ nghĩa đối chiếu của token profile. Không tự bỏ dấu `/` cuối hoặc chuyển đổi chữ hoa/chữ thường để “khớp gần đúng”.

### 5.3. Kiểm tra kiểu dữ liệu của claims

Một JSON có thể parse được nhưng vẫn **sai schema** mà API yêu cầu:

~~~json
{
  "iss": 123,
  "aud": {"value": "orders-api"},
  "scope": ["orders.read"],
  "exp": "1795400300",
  "nbf": true
}
~~~

Ở hợp đồng ví dụ này: `iss` phải là chuỗi; `aud` là chuỗi hoặc mảng chuỗi; `exp`/`nbf` là NumericDate dạng JSON number; `scope` theo profile là chuỗi có các mục phân cách bởi dấu cách. Không tự ép `"1795400300"` thành số, `true` thành `1` hoặc object thành chuỗi. Nếu AS dùng `scp` dạng mảng, **phải cấu hình rõ ràng profile đó** thay vì đoán khi gặp token lạ.

Về chuẩn JWT, **NumericDate** là số giây từ Unix epoch và không bắt buộc là số nguyên trong mọi profile. Validator cần xử lý số hữu hạn, phạm vi thời gian hợp lý và giới hạn tràn số của thư viện; nếu hợp đồng AS yêu cầu thời gian nguyên giây thì đó là **ràng buộc profile bổ sung**, không phải khẳng định mọi JWT chuẩn đều cấm phần lẻ.

Các trường hợp lỗi cần chặn: số quá lớn làm tràn kiểu dữ liệu, số âm bất thường theo policy, `exp` nhỏ hơn thời gian hiện tại, `nbf` quá xa trong tương lai, giá trị `aud` rỗng, `iss` sai issuer, hoặc `sub` sai kiểu. Có thể cho phép lệch đồng hồ nhỏ được cấu hình nhưng không biến thành cửa sổ chấp nhận vô hạn.

### 5.4. Audience, scope và identity phải so khớp ngữ nghĩa

Các kiểm tra:

- `aud` có thể là một chuỗi hoặc mảng các chuỗi theo JWT; yêu cầu **giá trị audience của API xuất hiện chính xác**, không dùng `contains("orders")` hoặc tiền tố `startsWith`.
- `scope` trong OAuth thường là chuỗi các scope cách nhau bằng dấu cách; phải tách theo hợp đồng, so **từng scope nguyên vẹn**. Scope `orders.readonly` không đồng nghĩa `orders.read`.
- `sub`, `client_id`, `tenant_id` cần type và contract nhất quán; không tự gán chủ thể mặc định nếu thiếu.
- `roles` hoặc `groups` nếu AS dùng là dữ liệu ủy quyền riêng của profile; không nên tự tin mọi JWT đều có claims đó.
- Luôn kiểm tra quyền trên tài nguyên/tenant thực tế; token có `scope: orders.read` không tự cấp quyền đọc đơn hàng của tenant khác.

Kiểu dữ liệu và so sánh chuỗi là một phần của **security policy**, không chỉ là việc code map JSON thành object Java.

## 6. Header JOSE: alg, kid và URL là dữ liệu đầu vào không đáng tin

Một header JWT JWS minh họa:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "key-rotation-2026-11"
}
~~~

Header có thể giúp thư viện tìm khóa, nhưng trước khi chữ ký được xác minh, mọi trường đều là **untrusted input**.

### 6.1. Algorithm confusion

Không lấy `alg` từ token rồi tự chọn bất kỳ thuật toán nào. Chỉ cho phép danh sách thuật toán được cấu hình cho issuer và token profile; ví dụ RS256. Phải từ chối `alg: none` hoặc cố dùng HS256 với cùng bytes vốn là RSA public key. Không cho thuật toán đối xứng và bất đối xứng dùng lẫn key material.

### 6.2. kid chỉ chọn khóa trong trust store

`kid` là **gợi ý chọn khóa**, không phải URL, path, câu lệnh SQL hay bằng chứng tin cậy. Một token có:

~~~json
{
  "alg": "RS256",
  "kid": "../../private/keys/backup.pem",
  "jku": "https://untrusted.example/keys.json"
}
~~~

không được khiến API đọc file cục bộ, xây câu SQL động hoặc tải JWKS tùy ý. Chỉ tìm `kid` trong bộ khóa tin cậy của issuer đã phê duyệt; giới hạn kích thước/định dạng `kid` và giới hạn tần suất refresh JWKS khi không tìm thấy khóa.

### 6.3. jku, x5u, x5c và crit

- `jku`/`x5u` có thể chỉ URL tài liệu khóa/chứng chỉ. **Không tự fetch URL do token gửi**; đây là điểm tấn công SSRF, exfiltration hoặc trust hijack. Nguồn khóa phải do cấu hình/metadata tin cậy quy định.
- `x5c` có thể mang chuỗi chứng chỉ. Chứng chỉ được đính kèm **không tự động được tin cậy**; nếu profile cho phép phải kiểm tra chuỗi và trust anchors đúng cách.
- `crit` mô tả extension header bắt buộc hiểu. Nếu gặp extension không hỗ trợ, từ chối thay vì bỏ qua.
- `typ` giúp phân biệt access token JWT với ID token hoặc token khác; kiểm tra đúng profile mà AS và RS thỏa thuận, không coi việc thấy chuỗi `JWT` ở header là đủ.

**Kết quả mong muốn:** Dù kẻ tấn công kiểm soát `kid`, `alg`, `jku` hay `iss` trong token, chúng không thể tạo nguồn tin cậy mới hoặc buộc resource server bỏ qua chữ ký/audience.

## 7. Input không hợp lệ và chống từ chối dịch vụ (DoS)

Parser token thường nằm trên đường xử lý của **mọi request có xác thực**. Một token lỗi có thể không gây vượt quyền nhưng vẫn gây hỏng dịch vụ nếu bắt API tiêu tốn quá nhiều CPU, RAM, kết nối mạng hoặc log. Áp dụng giới hạn trước khi giải mã dữ liệu đắt đỏ là một phần quan trọng của thiết kế.

| Input bất thường | Rủi ro | Kiểm soát nên có |
| --- | --- | --- |
| Bearer header hàng MB | Phân bổ bộ nhớ lớn, request queue bị lấp | Giới hạn header ở proxy/gateway và ứng dụng |
| Một đoạn Base64url cực dài | Decode và tạo JSON quá lớn | Kiểm tra kích thước toàn token và đoạn trước khi decode |
| JSON lồng hàng nghìn tầng | Parser đệ quy sâu, stack overflow/CPU cao | Max nesting depth, max document size |
| Array `aud` hoặc `scope` dài bất thường | Tăng chi phí cấp phát và phân quyền | Giới hạn số phần tử theo hợp đồng |
| `kid` thay đổi liên tục | Liên tục refresh JWKS, gây tải AS | Cache theo issuer, rate limit refresh và negative caching thích hợp |
| `jku` trỏ IP nội bộ/metadata service | SSRF nếu thư viện tự fetch | Không fetch URL từ token; pin endpoint tin cậy |
| JSON number cực lớn như `1e999999` | Overflow hoặc xử lý số chậm | Parser giới hạn độ dài/số và reject giá trị ngoài range |
| Claims thiếu kiểu hoặc lặp | Đọc sai quyền giữa các thành phần | JSON parser strict, schema validation |
| Chữ ký sai hàng loạt | CPU dành để verify và ghi log | Rate limiting, quan sát metrics gộp, tránh log nguyên token |
| Introspection chậm hoặc treo | Exhaustion thread/connection pool | Timeout, concurrency limit, circuit breaker và fail closed |

Các giá trị giới hạn là **quyết định theo hệ thống**, không có một con số cố định áp dụng cho mọi JWT. Ví dụ, với API chỉ dùng JWT nhỏ, đội phát triển có thể chọn token tối đa vài KB hoặc vài chục KB theo token profile thực tế; cần kiểm tra token hợp lệ lớn nhất trước khi chốt để tránh từ chối nhầm credential hợp lệ. Hạn mức phải nhất quán ở gateway và ứng dụng, cùng chính sách response phù hợp.

### 7.1. Không cho parser và verifier tạo kết nối mạng tùy ý

Một verifier JWT có thể cần tải JWKS qua HTTPS, nhưng **đường dẫn JWKS phải được cấu hình từ issuer tin cậy**, không lấy từ `jku` do attacker gửi. Nếu không có khóa đúng `kid`:

1. Tra cache JWKS của đúng issuer, đúng thuật toán/loại khóa.
2. Nếu policy cho phép, refresh JWKS từ endpoint cố định với giới hạn tốc độ.
3. Nếu vẫn không có khóa hoặc kết nối lỗi, từ chối token.

Không nên refresh JWKS vô hạn mỗi lần gặp `kid` lạ; attacker có thể tạo hàng nghìn token với `kid` ngẫu nhiên. Cache được phân vùng theo issuer; không dùng một `kid` toàn cục cho nhiều AS.

### 7.2. Không làm rò rỉ dữ liệu khi báo lỗi

Thông điệp phục vụ client chỉ cần diễn đạt credential không hợp lệ hoặc không đủ quyền. Log nội bộ có thể ghi **mã lý do chung** như `INVALID_BASE64URL`, `UNSUPPORTED_ALG` hoặc `INVALID_AUDIENCE`, request ID, issuer *đã được xác nhận*, endpoint và thời gian. Không log toàn bộ JWT, bearer header, thông tin cá nhân trong payload hoặc private key.

Không hiển thị stack trace parser và dữ liệu decode nguyên vẹn cho client. Ngoài việc lộ chi tiết nội bộ, lỗi dài chứa token có thể rơi vào APM, hàng đợi và kho log có quyền truy cập rộng hơn API.

## 8. Phân biệt parser strict với validator strict

Một JWT hoàn toàn hợp lệ theo JSON và JWS có thể vẫn không được phép truy cập API. Ví dụ:

~~~json
{
  "iss": "https://auth.example.test",
  "aud": "billing-api",
  "scope": "orders.read",
  "iat": 1795400000,
  "exp": 1795400300
}
~~~

Token này có thể có chữ ký hợp lệ từ issuer đáng tin nhưng **audience dành cho billing-api**, vì vậy `orders-api` phải từ chối. Ngược lại, một payload có `aud: orders-api` nhưng JSON sai cú pháp cũng phải bị từ chối ngay.

Một pipeline an toàn có thể hình dung như sau:

~~~mermaid
flowchart TD
    A["Request chứa bearer credential"] --> B{"Một nguồn credential hợp lệ?"}
    B -->|"Không"| R["Reject"]
    B -->|"Có"| C{"Giới hạn kích thước và format?"}
    C -->|"Không"| R
    C -->|"Có"| D{"Chọn profile từ cấu hình RS"}
    D --> J["JWT/JWS parser + JOSE verifier"]
    D --> O["Opaque token introspection"]
    J --> E{"Signature, issuer, typ, aud, exp hợp lệ?"}
    O --> F{"active, issuer/resource, scope hợp lệ?"}
    E -->|"Không"| R
    F -->|"Không"| R
    E -->|"Có"| G["Authorization scope/tenant/object"]
    F -->|"Có"| G
    G -->|"Đủ quyền"| OK["Cho phép"]
    G -->|"Không đủ"| R
~~~

Điểm phân biệt:

- **Parser** kiểm tra biểu diễn được định nghĩa và có thể tạo dữ liệu kiểu đã chuẩn hóa theo schema.
- **Cryptographic verifier** kiểm tra chữ ký, MAC hoặc authenticated encryption với khóa/thuật toán tin cậy.
- **Claims validator** kiểm tra issuer, audience, thời hạn, profile, chủ thể và yêu cầu token cụ thể.
- **Authorization engine** đánh giá quyền thực tế trên endpoint và dữ liệu.

Ứng dụng không được parse payload JWT bằng Base64 để đọc `role=admin` rồi cấp quyền trước khi verifier hoàn tất. Dù claims được thư viện cung cấp từ trước để phục vụ lựa chọn issuer/key, chúng vẫn là **untrusted data** và chỉ được dùng trong giới hạn của quy trình xác minh.

### 8.1. Opaque token có cần JSON parser không?

Resource server **không cần và không nên tự decode opaque token**. Thay vào đó, nó gửi chuỗi token đến introspection endpoint đã cấu hình của AS theo RFC 7662. Phản hồi introspection là JSON có contract riêng: tối thiểu trường `active` có ngữ nghĩa của một boolean; những claims khác như `exp`, `aud`, `scope` tùy triển khai.

Ví dụ:

~~~json
{
  "active": true,
  "client_id": "orders-worker",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1795400300
}
~~~

Nếu response chứa `"active": "true"` dạng chuỗi, validator không được tự ép thành boolean. Nếu endpoint gặp lỗi mạng, trả JSON thiếu trường bắt buộc hoặc không thể xác thực server TLS, không được coi đó là `active: true`. Response `active: false` thường không bao gồm claims chi tiết; không diễn giải nó như token được dùng với quyền rỗng rồi cho vào API.

Introspection cũng cần bảo vệ khỏi parser differential và giới hạn thời gian/kích thước response. AS phải có thẩm quyền đối với token và audience/resource được kiểm tra; **`active: true` đơn lẻ chưa phải quyết định phân quyền cuối cùng**.

### 8.2. Kiểm soát token confusion

Cùng một AS có thể phát hành:

| Loại credential | Có thể là JWT? | Audience điển hình | Có dùng gọi resource API trực tiếp? |
| --- | --- | --- | --- |
| OAuth access token | Có hoặc opaque | Resource server/API | Có, khi hợp lệ và đủ quyền |
| OIDC ID token | Có | OAuth/OIDC client ID | Không thay access token |
| OAuth refresh token | Có thể có cấu trúc riêng/opaque | Token endpoint/AS | Không |
| JWT client assertion | Có | Token endpoint/AS | Không |
| Workload/STS assertion | Có | STS/token exchange endpoint | Chỉ khi API chủ động hỗ trợ profile riêng |

Nếu API kiểm tra “có chữ ký đúng của AS” mà không kiểm tra `aud` và **mục đích token**, kẻ tấn công có thể dùng ID token hoặc client assertion ở nơi chỉ nên chấp nhận access token. Với JWT access token profile RFC 9068, header `typ: at+jwt` và các claims/profile đặc thù giúp giảm nhầm lẫn; tuy nhiên, phải thực thi validator chứ không chỉ giải mã header thành object.

## 9. Ví dụ Java và Spring Security: dùng thư viện xác minh, giới hạn input

Các ví dụ sau minh họa kiến trúc Spring Boot/Spring Security 6.x; class/import và cơ chế cấu hình profile cụ thể cần kiểm tra theo phiên bản đang triển khai. **Không tự viết parser JOSE/JWT bằng regex/Base64 decoder để thay verifier**. Dùng thư viện JOSE có kiểm soát thuật toán, cấu hình issuer/JWKS và validator bổ sung.

### 9.1. JWT resource server với issuer và audience cố định

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Cấu hình `issuer-uri` giúp xác định AS tin cậy. Tùy framework, nó có thể hỗ trợ discovery JWKS và kiểm tra claims chuẩn. **Audience và mục đích access token vẫn cần được thực thi theo policy của API**.

Ví dụ cấu hình bean với JWKS URI được pin từ hợp đồng triển khai, thuật toán RS256 và validator audience:

~~~java
@Configuration
class TokenSecurityConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = "https://auth.example.test";
        String jwksUri = "https://auth.example.test/oauth2/jwks";

        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(jwksUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains("orders-api")) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Access token sai audience",
                            null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(standard, audience));
        return decoder;
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/orders/**")
                .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/orders/**")
                .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll());
        http.oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

Bean `JwtDecoder` cần được cấu hình để xử lý loại JWT access token mà AS thực tế phát hành. Ví dụ này **chưa mô tả mọi validation profile** như `typ: at+jwt`, giới hạn tối đa độ sâu JSON hay xử lý duplicate member ở decoder thấp hơn. Hãy chọn phiên bản Nimbus/JOSE an toàn, test những input khó và bổ sung kiểm tra loại token, phạm vi issuer/tenant, quyền trên từng object theo yêu cầu. Mặc định `SCOPE_orders.read` chỉ là kiểm tra scope ở HTTP layer; backend vẫn phải kiểm tra người gọi có được đọc **đúng đơn hàng** không.

### 9.2. Cố định nguồn bearer token

Spring Security có `DefaultBearerTokenResolver` để trích xuất credential theo cấu hình. Với API chỉ cho phép bearer từ header, có thể nêu rõ chính sách:

~~~java
@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
    resolver.setAllowFormEncodedBodyParameter(false);
    resolver.setAllowUriQueryParameter(false);
    return resolver;
}
~~~

Một bean resolver chỉ có tác dụng khi được kết nối vào cấu hình resource server của phiên bản framework đang dùng, ví dụ qua `oauth.bearerTokenResolver(bearerTokenResolver())`. Đảm bảo edge gateway cũng chặn duplicate Authorization headers và áp giới hạn kích thước header. Nếu có proxy chuẩn hóa header, kiểm tra toàn bộ chuỗi gateway → servlet container → Spring; một parser chuẩn tại ứng dụng không xử lý được mâu thuẫn mà proxy đã tạo ra trước đó.

### 9.3. Giới hạn độ dài trước khi đi vào decoder

Một biện pháp bổ sung là đặt mức tối đa của header ở reverse proxy trước ứng dụng. Nếu dùng filter tại ứng dụng, filter chỉ nên kiểm tra **độ dài và cú pháp input đã được framework cho phép** trước các bước parse đắt đỏ; lỗi cần đi qua cơ chế trả 400/401 được thiết kế sẵn, không log credential.

Pseudo-code minh họa vị trí kiểm soát:

~~~text
ON REQUEST:
  if HTTP Authorization header count > 1:
      reject ambiguous request
  if Authorization header exceeds configured limit:
      reject oversized input
  token = standards_compliant_bearer_resolver(request)
  if token exists:
      validated = trusted_token_verifier.verify(token)
      principal = strict_claims_validator.check(validated)
      authorize(principal, request.resource, request.action)
  else:
      handle unauthenticated access according to route policy
~~~

Không dùng đoạn pseudo-code như một thư viện tự xây: việc xử lý JWS/JWE, Base64url, JSON, chữ ký và introspection phải do thư viện phù hợp đảm nhiệm. Nếu thêm preflight riêng, cần đối chiếu nó với RFC và profile để tránh từ chối input hợp lệ hoặc bỏ sót input mơ hồ.

## 10. Bộ kiểm thử âm (negative test suite)

Kiểm thử parser bằng input lỗi là cách xác nhận **fail closed** và giảm khác biệt giữa môi trường. Thực hiện với test JWT được ký bằng khóa của môi trường kiểm thử, issuer/audience/scope xác định. Không dùng khóa production, không dán access token thật vào test report.

| ID | Input kiểm thử | Điều phải xác minh | Kỳ vọng |
| --- | --- | --- | --- |
| N01 | Không có `Authorization` trên endpoint bảo vệ | Thiếu credential | Từ chối yêu cầu xác thực |
| N02 | Hai header `Authorization` | Credential mơ hồ | Từ chối ở edge/app |
| N03 | `Bearer` không có token | Sai cú pháp | Từ chối |
| N04 | Token JWT quá giới hạn kích thước | Chống DoS | Từ chối trước parse sâu |
| N05 | JWS thiếu hoặc thừa đoạn | Sai compact serialization | Từ chối |
| N06 | Base64url chứa `+`/`/`, percent escape, padding sai | Strict encoding | Từ chối theo JWS compact profile |
| N07 | Header JSON chứa duplicate `alg` | Duplicate member | Từ chối |
| N08 | Payload chứa `iss` và `\u0069ss` | Duplicate member sau unescape | Từ chối |
| N09 | Payload JSON malformed, UTF-8 lỗi, trailing comma | Strict JSON/UTF-8 | Từ chối |
| N10 | `alg: none` hoặc HS256 trong API chỉ cho RS256 | Algorithm allowlist | Từ chối |
| N11 | `kid` lạ hoặc `jku` tới IP nội bộ | Source-of-key trust | Không fetch URL tùy ý; từ chối |
| N12 | Chữ ký bị thay một byte | Cryptographic validation | Từ chối |
| N13 | `iss` không thuộc danh sách tin cậy | Issuer pinning | Từ chối |
| N14 | `aud: billing-api` khi API cần `orders-api` | Audience | Từ chối |
| N15 | `exp` là chuỗi; `aud` là object; `nbf` là boolean | Strict claim types | Từ chối |
| N16 | Token hết hạn hoặc chưa đến `nbf` | Time validation | Từ chối |
| N17 | ID token có chữ ký đúng dùng như access token | Token purpose/profile | Từ chối |
| N18 | Token đúng nhưng thiếu scope `orders.write` | Authorization | Từ chối thao tác ghi |
| N19 | JWT với `b64: false` trong JWT access token | Unsupported/forbidden profile | Từ chối |
| N20 | JWT JWE năm đoạn gửi đến API chỉ hỗ trợ JWS ba đoạn | Unsupported format | Từ chối |
| N21 | Introspection trả `"active": "true"` | Không ép sai kiểu | Từ chối |
| N22 | Introspection timeout/TLS lỗi | Fail closed | Không cấp quyền |
| N23 | JSON sâu và `aud` mảng cực dài | Bound complexity | Từ chối theo giới hạn |
| N24 | Token issuer A dùng `kid` trùng issuer B | Key namespace | Không lẫn khóa khác issuer |

**Thêm kiểm thử dương (positive tests):** Token chuẩn, chữ ký đúng, claims đúng, scope đủ; token có audience ở dạng chuỗi và dạng mảng khi cả hai được profile hỗ trợ; xử lý key rotation với JWKS cũ/mới trong cửa sổ hợp lệ; các biến thể whitespace HTTP hợp lệ. Kiểm thử âm mà thiếu positive tests có thể “thành công” với một API luôn từ chối tất cả.

### 10.1. Các assertions ngoài mã HTTP

Đối với mỗi test âm, kiểm tra thêm:

- Không có request nào tới URL `jku` hoặc host lạ do token khai báo.
- Không ghi bearer token, secret, claims nhạy cảm vào log/telemetry.
- Không có mutation nghiệp vụ trước khi xác thực và phân quyền hoàn tất.
- Lỗi được trả nhất quán giữa gateway và ứng dụng; không có chỗ nhận token mà chỗ khác từ chối.
- Độ trễ và RAM/CPU nằm trong giới hạn hợp lý với input quá dài hoặc malformed.
- Khi JWKS/introspection lỗi, hệ thống không chuyển sang chấp nhận token.

Kiểm thử phân biệt **401/403** với lỗi vận hành như **503**: token thiếu/không hợp lệ thường dẫn đến 401 và `WWW-Authenticate` theo RFC 6750; token hợp lệ nhưng thiếu scope dẫn đến 403; AS bị sự cố nên có thông tin vận hành riêng, nhưng trong mọi trường hợp **không cho phép truy cập** khi thiếu bằng chứng hợp lệ.

## 11. Ba bài tập tình huống

### Tình huống 1: Duplicate scope qua hai parser

Gateway kiểm tra JSON payload có `"scope": "orders.read"` ở phần đầu. Backend dùng parser lấy trường `scope` cuối cùng là `"orders.admin"`. JWT được ký bằng khóa của issuer đã tin (ví dụ môi trường có AS lỗi hoặc dữ liệu test được ký hợp lệ). Backend có thể cấp quyền khác với gateway.

**Cách xử lý:** Không sử dụng claims chưa xác minh; nhất quán JSON parser và schema; khuyến nghị **reject duplicate names** ngay cả khi chữ ký đúng. Bảo vệ cả pipeline kiểm tra từ gateway tới backend.

### Tình huống 2: Server tải khóa từ đường dẫn trong kid

Token có `kid: ../../keys/test.pem` và `jku` trỏ tới một địa chỉ nội bộ. Code tự lấy `kid` để ghép đường dẫn file và tải `jku` khi không thấy khóa.

**Lỗi:** Kẻ tấn công đã biến metadata chưa tin cậy thành thao tác filesystem/network. **Cách xử lý:** Chỉ chọn khóa trong JWKS của issuer được phép; `kid` là identifier trong trust store, không phải path/URL; thêm rate limit JWKS refresh và kiểm tra lỗi unknown key.

### Tình huống 3: ID token bị nhận như access token

Client OIDC nhận ID token có chữ ký hợp lệ, `aud = web-client` và `sub = alice`. API kiểm tra chữ ký đúng và `sub` có dữ liệu, sau đó trả đơn hàng của Alice.

**Lỗi:** Token confusion. API đã bỏ qua mục đích và audience của token. **Cách xử lý:** API chỉ chấp nhận access token dành cho `orders-api`, áp dụng token profile phù hợp, scope và quyền bản ghi; từ chối ID token dù issuer và chữ ký đều đúng.

## 12. Checklist triển khai thực tế

1. **Hợp đồng input:** Có quy định rõ HTTP Bearer channel, loại token, JWS/JWE/opaque, issuer, audience và supported algorithms chưa?
2. **Parser cấu trúc:** Có dùng thư viện JOSE/JSON được bảo trì, kiểm tra Base64url, UTF-8, số đoạn, JSON duplicate members và extension headers chưa?
3. **Khóa và nguồn tin cậy:** `kid` chỉ chọn khóa trong JWKS của issuer tin cậy? Có cấm `jku`/`x5u` tùy ý, chặn `alg=none` và algorithm confusion không?
4. **Schema và claims:** Có từ chối sai kiểu dữ liệu, `aud` sai, `exp`/`nbf` không hợp lệ, scope không đúng profile hoặc token sai mục đích chưa?
5. **Resource limits:** Có giới hạn kích thước header/token, JSON depth, array lengths, timeout introspection, retry/refresh JWKS chưa?
6. **HTTP chain:** Gateway và backend có xử lý thống nhất duplicate Authorization headers và nguồn credential không?
7. **Authorization:** Đã kiểm tra scope/tenant/quyền trên tài nguyên **sau** khi token được xác minh chưa?
8. **Quan sát và lỗi:** Có fail closed, 401/403 phù hợp, metrics an toàn và log không chứa token không?
9. **Kiểm thử:** Đã có cả test âm lẫn test dương và ca cross-issuer/token confusion chưa?

### Câu hỏi tự kiểm tra

**Câu 1.** JWT có đúng ba đoạn và decode được Base64url có được coi là hợp lệ không?

**Trả lời:** Chưa. Cần kiểm tra JSON, JOSE header, chữ ký với khóa/issuer tin cậy, token profile, audience, thời hạn và quyền nghiệp vụ.

**Câu 2.** JWT có duplicate claim `scope`; parser cuối cùng chọn giá trị sau. Có nên chấp nhận không?

**Trả lời:** Có những cách xử lý duplicate mà RFC 7519 đề cập, nhưng **chính sách strict được khuyến nghị là từ chối** để tránh parser differential; không dùng một kết quả nhập nhằng cho quyết định bảo mật.

**Câu 3.** Token có `kid` lạ và `jku` trỏ tới URL khác. Có được tải URL đó để kiểm tra chữ ký không?

**Trả lời:** Không. Nguồn khóa phải từ issuer đã được cấu hình/kiểm chứng; token không có quyền thiết lập trust anchor.

**Câu 4.** Một opaque token chứa ba dấu chấm có nên tự động parse JWT không?

**Trả lời:** Không. Định dạng do hợp đồng token của AS/RS xác định, không được suy ra độ tin cậy từ chuỗi ký tự.

**Câu 5.** Khi introspection timeout, có nên cho qua nếu token từng `active: true` cách đây một giờ?

**Trả lời:** Không. Chỉ được dùng cache còn hiệu lực theo policy đã thiết kế; một response cũ ngoài TTL không đủ căn cứ xác minh.

## Tài liệu chuẩn tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cú pháp bearer trên HTTP, `WWW-Authenticate` và nguy cơ rò rỉ token.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS serialization, protected header và signature validation.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWE compact, authenticated encryption và cấu trúc token.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và `kid`.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims, duplicate claims và NumericDate.
- [RFC 4648 — Base Encodings](https://www.rfc-editor.org/rfc/rfc4648): Base64url và quy tắc encoding.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): JSON encoding và duplicate member considerations.
- [RFC 7797 — JWS Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797): `b64` và giới hạn sử dụng với JWT.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm confusion, cross-JWT confusion, input validation và trust boundary.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile access token và `typ`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh opaque token và trạng thái `active`.

**Điểm cần nhớ:** Parser chặt chẽ giúp từ chối biểu diễn token sai, nhập nhằng hoặc nguy hiểm, nhưng nó chỉ là **lớp đầu tiên**. Một resource server an toàn còn phải xác minh chữ ký/nguồn introspection đã tin, issuer, audience, thời hạn, token profile, scope và quyền nghiệp vụ. Không nên cứu input lỗi bằng tự sửa chuỗi, fallback sang parser khác, lấy khóa từ URL do token tự khai hoặc coi claim chưa xác minh là đáng tin.

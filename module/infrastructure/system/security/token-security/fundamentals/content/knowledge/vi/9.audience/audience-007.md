# Confused deputy do bỏ qua audience

## 1. Khi API tin một token không dành cho mình

Trong chương **Audience** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, một quy tắc quan trọng của mô hình tin cậy là: **resource server chỉ được sử dụng access token được cấp cho chính nó**. Resource server có thể xác minh đúng chữ ký JWT, đúng issuer và đúng scope mà vẫn mắc lỗ hổng nghiêm trọng nếu không kiểm tra claim `aud` (audience).

Hãy tưởng tượng một authorization server (AS) phát hành token cho ứng dụng `reports-api`:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": ["reports-api"],
  "scope": "data.read",
  "exp": 1795400300
}
~~~

Token này có thể là JWT ký số hợp lệ, nhưng **không phải giấy phép gọi `orders-api`**. Nếu `orders-api` cũng chấp nhận scope `data.read`, chỉ xác minh chữ ký, issuer và scope, một client có thể lấy token dành cho `reports-api` rồi dùng để yêu cầu dữ liệu từ `orders-api`. Khi `orders-api` sử dụng quyền của chính nó để lấy hoặc trả dữ liệu nhạy cảm, tình huống có thể trở thành một biến thể của **confused deputy**.

> **Issuer cho biết ai phát hành token; audience cho biết token được cấp cho ai.** Một API không được suy luận rằng token có issuer và chữ ký đúng thì dùng được tại mọi API cùng tin issuer đó.

Bài học này tập trung vào sự nhầm lẫn giữa các resource server, cách exploit dẫn tới confused deputy, phương thức phòng vệ với JWT hoặc opaque token, tích hợp OAuth 2.0/OIDC, cùng cách kiểm thử trong Java/Spring Security.

### Sau bài này, bạn có thể

1. Giải thích vì sao bỏ qua `aud` tạo điều kiện dùng access token sai đích (*cross-resource token substitution*).
2. Phân biệt lỗi audience với lỗi scope, issuer, client identity và việc token bị đánh cắp/phát lại.
3. Thiết kế resource server từ chối token dành cho API khác, kể cả khi chữ ký và scope đều đúng.
4. Dùng Resource Indicators hoặc token exchange để xin token cho resource đích khi một service gọi service khác.
5. Viết validator và các phép thử âm để phát hiện confused deputy, multi-audience và đa tenant.

## 2. Confused deputy là gì trong hệ thống OAuth?

**Deputy** là thành phần được ủy quyền hoặc vốn có khả năng thực hiện hành động mà một bên khác không thể trực tiếp thực hiện. **Confused deputy** xảy ra khi kẻ tấn công khiến thành phần đó sử dụng quyền của nó theo ngữ cảnh sai, chẳng hạn coi credential dành cho hệ thống A là bằng chứng ủy quyền đủ để gọi hệ thống B.

Trong OAuth 2.0, ranh giới điển hình có ba bên:

- **Authorization server (AS)** cấp access token với nguồn phát hành, mục đích, thời hạn và phạm vi quyền.
- **Client** sở hữu access token và gửi đến một resource server.
- **Resource server (RS)** kiểm tra token rồi quyết định có dùng quyền của mình để đọc/ghi dữ liệu hay gọi backend khác không.

Một RS không kiểm tra audience có thể chấp nhận token từ **đúng AS nhưng sai resource**. Đây trước hết là **lỗi chấp nhận token sai đích**. Khi RS bị lợi dụng để thực hiện hành động bằng quyền cao hơn hoặc khác quyền mà kẻ tấn công được cấp, đó là hình thái **confused deputy** cụ thể.

### 2.1. Ví dụ hai API có tên scope trùng nhau

Giả sử một tổ chức có:

| Thành phần | Vai trò | Mức tin cậy và quyền |
| --- | --- | --- |
| `auth.example.test` | AS chung | Phát hành token cho nhiều API |
| `reports-api` | API báo cáo ít nhạy cảm | Chấp nhận `data.read` cho dữ liệu báo cáo |
| `orders-api` | API đơn hàng nhạy cảm hơn | Cũng kiểm tra `data.read` nhưng có dữ liệu và quyền backend riêng |
| `client-demo` | Client được phép gọi `reports-api` | Chỉ có quyền được cấp cho reports |

`client-demo` được AS cấp access token `aud=reports-api` và `scope=data.read`. Kẻ tấn công sở hữu client này hoặc có được token đó, rồi gọi endpoint trên `orders-api`. Nếu `orders-api` chỉ xác minh chữ ký và scope `data.read`, nó có thể đọc dữ liệu đơn hàng từ backend và trả cho bên gửi.

Điểm gây ra lỗi là **`orders-api` không kiểm tra token có dành cho mình không**, không phải token đã bị sửa. Kẻ tấn công **không cần** giả mạo chữ ký AS.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client được phép gọi reports-api
    participant AS as Authorization Server
    participant R as reports-api
    participant O as orders-api (deputy)
    participant DB as Orders database / backend
    C->>AS: Xin token cho reports-api, scope=data.read
    AS-->>C: JWT hợp lệ, aud=reports-api
    C->>R: Gọi reports-api (đúng audience)
    R-->>C: Trả báo cáo
    C->>O: Gọi orders-api bằng cùng JWT
    O->>O: Kiểm tra signature, iss, scope; BỎ QUA aud
    O->>DB: Đọc đơn hàng bằng quyền của orders-api
    DB-->>O: Dữ liệu đơn hàng
    O-->>C: Trả dữ liệu trái mục đích token
~~~

Điều kiện để khai thác thành công còn phụ thuộc policy cụ thể: API đích phải dùng quyền trong token theo cách quá rộng, có quyền backend liên quan và không có kiểm tra nghiệp vụ khác ngăn truy cập. **Bỏ qua audience là lỗ hổng độc lập cần sửa ngay cả khi kiểm tra khác tình cờ chặn được kịch bản ví dụ.**

### 2.2. Vì sao lỗi dễ bị bỏ sót?

Nhiều đội phát triển kiểm tra:

~~~text
validSignature(token)
AND trustedIssuer(token.iss)
AND notExpired(token.exp)
AND token.scope contains "data.read"
~~~

rồi coi request đã hợp lệ. Nhưng với một API dùng chung AS cho nhiều dịch vụ, biểu thức này **không ràng buộc token vào resource nhận request**. Điều kiện còn thiếu là:

~~~text
AND expectedAudience("orders-api") ∈ token.aud
~~~

Để an toàn, cần thêm token profile, chính sách tenant và quyền trên từng đối tượng. Tuy nhiên, **audience là rào chắn trực tiếp chống token dành cho API khác bị sử dụng lại**.

## 3. Hiểu chính xác claim aud

Theo JWT (RFC 7519), claim `aud` xác định những **recipient** mà JWT được dự định sử dụng. Đối với JWT có `aud`, bên xử lý JWT phải tự nhận diện được mình trong giá trị audience; nếu không thì phải từ chối.

`aud` có thể biểu diễn bằng:

~~~json
{
  "aud": "orders-api"
}
~~~

hoặc:

~~~json
{
  "aud": ["orders-api", "analytics-api"]
}
~~~

Trong profile OAuth 2.0 JWT access token (RFC 9068), audience là một phần quan trọng của hợp đồng token. Với resource server `orders-api`, chính sách thường là **yêu cầu audience có mặt và chứa chính xác định danh resource đã được cấu hình**.

| Giá trị `aud` trong token | API kỳ vọng `orders-api` | Kết quả |
| --- | --- | --- |
| `"orders-api"` | `orders-api` | Có thể qua kiểm tra audience |
| `["orders-api"]` | `orders-api` | Có thể qua kiểm tra audience |
| `["orders-api", "analytics-api"]` | `orders-api` | Chỉ chấp nhận nếu chính sách API cho phép multi-audience |
| `"orders"` | `orders-api` | Từ chối, khác chuỗi |
| `"orders-api-v2"` | `orders-api` | Từ chối nếu không cấu hình rõ phiên bản đó |
| `"https://orders.example.test/"` | `orders-api` | Từ chối nếu hợp đồng dùng tên `orders-api` |
| Không có `aud` | `orders-api` | Từ chối theo policy API/OAuth profile |
| `{"name": "orders-api"}` | `orders-api` | Từ chối, sai kiểu dữ liệu |

**So khớp chính xác** là điều quan trọng: không dùng `startsWith("orders")`, `contains("orders")` hay tự bỏ dấu gạch chéo cuối URL để tạo kết quả khớp. Audience là **định danh theo hợp đồng AS–RS**, có thể là URI hoặc chuỗi khác; không nhất thiết là hostname đang nhận request. Nếu định danh resource là URI, hãy so sánh đúng URI đã đăng ký theo policy thay vì suy ra từ header `Host` chưa đáng tin.

### 3.1. Audience không phải issuer, client_id hay scope

| Claim/thuộc tính | Câu hỏi nó trả lời | Vì sao không thay thế `aud`? |
| --- | --- | --- |
| `iss` | Ai đã cấp token? | Một AS có thể cấp token cho hàng chục API |
| `aud` | Token dành cho resource/recipient nào? | Đây là điều kiện gắn token với API nhận |
| `scope` | Token được cấp loại quyền gì? | Hai API có thể đặt scope trùng tên hoặc cùng nhóm chức năng |
| `sub` | Chủ thể được token biểu diễn là ai? | Alice có thể được phép gọi reports nhưng không được phép gọi orders |
| `client_id` | OAuth client nào được cấp token? | Cùng client có thể nhận nhiều token cho các resource khác nhau |
| `azp` (trong profile có dùng) | Authorized party của token theo ngữ nghĩa profile | Thường chỉ client/party, không phải tài nguyên đích |
| `exp`/`nbf` | Token hợp lệ về thời gian không? | Token còn hạn vẫn có thể dành cho API khác |
| `kid`/`alg` | Chọn khóa/thuật toán kiểm tra chữ ký | Chữ ký hợp lệ không định nghĩa resource được phép dùng |

Một token `aud=orders-api` cũng **không có nghĩa** mọi thao tác trên orders đều được phép. Cần cả `scope`, người dùng hoặc machine identity thích hợp, tenant, quyền bản ghi và điều kiện nghiệp vụ.

### 3.2. Multi-audience: hợp lệ không có nghĩa luôn nên dùng

Một JWT có `aud=["orders-api","analytics-api"]` có thể hợp lệ theo JWT. Tuy nhiên, cấp một bearer token dùng được ở **nhiều resource server** làm rộng phạm vi nơi token có giá trị và tăng thiệt hại nếu token bị lộ. Các dịch vụ cần có chính sách phối hợp về scope, ngữ cảnh, dữ liệu và thu hồi.

Thực hành thường an toàn hơn là **mỗi resource nhận một access token có audience hẹp**, nhất là khi resource thuộc nhóm tin cậy khác nhau. Nếu bắt buộc multi-audience, AS phải chủ động cấp các audience theo policy; mỗi API vẫn kiểm tra audience của chính nó và quyền tương ứng.

Không diễn giải `aud` dạng mảng là “chỉ cần có một audience bất kỳ trong danh sách hệ thống”. Resource server phải có **expected audience của chính nó**, không chấp nhận vì token có tên một API khác cũng thuộc tổ chức.

## 4. Vì sao chữ ký, scope và bearer không giải quyết được audience?

### 4.1. JWT ký số vẫn có thể bị sử dụng sai resource

Chữ ký JWS trả lời câu hỏi **token có được ký bởi khóa thuộc issuer tin cậy và có bị chỉnh sửa không?**. Nó không chứng minh token này được phát hành để gọi `orders-api`. Trong ví dụ `reports-api`, chữ ký JWT hoàn toàn đúng vì AS **đúng là đã cấp** token — nhưng cho một resource khác.

Kiểm tra chữ ký và issuer mà bỏ `aud` có thể biến “tất cả token do công ty cấp” thành “token hợp lệ cho tất cả API của công ty”. Đây là **nhầm lẫn về phạm vi tin cậy**, không phải lỗi thuật toán ký.

### 4.2. Scope chỉ rõ loại quyền, không thay địa chỉ resource

Hai API có thể cùng dùng scope `read`, `data.read` hoặc `orders.read` theo quy ước riêng. Ngay cả khi tên scope không trùng nhau, một API có thể mắc lỗi map scope quá rộng hoặc cho phép role tương đương. Audience chặn một lớp tấn công khác: **token có đúng đích đến hay không?**

Một access token có `scope=orders.read` nhưng `aud=billing-api` phải bị `orders-api` từ chối ngay cả khi mọi claims khác đúng. Không được “sửa” `aud` trong token hoặc dùng URL do client gửi để quyết định expected audience.

### 4.3. Bearer token và phát lại qua dịch vụ

Bearer token cho phép bên **đang sở hữu chuỗi token** trình token trong thời hạn hiệu lực. Nếu một token dùng được ở nhiều API do thiếu audience validation, kẻ đánh cắp token của API ít nhạy cảm có thể thử phát lại token ở API nhạy cảm hơn.

Các biện pháp như HTTPS, token TTL ngắn, không ghi token vào log và sender-constrained tokens như DPoP/mTLS rất hữu ích. Tuy nhiên, **sender-constrained token không thay thế audience**: một client hợp lệ nắm private key của mình có thể chứng minh possession với API B nhưng token vẫn chỉ được phát hành cho API A. API B phải kiểm tra audience độc lập.

## 5. Chốt đúng nguồn tin cậy trước khi kiểm tra audience

Resource server cần xác định **issuer nào được quyền phát hành access token cho mình** trước khi tin các claims. Chuỗi kiểm tra điển hình:

~~~mermaid
flowchart TD
    C["Client gửi access token"] --> FORMAT{"Đúng loại access token và định dạng?"}
    FORMAT -->|"Không"| DENY["Từ chối token"]
    FORMAT -->|"Có"| TRUST{"Nguồn xác minh nằm trong trust configuration?"}
    TRUST -->|"Không"| DENY
    TRUST -->|"Có"| VALID{"Signature JWT hoặc introspection hợp lệ?"}
    VALID -->|"Không"| DENY
    VALID -->|"Có"| ISS{"iss đúng issuer?"}
    ISS -->|"Không"| DENY
    ISS -->|"Có"| AUD{"aud chứa expected audience của API?"}
    AUD -->|"Không"| DENY
    AUD -->|"Có"| TIME{"exp/nbf và profile còn hợp lệ?"}
    TIME -->|"Không"| DENY
    TIME -->|"Có"| SCOPE{"Scope đủ cho endpoint?"}
    SCOPE -->|"Không"| FORBID["Từ chối 403"]
    SCOPE -->|"Có"| OWNER{"Có quyền theo tenant và đối tượng?"}
    OWNER -->|"Không"| FORBID
    OWNER -->|"Có"| ALLOW["Cho phép truy cập"]
~~~

Trên thực tế, thư viện có thể xác minh claims và chữ ký theo thứ tự kỹ thuật khác; điều bắt buộc là **không cấp quyền trước khi tất cả phép kiểm tra liên quan hoàn tất**.

### 5.1. JWKS và issuer

Nếu API nhận JWT access token:

1. Cấu hình issuer được chấp nhận, ví dụ `https://auth.example.test`.
2. Dùng metadata đã được kiểm chứng/JWKS thuộc issuer đó; không tải khóa từ `jku` hoặc `x5u` tùy ý trong JWT.
3. Giới hạn thuật toán ký, kiểm tra chữ ký và claims chuẩn; dùng `kid` chỉ để chọn public key trong tập khóa tin cậy.
4. Ràng buộc **đúng audience của API** trước khi tạo principal được dùng cho phân quyền.
5. Kiểm tra loại token (access token thay vì ID token, refresh token hoặc client assertion) theo profile, rồi kiểm tra quyền.

Nếu có nhiều issuer hoặc tenant, danh sách tin cậy và mapping **issuer → JWKS → expected audience/tenant** phải được quản trị. Một `kid` trùng giữa hai issuer không được khiến API dùng sai khóa. Không lấy `iss` chưa xác minh để tải metadata từ một issuer mới chưa được phê duyệt.

### 5.2. Opaque token và introspection

Với opaque access token, resource server gửi token tới **introspection endpoint được cấu hình** của AS có thẩm quyền, xác thực chính mình khi gọi, rồi kiểm tra `active` và các ràng buộc.

Ví dụ phản hồi minh họa:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": ["reports-api"],
  "scope": "data.read",
  "client_id": "client-demo",
  "exp": 1795400300
}
~~~

`orders-api` phải từ chối token này vì `aud=reports-api`, mặc dù `active=true`. Theo RFC 7662, chỉ `active` là trường cốt lõi, các trường còn lại là tùy chọn tùy AS. Nếu AS không trả audience, **không mặc định** `active=true` đồng nghĩa token hợp lệ cho mọi API. Resource server cần một hợp đồng đã kiểm chứng bảo đảm introspection **ràng buộc đúng resource của mình**; nếu không có bảo đảm như vậy thì từ chối token thiếu thông tin cần thiết.

Lưu ý khả năng cache kết quả introspection: cache `active=true` có thể khiến token đã thu hồi tiếp tục được chấp nhận trong TTL cache. Giới hạn cache bởi `exp` và yêu cầu thu hồi, và **fail closed** khi không xác minh được trạng thái.

## 6. AS phát hành token đúng resource: Resource Indicators

Việc phòng chống confused deputy nên bắt đầu từ **cấp phát token**. Authorization server cần biết client đang muốn gọi API nào, sau đó giới hạn token theo resource được phê duyệt. OAuth 2.0 Resource Indicators (RFC 8707) định nghĩa tham số `resource` để client chỉ rõ tài nguyên đích trong những flow mà AS hỗ trợ.

Ví dụ: `sales-dashboard` cần gọi `orders-api` tại định danh resource `https://orders.example.test/`. Một authorization request minh họa:

~~~http
GET /authorize?response_type=code&client_id=sales-dashboard&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&scope=orders.read&resource=https%3A%2F%2Forders.example.test%2F&state=<random-state>&code_challenge=<pkce-challenge>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

Sau khi xác thực và ủy quyền theo policy, client đổi authorization code lấy access token. Nếu AS hỗ trợ resource indicator trong luồng này, kết quả có thể là JWT access token như sau:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": ["https://orders.example.test/"],
  "scope": "orders.read",
  "client_id": "sales-dashboard",
  "exp": 1795400300
}
~~~

Resource server `orders-api` được cấu hình **expected audience = `https://orders.example.test/`** thì có thể qua kiểm tra audience. Nếu dùng định danh audience khác như `orders-api`, AS và RS phải thống nhất mapping; không giả định `resource` trong request luôn xuất hiện nguyên văn trong `aud` của mọi nhà cung cấp.

### 6.1. AS không được cấp audience tùy ý

Tham số `resource` cũng là dữ liệu do client đưa vào, vì vậy AS cần kiểm tra:

- Client có được phép nhận token cho resource đó không?
- Scope yêu cầu có được dùng ở resource đó không?
- Người dùng hoặc service principal có quyền ủy quyền cho resource đó không?
- Resource có được đăng ký và nằm trong danh sách tin cậy của AS không?
- Có cần consent, chính sách tenant hoặc xác thực mạnh hơn không?

Nếu client chỉ được gọi `reports-api` nhưng gửi `resource=https://orders.example.test/`, AS phải áp dụng policy để **từ chối hoặc giới hạn** quyền; chỉ thấy một URI hợp lệ về cú pháp không đủ căn cứ cấp audience đó.

### 6.2. Token riêng cho từng resource

Thay vì một access token chung cho nhiều hệ thống:

~~~text
Token T:
  aud = ["reports-api", "orders-api", "payments-api"]
  scope = ["data.read", "orders.read", "payments.read"]
~~~

có thể thiết kế:

~~~text
Token T1: aud = reports-api   ; scope = reports.read
Token T2: aud = orders-api    ; scope = orders.read
Token T3: aud = payments-api  ; scope = payments.read
~~~

Đây là ví dụ policy mong muốn, không phải yêu cầu giao thức phải có chính xác ba token. Token tách biệt giúp giảm **phạm vi sử dụng lại** sau khi lộ, hỗ trợ kiểm soát scope riêng cho từng API, và cho phép mỗi resource server đối chiếu expected audience đơn giản.

## 7. Service-to-service: không chuyển tiếp token mù quáng

Một mẫu kiến trúc dễ lỗi:

~~~text
Browser → API Gateway → orders-service → payments-service
~~~

Browser gửi access token `aud=orders-api` tới `orders-service`. Khi `orders-service` muốn gọi `payments-service`, việc copy nguyên header `Authorization` sang payments là sai nếu payments chỉ chấp nhận `aud=payments-api`.

### 7.1. Vì sao forward token tạo confused deputy?

Giả sử `payments-service` bỏ qua audience và chấp nhận token user cấp cho `orders-api`. Khi payments dùng credential backend của chính mình để thực hiện thanh toán, token sai resource đã dẫn đến một hành động có đặc quyền. `payments-service` đã bị biến thành deputy thực hiện việc không được ủy quyền cho resource của nó.

Ngược lại, nếu `orders-service` bỏ qua audience, một token được cấp cho một service khác cũng có thể gọi `orders-service`, rồi mượn quyền backend của orders để truy xuất dữ liệu.

**Quy tắc:** Mỗi hop nhận token phải kiểm tra **audience dành cho chính hop/resource đó**. Không thể dựa vào việc token “đã được API Gateway xác minh” nếu gateway không truyền thông tin xác minh và ngữ cảnh tin cậy một cách an toàn, hoặc các service xử lý token với policy khác nhau.

### 7.2. Dùng token exchange khi cần delegation

OAuth 2.0 Token Exchange (RFC 8693) cung cấp khung trao đổi token nếu AS và các bên hỗ trợ. Khi `orders-service` cần gọi `payments-service` thay mặt Alice:

1. `orders-service` nhận và xác minh token **dành cho orders** theo vai trò resource server.
2. `orders-service` xác thực với AS/STS và yêu cầu token mới **dành cho payments**, khai báo delegation/actor và resource đích theo policy.
3. AS quyết định có được cấp hay không dựa trên user, client, actor, scope và resource.
4. `orders-service` sử dụng token mới `aud=payments-api` để gọi payments.
5. `payments-service` kiểm tra issuer, audience của chính nó, scope, danh tính actor/subject và quyền nghiệp vụ liên quan.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice
    participant O as orders-service
    participant AS as AS / STS
    participant P as payments-service
    U->>O: Access token aud=orders-api
    O->>O: Xác minh audience=orders-api và quyền Alice
    O->>AS: Token exchange xin aud=payments-api
    AS->>AS: Kiểm tra subject, actor, client, scope, policy
    AS-->>O: Access token mới aud=payments-api
    O->>P: Gọi API với token mới
    P->>P: Verify aud=payments-api, scope và business policy
    P-->>O: Kết quả được phép
~~~

Ví dụ form request theo mô hình token exchange:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-authentication>
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&
subject_token=<incoming-access-token>&
subject_token_type=urn:ietf:params:oauth:token-type:access_token&
resource=https%3A%2F%2Fpayments.example.test%2F&
scope=payments.create
~~~

Đây là **ví dụ minh họa**: AS phải hỗ trợ grant này, client authentication và resource indicator đúng profile. Việc gửi token đầu vào **không tự bảo đảm** AS sẽ cấp token đích hoặc sẽ giữ ngữ nghĩa actor/subject như mong muốn. Cần quy định contract về delegation, audit, quyền tối đa và cách ánh xạ resource.

Đặc biệt, không được dùng token exchange để âm thầm **nâng quyền Alice** từ `orders.read` thành `payments.admin`. AS và services cần chứng minh yêu cầu token mới có căn cứ ủy quyền hợp lệ.

### 7.3. Dùng client credentials khi thực sự là quyền của service

Nếu `orders-service` gọi payments để thực hiện một tác vụ độc lập thuộc quyền **chính service** (không phải quyền của Alice), có thể dùng client credentials hoặc workload identity để lấy access token cho `payments-api`.

Nhưng khi thao tác được kích hoạt bởi Alice, backend phải giữ và kiểm tra quyền của Alice ở ranh giới thích hợp; không dùng service credential mạnh để bỏ qua kiểm tra authorization của người dùng. Không được trộn lẫn **app-only authorization** với **delegated authorization** chỉ vì cả hai đều gửi bearer token.

## 8. Cấu hình Java/Spring Security kiểm tra audience

Ví dụ sau minh họa API Spring Boot/Spring Security sử dụng JWT access token từ một issuer đã tin. Các class/import phải tương ứng với phiên bản Spring Security được triển khai. Mục tiêu là **ngăn token đúng chữ ký nhưng sai audience** trước khi phân quyền endpoint.

### 8.1. Chỉ cấu hình issuer là chưa đủ

Ví dụ file cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

`issuer-uri` giúp xác định issuer/JWKS và kiểm tra một số điều kiện chuẩn; **đừng giả định** cấu hình này tự biết định danh audience `orders-api` của hệ thống bạn. Cần thêm validation audience theo API và profile token.

### 8.2. JwtDecoder có validator audience

~~~java
@Configuration
@EnableWebSecurity
public class OrdersApiSecurityConfig {

    private static final String ISSUER =
            "https://auth.example.test";
    private static final String JWKS_URI =
            "https://auth.example.test/oauth2/jwks";
    private static final String EXPECTED_AUDIENCE =
            "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(JWKS_URI)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(EXPECTED_AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            OAuth2Error error = new OAuth2Error(
                    "invalid_token",
                    "Access token khong danh cho orders-api",
                    null);
            return OAuth2TokenValidatorResult.failure(error);
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standard, audienceValidator));
        return decoder;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll());

        http.oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

**Cách đọc ví dụ:**

1. `JWKS_URI` là nguồn public key được cấu hình từ issuer tin cậy; không sử dụng `jku` do token tự đưa vào.
2. Chỉ chấp nhận thuật toán RS256 theo giả định của ví dụ; chính sách thuật toán thực tế phải khớp AS.
3. Validator chuẩn kiểm tra issuer và các điều kiện thời gian; `audienceValidator` bắt buộc token chứa `orders-api` bằng so khớp **giá trị nguyên vẹn**.
4. Khi xác thực thành công, authorization rule yêu cầu `SCOPE_orders.read` hoặc `SCOPE_orders.write` theo endpoint.
5. Domain/service layer vẫn phải kiểm tra user, role, tenant và quyền truy cập **đơn hàng cụ thể**.

Ví dụ này chưa bao quát toàn bộ cấu hình production: cần kiểm tra token profile (`typ: at+jwt` hoặc quy ước tương ứng), giới hạn format, chính sách key rotation, xử lý multi-issuer khi có và exception mapping. `jwt.getAudience()` là danh sách audience đã được decoder parse; ứng dụng không được đọc trực tiếp chuỗi chưa xác minh để cấp quyền.

### 8.3. Cách tiếp cận bằng issuer-uri và audience

Một số phiên bản Spring Boot/Spring Security hỗ trợ cấu hình audience bằng property, hoặc có API `JwtAudienceValidator`. Nếu dùng cơ chế tích hợp, hãy kiểm tra tài liệu **phiên bản thực tế** để bảo đảm nó được kích hoạt đúng; điều kiện cần đạt không đổi:

~~~text
trustedIssuer == token.iss
AND signatureValid
AND "orders-api" is exactly one of token.aud
AND token is a valid access token
AND token is not expired
AND scope and business authorization are sufficient
~~~

Tránh viết một filter riêng chỉ `Base64.decode(payload)` rồi lấy `aud` để tạo principal: payload chưa được verify hoàn toàn có thể bị sửa. Audience validator phải nằm trong **đường xác minh token đáng tin**, trước khi phân quyền.

### 8.4. Với opaque token trong Spring Security

Spring Security resource server có thể dùng introspection bằng cấu hình minh họa:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: EXTERNAL_SECRET_REFERENCE
~~~

`EXTERNAL_SECRET_REFERENCE` là placeholder, cần thay bằng secret được tải an toàn từ secret manager/biến môi trường hoặc cơ chế quản lý khóa phù hợp. Cấu hình introspection **chưa tự chứng minh** AS đã gắn token với `orders-api`.

Sau khi nhận phản hồi introspection đáng tin, API phải kiểm tra audience/resource binding trong response theo hợp đồng của AS. Pseudocode:

~~~text
attributes = trustedIntrospector.introspect(bearerToken)
if attributes.active is not true:
    reject
if "orders-api" not in strictlyValidatedAudience(attributes):
    reject
if tokenExpiredOrWrongPurpose(attributes):
    reject
principal = createVerifiedPrincipal(attributes)
authorizeScopeAndOrderOwnership(principal, request)
~~~

Đây chỉ là **pseudocode về policy**. Kiểu `active`, cách Spring Security cung cấp `OAuth2AuthenticatedPrincipal` và extension point cho custom `OpaqueTokenIntrospector` tùy phiên bản. Nếu AS không trả `aud`, phải có bảo đảm tương đương rằng introspection được giới hạn cho resource này; không tự cho phép chỉ vì `active=true`.

### 8.5. 401 và 403 khi sai audience

Token có chữ ký hợp lệ nhưng `aud` không khớp là **token không hợp lệ đối với resource server này**, nên thường trả `401 Unauthorized` và `WWW-Authenticate: Bearer error="invalid_token"` theo hợp đồng OAuth 2.0 Bearer (RFC 6750).

Ngược lại, token có audience đúng, còn hiệu lực nhưng thiếu `orders.write` thì thường trả `403 Forbidden` với `error="insufficient_scope"`. Phân biệt hai tình huống giúp client biết cần xin **token cho resource khác** hay cần **quyền khác**.

Không đưa toàn bộ token, claims nhạy cảm, nội dung private key hoặc thông tin cấu hình AS vào error response/log.

## 9. Những biến thể của confused deputy trong thực tế

### 9.1. API Gateway xác minh chung, backend bỏ qua audience

Kiến trúc:

~~~text
Client → API Gateway → orders-api
                     → billing-api
                     → reports-api
~~~

Gateway sử dụng một cấu hình JWT decoder chung. Nó chỉ kiểm tra `iss`, chữ ký và `exp`, rồi chuyển tiếp request tới API phía sau. Nếu backend tin mọi request qua gateway đã được xác thực đúng resource, một token `aud=reports-api` có thể tới `orders-api` với identity được gateway xác nhận **nhưng sai mục đích**.

Có hai cách tổ chức bảo vệ hợp lệ:

- **Mỗi resource server tự kiểm tra access token** với expected audience của chính nó, cùng issuer, scope và policy.
- **Gateway thực hiện xác minh audience theo route** và truyền ngữ cảnh đã xác thực tới backend qua ranh giới được bảo vệ, với xác thực gateway–backend, header chống giả mạo và chính sách rõ về service nào được phép tin gateway.

Trường hợp thứ hai đòi hỏi cấu hình chặt và kiểm thử toàn tuyến; không đơn giản chuyển tiếp `X-User` hoặc `X-Audience` do client có thể tự gửi. Nếu backend còn nhận bearer token trực tiếp, nó vẫn phải xử lý token theo hợp đồng riêng.

### 9.2. Môi trường development và production dùng chung issuer

Giả sử token môi trường kiểm thử được cấp từ một AS chung:

~~~json
{
  "iss": "https://auth.example.test",
  "aud": ["orders-api-dev"],
  "scope": "orders.read"
}
~~~

Nếu production `orders-api` chỉ kiểm tra issuer/scope, token từ dev có thể bị dùng ở production. Nên tách **audience**, client permissions, issuer hoặc tổ hợp các ranh giới thích hợp giữa môi trường. Một request production chỉ chấp nhận đúng audience production, dù token dev có chữ ký cùng AS.

### 9.3. Nhiều tenant dùng chung audience

Audience `orders-api` chỉ xác định **dịch vụ nhận**. Nếu cùng một API phục vụ `tenant-a` và `tenant-b`, cả hai có thể nhận token mang `aud=orders-api`. Vì vậy phải kiểm tra thêm issuer/tenant, account và quyền của request với tài nguyên.

Ví dụ token:

~~~json
{
  "iss": "https://auth.example.test",
  "aud": ["orders-api"],
  "sub": "alice",
  "tenant_id": "tenant-a",
  "scope": "orders.read"
}
~~~

không đủ để đọc đơn hàng của `tenant-b`. Đây là **cross-tenant authorization**, một lớp khác ngoài audience validation. Nếu các tenant dùng issuer khác nhau, cần tách cả trust configuration của issuer để tránh tin nhầm token/khóa của tenant khác.

### 9.4. Nhầm ID token với access token

Trong OIDC, ID token thường có `aud` là **client ID** nhận kết quả đăng nhập, ví dụ:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": ["web-dashboard"],
  "exp": 1795400300
}
~~~

Nếu `orders-api` chỉ kiểm tra chữ ký và `sub`, nó có thể vô tình chấp nhận ID token do client gửi. Đây là **token type confusion**, có liên hệ với cùng nguyên nhân: API không kiểm tra token có được phát hành **cho mình và cho mục đích access token** không.

Để phòng vệ, resource server cần cả `aud` phù hợp và token profile hợp lệ (ví dụ RFC 9068 `typ=at+jwt` khi AS hỗ trợ/tuân theo profile). Không chấp nhận ID token, refresh token hay JWT client assertion thay cho access token.

### 9.5. Một token nhiều audience nhưng scope không tách

Giả sử AS cấp:

~~~json
{
  "aud": ["reports-api", "orders-api"],
  "scope": "data.read"
}
~~~

Cả hai API có thể thấy audience của mình và scope `data.read`. Nếu ngữ nghĩa quyền khác nhau giữa hai API, AS và RS đã tạo ra quyền mơ hồ. Multi-audience có thể là thiết kế có chủ đích, nhưng mỗi API phải biết **scope nào áp dụng cho mình**, AS phải giới hạn quyền cấp và client phải được phép gọi tất cả resource đó. Với hệ thống nhạy cảm, ưu tiên token riêng mỗi API để tránh quyền bị mở rộng không chủ ý.

## 10. Token theft, replay và revocation trong lỗi audience

Lỗi audience khiến tác động của một bearer token bị đánh cắp **lan ra nhiều API hơn** so với resource ban đầu. Một token `aud=reports-api` bị lộ từ log reports đáng lẽ chỉ có giá trị ở reports; nếu orders bỏ qua audience, kẻ cầm token có thể dùng token đó ở orders trong thời gian hiệu lực.

| Biện pháp | Ngăn điều gì? | Giới hạn |
| --- | --- | --- |
| **Audience validation** | Không cho token của resource A dùng ở B | Không ngăn token bị lộ được dùng ngay tại A |
| **Scope tối thiểu** | Giảm thao tác mà token có thể thực hiện | Scope đúng vẫn cần object-level authorization |
| **TTL ngắn** | Giảm thời gian replay token bị đánh cắp | Không ngăn replay ngay sau khi token lộ |
| **HTTPS và secret hygiene** | Giảm khả năng token bị chặn/lộ qua kênh không an toàn | Không bảo vệ khi client hoặc log đã bị chiếm quyền |
| **Introspection / denylist** | Có thể từ chối token đã thu hồi trước `exp` | Phụ thuộc chính sách cache, khả năng AS và RS |
| **mTLS certificate-bound / DPoP** | Yêu cầu proof khóa/chứng chỉ đi cùng token | Bên có đúng key vẫn phải bị giới hạn audience |
| **Kiểm tra tenant/ACL** | Chặn truy cập bản ghi và miền dữ liệu không được phép | Không sửa được lỗi nhầm resource nếu API khác vẫn bỏ qua audience |

**Thu hồi token** và **kiểm tra audience** giải quyết hai câu hỏi khác nhau. Một JWT bị thu hồi có thể cần denylist hoặc kiểm tra trạng thái bổ sung; một JWT còn hiệu lực vẫn phải bị từ chối nếu audience sai. Một opaque token `active=true` cũng phải qua kiểm tra resource binding.

Với DPoP (RFC 9449), proof ràng buộc method/URI và khóa của client, giúp giảm khả năng phát lại token đơn thuần. Tuy nhiên, client được cấp token cho resource A có thể sở hữu private key hợp lệ và tạo proof để gọi B. Vì vậy resource B phải **tiếp tục xác minh audience B**.

## 11. Bộ kiểm thử phát hiện audience confusion

Thiết lập test AS và hai API `reports-api`, `orders-api`. Tạo token từ **khóa test hợp lệ** để bảo đảm thử nghiệm không chỉ thất bại do chữ ký; giữ issuer, scope và chữ ký đúng khi muốn cô lập kiểm tra audience.

| ID | Token hoặc tình huống | Kỳ vọng tại `orders-api` |
| --- | --- | --- |
| A01 | `iss` đúng, `aud=orders-api`, scope đủ, còn hạn | Cho qua audience, tiếp tục policy |
| A02 | `iss` đúng, `aud=reports-api`, scope giống orders, còn hạn | **Từ chối** |
| A03 | `aud=billing-api`, chữ ký hợp lệ từ AS chung | **Từ chối** |
| A04 | Không có `aud` trong JWT access token | **Từ chối** |
| A05 | `aud=orders`, API kỳ vọng `orders-api` | **Từ chối**, không prefix match |
| A06 | `aud=orders-api-v2`, API chỉ tin `orders-api` | **Từ chối**, không substring match |
| A07 | `aud=https://orders.example.test/`, kỳ vọng `orders-api` | **Từ chối** nếu không có mapping allowlist |
| A08 | `aud=["reports-api","orders-api"]` | Chỉ qua audience khi policy cho phép multi-audience |
| A09 | `aud=["reports-api","billing-api"]` | **Từ chối** |
| A10 | `aud` là number, object hoặc mảng có kiểu sai | **Từ chối** |
| A11 | `iss` sai, `aud=orders-api` | **Từ chối** |
| A12 | Token bị thay chữ ký, `aud=orders-api` | **Từ chối** |
| A13 | ID token `aud=web-dashboard` dùng gọi orders | **Từ chối** |
| A14 | Token `aud=orders-api` nhưng `exp` đã qua | **Từ chối** |
| A15 | Token `aud=orders-api` nhưng thiếu `orders.read` | **Từ chối thao tác** (thường 403) |
| A16 | Token aud đúng/scope đúng nhưng object sai tenant | **Từ chối theo policy** |
| A17 | Token `aud=orders-api-dev` gửi lên production orders | **Từ chối** |
| A18 | Token của issuer/tenant khác có cùng `kid` và `aud` | **Từ chối** nếu issuer không được phê duyệt |
| A19 | Opaque token `active=true` nhưng `aud=reports-api` | **Từ chối** |
| A20 | Opaque token không có `aud` và AS không ràng buộc resource | **Từ chối** |
| A21 | Introspection timeout/TLS lỗi | **Không cấp quyền** (fail closed) |
| A22 | Token `aud=orders-api` từ AS đã tin, scope đúng, user đúng tenant | **Cho phép** request hợp lệ |
| A23 | Gateway chấp nhận `aud=reports-api` nhưng route chuyển sang orders | **Từ chối** ở route/backend theo kiến trúc tin cậy |
| A24 | DPoP/mTLS proof hợp lệ nhưng `aud=reports-api` | **Từ chối** ở orders dù proof đúng |

### 11.1. Cách kiểm thử có ý nghĩa

Để chứng minh lỗi **bỏ qua audience** đã được chặn, hãy đặt hai token cạnh nhau:

~~~json
{
  "token_for_orders": {
    "iss": "https://auth.example.test",
    "aud": ["orders-api"],
    "scope": "orders.read"
  },
  "token_for_reports": {
    "iss": "https://auth.example.test",
    "aud": ["reports-api"],
    "scope": "orders.read"
  }
}
~~~

Hai object là **mô tả test claims**, không phải token phát hành thật. Tạo JWT có chữ ký hợp lệ bằng khóa test và các claims thời gian đúng cho từng trường hợp; token `token_for_orders` phải vượt qua xác minh audience, còn `token_for_reports` phải bị từ chối. Nếu cả hai cùng thất bại do một lỗi cấu hình issuer/JWKS, test **chưa chứng minh** audience validator hoạt động.

Kiểm tra thêm hành vi phụ: request bị từ chối **không được gọi database hoặc backend có đặc quyền**, không ghi toàn bộ bearer token vào log và không tự gửi token sang API khác khi redirect. Với hệ thống đa service, kiểm thử cả đường qua gateway và gọi trực tiếp backend nếu backend có thể được truy cập.

### 11.2. Các phản hồi lỗi mong muốn

Ví dụ access token sai audience:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
Cache-Control: no-store
~~~

Ví dụ token đúng audience nhưng thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders.write"
Cache-Control: no-store
~~~

Không nên công khai danh sách issuer tin cậy, cấu trúc khóa hoặc nội dung token trong thông điệp lỗi. Với sự cố introspection và JWKS khiến API không thể xác minh, cần phân biệt lỗi vận hành với token thật sự không hợp lệ khi chọn HTTP status; dù dùng mã nào, **không cho phép truy cập khi thiếu bằng chứng**.

## 12. Checklist thiết kế và câu hỏi tự kiểm tra

Trước khi triển khai resource server, kiểm tra:

1. **Trust bootstrap:** API có danh sách issuer, JWKS hoặc introspection endpoint được phép; không tin issuer/key URL do token tự chọn?
2. **Audience:** Expected audience có được cấu hình riêng cho API/resource và kiểm tra chính xác ở mọi request?
3. **Token profile:** API chỉ nhận access token đúng mục đích; từ chối ID token, refresh token hoặc assertion?
4. **AS issuance:** AS chỉ cấp token cho resource client được phép; có hỗ trợ resource indicator/token exchange nếu kiến trúc cần?
5. **Scope/permission:** Có kiểm tra scope theo action và kiểm tra tenant/ACL trên từng bản ghi sau khi xác minh token?
6. **Service chain:** Service A gọi B bằng token đúng audience B; có cơ chế delegation hoặc client credentials được kiểm soát?
7. **Multi-issuer và multi-audience:** Có policy allowlist/mapping rõ và không dùng chung `kid`/role/tenant sai ngữ cảnh?
8. **Opaque token:** Introspection có bảo đảm token dành cho đúng resource, không chỉ trả `active=true`?
9. **Security operations:** Có giới hạn TTL, bảo vệ token, rotation/revocation và fail closed khi không thể xác minh?
10. **Tests:** Có test âm cùng issuer/chữ ký/scope nhưng audience sai, cùng test dương để tránh API luôn từ chối mọi token?

### Câu hỏi 1

**Token có chữ ký RS256 đúng, `iss` được tin cậy, `scope=orders.read` nhưng `aud=reports-api`. `orders-api` có nên chấp nhận không?**

Không. Chữ ký chỉ bảo đảm issuer đã ký token; audience cho biết token dành cho reports. `orders-api` phải từ chối.

### Câu hỏi 2

**Nếu một token có `aud=["reports-api","orders-api"]`, có phải lúc nào `orders-api` cũng chấp nhận?**

Không. Nó có thể qua kiểm tra audience nếu multi-audience được policy AS/RS cho phép; API vẫn phải xác minh issuer, chữ ký/trạng thái, thời hạn, token profile, scope và quyền nghiệp vụ. Một số API có thể chủ động từ chối token multi-audience theo chính sách hẹp.

### Câu hỏi 3

**`orders-service` có thể gửi nguyên token `aud=orders-api` đến `payments-service` không?**

Không nên. `payments-service` phải yêu cầu token dành cho mình; `orders-service` có thể dùng token exchange/delegation hoặc nhận token bằng quyền chính service theo thiết kế có kiểm soát.

### Câu hỏi 4

**Opaque token có `active=true` từ AS chung có đủ để mọi API chấp nhận không?**

Không. Phải có audience hoặc bảo đảm resource binding rõ ràng từ AS/introspection, đồng thời kiểm tra quyền và thời hạn.

### Câu hỏi 5

**Nếu API đã sử dụng mTLS hoặc DPoP, có thể bỏ kiểm tra audience không?**

Không. Bằng chứng sở hữu khóa giúp xác định người gửi được ràng buộc, nhưng không chứng minh token được cấp cho **resource server nhận request**.

### Câu hỏi 6

**Đâu là khác biệt giữa token substitution và confused deputy?**

Token substitution là sử dụng token không dành cho ngữ cảnh hiện tại. Nó có thể dẫn tới confused deputy khi một service/RS được trao quyền bị lừa dùng quyền của mình để làm việc mà kẻ tấn công không được ủy quyền. Cả hai đều cần ranh giới audience và authorization rõ ràng.

## Tài liệu chuẩn để đọc thêm

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa `aud`, `iss`, `exp` và các claims JWT.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): vai trò authorization server, client, resource server và quyền được cấp.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer access token, lỗi `invalid_token`/`insufficient_scope`.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): xin token dành cho resource cụ thể.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): cấp token mới cho resource đích và delegation theo policy.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token, audience, token type và claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): phòng cross-JWT confusion và kiểm tra ngữ cảnh của token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác thực trạng thái opaque token và metadata của token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ OAuth access token, audience restriction và các biện pháp token security.
- [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705), [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access tokens.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): phân biệt ID token của OIDC client và access token dành cho API.

**Điểm cần ghi nhớ:** Resource server không được xem một token “đúng chữ ký, đúng issuer, đúng scope” là hợp lệ **cho chính mình** nếu token không chứa audience dành cho resource đó. Bỏ qua audience mở đường cho cross-resource token substitution và có thể khiến một service trở thành confused deputy. Phòng vệ đầy đủ gồm **issuer/JWKS hoặc introspection đáng tin + kiểm tra audience chính xác + đúng loại access token + scope + quyền trên tài nguyên**, đồng thời sử dụng token riêng cho từng resource hoặc token exchange khi cần gọi giữa các service.

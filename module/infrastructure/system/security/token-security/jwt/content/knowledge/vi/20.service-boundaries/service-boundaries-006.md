# Ủy quyền qua nhiều dịch vụ và bảo toàn ngữ cảnh chủ thể

## 1. Vì sao ủy quyền xuyên dịch vụ khó hơn xác thực một request?

Trong kiến trúc nhiều dịch vụ, một request thường đi qua nhiều thành phần trước khi hoàn thành nghiệp vụ. Ví dụ người dùng yêu cầu tạo đơn hàng; API gateway chuyển request tới order service, order service gọi inventory service để giữ hàng, rồi gọi payment service để thanh toán.

Mỗi dịch vụ cần biết ít nhất hai điều:

- **Ai là chủ thể (subject)?** Người dùng hoặc principal mà hành động đang được thực hiện thay mặt.
- **Ai là actor?** Client hoặc dịch vụ đang thực hiện hành động tại chặng hiện tại.

Nếu chỉ truyền một chuỗi user ID qua header, dịch vụ downstream không có bằng chứng đáng tin cậy rằng user ID đó đã được xác thực. Nếu chỉ truyền danh tính service, downstream có thể biết order service đang gọi nhưng không biết thao tác đó thuộc yêu cầu của người dùng nào và người dùng có quyền gì.

Nếu truyền nguyên access token của người dùng qua mọi dịch vụ, token có thể có audience quá rộng, scope lớn hơn nhu cầu và thời hạn dài hơn thời gian cần thiết. Một dịch vụ bị xâm nhập khi đó có thể sử dụng token ở nhiều nơi khác.

Thiết kế ủy quyền xuyên dịch vụ phải bảo toàn ngữ cảnh chủ thể, ghi nhận actor, giới hạn quyền theo từng chặng và giữ ranh giới tin cậy rõ ràng. **Không được làm mất danh tính người dùng, cũng không được biến danh tính người dùng thành quyền vô hạn cho mọi dịch vụ.**

Bài thuộc chương **Ranh giới dịch vụ** của module **Security - JSON Web Token (JWT)**. Nội dung áp dụng chung cho OAuth 2.0, JWT, API gateway, microservices và hệ thống xử lý nền; không phụ thuộc Java hay framework.

## 2. Subject và actor là hai danh tính khác nhau

### 2.1. Subject: người mà quyền đang đại diện

Subject là principal mà access token thể hiện quyền truy cập. Trong luồng người dùng đăng nhập, subject thường là người dùng cuối. Trong một số luồng hệ thống, subject có thể là một workload hoặc service principal.

Ví dụ:

- Người dùng `user-42` yêu cầu xem đơn hàng của mình.
- Dịch vụ `order-service` xử lý yêu cầu đó.
- Dịch vụ `inventory-service` kiểm tra tình trạng hàng.

Ở đây, subject của yêu cầu nghiệp vụ là `user-42`, dù inventory service không trực tiếp nhận request từ trình duyệt.

### 2.2. Actor: thành phần đang thực hiện hành động

Actor là client hoặc dịch vụ đang thực hiện thao tác tại một thời điểm. Trong ví dụ:

- Chặng đầu: actor có thể là `web-client` hoặc BFF.
- Chặng tiếp theo: actor là `order-service`.
- Chặng sau nữa: actor là `inventory-service` nếu nó tiếp tục gọi một dịch vụ khác.

Actor không nhất thiết là subject. Một dịch vụ có thể hành động thay mặt người dùng mà không trở thành người dùng đó.

### 2.3. Vì sao không nên ghi đè subject bằng service identity?

Nếu order service gọi inventory service bằng credential của chính nó và downstream chỉ thấy `sub=order-service`, ngữ cảnh người dùng `user-42` đã biến mất. Inventory service không thể áp dụng chính sách dựa trên người dùng, tenant hoặc quyền sở hữu dữ liệu.

Ngược lại, nếu order service chỉ chuyển tiếp access token của user mà không có thông tin actor, hệ thống có thể mất khả năng audit dịch vụ nào đã thực hiện thao tác. Khi điều tra, khó phân biệt người dùng trực tiếp gọi API với một dịch vụ nội bộ đang sử dụng quyền thay mặt họ.

Mô hình tốt giữ riêng subject và actor, đồng thời xác định rõ quyền nào thuộc người dùng, quyền nào thuộc dịch vụ.

## 3. Ngữ cảnh ủy quyền cần bảo toàn qua các chặng

### 3.1. Những thông tin quan trọng

Một ngữ cảnh ủy quyền xuyên dịch vụ thường bao gồm:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Subject | Chủ thể mà quyền đại diện | `user-42` |
| Actor/client | Thành phần đang hành động | `order-service` |
| Issuer | Hệ thống phát hành token | `https://identity.example` |
| Audience/resource | Dịch vụ được phép nhận token | `https://inventory.internal` |
| Scope/permission | Quyền được cấp cho chặng này | `inventory.reserve` |
| Tenant | Phạm vi tổ chức/khách hàng | `tenant-7` |
| Token/session ID | Định danh để audit hoặc thu hồi | `jti`, session ID |
| Thời hạn | Khoảng thời gian credential có hiệu lực | `exp`, `nbf` |
| Delegation chain | Chuỗi actor đã tham gia | gateway → order → inventory |
| Request context | Mã tương quan nghiệp vụ | correlation ID |

Không phải mọi thông tin đều cần nằm trong JWT. Chỉ đưa claims cần thiết để downstream xác minh và quyết định quyền. Correlation ID, trace ID và dữ liệu quan sát thường nên truyền qua cơ chế tracing riêng.

### 3.2. Bảo toàn subject không có nghĩa giữ nguyên mọi quyền

Subject có thể vẫn là `user-42` qua nhiều chặng, nhưng scope cần giảm theo nhiệm vụ:

~~~text
User request:
  subject = user-42
  requested action = create order

Order service:
  needs orders.create

Inventory service:
  needs inventory.reserve

Payment service:
  needs payments.authorize
~~~

Inventory service không cần quyền `payments.authorize`. Payment service không cần quyền đọc toàn bộ hồ sơ người dùng. Việc giữ nguyên subject giúp chính sách downstream hiểu ai được đại diện; việc giới hạn scope giúp mỗi dịch vụ chỉ làm phần việc được giao.

### 3.3. Context không phải credential

Một object context nội bộ hoặc header như `X-User-Id`, `X-Tenant-Id`, `X-Actor-Service` có thể hữu ích cho logging và routing. Nhưng nếu client có thể tự gửi hoặc sửa, các giá trị đó không phải bằng chứng xác thực.

Chỉ sử dụng thông tin danh tính để ra quyết định bảo mật khi nó đến từ token đã được xác minh, token exchange do authorization server tin cậy phát hành, assertion được ký và xác minh theo hợp đồng rõ ràng, hoặc kênh workload identity được xác thực và ràng buộc với service.

Không biến header tương quan hoặc metadata tracing thành nguồn quyền.

## 4. Kiến trúc ví dụ: từ người dùng tới nhiều dịch vụ

### 4.1. Luồng nghiệp vụ

Giả sử một ứng dụng thương mại điện tử có các thành phần:

~~~text
Browser
   |
   v
API Gateway / BFF
   |
   v
Order Service
   |-------------------|
   v                   v
Inventory Service   Payment Service
   |                   |
   v                   v
Warehouse Service   Payment Provider
~~~

Người dùng `user-42` tạo đơn hàng. Order service cần giữ hàng và thanh toán. Mỗi dịch vụ downstream có ranh giới dữ liệu và quyền riêng:

- Order service có thể tạo đơn cho subject hợp lệ.
- Inventory service chỉ được giữ số lượng hàng cho đơn đó.
- Payment service chỉ được authorize khoản tiền theo order và policy.
- Warehouse service chỉ được tạo yêu cầu xuất kho sau khi điều kiện nghiệp vụ đạt.

### 4.2. Danh tính và quyền theo từng chặng

| Chặng | Subject | Actor | Audience | Quyền cần thiết |
| --- | --- | --- | --- | --- |
| Browser → Gateway | `user-42` | `web-client` | `orders-api` | `orders.create` |
| Gateway → Order | `user-42` | `api-gateway` hoặc BFF | `order-service` | `orders.create` |
| Order → Inventory | `user-42` | `order-service` | `inventory-service` | `inventory.reserve` |
| Order → Payment | `user-42` | `order-service` | `payment-service` | `payments.authorize` |
| Inventory → Warehouse | `user-42` nếu nghiệp vụ cần giữ subject | `inventory-service` | `warehouse-service` | `warehouse.pick` |

Subject có thể được bảo toàn xuyên suốt, nhưng audience và scope thay đổi theo dịch vụ nhận token. Actor cũng thay đổi theo từng chặng.

### 4.3. Dịch vụ phải xác minh độc lập

Mỗi downstream service phải xác minh token hoặc credential được gửi tới nó. Không được giả định gateway đã xác minh thì mọi service phía sau không cần xác minh, request đến từ mạng nội bộ thì mặc nhiên đáng tin, token có chữ ký hợp lệ thì audience nào cũng chấp nhận được, hoặc một service upstream có quyền gọi mọi API downstream.

Gateway là một lớp kiểm soát quan trọng, nhưng không thay thế xác thực và phân quyền tại ranh giới từng resource server.

## 5. Token forwarding và token exchange

### 5.1. Token forwarding là gì?

Token forwarding là việc dịch vụ upstream chuyển tiếp access token hiện có tới dịch vụ downstream:

~~~text
Client -- user access token --> Order Service
Order Service -- same token --> Inventory Service
~~~

Cách này đơn giản và có thể phù hợp khi token ban đầu được phát hành rõ ràng cho nhiều resource cần nhận nó. Tuy nhiên, cần kiểm tra:

- `aud` có bao gồm downstream service không?
- Scope có giới hạn đúng nhu cầu downstream không?
- Downstream có chấp nhận cùng token profile và issuer không?
- Token có ràng buộc sender hoặc client không?
- Token có bị lộ tới service không cần quyền đó không?

Nếu token chỉ có audience `orders-api`, inventory service không được chấp nhận nó chỉ vì order service chuyển tiếp. Không sửa claim `aud` trong token đã ký; muốn thay đổi audience phải có token mới được issuer tin cậy phát hành.

### 5.2. Rủi ro của việc chuyển tiếp nguyên token

Token forwarding rộng có thể dẫn tới token có audience quá rộng và trở thành credential dùng ở nhiều dịch vụ, scope lớn hơn quyền downstream cần, nhiều service có thể dùng lại token trong suốt thời hạn còn lại, khó xác định actor thực hiện hành động, một service bị xâm nhập có thể phát lại token ở các resource khác, hoặc claims/dữ liệu không cần thiết bị phân phối rộng.

Không nên xem token người dùng là “context header” có thể phát tán tự do.

### 5.3. Token exchange là gì?

**OAuth 2.0 Token Exchange** theo RFC 8693 cho phép một client gửi token hiện có tới authorization server để nhận một token khác phù hợp với resource, audience hoặc mục đích mới.

~~~text
User access token for Order API
            |
            v
      Order Service
            |
            | subject token + authenticated actor
            v
   Authorization Server
            |
            | issue token for Inventory API
            v
  Inventory-scoped access token
~~~

Token exchange giúp authorization server áp dụng policy tập trung:

- Xác thực subject token và actor/client.
- Kiểm tra actor có được phép đại diện subject hay không.
- Xác định audience/resource đích.
- Giảm scope theo công việc downstream.
- Thiết lập thời hạn phù hợp.
- Ghi nhận actor trong delegation context khi profile hỗ trợ.

Token exchange không tự động làm hệ thống an toàn. Authorization server phải có policy chặt chẽ; nếu nó cho phép bất kỳ service nào đổi token thành quyền tùy ý, token exchange chỉ chuyển rủi ro sang một endpoint trung tâm.

### 5.4. Khi nào chọn cách nào?

| Tiêu chí | Forward token hiện có | Token exchange |
| --- | --- | --- |
| Đơn giản triển khai | Thường đơn giản hơn | Cần authorization server hỗ trợ |
| Audience downstream | Token phải có sẵn audience phù hợp | Có thể phát hành token cho audience đích theo policy |
| Scope | Dùng scope hiện tại, có thể quá rộng | Có thể thu hẹp scope theo chặng |
| Actor chain | Có thể thiếu hoặc không rõ | Có thể biểu diễn actor/delegation rõ hơn |
| Thời hạn | Dùng thời hạn token gốc | Có thể cấp thời hạn ngắn hơn |
| Thu hồi và audit | Phụ thuộc token gốc và log | Có thể quản lý theo token exchange và policy |
| Phù hợp | Token đã được thiết kế cho đúng resource set | Nhiều service, audience riêng và delegation rõ ràng |

Chọn forwarding chỉ khi token được phát hành có chủ đích cho resource nhận nó. Khi cần đổi audience, giảm quyền hoặc ghi nhận actor, token exchange thường phù hợp hơn.

## 6. OAuth 2.0 Token Exchange theo RFC 8693

### 6.1. Các thành phần của một token exchange request

RFC 8693 định nghĩa grant type:

`urn:ietf:params:oauth:grant-type:token-exchange`

Request có thể bao gồm subject_token, subject_token_type, actor_token, actor_token_type, requested_token_type, audience hoặc resource đích, và scope mong muốn trong token mới.

Ví dụ minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <client-authentication>
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=<USER_ACCESS_TOKEN>
&subject_token_type=urn:ietf:params:oauth:token-type:access_token
&requested_token_type=urn:ietf:params:oauth:token-type:access_token
&audience=https%3A%2F%2Finventory.internal
&scope=inventory.reserve
~~~

Đây là request khái niệm. Client authentication, token type, audience, scope và cách gửi actor token phải tuân theo cấu hình và policy của authorization server. Không phải authorization server nào cũng hỗ trợ mọi tham số hoặc mọi loại token.

### 6.2. Authorization server phải kiểm tra gì?

Trước khi phát hành token mới, authorization server cần:

1. Xác thực client/service đang yêu cầu exchange.
2. Xác minh subject token: issuer, chữ ký/introspection, thời hạn, audience và trạng thái.
3. Xác minh actor token nếu request có cung cấp.
4. Kiểm tra actor có quyền hành động thay mặt subject trong ngữ cảnh này.
5. Kiểm tra resource/audience đích đã đăng ký và được phép.
6. Tính scope giao nhau giữa quyền subject, quyền actor, policy client và nhu cầu resource.
7. Giới hạn thời hạn và loại token được phát hành.
8. Ghi nhận kết quả và delegation context để audit.

Không phát hành token chỉ vì subject token hợp lệ. Một user token hợp lệ không có nghĩa mọi service đều được phép sử dụng quyền của user.

### 6.3. Token mới cần có gì?

Token mới phải được phát hành theo access-token profile mà resource server hiểu. Một token có thể chứa:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://inventory.internal",
  "client_id": "order-service",
  "scope": "inventory.reserve",
  "iat": 1760000000,
  "exp": 1760000300,
  "jti": "exchanged-token-unique-id",
  "act": {
    "sub": "order-service"
  }
}
~~~

Đây là ví dụ minh họa claims, không phải mẫu bắt buộc cho mọi triển khai. `client_id` và `act` có ngữ nghĩa phụ thuộc profile; resource server phải biết chính xác issuer và profile nào phát hành token. `sub` giữ subject, `act` thể hiện actor theo mô hình RFC 8693.

### 6.4. Token exchange không phải đăng nhập lại người dùng

Token exchange thường là thao tác server-to-server dựa trên một subject token đã có và quyền của client đang exchange. Nó không có nghĩa service được phép giả mạo người dùng hoặc tự tạo `sub` tùy ý.

Nếu subject token không hợp lệ, hết hạn hoặc không đủ quyền, authorization server phải từ chối exchange. Nếu actor không được phép đại diện subject, cũng phải từ chối.

## 7. Biểu diễn subject và actor trong JWT

### 7.1. Claim sub

Claim `sub` xác định subject của token theo issuer và token profile. Với delegated access token, subject thường vẫn là người dùng cuối mà quyền đại diện, dù request đang được service xử lý.

Không nên thay `sub` thành tên service ở mỗi hop nếu mục tiêu là bảo toàn người dùng. Nếu service cần credential cho quyền riêng của chính nó, hãy dùng một token service identity riêng hoặc một mô hình token có subject/actor được định nghĩa rõ.

### 7.2. Claim act trong RFC 8693

RFC 8693 định nghĩa claim `act` để biểu diễn actor mà quyền đã được ủy quyền cho:

~~~json
{
  "sub": "user-42",
  "act": {
    "sub": "order-service"
  }
}
~~~

Trong ví dụ, subject vẫn là `user-42`, còn actor hiện tại là `order-service`. Resource server có thể dùng cả hai để audit hoặc áp dụng policy, ví dụ chỉ cho phép order service thực hiện thao tác inventory đã được ủy quyền.

### 7.3. Chuỗi actor lồng nhau

Khi delegation đi qua nhiều actor, claim `act` có thể chứa actor trước đó trong một `act` lồng nhau:

~~~json
{
  "sub": "user-42",
  "act": {
    "sub": "inventory-service",
    "act": {
      "sub": "order-service",
      "act": {
        "sub": "api-gateway"
      }
    }
  }
}
~~~

Actor ngoài cùng là actor hiện tại được biểu diễn; các actor lồng nhau ghi lại chuỗi delegation trước đó theo cấu trúc RFC 8693. Cần thống nhất cách diễn giải chain và giới hạn độ sâu để tránh token phình to hoặc tạo dữ liệu audit khó kiểm soát.

### 7.4. Không tự phát minh claim actor không có hợp đồng

Một số hệ thống dùng claim riêng như `service`, `caller`, `client`, `delegated_by` hoặc header `X-Actor`. Những tên này không tự có ngữ nghĩa chuẩn thống nhất.

Nếu dùng claim riêng, cần định nghĩa schema và semantics, xác định ai được phép phát hành, quy định cách xác minh và thứ tự delegation, phân biệt actor hiện tại với actor trước đó, đặt versioning và compatibility policy.

Không dùng `azp` trong ID Token như một cách thay thế tổng quát cho actor claim trong mọi access token. `azp` có ngữ nghĩa theo OpenID Connect và cần được dùng đúng ngữ cảnh.

## 8. Giới hạn audience và scope ở từng chặng

### 8.1. Audience xác định resource nhận token

Claim `aud` cho biết recipient mà JWT hướng tới. Resource server phải kiểm tra audience của chính nó theo policy. Token dành cho order service không tự động hợp lệ ở inventory service.

~~~text
Token A:
  aud = order-service
  scope = orders.create

Token B:
  aud = inventory-service
  scope = inventory.reserve
~~~

Không sửa `aud` của token A rồi gửi tới inventory service. Chỉ issuer tin cậy mới được phát hành token B sau khi kiểm tra delegation.

### 8.2. Audience hẹp giúp giảm blast radius

Token có nhiều audience có thể cần thiết trong một số profile, nhưng càng nhiều resource nhận được cùng bearer token thì hậu quả khi token bị lộ càng lớn.

Ưu tiên một audience rõ ràng cho một resource server hoặc resource group có cùng ranh giới tin cậy; tách token khi quyền và resource khác nhau; không dùng audience chung kiểu `internal` cho mọi service nếu nó làm mất khả năng phân biệt recipient; kiểm tra audience chính xác tại từng service.

### 8.3. Scope phải được thu hẹp, không tự tăng

Scope của token downstream phải nằm trong tập quyền mà policy cho phép. Có thể hình dung:

~~~text
effective scopes =
    subject permissions
  ∩ actor permissions
  ∩ client policy
  ∩ target resource policy
  ∩ requested scopes
~~~

Đây là mô hình tư duy về phép giao quyền, không phải công thức chuẩn bắt buộc của OAuth. Authorization server cần áp dụng policy cụ thể và không cấp scope chỉ vì client yêu cầu.

Ví dụ user có thể tạo đơn hàng nhưng order service chỉ được yêu cầu inventory reserve cho đơn đang xử lý. Token exchange không nên cấp thêm `inventory.admin` hoặc quyền đọc toàn kho.

### 8.4. Scope không thay thế kiểm tra tài nguyên

Scope `orders.read` có thể cho phép gọi chức năng đọc đơn hàng, nhưng chưa chắc cho phép đọc mọi đơn hàng. Resource server vẫn cần kiểm tra object-level authorization:

- Subject có quyền với order ID này không?
- Order có thuộc tenant đúng không?
- Actor có được phép đọc dữ liệu thay mặt subject không?
- Hành động có phù hợp trạng thái nghiệp vụ không?

Không dùng scope chung để bỏ qua kiểm tra quyền sở hữu hoặc tenant isolation.

## 9. Service identity và user delegation

### 9.1. Service-to-service authentication

Service identity chứng minh workload nào đang kết nối. Nó có thể được xác thực bằng mTLS, workload identity, client credentials hoặc cơ chế tương đương.

~~~text
order-service -- mTLS/workload identity --> inventory-service
~~~

Service identity trả lời: “Ai đang kết nối với tôi?” Nó không nhất thiết trả lời: “Người dùng nào yêu cầu hành động này?”.

### 9.2. User delegation

User delegation mang ngữ cảnh quyền của subject và cho biết actor được phép hành động thay mặt subject:

~~~text
subject = user-42
actor = order-service
audience = inventory-service
scope = inventory.reserve
~~~

### 9.3. Hai lớp có thể cùng cần thiết

Một downstream service có thể cần xác minh đồng thời:

1. Workload identity của caller qua mTLS hoặc client authentication.
2. Delegated access token có subject, actor, audience và scope phù hợp.

Điều này giúp bảo đảm token không bị một workload khác đánh cắp rồi sử dụng. Nếu token được sender-constrain bằng mTLS hoặc DPoP, cần xác minh binding theo profile.

### 9.4. Phân biệt quyền riêng của service và quyền thay mặt user

Một service có thể cần hai loại quyền:

- **Service authority:** quyền vận hành của workload, ví dụ đọc cấu hình hoặc ghi metrics.
- **Delegated user authority:** quyền thực hiện nghiệp vụ thay mặt một user, ví dụ giữ hàng cho đơn do user tạo.

Không gộp hai loại quyền vào một token rộng. Tách credential và policy giúp service không vô tình dùng quyền hệ thống để vượt qua quyền người dùng.

## 10. Ngăn confused deputy và ambient authority

### 10.1. Confused deputy là gì?

Confused deputy xảy ra khi một thành phần có quyền cao bị thuyết phục sử dụng quyền đó thay cho một bên không có quyền tương ứng.

Ví dụ order service có service credential đủ quyền gọi payment service; người dùng gửi request yêu cầu thanh toán khoản không thuộc đơn của họ; order service không kiểm tra quan hệ giữa subject, order và payment; rồi dùng quyền service rộng để thanh toán thay người dùng.

Downstream thấy một service đáng tin, nhưng service đã dùng quyền quá mức so với ý định và quyền của subject.

### 10.2. Nguyên tắc giảm rủi ro

- Giữ subject và actor riêng biệt.
- Ràng buộc token với audience đích.
- Giảm scope theo nhiệm vụ.
- Downstream kiểm tra actor có được phép thực hiện hành động đó không.
- Kiểm tra quan hệ subject-resource-tenant.
- Không cho upstream tự khai báo subject bằng header.
- Tách service authority khỏi delegated user authority.
- Không dùng một service credential admin để thực hiện mọi thao tác user.

### 10.3. Không dùng ambient authority

Ambient authority là quyền sẵn có trong môi trường mà code có thể sử dụng mà không cần được cấp rõ ràng cho từng hành động. Ví dụ một service có token admin toàn hệ thống trong biến môi trường và dùng nó cho mọi request.

Ưu tiên credential có audience và scope cụ thể, thời hạn ngắn, được lấy khi cần và gắn với operation. Không truyền token admin rộng qua các chặng chỉ vì tiện.

## 11. Trust boundary và trách nhiệm của từng dịch vụ

### 11.1. Mỗi service là một resource server độc lập

Một service nhận delegated token cần xác minh issuer nằm trong danh sách tin cậy, chữ ký và thuật toán đúng policy, audience dành cho service hiện tại, token còn hiệu lực, subject có định dạng và issuer context hợp lệ, actor được phép gọi resource này, scope/permission đáp ứng endpoint, tenant và object-level constraints đúng, sender constraint nếu token yêu cầu.

Không tin các claim chỉ vì chúng xuất hiện trong JWT. Phải xác minh chữ ký và áp dụng profile/token contract đã thống nhất.

### 11.2. Upstream không thể tự cấp quyền downstream

Order service có thể đề nghị token exchange với `audience=inventory-service`, nhưng authorization server quyết định có cấp hay không. Order service không được tự ký một JWT nội bộ rồi yêu cầu inventory service tin nó, trừ khi kiến trúc có một issuer nội bộ được quản trị rõ ràng và policy xác định.

### 11.3. Downstream phải kiểm tra object-level authorization

Ngay cả khi token hợp lệ và scope đúng, inventory service vẫn cần xác nhận yêu cầu giữ hàng thuộc đơn hợp lệ, tenant đúng, số lượng được phép và trạng thái đơn cho phép.

Không để một delegated token biến thành quyền truy cập mọi đối tượng trong resource server.

### 11.4. Không dựa vào mạng nội bộ

Private network, service mesh hoặc firewall có thể giảm bề mặt tấn công, nhưng không chứng minh mọi request đều hợp lệ. Một service nội bộ có thể bị xâm nhập hoặc cấu hình sai. Xác thực và phân quyền vẫn phải được áp dụng tại service boundary.

## 12. Ngữ cảnh trong hệ thống bất đồng bộ

### 12.1. Queue và background job

Không phải mọi nghiệp vụ hoàn tất trong một HTTP request. Order service có thể phát event để inventory service xử lý sau vài giây hoặc vài phút.

Không nên lưu access token ngắn hạn của user vào message queue rồi kỳ vọng nó còn hợp lệ khi worker chạy. Token có thể hết hạn trước khi message được xử lý; lưu bearer token lâu dài trong queue cũng mở rộng nơi credential có thể bị lộ.

### 12.2. Tách business context khỏi bearer credential

Một event có thể mang:

~~~json
{
  "event_id": "evt-1001",
  "order_id": "order-900",
  "requested_by": "user-42",
  "tenant_id": "tenant-7",
  "operation": "reserve-inventory",
  "correlation_id": "trace-abc"
}
~~~

Đây là dữ liệu nghiệp vụ/tương quan, không tự chứng minh quyền. Consumer phải xác thực nguồn message và kiểm tra quyền theo policy. Nếu cần delegated authorization tại thời điểm xử lý, worker có thể exchange một delegation assertion còn hợp lệ hoặc lấy token mới từ authorization server theo job policy.

### 12.3. Job dài hạn

Với job chạy lâu, ghi nhận ai yêu cầu job và service nào khởi tạo; lưu tenant, resource và action đã được phê duyệt; xác định quyền có được đánh giá tại thời điểm tạo job hay phải đánh giá lại khi thực thi; không lưu bearer token thô lâu dài nếu không cần; cấp credential ngắn hạn cho worker và audience đích; có cơ chế hủy job khi user/session bị thu hồi nếu nghiệp vụ yêu cầu; audit actor và subject tại cả thời điểm yêu cầu lẫn thực thi.

Nếu quyền người dùng thay đổi sau khi job được tạo, policy phải xác định rõ job tiếp tục theo quyết định đã chốt hay bị đánh giá lại. Không để hành vi phụ thuộc ngẫu nhiên vào việc token cũ còn hạn.

### 12.4. Event không phải authorization assertion

Trường `requested_by` trong JSON message chỉ là dữ liệu. Một producer bị xâm nhập có thể tạo event giả với user ID bất kỳ. Nếu consumer cần tin subject/actor, xác thực producer bằng workload identity, bảo vệ tính toàn vẹn và nguồn gốc message, dùng token hoặc assertion được issuer tin cậy ký, ràng buộc assertion với audience/operation/thời hạn và kiểm tra message ID để chống replay nghiệp vụ.

Không dùng correlation ID hoặc trace baggage làm bằng chứng ủy quyền.

## 13. Trace context và authorization context

### 13.1. Trace ID không phải danh tính

Distributed tracing thường truyền trace ID, span ID và baggage qua nhiều service. Chúng giúp kết nối log và đo độ trễ, nhưng không phải credential.

Không đặt `sub`, role hoặc quyền nhạy cảm vào baggage rồi tin nó ở downstream. Trace context có thể đi qua proxy, queue hoặc hệ thống quan sát không thuộc trust boundary của authorization.

### 13.2. Correlation ID nên tách khỏi JWT

Correlation ID có thể được tạo ở gateway hoặc ingress, sau đó truyền qua các service để liên kết log. Nó không cần nằm trong JWT và không nên quyết định quyền.

Nếu cần gắn token với một request cụ thể, dùng cơ chế sender constraint hoặc proof theo chuẩn phù hợp; một trace ID tự khai báo không ràng buộc cryptographic token với request.

### 13.3. Logging subject và actor

Log audit nên ghi riêng subject đã được xác minh, actor hiện tại, issuer và audience, resource/action được yêu cầu, kết quả authorization, token ID/fingerprint an toàn khi cần, correlation/trace ID.

Không ghi raw bearer token. Hạn chế ghi PII và áp dụng retention/access policy cho audit log.

## 14. Tenant isolation trong delegated authorization

### 14.1. Tenant là một ràng buộc quyền

Trong hệ thống multi-tenant, subject có thể thuộc nhiều tenant hoặc có role khác nhau ở từng tenant. Token cần mang hoặc liên kết tới tenant context đã được xác minh theo profile.

Downstream phải kiểm tra tenant trong token có hợp lệ với issuer và subject không, resource có thuộc tenant đó không, actor/service có được phép hoạt động trong tenant đó không, và request có cố thay đổi tenant ID để truy cập dữ liệu khác không.

Không tin `X-Tenant-Id` từ client nếu nó chưa được đối chiếu với identity và authorization policy.

### 14.2. Tenant trong token exchange

Authorization server có thể phát hành token downstream gắn tenant cụ thể khi policy cho phép. Nếu subject có quyền ở tenant A nhưng không ở tenant B, exchange cho resource tenant B phải bị từ chối.

Không cho client tự yêu cầu tenant tùy ý rồi đưa giá trị đó vào token. Tenant phải được xác minh từ subject permissions và context nghiệp vụ đáng tin cậy.

### 14.3. Tránh confused deputy xuyên tenant

Một service có quyền truy cập dữ liệu nhiều tenant có thể vô tình dùng service authority để vượt qua giới hạn tenant của user. Vì vậy downstream cần kiểm tra đồng thời:

`subject permission + actor permission + tenant boundary + resource ownership`

Một scope chung như `orders.read` không tự cho phép đọc mọi đơn hàng ở mọi tenant.

## 15. Thời hạn, thu hồi và vòng đời delegation

### 15.1. Token downstream nên ngắn hạn

Token exchange thường tạo token mới với thời hạn phù hợp chặng downstream. Không cần giữ token inventory service lâu bằng refresh token của phiên người dùng.

Thời hạn nên đủ cho công việc cần thiết, có tính tới clock skew và thời gian xử lý, nhưng không dài hơn nhu cầu. Job dài hạn nên lấy credential mới theo policy thay vì dùng một bearer token dài hạn.

### 15.2. Thu hồi token gốc và token đã exchange

Việc thu hồi subject token không tự động bảo đảm mọi exchanged token đã phát hành bị vô hiệu ngay. Nếu downstream chỉ xác minh JWT stateless, token đã exchange có thể còn hiệu lực đến `exp`.

Tùy yêu cầu, có thể dùng TTL ngắn, token introspection hoặc revocation state, session/family version, denylist cho token cụ thể hoặc cơ chế thông báo thu hồi tới resource server.

Đánh đổi giữa thu hồi tức thì, độ trễ, khả năng chịu lỗi và chi phí tra cứu phải được thiết kế rõ.

### 15.3. Delegation không vượt thời hạn subject

Authorization server không nên phát hành token downstream có thời hạn vượt quá giới hạn policy của subject token hoặc phiên nguồn nếu điều đó làm quyền tồn tại lâu hơn ý định ban đầu.

Một quy tắc thận trọng là thời hạn token mới bị giới hạn bởi thời hạn còn lại của credential nguồn, policy client, policy resource và thời hạn tối đa delegation. Đây là chính sách an toàn thường dùng, không phải phép tính bắt buộc giống nhau cho mọi profile.

## 16. Sender-constrained token và bảo vệ theo chặng

### 16.1. Rủi ro bearer token

Bearer token có thể được sử dụng bởi bất kỳ bên nào sở hữu token. Khi token được chuyển tiếp qua nhiều service, số nơi có thể đọc hoặc log token tăng lên.

### 16.2. Ràng buộc token với client

Các cơ chế như mTLS hoặc DPoP có thể ràng buộc token với client/key:

- mTLS ràng buộc access token với chứng thư client theo profile phù hợp.
- DPoP dùng proof-of-possession gắn với khóa của client và request.

Downstream cần kiểm tra sender constraint theo đúng profile. Chỉ thêm một claim tên `cnf` hoặc `jkt` mà không thực hiện proof validation là chưa đủ.

### 16.3. Sender constraint không thay thế audience/scope

Token gắn với một khóa client vẫn cần audience đúng, scope tối thiểu, thời hạn hợp lệ và subject/actor rõ ràng. Sender constraint giảm khả năng token bị đánh cắp đem dùng từ client khác; nó không cấp thêm quyền nghiệp vụ.

## 17. Quy trình thiết kế ủy quyền xuyên dịch vụ

### 17.1. Bước 1: xác định subject và actor

Với mỗi operation, trả lời ai yêu cầu hành động, ai đang thực thi ở chặng hiện tại, service nào được phép hành động thay mặt subject, có cần giữ actor chain để audit không và service nào chỉ cần quyền riêng của workload.

### 17.2. Bước 2: xác định resource và quyền từng chặng

Liệt kê từng downstream resource, audience và scope tối thiểu. Không cấp scope tổng hợp chỉ vì upstream có nhiều bước nghiệp vụ.

### 17.3. Bước 3: chọn cách truyền quyền

- Forward token nếu token gốc được phát hành cho đúng resource và quyền.
- Token exchange khi cần audience mới, scope hẹp hơn hoặc actor chain.
- Client credentials/service identity cho thao tác thuần service, không đại diện user.
- Assertion riêng chỉ khi có hợp đồng, issuer và validation policy rõ ràng.

### 17.4. Bước 4: xác định policy tại authorization server

Quy định client nào được exchange, subject token type nào được chấp nhận, actor nào được đại diện subject, audience nào được yêu cầu và scope nào được cấp. Áp dụng allowlist và giới hạn thời hạn.

### 17.5. Bước 5: xác minh ở downstream

Mỗi service xác minh chữ ký, issuer, audience, thời hạn, token type/profile, actor, scope, tenant và object-level permission trước khi thực hiện thao tác.

### 17.6. Bước 6: thiết kế audit và thu hồi

Ghi nhận subject, actor, audience, action, kết quả và correlation ID. Xác định TTL, revocation, job cancellation và cách xử lý credential đã exchange.

## 18. Luồng tham khảo: Order service gọi Inventory

### 18.1. Luồng tổng quát

~~~mermaid
sequenceDiagram
    participant U as User
    participant G as API Gateway
    participant O as Order Service
    participant AS as Authorization Server
    participant I as Inventory Service
    U->>G: Request tạo order + user access token
    G->>G: Verify issuer, audience, signature, claims
    G->>O: Forward request theo policy
    O->>O: Xác định subject=user-42, actor=order-service
    O->>AS: Token exchange cho inventory audience/scope
    AS->>AS: Verify subject token và actor authorization
    AS-->>O: Token aud=inventory, scope=inventory.reserve, act=order-service
    O->>I: Reserve item + exchanged access token
    I->>I: Verify token, audience, actor, scope và tenant
    I-->>O: Reservation result
    O-->>G: Order result
    G-->>U: Response
~~~

### 18.2. Token tại từng chặng

Token người dùng tới gateway:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders.create orders.read",
  "exp": 1760000300
}
~~~

Token exchange cho inventory:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "inventory-service",
  "client_id": "order-service",
  "scope": "inventory.reserve",
  "act": {
    "sub": "order-service"
  },
  "exp": 1760000150
}
~~~

Ví dụ cho thấy subject không đổi, audience và scope được giới hạn cho inventory, còn actor được ghi nhận. Giá trị thực tế phải theo token profile và policy của hệ thống.

### 18.3. Inventory service quyết định

Inventory service không chỉ kiểm tra `scope=inventory.reserve`. Nó còn cần xác minh issuer và chữ ký, audience là inventory service, token còn hạn và đúng token type, actor `order-service` được phép gọi thao tác này, subject/tenant phù hợp với order, item/số lượng/trạng thái/giới hạn nghiệp vụ và ghi audit subject cùng actor.

Nếu một điều kiện bắt buộc thất bại, không giữ hàng.

## 19. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Hậu quả | Cách xử lý |
| --- | --- | --- | --- |
| Chỉ truyền user ID qua header | Không có bằng chứng tin cậy | Caller giả mạo subject | Dùng token/assertion được xác minh |
| Ghi đè `sub` thành service | Trộn subject với actor | Mất ngữ cảnh người dùng | Giữ subject và biểu diễn actor riêng |
| Chuyển tiếp token tới mọi service | Không giới hạn audience | Token bị dùng ngoài resource dự kiến | Token exchange hoặc token có aud được thiết kế rõ |
| Dùng một audience `internal` cho tất cả | Ranh giới resource mờ | Token lộ có blast radius lớn | Audience hẹp theo resource |
| Scope upstream quá rộng | Không thu hẹp quyền | Downstream có quyền thừa | Tính quyền theo subject/actor/client/resource |
| Trust gateway hoàn toàn | Downstream không xác minh | Lateral movement | Xác minh tại từng service boundary |
| Service credential thay user token | Chỉ biết actor, mất subject | Không áp dụng được quyền user | Kết hợp workload identity và delegated token |
| Tin `requested_by` trong event | Message data bị giả mạo | Giả danh user trong job | Xác thực producer và delegation assertion |
| Dùng trace baggage làm quyền | Trộn observability với security | Header bị sửa thành quyền | Giữ trace context tách biệt |
| Dùng ID Token gọi API | Nhầm loại token | Sai semantics/audience | Dùng access token đúng profile |
| Token exchange cấp scope tùy ý | Policy exchange quá rộng | Escalation | Allowlist audience và quyền được phép |
| Không kiểm tra tenant downstream | Tin tenant từ upstream | Cross-tenant access | Kiểm tra tenant-resource-subject |
| Không ghi actor chain | Thiếu audit | Khó điều tra | Dùng `act` hoặc schema delegation rõ ràng |
| Thu hồi subject token nhưng quên exchanged token | Chỉ nghĩ về token nguồn | Quyền downstream còn tồn tại | TTL ngắn và revocation strategy |

## 20. Checklist triển khai

### 20.1. Mô hình danh tính

- [ ] Đã định nghĩa subject và actor riêng biệt.
- [ ] Subject được bảo toàn qua các chặng cần thiết.
- [ ] Actor hiện tại và delegation chain có semantics rõ ràng.
- [ ] Service identity được phân biệt với delegated user authority.
- [ ] Không tin `X-User-Id`, `X-Tenant-Id` hoặc trace baggage từ nguồn chưa xác thực.

### 20.2. Token và policy

- [ ] Token có issuer và profile được downstream tin cậy.
- [ ] Audience phù hợp với resource nhận token.
- [ ] Scope chỉ bao gồm quyền tối thiểu của chặng hiện tại.
- [ ] Authorization server kiểm tra quyền của subject, actor, client và resource khi exchange.
- [ ] Không sửa `aud`, `sub` hoặc scope của token đã ký.
- [ ] ID Token không được dùng thay access token.
- [ ] Actor chain không vượt giới hạn và không chứa dữ liệu nhạy cảm không cần thiết.

### 20.3. Ranh giới service

- [ ] Mỗi downstream service xác minh token độc lập.
- [ ] Workload identity của caller được xác thực.
- [ ] Actor được phép gọi endpoint.
- [ ] Có object-level và tenant-level authorization.
- [ ] Không dựa vào private network như bằng chứng quyền.
- [ ] Service authority và delegated user authority được tách.

### 20.4. Vận hành

- [ ] Có audit subject, actor, resource, action và kết quả.
- [ ] Correlation/trace ID tách khỏi credential.
- [ ] Không log raw token.
- [ ] Có TTL và chiến lược thu hồi cho exchanged token.
- [ ] Job bất đồng bộ không lưu bearer token dài hạn nếu không cần.
- [ ] Có test cho audience mismatch, scope escalation, actor mismatch và tenant crossing.

## 21. Kiểm thử bảo mật

Các trường hợp âm tính nên được kiểm tra:

1. Token audience dành cho order service được gửi tới inventory service.
2. Token có scope `orders.read` được dùng để yêu cầu `inventory.reserve`.
3. Service khác giả mạo `X-User-Id=user-42`.
4. Actor không nằm trong policy được phép exchange token.
5. Subject token hợp lệ nhưng actor token không hợp lệ.
6. Token exchange yêu cầu audience không được đăng ký.
7. Client yêu cầu scope cao hơn quyền subject hoặc actor.
8. Actor chain sai cấu trúc hoặc vượt giới hạn độ sâu.
9. Token có `sub` đúng nhưng tenant/resource không khớp.
10. Event queue chứa `requested_by` giả mạo.
11. Trace baggage bị sửa thành role hoặc scope.
12. Token exchanged đã hết hạn hoặc bị thu hồi.
13. Access token của một loại được dùng nhầm ở endpoint loại khác.
14. Service identity hợp lệ nhưng delegated user permission không đủ.

Tiêu chí đạt:

- Không thể đổi subject bằng header không tin cậy.
- Không thể dùng token ở sai audience.
- Không thể tăng scope bằng cách tự sửa request exchange.
- Downstream biết actor nào đang hành động thay mặt subject.
- Quyền của một service không tự động trở thành quyền của mọi service.
- Job/event bất đồng bộ không biến metadata thành authorization assertion.

## 22. Những hiểu lầm phổ biến

**“Chỉ cần truyền user ID qua các service là bảo toàn được danh tính.”** Sai. User ID trong header chỉ là dữ liệu nếu không có nguồn xác thực và tính toàn vẹn đáng tin cậy.

**“Service nào cũng có thể dùng access token của người dùng.”** Sai. Token phải có audience và scope phù hợp với resource nhận nó.

**“Giữ nguyên subject nghĩa là giữ nguyên toàn bộ quyền.”** Sai. Subject có thể giữ nguyên trong khi scope được thu hẹp cho từng chặng.

**“Service identity thay thế user delegation.”** Sai. Workload identity cho biết caller là service nào; nó không tự chứng minh người dùng cuối có quyền thực hiện hành động.

**“Gateway xác minh rồi thì downstream không cần xác minh.”** Sai. Mỗi resource server phải thực thi trust policy của chính nó.

**“Token exchange luôn tự động an toàn hơn forwarding.”** Sai. Exchange chỉ an toàn khi authorization server kiểm tra subject, actor, audience và scope theo policy chặt chẽ.

**“Trace ID có thể dùng làm định danh ủy quyền.”** Sai. Trace context phục vụ quan sát, không phải credential.

**“Thu hồi token nguồn sẽ thu hồi ngay mọi token đã exchange.”** Không nhất thiết. Exchanged JWT có thể còn hiệu lực đến expiry nếu downstream xác minh stateless.

**“Một service có quyền admin thì có thể dùng quyền đó thay mặt mọi user.”** Sai. Đây là nguy cơ confused deputy và ambient authority.

## 23. Câu hỏi tự kiểm tra

1. Phân biệt subject và actor trong một request đi qua ba microservice.
2. Vì sao không nên ghi đè `sub` bằng service identity ở mỗi hop?
3. Token forwarding khác token exchange ở điểm nào?
4. Những điều kiện nào cần được authorization server kiểm tra trước khi exchange?
5. Vì sao `aud` cần được giới hạn cho từng resource server?
6. Scope downstream nên được tính theo những quyền và policy nào?
7. Claim `act` trong RFC 8693 biểu diễn điều gì?
8. Vì sao service identity và delegated user authority có thể cần được xác minh đồng thời?
9. Confused deputy xuất hiện như thế nào khi order service dùng service credential quá rộng?
10. Vì sao `requested_by` trong queue message không phải authorization assertion?
11. Trace ID và trace baggage khác authorization context ra sao?
12. Thu hồi subject token có làm exchanged access token stateless mất hiệu lực ngay không?
13. Khi nào token forwarding có thể chấp nhận được?
14. Những kiểm tra nào phải diễn ra tại downstream service trước khi thực hiện hành động?

## 24. Tiêu chuẩn và tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), access token, client authorization và token grant.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693), subject token, actor token, token exchange và claim `act`.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068), profile JWT access token.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519), claims `sub`, `aud`, `iss`, `exp` và cấu trúc JWT.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707), xác định resource đích trong yêu cầu cấp token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700), bảo vệ OAuth token và ranh giới tin cậy.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449), ràng buộc access token với khóa client.
- [OWASP Microservices Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Microservices_Security_Cheat_Sheet.html), xác thực, ủy quyền và bảo vệ ranh giới giữa các microservice.

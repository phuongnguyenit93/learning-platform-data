# Chọn token exchange hay relay

Khi một service nhận request có access token rồi gọi service khác, đội phát triển phải quyết định nên **relay token hiện có** hay **đổi token sang một token mới dành cho dịch vụ đích**. Hai cách đều có thể đúng, nhưng giải quyết các ranh giới tin cậy khác nhau. Relay giữ nguyên credential và ngữ cảnh quyền của token ban đầu; token exchange yêu cầu Authorization Server phát hành credential mới theo audience, scope và chính sách ủy quyền của luồng gọi.

Bài học thuộc chương **Quyết định thiết kế** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung giúp chọn cách truyền danh tính và quyền giữa các service trong OAuth 2.0/OIDC, giảm quyền quá mức, tránh confused deputy, bảo vệ access token và giữ được ngữ cảnh người dùng hoặc workload khi đi qua nhiều tầng.

## 1. Bối cảnh: service gọi service

Giả sử người dùng gọi `orders-api` để xem đơn hàng. Để dựng chi tiết đơn, `orders-api` cần gọi `inventory-api` lấy trạng thái tồn kho.

Có hai lựa chọn chính:

- **Token relay:** `orders-api` chuyển tiếp access token nhận từ client sang `inventory-api`. Service đích xác minh chính token đó và quyết định có chấp nhận hay không.
- **Token exchange:** `orders-api` gửi access token hiện tại đến Authorization Server theo Token Exchange grant. Authorization Server kiểm tra quyền đổi token và cấp một access token mới dành cho `inventory-api` với quyền được giới hạn theo policy.

Token relay đơn giản hơn, ít phụ thuộc vào Authorization Server trong mỗi lần gọi. Token exchange tạo được ranh giới quyền rõ hơn cho service đích, nhưng thêm bước cấp token, độ trễ, dependency và yêu cầu quản lý cache/lifetime.

## 2. Phân biệt hai mô hình

| Tiêu chí | Token relay | Token exchange |
| --- | --- | --- |
| Token gửi tới service đích | Token ban đầu, giữ nguyên | Token mới do Authorization Server phát hành |
| Audience | Phải bao gồm service đích theo hợp đồng token | Có thể yêu cầu audience/resource cụ thể |
| Scope | Giữ nguyên scope của token ban đầu | Có thể thu hẹp theo scope được phép |
| Subject | Giữ nguyên subject | Có thể giữ subject hoặc ánh xạ theo policy |
| Actor/service gọi thay mặt user | Thường không được biểu đạt rõ bằng một token riêng | Có thể biểu đạt bằng actor token/claim theo RFC 8693 và policy issuer |
| Phụ thuộc Authorization Server lúc gọi | Không cần exchange mỗi lần | Cần exchange khi chưa có token phù hợp trong cache |
| Độ phức tạp | Thấp hơn | Cao hơn: grant, policy, cache, audit và failure handling |
| Rủi ro chính | Token quá rộng bị lan truyền qua nhiều service | Exchange policy sai có thể cấp quyền vượt quá hoặc sai subject/actor |

Điểm quan trọng: token exchange không tự động làm hệ thống an toàn. Nó chỉ hữu ích khi Authorization Server thực sự kiểm tra ai được đổi token nào, cho audience nào và với quyền gì. Nếu exchange endpoint cấp token tùy tiện hoặc cho phép giữ nguyên toàn bộ quyền, lợi ích của việc đổi token sẽ giảm đáng kể.

## 3. Token relay hoạt động như thế nào?

Trong mô hình relay, service trung gian lấy access token từ security context đã xác minh và gửi nguyên token trong header Authorization đến service đích:

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as orders-api
    participant Inventory as inventory-api
    Client->>Orders: HTTPS + Bearer access token
    Orders->>Orders: Xác minh token và quyền trên orders
    Orders->>Inventory: HTTPS + cùng access token
    Inventory->>Inventory: Xác minh issuer, audience, scope và quyền
    Inventory-->>Orders: Kết quả tồn kho
    Orders-->>Client: Kết quả đơn hàng
~~~

Relay phù hợp khi:

- Access token được phát hành có audience bao gồm service đích hoặc resource server được thiết kế để chấp nhận token đó.
- Token chỉ chứa scope cần thiết cho cả service trung gian và service đích.
- Service trung gian được phép chuyển tiếp token theo hợp đồng bảo mật.
- Service đích có thể xác minh token độc lập và kiểm tra quyền trên tài nguyên của chính nó.
- Hệ thống chấp nhận cùng một credential đi qua các tầng trong một trust boundary đã được xác định.

Relay không có nghĩa service trung gian được bỏ qua kiểm tra quyền. `orders-api` vẫn phải xác minh token và quyền trên đơn hàng; `inventory-api` tiếp tục xác minh token và quyền trên dữ liệu tồn kho. Mỗi service phải chịu trách nhiệm cho tài nguyên của mình.

### Ví dụ HTTP relay

~~~http
GET /internal/inventory/items/sku-42 HTTP/1.1
Host: inventory.internal.example
Authorization: Bearer <the-same-access-token>
Accept: application/json
~~~

Token trong ví dụ phải là access token dành cho `inventory-api` theo hợp đồng issuer. Không relay ID token, refresh token, authorization code hoặc session cookie của browser như thể chúng là access token cho API. Không chuyển token vào query string hoặc URL.

## 4. Token exchange hoạt động như thế nào?

OAuth 2.0 Token Exchange được mô tả trong RFC 8693. Một client đã được Authorization Server cho phép có thể gửi subject token, tùy chọn actor token và thông tin token mong muốn để xin một token mới.

Trong ví dụ:

- `subject_token` đại diện cho người dùng đang được ủy quyền.
- `actor_token` có thể đại diện cho service đang hành động thay mặt subject.
- `audience` hoặc `resource` xác định nơi token mới sẽ được sử dụng theo khả năng của issuer.
- `scope` yêu cầu quyền cần thiết cho thao tác ở service đích.
- Authorization Server quyết định có cấp token hay không và phát hành token theo policy.

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as orders-api
    participant AS as Authorization Server
    participant Inventory as inventory-api
    Client->>Orders: HTTPS + access token A
    Orders->>Orders: Xác minh token A và quyền
    Orders->>AS: Token Exchange: subject token A, actor orders-api, audience inventory-api
    AS->>AS: Kiểm tra subject, actor, audience, scope và policy
    AS-->>Orders: Access token B dành cho inventory-api
    Orders->>Inventory: HTTPS + access token B
    Inventory->>Inventory: Xác minh token B và quyền
    Inventory-->>Orders: Kết quả tồn kho
    Orders-->>Client: Kết quả đơn hàng
~~~

### Ví dụ Token Exchange request

Request minh họa theo RFC 8693:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Authorization: Basic <orders-api-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&
subject_token=<user-access-token>&
subject_token_type=urn:ietf:params:oauth:token-type:access_token&
requested_token_type=urn:ietf:params:oauth:token-type:access_token&
audience=inventory-api&
scope=inventory:read
~~~

Đây là ví dụ minh họa; cách xác thực client, tên audience/resource, scope và việc có cần actor token phụ thuộc cấu hình Authorization Server. Không gửi client secret trong URL hoặc log. Subject token cần được gửi qua HTTPS và không được ghi lại dưới dạng rõ.

Response có thể chứa access token mới, loại token, thời hạn và loại token đã phát hành:

~~~json
{
  "access_token": "<new-access-token-for-inventory>",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory:read"
}
~~~

Token mới cần có audience phù hợp với `inventory-api`. Resource Server vẫn phải xác minh chữ ký hoặc introspection, issuer, audience, thời hạn, loại token và quyền. Client không được tự sửa claim hoặc tự tạo token mới từ payload cũ.

## 5. Cách biểu đạt subject và actor

Trong luồng service-to-service có người dùng, cần phân biệt:

- **Subject:** người dùng hoặc principal mà hành động đang được thực hiện thay mặt.
- **Actor:** service/client thực sự thực hiện request ở bước hiện tại.
- **Client:** OAuth client đã xác thực với Authorization Server.
- **Resource server:** service nhận token và quyết định có phục vụ request hay không.

Ví dụ `user-123` gọi `orders-api`, rồi `orders-api` gọi `inventory-api` thay mặt người dùng. Subject vẫn là `user-123`; actor có thể là `orders-api`. Nếu chỉ relay token, service đích có thể biết subject nhưng không luôn có bằng chứng chuẩn hóa về service nào đang acting. Network identity, mTLS hoặc metadata riêng có thể bổ sung thông tin nhưng phải được xác minh.

RFC 8693 định nghĩa các khái niệm subject token và actor token. Issuer có thể phát hành token có claim biểu đạt actor theo profile/chính sách tương ứng. Không tự giả định mọi access token đều có claim actor, hoặc mọi Authorization Server đều triển khai đầy đủ các tính năng của RFC 8693.

Nếu service gọi API bằng chính danh tính workload và không cần đại diện người dùng, hãy cân nhắc Client Credentials grant thay vì token exchange. Nếu cần giữ cả ngữ cảnh user lẫn service acting, token exchange có thể phù hợp hơn, với policy xác minh subject và actor tường minh.

## 6. Quyết định dựa trên audience và scope

Audience là ranh giới quan trọng. Token có audience dành cho `orders-api` không mặc nhiên được dùng cho `inventory-api` chỉ vì hai service cùng hệ thống hoặc cùng issuer.

| Tình huống | Quyết định thường phù hợp |
| --- | --- |
| Token đã được phát hành cho cả orders và inventory, scope vừa đủ, cùng trust boundary | Có thể relay |
| Token chỉ dành cho orders, inventory yêu cầu audience riêng | Token exchange hoặc xin token riêng cho inventory |
| Token có scope rộng hơn nhiều so với thao tác downstream | Exchange để xin scope hẹp hơn |
| Service đích cần phân biệt user và service đang acting | Exchange với subject/actor context nếu policy hỗ trợ |
| Service chỉ cần danh tính workload, không cần user context | Client Credentials grant |
| API đích không tin issuer của token đầu vào | Exchange qua issuer/trust broker được API đích tin cậy, nếu policy cho phép |
| API đích chấp nhận token opaque và token được introspect đúng resource | Có thể relay nếu audience/ủy quyền phù hợp |

Không nên giải quyết audience mismatch bằng cách bỏ qua audience validation hoặc thêm mọi service vào audience của mọi token. Điều đó làm giảm khả năng giới hạn token theo resource và tăng tác động nếu token bị đánh cắp.

Nếu dùng RFC 8707 Resource Indicators, client có thể chỉ định resource đích trong request cấp token. Khả năng hỗ trợ và cách kết hợp với token exchange tùy Authorization Server. Hãy định nghĩa rõ audience và resource theo hợp đồng issuer, tránh dùng chúng như hai tên thay thế mà không kiểm tra semantics.

## 7. Decision matrix: khi nào chọn cách nào?

| Câu hỏi | Nếu câu trả lời là Có | Hướng chọn |
| --- | --- | --- |
| Token đầu vào đã dành cho service đích? | Có | Relay có thể đủ |
| Scope hiện tại chỉ vừa đủ cho downstream? | Có | Relay có thể đủ |
| Cần giảm quyền hoặc giới hạn token theo resource? | Có | Token exchange |
| Cần giữ subject nhưng ghi nhận actor service rõ ràng? | Có | Token exchange có actor context |
| Service đích thuộc trust boundary/issuer khác? | Có | Exchange hoặc federation được thiết kế rõ |
| Authorization Server hỗ trợ policy exchange đáng tin cậy? | Không | Không thể giả định exchange; xem lại kiến trúc/trust model |
| Downstream chỉ cần workload identity? | Có | Client Credentials thường phù hợp |
| Nhiều service cần token chung cho cùng resource và quyền? | Có | Relay có thể giảm độ phức tạp |

Một quy tắc thực tế:

- **Relay** khi token đã đúng resource, quyền vừa đủ và service trung gian được phép chuyển tiếp.
- **Exchange** khi cần một token mới với audience, scope, lifetime, issuer hoặc actor context khác.
- **Client Credentials** khi downstream chỉ cần danh tính workload và không cần ủy quyền thay mặt user.

Nếu cả relay và exchange đều khả thi, so sánh chi phí vận hành với mức giảm quyền thực tế. Không chọn exchange chỉ vì nó có vẻ hiện đại hơn; cũng không chọn relay chỉ để giảm một network call nếu điều đó làm token có quyền quá rộng lan qua nhiều service.

## 8. Threat model và lỗi thiết kế thường gặp

### 8.1. Relay token có quyền quá rộng

Token được cấp cho gateway hoặc frontend có scope lớn và audience nhiều API. Khi relay qua các service, mỗi service có thể dùng toàn bộ quyền của token. Nếu một service bị compromise, attacker có thể dùng token đó để gọi các API khác trong cùng audience.

Giảm rủi ro bằng audience/resource cụ thể, scope tối thiểu, lifetime ngắn, network policy và exchange khi downstream cần quyền hẹp hơn.

### 8.2. Confused deputy trong token exchange

Service trung gian có quyền gọi exchange endpoint và yêu cầu token cho một audience bất kỳ. Nếu Authorization Server không kiểm tra service đó có được phép đổi subject token sang resource đích hay không, attacker có thể lợi dụng service như một deputy để xin quyền vượt quá.

Authorization Server phải kiểm tra ít nhất:

- Client/actor đã xác thực và được phép sử dụng grant.
- Subject token hợp lệ, issuer và loại token được chấp nhận.
- Actor có quyền hành động thay mặt subject trong ngữ cảnh yêu cầu.
- Audience/resource đích thuộc tập resource được phép.
- Scope yêu cầu là tập con quyền có thể cấp trong policy.
- Quan hệ tenant, delegation, consent và các giới hạn khác còn hiệu lực.

### 8.3. Exchange nhưng không thu hẹp quyền

Nếu token mới giữ nguyên scope rộng, audience rộng và thời hạn dài, exchange chỉ thêm một bước mà không giảm blast radius. Hãy kiểm tra token được phát hành có thực sự khác về audience/scope/lifetime/actor context và được policy giới hạn hay không.

### 8.4. Dùng sai loại token

Không relay ID token hoặc refresh token đến Resource Server. Với token exchange, phải dùng subject token type mà Authorization Server hỗ trợ và xác minh đúng loại. Token mới phải là access token dành cho API đích nếu đó là mục đích của request.

### 8.5. Tin claim do service trung gian tự khai

Không chấp nhận subject, tenant, actor hoặc role do service gửi trong header/body như bằng chứng ủy quyền. Những thông tin đó phải đến từ token đã xác minh, mTLS/workload identity tin cậy hoặc policy store có thẩm quyền. Header nội bộ có thể bị giả mạo nếu ingress không xóa giá trị client tự gửi.

### 8.6. Ghi token vào log hoặc trace

Relay và exchange đều có bearer credential đi qua nhiều thành phần. Không ghi raw Authorization header, subject token, actor token, exchanged token hoặc refresh token vào log, tracing baggage, exception hay analytics. Dùng request ID và fingerprint HMAC được kiểm soát nếu cần correlation.

## 9. Lifetime, cache và thu hồi

### Với relay

Token có lifetime và thời điểm hết hạn do issuer quyết định. Service trung gian không thể tự kéo dài token. Nếu token gần hết hạn, request downstream có thể thất bại; không tự retry vô hạn hoặc tiếp tục dùng token đã hết hạn.

Cache token ở service trung gian không cần thiết nếu chỉ relay token theo request. Nếu có lưu tạm, phải giới hạn memory, tránh persistence và không ghi log. Không dùng token của request trước cho request khác nếu không chứng minh được cùng subject, client, audience, tenant và quyền.

### Với exchange

Token mới có thể có lifetime ngắn hơn token subject. Cache exchanged token giúp giảm số lần gọi Authorization Server, nhưng cache key phải bao gồm các yếu tố quyết định quyền:

- Subject token fingerprint hoặc phiên/subject đã xác minh.
- Actor/client identity.
- Audience/resource đích.
- Scope set đã được cấp.
- Tenant/authorization context nếu có.
- Token type, issuer và các ràng buộc proof-of-possession.

Không cache chỉ theo client ID hoặc audience nếu token phụ thuộc subject/tenant. Không trả exchanged token cho request có subject hoặc quyền khác.

Khi refresh token hoặc session gốc bị thu hồi, exchanged token có thể vẫn còn hiệu lực đến thời điểm hết hạn nếu Authorization Server và Resource Server không có cơ chế thu hồi liên kết. Cần quyết định cách truyền trạng thái revoke: introspection, token family linkage, denylist, authorization version hoặc lifetime ngắn. Đặt cache TTL không vượt quá thời gian còn lại của token và policy thu hồi.

## 10. Vận hành khi Authorization Server không khả dụng

Relay không cần gọi Token Exchange Endpoint trong đường đi của mỗi request, nên có thể giảm dependency vào Authorization Server ở thời điểm gọi downstream. Tuy vậy, Resource Server vẫn cần xác minh token theo cơ chế của nó: JWT offline validation có thể tiếp tục khi JWKS đã cache hợp lệ, trong khi opaque token introspection có thể phụ thuộc Authorization Server.

Token exchange phụ thuộc Authorization Server khi cần token mới. Khi endpoint exchange lỗi:

- Không tự fallback sang relay nếu token ban đầu không có audience hoặc scope phù hợp.
- Có thể dùng exchanged token còn hiệu lực trong cache nếu cache key và policy vẫn hợp lệ.
- Trả lỗi tạm thời khi không thể lấy token phù hợp; không cấp quyền rộng hơn để duy trì availability.
- Dùng timeout, circuit breaker và bulkhead cho exchange call.
- Quan sát exchange latency, failure rate, cache hit ratio và số token còn lại trong cache.

Nếu thiết kế cho phép fallback relay, điều kiện fallback phải được xác định trước, ví dụ token ban đầu đã được cấp cho downstream và có quyền tương đương. Không quyết định fallback chỉ vì exchange endpoint đang lỗi.

## 11. Kiểm thử quyết định relay/exchange

Một test suite cần kiểm tra cả đường cho phép và đường từ chối:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Relay token có audience và scope đúng cho API đích | API đích xác minh token và xử lý theo quyền |
| Relay token chỉ có audience của service trung gian | API đích từ chối, thường là `401 invalid_token` |
| Relay ID token hoặc refresh token đến API | Từ chối |
| Token exchange với subject token hợp lệ, actor được phép, audience và scope hợp lệ | Authorization Server cấp token đích đúng policy |
| Exchange yêu cầu audience ngoài danh sách được phép | Từ chối |
| Exchange yêu cầu scope rộng hơn quyền subject/actor | Từ chối hoặc chỉ cấp tập con theo policy |
| Subject token hết hạn hoặc bị thu hồi | Exchange bị từ chối |
| Actor token/client không được phép exchange | Từ chối |
| Subject thuộc tenant A nhưng request xin token cho tenant B | Từ chối nếu không có delegation hợp lệ |
| Exchanged token được gửi tới API sai audience | API từ chối |
| Cache key bỏ qua subject hoặc tenant | Test phải phát hiện token của principal khác bị tái sử dụng |
| Authorization Server unavailable và relay token không phù hợp | Không fallback sang token rộng; trả lỗi tạm thời |
| Token được revoke sau exchange | Kiểm tra propagation/revoke behavior theo policy |

Integration test nên xác minh:

1. Token đầu vào được xác thực trước khi relay hoặc exchange.
2. Token exchange request được xác thực client và gửi qua HTTPS.
3. Authorization Server thực thi audience/scope/delegation policy.
4. Service đích xác minh token mới như một Resource Server độc lập.
5. Log, trace và error response không làm lộ token.

## 12. Checklist quyết định kiến trúc

- [ ] Đã xác định subject, actor, OAuth client và resource server ở từng hop.
- [ ] Token relay chỉ dùng access token dành cho đúng downstream audience.
- [ ] Scope của token relay vừa đủ cho tất cả service nhận token.
- [ ] Không relay ID token, refresh token hoặc authorization code.
- [ ] Token exchange endpoint xác thực client/actor và kiểm tra delegation.
- [ ] Audience/resource và scope của exchanged token bị giới hạn theo policy.
- [ ] Không tin subject, actor, tenant hoặc role do request tự khai.
- [ ] Token mới có lifetime phù hợp và không rộng hơn quyền cần thiết.
- [ ] Cache key phân biệt subject, actor, audience, scope và tenant khi có.
- [ ] Có chính sách revoke/propagation cho exchanged token.
- [ ] Có timeout, circuit breaker và hành vi rõ ràng khi Authorization Server lỗi.
- [ ] Không fallback sang relay nếu token ban đầu không phù hợp.
- [ ] Có audit event cho subject, actor, client, audience, scope và quyết định exchange.
- [ ] Không log raw token hoặc Authorization header.
- [ ] Có integration test cho audience mismatch, scope escalation, tenant mismatch và token replay.

## 13. Tình huống tổng hợp

`orders-api` nhận access token có `aud=orders-api` và `scope=orders:read`. Khi cần lấy tồn kho, service gọi `inventory-api`. Token ban đầu không có audience của inventory.

**Không được relay token đó như thể inventory đã được cấp quyền.** Có hai hướng thiết kế:

1. Thay đổi authorization request ban đầu để issuer cấp token có audience và scope phù hợp cho cả hai resource, nếu mô hình trust và quyền cho phép; khi đó relay có thể đáp ứng.
2. Dùng Token Exchange: `orders-api` xác thực với Authorization Server, gửi subject token và actor context, yêu cầu audience `inventory-api` cùng scope `inventory:read`. Authorization Server xác minh user được đọc tồn kho trong tenant tương ứng và `orders-api` được phép acting thay mặt user. Token mới chỉ cấp quyền đã duyệt.

Nếu inventory chỉ cần biết `orders-api` đang gọi như một workload và không cần user context, có thể dùng Client Credentials với scope workload phù hợp. Lựa chọn phụ thuộc vào việc API đích cần ủy quyền theo user, theo service hay cả hai.

**Điều cần nhớ:** relay giữ nguyên token nên chỉ đúng khi token ban đầu đã dành cho downstream và quyền vừa đủ. Token exchange tạo token mới nên phù hợp khi cần đổi audience, thu hẹp scope hoặc biểu đạt delegation/actor. Quyết định phải xuất phát từ trust boundary, quyền thực tế và policy của Authorization Server.

## 14. Tài liệu chuẩn tham khảo

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): subject token, actor token, requested token type, audience và token exchange grant.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707.html): chỉ định resource đích khi xin access token.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): cách sử dụng và bảo vệ Bearer access token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): khuyến nghị bảo mật OAuth 2.0 hiện đại.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): profile xác minh JWT access token tại Resource Server.

# Resource server — Máy chủ tài nguyên trong OAuth 2.0

Một ứng dụng di động đăng nhập người dùng qua nhà cung cấp danh tính, nhận access token rồi gọi API đơn hàng. API nhận token đó và quyết định có trả dữ liệu hay không. Thành phần API chịu trách nhiệm nhận và kiểm tra access token, xác định principal, áp dụng quyền và bảo vệ tài nguyên được gọi là **resource server** (máy chủ tài nguyên).

Resource server là một ranh giới tin cậy quan trọng trong OAuth 2.0. Nó thường không xác thực mật khẩu người dùng và cũng không phát hành access token; đó là trách nhiệm của authorization server hoặc identity provider theo kiến trúc. Resource server phải xác minh token được cấp bởi issuer tin cậy, dành cho đúng API, còn hiệu lực và mang quyền phù hợp. Sau đó nó vẫn phải kiểm tra quyền trên tài nguyên cụ thể, chẳng hạn người dùng có được xem đơn hàng thuộc tài khoản của họ hay không.

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, bài học này kết nối credential, xác thực, token, phiên và phân quyền. Người học sẽ biết cách triển khai resource server cho JWT và opaque token, kiểm tra issuer/audience/thời hạn/chữ ký, dùng JWKS hoặc introspection, ánh xạ scope thành authority, xử lý thu hồi và lỗi, đồng thời chống token theft, replay, confused deputy và truy cập chéo tenant.

## 1. Resource server nằm ở đâu trong OAuth?

OAuth 2.0 là framework ủy quyền. Các vai trò cốt lõi gồm:

| Vai trò | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Resource owner** | Chủ thể có quyền trên tài nguyên; thường là người dùng | Người sở hữu đơn hàng |
| **Client** | Ứng dụng yêu cầu access token và gọi API | Mobile app, web backend, service |
| **Authorization server (AS)** | Xác thực/ủy quyền theo flow, phát access token và quản lý grant | Identity platform hoặc OAuth server |
| **Resource server (RS)** | Bảo vệ API/tài nguyên và kiểm tra access token | Orders API, Payments API |

Luồng đơn giản:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client
    participant AS as Authorization server
    participant RS as Resource server
    U->>C: Bắt đầu đăng nhập / cấp quyền
    C->>AS: Authorization request
    AS->>AS: Xác thực người dùng và áp dụng consent/policy
    AS-->>C: Authorization code
    C->>AS: Đổi code lấy token
    AS-->>C: Access token
    C->>RS: API request + access token
    RS->>RS: Xác minh token và policy
    RS-->>C: Tài nguyên nếu được phép
~~~

Resource server nhận **access token** như credential để truy cập tài nguyên. Token có thể là opaque string hoặc JWT. Resource server không nên suy ra quyền từ trạng thái đăng nhập ở client, cookie của một domain khác hoặc thông tin người dùng tự gửi trong body.

### Resource server không phải authorization server

- Authorization server quyết định có cấp token cho client hay không, dựa trên grant, client, subject, consent và policy.
- Resource server quyết định có chấp nhận token cho API cụ thể hay không, rồi kiểm tra quyền trên tài nguyên.
- Một hệ thống có thể kết hợp hai vai trò trong cùng sản phẩm, nhưng ranh giới logic và quyền quản trị vẫn cần rõ.

Không nên để resource server tự cấp token chỉ vì request có username hoặc API key hợp lệ. Cũng không nên để authorization server quyết định thay toàn bộ quyền truy cập đối tượng ở mọi API nếu resource server có dữ liệu nghiệp vụ cần kiểm tra.

## 2. Access token mang điều gì?

Access token đại diện cho quyền được cấp trong một phạm vi và thời gian nhất định. Nó thường liên kết với subject, client, audience, scope và thời hạn. Token không nhất thiết chứng minh người dùng đã nhập mật khẩu trực tiếp vào resource server.

Các claim/thuộc tính thường gặp:

| Claim / field | Ý nghĩa | Resource server cần làm gì |
| --- | --- | --- |
| `iss` | Issuer phát hành token | Chỉ tin issuer đã được cấu hình/onboard |
| `sub` | Subject mà token đại diện | Ánh xạ tới principal ổn định trong đúng issuer/tenant |
| `aud` | Resource/API được token cấp cho | Bắt buộc khớp API hoặc audience được cho phép |
| `exp` | Thời điểm token hết hạn | Từ chối sau hạn, có clock skew nhỏ theo policy |
| `nbf` | Thời điểm token bắt đầu có hiệu lực | Không chấp nhận trước thời điểm đó |
| `iat` | Thời điểm token được phát hành | Có thể dùng để đánh giá tuổi token và policy |
| `jti` | ID token | Có thể hỗ trợ denylist hoặc điều tra replay |
| `scope` | Quyền dạng scope được cấp | Ánh xạ thành authority và kiểm tra endpoint/action |
| `client_id` / `azp` | Client được cấp hoặc được ủy quyền | Áp dụng policy theo client khi cần |
| `tenant` / organization claim | Phạm vi tổ chức | Chỉ tin claim theo profile đã xác minh; kiểm tra tenant của tài nguyên |
| `cnf` | Thông tin ràng buộc token với khóa/chứng chỉ trong một số profile | Xác minh proof-of-possession tương ứng nếu token yêu cầu |

Không phải access token nào cũng có đầy đủ các trường trên. Opaque token có thể không hiển thị claim cho client hoặc resource server; resource server tra trạng thái qua introspection. JWT cũng có thể dùng profile riêng. Hãy triển khai theo hợp đồng token đã thống nhất với issuer, không đoán cấu trúc từ một token mẫu.

### Không nhầm access token với ID token

ID token trong OpenID Connect cho client biết kết quả xác thực của người dùng. Access token dành cho resource server để gọi API. Một ID token có chữ ký hợp lệ nhưng audience là client web không phải là access token hợp lệ cho Orders API. Resource server phải từ chối token sai loại hoặc sai audience, ngay cả khi chữ ký của nó hợp lệ.

### Token là bearer credential

Với bearer token, bên nào nắm được token có thể sử dụng token trong phạm vi và thời hạn được cấp. Do đó:

- Chỉ truyền token trong header Authorization qua HTTPS.
- Không đặt token trong URL, query string, fragment, log hoặc analytics.
- Không gửi token tới host hoặc API không thuộc audience.
- Giữ token trong nơi lưu phù hợp với loại client; giảm khả năng XSS, malware và crash dump làm lộ token.
- Dùng access token thời hạn hợp lý; cân nhắc sender-constrained token nếu rủi ro yêu cầu.

## 3. Pipeline xác minh tại resource server

Một resource server an toàn không dừng ở việc parse token hoặc kiểm tra một chữ ký. Pipeline điển hình:

~~~mermaid
flowchart TD
    A[Nhận API request] --> B[Đọc Authorization Bearer]
    B --> C[Kiểm tra cú pháp và giới hạn đầu vào]
    C --> D[Chọn validator theo token profile]
    D --> E[Verify signature hoặc introspection]
    E --> F[Kiểm tra issuer, audience, thời hạn, loại token]
    F --> G[Kiểm tra trạng thái / revocation nếu policy yêu cầu]
    G --> H[Dựng principal và authorities]
    H --> I[Authorization endpoint và object-level]
    I --> J[Thực thi nghiệp vụ]
~~~

Thứ tự thực tế có thể thay đổi một số bước để tối ưu, nhưng **không được sử dụng claim chưa xác minh để cấp quyền hoặc truy cập dữ liệu**. Resource server cần xác định token profile trước khi tin cấu trúc, sau đó áp dụng mọi validation rule bắt buộc.

### Các bước chính

1. **Nhận token:** lấy từ header Authorization theo định dạng Bearer hoặc cơ chế sender-constrained đã cấu hình. Từ chối nhiều nguồn token mơ hồ.
2. **Xác định kiểu token:** JWT, opaque hoặc profile khác theo endpoint/issuer; không chọn verifier dựa trên dữ liệu không tin cậy một cách tùy tiện.
3. **Xác minh mật mã/trạng thái:** JWT thì xác minh chữ ký bằng key được tin cậy; opaque thì introspect hoặc tra trạng thái.
4. **Xác minh ngữ cảnh:** issuer, audience, thời hạn, token type/profile, client và các claim bắt buộc.
5. **Kiểm tra thu hồi:** denylist, introspection, session/account version hoặc policy tương ứng nếu cần cắt quyền trước hạn.
6. **Dựng principal:** lấy subject, tenant, client và authorities từ token đã xác minh hoặc phản hồi introspection đáng tin.
7. **Phân quyền:** kiểm tra scope/role và quyền trên object, tenant, trạng thái nghiệp vụ.
8. **Thực thi:** chỉ thực hiện thao tác sau khi tất cả kiểm tra đạt; ghi audit phù hợp và không log token.

## 4. Xác minh JWT access token

JWT thường gồm header, payload và signature. Payload được Base64url-encode chứ không được mã hóa mặc định; người có token có thể đọc claim. Chữ ký bảo vệ tính toàn vẹn và nguồn phát hành theo khóa được tin cậy.

### 4.1. Xác minh chữ ký và thuật toán

Resource server phải:

- Chọn thuật toán được phép từ cấu hình server, không tin thuật toán tùy ý trong JWT header.
- Từ chối thuật toán không hỗ trợ hoặc không được policy cho phép; tuyệt đối không chấp nhận `alg=none` cho token cần chữ ký.
- Dùng khóa gắn với issuer đã cấu hình, thường lấy từ JWKS endpoint tin cậy.
- Xác minh chữ ký trước khi tin các claim trong payload.
- Không tải khóa từ URL do token không tin cậy tự khai như `jku`/`x5u`, trừ khi profile có cơ chế cho phép được kiểm soát chặt.
- Kiểm tra key type, thuật toán và mục đích sử dụng phù hợp; tránh algorithm confusion.

### 4.2. Issuer và audience

`iss` xác định authorization server phát hành token. `aud` xác định resource server hoặc tập resource mà token được cấp cho. Hai giá trị này phải được kiểm tra riêng:

- Chỉ chấp nhận issuer nằm trong trust configuration của API.
- Audience phải chứa identifier chính xác của resource server hiện tại hoặc khớp profile được triển khai.
- Không chấp nhận token chỉ vì chữ ký hợp lệ nếu `aud` thuộc API khác.
- Trong hệ thống nhiều issuer, không để token từ issuer A được xác minh bằng khóa hoặc policy của issuer B.
- Với nhiều audience, áp dụng quy tắc `azp`/authorized party theo token profile nếu có.

Audience restriction giúp ngăn token substitution: token cấp cho API hồ sơ không được tự động dùng ở API thanh toán.

### 4.3. Thời gian và token type

Kiểm tra `exp` và `nbf` nếu có; có thể cho phép clock skew nhỏ để xử lý sai lệch đồng hồ, nhưng phải giới hạn và giám sát. `iat` có thể được dùng để giới hạn tuổi token hoặc phát hiện token bất thường. Không nới thời hạn quá rộng chỉ để tránh lỗi đồng hồ.

Nếu issuer phát JWT access token theo profile OAuth, resource server nên kiểm tra token type/profile theo hợp đồng, chẳng hạn `typ` phù hợp với access token khi profile yêu cầu. Không dùng chung một decoder permissive cho ID token, access token, logout token và các JWT nghiệp vụ khác.

### 4.4. Scope và claim

Sau khi token hợp lệ, resource server chuyển scope thành quyền có thể kiểm tra. Ví dụ:

| Scope | Ý nghĩa minh họa | API có thể yêu cầu |
| --- | --- | --- |
| `orders.read` | Đọc đơn hàng | GET `/api/orders/**` |
| `orders.write` | Tạo/cập nhật đơn hàng | POST/PATCH `/api/orders/**` |
| `payments.refund` | Yêu cầu hoàn tiền | POST `/api/payments/*/refund` |
| `profile.read` | Đọc hồ sơ | GET `/api/profile` |

Scope là quyền được cấp ở mức coarse-grained. Nó không nhất thiết cho phép truy cập mọi object cùng loại. Ví dụ, `orders.read` không có nghĩa người dùng được đọc đơn hàng của mọi khách hàng; cần kiểm tra owner/tenant ở tầng dữ liệu.

## 5. JWKS và quản lý signing key

JWT verifier thường nhận public key từ JWKS (JSON Web Key Set) của issuer. Token header có `kid` để gợi ý key tương ứng. Resource server cần có chính sách cache và rollover rõ ràng.

### Quy trình key selection

1. Chọn issuer theo cấu hình tin cậy hoặc transaction/resource policy.
2. Lấy JWKS từ endpoint được cấu hình cho issuer đó qua HTTPS có xác minh TLS.
3. Chọn key theo `kid`, key type, algorithm và metadata phù hợp.
4. Xác minh chữ ký.
5. Nếu `kid` chưa biết, có thể refresh JWKS một lần có giới hạn và rate limit; nếu vẫn không tìm thấy thì từ chối.

Không gọi JWKS URL tùy ý từ token header; điều đó có thể tạo SSRF hoặc khiến API tin khóa của attacker. Không refresh vô hạn khi nhận nhiều `kid` lạ, vì attacker có thể làm cạn issuer hoặc resource server.

### Rotation và cache

Issuer có thể công bố khóa mới trước khi ký token bằng khóa đó, rồi ngừng khóa cũ sau khi các token cũ hết hạn. Resource server nên:

- Cache JWKS theo HTTP cache headers/TTL hợp lý và hỗ trợ refresh có giới hạn.
- Chấp nhận overlap khóa cũ/mới theo trust policy trong thời gian rollover có kế hoạch.
- Không tiếp tục tin key đã bị loại khỏi trust policy vô thời hạn chỉ vì cache cũ.
- Xử lý outage JWKS: chỉ dùng key đã cache nếu vẫn được policy tin cậy và token qua mọi kiểm tra; không bỏ chữ ký.
- Theo dõi `kid` lạ, lỗi signature, tuổi cache và sự kiện đổi key.

Nếu signing key bị compromise, cần emergency distrust/rotation, đánh giá token đã ký trong khoảng ảnh hưởng và cập nhật verifier. Xoay khóa ký không giống thu hồi một token cụ thể; nó có thể ảnh hưởng nhiều token cùng lúc.

## 6. Opaque token và introspection

Opaque token thường là chuỗi ngẫu nhiên, không chứa claim có thể đọc trực tiếp. Resource server gửi token tới introspection endpoint của authorization server qua kênh xác thực. AS trả về trạng thái active và các thuộc tính được phép chia sẻ.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource server
    participant AS as Authorization server
    C->>RS: Request + opaque access token
    RS->>AS: Introspection request qua TLS và client auth
    AS->>AS: Kiểm tra token, grant, trạng thái và expiry
    AS-->>RS: active, sub, aud, scope, exp...
    RS->>RS: Kiểm tra audience, scope và quyền object
    RS-->>C: Response API
~~~

Phản hồi `active=true` cho biết token còn active theo issuer tại thời điểm introspection; resource server vẫn cần kiểm tra audience, scope, tenant và quyền nghiệp vụ. Không được coi `active=true` là quyền truy cập toàn bộ API.

### Bảo vệ introspection

- Chỉ resource server được đăng ký/ủy quyền mới được gọi endpoint.
- Dùng client authentication phù hợp, chẳng hạn private_key_jwt, mTLS hoặc client secret được bảo vệ theo policy.
- Không gửi token trong URL; dùng POST qua HTTPS.
- Không log token request/response.
- Cache kết quả chỉ trong TTL phù hợp với ngân sách revocation latency.
- Xác định fail-open/fail-closed khi AS hoặc network không khả dụng.

Opaque token giúp thu hồi tập trung dễ hơn, nhưng phụ thuộc availability và độ trễ introspection. Cache quá lâu có thể khiến token đã revoke vẫn được chấp nhận.

## 7. Tạo principal và ánh xạ authority

Sau khi xác minh token, resource server dựng principal. Principal là danh tính được API sử dụng trong authorization; nó phải đến từ token đã xác minh hoặc introspection response đáng tin.

Một principal nội bộ có thể gồm:

| Thuộc tính | Nguồn | Cách dùng |
| --- | --- | --- |
| `issuer` | Claim `iss` đã xác minh | Namespace cho subject và trust policy |
| `subject` | Claim `sub` đã xác minh | Định danh user/service trong issuer |
| `clientId` | Claim/profile được xác minh | Policy theo client hoặc workload |
| `tenantId` | Claim được tin theo profile hoặc mapping server-side | Cô lập dữ liệu tổ chức |
| `scopes` | Claim scope/introspection | Quyền coarse-grained |
| `roles` | Mapping từ group/claim theo policy | Quyền ứng dụng; không tin claim tùy ý |
| `tokenId` | `jti` nếu có | Audit, denylist hoặc điều tra |
| `authContext` | Claim assurance theo profile | Step-up hoặc policy nhạy cảm khi được hỗ trợ |

Không dùng email làm principal key duy nhất nếu email có thể thay đổi hoặc trùng giữa issuer. Với federation, định danh ổn định thường phải giữ cả issuer và subject. Với service account, định danh cần gắn với workload/client đã được cấp quyền.

### Scope mapping

Ví dụ, scope `orders.read` có thể được ánh xạ thành authority nội bộ `SCOPE_orders.read`. Endpoint GET kiểm tra authority đó. Nhưng việc mapping cần nhất quán giữa issuer và API; không tự động biến mọi group claim thành role quản trị.

Nếu issuer dùng claim dạng array, space-separated string hoặc nested claim, parser phải theo đúng profile. Không cho client tự gửi header như `X-User`, `X-Roles`, `X-Tenant` để ghi đè principal đã xác minh. Nếu gateway truyền principal xuống backend qua header nội bộ, phải xác thực gateway, xóa header cùng tên từ request bên ngoài và bảo vệ hop nội bộ.

## 8. Authorization: scope không thay thế kiểm tra tài nguyên

Resource server thực hiện ít nhất hai lớp authorization:

1. **Endpoint/function-level:** token có scope hoặc authority cần thiết cho thao tác không?
2. **Object/resource-level:** principal có quyền trên tài nguyên cụ thể trong tenant/phạm vi hiện tại không?

Ví dụ:

~~~text
Token hợp lệ:
  sub = user-42
  tenant = org-a
  scope = orders.read

Request:
  GET /api/orders/order-900

Policy:
  - cần scope orders.read
  - order-900 phải thuộc tenant org-a
  - user-42 phải là owner hoặc có quyền support được cấp
~~~

Nếu chỉ kiểm tra scope, user-42 có thể thử thay ID đơn hàng để đọc dữ liệu của người khác. Đây là lỗi Broken Object Level Authorization (BOLA/IDOR). Hãy kiểm tra quyền ở service/repository theo principal và object đang truy cập, không dựa vào việc ID khó đoán.

### Multi-tenant isolation

Với API nhiều tenant:

- Tenant phải được lấy từ claim/mapping đã xác minh hoặc context server-side đáng tin.
- Không dùng tenant ID trong path/body làm căn cứ duy nhất để quyết định phạm vi quyền.
- Mọi truy vấn dữ liệu phải áp dụng tenant constraint.
- Kiểm tra resource thực sự thuộc tenant đã xác định; không chỉ kiểm tra tenant claim có mặt.
- Không ánh xạ group/role từ issuer khác nhau vào cùng role nếu chưa có policy.
- Kiểm thử token của tenant A truy cập resource tenant B.

### Quyền service-to-service

Client credentials flow thường cấp token đại diện cho ứng dụng/workload, không có người dùng cuối. Resource server cần phân biệt token user và token workload, kiểm tra client identity, audience và scope. Không giả định mọi token có `sub` đều là người dùng; theo profile, subject có thể là client hoặc service principal.

## 9. Xử lý token theo HTTP và lỗi chuẩn

Với bearer token, client thường gửi:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
~~~

Không nhận bearer token qua query string vì URL có thể xuất hiện trong browser history, reverse proxy log, analytics và Referer. Tránh nhận token đồng thời qua nhiều kênh; nếu header và cookie chứa hai token khác nhau, từ chối hoặc áp dụng một contract duy nhất.

### 401 và 403

| Trạng thái | Ý nghĩa thường dùng | Ví dụ |
| --- | --- | --- |
| `401 Unauthorized` | Không có credential hợp lệ hoặc token không được chấp nhận | Token thiếu, sai chữ ký, hết hạn, sai issuer/audience |
| `403 Forbidden` | Đã xác thực nhưng không đủ quyền | Token hợp lệ nhưng thiếu scope hoặc không sở hữu resource |

Với bearer token, response có thể dùng `WWW-Authenticate: Bearer` và error code phù hợp như `invalid_token` hoặc `insufficient_scope` theo RFC 6750. Không trả chi tiết nhạy cảm như public key nội bộ, token claim đầy đủ hoặc stack trace cho client.

### CORS không phải xác thực

CORS kiểm soát việc browser JavaScript đọc response cross-origin; nó không thay thế việc xác minh access token. Một request có thể đến resource server dù browser không cho script đọc response. Resource server vẫn phải xác thực token và authorization cho mọi request, bất kể CORS.

## 10. Thu hồi token và trạng thái hiện tại

JWT access token tự chứa có thể tiếp tục được xác minh chữ ký tới `exp`, ngay cả khi authorization server đã đánh dấu token bị thu hồi. Resource server cần chọn cơ chế theo mức rủi ro:

- Access token ngắn hạn để giới hạn thời gian còn hiệu lực.
- Introspection để hỏi trạng thái tập trung.
- Denylist theo `jti` hoặc token identifier.
- Session/account version hoặc credential version được kiểm tra tại request.
- Sender-constrained token để giảm khả năng sử dụng token bị đánh cắp.

### Ngân sách revocation latency

Định nghĩa thời gian từ lúc issuer commit revoke đến lúc resource server cuối cùng từ chối token. Độ trễ có thể đến từ:

- cache JWKS hoặc introspection;
- denylist replication;
- event bus hoặc consumer bị trễ;
- account/session version stale;
- gateway cache principal;
- long-lived connection hoặc session context.

Đặt mục tiêu cụ thể theo rủi ro và kiểm thử từ nhiều replica/region. Không tuyên bố thu hồi tức thời nếu verifier có cache stale không giới hạn.

### Fail-open và fail-closed

Nếu introspection hoặc trạng thái revoke không truy cập được:

- **Fail-closed:** từ chối request khi không thể xác minh trạng thái cần thiết; phù hợp API thanh toán, dữ liệu nhạy cảm hoặc thao tác quản trị.
- **Degraded mode có kiểm soát:** cho phép một số request ít rủi ro dựa trên token đã xác minh và thời hạn còn lại; phải giới hạn rõ.
- **Fail-open tùy tiện:** chấp nhận mọi token vì AS lỗi; không nên dùng.

Quyết định phải được ghi trong threat model và cấu hình endpoint theo mức nhạy cảm, không để default của thư viện quyết định thay sản phẩm.

## 11. Sender-constrained token: giảm rủi ro bearer theft

Bearer token chỉ cần bị lấy là có thể bị sử dụng. Một số profile ràng buộc token với khóa/chứng chỉ của client để yêu cầu proof-of-possession.

### mTLS-bound access token

Authorization server phát token gắn với certificate của client. Resource server xác minh TLS client certificate và kiểm tra claim confirmation (`cnf`) trong token theo profile. Token bị sao chép sang thiết bị không có private key tương ứng sẽ không đủ để gọi API.

### DPoP

Demonstrating Proof of Possession (DPoP) dùng khóa bất đối xứng phía client để tạo proof cho request. Resource server kiểm tra chữ ký proof, method/URI, thời gian, proof ID và ràng buộc với access token theo profile. DPoP giảm nguy cơ token bị lấy riêng lẻ, nhưng không bảo vệ nếu attacker kiểm soát endpoint hoặc private key của client.

Không tự phát minh proof format. Dùng thư viện và profile chuẩn, kiểm tra nonce nếu server yêu cầu, chống replay proof và ràng buộc đúng URI/method. Sender constraint bổ sung cho token validation; không thay issuer/audience/scope checks hoặc revocation.

## 12. Ví dụ cấu hình Spring Security Resource Server

Ví dụ dưới đây minh họa API dùng JWT access token. Cần dùng Spring Security phiên bản được hỗ trợ và cấu hình issuer/audience theo môi trường thực tế.

~~~java
@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        // Chỉ tắt CSRF khi API thực sự chỉ dùng Authorization bearer header
        // và không dựa vào cookie tự động gửi từ trình duyệt.
        http.csrf(csrf -> csrf.disable());
        return http.build();
    }
}
~~~

Spring Security có thể xác minh JWT theo issuer và JWKS qua cấu hình resource server. Tuy nhiên, ứng dụng cần bổ sung validator audience và các claim/policy riêng; không giả định cấu hình tối thiểu đã đáp ứng mọi yêu cầu.

Ví dụ validator audience:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://auth.example.com";
    String requiredAudience = "orders-api";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withIssuerLocation(issuer)
        .build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        OAuth2Error error = new OAuth2Error(
            "invalid_token", "Required audience is missing", null
        );
        return OAuth2TokenValidatorResult.failure(error);
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience)
    );
    return decoder;
}
~~~

Đoạn cấu hình là ví dụ khởi điểm. Cần xác minh cách phiên bản Spring Security đang dùng xử lý thuật toán, token type, claim tùy biến và key rollover; thêm validator cho profile access token và policy tenant nếu cần. Nếu API dùng cookie session thay vì bearer-only, không tắt CSRF theo mẫu này.

### Opaque token trong Spring Security

Spring Security cũng hỗ trợ opaque token qua introspection. Cấu hình cần chỉ rõ introspection URI, client authentication và mapping authority. Secret/client credential phải được nạp từ secret manager hoặc cấu hình bảo mật, không hardcode trong source code.

~~~java
http.oauth2ResourceServer(oauth -> oauth
    .opaqueToken(opaque -> opaque
        .introspectionUri("https://auth.example.com/oauth2/introspect")
        .introspectionClientCredentials(
            introspectionClientId,
            introspectionClientSecret
        )
    )
);
~~~

Trong production, hãy quản lý timeout, retry, cache policy và failure mode của introspection. Không cache `active=true` lâu hơn ngân sách thu hồi đã cam kết.

## 13. Những lỗi resource server thường gặp

| Lỗi | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Chỉ kiểm tra chữ ký JWT | Token đúng chữ ký nhưng sai issuer/audience vẫn được chấp nhận | Kiểm tra issuer, audience, expiry, type và profile |
| Dùng ID token gọi API | Token dành cho client bị chấp nhận ở resource server | Phân biệt token type/profile và audience |
| Chấp nhận `alg=none` hoặc thuật toán không mong muốn | Bypass/algorithm confusion | Allowlist thuật toán ở server, dùng thư viện chuẩn |
| Lấy JWKS URL từ token không tin cậy | SSRF hoặc tin khóa attacker | JWKS endpoint cấu hình theo issuer đã onboard |
| Không giới hạn refresh JWKS khi `kid` lạ | DoS vào resource server/issuer | Refresh có rate limit và cache |
| Không kiểm tra audience | Token cấp cho API khác bị dùng lại | Audience riêng cho từng resource server |
| Tin scope mà không kiểm tra object | BOLA/IDOR, đọc dữ liệu người khác | Object-level và tenant authorization |
| Tin role/tenant từ header client | Client tự nâng quyền hoặc đổi tenant | Principal từ token đã xác minh/server-side mapping |
| Không xử lý revoke | JWT bị đánh cắp vẫn dùng tới exp | Introspection/denylist/version/short TTL theo risk |
| Cache trạng thái quá lâu | Token đã revoke vẫn được chấp nhận | TTL/invalidation theo revocation latency |
| Log Authorization header | Token bị lộ qua log/trace | Redact token và cookie ở mọi lớp |
| Chấp nhận token qua query string | Token xuất hiện trong URL/history/referrer | Chỉ nhận qua header hoặc profile được thiết kế rõ |
| Tắt CSRF trong API dùng cookie | Request cross-site có thể thực hiện hành động | Chỉ tắt khi bearer-only; nếu cookie, giữ CSRF defense |
| Fail-open khi introspection lỗi | Token revoke có thể vẫn được dùng | Fail-closed cho endpoint nhạy cảm |
| Dùng một key/issuer config cho mọi tenant | Trust boundary bị trộn | Cấu hình issuer/tenant rõ, không tin issuer tùy ý |

## 14. Kiểm thử resource server

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| JWT đúng chữ ký, issuer và audience | Được xác minh; authorization vẫn được kiểm tra |
| JWT sai chữ ký hoặc key không tin cậy | `401`, không tạo principal |
| JWT `iss` khác issuer được cấu hình | Từ chối |
| JWT `aud` không chứa API hiện tại | Từ chối |
| JWT hết hạn hoặc chưa tới `nbf` | Từ chối theo clock policy |
| ID token có chữ ký đúng nhưng sai audience/type | Từ chối |
| JWT dùng thuật toán ngoài allowlist hoặc `none` | Từ chối |
| `kid` mới sau JWKS rollover | Refresh có giới hạn; chấp nhận chỉ sau khi xác minh key mới |
| JWKS endpoint timeout và cache có key tin cậy còn hiệu lực | Chỉ tiếp tục theo policy cache; không bỏ signature validation |
| Opaque token `active=false` | Từ chối |
| Introspection endpoint lỗi | Áp dụng fail-closed/degraded policy đã định nghĩa |
| Token hợp lệ nhưng thiếu scope | `403`/`insufficient_scope` |
| Scope đúng nhưng object thuộc tenant khác | Từ chối truy cập object |
| Token đã revoke nhưng JWT signature vẫn đúng | Từ chối theo cơ chế revocation nếu endpoint yêu cầu |
| Token bị gửi trong query string | Từ chối hoặc không hỗ trợ kênh này; không ghi URL có token vào log |
| Token từ client credentials flow gọi endpoint chỉ dành cho user | Từ chối theo principal type/policy |
| Client gửi `X-User` hoặc `X-Role` giả | Không ảnh hưởng principal/authority |
| Resource server nhận duplicate Authorization header | Từ chối request mơ hồ |
| DPoP proof replay hoặc method/URI sai | Từ chối proof/token |
| Log, tracing và exception | Không chứa raw access token hoặc refresh token |

### Tình huống thực hành

Một hệ thống có hai API: `profile-api` và `payments-api`. Authorization server phát JWT có scope `profile.read` và audience `profile-api`. Do dùng chung decoder chỉ kiểm tra chữ ký, `payments-api` cũng chấp nhận token này. Endpoint hoàn tiền chỉ kiểm tra người gọi đã authenticated, không kiểm tra scope hoặc quyền trên payment. Một người dùng có thể gửi token profile tới payments API và gọi refund.

**Yêu cầu:** xác định lỗi và đề xuất sửa thiết kế.

**Hướng giải:**

1. Cấu hình audience riêng cho từng resource server; payments API chỉ chấp nhận token có audience `payments-api`.
2. Kiểm tra issuer, chữ ký, thuật toán, expiry, nbf và token profile; không chỉ kiểm tra signature.
3. Endpoint refund yêu cầu scope phù hợp như `payments.refund` và policy assurance/step-up nếu nghiệp vụ yêu cầu.
4. Kiểm tra principal có quyền trên payment cụ thể, tenant, trạng thái giao dịch và giới hạn nghiệp vụ.
5. Phân biệt user token với client credentials/service token; không để workload token tự động đại diện cho người dùng.
6. Dùng TTL, introspection/denylist hoặc session state phù hợp với yêu cầu thu hồi; không log bearer token.
7. Thêm test token profile audience của profile-api gọi payments-api phải bị từ chối trước khi chạy nghiệp vụ.

## 15. Câu hỏi tự kiểm tra

1. **Resource server khác authorization server thế nào?** Authorization server cấp token; resource server xác minh token và bảo vệ API/tài nguyên.
2. **Vì sao chữ ký JWT hợp lệ chưa đủ?** Cần kiểm tra issuer, audience, thời hạn, token type/profile, trạng thái và quyền.
3. **Vì sao không dùng ID token làm access token?** ID token dành cho client để biểu diễn kết quả xác thực; access token dành cho resource server với audience/scope phù hợp.
4. **Opaque token được xác minh thế nào?** Resource server thường gọi introspection hoặc tra trạng thái tại authorization server/kho dữ liệu tin cậy.
5. **Scope có đủ để bảo vệ object không?** Không. Cần kiểm tra owner, tenant và quyền trên tài nguyên cụ thể.
6. **JWT bị revoke có tự mất hiệu lực mật mã không?** Không. Resource server cần cơ chế trạng thái, denylist, introspection hoặc thời hạn ngắn phù hợp.
7. **CORS có thay thế token validation không?** Không. Mọi request vẫn phải xác minh token và authorization phía server.
8. **mTLS/DPoP giải quyết vấn đề gì?** Ràng buộc token với khóa/chứng chỉ của client để giảm nguy cơ bearer token bị đánh cắp rồi dùng ở nơi khác.

**Ghi nhớ:** Resource server là nơi biến access token thành quyết định truy cập API. Hãy xác minh **đúng issuer, audience, chữ ký/trạng thái, thời hạn và token profile**, dựng principal từ dữ liệu đã tin cậy, kiểm tra scope cùng quyền trên từng tài nguyên, và quản lý thu hồi/cache theo độ trễ cam kết. Token hợp lệ không đồng nghĩa mọi hành động đều được phép.

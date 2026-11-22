# Chặn endpoint hoặc client theo phạm vi nhỏ nhất

Trong chương **Incident response API** của module `SECURITY_API_SECURITY`, containment là bước giới hạn tác động khi một API, credential, client hoặc luồng nghiệp vụ đang bị khai thác. Mục tiêu là ngăn hành vi nguy hiểm tiếp tục xảy ra trong khi vẫn giữ các chức năng không liên quan hoạt động bình thường. Nếu chỉ biết một client bị lộ API key mà tắt toàn bộ API, hệ thống có thể gây gián đoạn lớn hơn sự cố ban đầu. Nếu chỉ chặn một IP trong khi attacker dùng nhiều credential hoặc proxy, containment lại không đủ hiệu quả.

Hãy chọn điểm chặn nhỏ nhất có thể chứng minh là đủ: một credential, một OAuth client, một operation, một route/version, một tenant, một loại side effect hoặc một dependency. Phạm vi phải được xác định bằng evidence, áp dụng ở enforcement point thực sự bảo vệ request, có người sở hữu, có thời hạn xem xét và có cách xác minh rằng đường vòng không còn hoạt động.

Containment không phải là thay thế cho điều tra nguyên nhân hoặc khắc phục lỗ hổng. Nó là biện pháp tạm thời có kiểm soát để giảm thiệt hại, bảo toàn khả năng vận hành và tạo thời gian sửa lỗi an toàn.

## 1. Vì sao cần containment theo phạm vi nhỏ nhất?

Một API thường phục vụ nhiều client, tenant và operation trên cùng hạ tầng. Một incident có thể chỉ ảnh hưởng một phần nhỏ của bề mặt đó:

- Một đối tác làm lộ API key dùng riêng cho integration của họ.
- Một endpoint export có lỗi object authorization nhưng các endpoint đọc/ghi khác vẫn an toàn.
- Một OAuth client bị compromise nhưng các client khác dùng cùng API vẫn bình thường.
- Một tenant bị lạm dụng endpoint tạo báo cáo tốn chi phí.
- Một version cũ chưa có validation mới, trong khi version mới đã được vá.
- Một outbound integration đang bị lợi dụng để SSRF tới dải mạng nội bộ.
- Một loại mutation gây side effect trùng do retry, nhưng read operation không bị ảnh hưởng.

Nếu containment quá rộng, hệ quả có thể gồm ngừng dịch vụ cho khách hàng không liên quan, làm gián đoạn giao dịch đang chạy, phá vỡ SLA, tạo backlog hoặc cản trở điều tra. Nếu containment quá hẹp, attacker có thể đổi credential, route alias, tenant context hoặc phương thức gọi để tiếp tục khai thác.

### 1.1. Nguyên tắc chọn phạm vi

1. **Chặn đúng hành vi có hại:** xác định operation, action, resource và side effect bị khai thác.
2. **Ràng buộc theo danh tính đã xác minh:** dùng credential/client/workload identity do server xác thực, không tin `clientId` tự khai trong body/header.
3. **Thu hẹp theo bằng chứng:** chỉ giới hạn tenant, client hoặc route khi có dữ liệu hỗ trợ phạm vi đó.
4. **Giữ nguyên invariant bảo mật:** không mở một lối đi yếu hơn để duy trì availability.
5. **Có thể quan sát và hoàn tác:** mọi thay đổi containment cần audit, metric, owner và điều kiện gỡ bỏ.
6. **Mở rộng nhanh khi cần:** nếu evidence cho thấy phạm vi ban đầu không đủ, tăng mức chặn theo escalation criteria đã định.

### 1.2. Availability không được ưu tiên bằng cách bỏ authorization

Trong incident, có thể cần tạm dừng một operation hoặc chuyển sang chế độ read-only. Không nên bỏ object authorization, tenant isolation, signature verification hoặc authentication để “giữ API chạy”. Một fallback làm lộ dữ liệu hoặc cho phép ghi trái quyền có thể biến incident đang được khoanh vùng thành sự cố rộng hơn.

Nếu chưa thể xác minh quyền cho một thao tác nhạy cảm, fail closed cho thao tác đó và giữ các operation độc lập vẫn có thể được chứng minh an toàn.

## 2. Xác định đúng đối tượng cần chặn

Trước khi thay đổi gateway hoặc application, mô tả sự cố bằng các chiều có thể kiểm chứng. Không dùng từ chung chung như “API bị tấn công” làm phạm vi chặn.

### 2.1. Các chiều scope thường gặp

| Chiều | Ví dụ | Khi nào phù hợp |
|---|---|---|
| Credential | Một API key, refresh token, certificate fingerprint | Secret cụ thể bị lộ hoặc bị dùng trái phép |
| OAuth client/workload | `client_id` đã xác minh, service account, workload identity | Một ứng dụng/service bị compromise |
| Principal | User hoặc service principal cụ thể | Một danh tính thực hiện hành vi bất thường |
| Tenant/account | Một tenant hoặc customer account | Bằng chứng cho thấy hành vi hoặc dữ liệu chỉ liên quan tenant đó |
| Operation | `orders.export`, `users.invite`, `payment.refund` | Một chức năng có lỗi hoặc đang bị abuse |
| Route/method/version | `POST /v1/reports`, legacy alias | Một đường HTTP cụ thể bị khai thác |
| Resource scope | Một project, object family hoặc region | Lỗi chỉ tác động một nhóm resource và policy hỗ trợ giới hạn đó |
| Side effect/dependency | SMS send, export job, URL fetch, payment provider | Có thể dừng hành vi nguy hiểm ở downstream boundary |
| Network source | Egress IP, CIDR, mTLS peer | Chỉ khi nguồn mạng là tín hiệu đáng tin và ổn định |
| Global service | Toàn bộ API hoặc service | Chỉ khi không thể khoanh hẹp an toàn hoặc compromise có tính hệ thống |

### 2.2. Không nhầm client identity với header do caller tự khai

Header như `X-Client-Id`, `X-Tenant-Id`, `X-User-Id` hoặc field cùng tên trong JSON chỉ là input cho đến khi được ràng buộc với credential đã xác minh. Containment theo client phải dựa trên identity từ OAuth client authentication, API key registry, mTLS certificate mapping hoặc workload identity đã được kiểm tra.

Nếu gateway xác minh credential rồi inject một internal identity header, phải bảo đảm gateway xóa header cùng tên do Internet gửi vào và service chỉ nhận traffic qua trust boundary được bảo vệ. Nếu service có thể bị gọi trực tiếp, nó phải tự xác thực upstream hoặc dùng credential service-to-service; không tin header chỉ vì tên có tiền tố `X-Internal-`.

### 2.3. IP address chỉ là một tín hiệu

Chặn IP có thể hữu ích khi nguồn tấn công tập trung, nhưng IP có thể dùng chung qua NAT, proxy, mobile carrier hoặc thay đổi liên tục. Một attacker có thể chuyển IP; ngược lại, chặn một IP có thể làm gián đoạn nhiều khách hàng hợp lệ.

Ưu tiên credential/principal đã xác minh và behavior theo operation. Dùng IP/CIDR như lớp bổ sung khi có evidence, giới hạn thời gian và đánh giá collateral impact. Không dùng `X-Forwarded-For` do client gửi làm căn cứ block nếu proxy chain chưa được cấu hình và xác minh.

### 2.4. Phân biệt abuse với traffic hợp lệ tăng đột biến

Một tenant có thể tạo nhiều request do batch job, retry client hoặc chiến dịch kinh doanh. Trước khi disable client, đối chiếu operation, rate, error, credential, user-agent, thời điểm, deployment và business event. Nếu có thể, áp dụng quota/concurrency cap trước khi khóa toàn bộ client.

## 3. Chọn containment control nhỏ nhất đủ hiệu quả

Containment nên được áp dụng tại nơi có đủ ngữ cảnh và thực sự nằm trên mọi đường tới hành vi nguy hiểm. Có thể dùng nhiều lớp, nhưng mỗi lớp cần có lý do rõ.

### 3.1. Bảng quyết định

| Evidence | Control ưu tiên | Phạm vi dự kiến |
|---|---|---|
| Một API key cụ thể bị lộ | Revoke/rotate key; giữ client khác hoạt động | Credential |
| Một OAuth client bị compromise | Disable client hoặc thu hồi grant/token theo client | OAuth client |
| Một user bị chiếm tài khoản | Revoke session/refresh token, step-up hoặc disable principal | Principal |
| Một operation có BOLA/IDOR | Tạm dừng operation hoặc siết policy tại service boundary | Operation/resource |
| Một route version cũ bỏ qua control | Chặn route/version cũ sau khi xác minh alias | Route/version |
| Một tenant tạo tải bất thường | Tenant-scoped rate/concurrency/quota limit | Tenant + operation |
| URL fetch bị lợi dụng SSRF | Tạm disable URL-fetch operation hoặc deny destination class | Side effect/destination |
| Một provider gây retry storm | Circuit breaker/queue pause cho dependency đó | Dependency/queue |
| Nhiều service bị compromise qua cùng trust root | Disable trust root/credential family, có thể mở rộng global | Identity boundary |
| Không xác định được phạm vi và dữ liệu đang bị exfiltrate | Chặn operation nhạy cảm hoặc listener bị ảnh hưởng; escalation | Tạm thời rộng hơn |

### 3.2. Chặn credential trước khi chặn toàn client

Nếu client có nhiều credential và chỉ một key bị lộ, revoke đúng key. Nếu attacker có quyền tạo key mới hoặc compromise toàn bộ client secret, disable OAuth client/service account và xử lý các token/grant liên quan. Xác minh key rotation không làm mất bằng chứng hoặc vô tình giữ credential cũ còn hiệu lực.

### 3.3. Chặn operation trước khi chặn toàn API

Nếu endpoint export có lỗi, có thể tạm trả `503`/`404` theo contract cho operation đó, tắt chức năng export hoặc yêu cầu approval bổ sung. Các operation đọc/ghi không liên quan vẫn hoạt động nếu cùng security boundary đã được xác minh an toàn.

Chặn theo operation phải bao phủ mọi route alias, method, API version, GraphQL mutation, RPC method và background job có thể kích hoạt cùng side effect. Không chỉ chặn một path dễ thấy ở gateway.

### 3.4. Chặn tenant khi có bằng chứng tenant-scoped

Tenant-level containment phù hợp khi nguồn lạm dụng được xác định gắn với tenant đã xác minh. Áp dụng limit hoặc suspend trên tenant context do server xác thực. Không lấy tenant ID từ body hoặc query để chọn tenant bị chặn, vì attacker có thể đổi giá trị để tránh policy hoặc gây khóa nhầm khách hàng khác.

Nếu sự cố là lỗi cross-tenant authorization, cần xem xét toàn bộ operation và tenant có thể bị ảnh hưởng; chỉ khóa tenant gửi request bất thường không giải quyết được việc attacker đọc dữ liệu tenant khác.

### 3.5. Chặn side effect ở downstream boundary

Khi một API có thể tạo SMS, payment, export, webhook hoặc outbound URL fetch, có thể tạm dừng side effect đó bằng circuit breaker, queue pause, provider quota hoặc policy ở adapter. Cách này hữu ích khi request vẫn cần được nhận và lưu trạng thái nhưng không được thực hiện tác động bên ngoài.

Phải định nghĩa rõ API trả trạng thái gì: từ chối ngay, `202` với trạng thái pending, hay `503` để client thử lại. Không trả thành công nếu side effect chưa xảy ra; không retry tự động nếu outcome của lần gọi trước chưa rõ.

## 4. Runbook: từ phát hiện tới containment

Một runbook ngắn, rõ owner giúp tránh thao tác tùy hứng khi áp lực thời gian cao.

### 4.1. Bước 1 — Xác nhận tín hiệu và mức độ khẩn cấp

Thu thập những thông tin tối thiểu:

- Thời điểm bắt đầu và hệ thống phát hiện.
- API family, operation, method/path/version hoặc message type liên quan.
- Credential/client/principal/tenant đã xác minh nếu có.
- Dấu hiệu: access bất thường, data exposure, privilege escalation, SSRF, resource abuse hoặc side effect trùng.
- Số request, tỷ lệ thành công/thất bại, dữ liệu hoặc tenant có thể bị ảnh hưởng.
- Các deployment/config change gần thời điểm bắt đầu.

Không chờ có đầy đủ root cause mới containment nếu đang có exfiltration hoặc side effect nguy hiểm. Ghi rõ phần nào đã xác minh, phần nào là giả thuyết.

### 4.2. Bước 2 — Bảo toàn evidence trước và trong thay đổi

Lưu các log/audit/trace liên quan theo retention và incident procedure; snapshot cấu hình gateway, policy, key registry và deployment version trước khi sửa nếu có thể. Ghi thời điểm, người thực hiện và thay đổi. Không export payload nhạy cảm sang ticket/chat không được bảo vệ.

Nếu credential có khả năng đã lộ, không sao chép giá trị secret vào incident note. Ghi fingerprint/key ID hoặc reference an toàn. Nếu cần thu hồi khẩn cấp, ưu tiên revoke trước khi hoàn tất mọi phân tích.

### 4.3. Bước 3 — Viết containment statement

Trước khi áp dụng, mô tả bằng một câu có thể kiểm chứng:

> Chặn `POST /v2/reports/export` cho OAuth client đã xác minh `reporting-partner-17` vì credential của client này bị lộ; các client khác và operation đọc report vẫn được phép theo policy hiện hành.

Một containment statement tốt chỉ rõ:

- Điều gì bị chặn.
- Ai/điều kiện nào bị chặn.
- Ở enforcement point nào.
- Vì sao evidence hỗ trợ scope đó.
- Owner và thời gian đánh giá lại.
- Test nào chứng minh chặn đúng và không ảnh hưởng ngoài phạm vi.

### 4.4. Bước 4 — Áp dụng control và xác minh ngay

Sau khi thay đổi:

1. Gọi request bằng credential/client/operation bị chặn trong môi trường kiểm thử hoặc canary được phép.
2. Gọi request bằng client/operation không liên quan để xác minh không bị chặn nhầm.
3. Thử alias/version/method hoặc đường async tương đương.
4. Kiểm tra downstream side effect đã dừng hoặc bị giới hạn.
5. Kiểm tra metric, audit và log cho thấy policy mới thực sự có hiệu lực.

Không kết luận containment thành công chỉ vì control plane báo “configuration updated”. Cần bằng chứng từ data plane hoặc request thực tế.

### 4.5. Bước 5 — Theo dõi và điều chỉnh scope

Theo dõi request bị chặn, request hợp lệ bị ảnh hưởng, queue backlog, provider cost, error rate và dấu hiệu attacker chuyển sang credential/route khác. Nếu attacker đổi đường, mở rộng scope có mục tiêu. Nếu có false positive, điều chỉnh theo evidence và audit thay đổi; không tắt toàn bộ control để giảm alert noise.

## 5. Containment theo credential và client identity

Credential compromise thường cần hành động nhanh vì attacker có thể tiếp tục gọi API như client hợp lệ.

### 5.1. API key

Khi một API key bị lộ:

1. Xác định key bằng key ID/fingerprint trong secret registry, không tìm bằng cách copy secret vào log.
2. Revoke key bị lộ tại nơi xác thực thực tế.
3. Kiểm tra key có được dùng ở nhiều integration/tenant không.
4. Phát hành key mới qua kênh secret delivery an toàn cho owner hợp lệ.
5. Theo dõi request từ key cũ và mới, bao gồm cache hoặc replica có thể còn trạng thái cũ.
6. Kiểm tra key cũ không còn được chấp nhận ở gateway, application hoặc service phụ.

Không tạo một key mới nhưng để key cũ hoạt động vô thời hạn. Nếu cần overlap để migration, đặt thời hạn ngắn, scope hạn chế và cảnh báo khi key cũ tiếp tục được dùng.

### 5.2. OAuth 2.0 client

Nếu `client_id` hoặc client secret bị compromise, disable client hoặc thu hồi credential/grant theo khả năng của authorization server. Kiểm tra access token đã phát hành:

- Token opaque có thể được vô hiệu qua introspection/session state nếu resource server kiểm tra trạng thái.
- JWT stateless có thể còn hiệu lực tới `exp` nếu resource server chỉ kiểm tra chữ ký/claim. Cần đánh giá denylist theo `jti`, client block policy, token lifetime hoặc introspection để thu hồi sớm.
- Refresh token cần revoke/rotate; phát hiện reuse nếu hệ thống hỗ trợ.
- Client credentials grant cần rotate secret hoặc certificate và xác minh mọi replica nhận cấu hình mới.

Không giả định disable client tự động vô hiệu mọi access token đã phát hành. Xác minh semantics thực tế của authorization server và resource server.

### 5.3. mTLS certificate và workload identity

Khi certificate bị lộ, revoke certificate/serial hoặc cập nhật trust policy và kiểm tra OCSP/CRL/cache theo cơ chế hạ tầng. Nếu dùng SPIFFE/workload identity hoặc cloud workload identity, disable principal hoặc binding bị compromise. Xác minh service mesh, gateway và service trực tiếp đều áp dụng trạng thái thu hồi.

Certificate rotation có thể làm gián đoạn workload hợp lệ. Chuẩn bị certificate thay thế qua kênh tin cậy và kiểm tra identity mapping trước khi mở lại traffic.

### 5.4. User session và refresh token

Với user bị compromise, revoke session/refresh token, yêu cầu đăng nhập lại hoặc step-up authentication theo risk policy. Nếu chỉ một session bị lộ, không nhất thiết khóa toàn bộ account; nếu evidence cho thấy account takeover hoặc recovery channel bị chiếm, mở rộng containment theo account và credential liên quan.

Không dùng request ID hoặc user ID trong URL làm căn cứ thu hồi. Hành động phải dựa trên principal/session/token identifier đã xác minh.

## 6. Containment theo endpoint, operation và API version

Khi lỗ hổng nằm ở một chức năng, chặn đúng operation thường giảm tác động hơn tắt cả service.

### 6.1. Chặn tại gateway

Gateway có thể áp dụng deny rule theo method, route template, version, client identity hoặc scope. Ví dụ cấu hình khái niệm:

```yaml
emergencyPolicy:
  id: incident-2026-041
  expiresAt: "2026-11-18T23:00:00Z"
  match:
    clientIdentity: "reporting-partner-17"
    method: "POST"
    routeId: "reports-export-v2"
  action: DENY
  response:
    status: 503
    code: "OPERATION_TEMPORARILY_DISABLED"
```

Đây là pseudoconfiguration; cú pháp và semantics phụ thuộc gateway. `clientIdentity` phải được gateway suy ra từ credential đã xác minh. `routeId` nên là định danh route đã quản lý thay vì regex path tùy tiện. Rule cần expiry, owner, audit và test cho traffic ngoài scope.

### 6.2. Chặn trong application service

Nếu một operation có nhiều đường vào (REST, GraphQL, RPC, worker), policy tại application service/domain boundary có thể bao phủ tốt hơn gateway. Ví dụ một `ExportPolicy` có thể từ chối export trong incident mode cho một client hoặc tenant đã xác minh.

Không chỉ thêm `if` vào một controller. Cùng nghiệp vụ có thể được gọi từ scheduled job, message consumer, internal endpoint hoặc API version khác. Tập trung policy tại service boundary và kiểm thử mọi adapter.

### 6.3. Feature flag/kill switch có kiểm soát

Kill switch có thể tạm disable một operation. Nó cần:

- Key/operation cụ thể, không phải boolean global khó hiểu.
- Owner, lý do incident, người thay đổi và thời điểm.
- Expiry hoặc review deadline bắt buộc.
- Giá trị mặc định an toàn nếu config store unavailable.
- Propagation time và trạng thái áp dụng trên từng instance.
- Audit và metric về request bị chặn.
- Test để chắc chắn chỉ operation dự kiến bị ảnh hưởng.

Không để `disableSecurity=false` hoặc `skipAuthorization=true` làm cơ chế containment. Kill switch phải giảm quyền/hành vi, không bỏ kiểm soát.

### 6.4. API version cũ và route alias

Khi V1 có lỗ hổng nhưng V2 an toàn, có thể tạm chặn V1 hoặc operation bị ảnh hưởng và hướng dẫn consumer migrate. Trước khi áp dụng, kiểm tra:

- Path, host, header-based version negotiation và alias.
- HTTP method và method override nếu được hỗ trợ.
- Gateway rewrite và direct service route.
- GraphQL field/mutation hoặc RPC method gọi cùng service.
- Background job/message consumer có thể kích hoạt logic cũ.

Không redirect tự động một request V1 sang V2 nếu semantics, authorization hoặc payload mapping khác nhau. Redirect có thể làm client gửi lại credential/body sang endpoint không dự kiến.

## 7. Containment theo tenant, quota và resource abuse

Khi một tenant hoặc integration gây tải bất thường, có thể giảm tốc độ hoặc giới hạn operation thay vì disable toàn account ngay lập tức.

### 7.1. Thứ tự giảm tải

Tùy mức độ, cân nhắc:

1. Giảm concurrency cho operation tốn tài nguyên.
2. Hạ quota theo tenant/client đã xác minh.
3. Giới hạn batch size, export size hoặc thời gian xử lý.
4. Tạm dừng enqueue job mới nhưng vẫn cho phép đọc trạng thái job cũ.
5. Chặn một operation cụ thể.
6. Suspend client/tenant nếu abuse tiếp tục hoặc có rủi ro dữ liệu.

Đây không phải thứ tự bắt buộc cho mọi incident. Nếu đang exfiltrate dữ liệu hoặc thực hiện payment trái phép, cần deny ngay thay vì giảm tốc độ. Chọn control theo tác động, không theo tiện ích triển khai.

### 7.2. Rate limit phải dùng identity đáng tin

Bucket có thể theo client, principal, tenant và operation. Các key này phải được tạo từ authentication context đã xác minh. Không cho caller đổi `tenantId` hoặc `clientId` để có bucket mới.

Kết hợp giới hạn request count với cost unit: một request export có thể tốn hơn một request đọc metadata. Theo dõi cả concurrency, queue age và provider usage; chỉ rate limit ở gateway có thể không chặn fan-out phía sau.

### 7.3. Giữ các luồng thiết yếu

Nếu cần suspend một tenant, xác định các operation thiết yếu như đọc trạng thái incident, tải dữ liệu cần thiết theo hợp đồng, hoặc endpoint quản trị tài khoản. Mọi ngoại lệ phải có authorization rõ, audit và giới hạn; không tạo một “support bypass” chung có quyền đọc mọi tenant.

## 8. Containment cho SSRF và outbound request

Khi URL fetcher hoặc integration endpoint bị khai thác, containment nên đặt ở outbound boundary để mọi route gọi tới đều được bảo vệ.

### 8.1. Tạm dừng chức năng fetch theo operation

Nếu chưa thể chứng minh URL policy an toàn, tạm disable preview/import/callback validation có nhận URL. Có thể giữ các API không thực hiện outbound request hoạt động. Thông báo lỗi không nên tiết lộ dải IP nội bộ hoặc rule cụ thể mà attacker có thể dùng để dò.

### 8.2. Chặn destination class ở egress

Egress firewall/proxy có thể chặn loopback, private, link-local, metadata và destination không được phê duyệt. Đây là lớp bổ sung; application vẫn phải validate scheme, DNS result, redirect, port và pin địa chỉ cho request. Không chỉ dựa vào block IP tĩnh nếu cloud/network có dải đặc thù.

### 8.3. Không chuyển correlation/credential tới host không tin cậy

Trong containment, rà soát outbound headers. Không forward Authorization, Cookie, internal request ID, trace baggage hoặc credential service tới URL do user cấu hình. Nếu phát hiện secret đã gửi tới host không tin cậy, xử lý như credential exposure: revoke/rotate và đánh giá log phía nhận.

## 9. Containment cho async job, queue và side effect

Một HTTP endpoint có thể trả `202` rồi worker mới thực hiện action. Chặn route producer không tự dừng message đã enqueue.

### 9.1. Dừng enqueue và xử lý backlog

Nếu job đang gây hại:

- Tạm dừng producer hoặc operation tạo job.
- Tạm dừng consumer hoặc handler cụ thể nếu cần.
- Giữ message trong queue/quarantine; không xóa hàng loạt.
- Xác định message nào đã xử lý, đang chạy, pending hoặc có outcome không rõ.
- Ngăn redrive tự động trong lúc điều tra.
- Đối soát side effect với provider/database trước khi resume.

### 9.2. Không xóa evidence để làm queue sạch

Message có thể là bằng chứng quan trọng. Dùng quarantine/DLQ có ACL, retention và audit. Nếu payload chứa secret/PII, bảo vệ hoặc redact bản sao theo incident procedure nhưng vẫn giữ evidence cần thiết có kiểm soát.

### 9.3. Idempotency và ambiguous outcome

Nếu payment/email/SMS có thể đã được provider nhận trước khi timeout, không retry mù quáng khi mở lại consumer. Tra cứu provider reference, idempotency key và business state. Ghi nhận trạng thái `UNKNOWN`/reconciliation khi chưa thể xác định kết quả.

### 9.4. Redrive có kiểm soát

Chỉ redrive sau khi nguyên nhân đã được khắc phục và schema/authorization hiện tại đã được xác minh. Giữ original message ID, kiểm tra expiry, tenant và quyền tại thời điểm thực thi. Bắt đầu bằng batch nhỏ, rate limit và stop condition; không replay toàn bộ backlog cùng lúc.

## 10. Ví dụ Spring: operation kill switch và client policy

Ví dụ dưới đây minh họa cách đặt một policy tại service boundary. Nó không thay thế authentication hoặc object authorization.

```java
public record VerifiedClient(String clientId, String tenantId) {}

public interface IncidentPolicy {
    void requireOperationEnabled(
            String operation,
            VerifiedClient client);
}

@Service
public class ReportExportService {
    private final IncidentPolicy incidentPolicy;
    private final ReportAuthorization authorization;
    private final ReportRepository reports;

    public ReportExportService(
            IncidentPolicy incidentPolicy,
            ReportAuthorization authorization,
            ReportRepository reports) {
        this.incidentPolicy = incidentPolicy;
        this.authorization = authorization;
        this.reports = reports;
    }

    public ExportResult export(
            UUID reportId,
            CurrentPrincipal principal,
            VerifiedClient client) {

        incidentPolicy.requireOperationEnabled("reports.export", client);
        Report report = reports.findByIdAndTenantId(
                reportId, principal.tenantId())
            .orElseThrow(ResourceNotFoundException::new);
        authorization.requireCanExport(principal, report);
        return createExport(report, principal);
    }
}
```

`VerifiedClient` phải được tạo từ authentication context đã xác minh; không bind trực tiếp từ request body/header. `IncidentPolicy` chỉ quyết định operation có đang bị containment hay không. Object authorization và tenant-scoped lookup vẫn được thực hiện sau đó. Nếu client không được xác định trong context, policy phải xử lý fail closed cho operation cần client identity.

### 10.1. Policy có expiry và audit

Một policy record có thể gồm `incidentId`, operation, client/tenant scope, action, owner, `createdAt`, `expiresAt`, reason code và version. Khi hết hạn, không nên tự động mở lại một operation nhạy cảm mà không có review; có thể chuyển sang trạng thái cần xác nhận của incident owner. Cần audit cả tạo, sửa, disable và expiry.

### 10.2. Tránh cache policy cũ quá lâu

Nếu mỗi instance cache incident policy, revoke/deny có thể không có hiệu lực ngay. Đặt TTL ngắn, push invalidation hoặc dùng control plane có consistency được hiểu rõ. Với incident nghiêm trọng, có thể cần local emergency deny list hoặc egress/gateway control độc lập. Theo dõi config version và propagation lag trên từng instance.

### 10.3. Không để control plane là điểm lỗi duy nhất

Nếu policy store unavailable, hành vi phải được định nghĩa theo loại operation. Operation nhạy cảm có thể fail closed; read-only/low-risk operation có thể dùng last-known-good policy trong một cửa sổ giới hạn nếu threat model cho phép. Không để cache stale vô hạn hoặc mặc định allow khi không tải được emergency deny policy.

## 11. Xác minh containment ở data plane

Một thay đổi cấu hình chưa chứng minh rằng attacker bị chặn. Cần kiểm thử cả đường bị chặn và đường hợp lệ.

### 11.1. Negative verification

- Credential bị revoke không thể xác thực ở mọi gateway/region.
- OAuth client bị disable không thể lấy token mới; token cũ bị xử lý theo semantics đã xác minh.
- Operation bị chặn qua mọi version, alias, method và protocol adapter.
- Tenant/client bị limit không thể đổi header/body để tạo bucket khác.
- URL fetch không thể kết nối tới destination đã bị chặn qua redirect/DNS variation.
- Queue consumer không thực hiện message thuộc scope containment.

### 11.2. Positive verification

Gọi bằng client/tenant/operation không liên quan để xác minh không bị khóa nhầm. Kiểm tra read-only operation còn hoạt động nếu được giữ lại. Kiểm tra health/monitoring path vẫn có thể phục vụ vận hành mà không expose thông tin nhạy cảm.

### 11.3. Side-effect verification

Đối với mutation, export, payment hoặc outbound call, xác minh không có side effect mới sau thời điểm containment. Kiểm tra database, outbox, queue, provider dashboard/reference và audit event. HTTP `403`/`503` đơn lẻ không đủ nếu request đã enqueue job trước khi bị chặn.

### 11.4. Kiểm tra enforcement point dự phòng

Xác minh request không thể đi thẳng tới service qua internal load balancer, port khác, hostname cũ, alternate gateway hoặc route debug. Nếu gateway là enforcement point duy nhất, network policy phải ngăn bypass gateway. Nếu service tự enforce, kiểm tra mọi instance đã nhận policy.

## 12. Giao tiếp, ownership và thay đổi containment

Incident response cần có người chịu trách nhiệm cho quyết định và thời điểm đánh giá lại. Không để rule khẩn cấp trở thành cấu hình vĩnh viễn không ai nhớ.

### 12.1. Ghi lại containment record

Mỗi thay đổi nên có:

- Incident/reference ID.
- Evidence và confidence level.
- Scope bị chặn và scope được giữ.
- Enforcement point và policy/config version.
- Người yêu cầu, người phê duyệt và người thực hiện theo quy trình tổ chức.
- Thời gian áp dụng, expiry/review time.
- Kết quả negative/positive/side-effect verification.
- Customer/consumer impact và communication owner.
- Điều kiện rollback hoặc mở lại.

Không ghi secret, token hoặc raw PII vào record. Dùng key ID, certificate serial hoặc reference đã mask.

### 12.2. Thông báo cho consumer bị ảnh hưởng

Thông báo nên nêu operation/client scope, thời gian, response code, hành động cần làm và kênh hỗ trợ. Không tiết lộ chi tiết exploit, detection threshold hoặc network topology có thể giúp attacker điều chỉnh hành vi. Không gửi thông báo cho bên ngoài nếu chưa được incident/comms owner phê duyệt theo quy trình.

### 12.3. Quản lý ngoại lệ

Nếu một consumer cần ngoại lệ tạm thời, giới hạn theo identity, operation, tenant và thời gian. Ngoại lệ cần owner, lý do, compensating control, audit và expiry. Không tạo bypass chung theo IP hoặc header bí mật.

## 13. Khôi phục dịch vụ và gỡ containment

Gỡ rule cũng là một quyết định bảo mật. Không tự động mở lại chỉ vì alert giảm hoặc thời gian TTL đã hết.

### 13.1. Điều kiện mở lại

Trước khi gỡ containment, xác minh:

- Root cause đã được sửa hoặc có compensating control được chấp thuận.
- Credential đã rotate/revoke và client hợp lệ đã chuyển sang credential mới.
- Authorization, validation, SSRF hoặc quota policy đã được test trên mọi đường vào.
- Backlog/queue đã được phân loại; message hết hạn hoặc duplicate được xử lý.
- Data/provider reconciliation hoàn tất cho side effect có outcome không rõ.
- Monitoring/alert đã sẵn sàng phát hiện tái diễn.
- Consumer và support đã biết điều kiện hoạt động trở lại.

### 13.2. Mở lại theo từng bước

1. Mở cho một canary client/tenant có danh tính đã xác minh.
2. Bật operation với quota/concurrency thấp nếu phù hợp.
3. Quan sát error rate, authorization denial, abuse signal và downstream side effect.
4. Mở rộng theo batch nhỏ khi guardrail ổn định.
5. Gỡ rule tạm thời sau khi xác minh mọi instance đã đồng bộ.
6. Đóng incident containment record và lưu evidence.

Nếu có dấu hiệu tái diễn, dừng rollout và quay lại trạng thái containment đã biết an toàn. Không để hai rule mâu thuẫn cùng tồn tại mà không có owner.

### 13.3. Không rollback về cấu hình dễ bị khai thác

Rollback application có thể đưa trở lại version thiếu authorization hoặc validation. Trước rollback, kiểm tra security invariant của bản cũ. Nếu bản cũ không an toàn, giữ control ở gateway/service boundary hoặc deploy hotfix tương thích; không khôi phục lỗ hổng chỉ để phục hồi availability.

## 14. Các tình huống mẫu

### 14.1. API key của một đối tác bị lộ

**Evidence:** log xác thực cho thấy một key ID của partner A được dùng từ nguồn và thời điểm bất thường; các key khác của partner A chưa có dấu hiệu bị lộ.

**Containment:** revoke đúng key ID, phát key mới qua secret delivery an toàn, giữ các client khác hoạt động. Nếu partner có nhiều integration, kiểm tra key scope và usage trước khi quyết định disable toàn OAuth client.

**Verification:** key cũ thất bại ở mọi region; key mới chỉ có scope đã cấp; không có side effect mới từ key cũ; alert theo dõi việc tiếp tục dùng key đã revoke.

### 14.2. Endpoint export có lỗi object authorization

**Evidence:** user tenant A có thể export report tenant B bằng cách thay ID. Các read endpoint khác đã kiểm tra tenant scope nhưng export path gọi repository riêng.

**Containment:** tạm disable operation export hoặc chặn đúng route/mutation và job handler; giữ các read operation không liên quan hoạt động nếu đã xác minh an toàn. Không chỉ block user phát hiện lỗi vì mọi user có thể khai thác cùng bug.

**Verification:** test tenant A/B qua REST, GraphQL, alias/version và worker; xác minh không tạo file/export job và không lộ signed URL. Sau khi sửa shared authorization, mở lại canary rồi rollout.

### 14.3. Một tenant gây retry storm qua provider SMS

**Evidence:** tenant đã xác minh tạo lượng lớn send request; provider trả `429`; consumer retry đồng loạt và queue age tăng.

**Containment:** giảm concurrency/quota SMS theo tenant và provider, mở circuit breaker, giữ message trong delayed retry có giới hạn. Các API đọc trạng thái và tenant khác vẫn hoạt động. Không xóa backlog hoặc replay ngay khi provider phục hồi.

**Verification:** downstream call rate giảm; budget theo tenant hoạt động; message không mất; đối soát SMS đã gửi và idempotency trước redrive.

### 14.4. URL preview bị khai thác SSRF

**Evidence:** destination policy ghi nhận request tới link-local/private address; redirect hoặc DNS variation có thể bypass validation.

**Containment:** disable preview/fetch operation hoặc áp dụng egress deny cho destination class; giữ upload/download nội bộ không liên quan hoạt động. Thu hồi/rotate credential nếu outbound request đã gửi header secret tới host không tin cậy.

**Verification:** test redirect, A/AAAA, CNAME, IPv4/IPv6 và DNS rebinding bằng resolver/transport cô lập; xác minh không có connection tới destination bị chặn.

### 14.5. Một version cũ bỏ qua control mới

**Evidence:** V2 có tenant authorization nhưng V1 còn route legacy truy cập cùng service.

**Containment:** chặn V1 operation/alias tại gateway và application boundary, thông báo migration theo quy trình. Kiểm tra header-based version, rewrite và direct route.

**Verification:** mọi route V1/alias bị chặn; V2 vẫn áp dụng authorization; không có fallback tự động sang route cũ.

## 15. Monitoring trong thời gian containment

Theo dõi cả hiệu quả chặn và tác động phụ. Một rule có thể block đúng attacker nhưng cũng có thể block nhiều consumer hợp lệ.

Metric và event nên gồm:

- Số request bị chặn theo incident rule, operation và identity category.
- Tỷ lệ request bị chặn theo client/tenant đã xác minh.
- Credential cũ tiếp tục được sử dụng sau revoke.
- Request chuyển sang version/alias/route khác.
- Side effect downstream trước/sau containment.
- False-positive signal và support error từ consumer hợp lệ.
- Policy propagation lag và số instance chưa áp dụng version mới.
- Queue backlog, oldest message age, DLQ depth và provider cost.
- Thay đổi rate của `401`, `403`, `404`, `429` và `503` theo operation.

Không đưa token, email, raw payload hoặc correlation ID thành metric label. Dùng event/log có quyền truy cập để điều tra chi tiết và aggregate metric có cardinality hữu hạn.

### 15.1. Alert khi containment không có hiệu lực

Phát cảnh báo khi request bị chặn tiếp tục xuất hiện qua một route khác, credential đã revoke vẫn được chấp nhận, policy version không đồng nhất giữa instance hoặc side effect vẫn tăng sau khi disable producer. Đây là dấu hiệu enforcement point chưa bao phủ mọi đường hoặc trạng thái cache chưa được cập nhật.

### 15.2. Alert khi containment quá rộng

Theo dõi tỷ lệ request hợp lệ bị từ chối, tenant/client không liên quan bị ảnh hưởng, backlog và SLA. Nếu collateral impact vượt ngưỡng, incident owner cần xem lại scope và chọn control hẹp hơn nếu không làm giảm hiệu quả chặn.

## 16. Lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Tắt toàn bộ API khi một key bị lộ | Gián đoạn client không liên quan | Revoke đúng credential/client |
| Chỉ block IP | Attacker đổi IP; NAT làm ảnh hưởng khách hàng khác | Dựa trên identity đã xác minh, IP là lớp phụ |
| Tin `X-Client-Id` từ request | Attacker giả client hoặc gây khóa nhầm | Lấy identity từ authentication context |
| Chỉ chặn một path | Alias, version, GraphQL hoặc worker vẫn hoạt động | Inventory mọi adapter và side effect |
| Chặn ở gateway nhưng service có đường direct | Bypass enforcement point | Network isolation và service-side policy |
| Disable toàn tenant khi chỉ một operation abuse | Ảnh hưởng rộng và khó khôi phục | Operation-scoped quota/deny trước nếu đủ |
| Tắt authorization để duy trì availability | Mở rộng data exposure | Fail closed operation nhạy cảm |
| JWT client bị disable nhưng token cũ vẫn hợp lệ | Attacker tiếp tục dùng token đã phát hành | Xác minh revocation semantics/JTI/TTL/introspection |
| Kill switch không expiry/owner | Rule khẩn cấp thành cấu hình vĩnh viễn | Owner, audit, expiry và review |
| Config báo cập nhật nhưng data plane chưa đổi | Request vẫn đi qua instance/cache cũ | Verify trên mọi region/instance |
| Xóa queue để dừng abuse | Mất evidence và giao dịch hợp lệ | Pause/quarantine, phân loại và đối soát |
| Redrive toàn backlog cùng lúc | Retry storm mới và side effect trùng | Batch, rate limit, idempotency và stop condition |
| Mở lại chỉ vì alert giảm | Lỗ hổng gốc vẫn còn | Root-cause fix và security regression trước recovery |

## 17. Checklist containment và recovery

### Khi bắt đầu incident

- [ ] Xác định operation, route/version, side effect và dữ liệu có thể bị ảnh hưởng.
- [ ] Xác minh client/principal/tenant từ authentication context, không từ input tự khai.
- [ ] Ghi evidence, thời điểm, confidence và các giả thuyết chưa xác minh.
- [ ] Bảo toàn log/audit/config snapshot theo incident procedure.
- [ ] Viết containment statement nêu rõ scope, enforcement point, owner và review time.

### Khi áp dụng containment

- [ ] Chọn credential/client/operation/tenant/dependency nhỏ nhất đủ hiệu quả.
- [ ] Revoke credential tại nơi thực sự xác thực; kiểm tra token đã phát hành và cache.
- [ ] Bao phủ route alias, API version, method, GraphQL/RPC và async worker.
- [ ] Giữ authentication, authorization, tenant isolation và validation.
- [ ] Kill switch có owner, audit, expiry/review và fail-safe behavior.
- [ ] Xác minh request bị chặn và request không liên quan vẫn hoạt động.
- [ ] Xác minh database, queue, provider và outbound side effect.
- [ ] Theo dõi propagation lag, false positive và dấu hiệu attacker chuyển đường.

### Khi khôi phục

- [ ] Root cause đã sửa hoặc có compensating control được phê duyệt.
- [ ] Credential mới đã phát hành; credential cũ đã bị vô hiệu ở mọi enforcement point.
- [ ] Authorization/validation/SSRF/resource policy có regression test.
- [ ] Backlog và ambiguous outcome đã được đối soát; redrive có giới hạn.
- [ ] Canary client/tenant được mở trước; guardrail và stop condition đang hoạt động.
- [ ] Gỡ rule tạm thời có audit; không rollback về cấu hình yếu hơn.
- [ ] Incident record có owner, evidence, impact, thay đổi và bài học sau sự cố.

## Kết luận

Containment API hiệu quả bắt đầu từ việc xác định đúng credential, client, principal, tenant, operation và side effect bị ảnh hưởng. Chọn enforcement point nhỏ nhất đủ chặn hành vi nguy hiểm, giữ nguyên các security invariant, bảo toàn evidence và xác minh cả request bị chặn lẫn traffic không liên quan. Với credential compromise, kiểm tra cả token đã phát hành; với async và outbound integration, xử lý backlog và side effect đang chạy; khi recovery, mở lại theo canary sau khi root cause đã được khắc phục. Mọi rule khẩn cấp cần owner, audit và thời hạn review để biện pháp tạm thời không trở thành cấu hình mơ hồ lâu dài.

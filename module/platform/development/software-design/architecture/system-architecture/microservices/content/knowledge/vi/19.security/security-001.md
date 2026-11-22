# Mô hình đe dọa và ranh giới tin cậy trong hệ thống nhiều dịch vụ

## 1. Mục tiêu và phạm vi

Khi một ứng dụng được tách thành nhiều dịch vụ, một yêu cầu nghiệp vụ có thể đi qua trình duyệt, API Gateway, các service nội bộ, message broker, cơ sở dữ liệu và nhà cung cấp bên ngoài. Mỗi lần dữ liệu hoặc lệnh vượt qua một ranh giới tin cậy là một điểm cần xác định **ai đang gọi, danh tính được chứng minh bằng cách nào, được phép làm gì, dữ liệu nào có thể bị thao túng và hệ thống sẽ xử lý ra sao khi giả định tin cậy sai**.

Mô hình đe dọa (threat modeling) là quá trình có cấu trúc để tìm đường tấn công, đánh giá hậu quả và quyết định biện pháp giảm thiểu ngay từ thiết kế. Nó tạo ra một danh sách quyết định có thể kiểm chứng; một sơ đồ hạ tầng hoặc danh sách công nghệ bảo mật riêng lẻ chưa đủ để trở thành mô hình đe dọa.

Sau khi học, bạn có thể:

1. Xác định tài sản cần bảo vệ, tác nhân, luồng dữ liệu và các giả định tin cậy của kiến trúc nhiều service.
2. Vẽ Data Flow Diagram (DFD) có ranh giới tin cậy, nhận diện điểm chuyển danh tính và thay đổi quyền.
3. Áp dụng STRIDE vào từng thành phần và từng luồng, kể cả luồng bất đồng bộ.
4. Chọn kiểm soát phù hợp theo rủi ro, trách nhiệm của từng service và khả năng xác minh.
5. Duy trì threat model khi hệ thống có endpoint, service, tenant, nhà cung cấp hoặc cơ chế triển khai mới.

Ví dụ xuyên suốt: nền tảng đặt hàng có Order Service, Payment Service, Inventory Service, Notification Service, API Gateway, message broker và cổng thanh toán bên thứ ba (PSP). Ví dụ chỉ để minh họa phương pháp; ranh giới và biện pháp thực tế phải được xác nhận theo hệ thống cụ thể.

## 2. Khái niệm cốt lõi

| Khái niệm | Ý nghĩa thực hành | Ví dụ |
|---|---|---|
| Asset (tài sản) | Dữ liệu, quyền hoặc tính chất nghiệp vụ cần bảo vệ | Thông tin đơn hàng, khóa API PSP, số tiền thanh toán |
| Threat actor | Chủ thể có khả năng gây hại, cố ý hoặc do bị chiếm quyền | Khách hàng độc hại, service bị xâm nhập, nhân sự có quyền quá rộng |
| Entry point | Điểm nhận dữ liệu hoặc hành động từ chủ thể khác | REST API, webhook, topic, tác vụ quản trị, pipeline CI/CD |
| Trust boundary | Nơi mức tin cậy hoặc cách xác thực/ủy quyền thay đổi | Internet → Gateway; Order → Payment; service → database |
| Trust assumption | Điều đang được giả định là đúng | “Gateway đã xác thực token”; “event chỉ do Order phát” |
| Security invariant | Điều luôn phải đúng dù yêu cầu đi qua bao nhiêu service | Một tenant không đọc được đơn hàng tenant khác |
| Attack path | Chuỗi bước khiến tác nhân đạt mục tiêu gây hại | Chiếm token → gọi API nội bộ → truy cập tài nguyên tenant khác |
| Mitigation | Kiểm soát làm giảm khả năng hoặc mức độ thiệt hại | Kiểm tra audience, ủy quyền cấp đối tượng, hạn chế egress |
| Residual risk | Rủi ro còn lại sau khi có biện pháp | Tấn công DoS phân tán vẫn có thể làm giảm khả dụng |

**Ranh giới tin cậy không đồng nghĩa ranh giới mạng.** Hai pod ở cùng Kubernetes namespace vẫn có thể khác quyền. Hai tenant dùng chung một database vẫn có ranh giới logic. Một API Gateway có thể xác thực người dùng nhưng không thể thay service quyết định người đó có quyền với từng đơn hàng hay không. mTLS có thể chứng minh danh tính workload, nhưng tự nó không chứng minh quyền gọi nghiệp vụ.

### 2.1. Ba loại danh tính phải phân biệt

- **End-user identity:** người dùng cuối, gồm subject, tenant, nhóm/quyền được cấp. Không tự suy ra quyền truy cập đối tượng từ việc token hợp lệ.
- **Workload identity:** service hoặc tác vụ đang gọi, ví dụ danh tính gắn với chứng chỉ mTLS hoặc token riêng cho service. Cần phân quyền service-to-service.
- **Resource identity:** đơn hàng, tài khoản, kho, chứng từ, đối tượng thuộc tenant và chủ sở hữu nào. Phải kiểm tra tại thời điểm truy cập.

Một yêu cầu Payment Service có thể đồng thời mang danh tính workload “order-service” và ngữ cảnh người dùng “customer-123”. Hai danh tính phục vụ hai quyết định khác nhau: Order có được gọi Payment không, và người dùng có được thanh toán đơn hàng cụ thể không.

## 3. Xác định tài sản và bất biến bảo mật trước khi vẽ sơ đồ

Bắt đầu từ hậu quả có thể xảy ra, thay vì liệt kê công nghệ hiện có.

| Tài sản hoặc bất biến | Hậu quả nếu vi phạm | Dịch vụ chịu trách nhiệm chính |
|---|---|---|
| Chủ đơn hàng và tenant của đơn | Rò rỉ đơn hàng, thay đổi trái phép | Order |
| Số tiền và đơn vị tiền tệ của giao dịch | Tính sai tiền, gian lận | Order + Payment với hợp đồng dữ liệu rõ ràng |
| Quy tắc “một yêu cầu thanh toán không thu tiền hai lần” | Double charge khi retry hoặc replay | Payment |
| Thông tin định danh và địa chỉ giao hàng | Rò rỉ dữ liệu cá nhân | Order + các consumer được phép |
| Tồn kho và số lượng đã giữ chỗ | Bán vượt kho, phá vỡ nhất quán | Inventory |
| Khóa gọi PSP, khóa ký webhook | Kẻ tấn công giả mạo giao dịch | Payment + nền tảng secrets |
| Tính xác thực và thứ tự trạng thái sự kiện | Chuyển trạng thái sai, xử lý lặp | Producer và consumer |
| Khả dụng của checkout | Không thể đặt hàng dù service riêng lẻ còn hoạt động | Toàn luồng checkout |

Viết bất biến dưới dạng có thể kiểm chứng: “Payment chỉ chấp nhận số tiền từ bản ghi đơn hàng đã được xác nhận”, “Webhook phải gắn đúng payment attempt”, “Order API chỉ trả đơn thuộc tenant trong principal đã xác thực”, “Mọi thay đổi trạng thái thanh toán đều có bằng chứng truy vết”.

## 4. DFD và bản đồ ranh giới tin cậy

### 4.1. Sơ đồ ví dụ

~~~mermaid
flowchart LR
    subgraph INTERNET["TB-0: Internet / client không tin cậy"]
      User["Web / Mobile client"]
      Attacker["External caller"]
    end
    subgraph EDGE["TB-1: Edge"]
      GW["API Gateway"]
    end
    subgraph APP["TB-2: Internal workloads"]
      Orders["Order Service"]
      Payments["Payment Service"]
      Inventory["Inventory Service"]
      Notify["Notification Service"]
    end
    subgraph PLATFORM["TB-3: Data / event plane"]
      OrderDB[("Order DB")]
      PayDB[("Payment DB")]
      Broker[("Message Broker")]
    end
    subgraph THIRD["TB-4: Third party"]
      PSP["Payment Provider"]
    end
    User -->|"F1 HTTPS + access token"| GW
    Attacker -->|"F1 untrusted requests"| GW
    GW -->|"F2 authenticated request"| Orders
    Orders -->|"F3 mTLS + service identity"| Payments
    Orders -->|"F4 scoped DB credential"| OrderDB
    Payments -->|"F5 scoped DB credential"| PayDB
    Orders -->|"F6 publish domain event"| Broker
    Broker -->|"F7 consume"| Inventory
    Broker -->|"F8 consume"| Notify
    Payments -->|"F9 outbound TLS"| PSP
    PSP -->|"F10 signed webhook"| GW
    GW -->|"F11 routed webhook"| Payments
~~~

Khung trong sơ đồ giúp nhóm thảo luận, nhưng **mỗi mũi tên vẫn phải được xem là một chuyển tiếp có điều kiện tin cậy**. Không gắn nhãn “trusted internal” cho tất cả các mũi tên trong cluster. Tách rõ control plane (CI/CD, secret manager, quản trị) ra khỏi data plane khi phân tích hệ thống thật.

### 4.2. Bảng chuyển ranh giới

| Luồng | Dữ liệu/động tác | Câu hỏi cần trả lời khi vượt ranh giới |
|---|---|---|
| F1 Client → Gateway | Token, giỏ hàng, mã đơn | Ai phát hành token? Có chặn giả mạo, quá tải, payload quá cỡ không? |
| F2 Gateway → Order | Identity context, yêu cầu đọc/sửa đơn | Order có tự xác minh principal và quyền trên đúng đối tượng không? Header danh tính có thể bị client tự đặt không? |
| F3 Order → Payment | Lệnh tạo thanh toán, amount, orderId | Payment có nhận diện workload gọi, xác thực order state và chống gọi lặp không? |
| F4/F5 Service → DB | Câu truy vấn và dữ liệu nhạy cảm | Credential có giới hạn service, schema, thao tác không? Có truy vấn chéo tenant không? |
| F6 Order → Broker | OrderPlaced, event ID, tenant, order ID | Ai được publish? Event có schema, quyền topic và tính toàn vẹn không? |
| F7/F8 Broker → Consumer | Bản tin có thể lặp, đến trễ, sai thứ tự | Consumer có validate schema, tự ủy quyền hành động, idempotency không? |
| F9 Payment → PSP | Yêu cầu thu tiền, khóa truy cập PSP | Có giới hạn endpoint được gọi, timeout, retry policy, kiểm tra TLS không? |
| F10/F11 PSP → Payment | Webhook trạng thái giao dịch | Có xác thực chữ ký trên raw body, chống replay và đối chiếu giao dịch không? |

Đánh dấu thêm ranh giới **tenant A ↔ tenant B**, **operator ↔ production**, **build pipeline ↔ runtime**, **service ↔ metadata/cloud control API**, và **backup/analytics ↔ production data** nếu chúng tồn tại. Đây là các ranh giới dễ bị bỏ quên vì không nằm trực tiếp trong luồng checkout.

### 4.3. Cách vẽ DFD có ích cho bảo mật

1. Xác nhận phạm vi và trường hợp sử dụng: checkout, hoàn tiền, đổi địa chỉ, nhập kho, đọc báo cáo.
2. Vẽ external entity, process/service, data store và các mũi tên có hướng; ghi rõ giao thức, loại dữ liệu, principal và mức nhạy cảm.
3. Gạch rõ trust boundary ở nơi thay đổi chủ thể kiểm soát, credential, quyền, tenant hoặc chính sách.
4. Ghi nhận mọi điểm chuyển từ một danh tính sang danh tính khác: token exchange, service account, webhook, job queue.
5. Với từng mũi tên, hỏi nguồn dữ liệu có thể bị giả mạo, sửa đổi, phát lại, truy cập quá quyền hay gây cạn kiệt tài nguyên không.
6. Đối chiếu sơ đồ với tuyến gọi thực tế và các thành phần vận hành: admin API, cache, queue, object storage, tracing, cron job và pipeline.

Đặt nhãn dữ liệu cụ thể. “OrderCreated {eventId, orderId, tenantId, version}” hữu ích hơn “message”. “PSP webhook có chữ ký” hữu ích hơn “callback”.

## 5. Dùng STRIDE để tìm đe dọa

STRIDE là khung đặt câu hỏi theo sáu nhóm; một mối đe dọa có thể thuộc nhiều nhóm. Áp dụng lên từng process, data store và data flow; không dừng ở câu hỏi tổng quát “hệ thống có an toàn không?”.

| Nhóm | Câu hỏi trong hệ thống nhiều service | Ví dụ |
|---|---|---|
| **S – Spoofing** (giả mạo) | Ai có thể giả user/service/producer/webhook? | Dùng token phát cho Service A để gọi Service B vì B không kiểm tra audience |
| **T – Tampering** (sửa đổi) | Payload/event/trạng thái có thể bị sửa ở đâu? | Client tự sửa amount; consumer tin amount không có đối chiếu |
| **R – Repudiation** (phủ nhận) | Có thể chứng minh ai yêu cầu hành động và kết quả nào xảy ra không? | Không phân biệt retry tự động và yêu cầu thanh toán mới |
| **I – Information disclosure** (lộ thông tin) | Dữ liệu vượt ra ngoài tenant/vai trò/log/tracing không? | IDOR/BOLA qua GET /orders/{id}; token xuất hiện trong log |
| **D – Denial of service** (từ chối dịch vụ) | Có thể làm cạn CPU, connection pool, queue hoặc quota không? | Một API gây fan-out tới nhiều service và retry hàng loạt |
| **E – Elevation of privilege** (leo thang quyền) | Chủ thể ít quyền có thể mượn quyền service mạnh hơn không? | Service nhận URL do người dùng nhập rồi gọi metadata endpoint bằng quyền workload |

### 5.1. Những chuỗi tấn công cần thử nghĩ đến

**Đường A — Truy cập chéo tenant.** Người dùng tenant X có token hợp lệ, đổi orderId thành ID của tenant Y. Gateway chấp nhận token; Order chỉ kiểm tra “đã đăng nhập” và truy vấn theo ID. Kết quả: lộ đơn hàng tenant Y. Kiểm soát phải nằm ở truy vấn/ủy quyền của Order, ví dụ lọc theo tenant đáng tin cậy và chính sách truy cập tài nguyên; ID ngẫu nhiên không thay thế authorization.

**Đường B — Lạm dụng danh tính nội bộ.** Notification bị chiếm quyền và thử gọi Payment API. Nếu Payment tin mọi pod “trong mạng” hoặc nhận token không kiểm tra audience, attacker có thể tạo hoặc sửa yêu cầu thanh toán. Cần danh tính workload riêng, policy allowlist service→action, token audience phù hợp, mạng mặc định từ chối và nhật ký cảnh báo.

**Đường C — Replay bất đồng bộ.** Consumer Inventory nhận lại cùng OrderPlaced sau timeout. Nếu mỗi lần nhận đều trừ kho, một đơn trừ kho nhiều lần. Cần eventId duy nhất, bảng inbox/processed-events hoặc khóa idempotency, state transition hợp lệ và cơ chế xử lý bản tin lỗi. “Exactly once” ở một đoạn broker không tự đảm bảo exactly-once cho side effect xuyên qua database và PSP.

**Đường D — Webhook giả.** Attacker gửi POST báo “payment_succeeded”. Nếu Payment tin header hoặc payload mà không kiểm tra chữ ký/timestamp/transaction mapping, đơn có thể được đánh dấu đã trả tiền. Phải xác thực trên raw request body theo cơ chế PSP, so sánh an toàn, chống replay, và đối chiếu số tiền, tiền tệ, payment attempt với bản ghi nội bộ.

## 6. Sổ đăng ký đe dọa mẫu

Một threat model hữu ích cần liên kết **đường tấn công → tác động → kiểm soát → bằng chứng kiểm thử → người chịu trách nhiệm**. Bảng dưới là ví dụ để nhóm điều chỉnh, không phải danh sách đầy đủ.

| ID | Ranh giới / tài sản | Đe dọa và tác động | Kiểm soát đề xuất | Bằng chứng xác minh |
|---|---|---|---|---|
| T-01 | F2, tenant → Order | BOLA/IDOR làm lộ đơn tenant khác | Object-level authorization; truy vấn gắn tenant từ principal; audit | Test GET/PATCH orderId của tenant khác trả 403 hoặc 404, không rò nội dung |
| T-02 | F3, Order → Payment | Workload giả mạo hoặc token dùng sai đích | mTLS/workload identity, kiểm issuer/audience, policy theo service+action | Token cấp cho Inventory bị Payment từ chối |
| T-03 | F3, tiền thanh toán | Client sửa amount/currency hoặc order state | Payment tra cứu snapshot/bản ghi đáng tin cậy; state machine; kiểm tổng tiền | Tamper amount/request bị từ chối hoặc bỏ qua giá trị không đáng tin |
| T-04 | F3/F9, tính duy nhất | Retry tạo hai lần charge | Idempotency key ràng buộc đơn/payment attempt; unique constraint; PSP idempotency | Gửi cùng lệnh đồng thời nhiều lần chỉ tạo một hiệu ứng thu tiền |
| T-05 | F6/F7, broker | Producer trái phép publish sự kiện giả | Topic ACL theo identity, schema validation, phân quyền producer/consumer | Workload không được cấp quyền publish bị từ chối |
| T-06 | F7/F8, consumer | Duplicate/reorder khiến trạng thái sai | Event ID, version/sequence, inbox, transition guard, DLQ | Bản tin lặp hoặc đến ngược thứ tự không trừ kho hai lần |
| T-07 | F10/F11, webhook | Giả webhook hoặc replay cập nhật thanh toán | Xác thực chữ ký, timestamp/nonce, đối chiếu payment ID và amount | Chữ ký sai/quá hạn/replay bị từ chối |
| T-08 | Service → DB, tenant | Query không giới hạn tenant, quyền DB quá rộng | Tenant-scoped query, least-privilege DB role, tách credential | Query chéo tenant bị chặn; role Order không sửa Payment DB |
| T-09 | Workload → outbound | SSRF tới metadata service/endpoint nội bộ | Kiểm soát URL đích, egress policy, chặn IP nội bộ, cloud metadata hardening | URL tới loopback, private CIDR, metadata bị từ chối |
| T-10 | API và queue | Fan-out/retry storm gây cạn tài nguyên | Rate limit, quota, timeout, bounded retries, backoff+jitter, bulkhead, DLQ | Load test duy trì giới hạn connection/queue và thoát quá tải |
| T-11 | Log/trace/metrics | Lộ token, PII, bí mật qua observability | Mask/redact theo trường; RBAC; retention; không log raw token/body | Kiểm tra trace/log của luồng thanh toán không chứa bí mật |
| T-12 | CI/CD → runtime | Artifact hoặc secret bị thay thế, quyền deploy quá rộng | Artifact signing/provenance, least-privilege deploy, secret manager, kiểm soát môi trường | Build/deploy không hợp lệ hoặc image không tin cậy bị chặn |

Với từng mục, bổ sung **trạng thái (open/mitigated/accepted), owner, ngày cần xử lý, bằng chứng và residual risk**. Đừng tuyên bố “đã giảm thiểu” chỉ vì một công cụ đã được cài; phải có kiểm tra hành vi tương ứng.

## 7. Thiết kế kiểm soát theo từng ranh giới

### 7.1. Internet → API Gateway → Service

- Dùng TLS từ client; cấu hình giới hạn request size, rate limit, timeout và chống abuse tại edge. Các lớp này giảm tải nhưng không thay logic bảo mật trong service.
- Xác thực access token bằng thư viện tin cậy: chữ ký và khóa hợp lệ, thuật toán cho phép, issuer, audience, thời hạn, thời điểm hiệu lực; kiểm soát clock skew phù hợp. Chỉ decode nội dung JWT không phải xác thực.
- Chọn mô hình truyền danh tính rõ ràng. Nếu gateway chuyển trusted identity headers, backend phải ngăn client trực tiếp truy cập/giả header và xác thực nguồn upstream; tốt hơn là dùng token có thể xác minh tại service hoặc cơ chế identity propagation được thiết kế và giám sát.
- Tại Order, kiểm tra quyền hành động trên **đối tượng cụ thể**; ràng buộc tenant từ principal đã xác minh thay vì tenantId do request tự khai. Tách quyền “xem đơn” với “hoàn tiền” hoặc “sửa giá”.
- Không trả về stack trace, secret hay thông tin tồn tại của tài nguyên không được phép. Đặt mã 403/404 theo chính sách nhưng nhất quán tránh rò dữ liệu qua khác biệt phản hồi.

Ví dụ logic cấp tài nguyên (mã minh họa, phụ thuộc framework/repository thực tế):

~~~java
// jwt đã được Resource Server kiểm tra chữ ký, issuer, audience và thời hạn.
String authenticatedTenant = jwt.getClaimAsString("tenant_id");
String requester = jwt.getSubject();

// Không lấy tenant quyết định quyền từ query parameter của client.
Order order = orderRepository
    .findByIdAndTenantId(orderId, authenticatedTenant)
    .orElseThrow(NotFoundException::new);

if (!policy.canReadOrder(requester, order)) {
    throw new ForbiddenException();
}
return orderViewMapper.toSafeDto(order);
~~~

Bài học: kiểm tra “token hợp lệ” là **authentication**; kiểm tra tenant và quyền trên bản ghi là **authorization**. Phải có cả hai.

### 7.2. Service → Service: tránh “mạng nội bộ là tin cậy”

- Cấp workload identity duy nhất cho từng service/instance; cân nhắc mTLS với danh tính chứng chỉ được quản lý và luân chuyển tự động.
- Ở service đích, chặn mặc định rồi cấp quyền theo caller, hành động và phạm vi tài nguyên. “Bất cứ service nào trong cluster” không phải policy đủ hẹp.
- Nếu dùng token giữa service, kiểm tra issuer, audience đúng service đích, scopes và expiry. Không chuyển nguyên token có audience dành cho API khác rồi mặc định được chấp nhận.
- Khi thực hiện hành động “thay mặt người dùng”, ghi rõ mô hình delegation/token exchange và giới hạn quyền; không nâng yêu cầu người dùng thành quyền admin chỉ vì worker có service account mạnh.
- Tách credential của Order, Payment, Inventory; hạn chế truy cập trực tiếp database của service khác. Giao tiếp qua API/event có hợp đồng và cơ chế ủy quyền.
- NetworkPolicy/firewall và service mesh là lớp bổ trợ. Lỗi logic trong đối tượng vẫn cần kiểm soát ở ứng dụng.

Ma trận chính sách mẫu:

| Caller | Callee | Hành động được phép | Mặc định |
|---|---|---|---|
| API Gateway | Order | submitOrder, readOwnOrder | Cấm mọi API quản trị |
| Order | Payment | createPaymentAttempt, queryPaymentStatus | Cấm refund nếu không có luồng riêng |
| Order | Broker | publish OrderPlaced theo topic sở hữu | Cấm publish PaymentSucceeded |
| Inventory | Payment | Không có | Deny |
| Notification | Order | Truy vấn projection đã giới hạn hoặc nhận event | Cấm chỉnh sửa đơn |

### 7.3. Service → Database/Cache/Object Storage

- Mỗi service dùng tài khoản DB riêng với đặc quyền tối thiểu; tránh tài khoản shared admin. Kiểm soát quyền migration tách khỏi quyền runtime.
- Truy vấn tenant phải có tenant filter đáng tin cậy; cân nhắc row-level security như lớp phòng thủ bổ sung nếu phù hợp. Kiểm tra cả export, report, search index và cache key có chứa tenant.
- Chống SQL injection bằng parameterized queries. Hạn chế quyền gọi function, schema, extension và thao tác nguy hiểm.
- Mã hóa dữ liệu truyền và lưu trữ phù hợp phân loại dữ liệu, với chính sách cấp và xoay khóa có thể vận hành được.
- Secret chỉ được lấy từ secret manager/managed identity theo quyền; không lưu trong repository, image, log hoặc biến môi trường bị in ra trong diagnostic.
- Backup, snapshot, analytics và quyền support/operator là những đường ra dữ liệu riêng cần đánh giá trust boundary.

### 7.4. Service → Broker → Consumer

Thông điệp đến từ broker **không tự động là yêu cầu đã được ủy quyền**. Producer có thể bị xâm nhập, cấu hình ACL sai hoặc payload cũ được gửi lại.

- Quy định schema và phiên bản sự kiện; validate kiểu, giới hạn kích thước, giá trị enum và transition hợp lệ. Tránh deserialization không an toàn.
- Gắn eventId, producer, occurredAt, aggregateId, tenantId và version/sequence phù hợp. Các trường trong payload vẫn phải được đánh giá theo nguồn tin cậy.
- Cấp quyền publish/subscribe riêng theo topic và consumer group. Không cho một service tùy tiện phát event của service khác.
- Dùng idempotent consumer, transaction/inbox/outbox phù hợp; duplicate là tình huống bình thường trong hệ thống at-least-once.
- Kiểm soát retry, dead-letter queue, poison message và backpressure; bảo vệ PII trong topic, DLQ và hệ thống quan sát.
- Khi event vượt tổ chức/vùng tin cậy, cần thêm kiểm soát xác thực nguồn/tính toàn vẹn theo hợp đồng, ngoài ACL của broker.

Ví dụ xử lý event có thể nhận nhiều lần:

~~~text
on OrderPlaced(event):
    validateSchema(event)
    assert permittedProducer(event.topic, authenticatedProducer)
    assert validTenantAndState(event)
    transaction:
        if processedEvents.contains(event.eventId):
            return ACK
        applyInventoryReservationIfValid(event.orderId, event.version)
        processedEvents.insertUnique(event.eventId)
    return ACK
~~~

Để tránh race, khóa duy nhất cho eventId và thay đổi tồn kho cần nằm trong một giao dịch nhất quán tại consumer; nếu side effect ngoài DB, cần thiết kế idempotency tương ứng.

### 7.5. Payment → PSP và webhook ngược

- Xác định danh sách host/endpoint PSP, bảo vệ khóa truy cập, bật TLS verification và giới hạn egress.
- Giữ một payment attempt ID nội bộ, idempotency key và trạng thái chuyển hợp lệ. Retry sau timeout phải hỏi trạng thái/tiếp tục cùng attempt theo hợp đồng PSP, thay vì tự động tạo lệnh thu tiền mới.
- Webhook phải được xác thực bằng cơ chế chữ ký chính thức của PSP trên **raw body** và các header/timestamp cần thiết. So sánh chữ ký an toàn; dùng cơ chế chống replay theo hướng dẫn PSP.
- Không tin orderId, amount, currency, status chỉ vì webhook hợp lệ: đối chiếu với payment attempt trong DB; hạn chế state transition, ví dụ không biến trạng thái đã hoàn tiền thành chưa thanh toán.
- Trả ACK nhanh, chuyển công việc nặng sang xử lý idempotent. Có lịch đối soát độc lập với PSP để xử lý webhook bị mất hoặc gửi trễ.

### 7.6. Luồng vận hành và chuỗi cung ứng

Threat model cần gồm đường phát hành code/secret vào production: repository → build → artifact registry → deploy → runtime. Xem xét người có quyền thay CI, token của runner, dependency, artifact tampering, cấu hình IaC và quyền quản trị cluster. Quy tắc tối thiểu: phân quyền deploy theo môi trường, bảo vệ nhánh, kiểm soát provenance và dependency, xoay credential, ghi audit sự kiện thay đổi quyền và cấu hình. Phân biệt người xem log với người có quyền đọc secret hoặc thực thi command trong production.

## 8. Lựa chọn ưu tiên và quyết định rủi ro

Không cần giả vờ rằng mọi đe dọa có cùng mức ưu tiên. Một cách đơn giản là chấm **khả năng xảy ra (L)** và **mức tác động (I)** trên thang 1–5, rồi lấy L × I làm điểm sàng lọc. Đây là quy ước nội bộ để so sánh tương đối; không phải xác suất thực tế hay phép đo độ an toàn tuyệt đối.

| Mức điểm minh họa | Hướng xử lý |
|---|---|
| 15–25 | Ưu tiên chặn trước khi release hoặc cần phê duyệt ngoại lệ rất rõ |
| 8–14 | Lập kế hoạch giảm thiểu có owner và hạn |
| 1–7 | Có thể chấp nhận có điều kiện, theo dõi giả định và trigger đánh giá lại |

Khi chấm, xem xét khả năng attacker tiếp cận ranh giới, mức đặc quyền cần có, độ khó khai thác, phạm vi dữ liệu, tác động tài chính và khả năng phát hiện/khôi phục. Nếu một lỗ hổng có tác động đặc biệt nghiêm trọng (ví dụ thu tiền sai hoặc rò dữ liệu liên tenant), có thể nâng ưu tiên bất kể điểm tổng.

Ví dụ:

- **T-01 Truy cập chéo tenant:** tiếp cận dễ qua API công khai, tác động cao; ưu tiên sửa object-level authorization và test âm tính trước release.
- **T-06 Duplicate event:** dễ xảy ra ngay cả khi không có attacker, tác động trung bình/cao; idempotency là yêu cầu thiết kế và tính đúng đắn.
- **T-10 Retry storm:** khả năng cao trong sự cố downstream; ưu tiên timeout, bounded retry, queue limit và thử nghiệm tải.

Mỗi quyết định nên lưu lý do, owner, kiểm soát đã có, bằng chứng kiểm thử, residual risk, hạn xử lý và người chấp nhận nếu còn tồn tại. “WAF đang bật” hoặc “service mesh đã triển khai” không đủ làm chứng cứ rủi ro đã được xử lý.

## 9. Từ đe dọa đến bài kiểm thử

Thiết kế test từ bất biến bảo mật và đường tấn công, thay vì chỉ kiểm tra luồng thành công.

| Kiểm thử | Kịch bản | Kỳ vọng |
|---|---|---|
| AuthN | Token hết hạn, issuer sai, audience sai, chữ ký sai | Từ chối trước nghiệp vụ; log mã lỗi không lộ token |
| AuthZ đối tượng | User tenant A truy cập orderId tenant B | Không trả dữ liệu, không thay đổi trạng thái |
| AuthZ workload | Notification gọi API refund của Payment | Bị từ chối kể cả cùng cluster |
| Payload tampering | Client sửa price/currency/tenantId | Amount lấy từ nguồn đáng tin; dữ liệu client không nâng quyền |
| Duplicate/replay | Gửi cùng createPayment/event nhiều lần, kể cả đồng thời | Một side effect hợp lệ; trạng thái nhất quán |
| Event ordering | PaymentSucceeded đến trước PaymentPending | State machine từ chối hoặc xử lý đúng theo quy tắc |
| Webhook | Chữ ký sai, timestamp cũ, amount lệch, ID lạ | Không ghi nhận thanh toán thành công |
| Resource exhaustion | Nhiều request dài, downstream timeout, retry tăng | Rate limit, bounded queue, circuit breaker, graceful degradation |
| SSRF | URL trỏ localhost, private IP, metadata endpoint, redirect | Chặn tại URL validation/egress sau khi resolve và theo redirect policy |
| Data exposure | Trace/log khi checkout thất bại | Không có token, CVV, secret, body nhạy cảm; chỉ metadata cần thiết |

Cần có **integration/security tests** tại service chịu trách nhiệm, **contract tests** cho giao tiếp liên service và **chaos/load tests** cho timeout, retry và phụ thuộc downstream. Với mục rủi ro cao, ghi rõ kiểm thử nào chứng minh kiểm soát đang hoạt động; kết quả pass chỉ có nghĩa trong phạm vi các giả định và kịch bản đã kiểm thử.

## 10. Quan sát, điều tra và ứng phó sự cố

Nhật ký là kiểm soát quan trọng cho nhóm Repudiation và phát hiện lạm dụng, nhưng cũng là nơi rò dữ liệu nhạy cảm.

- Gắn correlation/trace ID xuyên luồng; mỗi service ghi principal đã xác minh, workload caller, hành động, mã tài nguyên không nhạy cảm, decision allow/deny và outcome. Tránh ghi toàn bộ access token, secret, số thẻ hoặc payload chứa PII.
- Khi delegated request, ghi rõ **ai yêu cầu** và **service nào thực thi**, tránh chỉ thấy service account chung.
- Lưu audit cho thanh toán/hoàn tiền, thay đổi đặc quyền, thay đổi policy, triển khai và truy cập dữ liệu nhạy cảm. Bảo vệ quyền sửa/xóa và thời hạn lưu theo yêu cầu tổ chức.
- Đặt cảnh báo cho 401/403 tăng đột biến, service gọi API lạ, publish trái quyền, webhook chữ ký sai, retry bất thường, idempotency conflict và truy cập chéo tenant.
- Có phương án vô hiệu hóa credential bị lộ, thu hồi workload, khóa egress, dừng route/payment method, replay event có kiểm soát và đối soát giao dịch. Diễn tập cách phân biệt charge thật với timeout không rõ kết quả.

## 11. Quy trình workshop threat modeling 60–90 phút

**Đầu vào:** một use case, sơ đồ hiện tại, danh sách endpoint/topic, phân loại dữ liệu, quyền của workload, giả định vận hành và người hiểu nghiệp vụ. Nên có developer, kiến trúc sư, security và người phụ trách vận hành; nhóm nhỏ vẫn thực hiện được với vai trò kiêm nhiệm.

**Bước 1 — Chốt phạm vi và bất biến (10–15 phút).** Chọn một luồng có hậu quả rõ ràng, ví dụ “tạo đơn → giữ tồn → thanh toán”. Liệt kê dữ liệu/tiền/quyền cần bảo vệ và điều tuyệt đối không được sai.

**Bước 2 — Vẽ luồng và ranh giới (15–20 phút).** Vẽ actor, service, data store, nhà cung cấp, cả request và callback/event. Mỗi mũi tên có loại dữ liệu, giao thức và danh tính. Đánh dấu các điểm chuyển quyền, tenant và tổ chức.

**Bước 3 — Tìm đe dọa theo STRIDE (20 phút).** Đi từng mũi tên/điểm xử lý; đặt câu hỏi: có thể giả caller, sửa dữ liệu, chối bỏ, đọc trái quyền, làm cạn tài nguyên, nâng quyền không? Viết kịch bản có tác nhân và kết quả, ví dụ “customer A đổi orderId và đọc dữ liệu customer B”, thay vì nhãn chung “API không an toàn”.

**Bước 4 — Xếp ưu tiên và gán kiểm soát (15 phút).** Ghi threat ID, impact, likelihood, mitigation, service owner, deadline và quyết định chấp nhận rủi ro nếu có.

**Bước 5 — Chuyển thành việc kỹ thuật (10–20 phút).** Mỗi threat quan trọng có test âm tính, kiểm soát có thể triển khai, chủ sở hữu và tiêu chí hoàn thành. Lưu sơ đồ và threat register cùng tài liệu kiến trúc; cập nhật khi thay đổi thiết kế.

Đầu ra tối thiểu:

~~~text
Use case: Checkout
Assets/invariants: tenant isolation; payment at-most-once; order amount integrity
Diagram version: checkout-dfd-v1
Threat ID: T-04
Boundary: Order -> Payment -> PSP
Scenario: concurrent retries create multiple charges
Impact/likelihood: High / Medium
Decision: Mitigate
Control: stable idempotency key + unique payment attempt + PSP idempotency
Owner: Payment team
Verification: 50 concurrent identical retries -> one PSP charge
Residual risk: PSP outage with unknown final state; periodic reconciliation
Review trigger: change PSP provider or payment retry contract
~~~

## 12. Những lỗi tư duy thường gặp

1. **“Gateway đã xác thực nên mọi service phía sau an toàn.”** Gateway không biết đầy đủ quyền trên từng bản ghi, tenant và trạng thái nghiệp vụ. Quyết định ủy quyền phải được thực thi ở thành phần sở hữu tài nguyên.
2. **“Trong VPC/cluster thì mặc định tin cậy.”** Một workload bị chiếm quyền có thể lateral movement. Mọi service có identity, quyền và giới hạn mạng rõ ràng.
3. **“mTLS giải quyết authorization.”** mTLS giúp xác thực workload/kênh, nhưng Payment vẫn phải kiểm caller được làm hành động gì, với đối tượng nào.
4. **“Event trên broker đều hợp lệ.”** Producer có thể bị chiếm quyền và bản tin có thể lặp/sai thứ tự. Kiểm ACL, schema, quyền nghiệp vụ và idempotency ở consumer.
5. **“Token hợp lệ nghĩa là có quyền.”** Signature/issuer/audience/expiry xác nhận token dành cho service này; quyền với orderId cần kiểm riêng.
6. **“Một lần delivery nghĩa là một lần side effect.”** Transaction nằm ở database, broker và PSP là các hệ khác nhau. Thiết kế phục hồi/idempotency rõ ràng.
7. **“Gắn công cụ bảo mật là xong threat model.”** Công cụ chỉ có giá trị khi policy được áp dụng, cấu hình đúng và được kiểm thử.
8. **“Sơ đồ chỉ cần đường happy path.”** Webhook, callback, cron, admin, backup, DLQ và CI/CD thường tạo đường tấn công ngoài luồng chính.
9. **“Đã review lần đầu thì không cần cập nhật.”** Thay service, endpoint, scope, tenant model, nhà cung cấp hoặc auth flow phải kích hoạt review.

## 13. Bài tập áp dụng

### Bài A — Phân tích ranh giới

Một Order Service nhận access token của người dùng, sau đó gọi Payment Service bằng token đó. Payment chỉ kiểm chữ ký và thời hạn, không kiểm audience; Payment API có endpoint /refund.

Hãy xác định: (1) danh tính người dùng và workload đang bị trộn như thế nào; (2) ranh giới nào có thể bị vượt quá quyền; (3) cần kiểm gì ở Payment; (4) test nào chứng minh /refund không bị gọi bởi token dành cho Order.

**Gợi ý:** mô tả issuer/audience/scopes, chính sách workload→action, ủy quyền trên payment attempt và quyền refund riêng; tạo test dùng token đúng chữ ký nhưng sai audience.

### Bài B — Thiết kế idempotency

Order publish OrderPlaced tới broker; Inventory consumer trừ kho và ACK. Consumer crash sau khi commit DB nhưng trước ACK; broker redeliver.

Hãy thiết kế transaction boundary, unique key cho eventId, cách phát hiện duplicate, xử lý lỗi và quan sát. Giải thích vì sao dùng “retry 3 lần” không ngăn trừ kho hai lần.

**Gợi ý:** thao tác reserve và ghi processed-event trong cùng transaction, unique constraint và test redelivery. Nếu có gọi API ngoài DB, hãy thiết kế idempotency cho API đó.

### Bài C — Đa tenant

GET /orders/{orderId} chạy sau API Gateway. Ở tầng service, hệ thống lấy tenantId từ query string; order ID là UUID khó đoán.

Hãy tìm bất biến bị vi phạm, đề xuất truy vấn có điều kiện tenant được suy ra từ principal và viết test âm tính cho hai tenant. Giải thích vì sao UUID khó đoán chỉ giảm đoán ID chứ không tạo authorization.

### Bài D — Kịch bản sự cố liên service

Một service bị khai thác SSRF và có quyền egress rộng. Hãy vẽ attack path từ URL do client cung cấp tới metadata endpoint, credential và Payment API. Đề xuất lớp phòng thủ theo thứ tự: input/URL handling, DNS/IP checks sau resolve, network egress, metadata hardening, workload IAM và Payment authorization.

## 14. Checklist khi đưa threat model vào một dự án thật

- [ ] Có phạm vi, tài sản, bất biến bảo mật và người chịu trách nhiệm.
- [ ] DFD thể hiện request, event, webhook, database, third party, admin và pipeline quan trọng.
- [ ] Mỗi luồng quan trọng ghi rõ principal, giao thức, dữ liệu và ranh giới tin cậy.
- [ ] Tenant isolation, object-level authorization và delegated actions được đánh giá riêng.
- [ ] Workload identity, audience và quyền service-to-service có chính sách chặn mặc định.
- [ ] Các thao tác có side effect (tiền, tồn kho, email) có idempotency/state transition rõ ràng.
- [ ] Broker, consumer, DLQ, webhook và retry được phân tích theo giả định mất/lặp/trễ/sai thứ tự.
- [ ] Đường exfiltration, log/trace, secret, egress và CI/CD nằm trong phạm vi phù hợp.
- [ ] Threat register có owner, ưu tiên, kiểm soát và test xác minh.
- [ ] Có trigger cập nhật khi kiến trúc, quyền hoặc nhà cung cấp thay đổi.

## 15. Tổng kết kiến thức cần vận dụng

Mô hình đe dọa trong microservices bắt đầu bằng **bất biến nghiệp vụ và sơ đồ luồng có ranh giới tin cậy**, sau đó mới chọn công nghệ. Ở mọi ranh giới, trả lời năm câu hỏi:

1. **Ai** đang gọi: người dùng, workload hay nhà cung cấp nào?
2. **Bằng chứng** nào xác thực danh tính và đích của thông điệp?
3. **Quyền** nào cho phép hành động trên đúng tài nguyên/tenant?
4. **Điều gì có thể sai** khi payload giả, lặp, trễ, sai thứ tự hoặc khi service bị chiếm quyền?
5. **Kiểm chứng** nào cho thấy biện pháp bảo vệ thực sự hoạt động?

Một threat model tốt phải giúp người xây dựng hệ thống quyết định chỗ nào cần chặn, test nào cần chạy và ai chịu trách nhiệm với rủi ro còn lại.
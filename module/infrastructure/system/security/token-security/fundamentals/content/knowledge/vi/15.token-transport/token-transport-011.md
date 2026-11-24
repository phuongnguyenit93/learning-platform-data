# Token trong message broker

Một người dùng nhấn **“Hoàn tiền”** trên ứng dụng. API nhận **Bearer access token**, xác minh người gọi và gửi lệnh xử lý vào Kafka hoặc RabbitMQ. Để worker có thể thực hiện tác vụ sau vài phút, lập trình viên sao chép nguyên header **Authorization: Bearer ...** vào message. Cách này có vẻ tiện: consumer chỉ cần lấy token rồi gọi tiếp Payments API. Nhưng nó đưa một **credential có thể sử dụng** vào hệ thống lưu trữ, sao chép, retry và phát lại message. Khi worker thực sự chạy, token có thể đã hết hạn, bị thu hồi, sai audience hoặc bị lộ qua dead-letter queue và công cụ quan sát.

**Nguyên tắc mặc định: không đưa access token, refresh token hay ID token thô vào payload hoặc headers của message broker để “chuyển tiếp đăng nhập”.** Thay vào đó, message nên mang **ngữ cảnh nghiệp vụ tối thiểu**; consumer xác minh nguồn message, sử dụng danh tính dịch vụ của chính nó hoặc nhận một **access token mới đúng audience và scope** qua cơ chế ủy quyền được thiết kế rõ. Consumer vẫn phải thực thi chính sách với tài nguyên tại thời điểm xử lý.

Bài học thuộc chương **Token transport** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trọng tâm là ranh giới tin cậy của JWT, opaque token, access token, refresh token và OAuth 2.0/OIDC khi đi qua hệ thống bất đồng bộ; các yêu cầu xác minh **issuer, audience, scope**, lưu trữ, thu hồi và chống token bị đánh cắp hoặc phát lại.

Sau bài học, bạn sẽ:

- Phân biệt **xác thực với broker** và **truyền thông tin ủy quyền trong message**.
- Giải thích vì sao queue, retry, retention, dead-letter và replay khiến bearer token khó dùng an toàn.
- Chọn mô hình **service identity**, **delegation/token exchange** hoặc **business authorization record** phù hợp.
- Thiết kế message không chứa credential, nhưng vẫn truy vết được chủ thể, tenant, hành động và nguồn phát.
- Kiểm tra quyền tại producer và consumer, bảo vệ broker, logging và đường gọi API phía sau.
- Xây dựng các negative tests cho token bị lộ, sai audience, hết hạn, replay và quyền bị thu hồi.

## 1. Message broker thay đổi ranh giới tin cậy như thế nào?

Trong HTTP đồng bộ, client gửi access token đến **Resource Server** được chỉ định. API kiểm tra token và thường hoàn tất request ngay trong thời gian token còn hiệu lực. Trong xử lý bất đồng bộ, API có thể chỉ **xếp lịch công việc**, còn consumer sẽ chạy sau vài giây, vài giờ hoặc sau khi hệ thống phục hồi.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client
    participant API as Orders API
    participant B as Message Broker
    participant W as Worker
    participant P as Payments API
    U->>C: Yêu cầu hoàn tiền
    C->>API: Bearer access token dành cho Orders API
    API->>API: Xác minh token, scope, tenant và lệnh
    API->>B: Publish lệnh nghiệp vụ tối thiểu
    Note over B: Lưu, retry, phân phối, có thể phát lại
    B-->>W: Deliver message
    W->>W: Xác minh nguồn message và policy
    W->>P: Access token riêng dành cho Payments API
    P->>P: Xác minh token và quyền thanh toán
    P-->>W: Kết quả được phép
~~~

Trong sơ đồ, **Orders API không chuyển access token của client qua broker**. Worker nhận yêu cầu nghiệp vụ với một định danh sự kiện/đối tượng có thể kiểm tra, rồi sử dụng cơ chế được ủy quyền để gọi Payments API.

Các thuộc tính của message broker cần lưu ý:

| Đặc điểm | Hệ quả khi message chứa bearer token |
|---|---|
| **Lưu trữ bền vững** | Token có thể nằm trên ổ đĩa, backup và bản sao lâu hơn thời gian request |
| **Retry và redelivery** | Cùng token có thể đi qua consumer nhiều lần, kể cả sau khi bị thu hồi |
| **Consumer group và fan-out** | Nhiều ứng dụng/instance có thể nhận credential không cần thiết |
| **Dead-letter queue (DLQ)** | Payload lỗi, gồm token nếu có, có thể được giữ và truy cập lâu |
| **Replay/backfill** | Message cũ có thể được đọc lại để dựng trạng thái, dù token đã hết hạn |
| **Observability** | Header/payload bị ghi vào log, trace, metrics hoặc công cụ hỗ trợ |
| **Độ trễ không xác định** | Token ngắn hạn có thể hết hạn trước khi worker chạy |

**Broker vận chuyển message không đồng nghĩa broker là Resource Server mà access token ban đầu được cấp cho.** Một token có **aud=orders-api** không tự trở nên hợp lệ ở worker hay Payments API chỉ vì message được phát từ Orders API.

## 2. Đừng nhầm broker authentication với token nằm trong message

Có **hai vấn đề bảo mật khác nhau**:

1. **Xác thực kết nối đến broker:** producer/consumer chứng minh danh tính với Kafka, RabbitMQ hoặc hệ thống tương đương, thông qua **TLS/mTLS**, SASL hoặc cơ chế broker hỗ trợ.
2. **Ủy quyền thực hiện nghiệp vụ trong message:** consumer cần chứng minh message đến từ nguồn được phép, có đúng tenant/resource/hành động không, và chính worker có quyền gọi API downstream hay không.

Một số broker hỗ trợ **OAuth 2.0 Bearer token cho giao thức xác thực kết nối**, ví dụ cơ chế SASL/OAUTHBEARER trong hệ sinh thái Kafka khi được cấu hình. Đây là **credential dành cho chính broker/authentication service**, được truyền trong handshake theo giao thức, không phải lý do để nhúng access token của người dùng vào payload sự kiện.

| Câu hỏi | Kiểm soát phù hợp |
|---|---|
| Producer nào được kết nối broker? | Broker authentication, TLS/mTLS/SASL, danh tính workload |
| Producer được ghi topic/queue nào? | Broker ACL/permission theo principal và resource |
| Consumer được đọc topic/queue nào? | Broker ACL, consumer group/vhost/queue permissions |
| Message có đến từ nguồn nghiệp vụ đáng tin? | Broker identity và quyền publish; khi cần, chữ ký/MAC message hoặc bản ghi audit có thể xác minh |
| Consumer được làm gì với dữ liệu? | Policy theo subject, action, tenant, resource và trạng thái hiện hành |
| Worker được gọi downstream API nào? | Access token riêng với issuer, audience, scope và client identity phù hợp |

**Đã xác thực kết nối broker không tự động chứng minh mọi field trong message là đúng.** Nếu một producer có quyền ghi topic nhưng bị xâm nhập hoặc tạo dữ liệu sai, consumer vẫn cần kiểm tra schema, nguồn dữ liệu, tenant và policy. Nếu message đi qua nhiều relay hoặc kho lưu trung gian, cân nhắc **chứng cứ nguồn gốc end-to-end** thay vì chỉ tin danh tính của kết nối broker cuối cùng.

## 3. Tại sao không chuyển tiếp Bearer access token qua queue?

### 3.1. Token có thể hết hạn trước khi được tiêu thụ

Giả sử access token có hiệu lực từ 09:00 đến 09:15. Lệnh được publish lúc 09:08, nhưng worker chỉ chạy lúc 09:40 vì backlog. Token cũ đã hết hạn. **Không được bỏ qua exp, nbf hoặc signature validation để cho job chạy được.** Mở rộng TTL access token thành nhiều ngày cũng làm tăng cửa sổ rủi ro nếu nó bị lộ.

### 3.2. Audience thường không phù hợp với downstream API

Access token của người dùng có thể có **aud=orders-api**. Worker sau đó cần gọi **payments-api**. Payments API phải từ chối token của Orders API, kể cả khi **issuer và chữ ký đều hợp lệ**. Một OAuth access token luôn có ngữ cảnh bên nhận; không dùng token của một API như credential đa năng cho tất cả các service.

### 3.3. Scope không tự cho phép thao tác sau thời gian chờ

Token có **scope=orders:read** không cho phép **payments:refund**. Ngay cả token đã được cấp scope thích hợp tại thời điểm publish, quyền người dùng theo **tenant, ownership, role, approval và trạng thái tài nguyên** có thể thay đổi trước khi consume. Một JWT được ký chỉ phản ánh claims tại thời điểm phát hành; chữ ký đúng không chứng minh policy vẫn đúng hiện tại.

### 3.4. Replay vốn là khả năng bình thường của broker

Broker có thể phân phối **at least once** và tái giao cùng message do retry, consumer crash hoặc rebalancing. Với Kafka, operator còn có thể chủ động reset offset và đọc lại dữ liệu. Nếu message chứa bearer token, mỗi lần replay cũng **tái phơi bày credential**. Tránh lấy **jti** hoặc token ID làm idempotency key nghiệp vụ; jti là metadata token, không nhất thiết là định danh duy nhất của một lệnh hoàn tiền.

### 3.5. Token tồn tại trên nhiều lớp lưu trữ

Khi message có credential, các bản sao có thể nằm trong:

- Broker log/segment, replication và snapshot.
- DLQ, retry queue, parking-lot queue, mirror hoặc bridge.
- Consumer memory dump, debug log, tracing, exception.
- Hệ thống phân tích, công cụ replay, export, backup và môi trường staging được sao chép dữ liệu.

**Mã hóa TLS bảo vệ đường truyền, không xóa bản sao token đã được ghi vào broker hoặc log.** Mã hóa at rest giúp giảm rủi ro khi ổ đĩa bị đọc trái phép, nhưng consumer được phép giải mã vẫn có thể tiếp xúc credential.

## 4. Access token, refresh token và ID token: không loại nào là event payload mặc định

| Credential | Bên nhận dự kiến | Rủi ro khi đặt trong message | Thiết kế thay thế |
|---|---|---|---|
| **OAuth access token (JWT)** | Resource Server đúng audience | Bị replay, hết hạn, sai audience; JWS payload dễ đọc | Worker nhận access token mới khi cần |
| **OAuth access token (opaque)** | Resource Server/điểm xác minh tin cậy | Vẫn là bearer credential dù không đọc được claims; cache/revocation phức tạp | Không gửi chuỗi qua broker; chỉ truyền business ID |
| **Refresh token** | Authorization Server/token endpoint | Có thể xin thêm access token; lưu dài hạn và rò rỉ qua DLQ rất nguy hiểm | Chỉ thành phần được ủy quyền giữ refresh token và làm mới trực tiếp với AS |
| **OIDC ID token** | Client/Relying Party | Không dùng để gọi API; có thể làm lộ claims danh tính | Chỉ truyền principal reference/bằng chứng được thiết kế riêng |
| **Authorization code / PKCE verifier** | Thành phần đổi code theo OAuth flow | Có thể bị lộ credential tạm thời hoặc sai flow | Không nhúng vào message nghiệp vụ |
| **Session cookie / API key** | Điểm xác thực được quy định | Có nguy cơ chiếm phiên hoặc dịch vụ | Dùng danh tính workload/service và secret manager phù hợp |

**JWT hay opaque** là cách biểu diễn và xác minh, còn **access, refresh, ID token** mô tả mục đích. Định dạng không thay đổi ranh giới: **refresh token không được đưa vào message chỉ vì nó là chuỗi opaque**, và **ID token không được biến thành access token** dù có chữ ký hợp lệ.

Nếu cần chuyển chứng cứ ủy quyền qua bất đồng bộ, hãy chọn **một cơ chế ủy quyền dành riêng cho tác vụ đó**, với thời gian sống, audience, phạm vi, nguồn phát, khả năng thu hồi và audit rõ ràng; không sao chép token của request vào event theo thói quen.

## 5. Mô hình ưu tiên: Consumer dùng service identity

Với công việc mà hệ thống cho phép **dịch vụ tự thực hiện** sau khi API đã tiếp nhận yêu cầu hợp lệ, consumer có thể dùng **danh tính workload** của chính nó:

1. HTTP API xác thực access token, kiểm **iss, aud, exp, scope** và quyền trên resource.
2. API tạo **lệnh nghiệp vụ** hoặc bản ghi công việc đã được phê duyệt theo policy.
3. API publish message gồm **command ID, tenant ID, resource ID và metadata tối thiểu**, không chứa bearer token.
4. Worker được broker xác thực, nhận message và xác minh nguồn, tính hợp lệ của lệnh và trạng thái nghiệp vụ.
5. Worker sử dụng **Client Credentials** hoặc danh tính workload được AS chấp thuận để nhận **access token riêng dành cho downstream API**.
6. Downstream API kiểm issuer, audience, scope và quyền của **service principal**, không giả định nó là người dùng cuối.

~~~mermaid
sequenceDiagram
    participant API as Orders API
    participant B as Broker
    participant W as Refund Worker
    participant AS as Authorization Server
    participant P as Payments API
    API->>API: Xác minh người dùng và tạo authorized job
    API->>B: refund.requested: jobId, orderId, tenantId
    B-->>W: Deliver command
    W->>W: Kiểm source, job state và tenant
    W->>AS: Client credentials / workload proof
    AS-->>W: Access token aud=payments-api
    W->>P: Refund request + Bearer service access token
    P->>P: Kiểm token, scope, refund policy và idempotency
    P-->>W: Kết quả nghiệp vụ
~~~

**Quan trọng:** Service token chứng minh **quyền của worker/service**, không tự chứng minh user từng đồng ý hoặc có quyền. Nếu nghiệp vụ phải có phê duyệt người dùng, consumer phải truy xuất **bản ghi ủy quyền/approval** được bảo vệ, còn hiệu lực và ràng buộc đúng order/amount/tenant. Không dùng service account như “siêu người dùng” để bỏ qua kiểm soát nghiệp vụ.

### Khi nào nên dùng service identity?

- Công việc nền được hệ thống cho phép thực hiện theo vai trò dịch vụ, ví dụ tạo báo cáo, đồng bộ cache hoặc xử lý event hợp lệ.
- Tác vụ đã được **chuyển thành trạng thái nghiệp vụ bền vững** sau khi người dùng được kiểm tra tại thời điểm yêu cầu.
- Downstream API có policy riêng cho service principal và kiểm điều kiện đối tượng/tenant.

Nếu hành động **bắt buộc được thực thi thay mặt người dùng cụ thể**, cần mô hình delegation chặt chẽ hơn; không giả mạo danh tính người dùng bằng cách tự đặt **sub=user-42** trong message.

## 6. Khi cần “on behalf of user”: delegation và token exchange

Một số tác vụ phải thực thi **theo quyền của người dùng**, không chỉ theo quyền hệ thống. Ví dụ worker thay mặt người dùng truy vấn một API ở tenant khác, trong đó service principal riêng không được phép tự truy cập.

**OAuth 2.0 Token Exchange (RFC 8693)** có thể cho phép một thành phần được ủy quyền đổi chứng cứ hợp lệ thành **token mới đúng audience, scope và ngữ cảnh chủ thể/actor**, nếu AS hỗ trợ. Đây là một lựa chọn, **không phải đặc quyền mặc nhiên** của worker.

Đặc biệt trong xử lý bất đồng bộ:

- Token đầu vào có thể hết hạn trước khi worker chạy. Không thể giả định một access token cũ vẫn có thể đổi sau nhiều giờ.
- AS phải kiểm **delegation grant còn hiệu lực**, quyền của worker, subject, resource, scope và audience.
- Nếu cần sử dụng dài hạn, nên thiết kế **ủy quyền bền vững, có thể thu hồi** hoặc một cơ chế consent/approval có phạm vi cụ thể; không lưu refresh token của người dùng vào message.
- Worker cần nhận **access token mới khi sắp gọi downstream API**, từ nguồn AS tin cậy, thay vì nhận token dài hạn cùng message.
- Downstream API phải hiểu **actor vs subject** theo profile được thỏa thuận; service token không tự biến thành token của người dùng.

Một quyết định thiết kế:

| Nhu cầu | Mô hình phù hợp hơn |
|---|---|
| Worker chạy theo quyền máy để hoàn thành công việc nội bộ | **Client Credentials/workload identity** với scope/audience tối thiểu |
| Worker cần quyền người dùng tại thời điểm thực hiện | **Delegation/token exchange** được AS chấp thuận, hoặc cơ chế authorization grant tương đương |
| Công việc đã được phê duyệt cụ thể và cần chạy sau nhiều giờ | **Durable authorization/approval record** kiểm chứng được, ràng buộc action/resource/tenant/TTL |
| Cần sự đồng ý mới trước khi thao tác nhạy cảm | **Tạm dừng job**, yêu cầu user reauthorize/step-up, không tự nối dài quyền |

Đừng gán một access token của người dùng vào message để “giữ hộ quyền”. Token có thể là bearer, có audience riêng, có TTL và cơ chế revoke không tương ứng với thời gian công việc nằm trong hàng đợi.

## 7. Thiết kế message envelope không chứa credential

Một message nên mô tả **ý định và ngữ cảnh nghiệp vụ cần thiết**, không sao chép HTTP request nguyên vẹn.

Ví dụ event/lệnh minh họa:

~~~json
{
  "schemaVersion": 1,
  "messageId": "msg-8d21-example",
  "type": "refund.requested",
  "occurredAt": "2026-11-23T09:00:00Z",
  "producer": "orders-service",
  "tenantId": "tenant-17",
  "jobId": "refund-job-590",
  "orderId": "order-901",
  "approvalRef": "approval-72",
  "correlationId": "corr-201"
}
~~~

Đây là dữ liệu giả để minh họa, **không phải bằng chứng ủy quyền tự thân**. Consumer phải kiểm chứng rằng **producer** thực sự được phép tạo loại lệnh này, **jobId/approvalRef** tồn tại trong kho tin cậy, và **orderId, tenantId, action** khớp với hồ sơ nghiệp vụ.

### Những trường không đưa vào envelope hoặc headers

~~~text
Authorization: Bearer <access-token>
refresh_token: <refresh-token>
id_token: <id-token>
Cookie: session=<credential>
client_secret: <secret>
code_verifier: <pkce-verifier>
private_key: <key>
~~~

**Message headers cũng thường được lưu cùng message** và có thể đi vào DLQ, tracing, replay hoặc công cụ broker. Chuyển token từ JSON payload sang Kafka headers hoặc RabbitMQ properties **không biến token thành an toàn**.

### Ngữ cảnh nào có thể đi cùng message?

| Thuộc tính | Có thể mang? | Điều kiện |
|---|---|---|
| **messageId / jobId** | Có | Server tạo hoặc xác minh; dùng chống trùng và audit |
| **tenantId / resourceId** | Có | Chỉ là identifier, phải ràng buộc với bản ghi đáng tin khi consume |
| **initiatedBy / subjectRef** | Có điều kiện | Không phải proof xác thực; xác minh qua bản ghi phê duyệt hoặc nguồn danh tính tin cậy |
| **approvalRef** | Có | Tham chiếu tới authorization record có trạng thái, TTL, action và resource |
| **correlationId** | Có | Không chứa token; giới hạn dữ liệu cá nhân và độ dài |
| **scope/role snapshot** | Hạn chế | Không coi metadata tự khai hoặc stale snapshot là quyền hiện tại |
| **Access/refresh/ID token** | **Không theo mặc định** | Dùng cơ chế lấy token/ủy quyền tại điểm thực hiện thay thế |

Một identifier như **subjectRef** hoặc **tenantId** vẫn có thể là dữ liệu nhạy cảm cần kiểm soát retention, quyền đọc và mục đích. **Không phải credential** không có nghĩa được phép log hoặc chia sẻ không giới hạn.

## 8. Consumer phải xác minh điều gì trước khi thực thi?

Consumer xử lý dữ liệu từ broker như **đầu vào chưa đủ tin cậy để quyết định quyền**, kể cả broker có ACL.

Quy trình ở mức kiến trúc:

~~~mermaid
flowchart TD
    A["Consumer nhận message"] --> B{"Nguồn broker/topic/producer được phép?"}
    B -->|Không| X["Reject / quarantine an toàn"]
    B -->|Có| C{"Schema, kích thước và messageId hợp lệ?"}
    C -->|Không| X
    C -->|Có| D{"Message/job đã xử lý chưa?"}
    D -->|Rồi| Y["Ack idempotent, không thực hiện lại"]
    D -->|Chưa| E["Tải job và approval từ kho tin cậy"]
    E --> F{"Tenant/resource/action và trạng thái khớp?"}
    F -->|Không| X
    F -->|Có| G{"Policy tại thời điểm consume cho phép?"}
    G -->|Không| Z["Deny/cancel/escalate job"]
    G -->|Có| H["Lấy service/delegated token đúng audience"]
    H --> I["Gọi API với idempotency và scope phù hợp"]
    I --> J["Lưu kết quả bền vững, ack"]
~~~

Các kiểm tra cần thiết:

1. **Nguồn:** service nào được phép publish vào topic/queue này? Có kiểm soát broker ACL, producer identity, vhost, consumer group hay không?
2. **Tính toàn vẹn:** schema, version, kích thước, field bắt buộc, kiểu dữ liệu và nguồn gốc có phù hợp không? Nếu có relay không hoàn toàn tin cậy, cần bảo vệ message authenticity end-to-end.
3. **Idempotency/replay:** messageId/jobId đã được xử lý chưa? Redelivery không được tạo thêm side effect.
4. **Tenant boundary:** message có chỉ tới resource trong đúng tenant/workspace được kiểm chứng từ database không?
5. **Ủy quyền nghiệp vụ:** command có approval hợp lệ, đúng action, đúng tài nguyên, hạn mức, thời hạn và trạng thái không?
6. **Độ mới quyền:** có cần kiểm quyền người dùng/ủy quyền hiện hành, hay policy cho phép dùng approval đã được chốt từ lúc submit? Quy tắc phải rõ và được audit.
7. **Token downstream:** chỉ cấp access token **đúng loại, đúng issuer/audience/scope** cho worker ngay trước lời gọi đến Resource Server.
8. **Xử lý thất bại:** không leak token vào message retry/DLQ; phân biệt lỗi tạm thời và lỗi từ chối vĩnh viễn.

**Một message chứa subjectId, scope và role không phải JWT đã được xác minh**, và cũng không phải authorization decision đủ điều kiện. Nếu kẻ tấn công có quyền publish message tự đặt **role=ADMIN**, consumer không được tin role này để bỏ qua policy.

## 9. Thời điểm kiểm tra quyền: lúc publish hay lúc consume?

Trong xử lý bất đồng bộ, hai thời điểm có thể cách nhau nhiều giờ. Do đó cần định nghĩa **ngữ nghĩa ủy quyền của job**:

| Chiến lược | Phù hợp khi | Rủi ro và kiểm soát |
|---|---|---|
| **Kiểm tại submit và kiểm lại khi consume** | Thao tác nhạy cảm, quyền thay đổi nhanh | Người dùng mất quyền → job phải bị từ chối/cần phê duyệt mới |
| **Chốt một authorization record tại submit** | Công việc đã được chấp thuận rõ và cần hoàn tất kể cả user offline | Record phải ràng buộc action/resource/amount/TTL, có thể thu hồi; consumer xác minh trạng thái record |
| **Chỉ dùng service permission** | Công việc định kỳ thuộc quyền của chính dịch vụ | Không được mượn quyền máy để bỏ qua yêu cầu approval người dùng |
| **Yêu cầu reauthorization tại execution** | Hành động có giá trị cao hoặc tuân thủ quy định step-up | Job tạm dừng khi không có bằng chứng ủy quyền mới |

Ví dụ user được phép yêu cầu hoàn tiền lúc 09:00 nhưng bị gỡ vai trò lúc 09:05; job chạy lúc 09:10. Nếu policy yêu cầu **quyền hiện hành**, phải từ chối. Nếu doanh nghiệp cho phép **quyết định phê duyệt đã chốt**, job có thể tiếp tục **chỉ khi** approval record còn hiệu lực, chưa bị thu hồi và đúng số tiền/đơn hàng. Không thể thay sự lựa chọn policy này bằng việc giữ access token cũ trong message.

Điểm quan trọng: **AuthN/AuthZ tại ingress và AuthZ tại execution giải quyết những câu hỏi khác nhau**. Quyền nhận yêu cầu không luôn bằng quyền thực thi một tác vụ trễ, nhất là khi người dùng, tenant và resource state thay đổi.

## 10. Bảo vệ broker, DLQ, retry và replay

### 10.1. Kết nối và quyền truy cập

- Dùng **TLS/mTLS** hoặc cơ chế transport security mà broker hỗ trợ, xác minh certificate đúng cách và quản lý secrets riêng.
- Xác thực producer và consumer bằng danh tính ứng dụng/workload, có **quyền publish/consume tối thiểu** theo topic, queue, routing key, vhost hoặc consumer group.
- Tách môi trường dev/staging/production và tenant nhạy cảm nếu mô hình truy cập yêu cầu.
- Mã hóa at rest và bảo vệ key/backup; tránh tài khoản vận hành có quyền đọc toàn bộ payload khi không cần.
- Giám sát thay đổi ACL, tạo consumer mới, hoạt động replay/backfill và truy cập DLQ.

### 10.2. Retry và dead-letter

Message lỗi có thể được chuyển qua **retry topic** và **dead-letter queue**. Nếu message ban đầu chứa credential, mọi bản sao phụ cũng có credential. Do đó **phòng ngừa từ envelope ban đầu** là biện pháp tốt nhất.

Phân biệt lỗi:

- **Lỗi tạm thời** như API downstream trả 503 có thể retry với backoff/jitter, giới hạn số lần, không lưu token mới nhận vào message.
- **Lỗi quyền** như token sai audience hoặc approval bị revoke thường không nên retry vô hạn; xử lý deny/cancel/escalate.
- **Schema sai hoặc message nguồn không tin cậy** cần quarantine theo chính sách, không in toàn payload hoặc secrets ra log.
- **Job đã xử lý** phải được ack/đánh dấu idempotent, không thực hiện hoàn tiền lần hai vì redelivery.

### 10.3. Retention và replay

Với broker có retention dài hoặc khả năng replay, message phải còn **có ý nghĩa nghiệp vụ khi được đọc lại** mà không cần token của lần HTTP gốc. Consumer nên kiểm **message version**, job state, idempotency và chính sách hiện hành. Nếu một command đã hoàn thành, replay chỉ nên tái dựng trạng thái hoặc được bỏ qua, **không thực hiện side effect lần nữa**.

**Exactly-once processing** của một framework/broker không tự bảo đảm một lời gọi HTTP đến Payments API chỉ xảy ra một lần khi có crash, timeout hoặc retry xuyên hệ thống. Cần **business idempotency key** và ràng buộc giao dịch ở phía thực thi/downstream.

## 11. Mẫu xử lý consumer an toàn

Pseudocode dưới đây là mô hình trách nhiệm, **không phải ứng dụng Kafka/RabbitMQ chạy trực tiếp**:

~~~text
handleRefundRequested(message, brokerContext):
    if not trustedProducerForTopic(brokerContext, "refund.requested"):
        rejectOrQuarantineWithoutLoggingPayload()

    command = parseAndValidateSchema(message)
    if command.invalid or containsForbiddenCredentialFields(command):
        rejectOrQuarantineWithoutLoggingPayload()

    if idempotencyStore.wasCompleted(command.jobId):
        acknowledgeWithoutReExecuting()

    job = jobRepository.find(command.jobId)
    approval = approvalRepository.find(job.approvalRef)
    if job missing or approval missing:
        denyJob()

    if not identifiersMatch(job, command.tenantId, command.orderId):
        denyJob()

    if not approval.allows("refund", job.orderId, job.amount):
        denyJob()

    if approval.revoked or approval.expired or not currentPolicyAllows(job):
        cancelOrEscalateJob()

    # Token được cấp gần thời điểm sử dụng, không lấy từ message.
    serviceAccessToken = authorizationServer.obtainAccessToken(
        clientIdentity = trustedWorkerIdentity,
        audience = "payments-api",
        scopes = ["payments:refund"]
    )

    response = paymentsApi.refund(
        orderId = job.orderId,
        amount = job.amount,
        idempotencyKey = job.jobId,
        accessToken = serviceAccessToken
    )

    recordResultAndAcknowledgeAccordingToDeliverySemantics(response)
~~~

Các điểm cần triển khai chặt chẽ:

- **trustedProducerForTopic** không được chỉ tin chuỗi **producer** trong JSON. Nó phải xuất phát từ danh tính/quyền kết nối broker, nguồn đã ký hoặc bản ghi phê duyệt được truy xuất an toàn.
- **containsForbiddenCredentialFields** chỉ là lớp kiểm tra bổ sung. Giải pháp chính là **schema allowlist không có field token**, không ghi raw message để debug.
- **currentPolicyAllows** phải sử dụng mô hình ủy quyền thích hợp; một approval đã chốt có thể có quy tắc hiệu lực riêng.
- **authorizationServer.obtainAccessToken** là lời gọi khái niệm. Không nhét client secret trong message; client được xác thực bằng cơ chế phù hợp và không vượt quyền.
- **idempotencyStore** và downstream cần xử lý tranh chấp đồng thời. Đánh dấu completed trước khi hoàn thành side effect có thể làm mất job; đánh dấu sau mà không có idempotency downstream có thể tạo side effect trùng.

### Outbox và ranh giới giao dịch

Nếu Orders API ghi approval/job vào database rồi publish message, hai thao tác có thể thất bại ở hai thời điểm khác nhau. **Transactional outbox** là một cách giúp ghi **trạng thái nghiệp vụ và bản ghi sự kiện cần phát** trong cùng giao dịch database; một publisher khác đưa event ra broker sau đó.

Outbox không thay thế xác minh token hay phân quyền, nhưng giúp consumer có **job/approval record bền vững** để kiểm lại, thay vì đặt toàn bộ chứng cứ quyền và bearer token vào message.

## 12. Hai ví dụ HTTP và broker: sai và đúng

### Thiết kế sai

Client gửi access token dành cho Orders API. Producer sao chép nguyên header Authorization vào message:

~~~json
{
  "type": "refund.requested",
  "orderId": "order-901",
  "headers": {
    "Authorization": "Bearer <user-access-token-for-orders-api>"
  },
  "refreshToken": "<user-refresh-token>"
}
~~~

Các giá trị đều là placeholder, không phải credential thật. Nhưng về mặt thiết kế, message này:

1. Mang bearer credential đến nơi nhận khác với API được cấp.
2. Có thể nằm trên broker và DLQ sau khi token hết hạn.
3. Đưa refresh token của client đến worker không có quyền nắm nó.
4. Khuyến khích worker gọi Payments API bằng access token sai audience.
5. Tạo đường rò qua log, trace, replay và backup.

### Thiết kế an toàn hơn

~~~json
{
  "schemaVersion": 1,
  "messageId": "msg-refund-01",
  "type": "refund.requested",
  "jobId": "refund-job-590",
  "tenantId": "tenant-17",
  "orderId": "order-901",
  "approvalRef": "approval-72"
}
~~~

Consumer tra job/approval qua nguồn đáng tin, kiểm policy và lấy access token của chính worker **aud=payments-api** khi thực thi. Nếu job đòi quyền người dùng được ủy nhiệm, dùng cơ chế delegation/grant riêng đã được AS chấp thuận. **Không coi approvalRef tự nó là bằng chứng có thể sửa tùy ý:** phải kiểm người phát, trạng thái và dữ liệu được bảo vệ phía server.

## 13. Quan sát và ứng cứu khi token đã lọt vào queue

### Log và tracing an toàn

Không ghi:

~~~text
Authorization: Bearer <raw-token>
refresh_token=<raw-refresh-token>
id_token=<raw-id-token>
Kafka message payload=<entire-message-with-secrets>
RabbitMQ headers=<raw-headers-with-credentials>
~~~

Thay vào đó, chỉ ghi metadata được cho phép:

~~~json
{
  "event": "refund_job_consumed",
  "message_id": "msg-refund-01",
  "job_id": "refund-job-590",
  "consumer": "refund-worker",
  "result": "denied",
  "reason_code": "APPROVAL_REVOKED"
}
~~~

Ngay cả **tenantId, subjectRef, messageId** cũng có thể là dữ liệu cần kiểm soát theo chính sách riêng tư. Với metrics, ưu tiên **số đếm theo topic/operation/result/reason code** thay vì raw token hoặc user ID làm label.

### Nếu phát hiện credential trong broker

1. **Chặn nguồn phát:** sửa publisher/schema/interceptor để không đưa token vào message và headers mới.
2. **Xác định phạm vi:** broker partitions/topics/queues, DLQ, retry, replicas, mirrors, tracing, logs, backups, exports và nhóm có quyền consume.
3. **Đánh giá hiệu lực:** token loại gì, còn hạn không, audience/scope nào, có sender-constraining hay không, đã bị phát lại chưa.
4. **Thu hồi phù hợp:** revoke access/refresh token hoặc token family theo cơ chế AS và chính sách sự cố; giới hạn quyền consume/read, bảo vệ dữ liệu còn lưu.
5. **Xử lý dữ liệu đã sao chép:** áp dụng quy trình retention/xóa/quarantine và phối hợp chủ sở hữu hệ thống; **xóa message chính không chứng minh mọi bản sao đã mất**.
6. **Kiểm chứng:** chạy negative tests bằng token giả, kiểm broker headers, DLQ, logs và telemetry; thêm schema/guardrails để ngăn tái phát.

**Thu hồi bearer token ngăn credential tiếp tục được dùng theo cơ chế hệ thống; nó không tự xóa claims hoặc dữ liệu đã bị sao chép.** Với JWT ký thông thường, payload có thể đã được đọc bởi mọi bên có bản sao token.

## 14. Ma trận kiểm thử bảo mật message broker

| Tình huống | Kết quả mong đợi |
|---|---|
| Message hợp lệ từ producer được phép, job/approval còn hiệu lực | Worker thực thi theo policy, không nhận token từ payload |
| Message chứa field **accessToken** hoặc **Authorization** | Bị schema/guardrail từ chối hoặc xử lý an toàn; không ghi credential thô |
| Message chứa **refreshToken** trong headers | Không dùng để xin token mới; ngăn lộ qua DLQ/log |
| Broker nhận producer không có quyền publish topic | Broker từ chối theo ACL |
| Consumer không có quyền đọc topic hoặc DLQ | Broker từ chối theo ACL |
| Message tự khai **producer=trusted-service** nhưng nguồn broker không đáng tin | Consumer từ chối hoặc quarantine |
| Message có **tenantId** khác với job record | Không thực thi |
| Approval bị thu hồi trước khi consume | Từ chối/cancel hoặc quy trình đặc biệt đúng policy |
| JWT của user hết hạn trước khi worker chạy | Không bypass exp; worker dùng cơ chế ủy quyền riêng |
| Worker gọi Payments API bằng token **aud=orders-api** | Payments API từ chối |
| Worker có access token riêng **aud=payments-api** nhưng thiếu scope refund | Payments API từ chối |
| Message bị redeliver sau khi hoàn tiền thành công | Không hoàn tiền lần hai nhờ idempotency |
| Retry chuyển message đến DLQ | DLQ không chứa bearer/refresh token và được phân quyền chặt |
| Backfill/replay lại message một tháng trước | Không cấp quyền từ claims cũ; kiểm job state và xử lý idempotent |
| Kết nối đến AS hoặc downstream lỗi | Retry có giới hạn, không fail open, không in access token vào log |
| Hệ thống bật debug HTTP/message tracing | Không xuất credential trong payload, headers, spans hoặc crash report |
| Issuer hoặc signing key của token downstream bị thu hồi | Không tiếp tục chấp nhận token từ nguồn bị vô hiệu hóa |

**Kiểm thử phải quan sát side effect thực tế**, không chỉ phản hồi ACK/NACK. Một message bị xử lý hai lần nhưng cả hai đều ACK “thành công” vẫn là lỗi nếu thanh toán/hoàn tiền xảy ra hai lần.

## 15. Checklist triển khai

1. **Message schema:** đã loại access token, refresh token, ID token, cookie, code, verifier và secrets khỏi cả payload lẫn headers chưa?
2. **Trust boundary:** producer/consumer được xác thực với broker và phân quyền theo topic/queue/vhost/consumer group chưa?
3. **Token purpose:** đã phân biệt credential xác thực broker với access token dùng gọi Resource Server chưa?
4. **Producer checks:** HTTP API đã xác minh issuer, audience, scope và quyền đối tượng trước khi tạo job chưa?
5. **Provenance:** consumer có xác minh nguồn message độc lập với field producer tự khai không?
6. **Authorization at consume:** policy có quy định quyền hiện hành, approval còn hiệu lực, tenant/resource/action và TTL rõ ràng chưa?
7. **Downstream access:** worker lấy token mới đúng issuer/audience/scope khi cần, không chuyển tiếp token của HTTP request ban đầu?
8. **Delegation:** nếu cần thay mặt người dùng, đã có grant/token exchange hoặc record được ủy quyền, có thể thu hồi chưa?
9. **Idempotency:** retry, redelivery, offset reset, replay và concurrent consumers có được xử lý theo jobId/idempotency key?
10. **DLQ/retention:** bản sao message, retries, backups, replicas, mirrors có được phân quyền, mã hóa và giữ thời gian phù hợp không?
11. **Observability:** logs/traces/metrics có tránh raw payload/header chứa credential và tránh dữ liệu cá nhân dư thừa không?
12. **Failure semantics:** phân biệt lỗi tạm thời với lỗi quyền, không retry vô hạn hoặc cho phép khi AS/RS không xác minh được?
13. **Incident response:** có thể thu hồi token, hạn chế broker readers và xác định bản sao trong DLQ/backup khi xảy ra lộ credential không?
14. **Test coverage:** có negative tests cho sai producer, sai tenant, revoked approval, expired token, wrong audience, duplicate delivery và log leakage không?

## 16. Câu hỏi tự đánh giá

**1. Vì sao không nên đưa Bearer access token vào Kafka message để worker dùng sau?** Vì message có thể được lưu, retry, replay, chuyển DLQ và đọc bởi nhiều thành phần; token có thể hết hạn, sai audience hoặc bị lộ như một credential đang hoạt động.

**2. Kafka/RabbitMQ xác thực producer bằng SASL/OAuth hoặc mTLS có nghĩa mọi message đều được phép thực thi không?** Không. Broker authentication chứng minh danh tính kết nối theo cấu hình; consumer vẫn phải kiểm schema, provenance, tenant, approval, trạng thái và policy nghiệp vụ.

**3. Nếu access token ban đầu có aud=orders-api, worker có được dùng nó gọi Payments API?** Không. Payments API cần access token dành cho chính mình với scope thích hợp và kiểm tra policy của nó.

**4. Refresh token có thể đặt trong message header để worker xin access token mới không?** Không theo thiết kế mặc định. Headers cũng có thể được lưu và sao chép, còn refresh token là credential có khả năng duy trì truy cập dài hạn, chỉ nên do thành phần được ủy quyền quản lý.

**5. Worker có service token thì có thể hoàn tiền mọi đơn không?** Không. Service token cho phép danh tính workload gọi API trong quyền cấp; nghiệp vụ vẫn phải kiểm order, tenant, số tiền, approval và idempotency.

**6. Một message đã được phê duyệt ở thời điểm publish thì có cần kiểm quyền khi consume?** Tùy chính sách đã thiết kế: có thể cần quyền hiện hành hoặc kiểm một approval record bền vững, còn hiệu lực, có thể thu hồi. Không mặc nhiên tin token/role snapshot cũ.

**7. Replay cùng một message có nghĩa phải chạy lại hành động không?** Không. Consumer phải dùng idempotency và job state để ngăn side effect trùng, đặc biệt với chuyển tiền hoặc hoàn tiền.

**8. Chuyển bearer token từ payload sang broker header có giải quyết rủi ro không?** Không. Headers có thể nằm cùng record, DLQ, logs và tracing.

**9. Tại sao TLS và mã hóa at rest vẫn chưa đủ?** Vì producer, broker operator, consumer hoặc pipeline được phép đọc/giải mã vẫn có thể sao chép token; retention và replay vẫn tồn tại.

**10. Khi cần gọi API thay mặt người dùng sau nhiều giờ, nên làm gì?** Thiết kế cơ chế delegation/authorization record bền vững có thể thu hồi, hoặc yêu cầu xác thực lại; nhận access token phù hợp gần thời điểm gọi API, không giữ bearer token cũ trong queue.

**Ghi nhớ:** **Message broker là kênh vận chuyển và lưu trữ công việc, không phải nơi giữ hộ access token hay refresh token của người dùng.** Hãy xác thực producer/consumer với broker, gửi message nghiệp vụ tối thiểu, kiểm nguồn và policy tại thời điểm thực thi, sử dụng service identity hoặc delegation được AS chấp thuận để nhận access token mới đúng audience/scope, và thiết kế retry, DLQ, replay cùng idempotency ngay từ đầu. Việc bảo vệ token xuyên hệ thống bất đồng bộ là bảo vệ **cả nơi nhận credential lẫn quyết định quyền thực hiện công việc**, không chỉ mã hóa đường truyền.

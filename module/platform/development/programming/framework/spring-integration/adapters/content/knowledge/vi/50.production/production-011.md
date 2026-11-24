# Runbook cho mất kết nối hệ thống ngoài trong Spring Integration Adapters

> **Chương:** Production  
> **Chủ đề:** Runbook cho mất kết nối hệ thống ngoài  
> **Phạm vi module:** SPRING_INTEGRATION_ADAPTERS — vận hành tích hợp inbound/outbound adapter, gateway, poller và MessageChannel của Spring Integration; các luồng File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Runbook tập trung vào nhận diện mất kết nối, giới hạn tác động, bảo toàn message, khôi phục an toàn và xác minh kết quả nghiệp vụ.

## 1. Mục đích, phạm vi và cách sử dụng runbook

Một kết nối bên ngoài bị gián đoạn không chỉ gây log lỗi. Hậu quả có thể là **không nhận được dữ liệu mới, tồn đọng tăng, request/reply timeout, token không được xác nhận, message được giao lại, hoặc tác động nghiệp vụ đã xảy ra nhưng ứng dụng không biết kết quả**. Trong production, khôi phục kết nối mà bỏ qua trạng thái message có thể nguy hiểm hơn cả sự cố ban đầu.

Runbook này trả lời bốn câu hỏi theo đúng thứ tự:

1. **Có sự cố thật không?** Đó là lỗi kết nối, chứng thực, cấu hình, hạ tầng hay đơn thuần nguồn không có dữ liệu?
2. **Tác động đến đâu?** Những flow, tenant, đối tác, message và cam kết dịch vụ nào bị ảnh hưởng?
3. **Làm sao giữ an toàn?** Nên dừng, giảm tải, buffer, retry hay cô lập connector để tránh mất/trùng/đổi thứ tự dữ liệu?
4. **Khôi phục và chứng minh thế nào?** Kết nối thành công **chưa đủ**; phải kiểm tra nhận, xử lý, commit, ack/offset, backlog và trạng thái hệ đích.

### 1.1. Đối tượng sử dụng

- **On-call/SRE/Production Support:** phát hiện, phân loại, cô lập, khôi phục, theo dõi SLO và điều phối sự cố.
- **Integration Engineer:** kiểm tra Spring Integration flow, endpoint lifecycle, channel, adapter, gateway, poller và error path.
- **System Owner/Partner Owner:** xác minh bên ngoài (SFTP server, API, broker, DB, chứng chỉ, quota) và thay đổi kết nối có kiểm soát.
- **Business/Data Owner:** đánh giá tác động, quyết định replay, bù trừ giao dịch hoặc chấp nhận mất dữ liệu theo quy trình.
- **Security/Compliance:** tham gia khi nghi ngờ credential bị lộ, chứng chỉ giả mạo, truy cập trái phép hoặc mất tính toàn vẹn dữ liệu.

Runbook **không cho phép** tự xóa dữ liệu, tự bỏ qua TLS/host-key verification, tua offset, bỏ qua dead-letter queue hoặc chỉnh sửa giao dịch đã commit. Những thao tác làm thay đổi trạng thái cần quyền phù hợp, bằng chứng và phương án rollback.

### 1.2. Điều kiện đầu vào khi xảy ra incident

Một bản ghi sự cố tối thiểu cần có:

| Trường | Ví dụ điền | Vì sao cần |
| --- | --- | --- |
| Incident ID | INC-LAB-2026-011 | Liên kết log, quyết định, communication |
| Detected at | 2026-11-23T15:10:00+07:00 | Mốc tính thời gian lỗi và SLA |
| Flow/endpoint | partner-orders-sftp-inbound | Tìm đúng Spring Integration endpoint |
| Source/target | sftp.partner.example / orders-db | Xác định ranh giới ngoài |
| Environment | production / region-a | Không thao tác nhầm môi trường |
| First failed operation | list remote files / connect / send / commit | Phân biệt tầng lỗi |
| Last known success | 2026-11-23T15:02:00+07:00 | Xác định cửa sổ ảnh hưởng |
| Current backlog | 340 files, oldest 8 min | Đánh giá recovery time |
| Data semantics | at-least-once + business idempotency | Quyết định replay và ack |
| Incident commander | vai trò trực được chỉ định | Quyết định và điều phối |
| Evidence links | dashboard, trace, log đã redact | Chẩn đoán và audit |

**Các tên và số liệu trên là giả định.** Khi vận hành, thay bằng thông tin thực tế, không suy ra chúng từ tên module hoặc nội dung bài học.

### 1.3. Định nghĩa “khôi phục thành công”

Một incident chỉ được kết luận phục hồi khi thỏa **cả ba tầng**:

1. **Kết nối:** transport/endpoint trao đổi được với bên ngoài; credentials và cấu hình TLS/host key hợp lệ.
2. **Tiến triển kỹ thuật:** message được nhận/gửi, retry có kiểm soát, không còn lỗi lặp bất thường; lag/backlog bắt đầu giảm.
3. **Tính đúng nghiệp vụ:** message đã validate, commit đúng; không mất, không xử lý trùng ngoài contract; có đối soát source–target và xử lý phần còn tồn đọng.

Lời cảnh báo **“connection recovered” không đồng nghĩa “incident resolved”**. Một connector có thể reconnect nhưng chỉ đọc dữ liệu mới, bỏ mất backlog hoặc ACK nhầm dữ liệu cũ.

## 2. Bản đồ phụ thuộc và các kiểu mất kết nối

Spring Integration sử dụng **MessageChannel** và các endpoint để tách giao thức bên ngoài khỏi business handler. Sự cố có thể xảy ra ở đầu vào, trong quá trình truyền channel, ở outbound adapter, tại kho dữ liệu, hoặc trong đường reply.

### 2.1. Bản đồ khái quát

~~~mermaid
flowchart LR
    EXTS["File/SFTP/HTTP/JMS/AMQP/Kafka/DB source"] --> IA["Inbound Adapter / Gateway"]
    IA --> CH["MessageChannel"]
    CH --> F["Filter / Transformer / Router / Service Activator"]
    F --> OA["Outbound Adapter / Gateway"]
    OA --> EXTT["External API/Broker/DB/File target"]
    IA --> ERR["Error handling / ErrorChannel"]
    F --> ERR
    OA --> ERR
    CH --> BUF["Queue / MessageStore nếu có"]
    BUF --> F
~~~

Một flow có thể gồm nhiều adapter nối tiếp. Vì vậy phải xác định **endpoint nào mất kết nối và message đang nằm ở đâu** trước khi tắt một flow hoặc replay.

### 2.2. Sáu loại sự cố cần phân biệt

| Nhóm lỗi | Tín hiệu thường gặp | Kiểm tra đầu tiên |
| --- | --- | --- |
| **DNS/routing/network** | Unknown host, connection refused, reset, unreachable | DNS, route, firewall, endpoint/port và mạng vùng |
| **Transport/TLS/SSH** | TLS handshake, certificate expired, SSH host-key mismatch | Cert/key validity, truststore, server identity |
| **Authentication/authorization** | HTTP 401/403, broker auth failure, DB login denied, SFTP permission denied | Credential rotation, role, ACL, token expiry |
| **Capacity/throttling** | 429, timeouts tăng, broker flow control, DB pool exhausted | Rate limit, thread/pool, queue depth, sink saturation |
| **Protocol/configuration** | Wrong topic/queue/path, unsupported cipher, schema mismatch | Cấu hình release, endpoint address, contract |
| **Semantic/business failure** | Validation fail, duplicate, stale version, poison message | Business event, schema, idempotency; chưa chắc mất kết nối |

**HTTP 404** hoặc một poll rỗng không tự chứng minh mất kết nối: 404 có thể là tài nguyên không tồn tại; poll file rỗng có thể vì đối tác chưa upload. Tương tự, **broker connected** không chứng minh consumer đang được gán partition hoặc handler đã commit.

### 2.3. Nơi lưu message quyết định khả năng khôi phục

| Nơi message ở thời điểm lỗi | Thường có khả năng phục hồi? | Rủi ro |
| --- | --- | --- |
| Source SFTP/File còn nguyên | Có thể đọc lại nếu source giữ nguyên và filter phù hợp | Xóa/rename/metadata đã đánh dấu sớm |
| JDBC bảng READY/outbox | Có nếu transaction/claim/lease thiết kế đúng | Trạng thái CLAIMED kẹt, stale lock, double claim |
| JMS/AMQP durable queue | Tùy queue/message persistence, ack/transaction | Ack sớm, DLQ policy, TTL hết hạn |
| Kafka topic | Tùy retention, offset, consumer group | Offset commit sớm, replay sai phạm vi, rebalance |
| QueueChannel in-memory | **Không mặc định bền vững** | JVM crash mất message đang chờ/đã dequeue |
| Object/MessageStore bền vững | Có thể redeem lại theo claim ID | Token hết hạn, GC xóa sớm, quyền truy cập |
| Remote HTTP service đã commit | Có thể phải tra trạng thái từ service | Caller timeout nên không biết đã tạo side effect chưa |

Khi không biết message ở đâu, **không replay hàng loạt**. Hãy ghi rõ uncertainty và điều tra từ nguồn có thẩm quyền.

## 3. Phân loại mức độ, SLO và trách nhiệm quyết định

### 3.1. Bảng mức độ tham khảo

| Mức | Dấu hiệu gợi ý | Phản ứng |
| --- | --- | --- |
| **SEV-1 / Critical** | Mất toàn bộ luồng quan trọng, nghi mất/trùng dữ liệu có giá trị cao, ảnh hưởng nhiều khách hàng, nghi rò rỉ dữ liệu | Kích hoạt incident commander, Security/Business Owner khi liên quan, bảo toàn chứng cứ, hạn chế thao tác nguy hiểm |
| **SEV-2 / High** | Một connector quan trọng ngừng nhiều lần, backlog tăng và SLO sắp vi phạm | Điều phối on-call + system owner, containment và recovery có ưu tiên |
| **SEV-3 / Medium** | Một nguồn/tenant bị ảnh hưởng cục bộ, vẫn có cơ chế buffer và dư thời gian | Triage, giám sát backlog, xử lý có kế hoạch |
| **SEV-4 / Low** | Lỗi thoáng qua đã tự phục hồi, không có tác động nghiệp vụ | Ghi dấu, phân tích xu hướng, cải thiện cảnh báo |

Đây là **khung gợi ý**, không thay chính sách severity/SLO chính thức của tổ chức. Nếu chưa có SLO, cần ghi rõ đang dùng ngưỡng tạm thời do owner phê duyệt.

### 3.2. SLI/SLO theo luồng dữ liệu

Những chỉ tiêu hữu ích hơn “service alive”:

- **Freshness:** độ trễ từ lúc nguồn có dữ liệu đến lúc business commit.
- **Success rate:** số work thành công theo business contract / tổng số work đến hạn.
- **Backlog age:** tuổi work lâu nhất chưa xử lý.
- **End-to-end correctness:** số item đối soát khớp, số thiếu/trùng/stale.
- **Availability of dependency:** tỉ lệ kết nối hợp lệ với target, nhưng phải đi kèm tiến triển.
- **Recovery time:** thời gian từ phát hiện đến khi đạt điều kiện phục hồi nghiệp vụ.

### 3.3. RTO, RPO và điểm không được đoán

**RTO (Recovery Time Objective)** là mục tiêu thời gian khôi phục dịch vụ. **RPO (Recovery Point Objective)** là mức mất dữ liệu chấp nhận được theo thiết kế và hợp đồng. Không nên tự tuyên bố RPO=0 chỉ vì broker có durable queue; ack sớm, retention, consumer lỗi và tác động ngoài transaction vẫn có thể gây mất dữ liệu.

| Quyết định | Ai nên phê duyệt khi rủi ro cao? |
| --- | --- |
| Giảm nhịp/tạm ngừng một connector | Incident commander/on-call theo quyền vận hành |
| Đổi credential, certificate, network ACL | Owner hạ tầng/Security theo quy trình |
| Tua Kafka offset, xóa queue/DLQ, reset metadata | Data/Business Owner + Integration Owner; đánh giá phạm vi |
| Replay work có side effect | Business Owner + người chịu trách nhiệm idempotency |
| Chấp nhận mất một phần dữ liệu hoặc trạng thái UNKNOWN | Người có thẩm quyền nghiệp vụ/compliance |
| Công bố sự cố cho đối tác/khách hàng | Communications/Incident Commander theo quy định |

**Nguyên tắc:** ưu tiên **hành động có thể đảo ngược và không phá chứng cứ** trước; ghi ai quyết định, vì sao, phạm vi, thời điểm và cách xác minh.

## 4. Phát hiện và cảnh báo: quan sát đúng tín hiệu

### 4.1. Không chỉ dựa vào stack trace

Một connector có thể tự động retry trong background và không báo lỗi ra caller. Một service có thể hết kết nối nhưng vẫn có thread đang chạy. Vì vậy cần giám sát **hành vi trao đổi dữ liệu** bên cạnh log exception.

| Nhóm | Tín hiệu đo | Cách hiểu |
| --- | --- | --- |
| Connection | connect success/failure, TLS/SSH handshake, reconnect count | Phát hiện lỗi mạng/xác thực |
| Request | sent, received, 2xx/4xx/5xx, timeout, latency P95/P99 | Phát hiện API/broker đích chậm |
| Polling | attempts, empty polls, last successful poll | Phân biệt không có dữ liệu và poller chết |
| Messaging | queue depth, unacked, retries, DLQ, Kafka lag | Phát hiện backlog/redelivery |
| Business | last committed event, success/failure, duplicate suppressed | Xác nhận tiến triển thực |
| Storage | DB pool, transaction latency, SFTP file age, disk capacity | Xác định nút thắt liên quan |
| Security | 401/403, cert expiry, token refresh failures | Phân biệt hết hạn credential và outage mạng |

### 4.2. Ba cảnh báo ưu tiên

1. **No business progress:** nguồn có work đến hạn nhưng thời điểm commit cuối quá xa.
2. **Backlog age SLO breach:** tuổi dữ liệu chờ xử lý tiến gần hoặc vượt SLO.
3. **Sustained dependency failure:** lỗi kết nối/timeout/5xx/authorization vượt ngưỡng và ảnh hưởng một flow đang có work.

Nếu một poller SFTP rỗng trong giờ không có file dự kiến, có thể không cần báo động. Cảnh báo nên gắn với **lịch/khối lượng dữ liệu được kỳ vọng**, chứ không chỉ “không thấy message”.

### 4.3. Mẫu dữ liệu dashboard

~~~text
Flow: partner-orders-sftp-inbound
Dependency: sftp.partner.example
Endpoint state: RUNNING
Last connection success: 15:02
Last business commit: 15:01
Connection failures / 5m: 24
Files waiting: 340
Oldest file age: 8m
Processing errors / 5m: 0
Retry attempts / 5m: 24
Unreconciled work: UNKNOWN
~~~

Tất cả số liệu là **mô phỏng**, không phản ánh hệ thống production thực tế. Lưu ý: endpoint báo RUNNING nhưng kết nối vẫn có thể lỗi; “0 processing errors” chưa chắc tốt nếu không có message nào đến được handler.

### 4.4. Ngưỡng cảnh báo: mẫu có điều kiện

Không áp một ngưỡng cố định cho mọi hệ. Ví dụ:

~~~text
WARN nếu oldestPendingAge > 0.7 × freshnessSLO
PAGE nếu oldestPendingAge > freshnessSLO
PAGE nếu expectedWork > 0 và successfulCommitCount = 0
     quá ngưỡng đã thống nhất
SECURITY ALERT nếu certificate/host-key mismatch không giải thích được
~~~

Đây là **chính sách đề xuất**, không phải cấu hình alerting mặc định của Spring Integration. Cần điều chỉnh để tránh false positive, làm rõ nguồn số liệu và vùng thời gian.

## 5. Quy trình phản ứng ban đầu: 0–15 phút đầu

Trong sự cố thật, việc đầu tiên không phải khởi động lại mọi instance. Cần xác định ranh giới và ngăn trạng thái xấu đi.

### 5.1. Giai đoạn 0–2 phút: xác nhận và bảo toàn dấu vết

- [ ] Mở incident record, ghi **thời điểm phát hiện**, người trực và flow ảnh hưởng.
- [ ] Xem dashboard **last success, error count, backlog age, pending/acks**.
- [ ] So sánh với lịch dữ liệu: nguồn đang thực sự có work hay không?
- [ ] Ghi phiên bản deploy/config gần nhất, thời điểm credential/cert rotation nếu biết.
- [ ] Bảo toàn trace/log/error message đã **redact secrets**; chưa xóa hàng đợi hoặc reset offset.
- [ ] Nếu nghi vấn TLS/SSH impersonation hoặc credential compromise: **dừng hành động làm lộ dữ liệu**, thông báo Security theo quy trình.

### 5.2. Giai đoạn 2–5 phút: định vị lỗi

- [ ] Xác định **chiều giao tiếp**: inbound receive, outbound send, request/reply hoặc storage lookup.
- [ ] Xác định **protocol**: File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC.
- [ ] Chọn **first failing hop** thay vì nhìn exception cuối từ một handler.
- [ ] Phân biệt lỗi DNS/network/TLS/authn/authz/rate limit/schema.
- [ ] Kiểm tra một endpoint hay nhiều đối tác/region cùng lỗi.
- [ ] Ước lượng **cửa sổ work ảnh hưởng** từ last success đến hiện tại; ghi unknown nếu chưa đủ bằng chứng.

### 5.3. Giai đoạn 5–10 phút: containment

- [ ] Nếu producer đẩy nhanh hơn consumer, áp **rate limit, bounded buffer hoặc tạm dừng intake** có kiểm soát.
- [ ] Nếu lỗi có side effect không xác định, **dừng retry tự động nguy hiểm** hoặc chuyển sang state cần đối soát khi policy cho phép.
- [ ] Nếu queue/broker còn lưu work, bảo toàn retention và tránh ack/drop sai.
- [ ] Nếu SFTP/File có file chưa hoàn tất, tránh đổi tên/xóa trong lúc chưa xác minh.
- [ ] Nếu mất kết nối vì credential, không brute-force retry với secret sai.
- [ ] Đánh dấu rõ các work **IN_FLIGHT, PENDING, UNKNOWN, RETRYABLE, QUARANTINED** theo nguồn dữ liệu đáng tin.

### 5.4. Giai đoạn 10–15 phút: phục hồi có điều kiện

- [ ] Điều tra/trả lời nguyên nhân đầu tiên đủ chắc để hành động: mạng, cert, token, quota, broker, DB pool, code/config.
- [ ] Chọn một **thay đổi nhỏ, đảo ngược được**: reconnect theo chính sách, rollback cấu hình, giảm concurrency hoặc chuyển sang endpoint dự phòng được phê duyệt.
- [ ] Đặt **điều kiện dừng** nếu sau thay đổi lỗi/duplicate tăng.
- [ ] Ghi người phê duyệt, timestamp, cấu hình trước/sau và phép thử xác minh.
- [ ] Xác nhận **một message mới** đi hết đường trước khi mở lại toàn bộ backlog.
- [ ] Phát cập nhật incident với tình trạng và phạm vi chưa chắc chắn.

### 5.5. Timeline tác nghiệp

~~~mermaid
flowchart LR
    DET["Detect + timestamp"] --> SCOPE["Scope impact"]
    SCOPE --> SAFE["Contain / preserve work"]
    SAFE --> DIAG["Diagnose first failing hop"]
    DIAG --> FIX["Small reversible recovery"]
    FIX --> TEST["End-to-end canary"]
    TEST --> BACKLOG["Controlled backlog drain"]
    BACKLOG --> RECON["Reconcile + verify"]
    RECON --> CLOSE["Close incident / postmortem"]
~~~

Không nhất thiết hoàn thành các bước ở mốc phút chính xác: thời gian phụ thuộc severity và quyền truy cập. Điểm cố định là **không bỏ containment và data-safety check để đổi lấy tốc độ reconnect**.

## 6. Cây quyết định xử lý sự cố kết nối

### 6.1. Chẩn đoán theo lớp lỗi

~~~mermaid
flowchart TD
    A["Không có tiến triển hoặc nhiều lỗi"] --> B{"Nguồn thực sự có work?"}
    B -->|Không/Chưa rõ| CHECK["Kiểm tra lịch và hệ nguồn; không báo mất dữ liệu vội"]
    B -->|Có| C{"Có thiết lập kết nối được?"}
    C -->|Không| NET["DNS/route/port/firewall, TLS/SSH, credentials"]
    C -->|Có| D{"Endpoint được quyền thao tác?"}
    D -->|Không| AUTH["401/403/ACL/topic/DB/SFTP permission"]
    D -->|Có| E{"Có bị giới hạn tải?"}
    E -->|Có| THROTTLE["429, pool exhausted, broker flow control"]
    E -->|Không| F{"Message có tới handler?"}
    F -->|Không| ROUTE["Channel/endpoint state, filter, poller, subscription"]
    F -->|Có| G{"Business commit thành công?"}
    G -->|Không| BIZ["Schema, DB, handler, transaction, retry/DLQ"]
    G -->|Có| H{"Ack/offset và readback đúng?"}
    H -->|Không| REC["Reconcile duplicate / unknown / late reply"]
    H -->|Có| OK["Canary + backlog drain + xác nhận SLA"]
~~~

### 6.2. Câu hỏi bắt buộc trước khi retry

1. Message **chưa được gửi**, **đã gửi nhưng chưa ack**, hay **đã commit nghiệp vụ nhưng thiếu reply**?
2. Side effect có thể thực hiện lại an toàn không? Có business idempotency key bền vững?
3. Retention/TTL của nguồn có đủ cho retry và backlog hay không?
4. Có nhiều worker/replica cùng xử lý không? Lock/lease/consumer group/partition ownership đã rõ chưa?
5. Có nhóm subscriber khác còn cần message không?
6. Nếu thay connection pool/endpoint URL, có làm mất ordering, session hoặc replay state không?
7. Nếu dừng connector, dữ liệu mới sẽ nằm ở đâu và **ai chịu trách nhiệm giữ**?

**Nguyên tắc vàng:** khi tác động nghiệp vụ ở trạng thái **UNKNOWN**, đừng retry lệnh không idempotent trước khi tra cứu trạng thái thật hoặc nhận phê duyệt xử lý tương ứng.

### 6.3. Nguyên tắc thao tác an toàn

| Hành động | Mức thận trọng | Lý do |
| --- | --- | --- |
| Đọc dashboard/log đã che secret | Thường an toàn | Không đổi trạng thái |
| Kiểm tra DNS/route/health bằng thao tác không side effect | Thường an toàn | Cần xác minh quyền và tải |
| Giảm concurrency/rate và tạm dừng nhận việc mới | Có thể đảo ngược | Cần xem buffer/retention trong lúc dừng |
| Restart một listener/connector | Cần kế hoạch | Có thể gây redelivery, rebalance, mất in-memory state |
| Đổi credentials/truststore/host key | Có kiểm soát an ninh | Có thể che sự cố giả mạo hoặc làm hỏng kết nối khác |
| Replay DLQ hoặc outbox | Rủi ro side effect | Cần idempotency và phạm vi chính xác |
| Tua Kafka offset, xóa queue, xóa file, reset processed metadata | Rủi ro cao | Có thể mất hoặc nhân đôi dữ liệu |
| Bỏ qua TLS verification hoặc SSH host-key check | **Không thực hiện** | Nguy cơ lộ/giả mạo hệ thống |

### 6.4. Ghi nhật ký hành động

Mỗi thay đổi vận hành phải có **before state, hypothesis, change, verifier, rollback và evidence**.

~~~yaml
incidentId: INC-LAB-2026-011
operation: "reduce-consumer-concurrency"
target: "orders-inbound-flow"
hypothesis: "DB pool saturation causes read timeout"
before: "4 workers, high DB wait"
change: "reduce to 2 workers via approved deployment configuration"
expected: "DB wait and retries decrease; committed throughput stabilizes"
rollback: "restore approved previous concurrency"
approvedBy: "incident-commander"
result: "PENDING"
evidence: "redacted-dashboard-link-placeholder"
~~~

Mẫu này là ví dụ tài liệu, **không phải kết quả đã chạy**; các giá trị cần được thay bằng bằng chứng thực khi vận hành.

## 7. Runbook HTTP: inbound gateway và outbound gateway mất kết nối

HTTP có nhiều kiểu thất bại: **không kết nối được**, **TLS handshake lỗi**, **server trả 4xx/5xx**, **đường mạng timeout sau khi server đã nhận request**, và **gateway của caller timeout trước khi handler hoàn thành**. Cần biết flow đang nhận request hay gọi dịch vụ bên ngoài.

### 7.1. Định vị đúng phía

| Spring Integration endpoint | Trách nhiệm | Điểm lỗi thường gặp |
| --- | --- | --- |
| **HTTP inbound gateway** | Nhận request ngoài và trả response từ integration flow | Reverse proxy, request size, auth, thread pool, reply timeout |
| **HTTP outbound gateway** | Gọi HTTP API bên ngoài và đưa response vào flow | DNS, TLS, connection/read timeout, 429/5xx |
| **HTTP outbound adapter** | Gửi một chiều, không có hợp đồng reply message như gateway | Unknown side effect khi network timeout |
| **Scheduled HTTP poll** | Poller kích hoạt call HTTP theo lịch | Request rate, cursor/watermark, empty poll khác outage |

### 7.2. Dấu hiệu và kiểm tra an toàn

- [ ] Xác định đúng URL hostname, port, path, method và environment, **không sao chép credential vào log**.
- [ ] Phân biệt **connect timeout** với **read/response timeout**; cả hai không có ý nghĩa nghiệp vụ giống nhau.
- [ ] Kiểm tra TLS certificate validity, truststore, SNI, proxy, DNS và network path.
- [ ] Với **401/403**, kiểm tra identity, scope/audience, key rotation và policy; không tự cấp quyền cao hơn.
- [ ] Với **429**, đọc Retry-After và rate limit được phép; không tăng số request thử.
- [ ] Với **502/503/504**, kiểm tra upstream/downstream health, circuit breaker, proxy timeout và server overload.
- [ ] Kiểm tra message ở **requestChannel** đã gửi tới HTTP gateway chưa, và reply/error channel được định tuyến thế nào.
- [ ] Thu thập requestId, correlationId và **status của side effect** từ API đích nếu có khả năng ghi.

### 7.3. Kế hoạch xử lý theo mã lỗi

| Tình huống | Containment | Recovery | Xác minh |
| --- | --- | --- | --- |
| DNS không phân giải được | Giảm retry, kiểm tra phạm vi DNS | Khôi phục DNS/config đúng, không dùng IP tạm thiếu xác minh TLS | Lookup từ cùng mạng runtime, gọi canary |
| TLS certificate expired/mismatch | Không tắt certificate validation | Gia hạn/sửa chain/truststore theo quy trình | TLS handshake xác minh đúng host |
| Token hết hạn (401) | Tạm dừng lặp lỗi xác thực | Refresh/rotate credential qua secret manager | Request có quyền tối thiểu thành công |
| 403 Forbidden | Điều tra principal/scope/resource | Sửa quyền được phê duyệt, không dùng admin token | Canaries được phép/không được phép đúng |
| 429 Too Many Requests | Rate limit/bulkhead | Tôn trọng Retry-After, giảm concurrency | 429 giảm, latency/throughput ổn |
| 5xx/timeout | Circuit breaker/backoff | Phối hợp owner đích, failover nếu được hỗ trợ | End-to-end commit/readback và backlog giảm |
| Reply timeout ở inbound gateway | Cô lập request dài | Kiểm tra handler và outbound dependency; cân nhắc 202/jobId nếu hợp đồng cho phép | Response/error mapping và job state đúng |

### 7.4. Lỗi “server đã commit nhưng caller timeout”

~~~mermaid
sequenceDiagram
    participant F as Spring Integration Flow
    participant G as HTTP Outbound Gateway
    participant S as Remote Service
    participant DB as Remote DB
    F->>G: CreateOrder(requestId=R100)
    G->>S: POST /orders R100
    S->>DB: Commit order R100
    DB-->>S: OK
    Note over G,S: Response bị mất hoặc quá deadline
    G-->>F: Timeout / UNKNOWN
    F->>S: GET status by R100 (nếu hợp đồng hỗ trợ)
    S-->>F: Order R100 exists
    Note over F,S: Không gửi command tạo mới lần hai
~~~

Nếu API đích không có **idempotency key** hoặc **status lookup**, incident owner phải phân loại công việc UNKNOWN và thống nhất quy trình xác minh thủ công, không tự khẳng định retry là an toàn.

### 7.5. Cách đưa flow trở lại

1. Kiểm tra một request **read-only hoặc canary** đúng mục tiêu và được phép, không gây side effect không kiểm soát.
2. Xác minh retry/timeout policy đã không bị vô hiệu hoặc đặt quá thấp gây thác lỗi.
3. Mở lại từng phần traffic (theo tenant/partition/endpoint khi có thể).
4. Theo dõi P95/P99, 429/5xx, in-flight, circuit breaker và downstream commit success.
5. Với backlog command ghi, kiểm tra requestId/idempotencyKey trước retry.
6. Đối soát số request accepted, committed, timed out và UNKNOWN.

### 7.6. Cảnh báo phân loại

- HTTP **200** chưa chắc payload hợp schema hay business đã thành công.
- HTTP **202** chỉ là accepted theo API contract, không phải completed.
- HTTP **409** có thể là xung đột phiên bản hoặc duplicate key hợp lệ; không retry vô hạn.
- HTTP **4xx** thường cần sửa request/quyền, không phải cứ retry giống lỗi mạng.
- Một request bị caller cancel có thể vẫn đang thực thi ở server.

## 8. Runbook File/SFTP: remote file source không sẵn sàng

File/SFTP inbound thường dùng **SourcePollingChannelAdapter** poll **MessageSource**; không nên nhầm với một **PollingConsumer** đọc **QueueChannel**. Khi poller báo RUNNING nhưng không có file mới, phải kiểm tra source, filter và contract “file đã hoàn tất”.

### 8.1. Bản đồ luồng mẫu

~~~mermaid
flowchart LR
    PARTNER["Partner SFTP / Local directory"] --> SOURCE["File/SFTP MessageSource"]
    POLLER["Scheduler + Poller"] --> SOURCE
    SOURCE --> CH["MessageChannel"]
    CH --> PARSE["Validate / Parse"]
    PARSE --> DB["Business DB / Outbound Adapter"]
    SOURCE --> META["Accept-once metadata / filter"]
    PARSE --> ARCH["Archive / Quarantine theo policy"]
~~~

### 8.2. Dấu hiệu điển hình

| Dấu hiệu | Giả thuyết | Dấu vết cần thu |
| --- | --- | --- |
| SFTP connect timeout | Network, DNS, server down, connection pool | Endpoint URL, reachability, timeout class |
| SSH host-key mismatch | Server đổi key hoặc MITM | Fingerprint được phê duyệt, server owner |
| Authentication failed | Key/password rotate, account locked | Principal, key version, auth log |
| Directory listing denied | ACL/path/permission sai | Remote path, quyền list/read |
| Poller không chọn file mới | Filter pattern, last-modified, accept-once metadata | Filter reason, remote listing, timestamp |
| File parse lỗi ngẫu nhiên | Producer đang upload dở | Temp extension, marker/rename, size over time |
| File bị đọc lại sau restart | Metadata store không bền/dùng chung | File ID/path, persisted filter state |
| Nhiều replicas lấy cùng file | Không có shared claim/lock | Instance IDs, claim records |

### 8.3. Triage từ xa

- [ ] Xác minh DNS và SSH endpoint theo thông số cấu hình đã được phê duyệt.
- [ ] Kiểm tra host fingerprint qua kênh độc lập với owner, **không auto-accept host key mới**.
- [ ] Kiểm tra key/credential đúng role, hạn dùng và quyền remote folder.
- [ ] Phân biệt lệnh **list** thành công, **download** thành công và **parse/business commit** thành công.
- [ ] Kiểm tra thư mục remote có file thật, filename pattern và file-ready marker.
- [ ] Kiểm tra thời điểm modified/size/rename, UTC/timezone và đồng hồ server nếu dùng age filter.
- [ ] Kiểm tra local staging disk/quota, file handle, stream và session pool.
- [ ] Xác định remote filter và local filter có lưu metadata bền vững hay chỉ memory.

### 8.4. Phục hồi an toàn theo nguyên nhân

1. **Server mất kết nối:** giữ nguồn file nếu producer còn giữ, backoff poller, phối hợp đối tác, không xóa metadata đã thấy.
2. **SSH host-key đổi:** xác minh sự thay đổi với owner bằng kênh tin cậy rồi cập nhật trust theo quy trình; tuyệt đối không tắt kiểm tra.
3. **SFTP key hết hạn:** rotate secret và thử danh tính có quyền tối thiểu; tránh lưu key vào log/ticket.
4. **Không có file vì sai pattern/filter:** kiểm tra read-only listing và metadata, không reset toàn bộ bộ lọc trước khi xác định file đã xử lý.
5. **File đang upload dở:** yêu cầu producer dùng temp name/atomic rename hoặc marker file; không parse file chưa hoàn tất.
6. **Staging disk full:** dừng download/giới hạn intake, giải phóng dung lượng theo retention và owner, không xóa file chưa commit.
7. **Stale SFTP session:** reconnect/session validation theo adapter; xác minh khả năng tiếp tục/đọc lại transfer.

### 8.5. Đặc biệt với streaming adapter

Một SFTP inbound streaming adapter có thể cung cấp **InputStream** hoặc tài nguyên stream phụ thuộc remote session. Stream đã đóng không thể đọc lại, và object stream **không portable sang JVM khác**. Nếu handler lỗi giữa chừng:

- Biết file nguồn còn không, offset/transfer có thể bắt đầu lại không.
- Đóng stream/session trong mọi đường lỗi.
- Nếu phải retry bền vững, lưu file/object hoàn chỉnh vào staging/shared store trước khi công nhận nhận thành công.
- Không giữ InputStream trong durable MessageStore rồi mong deserialize sau restart.

### 8.6. Tránh thao tác gây mất dữ liệu

**Không** tự động xóa remote file, chuyển file vào archive hoặc reset accept-once filter chỉ vì kết nối đã thông. Quy trình đúng là:

~~~text
Confirm source file complete
  → Confirm file identity/checksum/business key
  → Confirm processed/unknown state
  → Process or idempotent replay
  → Business DB readback
  → Archive/delete only when completion contract permits
~~~

Nếu đối tác xóa file sau một thời gian cố định, thông báo nguy cơ **source retention expiry** trong incident timeline và phối hợp giữ file trước khi hết hạn.

### 8.7. Kiểm chứng phục hồi

- [ ] Kết nối SFTP hợp lệ với host key được xác minh.
- [ ] Có thể list và đọc một file thử được phép.
- [ ] File hoàn tất đúng pattern được chọn; file tạm không được chọn.
- [ ] File đã xử lý không tạo side effect trùng sau reconnect/restart.
- [ ] Backlog file và tuổi file giảm; parser/business handler commit thành công.
- [ ] Staging, metadata và archive phản ánh đúng trạng thái đã đối soát.

## 9. Runbook JMS: listener không nhận message hoặc broker mất kết nối

JMS message-driven inbound adapter của Spring Integration thường dựa trên **message listener container**. Một queue có thể có nhiều competing consumers; topic có subscription semantics khác. **JMS session acknowledgment và transaction policy** quyết định message có bị giao lại khi listener dừng.

### 9.1. Điều kiện phát hiện

- Listener không kết nối được broker hoặc liên tục reconnect.
- Queue depth tăng, consumer count giảm, received=0 trong khi producer publish.
- Lỗi authentication, destination missing hoặc provider-specific exception.
- Unacked/in-flight tăng, business commits không tăng.
- DLQ tăng nhanh sau một lần đổi schema/code.
- Outbound JMS gateway gửi request nhưng không nhận reply đúng correlation.

### 9.2. Bảng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Broker refused connection | Network, broker down, sai endpoint | Broker health/port, DNS, route |
| JMS authentication failed | Credential/ACL rotate | Principal và quyền consume/publish |
| Destination not found | Sai tên queue/topic, provisioning | Topology, environment, deploy diff |
| Consumer count=0 | Listener/container dừng | Endpoint lifecycle, startup logs |
| Queue depth tăng, consumers vẫn chạy | Handler chậm, DB lỗi, poison message | Business latency, retry, DLQ |
| Message liên tục redeliver | Rollback/recover, thiếu commit, handler lỗi | Exception, attempt, transaction config |
| Reply timeout | Responder down, reply destination/correlation lỗi | Request ID, JMSReplyTo, reply consumer |

### 9.3. Các bước điều tra

1. Xác định destination: **JMS Queue hay Topic**, có durable/shared subscription hay không.
2. Xem trạng thái **ConnectionFactory, session, listener container** và consumer count theo broker.
3. Kiểm tra authentication/authorization, certificate nếu transport dùng TLS.
4. Đối chiếu **messages enqueued/dequeued/unacked**, DLQ và last business commit.
5. Xác định **ack mode hoặc transaction manager** thực tế, không suy từ Spring Integration handler.
6. Kiểm tra **một flow hay mọi flow** dùng cùng broker bị ảnh hưởng.
7. Nếu endpoint bị stop, xác nhận ai chủ động dừng, autoStartup và sự kiện deploy gần nhất.

### 9.4. Containment

- Nếu broker down, giữ message ở producer/outbox khi có thể; không gửi retry dồn dập.
- Nếu handler lỗi gây redelivery loop, giảm retry, chuyển poison message theo DLQ policy, bảo toàn evidence.
- Nếu DB sink quá tải, giảm listener concurrency phù hợp thay vì tăng số consumer.
- Nếu cần pause consumer, xác minh queue retention và expiry của message.
- Không tạo queue mới trùng tên/đổi topic tùy tiện làm tách dòng work.

### 9.5. Khôi phục

1. Khôi phục broker/connectivity/credential theo owner, giữ TLS và ACL đúng chính sách.
2. Khi listener reconnect, kiểm tra **destination và consumer subscription** chính xác.
3. Chạy canary message có business key duy nhất được phép, xác minh end-to-end.
4. Mở concurrency từng mức khi downstream còn capacity.
5. Quan sát redelivery/DLQ, bởi in-flight messages trước outage có thể được giao lại.
6. Đối soát accepted vs committed vs acked, không kết luận chỉ từ broker dequeue.

### 9.6. JMS transaction và redelivery

~~~mermaid
sequenceDiagram
    participant B as JMS Broker
    participant L as Listener
    participant DB as Business DB
    B->>L: Deliver Work W1
    L->>DB: Commit W1
    DB-->>L: OK
    Note over L: Process crash trước JMS ack/commit
    B->>L: Redeliver W1 after recovery
    L->>DB: Check idempotency for W1
    DB-->>L: Already committed
    L-->>B: Acknowledge according to policy
~~~

**Cảnh báo:** JDBC transaction và JMS session transaction **không tự là một giao dịch atomic** chỉ vì cùng một method Java gọi cả hai. Nếu cần phối hợp mạnh, phải cấu hình transaction manager thực tế, hoặc dùng inbox/outbox/idempotency/reconciliation.

### 9.7. Không nhầm service activator async với broker ACK

Nếu listener chuyển message tới ExecutorChannel rồi trả về **trước business commit**, listener container có thể coi thao tác dispatch thành công theo cấu hình và xác nhận message quá sớm. Khi đó JVM chết sẽ mất work đã không còn ở broker. Cần:

- Giữ các bước quan trọng đồng bộ trong phạm vi ack/transaction, **hoặc**
- Durable handoff vào kho/queue khác rồi mới ack, **hoặc**
- Một cơ chế ack thủ công được framework và broker hỗ trợ, có kiểm thử failure path.

### 9.8. Tiêu chí kết thúc riêng cho JMS

- [ ] Broker connection và listener consumer count ổn định.
- [ ] Queue depth/unacked giảm về mức cho phép; expiry không đe dọa backlog.
- [ ] Business commits tăng và idempotency hoạt động sau redelivery.
- [ ] DLQ tăng không bất thường, các item cũ có owner xử lý.
- [ ] Với request/reply, correlation và reply destination vẫn đúng.

## 10. Runbook AMQP/RabbitMQ: connection, channel, consumer và flow control

RabbitMQ có **exchange → queue → consumer**, khác Kafka partitioned log và không hoàn toàn giống JMS. Khi broker hoặc connection gián đoạn, có thể tồn tại message **unacked**, publisher confirm chưa nhận và delivery lại.

### 10.1. Cấu trúc liên quan

~~~text
Producer
   → AMQP outbound adapter/publisher
   → Exchange + routing key
   → Queue (durable/quorum/classic theo lựa chọn)
   → Spring AMQP listener container
   → Spring Integration AMQP inbound adapter
   → MessageChannel → business handler
~~~

**Publisher confirms**, **consumer acknowledgments** và **business commit** là ba điểm khác nhau. Confirm producer nói về một mốc nhận của broker theo cấu hình, không khẳng định consumer đã xử lý.

### 10.2. Phát hiện và thu thập evidence

| Dấu hiệu | Gợi ý kiểm tra | Thận trọng |
| --- | --- | --- |
| Connection refused/reset | Broker node, network, TLS | Không tắt TLS |
| Channel closed | Protocol exception, resource limit, auth | Kiểm tra exception cụ thể, topology |
| Queue messages ready tăng | Consumer thiếu/chậm | Đo business commit, unacked |
| Messages unacked cao | Prefetch cao, handler giữ message | Không restart tùy tiện khi chưa hiểu in-flight |
| Publisher confirm timeout | Broker chậm hoặc mất kết nối | Message có thể đã đến broker |
| Unroutable publish | Exchange/binding/routing key sai | Không coi send OK là queue nhận |
| DLQ tăng | Poison message, retry/reject policy | Cần phân loại lỗi trước replay |
| Flow control/memory/disk alarm | Broker pressure | Giảm publish rate, phối hợp broker admin |

### 10.3. Triage và containment

1. Xác định **vhost, exchange, queue, binding, routing key** đúng môi trường.
2. Kiểm tra queue tồn tại và loại queue/policy (durable, TTL, dead lettering).
3. Ghi **ready, unacked, consumers, publish/deliver/ack rate** trước thay đổi.
4. Nếu **broker memory/disk alarm**, giảm publisher rate và phối hợp capacity team; đừng tiếp tục publish dồn dập.
5. Nếu consumer bị stop, kiểm tra connection, channel, listener container và auth.
6. Nếu unacked giữ cao, xem prefetch và thời gian handler; không mặc nhiên đây là work đã hoàn tất.
7. Nếu publisher confirm mất, ghi trạng thái **UNKNOWN** và retry với stable business event ID.

### 10.4. Khôi phục theo bước

- Khôi phục broker topology/network/credentials theo change process.
- Xác minh queue binding **và routing** bằng canary message hợp lệ; chỉ kết nối thành công là chưa đủ.
- Mở lại publisher/consumer từ mức thấp, quan sát ready/unacked/ack rate.
- Với message redelivery, xác minh idempotency ở DB và retry budget.
- Theo dõi DLQ, especially message được đưa vào đó do TTL/reject/overflow policy.
- Tránh dùng bulk purge queue hoặc xóa DLQ để giảm dashboard backlog.

### 10.5. Prefetch và recovery

Prefetch lớn có thể khiến một consumer giữ nhiều delivery unacked. Khi nó mất kết nối, broker có thể đưa lại các message đó theo semantics, làm tăng đột ngột work mới cho consumer khác. Giảm prefetch trong incident **có thể** làm phân phối công bằng hơn, nhưng phải đánh giá throughput, latency và round-trip. Một thay đổi prefetch cũng không sửa được DB sink lỗi.

### 10.6. Retry/requeue loop

Nếu handler luôn ném lỗi schema và broker ngay lập tức requeue:

~~~text
Receive → fail schema → nack/requeue → receive → fail ...
~~~

Flow có thể **tiêu thụ CPU và kết nối nhưng không tiến triển**. Áp dụng retry policy hữu hạn, DLQ/quarantine, owner và controlled replay. Với dữ liệu cần ordering, chuyển poison message ra DLQ phải được business owner chấp thuận vì có thể tạo gap.

### 10.7. Không dùng broker như bằng chứng nghiệp vụ

Message **acked** chưa chắc hệ khác đã commit nếu listener ack trước async work. Ngược lại, business DB đã commit nhưng ack mất có thể dẫn tới redelivery. Hãy đối soát theo business key, không dựa chỉ vào counter của RabbitMQ.

### 10.8. Tiêu chí kết thúc riêng cho AMQP

- [ ] Publisher confirms/routing và consumers hoạt động bình thường.
- [ ] Ready/unacked/connection errors ổn định; backlog age giảm.
- [ ] Retry/requeue loop đã được loại bỏ hoặc cô lập.
- [ ] DLQ có owner và TTL đủ cho điều tra.
- [ ] Business DB readback không có side effect trùng.

## 11. Runbook Kafka: broker unreachable, rebalance, lag và offset

Kafka consumer client dùng poll loop nội bộ; Spring Integration **message-driven Kafka inbound adapter** thường dùng listener container để nhận record. Một nhóm consumer chia **topic partitions**; lag và assignment có thể bất thường dù network đã phục hồi.

### 11.1. Các triệu chứng quan trọng

| Dấu hiệu | Giả thuyết | Xem ở đâu |
| --- | --- | --- |
| Broker connection failures | DNS, TLS, SASL, bootstrap/listener addresses | Client logs, broker availability |
| Consumer group không có active members | Listener down, credentials sai | Group membership, app lifecycle |
| Rebalance liên tục | Instance churn, poll interval, long processing | Assignment/rebalance metrics |
| Lag tăng một partition | Hot key, poison record, handler chậm | Lag per partition, commit/processing |
| Offset không tiến triển | Handler lỗi, ack mode, commit failure | Consumer logs, business readback |
| Một consumer idle dù group nhiều replicas | Consumer nhiều hơn partitions | Partition count/assignment |
| DLT tăng | Deserialization/schema/processing errors | Error handler, DLT status |
| Đọc lại record sau restart | Offset chưa commit hoặc reset | Committed offsets, group state |

### 11.2. First checks

- [ ] Xác định đúng **bootstrap servers, cluster, topic, group.id, partition count** và vùng.
- [ ] Xác minh TLS/SASL credentials, ACL topic/group theo quyền tối thiểu.
- [ ] Kiểm tra assignment và lag **theo partition**, không chỉ tổng lag.
- [ ] Kiểm tra listener container, error handler, retry topic/DLT và backoff.
- [ ] Xác định offset nào **đã commit**, offset nào **đã business commit**.
- [ ] Nếu mới deploy, xem deserializer/schema version và partition key thay đổi không.
- [ ] Kiểm tra việc xử lý lâu có vượt cấu hình poll interval/timeout liên quan, gây rebalance không.

### 11.3. Những hành động nên tránh

**Không** tự reset offset về earliest/latest, đổi group.id, tăng partition, xóa topic hoặc bỏ qua một offset lỗi chỉ để “lag về 0”. Những thao tác này có thể **xử lý trùng cả lịch sử hoặc bỏ qua message chưa xử lý**. Cần xác định record range, business key, retention, idempotency và phê duyệt.

### 11.4. Khôi phục connection

1. Sửa đúng DNS/broker listener/TLS/SASL/ACL theo owner.
2. Xác minh listener container join group và **nhận partition assignment**.
3. Kiểm tra canary record và consumer business commit.
4. Theo dõi rebalance count, poll/processing duration, commit errors và lag.
5. Mở concurrency theo **số partition có thể phân công**, không tăng replicas vô hạn.
6. Xử lý stuck partition/poison record bằng error handling và DLT theo chính sách.
7. Đối soát business state so với offsets đã đọc/commit.

### 11.5. Rebalance và duplicate

~~~mermaid
sequenceDiagram
    participant K as Kafka Topic
    participant A as Consumer A
    participant DB as Business DB
    participant B as Consumer B
    K->>A: Record R offset 91
    A->>DB: Commit R
    DB-->>A: Success
    Note over A: Rebalance/crash before offset commit
    K->>B: Reassign partition; read R again
    B->>DB: Idempotent check R
    DB-->>B: Already applied
    B-->>K: Commit progress per container policy
~~~

Kafka có thể có semantics xử lý mạnh trong phạm vi transaction/configuration riêng, nhưng **không tự bảo đảm exactly-once cho HTTP/SFTP/DB bên ngoài**. Với external side effect, vẫn cần business idempotency và reconciliation.

### 11.6. Phân biệt throughput với lag

Một partition nóng có thể khiến tổng lag tăng dù các partition còn lại gần 0. Tăng số worker vượt partition count không sửa được vấn đề; cần phân tích key distribution hoặc bottleneck business. Nếu handler chậm vì DB, tăng concurrency có thể làm lag nặng hơn do lock contention.

### 11.7. Recovery nếu offset và business state lệch

| Trạng thái | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Business commit OK, offset chưa commit | Redelivery/duplicate | Idempotency, commit lại sau xác minh |
| Offset đã commit, business chưa commit | Data loss nếu không có nguồn tái phát | Escalate, đối soát, replay chỉ theo business key/range được duyệt |
| Source topic đã hết retention | Không còn record để replay | Khôi phục từ outbox/snapshot/backup hợp lệ hoặc ghi nhận gap |
| DLT có record lỗi | Cần phân loại permanent/transient | Sửa schema/code, replay có kiểm soát |
| Group ID vô tình đổi | Đọc lại/bỏ qua tùy offset reset policy | Khôi phục config, phân tích phạm vi ảnh hưởng |

### 11.8. Tiêu chí kết thúc riêng cho Kafka

- [ ] Group membership và assignment ổn định.
- [ ] Không có rebalance loop bất thường; lag từng partition giảm hợp lý.
- [ ] Record thử đi hết business handler và DB commit.
- [ ] DLT/retry topics có owner và không tạo vòng lặp.
- [ ] Offset và business state được đối soát trên cửa sổ incident.

## 12. Runbook JDBC/database: mất kết nối hoặc hết connection pool

Database có thể là **nguồn** của JDBC polling, **đích** của service activator/outbound gateway, hoặc **MessageStore/outbox/inbox** phục vụ reliability. Khi database không sẵn sàng, cả receive và business commit có thể dừng, nhưng hậu quả khác nhau theo vị trí.

### 12.1. Triệu chứng

| Tín hiệu | Giả thuyết | Phân biệt |
| --- | --- | --- |
| Connection refused | DB node/service/route không sẵn | Network/database health |
| Login/auth failed | Credential rotate/role revoke | Principal, secret version, role |
| Connection acquisition timeout | Pool cạn, leak, DB quá tải | Active/idle/pending pool, DB session |
| Query timeout | SQL chậm, lock, downstream | Query plan/locks/timeouts |
| Deadlock/serialization failure | Transaction contention | Retry phù hợp và ordering |
| Claim rows stuck IN_PROGRESS | Worker chết, lease chưa hết | Lease, owner, attempt |
| Outbox pending tăng | Relay/broker hoặc database lỗi | Last publish, outbox lag |
| MessageStore retrieve lỗi | DB claim store offline/schema mismatch | Store health, serialization |

### 12.2. Mối nguy lớn nhất khi restart

Nếu ứng dụng:

1. Lấy một hàng trạng thái READY;
2. Đổi thành PROCESSING và commit;
3. Gặp DB timeout hoặc process chết;
4. Không có lease expiry/reclaim;

thì task có thể **kẹt vĩnh viễn**. Ngược lại, nếu retry claim mà không có update có điều kiện, hai workers có thể xử lý cùng task.

### 12.3. Triage

- [ ] Xác định database là **source, business sink, message store, claim registry hay outbox**.
- [ ] Kiểm tra connection pool active/idle/wait/timeout và giới hạn DB server.
- [ ] Xác định exception loại mạng, login, deadlock, query timeout hoặc schema mismatch.
- [ ] Kiểm tra active transactions và long-held locks trong phạm vi được phép.
- [ ] Xem deployment/migration/credential rotation gần incident.
- [ ] Với JDBC polling, kiểm tra query READY và transaction/claim/lease.
- [ ] Với outbox, kiểm tra pending count, oldest pending age và relay status.
- [ ] Với MessageStore, xác minh schema/serializer compatibility sau deployment.

### 12.4. Phục hồi

1. Phối hợp DB owner khôi phục service/connectivity/credentials; không mở quyền rộng để “thử”.
2. Nếu pool cạn do leak/slow queries, **giảm concurrency** và cô lập tác vụ gây lock thay vì chỉ tăng pool size.
3. Đảm bảo transactions đang dở được DB rollback/resolve theo trạng thái thật.
4. Với JDBC polling, reclaim **lease hết hạn hợp lệ**; không reset mọi row IN_PROGRESS thành READY tùy tiện.
5. Với outbox, relay tiếp tục publish **cùng event ID**; consumer phải chịu duplicate.
6. Kiểm tra một transaction canary và readback nghiệp vụ.
7. Mở lại tốc độ từng mức, theo dõi pool saturation/lock wait/commit latency.

### 12.5. Bảng trạng thái claim task mẫu

~~~text
READY
  → CLAIMED(owner, leaseUntil, version)
  → PROCESSING
  → COMPLETED
  hoặc → RETRYABLE / FAILED

Nếu lease hết hạn:
  xác minh không có worker hợp lệ còn quyền commit
  → reclaim với điều kiện trên version/lease
~~~

Với worker cũ vẫn chạy sau khi hết lease, **fencing/version check tại điểm commit** giúp ngăn stale worker ghi kết quả sau khi worker mới nhận task.

### 12.6. Tiêu chí kết thúc riêng cho JDBC

- [ ] Connection pool và DB service ổn định, không có lỗi login/timeout liên tục.
- [ ] Truy vấn/transaction chính hoạt động, business readback khớp.
- [ ] Claim rows và outbox có tiến triển, không còn task kẹt ngoài policy.
- [ ] Đối soát duplicate/unknown transactions trong incident window.
- [ ] Handler không đánh dấu processed trước commit.

## 13. Đọc đúng nội bộ Spring Integration khi một connector lỗi

Một flow có thể bị kẹt **dù connector bên ngoài đã phục hồi** do channel, endpoint lifecycle, error handler, scheduler hoặc gateway reply mapping. Cần phân tích từng mắt xích.

### 13.1. Endpoint nào đang chạy?

| Thành phần | Vai trò | Điều cần kiểm tra |
| --- | --- | --- |
| **SourcePollingChannelAdapter** | Poll MessageSource như File/SFTP/JDBC | Scheduler, trigger, source.receive(), filter, maxMessagesPerPoll |
| **PollingConsumer** | Receive từ PollableChannel | QueueChannel depth, receiveTimeout, poller và handler |
| **Message-driven inbound adapter** | Listener từ JMS/AMQP/Kafka | Listener container, connection, subscription, ack |
| **Inbound gateway** | Nhận request bên ngoài và trả reply | HTTP request mapping, reply timeout, error mapping |
| **Outbound adapter** | Gửi một chiều tới hệ ngoài | Send result, retry/ack semantics, error path |
| **Outbound gateway** | Gửi request và chờ reply | Send timeout, remote I/O timeout, correlation |
| **Service activator** | Chạy business handler | Transaction, validation, idempotency |
| **MessageChannel** | Dispatch message | Direct/Executor/Queue/PubSub khác semantics |

### 13.2. Phân biệt lỗi gửi và lỗi handler

**DirectChannel** thường gọi handler trên thread gửi. Một exception đồng bộ từ handler có thể lan ngược tới adapter/gateway và ảnh hưởng transaction/ack nếu được cấu hình phù hợp.

**ExecutorChannel** có thể nhận message vào executor rồi xử lý ở thread khác. Khi adapter báo send thành công, **handler có thể chưa hoàn tất**. Error handling và transaction context không tự lan xuyên thread; phải theo dõi error channel và completion riêng.

**QueueChannel** giữ message cho consumer chủ động poll. Nếu channel trong memory bị mất khi restart, không thể nói “broker sẽ redeliver” trừ khi còn một nguồn bền vững phía trước và cơ chế retry được thiết kế.

**PublishSubscribeChannel** có thể gửi tới nhiều subscribers. Nếu một nhánh lỗi nhưng nhánh khác đã commit, replay toàn bộ có thể tạo side effect trùng ở nhánh đã thành công.

### 13.3. Poller đang sống nhưng không tiến triển

- [ ] Scheduler thread có bị nghẽn bởi công việc khác không?
- [ ] FixedDelay/FixedRate/Cron trigger có chạy đúng thời điểm không?
- [ ] maxMessagesPerPoll có thấp khiến backlog không giảm không?
- [ ] MessageSource.receive() trả null vì source rỗng hay vì filter loại hết?
- [ ] SFTP session/connect timeout có kéo dài mỗi lượt poll?
- [ ] Poller exception có bị error handler log rồi nuốt, không tạo alert?
- [ ] Nếu có transaction advice, đoạn nào thực sự được bao bởi transaction?

**receiveTimeout** trên PollableChannel không phải **HTTP/SFTP network timeout**. Khi source bên ngoài không kết nối, điều chỉnh receiveTimeout của QueueChannel có thể hoàn toàn không liên quan.

### 13.4. Gateway có timeout mà handler vẫn xử lý

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant GW as Spring Integration Gateway
    participant CH as ExecutorChannel
    participant H as Handler
    C->>GW: Request R1
    GW->>CH: send(R1)
    CH->>H: async process
    Note over GW: Reply timeout
    GW-->>C: Timeout
    H->>H: Business commit R1
    H-->>GW: Late reply
    Note over GW,H: Caller đã hết chờ; retry có nguy cơ duplicate
~~~

Nếu caller retry, phải dùng **requestId/idempotencyKey** để tra trạng thái và ngăn side effect lặp. Không cố “sửa” bằng cách tăng mọi timeout vô hạn.

### 13.5. ErrorChannel và lỗi transport

Spring Integration có **ErrorMessage**, error channel, advice chain và error handlers. Nhưng:

- Một exception có thể **ném lại**, **chuyển sang ErrorMessage**, hoặc bị **handler xử lý và nuốt**.
- Việc một error flow chỉ log lỗi **không bảo đảm** broker sẽ rollback/redeliver.
- Lỗi bất đồng bộ có thể không quay về original sender.
- MessageHeaders có thể chứa errorChannel/replyChannel nhưng phải bảo vệ thông tin nhạy cảm.
- Vị trí **ack/commit** cần được kiểm chứng với adapter/container cụ thể.

**Tác nghiệp đúng:** từ một business key/tracing ID, dựng đường đi qua **receive → channel send → transform → handler → DB/outbound → ack/reply**, xác định bước cuối có bằng chứng thành công và bước đầu có bằng chứng thất bại.

### 13.6. Endpoint lifecycle và quyền thao tác

Có thể sử dụng cơ chế quản lý endpoint do Spring Integration hỗ trợ (ví dụ lifecycle/start/stop, control bus nếu hệ thống đã cấu hình) để pause/resume flow. Nhưng **không giả định** mọi endpoint có thể dừng ngay tức thì hoặc dừng an toàn in-flight work. Tên bean, registry, lệnh điều khiển và quyền runtime phụ thuộc ứng dụng/phiên bản, cần đọc cấu hình đã được owner cung cấp trong quy trình vận hành.

**Không** gửi lệnh tùy tiện vào control bus production khi chưa xác minh đối tượng, mức quyền và side effect.

## 14. Retry, backoff, timeout, circuit breaker và bulkhead

Một thiết kế resilience tốt phải **khôi phục được lỗi tạm thời** mà không biến outage nhỏ thành thác retry làm sập hệ đích.

### 14.1. Bốn lớp retry cần phối hợp

| Lớp | Ví dụ | Rủi ro nếu cùng bật không kiểm soát |
| --- | --- | --- |
| HTTP client retry | Retry connect/read timeout | Lặp command side effect |
| Spring Integration advice/error handler | Retry handler gửi message | Nhân số lần gửi với client retry |
| Broker redelivery/retry topic | JMS/AMQP requeue, Kafka retry | Poison loop, DLT/backlog |
| Business/job scheduler | Re-enqueue task FAILED | Gửi lại cùng work nhiều lần |

Nếu mỗi lớp retry tối đa **3 lần**, số lượt gọi phía đích có thể nhiều hơn kỳ vọng do các vòng retry lồng nhau; **không lấy 3 là retry budget cuối**. Xác định **một tầng chủ trì retry** cho từng loại lỗi, còn các tầng khác chỉ báo trạng thái hoặc thực hiện retry có kiểm soát.

### 14.2. Bảng chính sách retry gợi ý

| Lỗi | Có retry? | Điều kiện |
| --- | --- | --- |
| DNS transient/connection reset | Có điều kiện | Retry có backoff, kiểm tra phạm vi và quota |
| HTTP 503/504 | Có điều kiện | Không làm lặp side effect khi outcome UNKNOWN |
| HTTP 429 | Có | Tôn trọng Retry-After và giảm tải |
| HTTP 400/422 | Thường không | Sửa request/schema trước |
| HTTP 401/403 | Không retry dồn dập | Credential/policy fix, security review |
| TLS/SSH host identity mismatch | **Không retry bỏ xác minh** | Xác minh owner/certificate/key |
| DB deadlock/serialization failure | Có điều kiện | Transaction có khả năng retry an toàn, budget |
| Broker unavailable | Có | Backoff/producer outbox/queue buffer |
| Poison message | Có giới hạn/không | Quarantine/DLQ, owner |

### 14.3. Backoff + jitter

Mẫu chính sách:

~~~text
attempt 1: retry after short delay
attempt 2: exponential increase + jitter
attempt 3: increase up to configured cap
attempt N: stop automatic retry; quarantine/escalate

Never busy-loop with zero delay when the dependency is unavailable.
~~~

Ví dụ này không phải cấu hình mặc định của Spring Retry hay Spring Integration. Các thông số thực phải căn cứ vào SLA, quota và idempotency của hệ đích.

### 14.4. Circuit breaker

Khi dependency liên tục lỗi, circuit breaker có thể tạm từ chối lời gọi để bảo vệ thread/connections. Nhưng một breaker **OPEN** không đồng nghĩa message được lưu ở nơi an toàn. Cần biết:

- Call bị từ chối thì message đang ở đâu?
- Caller nhận lỗi/fallback hay task được buffer?
- Có phân biệt **business UNKNOWN** và lỗi chưa gửi không?
- Thời điểm half-open thử phục hồi có tạo side effect lặp không?
- Khi breaker close, hệ đích có chịu được backlog không?

### 14.5. Bulkhead và bounded queue

Giới hạn số request/outbound calls đồng thời tới một endpoint để tránh một đối tác lỗi giữ toàn bộ thread. Nếu QueueChannel/ExecutorChannel có capacity, phải xác định hành vi khi đầy: chờ, reject, đưa vào broker bền vững hay trả lỗi có kiểm soát. **Không dùng queue trong heap vô hạn** để giấu backlog; JVM crash có thể làm mất work.

### 14.6. Timeout layering

~~~text
Business deadline
  >= / liên quan tới
  gateway reply timeout
  + outbound connect/read timeout
  + retry/backoff budget
  + handler/transaction execution time
~~~

Các mốc không nhất thiết cộng tuyến tính trong mọi implementation. Khi thiết kế, phải có **end-to-end deadline** rõ và bảo đảm các timeout từng bước không vượt deadline một cách vô ích. Một tầng timeout xảy ra **không tự hủy transaction bên kia**.

### 14.7. Ưu tiên sửa nguyên nhân gốc

Nếu DB pool cạn vì long-running transaction, tăng retry sẽ làm nhiều thread chờ hơn. Nếu API đích trả 429, tăng concurrency là sai hướng. Nếu Kafka rebalance do handler xử lý lâu, cần đánh giá thiết kế xử lý/partition/ack, không chỉ tăng session timeout không giới hạn.

## 15. Tính đúng dữ liệu: ack, commit, duplicate và reconciliation

Một runbook production phải có chính sách **data correctness** chứ không chỉ khôi phục network. Gần như mọi hệ tích hợp nhiều hop đều có những khoảng trống giữa nhận, xử lý và xác nhận.

### 15.1. Bản đồ trạng thái một work item

~~~text
SOURCE_AVAILABLE
  → DELIVERED
  → VALIDATED
  → BUSINESS_COMMITTED
  → TRANSPORT_ACKNOWLEDGED
  → RETENTION_OR_CLEANUP_ELIGIBLE

Các trạng thái ngoại lệ:
  RETRYABLE, UNKNOWN, DUPLICATE, QUARANTINED, EXPIRED, RECONCILE_REQUIRED
~~~

Đây là **state model ứng dụng** để tổ chức runbook, không phải một enum mặc định của Spring Integration. Các tên trạng thái có thể khác trong production; điều quan trọng là không đồng nhất những mốc khác nhau.

### 15.2. Ma trận cửa sổ lỗi

| Bước cuối có bằng chứng | Bước chưa có bằng chứng | Rủi ro | Hành động |
| --- | --- | --- | --- |
| Nguồn có file/hàng READY | Receive chưa thành công | Data pending | Giữ nguồn, sửa connector, sau đó nhận lại |
| Message đã đưa vào QueueChannel memory | Business chưa commit | JVM restart làm mất buffer | Tìm source durable, không giả broker redelivery |
| Broker delivered | Handler chưa commit | Redelivery có thể xảy ra | Retry/idempotency, giữ DLQ policy |
| DB đã commit | Broker ack/offset chưa xác nhận | Duplicate sau restart/rebalance | Deduplicate business key, ack sau xác minh |
| HTTP request đã gửi | Không có reply | UNKNOWN external side effect | Query status/idempotency, không retry mù |
| Claim Check token đã publish | Claim content không lấy được | Missing/expired claim | Reconcile store, retention và quyền |
| Business commit OK | Outbox event chưa phát | Downstream thiếu event | Outbox relay, publish idempotent |
| Business commit OK | Cleanup/ack incomplete | Tồn dư hoặc redelivery | Hoàn tất theo policy, không sửa business state sai |

### 15.3. Idempotency theo khóa nghiệp vụ

Một **message ID kỹ thuật** có thể thay đổi khi retry hoặc khi message được tạo lại. Idempotency nên dùng business key ổn định:

~~~text
sourceSystem + tenantId + operation + businessEntityId + version
~~~

Ví dụ partner gửi cùng đơn hàng hai lần với filename khác nhau, key theo **filename** không ngăn được tạo đơn trùng; key theo **partner + documentId/orderId + version** có thể phù hợp hơn nếu contract xác định mỗi version chỉ xử lý một lần.

### 15.4. Cấu trúc inbox/outbox minh họa

~~~sql
CREATE TABLE integration_inbox (
    consumer_name VARCHAR(120) NOT NULL,
    business_key VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    result_ref VARCHAR(200),
    PRIMARY KEY (consumer_name, business_key)
);

CREATE TABLE integration_outbox (
    event_id VARCHAR(180) PRIMARY KEY,
    business_key VARCHAR(200) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    publish_status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Đây là schema ví dụ, **không phải migration yêu cầu chạy** và không đầy đủ về retry/claim/version. Khi cả business table và inbox/outbox cùng một DB, có thể đưa thay đổi liên quan vào **một DB transaction**. Nhưng database transaction thông thường không rollback được HTTP request, SFTP rename hay broker send ở một hệ khác.

### 15.5. Reconciliation phải dựa trên nguồn sự thật

Với incident window **[last known good, first fully recovered]**, lập danh sách:

1. Work **đã phát từ nguồn** theo file manifest, outbox, broker log hoặc API request register.
2. Work **đã được nhận** bởi adapter.
3. Work **đã commit** ở hệ đích.
4. Work **đã ack/offset/mark processed** theo transport.
5. Work **đã vào DLQ/quarantine** hoặc còn pending.
6. Work **không xác định**: kết nối lỗi, ACK/reply mất hoặc log không đủ.

Không đối soát bằng **số đếm đơn thuần** nếu một file chứa nhiều đơn hàng, một message là batch hoặc có fan-out nhiều subscriber. Cần đối chiếu theo business key/version và đúng scope/tenant.

### 15.6. Những trạng thái không được tự động sửa

- **UNKNOWN_PAYMENT/UNKNOWN_ORDER:** tác động remote có thể đã commit, phải xác minh theo business reference.
- **OFFSET_AHEAD_OF_COMMIT:** Kafka đã bỏ qua record chưa có business result, cần kế hoạch replay có phê duyệt.
- **FILE_ARCHIVED_BUT_NOT_COMMITTED:** nguồn đã đổi trạng thái, cần phục hồi file theo audit.
- **DLQ_WITHOUT_ORIGINAL_PAYLOAD:** Claim Check retention hết hạn, không thể replay chỉ bằng token.
- **DUPLICATE_WITH_CONFLICTING_PAYLOAD:** cùng idempotency key nhưng nội dung thay đổi, cần xử lý version/conflict.

### 15.7. Tiêu chí số liệu sau reconciliation

Một báo cáo có thể trình bày:

~~~text
Expected distinct business keys:      2,000
Confirmed committed keys:             1,970
Retryable/pending keys:                  20
Quarantined with owner:                   8
UNKNOWN pending manual review:            2
Confirmed unintended duplicate effects:  0
~~~

Các giá trị là **ví dụ**. Nếu còn UNKNOWN, có thể tuyên bố **kết nối phục hồi nhưng incident data reconciliation còn mở**; không báo toàn bộ CLOSED khi chưa xử lý theo chính sách.

## 16. Bảo mật: chứng chỉ, định danh và quyền kết nối

Trong incident kết nối, người trực có thể bị áp lực “làm cho chạy lại”. Tuy nhiên một lỗi xác minh server có thể là dấu hiệu **tấn công giả mạo, sai routing hoặc thay đổi cấu hình trái phép**.

### 16.1. Tuyệt đối tránh

- Tắt **TLS certificate validation**, kiểm tra hostname hoặc SSH host-key verification để vượt lỗi handshake.
- Dùng tài khoản quản trị rộng thay cho credential service chỉ để xác minh request.
- Đăng raw password, access token, SFTP private key hoặc DB connection string có secret lên ticket/chat/log.
- Cho phép mọi IP/cidr vào firewall production không có scope hoặc expiry.
- Ghi toàn bộ message payload chứa PII vào log để “dễ debug”.
- Bỏ authorization theo tenant khi retry/replay.
- Tin header requesterId/tenantId do đối tác tự đặt mà không xác minh nguồn.

### 16.2. Runbook TLS/SSH mismatch

1. Xác nhận đây là **đúng host** từ cấu hình có thẩm quyền; kiểm tra DNS/routing thay đổi.
2. Thu thập fingerprint/certificate metadata **không nhạy cảm** và lỗi handshake.
3. Liên hệ system/partner owner **qua kênh độc lập** để xác minh planned rotation.
4. Nếu thay đổi được xác minh, cập nhật truststore/known hosts theo change process.
5. Thử kết nối tối thiểu và log audit.
6. Nếu không xác minh được, **giữ fail-closed**, escalation Security, không tiếp tục dữ liệu nhạy cảm.

### 16.3. Runbook credential expiry

1. Kiểm tra credential version và expiration qua secret management system được phép.
2. So sánh thời điểm rotation với first failed attempt.
3. Kiểm tra permission/scope của principal ở đúng resource; tránh cấp rộng.
4. Rotate/refresh credential qua quy trình phê duyệt, không hardcode hoặc lưu vào Markdown.
5. Xác minh **positive và negative authorization**: thao tác hợp lệ thành công, thao tác trái quyền vẫn bị từ chối.
6. Theo dõi lỗi trong các flow khác dùng cùng secret để tránh tác dụng phụ.

### 16.4. Network incident có thể bị hiểu nhầm với security incident

DNS trỏ nhầm endpoint, proxy đổi chứng chỉ, broker ACL bị thay hoặc token OAuth sai audience có thể tạo cùng cảm giác “server down”. Vì vậy phân loại đúng **network vs authentication vs authorization vs server identity** trước khi thay đổi firewall/TLS/credentials.

### 16.5. Cảnh báo mối quan hệ giữa access và dữ liệu tồn dư

Khi service account bị thu hồi vì compromise, có thể còn **token trong broker, object trong message store, claim references, DLQ hoặc file staging**. Khôi phục service cần kiểm tra ai có quyền đọc/tái phát dữ liệu tồn dư; không chỉ cấp lại một credential mới rồi bỏ quên các bản sao.

## 17. Checklist thay đổi production có kiểm soát

### 17.1. Chuẩn bị trước một thay đổi

- [ ] Xác định **system of record** và trạng thái message trong cửa sổ lỗi.
- [ ] Thay đổi được đề xuất có quyền và phạm vi hợp lệ.
- [ ] Có **before state**: cấu hình, version, metrics, pending/offsets, data correctness.
- [ ] Có hypothesis cho nguyên nhân, không chỉ “thử restart xem sao”.
- [ ] Có bản thay đổi nhỏ nhất, reversible khi có thể.
- [ ] Đã kiểm tra có làm duplicate, mất dữ liệu, reordering hoặc lộ secret không.
- [ ] Có canary/readback và ngưỡng dừng khi kết quả xấu.
- [ ] Có communication tới owner liên quan.

### 17.2. Trong lúc thực hiện

1. Ghi change/incident ID, owner và timestamp.
2. Thực hiện **một thay đổi được kiểm soát mỗi lần** nếu điều kiện incident cho phép.
3. Theo dõi connection failures, successful commit, backlog age, retries, DLQ và duplicate ngay sau thay đổi.
4. Nếu duplicate/unknown side effect tăng, dừng mở rộng traffic, thu thập bằng chứng.
5. Không xóa các artifact dùng để chứng minh sự cố khi chưa kết thúc đối soát.

### 17.3. Sau thay đổi

- [ ] Dependency handshake/authn/authz hợp lệ.
- [ ] Endpoint đúng flow và đúng environment đã start lại.
- [ ] Canary đã đi hết business commit và readback.
- [ ] Không có retry storm, queue memory pressure hoặc source file bị đọc trùng ngoài contract.
- [ ] Backlog có thể được xử lý trong khung SLO bằng tốc độ an toàn.
- [ ] Chỉ chuyển incident sang giai đoạn **recovery/reconciliation** khi có bằng chứng.

### 17.4. Rollback

Một rollback **chỉ khôi phục cấu hình** có thể không khôi phục data đã ghi. Nếu thay đổi đã khiến message được gửi/commit, rollback ứng dụng không được tự xóa kết quả nghiệp vụ. Cần xác minh transaction state, offset/queue position và replay safety riêng.

### 17.5. Mẫu bản ghi thao tác

~~~yaml
incidentId: INC-LAB-2026-011
changeId: CHG-LAB-009
targetFlow: orders-http-outbound
beforeVersion: "v1"
afterVersion: "v2"
reason: "approved TLS truststore rotation"
scope: "one external partner endpoint"
dataSafety:
  pendingWorkLocation: "durable-outbox"
  replayPolicy: "idempotency required"
  estimatedUnknownEffects: "PENDING_REVIEW"
validation:
  transportHandshake: "PENDING"
  canaryBusinessCommit: "PENDING"
  sourceTargetReconciliation: "PENDING"
rollback: "restore approved v1 configuration after evaluating in-flight work"
approval: "recorded incident owner placeholder"
~~~

**Không đánh dấu PASS khi chưa thử.** Đây là mẫu để điền, không đại diện một thay đổi đã triển khai.

## 18. Khôi phục backlog và replay đúng trình tự

Sau khi connectivity phục hồi, hệ thống có thể nhận một lượng work lớn đã tích tụ. Nếu mở toàn bộ workers ngay, downstream đang yếu có thể lỗi lại, tạo retry storm và làm sai ordering.

### 18.1. Các bước mở lại traffic

1. Xác minh nguồn công việc còn nguyên và có quyền đọc.
2. Phân loại work theo **new, pending, retryable, unknown, DLQ, already committed**.
3. Chạy một canary có business key riêng, kiểm tra source–target readback.
4. Mở **mức concurrency nhỏ** và quan sát commit throughput/latency.
5. Tăng dần khi sink còn dư capacity, không có retry storm.
6. Tách poison messages và không tự bỏ qua các event cần ordering.
7. Đối soát dữ liệu trong outage window, không chỉ xử lý backlog mới.
8. Quay về steady-state sau khi hoàn tất data correctness và SLO.

### 18.2. Ước lượng thời gian xả backlog

Nếu backlog ban đầu là **B work items**, tốc độ dữ liệu mới đến **λ item/s**, và throughput commit bền vững **μ item/s**, với μ lớn hơn λ:

~~~text
approximateDrainTimeSeconds = B / (μ - λ)
~~~

Ví dụ:

~~~text
B = 12,000 items
λ = 30 items/s
μ = 70 committed items/s
net drain = 40 items/s
approximate drain time = 300 s ≈ 5 phút
~~~

Đây là **ước lượng lý tưởng** trong điều kiện ổn định, chưa tính retry, batch, ordering, hot partitions, remote API throttling hoặc quota. Nếu μ không lớn hơn λ, backlog **không tự giảm**; tăng worker chưa chắc tăng μ khi sink đã bão hòa.

### 18.3. Backlog age quan trọng hơn chỉ số lượng

Một queue 1.000 messages mới đến có thể bình thường, nhưng queue 100 messages đã chờ 2 giờ có thể vi phạm nghiệp vụ. Đo **oldest unprocessed age**, deadline theo loại work và tỷ lệ đúng hạn.

### 18.4. Replay theo nguyên tắc tối thiểu

- **Chỉ replay những business keys cần replay**, không quét lại toàn bộ lịch sử nếu chưa có lý do.
- Giữ **idempotencyKey và eventVersion** ổn định khi tái phát công việc cũ.
- Với fan-out, tách phạm vi subscriber; không bắt nhánh đã commit làm lại vô ích.
- Với Kafka, không reset offset toàn group nếu chỉ một partition/range bị ảnh hưởng và chưa có phê duyệt.
- Với SFTP/File, phân biệt file đã parse một phần, đã commit toàn bộ hay chưa xử lý.
- Với HTTP command UNKNOWN, xác minh status trước khi tạo lại.
- Với DLQ, sửa schema/code hoặc dependency trước khi replay.

### 18.5. Phân luồng theo mức rủi ro

| Nhóm work | Ưu tiên xử lý | Ràng buộc |
| --- | --- | --- |
| Query read-only chưa trả kết quả | Có thể retry theo TTL/deadline | Không trả dữ liệu cũ/hết hạn |
| Business command đã xác minh chưa commit | Retry khi an toàn | Có idempotency và source state |
| Business command UNKNOWN | Đối soát trước | Không tự replay |
| Event stale version | Không áp lại nếu state mới hơn | Audit/repair theo business rule |
| DLQ poison message | Sửa nguyên nhân rồi controlled replay | Owner, số attempt, checksum/version |
| File chưa hoàn tất | Chờ producer công bố hoàn tất | Marker/rename/size contract |

### 18.6. Khi nào tạm dừng replay?

Dừng hoặc giảm tốc nếu:

- Business duplicate/conflict vượt ngưỡng an toàn.
- API đích trả 429/5xx tăng cùng throughput.
- DB pool saturation/lock wait tăng nghiêm trọng.
- Kafka rebalance liên tục hoặc offset/commit state bất thường.
- SFTP/file source hết retention, checksum mismatch hoặc file được thay đổi.
- DLQ tăng nhanh và chưa rõ nguyên nhân.

### 18.7. Kết thúc backlog drain

Không đợi queue depth chính xác bằng 0 nếu hệ thống liên tục nhận work. Thay vào đó, đo **steady-state age/lag, commit throughput và correctness**, rồi đối soát những item đặc biệt còn UNKNOWN/quarantine.

## 19. Dashboard và bằng chứng quan sát sau sự cố

Để runbook dùng được, mọi flow quan trọng nên có dashboard **gắn với một business outcome**. Những chỉ số ở adapter chỉ đo tầng vận chuyển, không thay thế bằng chứng kết quả cuối.

### 19.1. Bộ metrics tối thiểu

| Chỉ số | Dimension đề xuất | Câu hỏi trả lời |
| --- | --- | --- |
| **dependency_connection_failures_total** | flow, dependency, error class, region | Có bao nhiêu lỗi kết nối? |
| **dependency_reconnect_attempts_total** | connector type, dependency | Đang thử kết nối lại bao lâu/lặp tới mức nào? |
| **outbound_request_duration** | target, method/operation, outcome | Có chậm hoặc timeout? |
| **poll_attempts/empty_polls** | source, endpoint | Poller sống hay bị nghẽn? |
| **message_received_total** | flow, connector | Có work thực tới ứng dụng không? |
| **business_committed_total** | flow, result class | Có kết quả nghiệp vụ thật không? |
| **message_retry_total** | reason, stage | Retry tập trung ở đâu? |
| **message_duplicate_suppressed_total** | consumer, source | Có redelivery/duplicate nhiều không? |
| **message_dead_letter_total** | flow, category | Work nào cần triage? |
| **queue_depth / consumer_lag** | queue, group, partition | Backlog và phân phối tải ra sao? |
| **oldest_pending_age** | source, priority | Vi phạm freshness SLO chưa? |
| **message_inflight_unacked** | connector, consumer | Có work giữ lâu chưa ack không? |
| **connection_pool_active/wait** | datasource/client | Có nghẽn pool không? |
| **last_successful_business_commit** | flow | Kết quả cuối gần nhất là khi nào? |
| **unreconciled_work_count** | flow, severity | Bao nhiêu work còn UNKNOWN? |

**Tên metric là ví dụ đặt tên**, không phải metric mặc định được Spring Integration/Spring Boot tự phát với đúng nhãn này. Khi triển khai bằng Micrometer, tracing hoặc broker monitoring, phải map tên metric thực tế và bảo đảm cardinality hợp lý.

### 19.2. Những nhãn nên tránh

Không thêm **requestId, token, claimId, filename đầy đủ, raw URL chứa query secret, email, customerId** làm label metric có cardinality cao hoặc rò thông tin. Thay vào đó, dùng nhãn tổng hợp: flow, operation, source type, region, outcome, error class. Mã định danh đơn lẻ thuộc trace/log có quyền truy cập phù hợp.

### 19.3. Đối chiếu bốn biểu đồ trong cùng khung thời gian

~~~text
A. Dependency errors / minute       ↑ tăng mạnh lúc 15:03
B. Received vs committed / minute   nhận = 0, commit = 0
C. Backlog depth + oldest age       ↑ tăng liên tục
D. Retry, DLQ, duplicate rate       retry ↑, DLQ ổn định
~~~

Khi kết nối phục hồi:

~~~text
A. Dependency errors                ↓ về baseline
B. Committed throughput             ↑ lớn hơn arrival rate trong giai đoạn drain
C. Backlog/oldest age               ↓ về ngưỡng SLO
D. DLQ/duplicate/unknown            ổn định và có owner theo dõi
~~~

Nếu A giảm nhưng B vẫn bằng 0, chưa thể kết luận incident đã khôi phục; cần xem channel/handler/transaction.

### 19.4. Mẫu log cấu trúc

~~~json
{
  "incidentId": "INC-LAB-2026-011",
  "flow": "partner-orders-sftp-inbound",
  "dependencyType": "SFTP",
  "dependencyAlias": "partner-sftp-lab",
  "endpoint": "orders-inbound-adapter",
  "stage": "CONNECT",
  "outcome": "TRANSIENT_FAILURE",
  "errorClass": "ConnectTimeout",
  "businessKeyRef": "redacted-or-hashed",
  "retryAttempt": 3,
  "traceId": "TRACE-LAB-018",
  "occurredAt": "2026-11-23T15:05:00+07:00"
}
~~~

Đây là log **minh họa**, không phải format mặc định. Không ghi secret hoặc payload nguyên văn trong incident ticket; dùng liên kết đến kho audit có phân quyền.

### 19.5. Phân loại outcome thống nhất

Đề xuất dùng một hệ từ vựng giữa vận hành và engineering:

| Outcome | Ý nghĩa |
| --- | --- |
| **CONNECTED** | Handshake/connection thành công, chưa chứng minh work processed |
| **DELIVERED** | Work đã đến một endpoint/channel/broker |
| **COMMITTED** | Business transaction đáp ứng điều kiện hoàn tất |
| **ACKNOWLEDGED** | Transport ghi nhận tiến độ |
| **RETRYABLE** | Có thể thử lại theo policy |
| **PERMANENT_FAILURE** | Không tự retry nếu chưa sửa nguyên nhân |
| **UNKNOWN** | Không thể xác nhận side effect có xảy ra |
| **RECONCILED** | Đã đối chiếu trạng thái với nguồn sự thật |
| **QUARANTINED** | Work bị cô lập chờ owner |

Không sử dụng từ **SUCCESS** cho cả connect, send và business commit mà không nêu cụ thể thành công ở tầng nào.

## 20. Giao tiếp trong incident và bàn giao giữa các ca trực

Runbook giúp kỹ thuật khôi phục, nhưng một incident dài cũng cần thông tin **đúng, ngắn và không suy đoán** để đội nghiệp vụ biết rủi ro, phạm vi và bước tiếp theo.

### 20.1. Mẫu thông báo mở incident

~~~text
INCIDENT: [INC-ID] – [Flow/Dependency]
Thời điểm phát hiện: [timestamp timezone]
Tác động đã xác nhận: [nguồn/đích, chức năng, tenant/phạm vi]
Triệu chứng: [connection / timeout / backlog / no business progress]
Dữ liệu: [đã commit / pending / unknown; không đoán số lượng]
Containment: [hành động đã thực hiện, phạm vi]
Đang điều tra: [giả thuyết ưu tiên và bằng chứng]
Owner: [on-call/partner owner/incident commander]
Cập nhật tiếp theo: [theo chu kỳ truyền thông incident chính thức]
~~~

**Không** viết “không mất dữ liệu” khi chưa đối soát, cũng không chia sẻ hostname nội bộ/secret nếu kênh truyền thông không được phép.

### 20.2. Mẫu cập nhật tiến độ

~~~text
Trạng thái: INVESTIGATING / CONTAINED / RECOVERING / RECONCILING
Bằng chứng mới: [sự kiện hoặc metric đã xác minh]
Connection state: [DOWN / PARTIAL / UP]
Business progress: [commit rate, last success, backlog trend]
Outstanding unknown: [số lượng hoặc UNKNOWN]
Thay đổi đã áp dụng: [change ID, owner, rollback path]
Rủi ro còn lại: [retry, duplicate, loss, retention expiry, security]
Bước kế tiếp: [một hành động cụ thể]
~~~

### 20.3. Mẫu thông báo khôi phục kết nối nhưng chưa xong dữ liệu

~~~text
Đã khôi phục kết nối đến [dependency] và canary đã đi hết flow.
Backlog đang giảm trong phạm vi SLO dự kiến.
Các message thuộc cửa sổ [from, to] vẫn đang được đối soát;
chưa xác nhận hoàn toàn rằng không có work thiếu/trùng.
Nhóm phụ trách reconciliation: [owner].
Sự cố vẫn ở trạng thái RECOVERING/RECONCILING.
~~~

### 20.4. Mẫu đóng incident

~~~text
Incident [ID] được đóng lúc [timestamp].
Nguyên nhân xác định: [root cause hoặc best-supported cause].
Connection và business path đã được kiểm chứng:
  [transport test, canary, commit readback, backlog, reconciliation].
Dữ liệu:
  [expected, committed, replayed, quarantined, unknown].
Rủi ro tồn dư và owner:
  [nếu có, theo quy trình bàn giao].
Corrective actions:
  [action, owner, due date].
~~~

Nếu vẫn còn UNKNOWN, ghi **incident kết nối đã khắc phục nhưng work item đối soát còn mở** theo cơ chế quản trị phù hợp; không xóa dòng dữ liệu còn nghi vấn chỉ để đóng dashboard.

### 20.5. Bàn giao ca trực

- [ ] Incident ID, severity, service/flow và owners.
- [ ] Last known good, outage window, thời gian khôi phục kết nối.
- [ ] Thay đổi đang hiệu lực và cách rollback.
- [ ] Queue depth/lag/oldest age, retry/DLQ, business commit rate.
- [ ] Danh sách message/range còn UNKNOWN hoặc quarantine.
- [ ] Những thao tác **không được làm** cho tới khi có phê duyệt.
- [ ] Contact hệ ngoài/partner và tình trạng phản hồi.
- [ ] Hành động tiếp theo có owner và điều kiện kiểm chứng.

### 20.6. Ranh giới trách nhiệm giữa incident commander và engineer

Engineer đưa ra **bằng chứng và phương án kỹ thuật**, không tự quyết định chấp nhận mất dữ liệu nghiệp vụ. Incident commander điều phối ưu tiên và quyết định thay đổi trong phạm vi quyền; Security hoặc business owner tham gia khi thay đổi ảnh hưởng bí mật, tiền, dữ liệu cá nhân hoặc tính nhất quán nghiệp vụ.

## 21. Diễn tập tình huống đầy đủ: SFTP gián đoạn, RabbitMQ tồn đọng, DB chậm

### 21.1. Bối cảnh hệ thống giả lập

Hệ thống **Partner Orders Pipeline** nhận mỗi file CSV từ SFTP, kiểm tra schema, lưu thành các work items trong một RabbitMQ queue, sau đó nhiều workers ghi đơn hàng vào PostgreSQL thử nghiệm. Một số kết quả sau commit được gửi tới một HTTP service khác. Đây là **kịch bản học tập**; không có sự cố production thật nào được suy ra từ các con số dưới đây.

~~~mermaid
flowchart LR
    PARTNER["Partner SFTP"] --> POLL["SFTP inbound poller"]
    POLL --> PARSE["Validate / Split file"]
    PARSE --> OUT["AMQP outbound adapter"]
    OUT --> QUEUE["orders.work queue"]
    QUEUE --> A["Consumer A"]
    QUEUE --> B["Consumer B"]
    A --> DB[("Orders DB")]
    B --> DB
    DB --> HTTP["HTTP Outbound Gateway"]
    HTTP --> TARGET["Partner Status API"]
    POLL --> META["Persistent metadata"]
    A --> ERR["Error / DLQ / Audit"]
    B --> ERR
~~~

**Thiết kế đúng yêu cầu:** file chỉ được công nhận hoàn tất khi dữ liệu nghiệp vụ cần thiết được ghi theo contract; RabbitMQ có durable queue/ack policy phù hợp; DB có unique business key; HTTP side effect có idempotency/status lookup.

### 21.2. Timeline giả lập

| Mốc | Sự kiện | Bằng chứng |
| --- | --- | --- |
| 15:00 | Flow bình thường | File age thấp, business commit ổn |
| 15:03 | SFTP connection reset | Connection errors tăng |
| 15:05 | Poller vẫn RUNNING nhưng không nhận file | Last successful SFTP poll dừng |
| 15:08 | Đối tác báo đang upload batch mới | Có backlog ở nguồn |
| 15:10 | On-call mở incident | First failed hop là SFTP receive |
| 15:13 | Giảm retry, kiểm tra host/cert/credentials | Không làm thay đổi source files |
| 15:17 | Kết nối SFTP khôi phục | List/download canary thành công |
| 15:18 | Poller đưa nhiều file vào flow | Broker work queue tăng |
| 15:19 | DB pool chạm giới hạn | Handler timeouts, RabbitMQ unacked tăng |
| 15:22 | Giảm consumer concurrency | DB wait giảm, commits ổn định |
| 15:28 | Backlog bắt đầu giảm | Commit throughput lớn hơn arrival |
| 15:37 | Business data được đối soát | Pending/unknown được phân loại |

### 21.3. Những bước xử lý đúng

**Bước A — Không reset bộ lọc SFTP.** Trước khi replay cần xác định file nào đã commit trước outage; filter metadata chỉ là một tín hiệu, không thay business DB readback.

**Bước B — Giữ raw file/source.** Nếu dữ liệu của đối tác còn đang upload, chờ marker hoặc rename hoàn tất; không đọc file đang ghi dở vì poller vừa reconnect.

**Bước C — Phát work idempotent.** Nếu producer RabbitMQ bị timeout lúc publish, một event có thể đã được broker nhận. Giữ event ID/business key ổn định để consumer chống lặp.

**Bước D — Giới hạn tải downstream.** Sau khi SFTP phục hồi, nếu RabbitMQ có nhiều message nhưng DB đã quá tải, tăng AMQP concurrency sẽ làm tình hình tệ hơn. Giảm tốc và đo commit throughput thực.

**Bước E — Đối soát request HTTP không có reply.** Nếu đơn hàng đã commit DB và HTTP status API timeout, ghi trạng thái UNKNOWN của HTTP side effect; không gửi lại command không có idempotency.

**Bước F — Kiểm tra cuối:** nguồn SFTP, số file, số row hợp lệ, broker queue/DLQ, DB business keys, và các trạng thái HTTP remote phải khớp theo contract.

### 21.4. Hai lỗi nguy hiểm nếu làm vội

**Sai lầm 1 — Đổi tất cả file về “chưa xử lý”.** Nếu 40% file đã tạo đơn trước outage, việc reset metadata rồi chạy lại có thể tạo duplicate khi business không idempotent.

**Sai lầm 2 — Scale workers lên cực lớn để xóa backlog.** DB pool vốn đang nghẽn; thêm worker có thể tăng lock/timeout/redelivery, làm backlog già hơn và khó đối soát hơn.

### 21.5. Bằng chứng tối thiểu để đóng case study

- [ ] SFTP host identity hợp lệ và file-ready contract được tuân thủ.
- [ ] Có danh sách file nguồn trong incident window, trạng thái xử lý từng file.
- [ ] RabbitMQ published/delivered/acked/DLQ được đối chiếu theo business events, không chỉ tổng số.
- [ ] DB chứa đúng một kết quả theo business key cần unique.
- [ ] HTTP commands UNKNOWN có state query hoặc owner theo dõi.
- [ ] Last business commit mới xuất hiện, oldest backlog age giảm dưới SLO.
- [ ] Những item quarantined có reason, owner và kế hoạch replay.
- [ ] Config sau incident có rollback/reference, audit và root-cause notes.

## 22. Ma trận kiểm thử runbook trước khi áp dụng production

Bộ test này tập trung vào **khả năng thao tác và khôi phục**, không chỉ unit test parser. Kịch bản cần chạy trong môi trường thử/diễn tập được phép, có **before/after state** và evidence; không tự đánh dấu PASS nếu chưa thực hiện.

### 22.1. Kết nối, định danh và phân loại lỗi

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **RB-01** | DNS của HTTP target không phân giải | Phân loại DNS/network, retry bounded, không lộ secret |
| **RB-02** | HTTP connect timeout | Không giả định remote đã nhận request |
| **RB-03** | HTTP read timeout sau remote DB commit | Trạng thái UNKNOWN, status query/idempotency trước retry |
| **RB-04** | HTTP 429 có Retry-After | Giảm nhịp; không retry storm |
| **RB-05** | HTTP 401 do token hết hạn | Credential refresh/rotation an toàn, không brute-force |
| **RB-06** | HTTP 403 do thiếu quyền thật | Không tự nâng privilege, báo owner |
| **RB-07** | TLS cert mismatch | Fail-closed, xác minh owner, không disable validation |
| **RB-08** | SFTP host-key mismatch | Chặn kết nối chưa xác minh, không auto-accept |
| **RB-09** | SFTP key hết hạn | Rotate đúng service principal, không log private key |
| **RB-10** | File inbound poll rỗng nhưng nguồn không có file | Không tự báo outage sai |

### 22.2. File, polling và lưu trữ

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **RB-11** | SFTP connect timeout 10 phút | Backoff/alert, không tạo tight retry loop |
| **RB-12** | File đang upload chưa rename | Không parse file chưa hoàn tất |
| **RB-13** | Poller RUNNING nhưng filter loại file mới | Tìm được nguyên nhân filter/metadata, không reset mù |
| **RB-14** | Hai replicas cùng nhìn một file | Shared claim/metadata và idempotency tránh side effect trùng |
| **RB-15** | Stream SFTP lỗi giữa download | Đóng session/stream, có đường đọc lại an toàn |
| **RB-16** | Local staging disk full | Pause/giảm tải, không xóa file chưa commit |
| **RB-17** | QueueChannel in-memory chứa work khi JVM crash | Thừa nhận giới hạn; nguồn durable/reconciliation xử lý |
| **RB-18** | Claim Check token còn, original message đã hết TTL | Missing claim được phát hiện, không ack success giả |

### 22.3. JMS, RabbitMQ và Kafka

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **RB-19** | JMS broker restart | Listener reconnect đúng destination, redelivery an toàn |
| **RB-20** | JMS listener dừng do lỗi credentials | Phân loại auth, khôi phục quyền tối thiểu |
| **RB-21** | JMS commit DB rồi chết trước ack | Business idempotency ngăn duplicate |
| **RB-22** | JMS error handler nuốt exception | Test chứng minh ack/retry semantics thực, tránh mất message |
| **RB-23** | RabbitMQ publisher confirm bị mất | Ghi outcome UNKNOWN, retry theo stable event ID |
| **RB-24** | RabbitMQ unacked cao do prefetch | Tìm worker chậm, tune có kiểm chứng |
| **RB-25** | RabbitMQ poison message requeue vô hạn | Retry budget/DLQ dừng loop |
| **RB-26** | Kafka broker không reachable | Retry/backoff, listener khôi phục assignment |
| **RB-27** | Kafka consumer group rebalance liên tục | Chẩn đoán partition/processing time, không reset offset |
| **RB-28** | Kafka commit DB trước offset commit | Redelivery không tạo side effect trùng |
| **RB-29** | Kafka offset vượt business state | Incident data-gap, replay có phê duyệt |
| **RB-30** | Kafka có 3 partitions, 5 consumers | Không khẳng định 5 consumers đều active |

### 22.4. Database, nghiệp vụ và khả năng phục hồi

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **RB-31** | DB connection pool cạn | Giảm tải/tối ưu; không chỉ tăng retry |
| **RB-32** | DB deadlock transient | Retry transaction đúng policy và idempotent |
| **RB-33** | JDBC task CLAIMED nhưng worker chết | Lease reclaim có version/fencing |
| **RB-34** | Outbox commit thành công nhưng relay chưa publish | Retry cùng event ID, không mất message |
| **RB-35** | HTTP command side effect đã commit nhưng reply timeout | Reconciliation/lookup ngăn thực hiện hai lần |
| **RB-36** | DLQ replay sau sửa schema | Chỉ replay mục tiêu, business result đúng |
| **RB-37** | Fan-out một nhánh đã commit, nhánh khác lỗi | Không bắt nhánh thành công xử lý trùng vô ích |
| **RB-38** | Business event đến sai version | Không ghi đè state mới bằng state cũ |
| **RB-39** | Deploy rolling khi còn message unacked | Graceful stop/redelivery theo contract |
| **RB-40** | Mở lại backlog quá nhanh làm DB 503/timeouts | Backpressure/circuit breaker giữ hệ đích ổn định |
| **RB-41** | Thử rollback connector sau khi có side effect | Không tự rollback business state ngoài transaction |
| **RB-42** | Reconciliation còn UNKNOWN sau khi reconnect | Incident chưa tự tuyên bố data fully recovered |

### 22.5. Quan sát và kiểm soát con người

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **RB-43** | Endpoint RUNNING nhưng business commits=0 | Alert no progress phát hiện lỗi |
| **RB-44** | Empty polls khi không có input theo lịch | Không tạo false page kéo dài |
| **RB-45** | Source retention sắp hết trước recovery | Có cảnh báo và phối hợp giữ nguồn |
| **RB-46** | Incident log chứa access token | Redaction/ACL và xử lý đúng chính sách |
| **RB-47** | Operator định purge DLQ khi chưa đối soát | Runbook chặn và yêu cầu approval |
| **RB-48** | Bàn giao ca trực khi còn backlog/unknown | Có owner, evidence, next action và rollback |
| **RB-49** | Canary transport thành công nhưng business DB chưa ghi | Không đánh dấu toàn bộ incident resolved |
| **RB-50** | Remote partner phản hồi khôi phục nhưng metrics lỗi | Tiếp tục điều tra dựa trên end-to-end evidence |

### 22.6. Mẫu báo cáo ca kiểm thử

~~~yaml
testCase: RB-35
flow: "orders-http-outbound"
scenario: "Remote commit succeeds but reply is lost"
expected: >
  The request enters UNKNOWN status; business state is checked using
  the same stable idempotency key before any retry.
actual: "Fill after experiment"
result: PENDING
evidence: "lab://tests/RB-35"
owner: "integration-lab"
verifiedAt: null
~~~

Mẫu YAML này **chỉ là minh họa trong tài liệu**, không phải file mới cần tạo trong repository. Không chuyển result sang PASS khi chưa kiểm tra trạng thái thật tại remote và tác động ở business DB.

### 22.7. Thứ tự chạy test có ích

1. **Tầng mạng:** timeout, DNS, TLS, authentication.
2. **Tầng connector:** listener/poller startup, subscription, channel/error mapping.
3. **Tầng dữ liệu:** retry, ack, offset, idempotency, business commit.
4. **Tầng hạ tầng:** restart broker/DB, worker crash, rolling deployment.
5. **Tầng vận hành:** backlog drain, alerts, incident communications và rollback.

Các phép thử **negative/fault injection** thường bộc lộ sai lầm nhiều hơn chỉ chạy một request happy path. Luôn cách ly môi trường và dữ liệu thử trước khi gây lỗi có chủ ý.

## 23. Game day: diễn tập mất kết nối định kỳ

Runbook không được kiểm chứng trong diễn tập có thể chứa những giả định sai về **endpoint lifecycle, broker ack, source retention hoặc giới hạn của hệ đích**. Game day có mục đích chứng minh runbook áp dụng được, không phải tạo sự cố production vô cớ.

### 23.1. Điều kiện trước khi diễn tập

- [ ] Môi trường thử có phạm vi quyền rõ ràng, tách dữ liệu và credential production.
- [ ] Có **test dataset** với business key riêng, biết expected output.
- [ ] Có một người điều phối và người thực hiện được cấp quyền.
- [ ] Có rollback/abort criteria và cách khôi phục data test.
- [ ] Dashboard metrics/log/tracing đã hoạt động và không chứa secret.
- [ ] Có snapshot cấu hình/test state phù hợp.
- [ ] Phạm vi fault injection được phê duyệt; không tác động đối tác thật nếu chưa có thỏa thuận.

### 23.2. Năm bài diễn tập nên ưu tiên

| Drill | Lỗi mô phỏng | Cần quan sát |
| --- | --- | --- |
| **G1 – SFTP unavailable** | Test server ngừng cho kết nối trong một khoảng giới hạn | Backoff, alert, file readiness, readback sau phục hồi |
| **G2 – HTTP timeout after commit** | Mock trả response chậm hoặc mất sau khi lưu kết quả | UNKNOWN, idempotency và trạng thái remote |
| **G3 – Broker restart** | JMS/AMQP test broker restart | Redelivery, ack, duplicate suppression, backlog |
| **G4 – Kafka rebalance** | Dừng một consumer member test | Assignment, offset, lag và ordering |
| **G5 – DB pool saturation** | Giới hạn kết nối hoặc làm chậm DB test | Bulkhead, backpressure, không retry storm |

### 23.3. Diễn tập chi tiết G2: mất response nhưng DB đã commit

**Dữ liệu đầu vào:** Request CreateOrder có idempotencyKey = ORDER-TEST-0099.

**Fault injection:** mock remote service ghi đơn hàng rồi chủ động làm caller timeout trước khi trả response. Không dùng endpoint thanh toán hoặc tạo đơn production thật.

**Mục tiêu:**

1. Gateway báo timeout/UNKNOWN thay vì “chưa xử lý”.
2. Retry controller giữ cùng idempotencyKey.
3. Service trả lại kết quả đã lưu hoặc cho tra trạng thái.
4. Business DB chỉ có **một** đơn theo khóa thử nghiệm.
5. Audit có timestamp cho send, commit, timeout, status lookup và reconciliation.

**Đánh giá FAIL nếu:** handler tạo hai đơn, mất dấu trạng thái UNKNOWN hoặc bắt lỗi rồi báo success giả.

### 23.4. Diễn tập chi tiết G3: broker lỗi giữa receive và ACK

1. Publish một message hợp lệ với stable business ID.
2. Cho consumer nhận và ghi DB.
3. Gây crash/đứt kết nối **trước acknowledgment** trong môi trường test.
4. Khôi phục broker/consumer.
5. Kiểm tra có redelivery hay không theo policy.
6. Xác minh DB vẫn chỉ có một business effect.
7. Kiểm tra DLQ và attempts; không có infinite loop.

Nếu kịch bản không thể kiểm soát chính xác thời điểm crash, ghi rõ **giới hạn phép thử**, không tuyên bố đã chứng minh exactly-once.

### 23.5. Chỉ số đánh giá runbook

| Tiêu chí | Cách đo |
| --- | --- |
| **Time to detect** | Thời gian từ first failure tới alert được nhìn thấy |
| **Time to classify** | Thời gian xác định đúng first failing hop |
| **Time to contain** | Thời gian đưa hệ vào trạng thái không làm xấu dữ liệu |
| **Time to reconnect** | Đến lúc connection/canary hoạt động |
| **Time to business recovery** | Đến lúc commits/lag đáp ứng tiêu chí |
| **Time to reconcile** | Đến khi phân loại mọi work trong incident window |
| **Operator error count** | Thao tác sai scope/thiếu approval, nếu có |
| **Replay correctness** | Số business keys thiếu/trùng/stale sau diễn tập |

### 23.6. Sau diễn tập

Ghi những gì **runbook nói phải xảy ra** và **thực tế đã xảy ra**. Cập nhật chỉ dẫn, owner, dashboard, cảnh báo hoặc coding practices trong vòng cải tiến tiếp theo. **Không biến phần này thành sửa bài học của module khác trong STEP 4**; đây là hướng dẫn cho người học.

## 24. Postmortem, corrective actions và đóng vòng lặp độ tin cậy

Sự cố kết nối thường có một **trigger** rõ (cert hết hạn, broker node down, API rate limit) nhưng **tác động dữ liệu lớn hơn trigger** nếu retry/ack/retention/idempotency chưa tốt. Postmortem phải nói rõ nguyên nhân gốc và những điều kiện khiến tác động lan rộng.

### 24.1. Cấu trúc postmortem

1. **Summary:** dịch vụ, thời gian bắt đầu/kết thúc, mức độ và ảnh hưởng.
2. **Customer/business impact:** flow, volume, độ trễ, lỗi, việc chưa đối soát.
3. **Timeline:** thông tin có timestamp và nguồn bằng chứng.
4. **Detection:** cảnh báo nào phát hiện, cảnh báo nào không hoạt động.
5. **Root cause and contributing factors:** network, TLS, credential, config, code, broker, DB, retry, owner dependency.
6. **Data correctness:** expected/committed/missing/duplicate/unknown/quarantine.
7. **Mitigation and recovery:** thay đổi đã làm, hiệu quả, rollback.
8. **What went well / poorly:** điểm mạnh/yếu của runbook, phối hợp và telemetry.
9. **Corrective actions:** sửa mã/cấu hình/monitoring/runbook/test, owner và deadline.
10. **Follow-up validation:** test hoặc game day chứng minh action đã giải quyết vấn đề.

### 24.2. Tách trigger với yếu tố khuếch đại

Ví dụ:

~~~text
Trigger:
  Partner SFTP server đổi host key nhưng không có planned notification.

Contributing factor A:
  Không có cảnh báo trước về certificate/key rotation.

Contributing factor B:
  Poller retry liên tục không backoff phù hợp.

Contributing factor C:
  Source file retention quá ngắn so với outage window.

Contributing factor D:
  Processed metadata không được đối soát khi recovery.

Corrective actions:
  (1) Partner change notification + owner process.
  (2) Backoff/circuit breaker + no-progress alert.
  (3) Retention agreement / outbox / durable staging.
  (4) Replay checklist và idempotency/reconciliation tests.
~~~

Các nội dung trên là ví dụ, không đại diện một incident thật. Đội vận hành phải tránh quy kết nguyên nhân khi chưa có evidence.

### 24.3. Tiêu chí corrective action tốt

| Chưa đủ cụ thể | Có thể kiểm chứng |
| --- | --- |
| “Improve monitoring” | “Thêm alert oldest SFTP file age vượt SLO trong giờ nhận file, drill RB-11” |
| “Make retries safer” | “Giới hạn retry budget cho HTTP 503/429 và giữ idempotencyKey; test RB-03/RB-04” |
| “Fix Kafka” | “Ổn định partition assignment và commit policy, game day rebalance test RB-28” |
| “Handle failures” | “Phân biệt transient/permanent, DLT owner, test poison loop RB-25” |
| “Improve DB” | “Theo dõi DB pool wait, reduce concurrency when saturated, test RB-31” |
| “Ensure no duplicates” | “Unique business key + inbox transaction, fault-injection test RB-21/RB-23/RB-28” |

### 24.4. Phải có owner và chứng cứ đóng action

Mỗi action cần:

- Mục tiêu và phạm vi connector.
- Đội/role owner.
- Ngày cần hoàn tất theo tổ chức.
- Kiểu thay đổi: code, cấu hình, tài nguyên, quyền, vận hành hay hợp đồng đối tác.
- Test/rehearsal chứng minh kết quả.
- Rollback/risk của thay đổi.

Không đóng corrective action chỉ vì PR merge/deploy xong; nếu action nhằm ngăn mất/trùng dữ liệu, cần test phù hợp hoặc bằng chứng tương đương.

### 24.5. Chu kỳ rà soát runbook

Runbook cần được rà soát khi:

- Đổi broker/HTTP client/SFTP/JDBC connector hoặc Spring Integration version.
- Đổi error handler, retry advice, ack/offset hoặc transaction strategy.
- Thay topology multi-instance, partitions, queues, consumer groups.
- Thay credential, TLS/SSH key rotation policy hoặc các đối tác ngoài.
- Thay retention của Kafka/file/object store/DLQ.
- Một incident/game day bộc lộ hướng dẫn sai hoặc thiếu.

## 25. Checklist một trang cho người trực và tổng kết

### 25.1. Checklist 60 giây trước khi thao tác

- [ ] Tôi biết **flow, environment, first failing hop** và thời điểm last good.
- [ ] Tôi biết nguồn còn dữ liệu hay không; message đang nằm ở đâu.
- [ ] Tôi đã kiểm tra network/TLS/auth/capacity **trước** khi restart.
- [ ] Tôi không định tắt kiểm tra TLS/SSH hoặc mở rộng quyền trái chính sách.
- [ ] Tôi chưa xóa queue/DLQ/file, reset offsets hoặc metadata mà không có approval.
- [ ] Tôi biết message nào **COMMITTED, ACKED, UNKNOWN, RETRYABLE**.
- [ ] Tôi đã xác định idempotency và cách đối soát trước replay.
- [ ] Tôi có canary, điều kiện dừng, rollback và owner.
- [ ] Tôi theo dõi **business commits** và **backlog age**, không chỉ connection.
- [ ] Tôi ghi evidence và cập nhật incident trước khi chuyển ca.

### 25.2. Ma trận nhanh theo giao thức

| Giao thức | Kiểm tra kết nối | Điểm cần giữ an toàn | Tín hiệu phục hồi |
| --- | --- | --- | --- |
| **File/SFTP** | SSH key/session, path, poller, file-ready filter | Remote file, accept-once metadata, staging | File mới được xử lý một lần, backlog age giảm |
| **HTTP** | DNS/TLS/auth, 429/5xx, connect/read timeout | Side effect UNKNOWN, idempotency key | Canary + status readback, 5xx giảm |
| **JMS** | Broker/session/listener, destination, auth | Ack/transaction/redelivery, DLQ | Business commit và queue depth ổn |
| **AMQP** | Connection/channel/exchange/queue/binding | Publisher confirm, unacked, requeue/DLQ | Ack + commit, ready/unacked giảm |
| **Kafka** | Broker/SASL/TLS, group assignment, lag | Offset/commit/rebalance, DLT, retention | Lag per partition giảm và business commit khớp |
| **JDBC** | DB/connection pool/query/locks | Transaction, claim/lease/outbox | Query/commit ổn định, task stuck giảm |

### 25.3. Ba cột kết quả sau khi khôi phục

~~~text
TRANSPORT
  Connection/TLS/authentication OK
  Endpoint/listener/poller/channel hoạt động

DATA DELIVERY
  Backlog/lag giảm theo SLO
  Retry/DLQ/offset/ack không có bất thường chưa giải quyết

BUSINESS CORRECTNESS
  Committed results được readback
  Duplicate/missing/stale/UNKNOWN được đối soát
  Incident actions và owners được bàn giao
~~~

### 25.4. Câu hỏi tự kiểm tra

1. Vì sao một endpoint báo RUNNING mà still có thể không xử lý message?
2. **HTTP connect timeout** khác **HTTP read timeout sau commit** thế nào?
3. Nếu SFTP host key thay đổi bất ngờ, nên làm gì trước khi cập nhật known hosts?
4. Khi SFTP poller kết nối lại, vì sao không reset accept-once metadata hàng loạt?
5. Vì sao QueueChannel trong memory không thay thế JMS/RabbitMQ durable queue?
6. Một JMS listener trả về sau khi đẩy message vào ExecutorChannel có thể gây rủi ro ACK nào?
7. Publisher confirm của RabbitMQ có chứng minh DB downstream commit không?
8. Kafka lag cao một partition có được sửa chỉ bằng tăng consumers không?
9. Nếu Kafka offset đã commit nhưng DB chưa có kết quả, cần xử lý theo quy trình nào?
10. Khi database pool exhausted, tăng retry có thể gây hệ quả gì?
11. Vì sao DLQ/replay cần business key và owner?
12. Một message đã gửi nhưng reply mất nên được đánh dấu trạng thái gì?
13. Circuit breaker OPEN có tự bảo vệ message khỏi mất không?
14. Khi backlog cao, nên theo dõi thông lượng received hay committed?
15. Điều kiện gì phải đạt trước khi tuyên bố **business recovered**?

**Gợi ý:** (1) mất connection/filter/handler; (2) một trường hợp chưa kết nối, trường hợp khác remote có thể đã xử lý; (3) xác minh nguồn qua kênh độc lập; (4) rủi ro duplicate; (5) không có durability/redelivery như broker; (6) ack trước business commit; (7) không; (8) không, cần xem partition/key/sink; (9) reconciliation và replay có phê duyệt; (10) làm nghẽn thêm; (11) tránh side effect trùng và poison loop; (12) UNKNOWN; (13) không; (14) committed cùng backlog age; (15) canary, tiến triển, SLO và correctness.

### 25.5. Kết luận

**Runbook cho mất kết nối hệ thống ngoài** không chỉ là quy trình reconnect. Trong Spring Integration Adapters, một sự cố có thể bắt đầu ở **File/SFTP MessageSource, HTTP gateway, JMS/AMQP listener, Kafka consumer group hoặc JDBC connection pool**, rồi lan qua MessageChannel, handler, retry, transaction, DLQ và hệ đích.

Để vận hành an toàn, cần thực hiện theo chuỗi **phát hiện → định vị → containment → sửa nguyên nhân → canary → xả backlog có kiểm soát → đối soát → bàn giao/postmortem**. Phải phân biệt **đã nhận, đã gửi, đã xử lý, đã commit và đã ack**, vì một lỗi ở khoảng giữa có thể tạo mất dữ liệu hoặc duplicate dù kết nối đã chạy lại.

**Nguyên tắc cuối cùng:** *Khôi phục connection chỉ là bước đầu; phục hồi production thực sự được chứng minh khi luồng nghiệp vụ tiếp tục tiến triển, dữ liệu trong cửa sổ sự cố được đối soát và mọi thao tác retry/replay đều có thể giải thích, kiểm chứng và kiểm soát rủi ro.*

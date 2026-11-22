# Bảo vệ phương án và điều chỉnh khi yêu cầu nghiệp vụ thay đổi

## 1. Mục tiêu của bài thực hành

Một bản thiết kế ứng dụng cloud tốt vẫn cần được **bảo vệ trước phản biện**: nó giải quyết nhu cầu nghiệp vụ nào, đạt độ tin cậy và hiệu năng ra sao, phải đánh đổi những gì, bằng chứng nào chứng minh quyết định và điều kiện nào buộc phải thiết kế lại.

Bài này đưa người học vào vai kiến trúc sư của một nền tảng bán hàng. Người học phải **xác định yêu cầu → thiết kế phương án → so sánh lựa chọn → bảo vệ quyết định → tiếp nhận yêu cầu thay đổi → phân tích tác động → cập nhật phương án → lập kế hoạch kiểm chứng**. Các kỹ năng này giúp đưa nguyên tắc Well-Architected từ danh sách kiểm tra vào quyết định thực tế.

Kết thúc bài học, người học có thể:

1. Chuyển yêu cầu nghiệp vụ thành mục tiêu phi chức năng, SLI/SLO và tiêu chí nghiệm thu đo được.
2. Lập lập luận theo chuỗi **yêu cầu – lựa chọn – đánh đổi – bằng chứng – rủi ro – điểm xem xét lại**.
3. Trả lời phản biện từ người sở hữu sản phẩm, SRE, bảo mật, quản trị dữ liệu và tài chính.
4. Phân tích tác động dây chuyền của yêu cầu mới đến network, compute, data, security, scalability, reliability, chi phí và vận hành.
5. Cập nhật Architecture Decision Record (ADR), sơ đồ, kế hoạch di chuyển và kiểm thử một cách nhất quán.
6. Nhận biết khi cần thương lượng mục tiêu hoặc xin quyết định kinh doanh thay vì đưa ra một cam kết kỹ thuật thiếu bằng chứng.

> **Nguyên tắc:** Bảo vệ kiến trúc không có nghĩa giữ nguyên quyết định ban đầu bằng mọi giá. Một quyết định tốt đúng trong phạm vi các giả định đã nêu và có điều kiện để xem xét lại khi dữ kiện thay đổi.

## 2. Tình huống xuyên suốt: OmniOrder

### 2.1. Bối cảnh

Doanh nghiệp giả định **OmniOrder** đang hiện đại hóa hệ thống đặt hàng chạy trên máy chủ tự quản lý thành ứng dụng trên cloud. Khách hàng có thể duyệt sản phẩm, tìm kiếm, thêm giỏ, tạo đơn và thanh toán qua cổng đối tác. Nhân viên vận hành có thể tra cứu, hủy/hoàn tiền và đối soát đơn hàng. Nhóm triển khai có tám kỹ sư quen Java, SQL, container và CI/CD nhưng ít kinh nghiệm vận hành hệ thống phân tán nhiều dịch vụ.

Mọi thông số sau đây là **giả định để luyện thiết kế**, không phải khuyến nghị cấu hình chung hay lời cam kết về nhà cung cấp cloud cụ thể.

| Mã | Yêu cầu hoặc ràng buộc ban đầu | Mức ưu tiên |
|---|---|---|
| BR-01 | Khách được đặt đơn, thanh toán và theo dõi trạng thái | Bắt buộc |
| BR-02 | Nhân viên tra cứu và xuất báo cáo đơn hàng cuối ngày | Bắt buộc |
| Q-01 | Đỉnh hiện tại 300 yêu cầu đọc/giây và 40 lần bắt đầu checkout/giây | Dự báo cần kiểm thử |
| Q-02 | p95 xem sản phẩm dưới 400 ms, p95 phản hồi tạo đơn dưới 900 ms | SLO theo hành trình |
| Q-03 | Availability SLO của API đặt hàng 99,9% theo tháng | Mục tiêu, cần định nghĩa phạm vi |
| Q-04 | Lỗi một Availability Zone: mục tiêu phục hồi khả năng phục vụ trong 10 phút | Mục tiêu cần diễn tập |
| Q-05 | Thảm họa toàn vùng: RTO tối đa 2 giờ, RPO tối đa 15 phút | Yêu cầu DR cần bằng chứng |
| S-01 | Dữ liệu khách hàng và thanh toán phải được bảo vệ, mã hóa và phân quyền | Bắt buộc |
| O-01 | Triển khai nhiều lần/tuần, có quan sát lỗi và rollback | Bắt buộc |
| C-01 | Tổng chi phí cloud không vượt trần do tài chính duyệt | Trần chưa được cung cấp |
| T-01 | Cutover trong 6 tháng; hệ thống cũ còn đối soát trong chuyển tiếp | Ràng buộc tiến độ |

**Điểm phản biện cần phát hiện:** 99,9% availability trong tháng 30 ngày tương ứng khoảng \(30 \times 24 \times 60 \times 0{,}001 = 43{,}2\) phút ngân sách không sẵn sàng nếu tính theo phút và không có ngoại lệ. Một sự cố toàn vùng kéo dài 2 giờ sẽ vượt ngân sách này. Vì vậy **Q-03 và Q-05 chưa được chứng minh tương thích**; phải làm rõ phạm vi SLO, xác suất/thời lượng sự cố, phương án duy trì phục vụ hoặc mức rủi ro được chấp nhận. Không tự coi RTO 2 giờ là bằng chứng đạt 99,9%.

### 2.2. Quy trình và bất biến nghiệp vụ

Hành trình quan trọng của khách:

1. Duyệt danh mục và thêm sản phẩm vào giỏ.
2. Gửi yêu cầu tạo đơn có **idempotency key** để xử lý gửi lại an toàn.
3. Hệ thống chốt snapshot giá, số lượng, địa chỉ và tổng tiền; lưu đơn ở trạng thái chờ thanh toán.
4. Cổng thanh toán trả kết quả hoặc gọi callback có thể đến muộn/lặp lại.
5. Hệ thống xác nhận đơn hợp lệ, phát sự kiện cho khâu thông báo và vận hành.

Các **invariant** không được phép phá vỡ: một thao tác gửi lại không tự tạo thêm đơn khác; không ghi nhận cùng một thanh toán hai lần do retry; tổng tiền đơn đã chốt không thay đổi chỉ vì giá catalog thay đổi; đơn được chuyển trạng thái theo quy tắc hợp lệ.

Nền tảng cần xác định kết quả nào là **chấp nhận yêu cầu**, kết quả nào mới là **đơn hoàn tất**. HTTP 202 không đồng nghĩa đã thanh toán thành công; trả nhanh nhưng backlog tăng vô hạn cũng không đáp ứng nhu cầu nghiệp vụ.

### 2.3. Câu hỏi cần hỏi trước khi vẽ sơ đồ

- Số 40 checkout/giây là số lần người dùng bấm xác nhận hay đơn thực sự thành công? Tỷ lệ retry ra sao?
- Availability SLO bao gồm endpoint và nhóm khách hàng nào? Có loại trừ bảo trì hoặc lỗi đầu vào không?
- Đơn hàng, tồn kho và thanh toán phải nhất quán ngay ở bước nào? Bước nào được xử lý bất đồng bộ?
- Cổng thanh toán có giới hạn kết nối/rate, thời hạn callback và sandbox mô phỏng sự cố không?
- Phân loại dữ liệu nhạy cảm, nơi cư trú, thời hạn giữ và chính sách backup/khóa được ai xác nhận?
- Có thể sử dụng token từ cổng thanh toán để không lưu dữ liệu thẻ trong ứng dụng không?
- Trần C-01 là bao nhiêu, bao gồm những khoản gì (logging, egress, backup, DR, support)?
- Có bao nhiêu region/AZ và dịch vụ phù hợp với yêu cầu pháp lý, latency, khả năng vận hành?
- Chức năng nào được ưu tiên khi hệ thống thiếu tài nguyên: checkout hay gợi ý sản phẩm/báo cáo?

Nếu chưa có đáp án, ghi **assumption** cùng người chịu trách nhiệm và thời hạn xác nhận. Không biến thông tin chưa kiểm chứng thành một lời hứa trong tài liệu.

## 3. Cách bảo vệ một quyết định

Một lập luận tốt đi theo chuỗi:

~~~text
Mục tiêu nghiệp vụ / yêu cầu có mã
   ↓
Tình huống chất lượng và điều kiện nghiệm thu
   ↓
Lựa chọn kiến trúc và phương án thay thế
   ↓
Lý do, đánh đổi và chi phí
   ↓
Bằng chứng đã có / thử nghiệm cần làm
   ↓
Rủi ro còn lại, owner và trigger xem xét lại
~~~

Đối với từng quyết định lớn, người học cần trả lời:

1. **Chúng ta đang giải quyết vấn đề nào?** Gắn với yêu cầu BR/Q/S/O/T cụ thể.
2. **Có những cách khả thi nào?** Ít nhất một phương án thay thế đáng cân nhắc.
3. **Vì sao chọn phương án hiện tại?** Phân tích hiệu năng, độ tin cậy, bảo mật, tốc độ thay đổi, chi phí.
4. **Bằng chứng nào hỗ trợ?** Benchmark, data-flow review, thử failover, giá dịch vụ và giới hạn quota.
5. **Điều gì chưa chắc?** Dự báo tải, đặc điểm dữ liệu, hành vi đối tác, năng lực đội.
6. **Khi nào quyết định hết phù hợp?** Tải, yêu cầu pháp lý, SLA, ngân sách hoặc tổ chức thay đổi.

Ví dụ câu trả lời yếu: “Dùng microservices vì cloud-native, dễ scale và ổn định”.

Câu trả lời có thể đánh giá: “Với nhóm tám người và nghiệp vụ đang được tinh chỉnh, chúng tôi ưu tiên modular monolith đa replica. Ordering, Catalog và Payment Integration có ranh giới module rõ để kiểm soát data ownership. Điểm yếu là scale cả runtime khi chỉ checkout tăng; chúng tôi sẽ đo DB wait, p95/p99 và throughput trong load test. Nếu nhu cầu tách scale hoặc release riêng được chứng minh và hợp đồng nghiệp vụ đã ổn định, chúng tôi sẽ đánh giá tách module bằng Strangler Fig.”

## 4. Lựa chọn kiến trúc ban đầu

### 4.1. Phương án A: modular monolith đa replica

Một thiết kế logic có thể là:

~~~mermaid
flowchart TB
    C[Web / Mobile] --> E[DNS + CDN/WAF + Load Balancer]
    E --> A[Java app nhiều replica / nhiều AZ]
    subgraph M[Modular Monolith]
      A --> CAT[Catalog]
      A --> ORD[Ordering]
      A --> PAY[Payment Integration]
    end
    CAT --> CACHE[(Cache dữ liệu đọc)]
    CAT --> DB[(Managed relational DB / Multi-AZ)]
    ORD --> DB
    PAY --> DB
    ORD --> OUT[Transactional Outbox]
    OUT --> R[Outbox Relay]
    R --> Q[Queue / Event Bus]
    Q --> W[Notification Worker]
    PAY --> PSP[Payment provider / Sandbox]
    A -. Logs, metrics, traces .-> OBS[Observability]
    DB -. Backup, health, audit .-> OBS
    Q -. Lag / DLQ .-> OBS
~~~

Đây là **sơ đồ logic**. Outbox thường là bảng trong database nghiệp vụ và được ghi cùng transaction của thay đổi đơn; việc phát event ra broker được thực hiện sau, có thể phát lặp nên consumer phải idempotent. Multi-AZ ở từng tầng cần kiểm tra cụ thể theo dịch vụ đã chọn; sơ đồ không tự tạo khả năng chịu lỗi toàn vùng.

Quyết định chính:

- **Compute:** ứng dụng stateless nhiều replica; health/readiness check, cân bằng tải, triển khai và rollback có kiểm soát.
- **Networking:** chỉ công khai entry point cần thiết; database, worker, broker, management dùng phân đoạn mạng và quyền tối thiểu.
- **Data:** database quan hệ authoritative cho đơn và transaction; sở hữu schema, index và migration rõ.
- **Cache:** dành cho read phù hợp, có TTL và invalidation; không để cache quyết định kết quả giao dịch.
- **Messaging:** queue phục vụ công việc hậu xử lý như thông báo; retry giới hạn, DLQ và SLO cho hoàn tất nghiệp vụ.
- **Security:** TLS, IAM least privilege, quản lý secret/khóa, bảo vệ callback, logging phù hợp phân loại dữ liệu.
- **Operations:** CI/CD, IaC, SLI theo hành trình đặt hàng, DB waits, quota, queue lag và chi phí theo môi trường.

### 4.2. Xử lý thanh toán không đồng bộ và chống trùng

~~~mermaid
sequenceDiagram
    participant U as Client
    participant O as Ordering
    participant DB as DB
    participant P as Payment provider
    participant Q as Queue
    participant W as Worker
    U->>O: Tạo đơn (idempotency key)
    O->>DB: Transaction: đơn chờ + outbox
    DB-->>O: Commit
    O-->>U: Order ID + trạng thái chờ
    O->>P: Yêu cầu thanh toán (idempotency)
    P-->>O: Response / Callback
    O->>DB: Xác minh callback + chuyển trạng thái + outbox
    DB-->>O: Commit
    DB-->>Q: Relay phát event đã lưu
    Q->>W: OrderConfirmed (có thể gửi lại)
    W-->>Q: Ack sau xử lý idempotent
~~~

Sơ đồ đơn giản hóa một state machine thực. Thiết kế cần xử lý timeout khi provider đã nhận yêu cầu nhưng ứng dụng chưa nhận phản hồi; callback sai thứ tự; hoàn tiền; đối soát giao dịch với provider và việc không thu tiền hai lần. **Không giả định giao dịch ACID xuyên database và cổng thanh toán.**

### 4.3. So sánh ba phương án

| Tiêu chí | A. Modular monolith đa replica | B. Microservices theo domain | C. Serverless theo sự kiện |
|---|---|---|---|
| Tốc độ ra mắt của nhóm tám người | Ít pipeline, ít phụ thuộc vận hành | Nhiều service, hợp đồng và ownership | Cần kỹ năng workflow/event/quota mới |
| Giao dịch tạo đơn | Thuận lợi với transaction cục bộ | Cần thiết kế consistency giữa service | Cần quản lý trạng thái và xử lý lặp |
| Scale theo chức năng | Bị giới hạn nếu module chung runtime | Tốt khi ranh giới đúng, downstream không nghẽn | Tốt với tác vụ phù hợp, chịu concurrency/quota |
| Độ trễ và lỗi từng phần | Ít network hop nội bộ | Nhiều network hop và timeout cần quản lý | Event/workflow có thể tăng độ trễ |
| Bảo mật | Ít service identity nhưng cần bảo vệ boundary module | Nhiều điểm giao tiếp, IAM, secrets | Phân quyền từng function/event và dữ liệu |
| Chi phí | Dễ ước lượng nền; scale cả runtime | Tăng overhead nền, telemetry, network, on-call | Phụ thuộc invocation, runtime và dịch vụ hạ nguồn |
| Thay đổi về sau | Tách module cần kỷ luật phụ thuộc | Độc lập nếu domain thực sự rõ | Phụ thuộc hợp đồng và độ tin cậy event |

Chọn **A có điều kiện** trong giai đoạn đầu vì đội nhỏ, domain chưa ổn định và chưa có bằng chứng scale riêng theo capability. Không khẳng định A rẻ nhất hoặc đáp ứng SLO khi chưa có benchmark và mô hình chi phí. B/C vẫn có thể là quyết định đúng khi yêu cầu, năng lực đội hoặc workload thay đổi.

### 4.4. Rủi ro cần công khai

| Rủi ro | Hậu quả | Việc cần làm / người chịu trách nhiệm |
|---|---|---|
| Database trở thành nút thắt ở đỉnh checkout | Latency cao, lock/connection đầy | Data + Platform đo query, pool, IOPS, transaction |
| Hỏng cả region | Vi phạm RTO/RPO/availability | Architect + SRE thiết kế và diễn tập DR |
| Callback/payment timeout và retry | Sai trạng thái hoặc thu tiền trùng | Payment owner thử sandbox và reconciliation |
| Cache stale | Hiển thị giá/thông tin cũ | Product/Data xác định độ mới chấp nhận |
| Autoscaler khởi động chậm | Spike vượt SLO trước khi đủ replica | SRE đo thời gian scale, cân nhắc pre-warm |
| Chưa có giá dịch vụ và trần rõ | Rủi ro chi phí | Finance + Platform xác nhận giá, ngân sách và dự phòng |

## 5. Đưa phương án ra kiểm chứng

| Requirement | Thiết kế liên quan | Kiểm chứng cần thực hiện | Tiêu chí quyết định |
|---|---|---|---|
| Q-01/Q-02 | Gateway, app, DB, cache | Load test theo tỉ lệ xem/tìm/checkout | Đạt p95, lỗi và throughput nghiệp vụ tại đỉnh |
| Q-03 | Nhiều replica, health check, rollback | SLI end-to-end, thử lỗi replica | Phục vụ trong error budget đã định nghĩa |
| Q-04 | Phân tán AZ, DB HA | Failure drill một AZ | Khôi phục chức năng và dữ liệu theo mục tiêu |
| Q-05 | DR/backup/replication | Restore/failover drill và đối soát | RTO/RPO đo thực đáp ứng |
| S-01 | IAM, secret, mã hóa, network, audit | Threat model, quyền truy cập, data-flow review | Không có đường vượt quyền, chính sách dữ liệu đạt |
| C-01 | Compute, DB, storage, observability, DR | Dự toán theo tải và kiểm tra sau thử nghiệm | Tổng chi phí trong trần có dự phòng |
| O-01 | IaC, pipeline, runbook | Canary/rollback và incident drill | Nhóm vận hành khôi phục được thay đổi |

Các phép thử phục vụ những câu hỏi khác nhau. Load test không chứng minh RTO/RPO; một cấu hình Multi-AZ không tự chứng minh SLO; triển khai thành công không chứng minh dữ liệu được phân quyền đúng.

### 5.1. Bảo vệ bằng số liệu đúng phạm vi

Lưu ý khi trình bày:

- **Availability** khác **RTO** và **RPO**: một mục tiêu recovery kéo dài có thể làm vượt error budget.
- **Throughput hữu ích** là giao dịch thành công trong SLO, không phải request nhận vào hoặc HTTP 202.
- **Độ trễ p95/p99** cần đo hành trình đầu-cuối, không lấy trung bình phân vị của nhiều instance.
- **Autoscaling** tăng tài nguyên nhưng không tự giải quyết DB, cache, queue hoặc quota bão hòa.
- **Backup** không phải bằng chứng restore thành công; phải kiểm tra có thể giải mã, đọc, khôi phục nhất quán.
- **Chi phí** phải tính cả compute, DB, cache, egress, logging/tracing, backup và DR, theo giả định rõ ràng.

## 6. Phiên bảo vệ trước hội đồng

Giả lập 5 vai: Product Owner, SRE/Platform, Security, Data Owner và Finance. Kiến trúc sư trình bày trong 10 phút, dành 15 phút trả lời phản biện.

| Người hỏi | Câu hỏi phản biện | Cách trả lời nên có |
|---|---|---|
| Product | Vì sao không tách hết thành microservices để dễ scale? | Nêu data/team coupling, lựa chọn thay thế, ngưỡng quyết định tách |
| SRE | Nếu AZ hoặc toàn region hỏng thì checkout ra sao? | Chỉ rõ failure domain, điểm phụ thuộc, DR drill, khoảng chưa chứng minh |
| Security | Callback bị giả mạo hoặc replay sẽ thế nào? | Xác thực/chữ ký, chống replay, idempotency, audit, test |
| Data Owner | Làm sao tránh tạo đơn hoặc ghi thanh toán trùng? | Invariant, unique constraint, idempotency, transaction, outbox, đối soát |
| Finance | Nếu lưu lượng tăng 5–8 lần, chi phí thế nào? | Cost model, guardrail, giới hạn scale, giả định báo giá và phương án giảm tải |
| Business continuity | RTO 2h có thực sự đạt 99,9% SLO? | Nêu xung đột, lựa chọn tăng HA/DR, đổi SLO có phê duyệt hoặc rủi ro còn lại |

Trả lời tốt có cấu trúc: **“Chúng tôi chọn X để đáp ứng yêu cầu Y, có đánh đổi Z. Bằng chứng đã có là A; còn thiếu B và sẽ kiểm tra bằng C. Nếu không đạt D thì chuyển sang E.”**

Trả lời chưa đạt là dùng tên công nghệ hoặc tài liệu marketing làm bằng chứng chắc chắn, chẳng hạn “Cloud tự động HA và scale nên không thể lỗi”.

## 7. Change request 1: chiến dịch flash sale

Sau review, bộ phận kinh doanh bổ sung yêu cầu:

> Trong một đợt flash sale 30 phút, mức đọc tăng từ **300 lên 2.400 request/giây** và lần bắt đầu checkout tăng từ **40 lên 320 lần/giây**. Lưu lượng có thể tăng trong **30 giây**. Checkout giữ mục tiêu p95 dưới 900 ms, không phát sinh đơn trùng; tổng chi phí autoscaling không được tự động vượt ngân sách.

Đây là lưu lượng **bắt đầu thao tác**, chưa phải số đơn thanh toán thành công. Những phép tính capacity phải phân biệt tổng request, throughput nghiệp vụ, retry và xử lý bất đồng bộ.

### 7.1. Ma trận tác động

| Lớp | Rủi ro do thay đổi | Bằng chứng cần đo |
|---|---|---|
| CDN/edge | Băng thông, cache miss, WAF/rate limit | Cache hit, edge quota, egress cost |
| Application | Spike nhanh hơn thời gian tạo replica | Desired/ready replica, startup latency, p95/p99 |
| Ordering | Ghi đơn, idempotency và tranh chấp dữ liệu tăng | Đơn thành công, duplicate, DB lock, connection |
| Database | Query, write IOPS, outbox, pool bão hòa | Wait, query time, lock, replication lag |
| Queue/worker | Sự kiện đến nhanh hơn xử lý | Enqueue/dequeue, oldest age, DLQ, drain time |
| Payment | Provider rate limit/timeout | Sandbox, quota, retry, reconciliation |
| Observability | Log/trace và chi phí tăng mạnh | Sampling, log volume, ingestion cost |
| Finance | Pre-scale và dự phòng tạo chi phí | Estimate cho spike, ngân sách tối đa, scale-in |

### 7.2. Lựa chọn cải tiến

**A1. Pre-scale ứng dụng trước chiến dịch:** tăng min replica dựa trên thử nghiệm, tối ưu database, cache nội dung đọc, kiểm tra quota và thanh toán. Có thể thực hiện nhanh nhưng dễ phải scale cả runtime và đẩy bottleneck sang DB.

**A2. Tách luồng đọc và ghi:** CDN/cache cho catalog, read model hoặc read replica khi phù hợp; checkout vẫn dùng dữ liệu authoritative. Giảm tải đọc lên DB nhưng phải xử lý stale cache, cache stampede và chi phí mới.

**A3. Nhận checkout bất đồng bộ có giới hạn:** lưu lệnh và idempotency an toàn, trả trạng thái chờ rõ ràng, xử lý qua workflow/queue. Có thể hấp thụ spike nhưng thay đổi trải nghiệm, yêu cầu SLO hoàn tất nghiệp vụ, tránh trùng và quản lý backlog. Không tuyên bố đơn đã thành công khi chỉ mới được đưa vào queue.

**Đề xuất có điều kiện:** thử A1 kết hợp phần đọc của A2 trước; chọn A3 chỉ khi doanh nghiệp chấp nhận trạng thái bất đồng bộ và cơ chế giao dịch đạt điều kiện đúng đắn. Không tự động tách toàn bộ thành microservices để chữa một đợt đỉnh tải ngắn.

### 7.3. Kế hoạch thử và quyết định

~~~text
Test 1: baseline 300 read/s + 40 checkout attempts/s
Test 2: tăng tải từng bước tới 2.400 read/s + 320 checkout attempts/s
Test 3: spike lên tải đích trong 30 giây
Test 4: giữ tải 30 phút, theo dõi DB/queue và outcome
Test 5: giảm tải, đo drain backlog và scale-in
Test 6: timeout payment, callback trùng, retry và đối soát đơn
~~~

Ghi **requested/achieved rate, p95/p99, lỗi, đơn hợp lệ, duplicate, DB waits, lag, quota, autoscaling timeline và chi phí**. Nếu load generator không phát đủ tải hoặc dataset không đại diện, không được tuyên bố hệ thống production đã đạt năng lực.

Các điều kiện dừng gồm sai lệch đơn/tiền, lỗi kéo dài trên ngưỡng phê duyệt, backlog tăng không kiểm soát và tác động ra ngoài phạm vi thử nghiệm. Admission control có thể bảo vệ hệ thống khi quá tải, nhưng tỷ lệ từ chối cần được phản ánh minh bạch trong SLI.

**Quyết định có thể điều chỉnh:** giữ modular monolith, pre-warm tải flash sale, tối ưu/cache read, giới hạn DB/payment, theo dõi khả năng drain và scale-in. Nếu sự kiện lặp lại thường xuyên hoặc Ordering có tải/nhịp release riêng được chứng minh, xem xét tách capability này bằng ADR mới.

## 8. Change request 2: dữ liệu và mục tiêu phục hồi mới

Một khách hàng doanh nghiệp yêu cầu theo hợp đồng rằng **dữ liệu định danh, log chứa định danh, bản sao lưu và bản sao DR phải cư trú trong một lãnh thổ xác định**. Đây là **giả định của bài thực hành**, không phải tuyên bố về luật của bất kỳ nước nào.

Đồng thời, khách hàng muốn RTO thảm họa toàn vùng giảm từ **2 giờ xuống 30 phút**, RPO giảm từ **15 xuống 5 phút**.

### 8.1. Phân tích xung đột trước khi thiết kế

- Bản sao dữ liệu có thể nằm trong database, cache, log, trace, analytics, object store, snapshot, queue, dead-letter queue và công cụ hỗ trợ.
- Cần xem luồng đi qua nhà cung cấp thanh toán, observability và mạng của bên thứ ba có mang dữ liệu bị giới hạn hay không.
- Multi-AZ trong một region **không đồng nghĩa** chịu được sự cố toàn region.
- RTO 30 phút có thể đòi vùng dự phòng độc lập và quy trình failover được diễn tập. Nếu lãnh thổ quy định không có vùng độc lập phù hợp, ràng buộc cư trú có thể xung đột với mục tiêu DR.
- Backup định kỳ không tự đáp ứng RPO 5 phút; replication cũng không tự chứng minh RTO 30 phút nếu các thành phần liên quan chưa thể phục vụ.
- Cần xác định dữ liệu, khóa mã hóa, quyền truy cập, thứ tự khôi phục, DNS, event replay và consistency khi chuyển vùng.

**Hành động bắt buộc:** kiểm tra chính xác điều kiện hợp đồng, phân loại và đường đi dữ liệu, dịch vụ/region được phép, phương án DR và chi phí. Nếu không có topology khả thi, phải báo mâu thuẫn cho chủ nghiệp vụ và pháp chế; không tự bỏ yêu cầu cư trú.

### 8.2. Phương án DR để so sánh

| Lựa chọn | Giá trị | Rủi ro hoặc giới hạn |
|---|---|---|
| Multi-AZ trong vùng hợp lệ + backup/PITR | Phù hợp nhiều lỗi cục bộ, vận hành tương đối đơn giản | Không bảo đảm mất toàn vùng |
| Hai region độc lập đều được phép về cư trú | Có cơ sở thiết kế DR tách vùng | Phải xác minh region, replication, key, failover, chi phí |
| Môi trường DR khác loại hạ tầng nhưng trong lãnh thổ | Có thể đáp ứng giới hạn vị trí | Phức tạp mạng, đồng bộ, vận hành và diễn tập |
| Backup phục hồi theo yêu cầu | Chi phí nền có thể thấp | Có thể không đáp ứng RTO 30 phút/RPO 5 phút |

**Đề xuất có điều kiện:** nếu có hai vùng độc lập hợp lệ và đủ năng lực, thiết kế DR theo failure domain, replication, trạng thái bảo mật, runbook và đo failover thực. Nếu không có, trình chủ hợp đồng **lựa chọn kinh doanh**: thương lượng SLA hợp pháp, điều chỉnh phạm vi dịch vụ hoặc đầu tư giải pháp hạ tầng khác. Không tuyên bố đạt chỉ dựa vào sơ đồ.

### 8.3. Điều kiện nghiệm thu cho yêu cầu mới

Diễn tập với workload và dữ liệu đại diện; đo từ lúc phát hiện lỗi cho đến khi khách có thể thực hiện nghiệp vụ hợp lệ. Đối soát dữ liệu phục hồi với RPO, kiểm tra order/payment state machine, không thu tiền trùng khi replay event, quyền giải mã khóa và tính đúng của luồng tích hợp. Đánh giá data-flow thực tế từ app qua log, backup, analytics và bên thứ ba để kiểm chứng cư trú.

## 9. Quy trình xử lý thay đổi yêu cầu

~~~mermaid
flowchart TD
    R[Yêu cầu mới] --> C[Làm rõ owner, mục tiêu, phạm vi, deadline]
    C --> T[Phân loại bắt buộc / mục tiêu / giả định]
    T --> I[Impact analysis xuyên app, data, network, security, cost]
    I --> O[So sánh phương án và đánh đổi]
    O --> D{Khả thi trong các ràng buộc?}
    D -->|Có| P[ADR + migration/test/rollback plan]
    D -->|Chưa| E[Escalate cho chủ nghiệp vụ có thẩm quyền]
    E --> O
    P --> V[Đo kiểm và nghiệm thu]
    V --> G{Đạt tiêu chí?}
    G -->|Không| O
    G -->|Có| A[Phê duyệt triển khai và theo dõi]
~~~

| Chiều tác động | Câu hỏi phải trả lời |
|---|---|
| Business/UX | Có đổi nghĩa của “thành công”, thứ tự xử lý, hành vi người dùng? |
| Compute/scale | Có cần warmup, autoscaling khác, tách thành phần hoặc tăng quota? |
| Networking | Latency, gateway, luồng vào/ra, kết nối đối tác và failure domain có đổi? |
| Data | Schema, data owner, replication, consistency, backup, cư trú, retention có đổi? |
| Security | Trust boundary, IAM, secret, key, audit, hợp đồng xử lý dữ liệu có đổi? |
| Reliability | SLO, RTO/RPO, blast radius, failover, rollback và runbook có đổi? |
| Operations | CI/CD, observability, on-call, khả năng quản lý hệ thống và trách nhiệm có đủ? |
| Cost | Compute, DB, egress, queue, log, backup/DR, chi phí đội ngũ và trần có đổi? |
| Delivery | Deadline, phụ thuộc đối tác, dữ liệu chuyển tiếp, backward compatibility ra sao? |

Một yêu cầu có thể được giải quyết bằng **điều chỉnh tham số**, **thêm/thay thành phần**, **đổi ranh giới/hợp đồng**, hoặc **đàm phán mục tiêu kinh doanh**. Độ lớn của thay đổi kiến trúc không được đo bằng số dòng IaC mà bằng ảnh hưởng đến nghiệp vụ, dữ liệu, phụ thuộc và khả năng quay lui.

## 10. Bảo vệ quyết định bằng hồ sơ truy vết

Một kiến trúc thường được trình bày bằng sơ đồ, nhưng sơ đồ đơn lẻ không cho biết vì sao thành phần xuất hiện và phải kiểm thử gì. **Requirement traceability matrix** giúp nối từng yêu cầu với thiết kế, bằng chứng và người chịu trách nhiệm.

| Requirement | Quyết định liên quan | Bằng chứng hoặc test | Trạng thái / rủi ro |
|---|---|---|---|
| BR-01: tạo và thanh toán đơn | Ordering, transaction/outbox, Payment Integration | Test idempotency, retry, callback, đối soát đơn/tiền | Chưa thể kết luận trước kiểm thử |
| Q-02: checkout p95 dưới 900 ms | Replica, DB index/connection, network path | Load test theo hành trình và dataset đại diện | Cần đo thực tại tải Q-01 |
| Q-03: 99,9% monthly availability | Multi-AZ, health, rollback | SLI đầu-cuối và fault drill | Có căng thẳng với RTO vùng |
| Q-05: RTO 2h/RPO 15m | DR/backup/replication | Restore/failover drill và reconciliation | Chưa được bảo đảm chỉ bằng backup |
| CH-01: spike 8x | Pre-scale, read caching, quota/guardrail | Spike/soak + cost report + business verification | DB/payment có thể là bottleneck |
| CH-02: dữ liệu cư trú | Data inventory, placement, IAM, logging, backups | Data-flow mapping, config/audit review | Chưa xác minh có region phù hợp |
| CH-03: RTO 30m/RPO 5m | Topology DR mới nếu cần | Recovery drill đo đầu-cuối | Có thể xung đột chi phí/cư trú |

Khi yêu cầu đổi, cập nhật đồng bộ **sơ đồ triển khai, data-flow, bảng yêu cầu, ADR, threat model, test plan, cost model, runbook và risk register**. Đừng để ADR nói đã chuyển data owner nhưng một sơ đồ khác vẫn mô tả hai hệ thống cùng ghi không kiểm soát.

### 10.1. Ghi độ chắc chắn của tuyên bố

| Nhãn | Ý nghĩa | Ví dụ |
|---|---|---|
| **Assumed** | Giả định chưa được xác nhận | Đỉnh 320 checkout attempts/s chỉ kéo dài 30 phút |
| **Measured** | Đã có dữ liệu đo với môi trường và thời điểm rõ | p95 710 ms trong test 200 checkout/s ở dataset X |
| **Approved** | Có người có quyền xác nhận quyết định hoặc rủi ro | Product chấp thuận trạng thái PENDING của checkout |
| **Open** | Chưa có câu trả lời đủ tin cậy | Nhà cung cấp có hai vùng hợp lệ cho DR hay không |
| **Rejected** | Không đáp ứng ràng buộc hoặc không cân xứng lợi ích | Bỏ logging cho dữ liệu nhạy cảm chỉ để giảm chi phí |

**Measured không đồng nghĩa Approved**, và Approved không thay thế Measured. Một kết quả hiệu năng chỉ có giá trị trong phạm vi cấu hình, workload, dữ liệu và môi trường của phép thử; một quyết định có phê duyệt vẫn cần kế hoạch xác minh.

### 10.2. Mẫu ADR cho thay đổi tải

~~~markdown
# ADR-012: Năng lực cho flash sale OmniOrder

## Trạng thái
Proposed — chờ kết quả load test và duyệt ngân sách.

## Bối cảnh
CH-01: đọc 300 lên 2.400 req/s; checkout attempts
40 lên 320 lần/giây trong 30 giây;
duy trì đỉnh 30 phút, p95 checkout dưới 900 ms.

## Phương án
A. Pre-scale modular monolith, cache đọc, tối ưu DB.
B. Tách Ordering thành service có pipeline riêng.
C. Chuyển checkout sang workflow nhận yêu cầu bất đồng bộ.

## Quyết định đề xuất
Thử A kết hợp tối ưu đường đọc trước.
Giữ Ordering trong module cho đến khi có bằng chứng
về tải, release cadence hoặc yêu cầu cô lập riêng.

## Đánh đổi
Tăng chi phí trước chiến dịch và scale cả ứng dụng;
DB/payment có thể tiếp tục giới hạn throughput.

## Kiểm chứng
Spike test 30 giây; giữ tải 30 phút; đối soát
giao dịch, callback, retry, backlog và chi phí.

## Điều kiện xem xét lại
Nếu không đạt SLO trong trần ngân sách hoặc
chiến dịch lặp lại với nhu cầu scale độc lập,
thẩm định phương án B/C bằng ADR mới.

## Owner và approval
Product, SRE, Data, Security, Finance.
~~~

Khi quyết định mới thay thế một ADR cũ, đánh dấu quan hệ **supersedes/superseded by** thay vì xóa lịch sử. Cách này giải thích vì sao một quyết định từng phù hợp nhưng không còn phù hợp sau khi yêu cầu hoặc bằng chứng thay đổi.

## 11. Đàm phán những đánh đổi thật sự

Yêu cầu có thể xung đột với nhau: nâng DR giảm RTO nhưng tăng chi phí; giảm latency có thể cần thêm cache, compute hoặc giới hạn nhất quán; residency giới hạn vùng triển khai; tăng bảo mật làm thay đổi đường truy cập và vận hành.

Kiến trúc sư cần trình bày **lựa chọn và hậu quả**:

| Lựa chọn | Giá trị đạt được | Giá phải trả | Người quyết định |
|---|---|---|---|
| Duy trì SLA cao, tăng DR capacity | RTO/RPO có cơ hội đạt nếu diễn tập thành công | Replication, năng lực dự phòng, hạ tầng và vận hành | Business owner + Finance + SRE |
| Giữ ngân sách, thương lượng recovery dài hơn | Tối ưu chi phí nền | Rủi ro không phục vụ lâu hơn khi thảm họa | Business/risk owner |
| Ưu tiên checkout khi quá tải | Giữ hành trình tạo doanh thu | Có thể giảm gợi ý, tìm kiếm nâng cao, báo cáo | Product owner |
| Hoãn mở thị trường khi chưa đạt residency | Giảm rủi ro hợp đồng và dữ liệu | Trễ doanh thu/mục tiêu mở rộng | Chủ dự án và bộ phận pháp lý |
| Giữ monolith, tách worker theo tải | Ít đổi code nghiệp vụ, xử lý queue nhanh hơn | Không tách được mọi đường tải, vẫn cần quản lý DB | Architect + Engineering |

**Ràng buộc bắt buộc không thể tùy tiện đổi lấy lợi ích khác.** Nếu yêu cầu pháp lý hoặc hợp đồng đã xác minh không cho phép xử lý dữ liệu ở một vị trí, không được chọn phương án vi phạm chỉ vì có chi phí thấp hơn. Đưa phạm vi hợp pháp và mục tiêu kinh doanh ra thảo luận với người có thẩm quyền.

### 11.1. Lượng hóa chi phí mà không bịa dữ liệu

Có thể lập mô hình:

\[
C_{\text{total}} = C_{\text{compute}} + C_{\text{database}}
 + C_{\text{storage}} + C_{\text{network}} + C_{\text{observability}}
 + C_{\text{backup/DR}} + C_{\text{external}}
\]

Trong đó mỗi khoản cần công khai **số lượng tài nguyên, giờ sử dụng, dữ liệu truyền/lưu, đơn giá, vùng, quota, mô hình billing, sai số và dự phòng**. Ví dụ pre-scale trước flash sale làm tăng số replica-giờ, còn logging có thể tăng theo số request và kích thước event. Chi phí DR còn có replica, backup, replication traffic và thử khôi phục.

Không giả định chi phí tăng tuyến tính với RPS: cache có thể làm giảm DB load, network egress tăng theo payload, một số dịch vụ có đơn giá/tầng sử dụng khác nhau. Khi chưa có báo giá, ghi *unverified* và giao người xác minh, không gắn một con số chính xác giả.

### 11.2. Định lượng rủi ro

Một risk register hữu ích có thể gồm:

| Risk ID | Tình huống | Mức độ sơ bộ | Trigger | Mitigation / Owner |
|---|---|---|---|---|
| R-01 | DB pool đầy khi flash sale | Cao | Queue waits hoặc timeout tăng | Benchmark, giới hạn pool/connection, Data + SRE |
| R-02 | Không có vùng DR đáp ứng residency | Cao | Kiểm tra dịch vụ/region không đạt | Đưa lựa chọn hợp đồng/hạ tầng, Architect + Legal |
| R-03 | Payment callback trùng hoặc sai thứ tự | Cao | Đối soát sai hoặc duplicate | State machine, idempotency, Payment owner |
| R-04 | Scale quá mức và vượt ngân sách | Trung bình–cao | Replica/egress/log vượt ngưỡng | Quota, cost alerts, pre-approve cap, Finance/SRE |
| R-05 | Rollback ứng dụng phá compatibility dữ liệu | Cao | Schema migration không tương thích | Expand-contract, canary, rehearsal, Engineering |
| R-06 | Vi phạm SLO khi mất AZ | Cao | Fault drill lỗi hoặc failover chậm | Kiểm tra readiness, HA DB, SRE |

Các mức độ trên chỉ minh họa; môi trường thực nên áp dụng thang đánh giá rủi ro đã thống nhất và ghi rõ xác suất, ảnh hưởng, mức còn lại sau kiểm soát.

## 12. Kế hoạch chuyển đổi, nghiệm thu và rollback

Một phương án được duyệt vẫn có thể thất bại nếu rollout và dữ liệu chuyển tiếp không được thiết kế.

1. **Snapshot trạng thái gốc:** release, cấu hình, dependency, topology, lưu lượng, telemetry, dữ liệu và chi phí trước thay đổi.
2. **Xác minh giả thuyết quan trọng:** chạy PoC/benchmark với phạm vi cho phép; đo DB và gateway quota, DR và key access.
3. **Hợp đồng và dữ liệu:** data owner, schema version, migration, reconciliation, backfill, mô hình lỗi và tương thích.
4. **Canary hoặc traffic shift:** chuyển phần lưu lượng kiểm soát được, so sánh SLI và sự kiện nghiệp vụ giữa các phiên bản.
5. **Rollback gate:** định nghĩa ngưỡng lỗi, latency, dữ liệu sai, quá tải hoặc vượt trần chi phí khiến phải dừng.
6. **Điểm không thể đảo ngược:** xóa DB/khóa, migration không tương thích, thay đổi nguồn ghi; chỉ sau khi phê duyệt và có bằng chứng.
7. **Theo dõi sau thay đổi:** so sánh SLO, báo động, queue lag, dữ liệu giao dịch, chi phí và khả năng scale-in.

**Rollback không đơn thuần là đổi về container image cũ.** Khi phiên bản mới đã tạo dữ liệu theo schema mới, ứng dụng cũ có thể không hiểu được. Dùng phương pháp expand-and-contract và migration tương thích khi phù hợp; xác định rõ cách xử lý dữ liệu đã ghi sau cutover và trường hợp không thể rollback.

### 12.1. Mẫu gate có thể kiểm tra

~~~yaml
change_id: omniorder-flash-sale
status: proposed
business_owner: omniorder-product
technical_owner: platform-team
requirements:
  - CH-01
gates:
  workload_profile_reviewed: pending
  load_and_spike_test_passed: pending
  idempotency_reconciliation_passed: pending
  database_and_payment_quota_checked: pending
  security_review_passed: pending
  cost_ceiling_approved: pending
  rollback_drill_passed: pending
rollout:
  strategy: canary-then-progressive
  stop_on_slo_breach: true
  observation_window: "Theo change record"
evidence:
  adr: "ADR link"
  test_report: "Load test report link"
  runbook: "Rollback runbook link"
approvals:
  product: pending
  sre: pending
  security: pending
  finance: pending
~~~

Đây là biểu mẫu, **không phải tập lệnh tự triển khai**. Các trường pending cần được xác nhận bằng bằng chứng và người có thẩm quyền; hiện chưa đồng nghĩa được phép cutover.

## 13. Đánh giá lại bằng sáu trụ cột Well-Architected

| Trụ cột | Câu hỏi kiến trúc sư phải bảo vệ | Bằng chứng và đánh đổi |
|---|---|---|
| **Operational Excellence** | Đội có hiểu, giám sát, deploy, rollback và vận hành sau thay đổi không? | IaC, runbook, ADR, SLI, on-call; thêm dịch vụ làm tăng overhead |
| **Security** | Trust boundary và dữ liệu có được bảo vệ theo yêu cầu mới? | Threat model, IAM, encryption/key, data-flow, audit; cư trú hạn chế lựa chọn DR |
| **Reliability** | Lỗi instance/AZ/region và phụ thuộc ngoài ảnh hưởng hành trình ra sao? | Fault/DR drill, retry, idempotency, circuit breaker, RTO/RPO; dự phòng tăng chi phí |
| **Performance Efficiency** | Mở rộng đúng tài nguyên giới hạn và đạt p95/p99 thực tế? | Load/spike/soak, query waits, queue lag, autoscale timeline; cache có độ mới hữu hạn |
| **Cost Optimization** | Đạt SLO trong ngân sách và giảm công suất hợp lý sau đỉnh? | Cost per successful transaction, quota, egress, logs, DR; HA tạo chi phí nền |
| **Sustainability** | Có giảm tài nguyên nhàn rỗi, retry dư, truyền dữ liệu không cần thiết? | Right-size, scale-in, retention, workload efficiency, giảm xử lý lặp |

**Đạt có điều kiện** là kết luận hợp lệ nếu các điểm chưa có bằng chứng được chỉ rõ với owner và thời hạn. Nhưng nếu yêu cầu bắt buộc như cư trú dữ liệu hoặc tính đúng của thanh toán chưa xác minh, không được gắn nhãn đạt hoàn toàn.

## 14. Workshop thực hành: hội đồng kiến trúc

### 14.1. Vai trò và thời lượng

| Vai | Mối quan tâm chính |
|---|---|
| Cloud Architect | Phương án đích, giả định, trade-off, thay đổi kiến trúc |
| Product/Business Owner | Luồng doanh thu, trải nghiệm, ưu tiên, phạm vi và deadline |
| SRE/Platform | SLO, autoscaling, on-call, failover, rollback, chi phí vận hành |
| Security/Data Owner | Cư trú dữ liệu, phân quyền, mã hóa, audit, tính đúng đắn |
| Finance | Tổng chi phí, trần ngân sách, dự phòng theo tải |
| Reviewer | Tìm giả định yếu, xung đột và bằng chứng thiếu |

Nhóm 4–6 người có thể gộp một số vai; người học cá nhân viết cả phần phản biện lẫn câu trả lời. Thời lượng gợi ý **100 phút**: 15 phút làm rõ yêu cầu; 20 phút phác phương án; 15 phút bảo vệ; 10 phút nhận change request; 20 phút cập nhật; 15 phút review lần hai; 5 phút lập biên bản.

### 14.2. Hồ sơ người học phải nộp

1. **Requirement register** có ít nhất tám mã yêu cầu, ưu tiên, chủ sở hữu, điều kiện nghiệm thu và trạng thái xác minh.
2. **Sơ đồ ban đầu và sau thay đổi** có chú thích data owner, đường đồng bộ/bất đồng bộ, trust boundary và failure domain.
3. **Ma trận quyết định** so sánh ít nhất ba phương án, lý do chọn, hệ quả, điểm xem xét lại.
4. **Hai ADR**: quyết định ban đầu và quyết định được cập nhật bởi một change request.
5. **Impact analysis** của CH-01 và CH-02/CH-03 xuyên compute, network, data, security, DR, cost, operations.
6. **Verification plan**: load/spike, data reconciliation, fault/DR drill, security/cost review; có ngưỡng pass/fail.
7. **Risk register** ít nhất năm rủi ro, mức độ, owner, trigger và kế hoạch xử lý.
8. **Biên bản hội đồng**: phê duyệt, phê duyệt có điều kiện hoặc yêu cầu thiết kế lại, kèm lý do.

### 14.3. Thực hành theo ba vòng

**Vòng A — Bảo vệ phương án gốc:** Nhóm kiến trúc trình bày tình huống và A/B/C trong 10 phút. Reviewer truy từ mỗi tuyên bố “nhanh, tin cậy, rẻ, an toàn” tới tiêu chí đo hoặc bằng chứng cụ thể.

**Vòng B — Đối mặt với tải tăng tám lần:** Người điều phối công bố CH-01. Nhóm phải cập nhật bottleneck, capacity plan, chi phí, SLO, data flow và hậu quả nếu thanh toán chậm. Tăng số replica app là một giả thuyết, không phải bài giải hoàn chỉnh.

**Vòng C — Cư trú dữ liệu và DR nghiêm ngặt:** Người điều phối công bố CH-02/CH-03. Nhóm phải nêu rõ yếu tố chưa biết, phương án khả thi theo lãnh thổ, chi phí, kế hoạch thử RTO/RPO và quyết định kinh doanh cần xin. Trả lời chắc chắn khi chưa biết dịch vụ cloud hỗ trợ gì là lỗi thiết kế.

### 14.4. Thang đánh giá 100 điểm

| Tiêu chí | Điểm tối đa | Biểu hiện đạt |
|---|---:|---|
| Hiểu yêu cầu, nhận diện giả định và xung đột | 15 | Nêu rõ SLO–RTO và yêu cầu cư trú |
| Kiến trúc, data ownership và luồng xử lý | 15 | Sơ đồ đúng ngữ nghĩa, trạng thái và failure domain rõ |
| Lý do chọn, phương án thay thế, đánh đổi | 20 | Có căn cứ và trigger đổi quyết định |
| Phân tích và điều chỉnh khi requirement thay đổi | 20 | Impact analysis và ADR mới nhất quán |
| Kế hoạch đo kiểm, DR và rollback | 15 | Pass/fail, môi trường đại diện, chủ sở hữu bằng chứng |
| Chi phí, bảo mật, vận hành | 10 | Guardrail, quota, residency, on-call và cost model |
| Trình bày và phản biện | 5 | Trả lời thẳng, không che giấu giới hạn |
| **Tổng** | **100** | |

Thang này là công cụ học tập. Phương án khác ví dụ A vẫn có thể được điểm tối đa nếu đáp ứng yêu cầu, có bằng chứng phù hợp và giải thích rõ đánh đổi.

## 15. Bài tập tự luyện và hướng dẫn trả lời

### Bài tập 1: phát hiện lời hứa không có bằng chứng

Một thành viên nói: “Triển khai ba replica trên hai AZ và bật autoscaling là đạt 99,9% availability và xử lý được flash sale”.

**Yêu cầu:** Viết ba câu hỏi phản biện và hai phép kiểm chứng.

**Gợi ý:** hỏi DB, gateway và queue có failure domain nào; bao lâu replica mới sẵn sàng; 99,9% tính theo endpoint/request nào; capacity hạ nguồn là bao nhiêu. Kiểm chứng bằng fault drill một AZ và spike test đo p95, throughput nghiệp vụ, DB wait/queue lag. Replica nhiều không bảo đảm được phụ thuộc chung.

### Bài tập 2: RPO khác RTO như thế nào?

Khách hàng yêu cầu mất tối đa năm phút dữ liệu và phục hồi dịch vụ trong 30 phút sau sự cố toàn vùng. Nhóm chỉ có snapshot DB mỗi giờ và bản triển khai IaC.

**Yêu cầu:** Nhận xét giải pháp và đề xuất bằng chứng bổ sung.

**Gợi ý:** snapshot mỗi giờ thường không đủ chứng minh RPO năm phút; IaC dựng lại hạ tầng nhưng không tự khôi phục dữ liệu/giao dịch. Cần phương án replication/restore phù hợp, backup chain/key access, region hợp lệ, thử failover có đo giao dịch cuối được phục hồi và khả năng xử lý đơn/payment sau khi mở lại.

### Bài tập 3: đổi kiến trúc hay thương lượng mục tiêu?

Một lãnh thổ chỉ có lựa chọn hạ tầng không đáp ứng được RTO 30 phút trong ngân sách hiện tại, trong khi hợp đồng bắt buộc dữ liệu cư trú tại đó.

**Yêu cầu:** Soạn hai phương án gửi chủ nghiệp vụ.

**Gợi ý:** (a) tăng ngân sách hoặc đầu tư hạ tầng DR độc lập trong lãnh thổ hợp lệ, kèm PoC/DR drill và mốc quyết định; (b) thương lượng RTO/khung phục vụ hợp lệ hoặc giới hạn phạm vi sản phẩm nếu bên ký hợp đồng đồng ý. Tuyệt đối không chọn lưu dữ liệu ở vị trí bị cấm rồi coi như một rủi ro “đã chấp nhận”.

### Bài tập 4: báo cáo sau một phép đo không đạt

Trong bài spike, 320 lần checkout/s được gửi nhưng chỉ 180 lần/s hoàn tất; p95 1.600 ms, DB wait tăng, queue oldest age tăng liên tục, autoscaler đã tăng từ 4 lên 12 replica.

**Yêu cầu:** Bảo vệ một quyết định tiếp theo mà không đưa ra kết luận quá mức.

**Gợi ý:** Kết luận **chưa đạt** CH-01/Q-02 trong điều kiện test. Chưa đủ căn cứ cho rằng thiếu replica app, vì DB wait và queue lag chỉ ra khả năng bão hòa hạ nguồn. Cần đo DB pool/lock/IOPS, retry, achieved rate, thời gian xử lý queue và payment quota; thử tối ưu query/worker/giới hạn trước khi thay đổi topology. Cập nhật ADR và test lại cùng workload.

## 16. Ví dụ biên bản hội đồng sau hai thay đổi

Một kết quả thực hành có căn cứ có thể viết:

> Hội đồng **phê duyệt có điều kiện** kiến trúc modular monolith đa replica cho giai đoạn đầu. Trước cutover cần có kết quả load test Q-01, đối soát giao dịch, thử mất một AZ, security review và dự toán C-01. Đối với CH-01, nhóm thử pre-scale kết hợp cache đọc; nếu không đạt SLO trong trần chi phí thì trình phương án thay thế. Với CH-02/CH-03, hội đồng chưa phê duyệt cam kết cư trú dữ liệu hoặc RTO/RPO mới cho đến khi hoàn thành data-flow review, xác minh vùng/dịch vụ hợp lệ và DR drill. Product owner, Security/Data Owner và Finance chịu trách nhiệm xác nhận các ràng buộc kinh doanh và ngân sách.

Biên bản không tuyên bố dự án đã hoàn thành. Nó ghi **quyết định, điều kiện, việc chưa được chứng minh và trách nhiệm tiếp theo**. Khi kết quả thử nghiệm hoặc hợp đồng thay đổi, nhóm cập nhật trạng thái và hồ sơ trước khi phát hành.

## 17. Lỗi thường gặp

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| Trình bày công nghệ thay cho nhu cầu | Không biết khi nào phương án có giá trị | Truy từ business outcome đến quality attribute |
| “Cloud tự HA và autoscale” | Bỏ qua DB, quota, startup, lỗi vùng | Thiết kế failure domain, drill và load test |
| Chỉ trình bày một phương án | Không thấy trade-off và điều kiện đổi quyết định | Đưa lựa chọn thay thế đáng cân nhắc |
| Đổi tải mà chỉ tăng app replicas | DB/payment/queue vẫn nghẽn | Đo bottleneck xuyên hệ thống |
| Xem HTTP 202 là đơn thành công | Backlog tăng, khách chờ vô hạn | SLO cho outcome nghiệp vụ |
| Coi Multi-AZ là DR toàn vùng | Không đạt RTO/RPO sau sự cố region | Xác định phạm vi lỗi và diễn tập |
| Quên log, backup trong phạm vi cư trú | Dữ liệu nhạy cảm ra ngoài ràng buộc | Data inventory và data-flow end-to-end |
| Thay yêu cầu nhưng không cập nhật ADR | Hồ sơ và thiết kế lệch nhau | Traceability, versioning và review |
| Rollback chỉ đổi container image | Dữ liệu/schema mới không tương thích | Expand-contract, đối soát, kiểm thử rollback |
| Giấu thiếu hụt bằng chứng | Hội đồng ra quyết định trên giả định | Nhãn assumed/measured/approved/open |
| Hứa mọi yêu cầu với ngân sách cố định | Không nhận diện xung đột thật | Trình lựa chọn và chủ sở hữu quyết định |

## 18. Checklist trước khi bảo vệ lần cuối

- [ ] Yêu cầu nghiệp vụ có owner, độ ưu tiên, phạm vi, giả định và điều kiện nghiệm thu?
- [ ] Các mâu thuẫn như availability SLO so với RTO/RPO được phân tích rõ?
- [ ] Sơ đồ thể hiện entry point, dữ liệu authoritative, đường đồng bộ/bất đồng bộ, trust boundary và failure domain?
- [ ] Có ít nhất hai phương án thay thế, lý do chọn và điều kiện cần đổi?
- [ ] Đã xem xét compute, network, data, cache, queue, third-party, quota, bảo mật và chi phí khi tải thay đổi?
- [ ] Đã kiểm tra cư trú của database, log, trace, backup, snapshot, queue, analytics và các đối tác?
- [ ] Có phép đo workload đại diện, latency p95/p99, throughput nghiệp vụ, lỗi, retry, backlog và cost?
- [ ] Có fault/DR drill đo RTO và RPO thực, bao gồm khôi phục dữ liệu và nghiệp vụ?
- [ ] Có rollout, migration, compatibility, canary, rollback và gate cho thao tác không thể đảo ngược?
- [ ] ADR, risk register, requirement matrix, cost model, test plan và runbook cùng mô tả một quyết định hiện hành?
- [ ] Những điều chưa chứng minh được có người chịu trách nhiệm, hạn xác minh và phương án thay thế?
- [ ] Đã soát sáu trụ cột Well-Architected và nêu rõ đánh đổi ảnh hưởng đến doanh nghiệp?

## 19. Kết luận

**Bảo vệ phương án kiến trúc** là năng lực chuyển một sơ đồ thành quyết định có thể thẩm định: gắn yêu cầu với giải pháp, công khai đánh đổi, chỉ ra bằng chứng, nhận diện rủi ro và trả lời phản biện có trách nhiệm. **Điều chỉnh phương án khi yêu cầu thay đổi** là năng lực giữ vững các bất biến nghiệp vụ và ràng buộc bắt buộc, đồng thời sẵn sàng sửa cách triển khai, phân bổ dữ liệu, cấu hình hạ tầng, SLO và kế hoạch kiểm chứng khi cần.

Trong thiết kế ứng dụng cloud, không có một sơ đồ đúng cho mọi giai đoạn. Kiến trúc phù hợp phải **giải thích được vì sao đang đúng, đo được giới hạn của chính mình và có tiêu chí rõ để quyết định điều gì cần thay đổi**. Đó là cách cân bằng độ tin cậy, bảo mật, khả năng mở rộng, hiệu năng, chi phí, vận hành và tính bền vững theo tư duy Well-Architected.

# Những năng lực cần có trước khi vận hành hệ thống phân tán

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Tổng quan.  
> **Đối tượng:** Kiến trúc sư phần mềm, lập trình viên backend, platform engineer, SRE, tech lead và nhóm chuẩn bị đưa microservices lên môi trường production.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao hệ thống phân tán đòi hỏi năng lực vận hành khác ứng dụng chạy trong một tiến trình.
2. Nhận diện các nhóm năng lực cần chuẩn bị: thiết kế dịch vụ, dữ liệu, giao tiếp mạng, độ tin cậy, quan sát, bảo mật, hạ tầng, quy trình và con người.
3. Xác định bằng chứng cần có trước khi mở lưu lượng production.
4. Lập lộ trình xây năng lực theo quy mô và mức độ rủi ro, tránh áp dụng microservices chỉ vì xu hướng.

## 1. Bài toán thực sự khi hệ thống trở thành phân tán

Ở một ứng dụng đơn khối, lời gọi giữa các module thường diễn ra trong cùng tiến trình, có thể dùng chung transaction và một cơ chế triển khai. Với microservices, các thành phần có thể nằm ở máy khác nhau, triển khai độc lập, dùng kho dữ liệu riêng và giao tiếp qua mạng. Khi đó:

- **Mạng có thể lỗi từng phần:** service A còn hoạt động trong khi service B mất kết nối; timeout không chứng minh yêu cầu đã thất bại.
- **Độ trễ biến động:** một lời gọi bình thường 20 ms có thể tăng lên vài giây khi nghẽn mạng hoặc phụ thuộc phía sau.
- **Dữ liệu không đồng bộ tức thời:** các bản sao và các service có thể nhìn thấy trạng thái khác nhau trong một khoảng thời gian.
- **Lỗi lan truyền:** một dependency chậm có thể làm cạn connection pool, thread pool và gây nghẽn dây chuyền.
- **Thay đổi không diễn ra đồng thời:** phiên bản API/event cũ và mới cùng tồn tại trong một đợt triển khai.
- **Quan sát khó hơn:** một yêu cầu của người dùng có thể đi qua nhiều service; log tại một máy không đủ để tìm nguyên nhân.
- **Trách nhiệm bị phân tán:** nhiều nhóm cùng tham gia một luồng nghiệp vụ nhưng sự cố vẫn cần một đầu mối xử lý.

**Nguyên tắc thiết kế:** giả định lỗi sẽ xảy ra; định nghĩa hành vi của hệ thống khi phụ thuộc chậm, mất kết nối, trả kết quả không chắc chắn hoặc dữ liệu chưa hội tụ.

## 2. Bản đồ các năng lực cốt lõi

| Năng lực | Cần trả lời được | Bằng chứng tối thiểu |
|---|---|---|
| Ranh giới dịch vụ và ownership | Mỗi service chịu trách nhiệm nghiệp vụ nào? | Sơ đồ context, owner, API và dữ liệu sở hữu |
| Nền tảng hệ thống phân tán | Xử lý timeout, duplicate, partition và eventual consistency ra sao? | Các kịch bản lỗi và hành vi dự kiến |
| Hợp đồng giao tiếp | API/event tiến hóa thế nào mà không làm hỏng consumer? | Schema version, contract test, chính sách tương thích |
| Quản lý dữ liệu | Ai có quyền ghi? Giao dịch liên service được bảo đảm thế nào? | Data ownership, outbox/saga hoặc phương án thay thế |
| Độ tin cậy | Chậm, lỗi và quá tải được giới hạn tác động ra sao? | Timeout, retry có giới hạn, circuit breaker, load shedding |
| Quan sát hệ thống | Tìm được nguyên nhân của một request lỗi không? | Metrics, log, distributed trace và correlation ID |
| SLO và ứng cứu | Khi nào phải báo động, ai trực và xử lý theo runbook nào? | SLI/SLO, alert, on-call, runbook và diễn tập |
| Bảo mật | Service và người dùng được xác thực, phân quyền ra sao? | Identity, policy, secret rotation, audit trail |
| Hạ tầng và phát hành | Rollout, rollback, scale và cấu hình có tái lập được không? | CI/CD, IaC, health checks, rollout strategy |
| Khả năng khôi phục | Nếu mất node, vùng hoặc dữ liệu, khôi phục trong bao lâu? | Backup restore test, RTO/RPO, DR drill |
| Tổ chức và vận hành | Ai sở hữu chi phí, chất lượng và sự cố? | Service catalog, trách nhiệm, lịch trực, review định kỳ |
| Kiểm thử thực tế | Có bằng chứng hệ thống chịu được tải và lỗi kỳ vọng? | Load/soak/failover/chaos tests với kết quả lưu lại |

Bảng trên là khung đánh giá năng lực, không có nghĩa mọi hệ thống nhỏ đều cần ngay lập tức một nền tảng điều phối hoặc đội SRE riêng. Mức đầu tư phải tương ứng với mức ảnh hưởng khi dịch vụ lỗi.

## 3. Hiểu đúng các khái niệm phân tán trước khi chọn công nghệ

### 3.1. Partial failure, timeout và kết quả không xác định

Giả sử Order Service gửi yêu cầu trừ tiền đến Payment Service. Sau 2 giây, Order Service bị timeout. Có ít nhất ba khả năng:

1. Payment Service chưa nhận được yêu cầu.
2. Payment Service đã xử lý thành công, nhưng phản hồi thất lạc.
3. Payment Service vẫn đang xử lý và kết quả chưa biết.

Vì vậy, **timeout không đồng nghĩa với thất bại nghiệp vụ**. Nếu gọi lại không có cơ chế idempotency, khách hàng có thể bị trừ tiền hai lần. Thiết kế cần có khóa idempotency, trạng thái yêu cầu, khả năng tra cứu kết quả và quy trình đối soát.

### 3.2. Consistency, availability và network partition

Khi mất liên lạc giữa các node, hệ thống không thể bảo đảm mọi yêu cầu đều vừa có dữ liệu nhất quán mạnh vừa luôn được phục vụ. Quyết định phụ thuộc vào nghiệp vụ:

- Chốt số dư hoặc hạn mức: thường ưu tiên kiểm soát tính nhất quán để tránh chấp nhận giao dịch sai.
- Danh sách sản phẩm hoặc bộ đếm lượt xem: có thể chấp nhận dữ liệu chậm cập nhật trong thời gian ngắn.
- Kiểm tra tồn kho: cần làm rõ thời điểm giữ chỗ, trừ kho, hết hạn và bù trừ khi một bước thất bại.

**CAP không phải quy tắc chọn sẵn hai trong ba đặc tính cho mọi tình huống.** Câu hỏi thực tiễn là: khi partition thực sự xảy ra, từng thao tác sẽ từ chối, chờ, trả dữ liệu cũ hay tiếp tục với điều kiện nào?

### 3.3. Đồng hồ, thứ tự sự kiện và giao hàng lặp

Các node không có chung đồng hồ tuyệt đối. Timestamp từ hai service không đủ để suy ra thứ tự nhân quả nếu chưa xét đồng bộ đồng hồ và cơ chế phiên bản. Broker thường cung cấp lựa chọn về thứ tự trong từng partition, không bảo đảm thứ tự toàn cục.

Hệ thống nên có:

- Event ID duy nhất và business key ổn định.
- Version/sequence khi nghiệp vụ cần xử lý theo thứ tự.
- Consumer chịu được duplicate và replay.
- Quy ước UTC cho thời điểm lưu trữ, đồng thời phân biệt event time và processing time.
- Chính sách bỏ qua, lưu chờ hoặc xử lý lại sự kiện đến trễ.

Các nhãn “at least once”, “at most once” và “exactly once” cần hiểu theo phạm vi công nghệ cụ thể. **Không mặc định exactly-once end-to-end** qua database, broker và dịch vụ bên ngoài.

## 4. Thiết kế ranh giới dịch vụ và quyền sở hữu

### 4.1. Chia theo năng lực nghiệp vụ

Dùng domain modeling và bounded context để xác định vùng chịu trách nhiệm. Một dịch vụ hợp lý có mô hình nghiệp vụ tương đối rõ, dữ liệu do nó làm chủ, luồng thay đổi tương đối độc lập và một nhóm chịu trách nhiệm vận hành.

Tránh chia service theo từng bảng database hoặc từng lớp kỹ thuật như Controller Service, Validation Service, Repository Service. Kiểu chia này tạo thêm gọi mạng nhưng không mang lại quyền tự chủ.

Ví dụ trong thương mại điện tử:

- **Catalog:** thông tin sản phẩm, danh mục và trạng thái hiển thị.
- **Inventory:** tồn kho khả dụng, giữ chỗ và giải phóng giữ chỗ.
- **Order:** vòng đời đơn hàng, trạng thái đặt và huỷ.
- **Payment:** yêu cầu thanh toán, kết quả và đối soát.

Mỗi service định nghĩa ai được ghi dữ liệu, ai chỉ đọc qua API/event và ai xử lý sai lệch giữa các hệ thống.

### 4.2. Contract và tiến hóa phiên bản

Năng lực phải có trước production:

- Mô tả API bằng OpenAPI hoặc hợp đồng tương đương; event bằng schema có phiên bản.
- Quy định rõ mã lỗi, timeout kỳ vọng, pagination, giới hạn kích thước payload và idempotency.
- Áp dụng **expand → migrate → contract** với thay đổi dữ liệu/API: thêm trường tương thích, chuyển consumer, rồi mới bỏ trường cũ.
- Chạy contract tests giữa provider và consumer; kiểm tra phiên bản cũ/mới có thể hoạt động song song.
- Có chính sách deprecation công khai với owner và mốc thời gian; tránh đổi nghĩa trường đã phát hành.

Quy tắc: consumer không nên phụ thuộc vào trường chưa được cam kết; provider không được âm thầm thay đổi ý nghĩa của trường đang dùng.

### 4.3. Đồng bộ và bất đồng bộ

**Synchronous HTTP/gRPC** phù hợp khi caller cần kết quả ngay; đổi lại caller chịu độ trễ và tình trạng sẵn sàng của dependency.

**Asynchronous messaging** phù hợp với tác vụ có thể xử lý sau, thông báo sự kiện hoặc làm phẳng đỉnh tải; đổi lại phải quản lý duplicate, ordering, retry, dead-letter queue và độ trễ hội tụ dữ liệu.

Khi chọn cơ chế, ghi rõ: yêu cầu người dùng cần phản hồi trong bao lâu, hệ thống có thể chấp nhận dữ liệu cũ bao lâu, thất bại được khôi phục tự động hay thủ công, và ai sở hữu thông điệp lỗi tồn đọng.

## 5. Năng lực dữ liệu: transaction, idempotency và khôi phục trạng thái

### 5.1. Data ownership và transaction boundary

Mỗi service nên sở hữu logic ghi của dữ liệu nghiệp vụ mình quản lý. Không cho các service khác ghi trực tiếp vào bảng nội bộ chỉ vì dùng chung database; điều này làm mất ranh giới và khiến phát hành độc lập trở nên khó.

Transaction ACID trong một database có giới hạn rõ. Khi một giao dịch đi qua nhiều service, hãy chọn quy trình phù hợp:

- **Saga:** chia thành các bước cục bộ, có trạng thái điều phối/choreography và hành động bù trừ khi cần.
- **Transactional outbox:** ghi thay đổi nghiệp vụ và bản ghi sự kiện trong cùng transaction database; worker/CDC phát sự kiện sau đó.
- **Inbox/deduplication:** lưu ID thông điệp đã xử lý hoặc áp dụng cập nhật có điều kiện để chống phát lại.
- **Reconciliation:** định kỳ so sánh trạng thái giữa các bên, sửa trường hợp kết quả không chắc chắn.

Outbox giúp tránh lỗi “commit database thành công nhưng chưa gửi event”; tuy nhiên consumer vẫn cần chống duplicate vì việc phát lại có thể xảy ra.

### 5.2. Ví dụ luồng đặt hàng

~~~text
Client
  -> Order Service: Tạo đơn (Idempotency-Key)
  -> Order DB: Lưu PENDING + outbox OrderPlaced
  -> Broker: Phát OrderPlaced
  -> Inventory Service: Giữ hàng -> InventoryReserved / InventoryRejected
  -> Payment Service: Thu tiền -> PaymentSucceeded / PaymentFailed
  -> Order Service: Xác nhận COMPLETED hoặc xử lý bù trừ
~~~

Các câu hỏi phải được trả lời trước khi chạy thật:

1. Một sự kiện được gửi hai lần thì trạng thái có bị cập nhật sai không?
2. Giữ hàng thành công nhưng thanh toán thất bại thì ai giải phóng hàng?
3. Thanh toán thành công nhưng Order Service mất kết nối thì kiểm tra và đối soát bằng cách nào?
4. Người dùng gọi tạo đơn hai lần bằng cùng khóa idempotency thì hệ thống trả lại cùng kết quả ra sao?
5. Nếu một consumer ngừng trong 6 giờ, broker có còn giữ đủ sự kiện để chạy bù không?

### 5.3. Mô hình hợp đồng tối thiểu cho event

~~~json
{
  "eventId": "e6ac...",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "aggregateId": "order-4821",
  "occurredAt": "2026-11-11T09:30:00Z",
  "traceId": "6a1b...",
  "payload": {
    "orderId": "order-4821",
    "customerId": "customer-71"
  }
}
~~~

Đây là ví dụ minh họa, không phải quy ước bắt buộc cho mọi hệ thống. Nên xác định chính sách thông tin nhạy cảm trong payload, lịch sử schema, retention và cách replay trước khi chọn định dạng thực tế.

## 6. Kỹ thuật chống lỗi lan truyền

### 6.1. Timeout và deadline

Mọi lời gọi mạng cần có timeout có chủ đích. Phân biệt connection timeout, request/response timeout và deadline tổng của request. Timeout ở từng tầng phải phù hợp với ngân sách thời gian toàn luồng.

Ví dụ: mục tiêu hoàn thành một yêu cầu trong 800 ms. Nếu API Gateway dành 150 ms cho mạng/serializing và Order Service dành 150 ms cho xử lý cục bộ, phần còn lại cho các dependency chỉ khoảng 500 ms. Không nên để một dependency timeout 3 giây khi caller chỉ còn 500 ms.

Khi deadline hết, hủy tác vụ có thể hủy, giải phóng tài nguyên và trả kết quả rõ. Không tạo thêm retries tại mọi tầng mà thiếu ngân sách.

### 6.2. Retry, backoff, jitter và idempotency

Chỉ retry lỗi có khả năng phục hồi như network glitch hoặc phản hồi quá tải phù hợp. Dùng exponential backoff, jitter, giới hạn tổng số lần, deadline và retry budget.

Ví dụ minh họa:

~~~text
attempt 1: gọi dependency
attempt 2: chờ khoảng 100–200 ms (có jitter)
attempt 3: chờ khoảng 200–400 ms (có jitter)
sau deadline hoặc retry budget: dừng và trả kết quả phù hợp
~~~

Không retry mù lệnh tạo thanh toán, gửi email hoặc đặt hàng nếu thiếu idempotency. Nhiều tầng retry đồng thời có thể khuếch đại số request và làm dependency đang lỗi càng quá tải.

### 6.3. Các cơ chế cần biết

| Cơ chế | Mục đích | Điều cần tránh |
|---|---|---|
| Circuit breaker | Tạm ngắt gọi dependency đang lỗi để giảm lan truyền | Ngắt quá nhạy gây dao động |
| Bulkhead | Cô lập thread/connection/concurrency giữa các nhóm công việc | Dùng chung pool không có quota |
| Rate limiting | Giới hạn tốc độ request theo user/tenant/service | Không công bố hành vi khi vượt hạn mức |
| Load shedding | Bỏ có chọn lọc công việc kém ưu tiên khi quá tải | Xử lý mọi thứ đến khi toàn hệ thống sập |
| Bounded queue | Giới hạn số tác vụ chờ | Queue tăng vô hạn, chiếm hết RAM |
| Fallback | Cung cấp dữ liệu cũ/chế độ giảm chức năng khi hợp lý | Trả dữ liệu sai cho nghiệp vụ yêu cầu chính xác |
| Graceful shutdown | Ngừng nhận mới, xử lý/drain tác vụ đang chạy | Kill đột ngột làm thất lạc công việc |

**Chọn cơ chế bằng failure mode thực tế**, không lắp toàn bộ pattern lên mọi endpoint. Mỗi fallback phải được nghiệp vụ chấp nhận; ví dụ checkout không thể “giả thành công” khi chưa xác nhận thanh toán.

## 7. Quan sát: biết hệ thống đang xảy ra điều gì

Một service có endpoint health không có nghĩa toàn bộ hành trình người dùng đang ổn. Cần kết hợp ba loại tín hiệu:

### 7.1. Metrics và SLI/SLO

Với một API quan trọng, quan sát ít nhất: request rate, tỉ lệ lỗi, latency percentiles (p50/p95/p99), saturation của CPU/memory/thread/connection/queue, và thành công nghiệp vụ.

- **SLI:** phép đo thực tế, ví dụ tỉ lệ yêu cầu thanh toán hoàn tất hợp lệ.
- **SLO:** mục tiêu theo khoảng thời gian, ví dụ 99,9% request hợp lệ hoàn tất trong giới hạn đã định trong 30 ngày.
- **SLA:** cam kết với khách hàng, thường có hệ quả hợp đồng nếu vi phạm.
- **Error budget:** phần sai lệch được phép so với SLO, hỗ trợ quyết định tốc độ phát hành và đầu tư ổn định.

Một SLO cần mô tả rõ tập request được đo, công thức, cửa sổ thời gian và trường hợp loại trừ. Đặt alert dựa trên tác động người dùng và tốc độ tiêu hao error budget; tránh alert chỉ vì CPU cao nhất thời.

### 7.2. Log, trace và correlation

- **Structured logs:** JSON hoặc cấu trúc tương đương, có timestamp, service, environment, traceId, requestId và mã lỗi phù hợp.
- **Distributed tracing:** truyền ngữ cảnh qua HTTP/gRPC và message; xem được chuỗi span và nơi phát sinh độ trễ.
- **Correlation ID:** liên kết hành trình xuyên nhiều service, kể cả xử lý bất đồng bộ.
- **Telemetry hygiene:** thống nhất tên metrics và trace attributes; tránh label có cardinality vô hạn như userId trên mọi metric.
- **Dữ liệu nhạy cảm:** không ghi mật khẩu, token, thông tin thanh toán hoặc PII quá mức; quản lý quyền truy cập và thời gian lưu.

Công cụ có thể là OpenTelemetry cùng backend phù hợp, nhưng **chuẩn hóa instrumentation và khả năng truy vết** quan trọng hơn tên vendor.

### 7.3. Kiểm tra năng lực tìm lỗi

Thực hành tình huống: người dùng báo đơn hàng bị treo, chỉ cung cấp orderId và thời điểm xảy ra. Đội trực cần từ dashboard tìm request liên quan, lần theo trace, xác định dependency, xem event/queue state và quyết định khôi phục hay đối soát. Nếu phải đăng nhập thủ công từng máy và grep log không có correlation, chưa đủ năng lực vận hành phân tán ở quy mô lớn.

## 8. Nền tảng hạ tầng và phát hành

### 8.1. Chuẩn môi trường chạy

Có thể dùng VM, container hoặc orchestrator. Dù chọn gì, cần nhất quán về:

- **Service discovery/DNS:** service tìm nhau qua tên ổn định, không hard-code IP.
- **Cấu hình:** phân tách môi trường, kiểm soát thay đổi và bí mật; cấu hình có thể truy xuất nguồn gốc.
- **Health probes:** phân biệt liveness (tiến trình cần restart?), readiness (có nhận traffic mới được?) và startup cho ứng dụng khởi động lâu.
- **Resource limits:** request/limit CPU-memory, quota kết nối và concurrency, cơ chế tránh OOM và overload.
- **Autoscaling:** dựa trên tín hiệu sát tải thực; kiểm soát độ trễ scale-up và ảnh hưởng đến dependency.
- **Network policy:** chỉ mở luồng giao tiếp cần thiết; kiểm soát ingress/egress, DNS và TLS.
- **Infrastructure as Code:** hạ tầng định nghĩa bằng mã, có review, version và khả năng dựng lại.

Kubernetes giúp điều phối nhưng không tự sửa thiết kế transaction, idempotency, contract hay tổ chức on-call. Không cần chọn Kubernetes khi đội chưa có năng lực quản trị nó và quy mô chưa đòi hỏi.

### 8.2. CI/CD, rollout và rollback

Pipeline tối thiểu nên chạy build, unit/integration/contract tests, quét dependency và image, tạo artifact có phiên bản bất biến, rồi triển khai có kiểm soát.

Các chiến lược cần hiểu:

- **Rolling deployment:** thay phiên instance, yêu cầu khả năng tương thích giữa hai phiên bản.
- **Canary:** đưa một phần nhỏ traffic sang phiên bản mới và theo dõi SLI.
- **Blue-green:** duy trì hai môi trường, chuyển traffic khi đạt tiêu chí.
- **Feature flag:** tách bật tính năng khỏi deploy, nhưng phải có owner và hạn dọn cờ.

Rollback ứng dụng không đồng nghĩa rollback được schema hay dữ liệu. Vì thế migration nên tương thích ngược qua nhiều lần phát hành và có kế hoạch phục hồi dữ liệu nếu lỗi.

### 8.3. Năng lực capacity planning

Biết đo tải thật và dự đoán đỉnh theo request/giây, fan-out, kích thước payload, số connection, queue lag và tốc độ tăng dữ liệu. Một user request gọi 5 dependency không đồng nghĩa backend chỉ chịu 1 request. Cần làm rõ concurrency, headroom và giới hạn quota nhà cung cấp.

Thực hiện load test, stress test và soak test với mô hình lưu lượng đại diện; theo dõi cả throughput lẫn p95/p99 latency và tỉ lệ lỗi. Chỉ dùng số liệu đã đo để đặt capacity target.

## 9. Bảo mật và quyền truy cập xuyên service

Mỗi service là một biên an ninh mới. Tối thiểu cần:

1. **Identity:** xác thực người dùng ở cạnh hệ thống và xác thực workload/service khi giao tiếp nội bộ.
2. **Authorization:** kiểm tra quyền tại service nắm nghiệp vụ, không tin rằng API Gateway đã kiểm tra đủ.
3. **Least privilege:** tài khoản, service account, database role và message topic chỉ cấp quyền cần thiết.
4. **Secret management:** cất token/key trong secret manager; có lịch rotation và quy trình thu hồi.
5. **Encryption:** TLS cho giao tiếp phù hợp, mã hóa dữ liệu lưu khi cần; quản lý chứng chỉ và vòng đời khóa.
6. **Supply chain:** scan dependency, image, quản lý SBOM nếu phù hợp, ký artifact và hạn chế quyền pipeline.
7. **Audit:** ghi lại hoạt động quan trọng, ai thay đổi cấu hình, ai truy cập dữ liệu nhạy cảm, ai thực hiện thao tác khôi phục.
8. **Threat modeling:** xem xét giả mạo service, leo thang quyền, rò rỉ token, replay event và giả mạo webhook.

Ví dụ: dù gateway xác thực JWT, Inventory Service vẫn cần kiểm tra Order Service có quyền gửi lệnh reserve hay không, đồng thời chống replay/duplicate theo contract nghiệp vụ.

## 10. Vận hành sự cố và khôi phục

### 10.1. Incident response phải có người chịu trách nhiệm

Trước production, xác định rõ:

- On-call primary/secondary, lịch trực và kênh escalation.
- Severity theo ảnh hưởng người dùng/doanh thu, không theo mức độ ồn của log.
- Runbook cho các tình huống phổ biến: database đầy, queue backlog, dependency timeout, deployment lỗi, cert hết hạn, hết quota, dữ liệu sai lệch.
- Quyền dừng rollout, giảm traffic, disable feature, scale có kiểm soát, restore backup và rollback.
- Incident commander/đầu mối phối hợp nếu sự cố liên quan nhiều nhóm.
- Postmortem tập trung tìm nguyên nhân hệ thống và hành động phòng ngừa có owner, deadline.

Một alert tốt chỉ đúng người, có mô tả triệu chứng/tác động, dashboard hoặc truy vấn, tài liệu xử lý, và điều kiện xác nhận đã phục hồi.

### 10.2. RTO, RPO, backup và disaster recovery

- **RTO (Recovery Time Objective):** thời gian khôi phục chấp nhận được.
- **RPO (Recovery Point Objective):** lượng dữ liệu có thể mất tối đa đo theo thời gian.
- **Backup:** có lịch, mã hóa, kiểm soát truy cập và chính sách giữ bản sao.
- **Restore test:** phục hồi vào môi trường tách biệt và kiểm chứng dữ liệu/ứng dụng thực sự dùng được.
- **Failover drill:** diễn tập mất node, broker, database primary hoặc một vùng hạ tầng theo mức độ rủi ro.

Có backup nhưng chưa restore thử thì **chưa có bằng chứng khôi phục**. Cần ghi lại thời gian khôi phục đo được và mức mất dữ liệu thực tế so với RTO/RPO.

### 10.3. Diễn tập lỗi trước sự cố thật

Bắt đầu từ môi trường kiểm thử, sau đó tăng mức sát production khi đã có giới hạn ảnh hưởng, tiêu chí dừng và người chịu trách nhiệm. Kịch bản tiêu biểu: một pod chết, dependency tăng latency, broker tạm mất kết nối, mất một replica, DNS sai cấu hình, consumer bị poison message. Quan sát xem timeout, retry, alert, runbook và dữ liệu khôi phục có hoạt động như thiết kế hay không.

## 11. Năng lực tổ chức: con người mới vận hành hệ thống

Phân tán kỹ thuật thường kéo theo phân tán trách nhiệm. Một kiến trúc chỉ sẵn sàng khi đội biết ai quyết định và ai xử lý:

- **Service owner:** nhóm sở hữu từ thiết kế, phát hành đến vận hành và chi phí.
- **Service catalog:** mô tả purpose, upstream/downstream dependencies, API, dashboard, repository, on-call, SLO và hướng dẫn khôi phục.
- **Platform enablement:** cung cấp mẫu CI/CD, observability, secret, network, runtime và “paved road” để các đội không tự giải quyết lại mọi vấn đề.
- **Change management:** review thay đổi contract và migration giữa service; có quy tắc tương thích.
- **Incident learning:** chia sẻ bài học sự cố, cập nhật runbook và theo dõi hành động cải thiện.
- **Cost ownership:** xem chi phí tài nguyên, hạ tầng quan sát, message broker, lưu trữ log/trace và traffic giữa vùng.

Conway's Law nhắc rằng cấu trúc giao tiếp của tổ chức ảnh hưởng cấu trúc hệ thống. Nếu nhiều nhóm phải đồng bộ lịch deploy cho mọi thay đổi nhỏ, ranh giới service có thể chưa phù hợp hoặc hợp đồng giữa các đội chưa đủ tốt.

## 12. Bộ tiêu chí sẵn sàng đưa một luồng nghiệp vụ lên production

Dùng bảng này cho **một luồng quan trọng cụ thể** (ví dụ tạo đơn hàng), không chỉ đánh dấu chung cho toàn hệ thống. Mỗi tiêu chí phải có bằng chứng liên kết được.

| Nhóm | Câu hỏi kiểm tra | Bằng chứng chấp nhận |
|---|---|---|
| Nghiệp vụ | Nếu một bước thất bại, trạng thái cuối và người chịu trách nhiệm là gì? | State diagram, kịch bản bù trừ và owner |
| Ranh giới | Service nào sở hữu dữ liệu và API của từng bước? | Context map, service catalog |
| Contract | Consumer cũ còn chạy được sau một deploy mới không? | Contract/integration test qua hai phiên bản |
| Duplicate | Retry hoặc replay có làm phát sinh giao dịch trùng không? | Idempotency test và test duplicate event |
| Partial failure | Khi một dependency timeout/mất kết nối, caller làm gì? | Test lỗi, deadline và fallback đã định |
| Tải | Đỉnh lưu lượng dự kiến có đạt SLO không? | Load/soak test và thông số headroom |
| Observability | Có thể truy vết một giao dịch từ đầu đến cuối? | Dashboard, trace mẫu, log liên quan |
| Alerting | Đội trực được báo khi người dùng bị ảnh hưởng? | SLO alert test, routing và runbook |
| Bảo mật | Quyền service và secret được kiểm soát? | Review quyền, token rotation, audit |
| Phát hành | Nếu canary lỗi hoặc migration không tương thích sẽ làm gì? | Rollback/roll-forward rehearsal |
| Dữ liệu | Backup và đối soát khôi phục đã kiểm thử? | Restore report, replay/reconciliation test |
| Con người | Ai trực, ai quyết định rollback, ai báo khách hàng? | On-call roster, escalation, incident drill |

**Cách kết luận:** dùng các trạng thái “Đạt / Chưa đạt / Không áp dụng” kèm đường dẫn bằng chứng và người chịu trách nhiệm. Với tiêu chí “Chưa đạt”, hoặc xử lý trước khi phát hành, hoặc ghi rõ quyết định chấp nhận rủi ro có người phê duyệt và phương án giảm tác động. Đây là cổng vận hành kỹ thuật, không thay thế quy trình phê duyệt riêng của doanh nghiệp.

## 13. Lộ trình xây năng lực theo mức độ trưởng thành

### Giai đoạn A — Nền tảng trước khi tách dịch vụ

- Có lý do nghiệp vụ rõ để tách: quy mô đội, nhu cầu triển khai độc lập, ranh giới domain hoặc yêu cầu scale khác nhau.
- Bắt đầu bằng modular monolith nếu đội chưa sẵn sàng chịu chi phí phân tán.
- Chuẩn hóa CI/CD, metrics/logging, quản lý cấu hình, database migration, backup, owner và on-call.
- Đo baseline throughput, latency, error rate và chi phí của ứng dụng hiện tại.

**Điều kiện chuyển giai đoạn:** đã chỉ ra bottleneck hoặc nhu cầu tự chủ cụ thể; có mô hình domain và năng lực vận hành tối thiểu.

### Giai đoạn B — Một vài service với đường đi đơn giản

- Tách một bounded context có ownership rõ, giới hạn fan-out và shared database.
- Chuẩn hóa API contract, timeout, tracing, health checks và deploy pipeline.
- Có idempotency cho thao tác sinh tác dụng phụ, phương án đối soát và runbook cơ bản.
- Thử nghiệm mất kết nối và rollback trên luồng đó.

**Điều kiện chuyển giai đoạn:** đội tự phát hiện, chẩn đoán và khôi phục được lỗi điển hình mà không phụ thuộc vào một cá nhân duy nhất.

### Giai đoạn C — Nhiều service, traffic và thay đổi cao

- Bổ sung messaging, outbox, schema governance, tự động kiểm tra tương thích khi nhu cầu thực tế xuất hiện.
- Đo SLO end-to-end, dự toán capacity, áp dụng rollout theo tín hiệu.
- Thiết lập service catalog, ownership, observability tiêu chuẩn và quản trị chi phí.
- Diễn tập incident và phục hồi định kỳ; giảm công việc thủ công bằng nền tảng dùng chung.

**Điều kiện duy trì:** phát hành độc lập nhưng vẫn giữ SLO, khôi phục được sự cố và có bằng chứng kiểm soát rủi ro/chi phí.

## 14. Các sai lầm thường gặp và cách điều chỉnh

**“Triển khai Kubernetes là đã sẵn sàng microservices.”**  
Orchestrator giải quyết một phần vòng đời workload; vẫn cần data consistency, idempotency, observability, security và trách nhiệm vận hành. Giải pháp: lập tiêu chí năng lực theo hành trình nghiệp vụ.

**“Mọi lời gọi lỗi đều retry ba lần.”**  
Retry có thể nhân tải và nhân tác dụng phụ. Giải pháp: phân loại lỗi, giới hạn tổng deadline, dùng jitter và bảo vệ thao tác bằng idempotency.

**“Có hàng đợi thì hệ thống luôn bất đồng bộ, không còn phụ thuộc.”**  
Consumer vẫn có thể chậm, broker có thể đầy, backlog tăng và dữ liệu chưa hội tụ. Giải pháp: theo dõi queue lag, DLQ, retention, replay và capacity; thiết kế hành vi khi sự kiện trễ.

**“Chỉ cần log đầy đủ.”**  
Log rời rạc khó nối thành một hành trình; log quá chi tiết còn tăng chi phí và nguy cơ lộ dữ liệu. Giải pháp: trace propagation, metric SLO, log có cấu trúc và chính sách nhạy cảm.

**“Mỗi service có database riêng thì dữ liệu sẽ tự nhất quán.”**  
Dữ liệu phân tán cần thiết kế hành vi giao dịch, trễ và bù trừ. Giải pháp: phân định owner, áp dụng outbox/saga khi phù hợp và đối soát.

**“Chỉ cần autoscaling để xử lý quá tải.”**  
Scale thêm có thể dồn áp lực lên database hoặc dependency hữu hạn. Giải pháp: capacity test, limit concurrency, backpressure, rate limiting và hiểu giới hạn hệ thống.

**“Nhiều service luôn tốt hơn modular monolith.”**  
Phân tán tăng chi phí mạng, triển khai, bảo mật, giám sát và phối hợp. Giải pháp: chứng minh lợi ích tách ranh giới so với chi phí vận hành, ưu tiên kiến trúc đơn giản đủ đáp ứng yêu cầu.

## 15. Bài tập thực hành: diễn tập sự cố đặt hàng

**Bối cảnh:** hệ thống gồm API Gateway, Order Service, Inventory Service, Payment Service và broker. Đơn hàng mới được tạo, hàng đã giữ chỗ, nhưng Payment Service phản hồi chậm.

**Nhiệm vụ:**

1. Vẽ sequence diagram cho happy path và hai đường lỗi: timeout trước khi thanh toán, timeout sau khi thanh toán đã thành công.
2. Chỉ rõ idempotency key của tạo đơn và thanh toán; mô tả trạng thái đơn khi kết quả payment chưa xác định.
3. Đề xuất deadline tổng, timeout từng hop, số retry tối đa và cách giảm retry storm.
4. Định nghĩa ít nhất ba SLI: tỉ lệ tạo đơn hợp lệ thành công, p95 thời gian tạo đơn, độ tuổi lớn nhất của payment chưa được đối soát.
5. Chọn metric, log field và trace context để tìm được một đơn lỗi trong vòng vài phút.
6. Viết runbook cho tình huống backlog tăng, Payment Service lỗi 5xx và database Order Service mất một replica.
7. Thử duplicate event, consumer restart và replay; đối chiếu trạng thái đơn, thanh toán và giữ hàng.
8. Diễn tập rollback một phiên bản Order Service trong khi consumer đang chạy hợp đồng event cũ.

**Kết quả cần nộp:** sơ đồ kiến trúc/sequence, bảng failure modes, hợp đồng API/event, dashboard mẫu, runbook, báo cáo test và danh sách rủi ro còn mở. Thành công được đo bằng hành vi khi lỗi và khả năng khôi phục đã chứng minh, không chỉ ở việc tất cả container đang ở trạng thái Running.

## 16. Câu hỏi tự kiểm tra

1. Vì sao timeout không chứng minh một thao tác đã thất bại? Phân biệt retry an toàn và retry gây trùng tác dụng phụ.
2. Khi nào eventual consistency chấp nhận được, và đâu là điểm nghiệp vụ cần consistency mạnh?
3. Vì sao transactional outbox không loại bỏ nhu cầu idempotency của consumer?
4. Cần những telemetry nào để truy vết một request đi qua HTTP và broker?
5. SLI, SLO, SLA và error budget khác nhau ở điểm nào?
6. Rollback ứng dụng có giải quyết được mọi lỗi migration database không?
7. Vì sao autoscaling, rate limiting và backpressure bổ trợ nhau?
8. Có backup rồi thì cần bằng chứng gì mới dám công bố RTO/RPO?
9. Điều gì cho thấy ranh giới service đang khiến các đội bị buộc deploy cùng nhau?
10. Trong trường hợp nào giữ modular monolith là quyết định tốt hơn?

## Kết luận

Vận hành hệ thống phân tán là khả năng **dự đoán và kiểm soát lỗi từng phần, giữ đúng bất biến nghiệp vụ, phát hiện tác động tới người dùng, khôi phục nhanh và học từ sự cố**. Trước khi mở rộng microservices, hãy chứng minh các năng lực đó trên một luồng nghiệp vụ thật: owner rõ, contract tương thích, dữ liệu có quy tắc, timeout/retry an toàn, quan sát được, có SLO, trực xử lý và phục hồi đã diễn tập. Công nghệ chỉ có giá trị khi đội ngũ có thể duy trì các cam kết này trong vận hành thường ngày.

## Tài liệu đọc thêm

- Google, *Site Reliability Engineering* và *The Site Reliability Workbook*: https://sre.google/books/
- Google Cloud, *Reliability patterns*: https://cloud.google.com/architecture
- AWS, *Well-Architected Reliability Pillar*: https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/
- Microsoft, *Cloud Design Patterns*: https://learn.microsoft.com/azure/architecture/patterns/
- OpenTelemetry, tài liệu instrumentation và trace context: https://opentelemetry.io/docs/
- CNCF, tài liệu về hệ sinh thái cloud native: https://www.cncf.io/
# Đo mức sử dụng, chi phí và chất lượng dịch vụ theo tenant

## Mục tiêu học tập

Trong kiến trúc đa khách hàng (*multi-tenant architecture*), nhiều tenant cùng sử dụng một nền tảng ứng dụng, compute, database, network và dịch vụ dữ liệu. Việc dùng chung tài nguyên giúp tăng hiệu quả và giảm chi phí nền tảng, nhưng cũng đặt ra một câu hỏi quan trọng: **mỗi tenant đang sử dụng bao nhiêu tài nguyên, tạo ra chi phí nào và nhận được chất lượng dịch vụ ra sao?**

Nếu chỉ đo CPU, memory hoặc tổng request ở cấp cluster, đội vận hành khó biết tenant nào đang tạo tải, tenant nào bị ảnh hưởng, chi phí nên phân bổ cho ai và liệu một tenant có đang chiếm tài nguyên của tenant khác hay không. Nếu chỉ đếm request, hệ thống cũng có thể tính sai vì một request tìm kiếm nhẹ và một request tạo báo cáo lớn tiêu thụ tài nguyên rất khác nhau.

Bài học này trình bày cách thiết kế hệ thống **tenant metering, cost allocation và quality of service (QoS)** từ lúc xác định đơn vị đo đến thu thập, tổng hợp, giới hạn và cung cấp dữ liệu cho vận hành hoặc tính phí. Nội dung bao gồm usage dimensions, attribution, quota, fairness, noisy-neighbor, SLI/SLO theo tenant, showback/chargeback và kiểm soát tính đúng đắn của số liệu.

Sau bài học, bạn có thể:

- Xác định tenant identity đáng tin cậy và gắn tenant context xuyên request, worker, event và data pipeline.
- Chọn đơn vị đo phản ánh tài nguyên thực tế thay vì chỉ đếm request.
- Thiết kế usage events, meter aggregation, idempotency và correction.
- Phân biệt metering, billing, cost allocation, showback và chargeback.
- Phân bổ chi phí dùng chung theo driver có thể giải thích và kiểm toán.
- Thiết kế quota, rate limit, concurrency limit, fairness và admission control.
- Phát hiện và giảm tác động noisy-neighbor trong compute, database, storage và network.
- Định nghĩa SLI/SLO và error budget riêng theo tenant hoặc service tier.
- Xây dashboard, cảnh báo, audit trail và quy trình đối soát.
- Đánh giá bảo mật, quyền riêng tư, độ chính xác và TCO theo nguyên tắc Well-Architected.

## 1. Vì sao phải đo theo tenant?

Giả sử một nền tảng SaaS phục vụ 2.000 doanh nghiệp. Họ dùng chung API, database cluster, object storage, queue và worker fleet. Trong một giờ, tổng request tăng gấp đôi. Dashboard cấp hệ thống cho thấy CPU tăng và p95 latency xấu đi, nhưng không trả lời được:

- Tenant nào tạo phần lớn tải tăng?
- Tải đến từ API nào, job nào hoặc tính năng nào?
- Tenant bị giới hạn có đang tiêu thụ ít tài nguyên hơn do quota hay bị ảnh hưởng bởi tenant khác?
- Chi phí tăng do compute, database, storage, egress hay log?
- Tenant trả gói Enterprise có nhận được SLO đã cam kết không?
- Có thể tính usage công bằng mà không tính lặp khi request retry hay event được giao lại không?

Tenant-level metering giúp đưa hoạt động kỹ thuật về ngữ cảnh hợp đồng và nghiệp vụ. Nó hỗ trợ capacity planning, phát hiện lạm dụng, tối ưu chi phí, thiết kế gói dịch vụ và xử lý tranh chấp hóa đơn.

### 1.1. Tenant usage không đồng nghĩa tenant cost

Usage là lượng tài nguyên hoặc hoạt động được đo. Cost là giá trị tiền tệ được phân bổ theo một mô hình chi phí. QoS là chất lượng dịch vụ tenant trải nghiệm.

Một tenant có số request cao chưa chắc tạo chi phí cao nhất nếu request chủ yếu được cache. Một tenant có ít request có thể tạo nhiều chi phí nếu mỗi request chạy truy vấn lớn, xử lý file nhiều GB hoặc truyền dữ liệu ra Internet.

Tương tự, cost thấp không có nghĩa QoS tốt. Tenant có thể bị throttling nhiều nên usage và cost thấp nhưng trải nghiệm rất kém.

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Usage / metering | Tenant đã dùng bao nhiêu? | 1,2 triệu API units, 80 GB storage |
| Cost allocation | Chi phí nền tảng được phân bổ thế nào? | 4,5 triệu VND compute/storage |
| Billing | Tenant phải trả bao nhiêu theo hợp đồng? | Gói cố định + vượt mức |
| QoS | Tenant nhận chất lượng nào? | API p95 180 ms, availability 99,95% |
| Fairness | Tài nguyên có được phân phối hợp lý? | Một tenant không chiếm toàn bộ worker |
| Entitlement | Tenant được phép dùng gì? | 500 request/s, 100 GB storage |

## 2. Xác định tenant identity trước khi đo

Metering sai tenant thường nguy hiểm hơn thiếu metric, vì số liệu có thể dẫn tới hóa đơn sai, quota sai hoặc lộ dữ liệu tenant khác.

### 2.1. Không tin tenant ID do client tự khai

Tenant identity phải được xác định từ nguồn tin cậy, chẳng hạn:

- Claim đã được xác thực trong token hoặc session.
- API key được ánh xạ sang tenant trong registry.
- Mapping từ customer/account đến tenant đã được server xác minh.
- Service identity cho background job hoặc tích hợp hệ thống.
- Tenant context được lưu trong job/event do hệ thống phát hành.

Không nhận một header tenant tùy ý từ Internet rồi dùng trực tiếp làm billing dimension. Gateway hoặc application phải xác thực caller và xác minh caller có quyền truy cập tenant được yêu cầu.

### 2.2. Tenant context xuyên suốt luồng xử lý

Một request có thể tạo event, job nền hoặc task batch. Context cần đi theo công việc để usage của bước sau vẫn được quy về tenant khởi tạo, nhưng worker phải kiểm tra tính toàn vẹn và quyền xử lý của context.

~~~mermaid
flowchart LR
    C["Client"] --> G["Gateway / Authentication"]
    G --> A["Tenant context resolver"]
    A --> API["Tenant-aware API"]
    API --> DB[("Tenant data")]
    API --> E["Usage / business event"]
    E --> Q[("Queue")]
    Q --> W["Background worker"]
    W --> M["Usage meter"]
    API --> M
    M --> U[("Usage ledger")]
~~~

Context thường có tenantId, requestId, correlationId, service, operation, plan/tier và resource scope. Tránh đưa PII hoặc secret vào metric label. Với event/job, ghi tenant identifier theo schema ổn định và có chữ ký/nguồn phát hành tin cậy nếu luồng đi qua vùng không tin cậy.

### 2.3. Tenant context trong multi-tenant database

Nếu database dùng shared schema có tenant_id, mọi truy vấn tenant-scoped phải áp dụng filter hoặc row-level security phù hợp. Usage aggregation cũng phải tách theo tenant. Kiểm thử cả query raw, report, export, cache key và background job; một pipeline metering thiếu tenant filter có thể cộng dữ liệu của nhiều khách vào cùng một account.

### 2.4. Thay đổi tenant ownership

Tenant có thể đổi gói, chuyển chủ sở hữu, hợp nhất hoặc tách tenant. Cần lưu effective time và lịch sử mapping. Không sửa ngược lịch sử usage sang owner mới mà không có policy. Billing period phải biết tenant, account, subscription và plan nào có hiệu lực tại thời điểm usage được phát sinh.

## 3. Thiết kế taxonomy và đơn vị đo

### 3.1. Phân loại usage dimensions

Có thể chia metering thành nhiều nhóm:

| Nhóm | Dimension ví dụ | Đơn vị |
| --- | --- | --- |
| API | Request count, request class, API units | request, unit |
| Compute | Function duration, CPU time, vCPU-second, GB-second | second, GB-second |
| Database | Query count, rows read/written, DB compute, connection time | query, row, unit-second |
| Storage | Logical bytes, physical bytes, object count, request count | byte, GB-month, operation |
| Network | Ingress, egress, cross-region transfer | byte, GB |
| Messaging | Message count, message size, queue storage, delivery attempts | message, byte, operation |
| Analytics | Data scanned, query runtime, slot/warehouse time | GB scanned, second |
| AI/processing | Tokens, image pages, processing units | token, page, unit |
| Support | Backup retention, export, audit retention | GB-month, job |

Không phải dimension nào cũng nên tính phí. Có dimension dùng để tối ưu nội bộ hoặc bảo vệ hệ thống; có dimension được đưa vào hợp đồng. Phải định nghĩa rõ loại nào là metering, loại nào là billing meter và loại nào chỉ là operational metric.

### 3.2. Chọn đơn vị có quan hệ với tài nguyên

Request count dễ thu thập nhưng không phản ánh độ nặng. Một cách tốt hơn là phân loại request thành operation classes:

- Read-small: truy vấn một record hoặc metadata.
- Read-large: search, export hoặc query nhiều dòng.
- Write: tạo/cập nhật dữ liệu.
- Compute-heavy: tạo báo cáo, xử lý file, tính toán.
- External-transfer: truyền dữ liệu lớn hoặc cross-region.

Có thể gán weighted units dựa trên benchmark, nhưng trọng số phải được kiểm chứng và công bố rõ nếu dùng để tính phí. Không tự đặt mỗi request nặng là 10 units chỉ vì cảm giác; hãy đo CPU time, data scanned, duration hoặc chi phí phụ thuộc.

### 3.3. Phân biệt logical usage và provider cost

Ví dụ tenant lưu 50 GB logical data. Sau replication, versioning, compression hoặc backup, provider có thể tính phí trên physical storage cao hơn hoặc thấp hơn 50 GB. Logical usage phục vụ product limit; physical consumption phục vụ cost allocation. Hai số này cần được đặt tên riêng.

Tương tự:
- API request count là đơn vị sản phẩm.
- Egress bytes là tài nguyên cloud.
- Function GB-second là provider meter.
- Database connection-seconds có thể là usage nội bộ nhưng không nhất thiết là đơn vị billing của DB managed service.

### 3.4. Định nghĩa grain của usage record

Một usage record nên có grain rõ ràng, ví dụ một operation đã hoàn tất, một usage interval cho một resource, hoặc một snapshot storage theo giờ. Nếu không định nghĩa grain, aggregation có thể đếm request một lần ở API và thêm một lần ở worker dù đó là cùng một business operation.

## 4. Usage event và metering pipeline

### 4.1. Cấu trúc usage event

Ví dụ một usage event:

~~~json
{
  "usage_event_id": "usage-7f4a",
  "tenant_id": "tenant-42",
  "account_id": "account-18",
  "subscription_id": "sub-2026-08",
  "meter_name": "report_compute",
  "quantity": 12.5,
  "unit": "GB_SECOND",
  "operation_id": "report-run-991",
  "resource_id": "job-991",
  "occurred_at": "2026-11-18T09:15:00Z",
  "recorded_at": "2026-11-18T09:15:03Z",
  "service": "report-worker",
  "region": "ap-southeast-1",
  "meter_version": 2,
  "source": "worker-completion"
}
~~~

Đây là schema minh họa. Số lượng, đơn vị và meter version phải có định nghĩa rõ. Không dùng floating point tùy tiện cho tiền; usage decimal nên lưu precision phù hợp hoặc chuyển sang integer micro-units nếu meter yêu cầu.

Các trường quan trọng:

- Usage event ID duy nhất để deduplicate.
- Tenant/account/subscription effective tại thời điểm phát sinh.
- Meter name và version.
- Quantity và unit.
- Operation/resource ID để đối soát.
- Occurred time và recorded time.
- Source service, region, environment.
- Correlation/request ID nếu cần điều tra.
- Correction/reversal reference nếu điều chỉnh usage.

### 4.2. Metering ở đâu?

Có thể thu thập usage ở nhiều lớp:

- Gateway: request accepted, endpoint class, bytes, response status.
- Application: business operation hoàn tất, feature được sử dụng.
- Worker: duration, compute units, job outcome.
- Storage: snapshot bytes/object count theo tenant.
- Database: query/rows/compute attribution nếu engine hỗ trợ.
- Cloud billing export: provider cost theo resource/account/tag.

Không dùng một điểm đo cho mọi loại tài nguyên. Gateway không biết chính xác compute duration của background job; worker có thể đo duration nhưng không biết provider egress bill nếu không nhận dữ liệu billing export.

### 4.3. Event phát sinh một lần không đảm bảo được ghi nhận một lần

Usage event có thể được gửi lại do retry hoặc queue redelivery. Metering pipeline cần idempotency:

1. Mỗi operation tạo usage_event_id ổn định.
2. Consumer ghi event vào ledger với unique constraint.
3. Aggregate từ các ledger event đã commit.
4. Nếu nhận duplicate, bỏ qua theo event identity.
5. Nếu cần điều chỉnh, phát correction event có liên kết bản gốc.
6. Đối soát tổng usage với source count hoặc provider invoice.

Không dùng timestamp gần nhau để deduplicate vì hai operation hợp lệ có thể cùng diễn ra trong một millisecond.

### 4.4. Metering ledger và aggregation

Usage ledger là nơi giữ record chi tiết phục vụ audit/đối soát. Aggregate table hoặc warehouse phục vụ dashboard và invoice. Không chỉ giữ tổng cuối kỳ rồi xóa chi tiết; khi tenant khiếu nại, cần khả năng truy về operation/resource và meter version.

~~~mermaid
flowchart TB
    S1["API meters"] --> E["Usage events"]
    S2["Worker meters"] --> E
    S3["Storage snapshots"] --> E
    S4["Provider billing export"] --> E
    E --> Q[("Durable ingestion")]
    Q --> V["Validate / deduplicate"]
    V --> L[("Usage ledger")]
    L --> A["Aggregate by tenant / meter / period"]
    A --> D[("Usage warehouse")]
    D --> BILL["Billing / invoice"]
    D --> DASH["Tenant and operator dashboards"]
    L --> REC["Reconciliation"]
~~~

## 5. Exactness, late data và correction

Metering thường liên quan tới tiền hoặc quyền sử dụng. Vì vậy cần định nghĩa độ chính xác và cách xử lý dữ liệu trễ.

### 5.1. Occurred time và recorded time

Một job bắt đầu lúc 10:00 và hoàn tất lúc 10:20; usage có thể chỉ biết chính xác sau khi job hoàn thành. Event có occurred_at là khoảng thời gian hoạt động và recorded_at là lúc ledger nhận record. Billing period có thể dựa trên thời gian phát sinh, thời gian kết thúc hoặc quy tắc hợp đồng; phải công bố một cách nhất quán.

### 5.2. Late-arriving usage

Provider billing export có thể đến trễ nhiều giờ hoặc ngày. Worker có thể offline và gửi usage sau khi kết nối phục hồi. Cần hỗ trợ:
- Late arrival window.
- Period close và reopen policy.
- Provisional usage và finalized usage.
- Correction/reversal record.
- Invoice adjustment hoặc credit.
- Audit người duyệt correction.

Không âm thầm ghi đè số liệu đã chốt. Nếu hóa đơn đã phát hành, điều chỉnh cần theo chính sách billing và chứng từ.

### 5.3. Meter versioning

Nếu thay đổi cách đo CPU units hoặc operation weights, cùng một meter name có thể không còn so sánh được giữa các kỳ. Hãy version meter, lưu effective date và giữ định nghĩa cũ đủ lâu để tái tính hóa đơn. Không replay dữ liệu lịch sử bằng meter mới nếu không có migration/correction được phê duyệt.

## 6. Cost allocation: từ cloud bill tới tenant

Cloud provider thường tính chi phí theo account, project, subscription, resource, region, tag hoặc meter. Một shared database hoặc cluster có thể phục vụ nhiều tenant và không có hóa đơn provider riêng cho từng tenant.

Cost allocation phân bổ phần chi phí đó theo **cost driver** được lựa chọn. Có thể phân loại:

- **Direct cost:** chi phí quy trực tiếp cho một tenant, ví dụ dedicated compute hoặc storage bucket riêng.
- **Shared variable cost:** chi phí biến thiên theo usage, ví dụ data transfer hoặc compute units.
- **Shared fixed cost:** baseline platform, control plane, minimum capacity, support.
- **Platform overhead:** security, logging, backup, monitoring, network hub.
- **Unallocated/residual:** phần chưa có driver tin cậy; cần hiển thị riêng thay vì phân bổ giả chính xác.

### 6.1. Chọn cost driver

| Cost pool | Driver có thể dùng | Rủi ro |
| --- | --- | --- |
| API compute | CPU time, weighted request units | Request weight không phản ánh chính xác mọi code path |
| Worker compute | vCPU-second/GB-second theo job | Shared worker idle capacity khó phân bổ |
| Database | Query/compute units, rows, workload attribution | Shared cache/lock/idle capacity phức tạp |
| Storage | GB-month theo tenant, object count/operations | Replication/backup tạo chênh lệch physical |
| Network | Egress bytes theo tenant/endpoint | Shared NAT/gateway có phí cố định |
| Logs | Bytes ingested theo service/tenant | Log không có tenant context hoặc cardinality |
| Support/platform | Seats, plan, tenant count hoặc revenue allocation | Không phản ánh nguyên nhân sử dụng trực tiếp |
| Shared baseline | Equal share, plan tier, capacity reservation | Có thể không công bằng với tenant quy mô khác |

Driver phải phù hợp với cấu trúc cost pool. Đừng phân bổ toàn bộ cluster cost chỉ theo request count nếu query cost chênh lệch lớn.

### 6.2. Phân bổ chi phí dùng chung

Một mô hình tổng quát:

~~~text
Tenant allocated cost
  = Direct tenant cost
  + Σ(shared cost pool × tenant driver share)
  + Contractual fixed fee or reserved capacity (nếu có)
~~~

Ví dụ shared worker cost tháng là 100 triệu VND. Metered compute của tenant A là 40.000 units, B là 35.000 và C là 25.000; tổng 100.000 units.

~~~text
A share = 40,000 / 100,000 = 40%  -> 40 triệu VND
B share = 35,000 / 100,000 = 35%  -> 35 triệu VND
C share = 25,000 / 100,000 = 25%  -> 25 triệu VND
~~~

Cách này minh bạch nếu compute units thực sự đại diện tốt cho shared worker cost. Nếu pool có idle baseline lớn, có thể tách fixed cost và variable cost rồi phân bổ theo capacity reservation/plan thay vì tính hết theo usage.

### 6.3. Showback và chargeback

- **Showback:** hiển thị tenant/team đã tiêu thụ và được phân bổ bao nhiêu, không trực tiếp ghi nợ.
- **Chargeback:** dùng số liệu để tính phí hoặc phân bổ ngân sách thật.
- **Billing:** tính số tiền tenant phải trả theo hợp đồng, discount, tier, minimum commitment, tax, currency và adjustment.

Có thể triển khai showback trước để kiểm chứng meter và driver. Khi chuyển sang chargeback, cần governance cao hơn: audit, period close, correction, dispute workflow và quyền truy cập hóa đơn.

## 7. Pricing model và billing meter

Usage meter không nhất thiết là billing meter. Hợp đồng có thể tính phí theo subscription cố định, số seat, số giao dịch, storage vượt mức, API units hoặc combination.

| Pricing model | Tính phí | Điều cần định nghĩa |
| --- | --- | --- |
| Flat subscription | Phí cố định mỗi kỳ | Entitlement, giới hạn hợp lý, overage policy |
| Per-seat | Số người dùng active/được cấp phép | Active seat, deactivation, prorating |
| Per-operation | Số operation/billing units | Successful vs attempted, retry, excluded operations |
| Tiered | Giá đơn vị theo bậc usage | Cumulative tier, reset period, boundary |
| Volume discount | Đơn giá giảm khi vượt ngưỡng | Threshold, retroactive hay marginal |
| Reserved capacity | Trả cho capacity đã cam kết | Reservation, utilization, burst policy |
| Hybrid | Subscription + usage/overage | Included quota và cách tính phần vượt |

### 7.1. Định nghĩa billable event

Hợp đồng cần trả lời:

- Chỉ tính operation thành công hay cả attempted request?
- Retry do lỗi nền tảng có được tính không?
- Operation bị client cancel ở giữa có tính phần compute đã tiêu thụ?
- Cache hit có tính theo API request hay resource usage?
- Storage tính logical, physical hay average daily GB-month?
- Có free tier, included quota và grace period không?
- Usage được làm tròn theo giây, phút, GB-day hay GB-month?
- Currency, tax và exchange rate có nguồn và thời điểm nào?

Nếu không rõ, tenant có thể thấy hai hệ thống tính cùng một feature khác nhau.

### 7.2. Ví dụ tính phí theo tier

Giả sử hợp đồng có 100.000 API units included; 100.000 units tiếp theo có giá 0,8 VND/unit; phần vượt 200.000 có giá 0,5 VND/unit. Tenant dùng 260.000 units:

~~~text
Included:                100,000 × 0      = 0
Tier 1:                  100,000 × 0.8    = 80,000 VND
Tier 2:                   60,000 × 0.5    = 30,000 VND
Usage charge:                             110,000 VND
~~~

Đây là ví dụ marginal tier. Một số hợp đồng áp dụng giá thấp nhất cho toàn bộ volume sau khi đạt bậc (volume tier); hai cách cho kết quả khác nhau nên phải ghi rõ.

## 8. QoS theo tenant: fairness và noisy-neighbor

### 8.1. Noisy-neighbor là gì?

Noisy-neighbor xảy ra khi một tenant dùng tài nguyên chung ở mức khiến tenant khác bị chậm, lỗi hoặc thiếu capacity. Có thể đến từ request burst, truy vấn database đắt, export lớn, queue backlog, storage operation hoặc log volume.

Một nền tảng cần đảm bảo tenant lớn có thể sử dụng nhiều tài nguyên theo entitlement, nhưng không để một tenant vượt mức gây ảnh hưởng không kiểm soát lên các tenant khác.

### 8.2. Các cơ chế kiểm soát

- **Rate limiting:** giới hạn request theo tenant, endpoint hoặc operation class.
- **Concurrency limit:** giới hạn số request/job đồng thời.
- **Quota:** giới hạn lượng tài nguyên trong kỳ hoặc số resource tồn tại.
- **Weighted fair queueing:** chia lượt xử lý theo trọng số plan/priority.
- **Admission control:** từ chối hoặc trì hoãn công việc khi capacity không đủ.
- **Bulkhead:** tách pool/queue/resource pool cho workload hoặc tenant tier.
- **Priority class:** phân biệt interactive, background và batch.
- **Per-tenant circuit breaker:** cô lập dependency hoặc tenant gây lỗi lặp.
- **Backpressure:** giảm tốc producer hoặc báo retry-after khi hệ thống bão hòa.

Không phải tenant nào cũng cần dedicated infrastructure. Có thể dùng shared pool với fairness scheduler, đồng thời cung cấp isolated pool cho tenant có entitlement hoặc yêu cầu compliance đặc biệt.

### 8.3. Rate limit và quota khác nhau

Rate limit giới hạn tốc độ tại một cửa sổ thời gian, ví dụ 100 request/giây. Quota giới hạn tổng sử dụng trong kỳ, ví dụ 2 triệu API units/tháng hoặc 500 GB storage.

Một tenant có thể còn monthly quota nhưng chạm rate limit tạm thời. Ngược lại, tenant có tốc độ thấp nhưng đã dùng hết quota tháng. API response cần phân biệt lý do và cung cấp metadata phù hợp như retry-after, limit, remaining và reset time.

### 8.4. Token bucket minh họa

Token bucket cho phép burst có giới hạn:

~~~text
tokens(t)
  = min(bucket_capacity,
        previous_tokens + refill_rate × elapsed_time)

Request cost <= available tokens -> accept and deduct
Otherwise -> throttle or reject
~~~

Mỗi request có thể tiêu thụ số token theo operation class. Bucket nên được phân phối nhất quán khi có nhiều API instance; local in-memory bucket trên từng pod có thể làm tenant nhận tổng limit gấp số replica. Có thể dùng gateway, centralized limiter hoặc thuật toán phân bổ quota từng instance.

## 9. Capacity isolation theo tầng

### 9.1. Compute

Theo dõi CPU time, memory, duration, concurrency và queue age theo tenant/job class. Giới hạn concurrency cho report/export, tách worker pool hoặc cấp priority để job batch không chiếm hết worker phục vụ tương tác.

### 9.2. Database

Một tenant có thể chạy report truy vấn hàng triệu dòng trong khi tenant khác thực hiện transaction ngắn. Các biện pháp gồm query timeout, statement/resource limit nếu engine hỗ trợ, connection pool riêng theo workload, workload group, read replica, partitioning và index. Không áp dụng per-tenant connection pool vô hạn; tổng pool vẫn phải nằm trong connection budget database.

### 9.3. Storage

Đo logical/physical bytes, object count, API operations và growth rate. Cần quota theo tenant, lifecycle policy, limit upload size và guardrail cho export. Một tenant không nên làm storage listing hoặc compaction của toàn platform bị quá tải.

### 9.4. Network và egress

Theo dõi bytes theo tenant, destination class và region. Egress lớn có thể phát sinh chi phí đáng kể hoặc bão hòa gateway. Có thể giới hạn export concurrency, chuyển file lớn qua object storage presigned URL, dùng CDN và áp dụng quota theo gói.

### 9.5. Queue và worker

Queue cần priority/fairness theo tenant hoặc job class. Nếu một tenant phát hàng triệu message, một FIFO toàn cục có thể gây head-of-line blocking. Có thể shard theo key, dùng fair scheduler hoặc tách queue cho tier; đổi lại số queue và vận hành tăng.

## 10. SLO theo tenant và service tier

SLO cấp platform có thể che giấu tenant có trải nghiệm kém. Ví dụ 99,9% request toàn hệ thống thành công nhưng một tenant có 20% lỗi vì data partition hoặc quota sai.

### 10.1. Tenant-specific SLI

Các SLI có thể gồm:

- Availability: tỷ lệ request hợp lệ thành công.
- Latency: p50/p95/p99 theo API/operation class.
- Freshness: độ trễ dữ liệu hoặc projection.
- Job completion: tỷ lệ job hoàn tất đúng deadline.
- Throttling: tỷ lệ request bị rate limit/quota.
- Data correctness: reconciliation mismatch hoặc failed validation.
- Support: thời gian phản hồi/sự cố theo tier nếu thuộc hợp đồng.

Phải tách lỗi do platform, lỗi client, quota hợp lệ và dependency ngoài theo quy tắc rõ. Không loại tất cả request bị throttled khỏi SLO nếu throttling bất ngờ do platform; nhưng có thể phân loại riêng trường hợp tenant chủ động vượt entitlement.

### 10.2. Ví dụ service tier

| Tier | Availability objective | Interactive latency target | Job priority | Support |
| --- | --- | --- | --- | --- |
| Standard | 99,5% | API p95 dưới 700 ms | Best effort | Giờ làm việc |
| Business | 99,9% | API p95 dưới 400 ms | Priority thường | Phản hồi nhanh hơn |
| Enterprise | 99,95% | API p95 dưới 250 ms | Reserved/priority capacity theo hợp đồng | Hỗ trợ theo SLA |

Đây là mức minh họa, không phải lời hứa dịch vụ. Target thật phải khả thi theo hạ tầng, region, dependencies và hợp đồng. Không cam kết p95 riêng cho tenant nếu kiến trúc shared pool không thể đảm bảo điều đó ở peak.

### 10.3. Error budget

Nếu SLO availability là 99,9% trong tháng 30 ngày, error budget theo thời gian tương đương:

~~~text
30 days × (1 - 0.999)
= 0.03 days
= 43.2 minutes
~~~

Cách tính theo request count sẽ khác với cách tính theo thời gian. Chọn SLI phù hợp, công bố cửa sổ và quy tắc loại trừ. Tenant-specific SLO cũng cần đủ traffic để percentile có ý nghĩa; tenant ít request nên dùng cửa sổ dài hơn hoặc kết hợp latency/error theo operation.

## 11. Phân biệt platform health, tenant QoS và contract entitlement

Ba lớp thông tin không nên trộn:

1. **Platform health:** cluster, database, queue, network, deployment và region đang hoạt động ra sao.
2. **Tenant QoS:** tenant cụ thể thực sự nhận latency, availability, freshness và job completion nào.
3. **Entitlement/contract:** tenant được sử dụng bao nhiêu và loại support/service tier nào.

Một tenant có thể có QoS thấp vì platform incident; cũng có thể bị throttle hợp lệ vì đã vượt rate limit. Dashboard cần hiển thị cả actual usage và entitlement để tránh diễn giải sai.

### 11.1. Tenant experience scorecard

Ví dụ scorecard:

| Metric | Actual period | Entitlement/SLO | Trạng thái |
| --- | ---: | ---: | --- |
| API units | 820.000 | 1.000.000 | Trong quota |
| Storage logical | 72 GB | 100 GB | Trong quota |
| API p95 | 310 ms | 400 ms | Đạt |
| Availability | 99,92% | 99,9% | Đạt |
| Export completion p95 | 8 phút | 10 phút | Đạt |
| Throttled requests | 0,4% | Baseline 0,2% | Cần điều tra |

Các giá trị chỉ minh họa. Không gộp metric thành một điểm số duy nhất nếu không giải thích cách tính và mức độ quan trọng của từng thành phần.

## 12. Observability và dashboard tenant-aware

### 12.1. Metric labels phải được kiểm soát

Gắn tenant ID trực tiếp vào mọi metric time series có thể tạo cardinality rất lớn nếu có hàng chục nghìn tenant và nhiều operation/region/status. Điều đó làm monitoring system tốn storage, memory và chi phí query.

Có thể:
- Dùng metric tổng hợp theo tier, region, operation class.
- Giữ tenant-level detail trong usage ledger hoặc analytics store.
- Dùng exemplar hoặc trace link cho điều tra request cụ thể.
- Chỉ tạo metric chi tiết cho tenant/tier cần SLO riêng.
- Hạn chế dimensions có cardinality cao.
- Dùng hashed/pseudonymous tenant reference nếu phù hợp.

Không đưa email, domain, tên khách hoặc dữ liệu nhạy cảm làm label. Tenant ID có thể là identifier nội bộ nhưng vẫn cần đánh giá khả năng nhận diện và quyền truy cập.

### 12.2. Dashboard cho từng đối tượng

**Tenant dashboard** nên hiển thị:
- Usage hiện tại và xu hướng theo meter.
- Quota, entitlement, remaining và reset time.
- Service health và SLO liên quan.
- Job/export status.
- Cost estimate hoặc invoice detail theo quyền.
- Warning khi gần ngưỡng hoặc bị throttled.

**Operator dashboard** nên hiển thị:
- Top tenants theo resource, growth và cost drivers.
- Noisy-neighbor signals.
- Pool/queue/database saturation.
- Platform SLI/SLO và tenant-specific SLO.
- Meter ingestion lag, duplicate, rejected/corrected events.
- Allocation residual và reconciliation mismatch.

### 12.3. Trace và usage attribution

Trace nên mang tenant context đã được xác thực và operation class. Child span của worker cần kế thừa context từ job metadata. Có thể liên kết trace với usage event ID để operator điều tra một số liệu cụ thể; không cần lưu toàn bộ payload hay PII.

## 13. Billing correctness, audit và dispute handling

Khi usage được dùng để tính tiền, hệ thống phải giải thích được con số từ nguồn tới invoice.

Một billing record nên có:
- Tenant/account/subscription và billing period.
- Meter name/version, quantity/unit.
- Pricing plan/version, tier và rate.
- Discount/credit/tax nếu áp dụng.
- Source usage event range hoặc ledger reference.
- Calculation timestamp và invoice version.
- Adjustment/reversal và approval reference.

### 13.1. Tách metering khỏi pricing

Metering xác định quantity. Pricing áp dụng hợp đồng. Billing tổng hợp khoản phải trả. Việc tách này cho phép thay đổi giá hoặc discount mà không phải đo lại usage lịch sử, đồng thời tái tính invoice khi có correction.

### 13.2. Dispute workflow

Khi tenant khiếu nại hóa đơn:

1. Định danh invoice line và meter version.
2. Truy về ledger records và operation/resource references.
3. Kiểm tra duplicate, missing data, late arrival và correction.
4. So với source logs/provider usage export hoặc business transaction.
5. Kiểm tra entitlement, plan effective time và pricing rule.
6. Phê duyệt credit/adjustment nếu cần.
7. Ghi audit và cập nhật invoice revision.

Không sửa trực tiếp ledger đã chốt để làm số liệu “đẹp”. Dùng correction/reversal event có reason và người duyệt.

### 13.3. Reconciliation

Đối soát có thể gồm:

- API gateway request count với application usage meter.
- Job completion records với worker compute meter.
- Tenant logical storage snapshot với storage inventory.
- Cloud billing export với resource/account cost pool.
- Usage ledger với invoice quantities.
- Invoice totals với pricing rules và rounding.

Sai lệch cần có threshold, owner và trạng thái xử lý. Không phải mọi resource charge đều quy chính xác được tới tenant; ghi rõ phần shared residual.

## 14. Security và privacy cho tenant metering

Metering data có thể tiết lộ quy mô kinh doanh, hành vi sử dụng, số người dùng, thời gian hoạt động và loại giao dịch của tenant. Vì vậy usage analytics cũng là dữ liệu cần bảo vệ.

- Tenant chỉ đọc usage/billing của chính mình.
- Billing operator có role rõ, audit truy cập và export.
- Meter writer chỉ được ghi event cho tenant context đã xác minh.
- Không nhận tenant identity tùy ý từ client.
- Usage ledger có integrity protection, retention và backup.
- Chống chỉnh sửa/giả mạo event và replay trái phép.
- Tách dữ liệu production khỏi test/demo.
- Mask hoặc pseudonymize identifier trong analytics.
- Giới hạn retention theo hợp đồng và yêu cầu pháp lý.
- Dùng encryption at rest/in transit và key separation phù hợp.
- Không đưa tenant-level private details vào metric label công khai.

Nếu tenant dùng hệ thống BYOK hoặc encryption key riêng, cần xem quyền đọc metadata usage và billing có phụ thuộc data key của tenant hay không. Metering không nên đòi quyền giải mã nội dung dữ liệu nếu chỉ cần đo byte hoặc operation count.

## 15. Capacity planning và dự báo theo tenant

Usage history hỗ trợ dự báo growth, detect anomaly và lập capacity. Nhưng forecast không nên chỉ dựa vào tổng request.

Có thể theo dõi:
- Tenant growth rate theo meter.
- Peak-to-average ratio.
- Seasonality theo ngày/giờ/campaign.
- Storage growth và retention.
- Job duration distribution.
- API operation mix.
- Quota utilization và frequency of throttling.
- Cost per unit và unit economics.

### 15.1. Forecast và alert

Ví dụ tenant storage tăng từ 50 GB lên 70 GB trong 10 ngày. Tốc độ tăng trung bình khoảng 2 GB/ngày. Nếu quota là 100 GB, ước tính còn 15 ngày tới ngưỡng nếu tốc độ không đổi.

~~~text
Average daily growth
  = (Current storage - Previous storage) / Elapsed days

Estimated days to quota
  = (Quota - Current usage) / Average daily growth
~~~

Đây là forecast đơn giản; thực tế có thể có seasonality, compression, deletion và snapshot. Cần hiển thị đây là ước lượng, không phải cam kết ngày chạm quota.

### 15.2. Anomaly detection

Có thể phát hiện:
- Request rate tăng bất thường so với baseline của tenant.
- Egress tăng nhanh sau khi bật export.
- Storage growth đột ngột.
- Error/throttle spike.
- Job duration hoặc data scanned tăng bất thường.
- Usage meter giảm về zero dù business traffic vẫn có.

Anomaly không đồng nghĩa abuse. Tenant có thể đang chạy chiến dịch hợp lệ; operator cần contextualize với deployment, contract và lịch hoạt động.

## 16. TCO và quyết định shared hay isolated capacity

Metering cũng giúp quyết định tenant nào nên dùng shared pool, reserved capacity hoặc dedicated environment.

| Mô hình | Ưu điểm | Trade-off |
| --- | --- | --- |
| Fully shared | Cost efficiency, vận hành tập trung | Noisy-neighbor và attribution phức tạp |
| Shared với quota/fairness | Cân bằng sử dụng, giảm tenant ảnh hưởng lẫn nhau | Scheduler/limiter phức tạp |
| Pooled theo tier/region | Isolation tốt hơn ở nhóm workload | Tốn capacity headroom, placement phức tạp |
| Dedicated tenant stack | Isolation, customization, compliance | Chi phí và vận hành cao, capacity có thể nhàn rỗi |
| Hybrid | Shared baseline, dedicated cho tenant đặc biệt | Nhiều mô hình cần metering nhất quán |

### 16.1. Cost per tenant và cost to serve

~~~text
Cost to serve tenant
  = Direct resource cost
    + Allocated shared variable cost
    + Allocated platform fixed cost
    + Support/operations allocation

Tenant contribution
  = Contract revenue
    - Cost to serve
    - Applicable discounts/credits
~~~

Không dùng contribution để tự động hạ QoS hay phân biệt đối xử với tenant trái hợp đồng. Chỉ số này hỗ trợ product/pricing/capacity planning; quyết định dịch vụ vẫn phải tuân theo entitlement và SLA.

## 17. Case study: nền tảng SaaS đa tenant

### 17.1. Bối cảnh

Một SaaS quản lý vận hành cho 500 doanh nghiệp. Nền tảng dùng chung Kubernetes, PostgreSQL, object storage, queue và worker. Gói dịch vụ gồm Standard, Business và Enterprise. Một vài tenant chạy export lớn vào cuối ngày, làm queue và database tăng tải.

Yêu cầu giả định:

- Tenant có dashboard xem usage và quota.
- Operator biết tenant nào gây tải và chi phí nào tăng.
- Export lớn không làm request tương tác của tenant khác vượt SLO.
- Usage billing có thể đối soát tới operation.
- Enterprise có reserved concurrency và SLO riêng theo hợp đồng.
- Dữ liệu usage của tenant phải được bảo vệ.

### 17.2. Thiết kế metering

Gateway ghi API units theo operation class; worker ghi compute duration và job size; storage inventory tạo snapshot GB theo ngày; cloud billing export cung cấp provider cost theo resource. Các usage events đi vào durable queue, được validate/deduplicate rồi ghi usage ledger. Aggregate theo tenant, meter, period và version được dùng cho dashboard và billing.

~~~mermaid
flowchart TB
    G["API gateway meters"] --> UE["Usage event bus"]
    W["Worker meters"] --> UE
    ST["Storage inventory"] --> UE
    CB["Cloud billing export"] --> UE
    UE --> LEDGER[("Usage ledger")]
    LEDGER --> AGG["Tenant aggregation"]
    AGG --> DW[("Usage warehouse")]
    DW --> TD["Tenant usage dashboard"]
    DW --> OP["Operator cost/QoS dashboard"]
    DW --> INV["Billing calculation"]
~~~

### 17.3. Fairness cho export

Export job được phân loại background-heavy. Standard/Business dùng shared worker queue với per-tenant concurrency limit và fair scheduling. Enterprise có reserved worker capacity theo entitlement. API interactive có priority cao hơn batch export. Khi backlog tăng, hệ thống phát retry-after hoặc báo job pending thay vì giữ hàng nghìn request thread chờ.

### 17.4. Cost allocation

Storage GB-month được phân bổ trực tiếp theo tenant snapshot. Worker compute được phân bổ theo measured duration/resource units. Database shared baseline được tách fixed pool theo tier/tenant entitlement, còn phần variable được phân bổ theo workload driver đã công bố. Network egress dùng bytes theo tenant; platform security/control-plane cost hiển thị thành shared overhead.

### 17.5. QoS và điều tra

Operator thấy tenant X có export concurrency cao, queue age tăng và database read latency bị ảnh hưởng. Limiter giảm concurrency export của tenant X trong phạm vi quota; API interactive vẫn giữ capacity. Tenant dashboard hiển thị usage, quota và trạng thái job. SLO theo tenant cho thấy Business tenant vẫn đạt API latency, còn export completion bị trễ; operator có runbook kiểm tra worker saturation và backlog.

### 17.6. Billing dispute

Tenant Y khiếu nại API units cao hơn dashboard nội bộ. Billing team truy invoice line về meter version và usage ledger. Họ phát hiện event retry bị ghi hai lần ở một consumer cũ do thiếu unique constraint. Correction event đảo phần usage trùng; pipeline được fix, invoice revision có audit. Đây là lý do metering cần ledger, idempotency và reconciliation.

## 18. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Tin tenant ID từ request header | Usage bị gán sai hoặc lộ dữ liệu | Resolve từ identity đã xác thực |
| Chỉ đếm request | Không phản ánh chi phí request nặng | Weighted meter và resource usage |
| Meter ở nhiều lớp mà không có operation ID | Đếm trùng API và worker | Định nghĩa grain và meter ownership |
| Không idempotent usage event | Retry làm tăng hóa đơn | Unique event ID và ledger constraint |
| Chỉ lưu aggregate cuối kỳ | Không điều tra được dispute | Giữ usage ledger có audit |
| Gộp fixed và variable cost | Phân bổ không công bằng | Tách cost pools và cost drivers |
| Dùng tenant ID làm label cho mọi metric | Cardinality và chi phí monitoring tăng | Aggregate metric, detail trong warehouse |
| Rate limit local từng pod | Tổng limit tăng theo số replica | Shared limiter hoặc quota partition |
| Tenant lớn chiếm hết queue | Noisy-neighbor và head-of-line blocking | Fair scheduler, priority, bulkhead |
| SLO chỉ đo cấp platform | Tenant cụ thể bị lỗi bị che khuất | Tenant-level SLI/SLO |
| Correction ghi đè lịch sử | Mất audit, tranh chấp billing | Reversal/correction event |
| Pricing thay đổi nhưng không version | Không tái tạo được invoice cũ | Meter/pricing version và effective date |
| Showback dùng như chargeback ngay | Tin cậy chưa được kiểm chứng | Shadow billing và dispute test trước |
| Phân bổ cost chính xác giả tạo | Quyết định sai và mất niềm tin | Công bố residual/shared overhead |

## 19. Bài tập thực hành

Một nền tảng SaaS có 1.000 tenant dùng chung API, PostgreSQL, object storage và queue. Ba gói dịch vụ có quota khác nhau. Một tenant chạy export 2 TB khiến queue backlog tăng và API latency của tenant khác vượt SLO. Finance muốn tính usage hàng tháng, còn vận hành cần phát hiện noisy-neighbor.

Hãy thực hiện:

1. Xác định tenant identity đáng tin cậy cho API, scheduled job và worker event.
2. Đề xuất meter cho API, compute, database, storage, egress và queue; ghi unit, grain và source.
3. Thiết kế usage event schema với event ID, operation ID, tenant/account, meter version và timestamps.
4. Đảm bảo metering idempotent khi queue redelivery và worker retry.
5. Phân loại direct, shared variable, shared fixed và platform overhead; chọn cost driver cho từng nhóm.
6. Tính phân bổ 120 triệu VND worker cost nếu tenant A/B/C tiêu thụ 50.000/30.000/20.000 compute units.
7. Thiết kế pricing tiers và nêu rõ included quota, overage, retry và late usage policy.
8. Thiết kế rate limit, concurrency, fair queue và reserved capacity để giảm noisy-neighbor.
9. Định nghĩa ít nhất hai SLI/SLO theo tenant và một SLO cấp platform.
10. Xây dashboard cho tenant và operator; tránh metric cardinality quá cao.
11. Thiết kế usage ledger, correction event, invoice reconciliation và dispute workflow.
12. Kiểm thử giả mạo tenant context, duplicate usage, late event, limiter scale-out và queue starvation.
13. Viết ADR về shared, pooled hoặc dedicated capacity theo tier; nêu cost và QoS trade-off.

**Gợi ý tự đánh giá:** Bài làm đạt khi số usage truy được về tenant và operation, cost driver giải thích được, quota không bị nhân theo replica, tenant QoS không bị metric tổng che khuất, và hóa đơn có thể tái tạo/đối soát.

## 20. Checklist trước production

- [ ] Tenant identity được xác thực và xuyên suốt API, event, worker, batch.
- [ ] Usage meter có tên, version, unit, grain, source và owner.
- [ ] Phân biệt logical usage, provider resource usage và billable usage.
- [ ] Mỗi operation/usage event có ID ổn định và cơ chế dedup.
- [ ] Usage ledger có retention, audit và correction/reversal.
- [ ] Late data, period close và invoice adjustment có policy.
- [ ] Meter version và pricing version có effective time.
- [ ] Direct/shared fixed/shared variable cost được tách rõ.
- [ ] Cost driver được công bố và residual không bị phân bổ giả chính xác.
- [ ] Showback được kiểm chứng trước chargeback.
- [ ] Quota, rate limit và concurrency limit nhất quán khi scale nhiều replica.
- [ ] Có fairness, priority, bulkhead và backpressure cho workload nặng.
- [ ] Tenant-level SLI/SLO tách platform failure và quota enforcement.
- [ ] Dashboard tránh PII và metric cardinality không kiểm soát.
- [ ] Tenant chỉ đọc usage/billing của chính mình; operator access có audit.
- [ ] Có reconciliation từ source tới ledger, aggregate và invoice.
- [ ] Có dispute workflow và người duyệt correction.
- [ ] Đã kiểm thử noisy-neighbor, duplicate, late usage, scale-out và dependency failure.
- [ ] TCO và capacity planning sử dụng dữ liệu usage có chất lượng.

## 21. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi thiết kế tenant metering và QoS |
| --- | --- |
| **Operational Excellence** | Usage ledger, dashboard, alert, cost allocation, invoice reconciliation và runbook có owner không? |
| **Security** | Tenant identity có đáng tin; usage/billing có tenant isolation, least privilege, audit và retention không? |
| **Reliability** | Metering có durable, idempotent, xử lý late data/correction và không làm chậm request path không? |
| **Performance Efficiency** | Quota, fairness, concurrency và isolation có bảo vệ tenant khác khi peak/noisy-neighbor không? |
| **Cost Optimization** | Cost driver phản ánh consumption; shared overhead, cost per tenant và pricing có được theo dõi không? |
| **Sustainability** | Có giảm overprovisioning, idle reservation, log thừa và xử lý lặp không? |

**Kết luận:** Đo theo tenant cần nối được danh tính, operation, tài nguyên, chi phí và chất lượng dịch vụ trong cùng một mô hình có thể kiểm toán. Metering chính xác tạo nền cho showback và billing; cost allocation cần driver minh bạch; QoS cần quota, fairness và SLO theo tenant để một khách hàng không âm thầm ảnh hưởng khách hàng khác. Hãy tách usage khỏi pricing, lưu ledger có thể đối soát, bảo vệ tenant context xuyên suốt và chọn mức isolation dựa trên hợp đồng cùng dữ liệu tải thực tế theo tinh thần Well-Architected.

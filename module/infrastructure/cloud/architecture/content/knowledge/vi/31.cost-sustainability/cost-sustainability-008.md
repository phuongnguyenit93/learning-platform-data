# Ngân sách, phát hiện bất thường và vòng phản hồi FinOps

Chi phí cloud có thể tăng nhanh dù kiến trúc không thay đổi rõ rệt. Traffic tăng, log retention dài hơn, một database replica được tạo để xử lý sự cố rồi bị quên, autoscaling mở rộng theo burst, hoặc một job batch chạy lặp đều có thể làm hóa đơn vượt dự báo. Nếu chỉ xem tổng hóa đơn vào cuối tháng, nhóm kỹ thuật thường phát hiện vấn đề quá muộn và khó xác định ai có thể hành động.

**FinOps** là cách vận hành tài chính cloud có sự phối hợp giữa engineering, finance, product và business. Mục tiêu không đơn giản là cắt giảm chi phí; đó là tạo khả năng nhìn thấy chi phí, phân bổ chi phí về sản phẩm/workload, dự báo nhu cầu, phát hiện bất thường và đưa quyết định tối ưu vào vòng đời kỹ thuật. Một hệ thống rẻ hơn nhưng làm giảm độ tin cậy hoặc hiệu năng vượt mức nghiệp vụ chấp nhận có thể tạo tổng chi phí lớn hơn.

Bài học thuộc chương **Chi phí và bền vững** của module **CLOUD_ARCHITECTURE**. Trọng tâm là thiết kế ngân sách và forecast, đo chi phí theo đơn vị nghiệp vụ, thiết lập anomaly detection, phân định ownership và tạo vòng phản hồi FinOps để cân bằng chi phí với độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng và mục tiêu bền vững.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của ngân sách, forecast, allocation, showback và chargeback trong FinOps.
2. Xây dựng cost model và unit economics theo sản phẩm/workload/đơn vị nghiệp vụ.
3. Thiết kế tagging, account/project hierarchy và ownership để phân bổ chi phí đáng tin cậy.
4. Theo dõi actual, budget, forecast, variance và cost trend.
5. Phát hiện cost anomaly theo mức nền, tốc độ tăng và mức độ ảnh hưởng.
6. Phân biệt anomaly kỹ thuật với thay đổi kinh doanh hợp lệ.
7. Thiết lập alert, triage, owner, remediation và post-incident learning.
8. Đánh giá rightsizing, autoscaling, commitment, storage lifecycle và kiến trúc theo tổng chi phí.
9. Tổ chức vòng phản hồi FinOps có KPI, review cadence và guardrail.

## 2. FinOps và trách nhiệm chung

### 2.1. FinOps là một vòng lặp vận hành

FinOps kết nối ba nhóm hoạt động:

- **Inform:** hiểu chi phí phát sinh ở đâu, thuộc workload nào, thay đổi vì lý do gì.
- **Optimize:** lựa chọn cách sử dụng tài nguyên hiệu quả hơn với yêu cầu nghiệp vụ.
- **Operate:** đưa ownership, ngân sách, forecast, policy và review vào vận hành thường xuyên.

~~~mermaid
flowchart LR
    INFORM[Inform: visibility and allocation] --> OPT[Optimize: evaluate and act]
    OPT --> OPERATE[Operate: budget, policy and review]
    OPERATE --> INFORM
    BUSINESS[Product and business goals] --> INFORM
    BUSINESS --> OPT
    ENG[Engineering and platform teams] --> OPT
    FIN[Finance and FinOps] --> OPERATE
~~~

Vòng lặp chỉ có tác dụng khi dữ liệu chi phí dẫn tới hành động và kết quả hành động được đo lại. Dashboard đẹp nhưng không có owner hoặc quyết định tiếp theo sẽ không làm chi phí tốt hơn.

### 2.2. Phân công trách nhiệm

| Vai trò | Trách nhiệm điển hình |
|---|---|
| Finance | Nguyên tắc ngân sách, kỳ kế toán, forecast tài chính, kiểm soát cam kết |
| FinOps/platform team | Cost data pipeline, allocation model, anomaly detection, policy và enablement |
| Product/business owner | Dự báo nhu cầu, quyết định trade-off và cost per business outcome |
| Engineering/service owner | Phân tích driver kỹ thuật, rightsizing, capacity và remediation |
| Procurement/vendor owner | Hợp đồng, pricing, credit, discount và renewal |
| Leadership | Mục tiêu, guardrail và ưu tiên giữa tăng trưởng, reliability và chi phí |

Một khoản chi phí nên có owner có khả năng giải thích và hành động. Không đẩy toàn bộ trách nhiệm cho finance vì nhiều driver chỉ engineering mới có thể thay đổi; cũng không để engineering tự tối ưu mà không hiểu tác động thương mại.

### 2.3. Cost optimization không đồng nghĩa cắt giảm bằng mọi giá

Chi phí phải được xem cùng chất lượng dịch vụ. Giảm replica có thể hạ bill nhưng làm mất HA; giảm log retention có thể tiết kiệm storage nhưng ảnh hưởng điều tra; dùng instance nhỏ hơn có thể tăng tail latency và retry. Quyết định tối ưu cần ghi rõ mục tiêu, ràng buộc, rủi ro và cách đo sau thay đổi.

## 3. Hiểu mô hình chi phí cloud

### 3.1. Thành phần chi phí phổ biến

| Nhóm | Ví dụ driver | Nguyên nhân tăng thường gặp |
|---|---|---|
| Compute | vCPU-hour, memory, instance/accelerator time | Capacity dư, workload chạy lâu, autoscaling không hạ |
| Container/serverless | vCPU/memory duration, invocation, request | Nhiều invocation, cold start, retry, concurrency |
| Storage | GB-month, IOPS, request, retrieval | Data growth, snapshot, log, version và retention |
| Network | Egress, inter-zone/region transfer, NAT, load balancer | Data transfer, chatty service, cross-region replication |
| Database | Instance time, storage, I/O, backup, connection | Oversizing, query kém, replica dư, backup tăng |
| Messaging | Throughput, partition, request, retained data | Consumer chậm, retry, retention dài |
| Observability | Ingest, indexing, query, retention | Log volume, high cardinality, trace sampling cao |
| Security | KMS request, scanning, WAF, audit storage | Quy mô request, policy và retention |
| Commercial | Support plan, license, subscription, commitment | Seat/usage growth, contract overlap |

Tên đơn vị và cách tính khác nhau giữa provider và service. Dùng billing export/rate card thực tế của tổ chức, không áp một công thức chung cho mọi cloud.

### 3.2. Fixed, variable và step cost

- **Fixed/committed cost:** khoản đã cam kết hoặc subscription khó giảm ngay.
- **Variable cost:** tăng theo request, data, compute time hoặc transfer.
- **Step cost:** khi vượt ngưỡng capacity cần thêm node, shard, replica hoặc license tier.

Phân loại này giúp hiểu tại sao traffic tăng 10% không nhất thiết làm bill tăng đúng 10%. Một hệ thống có thể còn headroom rồi đột ngột cần capacity mới; hoặc có commitment làm chi phí ngắn hạn ít thay đổi dù sử dụng giảm.

### 3.3. Direct và shared cost

Direct cost gắn khá rõ với một resource/workload, như database riêng của service. Shared cost gồm network egress chung, observability platform, support plan, control plane hoặc cluster dùng chung. Cần quy tắc allocation cho shared cost, nếu không mỗi sản phẩm có thể bị đánh giá sai.

### 3.4. Cost dimensions

Có thể phân tích chi phí theo:

- Account/project/subscription và environment.
- Product, service, team và owner.
- Region, availability zone và resource type.
- Tenant/customer cohort hoặc plan.
- Cost center, business unit và application.
- Shared, direct, platform và unallocated.

Không phải dimension nào cũng nên trở thành resource tag; một số lấy từ CMDB, service catalog, account hierarchy hoặc billing metadata.

## 4. Ngân sách và guardrail

### 4.1. Ngân sách là giới hạn quản trị

Budget đặt mức chi tiêu kỳ vọng cho phạm vi và thời gian cụ thể. Budget có thể áp dụng ở account, product, service, environment, team hoặc project. Cần xác định:

- Phạm vi resource và chi phí được tính.
- Đơn vị tiền tệ và kỳ (tháng/quý/năm).
- Có bao gồm tax, support, credit, discount và marketplace không.
- Actual hay amortized/effective cost được dùng.
- Owner, approver và người nhận alert.
- Hành động khi vượt ngưỡng.

Budget alert thường không tự ngăn chi phí phát sinh. Muốn có guardrail thực thi cần kết hợp quota, policy, admission control, autoscaling limit hoặc approval cho resource đắt tiền.

### 4.2. Budget theo giai đoạn

| Giai đoạn | Mục đích | Ví dụ |
|---|---|---|
| Planning | Dự báo nhu cầu và cấp vốn | Budget năm cho product |
| Delivery | Kiểm soát build/test/release | Giới hạn spend của sandbox |
| Production | Theo dõi vận hành | Monthly budget theo service |
| Experiment | Cho phép thử có giới hạn | Budget/TTL cho GPU experiment |
| Incident | Cho phép tăng capacity có kiểm soát | Emergency spend allowance |

Ngân sách production không nên vô tình chặn scale cần thiết trong incident. Cần quy trình emergency override có owner, thời hạn và review sau sự cố.

### 4.3. Guardrail theo môi trường

- Development/test có lịch tự tắt hoặc TTL.
- Production có baseline và capacity floor theo SLO.
- GPU/high-cost resource cần approval hoặc quota.
- Public IP, NAT, snapshot và storage có owner/retention.
- Region mới hoặc service mới cần cost estimate trước triển khai.
- Môi trường thử nghiệm có budget và deadline.

Guardrail phải phù hợp risk. Tự động terminate mọi resource vượt budget có thể gây outage hoặc mất dữ liệu; ưu tiên cảnh báo, approval và policy theo loại resource.

### 4.4. Budget threshold

Một số ngưỡng cảnh báo thường dùng:

- 50% budget: kiểm tra spend trend.
- 80% budget: owner rà soát forecast và driver.
- 100% budget: escalation và quyết định hành động.
- Forecast vượt budget trước kỳ kết thúc: hành động sớm thay vì chờ actual chạm ngưỡng.

Đây chỉ là ví dụ. Ngưỡng cần tính tới độ trễ billing, seasonality và độ lớn của workload.

## 5. Forecast và lập kế hoạch chi phí

### 5.1. Forecast không chỉ là kéo đường thẳng

Forecast nên kết hợp:

- Baseline từ actual spend.
- Traffic/usage forecast và business volume.
- Unit price/rate card, discount và commitment.
- Capacity plan, release roadmap và region changes.
- Seasonality, campaign, peak period.
- Retention/data growth và lifecycle.
- Rủi ro vendor/pricing hoặc thay đổi sản phẩm.

### 5.2. Mô hình driver-based forecast

Ví dụ compute cost có thể ước lượng:

\[
C_{\text{compute}} \approx \text{instance-hours} \times \text{effective hourly rate}
\]

Database storage:

\[
C_{\text{storage}} \approx \text{average GB-month} \times \text{price per GB-month}
\]

Network egress:

\[
C_{\text{egress}} \approx \text{billable GB} \times \text{effective rate}
\]

Các công thức chỉ biểu diễn driver cơ bản. Actual bill có thể còn tier, free allowance, request charge, minimum duration, regional price, currency và discount.

### 5.3. Forecast theo scenario

Lập ít nhất ba scenario:

| Scenario | Giả định | Mục đích |
|---|---|---|
| Baseline | Tăng trưởng kỳ vọng và release đã duyệt | Lập ngân sách chuẩn |
| High growth | Traffic/campaign cao hơn hoặc tenant mới | Kiểm tra capacity và budget headroom |
| Downside | Tăng trưởng thấp, tối ưu giảm usage | Tránh commitment dư và capacity nhàn rỗi |

Forecast nên thể hiện assumption, confidence/range, owner và ngày cập nhật. Một con số chính xác giả tạo thường kém hữu ích hơn một range có giả định rõ.

### 5.4. Rolling forecast

Rolling forecast cập nhật liên tục theo actual, pipeline sản phẩm và thay đổi nhu cầu thay vì chỉ lập một lần đầu năm. Tần suất có thể hàng tháng cho tài chính và hàng tuần cho service có biến động cao. Không thay forecast cũ mà không lưu version; cần giữ lịch sử để biết dự báo sai vì volume, unit price hay architecture change.

### 5.5. Variance analysis

Variance:

\[
\text{Variance}=\text{Actual}-\text{Budget}
\]

Variance percentage:

\[
\text{Variance \%}=\frac{\text{Actual}-\text{Budget}}{\text{Budget}}\times100\%
\]

Variance âm không nhất thiết tốt: có thể service không đáp ứng traffic hoặc một backup job đã ngừng chạy. Variance dương cũng không luôn xấu: có thể do tăng doanh thu hoặc incident đã được phê duyệt. Cần giải thích nguyên nhân và ảnh hưởng.

## 6. Cost allocation, tagging, showback và chargeback

### 6.1. Allocation

Cost allocation phân bổ chi phí về đối tượng có trách nhiệm hoặc hưởng lợi. Để phân bổ được, cần taxonomy ổn định cho resource và workload.

Tag/label gợi ý:

| Key | Ví dụ | Ý nghĩa |
|---|---|---|
| service | booking-api | Service sở hữu |
| owner | team-booking | Team chịu trách nhiệm |
| environment | production | Môi trường |
| cost-center | CC-204 | Đơn vị tài chính |
| product | reservations | Sản phẩm |
| data-class | confidential | Phân loại dữ liệu |
| managed-by | terraform | Cơ chế quản lý |
| expiry-date | 2026-12-31 | Thời hạn resource tạm |

Không đưa secret, email người dùng hay thông tin nhạy cảm vào tag. Tag schema cần được chuẩn hóa, validate và áp tự động từ IaC/pipeline khi có thể.

### 6.2. Tag coverage và unallocated spend

Theo dõi tỷ lệ chi phí được phân bổ:

\[
\text{Allocation coverage}=
\frac{\text{Allocated spend}}{\text{Total in-scope spend}}\times100\%
\]

Chi phí chưa phân bổ phải được hiển thị thành một nhóm có owner xử lý, không âm thầm chia đều. Định kỳ điều tra resource thiếu tag, tag sai và shared cost chưa có quy tắc.

### 6.3. Showback

Showback cung cấp báo cáo chi phí cho team/product để họ hiểu mức sử dụng nhưng không chuyển khoản kế toán trực tiếp. Đây thường là bước đầu phù hợp khi taxonomy và allocation chưa đủ trưởng thành.

### 6.4. Chargeback

Chargeback tính hoặc phân bổ chi phí vào ngân sách/cost center của đơn vị tiêu thụ. Cần định nghĩa rõ:

- Rate và cách amortize commitment.
- Shared platform overhead.
- Chi phí network/shared service.
- Credit/refund/tax và currency.
- Quy trình dispute/correction.

Nếu allocation còn sai, chargeback có thể tạo tranh chấp và hành vi tối ưu sai. Nên bắt đầu bằng showback có thể giải thích, sau đó chuyển dần khi dữ liệu đáng tin.

### 6.5. Shared cost allocation

Một số cách:

- Theo usage đo được (request, GB, vCPU-hour).
- Theo capacity reservation hoặc quota.
- Theo số tenant/customer.
- Theo revenue hoặc business weighting.
- Giữ ở platform overhead nếu không có driver hợp lý.

Chọn driver phản ánh quan hệ tiêu thụ và công bố quy tắc. Không nên thay driver mỗi kỳ để làm đẹp báo cáo.

## 7. Unit economics: chi phí trên một kết quả nghiệp vụ

### 7.1. Vì sao cần unit cost?

Bill tổng tăng chưa nói rõ hiệu quả kinh tế. Nếu số booking tăng nhanh hơn chi phí thì cost per booking có thể giảm; ngược lại, bill không đổi nhưng traffic giảm có thể khiến cost per request tăng.

Ví dụ:

\[
\text{Cost per booking}=
\frac{\text{Allocated cloud cost for booking platform}}{\text{Completed bookings}}
\]

Các đơn vị khác:

- Cost per active tenant.
- Cost per monthly active user.
- Cost per API request hoặc successful request.
- Cost per GB stored/served.
- Cost per transaction processed.
- Cost per search/query hoặc report generated.

### 7.2. Chọn denominator đúng

Denominator cần phản ánh outcome có giá trị, không chỉ hoạt động kỹ thuật. Một booking tạo nhưng bị hủy hoặc thanh toán thất bại có thể không tương đương booking hoàn tất. Cần định nghĩa metric cùng product/finance owner.

### 7.3. Phân bổ chi phí vào unit

Chọn cost scope nhất quán:

- Include direct resource cost.
- Xác định cách phân bổ shared platform/network/observability.
- Quy định period và currency.
- Loại trừ hoặc phân bổ credit/refund theo policy.
- Gắn volume cùng kỳ và xử lý late-arriving billing data.

Không so sánh cost per unit giữa hai team nếu cách tính shared cost khác nhau.

### 7.4. Cost và chất lượng

Đọc unit cost cùng SLO:

| Chỉ số | Câu hỏi |
|---|---|
| Cost per successful booking | Chi phí tạo ra kết quả thực sự |
| p95/p99 latency | Tiết kiệm có làm trải nghiệm chậm hơn? |
| Availability/error rate | Có giảm redundancy hoặc capacity quá mức? |
| Retry per operation | Có đang trả tiền cho công việc lặp? |
| Support/incident cost | Tiết kiệm cloud có làm tăng công vận hành? |

Unit cost thấp hơn nhưng lỗi cao hơn hoặc tỷ lệ hoàn tất thấp hơn không nhất thiết là hiệu quả hơn.

## 8. Phát hiện cost anomaly

### 8.1. Anomaly là gì?

Cost anomaly là biến động chi phí khác đáng kể so với mức dự kiến hoặc hành vi bình thường. Nó có thể đến từ:

- Resource bất thường: instance lớn, accelerator, database replica.
- Usage bất thường: egress, API calls, NAT processing, log ingest.
- Cấu hình sai: retention vô hạn, autoscaling max quá cao, retry loop.
- Thay đổi kiến trúc: replication mới, cross-region traffic.
- Security incident: cryptomining, exfiltration, credential misuse.
- Thay đổi kinh doanh hợp lệ: campaign, tenant growth, launch.

Không phải mọi spike là anomaly xấu; cần đối chiếu với release, campaign, incident và volume nghiệp vụ.

### 8.2. Baseline và ngưỡng

Phát hiện đơn giản có thể so sánh actual với rolling average hoặc forecast:

\[
\text{Deviation \%}=
\frac{\text{Actual}-\text{Expected}}{\max(\text{Expected},\epsilon)}\times100\%
\]

Đặt epsilon hoặc mức spend tối thiểu để tránh percentage rất lớn khi baseline gần zero. Có thể kết hợp:

- Absolute spend threshold.
- Percent deviation.
- Rate-of-change trong giờ/ngày.
- Forecast end-of-period.
- Resource-specific threshold.
- Seasonal baseline theo ngày trong tuần/tháng.

### 8.3. Phát hiện theo nhiều cấp

| Cấp | Tín hiệu | Hành động |
|---|---|---|
| Organization/account | Tổng chi phí vượt budget/forecast | FinOps triage |
| Product/service | Một workload tăng bất thường | Service owner điều tra |
| Resource | Một resource có spend đột biến | Kiểm tra config, tag, lifecycle |
| Usage driver | Egress/IO/log/request tăng | Truy tìm traffic hoặc behavior |
| Unit economics | Cost per booking/request xấu đi | Đánh giá hiệu quả sản phẩm/kiến trúc |

### 8.4. Baseline theo seasonality

Campaign, cuối tuần, ngày lương hoặc kỳ báo cáo có thể tạo traffic pattern lặp. Baseline chỉ dùng moving average có thể báo giả. Dùng seasonal comparison (cùng thứ/ngày, cùng kỳ) hoặc forecast có business calendar.

### 8.5. Cost data delay

Billing data có thể đến trễ hoặc được điều chỉnh. Anomaly alert phải ghi rõ data freshness và mức ước tính. Kết hợp real-time usage metric từ service/cloud monitoring để phát hiện sớm, sau đó đối soát với billing actual.

## 9. Anomaly detection và cảnh báo

### 9.1. Cấp độ cảnh báo

- **Info:** variance nhỏ hoặc resource mới được tạo.
- **Warning:** spend/forecast vượt ngưỡng và cần owner giải thích.
- **Critical:** tốc độ tiêu thụ lớn, projected overspend đáng kể hoặc dấu hiệu abuse/security.

### 9.2. Alert phải có ngữ cảnh

Một alert hữu ích nên gồm:

- Scope/account/service/resource và owner.
- Actual, expected, delta tuyệt đối và delta phần trăm.
- Thời điểm bắt đầu và data freshness.
- Forecast tới cuối kỳ.
- Driver chính và link dashboard/billing breakdown.
- Release/change/incident gần thời điểm đó nếu có.
- Runbook và mức độ ưu tiên.

Alert “cloud spend increased” không có owner hoặc driver sẽ khó xử lý.

### 9.3. Ưu tiên theo impact

Có thể xếp priority bằng cách xét:

- Spend delta tuyệt đối.
- Tốc độ tăng và khả năng tiếp tục.
- Forecast overspend.
- Criticality của workload.
- Rủi ro security/abuse.
- Khả năng dừng an toàn.

Một resource thử nghiệm tăng 300% từ mức rất nhỏ có thể ít ưu tiên hơn egress production tăng 20% nhưng thêm khoản lớn mỗi ngày.

### 9.4. Tránh alert fatigue

Gộp alert theo root cause/resource group, dùng cooldown và suppression cho change đã được duyệt, nhưng không suppress dấu hiệu vượt ngưỡng lớn hoặc nghi ngờ compromise. Theo dõi false positive, missed anomaly và thời gian phát hiện.

## 10. Quy trình triage anomaly

### 10.1. Triage ban đầu

1. Xác minh dữ liệu billing/usage mới nhất và kỳ tính.
2. Xác định khoản tăng ở account, service, resource type, region hoặc usage dimension nào.
3. So sánh với deployment, campaign, traffic và incident gần thời điểm đó.
4. Tìm resource mới, thay đổi size, replica, retention hoặc network route.
5. Kiểm tra cost per unit và SLO để hiểu tác động.
6. Gán owner và mức độ ưu tiên.

### 10.2. Phân loại nguyên nhân

- **Expected growth:** traffic hoặc customer tăng theo kế hoạch.
- **Architecture/change driven:** rollout hoặc replication tạo cost mới.
- **Waste:** idle resource, overprovisioning, orphan hoặc storage dư.
- **Inefficiency:** query/algorithm, retry, egress hoặc logging không hiệu quả.
- **Misconfiguration:** scaling/retention/region/price tier sai.
- **Abuse/security:** credential bị lạm dụng, cryptomining hoặc exfiltration.
- **Billing/commercial:** discount hết hạn, SKU/contract thay đổi, credit điều chỉnh.

### 10.3. Chọn remediation an toàn

Trước khi stop/resize resource:

- Xác định production dependency và owner.
- Kiểm tra redundancy, SLO và data durability.
- Xác nhận resource có thể restart/terminate không.
- Lưu evidence và cost breakdown.
- Có rollback hoặc recreate path.
- Với nghi ngờ security, phối hợp incident response và bảo toàn log.

Không xóa snapshot, backup, log hoặc resource stateful chỉ vì chúng đắt mà chưa xác minh retention và recovery obligations.

## 11. Remediation playbook theo cost driver

| Driver | Nguyên nhân có thể | Hành động kiểm tra |
|---|---|---|
| Compute tăng | Instance lớn, autoscaling không scale-in, job chạy lâu | CPU/memory utilization, request load, scaling policy, schedule |
| Database tăng | Replica dư, storage/index phình, I/O cao | Query plan, connection, replica purpose, retention |
| Egress tăng | Cross-zone/region, payload lớn, egress loop | Network flow, route, cache, compression, data locality |
| NAT/load balancer | Traffic qua NAT, connection churn | Architecture path, endpoint, connection reuse |
| Logs/traces tăng | Debug log, cardinality, sampling/retention | Log level, attributes, sample rate, retention tiers |
| Object storage | Version/snapshot, lifecycle thiếu | Object age, access tier, replication, delete marker |
| Queue/messaging | Consumer lag, redelivery, retention | Retry loop, poison message, throughput, DLQ |
| Serverless | Invocation/retry/concurrency tăng | Trigger storm, function duration, memory, recursion |
| License/SaaS | Seat hoặc usage tier vượt ngưỡng | Active seats, contract, quota, unused integration |

### 11.1. Compute

Rightsizing cần dựa trên profile theo thời gian, peak, CPU throttling, memory pressure, latency và availability. Resource average 10% CPU có thể vẫn cần headroom khi burst hoặc có latency-sensitive workload. Kiểm tra scale-in behavior và minimum capacity trước khi giảm.

### 11.2. Storage

Áp lifecycle theo data class: hot, warm, cold, archive. Cân nhắc retrieval fee, latency, minimum storage duration và replication. Dọn orphan chỉ sau khi kiểm chứng ownership và retention. Snapshot có thể tăng theo change rate và retention, không chỉ theo dung lượng database hiện tại.

### 11.3. Network

Network cost thường khó phân bổ. Dùng flow log hoặc telemetry theo service/region khi phù hợp; tìm chatty calls, payload dư, cross-zone transfer và route vòng. Cache hoặc co-locate có thể giảm egress nhưng phải xem consistency, data residency và failure domain.

### 11.4. Observability

Không tắt metric/log/tracing một cách đại trà để giảm bill. Phân loại signal theo giá trị điều tra, sampling, retention, cardinality và archive. Giữ audit/security log theo policy bắt buộc; tối ưu debug/noisy logs trước.

## 12. Optimization portfolio và quyết định đầu tư

### 12.1. Từ finding thành initiative

Mỗi cơ hội tối ưu cần:

- Baseline spend và thời gian đo.
- Nguyên nhân/driver.
- Tiềm năng tiết kiệm theo tháng/năm.
- Chi phí triển khai và owner.
- Ảnh hưởng latency, availability, security và engineering time.
- Risk/rollback và cách đo lợi ích.

### 12.2. Ưu tiên

Có thể xếp theo:

\[
\text{Priority score}=
\frac{\text{Expected net benefit}\times\text{Confidence}}
{\text{Effort}\times\text{Risk factor}}
\]

Đây là khung ra quyết định, không phải công thức tài chính chuẩn. Không nên để một điểm số che khuất nghĩa vụ compliance hoặc rủi ro availability.

### 12.3. Optimization backlog

| Initiative | Benefit | Trade-off | Success measure |
|---|---|---|---|
| Rightsize API nodes | Giảm compute cost | Ít headroom hơn | Cost/request và p99 vẫn đạt |
| Cache catalog reads | Giảm DB/egress | Freshness và cache invalidation | Cost/query, hit rate, stale errors |
| Move archive to cold tier | Giảm storage rate | Retrieval latency/fee | Cost per retained GB và retrieval SLO |
| Tune log sampling | Giảm ingest/index cost | Giảm độ chi tiết một số trace/log | Incident investigation coverage |
| Commitment discount | Giảm unit price | Cam kết usage và flexibility | Effective savings sau utilization |

### 12.4. Net savings

Không tính gross savings mà bỏ qua chi phí chuyển đổi, license, engineering time, data transfer hoặc tăng support burden. Đo net savings và giữ baseline so sánh, bao gồm ảnh hưởng volume.

## 13. Commitment, discount và capacity planning

### 13.1. Khi nào commitment có lợi?

Commitment/reservation/savings plan có thể giảm effective rate cho usage tương đối ổn định. Trước khi mua, cần hiểu:

- Term, payment option và scope coverage.
- Flexibility theo instance family/region/platform.
- Utilization và coverage hiện tại.
- Forecast có thể thay đổi do migration/product roadmap không.
- Rủi ro stranded commitment nếu workload giảm hoặc đổi kiến trúc.

Không mua commitment chỉ vì discount rate cao. Nếu usage không được tận dụng, net savings có thể âm.

### 13.2. Coverage và utilization

- Coverage: tỷ lệ eligible usage được commitment bao phủ.
- Utilization: tỷ lệ commitment thực tế được sử dụng.

Coverage thấp có thể bỏ lỡ tiết kiệm; utilization thấp báo hiệu mua quá mức hoặc workload thay đổi. Đọc cả hai cùng forecast và flexibility.

### 13.3. Capacity planning

Cost forecast phải liên kết với capacity planning. Dự báo request, storage, queue, data transfer và replica; tính peak headroom và failure capacity. Capacity dư có thể là chi phí cần thiết để đáp ứng SLO; cần làm rõ phần nào là resilience reserve, phần nào là waste.

## 14. Cost anomaly có thể là tín hiệu bảo mật

### 14.1. Dấu hiệu cần chú ý

- Compute/GPU tăng ở region hoặc account không dùng trước đó.
- Egress đột biến ngoài giờ hoặc tới destination lạ.
- API call/KMS request tăng bất thường.
- Container/VM mới không có owner hoặc deployment record.
- IAM key mới, role assumption hoặc resource creation trái quy trình.
- Log bị tắt hoặc retention đổi cùng lúc chi phí biến động.

### 14.2. Kết hợp security telemetry

Cost anomaly detector chỉ cho biết chi phí lạ, không chứng minh compromise. Kết hợp cloud audit log, identity event, network flow, deployment record và runtime telemetry. Nếu nghi abuse, kích hoạt incident response, thu hồi credential theo quy trình và giữ evidence trước khi xóa resource.

### 14.3. Không auto-terminate dựa trên cost alert đơn lẻ

Một resource đắt có thể là workload quan trọng hoặc đang xử lý incident. Automated response cần confidence, allowlist, resource criticality, owner và policy. Có thể tự dừng sandbox có TTL hết hạn; production resource phải có kiểm tra sâu và approval phù hợp.

## 15. Governance và policy as code

### 15.1. Governance không phải chỉ là báo cáo

Policy có thể kiểm soát:

- Resource phải có owner, service và cost center.
- Environment tạm phải có expiry/TTL.
- Region và SKU được phép.
- Instance class hoặc accelerator cần approval.
- Storage encryption, backup và retention.
- Public IP/network egress.
- Budget owner và alert route.
- Tag schema và unallocated cost threshold.

### 15.2. Policy enforcement

Áp dụng qua IaC validation, cloud policy, admission control, account vending hoặc CI pipeline. Một số policy nên cảnh báo trước khi block để tránh làm gián đoạn workload hiện hữu. Với policy cứng, cần exception có owner, reason, expiry và audit.

### 15.3. Resource lifecycle

Resource tạm như test environment, snapshot tạm hoặc preview deployment cần TTL và cleanup automation. Cleanup phải xác minh resource không còn owner/use/retention; không xóa dữ liệu sản xuất dựa trên tag thiếu hoặc hết hạn một cách mù quáng.

## 16. Dashboard và review cadence

### 16.1. Dashboard cấp lãnh đạo

- Actual spend so với budget/forecast.
- Forecast cuối kỳ và variance.
- Spend theo product/business unit.
- Unit economics và xu hướng.
- Top anomalies/risks.
- Savings realized so với plan.
- Commitment coverage/utilization.
- Unallocated/shared cost.

### 16.2. Dashboard service owner

- Spend theo resource/service/region.
- Compute utilization và cost per request.
- DB/storage/network/observability breakdown.
- Cost anomaly và recent changes.
- SLO/latency/error cùng cost.
- Idle/orphan resources và optimization backlog.

### 16.3. Review cadence

| Nhịp | Cuộc review | Mục tiêu |
|---|---|---|
| Hàng ngày | Anomaly/overspend triage | Phát hiện nhanh biến động lớn |
| Hàng tuần | Service cost review | Driver, action và owner |
| Hàng tháng | Budget/forecast review | Variance, unit economics, forecast |
| Hàng quý | Architecture/commitment review | Rightsizing, contract, roadmap, resilience |

Nhịp thực tế tùy độ biến động. Workload đắt, thay đổi nhanh cần review thường xuyên hơn; shared platform ổn định có thể theo lịch dài hơn.

## 17. Quy trình phản hồi FinOps end-to-end

~~~mermaid
flowchart TD
    DATA[Billing and usage data] --> ALLOC[Normalize and allocate]
    ALLOC --> BASE[Budget, forecast and baseline]
    BASE --> DETECT[Detect variance and anomaly]
    DETECT --> TRIAGE[Owner triage and root cause]
    TRIAGE --> DECIDE{Expected or actionable?}
    DECIDE -->|Expected| UPDATE[Update forecast and context]
    DECIDE -->|Actionable| PLAN[Choose safe remediation]
    PLAN --> CHANGE[Implement change with review]
    CHANGE --> MEASURE[Measure cost and SLO outcome]
    MEASURE --> LEARN[Record learning and update guardrail]
    UPDATE --> LEARN
    LEARN --> ALLOC
~~~

### 17.1. Closed-loop action

Một vòng xử lý chỉ hoàn thành khi:

1. Có anomaly/finding với dữ liệu và owner.
2. Nguyên nhân được phân loại.
3. Quyết định được phê duyệt.
4. Thay đổi được triển khai an toàn.
5. Cost và service quality được đo lại.
6. Savings hoặc lý do không tối ưu được ghi nhận.
7. Forecast, policy hoặc runbook được cập nhật nếu cần.

### 17.2. Theo dõi savings realization

Savings dự kiến không bằng savings thực tế. Sau change, normalize theo volume/seasonality và so sánh với baseline. Ghi gross saving, implementation cost, recurring cost, quality impact và net saving. Nếu traffic tăng, bill có thể không giảm dù unit cost đã tốt hơn.

### 17.3. Học từ anomaly

Post-review nên trả lời:

- Alert có phát hiện đủ sớm không?
- Cost data có đủ chi tiết và chính xác không?
- Ownership/tag có đúng không?
- Hành động có an toàn và nhanh không?
- Có thể ngăn lặp lại bằng policy, automation hay kiến trúc không?
- Có ảnh hưởng SLO, security hoặc customer experience không?

## 18. Ví dụ: FinOps cho Booking Platform

### 18.1. Tình huống

Booking Platform có API, database, cache, queue, object storage và observability. Budget tháng là 40.000 đơn vị tiền tệ. Sau một chiến dịch marketing, projected spend cuối tháng tăng lên 52.000. Billing breakdown cho thấy compute tăng 20%, egress tăng 70% và log ingest tăng gấp đôi.

### 18.2. Triage

1. Đối chiếu campaign volume và completed bookings.
2. Kiểm tra compute scaling, request rate, CPU/memory và cost per request.
3. Dùng network flow để tìm egress cross-zone và response payload.
4. Kiểm tra logging release gần đây có bật debug hoặc capture payload.
5. So sánh SLO và error rate để phân biệt tăng trưởng hợp lệ với inefficiency.

### 18.3. Remediation

- Compute: rightsizing có kiểm chứng hoặc tối ưu autoscaling, giữ capacity reserve cho peak.
- Egress: cache catalog/reference data, giảm payload và xem lại placement; không di chuyển database chỉ vì bill nếu ảnh hưởng durability/residency.
- Logs: giảm debug volume, redact và sample theo policy; giữ audit/security logs bắt buộc.
- Forecast: cập nhật theo campaign và volume thực tế; xin budget adjustment nếu tăng trưởng có giá trị kinh doanh.

### 18.4. Đo kết quả

Theo dõi:

- Cost per completed booking.
- Egress GB per successful request.
- Log GB per request.
- p95/p99 latency, error rate và queue age.
- Actual/forecast so với budget mới.
- Savings thực tế sau khi chuẩn hóa volume.

Không đặt mục tiêu bill phải trở lại 40.000 bằng mọi giá nếu volume booking tăng hợp lệ và contribution margin đạt kỳ vọng. Quyết định cần được product, finance và engineering thống nhất.

## 19. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ xem tổng hóa đơn cuối tháng | Phát hiện anomaly muộn | Usage signal, forecast và alert theo ngày/giờ khi cần |
| Budget không có owner | Alert không dẫn tới hành động | Owner, escalation và runbook |
| Tag tùy tiện, thiếu chuẩn | Không phân bổ được chi phí | Taxonomy và policy as code |
| Chia đều shared cost | Unit economics sai lệch | Driver allocation được công bố |
| Chargeback quá sớm | Tranh chấp do dữ liệu thiếu tin cậy | Bắt đầu bằng showback và hoàn thiện model |
| Forecast chỉ dựa trên tháng trước | Bỏ qua campaign, roadmap và seasonality | Driver-based rolling forecast |
| Percentage anomaly trên baseline gần zero | Alert giả rất lớn | Kết hợp absolute threshold và epsilon |
| Coi mọi spike là waste | Chặn tăng trưởng hợp lệ | Context business, release và incident |
| Tắt logging để tiết kiệm | Mất khả năng điều tra/security evidence | Sampling, tiered retention và log hygiene |
| Mua commitment chỉ vì discount | Stranded commitment | Phân tích coverage, utilization và forecast |
| Rightsize chỉ theo CPU average | Tăng tail latency/outage | Đo peak, memory, I/O và SLO |
| Auto-delete resource đắt | Mất dữ liệu hoặc gây outage | Criticality, retention, owner và approval |
| Không đo savings sau change | Tiết kiệm chỉ tồn tại trên slide | Baseline normalization và savings realization |
| Không liên kết cost với SLO | Tối ưu sai mục tiêu | Dashboard cost + quality + business outcome |

## 20. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Biện pháp và đánh đổi |
|---|---|---|
| **Operational Excellence** | Có owner, forecast, anomaly workflow và review cadence không? | FinOps operating model, automation và post-review |
| **Security** | Cost anomaly có thể chỉ ra abuse hoặc credential compromise không? | Kết hợp audit/identity/network telemetry; bảo toàn evidence |
| **Reliability** | Tiết kiệm có làm giảm redundancy, backup hoặc capacity reserve? | Cost optimization có SLO gate và rollback |
| **Performance Efficiency** | Resource có được rightsize theo workload và tail latency? | Profile, load test, autoscaling và unit cost |
| **Cost Optimization** | Có allocation, forecast, anomaly detection và savings realization? | Budget, tagging, showback, commitment và lifecycle |
| **Sustainability** | Có tài nguyên idle, data retention và compute lặp không cần thiết? | Schedule, cleanup, data lifecycle và efficient processing |

FinOps tốt không chỉ làm bill thấp hơn. Nó giúp tổ chức hiểu chi phí để lựa chọn kiến trúc và mức dịch vụ có chủ đích, rồi kiểm chứng rằng quyết định tạo ra giá trị tốt hơn.

## 21. Bài tập áp dụng

### Bài tập A — Budget variance

Service có budget 10.000/tháng, actual hiện tại 8.500 vào ngày 20 và forecast cuối tháng 12.000.

**Câu hỏi:** Có nên đợi actual chạm 10.000 mới hành động?

**Gợi ý:** Không. Forecast đã dự báo vượt budget. Kiểm tra tốc độ spend, driver và business volume; gán owner và quyết định remediation/budget adjustment sớm.

### Bài tập B — Anomaly từ baseline nhỏ

Một project tăng spend 500% nhưng chỉ tăng từ 2 lên 12 đơn vị tiền tệ.

**Câu hỏi:** Vì sao percentage alert dễ gây hiểu lầm?

**Gợi ý:** Baseline nhỏ làm tỷ lệ lớn nhưng absolute impact thấp. Kết hợp mức tăng tuyệt đối, projected cost và criticality.

### Bài tập C — Shared cost

Platform team có 30% chi phí cluster và observability chưa phân bổ.

**Câu hỏi:** Có nên chia đều cho mọi product?

**Gợi ý:** Chỉ khi đó là driver hợp lý. Xem xét CPU/memory/request/ingest/tenant usage hoặc giữ một phần platform overhead. Công bố quy tắc và đo allocation coverage.

### Bài tập D — Commitment utilization thấp

Commitment có discount tốt nhưng utilization chỉ 55% trong ba tháng.

**Câu hỏi:** Cần làm gì?

**Gợi ý:** Kiểm tra forecast, scope/flexibility, workload migration và thời điểm mua. Không mua thêm; cân nhắc thay đổi cấu trúc workload hoặc điều chỉnh cam kết tương lai theo điều khoản.

### Bài tập E — Log cost spike

Sau release, log ingest tăng 3 lần. Đội muốn tắt toàn bộ logging.

**Câu hỏi:** Giải pháp nào cân bằng hơn?

**Gợi ý:** Xác định logger/field/level gây tăng, loại payload thừa, sample debug, điều chỉnh retention theo signal class; giữ security/audit log bắt buộc và kiểm tra khả năng điều tra.

### Bài tập F — Cost anomaly và compromise

Account tạo GPU instance ở region chưa từng sử dụng, egress tăng và xuất hiện IAM key mới.

**Câu hỏi:** Đây là task FinOps thông thường hay security incident?

**Gợi ý:** Có dấu hiệu compromise/abuse. Kích hoạt incident response, bảo toàn audit/network evidence, xác minh actor và workload, cô lập theo runbook; không chỉ terminate resource và đóng alert.

## 22. Checklist triển khai vòng phản hồi FinOps

- [ ] Có owner và cost taxonomy cho account, product, service, team và environment.
- [ ] Billing/usage data có freshness, currency, discount/credit và cost view được định nghĩa.
- [ ] Tag/label schema có validation và automation; unallocated spend được theo dõi.
- [ ] Shared cost có driver allocation rõ hoặc được công bố là platform overhead.
- [ ] Budget có scope, kỳ, owner, approver và alert route.
- [ ] Có guardrail phù hợp cho sandbox, production, GPU/high-cost resource và region mới.
- [ ] Forecast dựa trên traffic, business volume, roadmap, rate, seasonality và capacity.
- [ ] Có baseline theo workload và unit economics theo outcome nghiệp vụ.
- [ ] Anomaly detector kết hợp absolute spend, relative deviation, rate-of-change và forecast.
- [ ] Alert có owner, driver, data freshness, impact và runbook.
- [ ] Cost anomaly được đối chiếu với release, campaign, incident và security telemetry.
- [ ] Triage phân biệt expected growth, waste, inefficiency, misconfiguration và compromise.
- [ ] Remediation có đánh giá SLO, backup, data durability, security và rollback.
- [ ] Optimization backlog có baseline, net savings, effort, risk và success measure.
- [ ] Commitment được đánh giá bằng coverage, utilization, term và forecast.
- [ ] Dashboard hiển thị cost cùng latency, reliability, usage và business outcome.
- [ ] Có cadence daily/weekly/monthly/quarterly với người chịu trách nhiệm.
- [ ] Savings realization được đo sau change và chuẩn hóa theo volume/seasonality.
- [ ] Ngoại lệ budget/policy có reason, owner, expiry và audit.
- [ ] Post-review cập nhật forecast, policy, runbook và architecture backlog.

**Điểm cốt lõi:** vòng phản hồi FinOps bắt đầu từ dữ liệu chi phí có thể phân bổ, đi qua ngân sách và forecast, phát hiện biến động, điều tra theo owner, rồi thực hiện thay đổi an toàn và đo lại kết quả. Unit economics giúp liên kết bill với giá trị nghiệp vụ; anomaly detection cần cả mức tăng tuyệt đối lẫn baseline; remediation phải giữ SLO, bảo mật và độ bền dữ liệu. Khi finance, product và engineering cùng tham gia, tổ chức có thể kiểm soát chi phí mà vẫn đầu tư đúng vào tăng trưởng và độ tin cậy.

# Lập ngân sách, dự báo và đo chi phí trên mỗi yêu cầu hoặc tác vụ

Một hệ thống compute có thể đáp ứng SLO nhưng vẫn vượt ngân sách nếu đội vận hành chỉ theo dõi tổng hóa đơn mà không biết workload nào tạo ra chi phí. Ngược lại, giảm số VM hoặc đơn giá chưa chắc làm dịch vụ rẻ hơn nếu latency tăng, request retry nhiều hơn hoặc tỷ lệ tác vụ hoàn thành giảm.

Lập ngân sách compute cần kết nối ba góc nhìn:

- **Chi phí tài nguyên:** VM, container, serverless, GPU, storage, network và dịch vụ phụ trợ.
- **Nhu cầu workload:** số request, job, tenant, thời gian xử lý, tải nền và tải đỉnh.
- **Kết quả dịch vụ:** request thành công, tác vụ hoàn tất đúng hạn, SLO và chất lượng đầu ra.

Từ đó, tổ chức có thể dự báo chi phí theo tháng hoặc theo kịch bản, xác định chi phí trên mỗi request/job, tìm nguyên nhân biến động và chọn phương án tối ưu phù hợp. Bài học này trình bày quy trình xây dựng cost model từ dữ liệu usage, capacity và billing; cách phân bổ chi phí dùng chung; cách tính unit economics; và cách vận hành ngân sách theo vòng lặp FinOps.

## 1. Phân biệt ngân sách, dự báo và chi phí thực tế

Ba khái niệm có liên quan nhưng không giống nhau:

- **Budget (ngân sách):** mức chi tiêu được phê duyệt cho một phạm vi và một kỳ, thường là tháng, quý hoặc năm.
- **Forecast (dự báo):** ước lượng chi phí có khả năng phát sinh dựa trên tải, cấu hình, giá, chính sách và xu hướng mới nhất.
- **Actual (thực tế):** chi phí và usage được ghi nhận trong billing system sau khi dữ liệu được cập nhật hoặc chốt.

Ví dụ, nhóm đặt ngân sách compute tháng là 10.000 đơn vị tiền. Đến ngày 15, actual đã đạt 6.500 và forecast cuối tháng là 12.000. Budget vẫn là 10.000; forecast cho biết có khả năng vượt 2.000; actual là số đã phát sinh đến thời điểm hiện tại.

Không nên thay đổi budget để làm biểu đồ forecast trông như đang đúng. Budget là giới hạn được phê duyệt; forecast phải phản ánh tình hình dự kiến; actual phải lấy từ nguồn chi phí có thẩm quyền.

### Các phạm vi ngân sách thường dùng

- Toàn tổ chức hoặc account cloud.
- Business unit, team hoặc cost center.
- Product/service.
- Environment: production, staging, development, test.
- Region hoặc project.
- Workload hoặc tenant.
- Một chương trình migration hoặc dự án có thời hạn.

Mỗi phạm vi cần có owner, kỳ ngân sách, currency, quy tắc phân bổ shared cost và nguồn dữ liệu. Nếu hai báo cáo dùng phạm vi hoặc cách phân bổ khác nhau, số liệu sẽ không thể so sánh trực tiếp.

## 2. Xác định phạm vi chi phí compute

Chi phí compute không chỉ là giá VM. Một cost model nên phân tách các nhóm sau:

| Nhóm chi phí | Thành phần ví dụ | Đơn vị hoặc driver thường gặp |
|---|---|---|
| Compute | VM, instance group, container node, serverless, GPU | Instance-hour, vCPU-time, memory-time, request, GPU-hour |
| Storage | Block volume, file storage, object storage, snapshot, backup | GiB-month, IOPS, throughput, operation |
| Network | Egress, inter-zone/inter-region, NAT, public IP, load balancer | GB transferred, gateway-hour, capacity unit |
| Managed services | Database, cache, queue, stream, search | Instance-hour, storage, request, throughput tier |
| Software/license | OS, database, middleware, security agent | Core-hour, host-hour, user, subscription |
| Observability | Metrics, logs, traces, retention, query | Data ingest, GB-month, request/query |
| Shared platform | Cluster control plane, registry, CI/CD, support | Fixed fee hoặc allocation driver |
| Operations | Backup orchestration, security scanning, automation | Direct cost hoặc phân bổ theo workload |

Phạm vi cụ thể phụ thuộc mục tiêu báo cáo. Báo cáo unit cost của một API có thể tính cả database, cache, load balancer và network; báo cáo riêng compute infrastructure có thể chỉ gồm VM/container/GPU. Hãy công bố rõ chi phí nào được tính vào tử số.

### Chi phí trực tiếp và chi phí dùng chung

- **Direct cost:** có thể gắn tương đối chính xác với workload, ví dụ một GPU job chạy trên instance riêng.
- **Shared cost:** được nhiều workload sử dụng, ví dụ Kubernetes node dùng chung, NAT gateway, load balancer, observability workspace hoặc database cluster nhiều tenant.
- **Unallocated cost:** chưa có đủ metadata hoặc driver để phân bổ.

Không bỏ shared cost chỉ vì khó phân bổ. Nếu chỉ tính VM trực tiếp, unit cost của workload có thể thấp giả tạo. Cũng không nên phân bổ tùy tiện; cần ghi lại driver và giả định.

## 3. Xây cost model từ usage và pricing

Mô hình cơ bản:

\[
C_{total} = C_{compute} + C_{storage} + C_{network} +
C_{managed} + C_{license} + C_{observability} + C_{shared}
\]

Với mỗi nhóm, chi phí có thể được tính từ quantity và effective rate:

\[
C_i = \sum_j Q_{i,j} \times P_{i,j}
\]

Trong đó:
- \(Q_{i,j}\) là usage quantity của meter hoặc SKU j.
- \(P_{i,j}\) là đơn giá hiệu dụng tương ứng.
- \(C_i\) là chi phí của nhóm i.

Ví dụ:
- 500 instance-hours nhân giá mỗi instance-hour.
- 3.000 GiB-month nhân giá storage mỗi GiB-month.
- 2.000 GB egress nhân đơn giá theo tier.
- 10 triệu invocation nhân đơn giá request, cộng duration/memory-time nếu dịch vụ tính riêng.

### Giá niêm yết và giá hiệu dụng

Cần phân biệt:
- List price: giá niêm yết.
- Contract/negotiated price: giá theo hợp đồng.
- Effective price: giá hiệu dụng sau discount hoặc commitment allocation theo cách báo cáo.
- Net cost: chi phí sau các khoản điều chỉnh theo định nghĩa hệ thống.
- Invoice amount: số tiền thanh toán, có thể gồm thuế, credit và khoản ngoài usage.

Không lấy list price nhân usage rồi gọi đó là actual cost nếu tổ chức có discount, credit hoặc commitment. Đối chiếu với billing export và định nghĩa các cột trước khi xây báo cáo.

### Chi phí một lần và chi phí định kỳ

Một số khoản có thể phát sinh một lần:
- Data migration hoặc egress trong đợt chuyển.
- Tạo snapshot ban đầu.
- License onboarding.
- Thiết lập dedicated capacity.
- Chi phí triển khai hoặc hỗ trợ chuyên biệt.

Các khoản khác lặp lại theo giờ, ngày hoặc tháng. Forecast cần tách hai loại để tránh cộng chi phí migration một lần vào mọi tháng sau đó.

## 4. Xác định đơn vị đầu ra để tính unit cost

Unit cost chỉ có ý nghĩa khi mẫu số phản ánh kết quả mà dịch vụ cần tạo ra.

Các đơn vị có thể dùng:
- Mỗi request nhận vào.
- Mỗi request thành công.
- Mỗi request thành công trong SLO.
- Mỗi transaction hoàn tất.
- Mỗi job hoàn tất.
- Mỗi job hoàn tất đúng deadline.
- Mỗi GB dữ liệu xử lý.
- Mỗi ảnh/video được render đạt chất lượng.
- Mỗi giờ inference hoặc mỗi nghìn token, nếu phù hợp workload.
- Mỗi tenant hoạt động trong một tháng.

### Cost per request

Hai chỉ số thường hữu ích:

\[
CostPerAttempt = \frac{AllocatedCost}{TotalAttempts}
\]

\[
CostPerSuccessfulRequest =
\frac{AllocatedCost}{SuccessfulRequests}
\]

Nếu request thất bại hoặc retry tiêu tốn tài nguyên, chi phí vẫn nằm trong tử số. Khi mẫu số chỉ đếm request thành công, chỉ số sẽ phản ánh chi phí thực tế để tạo ra kết quả thành công.

Có thể bổ sung cost per successful on-time request:

\[
CostPerOnTimeSuccess =
\frac{AllocatedCost}{SuccessfulRequestsWithinSLO}
\]

Đây là chỉ số hữu ích khi latency và deadline là yêu cầu quan trọng. Cần định nghĩa rõ request nào được tính là hợp lệ và cách xử lý request bị hủy bởi client.

### Cost per task

Với batch hoặc worker:

\[
CostPerCompletedTask =
\frac{Compute + Storage + Network + Retry + SharedCost}
{CompletedTasks}
\]

Nếu có task hoàn tất nhưng đầu ra không đạt chất lượng hoặc không được chấp nhận, cần định nghĩa thêm **accepted task** hoặc **successful business outcome** để tránh mẫu số quá rộng.

### Cost per unit of work

Một số workload không có khái niệm request rõ ràng. Có thể dùng:
- Chi phí trên mỗi GB ETL.
- Chi phí trên mỗi bản ghi xử lý.
- Chi phí trên mỗi phút video render.
- Chi phí trên mỗi inference với batch size xác định.
- Chi phí trên mỗi report tạo thành công.

Đơn vị đầu ra phải ổn định, có thể đo và liên quan tới giá trị kinh doanh.

## 5. Average unit cost và marginal cost

Hai loại chi phí trả lời hai câu hỏi khác nhau.

- **Average unit cost:** tổng chi phí phân bổ chia cho tổng số đơn vị đầu ra.
- **Marginal cost:** chi phí tăng thêm khi xử lý thêm một đơn vị công việc.

\[
AverageUnitCost = \frac{TotalCost}{TotalOutput}
\]

\[
MarginalCost \approx
\frac{\Delta TotalCost}{\Delta Output}
\]

Ví dụ, một cụm có chi phí cố định 1.000 đơn vị tiền/tháng và xử lý 10 triệu request. Average cost là 0,0001 đơn vị tiền/request. Nếu cụm còn capacity nhàn rỗi, thêm 1 triệu request có thể chỉ làm tăng network hoặc database usage một phần nhỏ; marginal cost thấp hơn average.

Khi tải vượt capacity, hệ thống cần thêm node hoặc nâng database tier. Marginal cost có thể tăng theo bậc thay vì tuyến tính.

### Vì sao average cost có thể gây hiểu nhầm?

- Chi phí commitment được phân bổ vào kỳ dù usage thấp.
- Shared platform cost được chia đều dù workload tiêu thụ không đều.
- Một tenant có burst có thể buộc cả cụm mở thêm node.
- Retry và lỗi có thể tăng chi phí mà output không tăng.
- Capacity dự phòng làm tăng average cost nhưng giúp đạt availability.

Khi ra quyết định pricing, capacity hoặc optimization, hãy xem average và marginal cùng với SLO.

## 6. Đo output và chi phí trong cùng một khoảng thời gian

Để tính unit cost chính xác, numerator và denominator phải có cùng:
- Time window.
- Workload boundary.
- Region/environment.
- Tenant hoặc service scope.
- Currency và cost basis.
- Trạng thái dữ liệu (provisional hay finalized).

Ví dụ, không chia cost tháng 11 cho số request chỉ trong 20 ngày đầu tháng. Không chia chi phí production cho output gồm cả staging nếu staging không nằm trong cùng phạm vi.

### Độ trễ billing

Billing export có thể đến trễ hoặc được điều chỉnh sau kỳ sử dụng. Output metric thường có sẵn gần thời gian thực. Báo cáo unit cost hôm nay có thể tạm dùng estimated cost, nhưng cần đánh dấu provisional và cập nhật khi billing finalized.

### Đồng bộ timestamp

Nên dùng UTC hoặc timezone được chuẩn hóa. Cần tính đến:
- Usage start/end.
- Event time.
- Ingestion time.
- Invoice period.
- Request completion timestamp.
- Job accepted/completed timestamp.

Nếu cost được ghi theo ngày UTC còn output được tổng hợp theo ngày địa phương, cần chuyển cùng timezone trước khi so sánh.

## 7. Phân bổ shared cost

Shared cost có thể được phân bổ bằng một driver phản ánh mức tiêu thụ hoặc lợi ích mà workload nhận được.

| Shared resource | Driver có thể dùng | Lưu ý |
|---|---|---|
| Kubernetes node compute | CPU request, CPU usage, memory request/usage | Chọn quy tắc nhất quán; tính cả system overhead |
| Database cluster | Query time, connection time, storage, workload tag | Query count đơn thuần có thể không phản ánh độ nặng |
| NAT/network gateway | Bytes, connections hoặc flow count | Egress và connection cost có thể khác nhau |
| Load balancer | Request count, processed bytes, capacity share | Request phức tạp có thể tiêu tốn không đồng đều |
| Observability | Log/trace ingest, metric series hoặc retention | Cardinality và retention tạo cost khác nhau |
| Shared storage | Dung lượng, IOPS, throughput hoặc object count | Dung lượng không phản ánh mọi mức sử dụng |
| Platform operations | Fixed share, instance count hoặc team allocation | Nêu rõ đây là overhead phân bổ |

### Ví dụ phân bổ node

Một node có chi phí 120 đơn vị tiền trong ngày. Ba workload có CPU usage tích lũy tương ứng 50%, 30% và 20% tổng CPU usage được phân bổ. Nếu chọn CPU usage làm driver, chi phí được phân bổ:

| Workload | Tỷ trọng driver | Chi phí được phân bổ |
|---|---:|---:|
| API | 50% | 60 |
| Worker | 30% | 36 |
| Reporting | 20% | 24 |
| **Tổng** | **100%** | **120** |

Nếu mục tiêu là chargeback theo capacity đã giữ, có thể dùng request thay cho usage. Nếu mục tiêu là phản ánh tài nguyên thực sự tiêu thụ, usage có thể phù hợp hơn. Không có driver duy nhất đúng cho mọi báo cáo.

### Idle capacity và dự phòng

Một cụm có thể giữ capacity dư để đáp ứng burst hoặc failover. Có thể phân bổ chi phí idle theo:
- Tỷ trọng capacity reserved của mỗi workload.
- Tỷ trọng demand tại giờ peak.
- Tỷ trọng sử dụng trung bình.
- Một khoản platform overhead chung.

Không nên phân bổ toàn bộ idle cost cho workload đang chạy nhiều nhất nếu capacity được giữ vì yêu cầu HA của toàn sản phẩm. Cần ghi lại lý do và policy phân bổ.

## 8. Xây dựng inventory và nguồn dữ liệu

Cost model cần kết hợp nhiều nguồn:

| Nguồn | Dữ liệu chính | Dùng để |
|---|---|---|
| Cloud billing export | SKU, quantity, rate, cost, account, region, resource ID | Actual cost |
| Resource inventory | Instance, disk, IP, cluster, service, tags | Xác định phạm vi và owner |
| Lifecycle events | Start/stop, scale, resize, terminate | Giải thích runtime và capacity |
| Metrics | CPU, memory, network, storage, concurrency | Hiểu utilization và headroom |
| Application telemetry | Request, error, latency, job outcome | Đo output và SLO |
| Queue/batch system | Enqueue, retry, complete, dead-letter | Đo task và công việc bị lặp |
| Pricing catalog | SKU và rate theo region/time | Lập forecast |
| Finance/contract | Discount, commitment, tax, credit, currency | Tính effective cost |

### Chuẩn hóa resource identity

Dùng resource ID ổn định để liên kết billing với inventory. Hostname hoặc pod name có thể thay đổi khi scale hoặc rollout.

Nhãn nên có:
- service.
- environment.
- owner/team.
- cost center.
- product/project.
- region.
- tenant nếu chính sách cho phép.
- lifecycle hoặc expiry.

Không đưa request ID hoặc user ID vào resource tag. Định danh từng request nên nằm trong trace/log, không phải cost allocation tag.

### Chất lượng dữ liệu

Trước khi forecast:
- Kiểm tra resource không có owner.
- Kiểm tra SKU không map được.
- Kiểm tra currency.
- Kiểm tra cost âm do credit/adjustment.
- Kiểm tra duplicate hoặc delayed billing record.
- Kiểm tra output metric thiếu hoặc reset.
- Kiểm tra tag coverage.
- Kiểm tra resource đã xóa nhưng còn charge phụ.

Dữ liệu không đầy đủ cần được đánh dấu, không tự coi là zero.

## 9. Phương pháp dự báo chi phí

Có thể kết hợp ba cách dự báo.

### Bottom-up theo workload

Tính từ demand và cấu hình:
1. Dự báo số request/job.
2. Ước lượng throughput an toàn mỗi instance.
3. Tính số instance hoặc resource cần theo thời gian.
4. Tính compute-hours hoặc resource-time.
5. Cộng storage, network, managed service, license và shared cost.
6. Áp effective price và discount.

Cách này phù hợp với workload có metric và capacity model tốt.

### Run-rate từ actual

Lấy actual trong một khoảng gần nhất rồi ngoại suy theo số ngày còn lại. Ví dụ chi phí 10 ngày đầu tháng là 3.000, run-rate đơn giản cho tháng 30 ngày là 9.000.

Run-rate hữu ích để cảnh báo sớm nhưng có thể sai nếu:
- Tải theo mùa vụ.
- Có ngày campaign.
- Một đợt migration hoặc backup.
- Billing delay.
- Chi phí một lần.
- Commitment hoặc credit được ghi theo kỳ khác.

### Top-down theo tăng trưởng

Bắt đầu từ doanh thu, người dùng, tenant hoặc sản lượng kinh doanh dự kiến rồi quy đổi sang workload. Ví dụ số người dùng tăng 20% không nhất thiết làm request tăng đúng 20%; cần biết mức hoạt động, caching và request/user.

Top-down hữu ích cho kế hoạch quý/năm, nhưng cần đối chiếu bottom-up để kiểm tra capacity và pricing.

## 10. Forecast compute từ demand và capacity

Với workload chạy trên VM hoặc node cố định trong từng khoảng:

\[
ComputeCost = \sum_t N_t \times H_t \times P_t
\]

Trong đó:
- \(N_t\) là số instance billable trong khoảng t.
- \(H_t\) là thời lượng của khoảng.
- \(P_t\) là đơn giá mỗi instance-hour phù hợp.

Nếu instance type thay đổi, tách theo SKU. Với autoscaling, có thể dùng profile số instance theo giờ hoặc ngày thay vì lấy desired capacity cuối kỳ nhân toàn bộ tháng.

### Ước lượng số instance

Nếu một instance xử lý an toàn \(Q_{safe}\) request/giây và nhu cầu là \(D_t\):

\[
N_t = \left\lceil \frac{D_t}{Q_{safe}} \right\rceil
\]

Cần cộng capacity cho:
- N-1 instance/AZ failure.
- Rolling deployment surge.
- Autoscaling delay.
- Burst và traffic uncertainty.
- Workload background.
- Headroom theo SLO.

Không cộng headroom hai lần nếu \(Q_{safe}\) đã được đo với utilization target và failure reserve.

### Forecast theo thời gian

Một hệ thống có tải cao vào ban ngày và thấp vào ban đêm không nên dự báo bằng average 24 giờ nếu autoscaler scale theo giờ. Chia thời gian thành các interval:
- Business hours.
- Night hours.
- Weekend.
- Campaign/peak.
- Batch window.
- Maintenance window.

Tính capacity và cost từng interval rồi cộng lại. Đây là cách phản ánh schedule và autoscaling tốt hơn.

## 11. Kịch bản low, base và high

Forecast luôn có bất định. Thay vì một con số duy nhất, hãy xây ba kịch bản:

- **Low:** nhu cầu thấp hơn dự kiến, tối ưu utilization tốt, không có sự cố lớn.
- **Base:** dự báo có xác suất cao nhất theo kế hoạch hiện tại.
- **High:** tăng trưởng hoặc burst cao, giá/egress thay đổi, retry hoặc capacity reserve tăng.

Ví dụ:

| Driver | Low | Base | High |
|---|---:|---:|---:|
| Request/tháng | 60 triệu | 80 triệu | 110 triệu |
| Peak multiplier | 1,5x | 2x | 2,5x |
| Instance cần ở peak | 5 | 7 | 10 |
| Egress | 1,2 TB | 1,8 TB | 2,8 TB |
| Retry overhead | 1% | 3% | 7% |
| Dự phòng capacity | 10% | 20% | 30% |

Các số trong bảng là giả định minh họa. Mỗi kịch bản cần được chuyển thành usage quantity và cost theo SKU, không chỉ nhân tổng hóa đơn với một hệ số tùy ý.

### Scenario driver

Thay đổi một số driver rõ ràng:
- Request growth.
- Average payload size.
- Cache hit ratio.
- CPU time per request.
- DB query time.
- Retry rate.
- Peak-to-average ratio.
- Number of replicas.
- Price/discount.
- Storage retention.
- Egress per request.

Nhờ vậy, khi forecast thay đổi, người xem biết yếu tố nào gây ra delta.

### Sensitivity analysis

Tính mức độ ảnh hưởng khi một driver thay đổi. Ví dụ egress cost có thể tăng mạnh nếu response payload lớn hơn; compute cost có thể tăng bậc khi peak vượt capacity hiện tại và cần thêm replica.

Không giả định mọi cost tăng tuyến tính theo request volume. Một số khoản fixed, một số variable, một số stepwise và một số có tier pricing.

## 12. Fixed, variable và stepwise cost

Phân loại cost behavior giúp forecast tốt hơn:

- **Fixed:** gần như không đổi trong phạm vi hoạt động nhất định, ví dụ một khoản subscription hoặc minimum platform fee.
- **Variable:** thay đổi theo usage, ví dụ request, egress hoặc invocation.
- **Stepwise:** giữ nguyên trong một khoảng rồi tăng khi vượt ngưỡng, ví dụ thêm VM, thêm database tier hoặc mở thêm node.
- **Hybrid:** gồm phần cố định và phần biến đổi, ví dụ một cluster có baseline node và autoscaling node.

Một model đơn giản:

\[
C = F + v \times U
\]

Trong đó \(F\) là fixed cost, \(v\) là variable rate và \(U\) là usage. Với stepwise cost, cần thêm điều kiện capacity hoặc tier.

### Ví dụ stepwise

Một VM có thể xử lý an toàn 1.000 request/giây. Nếu peak là 900 request/giây, nhóm có thể chạy 1 VM. Khi peak tăng lên 1.100, có thể cần 2 VM. Chi phí compute gần như tăng gấp đôi dù demand chỉ tăng 22%.

Đây là lý do forecast cần dùng capacity threshold và không chỉ lấy chi phí hiện tại nhân tỷ lệ tăng request.

## 13. Dự báo theo mô hình pricing

### On-demand

Tính usage theo meter và đơn giá hiện hành. Phù hợp làm baseline linh hoạt, nhưng cần dự báo runtime, scale profile và các resource phụ.

### Reserved/committed use

Cam kết có thể giảm đơn giá nhưng tạo nghĩa vụ chi trả hoặc coverage trong kỳ. Khi forecast:
- Tính usage đủ điều kiện được coverage.
- Tách committed amount và on-demand spillover.
- Phân bổ commitment theo policy.
- Theo dõi utilization/coverage của commitment.
- Tính phần không sử dụng nếu có.
- Xem ngày bắt đầu/kết thúc và thay đổi workload.

Một commitment rẻ hơn trên mỗi unit chưa chắc giảm tổng cost nếu usage thấp hơn mức cam kết. Cần so total cost theo kịch bản, không chỉ so unit rate.

### Spot/preemptible

Giá thấp hơn nhưng có thể bị thu hồi. Cost model cần tính:
- Thời gian compute hữu ích.
- Work bị mất khi interruption.
- Checkpoint storage và transfer.
- Retry/restart overhead.
- Fallback sang on-demand.
- Job completion rate và deadline.

Đơn giá thấp nhưng retry nhiều có thể làm cost per successful task cao hơn.

### Serverless

Tính:
- Request/invocation count.
- Duration.
- Memory hoặc CPU allocation.
- Provisioned/warm concurrency.
- Retry và timeout.
- Data transfer và dependency.

Với workload chạy liên tục, so sánh serverless với VM/container theo tổng cost ở cùng throughput và SLO.

### GPU/accelerator

Không chỉ tính GPU-hour. Cần tính:
- GPU count/type.
- CPU/RAM host.
- Storage throughput và checkpoint.
- Network bandwidth.
- Idle GPU time.
- Batch size và utilization.
- Failed/aborted training time.
- License và accelerator software stack.

Unit economics có thể là cost per training step, per model run, per inference hoặc per accepted output.

## 14. Tính cost per request cho API

Một API thường có nhiều thành phần cost. Cost model có thể gồm:

\[
C_{API} = C_{app} + C_{database} + C_{cache} +
C_{network} + C_{loadbalancer} + C_{observability} + C_{shared}
\]

### Ví dụ minh họa theo tháng

Giả sử một API có các chi phí được phân bổ như sau:

| Thành phần | Chi phí tháng (đơn vị tiền) |
|---|---:|
| Application VM | 613,20 |
| Worker VM | 197,10 |
| Managed database | 900,00 |
| Cache | 180,00 |
| Storage/backup | 120,00 |
| Network egress | 240,00 |
| Load balancer/NAT | 80,00 |
| Observability | 110,00 |
| Shared platform | 160,00 |
| **Tổng** | **2.600,30** |

Trong tháng:
- 90 triệu request attempts.
- 80 triệu request thành công.
- 76 triệu request thành công trong SLO.

Cost per attempt:

\[
2600.30 / 90{,}000{,}000
\approx 0.00002889
\]

Cost per successful request:

\[
2600.30 / 80{,}000{,}000
\approx 0.00003250
\]

Cost per successful on-time request:

\[
2600.30 / 76{,}000{,}000
\approx 0.00003421
\]

Cost trên mỗi 1.000 successful requests xấp xỉ 0,03250 đơn vị tiền. Đây là ví dụ số học, không phải đơn giá cloud thực tế.

### Đọc kết quả

Nếu cost per successful request tăng, có thể do:
- Chi phí tăng nhanh hơn output.
- Tỷ lệ request thành công giảm.
- Retry hoặc timeout tăng.
- Cache hit ratio giảm.
- Database query chậm làm worker giữ lâu hơn.
- Peak traffic buộc giữ thêm capacity.
- Giá hoặc egress thay đổi.

Không kết luận phải resize VM ngay. Phân rã cost theo thành phần và so với request mix, SLO trước khi thay đổi.

## 15. Tính cost per batch task

Với batch worker, nên tính chi phí của cả vòng đời task:

\[
C_{task} =
C_{compute} + C_{storage} + C_{network} +
C_{checkpoint} + C_{retry} + C_{orchestration}
\]

Ví dụ một batch có 10.000 task:
- Compute worker: 0,80 đơn vị tiền.
- Checkpoint/storage: 0,15.
- Data transfer: 0,05.
- Retry overhead: 0,20.
- Tổng: 1,20.
- Task hoàn tất và được chấp nhận: 9.600.

\[
CostPerAcceptedTask = 1.20 / 9600 = 0.000125
\]

Nếu tối ưu làm retry giảm từ 0,20 xuống 0,05 nhưng compute không đổi, cost per accepted task giảm. Nếu chỉ nhìn VM price, lợi ích này có thể bị bỏ sót.

### Batch có thời lượng khác nhau

Có thể tính:
- Cost per task.
- Cost per CPU-second.
- Cost per GB processed.
- Cost per successful batch.
- Cost per deadline-compliant batch.

Chọn metric phù hợp với công việc. Một task lớn có thể tốn tài nguyên gấp nhiều lần task nhỏ; cost per task đơn giản có thể không công bằng. Có thể phân nhóm theo size hoặc complexity.

## 16. Forecast theo tháng và theo quý

Một forecast thực tế nên có:
- Actual-to-date.
- Estimate cho phần còn lại của kỳ.
- One-time cost.
- Run-rate.
- Seasonal adjustment.
- Price/discount assumption.
- Capacity plan.
- Low/base/high.
- Confidence level và owner.

### Forecast tháng

Có thể chia:
- Actual từ đầu tháng đến ngày chốt dữ liệu.
- Forecast từng ngày/tuần còn lại.
- Chi phí định kỳ.
- Chi phí dự án hoặc migration một lần.
- Credit/adjustment dự kiến.

Không dùng run-rate đơn giản nếu tháng có campaign hoặc workload batch định kỳ. Thay bằng profile theo ngày trong tuần và lịch sự kiện.

### Forecast quý/năm

Dùng các driver dài hạn:
- Tăng trưởng user/tenant.
- Request per active user.
- Payload size.
- Tỷ lệ feature mới.
- Retention.
- Region expansion.
- Replica count.
- Pricing/commitment renewal.
- Thay đổi kiến trúc hoặc migration.

Đặt ngày rà soát giả định. Một forecast 12 tháng cần được cập nhật khi traffic, SKU, price hoặc architecture thay đổi.

## 17. Xây bảng forecast có thể kiểm tra

Một workbook hoặc bảng dữ liệu nên có các tab/phần:

### Assumptions

- Currency và kỳ forecast.
- Region và SKU.
- Effective rate.
- Demand growth.
- CPU time/request.
- Memory/request.
- Egress/request.
- Cache hit ratio.
- Retry rate.
- Capacity per instance.
- Headroom và availability reserve.
- Commitment coverage.
- Shared cost allocation policy.

### Workload forecast

- Requests/jobs theo ngày hoặc tháng.
- Peak/average ratio.
- Success rate.
- On-time success rate.
- Payload/data processed.
- Retry count.
- Tenant/product mix.

### Resource forecast

- Instance count theo interval.
- Instance-hours hoặc resource-time.
- Storage provisioned/consumed.
- Network transfer.
- DB/cache/queue capacity.
- GPU-hours.
- Warm/provisioned capacity.
- Rollout/failover reserve.

### Cost forecast

- Quantity theo meter.
- Unit rate.
- Discount/commitment.
- Direct cost.
- Shared cost.
- One-time cost.
- Tax/credit nếu phạm vi cần.
- Total low/base/high.

### Unit economics

- Cost per attempt.
- Cost per success.
- Cost per on-time success.
- Cost per job/GB/output.
- Marginal cost.
- SLO và quality indicators.

### Actual vs forecast

- Budget.
- Actual.
- Forecast.
- Variance amount.
- Variance percent.
- Driver explanation.
- Owner.
- Action/date.

## 18. Variance analysis: giải thích chênh lệch

Variance:

\[
Variance = Actual - Budget
\]

Variance percentage:

\[
Variance\% = \frac{Actual - Budget}{Budget} \times 100\%
\]

Nếu actual lớn hơn budget, variance dương theo quy ước này. Một số tổ chức dùng dấu ngược để biểu thị favorable/unfavorable; hãy thống nhất quy ước trong dashboard.

### Phân rã variance

Có thể phân rã thành:
- Volume variance: request/job nhiều hơn dự báo.
- Rate variance: đơn giá hoặc SKU thay đổi.
- Mix variance: tỷ lệ workload hoặc loại instance thay đổi.
- Efficiency variance: CPU time, retry hoặc resource per request tăng.
- Capacity variance: thêm replica, failover reserve hoặc idle capacity.
- Shared allocation variance: driver phân bổ thay đổi.
- One-time variance: migration, incident hoặc project cost.
- Billing timing: dữ liệu đến trễ hoặc adjustment.

### Ví dụ

Actual cost tăng 15% so với forecast. Phân tích cho thấy:
- Request tăng 8%.
- Egress/request tăng 4% do payload lớn hơn.
- Retry rate tăng từ 2% lên 4%.
- Một database tier được nâng trong tuần cuối tháng.

Không nên mô tả chung là “cloud bill tăng”. Gắn variance với driver giúp chọn hành động đúng: tối ưu payload, sửa lỗi retry, kiểm tra query hoặc cập nhật forecast capacity.

## 19. Ngân sách và guardrail

Budget alert nên được thiết lập theo nhiều mức:
- Cảnh báo khi đạt 50%, 75%, 90% budget.
- Dự báo cuối kỳ vượt budget.
- Một service có unit cost tăng nhanh.
- Một project có resource không gắn owner.
- Một SKU hoặc region phát sinh usage bất thường.
- Commitment utilization thấp.
- Spot fallback làm tăng on-demand spend.
- GPU idle hoặc serverless provisioned capacity ít sử dụng.

### Budget không phải công tắc tắt hệ thống

Không tự động dừng production chỉ vì budget đạt 100%. Hành động cần theo severity và policy:
- Thông báo owner.
- Xác minh anomaly.
- Dừng resource dev/test không cần thiết.
- Giảm non-critical batch hoặc defer công việc.
- Hạ mức log retention nếu policy cho phép.
- Điều chỉnh autoscaling guardrail an toàn.
- Xin phê duyệt tăng ngân sách khi tải hợp lệ.

Production guardrail phải giữ SLO và availability. Cost control cần phân biệt workload bắt buộc, workload có thể trì hoãn và workload có thể dừng.

### Anomaly detection

So sánh actual với baseline theo:
- Cùng ngày trong tuần.
- Cùng giờ.
- Cùng mức request.
- Cùng số tenant.
- Cùng deployment version.

Một đợt tăng cost có thể là tăng trưởng hợp lệ. Cần kết hợp usage, output và SLO để phân biệt anomaly với demand tăng.

## 20. FinOps: vận hành cost model theo vòng lặp

FinOps kết nối engineering, finance và product để quản lý chi phí cloud theo giá trị tạo ra.

Một vòng lặp thực tế:

1. **Inform:** thu thập cost, usage, ownership, output và SLO.
2. **Optimize:** rightsizing, schedule, autoscale, cache, improve efficiency, pricing model.
3. **Operate:** đặt budget, forecast, owner, policy và review định kỳ.
4. **Measure:** kiểm tra unit cost, variance, quality và business outcome.
5. **Repeat:** cập nhật giả định và hành động theo dữ liệu mới.

### Vai trò

- Engineering đo resource usage, capacity và performance.
- Finance quản lý budget, invoice, commitment và forecast.
- Product xác định output, demand, feature mix và value.
- Platform/FinOps xây tagging, allocation, dashboard và policy.

Không nên giao toàn bộ cloud cost cho finance nếu engineering không có metric workload; cũng không nên để engineering tối ưu đơn giá mà không biết giá trị kinh doanh.

## 21. Chọn hành động tối ưu từ unit economics

| Dấu hiệu | Hành động có thể thử | Metric xác nhận |
|---|---|---|
| CPU thấp kéo dài, VM billable cả đêm | Schedule, scale down hoặc resize | Instance-hours, p95, cost/request |
| CPU cao, throughput không tăng | Profile, tune worker hoặc tăng capacity đúng chỗ | CPU, queue, throughput, p99 |
| Retry rate tăng | Sửa lỗi dependency, backoff/jitter, idempotency | Retry cost, success rate |
| Egress/request cao | Nén payload, cache, giảm response hoặc thay route | GB/request, latency, cost/success |
| DB cost tăng nhanh | Query optimization, cache, connection tuning | Query cost, DB CPU, p95 |
| Shared node idle nhiều | Bin packing, node pool sizing, autoscaling | Node-hours, utilization, unit cost |
| Commitment utilization thấp | Điều chỉnh coverage khi renewal | Commitment waste, effective rate |
| GPU utilization thấp | Batch, schedule, right-size accelerator | GPU-hours/output, idle GPU |
| Serverless provisioned capacity nhàn rỗi | Tune provisioned concurrency hoặc warm pool | Cold start, provisioned cost, SLO |
| Cost/request giảm nhưng lỗi tăng | Kiểm tra trade-off chất lượng | Success/on-time rate, error, customer impact |

Mỗi optimization nên có:
- Baseline.
- Giả thuyết.
- Thay đổi nhỏ và có thể rollback.
- SLO guardrail.
- Cost measurement.
- Kết quả trước/sau.
- Owner và thời điểm review.

Không ghi nhận tiết kiệm chỉ dựa trên giá niêm yết. Xác nhận bằng actual cost hoặc forecast đã điều chỉnh theo demand và scope tương đương.

## 22. Những sai lầm thường gặp

1. **Chỉ forecast bằng tổng hóa đơn tháng trước.** Cách này bỏ qua growth, seasonality, SKU và thay đổi kiến trúc.
2. **Dùng request attempts làm mẫu số duy nhất.** Retry và lỗi có thể làm unit cost thành công bị che khuất.
3. **Bỏ shared cost.** Unit cost thấp giả tạo và khó đối chiếu với tổng bill.
4. **Phân bổ shared cost không có policy.** Các team không thể giải thích hoặc so sánh số liệu.
5. **Dùng CPU average để dự báo instance count.** Peak, queue, DB, memory và AZ reserve có thể quyết định capacity.
6. **Giả định cost tăng tuyến tính theo request.** Autoscaling và tier pricing tạo stepwise cost.
7. **Bỏ qua retry và failed work.** Compute đã tiêu thụ vẫn phát sinh chi phí dù không có output.
8. **Không tách one-time cost.** Migration hoặc incident làm sai forecast các tháng sau.
9. **Nhầm list price với effective cost.** Discount/commitment có thể làm đơn giá thực khác.
10. **Không tính commitment waste.** Rate thấp nhưng usage không đủ có thể tăng tổng cost.
11. **Không thống nhất time window.** Numerator và denominator khác kỳ tạo unit cost sai.
12. **Tối ưu cost bằng cách làm giảm SLO.** Cost per success cần xem cùng latency, availability và quality.
13. **Không có owner cho variance.** Không ai chịu trách nhiệm điều tra hoặc hành động.
14. **Dùng dữ liệu billing chưa finalized mà không gắn nhãn.** Forecast và actual có thể sai lệch do ingestion delay.

## 23. Ví dụ tổng hợp: forecast và unit cost của API

Một API hiện xử lý 80 triệu request thành công mỗi tháng. Nhóm dự báo tăng trưởng 10% mỗi tháng trong quý tới. Capacity test cho thấy mỗi instance xử lý an toàn 12 triệu request/tháng theo profile tải hiện tại, nhưng cần thêm 20% capacity reserve cho peak và failover.

### Tính capacity

Nhu cầu tháng đầu của forecast:

\[
80M \times 1.10 = 88M
\]

Số instance theo throughput an toàn:

\[
\lceil 88 / 12 \rceil = 8
\]

Nếu capacity reserve 20% chưa được tính trong Q_safe, cần cộng theo policy và làm tròn phù hợp. Nếu Q_safe đã đo với headroom đó, không cộng thêm lần nữa.

### Forecast cost

Tách cost:
- Application compute theo instance-hours.
- Worker compute theo job volume.
- Database theo tier và storage.
- Cache theo memory capacity.
- Network theo egress/request.
- Observability theo ingest volume.
- Shared platform theo allocation rule.

Dự báo từng tháng với request growth, peak profile và pricing assumptions. Khi request tăng nhưng cache hit ratio tốt hơn, database cost có thể tăng chậm hơn compute. Nếu payload lớn hơn, network cost có thể tăng nhanh hơn request count.

### Theo dõi unit economics

Mỗi tháng báo cáo:
- Cost per attempt.
- Cost per successful request.
- Cost per successful on-time request.
- Cost per 1.000 requests.
- Error/retry rate.
- p95/p99 latency.
- Cost breakdown theo thành phần.

Nếu cost/request giảm nhưng p99 vượt SLO, optimization chưa đạt mục tiêu. Nếu cost/request tăng do giữ thêm HA reserve nhưng availability cải thiện theo mục tiêu, cần đánh giá theo giá trị dịch vụ và risk reduction.

## 24. Checklist xây ngân sách và unit economics

### Phạm vi và dữ liệu
- [ ] Đã xác định kỳ, currency, service và environment.
- [ ] Đã định nghĩa chi phí direct, shared và excluded.
- [ ] Billing export có SKU, quantity, unit, region và cost basis.
- [ ] Resource inventory có ID, owner và tags.
- [ ] Output metric có request/job success và timestamp.
- [ ] Billing data delay và finalized state được đánh dấu.

### Cost model
- [ ] Compute, storage, network, managed service và license được tách.
- [ ] One-time cost được tách khỏi recurring cost.
- [ ] List price và effective/net cost không bị trộn.
- [ ] Commitment, credit và Spot/fallback được tính đúng.
- [ ] Shared cost có allocation driver và policy.
- [ ] Idle/HA reserve được phân bổ có giải thích.

### Forecast
- [ ] Có bottom-up, run-rate hoặc top-down phù hợp.
- [ ] Demand forecast có peak và seasonality.
- [ ] Capacity dùng throughput an toàn và SLO.
- [ ] Có low/base/high scenario.
- [ ] Có sensitivity với retry, payload, price và growth.
- [ ] Fixed, variable và stepwise cost được mô hình hóa.
- [ ] Có actual-to-date và forecast phần còn lại của kỳ.

### Unit economics
- [ ] Đã định nghĩa request/task thành công.
- [ ] Cost per attempt và cost per success được phân biệt.
- [ ] Có cost per on-time success nếu cần.
- [ ] Numerator và denominator cùng time window/scope.
- [ ] Retry, failed work và shared cost được tính.
- [ ] Average và marginal cost được theo dõi.
- [ ] Unit cost được xem cùng SLO và chất lượng.

### Governance
- [ ] Budget owner và workload owner rõ ràng.
- [ ] Có budget alert và forecast-overrun alert.
- [ ] Có variance analysis theo volume/rate/mix/efficiency.
- [ ] Có quy trình xử lý anomaly và approval.
- [ ] Optimization có baseline, guardrail và rollback.
- [ ] Forecast và allocation policy được review định kỳ.

## Kết luận

Lập ngân sách compute hiệu quả cần nối demand, capacity, pricing và kết quả workload. Forecast tốt phải mô hình hóa request/job volume, peak, throughput an toàn, resource-time, shared service, discount và các khoản một lần. Unit cost cần dùng đầu ra có ý nghĩa như request thành công hoặc task được chấp nhận, đồng thời tính cả retry và chi phí dùng chung. Theo dõi average cost, marginal cost, variance, SLO và quality giúp nhận biết chi phí tăng do nhu cầu, giá, hiệu suất hay capacity reserve. Khi cost model có owner, nguồn dữ liệu rõ và được cập nhật theo vòng lặp FinOps, đội ngũ có thể dự báo sát hơn, giải thích hóa đơn và tối ưu chi phí mà vẫn giữ chất lượng dịch vụ.

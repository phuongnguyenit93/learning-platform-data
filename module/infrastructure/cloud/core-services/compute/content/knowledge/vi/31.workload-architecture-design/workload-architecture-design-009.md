# Lập bảng quyết định theo độ trễ, độ tin cậy, chi phí và năng lực vận hành

Khi thiết kế một workload compute, có thể chọn giữa VM, container, serverless, managed platform hoặc kiến trúc hybrid/edge. Mỗi lựa chọn có ưu điểm và giới hạn khác nhau: VM cho quyền kiểm soát hệ điều hành và runtime; container giúp đóng gói và triển khai nhất quán; serverless giảm công quản lý máy chủ; managed service chuyển một phần trách nhiệm vận hành cho nhà cung cấp; hybrid/edge đưa xử lý gần dữ liệu hoặc thiết bị. Không có mô hình nào tốt nhất cho mọi workload.

Để quyết định có căn cứ, cần lập bảng đánh giá theo bốn nhóm chính: **độ trễ**, **độ tin cậy**, **chi phí toàn vòng đời** và **năng lực vận hành**. Bảng điểm chỉ có ý nghĩa sau khi xác định các điều kiện bắt buộc như data residency, latency ceiling, RTO/RPO, thời lượng chạy, kiến trúc CPU, kết nối và giới hạn bảo mật. Một lựa chọn có điểm tổng cao vẫn phải bị loại nếu vi phạm một điều kiện bắt buộc.

## 1. Bắt đầu từ workload và kết quả cần đạt

Không nên chọn compute model chỉ vì đội ngũ đã quen với một công nghệ hoặc vì một loại dịch vụ đang phổ biến. Trước tiên, mô tả workload bằng ngôn ngữ nghiệp vụ và kỹ thuật:

- Workload phục vụ request trực tiếp, xử lý nền liên tục, chạy batch theo lịch hay tính toán phân tán?
- Ai hoặc hệ thống nào tạo tải; tải nền, peak, burst và tăng trưởng ra sao?
- Người dùng cần kết quả trong bao lâu; dữ liệu cần được xử lý gần nơi phát sinh không?
- Khi một instance, node, zone, region hoặc đường truyền lỗi, hệ thống phải tiếp tục hoạt động thế nào?
- Dữ liệu nào được tạo, lưu, truyền và cần bảo vệ ở đâu?
- Có thể dừng, retry, checkpoint hoặc chạy lại công việc không?
- Đội ngũ hiện có thể triển khai, giám sát, vá lỗi và xử lý sự cố ở mức nào?

Đầu ra của bước này là một workload profile có thể dùng để so sánh các phương án. Một profile tốt nêu cả mục tiêu và giới hạn, ví dụ: “API tra cứu đơn hàng cần p95 dưới 250 ms trong region chính, availability 99,9%, RTO 30 phút, RPO 5 phút, tải nền 300 request/s và peak 1.500 request/s; dữ liệu phải ở trong khu vực được phê duyệt; đội vận hành có Kubernetes nhưng không có trực 24/7 cho cluster tự quản lý.”

## 2. Phân biệt điều kiện bắt buộc và tiêu chí tối ưu

Một lỗi thường gặp là cộng tất cả tiêu chí vào một điểm tổng ngay từ đầu. Cách đó có thể khiến một lựa chọn rất rẻ bù điểm cho việc vi phạm yêu cầu pháp lý hoặc SLO. Nên tách hai lớp:

1. **Hard constraints (điều kiện bắt buộc):** nếu không đáp ứng thì loại phương án, bất kể điểm ở tiêu chí khác.
2. **Scored criteria (tiêu chí chấm điểm):** dùng để so sánh những phương án còn khả thi.

Ví dụ hard constraints:

- Dữ liệu phải ở region/site được phê duyệt.
- Độ trễ tối đa tới thiết bị không được vượt ngưỡng đã đo.
- Workload phải chạy được trên CPU architecture hoặc accelerator được chỉ định.
- Thời lượng một job phải nằm trong giới hạn runtime của nền tảng.
- RPO/RTO phải đáp ứng yêu cầu nghiệp vụ.
- Có đường kết nối riêng, isolation hoặc kiểm soát truy cập bắt buộc.
- Phải hỗ trợ offline mode tại edge hoặc hoạt động khi WAN gián đoạn.
- Phải tương thích với phần mềm/vendor được chứng nhận.

Nếu một phương án không đạt hard constraint, ghi rõ `Không phù hợp` và lý do; không đưa nó vào phép tính điểm trung bình có trọng số.

## 3. Định nghĩa bốn nhóm tiêu chí

### Độ trễ (latency)

Độ trễ là thời gian từ lúc một thao tác được bắt đầu tới khi kết quả hoặc phản hồi cần thiết sẵn sàng. Cần phân biệt:

- **Request latency:** thời gian client chờ một request-response.
- **Queueing delay:** thời gian task chờ trước khi worker bắt đầu xử lý.
- **Processing time:** thời gian CPU/GPU hoặc ứng dụng thực hiện công việc.
- **Network latency:** thời gian truyền và phản hồi qua mạng.
- **End-to-end latency:** tổng thời gian qua các bước trong luồng nghiệp vụ.
- **Tail latency:** các percentile cao như p95/p99, phản ánh trải nghiệm của nhóm request chậm.

Không chỉ dùng latency trung bình. Một API có trung bình 40 ms nhưng p99 là 2 giây có thể vi phạm SLO với một tỷ lệ request đáng kể. Với xử lý nền, queue age và thời gian từ event creation tới completion thường quan trọng hơn thời gian một lần function chạy.

### Độ tin cậy (reliability)

Độ tin cậy thể hiện khả năng workload cung cấp chức năng đúng và liên tục trong điều kiện lỗi có thể dự đoán. Các yếu tố gồm:

- Availability/SLO và error budget.
- Khả năng chịu lỗi instance, node, rack, zone hoặc region.
- RTO (thời gian mục tiêu phục hồi) và RPO (mức mất dữ liệu tối đa chấp nhận được).
- Backup, restore, replication và consistency.
- Health check, failover, retry, idempotency và graceful shutdown.
- Khả năng quan sát, phát hiện sự cố và thời gian phản ứng.
- Phụ thuộc vào control plane, WAN, DNS, identity hoặc dịch vụ bên ngoài.

Chạy nhiều replica không tự động tạo HA. Nếu tất cả replica cùng zone, cùng storage hoặc cùng dependency, một lỗi chung vẫn có thể làm toàn bộ workload ngừng hoạt động.

### Chi phí (cost)

So sánh chi phí toàn vòng đời thay vì chỉ nhìn đơn giá VM hoặc function. TCO nên tính:

- Compute, memory, GPU và capacity dự phòng.
- Storage, IOPS, snapshot, backup và retention.
- Network, egress, cross-zone, NAT, load balancer và connectivity.
- License, support plan và managed service fee.
- Logging, metrics, tracing, security tooling và data retention.
- Chi phí migration, chạy song song, test và decommission.
- Nhân lực phát triển nền tảng, on-call, patching, backup và incident response.
- Chi phí gián đoạn, mất dữ liệu hoặc không đạt deadline nếu có thể ước lượng.

Nên tính unit economics như chi phí trên mỗi request thành công, task hoàn tất, record xử lý hoặc giờ compute hữu ích. Tổng hóa đơn tăng có thể vẫn là cải thiện nếu số đơn vị công việc hoàn thành tăng nhanh hơn và SLO được giữ vững.

### Năng lực vận hành (operational capability)

Đánh giá xem tổ chức có thể vận hành lựa chọn đó an toàn và ổn định hay không:

- Kỹ năng về OS, network, storage, container, Kubernetes, serverless hoặc database.
- Khả năng trực/on-call, xử lý incident và phối hợp vendor.
- Công cụ CI/CD, IaC, secrets, observability và policy enforcement.
- Quy trình patching, vulnerability management, backup/restore và DR test.
- Khả năng quản lý capacity, quota, autoscaling và cost governance.
- Mức độ trưởng thành của runbook, ownership, change management và service catalog.
- Số thành phần phải tự quản lý và mức phụ thuộc vào nhà cung cấp.

Một kiến trúc có hiệu năng tốt nhưng vượt quá năng lực vận hành hiện có có thể làm tăng downtime và chi phí nhân lực. Cần tính cả năng lực phải xây dựng trong lộ trình, không giả định đội ngũ sẽ tự nhiên có đủ kỹ năng ngay khi go-live.

## 4. Thu thập dữ liệu trước khi chấm điểm

Bảng quyết định đáng tin cậy cần dữ liệu thay vì nhận định cảm tính. Thu thập ít nhất:

| Nhóm | Dữ liệu cần có | Nguồn thường dùng |
|---|---|---|
| Latency | p50/p95/p99, queue age, network RTT, processing duration, cold start | APM, tracing, load test, synthetic test |
| Reliability | uptime, error rate, incident history, RTO/RPO, restore time, failover test | Monitoring, incident records, DR exercise |
| Cost | usage profile, invoice/export, storage growth, egress, license, staffing estimate | Billing export, cost calculator, inventory, timesheet/operations estimate |
| Operations | deployment frequency, recovery time, on-call coverage, patch cadence, skill matrix | CI/CD, incident review, team assessment, runbook audit |
| Workload | request rate, concurrency, job duration, payload size, data locality, dependency graph | Metrics, profiling, application inventory |

Nếu workload hiện tại chưa có metric, hãy chạy baseline hoặc pilot. Ghi rõ thời gian đo, kích thước mẫu, tải thử, region, loại instance, cache state và các giả định. Một benchmark ngắn ở môi trường rảnh không đại diện cho peak production.

## 5. Xác định ngưỡng độ trễ theo loại workload

Không có một ngưỡng latency phù hợp cho mọi hệ thống. Xác định ngưỡng từ hành vi người dùng và dependency:

| Workload | Metric chính | Câu hỏi quyết định |
|---|---|---|
| API tương tác | p95/p99 request latency | Người dùng có chờ được không? Gateway và client timeout là bao nhiêu? |
| Giao dịch nội bộ | end-to-end transaction latency | Có cần phản hồi đồng bộ hoặc có thể trả job ID? |
| Background worker | oldest message age, queue wait, task duration | Event phải hoàn tất trong bao lâu sau khi được tạo? |
| Batch | job duration, throughput, completion deadline | Job phải hoàn thành trước thời điểm nào? |
| HPC/distributed AI | communication latency, all-reduce time, step time | Mạng có nằm trên critical path không? |
| Edge control | local response time và WAN dependency | Có phải phản hồi ngay cả khi mất kết nối cloud? |

Với latency nhạy cảm, kiểm tra placement, network hop, zone/region distance, cold start, connection establishment, storage I/O và dependency chain. Nếu dữ liệu nằm tại edge, đưa compute tới gần dữ liệu có thể giảm latency và egress, nhưng tăng số site cần quản lý.

## 6. Đánh giá độ tin cậy bằng failure scenario

Không nên chấm reliability chỉ bằng số replica hoặc tuyên bố SLA của dịch vụ. Hãy liệt kê các tình huống lỗi và kiểm tra cách workload phục hồi:

- Một process/container bị crash.
- Một VM hoặc node mất kết nối.
- Một rack hoặc availability zone không khả dụng.
- Database, queue hoặc identity provider bị gián đoạn.
- WAN từ edge tới cloud bị mất.
- Một region bị lỗi hoặc control plane không truy cập được.
- Release mới có lỗi và cần rollback.
- Backup tồn tại nhưng restore chậm hoặc không thành công.

Với từng scenario, ghi nhận detection time, recovery action, RTO thực tế, dữ liệu có thể mất, mức suy giảm chức năng và người chịu trách nhiệm. Chỉ đánh giá phương án đạt reliability khi có bằng chứng từ test hoặc runbook đã diễn tập.

### RTO và RPO phải gắn với dữ liệu

RTO là thời gian tối đa để khôi phục dịch vụ theo mục tiêu. RPO là lượng dữ liệu tối đa có thể mất tính theo thời gian hoặc điểm dữ liệu. Một workload stateless có thể khôi phục bằng cách tạo replica mới; database stateful cần backup/replication và kiểm tra consistency. Không dùng cùng một giả định RTO/RPO cho compute và data store nếu cách phục hồi khác nhau.

## 7. Xây dựng mô hình TCO có thể so sánh

Để so sánh VM, container, serverless và managed service, dùng cùng workload profile, cùng region/điều kiện mạng, cùng SLO và cùng thời hạn phân tích.

Một mô hình tổng quát:

\[
TCO = C_{compute} + C_{storage} + C_{network} + C_{platform} + C_{license} + C_{observability} + C_{operations} + C_{migration}
\]

Trong đó `C_operations` gồm chi phí nhân lực vận hành và hỗ trợ. Nếu không có dữ liệu tiền tệ đáng tin cậy cho nhân lực, ghi thành ước lượng hoặc điểm effort riêng; không cộng một con số tùy ý vào invoice.

Ví dụ công thức compute cho VM chạy liên tục:

\[
C_{VM} = N \times H_{month} \times P_{hour}
\]

Với worker scale theo tải:

\[
C_{worker} \approx \sum_i (N_i \times H_i \times P_i) + C_{queue} + C_{network} + C_{storage}
\]

Với function:

\[
C_{function} \approx N_{invocations} \times Duration \times AllocatedResources + C_{requests} + C_{dependencies}
\]

Các công thức chỉ là mô hình khái niệm; đơn vị tính, mức tối thiểu, free tier, provisioned concurrency, request meter, egress và chiết khấu khác nhau theo provider. Dùng billing calculator/export thực tế để xác minh.

## 8. Đánh giá năng lực vận hành theo trách nhiệm thực tế

Đối với mỗi phương án, liệt kê thành phần mà đội ngũ phải trực tiếp quản lý và thành phần được managed:

| Trách nhiệm | VM tự quản lý | Container trên Kubernetes | Serverless/managed platform |
|---|---|---|---|
| OS patching | Thường do đội workload/platform quản lý | Worker node/OS do platform quản lý tùy mô hình; image vẫn cần cập nhật | Phần lớn runtime/host do provider quản lý; dependency ứng dụng vẫn do team cập nhật |
| Runtime/app dependency | Team ứng dụng | Team ứng dụng và image pipeline | Team ứng dụng và package/dependency |
| Scheduling/placement | VM/orchestrator hoặc operator | Kubernetes scheduler và platform | Provider runtime/event service |
| Autoscaling | Cần cấu hình VM group/agent hoặc orchestrator | HPA/VPA/node autoscaler và quota | Provider scale theo request/event trong giới hạn dịch vụ |
| Network/security | OS, firewall, subnet, IAM, endpoint | Cluster/network policy, ingress, service account, node | IAM, trigger permissions, VPC access và service policy |
| Observability | Agent/stack tự cấu hình | Cluster + workload telemetry | Tích hợp log/metric/trace theo dịch vụ; vẫn cần dashboard/alert |
| Backup/DR | Tự thiết kế cho OS/app/data | Quản lý state, PV, cluster và data | Provider có thể cung cấp tính năng; retention/restore vẫn cần thiết kế |
| On-call | Phụ thuộc team và automation | Cần năng lực cluster/platform | Cần hiểu event, quota, timeout, retry và provider limits |

Managed không có nghĩa “không cần vận hành”. Trách nhiệm chuyển từ quản lý host sang cấu hình dịch vụ, IAM, quota, retry, data lifecycle, cost và observability. Cần đọc shared responsibility model của dịch vụ cụ thể.

## 9. Thiết lập thang điểm nhất quán

Một thang điểm 1–5 có thể dùng như sau:

| Điểm | Ý nghĩa chung | Latency | Reliability | Cost | Operations |
|---:|---|---|---|---|---|
| 1 | Rất kém/không đáp ứng mục tiêu mềm | Vượt xa ngưỡng mục tiêu | Khó phục hồi, thiếu bằng chứng | TCO rất cao so với giá trị | Vượt năng lực đội ngũ hiện tại |
| 2 | Kém | Thường xuyên sát/vượt ngưỡng | Có nhiều điểm lỗi đơn, runbook yếu | Cao | Cần nhiều kỹ năng/quy trình mới |
| 3 | Đạt mức chấp nhận | Đáp ứng phần lớn tải đo | Có HA/backup cơ bản và test một phần | Trong ngân sách dự kiến | Đội ngũ có thể vận hành với hỗ trợ |
| 4 | Tốt | Đáp ứng SLO với headroom | Có failure test, recovery rõ | TCO cạnh tranh | Tự động hóa và ownership rõ |
| 5 | Rất tốt | Có headroom tốt ở peak/tail | Đã diễn tập nhiều scenario, recovery tin cậy | TCO thấp theo unit economics | Có năng lực, automation và on-call trưởng thành |

Thang điểm cần được cụ thể hóa theo workload. Ví dụ, latency score 5 có thể là p99 thấp hơn một nửa ngưỡng; reliability score 5 có thể yêu cầu DR test đạt RTO/RPO; operations score 5 yêu cầu deployment, patching và incident response đã tự động hóa. Không nên để mỗi người tự hiểu điểm 4 theo một cách.

## 10. Chọn trọng số theo mục tiêu workload

Trọng số thể hiện tầm quan trọng tương đối của từng nhóm. Tổng trọng số phải bằng 100% hoặc 1,0.

Ví dụ trọng số tham khảo:

| Loại workload | Latency | Reliability | Cost | Operations | Lý do |
|---|---:|---:|---:|---:|---|
| API tương tác | 35% | 30% | 15% | 20% | Trải nghiệm và availability quan trọng |
| Giao dịch quan trọng | 20% | 40% | 10% | 30% | Tính đúng đắn và phục hồi ưu tiên |
| Batch/analytics | 15% | 25% | 35% | 25% | Chi phí mỗi record và deadline quan trọng |
| HPC/distributed AI | 40% | 20% | 25% | 15% | Network/compute performance chi phối |
| Edge/industrial | 30% | 35% | 15% | 20% | Local response và hoạt động khi WAN lỗi |

Đây chỉ là điểm khởi đầu. Với workload có quy định hoặc criticality cao, reliability có thể là hard constraint thay vì chỉ tăng trọng số. Không dùng cùng trọng số cho toàn module hoặc mọi ứng dụng.

## 11. Tính điểm có trọng số

Sau khi loại phương án vi phạm hard constraint, tính điểm:

\[
Score = W_L \times S_L + W_R \times S_R + W_C \times S_C + W_O \times S_O
\]

Trong đó:

- `W_L`, `W_R`, `W_C`, `W_O` là trọng số latency, reliability, cost và operations; tổng bằng 1.
- `S_L`, `S_R`, `S_C`, `S_O` là điểm 1–5 cho từng tiêu chí.

Điểm cao hơn cho biết phương án phù hợp hơn theo trọng số và thang điểm đã chọn. Nó không phải xác suất thành công hoặc bảo đảm hiệu năng. Cần lưu cả điểm thành phần, bằng chứng, giả định và mức độ tin cậy của dữ liệu.

Nếu hai phương án chênh điểm rất nhỏ, không nên tuyên bố một phương án thắng tuyệt đối. Hãy kiểm tra sensitivity: thay đổi trọng số, giá cloud, tải peak hoặc giả định vận hành để xem thứ hạng có đảo không.

## 12. Bảng quyết định mẫu giữa các mô hình compute

Bảng dưới đây là đánh giá định tính ban đầu cho workload web/API phổ biến, chưa phải kết luận cho mọi hệ thống. Điểm cụ thể phải được thay bằng số đo và điều kiện thực tế.

| Phương án | Latency | Reliability | Cost | Operations | Điểm mạnh | Hạn chế chính |
|---|---:|---:|---:|---:|---|---|
| VM tự quản lý | 3 | 3 | 3 | 2 | Kiểm soát OS/runtime, tương thích legacy | Patching, HA, scaling và capacity cần vận hành |
| Container trên Kubernetes | 4 | 4 | 3 | 2 | Deployment, scheduling, scaling và portability | Cần năng lực cluster, network, storage và platform |
| Serverless function | 3 | 4 | 4 | 4 | Ít quản lý host, scale theo event/request | Cold start, timeout, quota, runtime constraint và vendor limits |
| Managed application/container platform | 4 | 4 | 3 | 4 | Giảm công quản lý cluster/host, tích hợp autoscaling | Chi phí dịch vụ và giới hạn platform cần xác minh |
| Hybrid/edge compute | 5 tại local path | 3 | 2 | 2 | Xử lý gần thiết bị/dữ liệu, tiếp tục hoạt động offline | Fleet, site connectivity, update và identity phức tạp |

Điểm trong bảng chỉ mang tính minh họa để giải thích phương pháp. Chúng không phải benchmark, SLA hoặc báo giá của bất kỳ provider nào. Đặc biệt, hybrid/edge không mặc định có latency 5 hay reliability 3; kết quả phụ thuộc topology, phần cứng, WAN, nguồn điện, vận hành site và khả năng đồng bộ.

## 13. Ví dụ chấm điểm cho một API thương mại

Giả sử API cần p95 dưới 200 ms trong region chính, availability 99,9%, RTO 30 phút và đội ngũ có kỹ năng container cơ bản nhưng chưa trực Kubernetes 24/7. Sau pilot, ba phương án được chấm điểm:

| Tiêu chí | Trọng số | VM | Kubernetes | Managed container platform |
|---|---:|---:|---:|---:|
| Latency | 0,35 | 4 | 4 | 4 |
| Reliability | 0,30 | 3 | 4 | 4 |
| Cost | 0,15 | 3 | 3 | 3 |
| Operations | 0,20 | 3 | 2 | 4 |

Tính điểm:

\[
Score_{VM} = 0.35(4)+0.30(3)+0.15(3)+0.20(3)=3.35
\]

\[
Score_{K8s} = 0.35(4)+0.30(4)+0.15(3)+0.20(2)=3.45
\]

\[
Score_{Managed} = 0.35(4)+0.30(4)+0.15(3)+0.20(4)=3.85
\]

Trong giả định này, managed container platform có điểm cao hơn vì giữ latency/reliability tương đương nhưng phù hợp năng lực vận hành hiện tại. Nếu đội ngũ đã có platform team trực 24/7 và cluster shared có capacity, điểm operations của Kubernetes có thể tăng và thứ hạng thay đổi.

Trước khi quyết định, phải xác minh cả ba phương án đạt hard constraints: latency p95, availability, RTO, data location, network path, security và quota. Nếu managed platform không đáp ứng một yêu cầu network hoặc data residency, nó bị loại dù điểm 3,85 cao nhất.

## 14. Ví dụ quyết định cho batch xử lý dữ liệu

Một job ETL chạy 2–3 giờ mỗi đêm, xử lý file lớn, có thể chia partition và cần hoàn thành trước 05:00. Người dùng không chờ response đồng bộ.

Các lựa chọn:

- VM theo lịch: kiểm soát môi trường, nhưng phải quản lý boot, patch, scheduler và capacity.
- Container Job: đóng gói dependency, chạy task hữu hạn, dễ scale theo partition nếu nền tảng hỗ trợ.
- Serverless function: phù hợp các bước ngắn hoặc từng partition nhỏ; có thể không phù hợp nếu một invocation vượt timeout hoặc payload lớn.
- Managed batch service: có thể hỗ trợ queue, job scheduling, retry và placement; cần kiểm tra phí và giới hạn.

Trọng số có thể là latency/deadline 15%, reliability 25%, cost 35%, operations 25%. Metric quan trọng gồm cost per million records, thời gian hoàn thành, retry rate, checkpoint recovery và storage/network throughput. Một phương án chậm hơn một chút nhưng rẻ và hoàn thành ổn định trước deadline có thể tốt hơn phương án có throughput cao nhất.

## 15. Ví dụ quyết định cho workload edge

Một gateway tại nhà máy phải xử lý tín hiệu điều khiển cục bộ trong 20 ms và tiếp tục vận hành khi WAN mất trong 4 giờ. Dữ liệu sau đó được đồng bộ về cloud.

Cloud-only serverless không đáp ứng hard constraint nếu đường điều khiển cần đi qua WAN. Một edge runtime/container hoặc native service tại site có thể xử lý local, còn cloud đảm nhiệm quản lý fleet, phân tích dài hạn và báo cáo.

Các tiêu chí cần đánh giá:

- Local latency p99 trong điều kiện CPU/storage tải cao.
- Khả năng hoạt động offline, buffer quota và hành vi khi buffer đầy.
- RTO khi gateway reboot và khả năng khôi phục state.
- Certificate/device identity và quy trình revoke/rotate.
- Chi phí thiết bị, thay thế phần cứng, hỗ trợ site và cập nhật offline.
- Năng lực đội ngũ/site operator xử lý lỗi mà không cần cloud control plane.

Trong trường hợp này, kiến trúc phù hợp có thể là hybrid: edge compute cho đường điều khiển nhạy latency; cloud service cho orchestration, analytics và lưu trữ tập trung. Đây là quyết định theo hard constraints và data locality, không phải do edge luôn rẻ hoặc đáng tin cậy hơn cloud.

## 16. Xem xét kiến trúc kết hợp thay vì chỉ chọn một nền tảng

Một workload có thể chia thành nhiều component với yêu cầu khác nhau:

| Component | Đặc tính | Mô hình có thể phù hợp |
|---|---|---|
| API tiếp nhận | Latency thấp, request-response | Managed container, VM hoặc serverless HTTP |
| Worker | Task bất đồng bộ, retry và scale theo queue | Container worker hoặc event-driven function |
| Batch analytics | Job hữu hạn, throughput và checkpoint | Container Job, VM theo lịch hoặc managed batch |
| Database | State, consistency, backup/restore | Managed database hoặc database tự quản lý khi có yêu cầu đặc thù |
| Edge collector | Local I/O, offline buffer, device protocol | Container/native service tại edge |
| Control plane | Quản lý fleet, policy và rollout | Cloud managed service hoặc platform service |

Không nên buộc mọi component dùng cùng một compute model chỉ để đồng nhất công nghệ. Có thể dùng chung CI/CD, image, identity convention, logging schema và service catalog trong khi runtime khác nhau theo đặc tính workload.

## 17. Đưa năng lực vận hành vào bảng quyết định

Để tránh chấm điểm operations theo cảm giác, đánh giá từng năng lực theo cấp độ:

| Năng lực | Cấp 1: thủ công | Cấp 2: có quy trình | Cấp 3: tự động hóa cơ bản | Cấp 4: vận hành trưởng thành |
|---|---|---|---|---|
| Deployment | Cài tay | Runbook có kiểm soát | CI/CD và rollback | Progressive delivery, policy và audit |
| Infrastructure | Cấu hình thủ công | Template chuẩn | IaC, review và drift detection | Reusable platform, policy as code |
| Observability | Log rời rạc | Dashboard cơ bản | Metrics/log/trace và alert | SLO, error budget, anomaly và runbook liên kết |
| Incident response | Phụ thuộc cá nhân | Có on-call/runbook | Diễn tập và postmortem | SLO-based response, automation và cải tiến liên tục |
| Security/patching | Cập nhật không định kỳ | Lịch patch và scan | Image/base patch pipeline | Risk-based remediation, attestation và compliance evidence |
| Backup/DR | Backup không kiểm tra | Có policy và restore runbook | Restore test định kỳ | DR exercise, measured RTO/RPO và automation |
| Cost governance | Xem hóa đơn cuối kỳ | Có budget/owner | Tag, allocation và alert | Unit economics, forecast và continuous optimization |

Nếu workload yêu cầu cấp 4 nhưng đội ngũ đang ở cấp 1, phải có kế hoạch nâng năng lực, ngân sách và thời gian trước go-live. Có thể chọn managed service trong giai đoạn đầu để giảm phạm vi vận hành, sau đó tự quản lý khi năng lực đã đủ và lợi ích kinh tế được chứng minh.

## 18. Đánh giá rủi ro phụ thuộc nhà cung cấp và khả năng di chuyển

Chi phí và năng lực vận hành còn chịu ảnh hưởng của mức phụ thuộc vào API, runtime, database, event service hoặc proprietary networking của provider.

Đánh giá:

- Artifact có thể chạy trên runtime khác không?
- Dữ liệu có thể export với định dạng và thời gian hợp lý không?
- API, IAM, event schema và observability có phụ thuộc độc quyền không?
- Có thể thay managed database hoặc queue mà không viết lại toàn bộ ứng dụng không?
- Phí egress, data transfer và migration có tạo rào cản không?
- Đội ngũ có kỹ năng vận hành phương án thay thế không?
- Có thể duy trì hoạt động trong thời gian migration hoặc provider outage không?

Không phải lúc nào cũng cần portability tối đa. Tối ưu sâu vào managed service có thể giảm công vận hành và tăng tốc phát triển. Quyết định cần cân bằng lợi ích hiện tại với chi phí exit, yêu cầu resilience và khả năng thương lượng.

## 19. Kiểm tra độ nhạy của kết quả (sensitivity analysis)

Điểm tổng có thể thay đổi khi giả định thay đổi. Thử ít nhất các kịch bản:

- Tải tăng gấp đôi hoặc peak kéo dài lâu hơn dự kiến.
- Giá compute/network tăng hoặc commitment discount thay đổi.
- Availability target tăng từ 99,9% lên 99,95%/99,99%.
- Mất một zone và workload phải chạy trên capacity còn lại.
- Đội ngũ chưa tuyển được kỹ năng vận hành đã giả định.
- Provider giới hạn quota hoặc loại instance cần dùng không còn capacity.
- WAN edge gián đoạn lâu hơn hoặc số site tăng nhanh.

Nếu chỉ cần thay đổi một giả định nhỏ đã đảo thứ hạng, quyết định có độ nhạy cao. Khi đó nên chạy pilot, thương lượng điều khoản, cải thiện dữ liệu hoặc chọn kiến trúc có khả năng chuyển đổi dễ hơn.

## 20. Template bảng quyết định cho một workload

Có thể dùng mẫu sau trong design review. Điền số đo và nguồn bằng chứng thay cho các giá trị ví dụ.

| Mục | Nội dung cần ghi |
|---|---|
| Workload/service ID | Tên service trong catalog |
| Business owner / technical owner | Đơn vị nghiệp vụ và team kỹ thuật |
| Workload type | Online, worker, batch, HPC, edge hoặc hybrid |
| Region/site/data location | Vị trí xử lý và lưu dữ liệu được phép |
| Latency target | p95/p99 hoặc queue age/end-to-end deadline |
| Reliability target | Availability, RTO, RPO và failure scenarios |
| Cost envelope | Budget, TCO horizon và unit economics |
| Operations capability | Kỹ năng, on-call, automation, runbook và support |
| Hard constraints | Điều kiện bắt buộc và bằng chứng đáp ứng |
| Candidate architectures | VM, container, serverless, managed, hybrid/edge |
| Weighted score | Điểm theo trọng số đã thống nhất |
| Risks/assumptions | Rủi ro, giả định và mức độ tin cậy dữ liệu |
| Decision | Phương án được chọn và lý do |
| Review trigger | Điều kiện cần đánh giá lại, ví dụ tải/giá/site tăng |

Mẫu scorecard:

| Tiêu chí | Weight | Phương án A | Evidence A | Phương án B | Evidence B |
|---|---:|---:|---|---:|---|
| Latency |  |  |  |  |  |
| Reliability |  |  |  |  |  |
| Cost |  |  |  |  |  |
| Operations |  |  |  |  |  |
| Total | 100% |  |  |  |  |

Ghi rõ điểm theo thang 1–5, không để ô evidence trống. Nếu dữ liệu chưa có, đánh dấu `Chưa đo` và lên kế hoạch pilot; không tự gán điểm cao để hoàn tất bảng.

## 21. Quy trình ra quyết định và phê duyệt

Một design decision có thể đi qua các bước:

1. **Xác định owner và mục tiêu:** service owner, business owner, SLO, budget và phạm vi dữ liệu.
2. **Thu thập workload profile:** tải, latency, dependency, state, runtime và vị trí dữ liệu.
3. **Xác định hard constraints:** loại phương án không đáp ứng yêu cầu bắt buộc.
4. **Lập shortlist:** chọn các phương án thực sự khả thi, thường 2–4 lựa chọn.
5. **Thu thập bằng chứng:** benchmark, cost estimate, failure test và operations assessment.
6. **Chọn trọng số và chấm điểm:** có đại diện ứng dụng, platform, security, operations và finance.
7. **Sensitivity analysis:** thay đổi giả định quan trọng để kiểm tra tính ổn định của quyết định.
8. **Ghi ADR/design record:** lưu lựa chọn, lý do, trade-off, rủi ro và phương án bị loại.
9. **Pilot và xác minh:** triển khai quy mô nhỏ với tải và failure scenario đại diện.
10. **Phê duyệt và triển khai:** có tiêu chí go/no-go, rollout và rollback.
11. **Review sau vận hành:** so sánh actual với giả định và đánh giá lại khi workload thay đổi.

Quyết định kiến trúc cần có thời điểm xem xét lại. Ví dụ, khi traffic tăng 5 lần, workload chuyển region, RTO thay đổi hoặc team có platform capability mới, bảng quyết định cũ có thể không còn đúng.

## 22. Lưu quyết định bằng Architecture Decision Record

ADR giúp lưu lý do lựa chọn để đội ngũ sau này hiểu bối cảnh và không phải tái tranh luận từ đầu.

Mẫu ngắn:

```markdown
# ADR-014: Chọn managed container platform cho orders API

## Context
- p95 latency target: 200 ms
- Availability target: 99.9%
- RTO: 30 minutes
- Team có container skills, chưa có 24/7 Kubernetes on-call

## Decision
Chọn managed container platform tại region được phê duyệt.

## Rationale
- Đạt latency và reliability trong pilot.
- Operations score cao hơn Kubernetes tự quản lý.
- TCO nằm trong budget dự kiến.

## Trade-offs
- Phụ thuộc platform API và quota.
- Cần kiểm tra egress và exit plan.

## Validation
- Load test, zone failure exercise, restore test và cost review.

## Revisit when
- Traffic tăng gấp 3, platform fee thay đổi đáng kể hoặc yêu cầu data location đổi.
```

Đây là ví dụ minh họa, không phải quyết định đã áp dụng cho một hệ thống thực. ADR phải liên kết với kết quả test, cost estimate và người phê duyệt thực tế.

## 23. Những sai lầm thường gặp khi lập bảng quyết định

- **Chấm điểm trước khi xác định hard constraint:** phương án không hợp lệ vẫn có thể thắng do giá rẻ. Loại phương án vi phạm điều kiện bắt buộc trước.
- **Dùng latency trung bình:** che giấu tail latency. Theo dõi p95/p99 và end-to-end time.
- **Đồng nhất nhiều replica với HA:** bỏ qua failure domain và dependency chung. Diễn tập node/zone/dependency failure.
- **Chỉ so giá compute:** bỏ sót network, storage, license, observability và nhân lực. Dùng TCO cùng unit economics.
- **Đánh giá operations bằng số lượng dịch vụ managed:** managed vẫn cần IAM, quota, data lifecycle, alert và incident response. Dùng responsibility matrix.
- **Dùng trọng số giống nhau cho mọi workload:** API, batch, HPC và edge có ưu tiên khác nhau. Chọn trọng số theo SLO và business impact.
- **Chấm điểm không có bằng chứng:** kết quả phụ thuộc cảm nhận cá nhân. Gắn metric, benchmark, invoice hoặc test report cho mỗi điểm.
- **Bỏ qua năng lực đội ngũ tương lai:** giả định kỹ năng sẽ có ngay. Ghi kế hoạch tuyển dụng/đào tạo/managed support.
- **Bỏ qua sensitivity:** thứ hạng đảo khi giá hoặc tải thay đổi. Chạy nhiều kịch bản.
- **Coi portability là miễn phí:** abstraction quá mức có thể tăng chi phí và làm giảm lợi ích managed service. Cân nhắc exit cost theo rủi ro thực tế.
- **Không review sau go-live:** workload thay đổi nhưng kiến trúc không được đánh giá lại. Đặt review trigger và lịch định kỳ.

## 24. Checklist trước khi chốt kiến trúc

**Workload và hard constraints**

- [ ] Có workload profile với request rate, peak, concurrency, data size và dependency.
- [ ] Đã phân biệt request latency, queue age, processing time và end-to-end latency.
- [ ] Có latency target p95/p99 hoặc deadline xử lý rõ ràng.
- [ ] Có availability/SLO, RTO, RPO và failure scenarios.
- [ ] Data residency, security, CPU architecture, network và runtime limits được xác định.
- [ ] Các phương án vi phạm hard constraint đã bị loại và có lý do.

**Bảng điểm và chi phí**

- [ ] Có trọng số phù hợp workload và tổng trọng số bằng 100%.
- [ ] Thang điểm 1–5 được định nghĩa bằng ngưỡng đo cụ thể.
- [ ] Mỗi điểm có evidence hoặc được đánh dấu chưa đo.
- [ ] TCO gồm compute, storage, network, license, managed service, observability, operations và migration.
- [ ] Có unit economics theo request/task/record thành công.
- [ ] Có low/expected/high scenario và sensitivity analysis.

**Năng lực vận hành và quyết định**

- [ ] Có owner, on-call, skill matrix, runbook và support model.
- [ ] Trách nhiệm patching, security, backup/restore, scaling và incident được phân định.
- [ ] Có pilot/load test/failure test với workload đại diện.
- [ ] Có ADR ghi decision, rationale, trade-off, risk và phương án bị loại.
- [ ] Có go/no-go criteria, rollout, rollback và review trigger.
- [ ] Có lịch đối chiếu actual latency, reliability, cost và operations sau go-live.

Lập bảng quyết định theo độ trễ, độ tin cậy, chi phí và năng lực vận hành giúp biến lựa chọn kiến trúc thành một quyết định có thể giải thích và kiểm chứng. Trước hết phải loại phương án không đáp ứng điều kiện bắt buộc; sau đó mới chấm điểm theo trọng số phù hợp workload, dựa trên metric, benchmark, failure test và TCO. Khi ghi lại giả định, bằng chứng, trade-off và thời điểm đánh giá lại, tổ chức có thể chọn mô hình compute phù hợp hiện tại mà vẫn chủ động điều chỉnh khi tải, yêu cầu nghiệp vụ hoặc năng lực vận hành thay đổi.

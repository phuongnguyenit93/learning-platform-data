# So sánh tổng chi phí sở hữu giữa VM, container và serverless

Khi chọn mô hình chạy ứng dụng trên cloud, giá compute theo giờ hoặc theo request chỉ là một phần của chi phí. Một VM có đơn giá thấp nhưng luôn chạy khi tải gần bằng không vẫn có thể tốn kém. Container có thể đóng gói nhiều dịch vụ trên cùng node, nhưng cần trả cho node, control plane, registry, storage và năng lực vận hành nền tảng. Serverless giảm công việc quản lý máy và có thể scale về zero, nhưng chi phí tăng theo số request, thời gian thực thi, bộ nhớ, concurrency và các dịch vụ đi kèm.

**Tổng chi phí sở hữu (Total Cost of Ownership - TCO)** là tổng chi phí cần thiết để đưa một workload vào vận hành, duy trì, bảo mật, mở rộng và thay đổi trong một khoảng thời gian xác định. So sánh TCO giữa VM, container và serverless phải dùng cùng workload, cùng SLO, cùng yêu cầu bảo mật và cùng phạm vi chi phí.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, việc so sánh cần xét cả compute, storage, network, license, observability, backup, control plane, nhân lực, migration, khả năng chịu lỗi và chi phí khi workload tăng hoặc giảm. Mô hình rẻ nhất theo hóa đơn compute chưa chắc có chi phí thấp nhất trên mỗi request hoặc giao dịch thành công.

## 1. TCO khác gì với giá compute?

Giá compute thường là khoản phí cho vCPU/RAM theo giờ, container capacity theo node hoặc thời gian thực thi function. TCO bao gồm thêm các khoản cần thiết để workload hoạt động an toàn và đáp ứng yêu cầu nghiệp vụ.

Một mô hình tổng quát:

~~~text
TCO trong kỳ =
    Compute
  + Storage
  + Network và data transfer
  + Control plane và dịch vụ nền tảng
  + License và phần mềm
  + Logging, monitoring và tracing
  + Backup, DR và capacity dự phòng
  + Security và compliance
  + Nhân lực vận hành
  + Migration và enablement đã phân bổ
  + Chi phí gián đoạn hoặc rủi ro được ước lượng
  - Discount, credit và lợi ích có thể ghi nhận
~~~

Không phải tổ chức nào cũng đưa chi phí gián đoạn vào cùng một báo cáo tài chính. Tuy nhiên, khi quyết định kiến trúc, cần xem xét tác động của downtime, mất dữ liệu, giới hạn capacity và vendor lock-in.

### 1.1. Xác định phạm vi so sánh

Trước khi tính, cần thống nhất:

- Khoảng thời gian: theo tháng, năm hay vòng đời 3 năm.
- Workload: request/giây, số job, kích thước dữ liệu, tỷ lệ đọc/ghi và thời gian chạy.
- SLO: availability, p95/p99 latency, throughput và error rate.
- Môi trường: production, staging, development hay tất cả.
- Failure domain: một zone hay nhiều zone, có DR region hay không.
- Security: encryption, identity, network isolation, audit và retention.
- Phạm vi nhân lực: chỉ vận hành hạ tầng hay gồm platform engineering và hỗ trợ ứng dụng.
- Cách phân bổ chi phí dùng chung giữa nhiều workload.

Nếu VM được so sánh ở một zone với container/serverless chạy nhiều zone, kết quả sẽ không công bằng. Tương tự, một phương án có backup và logging đầy đủ không nên được so với phương án bỏ qua các yêu cầu này.

### 1.2. Tính theo đơn vị công việc hữu ích

Tổng bill thấp chưa chắc có hiệu quả tốt nếu hệ thống xử lý ít request hơn hoặc có nhiều lỗi. Nên bổ sung các chỉ số:

- Cost per successful request.
- Cost per completed job.
- Cost per transaction.
- Cost per GB processed.
- Cost per active user hoặc workload unit.

Ví dụ:

~~~text
Cost per successful request =
    TCO trong kỳ / Số request hoàn tất thành công trong kỳ
~~~

Khi tính mẫu số, loại request lỗi hoặc retry không tạo ra kết quả nghiệp vụ. Điều này giúp nhìn thấy chi phí của retry storm, timeout và hệ thống thiếu capacity.

## 2. Các khoản chi phí chung cho cả ba mô hình

Một số chi phí tồn tại dù ứng dụng chạy trên VM, container hay serverless.

| Nhóm chi phí | Thành phần cần tính |
| --- | --- |
| Dữ liệu | Database, object storage, file storage, backup và snapshot |
| Network | Load balancer/API gateway, NAT, private endpoint, egress, cross-zone và cross-region transfer |
| Bảo mật | KMS/key management, secret manager, vulnerability scanning, WAF và audit |
| Quan sát | Log ingestion/retention, metrics, tracing, alerting và APM |
| Vận hành | On-call, incident response, patching, capacity planning và cost management |
| Khả năng sẵn sàng | Multi-zone, replica, standby capacity, DR và diễn tập khôi phục |
| Phần mềm | OS, database, runtime, middleware, commercial license và support |

Chi phí dùng chung nên được phân bổ theo một tiêu thức hợp lý, chẳng hạn request count, dung lượng lưu trữ, network bytes, CPU time hoặc mức tiêu thụ thực tế. Không chia đều cho mọi ứng dụng nếu mức sử dụng khác nhau đáng kể.

## 3. TCO của mô hình Virtual Machine

VM cung cấp một máy ảo với vCPU, RAM, disk và network được cấp phát trong một khoảng thời gian. Tổ chức có quyền kiểm soát OS, runtime và phần lớn cấu hình guest.

### 3.1. Thành phần chi phí VM

- **Compute instance:** giá theo loại máy, kích thước, hệ điều hành, region và thời gian chạy.
- **Boot disk/data disk:** dung lượng, loại volume, IOPS/throughput và snapshot.
- **Network:** public IP, load balancer, NAT, egress và transfer giữa zone/region.
- **License:** Windows, commercial database hoặc phần mềm cài trên máy nếu có.
- **Availability:** số VM dự phòng, multi-zone, standby và capacity reservation.
- **Operations:** patch OS, hardening, backup agent, monitoring agent, image build và xử lý sự cố.
- **Capacity waste:** vCPU/RAM đã cấp nhưng không được sử dụng, thời gian idle và headroom.

### 3.2. Khi VM có lợi thế chi phí

VM thường phù hợp khi:

- Workload chạy liên tục và có mức sử dụng tương đối ổn định.
- Ứng dụng cần kiểm soát OS, kernel, driver hoặc phần mềm đặc thù.
- Workload dài hạn có thể dùng commitment/Reserved Instance/Savings Plan phù hợp.
- Nhiều tiến trình có thể chia sẻ tài nguyên trong cùng máy mà không cần orchestration phức tạp.
- Đội ngũ đã có kỹ năng và công cụ quản lý VM.
- Workload cần quyền truy cập hệ thống hoặc cấu hình máy chuyên biệt.

Nếu một VM được sử dụng ổn định gần công suất dự kiến, chi phí capacity cố định có thể hiệu quả. Tuy nhiên, cần tính cả dự phòng cho failover, bảo trì và peak.

### 3.3. Các nguồn lãng phí thường gặp

- Cấp VM lớn hơn nhu cầu thực tế.
- Duy trì máy dev/test qua đêm hoặc cuối tuần.
- Chạy nhiều VM nhỏ trong khi workload có thể hợp nhất.
- Không xóa disk, snapshot hoặc public IP không còn dùng.
- Giữ capacity cao cho peak ngắn nhưng không scale-in sau peak.
- Không dùng commitment cho baseline đủ ổn định.
- Dùng Spot cho workload không chịu được interruption rồi phải chạy lại nhiều lần.

### 3.4. Chi phí nhân lực VM

VM thường cần quy trình quản lý OS và vòng đời máy:

- Cập nhật package, kernel và security patch.
- Build, kiểm tra và phát hành machine image.
- Quản lý cấu hình, agent, certificate và secret.
- Theo dõi dung lượng, filesystem, backup và I/O.
- Xử lý drift giữa các máy.
- Quản lý autoscaling group và load balancer.

Automation và immutable image có thể giảm effort, nhưng cần đầu tư pipeline và kỹ năng. Không nên coi chi phí nhân lực bằng zero chỉ vì VM đã được tạo tự động.

## 4. TCO của mô hình container

Container đóng gói ứng dụng và dependency thành image, sau đó chạy trên một runtime hoặc nền tảng điều phối như Kubernetes. Container thường giúp tận dụng node tốt hơn bằng cách đặt nhiều workload trên cùng hạ tầng.

### 4.1. Thành phần chi phí container

- **Worker nodes:** VM hoặc máy vật lý chạy container.
- **Control plane:** phí cluster hoặc tài nguyên quản lý nếu dịch vụ tính riêng.
- **System capacity:** CPU/RAM dành cho kubelet, runtime, networking, monitoring, daemon và system pod.
- **Container registry:** lưu image, replication, scanning và data transfer.
- **Storage:** persistent volume, CSI, snapshot và backup.
- **Network:** load balancer, ingress, service mesh, NAT, cross-node và cross-zone traffic.
- **Observability:** log, metrics, tracing và retention.
- **Platform engineering:** quản lý cluster, upgrade, policy, RBAC, admission và capacity.
- **License/support:** commercial add-on, service mesh hoặc nền tảng enterprise nếu dùng.

### 4.2. Bin packing và mức sử dụng node

Container có thể giảm chi phí khi nhiều workload cùng chia sẻ node. Scheduler đặt pod dựa trên resource request, limit, affinity, taint/toleration và các ràng buộc khác.

Lợi ích phụ thuộc khả năng bin packing:

- Pod nhỏ có thể dùng phần capacity còn trống trên node.
- Workload có pattern tải khác nhau có thể chia sẻ capacity.
- Autoscaler có thể thêm/bớt node theo nhu cầu.
- Nhiều dịch vụ có thể dùng chung ingress, logging và control plane.

Nhưng tổng CPU/RAM request không thể bằng toàn bộ tài nguyên node. Phải dành phần cho OS, kubelet, runtime, daemon và system workload. Nếu request đặt quá cao, node bị lãng phí; nếu đặt quá thấp, workload có thể bị contention hoặc OOM.

### 4.3. Chi phí cluster nhàn rỗi

Một cluster nhỏ vẫn có chi phí nền:

- Control plane hoặc cluster management.
- Số node tối thiểu để duy trì availability.
- System pod và daemon chạy liên tục.
- Load balancer, disk và log.
- Capacity không thể đóng gói do CPU/RAM fragmentation.

Scale-to-zero cho workload container không có nghĩa toàn bộ cluster có thể scale về zero. Nếu cluster cần node hoặc control plane hoạt động liên tục, vẫn tồn tại chi phí nền.

### 4.4. Khi container có lợi thế chi phí

Container thường phù hợp khi:

- Có nhiều dịch vụ hoặc workload cùng chia sẻ một nền tảng.
- Cần scale từng service độc lập.
- Muốn chuẩn hóa runtime và deployment.
- Workload có thể tận dụng tốt node pool chung.
- Đội ngũ có năng lực vận hành Kubernetes/container platform.
- Cần portability giữa môi trường hoặc cloud trong giới hạn tương thích.

Với một ứng dụng đơn lẻ, tải nhỏ, không cần orchestration phức tạp, chi phí control plane và vận hành có thể làm container đắt hơn VM.

### 4.5. Chi phí vận hành Kubernetes

Kubernetes đem lại khả năng điều phối mạnh nhưng cũng tạo thêm công việc:

- Nâng cấp cluster, node image và add-on.
- Quản lý ingress, CNI, CSI, DNS và policy.
- Điều chỉnh request/limit và autoscaling.
- Bảo mật API server, RBAC, secret và network policy.
- Theo dõi node pressure, pod eviction và scheduling failure.
- Quản lý version compatibility và incident.

TCO cần tính nhân lực platform engineering và on-call. Nếu nền tảng được dùng chung cho nhiều ứng dụng, phân bổ chi phí control plane và đội platform theo mức sử dụng thay vì tính toàn bộ cho một service.

## 5. TCO của mô hình serverless

Serverless cho phép chạy code hoặc workload theo sự kiện mà không phải quản lý trực tiếp VM/node. Provider quản lý hạ tầng nền; khách hàng thường trả theo số request, thời gian thực thi, bộ nhớ hoặc cấu hình capacity.

Serverless có nhiều dạng:

- Function as a Service (FaaS).
- Container/serverless compute theo vCPU-second và GB-second.
- Managed job hoặc task chạy theo yêu cầu.
- Event-driven integration và workflow orchestration.

Không phải mọi dịch vụ mang tên serverless đều có cùng cách tính giá.

### 5.1. Thành phần chi phí serverless

- **Invocations/requests:** số lần gọi hoặc số event được xử lý.
- **Execution duration:** thời gian chạy của từng invocation/task.
- **Memory/CPU allocation:** mức tài nguyên cấp cho mỗi lần thực thi.
- **Concurrency:** số invocation đồng thời và giới hạn account/service.
- **Provisioned/minimum capacity:** chi phí giữ instance/function warm hoặc mức capacity tối thiểu nếu cấu hình.
- **API gateway/event routing:** request, event, rule và workflow step.
- **Storage/network:** log, object, database, egress và private networking.
- **Observability:** log volume, tracing và metric cardinality.
- **Retries/timeouts:** lần thực thi lại do lỗi hoặc timeout.
- **Operations:** thiết kế event, kiểm soát concurrency, quota, cold start và dependency.

### 5.2. Khi serverless có lợi thế chi phí

Serverless thường phù hợp khi:

- Tải gián đoạn hoặc có thời gian idle dài.
- Workload chạy ngắn, theo request hoặc event.
- Có thể scale-to-zero.
- Không cần kiểm soát OS hoặc runtime ở mức thấp.
- Tải có thể tăng/giảm nhanh và cần giảm việc quản lý capacity.
- Đội ngũ muốn tập trung vào logic ứng dụng.

Với tải nền rất cao và ổn định, tổng chi phí invocation/duration có thể vượt một fleet VM hoặc container được sử dụng hiệu quả. Cần benchmark và tính theo request/job thực tế.

### 5.3. Các yếu tố làm chi phí serverless tăng

- Function chạy lâu hoặc giữ bộ nhớ lớn.
- Retry lặp lại do dependency lỗi.
- Provisioned concurrency hoặc minimum instance luôn bật.
- Cold start làm tăng duration hoặc cần provision thêm capacity.
- Payload lớn, nhiều lần gọi API gateway hoặc workflow step.
- Log/tracing quá chi tiết tạo lượng dữ liệu quan sát lớn.
- Egress, NAT, private networking và cross-zone transfer.
- Database connection bị tạo quá nhiều do scale-out.

Serverless giảm việc quản lý máy nhưng không loại bỏ chi phí vận hành. Thiết kế event, idempotency, retry, observability và giới hạn concurrency vẫn cần được quản lý.

## 6. So sánh ba mô hình theo cùng tiêu chí

| Tiêu chí | VM | Container | Serverless |
| --- | --- | --- | --- |
| Đơn vị tính phí chính | VM theo thời gian, disk, network | Node/cluster, control plane, storage, network | Request, duration, memory/CPU, concurrency |
| Chi phí idle | Thường vẫn trả khi VM chạy | Node/control plane tối thiểu vẫn có thể tính phí | Có thể rất thấp khi scale-to-zero; dịch vụ phụ trợ vẫn có phí |
| Khả năng tận dụng tài nguyên | Phụ thuộc mức sử dụng từng VM | Có thể bin-pack nhiều workload trên node | Provider phân bổ tài nguyên theo execution model |
| Scale | VM/group/autoscaler | Pod và node autoscaler | Tự động theo event/request trong giới hạn |
| Quyền kiểm soát OS | Cao | Có thể chọn image nhưng phụ thuộc node/runtime | Thấp hơn, thường do provider quản lý |
| Vận hành | Patch, image, VM và fleet | Cluster, node, scheduler, image và policy | Event, function, quota, concurrency và dependency |
| Startup/cold start | Boot VM tương đối lâu | Container start thường nhanh hơn VM nhưng còn phụ thuộc node/image | Có thể có cold start hoặc provisioned capacity |
| Workload dài hạn | Thường phù hợp | Phù hợp | Có thể bị giới hạn duration hoặc kém kinh tế |
| Workload gián đoạn | Cần scale/tắt máy để giảm idle | Có thể scale workload, nhưng cluster có chi phí nền | Thường phù hợp nếu scale-to-zero |
| Portability | OS/image có thể chuyển nhưng phụ thuộc cloud | Image portable hơn trong môi trường tương thích | Phụ thuộc runtime, trigger và dịch vụ provider |
| Độ phức tạp | Quản trị hệ điều hành | Quản trị nền tảng điều phối | Quản trị event, quota và dịch vụ tích hợp |

Không có mô hình rẻ nhất trong mọi trường hợp. Mức sử dụng, thời gian idle, cách chia workload và chi phí nhân lực thường quyết định kết quả.

## 7. Mô hình hóa TCO trên cùng workload

Để so sánh công bằng, hãy xây dựng một workload tham chiếu:

- 30 triệu request mỗi tháng.
- Thời gian xử lý trung bình 150 ms.
- Mức bộ nhớ serverless tham chiếu 512 MiB cho mỗi request.
- Tải trung bình khoảng 11,6 request/giây, peak có thể đạt 100 request/giây.
- Cùng một managed database và yêu cầu backup.
- 100 GB egress mỗi tháng.
- Cùng API entry point và SLO.
- Production cần có capacity dự phòng phù hợp với yêu cầu availability.

Các con số giá dưới đây hoàn toàn giả định để minh họa phương pháp. Chúng không phải bảng giá của AWS, Azure, Google Cloud hoặc bất kỳ nhà cung cấp nào. Đơn giá thật phụ thuộc region, loại dịch vụ, hệ điều hành, discount, billing unit và thời điểm.

### 7.1. Giả định giá dùng trong ví dụ

- VM/node tương đương: 0,12 USD mỗi giờ.
- Một tháng tính 730 giờ.
- Disk: 0,08 USD/GB-tháng.
- Egress: 0,09 USD/GB.
- Serverless execution: 0,0000167 USD/GB-second.
- Serverless request: 0,20 USD cho một triệu invocation.
- API gateway: 1 USD cho một triệu request.
- Nhân lực vận hành quy đổi: 40 USD/giờ.

Các khoản managed database, backup, API gateway và egress được giữ như nhau trong ba phương án để minh họa việc phải tính cả dịch vụ ngoài compute.

### 7.2. Phương án VM

Giả sử chạy 3 VM để đáp ứng baseline và phân tán qua các failure domain:

| Khoản mục | Cách tính | Chi phí/tháng |
| --- | --- | ---: |
| VM compute | 3 × 0,12 × 730 | 262,80 USD |
| Boot disk | 3 × 40 GB × 0,08 | 9,60 USD |
| Load balancer | Giả định | 25,00 USD |
| API gateway | 30 triệu request | 30,00 USD |
| Managed database | Giả định | 90,00 USD |
| Backup | Giả định | 6,00 USD |
| Egress | 100 GB × 0,09 | 9,00 USD |
| Logging/monitoring | Giả định | 18,00 USD |
| Operations labor | 6 giờ × 40 USD | 240,00 USD |
| Migration amortization | Giả định | 20,00 USD |
| **Tổng** |  | **710,40 USD** |

### 7.3. Phương án container

Giả sử workload dùng một cluster chuyên dụng với 3 worker node tương đương VM ở trên:

| Khoản mục | Cách tính | Chi phí/tháng |
| --- | --- | ---: |
| Worker node compute | 3 × 0,12 × 730 | 262,80 USD |
| Managed control plane | Giả định | 73,00 USD |
| Persistent/boot disk | 3 × 40 GB × 0,08 | 9,60 USD |
| Load balancer | Giả định | 25,00 USD |
| API gateway | 30 triệu request | 30,00 USD |
| Managed database | Giả định | 90,00 USD |
| Backup | Giả định | 6,00 USD |
| Egress | 100 GB × 0,09 | 9,00 USD |
| Registry/scanning/logging | Giả định | 24,00 USD |
| Platform operations labor | 5 giờ × 40 USD | 200,00 USD |
| Migration amortization | Giả định | 30,00 USD |
| **Tổng** |  | **759,40 USD** |

Trong ví dụ một workload trên cluster riêng, chi phí control plane và vận hành làm container cao hơn VM. Nếu cluster dùng chung cho nhiều ứng dụng, phần control plane, node idle và platform labor được phân bổ cho nhiều workload; TCO trên mỗi ứng dụng có thể thấp hơn đáng kể.

### 7.4. Phương án serverless

Với 30 triệu request, 150 ms mỗi request và 0,5 GB bộ nhớ:

~~~text
GB-second = 30.000.000 × 0,15 × 0,5
          = 2.250.000 GB-second

Execution cost = 2.250.000 × 0,0000167
               = 37,575 USD

Request cost = 30 × 0,20
             = 6,00 USD
~~~

Giả sử thêm provisioned concurrency cho phần tải cần latency ổn định:

| Khoản mục | Cách tính | Chi phí/tháng |
| --- | --- | ---: |
| Execution | 2.250.000 GB-second × 0,0000167 | 37,58 USD |
| Invocation | 30 triệu × 0,20 USD/million | 6,00 USD |
| Provisioned concurrency | Giả định | 20,00 USD |
| API gateway | 30 triệu request | 30,00 USD |
| Managed database | Giả định | 90,00 USD |
| Backup | Giả định | 6,00 USD |
| Egress | 100 GB × 0,09 | 9,00 USD |
| Logs/traces | Giả định | 15,00 USD |
| Operations labor | 2 giờ × 40 USD | 80,00 USD |
| Migration amortization | Giả định | 25,00 USD |
| **Tổng** |  | **318,58 USD** |

### 7.5. So sánh kết quả minh họa

| Mô hình | TCO/tháng | Cost trên 1 triệu request |
| --- | ---: | ---: |
| VM | 710,40 USD | 23,68 USD |
| Container cluster riêng | 759,40 USD | 25,31 USD |
| Serverless | 318,58 USD | 10,62 USD |

Trong giả định này, serverless có chi phí thấp hơn vì execution ngắn và có thể trả theo lượng request. Kết quả không thể áp dụng máy móc cho workload khác. Nếu request tăng mạnh, duration dài, cần provisioned concurrency lớn hoặc database phải scale theo, serverless cost sẽ tăng. Nếu container cluster được chia sẻ cho nhiều ứng dụng, phần chi phí phân bổ có thể giảm. Nếu VM được dùng gần hết capacity liên tục và mua được commitment phù hợp, VM có thể cạnh tranh hơn.

## 8. Phân tích điểm hòa vốn

Điểm hòa vốn phụ thuộc phần chi phí cố định và phần chi phí biến đổi.

### 8.1. VM và container

Với VM, chi phí compute thường tăng theo số máy và thời gian chạy. Với container, chi phí node cũng có dạng tương tự, nhưng có thể chia sẻ cho nhiều workload. Điểm hòa vốn container cải thiện khi:

- Có đủ workload để tận dụng node chung.
- Resource request/limit được đặt sát nhu cầu.
- Cluster overhead được phân bổ cho nhiều dịch vụ.
- Chi phí platform engineering không tăng tuyến tính theo số ứng dụng.
- Tỷ lệ node utilization tăng mà không gây contention.

Nếu chỉ có một workload nhỏ, cluster riêng có thể không đạt mức sử dụng đủ cao để bù control plane và vận hành.

### 8.2. Serverless và compute luôn chạy

Mô hình khái quát:

~~~text
Serverless TCO =
    Fixed ancillary cost
  + Request count × Cost per request
  + Execution GB-second × Rate
  + Provisioned capacity
~~~

~~~text
VM/container TCO =
    Always-on capacity
  + Storage/network/platform overhead
  + Operations
~~~

Khi số request thấp hoặc tải gián đoạn, serverless có thể thắng vì không phải trả cho toàn bộ thời gian idle. Khi request liên tục, duration dài hoặc memory lớn, chi phí biến đổi có thể vượt chi phí capacity cố định được sử dụng hiệu quả.

### 8.3. Các biến làm thay đổi điểm hòa vốn

- Số request hoặc job mỗi tháng.
- Duration trung bình và phân phối p95/p99.
- Memory/CPU allocation.
- Tỷ lệ retry và timeout.
- Concurrency và provisioned capacity.
- Tải nền và thời gian idle.
- Node packing và mức utilization.
- Discount/commitment và giá region.
- Network egress, gateway và data transfer.
- Nhân lực vận hành và độ phức tạp nền tảng.

Không dùng average duration một mình nếu có một nhóm request rất dài. Hãy đo phân phối thời gian và kích thước payload.

## 9. Chi phí ẩn và các yếu tố thường bị bỏ sót

### 9.1. Observability

Log, metric và trace có thể trở thành khoản đáng kể khi lưu lượng tăng. Container có thể tạo nhiều log từ node, sidecar và system component. Serverless có thể tạo một log stream cho nhiều invocation và tracing có thể ghi nhiều span. VM có thể giữ agent và log lâu ngày.

Để kiểm soát:

- Đặt retention theo yêu cầu nghiệp vụ và audit.
- Giảm log trùng lặp hoặc log mức debug trong production.
- Sampling trace có kiểm soát.
- Theo dõi metric cardinality.
- Gắn cost allocation tag cho log và telemetry.

### 9.2. Network và data transfer

Một kiến trúc nhiều tầng có thể tạo thêm network hop:

- Container qua ingress, service mesh và cross-node networking.
- Serverless qua API gateway, NAT, private endpoint và database.
- VM qua load balancer, NAT và inter-zone route.

Đặt compute gần database có thể giảm latency và transfer charge. Nhưng không nên gom tất cả vào một zone nếu điều đó làm giảm availability.

### 9.3. License và phần mềm thương mại

License có thể tính theo core, socket, VM, node, user hoặc mức sử dụng. Chuyển từ VM sang container không tự động giảm license; một số sản phẩm tính theo host/node, một số tính theo vCPU hoặc replica.

Trước khi migration, kiểm tra điều khoản license, quyền chạy container, BYOL, OS image, database edition và support contract.

### 9.4. Security và compliance

Chi phí bảo mật có thể gồm:

- Image scanning và vulnerability management.
- Runtime protection, EDR và agent.
- KMS, key rotation và secret manager.
- WAF, firewall, policy engine và audit.
- Data residency, encryption và retention.
- Kiểm tra compliance và bằng chứng kiểm toán.

Một mô hình compute rẻ hơn nhưng yêu cầu thêm nhiều lớp kiểm soát có thể có TCO cao hơn. Ngược lại, managed service có thể giảm công việc patching nhưng vẫn cần đánh giá trách nhiệm bảo mật còn lại.

### 9.5. Migration và exit cost

Migration có thể cần:

- Viết lại bootstrap hoặc build pipeline.
- Chuyển image và data.
- Refactor session, file và background job.
- Chuyển monitoring, alert và deployment.
- Đào tạo đội ngũ.
- Chạy song song trong thời gian cutover.
- Giữ phương án rollback và trả chi phí cho hai môi trường.

Exit cost cũng quan trọng: chuyển khỏi dịch vụ serverless có proprietary event/API, chuyển dữ liệu lớn khỏi region hoặc thay nền tảng Kubernetes có custom operator đều có thể tốn kém.

## 10. Ảnh hưởng của availability và DR đến TCO

Không thể so sánh chi phí của một VM đơn lẻ với một serverless service multi-zone mà không điều chỉnh yêu cầu availability.

Các chi phí có thể tăng khi nâng mức sẵn sàng:

- VM: thêm instance ở zone khác, load balancer, disk replication và capacity dự phòng.
- Container: thêm node pool ở nhiều zone, control plane HA, replica và network transfer.
- Serverless: provisioned concurrency, regional deployment, event replication, database replica và quota/capacity planning.

Với cả ba mô hình, DR có thể cần backup, replication, recovery environment, capacity reservation hoặc warm standby. Phải tính chi phí khi bình thường và chi phí khi chuyển sang DR.

Nên so sánh theo cùng mục tiêu:

| Yêu cầu | Câu hỏi cần tính |
| --- | --- |
| Availability | Có bao nhiêu failure domain và bao nhiêu replica? |
| RTO | Cần capacity sẵn hay có thể provision sau sự cố? |
| RPO | Chi phí replication/backup cần thiết là bao nhiêu? |
| Peak | Có đủ capacity khi tải tăng hoặc mất một zone không? |
| Recovery | Cần giữ image, disk, secret và quota ở site dự phòng thế nào? |

## 11. Chọn mô hình theo đặc tính workload

| Đặc tính workload | VM | Container | Serverless |
| --- | --- | --- | --- |
| Tải nền ổn định 24/7 | Thường cạnh tranh | Tốt khi chia sẻ node | Có thể đắt nếu execution liên tục |
| Tải burst ngắn | Cần autoscaling và headroom | Scale pod/node, có startup delay | Thường phù hợp |
| Nhiều microservice | Có thể tăng số VM và vận hành | Phù hợp với nền tảng dùng chung | Phù hợp cho service/event nhỏ |
| Job chạy dài | Phù hợp | Phù hợp | Có thể vướng duration/cost |
| Xử lý event gián đoạn | Có thể dư capacity idle | Có thể scale worker | Thường phù hợp nếu trigger được hỗ trợ |
| Cần OS/driver đặc thù | Phù hợp | Có thể phụ thuộc node/runtime | Thường hạn chế |
| Cần GPU hoặc accelerator | Có nhiều lựa chọn instance | Có thể dùng node pool accelerator | Phụ thuộc dịch vụ serverless cụ thể |
| Đội ngũ chưa có nền tảng điều phối | Quen thuộc hơn nếu đã có kỹ năng VM | Có thể tạo overhead lớn | Có thể giảm quản lý hạ tầng nhưng cần kỹ năng cloud/event |
| Cần kiểm soát runtime sâu | Cao | Trung bình đến cao | Thấp hơn |

Đây là định hướng ban đầu. Quyết định cuối cùng phải dựa trên benchmark, SLO, pricing calculator và năng lực đội ngũ.

## 12. Quy trình xây dựng mô hình TCO

1. **Xác định workload:** request rate, job count, duration, payload, read/write và seasonality.
2. **Xác định SLO:** availability, latency, throughput, RPO/RTO và security.
3. **Thiết kế phương án tương đương:** VM fleet, container platform và serverless service đều phải đáp ứng cùng yêu cầu.
4. **Tính compute:** instance hours, node hours, GB-second, invocations và provisioned capacity.
5. **Tính storage/network:** disk, object, backup, egress, cross-zone, gateway và NAT.
6. **Tính platform:** control plane, registry, orchestration, managed integrations và license.
7. **Tính vận hành:** giờ công, on-call, patching, incident và platform engineering.
8. **Phân bổ chi phí dùng chung:** database, observability, security và network theo tiêu thức hợp lý.
9. **Tính migration và DR:** chi phí chuyển đổi, chạy song song, backup, replica và standby.
10. **Mô hình hóa kịch bản:** tải thấp, bình thường, peak, tăng trưởng và sự cố.
11. **Chuẩn hóa kết quả:** cost per successful request/job và tổng TCO trong cùng kỳ.
12. **Đo thử và cập nhật:** dùng telemetry thực tế để hiệu chỉnh giả định.

## 13. Độ nhạy theo tải và kịch bản

Không nên chỉ lập một dự báo trung bình. Dùng ít nhất ba kịch bản:

| Kịch bản | Mô tả | Điều cần quan sát |
| --- | --- | --- |
| Low | Tải giảm hoặc có nhiều giờ idle | Chi phí nền, scale-to-zero, commitment unused |
| Expected | Tải bình thường theo forecast | Cost per request và utilization |
| Peak/growth | Tải tăng mạnh hoặc tăng trưởng dài hạn | Scale-out, quota, latency, egress và chi phí biến đổi |
| Failure/DR | Mất một zone hoặc site chính | Capacity dự phòng, replication, RTO và chi phí DR |

Các biến nhạy cảm:

- Thời gian chạy trung bình và p95 của function.
- Số invocation và retry.
- Số node tối thiểu và tỷ lệ bin packing.
- Số giờ VM idle.
- Discount/commitment utilization.
- Chi phí log trên mỗi request.
- Data transfer giữa zone/region.
- Nhân lực cần thiết khi tăng số service hoặc cluster.

Sensitivity analysis cho thấy biến nào tác động mạnh nhất đến TCO. Tập trung tối ưu biến lớn thay vì chỉ giảm một khoản nhỏ trên hóa đơn.

## 14. Phân bổ chi phí khi dùng chung nền tảng

Container platform thường được nhiều team dùng chung; database, API gateway, observability và network cũng có thể phục vụ nhiều workload.

Một số phương pháp phân bổ:

- Theo CPU/memory request hoặc usage thực tế.
- Theo số request hoặc transaction.
- Theo GB lưu trữ và GB transfer.
- Theo số node hoặc namespace có mức capacity tối thiểu.
- Theo tỷ lệ sử dụng control plane hoặc license.
- Theo team/service owner bằng tag và label.

Nên phân biệt:

- **Direct cost:** chi phí gắn trực tiếp với workload.
- **Shared cost:** chi phí nền tảng dùng chung.
- **Unallocated cost:** khoản chưa gắn được owner, cần điều tra.

Không phân bổ shared cost theo một tỷ lệ cố định nếu usage thay đổi đáng kể. Dữ liệu allocation nên được rà soát theo chu kỳ.

## 15. Những sai lầm thường gặp khi so sánh TCO

- Chỉ so giá vCPU/giờ mà bỏ qua storage, network và nhân lực.
- Dùng workload hoặc SLO khác nhau cho từng mô hình.
- So VM multi-zone với serverless một vùng rồi kết luận serverless rẻ hơn.
- Bỏ qua control plane và node overhead của container.
- Cho rằng serverless không có chi phí khi không có invocation dù gateway, database, storage hoặc provisioned capacity vẫn chạy.
- Không tính retry, timeout và execution lặp.
- Không tính license theo core/node/host.
- Không tính thời gian platform team và on-call.
- Không phân bổ cluster dùng chung cho nhiều workload.
- Bỏ qua migration, dual-run và exit cost.
- Dùng một mức utilization trung bình để đại diện cho peak và failure.
- Không chuẩn hóa theo request/job thành công.
- Dùng giá minh họa như báo giá thực tế mà không kiểm tra region và điều khoản.

## 16. Checklist đánh giá TCO

**Workload và SLO**

- [ ] Cùng request/job mix và mức tải cho cả ba phương án.
- [ ] Có dữ liệu low, average, peak và seasonal.
- [ ] Có p95/p99 latency, availability, RPO và RTO.
- [ ] Đã tính capacity dự phòng và multi-zone.

**Chi phí hạ tầng**

- [ ] Compute/instance/node/execution.
- [ ] Storage, snapshot, backup và replication.
- [ ] Network, gateway, NAT, egress và cross-zone.
- [ ] Control plane, registry, API gateway và managed service.
- [ ] License, support và security tools.
- [ ] Logging, metrics, tracing và retention.

**Chi phí tổ chức**

- [ ] Build pipeline và migration.
- [ ] Patching, platform engineering và on-call.
- [ ] Incident response và DR exercise.
- [ ] Training và kỹ năng cần duy trì.
- [ ] Shared cost allocation và cost ownership.
- [ ] Vendor lock-in, data egress và exit cost.

**Kết quả**

- [ ] Có TCO theo tháng và theo vòng đời.
- [ ] Có cost per successful request/job.
- [ ] Có sensitivity analysis cho tải thấp, bình thường, peak và DR.
- [ ] Đã kiểm tra giá thực tế theo provider/region/discount.
- [ ] Đã benchmark và xác minh SLO trước khi quyết định.

## 17. Nguyên tắc ra quyết định

1. **So sánh cùng điều kiện:** cùng workload, SLO, bảo mật và failure domain.
2. **Tính toàn bộ vòng đời:** compute, data, network, platform, people, migration và DR.
3. **Chuẩn hóa theo công việc thành công:** không chỉ nhìn tổng bill hoặc giá compute.
4. **VM phù hợp với tải ổn định và nhu cầu kiểm soát máy:** đặc biệt khi utilization cao và có thể tối ưu commitment.
5. **Container có lợi khi chia sẻ nền tảng hiệu quả:** cần đủ mật độ workload để bù control plane và platform operations.
6. **Serverless phù hợp với tải gián đoạn và execution ngắn:** cần theo dõi invocation, duration, concurrency và dịch vụ phụ trợ.
7. **Không bỏ qua chi phí ẩn:** observability, license, security, on-call và migration có thể đổi thứ hạng.
8. **Tính availability/DR như một phần TCO:** capacity dự phòng và replication có chi phí thật.
9. **Mô hình hóa nhiều kịch bản:** tải thấp, bình thường, peak, tăng trưởng và sự cố.
10. **Dùng dữ liệu thực tế để hiệu chỉnh:** benchmark và billing telemetry cần cập nhật giả định.

VM, container và serverless là ba cách tổ chức và tiêu thụ năng lực compute với cấu trúc chi phí khác nhau. VM thường có chi phí capacity theo thời gian; container thêm chi phí nền tảng nhưng có thể chia sẻ node giữa nhiều workload; serverless chuyển phần lớn chi phí compute sang request và thời gian thực thi. Chỉ khi đưa cả hạ tầng, dữ liệu, network, vận hành, bảo mật, migration và availability vào cùng một mô hình TCO, tổ chức mới có thể chọn phương án phù hợp với tải và mục tiêu kinh doanh.

# So sánh chi phí serverless với container theo điểm hòa vốn

Serverless và container có cách tính chi phí khác nhau. Với function-as-a-service (FaaS), chi phí compute thường gắn với số lần gọi, thời gian thực thi và tài nguyên được cấp phát. Với container chạy liên tục, chi phí thường gắn với số instance hoặc node, CPU/RAM được giữ trong thời gian hoạt động và mức capacity dự phòng. Vì vậy, workload ít request và có lưu lượng thất thường thường tận dụng tốt mô hình tính theo lần dùng; workload có tải cao, đều và kéo dài có thể amortize chi phí container tốt hơn.

Không có một ngưỡng request cố định áp dụng cho mọi hệ thống. Điểm hòa vốn phụ thuộc vào thời gian xử lý, memory/CPU, concurrency, mức sử dụng instance, min capacity, network, database, logging, retry, discount và công sức vận hành. Muốn so sánh đúng, cần mô hình hóa cả chi phí cố định lẫn chi phí biến đổi, rồi chia tổng chi phí cho số operation nghiệp vụ thành công.

Bài học trình bày cách xây dựng cost model cho Java serverless và container, tính điểm hòa vốn, phân tích traffic profile và utilization, đưa chi phí dùng chung vào phép tính, xây dựng ví dụ định lượng và dùng FinOps để cập nhật quyết định theo dữ liệu thực tế.

## 1. So sánh hai mô hình chi phí

FaaS thường tính phí theo số invocation và tài nguyên compute được sử dụng trong thời gian function chạy. Một function chạy ngắn và không có traffic có thể gần như không tạo compute charge, tùy dịch vụ và cấu hình. Tuy nhiên, API gateway, queue, database, log, network egress hoặc provisioned capacity vẫn có thể phát sinh phí.

Container service chạy liên tục thường cần trả tiền cho capacity được giữ sẵn, kể cả khi không có request. Khi traffic tăng, cần thêm instance hoặc node. Nếu instance có nhiều khoảng idle, một phần chi phí không tạo ra operation hữu ích. Ngược lại, nếu workload sử dụng CPU/RAM ổn định ở mức cao, container có thể xử lý nhiều request trên cùng capacity và giảm chi phí biên trên mỗi request.

| Khía cạnh | Serverless function (FaaS) | Container service chạy liên tục |
|---|---|---|
| Đơn vị tính phí compute | Invocation, duration, memory/compute allocation; có thể có concurrency capacity riêng | Instance/node uptime, vCPU, RAM hoặc thời gian sử dụng tài nguyên |
| Khi không có traffic | Có thể scale-to-zero; vẫn có phí tài nguyên phụ trợ hoặc capacity được giữ ấm | Thường vẫn trả tiền cho min instances, node hoặc cluster capacity |
| Khi traffic tăng | Nền tảng tự scale theo quota và concurrency | Autoscaler tăng instance/replica hoặc node |
| Tải thất thường | Có thể tiết kiệm vì không giữ compute liên tục | Có thể trả tiền cho idle capacity hoặc scale lag |
| Tải ổn định cao | Chi phí invocation/compute có thể tăng theo từng request | Có thể tận dụng capacity và pooling hiệu quả |
| Cold start/startup | Có thể phát sinh khi tạo execution environment mới | Instance thường đã chạy, nhưng scale-out vẫn cần startup |
| Vận hành | Ít quản lý runtime host hơn; vẫn cần quản lý trigger, quota, IAM và dependency | Cần quản lý image, rollout, scaling, runtime, node/cluster hoặc nền tảng managed |
| Workload dài hạn | Bị giới hạn bởi timeout và mô hình invocation | Thường phù hợp với process dài, streaming hoặc service liên tục |

Lưu ý: container không đồng nghĩa với máy chủ luôn bật. Container có thể chạy trên nền tảng managed có scale-to-zero hoặc tính phí theo request. Khi so sánh, cần xác định chính xác lựa chọn là FaaS, managed container request-based hay container chạy trên VM/Kubernetes có capacity thường trực. Các mô hình này có cost curve khác nhau.

## 2. Phân loại chi phí trước khi tính điểm hòa vốn

Một so sánh công bằng cần chia chi phí thành ba nhóm:

1. **Chi phí cố định:** phát sinh theo tháng hoặc theo giờ dù traffic thấp.
2. **Chi phí biến đổi:** tăng theo request, thời gian compute, dữ liệu hoặc message.
3. **Chi phí dùng chung:** database, storage, network, observability và dịch vụ khác mà cả hai phương án cùng cần.

### Chi phí của serverless

- Số lần invocation/request.
- Thời gian thực thi được tính phí.
- Memory hoặc compute allocation.
- Provisioned concurrency, minimum instances hoặc capacity giữ ấm nếu dùng.
- Ephemeral storage vượt mức miễn phí hoặc quota.
- Event source polling, queue request, stream processing.
- API Gateway/HTTP ingress.
- Network egress, NAT, private connectivity và cross-region traffic.
- Logs, metrics, traces và retention.
- Retry, duplicate delivery và DLQ.
- Database, cache, object storage và external API.
- Chi phí bảo mật, secret access và key management nếu tính riêng.

### Chi phí của container

- vCPU và RAM của instance/node theo thời gian.
- Số replica tối thiểu và capacity dự phòng.
- Node/VM, control plane hoặc cluster fee nếu có.
- Load balancer, ingress, service mesh và API gateway.
- Persistent disk, image registry và artifact storage.
- Network egress, NAT và cross-zone traffic.
- Logs, metrics, traces và retention.
- Autoscaling headroom, rollout surge và capacity cho high availability.
- Database, cache, queue, object storage và external API.
- Nhân lực vận hành, patching, upgrade, incident response và quản lý cluster.

### Chi phí dùng chung

Database hoặc queue không biến mất khi đổi từ FaaS sang container. Tuy nhiên, mức sử dụng có thể thay đổi:

- FaaS scale-out nhanh có thể tạo nhiều connection ngắn hạn đến database.
- Container có thể giữ connection pool lâu và tận dụng connection reuse tốt hơn.
- Một phương án có thể tạo nhiều retry hơn do timeout hoặc cold start.
- Cả hai có thể phát sinh cùng chi phí egress nhưng volume khác nhau.
- Cấu hình log/trace khác nhau có thể làm chi phí observability lệch đáng kể.

Không cộng chi phí dùng chung hai lần. Hãy phân loại chi phí nào giữ nguyên, chi phí nào thay đổi theo kiến trúc và chi phí nào chỉ phát sinh ở một phương án.

## 3. Cost model: fixed cost và variable cost

Để tìm điểm hòa vốn, bắt đầu bằng mô hình đơn giản theo số business operation mỗi tháng.

Ký hiệu:

- (N): số operation đủ điều kiện trong tháng.
- (F_s): chi phí cố định hàng tháng của phương án serverless.
- (v_s): chi phí biến đổi trung bình cho mỗi operation ở phương án serverless.
- (F_c): chi phí cố định hàng tháng của phương án container.
- (v_c): chi phí biến đổi trung bình cho mỗi operation ở phương án container.

Khi đó:

```text
C_serverless(N) = F_s + N × v_s
C_container(N)  = F_c + N × v_c
```

Chi phí tổng có thể bổ sung các nhóm network, storage, logs, database và vận hành. Trong mô hình đơn giản, những khoản cố định được đưa vào F; khoản tăng theo operation được đưa vào v.

### Công thức điểm hòa vốn

Điểm hòa vốn là số operation tại đó hai phương án có tổng chi phí bằng nhau:

```text
F_s + N × v_s = F_c + N × v_c
```

Suy ra:

[
N^* = \frac{F_c - F_s}{v_s - v_c}
]

Công thức này có điểm hòa vốn dương khi chi phí cố định container cao hơn serverless ((F_c > F_s)) và chi phí biến đổi mỗi operation của serverless cao hơn container ((v_s > v_c)). Nếu các điều kiện không đúng, không có điểm giao dương theo mô hình tuyến tính này; một phương án có thể rẻ hơn trên toàn miền đang xét.

### Ý nghĩa của điểm hòa vốn

- Khi (N < N^*), serverless có thể rẻ hơn vì chi phí cố định thấp.
- Khi (N > N^*), container có thể rẻ hơn nếu chi phí biến đổi trên mỗi operation thấp hơn.
- Gần (N^*), các chi phí phụ, traffic shape, latency, reliability và công sức vận hành có thể quyết định phương án phù hợp.

Điểm hòa vốn là kết quả của giả định, không phải một con số cố định của FaaS hay container. Nếu container cần thêm node theo từng ngưỡng hoặc FaaS có nhiều tier giá, cost curve sẽ có các đoạn gãy thay vì một đường thẳng.

## 4. Ví dụ tính điểm hòa vốn bằng số liệu giả định

Giả sử một Java API có hai phương án. Các con số dưới đây chỉ dùng để minh họa cách tính, không phải bảng giá của AWS, Google Cloud, Azure hay nhà cung cấp nào.

| Thành phần | Serverless | Container |
|---|---:|---:|
| Fixed cost mỗi tháng | 20 USD | 140 USD |
| Variable cost mỗi operation | 0,000004 USD | 0,000001 USD |

Serverless có fixed cost thấp hơn, nhưng variable cost cao hơn trong giả định này.

```text
N* = (140 - 20) / (0.000004 - 0.000001)
   = 120 / 0.000003
   = 40,000,000 operations/month
```

| Sản lượng tháng | Serverless | Container | Phương án rẻ hơn |
|---:|---:|---:|---|
| 10 triệu | 20 + 10.000.000 × 0,000004 = 60 USD | 140 + 10.000.000 × 0,000001 = 150 USD | Serverless |
| 40 triệu | 180 USD | 180 USD | Hòa vốn |
| 60 triệu | 260 USD | 200 USD | Container |

Trong ví dụ, điểm giao nằm ở 40 triệu operation/tháng. Ở dưới mức này, phần fixed cost thấp giúp serverless có lợi thế. Ở trên mức này, variable cost thấp hơn của container bù được fixed cost ban đầu.

Giả định (v_c) là chi phí biên đã phân bổ trong capacity hiện có. Khi vượt capacity, container có thể cần thêm replica/node và fixed cost tăng theo bậc. Do đó, không ngoại suy tuyến tính mãi đến mọi mức traffic.

## 5. Tính variable cost của một function

Với FaaS, variable cost thường gồm request charge và compute charge. Một công thức khái quát:

```text
Function compute cost
  = billable GB-seconds × price per GB-second

Request cost
  = billable invocations × price per request unit

FaaS variable cost
  = compute cost + request cost + other per-use charges
```

Trong đó:

```text
Billable GB-seconds
  = invocation count × billable duration × configured memory in GB
```

Công thức đơn giản này cần điều chỉnh theo semantics của provider: duration rounding/minimum, CPU allocation, architecture, ephemeral storage, free tier, provisioned concurrency, snapshot/restore và các mức giá khác.

### Ví dụ compute usage

Giả sử:

- 5.000.000 invocation/tháng.
- Memory cấu hình: 512 MB = 0,5 GB.
- Billable duration trung bình: 250 ms = 0,25 giây.

```text
GB-seconds
= 5,000,000 × 0.5 × 0.25
= 625,000 GB-seconds
```

Từ đó nhân với đơn giá GB-second của region/runtime/architecture đang dùng và cộng request charge. Đây mới là compute/request cost; chưa gồm API Gateway, queue, logs, egress, database, NAT hoặc provisioned capacity.

### Memory ảnh hưởng cả giá và thời gian

Tăng memory có thể làm chi phí mỗi giây cao hơn, nhưng với một số runtime, nó cũng tăng CPU hoặc throughput và rút ngắn duration. Vì vậy, không mặc định memory thấp nhất là rẻ nhất.

Ví dụ giả định:

| Cấu hình | Memory | Duration | GB-seconds mỗi invocation |
|---|---:|---:|---:|
| A | 0,5 GB | 800 ms | 0,4 |
| B | 1 GB | 300 ms | 0,3 |
| C | 2 GB | 120 ms | 0,24 |

Cấu hình C dùng memory cao nhất nhưng tổng GB-seconds thấp nhất trong ví dụ. Cần benchmark bằng workload thật, kiểm tra latency và giá compute tương ứng trước khi chọn.

## 6. Tính chi phí container

Với container chạy liên tục trên VM hoặc Kubernetes, chi phí compute thường phụ thuộc vào capacity được giữ trong thời gian hoạt động.

Một mô hình khái quát:

```text
Container compute cost
  = Σ(instance count × instance hourly cost × active hours)
    + node/control-plane/platform charges
```

Cần phân biệt:

- **Requested resources:** CPU/RAM mà scheduler dành hoặc dùng để tính capacity.
- **Actual utilization:** CPU/RAM thực tế workload tiêu thụ.
- **Provisioned capacity:** tổng capacity đã trả tiền hoặc phải giữ.
- **Useful throughput:** số operation thành công trên capacity đó.

Nếu container yêu cầu 2 vCPU và 4 GB RAM nhưng chỉ dùng trung bình 15% CPU, chi phí vẫn có thể dựa trên resource request hoặc instance uptime tùy nền tảng. Tối ưu resource request, packing nhiều workload trên node và autoscaling có thể giảm chi phí, nhưng phải giữ headroom cho peak và failure.

### Tính utilization

```text
CPU utilization = used CPU / provisioned CPU
Memory utilization = used memory / provisioned memory
```

Utilization thấp kéo dài có thể cho thấy overprovisioning. Utilization cao kéo dài có thể làm latency tăng và giảm khả năng chịu burst. Không tối ưu chỉ để đẩy utilization lên 100%; capacity dự phòng có giá trị cho availability và scale-out.

## 7. Traffic shape quyết định cost curve

Hai hệ thống có cùng số request mỗi tháng vẫn có thể có chi phí khác nhau nếu phân bố traffic khác nhau.

Ví dụ:

- Hệ thống A nhận 10 triệu request đều trong cả tháng.
- Hệ thống B nhận 10 triệu request trong 4 ngày chiến dịch và gần như không có traffic trong thời gian còn lại.

FaaS có thể tận dụng khoảng idle của hệ thống B bằng cách scale về zero. Container chạy liên tục có thể trả chi phí capacity trong những ngày ít tải, trừ khi nền tảng cho phép scale-to-zero.

Ngược lại, nếu hệ thống A có traffic đều và concurrency ổn định, container có thể giữ một lượng instance vừa đủ và sử dụng chúng liên tục.

### Những đại lượng cần thu thập

- Request/event count theo phút hoặc giờ, không chỉ tổng tháng.
- Peak RPS và thời gian duy trì peak.
- Concurrency distribution.
- Duration p50/p95/p99.
- Memory/CPU usage và thời gian idle.
- Tỷ lệ retry, timeout, duplicate và failed invocation.
- Batch size thực tế và queue backlog.
- Số giờ phải giữ min instances.
- Scale-out/scale-in delay.
- Mức traffic theo tenant, region và loại operation.

Không dùng average monthly RPS để mô tả một workload có burst ngắn và rất cao. Cần mô hình hóa histogram hoặc time series để dự báo capacity và bill.

## 8. Chi phí idle và minimum capacity

Scale-to-zero là lợi thế của một số nền tảng serverless, nhưng không phải mọi thành phần đều scale về zero.

Một FaaS function có thể không phát sinh compute charge khi không chạy, nhưng hệ thống vẫn có thể trả tiền cho:

- API Gateway hoặc public endpoint.
- Database provisioned capacity.
- NAT Gateway hoặc network appliance.
- Queue/topic hoặc stream capacity.
- Logs retention và metrics.
- Provisioned concurrency hoặc minimum instances.
- Storage, backup và key management.

Container cũng có thể scale-to-zero nếu dùng managed platform hỗ trợ. Khi đó, cần tính startup latency, min instance policy và billing mode. Không so sánh FaaS scale-to-zero với container luôn bật nếu container platform được cấu hình scale-to-zero trong kiến trúc thực tế.

### Chi phí giữ ấm

Nếu cần giảm cold start, FaaS có thể cần provisioned concurrency hoặc capacity warm. Khoản này tạo fixed cost gần giống container minimum instances. Khi capacity giữ ấm lớn và traffic ổn định, lợi thế fixed cost thấp của serverless có thể giảm.

Cần mô hình hóa hai cấu hình:

1. Serverless scale-to-zero, chấp nhận cold start trong SLO.
2. Serverless có warm/provisioned capacity để đáp ứng latency.

Đối chiếu với container có min replicas tương ứng để so sánh công bằng.

## 9. Chi phí retry và operation thất bại

Bill không chỉ tăng theo số operation người dùng gửi. Retry có thể tạo thêm invocation và compute duration. Một dependency lỗi có thể khiến function chạy nhiều lần, tạo chi phí nhưng không hoàn tất nghiệp vụ.

Một mô hình hữu ích:

```text
Expected attempts per operation
  = 1 + expected retry attempts

Compute cost per operation
  = expected attempts × average cost per attempt
```

Ví dụ nếu trung bình một business operation cần 1,15 invocation do retry, variable compute cost có thể tăng khoảng 15% so với trường hợp một attempt, nếu các attempt có cost tương đương. Thực tế attempt lỗi có thể ngắn hơn hoặc dài hơn attempt thành công.

Đo **cost per successful operation** để không che khuất chi phí của lỗi:

```text
Cost per successful operation
  = total attributable cost / successful business operations
```

Nếu tổng bill giữ nguyên nhưng tỷ lệ success giảm, cost per successful operation tăng. Đây là chỉ số tốt hơn cost per invocation khi đánh giá chất lượng và hiệu quả kinh tế.

### Duplicate và redrive

- Message được giao lại có thể tạo thêm invocation.
- DLQ redrive làm tăng compute và downstream calls.
- Poison message có thể lặp lại nhiều lần mà không tạo kết quả.
- Idempotency ngăn side effect trùng nhưng không loại bỏ hoàn toàn chi phí của invocation duplicate.

Cần tính retry policy, visibility/ack deadline, max receive count và retention trong cost model.

## 10. Chi phí network và data transfer

Network có thể là khoản đáng kể, đặc biệt khi function chạy trong private network hoặc truy cập nhiều dịch vụ qua NAT.

Theo dõi:

- Internet egress.
- Cross-zone/cross-region transfer.
- NAT Gateway processing/hour charges nếu provider áp dụng.
- Private endpoint hoặc VPC connector.
- API Gateway data processing.
- Data transfer giữa service và database.
- Payload size và số lần truyền lại do retry.

Ví dụ, một function tải object 10 MB rồi gửi tiếp sang một API khác có thể tạo data transfer đáng kể dù compute duration ngắn. Nếu function và storage/database ở khác region, phí transfer và latency có thể tăng.

Tối ưu bằng cách đặt compute gần data, dùng private endpoint phù hợp, tránh copy payload không cần thiết và truyền reference đến object thay vì gửi file lớn qua nhiều function.

Không mặc định network cost giống nhau giữa FaaS và container. Route, NAT, private connectivity và vị trí deployment có thể khác.

## 11. Database và connection pooling trong cost model

Database thường là một phần lớn của tổng chi phí và có thể thay đổi theo mô hình compute.

### FaaS

- Scale-out nhanh có thể tạo nhiều connection đồng thời.
- Function ngắn hạn có thể mở/đóng connection thường xuyên.
- Connection proxy/pooling có thể thêm phí nhưng giảm áp lực database.
- Reserved concurrency hoặc max instances giúp giới hạn connection demand.
- Một invocation retry có thể lặp query hoặc transaction nếu idempotency chưa đúng.

### Container

- Connection pool được giữ lâu và có thể reuse tốt.
- Số pool theo replica nhân với max connection mỗi pool.
- Instance min capacity có thể giữ connection ngay cả khi traffic thấp.
- Autoscaling replica có thể tạo connection burst khi scale-out.

Công thức ngân sách sơ bộ:

```text
Potential DB connections
  ≈ active compute instances × max pool size per instance
```

Đây là giới hạn tiềm năng, không phải số connection luôn mở. Đặt pool size theo tổng ngân sách database dành cho tất cả service, worker, admin và migration.

Khi so sánh chi phí, tính cả database tier/compute/storage và connection proxy nếu một phương án làm thay đổi nhu cầu đó.

## 12. Chi phí logging, metrics và tracing

Observability cần thiết để vận hành serverless và container, nhưng lượng telemetry có thể tăng theo request volume.

Các yếu tố:

- Log bytes mỗi request.
- Số metric series và cardinality.
- Trace sampling rate.
- Log retention.
- Export telemetry qua network.
- Alerting và dashboard plan.
- Chi phí lưu trữ và truy vấn log.

Một function scale-out thành hàng nghìn invocation có thể tạo log volume lớn nếu log payload hoặc stack trace đầy đủ ở mọi lần retry. Container cũng có thể tạo volume lớn từ access log và sidecar.

Tối ưu:

- Dùng structured logging và log đúng mức cần thiết.
- Không log secret, token hoặc payload nhạy cảm.
- Dùng sampling có chủ đích cho trace, nhưng giữ metric SLI đầy đủ.
- Tránh label cardinality cao như request ID hoặc tenant ID không giới hạn.
- Đặt retention theo mục đích audit và điều tra.
- Tách debug logging khỏi production mặc định.

Không tắt telemetry cần thiết chỉ để giảm bill; hãy tối ưu volume và giữ khả năng phát hiện lỗi.

## 13. Operational cost và total cost of ownership

Hạ tầng bill không phải toàn bộ chi phí. Container tự quản lý có thể cần thời gian của đội kỹ thuật cho:

- OS/runtime patching.
- Node upgrade và cluster maintenance.
- Image build, scan và lifecycle.
- Capacity planning và autoscaling tuning.
- Deployment, rollback và incident response.
- On-call cho cluster/network.
- Security hardening và compliance evidence.

FaaS giảm một phần công việc quản lý host và runtime capacity, nhưng vẫn cần:

- Quản lý IAM, network và secret.
- Theo dõi concurrency/quota/cold start.
- Xử lý timeout, retry, DLQ và idempotency.
- Tối ưu invocation duration/memory.
- Quản lý nhiều function và event source.
- Debug distributed trace và deployment.
- Kiểm soát chi phí dịch vụ phụ trợ.

Đưa công sức vận hành vào TCO (total cost of ownership). Có thể ước lượng giờ công theo tháng nhân với fully loaded labor rate, nhưng cần tránh phân bổ cùng một giờ công cho nhiều dịch vụ.

Không nên chọn FaaS chỉ vì bill compute thấp nếu hệ thống cần nhiều workaround, hoặc chọn container chỉ vì compute đơn giá thấp mà bỏ qua chi phí vận hành.

## 14. Chi phí theo từng nền tảng: cần đọc đúng billing dimension

Tên dịch vụ không đủ để suy ra bill. Cần xác định loại trigger, pricing mode, region, runtime, architecture và cấu hình.

| Nền tảng | Các dimension thường cần kiểm tra |
|---|---|
| AWS Lambda | Request count, duration, memory/architecture, provisioned concurrency, ephemeral storage, data transfer, event source và dịch vụ phụ trợ |
| Google Cloud Functions/Cloud Run functions | Invocation, compute time, memory/CPU, networking, build/artifact, logging và dịch vụ Cloud Run liên quan theo generation |
| Azure Functions | Hosting plan, execution/resource consumption, always-ready/prewarmed instances, storage, networking và trigger integration |
| Managed container platform | Request-based hay instance-based billing, vCPU/RAM time, min/max instances, idle billing, ingress/egress và log/metric |
| Kubernetes/VM container | Node/VM uptime, requested resources, autoscaling, control plane, load balancer, disk, network và operational overhead |

Một số nền tảng có nhiều thế hệ hoặc billing mode. Ví dụ một function có thể được triển khai trên nền tảng container managed; cùng code nhưng cost model thay đổi theo cách tính request-based hoặc instance-based. Hãy lấy pricing calculator và invoice export hiện hành của đúng region thay vì dùng con số từ bài viết cũ.

### Free tier và discount

Free tier có thể làm một phương án có vẻ rẻ trong giai đoạn đầu nhưng không nên dùng làm cơ sở duy nhất cho quyết định dài hạn. Cần tính cả:

- Ngưỡng miễn phí có điều kiện.
- Giá sau khi vượt ngưỡng.
- Savings Plans/committed use/reserved capacity.
- Enterprise discount.
- Spot/preemptible capacity nếu phù hợp.
- Phí support và marketplace.
- Currency, thuế và thời gian hiệu lực của báo giá.

So sánh cùng một thời gian, region, currency và giả định discount.

## 15. Worked example: một Java API có traffic theo giờ

Giả sử một API quản lý báo cáo có các đặc điểm:

- 12 triệu request/tháng.
- 80% request đến trong giờ làm việc.
- Duration trung bình 350 ms.
- Memory FaaS 1 GB.
- Một số ngày cuối tháng traffic tăng gấp 4.
- Database và object storage dùng chung cho cả hai phương án.

Compute usage FaaS sơ bộ:

```text
12,000,000 × 1 GB × 0.35 seconds
= 4,200,000 GB-seconds
```

Cần nhân với đơn giá GB-second tương ứng, cộng request charge, network, logs, API gateway và các dịch vụ phụ trợ. Nếu cuối tháng duration tăng do database contention, GB-seconds sẽ cao hơn giả định 350 ms.

Đối với container, không thể chỉ lấy 12 triệu request chia cho một throughput lý thuyết. Cần benchmark throughput mỗi instance dưới latency SLO và tính số instance cần giữ ở peak. Ví dụ nếu một instance chịu tải bền vững 40 RPS, peak 500 RPS cần ít nhất 13 instance theo phép chia đơn giản, cộng headroom và HA. Chi phí phụ thuộc số giờ giữ min capacity và thời gian scale-out.

### Kịch bản cần so sánh

| Kịch bản | FaaS | Container |
|---|---|---|
| Traffic thấp ban đêm | Compute có thể scale về zero; phụ trợ vẫn tính phí | Min instance/node có thể tiếp tục tính phí |
| Giờ làm việc đều | Request và GB-second tăng theo tải | Instance được sử dụng liên tục, có thể hiệu quả |
| Peak cuối tháng | Scale-out nhanh nhưng có thể tăng concurrency/DB pressure | Autoscaler tăng replica; cần đủ quota và startup time |
| Cold start nhạy cảm | Có thể cần provisioned/warm capacity | Instance min capacity giữ sẵn |
| Database bottleneck | Thêm function concurrency không giải quyết DB | Thêm replica cũng không giải quyết DB |
| Retry từ provider | Tăng invocation và compute | Tăng request/CPU time nhưng có thể tận dụng instance đang chạy |

Không thể kết luận phương án rẻ hơn chỉ từ số request. Cần đo traffic theo phút, benchmark instance, lấy giá hiện hành và tính shared cost theo mức sử dụng thực tế.

## 16. Phân tích sensitivity và nhiều kịch bản

Một điểm hòa vốn duy nhất có thể gây hiểu nhầm nếu input thay đổi. Hãy tính ít nhất ba kịch bản:

- **Low:** traffic thấp hơn dự báo, nhiều thời gian idle.
- **Base:** traffic theo forecast hiện tại.
- **High:** peak lớn, tăng trưởng người dùng hoặc chiến dịch.
- Có thể bổ sung **stress/recovery:** retry/replay sau sự cố hoặc một region/zone mất capacity.

Các biến nên thay đổi trong sensitivity analysis:

| Biến | Tác động |
|---|---|
| Average duration | Tăng GB-seconds và concurrency của FaaS |
| Memory/CPU allocation | Thay đổi đơn giá compute và thời gian xử lý |
| Request volume | Tăng request charge và variable cost |
| Retry rate | Tăng invocation/compute nhưng không tăng good operations tương ứng |
| Peak-to-average ratio | Tác động min capacity và scale-out |
| Container utilization | Quyết định chi phí idle và số replica cần giữ |
| Minimum instances | Tăng fixed cost để giảm cold start |
| Discount/commitment | Có thể giảm giá container hoặc compute capacity |
| Egress/data volume | Tăng chi phí network |
| Observability volume | Tăng log/trace cost |

Có thể tính lại (N^*) cho từng kịch bản. Nếu điểm hòa vốn thay đổi rất nhiều khi duration chỉ tăng 10%, hãy ưu tiên tối ưu duration và đo lại trước khi ra quyết định kiến trúc.

## 17. FinOps: phân bổ và theo dõi chi phí

FinOps là vòng lặp liên tục giữa engineering, finance và product để hiểu, phân bổ và tối ưu chi phí cloud.

Các thực hành quan trọng:

- Gắn project/service/environment/team tags hoặc labels.
- Dùng cost allocation tags để phân bổ shared services.
- Theo dõi chi phí theo tenant hoặc business unit khi có thể.
- So sánh forecast với actual spend.
- Tạo budget và anomaly alert.
- Đo cost per successful operation.
- Ghi nhận release gây thay đổi duration, memory hoặc traffic.
- Đặt owner cho mỗi dịch vụ và ngân sách.
- Review chi phí định kỳ, không chỉ khi vượt budget.

### Showback và chargeback

- **Showback:** hiển thị chi phí cho team/tenant sử dụng nhưng chưa tính tiền nội bộ.
- **Chargeback:** phân bổ hoặc tính chi phí vào ngân sách của team/tenant.

Để phân bổ shared cost, có thể dùng tỷ lệ request, GB-seconds, storage bytes, data transfer hoặc một driver phù hợp với nguyên nhân tạo chi phí. Tránh chia đều nếu mức sử dụng rất khác nhau.

### Unit economics

Các chỉ số hữu ích:

```text
Cost per successful request
  = attributable monthly cost / successful requests

Cost per tenant
  = attributable tenant cost / tenant count

Cost per report
  = compute + storage + transfer + shared allocation
    / completed reports
```

Chọn denominator theo giá trị nghiệp vụ. Ví dụ payment service nên theo cost per successful payment, không chỉ cost per invocation.

## 18. Quy trình so sánh thực tế

Một quy trình đánh giá có thể thực hiện như sau:

1. Xác định workload và đơn vị nghiệp vụ: request, job, report hoặc event.
2. Thu thập request volume theo thời gian, peak RPS, duration và concurrency.
3. Đo memory/CPU và batch size thực tế của Java workload.
4. Xác định cấu hình FaaS: memory, timeout, concurrency, provisioned capacity và trigger.
5. Xác định cấu hình container: vCPU/RAM, min/max replicas, utilization target, load balancer và autoscaling.
6. Liệt kê shared services: database, queue, cache, storage, network, logs và external APIs.
7. Lấy đơn giá hiện hành từ calculator/invoice export theo đúng region và pricing mode.
8. Tính fixed cost và variable cost cho từng phương án.
9. Tính điểm hòa vốn theo mô hình phù hợp; ghi rõ điều kiện và giả định.
10. Chạy low/base/high traffic scenarios và sensitivity analysis.
11. Load test để xác định throughput bền vững và latency SLO.
12. Tính cost per successful business operation, bao gồm retry và failure cost.
13. Đưa operational labor, reliability và delivery speed vào TCO.
14. Triển khai thử có giới hạn, đo bill thực tế và hiệu chỉnh model.
15. Review định kỳ khi traffic, giá, runtime hoặc kiến trúc thay đổi.

## 19. Những lỗi so sánh chi phí thường gặp

- **Chỉ so compute price:** bỏ qua gateway, network, database, logs và storage; so sánh toàn bộ bill có thể quy trách nhiệm.
- **Dùng tổng request tháng mà bỏ traffic shape:** không thấy idle và peak; dùng time series.
- **Giả định container luôn bật:** managed container có thể scale-to-zero; xác minh billing mode.
- **Giả định serverless hoàn toàn miễn phí khi idle:** database, NAT, queue, logs và warm capacity vẫn có thể tính phí.
- **Không tính provisioned concurrency/min instances:** fixed cost serverless bị đánh giá thấp.
- **Dùng average duration không đại diện:** cold start, tail latency và dependency delay có thể tăng bill; đo phân phối.
- **Bỏ qua retry và duplicate:** chi phí tăng nhưng operation thành công không tăng tương ứng.
- **Tính container theo CPU usage nhưng bỏ requested/allocated capacity:** bill có thể dựa trên capacity được giữ.
- **Coi utilization 100% là tối ưu:** thiếu headroom làm latency và failure tăng.
- **Bỏ qua database connection pressure:** scale-out có thể buộc nâng database tier hoặc thêm proxy.
- **Không tính operational labor:** TCO bị thiếu phần chi phí vận hành.
- **Dùng free tier để dự báo dài hạn:** khi vượt ngưỡng, cost curve thay đổi.
- **Dùng một điểm hòa vốn duy nhất:** giả định linear không phản ánh step scaling và discount.
- **Không đo cost per successful operation:** chi phí của retry/failure bị che bởi cost per invocation.
- **Không cập nhật giá:** pricing thay đổi theo region, generation và thời gian.

## 20. Gợi ý chọn serverless hay container

Serverless function thường phù hợp khi:

- Traffic không đều, có thời gian idle đáng kể.
- Công việc ngắn, stateless và có trigger rõ.
- Nhu cầu scale biến động khó dự báo.
- Muốn giảm công việc quản lý host và runtime.
- Chi phí theo operation phù hợp với unit economics.
- Có thể thiết kế retry, idempotency và timeout theo giới hạn FaaS.

Container service chạy liên tục thường phù hợp khi:

- Traffic cao và ổn định trong phần lớn thời gian.
- Process dài, streaming hoặc cần giữ kết nối lâu.
- Cần kiểm soát runtime, thư viện native hoặc sidecar.
- Workload tận dụng CPU/RAM liên tục và pooling.
- Cần latency ổn định với warm capacity.
- Đội có khả năng vận hành platform và autoscaling.

Mô hình kết hợp thường hợp lý:

- HTTP API ngắn chạy bằng FaaS.
- Worker xử lý streaming dài chạy container.
- Event consumer bursty dùng FaaS, nhưng giới hạn concurrency theo database.
- Một service có tải ổn định cao chạy container; tác vụ nền theo sự kiện chạy function.
- Report generation nặng chạy container job, còn request tạo job chạy FaaS.

Đừng chọn theo nhãn công nghệ. Chọn theo workload, SLO, cost curve, operational capacity và khả năng thay đổi trong tương lai.

## 21. Ghi nhớ

Serverless thường có fixed compute cost thấp và variable cost theo invocation/duration; container chạy liên tục thường có fixed capacity cost cao hơn nhưng có thể có variable cost biên thấp hơn khi utilization ổn định. Điểm hòa vốn trong mô hình tuyến tính được tính bằng chênh lệch fixed cost chia cho chênh lệch variable cost mỗi operation, nhưng kết quả chỉ có ý nghĩa khi các giả định và điều kiện của công thức được đáp ứng.

So sánh công bằng phải tính traffic shape, memory/CPU, duration, min capacity, retry, network, database, logs, storage, discount và công sức vận hành. Hãy đo cost per successful business operation thay vì chỉ cost per invocation, rồi kiểm chứng bằng load test và bill thực tế.

FaaS có thể phù hợp với workload bursty và ít traffic; container có thể có lợi thế với tải ổn định, sử dụng capacity cao. Điểm hòa vốn thay đổi khi workload, giá và cấu hình thay đổi, vì vậy FinOps cần được thực hiện liên tục cùng engineering và product.


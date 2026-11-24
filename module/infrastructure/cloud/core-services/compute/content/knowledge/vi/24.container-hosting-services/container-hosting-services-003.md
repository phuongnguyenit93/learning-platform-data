# Lựa chọn capacity dựa trên CPU, memory và yêu cầu mạng

Trong chương **Dịch vụ chạy container**, việc chọn capacity là xác định mỗi container cần bao nhiêu CPU, bộ nhớ và năng lực mạng để đáp ứng tải với độ trễ, độ sẵn sàng và chi phí phù hợp. Capacity cần xuất phát từ đặc điểm workload và số liệu đo được. Chọn cấu hình quá nhỏ gây throttling, OOM hoặc nghẽn mạng; chọn quá lớn làm tăng chi phí và có thể khiến bộ lập lịch khó xếp workload lên node.

Bài học này thuộc phạm vi **CLOUD_CORE_SERVICES_COMPUTE**: tìm hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless, cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật, đồng thời thực hành triển khai, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành.

## 1. Chuyển yêu cầu ứng dụng thành chỉ số capacity

Trước khi chọn loại dịch vụ hoặc kích thước container, hãy mô tả workload bằng các chỉ số có thể kiểm chứng:

| Nhóm yêu cầu | Cần thu thập | Ý nghĩa khi chọn capacity |
|---|---|---|
| Lưu lượng | Request/giây trung bình, p95, đỉnh và thời lượng đỉnh | Xác định số replica và khả năng chịu burst |
| Đồng thời | Số request đang xử lý, số kết nối mở, hàng đợi | Ảnh hưởng đến bộ nhớ, thread, connection pool |
| Độ trễ | SLO p95/p99, thời gian xử lý CPU và thời gian chờ I/O | Xác định headroom và vị trí nghẽn |
| Dữ liệu | Kích thước request/response, payload, file hoặc stream | Ước lượng throughput và bộ nhớ đệm |
| Phụ thuộc | Database, cache, dịch vụ nội bộ, API bên ngoài | Tính cả lưu lượng east-west và giới hạn downstream |
| Vận hành | Mức sẵn sàng, thời gian khởi động, khả năng scale-out | Quyết định số replica tối thiểu và dự phòng |

Đo ở tải đại diện cho production, gồm cả thời điểm cao điểm. Một phép đo CPU thấp khi ứng dụng đang chờ database không chứng minh container còn đủ capacity; tương tự, RAM trung bình thấp có thể che khuất đỉnh bộ nhớ khi nhiều request xử lý đồng thời.

Nên thu thập tối thiểu:

- CPU usage theo container và node, CPU throttling hoặc thời gian chờ CPU.
- Working set và mức sử dụng bộ nhớ theo container; số lần restart, OOMKilled.
- Request rate, concurrency, độ trễ p50/p95/p99, error rate và queue depth.
- Bytes vào/ra, throughput, số kết nối, retransmission, timeout và lỗi từ load balancer/NAT.
- Số replica, thời gian scale-out, thời gian khởi động và tỷ lệ node đã được cấp phát.

## 2. Ước lượng CPU

CPU được tính theo lượng thời gian xử lý thực sự cần cho mỗi đơn vị công việc. Với API, có thể ước lượng số core cần dùng bằng:

\[
\text{CPU cores cần dùng} =
\text{requests/second} \times
\text{CPU seconds/request}
\]

Đây là nhu cầu CPU trung bình tại mức lưu lượng đang xét. Nếu muốn duy trì mức sử dụng mục tiêu \(u\), capacity cấp phát cần xấp xỉ:

\[
\text{CPU cores cấp phát} =
\frac{\text{CPU cores cần dùng}}{u}
\]

Ví dụ, API xử lý 250 request/giây và profiling cho thấy mỗi request tiêu thụ 18 ms CPU:

\[
250 \times 0.018 = 4.5\ \text{CPU cores}
\]

Nếu đặt mục tiêu sử dụng CPU khoảng 65% để còn dư địa cho dao động, tổng capacity cần:

\[
4.5 / 0.65 \approx 6.93\ \text{vCPU}
\]

Có thể bắt đầu thử nghiệm với khoảng 7–8 vCPU tổng cộng, sau đó điều chỉnh theo kết quả tải thực tế và yêu cầu dự phòng. Đây là ước lượng ban đầu, không phải cam kết hiệu năng: CPU time/request thay đổi theo dữ liệu, cache hit, thuật toán, TLS, garbage collection và các lời gọi thư viện.

### Chọn số vCPU cho mỗi replica

Tổng CPU có thể chia thành nhiều replica nhỏ hoặc ít replica lớn:

- Nhiều replica nhỏ thường giúp scale-out linh hoạt và giới hạn phạm vi ảnh hưởng khi một replica lỗi. Đổi lại, tổng overhead của runtime, sidecar, kết nối và bộ nhớ có thể tăng.
- Ít replica lớn giảm số bản sao và có thể phù hợp với workload cần nhiều thread hoặc xử lý song song. Đổi lại, scale-out kém mịn và mỗi lần khởi động hoặc thay thế replica có ảnh hưởng lớn hơn.
- Workload CPU-bound như mã hóa, nén, xử lý ảnh hoặc tính toán cần profiling để chọn số core và mức song song. Tăng số thread vượt số core hữu ích có thể làm tăng context switching.
- Workload I/O-bound thường dành nhiều thời gian chờ mạng hoặc storage. Tăng CPU đơn thuần có thể không cải thiện throughput; hãy kiểm tra connection pool, giới hạn downstream và độ trễ I/O.

### Requests, limits và throttling trong Kubernetes

Trong Kubernetes:

- **resources.requests.cpu** là lượng CPU scheduler dùng để đặt Pod lên node và là cơ sở tính mức CPU tương đối khi tranh chấp.
- **resources.limits.cpu** đặt giới hạn CPU tối đa. Khi container chạm quota, tiến trình có thể bị throttling dù node còn CPU rảnh.
- Tổng requests của các Pod, cộng overhead hệ thống, phải nằm trong capacity khả dụng của node. Không lấy tổng vCPU quảng cáo của node làm capacity có thể cấp cho ứng dụng.

Đặt request quá thấp có thể khiến scheduler xếp quá nhiều Pod lên node và tạo tranh chấp. Đặt limit quá thấp có thể làm tăng throttling và độ trễ p99. Hãy đối chiếu CPU usage, throttled time và latency trước khi thay đổi request/limit. Với nền tảng container serverless, kiểm tra cách nhà cung cấp cấp CPU trong thời gian xử lý request, khi idle và trong giai đoạn khởi động.

## 3. Ước lượng memory

Memory phải đủ cho toàn bộ working set của tiến trình trong container, không chỉ riêng heap hoặc dữ liệu nghiệp vụ. Một cách lập dự toán cho mỗi replica:

\[
\begin{aligned}
\text{Memory dự kiến} ={}&
\text{baseline runtime} \\
&+ \text{memory cho request đồng thời} \\
&+ \text{cache và buffer} \\
&+ \text{native memory, thread stack và overhead}
\end{aligned}
\]

Sau đó cộng headroom dựa trên biến động quan sát được. Hãy tính cả sidecar nếu chúng chạy trong cùng Pod và bị tính vào giới hạn tài nguyên của Pod/node.

Ví dụ một API có baseline runtime 300 MiB, tối đa 20 request đồng thời với khoảng 20 MiB mỗi request, cache 250 MiB và native memory/stack/buffer 200 MiB:

\[
300 + (20 \times 20) + 250 + 200 = 1{,}150\ \text{MiB}
\]

Nếu muốn mức dự toán này không vượt khoảng 75% giới hạn container:

\[
1{,}150 / 0.75 \approx 1{,}534\ \text{MiB}
\]

Giới hạn 2 GiB là điểm bắt đầu hợp lý để kiểm thử trong ví dụ này. Cần đo lại working set ở concurrency cao nhất, khi cache được làm nóng và trong lúc triển khai/khởi động.

Các điểm cần lưu ý:

- Memory không co giãn tức thời giống CPU. Khi vượt giới hạn cgroup, container có thể bị kernel kết thúc và Kubernetes ghi nhận OOMKilled.
- **requests.memory** ảnh hưởng đến quyết định đặt Pod; **limits.memory** là ranh giới sử dụng bộ nhớ của container. Đặt request thấp hơn nhiều so với working set làm tăng nguy cơ node bị áp lực bộ nhớ.
- Với JVM, heap không phải toàn bộ memory của container. Cần chừa chỗ cho metaspace, direct buffer, thread stack, JIT và native library. Có thể cấu hình heap theo tỷ lệ RAM container, sau đó kiểm chứng bằng số liệu RSS/working set.
- Với ứng dụng cache-heavy, kiểm tra chính sách eviction và giới hạn cache. Cache tăng hit rate nhưng cũng chiếm memory; không để cache phát triển không giới hạn.
- Nếu Pod có nhiều container, cộng request và xem xét giới hạn từng container. Sidecar proxy, agent log và telemetry cũng tiêu thụ tài nguyên.

## 4. Ước lượng năng lực mạng

Năng lực mạng gồm throughput, độ trễ, số kết nối đồng thời và khả năng mở kết nối mới. Với API, có thể ước lượng băng thông dữ liệu:

\[
\text{Throughput (bytes/s)} =
\text{requests/s} \times
(\text{bytes request} + \text{bytes response})
\]

Ví dụ, mỗi request trung bình có 10 KiB dữ liệu vào và 200 KiB dữ liệu ra. Ở 250 request/giây:

\[
250 \times 210\ \text{KiB} \approx 51.3\ \text{MiB/s}
\]

Tương đương khoảng 430 Mbit/s dữ liệu ứng dụng theo chiều tổng hợp. Nếu lưu lượng có burst 1.5 lần, throughput có thể tiến gần 645 Mbit/s. Phép tính này chưa bao gồm overhead giao thức, TLS, retransmission, health check, telemetry và lưu lượng gọi dịch vụ phụ thuộc. Khi đánh giá đường truyền thực tế, hãy tách chiều ingress và egress vì giới hạn có thể khác nhau.

Kiểm tra các giới hạn mạng theo đúng loại dịch vụ:

- Băng thông tối đa theo instance, task, node, NIC hoặc loại máy nền.
- Giới hạn throughput của load balancer, NAT gateway, gateway API và kết nối liên vùng.
- Số kết nối đồng thời, connection tracking, ephemeral port và tốc độ tạo kết nối mới.
- Độ trễ giữa zone/region và chi phí truyền dữ liệu giữa các zone hoặc ra Internet.
- Kích thước payload, MTU, TLS termination, keep-alive, connection pooling và retry policy.
- Network policy, firewall và service mesh có thể giới hạn đường đi hoặc thêm overhead; quyền truy cập mạng đúng không đồng nghĩa có đủ băng thông.

Nếu ứng dụng thường xuyên gọi database hoặc API nội bộ, tính cả lưu lượng giữa các dịch vụ. Retry quá mức có thể khuếch đại tải mạng và tải downstream trong lúc sự cố. Ưu tiên keep-alive, connection pooling, timeout hữu hạn và retry có backoff/jitter.

## 5. Ghép CPU, memory và network vào một cấu hình

Không chọn capacity theo một chỉ số riêng lẻ. Replica chỉ xử lý được tải nếu cả CPU, memory và đường mạng đều đủ. Ví dụ CPU còn dư nhưng memory đạt giới hạn vẫn có thể gây OOM; memory còn trống nhưng network throughput chạm trần vẫn làm tăng timeout.

Quy trình lựa chọn:

1. Xác định tải mục tiêu, tải đỉnh, concurrency và SLO độ trễ.
2. Profile CPU time/request để ước lượng tổng core cần thiết.
3. Đo working set ở concurrency mục tiêu, cộng cache, native memory và overhead.
4. Tính ingress/egress từ kích thước payload và lưu lượng; xác minh giới hạn theo instance và toàn tuyến.
5. Chọn số replica và cấu hình mỗi replica sao cho còn headroom khi một replica hoặc node không sẵn sàng.
6. Kiểm thử tăng tải, burst, scale-out, scale-in và tình huống downstream chậm.
7. Điều chỉnh dựa trên metrics, chi phí và kết quả SLO.

### Ví dụ tổng hợp: API danh mục sản phẩm

Giả sử API có các đặc điểm đã đo trong môi trường staging:

| Thông số | Giá trị giả định |
|---|---:|
| Tải đỉnh duy trì | 250 request/giây |
| CPU time mỗi request | 18 ms |
| CPU utilization mục tiêu | 65% |
| Memory baseline | 300 MiB |
| Memory mỗi request đồng thời | 20 MiB |
| Concurrency tối đa cần kiểm thử | 20 |
| Cache | 250 MiB |
| Native memory, stack và buffer | 200 MiB |
| Payload vào + ra trung bình | 210 KiB/request |

Ước lượng ban đầu:

- CPU: \(250 \times 0.018 / 0.65 \approx 6.93\) vCPU. Với một replica 1 vCPU, mức tải tương ứng mục tiêu 65% vào khoảng \(0.65 / 0.018 \approx 36\) request/giây. Bảy replica đáp ứng gần 250 request/giây theo mô hình trung bình; chọn 8 replica ở tải đỉnh để có thêm dư địa và chịu được việc mất một replica.
- Memory: working set dự kiến là 1,150 MiB. Với headroom như phép tính trên, bắt đầu thử nghiệm giới hạn 2 GiB cho mỗi replica.
- Network: mỗi replica ở khoảng 36 request/giây tạo ra gần 60 Mbit/s dữ liệu ứng dụng theo tổng hai chiều. Với burst 1.5 lần, cần xác minh đường mạng của mỗi instance chịu được khoảng 90 Mbit/s trở lên, đồng thời kiểm tra giới hạn egress tổng, NAT và load balancer.

Một cấu hình thử nghiệm ban đầu có thể là 8 replica, mỗi replica 1 vCPU và 2 GiB RAM. Có thể đặt min replicas thấp hơn để tiết kiệm chi phí khi tải thấp, nhưng phải đo thời gian scale-out và cold start để xác định mức tối thiểu. Ví dụ dưới đây dùng Kubernetes; các con số là điểm bắt đầu để load test, không phải cấu hình mặc định cho mọi ứng dụng.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 8
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: api
          image: registry.example.com/catalog-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "1"
              memory: "2Gi"
            limits:
              cpu: "1"
              memory: "2Gi"
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: catalog-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: catalog-api
  minReplicas: 4
  maxReplicas: 16
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
~~~

HPA trong ví dụ dùng CPU làm tín hiệu scale. Nếu ứng dụng bị giới hạn bởi network, concurrency hoặc queue, CPU có thể vẫn thấp trong khi độ trễ tăng. Khi đó cần bổ sung custom/external metrics phù hợp, chẳng hạn request concurrency, queue depth hoặc throughput; đồng thời bảo đảm cluster autoscaler có thể cung cấp node khi Pod không được schedule. Kubernetes không tự cấp thêm băng thông chỉ vì HPA tạo thêm Pod.

Trong dịch vụ container được quản lý hoặc serverless container, ánh xạ cùng cách tính sang CPU/RAM tối đa cho mỗi instance, concurrency tối đa, min/max instance và giới hạn network do nhà cung cấp công bố. Với nền tảng task như Fargate hoặc container app, kiểm tra các cặp CPU/memory được phép chọn, giới hạn mỗi task/instance, thời gian khởi động và cách tính phí. Với Kubernetes tự quản lý, cộng thêm overhead của kubelet, daemonset, system component và sidecar khi tính node allocatable.

## 6. Đánh đổi vận hành và chi phí

| Quyết định | Lợi ích | Đánh đổi cần theo dõi |
|---|---|---|
| Tăng CPU mỗi replica | Xử lý được nhiều việc song song hơn khi CPU-bound | Chi phí mỗi replica cao hơn; có thể lãng phí nếu ứng dụng chờ I/O |
| Tăng số replica | Phân tán tải, cải thiện khả năng chịu lỗi và scale-out | Tăng overhead, kết nối downstream, chi phí load balancer/NAT |
| Tăng memory | Giảm nguy cơ OOM, chứa được working set/cache lớn hơn | Tăng chi phí; request cao có thể làm giảm mật độ Pod trên node |
| Tăng concurrency | Tận dụng tài nguyên khi request chờ I/O | Tăng memory, connection và áp lực lên database |
| Dùng autoscaling | Theo tải và giảm capacity khi tải thấp | Có độ trễ scale, cần min capacity và node capacity dự phòng |
| Dùng instance/network tier lớn hơn | Có thể tăng throughput và giới hạn kết nối | Có thể trả phí cao hơn ngay cả khi chưa dùng hết |

Theo dõi chi phí theo đơn vị công việc, ví dụ chi phí trên 1.000 request thành công hoặc trên một giờ xử lý batch. Nếu tăng CPU làm latency giảm nhưng số request thành công không đổi do database đã nghẽn, thay đổi đó không tạo ra hiệu quả. Tối ưu connection pool, query, cache hoặc phân bố workload có thể đem lại kết quả tốt hơn tăng kích thước container.

## 7. Kiểm chứng sau triển khai

Thực hiện trong môi trường staging hoặc một đợt canary có giới hạn tải:

1. Ghi lại cấu hình CPU/memory request và limit, số replica, node allocatable, giới hạn network của instance và các giới hạn dịch vụ phụ thuộc.
2. Chạy tải tăng dần đến mức trung bình, tải đỉnh duy trì và burst. Giữ mỗi mức đủ lâu để quan sát autoscaling, cache và garbage collection.
3. Theo dõi CPU usage cùng CPU throttling; kiểm tra Pod có pending do thiếu CPU hoặc node có tranh chấp tài nguyên không.
4. Theo dõi working set, RSS/heap nếu phù hợp, memory peak, restart và sự kiện OOMKilled.
5. Theo dõi ingress/egress, throughput theo chiều, kết nối đồng thời, lỗi DNS/TLS, timeout, retransmission và giới hạn NAT/load balancer.
6. Đối chiếu p95/p99, error rate và queue depth với SLO. Xác định tài nguyên nào chạm ngưỡng trước khi tăng capacity.
7. Thử mất một replica hoặc node, scale-out/scale-in và triển khai phiên bản mới. Xác minh các replica còn lại vẫn đáp ứng tải mục tiêu.
8. Lưu lại kết quả, cập nhật request/limit, min/max replica và cảnh báo. Lặp lại khi thay đổi phiên bản ứng dụng, payload hoặc traffic pattern.

Các lệnh kiểm tra cơ bản trên Kubernetes:

~~~bash
# Xem mức sử dụng CPU và memory của node, Pod
kubectl top nodes
kubectl top pods -n production

# Kiểm tra trạng thái scale và số replica
kubectl get deployment,hpa,pods -n production
kubectl describe hpa catalog-api -n production

# Kiểm tra Pod bị giới hạn tài nguyên hoặc bị OOM
kubectl describe pod <pod-name> -n production
kubectl get events -n production --sort-by=.lastTimestamp

# Kiểm tra capacity còn có thể cấp trên node
kubectl describe nodes
~~~

Lệnh kubectl top cần Metrics Server và chủ yếu cho biết mức sử dụng hiện tại; nó không thay thế metrics lịch sử, CPU throttling, p95/p99 hay network telemetry. Dùng hệ thống giám sát của nền tảng hoặc Prometheus/OpenTelemetry để xem xu hướng và tương quan giữa tài nguyên với SLO. Đối với network throughput, cần lấy số liệu từ container/host, CNI, load balancer và cloud network metrics; không suy ra băng thông chỉ từ CPU hoặc số lượng Pod.

Không chạy công cụ tạo tải hoặc iperf3 trên production nếu chưa có cửa sổ kiểm thử và giới hạn lưu lượng được phê duyệt. Một bài test mạng cần đo đúng đường đi thực tế và không làm ảnh hưởng dịch vụ dùng chung.

## 8. Checklist lựa chọn capacity

- [ ] Đã xác định request rate trung bình, p95, peak, burst, concurrency và SLO.
- [ ] Đã profile CPU time/request và tính tổng vCPU theo utilization mục tiêu.
- [ ] Đã chọn số replica dựa trên tải mỗi replica, khả năng scale và tình huống mất một replica/node.
- [ ] Đã tính memory baseline, request đồng thời, cache, native memory, sidecar và headroom.
- [ ] Đã xác minh request/limit và node allocatable; không bỏ qua CPU throttling hoặc nguy cơ OOM.
- [ ] Đã tính ingress/egress từ payload và kiểm tra throughput, latency, connection, NAT, load balancer cùng giới hạn downstream.
- [ ] Đã cấu hình autoscaling với min/max hợp lý và xác minh node capacity có thể mở rộng theo.
- [ ] Đã load test tải duy trì, burst, scale-out, scale-in và tình huống lỗi.
- [ ] Đã đối chiếu metrics với p95/p99, error rate, availability và chi phí trên đơn vị công việc.
- [ ] Đã lưu baseline, ngưỡng cảnh báo và thời điểm cần đánh giá lại capacity.

Capacity tốt là cấu hình đã được kiểm chứng ở tải đại diện, còn đủ dư địa khi có biến động và có thể giải thích bằng số liệu. Khi ứng dụng hoặc traffic thay đổi, hãy đo lại CPU time, working set và network throughput để cập nhật cấu hình thay vì giữ nguyên kích thước container theo thói quen.

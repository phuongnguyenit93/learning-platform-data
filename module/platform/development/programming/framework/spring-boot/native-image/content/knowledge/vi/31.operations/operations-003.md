# Giới hạn bộ nhớ và quan sát hành vi khi tải tăng

## 1. Mục tiêu vận hành

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng **Spring AOT** rồi biên dịch thành **GraalVM Native Image** để cải thiện thời gian khởi động, footprint và khả năng triển khai. Sau khi đưa executable vào container, nhóm vận hành cần biết service phản ứng thế nào khi request rate, concurrency và kích thước dữ liệu tăng.

Bài này tập trung vào quyết định vận hành: đặt memory request/limit, xác định khoảng dự phòng, quan sát mức tiêu thụ theo tải, nhận biết dấu hiệu saturation và giảm áp lực trước khi container bị OOM kill. Các khái niệm heap, RSS, PSS và cgroup được dùng như tín hiệu trong dashboard và runbook.

Một service có thể chạy ổn định ở mức tải thấp nhưng tăng bộ nhớ nhanh khi số request đồng thời tăng. Nguyên nhân có thể là request đang xử lý giữ object, response buffer, connection, thread stack hoặc dữ liệu tạm; cũng có thể do queue không giới hạn, cache tăng theo dữ liệu hoặc memory leak. Nếu chỉ quan sát một con số memory hiện tại, người vận hành khó phân biệt tải cao bình thường với xu hướng mất kiểm soát.

Sau bài học, người học có thể:

1. Chọn memory request, limit và runtime heap budget phù hợp cho native container.
2. Xây dựng dashboard ghép memory với RPS, concurrency, queue, latency và error rate.
3. Quan sát cgroup usage, process RSS và các metric ứng dụng theo thời gian.
4. Phân biệt memory tăng theo tải, cache warm-up, queue backlog và memory leak.
5. Xác định ngưỡng cảnh báo theo headroom và tốc độ tăng, thay vì chỉ dùng một phần trăm cố định.
6. Giới hạn concurrency, queue và connection pool để kiểm soát memory pressure.
7. Cấu hình readiness, liveness và startup probes phù hợp khi service quá tải.
8. Điều tra OOMKilled, restart loop và memory pressure trong Docker/Kubernetes.
9. Thực hiện load ramp, soak test và capacity review trước khi tăng traffic.
10. Viết runbook phản ứng và điều kiện rollback cho native deployment.

> **Nguyên tắc vận hành:** bộ nhớ phải được quan sát cùng tải và độ trễ. Khi memory tăng, hãy xác định service đang giữ thêm công việc, dữ liệu hay tài nguyên nào; giảm lượng công việc đồng thời trước khi chỉ tăng container limit.

## 2. Đọc đường cong memory khi tải tăng

Khi tăng tải từng bước, memory của service thường đi qua một số trạng thái. Hình dạng đường cong giúp đặt giả thuyết ban đầu:

| Dạng quan sát | Diễn giải có thể | Việc cần kiểm tra |
| --- | --- | --- |
| Tăng lúc startup rồi ổn định | Runtime, context, cache và connection pool được khởi tạo. | So sánh idle sau readiness và sau warm-up. |
| Tăng theo RPS rồi đạt plateau | Buffer/cache/pool đạt mức ổn định hoặc concurrency giữ ở mức giới hạn. | Kiểm tra queue, pool size và cgroup headroom. |
| Tăng theo số request đang xử lý | Mỗi request giữ dữ liệu trong thời gian xử lý; concurrency càng cao, memory càng lớn. | In-flight requests, payload size, downstream latency và timeout. |
| Tăng theo từng bậc sau mỗi đợt tải | Cache hoặc pool mở rộng theo nhu cầu rồi giữ lại tài nguyên. | Cache size, eviction, pool max và thời điểm GC. |
| Tăng liên tục dù RPS/concurrency ổn định | Có thể có leak, queue tích lũy, cache không giới hạn hoặc native allocation chưa được giải phóng. | Heap after GC, queue depth, RSS, thread count và cgroup stat. |
| Memory tăng khi latency downstream tăng | Request bị giữ lâu hơn, làm tăng in-flight work và buffer. | DB pool wait, HTTP connection pool, retry, timeout và queue. |

Một plateau không tự động có nghĩa memory an toàn. Nếu plateau nằm sát container limit, một burst nhỏ hoặc GC peak cũng có thể làm container bị kill. Ngược lại, memory tăng khi tải tăng không tự động là leak; service có thể đang giữ thêm request hợp lệ.

### 2.1. Dùng concurrency để giải thích memory

Một mô hình gần đúng cho request memory:

~~~text
In-flight requests = arrival rate x average time in service
Request memory ~= in-flight requests x average retained bytes per request
~~~

Ví dụ, nếu downstream chậm gấp đôi, thời gian một request nằm trong service tăng. Với cùng RPS, số request đang chờ/đang xử lý có thể tăng gần gấp đôi. Mỗi request giữ DTO, buffer, tracing context và response data; memory có thể tăng dù request rate không đổi.

Mô hình này chỉ để lập giả thuyết, không phải công thức dự đoán chính xác. Request có kích thước và đường xử lý khác nhau; concurrency, queueing và garbage collection cũng ảnh hưởng kết quả.

### 2.2. Phân biệt cache warm-up với leak

Cache thường tăng nhanh khi service gặp key/dataset mới rồi đạt giới hạn hoặc eviction policy. Leak thường biểu hiện bằng xu hướng giữ lại object/tài nguyên sau khi tải đã trở về mức bình thường.

Để phân biệt:

1. Ghi baseline sau startup và warm-up.
2. Chạy một đợt tải có thời lượng cố định.
3. Giảm tải về idle và quan sát memory qua nhiều chu kỳ GC.
4. Kiểm tra cache size, queue depth, active connections và thread count.
5. Lặp lại cùng workload để xem baseline sau mỗi vòng có tăng dần không.

Không kết luận leak chỉ từ RSS không giảm ngay sau khi tải kết thúc. Allocator/runtime có thể giữ vùng memory đã cấp phát để tái sử dụng. Cần kết hợp heap/object diagnostics và các counter theo resource.

## 3. Đặt memory budget cho container

### 3.1. Memory limit là giới hạn của toàn container

Trong Docker hoặc Kubernetes trên Linux, memory limit được thực thi bằng cgroup. Kernel có thể chấm dứt process khi memory pressure vượt khả năng reclaim dưới hard limit. Container có thể bị OOM kill dù Java heap chưa đạt Xmx, vì limit còn tính các vùng khác và các process trong cùng cgroup. [Docker mô tả hard/soft limits và OOM behavior trong Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/); [Kubernetes mô tả memory limit được thực thi bằng cgroup và OOM kill](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).

Với native executable, đặt heap max thấp hơn container limit để dành chỗ cho:

- Native Image runtime và GC structures.
- Thread stacks và số thread tăng theo tải.
- Direct/network buffers.
- JNI hoặc native libraries.
- File mappings, TLS/crypto và client libraries.
- Logging, metrics/tracing exporter và process phụ.
- Peak khi GC, cache warm-up hoặc traffic burst.

Không dùng một tỷ lệ heap/container cố định cho mọi service. Hãy lấy peak thực tế từ workload đại diện, sau đó đặt heap max và container limit với headroom đã được kiểm chứng.

### 3.2. Phân biệt request và limit trong Kubernetes

- **Memory request** được scheduler dùng để quyết định pod có phù hợp với node hay không; HPA cũng dùng request làm cơ sở tính utilization cho resource metric.
- **Memory limit** là hard limit được runtime/kernel thực thi.
- Request không phải hard cap.
- Limit không phải mục tiêu mà service nên thường xuyên chạm tới.

QoS class được xác định từ cấu hình tài nguyên của toàn bộ Pod. Pod chỉ thuộc lớp Guaranteed khi mọi container đều khai báo CPU và memory requests/limits, đồng thời từng cặp request/limit bằng nhau. Việc một container có memory request bằng limit chưa đủ để kết luận toàn Pod là Guaranteed. Xem QoS và eviction behavior trong bối cảnh cấu hình toàn Pod và cluster.

Ví dụ minh họa, cần thay số theo số đo của service:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "384Mi"
  limits:
    cpu: "1"
    memory: "512Mi"
~~~

Các giá trị 384Mi/512Mi chỉ là ví dụ cấu hình, không phải sizing khuyến nghị cho mọi Spring Boot Native Image. Xác định request từ nhu cầu ổn định và scheduling; xác định limit từ peak đã đo cộng khoảng dự phòng phù hợp.

### 3.3. Chọn runtime heap max

Native executable có thể nhận heap options như Xms và Xmx theo GraalVM version/runtime. Ví dụ:

~~~bash
/app/orders-service -Xms64m -Xmx256m
~~~

Nếu container limit là 512 MiB, ví dụ heap max 256 MiB còn chỗ cho native/off-heap và các vùng khác. Nhưng con số này chỉ là điểm bắt đầu; nếu workload có nhiều direct buffers, thread hoặc JNI, phần còn lại có thể không đủ.

Khi thay Xmx:

1. Chạy workload baseline và ghi cgroup peak.
2. Thay một option tại một thời điểm.
3. Theo dõi heap, RSS, cgroup usage, GC và latency.
4. Chạy peak/soak test.
5. Xác nhận không có OOM và còn headroom khi traffic tăng.

Tăng heap có thể giảm GC pressure nhưng làm tổng memory có thể tăng. Giảm heap quá mạnh có thể làm GC thường xuyên, latency tăng hoặc allocation thất bại. Cần đánh giá đồng thời throughput, latency và memory.

### 3.4. Tránh cấp phát sát hard limit

Không thiết kế service để cgroup memory.current thường xuyên nằm sát memory.max. Chừa khoảng trống cho burst, GC, cache expansion, rolling deployment và sai số đo. Khoảng dự phòng cần dựa trên peak-to-peak variance và yêu cầu availability của hệ thống.

Một cách tính đơn giản:

~~~text
Headroom bytes = cgroup memory limit - observed cgroup peak
Headroom percent = headroom bytes / cgroup memory limit x 100
~~~

Theo dõi cả headroom tuyệt đối và phần trăm. Với container nhỏ, một phần trăm tương đối có thể tương ứng số MiB rất ít.

## 4. Bộ tín hiệu cần quan sát cùng nhau

Dashboard vận hành cần ghép các lớp telemetry. Không dùng riêng heap hoặc riêng container memory để ra quyết định.

| Nhóm | Tín hiệu nên theo dõi | Câu hỏi vận hành |
| --- | --- | --- |
| Container | memory current, limit, peak, working set, OOM events | Còn bao nhiêu headroom? Có bị reclaim/OOM không? |
| Process | RSS, peak RSS, thread count, file descriptors | Process nào đang giữ memory và tài nguyên hệ điều hành? |
| Runtime | heap used/max, buffer pool, GC count/time nếu có | Object allocation/GC có tăng theo tải không? |
| HTTP | RPS, in-flight requests, p50/p95/p99, 4xx/5xx | Tải tăng có làm request chậm và giữ lâu hơn không? |
| Executor/queue | active threads, queue depth, rejected tasks | Công việc có tích lũy nhanh hơn tốc độ xử lý không? |
| Database | active/idle connections, pending acquire, query latency | Request đang chờ DB và giữ memory bao lâu? |
| HTTP client | active connections, pending acquire, retry, timeout | Downstream có làm buffer và in-flight work tăng không? |
| Cache | size, hit/miss, eviction, load time | Memory tăng do cache hay do retention bất thường? |
| Deployment | replica count, restarts, OOMKilled, rollout age | Tăng tải có gây restart hoặc phân phối không đều? |

### 4.1. Spring Boot Actuator và Micrometer

Spring Boot Actuator cung cấp meter qua Micrometer. Tùy dependency và runtime, các nhóm thường có:

- jvm.*: memory/buffer pools, GC, thread và class loading.
- process.*: process CPU, memory và uptime khi binder/platform hỗ trợ.
- system.*: CPU và thông tin hệ thống.
- http.server.requests: request count và duration.
- jdbc.connections.* và hikaricp.*: connection pool.
- executor.* hoặc các meter tương ứng cho task executor/scheduler được instrument.
- application.started.time và application.ready.time: startup/ready time.

Tên meter cụ thể phụ thuộc Spring Boot, Micrometer, server và client đang dùng. Hãy xem danh sách meter thực tế trong môi trường chạy. [Spring Boot Metrics reference](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) mô tả các meter JVM, system, startup, executor và datasource.

Với Native Image, không giả định mọi jvm.* meter có cùng phạm vi như HotSpot JVM. Giữ cgroup/process telemetry làm nguồn đo bộ nhớ container và process; dùng Actuator để hiểu hoạt động của ứng dụng và runtime khi meter có sẵn.

### 4.2. Expose metrics an toàn

Ví dụ cấu hình cho môi trường nội bộ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
~~~

Cần có registry/exporter tương ứng nếu muốn Prometheus scrape. Không dùng endpoint /actuator/metrics như hệ thống lưu trữ/scrape production; endpoint này chủ yếu để xem metric hiện có và chẩn đoán. Dùng Prometheus, OpenTelemetry hoặc monitoring backend phù hợp để thu time series. Bảo vệ endpoint quản trị bằng network policy, authentication và exposure policy của tổ chức.

### 4.3. Thu cgroup metrics

Trên cgroup v2, theo dõi các counter chính:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.events
~~~

Nếu process nằm trong sub-cgroup, xác định đúng path từ /proc/self/cgroup và mount information. memory.events cho biết counter như high, max, oom và oom_kill; lấy delta giữa các khoảng thời gian để biết sự kiện có phát sinh trong đợt tải hay không.

Trên Kubernetes, container metrics có thể được thu qua kubelet/cAdvisor hoặc hệ thống observability của cluster. Không nhầm kubectl top/working set với memory.current hay RSS; ghi rõ metric source trong dashboard.

## 5. Thiết kế dashboard và cảnh báo

### 5.1. Dashboard theo thời gian

Một dashboard tối thiểu nên có các biểu đồ dùng chung time axis:

1. Container memory current, peak và limit.
2. Process RSS/peak RSS.
3. Heap used/max và GC activity nếu runtime expose.
4. RPS và in-flight requests.
5. p95/p99 latency và error rate.
6. Executor active threads, queue depth và rejected count.
7. DB/HTTP connection pool active, pending và timeout.
8. Replica count, restarts và OOM events.

Khi memory tăng, người vận hành có thể nhìn cùng thời điểm để xác định tải, latency downstream, queue hoặc restart đã thay đổi trước hay sau.

### 5.2. Cảnh báo theo headroom và tốc độ tăng

Ngưỡng cần hiệu chỉnh bằng dữ liệu thật. Ví dụ ban đầu để thử nghiệm:

| Mức | Điều kiện minh họa | Phản ứng |
| --- | --- | --- |
| Observe | Usage tăng cùng RPS nhưng còn headroom và đã plateau | Theo dõi, so sánh với baseline theo giờ/ngày. |
| Warning | Trên khoảng 75% limit kéo dài hoặc headroom giảm nhanh | Kiểm tra concurrency, queue, latency và trend. |
| Critical | Trên khoảng 85–90% limit, memory.events tăng hoặc thời gian tới limit ngắn | Giảm tải, scale theo capacity đã xác nhận, chuẩn bị rollback. |
| Incident | OOM kill, restart loop, request failure diện rộng hoặc mất readiness | Kích hoạt incident runbook và bảo vệ phần còn lại của hệ thống. |

Các tỷ lệ trên là ví dụ, không phải ngưỡng chung cho production. Với service có peak tự nhiên cao, warning có thể thấp hơn; với service memory rất ổn định, ngưỡng có thể được thiết lập theo headroom tuyệt đối và tốc độ tăng.

Tính thời gian ước lượng tới limit nếu memory đang tăng đều:

~~~text
Time to limit ~= remaining memory headroom / positive memory growth rate
~~~

Đây chỉ là phép ước lượng ngắn hạn. Memory growth thường phi tuyến khi cache, GC hoặc queue thay đổi; dùng nó làm tín hiệu cảnh báo bổ sung, không phải dự báo chắc chắn.

### 5.3. Tránh alert chỉ dựa trên một mẫu

Một spike ngắn có thể do GC, cache fill hoặc scrape timing. Kết hợp:
- Ngưỡng duy trì trong một khoảng thời gian.
- Tốc độ tăng theo cửa sổ ngắn.
- Headroom còn lại.
- OOM/max events.
- Latency/error rate và queue growth.

Cảnh báo nên phân biệt “memory cao nhưng ổn định” với “memory đang tăng nhanh và service suy giảm”.

## 6. Tăng tải có kiểm soát

### 6.1. Chuẩn bị trước load ramp

Trước khi tăng tải:

- Dùng đúng native executable và container image dự kiến triển khai.
- Cố định memory request/limit, CPU limit, swap policy và replica count.
- Dùng dataset, profile và downstream service gần production.
- Bật telemetry cgroup/process/application.
- Xác định readiness và liveness behavior.
- Ghi baseline ở idle và warm-up.
- Xác định stop condition: OOM event, headroom dưới mức an toàn, latency/error vượt SLO hoặc queue không giảm.

Không chạy load test trên môi trường dùng chung mà không giới hạn concurrency và tổng thời lượng.

### 6.2. Ramp theo từng bậc

Ví dụ kế hoạch tải:

| Giai đoạn | Mức tải | Thời gian | Mục đích |
| --- | --- | --- | --- |
| Baseline | 10% tải dự kiến | 5 phút | Xác định idle/warm memory. |
| Step 1 | 25% | 5–10 phút | Xem memory và latency bắt đầu thay đổi. |
| Step 2 | 50% | 10 phút | Quan sát queue, pool và GC. |
| Step 3 | 75% | 10 phút | Xác định vùng bắt đầu saturation. |
| Step 4 | 100% | 15–30 phút | Xác nhận tải mục tiêu. |
| Burst | 125% trong thời gian ngắn | 1–3 phút | Kiểm tra khả năng hấp thụ burst và recovery. |
| Recovery | 10% hoặc idle | 10 phút | Xem queue/cache/resource có trở về trạng thái ổn định không. |

Các mức và thời lượng chỉ là ví dụ. Điều chỉnh theo SLO, traffic pattern và mức rủi ro. Tăng từng bậc giúp xác định điểm memory hoặc latency bắt đầu tăng phi tuyến.

### 6.3. Đo concurrency và queue, không chỉ RPS

Một service có thể nhận cùng RPS nhưng memory khác nhau khi:
- Payload lớn hơn.
- Downstream chậm hơn.
- Request timeout dài hơn.
- Retry làm tăng số lần gọi downstream.
- Queue cho phép nhiều request chờ.
- Connection pool bị nghẽn.

Ghi in-flight requests, queue depth, active threads, connection acquire wait và downstream latency. Khi những chỉ số này tăng cùng memory, tìm nơi công việc đang bị giữ lại.

### 6.4. Chạy soak test

Giữ tải ổn định đủ lâu để quan sát:
- Cache growth và eviction.
- Thread/connection leak.
- Queue không trở về zero sau khi giảm tải.
- Memory baseline sau mỗi chu kỳ tăng dần.
- GC frequency và pause.
- Cgroup memory peak và OOM events.

Một bài test ngắn chỉ chứng minh service chịu được một khoảng tải ngắn; nó không chứng minh memory ổn định trong nhiều giờ.

## 7. Điều tiết tải để bảo vệ memory

Khi memory tăng cùng concurrency hoặc queue, giảm lượng công việc đang được giữ trong process thường hiệu quả hơn việc tăng limit ngay lập tức.

### 7.1. Giới hạn concurrency

Đặt giới hạn phù hợp cho:
- Số request đang xử lý đồng thời.
- Worker threads và task executor.
- Số connection DB và HTTP client.
- Số tác vụ batch song song.
- Số message đang xử lý/in-flight.

Giới hạn phải phối hợp với throughput downstream. Ví dụ, tăng web concurrency trong khi DB pool vẫn nhỏ có thể chỉ làm nhiều request chờ connection và giữ object lâu hơn.

### 7.2. Dùng bounded queue

Queue không giới hạn có thể tích lũy request nhanh hơn tốc độ xử lý. Dùng bounded queue và xác định hành vi khi queue đầy:
- Reject task sớm.
- Trả HTTP 429 hoặc 503 phù hợp.
- Áp dụng Retry-After nếu client có thể tuân thủ.
- Đưa công việc vào durable queue bên ngoài nếu nghiệp vụ cho phép.
- Ghi metric rejected/queue-full để quan sát.

Không dùng queue lớn để che giấu downstream bottleneck. Queue lớn thường đổi lỗi tức thời thành latency dài và memory pressure.

### 7.3. Timeout, retry và bulkhead

- Đặt connect/read/response timeout theo SLO.
- Retry có giới hạn, exponential backoff và jitter.
- Không retry vô hạn khi downstream đang lỗi.
- Tách pool cho dependency có mức độ quan trọng khác nhau.
- Dùng bulkhead để một downstream chậm không giữ toàn bộ worker.
- Tránh giữ request body hoặc response buffer lâu hơn cần thiết.

Retry storm có thể làm tăng in-flight requests, connection usage và memory ngay khi service đang thiếu tài nguyên.

### 7.4. Giới hạn payload và streaming

Payload lớn có thể làm tăng memory theo số request đồng thời. Cân nhắc:
- Giới hạn request body size.
- Validate Content-Length và xử lý chunked body đúng cách.
- Stream file/large response thay vì buffer toàn bộ nếu API/framework hỗ trợ.
- Giới hạn upload concurrency.
- Không giữ bản sao payload không cần thiết trong nhiều layer.
- Dùng pagination cho kết quả lớn.

## 8. Readiness, liveness và startup probes khi memory pressure

Ba probe có vai trò khác nhau:

- **Startup probe:** cho phép ứng dụng hoàn thành initialization trước khi kubelet bắt đầu liveness/readiness checks.
- **Readiness probe:** quyết định pod có nhận traffic qua Service hay không; có thể chuyển pod sang not-ready trong lúc overload hoặc recovery.
- **Liveness probe:** xác định process có bị kẹt/không thể tiến triển và cần restart hay không.

Không cấu hình liveness probe thất bại chỉ vì memory utilization cao hoặc latency tạm thời tăng. Nếu mọi pod đều bị restart khi tải cao, các pod còn lại nhận thêm traffic và có thể tạo cascading failure. Kubernetes cảnh báo liveness probe cấu hình sai có thể gây restart dưới tải và làm hệ thống kém ổn định. [Kubernetes probe guidance](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/).

Ví dụ probe:

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 30

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
~~~

Đây là cấu hình minh họa; chọn timeout, period và failure threshold theo thời gian startup và khả năng phục hồi. Health group cần được expose/cấu hình đúng cho Spring Boot version. Readiness có thể loại pod khỏi traffic khi pod quá tải tạm thời, nhưng phải có cơ chế phục hồi để pod quay lại Ready. Không để readiness check phụ thuộc vào một downstream không thiết yếu nếu điều đó sẽ loại toàn bộ replica khỏi Service.

## 9. Autoscaling và memory limits trong Kubernetes

### 9.1. Memory utilization có thể là tín hiệu trễ

HPA có thể scale theo resource metrics như CPU hoặc memory utilization; utilization được tính tương đối với resource request. Tuy nhiên, memory thường không giảm ngay khi traffic giảm vì cache hoặc allocator có thể giữ vùng đã cấp phát. Do đó, scale theo memory đơn lẻ có thể:
- Scale out khi cache warm-up chứ không phải service thiếu capacity.
- Không scale kịp khi request backlog tăng nhanh.
- Giữ số replica cao sau khi tải giảm.
- Bỏ qua một container nóng nếu chỉ nhìn tổng pod usage.

Kubernetes HPA cũng hỗ trợ container resource metrics và custom/external metrics tùy phiên bản/adapter. Hãy chọn tín hiệu gần nguyên nhân overload như CPU, RPS per pod, in-flight requests hoặc queue depth, đồng thời dùng memory làm safety guard. [Kubernetes HPA documentation](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/).

### 9.2. Không dùng autoscaling thay cho backpressure

Scale out có thể giảm tải trên mỗi replica, nhưng không sửa được:
- Queue vô hạn.
- Retry storm.
- Connection pool bị cấu hình sai.
- Cache không giới hạn.
- Một downstream đã hết capacity.
- Memory leak tăng theo thời gian trên từng replica.

Kết hợp autoscaling với concurrency cap, queue bound và timeout. Đặt max replicas theo khả năng của database, broker và downstream services.

### 9.3. Ví dụ Deployment resources và native heap

~~~yaml
containers:
  - name: orders
    image: registry.example.com/orders:native
    command: ["/app/orders-service"]
    args: ["-Xmx256m"]
    resources:
      requests:
        cpu: "500m"
        memory: "384Mi"
      limits:
        cpu: "1"
        memory: "512Mi"
~~~

Đây là ví dụ cú pháp. Trước khi áp dụng, xác nhận native executable nhận runtime option Xmx theo GraalVM version đang dùng và thay các số minh họa bằng kết quả load test. Nếu chart/entrypoint có wrapper script, kiểm tra cách script truyền arguments để chúng đến native process.

## 10. Runbook khi memory tăng nhanh

### 10.1. Xác nhận mức độ ảnh hưởng

Kiểm tra ngay:
- Cgroup current/limit/peak và event counters.
- Container restart count, OOMKilled, exit code và pod events.
- Số replica Ready/NotReady.
- RPS, in-flight requests, p95/p99 latency và error rate.
- Queue depth, rejected tasks và connection pool wait.
- Downstream latency, timeout và retry rate.

Không chỉ nhìn dashboard tổng hợp; xác định pod/container nào đang tăng nhanh và có phải tất cả replicas cùng gặp vấn đề hay không.

### 10.2. Phân loại nguyên nhân

| Quan sát | Giả thuyết đầu tiên | Hành động kiểm tra |
| --- | --- | --- |
| Memory tăng cùng in-flight requests | Concurrency quá cao hoặc downstream chậm | Xem request duration, DB/HTTP pool wait và timeout. |
| Queue tăng liên tục | Consumer/worker không theo kịp producer | Giới hạn producer, bounded queue, kiểm tra consumer throughput. |
| Heap tăng cùng cache size | Cache mở rộng theo key/data | Kiểm tra max size, TTL, eviction và key cardinality. |
| Heap ổn định nhưng RSS tăng | Native/direct buffer, thread hoặc JNI | Xem process maps, thread count và library metrics. |
| Cgroup tăng nhưng RSS app ổn định | Page cache, kernel, socket hoặc process khác | Xem cgroup memory.stat và process list. |
| Một replica tăng bất thường | Traffic skew, hot key hoặc leak cục bộ | So sánh per-pod request rate, route, tenant và age. |
| Memory tăng sau mỗi rollout | Cache warm-up hoặc thay đổi dependency/config | So sánh startup timeline và build/version. |

### 10.3. Hành động giảm áp lực

Theo thứ tự ưu tiên tùy tình huống:

1. Giảm hoặc giới hạn traffic mới nếu hệ thống có rate limiter/gateway.
2. Giảm concurrency và batch parallelism đến mức đã xác nhận an toàn.
3. Bật bounded queue/reject behavior nếu đang có backlog.
4. Tạm dừng workload không thiết yếu hoặc batch có thể trì hoãn.
5. Scale out nếu downstream và cluster còn capacity.
6. Tăng memory limit chỉ khi telemetry chứng minh đây là nhu cầu hợp lệ và node có đủ tài nguyên.
7. Rollback release nếu memory regression xuất hiện sau deploy.
8. Thu log, cgroup events và diagnostic artifacts trước khi restart nếu tình trạng cho phép.

Không disable OOM killer để che giấu vấn đề. Không tăng limit vượt node capacity hoặc database capacity. Không restart toàn bộ replica đồng thời nếu có thể thực hiện rollout/replace tuần tự.

### 10.4. Sau khi service ổn định

- Lưu timeline memory/load/latency/queue và event.
- So sánh trước/sau khi giảm concurrency hoặc rollback.
- Xác định memory tăng theo request, cache, thread, pool hay native allocation.
- Tạo load test tái hiện.
- Đặt regression threshold cho peak memory và latency.
- Cập nhật memory request/limit và autoscaling policy bằng dữ liệu.
- Ghi rõ temporary mitigation và permanent fix.

## 11. Rollout và capacity review

Trước khi phát hành native executable mới:

1. So sánh RSS/cgroup peak với phiên bản đang chạy trong cùng workload.
2. Kiểm tra heap max, GC và runtime flags.
3. Chạy startup/ready, steady load, burst và soak tests.
4. Xác nhận request/limit và node allocatable capacity.
5. Kiểm tra startup/readiness/liveness probes.
6. Rollout canary với tỷ lệ traffic giới hạn.
7. Quan sát per-pod memory, latency, error và restart.
8. Chỉ tăng traffic khi các tín hiệu nằm trong ngưỡng.
9. Giữ baseline image/version để rollback.

Nếu canary có memory slope hoặc queue growth khác baseline, dừng rollout và giữ traffic ở mức hiện tại. Không đợi tới khi OOM mới kết luận release có regression.

### 11.1. Capacity per replica

Xác định tải bền vững mỗi replica bằng load test. Chọn operating point thấp hơn điểm bắt đầu saturation để còn chỗ cho burst và pod replacement. Tính replica count theo peak traffic và capacity per replica, đồng thời kiểm tra tổng connection pool không vượt khả năng database.

Nếu mỗi pod mở tối đa 30 DB connections và deployment có 20 replicas, database có thể nhận tối đa 600 connections chỉ từ service này. Autoscaling cần phối hợp với connection budget của downstream.

### 11.2. Rolling deployment và memory headroom của node

Trong rolling update, old và new pods có thể cùng tồn tại trong một khoảng thời gian. Node cần đủ allocatable memory cho surge replicas và workload hiện tại. Nếu node thiếu memory, rollout có thể Pending hoặc gây pressure cho pod khác.

Đặt maxSurge, maxUnavailable, resource requests và node capacity dựa trên kế hoạch rollout thực tế. Không chỉ tính memory cho số replica steady-state.

## 12. Bài thực hành: quan sát native service khi tải tăng

**Bối cảnh:** dịch vụ Spring Boot native chạy trong Kubernetes với memory limit 512Mi. Khi tải tăng, p99 latency và memory current cùng tăng; một số pod bị OOMKilled. Nhóm cần tìm nguyên nhân và cấu hình lại cách điều tiết tải.

### Nhiệm vụ

1. Ghi lại GraalVM/JDK, Spring Boot, native build options, image, resource request/limit và replica count.
2. Thu baseline ở startup, ready và idle cho process/cgroup/application metrics.
3. Chạy load ramp theo các bậc 10%, 25%, 50%, 75% và 100% tải dự kiến.
4. Ghi memory current/peak/limit, RSS, heap/buffer metrics, in-flight requests và p95/p99.
5. Ghi executor queue, active threads, DB/HTTP connection pool, pending acquire và retry rate.
6. Xác định điểm bắt đầu saturation và mức tải tối đa còn giữ SLO.
7. Chạy lại khi downstream latency tăng để kiểm tra memory do in-flight requests.
8. Đặt bounded queue, concurrency limit, timeout và retry policy.
9. Kiểm tra readiness/liveness behavior khi pod overload; bảo đảm liveness không tạo restart cascade.
10. Chạy burst và soak tests; quan sát memory có plateau và recovery không.
11. So sánh HPA theo CPU/custom metrics với memory guard; kiểm tra database capacity.
12. Viết runbook cảnh báo, mitigation, rollback và điều kiện tăng memory limit.

### Hồ sơ kết quả

| Bằng chứng | Nội dung cần lưu |
| --- | --- |
| Runtime | GraalVM/JDK, Spring Boot, GC và runtime options. |
| Container | Image, request/limit, cgroup version và node allocatable. |
| Baseline | Memory idle/ready, heap, RSS, cgroup và startup time. |
| Workload | Request mix, RPS, concurrency, payload, duration và downstream latency. |
| Saturation | Điểm queue/latency/error/memory bắt đầu tăng phi tuyến. |
| Controls | Concurrency, queue capacity, timeout, retry, pool sizes và rate limits. |
| Scaling | HPA metric, min/max replicas, per-pod capacity và DB connection budget. |
| Probes | Startup/readiness/liveness config và kết quả khi overload. |
| Incident | OOM events, restart reason, mitigation và rollback timeline. |
| Decision | Limit/heap budget mới, headroom và test chứng minh. |

### Tiêu chí hoàn thành

- [ ] Phân biệt memory request và hard limit.
- [ ] Có dashboard ghép memory với RPS, in-flight requests, latency và queue.
- [ ] Xác định được memory tăng do concurrency hay do resource retention.
- [ ] Đo được cgroup peak và OOM event khi load test.
- [ ] Tìm được điểm bắt đầu saturation.
- [ ] Có concurrency cap và bounded queue.
- [ ] Timeout/retry không tạo retry storm.
- [ ] Readiness và liveness có vai trò riêng.
- [ ] HPA không vượt khả năng của database/downstream.
- [ ] Có headroom cho burst và rolling deployment.
- [ ] Runbook nêu rõ mitigation, rollback và điều kiện nâng limit.

## 13. Câu hỏi tự đánh giá

1. Vì sao memory có thể tăng khi RPS không đổi nhưng downstream latency tăng?
2. Làm thế nào phân biệt cache warm-up với memory leak?
3. Memory request khác memory limit trong Kubernetes ở điểm nào?
4. Vì sao Xmx phải thấp hơn container memory limit?
5. Những metric nào cần đặt trên cùng dashboard để giải thích memory pressure?
6. Vì sao bounded queue giúp kiểm soát memory tốt hơn queue không giới hạn?
7. Khi nào nên giảm concurrency thay vì tăng memory limit?
8. Readiness probe khác liveness probe như thế nào khi service quá tải?
9. Vì sao autoscaling theo memory đơn lẻ có thể phản ứng chậm hoặc sai?
10. Cần kiểm tra gì trước khi scale out để tránh làm database quá tải?
11. Vì sao rolling deployment cần node memory headroom cho surge replicas?
12. Những bằng chứng nào cần lưu sau một sự cố OOMKilled?

## 14. Tài liệu chính thức

Các meter, resource behavior và probe semantics phụ thuộc version framework và nền tảng. Đối chiếu đúng phiên bản triển khai:

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): JVM/system/startup metrics, executor, HTTP client và datasource instrumentation.
- [Spring Boot — Actuator Metrics Endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/metrics.html): cách xem meter hiện có phục vụ chẩn đoán; không dùng endpoint này làm metrics backend production.
- [Docker Engine — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/): hard/soft memory limits, swap và OOM behavior.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): requests, limits, cgroup enforcement và OOMKilled.
- [Kubernetes — Horizontal Pod Autoscaling](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/): resource, container và custom metrics cho autoscaling.
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): cách kubelet dùng probe để restart hoặc ngừng gửi traffic.
- [GraalVM Native Image — Memory Management](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/): runtime heap/GC options và giới hạn bộ nhớ của native executable.

**Điểm cần nhớ:** khi tải tăng, memory thường tăng cùng concurrency, queue và thời gian request bị giữ trong service. Hãy quan sát các tín hiệu này cùng cgroup headroom, điều tiết công việc bằng giới hạn rõ ràng, và chỉ thay đổi memory limit sau khi có số đo chứng minh nguyên nhân và capacity của nền tảng.


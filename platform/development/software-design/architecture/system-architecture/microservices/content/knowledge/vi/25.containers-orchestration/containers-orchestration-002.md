# Yêu cầu tài nguyên, giới hạn CPU và bộ nhớ trong Container và Microservices

Một microservice có thể chạy đúng trên máy lập trình, vượt qua toàn bộ unit test và vẫn thất bại khi lên Kubernetes: Pod không được lập lịch, ứng dụng bị chậm khi tải tăng, container liên tục bị OOMKilled, hoặc autoscaler không mở rộng đúng lúc. Những vấn đề này thường bắt đầu từ việc chọn **resource requests** và **resource limits** không phù hợp với cách ứng dụng thực sự tiêu thụ CPU và bộ nhớ.

Trong Kubernetes, requests và limits giúp cụm trả lời hai nhóm câu hỏi khác nhau:

- **Requests:** workload cần được tính bao nhiêu tài nguyên khi scheduler chọn node, và được chia sẻ tài nguyên thế nào khi có cạnh tranh?
- **Limits:** một container được phép sử dụng tối đa bao nhiêu CPU hoặc bộ nhớ theo cơ chế thực thi tương ứng?

Requests/limits liên quan trực tiếp đến khả năng lập lịch, mật độ Pod, độ trễ, độ ổn định, OOM, chi phí và autoscaling. Đặt chúng quá thấp có thể khiến ứng dụng thiếu tài nguyên; đặt quá cao có thể làm node không đủ chỗ cho Pod khác dù thực tế tài nguyên đang rảnh.

Bài học tập trung vào container chạy microservices, đặc biệt là Java 21/Spring Boot trên Kubernetes, cùng các kỹ thuật đo, cấu hình và xử lý sự cố trong production.

## 1. Mô hình tổng quát: từ yêu cầu HTTP đến tài nguyên máy

Một hệ thống microservices điển hình:

~~~text
Client
  |
  v
Ingress / API Gateway
  |
  +----> Order Service (Deployment; nhiều Pod)
  |          |
  |          +----> PostgreSQL
  |          +----> Payment Service
  |          +----> Broker
  |
  +----> Catalog Service (Deployment; nhiều Pod)
                 |
                 +----> Cache / Search

Kubernetes cluster
  |
  +-- Node A: gateway Pod, order Pod, catalog Pod
  +-- Node B: order Pod, payment Pod
  +-- Node C: catalog Pod, worker Pod
~~~

Mỗi Pod có thể chứa một container ứng dụng và một hoặc nhiều container phụ như proxy/sidecar. Tài nguyên của một Pod cần tính đến **mọi container liên quan**, không chỉ process Java chính.

Có ba lớp khác nhau:

1. **Kubernetes scheduler:** dùng requests và những ràng buộc khác để quyết định Pod có thể đặt vào node nào.
2. **Kubelet + container runtime + kernel:** dùng cơ chế cgroup và các chính sách tài nguyên để thực thi giới hạn, thu thập số liệu và phản ứng khi node bị áp lực.
3. **Ứng dụng bên trong container:** JVM, thread pool, connection pool, cache và bộ xử lý request quyết định nhu cầu tài nguyên thực tế.

Kubernetes không tự biết một request đặt hàng cần bao nhiêu heap, bao nhiêu thread hoặc bao nhiêu connection. Người thiết kế cần đo và khai báo tài nguyên phù hợp, sau đó kiểm chứng dưới tải thực tế.

## 2. Requests và limits: phân biệt chính xác

Hai thuộc tính phổ biến trong một container:

~~~yaml
resources:
  requests:
    cpu: "250m"
    memory: "512Mi"
  limits:
    cpu: "1"
    memory: "1Gi"
~~~

Đối với container này:

- **CPU request = 250m:** scheduler tính nhu cầu 0,25 CPU; khi CPU bị tranh chấp, request còn ảnh hưởng đến trọng số chia sẻ CPU tùy cơ chế kernel/runtime.
- **CPU limit = 1:** giới hạn mức CPU có thể tiêu thụ theo hạn ngạch thời gian CPU, tương đương khoảng một CPU-core trung bình trong kỳ kiểm soát quota. Trong giai đoạn tăng tải, container có thể bị throttling.
- **Memory request = 512Mi:** scheduler tính nhu cầu khoảng 512 MiB khi chọn node. Đây không phải lệnh preallocate 512 MiB RAM vật lý cho ứng dụng.
- **Memory limit = 1Gi:** container chịu giới hạn bộ nhớ khoảng 1 GiB theo cơ chế quản lý bộ nhớ của kernel/cgroup. Nếu vượt giới hạn không thể được đáp ứng, process có thể bị OOM kill.

| Thuộc tính | Ảnh hưởng lập lịch | Cơ chế chính khi chạy | Khi không đủ |
| --- | --- | --- | --- |
| CPU request | Có | Trọng số chia sẻ khi tranh chấp CPU | Có thể chạy chậm dưới cạnh tranh |
| CPU limit | Thường không quyết định placement trực tiếp | CFS quota / CPU bandwidth control tùy môi trường | CPU bị throttling, thường không bị kill vì chạm CPU limit |
| Memory request | Có | Mốc tham chiếu cho áp lực bộ nhớ và chính sách eviction | Có thể bị đánh giá khi node thiếu RAM |
| Memory limit | Không thay thế memory request để sizing node | Memory cgroup constraint | Có thể bị OOMKilled nếu không thể cấp thêm bộ nhớ |

**Request không phải lời hứa tuyệt đối về latency hoặc mức CPU rảnh mọi lúc.** Nó là đầu vào lập lịch và quản lý chia sẻ tài nguyên. Nếu nhiều Pod cùng bùng nổ vượt requests trên một node, chúng vẫn có thể cạnh tranh mạnh.

**Limit không phải mục tiêu sử dụng.** CPU thường xuyên bị chặn tại limit có thể là tín hiệu cần thay đổi sizing hoặc concurrency; memory thường xuyên gần limit có thể là dấu hiệu cần giảm footprint, sửa memory leak hoặc tăng ngân sách.

## 3. Cách đọc đơn vị CPU và bộ nhớ

### 3.1. CPU: core và millicore

Kubernetes biểu diễn CPU bằng đơn vị tương đương số core:

| Giá trị | Ý nghĩa |
| --- | --- |
| 100m | 0,1 CPU |
| 250m | 0,25 CPU |
| 500m | 0,5 CPU |
| 1000m hoặc 1 | 1 CPU |
| 2000m hoặc 2 | 2 CPU |

Chữ **m** là milli, nghĩa là một phần nghìn CPU. CPU request 500m không có nghĩa kernel ghim container vào một nửa core vật lý riêng biệt; đó là cách khai báo lượng CPU dùng cho scheduling/sharing. Container có thể chạy trên nhiều core theo chính sách CPU affinity và throttling của môi trường.

Trong các node khác nhau, một “CPU core” logic không nhất thiết cho cùng hiệu năng tuyệt đối; loại CPU, xung nhịp, NUMA và tải node có thể ảnh hưởng latency.

### 3.2. Bộ nhớ: MiB, GiB và cách viết

| Giá trị | Quy mô |
| --- | --- |
| 128Mi | 128 mebibyte |
| 512Mi | 512 MiB |
| 1024Mi | 1 GiB |
| 1Gi | 1 gibibyte |
| 2Gi | 2 GiB |

Đơn vị **Mi/Gi** theo cơ số 1024: 1 GiB = 1024 MiB = 1.073.741.824 byte. Đơn vị **M/G** theo cơ số 1000, không hoàn toàn tương đương. Đặc biệt, chữ **m** thường dùng cho CPU millicore; đặt memory bằng m có thể dẫn đến giá trị rất khác ý định.

Nên chọn một quy ước dễ đọc như CPU với 100m/250m/500m/1 và memory với 256Mi/512Mi/1Gi/2Gi; kiểm tra kết quả YAML đã được áp dụng thực tế.

## 4. Scheduler dùng requests để xếp Pod lên node như thế nào?

Khi Pod được tạo, scheduler xét CPU/memory **requests** cùng node selectors, affinity, taints/tolerations, topology constraints và nhiều điều kiện khác. Một node có thể được chọn nếu lượng tài nguyên có thể cấp theo thông tin scheduler đủ cho requests của Pod.

Ví dụ minh họa:

~~~text
Node allocatable:
  CPU:       4 core
  Memory:    8 GiB

Các Pod đã được tính requests:
  CPU:       3.2 core
  Memory:    6 GiB

Pod mới yêu cầu:
  CPU:       1 core
  Memory:    1 GiB

CPU còn cho requests = 0.8 core < 1 core
=> Pod mới có thể Pending/Unschedulable trên node này
   dù biểu đồ CPU usage thực tế đang rất thấp.
~~~

Điểm quan trọng là **node allocatable** không bằng toàn bộ CPU/RAM vật lý. Một phần tài nguyên dùng cho hệ điều hành, kubelet, runtime và vùng dự phòng theo cấu hình node. Tổng requests phải so với allocatable và các điều kiện scheduling khác.

Nếu Pod Pending vì Insufficient cpu/memory, tăng limit của container không giúp scheduler đặt Pod. Cần xem requests, dung lượng node, autoscaling node hoặc phân bố workload. Nếu resources không đủ cho Pod ở bất kỳ node tương thích nào, Pod sẽ chờ.

### 4.1. Overcommit là gì?

Kubernetes thường cho phép tổng **limits** trên node lớn hơn node allocatable, vì không phải mọi container dùng tới limit đồng thời. Đây là một dạng overcommit hữu ích cho workload có tải dao động.

~~~text
Node allocatable:       8 GiB RAM
Tổng memory requests:   6 GiB
Tổng memory limits:    12 GiB
~~~

Node có thể xếp được các Pod theo requests, nhưng nếu chúng đồng thời dùng gần limits, tổng mức dùng vượt khả năng vật lý. Khi node chịu memory pressure, kubelet và kernel có thể kích hoạt reclaim/eviction/OOM. Vì thế overcommit cần dữ liệu tải, ngưỡng dự phòng và chính sách eviction, không chỉ mong rằng mọi service sẽ không bao giờ peak cùng lúc.

### 4.2. Pod có nhiều container

Pod gồm container ứng dụng và sidecar phải được tính tổng requests/limits của các container chạy đồng thời. Với init containers, Kubernetes còn tính effective resource requirements theo quy tắc giai đoạn init và những container thường; không đơn thuần cộng tất cả container theo thời gian nếu chúng không chạy cùng nhau.

Trong bài toán sizing đơn giản, nếu ứng dụng request 500Mi và sidecar request 100Mi, Pod có nhu cầu ít nhất khoảng 600Mi đối với hai container chạy đồng thời, chưa tính Pod overhead hoặc quy tắc đặc biệt áp dụng. Không được định cỡ pod chỉ theo heap của JVM.

## 5. CPU request: công bằng khi node bị tranh chấp

CPU là tài nguyên có thể chia sẻ theo thời gian. Một container cần ít CPU có thể sử dụng rất ít; khi traffic đến, nó có thể cần nhiều CPU trong vài mili giây để xử lý request rồi trở về trạng thái rảnh.

Dưới cạnh tranh CPU, requests ảnh hưởng đến trọng số CPU mà container được cấp theo cơ chế runtime/kernel:

~~~text
Node bị bão hòa CPU

Service A request 500m
Service B request 250m

Nếu hai workload cùng cạnh tranh tài nguyên,
trọng số chia sẻ CPU của A có thể cao hơn B.
Đây là ví dụ nguyên lý, không phải cam kết tỉ lệ
CPU hoặc thời gian đáp ứng tuyệt đối.
~~~

CPU request được chọn quá thấp có thể làm service chịu latency xấu khi những workload khác cùng tăng tải. CPU request quá cao làm scheduler khó xếp Pod và làm giảm mật độ sử dụng node.

Đối với HTTP service cần đáp ứng nhanh, ngoài CPU usage trung bình còn phải đo đợt tăng tải, p95/p99 latency, hàng đợi executor, CPU throttling và số instance đang cạnh tranh trên cùng node.

## 6. CPU limit và hiện tượng throttling

Trong cấu hình Kubernetes phổ biến dùng Linux cgroup, **CPU limit** được thực thi bằng hạn ngạch CPU theo chu kỳ. Khi container đã tiêu thụ hết quota của chu kỳ hiện tại, kernel có thể tạm ngừng cho nó chạy CPU cho đến chu kỳ tiếp theo. Đó là **CPU throttling**.

Giả sử một JVM cần chạy nhiều thread đồng thời:

~~~text
CPU limit: 500m (0,5 CPU trung bình)

Trong một khoảng tải tăng:
  Nhiều request cùng đến
  JVM thread pool + GC cần CPU
  Các thread dùng hết quota sớm trong chu kỳ
  => tiếp tục phải chờ quota của chu kỳ kế tiếp

Hậu quả:
  Throughput bị giới hạn
  p95/p99 latency tăng
  Timeout ở upstream có thể xuất hiện
~~~

Đụng CPU limit **thường không giết process** như memory OOM. Service vẫn có thể sống, readiness vẫn trả OK, nhưng request chậm khiến người dùng gặp timeout. Liveness probe cấu hình thiếu hợp lý có thể làm tình hình tệ hơn nếu bị chậm cùng lúc.

Các chỉ số giúp điều tra:

- CPU usage theo container/Pod và request/limit.
- Thời gian/chu kỳ bị CPU throttling từ cgroup hoặc hệ thống metrics tương ứng.
- Latency và timeout theo endpoint.
- Số lượng thread runnable, GC pause, độ sâu queue, connection wait.
- Thời điểm rollout, tăng traffic hoặc thay đổi limit.

**Không kết luận chỉ từ một metric throttled periods**: cần đối chiếu lượng thời gian bị throttle, mức sử dụng CPU, độ trễ thực tế và tải. Một số ứng dụng có burst ngắn vẫn biểu hiện throttling nhưng không ảnh hưởng đáng kể SLO.

### 6.1. Khi nào nên có CPU limit?

Tùy chính sách nền tảng, loại workload và mục tiêu cô lập tài nguyên:

- CPU limit có thể ngăn một container dùng quá nhiều CPU so với ngân sách, bảo vệ mức độ chia sẻ trên node.
- Một limit quá thấp có thể làm tăng tail latency, đặc biệt ở JVM có nhiều thread hoặc GC.
- Một số nền tảng cân nhắc bỏ CPU limit cho dịch vụ nhạy latency trong khi vẫn thiết lập CPU request, quota namespace và kiểm soát tải. Điều này cần chính sách cluster chấp thuận và theo dõi mức sử dụng.
- Với batch worker, CPU limit có thể hữu ích nếu chấp nhận hoàn tất chậm hơn để không làm ảnh hưởng dịch vụ khác.

Không có cấu hình CPU limit duy nhất đúng cho mọi microservice. Phải đo dưới tải và phối hợp với chính sách multi-tenant.

## 7. Memory request và memory limit: tính chất khác CPU

Memory là tài nguyên không thể lấy lại một cách tương đương CPU-time khi cần ngay. Khi chương trình đã cấp phát dữ liệu, runtime phải giữ dữ liệu còn sống, giải phóng hoặc chịu áp lực bộ nhớ.

**Memory request** phục vụ scheduling và các chính sách quản lý tài nguyên; **memory limit** là ngưỡng thực thi cho container. Một container request 512Mi, limit 1Gi có thể sử dụng vượt 512Mi khi node cho phép. Nhưng nếu bộ nhớ được tính theo cgroup tăng đến giới hạn và không giải phóng được, kernel có thể chọn process để kill.

Ví dụ:

~~~text
Order Service:
  Memory request = 512Mi
  Memory limit   = 1Gi

RSS/cgroup memory tăng do:
  Java heap
  Direct ByteBuffer
  Metaspace, Code Cache
  Thread stacks
  Native allocations
  Mapped files / page cache được tính
  Thành phần runtime khác

Nếu tổng bộ nhớ chịu tính cgroup vượt ngưỡng
và reclaim không đủ:
  => OOM kill có thể xảy ra.
~~~

**Memory request không phải soft limit đơn giản** và không bảo đảm một tiến trình luôn được cấp chính xác lượng RAM đó. Giới hạn bộ nhớ, node pressure, priority, QoS và cơ chế reclaim/eviction có thể cùng quyết định kết quả.

### 7.1. OOMKilled khác với Java OutOfMemoryError

Hai dấu hiệu có thể liên quan nhưng không đồng nghĩa:

**Java OutOfMemoryError:** JVM phát hiện không thể đáp ứng cấp phát bên trong một vùng hoặc điều kiện của JVM, ví dụ Java heap space hay unable to create native thread. Process có thể tiếp tục hoặc thoát tùy loại lỗi và cấu hình.

**Container OOMKilled:** kernel/cgroup kill process vì giới hạn bộ nhớ hoặc áp lực hệ thống; Kubernetes có thể báo trạng thái last terminated reason là OOMKilled. JVM đôi khi không kịp ghi heap dump hoặc stack trace vì bị kill ở mức OS.

Exit code 137 thường liên quan SIGKILL và có thể gặp khi OOM kill, nhưng **chỉ exit code 137 không đủ kết luận nguyên nhân**. Cần kết hợp reason, sự kiện Kubernetes, cgroup/node metrics và thông tin thời điểm.

### 7.2. Eviction do node pressure

Nếu node thiếu RAM, kubelet có thể evict Pod nhằm khôi phục khả năng hoạt động của node. Đây là hành vi khác với container vượt memory limit riêng của nó.

Cần phân biệt:

- **OOMKilled:** thường phản ánh process/container bị kernel kill khi giới hạn hoặc áp lực OOM.
- **Evicted:** Pod bị kubelet loại khỏi node vì áp lực tài nguyên (ví dụ memory pressure) theo chính sách.
- **Unschedulable/Pending:** Pod chưa được đặt lên node vì requests hoặc ràng buộc không được đáp ứng.
- **CrashLoopBackOff:** hệ quả khởi động lại thất bại liên tục; cần đọc nguyên nhân termination bên dưới.

Không gộp mọi sự cố này thành “thiếu RAM”. Nguyên nhân và cách khắc phục khác nhau.

## 8. QoS classes: Guaranteed, Burstable và BestEffort

Kubernetes phân loại Pod thành các lớp **Quality of Service (QoS)** dựa trên CPU và memory requests/limits:

| QoS | Điều kiện khái quát | Ý nghĩa vận hành |
| --- | --- | --- |
| Guaranteed | Mọi container liên quan đều có CPU và memory request/limit, mỗi request bằng limit tương ứng | Có ưu tiên bảo vệ tương đối cao hơn trong một số quyết định eviction do tài nguyên |
| Burstable | Có requests/limits nhất định nhưng không đáp ứng điều kiện Guaranteed | Cho phép dùng tài nguyên linh hoạt; tình trạng vượt request có thể ảnh hưởng eviction khi node pressure |
| BestEffort | Không có CPU/memory requests hoặc limits | Dễ bị ảnh hưởng khi node thiếu tài nguyên |

QoS không phải hợp đồng tuyệt đối rằng Guaranteed Pod không thể bị OOM hoặc eviction. Một Guaranteed container vẫn có thể vượt chính memory limit của mình; node còn có thể gặp những giới hạn hoặc điều kiện khác.

Việc chọn Pod nào bị evict còn phụ thuộc priority, mức sử dụng tài nguyên so với requests, áp lực hiện tại và các chính sách liên quan. Không coi QoS là một thứ tự bất biến cho mọi tình huống.

**Lưu ý cơ chế default:** trong một số điều kiện, khi khai báo limit nhưng bỏ request, Kubernetes/admission có thể mặc định request bằng limit hoặc áp chính sách LimitRange. Vì thế QoS thực tế và scheduling có thể khác suy đoán từ YAML ban đầu. Nên khai báo rõ requests/limits theo chủ đích và kiểm tra PodSpec sau admission khi cần.

## 9. Ví dụ Deployment cho Java/Spring Boot

Đây là ví dụ cấu hình minh họa cho Order Service chạy Java 21/Spring Boot. Giá trị CPU/bộ nhớ **không phải đề xuất mặc định cho production**; cần đo theo tải và môi trường thực tế.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-service
          image: registry.example.com/order-service:1.4.2
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          env:
            - name: JAVA_TOOL_OPTIONS
              value: >-
                -XX:MaxRAMPercentage=60.0
                -XX:InitialRAMPercentage=25.0
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
~~~

Các điểm cần hiểu:

1. **Ba replica** giúp chia tải và tăng khả dụng, nhưng chỉ khi mỗi replica có thể đặt lên node và các ràng buộc topology phù hợp.
2. CPU request 250m là cơ sở lập lịch và cân nhắc chia sẻ; CPU limit 1 có thể giới hạn burst CPU.
3. Memory limit 1Gi cần bao gồm **toàn bộ footprint của tiến trình JVM và bộ nhớ được tính trong cgroup**, không chỉ Java heap.
4. JAVA_TOOL_OPTIONS đặt ngưỡng heap theo tỷ lệ bộ nhớ mà JVM nhận biết. Giá trị 60% chỉ là ví dụ để chừa chỗ cho native memory và các vùng khác; cần đo trước khi chốt.
5. Startup/readiness/liveness probe chỉ hợp lệ nếu ứng dụng đã cấu hình Spring Boot Actuator health probes tương ứng.
6. Với nhiều container hoặc sidecar, phải bổ sung resources cho **từng container** và xem tổng nhu cầu của Pod.
7. Nếu một service có startup chậm, startupProbe giúp tránh liveness restart quá sớm; probe không thay thế việc sizing CPU/RAM.

Không sửa liveness thành một endpoint phụ thuộc mọi downstream service; khi một database chậm, cách đó có thể khiến nhiều Pod cùng restart, làm sự cố lan rộng.

## 10. Java heap không bằng toàn bộ bộ nhớ container

Đây là nguyên nhân phổ biến gây OOMKilled ở microservice Java.

Bộ nhớ một JVM có nhiều vùng:

| Thành phần | Ví dụ | Có nằm toàn bộ trong -Xmx? |
| --- | --- | --- |
| Java heap | Object, cache trong heap, dữ liệu request | Có |
| Metaspace | Metadata class | Không |
| Code cache | JIT compiled code | Không |
| Thread stacks | Stack của worker/thread | Không |
| Direct/off-heap buffers | NIO, Netty, một số driver/client | Không |
| Native libraries | SSL, compression, JNI, allocator | Không |
| GC/native bookkeeping | Các cấu trúc runtime | Không |
| Memory-mapped files/page cache | Một phần memory charge tùy cgroup/kernel | Không |

Giả sử memory limit là 1Gi. Nếu đặt -Xmx1g, JVM còn cần bộ nhớ ngoài heap; container có nguy cơ vượt limit. Thậm chí heap không đầy mà off-heap tăng mạnh vẫn có thể dẫn đến OOMKilled.

Một ngân sách bộ nhớ minh họa:

~~~text
Container memory limit:          1024 MiB
Java heap tối đa:                 600 MiB
Metaspace + code cache:           130 MiB
Threads + native + direct:        190 MiB
Dự phòng dao động/chi phí khác:   104 MiB
                                ----------
Tổng ngân sách minh họa:         1024 MiB
~~~

Các con số chỉ để hình dung cách cộng các thành phần, không phải một công thức chuẩn. Đường tải khác nhau có thể tạo phân bổ rất khác: WebFlux/Netty có direct buffers, MVC có nhiều thread stacks, tính toán batch có object lớn, Jackson có tạm cấp phát, JDBC pool có buffer và connection.

### 10.1. Container awareness của JVM

Các phiên bản JDK hiện đại, gồm Java 21, có khả năng nhận biết giới hạn container theo môi trường và cgroup được hỗ trợ. Tuy nhiên cần **kiểm tra runtime thực tế**, không giả định việc nâng cấp JDK sẽ tự sửa mọi cấu hình heap hoặc số worker thread.

Các lựa chọn thường dùng:

- **-Xmx / -Xms:** đặt heap tối đa/ban đầu tuyệt đối.
- **-XX:MaxRAMPercentage:** tính heap tối đa theo tỷ lệ ngân sách memory mà JVM dùng làm cơ sở.
- **-XX:InitialRAMPercentage:** điều chỉnh kích thước heap ban đầu trong chế độ dùng tỷ lệ.
- **-XX:ActiveProcessorCount:** ghi đè số CPU logic mà JVM suy ra trong những tình huống đặc biệt đã được đo và đánh giá.

Đừng đồng thời đặt nhiều lựa chọn mâu thuẫn rồi đoán cái nào được ưu tiên. Xác nhận JVM flags hiệu lực với lệnh chẩn đoán trong môi trường test hoặc production có quyền phù hợp.

Ví dụ lệnh trong container Java:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Khi cần số liệu native memory, có thể cân nhắc **Native Memory Tracking (NMT)** và jcmd ở môi trường phù hợp, nhưng NMT có chi phí và không bao phủ mọi cấp phát native của mọi thư viện. Heap dump cũng chứa dữ liệu nhạy cảm, cần kiểm soát quyền lưu và xóa.

### 10.2. Thread và connection pool tác động RAM/CPU

Tăng thread pool “để nhanh hơn” không mặc nhiên tăng throughput. Mỗi thread có stack và overhead; nhiều thread runnable làm tăng context switching và cạnh tranh CPU.

Nếu Order Service có:

~~~text
HTTP worker threads:       200
Database pool:              50
Background consumers:       32
CPU request:              250m
CPU limit:                  1
Memory limit:             1Gi
~~~

Cấu hình có thể tạo hàng trăm tác vụ tranh cùng một CPU-core và nhiều memory allocations trong khi DB pool trở thành bottleneck. Không thể kết luận an toàn chỉ từ CPU usage trung bình.

Cần phối hợp giới hạn request concurrency, thread pool, connection pool, queue length, retry và các giới hạn downstream. Scaling nhiều Pod cũng làm **tổng kết nối đến database tăng**; nếu HPA thêm replica mà không tính DB connection budget, vấn đề có thể chuyển từ CPU sang database.

## 11. Đặt request dựa trên dữ liệu sử dụng

Một cách khởi đầu là đo một service dưới tải đại diện:

- CPU usage theo thời gian: idle, bình thường, giờ cao điểm, batch job, deployment/startup.
- Memory working set, RSS/cgroup usage, heap used/committed, GC, off-heap, số thread.
- Request rate, concurrency, throughput, p50/p95/p99 latency, error/timeout rate.
- CPU throttling, restart/OOM, connection pool queue, consumer lag.
- Độ lệch theo phiên bản mới, kích thước payload, tenant và mô hình traffic.

**Không lấy CPU trung bình toàn ngày làm request mà bỏ qua độ nhạy latency.** Service có thể idle 90% thời gian nhưng cần burst ngắn để trả kết quả đúng SLO.

Một cách sizing mang tính quy trình:

1. Đặt mục tiêu SLO và tải dự kiến của **một replica**.
2. Chạy workload thử có tải, spike, trường hợp dữ liệu lớn và khoảng chạy đủ dài để quan sát GC/memory ổn định.
3. Đo các chỉ số ở container, Pod và app thay vì chỉ đọc dashboard node.
4. Chọn CPU request hỗ trợ scheduling và giảm tranh chấp tại ngưỡng tải mong muốn.
5. Chọn memory request dựa trên footprint có thể duy trì và mức an toàn trước node pressure.
6. Chọn memory limit có đủ khoảng cách tới peak thực, theo chính sách bảo vệ node và chi phí.
7. Quyết định CPU limit dựa trên chính sách cluster và ảnh hưởng throttling đã đo.
8. Kiểm tra lại khi bật HPA, tăng pod density hoặc thay đổi JVM/workload.

Giá trị request là cam kết năng lực ở mức lập lịch, nên cần tránh vừa đặt quá thấp để “nhét được nhiều Pod” vừa kỳ vọng SLO như trên node không tranh chấp.

## 12. Ví dụ sizing từ tải và ngân sách replica

Giả sử Order Service có mục tiêu:

~~~text
Traffic đỉnh dự kiến:        600 requests/giây
Số replica ban đầu:            6
Traffic trung bình/replica:  100 requests/giây
SLO ví dụ: p95 < 300 ms
~~~

Một lần load test cho thấy:

| Mức tải/replica | CPU trung bình | Memory working set | p95 latency | Kết luận |
| --- | ---: | ---: | ---: | --- |
| 40 req/s | 180m | 340Mi | 90 ms | Có dư địa |
| 80 req/s | 420m | 470Mi | 160 ms | Nằm trong SLO |
| 100 req/s | 620m | 560Mi | 250 ms | Sắp chạm ngưỡng |
| 125 req/s | 900m | 650Mi | 520 ms | Không đạt SLO |

Các số liệu này **hoàn toàn minh họa**, dùng để chỉ ra cách suy luận.

Nếu kỳ vọng 100 req/s/replica, chọn CPU request 100m chỉ vì service lúc idle dùng rất ít là thiếu căn cứ. Cần cân nhắc scheduling khi nhiều Pod cùng đạt mức tải. Memory limit 600Mi cũng quá sát footprint đo được ở 100 req/s và có thể gây OOM khi tải hoặc kích thước request dao động. Việc chọn requests/limits phải đi kèm ngưỡng HPA, số replica tối thiểu, headroom và chi phí.

Công thức ước lượng đơn giản:

~~~text
Traffic mỗi replica ≈ Traffic toàn service / Số replica hiệu dụng

Số replica cần cho throughput:
  ceil(Traffic đỉnh / Throughput ổn định mỗi replica)

Thêm dự phòng cho:
  - Pod chưa Ready
  - rollout đang thay thế Pod
  - node bị mất/eviction
  - traffic phân bố không đều
  - tải của dependency
~~~

Công thức không tự chứng minh độ trễ: throughput đo được phải nằm trong vùng đạt SLO; còn bottleneck database, network, lock hoặc broker có thể làm scale ngang không hiệu quả.

## 13. Horizontal Pod Autoscaler (HPA) dùng requests thế nào?

**HPA** thay đổi số replica dựa trên metrics. Với CPU utilization, tỷ lệ thường được tính bằng **CPU usage so với CPU request**, không phải so với CPU limit.

Ví dụ:

~~~text
CPU request / Pod: 500m
CPU usage bình quân: 300m

Utilization so với request = 300 / 500 = 60%
~~~

Nếu HPA targetAverageUtilization là 70%, trạng thái trên chưa nhất thiết kích hoạt scale up theo riêng metric CPU đó. Nếu usage lên 450m thì utilization là 90% và HPA có thể yêu cầu thêm replica, còn phải xét tolerance, stabilization, chính sách scale và các điều kiện của HPA.

Cấu hình HPA minh họa:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: order-service
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: order-service
  minReplicas: 3
  maxReplicas: 12
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
~~~

Để hoạt động cần pipeline metrics phù hợp (ví dụ metrics-server cho resource metrics), Deployment có selector/replicas đúng và CPU requests hợp lệ. Khi một số Pod/container không có requests, việc tính CPU utilization có thể bị ảnh hưởng hoặc không hợp lệ cho metric mong muốn. Nên khai báo rõ requests cho container cần đo.

### 13.1. Đặt CPU request sai làm HPA khó diễn giải

Giả sử service cùng tiêu thụ 300m:

| CPU request | HPA CPU utilization quan sát |
| --- | ---: |
| 200m | 150% |
| 500m | 60% |
| 1000m | 30% |

Đây là cùng một lượng CPU thực tế nhưng tỷ lệ utilization khác nhau. Nếu request quá thấp, HPA có thể scale nhiều hơn dự định; nếu quá cao, HPA có thể ít phản ứng hơn. Vì vậy chỉnh CPU request đồng thời thay đổi **ý nghĩa của ngưỡng autoscaling**, phải đo lại HPA sau mỗi lần thay requests.

### 13.2. HPA chưa đủ cho mọi workload

CPU thấp không có nghĩa service không nghẽn:

- Consumer chờ message broker với queue lag lớn.
- HTTP service chờ DB connection, CPU thấp nhưng latency cao.
- Tác vụ I/O-bound, nhiều request treo chờ network.
- Có giới hạn tài nguyên của downstream; thêm replica chỉ tạo thêm connection/retry.
- Memory tăng do leak; scale ngang có thể che triệu chứng nhưng không sửa leak.

Với event-driven worker, có thể scale theo queue depth, consumer lag hoặc rate bằng metrics tương ứng. Với HTTP, cân nhắc request concurrency và latency cùng các giới hạn upstream/downstream. HPA chỉ thực hiện đúng công thức đối với **tín hiệu đã chọn**, không tự suy luận nhu cầu nghiệp vụ.

## 14. Vertical scaling, VPA và node autoscaling

Có ba cấp thay đổi năng lực:

1. **Tuning container:** điều chỉnh requests/limits, JVM heap, pool và concurrency.
2. **Horizontal Pod Autoscaler:** tăng/giảm số Pod.
3. **Node/cluster autoscaler:** bổ sung hoặc thu hẹp node để có chỗ đặt Pod.

**Vertical Pod Autoscaler (VPA)** có thể đưa ra gợi ý hoặc cập nhật resource requests theo chế độ triển khai; mức độ tác động đến Pod restart/resize phụ thuộc khả năng của môi trường và phiên bản. Không nên để VPA và HPA đồng thời điều khiển cùng CPU utilization một cách thiếu thiết kế vì mỗi bên có thể làm thay đổi đầu vào của bên còn lại.

Node autoscaler giúp khi có Pod **không thể schedule** do thiếu tài nguyên, nếu cụm có node pool phù hợp, quota và khả năng mở rộng. Nó không tự giải quyết CPU throttling khi các Pod đã được xếp lên node nhưng CPU limit của từng Pod vẫn quá thấp.

Một diễn biến ví dụ:

~~~text
Traffic tăng
  -> HPA muốn 10 Pod thay vì 6
  -> Scheduler không đủ allocatable CPU/memory
  -> Pod mới Pending
  -> Node autoscaler thêm node nếu đủ điều kiện
  -> Pod mới được schedule và Ready
  -> Traffic được phân phối sang replica mới
~~~

Toàn bộ chuỗi có độ trễ. Do đó minReplicas, startup time, PodDisruptionBudget, readiness và headroom ảnh hưởng khả năng đáp ứng spike, không chỉ giá trị HPA maxReplicas.

## 15. LimitRange, ResourceQuota và chính sách namespace

Trong cluster có nhiều team, một container không giới hạn tài nguyên có thể cạnh tranh mạnh, còn một workload request quá lớn có thể làm cạn khả năng cấp tài nguyên cho namespace.

Hai cơ chế quản trị thường dùng:

**LimitRange:** đặt default, defaultRequest, min/max hoặc quan hệ giới hạn tài nguyên cho container/Pod trong namespace, tùy loại và cấu hình. Nó có thể thêm giá trị mặc định khi Pod không khai báo.

**ResourceQuota:** giới hạn tổng requests/limits, số lượng Pod/đối tượng hoặc tài nguyên khác trong namespace.

Ví dụ minh họa LimitRange:

~~~yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: service-defaults
spec:
  limits:
    - type: Container
      defaultRequest:
        cpu: "100m"
        memory: "256Mi"
      default:
        cpu: "1"
        memory: "1Gi"
      min:
        cpu: "50m"
        memory: "128Mi"
      max:
        cpu: "2"
        memory: "4Gi"
~~~

Đây là chính sách ví dụ, không phải mức mặc định phù hợp mọi namespace. Với Pod không khai báo resources, admission có thể thêm giá trị mặc định làm thay đổi scheduling và QoS; cần xem manifest thực tế đã được chấp nhận.

Ví dụ tổng quota namespace:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-budget
spec:
  hard:
    requests.cpu: "12"
    requests.memory: "24Gi"
    limits.cpu: "24"
    limits.memory: "48Gi"
    pods: "60"
~~~

Quota giúp quản trị khả năng cấp tài nguyên, nhưng không đồng nghĩa ứng dụng được cấp CPU/RAM vật lý ngay lập tức. Nếu quota đã hết, Pod mới có thể bị từ chối ở admission dù node vẫn còn chỗ.

## 16. Tài nguyên của một microservice không chỉ có CPU và RAM

CPU/memory rất quan trọng nhưng các giới hạn khác cũng có thể làm dịch vụ mất khả dụng:

- **Ephemeral storage:** file log, cache tạm, file tải xuống, container writable layer; có request/limit riêng khi cấu hình.
- **Network bandwidth và connection count:** phụ thuộc plugin, node, service và gateway, không tự được kiểm soát bởi CPU/memory requests.
- **File descriptors:** socket/connection và file đang mở.
- **Thread/executor và DB pool:** số lượng hữu hạn, có thể nghẽn khi CPU còn rảnh.
- **Broker consumer concurrency, partition và queue:** quyết định throughput xử lý bất đồng bộ.
- **GPU/extended resources:** cần cơ chế resource tương ứng nếu workload sử dụng.
- **Pod overhead, daemon/system reservations:** ảnh hưởng node allocatable và mật độ Pod.

Nếu một service bị timeout do cạn DB connection, tăng memory limit không phải cách sửa trực tiếp. Cần chẩn đoán bottleneck và chọn đúng cơ chế điều chỉnh.

## 17. Probe và lifecycle liên quan sizing

Kubernetes có các probe khác nhau:

| Probe | Câu hỏi | Ảnh hưởng |
| --- | --- | --- |
| Startup | Ứng dụng đã khởi động đủ để bắt đầu kiểm tra thường xuyên chưa? | Trì hoãn liveness/readiness trong giai đoạn startup |
| Readiness | Pod hiện có sẵn sàng nhận traffic hay không? | Pod bị loại khỏi endpoint sẵn sàng nếu fail |
| Liveness | Process có đang trong trạng thái cần được khởi động lại không? | Kubelet có thể restart container |

CPU throttling có thể làm response health chậm, GC pause kéo dài cũng có thể khiến probe timeout. Nếu đặt liveness quá nhạy, một service đang quá tải có thể bị restart liên tục và làm tải chuyển sang các Pod còn lại, khiến tình hình xấu hơn.

Các nguyên tắc:

1. Liveness không nên phụ thuộc một downstream service đang chập chờn, trừ khi sự phụ thuộc đó thực sự chứng minh process cần restart.
2. Readiness phản ánh khả năng phục vụ request và trạng thái local; cân nhắc một cách cẩn thận việc phụ thuộc DB/broker để không gây mất toàn bộ endpoints.
3. Startup probe cho phép JVM warm-up/migration có giới hạn thời gian hợp lý.
4. Khi rolling update, kết hợp readiness, maxSurge/maxUnavailable và ngân sách node để không thiếu capacity.
5. Khi Pod bị terminating, bảo đảm graceful shutdown phù hợp với request và consumer đang xử lý.

Probe phải được kiểm thử dưới tải cao, GC hoạt động và khi dependency lỗi. Một health endpoint trả 200 không chứng minh service đã đủ CPU hoặc đạt latency SLO.

## 18. Chẩn đoán Pod Pending vì requests

Triệu chứng: Deployment muốn 6 replica nhưng chỉ 4 Pod Running, 2 Pod Pending.

Lệnh kiểm tra tham khảo:

~~~bash
kubectl get pods -n shop
kubectl describe pod order-service-xxxx -n shop
kubectl get nodes
kubectl describe node worker-node-1
kubectl top nodes
~~~

Tên Pod/node/namespace là ví dụ; thay bằng giá trị thật khi vận hành.

Nếu sự kiện nói Insufficient cpu hoặc Insufficient memory:

- Đọc requests Pod mới và tổng requests đã được phân bổ theo scheduler trên node.
- So với node allocatable, không chỉ so với CPU/memory usage hiện tại.
- Xem node affinity, toleration, topology spread và các hạn chế node pool.
- Kiểm tra namespace ResourceQuota/LimitRange nếu Pod bị từ chối.
- Cân nhắc tăng node capacity, chỉnh phân bố hoặc sizing requests dựa trên phép đo.
- Không hạ requests chỉ để Pod Running mà bỏ qua nguy cơ service thiếu CPU dưới tranh chấp.

Một Pod có request quá lớn so với bất kỳ node nào trong pool cần node có kích thước thích hợp, hoặc thiết kế lại workload nếu không cần tài nguyên như vậy.

## 19. Chẩn đoán container OOMKilled

Triệu chứng: Order Service restart nhiều lần; trạng thái last termination cho thấy OOMKilled, latency tăng quanh thời điểm tải lớn.

Lệnh tham khảo:

~~~bash
kubectl get pods -n shop
kubectl describe pod order-service-xxxx -n shop
kubectl logs order-service-xxxx -n shop --previous
kubectl top pod order-service-xxxx -n shop --containers
~~~

Các lệnh top hiển thị snapshot hiện tại; **không thay thế memory history**. Sau khi container đã bị kill, snapshot có thể không còn cho thấy peak trước sự cố.

Quy trình phân tích:

1. Xác định thời gian, số lần restart, reason, exit code và memory limit.
2. Đọc biểu đồ memory working set/RSS, cgroup usage, heap used/committed, GC và off-heap theo thời gian trước sự cố.
3. Tìm tải kích hoạt: request lớn, cache tăng, batch job, thread tăng, direct buffer, JSON processing hoặc memory leak.
4. Kiểm tra -Xmx/MaxRAMPercentage và headroom cho native memory; không đặt heap bằng memory limit.
5. Xem liveness/restart policy và khối lượng công việc bị xử lý lại sau restart.
6. Tái hiện bằng load test hoặc soak test có kiểm soát trước khi tăng limit.
7. Nếu tăng memory limit là cần thiết, đánh giá lại request, node allocatable, HPA, quota và chi phí.

Nếu metric cho thấy Java heap ổn định nhưng container memory tăng liên tục, nên điều tra native memory, direct buffer, thread stacks hoặc page cache thay vì chỉ tăng -Xmx.

**Không tăng limit mãi để che memory leak.** Tăng RAM có thể kéo dài thời gian trước khi crash nhưng làm tốn tài nguyên và không xử lý nguyên nhân.

## 20. Chẩn đoán CPU throttling và tail latency

Triệu chứng: số request/giây tăng nhẹ, CPU usage không vượt rõ rệt một core nhưng p99 latency tăng mạnh; dashboard throttle cho thấy container bị giới hạn CPU thường xuyên.

Quy trình:

1. Xem CPU request, CPU limit, usage và throttled time/periods theo khoảng thời gian gây sự cố.
2. So sánh latency ở cùng request rate và concurrency trước/sau thay đổi limit.
3. Kiểm tra HPA đang scale chưa, replica có Ready đủ, node có cạnh tranh CPU không.
4. Phân biệt thiếu CPU thực với chờ DB/network/lock hoặc GC pause.
5. Nếu limit là nút thắt, thử nâng/bỏ limit theo chính sách ở môi trường đo có kiểm soát.
6. Nếu application tự gây CPU cao, profile CPU và cải thiện thuật toán, serialization, cache hoặc concurrency.
7. Theo dõi sau thay đổi: latency, throughput, CPU, throttle, node saturation và chi phí.

Một service có CPU usage 400m và CPU limit 500m vẫn có thể bị throttling trong những giai đoạn burst; trung bình theo phút chưa phản ánh đầy đủ hành vi bên trong mỗi chu kỳ quota.

## 21. Rolling deployment và ngân sách tài nguyên

Khi triển khai phiên bản mới, Kubernetes có thể tạo thêm Pod trước khi xóa Pod cũ. Điều này hữu ích cho availability nhưng cần đủ tài nguyên tạm thời.

Ví dụ:

~~~text
Deployment:
  replicas = 10
  maxSurge = 2
  maxUnavailable = 0

Trong rollout có thể tạm cần:
  12 Pod chạy/đang khởi động

Nếu mỗi Pod request:
  500m CPU + 1Gi memory

Chỉ riêng phần tăng 2 Pod có thể cần thêm:
  1 core CPU request + 2Gi memory request
~~~

Nếu node không có chỗ cho surge Pod và không thể scale node, rollout có thể bị kẹt. HPA cũng có thể tăng replicas đúng lúc rollout, làm nhu cầu capacity cao hơn.

Nên kiểm tra tài nguyên cho trạng thái **steady state, deploy surge, mất một node, autoscaling spike và failover**. Sizing chỉ vừa đủ chạy hôm nay có thể không đủ cho việc triển khai an toàn vào ngày mai.

## 22. Liên hệ với độ tin cậy trong Microservices

Giới hạn tài nguyên không chỉ ảnh hưởng một container đơn lẻ. Khi Order Service bị throttle hoặc OOM:

~~~text
Order Service quá tải
      |
      v
Request timeout
      |
      v
Gateway hoặc client retry
      |
      v
Tăng request vào Order Service
      |
      v
Tăng cạnh tranh CPU / memory / DB connections
      |
      v
Lỗi lan sang Payment, Inventory hoặc database
~~~

Để ngăn khuếch đại:

- **Timeout/deadline** phù hợp giữa service.
- **Retry có giới hạn** và chỉ cho thao tác an toàn/idempotent.
- **Circuit breaker, bulkhead, rate limit, load shedding** cho dependencies.
- **Concurrency limit** ở ứng dụng và consumer.
- **Backpressure** hoặc giới hạn queue length thay vì nhận vô hạn request.
- **HPA** theo tín hiệu nhu cầu đúng, có capacity ở node.
- **Readiness** chỉ nhận traffic khi Pod có khả năng phục vụ.
- **SLO/alert** theo trải nghiệm người dùng, không chỉ trạng thái Running.

Một cấu hình resources tốt cần phối hợp với thiết kế chịu lỗi. Không thể chỉ chỉnh CPU limit rồi kỳ vọng retry storm tự biến mất.

## 23. Tối ưu chi phí và hiệu suất cụm

Giá trị requests ảnh hưởng mật độ Pod, số node cần có và mức độ lãng phí theo kế hoạch. Limits ảnh hưởng khả năng dùng burst tài nguyên và mức cô lập.

Ba kiểu sizing cần tránh:

**Overprovision:** mỗi Pod request 4 CPU, 8Gi trong khi thực tế thường dùng 100m, 400Mi. Kết quả là scheduler yêu cầu nhiều node dù tài nguyên được cấp nhưng bỏ trống phần lớn thời gian.

**Underprovision:** mỗi Pod request 50m, 128Mi dù tải đạt 700m, 700Mi. Scheduler có thể xếp quá nhiều Pod cùng node, dẫn đến tranh CPU và memory pressure.

**Limit quá sát:** memory limit bằng đúng mức dùng bình thường hoặc CPU limit thấp hơn burst cần để đạt SLO. Người dùng thấy chậm hoặc container bị kill dù hệ thống vẫn còn tài nguyên chưa dùng ở nơi khác.

Tối ưu nên nhìn **chi phí trên một request hoặc giao dịch hoàn tất đạt SLO**, không chỉ CPU utilization trung bình. Giảm requests có thể làm hóa đơn node thấp nhưng tăng timeout, retry và số giao dịch thất bại. Tăng replicas có thể cải thiện latency nhưng cũng làm tăng chi phí connection/database.

## 24. Quy tắc thực hành với Java 21/Spring Boot

### 24.1. Đặt ngân sách heap có headroom

Với memory limit 1Gi, một điểm bắt đầu để kiểm thử có thể là MaxRAMPercentage=60.0; cần xác nhận heap, native memory, GC và peak RSS thực tế. Một ứng dụng dùng nhiều Netty direct buffer hoặc thread pool lớn có thể cần tỷ lệ thấp hơn.

### 24.2. Đo GC trước khi sửa

Một ứng dụng GC nhiều có thể do heap quá nhỏ, tốc độ cấp phát cao, dữ liệu giữ lâu hoặc áp lực CPU. Tăng heap có thể giảm GC nhưng cũng tăng memory footprint và chi phí, không phải lúc nào cũng cải thiện hiệu năng.

### 24.3. Giới hạn concurrency tương ứng tài nguyên

Không cấu hình hàng nghìn HTTP threads cho container có CPU request rất thấp và memory limit nhỏ rồi kỳ vọng latency ổn định. Với ứng dụng reactive, ít thread không tự đồng nghĩa ít memory nếu có nhiều tác vụ và buffer in-flight.

### 24.4. Đo off-heap và các thư viện

Driver, gRPC, Netty, compression, TLS và JNI có thể dùng native memory đáng kể. Khi heap dump không giải thích tổng memory, cần xem container metrics và native memory thay vì kết luận “Kubernetes báo nhầm”.

### 24.5. Kiểm tra resource awareness theo runtime

Version JDK, cgroup v1/v2, container runtime và cấu hình CPU có thể ảnh hưởng cách JVM suy ra số CPU và giới hạn RAM. Đo từ chính môi trường chạy; không đo trên laptop host rồi dùng y nguyên kết quả cho Kubernetes.

### 24.6. Hiểu hành vi khi OOM

Nếu process bị OOMKilled, việc lưu heap dump vào local ephemeral storage có thể thất bại và có nguy cơ làm tăng storage pressure. Cần chính sách diagnostic data, bảo mật và dung lượng rõ. Với sự cố production, ưu tiên telemetry có sẵn, sampling/profiling phù hợp và môi trường tái hiện an toàn.

## 25. Resource requests/limits cho worker xử lý message

Microservice consumer khác API request service ở mô hình tải:

- Consumer có thể xử lý message theo batch.
- Throughput phụ thuộc số partition/queue, prefetch, concurrency và downstream.
- Một message lớn có thể tạo peak memory.
- Queue lag có thể tăng trong khi CPU thấp nếu đang chờ DB/API.
- Tăng replicas quá nhiều có thể gây tranh lock, DB connection exhaustion hoặc partition contention.

Ví dụ worker xử lý event:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "2"
    memory: "1536Mi"
~~~

Các giá trị chỉ minh họa. Điều cần đo: messages/s, thời gian xử lý p95, heap/off-heap peak mỗi message, số message in-flight, consumer lag, retry, DLQ và tổng connection. Nếu workload có thể chạy chậm hơn mà không ảnh hưởng SLO, có thể cân nhắc CPU throttling ở mức hợp lý; nếu hàng đợi cần rút nhanh, lựa chọn limit và concurrency phải tương thích.

Không tăng consumer concurrency chỉ vì broker còn message; phải xem tài nguyên và sức chịu đựng của downstream.

## 26. Khi cần thay đổi requests hoặc limits

Thay resources có thể dẫn tới thay đổi PodSpec/rollout hoặc các cơ chế resize được môi trường hỗ trợ. Đừng giả định mọi thay đổi đều áp dụng tức thì cho process đang chạy. Khi triển khai qua GitOps/Helm, xác minh cấu hình **đã được áp dụng** và Pod mới/đang chạy thực sự nhận đúng requests/limits.

Checklist thay đổi:

1. Ghi rõ triệu chứng, SLO bị ảnh hưởng và bằng chứng metrics.
2. Đề xuất giá trị mới cùng giả thuyết: tăng request để giảm tranh chấp, tăng memory limit để có headroom, hoặc sửa concurrency thay vì tăng CPU.
3. Kiểm tra ResourceQuota, LimitRange, node allocatable, HPA thresholds và số replicas.
4. Kiểm tra JVM heap/off-heap và container sidecars.
5. Chạy load test đủ đại diện và quan sát khi rollout một phần.
6. Rollout có kiểm soát, kiểm tra Pending, Ready, OOM, throttle và latency.
7. Ghi lại cấu hình trước/sau, người thay đổi và lý do.
8. Theo dõi vài chu kỳ tải, rồi cập nhật baseline/alert và ngân sách chi phí.

Với thay đổi lớn, có thể canary một phần Pod để so sánh cùng tải và cấu hình. Cần lưu ý load balancing không phân phối traffic hoàn toàn đều, vì vậy so sánh phải theo request rate/concurrency thực tế của mỗi cohort.

## 27. Bài tập tình huống: CPU throttling hay OOM?

Một ứng dụng Order Service Java 21 chạy 4 replica trên Kubernetes:

~~~yaml
resources:
  requests:
    cpu: "100m"
    memory: "256Mi"
  limits:
    cpu: "500m"
    memory: "768Mi"
~~~

Trong giờ cao điểm:

- CPU usage trung bình khoảng 440m/Pod.
- p99 latency tăng từ 250 ms lên 1.8 s.
- CPU throttled time tăng rõ.
- Memory working set tăng từ 420Mi đến 700Mi.
- Một Pod restart với reason OOMKilled.
- HPA dựa trên CPU utilization tăng replicas lên 8, nhưng hai Pod Pending vì node không đủ allocatable memory requests theo ràng buộc hiện tại.
- Database connections gần cạn sau khi số replica tăng.

**Câu hỏi:**

1. Vì sao CPU usage dưới 500m vẫn có thể có throttling và p99 tăng?
2. Memory request 256Mi có bảo vệ Pod khỏi OOMKilled tại limit 768Mi không?
3. HPA tính CPU utilization so với 100m hay 500m?
4. Vì sao HPA muốn tăng replica nhưng một số Pod không thể Running?
5. Tăng replicas có thể làm vấn đề database nặng hơn như thế nào?
6. Những metric và lệnh nào cần xem trước khi tăng CPU/memory?
7. Nếu JVM heap tối đa đã là 700Mi, có nên giữ memory limit 768Mi không?

**Hướng giải:**

- CPU limit theo quota có thể throttle các burst ngắn dù usage trung bình chưa vượt limit; cần đối chiếu throttled time và latency.
- Memory request dùng cho scheduling, không ngăn container bị OOM tại memory limit.
- HPA CPU utilization dựa trên request 100m, nên CPU 440m tương đương khoảng 440% request trong ví dụ này.
- Pod Pending vì thiếu tài nguyên có thể cấp theo scheduler, không tự giải quyết bằng tăng HPA replicas.
- Tăng Pod có thể tăng tổng DB connections; cần kiểm tra connection budget và pool.
- Xem kubectl describe, logs --previous, CPU/memory history, JVM heap/off-heap, cgroup, HPA và node allocatable.
- Heap gần bằng limit không chừa đủ headroom cho native memory; cần đo lại cấu hình và sửa ngân sách heap/limit.

Không có một chỉnh sửa duy nhất chữa mọi triệu chứng. Phải cân nhắc định cỡ Pod, số replica, DB connection, concurrency, CPU quota và nguyên nhân tăng memory.

## 28. Lỗi thiết kế thường gặp

**“Request thấp giúp tiết kiệm CPU.”** Request thấp chủ yếu làm scheduler có thể xếp thêm Pod và thay đổi trọng số chia sẻ; nó không tự giảm lượng CPU mà code cần.

**“Limit cao đồng nghĩa scheduler đã dành sẵn chừng ấy tài nguyên.”** Scheduler chủ yếu dựa vào requests khi xếp Pod, nên limit rất cao không tự tạo năng lực node tương ứng.

**“Memory request bằng 512Mi thì Pod không thể dùng hơn 512Mi.”** Nếu limit cao hơn và node có tài nguyên, container có thể dùng vượt request.

**“CPU chạm limit sẽ OOMKilled.”** CPU và memory có cơ chế thực thi khác nhau; CPU thường bị throttle, memory có thể dẫn đến OOM kill.

**“Đặt -Xmx bằng memory limit là tối ưu.”** JVM còn native memory, thread stacks, metaspace và nhiều chi phí khác.

**“Pod Running nghĩa là hệ thống đủ tài nguyên.”** Pod vẫn có thể bị CPU throttle, tăng latency, thiếu pool hoặc sắp OOM.

**“HPA dùng CPU limit làm mẫu số.”** CPU utilization target của HPA thường so với CPU request.

**“Chỉ cần thêm replica là tăng throughput vô hạn.”** Database, network, broker, lock và quota có thể trở thành bottleneck; workload đôi khi không scale tuyến tính.

**“QoS Guaranteed có nghĩa Pod không bao giờ bị kill.”** Guaranteed cải thiện một số khía cạnh phân loại/eviction; không vô hiệu memory limit hay lỗi ứng dụng.

**“Đồ thị CPU trung bình thấp nghĩa là không có vấn đề.”** Burst/throttling, latency p99 và block trên các tài nguyên khác có thể bị che trong trung bình.

**“OOMKilled thì tăng RAM ngay.”** Cần phân biệt memory leak, off-heap, cấu hình JVM, payload lớn và node pressure; tăng limit không bảo đảm giải quyết nguyên nhân.

**“Tăng resources sẽ không ảnh hưởng phần còn lại.”** Thay requests tác động scheduling, chi phí và HPA; thay limits tác động CPU throttling và khả năng dùng peak memory.

## 29. Quy trình áp dụng cho một microservice mới

Trước khi vận hành một service container hóa, làm theo thứ tự:

1. **Xác định workload:** HTTP, gRPC, batch hay event consumer; throughput và latency SLO là gì?
2. **Đo baseline:** khởi động, idle, tải bình thường, peak và stress; thu CPU, memory, GC, thread/connection và số lỗi.
3. **Đặt request ban đầu có căn cứ:** đảm bảo scheduler tính tài nguyên phù hợp với tải ổn định cần đạt.
4. **Đặt limit theo chính sách:** memory có headroom; CPU limit không làm vi phạm latency SLO trong kiểm thử.
5. **Kiểm tra JVM:** heap + native + direct + thread stacks nằm trong ngân sách container.
6. **Xem Pod đầy đủ:** sidecars, init containers, overhead, ephemeral storage và lifecycle.
7. **Cấu hình probes:** startup/readiness/liveness phù hợp hành vi Java và ngưỡng tải.
8. **Xác định autoscaling:** HPA targets, metrics, số replica, node capacity và downstream budget.
9. **Kiểm thử tình huống lỗi:** throttling, OOM, thiếu node, broker lag, GC, rollout surge và một node mất.
10. **Bật giám sát:** saturation, error rate, p95/p99, OOM/restarts, HPA, Pending, eviction, memory/CPU trends.
11. **Rollout có kiểm soát:** xác nhận cấu hình hiệu lực và không làm service khác mất tài nguyên.
12. **Rà soát định kỳ:** dữ liệu mới, thay đổi phiên bản JVM, traffic, payload và chi phí đòi hỏi sizing lại.

### Câu hỏi tự kiểm tra

- Tại sao CPU request 500m không giống CPU limit 500m?
- Khi memory limit là 1Gi, vì sao Java heap tối đa 1Gi có thể dẫn đến OOMKilled?
- Một Pod Pending vì Insufficient memory có thể xảy ra dù node memory usage hiện tại thấp không?
- Tại sao HPA có thể scale khác đi sau khi chỉ thay CPU request?
- Phân biệt container OOMKilled với kubelet eviction vì node memory pressure.
- Khi service có 200 thread, CPU limit 500m và DB pool 20, đâu là các điểm có thể gây p99 latency tăng?
- Vì sao rolling deployment cần ngân sách tài nguyên lớn hơn steady-state trong một số chính sách rollout?

---

**Điểm cốt lõi:** Trong Kubernetes, **requests quyết định cách workload được tính khi phân bổ tài nguyên và chia sẻ dưới cạnh tranh; limits tạo ranh giới thực thi**. CPU có thể bị throttling khi hết quota, còn memory vượt giới hạn có thể khiến process bị OOM kill. Đối với microservice Java, hãy định cỡ dựa trên **toàn bộ memory footprint**, tải thực, độ trễ, concurrency và autoscaling. Cấu hình đúng được chứng minh bằng khả năng đáp ứng SLO khi tải thay đổi, chứ không chỉ bằng việc Pod chuyển sang trạng thái Running.

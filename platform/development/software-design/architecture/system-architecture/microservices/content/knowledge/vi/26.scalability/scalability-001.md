# Phân biệt mở rộng theo chiều dọc và chiều ngang trong Microservices

Trong kiến trúc Microservices, một dịch vụ đang chạy ổn định ở 100 request/giây có thể bắt đầu tăng độ trễ khi lưu lượng tăng lên 500 request/giây. Khi đó, câu hỏi đầu tiên thường là: **nên cấp thêm CPU/RAM cho mỗi instance hay tạo thêm instance để chia tải?** Hai hướng giải quyết tương ứng với **mở rộng theo chiều dọc (vertical scaling)** và **mở rộng theo chiều ngang (horizontal scaling)**.

Cả hai đều có thể nâng năng lực hệ thống, nhưng cách chúng tác động đến phần mềm, hạ tầng, độ sẵn sàng, chi phí và dữ liệu rất khác nhau. Một dịch vụ HTTP không giữ trạng thái có thể dễ dàng được nhân bản; một database ghi duy nhất hoặc một worker giữ lock cục bộ thì không thể tăng số bản sao mà bỏ qua tính nhất quán.

Bài học này thuộc nhóm **Khả năng mở rộng** trong kiến trúc Microservices. Nội dung tập trung vào cách phân biệt, đo lường và lựa chọn chiến lược mở rộng, cùng các tình huống triển khai thường gặp với ứng dụng Java/Spring Boot và Kubernetes.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích scaling up/down và scaling out/in bằng những ví dụ cụ thể.
- So sánh giới hạn tài nguyên, độ sẵn sàng, thông lượng, độ trễ, chi phí và độ phức tạp của hai hướng.
- Nhận ra vì sao nhân bản instance không mặc nhiên giúp hệ thống xử lý nhanh hơn.
- Phân tích các nút nghẽn CPU, memory, connection pool, database, hàng đợi và giới hạn bên thứ ba.
- Hiểu các điều kiện để một Microservice hỗ trợ horizontal scaling: stateless, routing, session, idempotency, state ownership.
- Tính gần đúng số replica theo throughput đo được và dự phòng công suất.
- Biết vai trò của Kubernetes HPA, Cluster Autoscaler/node autoscaling, VPA và các metric theo nhu cầu.
- Lập kế hoạch load test, xác minh khả năng scale và xử lý scale-in một cách an toàn.

## 2. Khái niệm cơ bản

### 2.1. Mở rộng theo chiều dọc — Vertical scaling

**Vertical scaling** là tăng hoặc giảm tài nguyên dành cho **một đơn vị xử lý**: nâng CPU, RAM, giới hạn I/O, dung lượng/hiệu năng đĩa hoặc cấp VM có cấu hình mạnh hơn.

~~~text
TRƯỚC (scale up)
+-----------------------+
| Order Service: Pod A  |
| 1 vCPU, 2 GiB RAM     |
+-----------------------+

SAU
+-----------------------+
| Order Service: Pod A  |
| 4 vCPU, 8 GiB RAM     |
+-----------------------+
~~~

Tên thường gặp:

- **Scale up:** tăng tài nguyên cho một instance.
- **Scale down:** giảm tài nguyên cho một instance.

Trong môi trường máy ảo, scale up có thể cần thay đổi instance type và khởi động lại. Với Kubernetes, thay đổi resource requests/limits thường dẫn đến việc thay Pod bằng Pod có cấu hình mới; tính năng resize tại chỗ phụ thuộc phiên bản Kubernetes, cấu hình cluster và khả năng hỗ trợ của runtime. Không mặc định mọi thay đổi CPU/RAM đều diễn ra không gián đoạn.

**Ví dụ:** PostgreSQL thiếu RAM để giữ working set trong cache. Nâng RAM của database server có thể giảm đọc đĩa và cải thiện độ trễ truy vấn khi nguyên nhân thật sự là memory pressure.

### 2.2. Mở rộng theo chiều ngang — Horizontal scaling

**Horizontal scaling** là tăng hoặc giảm **số đơn vị xử lý** phục vụ cùng một workload: thêm Pod/VM/service instance, worker, consumer hoặc một phân vùng xử lý độc lập.

~~~text
TRƯỚC (scale out)
             +---------------------+
Request ---> | Order Service: A    |
             | 1 vCPU, 2 GiB RAM   |
             +---------------------+

SAU
             +-----------------------+
Request ---> | Load Balancer         |
             +-----------+-----------+
                         |
             +-----------+------------+
             |           |            |
             v           v            v
        +--------+  +--------+   +--------+
        | Pod A  |  | Pod B  |   | Pod C  |
        | 1 CPU  |  | 1 CPU  |   | 1 CPU  |
        +--------+  +--------+   +--------+
~~~

Tên thường gặp:

- **Scale out:** thêm instance.
- **Scale in:** bớt instance.

Một service có 3 Pod không đương nhiên đạt gấp 3 lần throughput của 1 Pod. Năng lực thực tế còn phụ thuộc load balancing, database, cache, network, contention, cold start và giới hạn các dependency.

### 2.3. Scaling khác tối ưu hóa

Scaling tăng tài nguyên hoặc đơn vị xử lý. **Optimization** cải thiện hiệu quả sử dụng tài nguyên hiện có: sửa truy vấn, giảm số lời gọi mạng, thêm cache đúng chỗ, batch I/O, loại bỏ lock không cần thiết, tối ưu thuật toán hoặc giảm payload. Một service thiếu index khiến mỗi request scan hàng triệu row có thể vẫn chậm dù thêm rất nhiều Pod.

Thực tế thường kết hợp cả hai: đo nút nghẽn → tối ưu những lãng phí rõ ràng → xác định ngưỡng tải của mỗi instance → thiết kế cách mở rộng an toàn.

## 3. So sánh nhanh hai hình thức

| Tiêu chí | Vertical scaling | Horizontal scaling |
|---|---|---|
| Thao tác chính | Tăng CPU/RAM/I/O cho instance | Tăng số instance/partition |
| Đơn vị được thay đổi | Kích thước một máy/Pod | Số máy/Pod/worker |
| Độ phức tạp ứng dụng | Thường thấp hơn nếu workload không đổi | Cần xử lý routing, state, concurrency |
| Giới hạn | Trần cấu hình host/VM, phần mềm và chi phí | Trần của dependency, dữ liệu và điều phối |
| Sẵn sàng | Một instance lớn vẫn có thể là điểm lỗi đơn | Nhiều instance có thể tăng khả năng chịu lỗi nếu đặt độc lập |
| Ảnh hưởng triển khai | Có thể cần restart/migrate | Có thể tăng bản sao không gián đoạn nếu readiness và shutdown đúng |
| Scale khi tải biến động | Thường chậm hơn, tùy hạ tầng | Hợp với autoscaling dựa trên metric |
| Đặc tính chi phí | Máy lớn đôi khi đắt hơn theo bậc | Có chi phí instance, load balancer, network |
| Dữ liệu có trạng thái | Có thể đơn giản hơn trong ngắn hạn | Phải thiết kế consistency, partition, replication |
| Phù hợp điển hình | Single-node database, memory-bound workload | Stateless API, worker độc lập, consumer theo partition |

Không nên áp dụng một dòng của bảng như quy luật tuyệt đối. Ví dụ tăng CPU limit không giúp nếu ứng dụng chỉ dùng được một core vì lock hoặc thuật toán tuần tự. Ngược lại, nhân bản read replica database có thể hữu ích dù database là thành phần stateful, miễn kiến trúc đọc/ghi được thiết kế phù hợp.

## 4. Phân biệt Scale Up với Scale Out qua các ví dụ

### 4.1. API xử lý request độc lập

Order API là một dịch vụ Java/Spring Boot, đọc dữ liệu qua database và trả về JSON. Giả sử CPU xử lý JSON/logic cao, request độc lập và instance không giữ session cục bộ.

- Vertical: đổi từ 1 vCPU/2 GiB lên 4 vCPU/8 GiB cho mỗi Pod.
- Horizontal: giữ 1 vCPU/2 GiB nhưng tăng từ 2 Pod lên 8 Pod.
- Hybrid: tăng nhẹ cấu hình mỗi Pod để tránh GC/CPU throttling rồi tăng số Pod theo tải.

Điểm cần đo: throughput đạt SLO, p95/p99 latency, CPU, bộ nhớ, số connection và hiệu suất load balancing.

### 4.2. Database ghi

Một PostgreSQL primary xử lý ghi có shared state. Thêm Pod PostgreSQL giống hệt nhau không làm các instance đó tự động trở thành một database ghi thống nhất.

- Vertical: tăng CPU, RAM, IOPS cho primary nếu áp lực nằm ở tài nguyên máy.
- Horizontal cho đọc: thêm read replica và định tuyến read-only query phù hợp, lưu ý replication lag.
- Horizontal cho ghi: partition/shard hoặc kiến trúc distributed database, cần xử lý phân phối khóa, transaction và consistency.
- Optimization: thêm index, sửa truy vấn, batch writes, partition table, cải thiện connection pooling.

Database thường là nút thắt quyết định hiệu quả scale của tầng API. Nếu mọi Pod mới đều tăng số connection đến primary, bottleneck có thể tệ hơn.

### 4.3. Worker xử lý message

Một consumer xử lý email giả lập hoặc task tạo thumbnail từ queue:

- Vertical: thêm CPU/RAM cho worker nếu tác vụ nặng hoặc chạy song song trong một process.
- Horizontal: thêm worker nếu mỗi message độc lập và queue hỗ trợ phân phối.
- Với Kafka, số consumer có thể xử lý song song hiệu quả trong một consumer group bị giới hạn bởi **số partition được gán** cho group. Có 20 consumer mà chỉ 6 partition thì không có 20 consumer cùng được gán partition để xử lý trên topic đó.
- Với task có side effect, thêm worker cần idempotency, retry, dead-letter và giới hạn đồng thời.

### 4.4. Dịch vụ có session cục bộ

Một hệ thống WebSocket hoặc ứng dụng lưu giỏ hàng trong RAM của process hiện tại có thể chạy với 1 instance nhưng không an toàn khi thêm nhiều replica.

Để scale out phải xem cách định tuyến kết nối, session affinity, shared session store, sự kiện khi một instance bị xóa và khả năng kết nối lại. **Sticky session** giảm một số triệu chứng nhưng vẫn cần giải pháp chuyển trạng thái và phục hồi khi Pod chết.

## 5. Vì sao Vertical Scaling không tăng vô hạn?

### 5.1. Giới hạn vật lý và loại máy

Máy/VM có cấu hình lớn nhất, dung lượng RAM, băng thông và IOPS giới hạn. Trong cloud, mức cấu hình cao hơn thường tăng chi phí theo nấc, đôi khi cần downtime hoặc migration.

### 5.2. Giới hạn phần mềm

Một chương trình bị tuần tự hóa bởi một lock chính không dùng hết 64 core. Một connection pool chỉ cho phép 10 kết nối đang hoạt động có thể khiến CPU còn trống nhưng request vẫn chờ. Một service phụ thuộc vào API bên thứ ba giới hạn 100 request/giây cũng không vượt được hạn mức đó chỉ bằng CPU.

**Định luật Amdahl** mô tả giới hạn tăng tốc khi chỉ một phần công việc được song song hóa. Nếu tỷ lệ tuần tự là s, tốc độ tăng tối đa với N đơn vị song song lý tưởng được xấp xỉ:

~~~text
Speedup(N) = 1 / [s + (1-s)/N]
~~~

Ví dụ 20% thời gian không thể song song hóa, khi N rất lớn, tốc độ tăng tối đa theo mô hình này tiến về 5 lần. Đây là mô hình trực giác, không thay thế benchmark; với request độc lập, cách chia tải và nguồn gốc phần tuần tự khác so với tăng core bên trong một request.

### 5.3. Rủi ro điểm lỗi đơn

Nếu chỉ chạy một instance lớn, nó vẫn có thể dừng do lỗi process, OS, host hoặc vùng hạ tầng. Vertical scaling tự nó không đảm bảo high availability. Có thể dùng nhiều instance lớn, multi-AZ và cơ chế failover nếu hệ thống cần khả năng chịu lỗi.

## 6. Vì sao Horizontal Scaling cũng có trần?

Nhân bản dịch vụ chỉ hữu ích khi phần lớn công việc có thể **phân phối độc lập** và hệ thống chia sẻ còn đủ năng lực.

Các nút thắt thường gặp:

1. **Database primary:** tất cả API Pod ghi vào một primary có write capacity giới hạn.
2. **Connection pool tổng:** mỗi Pod 30 connection × 20 Pod = 600 connection; database có thể quá tải dù mỗi Pod còn rảnh.
3. **Cache hot key:** nhiều Pod cùng truy cập/ghi một key khiến cache node hoặc lock bị nghẽn.
4. **Downstream rate limit:** nhà cung cấp thanh toán giới hạn request, thêm Pod chỉ khiến nhiều 429 hơn.
5. **Partition count:** worker Kafka không thể mở rộng consumer group vượt quá số partition hoạt động hiệu quả.
6. **Distributed lock:** mọi request phải giữ một lock phân tán, mức song song thực tế thấp.
7. **Network và load balancer:** băng thông, connection tracking, NAT, service mesh sidecar là giới hạn khác.
8. **Queue/backlog không do thiếu worker:** lỗi poison message hoặc dependency bị ngắt không được giải quyết bằng scale out.
9. **Tài nguyên node:** HPA yêu cầu thêm Pod nhưng cluster không có CPU/RAM để schedule.
10. **Dữ liệu có trạng thái:** fan-out request có thể đọc trạng thái khác nhau giữa replica.

Do đó, phát biểu “thêm replica sẽ tuyến tính tăng công suất” chỉ đúng xấp xỉ khi một tập điều kiện đo được còn được đáp ứng.

## 7. Scale up hay scale out ảnh hưởng độ trễ ra sao?

### 7.1. Throughput và latency

- **Throughput:** số công việc hoàn thành mỗi giây, ví dụ request/giây hoặc message/giây.
- **Latency:** thời gian từ lúc nhận đến lúc trả kết quả, thường quan tâm p95/p99.
- **Concurrency:** số request đang được xử lý hoặc đang chờ đồng thời.
- **Utilization:** tỷ lệ tài nguyên đang sử dụng theo một mẫu đo cụ thể.

Ở mức tải thấp, một Pod có thể trả 20 ms. Khi tải đến sát năng lực, request bắt đầu xếp hàng và p95 tăng mạnh; không cần CPU đạt chính xác 100% mới có queueing.

Vertical scaling có thể rút ngắn phần compute của request CPU-bound hoặc tăng số request xử lý song song nhờ thêm core. Horizontal scaling có thể chia số request cho nhiều Pod và giảm queue tại mỗi Pod. Nếu độ trễ chủ yếu là chờ database hoặc downstream bị nghẽn, cả hai có thể không giúp.

### 7.2. Little's Law

Trong hệ thống ổn định, quan hệ trung bình:

~~~text
L = λ × W

L : số request/công việc trung bình trong hệ thống
λ : tốc độ hoàn thành trung bình (công việc/giây)
W : thời gian trung bình một công việc ở trong hệ thống (giây)
~~~

Nếu hệ thống hoàn tất 200 request/giây và mỗi request mất trung bình 0,1 giây từ đầu đến cuối, số request đồng thời trung bình trong hệ thống xấp xỉ 20.

Điều này **không trực tiếp cho biết phải có 20 thread hay 20 Pod**. Cần biết request dùng bao nhiêu CPU, bao nhiêu thời gian chờ, concurrency limit, mức phân phối tải và các dependency. Little's Law giúp kiểm tra tương quan giữa throughput, latency và số công việc tồn đọng.

### 7.3. Quan sát điểm bão hòa

Benchmark nên tạo đường cong throughput–latency khi tăng tải, thay vì chỉ nhìn “maximum RPS”. Giữ một SLO, chẳng hạn p95 latency dưới 200 ms và error rate dưới 0,5%. Công suất sử dụng để sizing là **throughput duy trì khi còn đạt SLO**, không phải đỉnh RPS lúc đã đầy timeout.

## 8. Tính gần đúng số replica cần thiết

Giả sử bài load test chứng minh một Pod Order Service xử lý ổn định **80 request/giây** khi vẫn đạt SLO. Dự báo peak 240 request/giây; muốn vận hành ở tối đa 75% của năng lực đo được để dự phòng.

~~~text
Replica_required
  = ceil(Peak_RPS / (Pod_sustainable_RPS × Target_load))

  = ceil(240 / (80 × 0.75))
  = ceil(4)
  = 4 Pods
~~~

Giả định này hữu ích để ước lượng ban đầu, nhưng cần xác minh:

- Năng lực đo được dựa trên cùng workload, tỷ lệ endpoint và kích thước payload chưa?
- Hệ thống có đạt SLO khi chạy **4 Pod cùng lúc** không?
- Database và downstream có chịu được 240 request/giây tổng không?
- Pod có phân bố qua node/zone để chống lỗi không?
- Trong lúc rolling deployment hoặc mất một Pod, công suất còn đủ không?
- Autoscaler có thời gian tạo Pod mới ngắn hơn thời gian tăng tải không?

Nếu cần tiếp tục đáp ứng 240 RPS khi mất một trong bốn Pod, chỉ còn 3 × 80 × 0,75 = 180 RPS theo giả định; cần tăng số Pod, điều chỉnh ngân sách tải hoặc chiến lược dự phòng. Không coi con số 4 là kết luận HA khi chưa đánh giá khả năng mất replica.

### 8.1. Capacity planning với nhiều endpoint

Một request GET /catalog nhẹ có thể mất 5 ms CPU, còn POST /checkout có thể mất 50 ms CPU và nhiều truy vấn. Tổng RPS không phản ánh chính xác nhu cầu nếu cơ cấu request thay đổi.

Nên load test theo *workload mix*: tỷ lệ endpoint, payload, tenant, cache hit/miss, thời gian gọi bên thứ ba và pattern burst. Sizing của một Pod phải dựa trên workload đại diện, và bổ sung stress test cho luồng nặng.

## 9. Stateless là điều kiện hỗ trợ Scale Out dễ hơn

**Stateless service** theo nghĩa thực dụng là một instance có thể xử lý request hợp lệ mà không cần dữ liệu phiên làm việc độc quyền nằm trong RAM của instance khác. Dữ liệu nghiệp vụ lâu dài vẫn nằm trong database/cache/object storage hoặc các hệ thống được chia sẻ hợp lệ.

Ví dụ cần tránh:

~~~java
@RestController
class CartController {
    private final Map<String, Cart> carts = new ConcurrentHashMap<>();

    @PostMapping("/cart/{userId}")
    void add(@PathVariable String userId, @RequestBody Item item) {
        carts.computeIfAbsent(userId, key -> new Cart()).add(item);
    }
}
~~~

Nếu các Pod lưu cart độc lập, request tiếp theo của cùng user đến Pod khác sẽ không thấy giỏ hàng trước đó. Map thread-safe chỉ giải quyết chia sẻ giữa thread trong một JVM, **không chia sẻ dữ liệu giữa Pod**.

Phương án phù hợp hơn là dùng repository/kho lưu trữ được thiết kế cho state cần chia sẻ; service instance xử lý request rồi đọc/ghi state qua interface đó. Cần thiết kế transaction, concurrency và thời hạn giữ giỏ hàng phù hợp.

### 9.1. Những trạng thái dễ bị quên

- Session/token không nên phụ thuộc vào một Pod cụ thể nếu cần tự do chuyển request.
- Local in-memory cache phải có cơ chế invalidation/TTL, không là nguồn sự thật duy nhất.
- Scheduler chạy trong mỗi Pod có thể kích hoạt job N lần nếu không dùng distributed lock hoặc kiến trúc scheduler/worker phù hợp.
- Upload lớn đang xử lý phải có cơ chế resumable hoặc lưu tạm bên ngoài khi Pod bị terminate.
- WebSocket/gRPC stream dài cần xử lý kết nối lại và graceful shutdown khi scale-in.
- Unique ID và idempotency key phải được thiết kế toàn hệ thống; counter trong memory từng Pod không đủ.

## 10. Load Balancer và Service Discovery khi Scale Out

Khi số instance thay đổi, client cần một cơ chế chọn instance sống và đủ điều kiện nhận request:

~~~text
Client
  |
  v
API Gateway / Load Balancer
  |
  +--> Service A, Pod 1 (READY)
  +--> Service A, Pod 2 (READY)
  +--> Service A, Pod 3 (NOT READY: không nhận traffic)
~~~

Cần phân biệt:

- **Liveness:** tiến trình còn hoạt động đủ để không cần restart?
- **Readiness:** instance đã khởi tạo xong và có thể phục vụ request?
- **Startup:** ứng dụng cần thêm thời gian khởi động ban đầu?
- **Graceful termination:** Pod ngừng nhận request mới, hoàn tất tác vụ đang chạy hoặc hủy an toàn trước khi thoát.

Nếu không dùng readiness, autoscaler có thể thêm nhiều Pod nhưng load balancer đưa traffic đến khi ứng dụng chưa load xong cấu hình, chưa warm cache hoặc chưa thiết lập kết nối database. Khi scale-in, xóa Pod ngay giữa transaction/stream có thể gây lỗi.

Việc dùng load balancer không đồng nghĩa mọi request được phân phối hoàn hảo: long-lived connection, HTTP/2 multiplexing, session affinity và hash routing có thể tạo tải lệch giữa các Pod.

## 11. Vertical scaling trong Kubernetes

Mỗi container có thể khai báo **resource requests** và **limits**:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
~~~

Đây là ví dụ triển khai, image cần thay bằng artifact thật. Ý nghĩa:

- **CPU request 500m:** scheduler dùng mức này để đặt Pod lên node và làm mẫu số cho HPA CPU utilization.
- **CPU limit 1:** container có thể bị CPU throttling khi vượt mức giới hạn được áp đặt.
- **Memory request 512Mi:** mức yêu cầu dùng cho scheduling và chính sách quản lý tài nguyên.
- **Memory limit 1Gi:** vượt giới hạn có thể khiến container bị OOM kill.

Tăng requests/limits của mỗi Pod là một cách thay đổi tài nguyên theo chiều dọc. Nhưng tăng CPU limit từ 1 lên 2 không giúp khi node không có capacity, và nâng memory chỉ để tránh OOM có thể che rò rỉ bộ nhớ nếu không điều tra nguyên nhân.

### 11.1. CPU request, CPU limit và JVM

Trong Java, giới hạn bộ nhớ container cần xét cả Java heap, metaspace, thread stacks, native/direct buffers và overhead khác. Đặt -Xmx bằng toàn bộ memory limit có thể không chừa chỗ cho phần bộ nhớ ngoài heap. Kiểm tra bản JDK và cơ chế container awareness đang sử dụng, quan sát RSS, GC, heap usage, container OOM events.

Nếu p99 tăng do GC pressure, cần biết tăng RAM có cải thiện đáng kể hay không; nếu p99 tăng do connection pool chờ lâu, tăng heap không giải quyết gốc rễ.

### 11.2. VPA — Vertical Pod Autoscaler

Vertical Pod Autoscaler có thể khuyến nghị hoặc điều chỉnh cấu hình CPU/RAM dựa trên quan sát usage tùy chế độ triển khai. Một số chế độ thay Pod để cập nhật resource; hỗ trợ thay tại chỗ tùy phiên bản và cấu hình cluster.

VPA phù hợp với workload khó xác định requests hoặc có nhu cầu tài nguyên thay đổi theo thời gian, nhưng cần cân nhắc disruptions. Nếu HPA và VPA đồng thời điều khiển dựa trên cùng CPU utilization/requests, chúng có thể gây tương tác khó dự đoán. Phải thiết kế phạm vi metric và controller rõ ràng trước khi bật cả hai.

## 12. Horizontal scaling trong Kubernetes với HPA

**Horizontal Pod Autoscaler (HPA)** điều chỉnh số replica của workload mục tiêu theo metric. Ví dụ HPA dựa trên CPU utilization:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: order-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: order-service
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Pods
          value: 2
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
~~~

Ví dụ minh họa, cần metrics pipeline và quyền cluster phù hợp. Với target 60%, CPU utilization được so với **CPU requests** của container; không có request phù hợp thì metric utilization có thể không dùng được như mong muốn.

Nếu một Pod có CPU request 500m, mức CPU tương ứng với target 60% là xấp xỉ 300m trung bình theo mẫu đo. Đây **không phải** cam kết Pod luôn dùng dưới 300m, cũng không bảo đảm SLO ở mọi workload.

HPA có thể tính số replica mong muốn gần theo quan hệ:

~~~text
DesiredReplicas
  ≈ ceil(CurrentReplicas × CurrentMetric / DesiredMetric)
~~~

Thuật toán HPA thực tế còn xử lý tolerance, metric thiếu, Pod chưa sẵn sàng, stabilization và các policy scale; không nên mô phỏng scheduler bằng một công thức duy nhất.

### 12.1. HPA scale Pod, không tự tạo node

Nếu HPA muốn 12 Pod nhưng các node chỉ có tài nguyên cho 8 Pod, một số Pod sẽ Pending. **Node/Cluster Autoscaler** (hoặc giải pháp node provisioning tương đương) cần tạo thêm node; node mới cũng cần thời gian khởi tạo. HPA, scheduler và node autoscaling là các tầng điều khiển khác nhau.

### 12.2. CPU có phải metric đúng?

Với dịch vụ CPU-bound, CPU utilization có thể phản ánh nhu cầu. Nhưng các workload sau cần metric khác:

- API chờ database I/O: CPU thấp dù p95 latency cao.
- Queue worker: cần xem backlog, tốc độ xử lý và tuổi message.
- Gateway giữ nhiều connection dài: cần metric active connections/concurrency.
- HTTP service bị rate limit downstream: CPU không phản ánh khả năng tăng throughput.

HPA có thể dùng custom/external metric qua adapter. KEDA thường được dùng để scale worker/event-driven workload theo tín hiệu hàng đợi hoặc nguồn sự kiện; ngưỡng và giới hạn vẫn cần phù hợp công suất dependency.

## 13. Autoscaling theo hàng đợi và backlog

Giả sử một worker xử lý ổn định 10 message/giây. Queue đang có 3.000 message, yêu cầu xử lý lượng backlog này trong 60 giây nếu không có thêm message mới.

Ước lượng số worker thuần lý thuyết:

~~~text
Required throughput = 3,000 / 60 = 50 msg/s
Worker capacity     = 10 msg/s
Workers             = ceil(50 / 10) = 5
~~~

Nhưng nếu có thêm 20 msg/giây liên tục trong 60 giây, hệ thống cần tổng năng lực khoảng 70 msg/giây để vừa xử lý backlog vừa giữ pace với incoming traffic: cần ít nhất 7 worker theo mô hình lý tưởng. Phải có headroom cho retry, phân phối tải và dependency latency.

Cần theo dõi:

- **Queue depth:** số message chờ xử lý.
- **Oldest message age:** message lâu nhất chờ bao lâu; đôi khi phản ánh SLO rõ hơn depth.
- **Arrival rate:** message mới/giây.
- **Service rate:** message hoàn tất/giây của mỗi worker.
- **Failure/retry/dead-letter:** có tăng do downstream lỗi không.

Nếu consumer Kafka trong một group chỉ có 4 partition, tăng 8 Pod consumer không làm 8 Pod đều có partition làm việc. Nếu downstream giới hạn 30 request/giây, scale lên 20 worker có thể làm rate limit trở nên nghiêm trọng hơn.

### 13.1. Scale-to-zero

Một số event-driven worker có thể giảm replica về 0 khi không có việc và được kích hoạt khi có event. Điều này có lợi về chi phí, nhưng có độ trễ khởi động, cần bảo đảm trigger không bị mất và cần phân biệt workload chịu được cold start với workload có latency SLO nghiêm ngặt. API đồng bộ quan trọng thường không thích hợp với scale-to-zero nếu request phải đáp ứng nhanh.

## 14. Dữ liệu và tính nhất quán khi scale out

Horizontal scaling làm tăng concurrency, do đó những giả định trước đây “chỉ có một process ghi” có thể không còn đúng.

### 14.1. Race condition

Hai instance cùng xử lý một lệnh cập nhật tồn kho:

~~~text
Stock hiện tại = 1

Pod A đọc stock = 1
Pod B đọc stock = 1
Pod A trừ còn 0
Pod B trừ còn 0

=> Cả hai lệnh có thể cùng cho rằng đặt được hàng
~~~

Chỉ thêm Pod không tạo ra tính đúng đắn. Cần dùng transaction/locking hoặc optimistic concurrency có kiểm tra version; có thể dùng atomic update có điều kiện ở database:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'SKU-01' AND quantity >= 1;
~~~

Sau lệnh này, application phải kiểm tra số row bị cập nhật để quyết định đặt hàng thành công hay hết hàng. Trường hợp có nhiều thao tác xuyên dịch vụ cần cơ chế phù hợp như saga, idempotency, outbox hoặc compensation; không thể mặc nhiên dựa vào một transaction database cục bộ.

### 14.2. Idempotency

Khi retry hoặc thay đổi Pod, cùng một request có thể được xử lý nhiều lần. Các thao tác có side effect cần idempotency key hoặc cơ chế deduplication có phạm vi dữ liệu phù hợp. Lưu trạng thái deduplication trong memory của từng Pod sẽ không bảo vệ được toàn hệ thống.

### 14.3. Cache và session

Local cache trên từng Pod có thể giúp đọc nhanh nhưng thường là bản sao; cần TTL, invalidation và phương án cập nhật. Shared cache giảm sai khác giữa Pod nhưng có thể trở thành nút thắt và tạo hot key. Session nên được mô hình hóa rõ với token phù hợp hoặc session store có HA nếu có nhu cầu lưu trạng thái server-side.

## 15. Scale Out cho database khác Scale Out cho API

API không trạng thái được nhân bản tương đối dễ vì request có thể đi đến nhiều bản sao. Database chịu trách nhiệm duy trì một tập dữ liệu nhất quán và thường có ràng buộc ghi chặt hơn.

### 15.1. Read replica

~~~text
                +------------------+
Write requests ->| Primary Database |
                +--------+---------+
                         |
               Replication
                 /       \
                v         v
          +----------+ +----------+
Read ---> | Replica1 | | Replica2 | <--- Read
          +----------+ +----------+
~~~

Read replica giúp phân phối khối lượng đọc nếu ứng dụng biết request nào chấp nhận dữ liệu trễ. Các truy vấn đòi hỏi đọc ngay sau khi ghi (*read-your-writes*) có thể cần truy cập primary hoặc một cơ chế nhất quán phù hợp.

### 15.2. Sharding

Sharding chia dữ liệu theo shard key như tenantId hoặc customerId để phân phối cả lưu trữ và ghi. Đổi lại:

- Cần chọn shard key cân bằng; hot tenant có thể làm một shard quá tải.
- Cross-shard transaction/query phức tạp hơn.
- Rebalancing dữ liệu có thể tốn tài nguyên.
- Backup, restore, migration và observability phải theo từng shard.

Không nên shard sớm chỉ vì API có nhiều Pod. Chỉ cân nhắc khi có bằng chứng cấu hình database, read replica và tối ưu truy vấn không đáp ứng được nhu cầu.

### 15.3. Connection budget

Giả sử mỗi Pod có pool tối đa 30 connection. Từ 3 Pod tăng lên 20 Pod làm tổng connection tiềm năng từ 90 lên 600. Nếu database không hỗ trợ số kết nối như vậy, hệ thống có thể tăng lỗi "too many connections". Cần đặt pool size theo tổng ngân sách, xem xét connection pooling tập trung và giám sát active/idle/waiting connections.

## 16. Độ sẵn sàng và khả năng chịu lỗi

Horizontal scaling có thể tăng high availability khi các replica đặt trên failure domain độc lập. Ba Pod trên cùng một node không bảo vệ trước việc node đó ngừng hoạt động. Tương tự, ba Pod trong cùng một availability zone không nhất thiết chịu được sự cố toàn zone.

Biện pháp thường gặp:

- Chạy tối thiểu nhiều replica cho dịch vụ quan trọng.
- Sử dụng topology spread constraints hoặc pod anti-affinity phù hợp.
- Đặt PodDisruptionBudget để giới hạn số Pod tự nguyện bị gián đoạn cùng lúc.
- Cấu hình readiness, startup, liveness đúng đặc tính ứng dụng.
- Graceful shutdown và connection draining để giảm lỗi khi scale-in.
- Kiểm tra downstream cũng có phương án HA, không chỉ tier API.

Vertical scaling kết hợp HA vẫn khả thi khi dùng nhiều VM lớn, replication/failover hoặc managed database. Vì vậy, **vertical và horizontal không đối lập tuyệt đối**; chúng giải quyết các chiều tài nguyên và cấu trúc khác nhau.

## 17. Chi phí: không chỉ số CPU/RAM được cấp

Để so sánh chi phí, cần tính *total cost per useful work*:

~~~text
Chi phí vận hành
= Compute + Memory + Storage + Network + Managed services
  + Load balancer + Observability + Operational overhead
~~~

Một VM 8 vCPU có thể rẻ hoặc đắt hơn tám VM 1 vCPU tùy giá cloud, disk, network, cam kết mua và chi phí vận hành. Horizontal scaling tạo thêm network traffic, sidecar, log streams, connection pool và tải lên dependency. Vertical scaling có thể giảm overhead của nhiều instance nhưng gặp trần loại máy và tốn tiền khi tải thấp.

### 17.1. Ví dụ tính minh họa

Giả sử hai cách đều đã chứng minh đạt cùng SLO và cùng công suất:

| Phương án | Cấu hình | Tổng CPU | Tổng RAM | Đặc điểm |
|---|---|---|---|---|
| Vertical | 2 Pod × 4 vCPU/8 GiB | 8 vCPU | 16 GiB | Ít Pod, mỗi Pod lớn |
| Horizontal | 8 Pod × 1 vCPU/2 GiB | 8 vCPU | 16 GiB | Nhiều Pod, linh hoạt chia tải |

Cùng tổng CPU/RAM không có nghĩa throughput, latency hay giá tiền bằng nhau. Pod lớn có thể đạt cache locality tốt hơn; Pod nhỏ có thể chịu overhead lớn hơn hoặc dễ rải qua node. Benchmark và bảng giá thực tế mới là bằng chứng.

### 17.2. Quy tắc chi phí

- Xác định mức sử dụng tối thiểu và peak; tránh cấp phát theo peak 24/7 nếu tải biến động mạnh.
- Chọn minReplicas để đáp ứng HA/cold start, maxReplicas để khống chế chi phí và bảo vệ downstream.
- Tính cả logging, tracing, egress và database connections khi tăng replica.
- Với burst khó dự báo, cần headroom và khả năng cấp node đủ nhanh.
- Với tải ổn định, một mức tài nguyên cố định phù hợp có thể đơn giản và rẻ hơn autoscaling phức tạp.

## 18. Khi nào ưu tiên từng chiến lược?

### 18.1. Thường ưu tiên vertical khi

- Workload khó phân phối và đã xác định đang thiếu CPU/RAM/I/O trên một instance.
- Database primary, in-memory index hoặc tác vụ cần working set lớn chạy tốt hơn trên máy mạnh.
- Tăng cấu hình không vượt trần hạ tầng và chi phí hợp lý.
- Phần mềm hiện tại khó chạy nhiều instance, cần giải pháp ngắn hạn trong khi thiết kế lại.
- Đã có HA độc lập; không tạo điểm lỗi đơn chỉ vì scale up.

### 18.2. Thường ưu tiên horizontal khi

- Request/task tương đối độc lập, dữ liệu chia sẻ được quản lý bên ngoài.
- Cần chịu tải tăng/giảm theo giờ, chiến dịch hoặc mùa vụ.
- Cần duy trì khả năng phục vụ khi một instance/node lỗi.
- Thời gian provision replica ngắn và load balancing hoạt động tốt.
- Dependency có đủ công suất hoặc cũng có chiến lược mở rộng tương ứng.

### 18.3. Kết hợp cả hai

Một thiết kế phổ biến:

~~~text
                 +----------------------+
Users ---------->| Gateway / LB         |
                 +-----------+----------+
                             |
                  Horizontal scale
                 /      |       \
                v       v        v
             API Pod  API Pod  API Pod
                 \      |       /
                  \     |      /
                   v    v     v
               +-----------------+
               | Database Primary|
               | Vertical tuning |
               +-----------------+
                          |
                      Read replicas
~~~

API scale out vì request độc lập; database primary được tune CPU/RAM/I/O, kèm read replica cho khối lượng đọc. Điều này không tự bảo đảm hệ thống vô hạn năng lực, nhưng thường phản ánh đúng đặc tính từng tầng.

## 19. Thực hành quan sát trước khi quyết định scale

Một dashboard tối thiểu cho Microservice nên có:

| Nhóm | Metric | Ý nghĩa |
|---|---|---|
| Golden signals | Rate, error, duration, saturation | Nhu cầu và trải nghiệm thực tế |
| CPU | CPU usage, throttling, request/limit | CPU có là bottleneck không? |
| Memory | Working set/RSS, GC, OOM, heap | Có memory pressure hoặc leak không? |
| Server | Active requests, threads, queue, connection pools | Request chờ ở đâu? |
| Database | QPS, latency, locks, IOPS, pool wait | Nút thắt shared persistence |
| Messaging | Backlog, age, consumer lag, retry | Cần worker hay sửa dependency? |
| Pod/Node | Pending Pods, node utilization, restarts | HPA có thực sự scale được không? |
| Business | Orders completed, payments approved | Thêm resource có cải thiện outcome không? |

### 19.1. Phân tích một tình huống

Triệu chứng: p95 của Checkout API tăng từ 100 ms lên 1.200 ms khi RPS tăng. CPU chỉ 35%; JVM heap ổn định. Pool database dùng hết 30 connection, thời gian chờ connection tăng, query trên bảng order bị lock.

Kết luận thực dụng: ưu tiên phân tích truy vấn/transaction và pool/database trước khi scale out API. Thêm Pod có thể tăng tổng connection và lock contention. Vertical scale CPU của API ít có khả năng giải quyết.

Nếu thay vào đó CPU bị throttling liên tục, database latency ổn và throughput mỗi Pod tăng khi thêm CPU, vertical scale hoặc scale out đều có thể cải thiện; cần so sánh bằng benchmark và chi phí.

## 20. Load test để kiểm chứng hướng scale

Chọn các phép đo có cùng môi trường và workload mix:

1. **Baseline:** đo một Pod với cấu hình hiện tại ở các mức tải.
2. **Vertical experiment:** giữ số Pod, tăng CPU/RAM theo từng mức.
3. **Horizontal experiment:** giữ cấu hình Pod, tăng replica theo từng mức.
4. **Hybrid experiment:** thử một số kết hợp có giá trị thực tế.
5. **Failure experiment:** xóa một Pod/node hoặc làm một dependency chậm để kiểm tra hệ thống còn đạt yêu cầu gì.
6. **Scale-in experiment:** giảm replica khi đang có request/queue để đánh giá graceful shutdown và số công việc thất lạc.

Giữ các điều kiện càng đồng nhất càng tốt: code/image digest, database size, cache warm-up, loại request, network, chính sách logging và thời gian đo. Ghi rõ mức tải tại đó SLO không còn đạt.

### 20.1. Ví dụ kế hoạch thử nghiệm

| Case | Pod | CPU mỗi Pod | Tổng CPU | Mục tiêu |
|---|---:|---:|---:|---|
| Baseline | 2 | 1 vCPU | 2 vCPU | Năng lực hiện tại |
| Vertical A | 2 | 2 vCPU | 4 vCPU | Lợi ích khi nâng core |
| Vertical B | 2 | 4 vCPU | 8 vCPU | Kiểm tra giới hạn scale up |
| Horizontal A | 4 | 1 vCPU | 4 vCPU | Hiệu quả nhân bản |
| Horizontal B | 8 | 1 vCPU | 8 vCPU | Độ tuyến tính và dependency |
| Hybrid | 4 | 2 vCPU | 8 vCPU | Tối ưu latency/chi phí |

Không điền kết quả giả vào bảng. Sau mỗi case, lưu throughput thực tế, latency p50/p95/p99, error, CPU throttling, memory, DB latency và tổng chi phí tương ứng.

### 20.2. Tránh lỗi đo

- Không so sánh case có cache lạnh với case cache nóng mà không ghi chú.
- Không dùng số RPS máy phát tải muốn gửi thay cho RPS hệ thống thực sự hoàn tất.
- Nếu máy tạo tải đã bão hòa CPU/network, kết quả đo về hệ thống có thể sai.
- Không bỏ qua timeout và response 5xx khi tính throughput thành công.
- Nên có thời gian warm-up và giai đoạn đo ổn định, đặc biệt với JIT JVM.
- Các test có side effect cần dữ liệu riêng và cleanup; không phá dữ liệu môi trường chia sẻ.

## 21. Scale-In không đơn giản là xóa Pod

Khi autoscaler giảm replica, hệ thống phải tránh làm mất công việc đang diễn ra.

Đối với HTTP API:

- Đưa Pod ra khỏi danh sách ready trước khi ngừng phục vụ.
- Cho các request đang xử lý thời gian kết thúc trong giới hạn.
- Cấu hình terminationGracePeriodSeconds theo thời lượng request, kết nối và logic shutdown.
- Đảm bảo client có retry an toàn cho thao tác idempotent hoặc có idempotency key.

Đối với worker:

- Ngừng nhận message mới.
- Hoàn thành task hoặc ghi checkpoint/offset phù hợp trước khi thoát.
- Không commit offset trước khi side effect thực sự được đảm bảo nếu điều đó làm mất message.
- Tính đến at-least-once delivery và khả năng xử lý trùng khi worker được khởi động lại.

Đối với WebSocket/stream:

- Cho client tín hiệu reconnect/drain khi có thể.
- Tránh cắt phiên dài đột ngột nếu ứng dụng có cam kết hoàn tất.

HPA thường giảm replica khi metric giảm; một metric thấp tại thời điểm đo không có nghĩa mọi tác vụ nền đã kết thúc. Cần đo active jobs, in-flight requests và backlog phù hợp.

## 22. Autoscaling có thể gây dao động

Nếu tải thay đổi nhanh, hệ thống có thể liên tục tăng và giảm replica (*flapping*):

~~~text
Load tăng -> HPA scale out -> Pod warming
Load giảm -> HPA scale in -> Pod terminating
Load lại tăng -> Pod thiếu -> latency spike -> scale out ...
~~~

Để giảm dao động:

- Chọn stabilization window và chính sách scaleDown phù hợp.
- Dùng metric phản ánh nhu cầu thật nhưng không quá nhiễu.
- Đảm bảo startup/readiness của Pod chính xác và đo thời gian cold start.
- Đặt minReplicas đủ cho tải nền và HA, maxReplicas hợp với khả năng database.
- Cân nhắc dự báo theo lịch/sự kiện nếu tải theo giờ hoặc chiến dịch có thể đoán được.
- Quan sát cùng lúc autoscaling ở Pod và node để tránh tình trạng Pod Pending kéo dài.

Autoscaling là một vòng điều khiển có độ trễ; nó không thể phản ứng tức thì với mọi spike. Cần dự phòng công suất và công cụ bảo vệ tải như backpressure, queue, rate limiting hoặc load shedding có chủ đích.

## 23. Scale và Resilience phải đi cùng nhau

Một hệ thống có thể scale out mạnh nhưng giảm reliability vì tạo nhiều retry đồng thời khi dependency lỗi. Ví dụ 50 Pod cùng retry 3 lần vào Payment Service có thể biến 1.000 request ban đầu thành nhiều nghìn lần gọi gây nghẽn thêm.

Các cơ chế cần phối hợp:

- **Timeout:** giới hạn thời gian chờ để tránh giữ tài nguyên vô hạn.
- **Bounded retry + jitter:** giảm retry storm; chỉ retry khi an toàn.
- **Circuit breaker:** ngăn tiếp tục gây áp lực lên dependency đang lỗi.
- **Bulkhead:** cô lập nhóm tài nguyên để lỗi một chức năng không làm nghẽn toàn bộ.
- **Backpressure:** cho producer biết consumer không theo kịp.
- **Rate limit:** đặt giới hạn tại entry point hoặc dependency có hạn mức.
- **Idempotency:** tránh duplicate side effect khi retry hoặc thay đổi replica.

Thêm replica nên được nhìn như tăng **khả năng xử lý có kiểm soát**, không phải giấy phép gửi lưu lượng vô hạn xuống các hệ thống phụ thuộc.

## 24. Tình huống thiết kế: tăng lưu lượng gấp năm lần

**Bài toán:** Một hệ thống đặt hàng dùng 2 Pod Order Service, mỗi Pod 1 vCPU/2 GiB, PostgreSQL primary và Redis. Khi flash sale, tải tăng gấp năm. p95 latency vượt SLO, CPU API 90%, database CPU 40%, database pool wait thấp; Redis hit rate ổn định.

Cách tiếp cận:

1. Xác nhận metric đo đúng thời điểm peak và lỗi không chủ yếu xuất phát từ downstream.
2. Benchmark một Pod để xác định throughput đạt SLO.
3. Thử tăng CPU mỗi Pod lên 2 vCPU; đo mức cải thiện và tác động memory/GC.
4. Thử tăng số Pod lên 4, 6, 8 với CPU 1 vCPU; đo throughput, p95, DB connection và network.
5. Nếu scale out hiệu quả, thiết kế HPA với target metric phù hợp, minReplicas bảo đảm HA, maxReplicas trong ngân sách DB.
6. Kích hoạt node autoscaling nếu cần; kiểm tra Pod có thực sự schedule được.
7. Thử xóa Pod khi tải cao, xác nhận readiness/drain và tính đúng đắn của request.
8. Quyết định cấu hình theo thông lượng đạt SLO, tính chịu lỗi, chi phí và khả năng phản ứng trước spike.

Nếu load test cho thấy throughput gần như không tăng khi thêm Pod vì database bắt đầu nghẽn, thay đổi kết luận: cần mở rộng/tối ưu database hoặc giảm tải ghi đồng bộ trước. **Chiến lược scale phải theo nút nghẽn quan sát được, không theo thói quen của nhóm.**

## 25. Câu hỏi thường gặp

### 25.1. Microservices có bắt buộc horizontal scaling không?

Không. Một Microservice có thể chạy một instance khi tải nhỏ hoặc khi workload có state khó nhân bản. Tuy nhiên, khả năng tách dịch vụ giúp mỗi service có thể được scale độc lập nếu kiến trúc và vận hành hỗ trợ.

### 25.2. Horizontal scaling luôn rẻ hơn vertical scaling?

Không. Giá trị phụ thuộc kích thước máy, mức sử dụng, chi phí node, network, sidecar, log, load balancer và cách autoscaling tận dụng giờ thấp điểm. Cần cùng benchmark và SLO trước khi so sánh.

### 25.3. Tăng số Pod có giảm latency của một request đơn lẻ?

Không nhất thiết. Nếu độ trễ chính là thời gian chờ của một downstream không thay đổi, thêm Pod không làm request đó nhanh hơn. Horizontal scaling chủ yếu giúp chia tải/concurrency, giảm chờ hàng đợi ở tầng đang bão hòa. Vertical scaling có thể giảm thời gian xử lý CPU-bound nếu ứng dụng sử dụng được tài nguyên tăng thêm.

### 25.4. Kubernetes HPA và Cluster Autoscaler có giống nhau?

Không. HPA điều chỉnh số replica workload; Cluster/Node Autoscaler tạo hoặc giảm node để đủ chỗ chạy các Pod. Một hệ thống thường cần cả hai khi tải biến động vượt mức capacity của node sẵn có.

### 25.5. HPA dựa trên CPU có đủ cho worker Kafka?

Thường không. Backlog, consumer lag, tuổi message, throughput và số partition phản ánh nhu cầu xử lý tốt hơn. CPU vẫn hữu ích để phát hiện bão hòa nhưng phải kết hợp đặc tính của nguồn sự kiện và downstream.

### 25.6. Có nên scale database trước hay API trước?

Cần xem metric. Nếu API CPU bão hòa và DB còn dư công suất, scale API thường hợp lý. Nếu DB đang nghẽn query/locks/IO, thêm API replica có thể làm lỗi nặng hơn. Không có thứ tự cố định cho mọi hệ thống.

### 25.7. Có thể dùng HPA và VPA cùng một workload?

Có những cấu hình phối hợp hợp lệ nhưng cần tránh hai bộ điều khiển ảnh hưởng lẫn nhau trên cùng tín hiệu CPU/requests. Phải xem phiên bản, chế độ VPA và cách HPA lấy metric, rồi thử trên môi trường an toàn trước.

### 25.8. Tại sao p95 tăng dù CPU mới chỉ 50%?

CPU là trung bình theo thời gian và có thể che tải lệch, nghẽn ở một thread, GC pause, connection pool, locks, database, mạng hoặc một Pod nhận quá nhiều request. Phân tích trace, queue và metric theo Pod/endpoint.

## 26. Bài tập thực hành

### Bài tập A — Chọn hướng scale

Cho các tình huống:

1. API stateless CPU 95%, database còn dư công suất, tải tăng theo giờ.
2. PostgreSQL primary có cache miss cao và đọc đĩa là nút nghẽn.
3. Kafka consumer group có 4 partition, hiện đã có 4 consumer và backlog vẫn tăng.
4. 10 Pod đều timeout khi gọi cổng thanh toán bị giới hạn 100 request/giây.
5. Ứng dụng lưu session trong RAM của mỗi Pod, chạy một instance tốt nhưng nhân bản thì user mất session.

Với mỗi tình huống, hãy ghi: bottleneck, hướng scale dự kiến, rủi ro và phép đo cần có để xác nhận. Gợi ý: không phải bài nào cũng giải được bằng thêm CPU hoặc Pod; có trường hợp phải thay đổi thiết kế dữ liệu, partition, rate limit hoặc session ownership.

### Bài tập B — Tính replica

Một Pod đáp ứng ổn định 120 request/giây ở SLO p95 dưới 150 ms. Dự kiến peak 540 request/giây. Nhóm đặt tải mục tiêu tối đa 75% công suất mỗi Pod.

~~~text
Required pods = ceil(540 / (120 × 0.75))
              = ceil(6)
              = 6 Pods
~~~

Tiếp tục tự kiểm tra: nếu một Pod ngừng hoạt động, 5 Pod còn lại có đáp ứng 540 RPS ở target 75% không? Không: 5 × 120 × 0,75 = 450 RPS. Cần xác định số replica hoặc giải pháp dự phòng để đạt yêu cầu chống mất một Pod, và xác nhận qua load test.

### Bài tập C — Đo trên môi trường tạm thời

Dựng một API demo có endpoint CPU-bound và một endpoint gọi database. Thử lần lượt:

- 1 Pod × 1 vCPU.
- 1 Pod × 2 vCPU.
- 2 Pod × 1 vCPU.
- 4 Pod × 1 vCPU.

Đo rate, p95/p99, error, CPU throttling và database wait. So sánh tại **cùng mức tải** rồi tại **giới hạn tải còn đạt SLO**. Giải thích vì sao endpoint CPU-bound và DB-bound có thể phản ứng khác nhau khi scale.

## 27. Checklist quyết định Scaling cho một Microservice

- [ ] Đã xác định SLO và peak workload đại diện, không chỉ đếm RPS.
- [ ] Có baseline throughput, latency, error và tài nguyên theo từng Pod.
- [ ] Đã tìm bottleneck chính: CPU, memory, thread, database, broker, network hay downstream.
- [ ] Đã thử tối ưu rõ ràng trước khi cấp tài nguyên lớn hơn.
- [ ] Nếu scale out, instance có xử lý request độc lập và không giữ state độc quyền cục bộ.
- [ ] Đã kiểm tra session, cache, scheduler, concurrency và idempotency giữa các Pod.
- [ ] Đã tính tổng connection pool, rate limit và sức chịu tải của dependency.
- [ ] HPA dùng metric phù hợp, có requests/metrics pipeline, min/max replica và stabilization.
- [ ] Cluster có đủ node capacity hoặc có autoscaling node đáng tin cậy.
- [ ] Readiness, graceful shutdown và scale-in không làm mất công việc đang chạy.
- [ ] Pod được phân bố trên failure domains phù hợp với mục tiêu HA.
- [ ] Benchmark đã so sánh vertical/horizontal/hybrid trong cùng điều kiện.
- [ ] Kết quả scale cải thiện throughput **khi vẫn đạt SLO**, không chỉ làm tăng CPU tổng.
- [ ] Chi phí bao gồm node, network, load balancer, monitoring và downstream.
- [ ] Có kịch bản mất một instance/node và kế hoạch bảo vệ tải khi autoscaling phản ứng chậm.
- [ ] Có cảnh báo khi replica đạt max, Pod Pending, queue backlog tăng hoặc dependency bão hòa.

## 28. Kết luận

**Mở rộng theo chiều dọc** tăng tài nguyên cho một instance; **mở rộng theo chiều ngang** tăng số instance để phân chia công việc. Vertical scaling có lợi khi một tiến trình cần thêm RAM/CPU/I/O và việc phân phối chưa cần thiết hoặc khó thực hiện. Horizontal scaling đặc biệt phù hợp với API stateless và worker độc lập, đồng thời hỗ trợ điều chỉnh công suất và tăng khả năng chịu lỗi khi các replica được triển khai đúng cách.

Trong Microservices, quyết định scale phải xuất phát từ **mức tải, giới hạn dịch vụ phụ thuộc, tính đúng đắn của dữ liệu và SLO**. Một API có 20 replica vẫn có thể nghẽn vì database; một database rất lớn vẫn có thể gây downtime nếu chỉ có một điểm lỗi; và một autoscaler được cấu hình đẹp vẫn không giúp nếu Pod không sẵn sàng hoặc queue bị nghẽn bởi poison message.

Cách tiếp cận thực dụng là **đo → xác định nút thắt → lựa chọn vertical/horizontal/hybrid → load test → kiểm tra scale-in/khả năng chịu lỗi → theo dõi sau triển khai**. Khi hiểu rõ điểm mạnh và giới hạn của từng hướng, nhóm có thể mở rộng dịch vụ theo nhu cầu thực tế mà vẫn kiểm soát độ trễ, độ tin cậy và chi phí.
# Tính giới hạn pool theo tài nguyên và số bản sao ứng dụng

Trong ứng dụng Spring Data Relational R2DBC, connection pool giới hạn số kết nối database mà một instance ứng dụng có thể sử dụng đồng thời. Giá trị `maxSize` không chỉ là một tham số tối ưu hiệu năng: khi ứng dụng chạy nhiều replica, tổng số connection có thể tạo ra bằng tổng pool của tất cả instance, worker và dịch vụ cùng truy cập database. Nếu mỗi pod cấu hình pool quá lớn, autoscaling hoặc rolling deployment có thể làm database vượt giới hạn connection dù từng pod riêng lẻ vẫn có vẻ hợp lý.

Thiết kế pool cần cân bằng ba yếu tố: **capacity của database**, **số replica tối đa của mọi client** và **mức concurrency/connection hold time của workload**. Pool quá nhỏ tạo hàng đợi acquire và tăng latency; pool quá lớn làm tăng số session, memory, scheduling và contention ở database. Mục tiêu là chọn một giới hạn đủ phục vụ tải dự kiến, có headroom cho biến động, đồng thời không vượt ngân sách connection toàn hệ thống.

## 1. Connection pool giải quyết vấn đề gì?

Mở một kết nối database có chi phí: thiết lập TCP/TLS, xác thực, khởi tạo session và các bước handshake của driver/database. Nếu mỗi thao tác tạo rồi đóng một connection mới, latency và tải hạ tầng sẽ tăng.

R2DBC connection pool giữ một tập connection để tái sử dụng:

```text
HTTP request / background job
             |
             v
       R2DBC Connection Pool
        /       |        \
       v        v         v
   Connection Connection Connection
       |        |         |
       +--------+---------+
                |
                v
             Database
```

Khi một thao tác cần database, ứng dụng yêu cầu connection từ pool. Nếu có connection rảnh, pool cấp ngay. Nếu không, request chờ trong hàng đợi acquire cho tới khi connection được trả về hoặc hết thời gian chờ. Khi thao tác hoàn tất và lifecycle được cleanup, connection được trả về pool hoặc bị loại bỏ nếu không còn hợp lệ.

Pool giúp tái sử dụng connection và giới hạn concurrency tới database. Nó không làm database xử lý nhiều truy vấn hơn khả năng CPU, I/O, lock hoặc memory của database. Tăng số connection có thể làm tăng throughput tới một điểm, sau đó chỉ làm tăng contention.

## 2. Phân biệt pool size, connection đang dùng và request concurrency

Các khái niệm sau không giống nhau:

| Khái niệm | Ý nghĩa |
|---|---|
| `maxSize` | Số connection tối đa một pool được phép quản lý |
| `initialSize` | Số connection pool cố gắng tạo ban đầu, tùy implementation và thời điểm khởi tạo |
| Allocated/total | Số connection đã được pool tạo |
| Acquired/active | Số connection đang được cấp cho consumer |
| Idle | Số connection rảnh có thể cấp |
| Pending acquire | Số yêu cầu đang chờ connection |
| Application concurrency | Số công việc/request có thể chạy đồng thời ở ứng dụng |
| Database max connections | Giới hạn session/connection phía database hoặc proxy |

Một ứng dụng có 500 request HTTP đồng thời không nhất thiết cần 500 database connection. Nhiều request có thể không truy cập database, có thể chờ I/O khác, hoặc các thao tác database chỉ chiếm một phần thời gian request. Ngược lại, một request có thể thực hiện nhiều truy vấn tuần tự hoặc chạy nhiều tác vụ database song song.

Vì vậy, không chọn `maxSize` bằng số thread, số CPU hoặc số HTTP request tối đa. Hãy đo số thao tác database đồng thời và thời gian mỗi thao tác giữ connection.

## 3. Ngân sách connection bắt đầu từ database

Database thường có giới hạn số connection/session. Giới hạn này phải phục vụ tất cả client, không riêng một ứng dụng Spring Boot.

Ví dụ các nhóm cùng dùng database:

- Các replica của API chính.
- Worker/consumer và scheduled jobs.
- Dịch vụ khác dùng chung database.
- Migration job, schema tool và deployment task.
- Dashboard, BI, report hoặc batch integration.
- DBA, monitoring, backup, replication và kết nối quản trị.
- Connection dự phòng cho failover hoặc xử lý sự cố.

Không cấp toàn bộ `max_connections` cho pool ứng dụng. Cần giữ phần dự phòng cho quản trị và các workload khác, đồng thời xét giới hạn thực tế của database về RAM, CPU, file descriptor và chi phí mỗi session.

Một công thức ngân sách đơn giản:

\[
\text{Connection budget cho service}
= \text{DB connection limit}
- \text{reserved capacity}
- \text{other clients}
\]

Đây là ngân sách tổng của service trên toàn bộ replica và mọi pool thuộc service đó, không phải ngân sách cho từng pod.

### 3.1. Ví dụ phân bổ ngân sách

Giả sử một PostgreSQL instance có giới hạn 300 connection. Đội vận hành quyết định giữ 50 connection cho quản trị, monitoring, failover và headroom; các service khác có ngân sách tối đa 70; migration/reporting và công cụ nội bộ cần thêm 20.

| Thành phần | Connection dự kiến |
|---|---:|
| DB connection limit | 300 |
| Dự phòng/quản trị | 50 |
| Service khác | 70 |
| Migration/reporting/tools | 20 |
| Còn lại cho service đang thiết kế | 160 |

160 là trần ngân sách tổng cho service này trong kịch bản giả định. Nếu service có nhiều pool (ví dụ primary và read replica), tổng `maxSize` của mọi pool trên mọi replica phải nằm trong ngân sách được giao.

Các số trên chỉ là ví dụ. `max_connections` không đồng nghĩa database có thể xử lý hiệu quả từng ấy query đồng thời; capacity thực tế phải được xác định qua tải thử và metrics server.

## 4. Số replica làm tổng pool nhân lên

Mỗi instance thường tạo pool riêng. Nếu một ứng dụng có `R` replica và mỗi replica có `P` connection tối đa:

\[
\text{Tổng connection tối đa} = R \times P
\]

Nếu có nhiều pool trên mỗi instance:

\[
\text{Tổng connection tối đa}
= R \times \sum_{i=1}^{n} P_i
\]

Trong đó `P_i` là max size của pool thứ `i` trên một instance. Công thức cần mở rộng nếu có nhiều loại replica hoặc worker có cấu hình khác nhau.

Ví dụ một service có 8 replica, mỗi pod pool `maxSize = 30`:

\[
8 \times 30 = 240\text{ connections}
\]

Nếu autoscaling tăng lên 12 replica, tổng trần trở thành 360 connection. Database có thể bị vượt ngân sách dù cấu hình trong mỗi pod không thay đổi.

### 4.1. Luôn dùng số replica tối đa, không dùng số replica trung bình

Pool phải được tính theo mức scale tối đa được phép, bao gồm:

- `maxReplicas` của Horizontal Pod Autoscaler.
- Replica cố định ngoài HPA.
- Worker deployment có thể scale độc lập.
- CronJob hoặc batch job chạy đồng thời.
- Instance cũ còn sống trong rolling deployment.
- Replica tạm thời khi rollout, canary hoặc blue-green.

Nếu chỉ tính theo số pod bình thường vào giờ thấp điểm, hệ thống có thể vượt giới hạn database đúng lúc autoscaling cần mở rộng để xử lý tải cao.

### 4.2. Rolling deployment và surge capacity

Trong rolling update, Kubernetes hoặc nền tảng triển khai có thể tạo pod mới trước khi pod cũ dừng. `maxSurge` làm số replica tạm thời cao hơn `replicas` mong muốn.

Ví dụ deployment có 8 replica và cho phép surge thêm 2 pod. Trong giai đoạn rollout có thể tồn tại 10 pod. Nếu pool mỗi pod tối đa 16:

\[
10 \times 16 = 160\text{ connections}
\]

Tính theo 8 pod sẽ chỉ ra 128 connection và đánh giá thiếu 32 connection so với peak rollout. Hãy tính cả surge, canary và blue-green overlap trong ngân sách.

### 4.3. Scale down cũng có thể tạo biến động

Khi pod bị terminate, pool cần đóng connection và request đang chạy cần có thời gian hoàn tất hoặc bị hủy theo shutdown policy. Nếu termination grace period quá ngắn, request có thể lỗi; nếu pod cũ chưa thoát nhưng pod mới đã lên, số connection có thể tạm thời tăng.

Pool sizing và graceful shutdown cần được xem cùng nhau. Hãy theo dõi số connection theo instance và kiểm tra hành vi rollout thực tế.

## 5. Công thức tính maxSize theo số replica

Sau khi có ngân sách tổng cho service, chia cho số instance tối đa có thể tồn tại đồng thời:

\[
P_{\max}
\leq
\left\lfloor
\frac{B_{service}}{R_{peak}}
\right\rfloor
\]

Trong đó:

- `B_service`: ngân sách connection tổng của service.
- `R_peak`: số replica/worker có thể tồn tại đồng thời trong kịch bản lớn nhất.
- `P_max`: max size cho mỗi instance nếu mọi instance dùng cấu hình giống nhau.

Với ví dụ ngân sách 160 connection và peak 10 pod:

\[
P_{\max} \leq \lfloor 160/10 \rfloor = 16
\]

Vì vậy, `maxSize = 16` là trần toán học theo ngân sách giả định. Có thể chọn thấp hơn để dành headroom hoặc vì database không xử lý hiệu quả 160 truy vấn đồng thời.

### 5.1. Nhiều pool trên một instance

Nếu mỗi pod có pool ghi primary tối đa 10 và pool đọc replica tối đa 8, tổng trên một pod là 18. Với 10 pod:

\[
10 \times (10 + 8) = 180
\]

Không tính riêng từng pool rồi quên tổng. Mọi pool kết nối tới cùng một database endpoint phải cộng vào ngân sách endpoint đó. Nếu read pool kết nối tới một database server khác, lập ngân sách riêng cho server đó.

### 5.2. Cấu hình pool khác nhau theo loại workload

API, worker và report job không nhất thiết cần cùng `maxSize`. Có thể phân ngân sách theo vai trò:

- API tương tác: pool nhỏ, latency mục tiêu thấp, concurrency có giới hạn.
- Worker: pool theo throughput và concurrency job.
- Report/export: pool riêng hoặc quota nhỏ để workload dài không chiếm hết connection của API.
- Migration: connection riêng, chỉ chạy trong cửa sổ triển khai và được tính vào ngân sách.

Tuy nhiên, nhiều pool riêng không tạo thêm capacity database. Tổng tất cả pool vẫn phải nằm trong giới hạn server và được đo như một hệ thống.

## 6. Xác định nhu cầu từ concurrency và thời gian giữ connection

Ngân sách database cho biết giới hạn trên. Bước tiếp theo là ước lượng workload thực sự cần bao nhiêu connection.

Một cách ước lượng dựa trên định luật Little:

\[
L = \lambda \times W
\]

Trong đó:

- `L`: số thao tác trung bình đang ở trong hệ thống.
- `λ`: tốc độ thao tác đến, ví dụ database operations/giây.
- `W`: thời gian trung bình một thao tác chiếm tài nguyên, tính bằng giây.

Nếu service phát sinh trung bình 120 thao tác database mỗi giây và mỗi thao tác giữ connection trung bình 80 ms:

\[
L = 120 \times 0.08 = 9.6
\]

Số connection bận trung bình ước tính khoảng 10 nếu mỗi thao tác giữ một connection trong khoảng thời gian đó và không có sự chia sẻ đặc biệt. Peak concurrency sẽ cao hơn trung bình khi traffic burst hoặc thời gian giữ connection có đuôi dài.

Không dùng kết quả này làm `maxSize` cuối cùng. Đây là baseline để so sánh với active connections, queueing và latency đo được.

### 6.1. Connection hold time quan trọng hơn thời gian HTTP request

Một HTTP request có thể tồn tại 2 giây nhưng chỉ dùng database 50 ms. Ngược lại, một response streaming có thể giữ result và connection trong nhiều giây.

Hãy đo:

- Thời gian acquire connection.
- Thời gian statement/result được tiêu thụ.
- Thời gian transaction giữ connection.
- Thời gian downstream xử lý khi connection vẫn đang được giữ.

Nếu một transaction bao trùm cả HTTP call hoặc xử lý CPU dài, `W` tăng và số connection bận trung bình tăng theo.

### 6.2. Tính peak concurrency theo operation

Một service có nhiều loại thao tác:

| Operation | Rate giả định | Hold time trung bình | Connection bận trung bình ước tính |
|---|---:|---:|---:|
| Lookup customer | 80/s | 20 ms | 1.6 |
| Create order | 25/s | 100 ms | 2.5 |
| Update inventory | 30/s | 60 ms | 1.8 |
| Report page | 5/s | 400 ms | 2.0 |
| Tổng | 140/s | — | 7.9 |

Con số tổng là ước lượng theo Little's Law nếu các nhóm dùng connection độc lập trong khoảng hold time đã đo. Nó chưa bao gồm burst, tail latency, retry, transaction dài và prefetch. Report page có rate thấp nhưng hold time dài nên vẫn tiêu thụ capacity đáng kể.

### 6.3. Dùng percentile và peak thay vì chỉ dùng average

Connection occupancy thường chịu ảnh hưởng bởi các thao tác hiếm nhưng rất dài. Theo dõi p50/p95/p99 hold duration và active/pending connection trong giờ cao điểm. Một average thấp có thể che giấu vài stream giữ connection trong nhiều phút.

Nếu tải có burst, thử tải theo profile thực tế và đo peak concurrent acquire. Không chọn pool chỉ từ rate trung bình của một ngày.

## 7. Pool size không bằng số thread

R2DBC là non-blocking API, do đó số thread event loop không quyết định trực tiếp số connection database cần có.

Ví dụ:

- Một event loop thread có thể điều phối nhiều request.
- Một request có thể không dùng database.
- Một query có thể chờ network mà không chiếm thread, nhưng vẫn giữ connection.
- Một transaction có thể giữ connection qua nhiều thao tác reactive.
- `flatMap` có thể tạo nhiều thao tác database đồng thời trong cùng một request.

Không dùng công thức “số CPU × 2” hoặc “số Netty worker thread” để đặt pool size nếu chưa có đo lường. Hãy dựa vào database concurrency, hold time và giới hạn database.

### 7.1. Concurrency ở Reactor có thể vượt pool capacity

Ví dụ:

```java
return Flux.fromIterable(orderIds)
    .flatMap(orderId -> orderRepository.findById(orderId), 100);
```

Đoạn code có thể tạo tối đa nhiều inner publisher đang hoạt động. Nếu pool chỉ có 16 connection, một phần thao tác phải chờ acquire. Nếu nhiều request cùng chạy pipeline này, nhu cầu tổng có thể vượt xa pool.

Đặt concurrency theo ngân sách:

```java
return Flux.fromIterable(orderIds)
    .flatMap(orderId -> orderRepository.findById(orderId), 8);
```

Con số 8 chỉ là ví dụ. Cần tính cả concurrency từ request khác và worker khác; không dành toàn bộ pool cho một pipeline.

### 7.2. Concurrency limit không thay thế pool limit

Giới hạn `flatMap` ở một service không bao phủ các repository call khác, scheduler, worker hoặc request song song. Pool `maxSize` vẫn là hàng rào cuối cùng cho mỗi instance. Bulkhead/concurrency limit giúp phân phối capacity giữa workload để một operation không chiếm hết pool.

## 8. Transaction ảnh hưởng tới nhu cầu connection

Trong reactive transaction, connection thường được gắn với transaction context và giữ tới khi transaction complete, error hoặc cancel rồi cleanup. Nếu transaction kéo dài qua nhiều thao tác hoặc chờ một service ngoài, connection không thể được cấp cho request khác trong thời gian đó.

Ví dụ cần cân nhắc:

```java
@Transactional
public Mono<Order> createOrder(CreateOrder command) {
    return orderRepository.save(toOrder(command))
        .flatMap(order -> inventoryClient.reserve(order)
            .thenReturn(order));
}
```

Nếu `inventoryClient.reserve` là HTTP call chậm và transaction vẫn mở trong lúc chờ, connection database có thể bị giữ lâu hơn cần thiết. Hãy cân nhắc rút ngắn transaction, tách workflow hoặc dùng outbox/saga tùy yêu cầu nhất quán.

### 8.1. Transaction dài làm pool bận dù SQL đã chạy xong

Một transaction có thể giữ connection giữa hai statement trong lúc ứng dụng xử lý logic. Vì vậy, query duration ngắn không đảm bảo connection hold time ngắn.

Theo dõi transaction duration riêng nếu có thể. Đặt giới hạn cho công việc trong transaction và tránh chờ user, network hoặc timer dài khi connection đang bị giữ.

### 8.2. Streaming result có thể giữ connection theo tốc độ consumer

Một `Flux` lớn được trả trực tiếp cho WebFlux client chậm có thể làm result và connection tồn tại tới khi stream hoàn tất hoặc bị hủy. Nếu endpoint export có thời gian dài, cân nhắc keyset pagination hoặc background export job để release connection giữa các page.

Pool sizing cần xét cả workload stream dài, không chỉ query CRUD ngắn.

## 9. Chọn maxSize thấp hơn ngân sách toán học khi cần

Giới hạn chia ngân sách cho biết mức tối đa không vượt server budget. Nhưng database có thể đạt throughput tốt nhất ở số connection thấp hơn.

Một số nguyên nhân:

- Mỗi connection tạo session/process hoặc memory overhead.
- Quá nhiều query đồng thời tranh CPU và I/O.
- Lock contention tăng khi nhiều transaction cập nhật cùng dữ liệu.
- Buffer/cache của database bị phân tán cho nhiều hoạt động đồng thời.
- Context switching và scheduling overhead tăng.
- Nhiều connection cùng chờ một lock không làm transaction hoàn tất nhanh hơn.

Vì vậy, hãy load test với nhiều giá trị pool size. So sánh throughput, p95/p99 latency, database CPU/I/O, lock waits, pending acquire và error rate. Chọn điểm cân bằng tốt nhất thay vì giá trị lớn nhất có thể.

## 10. Tính ngân sách trong một ví dụ đầy đủ

Giả sử hệ thống có các giả định sau:

| Thông số | Giá trị giả định |
|---|---:|
| PostgreSQL connection limit | 400 |
| Reserved cho admin/monitoring/failover | 60 |
| Các service khác | 100 |
| Worker/report/migration ngoài service | 40 |
| Ngân sách còn lại cho service API | 200 |
| Replica API mong muốn | 10 |
| Rolling surge tối đa | 2 |
| Peak replica trong rollout | 12 |

Ngân sách mỗi pod theo giới hạn server:

\[
P_{max} = \left\lfloor \frac{200}{12} \right\rfloor = 16
\]

Nếu chọn `maxSize = 16`, tổng pool trong rollout là:

\[
12 \times 16 = 192
\]

Service còn 8 connection headroom trong ngân sách giả định. Nhưng cần kiểm tra liệu database có xử lý hiệu quả 192 connection bổ sung hay không. Nếu load test cho thấy throughput tối ưu ở 10 connection/pod, chọn 10 có thể tốt hơn:

\[
12 \times 10 = 120
\]

Khi đó còn 80 connection trong ngân sách service cho biến động, job hoặc một pool khác. Không nhất thiết phải sử dụng hết ngân sách.

### 10.1. Nếu có hai pool

Giả sử mỗi pod có:

- Primary write pool: `maxSize = 8`.
- Read replica pool: `maxSize = 6`.

Với 12 pod, nhu cầu trần là:

\[
12 \times (8 + 6) = 168
\]

Nếu primary và read replica là hai database server khác nhau, phân bổ 96 connection cho primary và 72 cho replica rồi đối chiếu ngân sách riêng của từng server. Không cộng vào một con số chung nếu chúng có giới hạn khác nhau; cũng không bỏ qua pool nào vì mỗi server vẫn có giới hạn riêng.

## 11. Autoscaling cần gắn với database capacity

HPA có thể tăng replica dựa trên CPU, memory hoặc custom metrics. Nhưng mỗi replica mới có thể tạo thêm pool và tăng tổng connection.

Nếu HPA scale từ 5 lên 20 pod, pool max 20 làm trần connection tăng từ 100 lên 400. Nếu database chỉ có capacity cho 150 connection của service, autoscaling có thể biến overload ở application thành overload ở database.

### 11.1. Đặt maxReplicas theo connection budget

Một giới hạn đơn giản:

\[
R_{max} \leq
\left\lfloor
\frac{B_{service}}{P_{per\ instance}}
\right\rfloor
\]

Nếu ngân sách service là 200 và pool mỗi instance tối đa 10, giới hạn lý thuyết là 20 instance, trước khi xét surge và các pool khác. Nếu rollout cần thêm 2 pod, cần giảm `maxReplicas` hoặc giảm pool per instance để tổng peak vẫn nằm trong ngân sách.

### 11.2. Scale application không đồng nghĩa database scale

Khi request tăng, tăng replica có thể giúp xử lý HTTP, CPU và I/O ngoài database. Nhưng nếu mọi request đều cần cùng database và database đã bão hòa, thêm pod chỉ tạo thêm connection waiter và query concurrency.

Hãy phân biệt bottleneck:

- Nếu application CPU cao nhưng database còn capacity, scale app có thể hữu ích.
- Nếu pool pending tăng do mỗi pod có pool quá nhỏ nhưng database còn capacity, có thể điều chỉnh pool/concurrency.
- Nếu database CPU/IO/lock đã bão hòa, scale app thường làm tình hình tệ hơn; cần tối ưu query, giảm load hoặc scale database.

### 11.3. HPA theo pending acquire cần thận trọng

Nếu dùng pending acquire làm tín hiệu scale, cần tránh vòng lặp: pool pending tăng → HPA thêm pod → mỗi pod tạo thêm pool → database nhận thêm connection → database quá tải hơn. Custom autoscaling phải có giới hạn tổng connection và hiểu capacity của database.

Có thể scale worker hoặc API theo queue/CPU nhưng giữ tổng pool budget cố định bằng cách giảm pool per instance khi replica tăng, hoặc dùng một giới hạn concurrency tập trung. Cách triển khai phụ thuộc nền tảng và kiến trúc.

## 12. Cấu hình pool trong Spring Boot

Spring Boot hỗ trợ cấu hình R2DBC pool khi dependency và phiên bản phù hợp được đưa vào. Các property thường gặp có prefix `spring.r2dbc.pool`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db.internal:5432/app
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 2
      max-size: 10
      max-acquire-time: 2s
      max-create-connection-time: 3s
      max-idle-time: 10m
      max-life-time: 30m
```

Đây là ví dụ minh họa, không phải cấu hình mặc định phù hợp mọi môi trường. Property availability và tên chính xác phụ thuộc Spring Boot version, `r2dbc-pool` và cách tạo `ConnectionFactory`. Kiểm tra configuration metadata/tài liệu đúng phiên bản dự án.

### 12.1. Ý nghĩa một số thuộc tính

| Thuộc tính | Ý nghĩa | Lưu ý |
|---|---|---|
| `enabled` | Bật/tắt pooling nếu auto-configuration hỗ trợ | Xác nhận dependency và auto-config |
| `initial-size` | Số connection khởi tạo ban đầu | Tăng startup connection burst nếu nhiều pod cùng lên |
| `max-size` | Giới hạn connection của một pool trong một instance | Phải nhân với replica và số pool |
| `max-acquire-time` | Thời gian tối đa chờ lấy connection | Chọn theo request budget |
| `max-create-connection-time` | Thời gian tối đa tạo connection mới | Liên quan network/authentication |
| `max-idle-time` | Thời gian connection idle trước khi bị loại theo policy | Phối hợp với database/proxy idle timeout |
| `max-life-time` | Tuổi thọ tối đa connection trước khi được thay thế | Có thể giúp luân chuyển connection cũ |

Một số version còn hỗ trợ validation timeout/query hoặc background eviction interval. Không sao chép property không có trong version đang chạy.

### 12.2. Không đặt initial-size bằng max-size một cách tự động

Nếu có 20 pod khởi động đồng thời và mỗi pool `initial-size = 20`, hệ thống có thể tạo 400 connection ngay trong lúc rollout. Điều này tạo connection storm, tăng tải authentication và làm database chạm connection limit trước khi workload thực sự cần.

Chọn initial size nhỏ để startup có thể diễn ra từ từ; pool mở rộng theo nhu cầu trong giới hạn max size. Nếu cần warm-up có kiểm soát, hãy điều phối rollout và connection ramp-up.

### 12.3. Acquire timeout không thay thế maxSize

`maxSize` giới hạn số connection. `maxAcquireTime` giới hạn thời gian một caller chờ connection rảnh. Nếu pool bão hòa, tăng acquire timeout chỉ làm request chờ lâu hơn và giữ nhiều request pending; nó không tạo thêm capacity.

Chọn acquire timeout nhỏ hơn phần ngân sách latency còn lại của request. Nếu HTTP deadline là 3 giây, không nên để acquire chờ 10 giây rồi mới báo lỗi.

## 13. Cấu hình qua R2dbcPoolConfiguration

Nếu tự tạo pool, có thể cấu hình qua `ConnectionPoolConfiguration` của `r2dbc-pool`:

```java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .initialSize(2)
        .maxSize(10)
        .maxAcquireTime(Duration.ofSeconds(2))
        .maxCreateConnectionTime(Duration.ofSeconds(3))
        .maxIdleTime(Duration.ofMinutes(10))
        .maxLifeTime(Duration.ofMinutes(30))
        .build();

ConnectionPool pool = new ConnectionPool(configuration);
```

Ví dụ sử dụng API của R2DBC Pool; package, builder method và default cần khớp version. Nếu Spring Boot đã auto-configure pool, không tạo thêm pool thứ hai một cách vô tình. Mỗi `ConnectionFactory`/pool bổ sung phải được tính vào connection budget và được đóng đúng lifecycle.

## 14. Pool size, min/initial size và idle policy

Pool không nhất thiết phải duy trì mọi connection ở trạng thái mở.

- `initialSize` kiểm soát số connection khởi tạo ban đầu.
- `maxSize` giới hạn số connection tối đa.
- `maxIdleTime` và eviction policy giúp loại connection idle lâu.
- `maxLifeTime` giúp luân chuyển connection cũ.

Không phải mọi pool đều có một thuộc tính `minSize` riêng. Một số cấu hình dùng `initialSize` nhưng không bảo đảm duy trì số connection tối thiểu sau khi eviction. Kiểm tra semantics thực tế của implementation.

### 14.1. maxIdleTime và idle timeout phía database/proxy

Nếu database hoặc proxy đóng connection idle sau 5 phút nhưng pool giữ connection lâu hơn, pool có thể cấp một connection đã bị server đóng. Hãy phối hợp idle policy để pool phát hiện/loại connection trước hoặc xử lý lỗi validation/reconnect đúng cách.

Không đặt `maxIdleTime` quá ngắn nếu workload đều đặn vì pool sẽ liên tục đóng/mở connection. Cũng không giữ idle connection quá lâu khi có nhiều pod scale lớn và database có ngân sách nhỏ.

### 14.2. maxLifeTime và connection rotation

`maxLifeTime` có thể giúp thay connection cũ, hỗ trợ rotation credential, DNS change hoặc tránh giữ session lâu. Khi nhiều pod có cùng lifetime và khởi động cùng lúc, chúng có thể cùng loại connection ở một thời điểm. Nếu implementation hỗ trợ jitter hoặc eviction scheduling phù hợp, cân nhắc dùng để tránh đồng loạt reconnect.

Đừng đặt lifetime ngắn hơn mức cần thiết; tạo lại connection có chi phí và có thể gây spike khi nhiều connection bị thay cùng lúc.

## 15. Connection pool và PgBouncer/proxy

Một số hệ thống đặt PgBouncer hoặc database proxy giữa ứng dụng và PostgreSQL. Khi đó cần phân biệt:

- Client connection từ R2DBC pool tới proxy.
- Server connection từ proxy tới PostgreSQL.
- Pooling mode của proxy: session, transaction hoặc statement tùy sản phẩm/cấu hình.

R2DBC `maxSize` giới hạn client connection của từng application instance tới proxy. Nó không nhất thiết bằng số PostgreSQL backend connection được proxy giữ.

Với PgBouncer transaction pooling, connection backend có thể được cấp trong transaction và trả lại sau commit/rollback. Điều này ảnh hưởng tới session-level state, prepared statements, temporary tables và các tính năng phụ thuộc session. Cần kiểm tra tính tương thích của driver và ứng dụng với pooling mode đang dùng.

### 15.1. Proxy không làm biến mất giới hạn client

Ngay cả khi proxy giảm số backend session, proxy vẫn có giới hạn client connection, memory, file descriptor và queue. Pool ở ứng dụng cần nằm trong ngân sách client connection của proxy; proxy backend pool cần nằm trong ngân sách PostgreSQL.

### 15.2. Lập ngân sách ở cả hai tầng

```text
Application replicas
  10 pods x 10 R2DBC connections = 100 client connections
                    |
                    v
              PgBouncer
      client limit / queue / pool mode
                    |
                    v
          PostgreSQL backend pool
       backend connections <= DB budget
```

Hãy theo dõi client connections và server connections riêng. Không so sánh trực tiếp `R2DBC maxSize` với `max_connections` khi có proxy mà bỏ qua lớp trung gian.

## 16. Nhiều database và read/write pools

Một ứng dụng có thể kết nối nhiều database hoặc tách read/write:

- Primary database cho INSERT/UPDATE/transaction.
- Read replica cho truy vấn đọc.
- Database riêng cho audit/reporting.
- Tenant database hoặc shard khác nhau.

Mỗi `ConnectionFactory` có thể có pool riêng. Hãy lập bảng ngân sách theo endpoint/database:

| Database endpoint | Pool mỗi pod | Peak pod | Tổng pool tối đa | Ngân sách endpoint |
|---|---:|---:|---:|---:|
| Primary | 8 | 12 | 96 | 120 |
| Read replica | 6 | 12 | 72 | 100 |
| Reporting DB | 2 | 4 | 8 | 20 |

Các số là ví dụ. Bảng giúp thấy tổng connection theo server và chỗ còn headroom. Nếu một database được dùng bởi nhiều service, phải cộng tất cả service.

### 16.1. Không gửi mọi truy vấn đọc sang replica theo mặc định

Read replica có capacity riêng, replication lag và consistency semantics khác primary. Tăng read pool không giải quyết query chậm nếu replica CPU/I/O đã bão hòa. Đặt ngân sách theo từng replica và phân phối workload có chủ đích.

### 16.2. Tenant/shard fan-out

Nếu một pod tạo pool tới nhiều shard, tổng connection trên một pod là tổng max size của tất cả pool được tạo. Lazy pool creation có thể trì hoãn việc tạo connection nhưng không làm biến mất trần tổng nếu mọi shard đều được sử dụng.

Với hàng trăm tenant database, không tạo một pool lớn cố định cho từng tenant nếu không có cơ chế giới hạn và eviction. Cân nhắc pool registry có giới hạn, idle eviction và ngân sách tổng.

## 17. Tách pool cho workload nặng

Một số query report/export có thể giữ connection lâu hơn lookup giao dịch. Nếu dùng chung một pool, workload dài có thể chiếm hết connection khiến request quan trọng phải chờ.

Có thể cân nhắc:

- Pool riêng cho reporting/read replica.
- Concurrency limit thấp cho export.
- Queue cho batch job.
- Giới hạn query timeout/page size.
- Ưu tiên capacity cho transaction tương tác.

Pool riêng chỉ hữu ích khi nó trỏ tới capacity được quản lý riêng hoặc được quota rõ. Nếu hai pool cùng trỏ một PostgreSQL server, tổng connection vẫn cộng lại và có thể làm server quá tải hơn.

## 18. Retry làm tăng nhu cầu connection như thế nào?

Retry có giới hạn vẫn có thể làm tăng database operation rate khi lỗi xảy ra. Nếu 100 request cùng retry ba lần, database có thể nhận nhiều attempt hơn số request gốc.

Theo dõi:

- Attempt count theo operation/error category.
- Backoff duration.
- Retry success ratio.
- Số operation đang chờ backoff.
- Connection acquire rate và query rate trong lúc retry.

Dùng exponential backoff và jitter cho lỗi tạm thời. Không retry lỗi validation/constraint hoặc lỗi không thể tự hết. Với write, cần idempotency để retry không tạo side effect trùng.

Pool sizing không nên dựa trên giả định retry không bao giờ xảy ra. Tuy nhiên, cũng không nên tăng pool để hấp thụ một retry storm; cần giới hạn retry và bảo vệ database.

## 19. Pool size và database workload capacity

`max_connections` chỉ là giới hạn số session, không phải công suất xử lý đồng thời tối ưu. Database có thể đạt throughput tối đa ở mức connection thấp hơn giới hạn cấu hình.

Load test nên thay đổi pool size theo một số mức và đo:

- Throughput (operations/second).
- p50/p95/p99 latency.
- Active/pending connections và acquire duration.
- Database CPU, memory, I/O và storage latency.
- Lock waits, deadlocks và transaction duration.
- Error rate, timeout và retry rate.
- Connection creation/close rate.

Nếu tăng pool từ 10 lên 20 không cải thiện throughput nhưng p99 và database CPU tăng, pool lớn hơn không có lợi. Có thể cần tối ưu query/index hoặc giảm concurrency.

### 19.1. Thử tải theo kịch bản thực tế

Bao gồm:

- Traffic bình thường và giờ cao điểm.
- Burst ngắn và sustained load.
- Tỷ lệ read/write thực tế.
- Transaction ngắn và transaction dài.
- Query trả nhiều hàng/stream.
- Worker và report job chạy đồng thời.
- Rolling deployment/autoscaling.
- Một số lỗi transient gây retry.

Chỉ benchmark một câu SELECT đơn giản thường không đại diện cho connection hold time và contention của workload thật.

## 20. Theo dõi metrics để điều chỉnh pool

Các metric cần theo dõi:

| Metric | Khi tăng bất thường cần xem |
|---|---|
| Acquired/active | Connection hold time, concurrency, transaction dài |
| Idle | Pool có đang cấp quá nhiều connection so với nhu cầu không |
| Pending acquire | Pool saturation, query chậm, burst, maxSize quá nhỏ |
| Acquire latency | Hàng đợi và timeout budget |
| Acquire timeout | Người dùng/job không lấy được connection |
| Connection creation rate | Pool churn, maxIdleTime/maxLifeTime, startup storm |
| Connection creation failure | Network, credentials, DB capacity, proxy |
| Hold duration | Result stream, transaction, cleanup chậm |

Tên meter phụ thuộc R2DBC Pool/Micrometer/Spring Boot version. Xác minh metric thực tế được export trước khi tạo dashboard/alert.

### 20.1. Kết hợp pool metrics với query và HTTP metrics

Ví dụ chẩn đoán:

| Quan sát | Khả năng cần điều tra |
|---|---|
| Active cao, pending cao, query duration cao | Query chậm hoặc database contention |
| Active cao, query execution thấp, HTTP stream duration cao | Downstream chậm hoặc result bị tiêu thụ lâu |
| Pending tăng ngay khi scale pod | Tổng connection demand/rollout surge vượt capacity |
| Acquire timeout tăng, DB connections đã chạm limit | Ngân sách toàn hệ thống hoặc pool quá lớn |
| Idle cao, creation rate liên tục cao | Pool churn, lifetime/idle policy hoặc traffic burst |
| Pool active thấp nhưng acquire timeout | Connection creation/network/validation hoặc metric chưa đúng |

Không kết luận chỉ từ một metric. Correlate theo thời gian, instance, pool và operation.

## 21. Alert cho pool capacity

Một số tín hiệu cảnh báo có thể gồm:

- Acquired gần max kéo dài.
- Pending acquire duy trì lớn hơn 0.
- Acquire latency p95/p99 vượt ngân sách.
- Acquire timeout tăng.
- Tổng connection trên database tiến gần giới hạn.
- Connection creation failures tăng.

Ví dụ rule minh họa:

```text
IF acquired_connections / max_connections > 0.90
AND pending_acquire > 0
FOR 5 minutes
THEN alert = R2DBC_POOL_SATURATED
```

Các ngưỡng 90% và 5 phút không phải mặc định chung. Điều chỉnh theo baseline, SLA, burst pattern và mức độ ảnh hưởng. Utilization cao đơn lẻ có thể chỉ là trạng thái pool đang được dùng hiệu quả; pending/acquire latency/timeout thể hiện saturation rõ hơn.

### 21.1. Alert theo tổng connection database

Theo dõi tổng session từ mọi application và service, không chỉ metric của một pool. Nếu database connection usage tiến gần server limit, cảnh báo cần nêu database endpoint và nguồn kết nối nếu có thể xác định.

Không dùng username động hoặc application instance ID làm label có cardinality không kiểm soát. Dùng service name, logical pool và environment.

## 22. Startup storm và warm-up khi scale out

Khi nhiều pod khởi động đồng thời, mỗi pod có thể tạo `initialSize` connection và sau đó tăng nhanh theo request. Một đợt rollout 20 pod với initial size 10 có thể tạo 200 connection gần như cùng lúc.

Các biện pháp:

- Đặt `initialSize` thấp hơn max size nếu workload cho phép.
- Giới hạn rollout surge và tốc độ rollout.
- Dùng startup/readiness logic phù hợp để không nhận traffic trước khi pool sẵn sàng.
- Tránh tất cả pod cùng reconnect sau sự cố database mà không có backoff.
- Theo dõi connection creation rate và authentication load.
- Cân nhắc jitter/eviction scheduling nếu pool hỗ trợ.

Không warm-up bằng cách mở toàn bộ maxSize trên mọi pod nếu chưa tính vào ngân sách. Warm-up phải là hành động có kiểm soát.

## 23. Graceful shutdown và connection lifecycle khi scale down

Khi pod bị dừng, pool cần đóng connection và các publisher đang chạy cần hoàn tất hoặc bị hủy theo shutdown policy. Cấu hình termination grace period và server shutdown timeout phải phù hợp với thời gian request tối đa.

Các điểm cần kiểm tra:

- Pod ngừng nhận request mới trước khi shutdown.
- Request đang chạy có đủ thời gian hoàn tất theo SLA không?
- Worker có dừng nhận job mới và checkpoint công việc không?
- Transaction được commit/rollback đúng khi cancellation/shutdown không?
- Pool được dispose và connection được đóng đúng lifecycle không?
- Pod mới có lên quá sớm làm tổng connection vượt ngân sách không?

Không dựa vào việc process bị kill để database tự cleanup ngay. Có thể có session tồn tại tới khi server phát hiện socket đóng hoặc timeout.

## 24. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chọn maxSize theo một pod | Tổng pool vượt DB limit khi scale | Nhân với peak replica và mọi pool |
| Dùng replica bình thường thay vì maxReplicas | Autoscaling làm cạn connection | Tính theo HPA max, surge và worker |
| Bỏ qua rolling deployment surge | Connection tăng tạm thời trong rollout | Tính peak overlap của pod cũ/mới |
| Cộng ngân sách từng service mà không reserve admin/other clients | DBA/migration không còn connection | Giữ reserved headroom và cộng mọi client |
| Chọn pool size theo số thread/CPU | Không phản ánh DB concurrency thực tế | Đo operation rate và connection hold time |
| Tăng pool khi DB đã bão hòa | Tăng contention và session overhead | Load test, tối ưu query và giới hạn concurrency |
| Chỉ tính một pool trong ứng dụng | Read/report/tenant pool bị bỏ sót | Cộng maxSize của mọi ConnectionFactory |
| Đặt initialSize bằng maxSize trên nhiều pod | Startup connection storm | Khởi tạo nhỏ và ramp-up có kiểm soát |
| Acquire timeout quá dài | Nhiều request chờ và latency dây chuyền | Đặt theo request deadline và xử lý overload |
| Acquire timeout quá ngắn | Fail fast dù burst ngắn có thể tự giải tỏa | Điều chỉnh theo SLA và phân phối wait time |
| Transaction dài hoặc stream chậm | Connection bị giữ lâu | Rút ngắn transaction, phân trang, export job |
| flatMap concurrency quá cao | Nhu cầu connection vượt pool | Giới hạn concurrency/bulkhead |
| Retry không giới hạn | Retry storm và pool saturation | Backoff, jitter, filter và deadline |
| Chỉ theo dõi utilization | Bỏ sót hàng đợi hoặc false positive | Kết hợp pending, acquire latency và timeout |
| Có PgBouncer nhưng chỉ tính backend connection | Proxy client limit bị vượt | Lập ngân sách cả client và server pool |
| Không đóng pool khi shutdown/test | Connection/resource tồn tại ngoài dự kiến | Dispose pool đúng lifecycle |

## 25. Quy trình tính và cấu hình pool

Khi triển khai một service mới hoặc thay đổi số replica, hãy đi theo trình tự:

1. **Xác định database limit:** lấy giới hạn server/proxy và capacity thực tế qua load test.
2. **Liệt kê mọi client:** API, worker, scheduled job, report, migration và service khác.
3. **Giữ reserved headroom:** admin, monitoring, failover, maintenance và workload bất ngờ.
4. **Tính service budget:** phần connection còn lại được cấp cho service.
5. **Tính peak replica:** HPA max, rolling surge, canary, blue-green và worker overlap.
6. **Cộng mọi pool:** primary/read/report/tenant/shard trên mỗi instance.
7. **Tính trần mỗi pool:** chia ngân sách theo peak instance và phân bổ vai trò.
8. **Ước lượng workload:** operation rate, concurrency, connection hold time, transaction và streaming.
9. **Load test nhiều cấu hình:** đo throughput, p95/p99, DB CPU/I/O, lock và pending acquire.
10. **Đặt giới hạn bổ sung:** `maxAcquireTime`, create timeout, idle/lifetime, page size và Reactor concurrency.
11. **Kiểm thử scale/rollout:** xác nhận tổng connection không vượt ngân sách khi pod tăng hoặc thay thế.
12. **Theo dõi và hiệu chỉnh:** review metrics sau khi traffic và số replica thay đổi.

## 26. Checklist tính toán minh họa

Một bảng tính capacity nên có ít nhất các trường sau:

| Trường | Giá trị cần điền |
|---|---|
| Database endpoint | Tên logical database/proxy |
| Server connection limit | Giới hạn từ DB/proxy |
| Reserved headroom | Admin, failover, monitoring, migration |
| Other client budget | Các service khác |
| Service budget | Phần còn lại cho service này |
| Deployment desired replicas | Replica bình thường |
| HPA max replicas | Replica tối đa theo autoscaling |
| Rollout surge/canary | Số instance overlap bổ sung |
| Worker/job replicas | Instance ngoài web deployment |
| Number of pools per instance | Số pool tới endpoint này |
| Max size per pool | Cấu hình dự kiến |
| Total peak connections | Tổng theo mọi instance/pool |
| Measured hold time | p50/p95/p99 nếu có |
| Peak DB operation concurrency | Đo trong load test |
| Acquire timeout/latency | Baseline và mục tiêu |
| Database CPU/I/O/lock | Capacity thực tế |

Tổng peak connection phải nhỏ hơn service budget sau khi tính tất cả pool và instance. Đồng thời, pool size phải được xác nhận qua hiệu năng database; đáp ứng phép tính connection limit chưa có nghĩa workload chạy tốt.

## 27. Nguyên tắc cần nhớ

- `maxSize` là giới hạn cho một pool trong một instance; tổng connection tăng theo số replica và số pool.
- Tính ngân sách từ database connection limit, giữ reserved headroom cho admin, failover, monitoring và client khác.
- Dùng số replica tối đa, HPA max, rolling surge, canary, blue-green và worker overlap.
- Với một pool đồng nhất, `maxSize mỗi instance <= service budget / peak instance count`.
- Cộng tất cả pool primary/read/report/tenant/shard theo đúng database endpoint.
- Không chọn pool size theo số thread, CPU hoặc HTTP request concurrency.
- Ước lượng nhu cầu bằng operation rate và connection hold time; dùng `L = λ × W` làm baseline, rồi xác nhận bằng load test.
- Theo dõi p95/p99 hold duration, transaction duration, pending acquire và acquire latency.
- Transaction dài, result stream chậm, `flatMap` concurrency cao và retry storm đều làm tăng connection occupancy.
- Pool lớn hơn không luôn tạo throughput cao hơn; quá nhiều session có thể làm database contention tăng.
- Đặt `initialSize` có kiểm soát để tránh startup/rollout connection storm.
- `maxAcquireTime` giới hạn thời gian chờ, không tạo thêm capacity; chọn theo request deadline.
- Phối hợp idle/lifetime policy với database/proxy timeout và connection rotation.
- Nếu dùng PgBouncer/proxy, lập ngân sách riêng cho client connections và backend connections.
- Giới hạn concurrency, page size và workload export để một nhóm request không chiếm hết pool.
- Theo dõi metrics ở cả application pool và database server; utilization cần đi cùng saturation và lỗi.
- Kiểm thử scale-out, rolling deployment, shutdown và tải thực tế trước khi nâng max replica hoặc pool size.

Tính giới hạn pool đúng là bài toán capacity toàn hệ thống. Hãy bắt đầu từ ngân sách connection mà database có thể dành cho service, chia theo số instance tối đa có thể cùng tồn tại và tổng của mọi pool, rồi so sánh với concurrency và thời gian giữ connection đo được. Cấu hình cuối cùng cần được xác nhận qua tải thử và theo dõi pending acquire, latency, database CPU/I/O cùng connection usage. Khi pool size, autoscaling, rollout surge và concurrency được thiết kế như một ngân sách chung, ứng dụng R2DBC có thể scale mà không vô tình nhân số connection vượt khả năng database.

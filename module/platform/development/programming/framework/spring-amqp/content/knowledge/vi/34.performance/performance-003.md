# Tăng consumer concurrency theo năng lực hệ thống phía sau

Trong hệ thống dùng **RabbitMQ và Spring AMQP**, queue tồn đọng thường khiến ta nghĩ ngay: “Tăng số consumer lên là xử lý nhanh hơn”. Điều này chỉ đúng khi các consumer hiện tại **chưa khai thác hết năng lực xử lý** của ứng dụng và những hệ thống phía sau, chẳng hạn database, HTTP API, cache hoặc dịch vụ thanh toán. Nếu bottleneck là connection pool của PostgreSQL hoặc giới hạn request/giây của API đích, tăng consumer từ 8 lên 40 có thể khiến **throughput không tăng nhưng timeout, retry, redelivery và backlog tăng mạnh**.

Bài thuộc chương **Hiệu năng** của module **SPRING_AMQP**. Ta sẽ thực hành kết nối RabbitMQ bằng `RabbitTemplate` và `@RabbitListener`, hiểu exchange–queue–binding, phân biệt **consumer concurrency** với **prefetch**, tính ngân sách tài nguyên phía sau, đo throughput và độ trễ, rồi kết hợp publisher confirms, ACK sau commit, retry, dead-letter và quan sát hệ thống để xây luồng bất đồng bộ vừa nhanh vừa đáng tin cậy.

> **Nguyên tắc cốt lõi:** tăng consumer concurrency là **phân bổ thêm công việc đồng thời**. Nó **không tạo thêm** CPU, database connections, IOPS hay quota của hệ thống phụ thuộc. Giá trị concurrency đúng là giá trị có thể duy trì **tốc độ commit nghiệp vụ** trong SLO mà không làm downstream quá tải.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích quan hệ giữa số consumer, tốc độ vào queue, thời gian xử lý message và năng lực của downstream.
2. Phân biệt **concurrency**, **prefetch**, **số replica**, **channel**, **message đang xử lý** và **message chưa ACK**.
3. Cấu hình concurrency cố định hoặc co giãn của `SimpleMessageListenerContainer`, đồng thời hiểu điểm khác với `DirectMessageListenerContainer`.
4. Ước lượng giới hạn concurrency từ **DB connection pool**, **HTTP rate limit**, **thread pool**, CPU, bộ nhớ và tài nguyên broker.
5. Thiết kế benchmark tăng concurrency từng nấc dựa trên **throughput thành công, p95/p99 latency, error rate và queue age**.
6. Nhận biết thời điểm thêm consumer không còn hiệu quả, thậm chí gây retry storm và thông lượng suy giảm.
7. Giữ đúng ngữ nghĩa ACK, transaction, idempotency và retry/DLQ trong lúc scale.
8. Xây dashboard, runbook và kế hoạch rollback khi consumer tăng làm hệ thống phía sau chịu tải quá mức.

## 2. Bức tranh hệ thống: một queue, nhiều consumer, một downstream hữu hạn

Giả sử Order Service publish `OrderPaid` vào `orders.events.exchange` với routing key `order.paid`. RabbitMQ dùng binding đưa message vào `billing.order-paid.queue`. Các `@RabbitListener` xử lý message, sau đó gọi Billing API và cập nhật database.

~~~mermaid
flowchart LR
    P["Order Service<br/>RabbitTemplate"] --> E["Exchange orders.events.exchange"]
    E -->|"order.paid / binding"| Q["Queue billing.order-paid.queue"]
    Q --> C1["Consumer 1"]
    Q --> C2["Consumer 2"]
    Q --> C3["Consumer 3"]
    Q --> CN["Consumer N"]
    C1 --> API["Billing API<br/>quota hữu hạn"]
    C2 --> API
    C3 --> API
    CN --> API
    API --> DB["Billing DB<br/>pool / IOPS hữu hạn"]
~~~

Nếu mỗi consumer chạy một handler đồng bộ, concurrency `C` xấp xỉ số **listener worker có thể thực hiện một xử lý tại cùng thời điểm**. Khi tăng `C`:

- Có nhiều message được lấy ra và xử lý song song hơn.
- Tải đồng thời lên database/API tăng.
- Tổng connection, thread, memory và message unacked có thể tăng.
- Thứ tự hoàn tất message khó dự đoán hơn.
- Khả năng duplicate hoặc retry khi downstream quá tải có thể tăng.

**Tăng consumer không làm producer hoặc exchange định tuyến nhanh hơn một cách tự động.** Nếu hạn chế nằm ở tốc độ publish, topology, queue leader, network hay broker resource alarm, phải xử lý bottleneck đó trước.

### 2.1. Phân biệt các đơn vị song song

| Khái niệm | Ý nghĩa | Có luôn làm tăng business throughput? |
| --- | --- | --- |
| **Consumer concurrency** | Số consumer có thể nhận/xử lý delivery đồng thời | Không, nếu downstream đã bão hòa |
| **Prefetch** | Ngân sách delivery chưa ACK được broker cấp cho consumer | Không, tăng prefetch chủ yếu tăng số delivery ở trạng thái in-flight |
| **Số replica** | Số process/pod ứng dụng | Có thể tăng tổng consumer và tổng kết nối tới DB/API |
| **RabbitMQ channel** | Đường AMQP logic trong connection | Không đồng nghĩa một business worker độc lập |
| **Unacked messages** | Delivery broker chưa nhận ACK | Không đồng nghĩa đang chạy CPU; có thể bị giữ chờ xử lý |
| **Active DB connection** | Connection được mượn và đang dùng | Là tài nguyên hữu hạn, có thể trở thành bottleneck |
| **HTTP in-flight requests** | Request đang chờ kết quả từ dịch vụ đích | Bị giới hạn bởi quota, pool và độ trễ |

Cần đọc từng metric đúng phạm vi. Một queue có 2.000 unacked không chứng minh có 2.000 transaction thực sự đang chạy; phần lớn có thể chỉ **được prefetch rồi nằm chờ trong client**.

## 3. Vì sao concurrency tăng không tuyến tính?

Tốc độ xử lý tối đa lý tưởng của `C` worker đồng bộ, mỗi worker mất trung bình `W` giây cho một message, có thể ước lượng:

\[
\mu_{\text{worker}} \approx \frac{C}{W}
\]

Ví dụ `C=4` và thời gian xử lý trung bình `W=0{,}2\ \text{s}`, năng lực lý tưởng khoảng `20 message/s`. Tăng lên `C=8` có thể nâng gần `40 message/s` **nếu W không đổi** và downstream còn dư năng lực.

Nhưng khi quá nhiều consumer cùng gọi DB, thời gian xử lý có thể tăng. Giả sử:

| Consumer đồng thời | W trung bình quan sát | Tốc độ lý tưởng theo C/W |
| ---: | ---: | ---: |
| 2 | 0,20 s | 10 msg/s |
| 4 | 0,20 s | 20 msg/s |
| 8 | 0,23 s | ~35 msg/s |
| 12 | 0,40 s | 30 msg/s |
| 20 | 1,10 s | ~18 msg/s |

Các số liệu **minh họa một thí nghiệm**, không phải đặc tính cố định của Spring AMQP. Từ `C=8` lên `C=20`, throughput lại giảm vì `W` tăng mạnh, chẳng hạn do pool contention, database lock hay API throttling.

**Tăng concurrency chỉ đáng giá khi tốc độ hoàn thành nghiệp vụ tăng ổn định mà thời gian xử lý, timeout và retry vẫn trong giới hạn.**

### 3.1. Luồng vào queue cũng quan trọng

Gọi:

- `λ`: tốc độ message hợp lệ **đến queue** (message/s).
- `μ`: tốc độ message được **xử lý và hoàn tất** (message/s).
- `B`: số message ready đang tồn đọng.

Mô hình gần đúng:

\[
\frac{dB}{dt} \approx \lambda-\mu
\]

Nếu `λ=150/s` và `μ=120/s`, queue tăng khoảng `30 message/s` hay `1.800 message/phút`. Tăng consumer chỉ hữu ích nếu có thể nâng `μ` bằng cách dùng capacity **còn dư** của downstream.

Nếu downstream chịu tối đa `140/s` ổn định, việc cố tăng tới `250/s` có thể làm timeout và retry, khiến `μ` thực tế còn thấp hơn `140/s`.

### 3.2. Thời gian xả backlog

Nếu input và tốc độ hoàn thành ổn định, `μ>λ`:

\[
T_{\text{drain}}\approx \frac{B}{\mu-\lambda}
\]

Với `B=6.000`, `λ=100/s`, `μ=160/s` thì ước lượng lý tưởng là **100 giây**. Không nên dùng công thức này như SLA cứng: retries, message sizes khác nhau, network jitter, variation trong DB và lệch phân phối làm kết quả thực khác mô hình.

## 4. Dùng Little's Law để ước lượng số xử lý đồng thời

Theo quan hệ Little trong điều kiện hệ thống đủ ổn định:

\[
L \approx \lambda_{\text{completed}}\times W
\]

Trong đó:

- `L`: số công việc đồng thời trung bình đang được xử lý.
- `λ_completed`: throughput hoàn tất trung bình.
- `W`: thời gian một công việc ở vùng xử lý đó.

Ví dụ muốn xử lý `100 message/s`, một handler đồng bộ mất trung bình `0{,}15s`. Nhu cầu đồng thời trung bình lý tưởng:

\[
L \approx 100\times0{,}15=15
\]

Vì có dao động thời gian, nên **không nên chọn chính xác 15 rồi tuyên bố đã đạt 100/s**. Cần đo p95/p99, jitter, connection contention và thêm headroom. Quan trọng hơn, **downstream phải chịu được 100/s**. Little's Law không tạo capacity mới.

### 4.1. Mean và p95/p99 không thay thế nhau

- **Mean latency** hữu ích để ước lượng đồng thời trung bình.
- **p95/p99** giúp kiểm tra tail latency, timeout và khả năng xuất hiện queueing.
- Chỉ dùng `C / p95` làm throughput tối đa thường quá bi quan; chỉ dùng `C / mean` làm SLA lại quá lạc quan.
- Benchmark cần đo cả **business commit rate** và độ trễ phân vị dưới tải thật.

Nếu handler gọi Billing API mất p99 3 giây nhưng median 100 ms, một vài yêu cầu rất chậm có thể giữ consumer lâu và làm giảm công suất. Có thể giải quyết bằng timeout hợp lý, circuit breaker, retry có delay hoặc tách xử lý dài sang workflow riêng, thay vì chỉ tăng số consumer.

## 5. Xác định bottleneck trước khi tăng concurrency

Một consumer handler có thể qua nhiều giai đoạn:

~~~mermaid
flowchart LR
    A["Nhận delivery"] --> B["Deserialize / validate"]
    B --> C["DB read/write"]
    C --> D["HTTP downstream"]
    D --> E["DB commit"]
    E --> F["Container ACK"]
~~~

Đo từng giai đoạn để biết thời gian nằm ở đâu.

| Tín hiệu | Bottleneck có thể | Kiểm tra tiếp |
| --- | --- | --- |
| CPU app 90–100%, GC pressure | CPU-bound serialization/computation | Profiling, heap, CPU quotas, cores |
| Hikari pending connections tăng | DB pool thiếu hoặc query giữ connection lâu | DB active/idle/pending, SQL latency |
| DB CPU/IOPS/locks cao | DB đã bão hòa | Query plan, indexes, transaction duration, locks |
| HTTP 429/503 hoặc timeout tăng | Quota hoặc downstream quá tải | HTTP rate, in-flight, breaker, rate limit |
| RabbitMQ resource alarm, publisher blocked | Broker memory/disk pressure | Node alarms, disk, memory, queue bytes |
| Unacked tăng, ACK rate không tăng | Handler chậm, prefetch quá cao, quên ACK | Listener traces, prefetch, ACK mode |
| Ready tăng nhưng consumer count=0 | Consumer không tồn tại | Container startup, vhost, permissions |
| Delivery rate cao, commit rate thấp | Retry/requeue/poison loop | Redelivery, DLQ, exception classes |

Điểm tối ưu **không nhất thiết là tăng concurrency**. Có khi tối ưu SQL hoặc giảm N+1 query làm `W` giảm một nửa, đồng nghĩa tăng throughput mà không tạo thêm connection.

## 6. Các giới hạn của downstream phải được tính theo *tổng* instance

Ứng dụng chạy nhiều pod. Một cấu hình `concurrency=10` thường được hiểu là **10 consumer trong mỗi instance** đối với queue/listener tương ứng, không phải 10 consumer của toàn deployment.

Nếu có `N` pod và mỗi pod có `C` consumer cùng đọc một queue:

\[
C_{\text{total}}\approx N\times C
\]

Ví dụ 4 pod, mỗi pod cấu hình 8 consumer ⇒ khoảng **32 consumer đồng thời**. Tăng lên 12 consumer/pod tạo tối đa **48 worker**, và các worker này có thể cùng gọi một database/API.

Cần phân biệt **số consumer được tạo**, **số đang làm việc thực tế** và **số resource lease đồng thời**. Một consumer có thể xử lý JSON mà chưa lấy DB connection; một handler khác có thể giữ DB connection trong lúc chờ HTTP. Đo pool usage thực thay vì mặc định 1 consumer luôn chiếm đúng 1 connection suốt toàn bộ thời gian.

### 6.1. Ngân sách DB connection

Giả sử:

- Database cho phép tối đa `80` connection.
- Dành `20` cho admin, migration, API trực tiếp và headroom.
- Ba replica cùng sử dụng database.
- Mỗi message đồng thời có thể giữ tối đa **một** DB connection trong phần transaction.

Ngân sách lý thuyết cho mỗi replica:

\[
C_{\text{DB,pod}} \lesssim
\left\lfloor \frac{80-20}{3}\right\rfloor = 20
\]

Đây **không phải đề xuất đặt ngay concurrency=20**. Hikari pool, API traffic cùng JVM, thời gian giao dịch, spike và các tác vụ khác có thể cần giới hạn thấp hơn, chẳng hạn 8–12 để dành headroom.

Nếu mỗi pod đặt `spring.datasource.hikari.maximum-pool-size=12`, tổng pool tối đa của ba pod là **36 connections**. Concurrency vượt 12/pod có thể vẫn chạy nếu không phải worker nào cũng dùng DB cùng lúc; nhưng khi mọi worker đồng loạt vào transaction, sẽ có thread **đợi connection**, tăng thời gian xử lý và giảm tốc độ ACK.

### 6.2. Ngân sách HTTP API phía sau

Giả sử Billing API chịu ổn định **120 request/s** và mỗi message tạo **một** request. Với ba pod, phần quota công bằng khoảng `40 req/s/pod`. Nếu thời gian HTTP trung bình `0{,}25s`:

\[
C_{\text{HTTP,pod}}\approx40\times0{,}25=10
\]

Nếu consumer chỉ làm việc gọi HTTP đồng bộ, mức đồng thời khoảng 10/pod có thể đã đủ dùng quota; nâng lên 30/pod không biến API thành 360 req/s. Tại tải cao, API bắt đầu trả 429, latency tăng, retry làm áp lực thêm.

Nên có **client-side rate limiter/bulkhead** và timeout. Một con số concurrency theo pod còn phải tính các client cùng dùng API từ dịch vụ khác; không nên chiếm hết quota của tổ chức.

### 6.3. Capacity không chỉ là DB và HTTP

| Tài nguyên | Giới hạn đo được | Tác động khi vượt |
| --- | --- | --- |
| CPU cores/container quota | CPU utilization, throttling | Handler và GC chậm, tail latency tăng |
| Memory/heap | GC pause, object allocation, unacked body bytes | OOM, reconnect, redelivery |
| DB pool | Active/idle/pending, acquisition timeout | Thread đứng chờ, transaction kéo dài |
| DB server | CPU, IOPS, WAL, locks | Query chậm và deadlock |
| HTTP pool | Max connections, pending acquire | Chờ socket, timeout |
| HTTP quota | 429, rate-limit headers, contract | Lỗi tạm thời và retry storm |
| Thread pool | Active, queue, rejected tasks | Listener kẹt hoặc tăng queue nội bộ |
| RabbitMQ | Queue throughput, connections/channels, alarms | Broker block publish hoặc consumer lag |
| External payment service | Request quota, idempotency contract | Side effect trùng hoặc bị throttled |

**Concurrency hợp lý là điểm thấp nhất của những ngưỡng đang ràng buộc luồng**, có dự phòng cho dao động và failure recovery.

## 7. Phân biệt concurrency với prefetch trong RabbitMQ

`prefetch` giới hạn số delivery chưa ACK broker gửi cho consumer trước khi cần ACK tiếp theo, theo semantics RabbitMQ/AMQP 0-9-1. Trong cách dùng RabbitMQ phổ biến, QoS được áp dụng theo **consumer**; phải kiểm tra version/container nếu có cấu hình QoS khác.

Ví dụ:

- 4 consumer; `prefetch=20`.
- Broker có thể giao tổng khoảng **80 message chưa ACK** cho bốn consumer.
- Nhưng nếu mỗi consumer xử lý **một message đồng bộ tại một thời điểm**, chỉ khoảng bốn business handler đang chạy đồng thời.

Những message còn lại có thể đang được giữ ở phía client, không còn ở trạng thái ready tại broker.

### 7.1. Vì sao prefetch quá lớn làm quan sát khó?

Với `C_total=40` và `prefetch=100`, có thể có hàng nghìn delivery **unacked** dù ứng dụng chỉ xử lý 40 message đồng thời. Hệ quả:

- Thêm memory ở client/broker để theo dõi delivery.
- Message có thể bị phân phối thiếu công bằng cho consumer xử lý chậm.
- Khi pod crash, số delivery phải redeliver lớn.
- Queue ready giảm mạnh, khiến dashboard đánh giá quá lạc quan.
- Khi ACK theo batch, lỗi có thể ảnh hưởng nhiều delivery cùng chu kỳ.

**Prefetch không phải “số worker”.** Nếu mục tiêu là tăng tốc gọi API/DB, tăng prefetch từ 20 lên 1.000 không tạo thêm handler chạy song song.

### 7.2. Cách chọn prefetch thực dụng

- Bắt đầu bằng một giá trị vừa phải, chẳng hạn `10–30`, khi message đồng kích thước và handler đồng bộ; đây chỉ là **điểm bắt đầu thử nghiệm**.
- Nếu message nặng, yêu cầu latency thấp hoặc memory giới hạn, thử prefetch thấp hơn.
- Nếu handler cực nhanh, round-trip ACK là giới hạn thực sự, prefetch có thể cần tăng nhưng phải đo.
- Với giao dịch cần thứ tự nghiêm ngặt hoặc in-flight thấp, `prefetch=1` có thể thích hợp.
- Kiểm tra `messages_unacked`, unfair distribution, redelivery và handler time khi thay đổi.

Đừng gắn một con số “tối ưu toàn cục”. Giá trị đúng phụ thuộc message size, batch handling, network latency, loại queue, concurrency và nhu cầu ordering.

## 8. Spring AMQP có hai kiểu listener container phổ biến

### 8.1. `SimpleMessageListenerContainer` (SMLC)

SMLC có các thông số:

- `concurrentConsumers`: số consumer tối thiểu cần duy trì.
- `maxConcurrentConsumers`: số consumer tối đa khi dùng co giãn tự động.
- `prefetchCount`: số delivery chưa ACK được cấp cho mỗi consumer theo cấu hình.
- Các khoảng trigger/min interval giúp SMLC tăng/giảm consumer dựa trên **mức độ hoạt động của consumer**.

Nếu min bằng max, số consumer mục tiêu gần như cố định. Nếu min thấp hơn max, SMLC có thể điều chỉnh số consumer trong khoảng đó khi có tải/idle. **Thuật toán này không biết database của bạn đã quá tải hay chưa.** Nó đánh giá hoạt động của consumer, không phải một autoscaler theo p95 DB latency.

### 8.2. `DirectMessageListenerContainer` (DMLC)

DMLC kết nối mô hình consumer và delivery callbacks theo cách khác SMLC; thông số thường dùng là:

- `consumersPerQueue`: số consumer trên từng queue.
- `prefetchCount` và các thành phần connection/executor tương ứng.

Không chép trực tiếp logic `concurrentConsumers/maxConcurrentConsumers` của SMLC sang DMLC. DMLC phù hợp một số mô hình có nhiều queue, nhưng số thread/callback và khả năng tiêu thụ phải được đo theo workload; **consumersPerQueue** nhân với số queue liên quan có thể tạo nhiều consumer hơn dự kiến.

### 8.3. So sánh

| Khía cạnh | SMLC | DMLC |
| --- | --- | --- |
| Cấu hình concurrency cơ bản | `concurrentConsumers`, `maxConcurrentConsumers` | `consumersPerQueue` |
| Co giãn container | Có trigger hoạt động/idle trong khoảng min–max | Không dùng cùng cơ chế min–max của SMLC |
| Số queue lớn | Cần xem thread/consumer/monitoring overhead | Có thể phù hợp hơn trong một số mô hình đa queue |
| Prefetch | Có | Có |
| ACK, retry/DLQ | Được cấu hình qua listener và error handling | Tương tự về mục tiêu, khác lifecycle nội bộ |
| Chọn loại nào | Dựa trên workload và khả năng đo/điều chỉnh | Không mặc định “Direct luôn nhanh hơn” |

Trong bài này, phần code chính dùng **SMLC** vì cung cấp cả concurrency tối thiểu và tối đa để thực hành tăng tải có kiểm soát.

## 9. Cấu hình concurrency bằng Spring Boot

Khi sử dụng Spring Boot 3.x với `spring-boot-starter-amqp` và SMLC, có thể bắt đầu bằng một cấu hình có giới hạn:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    virtual-host: /orders
    requested-heartbeat: 30s
    connection-timeout: 5s

    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true

    listener:
      type: simple
      simple:
        concurrency: 2
        max-concurrency: 8
        prefetch: 20
        acknowledge-mode: auto
        default-requeue-rejected: false

  datasource:
    hikari:
      maximum-pool-size: 12
      connection-timeout: 2s
~~~

Ý nghĩa:

- Mỗi instance khởi đầu với khoảng **2 consumer** cho listener factory phù hợp, có thể tăng tối đa **8 consumer** khi container nhận thấy đủ hoạt động.
- Mỗi consumer có giới hạn prefetch 20: khi đạt 8 consumer, tổng unacked ngân sách có thể lên khoảng **160 delivery/instance**, không phải 160 business handler chạy đồng thời.
- Pool DB tối đa 12 connection/instance. Đây **không** có nghĩa có thể dành trọn 12 connection cho listener nếu HTTP controller hoặc job trong JVM cũng dùng DB.
- `default-requeue-rejected: false` giúp tránh vòng requeue vô hạn đối với exception đã được container xử lý thành reject, khi có DLX phù hợp; nó không thay thế phân loại lỗi và retry budget.

**Chú ý:** khi đã khai báo một custom `SimpleRabbitListenerContainerFactory` hoặc cấu hình concurrency ngay ở `@RabbitListener`, cần xác minh property nào thực sự áp dụng cho listener đó. Không giả định Spring Boot tự nhân mọi cấu hình YAML sang các factory do ứng dụng tạo thủ công.

### 9.1. Muốn concurrency cố định thì sao?

Nếu benchmark chứng minh 4 consumer/instance là mức ổn định, có thể đặt:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        concurrency: 4
        max-concurrency: 4
        prefetch: 10
~~~

Việc khóa min=max hữu ích khi:

- Downstream có quota nghiêm ngặt và muốn tránh container tự tăng số consumer.
- Tải ổn định, capacity đã được kiểm chứng.
- Cần kiểm soát số handler đồng thời cho mỗi deployment.
- Autoscaling ở cấp pod đã quản lý tổng consumer, không muốn thêm một vòng co giãn cùng lúc.

Không chọn concurrency cố định cao hơn capacity chỉ để giảm backlog trên dashboard.

### 9.2. DMLC dùng thông số khác

Nếu lựa chọn direct listener container:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: direct
      direct:
        consumers-per-queue: 3
        prefetch: 20
        acknowledge-mode: auto
~~~

`consumers-per-queue` áp dụng **theo mỗi queue** có liên quan. Ví dụ một listener DMLC xử lý 10 queue, đặt 3 có thể tạo nhiều consumer hơn ý định “tổng 3”. Cần kiểm tra tổng consumer/channel/thread và khả năng downstream thực tế.

## 10. Java configuration với giới hạn concurrency và retry hữu hạn

Một factory rõ ràng giúp bài lab kiểm soát các giá trị thay vì dựa vào mặc định:

~~~java
package com.example.amqp.performance;

import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ConsumerPerformanceConfig {

    @Bean
    Jackson2JsonMessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean("billingListenerFactory")
    SimpleRabbitListenerContainerFactory billingListenerFactory(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter jsonMessageConverter) {

        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(jsonMessageConverter);

        // Số consumer có thể thay đổi trong khoảng 2..8.
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(8);
        factory.setPrefetchCount(20);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);

        // Retry xử lý message khác với retry mở connection.
        factory.setAdviceChain(
                RetryInterceptorBuilder.stateless()
                        .maxAttempts(3)
                        .backOffOptions(300L, 2.0, 1_200L)
                        .recoverer(new RejectAndDontRequeueRecoverer())
                        .build());

        factory.setDefaultRequeueRejected(false);
        return factory;
    }
}
~~~

Trong ví dụ, `maxAttempts(3)` tính cả lần thử đầu; retry in-process giữ consumer thread làm việc và **có thể làm giảm throughput** khi downstream lỗi. Một giải pháp thay thế cho backoff dài là reject/route sang **delay retry queue** hoặc scheduler có budget, sau đó chuyển sang DLQ khi hết số lần thử.

Việc tăng `maxConcurrentConsumers` không tự bảo đảm SMLC lập tức tăng lên số tối đa. Cơ chế co giãn xem xét **độ hoạt động và khoảng chờ min/trigger**, không chỉ nhìn `messages_ready`. Nếu cần concurrency ổn định để benchmark, khóa min và max ở từng nấc thử.

### 10.1. Khi nào tránh dynamic concurrency của SMLC?

- Khi DB chỉ cho phép một số transaction đồng thời rất rõ.
- Khi downstream latency tăng mạnh mỗi lúc nhiều request cùng đến.
- Khi đồng thời có Horizontal Pod Autoscaler: hai vòng scale độc lập có thể nhân tổng consumer vượt ngân sách.
- Khi muốn kết quả load test dễ so sánh giữa các nấc `C=2,4,6,8`.
- Khi có giới hạn rate của đối tác, dynamic concurrency không thay thế rate limiter.

Dynamic scale hữu ích khi workload biến động và downstream còn dư capacity, nhưng vẫn cần **giới hạn `maxConcurrentConsumers` dựa trên tải thật**.

## 11. Topology và listener minh họa

Bài lab dùng một direct exchange, work queue durable và terminal DLQ. Mục tiêu không phải thêm thật nhiều consumer lên cùng một queue một cách vô điều kiện, mà tạo đường đi có thể **kiểm chứng publish, xử lý, ACK và xử lý lỗi**.

### 11.1. Exchange, queue, binding và DLX

~~~java
package com.example.amqp.performance;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BillingTopology {

    public static final String EXCHANGE = "orders.events.exchange";
    public static final String KEY = "order.paid";
    public static final String WORK_QUEUE = "billing.order-paid.queue";
    public static final String DLX = "billing.errors.exchange";
    public static final String DLQ = "billing.order-paid.dlq";

    @Bean
    DirectExchange ordersEventsExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue billingWorkQueue() {
        return QueueBuilder.durable(WORK_QUEUE)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey("order.failed")
                .build();
    }

    @Bean
    Binding billingWorkBinding() {
        return BindingBuilder.bind(billingWorkQueue())
                .to(ordersEventsExchange())
                .with(KEY);
    }

    @Bean
    DirectExchange billingErrorsExchange() {
        return new DirectExchange(DLX, true, false);
    }

    @Bean
    Queue billingDlq() {
        // Terminal DLQ, không đưa thẳng về queue nguồn.
        return QueueBuilder.durable(DLQ).build();
    }

    @Bean
    Binding billingDlqBinding() {
        return BindingBuilder.bind(billingDlq())
                .to(billingErrorsExchange())
                .with("order.failed");
    }
}
~~~

Mỗi tên queue/exchange và binding phải được `RabbitAdmin` khai báo phù hợp với virtual host/broker đang dùng, hoặc provision bởi hệ thống bên ngoài. Nếu queue production đã tồn tại với arguments khác, redeclare có thể báo `PRECONDITION_FAILED`; không đổi topology trong khi làm load test mà không có kế hoạch.

### 11.2. DTO có ID ổn định để chống trùng

~~~java
package com.example.amqp.performance;

import java.time.Instant;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        String orderId,
        long version,
        Instant occurredAt
) {}
~~~

ID nghiệp vụ phải tồn tại xuyên **publish retry**, **consumer redelivery** và **DLQ replay**. Đừng dùng RabbitMQ delivery tag làm ID vì delivery tag có phạm vi channel và thay đổi khi connection/channel được tạo lại.

### 11.3. Listener đồng bộ, commit rồi return

~~~java
package com.example.amqp.performance;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BillingOrderPaidListener {

    private final IdempotentBillingService service;

    public BillingOrderPaidListener(IdempotentBillingService service) {
        this.service = service;
    }

    @RabbitListener(
            id = "billingOrderPaidListener",
            queues = BillingTopology.WORK_QUEUE,
            containerFactory = "billingListenerFactory")
    public void onOrderPaid(OrderPaid event) {
        service.applyOnce(event);
        // Không return trước khi transaction nghiệp vụ commit.
    }
}
~~~

Với `AcknowledgeMode.AUTO`, listener container sẽ ACK sau khi listener xử lý thành công theo cơ chế của container. Đây **không phải** RabbitMQ `autoAck=true` vô điều kiện. Nếu listener chỉ gửi nhiệm vụ sang `ExecutorService` rồi return, container có thể ACK **trước khi tác vụ thực sự thành công**.

Cần ghi nhớ: ACK sau commit vẫn có cửa sổ **DB commit thành công nhưng ACK chưa tới broker**, dẫn đến redelivery. Concurrency lớn khiến một event bị xử lý trùng hoặc cùng `orderId` được xử lý song song dễ xảy ra hơn; cần idempotency và quy tắc xử lý thứ tự.

## 12. Ví dụ bảo vệ database bằng transaction và idempotency

Một bảng marker với unique constraint có thể đảm bảo duplicate không thực hiện side effect lần nữa:

~~~sql
CREATE TABLE processed_order_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE billing_projection (
    order_id VARCHAR(80) PRIMARY KEY,
    order_version BIGINT NOT NULL,
    paid BOOLEAN NOT NULL
);
~~~

Ví dụ dùng Spring JDBC/PostgreSQL:

~~~java
package com.example.amqp.performance;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IdempotentBillingService {

    private final JdbcTemplate jdbc;

    public IdempotentBillingService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce(OrderPaid event) {
        int marker = jdbc.update("""
                INSERT INTO processed_order_events(
                    consumer_name, event_id
                )
                VALUES (?, ?)
                ON CONFLICT DO NOTHING
                """, "billing-projection", event.eventId());

        if (marker == 0) {
            // Message trùng: không chạy side effect lần hai.
            return;
        }

        jdbc.update("""
                INSERT INTO billing_projection(
                    order_id, order_version, paid
                )
                VALUES (?, ?, TRUE)
                ON CONFLICT (order_id) DO UPDATE
                    SET order_version = EXCLUDED.order_version,
                        paid = EXCLUDED.paid
                WHERE billing_projection.order_version
                    < EXCLUDED.order_version
                """, event.orderId(), event.version());
    }
}
~~~

Marker và cập nhật projection nằm trong **cùng DB transaction**. Nếu phần cập nhật ném exception, transaction phải rollback cả marker, để redelivery có cơ hội xử lý lại. `@Transactional` cần được Spring proxy áp dụng đúng; không gọi self-invocation làm bỏ qua transaction.

**Điểm quan trọng về concurrency:** hai event của **cùng order** có thể đến hoặc hoàn tất không theo thứ tự. Ví dụ projection sử dụng `order_version` để không ghi đè dữ liệu mới bằng event cũ. Nếu nghiệp vụ bắt buộc xử lý **mọi phiên bản tuần tự** (không chỉ trạng thái mới nhất), version guard đơn giản chưa đủ; cần partitioning theo key, sequencing hoặc workflow phát hiện gap.

### 12.1. Đừng giữ DB transaction trong lúc gọi HTTP chậm nếu tránh được

Một anti-pattern:

~~~java
@Transactional
public void process(OrderPaid event) {
    repository.saveSomething(event);
    billingApi.callRemote(); // Có thể treo vài giây.
    repository.updateAgain(event);
}
~~~

Khi giữ transaction/connection qua HTTP call, thêm consumer có thể đẩy Hikari pool vào trạng thái chờ, tăng lock contention và làm throughput sụp đổ. Có thể thiết kế thành:

1. **Local transaction** lưu trạng thái công việc/inbox và outbox của bước tiếp.
2. **Worker/relay** gọi HTTP bên ngoài transaction database dài.
3. **Ghi trạng thái kết quả** bằng transaction ngắn.
4. Dùng **idempotency key** ở API đích và cơ chế reconciliation khi HTTP outcome không chắc chắn.

Không giả định mọi workflow có thể cắt nhỏ một cách nguyên tử. Với tác vụ quan trọng như thanh toán, cần hợp đồng nghiệp vụ về trạng thái và bù trừ, không chỉ đổi annotation.

## 13. Ngân sách tổng khi vừa tăng pod vừa tăng concurrency

Nếu deployment sử dụng autoscaling:

~~~text
Replica count × consumers per replica
        ↓
Số listener đồng thời
        ↓
DB connections / HTTP requests / CPU load
~~~

Ví dụ:

| Giai đoạn | Replicas | Consumer mỗi replica | Tổng consumer |
| --- | ---: | ---: | ---: |
| Baseline | 2 | 4 | 8 |
| Chỉ tăng consumer | 2 | 8 | 16 |
| Chỉ tăng replicas | 4 | 4 | 16 |
| Tăng cả hai | 4 | 8 | 32 |
| HPA đột ngột lên 8 pods | 8 | 8 | 64 |

Nếu quota API chỉ chịu 20 request đồng thời và chưa có bulkhead toàn hệ thống, giai đoạn cuối có thể gây 429/timeout hàng loạt. **Hai chiều scale không độc lập về tác động**, dù có thể được cấu hình độc lập.

### 13.1. Công thức ngân sách thực dụng

Giả sử:

- `R` là số replica tối đa có thể có trong một đợt autoscaling.
- `C` là mức consumer tối đa mỗi replica.
- `D_db` là ngân sách DB connection dành riêng cho workload.
- `q_db` là số DB connection đồng thời tối đa mà một business handler có thể nắm giữ trong tình huống cần bảo vệ.

Một giới hạn bảo thủ:

\[
R\times C\times q_{\mathrm{db}}\le D_{\mathrm{db}}
\]

Đây là **bound thiết kế**, không phải mô hình chính xác cho mọi code path. Nếu handler lấy/nhả DB connection từng đoạn, mức dùng thực có thể thấp hơn; nhưng nếu nhiều handler đồng loạt vào DB, bound giúp tránh oversubscription nghiêm trọng.

Với HTTP API, nếu mỗi message sinh một request, nên giới hạn **tốc độ gọi** và **số request in-flight** độc lập với concurrency. Rate limit `120 req/s` không thể được giải quyết bằng việc tạo 64 listener; phải kiểm soát rate/retry.

### 13.2. Bulkhead và rate limiting

Bulkhead là giới hạn số thao tác đồng thời tới một dependency, giúp bảo vệ hệ thống phía sau khi tổng listener tăng. Có thể dùng `Semaphore`, bounded HTTP connection pool hoặc thư viện resilience có bulkhead/rate limiter.

Ví dụ **chỉ minh họa một bulkhead cục bộ theo process**:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class BillingApiBulkhead {

    private final Semaphore permits = new Semaphore(8);
    private final BillingApi api;

    public BillingApiBulkhead(BillingApi api) {
        this.api = api;
    }

    public void call(String orderId, String idempotencyKey)
            throws InterruptedException {

        if (!permits.tryAcquire(500, TimeUnit.MILLISECONDS)) {
            throw new DownstreamBusyException(
                    "Billing API in-flight limit reached");
        }

        try {
            api.submit(orderId, idempotencyKey);
        } finally {
            permits.release();
        }
    }
}
~~~

`BillingApi` và `DownstreamBusyException` là interface/exception ứng dụng cần định nghĩa. Đây là **limit theo JVM**, không phải quota phân tán: 4 pods × 8 permit cho phép tối đa **32 request in-flight**. Nếu API có quota toàn hệ thống, phải điều chỉnh theo replica tối đa hoặc dùng rate limiter phân tán phù hợp.

Không chặn vô hạn trong listener chờ semaphore: nó giữ consumer thread, làm unacked tăng và có thể gây timeout. Timeout hoặc từ chối có kiểm soát cần đi vào **retry có backoff**/delay queue chứ không busy-loop.

## 14. Đo đúng throughput và saturation

Dưới đây là bộ metric cần thiết khi thử tăng concurrency:

| Metric | Nguồn | Diễn giải |
| --- | --- | --- |
| Queue `messages_ready` | RabbitMQ | Backlog còn chờ |
| Queue `messages_unacknowledged` | RabbitMQ | Delivery đã giao nhưng chưa ACK |
| Consumer count | RabbitMQ | Số consumer đăng ký, **không chắc** số đang xử lý |
| Delivery, ACK, redelivery rate | RabbitMQ | Hoạt động transport; không thay thế business commit |
| Handler success/commit per second | Ứng dụng | Throughput hữu ích |
| Handler duration p50/p95/p99 | Micrometer/APM | Latency và tail khi saturation |
| DB pool active/idle/pending | HikariCP | Lỗi chờ connection |
| DB query latency, locks, CPU/IOPS | Database | Tình trạng bottleneck thật |
| HTTP 429/5xx/timeout, p95 | API client/downstream | Quota và overload |
| Thread pool active/queued/rejected | JVM | Worker bị nghẽn |
| CPU throttling/GC/OOM | Container/JVM | Giới hạn process |
| Outbox pending/oldest age | Producer | Event chưa xác nhận publish |
| DLQ length và retry counts | Broker + ứng dụng | Lỗi tăng khi áp lực lớn |
| Business event age | Ứng dụng | SLO đầu cuối |

Metric Spring/Micrometer thực tế phụ thuộc phiên bản và cấu hình observation. Một số metric có thể phải instrument thủ công. Không tuyên bố mọi tên metric minh họa dưới đây được Spring Boot tự xuất.

### 14.1. PromQL ví dụ cho queue và DB pool

Nếu sử dụng RabbitMQ Prometheus `/metrics/detailed` và có các family/labels phù hợp:

~~~promql
rabbitmq_detailed_queue_messages_ready{
  vhost="/orders",queue="billing.order-paid.queue"
}
~~~

Tốc độ ACK ở queue (cần kiểm tra counter thực của exporter):

~~~promql
rate(
  rabbitmq_detailed_queue_messages_acked_total{
    vhost="/orders",queue="billing.order-paid.queue"
  }[5m]
)
~~~

Metric HikariCP khi được export sang Prometheus có thể gồm:

~~~promql
hikaricp_connections_active{pool="HikariPool-1"}

hikaricp_connections_pending{pool="HikariPool-1"}
~~~

Nhãn `pool` có thể khác theo cấu hình dự án. Đừng so sánh một queue cụ thể với toàn bộ DB pool nếu nhiều service dùng chung mà không phân tách workload.

### 14.2. Chọn biểu đồ so sánh cùng một trục thời gian

Dashboard nên hiển thị đồng thời:

1. `C_total`, pod count và consumer count.
2. RabbitMQ ready/unacked.
3. Business commits per second và p95/p99 latency.
4. Hikari active/pending và DB query p95.
5. HTTP request rate, 429/5xx và p95 latency.
6. Redelivery, retry, DLQ và duplicate suppression.
7. CPU/GC và broker alarms.

Nếu tăng consumer làm ACK rate tăng 5% nhưng DB p99 tăng gấp ba, HTTP 429 tăng và DLQ nhiều hơn, không nên coi đó là cải thiện có giá trị.

## 15. Quy trình benchmark theo từng nấc concurrency

Một bài test có ý nghĩa phải kiểm soát **input workload**, **size distribution**, **consumer replicas**, **prefetch**, **DB/API capacity** và thời điểm đo. Tránh thay concurrency, prefetch, số pod và SQL cùng lúc vì không biết thay đổi nào gây kết quả.

### 15.1. Chuẩn bị

1. Chọn một môi trường tương tự production về tài nguyên, không thử trên queue production đang có đơn hàng thật.
2. Đo baseline hiện tại: throughput, latency p95/p99, ready/unacked, DLQ, DB/API saturation.
3. Sử dụng một tập dữ liệu đa dạng: message nhỏ/lớn, một số key nóng, phần trăm retry dự kiến.
4. Đảm bảo producer tạo được input ổn định; ghi `eventId` duy nhất cho từng event mới.
5. Thiết lập một SLO minh họa, ví dụ: 99% event hoàn tất trong 10 giây, business error rate dưới 0,1%.
6. Quy định tiêu chí rollback: DB pending connections liên tục, 429 tăng, p99 vượt ngưỡng hoặc DLQ bất thường.

### 15.2. Tăng theo bậc, giữ biến khác cố định

Ví dụ với hai pod cố định, `prefetch=10`:

| Lần đo | Consumer/pod | Tổng consumer | Mục tiêu |
| --- | ---: | ---: | --- |
| A | 2 | 4 | Baseline |
| B | 4 | 8 | Kiểm tra throughput tăng và p95 ổn |
| C | 6 | 12 | Tìm dấu hiệu contention |
| D | 8 | 16 | Kiểm tra điểm bão hòa |
| E | 10 | 20 | Chỉ khi downstream còn capacity |

Giữ mỗi nấc đủ lâu để vượt qua warm-up, JIT, connection pool initialization, load burst và timeout dài. Khi cần benchmark chính xác, đặt min=max trong SMLC để tránh auto-scale làm số consumer thay đổi bất ngờ.

### 15.3. Phiếu ghi kết quả ví dụ

| C tổng | Commit/s | Handler p95 | DB pool pending | HTTP 429 | Nhận định |
| ---: | ---: | ---: | ---: | ---: | --- |
| 4 | 30 | 180 ms | 0 | 0 | Còn dư capacity |
| 8 | 58 | 200 ms | 0 | 0 | Cải thiện tốt |
| 12 | 72 | 310 ms | 1 | 0 | Bắt đầu contention |
| 16 | 73 | 700 ms | 9 | 4/s | Gần bão hòa, không nên tăng |
| 20 | 65 | 1.600 ms | 17 | 15/s | Thoái hóa do overload |

**Các số liệu chỉ minh họa.** Ở đây có thể chọn **8–12 consumer tổng** tùy SLO và headroom, không chọn 20 chỉ vì con số lớn. Với một SLO p95 nhỏ, 8 có thể là lựa chọn tốt hơn 12.

### 15.4. Đánh giá bằng *goodput*, không chỉ delivery rate

- **Delivery throughput**: số message broker giao cho consumer.
- **ACK throughput**: số message được broker xác nhận; có thể bao gồm những duplicate đã được bỏ qua.
- **Business goodput**: số event hợp lệ mới được xử lý và **commit thành công**, không trùng.
- **Retry rate**: công việc lại phải làm do lỗi tạm thời hoặc poison.
- **Business latency**: thời gian nguồn tạo event tới khi kết quả bền vững.

Mục tiêu là tăng **goodput** mà giữ latency/error/SLO, không phải tăng số lần broker giao cùng một message.

## 16. Khi concurrency phải giảm thay vì tăng

Sau benchmark hoặc trong incident, hãy **giảm** concurrency nếu thấy:

- Hikari pending threads/connection acquisition timeout tăng liên tục.
- Downstream 429/503/timeout tăng.
- DB lock wait, deadlock, CPU hoặc IOPS bão hòa.
- Handler p95/p99 tăng mạnh khi số consumer mới không mang thêm commits.
- Redelivery, retry và DLQ tăng, cùng event lỗi nhiều lần.
- JVM memory/GC hoặc RabbitMQ unacked bytes tăng bất thường.
- Thuật toán tăng consumer làm cạnh tranh với service front-end dùng chung DB.

Việc giảm concurrency có thể **tăng goodput** vì mỗi message ít phải chờ lock/connection và hệ thống phục hồi ổn định. Nên có điểm rollback đã thử nghiệm, ví dụ quay từ 12 về 8 consumer/pod khi pool pending và 429 vượt guardrail.

## 17. Concurrency và thứ tự xử lý message

Một queue RabbitMQ có thứ tự lưu trữ/định tuyến nhất định, nhưng khi có nhiều consumer và nhiều delivery in-flight, **thứ tự hoàn tất xử lý không còn được bảo đảm như khi chỉ có một consumer tuần tự**.

Ví dụ:

~~~text
Queue: OrderEvent(version=1) → OrderEvent(version=2)

Consumer A nhận version=1 → gọi API chậm 2 giây
Consumer B nhận version=2 → DB commit sau 100 ms

Kết quả hoàn tất: version=2 trước version=1
~~~

Nếu handler cập nhật state trực tiếp mà không có guard, version=1 có thể **ghi đè** version=2. Điều này không phải lỗi RabbitMQ: song song hóa đã thay đổi thứ tự hoàn tất.

Có những chiến lược:

1. **Chấp nhận xử lý out-of-order** nếu nghiệp vụ có thể xử lý bằng version guard hoặc commutative operation.
2. **Partition theo business key**, bảo đảm mọi event cùng `orderId` đi vào cùng partition queue, với consumer tuần tự phù hợp.
3. **Single Active Consumer** trên từng queue khi cần một consumer active tại một thời điểm.
4. **`prefetch=1` và concurrency=1** khi muốn giảm in-flight/đơn giản hóa thứ tự, chấp nhận giới hạn throughput.
5. **Sử dụng idempotency và event version** để chống redelivery và event cũ tới muộn.

### 17.1. Khi không thể tăng consumer trên một queue

Một queue dùng Single Active Consumer có thể có nhiều consumer đã đăng ký, nhưng broker chỉ chọn **một active consumer**. Tăng số pod standby **không tăng khả năng xử lý đồng thời trên queue đó**. Nếu cần tăng throughput mà vẫn giữ thứ tự theo entity, có thể chia thành nhiều queue theo khóa ổn định:

~~~mermaid
flowchart LR
    E["Exchange / partition router"] -->|"hash(orderId) % N = 0"| Q0["Queue partition 0 / SAC"]
    E -->|"hash(orderId) % N = 1"| Q1["Queue partition 1 / SAC"]
    E -->|"hash(orderId) % N = 2"| Q2["Queue partition 2 / SAC"]
    Q0 --> C0["Active consumer 0"]
    Q1 --> C1["Active consumer 1"]
    Q2 --> C2["Active consumer 2"]
~~~

Đây là **chiến lược partition của ứng dụng/routing**, không phải việc chỉ đổi `concurrency` của một listener. Cần quản lý route key, thay đổi số partition và phân phối key nóng để tránh một queue vẫn bão hòa trong khi queue khác rỗng.

**Không tăng concurrency vượt yêu cầu thứ tự nghiệp vụ.** Goodput cao hơn nhưng state sai không phải cải thiện hiệu năng.

## 18. ACK, retry và dead-letter khi tăng tải

Tăng số consumer làm số delivery đồng thời tăng, kéo theo nhiều cửa sổ lỗi:

- Consumer có thể bị kill giữa transaction.
- DB đã commit nhưng ACK chưa tới broker.
- API đã nhận request nhưng caller timeout.
- Publisher gửi thành công nhưng confirm bị mất.
- Nhiều consumer cùng gặp DB lock/429 và retry đồng loạt.

### 18.1. ACK sau commit và idempotency

`AcknowledgeMode.AUTO` trong Spring listener container ACK sau khi listener xử lý thành công theo cơ chế container. Handler cần hoàn tất transaction **trước khi return**. Khi DB commit thành công nhưng connection/channels chết trước ACK, broker có thể redeliver cùng event.

Để tránh business effect trùng:

1. Producer gắn `eventId` ổn định.
2. Consumer lưu marker độc nhất theo `(consumerName,eventId)`.
3. Marker và side effect commit cùng database transaction.
4. Message trùng được nhận diện, bỏ qua side effect nhưng vẫn kết thúc xử lý thành công.
5. Nếu effect nằm ở HTTP/payment bên ngoài DB, dùng idempotency key được đích hỗ trợ và đối soát unknown outcome.

Concurrency càng lớn, khả năng hai consumer cùng cố xử lý một ID hoặc cùng order càng phải được kiểm soát bằng **ràng buộc ở storage**, không chỉ bằng một `ConcurrentHashMap` trong JVM.

### 18.2. Retry có thể nhân tải downstream

Giả sử 100 message/s, 20% request thất bại tạm thời, mỗi message lỗi được thử tối đa ba lần. Số request HTTP thực có thể tăng đáng kể so với 100/s, dù arrival rate chỉ 100 message/s. Nếu retry không có backoff hoặc tất cả consumers retry đồng bộ, lỗi quá tải có thể tự khuếch đại.

Phân biệt:

- **Connection recovery**: listener không còn connection hợp lệ tới broker.
- **Business retry**: handler đã nhận message nhưng DB/API lỗi.
- **Publish retry**: producer chưa có confirm đáng tin cậy.
- **Dead-letter**: broker chuyển message lỗi theo cấu hình DLX/queue policy.

Không tạo vô hạn vòng `basic.nack(requeue=true)` để “cho mọi message một cơ hội nữa”. Với các lỗi permanent, nên reject có điểm dừng và đưa message vào terminal DLQ hoặc luồng điều tra. Với các lỗi transient kéo dài, delay retry/backoff giúp giảm áp lực thay vì giữ consumer thread busy-loop.

### 18.3. Publisher confirms/returns không thay thế consumer ACK

Cấu hình producer minh họa:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

- Confirm ACK thuộc chặng **publisher → broker**.
- Return giúp nhận biết publish không route được khi mandatory áp dụng.
- Consumer ACK thuộc chặng **broker → listener**.
- DB commit là kết quả **nghiệp vụ**.

Một queue có depth nhỏ không chứng minh publisher không bị chặn vì resource alarm hay binding bị sai. Theo dõi **outbox pending age** cùng confirms/returns và business goodput.

## 19. Autoscaling dựa trên năng lực thật của hệ thống

Có thể điều chỉnh concurrency trong container, số pod hoặc cả hai. Điều quan trọng là **tổng consumer không vượt ngân sách downstream**.

### 19.1. Một công thức khởi đầu cho horizontal scaling

Nếu đo được mỗi pod xử lý bền vững `g` event/s ở một cấu hình consumer cố định, và có mục tiêu `λ_target`, số pod tối thiểu lý tưởng:

\[
R_{\text{needed}}\approx
\left\lceil \frac{\lambda_{\text{target}}}{g}\right\rceil
\]

Đây chỉ là ước lượng khi có capacity tăng tuyến tính; quota DB/API dùng chung có thể khiến `g` **giảm** khi tăng pod. Giá trị `R_needed` phải bị chặn bằng `R_max` suy ra từ downstream, không chỉ từ CPU hoặc queue length.

Ví dụ một pod ở `C=4` xử lý ổn định `50 event/s`, nhu cầu `150/s` có thể gợi ý 3 pod. Nhưng nếu API đích chỉ cho toàn hệ thống `120 request/s`, ba pod **không thể** duy trì `150/s` bất kể worker khỏe đến đâu; cần giảm input/đổi kiến trúc/thỏa thuận quota.

### 19.2. Queue depth là chỉ báo trễ, không phải bộ điều khiển đủ thông minh

Autoscaling chỉ theo ready messages dễ gây vấn đề:

- Pod mới chưa warm-up, connection pool chưa sẵn sàng.
- Sự cố downstream khiến backlog tăng; autoscaler tăng pod và làm downstream lỗi nặng hơn.
- Consumer đang unacked rất nhiều nên ready giảm, dù business progress không tăng.
- Một batch theo lịch tạo backlog dự kiến, autoscaler phản ứng quá nhanh rồi scale down ngay.
- Khi nhiều pod rút xuống, message unacked được giao lại, gây spike retry.

Nếu dùng KEDA/HPA hoặc cơ chế tương tự, nên kiểm tra hỗ trợ/metric thực, giới hạn replica tối đa theo downstream, đặt stabilization/cooldown và có guardrail theo error rate, latency và resource saturation.

### 19.3. Circuit breaker và backpressure không thể chỉ trông vào scale

Một API đang trả 429 liên tục cần **giảm tốc độ request**, không tăng worker. Các phương án gồm:

- Rate limiter theo quota toàn hệ thống hoặc per-tenant.
- Bulkhead giới hạn in-flight request.
- Timeout và circuit breaker để tránh giữ thread quá lâu.
- Delay retry queue, không requeue ngay.
- Admission control từ phía producer hoặc outbox relay.
- Tách workload ưu tiên cao/thấp thành queue khác với ngân sách concurrency riêng.

Khi đã có hàng đợi ở broker, thường **không cần tạo thêm hàng đợi vô hạn ở memory của ứng dụng**. Dùng RabbitMQ như bộ đệm có giám sát, rồi xử lý ở tốc độ downstream chịu được.

## 20. Kịch bản kiểm thử tăng concurrency

Các thí nghiệm dưới đây nên chạy trong staging với broker, queue, database và API giả lập tương đương production, có dữ liệu riêng và công cụ đo. Không tăng concurrency trên production dựa vào suy đoán mà chưa có guardrail.

### Kịch bản A — tăng concurrency khi downstream còn rảnh

1. Đặt SMLC `concurrency=2` và `max-concurrency=2`.
2. Gửi tải ổn định, đo business commits/s, p95, DB pool và ready queue.
3. Tăng lên 4, sau đó 6 với cùng prefetch và số pod.
4. So sánh throughput và tail latency sau khi warm-up.

**Kỳ vọng:** throughput tăng khi downstream có capacity; độ trễ và error rate vẫn trong SLO.

### Kịch bản B — saturation database

1. Dùng database test với pool size giới hạn.
2. Tăng consumer qua ngân sách connection.
3. Quan sát `hikaricp_connections_pending`, acquisition timeouts, DB CPU/locks.
4. Đo commit rate ở mỗi mức.
5. Giảm về mức trước saturation.

**Kỳ vọng:** học cách nhận ra điểm tăng concurrency không còn đem thêm goodput.

### Kịch bản C — HTTP API giới hạn tốc độ

1. Thiết lập Billing API test quota, ví dụ 120 request/s.
2. Tăng consumer nhưng giữ request rate không vượt quota bằng limiter phù hợp.
3. Thử tắt limiter trong môi trường an toàn, quan sát 429/timeout và retry.
4. Khôi phục limiter, đo goodput và queue age.

**Kỳ vọng:** concurrency không thay thế rate limiting.

### Kịch bản D — thay prefetch nhưng giữ concurrency

1. Giữ `C=8` và payload distribution cố định.
2. Thử `prefetch=1`, `10`, `50` rồi so sánh.
3. Đo ready, unacked, memory, fairness và ACK/commit rate.
4. Dừng tăng khi unacked/memory tăng mà goodput không cải thiện.

**Kỳ vọng:** thấy prefetch không đồng nghĩa số handler đang chạy.

### Kịch bản E — scale pod và scale consumer cùng lúc

1. Baseline 2 pod × 4 consumer.
2. Thử 4 pod × 4 consumer, rồi 4 pod × 8.
3. Quan sát **tổng** database connections, HTTP in-flight và error rate.
4. Đưa về mức nằm trong ngân sách tổng.

**Kỳ vọng:** hiểu mức concurrency thực là tích của số replica và consumer/pod.

### Kịch bản F — downstream chậm đột ngột

1. Đặt Billing API test trả lời chậm hoặc 503.
2. Quan sát listener latency, unacked, retries và queue ready.
3. Kiểm tra container dynamic concurrency có thể tăng tải trong khoảng min–max không.
4. Giới hạn concurrency/rate, bật backoff/circuit breaker.
5. Khôi phục API và đo thời gian xả backlog.

**Kỳ vọng:** khi dependency hỏng, **giảm áp lực** thường tốt hơn tăng số worker.

### Kịch bản G — mất ACK sau DB commit

1. Consumer nhận `E42`, commit marker inbox và projection.
2. Mô phỏng connection chết trước ACK broker nhận.
3. Cho E42 redeliver sau recovery.
4. Xác minh unique constraint không cho lặp side effect.

**Kỳ vọng:** scale không làm mất tính idempotent.

### Kịch bản H — poison message khi nhiều consumer

1. Gửi message sai schema hoặc business invariant.
2. Cho listener retry hữu hạn và reject không requeue.
3. Xác minh message vào terminal DLQ.
4. Kiểm tra delivery rate, retry rate và goodput của message hợp lệ.
5. Replay có chọn lọc sau khi sửa lỗi.

**Kỳ vọng:** tăng consumer không tạo vòng requeue vô hạn.

### Kịch bản I — thứ tự cùng business key

1. Publish version 1 và 2 của cùng `orderId`.
2. Với `concurrency>1`, cố tình làm handler version 1 chậm.
3. Quan sát khả năng version 2 commit trước.
4. Kiểm tra version guard hoặc partition/SAC ngăn state bị ghi đè sai.

**Kỳ vọng:** throughput cao vẫn giữ đúng invariant nghiệp vụ.

### Kịch bản J — kiểm tra consumer count và backlog khi SAC

1. Tạo queue SAC trong staging.
2. Chạy nhiều consumer trên cùng queue.
3. Kiểm tra chỉ một active consumer nhận delivery.
4. Thử tăng consumer và đo throughput.
5. Nếu cần, thử partition queue theo key trong bài riêng.

**Kỳ vọng:** không đánh đồng nhiều consumer đã đăng ký với nhiều worker thực sự hoạt động.

### Kịch bản K — thử autoscaling khi backlog tăng vì lỗi downstream

1. Tạo backlog do API đích tạm lỗi.
2. Quan sát hệ thống autoscaling dựa trên queue depth.
3. Kiểm tra số pod/concurrency có vượt ngân sách DB/API không.
4. Áp dụng max replicas, limiter và stabilization phù hợp.
5. Khôi phục API và đo drain time.

**Kỳ vọng:** autoscaler không tự khuếch đại overload.

### Kịch bản L — benchmark sau khi tối ưu SQL

1. Giữ số consumer cố định và đo baseline.
2. Tối ưu SQL/indexing bằng quy trình DB độc lập.
3. Đo lại mean/p95 processing time và goodput.
4. Chỉ sau đó tăng concurrency từng nấc.
5. Kiểm tra liệu bottleneck đã chuyển sang API/network chưa.

**Kỳ vọng:** tối ưu handler trước giúp tăng throughput an toàn hơn chỉ tăng concurrency.

## 21. Runbook khi tăng concurrency làm hệ thống xấu đi

Giả sử vừa nâng `concurrency=4` lên `12`, sau đó p99 latency tăng, queue unacked lớn, Billing API trả 429 và DLQ có message mới.

Thứ tự xử lý:

1. **Dừng rollout/tăng scale tiếp.** Ghi lại cấu hình trước và sau: pod count, consumer/pod, prefetch, retry.
2. **Xác định điểm nghẽn:** DB pool pending? API quota? CPU/GC? broker alarm? Queue leader throughput?
3. **Giảm về cấu hình an toàn trước đó** nếu guardrail đã vượt, ví dụ 4 consumer/pod.
4. **Giới hạn request tới downstream** bằng bulkhead/rate limiter/backoff; không phát retry ồ ạt.
5. **Giữ outbox và queue còn nguyên**, không purge để làm dashboard đẹp.
6. **Kiểm tra DLQ** và poison events; không replay trước khi xác định nguyên nhân.
7. **Đối soát ACK/commit và duplicate** vì nhiều message có thể redeliver trong lúc restart.
8. **Theo dõi phục hồi:** HTTP 429 giảm, DB pending về bình thường, business goodput tăng, queue age giảm.
9. **Chạy lại benchmark kiểm soát** với một biến duy nhất thay đổi.
10. **Cập nhật runbook và ngân sách concurrency** dựa trên capacity quan sát được.

**Cách tính toán sau incident:** không chọn mức concurrency đã đạt throughput cao nhất trong một khoảng 30 giây ngắn ngủi. Chọn mức **duy trì được** throughput/latency và có headroom cho spike, retry, rolling restart và sự cố một replica.

## 22. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Queue tăng thì tăng consumer vô hạn | Downstream bão hòa, throughput giảm | Xác định bottleneck và ngân sách |
| Coi `prefetch=100` là 100 handler song song | Unacked tăng, đánh giá sai capacity | Tách prefetch khỏi concurrency |
| Chỉ tính consumer mỗi pod | Tổng consumer vượt DB/API quota | Tính `replicas × consumer/pod` |
| Tin auto-scale SMLC biết DB đang bận | Consumer tăng dựa trên activity dù DB chậm | Đặt max theo downstream, giám sát saturation |
| Dùng Hikari pool quá lớn cho mỗi replica | Tổng DB connections vượt giới hạn | Tính pool budget trên tất cả instances |
| Giữ DB transaction trong lúc HTTP chậm | Lock/connection bị giữ lâu | Tách workflow, outbox và idempotency |
| Retry ngay sau 429 vô hạn | Tạo retry storm | Rate limiter, backoff có điểm dừng |
| Chỉ đo RabbitMQ delivery rate | Poison requeue làm số đẹp giả | Đo business goodput và commit |
| Không đo p95/p99 | Tail latency/SLO xấu dù average tốt | Theo dõi percentiles và error budgets |
| Tăng consumer trên queue SAC | Nhiều standby nhưng throughput không tăng | Partition theo key hoặc đổi semantics |
| Quên thứ tự hoàn tất khi song song | Event cũ ghi đè event mới | Version guard, partition/sequencing |
| ACK trước commit vì muốn nhanh | Crash gây mất side effect | ACK sau transaction, dùng idempotency |
| Không có DLQ terminal | Poison loop hoặc message bị drop | Retry hữu hạn, DLX/DLQ đã kiểm tra |
| HPA chỉ theo queue ready | Overload downstream thì càng scale | Giới hạn replicas, kết hợp guardrails |

## 23. Checklist áp dụng production

- [ ] Đã định nghĩa business SLO, throughput mục tiêu và giới hạn error/retry.
- [ ] Biết backlog đến từ producer spike, mất consumer, broker hay downstream.
- [ ] Đã đo baseline goodput, handler mean/p95/p99, queue ready/unacked.
- [ ] Đã đo DB pool active/pending, query latency, CPU/IOPS và locks.
- [ ] Đã đo HTTP rate, 429/5xx, timeout, in-flight và quota thực.
- [ ] Có ngân sách tổng `R_max × C_max`, không chỉ max consumers/pod.
- [ ] Đã chọn SMLC/DMLC và thông số concurrency phù hợp với khả năng API được dùng.
- [ ] Prefetch được chọn qua load test, không dùng để giả lập concurrency.
- [ ] Có backpressure/bulkhead/rate limiter cho dependency dễ quá tải.
- [ ] Listener ACK sau business commit, không return trước công việc async chưa hoàn tất.
- [ ] Consumer có eventId, unique marker và xử lý out-of-order phù hợp nghiệp vụ.
- [ ] Retry có giới hạn; terminal DLQ được khai báo và kiểm thử trên đúng broker/vhost.
- [ ] Producer dùng confirms/returns và outbox khi không thể mất event.
- [ ] Không có auto-scale trên hai chiều gây vượt capacity khi spike.
- [ ] Đã benchmark từng nấc với một biến thay đổi, có ngưỡng rollback.
- [ ] Có dashboard business goodput, p95/p99, queue age, downstream saturation và DLQ.
- [ ] Đã diễn tập DB pool saturation, HTTP 429, ACK lost, poison, ordering và autoscaling.
- [ ] Có runbook giảm concurrency an toàn khi downstream bắt đầu quá tải.

## 24. Tài liệu tham khảo và tổng kết

Các tài liệu nên đối chiếu với phiên bản Spring AMQP, Spring Boot và RabbitMQ đang triển khai:

- [Spring AMQP Reference — Listener Container](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html)
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/)
- [RabbitMQ Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch)
- [RabbitMQ Consumers](https://www.rabbitmq.com/docs/consumers)
- [RabbitMQ Monitoring](https://www.rabbitmq.com/docs/monitoring)
- [RabbitMQ Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)

**Tăng consumer concurrency** chỉ có giá trị khi ứng dụng và downstream còn năng lực xử lý. Trong **SPRING_AMQP**, SMLC có thể điều chỉnh consumer trong khoảng min–max, còn DMLC dùng `consumersPerQueue`; cả hai đều chịu giới hạn **database pool, API quota, CPU, memory, queue type và yêu cầu thứ tự nghiệp vụ**. Prefetch điều khiển delivery chưa ACK, **không phải** số business handler đồng thời.

Một quy trình tối ưu đúng gồm: **đo baseline → tìm bottleneck → tính ngân sách toàn deployment → tăng concurrency từng nấc → kiểm tra goodput/p95/p99/error rate → giữ headroom → chuẩn bị rollback**. Phải đồng thời duy trì publisher confirms, ACK sau commit, idempotency, retry và terminal DLQ để thông lượng cao hơn **không làm mất hoặc xử lý trùng message**.

Câu hỏi cuối cùng không phải “đã tạo được bao nhiêu consumer?”, mà là **“Hệ thống đã xử lý và commit thêm bao nhiêu event hợp lệ mỗi giây, với độ trễ và lỗi trong SLO, trong khi database/API vẫn còn khả năng phục hồi khi có sự cố?”**



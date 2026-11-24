# Rolling update với cùng nhóm và tái cân bằng consumer

Khi triển khai phiên bản mới của ứng dụng xử lý sự kiện bằng Spring Cloud Stream, đội vận hành thường muốn thay dần các Pod hoặc instance mà không dừng toàn bộ pipeline. Trong Kubernetes, đó là **rolling update**: phiên bản mới được khởi chạy theo từng đợt, còn phiên bản cũ được dừng sau khi đạt điều kiện thay thế. Nếu các instance cùng tiêu thụ một Kafka topic với **cùng consumer group**, việc thành viên mới tham gia hoặc thành viên cũ rời nhóm sẽ ảnh hưởng đến phân công partition và có thể kích hoạt **consumer rebalance**.

Rolling update có thể giúp duy trì năng lực xử lý, nhưng không mặc nhiên đảm bảo không có khoảng dừng xử lý, không có message giao lại hoặc không có tác dụng nghiệp vụ bị lặp. Kafka lưu offset theo group và partition; Spring Cloud Stream binder quản lý consumer bên dưới; Kubernetes quản lý vòng đời container. Ba cơ chế đó phải phối hợp với thời gian hoàn tất message đang xử lý, commit offset và khả năng chịu tải của hệ thống.

Bài này tập trung vào Kafka consumer group trong Spring Cloud Stream, đồng thời chỉ ra khác biệt khi ứng dụng dùng RabbitMQ binder, Pulsar binder hoặc Kafka Streams binder. Những ví dụ về cấu hình là điểm xuất phát cần kiểm tra với phiên bản Spring Boot, Spring Cloud Stream, Kafka client/broker và môi trường triển khai thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích rolling update khác với việc thay consumer group.
- Dự đoán partition assignment khi Pod mới vào và Pod cũ rời cùng Kafka group.
- Phân biệt eager, cooperative rebalance và giao thức consumer group mới.
- Hiểu vai trò của `group.id`, `concurrency`, `group.instance.id` và các timeout.
- Cấu hình Spring Cloud Stream Kafka binder với group cố định.
- Thiết kế Kubernetes RollingUpdate, readiness, liveness và graceful termination.
- Giảm thời gian gián đoạn và tránh mất message khi Pod bị dừng.
- Xử lý duplicate delivery, transaction boundary và thứ tự theo partition.
- Theo dõi lag, rebalance, assignment, lỗi xử lý và thời gian drain.
- Kiểm thử rolling update, rollout thất bại và rollback bằng dữ liệu thật.

## 1. Cùng group nghĩa là chia việc, không phải phát bản sao cho mỗi Pod

Xét topic `orders.created` có **6 partition** và ứng dụng Spring Cloud Stream tên `order-processor` đang chạy **3 Pod**. Mỗi Pod tạo một Kafka consumer trong group `order-processing`.

~~~text
Kafka topic: orders.created (6 partitions)

Partition:   P0   P1   P2   P3   P4   P5
              \   /     \   /     \   /
Group:       Pod A       Pod B       Pod C
             v1.0        v1.0        v1.0
~~~

Đây là một sơ đồ phân công minh họa. Kafka assignor thực tế quyết định partition nào thuộc consumer nào; không nên giả định luôn có cách phân công P0/P1 cho A, P2/P3 cho B.

Trong một consumer group thông thường, một partition được giao cho **một consumer thành viên tại một thời điểm**. Nhiều Pod thuộc cùng group cùng xử lý các partition khác nhau. Nếu muốn mọi phiên bản đều nhận toàn bộ event để kiểm thử song song, phải dùng một group khác, nhưng khi đó tác dụng phụ nghiệp vụ có thể xảy ra hai lần nếu cả hai group đều ghi hệ thống thật.

### 1.1. Điều gì xảy ra khi rolling update?

Giả sử Deployment tạo Pod D phiên bản v2 trước khi dừng Pod A:

~~~text
T0: A(v1), B(v1), C(v1)          -> group có 3 thành viên
T1: A(v1), B(v1), C(v1), D(v2)   -> có thành viên mới
T2: B(v1), C(v1), D(v2)          -> A rời nhóm
T3: B(v1), C(v1), D(v2), E(v2)   -> thành viên khác tham gia
...
Tn: D(v2), E(v2), F(v2)          -> phiên bản mới hoàn tất
~~~

Ở mỗi thời điểm có thành viên vào/ra, group coordinator có thể điều chỉnh phân công partition. Một số consumer bị tạm dừng khi cần trao hoặc nhận partition, nhưng topic vẫn tồn tại, producer vẫn có thể ghi và record chờ trong log Kafka. Mục tiêu của rollout là giảm thời gian xử lý chậm và bảo đảm consumer mới tiếp tục từ offset hợp lệ.

### 1.2. Hai phiên bản cùng lúc trong một group

Kubernetes rolling update tạo khoảng thời gian mà v1 và v2 cùng tồn tại. Cả hai phải đọc được schema do producer đang phát và phải ghi side effect tương thích với nhau.

Ví dụ, nếu v2 bắt đầu yêu cầu trường `currency` mà v1 chưa biết, hãy triển khai schema tương thích theo nguyên tắc expand/contract trước. Không nên bật một thay đổi không tương thích khi các Pod v1 còn đọc event.

## 2. Rebalance của Kafka diễn ra như thế nào?

Một thành viên group có thể cần được thay thế khi:

- Consumer mới join group.
- Consumer đóng hoặc leave group.
- Consumer mất heartbeat quá thời hạn session.
- Assignment thay đổi vì topic có partition mới hoặc subscription đổi.
- Một consumer không tiếp tục gọi `poll()` kịp giới hạn `max.poll.interval.ms`.
- Broker/group coordinator thay đổi hoặc gặp sự cố.

Quy trình khái quát:

~~~mermaid
sequenceDiagram
    participant K as Kubernetes
    participant N as Pod mới
    participant C as Kafka Coordinator
    participant O as Pod cũ
    K->>N: Khởi chạy v2
    N->>C: Join group
    C-->>O: Yêu cầu thay đổi assignment nếu cần
    O->>O: Hoàn tất/đóng xử lý đang giữ theo lifecycle
    C-->>N: Assign partition
    N->>N: Poll và xử lý
    K->>O: SIGTERM khi đủ điều kiện rollout
    O->>C: Leave/close consumer
    C-->>N: Cập nhật assignment nếu cần
~~~

Đây là mô hình nhận thức, không phải lịch callback chính xác cho mọi assignor và protocol. Thứ tự cũng phụ thuộc phiên bản Kafka, Spring Kafka container và cấu hình shutdown.

### 2.1. Group membership và committed offset

Kafka lưu committed offset theo tổ hợp consumer group, topic và partition. Khi partition chuyển từ Pod A sang Pod D, D tiếp tục tại offset đã được commit bởi group, không bắt đầu lại ở offset 0 chỉ vì Pod hoặc image mới.

Ví dụ:

~~~text
P2: offsets 100 101 102 103 104 105 106 ...
    A đã thực hiện tác dụng nghiệp vụ của 104
    offset commit cuối cùng của group là 104
    (vị trí sẽ đọc tiếp sau phần đã commit)

    A chết trước khi commit vị trí kế tiếp
    D nhận P2, đọc lại từ committed offset
~~~

Trong ví dụ trên, D có thể xử lý lại record vừa tạo tác dụng nghiệp vụ ở A. Cách biểu diễn offset cần theo quy ước “committed offset là vị trí đọc kế tiếp”; tránh nhầm nó với “ID của record cuối đã xử lý”. Duplicate là hiện tượng có thể xảy ra khi side effect và offset commit không nằm trong cùng transaction.

### 2.2. Eager rebalance

Với kiểu rebalance **eager**, các consumer tham gia quá trình tái phân công có thể phải revoke toàn bộ assignment cũ trước khi nhận assignment mới. Điều này tạo khoảng tạm dừng đáng kể khi group lớn hoặc rollout làm nhiều thành viên liên tục vào/ra.

### 2.3. Cooperative rebalance

Cooperative rebalance (ví dụ `CooperativeStickyAssignor` trong classic protocol) có thể giữ các partition không cần chuyển chủ, chỉ revoke những partition cần đổi. Điều đó thường giảm gián đoạn, nhưng không loại bỏ hẳn rebalance, duplicate hoặc thời gian chờ khi xử lý chưa hoàn tất.

Với **classic group protocol**, cấu hình Kafka client thường dùng property `partition.assignment.strategy`. Tài liệu Kafka 4.4 liệt kê mặc định `RangeAssignor, CooperativeStickyAssignor`; vì Range đứng trước, **không mặc định hiểu rằng đang dùng cooperative**. Việc đổi assignor cần kế hoạch tương thích và rollout tuần tự, đặc biệt khi v1/v2 cùng trong group.

### 2.4. Consumer group protocol mới

Các phiên bản Kafka hiện hành có `group.protocol` nhận `classic` hoặc `consumer`. Classic sử dụng assignor phía client; protocol `consumer` (KIP-848) dùng phân công phía broker và quy trình cập nhật assignment khác. Khi dùng `consumer`, `group.remote.assignor` và một số timeout phía broker trở nên quan trọng; `heartbeat.interval.ms` và `session.timeout.ms` kiểu classic không phải các tuning knob tương ứng.

Đừng copy nguyên bộ cấu hình classic sang protocol mới. Trước khi nâng cấp protocol, kiểm tra khả năng hỗ trợ của broker, Kafka client, Spring Kafka, Spring Cloud Stream binder và hướng dẫn migration; thử trong staging với cùng kích thước group.

## 3. Giữ group cố định trong Spring Cloud Stream

Ví dụ function xử lý:

~~~java
@SpringBootApplication
public class OrderProcessorApplication {

    @Bean
    Consumer<OrderCreated> processOrder(OrderService service) {
        return service::handle;
    }
}

record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        Instant occurredAt) {}
~~~

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processing
          consumer:
            concurrency: 1
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              autoRebalanceEnabled: true
~~~

Ở đây:

- `processOrder-in-0` là tên input binding theo functional model.
- `destination` là topic Kafka.
- `group` chọn group có offset dùng chung giữa mọi replica.
- `concurrency` quyết định số consumer thread/container trong mỗi replica đối với binder hỗ trợ.
- `autoRebalanceEnabled=true` cho Kafka quản lý phân công partition qua group. Khi đặt `false`, binder dùng phân công partition cố định dựa trên `instanceCount`/`instanceIndex`; đó là chiến lược khác, cần quản lý instance identity riêng và không được trộn vào ví dụ rolling group thông thường.

**Không thay `group` trong bản v2** nếu muốn tiếp tục offset của group cũ. Group mới có offset riêng và có thể đọc lại dữ liệu lịch sử hoặc bắt đầu theo offset reset policy; điều này thay đổi bản chất rollout.

### 3.1. Số partition, số Pod và concurrency

Nếu topic có `P` partition, Deployment có `R` replica và mỗi replica có `C` consumer thread, số consumer thành viên lý thuyết là khoảng `R × C`. Số partition giới hạn mức tiêu thụ song song trong một group:

\[
\text{parallel consumers hữu ích}
\leq
\min(P, R \times C)
\]

Ví dụ:

| Partition | Pod | Concurrency/Pod | Tổng consumer | Nhận xét |
|---:|---:|---:|---:|---|
| 6 | 3 | 1 | 3 | Mỗi consumer có thể nhận khoảng 2 partition |
| 6 | 3 | 2 | 6 | Có thể phân bố 1 partition mỗi consumer |
| 6 | 4 | 2 | 8 | Ít nhất 2 consumer không có partition, tùy phân công |
| 3 | 5 | 1 | 5 | Nhiều Pod không xử lý partition nào |

Tăng `replicas` hoặc `concurrency` có thể làm rebalance thường xuyên hơn và tăng connection, CPU, RAM, DB pool. Trong rollout với `maxSurge`, số consumer tạm thời còn cao hơn trạng thái ổn định. Cần kiểm tra headroom của ứng dụng và hệ thống downstream.

### 3.2. Không đặt reset offset cho rolling deploy

Đối với group đã có committed offsets, consumer mới cần tiếp tục từ offsets đó. Không đặt `resetOffsets=true` để “khởi động sạch” trong rollout; điều đó có thể làm đọc lại hoặc bỏ qua lượng lớn record tùy cấu hình. Các thiết lập `startOffset`/`auto.offset.reset` chỉ phù hợp trong những trường hợp chưa có offset hợp lệ hoặc offset bị mất/ngoài range theo semantics cụ thể.

## 4. Chiến lược Kubernetes RollingUpdate

Deployment có hai tham số quan trọng:

- `maxSurge`: số Pod bổ sung tối đa so với số replica mong muốn trong quá trình update.
- `maxUnavailable`: số Pod tối đa có thể không sẵn sàng trong rollout.

Ví dụ cho ứng dụng xử lý Kafka:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-processor
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: order-processor
  template:
    metadata:
      labels:
        app: order-processor
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: app
          image: registry.example.org/order-processor:2.0.0
          ports:
            - containerPort: 8080
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
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 5
            failureThreshold: 24
~~~

Giải thích:

- Với 3 replica và `maxSurge: 1`, Kubernetes có thể tạo thêm tối đa 1 Pod vượt số replica mong muốn trong rollout.
- `maxUnavailable: 0` hướng tới việc không giảm số Pod được Kubernetes coi là Available trong quá trình cập nhật; điều đó không đảm bảo Kafka consumer có partition ngay khi readiness probe trả về thành công.
- `terminationGracePeriodSeconds: 90` cho container tối đa khoảng 90 giây để dừng theo vòng đời Kubernetes; đây là số minh họa, không phải mặc định hay giá trị tối ưu cho mọi handler.
- `startupProbe` cho ứng dụng thời gian khởi động và tránh liveness restart khi chưa kịp khởi tạo.
- Liveness và readiness ở ví dụ dùng Spring Boot Actuator probes; cần bật và expose endpoint nếu cấu hình dự án chưa làm.

Ví dụ giả định ứng dụng có HTTP web server và Spring Boot Actuator đang lắng nghe cổng 8080. Consumer-only service không khởi động web server sẽ không có endpoint HTTP này; khi đó cần chủ động cấu hình một management HTTP endpoint phù hợp hoặc chọn cơ chế probe khác trước khi áp dụng manifest.

Kubernetes dùng trạng thái readiness/availability của Pod để quyết định nhịp rollout, **không dùng trực tiếp Kafka partition assignment hoặc consumer lag**. Do đó một Pod v2 có thể đã Ready theo HTTP trước khi consumer join group hoặc được giao partition. Nếu SLA đòi hỏi mạnh hơn, cần kiểm tra khả năng bind/consumer assignment riêng và điều chỉnh readiness một cách có chủ đích.

### 4.1. Khi nào nên chọn maxUnavailable lớn hơn 0?

Nếu ưu tiên cập nhật nhanh và pipeline chịu được backlog ngắn, `maxUnavailable: 1` có thể chấp nhận được. Nhưng nếu chỉ có 1 replica, giá trị đó có thể khiến lúc chuyển phiên bản không còn consumer xử lý; nếu cần liên tục, dùng nhiều replica và đặt ngân sách rollout phù hợp.

`maxSurge: 1`, `maxUnavailable: 0` là cấu hình khởi đầu thận trọng cho 3 replica, chưa phải bằng chứng zero downtime. Cần thử với throughput và độ dài xử lý thực tế.

### 4.2. PodDisruptionBudget và rollout

PodDisruptionBudget (PDB) giúp giới hạn các eviction tự nguyện thông qua Eviction API, chẳng hạn node drain. Deployment rolling update không dựa vào PDB để điều khiển `maxSurge` và `maxUnavailable`. Hãy cấu hình cả hai đúng mục đích; không trông chờ PDB tự làm rolling update an toàn.

## 5. Graceful shutdown và commit offset

Khi Kubernetes xóa Pod theo vòng đời bình thường, Pod đi vào trạng thái Terminating; kubelet chạy `preStop` nếu có, sau đó yêu cầu container dừng (thường bằng SIGTERM). Khi hết grace period, runtime có thể gửi SIGKILL. Nếu JVM không nhận tín hiệu hoặc bị kill quá sớm, Spring application context và consumer container không có cơ hội đóng đúng cách.

Spring Boot cung cấp thời gian dừng theo phase:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 60s

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Đối với phiên bản Spring Boot hiện hành, graceful shutdown của embedded web server được bật mặc định. Có thể khai báo `server.shutdown: graceful` tường minh khi dự án muốn làm rõ chính sách; kiểm tra phiên bản Spring Boot đang dùng. Quan trọng hơn, graceful shutdown của **HTTP server không tự chứng minh Kafka listener đã xử lý xong**. Kafka listener container có lifecycle và timeout riêng, phụ thuộc Binder/Spring Kafka.

### 5.1. Thứ tự shutdown mong muốn

Một quy trình shutdown an toàn cần đạt các ý sau:

1. Pod không nhận thêm HTTP traffic mới nếu có ingress HTTP.
2. Consumer ngừng nhận thêm record mới theo lifecycle phù hợp; việc stop/pause phải được phối hợp với Spring Kafka container.
3. Những message đang xử lý được hoàn tất hoặc được phép xử lý lại an toàn.
4. Chỉ commit offset theo kết quả xử lý đã thành công; không commit sớm để “tắt nhanh”.
5. Producer gửi output được flush/đóng theo chính sách của binder.
6. Consumer close và rời group; partition được giao lại cho các consumer còn sống.
7. JVM thoát trước khi Kubernetes hết grace period.

Tùy implementation, container có thể hoàn tất các record đã poll trong batch trước khi stop, hoặc cần cơ chế dừng riêng. Đừng tự hứa “nhận SIGTERM thì mọi record đã fetch đều xong”; hãy kiểm thử với thời gian xử lý dài nhất và ack mode đang dùng.

### 5.2. Ngân sách thời gian shutdown

Chọn `terminationGracePeriodSeconds` lớn hơn tổng thời gian dự kiến của:

\[
T_{\text{preStop}} + T_{\text{drain}} + T_{\text{flush}} + T_{\text{close}} + \text{dự phòng}
\]

Ví dụ nếu một message có thể xử lý 40 giây, producer flush mất 10 giây và container cần thêm thời gian đóng, giá trị 30 giây mặc định của Kubernetes có thể thiếu. Với cấu hình ví dụ, Spring lifecycle timeout là 60 giây và Pod grace là 90 giây; cần kiểm tra các phase thực tế có nằm trong ngân sách không.

Nếu dùng `preStop`, thời gian của hook **cũng tính trong** termination grace period. Không thêm sleep tùy tiện: nó có thể làm Pod giữ consumer lâu hơn và hết thời gian xử lý phần quan trọng. Chỉ dùng hook khi có mục đích xác định, ví dụ báo drain trước một tác vụ cụ thể, và có test.

### 5.3. Tránh cấu hình liveness thành kiểm tra Kafka lag

Liveness nên phản ánh tiến trình có còn có thể hoạt động hay không. Nếu broker tạm ngừng hoặc lag tăng mà liveness lập tức trả DOWN, Kubernetes có thể restart hàng loạt consumer, làm rebalance và lag nặng hơn.

Readiness có thể phản ánh app đã sẵn sàng cho traffic cần phục vụ; nếu dùng readiness cho consumer-only worker, cần biết chính xác Spring/Kubernetes sẽ làm gì khi probe fail. Chỉ làm readiness phụ thuộc vào assignment nếu mục tiêu và quy tắc rollout thực sự yêu cầu, tránh vòng lặp “chưa được assign nên không Ready, chưa Ready nên rollout không tiến triển”.

## 6. Timeout ảnh hưởng đến rebalance

Một số cấu hình Kafka quan trọng:

| Cấu hình | Ý nghĩa | Rủi ro khi đặt sai |
|---|---|---|
| `max.poll.interval.ms` | Thời gian tối đa giữa hai lần poll của consumer | Handler quá chậm có thể bị coi là không tiến triển; assignment đổi |
| `session.timeout.ms` | Thời gian phát hiện member không heartbeat trong classic protocol | Quá ngắn: rebalance do dao động; quá dài: failover chậm |
| `heartbeat.interval.ms` | Nhịp heartbeat trong classic protocol | Cần phù hợp session timeout |
| `max.poll.records` | Số record tối đa trả mỗi poll | Batch lớn có thể kéo dài thời gian xử lý |
| `group.instance.id` | Danh tính static member (nếu dùng) | ID trùng có thể gây fencing; ID không ổn định làm mất lợi ích |
| `partition.assignment.strategy` | Classic-protocol assignor | Thay đổi thiếu kế hoạch gây churn/mismatch |
| `group.protocol` | Chọn `classic` hoặc `consumer` | Từng protocol có cấu hình heartbeat/assignment khác nhau |

Ví dụ cấu hình Kafka consumer client ở một binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              configuration:
                "max.poll.records": 100
                "max.poll.interval.ms": 300000
~~~

Ở môi trường dùng `classic`, có thể cấu hình session và heartbeat tương thích với broker. Với `group.protocol=consumer`, thời gian heartbeat/session được broker điều khiển; không dùng các knob classic làm thay thế. Giá trị trên là minh họa, chưa đủ để biết batch 100 record có thể xử lý trong 5 phút hay không.

**Không tăng vô hạn timeout để che handler chậm.** Trước hết đo P95/P99 processing duration, giới hạn batch, cấu hình retry/backoff và tránh chặn consumer poll thread quá lâu.

## 7. Static membership: hữu ích nhưng không phải mặc định cho Deployment

Kafka hỗ trợ static group membership qua `group.instance.id`. Khi một member có ID ổn định khởi động lại ngắn hạn, coordinator có thể giảm một số lần rebalance. Tuy nhiên:

- ID phải duy nhất cho từng consumer member đang sống trong group.
- Một ID dùng chung giữa nhiều Pod dẫn đến fencing hoặc tranh chấp.
- Deployment rolling update tạo Pod mới với tên/UID mới và đôi lúc chạy song song với Pod cũ; khó giữ ID ổn định, duy nhất qua overlap.
- Nếu session timeout dài, consumer cũ chết bất ngờ có thể làm partition không được giao lại ngay, tăng lag.
- Spring Kafka `ConcurrentMessageListenerContainer` với concurrency lớn hơn 1 có thể thêm hậu tố vào `group.instance.id` cho các child container; cần kiểm tra cách tính ID trên phiên bản đang chạy.

Nếu thực sự cần static membership ổn định, hãy cân nhắc StatefulSet với tên Pod có ordinal cố định và chiến lược update phù hợp. Dù vậy, vẫn phải thử tình huống Pod cũ còn giữ membership khi Pod mới xuất hiện; cùng `group.instance.id` không thể được dùng đồng thời bởi hai thành viên.

Với Deployment thông thường và Pod identity động, dynamic membership thường dễ vận hành hơn. Không đặt `group.instance.id` bằng một chuỗi hằng giống nhau cho toàn bộ replica.

## 8. Offset commit, duplicate và bảo đảm giao nhận

Rolling update thường không làm mất record khỏi Kafka log; vấn đề chính là chỗ nào đã được commit và chỗ nào side effect đã xảy ra.

| Trình tự sự kiện | Sau khi Pod cũ dừng | Kết quả |
|---|---|---|
| Offset commit trước khi ghi DB thành công | Pod mới đọc sau offset đã commit | Có thể mất side effect nghiệp vụ |
| Ghi DB thành công, crash trước commit offset | Pod mới đọc lại record | Có thể thực hiện side effect hai lần |
| Side effect và marker dedupe commit trong một DB transaction | Pod mới đọc lại record | Duplicate được nhận diện và bỏ qua |
| Kafka read-process-write dùng Kafka transaction đúng scope | Transaction commit/abort cùng output/offset | Bảo vệ Kafka output và offset trong scope Kafka |

Đừng thay đổi commit mode để làm rollout “mượt” mà chưa hiểu semantics. Với external DB, HTTP hoặc thanh toán, Kafka transaction không tự đưa tác dụng phụ đó vào transaction.

### 8.1. Idempotent consumer

Mẫu dùng bảng đã xử lý với unique constraint:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Handler minh họa:

~~~java
@Service
class OrderService {

    private final ProcessedEventRepository processedEvents;
    private final OrderRepository orders;

    OrderService(
            ProcessedEventRepository processedEvents,
            OrderRepository orders) {
        this.processedEvents = processedEvents;
        this.orders = orders;
    }

    @Transactional
    public void handle(OrderCreated event) {
        boolean firstTime =
                processedEvents.insertIfAbsent("order-processing", event.eventId());

        if (!firstTime) {
            return; // đã xử lý ở Pod cũ hoặc lần giao trước
        }

        orders.applyOrderCreated(event);
    }
}
~~~

`insertIfAbsent` là phương thức nghiệp vụ cần triển khai bằng thao tác insert nguyên tử và unique constraint của DB, chẳng hạn `INSERT ... ON CONFLICT DO NOTHING` ở PostgreSQL. Không triển khai bằng “SELECT rồi INSERT” vì hai consumer có thể race. DB marker và thay đổi order phải nằm trong cùng transaction, và Spring proxy phải thực sự áp dụng `@Transactional`.

Khi function bean gọi qua service đã được proxy, transaction commit trước khi handler trả thành công. Nếu app chết sau DB commit nhưng trước offset commit, record có thể giao lại; marker giúp side effect không lặp. Nếu side effect là HTTP call hoặc gửi email, cần idempotency key ở hệ thống đích hoặc outbox vì DB transaction cục bộ không bao phủ API bên ngoài.

### 8.2. Thứ tự xử lý

Kafka duy trì thứ tự record trong **một partition** theo offset. Khi rebalance, quyền sở hữu partition thay đổi; các xử lý đang bay dở hoặc tác vụ bất đồng bộ tự tạo có thể hoàn tất sau khi partition được giao cho thành viên mới nếu ứng dụng không phối hợp đúng.

Không giả định thứ tự toàn topic khi có nhiều partition. Nếu cần thứ tự theo `orderId`, producer phải partition theo key ổn định và consumer cần tránh xử lý song song không kiểm soát trên cùng key. Dùng sequence hoặc version check để phát hiện event cũ, trùng hoặc đảo thứ tự.

## 9. KafkaBindingRebalanceListener dùng khi cần quản lý assignment

Spring Cloud Stream Kafka binder cung cấp `KafkaBindingRebalanceListener` để quan sát hoặc tùy biến hành động khi partition được revoke và assigned. Nó hữu ích cho ứng dụng có local cache, checkpoint riêng hoặc logic cần biết partition ownership.

Ví dụ chỉ log thay đổi partition:

~~~java
@Bean
KafkaBindingRebalanceListener partitionLifecycleLogger() {
    return new KafkaBindingRebalanceListener() {
        @Override
        public void onPartitionsRevokedAfterCommit(
                String bindingName,
                org.apache.kafka.clients.consumer.Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {
            log.info(
                    "Binding {} revoked partitions {}",
                    bindingName, partitions);
        }

        @Override
        public void onPartitionsAssigned(
                String bindingName,
                org.apache.kafka.clients.consumer.Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions,
                boolean initial) {
            log.info(
                    "Binding {} assigned partitions {} (initial={})",
                    bindingName, partitions, initial);
        }
    };
}
~~~

Với Spring Cloud Stream, một bean listener có thể được áp vào các Kafka consumer binding của ứng dụng. Không thực hiện I/O chậm, blocking hoặc gọi dịch vụ ngoài trong rebalance callback. Nếu cần seek đặc biệt, hiểu rõ callback và offset commit semantics trước khi triển khai.

Tài liệu binder cũng quy định không dùng `resetOffsets=true` khi cung cấp `KafkaBindingRebalanceListener`. Đừng dùng callback để gọi `seekToBeginning` mỗi khi assign trong rollout nếu mục tiêu là tiếp tục committed offset.

## 10. Rolling update cho Kafka Streams binder khác gì?

Kafka Streams chạy topology có task và local state store; khi instance thay đổi, Streams có thể:

- Chuyển active tasks giữa các instance.
- Restore state stores từ changelog topic.
- Cập nhật partition/task ownership.
- Dùng standby replicas nếu được cấu hình để giảm thời gian phục hồi.

Một app Kafka Streams có thể cần thêm thời gian để restore state trước khi xử lý hiệu quả. Spring Cloud Stream Kafka Streams binder có cơ chế binding và Streams lifecycle khác Kafka message-channel binder; không mặc định áp dụng mọi property consumer classic từ phần trên cho Streams application.

Khi triển khai Streams stateful:

- Giữ `application.id` ổn định nếu muốn tiếp tục cùng state/changelog.
- Đảm bảo state directory và changelog retention đúng nhu cầu.
- Theo dõi restore lag, task assignment và rebalance duration.
- Xem xét standby tasks và cache/state store sizing.
- Thử readiness của instance trong giai đoạn restoring, tránh hiểu “process Running” là “topology đã phục vụ đủ”.
- Không thay `application.id` tùy tiện vì đó tương đương thay logical Streams application.

## 11. RabbitMQ và Pulsar khi rolling update

Đề bài tập trung vào consumer rebalance của Kafka, nhưng cùng module Spring Cloud Stream còn có RabbitMQ và Pulsar. Hai hệ thống này không sử dụng Kafka `group.id` và Kafka partition assignor.

| Hệ thống | Cơ chế chia việc | Ảnh hưởng khi Pod rời |
|---|---|---|
| Kafka binder | Group membership và partition assignment | Rebalance, partition chuyển chủ, đọc từ committed offsets |
| RabbitMQ binder | Consumer cùng queue chia delivery; broker theo dõi ack | Delivery unacked có thể được requeue/redeliver khi channel/connection đóng |
| Pulsar binder | Subscription name + type như Shared, Failover, Key_Shared | Unacked/redelivery, chuyển active consumer hoặc ownership theo key/subscription |

### 11.1. RabbitMQ

Nhiều consumer cùng queue nhận delivery theo broker scheduling và prefetch, không có một Kafka group rebalance. Trong shutdown, message đã được giao mà chưa ack có thể được giao lại khi channel đóng. Nếu handler hoàn tất side effect trước ack, duplicate vẫn có thể xảy ra. Tăng Pod không tạo consumer group kiểu Kafka; phải kiểm tra queue name/group binding, prefetch, ack mode, retry và DLQ.

### 11.2. Pulsar

Pulsar `Shared` cho nhiều consumer dùng cùng subscription và chia message, không đảm bảo thứ tự message chung. `Failover` cho phép standby consumer nhận quyền khi active consumer rời. `Key_Shared` hướng tới giữ các message cùng key trên cùng consumer, với điều kiện/ngoại lệ liên quan redelivery và rebalance theo phiên bản broker. Không đồng nhất subscription name của Pulsar với Kafka group hoặc tùy tiện suy ra partition assignment giống Kafka.

Đối với cả RabbitMQ và Pulsar, vẫn cần shutdown có thời gian drain, ack sau xử lý, idempotency, giám sát backlog, lỗi và DLQ.

## 12. Triển khai phiên bản mới có backward compatibility

Trong một rolling update, v1 và v2 có thể cùng chạy vài phút hoặc lâu hơn. Kiểm tra:

1. **Message schema:** v1 đọc được event do producer hiện tại phát; v2 xử lý được event cũ vẫn đang nằm trong Kafka log.
2. **Database schema:** migration kiểu expand trước, code v1/v2 đều hoạt động; contract sau khi toàn bộ v1 đã rút.
3. **Header, content type và serialization:** không đổi đột ngột khiến v1 fail deserialize.
4. **Event key/partitioning:** thay key hoặc partition count có thể thay đổi ordering theo entity.
5. **Retry/DLQ:** lỗi v2 không làm message đi qua đường xử lý khác mà operator không biết.
6. **Idempotency:** event ID và dedupe key ổn định giữa hai phiên bản.
7. **External side effects:** endpoint downstream có khả năng nhận cả hai biến thể payload trong giai đoạn overlap.

Nếu thay đổi không thể backward compatible, rolling update cùng group có thể không phù hợp. Cần lên kế hoạch migration dữ liệu/schema, bảo toàn backlog và xử lý downtime có kiểm soát.

## 13. Metrics cần giám sát trong rollout

Không chỉ nhìn trạng thái `kubectl rollout status`. Một rollout thành công ở Kubernetes có thể vẫn làm consumer lag cao.

| Tín hiệu | Điều cần quan sát |
|---|---|
| Kafka group state, member count | Group có ổn định hay churn liên tục |
| Assignment theo topic/partition | Có partition không được tiêu thụ trong thời gian dài không |
| Consumer lag tổng và theo partition | Backlog có tăng ngắn hạn hay kéo dài |
| Records consumed/second | Năng lực xử lý thực tế của cả group |
| Handler P95/P99 duration | Thời gian xử lý có tăng khi v2 được đưa vào không |
| Rebalance count/duration | Tần suất và chi phí rebalance |
| Commit failures | Consumer cũ commit quá muộn hoặc đã mất ownership |
| Retry/DLQ count | Có message lỗi sau nâng cấp schema hoặc nghiệp vụ không |
| Duplicate dedupe count | Tỷ lệ message giao lại khi đổi Pod |
| DB pool, CPU, memory | Surge có quá tải downstream không |
| Pod restart, readiness, termination reason | Pod có bị kill hoặc health probe gây restart không |

### 13.1. Lệnh quan sát

~~~bash
kubectl rollout status deployment/order-processor
kubectl get pods -l app=order-processor -o wide
kubectl describe deployment order-processor
kubectl logs deployment/order-processor --since=10m
~~~

Kiểm tra Kafka group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.org:9092 \
  --describe \
  --group order-processing

kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.org:9092 \
  --describe \
  --group order-processing \
  --state
~~~

Kafka CLI, group protocol và phiên bản client có thể làm số cột/option khác nhau. Kiểm tra `CURRENT-OFFSET`, `LOG-END-OFFSET`, `LAG` và member assignment theo partition. Metrics qua Micrometer/Prometheus có thể bổ sung khi cần theo dõi lịch sử.

### 13.2. Ngưỡng cảnh báo

Đặt alert theo throughput và SLA:

- Lag tăng nhiều phút sau khi rollout đã ổn định.
- Group thiếu consumer hoạt động hoặc liên tục rebalance.
- Handler processing time vượt ngưỡng trước khi commit.
- Error/retry/DLQ tăng mạnh ở v2.
- Pod bị `OOMKilled`, `CrashLoopBackOff` hoặc vượt termination grace.
- End-to-end event age vượt SLA.

Không xem một đỉnh lag ngắn trong rebalance là sự cố nếu hệ thống rút backlog nhanh. Ngược lại, lag thấp không chứng minh side effect không bị trùng; cần dedupe/error metrics.

## 14. Kiểm thử rolling update và failure injection

Trước production, chạy thử với môi trường có broker và cùng cấu hình group, partition count, concurrency gần production:

| Kịch bản | Kỳ vọng cần xác minh |
|---|---|
| Deploy v1 với 3 Pod, nâng từng Pod lên v2 | Group hoạt động, partition được giao lại, không mất event |
| v2 join khi v1 còn sống | Group assignment thay đổi đúng, không tạo hai consumer cùng sở hữu một partition trong stable assignment |
| SIGTERM Pod đang xử lý record lâu | Handler hoàn tất hoặc event được xử lý lại an toàn |
| Pod bị SIGKILL/OOM giữa side effect và offset commit | Duplicate được dedupe, không tạo side effect hai lần |
| Kafka coordinator gián đoạn | Rebalance và recovery theo timeout phù hợp |
| v2 deserialize event cũ | Không tạo poison record/DLQ ngoài ý muốn |
| Quá nhiều Pod so với partition | Pod/consumer dư có thể idle; không hiểu lầm là đã scale throughput |
| v2 rollback về v1 | Schema và DB migration vẫn tương thích, group offsets vẫn sử dụng tiếp |
| Kafka Streams stateful rollout | Changelog restore, task assignment và state correctness |

### 14.1. Thử với event ID ổn định

Phát một tập event có ID duy nhất, ghi nhận kết quả nghiệp vụ ở database hoặc sink cuối:

- Mọi event cần xử lý có kết quả cuối cùng hợp lệ.
- Không thiếu event sau khi Pod được thay.
- Không có side effect áp dụng nhiều lần dù Kafka có thể redeliver.
- Offset của group tiến về phía trước và lag giảm sau rollout.
- DLQ không tăng do schema version mới.

Test binder đơn thuần hữu ích cho logic function nhưng không mô phỏng đầy đủ consumer group coordinator, rebalance, SIGTERM và offset commit. Dùng integration test với Kafka thật/Testcontainers và kiểm thử rollout trong Kubernetes khi mục tiêu là reliability ở môi trường triển khai.

## 15. Quy trình rollout có thể vận hành

### Trước rollout

1. Kiểm tra topic, partition count, group ID và consumer concurrency hiện tại.
2. Xác minh offset đã commit và lag trước khi cập nhật.
3. Kiểm tra tương thích schema/message, database và external API giữa v1/v2.
4. Đo P99 handler time và chọn termination grace có dự phòng.
5. Xác minh idempotency, retry/DLQ và các đường lỗi.
6. Đảm bảo cluster và downstream chịu được số Pod/connection trong `maxSurge`.
7. Chuẩn bị dashboard, alert, runbook và quyền rollback.

### Trong rollout

1. Khởi chạy v2 theo `maxSurge` và `maxUnavailable` đã chọn.
2. Quan sát readiness và Kafka group membership/partition assignment.
3. Khi Pod v1 nhận tín hiệu dừng, theo dõi graceful shutdown/commit/leave.
4. Theo dõi lag, processing duration, rebalance và DLQ.
5. Tạm dừng rollout nếu dữ liệu không tương thích, error hoặc lag vượt ngưỡng.
6. Chỉ tiếp tục đợt thay tiếp theo khi hệ thống đã ổn định.

### Sau rollout

1. Xác nhận tất cả Pod chạy đúng image v2.
2. Group có member count và assignment mong đợi.
3. Lag giảm về mức bình thường, không còn partition bị treo.
4. Không có error/duplicate side effect bất thường.
5. Ghi lại duration, rebalance count, peak lag và kết quả thử nghiệm.
6. Điều chỉnh partition/concurrency và shutdown budget nếu kết quả không đạt SLO.

## 16. Troubleshooting và rollback

| Triệu chứng | Nguyên nhân nên kiểm tra | Hành động |
|---|---|---|
| Lag tăng mạnh khi rollout | Eager rebalance, v2 xử lý chậm, thiếu capacity | Kiểm tra assignment, pause rollout, so rate |
| Partition không được assign lâu | Member session chưa hết, static ID conflict, group lỗi | Xem group state, timeout và logs coordinator |
| Message xử lý trùng | Side effect thành công trước offset commit; Pod bị kill | Bật/cải thiện idempotency, xem ack mode |
| Consumer liên tục join/leave | Liveness restart, OOM, timeout quá ngắn | Kiểm tra Pod events, resource limits, heartbeat |
| `CommitFailedException` hoặc rebalance errors | Member mất quyền sở hữu partition hoặc xử lý quá lâu | Kiểm tra max poll, handler duration, rebalancing |
| Pod Ready nhưng không consume | Chưa được assign hoặc không còn partition dư | Kiểm tra group assignment, partition count |
| Rollout bị stalled | Readiness không đạt, image lỗi, thiếu tài nguyên | Xem Deployment conditions và Pod events |
| Rollback nhưng v1 lỗi schema | v2 đã phát payload/DB schema không tương thích | Cần kế hoạch compatibility/roll-forward an toàn |

Lệnh vận hành:

~~~bash
kubectl rollout pause deployment/order-processor
kubectl rollout resume deployment/order-processor
kubectl rollout undo deployment/order-processor
~~~

Rollback thay image/Pod template theo Deployment history; nó **không đưa Kafka committed offsets hoặc database về trạng thái cũ**. Nếu v2 đã commit offset hoặc ghi schema mới, v1 cần tương thích với trạng thái đó. Không tự reset offset để “undo” một deployment.

## 17. Những nhầm lẫn thường gặp

1. **Đổi group ID khi lên v2:** tạo nhóm offset khác; không còn là rolling update cùng group.
2. **Tin rằng Pod Ready tức là đã nhận partition:** HTTP readiness và Kafka assignment là hai tín hiệu khác nhau.
3. **Coi maxUnavailable=0 là zero downtime:** chỉ là ràng buộc số Pod Available; rebalance vẫn có thể tạm dừng xử lý.
4. **Đặt replicas quá số partition:** consumer/Pod dư không giúp tăng parallelism của group.
5. **Tăng concurrency không đo downstream:** có thể gây quá tải DB và rebalance/retry tăng.
6. **Dùng static group.instance.id giống nhau cho mọi Pod:** dễ bị fencing; cần ID duy nhất, ổn định.
7. **Bật cooperative assignor mà không xác minh cấu hình thực tế:** trong classic protocol có thể vẫn chọn RangeAssignor.
8. **Dùng timeout classic cho group.protocol=consumer:** protocol mới quản lý heartbeat/session khác.
9. **SIGTERM xong là giả định message đã commit:** phải xác minh listener stop, processing và offset.
10. **Để shutdown grace quá ngắn:** Pod bị SIGKILL khi còn work/producer flush.
11. **Commit offset trước side effect:** có thể làm mất tác dụng nghiệp vụ khi Pod chết.
12. **Không idempotent:** record được giao lại gây thanh toán, cập nhật hoặc email lặp.
13. **Gọi seekToBeginning trong rebalance callback:** có thể vô tình phát lại lịch sử.
14. **Liveness fail khi broker mất kết nối:** tạo restart storm và thêm rebalance.
15. **Coi RabbitMQ/Pulsar như Kafka group:** các broker có cơ chế assignment và acknowledgment khác nhau.
16. **Rollback image đồng nghĩa rollback dữ liệu:** offsets và DB state không tự quay về quá khứ.

## Kết luận

Rolling update của Spring Cloud Stream consumer trong cùng Kafka group là quá trình thay dần member đang sở hữu các partition. Kafka có thể rebalance khi member mới tham gia hoặc member cũ rời; cooperative assignment và protocol mới có thể giảm gián đoạn trong điều kiện phù hợp, nhưng không miễn trừ yêu cầu xử lý message giao lại.

Thiết kế đáng tin cậy cần giữ `group` cố định, chọn số Pod/concurrency tương xứng số partition, phối hợp RollingUpdate với graceful shutdown, không commit offset sớm, và làm side effect idempotent. Quan sát group state, partition assignment, lag, rebalance duration, handler time và lỗi trong suốt rollout. Kiểm thử SIGTERM, SIGKILL, schema compatibility và rollback trước khi coi chiến lược là an toàn cho production.

## Tài liệu tham khảo

- [Spring Cloud Stream — Partitioning with the Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — KafkaBindingRebalanceListener](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/rebalance_listener.html)
- [Spring Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Apache Kafka 4.4 — Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Apache Kafka 4.4 — Group Configs](https://kafka.apache.org/44/configuration/group-configs/)
- [Kubernetes — Deployments / Rolling Update](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Apache Pulsar — Messaging and Subscription Types](https://pulsar.apache.org/docs/4.2.x/concepts-messaging/)

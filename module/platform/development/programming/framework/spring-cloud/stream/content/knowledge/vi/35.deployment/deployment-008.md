# Tự động mở rộng theo lag hoặc độ sâu hàng đợi

Trong kiến trúc xử lý sự kiện, tải không chỉ thể hiện qua CPU của ứng dụng. Một consumer Spring Cloud Stream có thể dùng rất ít CPU vì đang chờ database, nhưng **consumer lag** của Kafka hoặc **độ sâu hàng đợi** của RabbitMQ/Pulsar vẫn tăng nhanh. Nếu chỉ tăng replica theo CPU, hệ thống có thể không kịp xử lý sự kiện trong thời hạn nghiệp vụ. **Event-driven autoscaling** điều chỉnh số instance xử lý theo khối lượng công việc đang chờ, đồng thời kiểm soát năng lực tối đa và chi phí.

Bài thuộc chương **Triển khai** trong module `SPRING_CLOUD_STREAM`. Phạm vi là ứng dụng Spring Cloud Stream với mô hình hàm `Supplier`/`Function`/`Consumer`, binding và binder kết nối **Kafka, RabbitMQ hoặc Pulsar**. Chúng ta sẽ cấu hình autoscaling bằng Kubernetes, HPA và KEDA, tính toán mức replica dựa trên backlog, đánh giá consumer group/partition/subscription, phân biệt scale-to-zero với scale-down thông thường và kiểm thử trong điều kiện retry, DLQ, rebalance hay broker mất kết nối.

## 1. Vì sao CPU không đủ để quyết định scale?

Giả sử service `order-projection` nhận sự kiện đơn hàng để cập nhật database:

```text
Producer -> Broker -> Consumer Spring Cloud Stream -> Database
                |                  |
                |                  +-- CPU: 25%, chờ DB chậm
                +-- Backlog tăng từ 5.000 lên 80.000 events
```

Khi database chậm, consumer có thể chủ yếu chờ I/O. CPU dưới ngưỡng 60% không kích hoạt CPU autoscaling, trong khi dữ liệu trở nên ngày càng cũ. Một sự cố tạm thời ở producer cũng có thể tạo đột biến backlog mà CPU trước đó không phản ánh. Đối với consumer xử lý message, lag/backlog là chỉ số gần với **công việc chưa hoàn tất** hơn CPU, mặc dù vẫn cần CPU, bộ nhớ và latency để phát hiện nút thắt khác.

Một autoscaler tốt không chỉ trả lời "queue dài bao nhiêu?" mà còn phải xét **queue đang dài lên hay ngắn đi**, **mỗi replica thực sự xử lý bao nhanh** và **có thể tăng song song đến đâu**. Tăng replica không làm database nhanh hơn nếu database đã bão hòa; ngược lại, tăng quá nhanh có thể làm hệ thống downstream sập vì quá tải.

## 2. Các thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Nguồn đo điển hình |
|---|---|---|
| Backlog | Số message chưa được xử lý/xác nhận theo một điểm quan sát | Queue/broker/subscription |
| Consumer lag | Khoảng cách giữa offset mới nhất và offset đã commit của consumer group | Kafka group/topic/partition |
| Queue depth | Số message còn trong queue; cần phân biệt ready và unacknowledged | RabbitMQ management/queue API |
| Subscription backlog | Số entry/message chưa được subscription xác nhận theo semantics của Pulsar | Pulsar Admin/metrics |
| Arrival rate \(\lambda\) | Số message mới đến mỗi giây | Broker producer metrics |
| Processing rate \(\mu\) | Số message được xử lý thành công mỗi giây trên một worker/replica | Consumer/application metrics |
| Drain time | Thời gian ước tính để xóa backlog khi tổng năng lực xử lý vượt tốc độ đến | Tính toán hoặc đo tải |
| Desired replicas | Số replica autoscaler mong muốn theo metric và chính sách | HPA/KEDA |
| Ready replicas | Số replica thực sự sẵn sàng xử lý sau startup, binding và health checks | Kubernetes Deployment |

Các metric này không đồng nhất. Ví dụ Kafka lag là khoảng cách offset, không phải số "business events" chính xác nếu có transaction, log compaction hoặc record được lọc. RabbitMQ có message **ready** và message **unacknowledged**; Pulsar backlog được tính theo subscription và cursor. Khi thiết kế ngưỡng, phải hiểu scaler đang đọc metric nào và cách nó xử lý ack/redelivery.

## 3. Kiến trúc Kubernetes HPA và KEDA

Kubernetes **Horizontal Pod Autoscaler (HPA)** tự điều chỉnh số Pod replica theo metric. HPA thường dùng CPU/memory thông qua Metrics Server; muốn dùng broker backlog cần metric ngoài do adapter cung cấp. **KEDA (Kubernetes Event-driven Autoscaling)** đọc metric từ nguồn sự kiện và quản lý HPA tương ứng cho workload.

```text
             Kafka / RabbitMQ / Pulsar
                       |
                 broker metrics
                       |
                       v
                  KEDA Scaler
                       |
               ScaledObject + metrics
                       |
                       v
                Kubernetes HPA
                       |
                 desiredReplicas
                       |
                       v
             Spring Cloud Stream Deployment
                 Pod A / Pod B / Pod C
```

KEDA đọc lag/backlog theo chu kỳ `pollingInterval`. Khi workload đang hoạt động, HPA dùng external metric để quyết định replica theo chu kỳ của HPA controller. KEDA còn hỗ trợ kích hoạt từ 0 replica đối với những trigger có semantics và điều kiện phù hợp. KEDA không thay thế cấu hình consumer group, subscription hay quy trình xử lý lỗi của ứng dụng.

> **Giới hạn phiên bản:** ví dụ YAML dưới đây minh họa các metadata phổ biến của KEDA. Tên trường, chế độ xác thực, khả năng scale-to-zero và cách tính lag có thể thay đổi theo phiên bản KEDA/scaler. Luôn đối chiếu CRD và tài liệu tương ứng với cluster đang triển khai; test với broker thật trước khi áp dụng ngưỡng production.

## 4. Chuẩn bị Spring Cloud Stream consumer có danh tính ổn định

Để autoscaling không biến thành nhiều ứng dụng độc lập nhận trùng message, mỗi replica của cùng workload cần dùng **định danh subscription/consumer group nhất quán**. Với Kafka Binder, đặt `group` cố định; với Pulsar cần subscription name ổn định; với Kafka Streams các instance của cùng topology dùng `applicationId` chung.

Ví dụ consumer xử lý đơn hàng:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String eventId, String orderId, String status) {}

@Configuration(proxyBeanMethods = false)
class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderEvent> processOrder(OrderService orderService) {
        return event -> orderService.applyIdempotently(event);
    }
}
```

Trong ví dụ, `OrderService` là thành phần nghiệp vụ do ứng dụng triển khai; `applyIdempotently` phải hoàn tất việc cập nhật dữ liệu bền vững hoặc chuyển quyền sở hữu công việc an toàn **trước khi handler trả thành công**. Nếu chỉ đưa event vào thread pool rồi trả về, cơ chế ack/offset của binder có thể đánh dấu message hoàn thành trước khi công việc thật sự xong.

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-projection
          consumer:
            concurrency: 1
```

Đây là phần binding chung. Cần bổ sung dependency binder và cấu hình broker tương ứng. Giá trị `concurrency` ở đây chỉ minh họa cho Kafka Binder hoặc binder hỗ trợ; ý nghĩa cụ thể của concurrency phải được kiểm tra theo binder, không tự suy ra nó giống nhau trên Kafka, RabbitMQ và Pulsar.

## 5. Triển khai Deployment làm mục tiêu scale

HPA/KEDA scale một workload Kubernetes đã được khai báo, thường là `Deployment`. Ví dụ rút gọn:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-projection
  namespace: event-processing
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-projection
  template:
    metadata:
      labels:
        app: order-projection
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: application
          image: registry.example.com/order-projection:1.0.0
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
```

Các thuộc tính `definition`, `destination` và `group` được khai báo trong `application.yml` như phần 4, hoặc cấp qua ConfigMap đã kiểm chứng. Tránh tự suy đoán tên biến môi trường từ binding có dấu gạch ngang và chỉ số `-in-0`; hãy xác minh cấu hình binding thực sự được nạp. Trong production, thêm readiness/liveness/startup probes, securityContext, service account, image pull secret và resource policy phù hợp.

Khi KEDA quản lý replica, không đặt đồng thời một HPA độc lập khác cũng scale cùng `Deployment` theo những quy tắc mâu thuẫn. KEDA thường tạo/kiểm soát HPA gắn với `ScaledObject`; hai HPA cùng ghi vào `scale` subresource có thể khiến số replica dao động ngoài dự kiến.

## 6. Kafka lag: đo theo consumer group và partition

Kafka lưu record theo partition. Lag của một consumer group thường được ước tính từ log end offset trừ committed offset ở mỗi partition, sau đó tổng hợp. Vì offset phải gắn với group, một nhóm consumer **chưa từng commit offset** có thể không có lag rõ ràng cho scaler. Khi đó cần cấu hình offset reset/init hoặc bootstrap group một cách có kế hoạch.

```text
Topic orders.events (4 partitions)

P0: end=12000, commit=10500 -> lag=1500
P1: end= 8800, commit= 8300 -> lag= 500
P2: end= 9300, commit= 8500 -> lag= 800
P3: end= 7000, commit= 6500 -> lag= 500
--------------------------------------------
Total lag (minh họa)             = 3300
```

Khi consumer group cùng nhau xử lý topic, mỗi partition chỉ được giao cho **một consumer trong group tại một thời điểm**. Do đó số consumer thực sự làm việc trên một topic không thể vượt số partition của topic đó, dù Kubernetes chạy nhiều Pod hơn. Một Pod có thể có nhiều consumer thread (`concurrency`), nên giới hạn hữu ích phụ thuộc tổng số consumer, không chỉ Pod.

Nếu consumer group xử lý nhiều topic, phải quyết định scale theo tổng lag hay một topic cụ thể. Trigger chỉ theo `orders.events` sẽ không thấy backlog ở `payments.events`. Nếu có nhiều trigger, cần hiểu HPA tổng hợp quyết định replica và tránh nhân đôi các metric tương quan gây scale quá cao.

## 7. KEDA Kafka ScaledObject — ví dụ cơ bản

Giả sử Kafka topic `orders.events` có 12 partition, mỗi Pod chạy một Kafka consumer (`concurrency: 1`) và dùng group `order-projection`:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: order-projection-kafka
  namespace: event-processing
spec:
  scaleTargetRef:
    name: order-projection
  pollingInterval: 30
  cooldownPeriod: 300
  minReplicaCount: 1
  maxReplicaCount: 12
  triggers:
    - type: kafka
      metadata:
        bootstrapServers: kafka-bootstrap.messaging.svc:9092
        consumerGroup: order-projection
        topic: orders.events
        lagThreshold: "1000"
        activationLagThreshold: "10"
```

Ý nghĩa các tham số:

| Thuộc tính | Ý nghĩa |
|---|---|
| `scaleTargetRef.name` | Deployment cần tăng/giảm replica |
| `pollingInterval: 30` | KEDA kiểm tra trạng thái trigger theo chu kỳ khoảng 30 giây |
| `cooldownPeriod: 300` | Thời gian chờ khi KEDA xử lý scale về 0 theo cơ chế kích hoạt; không nên hiểu là toàn bộ HPA scale-down policy |
| `minReplicaCount: 1` | Luôn giữ ít nhất một Pod, tránh khởi tạo group lần đầu từ 0 |
| `maxReplicaCount: 12` | Không cho tăng quá 12 Pod theo chính sách autoscaling này |
| `consumerGroup` | Phải trùng group của Spring Cloud Stream consumer |
| `topic` | Topic cần đo lag; cần khớp destination thực |
| `lagThreshold: "1000"` | Ngưỡng lag mục tiêu tính theo một replica trong mô hình scaler |
| `activationLagThreshold: "10"` | Ngưỡng kích hoạt scaler khỏi trạng thái không hoạt động theo semantics KEDA |

`lagThreshold` **không phải** mệnh lệnh "lag chạm 1.000 thì tăng ngay một Pod". Scaler cung cấp metric; HPA so với target và số replica hiện tại để ước lượng desired replicas. Việc scale thực tế còn bị giới hạn bởi metric caching, chu kỳ HPA, `minReplicaCount`, `maxReplicaCount`, partition cap và policy ổn định hóa.

Ví dụ này giả định Kafka broker có thể kết nối từ KEDA operator. Production cần cấu hình TLS/SASL qua `TriggerAuthentication`/`ClusterTriggerAuthentication` và Kubernetes Secret; không đặt mật khẩu trong ScaledObject hoặc Git.

## 8. Tính số replica theo lag không được nhầm với hiệu quả xử lý

Một mô hình xấp xỉ của scaler dựa vào backlog là:

\[
R_{desired} \approx \left\lceil\frac{L}{L_{target\;per\;replica}}\right\rceil
\]

Với total lag (L=8.400) và mục tiêu 1.000 record/replica, tính toán thô cho ra khoảng 9 replica trước khi áp dụng giới hạn khác. Tuy nhiên kết quả thực tế của KEDA/HPA có thể khác vì độ phân giải metric, hoạt động trigger và cap theo partition. Nếu topic chỉ có 6 partition và mỗi Pod có một consumer, chỉ 6 Pod có thể nhận partition; thêm Pod thứ 7 không làm lag giảm nhanh hơn.

Ngoài ra, 1.000 record xử lý trong một giây rất khác 1.000 record cần một phút. Cùng backlog nhưng payload khó, database chậm hoặc retry nhiều sẽ cần một số replica khác. Nên chọn ngưỡng dựa trên **benchmark thành công mỗi giây** và mục tiêu độ trễ, không chọn theo một số tròn ngẫu nhiên.

## 9. Consumer lag không phải ứng dụng đang khỏe

Nếu consumer liên tục đọc record và commit offset trước khi side effect bền vững, Kafka lag có thể bằng 0 trong khi công việc thật vẫn còn trong thread pool hoặc database. Scaler sẽ giảm Pod vì nghĩ queue đã rỗng, làm mất công việc đang chạy nếu không có drain.

Thiết kế cần đảm bảo:

1. Handler không báo thành công trước khi tác động nghiệp vụ đạt trạng thái an toàn.
2. Có idempotency để redelivery sau crash không gây tác động lặp.
3. Có metric riêng cho processing errors, in-flight work và end-to-end event age.
4. Probe và shutdown bảo đảm Pod không bị hủy khi còn công việc quan trọng.

Với Kafka Streams stateful, throughput chịu ảnh hưởng task assignment, state store và state restore. Lag tăng tạm thời trong khi rebalance/restore không nhất thiết là thiếu Pod. Scale quá nhạy trong giai đoạn restore có thể gây thêm rebalance, khiến lag tăng ngược lại.

## 10. Kafka partition cap và concurrency

Cho một topic duy nhất với 8 partition, số instance có thể đem lại parallelism hữu ích bị giới hạn bởi partition và concurrency:

| Replica | Consumer/Pod | Tổng consumer | Active consumer có partition tối đa |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 1 |
| 2 | 1 | 2 | 2 |
| 4 | 2 | 8 | 8 |
| 8 | 2 | 16 | 8 |
| 12 | 2 | 24 | 8 |

Khi mỗi Pod có `concurrency: 2`, có thể đạt 8 consumer trên 4 Pod, nhưng còn phụ thuộc assignment và cân bằng tài nguyên. Nếu tăng tối đa 12 Pod mà topic chỉ có 8 partition, tài nguyên dư không làm thêm partition nào được xử lý song song.

KEDA Kafka scaler có những tùy chọn kiểm soát giới hạn này theo partition và idle consumer trong các phiên bản tương ứng; không mặc định mọi cấu hình tự cap chính xác khi nhiều topic và nhiều consumer thread trên Pod. Hãy chọn `maxReplicaCount` dựa trên số partition **và** concurrency thực tế, đồng thời đo consumer assignment sau khi scale.

## 11. RabbitMQ: đo queue depth đúng queue của consumer group

RabbitMQ không dùng Kafka offset lag. Đơn vị mà RabbitMQ Binder thường tạo là **queue** cho một `destination` và consumer `group`. Producer publish vào exchange; binder/queue binding đưa message vào queue tương ứng. Autoscaler phải đọc **đúng queue** đang được consumer xử lý, không đọc tên exchange hoặc tên function theo phỏng đoán.

```text
Producer -> exchange orders.events
                   |
                   v
         queue orders.events.order-projection
                   |
             consumers A, B, C
                   |
              Database
```

Trong trường hợp dùng quy ước đặt tên mặc định, queue có thể có tên `orders.events.order-projection`; binder có thể đổi quy tắc đặt tên dựa trên `prefix`, `queueNameGroupOnly`, partitioning hoặc cấu hình topology. **Kiểm tra tên queue thực tế trên RabbitMQ Management UI/API** thay vì chỉ sao chép ví dụ.

RabbitMQ có các metric quan trọng:

| Metric | Điều nó phản ánh | Lưu ý khi autoscaling |
|---|---|---|
| `messages_ready` | Message còn sẵn để giao cho consumer | Phù hợp để nhận biết backlog chờ lấy |
| `messages_unacknowledged` | Message đã giao nhưng consumer chưa ack | Có thể tăng khi prefetch cao hoặc xử lý chậm |
| `messages` / tổng queue | Tổng message ready và unacknowledged theo cách API đo | Cần biết scaler dùng AMQP hay HTTP và metric nào |
| `publish_rate` | Message đến theo thời gian | Để ước lượng tốc độ tạo backlog |
| `ack_rate` | Message được ack theo thời gian | Để ước lượng tốc độ xử lý bền vững |
| `consumer_count` | Số consumer gắn với queue | Không đồng nghĩa số consumer đều active |

Queue depth tăng có thể vì consumer bị tắc, DB lỗi, broker flow control hoặc producer quá nhanh. Tăng số Pod có thể giúp nếu nguyên nhân là thiếu năng lực consumer; nếu cùng dùng một database đã bão hòa, scale thêm có thể khiến queue chờ lâu hơn do nhiều kết nối DB tranh tài nguyên.

## 12. RabbitMQ: KEDA ScaledObject theo queue length

Ví dụ queue do RabbitMQ Binder provision và ứng dụng cần giữ ít nhất một Pod:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: order-projection-rabbitmq
  namespace: event-processing
spec:
  scaleTargetRef:
    name: order-projection
  pollingInterval: 30
  cooldownPeriod: 300
  minReplicaCount: 1
  maxReplicaCount: 10
  triggers:
    - type: rabbitmq
      metadata:
        hostFromEnv: RABBITMQ_URL
        queueName: orders.events.order-projection
        mode: QueueLength
        value: "100"
        activationValue: "5"
```

Ở đây `value: "100"` là mục tiêu xấp xỉ 100 message tồn đọng trên một replica theo semantics metric của RabbitMQ scaler, **không** phải cấu hình giới hạn queue của broker. `activationValue` là ngưỡng kích hoạt. Hãy xác minh tham số theo phiên bản KEDA đang chạy.

Biến `RABBITMQ_URL` cần có trong container của Deployment vì scaler đọc nó thông qua `hostFromEnv` ở các phiên bản KEDA hỗ trợ. Ví dụ cách inject từ secret:

```yaml
env:
  - name: RABBITMQ_URL
    valueFrom:
      secretKeyRef:
        name: rabbitmq-consumer-credentials
        key: url
```

Ví dụ secret key tên `url` là **tham chiếu**, không đưa URL chứa username/password vào file YAML được commit. Nên cấp quyền đọc metrics tối thiểu; KEDA có thể dùng `TriggerAuthentication` để truy cập broker theo cơ chế riêng, tách credential của scaler khỏi runtime application. Các tham số kết nối AMQP/HTTP Management API, TLS và vhost phụ thuộc KEDA scaler mode và phiên bản, cần kiểm thử với cùng cấu hình broker production.

## 13. RabbitMQ: prefetch và số consumer phải được đo cùng depth

RabbitMQ Binder có các thuộc tính `prefetch`, `concurrency` và các lựa chọn provisioning khác. Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-projection
          consumer:
            concurrency: 2
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              prefetch: 20
```

`concurrency: 2` tạo nhiều consumer trong một Pod theo khả năng binder/container. `prefetch: 20` cho phép consumer nhận trước nhiều message chưa ack; message có thể chuyển từ `ready` sang `unacknowledged` rất nhanh dù xử lý nghiệp vụ vẫn chậm. Nếu autoscaler chỉ nhìn `ready`, nó có thể giảm replica trước khi toàn bộ công việc in-flight hoàn tất. Hãy đo thời gian xử lý thực tế, prefetch và cả ready/unacked trước khi chọn metric/threshold.

Với queue **Single Active Consumer**, nhiều consumer cùng đăng ký nhưng chỉ một active consumer được giao message. Scale từ 1 lên 10 Pod không tạo 10 active consumer cho cùng queue; các Pod còn lại chủ yếu là standby. Nếu phải tăng throughput và vẫn giữ thứ tự theo key, cần thiết kế nhiều queue phân vùng theo key, sau đó autoscale/đặt năng lực cho từng queue hoặc một worker đọc nhiều queue theo chính sách. Không bật autoscale theo queue length rồi kỳ vọng SAC biến thành xử lý song song.

Nếu queue có TTL, DLX hoặc max-length policy, việc thay đổi backlog không hoàn toàn do consumer ack. Message có thể bị expire hoặc dead-letter. Scaler nhìn queue rỗng không chứng minh message đã được xử lý thành công; cần theo dõi reject, retry, DLQ và tỉ lệ ack nghiệp vụ.

## 14. Pulsar: backlog là chỉ số theo subscription

Pulsar quản lý trạng thái message được xử lý theo **subscription cursor**. Với durable subscription, broker lưu backlog của subscription; nhiều consumer có thể cùng tham gia một subscription theo loại `Shared`, `Key_Shared`, `Failover` hoặc `Exclusive`. Autoscaler phải biết **tên topic đầy đủ** và **tên subscription**, không chỉ tên consumer bean.

```text
Topic: persistent://acme/orders/orders.events
                      |
                      +--> Subscription order-projection
                      |        backlog = 12.000 messages
                      |        Pod A / Pod B / Pod C
                      |
                      +--> Subscription audit-service
                               backlog = 80 messages
```

Hai subscription có backlog độc lập. Nếu KEDA đo `audit-service` nhưng scale Deployment `order-projection`, hai hệ thống sẽ vận hành sai. Phải đối chiếu tên subscription thực tế mà Pulsar Binder tạo từ `group` hoặc thuộc tính binding/subscription tương ứng ở release đang sử dụng.

Pulsar backlog còn chịu tác động của ack mode, negative acknowledgment/redelivery, message TTL, DLQ và retention. Một subscription có backlog cao nhưng đang chuyển message giữa retry topic và DLQ cần được điều tra trước khi scale; autoscaling không tự sửa poison message.

## 15. Pulsar: KEDA ScaledObject minh họa

KEDA có Pulsar scaler dựa trên subscription backlog trong những phiên bản hỗ trợ. Ví dụ cấu trúc thường gặp:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: order-projection-pulsar
  namespace: event-processing
spec:
  scaleTargetRef:
    name: order-projection
  pollingInterval: 30
  cooldownPeriod: 300
  minReplicaCount: 1
  maxReplicaCount: 8
  triggers:
    - type: pulsar
      metadata:
        adminURL: http://pulsar-admin.messaging.svc:8080
        topic: persistent://acme/orders/orders.events
        subscription: order-projection
        msgBacklogThreshold: "1000"
        activationMsgBacklogThreshold: "10"
        isPartitionedTopic: "true"
```

**Kiểm tra kỹ phiên bản:** Pulsar scaler có thể thay đổi tên metadata và điều kiện tính backlog đối với partitioned topic. `adminURL` trong ví dụ là URL nội bộ minh họa; production nên dùng HTTPS với token/mTLS và `TriggerAuthentication` nếu cần. Không tạo Kubernetes Secret chứa token ngay trong tài liệu. Xác minh endpoint Admin API có quyền đọc subscription statistics nhưng không cần quyền superuser nếu có thể cấp quyền hẹp.

`msgBacklogThreshold` là mục tiêu backlog cho một replica theo scaler; nó không phải số partition. `isPartitionedTopic` phải phản ánh topology thực; khi sai, scaler có thể đo thiếu hoặc không tìm được metadata. Kiểm tra topic/subscription thực tế bằng Pulsar Admin API trước khi tin chỉ số scaler.

## 16. Pulsar subscription type quyết định giới hạn mở rộng

| Subscription | Hành vi khi tăng nhiều consumer | Tác động tới autoscaling |
|---|---|---|
| `Exclusive` | Chỉ một consumer được subscribe trong cùng subscription | Scale Pod không tăng đồng thời worker tiêu thụ; có thể gây kết nối thất bại |
| `Failover` | Có active/standby, đối với partitioned topic có thể phân bố active ownership theo partition | Throughput phụ thuộc số partition và active assignment |
| `Shared` | Broker phân phối message cho nhiều consumer | Có thể tăng song song, không bảo đảm thứ tự toàn cục |
| `Key_Shared` | Điều phối theo key | Có thể tăng theo key, cần key và batching đúng semantics |

Autoscaling phải giữ `subscription` ổn định khi tăng Pod. Nếu mỗi Pod tạo subscription riêng, mỗi subscription có thể nhận bản sao logic của luồng dữ liệu thay vì chia tải, làm output nghiệp vụ trùng và backlog metric gây hiểu nhầm.

Với một số subscription type, nhiều consumer trên partitioned topic vẫn không có hiệu quả tuyến tính vì key nóng hoặc giới hạn active ownership. Vì thế, chọn `maxReplicaCount` sau khi đo **consumer thực sự nhận message**, không chỉ dựa trên số partition.

## 17. So sánh ba loại metric trước khi chọn scaler

| Đặc điểm | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Điểm theo dõi | Consumer group + topic + partition | Queue cụ thể của consumer group | Durable subscription + topic |
| Metric chính | Offset lag | Queue depth / ready / unacked | Subscription backlog |
| Đơn vị song song | Partition/consumer group | Consumer/queue, phụ thuộc SAC/exclusive | Subscription type, partition/key |
| Hoàn thành công việc | Commit offset | Ack message | Ack/cursor advancement |
| Ghi nhận lỗi | Retry/DLQ/error handling riêng | Nack/requeue/DLX/DLQ | Negative ack/redelivery/DLQ |
| Trường hợp scale vô ích | Hết partition hoặc hot partition | SAC/exclusive hoặc downstream bão hòa | Exclusive/Failover limit hoặc hot key |
| Scale-to-zero | Cần group/offset metric đọc được khi 0 Pod | Queue phải tồn tại và scaler truy cập được | Durable subscription phải tồn tại và backlog đọc được |

Không gom các giá trị `lag = 1000`, `queue length = 1000`, `Pulsar backlog = 1000` thành một ngưỡng chung rồi coi chúng tương đương. Thời gian xử lý, kích thước message, logic ack và chi phí khởi động có thể rất khác. Mỗi luồng nên benchmark để xác định ngưỡng riêng.

## 18. Công thức ước lượng replica theo mục tiêu drain time

Giả sử tốc độ đến là \(\lambda\) message/giây, mỗi replica xử lý thành công bền vững \(\mu\) message/giây khi ổn định, backlog hiện tại là \(L\) và muốn xóa backlog trong thời gian \(T\) giây.

Với \(R\) replica, năng lực ròng xử lý backlog là \(R\mu-\lambda\) nếu dương. Ước lượng:

\[
T_{drain}\approx\frac{L}{R\mu-\lambda}\quad\text{khi }R\mu>\lambda
\]

Để đạt \(T_{drain}\le T\), số replica lý thuyết cần ít nhất:

\[
R\ge\left\lceil\frac{\lambda + L/T}{\mu}\right\rceil
\]

Ví dụ: backlog 24.000 message, producer vẫn gửi 600 message/giây, một Pod đo được 200 message/giây, muốn xóa backlog trong 120 giây:

\[
R\ge\left\lceil\frac{600+24000/120}{200}\right\rceil=4
\]

Bốn Pod có năng lực ròng \(4\times200-600=200\) message/giây, nên cần khoảng 120 giây. Năm Pod có năng lực ròng 400 message/giây, nên ước tính khoảng 60 giây, có thêm dự phòng cho dao động. Đây là **ước lượng đơn giản**: bỏ qua startup delay, rebalance, retry, payload skew, network, broker và downstream limits; số Pod hiệu dụng còn bị giới hạn bởi partitions/consumer assignment.

Nếu \(R\mu\le\lambda\), backlog sẽ không tự giảm dù autoscaler tiếp tục giữ đúng \(R\). Cần tăng năng lực hợp lệ, tối ưu xử lý, điều tiết producer hoặc giảm độ trễ downstream. Không đặt threshold nhỏ vô hạn để ép HPA tăng vượt partition hoặc database capacity.

## 19. Chọn threshold theo SLO thay vì số đẹp

Các bước chọn `lagThreshold`/`value`/`msgBacklogThreshold`:

1. Chọn SLO: ví dụ "95% event được xử lý trong 60 giây" hoặc "drain 50.000 message trong 5 phút sau burst".
2. Đo latency và throughput **đã ack/commit thành công** của một Pod ở tải thực tế.
3. Ước lượng backlog cho phép trong thời gian SLO theo arrival rate và thời gian xử lý.
4. Chọn target backlog trên Pod sao cho autoscaler có thể tăng kịp trước khi SLO bị vượt.
5. Đặt `maxReplicaCount` không vượt mức song song thực tế và ngưỡng downstream chịu được.
6. Thử nghiệm burst, lỗi broker và database chậm; đo thời gian scale-out và drain.
7. Điều chỉnh threshold, polling, stabilization/cooldown theo kết quả.

Little's Law \(L\approx\lambda W\) mô tả quan hệ trung bình giữa số công việc trong hệ thống, tốc độ đến và thời gian ở trong hệ thống khi tương đối ổn định. Nó hữu ích để kiểm tra độ hợp lý của threshold, **không** bảo đảm thời gian xử lý cho từng message hoặc một hệ thống đang tăng backlog nhanh.

## 20. Scale-to-zero: hấp dẫn nhưng không luôn phù hợp

KEDA có khả năng scale từ 0 lên số replica dương khi trigger hỗ trợ và được cấu hình. Tuy nhiên scale-to-zero chỉ an toàn khi **bản thân broker giữ được message và scaler vẫn quan sát được backlog khi không có consumer**.

Đặt `minReplicaCount: 0` cần trả lời:

- Kafka consumer group đã tồn tại và có committed offset chưa? Scaler xử lý group/offset mới như thế nào?
- RabbitMQ queue đã được provision thành durable queue chưa, hay ứng dụng cần chạy để khai báo nó?
- Pulsar durable subscription đã được tạo chưa, hay subscription chỉ xuất hiện khi consumer kết nối lần đầu?
- Ai duy trì tên topic/group/subscription khi Pod bằng 0?
- Tốc độ scale từ 0 có đủ nhanh để đạt latency SLO không?
- Startup có cần schema registry, database, DNS, TLS, state restore hoặc topic provisioning?
- Nếu metric endpoint lỗi lúc 0 Pod, có phương án an toàn nào không?

**Khuyến nghị khởi đầu:** với pipeline nghiệp vụ cần latency thấp, message ordering chặt, Kafka Streams có state store hoặc chưa kiểm chứng bootstrap, giữ `minReplicaCount: 1`. Chỉ giảm về 0 sau khi đã kiểm thử đầy đủ việc provision, metric, warm-up, redelivery và backlog persistence.

## 21. Scale-down phải có cơ chế drain và graceful shutdown

Khi giảm Pod, consumer đang xử lý message có thể bị SIGTERM. Nếu process kết thúc trước khi ack/commit hoặc trước khi hoàn tất transaction ở database, công việc có thể được giao lại. Đó là hành vi chấp nhận được của at-least-once processing **nếu** handler idempotent và không đánh dấu thành công quá sớm.

Trình tự tốt:

```text
KEDA/HPA giảm desired replicas
           |
           v
Kubernetes gửi SIGTERM
           |
           v
Ứng dụng dừng nhận thêm công việc / đóng consumer orderly
           |
           v
Hoàn tất hoặc xử lý rollback các message in-flight
           |
           v
Ack/commit những message đã xử lý bền vững
           |
           v
Consumer rời group/subscription, Pod thoát
```

`terminationGracePeriodSeconds` phải bao phủ thời gian dừng thường lệ và xử lý in-flight ở mức hợp lý. Với Spring Boot, có thể cấu hình thời hạn graceful shutdown của web server và lifecycle theo version; không đồng nhất graceful HTTP shutdown với việc **mọi binder consumer đã drain xong**. Cần quan sát log và kiểm thử shutdown của đúng binder. Các message không kịp hoàn tất phải được redeliver/retried an toàn.

Đặt `preStop` ngủ một số giây không tự bảo đảm message đã được ack đúng. Nếu dùng `preStop`, hãy có mục đích cụ thể (ví dụ đợi traffic routing giảm), không dùng nó thay cho idempotency và consumer lifecycle có kiểm soát.

## 22. Tránh replica dao động liên tục

Nếu backlog dao động quanh threshold, HPA có thể tăng/giảm liên tục. Mỗi lần thêm hoặc bỏ Pod là một lần thay đổi consumer membership; Kafka có thể rebalance, Kafka Streams có thể restore state, RabbitMQ/Pulsar có thể chuyển consumer/subscription assignment. Những tác động này tự làm giảm throughput tạm thời, rồi làm lag tăng trở lại và kích hoạt một vòng scale khác.

Một số biện pháp:

- Đặt activation threshold khác target threshold để tránh Pod chạy chỉ vì một vài message lẻ.
- Dùng HPA scale-down stabilization window đủ dài để tránh giảm quá nhanh.
- Giới hạn số Pod được tăng/giảm trong một khoảng thời gian.
- Dùng `pollingInterval` cân đối với tốc độ thay đổi tải; polling quá nhanh không nhất thiết làm HPA phản ứng tức thời.
- Giữ số replica tối thiểu lớn hơn 0 khi startup, state restore hoặc business latency nhạy cảm.
- Đo số lần rebalance/consumer restart và thời gian tạm dừng xử lý.

KEDA hỗ trợ truyền cấu hình HPA behavior qua `advanced.horizontalPodAutoscalerConfig` trong những phiên bản có hỗ trợ. Ví dụ thêm vào `spec` của một `ScaledObject`:

```yaml
advanced:
  horizontalPodAutoscalerConfig:
    behavior:
      scaleUp:
        stabilizationWindowSeconds: 0
        policies:
          - type: Percent
            value: 100
            periodSeconds: 60
      scaleDown:
        stabilizationWindowSeconds: 300
        policies:
          - type: Pods
            value: 1
            periodSeconds: 60
```

Các giá trị này minh họa: cho phép tăng tương đối nhanh nhưng giảm từng Pod và chờ khoảng 5 phút trước quyết định giảm. Kiểm tra manifest CRD của KEDA và HPA behavior thực sự được tạo sau deploy. `cooldownPeriod` của KEDA và `stabilizationWindowSeconds` của HPA có phạm vi khác nhau; không xem chúng là hai tên cho cùng một chức năng.

## 23. Kết hợp backlog và CPU/memory: chọn trigger có chủ đích

Một workload có thể bị giới hạn bởi CPU hoặc lag. KEDA cho phép nhiều trigger; HPA tính desired replicas theo từng metric và thường chọn giá trị đề xuất lớn hơn khi metric hợp lệ. Ví dụ thêm CPU trigger vào ScaledObject đã có Kafka lag:

```yaml
triggers:
  - type: kafka
    metadata:
      bootstrapServers: kafka-bootstrap.messaging.svc:9092
      consumerGroup: order-projection
      topic: orders.events
      lagThreshold: "1000"
  - type: cpu
    metricType: Utilization
    metadata:
      value: "70"
```

Đây là đoạn `spec.triggers` minh họa, không phải tài nguyên Kubernetes độc lập. Một số phiên bản KEDA CPU scaler dùng `metadata.type: Utilization` thay cho `metricType`; phải đối chiếu schema scaler đúng release, và CPU utilization cần Pod có `resources.requests.cpu`. Nếu không thể xác minh metric CPU, chỉ dùng lag trigger trước rồi triển khai CPU trigger sau khi integration test pass.

Tăng theo CPU và lag có thể phù hợp khi transform nặng CPU; nhưng nếu downstream là database đang bão hòa, cả CPU lẫn lag có thể khuyến khích scale vượt khả năng DB. Đặt `maxReplicaCount`, connection-pool limit và rate limit có cơ sở. Với memory tăng vì leak, tăng Pod không giải quyết nguyên nhân; autoscaling không thay thế sửa memory leak hoặc giới hạn heap.

## 24. Bảo mật truy cập metrics từ KEDA

KEDA cần kết nối broker hoặc monitoring API để đo backlog. Truy cập này là một phần của **control plane**, không giống credential consumer runtime.

| Thành phần | Quyền tối thiểu gợi ý | Không nên cấp |
|---|---|---|
| KEDA Kafka scaler | Quyền xem topic/consumer group offset, metadata liên quan | Quyền quản trị cluster nếu không cần |
| KEDA RabbitMQ scaler | Quyền đọc thống kê queue/vhost hoặc AMQP access cần thiết | Tài khoản root mọi vhost |
| KEDA Pulsar scaler | Quyền truy cập topic/subscription stats qua Admin API theo chính sách broker | Superuser token chung cho mọi scaler |
| Spring Cloud Stream consumer | Quyền consume trên nguồn và publish/ack/retry theo nghiệp vụ | Quyền quản trị toàn bộ broker |
| Kubernetes workload | Quyền truy cập secret/ConfigMap trong namespace của mình | Quyền đọc toàn bộ Secret của cluster |

Sử dụng Kubernetes Secret hoặc secret manager và KEDA `TriggerAuthentication` để gắn credential theo từng ScaledObject. Ví dụ tham chiếu đến đối tượng authentication đã được tạo riêng:

```yaml
triggers:
  - type: kafka
    metadata:
      bootstrapServers: kafka-bootstrap.messaging.svc:9093
      consumerGroup: order-projection
      topic: orders.events
      lagThreshold: "1000"
    authenticationRef:
      name: order-kafka-metrics-auth
```

Đây là cách **tham chiếu**; nội dung `TriggerAuthentication` phải được cấu hình SASL/TLS/OAuth tương thích với broker và scaler cụ thể. Không đặt password, token hoặc certificate private key dạng literal trong Git. Giới hạn NetworkPolicy để KEDA chỉ truy cập endpoint cần thiết; với RabbitMQ Management API hoặc Pulsar Admin API, luôn dùng TLS khi đi qua mạng không đáng tin cậy.

Một scaler không lấy được metric có thể không scale lên được hoặc HPA không có dữ liệu quyết định. Cần cảnh báo lỗi metric/authentication của KEDA, không coi "autoscaler im lặng" là queue đang rỗng.

## 25. Kiểm tra trạng thái sau khi apply ScaledObject

Sau khi cài KEDA và tạo ScaledObject ở namespace phù hợp, dùng các lệnh Kubernetes để kiểm tra:

```bash
kubectl -n event-processing get scaledobjects
kubectl -n event-processing describe scaledobject order-projection-kafka
kubectl -n event-processing get hpa
kubectl -n event-processing describe hpa
kubectl -n event-processing get deployment order-projection
kubectl -n event-processing get pods -l app=order-projection
```

Các bước quan sát:

1. `ScaledObject` có điều kiện ready/active phù hợp không?
2. KEDA có tạo HPA quản lý đúng `Deployment` không?
3. HPA có đọc được current metric và target metric không?
4. Desired replicas có tăng khi lag/backlog tăng không?
5. Pod mới có `Ready` và đã tạo consumer subscription thật chưa?
6. Message processing/ack rate có tăng tương ứng không?
7. Khi tải giảm, Pod có scale xuống sau stabilization và graceful shutdown không?

Không kết luận autoscaling thành công chỉ từ `desiredReplicas` tăng. Nếu Pod ở trạng thái `Pending`, `CrashLoopBackOff` hoặc `NotReady`, năng lực xử lý thực tế không tăng. Tìm nguyên nhân ở image pull, CPU quota, node capacity, secrets, broker authentication, schema mismatch, database connection và startup duration.

## 26. Readiness, liveness và startup khi Pod mới xuất hiện

Actuator cung cấp các health endpoints của Spring Boot nếu dependency và exposure đã được cấu hình. Ví dụ:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
```

Kubernetes probe minh họa khi Actuator phục vụ trên port HTTP 8080:

```yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  failureThreshold: 30
  periodSeconds: 5
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
```

Với consumer không cung cấp HTTP server, cần thêm web starter hoặc chọn probe phù hợp khác. Các probe trên chỉ báo trạng thái ứng dụng theo Spring Boot health groups; `Readiness=UP` không tự chứng minh consumer đã được gán partition hoặc đã sẵn sàng xử lý. Nếu workload cần chờ Kafka Streams state restore hoặc broker connection trước khi được coi là có năng lực, xây dựng signal phù hợp và đo readiness latency.

**Không đưa broker availability vào liveness một cách máy móc.** Khi broker dùng chung bị lỗi, tất cả Pod restart đồng loạt sẽ làm tệ hơn. Với readiness, việc đưa binder health vào cũng cần đánh giá: một broker outage có thể làm toàn bộ Pod unready, tác động tới service routing và availability dù application có cơ chế tự reconnect.

## 27. Kafka Streams stateful: scale quá thường xuyên có thể làm chậm hơn

Kafka Streams Binder dùng task, thread và state store; instance mới đôi khi phải restore state từ changelog trước khi xử lý task. Khi scale-out:

```text
Tăng replica
   -> rebalance task
   -> di chuyển active/standby task
   -> khôi phục state store nếu cần
   -> resume processing
```

Trong thời gian restore, lag có thể tiếp tục tăng khiến autoscaler muốn thêm Pod. Tăng thêm có thể gây nhiều task migration và network/disk I/O. Để tránh vòng lặp, cân nhắc `minReplicaCount` phù hợp tải nền, scale-up policy thận trọng, scale-down stabilization và benchmark thời gian restore theo kích thước state thực tế.

Đối với StatefulSet hoặc topology phụ thuộc local state placement, cần xác minh KEDA/HPA `scaleTargetRef` hỗ trợ workload đích đúng cách và bảo đảm mỗi replica có state directory riêng. Không thay `applicationId` theo Pod name; các replica phải tham gia cùng Kafka Streams application logic. Standby task giúp phục hồi nhanh hơn nhưng không biến thành active capacity tăng thêm.

## 28. Backpressure: khi downstream không thể tăng tốc

Giả sử database chịu được tối đa 1.200 operations/giây. Mỗi Pod có thể đẩy 400 operations/giây trong môi trường benchmark đơn lẻ, nhưng khi chạy 10 Pod thì tổng tải không thể lên 4.000 operations/giây mà không làm database bão hòa.

```text
Broker backlog tăng
      |
      v
KEDA scale Pod từ 3 -> 10
      |
      v
DB connection pool cạn / timeout tăng
      |
      v
Retry tăng -> backlog còn tăng hơn
```

Các biện pháp bảo vệ:

- Hạn chế `maxReplicaCount` theo mức downstream chịu được.
- Đặt connection pool per Pod có tổng tối đa tính toán được (pool size × replicas).
- Giới hạn consumer concurrency hoặc prefetch nếu xử lý chậm.
- Dùng circuit breaker/rate limiter, backoff và jitter hợp lý.
- Phân loại lỗi tạm thời với poison message để tránh retry storm.
- Đặt quota broker/network/CPU/memory theo năng lực được phép.
- Theo dõi downstream p95/p99 latency, timeout và saturation cùng backlog.

Trong trường hợp upstream tạo dữ liệu nhanh hơn tổng năng lực downstream **bền vững**, chỉ scale consumer là chưa đủ. Có thể cần điều tiết producer, phân tầng hàng đợi, tăng năng lực database hoặc điều chỉnh SLO. Autoscaling phải là một phần của capacity planning, không phải cách che giới hạn của hệ thống.

## 29. Retry/DLQ ảnh hưởng metric kích hoạt như thế nào?

Message lỗi liên tục có thể tạo backlog cao dù tăng replica không tăng tốc độ xử lý thành công. Ví dụ consumer gặp lỗi deserialize, retry mỗi message ba lần rồi dead-letter. Nếu thông điệp lỗi chiếm 50% traffic, tăng Pod chỉ tạo nhiều exception và lưu lượng DLQ, có thể gây thêm tải broker.

| Hiện tượng | Metric cần xem | Hướng xử lý |
|---|---|---|
| Lag lớn, error rate thấp, CPU cao | CPU, processing rate, lag slope | Có thể tăng replica nếu còn partition và downstream capacity |
| Lag lớn, error rate cao | Retry/exception/DLQ, error class | Sửa schema/code/data; không scale vô hạn |
| Queue ready thấp, unacked cao | Consumer processing duration, prefetch | Xác minh handler treo, DB slow hoặc prefetch quá cao |
| Pulsar backlog cao, nhiều redelivery | Redelivery, negative ack, subscription | Xem timeout/poison message và subscription type |
| Lag thấp nhưng end-to-end latency cao | In-flight, processing duration, external work | Tránh ack sớm; đo thời gian hoàn tất nghiệp vụ |
| Lag tăng do rebalance kéo dài | Rebalance, restore rate, active threads | Giảm scale churn, kiểm tra state restoration |

Với RabbitMQ DLQ, queue lỗi thường là một queue khác. Đừng vô tình dùng cùng scaler cho queue chính và queue DLQ, rồi để Pod xử lý chính tự scale theo message lỗi không được tiêu thụ. DLQ cần workflow điều tra và replay riêng; có thể có autoscaling riêng cho DLQ processor nếu được thiết kế và kiểm soát.

## 30. Quan sát và cảnh báo end-to-end

Autoscaling có thể đạt desired replica nhưng vẫn không đạt SLO. Dashboard production nên kết hợp:

- Lag/backlog hiện tại và **slope** (tăng hay giảm trong mỗi phút).
- Arrival rate, successful ack/commit rate và error/retry rate.
- Age of oldest event / end-to-end processing latency.
- Desired, current, available và ready replicas.
- KEDA scaler errors, HPA metric fetch failures và thời gian từ trigger đến Pod ready.
- Partition assignment, consumer membership, rebalance count và Kafka Streams restore time.
- CPU, memory, heap/GC, per-Pod concurrency và connection pool usage.
- RabbitMQ ready/unacked, Pulsar subscription backlog/redelivery.
- DLQ backlog và số message đang bị chặn bởi ordering gap.
- Quota, node autoscaler latency và Pod Pending count.

Đặt cảnh báo khi lag tăng liên tục trong khi replica đã chạm `maxReplicaCount`, khi replica tăng nhưng processing rate không tăng, hoặc khi scaler không lấy được metric. Đây là dấu hiệu **giới hạn năng lực**, **lỗi downstream** hoặc **vấn đề đo lường** cần con người can thiệp.

## 31. Ma trận kiểm thử tự động mở rộng

| Kịch bản | Cách thực hiện | Điều phải quan sát |
|---|---|---|
| Không tải | Không gửi message; `minReplicaCount:1` | Một replica duy trì hoạt động, không flapping |
| Tăng tải đột ngột | Gửi burst 50.000 events | Replica tăng theo metric; end-to-end latency trong ngưỡng |
| Tải vừa phải | Gửi đều quanh target threshold | Replica ổn định, không scale lên/xuống mỗi chu kỳ |
| Producer tăng nhanh | Cho \(\lambda\) vượt processing rate | Backlog tăng có thể giải thích và được cảnh báo |
| Consumer quá ít partition | Kafka 4 partition, đặt maxReplicaCount 12 | Consumer thừa không làm thêm active partition |
| RabbitMQ SAC | Hai Pod trở lên cùng queue SAC | Chỉ một active consumer; throughput không tăng tuyến tính |
| Pulsar Shared/Key_Shared | Nhiều Pod chung subscription | Assignment đúng, xử lý theo ordering contract |
| Broker authentication sai | Đổi credential của scaler thành không hợp lệ | Báo lỗi scaler/metric; không silently xem queue rỗng |
| Database chậm | Tăng latency DB hoặc giảm connection limit | Backlog và timeout tăng; autoscaler không phá DB |
| Poison message | Phát payload lỗi lặp | DLQ/retry hoạt động; không scale storm vô hạn |
| Pod bị kill | Kill Pod đang có in-flight | Redelivery an toàn, không nhân đôi tác động |
| Scale-down | Cho backlog về 0 | Pod drain, không mất message trước ack |
| Scale-to-zero | Tắt toàn bộ Pod với trigger hỗ trợ | Subscription/queue tồn tại, message mới đánh thức Deployment |
| Kafka Streams restore | Restart instance có state lớn | Đo rebalance/restore; không lặp scale vô ích |

Các phép thử này cần môi trường Kubernetes có KEDA/HPA và broker thực hoặc môi trường tích hợp tương đương. `spring-cloud-stream-test-binder` kiểm tra logic function nhưng **không** mô phỏng được consumer group lag, RabbitMQ queue depth, Pulsar subscription backlog hay Kubernetes autoscaling loop.

## 32. Kịch bản thực hành: từ một Pod đến sáu Pod

Giả sử hệ thống có Kafka topic `orders.events` 12 partition, một group `order-projection`, mỗi Pod một consumer thread. Tại thời điểm thử nghiệm, producer gửi 400 event/giây và mỗi Pod xử lý ổn định 150 event/giây khi database chưa bão hòa. Backlog ban đầu là 18.000 message. Mục tiêu là xử lý hết backlog trong tối đa 120 giây.

Tính toán sơ bộ:

\[
R\ge\left\lceil\frac{400+18000/120}{150}\right\rceil
=\left\lceil3{,}67\right\rceil=4
\]

Bốn Pod có năng lực ròng \(4\times150-400=200\) message/giây, ước tính drain trong 90 giây (chưa tính startup). Sáu Pod có năng lực ròng 500 message/giây, drain trong khoảng 36 giây nếu DB chịu nổi. Vì có 12 partition, về mặt partition assignment có thể chạy sáu consumer hoạt động đồng thời. Nhưng nếu DB bắt đầu chậm khi có hơn bốn Pod, sáu Pod có thể không nhanh hơn; phải đo bằng dashboard.

Quy trình thực hành:

1. Chạy Deployment một Pod, xác minh group commit offset đúng và không ack sớm.
2. Apply ScaledObject với `minReplicaCount:1`, `maxReplicaCount:6`, target lag dựa trên benchmark.
3. Gửi burst, đo thời gian KEDA nhận tín hiệu, HPA đổi desired và Pod mới Ready.
4. Kiểm tra `kubectl get hpa`, `describe scaledobject` và group partition assignment.
5. Đo successful commits/second, database latency và backlog slope.
6. Chủ động làm một Pod lỗi, xác minh xử lý lại không gây side effect trùng.
7. Cho tải giảm, xác minh scale-down không cắt ngang tác vụ in-flight.
8. Lặp lại với database chậm và poison message để đánh giá giới hạn thực.

Nếu ứng dụng sử dụng `concurrency: 2` trên mỗi Pod, lại cần tính tổng consumer thread và số partition; không chỉ lấy số Pod làm số worker thực tế. Nếu chuyển sang Kafka Streams stateful, cần bổ sung thời gian restore/changelog, không tái sử dụng các benchmark stateless.

## 33. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| KEDA đo sai consumer group | Scale theo lag của ứng dụng khác | Đối chiếu `consumerGroup` với group runtime |
| KEDA RabbitMQ đọc tên exchange thay vì queue | Không lấy được queue depth chính xác | Xác minh queue name vật lý trên broker |
| KEDA Pulsar đo nhầm subscription | Backlog metric không khớp workload | Kiểm tra durable subscription name |
| Group/subscription đổi theo tên Pod | Mỗi Pod có luồng nhận riêng, dễ duplicate | Dùng ID ổn định cho một ứng dụng logic |
| Max replica lớn hơn mức song song hữu ích | Tốn tài nguyên, tăng rebalance | Cap theo partition/task/queue và concurrency |
| Chỉ đo queue ready | Bỏ qua khối lượng unacked do prefetch | Quan sát ready, unacked và processing duration |
| Chạy SAC/Exclusive rồi scale hàng chục Pod | Pod mới không giúp throughput | Thay đổi topology/subscription sau khi đánh giá ordering |
| Scale-to-zero trước khi queue/subscription tồn tại | Không đo được backlog để đánh thức worker | Provision tài nguyên và xác minh scaler hoạt động từ 0 |
| Đưa secret trực tiếp vào ScaledObject | Rò rỉ credential | Dùng Secret và TriggerAuthentication |
| Thiếu resource requests | HPA CPU metric thiếu chính xác/không có | Khai báo CPU/memory requests thích hợp |
| Giảm Pod ngay khi lag về 0 | Message in-flight bị gián đoạn | Graceful shutdown, idempotency, stabilization |
| Lag tăng vì poison message | Autoscaler tạo retry storm | Sửa lỗi dữ liệu/schema; dùng DLQ/rate limit |
| HPA độc lập cùng scale một Deployment | Replica tranh chấp, oscillation | Có một nguồn autoscaling kiểm soát scale target |
| Không có broker metrics khi mất kết nối | Scale không phản ứng hoặc báo metric unknown | Cảnh báo scaler error, credential/network |
| Nhầm desired với ready replicas | Nghĩ đã có năng lực mới khi Pod còn Pending | Theo dõi startup, readiness, quota/node capacity |

## 34. Checklist vận hành production

- [ ] Xác định workload thực sự là event consumer, không scale theo producer backlog không liên quan.
- [ ] Đặt group/subscription/application ID ổn định trên mọi replica.
- [ ] Xác minh broker metric đo đúng topic, queue hoặc subscription.
- [ ] Có SLO về tuổi message, drain time và độ trễ end-to-end.
- [ ] Benchmark processing rate bền vững mỗi Pod, gồm retry và downstream latency.
- [ ] Đặt `minReplicaCount`, `maxReplicaCount` theo partition, ordering và năng lực downstream.
- [ ] Phân biệt `pollingInterval`, KEDA cooldown và HPA stabilization.
- [ ] Cấu hình secret/TLS/auth riêng cho scaler metrics và runtime client.
- [ ] Có liveness/readiness/startup phù hợp, không kích hoạt restart storm khi broker lỗi.
- [ ] Handler idempotent, ack/commit sau khi công việc an toàn.
- [ ] Graceful shutdown và termination grace đã được test khi scale-down.
- [ ] Đã kiểm thử scale-to-zero nếu định dùng; queue/group/subscription vẫn đọc được ở 0 Pod.
- [ ] Có dashboard cho lag, ready/unacked, backlog, processing rate, scaler errors và Pod Ready.
- [ ] Có cảnh báo khi đã max replica mà lag vẫn tăng hoặc khi metric thiếu.
- [ ] Có thử nghiệm burst, poison message, broker outage, DB saturation và rebalance.

## 35. Câu hỏi tự kiểm tra

1. Vì sao CPU thấp không chứng minh consumer đang theo kịp tốc độ message đến?
2. Kafka consumer lag được xác định từ những offset nào và liên hệ với consumer group ra sao?
3. Một topic Kafka bốn partition có thể tận dụng tối đa bao nhiêu consumer cùng group trên một input topic đơn giản?
4. `lagThreshold` của KEDA khác gì so với target thời gian xử lý một message?
5. Vì sao RabbitMQ cần phân biệt `messages_ready` và `messages_unacknowledged`?
6. Tại sao 10 replica đọc một RabbitMQ Single Active Consumer queue không xử lý nhanh gấp 10 lần?
7. Với Pulsar, scaler phải đo backlog của topic hay của subscription nào?
8. Điều gì có thể xảy ra nếu scale về 0 trước khi Kafka group có committed offset hoặc Pulsar subscription được tạo?
9. Tại sao tăng Pod đôi khi làm lag Kafka Streams stateful tăng thêm?
10. Khi backlog là 20.000, arrival rate 200 message/giây, một Pod xử lý 100 message/giây, cần tối thiểu mấy Pod để backlog **giảm**?
11. Vì sao HPA scale-down phải phối hợp graceful shutdown và idempotency?
12. Nên cảnh báo những gì khi replica đã chạm trần mà backlog vẫn tăng?

## Kết luận

Tự động mở rộng Spring Cloud Stream theo khối lượng sự kiện giúp phản ứng sát hơn với tải thực tế so với chỉ dùng CPU. Với **Kafka**, đặt ngưỡng theo consumer group lag và tôn trọng giới hạn partition/concurrency. Với **RabbitMQ**, đo đúng queue của consumer group, hiểu ready/unacknowledged, prefetch và tác động của Single Active Consumer. Với **Pulsar**, đo đúng durable subscription backlog và chọn subscription type phù hợp. **KEDA** kết nối broker metric với **Kubernetes HPA**, nhưng không tự khắc phục consumer lỗi, kết nối database chậm, poison message hoặc replay sai. Chọn ngưỡng từ SLO và throughput benchmark, giới hạn replica theo năng lực downstream, bảo vệ scaler credentials, kiểm thử scale-to-zero, graceful shutdown, rebalance và theo dõi lag/backlog cùng processing rate để autoscaling vừa nhanh vừa an toàn.

## Tài liệu tham khảo

- Spring Cloud Stream — Reference Documentation: https://docs.spring.io/spring-cloud-stream/reference/
- Spring Cloud Stream — Kafka Binder consumer properties: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html
- Spring Cloud Stream — RabbitMQ Binder consumer properties: https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html
- Spring Cloud Stream — Pulsar Binder: https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html
- Kubernetes — Horizontal Pod Autoscaling: https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/
- KEDA — ScaledObject Specification: https://keda.sh/docs/latest/concepts/scaling-deployments/
- KEDA — Apache Kafka Scaler: https://keda.sh/docs/latest/scalers/apache-kafka/
- KEDA — RabbitMQ Queue Scaler: https://keda.sh/docs/latest/scalers/rabbitmq-queue/
- KEDA — Apache Pulsar Scaler: https://keda.sh/docs/latest/scalers/apache-pulsar/
- RabbitMQ — Queue Monitoring: https://www.rabbitmq.com/docs/monitoring
- Apache Pulsar — Subscriptions and Messaging: https://pulsar.apache.org/docs/4.0.x/concepts-messaging/

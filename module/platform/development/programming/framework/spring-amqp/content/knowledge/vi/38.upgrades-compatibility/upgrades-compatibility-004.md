# Đối chiếu thay đổi mặc định của container, prefetch và xử lý lỗi

Nâng cấp **Spring AMQP** có thể khiến một ứng dụng vẫn biên dịch, kết nối RabbitMQ bình thường nhưng **thay đổi hành vi tiêu thụ message**: số delivery chưa ACK tăng lên, listener chạy trên loại thread khác, batch/retry hoạt động khác trước, hoặc một message lỗi chuyển sang dead-letter thay vì được gửi lại. Nguy hiểm nhất là những thay đổi không xuất hiện trong business code: chúng đến từ **mặc định của listener container**, **phiên bản framework**, **Spring Boot auto-configuration** và đôi khi từ **chính RabbitMQ broker**.

Bài thuộc chương **Nâng cấp và tương thích** của module **SPRING_AMQP**, nơi học cách kết nối RabbitMQ với `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding, xác nhận giao nhận, retry, dead-letter, giao dịch và quan sát hệ thống. Trọng tâm không phải “nâng version thế nào cho biên dịch”, mà là **đối chiếu hợp đồng xử lý message trước và sau upgrade**.

Sau bài này, người học có thể:

- Lập **baseline hành vi hiện tại** trước khi cập nhật Spring AMQP/Spring Boot và RabbitMQ Java client.
- Phân biệt `SimpleMessageListenerContainer` (SMLC) với `DirectMessageListenerContainer` (DMLC), cũng như những thuộc tính **không thể chuyển 1:1**.
- Hiểu mốc thay đổi **prefetch mặc định từ 1 thành 250 kể từ Spring AMQP 2.0** và tác động tới bộ nhớ, fairness, ordering, ACK và redelivery.
- Đánh giá `AcknowledgeMode.AUTO`, `MANUAL`, `NONE`, `defaultRequeueRejected`, `ConditionalRejectingErrorHandler`, `x-death`, lỗi conversion và listener bất đồng bộ.
- Viết **integration tests trên RabbitMQ thật** để phát hiện thay đổi hành vi trước khi rollout.
- Tạo một **compatibility matrix** và runbook rollback dựa trên bằng chứng, không dựa vào giả định từ tài liệu một phiên bản khác.

> **Phạm vi:** Các ví dụ cấu hình chính dùng Java 17+, Spring Boot 3.x và Spring AMQP 3.2.x. Bài cũng chỉ rõ các mốc lịch sử từ 1.x/2.x và những điểm cần xử lý khi tiến lên Spring AMQP 4.x. Hãy sử dụng BOM do Spring Boot quản lý hoặc một tổ hợp dependency được nhà cung cấp hỗ trợ; **không trộn artifact 3.x và 4.x theo cảm tính**. Các ví dụ chưa phải kết quả build/QA; việc biên dịch và thử nghiệm với phiên bản mục tiêu cần thực hiện ở bước triển khai/kiểm thử.

## 1. “Giá trị mặc định” đến từ bốn lớp khác nhau

Đừng hỏi chung “Spring AMQP mặc định là gì?” mà thiếu **version và vị trí cấu hình**.

```text
                          @RabbitListener method
                                   |
                         Annotation overrides
                         id, ackMode, concurrency,
                         autoStartup, containerFactory
                                   |
                                   v
                  RabbitListenerContainerFactory bean
                           Simple hoặc Direct
                                   |
                      Spring Boot auto-configuration
                        / user-defined @Bean
                                   |
                   Framework container class defaults
                                   |
                        RabbitMQ Java client
                                   |
                         RabbitMQ broker
                 queue type, prefetch semantics, DLX,
                    delivery limit, permissions
```

**Bốn tầng cần kiểm tra:**

1. **Spring AMQP framework:** Class container quyết định default prefetch, error handler, recovery, shutdown và danh sách thuộc tính được hỗ trợ.
2. **Spring Boot:** Auto-configuration chọn loại container, bind các khóa `spring.rabbitmq.listener.*` và có thể áp dụng beans/customizers. Không mặc định Boot auto-config áp dụng đầy đủ lên một custom factory do ứng dụng tự tạo.
3. **Ứng dụng:** `@RabbitListener` có thể override factory bằng `containerFactory`, `ackMode`, `autoStartup` hoặc `concurrency`; một `BeanPostProcessor`/`ContainerCustomizer` cũng có thể thay cấu hình hiệu lực.
4. **Broker:** RabbitMQ quyết định cách áp prefetch cho consumers, requeue, dead-letter và policy quorum queues. Upgrade broker là một trục thay đổi khác với upgrade Spring AMQP.

Vì vậy **khóa cấu hình không xuất hiện trong YAML không chứng minh effective value là một hằng số bất biến theo thời gian**.

### 1.1. Hợp đồng thực sự cần bảo vệ

Một “hợp đồng consumer” không chỉ là method signature:

| Thành phần hợp đồng | Ví dụ trước upgrade | Tại sao cần đối chiếu? |
|---|---|---|
| Queue và broker/vhost | `orders.work` trên vhost `/orders` | Sai factory/vhost sẽ tiêu thụ queue khác hoặc không consume |
| Container type | SMLC | DMLC có kiến trúc thread, concurrency và batch semantics khác |
| Consumers | Một hoặc nhiều consumer | Nhiều consumer ảnh hưởng ordering, tải DB và fairness |
| Prefetch | 1 hay 250 | Giới hạn deliveries chưa ACK/buffer, memory và redelivery |
| ACK mode | `AUTO` | Thay đổi làm ACK sớm, thiếu ACK hoặc double ACK |
| Error policy | Requeue transient, reject fatal | Thay đổi có thể tạo retry loop hoặc loại message |
| Retry/Recoverer | 3 attempts + DLQ | Khác về số lần, backoff, xử lý khi exhausted |
| Converter | JSON version/mapping | Payload cũ có thể lỗi trước khi listener được gọi |
| Container lifecycle | Auto startup/recovery | Listener có thể đứng yên với queue ready tăng |
| SLO quan sát | Handler p95, ready/unacked, DLQ | Cùng business code nhưng throughput/latency khác |

## 2. Mốc thay đổi theo phiên bản Spring AMQP

Các mốc sau được mô tả trong **release notes/reference của Spring AMQP**; không có nghĩa mọi dự án tự động chịu tác động nếu trước đó đã override explicit.

| Mốc | Thay đổi đáng chú ý | Rủi ro hồi quy |
|---|---|---|
| **Trước 2.0** | Prefetch của container mặc định **1** | Hệ thống cũ có thể vô tình dựa vào công bằng/thứ tự khi chỉ có một delivery chưa ACK |
| **2.0** | Prefetch mặc định nâng thành **250**; `DirectMessageListenerContainer` xuất hiện | Buffer/unacked tăng, memory/duplicate window lớn hơn; có thêm lựa chọn container |
| **1.3.2** | `ConditionalRejectingErrorHandler` trở thành default error handler cho lỗi fatal trước listener | Message conversion lỗi thường bị reject không requeue, không đi vào vòng lặp vô hạn |
| **2.1** | `ConditionalRejectingErrorHandler` xử lý đặc biệt fatal message có header `x-death`, mặc định có thể discard để tránh vòng DLQ-TTL vô hạn | Replay DLQ phải kiểm tra kỹ; dữ liệu có thể không trở lại source queue như cũ |
| **2.1.9** | Fatal pre-listener errors có thể bị reject/no-requeue mặc định ngay cả khi ACK mode `MANUAL` | Một số message trước đó bị kẹt unacked sẽ đi đường reject/DLX |
| **2.2.21 / 2.3.13 / 2.4.1** | Với listener trả kết quả bất đồng bộ, framework tự chọn `MANUAL` khi nhận diện return type phù hợp | Thời điểm ACK chuyển từ lúc method return sang khi future/Mono hoàn tất |
| **3.0.5** | Hỗ trợ Kotlin `suspend` cho listener; error handler được gọi sau lỗi async theo điều kiện tương ứng | Callback/exception timing khác khi nâng phiên bản |
| **4.0** | Chuyển sang Spring Framework 7, hỗ trợ Jackson 3, chuyển từ Spring Retry sang Spring Core Retry ở API liên quan | Converter, retry advice/import và logic recoverer cần migration thay vì chỉ đổi version |
| **RabbitMQ 4.0/4.3** | Thay đổi liên quan quorum queue delivery limit và cách đếm requeue ở broker | Cùng listener exception nhưng số lần redelivery/đường DLQ khác trước |

**Đừng nhầm thứ tự thời gian:** Những thay đổi 1.3.2/2.1 là **mốc lịch sử riêng**, không được diễn đạt rằng chúng mới xuất hiện trong 2.0. Khi so sánh 2.4 → 3.2, các thay đổi cũ thường đã nằm trong baseline, nhưng vẫn cần xác minh vì một ứng dụng có thể override `errorHandler`/prefetch.

### 2.1. Version compatibility là một ma trận, không phải một con số

Cần ghi:

```text
Spring Boot BOM version:
Spring Framework version:
Spring AMQP (spring-rabbit) version:
RabbitMQ Java client version:
RabbitMQ broker version:
Java version:
Container type per listener:
Consumer message converter:
Retry advice / recoverer implementation:
Queue type / policies:
```

Một bug chỉ xuất hiện khi nâng Spring AMQP nhưng không nâng broker khác với bug xuất hiện khi đồng thời đổi **quorum queue policy**. Muốn tìm root cause, thay ít trục một lần và lưu baseline chính xác.

## 3. SimpleMessageListenerContainer và DirectMessageListenerContainer

### 3.1. Hai kiến trúc khác nhau

**SMLC** dùng một hàng đợi nội bộ và thread xử lý riêng:

```text
RabbitMQ
   |
Rabbit Java client thread
   |
   +--> internal queue của SMLC
                |
                v
        consumer worker thread
                |
                v
           @RabbitListener
                |
              ACK/NACK
```

**DMLC** gọi listener trên thread mà RabbitMQ Java client điều phối, tránh một bước handoff:

```text
RabbitMQ
   |
Rabbit Java client delivery thread
   |
   v
DirectMessageListenerContainer
   |
   v
@RabbitListener
   |
ACK/NACK
```

Điều này ảnh hưởng cách dùng executor, thread-local context, trace propagation, thông lượng, shutdown và số message đang được buffer. **DMLC không phải “SMLC nhưng nhanh hơn trong mọi trường hợp”**; nó có tập tính năng khác.

### 3.2. Bảng đối chiếu để tránh cấu hình nhầm

| Chủ đề | SMLC | DMLC |
|---|---|---|
| Đường xử lý | Client thread → internal queue → consumer thread | Listener chạy trực tiếp trên thread client điều phối |
| Điều khiển concurrency | `concurrentConsumers` và `maxConcurrentConsumers` | `consumersPerQueue` |
| Auto scaling consumers | Có cơ chế tăng/giảm theo active/idle triggers | Không có cùng cơ chế SMLC; có thể đổi consumersPerQueue bằng thao tác quản lý |
| Thêm/bớt queue runtime | Có thể restart consumers cùng container | Ít ảnh hưởng hơn lên consumers của queue không thay đổi |
| `batchSize` | Hỗ trợ cho ACK/transaction batch | Không hỗ trợ `batchSize` tương tự |
| `consumerBatchEnabled` | Có | Không có như SMLC |
| `messagesPerAck` | Không dùng như DMLC | Có, gom ACK trong một số trường hợp không transacted |
| Executor | Có worker threads riêng cho consumers | Dùng thread pool của RabbitMQ client; cần cấu hình/sizing phù hợp |
| Prefetch | Có | Có |
| AUTO/MANUAL ACK | Có | Có |
| Error handler, recovery | Có | Có nhưng lifecycle/chi tiết khác |
| `missingQueuesFatal` theo class 3.2 | **true** mặc định ở SMLC | **false** mặc định ở DMLC |

**Lưu ý:** Bảng nêu class/library defaults trong phạm vi được tài liệu 3.2 mô tả. Spring Boot property binding, custom factories và version khác có thể override. Giá trị hiệu lực phải được xác nhận trong integration test.

### 3.3. Concurrency của @RabbitListener không có cùng cú pháp

```java
// SMLC: "2-6" là min/max concurrent consumers.
@RabbitListener(
        queues = "orders.work",
        containerFactory = "ordersSimpleFactory",
        concurrency = "2-6")
public void handleWithSimple(String json) {
    // ...
}

// DMLC: "2" là consumersPerQueue;
// cú pháp "2-6" KHÔNG phải scale range như SMLC.
@RabbitListener(
        queues = "orders.audit",
        containerFactory = "auditDirectFactory",
        concurrency = "2")
public void handleWithDirect(String json) {
    // ...
}
```

Hai listener trên phải ở **những queue và mục đích khác nhau** nếu được chạy đồng thời; ví dụ chỉ nhằm so sánh cú pháp, không ngụ ý nên triển khai duplicate logic ở cả hai trong production.

Khi đổi `spring.rabbitmq.listener.type=simple` thành `direct`, một cấu hình `concurrency=2-6` có thể không còn phù hợp. DMLC thường áp số consumer **trên mỗi queue**, nên một container nghe ba queue với `consumersPerQueue=2` có thể tạo **6 consumer registrations**; đừng nghĩ đó là tổng hai consumers cho toàn container.

## 4. Spring Boot auto-configuration: default factory có thể khác custom factory

Với Spring Boot khi tích hợp RabbitMQ 0-9-1, nếu ứng dụng không định nghĩa factory của riêng mình, Boot thường auto-configure **SimpleRabbitListenerContainerFactory**. Có thể đổi sang direct bằng property `spring.rabbitmq.listener.type`.

### 4.1. Chọn Simple và khóa explicit

Ví dụ `application.yml`, các giá trị chỉ là **baseline minh họa** và cần đo dưới workload thật:

```yaml
spring:
  rabbitmq:
    listener:
      type: simple
      simple:
        acknowledge-mode: auto
        prefetch: 10
        concurrency: 2
        max-concurrency: 4
        auto-startup: true
        default-requeue-rejected: false
        missing-queues-fatal: true
        retry:
          enabled: false
```

Thiết lập `default-requeue-rejected=false` **chỉ an toàn khi có retry hữu hạn và DLX/quarantine phù hợp**. Không copy block này vào mọi service, vì default lỗi nghiệp vụ có thể bị reject và **drop** nếu queue không có dead-letter setup.

### 4.2. Chọn Direct với keys riêng

```yaml
spring:
  rabbitmq:
    listener:
      type: direct
      direct:
        acknowledge-mode: auto
        prefetch: 10
        consumers-per-queue: 2
        auto-startup: true
        default-requeue-rejected: false
        missing-queues-fatal: true
```

Khi chuyển type, đừng để các setting chỉ dành cho `simple` ở YAML và tưởng Boot áp dụng sang `direct`. Ví dụ `simple.max-concurrency` **không phải** `direct.consumers-per-queue`.

**Chú ý:** Boot có thể có defaults riêng ở một số phiên bản, và `@RabbitListener(containerFactory="...")` có thể chọn **custom factory**, bỏ qua factory mặc định của Boot. Trong nhiều dự án, thay property `spring.rabbitmq.listener.type` không hề đổi container type của listener đang dùng vì annotation đã trỏ tới bean custom.

### 4.3. Tạo factory bằng Java, tránh phụ thuộc defaults ẩn

```java
@Configuration
@EnableRabbit
public class ListenerFactoryConfig {

    @Bean("ordersSimpleFactory")
    SimpleRabbitListenerContainerFactory ordersSimpleFactory(
            ConnectionFactory cf) {

        SimpleRabbitListenerContainerFactory f =
                new SimpleRabbitListenerContainerFactory();
        f.setConnectionFactory(cf);
        f.setAcknowledgeMode(AcknowledgeMode.AUTO);
        f.setPrefetchCount(10);
        f.setConcurrentConsumers(2);
        f.setMaxConcurrentConsumers(4);
        f.setDefaultRequeueRejected(false);
        f.setMissingQueuesFatal(true);
        f.setAutoStartup(true);
        return f;
    }

    @Bean("auditDirectFactory")
    DirectRabbitListenerContainerFactory auditDirectFactory(
            ConnectionFactory cf) {

        DirectRabbitListenerContainerFactory f =
                new DirectRabbitListenerContainerFactory();
        f.setConnectionFactory(cf);
        f.setAcknowledgeMode(AcknowledgeMode.AUTO);
        f.setPrefetchCount(10);
        f.setConsumersPerQueue(2);
        f.setDefaultRequeueRejected(false);
        f.setMissingQueuesFatal(true);
        f.setAutoStartup(true);
        return f;
    }
}
```

Import chính:

```java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.config.DirectRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
```

Mỗi listener phải tham chiếu đúng factory. **Không cấu hình cùng một queue với hai listener types chạy cạnh tranh chỉ để “canary” rồi so output** nếu thứ tự/ownership mang tính nghiệp vụ; kiểm thử canary bằng một queue, replica hoặc vhost cô lập có chủ đích.

**Lưu ý chuyên môn:** Những custom factories không tự động nhận toàn bộ Spring Boot customizations (observation, converter, retry, container customizers) trong mọi trường hợp. Nếu đã dựa vào Boot auto-configuration, sử dụng `SimpleRabbitListenerContainerFactoryConfigurer` hoặc `DirectRabbitListenerContainerFactoryConfigurer` của Boot khi phù hợp, rồi override các thuộc tính cần thiết, và kiểm thử effective values.

## 5. Prefetch mặc định: từ 1 thành 250 và những hệ quả

### 5.1. Prefetch là giới hạn delivery chưa ACK

`prefetchCount` là lượng **delivery chưa ACK tối đa** RabbitMQ có thể đưa cho một consumer trước khi cần ACK để cấp thêm. RabbitMQ với `basic.qos` có semantics theo consumer trong những điều kiện thường dùng; tùy cờ `globalQos` và cấu hình channel, phạm vi giới hạn có thể khác.

```text
       Queue orders.work: ready=1000
                    |
                    | basic.deliver
                    v
              Consumer C1
              prefetch=250
          +------------------+
          | 250 deliveries   |  <-- unacked/in-flight
          | có thể đang buffer|
          | method xử lý 1   |
          +------------------+

       Ready có thể giảm 250 trước khi 250 event được commit!
```

**Điểm thay đổi lịch sử:** Trước Spring AMQP 2.0, default prefetch là **1**. Kể từ 2.0, default là **250**. Việc nâng version mà quên thiết lập explicit `prefetch` có thể tăng cửa sổ delivery chưa ACK gấp hàng trăm lần. Không có nghĩa broker luôn giao đủ 250; đó là **upper bound** trong những điều kiện thích hợp.

### 5.2. Bộ nhớ và thời gian chờ bị đẩy sang consumer

Giả sử 8 consumers, mỗi consumer prefetch 250, mỗi body trung bình 128 KiB:

\[
8 \times 250 \times 128\ \text{KiB} \approx 250\ \text{MiB}
\]

Đây chỉ là **tổng kích thước body có thể đang in-flight**, chưa kể Java object overhead, deserialization, thread stack, buffer và bản sao payload. Không thể coi con số này là heap usage chính xác, nhưng nó cho thấy rủi ro khi tăng prefetch trên hệ thống xử lý **message lớn**.

Bảng minh họa:

| Prefetch | Consumers | Tổng delivery chưa ACK tối đa | Đánh đổi chính |
|---:|---:|---:|---|
| 1 | 8 | 8 | Ít memory/redelivery window, có thể hụt throughput |
| 10 | 8 | 80 | Cân bằng để thử nghiệm với message vừa |
| 50 | 8 | 400 | Pipelining cao hơn, fairness cần đo |
| 250 | 8 | 2.000 | Thích hợp một số workload nhanh; rủi ro lớn với payload nặng |

**Không hiểu nhầm:** `messages_ready` thấp đi khi broker giao nhiều message cho client không có nghĩa business lag đã giảm; chúng có thể chuyển sang `messages_unacknowledged` hoặc client-side buffer.

### 5.3. Ordering và phân phối công bằng

Prefetch cao có thể làm một consumer giữ nhiều deliveries, trong khi một consumer vừa khởi động không nhận được backlog tương ứng. Khi có nhiều consumers, xử lý hoàn tất có thể **không theo thứ tự publish** vì callback times khác nhau; `prefetch=1` **không tự đảm bảo toàn hệ thống strict ordering** khi vẫn chạy đồng thời nhiều consumers.

Với workflow cần thứ tự theo đơn hàng:

- Đặt `prefetch=1` và chỉ **một consumer** cho queue nếu strict global order thực sự bắt buộc.
- Hoặc partition/routing theo `aggregateId`, sử dụng `aggregateVersion` và optimistic concurrency/version checks.
- Dùng business event ID để dedup khi failover hoặc retry.
- Đo throughput/latency sau thay đổi, vì giảm prefetch có thể giảm khả năng tận dụng đường truyền.

### 5.4. Prefetch có thể bị điều chỉnh bởi batch settings

Trong **SMLC**, khi `batchSize > prefetchCount`, container có thể tăng prefetch hiệu lực để phù hợp `batchSize`. Với **DMLC**, `messagesPerAck` nếu lớn hơn prefetch có thể làm prefetch hiệu lực được tăng tương ứng.

| Cấu hình | Hệ quả cần đo |
|---|---|
| SMLC `prefetch=5`, `batchSize=20` | Container có thể tăng prefetch lên ít nhất 20 |
| DMLC `prefetch=5`, `messagesPerAck=20` | Container có thể tăng prefetch lên ít nhất 20 |
| ACK mode `NONE` | Prefetch control không mang ý nghĩa bình thường vì broker không chờ ACK |
| `globalQos=true` | Prefetch được áp theo channel thay vì mặc định theo từng consumer, khác broker/client semantics |

**Upgrade checklist:** Kiểm tra giá trị broker thực sự nhìn thấy ở consumer detail (prefetch, ack required), không chỉ nhìn một field cấu hình `prefetch=5` trong YAML.

### 5.5. Prefetch thấp bao nhiêu là hợp lý?

Các trường hợp nên thử `1` hoặc một số nhỏ:

- Message body lớn hoặc callback chậm.
- Consumer dùng manual ACK và cần kiểm soát số event chưa commit.
- Workload cần công bằng giữa consumers hoặc thứ tự chặt.
- Downstream database/HTTP có quota thấp.
- Mất connection thường xuyên và redelivery window phải nhỏ.

Các trường hợp có thể tăng dần:

- Handler rất nhanh, payload nhỏ.
- Network RTT đáng kể so với processing latency.
- Nhiều consumers đọc lưu lượng lớn và ack/CPU không phải bottleneck.
- Đã có heap/latency/duplicate metrics và khả năng rollback.

**Không có prefetch “chuẩn cho tất cả ứng dụng”.** Khi nâng version, cách an toàn là **pin giá trị đang cho hành vi mong muốn**, benchmark riêng việc đổi prefetch và mới xét thay đổi production.

## 6. Acknowledge mode: AUTO, MANUAL, NONE

### 6.1. AUTO không phải broker auto-ack

| Spring `AcknowledgeMode` | Cách hoạt động | Rủi ro khi nhầm |
|---|---|---|
| `AUTO` | Container ACK khi listener hoàn thành bình thường; exception được xử lý theo error/requeue policy | Tên AUTO **không** có nghĩa broker ACK ngay khi deliver |
| `MANUAL` | Ứng dụng phải tự gọi `Channel.basicAck/basicNack/basicReject`, trừ các cơ chế container xử lý fatal/async đặc biệt | Quên ACK làm unacked kẹt; double ACK đóng channel |
| `NONE` | RabbitMQ auto-ack theo cách broker gọi, không đợi ACK từ consumer | Crash giữa delivery và DB commit có thể mất message |

`AUTO` là default được tài liệu container mô tả. Khi nâng cấp, tránh đổi sang `NONE` để cải thiện tốc độ ACK mà bỏ qua hệ quả mất xử lý khi consumer crash.

### 6.2. Manual ACK cần rõ ranh giới DB commit

```java
@Component
public class ManualOrdersConsumer {

    private final OrderService orderService;

    public ManualOrdersConsumer(OrderService orderService) {
        this.orderService = orderService;
    }

    @RabbitListener(
            queues = "orders.manual",
            containerFactory = "manualAckFactory")
    public void onOrder(Message message, Channel channel)
            throws IOException {

        long tag = message.getMessageProperties().getDeliveryTag();

        try {
            // Service commit nghiệp vụ và marker eventId idempotent.
            orderService.applyOnce(message.getBody());
        } catch (InvalidOrderEventException invalid) {
            channel.basicReject(tag, false); // DLX / drop theo broker
            return;
        } catch (RetryableOrderException temporary) {
            channel.basicNack(tag, false, true); // requeue có giới hạn/policy
            return;
        }

        channel.basicAck(tag, false);
    }
}
```

Trong ví dụ `OrderService`, `InvalidOrderEventException` và `RetryableOrderException` là types của ứng dụng. Chúng phải được định nghĩa và phân loại chính xác khi dùng thật. `Channel` là `com.rabbitmq.client.Channel`; `Message` là `org.springframework.amqp.core.Message`.

**Lưu ý:**

- Factory `manualAckFactory` phải đặt `AcknowledgeMode.MANUAL`; đừng dùng một factory AUTO rồi tự ACK tùy ý.
- NACK `requeue=true` không có backoff tự thân; với poison message nó có thể tạo vòng lặp nóng. Dùng retry policy với delay/limit thay vì NACK vô hạn.
- Nếu DB commit thành công nhưng `basicAck` thất bại do channel/network, message có thể redeliver: **idempotency bắt buộc**.
- Nếu `basicAck` ném exception, đừng tự động `basicNack` lần nữa trên channel có thể đã đóng; để recovery xử lý theo trạng thái channel.
- Không dùng `multiple=true` tùy tiện khi xử lý song song trên cùng channel, vì có thể ACK những delivery khác chưa commit.

### 6.3. Listener trả kết quả bất đồng bộ

Với `CompletableFuture`, `Mono` hoặc Kotlin `suspend`, “method trả về” không đồng nghĩa công việc đã hoàn thành. Spring AMQP có mốc thay đổi quan trọng: từ **2.2.21 / 2.3.13 / 2.4.1**, khi phát hiện async return type thích hợp, framework **tự điều chỉnh ACK mode sang MANUAL** để xác nhận khi async completion kết thúc.

Tuy nhiên, khi cấu hình một hệ thống mới hoặc migration, **nên cấu hình MANUAL explicit và kiểm thử**; tránh phụ thuộc việc phát hiện return type sau refactor.

```java
@Bean("asyncOrdersFactory")
SimpleRabbitListenerContainerFactory asyncOrdersFactory(
        ConnectionFactory cf) {

    SimpleRabbitListenerContainerFactory f =
            new SimpleRabbitListenerContainerFactory();
    f.setConnectionFactory(cf);
    f.setAcknowledgeMode(AcknowledgeMode.MANUAL);
    f.setPrefetchCount(8);
    f.setDefaultRequeueRejected(false);
    return f;
}
```

Ví dụ async method minh họa:

```java
@RabbitListener(
        queues = "orders.async",
        containerFactory = "asyncOrdersFactory")
public CompletableFuture<Void> applyAsync(String json) {
    try {
        return orderService.applyOnceAsync(json);
    } catch (RuntimeException ex) {
        // Phải trả về future thất bại để framework quyết định ACK/NACK.
        return CompletableFuture.failedFuture(ex);
    }
}
```

Ở đây `orderService.applyOnceAsync` phải trả future **chỉ hoàn thành thành công sau khi business effect thực sự commit**, không phải sau khi đưa task vào executor. Nếu dùng `MANUAL` với return type void/đồng bộ, ứng dụng phải tự basicAck; không thể áp toàn bộ ví dụ cho mọi listener.

**Một lỗi rất khó thấy:** Async method ném exception **trước khi tạo future**, và ứng dụng nuốt nó/trả future thành công. Container có thể ACK message dù chưa xử lý. Hãy kiểm thử cả đường lỗi xảy ra trước khi future được tạo. Với Spring AMQP 3.0.5+, hành vi `RabbitListenerErrorHandler` cho async return types cũng có thay đổi được tài liệu ghi nhận.

## 7. Xử lý lỗi: defaultRequeueRejected không quyết định mọi exception

### 7.1. Cây quyết định của một lỗi

```text
Delivery đến listener/container
           |
           v
   Có lỗi xảy ra?
           |
           +--- Không ---> ACK theo AUTO/logic MANUAL
           |
           +--- Có
                  |
                  v
        ErrorHandler / Retry Advice
                  |
           +------+------------------------+
           |                               |
  Fatal conversion/validation        Runtime business error
           |                               |
           v                               v
 ConditionalRejectingErrorHandler    retry/advice/recoverer
  có thể REJECT NO-REQUEUE                  |
           |                       exhausted hoặc không retry
           v                               |
        DLX / drop                          v
                               defaultRequeueRejected / exception
                                            |
                                  +---------+----------+
                                  |                    |
                               requeue              reject
                                  |                    |
                              redeliver             DLX/drop
```

**Quan trọng:** `defaultRequeueRejected=true` chỉ là **quy tắc fallback** khi listener thất bại và không có exception/error handler/recoverer override hành vi. Nó không bảo đảm mọi message sẽ được đưa lại vào queue.

### 7.2. Default values mà nhiều đội dựa vào nhầm

Trong Spring AMQP 3.2:

- `AcknowledgeMode.AUTO` mặc định.
- `defaultRequeueRejected=true` mặc định.
- `ErrorHandler` mặc định là `ConditionalRejectingErrorHandler`.
- Fatal errors trước listener như conversion/validation có thể bị **reject không requeue** dù `defaultRequeueRejected=true`.
- Khi từ chối không requeue, broker có thể **dead-letter** nếu queue có DLX; nếu không có DLX hoặc target không hợp lệ, message có thể bị loại.
- `AmqpRejectAndDontRequeueException` yêu cầu không requeue trong đường xử lý phù hợp.
- `ImmediateRequeueAmqpException` có thể yêu cầu requeue kể cả khi container default không requeue.

**Không chỉ test một RuntimeException chung.** Test ít nhất: transient DB error, payload JSON không parse được, bean validation lỗi và exception nghiệp vụ cố ý reject.

### 7.3. ConditionalRejectingErrorHandler phân loại fatal

Mặc định, error handler đánh dấu fatal đối với một số exception như:

- `org.springframework.amqp.support.converter.MessageConversionException`: converter thất bại.
- `org.springframework.messaging.converter.MessageConversionException`: conversion vào method argument.
- `MethodArgumentNotValidException`: Bean Validation trên listener argument.
- `MethodArgumentTypeMismatchException`: type không phù hợp.
- Một số trường hợp `NoSuchMethodException` và `ClassCastException` được thêm vào chiến lược fatal từ Spring AMQP 1.6.3.

Có thể xảy ra **trước khi user method bắt đầu**. Nếu instrument chỉ trong business method, bạn sẽ không thấy thời gian/error của những messages này; cần container error logs và DLQ metrics.

Ví dụ một `@RabbitListener` kỳ vọng DTO:

```java
@RabbitListener(queues = "orders.json")
public void consume(OrderCreated event) {
    orderService.applyOnce(event);
}
```

Nếu JSON hoặc type metadata không thể convert thành `OrderCreated`, method `consume` có thể **chưa từng chạy**, nhưng error handler vẫn phân loại fatal và broker có thể reject/no-requeue.

### 7.4. Xử lý x-death khi replay DLQ

Một pattern cũ:

```text
work queue -> converter lỗi -> DLQ
   ^                          |
   |                          | TTL expire + dead-letter back
   +--------------------------+
```

Nếu payload hỏng vĩnh viễn, vòng DLQ–TTL có thể chạy mãi. Từ **Spring AMQP 2.1**, `ConditionalRejectingErrorHandler` kiểm tra header `x-death` khi message có fatal exception và có thể **log rồi discard** message để chặn vòng lặp. Thuộc tính `discardFatalsWithXDeath` điều khiển hành vi này; mặc định theo tài liệu là tránh lặp.

**Rủi ro khi nâng cấp:** Một hệ thống vốn dựa vào DLQ-TTL replay liên tục có thể thấy message “mất khỏi retry loop” sau một lần quay về vì error handler đã chủ đích discard fatal. Không được sửa vội bằng cách bật mọi requeue; cần phân loại message poison, quarantine vĩnh viễn có audit/replay riêng, và xác định yêu cầu lưu giữ.

Từ **2.1.9**, fatal pre-listener errors cũng bị reject/no-requeue mặc định ngay cả với `MANUAL`, vì listener có thể không có cơ hội ACK/NACK. Điều này thay đổi tập message đang ở trạng thái unacked khi so sánh với phiên bản cũ.

### 7.5. Custom fatal strategy theo exception nghiệp vụ

Nếu một exception là **không thể khôi phục** (ví dụ `UnsupportedEventSchemaException`), có thể mở rộng chiến lược fatal:

```java
public final class OrderFatalExceptionStrategy
        extends ConditionalRejectingErrorHandler.DefaultExceptionStrategy {

    @Override
    protected boolean isUserCauseFatal(Throwable cause) {
        return cause instanceof UnsupportedEventSchemaException;
    }
}
```

Đưa vào factory:

```java
@Bean("ordersStrictFactory")
SimpleRabbitListenerContainerFactory ordersStrictFactory(
        ConnectionFactory cf) {
    SimpleRabbitListenerContainerFactory f =
            new SimpleRabbitListenerContainerFactory();
    f.setConnectionFactory(cf);
    f.setAcknowledgeMode(AcknowledgeMode.AUTO);
    f.setPrefetchCount(10);
    f.setDefaultRequeueRejected(true);

    f.setErrorHandler(
            new ConditionalRejectingErrorHandler(
                    new OrderFatalExceptionStrategy()));
    return f;
}
```

`UnsupportedEventSchemaException` do ứng dụng định nghĩa. Chiến lược custom ở trên cần **được test với wrapped causes** mà listener thực tạo ra: nếu exception nằm trong các lớp wrapping bất ngờ, việc override phải được rà soát. Không tự đánh dấu mọi `RuntimeException` là fatal vì lỗi DB/socket tạm thời sẽ bị reject thay vì retry.

**Khuyến nghị:** Ưu tiên định nghĩa error policy tường minh theo nhóm **transient vs permanent**. Với business errors có thể sinh ra sau conversion, việc chủ động throw `AmqpRejectAndDontRequeueException` hoặc dùng recoverer có kiểm soát thường dễ hiểu hơn một danh sách fatal không được document.

## 8. Retry advice, recoverer và thay đổi major version 4.x

### 8.1. Retry ở listener không giống broker redelivery

Có ba vòng lặp khác nhau:

1. **In-memory retry** bên trong listener/advice: có thể xử lý lại cùng delivery trước khi gửi ACK/NACK cho broker.
2. **Broker requeue/redelivery:** NACK/reject với requeue hoặc channel loss làm broker giao lại; không có backoff mặc định.
3. **Delayed retry qua retry queue/DLX hoặc ứng dụng republish:** Message qua queue khác hay publish attempt khác, có delay, TTL, metrics và có thể thay `x-death`.

Đối với một nâng cấp, phải kiểm tra **vòng lặp nào đang chịu trách nhiệm**, không chỉ nhìn tổng redelivery.

### 8.2. Spring AMQP 3.2: ví dụ retry với recoverer

Trong stack **Spring AMQP 3.2** dùng Spring Retry API được hỗ trợ tại phiên bản đó:

```java
@Bean("retryOrdersFactory")
SimpleRabbitListenerContainerFactory retryOrdersFactory(
        ConnectionFactory cf) {

    SimpleRabbitListenerContainerFactory f =
            new SimpleRabbitListenerContainerFactory();
    f.setConnectionFactory(cf);
    f.setPrefetchCount(10);
    f.setAcknowledgeMode(AcknowledgeMode.AUTO);

    f.setAdviceChain(
            RetryInterceptorBuilder.stateless()
                    .maxAttempts(3)
                    .backOffOptions(200L, 2.0, 2_000L)
                    .recoverer(new RejectAndDontRequeueRecoverer())
                    .build());

    return f;
}
```

Imports liên quan: `org.springframework.amqp.rabbit.config.RetryInterceptorBuilder`, `org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer` và các class factory/connection tương ứng.

**Hành vi:** Khi số attempts trong advice bị vượt quá, recoverer có thể yêu cầu reject không requeue để broker DLX/drop tùy queue policy. `maxAttempts(3)` gồm cả lần thử đầu, không có nghĩa “3 lần retry sau lần đầu”. Không dùng cấu hình này khi muốn giữ message lỗi nhưng queue không có DLQ/retention.

### 8.3. Khi nâng lên Spring AMQP 4.x

Theo tài liệu **Changes in 4.0 Since 3.2**:

- Spring AMQP 4.0 đòi **Spring Framework 7**; phải nâng BOM/Boot/Java theo compatibility matrix chính thức.
- API retry chuyển từ `org.springframework.retry:spring-retry` sang cơ chế **Spring Core Retry**, làm một số import/builder/infrastructure và recoverer thay đổi. Không copy nguyên snippet `RetryInterceptorBuilder` của stack 3.2 rồi mặc định biên dịch ở 4.x.
- Jackson 3 được bổ sung, các converters Jackson 2 bị deprecated for removal; cần test JSON type mapping, header `__TypeId__`, content type và schema.
- Một module RabbitMQ AMQP 1.0 riêng xuất hiện ở dòng 4.x; không nhầm `@AmqpListener` cho AMQP 1.0 với `@RabbitListener` sử dụng AMQP 0-9-1.

**Quy trình migration:** Đóng băng bảng hành vi ACK/retry/DLQ ở baseline, chuyển sang API retry mới theo official 4.x docs, rồi chạy lại **cùng test vectors**. Mục tiêu là bảo tồn semantics nghiệp vụ, không nhất thiết giữ nguyên class name.

## 9. So sánh missingQueuesFatal, autoDeclare và startup behavior

Thay đổi loại listener container cũng có thể thay đổi việc ứng dụng **fail fast** hay **cứ retry không có consumer** khi queue không tồn tại.

Trong Spring AMQP 3.2, theo Javadoc:

| Tính chất | SMLC | DMLC |
|---|---|---|
| `missingQueuesFatal` default | **true** | **false** |
| `autoStartup` | true | true |
| `autoDeclare` | true khi có admin phù hợp | true khi có admin phù hợp |
| Recovery | Recovery/declare retries theo cấu hình và context | Monitor consumers/registration theo cơ chế DMLC |

**Trường hợp tác động:** Sau khi đổi sang DMLC, ứng dụng có thể báo service đã start trong khi nó đang cố đăng ký lại consumer vì queue chưa được tạo, thay vì fail context giống trước. Điều đó **không nhất thiết là bug framework**; đó là khác biệt lifecycle/default cần có readiness/alert tương ứng.

### 9.1. Cấu hình rõ để không phụ thuộc default

```java
f.setAutoStartup(true);
f.setMissingQueuesFatal(true); // Fail fast nếu queue critical thiếu.
f.setContainerCustomizer(container ->
        container.setAutoDeclare(false)); // Topology do IaC provision.
```

Đây là ví dụ **chính sách vận hành** áp trên một factory `f` của Spring AMQP 3.2 cho queue production đã được provision trước. `setAutoDeclare` là thuộc tính của **listener container**, do đó ta dùng `setContainerCustomizer` trên factory để cấu hình nó. Với queue tạm thời/auto-delete, `missingQueuesFatal=false` có thể cần thiết để container chờ queue tái tạo. Không áp một quy tắc cho mọi queue.

**Lưu ý `RabbitAdmin`:** Khi `autoDeclare=true` và container thấy queue thiếu, nó có thể dùng RabbitAdmin để redeclare topology trong điều kiện được hỗ trợ. Với nhiều admins/connection factories, phải chỉ định admin đúng broker/vhost; nếu không, hành vi khác có thể phát sinh khi upgrade.

### 9.2. Cẩn thận với mismatched queue arguments

Một queue hiện tại là classic nhưng code mới khai báo `x-queue-type=quorum` cùng tên có thể gây `PRECONDITION_FAILED` (inequivalent arguments). Không coi lỗi này là container startup failure ngẫu nhiên.

`mismatchedQueuesFatal` khi bật có thể phát hiện khác biệt về queue attributes/arguments sớm, nhưng không thay thế migration topology. Với nhiều admins, cần cấu hình explicit phù hợp. Đừng dùng `ignoreDeclarationExceptions` hoặc tắt kiểm tra như cách “nâng cấp nhanh” khi dữ liệu cần bảo toàn.

## 10. Shutdown, force stop và duplicate window

Khi rollout phiên bản mới, container cũ thường dừng trong lúc còn messages đang xử lý. Cần đối chiếu:

- `shutdownTimeout`: thời hạn chờ workers/callback hoàn tất.
- `forceCloseChannel`/force stop options: khi timeout, channel có thể đóng; unacked deliveries sẽ được broker xử lý lại.
- `prefetchCount`: số message đang giữ chưa ACK.
- SMLC `batchSize` và DMLC `messagesPerAck`: ACK có thể được gom, khiến số event cần redeliver sau crash lớn hơn.
- Nếu listener gọi HTTP/DB ngoài transaction, cần biết side effects có idempotency key.

```text
Before upgrade rollout:
    pod v1 -> delivery E -> DB COMMIT OK
                     |
                SIGTERM / timeout
                     |
              broker chưa nhận ACK
                     |
After rollout:
    pod v2 -> redelivery E
                     |
            dedup(eventId) -> ACK
```

**Không gọi “duplicate after deploy” là bug RabbitMQ ngay lập tức.** Redelivery của unacked message sau channel close là hành vi phù hợp at-least-once. Chất lượng migration phụ thuộc consumer idempotency.

Trong Spring AMQP 4.x, release notes còn đề cập thay đổi SMLC khi shutdown với pending reply của `RabbitTemplate` listener. Khi ứng dụng dùng RPC/request-reply qua listener, cần test shutdown cùng pending replies, thay vì chỉ kiểm tra event fire-and-forget.

## 11. Transaction DB, ACK/NACK và lỗi nghiệp vụ khi upgrade

Có ba điểm commit thường tách biệt:

```text
producer publish -> RabbitMQ confirm ACK
                               |
                               v
                         delivery tới consumer
                               |
                         @RabbitListener
                               |
                         DB transaction commit
                               |
                         container basic.ack
```

Với `AcknowledgeMode.AUTO`, listener bình thường kết thúc mới được container ACK; nếu xử lý DB và ACK không chung một transaction phân tán, vẫn có **crash gap**. Tăng prefetch, chuyển container type hoặc đổi batch size **không sửa gap này**.

Một consumer idempotent có thể dùng:

```sql
CREATE TABLE processed_events (
    consumer_name varchar(100) NOT NULL,
    event_id uuid NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Trong **cùng DB transaction**:

1. Insert `(consumer_name, event_id)` với unique constraint.
2. Nếu insert thành công, áp dụng business effect.
3. Commit DB.
4. Cho listener ACK theo AUTO hoặc chủ động ACK theo MANUAL.
5. Nếu message redeliver, marker giúp tránh lặp effect.

Khi nâng cấp, test phải đối chiếu **DB side effect count**, không chỉ số lần listener method được gọi. Có thể nhận 2 deliveries nhưng chỉ có **một lần commit nghiệp vụ**.

### 11.1. Quorum queue delivery limit là trục broker riêng

Nếu đồng thời nâng RabbitMQ broker, đặc biệt các phiên bản 4.x:

- Default quorum queue delivery limit đã thay đổi trong lịch sử RabbitMQ.
- Hành vi tính `delivery-count` cho `basic.nack(requeue=true)` khác ở RabbitMQ 4.3 so với 4.2.
- Một consumer có exception/requeue giống hệt trước upgrade vẫn có thể đi DLQ theo vòng khác.

Do vậy cùng test suite phải ghi **broker version + queue type + policy**; không đổ mọi thay đổi retry/DLQ cho Spring AMQP. Với ứng dụng dùng classic queue, cần một nhánh kiểm thử riêng và không áp các điều kiện quorum queue cho tất cả.

## 12. Xây compatibility matrix trước/sau

Trước mỗi nâng cấp, ghi lại **giá trị mong muốn**, **giá trị hiệu lực thực tế** và **bằng chứng test**:

| Hạng mục | Baseline đang chạy | Target mong muốn | Cách xác minh |
|---|---|---|---|
| Spring BOM, AMQP, Java client | Version cụ thể trong deployment | Version được hỗ trợ | Build dependency report, lockfile |
| Broker/queue type | Classic/quorum, RabbitMQ version | Giữ hoặc migration rõ | Management/CLI |
| Listener factory | SMLC/DMLC class | Được quyết định explicit | Inspect bean/container type |
| Consumer counts | Ví dụ 2–4 | Không thay đổi ngoài kế hoạch | RabbitMQ consumers và logs |
| Prefetch | Ví dụ 10 | 10 | Broker consumer details/unacked cap |
| ACK mode | AUTO | AUTO | Test success/failure/DB commit |
| Fatal error handling | ConditionalRejecting handler | Contract giữ nguyên | Poison message test |
| Requeue fallback | true/false | Lựa chọn rõ | Transient exception test |
| Retry/backoff | 3 attempts, delay | Tương đương logic | Count attempts + timing |
| DLX/DLQ | Destination cụ thể | Không mất sự kiện lỗi | DLQ assertions |
| Async ACK | Future completion | Không ACK sớm | Controlled future test |
| Startup/missing queue | Fail fast hoặc retry | Được quy định | Absent queue test |
| Shutdown | Graceful và idempotent | Không làm lặp effect | Termination test |
| Metrics/tracing | Ready, unacked, p95, DLQ | Có dashboard theo SLO | Before/after comparison |

**Đừng dùng “lệnh deploy thành công” làm bằng chứng compatibility.** Một ứng dụng có thể báo `UP` khi listener chưa subscribe, hoặc ready giảm do message bị reject thay vì business commit.

### 12.1. Baseline nên lưu ở định dạng dễ review

Ví dụ cấu hình được quyết định có chủ đích:

```yaml
messaging-contract:
  consumer: orders-projection
  queue: orders.work
  container: simple
  min-consumers: 2
  max-consumers: 4
  prefetch: 10
  ack-mode: AUTO
  transient-error: bounded-retry
  permanent-error: reject-to-dlq
  duplicate-policy: dedup-by-event-id
  expected-startup: fail-if-critical-queue-missing
```

Đây là **tài liệu hợp đồng gợi ý**, không phải các Spring Boot properties thật; đừng copy nguyên block `messaging-contract` rồi mong framework tự áp dụng. Ánh xạ các quyết định vào `spring.rabbitmq.listener.*` hoặc Java config và kiểm tra hiệu lực.

## 13. Integration tests để khóa hành vi qua upgrade

**Dùng broker thật** (ví dụ RabbitMQ Testcontainers) cho các semantics ACK/NACK/DLX/prefetch. Mockito phù hợp unit test phân loại lỗi hoặc service idempotency, nhưng không xác nhận được broker requeue, `x-death`, queue arguments hay consumer registration.

### 13.1. Bộ fixture tối thiểu

Tạo topology test độc lập:

```text
direct exchange: it.orders.events
         |
         | routing key "created"
         v
durable queue: it.orders.work
         |
         | reject/no requeue
         v
dead-letter exchange: it.orders.dlx
         |
         v
queue: it.orders.dead
```

Mỗi test dùng queue và consumer ID riêng, không có consumer khác cạnh tranh, xóa topology test sau kiểm thử. Đừng đổi production queue type chỉ để tái hiện lỗi.

### 13.2. Test prefetch thực tế, không đo bằng sleep

1. Listener dùng `prefetch=1`; handler giữ một `CountDownLatch` tại lần xử lý đầu tiên để **chưa ACK**.
2. Publish ba events đã có ID riêng.
3. Khi handler #1 đang chờ, đối chiếu broker `unacked` không vượt số consumer có thể nhận, và `ready` còn backlog khi chỉ một consumer.
4. Release latch, chờ broker ACK bằng `Awaitility`, xác minh handler nhận đủ events.
5. Lặp lại với `prefetch=10` rồi đo unacked/ready; đừng bắt buộc chính xác unacked=10 nếu broker chỉ có 3 events hoặc callback quá nhanh.
6. Ghi lại không chỉ queue depth mà cả **DB commits**, max in-flight và heap khi chạy dữ liệu lớn.

```java
@Component
public class PrefetchProbeListener {

    private final CountDownLatch release = new CountDownLatch(1);
    private final AtomicInteger calls = new AtomicInteger();

    @RabbitListener(
            queues = "it.orders.work",
            containerFactory = "testPrefetchFactory")
    public void handle(String body) throws InterruptedException {
        calls.incrementAndGet();
        // Trong lab, giữ callback chưa hoàn tất để đo broker unacked.
        if (!release.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Probe đã hết hạn");
        }
    }

    public void resume() {
        release.countDown();
    }

    public int callCount() {
        return calls.get();
    }
}
```

Đây là **probe dành cho test**, không đưa latch vào production. Khi dùng SMLC một consumer, `@RabbitListener` chạy tuần tự trên worker; với prefetch cao, broker có thể giao thêm messages trước khi callback hiện tại hoàn tất. `RabbitAdmin.getQueueProperties` có thể trả số message ready và consumer count, nhưng để lấy unacked chính xác hãy dùng Management API/metrics hoặc broker CLI phù hợp.

### 13.3. Test fatal conversion và DLQ

1. Publish payload JSON hợp lệ → listener xử lý/ACK bình thường.
2. Publish payload malformed JSON có content type phù hợp để converter cố parse → kỳ vọng error trước listener.
3. Kiểm tra `ConditionalRejectingErrorHandler` phân loại fatal và message **không bị requeue vô hạn**.
4. Nếu DLX hợp lệ và broker policy cho phép, xác nhận message vào DLQ. Không chỉ assert ready giảm; có thể nó bị drop.
5. Với payload có `x-death` do broker dead-letter rồi quay lại, kiểm tra chính sách discard fatal phù hợp version.
6. Ghi rõ đường xảy ra trước listener, số lần listener thực sự được gọi và lý do dead-letter.

### 13.4. Test business transient error và retry

1. Service tạm thời ném exception giả lập DB timeout.
2. Nếu `defaultRequeueRejected=true` và không có recoverer override, broker có thể redeliver; kiểm soát test để không tạo loop vô hạn.
3. Nếu có retry advice, kiểm tra số attempts và backoff trong JVM, phân biệt broker redeliver count.
4. Khi exhausted, xác nhận recoverer quyết định đường retry/DLX như hợp đồng.
5. Sau khi DB phục hồi, event được commit đúng một lần.
6. Ghi nhận reason/headers, tránh so sánh string exception message dễ thay đổi giữa versions.

### 13.5. Test async result và ACK timing

```text
RabbitMQ delivers event E
          |
          v
listener returns INCOMPLETE CompletableFuture
          |
       unacked = 1
          |
    future completes successfully
          |
          v
       broker ACK
```

Với error completion, test theo `defaultRequeueRejected`/exception type; không mặc định mọi async failure đều được ACK hoặc đều đi DLQ. Với future completion trước khi DB commit, test phải **fail**, vì nó chỉ ra service đã thiết kế completion boundary sai.

### 13.6. Test stop/start và missing queue

- Với SMLC/DMLC, xác minh `RabbitListenerEndpointRegistry` biết ID và loại container mong đợi.
- Nếu `autoStartup=false`, broker consumer count phải bằng 0 cho listener đó trước `start()`.
- Thiếu critical queue: kiểm tra lựa chọn **fail fast** hoặc **retry** đúng như cấu hình explicit.
- Sau start, xác minh registration và message consumption.
- Graceful stop giữa nhiều messages: đối soát unacked/redelivery và business idempotency sau restart.

## 14. Testcontainers/JUnit: khung thực thi hồi quy

Một khung Java test có thể dùng:

```java
@Testcontainers
@SpringBootTest(properties = {
        "spring.rabbitmq.listener.type=simple",
        "spring.rabbitmq.listener.simple.prefetch=1",
        "spring.rabbitmq.listener.simple.acknowledge-mode=auto",
        "spring.rabbitmq.listener.simple.auto-startup=true"
})
class ListenerUpgradeIT {

    @Container
    static RabbitMQContainer rabbit =
            new RabbitMQContainer(
                    DockerImageName.parse("rabbitmq:4.1-management"));

    @DynamicPropertySource
    static void rabbitConnection(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        registry.add("spring.rabbitmq.username",
                rabbit::getAdminUsername);
        registry.add("spring.rabbitmq.password",
                rabbit::getAdminPassword);
    }

    @Autowired RabbitListenerEndpointRegistry listeners;

    @Test
    void selectedContainerIsSimple() {
        MessageListenerContainer c =
                listeners.getListenerContainer("ordersUpgradeTest");

        assertThat(c).isNotNull();
        assertThat(c).isInstanceOf(SimpleMessageListenerContainer.class);
    }
}
```

Các imports cần bổ sung: `org.junit.jupiter.api.Test`, `org.springframework.boot.test.context.SpringBootTest`, `org.springframework.beans.factory.annotation.Autowired`, `org.springframework.test.context.DynamicPropertySource`, `org.springframework.test.context.DynamicPropertyRegistry`, `org.testcontainers.containers.RabbitMQContainer`, `org.testcontainers.junit.jupiter.Container`, `org.testcontainers.junit.jupiter.Testcontainers`, `org.testcontainers.utility.DockerImageName`, `org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry`, `org.springframework.amqp.rabbit.listener.MessageListenerContainer`, `org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer` và AssertJ `assertThat`.

**Phạm vi snippet:** Đây là khung, không phải một test class độc lập có toàn bộ topology và listener beans. Cần có một `@RabbitListener(id="ordersUpgradeTest",...)` trong test context, queue được provision đúng và cleanup sau test. Spring Boot auto-config chỉ áp cho listener không trỏ tới **custom factory**; nếu dùng `containerFactory` riêng, nên assert class custom đó và thử effective prefetch qua broker metrics.

Với Testcontainers 2.x, package/container module có thể đã thay đổi; không nâng Testcontainers đồng thời với Spring AMQP nếu đang cố cô lập lỗi container behavior. Dùng phiên bản được dự án hỗ trợ và pin Docker image trong CI.

### 14.1. Không viết assertion phụ thuộc timing mong manh

Tránh:

```java
Thread.sleep(500);
assertThat(unacked).isEqualTo(10);
```

Thay bằng `CountDownLatch` cho thời điểm handler đang block và `Awaitility` để poll trạng thái broker trong timeout hữu hạn. Với concurrency và scheduling khác nhau, hãy assert **đặc tính cần bảo vệ** (ví dụ unacked không vượt prefetch × consumers, message chưa ACK không bị coi đã xử lý), không đòi mọi snapshot ra chính xác cùng số theo từng mili-giây.

## 15. Plan rollout nâng cấp có thể rollback

### Giai đoạn A — Inventory và baseline

1. Liệt kê listener IDs, queue/vhost, connection factory, container type và scope triển khai.
2. Ghi phiên bản Spring Boot/AMQP/Framework, RabbitMQ Java client và broker; kiểm tra official support matrix.
3. Chụp **effective settings**: prefetch, ACK mode, concurrency, error handler, default requeue, retry advice, converter, missing-queue behavior.
4. Ghi ít nhất một tuần hoặc khoảng tải đại diện: throughput, ready/unacked, redelivery, DLQ, handler p95/p99, DB error rate và business end-to-end latency.
5. Thu thập mẫu event hợp lệ, event cũ, payload poison và retry cases có thể replay trong test.

### Giai đoạn B — Tách thay đổi

1. **Pin prefetch và ack/error policy explicit ở version cũ** nếu trước đó dựa vào default.
2. Chỉ nâng Spring AMQP/Boot trong nhánh thử nghiệm; chưa đổi queue type/broker policy.
3. Chạy static checks và **integration tests trên RabbitMQ thật**.
4. Nếu muốn đổi SMLC → DMLC, xem đó là một thay đổi **riêng** với bảng concurrency/batching/recovery tương ứng.
5. Chỉ sau khi hành vi listener được xác nhận mới benchmark prefetch và concurrency mới.

### Giai đoạn C — Canary và quan sát

1. Deploy canary với **queue/test routing tách biệt** nếu workload không cho phép nhiều consumer nhận chia message tùy ý.
2. Giữ stable event IDs; consumer idempotent trong DB transaction.
3. Theo dõi broker consumer count, ready/unacked, p95/p99, retry, DLQ, memory và connection/channel errors.
4. Tạo test faults nhỏ có kiểm soát: invalid payload, transient DB failure, lost connection, SIGTERM khi handler đang chạy.
5. So sánh dữ liệu nghiệp vụ đã commit, không chỉ method invocation counts.

### Giai đoạn D — Rollback an toàn

- Giữ đường rollback binary/config, nhưng phải xem **schema/database migration** có tương thích ngược không.
- Không downgrade giữa chừng khi queue đang được khai báo với arguments mới mà app cũ không hiểu.
- Nếu lỗi khiến poison message bị discard/drop, rollback **không khôi phục message đã mất**. Cần backup/outbox/replay ledger riêng.
- Ghi danh sách event outcomes UNKNOWN và redelivery để đối soát sau rollback.
- Không purge DLQ/backlog để dashboard trở về bình thường.
- Khi quay về version cũ, xác minh idempotency và client connectivity cùng broker hiện tại.

## 16. Dashboard chẩn đoán hồi quy sau upgrade

| Metric | Dấu hiệu | Hướng điều tra |
|---|---|---|
| `messages_unacknowledged` tăng mạnh | Prefetch tăng, handler chậm hoặc ACK timing thay đổi | Broker consumer prefetch, handler tracing, ack mode |
| `messages_ready` giảm nhưng DB commit không tăng | Message chuyển sang client buffer/unacked hoặc bị reject | Phân biệt ready/unacked và outcome |
| Consumer count khác baseline | Đổi SMLC ↔ DMLC/concurrency/missing queue | Factory type, consumersPerQueue, lifecycle |
| Redelivery tăng | NACK/requeue, channel closes, batch ACK hoặc lost consumer ACK | Exceptions, recovery log, prefetch/batch |
| DLQ tăng | Fatal handler/recoverer/policy mới | Conversion logs, x-death, defaultRequeueRejected |
| DLQ giảm bất thường nhưng lỗi vẫn còn | Có thể discard/drop thay vì quarantine | Fatal x-death handling, DLX target |
| Memory/GC tăng | 250 prefetch × nhiều consumer × payload lớn | Heap, buffer, queues, payload sizes |
| Handler p99 xấu đi | More concurrency/DB contention hoặc client thread starvation | SMLC vs DMLC thread pools, DB/HTTP |
| Listener báo UP nhưng consumer count=0 | MissingQueuesFatal/recovery khác | Queue/vhost, RabbitAdmin, logs |
| Unknown publish/consumer duplicate | Failover hoặc ACK gap | Stable event ID, outbox/processed ledger |

Không lấy `messages_ready=0` làm bằng chứng “không mất message”. Nó có thể giảm vì broker đã giao cho client, ACK, dead-letter hoặc drop. Cần kiểm tra **business commits và DLQ/retry ledger**.

## 17. Bài thực hành nâng cấp có kiểm chứng

### Bài 1 — Đọc mốc prefetch theo phiên bản

So sánh tài liệu Spring AMQP trước 2.0 và 2.0+. Không cấu hình `prefetch` trong hai test environments, quan sát broker consumer prefetch. Sau đó đặt explicit `prefetch=1` để chứng minh bản mới có thể giữ behavior cũ.

### Bài 2 — Đo memory/unacked khi nâng prefetch

Một queue durable có nhiều message body lớn, handler giữ latch. Thử `prefetch=1`, `10` và `250`, ghi unacked, heap/GC và ready. Giải thích vì sao ready giảm không có nghĩa processing latency giảm.

### Bài 3 — Chuyển SMLC sang DMLC

Thay container type trong lab, chuyển `concurrency=2-4` sang lựa chọn `consumersPerQueue` có chủ đích. Quan sát thread names, consumer count, khả năng thêm/xóa queue runtime và ACK timings. Kiểm tra chỗ nào SMLC `batchSize` không áp dụng cho DMLC.

### Bài 4 — Transient business failure

Cho service throw một transient exception trước DB commit. Với `defaultRequeueRejected=true` và không có retry advice, xem requeue behavior. Sau đó đặt retry hữu hạn + recoverer, đối chiếu số attempts và DLQ. Không cho phép loop vô hạn trên test broker.

### Bài 5 — Fatal JSON conversion

Gửi malformed JSON có content type phù hợp. Xác minh exception xảy ra trước listener, `ConditionalRejectingErrorHandler` reject/no-requeue và message đến DLQ **nếu DLX được provision**. Không chỉ assert không có listener invocation.

### Bài 6 — DLQ x-death replay

Dùng một message đã dead-letter từ broker quay về queue làm việc. Xác minh fatal `x-death` behavior theo version; có thể bị discard để tránh vòng lặp. Viết quarantine policy lưu bằng chứng thay vì dựa vào retry vô hạn.

### Bài 7 — MANUAL ACK và asynchronous return

Dùng `CompletableFuture` chưa hoàn tất và quan sát unacked; hoàn thành future rồi quan sát ACK. Cho future failed, xác minh NACK/requeue hoặc reject theo error policy. Thử trường hợp exception xảy ra trước khi future được trả về.

### Bài 8 — Thiếu critical queue

Tạo listener trỏ tới queue chưa được provision, chạy cả SMLC và DMLC với `missingQueuesFatal` mặc định/explicit. So sánh startup failure và recovery loop. Sau đó provision queue và xác minh consumer đăng ký.

### Bài 9 — Graceful shutdown/redelivery

Dừng container khi handler đã commit DB nhưng chưa ACK; restart và kiểm tra duplicate delivery, unique event ID, business effect chỉ ghi một lần. Thay prefetch và batch ACK để đo duplicate window.

### Bài 10 — Spring AMQP 3.2 → 4.x migration

Tạo compatibility matrix từ mốc framework/Java/Boot, retry API và converter. Thực hiện chuyển đổi thử nghiệm khi phụ thuộc tương thích. Chạy lại test vectors hợp lệ, poison, transient, async, missing queue, DLX và shutdown. Ghi các khác biệt thực tế trước khi canary.

**Tiêu chí đạt:** Cùng bộ event IDs đưa vào hai phiên bản phải có **cùng số business commits**, cùng đường retry/DLQ đã thỏa thuận, không có message bị discard ngoài chính sách; prefetch/concurrency/threading và recovery đều được đo, không đoán.

## 18. Checklist review trước khi nâng cấp production

- [ ] Đã xác định chính xác Boot, Framework, Spring AMQP, client và broker versions.
- [ ] Đã phân biệt SMLC/DMLC và xác minh container type **hiệu lực** cho từng `@RabbitListener`.
- [ ] `prefetchCount` explicit; không phụ thuộc default lịch sử 1/250.
- [ ] Concurrency của SMLC và `consumersPerQueue` của DMLC được tính đúng theo số queue.
- [ ] SMLC `batchSize` và DMLC `messagesPerAck` được xem xét riêng, không “đổi tên là xong”.
- [ ] ACK mode (AUTO/MANUAL/NONE) được chốt theo transaction boundary.
- [ ] Listener async chỉ ACK khi future hoàn tất; không return future thành công trước DB commit.
- [ ] `defaultRequeueRejected`, `ConditionalRejectingErrorHandler` và fatal strategy được test.
- [ ] Các tình huống fatal conversion, `x-death`, manual fatal và poison loops có đường xử lý rõ ràng.
- [ ] Retry có hạn, backoff và recoverer không làm drop message ngoài chính sách.
- [ ] DLX/DLQ tồn tại, có quyền/binding đúng và có kế hoạch replay/audit.
- [ ] Missing queue startup/recovery behavior được explicit theo criticality.
- [ ] Custom listener factories thực sự nhận observation, converter, retry/config tùy chỉnh cần thiết.
- [ ] Dừng/khởi động listener không làm lặp business effects nhờ event ID idempotency.
- [ ] Đã có integration tests trên broker thật cho ACK/NACK/requeue/DLX/prefetch.
- [ ] Đã kiểm tra metrics ready/unacked, consumers, errors, DLQ và DB commits trước/sau.
- [ ] Có canary, rollback và kế hoạch đối soát event IDs sau sự cố.

## 19. Những ngộ nhận phổ biến

| Nhận định sai | Điều đúng |
|---|---|
| “Version update chỉ thay APIs, runtime giống hệt.” | Defaults và lifecycle/exception classification có thể đổi. |
| “Prefetch của Spring AMQP từ trước tới nay là 250.” | Trước 2.0 là 1, từ 2.0 mặc định 250. |
| “Prefetch 250 nghĩa là 250 listener threads.” | Là giới hạn delivery chưa ACK, không phải số threads. |
| “Queue ready giảm chứng minh handler xử lý nhanh.” | Có thể message chỉ chuyển sang unacked/client buffer. |
| “SMLC và DMLC chỉ khác tên class.” | Khác threading, concurrency, batching, queue runtime update. |
| “SMLC concurrency=2-6 mang nguyên sang DMLC.” | DMLC dùng consumersPerQueue, giá trị một số. |
| “AUTO ACK của Spring là broker auto-ack.” | Spring AUTO ACK sau listener; broker auto-ack tương ứng NONE. |
| “defaultRequeueRejected=true thì mọi lỗi đều requeue.” | Fatal error handler có thể reject/no-requeue. |
| “Manual ACK bảo đảm framework không bao giờ reject.” | Fatal pre-listener errors có ngoại lệ, đặc biệt từ 2.1.9. |
| “Lỗi JSON sẽ luôn vào business method rồi try/catch.” | Conversion có thể xảy ra trước listener method. |
| “Có x-death thì framework luôn đưa lại DLQ.” | Fatal x-death có thể bị discard để tránh loop. |
| “Retry trong JVM và requeue broker là cùng một thứ.” | Khác attempt count, redelivery, backoff và observability. |
| “Spring Boot property type=direct áp vào mọi custom factory.” | Custom factories có thể bỏ qua Boot default configuration. |
| “Đổi prefetch về 1 tự bảo đảm thứ tự toàn hệ thống.” | Nhiều consumers, retry và concurrent processing vẫn phá ordering. |
| “Rollback phiên bản ứng dụng tự khôi phục message đã drop.” | Phải có dữ liệu nguồn/backup/outbox và quy trình replay. |

## 20. Câu hỏi tự kiểm tra

1. Vì sao cần liệt kê **Boot BOM, Spring AMQP, RabbitMQ client, broker version** thay vì chỉ một version?
2. Prefetch mặc định đổi từ 1 sang 250 ở mốc nào?
3. SMLC và DMLC khác nhau thế nào về thread và concurrency?
4. Vì sao DMLC `consumersPerQueue=2` nghe ba queues có thể tạo sáu consumer registrations?
5. `messages_ready` giảm và `messages_unacknowledged` tăng sau upgrade có thể chỉ ra điều gì?
6. `batchSize` của SMLC và `messagesPerAck` của DMLC ảnh hưởng prefetch ra sao?
7. Phân biệt `AcknowledgeMode.AUTO` với `NONE`.
8. Vì sao khi async listener trả `CompletableFuture`, ACK không được gửi lúc method return?
9. `defaultRequeueRejected=true` có bảo đảm malformed JSON message requeue không?
10. `ConditionalRejectingErrorHandler` thường phân loại fatal các nhóm lỗi nào?
11. Cơ chế `discardFatalsWithXDeath` giải quyết vấn đề gì và có rủi ro vận hành gì?
12. `missingQueuesFatal` mặc định của SMLC khác DMLC ở điểm nào trong 3.2?
13. Tại sao Spring Boot config YAML có thể không áp vào listener sử dụng custom factory?
14. Vì sao local retry advice cần phân biệt với broker redelivery?
15. Điều gì có thể thay đổi khi chuyển API retry từ Spring AMQP 3.2 sang 4.0?
16. Tại sao cần integration test bằng RabbitMQ thật khi nâng cấp?
17. Tại sao message được redeliver sau container shutdown không tự chứng minh broker lỗi?
18. Kết quả nào mới chứng minh upgrade không làm xử lý nghiệp vụ trùng?

**Đáp án gợi ý:** (1) Các lớp có defaults/semantics khác nhau. (2) Spring AMQP 2.0. (3) SMLC internal queue/worker; DMLC client threads và consumersPerQueue. (4) Hai mỗi queue × ba queues. (5) Delivery được prefetch nhiều hơn nhưng chưa ACK/commit. (6) Container có thể nâng prefetch tới ít nhất giá trị batching. (7) AUTO do container ACK sau callback, NONE broker không chờ ACK. (8) Phải chờ async completion. (9) Không, fatal error handler có thể reject. (10) Conversion, validation, mismatch và một số fatal method errors. (11) Chặn DLQ retry loop nhưng có thể discard message. (12) SMLC true, DMLC false. (13) Factory có thể tự tạo/override. (14) Một là thử lại trong cùng delivery, một là broker giao lại. (15) Spring Core Retry, Jackson 3, Framework 7. (16) Broker protocol/DLX/prefetch không mô phỏng đầy đủ bằng mock. (17) Unacked redelivery là at-least-once. (18) Unique event IDs và một business commit mỗi event, cùng audit/DLQ đúng policy.

## 21. Tổng kết

Khi nâng cấp **Spring AMQP**, ba nhóm hành vi cần khóa bằng hợp đồng kiểm thử là **container type**, **prefetch/ACK window** và **xử lý lỗi/retry/DLQ**. Mốc prefetch mặc định từ **1 lên 250 ở phiên bản 2.0** là ví dụ điển hình: business code không đổi nhưng messages unacked, memory, fairness, ordering và duplicate window có thể thay đổi lớn.

`SimpleMessageListenerContainer` và `DirectMessageListenerContainer` không có cùng mô hình threading, concurrency hay batching. `AcknowledgeMode.AUTO` không đồng nghĩa broker auto-ack; `defaultRequeueRejected=true` không vượt qua các quyết định fatal của `ConditionalRejectingErrorHandler`. Những mốc thay đổi về `x-death`, manual ACK fatal, async listener completion, Spring Core Retry/Jackson 3 phải được xét theo **đúng version**.

**Nguyên tắc triển khai:** Không nâng cấp dựa trên mặc định ẩn. Hãy **pin các giá trị quan trọng**, lập compatibility matrix, dùng broker thật để kiểm chứng prefetch, ACK/NACK, conversion, retry, DLX, listener startup/shutdown, rồi đối chiếu **business commits + event IDs** trước và sau canary.

### Tài liệu tham khảo chính thức

- [Spring AMQP — Changes in 2.0 Since 1.7](https://docs.spring.io/spring-amqp/reference/appendix/previous-whats-new/changes-in-2-0-since-1-7.html): prefetch mặc định 1 → 250, DMLC và các thay đổi container.
- [Spring AMQP 3.2 — Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/3.2/amqp/containerAttributes.html): bảng properties, ACK mode, prefetch, batching, defaultRequeueRejected, missingQueuesFatal.
- [Spring AMQP 3.2 — Choosing a Container](https://docs.spring.io/spring-amqp/reference/3.2/amqp/receiving-messages/choose-container.html): khác biệt SMLC và DMLC.
- [Spring AMQP 3.2 — Exception Handling](https://docs.spring.io/spring-amqp/reference/3.2/amqp/exception-handling.html): ConditionalRejectingErrorHandler, fatal conversion, x-death, manual ACK.
- [Spring AMQP 3.2 — Async @RabbitListener Return Types](https://docs.spring.io/spring-amqp/reference/3.2/amqp/receiving-messages/async-returns.html): ACK của CompletableFuture/Mono/suspend, các mốc version.
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): concurrency SMLC/DMLC và scaling.
- [Spring AMQP 4.0 — What's New](https://docs.spring.io/spring-amqp/reference/4.0/whats-new.html): Framework 7, Spring Core Retry, Jackson 3 và thay đổi API.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): Boot auto-config và chọn listener type.
- [RabbitMQ — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): cách RabbitMQ xử lý basic.qos và giới hạn deliveries chưa ACK.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ACK/NACK/requeue semantics và redelivery.


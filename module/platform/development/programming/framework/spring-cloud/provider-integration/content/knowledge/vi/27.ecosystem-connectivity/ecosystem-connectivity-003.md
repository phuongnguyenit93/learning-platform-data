# Chọn Spring Cloud Stream binder và nhận biết khác biệt ngữ nghĩa nhà cung cấp

## 1. Bối cảnh và mục tiêu

Trong module **Spring Cloud Provider Integration**, ứng dụng Spring Boot kết nối dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud, SDK và connector tương ứng. Với hệ thống event-driven, một service thường cần nhận event từ broker, xử lý payload, rồi phát event sang service hoặc hệ thống khác. Spring Cloud Stream cung cấp mô hình lập trình thống nhất cho producer và consumer message, đồng thời dùng **binder** để kết nối binding của ứng dụng với broker hoặc middleware cụ thể.

Binder giúp application code tập trung vào function và message contract. Tuy nhiên, abstraction này không xóa khác biệt giữa Kafka, RabbitMQ, Azure Event Hubs, Google Pub/Sub, Amazon Kinesis hay SQS. Các nền tảng có mô hình partition, acknowledgment, offset/checkpoint, redelivery, ordering, transaction, retry và dead-letter khác nhau. Một cấu hình có tên giống nhau có thể được binder diễn giải khác nhau hoặc không được hỗ trợ.

Bài học tập trung vào cách chọn binder dựa trên protocol và semantics của workload, cấu hình binding, consumer group, partitioning, retry và DLQ; sau đó đối chiếu các lựa chọn khi chạy trên AWS, Azure và Google Cloud. Mục tiêu là dùng abstraction có chủ đích, biết lúc nào phải dùng tính năng riêng của provider và tránh tin rằng đổi binder là có thể đổi broker mà không thay đổi vận hành.

Sau bài học, bạn có thể:

1. Giải thích Spring Cloud Stream, function model, binding và binder.
2. Phân biệt Kafka binder, Rabbit binder và các tích hợp managed cloud theo provider.
3. Chọn binder theo broker protocol, ordering, throughput, replay, transaction và vận hành.
4. Cấu hình destination, consumer group, content type, partition và nhiều binder.
5. Nhận biết khác biệt offset, acknowledgment, checkpoint, redelivery và DLQ.
6. Thiết kế retry, idempotency, schema evolution và transactional outbox.
7. Dùng workload identity, least privilege và quản lý secret cho binder.
8. Kiểm thử bằng Test Binder, Testcontainers, emulator và cloud staging.
9. Quan sát consumer lag, backlog, throughput, retry và lỗi theo từng broker.

> **Phạm vi:** Spring Cloud Stream cung cấp programming model và binder abstraction. Binder có thể do Spring Cloud Stream, Spring Cloud Azure hoặc dự án tích hợp khác cung cấp; mức hỗ trợ phụ thuộc release. Không mặc định mọi dịch vụ AWS/Azure/GCP đều có binder chính thức, được duy trì hoặc có semantics tương đương Kafka/RabbitMQ.

## 2. Spring Cloud Stream và vai trò của binder

### 2.1. Các thành phần trong kiến trúc

Spring Cloud Stream đặt một lớp binding giữa function của ứng dụng và middleware:

~~~mermaid
flowchart LR
    A["Application function"] --> B["Input / output binding"]
    B --> C["Spring Cloud Stream"]
    C --> D["Binder implementation"]
    D --> E["Broker destination"]
    E --> D
    D --> C
    C --> B
    B --> A
~~~

Các thành phần chính:

- **Function:** logic nhận, biến đổi hoặc tạo message, thường là `Supplier`, `Function` hoặc `Consumer`.
- **Binding:** liên kết input/output của function với một destination.
- **Destination:** topic, queue, stream hoặc subscription trên broker.
- **Binder:** adapter kết nối binding tới broker, tạo/đọc destination, cấu hình consumer/producer và chuyển đổi message theo khả năng binder.
- **Binder configuration:** thông tin broker, credential, client properties và environment của từng binder.

Ứng dụng khai báo function và binding theo tên logic. Binder thực hiện phần transport cụ thể. Khi dùng Kafka binder, destination thường ánh xạ tới Kafka topic; với Rabbit binder, destination có thể ánh xạ tới exchange/queue và binding; với binder khác, destination có thể là stream, topic/subscription hoặc entity tương ứng.

### 2.2. Function-based programming model

Spring Cloud Stream dùng Spring Cloud Function để phát hiện function bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.util.function.Function;

@Configuration
public class ReservationFunctions {

    @Bean
    Function<ReservationCreated, ReservationAccepted> acceptReservation() {
        return event -> new ReservationAccepted(
                event.eventId(),
                event.reservationId(),
                "ACCEPTED");
    }
}
~~~

Function trên nhận một payload kiểu `ReservationCreated` và trả về `ReservationAccepted`. Binder liên kết input/output của function với destination đã cấu hình. Function không cần biết broker là Kafka hay RabbitMQ.

Các dạng function phổ biến:

| Dạng | Vai trò | Ví dụ |
| --- | --- | --- |
| `Supplier<T>` | Tạo message đầu ra | Poll/đọc dữ liệu và phát event |
| `Function<T, R>` | Nhận và biến đổi message | Validate/enrich rồi phát event mới |
| `Consumer<T>` | Nhận và xử lý message, không phát output | Gọi application service |
| `Function<Flux<T>, Flux<R>>` | Xử lý reactive stream khi binder hỗ trợ | Biến đổi luồng liên tục |

Không chọn reactive function chỉ để tăng tốc. Phải xem binder, client và downstream có hỗ trợ reactive end-to-end hay không; một đoạn blocking call trong pipeline vẫn chiếm thread và làm giảm lợi ích.

### 2.3. Binding name và convention

Với function tên `acceptReservation`, binding name mặc định theo convention:

- `acceptReservation-in-0`: input đầu tiên.
- `acceptReservation-out-0`: output đầu tiên.

Function có nhiều input/output sẽ có index tương ứng. Có thể đặt tên binding tường minh bằng property `spring.cloud.stream.function.bindings`, nhưng cần cân nhắc việc đổi convention làm cấu hình khó theo dõi hơn.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptReservation
    stream:
      bindings:
        acceptReservation-in-0:
          destination: reservation-created
          group: reservation-processor
          content-type: application/json
        acceptReservation-out-0:
          destination: reservation-accepted
          content-type: application/json
~~~

Ở đây `reservation-created` và `reservation-accepted` là tên destination logic. Broker cụ thể sẽ tạo hoặc sử dụng tài nguyên tương ứng theo binder và cấu hình provisioning.

### 2.4. Binding không phải business contract

Binding name và destination là cấu hình triển khai. Business event contract nên được định nghĩa độc lập: event type, schema version, event ID, timestamp, producer, correlation ID và payload. Tránh để tên topic, tên Java class hoặc package nội bộ trở thành contract duy nhất giữa các team.

Nếu một service có nhiều function, khai báo rõ function được bật bằng `spring.cloud.function.definition`. Không phụ thuộc vào việc framework tự phát hiện tất cả bean vì một ứng dụng có thể vô tình kích hoạt function không dự kiến hoặc tạo binding không mong muốn.

## 3. Chọn binder từ workload và broker protocol

### 3.1. Bắt đầu bằng protocol đang được vận hành

Binder không phải lựa chọn độc lập với broker. Hãy xác định broker/service đã được chọn hoặc yêu cầu kiến trúc trước, rồi tìm binder phù hợp:

| Broker hoặc dịch vụ | Hướng tích hợp thường gặp | Điểm cần xác minh |
| --- | --- | --- |
| Apache Kafka / Amazon MSK / managed Kafka | Spring Cloud Stream Kafka binder | Kafka protocol, SASL/TLS, offset, partition, transaction và IAM/OAuth mechanism |
| RabbitMQ / Amazon MQ for RabbitMQ | Spring Cloud Stream Rabbit binder | Exchange, queue, routing key, acknowledgment, prefetch, DLX |
| Azure Event Hubs | Spring Cloud Azure Stream binder hoặc Kafka binder qua Kafka endpoint | Binder version, partition/checkpoint, consumer group, authentication và giới hạn protocol |
| Google Cloud Pub/Sub | Spring Cloud GCP Pub/Sub integration hoặc binder tương thích được duy trì | Ack deadline, subscription, ordering key, retry/DLQ; xác minh binder có thực sự phù hợp |
| Amazon Kinesis Data Streams | Kinesis-specific integration/binder nếu tương thích; nếu không dùng AWSpring/SDK adapter | Shard, sequence number, checkpoint, iterator age, resharding |
| Amazon SQS/SNS/EventBridge | AWSpring, Spring Integration hoặc SDK adapter phù hợp | Queue visibility/ack, topic fan-out, event rule/PutEvents; không giả định có một binder chung |
| Google Managed Service for Apache Kafka | Kafka binder | Kafka API compatibility, auth, networking và quota |
| Azure Event Hubs Kafka endpoint | Kafka binder nếu tính năng cần dùng tương thích | Không phải mọi tính năng Kafka đều được Event Hubs hỗ trợ |

Điểm quan trọng là phân biệt **managed Kafka** với **managed messaging service**. MSK và Event Hubs Kafka endpoint cung cấp Kafka protocol ở những mức hỗ trợ nhất định; SQS, Pub/Sub và Kinesis có mô hình API/semantics riêng. Một Kafka binder không thể tự động giao tiếp với bất kỳ queue/topic nào chỉ vì tên gọi có chữ event.

### 3.2. Khi nào chọn Kafka binder?

Kafka binder thường phù hợp khi workload cần:

- Topic partition để scale consumer và giữ ordering trong partition.
- Consumer group và offset để theo dõi tiến độ.
- Retention và replay event theo offset.
- Throughput cao, stream event liên tục.
- Log-based event processing hoặc tích hợp với Kafka ecosystem.
- Kafka transactions hoặc idempotent producer khi yêu cầu phù hợp.

Cần xác minh partition strategy, key, replication, retention, consumer lag, rebalance behavior, transaction support và cách cấp quyền. Kafka binder có thể kết nối managed Kafka nhưng authentication/networking là đặc thù từng dịch vụ.

### 3.3. Khi nào chọn Rabbit binder?

Rabbit binder thường phù hợp khi workload cần:

- Routing qua exchange và routing key.
- Queue độc lập cho từng consumer group.
- Competing consumers và acknowledgment.
- Dead-letter exchange/queue.
- Message TTL, priority hoặc delayed delivery khi broker/plugin hỗ trợ.
- Request/reply hoặc task queue theo mô hình AMQP.

RabbitMQ không phải Kafka log. Queue và message thường được tiêu thụ rồi loại bỏ theo acknowledgment; replay không giống việc đọc lại Kafka offset. Nếu cần fan-out, exchange type, durable queue, quorum queue, prefetch và DLX phải được thiết kế rõ.

### 3.4. Khi nào dùng binder của managed cloud?

Dùng binder provider-specific khi nó được duy trì cho phiên bản Spring Boot/Cloud hiện tại và cung cấp đúng capability của dịch vụ. Ví dụ Azure Event Hubs có integration Spring Cloud Azure; Google Cloud có Spring integrations cho Pub/Sub; AWS có các integration cho SQS, SNS, Kinesis và EventBridge. Nhưng sự tồn tại của Spring integration không đồng nghĩa mọi dịch vụ đều có Spring Cloud Stream binder tương ứng.

Trước khi chọn, kiểm tra:

1. Binder có nằm trong release train tương thích với Spring Boot và Spring Cloud hiện tại không?
2. Có hỗ trợ đúng authentication/workload identity không?
3. Có hỗ trợ manual acknowledgment/checkpoint, batch, ordering và DLQ cần thiết không?
4. Có tài liệu migration, issue tracker và hoạt động bảo trì không?
5. Có thể test local/CI và quan sát production behavior không?
6. Có hỗ trợ các giới hạn/quota của managed service không?

Nếu binder không đáp ứng semantics cần thiết, dùng provider integration trực tiếp trong adapter/application boundary. Không ép một dịch vụ vào abstraction không phù hợp.

### 3.5. Ma trận quyết định thực tế

| Nhu cầu chính | Ưu tiên xem xét | Cần chấp nhận |
| --- | --- | --- |
| Event log, replay, partition ordering | Kafka binder | Quản trị partition, offset, retention và rebalance |
| Work queue, routing, DLX | Rabbit binder | Exchange/queue topology và ack semantics |
| Azure-native event ingestion | Event Hubs binder hoặc Kafka endpoint | Checkpoint/partition và khác biệt so với Kafka đầy đủ |
| Google-native publish/subscribe | Pub/Sub integration/binder tương thích | Ack deadline, subscription và provider IAM |
| AWS queue command | SQS integration/adapter | Visibility timeout, delete/ack và redelivery |
| AWS event routing | EventBridge adapter/SDK | Event bus/rule/PutEvents partial failure |
| AWS ordered stream | Kinesis integration/adapter | Shard/checkpoint/sequence semantics |

## 4. Cấu hình binding cơ bản

### 4.1. Consumer binding

Một consumer nhận event và gọi application service:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BillingFunctions {

    @Bean
    Consumer<ReservationAccepted> createBillingIntent(
            BillingApplicationService service) {
        return event -> service.createIntent(event);
    }
}
~~~

Cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: createBillingIntent
    stream:
      bindings:
        createBillingIntent-in-0:
          destination: reservation-accepted
          group: billing-service
          content-type: application/json
~~~

`group` định danh nhóm consumer có chia sẻ tiến độ/queue theo semantics binder. Nhiều instance của cùng group thường chia tải. Consumer không có group có thể được xử lý như anonymous/ephemeral subscription tùy binder; không dùng anonymous group cho xử lý nghiệp vụ cần tiếp tục nhận event sau restart.

### 4.2. Producer binding

Function producer có thể nhận input nội bộ và phát output, hoặc dùng Supplier để tạo message:

~~~java
import java.time.Instant;
import java.util.function.Supplier;

@Bean
Supplier<ReservationHeartbeat> reservationHeartbeat() {
    return () -> new ReservationHeartbeat(
            "reservation-service", Instant.now());
}
~~~

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: reservationHeartbeat
    stream:
      bindings:
        reservationHeartbeat-out-0:
          destination: reservation-heartbeat
          content-type: application/json
  integration:
    poller:
      fixed-delay: 5000
~~~

Supplier được poll theo cấu hình poller khi dùng cơ chế polling. Không dùng Supplier polling để thay thế event source chuyên dụng nếu nguồn có cursor/checkpoint, rate limit hoặc yêu cầu không bỏ sót dữ liệu. Khi phát event từ business transaction, transactional outbox thường đáng tin cậy hơn việc poll một Supplier đọc trạng thái trong memory.

### 4.3. Function có input và output

~~~java
@Bean
Function<ReservationCreated, ReservationAccepted> acceptReservation() {
    return event -> new ReservationAccepted(
            event.eventId(),
            event.reservationId(),
            "ACCEPTED");
}
~~~

Khai báo cả hai binding:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptReservation
    stream:
      bindings:
        acceptReservation-in-0:
          destination: reservation-created
          group: reservation-acceptor
          content-type: application/json
        acceptReservation-out-0:
          destination: reservation-accepted
          content-type: application/json
~~~

Function đồng bộ trả một output cho mỗi input. Nếu xử lý lỗi trước khi return, lỗi đi vào cơ chế error handling của binder/container. Nếu function trả null hoặc bỏ output theo semantics framework, hãy định nghĩa rõ đó là message bị lọc có chủ đích hay lỗi nghiệp vụ.

### 4.4. Chaining functions

Spring Cloud Stream có thể compose nhiều function trong cùng application:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeReservation|validateReservation|enrichReservation
~~~

Composition giúp chia bước transform thành function nhỏ. Tuy nhiên, composition nội bộ không tạo durable boundary giữa các bước. Nếu process crash giữa pipeline, broker thường chỉ biết trạng thái message đầu vào theo ack/transaction của binding; không có checkpoint độc lập cho từng function. Tách thành destination/service riêng khi cần scale, retry, ownership hoặc replay độc lập.

## 5. Destination, group và lifecycle

### 5.1. Destination là tài nguyên broker

Tên `destination` là tên logic được binder ánh xạ. Với Kafka, destination thường là topic; với Rabbit binder, destination có thể được ánh xạ thành exchange và queue theo group; với Pub/Sub, topic và subscription là hai tài nguyên riêng; với Event Hubs, destination liên quan event hub và consumer group. Đừng giả định destination luôn là một queue có thể xóa message.

Quyền provisioning cần tách khỏi quyền runtime nếu môi trường production yêu cầu quản trị tập trung. Có thể tạo topic/queue/subscription bằng IaC và cấu hình binder không tự provision hoặc chỉ kiểm tra resource đã tồn tại, tùy binder.

### 5.2. Consumer group và fan-out

Consumer group xác định consumer nào cùng chia sẻ message progress:

- Hai instance cùng group thường chia nhau partition/message theo binder.
- Hai group khác nhau thường nhận bản sao logic của cùng stream/destination nếu broker hỗ trợ pub/sub fan-out.
- Rabbit binder có thể tạo queue riêng theo group để mỗi group nhận bản sao message từ exchange.
- Pub/Sub subscription riêng là một đơn vị delivery/ack độc lập.

Nếu cần một event kích hoạt billing, analytics và notification độc lập, mỗi consumer service cần group/subscription riêng. Không triển khai ba chức năng trong cùng group nếu mong muốn mỗi chức năng đều nhận đủ event.

### 5.3. Group ổn định qua deployment

Group name là một phần của state vận hành. Đổi group có thể tạo consumer group mới, nhận lại dữ liệu theo offset/retention hoặc tạo subscription/queue mới. Không đưa build number, pod ID hoặc môi trường ngẫu nhiên vào group name của consumer nghiệp vụ. Dùng tên ổn định theo service/use case và tách môi trường bằng cluster/namespace hoặc prefix được quản lý.

### 5.4. Auto provisioning và cleanup

Provisioning tự động tiện cho local development nhưng production nên có ownership rõ:

- Ai tạo topic/queue/subscription?
- Partition count hoặc retention được đặt bằng IaC hay binder?
- Có policy chống xóa nhầm destination không?
- Khi xóa binding/group, resource broker có bị xóa theo không?
- Naming convention có phân biệt dev/test/staging/prod?
- Role của application có quyền create/delete resource hay chỉ produce/consume?

Không cấp quyền admin broker cho application runtime chỉ để binder tự tạo mọi resource nếu tổ chức đã có quy trình IaC.

## 6. Partitioning, ordering và concurrency

### 6.1. Partitioning giải quyết vấn đề gì?

Partitioning chia destination thành nhiều phần để consumer xử lý song song. Với Kafka, message được ghi vào một partition; ordering được giữ trong phạm vi partition. Consumer group phân công partition cho các consumer instance. Nếu số consumer vượt số partition, một số consumer sẽ không nhận partition nào.

Với Event Hubs, partition cũng là đơn vị phân phối và checkpoint. Với Kinesis, shard là đơn vị lưu trữ/đọc có sequence number. Với RabbitMQ, ordering phụ thuộc queue, publisher, consumer concurrency, prefetch và requeue. Không suy ra mọi broker có cùng partition model.

### 6.2. Chọn partition key

Nếu cần giữ thứ tự cho một reservation, dùng reservation ID làm key. Nếu cần giữ thứ tự theo tenant, dùng tenant ID. Key nên có cardinality và phân bố hợp lý; một key quá nóng có thể tạo hot partition và giới hạn throughput.

Ví dụ cấu hình partitioning ở mức Spring Cloud Stream:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        reservation-out-0:
          destination: reservation-events
          producer:
            partition-key-expression: headers['partitionKey']
            partition-count: 12
~~~

Producer cần gửi header key:

~~~java
Message<ReservationEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader("partitionKey", event.reservationId())
        .build();
~~~

Tên property và cách tính partition phụ thuộc binder/version; với Kafka binder, Kafka key và partitioner của producer có thể là cấu hình phù hợp hơn. Khi dùng binder native partitioning, xác minh cách binder map `partition-key-expression` thành broker key và cách partition count được provision.

### 6.3. Consumer concurrency

Concurrency điều khiển số consumer thread/container xử lý cùng binding. Kafka binder có thể gán partition cho consumer trong cùng group; số thread thực tế bị giới hạn bởi partition assignment. Rabbit binder có thể tạo nhiều consumer trên queue; tăng concurrency làm tăng số message in-flight và có thể ảnh hưởng ordering.

Không đặt concurrency bằng số CPU một cách máy móc. Tính theo:

- Số partition/shard hoặc broker consumer limit.
- Thời gian xử lý message và latency dependency.
- Database connection pool và downstream rate limit.
- Thứ tự nghiệp vụ theo key.
- Lock/visibility/ack deadline và thời gian gia hạn.
- CPU, memory và executor capacity.

Concurrency tăng quá mức có thể gây database pool exhaustion, throttling, lock expiry và duplicate processing. Tăng consumer chỉ hiệu quả nếu broker có partition/queue capacity và downstream còn khả năng nhận tải.

### 6.4. Partition count là quyết định dài hạn

Tăng partition có thể thay đổi mapping key-to-partition và làm ảnh hưởng ordering theo thời gian. Với Kafka, tăng partition count thường không tự phân phối lại dữ liệu cũ và có thể thay đổi partition cho key theo hash. Hãy xác định partition count từ throughput, consumer parallelism, retention và tăng trưởng dự kiến; không dùng số partition tùy tiện chỉ để có nhiều consumer.

### 6.5. Ordering và parallelism có đánh đổi

Muốn ordering theo aggregate, mọi event của aggregate đó phải đi cùng partition key/session key/ordering key và được xử lý theo đúng thứ tự. Có thể xử lý nhiều aggregate song song, nhưng không nên xử lý đồng thời hai event cùng aggregate nếu logic yêu cầu tuần tự. Khi retry một event cũ trong khi event mới đã đi tiếp, cần chính sách pause partition, sequence check hoặc version check ở application layer.

## 7. Binder-specific configuration

### 7.1. Cấu hình chung và cấu hình riêng

Spring Cloud Stream có các property chung cho binding như destination, group, content type, consumer concurrency và producer partitioning. Mỗi binder cũng có namespace riêng cho broker connection và tính năng riêng.

Khi dùng Kafka hoặc Rabbit binder, dependency tương ứng thường là:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-kafka</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-rabbit</artifactId>
</dependency>
~~~

Trong một ứng dụng dùng cả hai binder, thêm cả hai starter và cấu hình từng binder riêng. Quản lý version qua Spring Cloud BOM tương thích với Spring Boot; không tự nâng một binder độc lập khỏi release train.

Ví dụ cấu trúc Kafka binder:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafka
      bindings:
        acceptReservation-in-0:
          destination: reservation-created
          group: reservation-processor
          consumer:
            concurrency: 3
        acceptReservation-out-0:
          destination: reservation-accepted
      kafka:
        binder:
          brokers: broker-1.example:9092,broker-2.example:9092
          auto-create-topics: false
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
~~~

Ví dụ trên minh họa cấu trúc property, không phải cấu hình credential đầy đủ. Username/password hoặc token phải được inject qua secret manager/environment an toàn; không commit vào YAML. Broker-specific property có thể thay đổi theo Kafka client version và binder version.

### 7.2. Kafka consumer group và offset

Kafka binder dùng consumer group để chia partition và lưu offset. Cấu hình binding group phải ổn định. Khi một message được xử lý thành công, offset commit theo container/binder acknowledgment mode; nếu process dừng trước commit, message có thể được đọc lại.

Các câu hỏi cần trả lời:

- Offset commit tự động hay do acknowledgment mode điều khiển?
- Commit theo từng record hay batch?
- Handler lỗi có seek/retry record hay gửi DLQ?
- Rebalance có thể xảy ra khi xử lý lâu không?
- Consumer có thể vượt `max.poll.interval.ms` không?
- Có cần pause partition trong thời gian dependency outage?

Không cấu hình Kafka client property mà không hiểu tác động tới binder/container. Ví dụ tăng `max.poll.interval.ms` có thể giảm rebalance do xử lý chậm nhưng cũng kéo dài thời gian phát hiện consumer bị treo.

### 7.3. Rabbit binder và topology

Rabbit binder có thể ánh xạ destination thành exchange và consumer group thành queue. Cấu hình có thể bao gồm durable, auto-bind-DLQ, dead-letter exchange, prefetch và acknowledgment mode. Một số property là binder-specific, không dùng chung với Kafka.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        createBillingIntent-in-0:
          destination: reservation-events
          group: billing-service
      rabbit:
        bindings:
          createBillingIntent-in-0:
            consumer:
              acknowledge-mode: AUTO
              prefetch: 20
              auto-bind-dlq: true
~~~

Đây là ví dụ minh họa. Kiểm tra đúng property name/enum theo version Spring Cloud Stream Rabbit binder đang dùng. DLQ có thể yêu cầu exchange/queue và policy phù hợp; auto-bind-DLQ không thay thế việc thiết kế quyền, retention, alert và quy trình replay.

### 7.4. Nhiều binder trong một ứng dụng

Một ứng dụng có thể dùng nhiều binder, ví dụ Kafka cho event stream và Rabbit cho work queue. Định nghĩa binder configuration theo tên và chỉ định binder cho binding:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafka-east:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-a.example:9092
        rabbit-work:
          type: rabbit
          environment:
            spring:
              rabbitmq:
                addresses: amqps://rabbit.example:5671
      bindings:
        reservation-events-out-0:
          destination: reservation-events
          binder: kafka-east
        billing-work-in-0:
          destination: billing-work
          group: billing-worker
          binder: rabbit-work
~~~

Cấu trúc `environment` cô lập cấu hình cho từng binder; property thực tế cần điều chỉnh theo binder/version. Không chia sẻ cùng một secret hoặc credential giữa các binder nếu identity của broker khác nhau. Khi dùng nhiều binder, xác định rõ function nào nối với binding nào và tránh vô tình tạo hai kết nối tới cùng broker.

### 7.5. Cấu hình riêng cho AWS, Azure và Google Cloud

**AWS Managed Streaming for Apache Kafka (MSK):** nếu dùng Kafka binder, ứng dụng kết nối bằng Kafka protocol. Cấu hình broker bootstrap, TLS và SASL mechanism theo phương thức auth được chọn (ví dụ IAM authentication hoặc SCRAM). Với IAM auth, cần thư viện callback/login module tương ứng và workload role có quyền cluster/topic/group phù hợp. Không đặt static access key trong `sasl.jaas.config`; ưu tiên role/credential provider trên runtime.

**AWS Kinesis Data Streams:** Kinesis không phải Kafka. Dùng Kinesis-specific integration/binder nếu release tương thích và hỗ trợ checkpoint/consumer mode cần thiết; nếu không, dùng AWSpring/SDK adapter trong boundary. Phải hiểu shard, sequence number, iterator age, checkpoint và resharding. Không map `partition` của Kafka sang shard Kinesis rồi giả định semantics giống nhau.

**AWS SQS/SNS/EventBridge:** đây là các service có API và semantics riêng. Dùng AWSpring/SDK/Spring Integration adapter phù hợp. SQS có visibility timeout/delete, SNS có fan-out/subscription, EventBridge có event bus/rule và kết quả từng entry của PutEvents. Không xem chúng là một Kafka binder chỉ vì đều vận chuyển event.

**Azure Event Hubs:** có thể dùng Spring Cloud Azure Stream binder hoặc Kafka binder thông qua Kafka endpoint tùy yêu cầu và version. Native binder có thể expose semantics của Event Hubs; Kafka endpoint cho phép tái sử dụng Kafka client ở phạm vi tương thích. Cần kiểm tra partition ownership, checkpoint storage, consumer group, SAS/Managed Identity và tính năng Kafka chưa được hỗ trợ.

**Google Cloud Pub/Sub:** Spring Cloud GCP cung cấp tích hợp Pub/Sub cho Spring; việc có binder Spring Cloud Stream phù hợp phải được xác minh theo release và nguồn bảo trì cụ thể. Nếu dùng Pub/Sub native integration, thiết kế subscription, ack deadline, lease extension, ordering key, retry và dead-letter topic theo Pub/Sub. Nếu dùng Managed Service for Apache Kafka thì Kafka binder kết nối qua Kafka protocol, nhưng đó là một broker khác với Pub/Sub.

### 7.6. Không cấu hình một abstraction rồi bỏ qua native feature

Khi binder cung cấp một property chung, vẫn phải kiểm tra nó map sang broker feature nào. Ví dụ retry có thể là retry trong process, broker redelivery hoặc consumer container retry. DLQ có thể là Kafka topic, Rabbit DLX, Pub/Sub dead-letter topic hoặc queue riêng do adapter tạo. Một tên property giống nhau không đảm bảo retention, ordering, poison-message behavior hoặc replay giống nhau.
## 8. Delivery semantics và acknowledgment

### 8.1. At-most-once, at-least-once và effectively-once

- **At-most-once:** message có thể mất nhưng không được xử lý lặp theo semantics đã chọn.
- **At-least-once:** message được redeliver cho tới khi ack/commit thành công; consumer phải chấp nhận duplicate.
- **Effectively-once:** side effect nghiệp vụ được bảo vệ bằng idempotency/deduplication dù transport có thể redeliver.
- **Exactly-once:** thuật ngữ này chỉ có ý nghĩa trong một phạm vi transaction cụ thể; không tự động bao trùm DB, broker và API bên ngoài.

Không tuyên bố toàn hệ thống exactly-once chỉ vì Kafka idempotent producer hoặc transaction được bật. Side effect ngoài transaction boundary vẫn có thể lặp.

### 8.2. Kafka offset commit

Kafka consumer đọc record theo offset. Offset biểu thị vị trí consumer group đã xử lý/commit trong partition. Nếu commit trước khi side effect bền vững, process crash có thể làm mất xử lý. Nếu commit sau khi side effect bền vững nhưng commit thất bại, record có thể được đọc lại.

Với xử lý database, pattern phổ biến là transaction DB + inbox/deduplication, rồi commit offset sau khi DB commit. Kafka transaction có thể atomically ghi output topic và commit consumed offsets trong phạm vi Kafka transaction khi binder/container hỗ trợ; nó không tự bao gồm database transaction thông thường.

### 8.3. Rabbit acknowledgment

RabbitMQ consumer nhận delivery và ack sau xử lý. Ack thủ công cho phép xác nhận sau khi side effect hoàn tất; nack/reject có thể requeue hoặc dead-letter tùy cấu hình. Auto ack có thể khiến message bị coi là hoàn tất ngay khi broker gửi tới consumer, nên rủi ro mất message tăng nếu process crash trong lúc xử lý.

Prefetch giới hạn số message chưa ack được gửi tới consumer. Prefetch quá lớn tăng in-flight memory và có thể làm các consumer khác thiếu việc; quá nhỏ có thể giảm throughput. Khi xử lý lâu, cân nhắc timeout, consumer capacity và redelivery behavior.

### 8.4. Event Hubs và Kinesis checkpoint

Event Hubs/Kinesis thường theo mô hình stream partition/shard và checkpoint tiến độ đọc. Checkpoint quá sớm có thể bỏ qua record khi xử lý thất bại; checkpoint sau xử lý có thể dẫn tới duplicate nếu crash trước khi checkpoint được ghi. Checkpoint store và partition ownership có thể dùng storage riêng; identity cần quyền trên cả stream lẫn checkpoint store.

### 8.5. Pub/Sub acknowledgment deadline

Pub/Sub subscription có ack deadline; consumer phải ack hoặc gia hạn lease khi xử lý kéo dài. Nếu deadline hết hạn trước ack, message có thể được giao lại. Dead-letter policy và retry policy được cấu hình ở subscription. Ordering key có thể hạn chế song song theo key và có điều kiện vùng/region. Đừng xem ack deadline như Kafka offset hay Rabbit ack; chúng có lifecycle khác.

### 8.6. Bảng đối chiếu semantics

| Broker | Tiến độ xử lý | Hoàn tất message | Duplicate thường gặp khi |
| --- | --- | --- | --- |
| Kafka | Offset theo consumer group/partition | Commit offset | Side effect xong nhưng offset chưa commit |
| RabbitMQ | Delivery state/queue | Ack delivery | Ack thất bại hoặc consumer connection đóng |
| Azure Event Hubs | Checkpoint theo partition | Persist checkpoint | Xử lý xong nhưng checkpoint chưa ghi |
| Google Pub/Sub | Subscription delivery state | Ack trước deadline | Ack mất hoặc deadline hết |
| AWS SQS | Visibility/receipt handle | Delete message | Delete thất bại hoặc visibility timeout hết |
| AWS Kinesis | Sequence/checkpoint theo shard | Persist checkpoint | Record đã xử lý nhưng checkpoint chưa ghi |

### 8.7. Vì sao binder không thể chuẩn hóa mọi acknowledgment

Spring Cloud Stream có thể cung cấp error handling và acknowledgment API chung cho một số binder, nhưng transport adapter vẫn phải tuân thủ lifecycle broker. Một binder có thể hỗ trợ manual ack; binder khác có thể chỉ commit offset theo container policy hoặc checkpoint theo batch. Kiểm tra tài liệu binder trước khi thiết kế use case cần ack thủ công, batch failure hoặc partial retry.

Nếu function chỉ trả về bình thường, không tự suy ra mọi broker đã ghi nhận side effect bền vững. Xác minh thời điểm binder commit offset/ack so với transaction application. Nếu adapter không cho phép kiểm soát lifecycle cần thiết, cân nhắc native integration cho boundary đó.

## 9. Retry, dead-letter và poison message

### 9.1. Phân biệt retry trong process và broker redelivery

Retry có thể xảy ra ở nhiều tầng:

1. SDK retry request tới broker/API.
2. Binder/container retry handler trong cùng process.
3. Broker redeliver message sau nack, timeout, lock expiry hoặc offset behavior.
4. Application outbox worker retry publish.
5. Consumer inbox ngăn side effect lặp.

Nếu mọi tầng cùng retry ba lần, một message có thể tạo nhiều request hơn dự kiến. Thiết kế một policy tổng thể, chỉ rõ tầng nào chịu trách nhiệm với từng lỗi.

### 9.2. Phân loại lỗi trước khi retry

| Lỗi | Hành động thường phù hợp |
| --- | --- |
| JSON/schema không hợp lệ | Quarantine/DLQ; retry không làm payload hợp lệ |
| Authorization/permission denied | Dừng retry nhanh, alert và sửa IAM/role |
| Throttling/rate limit | Backoff có jitter, tôn trọng retry-after nếu có |
| Network timeout/service unavailable | Retry có giới hạn nếu thao tác an toàn |
| Database deadlock/transient failure | Rollback transaction rồi retry theo policy |
| Business rejection | Xử lý như kết quả nghiệp vụ, không nhất thiết là transport error |
| Bug lập trình | Alert, giữ stack trace và đưa message vào điều tra |

Không retry tất cả exception. Retry lỗi vĩnh viễn tạo poison-message loop, tăng chi phí và làm queue backlog.

### 9.3. Retry và recovery ở Spring Cloud Stream

Các binding có thể cấu hình retry/recovery theo property chung hoặc binder-specific. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        createBillingIntent-in-0:
          consumer:
            max-attempts: 3
~~~

Property trên minh họa số lần xử lý ở tầng consumer theo phiên bản/framework. Backoff, exception classification và recovery/DLQ cần cấu hình bổ sung theo version binder. Không dùng số lần thử mặc định như một SLA; tổng thời gian retry phải nằm trong visibility timeout, lock duration, ack deadline hoặc consumer poll constraints của broker.

Nếu binder hỗ trợ DLQ, cấu hình DLQ ở đúng binding và xác minh resource thực tế được tạo. Nếu không, dùng error handler/adapter riêng để chuyển message sang quarantine. Không tự tạo DLQ bằng cách chỉ log exception rồi ack message.

### 9.4. Kafka binder DLQ

Kafka binder có thể hỗ trợ dead-letter topic cho consumer binding khi cấu hình phù hợp. Cần xác định:

- DLQ name và partition count.
- Record key, original topic/partition/offset và exception metadata có được giữ không.
- Lỗi serialization xảy ra trước khi function nhận payload có đi vào error path mong muốn không.
- Retry có seek/retry cùng partition hay chuyển sang DLQ.
- Ai có quyền đọc/replay DLQ và cách tránh replay storm.

DLQ topic cũng cần retention, alert, quota, encryption và runbook. Consumer group mới để replay có thể đọc nhiều dữ liệu hơn dự kiến nếu offset policy không được kiểm soát.

### 9.5. Rabbit binder DLX/DLQ

Rabbit binder thường dựa vào dead-letter exchange và queue topology. Cần xác định queue nào bind vào DLX, routing key nào dùng cho dead-letter, message TTL và policy requeue. `requeue=true` có thể tạo vòng lặp nhanh khi message luôn thất bại. Với lỗi permanent, dead-letter/quarantine thường hợp lý hơn requeue.

Nếu dùng quorum queue hoặc delayed message plugin, kiểm tra tính năng có sẵn trên broker managed và version. Không giả định plugin của RabbitMQ community được bật trên mọi managed Rabbit service.

### 9.6. Cloud-native DLQ

- **SQS:** redrive policy chuyển message vượt max receive count sang DLQ; source và DLQ cần cùng Region/account theo ràng buộc dịch vụ. Visibility timeout phải đủ cho xử lý và retry.
- **Pub/Sub:** dead-letter topic gắn với subscription; service agent cần quyền publish/subscribe phù hợp và max delivery attempts phải được xác minh.
- **Event Hubs/Kinesis:** thường dùng checkpoint/retry và error storage/application dead-letter pattern; không đồng nhất với queue DLQ.
- **EventBridge:** target retry policy và DLQ được cấu hình ở rule/target; PutEvents producer có thể nhận lỗi từng entry, cần xử lý partial failure ở producer.

DLQ không phải nơi lưu trữ vô thời hạn. Đặt retention, encryption, quyền truy cập, alert theo oldest message age và quy trình xử lý/ẩn dữ liệu nhạy cảm.

### 9.7. Replay có kiểm soát

Quy trình replay cần:

1. Xác định nguyên nhân và sửa code/config trước.
2. Kiểm tra schema version và khả năng tương thích consumer.
3. Chọn subset message theo thời gian, event type hoặc ID.
4. Giới hạn tốc độ replay để không gây overload downstream.
5. Giữ event ID gốc để idempotency hoạt động.
6. Ghi audit ai yêu cầu replay, số message và kết quả.
7. Theo dõi backlog, duplicate và DLQ sau replay.

Không sửa payload gốc trong DLQ một cách không kiểm soát. Nếu cần chuyển đổi message cũ sang schema mới, dùng migration/replay tool có version và audit.
## 10. Idempotency, transactions và consistency

### 10.1. Consumer inbox

Managed broker thường hỗ trợ at-least-once trong các cấu hình phổ biến. Consumer có thể nhận lại message khi process crash sau side effect nhưng trước ack/offset commit, ack response thất lạc hoặc visibility/lock/ack deadline hết hạn. Dùng event ID ổn định do producer tạo để deduplicate:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(120) NOT NULL,
    event_id      VARCHAR(120) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer insert inbox record trong cùng DB transaction với side effect:

~~~java
@Transactional
public void handle(ReservationAccepted event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(
            "billing-service", event.eventId());

    if (!firstDelivery) {
        return;
    }

    billingRepository.createIntent(event.reservationId());
}
~~~

`insertIfAbsent` phải dựa trên unique constraint; tránh check-then-insert bằng hai query tách rời. Ack/commit message sau khi transaction DB commit. Nếu ack thất bại sau commit, message có thể redeliver nhưng inbox ngăn side effect chạy lần hai.

Nếu side effect gọi API ngoài database transaction, inbox không bảo vệ được API call đó. Truyền idempotency key tới API đích hoặc ghi command vào outbox để worker riêng thực hiện.

### 10.2. Transaction của Kafka và giới hạn của exactly-once

Kafka có idempotent producer và transaction cho phép phối hợp ghi nhiều topic và commit consumed offsets trong phạm vi Kafka. Kafka binder có thể expose transaction capability tùy cấu hình/version. Nhưng transaction Kafka không bao trùm database, S3, payment API hoặc service khác.

Ví dụ: consumer đọc event, ghi DB rồi publish Kafka output. Nếu DB commit thành công nhưng Kafka transaction abort, DB và Kafka không còn cùng trạng thái. Cần outbox/inbox hoặc thiết kế saga để quản lý consistency giữa các resource độc lập.

### 10.3. Rabbit và cloud broker transaction

RabbitMQ publisher confirms xác nhận broker đã nhận publish theo semantics cấu hình; consumer ack xác nhận delivery đã được xử lý. Hai thao tác này không tự tạo atomic transaction với database. Event Hubs/Kinesis checkpoint và Pub/Sub ack cũng không tham gia transaction DB thông thường.

Đừng dùng từ exactly-once nếu chỉ có broker deduplication hoặc transaction nội bộ. Mô tả chính xác phạm vi: producer deduplication, broker transaction, consumer offset commit, DB transaction hay application idempotency.

### 10.4. Transactional outbox

Khi business transaction cần phát event, ghi event vào outbox trong cùng transaction với thay đổi domain:

~~~sql
CREATE TABLE outbox_event (
    event_id      VARCHAR(120) PRIMARY KEY,
    aggregate_id  VARCHAR(120) NOT NULL,
    event_type    VARCHAR(160) NOT NULL,
    payload       JSONB NOT NULL,
    occurred_at   TIMESTAMPTZ NOT NULL,
    published_at  TIMESTAMPTZ NULL,
    attempts      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_outbox_unpublished
    ON outbox_event (occurred_at)
    WHERE published_at IS NULL;
~~~

DDL dùng JSONB/TIMESTAMPTZ và partial index của PostgreSQL; database khác cần điều chỉnh kiểu dữ liệu/cú pháp.

Application service:

~~~java
@Transactional
public void acceptReservation(String reservationId) {
    Reservation reservation = reservationRepository.accept(reservationId);
    ReservationAccepted event = eventFactory.from(reservation);

    outboxRepository.insert(
            event.eventId(),
            reservation.id(),
            "ReservationAccepted",
            serialize(event),
            event.occurredAt());
}
~~~

Outbox publisher đọc record chưa publish, gửi qua Spring Cloud Stream output binding rồi cập nhật `published_at` sau khi broker xác nhận. Dùng lease hoặc `FOR UPDATE SKIP LOCKED` để nhiều worker claim record an toàn; không giữ row lock trong lúc chờ network call.

Nếu worker crash sau khi publish nhưng trước khi cập nhật `published_at`, event có thể được gửi lại. Consumer inbox xử lý duplicate. Outbox bảo đảm ý định publish được lưu bền vững cùng transaction DB; nó không tự bảo đảm exactly-once delivery.

### 10.5. Chọn outbox publisher

Có thể dùng polling worker, CDC connector hoặc transaction log tailing tùy quy mô:

| Cách | Ưu điểm | Trade-off |
| --- | --- | --- |
| Polling outbox | Dễ triển khai, dễ kiểm soát | Poll query, lock contention và độ trễ theo chu kỳ |
| CDC/log-based | Độ trễ thấp, ít polling | Thêm connector, schema/offset operation và vận hành |
| Framework outbox integration | Có thể giảm code lặp | Phụ thuộc database, connector, version và topology |

Không publish trực tiếp từ entity listener hoặc callback trước khi transaction commit nếu chưa xử lý crash window. Worker cần metric cho oldest unpublished event, retry count và backlog.

## 11. Serialization, content type và schema evolution

### 11.1. Content type

Spring Cloud Stream có thể chuyển đổi payload dựa trên content type. Ví dụ binding JSON:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        acceptReservation-in-0:
          content-type: application/json
~~~

Nếu producer gửi JSON nhưng consumer mong đợi Avro/Protobuf hoặc byte array, cần thống nhất serializer/deserializer và schema contract. Không dựa vào Java native serialization cho message liên hệ thống vì nó gắn chặt class/version và có rủi ro bảo mật.

### 11.2. Envelope ổn định

Một event envelope nên có:

~~~json
{
  "eventId": "evt-01J...",
  "eventType": "ReservationAccepted",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T10:00:00Z",
  "producer": "reservation-service",
  "correlationId": "corr-...",
  "tenantId": "tenant-a",
  "data": {
    "reservationId": "res-1001"
  }
}
~~~

Consumer validate event type/version trước khi xử lý payload. Không dùng class name hoặc package Java làm schema contract. Có thể dùng JSON Schema, Avro hoặc Protobuf và registry tương thích với broker/platform.

### 11.3. Backward/forward compatibility

- **Backward-compatible:** consumer mới đọc được event cũ.
- **Forward-compatible:** consumer cũ có thể bỏ qua hoặc xử lý an toàn field mới của producer.
- **Breaking change:** đổi type, meaning, requiredness hoặc cấu trúc khiến consumer hiện tại không parse/hiểu đúng.

Ưu tiên thêm optional field có default, không đổi ý nghĩa field hiện có và rollout consumer trước producer khi cần. Với breaking change, tạo event type/version mới hoặc thực hiện migration có kế hoạch. Giữ schema compatibility policy trong CI để phát hiện thay đổi không an toàn.

### 11.4. Kafka key và Rabbit routing metadata

Kafka key ảnh hưởng partition và ordering; Rabbit routing key/exchange quyết định route tới queue. Đây là transport metadata, không thay thế event payload. Nếu application phụ thuộc vào broker key/routing key, ghi rõ trong contract adapter và test mapping. Không đưa tenant ID chưa xác thực vào key/routing metadata để quyết định authorization.

### 11.5. Payload lớn và object reference

Message broker thường có giới hạn kích thước payload và tối ưu cho metadata/event nhỏ. Với file lớn, lưu object trên S3/Blob/GCS rồi phát locator cùng checksum, content type, size và version/generation. Consumer cần workload identity và allow-list để tải object. Locator không phải quyền truy cập; tránh gửi presigned URL/SAS token có thể lọt vào log hoặc DLQ.

## 12. Security và identity cho binder

### 12.1. Workload identity

Ưu tiên identity gắn với workload:

- AWS: IAM role cho ECS task, EKS Pod Identity/IRSA hoặc EC2 instance profile.
- Azure: Managed Identity hoặc Workload Identity.
- Google Cloud: Workload Identity hoặc Application Default Credentials trong môi trường phù hợp.

Credential provider cần lấy token/key theo runtime và refresh khi hết hạn. Không hard-code access key, service principal secret, service account key hoặc connection string trong source/YAML commit Git.

### 12.2. Least privilege theo producer/consumer

Producer chỉ cần quyền publish vào destination cần thiết. Consumer chỉ cần quyền consume/subscribe/ack vào destination của mình. Quyền provisioning topic/queue nên tách khỏi runtime identity nếu IaC chịu trách nhiệm tạo tài nguyên.

Ví dụ phân quyền:

| Role | Quyền tối thiểu theo use case |
| --- | --- |
| Kafka producer | Write vào topic cụ thể; quyền cluster phù hợp với auth model |
| Kafka consumer | Read topic và consumer group cụ thể |
| Rabbit producer | Write vào exchange cần thiết |
| Rabbit consumer | Read queue và ack/reject delivery |
| Pub/Sub publisher | Publish vào topic cụ thể |
| Pub/Sub subscriber | Consume subscription cụ thể |
| SQS consumer | Receive/delete/change visibility trên queue |
| EventBridge publisher | PutEvents vào event bus cụ thể |

Tên permission thực tế phụ thuộc IAM/RBAC policy và broker. Không cấp quyền admin hoặc wildcard toàn account chỉ để binder khởi động được.

### 12.3. TLS, SASL và secret

Bật TLS cho broker connection; xác minh truststore/hostname và certificate rotation. Với Kafka, SASL mechanism có thể là SCRAM, OAuth hoặc cơ chế IAM của managed service. Với Rabbit, dùng TLS và credential/vhost permission. Với Azure/GCP native binder, ưu tiên token credential/workload identity.

Secret phải được cấp qua secret manager hoặc secret injection của runtime. Không log config object, SASL JAAS string, token hoặc connection string. Xoay secret cần có overlap window nếu broker/client hỗ trợ; xác minh client refresh/reconnect behavior.

### 12.4. Multi-tenant và message header

Không tin tenant ID do producer bên ngoài tự ghi vào header. Xác thực identity và tenant mapping ở ingress boundary, sau đó gắn tenant context đã xác thực. Nếu cần isolation mạnh, cân nhắc destination riêng hoặc broker ACL theo tenant; nếu dùng shared topic, enforce authorization trong application và phân vùng key/group phù hợp.

Không đưa token, PII, payment data hoặc presigned URL vào header. Header có thể được copy sang broker, tracing, log hoặc DLQ.
## 13. Kiểm thử binder và message flow

### 13.1. Unit test function

Function là Java bean nên có thể test độc lập, không cần Spring context hoặc broker:

~~~java
@Test
void mapsReservationToAcceptedEvent() {
    ReservationAccepted result = acceptReservation.apply(
            new ReservationCreated("evt-1", "res-1001"));

    assertThat(result.reservationId()).isEqualTo("res-1001");
    assertThat(result.status()).isEqualTo("ACCEPTED");
}
~~~

Unit test tập trung vào mapping, validation và business service. Không dùng unit test function để kết luận binder đã commit offset, ack message hoặc provision destination.

### 13.2. Spring Cloud Stream Test Binder

Test Binder cung cấp binding trong memory để test application integration mà không kết nối broker thật. Dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ví dụ test function input/output:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(properties = {
        "spring.cloud.function.definition=acceptReservation",
        "spring.cloud.stream.bindings.acceptReservation-in-0.destination=reservation-created",
        "spring.cloud.stream.bindings.acceptReservation-out-0.destination=reservation-accepted"
})
@Import(TestChannelBinderConfiguration.class)
class ReservationStreamTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void publishesAcceptedEvent() {
        ReservationCreated event =
                new ReservationCreated("evt-1", "res-1001");

        input.send(MessageBuilder.withPayload(event).build(),
                "reservation-created");

        Message<byte[]> result =
                output.receive(1000, "reservation-accepted");

        assertThat(result).isNotNull();
    }
}
~~~

Test Binder kiểm tra wiring và flow ở mức application. Nó không mô phỏng đầy đủ Kafka rebalance/offset, Rabbit prefetch/ack, Pub/Sub lease extension, Event Hubs checkpoint hoặc cloud IAM. Đừng dùng kết quả Test Binder thay cho contract test với broker thật.

### 13.3. Testcontainers và broker thật trong CI

Dùng Testcontainers hoặc môi trường ephemeral để kiểm tra binder với Kafka/RabbitMQ thực tế:

- Provision topic/queue và group.
- Gửi message, nhận output và xác minh payload/header.
- Restart consumer để kiểm tra offset/ack/redelivery.
- Kiểm tra partition assignment, key ordering và concurrency.
- Kiểm tra DLQ, retry, serialization failure và poison message.
- Xác minh TLS/auth khi test environment hỗ trợ.

Testcontainers giúp kiểm tra broker protocol thực nhưng không mô phỏng managed service IAM, quota, networking, encryption key policy hay mọi cloud-specific behavior.

### 13.4. Cloud staging contract test

Staging nên xác minh workload identity, resource policy, TLS, destination provisioning, ack/checkpoint, retry, DLQ, ordering và observability. Dùng resource test riêng, payload không nhạy cảm, quota/retention giới hạn và cleanup có kiểm soát.

Với AWS MSK, kiểm tra bootstrap brokers, IAM/SCRAM, topic ACL và consumer group. Với Event Hubs, kiểm tra Managed Identity/SAS, consumer group và checkpoint store. Với Pub/Sub, kiểm tra service account/workload identity, subscription, ack deadline, ordering và dead-letter topic. Với SQS/Kinesis, kiểm tra role, visibility/checkpoint, redrive và iterator age.

## 14. Observability và vận hành binder

### 14.1. Theo dõi từ application tới broker

Một message nên mang event ID, correlation ID và trace context xuyên qua producer, broker, consumer và side effect. Theo dõi các mốc:

1. Producer tạo event và gửi vào binding.
2. Binder gửi thành công hoặc nhận publish error.
3. Broker lưu/route message.
4. Consumer nhận message và bắt đầu xử lý.
5. Application commit side effect.
6. Binder ack/commit offset/checkpoint.
7. Nếu lỗi, retry hoặc dead-letter.

Micrometer Observation/metrics có thể instrument function/binding theo version. Propagate trace context qua broker header theo chuẩn tracing đang dùng. Không tự log toàn bộ payload/header vì có thể chứa dữ liệu nhạy cảm.

### 14.2. Metric quan trọng

| Metric | Dùng để phát hiện |
| --- | --- |
| Producer send rate/error rate | Producer chậm, broker reject hoặc throttling |
| Consumer throughput | Năng lực xử lý thực tế |
| Consumer lag / oldest message age | Consumer không theo kịp backlog |
| Partition/shard assignment | Mất cân bằng hoặc partition nóng |
| Offset/checkpoint progress | Consumer không commit tiến độ |
| In-flight/unacked count | Handler chậm hoặc ack bị kẹt |
| Retry/redelivery count | Dependency lỗi hoặc policy không phù hợp |
| DLQ depth/oldest age | Poison message hoặc lỗi chưa xử lý |
| Rebalance/reconnect count | Consumer instability hoặc network/auth issue |
| Serialization failure | Schema drift hoặc content type sai |

Metric cần gắn với binding, group, destination và broker nhưng tránh label cardinality cao từ event ID hoặc tenant ID tùy ý.

### 14.3. Runbook cho sự cố

**Consumer lag tăng:** xác định partition nóng, handler latency, downstream bottleneck và rebalance. Scale consumer chỉ khi có partition/shard và DB capacity; nếu downstream đang throttling, giảm concurrency hoặc pause receive.

**Authentication failure:** kiểm tra workload identity, token expiry, role/ACL và trust configuration. Không xử lý bằng cách cấp quyền admin rộng.

**DLQ tăng:** phân loại schema, permission, throttling và business rejection; sửa nguyên nhân rồi replay có giới hạn.

**Rebalance liên tục:** kiểm tra xử lý lâu, poll interval, heartbeat, network và max in-flight. Tránh tăng timeout mà không xác định nguyên nhân handler bị treo.

**Broker outage:** quyết định producer buffer/persist, retry window, circuit breaker và cách resume. Không giữ vô hạn message trong heap hoặc thread chờ.

### 14.4. Capacity và cost

Broker managed tính phí theo throughput, partition/throughput unit, request, storage, retention hoặc data transfer tùy dịch vụ. Consumer retry, metadata lookup, poll quá dày và payload lớn đều làm tăng cost. Thiết kế batch, compression, retention, partition/shard count và concurrency theo số liệu load test; theo dõi oldest message age cùng throughput để biết scale có cải thiện thực sự không.

## 15. Các lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Đổi binder nhưng behavior khác | Broker có semantics ack/ordering/partition khác | So sánh contract và viết provider-specific test |
| Consumer nhận duplicate | Offset/ack/checkpoint chưa commit hoặc timeout | Inbox/idempotency và điều chỉnh lifecycle |
| Message mất | Commit/ack trước khi side effect bền vững | Commit sau DB transaction hoặc persist trước ack |
| Consumer group không nhận event | Group mới, topic/partition/ACL sai hoặc binding không active | Kiểm tra group, destination, assignment và quyền |
| Throughput thấp dù tăng instance | Số partition ít hoặc downstream bottleneck | Điều chỉnh partition/capacity và profiling |
| Rabbit queue backlog tăng | Consumer chậm, prefetch/ack hoặc DLX loop | Kiểm tra unacked, concurrency và requeue policy |
| Kafka rebalance liên tục | Poll interval, xử lý lâu, heartbeat hoặc network | Đo handler duration và điều chỉnh container/client có căn cứ |
| Pub/Sub redelivery liên tục | Ack deadline hết hoặc lỗi ack | Gia hạn lease, giảm xử lý hoặc tăng capacity |
| Event Hubs/Kinesis lặp lại sau restart | Checkpoint chưa được ghi | Idempotency và kiểm tra checkpoint store |
| DLQ không có message dù handler lỗi | Lỗi xảy ra ngoài error path hoặc binder không bật DLQ | Xác minh error handler và broker DLQ policy |
| Message parse lỗi | Content type/serializer/schema không khớp | Contract test và version compatibility |
| Secret xuất hiện trong log | In ra config/header/exception chứa credential | Mask log, secret injection và rotation |

## 16. Quy trình chọn binder và migration

Khi chuyển broker hoặc binder, không bắt đầu bằng việc đổi property destination. Thực hiện theo trình tự:

1. Ghi lại contract hiện tại: schema, key, ordering, group, delivery, retention, retry, DLQ và replay.
2. Chọn broker/binder đích dựa trên workload và feature cần giữ.
3. Lập bảng mapping semantics: offset ↔ checkpoint, ack ↔ delete/complete, partition ↔ shard/session.
4. Xác minh các feature không có mapping tương đương và quyết định thay đổi application contract.
5. Tạo adapter/config riêng theo environment và identity.
6. Chạy Test Binder, Testcontainers và cloud staging contract tests.
7. Chạy dual publish/dual consume nếu cần migration, có event ID để deduplicate.
8. Theo dõi lag, duplicate, DLQ, ordering và cost trước khi cutover.
9. Dừng consumer cũ theo offset/checkpoint strategy đã thống nhất; lưu khả năng rollback.
10. Gỡ destination/credential cũ sau thời gian retention và kiểm chứng dữ liệu.

Không dual consume cùng một business event trên hai broker nếu side effect không idempotent. Nếu dual publish, event ID phải giống nhau ở cả hai đích và consumer phải deduplicate xuyên migration.

## 17. Checklist trước production

1. **Binder choice:** binder được duy trì và tương thích Spring Boot/Cloud release đang dùng.
2. **Broker semantics:** đã ghi rõ offset, ack, checkpoint, redelivery, ordering và retention.
3. **Bindings:** function definition, binding name, destination và group ổn định.
4. **Provisioning:** topic/queue/partition/group do IaC hay binder quản lý được xác định.
5. **Partitioning:** key, partition count, concurrency và hot-key risk được đánh giá.
6. **Delivery:** ack/commit xảy ra sau side effect bền vững; duplicate được xử lý.
7. **Retry/DLQ:** lỗi permanent/transient, retry budget, DLQ và replay runbook rõ ràng.
8. **Consistency:** outbox/inbox dùng cho dual-write và side effect cần idempotency.
9. **Schema:** content type, serializer, versioning và compatibility được kiểm tra.
10. **Security:** workload identity, TLS và least privilege; secret không nằm trong source/log.
11. **Testing:** Test Binder, broker integration test và cloud staging contract test.
12. **Operations:** lag, backlog, retry, DLQ, rebalance/checkpoint và cost có metric/alert.

## 18. Bài tập tự luyện

1. Viết một Consumer function nhận ReservationAccepted và một Function phát ReservationBilled; cấu hình input/output binding.
2. So sánh Kafka binder và Rabbit binder về destination, consumer group, partition, ordering, acknowledgment và replay.
3. Cấu hình nhiều binder cho Kafka và Rabbit; chỉ định binder riêng cho từng binding.
4. Chọn giữa Kafka binder và Event Hubs binder cho workload ingest event; nêu tính năng cần kiểm chứng.
5. Giải thích vì sao SQS, SNS, EventBridge, Kinesis và Pub/Sub không tự động tương đương với Kafka binder.
6. Thiết kế partition key theo reservation ID; phân tích hot key và tác động khi tăng partition count.
7. Mô phỏng crash sau DB commit nhưng trước offset/ack; dùng inbox để bảo vệ side effect.
8. Thêm transactional outbox và worker publish qua output binding; mô phỏng crash sau publish.
9. Cấu hình retry/DLQ cho lỗi throttling, permission và schema; giải thích lỗi nào không nên retry.
10. Lập contract test cho MSK, Event Hubs hoặc Pub/Sub: workload identity, ack/checkpoint, ordering, DLQ và metric.
11. Lập kế hoạch migration Kafka sang một managed broker khác; ghi rõ semantics không thể map trực tiếp.
12. Dùng Test Binder và Testcontainers để phân biệt test application function với test broker behavior.

**Tiêu chí hoàn thành:** người học chọn được binder phù hợp với workload và broker protocol, cấu hình được function/binding/group/partition, giải thích chính xác khác biệt offset/ack/checkpoint giữa các provider, thiết kế retry/DLQ/idempotency/outbox, và có test chứng minh các semantics cần thiết.

## Tài liệu tham khảo

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/): programming model, bindings, binders, consumer groups và partitioning.
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/): Kafka binder configuration và semantics.
- [Spring Cloud Stream — Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html): Rabbit binder và topology.
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-testing.html): Test Binder và message destinations.
- [Spring Cloud Azure — Event Hubs Binder](https://learn.microsoft.com/azure/developer/java/spring-framework/spring-cloud-stream-support): tích hợp Event Hubs với Spring Cloud Stream.
- [Spring Cloud GCP — Pub/Sub](https://googlecloudplatform.github.io/spring-cloud-gcp/): Spring integration với Google Cloud Pub/Sub.
- [AWS Spring — Spring Cloud AWS](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): tích hợp Spring với SQS, SNS và các dịch vụ AWS.
- [Amazon MSK — IAM authentication](https://docs.aws.amazon.com/msk/latest/developerguide/iam-authentication.html): xác thực Kafka client với IAM.
- [Azure Event Hubs — Kafka protocol](https://learn.microsoft.com/azure/event-hubs/azure-event-hubs-kafka-overview): khả năng tương thích Kafka và giới hạn.
- [Google Cloud Pub/Sub — Subscription overview](https://cloud.google.com/pubsub/docs/subscription-overview): acknowledgment, retry và subscription semantics.
- [AWS Prescriptive Guidance — Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html): dual-write và duplicate delivery.

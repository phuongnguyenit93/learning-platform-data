# Đánh giá binder đối tác như Azure Event Hubs, Pub/Sub và Solace

Spring Cloud Stream cung cấp mô hình lập trình thống nhất bằng Supplier, Function, Consumer và binding. Binder kết nối các binding đó với hệ thống messaging cụ thể. Vì vậy, có thể giữ phần lớn logic nghiệp vụ khi đổi middleware, nhưng không thể giả định mọi broker có cùng semantics về partition, consumer group, checkpoint, acknowledgement, retry, schema hay replay.

Azure Event Hubs, Google Cloud Pub/Sub và Solace PubSub+ đều có Spring Cloud Stream binder được liệt kê trong nhóm partner-maintained. Điều đó có nghĩa binder do nhà cung cấp hoặc đối tác duy trì, với lịch phát hành, ma trận tương thích và kênh hỗ trợ riêng. Khi đánh giá, cần xem cả dịch vụ messaging, binder, phiên bản Spring Boot/Spring Cloud và cách vận hành trong production.

Bài học này so sánh ba binder theo mô hình dữ liệu, cách ánh xạ binding, delivery semantics, partitioning, lỗi và khả năng vận hành. Cuối bài có ví dụ một ứng dụng dùng nhiều binder cùng lúc và một checklist để chọn giải pháp.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vị trí của binder đối tác trong hệ sinh thái Spring Cloud Stream.
- Phân biệt Event Hubs partitioned log, Pub/Sub topic/subscription và Solace topic/queue.
- Đánh giá consumer group, checkpoint, acknowledgement, ordering và partitioning.
- Chọn cách kết nối Azure Event Hubs qua binder riêng hoặc Kafka endpoint.
- Đánh giá các giới hạn của Google Pub/Sub binder về partitioning và exactly-once.
- Hiểu cách Solace ánh xạ consumer group thành durable queue và cách dùng partitioned queue.
- Cấu hình nhiều binder trong một ứng dụng Spring Cloud Stream.
- Lập kế hoạch kiểm thử và vận hành trước khi đưa binder đối tác vào production.

## 1. Binder đối tác trong Spring Cloud Stream

Spring Cloud Stream định nghĩa Binder SPI để kết nối ứng dụng với middleware. Ứng dụng khai báo function và binding; binder tạo producer/consumer, ánh xạ destination và chuyển message qua client của broker.

Spring Cloud Stream liệt kê các binder cốt lõi như RabbitMQ, Apache Kafka, Kafka Streams và Apache Pulsar. Azure Event Hubs, Google Pub/Sub và Solace PubSub+ được liệt kê là partner-maintained. Trước khi chọn một binder, hãy xác minh:

1. Ai duy trì mã nguồn và phát hành binder.
2. Binder đang hỗ trợ phiên bản Spring Cloud Stream, Spring Boot và Java nào.
3. Các tính năng broker có được binder expose hay không.
4. Những property nào là property chung của Spring Cloud Stream và property nào chỉ có ở binder.
5. Quy trình nâng cấp, hỗ trợ bảo mật, issue tracker và lịch phát hành.

Nhãn partner-maintained không có nghĩa binder không dùng được. Nó nhắc người triển khai phải xác minh ma trận tương thích và trách nhiệm hỗ trợ theo từng nhà cung cấp.

### Mô hình tích hợp của ba binder

| Binder | Thành phần tích hợp chính | Mô hình broker | Hợp với |
|---|---|---|---|
| Azure Event Hubs | Spring Integration Event Hubs Channel Adapters | Namespace, event hub và partitioned log | Thu nhận telemetry, event streaming và pipeline dữ liệu trên Azure |
| Google Cloud Pub/Sub | Spring Integration Pub/Sub Channel Adapters | Topic và subscription | Pub/sub phân tán, fan-out theo subscription và tích hợp dịch vụ Google Cloud |
| Solace PubSub+ | Solace Java API/JCSMP và Spring Cloud Stream Binder | Topic, durable queue, topic subscription và message VPN | Event mesh, routing theo topic và giao nhận tin cậy qua queue |

Cả ba có thể nhận function binding, nhưng các khái niệm phía sau không đồng nhất. Ví dụ, consumer group của Event Hubs gắn với checkpoint và quyền sở hữu partition; group của Pub/Sub được ánh xạ thành subscription; group của Solace được ánh xạ thành durable queue.

## 2. So sánh nhanh theo semantics

| Tiêu chí | Azure Event Hubs | Google Cloud Pub/Sub | Solace PubSub+ |
|---|---|---|---|
| Mô hình chính | Event log có partition | Topic và subscription | Topic kết hợp queue |
| Đơn vị consumer group | Consumer group | Subscription | Durable queue của group |
| Tiến độ consumer | Checkpoint theo partition, thường lưu trong Azure Blob Storage | Ack và ack deadline trên subscription | Broker acknowledgement trên queue |
| Phân phối song song | Partition ownership và lease | Subscriber clients, ordering key không phải partition | Nhiều consumer trên queue; broker phân phối theo access mode |
| Ordering | Trong một partition | Theo ordering key nếu bật và publish cùng region | Theo semantics queue/partitioned queue và cấu hình broker |
| Partition abstraction của Spring Cloud Stream | Binder hỗ trợ partition vật lý của Event Hubs | Binder hiện không hỗ trợ partitioning | Abstraction partitioning của Spring Cloud Stream không được hỗ trợ; broker có partitioned queue riêng |
| Retry/DLQ | Retry/checkpoint theo Event Processor và ứng dụng; thiết kế poison-event riêng | Redelivery, retry policy và dead-letter topic | Redelivery, error queue và Dead Message Queue |
| Exactly-once | Không suy ra từ checkpoint; kiểm tra tính idempotent và đường Kafka transaction riêng | Dịch vụ hỗ trợ exactly-once cho pull subscription; binder có giới hạn API acknowledgement | Có broker transaction/ack semantics riêng; không đồng nhất với exactly-once end-to-end |
| Tài nguyên phụ trợ | Azure Storage cho checkpoint và lease | Topic, subscription, IAM và quota | Message VPN, topic, queue, ACL và spool |

Bảng này là bản đồ khái niệm. Cấu hình cụ thể vẫn phải được xác minh theo phiên bản binder và tier dịch vụ.

## 3. Azure Event Hubs Binder

Azure Event Hubs là dịch vụ thu nhận và lưu giữ event theo partition. Một namespace chứa nhiều event hub; event hub tương ứng với topic trong cách nhìn của Kafka. Consumer đọc từ partition theo offset và xử lý dữ liệu trong thời gian retention.

### Cách binder hoạt động

Spring Cloud Azure Event Hubs Binder dựa trên Spring Integration Event Hubs Channel Adapters. Binder nhận destination từ binding và kết nối với Event Hubs SDK. Đây là tích hợp riêng cho Event Hubs, không phải Kafka binder đổi địa chỉ broker.

Các khái niệm chính:

- Namespace: vùng endpoint và capacity của Event Hubs.
- Event hub: stream chứa các event.
- Partition: log vật lý độc lập trong event hub.
- Consumer group: góc nhìn đọc độc lập của một ứng dụng.
- Checkpoint: vị trí consumer đã xử lý tới trong một partition.
- Checkpoint store: nơi lưu checkpoint và thông tin lease để điều phối partition ownership.

Event Hubs không lưu offset consumer theo cách giống Kafka broker. Event Processor sử dụng checkpoint store, thường là Azure Blob Storage, để lưu tiến độ theo partition. Storage lease cũng được dùng để xác định consumer nào đang sở hữu partition.

### Checkpoint và partition ownership

Khi consumer instance mới tham gia, Event Processor sử dụng lease trong Storage để phân phối partition. Một instance có thể nhận thêm partition từ instance đang sở hữu nhiều partition hơn. Cơ chế này khác với việc giả định Kafka group coordinator sẽ thực hiện toàn bộ rebalance và offset management trong broker.

Binder hỗ trợ batch consumer. Khi bật batch mode, function nhận danh sách event thay vì từng event riêng lẻ. Checkpoint có thể được thực hiện theo hai cách:

- BATCH: binder checkpoint cả batch theo cơ chế tự động sau khi batch được nhận.
- MANUAL: ứng dụng dùng Checkpointer được truyền qua message header để checkpoint theo quyết định nghiệp vụ.

Với MANUAL, chỉ checkpoint sau khi xử lý bền vững. Nếu checkpoint trước khi ghi database hoặc gọi hệ thống đích thành công, ứng dụng có thể bỏ qua event sau sự cố. Nếu xử lý thành công nhưng checkpoint chưa được lưu, event có thể được đọc lại; consumer phải idempotent.

### Dependency và cấu hình

Có thể dùng starter:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-stream-eventhubs</artifactId>
</dependency>
~~~

Hoặc dùng artifact binder trực tiếp nếu dự án quản lý dependency theo cách riêng:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-stream-binder-eventhubs</artifactId>
</dependency>
~~~

Ví dụ cấu hình một consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: consumeTelemetry
    stream:
      bindings:
        consumeTelemetry-in-0:
          destination: telemetry
          group: telemetry-processor
      azure:
        eventhubs:
          connection-string: AZURE_EVENTHUB_NAMESPACE_CONNECTION
          processor:
            checkpoint-store:
              account-name: CHECKPOINT_STORAGE_ACCOUNT
              container-name: eventhub-checkpoints
~~~

Các giá trị trên là placeholder để minh họa cấu trúc. Không commit connection string, Storage key hoặc secret vào repository. Trong production, ưu tiên Microsoft Entra ID và managed identity nếu hạ tầng hỗ trợ; cấp quyền tối thiểu cho Event Hubs và Storage checkpoint container.

Binder có các property theo binding dưới prefix:

~~~text
spring.cloud.stream.eventhubs.bindings.<binding-name>.consumer.*
~~~

Ví dụ có thể cấu hình checkpoint mode/count/interval, batch size, batch wait time và load-balancing strategy. Hãy tra bảng property của đúng phiên bản Spring Cloud Azure đang dùng; không nhầm prefix này với property của Kafka binder.

### Event Hubs qua Kafka endpoint

Event Hubs cung cấp Kafka-compatible endpoint. Một ứng dụng Kafka có thể kết nối qua Kafka protocol bằng cách thay bootstrap server, port và SASL configuration. Đây là một lựa chọn khác với Event Hubs Binder.

Chọn Kafka binder với Kafka endpoint khi:
- Ứng dụng đã phụ thuộc sâu vào Kafka client API.
- Muốn tái sử dụng Kafka producer/consumer configuration và tooling tương thích.
- Các tính năng Kafka mà ứng dụng dùng nằm trong tập Event Hubs hỗ trợ.

Chọn Event Hubs Binder khi:
- Muốn tích hợp trực tiếp với Azure Event Hubs SDK.
- Cần checkpoint store và partition ownership theo cơ chế Event Processor.
- Muốn dùng batch consumer và Checkpointer của binder.
- Ứng dụng cần theo dõi Azure-specific properties.

Kafka compatibility không có nghĩa Event Hubs là một Kafka cluster đầy đủ. Event Hubs dùng namespace làm endpoint và không expose mọi Kafka broker behavior. Tài liệu Azure hiện đánh dấu Kafka Streams và Kafka transactions ở trạng thái public preview trên Premium và Dedicated; Kafka compression cũng chỉ được hỗ trợ ở hai tier này, với gzip là loại được nêu trong tài liệu. Hãy kiểm tra tier và ma trận tính năng trước khi bật.

### Rủi ro cần kiểm tra

- Checkpoint store không truy cập được khiến tiến độ xử lý hoặc partition ownership gặp vấn đề.
- Storage lease và Event Hubs partition assignment cần được quan sát khi scale/restart.
- Số partition giới hạn mức song song hữu ích của consumer trong cùng consumer group.
- Batch checkpoint có thể xác nhận cả batch; nếu một phần batch chưa được xử lý bền vững, cần thiết kế lại ranh giới commit.
- Event Hubs retention và checkpoint là hai khái niệm khác nhau: checkpoint không giữ event lâu hơn retention.
- Kafka API compatibility có giới hạn theo tier và feature; kiểm thử các API thực tế mà ứng dụng dùng.

## 4. Google Cloud Pub/Sub Binder

Google Cloud Pub/Sub là dịch vụ messaging quản lý theo topic và subscription. Publisher gửi message tới topic; mỗi subscription có backlog và tiến độ acknowledgement riêng. Nhiều subscription trên cùng topic tạo fan-out độc lập: mỗi subscription nhận bản sao logic của luồng message.

### Cách binder hoạt động

Spring Framework on Google Cloud cung cấp Spring Cloud Stream Binder cho Pub/Sub. Binder dựa trên Spring Integration Channel Adapters.

Ánh xạ phổ biến:

- Binding destination phía producer là Pub/Sub topic.
- Binding destination phía consumer là topic; binder kết nối với subscription.
- Consumer group được dùng để tạo tên subscription theo topic và group.
- Không khai báo group thường tạo anonymous subscription; subscription này có thể được binder dọn khi ứng dụng dừng.
- Có thể chỉ định subscription name đã được tạo sẵn.

Ví dụ group tạo subscription tên theo dạng:

~~~text
<topicName>.<group>
~~~

Một subscription là một luồng giao nhận độc lập. Hai ứng dụng cần fan-out đều nhận toàn bộ message nên dùng hai subscription khác nhau. Các instance của cùng một consumer group chia sẻ một subscription để cùng xử lý backlog.

### Dependency và cấu hình

Artifact binder:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-pubsub-stream-binder</artifactId>
</dependency>
~~~

Dùng Spring Framework on Google Cloud BOM để quản lý phiên bản của binder và các client library. Ma trận tương thích của BOM xác định phiên bản Spring Cloud và Spring Boot được hỗ trợ; không tự chọn một phiên bản binder rời rạc chỉ vì nó mới hơn.

Ví dụ consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
      gcp:
        pubsub:
          bindings:
            processOrder-in-0:
              consumer:
                auto-create-resources: false
                subscription-name: orders-order-processor
~~~

Trong môi trường production, nên tạo topic và subscription bằng quy trình hạ tầng đã được review rồi đặt auto-create-resources=false. Nếu cho binder tự tạo tài nguyên, kiểm soát IAM và quyền tạo subscription/topic của service account.

Google Cloud authentication thường dùng Application Default Credentials (ADC). Trên Google Cloud, ưu tiên service account gắn với workload hoặc Workload Identity Federation. Không lưu JSON private key trong source control. Cần cấp quyền publisher/subscriber đúng resource, tránh dùng role quá rộng chỉ để làm cho ứng dụng khởi động.

### Acknowledgement và delivery

Pub/Sub mặc định cung cấp at-least-once delivery. Subscriber phải ack message trong ack deadline; nếu quá hạn hoặc nack, message có thể được giao lại. Thời gian ack có thể được client library gia hạn khi xử lý lâu.

Binder cung cấp các chế độ ack như AUTO, AUTO_ACK và MANUAL. Cần hiểu chính xác semantics của phiên bản binder đang dùng trước khi chọn:

- AUTO: adapter ack khi xử lý thành công và nack khi xử lý lỗi không được error handler xử lý xong.
- AUTO_ACK: adapter ack khi xử lý thành công; nếu xử lý lỗi, adapter không ack cũng không nack, để ack deadline điều khiển lần giao lại tiếp theo.
- MANUAL: ứng dụng chủ động xác nhận bằng callback/header được binder expose.

Với AUTO, nếu error handler nhận lỗi rồi hoàn tất bình thường, adapter có thể coi flow là thành công và ack message; muốn kích hoạt nack mặc định, lỗi cần được ném lại qua error flow. AUTO_ACK thường dùng khi muốn để ack deadline làm nhịp retry sau lỗi. Với MANUAL, lấy BasicAcknowledgeablePubsubMessage từ header gốc để ack/nack sau khi quyết định nghiệp vụ; vẫn cần idempotency vì lỗi mạng hoặc redelivery có thể tạo lần xử lý lặp.

Pub/Sub hỗ trợ dead-letter topic và retry policy ở cấp subscription. Số lần delivery, ack deadline và dead-letter topic là cấu hình của subscription; đừng nhầm retry RPC của client library với redelivery của message. Retry RPC xử lý lỗi gọi API, còn redelivery xảy ra khi message chưa được ack.

### Ordering và exactly-once

Pub/Sub ordering key không phải partition. Khi bật message ordering cho subscription, message có cùng ordering key và được publish trong cùng region được giao theo thứ tự service nhận chúng. Các key khác nhau không có thứ tự toàn cục. Hot key có thể làm giảm throughput và tạo backlog cho chuỗi message cùng key.

Pub/Sub hỗ trợ exactly-once delivery cho pull subscription trong cùng một region. Push và export subscription không hỗ trợ tính năng này. Tuy nhiên, tài liệu Spring Cloud GCP hiện hành lưu ý thư viện không expose AckReplyConsumerWithResponse, interface cần để sử dụng exactly-once acknowledgement API từ Java client. Vì vậy, không được suy ra rằng bật exactly-once ở subscription sẽ tự động khiến Spring Cloud Stream binder cung cấp đầy đủ semantics đó cho function.

Ngoài ra, binder hiện ghi rõ partitioning của Spring Cloud Stream chưa được hỗ trợ. Nếu ứng dụng phụ thuộc vào partition key, partition count hoặc binder-managed partitioning, hãy thiết kế lại theo ordering key và subscription semantics hoặc chọn middleware khác. Ordering key không tương đương với partition và không tạo một số lượng partition cố định.

### Rủi ro cần kiểm tra

- Tạo subscription anonymous khiến backlog và identity không ổn định khi restart.
- Auto-create resources cần IAM permissions; trong production nên quản lý tài nguyên riêng.
- Ack deadline hết hạn làm message redelivery; kiểm tra thời gian xử lý và flow control.
- Ordering key làm tăng latency và có thể tạo hot key.
- Exactly-once service capability không đồng nghĩa binder expose được API acknowledgement tương ứng.
- Binder không hỗ trợ Spring Cloud Stream partitioning abstraction.
- Google Cloud quotas, region, project ID và service account scope cần được kiểm tra cùng lúc.

## 5. Solace PubSub+ Binder

Solace PubSub+ là event broker hỗ trợ topic routing và guaranteed messaging qua queue. Binder ánh xạ mô hình Spring Cloud Stream sang mô hình topic/queue của Solace.

### Topic, queue và consumer group

Cách ánh xạ cơ bản:

- Producer binding luôn publish tới topic.
- Consumer binding luôn nhận message từ queue.
- Consumer group được ánh xạ thành durable queue.
- Queue của group được đăng ký subscription cho destination topic.
- Khi không khai báo group, binder tạo temporary queue cho anonymous consumer.
- Nếu queue có non-exclusive access, broker phân phối message round-robin giữa các consumer binding trong group.

Vì consumer nhận từ queue, Message VPN cần bật Assured Delivery và client profile cần quyền gửi/nhận guaranteed messages. Nếu chỉ tạo topic nhưng không có queue/subscription phù hợp, consumer group sẽ không nhận được message theo kỳ vọng.

### Dependency và cấu hình

Artifact starter:

~~~xml
<dependency>
    <groupId>com.solace.spring.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-solace</artifactId>
</dependency>
~~~

Ví dụ functional binding:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      bindings:
        uppercase-in-0:
          destination: orders
          group: order-processor
          binder: solace-main
        uppercase-out-0:
          destination: processed/orders
          binder: solace-main
      binders:
        solace-main:
          type: solace
          environment:
            solace:
              java:
                host: tcps://broker.example.net:55443
                msgVpn: production
                clientUsername: app-client
                clientPassword: SOLACE_CLIENT_PASSWORD
~~~

Trong production, dùng TLS và cơ chế quản lý secret phù hợp. Không commit password hoặc truststore password. Kiểm tra Message VPN, ACL profile, queue permissions, spool quota và quyền provision queue/topic subscription.

Binder hỗ trợ các property riêng dưới prefix:

~~~text
spring.cloud.stream.solace.bindings.<binding-name>.consumer.*
spring.cloud.stream.solace.bindings.<binding-name>.producer.*
~~~

Có thể cấu hình endpoint type, durable queue provisioning, queue access type, redelivery, error queue, batch mode, transaction, publisher confirmation, header mapping và dynamic producer destination.

### Broker version và acknowledgement

Với Solace PubSub+ Binder v5.x trở lên, consumer binding yêu cầu PubSub+ Broker 10.2.1 hoặc mới hơn vì binder dùng native message NACK được giới thiệu ở broker version đó. Producer binding của binder v5.x vẫn tương thích broker cũ hơn, nhưng một ứng dụng vừa publish vừa consume cần kiểm tra yêu cầu broker theo consumer.

Binder hỗ trợ manual message acknowledgement qua AcknowledgmentCallback. Tuy nhiên, manual acknowledgement không được hỗ trợ khi consumer bật transacted=true. Error queue republishing cũng không được hỗ trợ với consumer transacted=true. Đây là ràng buộc cần quyết định trước khi chọn transaction strategy.

Phân biệt hai loại queue lỗi:

- Error Queue: binder có thể republish message đã được broker giao thành công nhưng ứng dụng không xử lý được sau khi retry nội bộ cạn.
- Dead Message Queue (DMQ): broker định tuyến message thất bại theo cơ chế broker như TTL hết hạn hoặc vượt quá redelivery count.

Không xem Error Queue và DMQ là một tài nguyên giống nhau. Cấu hình, quyền publish/consume và quy trình replay có thể khác.

### Partitioning của Solace

PubSub+ broker hỗ trợ partitioned queue ở mức native. Tuy nhiên, abstraction partitioning của Spring Cloud Stream không được Solace binder hỗ trợ. Để publish vào partitioned queue, ứng dụng truyền partition key bằng header SolaceBinderHeaders.PARTITION_KEY (tên header trên message là solace_scst_partitionKey). Broker xử lý việc phân phối khi consumer đọc từ partitioned queue.

Vì vậy, không thể lấy cấu hình partitionCount/partitionKeyExpression của một binder khác rồi kỳ vọng Solace binder hiểu giống nhau. Hãy cấu hình partitioned queue trong broker và truyền key theo API/header của Solace binder.

### Redelivery và transaction

Khi message bị NACK để requeue, broker có thể redeliver message và các message tiếp theo đã được client buffer. Việc redelivery có thể tạo duplicate; consumer vẫn cần idempotency. Giới hạn redelivery count và cấu hình error queue/DMQ để tránh poison message lặp vô hạn.

Solace hỗ trợ local transaction cho một số consumer flow. Transaction size và giới hạn broker cần được kiểm tra. Manual ack, error queue republishing và transaction không phải các tính năng có thể ghép tùy ý; hãy thử đúng tổ hợp cấu hình trước khi production rollout.

## 6. Cấu hình nhiều binder trong cùng ứng dụng

Khi nhiều binder implementation có mặt trên classpath, Spring Cloud Stream cần biết binder nào sở hữu từng binding. Mỗi binder cung cấp một tên type trong metadata binder. Một binder configuration có tên riêng, type, environment và defaultCandidate.

Các property chung:

- spring.cloud.stream.bindings.<binding-name>.binder: chọn binder cho binding.
- spring.cloud.stream.binders.<binder-name>.type: tên type được binder cung cấp.
- spring.cloud.stream.binders.<binder-name>.environment: property riêng của binder context.
- spring.cloud.stream.binders.<binder-name>.default-candidate: xác định binder có được chọn làm default candidate hay không.

Không để nhiều binder cùng trở thành lựa chọn mặc định khi ứng dụng cần route rõ ràng. Gán binder cho từng binding quan trọng để cấu hình không phụ thuộc thứ tự classpath.

### Ví dụ: đọc từ Event Hubs, phát sang Solace và Pub/Sub

Giả sử ứng dụng có function nhận đơn hàng từ Event Hubs và phát kết quả sang Solace. Một Supplier độc lập phát audit event sang Pub/Sub.

~~~java
import java.time.Instant;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MultiBinderFunctions {

@Bean
Function<OrderCreated, OrderAccepted> azureToSolace() {
    return order -> new OrderAccepted(order.orderId(), "RECEIVED");
}

@Bean
Supplier<OrderAudit> publishAudit() {
    return () -> new OrderAudit("deployment-check", Instant.now());
}

record OrderCreated(String eventId, String orderId) {}
record OrderAccepted(String eventId, String orderId, String status) {}
record OrderAudit(String eventId, Instant createdAt) {}
}
~~~

Cấu hình minh họa:

~~~yaml
spring:
  cloud:
    function:
      definition: azureToSolace;publishAudit
    gcp:
      project-id: GOOGLE_CLOUD_PROJECT
    stream:
      bindings:
        azureToSolace-in-0:
          binder: eventhubs-main
          destination: incoming-orders
          group: order-bridge
        azureToSolace-out-0:
          binder: solace-main
          destination: enterprise/orders/accepted
        publishAudit-out-0:
          binder: pubsub-main
          destination: order-audit
      binders:
        eventhubs-main:
          type: eventhubs
          environment:
            spring:
              cloud:
                azure:
                  eventhubs:
                    connection-string: AZURE_EVENTHUB_CONNECTION
                    processor:
                      checkpoint-store:
                        account-name: AZURE_STORAGE_ACCOUNT
                        container-name: eventhub-checkpoints
        pubsub-main:
          type: pubsub
        solace-main:
          type: solace
          environment:
            solace:
              java:
                host: tcps://broker.example.net:55443
                msgVpn: production
                clientUsername: app-client
                clientPassword: SOLACE_CLIENT_PASSWORD
~~~

Ví dụ dùng placeholder để mô tả cấu trúc. Thay giá trị kết nối bằng secret hoặc workload identity theo môi trường. Azure checkpoint store cần được cấp quyền truy cập Storage.

Google Pub/Sub binder có lưu ý cấu hình riêng: các property kết nối GCP như project ID và credentials phải được đặt theo cách cấu hình single-binder của Spring Cloud GCP. Tài liệu tích hợp Solace mô tả giới hạn này khi Pub/Sub binder được dùng cùng binder khác; không giả định có thể cô lập mọi GCP property bên trong binder environment như với Azure hoặc Solace. Nếu cần nhiều Pub/Sub binder instance với cấu hình GCP tách biệt, xác minh khả năng của phiên bản binder cụ thể trước khi thiết kế.

Ví dụ này chỉ minh họa một ứng dụng có thể dùng nhiều broker. Nó không tạo transaction phân tán giữa Event Hubs, Solace và Pub/Sub. Nếu function đọc Event Hubs rồi publish sang Solace, có thể xảy ra tình huống publish thành công nhưng checkpoint Event Hubs chưa lưu, dẫn đến function được gọi lại và publish trùng. Dùng event ID ổn định, idempotent consumer, outbox/inbox hoặc cơ chế deduplication phù hợp.

## 7. Đánh giá khả năng thay thế và tính portable

Mô hình function giúp tái sử dụng business logic, nhưng các đặc tính broker không tự chuyển đổi được.

| Thành phần | Có thể dùng chung? | Cần adapter hoặc thiết kế riêng? |
|---|---|---|
| Supplier/Function/Consumer | Thường có | Cần điều chỉnh kiểu payload nếu binder có giới hạn |
| Binding name và destination | Cấu trúc chung | Tên destination có semantics riêng |
| Consumer group | Khái niệm chung | Queue, subscription và Event Hubs consumer group khác nhau |
| Partition key | Không hoàn toàn | Event Hubs partition key, Pub/Sub ordering key, Solace partition key là các khái niệm khác |
| Checkpoint/ack | Không | Azure checkpoint, Pub/Sub ack deadline, Solace broker ack khác nhau |
| Retry và DLQ | Không | Cấu hình và tài nguyên broker riêng |
| Message headers | Không hoàn toàn | Header mapping, reserved header và native metadata khác nhau |
| Schema | Không tự động | Schema registry/metadata và serialization cần được thống nhất |
| Exactly-once | Không | Mỗi dịch vụ và binder có phạm vi bảo đảm riêng |

Một cách thiết kế portable là giữ hợp đồng nghiệp vụ ở payload: eventId, eventType, aggregateId, occurredAt, schemaVersion và payload. Chỉ dùng header cho correlation ID, trace ID, tenant hoặc metadata vận chuyển có thể tái tạo. Khi đổi binder, viết adapter để chuyển metadata đặc thù sang mô hình nội bộ.

Đừng đưa object đặc thù như Checkpointer, Pub/Sub acknowledgement callback hoặc Solace AcknowledgmentCallback vào lớp nghiệp vụ dùng chung. Bao chúng trong adapter ở ranh giới messaging để phần xử lý đơn hàng không phụ thuộc trực tiếp vào vendor API.

## 8. Tiêu chí lựa chọn theo tình huống

### Chọn Azure Event Hubs khi

- Hệ thống chạy chủ yếu trên Azure.
- Nhu cầu chính là ingest và lưu event theo partition.
- Cần consumer group và replay từ offset trong retention.
- Có thể vận hành Azure Blob Storage checkpoint store.
- Batch consumer và checkpoint theo partition phù hợp với workload.
- Kafka endpoint đáp ứng đủ các Kafka API mà ứng dụng cần, hoặc binder riêng đáp ứng tốt hơn.

Không chọn chỉ vì Event Hubs có Kafka endpoint. Hãy kiểm tra tier, Kafka protocol feature matrix, compression, transaction, Kafka Streams preview và API mà ứng dụng thực sự sử dụng.

### Chọn Google Cloud Pub/Sub khi

- Hệ thống cần managed pub/sub và fan-out theo subscription.
- Các consumer độc lập cần backlog và tiến độ riêng.
- Ordering key đáp ứng yêu cầu ordering theo entity.
- Ứng dụng chấp nhận subscription-based delivery thay vì partition-based processing.
- Workload không phụ thuộc Spring Cloud Stream partitioning abstraction.
- IAM, project, region và quota được quản lý trong Google Cloud.

Nếu yêu cầu exactly-once delivery, kiểm tra đồng thời subscription type và khả năng binder expose acknowledgement API. Nếu yêu cầu partition cố định hoặc Kafka-style stream processing, Pub/Sub binder có thể không phù hợp.

### Chọn Solace PubSub+ khi

- Kiến trúc cần event mesh và topic routing.
- Consumer group được mô hình hóa bằng durable queue.
- Cần queue policy, spool, selector, topic subscription và assured delivery.
- Hệ thống cần các broker feature như redelivery, error queue, DMQ, publisher confirmation hoặc queue partitioning.
- Đội vận hành có thể quản lý Message VPN, queue, ACL, spool và broker version.

Kiểm tra broker version tối thiểu cho consumer binder, Assured Delivery, transaction/ack compatibility và giới hạn của Spring Cloud Stream partition abstraction.

## 9. Kiểm thử binder trước khi production

Không dừng ở unit test function. Cần kiểm thử cả binder, broker và tài nguyên ngoài broker.

### Ma trận kiểm thử chung

| Kiểm thử | Câu hỏi cần trả lời |
|---|---|
| Startup | Ứng dụng có tạo binding và kết nối broker đúng không? |
| Authentication | Workload identity/service principal/service account có quyền đúng không? |
| Resource provisioning | Topic, event hub, subscription, queue có được tạo đúng không? |
| Consumer group | Nhiều instance có chia tải đúng và fan-out có đúng không? |
| Partition/order | Key có giữ được thứ tự và phân phối như mong muốn không? |
| Acknowledgement | Ack/checkpoint chỉ xảy ra sau khi xử lý bền vững không? |
| Redelivery | Dừng process giữa xử lý có tạo redelivery như dự kiến không? |
| Retry | Lỗi tạm thời có retry có giới hạn và backoff không? |
| DLQ/error queue | Lỗi vĩnh viễn có được cách ly và có quy trình replay không? |
| Schema/header | Payload và metadata có giữ nguyên hợp đồng không? |
| Restart/rebalance | Instance mới có nhận partition/subscription/queue đúng không? |
| Shutdown | Producer flush, consumer stop và checkpoint có hoàn tất không? |
| Observability | Có metric cho lag, backlog, checkpoint, redelivery và lỗi publish không? |

### Kiểm thử riêng cho Event Hubs

- Tắt quyền Storage checkpoint để xác minh lỗi được phát hiện.
- Restart consumer và quan sát partition lease.
- Gửi batch lớn, làm lỗi một phần batch và kiểm tra checkpoint.
- Scale số consumer lên/xuống và xác minh phân phối partition.
- Nếu dùng Kafka endpoint, chạy test các Kafka API, authentication, compression và transaction thực tế.

### Kiểm thử riêng cho Pub/Sub

- Tạo hai subscription để xác minh fan-out.
- Chạy nhiều instance cùng group để kiểm tra chia tải.
- Hết ack deadline và xác minh redelivery.
- Kiểm tra ordering key cùng region và trường hợp hot key.
- Xác minh dead-letter topic và max delivery attempts.
- Thử exactly-once ở cấp dịch vụ, nhưng kiểm tra binder có expose API acknowledgement cần thiết hay không.
- Chạy test với Pub/Sub emulator cho logic cơ bản và test với dịch vụ thật cho IAM, quota, ordering và delivery semantics.

### Kiểm thử riêng cho Solace

- Xác minh durable queue và topic subscription được provision đúng.
- Kiểm tra Assured Delivery và queue access type.
- Gửi NACK và quan sát broker redelivery.
- Kiểm tra error queue khác DMQ trong từng loại lỗi.
- Thử manual ack cùng transaction để xác nhận cấu hình bị giới hạn đúng như tài liệu.
- Kiểm tra partition key header trên partitioned queue.
- Xác minh publisher confirmation và queue spool/TTL.

## 10. Quy trình đưa binder đối tác vào production

1. Chọn dịch vụ dựa trên mô hình dữ liệu và yêu cầu delivery, không chỉ dựa trên tên binder.
2. Chốt phiên bản Spring Boot, Spring Cloud Stream, BOM và binder.
3. Đọc release notes, migration guide và compatibility matrix.
4. Xác định ai chịu trách nhiệm nâng cấp binder và xử lý CVE/bug.
5. Khai báo dependency theo starter/BOM của nhà cung cấp.
6. Tách property theo binder và binding; không để secret trong YAML.
7. Tạo topic, subscription, event hub, queue và checkpoint store bằng quy trình hạ tầng.
8. Đặt consumer group hoặc subscription identity ổn định.
9. Chốt payload schema, event ID, header contract và retry/DLQ policy.
10. Chạy integration test với broker thật, gồm restart, rebalance, redelivery và replay.
11. Đặt metric/alert cho backlog, lag, checkpoint, redelivery, publish failure và queue quota.
12. Triển khai canary và xác minh không có duplicate/loss ngoài dự kiến.
13. Chuẩn bị rollback, replay và migration path trước khi chuyển traffic.

Nếu một ứng dụng publish sang broker thứ hai, hãy thiết kế failure handling cho tình huống chỉ một phía thành công. Spring Cloud Stream không cung cấp distributed transaction chung giữa Azure, Google Cloud và Solace. Outbox/inbox và idempotency thường là ranh giới bảo vệ cần thiết.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Binding dùng nhầm binder | Không gán binder hoặc defaultCandidate mơ hồ | Chỉ định binder cho binding quan trọng |
| Event Hubs consumer lặp dữ liệu sau restart | Checkpoint chưa được lưu hoặc Storage lease gặp sự cố | Kiểm tra checkpoint store và idempotency |
| Event Hubs consumer không scale như Kafka | Partition lease/rebalance có semantics riêng | Kiểm tra ownership, Storage lease và partition count |
| Kafka app không chạy trên Event Hubs | Dùng Kafka API không được Event Hubs hỗ trợ hoặc tier không đủ | Kiểm tra feature matrix và tier |
| Pub/Sub không giữ thứ tự như Kafka partition | Ordering key không tương đương partition | Thiết kế theo ordering key và cùng region |
| Pub/Sub tạo subscription ngoài dự kiến | Auto-create resources bật và group không ổn định | Pre-provision resource và tắt auto-create |
| Pub/Sub binder không đáp ứng partitioning | Binder không hỗ trợ Spring Cloud Stream partitioning | Đổi mô hình hoặc chọn broker phù hợp |
| Pub/Sub exactly-once không dùng được từ binder | Binder không expose AckReplyConsumerWithResponse | Xác minh API và cân nhắc dùng client adapter riêng |
| Solace consumer không nhận message | Queue/subscription hoặc Assured Delivery chưa đúng | Kiểm tra Message VPN, queue và ACL |
| Solace binder v5+ không consume được | Broker thấp hơn 10.2.1 | Nâng broker hoặc dùng phiên bản binder tương thích |
| Solace partition key không có tác dụng | Dùng property partitioning chung của Spring Cloud Stream | Dùng partitioned queue và SolaceBinderHeaders.PARTITION_KEY |
| Solace error queue không hoạt động | Thiếu ACL publish hoặc nhầm Error Queue với DMQ | Cấp quyền và kiểm tra đúng loại queue |
| Cross-broker tạo duplicate | Publish thành công nhưng checkpoint/ack nguồn chưa commit | Dùng event ID, inbox/outbox và deduplication |
| Header bị mất khi đổi binder | Header mapping và native metadata khác nhau | Chuẩn hóa contract và test header mapping |

## 12. Bài thực hành: đánh giá ba binder cho luồng đơn hàng

Một hệ thống có ba yêu cầu:

- Thu nhận event đơn hàng từ Event Hubs.
- Phát audit event lên Google Cloud Pub/Sub để nhiều subscription nhận độc lập.
- Phát event đã xử lý lên Solace để các ứng dụng trong event mesh tiêu thụ qua durable queue.

Thực hiện:

1. Viết Function đọc OrderCreated từ Event Hubs và phát OrderAccepted sang Solace.
2. Viết Supplier độc lập phát OrderAudit sang Pub/Sub.
3. Cấu hình từng binding dùng đúng binder.
4. Cấu hình Event Hubs checkpoint store và consumer group.
5. Tạo Pub/Sub topic, hai subscription và kiểm tra fan-out.
6. Tạo Solace Message VPN, topic, durable queue và subscription.
7. Chuẩn hóa eventId, orderId, eventType và occurredAt trong payload.
8. Mô phỏng lỗi sau khi publish Solace thành công nhưng trước khi checkpoint Event Hubs.
9. Xác minh duplicate được xử lý idempotent.
10. Mô phỏng Pub/Sub ack deadline hết hạn và kiểm tra redelivery.
11. Mô phỏng Solace NACK, redelivery và Error Queue.
12. Đo backlog/lag, checkpoint duration, redelivery count và publish latency.
13. So sánh chi phí vận hành, yêu cầu IAM/ACL, khả năng replay và độ phức tạp khi nâng cấp binder.
14. Viết ADR nêu lựa chọn cuối cùng, trade-off và kế hoạch rollback.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Binder selection | Mỗi binding chỉ rõ đúng binder |
| Version compatibility | BOM, Spring Boot, Spring Cloud và binder tương thích |
| Event Hubs checkpoint | Checkpoint store/lease hoạt động qua restart |
| Pub/Sub subscription | Fan-out và group mapping đúng |
| Pub/Sub ordering | Ordering key được bật đúng region/subscription |
| Solace queue | Durable queue và Assured Delivery đúng |
| Error handling | Retry, redelivery, DLQ/error queue đúng semantics |
| Schema contract | Payload và event ID thống nhất giữa broker |
| Idempotency | Cross-broker retry không tạo side effect trùng |
| Security | Workload identity, service account, ACL và secret đúng |
| Observability | Có metric backlog/lag/checkpoint/redelivery |
| Recovery | Có runbook replay và rollback |

## Kết luận

Azure Event Hubs, Google Cloud Pub/Sub và Solace PubSub+ đều có Spring Cloud Stream binder partner-maintained, nhưng phục vụ các mô hình messaging khác nhau. Event Hubs là partitioned event log với checkpoint và lease qua Azure Storage. Pub/Sub là topic/subscription service với acknowledgement deadline, ordering key và fan-out. Solace kết hợp topic routing với durable queue, Assured Delivery, redelivery và event mesh.

Hãy đánh giá semantics trước khi đánh giá cú pháp cấu hình. Event Hubs Binder có checkpoint và batch riêng; Pub/Sub binder không hỗ trợ partitioning của Spring Cloud Stream và có giới hạn API cho exactly-once; Solace binder ánh xạ group thành durable queue và dùng cơ chế partition/ack riêng của broker. Nhiều binder có thể cùng chạy trong một ứng dụng, nhưng không tạo distributed transaction giữa các broker. Giữ payload contract ổn định, dùng idempotency và kiểm thử failure path thực tế trước khi chuyển production.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.1.0 – Binder implementations](https://spring.io/projects/spring-cloud-stream/)
- [Spring Cloud Stream – Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-binders.html)
- [Spring Cloud Azure – Binder for Azure Event Hubs](https://microsoft.github.io/spring-cloud-azure/current/reference/html/index.html#spring-cloud-stream-binder-for-azure-event-hubs)
- [Microsoft Learn – Spring Cloud Stream support](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/spring-cloud-stream-support)
- [Microsoft Learn – Azure Event Hubs for Apache Kafka](https://learn.microsoft.com/en-us/azure/event-hubs/azure-event-hubs-apache-kafka-overview)
- [Spring Framework on Google Cloud – Spring Cloud Stream Binder for Pub/Sub](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/index.html#spring-cloud-stream)
- [Google Cloud – Using Pub/Sub in Spring applications](https://docs.cloud.google.com/pubsub/docs/spring)
- [Google Cloud – Subscription overview](https://docs.cloud.google.com/pubsub/docs/subscription-overview)
- [Google Cloud – Exactly-once delivery](https://docs.cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Solace – Spring Cloud Stream Binder for PubSub+](https://github.com/SolaceProducts/solace-spring-cloud/tree/master/solace-spring-cloud-starters/solace-spring-cloud-stream-starter)
- [Solace – Spring Cloud Stream tutorial](https://tutorials.solace.dev/spring/spring-cloud-stream/)


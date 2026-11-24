# Tích hợp Event Hubs với Spring Integration hoặc Stream binder

Spring Boot có nhiều cách kết nối Azure Event Hubs. Với **Spring Integration**, ứng dụng xây dựng message channel, inbound/outbound adapter, gateway và endpoint xử lý theo mô hình tích hợp của Spring. Với **Spring Cloud Stream**, ứng dụng khai báo các hàm Supplier, Consumer hoặc Function rồi gắn chúng vào destination thông qua **Event Hubs binder**. Hai hướng có thể dùng chung Azure SDK bên dưới, nhưng khác nhau ở cách tổ chức luồng, cấu hình, checkpoint và mức kiểm soát mà ứng dụng trực tiếp nắm giữ.

Bài học thuộc chương **Sự kiện Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua những thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Trong phạm vi bài này, trọng tâm là chọn đúng abstraction cho Event Hubs, cấu hình producer/consumer, xử lý checkpoint, partition, lỗi, bảo mật và vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **Spring Integration channel adapter** và **Spring Cloud Stream binder** khi kết nối Event Hubs.
- Chọn starter/dependency phù hợp và quản lý phiên bản bằng Spring Cloud Azure BOM.
- Gửi event bằng outbound channel adapter/gateway hoặc Stream binding.
- Nhận event bằng EventHubsInboundChannelAdapter hoặc functional Consumer.
- Cấu hình namespace, event hub, consumer group và Blob checkpoint store.
- Dùng Microsoft Entra ID, Managed Identity/Workload Identity và Azure RBAC thay cho secret dài hạn khi có thể.
- Chọn chế độ checkpoint phù hợp; chỉ xác nhận tiến độ sau khi xử lý nghiệp vụ bền vững.
- Hiểu partition key, consumer group, batch mode, error channel, retry và idempotency.
- Viết integration test cô lập, quan sát consumer lag, checkpoint age, throughput và lỗi gửi/nhận.

## 2. Chọn abstraction trước khi chọn code

### 2.1. Spring Integration

Spring Integration cung cấp mô hình **MessageChannel** và endpoint. Adapter nối một hệ thống bên ngoài với channel trong ứng dụng:
- **Outbound channel adapter:** nhận message từ channel và gửi sang Event Hubs.
- **Inbound channel adapter:** nhận event từ Event Hubs rồi đưa vào channel.
- **Messaging gateway:** cung cấp interface Java để code nghiệp vụ gửi message vào channel.
- **Service activator/transformer/router/filter:** xử lý hoặc định tuyến message giữa các channel.

Hướng này phù hợp khi ứng dụng đã dùng Spring Integration, cần ghép Event Hubs vào một luồng có nhiều bước biến đổi/định tuyến, hoặc cần kiểm soát rõ container và checkpoint.

### 2.2. Spring Cloud Stream binder

Spring Cloud Stream cung cấp mô hình hàm:
- **Supplier:** phát dữ liệu ra binding.
- **Consumer:** nhận dữ liệu từ binding.
- **Function:** nhận rồi biến đổi/phát dữ liệu.
- **Binding:** nối input/output của hàm với destination như một Event Hub.
- **Binder:** adapter chuyên biệt kết nối Spring Cloud Stream với broker.

Event Hubs binder sử dụng các Event Hubs channel adapter của Spring Integration ở lớp nền. Ứng dụng làm việc chủ yếu với function và cấu hình binding; binder quản lý phần kết nối, consumer group, partition ownership và checkpoint theo cấu hình.

### 2.3. So sánh nhanh

| Tiêu chí | Spring Integration | Spring Cloud Stream binder |
|---|---|---|
| Mô hình lập trình | MessageChannel, adapter, gateway, service activator | Supplier, Consumer, Function và binding |
| Gửi event | Outbound adapter, EventHubsTemplate/MessageHandler, gateway | Output binding từ Supplier/Function hoặc cơ chế gửi qua binding |
| Nhận event | Inbound adapter và listener container | Input binding gọi Consumer/Function |
| Checkpoint | Container properties và Checkpointer trong message header khi MANUAL | Binder properties và Checkpointer header khi MANUAL |
| Luồng xử lý | Tường minh, có thể ghép router/transformer/filter | Tập trung vào function và cấu hình destination |
| Tái sử dụng abstraction | Tốt khi ứng dụng đã dùng Spring Integration | Tốt khi tổ chức ứng dụng theo mô hình Cloud Stream |
| Kiểm soát chi tiết | Truy cập trực tiếp channel adapter/container properties | Phần lớn qua binder properties; có thể cần API thấp hơn cho trường hợp đặc biệt |
| Độ phức tạp ban đầu | Cần khai báo channel và adapter | Cấu hình binding và function tương đối gọn |

Không có hướng nào tự tạo bảo đảm exactly-once cho nghiệp vụ. Cả hai đều dựa trên Event Hubs, partition, consumer group và checkpoint; duplicate/replay vẫn phải được xử lý ở tầng ứng dụng.

## 3. Dependency và quản lý phiên bản

Spring Cloud Azure cung cấp starter riêng cho hai hướng:

| Nhu cầu | Artifact gợi ý |
|---|---|
| Spring Integration với Event Hubs | `com.azure.spring:spring-cloud-azure-starter-integration-eventhubs` |
| Spring Cloud Stream Event Hubs binder | `com.azure.spring:spring-cloud-azure-starter-stream-eventhubs` |
| Binder module không dùng starter tổng hợp | `com.azure.spring:spring-cloud-azure-stream-binder-eventhubs` |

Ví dụ dependency Maven cho Spring Integration:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-integration-eventhubs</artifactId>
</dependency>
~~~

Ví dụ dependency Maven cho Stream binder:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-stream-eventhubs</artifactId>
</dependency>
~~~

Quản lý các dependency Spring Cloud Azure bằng **Spring Cloud Azure BOM** tương thích với Spring Boot và Spring Cloud release train của dự án. Không tự ghép một phiên bản starter, binder, Azure SDK và Spring Integration tùy ý.

API và property đã thay đổi qua các thế hệ thư viện. Ví dụ các class hiện đại dùng tên `EventHubsInboundChannelAdapter`, `EventHubsMessageListenerContainer` và `EventHubsTemplate`; các API cũ như `EventHubOperation` hoặc `EventHubInboundChannelAdapter` có thể xuất hiện trong tài liệu legacy. Trước khi copy code, đối chiếu version mapping và migration guide của BOM đang dùng.

## 4. Chuẩn bị Event Hub và checkpoint store

Trước khi cấu hình Spring Boot, tạo sẵn các tài nguyên:
- Event Hubs namespace.
- Event hub, ví dụ `order-events`.
- Consumer group riêng cho mỗi ứng dụng logic, ví dụ `order-projection`.
- Storage account và Blob container dành cho ownership/checkpoint.
- Managed Identity hoặc workload identity cho runtime.
- Role assignment ở đúng scope.

Checkpoint store lưu **partition ownership và checkpoint metadata**, không lưu toàn bộ event stream. Các instance của cùng consumer group cần dùng chung checkpoint store logic để phối hợp. Không tạo một container ngẫu nhiên mỗi lần deploy, vì processor mới sẽ không tìm thấy tiến độ cũ.

Tạo namespace, event hub và container bằng IaC hoặc quy trình platform. Không cấp quyền quản lý resource rộng cho runtime chỉ để ứng dụng có thể tự tạo tài nguyên khi khởi động.

## 5. Xác thực và phân quyền

Ưu tiên Microsoft Entra ID:
- Producer cần role **Azure Event Hubs Data Sender**.
- Consumer cần role **Azure Event Hubs Data Receiver**.
- Processor ghi checkpoint cần role **Storage Blob Data Contributor** trên container hoặc scope phù hợp.
- Pipeline/IaC dùng danh tính triển khai riêng, có quyền quản lý resource theo phạm vi.
- Local developer có thể dùng credential phát triển, nhưng không tái sử dụng principal production.

Với Managed Identity, cấu hình tùy môi trường:
- System-assigned identity không cần client ID riêng.
- User-assigned identity cần client ID của identity được gắn.
- AKS có thể dùng Workload Identity.
- CI/CD có thể dùng workload identity federation.

Không commit connection string, SAS token, storage account key hoặc client secret vào source. Nếu phải dùng connection string trong lab, đặt trong secret store hoặc biến môi trường và giới hạn quyền/thời hạn. Role quản lý namespace không đồng nghĩa role data-plane; cần cấp đúng Data Sender/Receiver.

## 6. Cấu hình Azure dùng chung

Ví dụ cấu hình cho môi trường dev:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        # Với user-assigned identity, thêm client-id theo cấu hình môi trường.
        # client-id: <user-assigned-managed-identity-client-id>
      eventhubs:
        namespace: ${AZURE_EVENTHUBS_NAMESPACE}
        processor:
          checkpoint-store:
            account-name: ${AZURE_CHECKPOINT_STORAGE_ACCOUNT}
            container-name: ${AZURE_CHECKPOINT_CONTAINER}
~~~

Đây là các property Spring Cloud Azure cho credential, namespace và checkpoint store. Các biến môi trường phải được cấp từ deployment platform. Với local development, chọn credential chain phù hợp thay vì giả định Managed Identity có sẵn.

Từ Spring Cloud Azure 4.x trở đi, checkpoint container không nhất thiết được tạo tự động. Hãy tạo container trước bằng IaC; chỉ bật tùy chọn create-container-if-not-exists khi thực sự muốn ứng dụng có trách nhiệm tạo container và identity được cấp quyền tương ứng.

Tách checkpoint container theo môi trường và workload. Dev không nên dùng checkpoint container production; hai consumer group khác nhau cần tiến độ đọc độc lập.

## 7. Spring Integration: gửi event qua outbound channel adapter

### 7.1. Tạo output channel và MessageHandler

Spring Integration dùng một channel làm điểm vào cho luồng gửi. `EventHubsTemplate` cung cấp khả năng gửi, còn `DefaultMessageHandler` gắn template với tên event hub.

~~~java
import com.azure.spring.integration.core.handler.DefaultMessageHandler;
import com.azure.spring.messaging.eventhubs.core.EventHubsTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
class EventHubOutboundConfiguration {

    @Bean
    MessageChannel eventHubOutput() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "eventHubOutput")
    MessageHandler eventHubMessageSender(EventHubsTemplate template) {
        return new DefaultMessageHandler("order-events", template);
    }
}
~~~

Đây là cấu hình minh họa theo API Spring Integration Azure hiện đại; package/class cụ thể cần đối chiếu với BOM đang dùng. Namespace và credential được cấu hình qua Spring Cloud Azure. Producer runtime cần Event Hubs Data Sender.

### 7.2. Gửi bằng Messaging Gateway

Gateway giúp code nghiệp vụ không phụ thuộc trực tiếp vào EventHubsTemplate hoặc channel implementation:

~~~java
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.Message;

@MessagingGateway(defaultRequestChannel = "eventHubOutput")
interface OrderEventGateway {
    void send(Message<?> event);
}
~~~

Dùng gateway trong service:

~~~java
import com.azure.spring.messaging.AzureHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {
    private final OrderEventGateway gateway;

    OrderPublisher(OrderEventGateway gateway) {
        this.gateway = gateway;
    }

    void publish(String orderId, String jsonPayload) {
        gateway.send(MessageBuilder.withPayload(jsonPayload)
                .setHeader(AzureHeaders.PARTITION_KEY, orderId)
                .setHeader("eventId", "order-" + orderId + "-created")
                .build());
    }
}
~~~

Header partition key được ánh xạ thành thông tin định tuyến của Event Hubs; application headers được chuyển thành application properties theo hỗ trợ của adapter. Không tự đặt các header hệ thống như offset, sequence number hoặc enqueued time. Event ID cần ổn định qua retry; ví dụ trên chỉ minh họa, hệ thống thực nên tạo ID duy nhất theo nghiệp vụ.

### 7.3. Theo dõi lỗi gửi

Gửi bất đồng bộ có nghĩa lỗi có thể xuất hiện sau khi method gọi gateway đã trả về, tùy handler và callback được cấu hình. Cần có cơ chế quan sát send failure và không coi việc đưa message vào channel là bằng chứng Event Hubs đã nhận event.

Với sự cố timeout, kết quả gửi có thể không xác định: dịch vụ có thể đã nhận event nhưng phản hồi bị mất. Giữ nguyên event ID qua retry và làm consumer idempotent. Nếu database commit và publish phải nhất quán, dùng transactional outbox.

## 8. Spring Integration: nhận event qua inbound channel adapter

### 8.1. Tạo listener container với MANUAL checkpoint

`EventHubsInboundChannelAdapter` nhận event từ listener container rồi đẩy message vào Spring channel. Container sử dụng EventProcessorClient ở lớp dưới và cần consumer group cùng checkpoint store.

~~~java
import com.azure.spring.messaging.eventhubs.core.EventHubsProcessorFactory;
import com.azure.spring.messaging.eventhubs.core.checkpoint.CheckpointConfig;
import com.azure.spring.messaging.eventhubs.core.checkpoint.CheckpointMode;
import com.azure.spring.messaging.eventhubs.core.listener.EventHubsMessageListenerContainer;
import com.azure.spring.messaging.eventhubs.core.properties.EventHubsContainerProperties;
import com.azure.spring.integration.eventhubs.inbound.EventHubsInboundChannelAdapter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
class EventHubInboundConfiguration {

    @Bean
    MessageChannel eventHubInput() {
        return new DirectChannel();
    }

    @Bean
    EventHubsMessageListenerContainer eventHubsListenerContainer(
            EventHubsProcessorFactory processorFactory) {
        EventHubsContainerProperties properties =
                new EventHubsContainerProperties();
        properties.setEventHubName("order-events");
        properties.setConsumerGroup("order-projection");
        properties.setCheckpointConfig(
                new CheckpointConfig(CheckpointMode.MANUAL));

        return new EventHubsMessageListenerContainer(
                processorFactory, properties);
    }

    @Bean
    EventHubsInboundChannelAdapter eventHubsInboundAdapter(
            @Qualifier("eventHubInput") MessageChannel input,
            EventHubsMessageListenerContainer listenerContainer) {
        EventHubsInboundChannelAdapter adapter =
                new EventHubsInboundChannelAdapter(listenerContainer);
        adapter.setOutputChannel(input);
        return adapter;
    }
}
~~~

Các import thể hiện nhóm API cần dùng; hãy kiểm tra package và constructor chính xác theo phiên bản dependency. Không tạo một listener container khác cho từng request. Container phải sống theo lifecycle ứng dụng và cùng consumer group/checkpoint store với các replica của cùng workload.

### 8.2. Xử lý rồi mới checkpoint

Trong MANUAL mode, message mang header `AzureHeaders.CHECKPOINTER`. Handler chỉ gọi success sau khi xử lý nghiệp vụ đã commit bền vững:

~~~java
import com.azure.spring.messaging.AzureHeaders;
import com.azure.spring.messaging.checkpoint.Checkpointer;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
class OrderEventHandler {
    private final OrderService orderService;

    OrderEventHandler(OrderService orderService) {
        this.orderService = orderService;
    }

    @ServiceActivator(inputChannel = "eventHubInput")
    public void receive(
            byte[] payload,
            @Header(AzureHeaders.CHECKPOINTER) Checkpointer checkpointer) {

        // Service transaction hoàn tất và commit trước khi method trả về.
        orderService.processAndCommit(payload);

        // Chỉ checkpoint sau khi side effect đã bền vững.
        checkpointer.success().block();
    }
}
~~~

`processAndCommit` nên nằm trong một service bean có transaction riêng; khi lời gọi qua Spring proxy trả về, transaction đã commit. Nếu đặt `@Transactional` ngay trên method `receive` rồi checkpoint trong cùng method, checkpoint có thể chạy trước thời điểm transaction commit do transaction interceptor chỉ commit sau khi method kết thúc.

Nếu handler ném exception, không checkpoint event đó. Nếu DB commit thành công nhưng checkpoint thất bại, event có thể được đọc lại; dùng inbox/unique event ID để tránh side effect lặp. Trong luồng reactive, compose Mono thay vì block trên event loop.

### 8.3. Batch mode

Inbound adapter hỗ trợ batch listener. Khi bật `ListenerMode.BATCH`, payload là danh sách event và một số header cũng chuyển thành danh sách. Cấu hình batch size và wait time trên container properties. Checkpoint mode BATCH chỉ phù hợp với batch-consuming mode; MANUAL cho phép ứng dụng quyết định khi batch đã được xử lý bền vững.

Với batch, phải quyết định rõ:
- Nếu một event trong batch lỗi, checkpoint toàn batch có an toàn không?
- Có cần lưu từng event lỗi vào quarantine trước khi checkpoint batch không?
- Có thể xử lý song song nhưng vẫn giữ watermark hoàn tất liên tục không?
- Batch size/wait time ảnh hưởng latency, memory và replay window thế nào?

Không checkpoint cả batch chỉ vì đã nhận batch. Với side effect database, commit dữ liệu cần thiết trước rồi mới checkpoint.

## 9. Spring Cloud Stream: cấu hình Event Hubs binder

### 9.1. Dependency và binding

Dùng `spring-cloud-azure-starter-stream-eventhubs` hoặc binder module `spring-cloud-azure-stream-binder-eventhubs`. Binder nối function input/output với Event Hub destination.

Ví dụ cấu hình consumer và producer cùng một event hub:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
      eventhubs:
        namespace: ${AZURE_EVENTHUBS_NAMESPACE}
        processor:
          checkpoint-store:
            account-name: ${AZURE_CHECKPOINT_STORAGE_ACCOUNT}
            container-name: ${AZURE_CHECKPOINT_CONTAINER}
    stream:
      function:
        definition: consume;supply
      bindings:
        consume-in-0:
          destination: ${AZURE_EVENTHUB_NAME}
          group: ${AZURE_EVENTHUB_CONSUMER_GROUP}
        supply-out-0:
          destination: ${AZURE_EVENTHUB_NAME}
      eventhubs:
        bindings:
          consume-in-0:
            consumer:
              checkpoint:
                mode: MANUAL
~~~

Các binding name `consume-in-0` và `supply-out-0` được tạo theo tên function và hướng input/output. `destination` là tên Event Hub; `group` là consumer group. Các giá trị môi trường được cấp từ deployment, không ghi connection string hoặc account key vào file.

### 9.2. Functional Consumer với manual checkpoint

~~~java
import com.azure.spring.messaging.AzureHeaders;
import com.azure.spring.messaging.checkpoint.Checkpointer;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import java.util.function.Consumer;

@Component
class OrderFunctions {
    private final OrderService orderService;

    OrderFunctions(OrderService orderService) {
        this.orderService = orderService;
    }

    @Bean
    Consumer<Message<String>> consume() {
        return message -> {
            orderService.processAndCommit(message.getPayload());

            Checkpointer checkpointer = message.getHeaders()
                    .get(AzureHeaders.CHECKPOINTER, Checkpointer.class);
            if (checkpointer == null) {
                throw new IllegalStateException(
                        "Manual checkpoint header is missing");
            }
            checkpointer.success().block();
        };
    }
}
~~~

Khi checkpoint mode là MANUAL, binder đưa Checkpointer vào message header. Handler phải gọi success sau khi xử lý thành công. Không nuốt exception và không checkpoint khi transaction chưa commit. Với mode tự động, binder quyết định checkpoint theo cấu hình; hãy hiểu rõ semantics trước khi chọn.

### 9.3. Functional Supplier để phát event

Supplier được binder poll theo lịch. Ví dụ đơn giản:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;

@Bean
Supplier<Message<String>> supply() {
    AtomicLong sequence = new AtomicLong();
    return () -> {
        String payload = """
                {"eventId":"demo-%d","eventType":"TelemetryReceived"}
                """.formatted(sequence.incrementAndGet());
        return MessageBuilder.withPayload(payload).build();
    };
}
~~~

Supplier phù hợp cho dữ liệu định kỳ hoặc demo. Với event phát sinh theo request nghiệp vụ, cần chọn cách gửi theo binding/StreamBridge phù hợp phiên bản Spring Cloud Stream để không biến poller thành nguồn phát liên tục ngoài ý muốn. Trong cả hai trường hợp, event phải có ID ổn định và schema rõ ràng.

## 10. Checkpoint mode và batch trong Stream binder

Binder hỗ trợ các cấu hình checkpoint theo binding, tùy phiên bản:
- `RECORD`: checkpoint sau từng record khi mode này được hỗ trợ.
- `MANUAL`: ứng dụng gọi Checkpointer từ header sau khi xử lý bền vững.
- `BATCH`: checkpoint theo batch khi sử dụng batch consumer.
- `PARTITION_COUNT`: checkpoint sau số event cấu hình cho mỗi partition.
- `TIME`: checkpoint theo khoảng thời gian cấu hình.

Tên mode và property phải được xác minh theo BOM/binder version đang dùng. Các property count và interval chỉ có ý nghĩa với mode tương ứng.

Với `BATCH`, binder tự checkpoint batch sau khi batch được nhận theo semantics của binder; điều đó không chứng minh transaction nghiệp vụ trong database đã commit. Nếu cần quyết định checkpoint sau side effect bền vững, ưu tiên `MANUAL` và gọi Checkpointer sau khi service transaction hoàn tất.

Ví dụ batch consumer:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        consume-in-0:
          consumer:
            batch-mode: true
      eventhubs:
        bindings:
          consume-in-0:
            consumer:
              batch:
                max-size: 100
                max-wait-time: 2s
              checkpoint:
                mode: MANUAL
~~~

Khi batch mode bật, function nhận `Message<List<T>>`; các header như partition key, offset, sequence number và enqueued time có thể là danh sách theo từng event. Header partition/checkpointer chung cho batch được biểu diễn theo batch semantics. Đừng ép kiểu header của record consumer sang list consumer hoặc ngược lại.

Binder mặc định có content type negotiation. Với payload String nhưng content type là application/json, nội dung phải là JSON string hợp lệ theo converter; nếu cần văn bản thuần, cấu hình content type phù hợp như text/plain. Kiểm tra serialization bằng contract test thay vì chỉ dựa vào log payload.

## 11. Partition key, consumer group và scale

### 11.1. Partition key

Chọn partition key theo entity cần giữ thứ tự, ví dụ order ID hoặc device ID. Trong Spring Integration có thể truyền partition key qua message header được adapter hỗ trợ, ví dụ `AzureHeaders.PARTITION_KEY`. Với Stream binder, dùng cơ chế partition information/partition supplier và các thuộc tính partitioning mà binder version hỗ trợ.

Không nhầm:
- Partition key là khóa định tuyến event tới partition.
- Partition ID là partition cụ thể.
- Consumer group là vị trí đọc độc lập.
- Consumer instance là process/pod đang xử lý partition.

Một key quá nóng có thể làm một partition lag trong khi partition khác nhàn rỗi. Không có thứ tự tổng thể giữa các partition; nếu cần thứ tự nghiệp vụ, gắn aggregate version và kiểm tra tại consumer.

### 11.2. Consumer group

Mỗi ứng dụng logic nên có consumer group riêng, ví dụ `order-projection`, `analytics`, `fraud-detection`. Các replica của cùng ứng dụng logic dùng chung group để chia partition. Không tạo group mới cho mỗi pod nếu muốn chia tải; nếu làm vậy mỗi pod sẽ đọc một bản stream độc lập.

### 11.3. Checkpoint store và ownership

Cả hai abstraction dựa vào Blob Storage để lưu checkpoint/partition ownership. Spring Integration cấu hình checkpoint store qua Spring Cloud Azure Event Hubs properties; Stream binder cũng dùng cùng nhóm cấu hình checkpoint store. Các replica của cùng consumer group phải dùng cùng storage container logic. Nếu Blob bị 403 hoặc không truy cập được, processor có thể không lưu tiến độ hoặc cân bằng ownership.

Thêm pod không bảo đảm tăng throughput tuyến tính; số partition giới hạn parallelism. Kiểm tra consumer lag, ownership rebalance, DB pool và Blob latency trước khi scale.

## 12. Error handling, retry và idempotency

### 12.1. Spring Integration error channel

Spring Integration có error channel toàn cục và các error channel theo endpoint/adapter tùy cấu hình. Đăng ký handler để ghi nhận exception, correlation ID và context đã lọc; không chỉ log rồi bỏ qua. Khi handler nghiệp vụ lỗi, không checkpoint event.

### 12.2. Stream binder error channel

Binder có consumer error channel theo destination/group. Producer error channel có thể cần bật cấu hình `spring.cloud.stream.default.producer.errorChannelEnabled=true` trước khi đăng ký handler. Kiểm tra binding name thực tế để đặt đúng channel; đừng giả định lỗi producer và consumer đi cùng một channel.

### 12.3. Retry và lỗi không retry được

Retry chỉ dành cho lỗi tạm thời như throttling hoặc network interruption, có giới hạn, backoff, jitter và deadline. 401/403, sai namespace/event hub, payload không hợp lệ và schema error cần sửa cấu hình hoặc dữ liệu; retry vô hạn chỉ tăng tải.

SDK/binder có retry policy riêng. Trước khi thêm retry ở service layer, xác định số attempts tổng để tránh retry lồng nhau. Timeout khi send có thể có kết quả không xác định; giữ nguyên event ID qua retry.

### 12.4. Idempotency

Event Hubs là stream có thể replay từ checkpoint gần nhất. Handler cần idempotent:
- Dùng event ID ổn định từ producer.
- Ghi event ID vào inbox/processed-event table có unique constraint.
- Ghi dedup record và thay đổi nghiệp vụ trong cùng database transaction.
- Nếu event đã xử lý, không lặp side effect.
- Nếu cùng ID nhưng payload khác, ghi nhận conflict để điều tra.

Không dựa vào offset làm ID nghiệp vụ. Offset thuộc partition và consumer group; replay hoặc workload khác có thể đọc lại event trong ngữ cảnh khác.

## 13. Transactional outbox khi publish từ Spring Boot

Nếu API cập nhật database rồi gửi Event Hubs, hai thao tác không nằm trong một transaction atomic mặc định. Có thể xảy ra DB commit thành công nhưng publish thất bại, hoặc publish thành công nhưng response bị mất.

Transactional outbox giải quyết khoảng trống giữa commit DB và publish:
1. Ghi thay đổi nghiệp vụ và outbox event trong cùng transaction.
2. Worker đọc outbox và gửi event qua gateway/binding.
3. Đánh dấu outbox đã gửi sau khi nhận xác nhận.
4. Nếu worker chết sau send nhưng trước khi đánh dấu, event có thể được gửi lại; consumer dedup theo event ID.

~~~mermaid
flowchart TD
    API["Spring Boot API"] --> TX["Database transaction"]
    TX --> O["Update order"]
    TX --> OB["Insert outbox event"]
    OB --> W["Outbox publisher"]
    W --> EH["Event Hubs"]
    EH --> C["Idempotent consumer"]
    W -. "Send timeout / retry" .-> OB
~~~

Outbox không tạo exactly-once xuyên database và Event Hubs; nó bảo đảm event không bị quên sau commit, trong khi consumer xử lý duplicate an toàn.

## 14. Quan sát và vận hành

Theo dõi các chỉ số theo binding, consumer group và partition:
- Producer send success/failure, send latency, retry count và throttling.
- Incoming/outgoing messages/bytes, consumer lag và tuổi event chưa xử lý.
- Partition ownership/rebalance và số processor instance.
- Checkpoint age, checkpoint failure và Blob latency.
- Handler processing duration, duplicate suppressed và quarantine count.
- Batch size, batch wait time, prefetch và số event in-flight.
- CPU, memory, thread pool, DB connection pool và network.
- Chi phí Event Hubs tier/capacity, Blob checkpoint operations, retention, Capture và monitoring.

Log nên có event ID, correlation ID, consumer group, partition ID, sequence number và offset đã lọc; không log access token, SAS, connection string hoặc raw payload nhạy cảm.

Đặt cảnh báo khi checkpoint không tiến, consumer lag tăng, processor không có ownership, Blob checkpoint store trả 403/timeout hoặc throttling tăng đột biến. Mỗi cảnh báo cần runbook xác minh identity, resource, Region và network.

## 15. Kiểm thử tích hợp

Dùng namespace, event hub, consumer group và checkpoint container riêng cho test. Không reset checkpoint production hoặc dùng chung consumer group với workload thật.

| Kịch bản | Spring Integration | Stream binder | Kết quả mong đợi |
|---|---|---|---|
| Gửi event | Gateway/outbound adapter | Supplier/output binding | Event tới đúng Event Hub |
| Nhận event | Inbound adapter/channel | Consumer input binding | Handler nhận đúng payload và headers |
| Manual checkpoint | Checkpointer header | Checkpointer header | Chỉ checkpoint sau commit |
| Duplicate/replay | Gửi lại cùng event ID hoặc restart | Gửi lại cùng event ID hoặc restart | Không lặp side effect |
| Checkpoint Blob 403 | Dùng identity thiếu role | Dùng identity thiếu role | Lỗi được quan sát, tiến độ không báo thành công |
| Throttling/timeout | Giả lập lỗi adapter/SDK | Giả lập lỗi binder/SDK | Retry giới hạn, không retry storm |
| Batch | ListenerMode.BATCH | batch-mode=true | Batch và header đúng kiểu |
| Scale-out | Nhiều container cùng group | Nhiều instance cùng binding/group | Partition ownership được chia |
| Cross-environment | Identity dev truy cập resource prod | Identity dev truy cập resource prod | RBAC/network từ chối |
| Shutdown | Dừng container có kiểm soát | Dừng ứng dụng có kiểm soát | Event chưa checkpoint có thể replay an toàn |

Unit test kiểm tra serializer, event contract, partition key và business idempotency. Cloud integration test mới xác minh được Managed Identity, RBAC, private endpoint, checkpoint store và processor ownership thực tế.

## 16. Lỗi thường gặp

| Lỗi | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Producer 401/403 | Thiếu Data Sender hoặc sai principal | Xác minh identity runtime và role scope |
| Consumer không nhận event | Sai event hub/group/initial position hoặc thiếu Data Receiver | Kiểm tra binding destination, group và quyền |
| Processor không checkpoint | Blob container sai, thiếu Blob Data Contributor hoặc network lỗi | Kiểm tra checkpoint store và endpoint |
| Event xử lý lặp | Crash sau DB commit trước checkpoint | Inbox/dedup trong cùng transaction |
| Batch bị bỏ qua sau lỗi | Chọn BATCH checkpoint quá sớm so với nghiệp vụ | Dùng MANUAL và checkpoint sau xử lý |
| Tăng replica nhưng lag không giảm | Số partition hoặc downstream giới hạn | Đo lag theo partition, DB và handler |
| Không thấy lỗi producer | Producer error channel chưa bật hoặc callback chưa xử lý | Cấu hình error channel/callback |
| Profile dev đọc production | Endpoint/credential cấu hình sai | Tách identity/resource và thêm startup guard |
| Payload String lỗi parse | Content type và serializer không khớp | Kiểm tra content-type/JSON contract |

## 17. Chọn cách tích hợp nào?

Chọn **Spring Integration** khi:
- Ứng dụng đã có nhiều MessageChannel và flow.
- Cần router, filter, transformer, gateway hoặc adapter tùy chỉnh.
- Muốn kiểm soát trực tiếp listener container, batch mode và Checkpointer.
- Luồng tích hợp phức tạp hơn một function input/output.

Chọn **Spring Cloud Stream binder** khi:
- Ứng dụng được tổ chức quanh Supplier/Consumer/Function.
- Muốn khai báo destination và consumer group bằng binding properties.
- Cần mô hình function/pub-sub thống nhất giữa nhiều binder.
- Luồng xử lý có thể biểu diễn gọn bằng function và error channel.

Không nên dùng cả hai abstraction để tạo hai consumer vô tình đọc cùng một event hub/group. Nếu phối hợp chúng trong một ứng dụng, xác định rõ consumer group, checkpoint store và trách nhiệm từng luồng. Nếu cần API Event Hubs rất đặc thù không được abstraction expose, cân nhắc dùng Azure SDK trực tiếp cho phần đó thay vì ép abstraction.

## 18. Checklist trước production

- **Version:** BOM Spring Cloud Azure tương thích Spring Boot/Cloud; không dùng API legacy.
- **Resource:** Namespace, event hub, consumer group và checkpoint container đúng môi trường.
- **Identity:** Producer Data Sender, consumer Data Receiver, checkpoint Blob Data Contributor ở scope tối thiểu.
- **Configuration:** Namespace, destination, group, checkpoint store, Region và endpoint được quản lý qua deployment config.
- **Producer:** Event ID ổn định, schema version, partition key, send error và timeout được xử lý.
- **Consumer:** Handler idempotent, MANUAL checkpoint sau commit hoặc mode tự động đã được đánh giá.
- **Batch:** Listener/binder batch mode, payload type và checkpoint semantics khớp nhau.
- **Reliability:** Retry giới hạn, backoff/jitter, outbox/inbox, poison event và graceful shutdown.
- **Observability:** Send latency, throttling, consumer lag, checkpoint age, ownership và error channel có metric/alert.
- **Testing:** Duplicate, replay, checkpoint failure, RBAC denial, batch, scale-out và cross-environment test.
- **Cost:** Event Hubs capacity/tier, retention, Blob checkpoint operations, network và monitoring được dự toán.
- **Runbook:** Có hướng xử lý 401/403, timeout, lag, checkpoint failure và replay.

## 19. Tổng kết

**Spring Integration** nối Event Hubs với message channel bằng outbound/inbound adapter, gateway và listener container. **Spring Cloud Stream binder** nối Supplier/Consumer/Function với Event Hub qua binding và cấu hình destination/group. Binder dựa trên channel adapter ở lớp nền nhưng cung cấp mô hình lập trình hàm và cấu hình khác.

Dù chọn abstraction nào, ứng dụng vẫn phải quản lý consumer group, partition, Blob checkpoint store, Managed Identity/RBAC, event schema, retry và idempotency. Quy tắc quan trọng là **xử lý nghiệp vụ bền vững trước rồi mới checkpoint**. Kiểm thử crash/replay, checkpoint failure, batch và quyền truy cập trên tài nguyên riêng sẽ giúp Spring Boot tích hợp Event Hubs có thể mở rộng và phục hồi an toàn.

## Tài liệu tham khảo

- Spring Cloud Azure Developer Guide: https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview
- Spring Integration support for Azure Event Hubs: https://microsoft.github.io/spring-cloud-azure/current/reference/html/index.html
- Spring Cloud Stream support for Azure Event Hubs: https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/spring-cloud-stream-support
- Spring Cloud Stream binding properties: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html


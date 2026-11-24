# Chọn Spring Integration cho luồng tích hợp hướng thông điệp

## 1. Bối cảnh và mục tiêu

Trong module **Spring Cloud Provider Integration**, ứng dụng Spring Boot kết nối các dịch vụ managed của AWS, Azure và Google Cloud thông qua thư viện Spring Cloud, SDK và connector tương ứng. Khi một nghiệp vụ cần nhận event từ queue, gọi API bên ngoài, chuyển đổi payload, định tuyến theo điều kiện, kết hợp nhiều kết quả hoặc gửi thông điệp sang hệ thống khác, phần tích hợp nhanh chóng trở thành một luồng xử lý nhiều bước.

**Spring Integration** cung cấp mô hình lập trình hướng thông điệp để mô tả các luồng đó bằng message, channel, endpoint, transformer, router, filter, splitter, aggregator và gateway. Thay vì để service nghiệp vụ gọi trực tiếp từng SDK, ứng dụng có thể đặt các bước tích hợp vào một flow có ranh giới rõ ràng. Các adapter ở đầu vào/đầu ra chịu trách nhiệm giao tiếp với hệ thống bên ngoài; các handler ở giữa xử lý dữ liệu và điều phối.

Spring Integration đặc biệt hữu ích khi ứng dụng cần **điều phối luồng tích hợp bên trong một process Spring**. Ví dụ: nhận event ReservationConfirmed từ SQS, kiểm tra schema, enrich dữ liệu từ dịch vụ hồ sơ, phân tuyến theo tenant, rồi gửi thông tin sang một queue hoặc API đối tác. Flow có thể dùng channel đồng bộ hoặc bất đồng bộ, có thể quản lý retry/error channel và có thể kết hợp nhiều transport.

Spring Integration không thay thế mọi messaging platform. Khi mục tiêu chính là xây dựng microservice event-driven với contract message xuyên service và khả năng đổi binder giữa Kafka/RabbitMQ/cloud broker, **Spring Cloud Stream** thường phù hợp hơn. Khi chỉ cần một lệnh SDK đơn giản trong một use case, gọi SDK trực tiếp có thể rõ ràng hơn. Bài học tập trung vào cách chọn đúng công cụ và thiết kế flow bền vững.

Sau bài học, bạn có thể:

1. Phân biệt Spring Integration, Spring Cloud Stream và gọi SDK trực tiếp.
2. Nhận diện message, header, channel, endpoint, adapter và gateway.
3. Thiết kế flow bằng Java DSL với transformer, filter, router và service activator.
4. Kết nối flow với queue/topic/object storage/API managed của AWS, Azure và Google Cloud.
5. Chọn channel semantics, concurrency, transaction boundary và backpressure phù hợp.
6. Xử lý lỗi, retry, dead-letter, idempotency và transactional outbox.
7. Kiểm thử flow bằng mock, test channel, broker emulator và cloud staging.
8. Quan sát throughput, latency, backlog, retry và lỗi theo từng endpoint.

> **Phạm vi:** Spring Integration là framework tích hợp message-oriented trong ứng dụng Spring. Các cloud adapter phụ thuộc module, phiên bản và dịch vụ cụ thể. Không mặc định một starter Spring Cloud cung cấp sẵn adapter cho mọi service hoặc mọi operation; khi thiếu adapter phù hợp, có thể viết bridge nhỏ dùng SDK provider trong một endpoint riêng.

## 2. Chọn Spring Integration, Spring Cloud Stream hay SDK trực tiếp?

### 2.1. Bắt đầu từ hình dạng bài toán

Ba lựa chọn có thể cùng xuất hiện trong một hệ thống nhưng giải quyết các bài toán khác nhau:

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Điều phối nhiều bước trong một ứng dụng: transform, filter, route, split, aggregate, gọi API | **Spring Integration** | Có mô hình flow, channel và endpoint phong phú |
| Xây dựng producer/consumer microservice trao đổi event qua broker, muốn abstraction binder | **Spring Cloud Stream** | Function-based model, binder và destination abstraction |
| Một use case gọi một API cloud đơn giản, không có flow trung gian | **SDK trực tiếp** | Ít tầng, dễ đọc và dễ debug |
| Poll một nguồn dữ liệu, enrich, chuyển đổi, ghi sang nhiều đích | **Spring Integration** | Có inbound/outbound adapter và routing |
| Xử lý event stream liên tục với Kafka Streams semantics hoặc window/stateful stream | **Kafka Streams / nền tảng stream chuyên dụng** | Có semantics xử lý stream chuyên sâu |
| Orchestrate workflow dài, chờ nhiều giờ/ngày, cần durable state và compensation | **Workflow engine / managed workflow** | Trạng thái và tiến trình được lưu bền vững qua process restart |

Không chọn framework chỉ vì một integration có thể được viết bằng framework đó. Hãy xác định nơi cần điều phối, transport nào cần hỗ trợ, delivery guarantee, latency, throughput, ordering, retry và ai sở hữu schema.

### 2.2. Spring Integration và Spring Cloud Stream

| Tiêu chí | Spring Integration | Spring Cloud Stream |
| --- | --- | --- |
| Trọng tâm | Integration flow bên trong ứng dụng | Message-driven microservice qua binder |
| Mô hình | MessageChannel, endpoint, IntegrationFlow | Function/Consumer/Supplier và binding |
| Điều phối | Router, transformer, filter, splitter, aggregator, gateway | Xử lý message trong function; binder lo transport binding |
| Broker | Adapter/connector theo endpoint | Binder cho Kafka, RabbitMQ và một số managed broker |
| Kết nối nhiều hệ thống trong một process | Rất phù hợp | Có thể làm, nhưng không phải trọng tâm chính |
| Abstraction transport | Theo adapter cụ thể | Destination/binder abstraction |
| Tính năng nâng cao | Channel, poller, endpoint lifecycle, control bus, error channel | Consumer groups, partitioning, binder-specific capabilities |

Spring Cloud Stream có thể dùng Spring Integration bên dưới cho một số phần triển khai, nhưng hai framework có API và mục tiêu sử dụng khác nhau. Có thể dùng Stream cho boundary giữa microservice và Integration cho một flow nội bộ phức tạp, miễn là xác định rõ trách nhiệm để tránh hai tầng cùng quản lý retry/ack một cách khó hiểu.

### 2.3. Decision tree

~~~mermaid
flowchart TD
    A["Có cần giao tiếp với hệ thống bên ngoài?"] -->|Không| B["Dùng service/domain code thông thường"]
    A -->|Có| C{"Chỉ một lệnh SDK đơn giản?"}
    C -->|Có| D["Gọi SDK trực tiếp qua adapter nhỏ"]
    C -->|Không| E{"Trọng tâm là producer/consumer microservice qua broker?"}
    E -->|Có| F["Cân nhắc Spring Cloud Stream"]
    E -->|Không| G{"Có nhiều bước tích hợp cần điều phối?"}
    G -->|Có| H["Spring Integration flow"]
    G -->|Không| I["Chọn adapter/SDK đơn giản nhất"]
~~~

Hãy xem xét lại quyết định khi flow bắt đầu chứa nhiều logic nghiệp vụ. Integration flow nên điều phối thông điệp và gọi các application service; domain rule phức tạp vẫn thuộc domain/application layer. Không biến một IntegrationFlow dài thành nơi chứa toàn bộ business logic.

### 2.4. Những câu hỏi trước khi chọn

- Nguồn vào là queue, topic, webhook, file/object storage, database polling hay HTTP?
- Đầu ra là một hay nhiều hệ thống? Có cần fan-out hoặc content-based routing không?
- Message có cần xử lý đồng bộ trong request thread hay bất đồng bộ?
- Khi broker/đích không sẵn sàng, message được giữ ở đâu?
- Cần ordering theo toàn queue, partition, tenant hay aggregate ID?
- Consumer có thể nhận duplicate không? Idempotency key nằm ở đâu?
- Có cần transaction đồng bộ giữa broker và database hay nên dùng outbox/inbox?
- Ai quản lý schema, versioning, retention, replay và dead-letter?

## 3. Các thành phần cốt lõi của Spring Integration

### 3.1. Message và header

Spring Integration truyền dữ liệu dưới dạng `Message<T>`:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<ReservationConfirmed> message =
        MessageBuilder.withPayload(event)
                .setHeader("tenantId", event.tenantId())
                .setHeader("correlationId", correlationId)
                .setHeader("eventType", "ReservationConfirmed")
                .build();
~~~

Một message gồm:

- **Payload:** dữ liệu chính, ví dụ object Java, JSON string, byte array hoặc file reference.
- **Headers:** metadata phục vụ routing, correlation, reply, content type, timestamp và transport adapter.

Không đưa secret, access token hoặc dữ liệu nhạy cảm vào header. Header có thể được log, copy sang transport hoặc hiển thị trong tracing. Chỉ mang metadata cần thiết; tenant identity phải được xác thực ở boundary, không tin header do client tùy ý gửi lên.

### 3.2. MessageChannel

Channel quyết định cách message đi từ producer tới consumer. Một số channel phổ biến:

| Channel | Semantics chính | Khi dùng |
| --- | --- | --- |
| `DirectChannel` | Gọi subscriber trong cùng thread, thường load-balance giữa subscribers | Flow đơn giản, cần call stack và transaction context đồng bộ |
| `PublishSubscribeChannel` | Phát message tới nhiều subscriber | Fan-out trong cùng application |
| `QueueChannel` | Lưu message trong queue nội bộ; consumer nhận sau | Tách producer/consumer và tạo buffer trong process |
| `ExecutorChannel` | Gửi xử lý qua task executor | Tách thread, tăng concurrency có kiểm soát |
| `PriorityChannel` | Queue nội bộ có thứ tự ưu tiên | Ưu tiên công việc trong phạm vi process |

`QueueChannel` là queue nội bộ của application process, không phải SQS, Service Bus, Pub/Sub hay Kafka. Khi process dừng, message trong queue nội bộ có thể mất nếu không có persistent message store được cấu hình. Không dùng channel trong memory thay cho broker bền vững.

### 3.3. Endpoint và handler

Endpoint nối channel với một hành động:

- **Service activator:** gọi method/service để xử lý payload.
- **Transformer:** đổi payload hoặc header.
- **Filter:** quyết định message có được đi tiếp không.
- **Router:** chọn channel đích theo điều kiện.
- **Splitter:** chia một message thành nhiều message.
- **Aggregator:** gom các message liên quan thành một kết quả.
- **Bridge:** nối hai channel.
- **Inbound adapter:** nhận dữ liệu từ hệ thống bên ngoài và đưa vào flow.
- **Outbound adapter:** gửi message ra hệ thống bên ngoài.
- **Gateway:** cung cấp interface gọi request/reply hoặc command/reply từ application code.

Adapter thường là một chiều; gateway thường cung cấp tương tác request/reply. Chọn đúng loại endpoint để thể hiện semantics và timeout rõ ràng.

### 3.4. IntegrationFlow và Java DSL

Java DSL cho phép khai báo flow bằng builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class ReservationFlowConfiguration {

    @Bean
    IntegrationFlow reservationFlow(ReservationHandler handler) {
        return IntegrationFlow.from("reservation.input")
                .transform(String.class, String::trim)
                .filter(String.class, payload -> !payload.isBlank())
                .transform(String.class, payload ->
                        new ReservationCommand(payload))
                .handle(handler, "process")
                .get();
    }
}
~~~

`IntegrationFlow.from("reservation.input")` nhận message từ channel có tên đó. Các endpoint tiếp theo nối thành pipeline. `handle(handler, "process")` gọi method của handler; handler có thể trả kết quả để flow tiếp tục hoặc trả `void` khi kết thúc.

Một flow tốt nên có tên rõ theo use case, chia thành các subflow khi có nhánh phức tạp, và giữ logic nghiệp vụ trong service có thể test độc lập.

### 3.5. Dependency và tương thích phiên bản

Với Spring Boot, starter cơ bản thường là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Starter đưa Spring Integration core vào ứng dụng; module test cung cấp tiện ích kiểm thử flow/endpoint. Dùng dependency management của Spring Boot để giữ Spring Framework, Spring Integration và Spring Integration Test tương thích. Không tự override version một module Integration riêng lẻ nếu chưa kiểm tra release train. Cloud connector là dependency riêng, chọn theo provider/service và phiên bản đang dùng; không thêm mọi connector vào classpath chỉ để dự phòng.

## 4. Xây dựng flow tích hợp theo từng bước

### 4.1. Khai báo message channel

Có thể khai báo channel bằng bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class IntegrationChannelConfiguration {

    @Bean("reservation.input")
    MessageChannel reservationInput() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel reservationWorkQueue() {
        return new QueueChannel(500);
    }
}
~~~

Khi dùng `DirectChannel`, subscriber xử lý trong thread gửi message. Nếu handler lỗi, exception có thể quay về caller. Với `QueueChannel`, producer gửi message vào buffer; consumer phải poll hoặc subscribe theo cách phù hợp. Queue có capacity hữu hạn giúp tránh buffer tăng vô hạn trong process, nhưng khi đầy, `send()` có thể chờ hoặc thất bại tùy timeout/configuration.

### 4.2. Transformer và filter

Transformer chuyển payload:

~~~java
@Bean
IntegrationFlow normalizeReservationFlow() {
    return IntegrationFlow.from("reservation.raw")
            .transform(String.class, String::trim)
            .transform(String.class, String::toUpperCase)
            .channel("reservation.normalized")
            .get();
}
~~~

Filter loại message không đáp ứng điều kiện:

~~~java
@Bean
IntegrationFlow validReservationFlow() {
    return IntegrationFlow.from("reservation.normalized")
            .filter(String.class, payload -> payload.startsWith("RES-"),
                    spec -> spec.discardChannel("reservation.invalid"))
            .channel("reservation.valid")
            .get();
}
~~~

Discard channel hữu ích để đưa message bị loại vào luồng audit hoặc quarantine. Không bỏ message âm thầm khi đó là lỗi dữ liệu cần được xử lý.

### 4.3. Router theo nội dung

Router gửi message tới channel khác nhau:

~~~java
@Bean
IntegrationFlow routeReservationFlow() {
    return IntegrationFlow.from("reservation.valid")
            .route(String.class,
                    payload -> payload.startsWith("RES-VIP")
                            ? "reservation.priority"
                            : "reservation.standard")
            .get();
}
~~~

Trong production, route theo thuộc tính domain/header đã được xác thực và có danh sách channel đích xác định. Cần cấu hình default route hoặc error path cho giá trị không nhận diện; không tạo channel động vô hạn từ input bên ngoài.

### 4.4. Splitter và aggregator

Splitter chia một batch thành nhiều message:

~~~java
@Bean
IntegrationFlow splitImportFlow() {
    return IntegrationFlow.from("reservation.batch")
            .split()
            .channel("reservation.item")
            .get();
}
~~~

Aggregator gom các kết quả có chung correlation key:

~~~java
@Bean
IntegrationFlow aggregateReservationFlow() {
    return IntegrationFlow.from("reservation.result")
            .aggregate(spec -> spec
                    .correlationStrategy(message ->
                            message.getHeaders().get("batchId"))
                    .releaseStrategy(group ->
                            group.size() >= 3))
            .channel("reservation.batch.completed")
            .get();
}
~~~

Ví dụ chỉ minh họa nguyên tắc. Aggregator production cần định nghĩa release strategy theo số lượng kết quả mong đợi, timeout/expiry, group capacity, partial result và cách xử lý message đến trễ. Nếu group không bao giờ đủ điều kiện release, message có thể giữ state trong memory/store lâu dài. Cấu hình message group store, discard/reaper và persistence phù hợp với mức độ quan trọng của flow.

### 4.5. Service activator và application service

Handler nên gọi use case/service:

~~~java
import org.springframework.stereotype.Component;

@Component
public class ReservationHandler {

    private final ReservationApplicationService applicationService;

    public ReservationHandler(
            ReservationApplicationService applicationService) {
        this.applicationService = applicationService;
    }

    public void process(ReservationCommand command) {
        applicationService.process(command);
    }
}
~~~

Với ví dụ này, command có thể là một record đơn giản:

~~~java
public record ReservationCommand(String reservationId) {
}
~~~

Không để handler chứa toàn bộ validation nghiệp vụ, pricing, authorization hay transaction orchestration. Integration layer chuyển đổi protocol/message thành command; application service thực thi use case theo quy tắc của hệ thống.

## 5. Gateway và request/reply

### 5.1. Khi nào dùng Messaging Gateway?

Gateway giúp application code gọi flow qua interface:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "reservation.command")
public interface ReservationCommandGateway {

    @Gateway(requestChannel = "reservation.command")
    ReservationResult confirm(ReservationCommand command);
}
~~~

Flow xử lý command và trả response:

~~~java
@Bean
IntegrationFlow reservationCommandFlow(
        ReservationApplicationService applicationService) {
    return IntegrationFlow.from("reservation.command")
            .handle(ReservationCommand.class,
                    (command, headers) -> applicationService.confirm(command))
            .get();
}
~~~

Gateway phù hợp với request/reply có deadline. Nếu flow đi qua broker bất đồng bộ, không nên giữ HTTP request mở để đợi message reply không giới hạn. Dùng correlation ID và callback/future hoặc trả `202 Accepted` kèm operation ID nếu công việc kéo dài.

### 5.2. Timeout và reply channel

Request/reply cần xác định:

- Thời gian chờ response.
- Correlation ID để ghép reply với request.
- Hành vi khi timeout: hủy, trả trạng thái pending hay truy vấn lại.
- Reply channel và cleanup correlation state.
- Điều gì xảy ra nếu reply tới sau timeout.

Timeout không chứng minh xử lý ở remote system đã thất bại. Request có thể đã được xử lý nhưng response bị trễ hoặc thất lạc. Nếu caller retry, command cần idempotency key.

## 6. Kết nối managed cloud services

### 6.1. Ba lớp trong cloud integration flow

Một flow kết nối cloud nên tách ba lớp:

1. **Transport adapter:** nhận/gửi message qua SQS, SNS, EventBridge, Azure Service Bus, Event Hubs, Google Pub/Sub hoặc API khác.
2. **Integration flow:** transform, validate envelope, route, enrich, retry và mapping lỗi.
3. **Application/domain service:** xử lý nghiệp vụ và persistence.

Cloud adapter cần quản lý authentication, Region/endpoint, acknowledgment, visibility/lock duration, batch size và provider-specific error. Flow không nên giả định các broker có cùng delivery, ordering hoặc settlement semantics.

### 6.2. AWS: SQS/SNS/EventBridge

Với AWS, có thể dùng AWSpring module phù hợp, Spring Integration AWS adapter nếu version dự án hỗ trợ, hoặc bridge nhỏ dùng AWS SDK v2. Ví dụ inbound từ queue nên chuyển message sang channel sau khi adapter đã xử lý nhận message/ack theo contract của listener.

Mẫu bridge đơn giản:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class CloudMessageBridge {

    private final MessageChannel reservationInput;

    public CloudMessageBridge(
            @Qualifier("reservation.input") MessageChannel reservationInput) {
        this.reservationInput = reservationInput;
    }

    public void accept(String body, String providerMessageId) {
        reservationInput.send(
                MessageBuilder.withPayload(body)
                        .setHeader("providerMessageId", providerMessageId)
                        .setHeader("sourceSystem", "aws-sqs")
                        .build());
    }
}
~~~

Listener/adapter cụ thể gọi `accept()` sau khi nhận message. Việc ack/delete message phải theo adapter acknowledgment mode: không xóa message trước khi flow đạt trạng thái xử lý được xem là thành công. Nếu bridge chỉ `send()` vào DirectChannel, xử lý downstream diễn ra đồng bộ trong cùng call stack; nếu channel bất đồng bộ, cần cơ chế xác nhận sau khi xử lý bền vững chứ không ack ngay sau khi enqueue vào memory.

Với outbound, handler có thể gọi `SqsClient.sendMessage`, `SnsClient.publish` hoặc `EventBridgeClient.putEvents`. Nếu gửi batch EventBridge, phải kiểm tra từng entry result; HTTP 200 không có nghĩa mọi event đều được chấp nhận.

### 6.3. Azure: Service Bus và Event Hubs

Azure Service Bus có queue/topic subscription và settlement như complete, abandon, defer, dead-letter; lock duration và lock renewal ảnh hưởng cách xử lý message lâu. Event Hubs là event streaming platform với partition/offset semantics, phù hợp ingest stream lớn hơn là queue command thông thường.

Dùng Azure Spring integration hoặc Spring Integration adapter nếu phiên bản đang dùng hỗ trợ đúng operation. Nếu cần bridge qua Azure SDK, giữ `ServiceBusReceivedMessageContext` hoặc receiver settlement ở transport adapter và chỉ complete message khi flow đã xử lý thành công theo policy. Không hoàn tất message ngay sau khi gửi vào channel nội bộ in-memory nếu channel có thể mất khi process crash.

### 6.4. Google Cloud: Pub/Sub

Google Cloud Pub/Sub có subscription, acknowledgment deadline, lease extension, retry policy và dead-letter topic. Ordering chỉ được bảo đảm khi bật ordering và tuân thủ ordering key/region semantics. Dùng Spring Cloud GCP Pub/Sub integration hoặc adapter tương thích với version dự án; nếu dùng Google Cloud client trực tiếp, bridge payload và metadata sang Spring Message.

Ack cần gắn với kết quả xử lý bền vững. Nếu consumer ack trước khi transaction DB commit, crash có thể làm mất message. Nếu ack sau commit nhưng mất ack response, message có thể được redeliver; idempotency vẫn bắt buộc.

### 6.5. So sánh semantics broker

| Khía cạnh | Amazon SQS | Azure Service Bus | Google Pub/Sub |
| --- | --- | --- | --- |
| Cơ chế nhận | Receive + visibility timeout | Receive + message lock | Pull/push subscription + ack deadline |
| Hoàn tất | Delete message / acknowledgment theo adapter | Complete/settle message | Acknowledge |
| Retry/redelivery | Visibility timeout và redrive policy | Abandon/lock expiry và delivery count | Nack/ack deadline expiry và retry policy |
| Dead-letter | DLQ qua redrive policy | Dead-letter queue | Dead-letter topic khi cấu hình |
| Ordering | FIFO queue theo message group | Session/order semantics theo entity | Ordering key khi bật tính năng |
| Duplicate | Có thể redeliver | Có thể redeliver | Có thể redeliver |
| Giới hạn | Theo queue type/Region/quota | Theo tier/entity/quota | Theo quota/ordering configuration |

Tên gọi và cấu hình cụ thể thay đổi theo SDK/adapter. Luôn kiểm tra docs theo phiên bản và loại entity đang dùng. Không giả định adapter Spring tự làm giống nhau mọi hành vi ack, retry, ordering và DLQ.

## 7. Chọn channel, concurrency và transaction boundary

### 7.1. Đồng bộ hay bất đồng bộ?

Channel ảnh hưởng trực tiếp tới execution model:

- `DirectChannel` gọi subscriber trong thread gửi message. Lỗi handler có thể quay về caller; transaction thread-local thường vẫn hiện diện trong call stack.
- `ExecutorChannel` chuyển xử lý sang executor. Thread context không tự truyền đầy đủ; transaction đang mở ở thread gửi không tự bao trùm công việc ở thread nhận.
- `QueueChannel` giữ message trong buffer nội bộ, tách thời điểm gửi và nhận. Queue cần consumer/poller và giới hạn capacity.
- `PublishSubscribeChannel` fan-out tới nhiều subscriber. Nếu subscriber xử lý song song hoặc độc lập, một nhánh lỗi không có nghĩa các nhánh khác rollback.

Chọn synchronous flow khi cần response ngay, tải nhỏ và dependency ổn định. Chọn asynchronous flow khi cần tách producer/consumer, buffer có giới hạn hoặc xử lý nền. Với công việc quan trọng cần sống qua restart, lưu message ở broker hoặc database trước khi chuyển qua channel nội bộ.

### 7.2. Poller và inbound polling

Một số nguồn không push message mà cần poll theo lịch. Spring Integration hỗ trợ poller cho inbound adapter và pollable channel:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Bean
IntegrationFlow scheduledImportFlow(ExternalRecordSource source) {
    return IntegrationFlow
            .from(source,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(10))
                                    .maxMessagesPerPoll(20)))
            .handle("importHandler", "process")
            .get();
}
~~~

Ví dụ minh họa poller ở mức Integration DSL; adapter thực tế phải cung cấp source tương thích và cấu hình error handling phù hợp. `maxMessagesPerPoll` giới hạn số message lấy trong một lần poll, không phải giới hạn tổng số message của hệ thống.

Poll interval, batch size và concurrency cần dựa trên quota nguồn, latency và tốc độ downstream. Poll quá nhanh gây request thừa; poll quá chậm tăng thời gian chờ và backlog. Với API rate-limited, thêm backoff khi nhận throttling và tránh nhiều replica cùng poll một nguồn không có cơ chế phân chia công việc.

### 7.3. Backpressure và bounded concurrency

Không để flow tạo vô hạn task hoặc queue. Đặt giới hạn:

- Queue capacity hoặc broker prefetch/receive batch.
- Executor core/max pool size và bounded task queue.
- Số message in-flight theo partition/tenant.
- Timeout cho API downstream.
- Bulkhead riêng cho dependency chậm.
- Admission control hoặc pause/resume khi backlog vượt ngưỡng.

Nếu tốc độ nhận lớn hơn tốc độ xử lý trong thời gian dài, tăng thread chỉ chuyển vấn đề thành cạn connection, memory hoặc quota downstream. Theo dõi queue depth, executor active/rejected tasks và consumer lag để quyết định scale hoặc giảm tốc độ nhận.

### 7.4. Transaction boundary không tự lan qua mọi channel

`DirectChannel` thường giữ cùng thread; nhưng transaction chỉ bao phủ resource được transaction manager quản lý. Gửi message đến cloud broker và ghi database không tự trở thành một distributed transaction chỉ vì nằm trong cùng IntegrationFlow.

Với channel bất đồng bộ, executor hoặc broker boundary, không dựa vào transaction thread-local của producer. Hãy xác định transaction ở handler/service nơi database operation diễn ra; commit trước khi ack broker theo semantics adapter. Khi cần phát event cùng lúc với DB commit, dùng transactional outbox thay vì giả định một transaction bao trùm cả hai hệ thống.

## 8. Error handling, retry và dead-letter

### 8.1. Error channel

Spring Integration có thể chuyển lỗi phát sinh trong flow tới error channel. Với message-driven endpoint, lỗi có thể được bọc trong `ErrorMessage` và mang `MessagingException` chứa failed message/endpoint.

Có thể cấu hình error flow riêng:

~~~java
@Bean
IntegrationFlow reservationErrorFlow(ReservationErrorHandler errorHandler) {
    return IntegrationFlow.from("errorChannel")
            .handle(errorHandler, "handle")
            .get();
}
~~~

Ví dụ minh họa việc có handler riêng; trong ứng dụng thực tế, default error channel, executor và endpoint scope cần được kiểm tra. Không giả định mọi exception từ broker listener đều tự động đến cùng một error channel: adapter có thể có error handler riêng, callback riêng hoặc yêu cầu exception propagate để broker redeliver.

Error handler nên phân loại lỗi:

- Validation/schema lỗi vĩnh viễn: quarantine hoặc dead-letter, không retry liên tục.
- Permission/configuration lỗi: cảnh báo và dừng retry nhanh.
- Throttling/network/service unavailable: retry có giới hạn, backoff và jitter.
- Database transient failure: retry theo transaction policy và deadline.
- Bug lập trình: giữ stack trace/correlation ID, alert và đưa message vào trạng thái cần điều tra.

### 8.2. Retry có giới hạn

Spring Integration hỗ trợ retry advice cho endpoint thông qua Spring Retry hoặc cơ chế retry tương ứng phiên bản. Ví dụ cấu hình ý tưởng:

~~~java
@Bean
IntegrationFlow publishReservationFlow(
        ReservationPublisher publisher) {
    return IntegrationFlow.from("reservation.to.publish")
            .handle(publisher, "publish",
                    endpoint -> endpoint.advice(retryAdvice()))
            .get();
}
~~~

`retryAdvice()` cần được khai báo với retry policy, backoff, exception classifier và recovery callback phù hợp. Không sao chép một policy chung cho mọi endpoint: API validation, permission, throttling và timeout có thể có retryability khác nhau.

Quy tắc thực tế:

1. Chỉ retry lỗi tạm thời.
2. Giới hạn attempts và tổng thời gian retry.
3. Dùng exponential backoff có jitter.
4. Tôn trọng `Retry-After` hoặc provider throttling guidance khi có.
5. Không retry đồng thời ở SDK, Integration advice và broker mà không tính tổng attempts.
6. Sau khi hết retry, ghi nhận trạng thái và chuyển dead-letter/review.

### 8.3. Retry của SDK và retry của broker

Có thể có nhiều tầng retry: SDK HTTP retry, Integration endpoint retry và broker redelivery. Nếu mỗi tầng đều có 3 lần thử, một message có thể gây nhiều request hơn dự kiến. Hãy xác định tầng nào chịu trách nhiệm retry loại lỗi nào:

| Tầng | Trách nhiệm phù hợp |
| --- | --- |
| SDK client | Retry lỗi transport/service tạm thời theo policy API |
| Integration endpoint | Retry lỗi xử lý tại handler khi thao tác có thể lặp an toàn |
| Broker | Redelivery khi consumer không ack/complete hoặc visibility/lock hết hạn |
| Outbox worker | Retry publish sau khi DB đã ghi event bền vững |
| Consumer inbox | Chống duplicate và ngăn side effect lặp |

Ghi số attempt theo từng tầng vào metric/log để điều tra retry storm.

### 8.4. Dead-letter và quarantine

DLQ là nơi giữ message đã vượt quá retry policy hoặc bị từ chối theo rule. Quarantine có thể là queue riêng, database table hoặc object storage có quyền truy cập hạn chế.

Mỗi dead-letter record nên có:

- Message ID và business event ID.
- Source broker/queue/subscription và thời điểm nhận.
- Error category/code và endpoint thất bại.
- Attempt count, correlation ID và trace ID.
- Payload hoặc pointer tới payload đã mã hóa, theo retention policy.
- Trạng thái xử lý lại, người/automation thực hiện và kết quả.

Không replay mù toàn bộ DLQ vào production. Sửa nguyên nhân trước, xác minh schema/version, giới hạn tốc độ replay và bảo đảm consumer idempotent.

## 9. Idempotency, ordering và transactional outbox

### 9.1. Vì sao phải giả định message có thể bị gửi lại?

Hầu hết managed broker phổ biến dùng delivery ít nhất một lần trong nhiều cấu hình. Consumer có thể nhận lại message khi:

- Xử lý xong nhưng process crash trước khi ack/complete.
- Ack response bị mất trên mạng.
- Lock/visibility/ack deadline hết hạn khi handler còn chạy.
- Broker redeliver sau lỗi tạm thời.
- Producer retry vì timeout nhưng không biết lần gửi đầu đã được chấp nhận hay chưa.

Vì vậy, không dùng việc broker cấp một message ID làm bảo đảm nghiệp vụ exactly-once. Cần có business event ID ổn định do producer tạo, ví dụ `eventId`, `commandId` hoặc `reservationId + eventVersion`.

### 9.2. Consumer inbox/deduplication

Một bảng inbox có unique constraint giúp ngăn side effect nghiệp vụ chạy hai lần:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(120) NOT NULL,
    event_id      VARCHAR(120) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong cùng transaction với cập nhật nghiệp vụ, consumer insert event ID:

~~~java
@Transactional
public void handle(ReservationConfirmed event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(
            "billing-consumer", event.eventId());

    if (!firstDelivery) {
        return;
    }

    billingService.createChargeIntent(event.reservationId());
}
~~~

`insertIfAbsent` phải dựa trên unique constraint và trả false khi khóa đã tồn tại. Không thực hiện kiểu check-then-insert bằng hai query tách rời vì hai consumer đồng thời có thể cùng thấy chưa tồn tại. Nếu side effect gọi hệ thống ngoài, transaction DB không bao trùm API đó; truyền idempotency key tới API đích hoặc ghi thêm outbox command để xử lý riêng.

Ack message sau khi transaction đã commit thành công. Nếu ack thất bại sau commit, message có thể redeliver nhưng inbox sẽ ngăn xử lý lại.

### 9.3. Ordering là thuộc tính của broker và key

Spring Integration không tự tạo ordering toàn cục cho mọi message. Ordering phụ thuộc broker, partition/session/message group và concurrency:

- SQS FIFO dùng message group ID để duy trì thứ tự trong group; các group khác nhau có thể xử lý song song.
- Azure Service Bus có session để gom message theo session ID và xử lý theo thứ tự trong session.
- Pub/Sub ordering cần bật ordering và dùng ordering key theo điều kiện của service.
- Kafka ordering theo partition; key quyết định message đi vào partition nào.

Nếu nghiệp vụ yêu cầu thứ tự theo reservation, tenant hoặc aggregate, hãy dùng key ổn định tương ứng. Đồng thời giới hạn concurrency theo key/partition và xác định cách xử lý message đến trễ hoặc retry làm thay đổi thứ tự hoàn tất.

### 9.4. Transactional outbox cho producer

Khi một transaction cập nhật database đồng thời cần phát event, không gọi broker trước/sau commit một cách tùy tiện. Có hai cửa sổ lỗi:

- Publish trước DB commit: event có thể được gửi nhưng transaction DB rollback.
- DB commit trước publish: process có thể crash và event không bao giờ được gửi.

Outbox ghi business change và event trong cùng DB transaction:

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

DDL trên dùng kiểu `JSONB` và `TIMESTAMPTZ` của PostgreSQL; nếu dùng engine khác, thay kiểu dữ liệu và cú pháp partial index theo database đó.

Trong application service:

~~~java
@Transactional
public void confirm(String reservationId) {
    Reservation reservation = reservationRepository.confirm(reservationId);

    ReservationConfirmed event = eventFactory.from(reservation);
    outboxRepository.insert(event.eventId(), reservation.id(),
            "ReservationConfirmed", serialize(event), event.occurredAt());
}
~~~

Worker đọc outbox rồi đưa event qua Integration flow hoặc outbound adapter. Claim row bằng lease hoặc lock ngắn; không giữ transaction/row lock trong lúc chờ gọi cloud broker. Sau khi broker xác nhận publish, đánh dấu `published_at`. Nếu worker crash sau publish nhưng trước update, event có thể gửi lại; consumer inbox xử lý duplicate.

Outbox cung cấp khả năng khôi phục ý định phát event sau DB commit; nó không biến broker thành exactly-once. Với nhiều worker, dùng `FOR UPDATE SKIP LOCKED` hoặc lease có timeout, có cơ chế reclaim record bị worker chết giữ lại.

### 9.5. Không nhầm ack với business commit

Transport adapter nên complete/delete/ack message sau khi downstream xử lý bền vững. Với flow đồng bộ qua DirectChannel, adapter có thể nhận exception từ handler và quyết định không ack. Với flow bất đồng bộ, `send()` thành công có thể chỉ có nghĩa message đã vào queue nội bộ; nó chưa chứng minh DB commit hoặc side effect đã hoàn tất.

Nếu cần tách transport listener và flow async, hãy chuyển message vào broker nội bộ bền vững hoặc persist vào inbox/work table trước khi ack nguồn. Nếu chỉ enqueue vào memory rồi ack, process crash có thể làm mất message.

## 10. Schema, payload và bảo mật

### 10.1. Envelope và versioning

Nên thống nhất envelope cho message liên hệ thống:

~~~json
{
  "eventId": "evt-01J...",
  "eventType": "ReservationConfirmed",
  "schemaVersion": 2,
  "occurredAt": "2026-11-24T10:00:00Z",
  "producer": "reservation-service",
  "correlationId": "corr-...",
  "tenantId": "tenant-a",
  "data": {
    "reservationId": "res-1001",
    "propertyId": "property-21"
  }
}
~~~

Envelope giúp consumer định tuyến và kiểm tra version trước khi parse payload nghiệp vụ. Không dùng Java class name làm schema contract xuyên service. Có thể dùng JSON Schema, Avro hoặc Protobuf và quản lý compatibility theo quy trình của tổ chức.

Khi thêm field, ưu tiên thay đổi backward-compatible. Khi đổi kiểu field, ý nghĩa hoặc requiredness, tăng schema version và lên kế hoạch rollout producer/consumer theo thứ tự tương thích.

### 10.2. Payload nhỏ, tham chiếu object lớn

Broker có giới hạn kích thước message theo dịch vụ và tier. Không gửi file lớn hoặc toàn bộ document trong message nếu không cần. Đưa object lên S3/Blob/GCS rồi gửi locator đã được kiểm soát, checksum, content type và version/generation. Consumer tải object bằng workload identity với quyền tối thiểu.

Locator không phải authorization. Consumer phải kiểm tra tenant mapping và bucket/container allow-list trước khi truy cập; không tin URI do producer bên ngoài tùy ý cung cấp nếu producer chưa được xác thực.

### 10.3. Identity và least privilege

Mỗi adapter chỉ cần quyền cho operation của nó:

- AWS producer: quyền publish đúng SNS topic, EventBridge bus hoặc queue target.
- AWS consumer: quyền receive/delete/visibility đúng SQS queue; không cần quyền quản trị queue.
- Azure producer/consumer: role phù hợp trên đúng Service Bus namespace/entity.
- Google Pub/Sub publisher/subscriber: role publish hoặc subscribe trên đúng topic/subscription.

Ưu tiên workload identity: IAM role, Azure Managed Identity/Workload Identity hoặc Google Workload Identity/Application Default Credentials. Không nhúng client secret, service account key, SAS token hoặc cloud access key trong payload/header/application source.

### 10.4. Tenant boundary và chống giả mạo header

Không lấy tenant ID từ header message làm nguồn cấp quyền duy nhất. Xác thực producer, kiểm tra claim/tenant mapping ở boundary, rồi gắn tenant context đã xác thực vào message. Với multi-tenant queue/topic, quyết định cách phân vùng:

- Queue/topic riêng theo tenant hoặc nhóm tenant.
- Shared broker entity nhưng có tenant key và authorization trong application.
- Partition/session/ordering key theo tenant khi cần isolation/order.

Log và metric không nên tạo cardinality vô hạn từ tenant ID hoặc message ID. Mask hoặc hash identifier khi phù hợp; không log payload có PII/payment data.

## 11. Kiểm thử Spring Integration flow

### 11.1. Test flow bằng channel nội bộ

Có thể kiểm tra flow mà không cần cloud broker bằng channel test. Trước hết, khai báo output channel dạng pollable để test có thể nhận message:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
class ReservationTestFlowConfiguration {

    @Bean("reservation.test.output")
    QueueChannel reservationOutput() {
        return new QueueChannel(10);
    }

    @Bean("reservation.test.input")
    MessageChannel reservationTestInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow normalizeForTestFlow() {
        return IntegrationFlow.from("reservation.test.input")
                .transform(String.class, String::trim)
                .channel("reservation.test.output")
                .get();
    }
}
~~~

Trong integration test Spring context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Import(ReservationTestFlowConfiguration.class)
class ReservationFlowTest {

    @Autowired
    @Qualifier("reservation.test.input")
    MessageChannel input;

    @Autowired
    @Qualifier("reservation.test.output")
    PollableChannel output;

    @Test
    void trimsIncomingPayload() {
        input.send(MessageBuilder.withPayload("  RES-1001  ").build());

        Message<?> result = output.receive(1000);

        assertThat(result).isNotNull();
        assertThat(result.getPayload()).isEqualTo("RES-1001");
    }
}
~~~

Test này kiểm tra flow wiring và transform thực tế mà không cần broker. Tên channel trong test phải khớp với channel bean/DSL flow đã khai báo. Nếu flow có nhiều nhánh, thêm test cho mỗi route, discard path và error path.

### 11.2. Kiểm thử endpoint với mock

Mock SDK client hoặc provider adapter để xác minh:

- Payload và header mapping đúng.
- Router chọn đúng channel.
- Filter discard message không hợp lệ.
- Exception được phân loại đúng.
- Partial failure được xử lý theo entry.
- Ack chỉ xảy ra sau khi handler/transaction hoàn tất.
- Retry có giới hạn và không retry lỗi permanent.
- Duplicate event ID không tạo side effect lần hai.

Tách unit test application service khỏi test wiring của IntegrationFlow. Mock broker API không chứng minh broker thật có cùng semantics lock/visibility/ack.

### 11.3. Broker emulator và contract test

LocalStack có thể hỗ trợ một số AWS API như SQS/SNS/EventBridge. Azure Service Bus và Google Pub/Sub có emulator hoặc môi trường local phù hợp cho một số use case. Kiểm tra giới hạn từng emulator: IAM, policy, ordering, DLQ, retry và quota có thể không hoàn toàn giống cloud thật.

Contract/staging test cần xác minh:

1. Workload identity được cấp đúng quyền.
2. Adapter nhận đúng message envelope và metadata.
3. Ack/complete/delete được thực hiện sau commit theo policy.
4. Retry/redelivery và DLQ hoạt động như mong đợi.
5. Ordering/partition/session được cấu hình đúng.
6. Consumer deduplicate khi cùng event ID được gửi lại.
7. Metric và tracing có correlation xuyên transport boundary.

Không chạy load test hoặc thử throttling trên production nếu chưa có ngân sách, giới hạn concurrency và kế hoạch dừng.

## 12. Observability và vận hành

### 12.1. Trace một message xuyên flow

Mỗi message nên có correlation ID hoặc trace context để liên kết:

- Nhận từ broker/API.
- Qua transformer/router/filter.
- Gọi service nghiệp vụ/database.
- Publish sang broker hoặc API tiếp theo.
- Ack/complete hoặc dead-letter.

Spring Integration có thể tích hợp với Micrometer Observation/metrics theo version. Kiểm tra instrumentation thực tế và propagate trace context qua broker headers theo chuẩn đang dùng. Không tự tạo trace ID mới ở từng endpoint nếu cần theo dõi cùng một business operation.

### 12.2. Metric cần theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| Messages received/sent | Throughput đầu vào/đầu ra |
| Processing duration p50/p95/p99 | Latency theo endpoint/use case |
| Queue depth / consumer lag | Backlog đang tăng hay giảm |
| In-flight / active handler | Số message đang xử lý |
| Retry count / redelivery count | Dependency lỗi hoặc policy quá chặt |
| DLQ depth / oldest message age | Message bị kẹt cần điều tra |
| Handler error rate theo category | Phân biệt validation, permission, throttling, timeout |
| Executor active/rejected tasks | Concurrency hoặc queue nội bộ quá tải |

Không chỉ theo dõi tổng số lỗi. Một queue có throughput bình thường nhưng oldest message age tăng có thể báo consumer không theo kịp hoặc một partition bị kẹt.

### 12.3. Log an toàn và runbook

Log nên có event ID, correlation ID, endpoint/flow name, broker entity, attempt count, duration và error category. Không log credentials, SAS/presigned URL, raw payload nhạy cảm hoặc toàn bộ message headers.

Runbook cần trả lời:

- Khi backlog tăng, giảm receive concurrency hay tăng worker?
- Khi throttling, giới hạn publish rate ở đâu?
- Khi DLQ tăng, cách xem mẫu message và phân loại lỗi?
- Ai được phép replay và theo dõi replay thế nào?
- Cách xử lý schema version không còn tương thích?
- Cách pause/resume endpoint khi dependency outage?
- Làm sao xác nhận không mất message sau deployment/restart?

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Message nhận nhiều lần | Ack thất bại, lock/visibility hết hạn hoặc consumer crash | Inbox/idempotency; điều chỉnh lock/visibility và thời gian xử lý |
| Message mất sau restart | Ack sau khi enqueue vào channel in-memory | Persist trước ack hoặc giữ flow đồng bộ tới commit |
| Backlog tăng liên tục | Producer nhanh hơn consumer, downstream chậm hoặc concurrency thấp | Theo dõi lag/latency, scale có giới hạn và backpressure |
| Retry storm | SDK, Integration và broker đều retry cùng lỗi | Phân quyền retry theo tầng, giới hạn attempts và jitter |
| DLQ tăng | Schema lỗi, permission, poison message hoặc target unavailable | Phân loại error, sửa nguyên nhân, replay có kiểm soát |
| Message sai thứ tự | Nhiều consumer/thread, partition/session key không đúng | Chọn ordering key và giới hạn concurrency theo group |
| Tenant xử lý nhầm dữ liệu | Tin header tenant do producer gửi | Xác thực identity và kiểm tra tenant mapping ở boundary |
| Flow bị block | Handler đồng bộ gọi API chậm hoặc thread pool cạn | Timeout, bulkhead, bounded executor và async boundary có chủ đích |
| Aggregator giữ message lâu | Release strategy không đạt hoặc timeout thiếu | Cấu hình group timeout, reaper, capacity và persistent store |
| Gateway timeout nhưng remote đã xử lý | Reply trễ/thất lạc sau khi command được thực thi | Idempotency key và trạng thái operation có thể truy vấn |

## 14. Checklist trước production

1. **Tool choice:** đã xác định Spring Integration giải quyết điều phối flow; Stream/SDK/workflow engine có phù hợp hơn không?
2. **Boundaries:** transport adapter, integration flow và application/domain service có trách nhiệm riêng.
3. **Message contract:** envelope, schema version, event ID, correlation ID và tenant context được định nghĩa.
4. **Channel semantics:** sync/async, buffer, capacity, executor và transaction context được hiểu rõ.
5. **Broker semantics:** ack, visibility/lock, ordering, redelivery, retention và DLQ được cấu hình theo provider.
6. **Error policy:** phân biệt lỗi permanent/transient, retry có giới hạn và quarantine có quy trình.
7. **Idempotency:** consumer inbox/deduplication bảo vệ side effect.
8. **Consistency:** outbox được dùng khi DB commit phải đi cùng ý định publish.
9. **Security:** workload identity và least privilege; không đưa secret vào message/header/log.
10. **Backpressure:** bounded queue, concurrency, timeout và rate limit.
11. **Testing:** unit, flow wiring, emulator và staging contract test.
12. **Operations:** metric, tracing, alert, DLQ replay và runbook.

## 15. Bài tập tự luyện

1. Với use case nhận ReservationConfirmed từ SQS, enrich dữ liệu và publish sang EventBridge, vẽ flow và phân định transport adapter, IntegrationFlow và application service.
2. Viết IntegrationFlow dùng transformer, filter, router và service activator; test từng nhánh bằng QueueChannel.
3. So sánh DirectChannel, QueueChannel, ExecutorChannel và PublishSubscribeChannel qua thread, buffer, failure propagation và durability.
4. Chuyển một use case gọi SDK trực tiếp thành adapter nhỏ; xác định khi nào flow cần nhiều endpoint thì Spring Integration có giá trị.
5. Thiết kế gateway request/reply với timeout, correlation ID và cách xử lý reply đến trễ.
6. Viết bridge cho một provider broker; giải thích chính xác thời điểm ack/complete/delete message.
7. Thiết kế retry policy cho throttling, timeout, schema validation và access denied; tránh nhân số lần thử qua nhiều tầng.
8. Tạo inbox table để cùng event ID không tạo side effect hai lần.
9. Thêm transactional outbox cho use case ghi database và phát event; mô phỏng crash sau publish nhưng trước khi đánh dấu published.
10. So sánh SQS, Azure Service Bus và Pub/Sub về ack, redelivery, ordering, DLQ và identity; trình bày phần nào flow có thể dùng chung và phần nào phụ thuộc provider.

**Tiêu chí hoàn thành:** người học chọn được Spring Integration cho bài toán điều phối message flow phù hợp, xây dựng flow Java DSL có channel/endpoint rõ ràng, kết nối ít nhất một cloud broker qua adapter, xử lý ack/retry/DLQ/idempotency đúng semantics và kiểm thử được luồng từ đầu vào tới đầu ra.

## Tài liệu tham khảo

- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): message, channel, endpoint, Java DSL, error handling và adapters.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): khai báo IntegrationFlow bằng Java.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): channel types và semantics.
- [Spring Integration — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): request/reply và gateway.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): error channel và exception flow.
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/): binder, functional model, consumer groups và partitioning.
- [Spring Cloud AWS Reference](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): tích hợp AWS theo phiên bản.
- [Azure Spring documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/): tích hợp Spring với Azure services.
- [Google Cloud Spring documentation](https://cloud.google.com/java/docs/spring): tích hợp Spring với Google Cloud.
- [AWS Prescriptive Guidance — Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html): dual-write và duplicate delivery.

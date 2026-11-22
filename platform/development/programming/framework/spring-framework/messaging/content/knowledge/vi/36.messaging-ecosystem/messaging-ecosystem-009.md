# Ranh giới giữa kiến thức Framework và cấu hình sản phẩm bên ngoài

Khi học Spring Messaging, rất dễ trộn lẫn ba loại kiến thức: API do Spring Framework cung cấp, khả năng do một dự án Spring khác bổ sung và cấu hình thuộc về broker hoặc sản phẩm bên ngoài. Chúng thường xuất hiện cùng nhau trong một ứng dụng, nhưng có chủ sở hữu, vòng đời phiên bản và cách kiểm thử khác nhau.

Ví dụ, một ứng dụng có thể dùng Spring Messaging để tạo message, Spring for Apache Kafka để gửi message đến Kafka, Spring Boot để tự động cấu hình producer và Kafka broker để lưu message theo retention policy. Cả bốn thành phần cùng tham gia một luồng xử lý, nhưng không thể coi mọi thuộc tính hoặc hành vi trong luồng đó là tính năng của Spring Framework.

Bài học này giúp xác định đúng ranh giới, chọn đúng tài liệu và biết phần nào cần kiểm thử ở cấp Framework, adapter, runtime hay sản phẩm bên ngoài.

## 1. Bốn lớp kiến thức thường gặp

Một ứng dụng messaging thường có thể được nhìn qua bốn lớp:

1. **Spring Framework:** các abstraction và API nền tảng như Message, MessageHeaders, MessageChannel, MessageHandler, MessageConverter, WebSocket/STOMP, RSocket và tích hợp JMS.
2. **Dự án Spring mở rộng:** các dự án xây trên Framework để cung cấp integration flow, broker adapter, binder hoặc tính năng chuyên biệt.
3. **Spring Boot và cấu hình ứng dụng:** auto-configuration, externalized configuration, property binding, starter và quản lý dependency.
4. **Sản phẩm/runtime bên ngoài:** Kafka, RabbitMQ, ActiveMQ, Artemis, broker cloud, schema registry, proxy, load balancer, Kubernetes và hệ thống lưu trữ.

Các lớp này có thể phối hợp với nhau nhưng không thay thế nhau. Spring Framework định nghĩa API và tích hợp ở mức ứng dụng; dự án Spring mở rộng cung cấp adapter hoặc abstraction bổ sung; Boot giảm công việc cấu hình; sản phẩm bên ngoài thực thi semantics và quản lý tài nguyên của chính nó.

## 2. Những gì thuộc Spring Framework

Spring Framework cung cấp các abstraction messaging dùng chung để ứng dụng không phải tự định nghĩa cấu trúc message và cách chuyển dữ liệu ở mọi nơi.

Một số thành phần quan trọng:

- **Message và MessageHeaders:** biểu diễn payload cùng metadata.
- **MessageBuilder:** tạo message và thiết lập headers.
- **MessageChannel:** abstraction gửi message đến một channel.
- **MessageHandler:** abstraction xử lý message.
- **MessageConverter:** chuyển đổi payload giữa object và dạng dữ liệu phù hợp.
- **MessageHeaderAccessor:** đọc và thao tác headers theo API có kiểm soát.
- **Spring WebSocket/STOMP:** hỗ trợ message qua WebSocket, destination mapping và broker integration.
- **RSocket integration:** hỗ trợ requester, responder, route và codec strategies.
- **JMS integration:** cung cấp các thành phần như JmsTemplate và listener container thông qua module Spring JMS.

Ví dụ một đoạn code chỉ dùng abstraction của Spring Messaging:

~~~java
Message<String> message = MessageBuilder
    .withPayload("order submitted")
    .setHeader("correlationId", "corr-100")
    .build();

MessageChannel channel = obtainChannel();
boolean accepted = channel.send(message);
~~~

Đoạn code này thể hiện hợp đồng message và thao tác gửi qua channel. Nó chưa cho biết channel được nối đến Kafka, RabbitMQ, JMS, một executor nội bộ hay một adapter khác. Cách triển khai cụ thể nằm ở lớp tích hợp.

Tài liệu Spring Framework phù hợp để trả lời các câu hỏi như:

- Message có payload và headers như thế nào?
- Headers có bất biến không?
- MessageChannel và MessageHandler có vai trò gì?
- MessageConverter được gọi ở đâu?
- Spring ánh xạ STOMP destination vào handler ra sao?
- RSocket route được khai báo và gọi như thế nào?
- JmsTemplate và listener container được sử dụng ra sao?

Không nên dùng tài liệu Framework để suy ra một thuộc tính cấu hình riêng của Kafka hoặc RabbitMQ.

## 3. Những gì thuộc các dự án Spring mở rộng

Một số khả năng messaging phổ biến nằm trong dự án Spring riêng, dù chúng sử dụng abstraction của Spring Framework.

| Dự án | Phạm vi chính | Ví dụ kiến thức |
|---|---|---|
| Spring Integration | Enterprise Integration Patterns và integration flow | channel adapter, router, transformer, filter, aggregator |
| Spring for Apache Kafka | Tích hợp ứng dụng Spring với Apache Kafka | KafkaTemplate, listener container, retry topic, transaction |
| Spring AMQP / Spring for RabbitMQ | Tích hợp Spring với AMQP và RabbitMQ | RabbitTemplate, listener container, exchange, binding |
| Spring Cloud Stream | Abstraction cho event-driven microservices qua binder | function binding, consumer group, partition, binder |
| Spring Batch | Xử lý batch và job | chunk, reader, writer, retry/skip trong batch step |

Các dự án này có thể dùng chung Message, MessageChannel hoặc các abstraction khác, nhưng API và cấu hình của chúng không tự động trở thành API lõi của Spring Framework.

Ví dụ:

- **KafkaTemplate** thuộc Spring for Apache Kafka.
- **RabbitTemplate** thuộc Spring AMQP.
- **IntegrationFlow** và DSL của integration flow thuộc Spring Integration.
- **Function binding** và binder configuration thuộc Spring Cloud Stream.
- **JmsTemplate** thuộc Spring Framework module Spring JMS.

Khi tìm một class hoặc property, hãy kiểm tra artifact và package thực tế. Tên bắt đầu bằng Spring không đủ để kết luận nó thuộc Spring Framework core.

## 4. Phân biệt Spring Framework với Spring Boot

Spring Boot là lớp hỗ trợ xây dựng và chạy ứng dụng Spring. Boot cung cấp auto-configuration, starter, externalized configuration và cơ chế binding properties.

Ví dụ các property sau thường thuộc auto-configuration của Spring Boot khi có starter tương ứng:

~~~properties
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.group-id=orders-service
spring.rabbitmq.host=localhost
spring.rabbitmq.port=5672
~~~

Đây không phải API cấu hình chung của Spring Framework. Nếu ứng dụng không dùng Spring Boot, các property này không tự động có ý nghĩa; ứng dụng phải tự tạo bean và cấu hình client hoặc adapter phù hợp.

Một số thành phần cần phân biệt:

- **Spring Framework Environment:** abstraction truy cập property sources và profiles.
- **Spring Boot Config Data:** cơ chế Boot nạp cấu hình từ application.properties, application.yaml, profile và nguồn cấu hình khác.
- **Spring Boot auto-configuration:** tự tạo bean khi dependency và điều kiện phù hợp.
- **Starter:** tập hợp dependency tiện dụng, không phải một runtime broker.
- **Externalized configuration:** đưa cấu hình theo môi trường ra khỏi code; cách nạp và binding cụ thể phụ thuộc Framework, Boot và thư viện tích hợp.

Khi viết tài liệu, hãy ghi rõ property thuộc prefix nào và yêu cầu dependency nào. Không gọi mọi property bắt đầu bằng spring là property của Spring Framework.

## 5. Phần nào thuộc sản phẩm bên ngoài?

Broker hoặc sản phẩm bên ngoài quyết định nhiều hành vi mà Framework chỉ cấu hình hoặc sử dụng thông qua client.

Ví dụ với Kafka:

- Topic, partition và replication factor.
- Retention time và retention size.
- Consumer group coordination.
- Broker-side quota.
- Log compaction.
- Replication và leader election.
- ACL và cơ chế bảo mật broker.
- Kích thước record và giới hạn request của broker.

Với RabbitMQ:

- Exchange, queue và binding.
- Queue durability và message persistence.
- Prefetch/QoS và acknowledgement.
- Dead-letter exchange.
- TTL, maximum queue length và overflow behavior.
- Quorum queue hoặc stream.
- User, vhost, permission và policy.

Với các broker khác, khái niệm và tên cấu hình có thể khác. Không sao chép tên property của một broker sang broker khác chỉ vì chúng cùng hỗ trợ messaging.

Spring adapter có thể cung cấp một API để cấu hình hoặc sử dụng tính năng, nhưng semantics cuối cùng vẫn chịu ảnh hưởng bởi broker version, client library, protocol và cấu hình triển khai.

## 6. Ví dụ phân loại một luồng Kafka

Giả sử một service nhận lệnh tạo đơn, xử lý nghiệp vụ và phát event OrderCreated.

| Thành phần | Chủ sở hữu | Trách nhiệm |
|---|---|---|
| Message payload và headers | Spring Messaging / ứng dụng | Biểu diễn dữ liệu và metadata |
| KafkaTemplate | Spring for Apache Kafka | Gửi record đến Kafka |
| Kafka producer client | Apache Kafka client | Thực hiện giao tiếp protocol với broker |
| Bootstrap servers | Cấu hình ứng dụng / Boot | Chỉ ra broker để client kết nối |
| Topic và partition | Kafka cluster | Lưu và phân phối record |
| Retention policy | Kafka broker | Quyết định thời gian hoặc dung lượng lưu record |
| Auto-configuration | Spring Boot | Tạo bean theo dependency và properties |
| Business event schema | Ứng dụng / schema governance | Định nghĩa cấu trúc và ý nghĩa event |

Ví dụ code gửi event qua Spring for Apache Kafka:

~~~java
@Service
class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {
        return kafkaTemplate.send(
            "orders.created.v1",
            event.orderId(),
            event
        );
    }
}
~~~

Đoạn code sử dụng API của Spring for Apache Kafka. Nó không tự tạo topic, không tự đặt retention policy và không bảo đảm schema được đăng ký trong một schema registry. Những phần đó phải được quản lý ở đúng lớp.

Nếu ứng dụng dùng Spring Boot, Boot có thể tự cấu hình KafkaTemplate từ properties và dependency. Nếu không dùng Boot, ứng dụng cần cấu hình producer factory và template bằng Java config hoặc cơ chế tương ứng.

## 7. Ví dụ phân loại một luồng RabbitMQ

Với RabbitMQ, ứng dụng có thể dùng Spring AMQP để gửi message:

~~~java
@Service
class BillingPublisher {

    private final RabbitTemplate rabbitTemplate;

    BillingPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    void publish(PaymentCaptured event) {
        rabbitTemplate.convertAndSend(
            "billing.events",
            "payment.captured",
            event
        );
    }
}
~~~

Trong ví dụ:

- RabbitTemplate thuộc Spring AMQP.
- Exchange và routing key được dùng trong mô hình AMQP.
- Exchange, queue và binding phải tồn tại hoặc được khai báo theo cơ chế provisioning phù hợp.
- Durability, acknowledgement, dead-letter và TTL phụ thuộc cấu hình queue, broker và listener.
- Object event được chuyển đổi qua message converter đã cấu hình.

Không thể suy luận rằng gọi convertAndSend là message đã được consumer xử lý thành công. Việc gửi, broker xác nhận, consumer nhận và nghiệp vụ commit là các mốc khác nhau. Test và metric cần phân biệt các mốc đó.

## 8. Ví dụ phân loại STOMP và RSocket trong Spring Framework

STOMP và RSocket là hai tích hợp có trong Spring Framework, nhưng semantics và cách cấu hình khác nhau.

### STOMP qua WebSocket

Spring WebSocket hỗ trợ application destination prefix và broker destination prefix:

~~~java
@Configuration
@EnableWebSocketMessageBroker
class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Application prefix định tuyến message đến controller; broker prefix định tuyến message đến broker được cấu hình. Nếu dùng simple broker, khả năng của nó khác một broker chuyên dụng hoặc broker relay.

Cấu hình STOMP destination mapping thuộc Spring Framework WebSocket support. Nhưng cấu hình broker ngoài, quyền truy cập, queue policy, persistence hoặc cluster topology thuộc sản phẩm broker tương ứng.

### RSocket

Spring Framework cung cấp requester và responder API:

~~~java
@Controller
class StatusController {

    @MessageMapping("system.status")
    Mono<ServerStatus> status() {
        return Mono.just(new ServerStatus("UP"));
    }
}
~~~

Route system.status được xử lý bởi responder. RSocket có interaction models như Request-Response, Request-Stream, Fire-and-Forget và Channel. Codec, data MIME type và metadata MIME type cũng là phần quan trọng của hợp đồng.

Nếu RSocket server chạy sau load balancer, proxy hoặc service mesh, cấu hình TLS, idle timeout, connection draining và routing ở hạ tầng có thể ảnh hưởng đến kết nối. Những thông số đó không phải tự động là thuộc tính của @MessageMapping hoặc RSocketRequester.

## 9. Đặt câu hỏi đúng để tìm đúng tài liệu

Khi gặp một vấn đề messaging, trước hết hãy xác định lớp đang sở hữu hành vi cần tìm.

| Câu hỏi | Nơi nên tra cứu trước |
|---|---|
| MessageHeaders có immutable không? | Spring Framework API |
| MessageChannel.send trả về gì? | Spring Framework API |
| Handler STOMP được ánh xạ từ destination ra sao? | Spring Framework WebSocket/STOMP |
| RSocketRequester thiết lập connection thế nào? | Spring Framework RSocket và RSocket Java |
| KafkaTemplate gửi record thế nào? | Spring for Apache Kafka |
| spring.kafka.consumer.* được bind ra sao? | Spring Boot Kafka auto-configuration |
| Consumer group rebalance hoạt động thế nào? | Apache Kafka documentation |
| Rabbit queue có TTL và dead-letter ra sao? | RabbitMQ documentation và Spring AMQP adapter |
| Function được bind vào broker nào? | Spring Cloud Stream documentation |
| Pod scale và secret được mount thế nào? | Kubernetes hoặc nền tảng triển khai |

Nếu câu trả lời liên quan đến nhiều lớp, hãy đọc tài liệu từng lớp và ghi rõ ranh giới. Ví dụ, Spring Kafka có thể cho biết cách khai báo listener, nhưng tài liệu Kafka mới là nguồn chuẩn về consumer group protocol và broker configuration.

## 10. Phân loại cấu hình theo nơi sở hữu

Mỗi cấu hình nên được ghi cùng chủ sở hữu, phạm vi và nơi áp dụng.

| Nhóm cấu hình | Ví dụ | Chủ sở hữu chính |
|---|---|---|
| Messaging abstraction | Message headers, channel, converter | Spring Framework |
| Transport integration | STOMP endpoint, RSocket route, JMS listener | Spring Framework hoặc adapter tương ứng |
| Adapter/client | KafkaTemplate, RabbitTemplate, listener factory | Dự án Spring tích hợp |
| Application binding | spring.kafka.*, spring.rabbitmq.* | Spring Boot khi dùng auto-configuration |
| Client runtime | Kafka producer acks, client retries, serializer | Client library và cấu hình ứng dụng |
| Broker runtime | Kafka retention, Rabbit queue policy | Sản phẩm broker |
| Deployment | DNS, port, TLS secret, replica, resource limit | Nền tảng triển khai |
| Business contract | Event name, schema, compatibility rule | Ứng dụng và quy trình governance |

Không nên đưa secret, password hoặc token vào tài liệu công khai hoặc ví dụ commit vào repository. Hãy mô tả tên biến môi trường hoặc secret reference và chỉ rõ cách cấp phát ở môi trường chạy.

Một property có thể được khai báo ở ứng dụng nhưng được diễn giải bởi client library. Một giá trị khác có thể được lưu trong broker và được broker áp dụng. Tài liệu cần nêu rõ nơi giá trị được đọc và nơi hành vi thực sự được thực thi.

## 11. Quản lý phiên bản và compatibility

Một ứng dụng messaging thường có nhiều phiên bản độc lập:

- Spring Framework.
- Spring Boot.
- Dự án tích hợp như Spring Kafka hoặc Spring AMQP.
- Kafka client hoặc RabbitMQ Java client.
- Broker server.
- Protocol hoặc serializer.
- Schema registry và schema format.

Không nâng cấp một thành phần mà không xem xét compatibility với các thành phần còn lại. Spring Boot quản lý dependency versions qua dependency management/BOM khi sử dụng đúng phiên bản; nếu override dependency, cần kiểm tra compatibility matrix và release notes.

Khi lập tài liệu triển khai, nên ghi:

1. Phiên bản Java.
2. Phiên bản Spring Boot nếu có.
3. Phiên bản Spring Framework thực tế.
4. Phiên bản Spring integration project.
5. Phiên bản client library.
6. Phiên bản broker server.
7. Phiên bản protocol hoặc schema format khi có liên quan.

Không ghi một ví dụ là “API hiện hành” nếu chưa xác định phiên bản. API builder, package, tên converter và property có thể thay đổi theo release.

Với schema message, versioning cần được quản lý độc lập với version của framework. Nâng cấp Spring không nhất thiết làm thay đổi schema nghiệp vụ; ngược lại, schema có thể cần version mới dù framework không đổi.

## 12. Kiểm thử theo từng lớp

Một test chỉ kiểm tra một lớp không chứng minh toàn bộ luồng messaging hoạt động. Nên chia test theo phạm vi và câu hỏi cần trả lời.

### Unit test cho logic và abstraction

Dùng unit test để kiểm tra:

- Tạo message với payload và headers.
- Mapping domain object sang event DTO.
- Validation của message.
- Logic xử lý idempotency.
- Quy tắc đặt route hoặc destination.
- Xử lý lỗi và retry policy ở mức publisher.

Không cần broker thật để kiểm tra một hàm chuyển đổi DTO thuần hoặc một chính sách đặt tên.

### Spring context test cho wiring

Dùng test context để kiểm tra:

- Bean cần thiết có được tạo không.
- Message converter có đúng cấu hình không.
- Handler mapping có được đăng ký không.
- Property được bind vào bean đúng không.
- Conditional auto-configuration có kích hoạt đúng không.

Nếu test dùng Spring Boot, hãy nói rõ đây là Boot context test. Không kết luận rằng một property Boot là tính năng của Spring Framework chỉ vì test context khởi động thành công.

### Adapter integration test

Kiểm thử adapter với dependency tương ứng:

- Spring Kafka với Kafka broker.
- Spring AMQP với RabbitMQ.
- Spring JMS với JMS provider.
- Spring Integration với adapter/transport đang sử dụng.
- Spring STOMP với simple broker hoặc external broker relay.
- RSocket requester/responder qua transport thật.

Các test này xác nhận mapping, serialization, acknowledgement, routing và lifecycle trên ranh giới tích hợp.

### Broker và deployment test

Cần môi trường gần production để kiểm tra:

- Partition/replication hoặc queue durability.
- Broker restart và failover.
- Authentication, TLS và ACL.
- Consumer group rebalance.
- Prefetch, retry và dead-letter policy.
- Network timeout, proxy và connection draining.
- Load, throughput và resource limit.

Testcontainers có thể giúp khởi động sản phẩm thật trong test tự động nếu có module phù hợp. Nhưng một broker container đơn lẻ không mô phỏng đầy đủ cluster, replication, cloud IAM hoặc network topology production.

## 13. Kiểm thử cấu hình mà không biến thành test của sản phẩm khác

Một cấu hình nên được kiểm tra ở nơi nó được tiêu thụ:

- Property binding của Boot: kiểm tra bean sau khi binding.
- Kafka client property: kiểm tra cấu hình producer/consumer factory và integration với broker.
- Kafka broker property: kiểm tra cluster hoặc môi trường broker, không chỉ kiểm tra Spring ApplicationContext.
- Rabbit queue argument: kiểm tra declaration và hành vi của RabbitMQ.
- Kubernetes resource limit: kiểm tra manifest hoặc cluster, không chỉ unit test Java.
- Secret: kiểm tra secret injection bằng môi trường test an toàn, không hardcode giá trị thật.

Ví dụ một test context xác nhận Boot bind consumer group:

~~~java
@SpringBootTest(properties = {
    "spring.kafka.consumer.group-id=orders-test"
})
class KafkaPropertiesTest {

    @Autowired
    KafkaProperties properties;

    @Test
    void shouldBindConsumerGroup() {
        assertEquals(
            "orders-test",
            properties.getConsumer().getGroupId()
        );
    }
}
~~~

Test này xác nhận property được bind vào cấu hình Boot. Nó không chứng minh broker có topic, consumer group đã join thành công hay quyền ACL đã đúng. Những điều đó cần integration test hoặc test môi trường triển khai.

## 14. Cách viết tài liệu để không trộn lẫn các lớp

Một README hoặc runbook tốt nên phân tách nội dung theo phạm vi:

1. **Framework concept:** giải thích abstraction và API ổn định.
2. **Spring project integration:** nêu module/dependency và API adapter.
3. **Boot setup:** liệt kê starter, property prefix và auto-configuration condition.
4. **External product setup:** ghi broker version, topic/queue, policy, security và runtime configuration.
5. **Deployment:** ghi network, secret, resource, replica và health check.
6. **Testing:** nêu test nào xác nhận từng lớp và test nào cần môi trường thật.

Mỗi ví dụ cấu hình nên có chú thích:

- Property thuộc Spring Boot hay client library?
- Giá trị được đọc ở startup hay runtime?
- Nó cấu hình ứng dụng, client hay broker?
- Có cần restart ứng dụng hoặc broker để áp dụng không?
- Có thay đổi semantics của message hoặc chỉ thay đổi tài nguyên?
- Phiên bản nào đã được xác minh?

Khi một tính năng do adapter phơi bày nhưng thực thi ở broker, hãy mô tả cả hai phía. Ví dụ, Spring AMQP có thể khai báo queue argument, nhưng TTL và dead-letter behavior được RabbitMQ thực thi.

## 15. Các lỗi phân loại thường gặp

| Nhầm lẫn | Vì sao sai | Cách phân loại đúng |
|---|---|---|
| Gọi KafkaTemplate là API lõi của Spring Framework | Class thuộc Spring for Apache Kafka | Ghi rõ dự án và dependency |
| Gọi spring.kafka.* là property của Framework | Prefix thuộc Boot auto-configuration | Ghi rõ yêu cầu Spring Boot |
| Cho rằng Spring Messaging tự cung cấp broker | Framework cung cấp abstraction và integration | Chỉ rõ broker hoặc transport thực tế |
| Cho rằng /topic trong simple broker là queue bền vững | Prefix không tự tạo semantics broker chuyên dụng | Kiểm tra broker và cấu hình |
| Cho rằng gửi message thành công nghĩa consumer đã commit | Send, broker ack và business commit là các mốc khác nhau | Kiểm thử từng mốc |
| Dùng test context để chứng minh retention của Kafka | Retention do broker quản lý | Test broker hoặc cluster |
| Dùng một cấu hình cho mọi broker | Property và semantics không đồng nhất | Dùng tài liệu sản phẩm cụ thể |
| Nâng cấp Spring nhưng bỏ qua client/broker compatibility | Các thành phần có version độc lập | Kiểm tra BOM và compatibility matrix |
| Đưa secret vào application.yaml mẫu | Có thể rò rỉ credential | Dùng secret reference hoặc biến môi trường |
| Gọi mọi thứ bắt đầu bằng Spring là Framework core | Hệ sinh thái gồm nhiều dự án độc lập | Kiểm tra package, artifact và tài liệu |

## 16. Checklist trước khi công bố tài liệu hoặc triển khai

- [ ] Đã xác định API thuộc Spring Framework hay dự án Spring mở rộng.
- [ ] Đã ghi rõ có dùng Spring Boot hay không.
- [ ] Mỗi property có owner và nơi thực thi được xác định.
- [ ] Đã phân biệt cấu hình ứng dụng, client, broker và deployment.
- [ ] Broker/product version được ghi cùng cấu hình liên quan.
- [ ] Không dùng property của một broker như cấu hình chung cho mọi broker.
- [ ] API và ví dụ code phù hợp với phiên bản dependency.
- [ ] Schema nghiệp vụ được quản lý độc lập với framework version.
- [ ] Unit test, context test, adapter integration test và broker test có phạm vi rõ.
- [ ] Không tuyên bố broker behavior chỉ dựa trên việc Spring context khởi động thành công.
- [ ] Secret và credential không bị ghi vào source hoặc log.
- [ ] Có tài liệu release note và compatibility matrix cho các thành phần cần phối hợp.

## 17. Tài liệu tham khảo

- [Spring Framework Reference](https://docs.spring.io/spring-framework/reference/) — các abstraction và tích hợp chính thức của Spring Framework.
- [Spring Messaging](https://docs.spring.io/spring-framework/reference/integration.html) — messaging abstraction và các phần tích hợp trong Framework.
- [Spring Boot Reference](https://docs.spring.io/spring-boot/reference/) — auto-configuration, externalized configuration, properties và starter.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/) — integration flow, channel adapter và Enterprise Integration Patterns.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/) — KafkaTemplate, listener container, producer/consumer và transaction.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/) — RabbitTemplate, listener container và AMQP integration.
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/) — function binding, binder và event-driven application.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/) — topic, partition, retention, consumer group và broker configuration.
- [RabbitMQ Documentation](https://www.rabbitmq.com/docs) — exchange, queue, binding, acknowledgement, TTL và dead-letter policy.

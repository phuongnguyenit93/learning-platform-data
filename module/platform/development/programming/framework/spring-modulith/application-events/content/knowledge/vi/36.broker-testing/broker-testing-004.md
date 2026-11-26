# Kiểm thử queue

## Vì sao cần kiểm thử queue với broker thật?

Queue là nơi message được giữ lại để một hoặc nhiều consumer nhận và xử lý theo chính sách của broker. Trong kiến trúc event-driven, producer có thể gửi message thành công nhưng message vẫn không đến đúng queue, listener không được kích hoạt, acknowledgement không đúng hoặc message bị giao lại ngoài dự kiến.

Một unit test chỉ mock RabbitTemplate hoặc message publisher có thể xác nhận code gọi đúng method. Nó không chứng minh broker đã nhận message, exchange định tuyến đúng binding, queue giữ message sau restart, consumer acknowledge đúng hoặc dead-letter được cấu hình chính xác.

Kiểm thử queue cần xác nhận cả hợp đồng ứng dụng và hành vi thực tế của broker:

1. Producer gửi đúng message tới exchange/destination và routing key.
2. Broker định tuyến message tới queue dự kiến.
3. Consumer nhận, deserialize và xử lý message.
4. Acknowledgement, retry, redelivery và dead-letter tuân theo policy.
5. Nhiều consumer cạnh tranh hoặc nhiều subscription độc lập hoạt động đúng semantics.
6. Test có thể chạy lặp mà không để lại message hoặc queue làm nhiễu lần chạy sau.

~~~mermaid
flowchart LR
    P[Producer / Spring Modulith adapter] -->|publish| X[(Exchange)]
    X -->|routing key + binding| Q[(Queue)]
    Q --> C1[Consumer instance 1]
    Q --> C2[Consumer instance 2]
    C1 -->|ack / nack| Q
    C2 -->|ack / nack| Q
    Q -->|reject / dead-letter| D[(Dead-letter queue)]
~~~

Sơ đồ minh họa mô hình exchange và queue của RabbitMQ. Với broker khác, khái niệm destination, subscription, offset và acknowledgement có thể khác; test phải theo semantics của broker đang dùng.

## Phân biệt queue test với application event test

Application event trong Spring chạy bên trong ApplicationContext. Một listener nội bộ có thể được gọi mà không có broker hoặc queue nào tham gia.

Queue test kiểm tra chặng giao tiếp qua hạ tầng messaging. Khi Spring Modulith externalize một event, adapter chuyển event thành message gửi tới broker. Với RabbitMQ, target thường được ánh xạ tới exchange; exchange định tuyến message tới queue dựa trên binding và routing key.

| Phạm vi | Điều được kiểm tra |
|---|---|
| Application event test | Event được phát trong ApplicationContext và listener nội bộ được gọi |
| Externalization adapter test | Event được chuyển thành message đúng payload, header và target |
| Queue integration test | Broker nhận message, định tuyến tới queue và giữ message theo cấu hình |
| Consumer integration test | Listener nhận message, xử lý và xác nhận theo policy |
| End-to-end messaging test | Producer, broker, queue và consumer phối hợp qua ranh giới tiến trình |

Một test publisher nội bộ không chứng minh queue đã nhận message. Một test đọc trực tiếp message khỏi queue cũng không chứng minh listener production đã được đăng ký và xử lý đúng. Nên chọn test theo mục tiêu, rồi kết hợp một số integration test để xác nhận toàn bộ đường đi quan trọng.

## Chọn broker test phù hợp

Đối với RabbitMQ, nên dùng broker thật trong integration test, thường thông qua Testcontainers. Container tạo broker riêng cho test và cho phép kiểm tra exchange, queue, binding, acknowledgement và dead-letter với hành vi gần production.

Ví dụ khai báo container:

~~~java
@Testcontainers
@SpringBootTest
class OrderQueueIntegrationTests {

    @Container
    static RabbitMQContainer rabbit =
        new RabbitMQContainer("rabbitmq:3.13-management");

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        registry.add("spring.rabbitmq.username", rabbit::getAdminUsername);
        registry.add("spring.rabbitmq.password", rabbit::getAdminPassword);
    }
}
~~~

Ví dụ cần dependency Testcontainers RabbitMQ và cấu hình Spring Boot AMQP tương ứng. Chọn image broker theo phiên bản production đang hỗ trợ; không mặc định tag minh họa luôn phù hợp với mọi môi trường.

Có thể dùng broker dùng chung trong môi trường integration test, nhưng phải cô lập virtual host, queue name hoặc namespace theo build/test run. Nếu nhiều test cùng ghi vào một queue, kết quả dễ bị nhiễu và khó xác định test nào sở hữu message.

Không dùng mock broker cho test cần xác minh routing, persistence, acknowledgement hoặc dead-letter. Mock phù hợp với unit test của producer/consumer khi chỉ muốn kiểm tra logic gọi collaborator.

## Cấu hình connection và test environment

Test cần cung cấp các thông tin kết nối qua property hoặc test service connection:

- Host và port broker.
- Username/password hoặc cơ chế xác thực tương ứng.
- Virtual host hoặc namespace.
- Exchange, queue và routing key.
- TLS nếu test cần xác minh cấu hình bảo mật.
- Timeout và retry của client.

Không đặt credential production trong test. Container test nên dùng credential riêng, giới hạn trong môi trường chạy test.

Nếu test dùng Testcontainers, khai báo lifecycle rõ ràng để broker khởi động trước khi ApplicationContext tạo connection factory. Với Spring Boot có hỗ trợ service connection cho loại container đang dùng, có thể dùng cơ chế đó; nếu không, DynamicPropertySource là lựa chọn tường minh.

Test cần có timeout khởi động và teardown hợp lý. Nếu broker không thể khởi động, test nên thất bại với nguyên nhân rõ ràng thay vì âm thầm bỏ qua toàn bộ kiểm thử queue.

## Kiểm tra queue, exchange và binding

Một message chỉ tới queue nếu topology được khai báo đúng. Với RabbitMQ, cần xác nhận:

- Exchange tồn tại với đúng tên và loại.
- Queue tồn tại với đúng durability, exclusivity và auto-delete policy.
- Binding nối đúng exchange với queue.
- Binding key khớp routing key của producer.
- Queue có dead-letter exchange hoặc TTL đúng nếu use case yêu cầu.

Ví dụ khai báo topology bằng Spring AMQP:

~~~java
@Configuration
class OrdersRabbitTopology {

    static final String EXCHANGE = "commerce.orders";
    static final String QUEUE = "fulfillment.orders";
    static final String ROUTING_KEY = "order.confirmed";

    @Bean
    TopicExchange ordersExchange() {
        return new TopicExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue fulfillmentQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding fulfillmentBinding(
            Queue fulfillmentQueue,
            TopicExchange ordersExchange) {
        return BindingBuilder.bind(fulfillmentQueue)
            .to(ordersExchange)
            .with(ROUTING_KEY);
    }
}
~~~

Test nên xác nhận queue và exchange được khai báo thành công, sau đó publish message và kiểm tra queue nhận đúng message. Chỉ assert bean Queue tồn tại không chứng minh broker đã khai báo topology; cần thao tác qua RabbitAdmin hoặc gửi message qua broker thật.

Với topic exchange, kiểm tra cả wildcard binding như * và #. Với direct exchange, routing key phải khớp chính xác. Với fanout exchange, routing key không quyết định queue nhận message. Không áp dụng cùng một giả định routing cho mọi exchange type.

## Kiểm tra producer publish vào queue

Trong RabbitMQ, producer thường publish tới exchange; queue nhận message thông qua binding. Test nên gọi đúng đường gửi mà ứng dụng production sử dụng, ví dụ RabbitTemplate hoặc externalization adapter.

Ví dụ publish message:

~~~java
@SpringBootTest
class OrderQueuePublishTests {

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Test
    void routesOrderConfirmedToFulfillmentQueue() {
        OrderConfirmed event = new OrderConfirmed(
            UUID.randomUUID(),
            UUID.randomUUID()
        );

        rabbitTemplate.convertAndSend(
            "commerce.orders",
            "order.confirmed",
            event
        );

        Object received = rabbitTemplate.receiveAndConvert(
            "fulfillment.orders",
            5_000
        );

        assertThat(received).isInstanceOf(OrderConfirmed.class);
    }
}
~~~

Đây là ví dụ minh họa cho queue test trực tiếp. Trong dự án thực tế, payload có thể được serialize thành JSON hoặc envelope; assertion cần kiểm tra event ID, aggregate ID, event type và field nghiệp vụ quan trọng.

Không chỉ kiểm tra message có tồn tại. Hãy xác nhận:
- Message vào đúng queue.
- Message không xuất hiện ở queue không liên quan.
- Payload deserialize được theo contract.
- Header như content type, correlation ID và event ID được giữ đúng.
- Routing key hoặc metadata được adapter chuyển tiếp như thiết kế.

Nếu publisher gửi tới exchange không có binding phù hợp, message có thể bị unroutable. Cấu hình mandatory publish và publisher returns/confirm phù hợp giúp phát hiện trường hợp đó; test nên xác minh hành vi return hoặc lỗi theo cấu hình client.

## Publisher confirms và kết quả publish

Publish API trả về không luôn đồng nghĩa broker đã xác nhận message. Với RabbitMQ, publisher confirms cho biết broker đã nhận trách nhiệm với publish theo semantics của confirm; returned message giúp phát hiện message không được route khi dùng mandatory.

Test publisher nên phân biệt:

- Client đã gửi yêu cầu.
- Broker đã confirm publish.
- Message có được route tới ít nhất một queue hay không.
- Message có được lưu bền vững theo durability policy hay không.

Nếu use case yêu cầu không mất message, hãy kiểm tra durable exchange/queue, persistent delivery mode và publisher confirms theo cấu hình production. Những yếu tố này phối hợp với nhau; chỉ bật durable queue không tự làm mọi message trở nên persistent.

Khi publisher confirm timeout, trạng thái có thể không chắc chắn: broker có thể đã nhận message nhưng confirm bị mất trên đường về. Producer retry có thể tạo duplicate. Consumer vì vậy vẫn cần idempotency.

## Kiểm tra consumer listener

Test consumer nên xác nhận listener thực sự được đăng ký và xử lý message khi broker giao tới queue. Với Spring AMQP, listener thường được khai báo bằng @RabbitListener.

~~~java
@Component
@RequiredArgsConstructor
class FulfillmentQueueListener {

    private final FulfillmentService fulfillmentService;

    @RabbitListener(queues = "fulfillment.orders")
    public void on(OrderConfirmed event) {
        fulfillmentService.prepareShipment(event.orderId());
    }
}
~~~

Integration test gửi message qua RabbitTemplate rồi chờ side effect được commit:

~~~java
@Test
void consumesOrderConfirmedAndCreatesShipment() {
    UUID orderId = UUID.randomUUID();

    rabbitTemplate.convertAndSend(
        "commerce.orders",
        "order.confirmed",
        new OrderConfirmed(UUID.randomUUID(), orderId)
    );

    await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
        assertThat(shipmentRepository.existsByOrderId(orderId))
            .isTrue()
    );
}
~~~

Dùng Awaitility hoặc một cơ chế chờ có giới hạn để đợi trạng thái cuối cùng. Không dùng Thread.sleep cố định vì thời gian xử lý phụ thuộc tải, scheduler và broker.

Ưu tiên kiểm tra side effect nghiệp vụ thay vì chỉ kiểm tra listener method được gọi. Điều đó xác nhận message được deserialize, listener được dispatch và transaction xử lý đã commit.

## Kiểm tra acknowledgement

Acknowledgement cho broker biết consumer đã xử lý message đến mức nào. Với Spring AMQP, container có thể quản lý acknowledgement theo chế độ cấu hình; chế độ AUTO thường xác nhận khi listener hoàn tất thành công và xử lý exception theo error handler/requeue policy. MANUAL cho phép listener chủ động ack hoặc nack qua Channel hoặc cơ chế tương ứng.

Test cần xác nhận:
- Listener thành công thì message được acknowledge và không còn chờ xử lý.
- Listener thất bại thì message được requeue, reject hoặc dead-letter theo policy.
- Acknowledgement chỉ xảy ra sau khi side effect cần thiết đã hoàn tất.
- Consumer không ack trước khi transaction nghiệp vụ commit nếu điều đó có thể làm mất công việc.

Với MANUAL acknowledgement, cần kiểm tra cả ack, nack và reject path. Một message không được ack có thể được broker requeue khi channel hoặc connection đóng; hành vi này cần được tính vào thiết kế idempotency.

Không giả định ack đồng nghĩa message đã được xử lý đúng nghiệp vụ. Ack chỉ là tín hiệu giao nhận ở mức broker; assertion dữ liệu và transaction vẫn cần thiết.

## Kiểm tra requeue và redelivery

Khi listener thất bại, broker có thể giao lại message. Test nên xác nhận redelivery xảy ra theo cấu hình và không tạo tác động trùng.

Các tình huống cần kiểm tra:

| Tình huống | Điều cần xác nhận |
|---|---|
| Lỗi tạm thời, requeue bật | Message được giao lại |
| Lỗi dữ liệu, requeue tắt | Message không lặp vô hạn |
| Consumer process dừng trước ack | Message có thể được giao lại khi channel đóng |
| Duplicate delivery | Consumer idempotent, side effect chỉ xảy ra một lần |
| Retry vượt giới hạn | Message được chuyển sang dead-letter theo policy |

RabbitMQ có thể đặt cờ redelivered cho message được giao lại, nhưng cờ này chỉ là gợi ý giao nhận. Không dùng nó làm cơ chế deduplication duy nhất; consumer nên dựa vào event ID hoặc business key ổn định.

Test retry cần có giới hạn thời gian và số lần thử. Không tạo vòng lặp vô hạn làm suite treo khi listener luôn thất bại.

## Kiểm tra dead-letter queue

Dead-letter exchange/queue thường nhận message bị reject không requeue, hết TTL hoặc vượt giới hạn queue theo cấu hình broker.

Ví dụ queue có dead-letter exchange:

~~~java
@Bean
Queue fulfillmentQueue() {
    return QueueBuilder.durable("fulfillment.orders")
        .deadLetterExchange("commerce.dead")
        .deadLetterRoutingKey("orders.failed")
        .build();
}

@Bean
DirectExchange deadLetterExchange() {
    return new DirectExchange("commerce.dead", true, false);
}

@Bean
Queue fulfillmentDeadLetterQueue() {
    return QueueBuilder.durable("fulfillment.orders.dlq").build();
}

@Bean
Binding deadLetterBinding() {
    return BindingBuilder.bind(fulfillmentDeadLetterQueue())
        .to(deadLetterExchange())
        .with("orders.failed");
}
~~~

Test cần:
1. Gửi message vào queue gốc.
2. Làm listener reject hoặc ném exception theo policy không requeue.
3. Chờ message xuất hiện trong DLQ.
4. Xác nhận payload, event ID và metadata cần điều tra còn nguyên.
5. Xác nhận message không còn được xử lý lặp ở queue gốc.

Cần phân biệt DLQ của broker với retry queue. Retry queue thường giữ message để thử lại sau TTL hoặc delay; DLQ giữ message đã bị loại khỏi luồng xử lý bình thường. Topology và plugin hỗ trợ delayed message có thể khác giữa môi trường.

## Kiểm tra TTL và expiration

Queue hoặc message có thể được cấu hình TTL. Khi hết hạn, message có thể bị loại bỏ hoặc dead-letter tùy cấu hình.

Test nên xác nhận:
- TTL được áp dụng ở cấp queue hay message.
- Message chưa hết hạn vẫn có thể được consume.
- Message hết hạn không xuất hiện ở queue đích bình thường.
- Nếu dead-letter được cấu hình, message hết hạn được route tới DLQ đúng.
- Thời gian test đủ bao phủ TTL nhưng không dựa vào sleep không xác định.

TTL phụ thuộc clock và scheduler của broker; tránh assert ở đúng ranh giới mili giây. Chọn khoảng chờ có biên an toàn và kiểm tra trạng thái cuối bằng polling có timeout.

## Kiểm tra competing consumers

Một queue có thể được nhiều consumer instance cùng consume. Đây là mô hình competing consumers: mỗi message thường được giao cho một consumer trong nhóm queue đó, thay vì broadcast tới tất cả instance.

Test cần xác nhận:
- Nhiều consumer cùng nhận message từ một queue.
- Mỗi message được một consumer xử lý thành công theo semantics bình thường.
- Tổng số message xử lý khớp số message gửi, sau khi tính duplicate/redelivery.
- Consumer chậm không làm các message khác bị mất.
- Prefetch và concurrency không vượt giới hạn tài nguyên.

Không assert chính xác message nào phải đến instance nào nếu broker không bảo đảm phân phối round-robin tuyệt đối trong điều kiện concurrency, prefetch và consumer availability. Hãy kiểm tra tổng hợp side effect và không có message bị mất hoặc xử lý trùng ngoài policy.

Nếu nhiều hệ thống độc lập đều cần nhận mọi event, mỗi hệ thống cần queue/subscription riêng. Dùng chung một queue cạnh tranh chỉ chia message giữa các consumer, không broadcast mỗi message tới tất cả hệ thống.

## Kiểm tra ordering và prefetch

Queue có thể giữ thứ tự enqueue, nhưng thứ tự hoàn tất xử lý ở consumer không luôn giống thứ tự nhận. Nhiều consumer, prefetch lớn, redelivery và xử lý song song có thể làm kết quả hoàn tất khác thứ tự.

Nếu thứ tự là yêu cầu nghiệp vụ:
- Giới hạn concurrency hoặc dùng một consumer tuần tự cho phạm vi cần thiết.
- Dùng aggregate version/sequence để phát hiện event đến sai thứ tự.
- Tránh nhiều consumer đồng thời ghi cùng aggregate nếu không có optimistic locking.
- Kiểm tra hành vi redelivery và requeue.
- Xác định rõ ordering được yêu cầu ở mức queue, aggregate hay toàn hệ thống.

Prefetch điều khiển số message chưa acknowledge mà broker có thể giao cho consumer. Prefetch lớn có thể tăng throughput nhưng cũng làm nhiều message bị giữ ở một consumer đang chậm. Prefetch nhỏ giảm số message outstanding nhưng có thể làm giảm hiệu suất nếu network round trip cao.

Test hiệu năng nên đo throughput, queue depth, unacked count và thời gian xử lý, không chỉ kiểm tra một message đơn lẻ.

## Kiểm tra queue durability và restart

Nếu queue phải tồn tại sau khi broker restart, kiểm thử topology durable và message persistence theo cấu hình.

Các yếu tố cần phân biệt:
- Durable queue giữ khai báo queue qua restart.
- Persistent message được đánh dấu delivery mode phù hợp.
- Publisher confirm giúp biết broker đã nhận trách nhiệm với message.
- Replication/quorum queue cung cấp đặc tính chịu lỗi theo cấu hình RabbitMQ.
- Storage và broker recovery vẫn có thể ảnh hưởng thời gian sẵn sàng.

Test restart broker tốn thời gian hơn test integration thông thường. Có thể đặt trong nhóm test chuyên biệt, chạy theo lịch hoặc trước release quan trọng. Không kết luận message bền vững chỉ từ một test queue in-memory hoặc một broker container chưa restart.

Nếu dùng quorum queue, xác nhận số node và cấu hình cluster phù hợp. Một container RabbitMQ đơn lẻ không kiểm chứng được khả năng chịu lỗi của quorum cluster production.

## Kiểm tra queue qua Spring Modulith externalization

Spring Modulith có thể externalize application event qua integration adapter. Với RabbitMQ, target logic được ánh xạ tới exchange; routing key và binding quyết định queue nào nhận message.

Một test tích hợp nên xác nhận:
- Event được chọn để externalize theo annotation hoặc configuration.
- Adapter serialize event đúng contract.
- Target và routing key được ánh xạ chính xác.
- Broker nhận message và route tới queue đã bind.
- Consumer nhận payload đúng schema và xử lý được.
- Publication registry phản ánh kết quả externalization theo semantics của adapter.

Không coi Event Publication Registry là queue hoặc broker. Registry theo dõi publication của application event trong ứng dụng; queue giữ message phía broker. Publication hoàn tất không chứng minh listener downstream đã hoàn tất nghiệp vụ.

Nếu test chỉ cần xác nhận Spring Modulith chọn đúng event, có thể dùng test application context và kiểm tra adapter mapping. Nếu cần xác nhận routing, acknowledgement hoặc DLQ, phải có broker thật.

## Cô lập queue giữa các test

Queue giữ message sau khi test kết thúc có thể làm test kế tiếp đọc nhầm dữ liệu. Cần quản lý vòng đời topology và message:

- Dùng queue name riêng theo test class hoặc test run khi phù hợp.
- Dùng virtual host hoặc broker container riêng cho suite.
- Purge queue trước/sau test khi queue được chia sẻ và việc purge an toàn.
- Xóa queue/exchange được tạo riêng sau test.
- Không xóa topology dùng chung mà test khác đang sử dụng.
- Dùng event ID và aggregate ID riêng cho từng test.
- Chờ consumer hoàn tất trước khi teardown broker.

Nếu Spring context cache giữ RabbitListener container qua nhiều test, việc xóa queue quá sớm có thể làm listener báo lỗi. Teardown phải phối hợp với lifecycle của listener container và ApplicationContext.

Test chạy song song cần namespace độc lập. Một queue dùng chung với message của nhiều test có thể khiến consumer của test này lấy message thuộc test khác.

## Kiểm thử với RabbitListenerTestHarness

Spring AMQP cung cấp test support để quan sát và spy listener được khai báo bằng @RabbitListener. RabbitListenerTestHarness có thể hỗ trợ lấy kết quả invocation hoặc verify listener theo cấu hình test.

Ví dụ khái niệm:

~~~java
@SpringBootTest
@RabbitListenerTest(spy = true, capture = true)
class FulfillmentListenerTests {

    @Autowired
    RabbitListenerTestHarness harness;

    @Test
    void invokesListenerWithExpectedPayload() throws Exception {
        // Publish message vào queue thật trước đó.

        InvocationData invocation =
            harness.getNextInvocationDataFor(
                "fulfillmentListener",
                5,
                TimeUnit.SECONDS
            );

        assertThat(invocation).isNotNull();
        assertThat(invocation.getArguments()[0])
            .isInstanceOf(OrderConfirmed.class);
    }
}
~~~

Đây là ví dụ minh họa; listener cần có ID phù hợp và test configuration phải bật harness. API harness có thể thay đổi theo phiên bản Spring AMQP.

Harness giúp xác nhận listener invocation và tham số. Nó không thay thế assertion persistence, acknowledgement hoặc broker routing. Với test end-to-end, vẫn cần xác nhận side effect và trạng thái queue.

## Ma trận kiểm thử queue

Ma trận sau giúp xác định các nhánh quan trọng:

| Kịch bản | Producer/Broker | Consumer | Kết quả mong đợi |
|---|---|---|---|
| Publish hợp lệ | Confirm thành công, route đúng | Xử lý thành công | Side effect được commit |
| Sai routing key | Message unroutable hoặc route khác theo topology | Listener đích không nhận | Test phát hiện sai binding |
| Listener lỗi tạm thời | Message vẫn ở luồng retry/requeue theo policy | Thử lại có giới hạn | Cuối cùng thành công hoặc DLQ |
| Payload không hợp lệ | Broker vẫn có thể nhận message | Reject/quarantine | Không tạo side effect sai |
| Consumer dừng trước ack | Broker giữ/requeue theo connection state | Nhận lại message | Idempotency ngăn tác động trùng |
| TTL hết hạn | Broker hết hạn message | Không xử lý ở queue gốc | Dead-letter nếu được cấu hình |
| Nhiều consumer | Một queue có nhiều consumer | Chia tải | Không mất message |
| Hai subscription độc lập | Mỗi queue có binding riêng | Mỗi hệ thống nhận bản sao | Fan-out đúng |
| Broker restart | Queue/message durable theo policy | Consumer kết nối lại | Message còn lại được xử lý |
| Test chạy song song | Namespace/queue tách biệt | Không đọc chéo | Test độc lập |

Không phải mọi dự án cần toàn bộ ma trận ở mỗi lần chạy. Chọn các kịch bản tương ứng với cấu hình và rủi ro thực tế của queue.

## Tránh các lỗi thường gặp

- **Chỉ mock RabbitTemplate:** không kiểm tra broker routing hoặc acknowledgement.
- **Đọc message trực tiếp khỏi queue trong test consumer:** test đã lấy message trước listener nên listener không thể xử lý nó.
- **Dùng queue chung giữa các test:** message tồn dư gây kết quả không ổn định.
- **Chỉ assert queue tồn tại:** không chứng minh binding hoặc routing key đúng.
- **Dùng sleep cố định:** test phụ thuộc tốc độ máy và dễ flaky.
- **Không kiểm tra ack/nack:** message có thể bị mất hoặc redelivery liên tục.
- **Không kiểm tra duplicate:** retry có thể tạo side effect nhiều lần.
- **Nhầm queue với broadcast:** competing consumers chia message, không phải mỗi consumer nhận một bản.
- **Coi durable queue là đủ:** cần xem cả persistent message, confirms và replication.
- **Không giới hạn retry:** một message lỗi có thể chiếm tài nguyên vô hạn.

## Quy trình xây dựng queue integration test

Khi thêm một queue hoặc consumer mới, thực hiện theo thứ tự:

1. Xác định broker, exchange/destination, queue và routing/binding contract.
2. Chọn broker test phù hợp với phiên bản và topology production.
3. Khởi tạo connection properties và lifecycle test rõ ràng.
4. Khai báo topology giống production ở những thuộc tính cần xác minh.
5. Publish message qua đúng producer hoặc externalization adapter.
6. Xác nhận broker route message tới queue dự kiến.
7. Chờ consumer xử lý và kiểm tra side effect đã commit.
8. Kiểm tra acknowledgement, requeue, retry và DLQ.
9. Kiểm tra duplicate, ordering, prefetch và competing consumers nếu liên quan.
10. Cô lập queue, dữ liệu và consumer giữa các test.
11. Thêm test restart/durability riêng nếu yêu cầu vận hành cần bảo đảm đó.

Kiểm thử queue với broker thật giúp phát hiện lỗi topology, routing, listener, acknowledgement và recovery mà unit test không thể mô phỏng đầy đủ. Khi test được cô lập, chờ theo điều kiện có giới hạn và kiểm tra cả side effect lẫn trạng thái giao nhận, hệ thống messaging sẽ có bằng chứng đáng tin cậy hơn trước khi triển khai.

## Tài liệu tham khảo

- Spring AMQP Reference — Testing: https://docs.spring.io/spring-amqp/reference/testing.html
- Spring AMQP Reference — Listener Container Configuration: https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/listener-annotation.html
- RabbitMQ Documentation — Queues: https://www.rabbitmq.com/docs/queues
- RabbitMQ Documentation — Exchanges and Bindings: https://www.rabbitmq.com/tutorials/amqp-concepts
- RabbitMQ Documentation — Publisher Confirms and Consumer Acknowledgements: https://www.rabbitmq.com/docs/confirms
- Testcontainers — RabbitMQ Module: https://java.testcontainers.org/modules/rabbitmq/
- Spring Modulith Reference — Event Externalization: https://docs.spring.io/spring-modulith/reference/events.html

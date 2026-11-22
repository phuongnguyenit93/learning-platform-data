# Test channel và message handler trong Spring Integration

Một integration flow có thể trông rất đơn giản: nhận <code>Message&lt;OrderCommand&gt;</code> từ channel, gọi service activator rồi đẩy kết quả sang downstream. Nhưng khi chuyển từ <code>DirectChannel</code> sang <code>ExecutorChannel</code>, dùng <code>QueueChannel</code> với poller hoặc bổ sung retry, transaction, error channel, hành vi runtime thay đổi đáng kể. Bài kiểm thử chỉ xác nhận service trả đúng dữ liệu **chưa đủ** để chứng minh flow không làm mất message, không báo thành công quá sớm và định tuyến lỗi đúng.

Bài học **“Test channel và message handler”** thuộc chương **Testing runtime** của **SPRING_INTEGRATION_RUNTIME**. Trọng tâm là thiết kế test theo ranh giới channel–endpoint–handler, sử dụng Spring Integration Test Framework và JUnit 5, rồi mở rộng sang threading, timeout, retry, message store, correlation, transaction và lifecycle. Các ví dụ nhắm tới Java 17+ và Spring Integration 6.x; khi copy vào dự án cần đồng bộ phiên bản dependency và cấu hình ứng dụng.

> **Nguyên tắc:** <code>MessageChannel.send()</code> trả về thành công **không phải lúc nào** cũng có nghĩa handler và toàn bộ downstream đã xử lý thành công. Test phải quan sát đúng **completion boundary** của từng loại channel.

## 1. Xác định điều gì cần chứng minh trước khi viết test

Có thể chia test thành bốn mức; mỗi mức có độ tin cậy và chi phí khác nhau:

| Mức kiểm thử | Điểm vào / điểm quan sát | Chứng minh được | Chưa chứng minh được |
|---|---|---|---|
| **Unit test service** | Gọi thẳng method Java, mock repository | Quy tắc nghiệp vụ, validation, kết quả/trường hợp lỗi | Routing, header, advice, subscriber, polling, threading |
| **Channel test** | Tự tạo <code>DirectChannel</code>, <code>QueueChannel</code> hoặc <code>ExecutorChannel</code> | Send/receive, capacity, dispatch, thread và completion của channel | Toàn bộ wiring trong Spring context |
| **Flow integration test** | Gửi message vào bean input, nhận output hoặc kiểm tra side effect | Channel → endpoint → handler, chuyển payload/header, error path và lifecycle | Transaction của broker/database nếu chỉ mock |
| **System/boundary test** | Broker/database/adapter thật hoặc Testcontainers | ACK, redelivery, commit/rollback, restart, concurrency nhiều instance | Không tự chứng minh mọi tình huống ngoài hệ thống đã mô phỏng |

Một test tốt trả lời rõ:

1. **Given:** payload/header, trạng thái channel và service ban đầu là gì?
2. **When:** message đi vào channel nào; thread, poller hay adapter nào kích hoạt?
3. **Then:** ai hoàn tất, output ở đâu, exception đi về đâu, side effect xảy ra mấy lần?
4. **Finally:** tài nguyên/test double đã được trả lại trạng thái nào để test sau không bị ảnh hưởng?

~~~mermaid
flowchart LR
    T["JUnit test"] --> IN["Input channel"]
    IN --> EP["Consumer endpoint"]
    EP --> H["Message handler"]
    H --> OUT["Output channel"]
    OUT --> A["Assert payload, header, completion"]
    H -. "Exception" .-> E["Caller hoặc error flow"]
    E --> B["Assert lỗi / rollback / retry"]
~~~

Đối với flow bất đồng bộ, mũi tên từ <code>send()</code> trở về test có thể xảy ra **trước** khi <code>MessageHandler</code> chạy xong. Cần dùng output queue, latch, future hoặc các assertion chờ theo điều kiện có timeout.

## 2. So sánh semantics cần kiểm thử của các channel

| Loại channel | Cách dispatch / lưu message | <code>send()</code> thường nói lên điều gì? | Điểm assert đáng tin cậy |
|---|---|---|---|
| <code>DirectChannel</code> | Subscriber chạy đồng bộ trên thread sender | Lời gọi handler đồng bộ đã hoàn tất hoặc exception truyền về | Kết quả sau <code>send()</code>, exception từ cùng call stack |
| <code>PublishSubscribeChannel</code> không executor | Gọi subscriber đồng bộ theo dispatcher | Send đã thực hiện các subscriber theo chính sách, trừ khi error handler/subscriber thay đổi luồng | Side effect từng subscriber; lỗi theo cấu hình |
| <code>ExecutorChannel</code> | Giao task cho executor, handler ở worker | Task được chấp nhận, không phải mọi xử lý downstream đã xong | <code>CountDownLatch</code>, output channel hoặc trạng thái worker |
| <code>QueueChannel</code> | Đưa vào queue; consumer poll bằng <code>receive()</code> | Message được queue nhận, **chưa** có nghĩa đã xử lý | <code>receive(timeout)</code> và lần xử lý của polling endpoint |
| <code>FluxMessageChannel</code> | Publisher/Reactive Streams | Tùy subscriber/demand và ranh giới reactive | Completion, <code>onError</code>, StepVerifier, backpressure |

<code>MessageChannel</code> có <code>send(message)</code> và <code>send(message, timeout)</code>. Không nên khẳng định mọi lỗi đều trả <code>false</code>: với <code>DirectChannel</code> không có subscriber hoặc handler ném exception, một <code>MessagingException</code> có thể lan về caller. Với channel có buffer, <code>false</code> thường phản ánh việc không gửi được trong thời hạn.

## 3. Các dependency và quy tắc tổ chức fixture

Với một dự án được quản lý bởi Spring Boot BOM hoặc dependency management tương thích, test thường cần:

~~~kotlin
dependencies {
    implementation("org.springframework.integration:spring-integration-core")

    testImplementation("org.springframework.integration:spring-integration-test")
    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
~~~

Đây là mảnh cấu hình Gradle Kotlin DSL **minh họa**, không phải file build hoàn chỉnh. <code>spring-integration-test</code> cung cấp hỗ trợ test Spring Integration; các utility thuần test còn có ở <code>spring-integration-test-support</code>. Các artifact transitively phụ thuộc Spring Test/Mockito ở những cấu hình được hỗ trợ, nhưng khai báo rõ dependency theo nhu cầu giúp test dễ duy trì. Dùng cùng một bộ phiên bản Spring Framework, Spring Integration, Reactor và JUnit; không trộn các nhánh 5.x/6.x tùy ý.

Test fixture nên có tên channel/endpoint **ổn định** để có thể tìm qua <code>@Qualifier</code>, thay mock và xác minh topology. Không dùng cùng tên bean cho nhiều flow trong một <code>ApplicationContext</code> test.

## 4. Test DirectChannel không cần Spring context

Đây là bài test nhỏ nhất để chứng minh dispatch **đồng bộ**. <code>DirectChannel</code> là <code>SubscribableChannel</code>, nên có thể đăng ký một <code>MessageHandler</code> trực tiếp:

~~~java
@Test
void directChannelInvokesHandlerBeforeSendReturns() {
    DirectChannel channel = new DirectChannel();
    AtomicReference<Message<?>> observed = new AtomicReference<>();
    AtomicReference<String> handlerThread = new AtomicReference<>();
    String senderThread = Thread.currentThread().getName();

    channel.subscribe(message -> {
        observed.set(message);
        handlerThread.set(Thread.currentThread().getName());
    });

    Message<String> request = MessageBuilder.withPayload("ping")
        .setHeader("correlationId", "request-42")
        .build();

    assertTrue(channel.send(request));
    assertSame(request, observed.get());
    assertEquals(senderThread, handlerThread.get());
    assertEquals("request-42",
        observed.get().getHeaders().get("correlationId"));
}
~~~

Các kiểu chính: <code>org.springframework.integration.channel.DirectChannel</code>, <code>org.springframework.messaging.Message</code>, <code>org.springframework.integration.support.MessageBuilder</code>, <code>java.util.concurrent.atomic.AtomicReference</code>. Assertion thuộc JUnit 5.

### Test exception của synchronous handler

~~~java
@Test
void synchronousHandlerFailurePropagatesToSender() {
    DirectChannel channel = new DirectChannel();
    channel.subscribe(message -> {
        throw new IllegalStateException("Downstream failed");
    });

    Message<String> request =
        MessageBuilder.withPayload("will-fail").build();

    MessagingException failure = assertThrows(
        MessagingException.class,
        () -> channel.send(request));

    assertNotNull(failure.getCause());
}
~~~

Khi dispatcher chuyển một exception không thuộc <code>MessagingException</code> thành lỗi messaging, loại wrapper và cause có thể khác theo ranh giới framework và phiên bản. Vì vậy, để assert **nghiệp vụ**, nên kiểm tra loại nguyên nhân gốc hoặc message/cause phù hợp; đừng dựa vào một chuỗi log nguyên văn.

**Anti-pattern:** Test dùng <code>DirectChannel</code> rồi cho rằng <code>ExecutorChannel</code> ở production cũng sẽ ném exception về <code>send()</code> theo cách này. Hai loại channel có completion boundary khác nhau.

## 5. Test QueueChannel: có message trong queue chưa phải đã xử lý

<code>QueueChannel</code> là <code>PollableChannel</code>. Nó phù hợp làm output quan sát trong flow test vì test thread chủ động lấy message bằng <code>receive(timeout)</code>:

~~~java
@Test
void queueChannelStoresMessageUntilReceived() {
    QueueChannel queue = new QueueChannel(1);
    Message<String> first = MessageBuilder.withPayload("first").build();
    Message<String> second = MessageBuilder.withPayload("second").build();

    assertTrue(queue.send(first));
    assertFalse(queue.send(second, 0)); // Queue đang đầy; không chờ.

    Message<?> taken = queue.receive(0);
    assertNotNull(taken);
    assertEquals("first", taken.getPayload());
    assertNull(queue.receive(0));
}
~~~

Điểm quan trọng:

- <code>receive(0)</code> là phép poll không chờ; <code>receive(5_000)</code> cho phép chờ tối đa một khoảng hữu hạn.
- <code>send(second, 0)</code> có thể trả <code>false</code> vì hàng đợi giới hạn capacity đã đầy; kết quả không chứng minh <code>second</code> có lỗi payload.
- Lấy message khỏi queue **không** có nghĩa một service activator downstream đã thực hiện nghiệp vụ. Trong mô hình poller, việc lấy message và xử lý xảy ra ở endpoint/polling task riêng.
- <code>QueueChannel</code> in-memory không trở thành persistent queue chỉ vì test sử dụng nó. Với <code>JdbcChannelMessageStore</code>, cần test transaction và redelivery riêng.

Khi một test để output message trong queue mà không drain, test tiếp theo dùng lại Spring context có thể nhận **message từ test trước**. Có thể dùng channel/fixture riêng, dọn hàng đợi trong <code>@BeforeEach</code>/<code>@AfterEach</code> hoặc đánh dấu context dirty khi thật cần.

## 6. Test PublishSubscribeChannel: fan-out và failure boundary

<code>PublishSubscribeChannel</code> không executor thường gọi các subscriber **đồng bộ**. Test tối thiểu:

~~~java
@Test
void pubSubDeliversToBothSynchronousSubscribers() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel();
    List<String> seen = new CopyOnWriteArrayList<>();

    channel.subscribe(message ->
        seen.add("audit:" + message.getPayload()));
    channel.subscribe(message ->
        seen.add("notify:" + message.getPayload()));

    assertTrue(channel.send(
        MessageBuilder.withPayload("order-42").build()));

    assertEquals(2, seen.size());
    assertTrue(seen.contains("audit:order-42"));
    assertTrue(seen.contains("notify:order-42"));
}
~~~

Test trên **không** khẳng định subscriber luôn chạy theo một thứ tự cố định. Khi bổ sung executor, error handler, <code>requireSubscribers</code> hoặc policy áp dụng trình tự, cần tạo test mới phản ánh đúng cấu hình; ví dụ một subscriber thất bại có thể khiến các subscriber còn lại có được gọi hay không tùy dispatcher/error handling.

Không mock mọi subscriber nếu mục tiêu là xác nhận **fan-out**; một fake consumer ghi nhận payload/correlation là đủ để chứng minh hai nhánh nhận message.

## 7. Test ExecutorChannel bằng latch, không dựa vào sleep

<code>ExecutorChannel</code> giao nhiệm vụ xử lý cho worker; test không được assert ngay sau <code>send()</code> rằng side effect đã hoàn tất. Dùng <code>CountDownLatch</code> để kiểm soát ranh giới chính xác:

~~~java
@Test
void executorChannelSendCanReturnBeforeHandlerCompletes()
        throws Exception {
    ExecutorService executor = Executors.newSingleThreadExecutor();
    CountDownLatch entered = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    CountDownLatch finished = new CountDownLatch(1);
    AtomicBoolean handled = new AtomicBoolean(false);

    try {
        ExecutorChannel channel = new ExecutorChannel(executor);
        channel.subscribe(message -> {
            entered.countDown();
            try {
                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Test release timeout");
                }
                handled.set(true);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            } finally {
                finished.countDown();
            }
        });

        assertTrue(channel.send(
            MessageBuilder.withPayload("async").build()));
        assertTrue(entered.await(2, TimeUnit.SECONDS));
        assertFalse(handled.get()); // Worker vẫn đang chờ release.

        release.countDown();
        assertTrue(finished.await(2, TimeUnit.SECONDS));
        assertTrue(handled.get());
    } finally {
        release.countDown();
        executor.shutdownNow();
    }
}
~~~

Thử nghiệm này chứng minh sự khác biệt giữa **task accepted** và **handler completion**, không cần <code>Thread.sleep()</code> để “hy vọng” race condition xuất hiện. Nếu production dùng <code>ThreadPoolTaskExecutor</code>, hãy để Spring quản lý shutdown hoặc đóng executor trong <code>finally</code> khi tự tạo ở test.

**Không dùng một <code>AtomicBoolean</code> vừa được assert mà không có ranh giới đồng bộ**: ví dụ trên có <code>entered.await()</code>, <code>release</code> và <code>finished.await()</code> để test đạt trạng thái có thể chứng minh.

## 8. Fixture Spring Integration Java DSL cho test endpoint–handler

Ta sẽ xây dựng một flow xử lý đơn hàng đơn giản. <code>OrderService</code> không phụ thuộc API message; <code>Service Activator</code> nhận payload, gọi service và gửi kết quả ra output channel.

**Bước 1 — hai kiểu dữ liệu và một service:**

~~~java
public record OrderCommand(String orderId, int quantity) {}
public record OrderResult(String orderId, String status) {}

public class OrderService {
    public OrderResult process(OrderCommand order) {
        if (order.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return new OrderResult(order.orderId(), "ACCEPTED");
    }
}
~~~

**Bước 2 — cấu hình context riêng cho test:**

~~~java
@Configuration
@EnableIntegration
public class OrderFlowTestConfig {

    @Bean
    OrderService orderService() {
        return new OrderService();
    }

    @Bean(name = "orders.in")
    MessageChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean(name = "orders.out")
    PollableChannel ordersOut() {
        return new QueueChannel(20);
    }

    @Bean
    IntegrationFlow orderFlow(OrderService service) {
        return IntegrationFlow.from("orders.in")
            .handle(service, "process",
                endpoint -> endpoint.id("orders.process.endpoint"))
            .channel("orders.out")
            .get();
    }
}
~~~

Import chính: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.config.EnableIntegration</code>, <code>org.springframework.integration.channel.DirectChannel</code>/<code>QueueChannel</code>, <code>org.springframework.messaging.MessageChannel</code>/<code>PollableChannel</code> và <code>org.springframework.context.annotation.Configuration</code>/<code>Bean</code>.

<code>endpoint.id("orders.process.endpoint")</code> là tên endpoint được dùng ở phần mock handler, không nhất thiết bằng tên bean service <code>orderService</code>. Đây là điểm cực kỳ quan trọng khi dùng <code>MockIntegrationContext.substituteMessageHandlerFor(...)</code>.

## 9. Flow integration test: payload, reply và lỗi

<code>@SpringJUnitConfig</code> khởi tạo Spring TestContext tích hợp JUnit Jupiter; <code>@SpringIntegrationTest</code> bổ sung tiện ích riêng của Spring Integration.

~~~java
@SpringJUnitConfig(OrderFlowTestConfig.class)
@SpringIntegrationTest
class OrderFlowIntegrationTest {

    @Autowired
    @Qualifier("orders.in")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.out")
    PollableChannel output;

    @Test
    void validOrderProducesExpectedReplyAndCorrelation() {
        Message<OrderCommand> request = MessageBuilder
            .withPayload(new OrderCommand("O-301", 2))
            .setHeader("correlationId", "checkout-301")
            .build();

        assertTrue(input.send(request));

        Message<?> reply = output.receive(1_000);
        assertNotNull(reply);
        assertEquals(new OrderResult("O-301", "ACCEPTED"),
            reply.getPayload());
        assertEquals("checkout-301",
            reply.getHeaders().get("correlationId"));
        assertNull(output.receive(0));
    }

    @Test
    void invalidOrderPropagatesExceptionAndEmitsNoReply() {
        Message<OrderCommand> request = MessageBuilder
            .withPayload(new OrderCommand("O-302", 0))
            .build();

        assertThrows(MessagingException.class,
            () -> input.send(request));
        assertNull(output.receive(0));
    }
}
~~~

Các annotation: <code>org.springframework.test.context.junit.jupiter.SpringJUnitConfig</code>, <code>org.springframework.integration.test.context.SpringIntegrationTest</code>, <code>org.springframework.beans.factory.annotation.Autowired</code>/<code>Qualifier</code>. <code>MessagingException</code> thuộc <code>org.springframework.messaging</code>.

**Vì sao test này có giá trị?** Nó kiểm tra wiring bean, dispatch qua <code>DirectChannel</code>, gọi Service Activator đúng method, tạo reply và bảo toàn header correlation khi framework xây dựng message trả về. Nó không kiểm tra transaction của database hay ACK của một broker, vì fixture không chứa những thành phần đó.

Đối với error test, framework có thể wrap lỗi nghiệp vụ trong <code>MessagingException</code>; cần kiểm tra thêm chuỗi cause nếu muốn xác nhận lý do <code>quantity</code>. Không nên khóa test vào stack trace text không ổn định giữa phiên bản.

## 10. Thay handler bằng MockIntegrationContext

Khi muốn test **wiring và routing** nhưng không gọi service thật (có thể truy cập DB hoặc HTTP), Spring Integration hỗ trợ <code>MockIntegrationContext</code> và <code>MockMessageHandler</code>.

<code>@SpringIntegrationTest</code> đăng ký <code>MockIntegrationContext</code> trong test context. <code>substituteMessageHandlerFor(endpointId, mockHandler)</code> nhận **ID của consumer endpoint**, không phải tên tùy ý của method hoặc tên <code>MessageChannel</code>.

~~~java
@SpringJUnitConfig(OrderFlowTestConfig.class)
@SpringIntegrationTest
class MockedHandlerFlowTest {

    @Autowired
    MockIntegrationContext mockContext;

    @Autowired
    @Qualifier("orders.in")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.out")
    PollableChannel output;

    @AfterEach
    void resetMocks() {
        mockContext.resetBeans();
    }

    @Test
    void canSubstituteConsumerHandlerWithoutCallingRealService() {
        ArgumentCaptor<Message<?>> captured =
            MockIntegration.messageArgumentCaptor();

        MockMessageHandler fake = MockIntegration
            .mockMessageHandler(captured)
            .handleNextAndReply(message -> {
                OrderCommand order =
                    (OrderCommand) message.getPayload();
                return new OrderResult(order.orderId(), "MOCKED");
            });

        mockContext.substituteMessageHandlerFor(
            "orders.process.endpoint", fake);

        Message<OrderCommand> request = MessageBuilder
            .withPayload(new OrderCommand("O-303", 1))
            .build();

        assertTrue(input.send(request));
        Message<?> reply = output.receive(1_000);

        assertNotNull(reply);
        assertEquals(new OrderResult("O-303", "MOCKED"),
            reply.getPayload());
        assertSame(request, captured.getValue());
    }
}
~~~

Các kiểu thuộc <code>org.springframework.integration.test.context.MockIntegrationContext</code>, <code>org.springframework.integration.test.mock.MockIntegration</code>/<code>MockMessageHandler</code>, <code>org.mockito.ArgumentCaptor</code> và JUnit 5 <code>@AfterEach</code>.

<code>handleNextAndReply(...)</code> mô phỏng request–reply; với consumer one-way nên dùng <code>handleNext(...)</code>. Các callback được áp dụng cho những message tiếp theo theo thứ tự đã khai báo và callback cuối có thể được tái sử dụng khi còn message. Nếu test cần kiểm tra số lần gọi, dùng <code>ArgumentCaptor.getAllValues()</code> hoặc các assertion interaction phù hợp.

**Vì sao phải <code>resetBeans()</code>?** Spring TestContext có thể tái sử dụng <code>ApplicationContext</code> giữa các test. Không reset khiến test kế tiếp vẫn chạy fake handler thay vì handler thật, tạo lỗi phụ thuộc thứ tự test. <code>resetBeans()</code> khôi phục cấu hình ban đầu của endpoint đã được thay thế.

### Các trường hợp nên và không nên mock handler

| Mục tiêu | Nên mock? | Lý do |
|---|---|---|
| Kiểm tra router đưa message tới đúng endpoint | Có | Chặn side effect thật, xác nhận message đến đích |
| Kiểm tra service validation và mapping | Không mock chính service đang được kiểm tra | Nếu không chỉ kiểm tra hành vi fake |
| Kiểm tra error channel khi downstream ném lỗi | Có thể | Fake handler ném lỗi có chủ đích; phải kiểm tra đúng thread boundary |
| Kiểm tra transaction + DB rollback thực | Không đủ | Mock không chứng minh transaction của database |
| Kiểm tra retry advice quanh handler | Có thể, với mock lỗi n lần | Kiểm soát số attempt, nhưng cần test integration riêng cho side effect |

## 11. Không khởi động inbound adapter thật trong test

Một context chứa inbound adapter Kafka/JMS/JDBC hoặc scheduler có thể kết nối tới hệ thống ngoài **ngay khi test khởi tạo**. Để test channel/handler, không nhất thiết khởi động toàn bộ nguồn thực.

~~~java
@SpringJUnitConfig(ProductionLikeFlowConfig.class)
@SpringIntegrationTest(
    noAutoStartup = { "externalInboundAdapter", "*PollingSource*" })
class IsolatedFlowTest {

    @Autowired
    MockIntegrationContext mocks;

    // Test sẽ chủ động gửi message vào input channel trong context.
}
~~~

<code>noAutoStartup</code> dùng pattern matching đơn giản theo endpoint ID: <code>xxx*</code>, <code>xxx</code>, <code>*xxx</code>, <code>xxx*yyy</code>. Nó ngăn những endpoint khớp pattern tự start trong vòng đời của test; không tắt các handler/channel khác không nằm trong pattern.

Khi muốn thay nguồn nhận theo lịch, có thể dùng:

~~~java
mocks.substituteMessageSourceFor(
    "externalInboundAdapter",
    MockIntegration.mockMessageSource("test-payload"));
~~~

Đây là đoạn trong một test **đã có** <code>SourcePollingChannelAdapter</code> mang bean ID <code>externalInboundAdapter</code>, không phải API để tự tạo endpoint mới. Sau khi thay source, phải chủ động start endpoint hoặc cho scheduler chạy theo cấu hình test, và reset bean sau test. Từ Spring Integration **6.3**, <code>MockIntegrationContext.substituteTriggerFor(...)</code> còn cho phép thay trigger polling thật bằng trigger dành cho test.

**Không dùng test chạy poller mỗi vài giây rồi <code>Thread.sleep(10_000)</code> để chờ.** Có thể làm trigger chạy một lần, test trực tiếp polling source, hoặc dùng latch/queue kết hợp timeout. Điều này giúp test nhanh, ổn định và không chờ vô ích.

## 12. ChannelInterceptor để quan sát mà không thay handler

Khi test việc bổ sung header hoặc tính chất của việc gửi message vào một channel, có thể đăng ký <code>ChannelInterceptor</code> trên channel:

~~~java
@Test
void channelInterceptorSeesMessageAtSendBoundary() {
    DirectChannel channel = new DirectChannel();
    AtomicReference<Message<?>> intercepted = new AtomicReference<>();
    AtomicReference<Message<?>> delivered = new AtomicReference<>();

    channel.addInterceptor(new ChannelInterceptor() {
        @Override
        public Message<?> preSend(Message<?> message, MessageChannel ch) {
            intercepted.set(message);
            return message;
        }
    });

    channel.subscribe(delivered::set);

    Message<String> request = MessageBuilder.withPayload("data")
        .setHeader("correlationId", "corr-77")
        .build();

    channel.send(request);

    assertSame(request, intercepted.get());
    assertSame(request, delivered.get());
}
~~~

<code>ChannelInterceptor</code> thuộc <code>org.springframework.messaging.support</code>. Test kiểm tra boundary của channel nhưng không biết một outbound adapter khác có ACK dữ liệu hay không.

Nếu muốn kiểm tra interceptor **thay đổi message** (ví dụ thêm header), hãy assert trên message **thực sự đến subscriber**, không chỉ message mà interceptor quan sát ở <code>preSend()</code>.

## 13. Test lỗi: đồng bộ và bất đồng bộ là hai hợp đồng khác

### 13.1. DirectChannel: caller nhìn thấy exception

Trong fixture mục 9, input là <code>DirectChannel</code>. Test có thể <code>assertThrows(MessagingException.class, ...)</code> khi service activator ném lỗi runtime. Đây là chứng minh exception đi ngược synchronous call stack, không phải chứng minh global <code>errorChannel</code> đã nhận lỗi.

### 13.2. ExecutorChannel/poller: lỗi có thể xuất hiện ở worker

Nếu handler chạy trên executor, sender có thể đã nhận <code>send() == true</code> trước khi lỗi phát sinh. Phải kiểm tra **cơ chế báo lỗi được cấu hình**, ví dụ error handler/error channel của Spring Integration hoặc container/adapter error flow:

~~~text
Sender ──send() accepted──> ExecutorChannel
                               │
                               ▼
                          Worker thread
                               │
                          handler fails
                               │
                               ▼
                     Error handler / ErrorMessage
                               │
                               ▼
                        test error sink
~~~

Để test, thay handler bằng fake ném exception, cấu hình error channel đúng boundary và dùng <code>QueueChannel</code> làm error sink. Assert <code>ErrorMessage</code> chứa <code>Throwable</code> cùng thông tin original/failed message nếu được producer đưa vào. **Không nên giả định** mọi <code>ExecutorChannel</code> tự publish lỗi tới một queue tên tùy ý khi chưa cấu hình.

| Lỗi | Điều cần xác nhận |
|---|---|
| Lỗi conversion/transformer trước handler | Handler không được gọi; lỗi xuất hiện tại đúng upstream boundary |
| Handler ném exception đồng bộ | Caller hoặc gateway nhận lỗi theo semantics của <code>DirectChannel</code> |
| Handler lỗi sau async handoff | Error flow hoặc worker logging nhận lỗi; sender không bị assert sai |
| Retry hết lượt | Số attempt đúng, lỗi cuối được propagate/recover theo policy |
| Recovery nuốt exception | Được chấp nhận có chủ đích, không bị hiểu là xử lý nghiệp vụ thành công |
| Error flow cũng ném exception | Có quan sát lỗi thứ cấp, không làm test treo vô hạn |

Một <code>ErrorMessage</code> đã được publish **không chứng minh** message nguồn đã rollback, chưa ACK hoặc được redeliver. Muốn xác nhận các tình huống ấy phải test chính message source/adapter và transaction của nó.

## 14. Test retry và transaction quanh handler

Giả sử service có thể gặp lỗi tạm thời. <code>RequestHandlerRetryAdvice</code> bao quanh handler invocation; cần test số lần gọi và kết quả sau retry.

### Kịch bản retry thành công

1. Tạo fake service hoặc handler trả lỗi transient ở hai lần đầu.
2. Cấu hình retry policy tối đa ba attempt; backoff của test bằng 0 hoặc rất ngắn để không kéo dài suite.
3. Gửi một message vào endpoint có advice.
4. Xác nhận service được gọi **ba lần**, output chỉ có một kết quả hợp lệ.
5. Xác nhận không phát duplicate side effect khi attempt trước đã ghi một phần dữ liệu.

### Kịch bản retry thất bại

1. Fake luôn ném lỗi transient.
2. Xác nhận dừng đúng attempt count; không retry vô hạn.
3. Với flow đồng bộ, assert exception; với async, assert error sink/recovery.
4. Kiểm tra message/correlation ID vẫn có thể nhận diện qua error.

**Điểm quan trọng:** Nếu test chỉ xác minh số lần gọi mock, nó không chứng minh **transaction được tạo mới cho mỗi retry**. Một transaction bao ngoài nhiều attempt có thể đã bị đánh dấu rollback-only sau attempt đầu. Muốn chứng minh rollback, dùng database thật hoặc Testcontainers cùng transaction manager thực và đọc dữ liệu **sau khi giao dịch đã kết thúc**.

| Ranh giới cần test | Chọn cách kiểm thử |
|---|---|
| Handler validation, kết quả Java | Unit test trực tiếp |
| Retry advice + dispatch + số attempt | Flow test, fake handler/repository |
| JDBC commit/rollback khi downstream ném lỗi | Integration test với DB và manager thật |
| Rollback message receive ở transactional queue | Test persistent channel/store và poller transaction |
| ACK/requeue/DLQ ở Kafka/JMS/AMQP | Test adapter/container/broker phù hợp |
| Idempotency sau redelivery | Tạo duplicate với cùng business event ID, assert chỉ một side effect |

**Tránh <code>@Transactional</code> trên chính test** nếu mục tiêu là kiểm tra transaction do production facade/poller hoàn tất. Outer test transaction có thể khiến dữ liệu được rollback sau test và che giấu thời điểm commit/rollback thật của flow.

## 15. Test correlation, message headers và group store

Ngay cả khi bài chỉ tập trung channel và handler, một message có thể mang các header quyết định flow:

| Header/định danh | Mục tiêu test | Sai lầm thường gặp |
|---|---|---|
| <code>MessageHeaders.ID</code> | Có ID hợp lệ cho từng message | So ID tuyệt đối giữa các message được rebuild |
| <code>MessageHeaders.TIMESTAMP</code> | Có timestamp trong điều kiện hỗ trợ | Assert thời gian bằng đúng một giá trị mili giây |
| <code>correlationId</code> | Header đi qua transformer/handler theo hợp đồng | Coi correlation ID là transaction ID |
| <code>replyChannel</code> | Gateway hoặc handler trả reply về đúng đích | Quên cấu hình reply khi test request–reply |
| <code>errorChannel</code> | Đường lỗi được định tuyến đúng boundary | Giả định header tự khiến mọi exception chuyển thành ErrorMessage |
| Business event ID | Idempotency qua retry/redelivery | Dùng message ID mới làm idempotency key |

Với aggregator, có thể gửi các fragment **cùng correlation key**, xác nhận chưa có output khi thiếu, rồi gửi phần cuối và assert **một** group được release. Test nên kiểm tra cả message đến muộn, group timeout và store cleanup. Nếu dùng <code>SimpleMessageStore</code> trong test, kết quả chưa chứng minh được behavior qua restart; với <code>JdbcMessageStore</code>, cần test nhiều application context dùng cùng backend và dữ liệu.

**Đừng assert một header nhất định được truyền qua mọi adapter nếu chưa có hợp đồng.** Một số transformer/service activator tạo message mới, một số transport mapper có chính sách lọc header. Test phải đặt header ở input và xác nhận nơi nhận được đúng trường cần thiết.

## 16. Test poller và lifecycle không dùng thời gian chờ tùy tiện

Một polling consumer bắt đầu bằng task scheduler hoặc trigger. Nếu test chỉ đợi <code>Thread.sleep(500)</code> rồi nhận message, nó dễ fail trên CI chậm hoặc máy đang tải.

Hướng thiết kế ổn định hơn:

- Dùng <code>@SpringIntegrationTest(noAutoStartup = ...)</code> để không chạy adapter thật trong lúc khởi tạo fixture.
- Thay <code>MessageSource</code> bằng <code>MockIntegration.mockMessageSource(...)</code> hoặc <code>MessageSource</code> tự viết có đếm lượt nhận.
- Điều chỉnh trigger dành cho test; từ Spring Integration 6.3 có <code>substituteTriggerFor(...)</code> trên <code>MockIntegrationContext</code>.
- Đặt <code>maxMessagesPerPoll</code> và output queue rõ ràng; assert số message đã nhận và không có lần poll phụ ngoài dự kiến.
- Test start/stop qua endpoint <code>SmartLifecycle</code> hoặc flow registration; assert <code>isRunning()</code> và việc không có **poll mới** sau stop, đồng thời xử lý in-flight task theo policy.

Test lifecycle cần nhận biết <code>stop()</code> không nhất thiết đợi mọi task executor đã được giao chạy xong. Không assert queue đã rỗng ngay lập tức chỉ vì endpoint báo <code>isRunning() == false</code>.

## 17. TestUtils và kiểm tra cấu hình nội bộ

<code>spring-integration-test-support</code> cung cấp <code>TestUtils</code>. Khi cần kiểm tra cấu hình dispatcher hay nội bộ bean mà không có getter công khai:

~~~java
LoadBalancingStrategy strategy = TestUtils.getPropertyValue(
    directChannel,
    "dispatcher.loadBalancingStrategy",
    LoadBalancingStrategy.class);

assertNotNull(strategy);
~~~

<code>TestUtils</code> thuộc <code>org.springframework.integration.test.util</code>; <code>LoadBalancingStrategy</code> thuộc <code>org.springframework.integration.dispatcher</code>. <code>getPropertyValue()</code> dùng <code>DirectFieldAccessor</code> và hỗ trợ đường dẫn field lồng nhau.

**Cảnh báo:** Đây là kiểm tra implementation detail. Khi nâng version framework, tên field hoặc dispatcher có thể đổi dù hành vi bên ngoài không đổi. Hãy ưu tiên behavioral test trên message/callback trước, chỉ dùng <code>TestUtils</code> cho những thuộc tính thật sự cần xác nhận ở mức cấu hình.

## 18. Những nguyên nhân khiến test channel/handler bị flaky

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Test chạy riêng pass, chạy cả suite fail | Spring context được cache, mock handler không reset, queue còn message | <code>resetBeans()</code>, fixture cô lập và drain queue theo cleanup |
| <code>assertThrows()</code> không thấy lỗi | Handler chạy async hoặc có recovery advice | Kiểm tra thread boundary, error sink và chính sách recovery |
| <code>receive()</code> trả <code>null</code> | Endpoint chưa start, message bị route khác, worker chưa chạy hoặc không có output | Kiểm tra topology/endpoint lifecycle; chờ điều kiện với timeout |
| Test treo mãi | <code>receive()</code> không timeout, deadlock, poller chờ source | Dùng hạn chờ rõ ràng và log state khi hết hạn |
| Message đầu tiên của test sau chứa dữ liệu test trước | Shared <code>QueueChannel</code> không được dọn | Dùng unique correlation, drain/reset fixture |
| Verify mock sai số lần | Retry, subscriber fan-out, polling lặp lại | Xác định logical message và attempt count |
| Correlation ID khác mong đợi | Transformer rebuild message, adapter header mapper loại header | Kiểm tra contract của từng bước và header propagation |
| Throughput test dao động mạnh | Dựa vào <code>Thread.sleep</code> hoặc scheduler thật | <code>CountDownLatch</code>, trigger kiểm soát, virtual time khi phù hợp |
| Test DB thấy dữ liệu “biến mất” | Outer test transaction rollback | Đọc state sau boundary production commit; không lồng test transaction thiếu chủ đích |
| Test dùng fake vẫn kết nối broker | Inbound adapter tự startup trước khi mock | <code>noAutoStartup</code>, fixture context hoặc test profile |

### Quy trình debug một test thất bại

1. Xác minh input channel trong test **đúng bean** mà endpoint subscribe.
2. Kiểm tra endpoint ID, trạng thái running, số subscriber và cấu hình routing.
3. Xác định <code>DirectChannel</code> hay async/pollable boundary; xem <code>send()</code> có thể hoàn tất sớm không.
4. Đọc message trên output sink cùng payload, headers, message ID và correlation.
5. Nếu không có output, kiểm tra error sink, exception cause, retry count và poller scheduler.
6. Kiểm tra mock/queue/context có còn trạng thái từ test trước hay không.
7. Nếu có transaction hoặc broker, tìm bằng chứng commit/ACK/redelivery thực thay vì suy từ log handler.

## 19. Checklist cho bộ test đáng tin cậy

- [ ] Mỗi test nêu rõ completion boundary: gửi thành công, handler hoàn tất, reply có mặt hay transaction commit.
- [ ] Test <code>DirectChannel</code> chứng minh dispatch đồng bộ và exception propagation.
- [ ] Test <code>QueueChannel</code> chứng minh capacity/send/receive; không coi enqueue là xử lý nghiệp vụ.
- [ ] Test <code>ExecutorChannel</code> dùng latch/future và timeout hữu hạn thay vì ngủ tùy tiện.
- [ ] Flow test qua Spring context xác nhận wiring handler, payload, header và output/error channel.
- [ ] Khi mock endpoint, dùng đúng endpoint ID và khôi phục bằng <code>MockIntegrationContext.resetBeans()</code>.
- [ ] Inbound adapter thật được cô lập bằng <code>noAutoStartup</code> hoặc test profile khi không cần hạ tầng ngoài.
- [ ] Retry và transaction có test riêng cho số attempt, side effect trùng, rollback và exception cuối.
- [ ] Message store, poller, broker ACK/requeue và nhiều thread được kiểm thử ở tầng integration phù hợp.
- [ ] Test dọn channel state, context, executor, scheduler và mock sau mỗi ca.
- [ ] Logs/traces hiển thị correlation và endpoint/thread; test không phụ thuộc message ID hoặc timestamp ngẫu nhiên.
- [ ] Các assertion bất đồng bộ dùng chờ theo điều kiện có deadline và báo chẩn đoán hữu ích khi hết hạn.

**Kết luận:** Kiểm thử Spring Integration ở runtime là kiểm thử **hợp đồng của channel và endpoint**, không chỉ method nghiệp vụ. <code>DirectChannel</code> cho một ranh giới đồng bộ dễ assert; <code>QueueChannel</code> giúp quan sát message đang chờ; <code>ExecutorChannel</code> buộc test phân biệt send với completion. Khi kết hợp <code>@SpringIntegrationTest</code>, <code>MockIntegrationContext</code>, các fake handler/source và những test transaction–retry–correlation riêng, ta có thể phát hiện sai sót về threading, error routing và lifecycle trước khi triển khai message flow thật.

## Tài liệu tham khảo

- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration Reference — Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration 6.5 Javadoc — MockIntegrationContext](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/test/context/MockIntegrationContext.html)
- [Spring Integration 6.5 Javadoc — MockIntegration](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/test/mock/MockIntegration.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)

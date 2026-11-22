# Scheduler trong reactive pipeline

Trong một integration flow, cùng một message có thể được xử lý bởi inbound adapter, channel, transformer, service activator rồi tới downstream consumer. Với flow đồng bộ, ta thường lần theo một call stack Java. Với **reactive pipeline** dùng Project Reactor, việc tạo <code>Flux</code>/<code>Mono</code>, đăng ký <code>subscribe()</code> và xử lý tín hiệu có thể diễn ra ở những thời điểm hoặc thread khác nhau. Vì vậy, khi debug một lỗi “handler không chạy”, “flow bị nghẽn” hoặc “transaction đã commit nhưng downstream chưa hoàn tất”, cần xác định **Scheduler nào đang điều phối phần việc nào**.

Bài thuộc chương **Reactive runtime** của module **SPRING_INTEGRATION_RUNTIME**. Mục tiêu là sử dụng đúng Reactor <code>Scheduler</code> và các toán tử <code>subscribeOn()</code>, <code>publishOn()</code> trong Spring Integration; phân biệt chúng với <code>TaskScheduler</code> của poller và <code>TaskExecutor</code> của channel, đồng thời xử lý backpressure, blocking I/O, transaction, retry, error handling, correlation, lifecycle và quan sát hiệu năng.

> **Nguyên tắc:** Reactive không đồng nghĩa với “tự động đa luồng”. <code>Flux</code> hoặc <code>Mono</code> có thể chạy ngay trên thread của subscriber; chỉ khi nguồn, toán tử hoặc một ranh giới runtime dùng Scheduler/async API thì nơi thực thi mới thay đổi.

## 1. Ba câu hỏi phải tách biệt

Khi nhìn một pipeline, hãy trả lời ba câu hỏi:

1. **Ai kích hoạt xử lý?** <code>subscribe()</code> từ subscriber, một inbound protocol, một reactive consumer hoặc framework khi endpoint khởi động.
2. **Đoạn xử lý chạy ở đâu?** Thread của caller, worker của Reactor <code>Scheduler</code>, <code>TaskExecutor</code> của Spring Integration hay thread do client bất đồng bộ quản lý.
3. **Khi nào được phép phát tiếp?** Theo <code>request(n)</code> của Reactive Streams, capacity/buffer, hoặc chính sách giao message của adapter/channel.

~~~mermaid
flowchart LR
    P["Publisher<br/>Flux / Mono"] --> S["subscribe + request(n)"]
    S --> O1["Operator phía nguồn"]
    O1 --> SCH["publishOn(Scheduler)"]
    SCH --> O2["Operator phía sau"]
    O2 --> R["Reactive subscriber / endpoint"]
    R -. "request(n)" .-> P
    S -. "subscribeOn có thể đổi thread đăng ký" .-> O1
~~~

Hình chỉ minh họa luồng tín hiệu và nhu cầu: <code>request(n)</code> được truyền qua các operator theo cơ chế của Reactor, không phải một lời gọi trực tiếp đơn giản từ consumer cuối đến nguồn như mũi tên rút gọn.

### Reactor Scheduler khác Spring TaskScheduler và TaskExecutor

| Thành phần | Dùng để làm gì? | Ví dụ |
|---|---|---|
| <code>reactor.core.scheduler.Scheduler</code> | Lập lịch tác vụ Reactor, điều phối tín hiệu theo <code>publishOn</code>/<code>subscribeOn</code>, cung cấp clock cho một số toán tử | <code>Schedulers.parallel()</code>, <code>Schedulers.boundedElastic()</code> |
| <code>org.springframework.scheduling.TaskScheduler</code> | Lên lịch tác vụ theo thời gian/trigger trong Spring | Poller, scheduled task, <code>ThreadPoolTaskScheduler</code> |
| <code>org.springframework.core.task.TaskExecutor</code> | Thực thi <code>Runnable</code> bằng cơ chế executor | <code>ExecutorChannel</code>, <code>ThreadPoolTaskExecutor</code> |
| <code>FluxMessageChannel</code> | Channel tham gia Reactive Streams và cung cấp <code>Publisher&lt;Message&lt;?&gt;&gt;</code> | Đưa message đến <code>ReactiveStreamsConsumer</code> theo demand |

Chúng có thể được nối với nhau nhưng **không cùng một API**. Ví dụ <code>Schedulers.fromExecutorService(...)</code> bọc một <code>ExecutorService</code> thành Reactor Scheduler, song không biến <code>TaskScheduler</code> thành <code>FluxMessageChannel</code> hay tự truyền transaction qua thread.

## 2. Reactor không tự tạo thread khi xây dựng Mono/Flux

Xem ví dụ:

~~~java
Flux<Integer> pipeline = Flux.range(1, 3)
    .map(n -> {
        log.info("map n={}, thread={}", n, Thread.currentThread().getName());
        return n * 10;
    });

// Chỉ tới đây mới đăng ký và bắt đầu xử lý.
pipeline.subscribe(result -> log.info("result={}", result));
~~~

Nếu không có toán tử tự lập lịch, callback và <code>map()</code> thường chạy trên **thread gọi <code>subscribe()</code>**. Tạo biến <code>pipeline</code> chưa thực hiện phép nhân hay gọi nguồn. Với publisher *cold*, mỗi subscription có thể kích hoạt lại tác vụ từ nguồn; với nguồn *hot*, việc tạo/đăng ký có semantics khác và có thể phát tín hiệu độc lập với một subscriber cụ thể.

Một số toán tử như <code>delayElements()</code>, <code>interval()</code> có cơ chế lập lịch riêng và đôi khi dùng scheduler mặc định. Do đó, không nên đoán thread chỉ từ chỗ có <code>Flux</code>: cần xem **nguồn**, **operator** và **thread boundary** thực tế.

## 3. publishOn() và subscribeOn(): cùng đổi thread nhưng khác phạm vi

### 3.1. publishOn() chuyển nơi xử lý tín hiệu ở downstream

<code>publishOn(scheduler)</code> chuyển các tín hiệu sau điểm đặt operator sang một worker của Scheduler được chọn. Những operator downstream kế tiếp thường chạy trên worker đó cho tới khi gặp một <code>publishOn()</code> khác hoặc một toán tử/nguồn tự quản lý việc lập lịch.

~~~java
Scheduler downstream = Schedulers.newSingle("order-downstream");

try {
    Flux.just("A", "B")
        .map(s -> {
            log.info("before publishOn: {}", Thread.currentThread().getName());
            return s;
        })
        .publishOn(downstream)
        .map(s -> {
            log.info("after publishOn: {}", Thread.currentThread().getName());
            return s.toLowerCase(Locale.ROOT);
        })
        .blockLast(); // Chỉ dùng ở demo/điểm kiểm thử bên ngoài reactive worker.
} finally {
    downstream.dispose();
}
~~~

<code>publishOn()</code> không tự biến mỗi phần tử thành một tác vụ song song độc lập. Nó thường duy trì thứ tự tín hiệu <code>onNext</code> trong một subscription trên worker được chọn. Tên Scheduler là <code>parallel</code> cũng **không** đồng nghĩa một Flux duy nhất được <code>publishOn(Schedulers.parallel())</code> sẽ tự tách mọi phần tử sang nhiều core.

### 3.2. subscribeOn() đổi bối cảnh đăng ký và tác vụ nguồn

<code>subscribeOn(scheduler)</code> tác động quá trình subscribe/request về phía nguồn, thường phù hợp để chuyển một nguồn đồng bộ hoặc blocking sang worker khác:

~~~java
Mono<Customer> customer = Mono.fromCallable(
        () -> legacyJdbcRepository.loadCustomer("C-42"))
    .subscribeOn(Schedulers.boundedElastic());

// Khi có subscriber, callable được thực thi trên boundedElastic.
// Không thực hiện JDBC tại thời điểm khai báo biến customer.
~~~

Nên đặt <code>subscribeOn()</code> gần nguồn cần được cô lập để người đọc hiểu ranh giới. Trong một chuỗi có nhiều <code>subscribeOn()</code>, việc thêm chúng liên tiếp không làm một nguồn có nhiều subscription độc lập; thường chỉ tạo thêm chuyển thread không cần thiết. <code>publishOn()</code> downstream vẫn có thể đổi bối cảnh lần nữa.

### 3.3. Ví dụ kết hợp hai toán tử

~~~java
Flux<String> flow = Flux.range(1, 3)
    .map(i -> {
        trace("source-map", i);
        return "order-" + i;
    })
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(orderId -> {
        trace("validate", orderId);
        return orderId;
    });
~~~

Đoạn <code>source-map</code> thường thực thi trong bounded-elastic worker; đoạn <code>validate</code> sau <code>publishOn</code> được thực thi trên parallel worker. Hàm <code>trace</code> là hàm logging minh họa do ứng dụng cung cấp, không phải API của Spring Integration.

| Phạm vi | <code>subscribeOn()</code> | <code>publishOn()</code> |
|---|---|---|
| Mục tiêu | Chuyển subscription/source work sang scheduler khác | Chuyển tín hiệu downstream từ vị trí operator |
| Vị trí đặt | Thường gần source để rõ nghĩa | Đặt đúng trước đoạn cần đổi bối cảnh |
| Tác động đến operator trước nó | Có thể ảnh hưởng việc subscribe/emit từ source | Không đổi thread của operator upstream đã phát |
| Nhiều lần trong cùng chain | Thường không tăng ích lợi, có thể tốn thêm chuyển thread | Mỗi lần tạo một boundary mới |
| Dùng cho blocking legacy source | Thường dùng với <code>Mono.fromCallable(...)</code> + <code>boundedElastic</code> | Có thể cô lập downstream blocking callback; cần đảm bảo không block event-loop ở upstream |
| Tự đảm bảo parallelism theo phần tử? | Không | Không |

## 4. Chọn Scheduler theo đặc tính công việc

Project Reactor cung cấp nhiều loại Scheduler; lựa chọn sai có thể làm nghẽn event loop, giữ thread quá lâu hoặc khiến backpressure không hiệu quả.

| Scheduler | Phù hợp | Không nên dùng để |
|---|---|---|
| <code>Schedulers.immediate()</code> | Chạy ngay trên thread hiện hành, không tách execution context | Cô lập blocking I/O |
| <code>Schedulers.single()</code> | Công việc cần một luồng xử lý tuần tự, ngắn | Gọi JDBC, file I/O chậm, HTTP blocking kéo dài |
| <code>Schedulers.parallel()</code> | CPU-bound ngắn và non-blocking; số worker thường dựa trên CPU | Thực hiện <code>block()</code> hoặc JDBC blocking |
| <code>Schedulers.boundedElastic()</code> | Bao bọc I/O blocking bất khả tránh, thư viện legacy đồng bộ | Biến workload thành “non-blocking thật” hay chịu tải vô hạn |
| <code>Schedulers.newBoundedElastic(...)</code> | Tạo pool có giới hạn riêng cho một integration workload | Mở mới cho từng message mà không quản lý vòng đời |
| <code>Schedulers.fromExecutorService(...)</code> | Tích hợp một <code>ExecutorService</code> đã được quản trị | Tự động bảo toàn mọi semantics Reactive Streams |

**<code>boundedElastic()</code> là pool có giới hạn**, bao gồm giới hạn số thread và task chờ. Nó giúp cô lập đoạn blocking khỏi thread non-blocking, nhưng khi pool đầy, độ trễ tăng và có thể xuất hiện task rejection. Từ Reactor 3.6, nó có thể dùng Java 21 virtual threads nếu runtime và cấu hình hệ thống tương ứng được bật; không nên mặc định điều đó trong ứng dụng Java 17.

Các lời gọi <code>Mono.block()</code>, <code>Flux.blockLast()</code> trên thread thuộc <code>parallel</code> hoặc <code>single</code> mặc định có thể ném <code>IllegalStateException</code> do đây là các worker được đánh dấu non-blocking. Dù có chạy được <code>Thread.sleep()</code> trên một số thread, nó vẫn làm giảm throughput và phá mục tiêu thiết kế reactive.

### Quy tắc lựa chọn nhanh

- Nguồn là R2DBC, WebClient hoặc reactive driver thật: **duy trì API non-blocking**, chỉ đổi scheduler khi cần một ranh giới quan sát/điều phối cụ thể.
- Nguồn là <code>JdbcTemplate</code> hoặc REST client đồng bộ: dùng <code>Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())</code>, có giới hạn concurrency và timeout.
- Việc tính toán rất ngắn: có thể giữ ngay trên thread phát tín hiệu; không thêm <code>publishOn</code> chỉ để “nhìn thấy thread khác”.
- CPU-heavy cần parallelism thực sự: phân rã công việc có giới hạn bằng <code>flatMap</code> hoặc Reactor <code>parallel().runOn(...).sequential()</code>, đánh giá ordering và hiệu năng trước khi chọn.

## 5. Reactive endpoint trong Spring Integration đổi Scheduler thế nào?

Spring Integration có hai mảnh liên quan:

1. <code>FluxMessageChannel</code> là <code>MessageChannel</code> đồng thời tham gia <code>Publisher&lt;Message&lt;?&gt;&gt;</code> và <code>ReactiveStreamsSubscribableChannel</code>. Consumer theo Reactive Streams có thể yêu cầu message theo demand.
2. <code>ReactiveStreamsConsumer</code> là consumer endpoint của Spring Integration được xây dựng theo mô hình reactive, nối handler vào chuỗi subscriber/operator.

Từ Spring Integration 5.5, <code>ConsumerEndpointSpec.reactive(...)</code> cho phép biến endpoint thành reactive consumer **ngay cả khi input channel không phải <code>FluxMessageChannel</code>**. Callback nhận <code>Flux&lt;Message&lt;?&gt;&gt;</code> để thêm operator, chẳng hạn <code>publishOn</code>, logging, metrics hoặc logic khác.

### Ví dụ Java DSL: transformer xử lý trên parallel Scheduler

Ví dụ dùng Java 17+, Spring Integration 6.x và Reactor:

~~~java
@Configuration
@EnableIntegration
public class ReactiveNumberFlowConfig {

    @Bean(name = "numbers.input")
    MessageChannel numbersInput() {
        return new DirectChannel();
    }

    @Bean(name = "numbers.output")
    PollableChannel numbersOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow numbersFlow() {
        return IntegrationFlow
            .from("numbers.input")
            .transformWith(t -> t
                .<String, Integer>transformer(Integer::parseInt)
                .reactive(flux -> flux.publishOn(Schedulers.parallel())))
            .channel("numbers.output")
            .get();
    }
}
~~~

Các kiểu chính: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.channel.DirectChannel</code>, <code>org.springframework.integration.channel.QueueChannel</code>, <code>org.springframework.messaging.MessageChannel</code>, <code>org.springframework.messaging.PollableChannel</code>, <code>org.springframework.integration.config.EnableIntegration</code> và <code>reactor.core.scheduler.Schedulers</code>.

Đây là cách đặt <code>publishOn()</code> **trong cấu hình reactive endpoint của Spring Integration**. Input có thể là <code>DirectChannel</code>, nhưng endpoint nhận message bằng <code>ReactiveStreamsConsumer</code>; phần xử lý sau boundary diễn ra khi subscription được thiết lập và demand cho phép. Vì vậy, <code>send()</code> thành công ở đầu vào không phải bằng chứng transformer và downstream đã hoàn tất.

Gửi message để quan sát:

~~~java
Message<String> request = MessageBuilder.withPayload("42").build();
numbersInput.send(request);

// Do có ranh giới reactive, kết quả được chờ ở output channel.
Message<?> result = numbersOutput.receive(5_000);
if (result == null) {
    throw new IllegalStateException("Không có kết quả trong thời hạn");
}
Integer value = (Integer) result.getPayload(); // 42
~~~

<code>MessageBuilder</code> thuộc <code>org.springframework.integration.support</code>. Không dùng lệnh <code>receive()</code> blocking ở trong một Reactor non-blocking worker; đoạn chờ trên chỉ phù hợp trong test hoặc application boundary được quản lý.

### Điều gì không được suy ra từ ví dụ?

- <code>DirectChannel</code> trước endpoint không làm phần phía sau reactive endpoint trở thành một transaction đồng bộ end-to-end.
- <code>Schedulers.parallel()</code> không bảo đảm mọi message sẽ xử lý trên **một thread khác nhau**. Việc phân phối, ordering và demand phụ thuộc subscription/operator.
- <code>QueueChannel</code> đầu ra có semantics của polling, không tự biến thành một reactive channel.
- <code>publishOn</code> không thực hiện retry, không chuyển exception mặc định thành một <code>ErrorMessage</code> tùy ý và không lưu message bền vững khi restart.

## 6. FluxMessageChannel và backpressure của reactive consumer

Khi muốn toàn bộ đoạn flow tham gia Reactive Streams, có thể đặt <code>FluxMessageChannel</code> giữa các endpoint phù hợp:

~~~java
@Configuration
@EnableIntegration
public class ReactiveOrderChannels {
    @Bean(name = "orders.flux")
    FluxMessageChannel ordersFluxChannel() {
        return new FluxMessageChannel();
    }
}
~~~

<code>FluxMessageChannel</code> thuộc <code>org.springframework.integration.channel</code>. Nó không phải <code>PollableChannel</code> hay <code>SubscribableChannel</code> truyền thống; subscriber phải tuân theo Reactive Streams. Spring Integration dùng <code>ReactiveStreamsConsumer</code> làm cầu nối tới các message handler khi input tương thích.

~~~mermaid
flowchart LR
    IN["Reactive source Publisher"] --> FC["FluxMessageChannel"]
    FC --> RC["ReactiveStreamsConsumer"]
    RC --> H["ReactiveMessageHandler"]
    H --> OUT["Mono completion / downstream"]
    RC -. "request(n)" .-> FC
~~~

**Backpressure** nghĩa là downstream có thể thông báo số phần tử còn sẵn sàng nhận. Tuy nhiên, bảo đảm end-to-end chỉ tồn tại nếu **mọi đoạn liên quan tôn trọng demand**. Một inbound adapter dạng callback không hỗ trợ pause, một <code>send()</code> chủ động, một bridge sang channel imperative hoặc một toán tử buffer lớn có thể làm tiêu thụ bộ nhớ trước khi downstream kịp xử lý.

Ví dụ <code>publishOn(scheduler, 32)</code> sử dụng tham số <code>prefetch</code> để ảnh hưởng số phần tử chuẩn bị trước ở boundary:

~~~java
Flux<Message<?>> tuned = sourceFlux
    .publishOn(Schedulers.parallel(), 32);
~~~

<code>sourceFlux</code> là một <code>Flux&lt;Message&lt;?&gt;&gt;</code> do upstream cung cấp. Giảm prefetch có thể giảm buffer khi consumer chậm, nhưng có thể tăng chi phí điều phối và không chữa được một source bỏ qua backpressure. Cần đo memory, throughput và latency thực thay vì tối ưu theo một con số chung.

### Phân biệt concurrency với backpressure

| Tham số/kỹ thuật | Giải quyết vấn đề | Không đảm bảo |
|---|---|---|
| <code>request(n)</code> | Demand của subscriber | Tất cả adapter imperative đều tôn trọng demand |
| <code>publishOn(..., prefetch)</code> | Buffer/prefetch tại một boundary | Công việc downstream không thể block hoặc mất dữ liệu |
| <code>flatMap(..., concurrency)</code> | Giới hạn số inner publisher đang hoạt động | Output giữ nguyên thứ tự nguồn |
| <code>concatMap(...)</code> | Tuần tự hóa inner publisher và giữ thứ tự theo semantics operator | Throughput tối đa dưới tải I/O dài |
| <code>onBackpressureBuffer(...)</code> | Đệm theo chính sách khi upstream phát nhanh | Bộ nhớ vô hạn hoặc persistence sau crash |

Với message có cùng <code>correlationId</code> hoặc business key, concurrency quá cao có thể làm hai handler cập nhật cùng một group. Reactive Scheduler không thay thế <code>LockRegistry</code>, transaction hoặc idempotency.

## 7. Cô lập đoạn code blocking mà không làm nghẽn reactive worker

Một sai lầm thường gặp là gọi repository JDBC hoặc HTTP client đồng bộ trực tiếp trong <code>map()</code> đang chạy trên <code>Schedulers.parallel()</code>:

~~~java
// KHÔNG NÊN khi chạy trên event-loop / parallel worker:
Flux<Order> unsafe = ordersFlux
    .publishOn(Schedulers.parallel())
    .map(order -> legacyJdbcRepository.save(order));
~~~

<code>map</code> chờ cho tới khi JDBC trả về; worker bị chiếm trong toàn bộ thời gian I/O. Với tải cao, queue của scheduler hoặc backlog channel tăng.

### Cách 1 — cô lập từng nguồn blocking

~~~java
Mono<SaveResult> saveBlocking(Order order) {
    return Mono.fromCallable(() -> legacyJdbcRepository.save(order))
        .subscribeOn(Schedulers.boundedElastic());
}

Flux<SaveResult> results = ordersFlux
    .flatMap(this::saveBlocking, 8); // Tối đa 8 inner publisher hoạt động.
~~~

Cách này để <code>flatMap</code> giới hạn concurrency và <code>subscribeOn</code> chuyển lời gọi JDBC ra bounded-elastic worker. Nó **không làm JDBC thành non-blocking** và không giữ nguyên thứ tự input như <code>concatMap</code>. Repository là một thành phần minh họa; hàm <code>saveBlocking</code> thuộc lớp chứa đoạn xử lý.

### Cách 2 — ReactiveMessageHandler trong Spring Integration

Từ Spring Integration 6.1, Java DSL có <code>handleReactive(...)</code> cho một handler trả về <code>Mono&lt;Void&gt;</code>. Ví dụ terminal handler thực hiện một tác vụ JDBC đã được cô lập:

~~~java
@Bean
IntegrationFlow blockingStorageFlow(LegacyOrderService legacyService) {
    return IntegrationFlow.from("orders.flux")
        .handleReactive(message -> Mono
            .fromRunnable(() -> legacyService.store(
                (OrderCommand) message.getPayload()))
            .subscribeOn(Schedulers.boundedElastic())
            .then())
        .get();
}
~~~

Các tên <code>LegacyOrderService</code> và <code>OrderCommand</code> là kiểu do ứng dụng định nghĩa. Đoạn này là một **terminal** consumer (không phát reply), dùng như một ví dụ độc lập bên cạnh bean channel <code>orders.flux</code>; cần một producer thực sự gửi <code>OrderCommand</code> vào channel.

Nếu <code>legacyService.store(...)</code> dùng <code>@Transactional</code> JDBC, cần đi qua Spring proxy và mở transaction **bên trong thread thực hiện lời gọi đó**. Transaction JDBC của thread upstream không được tự mang qua <code>subscribeOn</code>.

**Không gọi <code>subscribe()</code> thủ công trong method handler để “fire-and-forget” rồi trả về thành công.** Điều đó cắt liên kết giữa completion/error của publisher và cơ chế backpressure/recovery của endpoint. Hãy trả về <code>Mono</code> cho framework composition khi API hỗ trợ.

## 8. Scheduler của poller không mặc định là Reactor Scheduler

Trong một polling consumer thông thường:

~~~text
TaskScheduler
  → chạy poller theo trigger
  → MessageSource.receive() hoặc QueueChannel.receive()
  → Consumer endpoint
  → handler
~~~

Đây là lịch chạy do **Spring <code>TaskScheduler</code>** kích hoạt. Đừng cấu hình <code>Schedulers.parallel()</code> rồi kỳ vọng polling consumer tự đổi thread scheduler hoặc tự hiểu demand của Reactive Streams.

Spring Integration có các biến thể khác:

- Khi <code>SourcePollingChannelAdapter</code> đẩy vào <code>ReactiveStreamsSubscribableChannel</code>, framework có thể tạo pipeline reactive tính lịch bằng trigger kết hợp <code>Mono.delay()</code>, và poll theo nhu cầu downstream thay vì lập một task scheduler thông thường.
- <code>ReactiveMessageSourceProducer</code> có thể bọc <code>MessageSource.receive()</code> thành nguồn reactive, sử dụng <code>Schedulers.boundedElastic()</code> để tách khả năng blocking trong source và lặp lại khi nguồn chưa có dữ liệu.
- Một flow có thể có *cả* polling boundary *và* reactive boundary ở bước sau; phải quan sát riêng hai scheduler/nguồn thread.

Do đó, để chẩn đoán “poller không chạy”, hãy kiểm tra endpoint <code>isRunning</code>, trigger, task scheduler, số message mỗi poll, subscriber/demand của channel đầu ra và khả năng receive của source. Thêm <code>publishOn</code> ở downstream không khởi động được một poller chưa start.

## 9. Reactive transaction theo Reactor Context, không theo ThreadLocal JDBC

Với giao dịch imperative, Spring thường gắn transaction state vào thread. <code>publishOn()</code>, <code>subscribeOn()</code> và các async boundary có thể làm processing chuyển thread, nên không được giả định <code>@Transactional</code> JDBC của sender còn tồn tại ở reactive worker.

Reactive transaction sử dụng <code>ReactiveTransactionManager</code> (ví dụ <code>R2dbcTransactionManager</code>), gắn state với **Reactor Context của subscription** thay vì chỉ ThreadLocal. Với những thao tác dữ liệu **thực sự reactive** và cùng manager, các operator có thể tiếp tục tham gia transaction ngay cả khi scheduler đổi thread.

Ví dụ nguyên lý dùng <code>TransactionalOperator</code>:

~~~java
@Service
public class ReactiveOrderService {
    private final ReactiveOrderRepository orders;
    private final ReactiveAuditRepository audits;
    private final TransactionalOperator tx;

    public ReactiveOrderService(
            ReactiveOrderRepository orders,
            ReactiveAuditRepository audits,
            ReactiveTransactionManager manager) {
        this.orders = orders;
        this.audits = audits;
        this.tx = TransactionalOperator.create(manager);
    }

    public Mono<Void> saveAndAudit(OrderCommand command) {
        return orders.save(command)
            .flatMap(saved -> audits.record(saved))
            .then()
            .as(tx::transactional);
    }
}
~~~

<code>ReactiveOrderRepository</code>/<code>ReactiveAuditRepository</code> là interface minh họa, có các method trả về publisher reactive. <code>TransactionalOperator</code> thuộc <code>org.springframework.transaction.reactive</code>, <code>ReactiveTransactionManager</code> thuộc <code>org.springframework.transaction</code>. Ví dụ giả định hai repository tương thích cùng reactive transaction manager.

Điều kiện để kết luận transaction bảo vệ cả save và audit:

1. Hai thao tác tham gia cùng reactive transaction manager và tài nguyên hỗ trợ transaction.
2. Publisher được **subscribe**, không có manual <code>subscribe()</code> tách rời ở giữa.
3. Exception của downstream được giữ trong pipeline và dẫn tới terminal <code>onError</code>, không bị thay thành thành công ngoài chủ đích.
4. Không đưa JDBC blocking vào giữa rồi mặc định nó được quản lý bởi reactive transaction manager.

<code>Reactor Context</code> khác với <code>MessageHeaders</code>: correlation ID đi qua headers theo hợp đồng message; các metadata subscription/transaction nằm trong reactive context. ThreadLocal logging MDC không tự di chuyển theo mọi <code>publishOn</code> hoặc thư viện: cần cơ chế context propagation phù hợp, không đơn thuần dựa vào tên thread.

## 10. Error handling và retry theo tín hiệu reactive

Trong một pipeline Reactor, exception thường trở thành tín hiệu **<code>onError</code> kết thúc subscription** nếu không được xử lý. Khi một bước xử lý lỗi, không nên mặc định toàn bộ exception sẽ xuất hiện ở global <code>errorChannel</code> của Spring Integration: điều này phụ thuộc loại endpoint, cách publisher được subscribe, adapter và cơ chế phát <code>ErrorMessage</code>.

~~~java
Mono<SaveResult> operation = Mono.defer(() -> reactiveClient.save(order))
    .doOnError(ex -> log.warn("Save failed", ex))
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
        .filter(this::isTransientFailure))
    .timeout(Duration.ofSeconds(5));
~~~

<code>reactiveClient</code>, <code>order</code> và <code>isTransientFailure</code> là các thành phần minh họa. <code>Retry</code> thuộc <code>reactor.util.retry</code>. Ba lần retry **bổ sung** sau lần thử đầu nếu policy cho phép; <code>timeout</code> là deadline reactive của đoạn được bao, không phải thời gian bảo đảm huỷ được mọi tác vụ blocking ở bên dưới.

### Các toán tử có tác động rất khác

| Operator | Hành vi | Rủi ro khi dùng sai |
|---|---|---|
| <code>doOnError(...)</code> | Quan sát lỗi, không nuốt lỗi | Nhầm là đã recover |
| <code>onErrorResume(...)</code> | Thay nhánh lỗi bằng publisher fallback | Biến thất bại thành kết quả thành công khiến upstream/ACK xử lý sai ý định |
| <code>onErrorMap(...)</code> | Chuyển exception thành loại khác | Mất nguyên nhân hoặc message context nếu bọc không đúng |
| <code>retryWhen(...)</code> | Resubscribe phần upstream đã được bao | Thực thi lại side effect nếu thiếu idempotency |
| <code>timeout(...)</code> | Phát lỗi nếu không có tiến triển đúng hạn | Tác vụ blocking/remote đã chạy có thể vẫn hoàn tất sau khi subscriber timeout |
| <code>doFinally(...)</code> | Ghi nhận completion, error hoặc cancellation | Không tự gửi DLQ hay hoàn tất transaction ngoài phạm vi |

**Đặc biệt:** Đặt <code>retry()</code> ở ngoài một publisher nhiều message có thể resubscribe **toàn bộ nguồn**, không chỉ message cuối cùng bị lỗi. Với nguồn hot, broker hoặc side effect, cần hiểu ngữ nghĩa nguồn và phân vùng retry theo từng message khi phù hợp.

Một <code>ReactiveMessageHandler</code> trả về <code>Mono&lt;Void&gt;</code> cho framework có cơ hội nhận completion/error. Ngược lại:

~~~java
// KHÔNG NÊN: lỗi về sau không còn gắn vào lời gọi hiện tại.
public void unsafe(Message<?> message) {
    reactiveClient.send(message).subscribe();
}
~~~

Đoạn code không phải handler đầy đủ; nó minh họa anti-pattern manual subscribe. Khi cần recovery, phải xác định chủ sở hữu: Reactor operator, Spring Integration reactive endpoint, adapter inbound của broker hay một error flow riêng. Chỉ ACK khi kết quả đáp ứng hợp đồng xử lý, không dựa vào việc đã *bắt đầu* subscription.

## 11. Backpressure, concurrency và thứ tự message

Một <code>Flux&lt;Message&lt;?&gt;&gt;</code> có thể xử lý nhiều message đồng thời nếu dùng <code>flatMap</code> với inner publisher không hoàn tất ngay:

~~~java
Flux<Receipt> receipts = incomingMessages
    .flatMap(message -> reactiveOrderService.process(
        (OrderCommand) message.getPayload()), 16);
~~~

Ở đây <code>incomingMessages</code> là <code>Flux&lt;Message&lt;?&gt;&gt;</code>, còn <code>process()</code> trả <code>Mono&lt;Receipt&gt;</code>. Giới hạn <code>16</code> là concurrency tối đa của các inner publisher, không phải “16 thread cố định”. Kết quả có thể hoàn thành **khác thứ tự đầu vào**.

Với nghiệp vụ phải giữ thứ tự theo account/order key, có thể:

- dùng <code>concatMap()</code> cho một dòng tuần tự, đánh đổi throughput;
- định tuyến/partition theo key rồi serialize xử lý trong từng partition;
- dùng locking/idempotency phù hợp cho group correlation, nhưng không coi lock là bảo đảm thứ tự arrival.

Không nên đặt <code>parallel()</code> hay <code>flatMap</code> concurrency lớn hơn khả năng DB/broker. Một publisher có backpressure tốt vẫn có thể mở quá nhiều request I/O nếu inner concurrency không bị giới hạn.

## 12. Lifecycle và quản lý Scheduler trong ứng dụng

Các factory như <code>Schedulers.parallel()</code>, <code>Schedulers.boundedElastic()</code> thường trả về shared scheduler. Trong khi đó, <code>Schedulers.newSingle(...)</code>, <code>newParallel(...)</code>, <code>newBoundedElastic(...)</code> tạo instance riêng; cần dispose khi ứng dụng ngừng sử dụng.

Ví dụ cấp Scheduler riêng cho legacy I/O và để Spring quản lý vòng đời:

~~~java
@Configuration
public class ReactorSchedulerConfig {

    @Bean(destroyMethod = "dispose")
    Scheduler legacyIoScheduler() {
        // 8 worker tối đa; cho phép tối đa 200 task chờ mỗi backing thread.
        return Schedulers.newBoundedElastic(8, 200, "legacy-io");
    }
}
~~~

Có thể inject bean này vào <code>Mono.fromCallable(...).subscribeOn(legacyIoScheduler)</code>. Không tạo Scheduler mới **mỗi message**, vì như vậy gây nhiều thread/queue và khó shutdown. Không dispose shared <code>Schedulers.parallel()</code> hoặc <code>Schedulers.boundedElastic()</code> chỉ vì một flow dừng; chúng có thể đang được flow khác sử dụng.

Spring Integration endpoint/flow có lifecycle start/stop riêng. Dừng một endpoint có thể huỷ subscription ở nơi được framework quản lý, nhưng **không có nghĩa mọi task đã được giao cho Scheduler hay mọi HTTP request đang chạy sẽ dừng tức thì**. Với việc đăng ký dynamic <code>IntegrationFlow</code> hoặc dùng <code>toReactivePublisher(autoStartOnSubscribe)</code>, phải kiểm tra rõ ai sở hữu subscription và ai đóng flow khi cancel/terminate.

## 13. Quan sát threading và chẩn đoán hiệu năng

Để tìm một message đang chạy ở đâu, nên ghi tối thiểu: correlation ID, tên endpoint/channel, thread name, request ID của upstream, số lần retry, latency, kết quả subscribe/cancel/error và độ sâu queue khi có. Không log toàn bộ payload nhạy cảm.

~~~java
Flux<Message<?>> observed = inputFlux
    .doOnSubscribe(s -> log.debug("reactive subscribed"))
    .doOnNext(message -> log.debug(
        "messageId={}, correlationId={}, thread={}",
        message.getHeaders().getId(),
        message.getHeaders().get("correlationId"),
        Thread.currentThread().getName()))
    .doOnError(ex -> log.error("reactive failure", ex))
    .doFinally(signal -> log.debug("terminated={}", signal));
~~~

Đây là đoạn instrumentation minh họa, không thay thế Micrometer/Observation. Một error hoặc cancellation là terminal signal của subscription; metric chỉ đếm <code>onNext</code> có thể bỏ sót lỗi khi converter/source thất bại trước khi tạo message.

| Triệu chứng | Nguyên nhân có thể | Cần kiểm tra |
|---|---|---|
| <code>send()</code> trả về nhưng output chưa có | Reactive endpoint chưa xử lý xong, chưa có demand, hoặc downstream lỗi | Subscription, output channel, consumer lifecycle, <code>onError</code> |
| CPU tăng nhưng throughput thấp | Thêm quá nhiều thread switch, <code>flatMap</code> concurrency không hợp lý | Profiling, scheduler queue, số <code>publishOn</code>, CPU |
| <code>parallel</code> worker bị giữ lâu | JDBC/HTTP blocking, <code>Thread.sleep</code>, <code>block()</code> | Thread dump, BlockHound nếu cấu hình, log handler |
| <code>boundedElastic</code> quá tải | Nhiều blocking call, task queue tăng | Thời gian chờ, thread cap, timeout, downstream capacity |
| Mất transaction sau <code>publishOn</code> | Dùng JDBC thread-bound transaction từ upstream | Transaction manager, thread boundary, reactive transaction scope |
| Message bị xử lý lại | <code>retryWhen</code>, resubscribe, broker redelivery | Vị trí retry, message ID, idempotency key và ACK |
| Correlation bị mất trong log | MDC/ThreadLocal không được propagate | Reactor Context, context-propagation, header correlation |
| Test treo vô hạn | Chưa subscribe, thiếu demand, scheduler bị dispose hoặc call blocking | StepVerifier, scheduler ownership, endpoint start |

### Quy trình kiểm tra nhanh

1. Xác minh publisher đã có **subscriber** và endpoint đang chạy; nếu không có subscription thì pipeline cold không làm việc.
2. Xác định ranh giới <code>publishOn</code>, <code>subscribeOn</code>, executor/channel và mọi operator tự lập lịch.
3. Phân loại đoạn blocking hoặc non-blocking; tìm <code>block()</code>, <code>Thread.sleep()</code>, JDBC và client sync.
4. Quan sát demand/backpressure, <code>flatMap</code> concurrency, queue depth và thời gian chờ scheduler.
5. Kiểm tra đường lỗi <code>onError</code>, recovery, retry, timeout và quyết định ACK/redelivery.
6. Xác định transaction theo thread-bound JDBC hay Reactor Context; kiểm tra correlation sau khi chuyển thread.
7. Kiểm tra lifecycle start/stop, cancellation và ownership của custom Scheduler.

## 14. Kiểm thử Scheduler và reactive pipeline

### 14.1. Kiểm chứng publishOn() thực sự đổi thread

~~~java
@Test
void publishOnRunsDownstreamOnDedicatedWorker() {
    Scheduler worker = Schedulers.newSingle("downstream-test");
    try {
        Mono<String> publisher = Mono.just("42")
            .publishOn(worker)
            .map(value -> Thread.currentThread().getName());

        StepVerifier.create(publisher)
            .expectNextMatches(name -> name.startsWith("downstream-test"))
            .verifyComplete();
    } finally {
        worker.dispose();
    }
}
~~~

<code>StepVerifier</code> thuộc <code>reactor.test</code>. Test này chỉ xác minh **execution context** của một operator, chưa chứng minh tính đúng của transaction hay backpressure trong toàn bộ Spring Integration flow.

### 14.2. Test time-based operator bằng virtual time

~~~java
@Test
void timeBasedFlowUsesVirtualTime() {
    StepVerifier.withVirtualTime(
            () -> Mono.delay(Duration.ofHours(1)))
        .expectSubscription()
        .expectNoEvent(Duration.ofMinutes(59))
        .thenAwait(Duration.ofMinutes(1))
        .expectNext(0L)
        .verifyComplete();
}
~~~

<code>withVirtualTime()</code> cho phép thay clock của các toán tử thời gian tương thích, tránh test đợi một giờ thực. Publisher phải được **tạo trong supplier**, sau khi virtual scheduler được cài đặt; một custom Scheduler đã inject trước đó có thể không bị thay bởi virtual time. Virtual time không làm JDBC/HTTP blocking chạy ảo hay thay thế integration test transaction/restart.

### 14.3. Test Spring Integration endpoint với timeout thực

Với flow <code>numbersFlow</code> ở mục 5:

~~~java
@Test
void reactiveTransformerPublishesParsedNumber() {
    numbersInput.send(MessageBuilder.withPayload("21").build());

    Message<?> result = numbersOutput.receive(5_000);
    assertNotNull(result);
    assertEquals(21, result.getPayload());
}
~~~

Các biến <code>numbersInput</code> và <code>numbersOutput</code> được inject từ những bean tương ứng. Cần kiểm thử thêm: JSON/number sai gây <code>onError</code>, demand không có subscriber, stop endpoint trong lúc xử lý, scheduler quá tải, timeout/cancellation và retry gây duplicate. Không gọi <code>receive()</code> trong non-blocking worker của Reactor.

## 15. Checklist khi đưa Scheduler vào production

- [ ] Xác định rõ nguồn nào tạo subscription và endpoint nào nhận <code>request(n)</code>.
- [ ] Phân biệt Reactor <code>Scheduler</code> với <code>TaskScheduler</code> của poller và <code>TaskExecutor</code> của channel.
- [ ] Chỉ dùng <code>publishOn</code>/<code>subscribeOn</code> tại ranh giới có chủ đích; biết operator nào chạy trước/sau.
- [ ] Không block <code>parallel</code>, <code>single</code> hoặc event loop; cô lập legacy blocking qua <code>boundedElastic</code> có giới hạn.
- [ ] Kiểm soát <code>flatMap</code> concurrency, prefetch, buffering, throughput, thứ tự và nguồn có hỗ trợ backpressure thật hay không.
- [ ] Giữ transaction reactive trong subscription/Reactor Context; không dựa vào JDBC ThreadLocal xuyên scheduler.
- [ ] Quy định rõ <code>onError</code>, retry/resubscribe, timeout/cancel, error channel và ACK/redelivery.
- [ ] Có correlation/idempotency khi nhiều message chung một key xử lý đồng thời hoặc bị retry.
- [ ] Quản lý <code>dispose()</code> cho custom Scheduler, lifecycle flow và in-flight task khi shutdown.
- [ ] Kiểm thử StepVerifier, virtual time, integration endpoint, tải và failure injection; quan sát p95/p99 latency cùng queue/scheduler saturation.

**Kết luận:** Scheduler quyết định **khi nào và trên thread nào** các bước reactive được thực thi, nhưng không tự giải quyết transaction, retry, backpressure hay độ bền của message. Trong Spring Integration, cần nhìn đồng thời Reactor <code>publishOn</code>/<code>subscribeOn</code>, <code>FluxMessageChannel</code>/<code>ReactiveStreamsConsumer</code> và các ranh giới poller/executor truyền thống. Khi đặt scheduler đúng nơi, tránh blocking trên worker không phù hợp và giữ completion/error trong cùng reactive composition, message flow sẽ dễ chẩn đoán và vận hành hơn.

## Tài liệu tham khảo

- [Project Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Spring Integration Reference — Reactive Streams Support](https://docs.spring.io/spring-integration/reference/reactive-streams.html)
- [Spring Integration Reference — Reactive Endpoint trong Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-reactive.html)
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Project Reactor Reference — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor Reference — Testing (StepVerifier và Virtual Time)](https://projectreactor.io/docs/core/release/reference/testing.html)

# Tách runtime handler khỏi service nghiệp vụ

Trong Spring Integration, **message handler** là điểm nối giữa hạ tầng trao đổi message và logic ứng dụng. Một message đi qua channel, được một consumer endpoint nhận rồi chuyển cho handler thực thi. Nếu handler vừa xử lý header, retry, thread, error channel, vừa chứa quy tắc nghiệp vụ và thao tác cơ sở dữ liệu, những thay đổi nhỏ về runtime sẽ dễ kéo theo thay đổi nghiệp vụ, đồng thời khiến việc kiểm thử và xử lý lỗi khó kiểm soát.

Mục tiêu của bài này là tổ chức hai lớp trách nhiệm rõ ràng:

- **Runtime handler (integration adapter):** hiểu Spring Integration, nhận và chuyển đổi message, đọc metadata cần thiết, gọi service, tạo kết quả trả về và để hạ tầng điều phối lỗi.
- **Application/domain service:** thực hiện use case, kiểm tra bất biến nghiệp vụ, quản lý giao dịch và trạng thái nghiệp vụ; có thể được gọi từ REST, batch, scheduler hoặc message flow mà không phụ thuộc vào API của Spring Integration.

Đây là một nguyên tắc thiết kế cho **Spring Integration runtime**, nơi message flow được điều phối qua channel, endpoint, consumer, poller và executor. Việc tách lớp giúp thay đổi topology, transaction boundary, retry hay error handling mà vẫn giữ được một service nghiệp vụ nhất quán.

## 1. Ranh giới giữa runtime và nghiệp vụ

~~~mermaid
flowchart LR
    A["Gateway / Inbound Adapter"] --> B["MessageChannel"]
    B --> C["Consumer endpoint"]
    C --> D["Runtime handler"]
    D --> E["Application service"]
    E --> F["Domain / Repository"]
    D -. "kết quả" .-> C
    C -. "reply" .-> G["Reply channel / Gateway"]
    C -. "lỗi khi runtime có cấu hình" .-> H["Error flow"]
~~~

Một <code>ServiceActivator</code> là consumer endpoint gắn handler với channel. Handler được Spring Integration gọi mỗi khi endpoint nhận được message. Service phía sau handler không cần biết message đến từ HTTP, Kafka, hàng đợi nội bộ hay một poller.

| Mối quan tâm | Runtime handler / integration configuration | Service nghiệp vụ |
|---|---|---|
| Giao tiếp | <code>Message</code>, payload, header, channel, reply | Command/DTO và kiểu dữ liệu của ứng dụng |
| Chuyển đổi | Chuẩn hóa payload, kiểm tra header bắt buộc, ánh xạ sang command | Kiểm tra quy tắc và bất biến nghiệp vụ |
| Điều phối | Subscriber, poller, executor, routing, timeout | Thực thi use case, phối hợp domain/repository |
| Độ tin cậy | Retry advice, error flow, dead-letter/recovery policy | Thao tác có thể chạy lại an toàn, kiểm soát trùng lặp theo khóa nghiệp vụ |
| Giao dịch | Cấu hình điểm bắt đầu giao dịch cho poller/adapter nếu cần | <code>@Transactional</code> bao quanh các thay đổi dữ liệu nghiệp vụ |
| Theo dõi | Correlation/tracing header, metric theo endpoint/channel | Log và metric về kết quả nghiệp vụ |
| Vòng đời | Start/stop endpoint, flow, consumer và executor | Service độc lập với việc flow đang chạy hay dừng |

**Nguyên tắc phụ thuộc:** handler gọi service; service không gọi ngược <code>MessageChannel</code>, không đọc <code>MessageHeaders</code> và không biết <code>IntegrationFlowContext</code>. Khi use case thực sự cần phát một sự kiện nghiệp vụ, service có thể phát domain event hoặc gọi một port do ứng dụng định nghĩa; adapter bên ngoài chuyển sự kiện đó sang message.

## 2. Dấu hiệu handler đang chứa quá nhiều trách nhiệm

Ví dụ một handler khó bảo trì:

~~~java
@ServiceActivator(inputChannel = "placeOrder.input")
public void handle(Message<PlaceOrderRequest> message) {
    // Mã minh họa một thiết kế cần tránh:
    // đọc header + tự retry + truy vấn/lưu database + gửi message khác
    // + quyết định quy tắc giảm giá + nuốt exception.
}
~~~

Trong mô hình này, kiểm thử quy tắc giảm giá buộc phải dựng <code>Message</code> và Spring Integration; mỗi retry có thể lưu đơn hai lần; một exception bị bắt và chỉ ghi log làm endpoint tưởng rằng việc xử lý đã thành công. Nếu đổi <code>DirectChannel</code> thành <code>ExecutorChannel</code>, lỗi và transaction có thể đổi hành vi mà đoạn handler không hề thể hiện điều đó.

Thay vào đó, giữ handler mỏng nhưng **không máy móc**: nó vẫn được phép kiểm tra header bắt buộc, chuẩn hóa format và phân loại lỗi hạ tầng. Quy tắc như “số lượng phải dương”, “đơn hàng không được trùng” hay “khách hàng được phép đặt hàng” thuộc service nghiệp vụ.

## 3. Ví dụ đầy đủ: gateway → channel → handler → service

Giả sử ứng dụng nhận lệnh tạo đơn theo <code>tenantId</code>. Gateway cung cấp API Java đồng bộ, handler ánh xạ message thành command, service xử lý giao dịch. Các đoạn code bên dưới là một ví dụ rút gọn theo Spring Integration 6.x và Spring Framework 6.x; phần triển khai lưu trữ được thay bằng một cổng <code>OrderStore</code>.

**Bước 1 — định nghĩa dữ liệu và hợp đồng của use case, không phụ thuộc messaging:**

~~~java
public record PlaceOrderRequest(String orderId, int quantity) {}
public record PlaceOrderCommand(String tenantId, String orderId, int quantity) {}
public record OrderReceipt(String orderId, String status) {}

public interface OrderStore {
    // Triển khai thật phải bảo đảm tính duy nhất theo tenantId + orderId
    OrderReceipt createIfAbsent(PlaceOrderCommand command);
}
~~~

**Bước 2 — service giữ quy tắc nghiệp vụ và transaction:**

~~~java
@Service
public class PlaceOrderService {
    private final OrderStore orderStore;

    public PlaceOrderService(OrderStore orderStore) {
        this.orderStore = orderStore;
    }

    @Transactional
    public OrderReceipt place(PlaceOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity phải lớn hơn 0");
        }
        return orderStore.createIfAbsent(command);
    }
}
~~~

<code>OrderStore.createIfAbsent</code> minh họa một thao tác có thể xử lý an toàn khi message được gửi lại: ứng dụng cần kiểm tra tính duy nhất bằng constraint/giao dịch ở persistence, không chỉ bằng một biến trong bộ nhớ. <code>@Transactional</code> có hiệu lực khi service được gọi qua Spring proxy, như ở handler là một bean khác.

**Bước 3 — handler làm nhiệm vụ chuyển đổi và ủy quyền:**

~~~java
@Component
public class PlaceOrderRuntimeHandler {
    private final PlaceOrderService service;

    public PlaceOrderRuntimeHandler(PlaceOrderService service) {
        this.service = service;
    }

    @ServiceActivator(inputChannel = "placeOrder.input")
    public OrderReceipt handle(Message<PlaceOrderRequest> message) {
        String tenantId = message.getHeaders().get("tenantId", String.class);
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Thiếu tenantId");
        }

        PlaceOrderRequest request = message.getPayload();
        PlaceOrderCommand command = new PlaceOrderCommand(
            tenantId, request.orderId(), request.quantity()
        );
        return service.place(command);
    }
}
~~~

Handler không dùng <code>EntityManager</code>, không quyết định điều kiện nghiệp vụ, không tự gọi <code>Thread.sleep()</code> để retry và không nuốt exception. Giá trị <code>OrderReceipt</code> trả về là payload của reply được Spring Integration tạo theo cơ chế request–reply.

**Bước 4 — wiring channel và gateway:**

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class OrderIntegrationConfig {
    @Bean(name = "placeOrder.input")
    MessageChannel placeOrderInput() {
        return new DirectChannel();
    }
}

@MessagingGateway(defaultRequestChannel = "placeOrder.input")
public interface OrderGateway {
    OrderReceipt place(
        PlaceOrderRequest request,
        @Header("tenantId") String tenantId
    );
}
~~~

Những import thường dùng: <code>org.springframework.integration.annotation.ServiceActivator</code>, <code>MessagingGateway</code>, <code>IntegrationComponentScan</code>; <code>org.springframework.integration.config.EnableIntegration</code>; <code>org.springframework.integration.channel.DirectChannel</code>; <code>org.springframework.messaging.Message</code>, <code>MessageChannel</code>; <code>org.springframework.messaging.handler.annotation.Header</code>. Với Java 17+, các <code>record</code> trong ví dụ có thể nằm trong những file riêng.

Khi gọi <code>orderGateway.place(new PlaceOrderRequest("O-42", 2), "T-A")</code>, gateway tạo message có payload và header <code>tenantId</code>, gửi qua <code>DirectChannel</code>, endpoint gọi handler, handler chuyển thành <code>PlaceOrderCommand</code> và nhận kết quả từ service. Gateway đợi reply rồi trả <code>OrderReceipt</code> về caller. Cấu hình reply/timeout phải được xem xét lại khi chuyển sang thực thi bất đồng bộ.

Một lựa chọn tương đương là định nghĩa consumer bằng Java DSL:

~~~java
@Bean
IntegrationFlow placeOrderFlow(PlaceOrderRuntimeHandler handler) {
    return IntegrationFlow.from("placeOrder.input")
        .handle(handler, "handle")
        .get();
}
~~~

**Chỉ chọn một kiểu đăng ký endpoint cho cùng handler.** Khi dùng <code>IntegrationFlow</code> ở trên, bỏ <code>@ServiceActivator</code> khỏi phương thức <code>handle</code>; nếu giữ cả hai, có thể tạo nhiều consumer cùng nghe một channel và dẫn tới hành vi xử lý khó dự đoán.

## 4. Threading và transaction: vì sao ranh giới này quan trọng?

Đổi loại channel có thể đổi thread thực thi nhưng không nên đổi API của <code>PlaceOrderService</code>.

| Cấu hình runtime | Hành vi chính | Tác động cần kiểm tra |
|---|---|---|
| <code>DirectChannel</code> | Handler chạy trên thread của sender; thường đồng bộ | Exception thường lan về sender; gateway thấy kết quả ngay khi handler hoàn thành |
| <code>ExecutorChannel</code> | Giao message cho <code>TaskExecutor</code> | Handler chạy ở thread khác; transaction/thread context của caller không tự truyền qua; gateway request–reply vẫn có thể phải chờ reply |
| <code>QueueChannel</code> + poller | Message được đưa vào queue, poller lấy và gọi handler | Cần thiết lập poller, capacity, backpressure, thời điểm commit và xử lý khi poller dừng |
| <code>PublishSubscribeChannel</code> | Phát cho nhiều subscriber | Không dùng như cơ chế phân tải công việc đơn lẻ; mỗi subscriber có thể tạo side effect riêng |

Với <code>DirectChannel</code>, có thể có cùng thread từ gateway tới handler và service. Nhưng **cùng thread không có nghĩa mọi thao tác tự nằm trong cùng transaction**: ranh giới thực tế phụ thuộc nơi đặt <code>@Transactional</code> và transaction manager. Với <code>ExecutorChannel</code> hoặc poller, giao dịch mở ở thread gửi sẽ không tự bao lấy service bên nhận. Giao dịch ở service vẫn có thể được mở trong thread xử lý nếu lời gọi đi qua Spring proxy.

Khi poller đọc message từ nguồn transactional, có thể cần thêm transaction advice ở poller/endpoint. Giao dịch dữ liệu và việc ACK với broker ngoài thường không tự trở thành một giao dịch nguyên tử; các luồng cần giao hàng tin cậy có thể phải dùng inbox/outbox, idempotency key hoặc cơ chế bù phù hợp.

Đừng nhét quyết định “chạy trên executor nào”, “poll bao lâu một lần” hay “stop/start flow” vào service. Những quyết định này thuộc cấu hình channel, consumer endpoint, poller và <code>IntegrationFlow</code>.

## 5. Retry, lỗi và idempotency

Khi xử lý một message thất bại, thiết kế phải phân biệt **lỗi nghiệp vụ không nên thử lại** với **lỗi tạm thời có thể thử lại**.

1. Service ném exception rõ nghĩa theo quy tắc của use case (ví dụ đơn không hợp lệ, trùng khóa, lỗi truy cập kho dữ liệu). Không bắt mọi exception rồi trả “thành công”.
2. Runtime cấu hình retry có giới hạn tại consumer endpoint, chẳng hạn bằng <code>RequestHandlerRetryAdvice</code>, với backoff và chính sách chỉ retry lỗi có thể hồi phục.
3. Khi hết lần thử, endpoint/adapter xử lý recovery, chuyển vào error flow, dead-letter queue hoặc log/alert theo cam kết giao hàng của hệ thống.
4. Service bảo đảm side effect an toàn khi thực thi lại: khóa duy nhất, idempotency key, trạng thái xử lý hoặc transactional outbox khi cần.

Với flow đồng bộ qua <code>DirectChannel</code>, exception chưa được xử lý thường lan trở lại phía gửi, có thể được bọc trong exception của Spring Messaging. Với consumer bất đồng bộ hoặc poller, lỗi có thể được chuyển thành <code>ErrorMessage</code> trên <code>errorChannel</code> tương ứng **nếu đường xử lý lỗi được cấu hình**. Không được giả định mọi exception đều tự động vào một error channel. <code>errorChannel</code>, retry advice và cơ chế ACK/redelivery cần được kiểm tra cụ thể trên endpoint/adapter đang dùng.

Chẳng hạn, người gửi có thể gửi lại cùng lệnh “tạo O-42”. <code>MessageHeaders.ID</code> có thể khác qua mỗi lần gửi; nó là định danh message, không phải khóa nghiệp vụ ổn định. Hãy dùng <code>tenantId + orderId</code> hoặc một <code>idempotencyKey</code> có hợp đồng rõ ràng để chặn ghi trùng. Nếu retry chạy lại thao tác gửi email hay gọi API thanh toán, cần thiết kế tương ứng cho side effect bên ngoài.

### Correlation và observability

Một flow có thể đi qua router, aggregator hoặc request–reply. Handler nên đọc các header cần thiết cho việc ánh xạ và quan sát, đồng thời giữ hoặc truyền metadata tương quan khi tạo message mới. Header <code>correlationId</code> phục vụ ghép nối bước xử lý hoặc tracing theo hợp đồng của flow; đừng coi nó là khóa nghiệp vụ hoặc mặc định luôn có.

Ở tầng runtime, theo dõi throughput, độ trễ tại handler, số lần retry, độ sâu queue, thread pool saturation, số message lỗi và thời gian chờ reply. Ở tầng nghiệp vụ, theo dõi số đơn được tạo/từ chối và nguyên nhân nghiệp vụ. Log correlation ID thay cho việc ghi tràn lan toàn bộ payload có thể chứa dữ liệu nhạy cảm.

## 6. Vòng đời IntegrationFlow độc lập với service

Spring Integration quản lý lifecycle của các endpoint (chẳng hạn <code>SmartLifecycle</code>) và có thể đăng ký flow động bằng <code>IntegrationFlowContext</code>. Khi cần bật/tắt xử lý một nguồn dữ liệu, thao tác trên flow registration hoặc consumer endpoint, không đặt biến cờ và vòng lặp nhận message trong <code>PlaceOrderService</code>.

- **Start:** endpoint bắt đầu nhận/poll; service chỉ được gọi khi message được giao tới handler.
- **Stop:** endpoint ngừng nhận/poll theo loại endpoint; công việc đang chạy có thể cần chờ, timeout hoặc cơ chế dừng an toàn riêng.
- **Remove/re-register flow:** cấu hình và subscriber thay đổi, nhưng hợp đồng command của service vẫn giữ nguyên.

Quản lý executor shutdown, pending queue, transaction đang mở và xử lý lại sau restart là việc của runtime/operations. Dừng endpoint không tự bảo đảm mọi message đang xử lý đã hoàn thành hay đã được lưu bền vững.

## 7. Kiểm thử theo từng ranh giới

Với cách tách này, mỗi tầng có một phạm vi kiểm thử tự nhiên:

| Cấp kiểm thử | Nên chứng minh điều gì? |
|---|---|
| Unit test service | Quy tắc nghiệp vụ, transaction/persistence qua test tích hợp khi cần, xử lý trùng lặp bằng khóa nghiệp vụ |
| Unit test handler | Đọc đúng header, ánh xạ payload → command, gọi đúng service, trả kết quả hoặc lan exception |
| Integration test flow | Gateway gửi được qua channel, endpoint tồn tại, reply về đúng nơi, timeout/error channel/retry hoạt động như cấu hình |
| Runtime test | Thay đổi thread/poller, tải đồng thời, backpressure, stop/restart và redelivery không làm sai side effect |

Ví dụ unit test handler bằng JUnit 5 và Mockito (lược bỏ import):

~~~java
@Test
void handlerMapsMetadataAndDelegates() {
    PlaceOrderService service = mock(PlaceOrderService.class);
    PlaceOrderRuntimeHandler handler = new PlaceOrderRuntimeHandler(service);
    PlaceOrderRequest request = new PlaceOrderRequest("O-42", 2);
    PlaceOrderCommand command = new PlaceOrderCommand("T-A", "O-42", 2);
    OrderReceipt receipt = new OrderReceipt("O-42", "ACCEPTED");

    when(service.place(command)).thenReturn(receipt);

    Message<PlaceOrderRequest> message = MessageBuilder.withPayload(request)
        .setHeader("tenantId", "T-A")
        .build();

    assertEquals(receipt, handler.handle(message));
    verify(service).place(command);
}
~~~

Unit test này không cần tạo <code>ApplicationContext</code> hoặc channel. Một integration test riêng nên gọi qua <code>OrderGateway</code> trong Spring context để phát hiện lỗi wiring; test riêng với executor hoặc poller mới chứng minh được hành vi thread, retry và error routing thực tế.

## 8. Các lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Service khó dùng lại từ REST hoặc batch | Nhận tham số kiểu <code>Message&lt;?&gt;</code> hoặc gọi channel bên trong | Đổi sang command/result thuần ứng dụng; để handler chuyển đổi |
| Exception bị mất, hệ thống xem như thành công | Handler bắt <code>Exception</code> rồi chỉ log | Để lỗi lan tới cơ chế error/retry phù hợp, chỉ recover khi có chính sách rõ |
| Đơn hoặc thanh toán bị tạo hai lần | Retry/redelivery, nhiều subscriber hoặc thiếu ràng buộc dữ liệu | Dùng idempotency key, unique constraint, thiết kế side effect an toàn |
| Gateway chờ mãi/timeout | Consumer không tạo reply, poller không chạy hoặc executor bị nghẽn | Kiểm tra reply channel, return value, poller, capacity, timeout |
| Dữ liệu không rollback như mong muốn | Transaction đặt sai thread, tự gọi phương thức <code>@Transactional</code> trong cùng bean | Đặt transaction tại service được gọi qua proxy; kiểm tra biên poller/adapter |
| Correlation bị mất sau khi biến đổi message | Tự tạo message mới và bỏ header cần truyền | Dùng cách build message giữ header cần thiết; kiểm tra chiến lược correlation |
| Stop flow nhưng vẫn còn tác vụ chạy | Công việc đã giao cho executor hoặc queue trước khi stop | Có chính sách graceful shutdown, quan sát in-flight task, xử lý lại an toàn |

## 9. Checklist trước khi đưa flow vào môi trường chạy

- Handler chỉ phụ thuộc vào API tích hợp ở phía ngoài và một hoặc vài port/service ứng dụng; service không phụ thuộc Spring Integration.
- Command/result rõ nghĩa, validation đúng tầng; header vận hành không rò rỉ thành dependency của domain.
- Chỉ đăng ký một consumer endpoint cho một handler theo chủ ý; hiểu rõ điểm khác nhau giữa unicast và publish–subscribe.
- Xác định rõ channel đồng bộ/bất đồng bộ, executor/poller, reply timeout và transaction boundary.
- Có chính sách retry/recovery cho lỗi transient; idempotency được bảo đảm ở tầng lưu trữ hoặc side effect tương ứng.
- Có correlation và metric đủ để lần theo message, thread và lỗi; có test service, handler và wiring flow.

**Kết quả mong muốn:** runtime chịu trách nhiệm *khi nào, ở thread nào, qua channel nào và với chính sách lỗi nào* một use case được gọi; service nghiệp vụ chịu trách nhiệm *use case phải làm gì và trạng thái nghiệp vụ nào hợp lệ*. Ranh giới này giúp message flow phát triển mà không làm logic nghiệp vụ phụ thuộc vào cách Spring Integration điều phối runtime.

# Phân biệt cấu hình flow với trạng thái runtime

Trong Spring Integration, khai báo một `IntegrationFlow` mới chỉ mô tả cách message cần đi qua các thành phần. Khi ứng dụng khởi động, Spring tạo các bean tương ứng, kết nối channel với endpoint và quản lý vòng đời của những component có khả năng chạy. Ở thời điểm runtime, một endpoint có thể đang chạy, đã dừng, đang chờ poller, hoặc đang xử lý message; những trạng thái đó không nằm trong bản mô tả flow.

Phân biệt hai lớp này giúp trả lời đúng các câu hỏi vận hành: flow đã được cấu hình hay chưa, endpoint đã được đăng ký hay chưa, consumer có đang nhận message không, queue còn message không, và executor có đang có công việc chờ xử lý không. Một flow xuất hiện trong cấu hình hoặc Integration Graph chưa đủ để kết luận toàn bộ flow đang hoạt động bình thường.

Sau bài này, bạn có thể:

- Giải thích `IntegrationFlow` mô tả điều gì và Spring tạo runtime components như thế nào.
- Phân biệt bean đã tồn tại với endpoint đã được start.
- Hiểu vai trò của `Lifecycle`, `SmartLifecycle`, `autoStartup` và `phase`.
- Theo dõi flow tĩnh và flow được đăng ký động qua `IntegrationFlowContext`.
- Chẩn đoán trường hợp flow có cấu hình nhưng không tiêu thụ message, hoặc đã dừng nhưng vẫn còn công việc đang chờ.

## 1. IntegrationFlow là mô tả cách ghép các thành phần

`IntegrationFlow` trong Java DSL là cách khai báo một chuỗi hoặc đồ thị xử lý message. Mỗi bước có thể là channel, transformer, filter, router, service activator, splitter, aggregator hoặc adapter. Bản khai báo mô tả các thành phần cần kết nối và cách message di chuyển giữa chúng.

Ví dụ một flow tĩnh được khai báo như một bean:

```java
@Configuration
class OrderIntegrationConfiguration {

    @Bean
    MessageChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ordersFlow(OrderService orderService) {
        return IntegrationFlow.from("ordersIn")
                .handle(orderService, "process")
                .get();
    }
}
```

Đoạn code trên mô tả một luồng nhận message từ `ordersIn` rồi gọi `OrderService.process`. Nó chưa nói rằng một thread riêng đã được tạo để liên tục chạy flow. Với `DirectChannel`, handler thường được gọi đồng bộ trong thread gửi message khi endpoint đã được start và đăng ký làm subscriber.

Khi ApplicationContext khởi tạo, hạ tầng Spring Integration xử lý định nghĩa flow và đăng ký các component cần thiết thành những bean runtime. Tùy flow, các component đó có thể gồm channel, message handler, consumer endpoint, poller hoặc adapter. Endpoint chịu trách nhiệm nối handler với channel và điều khiển việc nhận message.

Do đó cần phân biệt:

- `IntegrationFlow`: mô tả cấu trúc xử lý.
- Bean runtime: đối tượng cụ thể được Spring tạo và quản lý trong ApplicationContext.
- Endpoint đang chạy: component đã được khởi động và có thể thực hiện vai trò nhận hoặc phát message.
- Công việc đang diễn ra: message cụ thể đang được xử lý, đang nằm trong queue hoặc đã được giao cho executor.

Một bean có thể tồn tại mà endpoint tương ứng chưa chạy. Tương tự, endpoint có thể đã chạy nhưng tại thời điểm quan sát không có message nào cần xử lý.

## 2. Từ cấu hình đến runtime trong ApplicationContext

Với flow tĩnh khai báo bằng `@Bean` hoặc XML, quá trình thường diễn ra theo các bước:

```text
Java DSL / XML configuration
            |
            v
IntegrationFlow definition
            |
            v
ApplicationContext creates and registers components
            |
            v
Channels <----> handlers <----> consumer endpoints
            |
            v
Lifecycle startup according to autoStartup and phase
            |
            v
Message processing at runtime
```

Khi context được refresh, Spring tạo và cấu hình bean. Các component triển khai lifecycle contract được Spring quản lý trong giai đoạn khởi động và đóng ứng dụng. `SmartLifecycle` bổ sung khả năng tự khởi động, thứ tự start/stop và callback khi dừng bất đồng bộ.

Không phải mọi đối tượng trong flow đều là một tiến trình hoặc thread độc lập. `DirectChannel` là một kênh chuyển tiếp đồng bộ; `QueueChannel` giữ message trong hàng đợi; `ExecutorChannel` dùng executor để phân phối việc gọi handler. Consumer endpoint mới là thành phần gắn handler với cơ chế nhận message phù hợp.

Với một endpoint hướng sự kiện, khi endpoint start, nó đăng ký handler với `SubscribableChannel`. Khi endpoint stop, nó ngừng đăng ký nhận message theo lifecycle của endpoint. Với endpoint polling, việc start kích hoạt lịch poll; khi stop, lịch poll được dừng. Cả hai trường hợp đều cho thấy channel và endpoint có vòng đời khác nhau.

## 3. Cấu hình và trạng thái runtime khác nhau ở đâu?

| Khía cạnh | Cấu hình / definition | Trạng thái runtime |
|---|---|---|
| Flow | Các bước và quan hệ kết nối được khai báo trong `IntegrationFlow`. | Những component tương ứng đã được đăng ký và endpoint nào đang chạy. |
| Channel | Loại channel, tên bean và cách nối các bước. | Message đang có trong queue, subscriber hiện tại hoặc khả năng phân phối tại thời điểm đó. |
| Endpoint | Handler, input channel, poller, thuộc tính `autoStartup`, `phase`. | Endpoint đã start hay stop, có đang nhận message hay không. |
| Poller | Trigger, fixed delay/rate, giới hạn message mỗi lần poll. | Tác vụ poll đã được schedule, lần poll gần nhất, kết quả và lỗi khi poll. |
| Executor | Executor được chọn và cấu hình pool. | Số thread đang hoạt động, hàng đợi task, task hoàn tất hoặc bị từ chối. |
| Retry / transaction | Chính sách retry và cách khai báo transaction. | Lần thử hiện tại, transaction đang mở hay đã kết thúc, lỗi cuối cùng. |
| Message store | Cách lưu message hoặc trạng thái correlation. | Message và nhóm correlation thực tế đang được lưu tại thời điểm quan sát. |

Cấu hình thường ổn định trong suốt vòng đời ứng dụng, trong khi trạng thái runtime thay đổi theo thời gian. Một flow có thể giữ nguyên định nghĩa nhưng endpoint được start và stop nhiều lần. Queue có thể tăng rồi giảm; executor có thể lúc rảnh, lúc bận; một aggregator có thể có các nhóm message đang chờ đủ phần tử.

Vì thế, câu “flow đang chạy” thường quá chung chung. Khi điều tra, hãy chỉ rõ đang hỏi về sự tồn tại của definition, sự tồn tại của bean, trạng thái lifecycle của endpoint, hay tiến độ xử lý message.

## 4. Lifecycle, SmartLifecycle, autoStartup và phase

Spring cung cấp hai interface thường gặp để quản lý vòng đời component:

- `Lifecycle` có `start()`, `stop()` và `isRunning()`.
- `SmartLifecycle` mở rộng `Lifecycle`, bổ sung `isAutoStartup()`, `getPhase()` và cơ chế `stop(Runnable)` để hỗ trợ dừng có callback.

Các consumer endpoint của Spring Integration được quản lý theo lifecycle. Có thể cấu hình endpoint không tự khởi động khi ApplicationContext start bằng `autoStartup=false`, sau đó chủ động gọi `start()` khi điều kiện nghiệp vụ đã sẵn sàng. Thuộc tính `phase` điều khiển thứ tự khởi động và dừng giữa các component triển khai `SmartLifecycle`: phase thấp hơn được start trước; khi shutdown, thứ tự được đảo ngược.

Ví dụ đọc trạng thái một component đã lấy được từ ApplicationContext:

```java
void logLifecycle(Object component) {
    if (component instanceof SmartLifecycle smartLifecycle) {
        log.info("running={}, autoStartup={}, phase={}",
                smartLifecycle.isRunning(),
                smartLifecycle.isAutoStartup(),
                smartLifecycle.getPhase());
    }
    else if (component instanceof Lifecycle lifecycle) {
        log.info("running={}", lifecycle.isRunning());
    }
    else {
        log.info("Component does not expose Lifecycle state");
    }
}
```

Tên bean của endpoint được tạo từ cấu hình hoặc DSL và có thể phụ thuộc ID của flow/component. Khi cần kiểm tra một endpoint cụ thể, hãy đặt ID rõ ràng trong cấu hình rồi tra đúng bean tương ứng. Không nên giả định tên bean runtime luôn giống tên phương thức `@Bean` trả về `IntegrationFlow`.

`isRunning()` cho biết component đã được start theo lifecycle contract. Nó không chứng minh handler đang xử lý message, queue không bị nghẽn, executor còn đủ thread, hoặc downstream đang khỏe. Muốn kết luận khả năng xử lý thực tế, phải kết hợp trạng thái lifecycle với metrics, queue depth, log và tình trạng phụ thuộc bên ngoài.

## 5. Flow tĩnh và flow đăng ký động

Flow tĩnh thường được khai báo bằng `@Bean` hoặc XML và được xử lý cùng ApplicationContext. Khi ứng dụng khởi động, hạ tầng tạo các component tương ứng và quản lý lifecycle của chúng.

Khi cần tạo hoặc gỡ flow trong lúc ứng dụng đang chạy, Spring Integration cung cấp `IntegrationFlowContext`. Một registration đại diện cho flow được đăng ký động và cho phép điều khiển vòng đời của flow đó:

```java
@Service
class TenantFlowManager {

    private final IntegrationFlowContext flowContext;
    private final OrderService orderService;

    TenantFlowManager(
            IntegrationFlowContext flowContext,
            OrderService orderService) {
        this.flowContext = flowContext;
        this.orderService = orderService;
    }

    IntegrationFlowRegistration registerTenantFlow() {
        return flowContext
                .registration(flow -> flow
                        .from("tenant.orders")
                        .handle(orderService, "process"))
                .id("tenantOrders")
                .register();
    }
}
```

Đối tượng `IntegrationFlowRegistration` trả về là handle để quản lý registration. Có thể gọi `start()` hoặc `stop()` khi cần thay đổi trạng thái; gọi `destroy()` khi muốn hủy registration và loại bỏ các component do registration đó quản lý. Nếu cần đăng ký nhưng chưa chạy ngay, builder hỗ trợ cấu hình `autoStartup` trước khi gọi `register()`.

Ví dụ điều khiển vòng đời sau khi đăng ký:

```java
IntegrationFlowRegistration registration = registerTenantFlow();

registration.stop();   // Dừng nhận/xử lý theo lifecycle của flow.
registration.start();  // Khởi động lại registration.
registration.destroy(); // Hủy registration và các component thuộc flow.
```

Trong ứng dụng thực tế, hãy giữ registration handle ở nơi quản lý vòng đời tenant hoặc cấu hình động. Tránh tạo flow mới lặp lại cho cùng một tenant mà không quản lý registration cũ, vì điều đó có thể tạo endpoint trùng, subscriber dư hoặc rò rỉ bean.

`stop()` và `destroy()` có ý nghĩa khác nhau. Stop chuyển component sang trạng thái dừng nhưng vẫn giữ registration để có thể start lại. Destroy loại bỏ registration và component thuộc flow. Việc destroy flow không tự động xóa dữ liệu nghiệp vụ hoặc message đang được lưu trong hệ thống bên ngoài.

## 6. Channel, poller và executor có trạng thái riêng

Một flow có thể gồm nhiều loại channel và endpoint. Trạng thái của các thành phần này giải thích vì sao nhìn thấy cấu hình chưa đủ để biết message đang đi đến đâu.

### 6.1. DirectChannel

`DirectChannel` thường gọi subscriber trong cùng thread gửi message. Khi endpoint đã start và đăng ký handler, lệnh send có thể đi thẳng vào handler. Nếu endpoint dừng và không còn subscriber, message không được xử lý bởi endpoint đó; kết quả gửi còn phụ thuộc kiểu channel, số subscriber và cấu hình xử lý lỗi.

Không có hàng đợi nội bộ để giữ message chờ endpoint khởi động lại. Vì vậy, khi kiểm tra một `DirectChannel`, hãy xem subscriber và trạng thái endpoint, đồng thời kiểm tra kết quả send.

### 6.2. QueueChannel và PollingConsumer

`QueueChannel` có thể giữ message chờ consumer lấy ra. Một `PollingConsumer` sử dụng poller để nhận message theo lịch. Poller có thể được cấu hình bằng fixed delay, fixed rate, cron trigger hoặc giới hạn số message mỗi lần poll.

Nếu endpoint dừng, tác vụ polling ngừng chạy theo lifecycle của endpoint. Các message đã nằm trong queue thường vẫn còn đó và có thể được lấy khi endpoint chạy lại; việc lưu giữ lâu dài phụ thuộc queue và message store được sử dụng. Vì vậy, “endpoint stopped” không đồng nghĩa “queue empty”.

### 6.3. ExecutorChannel

`ExecutorChannel` chuyển việc gọi handler qua một `TaskExecutor`, nên message có thể được xử lý ở thread khác với thread gửi. Executor có trạng thái riêng như số thread đang hoạt động, task đang chờ và khả năng từ chối task khi quá tải.

Endpoint dừng không đồng nghĩa mọi task đã được executor nhận trước đó đều bị hủy. Khi chẩn đoán, cần xem cả trạng thái endpoint lẫn trạng thái executor, bao gồm queue task và lỗi rejected execution nếu có.

## 7. Dừng flow không đồng nghĩa xóa toàn bộ công việc

Một thao tác stop chủ yếu tác động đến lifecycle của component. Tùy channel và cơ chế thực thi, những việc sau có thể vẫn tồn tại sau khi endpoint dừng:

- Message đã được đưa vào `QueueChannel` hoặc message store.
- Task đã được giao cho executor nhưng chưa chạy xong.
- Handler đang thực thi và đang chờ I/O hoặc dịch vụ bên ngoài.
- Nhóm message correlation đang được aggregator lưu để chờ phần tử còn thiếu.
- Trạng thái retry, transaction hoặc dữ liệu lỗi đã được ghi ở hệ thống lưu trữ tương ứng.

Vì vậy, trước khi dừng một flow trong môi trường production, cần biết điểm nhận message, kiểu channel, chính sách lưu trữ và cách ứng dụng xử lý công việc đang in-flight. Nếu cần shutdown có kiểm soát, hãy phối hợp lifecycle phase, khả năng dừng của endpoint, thời gian chờ của executor và cơ chế drain queue phù hợp với yêu cầu nghiệp vụ.

Đặc biệt, `stop()` không phải thao tác purge queue. Nếu muốn xóa message, đó là hành động quản lý dữ liệu riêng và cần được thiết kế theo chính sách nghiệp vụ, tránh làm mất message hợp lệ.

## 8. Cách quan sát trạng thái runtime

Nên kết hợp nhiều góc nhìn thay vì dựa vào một cờ `isRunning()`:

| Câu hỏi | Nơi kiểm tra phù hợp |
|---|---|
| Flow đã được khai báo/đăng ký chưa? | ApplicationContext, cấu hình Java/XML hoặc `IntegrationFlowContext` với flow động. |
| Endpoint đã start chưa? | Bean endpoint và `Lifecycle.isRunning()`. |
| Endpoint có tự start không, thứ tự lifecycle thế nào? | `SmartLifecycle.isAutoStartup()` và `getPhase()`. |
| Message có đang nằm trong queue không? | Queue/channel hoặc MessageStore tương ứng. |
| Poller có đang hoạt động không? | Lifecycle của polling endpoint, scheduler và log lần poll. |
| Executor có bị nghẽn không? | Active thread, pool size, task queue, completed task và rejected task. |
| Flow có những component nào? | Integration Graph khi `IntegrationGraphServer` hoặc endpoint quản trị tương ứng được bật. |
| Handler có lỗi hoặc chậm không? | Log, metrics/observation, error channel và tracing. |

Spring Integration có Integration Graph để biểu diễn các component và quan hệ kết nối. Trong ứng dụng Spring Boot, có thể expose endpoint quản trị Integration Graph thông qua Actuator khi dependency và cấu hình phù hợp đã được bật. Graph hữu ích để hiểu cấu trúc runtime; nó không thay thế việc kiểm tra endpoint đang chạy hay queue/executor đang có tải.

Các component được instrument có thể cung cấp metrics/observation về gửi, nhận và xử lý message. Khi bật management và hệ thống metrics tương ứng, hãy dùng các số liệu đó cùng log và tracing để xác định latency, throughput và điểm nghẽn. Tên metric và khả năng expose phụ thuộc phiên bản Spring Integration, cấu hình Micrometer và hệ thống quan sát của ứng dụng.

## 9. Tình huống chẩn đoán

Giả sử dashboard cho thấy `ordersFlow` đã được tạo, nhưng đơn hàng mới không được xử lý. Hãy đi theo thứ tự sau:

1. **Xác nhận definition và registration.** Kiểm tra flow có trong cấu hình hoặc ApplicationContext không; nếu là flow động, kiểm tra registration còn tồn tại không.
2. **Xác định endpoint nhận đầu vào.** Tìm endpoint được nối với input channel, kiểm tra bean runtime và `Lifecycle.isRunning()`.
3. **Kiểm tra cơ chế nhận message.** Nếu là event-driven endpoint, kiểm tra subscriber; nếu là polling endpoint, kiểm tra poller, scheduler và cấu hình trigger.
4. **Kiểm tra channel.** Với `DirectChannel`, xem send có subscriber và có phát sinh lỗi không. Với `QueueChannel`, xem queue depth và thời gian message chờ.
5. **Kiểm tra executor và downstream.** Nếu dùng `ExecutorChannel`, kiểm tra thread pool và task queue. Kiểm tra handler, transaction, retry và dịch vụ được gọi ở bước sau.
6. **Đối chiếu error channel và quan sát.** Tìm exception, rejected task, retry exhaustion hoặc message được chuyển sang luồng lỗi.

Ví dụ, nếu endpoint là `PollingConsumer` đang stopped trong khi `QueueChannel` còn 120 message, cấu hình flow vẫn có thể hoàn toàn đúng. Vấn đề nằm ở trạng thái runtime của consumer hoặc scheduler. Ngược lại, nếu endpoint đang running nhưng executor queue tăng liên tục, điểm nghẽn có thể nằm ở năng lực xử lý phía sau chứ không phải cấu hình kết nối flow.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Có bean `IntegrationFlow` nghĩa là flow đang xử lý message. | Bean mô tả flow; cần kiểm tra các endpoint runtime và trạng thái lifecycle. |
| Endpoint tồn tại nghĩa là endpoint đã start. | Bean có thể tồn tại với `autoStartup=false` hoặc đã được stop. |
| `isRunning() == true` nghĩa là flow khỏe mạnh. | Nó chỉ phản ánh trạng thái lifecycle của component; cần xem metrics, queue, executor và lỗi. |
| Stop flow sẽ xóa message đang chờ. | Stop điều khiển lifecycle; message trong queue/store có thể vẫn tồn tại. |
| Mọi bước trong flow có một thread riêng. | Thread phụ thuộc channel và executor; `DirectChannel` thường chạy đồng bộ. |
| Flow động chỉ cần gọi stop khi không dùng nữa. | Stop giữ registration; cần destroy khi muốn gỡ flow và component khỏi context. |
| Integration Graph chứng minh message đã đi qua flow thành công. | Graph biểu diễn cấu trúc component; cần log, metrics và tracing để xác nhận xử lý thực tế. |

## 11. Tự kiểm tra

**Tình huống:** Một flow tĩnh đã được khai báo bằng `@Bean`. Sau khi ứng dụng khởi động, endpoint polling được cấu hình `autoStartup=false`. `QueueChannel` vẫn nhận message nhưng consumer không lấy message ra.

1. Flow definition có tồn tại không?
2. Việc bean endpoint tồn tại có chứng minh polling đang diễn ra không?
3. Cần kiểm tra trạng thái nào để giải thích queue tăng?
4. Khi gọi `start()` cho endpoint, điều gì được kích hoạt?

**Gợi ý trả lời:** (1) Có, flow đã được khai báo và xử lý trong ApplicationContext. (2) Không, endpoint có thể tồn tại nhưng chưa start. (3) Kiểm tra lifecycle của polling endpoint, poller/scheduler và queue depth. (4) Endpoint được khởi động và lịch polling được kích hoạt theo cấu hình; message đang chờ có thể được consumer lấy ra.

**Bài tập vận hành:** Tạo một flow có `QueueChannel` và polling endpoint. Chạy ứng dụng, quan sát trạng thái endpoint, gửi một vài message, sau đó stop endpoint và gửi tiếp message. Ghi lại queue depth trước và sau khi start lại endpoint. Lặp lại với một flow dùng `DirectChannel` để so sánh hành vi khi không có hàng đợi giữ message.

## Tài liệu tham khảo

- [Spring Integration Reference — Programming Tips and Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html)
- [Spring Integration Reference — Endpoint Lifecycle](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Reference — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html)
- [Spring Framework Reference — Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Integration Javadoc — IntegrationFlowContext](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/context/IntegrationFlowContext.html)

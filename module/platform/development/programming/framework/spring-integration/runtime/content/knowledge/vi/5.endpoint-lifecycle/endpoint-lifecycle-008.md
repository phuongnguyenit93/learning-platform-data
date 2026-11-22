# Restart endpoint sau lỗi hoặc sau maintenance

Trong Spring Integration, endpoint thường được quản lý theo vòng đời của Spring. Một endpoint có thể được start khi ApplicationContext khởi động, stop khi ứng dụng tắt, hoặc được điều khiển trong lúc runtime để phục hồi sau sự cố hay phục vụ maintenance. Tuy nhiên, gọi `start()` sau `stop()` chỉ khôi phục khả năng nhận và xử lý message của endpoint. Nó không tự sửa dependency đang lỗi, không bảo đảm message thất bại được phát lại và cũng không tự drain các task đang chạy.

Muốn restart an toàn, trước hết phải xác định endpoint thực sự đang ở trạng thái nào, lỗi xảy ra ở đâu và message đang nằm trong channel, executor hay broker. Sau đó điều phối producer, consumer, công việc đang chạy và dependency theo đúng thứ tự.

## 1. Endpoint có lifecycle riêng

Các endpoint của Spring Integration thường được xây dựng trên `AbstractEndpoint`, một lớp nền tích hợp với lifecycle của Spring. Endpoint hỗ trợ các thao tác `start()`, `stop()` và `isRunning()` thông qua `Lifecycle`; nhiều endpoint còn triển khai `SmartLifecycle` để tham gia thứ tự khởi động và dừng của ApplicationContext.

| API | Ý nghĩa |
|---|---|
| `start()` | Bắt đầu hoạt động của endpoint |
| `stop()` | Dừng hoạt động của endpoint |
| `isRunning()` | Cho biết endpoint hiện được đánh dấu đang chạy hay không |
| `isAutoStartup()` | Cho biết endpoint có tự khởi động theo lifecycle của context hay không |
| `getPhase()` | Cho biết phase dùng để sắp xếp lifecycle khi context start/stop |
| `stop(Runnable callback)` | Với `SmartLifecycle`, báo hoàn tất quá trình stop qua callback |

`isRunning()` là trạng thái lifecycle, không phải health check đầy đủ. Endpoint có thể vẫn running trong khi handler liên tục ném exception, dependency không truy cập được hoặc message bị chuyển vào error flow. Ngược lại, endpoint stopped có thể là kết quả của maintenance có chủ đích chứ không phải sự cố.

`autoStartup` cũng không phải công tắc bật/tắt ngay tại runtime. Nó quyết định endpoint có tự start trong quá trình khởi tạo ApplicationContext hay không. Sau khi context đã chạy, dùng `start()` và `stop()` để thay đổi trạng thái hiện tại.

### Endpoint khác IntegrationFlow

Một `IntegrationFlow` có thể tạo nhiều endpoint, channel và adapter. Stop một endpoint chỉ tác động tới lifecycle của endpoint đó. Nó không mặc nhiên dừng toàn bộ flow, channel, executor dùng chung hoặc các endpoint lân cận. Nếu cần dừng toàn bộ một flow được đăng ký động, cần điều khiển registration tương ứng trong `IntegrationFlowContext`; nếu chỉ cần tạm ngừng một consumer, điều khiển endpoint cụ thể thường có phạm vi nhỏ hơn.

## 2. Exception không đồng nghĩa endpoint đã stopped

Khi một message xử lý thất bại, đừng vội restart endpoint. Trước tiên xác minh lỗi đã làm endpoint dừng thật hay chỉ làm lần xử lý đó thất bại.

Hành vi phụ thuộc vào loại endpoint, channel, poller, executor và error handling được cấu hình:

- Với `DirectChannel`, handler thường chạy trên thread gửi message. Exception có thể truyền ngược về producer hoặc được xử lý tại ranh giới error handling tương ứng.
- Với `ExecutorChannel`, xử lý chạy trên worker thread. Producer có thể đã kết thúc trước khi worker báo lỗi; cần tìm error flow và log theo message ID hoặc Correlation ID.
- Với polling endpoint, một lần poll có thể thất bại nhưng scheduler và endpoint vẫn tiếp tục hoạt động tùy error handler, retry advice và cấu hình poller.
- Với inbound adapter kết nối broker, việc message được redeliver, requeue hay acknowledge phụ thuộc broker, acknowledgment mode và transaction.

Vì vậy, một exception đơn lẻ không chứng minh endpoint đã ngừng chạy. Hãy kiểm tra `isRunning()`, log lifecycle, số message nhận được, số lỗi và trạng thái consumer. Nếu endpoint vẫn running nhưng xử lý lỗi, cần sửa nguyên nhân hoặc chính sách retry trước khi cân nhắc restart.

### Phân loại trước khi thao tác

| Quan sát | Hướng điều tra |
|---|---|
| Endpoint running, một message thất bại | Kiểm tra payload, handler, validation, errorChannel và retry |
| Endpoint running, lỗi lặp lại trên nhiều message | Kiểm tra dependency, connection pool, timeout, cấu hình và backoff |
| Endpoint stopped ngoài dự kiến | Tìm log stop, lifecycle owner, quản trị runtime và lỗi khi khởi động |
| Endpoint running nhưng không nhận message | Kiểm tra channel subscription, poller, inbound source, routing và backlog |
| Endpoint vừa start lại rồi dừng hoặc lỗi ngay | Kiểm tra dependency chưa healthy, cấu hình chưa hợp lệ hoặc lỗi phát sinh trong `doStart`/lúc nhận message đầu tiên |

Restart chỉ hợp lý khi endpoint đã stopped ngoài ý muốn, cần tái kích hoạt sau maintenance, hoặc component cần được stop/start để áp dụng thay đổi mà lifecycle của nó hỗ trợ. Nếu lỗi nằm trong message hoặc dependency, restart đơn thuần thường chỉ khiến lỗi xuất hiện lại.

## 3. Điều khiển endpoint bằng Lifecycle

Trong code quản trị nội bộ, có thể inject endpoint bean dưới kiểu `Lifecycle` hoặc `SmartLifecycle`, rồi gọi các thao tác lifecycle. Tên bean trong ví dụ phải là tên endpoint thực tế trong ApplicationContext; endpoint do DSL tạo có thể có tên được framework sinh ra.

~~~java
@Component
public class EndpointLifecycleController {

    private final Lifecycle ordersEndpoint;

    public EndpointLifecycleController(
            @Qualifier("ordersEndpoint") Lifecycle ordersEndpoint) {
        this.ordersEndpoint = ordersEndpoint;
    }

    public synchronized void restart() {
        if (ordersEndpoint.isRunning()) {
            ordersEndpoint.stop();
        }

        verifyDependenciesAreReady();

        ordersEndpoint.start();
    }

    private void verifyDependenciesAreReady() {
        // Kiểm tra database, remote service, connection hoặc cấu hình liên quan.
    }
}
~~~

Đoạn code minh họa thao tác lifecycle; trong ứng dụng thực tế, `verifyDependenciesAreReady()` cần trả kết quả rõ ràng hoặc ném exception nếu chưa sẵn sàng. Không start endpoint khi dependency vẫn lỗi. Cũng cần ghi log trạng thái trước và sau thao tác, đồng thời bảo đảm chỉ một luồng quản trị thực hiện restart cùng endpoint tại một thời điểm.

Nếu cần đợi quá trình stop bất đồng bộ hoàn tất, dùng contract `SmartLifecycle.stop(Runnable callback)` và chỉ start lại sau callback. Không gọi `start()` ngay sau một lệnh stop bất đồng bộ nếu endpoint hoặc tác vụ đang chạy chưa hoàn tất quá trình dừng.

## 4. Điều khiển qua Control Bus

Spring Integration Control Bus cho phép gửi biểu thức điều khiển tới bean trong ApplicationContext. Đây là cách tiện dụng để thao tác endpoint khi vận hành mà không phải viết một service riêng cho từng lệnh.

~~~java
@Bean
IntegrationFlow controlBusFlow() {
    return IntegrationFlow.from("controlBus.input")
            .controlBus()
            .get();
}
~~~

Khi Control Bus đã được cấu hình, có thể gửi lệnh dạng biểu thức tới input channel:

~~~java
controlBusInput.send(new GenericMessage<>("@ordersEndpoint.stop()"));
controlBusInput.send(new GenericMessage<>("@ordersEndpoint.start()"));
~~~

`ordersEndpoint` ở đây là bean name thực tế của endpoint được phép điều khiển. Có thể dùng các biểu thức khác để đọc trạng thái hoặc gọi phương thức quản trị được expose. Hãy giới hạn channel Control Bus trong phạm vi quản trị đáng tin cậy, kiểm soát quyền gửi lệnh và audit ai đã thực hiện start/stop. Không expose một Control Bus có quyền gọi bean tùy ý ra public network.

Control Bus chỉ là cơ chế gửi lệnh. Nó không tự xác minh dependency đã healthy, message đã drain hay endpoint đã xử lý thành công sau khi start. Các bước đó vẫn cần quy trình vận hành và quan sát riêng.

## 5. Quy trình restart sau lỗi

Khi endpoint stopped ngoài dự kiến, nên xử lý theo trình tự:

1. **Xác định đúng endpoint.** Ghi lại bean name, component name, channel đầu vào, loại endpoint và flow chứa nó.
2. **Xác minh trạng thái.** Đọc `isRunning()` và log lifecycle để phân biệt endpoint stopped với endpoint running nhưng message thất bại.
3. **Tìm nguyên nhân gốc.** Kiểm tra exception, failed message metadata, errorChannel, retry, transaction, timeout, connection và trạng thái dependency.
4. **Ngăn lỗi lặp lại.** Nếu dependency đang lỗi, chờ hoặc phục hồi dependency; nếu message độc hại hoặc dữ liệu không hợp lệ, chuyển message vào error handling phù hợp.
5. **Xử lý message đang chờ.** Xác định message còn trong queue/broker, task đã submit vào executor hay message đã bị acknowledge. Chọn drain, giữ backlog, retry hoặc chuyển dead-letter theo chính sách.
6. **Start endpoint.** Chỉ start sau khi điều kiện cần thiết đã sẵn sàng.
7. **Xác minh phục hồi.** Kiểm tra endpoint running, consumer nhận message, backlog giảm, error rate trở về mức bình thường và không có lỗi lặp lại.

Nếu endpoint tự dừng vì lỗi trong quá trình start, cần xem exception của chính lần start đó. Lặp đi lặp lại `start()` mà không thay đổi điều kiện lỗi có thể tạo log nhiễu và làm tình trạng khó chẩn đoán hơn.

## 6. Quy trình restart phục vụ maintenance

Maintenance thường có kế hoạch, vì vậy có thể điều phối thứ tự để tránh message đến khi consumer chưa sẵn sàng.

~~~mermaid
flowchart TD
    A[Thông báo maintenance] --> B[Ngừng hoặc chặn producer mới]
    B --> C[Drain hoặc giữ backlog theo chính sách]
    C --> D[Stop endpoint cần bảo trì]
    D --> E[Thay đổi dependency / cấu hình]
    E --> F[Kiểm tra dependency healthy]
    F --> G[Start consumer endpoint]
    G --> H[Kiểm tra nhận và xử lý thử]
    H --> I[Mở lại producer]
    I --> J[Theo dõi backlog và error rate]
~~~

Thứ tự cụ thể phụ thuộc topology. Nếu endpoint là consumer của queue, có thể dừng producer trước, đợi queue được drain hoặc chấp nhận giữ backlog, rồi stop consumer. Nếu maintenance chỉ tác động tới handler và muốn giữ message chờ, có thể stop consumer trong khi producer tiếp tục ghi vào queue, nhưng phải bảo đảm queue còn capacity và có backpressure phù hợp.

Khi khởi động lại, thường start consumer trước rồi mới mở producer. Với inbound adapter chính là nguồn message, adapter đó có thể là endpoint cần start cuối cùng sau khi các downstream endpoint đã sẵn sàng.

### Drain và in-flight work

`stop()` không phải lệnh drain tổng quát cho toàn bộ topology. Tùy endpoint:

- Polling endpoint có thể ngừng các lần poll tiếp theo, trong khi lần poll đang thực thi cần thời gian hoàn tất.
- Event-driven consumer có thể ngừng nhận message mới từ channel sau khi unsubscribe; lời gọi handler đã bắt đầu có thể vẫn đang chạy.
- Executor có thể còn task đã submit nhưng chưa chạy. Stop endpoint không nhất thiết dừng hoặc drain executor dùng chung.
- Broker consumer có thể có message đang unacknowledged; kết quả khi stop phụ thuộc broker và acknowledgment mode.

Nếu cần bảo đảm không còn xử lý đang chạy, phải có cơ chế quiesce và chờ riêng: chặn nguồn mới, theo dõi in-flight count, đợi executor hoàn tất hoặc dùng callback lifecycle thích hợp. Không shutdown một `TaskExecutor` dùng chung chỉ vì một endpoint đang maintenance; executor có thể đang phục vụ các flow khác.

## 7. Channel quyết định message chờ ở đâu

Khi endpoint dừng, hành vi của message phụ thuộc channel và nguồn gửi.

| Channel/nguồn | Khi consumer dừng | Điều cần kiểm tra |
|---|---|---|
| `DirectChannel` | Không có buffer tích hợp; gửi khi không có subscriber có thể thất bại | Dừng producer hoặc route sang buffer/error path trước khi stop consumer |
| `QueueChannel` | Message có thể tiếp tục được enqueue và chờ consumer | Capacity, send timeout, backlog và loại MessageStore backing |
| `ExecutorChannel` | Task đã được executor nhận có thể vẫn chạy dù endpoint liên quan dừng | Executor queue, in-flight task, rejection và context propagation |
| `PublishSubscribeChannel` | Các subscriber còn hoạt động vẫn có thể nhận message; nhánh bị dừng có thể không xử lý | Xác định semantics của từng subscriber và có cần durable fan-out không |
| Broker inbound adapter | Broker giữ hoặc redeliver message tùy cấu hình consumer/acknowledgment | Ack mode, transaction, prefetch, requeue và dead-letter policy |

`QueueChannel` trong bộ nhớ không tự trở thành durable chỉ vì endpoint được restart. Nếu tiến trình JVM bị tắt, message trong queue bộ nhớ có thể mất. Muốn giữ message qua restart tiến trình, cần lựa chọn persistent store hoặc broker và cấu hình durability phù hợp.

Với broker, không giả định mọi message đang xử lý đều được redeliver khi stop. Nếu message đã acknowledge hoặc transaction đã commit, broker có thể không gửi lại. Nếu message chưa acknowledge, broker có thể requeue theo cấu hình. Kiểm tra semantics của adapter và broker cụ thể trước khi lập kế hoạch bảo trì.

## 8. Retry, Error Channel và Transaction sau restart

Restart endpoint và retry message là hai thao tác khác nhau.

Retry advice có thể thử lại một message ngay trong lần xử lý hoặc theo chính sách backoff. Error flow có thể nhận `ErrorMessage` khi xử lý thất bại. Một số nguồn message hỗ trợ redelivery; một số ứng dụng gửi message lỗi sang dead-letter channel hoặc lưu trạng thái lỗi riêng. Restart endpoint không tự kích hoạt lại các cơ chế này và không tự đưa message đã thất bại trở lại input channel.

Khi transaction được cấu hình cho poller hoặc broker, exception có thể khiến transaction rollback và nguồn message có thể phát lại message. Nhưng điều này chỉ xảy ra khi transaction manager, resource và acknowledgment mode thực sự tham gia cùng transaction theo cấu hình. Không suy ra redelivery chỉ từ việc endpoint ném exception.

Trước khi replay thủ công, kiểm tra side effect đã xảy ra hay chưa. Nếu handler đã ghi database hoặc gọi dịch vụ bên ngoài trước khi lỗi xảy ra, replay có thể tạo dữ liệu trùng. Dùng idempotency key, unique constraint hoặc cơ chế deduplication phù hợp. Retry cần giới hạn số lần, có backoff và phân biệt lỗi tạm thời với lỗi không thể phục hồi.

Một checklist riêng cho message lỗi:

- Xác định message ID, Correlation ID và failed message metadata.
- Kiểm tra message còn ở channel/broker, đã acknowledge hay đã chuyển sang error/dead-letter flow.
- Xác định retry đã chạy bao nhiêu lần và còn được phép thử lại không.
- Kiểm tra transaction commit/rollback và side effect đã thực hiện.
- Chỉ replay khi nguyên nhân đã được khắc phục và thao tác có tính idempotent hoặc đã có cách ngăn xử lý trùng.

## 9. Thay đổi cấu hình hay chỉ restart?

Restart phù hợp khi giữ nguyên cấu trúc endpoint và chỉ cần dừng rồi hoạt động lại, ví dụ sau khi dependency được phục hồi hoặc maintenance đã hoàn tất. Nếu thay đổi cấu trúc flow, channel, handler bean hoặc các thành phần cần được tạo lại, stop/start endpoint hiện tại có thể không đủ.

| Thay đổi | Hướng xử lý thường phù hợp |
|---|---|
| Dependency tạm thời mất kết nối, endpoint đã stopped | Phục hồi dependency, xác minh health, rồi start endpoint |
| Cần tạm ngừng consumer trong maintenance | Stop endpoint, quản lý producer/backlog, sau đó start lại |
| Thay đổi thuộc tính runtime có setter hỗ trợ | Áp dụng thay đổi theo contract của component, xác minh rồi restart nếu component yêu cầu |
| Thay đổi topology hoặc thay handler bean | Cập nhật/re-register flow hoặc quản lý lại bean theo lifecycle phù hợp |
| Flow động của tenant không còn được dùng | Stop và remove registration tương ứng, xử lý backlog theo chính sách |
| Muốn thay đổi `autoStartup` cho lần khởi động sau | Cập nhật cấu hình bean; không xem đó là lệnh start/stop runtime hiện tại |

Không dùng restart để che lỗi cấu hình. Nếu endpoint start lại nhưng handler vẫn trỏ tới dependency cũ, bean cũ hoặc cấu hình chưa được refresh, lỗi sẽ tái diễn. Hãy xác định component nào cần được tạo lại và dùng đúng lifecycle của component đó.

## 10. Quan sát trước, trong và sau restart

Ghi log có cấu trúc cho mỗi thao tác quản trị với endpoint name, component type, hành động, người hoặc hệ thống khởi tạo, lý do, thời điểm và kết quả. Khi có lỗi message, thêm message ID, Correlation ID và exception type; tránh ghi toàn bộ payload hoặc credential.

Theo dõi các tín hiệu sau:

| Tín hiệu | Trước restart | Sau restart |
|---|---|---|
| Endpoint lifecycle | `isRunning`, thời điểm stop và nguyên nhân | `isRunning` và thời điểm start thành công |
| Message throughput | Tốc độ nhận/xử lý trước maintenance | Có message mới được xử lý ổn định |
| Queue/broker backlog | Số message đang chờ hoặc unacknowledged | Backlog giảm hoặc nằm trong giới hạn dự kiến |
| Executor | Active threads, queue size, rejected tasks | Task được xử lý, không tăng rejection |
| Error flow | Error count, retry count, dead-letter count | Không còn lỗi lặp hoặc có xu hướng giảm rõ rệt |
| Dependency | Health, connection, latency | Healthy và latency trong giới hạn |

Không chỉ kiểm tra `isRunning()` rồi kết luận đã phục hồi. Một endpoint có thể running nhưng không có consumer hợp lệ, không poll được hoặc mọi message đều bị lỗi. Hãy gửi một message kiểm tra an toàn nếu có thể, xác nhận nó đi qua đúng endpoint và đối chiếu metric/log sau xử lý.

## 11. Checklist restart endpoint

- [ ] Xác định chính xác endpoint bean và flow chứa endpoint.
- [ ] Đọc `isRunning()` và log để biết endpoint thật sự stopped hay chỉ xử lý message lỗi.
- [ ] Tìm nguyên nhân gốc và xác minh dependency đã healthy.
- [ ] Chặn producer hoặc thiết lập backpressure trước khi dừng consumer nếu channel không có buffer.
- [ ] Xác định cách drain, giữ backlog và xử lý in-flight task.
- [ ] Kiểm tra retry, transaction, acknowledgment và dead-letter policy.
- [ ] Stop đúng endpoint; không dừng nhầm executor hoặc flow dùng chung.
- [ ] Start consumer sau khi dependency sẵn sàng và trước khi mở lại producer.
- [ ] Xác nhận endpoint running, message được xử lý, backlog và error rate ổn định.
- [ ] Ghi lại kết quả maintenance/restart và các message cần replay riêng.

Restart endpoint là một thao tác lifecycle có phạm vi cụ thể. Phục hồi hoàn chỉnh còn cần dependency khỏe, message được bảo toàn theo semantics của channel hoặc broker, các task đang chạy được xử lý đúng và hệ thống có bằng chứng rằng message mới đã đi qua thành công. Phân biệt rõ trạng thái endpoint với trạng thái message sẽ giúp tránh restart lặp lại mà không giải quyết được nguyên nhân.

## Tài liệu tham khảo

- [Spring Framework Reference: Lifecycle and SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Integration Reference: Endpoint Lifecycle](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Reference: Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html)
- [Spring Integration Reference: Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)

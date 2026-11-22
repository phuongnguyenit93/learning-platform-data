# WireTap và quan sát message qua channel

Trong Spring Integration, một message thường đi qua nhiều channel và endpoint trước khi hoàn tất nghiệp vụ. Khi cần quan sát dữ liệu đang đi qua mà không chèn thêm handler vào luồng chính, có thể dùng **WireTap**. WireTap là một implementation của `ChannelInterceptor`: nó quan sát thao tác gửi trên channel, lấy message và gửi message đó sang một channel khác để tạo thêm một nhánh xử lý.

WireTap thường được dùng để ghi log, audit, đo lưu lượng, kiểm tra payload trong môi trường test hoặc chuyển một bản message tới flow giám sát. Nó giúp bổ sung khả năng quan sát mà không phải sửa logic nghiệp vụ của producer và handler chính.

Điểm cần hiểu đúng là WireTap **không tự tạo thread bất đồng bộ**. Nhánh tap chạy đồng bộ hay bất đồng bộ phụ thuộc channel đích mà WireTap gửi tới. Nếu channel đích là `DirectChannel`, xử lý tap có thể chạy ngay trên thread gửi message và làm tăng latency của flow chính. Nếu channel đích là `QueueChannel` hoặc `ExecutorChannel`, việc gửi sang nhánh tap có thể tạo ranh giới bất đồng bộ theo semantics của channel đó.

## 1. WireTap nằm ở đâu trong message flow?

`MessageChannel` là điểm giao tiếp giữa producer và consumer. Channel có thể cung cấp interceptor để thực hiện các hành vi chung trước, trong hoặc sau thao tác send/receive. WireTap tận dụng điểm này để gửi thêm message tới một channel khác.

Sơ đồ:

~~~mermaid
flowchart LR
    P["Producer"] --> C["Main channel"]
    C --> H["Main handler / flow"]
    C -. "ChannelInterceptor: WireTap" .-> T["Tap channel"]
    T --> O["Logging / audit / metrics flow"]
~~~

Khi producer gửi message vào main channel:

1. Channel chạy các interceptor theo thứ tự đã đăng ký.
2. WireTap nhận message đang được gửi và gửi nó sang tap channel nếu selector cho phép.
3. Luồng chính tiếp tục gửi message qua channel.
4. Tap channel chuyển message tới consumer riêng của nhánh quan sát.
5. Nhánh tap có thể ghi log, lưu audit record, tạo metric hoặc kiểm tra dữ liệu.

WireTap không thay thế channel chính và không tự quyết định message đi tới handler nghiệp vụ nào. Nó tạo một nhánh phụ để quan sát cùng message.

### WireTap khác router và publish-subscribe thế nào?

| Thành phần | Vai trò |
|---|---|
| WireTap | Quan sát message trên một channel và gửi thêm message sang tap channel |
| Router | Chọn output channel dựa trên payload, header hoặc quy tắc nghiệp vụ |
| PublishSubscribeChannel | Phát message tới tất cả subscriber của chính channel đó |
| Bridge | Chuyển tiếp message từ channel này sang channel khác như một bước của flow |
| Logging channel adapter | Nhận message và ghi log theo cấu hình |

WireTap phù hợp khi muốn quan sát một channel hiện có mà không thay đổi cấu trúc flow chính. Publish-subscribe phù hợp khi broadcast là semantics chính của luồng. Router phù hợp khi cần phân nhánh theo nội dung message.

## 2. WireTap là ChannelInterceptor

Spring Integration cung cấp `WireTap` trong package `org.springframework.integration.channel.interceptor`. Nó triển khai cơ chế interceptor và chuyển message sang một `MessageChannel` khác.

Về ý tưởng, WireTap làm ba việc:

- Nhận biết message đi qua channel đang được intercept.
- Có thể kiểm tra selector để quyết định có tap message hay không.
- Gửi message được chọn tới channel đích.

WireTap không cần handler nghiệp vụ của flow chính biết rằng có nhánh quan sát. Producer vẫn gửi tới channel cũ; channel interceptor đảm nhiệm việc tạo nhánh phụ.

### WireTap không phải deep copy

Message trong Spring Messaging có envelope bất biến gồm payload và headers. Tuy nhiên, payload bên trong có thể là object mutable. Không nên giả định WireTap tạo một bản sao sâu độc lập của toàn bộ object graph.

Nếu payload là `Order` mutable và nhánh audit sửa trực tiếp object đó, handler chính có thể nhìn thấy thay đổi vì hai nhánh có thể cùng tham chiếu payload. Với nhánh quan sát, hãy ưu tiên đọc dữ liệu và tạo representation riêng để lưu log/audit; nếu cần sửa, hãy clone hoặc map sang DTO riêng trước.

Tương tự, không nên đưa object nhạy cảm hoặc object chứa tài nguyên sống như stream, connection hay entity proxy vào tap flow mà không kiểm soát cách đọc và serialization.

## 3. Chọn channel đích quyết định đồng bộ hay bất đồng bộ

WireTap không mặc định chạy ở background. Nó gửi message sang tap channel; chính loại channel đó quyết định cách nhánh tap được thực thi.

| Tap channel | Cách xử lý | Ảnh hưởng tới flow chính |
|---|---|---|
| `DirectChannel` | Dispatch handler trực tiếp trên thread gửi | Tap handler có thể làm chậm lời gọi gửi và có thể ảnh hưởng lỗi đồng bộ |
| `QueueChannel` | Lưu message trong queue; polling consumer lấy sau | Main flow thường chỉ chờ thao tác enqueue, còn xử lý tap diễn ra sau |
| `ExecutorChannel` | Bàn giao dispatch tới TaskExecutor | Main flow không chờ handler tap hoàn tất sau khi task được nhận |
| Broker-backed channel/adapter | Gửi qua broker theo adapter và broker semantics | Độ trễ, persistence, acknowledgment phụ thuộc cấu hình transport |

Ví dụ, nếu tap channel là DirectChannel và logging handler ghi file chậm, producer có thể bị block bởi thao tác log. Nếu tap channel là QueueChannel, producer chỉ gửi message vào queue; một polling flow riêng xử lý log sau đó. Nếu tap channel là ExecutorChannel, task được bàn giao cho worker pool, nhưng cần quản lý queue capacity và rejection policy của executor.

### Chọn theo mục tiêu quan sát

- **Debug cục bộ:** DirectChannel có thể đủ khi handler log ngắn và muốn thấy lỗi ngay.
- **Giám sát không làm chậm flow:** QueueChannel hoặc ExecutorChannel có thể tách thời gian xử lý.
- **Audit cần lưu bền vững:** dùng storage hoặc broker có persistence và transaction semantics phù hợp; QueueChannel trong bộ nhớ không bảo đảm giữ dữ liệu qua process restart.
- **Kiểm tra trong test:** QueueChannel giúp test đọc message được tap mà không cần tạo logging infrastructure.

Không nên chọn asynchronous channel chỉ để tăng tốc một cách mù quáng. Nếu worker pool đầy hoặc tap queue tăng liên tục, nhánh quan sát vẫn có thể gây áp lực bộ nhớ hoặc từ chối task.

## 4. Cấu hình WireTap cục bộ bằng XML

Có thể khai báo interceptor ngay trong channel cần quan sát:

~~~xml
<int:channel id="ordersChannel">
    <int:interceptors>
        <int:wire-tap channel="ordersAuditChannel"
                      selector-expression="headers['audit'] == true"/>
    </int:interceptors>
</int:channel>

<int:channel id="ordersAuditChannel">
    <int:queue capacity="1000"/>
</int:channel>

<int:service-activator input-channel="ordersAuditChannel"
                       ref="ordersAuditHandler"
                       method="record">
    <int:poller fixed-delay="250"/>
</int:service-activator>
~~~

Trong ví dụ:

- `ordersChannel` là channel chính.
- WireTap gửi message sang `ordersAuditChannel`.
- `selector-expression` chỉ tap message có header `audit` bằng `true`.
- Queue giúp tách thời điểm gửi message audit khỏi thời điểm handler audit xử lý.

Nếu selector không được cấu hình, WireTap có thể tap mọi message đi qua channel theo cấu hình mặc định. Với lưu lượng lớn, nên lọc sớm theo header hoặc `MessageSelector` để tránh ghi dữ liệu không cần thiết.

## 5. Cấu hình bằng Java và IntegrationFlow DSL

Có thể tạo tap channel dạng queue, gắn `WireTap` trực tiếp vào channel chính, rồi dùng một polling flow để xử lý nhánh audit:

~~~java
@Configuration
@EnableIntegration
class OrdersIntegrationConfiguration {

    @Bean
    QueueChannel ordersAuditChannel() {
        return new QueueChannel(1_000);
    }

    @Bean
    MessageChannel ordersChannel(QueueChannel ordersAuditChannel) {
        DirectChannel channel = new DirectChannel();
        channel.addInterceptor(new WireTap(ordersAuditChannel));
        return channel;
    }

    @Bean
    IntegrationFlow ordersAuditFlow(
            QueueChannel ordersAuditChannel,
            OrdersAuditHandler handler
    ) {
        return IntegrationFlow.from(
                        ordersAuditChannel,
                        endpoint -> endpoint.poller(Pollers.fixedDelay(250))
                )
                .handle(handler, "record")
                .get();
    }

    @Bean
    IntegrationFlow ordersFlow(
            @Qualifier("ordersChannel") MessageChannel ordersChannel,
            OrderHandler handler
    ) {
        return IntegrationFlow.from(ordersChannel)
                .handle(handler, "process")
                .get();
    }
}
~~~

Trong ví dụ, main flow dùng `DirectChannel`; WireTap gửi message sang `QueueChannel` audit. Polling consumer của audit flow lấy message theo fixed delay 250 ms. Handler audit vì vậy chạy trên thread của poller, tách khỏi thread gửi message sang channel chính. Queue capacity 1.000 là giới hạn buffer minh họa; cần chọn theo burst và chính sách khi queue đầy.

Một cách DSL ngắn hơn là `MessageChannels.queue().wireTap("loggingFlow.input").get()`. Khi dùng tên channel dạng string, Spring resolve channel bean trong application context. Hãy kiểm tra kiểu channel thực tế của `loggingFlow.input`: nếu đó là DirectChannel mặc định, nhánh log vẫn đồng bộ. Muốn nhánh tap chạy bất đồng bộ, hãy bảo đảm channel đích thực sự là pollable hoặc executor-based.

## 6. Conditional WireTap bằng selector

Không phải message nào cũng cần quan sát. WireTap hỗ trợ lọc message bằng `MessageSelector` hoặc SpEL selector expression.

Ví dụ selector:

~~~java
@Component
class AuditMessageSelector implements MessageSelector {

    @Override
    public boolean accept(Message<?> message) {
        return Boolean.TRUE.equals(
                message.getHeaders().get("audit")
        );
    }
}
~~~

Cấu hình XML:

~~~xml
<int:wire-tap channel="ordersAuditChannel"
              selector="auditMessageSelector"/>
~~~

Hoặc dùng SpEL:

~~~xml
<int:wire-tap channel="ordersAuditChannel"
              selector-expression="headers['eventType'] == 'order.submitted'"/>
~~~

Selector nên nhanh, không có side effect và không gọi dịch vụ bên ngoài. Nếu selector thực hiện I/O hoặc truy vấn database, chính thao tác lọc đã trở thành chi phí trên đường gửi message.

### Chọn message theo mục đích quan sát

Một số cách lọc thường gặp:

| Điều kiện | Mục đích |
|---|---|
| Header `audit=true` | Chỉ ghi các nghiệp vụ cần audit |
| Event type cụ thể | Theo dõi một loại event |
| Tenant hoặc nguồn dữ liệu | Điều tra một nhóm traffic |
| Correlation ID có trong danh sách test | Thu thập trace của một request |
| Sampling theo tỷ lệ | Giảm lượng log ở hệ thống throughput cao |

Nếu dùng sampling, hãy xác định sampling theo message, theo correlation ID hay theo business key. Sampling từng message có thể chỉ giữ một phần các bước của cùng một workflow; sampling theo correlation ID thường giúp quan sát trọn vẹn một request hơn.

## 7. Global WireTap cho nhiều channel

Khi muốn áp dụng cùng một WireTap cho một nhóm channel, có thể đăng ký global channel interceptor theo pattern.

Ví dụ Java:

~~~java
@Bean
@GlobalChannelInterceptor(
        patterns = {"orders*", "payments*"},
        order = 3
)
WireTap integrationAuditTap(
        @Qualifier("integrationAuditChannel") MessageChannel auditChannel
) {
    return new WireTap(auditChannel);
}
~~~

Global interceptor được áp dụng cho các channel khớp pattern. Thuộc tính `order` xác định thứ tự tương đối với các interceptor khác.

Ví dụ XML:

~~~xml
<int:wire-tap pattern="orders*, payments*"
              order="3"
              channel="integrationAuditChannel"/>
~~~

Global WireTap hữu ích khi muốn bật quan sát cho nhiều channel mà không sửa từng channel definition. Nó cũng có thể dùng trong test để thu thập message từ một nhóm channel.

### Chọn pattern hẹp và rõ ràng

Không nên gắn global WireTap lên mọi channel nếu không cần thiết. Các channel nội bộ có thể chứa message trung gian, payload nhạy cảm hoặc dữ liệu lớn. Tap quá rộng làm tăng chi phí gửi, lưu trữ và logging.

Nên xác định pattern theo ranh giới nghiệp vụ, ví dụ `orders.*` hoặc `payments*` tùy naming convention của ứng dụng. Kiểm tra cả channel đích của WireTap để bảo đảm nó không bị chính WireTap intercept lại.

Từ Spring Integration 5.1, global channel interceptors cũng được áp dụng cho channel đăng ký động, ví dụ channel được tạo bằng `IntegrationFlowContext` hoặc `BeanFactory.initializeBean()`. Nếu ứng dụng chạy phiên bản cũ hơn, hãy kiểm tra behavior của dynamic channel trong phiên bản đó.

## 8. Tránh circular reference và tap loop

Một lỗi cấu hình nguy hiểm là WireTap của channel A gửi sang channel B, nhưng channel B cũng khớp pattern của chính WireTap đó. Khi message được gửi sang B, interceptor lại tap message sang B hoặc một channel khác nằm trong vòng lặp. Kết quả có thể là recursion, lặp message vô hạn hoặc tăng tải bất thường.

Ví dụ không an toàn:

~~~text
ordersChannel
  └─ WireTap → auditChannel

auditChannel
  └─ cùng global WireTap → auditChannel
~~~

Cách phòng tránh:

- Dùng pattern chỉ áp dụng lên channel nghiệp vụ, loại trừ channel tap/audit.
- Không đặt tap channel trùng với source channel.
- Tách naming convention cho channel quan sát, ví dụ prefix `audit.` hoặc suffix `.tap`.
- Với custom `ChannelInterceptor` tham chiếu tới channel khác, cân nhắc triển khai `VetoCapableInterceptor` để từ chối intercept các channel không phù hợp.
- Bổ sung kiểm tra runtime trong interceptor tùy chỉnh nếu cần bảo vệ khỏi tham chiếu vòng.

WireTap tích hợp cơ chế bảo vệ cho trường hợp tham chiếu channel và veto việc intercept channel đích của chính nó. Tuy vậy, global pattern vẫn cần được thiết kế cẩn thận vì các interceptor khác hoặc flow tùy chỉnh có thể tạo vòng lặp.

## 9. ChannelInterceptor có những hook nào?

WireTap là một loại interceptor chuyên biệt. Khi cần quan sát hoặc thay đổi hành vi send/receive tổng quát hơn, có thể triển khai `ChannelInterceptor`.

Các hook:

| Method | Khi nào được gọi? | Mục đích |
|---|---|---|
| `preSend(message, channel)` | Trước khi channel thực hiện send | Quan sát, biến đổi message hoặc trả `null` để chặn send |
| `postSend(message, channel, sent)` | Ngay sau thao tác send | Quan sát kết quả boolean của send |
| `afterSendCompletion(message, channel, sent, ex)` | Sau khi send kết thúc, kể cả có exception | Cleanup hoặc ghi nhận kết quả cuối |
| `preReceive(channel)` | Trước receive trên PollableChannel | Trả false để ngăn receive |
| `postReceive(message, channel)` | Sau khi lấy được message, trước khi trả về caller | Quan sát hoặc biến đổi message nhận được |
| `afterReceiveCompletion(message, channel, ex)` | Sau khi receive kết thúc | Cleanup hoặc ghi nhận lỗi |

Các method mặc định của interface là no-op hoặc trả message/boolean cho phép tiếp tục. Vì vậy, custom interceptor chỉ cần override các hook thực sự cần.

### preSend có thể chặn message

Nếu `preSend()` trả về `null`, thao tác send thực tế không được thực hiện. Điều này có thể dùng cho validation hoặc policy enforcement, nhưng phải được thiết kế rõ vì caller có thể nhận kết quả gửi thất bại.

Ví dụ minh họa:

~~~java
@Component
class RequiredHeaderInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        if (message.getHeaders().get("tenantId") == null) {
            return null;
        }
        return message;
    }
}
~~~

Đoạn code chỉ minh họa việc chặn message thiếu header. Trong production, nên có log/metric và error path phù hợp để người vận hành biết vì sao message bị chặn. Không nên âm thầm trả null nếu producer cần phân biệt validation failure với việc channel không nhận message.

### postReceive chỉ áp dụng cho PollableChannel

`receive()` chỉ có ý nghĩa với `PollableChannel`. Vì vậy, `preReceive()` và `postReceive()` không phải hook chung cho mọi channel.

Từ Spring Integration 5.1, `postReceive()` không còn được gọi khi không nhận được message. Nếu cần cleanup bất kể có message hay không, hãy dùng `afterReceiveCompletion()`.

### after completion và thứ tự interceptor

`afterSendCompletion()` và `afterReceiveCompletion()` được gọi sau khi thao tác hoàn tất, kể cả khi có exception, miễn hook trước tương ứng đã cho phép thao tác tiếp tục. Các callback completion được gọi theo thứ tự ngược với thứ tự interceptor đã chạy ở hook bắt đầu.

Với queue-based channel, send và receive có thể diễn ra trên hai thread khác nhau. Do đó, không thể giả định toàn bộ chuỗi callback send và receive luôn xen kẽ theo một thứ tự cố định. Chỉ có thể dựa vào thứ tự nội bộ của từng thao tác: `preSend` trước `postSend`, và `preReceive` trước `postReceive`.

## 10. Viết custom ChannelInterceptor để đo thời gian send

Một interceptor có thể ghi nhận thời gian send và trạng thái gửi. Ví dụ đơn giản:

~~~java
@Component
class ChannelTimingInterceptor implements ChannelInterceptor {

    private final MeterRegistry meterRegistry;

    ChannelTimingInterceptor(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        return MessageBuilder.fromMessage(message)
                .setHeader("observedAt", System.nanoTime())
                .build();
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex
    ) {
        Object start = message.getHeaders().get("observedAt");
        if (start instanceof Long startNanos) {
            long elapsed = System.nanoTime() - startNanos;
            meterRegistry.timer(
                    "integration.channel.send",
                    "channelType", channel.getClass().getSimpleName(),
                    "result", ex == null && sent ? "success" : "failure"
            ).record(elapsed, TimeUnit.NANOSECONDS);
        }
    }
}
~~~

Đây là ví dụ minh họa cách đo thời gian trong phạm vi thao tác send. Khi triển khai thật:

- Không dùng channel object hoặc message ID làm metric tag có cardinality cao.
- Dùng channel name ổn định thay vì `toString()` nếu giá trị đó chứa identity động.
- Không giả định thời gian send bằng thời gian xử lý toàn bộ message flow nếu channel đích là asynchronous.
- Đưa exception vào log hoặc counter riêng theo loại lỗi, tránh gắn exception message vào tag.
- Xác định interceptor đo send ở channel nào, vì cùng message có thể đi qua nhiều channel.

Nếu `preSend()` tạo message mới để thêm header timestamp, `afterSendCompletion()` nhận message đã qua chuỗi interceptor theo semantics của channel. Với interceptor khác cũng thay message, cần thống nhất thứ tự và header sử dụng để tránh ghi đè ngoài ý muốn.

## 11. Quan sát message bằng logging channel adapter

WireTap thường kết hợp với logging channel adapter để ghi message ở nhánh phụ.

Ví dụ XML:

~~~xml
<int:channel id="ordersChannel">
    <int:interceptors>
        <int:wire-tap channel="ordersLogChannel"/>
    </int:interceptors>
</int:channel>

<int:channel id="ordersLogChannel"/>

<int:logging-channel-adapter id="ordersLogger"
                             channel="ordersLogChannel"
                             level="DEBUG"
                             expression="payload.orderId"/>
~~~

Có thể dùng SpEL expression để chọn phần cần log từ payload và headers. Theo mặc định, logging channel adapter chỉ log payload; tùy chọn `log-full-message` cho phép log cả headers cùng payload.

Không nên bật full message logging ở production nếu headers hoặc payload có token, thông tin cá nhân, dữ liệu thanh toán hay thông tin định danh nhạy cảm. Hãy log trường tối thiểu cần chẩn đoán, áp dụng masking và kiểm soát quyền truy cập log.

### Log payload hay full message?

| Cách log | Khi phù hợp | Rủi ro |
|---|---|---|
| Chỉ log payload | Payload đã được thiết kế để log hoặc đã masking | Có thể thiếu correlation metadata |
| Log full message | Debug có kiểm soát trong môi trường phù hợp | Lộ headers, token, thông tin cá nhân |
| SpEL chọn field | Cần log một vài field để tìm kiếm | Expression sai có thể gây lỗi hoặc log dữ liệu không mong muốn |
| Log ID và metadata tối thiểu | Production observability | Cần correlation/tracing tốt để truy ngược |

Với hệ thống có throughput cao, logging từng message có thể tạo I/O lớn. Cân nhắc sampling, metrics tổng hợp hoặc tracing thay vì ghi toàn bộ payload.

## 12. WireTap và transaction boundary

WireTap không tự tạo transaction mới. Nếu tap channel là DirectChannel, việc gửi sang nhánh tap thường xảy ra đồng bộ trong cùng thread; transaction đang mở có thể bao quanh cả thao tác gửi tới tap channel nếu resource và transaction manager tham gia cùng transaction.

Điều này có thể hữu ích khi audit record phải commit cùng nghiệp vụ chính. Tuy nhiên, cần kiểm tra transaction resource thực tế. Ghi log file hoặc gọi HTTP không tự động rollback chỉ vì database transaction của main flow rollback.

Nếu tap channel là QueueChannel hoặc ExecutorChannel, nhánh tap được tách khỏi thread gửi. Transaction thread-bound của main flow không tự động truyền sang worker hoặc polling consumer. Việc enqueue message vào queue nội bộ cũng không đồng nghĩa audit record đã được lưu bền vững.

### Audit bắt buộc và quan sát best-effort

Phân biệt hai mục tiêu:

- **Quan sát best-effort:** log hoặc metric hỗ trợ debug; có thể chấp nhận mất một phần dữ liệu quan sát khi hệ thống quá tải.
- **Audit bắt buộc:** dữ liệu audit là yêu cầu nghiệp vụ hoặc kiểm soát; cần persistence, transaction, retry và khả năng phục hồi được thiết kế rõ.

WireTap một mình không bảo đảm exactly-once, durability hoặc atomic commit giữa flow chính và audit storage. Với audit bắt buộc, cân nhắc ghi audit trong cùng transaction với dữ liệu nghiệp vụ, transactional outbox hoặc một cơ chế lưu bền vững phù hợp.

## 13. WireTap và hiệu năng

Mỗi message được tap tạo thêm một lần send và một nhánh xử lý. Chi phí phụ thuộc channel đích, selector, serialization, logging, I/O và số lượng interceptor.

Những yếu tố cần đo:

- Tỷ lệ message được tap.
- Thời gian `preSend` và tổng thời gian send trên channel chính.
- Queue depth của tap channel.
- Số worker active và rejected task nếu dùng executor.
- Thời gian xử lý log/audit.
- Tỷ lệ message bị selector loại bỏ.
- Tài nguyên storage và dung lượng log.

Nếu tap channel là DirectChannel, handler phụ nằm trên đường gửi chính. Nếu tap channel bất đồng bộ, main flow có thể tiếp tục sớm hơn nhưng hệ thống cần capacity để xử lý backlog của nhánh tap.

### Backpressure và overload ở tap flow

Một nhánh tap có thể chậm hơn main flow. Khi dùng QueueChannel hữu hạn, queue có thể đầy; khi dùng ExecutorChannel, executor có thể reject task. Tùy channel và cách WireTap gửi message, lỗi gửi tap có thể ảnh hưởng thao tác send trên channel chính.

Vì vậy, cần quyết định rõ:

- Có chấp nhận mất log/metric khi tap flow quá tải không?
- Có cần làm chậm flow chính để bảo vệ audit không?
- Có cần lưu bền vững tap message không?
- Có retry hoặc dead-letter cho nhánh tap không?
- Queue capacity và executor rejection được quan sát bằng metric nào?

Không mặc định rằng WireTap là fire-and-forget. Chỉ channel và cấu hình thực tế mới quyết định hành vi đó.

## 14. Kiểm thử WireTap

Một test đơn giản có thể xác nhận message được gửi cả tới flow chính và tap channel.

~~~java
@Test
void wireTapSendsMessageToAuditChannel() {
    QueueChannel auditChannel = new QueueChannel();
    QueueChannel inputChannel = new QueueChannel();

    inputChannel.addInterceptor(new WireTap(auditChannel));

    Message<String> message =
            MessageBuilder.withPayload("order-123").build();

    boolean sent = inputChannel.send(message);

    assertThat(sent).isTrue();
    Message<?> main = inputChannel.receive(0);
    Message<?> tapped = auditChannel.receive(0);

    assertThat(main).isNotNull();
    assertThat(main.getPayload()).isEqualTo("order-123");
    assertThat(tapped).isNotNull();
    assertThat(tapped.getPayload()).isEqualTo("order-123");
}
~~~

Test này kiểm tra việc tap gửi message sang queue audit. Trong integration test thực tế, nên xác minh thêm:

1. Message vẫn tới handler chính.
2. Selector chỉ tap message phù hợp.
3. Tap flow không sửa payload làm thay đổi dữ liệu của main flow.
4. Khi tap channel lỗi hoặc đầy, hành vi main flow đúng policy.
5. Global interceptor chỉ áp dụng cho pattern đã chọn.
6. Tap channel không tự bị intercept tạo vòng lặp.
7. Với async tap, test chờ consumer xử lý bằng timeout có giới hạn thay vì giả định hoàn tất ngay sau `send()`.

Nếu dùng WireTap để kiểm tra một channel trong test, có thể cấu hình global WireTap chỉ cho channel pattern cần quan sát. Sau test, context riêng của test sẽ giải phóng interceptor và channel theo lifecycle.

## 15. Chẩn đoán khi tap không nhận được message

Khi main flow chạy nhưng tap flow không có dữ liệu, hãy kiểm tra theo ranh giới:

1. WireTap đã được đăng ký vào đúng channel chưa?
2. Channel bean mà producer gửi vào có phải channel được intercept không?
3. Selector có loại message vì header hoặc expression không khớp không?
4. Tap channel có được resolve đúng bean không?
5. Tap channel có consumer hoặc polling endpoint đang chạy không?
6. Nếu tap channel là queue, queue capacity có đầy hoặc consumer có đang poll không?
7. Nếu tap channel là executor, executor có active worker, queue capacity và rejection policy phù hợp không?
8. Global interceptor pattern có khớp tên channel không?
9. Channel động có được tạo trong phiên bản hỗ trợ global interceptor như mong đợi không?
10. Có lỗi serialization, logging expression hoặc downstream handler trong tap flow không?

Nếu main flow cũng bị lỗi sau khi thêm WireTap, kiểm tra tap channel có phải DirectChannel và handler tap có ném exception đồng bộ hay không. Nếu chỉ tap flow bị trễ, kiểm tra queue depth, poller và executor của nhánh phụ.

### Triệu chứng thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| Main flow chạy nhưng audit queue rỗng | Sai channel, selector không match hoặc WireTap chưa được đăng ký |
| Main flow chậm sau khi bật WireTap | Tap channel đồng bộ hoặc selector/handler tap tốn thời gian |
| Message audit bị lặp nhiều lần | Global interceptor tạo vòng lặp hoặc cùng message đi qua nhiều channel được tap |
| Tap flow không xử lý dù queue có message | Polling endpoint chưa start hoặc poller không hoạt động |
| Main flow lỗi khi tap handler lỗi | Tap channel đồng bộ và exception truyền ngược |
| Tap queue tăng liên tục | Consumer audit chậm hơn tốc độ tap |
| Log chứa dữ liệu không mong muốn | Log full message hoặc selector/expression quá rộng |
| Dynamic channel không được tap | Kiểm tra phiên bản Spring Integration và cách đăng ký global interceptor |

## 16. Checklist khi đưa WireTap vào production

- [ ] Đã xác định đúng channel cần quan sát chưa?
- [ ] WireTap có tap mọi message hay chỉ message được selector chấp nhận?
- [ ] Tap channel có đúng semantics đồng bộ/bất đồng bộ theo mục tiêu không?
- [ ] Có cần QueueChannel, ExecutorChannel hoặc broker-backed channel cho nhánh tap không?
- [ ] Queue capacity và executor rejection có được cấu hình hữu hạn không?
- [ ] Tap handler có thể block hoặc ném exception ảnh hưởng main flow không?
- [ ] Có vòng lặp giữa source channel, tap channel và global interceptor không?
- [ ] Payload mutable có bị nhánh tap thay đổi không?
- [ ] Header/payload nhạy cảm có được masking hoặc loại bỏ trước khi log không?
- [ ] Metric tag có cardinality thấp và không chứa message ID động không?
- [ ] Audit là best-effort hay yêu cầu durability/transaction?
- [ ] Có test xác minh main flow và tap flow độc lập không?
- [ ] Có dashboard cho tap queue depth, processing latency và rejection không?
- [ ] Global interceptor pattern có giới hạn đúng các channel cần quan sát không?

WireTap giúp quan sát message flow bằng cách thêm một nhánh phụ tại channel. Để dùng an toàn, hãy xác định **message nào được tap**, **tap channel xử lý đồng bộ hay bất đồng bộ**, **nhánh phụ có thể ảnh hưởng main flow ra sao** và **dữ liệu nào được phép quan sát**. Khi bốn điều này được quy định rõ, WireTap trở thành công cụ hữu ích cho debug, metrics và audit mà không làm mờ semantics của message flow.

## Tài liệu tham khảo

- [Spring Integration — Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html) — các hook `ChannelInterceptor`, send/receive interception và completion callback.
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html) — cấu hình WireTap cục bộ, global, conditional selector và Java DSL.
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html) — semantics đồng bộ/bất đồng bộ của các channel.
- [Spring Framework — ChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html) — hợp đồng các callback interceptor.
- [Spring Integration — Logging Channel Adapter](https://docs.spring.io/spring-integration/reference/logging-channel-adapter.html) — cấu hình logging adapter, expression và full-message logging.

Các chi tiết cấu hình có thể khác theo phiên bản Spring Integration và Spring Framework. Đặc biệt, global interceptor cho channel động được hỗ trợ từ Spring Integration 5.1; hãy đối chiếu tài liệu đúng dependency của ứng dụng.

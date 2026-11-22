# Kích thước pool, hàng đợi và ảnh hưởng của tác vụ chặn trong Spring STOMP

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả luồng message qua `clientInboundChannel`, `brokerChannel` và `clientOutboundChannel`.
- Phân biệt thread pool, hàng đợi task của executor và buffer gửi theo từng WebSocket session.
- Giải thích quan hệ giữa `corePoolSize`, `maxPoolSize` và `queueCapacity` của `ThreadPoolExecutor`.
- Chọn cấu hình pool khác nhau cho công việc CPU-bound, I/O-bound và gửi message tới client chậm.
- Nhận biết cách một thao tác chặn trong `@MessageMapping` làm tăng độ trễ và tồn đọng message.
- Offload công việc chặn sang executor riêng hoặc xử lý bất đồng bộ.
- Đặt giới hạn buffer, thời gian gửi và kích thước message để kiểm soát backpressure.
- Theo dõi số liệu và kiểm thử tải để điều chỉnh cấu hình dựa trên dữ liệu thực tế.

## 1. Vì sao hiệu năng STOMP phụ thuộc vào pool và hàng đợi?

Spring STOMP không xử lý toàn bộ message trên một thread duy nhất. Message được chuyển qua các channel; một số channel dùng executor và thread pool để thực hiện công việc bất đồng bộ.

Một luồng xử lý phổ biến:

~~~text
WebSocket clients
       |
       v
clientInboundChannel
       |
       +---- /app/... ----> @MessageMapping controller
       |                         |
       |                         v
       |                    brokerChannel
       |                         |
       +---- /topic/... --------+
                                 |
                                 v
                            Message broker
                                 |
                                 v
                         clientOutboundChannel
                                 |
                                 v
                         WebSocket sessions
~~~

Ba channel chính:

| Channel | Hướng dữ liệu | Công việc |
|---|---|---|
| `clientInboundChannel` | Client → server | Nhận STOMP frame, định tuyến tới controller hoặc broker |
| `brokerChannel` | Ứng dụng server → broker | Chuyển message do controller, service hoặc `SimpMessagingTemplate` gửi tới broker |
| `clientOutboundChannel` | Broker → client | Gửi message tới WebSocket session tương ứng |

Hai channel `clientInboundChannel` và `clientOutboundChannel` mặc định được cấu hình với thread pool có kích thước bằng hai lần số processor khả dụng. Đây là giá trị khởi đầu của framework, không phải kích thước tối ưu cho mọi ứng dụng.

Hiệu năng phụ thuộc vào nhiều yếu tố cùng lúc:

- Số WebSocket session đang hoạt động.
- Số message mỗi giây và số subscriber nhận mỗi message.
- Kích thước payload và chi phí chuyển đổi JSON.
- Thời gian xử lý của các phương thức `@MessageMapping`.
- Tỷ lệ công việc CPU-bound và I/O-bound.
- Tốc độ mạng và khả năng nhận dữ liệu của client.
- Số kết nối và giới hạn của database, HTTP service hoặc broker bên ngoài.

Không có một con số thread pool duy nhất phù hợp cho mọi workload. Cần hiểu từng hàng đợi nằm ở đâu và nó đang chờ công việc gì.

## 2. Phân biệt thread pool và các loại hàng đợi

Trong ứng dụng STOMP, từ "queue" có thể nói tới nhiều thứ khác nhau:

1. **Executor task queue:** giữ task chờ được xử lý khi các worker thread đang bận. Ví dụ queue của `clientInboundChannel`.
2. **Per-session send buffer:** giữ message đang chờ gửi tới một WebSocket client cụ thể khi lần gửi trước chưa hoàn tất.
3. **Broker queue hoặc broker backlog:** trạng thái hàng đợi do message broker bên ngoài quản lý, nếu ứng dụng dùng external broker.
4. **Business queue:** hàng đợi công việc do ứng dụng tạo riêng, chẳng hạn executor cho xử lý báo cáo hoặc tác vụ nền.

Các loại hàng đợi này có giới hạn và cách đo khác nhau. Tăng `queueCapacity` của inbound executor không làm tăng buffer gửi cho client. Tăng `sendBufferSizeLimit` cũng không làm database hoặc broker xử lý nhanh hơn.

Một message có thể đi qua nhiều điểm chờ. Ví dụ:

~~~text
clientInboundChannel task queue
          |
          v
@MessageMapping handler
          |
          v
brokerChannel
          |
          v
broker processing / broker queue
          |
          v
clientOutboundChannel task queue
          |
          v
per-session send buffer
          |
          v
network and client
~~~

Nếu chỉ nhìn tổng số message đang chờ mà không xác định chúng nằm ở đâu, việc tăng pool có thể làm một đoạn luồng nhanh hơn nhưng khiến đoạn tiếp theo bị quá tải.

## 3. Ba thuộc tính quan trọng của ThreadPoolExecutor

Một `ThreadPoolExecutor` có ba thuộc tính cần hiểu:

| Thuộc tính | Ý nghĩa |
|---|---|
| `corePoolSize` | Số worker thread cơ sở mà pool duy trì |
| `maxPoolSize` | Số worker thread tối đa có thể tạo |
| `queueCapacity` | Số task có thể chờ trong queue khi các worker hiện tại bận |

Cách hoạt động khái quát:

1. Nếu số worker đang chạy nhỏ hơn `corePoolSize`, executor tạo worker mới để nhận task.
2. Khi đã đạt `corePoolSize`, task mới được đưa vào queue nếu còn chỗ.
3. Khi queue đầy, executor mới tăng số worker vượt core, tối đa đến `maxPoolSize`.
4. Nếu queue đầy và pool đã đạt `maxPoolSize`, task mới bị từ chối theo rejection policy của executor.

Điểm dễ nhầm là đặt `corePoolSize=10` và `maxPoolSize=20` không có nghĩa pool luôn tự tăng từ 10 lên 20 khi có thêm tải.

Spring mặc định dùng queue capacity rất lớn (`Integer.MAX_VALUE`) cho task executor đăng ký theo cách thông thường. Khi queue gần như không giới hạn, task mới tiếp tục được xếp hàng sau khi core thread bận; pool không cần tăng lên max. Vì vậy, `maxPoolSize` trên thực tế bị bỏ qua.

Ví dụ:

- Core = 8, Max = 32, Queue = 1000.
- Tám worker bận xử lý task.
- Task mới tiếp tục vào queue.
- Pool chỉ tạo thêm worker khi queue đã đầy.
- Nếu queue không bao giờ đầy, pool có thể chỉ chạy tám worker dù max là 32.

Một queue không giới hạn có thể che giấu tình trạng thiếu worker: request vẫn được nhận nhưng thời gian chờ ngày càng dài, bộ nhớ tăng và độ trễ cuối cùng trở nên khó kiểm soát.

## 4. Cấu hình pool cho clientInboundChannel và clientOutboundChannel

Spring cho phép cấu hình executor riêng cho hai channel:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureClientInboundChannel(
            ChannelRegistration registration) {

        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(24)
                .queueCapacity(200)
                .keepAliveSeconds(60);
    }

    @Override
    public void configureClientOutboundChannel(
            ChannelRegistration registration) {

        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(24)
                .queueCapacity(500)
                .keepAliveSeconds(60);
    }

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(
            MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Các số 8, 24, 200 và 500 chỉ là giá trị minh họa để giải thích cấu hình. Không dùng chúng như một khuyến nghị production cố định.

### 4.1 clientInboundChannel

Channel này nhận message từ client và chuyển chúng tới controller hoặc broker. Nếu handler chủ yếu tính toán CPU, số thread thường nên gần số processor khả dụng. Nếu handler thường phải chờ database, HTTP service hoặc một tài nguyên bên ngoài, pool có thể cần nhiều thread hơn để các worker khác tiếp tục xử lý message.

Tuy nhiên, tăng thread không làm database xử lý nhanh hơn. Nếu database connection pool chỉ cho phép 20 kết nối, tạo hàng trăm worker cùng chờ database có thể làm tăng context switching và contention mà không tăng throughput.

### 4.2 clientOutboundChannel

Channel này gửi message từ server tới các WebSocket client. Client có mạng nhanh thường tiêu thụ message nhanh. Client có mạng chậm hoặc băng thông thấp làm thời gian gửi kéo dài, khiến nhiều task outbound chờ xử lý.

Tăng pool có thể giúp phục vụ nhiều client chậm hơn, nhưng vẫn cần giới hạn buffer và thời gian gửi theo từng session. Một pool lớn không thể bù vô hạn cho các client nhận message chậm.

## 5. Tác vụ chặn làm nghẽn inbound pool như thế nào?

Giả sử `@MessageMapping` gọi một API bên ngoài mất 2 giây:

~~~java
@MessageMapping("/orders/status")
public OrderStatus getStatus(OrderRequest request) {
    return orderService.fetchStatusFromRemoteApi(request.orderId());
}
~~~

Nếu phương thức gọi HTTP đồng bộ, worker thread của `clientInboundChannel` phải chờ trong suốt thời gian gọi. Trong khi đó, các message khác tiếp tục tới channel và chờ trong executor queue.

Ví dụ pool có 8 worker:

- Tám message đồng thời gọi API chậm.
- Cả tám worker đều đang chờ I/O.
- Message thứ chín không có worker rảnh và phải xếp hàng.
- Khi tải tăng, queue tiếp tục dài ra.
- Độ trễ của các message mới tăng ngay cả khi bản thân chúng chỉ cần xử lý rất ít CPU.

Các tác vụ thường gây blocking:

- JDBC query chậm hoặc chờ lấy connection.
- HTTP request đồng bộ tới dịch vụ khác.
- Gọi filesystem hoặc dịch vụ lưu trữ từ xa.
- Chờ lock hoặc monitor đang bị thread khác giữ.
- `Thread.sleep()`, `Future.get()` hoặc `CompletableFuture.join()` trong handler.
- Chờ một tác vụ nền hoàn thành bằng cơ chế đồng bộ.

Một handler blocking không chỉ ảnh hưởng message của chính nó. Nó chiếm worker thread mà các message khác cần sử dụng.

## 6. Chọn kích thước pool theo loại workload

### CPU-bound

Ví dụ: tính toán, mã hóa, xử lý dữ liệu trong bộ nhớ.

- Bắt đầu với số worker gần số CPU khả dụng.
- Theo dõi CPU utilization và context switching.
- Tăng thread quá nhiều thường làm tăng tranh chấp CPU.
- Tối ưu thuật toán và giảm lượng dữ liệu xử lý thường có ích hơn tăng pool.

### I/O-bound

Ví dụ: gọi database hoặc HTTP service có thời gian chờ đáng kể.

- Có thể cần nhiều worker hơn số CPU.
- Đo thời gian chờ thực tế và tỷ lệ thread đang block.
- Giới hạn số tác vụ đồng thời theo connection pool và quota của dịch vụ bên ngoài.
- Dùng timeout cho request bên ngoài.
- Cân nhắc offload sang executor riêng hoặc API bất đồng bộ.

### Workload hỗn hợp

Một handler vừa chuyển đổi JSON, kiểm tra quyền, gọi database và phát message có nhiều giai đoạn với đặc tính khác nhau. Cần đo từng giai đoạn để tìm phần thực sự chiếm thời gian.

Không chọn pool chỉ dựa trên số WebSocket session. Một session có thể gửi nhiều message, còn một message có thể phát tới hàng trăm subscriber.

## 7. Offload công việc blocking sang executor riêng

Nếu một handler cần thực hiện I/O blocking, có thể chuyển phần đó sang một executor riêng. Khi phương thức trả về `CompletableFuture`, Spring có thể tiếp tục xử lý kết quả bất đồng bộ.

Ví dụ:

~~~java
@Configuration
public class WorkExecutorConfiguration {

    @Bean
    public ThreadPoolTaskExecutor blockingIoExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(24);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("stomp-io-");
        executor.initialize();

        return executor;
    }
}
~~~

Controller sử dụng executor riêng:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;
    private final Executor blockingIoExecutor;

    public OrderController(
            OrderService orderService,
            @Qualifier("blockingIoExecutor")
            Executor blockingIoExecutor) {
        this.orderService = orderService;
        this.blockingIoExecutor = blockingIoExecutor;
    }

    @MessageMapping("/orders/status")
    public CompletableFuture<OrderStatus> getStatus(
            OrderRequest request) {

        return CompletableFuture.supplyAsync(
                () -> orderService.fetchStatusFromRemoteApi(
                        request.orderId()),
                blockingIoExecutor);
    }
}
~~~

Khi handler trả về `CompletableFuture`, worker inbound có thể được giải phóng trong lúc tác vụ I/O tiếp tục trên executor riêng. Khi future hoàn tất, Spring xử lý giá trị trả về và gửi message theo cơ chế thông thường.

Lưu ý:

- Dùng executor có queue giới hạn để kiểm soát lượng việc chờ.
- Thiết lập timeout cho HTTP/database operation.
- Xử lý exception của future để lỗi không bị mất hoặc chỉ xuất hiện trong log.
- Đặt giới hạn concurrency phù hợp với dịch vụ đích.
- Không dùng `ForkJoinPool.commonPool()` một cách vô thức cho I/O blocking.
- Không chuyển mọi thao tác nhỏ sang executor khác nếu chi phí scheduling lớn hơn lợi ích.

Offload chỉ có ích khi executor mới được cấu hình và giám sát đúng. Nếu executor riêng cũng có queue vô hạn và tất cả worker đều chờ database, vấn đề chỉ chuyển từ inbound channel sang executor mới.

## 8. Hàng đợi giới hạn và backpressure

Khi tốc độ nhận task lớn hơn tốc độ xử lý, queue tăng. Nếu queue không giới hạn, ứng dụng có thể tiếp tục nhận task cho đến khi bộ nhớ bị tiêu thụ quá nhiều.

Queue giới hạn giúp ứng dụng có một ngưỡng tồn đọng rõ ràng:

~~~java
registration.taskExecutor()
        .corePoolSize(8)
        .maxPoolSize(24)
        .queueCapacity(200);
~~~

Khi queue đầy và pool đã đạt max, executor từ chối task theo rejection policy đang cấu hình. Ứng dụng cần quan sát và xử lý tình huống đó.

Một số nguyên tắc:

1. Chọn queue dựa trên độ trễ chấp nhận được, không chỉ dựa trên lượng RAM.
2. Task chờ càng lâu thì message càng cũ khi được xử lý.
3. Với message mang trạng thái mới nhất, có thể thiết kế cơ chế coalesce hoặc bỏ bản cập nhật cũ theo nghiệp vụ.
4. Với command nghiệp vụ quan trọng, cần trả lỗi hoặc áp dụng cơ chế retry/buffer bền vững phù hợp; không âm thầm loại bỏ.
5. Tránh để producer phát message nhanh hơn consumer trong thời gian dài mà không có giới hạn.

Backpressure không chỉ là tăng queue. Nó là cách điều chỉnh tốc độ producer, giới hạn lượng công việc đồng thời và quyết định ứng dụng sẽ làm gì khi consumer không theo kịp.

## 9. BrokerChannel và ảnh hưởng của gửi bất đồng bộ

`brokerChannel` chuyển message từ code phía server tới message broker. Mặc định, message từ ứng dụng tới broker được gửi đồng bộ. Điều này có nghĩa code gọi `SimpMessagingTemplate` có thể nhận exception nếu việc gửi không thành công.

Có thể cấu hình executor cho broker channel:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");

    registry.configureBrokerChannel()
            .taskExecutor()
            .corePoolSize(4)
            .maxPoolSize(16)
            .queueCapacity(200);
}
~~~

Khi thêm executor, việc gửi message tới broker trở thành bất đồng bộ. Code gọi template có thể kết thúc trước khi broker xử lý message, vì vậy lỗi gửi không còn nhất thiết xuất hiện ngay tại vị trí gọi.

Chỉ cấu hình executor cho broker channel khi đã hiểu thay đổi về thời điểm lỗi và có cơ chế quan sát phù hợp. Nếu nghiệp vụ cần xác nhận một message đã được chấp nhận, hãy dùng receipt hoặc cơ chế xác nhận phù hợp với broker; không coi việc phương thức gửi trả về bình thường là bằng chứng mọi subscriber đã nhận message.

## 10. Outbound buffer và client chậm

Ngay cả khi `clientOutboundChannel` có đủ worker, một WebSocket session vẫn cần xử lý gửi message theo cách an toàn. Tại một thời điểm, chỉ một thread gửi dữ liệu tới một client; các message khác có thể phải chờ trong buffer của session.

Nếu server phát message nhanh hơn client có thể nhận:

- Buffer gửi theo session tăng.
- Bộ nhớ dùng cho session đó tăng.
- Task outbound có thể phải chờ.
- Client chậm có thể ảnh hưởng throughput chung.

Spring cung cấp hai giới hạn:

- `sendTimeLimit`: giới hạn thời gian gửi.
- `sendBufferSizeLimit`: giới hạn lượng dữ liệu được buffer khi gửi tới một WebSocket session hoặc HTTP response trong SockJS fallback.

Ví dụ:

~~~java
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registration) {

    registration
            .setSendTimeLimit(15 * 1000)
            .setSendBufferSizeLimit(512 * 1024);
}
~~~

Các giá trị 15 giây và 512 KiB là ví dụ minh họa. Hãy chọn theo kích thước message, tốc độ phát, số subscriber, mạng và khả năng nhận của client.

Khi vượt giới hạn gửi hoặc buffer, Spring có thể xóa trạng thái session và thử đóng kết nối. Đây là cơ chế bảo vệ tài nguyên trước client không theo kịp, không phải cách bảo đảm message được giao thành công.

Nếu client cần dữ liệu mới nhất, cân nhắc giảm tần suất broadcast, gộp nhiều cập nhật, chỉ gửi delta hoặc để client lấy snapshot mới qua API.

## 11. Message size limit và bộ nhớ

Kích thước message ảnh hưởng trực tiếp đến bộ nhớ dùng bởi:

- Payload đang chờ trong executor queue.
- Buffer gửi theo session.
- Bộ đệm ghép nhiều WebSocket message thành một STOMP message.
- Bộ chuyển đổi JSON và object trong ứng dụng.
- Broker hoặc HTTP transport bên ngoài.

Spring cho phép giới hạn kích thước STOMP message nhận vào:

~~~java
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registration) {

    registration.setMessageSizeLimit(128 * 1024);
}
~~~

`setMessageSizeLimit` giới hạn kích thước sub-protocol message như STOMP frame có thể được ghép từ nhiều WebSocket message. Đây là giới hạn khác với `sendBufferSizeLimit`, vốn kiểm soát lượng dữ liệu đang chờ gửi tới một session.

Không tăng message size limit chỉ để làm mất lỗi payload lớn. Trước tiên, kiểm tra client có gửi payload thừa, có thể dùng phân trang, nén, tham chiếu file hoặc API tải dữ liệu riêng hay không.

## 12. Thứ tự xử lý và chi phí preserve order

Các executor có nhiều thread nên message có thể được xử lý đồng thời. Thứ tự nhận từ client hoặc thứ tự publish từ broker không nhất thiết giống thứ tự handler hoàn thành hoặc thứ tự client nhận.

Nếu ứng dụng cần giữ thứ tự trong cùng session, có thể bật:

~~~java
@Override
public void registerStompEndpoints(
        StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
            .setPreserveReceiveOrder(true);
}

@Override
public void configureMessageBroker(
        MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic");
    registry.setPreservePublishOrder(true);
}
~~~

- `setPreserveReceiveOrder(true)` giữ thứ tự xử lý message nhận từ cùng client session.
- `setPreservePublishOrder(true)` giữ thứ tự publish tới cùng client session.

Hai tùy chọn này có chi phí hiệu năng vì message trong một session được xử lý tuần tự ở giai đoạn tương ứng. Chỉ bật khi nghiệp vụ thực sự cần thứ tự.

Đối với nhiều client hoặc nhiều session, hai tùy chọn trên không tạo ra một thứ tự toàn cục cho mọi message. Nếu cần thứ tự nghiệp vụ, hãy dùng sequence number, version hoặc cơ chế đồng bộ ở tầng domain.

## 13. Theo dõi pool và queue

Khi dùng `@EnableWebSocketMessageBroker`, Spring cung cấp bean `WebSocketMessageBrokerStats` để tổng hợp số liệu hạ tầng. Theo tài liệu hiện hành, bean này mặc định ghi log ở mức INFO mỗi 30 phút và có thể export qua JMX.

Các số liệu cần theo dõi:

| Chỉ số | Dấu hiệu cần chú ý |
|---|---|
| Current / Total WebSocket sessions | Số kết nối đang hoạt động và tổng số session đã tạo |
| Abnormally closed / Connect failures | Proxy, mạng, heartbeat hoặc lỗi transport |
| Send limit exceeded | Client nhận quá chậm hoặc buffer/send timeout quá thấp |
| Client inbound channel | Task queue tăng cho thấy ứng dụng xử lý message đầu vào không kịp |
| Client outbound channel | Task queue tăng có thể cho thấy client chậm hoặc mạng yếu |
| STOMP broker relay TCP connections | Số kết nối tới broker ngoài so với số WebSocket session |
| SockJS task scheduler | Tình trạng scheduler gửi heartbeat cho HTTP fallback |

Kết hợp số liệu Spring với metrics của hệ thống:

- Executor active thread, queue depth, completed task và rejected task.
- CPU, heap, garbage collection và thread dump.
- Database connection pool active/pending và query latency.
- HTTP client connection pool và timeout.
- Broker queue depth, publish/consume rate và consumer lag.
- WebSocket send latency, disconnect rate và kích thước payload.

Nếu inbound queue tăng, kiểm tra thời gian handler, truy vấn database và các lời gọi HTTP. Nếu outbound queue tăng, kiểm tra slow client, fan-out, kích thước message và send buffer.

## 14. Quy trình tuning dựa trên số liệu

Một quy trình tuning thực tế:

1. Ghi nhận baseline: số session, message rate, payload size, p95/p99 latency, CPU, heap và queue depth.
2. Tách workload CPU-bound và I/O-bound.
3. Đo thời gian xử lý trung bình và phân vị cao của handler.
4. Kiểm tra database/HTTP pool trước khi tăng inbound threads.
5. Cấu hình core, max và bounded queue cho inbound/outbound riêng.
6. Đặt send timeout và send buffer limit theo khả năng client.
7. Tăng dần tải để xác định điểm queue bắt đầu tăng liên tục.
8. Kiểm tra behavior khi queue đầy và khi client chậm.
9. So sánh throughput, p95/p99 latency, rejection và memory trước/sau mỗi thay đổi.
10. Giữ cấu hình đơn giản nhất đáp ứng tải mục tiêu và kiểm thử lại khi message size hoặc fan-out thay đổi.

Không thay đổi đồng thời tất cả các thông số. Nếu vừa tăng max threads, queue capacity, send buffer và message size limit, sẽ khó biết thay đổi nào tạo ra tác động.

## 15. Lỗi cấu hình thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ tăng `maxPoolSize` nhưng giữ queue không giới hạn | Pool vẫn chỉ chạy gần core size | Đặt queue capacity hữu hạn nếu cần pool tăng vượt core |
| Tăng inbound pool quá lớn | Tăng contention và gây áp lực lên database/HTTP service | Đo tỷ lệ blocking và giới hạn theo tài nguyên downstream |
| Dùng một pool cho mọi loại việc | Tác vụ chậm có thể chiếm worker của message processing | Tách executor cho I/O blocking hoặc background work |
| Dùng queue không giới hạn | Backlog và memory tăng khi producer nhanh hơn consumer | Đặt bounded queue và chính sách xử lý khi queue đầy |
| Chỉ tăng outbound pool | Không giải quyết được client chậm và per-session buffer tăng | Kết hợp send timeout và send buffer limit |
| Tăng send buffer vô hạn | Một client chậm có thể giữ nhiều dữ liệu trong heap | Đặt giới hạn và giảm fan-out/tần suất message |
| Bật preserve order mặc định | Giảm mức song song dù nghiệp vụ không cần | Chỉ bật cho luồng thực sự cần thứ tự |
| Bỏ qua brokerChannel | Gửi bất đồng bộ có thể làm thay đổi thời điểm nhận lỗi | Hiểu rõ synchronous/asynchronous semantics trước khi cấu hình |
| Chỉ đo CPU | Bỏ qua queue backlog và downstream wait | Theo dõi executor, database, broker, outbound buffer và latency |

## 16. Bài tập tự kiểm tra

### Bài 1

Pool có `corePoolSize=8`, `maxPoolSize=32`, `queueCapacity=Integer.MAX_VALUE`. Khi tám worker đều bận, task mới thường được xử lý như thế nào?

**Đáp án:** Task mới được đưa vào queue không giới hạn. Vì queue vẫn nhận task, executor không cần tăng worker vượt core; `maxPoolSize` trên thực tế không phát huy tác dụng.

### Bài 2

Một handler gọi database đồng bộ và thường chờ 1 giây. Vì sao inbound queue có thể tăng dù CPU không cao?

**Đáp án:** Worker inbound đang bị giữ trong lúc chờ I/O. Khi nhiều worker cùng chờ database, message mới phải đợi trong queue dù CPU vẫn còn thời gian rảnh.

### Bài 3

Tăng `sendBufferSizeLimit` có làm client mạng chậm nhận message nhanh hơn không?

**Đáp án:** Không. Nó chỉ cho phép giữ nhiều dữ liệu đang chờ gửi hơn trước khi vượt giới hạn. Nếu tốc độ phát luôn cao hơn tốc độ nhận, buffer sẽ tiếp tục tăng và độ trễ vẫn tăng.

### Bài 4

Khi nào nên dùng `setPreservePublishOrder(true)`?

**Đáp án:** Khi ứng dụng cần giữ thứ tự publish trong cùng client session. Tùy chọn này có chi phí hiệu năng nên chỉ bật khi nghiệp vụ cần.

### Bài 5

`brokerChannel` mặc định gửi đồng bộ có ý nghĩa gì với code gọi `SimpMessagingTemplate`?

**Đáp án:** Code gọi template có thể nhận exception ngay khi việc gửi tới broker thất bại. Nếu cấu hình executor cho brokerChannel, thao tác gửi trở thành bất đồng bộ và thời điểm nhận lỗi thay đổi.

## Tài liệu tham khảo

- [Spring Framework — Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — Monitoring](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html)
- [Spring Framework — Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)
- [Spring Framework Javadoc — TaskExecutorRegistration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/TaskExecutorRegistration.html)
- [Spring Framework Javadoc — MessageBrokerRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [Spring Framework Javadoc — WebSocketTransportRegistration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketTransportRegistration.html)

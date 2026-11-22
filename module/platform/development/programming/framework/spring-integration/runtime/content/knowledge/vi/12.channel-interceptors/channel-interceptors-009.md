# Giới hạn chi phí interceptor trên đường nóng

`ChannelInterceptor` là điểm mở rộng hữu ích để quan sát hoặc điều chỉnh message khi message đi qua channel. Tuy nhiên, interceptor nằm ngay trên đường gửi/nhận của channel. Nếu một channel xử lý hàng nghìn hoặc hàng triệu message mỗi phút, mọi thao tác trong interceptor đều được nhân lên theo lưu lượng đó. Một lần ghi log, serialize payload hoặc gọi dịch vụ từ xa có thể biến interceptor nhỏ thành bottleneck của toàn bộ flow.

Thiết kế interceptor cho đường nóng cần bắt đầu từ câu hỏi: ta thực sự cần quan sát hoặc thay đổi điều gì tại ranh giới channel? Chỉ đăng ký ở phạm vi cần thiết, chọn callback tối thiểu, tránh I/O đồng bộ và đo chi phí bằng tải thực tế.

## 1. ChannelInterceptor chạy ở ranh giới nào?

`ChannelInterceptor` thuộc Spring Messaging và được `AbstractMessageChannel` sử dụng để can thiệp vào quá trình gửi/nhận message. Một interceptor có thể quan sát hoặc thay đổi message trước khi gửi, sau khi gửi, hoặc quanh thao tác receive của pollable channel.

Các callback chính:

| Callback | Thời điểm | Dùng khi |
|---|---|---|
| `preSend` | Trước khi channel thực hiện send | Kiểm tra metadata, bổ sung header cần thiết hoặc từ chối message có chủ đích |
| `postSend` | Sau khi channel thực hiện send | Ghi nhận kết quả send thành công hay thất bại qua cờ `sent` |
| `afterSendCompletion` | Khi quá trình send kết thúc, kể cả có exception | Cleanup hoặc ghi nhận lỗi sau send |
| `preReceive` | Trước khi pollable channel nhận message | Quyết định có thực hiện receive hay không |
| `postReceive` | Sau thao tác receive | Quan sát message vừa nhận; có thể trả message đã thay đổi |
| `afterReceiveCompletion` | Khi receive hoàn tất | Cleanup hoặc ghi nhận exception của receive |

Không phải mọi callback đều được gọi trên mọi loại channel. `preReceive`, `postReceive` và `afterReceiveCompletion` có ý nghĩa với channel hỗ trợ receive, như `QueueChannel`. Với `DirectChannel` hoặc `ExecutorChannel`, trọng tâm thường là send path.

Interceptor có thể được gọi cho mỗi message. Nếu có N interceptor trên một channel, một lần gửi có thể đi qua nhiều callback của từng interceptor. Vì vậy, số lượng interceptor và chi phí từng callback đều ảnh hưởng tới throughput.

## 2. Phân biệt chi phí channel với chi phí xử lý handler

Một interceptor đo thời gian quanh `send()` không nhất thiết đo thời gian xử lý nghiệp vụ.

| Channel | Phạm vi thường được bao quanh bởi send interceptor |
|---|---|
| `DirectChannel` | Lời gọi dispatch đồng bộ, thường bao gồm thời gian subscriber/handler thực thi |
| `ExecutorChannel` | Việc dispatch hoặc submit task tới executor; handler có thể chạy sau đó trên worker thread |
| `QueueChannel` | Việc enqueue message vào queue; consumer nhận và xử lý ở thời điểm khác |
| `PublishSubscribeChannel` có executor | Việc dispatch tới executor/subscriber theo cấu hình; không đồng nghĩa mọi nhánh đã xử lý xong |

Ví dụ, `postSend` trên `ExecutorChannel` có thể được gọi ngay sau khi task được chấp nhận bởi executor. Nếu dùng thời lượng này để báo cáo “handler processing time”, metric sẽ thấp hơn thời gian xử lý thật và dẫn tới kết luận sai.

Muốn đo thời gian handler, dùng instrumentation ở endpoint/handler, `Advice` quanh phương thức xử lý hoặc Observation phù hợp. Dùng `ChannelInterceptor` để đo thời gian và kết quả của ranh giới channel: send mất bao lâu, queue nhận message thành công không, receive có trả message hay không.

## 3. Giới hạn phạm vi interceptor

Spring Integration hỗ trợ đăng ký interceptor trực tiếp trên một channel hoặc đăng ký global interceptor theo pattern tên channel. Global interceptor tiện cho chính sách chung, nhưng wildcard quá rộng có thể khiến mọi channel trong application context đều chịu chi phí callback.

Ví dụ chỉ áp dụng interceptor cho nhóm channel đơn hàng:

~~~java
@Configuration
@EnableIntegration
public class ChannelObservabilityConfiguration {

    @Bean
    @GlobalChannelInterceptor(patterns = "orders*")
    ChannelInterceptor ordersChannelMetrics(MeterRegistry registry) {
        Counter accepted = Counter.builder("si.channel.send.accepted")
                .tag("channel_group", "orders")
                .register(registry);

        Counter rejected = Counter.builder("si.channel.send.rejected")
                .tag("channel_group", "orders")
                .register(registry);

        Counter failed = Counter.builder("si.channel.send.failed")
                .tag("channel_group", "orders")
                .register(registry);

        return new ChannelInterceptor() {

            @Override
            public void postSend(Message<?> message,
                                MessageChannel channel,
                                boolean sent) {
                if (sent) {
                    accepted.increment();
                }
                else {
                    rejected.increment();
                }
            }

            @Override
            public void afterSendCompletion(Message<?> message,
                                            MessageChannel channel,
                                            boolean sent,
                                            Exception ex) {
                if (ex != null) {
                    failed.increment();
                }
            }
        };
    }
}
~~~

Ví dụ trên minh họa metric có cardinality thấp cho một nhóm channel cố định. `postSend` phân biệt send được channel chấp nhận với send trả về `false`; `afterSendCompletion` ghi nhận exception nếu có. Các counter không gắn message ID, customer ID hoặc tenant ID làm tag.

Nếu chỉ cần quan sát một channel, đăng ký interceptor cục bộ trên channel đó sẽ có phạm vi nhỏ hơn. Chỉ dùng `@GlobalChannelInterceptor` khi muốn áp dụng chính sách cho một nhóm channel có tên rõ ràng. Pattern nên dựa trên quy ước tên ổn định, chẳng hạn `orders*`, `payments*` hoặc `audit*`.

Đừng đăng ký global interceptor với pattern bao phủ mọi channel nếu tác vụ chỉ cần theo dõi một nhánh. Các channel nội bộ, channel control, error channel hoặc channel tốc độ cao không nhất thiết cần cùng một mức quan sát.

## 4. Chọn callback tối thiểu

Mỗi callback bổ sung đều tăng số lần gọi method trên đường nóng. Hãy chọn đúng callback theo nhu cầu:

- Chỉ đếm send được chấp nhận: dùng `postSend` và kiểm tra `sent`.
- Cần ghi nhận exception khi send: dùng `afterSendCompletion`.
- Cần kiểm tra hoặc bổ sung metadata trước send: dùng `preSend`.
- Cần quan sát receive của pollable channel: dùng `postReceive` hoặc callback receive tương ứng.
- Không cần quan sát receive thì không override các callback receive.

`preSend` có thể trả `null` để ngăn message được gửi. Đây là một hành vi điều khiển, không chỉ là callback quan sát. Nếu mục tiêu là lọc message theo điều kiện nghiệp vụ, nên dùng `Filter` endpoint để logic đó hiển thị rõ trong flow, có discard channel và metric riêng. Tránh dùng interceptor như một filter nghiệp vụ ẩn.

Không tạo `MessageBuilder`, copy payload hoặc chỉnh header nếu không có yêu cầu cụ thể. Message trong Spring Messaging có tính bất biến; tạo message mới và copy header đều có chi phí allocation. Nếu cần thêm metadata, chỉ làm một lần tại điểm tạo message hoặc tại endpoint chuyên trách thay vì lặp lại ở mọi channel.

## 5. Tránh I/O và công việc nặng trong interceptor

Các thao tác sau thường không phù hợp với đường nóng:

| Thao tác | Vì sao tốn kém | Cách thay thế |
|---|---|---|
| Gọi HTTP hoặc database | Thêm network latency, timeout và failure vào send path | Đưa thành endpoint xử lý riêng hoặc phát event bất đồng bộ |
| Serialize toàn bộ payload để log | CPU, allocation và có thể lộ dữ liệu nhạy cảm | Ghi message ID, type, kích thước hoặc trường metadata đã whitelist |
| Ghi một dòng log cho mọi message | Formatting, appender và I/O có thể chặn thread | Dùng metric counter; log chi tiết theo sampling hoặc khi có lỗi |
| Regex/JSON parsing phức tạp | CPU và allocation lặp lại cho từng message | Parse một lần ở ingress hoặc dùng metadata đã chuẩn hóa |
| Chờ lock hoặc synchronized toàn cục | Các producer cạnh tranh cùng lock, giảm song song | Tránh shared mutable state; dùng metric thread-safe hoặc state partitioned |
| Tạo nhiều object tạm | Tăng allocation rate và GC pressure | Giữ callback ngắn, tái sử dụng cấu trúc an toàn khi thực sự cần |

Interceptor nên tránh blocking call. Một thao tác remote kéo dài 50 ms trên channel có 2.000 message/giây có thể giữ nhiều thread trong trạng thái chờ và làm backlog tăng nhanh. Chuyển công việc đó thành endpoint riêng giúp có thể giới hạn concurrency, timeout, retry và quan sát độc lập.

Không bắt exception rồi bỏ qua để giữ throughput. Làm vậy có thể khiến message mất metadata hoặc metric không nhất quán mà không ai biết. Nếu interceptor không thể thực hiện chức năng bắt buộc, hãy để lỗi được biểu diễn rõ ràng theo contract của flow hoặc dùng fallback có chủ đích.

## 6. Metric có cardinality thấp

Metric nên trả lời câu hỏi vận hành mà không tạo hàng triệu time series. Các giá trị như message ID, order ID, email, tenant ID tự do hoặc URL có path động không nên dùng làm tag metric.

Nên dùng tag có tập giá trị nhỏ và ổn định:

- `channel_group`: `orders`, `payments`, `notifications`.
- `channel_type`: `direct`, `queue`, `executor`, `publish_subscribe`.
- `result`: `accepted`, `rejected`, `failed`.
- `environment`: `dev`, `staging`, `prod` nếu hệ thống đã quản lý tag này ở cấp registry.

Tên channel cụ thể cũng chỉ nên dùng làm tag khi danh sách channel hữu hạn, được kiểm soát trong cấu hình và không chứa dữ liệu runtime. Nếu mỗi tenant tạo channel động, tag theo tên channel có thể làm cardinality tăng không giới hạn. Trong trường hợp đó, tổng hợp theo nhóm hoặc theo loại channel.

Counter phù hợp để đếm số lần gửi/nhận/kết quả. Timer phù hợp để đo thời lượng một thao tác. Gauge phù hợp cho trạng thái hiện tại như queue depth. Không dùng metric để thay thế log chi tiết của một message; dùng message ID/Correlation ID trong log hoặc trace khi cần truy vấn một giao dịch cụ thể.

## 7. Logging có chọn lọc

Nếu cần log metadata, giữ nội dung ngắn và kiểm tra log level trước khi format chuỗi. Ví dụ:

~~~java
@Override
public Message<?> preSend(Message<?> message, MessageChannel channel) {
    if (log.isTraceEnabled()) {
        log.trace("channel={}, messageId={}",
                channel, message.getHeaders().getId());
    }
    return message;
}
~~~

Không ghi toàn bộ payload hoặc tất cả header. Header có thể chứa token, thông tin cá nhân, object lớn hoặc metadata nội bộ. Chỉ log các trường đã được whitelist và tuân thủ chính sách che dữ liệu.

Trong production, có thể bật trace log trong thời gian ngắn để điều tra một flow cụ thể, nhưng nên giới hạn package/channel và tắt sau khi hoàn tất. Nếu cần sampling, chọn tỷ lệ hoặc điều kiện lấy mẫu rõ ràng; đừng dùng random hoặc tính toán đắt tiền cho mọi message nếu metric đơn giản đã đủ.

## 8. Tránh giữ state theo message trong interceptor

Không nên dùng một `HashMap` toàn cục để lưu message ID và timestamp trong `preSend`, rồi chờ `postSend` xóa. Cách này có thể tạo race condition, memory leak khi callback không chạy như dự kiến, và tăng chi phí đồng bộ.

Đặc biệt, interceptor không nên giả định một send luôn tương ứng một lần xử lý handler. Với `ExecutorChannel`, send callback kết thúc sau khi dispatch task; handler hoàn tất sau đó trên worker. Nếu muốn đo thời gian end-to-end của handler, đo tại handler/observation scope chứ không ghép hai callback channel thành một lifecycle xử lý nghiệp vụ.

Nếu cần state tạm trong một lần send đồng bộ, phải xem xét nested send, nhiều thread và mọi đường exception. Thông thường, metric có sẵn hoặc instrumentation tại endpoint sẽ đơn giản và an toàn hơn việc tự quản lý map theo message.

## 9. Interceptor không thay thế endpoint nghiệp vụ

Một số chức năng không nên đặt trong interceptor:

| Nhu cầu | Cơ chế phù hợp hơn |
|---|---|
| Lọc message theo điều kiện nghiệp vụ | `Filter` endpoint |
| Chuyển message sang channel khác theo header | Router endpoint |
| Chuyển đổi payload | Transformer endpoint |
| Gọi dịch vụ hoặc ghi database | Service Activator |
| Retry thao tác có side effect | Retry advice quanh handler/service với idempotency phù hợp |
| Đo thời gian xử lý nghiệp vụ | Handler advice, Micrometer Observation hoặc instrumentation tại service |
| Audit event bền vững | Audit/outbox service hoặc kho lưu trữ riêng |

Interceptor phù hợp với concern cắt ngang ở ranh giới channel như kiểm tra metadata kỹ thuật, metric send/receive, trace/log metadata hoặc kiểm soát truy cập đơn giản. Khi logic cần cấu hình riêng, retry, transaction hoặc error flow, endpoint chuyên trách giúp flow dễ đọc và vận hành hơn.

## 10. Đo chi phí interceptor

Không nên kết luận interceptor nhẹ chỉ vì callback có vài dòng code. Hãy đo trên đường đi thật với kích thước message và concurrency tương tự production.

Quy trình đo:

1. **Baseline:** chạy flow với cùng channel và handler nhưng chưa gắn interceptor; ghi throughput, p50/p95/p99 latency, CPU, allocation rate và GC.
2. **Một interceptor tối thiểu:** chỉ thêm counter hoặc callback cần thiết; đo lại cùng tải.
3. **Tăng dần:** thêm từng chức năng một như logging, header inspection hoặc timer; không bật tất cả cùng lúc.
4. **So sánh channel:** đo riêng `DirectChannel`, `ExecutorChannel` và `QueueChannel` vì send path có phạm vi khác nhau.
5. **Kiểm tra tải cao:** tăng concurrency và message size, quan sát lock contention, executor queue và rejected task.
6. **Đánh giá tail latency:** một interceptor có thể chỉ tăng trung bình vài microsecond nhưng làm p99 tăng mạnh khi log appender hoặc remote call bị chặn.

Với benchmark vi mô, có thể dùng JMH để đo callback hoặc xử lý metadata riêng lẻ. Với đánh giá end-to-end, dùng load test có warm-up, đủ thời gian chạy, cùng cấu hình JVM và cùng downstream. Không dùng thời gian chạy một lần trong unit test làm kết luận hiệu năng production.

## 11. Chẩn đoán interceptor trở thành bottleneck

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Throughput giảm rõ sau khi bật interceptor | Callback chạy trên mọi message hoặc quá nhiều interceptor | Tắt từng interceptor, đo lại và thu hẹp pattern |
| p99 tăng nhưng CPU không cao | Blocking log appender, network hoặc lock | Thread dump, profiler và thời gian chờ I/O/lock |
| CPU và allocation tăng | Serialize payload, regex, object creation hoặc format log | Allocation profiling và loại bỏ xử lý lặp |
| Metric backend tăng số time series | Tag chứa ID/tenant/channel động | Kiểm tra cardinality và chuyển sang tag nhóm cố định |
| `ExecutorChannel` có send nhanh nhưng handler chậm | Interceptor chỉ đo dispatch | Đo thêm ở handler và executor queue |
| Message bị từ chối ngoài ý muốn | `preSend` trả `null` hoặc callback sửa message không đúng | Kiểm tra interceptor chain và log kết quả send |
| Log có payload nhạy cảm | Interceptor dump toàn bộ message | Whitelist metadata và che dữ liệu |

Khi profiling, xác định thời gian nằm trong `preSend`, `postSend`, `afterSendCompletion`, dispatcher hay handler. Nếu chỉ xem tổng latency của producer, khó phân biệt chi phí interceptor với thời gian downstream.

## 12. Checklist cho đường nóng

- [ ] Chỉ đăng ký interceptor ở channel cần quan sát hoặc kiểm soát.
- [ ] Dùng global interceptor với pattern hẹp và tên channel ổn định.
- [ ] Chọn callback tối thiểu; không override callback chỉ để trống.
- [ ] Giữ callback ngắn, không blocking và không gọi database/HTTP.
- [ ] Không serialize hoặc log toàn bộ payload/header.
- [ ] Không tạo object hoặc copy message nếu không cần.
- [ ] Không dùng message ID, customer ID hoặc tenant tự do làm metric tag.
- [ ] Không giữ state toàn cục theo message trong interceptor.
- [ ] Phân biệt send/dispatch latency với handler processing latency.
- [ ] Dùng endpoint cho filter, router, transformer và nghiệp vụ.
- [ ] Đo baseline và tail latency trước/sau khi thêm interceptor.
- [ ] Kiểm tra exception, `preSend` trả `null` và cleanup trên mọi đường kết thúc.

Interceptor tốt trên đường nóng thường làm rất ít việc: đọc một vài metadata cần thiết, cập nhật metric có cardinality thấp hoặc gắn thông tin kỹ thuật nhỏ. Phạm vi hẹp và callback ngắn giữ cho channel tập trung vào việc chuyển message, trong khi logging chi tiết, I/O và xử lý nghiệp vụ được thực hiện ở nơi có thể giới hạn và quan sát riêng.

## Tài liệu tham khảo

- [Spring Framework API: ChannelInterceptor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Integration Reference: Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html)
- [Spring Integration API: GlobalChannelInterceptor](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/config/GlobalChannelInterceptor.html)
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/)

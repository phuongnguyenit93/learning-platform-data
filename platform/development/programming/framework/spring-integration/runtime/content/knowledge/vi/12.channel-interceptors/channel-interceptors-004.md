# Logging, metrics và tracing bằng interceptor

Trong Spring Integration, channel là ranh giới chuyển giao message giữa các endpoint. `ChannelInterceptor` cho phép quan sát hoặc điều chỉnh message ngay tại ranh giới đó. Đây là vị trí hữu ích để ghi nhận message được gửi hay bị từ chối, bổ sung ngữ cảnh cho log và thu thập số liệu vận hành.

Logging, metrics và tracing trả lời ba câu hỏi khác nhau: log ghi lại sự kiện cụ thể; metric tổng hợp xu hướng và tình trạng hệ thống; trace nối các bước xử lý của một request qua nhiều thread hoặc service. Interceptor có thể hỗ trợ cả ba, nhưng cần chọn đúng callback và hiểu rõ phạm vi mà callback quan sát được.

## 1. ChannelInterceptor quan sát điều gì?

`ChannelInterceptor` thuộc Spring Messaging và được channel gọi quanh thao tác send/receive. Các callback chính gồm:

| Callback | Thời điểm | Thông tin có thể quan sát |
|---|---|---|
| `preSend` | Trước khi channel gửi message | Message đầu vào, channel và khả năng từ chối hoặc thay message |
| `postSend` | Sau khi channel thực hiện send | Kết quả send qua cờ `sent` |
| `afterSendCompletion` | Khi quá trình send kết thúc | Kết quả cuối cùng và exception nếu có |
| `preReceive` | Trước khi pollable channel nhận message | Có cho phép thực hiện receive hay không |
| `postReceive` | Sau khi pollable channel nhận message | Message vừa lấy khỏi channel |
| `afterReceiveCompletion` | Khi quá trình receive kết thúc | Exception và trạng thái kết thúc receive |

Không phải mọi channel đều hỗ trợ receive. Các callback receive chủ yếu có ý nghĩa với `PollableChannel`, chẳng hạn `QueueChannel`. `DirectChannel` và `ExecutorChannel` thường được quan sát qua send path.

Điểm cần nhớ là interceptor quan sát hoạt động của channel. Nó không tự động bao quanh toàn bộ nghiệp vụ của mọi endpoint phía sau channel. Ví dụ, với `QueueChannel`, `postSend` thường ghi nhận việc enqueue; consumer có thể xử lý message sau đó. Với `ExecutorChannel`, send callback có thể kết thúc khi task đã được dispatch, trong khi handler vẫn đang chạy trên worker thread.

## 2. Chọn đúng phạm vi đăng ký

Có thể đăng ký interceptor trực tiếp trên một channel hoặc dùng `@GlobalChannelInterceptor` để áp dụng cho các channel khớp pattern tên. Nên dùng phạm vi nhỏ nhất đáp ứng nhu cầu quan sát.

Ví dụ đăng ký interceptor cho nhóm channel đơn hàng:

~~~java
@Configuration
@EnableIntegration
public class ChannelObservabilityConfiguration {

    @Bean
    @GlobalChannelInterceptor(patterns = "orders*")
    ChannelInterceptor ordersLoggingInterceptor() {
        return new ChannelInterceptor() {

            private final Logger log =
                    LoggerFactory.getLogger("integration.channel.orders");

            @Override
            public Message<?> preSend(Message<?> message,
                                      MessageChannel channel) {
                if (log.isDebugEnabled()) {
                    log.debug("send channel={} messageId={} correlationId={}",
                            channel,
                            message.getHeaders().getId(),
                            message.getHeaders().get("correlationId"));
                }
                return message;
            }

            @Override
            public void afterSendCompletion(Message<?> message,
                                            MessageChannel channel,
                                            boolean sent,
                                            Exception ex) {
                if (ex != null) {
                    log.warn("send failed channel={} messageId={}",
                            channel, message.getHeaders().getId(), ex);
                }
            }
        };
    }
}
~~~

Pattern `orders*` giới hạn interceptor vào những channel có tên bắt đầu bằng `orders`. Quy ước tên channel ổn định giúp log và metric dễ đối chiếu. Tránh pattern quá rộng nếu một số channel nội bộ, control hoặc tốc độ cao không cần cùng mức quan sát.

Nếu chỉ cần theo dõi một channel, đăng ký cục bộ sẽ dễ kiểm soát hơn. Global interceptor phù hợp khi có một chính sách chung cho một nhóm channel có tên rõ ràng.

## 3. Logging: ghi sự kiện có thể truy vấn

Log nên cho biết message đã đi qua channel nào, kết quả send ra sao và có lỗi gì. Các trường thường hữu ích gồm:

- Tên hoặc nhóm channel.
- Message ID để tìm một message cụ thể.
- Correlation ID để gom các message thuộc cùng nghiệp vụ.
- Trace ID/span ID nếu tracing đã được cấu hình.
- Kết quả send và exception type khi thất bại.

Ví dụ `preSend` ghi metadata và `afterSendCompletion` ghi lỗi:

~~~java
public class ChannelLoggingInterceptor implements ChannelInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(ChannelLoggingInterceptor.class);

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        if (log.isTraceEnabled()) {
            log.trace("channel={} messageId={} correlationId={}",
                    channel,
                    message.getHeaders().getId(),
                    message.getHeaders().get("correlationId"));
        }
        return message;
    }

    @Override
    public void afterSendCompletion(Message<?> message,
                                    MessageChannel channel,
                                    boolean sent,
                                    Exception ex) {
        if (ex != null) {
            log.warn("channel send failed: channel={} messageId={}",
                    channel, message.getHeaders().getId(), ex);
        }
        else if (!sent && log.isDebugEnabled()) {
            log.debug("channel did not accept message: channel={} messageId={}",
                    channel, message.getHeaders().getId());
        }
    }
}
~~~

Không ghi toàn bộ payload hoặc tất cả header. Payload có thể chứa dữ liệu cá nhân, token, thông tin thanh toán hoặc object lớn. Chỉ ghi các trường đã được whitelist và tuân thủ quy tắc che dữ liệu.

Log mỗi message ở mức INFO có thể tạo lượng I/O rất lớn. Thường nên dùng DEBUG/TRACE cho log chi tiết, còn INFO/WARN dành cho sự kiện vận hành có ý nghĩa. Nếu cần sampling, hãy chọn tỷ lệ hoặc điều kiện rõ ràng và bảo đảm lỗi nghiêm trọng vẫn được ghi nhận.

### Gắn MDC với message

MDC giúp đưa correlation ID hoặc trace ID vào mọi dòng log trên thread hiện tại. Có thể lấy correlation ID từ message header rồi đặt vào MDC trong phạm vi xử lý, sau đó khôi phục hoặc xóa trong `finally`.

Không giả định MDC tự đi qua `ExecutorChannel`, poller hoặc queue. Các ranh giới thread cần cơ chế context propagation phù hợp như `TaskDecorator` hoặc Micrometer Context Propagation. Tránh để MDC của message trước còn sót trên worker thread được tái sử dụng.

## 4. Metrics: đo số lượng và xu hướng

Metrics phù hợp để trả lời câu hỏi như:

- Có bao nhiêu message được channel chấp nhận?
- Bao nhiêu lần send trả về `false`?
- Có bao nhiêu exception xảy ra trong send path?
- Throughput hoặc latency của nhóm channel thay đổi thế nào theo thời gian?
- Queue có tăng backlog hay không?

Ví dụ dùng Micrometer `Counter` để đếm ba kết quả gửi:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "orders*")
ChannelInterceptor ordersChannelMetrics(MeterRegistry registry) {
    Counter accepted = registry.counter(
            "si.channel.send", "channel_group", "orders", "outcome", "accepted");
    Counter rejected = registry.counter(
            "si.channel.send", "channel_group", "orders", "outcome", "rejected");
    Counter failed = registry.counter(
            "si.channel.send", "channel_group", "orders", "outcome", "failed");

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
~~~

Trong ví dụ, `postSend` phân biệt message được chấp nhận với send trả về `false`; `afterSendCompletion` đếm exception. Đây là ba outcome riêng, không phải số message xử lý thành công cuối cùng. `accepted` chỉ có nghĩa channel đã chấp nhận/chuyển giao message theo semantics của channel.

### Giữ cardinality thấp

Tag metric phải có tập giá trị nhỏ và ổn định. Có thể dùng `channel_group`, `channel_type` hoặc `outcome`. Không dùng message ID, order ID, email, customer ID hoặc tenant ID tự do làm tag; mỗi giá trị mới có thể tạo một time series mới và làm metric backend quá tải.

Nếu channel được tạo động theo tenant, không gắn tên channel động vào metric. Hãy tổng hợp theo nhóm hoặc loại channel; dùng log/trace để tìm một message hoặc tenant cụ thể.

### Đo thời gian ở đúng tầng

Đừng dùng thời gian quanh send callback như thời gian xử lý handler cho mọi channel:

| Channel | Điều mà send instrumentation thường phản ánh |
|---|---|
| `DirectChannel` | Dispatch đồng bộ; có thể bao gồm thời gian subscriber/handler |
| `QueueChannel` | Thời gian enqueue message vào queue |
| `ExecutorChannel` | Thời gian dispatch/submit task; handler có thể chạy sau đó |
| `PublishSubscribeChannel` có executor | Thời gian dispatch theo executor và cấu hình subscriber, không nhất thiết là thời gian hoàn tất mọi nhánh |

Muốn đo thời gian nghiệp vụ, hãy instrument endpoint/handler bằng Micrometer Observation, timer hoặc advice phù hợp. Trước khi tự tạo timer trong interceptor, hãy xem xét lifecycle và concurrency của callback; tránh lưu `Timer.Sample` theo message trong map toàn cục chỉ để ghép `preSend` với completion vì điều đó tăng allocation, đồng bộ và nguy cơ rò rỉ state.

## 5. Tracing: nối các bước xử lý

Distributed tracing giúp nối một request qua nhiều endpoint, thread và service bằng trace ID cùng các span. Interceptor có thể hỗ trợ tracing bằng cách ghi nhận trace/span ID đang hoạt động trong log hoặc bổ sung metadata kỹ thuật khi thực sự cần.

Nếu ứng dụng dùng Micrometer Tracing, có thể đọc span hiện tại từ `Tracer`:

~~~java
public class TraceLoggingInterceptor implements ChannelInterceptor {

    private final Tracer tracer;
    private final Logger log =
            LoggerFactory.getLogger(TraceLoggingInterceptor.class);

    public TraceLoggingInterceptor(Tracer tracer) {
        this.tracer = tracer;
    }

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        Span span = tracer.currentSpan();
        if (span != null && log.isDebugEnabled()) {
            log.debug("channel={} messageId={} traceId={} spanId={}",
                    channel,
                    message.getHeaders().getId(),
                    span.context().traceId(),
                    span.context().spanId());
        }
        return message;
    }
}
~~~

Nếu không có span hiện tại, interceptor không ghi trace ID. Đây là trạng thái hợp lệ khi message chưa nằm trong một trace hoặc tracing chưa được bật.

Không nên tự tạo một span mới ở mọi callback interceptor chỉ để có thêm log. `preSend` và `afterSendCompletion` mô tả ranh giới send của channel; với `ExecutorChannel` hoặc `QueueChannel`, chúng không bao quanh toàn bộ xử lý bất đồng bộ. Hãy ưu tiên Observation/tracing instrumentation ở endpoint và dùng context propagation để nối span qua executor. Khi đi qua HTTP hoặc broker, dùng propagator chuẩn như W3C Trace Context và cấu hình header mapper tương ứng.

Correlation ID nghiệp vụ không thay thế Trace ID. Một đơn hàng có thể giữ cùng Correlation ID qua nhiều lần thử hoặc nhiều request, trong khi mỗi lần thực thi có thể tạo một trace riêng.

## 6. Phân biệt logging, metrics và tracing

| Khía cạnh | Logging | Metrics | Tracing |
|---|---|---|---|
| Mục tiêu | Ghi lại sự kiện cụ thể | Đo xu hướng và tình trạng tổng thể | Theo dõi đường đi của một request/message |
| Dữ liệu | Message ID, channel, lỗi, metadata đã whitelist | Counter, timer, gauge và tag ít giá trị | Trace ID, span ID, quan hệ cha-con và thời lượng |
| Truy vấn | Tìm một sự kiện hoặc message | Dashboard, alert và so sánh theo thời gian | Mở trace để thấy span chậm hoặc lỗi |
| Nơi phù hợp | Interceptor và endpoint | Interceptor cho channel outcome; instrumentation cho endpoint/queue | Observation/tracing instrumentation và propagator |

Không dùng metric để lưu từng message, không dùng log payload làm tracing và không dùng một trace ID tự tạo thay cho distributed tracing. Ba loại dữ liệu bổ sung cho nhau.

## 7. Khi nào nên dùng instrumentation có sẵn?

Trước khi viết interceptor riêng, kiểm tra instrumentation Micrometer/Observation mà phiên bản Spring Integration và Spring Boot đang dùng đã cung cấp cho channel hoặc endpoint đó chưa. Instrumentation có sẵn thường hiểu rõ lifecycle của component và tránh việc tự ghép các callback không cùng phạm vi.

Interceptor tùy chỉnh phù hợp khi cần metadata riêng của ứng dụng, quy tắc log đặc thù hoặc metric outcome mà instrumentation hiện tại chưa cung cấp. Không nên tạo một lớp tracing song song với Micrometer Tracing nếu framework đã instrument cùng operation; việc đó có thể tạo span trùng hoặc làm sai quan hệ cha-con.

## 8. Chi phí và an toàn trên đường nóng

Interceptor có thể chạy cho mọi message. Vì vậy:

- Giữ callback ngắn và tránh gọi HTTP/database.
- Không serialize payload chỉ để ghi log.
- Không tạo tag metric từ giá trị có cardinality cao.
- Không dùng lock toàn cục hoặc map state theo message nếu không cần.
- Không ghi log chi tiết ở INFO cho mọi message trên channel tốc độ cao.
- Chỉ đăng ký global interceptor theo pattern channel cần quan sát.
- Đo throughput và p95/p99 latency trước/sau khi bật instrumentation.

Nếu cần audit bền vững, ghi audit event bằng endpoint hoặc outbox riêng. `ChannelInterceptor` không phải kho audit và callback send không chứng minh transaction nghiệp vụ đã commit.

## 9. Chẩn đoán qua log, metric và trace

| Triệu chứng | Dữ liệu nên xem | Hướng kiểm tra |
|---|---|---|
| Message không tới endpoint | Log send, metric accepted/rejected, topology | Channel có subscriber không, router chọn đúng output không |
| Send thành công nhưng nghiệp vụ thất bại | Error log, trace endpoint, error flow | Handler lỗi sau khi channel đã nhận message |
| `ExecutorChannel` send nhanh nhưng xử lý chậm | Executor queue, worker utilization, handler span | Tách dispatch latency khỏi handler latency |
| Queue backlog tăng | Queue depth, oldest message age, consumer throughput | Consumer chậm, poller dừng hoặc producer vượt capacity |
| Trace bị đứt sau async boundary | Trace ID trước/sau executor, context propagation | Kiểm tra Observation và TaskDecorator/propagator |
| Metric backend tăng cardinality | Danh sách tag và số time series | Loại bỏ message/tenant ID khỏi metric tags |
| Log chứa sai correlation ID | MDC và thread reuse | Kiểm tra context propagation và cleanup trong `finally` |

Một quy trình điều tra hiệu quả là dùng metric phát hiện channel hoặc nhóm endpoint bất thường, trace xác định span chậm, rồi dùng log theo message ID/Correlation ID để xem sự kiện và exception cụ thể.

## 10. Checklist triển khai

- [ ] Chọn phạm vi interceptor cục bộ hoặc global pattern hẹp.
- [ ] Dùng `preSend` để log metadata cần thiết và `afterSendCompletion` để ghi exception.
- [ ] Dùng `postSend` để phân biệt send accepted với rejected.
- [ ] Không ghi payload hoặc header nhạy cảm.
- [ ] Dùng metric tag có cardinality thấp.
- [ ] Đo thời gian tại đúng tầng: channel dispatch hay handler processing.
- [ ] Dùng Micrometer Observation/Tracing cho span và context propagation.
- [ ] Không tự tạo span trùng với instrumentation có sẵn.
- [ ] Kiểm tra MDC/trace context qua `ExecutorChannel`, poller và broker adapter.
- [ ] Đo chi phí instrumentation trên tải gần production.

Interceptor là điểm quan sát hữu ích ở ranh giới channel, nhưng mỗi callback chỉ cho biết một phần của vòng đời message. Khi dùng log cho sự kiện, metric cho xu hướng và tracing cho đường đi xuyên suốt, đồng thời tôn trọng ranh giới đồng bộ/bất đồng bộ, ta có thể quan sát Spring Integration mà không nhầm việc channel nhận message với việc nghiệp vụ đã hoàn tất.

## Tài liệu tham khảo

- [Spring Framework API: ChannelInterceptor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Integration Reference: Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html)
- [Spring Integration Reference: Micrometer Observation](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/)

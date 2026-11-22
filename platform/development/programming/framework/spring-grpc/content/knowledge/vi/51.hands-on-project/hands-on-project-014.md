# Đo latency, throughput và lỗi sau khi triển khai

Trong dự án này, bạn sẽ bổ sung khả năng đo lường và thực hiện một đợt kiểm tra tải cho dịch vụ Spring gRPC đã triển khai. Bạn sẽ tạo tải có kiểm soát, thu thập latency, throughput và gRPC status, sau đó đối chiếu metric, trace và log để giải thích điều gì xảy ra khi số client hoặc tốc độ gửi tăng lên.

Mục tiêu là tạo ra một kết quả có thể lặp lại và dùng được cho quyết định vận hành. Một con số latency trung bình hoặc một lần gọi thành công bằng grpcurl không đủ để đánh giá hiệu năng. Bạn cần xác định rõ phép đo, tải đầu vào, tỷ lệ lỗi, phân vị latency và tài nguyên mà server sử dụng.

## 1. Kịch bản và phạm vi dự án

Giả sử bạn có một dịch vụ Spring gRPC cung cấp các RPC tra cứu và cập nhật dữ liệu. Dịch vụ có ít nhất một unary RPC và một RPC streaming. Bạn cần trả lời các câu hỏi sau sau khi triển khai:

- Khi số client đồng thời tăng, latency p95/p99 thay đổi như thế nào?
- Server xử lý được bao nhiêu RPC hoặc message mỗi giây ở một mức tải nhất định?
- Status lỗi nào xuất hiện khi tải tăng, và chúng bắt đầu xuất hiện ở mức tải nào?
- Thời gian nằm ở server, dependency hay đường truyền?
- Với streaming, server có duy trì được các stream dài và xử lý được client đọc chậm không?
- Sau khi đạt giới hạn tài nguyên, hệ thống phục hồi thế nào khi giảm tải?

Phạm vi bản đầu tiên gồm một môi trường triển khai, một dịch vụ Spring gRPC, một máy hoặc tiến trình tạo tải riêng và một hệ thống thu thập metric. Bạn có thể dùng Prometheus/Grafana và OpenTelemetry nếu chúng đã có trong môi trường. Nếu dự án dùng nền tảng giám sát khác, hãy ánh xạ các khái niệm và phép đo tương đương.

Không thay đổi nhiều cấu hình server trong cùng một lần thử. Khi so sánh hai phiên bản, giữ nguyên tải, payload, thời gian chạy, vị trí máy tạo tải và điều kiện môi trường để kết quả có ý nghĩa.

## 2. Mục tiêu học tập

Hoàn thành dự án sẽ giúp bạn:

- Phân biệt latency của một RPC, latency xử lý ở server và latency của một message trong stream.
- Đo throughput theo RPC/giây, message/giây và byte/giây.
- Đọc p50, p95, p99, error rate và gRPC status distribution.
- Tạo load profile có warm-up, ramp-up, steady state và thời gian nghỉ.
- Instrument server bằng Micrometer hoặc hệ thống metric tương đương.
- Kết nối trace và log để điều tra một request chậm hoặc lỗi.
- Thiết kế dashboard và báo cáo kết quả có dữ liệu, điều kiện thử nghiệm và giới hạn rõ ràng.
- Phân biệt lỗi do server, dependency, mạng, deadline và chính load generator.

## 3. Định nghĩa các chỉ số cần đo

Trước khi viết load test, hãy thống nhất định nghĩa của từng chỉ số. Cùng một tên gọi có thể biểu thị các khoảng thời gian khác nhau.

| Chỉ số | Định nghĩa trong dự án | Cách dùng |
| --- | --- | --- |
| Client-observed latency | Thời gian từ lúc client bắt đầu một RPC đến lúc nhận response cuối hoặc status kết thúc | Phản ánh trải nghiệm tổng thể của client |
| Server call duration | Thời gian server xử lý một RPC từ lúc nhận đến lúc đóng call | Giúp tách phần server khỏi thời gian mạng và client |
| Message round-trip latency | Thời gian từ lúc client gửi một message có định danh đến lúc nhận ACK tương ứng | Dùng cho thao tác trong bidi streaming |
| Time to first response | Thời gian mở RPC đến response đầu tiên | Hữu ích với server streaming và bidi streaming |
| Inter-message gap | Khoảng cách giữa hai response liên tiếp mà client nhận được | Giúp phát hiện stream bị ngắt quãng hoặc server phát chậm |
| Throughput | Số RPC thành công, message được xử lý hoặc byte truyền trong một đơn vị thời gian | Phải ghi rõ đơn vị và chỉ tính trong khoảng đo ổn định |
| Error rate | Số RPC hoặc thao tác thất bại chia cho tổng số RPC hoặc thao tác đã thử | Phải nêu rõ mẫu số và cách phân loại cancellation |
| Active streams | Số RPC streaming đang mở tại một thời điểm | Theo dõi tài nguyên và khả năng duy trì phiên dài |

Với unary RPC, latency của một call tương đối dễ xác định. Với streaming, thời gian sống của toàn bộ stream có thể kéo dài nhiều phút hoặc nhiều giờ; không dùng thời gian đó thay cho latency xử lý message. Hãy đo thời gian mở stream, time-to-first-response, message round-trip và thời gian sống stream như các chỉ số riêng.

Khi đo message round-trip, dùng đồng hồ monotonic ở client: ghi thời điểm ngay trước khi gửi message và dừng khi nhận ACK có cùng `operation_id`. Không trừ timestamp do hai máy tự ghi nếu chưa xử lý clock skew. Nếu cần đo thời gian xử lý riêng ở server, ghi timestamp hoặc duration tại server và dùng trace/metric tương ứng.

Latency trung bình có thể che khuất một nhóm request rất chậm. Báo cáo tối thiểu p50, p95 và p99, kèm số mẫu. Phân vị ở các cửa sổ hoặc instance khác nhau không thể cộng hoặc lấy trung bình đơn giản để tạo ra phân vị toàn hệ thống; hãy tính từ histogram bucket hoặc dữ liệu mẫu phù hợp.

## 4. Chuẩn bị môi trường đo

Trước khi tạo tải, ghi lại thông tin của môi trường:

- Phiên bản ứng dụng, commit/build ID và cấu hình Spring gRPC đang chạy.
- CPU, RAM, giới hạn container, số replica và cách phân phối request.
- Phiên bản Java/JVM, heap, garbage collector và các giới hạn thread/executor liên quan.
- Endpoint, TLS/mTLS, proxy, ingress hoặc load balancer trên đường đi.
- Phiên bản proto và kích thước payload của từng RPC.
- Vị trí máy tạo tải và độ trễ mạng cơ bản đến endpoint.
- Phiên bản load generator, cấu hình channel/stub và giới hạn tài nguyên của máy tạo tải.
- Dependency mà handler gọi, cùng trạng thái và tải nền của chúng.

Chạy load generator trên máy riêng hoặc tiến trình riêng với server. Nếu tạo tải trên cùng máy, CPU hoặc network của load generator có thể cạnh tranh với server và làm sai kết luận. Theo dõi chính load generator: CPU, RAM, số thread, số connection/channel, event loop và khả năng duy trì tốc độ gửi.

Kiểm tra endpoint bằng một request nhỏ trước khi chạy benchmark. `grpcurl` hữu ích để xác nhận service, method, reflection/proto, TLS và metadata; nó không phải công cụ đo tải đồng thời hoặc thay thế load generator.

## 5. Xây dựng load profile có thể lặp lại

Tạo một load test client riêng bằng Java gRPC stub hoặc dùng công cụ tạo tải gRPC phù hợp với môi trường. Nếu tự viết client, hãy dùng channel được tái sử dụng, stub đúng loại, payload được chuẩn bị trước và bộ thu thập latency không chặn luồng callback. Tránh tạo một channel mới cho mỗi RPC vì việc đó đo cả chi phí khởi tạo kết nối và có thể tạo tải không giống client thực tế.

Một lượt benchmark nên có các giai đoạn:

1. **Preflight:** xác nhận endpoint, xác thực, method, payload và trạng thái health.
2. **Warm-up:** gửi tải nhẹ để JVM, connection pool, DNS và cache ổn định; không đưa giai đoạn này vào số liệu steady state.
3. **Ramp-up:** tăng dần số client đồng thời hoặc tốc độ request để tránh tạo một spike ngoài dự kiến.
4. **Steady state:** giữ tải mục tiêu đủ lâu để thu được mẫu có ý nghĩa và metric hệ thống ổn định.
5. **Ramp-down:** giảm tải có kiểm soát và quan sát thời gian hàng đợi, CPU, active stream trở về mức bình thường.
6. **Cool-down:** chờ metric và log hoàn tất trước khi bắt đầu lượt thử tiếp theo.

Ví dụ ma trận thử nghiệm ban đầu:

| Lượt | Mức đồng thời | Thời gian warm-up | Thời gian đo ổn định | Mục đích |
| --- | ---: | ---: | ---: | --- |
| A | 1 client | 30 giây | 2 phút | Lấy baseline latency thấp tải |
| B | 10 client | 30 giây | 3 phút | Quan sát mức tải nhẹ |
| C | 25 client | 30 giây | 3 phút | Quan sát xu hướng khi tăng concurrency |
| D | 50 client | 30 giây | 3 phút | Tìm dấu hiệu bão hòa ban đầu |
| E | 100 client | 30 giây | 3 phút | Đánh giá ở tải cao hơn nếu môi trường cho phép |

Các mức trên chỉ là ví dụ. Hãy điều chỉnh theo giới hạn môi trường và mục tiêu tải của hệ thống. Không tăng tải vượt giới hạn được phê duyệt của môi trường dùng chung. Chạy mỗi cấu hình ít nhất ba lần nếu muốn so sánh xu hướng; ghi nhận biến động giữa các lần chạy.

Giữ cố định payload và workload khi so sánh concurrency. Sau đó mới tạo một ma trận riêng cho payload nhỏ/lớn, TLS bật/tắt nếu có lý do hợp lệ, hoặc các kiểu RPC khác nhau. Thay đổi từng yếu tố một để biết yếu tố nào làm kết quả thay đổi.

## 6. Thiết kế workload cho từng kiểu RPC

Không gộp tất cả loại RPC vào một con số throughput duy nhất. Mỗi kiểu RPC có đơn vị công việc và cách đo riêng.

| Kiểu RPC | Workload | Latency nên ghi | Throughput nên ghi |
| --- | --- | --- | --- |
| Unary | Gửi request độc lập với payload xác định | Client-observed latency và server call duration | RPC thành công/giây |
| Server streaming | Mở stream và yêu cầu dữ liệu, server phát nhiều response | Time-to-first-response, inter-message gap, thời gian hoàn tất nếu có | Message nhận/giây và stream mở/giây |
| Client streaming | Gửi số lượng message xác định rồi half-close | Thời gian upload, thời gian đến response cuối | Message nhận/giây và stream hoàn tất/giây |
| Bidi streaming | Duy trì nhiều stream, gửi message theo tốc độ xác định và nhận ACK/notification | Message round-trip, time-to-first-response, tuổi stream | Message gửi/nhận/giây và active streams |

Với streaming, hãy ghi số message mỗi stream, tốc độ gửi mỗi client, thời gian sống mục tiêu và chính sách đóng stream. Nếu chỉ ghi số RPC hoàn tất, một bidi stream kéo dài lâu có thể khiến throughput trông rất thấp dù message rate cao.

Tạo ít nhất hai workload:

- **Workload bình thường:** payload nhỏ, tốc độ ổn định, tỷ lệ đọc/ghi gần với hành vi client dự kiến.
- **Workload nặng:** payload lớn hơn hoặc nhiều stream đồng thời, nhưng vẫn nằm trong giới hạn cấu hình và mục tiêu thử nghiệm.

Với bidi, mỗi message nên mang `operation_id` để ghép request với ACK. Load generator cần lưu thời điểm gửi theo đồng hồ monotonic và khi nhận ACK thì cập nhật mẫu latency tương ứng. Nếu ACK bị thiếu, ghi nhận timeout hoặc stream kết thúc như một kết quả lỗi riêng, không loại bỏ mẫu đó.

## 7. Thu thập metric phía server bằng Micrometer

Nếu ứng dụng đã dùng Spring Boot Actuator và Micrometer, đăng ký các metric trong `MeterRegistry` thông qua một gRPC `ServerInterceptor` hoặc lớp instrumentation tương đương của stack đang dùng. Nếu starter cung cấp instrumentation sẵn, ưu tiên cơ chế đã được hỗ trợ và kiểm tra tên metric thực tế trước khi viết dashboard.

Các metric cơ bản nên có:

| Metric logic | Loại metric | Tag/label gợi ý |
| --- | --- | --- |
| Số RPC bắt đầu/kết thúc | Counter | `method`, `status` |
| Thời gian xử lý RPC | Timer/histogram | `method`, `status` |
| Message nhận/gửi | Counter | `method`, `direction` |
| Stream đang mở | Gauge | `method` |
| Queue outbound | Gauge | `method` hoặc loại queue cố định |
| Số lần queue đầy | Counter | `method`, `policy` |
| Lỗi dependency | Counter/timer | `dependency`, `outcome` |

Ví dụ cấu trúc interceptor để đo thời gian server call:

```java
public final class GrpcMetricsInterceptor implements ServerInterceptor {
    private final MeterRegistry registry;

    public GrpcMetricsInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();
        Timer.Sample sample = Timer.start(registry);
        AtomicBoolean recorded = new AtomicBoolean(false);
        registry.counter("grpc.server.calls.started", "method", method)
                .increment();

        ServerCall<ReqT, RespT> monitoredCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void sendMessage(RespT message) {
                        registry.counter("grpc.server.messages", 
                                "method", method, "direction", "outbound")
                                .increment();
                        super.sendMessage(message);
                    }

                    @Override
                    public void close(Status status, Metadata trailers) {
                        if (recorded.compareAndSet(false, true)) {
                            String code = status.getCode().name();
                            registry.counter("grpc.server.calls.completed",
                                    "method", method, "status", code)
                                    .increment();
                            sample.stop(Timer.builder("grpc.server.call.duration")
                                    .tag("method", method)
                                    .tag("status", code)
                                    .publishPercentileHistogram()
                                    .register(registry));
                        }
                        super.close(status, trailers);
                    }
                };

        ServerCall.Listener<ReqT> listener =
                next.startCall(monitoredCall, headers);
        return new ForwardingServerCallListener.SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onMessage(ReqT message) {
                registry.counter("grpc.server.messages",
                        "method", method, "direction", "inbound")
                        .increment();
                super.onMessage(message);
            }
        };
    }
}
```

Đây là skeleton minh họa. Hãy bổ sung import, đăng ký interceptor với server, kiểm tra phiên bản API gRPC/Micrometer của dự án và xác minh interceptor được áp dụng cho đúng service. Với streaming, `close()` đo thời gian toàn RPC; nó không đo latency từng message. Muốn đo thời gian xử lý message ở server, hãy instrument tại handler hoặc pipeline xử lý, dùng một timer cho loại thao tác phù hợp.

Khi triển khai thực tế, hãy kiểm tra thêm các đường kết thúc như cancellation và exception để bảo đảm counter/gauge được cập nhật đúng một lần. Nếu có gauge active streams, tăng khi call bắt đầu và giảm khi call kết thúc hoặc bị hủy. Không đăng ký gauge bằng object tạm thời có thể bị garbage collector thu hồi.

### Quy tắc về cardinality

Chỉ dùng label có tập giá trị nhỏ và ổn định, ví dụ method name, gRPC status code và direction. Không dùng `user_id`, `room_id`, `request_id`, `operation_id`, token hoặc nội dung payload làm label. Mỗi giá trị duy nhất tạo thêm một time series; label có cardinality cao có thể làm Prometheus và dashboard quá tải.

## 8. Thu thập trace và log

Metric cho biết xu hướng tổng thể; trace giúp điều tra một request cụ thể. Cấu hình OpenTelemetry hoặc tracing stack hiện có để tạo trace cho RPC và các dependency mà handler gọi.

Một trace hữu ích có thể cho thấy:

1. Client bắt đầu RPC và gửi metadata/trace context.
2. Server nhận RPC, chạy interceptor và handler.
3. Handler gọi database, HTTP client hoặc message broker.
4. Dependency trả kết quả hoặc timeout.
5. Server phát response và kết thúc RPC với status.

Với streaming, tránh tạo một span mới cho mọi message ở lưu lượng rất cao nếu chi phí tracing vượt mục tiêu. Có thể tạo span cho vòng đời stream và event/span mẫu cho một số thao tác; bổ sung metric cho tổng số message và latency phân bố. Dùng trace ID trong log để liên kết các dòng log của cùng một call.

Log nên ghi method, status, thời gian, trace ID và thông tin chẩn đoán đã được kiểm soát. Không ghi bearer token, private key, toàn bộ payload hoặc dữ liệu cá nhân. Lỗi dự kiến như validation nên được phân biệt với lỗi hệ thống để dashboard không biến mọi lỗi nghiệp vụ thành sự cố hạ tầng.

## 9. Dashboard cần xây dựng

Tạo dashboard có ít nhất các khu vực sau:

| Khu vực | Biểu đồ hoặc bảng | Câu hỏi cần trả lời |
| --- | --- | --- |
| Traffic | RPC/s, message/s, byte/s theo method | Lưu lượng có đúng với load profile không? |
| Latency | p50, p95, p99 theo method | Độ trễ tăng ở mức tải nào? |
| Errors | Error rate và status distribution | Lỗi nào bắt đầu xuất hiện và ở thời điểm nào? |
| Concurrency | Active RPC, active stream | Server đang giữ bao nhiêu call/stream? |
| Server resources | CPU, memory, heap, GC pause, thread/executor queue | Tài nguyên nào tiến gần giới hạn? |
| Dependencies | Latency, timeout và error của database/HTTP/broker | Thời gian bị tiêu tốn ở dependency nào? |
| Backpressure | Queue depth, isReady/slow consumer, overflow count | Client chậm có làm queue tăng không? |

Ví dụ PromQL dưới đây giả sử metric Micrometer được export thành các tên Prometheus tương ứng. Tên thực tế có thể khác theo exporter và quy ước đặt tên; hãy xác nhận trong trang metrics trước khi sử dụng.

Throughput RPC thành công:

```promql
sum by (method) (
  rate(grpc_server_calls_completed_total{status="OK"}[5m])
)
```

Tỷ lệ RPC kết thúc với status khác `OK`:

```promql
sum(rate(grpc_server_calls_completed_total{status!="OK"}[5m]))
/
clamp_min(sum(rate(grpc_server_calls_completed_total[5m])), 1e-9)
```

Latency p95 theo method từ histogram:

```promql
histogram_quantile(
  0.95,
  sum by (le, method) (
    rate(grpc_server_call_duration_seconds_bucket[5m])
  )
)
```

Message rate theo chiều:

```promql
sum by (method, direction) (
  rate(grpc_server_messages_total[5m])
)
```

Các biểu thức trên minh họa cách tính. Nếu metric thực tế có tên hoặc label khác, sửa truy vấn theo dữ liệu đã export. Không áp dụng error ratio cho message bằng cách lấy status của RPC nếu ứng dụng có lỗi nghiệp vụ được trả dưới dạng frame; khi đó cần một counter riêng cho operation accepted/rejected.

## 10. Chạy các thử nghiệm và ghi kết quả

Thực hiện tối thiểu các thử nghiệm sau:

### Thử nghiệm A: Baseline unary

Chạy một client hoặc concurrency thấp với payload cố định. Ghi p50/p95/p99, RPC/s, status và CPU/memory. Đây là mốc để so sánh các lượt tải cao hơn.

### Thử nghiệm B: Tăng concurrency

Tăng concurrency theo ma trận đã chọn. Quan sát điểm mà p95/p99 bắt đầu tăng nhanh, throughput không tăng tương ứng hoặc error rate xuất hiện. Đó có thể là dấu hiệu bão hòa ở server, dependency, mạng hoặc load generator; dùng trace và resource metric để xác định.

### Thử nghiệm C: Payload nhỏ và lớn

Giữ concurrency và request rate như nhau, thay đổi kích thước payload. Theo dõi byte/s, CPU serialization, network throughput, latency và message size limit. Không kết luận payload là nguyên nhân nếu các yếu tố khác cũng thay đổi.

### Thử nghiệm D: Streaming

Mở số stream đồng thời đã định, gửi message theo tốc độ ổn định và đo message round-trip. Với server streaming, ghi time-to-first-response và inter-message gap. Với client streaming, ghi upload duration và latency đến response cuối. Quan sát active stream và queue khi client đọc chậm.

### Thử nghiệm E: Deadline và dependency chậm

Trong môi trường kiểm thử có kiểm soát, mô phỏng dependency chậm hoặc deadline ngắn. Xác minh client nhận status phù hợp, server ghi metric lỗi và trace thể hiện thời gian chờ dependency. Không gây lỗi có chủ ý trên production hoặc môi trường dùng chung không được phép.

### Thử nghiệm F: Ramp-down và phục hồi

Sau khi giảm tải, quan sát active streams, queue depth, thread/executor queue, CPU và memory có trở về mức bình thường hay không. Kiểm tra có tác vụ bị treo, stream không được đóng hoặc backlog tiếp tục tăng không.

Với mỗi lượt, ghi lại:

- Run ID, ngày giờ, commit/build ID và môi trường.
- RPC/method, proto version, payload size và TLS/proxy path.
- Concurrency hoặc target request/message rate.
- Warm-up, ramp-up, steady-state và ramp-down duration.
- Số RPC/message đã gửi, thành công, lỗi, timeout và cancellation.
- p50/p95/p99, throughput, error rate và active streams.
- CPU, memory, GC, thread/executor queue và dependency latency.
- Ghi chú bất thường và trace ID của một số request chậm/lỗi.

## 11. Phân loại lỗi gRPC

Đừng gộp mọi status khác `OK` thành một loại lỗi duy nhất. Hãy giữ phân bố theo status và xác định lỗi nào là kết quả mong đợi của test.

| Status | Hướng điều tra |
| --- | --- |
| `UNAVAILABLE` | Server/endpoint không sẵn sàng, kết nối bị đóng, proxy/upstream lỗi hoặc instance đang restart. |
| `DEADLINE_EXCEEDED` | Deadline ngắn hơn thời gian hoàn tất, dependency chậm, queue chờ hoặc server quá tải. |
| `RESOURCE_EXHAUSTED` | Quota, giới hạn message, queue, stream đồng thời hoặc tài nguyên đã chạm ngưỡng. |
| `INTERNAL` | Exception hoặc lỗi nội bộ; tìm trace ID và stack trace phía server. |
| `CANCELLED` | Client, proxy hoặc test harness đã hủy call; phân biệt cancellation chủ động khi dừng test với cancellation bất thường. |
| `UNAUTHENTICATED` | Credential thiếu, sai hoặc hết hạn; kiểm tra metadata và interceptor. |
| `PERMISSION_DENIED` | Principal không được phép thực hiện thao tác; kiểm tra policy và tenant. |
| `INVALID_ARGUMENT` | Payload không hợp lệ hoặc sai hợp đồng; kiểm tra dữ liệu của load generator. |
| `UNIMPLEMENTED` | Method/service không được đăng ký hoặc client dùng sai descriptor/tên method. |

Định nghĩa error rate theo loại workload. Với unary, có thể dùng số RPC kết thúc khác `OK` chia tổng RPC kết thúc. Với streaming, báo cáo cả tỷ lệ stream kết thúc lỗi và tỷ lệ operation/message bị từ chối hoặc timeout. Tách cancellation do harness chủ động đóng stream khi kết thúc test khỏi lỗi xảy ra trong steady state.

## 12. Cách đọc kết quả và tìm nút thắt

Một số mẫu hình thường gặp:

| Quan sát | Giả thuyết cần kiểm chứng |
| --- | --- |
| Throughput tăng, p95 gần ổn định | Hệ thống còn khả năng phục vụ tải tăng trong vùng đang đo. |
| Throughput đi ngang, p95/p99 tăng nhanh | Một thành phần đã gần bão hòa; kiểm tra CPU, thread queue, dependency và network. |
| CPU cao, latency tăng, GC pause tăng | Có thể bị giới hạn bởi CPU, serialization, allocation hoặc GC. |
| CPU thấp nhưng latency cao | Kiểm tra chờ I/O, lock contention, connection pool, executor queue và dependency. |
| `DEADLINE_EXCEEDED` tăng cùng queue depth | Request chờ quá lâu trước khi được xử lý hoặc dependency không hoàn tất kịp deadline. |
| `RESOURCE_EXHAUSTED` tăng | Kiểm tra quota, message size, outbound queue, giới hạn concurrent stream và memory. |
| Unary ổn định nhưng streaming suy giảm | Kiểm tra stream lifetime, số message, flow control, slow consumer và cleanup. |
| Load generator CPU cao hoặc không đạt target rate | Phép thử có thể bị giới hạn bởi load generator; chưa thể kết luận server đã đạt giới hạn. |
| Latency client cao nhưng server call duration thấp | Kiểm tra network, proxy, client scheduling, channel và thời gian chờ trước/sau server. |

Đây là giả thuyết, không phải kết luận tự động. Dùng trace và metric ở cùng khoảng thời gian để xác nhận. Tránh tăng thread pool, timeout hoặc replica chỉ dựa trên một biểu đồ; mỗi thay đổi cần một giả thuyết và một lượt thử đối chứng.

## 13. Tiêu chí nghiệm thu

Dự án được xem là hoàn thành khi:

- [ ] Có load generator độc lập với server và tái sử dụng channel/stub phù hợp.
- [ ] Có ít nhất một workload unary và một workload streaming; nếu module triển khai cả bốn kiểu RPC, ghi phép đo tương ứng cho từng kiểu.
- [ ] Load profile có preflight, warm-up, ramp-up, steady state và ramp-down.
- [ ] Báo cáo ghi rõ định nghĩa latency, throughput, error rate, đơn vị và số mẫu.
- [ ] Có p50, p95, p99, RPC/s hoặc message/s và phân bố gRPC status.
- [ ] Streaming được đo theo message round-trip/time-to-first-response, không dùng riêng stream lifetime làm latency.
- [ ] Server xuất metric cho call duration, calls, messages và active streams hoặc các chỉ số tương đương.
- [ ] Có trace/log đủ để điều tra một request chậm và một lỗi đại diện.
- [ ] Dashboard thể hiện traffic, latency, errors, concurrency, tài nguyên và dependency.
- [ ] Load generator được theo dõi để loại trừ trường hợp chính nó trở thành bottleneck.
- [ ] Có ít nhất ba lượt lặp cho một cấu hình so sánh quan trọng hoặc giải thích vì sao không thể lặp.
- [ ] Không đưa credential, payload nhạy cảm hoặc ID có cardinality cao vào metric/log.

Không đặt một ngưỡng latency chung cho mọi môi trường. Nếu nhóm đã có SLO, dùng SLO đó làm tiêu chí. Nếu chưa có, báo cáo baseline và xu hướng theo tải, đồng thời nêu rõ cần xác định SLO với chủ hệ thống trước khi kết luận đạt/không đạt.

## 14. Kết quả cần bàn giao

Khi nộp dự án, cung cấp:

- Mã load generator hoặc cấu hình công cụ tạo tải và hướng dẫn chạy.
- Cấu hình instrumentation metric/tracing và cách bật trong môi trường kiểm thử.
- Dashboard hoặc file cấu hình dashboard cùng các truy vấn đã dùng.
- Bảng kết quả từng lượt thử, bao gồm p50/p95/p99, throughput, error rate, status và tài nguyên.
- Ít nhất một trace của request chậm và một ví dụ lỗi được phân tích.
- Báo cáo nêu điều kiện thử nghiệm, giới hạn của phép đo, bottleneck đã xác nhận và đề xuất tiếp theo.

Một báo cáo tốt cho phép người khác chạy lại cùng workload và hiểu tại sao kết luận được đưa ra. Latency, throughput và error rate chỉ có ý nghĩa khi đi kèm định nghĩa phép đo, điều kiện tải và dữ liệu quan sát từ server lẫn client.

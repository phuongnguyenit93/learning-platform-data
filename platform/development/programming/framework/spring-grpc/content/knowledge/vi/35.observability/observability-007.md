# Retry attempt và final status

Một client gRPC có thể thử gọi lại RPC khi attempt trước gặp lỗi tạm thời. Vì vậy, một thao tác từ góc nhìn caller có thể tạo nhiều attempt ở transport/server nhưng chỉ có một kết quả cuối cùng ở API client. Nếu chỉ đếm status cuối, ta không thấy retry đang khuếch đại tải; nếu chỉ đếm lỗi từng attempt, ta có thể đánh giá nhầm một call cuối cùng đã thành công.

**Retry attempt và final status** là cách quan sát riêng số lần thử, kết quả của từng attempt và status cuối của logical RPC. Bài thuộc chương **Observability** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là phân biệt logical call với attempt, hiểu retry commitment và deadline tổng, rồi thiết kế metrics/traces không đếm lẫn kết quả trung gian với kết quả cuối.

## 1. Logical call và attempt là hai đơn vị khác nhau

- **Logical call** là một lần ứng dụng gọi một gRPC method, ví dụ Inventory.GetStock.
- **Attempt** là một lần client thực sự thử thực hiện logical call tới server/transport.
- **Retry** là attempt bổ sung sau attempt trước, khi lỗi và policy cho phép thử lại.
- **Final status** là status duy nhất mà caller nhận khi logical call kết thúc.
- **Attempt status** là kết quả của từng lần thử; attempt thất bại có thể được theo sau bởi attempt khác.

Ví dụ client gọi GetStock một lần:

1. Attempt 1 tới instance A, nhận UNAVAILABLE.
2. Client chờ backoff rồi thử attempt 2 tới instance B.
3. Attempt 2 trả response thành công.
4. Ứng dụng nhận final status OK.

Trong trường hợp này, có một logical call, hai attempts, một retry và final status OK. Server A có thể ghi nhận một call kết thúc UNAVAILABLE; server B ghi nhận một call kết thúc OK. Client-level logical-call metric chỉ ghi một kết quả cuối OK.

Đừng cộng số attempt với số logical call thành “tổng request”. Chúng đo hai lớp khác nhau. Attempt count phản ánh tải thực tế mà client tạo ra; logical call count phản ánh ý định gọi ở tầng ứng dụng.

## 2. Retry không phải lúc nào cũng xảy ra

gRPC retry cần policy phù hợp và attempt phải chưa bị commitment. Các yếu tố chính:

- Method có retry policy trong service config.
- Status của attempt nằm trong retryableStatusCodes.
- Số attempt chưa vượt maxAttempts.
- Deadline tổng còn đủ thời gian cho backoff và attempt tiếp theo.
- Call chưa bị commit theo quy tắc retry của gRPC.
- Retry throttling hoặc server pushback không yêu cầu dừng retry.

Nếu không có retry policy, gRPC vẫn có thể thực hiện một số transparent retry giới hạn trong trường hợp transport biết request chưa được server xử lý. Transparent retry khác với retry theo policy và cần được phân biệt khi đọc metrics.

Một call có thể kết thúc ngay ở attempt đầu dù status retryable nếu policy không áp dụng, deadline gần hết, retry bị throttled hoặc call đã committed. Ngược lại, một logical call cuối cùng OK vẫn có thể đã tạo nhiều attempts thất bại trước đó.

## 3. Retry commitment và giới hạn của việc phát lại

Retry chỉ an toàn khi gRPC còn có thể phát lại call theo semantics và dữ liệu đã được buffer. Một call có thể trở thành committed, sau đó gRPC không tiếp tục retry call đó theo policy. Những điều kiện commitment cụ thể phụ thuộc protocol/runtime và có thể gồm việc client đã nhận response headers hoặc vượt giới hạn retry buffer.

Các điểm cần nhớ:

- Trước khi nhận response headers, gRPC có thể còn khả năng retry nếu attempt kết thúc bằng status retryable và policy cho phép.
- Khi response headers đã được chuyển tới ứng dụng, call thường đã committed; không giả định client sẽ thử lại attempt đó.
- Retry buffer giới hạn lượng request data được giữ để phát lại. Vượt giới hạn có thể commit call.
- Với streaming RPC, message có thể đã được gửi/nhận hoặc xử lý một phần; không thể mặc định mở lại stream và phát lại toàn bộ mà không tạo message trùng.
- Một attempt lỗi không chứng minh server chưa thực hiện side effect. Response có thể mất sau khi server đã commit nghiệp vụ.

Vì vậy, retry phù hợp nhất với operation idempotent hoặc operation có idempotency key/deduplication. Với RPC ghi, thiết kế nghiệp vụ phải chịu được việc cùng một logical operation tới server nhiều lần.

## 4. Cấu hình retry cho một unary method

Ví dụ service config cho method đọc inventory.Inventory/GetStock:

~~~java
Map<String, ?> retryPolicy = Map.of(
        "maxAttempts", 3.0,
        "initialBackoff", "0.1s",
        "maxBackoff", "1s",
        "backoffMultiplier", 2.0,
        "retryableStatusCodes", List.of("UNAVAILABLE")
);

Map<String, ?> methodConfig = Map.of(
        "name", List.of(Map.of(
                "service", "inventory.Inventory",
                "method", "GetStock")),
        "retryPolicy", retryPolicy
);

Map<String, ?> serviceConfig = Map.of(
        "methodConfig", List.of(methodConfig)
);

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///inventory.internal:8443")
        .defaultServiceConfig(serviceConfig)
        .build();
~~~

maxAttempts bao gồm attempt đầu tiên. Với giá trị 3, client có tối đa ba lần thử cho một logical call, tức tối đa hai retries. Backoff tăng theo initialBackoff và backoffMultiplier, nhưng không vượt maxBackoff; runtime còn có thể áp dụng jitter/throttling theo retry implementation.

Ví dụ chỉ retry UNAVAILABLE. Không đưa INVALID_ARGUMENT, PERMISSION_DENIED hoặc UNAUTHENTICATED vào retryable status một cách máy móc vì gửi lại cùng request/credential thường không sửa được nguyên nhân. RESOURCE_EXHAUSTED chỉ nên retry khi semantics và tín hiệu server cho biết lỗi tạm thời, đồng thời có backoff và giới hạn tải.

Trong ứng dụng Spring, channel thường do starter hoặc client configuration quản lý. Đặt service config tại đúng nơi tạo channel; không tạo channel mới cho mỗi RPC. Kiểm tra phiên bản grpc-java và cơ chế resolver có truyền service config tới channel hay không.

## 5. Deadline áp dụng cho toàn logical call

Deadline của logical call bao phủ các attempts và khoảng backoff giữa chúng. Retry không được cấp lại toàn bộ timeout cho mỗi attempt:

~~~text
Logical call deadline: 1.0 s

Attempt 1: 0.0 s ---------------- 0.2 s  UNAVAILABLE
Backoff:                       0.2 s -- 0.3 s
Attempt 2:                              0.3 s -------- 0.7 s  UNAVAILABLE
Backoff:                                                    0.7 s -- 0.8 s
Attempt 3:                                                           0.8 s -- 1.0 s
                                                                    deadline
~~~

Trong ví dụ, attempt 3 chỉ còn phần ngân sách thời gian tới deadline tổng. Nếu deadline hết trong lúc backoff hoặc attempt đang chạy, logical call kết thúc và client thường nhận DEADLINE_EXCEEDED. Một attempt trước có thể đã nhận UNAVAILABLE, nhưng final status của logical call vẫn là DEADLINE_EXCEEDED.

Đây là lý do cần đo attempt status và final status riêng. Nếu dashboard chỉ nhìn final status, có thể không thấy service đã thử lại nhiều lần trước khi deadline hết. Nếu chỉ nhìn attempt errors, có thể bỏ qua việc caller cuối cùng đã nhận kết quả OK.

## 6. Ba lớp status cần quan sát

Một hệ thống có thể có ba góc nhìn status:

| Lớp | Đơn vị | Status biểu thị |
| --- | --- | --- |
| Client logical call | Một lần ứng dụng gọi method | Final status caller nhận ở terminal callback. |
| Client attempt | Một lần thử transport/server | Kết quả của attempt; có thể là lỗi retryable rồi được thử lại. |
| Server call | Một RPC attempt server thực sự nhận | Status server dùng để đóng attempt; không thấy attempts chưa tới server. |

Ví dụ attempt 1 tới server A và kết thúc UNAVAILABLE, attempt 2 tới server B và kết thúc OK:

- Client logical call: một call, final status OK.
- Client attempts: hai attempts, một lỗi UNAVAILABLE và một thành công.
- Server calls: hai RPC được nhận, một UNAVAILABLE và một OK.

Nếu attempt 1 thất bại trước khi tới server, client có thể có attempt failure nhưng server không có call tương ứng. Nếu response bị mất sau khi server đã close OK, server có thể ghi OK trong khi client cuối cùng quan sát UNAVAILABLE hoặc deadline expiry. Không yêu cầu các counter ở ba lớp bằng nhau.

## 7. Metric model: logical calls, attempts và retries

Nên định nghĩa metric tách biệt:

~~~text
grpc.client.calls.started
  type: Counter
  tags: service, method

grpc.client.calls.completed
  type: Counter
  tags: service, method, final_status

grpc.client.attempts.started
  type: Counter
  tags: service, method

grpc.client.attempts.completed
  type: Counter
  tags: service, method, attempt_status

grpc.client.call.retries
  type: Counter
  tags: service, method

grpc.server.calls.completed
  type: Counter
  tags: service, method, server_status
~~~

Tên trên là metric custom minh họa; instrumentation OpenTelemetry hoặc gRPC runtime có thể dùng tên và attributes khác. Giữ semantics trong mô tả metric:

- calls.started tăng một lần khi ứng dụng tạo logical call.
- calls.completed tăng một lần khi logical call có final status.
- attempts.started tăng mỗi khi một attempt bắt đầu.
- attempts.completed tăng khi attempt có kết quả được instrumentation quan sát.
- call.retries tăng cho mỗi attempt bổ sung sau attempt đầu.
- server.calls.completed tăng cho mỗi RPC attempt mà server thực sự nhận và kết thúc.

Không giả định một ClientInterceptor thông thường nhìn thấy mọi retry attempt. Interceptor ở ranh giới ứng dụng thường quan sát logical call và final onClose; retry machinery có thể nằm bên trong channel/transport. Để lấy attempt-level metrics, dùng instrumentation có hỗ trợ retry attempt của gRPC/OpenTelemetry hoặc số liệu từ proxy/control plane; xác minh semantics của phiên bản đang triển khai.

## 8. ClientInterceptor phù hợp để đếm final status

Ví dụ interceptor client đếm một logical call hoàn tất theo final status:

~~~java
public final class LogicalCallMetricsInterceptor
        implements ClientInterceptor {

    private final MeterRegistry registry;

    public LogicalCallMetricsInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        String fullMethod = method.getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String methodName = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);

        registry.counter(
                "grpc.client.calls.started",
                "service", service,
                "method", methodName
        ).increment();

        return new ForwardingClientCall
                .SimpleForwardingClientCall<>(
                        next.newCall(method, callOptions)) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                Listener<RespT> monitored =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(
                                        responseListener) {
                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {
                                registry.counter(
                                        "grpc.client.calls.completed",
                                        "service", service,
                                        "method", methodName,
                                        "final_status",
                                        status.getCode().name()
                                ).increment();
                                super.onClose(status, trailers);
                            }
                        };
                super.start(monitored, headers);
            }
        };
    }
}
~~~

Metric này ghi final status mà application client quan sát. Nếu call retry một lần rồi thành công, interceptor thường ghi một completion với final_status=OK; nó không tự tạo một completion UNAVAILABLE cho attempt trung gian. Đây là hành vi mong muốn của logical-call metric.

## 9. Thu thập attempt-level metrics

Attempt-level metrics cần instrumentation ở tầng biết mỗi attempt bắt đầu/kết thúc. Có thể dùng OpenTelemetry gRPC instrumentation/metrics được hỗ trợ trong phiên bản triển khai, hoặc telemetry của proxy/service mesh. Khi chọn nguồn, xác minh các câu hỏi:

1. attempts.started có tính transparent retry không?
2. Attempt kết thúc trước khi server nhận request có được ghi nhận không?
3. Attempt status là status từ server, transport hay status được retry layer suy ra?
4. Retry counter có tính lần thử đầu tiên không? Theo định nghĩa, retry count thường chỉ tính attempts sau attempt đầu.
5. Final call duration/status được ghi một lần hay ghi theo attempt?

Nếu chỉ có server-side metrics, có thể đếm các attempt server đã nhận. Nhưng con số đó bỏ sót attempts thất bại trước khi request tới server. Đặt tên là server.calls.completed hoặc server.attempts.observed, không gọi nó là tổng client attempts.

Không viết ClientInterceptor rồi tăng attempt counter ở mỗi sendMessage hoặc onClose mà không xác minh retry layer. Một logical call có thể chỉ gọi interceptor một lần dù transport thực hiện nhiều attempts.

## 10. Retry amplification và hiệu quả retry

Retry làm tăng tải lên server. Một chỉ số hữu ích là số attempts trên mỗi logical call:

\[
\text{attempts per call} =
\frac{\text{client attempt count}}{\text{logical call count}}
\]

Nếu tỷ lệ gần 1, phần lớn call hoàn tất trong attempt đầu. Nếu tăng lên 1.8, trung bình mỗi logical call tạo gần hai attempts trong cửa sổ đo. Đây là dấu hiệu retry amplification, cần xem cùng final success rate và latency.

Các chỉ số bổ sung:

- Retry rate: số retries mỗi giây theo service/method.
- Retry ratio: số retries chia logical calls.
- Retry success ratio: tỷ lệ logical calls cuối cùng OK trong nhóm đã có retry.
- Retry exhaustion: số logical calls hết maxAttempts hoặc deadline trước khi thành công.
- Attempt error distribution: status của từng attempt.
- Final status distribution: status cuối caller nhận.

Không kết luận retry tốt chỉ vì final success rate cao. Retry có thể che giấu một instance lỗi nhưng đồng thời nhân tải và kéo dài p99. Theo dõi cả attempts/call, final status và logical-call duration.

## 11. Prometheus queries

Giả sử các counter custom được export với tên:

- grpc_client_calls_completed_total{final_status=...}
- grpc_client_attempts_started_total
- grpc_client_attempts_completed_total{attempt_status=...}
- grpc_client_call_retries_total

Final status rate:

~~~promql
sum by (service, method, final_status) (
  rate(grpc_client_calls_completed_total[5m])
)
~~~

Attempt rate:

~~~promql
sum by (service, method) (
  rate(grpc_client_attempts_started_total[5m])
)
~~~

Average attempts per logical call:

~~~promql
sum by (service, method) (
  rate(grpc_client_attempts_started_total[5m])
)
/
sum by (service, method) (
  rate(grpc_client_calls_started_total[5m])
)
~~~

Retry rate:

~~~promql
sum by (service, method) (
  rate(grpc_client_call_retries_total[5m])
)
~~~

Attempt UNAVAILABLE rate:

~~~promql
sum by (service, method) (
  rate(grpc_client_attempts_completed_total{attempt_status="UNAVAILABLE"}[5m])
)
~~~

Tên metric/label chỉ là ví dụ; thay bằng series thực tế do instrumentation/exporter tạo. Tử số và mẫu số phải cùng nguồn, cùng method, cùng cửa sổ và cùng semantics. Không chia server attempt count cho client logical call count rồi coi đó là số attempts chính xác nếu có traffic từ caller khác, nhiều client hoặc attempts không tới server.

## 12. Đọc attempt status cùng final status

| Attempt distribution | Final status | Diễn giải |
| --- | --- | --- |
| Hầu hết attempt OK | Hầu hết final OK | Service ổn định, ít retry. |
| Nhiều attempt UNAVAILABLE | Final OK vẫn cao | Retry đang che lỗi tạm thời; kiểm tra endpoint health và amplification. |
| Nhiều attempt UNAVAILABLE | Final UNAVAILABLE tăng | Retry không khôi phục được call; kiểm tra outage/capacity. |
| Attempt UNAVAILABLE rồi final DEADLINE_EXCEEDED | Caller hết ngân sách trong retry/backoff. | Kiểm tra deadline budget và latency phát hiện lỗi. |
| Attempt status tốt nhưng final CANCELLED tăng | Caller/parent hủy logical call. | Kiểm tra lifecycle caller và parent cancellation. |
| Attempt count/call tăng cùng p99 | Backoff và nhiều lần thử kéo dài call. | Xem retry policy, throttling và SLO. |

Một method có final status OK 99.9% nhưng trung bình 2.5 attempts/call vẫn có thể đang ở trạng thái suy giảm. Caller nhận thành công nhưng hệ thống đang tiêu tốn nhiều network, CPU và capacity hơn bình thường.

## 13. Retry và streaming RPC

Không áp dụng tư duy retry unary cho streaming một cách máy móc:

- Stream có thể đã gửi hoặc xử lý nhiều message trước khi lỗi.
- Client có thể đã nhận response headers hoặc message, khiến call committed.
- Phát lại toàn bộ request stream có thể tạo message trùng hoặc side effect trùng.
- Một stream đang mở không được load balancer di chuyển sang instance khác như một call mới.

Nếu cần phục hồi stream, thiết kế protocol resume: sequence number, cursor, acknowledgement hoặc resume token. Client mở một RPC mới từ vị trí đã xác nhận và server phải xử lý duplicate theo idempotency/deduplication. Metrics cần phân biệt retry attempt tự động của gRPC với application-level reconnect/resume; đây là hai cơ chế khác nhau.

## 14. Tracing: logical call và attempt spans

Trace có thể thể hiện một logical operation và các attempts con:

~~~text
Application operation
  └── gRPC logical call: Inventory.GetStock
        ├── attempt 1: UNAVAILABLE (instance A)
        └── attempt 2: OK (instance B)
~~~

Nếu instrumentation hỗ trợ attempt spans, ghi attempt number, endpoint/service instance và attempt status trong span attributes. Logical call span ghi final status, tổng duration và số retries. Server spans chỉ xuất hiện cho attempts thực sự tới server.

Không đưa attempt number, trace ID hoặc endpoint ephemeral vào metric labels có cardinality cao. Những thuộc tính này phù hợp với trace. Khi cần điều tra retry storm, dùng exemplar/trace link hoặc log có sampling để đi từ metric aggregate tới một logical call cụ thể.

## 15. Kiểm thử retry và final status

Integration test nên điều khiển server response theo attempt count. Ví dụ test service trả UNAVAILABLE ở lần đầu rồi thành công ở lần sau:

~~~java
final class RetryTestInventoryService
        extends InventoryGrpc.InventoryImplBase {

    final AtomicInteger receivedCalls = new AtomicInteger();

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> responseObserver) {
        int attempt = receivedCalls.incrementAndGet();
        if (attempt == 1) {
            responseObserver.onError(
                    Status.UNAVAILABLE
                            .withDescription("temporary test failure")
                            .asRuntimeException());
            return;
        }

        responseObserver.onNext(StockReply.newBuilder()
                .setAvailableUnits(7)
                .build());
        responseObserver.onCompleted();
    }
}
~~~

Với retry policy cho phép UNAVAILABLE, test gọi method một lần và xác minh client nhận response thành công, trong khi server fixture đã nhận hai RPC attempts. Cần cấu hình service config trên channel và dùng method name khớp với Protobuf service.

Ma trận kiểm thử nên gồm:

1. **Retry thành công:** attempt đầu UNAVAILABLE, attempt sau OK; một logical call, nhiều server attempts, final status OK.
2. **Retry cạn:** mọi attempt trả UNAVAILABLE; số attempts không vượt maxAttempts và final status là lỗi cuối theo retry semantics.
3. **Deadline trong backoff:** deadline hết trước attempt tiếp theo; final status DEADLINE_EXCEEDED.
4. **Status không retryable:** INVALID_ARGUMENT hoặc PERMISSION_DENIED; chỉ một attempt theo policy.
5. **Caller cancel:** hủy logical call trong backoff; không tiếp tục tạo attempt mới.
6. **Commitment:** sau khi response headers đã được chuyển tới caller, xác minh không giả định call tiếp tục retry.
7. **Retry buffer/stream:** kiểm tra giới hạn buffering và semantics khi request stream đã phát message.
8. **Idempotency:** gửi cùng operation key qua nhiều attempts; xác minh side effect nghiệp vụ chỉ xảy ra một lần.
9. **Metrics:** logical call count tăng một, attempts count phản ánh số lần thử, final status chỉ ghi một lần.

Không dùng Thread.sleep để đoán lúc retry xảy ra. Dùng latch, attempt counter, test server có trạng thái xác định và deadline hữu hạn. Backoff thực tế phụ thuộc cấu hình/runtime nên không assert một thời điểm chính xác tới millisecond.

## 16. Cardinality và bảo mật telemetry

Các metric labels nên chỉ chứa service, method, final_status hoặc attempt_status với tập giá trị hữu hạn. Tránh:

- Attempt ID hoặc retry sequence number.
- Request ID, trace ID, span ID.
- User/account/order/tenant ID.
- Exception message, status description hoặc raw metadata.
- Endpoint hostname/IP ephemeral nếu số instance thay đổi liên tục.

Không ghi credential, authorization metadata hoặc payload nhạy cảm trong span/log khi phân tích retry. Có thể ghi endpoint logical name và instance identity đã được chuẩn hóa nếu chính sách cardinality cho phép; chi tiết từng instance nên ưu tiên trong trace.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Một logical call bị đếm thành nhiều call | Cộng server attempts vào client call count. | Tách logical calls, attempts và server-observed calls. |
| Client metric không thấy attempt UNAVAILABLE | ClientInterceptor chỉ thấy final onClose. | Dùng attempt-level instrumentation hoặc proxy telemetry. |
| Final OK nhưng hệ thống vẫn quá tải | Nhiều retries che lỗi và khuếch đại traffic. | Theo dõi attempts/call, retry rate và p99. |
| Mỗi retry có timeout đầy đủ mới | Đặt deadline riêng lại cho từng attempt. | Giữ deadline tổng của logical call. |
| Retry lặp side effect | Operation ghi không idempotent. | Idempotency key, deduplication và status lookup. |
| Streaming tự phát lại toàn bộ message | Nhầm retry unary với stream resume. | Thiết kế cursor/sequence/acknowledgement. |
| Attempt count thấp hơn server calls | Transparent retry hoặc nguồn traffic khác chưa được tính cùng cách. | Xác minh instrumentation boundary và nguồn metric. |
| Final status và attempt status bị gộp chung | Không định nghĩa semantics của metric. | Dùng label/tên riêng cho final_status và attempt_status. |

## 18. Bài tập thực hành

1. Cấu hình retry policy cho một unary read idempotent, giới hạn maxAttempts và retryable status.
2. Tạo server test double trả UNAVAILABLE ở attempt đầu rồi OK ở attempt sau.
3. Viết ClientInterceptor đếm logical call started và final status; xác minh một call chỉ có một final status.
4. Dùng instrumentation attempt-level để đếm attempt started, attempt status và retry count; ghi rõ nguồn/semantics.
5. Viết PromQL tính final status rate, attempt rate, retry rate và average attempts per logical call.
6. Kiểm thử retry exhaustion, deadline trong backoff, caller cancellation và status không retryable.
7. Kiểm tra idempotency khi server có thể commit side effect trước khi attempt lỗi.
8. Tạo trace thể hiện logical call với các attempt con và final status.

Sau bài này, bạn cần phân biệt một logical RPC với các attempt bên dưới, đọc được status trung gian và final status, hiểu deadline/commitment giới hạn retry, và thiết kế metrics/traces không đếm trùng. Khi theo dõi attempts trên mỗi logical call cùng final success rate và latency, đội vận hành có thể nhận ra retry amplification trước khi nó trở thành sự cố tải trong hệ thống Spring gRPC.

# Số stream đồng thời

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích số stream đồng thời và phân biệt nó với số connection, số message đang truyền và tổng số RPC.
- Phân biệt giới hạn HTTP/2 theo từng connection với giới hạn admission ở cấp server, service và tenant.
- Thiết kế giới hạn số streaming RPC đang hoạt động trong Spring gRPC.
- Giữ một slot trong toàn bộ vòng đời stream và giải phóng chính xác khi hoàn tất, lỗi hoặc cancellation.
- Kết hợp concurrency limit với deadline, idle timeout, flow control và backpressure.
- Chọn giới hạn dựa trên memory, CPU, downstream capacity và mức công bằng giữa tenant.
- Xử lý quá tải bằng status phù hợp và retry có backoff.
- Kiểm thử giới hạn, cleanup và isolation giữa các stream đồng thời.

## 1. Số stream đồng thời là gì?

Trong **SPRING_GRPC**, streaming RPC giữ một call mở trong khi client và server trao đổi nhiều message. Ba kiểu streaming là server-streaming, client-streaming và bidirectional streaming. Mỗi call đang mở chiếm tài nguyên trong suốt thời gian tồn tại: state của handler, buffer, subscription, callback, timer, reference tới principal, và có thể cả connection tới database hoặc broker.

**Số stream đồng thời** là số streaming RPC đang hoạt động tại cùng một thời điểm trên một phạm vi xác định. Phạm vi đó có thể là một connection, một server instance, một service, một tenant hoặc toàn hệ thống.

Đây là giới hạn quan trọng vì một stream có thể tồn tại lâu hơn nhiều so với unary RPC. Một client mở hàng nghìn stream rảnh hoặc gửi dữ liệu chậm có thể giữ tài nguyên mà không tạo nhiều throughput hữu ích. Nếu không có giới hạn, một nhóm caller có thể chiếm worker, memory, subscription và connection pool, khiến tenant khác không thể mở stream mới.

Cần phân biệt:

- **Concurrent connections:** số kết nối TCP/TLS đang mở.
- **Concurrent HTTP/2 streams:** số HTTP/2 stream đang hoạt động trên một connection.
- **Concurrent gRPC calls:** số RPC đang hoạt động; unary và streaming đều là RPC.
- **Concurrent application streams:** số streaming RPC mà ứng dụng cho phép chạy.
- **In-flight messages:** số message đang được gửi, nhận hoặc xử lý.
- **Total messages/bytes:** tổng lượng dữ liệu đã trao đổi trong một stream.

Một connection HTTP/2 có thể multiplex nhiều stream. Vì vậy, số connection thấp không có nghĩa số RPC đang hoạt động thấp; ngược lại, một stream có thể chứa rất nhiều message nhưng vẫn chỉ là một RPC.

## 2. Các lớp giới hạn concurrency

Không có một con số duy nhất bảo vệ mọi tầng. Hãy đặt giới hạn ở những phạm vi có ý nghĩa khác nhau:

| Phạm vi | Điều được giới hạn | Mục đích |
| --- | --- | --- |
| HTTP/2 connection | Stream/call đồng thời trên mỗi connection | Ngăn một connection chiếm quá nhiều slot |
| Server instance | Streaming RPC đang hoạt động trên một instance | Bảo vệ memory, CPU và tài nguyên cục bộ |
| Service/method | Stream cho một nhóm API cụ thể | Cô lập workload nặng hoặc nhạy cảm |
| Tenant/principal | Stream của một khách hàng hoặc caller | Công bằng và ngăn noisy neighbor |
| Cluster | Tổng stream trên nhiều instance | Bảo vệ downstream dùng chung và quota toàn hệ thống |

Một giới hạn per-connection không thay thế giới hạn toàn server. Nếu mỗi connection được mở tối đa 100 call và server có 200 connection, tổng số call lý thuyết vẫn có thể rất lớn. Tương tự, giới hạn global không bảo đảm fairness: một tenant có thể chiếm hết slot trước tenant khác.

Thiết kế tốt thường kết hợp transport cap, global admission, quota theo tenant và giới hạn riêng cho các method tiêu tốn nhiều tài nguyên.

## 3. Giới hạn HTTP/2 và grpc-java transport

HTTP/2 cho phép nhiều stream cùng chạy trên một connection. Peer có thể quảng bá giới hạn concurrent streams thông qua SETTINGS_MAX_CONCURRENT_STREAMS. Đây là giới hạn ở tầng HTTP/2 và có phạm vi theo connection.

Với Netty transport của grpc-java, server builder có API giới hạn số call đồng thời trên mỗi connection:

~~~java
import io.grpc.Server;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;

Server server = NettyServerBuilder.forPort(9090)
        .maxConcurrentCallsPerConnection(64)
        .build();
~~~

Giá trị 64 chỉ là ví dụ. API này là giới hạn theo connection và có thể tác động tới cả unary lẫn streaming call. Nó không phải quota tổng cho mọi connection, không phân biệt tenant và không thay thế admission ở application layer.

Transport và phiên bản grpc-java khác có thể cung cấp API khác nhau. Hãy kiểm tra builder thực tế mà ứng dụng sử dụng. Trong Spring gRPC, server thường do starter quản lý; cấu hình qua builder customizer/configurer hoặc extension point mà phiên bản starter hỗ trợ. Không giả định mọi starter có cùng property name. Xác minh cấu hình bằng integration test khởi động server của ứng dụng.

Transport limit bảo vệ tầng connection; application vẫn cần giới hạn số stream có thể giữ subscription, buffer hoặc tài nguyên nghiệp vụ.

## 4. Global admission control cho streaming RPC

Một cách đơn giản để giới hạn streaming RPC trên một server instance là dùng Semaphore. Khi stream bắt đầu, interceptor thử lấy một permit. Nếu không còn permit, server từ chối trước khi gọi handler. Permit được giữ cho tới khi RPC kết thúc hoặc bị hủy.

~~~java
import io.grpc.ForwardingServerCallListener;
import io.grpc.MethodDescriptor;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

public final class StreamingAdmissionInterceptor
        implements ServerInterceptor {

    private final Semaphore permits;

    public StreamingAdmissionInterceptor(int maxConcurrentStreams) {
        if (maxConcurrentStreams <= 0) {
            throw new IllegalArgumentException(
                    "maxConcurrentStreams must be positive");
        }
        this.permits = new Semaphore(maxConcurrentStreams);
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        MethodDescriptor.MethodType type =
                call.getMethodDescriptor().getType();

        boolean streaming =
                type != MethodDescriptor.MethodType.UNARY;

        if (!streaming) {
            return next.startCall(call, headers);
        }

        if (!permits.tryAcquire()) {
            call.close(
                    Status.RESOURCE_EXHAUSTED
                            .withDescription("Concurrent stream limit reached"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        AtomicBoolean released = new AtomicBoolean();

        Runnable releasePermit = () -> {
            if (released.compareAndSet(false, true)) {
                permits.release();
            }
        };

        try {
            ServerCall.Listener<ReqT> delegate =
                    next.startCall(call, headers);

            return new ForwardingServerCallListener
                    .SimpleForwardingServerCallListener<ReqT>(delegate) {

                @Override
                public void onComplete() {
                    try {
                        super.onComplete();
                    } finally {
                        releasePermit.run();
                    }
                }

                @Override
                public void onCancel() {
                    try {
                        super.onCancel();
                    } finally {
                        releasePermit.run();
                    }
                }
            };
        } catch (RuntimeException | Error failure) {
            releasePermit.run();
            throw failure;
        }
    }
}
~~~

Ví dụ chỉ đếm ba loại streaming RPC và bỏ qua unary. Permit được giữ trong toàn bộ vòng đời call, không chỉ trong lúc interceptor thực thi. AtomicBoolean bảo đảm release chỉ xảy ra một lần nếu terminal callbacks đến theo nhiều đường hoặc lỗi xảy ra khi khởi tạo handler.

Cần đặt admission interceptor sau authentication và method authorization để caller chưa xác thực hoặc không có quyền không chiếm stream slot. Thứ tự interceptor cụ thể phụ thuộc cách đăng ký trong grpc-java/Spring starter; hãy xác minh bằng integration test. Nếu cần giới hạn cả unary call, dùng một admission policy riêng thay vì bỏ qua UNARY.

Đây là ví dụ cho một instance. Mỗi replica có Semaphore riêng, nên tổng capacity của cluster xấp xỉ tổng permit của các replica. Nếu cần quota cluster-wide, cần một bộ điều phối quota dùng chung hoặc phân bổ ngân sách rõ ràng cho từng instance.

## 5. Giới hạn theo tenant và method

Global semaphore bảo vệ instance nhưng không bảo đảm công bằng. Một tenant có thể mở stream đến khi chiếm hết toàn bộ permit. Với hệ thống multi-tenant, nên áp dụng thêm:

- **Per-tenant cap:** giới hạn stream hoạt động của một tenant.
- **Per-principal cap:** ngăn một user/service identity mở quá nhiều stream.
- **Per-method cap:** giới hạn riêng method tiêu tốn nhiều memory hoặc downstream connection.
- **Global cap:** bảo vệ tổng tài nguyên của instance.

Một admission controller có thể nhận principal, full method name và trả về lease:

~~~java
public interface StreamAdmissionController {

    StreamLease tryAcquire(
            String tenantId,
            String subject,
            String fullMethodName);
}

public interface StreamLease extends AutoCloseable {
    @Override
    void close();
}
~~~

Lease đại diện cho một slot đã được cấp. Khi RPC hoàn tất, bị hủy hoặc handler khởi tạo thất bại, đóng lease để trả quota. Cách này cho phép triển khai global và per-tenant limit cùng lúc mà interceptor không cần biết chi tiết cấu trúc quota.

Nếu lưu limiter theo tenant trong ConcurrentHashMap, cần quản lý vòng đời entry. Không tạo map tăng vô hạn theo tenant ID rồi không bao giờ dọn. Có thể dùng quota service có TTL, cache giới hạn kích thước hoặc registry có cơ chế reference counting/eviction an toàn. Với quota phân tán, cần xử lý timeout, partition và việc release lease khi process bị crash.

Không lấy tenant ID từ metadata hoặc message rồi tin trực tiếp. Tenant scope phải được xác minh từ principal/policy; nếu stream cho phép chọn tenant, kiểm tra membership trước khi xin quota tenant đó.

## 6. Chọn giới hạn từ ngân sách tài nguyên

Không chọn concurrency bằng cách lấy một con số tùy ý hoặc dựa riêng vào số connection. Hãy ước lượng tài nguyên mỗi stream và ngân sách còn lại của instance.

Các thành phần thường chiếm tài nguyên:

- Principal, state và object của handler.
- Inbound/outbound buffer và message đang chờ.
- Subscription tới broker, database change stream hoặc event source.
- Connection hoặc cursor downstream.
- Scheduled task, heartbeat và timer.
- Executor task và callback.
- Response queue, compression buffer và telemetry state.

Một mô hình ước lượng đơn giản:

\[
N_{\text{memory}} =
\left\lfloor
\frac{M_{\text{budget}}}
{M_{\text{per-stream, peak}}}
\right\rfloor
\]

Trong đó M_budget là memory thực sự có thể dành cho streaming sau khi trừ heap nền, cache, unary workload và headroom; M_per-stream,peak là memory đỉnh đo được cho một stream theo workload thực tế.

Capacity cuối cùng nên là giới hạn nhỏ nhất trong các ngân sách:

\[
N_{\text{safe}} =
\min(N_{\text{memory}}, N_{\text{CPU}},
N_{\text{downstream}}, N_{\text{transport}}, N_{\text{operational}})
\]

Đây là mô hình lập kế hoạch, không phải công thức thay thế load test. Stream rảnh và stream đang xử lý payload lớn có thể tiêu thụ tài nguyên rất khác nhau. Nếu có nhiều nhóm method, cần capacity riêng hoặc weighted admission để stream nặng không chiếm cùng ngân sách với stream nhẹ.

Đo p95/p99 memory, CPU, queue depth, downstream connection usage và latency khi số stream tăng dần. Giữ headroom cho traffic burst, reconnect và hoạt động quản trị.

## 7. Stream lâu cần deadline, idle timeout và maximum lifetime

Giới hạn số stream đồng thời không đủ nếu một stream có thể tồn tại vô hạn. Stream rảnh có thể giữ permit và subscription dù không còn trao đổi message.

Nên kết hợp:

- **RPC deadline:** giới hạn tổng thời gian call theo contract.
- **Idle timeout:** kết thúc stream không có hoạt động trong khoảng thời gian quy định.
- **Maximum stream lifetime:** buộc client mở lại stream định kỳ để làm mới credential/policy và phân phối lại tải.
- **Heartbeat:** chỉ dùng khi cần phát hiện connection/peer còn hoạt động; heartbeat không thay thế deadline.
- **Cancellation:** giải phóng công việc ngay khi client hủy hoặc server quyết định dừng.

Không đặt deadline quá ngắn cho stream vốn được thiết kế dài hạn. Có thể dùng maximum lifetime có kiểm soát và cơ chế resume bằng cursor/sequence để client reconnect mà không mất dữ liệu.

Khi stream bị giới hạn lifetime, tài liệu API cần quy định client phải reconnect, cách resume và cách xử lý message cuối cùng đã commit. Không âm thầm cắt stream mà không có cursor hoặc semantics retry.

## 8. Flow control khác giới hạn số stream

Flow control điều tiết lượng message đang truyền hoặc chờ xử lý trong một stream. Nó không giới hạn số RPC đang mở.

Ví dụ, một client có thể mở 500 stream, mỗi stream chỉ gửi một message nhỏ mỗi phút. Flow control không ngăn được 500 stream đó chiếm 500 bộ state và subscription. Ngược lại, một stream duy nhất có thể gửi message quá nhanh và làm đầy queue nếu ứng dụng không áp backpressure.

Cần kết hợp:

| Cơ chế | Bảo vệ |
| --- | --- |
| Concurrent stream cap | Số RPC streaming đang mở |
| Inbound/outbound flow control | Số message đang được truyền/nhận |
| Bounded queue | Số message chờ application xử lý |
| Message-size limit | Kích thước từng message |
| Total bytes/messages quota | Tổng dữ liệu của stream |
| Rate limit | Tốc độ message/byte |
| Deadline/idle timeout | Thời gian giữ tài nguyên |

Ở outbound streaming, ServerCallStreamObserver có thể cung cấp isReady và on-ready handler để producer chỉ phát khi transport sẵn sàng. Ở inbound streaming, manual flow control cho phép yêu cầu số message tiếp theo có kiểm soát. Dù dùng cơ chế nào, queue phải có giới hạn và cancellation phải dừng producer.

## 9. Từ chối khi hết slot và client retry

Khi global hoặc tenant admission hết slot, server có thể từ chối call mới bằng **RESOURCE_EXHAUSTED**. Đây là tình trạng quota/tài nguyên đã đạt giới hạn; không dùng PERMISSION_DENIED vì caller không nhất thiết thiếu quyền.

Client nên:

- Retry có giới hạn với exponential backoff và jitter nếu RPC có thể mở lại an toàn.
- Tôn trọng RetryInfo hoặc retry-after nếu API cung cấp.
- Không retry liên tục trong vòng lặp nhanh vì sẽ làm tình trạng quá tải nặng hơn.
- Dùng cursor/sequence để resume stream sau reconnect.
- Dùng idempotency key cho command có side effect.
- Phân biệt resource exhaustion với UNAVAILABLE, authentication failure và permission denial.

Không phải mọi streaming RPC đều có thể retry từ đầu. Nếu client-streaming đã gửi một phần dữ liệu, mở stream mới có thể tạo bản ghi trùng hoặc bỏ sót message. Contract cần xác định checkpoint, sequence, deduplication và semantics commit.

Admission control cũng nên có chính sách chờ ngắn nếu phù hợp, nhưng không giữ một lượng lớn request pending trong memory. Thường từ chối sớm và để client backoff dễ kiểm soát hơn hàng đợi vô hạn.

## 10. Cleanup và release permit đúng một lần

Permit chỉ có ích nếu được trả lại trong mọi terminal path. Các đường kết thúc cần tính đến:

- Client hoàn tất request và server hoàn tất response.
- Client hủy stream.
- Deadline hết hoặc transport đóng connection.
- Application gặp lỗi.
- Authorization bị thu hồi.
- Downstream subscription lỗi.
- Handler không khởi tạo được sau khi đã acquire permit.

Dùng lease có close idempotent hoặc AtomicBoolean để tránh double release. Đặt cleanup ở finally hoặc terminal callback phù hợp. Khi handler setup thất bại sau khi acquire, phải release ngay; nếu không, permit bị rò và server dần từ chối mọi stream mới dù không còn stream hoạt động.

Không release permit chỉ vì server đã gửi response đầu tiên. Với streaming, call vẫn mở cho tới khi kết thúc/cancel. Cũng không giữ permit sau terminal event trong lúc thực hiện công việc cleanup chậm; giải phóng slot admission trước hoặc sau cleanup theo định nghĩa tài nguyên được giới hạn, nhưng phải nhất quán và không để cleanup chạy vô hạn.

## 11. Quan sát số stream đồng thời

Theo dõi các chỉ số theo instance, service/method và tenant ở mức cardinality phù hợp:

- Active streaming RPCs hiện tại.
- Stream admission success/rejection.
- Số permit còn lại và thời gian chờ admission nếu có.
- Active stream duration p50/p95/p99.
- Stream kết thúc theo status: OK, CANCELLED, DEADLINE_EXCEEDED, RESOURCE_EXHAUSTED.
- Số stream theo method type: server, client hoặc bidi.
- Số stream theo tenant tier/quota group.
- Buffer/queue depth, memory, CPU và downstream pool utilization.
- Số stream bị đóng do idle timeout, max lifetime hoặc revocation.

Metric active stream phải tăng khi permit được cấp và giảm đúng một lần khi lease được release. Nếu metric tăng liên tục dù traffic ổn định, có thể có listener terminal path bị bỏ sót hoặc cleanup không chạy.

Không đưa raw user ID, tenant ID tùy ý hoặc stream ID vào metric label nếu tạo cardinality không kiểm soát. Dùng log/trace có redaction để điều tra từng call; metrics nên dùng method, status và quota tier.

## 12. Kiểm thử concurrency limit

Test phải xác minh giới hạn được áp dụng trong toàn bộ vòng đời stream, không chỉ thời điểm gọi interceptor.

Giả sử server cho phép tối đa hai streaming RPC:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Mở stream thứ nhất | Được cấp slot |
| Mở stream thứ hai | Được cấp slot |
| Mở stream thứ ba khi hai stream còn mở | Bị từ chối RESOURCE_EXHAUSTED |
| Hoàn tất một stream | Slot được trả |
| Mở stream mới sau khi slot được trả | Được chấp nhận |
| Client cancel một stream | Slot được trả đúng một lần |
| Handler setup ném exception sau acquire | Slot được trả |
| Unary RPC khi policy chỉ giới hạn streaming | Không tiêu thụ streaming permit |
| Tenant A đạt quota riêng | Tenant B vẫn có thể mở stream nếu global capacity còn |
| Hai stream cùng kết thúc gần nhau | Không double release hoặc permit âm |

Dùng latch/barrier trong in-process gRPC integration test để giữ stream mở có chủ đích. Mở đủ số stream để chiếm hết permit, thử mở thêm một stream và assert status. Sau đó hoàn tất/cancel một stream rồi thử lại.

Bổ sung test:

1. Global cap được giữ qua nhiều connection, không chỉ một channel.
2. Per-tenant cap không cho một tenant chiếm hết capacity.
3. Listener onComplete và onCancel đều release idempotent.
4. Stream bị cancel giải phóng subscription và buffer.
5. Deadline/idle timeout/max lifetime kết thúc stream và trả slot.
6. Application context Spring thực sự đăng ký admission interceptor.
7. Metrics active stream tăng/giảm đúng theo vòng đời.

Không dùng Thread.sleep để đồng bộ test concurrency. Dùng CountDownLatch, barrier hoặc test observer điều khiển thời điểm stream mở/đóng.

## 13. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ giới hạn số connection | Một connection multiplex quá nhiều stream | Thêm per-connection và application stream cap |
| Chỉ cấu hình per-connection cap | Nhiều connection vượt tổng capacity | Thêm global admission |
| Dùng global cap mà không có tenant quota | Một tenant chiếm toàn bộ slot | Thêm per-tenant/principal fairness |
| Acquire permit nhưng không release khi cancel | Permit leak, stream mới bị từ chối oan | Release ở onComplete/onCancel và setup failure |
| Release ngay sau response đầu tiên | Stream còn mở nhưng slot đã được cấp lại | Giữ permit đến terminal event |
| Dùng flow control thay concurrency cap | Nhiều stream rảnh vẫn chiếm tài nguyên | Giới hạn số call mở độc lập |
| Không giới hạn stream lifetime | Stream rảnh giữ slot vô hạn | Deadline, idle timeout và maximum lifetime |
| Retry ngay khi RESOURCE_EXHAUSTED | Tăng áp lực khi server quá tải | Backoff, jitter và resume |
| Đếm bằng field mutable không đồng bộ | Race, âm hoặc vượt cap | Semaphore/atomic lease và terminal guard |
| Chỉ test một connection | Bỏ sót global capacity qua nhiều connection | Test nhiều channel/connection và cùng server |

## 14. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo một server-streaming method và một bidirectional streaming method trong Spring gRPC.
2. Cấu hình transport per-connection call cap nếu grpc-java transport/version hỗ trợ.
3. Viết admission interceptor dùng Semaphore hoặc StreamAdmissionController để giới hạn streaming RPC trên một instance.
4. Đăng ký interceptor sau authentication và method authorization; xác minh thứ tự bằng integration test.
5. Bọc ServerCall.Listener để release lease khi onComplete, onCancel hoặc handler setup thất bại.
6. Thêm quota per-tenant và xác minh một tenant không chiếm hết global capacity.
7. Thêm maximum stream lifetime, cancellation cleanup và flow control/bounded queue.
8. Viết in-process test cho hai slot, stream thứ ba bị RESOURCE_EXHAUSTED, slot được trả sau complete/cancel và Spring wiring.

### Câu hỏi tự kiểm tra

**1. Số stream đồng thời là gì?**  
Số streaming RPC đang hoạt động cùng lúc trong một phạm vi như connection, instance, service hoặc tenant.

**2. Vì sao giới hạn connection không đủ?**  
HTTP/2 multiplex nhiều stream trên một connection; một connection có thể giữ nhiều RPC đồng thời.

**3. maxConcurrentCallsPerConnection có phải global cap không?**  
Không. Đây là giới hạn theo connection của Netty transport; nhiều connection vẫn có thể tạo tổng call lớn.

**4. Vì sao cần application admission control?**  
Để giới hạn tổng stream theo instance/service/tenant và bảo vệ subscription, memory, worker cùng downstream resource.

**5. Khi nào release stream permit?**  
Khi RPC hoàn tất, bị hủy hoặc setup thất bại; release phải idempotent và chỉ xảy ra một lần.

**6. Flow control có thay concurrency cap không?**  
Không. Flow control giới hạn message đang truyền; concurrency cap giới hạn số RPC đang mở.

**7. Status nào phù hợp khi hết stream slot?**  
RESOURCE_EXHAUSTED, vì server đã đạt giới hạn tài nguyên/quota.

**8. Làm sao tránh một tenant chiếm toàn bộ stream slot?**  
Kết hợp global cap với per-tenant/principal quota và admission fairness.

## Tổng kết

Số stream đồng thời phải được kiểm soát ở nhiều phạm vi. HTTP/2 và Netty có thể giới hạn call trên từng connection, nhưng không bảo vệ tổng capacity của server hoặc fairness giữa tenant. Spring gRPC cần application admission control để cấp và thu hồi slot trong toàn bộ vòng đời streaming RPC; release phải an toàn ở complete, cancel và setup failure. Chọn capacity từ memory, CPU và downstream budget, đồng thời áp quota tenant, deadline, idle timeout, flow control và bounded queue. Khi hết slot, từ chối sớm bằng RESOURCE_EXHAUSTED và để client retry có backoff/resume. Integration test phải giữ stream mở, vượt ngưỡng, đóng/cancel và chứng minh slot được trả chính xác.


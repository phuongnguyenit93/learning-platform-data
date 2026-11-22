# Kiểm tra metadata và deadline

Metadata và deadline là hai phần quan trọng của gRPC call contract. Metadata mang thông tin đi kèm RPC như request ID, tenant hoặc credential; deadline giới hạn thời gian caller chờ kết quả và được truyền qua các lời gọi tiếp theo. Kiểm thử cần xác minh metadata thực sự tới server, được xử lý theo policy, không rò giữa các call; đồng thời deadline được giữ nguyên qua stub/interceptor, kết thúc đúng status và kích hoạt cancellation khi hết hạn.

Trong Spring gRPC, có thể kiểm tra logic bằng generated stub, in-process server/channel và interceptor. Các test này xác minh call pipeline trong JVM. Spring context test bổ sung việc channel/stub bean có gắn interceptor thật hay không; TCP/TLS integration test xác minh metadata và deadline qua transport, proxy hoặc service mesh thực tế.

## 1. Metadata và deadline trong một RPC

Metadata là tập header/trailer ở tầng gRPC, tách khỏi Protobuf request message. Nó thường chứa:

- Request ID hoặc correlation ID để nối log/trace giữa các service.
- Authorization token hoặc thông tin xác thực do credential provider cấp.
- Tenant hoặc routing hint đã được xác minh theo policy.
- Trace context theo chuẩn observability của hệ thống.

Deadline biểu thị thời điểm muộn nhất caller chấp nhận kết quả. Client có thể đặt deadline trên stub hoặc call options; server nhận deadline trong gRPC Context và nên dừng công việc khi call bị cancel. Deadline có thể được truyền tiếp qua downstream RPC để toàn bộ request chain cùng tuân thủ ngân sách thời gian.

Metadata không phải payload nghiệp vụ, còn deadline không phải timeout cho toàn bộ process. Mỗi RPC có metadata và deadline riêng; không lưu chúng trong mutable field dùng chung giữa nhiều call.

## 2. Định nghĩa metadata key đúng cách

grpc-java dùng Metadata.Key với marshaller tương ứng:

```java
import io.grpc.Metadata;

static final Metadata.Key<String> REQUEST_ID =
    Metadata.Key.of(
        "x-request-id",
        Metadata.ASCII_STRING_MARSHALLER);

static final Metadata.Key<String> TENANT_ID =
    Metadata.Key.of(
        "x-tenant-id",
        Metadata.ASCII_STRING_MARSHALLER);

static final Metadata.Key<byte[]> SIGNATURE =
    Metadata.Key.of(
        "x-payload-signature-bin",
        Metadata.BINARY_BYTE_MARSHALLER);
```

Tên key metadata phải viết thường. Key binary có hậu tố -bin và dùng binary marshaller; không dùng ASCII marshaller để truyền byte array. Tránh dùng các header dành riêng cho gRPC transport hoặc tự đặt header có thể xung đột với proxy.

Metadata có thể chứa nhiều giá trị cho cùng một key. Nếu contract yêu cầu một giá trị duy nhất, quy định rõ hành vi khi key đã tồn tại: giữ giá trị caller gửi, thay thế bằng giá trị do gateway tạo, hay từ chối request. Đừng vô tình thêm giá trị thứ hai rồi để client/server diễn giải khác nhau.

## 3. Gắn metadata bằng ClientInterceptor

Client interceptor là nơi phù hợp để gắn metadata dùng chung cho các RPC. Ví dụ sau chỉ tạo request ID khi caller chưa cung cấp:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.function.Supplier;

final class RequestMetadataInterceptor implements ClientInterceptor {
    private final Supplier<String> requestIdSupplier;
    private final Supplier<String> tenantSupplier;

    RequestMetadataInterceptor(
            Supplier<String> requestIdSupplier,
            Supplier<String> tenantSupplier) {
        this.requestIdSupplier = requestIdSupplier;
        this.tenantSupplier = tenantSupplier;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {
        ClientCall<ReqT, RespT> delegate =
            next.newCall(method, callOptions);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(delegate) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                if (headers.get(REQUEST_ID) == null) {
                    headers.put(REQUEST_ID, requestIdSupplier.get());
                }
                if (headers.get(TENANT_ID) == null) {
                    headers.put(TENANT_ID, tenantSupplier.get());
                }
                super.start(responseListener, headers);
            }
        };
    }
}
```

Supplier được gọi theo từng call để tránh dùng một request ID cố định cho mọi request. Nếu request ID đã được gateway tin cậy tạo, interceptor có thể preserve; nếu caller không thuộc trust boundary, gateway nên xác minh hoặc replace ID theo policy.

Không lưu Metadata hoặc headers vào field interceptor singleton. Interceptor thường được dùng đồng thời bởi nhiều call; dữ liệu riêng call phải nằm trong biến local. Cũng không log bearer token, signature hoặc metadata nhạy cảm.

## 4. Kiểm thử metadata bằng in-process server

Để chứng minh header đã đi qua client call pipeline tới server, gắn server interceptor ghi nhận giá trị:

```java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<String> receivedRequestId = new AtomicReference<>();
AtomicReference<String> receivedTenant = new AtomicReference<>();

ServerInterceptor captureMetadata = new ServerInterceptor() {
    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {
        receivedRequestId.set(headers.get(REQUEST_ID));
        receivedTenant.set(headers.get(TENANT_ID));
        return next.startCall(call, headers);
    }
};
```

Dùng interceptor này khi đăng ký service definition trên in-process server, rồi gọi bằng generated stub qua channel đã gắn RequestMetadataInterceptor. Sau khi RPC hoàn tất, assertion trên thread test xác minh server nhận đúng request ID và tenant.

Đây là integration test trong JVM: nó xác minh metadata thực sự qua client/server call pipeline, thay vì chỉ gọi trực tiếp phương thức interceptor. Với nhiều call đồng thời, thay AtomicReference bằng queue hoặc map keyed by request ID để không ghi đè kết quả của call khác.

## 5. Dựng fixture test và gọi stub

Một fixture JUnit 5 có thể tạo server name riêng, đăng ký service cùng server interceptor, rồi tạo channel có client interceptor:

```java
String serverName = InProcessServerBuilder.generateName();

ServerServiceDefinition observedService =
    ServerInterceptors.intercept(
        new GreeterService().bindService(),
        captureMetadata);

Server server = InProcessServerBuilder.forName(serverName)
    .addService(observedService)
    .build()
    .start();

ManagedChannel baseChannel = InProcessChannelBuilder
    .forName(serverName)
    .build();

Channel interceptedChannel = ClientInterceptors.intercept(
    baseChannel,
    new RequestMetadataInterceptor(
        () -> "req-test-42",
        () -> "tenant-test"));

GreeterGrpc.GreeterBlockingStub stub =
    GreeterGrpc.newBlockingStub(interceptedChannel);
```

Sau khi gọi RPC, kiểm tra response và metadata server đã nhận. Đóng channel rồi server trong teardown, đặt timeout hữu hạn cho shutdown. Tên server phải mới cho mỗi test để fixture không kết nối nhầm server khác.

Test này không cần TCP port. Nó vẫn kiểm tra generated stub, method dispatch và interceptor chain. Muốn kiểm tra Spring tự đăng ký interceptor bean vào channel thật, dùng Spring context test riêng.

## 6. Kiểm thử generate, preserve và replace metadata

Với request ID hoặc tenant header, cần khóa policy bằng các ca:

| Metadata caller gửi | Policy | Kết quả cần xác minh |
| --- | --- | --- |
| Không có request ID | Generate | Server nhận ID do interceptor tạo |
| Có request ID hợp lệ từ gateway tin cậy | Preserve | Server nhận đúng ID ban đầu |
| Có request ID không hợp lệ | Reject hoặc replace | Hành vi được định nghĩa rõ |
| Có nhiều giá trị cho key single-valued | Reject hoặc chọn policy rõ | Không diễn giải ngầm |
| Hai call đồng thời | Generate per call | ID của call này không xuất hiện ở call kia |

Để replace header, xóa giá trị cũ bằng headers.removeAll(REQUEST_ID) rồi thêm giá trị mới. Để preserve, chỉ thêm khi headers.get(REQUEST_ID) là null. Nếu cần reject, client interceptor có thể báo lỗi trước khi gửi call; server vẫn phải xác minh dữ liệu caller không đáng tin.

Không dùng request ID làm credential. Tenant ID cũng không tự chứng minh caller được phép truy cập tenant đó; server phải liên kết tenant với principal đã xác thực.

## 7. Đặt deadline trên generated stub

Blocking stub hỗ trợ đặt deadline cho call:

```java
GreeterGrpc.GreeterBlockingStub boundedStub =
    stub.withDeadlineAfter(500, TimeUnit.MILLISECONDS);

HelloReply reply = boundedStub.sayHello(request);
```

withDeadlineAfter trả về một stub cấu hình mới, không thay đổi stub gốc. Deadline được tạo tại thời điểm gọi withDeadlineAfter, vì vậy hãy tạo bounded stub ngay trước từng RPC thay vì giữ một stub có deadline hữu hạn để tái sử dụng cho nhiều call. gRPC biểu diễn deadline dưới dạng thời điểm; khi deadline được truyền qua các hop, thời gian đã tiêu thụ không được cộng lại thành một timeout mới đầy đủ.

Async stub cũng nhận deadline theo cách tương tự:

```java
GreeterGrpc.GreeterStub boundedAsyncStub =
    asyncStub.withDeadlineAfter(500, TimeUnit.MILLISECONDS);

boundedAsyncStub.sayHello(request, responseObserver);
```

Khi deadline hết hạn trước khi RPC hoàn tất, caller nhận status DEADLINE_EXCEEDED. Nếu server hoàn tất trước deadline, caller nhận response bình thường. Đặt deadline hữu hạn cho test để suite không chờ vô hạn khi handler bị treo.

## 8. Deadline được truyền tới server và downstream

Server có thể đọc deadline hiện tại qua gRPC Context:

```java
import io.grpc.Context;
import io.grpc.Deadline;

Deadline deadline = Context.current().getDeadline();
if (deadline != null && deadline.isExpired()) {
    // Call đã hết ngân sách thời gian.
}
```

Không tự tạo timeout mới dài hơn deadline còn lại. Khi gọi downstream, truyền tiếp ngân sách còn lại hoặc deadline tương ứng để toàn request chain kết thúc đúng hạn. Nếu downstream không hỗ trợ cancellation, application cần timeout và cleanup phù hợp để tránh công việc chạy tiếp sau khi caller đã bỏ chờ.

Deadline khác timeout cấu hình kết nối. Connect timeout điều khiển việc thiết lập kết nối; RPC deadline giới hạn thời gian cho một call, bao gồm queueing, xử lý và response. Một channel kết nối thành công không đảm bảo RPC hoàn tất trước deadline.

## 9. Kiểm thử deadline và cancellation có kiểm soát

Tránh dùng Thread.sleep() để tạo một handler chậm. Có thể dùng scheduler để trì hoãn response và cancellation listener để xác minh server nhận cancellation:

```java
import io.grpc.Context;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

final class DelayedGreeterService extends GreeterGrpc.GreeterImplBase {
    private final ScheduledExecutorService scheduler;
    private final CountDownLatch cancelled;

    DelayedGreeterService(
            ScheduledExecutorService scheduler,
            CountDownLatch cancelled) {
        this.scheduler = scheduler;
        this.cancelled = cancelled;
    }

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> observer) {
        ScheduledFuture<?> responseTask = scheduler.schedule(() -> {
            observer.onNext(HelloReply.newBuilder()
                .setMessage("Hello, " + request.getName())
                .build());
            observer.onCompleted();
        }, 2, TimeUnit.SECONDS);

        Context.current().addListener(context -> {
            responseTask.cancel(false);
            cancelled.countDown();
        }, Runnable::run);
    }
}
```

Test gọi blocking stub với deadline ngắn hơn thời gian response dự kiến:

```java
StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> stub.withDeadlineAfter(100, TimeUnit.MILLISECONDS)
        .sayHello(request));

assertEquals(
    Status.Code.DEADLINE_EXCEEDED,
    error.getStatus().getCode());
assertTrue(cancelled.await(1, TimeUnit.SECONDS));
```

Ví dụ cần chạy server handler trên executor phù hợp và quản lý scheduler trong fixture. Nếu dùng directExecutor cùng một handler chặn, client timer/call có thể không được kiểm tra theo cách mong muốn. Ở ví dụ này handler trả về nhanh sau khi lên lịch response; cancellation listener hủy scheduled task để không gửi response muộn.

Test nên xác minh cả status phía client và cancellation phía server. Chỉ assert DEADLINE_EXCEEDED chưa chứng minh server đã dừng công việc; scheduled task hoặc downstream operation có thể tiếp tục chạy và tiêu tốn tài nguyên.

## 10. Kết hợp metadata và deadline trong cùng test

Một RPC production thường cần cả request ID, tenant, credential và deadline. Test tích hợp nên xác minh:

1. Client interceptor tạo hoặc preserve request ID theo policy.
2. Metadata tenant/credential được gửi đúng và server xác minh trước khi dùng.
3. Server handler nhận principal/context mong đợi.
4. Deadline từ stub không bị client interceptor làm mất.
5. Khi deadline hết hạn, client nhận DEADLINE_EXCEEDED.
6. Server nhận cancellation và dừng tác vụ có thể hủy.
7. Không ghi token hoặc metadata nhạy cảm vào log.

Interceptor phải gọi next.newCall(method, callOptions) với đúng CallOptions nhận được. Nếu tạo call bằng CallOptions mặc định, deadline của stub có thể bị mất. Test deadline qua channel có interceptor là cách phát hiện lỗi này.

## 11. Spring client wiring và transport boundary

Trong Spring gRPC, client channel thường được tạo qua bean hoặc client factory của starter. Để kiểm tra wiring:

- Khởi động Spring test context dùng cấu hình client như production.
- Xác minh channel/stub thực tế được tạo với client interceptor.
- Gọi RPC tới test server và kiểm tra metadata ở phía server.
- Đặt deadline qua stub, xác minh status khi handler chậm.
- Đóng channel khi context dừng nếu ứng dụng sở hữu channel lifecycle.

Không giả định mọi bean implement ClientInterceptor tự động được gắn vào mọi channel. Cơ chế đăng ký phụ thuộc phiên bản starter và cách channel được tạo. Test context phải gọi chính stub/channel mà application service sử dụng.

In-process test không xác minh HTTP/2 qua socket, TLS/mTLS, certificate, proxy, ingress, service mesh hoặc metadata limits do gateway áp dụng. Nếu hệ thống chạy qua các thành phần này, bổ sung TCP/TLS integration test từ đúng network boundary.

## 12. Ma trận kiểm thử và bài tập vận dụng

| Nhóm | Ca kiểm thử | Điều kiện PASS |
| --- | --- | --- |
| Metadata generate | Caller không gửi request ID | Server nhận ID mới |
| Metadata preserve | Caller gửi ID trusted | Server nhận đúng ID |
| Metadata replace/reject | Header sai policy | Hành vi đúng contract |
| Tenant | Tenant metadata không khớp principal | Server từ chối theo policy |
| Concurrency | Nhiều call với ID khác nhau | Không rò metadata |
| Deadline success | Handler trả trước deadline | Nhận response |
| Deadline exceeded | Handler trả sau deadline | Client nhận DEADLINE_EXCEEDED |
| Cancellation | Deadline/caller cancel | Server dừng tác vụ có thể hủy |
| CallOptions | Stub có deadline qua interceptor | Deadline vẫn được áp dụng |
| Error path | Server trả status/trailers | Client nhận nguyên status cần thiết |
| Spring wiring | Stub bean dùng channel cấu hình | Interceptor thực sự được gọi |
| Transport | TCP/TLS/proxy | Metadata và deadline hoạt động qua network thật |

**Bài tập:** OrderClient.GetOrder cần x-request-id, x-tenant-id và bearer token; deadline mặc định là 700 ms nhưng use case tìm kiếm chỉ cấp 250 ms. Gateway đã tạo request ID cho một số caller nội bộ.

1. Viết client interceptor tạo request ID nếu thiếu và preserve ID từ gateway tin cậy.
2. Gửi tenant và authorization metadata; xác minh server không tin tenant header nếu principal không được phép.
3. Viết in-process test để capture metadata phía server.
4. Xác minh stub có deadline 250 ms giữ nguyên deadline qua interceptor.
5. Dựng delayed handler bằng scheduler, kiểm tra DEADLINE_EXCEEDED và server cancellation.
6. Chạy nhiều call đồng thời để phát hiện rò request ID/tenant.
7. Viết Spring context test cho channel/stub bean và TCP/TLS test cho transport production.

**Câu hỏi tự kiểm tra:**

- Metadata khác Protobuf request message như thế nào?
- Khi nào dùng ASCII metadata key và khi nào dùng -bin?
- Vì sao request ID không phải credential?
- Client interceptor nên thêm metadata ở giai đoạn nào?
- Vì sao phải truyền nguyên CallOptions khi tạo ClientCall?
- Deadline khác connect timeout ra sao?
- Server đọc deadline từ đâu?
- Vì sao deadline exceeded cần kiểm tra cancellation phía server?
- Làm thế nào test metadata thực sự tới server thay vì chỉ test interceptor riêng lẻ?
- Những gì cần xác minh bằng Spring context và TCP/TLS integration test?

**Ghi nhớ:** Kiểm thử metadata phải xác minh generate/preserve/replace, tenant và credential theo policy, cùng việc header thực sự tới server. Kiểm thử deadline phải xác minh cả status DEADLINE_EXCEEDED lẫn cancellation và cleanup phía server. Giữ nguyên CallOptions qua interceptor, dùng in-process test cho call pipeline, Spring context test cho client wiring và TCP/TLS test cho transport thực tế.

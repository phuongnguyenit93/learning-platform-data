# Test blocking stub

Blocking stub là client API của grpc-java dành cho lời gọi đồng bộ: thread gọi method sẽ chờ cho tới khi nhận response, nhận status lỗi hoặc hết deadline. Khi kiểm thử Spring gRPC, blocking stub phù hợp để xác minh unary RPC và server-streaming RPC theo cách tuần tự, dễ đọc assertion. Test cần chứng minh cả kết quả nghiệp vụ lẫn hành vi đồng bộ: response đúng, status đúng, deadline được áp dụng và tài nguyên được giải phóng.

Generated blocking stub được tạo từ Protobuf service definition. Nó gọi server qua ManagedChannel; vì vậy có thể dùng in-process channel để test nhanh mà không mở TCP port. In-process test vẫn đi qua gRPC call pipeline, nhưng không xác minh TLS, HTTP/2 trên socket, ingress hoặc network policy.

## 1. Blocking stub hoạt động ra sao?

Khi gọi method trên blocking stub, caller bị chặn cho đến khi RPC kết thúc. Với unary RPC, method trả về một response message. Nếu RPC kết thúc bằng status khác OK, grpc-java ném StatusRuntimeException. Với server-streaming RPC, method trả về Iterator của response; việc gọi hasNext/next có thể tiếp tục chờ message hoặc kết thúc stream.

```text
Test thread
    |
    | blockingStub.getOrder(request)
    v
ManagedChannel
    |
    v
gRPC server method
    |
    +---- onNext(response) + onCompleted()
    |
    v
Blocking stub returns response
    |
    v
JUnit assertions
```

Blocking stub giúp test tuyến tính, nhưng thread test phải chờ network/call completion. Không dùng nó trong event loop hoặc thread cần xử lý callback khác để tránh tự tạo deadlock hay cạn thread pool.

## 2. Những RPC nào có blocking stub?

Generated Java API thường cung cấp các loại stub:

| Stub | Cách gọi | Phù hợp |
| --- | --- | --- |
| Blocking stub | Method đồng bộ trả response hoặc iterator | Unary và server-streaming |
| Async stub | Nhận kết quả qua StreamObserver callback | Unary và mọi kiểu streaming |
| Future stub | Trả ListenableFuture cho unary | Unary call cần composition qua future |

Blocking stub hỗ trợ unary và server-streaming. Client-streaming và bidirectional-streaming cần gửi nhiều request theo luồng; chúng được thực hiện qua async stub với StreamObserver, không có method tương ứng trong blocking stub truyền thống.

Chọn stub theo contract của RPC. Không ép một client-streaming method thành nhiều unary call nếu điều đó thay đổi semantics, ordering hoặc transaction boundary.

## 3. Tạo in-process server và channel

Một test có thể tạo server name duy nhất, đăng ký service implementation rồi kết nối channel tới cùng tên:

```java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class GreeterBlockingStubTest {
    private Server server;
    private ManagedChannel channel;
    private GreeterGrpc.GreeterBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(new GreeterService())
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = GreeterGrpc.newBlockingStub(channel);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow()
                .awaitTermination(5, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow()
                .awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Server name phải mới cho từng test để tránh kết nối nhầm fixture. Đóng channel trước server và đặt timeout hữu hạn cho cleanup. Nếu server dùng executor do test tạo, shutdown executor trong teardown sau khi server đã dừng.

directExecutor() làm callback chạy trực tiếp trên thread gọi và hữu ích cho test đơn giản. Nó không mô phỏng scheduling production; các test về executor, context propagation hoặc blocking handler cần dùng executor phù hợp và được quản lý vòng đời.

## 4. Kiểm thử unary response

Giả sử proto khai báo method unary:

```proto
service Greeter {
  rpc SayHello(HelloRequest) returns (HelloReply);
}
```

Service trả đúng một response và hoàn tất:

```java
final class GreeterService extends GreeterGrpc.GreeterImplBase {
    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> observer) {
        HelloReply reply = HelloReply.newBuilder()
            .setMessage("Hello, " + request.getName())
            .build();
        observer.onNext(reply);
        observer.onCompleted();
    }
}
```

Test dùng blocking stub và kiểm tra field response:

```java
@Test
void returnsGreeting() {
    HelloRequest request = HelloRequest.newBuilder()
        .setName("Mai")
        .build();

    HelloReply reply = stub.sayHello(request);

    assertEquals("Hello, Mai", reply.getMessage());
}
```

Không chỉ kiểm tra rằng method trả về mà không ném exception. Assertion nên xác minh field có ý nghĩa với contract. Nếu service gọi repository hoặc application service, kiểm tra side effect cần thiết bằng fake/mock hoặc test database phù hợp.

## 5. Kiểm thử status lỗi

Nếu service từ chối request, blocking stub ném StatusRuntimeException. Kiểm tra status code để khóa contract lỗi:

```java
@Test
void rejectsBlankName() {
    HelloRequest request = HelloRequest.newBuilder()
        .setName(" ")
        .build();

    StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.sayHello(request));

    assertEquals(
        Status.Code.INVALID_ARGUMENT,
        error.getStatus().getCode());
}
```

Status thường cần kiểm thử:

| Điều kiện | Status |
| --- | --- |
| Request sai hoặc thiếu field theo validation | INVALID_ARGUMENT |
| Resource không tồn tại | NOT_FOUND |
| Credential thiếu hoặc sai | UNAUTHENTICATED |
| Principal không đủ quyền | PERMISSION_DENIED |
| Dependency tạm thời không khả dụng | UNAVAILABLE theo error mapping |
| Call vượt deadline | DEADLINE_EXCEEDED |

Chỉ assert description hoặc trailer khi chúng là một phần contract được công bố. Tránh phụ thuộc vào message nội bộ của exception vì nội dung đó có thể thay đổi mà không làm thay đổi semantics của status.

## 6. Đặt deadline cho blocking call

Một blocking call không nên chờ vô hạn. Dùng deadline trên stub:

```java
HelloReply reply = stub
    .withDeadlineAfter(300, TimeUnit.MILLISECONDS)
    .sayHello(request);
```

withDeadlineAfter() trả về một stub cấu hình call mới; channel gốc vẫn được tái sử dụng. Khi deadline hết hạn trước khi RPC hoàn tất, blocking call kết thúc bằng StatusRuntimeException với code DEADLINE_EXCEEDED.

Test deadline nên dùng service có thể điều khiển thời điểm hoàn tất, chẳng hạn CountDownLatch hoặc scheduler test. Tránh Thread.sleep() cố định vì CI có scheduling và tải khác máy phát triển. Server handler cần chạy trên executor khác với thread đang chờ ở client; nếu dùng directExecutor và handler chặn ngay trên call thread, test có thể không quan sát deadline đúng như dự kiến.

Một deadline test tốt xác minh:

- Client nhận DEADLINE_EXCEEDED trong khoảng thời gian có giới hạn.
- Công việc server nhận được cancellation signal nếu implementation hỗ trợ hủy.
- Không có side effect muộn ngoài contract sau khi caller đã timeout.
- Latch, executor, channel và server đều được giải phóng khi test kết thúc.

## 7. Kiểm thử server-streaming bằng blocking stub

Với server-streaming RPC, một request có thể tạo nhiều response. Blocking stub trả về Iterator:

```proto
service Greeter {
  rpc SayHelloMany(HelloRequest) returns (stream HelloReply);
}
```

Ví dụ test:

```java
@Test
void receivesAllServerStreamMessages() {
    HelloRequest request = HelloRequest.newBuilder()
        .setName("Mai")
        .build();

    Iterator<HelloReply> replies = stub.sayHelloMany(request);
    List<String> messages = new ArrayList<>();

    while (replies.hasNext()) {
        messages.add(replies.next().getMessage());
    }

    assertEquals(
        List.of("Hello, Mai", "Welcome, Mai", "Goodbye, Mai"),
        messages);
}
```

hasNext() và next() là thao tác blocking: chúng có thể chờ response tiếp theo. Iterator kết thúc khi server đóng stream; nếu stream kết thúc bằng lỗi, lần đọc tiếp theo có thể ném StatusRuntimeException. Test cần kiểm tra số lượng, thứ tự và nội dung response, đồng thời có deadline để tránh treo khi server quên gọi onCompleted().

Không dùng blocking iterator cho client-streaming hoặc bidi-streaming; hai kiểu đó cần async stub để gửi request và nhận response theo luồng.

## 8. Metadata và interceptor trong blocking stub test

Blocking stub vẫn đi qua client interceptor và server interceptor. Có thể kiểm tra metadata được gửi và đọc tại server, ví dụ request ID hoặc tenant:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ClientInterceptors;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

Metadata headers = new Metadata();
Metadata.Key<String> requestIdKey = Metadata.Key.of(
    "x-request-id",
    Metadata.ASCII_STRING_MARSHALLER);
headers.put(requestIdKey, "test-123");

ClientInterceptor requestIdInterceptor = new ClientInterceptor() {
    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {
        return new ForwardingClientCall.SimpleForwardingClientCall<>(
                next.newCall(method, callOptions)) {
            @Override
            public void start(Listener<RespT> responseListener,
                              Metadata requestHeaders) {
                requestHeaders.merge(headers);
                super.start(responseListener, requestHeaders);
            }
        };
    }
};

Channel interceptedChannel =
    ClientInterceptors.intercept(channel, requestIdInterceptor);
GreeterGrpc.GreeterBlockingStub testStub =
    GreeterGrpc.newBlockingStub(interceptedChannel);

HelloReply reply = testStub.sayHello(request);
```

Client interceptor gắn metadata vào từng call trước khi gửi. Phía server dùng interceptor để đọc header, xác minh principal hoặc đưa request ID vào gRPC Context. Trong test, có thể dùng một interceptor server ghi nhận giá trị đã nhận để assertion.

Test nên xác minh metadata tới đúng call và không rò giữa các request. Không lưu tenant, principal hoặc request ID trong field mutable của stub/service singleton. Credential phải được xác minh trước khi dùng để cấp quyền; sự hiện diện của header không chứng minh identity hợp lệ.

## 9. Tái sử dụng channel, stub và kiểm thử concurrency

ManagedChannel là tài nguyên dài hạn, có thể phục vụ nhiều RPC đồng thời. Không tạo channel mới cho mỗi method call. Generated stub là immutable; có thể dùng lại stub hoặc tạo bản cấu hình mới bằng withDeadlineAfter(), withInterceptors() hay các method cấu hình tương ứng.

Với test concurrency:

- Chia sẻ channel giữa các worker thay vì tạo một channel cho từng request.
- Dùng request độc lập và xác minh response gắn đúng request.
- Dùng executor có kích thước hữu hạn, shutdown sau test.
- Đặt deadline cho từng call để lỗi không giữ worker vô hạn.
- Không gọi blocking stub từ event-loop thread hoặc executor có quá ít thread để xử lý cả call và callback phụ thuộc.

Nếu một test chạy nhiều blocking call nhưng chỉ có một thread xử lý cả caller lẫn server handler, có thể tạo starvation/deadlock giả. Thiết kế executor riêng cho client worker và server handler khi kiểm tra concurrency.

## 10. Blocking stub trong ứng dụng Spring

Trong ứng dụng Spring, channel và stub thường được cấu hình như bean hoặc được tạo từ client factory dùng chung. Test có thể inject stub đã cấu hình để kiểm tra cách ứng dụng sử dụng client, nhưng cần phân biệt:

- Test service client logic với channel in-process do test dựng.
- Spring context test xác minh bean, interceptor, credential và deadline mặc định được cấu hình đúng.
- TCP/TLS integration test xác minh target, resolver, certificate, HTTP/2 và network.

Không gọi blocking stub trên reactive event loop. Nếu service layer dùng WebFlux/Reactor, chuyển blocking call sang bounded elastic hoặc executor được giới hạn; ưu tiên async stub nếu luồng xử lý cần non-blocking end-to-end. Với Spring MVC, nhớ rằng mỗi blocking call chiếm một request thread trong suốt thời gian chờ.

## 11. Những giới hạn cần kiểm tra ngoài in-process test

| In-process blocking stub test xác minh | Cần integration test qua network |
| --- | --- |
| Unary response và status | DNS, TCP socket và port mapping |
| Server-streaming iterator và thứ tự message | HTTP/2 negotiation, proxy và ingress |
| Deadline/cancellation trong gRPC call pipeline | TLS/mTLS handshake và hostname verification |
| Client/server interceptor và metadata | Load balancer, service mesh và network policy |
| Stub configuration và service method path | Certificate rotation, reconnect và connection failure |

In-process transport không kiểm tra TLS hoặc byte transport thật. Nếu mục tiêu là xác minh Spring gRPC server được starter khởi động và expose đúng port, dùng Spring Boot integration test với server thật hoặc port động. Không kết luận wiring production đúng chỉ từ fixture tự tạo bằng InProcessServerBuilder.

## 12. Ma trận kiểm thử và bài tập vận dụng

| Nhóm | Ca kiểm thử | Điều kiện PASS |
| --- | --- | --- |
| Unary success | Request hợp lệ | Blocking stub trả response đúng |
| Validation | Request sai | Status INVALID_ARGUMENT |
| Business error | Resource không tồn tại | Status NOT_FOUND |
| Authentication | Credential thiếu/sai | Status UNAUTHENTICATED |
| Authorization | Principal thiếu quyền | Status PERMISSION_DENIED |
| Deadline | Server không hoàn tất đúng hạn | Client nhận DEADLINE_EXCEEDED |
| Server streaming | Nhiều response | Iterator trả đúng thứ tự và kết thúc |
| Metadata | Request ID/tenant | Server nhận đúng metadata của call |
| Concurrency | Nhiều worker cùng gọi | Không rò request state |
| Cleanup | Test hoàn tất | Channel/server/executor được đóng |
| Spring wiring | Stub bean được cấu hình | Interceptor/credential/deadline đúng |
| Transport | TLS/HTTP2/ingress | Kết nối thực hoạt động theo cấu hình |

**Bài tập:** OrderClient dùng generated OrderServiceBlockingStub để gọi GetOrder. Method yêu cầu bearer token, có deadline 250 ms và trả NOT_FOUND khi order không tồn tại. Một method server-streaming ListOrderEvents trả các event theo thứ tự.

1. Dựng in-process server/channel và tạo blocking stub cho test.
2. Viết test GetOrder thành công và xác minh toàn bộ field quan trọng.
3. Viết test order không tồn tại, xác minh status NOT_FOUND.
4. Gắn metadata authorization qua interceptor và kiểm tra request không có token bị từ chối.
5. Kiểm tra deadline 250 ms bằng service có thể điều khiển thời điểm hoàn tất.
6. Dùng Iterator để kiểm tra thứ tự ListOrderEvents và lỗi stream nếu có.
7. Chạy nhiều blocking call đồng thời với executor hữu hạn và deadline riêng.
8. Viết Spring context test cho stub bean, sau đó bổ sung TCP/TLS test cho transport.

**Câu hỏi tự kiểm tra:**

- Blocking stub chặn thread tại thời điểm nào?
- Blocking stub hỗ trợ unary và server-streaming ra sao?
- Vì sao client-streaming và bidi-streaming dùng async stub?
- Khi RPC trả status lỗi, blocking stub ném loại exception nào?
- withDeadlineAfter() ảnh hưởng call mới như thế nào?
- Vì sao server-streaming Iterator có thể block ở hasNext()?
- Vì sao không tạo ManagedChannel cho mỗi call?
- Có thể kiểm tra metadata/interceptor bằng in-process channel không?
- Những thuộc tính nào cần TCP/TLS integration test?
- Vì sao không gọi blocking stub trên reactive event loop?

**Ghi nhớ:** Test blocking stub bằng cách gọi generated synchronous API qua channel tới server test và kiểm tra response, status, deadline hoặc iterator của server stream. Tái sử dụng channel, đặt deadline hữu hạn và đóng tài nguyên sau test. In-process test xác minh call behavior; Spring context test xác minh bean wiring; TCP/TLS test xác minh transport và network thật.

# In-process channel cho test

In-process channel là một ManagedChannel kết nối client stub tới gRPC server test trong cùng JVM bằng tên định danh. Nó cho phép test gọi generated stub qua gRPC method dispatch mà không cần mở TCP port, phân giải DNS hay thiết lập socket. Test vẫn đi qua API client/server của gRPC, nhưng không phải khởi động transport mạng thật.

Trong Spring gRPC, in-process channel hữu ích để kiểm tra service implementation, request validation, response, status mapping, interceptor và deadline ở phạm vi call. Trọng tâm là tạo channel trỏ đúng server name, dùng channel với generated stub và đóng nó đúng lifecycle. Muốn xác minh TLS, HTTP/2, proxy, socket hoặc wiring thực tế của Spring starter thì vẫn cần integration test qua transport thật.

## 1. In-process channel kết nối với server test như thế nào?

Một test tạo tên server duy nhất, đăng ký service implementation, start server rồi tạo channel trỏ tới đúng tên đó:

```text
JUnit test
   |
   | generate in-process server name
   v
InProcessServerBuilder
   | addService(...)
   | build().start()
   v
In-process gRPC server
   ^
   | InProcessChannelBuilder.forName(serverName)
   |
Generated client stub
   |
   | unary request
   v
Service implementation
   |
   | response or gRPC status
   v
Test assertions
```

Server và channel giao tiếp qua in-process transport, không dùng socket. Client vẫn gọi service qua generated stub và gRPC method dispatch, vì vậy test có thể xác minh method path, request/response type, status và interceptor được gắn vào server.

Tên server phải được tạo mới cho từng fixture/test để tránh hai test vô tình kết nối nhầm server. Khi fixture kết thúc, đóng channel và server để không giữ executor, callback hoặc tài nguyên giữa các test.

## 2. Chuẩn bị dependency test

Thêm artifact in-process có phiên bản đồng bộ với các thư viện grpc-java còn lại. Ví dụ Gradle Kotlin DSL:

```kotlin
dependencies {
    testImplementation("io.grpc:grpc-inprocess:$grpcVersion")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
```

Nếu dự án quản lý version bằng gRPC BOM hoặc version catalog, dùng cùng nguồn version đó thay vì khai báo một phiên bản grpc-inprocess khác. Generated classes như `GreeterGrpc`, `HelloRequest` và `HelloReply` phải được sinh từ proto trong build của ứng dụng.

Test không cần thêm dependency transport TCP chỉ để chạy in-process server. Nếu test dùng Spring Boot test context, giữ các dependency test của Spring theo cấu hình dự án.

## 3. Viết service implementation nhỏ để kiểm thử

Ví dụ service có một unary method nhận tên và trả lời lời chào. Input rỗng được ánh xạ thành status `INVALID_ARGUMENT`:

```java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

final class GreeterService extends GreeterGrpc.GreeterImplBase {

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> observer) {

        String name = request.getName().trim();
        if (name.isEmpty()) {
            observer.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("name is required")
                    .asRuntimeException());
            return;
        }

        HelloReply reply = HelloReply.newBuilder()
            .setMessage("Hello, " + name)
            .build();
        observer.onNext(reply);
        observer.onCompleted();
    }
}
```

Với unary RPC, server gửi đúng một response rồi hoàn tất stream bằng `onCompleted()`. Khi có lỗi, server gọi `onError()` và không gửi thêm response. Không gọi cả hai nhánh terminal cho cùng một call.

Trong service thật, business logic nên gọi application service/repository đã được inject. Unit test cho business rule có thể test riêng; in-process test kiểm tra phần tích hợp giữa gRPC method và logic đó.

## 4. Dựng server/channel trong JUnit 5

Dùng `@BeforeEach` để dựng server và channel, `@AfterEach` để đóng chúng:

```java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class GreeterServiceTest {
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

`directExecutor()` giúp callback chạy trực tiếp trên thread gọi trong test đơn giản, làm thứ tự thực thi dễ quan sát. Nó không mô phỏng executor production. Nếu ứng dụng phụ thuộc executor bất đồng bộ, context propagation hoặc scheduling, bổ sung test với executor phù hợp.

Luôn đóng channel trước rồi server. Dùng timeout hữu hạn cho `awaitTermination` để test không treo vô hạn nếu shutdown có lỗi. Nếu test fixture khởi tạo thất bại giữa chừng, cleanup vẫn cần kiểm tra null như ví dụ.

## 5. Kiểm tra response và request validation

Test thành công nên kiểm tra nội dung response, không chỉ kiểm tra call không ném exception:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

@Test
void returnsGreetingForValidName() {
    HelloRequest request = HelloRequest.newBuilder()
        .setName("Linh")
        .build();

    HelloReply reply = stub
        .withDeadlineAfter(1, TimeUnit.SECONDS)
        .sayHello(request);

    assertEquals("Hello, Linh", reply.getMessage());
}
```

Test lỗi kiểm tra status code và các side effect quan trọng:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.grpc.Status;
import io.grpc.StatusRuntimeException;

@Test
void rejectsBlankName() {
    HelloRequest request = HelloRequest.newBuilder()
        .setName("   ")
        .build();

    StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.sayHello(request));

    assertEquals(
        Status.Code.INVALID_ARGUMENT,
        error.getStatus().getCode());
}
```

Không assert toàn bộ description nếu đó không phải contract công khai. Ưu tiên status code, response fields và side effect cần thiết. Nếu handler gọi repository, dùng fake/mock hoặc test database phù hợp để xác minh dữ liệu chỉ được ghi khi request hợp lệ.

## 6. Kiểm thử interceptor và Context

In-process server có thể đăng ký service qua `ServerInterceptors.intercept(...)` để xác minh interceptor được gọi trước handler:

```java
ServerServiceDefinition intercepted =
    ServerInterceptors.intercept(
        new GreeterService().bindService(),
        new RequestIdServerInterceptor());

server = InProcessServerBuilder.forName(serverName)
    .directExecutor()
    .addService(intercepted)
    .build()
    .start();
```

Một test interceptor nên xác minh:

- Metadata đầu vào được đọc đúng.
- Principal hoặc request ID được đặt vào gRPC Context.
- Handler nhận đúng context value.
- Request không hợp lệ bị từ chối trước khi business handler chạy.
- Interceptor không làm thay đổi response/status ngoài contract.

Nếu interceptor là Spring bean, test standalone trên chỉ kiểm tra interceptor implementation và cách bọc service. Cần Spring integration test riêng để xác minh bean được inject và đăng ký vào đúng server do starter quản lý.

## 7. Deadline, cancellation và status

Client stub cho phép đặt deadline cho từng call:

```java
HelloReply reply = stub
    .withDeadlineAfter(200, TimeUnit.MILLISECONDS)
    .sayHello(request);
```

Một test deadline cần service test có thể trì hoãn response bằng latch hoặc scheduler điều khiển được. Tránh dùng sleep tùy ý vì thời gian scheduling của CI có thể làm test flaky. Kiểm tra client nhận DEADLINE_EXCEEDED và service hủy công việc nếu implementation hỗ trợ cancellation.

Các status thường nên có test riêng:

| Tình huống | Status cần xác minh |
| --- | --- |
| Request sai hoặc thiếu dữ liệu | INVALID_ARGUMENT |
| Resource không tồn tại | NOT_FOUND |
| Caller chưa xác thực | UNAUTHENTICATED |
| Caller không có quyền | PERMISSION_DENIED |
| Dependency tạm thời không sẵn sàng | UNAVAILABLE theo contract |
| Deadline hết hạn | DEADLINE_EXCEEDED |
| Lỗi không mong đợi | INTERNAL hoặc mapping đã quy định |

Status phải ổn định và phù hợp semantics. Không biến mọi exception thành INTERNAL nếu ứng dụng có thể ánh xạ lỗi nghiệp vụ đã biết sang status cụ thể.

## 8. Kiểm thử tính cô lập và concurrency

Mỗi test nên có server name và fixture riêng. Không dùng một mutable service singleton giữa nhiều test nếu nó lưu request state. Nếu cần chia sẻ fake dependency, reset state trước mỗi test và tránh chạy test song song trên cùng fixture.

Với service stateless, có thể kiểm tra nhiều call đồng thời bằng executor và assert mỗi response tương ứng với request của nó. Nếu handler giữ principal, tenant hoặc correlation ID trong field mutable, test concurrency có thể phát hiện dữ liệu từ call này rò sang call khác.

Không lưu dữ liệu request vào field của service singleton. Dùng biến local trong handler hoặc gRPC Context cho dữ liệu gắn với call. Nếu cần xác minh số lần handler được gọi, dùng counter thread-safe như AtomicInteger.

## 9. In-process test không thay thế TCP/TLS integration test

In-process transport giúp kiểm tra gRPC dispatch và lifecycle nhanh, nhưng không xác minh đầy đủ các thành phần phụ thuộc transport thật:

| In-process test phù hợp | Cần transport integration test |
| --- | --- |
| Request/response và status mapping | TCP socket, port binding và DNS |
| Method dispatch và service registration trong fixture | HTTP/2 negotiation và framing trên network |
| Interceptor, metadata và Context ở call path | TLS handshake, certificate chain và hostname verification |
| Deadline/cancellation ở logic gRPC | Proxy, ingress, service mesh và load balancer |
| Nhiều test logic chạy nhanh, cô lập | Network timeout, connection reset và reconnect |

In-process transport không chứng minh byte serialization, TLS, HTTP/2 hay proxy hoạt động giống production. Nếu mục tiêu là xác minh wire compatibility, message size, certificate hoặc routing, phải gọi server qua transport thật.

## 10. Kiểm thử wiring của Spring gRPC

Một test tự tạo InProcessServerBuilder không chứng minh Spring đã đăng ký service bean đúng. Để kiểm tra Spring wiring:

1. Dùng test context với đúng starter/configuration mà ứng dụng triển khai.
2. Đăng ký service implementation và interceptor như production.
3. Lấy channel/stub từ client configuration của ứng dụng hoặc kết nối tới test port do server Spring mở.
4. Gọi unary RPC và xác minh response/status.
5. Xác minh interceptor, dependency injection và shutdown lifecycle.

Tên property và extension point để chọn in-process transport hoặc port động phụ thuộc phiên bản Spring gRPC starter. Không sao chép một property không được starter hiện tại hỗ trợ; hãy dùng cấu hình test đã có trong ứng dụng và xác minh endpoint thực tế mà context khởi động.

Giữ test in-process cho service behavior và test Spring context cho wiring. Một test end-to-end qua TCP/TLS nên bao phủ các ranh giới mà in-process không thể kiểm tra.

## 11. Ma trận kiểm thử unary RPC

| Nhóm | Ca kiểm thử | Điều kiện PASS |
| --- | --- | --- |
| Success | Request hợp lệ | Response fields chính xác |
| Validation | Field rỗng/sai định dạng | Status INVALID_ARGUMENT |
| Business error | Resource không tồn tại | Status NOT_FOUND |
| Authentication | Credential thiếu/sai | Status UNAUTHENTICATED |
| Authorization | Principal thiếu quyền | Status PERMISSION_DENIED |
| Dependency | Backend unavailable | Status theo error mapping |
| Deadline | Response vượt deadline | Client nhận DEADLINE_EXCEEDED |
| Interceptor | Metadata/Context được truyền | Handler nhận đúng context |
| Cancellation | Client hủy call | Công việc dừng hoặc được cleanup theo contract |
| Concurrency | Nhiều call đồng thời | Không rò state giữa request |
| Lifecycle | Test kết thúc | Channel/server được shutdown |
| Spring wiring | Service bean được đăng ký | RPC qua server do Spring quản lý thành công |

Không cần mọi test đều dùng server thật. Chọn transport phù hợp với câu hỏi cần xác minh, giữ test nhỏ và tập trung vào một contract mỗi lần.

## 12. Bài tập vận dụng

GreeterService.SayHello nhận HelloRequest và trả HelloReply. Service yêu cầu tên không rỗng, interceptor gắn request ID vào Context và client đặt deadline 200 ms. Một bug gần đây khiến request lỗi vẫn gọi repository và test suite đôi lúc treo sau khi hoàn tất.

**Yêu cầu:**

1. Tạo in-process server/channel fixture với tên server duy nhất cho mỗi test.
2. Viết test success xác minh chính xác response.
3. Viết test validation xác minh INVALID_ARGUMENT và repository không được gọi.
4. Kiểm tra interceptor truyền request ID qua Context tới handler.
5. Viết deadline/cancellation test bằng latch hoặc scheduler điều khiển được.
6. Chạy nhiều call đồng thời và xác minh không rò request ID.
7. Đóng channel và server trong cleanup có timeout hữu hạn.
8. Viết thêm Spring integration test để xác minh service/interceptor bean được đăng ký trên server do starter quản lý.
9. Bổ sung TCP/TLS test nếu cần xác minh certificate, HTTP/2 hoặc ingress.

**Câu hỏi tự kiểm tra:**

- Vì sao in-process server không cần port TCP?
- Khi nào dùng directExecutor() và giới hạn của nó là gì?
- Vì sao phải tạo server name mới cho từng test?
- Unary server phải gọi onNext() và onCompleted() theo thứ tự nào?
- Vì sao test lỗi nên kiểm tra status code và side effect?
- Làm thế nào kiểm tra interceptor đưa principal/request ID vào Context?
- Vì sao không nên dùng sleep cố định để test deadline?
- In-process test không thể xác minh những thuộc tính transport nào?
- Vì sao cần Spring integration test ngoài fixture tự dựng?

**Ghi nhớ:** In-process channel nối generated stub tới server test bằng tên định danh, cho phép kiểm thử unary RPC mà không cần network port. Tạo server name riêng, dựng channel trỏ đúng tên, xác minh response, validation, status, interceptor, Context và call lifecycle; luôn đóng channel/server sau test. Dùng Spring integration test để xác minh wiring, còn TCP/TLS test để kiểm tra HTTP/2, certificate, proxy và network behavior.

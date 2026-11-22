# In-process gRPC server

**Chương:** Testing basics  
**Phạm vi:** Spring gRPC (SPRING_GRPC) dùng hợp đồng Protocol Buffers, mã Java được sinh và triển khai client/server cho unary hoặc streaming RPC. Bài này tập trung vào kiểm thử service bằng in-process gRPC server: dựng server và channel trong cùng JVM, gọi service qua generated stub, rồi xác nhận request, response, status, metadata và streaming lifecycle mà không mở TCP port.

## 1. In-process server dùng để kiểm tra điều gì?

Unit test gọi trực tiếp method của service implementation chỉ kiểm tra logic Java bên trong handler. Nó bỏ qua một phần quan trọng của gRPC: generated client stub, method descriptor, call lifecycle, interceptor chain và việc runtime dispatch RPC tới đúng service method.

In-process transport cho phép dựng một gRPC server và channel trong cùng tiến trình. Client vẫn gọi generated stub như ứng dụng thật, còn server vẫn đăng ký generated service implementation. Nhờ vậy, test có thể kiểm tra:

- Generated stub gọi đúng service method.
- Request và response đi qua gRPC call path.
- Unary và streaming RPC kết thúc đúng lifecycle.
- gRPC status được trả về đúng code.
- Client/server interceptor được áp dụng.
- Metadata và deadline được chuyển qua call.
- Cancellation và lỗi được quan sát ở phía client/server.

In-process test chạy nhanh, không cần port cố định hoặc socket. Nó phù hợp để kiểm thử adapter/service và wiring gRPC ở mức runtime.

## 2. In-process test không thay thế transport integration test

In-process transport không mở TCP socket và không chạy Netty HTTP/2 transport như production. Vì vậy, test này không chứng minh:

- TLS handshake, certificate chain hoặc hostname verification.
- HTTP/2 framing, flow control và network backpressure thực tế.
- Netty event loop, channel pipeline hoặc socket timeout.
- Load balancing, DNS/service discovery hoặc retry behavior của hạ tầng.
- Firewall, proxy, ingress hoặc network policy.

Nên kết hợp các tầng test:

| Tầng | Mục tiêu |
| --- | --- |
| Unit test | Kiểm tra validator, mapper và application logic |
| In-process gRPC test | Kiểm tra generated stub, service registration, interceptor, status và call lifecycle |
| Transport integration test | Kiểm tra Netty/TCP, TLS, HTTP/2 và cấu hình server thực |
| End-to-end test | Kiểm tra luồng giữa các service trong môi trường gần production |

Không kết luận TLS hoặc HTTP/2 đã hoạt động chỉ vì generated stub gọi thành công qua in-process channel.

## 3. Dependency cần thiết

Trong test source set, cần artifact grpc-inprocess cùng phiên bản với gRPC Java runtime của module. Ví dụ Gradle:

~~~kotlin
dependencies {
    testImplementation("io.grpc:grpc-inprocess")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
~~~

Nếu module dùng gRPC BOM hoặc dependency platform, hãy để BOM quản lý version của grpc-inprocess, grpc-stub, grpc-core và các artifact liên quan. Tránh tự đặt version riêng khiến runtime và test transport không tương thích.

Generated protobuf classes và generated gRPC stub vẫn đến từ protobuf plugin/source set hiện có của dự án. Không tạo bản sao message class trong test.

## 4. Dựng server và channel tối thiểu

Hai builder chính:

- InProcessServerBuilder.forName(serverName): tạo server gắn với tên nội bộ.
- InProcessChannelBuilder.forName(serverName): tạo client channel kết nối tới server có cùng tên.

Tên server nên được sinh riêng cho từng test bằng InProcessServerBuilder.generateName() để tránh xung đột giữa test chạy song song.

~~~java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class OrderGrpcServiceTest {

    private Server server;
    private ManagedChannel channel;

    @BeforeEach
    void startServer() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new TestOrderGrpcService())
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();
    }

    @AfterEach
    void stopServer() throws Exception {
        if (channel != null) {
            channel.shutdownNow();
            channel.awaitTermination(5, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow();
            server.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Ví dụ dùng directExecutor() để callback chạy trực tiếp trên thread gọi, giúp test đồng bộ đơn giản hơn. Đây là lựa chọn cho test logic cơ bản; nó không mô phỏng scheduling và concurrency của production executor. Với test cancellation, race, callback bất đồng bộ hoặc thread isolation, dùng executor riêng và đồng bộ bằng latch/future.

Luôn shutdown channel và server trong teardown kể cả khi assertion thất bại. Không dùng cùng một server name cho nhiều test đồng thời.

## 5. Đăng ký service implementation thật

Generated service base được sinh từ file .proto. Service implementation kế thừa base class và được đăng ký với server:

Giả sử service contract còn khai báo các method streaming sau:

~~~proto
service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
  rpc WatchOrder(WatchOrderRequest) returns (stream OrderEvent);
  rpc UploadOrder(stream UploadChunk) returns (UploadSummary);
  rpc ControlOrder(stream OrderCommand) returns (stream OrderCommand);
}

message GetOrderRequest { string order_id = 1; }
enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_CREATED = 1;
}
message GetOrderResponse {
  string order_id = 1;
  OrderStatus status = 2;
}
message WatchOrderRequest { string order_id = 1; }
message OrderEvent { string event_type = 1; }
message UploadChunk {
  int32 sequence = 1;
  string payload = 2;
}
message UploadSummary { int32 accepted_count = 1; }
message OrderCommand { string action = 1; }
~~~

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.ArrayList;
import java.util.List;

final class TestOrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {
        if (request.getOrderId().equals("missing")) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Order not found")
                            .asRuntimeException());
            return;
        }

        responseObserver.onNext(
                GetOrderResponse.newBuilder()
                        .setOrderId(request.getOrderId())
                        .setStatus(OrderStatus.ORDER_STATUS_CREATED)
                        .build());
        responseObserver.onCompleted();
    }

    @Override
    public void watchOrder(
            WatchOrderRequest request,
            StreamObserver<OrderEvent> responseObserver) {
        responseObserver.onNext(OrderEvent.newBuilder()
                .setEventType("ACCEPTED")
                .build());
        responseObserver.onNext(OrderEvent.newBuilder()
                .setEventType("PACKED")
                .build());
        responseObserver.onCompleted();
    }

    @Override
    public StreamObserver<UploadChunk> uploadOrder(
            StreamObserver<UploadSummary> responseObserver) {
        List<UploadChunk> chunks = new ArrayList<>();
        return new StreamObserver<>() {
            @Override
            public void onNext(UploadChunk chunk) {
                chunks.add(chunk);
            }

            @Override
            public void onError(Throwable error) {
                chunks.clear();
            }

            @Override
            public void onCompleted() {
                responseObserver.onNext(
                        UploadSummary.newBuilder()
                                .setAcceptedCount(chunks.size())
                                .build());
                responseObserver.onCompleted();
            }
        };
    }

    @Override
    public StreamObserver<OrderCommand> controlOrder(
            StreamObserver<OrderCommand> responseObserver) {
        return new StreamObserver<>() {
            @Override
            public void onNext(OrderCommand command) {
                responseObserver.onNext(command);
            }

            @Override
            public void onError(Throwable error) {
                responseObserver.onError(error);
            }

            @Override
            public void onCompleted() {
                responseObserver.onCompleted();
            }
        };
    }
}
~~~

Đây là test service đơn giản để minh họa. Trong test adapter thực tế, có thể đăng ký chính service implementation production và mock application use case phía sau nó. Khi đó validator, mapper, adapter và generated stub vẫn là code thật; chỉ application dependency được thay bằng mock.

## 6. Gọi generated blocking stub

Sau khi dựng channel, tạo generated stub như client production:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

OrderServiceGrpc.OrderServiceBlockingStub stub =
        OrderServiceGrpc.newBlockingStub(channel);

GetOrderResponse response = stub.getOrder(
        GetOrderRequest.newBuilder()
                .setOrderId("order-42")
                .build());

assertEquals("order-42", response.getOrderId());
assertEquals(
        OrderStatus.ORDER_STATUS_CREATED,
        response.getStatus());
~~~

Blocking stub phù hợp với unary RPC trong test vì lời gọi trả response hoặc ném StatusRuntimeException. Không gọi service method trực tiếp; mục tiêu là kiểm tra đường đi qua generated stub và gRPC runtime.

## 7. Kiểm tra unary response và status lỗi

Một test có thể xác nhận cả nhánh thành công và lỗi:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.Iterator;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

@Test
void returnsResponseForExistingOrder() {
    OrderServiceGrpc.OrderServiceBlockingStub stub =
            OrderServiceGrpc.newBlockingStub(channel);

    GetOrderResponse response = stub.getOrder(
            GetOrderRequest.newBuilder()
                    .setOrderId("order-42")
                    .build());

    assertEquals("order-42", response.getOrderId());
}

@Test
void exposesNotFoundStatusForMissingOrder() {
    OrderServiceGrpc.OrderServiceBlockingStub stub =
            OrderServiceGrpc.newBlockingStub(channel);

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("missing")
                            .build()));

    assertEquals(
            Status.Code.NOT_FOUND,
            Status.fromThrowable(error).getCode());
}
~~~

Ở client, status code là contract ổn định hơn exception message. Nếu API dùng rich error details như google.rpc.BadRequest, hãy unpack detail và kiểm tra field violations trong test riêng. Không phụ thuộc vào chuỗi mô tả lỗi nếu nó không phải contract công khai.

## 8. Dùng asynchronous stub và kiểm soát callback

Async stub nhận StreamObserver để trả kết quả. Test nên dùng latch và atomic reference để chờ callback có giới hạn thời gian:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

@Test
void asyncStubCompletesUnaryCall() throws Exception {
    OrderServiceGrpc.OrderServiceStub stub =
            OrderServiceGrpc.newStub(channel);
    CountDownLatch terminal = new CountDownLatch(1);
    AtomicReference<GetOrderResponse> response =
            new AtomicReference<>();
    AtomicReference<Throwable> failure =
            new AtomicReference<>();

    stub.getOrder(
            GetOrderRequest.newBuilder()
                    .setOrderId("order-async")
                    .build(),
            new StreamObserver<>() {
                @Override
                public void onNext(GetOrderResponse value) {
                    response.set(value);
                }

                @Override
                public void onError(Throwable error) {
                    failure.set(error);
                    terminal.countDown();
                }

                @Override
                public void onCompleted() {
                    terminal.countDown();
                }
            });

    assertTrue(terminal.await(5, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals("order-async", response.get().getOrderId());
}
~~~

Không dùng Thread.sleep() để đoán lúc callback hoàn tất. Timeout trong await giúp test fail rõ ràng thay vì treo vô hạn. Nếu callback có thể gửi nhiều response, dùng collection thread-safe hoặc đồng bộ hóa khi ghi nhận.

## 9. Kiểm tra server-streaming RPC

Với server-streaming, generated blocking stub thường trả Iterator<Response>. Test có thể duyệt toàn bộ stream và xác nhận thứ tự:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.stub.StreamObserver;
import java.util.ArrayList;
import java.util.List;
import java.util.Iterator;
import org.junit.jupiter.api.Test;

@Test
void receivesServerStreamInOrder() {
    OrderServiceGrpc.OrderServiceBlockingStub stub =
            OrderServiceGrpc.newBlockingStub(channel);

    Iterator<OrderEvent> events = stub.watchOrder(
            WatchOrderRequest.newBuilder()
                    .setOrderId("order-42")
                    .build());

    List<OrderEvent> received = new ArrayList<>();
    events.forEachRemaining(received::add);

    assertEquals(2, received.size());
    assertEquals("ACCEPTED", received.get(0).getEventType());
    assertEquals("PACKED", received.get(1).getEventType());
}
~~~

Khi iterator kết thúc bình thường, stream đã hoàn tất. Nếu server kết thúc bằng lỗi, việc duyệt iterator có thể ném StatusRuntimeException; test nên xác nhận status code như unary test.

## 10. Kiểm tra client-streaming RPC

Với client-streaming, async stub trả inbound StreamObserver<Request>. Client gửi nhiều message rồi gọi onCompleted(); server trả một response cuối cùng:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

@Test
void uploadsMultipleChunksAndReceivesSummary() throws Exception {
    OrderServiceGrpc.OrderServiceStub stub =
            OrderServiceGrpc.newStub(channel);
    CountDownLatch terminal = new CountDownLatch(1);
    AtomicReference<UploadSummary> summary = new AtomicReference<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();

    StreamObserver<UploadChunk> requestObserver = stub.uploadOrder(
            new StreamObserver<>() {
                @Override
                public void onNext(UploadSummary value) {
                    summary.set(value);
                }

                @Override
                public void onError(Throwable error) {
                    failure.set(error);
                    terminal.countDown();
                }

                @Override
                public void onCompleted() {
                    terminal.countDown();
                }
            });

    requestObserver.onNext(UploadChunk.newBuilder()
            .setSequence(1)
            .setPayload("first")
            .build());
    requestObserver.onNext(UploadChunk.newBuilder()
            .setSequence(2)
            .setPayload("second")
            .build());
    requestObserver.onCompleted();

    assertTrue(terminal.await(5, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(2, summary.get().getAcceptedCount());
}
~~~

Không gọi onCompleted() trước khi gửi hết request. Sau terminal signal, không gửi thêm onNext(). Nếu test muốn kiểm tra client cancellation, gọi cancel trên call handle hoặc hủy stream qua cơ chế phù hợp thay vì gửi thêm message sau completion.

## 11. Kiểm tra bidirectional streaming

Với bidirectional streaming, client gửi và nhận message độc lập trong cùng một RPC. Test nên điều khiển luồng request, chờ response theo điều kiện và kết thúc đúng lifecycle:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.stub.StreamObserver;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

@Test
void exchangesMessagesInBidirectionalStream() throws Exception {
    OrderServiceGrpc.OrderServiceStub stub =
            OrderServiceGrpc.newStub(channel);
    CountDownLatch terminal = new CountDownLatch(1);
    List<OrderCommand> responses =
            new CopyOnWriteArrayList<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();

    StreamObserver<OrderCommand> requests = stub.controlOrder(
            new StreamObserver<>() {
                @Override
                public void onNext(OrderCommand value) {
                    responses.add(value);
                }

                @Override
                public void onError(Throwable error) {
                    failure.set(error);
                    terminal.countDown();
                }

                @Override
                public void onCompleted() {
                    terminal.countDown();
                }
            });

    requests.onNext(OrderCommand.newBuilder()
            .setAction("PAUSE")
            .build());
    requests.onNext(OrderCommand.newBuilder()
            .setAction("RESUME")
            .build());
    requests.onCompleted();

    assertTrue(terminal.await(5, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(2, responses.size());
}
~~~

Ví dụ giả định server trả một response cho mỗi command và hoàn tất khi client đóng chiều request. Nếu protocol cho phép server tiếp tục phát sau khi client hoàn tất gửi, test cần điều khiển response terminal theo đúng semantics của service.

## 12. Kiểm tra metadata bằng interceptor

In-process channel hỗ trợ client interceptor và server interceptor. Có thể kiểm tra metadata được gửi qua call mà không cần socket:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Channel;
import io.grpc.ClientInterceptor;
import io.grpc.ClientInterceptors;
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.MetadataUtils;
import java.util.concurrent.atomic.AtomicReference;

private static final Metadata.Key<String> TENANT_KEY =
        Metadata.Key.of(
                "x-tenant-id",
                Metadata.ASCII_STRING_MARSHALLER);
private static final Context.Key<String> TENANT_CONTEXT_KEY =
        Context.key("tenant-id");

final class TenantCaptureInterceptor implements ServerInterceptor {
    private final AtomicReference<String> capturedTenant =
            new AtomicReference<>();

    String capturedTenant() {
        return capturedTenant.get();
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {
        String tenant = headers.get(TENANT_KEY);
        capturedTenant.set(tenant);
        Context context = Context.current()
                .withValue(TENANT_CONTEXT_KEY, tenant);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

Đăng ký interceptor trên server builder:

~~~java
TenantCaptureInterceptor tenantCapture = new TenantCaptureInterceptor();
server = InProcessServerBuilder.forName(serverName)
        .directExecutor()
        .intercept(tenantCapture)
        .addService(service)
        .build()
        .start();
~~~

Client có thể gửi metadata qua client interceptor:

Trong cùng fixture, dùng chính instance tenantCapture đã đăng ký ở server builder và channel đang kết nối tới server đó:

~~~java
Metadata headers = new Metadata();
headers.put(TENANT_KEY, "tenant-test");

ClientInterceptor tenantHeader = MetadataUtils
        .newAttachHeadersInterceptor(headers);
Channel tenantChannel = ClientInterceptors.intercept(
        channel,
        tenantHeader);
OrderServiceGrpc.OrderServiceBlockingStub stub =
        OrderServiceGrpc.newBlockingStub(tenantChannel);

stub.getOrder(GetOrderRequest.newBuilder()
        .setOrderId("order-42")
        .build());
assertEquals("tenant-test", tenantCapture.capturedTenant());
~~~

Test có thể xác nhận service đọc được tenant context hoặc xác nhận interceptor ghi nhận đúng header. Metadata chỉ là dữ liệu đầu vào; không coi tenant ID do client gửi là bằng chứng authorization. Production phải xác thực caller và kiểm tra tenant access bằng security policy.

## 13. Deadline và cancellation

Deadline được gắn vào stub bằng withDeadlineAfter. Để test ổn định, dùng một service fixture lên lịch response sau thời gian deadline thay vì dựa vào Thread.sleep():

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

final class DelayedOrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase
        implements AutoCloseable {

    private final ScheduledExecutorService scheduler =
            Executors.newSingleThreadScheduledExecutor();

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> observer) {
        scheduler.schedule(() -> {
            observer.onNext(GetOrderResponse.newBuilder()
                    .setOrderId(request.getOrderId())
                    .build());
            observer.onCompleted();
        }, 5, TimeUnit.SECONDS);
    }

    @Override
    public void close() {
        scheduler.shutdownNow();
    }
}

@Test
void deadlineExpiresBeforeScheduledResponse() throws Exception {
    String name = InProcessServerBuilder.generateName();
    DelayedOrderGrpcService delayedService =
            new DelayedOrderGrpcService();
    Server delayedServer = InProcessServerBuilder.forName(name)
            .addService(delayedService)
            .build()
            .start();
    ManagedChannel delayedChannel =
            InProcessChannelBuilder.forName(name).build();

    try {
        OrderServiceGrpc.OrderServiceBlockingStub stub =
                OrderServiceGrpc.newBlockingStub(delayedChannel)
                        .withDeadlineAfter(1, TimeUnit.SECONDS);
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getOrder(GetOrderRequest.newBuilder()
                        .setOrderId("slow-order")
                        .build()));

        assertEquals(
                Status.Code.DEADLINE_EXCEEDED,
                Status.fromThrowable(error).getCode());
    } finally {
        delayedChannel.shutdownNow();
        delayedServer.shutdownNow();
        delayedService.close();
    }
}
~~~

Fixture lên lịch response sau năm giây trong khi client có deadline một giây. Test không phải chờ response muộn; teardown hủy scheduler sau khi xác nhận status. Vẫn nên dùng khoảng thời gian đủ rộng để CI có scheduling jitter và đóng channel/server/scheduler trong mọi nhánh.

Deadline/cancellation có thể hủy RPC ở phía client nhưng không tự động dừng mọi blocking operation trong application code. Handler và downstream client cần propagate cancellation/deadline, kiểm tra cancellation khi phù hợp và giải phóng tài nguyên. Test nên xác nhận server không phát response sau terminal cancellation.

## 14. Dùng Spring service bean trong in-process server

Trong ứng dụng Spring gRPC, service implementation thường là Spring bean được đăng ký bằng annotation/starter. Có thể lấy bean đã được Spring khởi tạo rồi đăng ký nó vào in-process server:

~~~java
OrderGrpcService service =
        applicationContext.getBean(OrderGrpcService.class);

Server server = InProcessServerBuilder.forName(serverName)
        .directExecutor()
        .addService(service)
        .build()
        .start();
~~~

Cách này kiểm tra adapter thật cùng các dependency Spring đã inject. Cần tổ chức test context sao cho không vô tình khởi động thêm một network gRPC server nếu mục tiêu chỉ là in-process test; cơ chế tắt server auto-configuration phụ thuộc starter và version dự án.

Nếu test không cần Spring wiring, khởi tạo service bằng constructor trực tiếp và truyền mock application use case. Cách này thường nhanh và dễ xác định lỗi hơn. Dùng Spring context khi chính việc wiring bean là một phần của câu hỏi kiểm thử.

## 15. Interceptor chain và thứ tự đăng ký

In-process server/channel có thể đăng ký nhiều interceptor. Điều này hữu ích để kiểm tra:

- Authentication/authorization interceptor từ chối call trước khi vào handler.
- Tracing interceptor tạo span và propagate context.
- Logging/metrics interceptor ghi nhận status và latency.
- Metadata interceptor chuyển dữ liệu call vào gRPC Context.

Thứ tự interceptor có thể ảnh hưởng dữ liệu mà interceptor phía sau nhìn thấy. Test nên dựng chain giống cấu hình ứng dụng và xác nhận behavior quan trọng; không suy ra thứ tự production chỉ từ một test builder khác cấu hình.

Không đưa secret hoặc raw authorization metadata vào assertion output/log. Với auth test, dùng token giả và xác nhận status như UNAUTHENTICATED hoặc PERMISSION_DENIED.

## 16. Executor và tính xác định của test

directExecutor() làm callback chạy ngay trên thread thực hiện call, phù hợp với test đơn giản và giảm nondeterminism. Nhưng nó có thể che giấu:

- Race giữa callback và cancellation.
- Lỗi chia sẻ mutable state giữa thread.
- Deadlock do code vô tình block event/callback thread.
- Sai sót khi propagate gRPC/OpenTelemetry/Security context qua executor.

Với behavior liên quan concurrency, bỏ directExecutor() và dùng executor rõ ràng hoặc runtime default. Đồng bộ test bằng CountDownLatch, CompletableFuture hoặc condition có timeout. Không chờ bằng vòng lặp bận và không dùng Thread.sleep() làm cơ chế đồng bộ chính.

## 17. Cleanup và quản lý tài nguyên

Mỗi test cần đóng:

- ManagedChannel: ngừng nhận call mới, hủy call còn tồn tại nếu test cần dừng nhanh, rồi await termination.
- Server: shutdown server và await termination.
- Executor do test tự tạo: shutdown và await termination.
- Scheduler/future hoặc stream còn mở: cancel/close để không giữ thread sau test.

Trong teardown, dùng try/finally hoặc JUnit @AfterEach để cleanup ngay cả khi assertion fail. Không chia sẻ một channel giữa test nếu test có thể thay đổi interceptor, deadline hoặc trạng thái stream.

## 18. Ma trận kiểm thử in-process gRPC server

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Unary success | Generated blocking stub nhận đúng response |
| Unary error | Client nhận đúng gRPC status code |
| Async unary | Callback hoàn tất trong timeout và không có error |
| Server streaming | Nhận đủ message, đúng thứ tự và terminal event |
| Client streaming | Gửi nhiều request, nhận summary sau completion |
| Bidirectional streaming | Trao đổi hai chiều theo protocol |
| Metadata | Client interceptor gửi header, server interceptor đọc được |
| Deadline | Call hết ngân sách nhận DEADLINE_EXCEEDED |
| Cancellation | Call kết thúc đúng, không phát response sau cancel |
| Authentication | Interceptor trả UNAUTHENTICATED/PERMISSION_DENIED |
| Spring wiring | Service bean thật được đăng ký và gọi được |
| Cleanup | Channel/server/executor kết thúc, không rò thread |

Không phải service nào cũng có đủ bốn kiểu RPC. Chọn ca theo contract thực tế và test từng behavior có rủi ro.

## 19. Những lỗi thường gặp

- **Dùng port cố định:** test chạy song song có thể xung đột; dùng generated server name.
- **Quên shutdown channel/server:** để lại thread và làm test suite treo.
- **Mock generated stub:** không kiểm tra được gRPC runtime; tạo stub thật từ in-process channel.
- **Gọi service method trực tiếp rồi gọi đó là in-process test:** không đi qua stub/channel.
- **Dùng directExecutor cho mọi test:** che khuất concurrency issue.
- **Dùng sleep để chờ callback:** tạo flaky test; dùng latch/future có timeout.
- **Kết luận TLS hoạt động:** in-process transport không thực hiện TLS handshake.
- **Không kiểm tra status code:** test chỉ thấy call fail nhưng không xác nhận contract lỗi.
- **Không kết thúc streaming observer:** test treo hoặc rò tài nguyên.
- **Tin metadata tenant do client gửi:** metadata không thay authorization.

## 20. Tự luyện tập

1. Vì sao in-process server hữu ích hơn việc gọi trực tiếp service method khi test generated stub?
2. Dùng InProcessServerBuilder.generateName() giải quyết vấn đề gì?
3. Vì sao directExecutor() phù hợp với test đơn giản nhưng không đại diện đầy đủ production concurrency?
4. Thiết kế test kiểm tra server-streaming nhận đủ message và kết thúc đúng.
5. Làm thế nào xác nhận client interceptor gửi metadata mà server interceptor có thể đọc?
6. In-process test có chứng minh TLS và HTTP/2 framing hoạt động không? Vì sao?
7. Khi dùng Spring bean thật trong in-process server, cần chú ý gì với auto-configuration của starter?

**Ghi nhớ:** In-process gRPC server cho phép gọi generated stub qua server/channel cùng JVM để kiểm tra service registration, unary/streaming lifecycle, status, metadata, interceptor, deadline và cancellation mà không mở TCP port. Dùng server name riêng, cleanup channel/server đầy đủ và chỉ dùng directExecutor cho test phù hợp. Bổ sung transport integration test riêng cho Netty, HTTP/2, TLS và network behavior.

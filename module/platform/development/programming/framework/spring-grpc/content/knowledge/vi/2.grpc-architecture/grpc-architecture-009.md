# Interceptor ở phía client và server

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích interceptor là điểm mở rộng để thực thi logic dùng chung quanh một RPC.
- Phân biệt vòng đời và trách nhiệm của **ClientInterceptor** với **ServerInterceptor** trong grpc-java.
- Gắn metadata ở client, xác thực/ủy quyền ở server và truyền thông tin đã xác minh qua **io.grpc.Context**.
- Theo dõi status, latency, cancellation và lỗi qua callback mà không làm thay đổi hành vi RPC.
- Đăng ký interceptor với **ManagedChannel** và gRPC server do Spring quản lý.
- Kiểm thử interceptor theo từng phía, kiểm soát thứ tự thực thi và tránh các lỗi về thread, metadata, bảo mật.

## 1. Interceptor nằm ở đâu trong một RPC?

Trong **SPRING_GRPC**, generated stub và gRPC runtime đảm nhiệm việc chuyển lời gọi Java thành RPC qua HTTP/2. Một ứng dụng thường cần áp dụng cùng một số hành vi cho nhiều method: gắn request ID, xác thực caller, ghi nhận latency, tạo trace hoặc chuẩn hóa lỗi. **Interceptor** cung cấp điểm móc ở tầng RPC để thực hiện những việc đó.

- **ClientInterceptor** chạy trong quá trình client tạo và sử dụng một RPC. Nó có thể bổ sung request metadata, bọc callback nhận response và quan sát status kết thúc.
- **ServerInterceptor** chạy khi server nhận một RPC, trước khi gọi service implementation. Nó có thể kiểm tra metadata, xác thực caller, tạo context và bọc các callback của server call.

~~~mermaid
sequenceDiagram
    participant App as Spring client service
    participant CI as ClientInterceptor
    participant Stub as Generated stub / Channel
    participant SI as ServerInterceptor
    participant Impl as Spring gRPC implementation
    App->>CI: Gọi RPC
    CI->>CI: Tạo request metadata
    CI->>Stub: Chuyển tiếp call
    Stub->>SI: HTTP/2 request
    SI->>SI: Kiểm tra metadata / tạo Context
    SI->>Impl: Chuyển tiếp call
    Impl-->>SI: Response hoặc Status
    SI-->>Stub: Kết quả RPC
    Stub-->>CI: Callback kết thúc
    CI-->>App: Chuyển kết quả cho caller
~~~

Interceptor hoạt động ở **ranh giới RPC**, không thay thế service nghiệp vụ. Ví dụ, interceptor có thể xác minh token và đặt principal vào Context; quyền xem một đơn hàng cụ thể vẫn cần được kiểm tra trong service/domain layer dựa trên principal đó.

## 2. Vòng đời và API của ClientInterceptor

Trong grpc-java, **ClientInterceptor** triển khai phương thức:

~~~java
<ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
        MethodDescriptor<ReqT, RespT> method,
        CallOptions callOptions,
        Channel next);
~~~

Mỗi khi stub tạo một RPC, interceptor có thể xem **MethodDescriptor** (method nào, kiểu request/response, loại RPC), **CallOptions** (deadline, credentials và các call option) và Channel tiếp theo. Nó trả về một **ClientCall** để runtime sử dụng.

Những điểm quan sát chính:

| API/callback | Thời điểm | Ứng dụng thường gặp |
| --- | --- | --- |
| **interceptCall(...)** | Khi tạo call | Chọn logic theo method, bọc ClientCall |
| **ClientCall.start(...)** | Bắt đầu call | Bổ sung request headers, bọc listener |
| **sendMessage(...)** | Client gửi request message | Đếm message/kích thước ở mức call nếu phù hợp |
| **halfClose()** | Client kết thúc chiều gửi | Quan sát kết thúc request stream |
| **cancel(...)** | Call bị hủy từ client | Ghi nhận cancellation |
| **Listener.onHeaders(...)** | Nhận initial response headers | Đọc metadata ban đầu |
| **Listener.onMessage(...)** | Nhận response message | Quan sát message nếu thực sự cần |
| **Listener.onClose(status, trailers)** | RPC kết thúc | Ghi status, latency, trailing metadata |

Không cần override mọi callback. Một interceptor nên chỉ làm công việc xuyên suốt các method và có chi phí thấp. Việc parse payload, gọi database hoặc thực hiện logic nghiệp vụ trong interceptor thường làm tăng coupling và latency.

### 2.1. Gắn request ID bằng ClientInterceptor

Ví dụ sau tạo một request ID cho mỗi RPC và thêm vào metadata:

~~~java
package dev.example.orders.client;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.UUID;

public final class RequestIdClientInterceptor
        implements ClientInterceptor {

    private static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of(
                    "x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);

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

                headers.put(REQUEST_ID, UUID.randomUUID().toString());
                super.start(responseListener, headers);
            }
        };
    }
}
~~~

**start(...)** là điểm thích hợp để bổ sung request headers trước khi call được gửi. Mã trên tạo ID mới cho mỗi RPC. Trong hệ thống phân tán, nếu caller đã có correlation/trace ID, có thể truyền tiếp ID đó theo context của request thay vì luôn tạo ID mới ở mỗi service.

Không tạo một **Metadata** mutable dùng chung ở cấp singleton rồi thay giá trị cho từng RPC. Các lời gọi đồng thời có thể gửi nhầm ID hoặc credential. Hãy tạo/điền metadata trong scope của từng call.

### 2.2. Quan sát status và latency

Client interceptor cũng có thể bọc listener để đo thời gian từ lúc call bắt đầu đến khi nhận callback kết thúc:

~~~java
package dev.example.orders.client;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;

public final class RpcMetricsClientInterceptor
        implements ClientInterceptor {

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions options,
            Channel next) {

        ClientCall<ReqT, RespT> delegate = next.newCall(method, options);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(delegate) {

            private long startedAtNanos;

            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata headers) {

                startedAtNanos = System.nanoTime();

                Listener<RespT> wrapped =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<RespT>(
                                        listener) {
                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {

                                long elapsedNanos =
                                        System.nanoTime() - startedAtNanos;

                                recordRpc(
                                        method.getFullMethodName(),
                                        status.getCode(),
                                        elapsedNanos);

                                super.onClose(status, trailers);
                            }
                        };

                super.start(wrapped, headers);
            }
        };
    }

    private void recordRpc(
            String fullMethodName,
            Status.Code code,
            long elapsedNanos) {
        // Gửi tới metrics system đã được inject/cấu hình.
    }
}
~~~

Đây là minh họa cho vị trí đo, không phải một metrics backend hoàn chỉnh. Trong ứng dụng thật, nên inject một recorder thread-safe; không thực hiện I/O đồng bộ hoặc log khối lượng lớn trong callback. Dùng **full method name** và **Status.Code** làm nhãn có cardinality kiểm soát; tránh dùng order ID, request ID hoặc token làm metric label.

**onClose(...)** là callback kết thúc call. Nó nhận status và trailers; cần gọi **super.onClose(...)** để callback của stub/caller tiếp tục được thực thi. Nếu interceptor nuốt callback, caller có thể không bao giờ nhận kết quả.

## 3. Vòng đời và API của ServerInterceptor

**ServerInterceptor** triển khai:

~~~java
<ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
        ServerCall<ReqT, RespT> call,
        Metadata headers,
        ServerCallHandler<ReqT, RespT> next);
~~~

Server interceptor nhận **ServerCall**, request headers và handler tiếp theo. Nó có thể:

- Từ chối lời gọi trước khi service implementation chạy.
- Xác minh metadata/credential và tạo principal.
- Đưa request ID hoặc principal đã xác minh vào **Context**.
- Bọc ServerCall để thêm response headers/trailers hoặc quan sát status.
- Bọc ServerCall.Listener để theo dõi message, half-close, cancellation và completion.

| Callback | Ý nghĩa |
| --- | --- |
| **interceptCall(...)** | Điểm vào của mỗi RPC ở server |
| **Listener.onMessage(...)** | Nhận request message |
| **Listener.onHalfClose()** | Client đã kết thúc chiều gửi |
| **Listener.onCancel()** | RPC bị client hủy/transport đóng theo ngữ cảnh |
| **Listener.onComplete()** | Call hoàn tất theo lifecycle server |
| **Listener.onReady()** | Server có thể gửi thêm message theo flow control |
| **ServerCall.sendHeaders(...)** | Gửi initial response metadata |
| **ServerCall.close(status, trailers)** | Kết thúc RPC và gửi status/trailers |

Một **ServerInterceptor** không đồng nghĩa một filter HTTP servlet. Nó xử lý RPC đã được gRPC runtime định tuyến; không tự áp dụng cho REST endpoint hoặc mọi kết nối trong ứng dụng Spring.

### 3.1. Đọc metadata và đưa principal vào Context

Ví dụ dưới đây yêu cầu metadata **x-request-id**, sau đó truyền giá trị vào gRPC Context để handler có thể đọc:

~~~java
package dev.example.orders.server;

import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class RequestContextServerInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of(
                    "x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    static final Context.Key<String> REQUEST_ID_CONTEXT =
            Context.key("request-id");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(REQUEST_ID);

        if (requestId == null || requestId.isBlank()) {
            call.close(
                    Status.INVALID_ARGUMENT.withDescription(
                            "Thiếu x-request-id"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        Context context = Context.current()
                .withValue(REQUEST_ID_CONTEXT, requestId);

        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

Ví dụ dùng request ID để minh họa việc truyền context. Ở một hệ thống thật, có thể tự sinh ID tại ingress nếu client không gửi; việc bắt buộc hay tùy chọn phải là policy được thống nhất. Request ID do caller cung cấp **không chứng minh danh tính** và không thể dùng làm căn cứ cấp quyền.

Handler có thể đọc:

~~~java
String requestId =
        RequestContextServerInterceptor.REQUEST_ID_CONTEXT.get();
~~~

**Contexts.interceptCall(...)** giúp context được gắn trong các callback của RPC. Nếu handler chuyển công việc sang executor tùy chỉnh, cần truyền context sang thread đó bằng API như **Context.wrap(...)**; không giả định ThreadLocal tự viết sẽ tự lan truyền.

### 3.2. Xác thực và phân quyền

Interceptor là vị trí phù hợp để xác minh credential chung cho nhiều method. Khi token không hợp lệ, server có thể kết thúc bằng **UNAUTHENTICATED**; khi caller đã xác thực nhưng không đủ quyền gọi một method, có thể trả **PERMISSION_DENIED**.

Cần phân biệt:

- **Authentication** xác minh danh tính caller.
- **Authorization** quyết định principal có được gọi service/method hoặc thao tác tài nguyên hay không.
- **Business authorization** có thể cần dữ liệu của từng đơn hàng/tenant và thường cần phối hợp với tầng service/domain.

Không tin header như **x-user-role: admin** do client tự gửi. Principal phải được tạo từ credential đã xác minh. Interceptor có thể chặn truy cập ở mức service/method; implementation vẫn cần kiểm tra quyền trên tài nguyên cụ thể.

Với token theo từng call, cân nhắc **CallCredentials** ở client để gắn authorization metadata theo cơ chế xác thực. ClientInterceptor có thể hỗ trợ tracing hoặc header chung, nhưng không nên tự lưu token lâu dài trong một đối tượng mutable dùng chung.

## 4. Bọc call và listener đúng cách

Interceptor thường dùng các lớp **ForwardingClientCall**, **ForwardingClientCallListener**, **ForwardingServerCall** và **ForwardingServerCallListener**. Các lớp này giúp thêm hành vi nhưng vẫn chuyển tiếp những callback không cần thay đổi.

Nguyên tắc:

1. Tạo delegate bằng **next.newCall(...)** ở client hoặc nhận **ServerCall** ở server.
2. Bọc delegate/listener ở đúng điểm lifecycle.
3. Gọi **super** hoặc chuyển tiếp callback tương ứng, trừ khi chủ đích kết thúc RPC.
4. Không phát callback terminal hai lần.
5. Không giữ state theo RPC trong field singleton của interceptor nếu state đó không được cô lập theo call.

Ví dụ interceptor server thêm metadata kết thúc ở **ServerCall.close(...)**:

~~~java
package dev.example.orders.server;

import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class ServiceVersionInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> SERVICE_VERSION =
            Metadata.Key.of(
                    "x-service-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        ServerCall<ReqT, RespT> wrapped =
                new ForwardingServerCall
                        .SimpleForwardingServerCall<ReqT, RespT>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        trailers.put(SERVICE_VERSION, "orders-v1");
                        super.close(status, trailers);
                    }
                };

        return next.startCall(wrapped, headers);
    }
}
~~~

Ví dụ thêm một custom trailer cho mọi kết quả kết thúc. Nếu chỉ muốn thêm khi lỗi, kiểm tra **status.isOk()** trước khi ghi. Không ghi đè **grpc-status** vì đây là trường giao thức do runtime quản lý.

## 5. Đăng ký interceptor trong ứng dụng Spring

### 5.1. Client: bọc Channel trước khi tạo stub

Với grpc-java cơ bản, **ClientInterceptors.intercept(...)** tạo một Channel wrapper. Spring có thể quản lý Channel gốc và stub như bean:

~~~java
package dev.example.orders.client;

import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.ClientInterceptors;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        return ManagedChannelBuilder
                .forAddress("localhost", 9090)
                .usePlaintext()
                .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderStub(
            ManagedChannel orderChannel) {

        return OrderServiceGrpc.newBlockingStub(
                ClientInterceptors.intercept(
                        orderChannel,
                        new RequestIdClientInterceptor(),
                        new RpcMetricsClientInterceptor()));
    }
}
~~~

Stub được tạo từ Channel wrapper nên mọi RPC qua stub đó đi qua interceptor đã đăng ký. **ManagedChannel** gốc vẫn được tái sử dụng và Spring đóng nó khi context dừng. **usePlaintext()** chỉ dành cho demo local hoặc môi trường đã kiểm soát; production cần TLS/mTLS và credentials phù hợp.

Không tạo một ManagedChannel mới cho từng request. Việc đó làm tăng connection, handshake và chi phí resolver, đồng thời mất lợi ích theo dõi Subchannel/load balancing liên tục.

### 5.2. Server: bọc service implementation

Với grpc-java ServerBuilder:

~~~java
package dev.example.orders.server;

import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.ServerInterceptors;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcServerConfig {

    @Bean(initMethod = "start", destroyMethod = "shutdown")
    Server orderServer(OrderEndpoint endpoint) {
        return ServerBuilder.forPort(9090)
                .addService(
                        ServerInterceptors.intercept(
                                endpoint,
                                new RequestContextServerInterceptor(),
                                new ServiceVersionInterceptor()))
                .build();
    }
}
~~~

**OrderEndpoint** là Spring bean kế thừa **OrderServiceGrpc.OrderServiceImplBase**. **ServerInterceptors.intercept(...)** tạo service wrapper gắn interceptor trước khi đăng ký với server.

Đây là cách tích hợp grpc-java trực tiếp. Nếu dự án dùng Spring gRPC starter có auto-configuration server/service, hãy đăng ký interceptor qua extension point của phiên bản starter đang dùng và tránh khởi động thêm server thủ công trên cùng cổng. Tên property/API của starter có thể khác giữa các phiên bản.

### 5.3. Thứ tự interceptor

Khi có nhiều interceptor, thứ tự ảnh hưởng đến hành vi:

- Interceptor ngoài cùng có thể tạo context hoặc correlation ID cho các lớp bên trong.
- Authentication nên diễn ra trước authorization dựa trên principal.
- Logging/metrics cần quan sát được status cuối cùng nhưng không ghi dữ liệu bí mật.
- Interceptor xử lý lỗi phải không che mất status gốc hoặc nuốt callback.

Thứ tự thực thi cụ thể phụ thuộc cách các interceptor được lồng/bọc và API đăng ký được dùng. Hãy khai báo rõ thứ tự trong cấu hình, viết test cho các phụ thuộc thứ tự và tránh để logic bảo mật phụ thuộc vào một thứ tự ngầm định.

## 6. Những việc interceptor nên và không nên làm

| Nên dùng interceptor cho | Nên để ở tầng khác |
| --- | --- |
| Gắn request/correlation ID | Quy tắc nghiệp vụ của đơn hàng |
| Xác minh credential chung | Kiểm tra quyền chi tiết trên từng tài nguyên |
| Đưa principal vào Context | Tính giá, tồn kho, giao dịch |
| Ghi nhận latency/status theo method | Ghi toàn bộ payload hoặc business event |
| Chuẩn hóa metadata/tracing | Thay đổi schema request/response |
| Chặn method không được phép | Retry một thao tác ghi không idempotent |

Interceptor nên **nhẹ, nhanh, ít phụ thuộc**. Một interceptor đồng bộ gọi database hoặc dịch vụ ngoài cho mọi RPC có thể trở thành nút nghẽn chung của toàn bộ service. Nếu cần kiểm tra quyền theo dữ liệu nghiệp vụ, hãy dùng principal do interceptor xác minh rồi thực hiện kiểm tra ở service/domain layer.

Một interceptor cũng không thay thế **deadline**, **cancellation**, **TLS** hay **health checking**. Nó có thể quan sát và phối hợp các cơ chế đó, nhưng mỗi cơ chế vẫn cần được cấu hình và thực thi đúng tại tầng tương ứng.

## 7. Kiểm thử interceptor

Nên kiểm tra hành vi quan sát được qua gRPC runtime, không chỉ gọi trực tiếp phương thức interceptor.

Các trường hợp cốt lõi:

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Client interceptor gắn request ID | Server interceptor đọc được đúng key/value |
| Request thiếu metadata bắt buộc | Server trả status theo policy, implementation không được gọi |
| Token sai | **UNAUTHENTICATED**, không tiết lộ token |
| Principal không đủ quyền | **PERMISSION_DENIED** |
| RPC thành công | Client nhận response và status OK |
| RPC thất bại | Client interceptor quan sát status cuối cùng |
| Server thêm custom trailer | Client đọc được trailer nếu transport chuyển được |
| Caller hủy stream | Callback hủy được xử lý, nguồn dữ liệu được cleanup |
| Nhiều RPC đồng thời | Request ID/principal/metrics không bị trộn giữa call |

### 7.1. Kiểm thử in-process với JUnit

Ví dụ đơn giản dùng **InProcessServerBuilder** và **InProcessChannelBuilder** để xác minh request ID được truyền vào Context và service trả response:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import dev.example.orders.v1.GetOrderRequest;
import dev.example.orders.v1.GetOrderResponse;
import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.ClientInterceptors;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

class InterceptorIntegrationTest {

    @Test
    void requestIdIsAvailableInsideServiceCall() throws Exception {
        String name = InProcessServerBuilder.generateName();

        OrderServiceGrpc.OrderServiceImplBase endpoint =
                new OrderServiceGrpc.OrderServiceImplBase() {
                    @Override
                    public void getOrder(
                            GetOrderRequest request,
                            StreamObserver<GetOrderResponse> observer) {

                        String requestId =
                                RequestContextServerInterceptor
                                        .REQUEST_ID_CONTEXT.get();

                        if (requestId == null || requestId.isBlank()) {
                            observer.onError(
                                    io.grpc.Status.INTERNAL
                                            .withDescription("Missing context")
                                            .asRuntimeException());
                            return;
                        }

                        observer.onNext(
                                GetOrderResponse.newBuilder()
                                        .setOrderId(request.getOrderId())
                                        .setState("PENDING")
                                        .build());
                        observer.onCompleted();
                    }
                };

        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(
                        ServerInterceptors.intercept(
                                endpoint,
                                new RequestContextServerInterceptor()))
                .build()
                .start();

        ManagedChannel baseChannel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            OrderServiceGrpc.OrderServiceBlockingStub stub =
                    OrderServiceGrpc.newBlockingStub(
                            ClientInterceptors.intercept(
                                    baseChannel,
                                    new RequestIdClientInterceptor()));

            GetOrderResponse response = stub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("order-42")
                            .build());

            assertEquals("order-42", response.getOrderId());
        } finally {
            baseChannel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Test giả định các interceptor ở mục 2 và 3 được đặt trong package/import phù hợp. Cần dependency **grpc-inprocess** tương thích phiên bản grpc-java và JUnit 5. **directExecutor()** tiện cho test nhỏ, nhưng không mô phỏng concurrency, thread pool hoặc transport mạng thật.

### 7.2. Kiểm thử qua transport thật

In-process test không xác minh TLS, ALPN, proxy HTTP/2, giới hạn metadata hoặc behavior khi TCP đứt. Với môi trường production, nên có kiểm thử bổ sung qua cấu hình transport thật, đặc biệt khi interceptor liên quan tới authorization, credentials, tracing hoặc trailers.

## 8. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| Server không đọc được request ID | Client interceptor chưa gắn vào Channel dùng bởi stub hoặc key khác nhau | Kiểm tra wiring và Metadata.Key |
| Server trả INVALID_ARGUMENT dù client có ID | Header bị proxy lọc hoặc interceptor đọc sai key | Kiểm tra metadata tại từng hop |
| Client không nhận callback kết thúc | Interceptor bọc listener nhưng quên gọi super.onClose(...) | Chuyển tiếp callback đầy đủ |
| Status bị đổi thành INTERNAL/UNKNOWN | Interceptor bắt exception rồi gói lại không đúng | Giữ status gốc; chỉ ánh xạ lỗi có chủ đích |
| Principal/request ID lẫn giữa RPC | Lưu state trong field mutable dùng chung | Dùng state theo call và gRPC Context |
| Token xuất hiện trong log | Ghi toàn bộ Metadata hoặc exception | Redact/allowlist key, không log credential |
| Metrics bị nhân đôi | Cùng interceptor được đăng ký nhiều lần | Kiểm tra Channel wrapper và server registration |
| Latency tăng sau khi bật interceptor | Có I/O/blocking hoặc serialization không cần thiết | Giữ interceptor nhẹ, đo chi phí từng callback |
| Server interceptor từ chối nhưng handler vẫn chạy | Đã gọi next.startCall(...) trước khi quyết định từ chối | Đóng ServerCall và trả listener rỗng trước khi chuyển tiếp |
| Hành vi thay đổi khi thêm interceptor mới | Thứ tự bọc không được xác định/test | Khai báo thứ tự và kiểm thử tổ hợp |

Khi debug, kiểm tra theo đường đi: **stub có dùng Channel wrapper không?** → **ClientInterceptor có chạy không?** → **headers có tới server không?** → **ServerInterceptor có được đăng ký cho service không?** → **Context có được gắn trong callback không?** → **listener/status có được chuyển tiếp không?**.

## 9. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo **RequestIdClientInterceptor** để gắn **x-request-id** riêng cho mỗi RPC.
2. Tạo **RequestContextServerInterceptor** để kiểm tra request ID và truyền vào Context; viết handler đọc giá trị đó.
3. Tạo **RpcMetricsClientInterceptor** ghi nhận full method name, latency và **Status.Code**; dùng recorder thread-safe và không đưa ID cá nhân vào metric label.
4. Tạo interceptor xác thực token ở server. Phân biệt **UNAUTHENTICATED** với **PERMISSION_DENIED**, không tin role do client tự gửi.
5. Đăng ký client interceptor qua Channel wrapper và server interceptor qua service wrapper trong ứng dụng Spring; xác nhận không đăng ký trùng.
6. Viết test in-process cho request ID hợp lệ/thiếu, status thành công/lỗi và nhiều RPC đồng thời.
7. Chạy kiểm thử transport thật để xác minh TLS, proxy và metadata khi triển khai.

### Câu hỏi tự kiểm tra

**1. ClientInterceptor và ServerInterceptor khác nhau ở đâu?**  
ClientInterceptor chạy quanh call do client tạo, có thể gắn request metadata và quan sát response/status. ServerInterceptor chạy trước service implementation, có thể kiểm tra headers, xác thực và tạo Context.

**2. Vì sao không nên lưu request ID vào field của interceptor singleton?**  
Một interceptor có thể phục vụ nhiều RPC đồng thời. Field mutable dùng chung có thể khiến state của call này ghi đè call khác.

**3. Nên dùng API nào để đưa principal đã xác minh tới handler?**  
Dùng **io.grpc.Context** và **Contexts.interceptCall(...)** để gắn dữ liệu theo RPC; tránh tin trực tiếp role header do caller gửi.

**4. Vì sao interceptor phải gọi super.onClose(...)?**  
Để listener của stub/caller nhận được status kết thúc. Nếu nuốt callback, caller có thể không nhận kết quả hoặc call không hoàn tất ở tầng ứng dụng.

**5. Có nên dùng interceptor để kiểm tra quyền xem từng đơn hàng không?**  
Interceptor phù hợp xác thực và policy chung. Quyền truy cập theo dữ liệu cụ thể thường cần service/domain layer sau khi đã có principal đáng tin.

**6. ClientInterceptor có thay thế CallCredentials không?**  
Không. CallCredentials là abstraction chuyên cho thông tin xác thực theo call; interceptor phù hợp với hành vi RPC dùng chung như tracing, request ID và metrics.

**7. In-process test có chứng minh TLS/proxy hoạt động đúng không?**  
Không. Nó kiểm tra gRPC API và routing trong process; TLS, ALPN, HTTP/2 proxy và lỗi TCP cần test trên transport thật.

## Tổng kết

**ClientInterceptor** và **ServerInterceptor** là các điểm mở rộng ở ranh giới RPC để thực thi hành vi dùng chung. Client interceptor thường gắn metadata và quan sát callback/status; server interceptor kiểm tra request headers, xác thực, tạo **Context** và bọc server call/listener. Trong Spring gRPC, đăng ký interceptor thông qua Channel wrapper hoặc service wrapper, giữ chúng nhẹ và thread-safe, chuyển tiếp đầy đủ callback và kiểm thử thứ tự thực thi. Interceptor giúp chuẩn hóa tracing, metrics và security ở tầng RPC, trong khi quy tắc nghiệp vụ vẫn thuộc service/domain layer.


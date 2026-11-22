# Interceptor dùng chung và cấu hình riêng

Trong một ứng dụng Spring gRPC, nhiều RPC cần cùng các xử lý xuyên suốt như xác thực, tracing, metrics, correlation ID hoặc ghi nhận audit. Một số service hoặc method lại có quy tắc riêng, chẳng hạn kiểm tra quyền theo nghiệp vụ, thêm tenant context hay giới hạn truy cập. Interceptor cho phép đặt các xử lý này ở đúng phạm vi mà không lặp lại trong từng service implementation.

Điểm cần quyết định là **phạm vi áp dụng**: interceptor dùng chung cho toàn server hoặc toàn client channel; interceptor chỉ gắn với một service; hay interceptor chỉ áp dụng cho một nhóm stub/method. Chọn phạm vi đúng giúp chính sách nhất quán, tránh áp dụng trùng và giữ cho các service độc lập.

## 1. Các phạm vi cấu hình

gRPC Java có interceptor phía server và phía client. Mỗi phía có thể áp dụng ở phạm vi rộng hoặc hẹp:

| Phạm vi | Phía server | Phía client | Phù hợp với |
| --- | --- | --- | --- |
| Toàn server/channel | `ServerBuilder.intercept(...)` | `ManagedChannelBuilder.intercept(...)` | Tracing, metrics, correlation, chính sách chung |
| Một service | Bọc `ServerServiceDefinition` bằng `ServerInterceptors.intercept(...)` | Tạo channel wrapper riêng cho stub của service | Authorization hoặc audit đặc thù service |
| Một nhóm method | Interceptor kiểm tra full method name rồi áp dụng rule | Client interceptor kiểm tra method descriptor | Chính sách chỉ dành cho một số RPC |
| Một stub/client flow | Không phải phạm vi đăng ký server; service policy thường phù hợp hơn | `ClientInterceptors.intercept(channel, ...)` rồi tạo stub trên channel wrapper | Header, tenant hoặc telemetry chỉ dành cho một client flow |

Phạm vi rộng giảm cấu hình lặp và tạo baseline thống nhất. Phạm vi hẹp giúp áp dụng quy tắc chuyên biệt mà không ảnh hưởng service khác. Có thể kết hợp chúng, nhưng phải biết interceptor nào đang chạy ở mỗi RPC.

## 2. Interceptor dùng chung phía server

Interceptor gắn vào `ServerBuilder` được áp dụng cho các service được đăng ký trên server đó. Đây là vị trí phù hợp cho những concern cần nhất quán trên toàn server, ví dụ:

- Tạo hoặc chuẩn hóa correlation ID.
- Đưa trace context vào gRPC `Context`.
- Đếm request, latency và status code.
- Xác thực danh tính chung cho server.
- Ghi nhận thông tin audit ở mức kỹ thuật.

Ví dụ dùng grpc-java API:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.ServerInterceptor;

ServerBuilder<?> builder = ServerBuilder.forPort(8443);
builder.intercept(traceInterceptor);
builder.intercept(metricsInterceptor);
builder.intercept(requestContextInterceptor);

builder.addService(new OrdersService());
builder.addService(new InventoryService());

Server server = builder.build().start();
```

Ba interceptor được cấu hình ở server builder nên tạo baseline cho cả `OrdersService` và `InventoryService`. Các interceptor nên dùng dependency được inject, xử lý từng call độc lập và không giữ dữ liệu request trong field mutable dùng chung.

Không phải mọi interceptor đều nên áp dụng toàn server. Ví dụ một quy tắc chỉ dành cho `OrderService` không nên được gắn global rồi xử lý bằng nhiều nhánh ngoại lệ nếu có thể cấu hình đúng ở service scope. Với health/reflection hoặc endpoint nội bộ, xác định rõ chúng có chịu global authentication/audit hay cần một chính sách riêng; đừng vô tình khóa health probe của nền tảng.

## 3. Interceptor riêng cho một service

Khi một service có quy tắc riêng, bọc `ServerServiceDefinition` trước khi đăng ký:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.ServerInterceptors;
import io.grpc.ServerServiceDefinition;

ServerServiceDefinition ordersDefinition =
    ServerInterceptors.intercept(
        ordersService.bindService(),
        ordersAuthorizationInterceptor,
        ordersAuditInterceptor);

ServerBuilder<?> builder = ServerBuilder.forPort(8443);
builder.intercept(globalTraceInterceptor);
builder.intercept(globalMetricsInterceptor);
builder.addService(ordersDefinition);
builder.addService(inventoryService);

Server server = builder.build().start();
```

Trong ví dụ, `OrdersService` có authorization và audit riêng; `InventoryService` chỉ nhận interceptor global. Các interceptor service-specific không làm thay đổi cấu hình của service còn lại.

Phạm vi này phù hợp khi:

- `OrderService` yêu cầu role hoặc scope riêng.
- Một service cần audit chi tiết hơn vì thao tác có tác động tài chính.
- Một service cần giới hạn concurrency hoặc quota theo chính sách riêng.
- Một service có metadata contract riêng, ví dụ tenant hoặc partner identity.

Nếu nhiều service cùng dùng một chính sách, có thể tái sử dụng cùng interceptor instance hoặc một factory tạo cấu hình theo service. Tuy nhiên, interceptor phải biết service/method hiện tại từ call descriptor; không suy ra service identity từ tên bean Spring.

## 4. Cấu hình interceptor dùng chung và riêng trong Spring

Trong Spring, interceptor thường là bean để constructor injection các dependency như `Tracer`, `MeterRegistry`, `AuthenticationService` hoặc `AuditService`. Ví dụ:

```java
import io.grpc.ServerInterceptor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GrpcInterceptorConfiguration {

    @Bean
    ServerInterceptor traceInterceptor(TraceService traceService) {
        return new TraceServerInterceptor(traceService);
    }

    @Bean
    ServerInterceptor metricsInterceptor(GrpcMetrics metrics) {
        return new MetricsServerInterceptor(metrics);
    }

    @Bean
    ServerInterceptor ordersAuthorizationInterceptor(
            OrdersAuthorization authorization) {
        return new OrdersAuthorizationInterceptor(authorization);
    }
}
```

Đây là cách khai báo dependency bằng Spring; việc gắn bean vào server hoặc service phải thực hiện qua cơ chế cấu hình server mà ứng dụng đang dùng. Nếu starter Spring gRPC quản lý server lifecycle, hãy dùng server customizer/configuration hook được phiên bản starter hỗ trợ. Không tự tạo một `Server` thứ hai song song chỉ để gắn interceptor, vì như vậy có thể mở thêm port và tạo hai lifecycle độc lập.

Với server được ứng dụng tự khởi tạo bằng grpc-java, inject các bean vào cấu hình server rồi gọi `builder.intercept(...)` hoặc bọc service definition trước `addService(...)`. Dù dùng starter hay bootstrap thủ công, nên tập trung việc đăng ký ở một nơi để dễ nhìn thấy thứ tự và phạm vi interceptor.

Interceptor bean mặc định thường là singleton. Vì cùng một instance có thể xử lý nhiều RPC đồng thời, chỉ giữ dependency thread-safe và cấu hình bất biến. Dữ liệu theo request phải đặt trong biến cục bộ hoặc gRPC `Context`, không lưu vào field rồi ghi đè giữa các call.

## 5. Interceptor dùng chung phía client

Client interceptor gắn vào `ManagedChannelBuilder` áp dụng cho các RPC đi qua channel. Đây là nơi thích hợp để gắn trace context, client metrics, user-agent hoặc metadata kỹ thuật chung:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

ManagedChannel channel = ManagedChannelBuilder
    .forTarget("dns:///orders.default.svc.cluster.local:8443")
    .intercept(clientTracingInterceptor)
    .intercept(clientMetricsInterceptor)
    .useTransportSecurity()
    .build();

OrderServiceGrpc.OrderServiceBlockingStub ordersStub =
    OrderServiceGrpc.newBlockingStub(channel);
```

Mọi stub dùng channel này sẽ đi qua các client interceptor đã gắn. Nếu cùng channel được tái sử dụng cho nhiều service, interceptor global cần giữ tính tổng quát và không tự thêm metadata chỉ đúng với một service.

Không gắn access token người dùng cố định vào singleton interceptor nếu token thay đổi theo caller hoặc request. Hãy lấy credential từ context/call credential phù hợp với từng call, hoặc từ provider thread-safe có khả năng refresh. Tránh để token của một request lọt sang request khác khi channel được dùng đồng thời.

## 6. Interceptor riêng cho một stub hoặc nhóm RPC

Nếu chỉ một client flow cần header hoặc telemetry riêng, tạo channel wrapper với `ClientInterceptors.intercept(...)` rồi tạo stub trên wrapper đó:

```java
import io.grpc.Channel;
import io.grpc.ClientInterceptors;

Channel ordersOnlyChannel = ClientInterceptors.intercept(
    sharedChannel,
    ordersTenantInterceptor,
    ordersClientAuditInterceptor);

OrderServiceGrpc.OrderServiceBlockingStub ordersStub =
    OrderServiceGrpc.newBlockingStub(ordersOnlyChannel);

InventoryGrpc.InventoryBlockingStub inventoryStub =
    InventoryGrpc.newBlockingStub(sharedChannel);
```

Trong ví dụ, chỉ `ordersStub` sử dụng channel wrapper và nhận interceptor riêng; `inventoryStub` tiếp tục dùng channel chung. Cả hai vẫn có thể dùng cùng transport/channel gốc, tùy cách wrapper được tạo.

Một interceptor gắn ở channel wrapper có thể kiểm tra method descriptor để chỉ áp dụng cho một số method. Cách đó hữu ích khi một service có nhiều RPC với chính sách khác nhau, nhưng nên dùng bảng rule rõ ràng thay vì nhiều điều kiện chuỗi rải rác.

## 7. Lọc theo service và method

Ở server, method descriptor cung cấp full method name để interceptor xác định RPC hiện tại:

```java
import io.grpc.*;

final class OrdersAuthorizationInterceptor
        implements ServerInterceptor {

    private final OrdersAuthorization authorization;

    OrdersAuthorizationInterceptor(OrdersAuthorization authorization) {
        this.authorization = authorization;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor()
            .getFullMethodName();

        if (method.equals("acme.orders.v1.OrderService/CancelOrder")
                && !authorization.mayCancel(headers)) {
            call.close(
                Status.PERMISSION_DENIED
                    .withDescription("Not allowed to cancel this order"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }

        return next.startCall(call, headers);
    }
}
```

Đoạn code minh họa việc chặn một method trước khi chuyển call tới service handler. Trong implementation thật, `mayCancel(...)` phải xác minh identity/credential đã được xác thực; không tin một header tenant hoặc user ID do caller tự khai. Nên dùng `Context` để truyền principal đã xác thực từ authentication interceptor tới authorization interceptor.

Full method name trong grpc-java có dạng `package.Service/Method`, thường không có dấu `/` đầu tiên. HTTP/2 path có dấu `/` đầu tiên. Dùng đúng định dạng khi so khớp hoặc cấu hình rule.

Với policy phức tạp, ưu tiên map method descriptor sang policy object hoặc annotation/config đã kiểm tra lúc khởi động. Không parse tên method theo substring dễ gây match nhầm service/version.

## 8. Thứ tự và composition của interceptor

Interceptor được ghép thành một chuỗi xử lý quanh RPC. Thứ tự ảnh hưởng tới:

- Authentication có chạy trước authorization không.
- Trace context có sẵn khi metrics/audit ghi nhận call không.
- Exception được chuyển thành gRPC `Status` ở lớp nào.
- Metadata có bị chuẩn hóa hoặc loại bỏ trước khi interceptor khác đọc không.
- Call bị từ chối có được ghi audit/metrics hay không.

Ví dụ một chuỗi server thường cần thể hiện các trách nhiệm: trace/context → authentication → authorization → audit/metrics → service handler. Đây là thứ tự mục tiêu về mặt logic; thứ tự callback thực tế còn phụ thuộc cách builder và wrapper ghép interceptor trong phiên bản grpc-java đang dùng. Hãy kiểm tra bằng test ghi nhận thứ tự trước/sau, không dựa vào suy đoán từ thứ tự khai báo.

Tránh đăng ký cùng interceptor ở cả server-global và service-specific nếu không chủ đích. Một request có thể bị đo metrics hai lần, ghi audit trùng hoặc xử lý metadata lặp. Nếu interceptor cần chạy ở nhiều scope, xác định rõ trách nhiệm của từng instance và test số lần thực thi.

## 9. Xử lý lỗi, metadata và Context an toàn

Interceptor thường là nơi phù hợp để:

- Đọc metadata đầu vào như trace ID hoặc credential.
- Xác thực credential và tạo principal đáng tin cậy.
- Đặt principal, tenant đã xác minh hoặc trace context vào `io.grpc.Context`.
- Đếm metrics và audit theo kết quả call.
- Đóng call bằng status phù hợp khi bị từ chối.

Một số nguyên tắc:

- Không tin `x-user-id`, `x-role` hoặc `x-tenant-id` chỉ vì chúng xuất hiện trong metadata.
- Không log authorization header, token, cookie hoặc dữ liệu nhạy cảm.
- Dùng status như `UNAUTHENTICATED` cho credential thiếu/không hợp lệ và `PERMISSION_DENIED` cho principal hợp lệ nhưng không đủ quyền.
- Giữ metadata nhỏ; không truyền object nghiệp vụ lớn qua header.
- Đảm bảo Context được gắn trong phạm vi call và không rò sang thread/request khác.
- Với streaming RPC, xử lý lifecycle listener/callback và lỗi bất đồng bộ, không chỉ xử lý lúc bắt đầu call.

Interceptor không nên chứa logic nghiệp vụ như tính giá, thay đổi trạng thái đơn hàng hoặc truy cập repository để hoàn thành use case. Những việc đó thuộc service/application layer.

## 10. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Interceptor không chạy | Bean được tạo nhưng chưa gắn vào server/channel | Kiểm tra hook đăng ký và phạm vi builder |
| Service khác cũng bị chặn | Policy riêng bị đăng ký global | Chuyển sang service-specific hoặc method-specific |
| Audit/metrics bị nhân đôi | Cùng interceptor được gắn ở nhiều scope | Kiểm tra chain và loại đăng ký trùng |
| Header của service này xuất hiện ở service khác | Dùng interceptor channel-wide cho metadata đặc thù | Tạo channel wrapper riêng hoặc kiểm tra method |
| User/tenant bị lẫn giữa request | Lưu request state trong field mutable của singleton | Dùng biến cục bộ và gRPC `Context` |
| Health probe bị `UNAUTHENTICATED` | Global auth chặn health service | Thiết kế allowlist/credential cho probe có chủ đích |
| Authorization không chạy đúng | Dùng nhầm service name hoặc full method format | Đối chiếu descriptor và `getFullMethodName()` |
| Thứ tự xử lý sai | Giả định thứ tự khai báo chính là thứ tự callback | Viết test xác nhận chain thực tế |

## 11. Kiểm thử phạm vi interceptor

Kiểm thử cần chứng minh cả interceptor được áp dụng và service ngoài phạm vi không bị ảnh hưởng:

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Server-global interceptor | Chạy cho mọi service đã đăng ký trên server |
| Service-specific interceptor | Chỉ chạy cho service được bọc |
| Method-specific rule | Chỉ method khớp full method name nhận policy riêng |
| Client channel interceptor | Chạy cho mọi stub/call qua channel |
| Client stub wrapper | Chỉ stub dùng wrapper nhận interceptor riêng |
| Authentication trước authorization | Authorization đọc được principal đã xác thực |
| Từ chối quyền | Call trả status đúng và audit/metrics được ghi theo policy |
| Health/reflection | Probe/công cụ vận hành hoạt động theo allowlist đã thiết kế |
| Concurrent calls | Không rò metadata hoặc principal giữa các request |
| Streaming call | Context và cleanup đúng trong toàn bộ lifecycle |
| Không đăng ký trùng | Metrics/audit không bị ghi hai lần |

Có thể dùng in-process server/channel để kiểm tra scope và thứ tự interceptor. Thêm integration test với transport thực khi cần xác minh TLS, metadata qua proxy hoặc client channel được starter tạo ra. Với Spring, kiểm tra ApplicationContext chỉ tạo đúng bean và hook cấu hình thực sự gắn bean vào server/channel.

## 12. Bài tập vận dụng

Một ứng dụng Spring gRPC có `OrderService`, `InventoryService` và health service. Tất cả cần tracing và metrics. `OrderService` cần authorization theo role; riêng `CancelOrder` cần audit chi tiết. Client dùng chung một channel cho cả Orders và Inventory, nhưng chỉ Orders cần metadata tenant.

**Yêu cầu:**

1. Chọn interceptor global phía server cho tracing/metrics.
2. Gắn authorization riêng cho `OrderService` và audit riêng cho `CancelOrder`.
3. Quyết định health service có nằm trong global authentication policy hay dùng allowlist/probe credential.
4. Gắn tracing/metrics chung cho client channel; tạo channel wrapper cho `OrderService` để thêm tenant metadata.
5. Xác định cách truyền principal đã xác thực qua gRPC `Context`.
6. Kiểm tra interceptor singleton có thread-safe và không giữ request state trong field.
7. Viết test xác nhận phạm vi, thứ tự, không đăng ký trùng và không rò tenant giữa hai stub.

**Câu hỏi tự kiểm tra:**

- Khi nào nên dùng `ServerBuilder.intercept(...)` và khi nào dùng `ServerInterceptors.intercept(...)`?
- Interceptor client gắn vào channel khác gì interceptor chỉ gắn vào channel wrapper của một stub?
- Vì sao interceptor dùng chung phải thread-safe?
- Làm thế nào áp dụng policy riêng cho một method?
- Vì sao không nên tin user/tenant ID chỉ từ metadata?
- Thứ tự interceptor ảnh hưởng authentication, authorization và audit ra sao?
- Làm thế nào tránh interceptor chạy hai lần do cấu hình trùng?
- Khi nào nên dùng interceptor và khi nào logic thuộc service layer?

**Ghi nhớ:** Interceptor dùng chung tạo baseline cho server hoặc channel; interceptor riêng giới hạn chính sách vào service, method hoặc stub cần nó. Trong Spring gRPC, khai báo interceptor bằng dependency injection nhưng phải gắn chúng qua đúng lifecycle/configuration hook của server hoặc channel. Xác định rõ phạm vi, thứ tự, thread safety và chính sách metadata; kiểm thử cả nơi interceptor phải chạy lẫn nơi nó không được chạy.

# Kiểm thử allow, deny và missing context

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt ba kết quả authorization: allow, deny và missing context.
- Chọn status phù hợp cho principal đã xác thực nhưng thiếu quyền và trường hợp chưa có principal.
- Viết unit test cho permission policy và integration test qua gRPC runtime.
- Xác minh interceptor thực sự chặn handler khi deny, thay vì chỉ trả status sau khi business code đã chạy.
- Kiểm tra thứ tự authentication trước authorization và việc dùng chung Context key.
- Kiểm thử method chưa có policy, metadata giả mạo, tenant/resource boundary và request đồng thời.
- Kiểm thử authorization của streaming RPC, cancellation và cleanup.
- Tổ chức test fixture có thể tái sử dụng trong ứng dụng Spring gRPC.

## 1. Ba trạng thái cần phân biệt

Trong **SPRING_GRPC**, authentication xác minh caller và tạo principal; authorization quyết định principal có được gọi method hoặc thao tác trên resource hay không. Khi kiểm thử, cần phân biệt ba trạng thái thường bị nhầm lẫn:

| Trạng thái | Principal trong Context | Quyền cần thiết | Kết quả mong đợi |
| --- | --- | --- | --- |
| **Allow** | Có principal đã xác minh | Đủ permission | RPC tiếp tục tới handler |
| **Deny** | Có principal đã xác minh | Thiếu permission hoặc policy từ chối | **PERMISSION_DENIED**, handler không chạy |
| **Missing context** | Không có principal | Không thể đánh giá quyền của caller | **UNAUTHENTICATED**, handler không chạy |

**Missing context không giống deny.** Deny nghĩa là server biết caller là ai nhưng policy không cho phép hành động. Missing context nghĩa là authorization không có principal đáng tin cậy; thường authentication chưa chạy, credential không hợp lệ hoặc Context không được truyền đúng.

Phân biệt hai trường hợp giúp phát hiện lỗi cấu hình interceptor. Nếu mọi test chỉ kiểm tra PERMISSION_DENIED, lỗi authentication không đặt principal có thể bị che khuất.

~~~mermaid
flowchart TD
    A["RPC tới server"] --> B{"Principal đã xác minh trong Context?"}
    B -- "Không" --> C["UNAUTHENTICATED"]
    B -- "Có" --> D{"Policy cho phép method/resource?"}
    D -- "Không" --> E["PERMISSION_DENIED"]
    D -- "Có" --> F["Gọi service handler"]
    C --> G["Handler không chạy"]
    E --> G
    F --> H["Assert business result"]
~~~

Một test authorization đúng cần kiểm tra cả **status** và **side effect**. Chỉ thấy client nhận PERMISSION_DENIED chưa chứng minh handler không chạy trước khi call bị đóng.

## 2. Xác định ranh giới cần kiểm thử

Authorization thường được triển khai ở nhiều lớp. Mỗi lớp cần loại test phù hợp:

| Thành phần | Điều cần xác minh | Loại test phù hợp |
| --- | --- | --- |
| Permission policy | Mapping method/resource tới permission | Unit test |
| Principal và Context key | Principal được đặt và đọc bằng cùng key | Unit test và interceptor test |
| Authentication interceptor | Credential hợp lệ tạo principal; credential sai bị từ chối | Interceptor test |
| Authorization interceptor | Allow/deny/missing context và không gọi handler khi deny | Unit test với fake call hoặc in-process test |
| gRPC server pipeline | Thứ tự interceptor, status thực tế, generated stub | In-process integration test |
| Spring gRPC configuration | Bean/extension point và server thật dùng đúng interceptor | Spring application integration test |
| Resource authorization | Tenant, ownership và trạng thái domain | Application/repository integration test |
| Streaming handler | Mỗi message được kiểm tra và tài nguyên được cleanup | Streaming integration test |

Unit test policy chạy nhanh và giúp kiểm tra nhiều mapping. Tuy nhiên nó không chứng minh interceptor đã đăng ký đúng, Context đã được truyền qua listener hoặc client thực sự nhận status dự kiến. Vì vậy cần ít nhất một lớp integration test đi qua gRPC runtime.

## 3. Kiểm thử permission policy bằng unit test

Policy thường nhận principal và full method name từ server-side MethodDescriptor. Test nên bao gồm method được cấp quyền, method thiếu quyền và method không có mapping.

Ví dụ policy đơn giản:

~~~java
public final class GrpcMethodPolicy {

    private final Map<String, String> requiredPermissions = Map.of(
            OrderServiceGrpc.getGetOrderMethod().getFullMethodName(),
            "orders:read",
            OrderServiceGrpc.getCancelOrderMethod().getFullMethodName(),
            "orders:cancel");

    public boolean allows(
            GrpcPrincipal principal,
            String fullMethodName) {

        if (principal == null) {
            return false;
        }

        String required = requiredPermissions.get(fullMethodName);
        return required != null
                && principal.hasPermission(required);
    }
}
~~~

JUnit 5:

~~~java
class GrpcMethodPolicyTest {

    private final GrpcMethodPolicy policy = new GrpcMethodPolicy();

    @Test
    void allowsMethodWhenPrincipalHasRequiredPermission() {
        GrpcPrincipal principal = new GrpcPrincipal(
                "user-1",
                "tenant-a",
                Set.of("orders:read"));

        String method =
                OrderServiceGrpc.getGetOrderMethod().getFullMethodName();

        assertTrue(policy.allows(principal, method));
    }

    @Test
    void deniesMethodWhenPermissionIsMissing() {
        GrpcPrincipal principal = new GrpcPrincipal(
                "user-1",
                "tenant-a",
                Set.of("orders:read"));

        String method =
                OrderServiceGrpc.getCancelOrderMethod().getFullMethodName();

        assertFalse(policy.allows(principal, method));
    }

    @Test
    void deniesMethodWithoutExplicitPolicy() {
        GrpcPrincipal principal = new GrpcPrincipal(
                "user-1",
                "tenant-a",
                Set.of("orders:read", "orders:cancel"));

        assertFalse(policy.allows(
                principal,
                "demo.admin.v1.AdminService/DisableAccount"));
    }
}
~~~

Ba test kiểm tra ba thuộc tính cốt lõi:

- Permission đúng cho phép đúng method.
- Có principal nhưng thiếu permission phải deny.
- Method chưa được khai báo phải deny theo **deny-by-default**.

Không dùng tên method do client tự khai trong metadata làm input của policy. Trong production, full method name nên lấy từ **call.getMethodDescriptor().getFullMethodName()**. Unit test có thể truyền chuỗi trực tiếp để kiểm tra mapping; integration test sẽ xác minh interceptor lấy đúng descriptor.

## 4. Test interceptor phải kiểm tra handler có chạy hay không

Authorization interceptor thường có hai nhánh:

- Allow: gọi **next.startCall(call, headers)**.
- Deny hoặc missing context: đóng call và trả listener rỗng, không gọi next.

Có thể dùng fake ServerCall/ServerCallHandler để unit test nhánh này, nhưng fake phải mô phỏng đúng hành vi cần kiểm tra. Một cách mạnh hơn là gọi qua in-process gRPC server và dùng bộ đếm trong service implementation.

Ví dụ service có side-effect counter:

~~~java
public final class TestOrderService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final AtomicInteger invocations;

    public TestOrderService(AtomicInteger invocations) {
        this.invocations = invocations;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {

        invocations.incrementAndGet();

        responseObserver.onNext(
                GetOrderResponse.newBuilder()
                        .setOrderId(request.getOrderId())
                        .build());
        responseObserver.onCompleted();
    }
}
~~~

Với một test deny, assert cả hai điều kiện:

~~~java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> blockingStub.getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("order-1")
                        .build()));

assertEquals(
        Status.Code.PERMISSION_DENIED,
        error.getStatus().getCode());

assertEquals(0, invocations.get());
~~~

Bộ đếm nên đại diện cho điểm bắt đầu business handler hoặc side effect quan trọng. Với use case ghi dữ liệu, ngoài invocation counter, kiểm tra database không thay đổi, outbox không có event và downstream mock không được gọi.

## 5. Dùng in-process gRPC để kiểm tra status thực tế

grpc-java cung cấp in-process transport để dựng server và channel trong cùng process. Test không cần mở TCP port nhưng vẫn đi qua gRPC dispatch, interceptor và generated stub.

Các dependency test thường cần:

- grpc-inprocess cùng phiên bản với grpc-core/grpc-stub của ứng dụng.
- JUnit Jupiter.
- Mockito nếu cần verify dependency không được gọi.
- Spring Boot test nếu cần khởi động cấu hình Spring gRPC thực tế.

Ví dụ khung fixture:

~~~java
class AuthorizationGrpcTest {

    private Server server;
    private ManagedChannel channel;
    private OrderServiceGrpc.OrderServiceBlockingStub blockingStub;
    private final AtomicInteger invocations = new AtomicInteger();

    private void startServer(GrpcPrincipal principal) throws IOException {
        String serverName = InProcessServerBuilder.generateName();

        ServerInterceptor authorization =
                new AuthorizationServerInterceptor(methodPolicy);

        ServerServiceDefinition securedDefinition;

        if (principal == null) {
            securedDefinition = ServerInterceptors.interceptForward(
                    new TestOrderService(invocations).bindService(),
                    authorization);
        } else {
            ServerInterceptor testAuthentication =
                    new PrincipalTestInterceptor(principal);

            securedDefinition = ServerInterceptors.interceptForward(
                    new TestOrderService(invocations).bindService(),
                    testAuthentication,
                    authorization);
        }

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(securedDefinition)
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        blockingStub = OrderServiceGrpc.newBlockingStub(channel);
    }

    @AfterEach
    void stopServer() {
        if (channel != null) {
            channel.shutdownNow();
        }
        if (server != null) {
            server.shutdownNow();
        }
    }
}
~~~

**PrincipalTestInterceptor** là test fixture chỉ dùng để mô phỏng kết quả authentication. Nó đặt principal vào đúng Context key:

~~~java
public final class PrincipalTestInterceptor implements ServerInterceptor {

    private final GrpcPrincipal principal;

    public PrincipalTestInterceptor(GrpcPrincipal principal) {
        this.principal = principal;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        Context context = Context.current().withValue(
                GrpcSecurityContext.PRINCIPAL,
                principal);

        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

Fixture này giúp kiểm tra authorization độc lập với JWT hoặc mTLS. Nó không thay thế test authentication thật; nên có test riêng cho token/certificate hợp lệ, sai chữ ký, hết hạn và sai audience.

Tên API và dependency phải cùng phiên bản grpc-java mà module sử dụng. Nếu Spring gRPC starter đã quản lý server, không dựng thêm server production trong test; dùng extension point hoặc Spring test context để xác minh chính cấu hình mà ứng dụng sẽ chạy.

## 6. Test allow: principal đủ quyền

Test allow cần xác minh RPC thành công và handler thực sự được gọi:

~~~java
@Test
void allowsCallWhenPrincipalHasPermission() throws Exception {
    GrpcPrincipal principal = new GrpcPrincipal(
            "user-1",
            "tenant-a",
            Set.of("orders:read"));

    startServer(principal);

    GetOrderResponse response = blockingStub.getOrder(
            GetOrderRequest.newBuilder()
                    .setOrderId("order-1")
                    .build());

    assertEquals("order-1", response.getOrderId());
    assertEquals(1, invocations.get());
}
~~~

Test này chứng minh principal được đặt trong Context trước khi authorization chạy và policy nhận được permission mong muốn. Nếu test trả UNAUTHENTICATED, kiểm tra Context key và thứ tự interceptor trước khi sửa policy.

Một allow test cũng nên kiểm tra resource scope. Principal có orders:read nhưng chỉ thuộc tenant A không được đọc order tenant B. Method permission đủ để gọi GetOrder, nhưng resource authorization vẫn có thể từ chối.

## 7. Test deny: principal tồn tại nhưng thiếu permission

Deny cần có principal hợp lệ nhưng tập permission không đáp ứng method:

~~~java
@Test
void deniesCallWhenPrincipalLacksPermission() throws Exception {
    GrpcPrincipal principal = new GrpcPrincipal(
            "user-1",
            "tenant-a",
            Set.of("orders:read"));

    startServer(principal);

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> blockingStub.cancelOrder(
                    CancelOrderRequest.newBuilder()
                            .setOrderId("order-1")
                            .build()));

    assertEquals(
            Status.Code.PERMISSION_DENIED,
            error.getStatus().getCode());

    assertEquals(0, invocations.get());
}
~~~

Điều quan trọng là test phải gửi RPC thực sự cần orders:cancel. Không chỉ gọi trực tiếp policy với một method string rồi kết luận interceptor bảo vệ endpoint.

Với mutation, kiểm tra thêm:

- Repository save/update không được gọi.
- Database state giữ nguyên.
- Outbox hoặc event publisher không nhận event.
- Payment/inventory client không được gọi.
- Audit ghi decision deny nhưng không ghi token hoặc payload nhạy cảm.

## 8. Test missing context: không có principal

Missing context cần được test riêng. Dựng server chỉ có authorization interceptor và không đăng ký test authentication interceptor:

~~~java
@Test
void rejectsCallWhenPrincipalIsMissing() throws Exception {
    startServer(null);

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> blockingStub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("order-1")
                            .build()));

    assertEquals(
            Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());

    assertEquals(0, invocations.get());
}
~~~

Test này xác minh authorization không tự tạo principal, không fallback sang user mặc định và không coi Context trống là allow.

Trong production, missing context có thể do authentication interceptor không được đăng ký, interceptor chạy sai thứ tự, dùng hai Context key khác nhau hoặc Context không được truyền qua callback. Vì vậy, khi test này fail, hãy kiểm tra pipeline và shared key trước khi thêm fallback.

Không dùng PERMISSION_DENIED cho trường hợp chưa xác minh được caller. UNAUTHENTICATED phản ánh đúng việc server chưa có principal đáng tin cậy.

## 9. Kiểm tra thứ tự interceptor và Context key dùng chung

Authentication phải chạy trước authorization. Integration test cần đăng ký interceptor theo thứ tự production và chứng minh authorization đọc được principal do authentication đặt.

~~~java
ServerServiceDefinition secured =
        ServerInterceptors.interceptForward(
                service.bindService(),
                authenticationInterceptor,
                authorizationInterceptor);
~~~

Các lỗi cần bắt:

- Authorization được đăng ký trước authentication nên Context chưa có principal.
- Authentication và authorization tạo hai Context key riêng dù cùng tên.
- Authentication đặt principal vào Context nhưng listener callback không được bọc đúng.
- Một interceptor khác ghi đè principal hoặc đặt principal không đúng nguồn.
- Spring configuration đăng ký interceptor hai lần hoặc chỉ áp dụng cho một service.

Có thể thêm test nhỏ xác nhận Context key dùng chung:

~~~java
assertSame(
        GrpcSecurityContext.PRINCIPAL,
        SecurityContextKeys.PRINCIPAL);
~~~

Chỉ cần một lớp sở hữu key. Tránh tạo key trùng tên ở nhiều module rồi dùng test để cố chứng minh chúng tương đương; chúng là các key khác nhau.

## 10. Test method không có policy và metadata giả mạo

Deny-by-default cần được xác minh bằng một method hợp lệ trong server nhưng chưa có mapping trong policy. Kết quả phải là PERMISSION_DENIED và handler không chạy.

Ngoài ra, gửi metadata giả như **x-method-name** với tên method được phép trong khi client gọi method quản trị. Authorization phải lấy tên method từ server-side descriptor:

~~~java
String actualMethod =
        call.getMethodDescriptor().getFullMethodName();
~~~

Test cần chứng minh:

1. Metadata khai tên GetOrder nhưng RPC thực tế là DisableAccount.
2. Policy vẫn đánh giá DisableAccount.
3. Caller thiếu permission quản trị nhận PERMISSION_DENIED.
4. Handler quản trị không chạy.
5. Audit ghi actual method từ descriptor; nếu lưu claimed method thì phải đánh dấu untrusted.

Không dùng metadata hoặc request field do client gửi làm nguồn xác định RPC đang thực thi.

## 11. Test tenant và resource authorization

Method allow không đồng nghĩa resource allow. Bổ sung test khi principal có permission chung nhưng resource thuộc tenant khác:

| Principal | Method permission | Resource | Kết quả |
| --- | --- | --- | --- |
| Tenant A | orders:read | Order thuộc A | Allow |
| Tenant A | orders:read | Order thuộc B | Deny hoặc NOT_FOUND theo contract |
| Tenant A | orders:cancel | Order A ở trạng thái có thể hủy | Allow |
| Tenant A | orders:cancel | Order A đã giao | FAILED_PRECONDITION |
| Không có principal | Không đánh giá | Bất kỳ resource nào | UNAUTHENTICATED |

Kiểm tra truy vấn repository có tenant predicate, ví dụ **findByTenantIdAndId**, thay vì tìm resource theo ID toàn cục rồi mới so sánh tenant ở Java. Với deny, xác minh không có mutation hoặc downstream call.

Nếu API dùng NOT_FOUND để che giấu resource ngoài tenant, test phải xác minh response nhất quán với resource không tồn tại trong tenant hiện tại và không làm lộ resource qua error detail hoặc log client.

## 12. Test Context isolation giữa các RPC đồng thời

Một lỗi nghiêm trọng là principal được lưu trong field mutable hoặc ThreadLocal không được cleanup. Khi hai RPC chạy đồng thời, request A có thể nhận principal của request B.

Test concurrency nên:

1. Tạo hai principal với subject và tenant khác nhau.
2. Gửi hai RPC đồng thời qua cùng server/service instance.
3. Dùng latch hoặc barrier để chồng lấp thời gian xử lý.
4. Ghi nhận principal mà từng handler đọc được.
5. Assert mỗi response và repository query dùng đúng tenant.
6. Lặp lại đủ lần để tăng khả năng phát hiện race condition.

Ví dụ kỳ vọng:

| RPC | Principal mong đợi | Tenant mong đợi |
| --- | --- | --- |
| Call A | user-a | tenant-a |
| Call B | user-b | tenant-b |

Không dùng Thread.sleep để cố tạo race một cách ngẫu nhiên. Dùng CountDownLatch, CyclicBarrier hoặc synchronization point trong test service để điều khiển thứ tự. Chạy test với executor thực tế hoặc executor nhiều thread; direct executor hữu ích cho test đơn giản nhưng không chứng minh mọi vấn đề concurrency.

Sau mỗi test, đóng channel/server và giải phóng executor. Không để task còn chạy giữ principal hoặc làm ảnh hưởng test kế tiếp.

## 13. Test streaming authorization và lifecycle

Với streaming RPC, kiểm thử cả quyền mở stream và quyền trên từng message/resource:

- Thiếu principal khi mở stream phải trả UNAUTHENTICATED và không tạo subscription.
- Principal thiếu method permission phải trả PERMISSION_DENIED trước khi handler khởi tạo stream.
- Client-streaming gửi message thuộc tenant được phép thì xử lý theo contract.
- Message tiếp theo tham chiếu tenant/resource khác phải bị từ chối trước side effect.
- Server-streaming chỉ subscribe nguồn dữ liệu đã scope tenant.
- Bidirectional stream kiểm tra từng command trước khi thực hiện.
- Client cancel hoặc deadline hết phải cleanup subscription, queue và worker.
- Hai stream đồng thời không chia sẻ principal hoặc tenant state.

Nếu contract hỗ trợ partial success, test response item-level cho message bị từ chối và xác minh stream chỉ tiếp tục trong trạng thái hợp lệ. Nếu contract yêu cầu terminate stream, assert status terminal và không có message/side effect sau đó.

Với cancellation, kiểm tra callback cleanup được gọi đúng một lần hoặc cleanup idempotent. Không chỉ assert client đã cancel; cần verify subscription và tài nguyên server đã được giải phóng.

## 14. Test error mapping và status ổn định

Các status cần phân biệt:

| Điều kiện | Status |
| --- | --- |
| Principal thiếu hoặc credential chưa xác minh | UNAUTHENTICATED |
| Principal hợp lệ nhưng thiếu permission | PERMISSION_DENIED |
| Resource ngoài phạm vi và được che giấu theo contract | NOT_FOUND |
| Resource ở trạng thái không thể thực hiện action | FAILED_PRECONDITION |
| Policy dependency không thể đánh giá | UNAVAILABLE hoặc DEADLINE_EXCEEDED |

Test dựa trên **Status.Code** và reason code ổn định, không parse status description tự do. Description có thể thay đổi ngôn ngữ hoặc cách diễn đạt; không nên là API contract cho client.

Với policy dependency lỗi, test phải chứng minh fail-closed: không có permission decision thì không được gọi business handler hoặc downstream. Với UNAVAILABLE, retry chỉ được thực hiện theo policy có giới hạn và operation an toàn.

## 15. Tổ chức test trong ứng dụng Spring gRPC

Có thể chia test thành ba tầng:

**Unit test** kiểm tra policy mapping, principal helper và exception/status mapper. Các test này không cần khởi động Spring hoặc tạo server.

**In-process integration test** kiểm tra grpc-java dispatch, generated stub, interceptor chain, Context và status. Đây là tầng phù hợp để chạy nhiều allow/deny/missing context case nhanh.

**Spring application integration test** khởi động application context và cấu hình gRPC server theo đúng starter đang dùng. Test xác minh interceptor bean/extension point thực sự được đăng ký, thứ tự đúng và các service cần bảo vệ đều đi qua chain.

Một lỗi thường gặp là test tự tạo interceptor chain đúng nhưng cấu hình Spring production quên đăng ký interceptor. In-process test độc lập vẫn PASS; chỉ test khởi động cấu hình Spring mới phát hiện lỗi wiring đó.

Giữ test fixture nhỏ, tái sử dụng principal builder và server lifecycle helper. Mỗi test nên tạo dữ liệu riêng, reset counter/mock và đóng channel/server để tránh phụ thuộc thứ tự chạy.

## 16. Ma trận kiểm thử tối thiểu

| Nhóm | Trường hợp bắt buộc | Assertion chính |
| --- | --- | --- |
| Allow | Principal đủ permission | Status OK; handler chạy |
| Deny | Principal thiếu permission | PERMISSION_DENIED; handler không chạy |
| Missing context | Không có principal | UNAUTHENTICATED; handler không chạy |
| Policy | Method không có mapping | Deny-by-default |
| Pipeline | Authentication trước authorization | Principal đọc được bằng shared key |
| Input giả mạo | Metadata khai method khác | Policy dùng server descriptor |
| Tenant | Resource thuộc tenant khác | Không trả dữ liệu/không mutation |
| Concurrency | Hai principal đồng thời | Không lẫn subject/tenant |
| Streaming | Message ngoài phạm vi | Không side effect; status/item result đúng |
| Lifecycle | Cancel/deadline | Cleanup được thực hiện |
| Spring wiring | Khởi động application context | Interceptor thực sự được đăng ký |
| Error mapping | Policy dependency unavailable | Fail-closed; status hạ tầng |

Đây là baseline cho security regression test. Khi thêm RPC mới, cần quyết định policy cho method đó và bổ sung test allow/deny tương ứng. Không để method mới chỉ được kiểm tra bằng happy path.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo policy cho GetOrder yêu cầu orders:read và CancelOrder yêu cầu orders:cancel.
2. Viết unit test cho allow, deny và method chưa có policy.
3. Dựng in-process gRPC server có authentication test interceptor và authorization interceptor.
4. Viết ba integration test riêng: principal đủ quyền, principal thiếu quyền và missing context.
5. Dùng AtomicInteger hoặc mock để chứng minh handler không chạy khi deny/missing context.
6. Gửi metadata x-method-name giả và xác minh policy vẫn dùng server-side MethodDescriptor.
7. Bổ sung test tenant/resource, concurrency và streaming message authorization.
8. Khởi động Spring application context trong integration test để xác minh interceptor wiring production.

### Câu hỏi tự kiểm tra

**1. Allow, deny và missing context khác nhau thế nào?**  
Allow có principal và đủ quyền; deny có principal nhưng policy từ chối; missing context không có principal đã xác minh để đánh giá quyền.

**2. Status nào phù hợp với deny và missing context?**  
Deny thường là PERMISSION_DENIED; missing principal là UNAUTHENTICATED.

**3. Vì sao assert status chưa đủ?**  
Handler có thể đã chạy và tạo side effect trước khi status được gửi. Cần assert handler không được gọi và dữ liệu không đổi.

**4. Unit test policy có thay integration test interceptor không?**  
Không. Unit test kiểm tra mapping; integration test chứng minh Context, thứ tự interceptor, dispatch và status thực tế.

**5. Vì sao cần test method chưa có policy?**  
Để chứng minh deny-by-default và ngăn RPC mới vô tình được mở.

**6. Làm sao test Context isolation?**  
Chạy hai RPC đồng thời với principal khác nhau, điều khiển overlap bằng latch/barrier và xác minh mỗi call chỉ thấy principal của nó.

**7. Có cần test authorization cho từng message streaming không?**  
Có khi message có thể tham chiếu resource/action khác nhau. Test phải chứng minh message bị deny không tạo side effect.

**8. Vì sao cần Spring application integration test nếu in-process test đã PASS?**  
Vì in-process test tự dựng chain; nó không chứng minh bean/extension point trong cấu hình Spring production đã đăng ký interceptor đúng.

## Tổng kết

Kiểm thử authorization cần phân biệt **allow**, **deny** và **missing context**. Principal đủ quyền phải đi tới handler; principal đã xác minh nhưng thiếu quyền nhận **PERMISSION_DENIED**; không có principal nhận **UNAUTHENTICATED**. Test phải xác minh status và chứng minh handler/business side effect không chạy khi bị từ chối. Kết hợp unit test policy, in-process gRPC integration test và Spring application integration test để kiểm tra cả mapping lẫn wiring thực tế. Bổ sung test method chưa có policy, metadata giả mạo, tenant/resource, request đồng thời, streaming và cancellation giúp ngăn lỗi phân quyền quay lại.


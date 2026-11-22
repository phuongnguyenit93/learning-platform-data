# Không dựa vào method name từ client

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao tên method do client tự khai trong metadata hoặc request body không phải căn cứ authorization đáng tin cậy.
- Phân biệt RPC path mà client chọn với method descriptor mà server đã dispatch tới.
- Lấy tên method từ server-side MethodDescriptor và dùng full method name để kiểm tra policy.
- Thiết kế allowlist chính xác, deny-by-default, không dựa vào prefix hoặc tên method gần giống.
- Kết hợp method authorization với principal đã xác minh, tenant và resource policy.
- Nhận biết tác động của gateway/path rewrite và cách bảo vệ backend.
- Kiểm thử giả mạo method name, gọi method không được phép và method không tồn tại.

## 1. Vì sao không tin method name do client tự khai?

Trong **SPRING_GRPC**, client gọi service bằng generated stub. Một RPC được xác định bởi service và method trong contract Protocol Buffers, chẳng hạn OrderService/GetOrder. Server cần biết method thực tế đang được thực thi để áp dụng authorization.

Một lỗi thiết kế phổ biến là để client gửi thêm metadata hoặc request field như:

~~~text
x-method-name: demo.orders.v1.OrderService/GetOrder
~~~

Sau đó server dùng giá trị này để quyết định quyền. Client có thể tự thay thành tên method được phép, dù RPC thực tế đang gọi method quản trị:

~~~text
RPC thực tế: demo.admin.v1.AdminService/DisableAccount
Metadata tự khai: demo.orders.v1.OrderService/GetOrder
~~~

Nếu authorization tin metadata, server có thể cho phép thao tác quản trị dựa trên tên method giả. Tên method do client tự khai chỉ là dữ liệu không tin cậy, giống như mọi input khác.

**Nguyên tắc:** authorization phải dựa trên method descriptor mà server đã dispatch, không dựa trên tên method trong custom metadata, protobuf request body, query parameter hay header do caller kiểm soát.

## 2. Client chọn RPC path, server xác định method được thực thi

Cần phân biệt hai khái niệm:

- Client thực sự chọn RPC bằng HTTP/2 path, thường có dạng /package.Service/Method. Đây là một phần của giao thức định tuyến; client được quyền yêu cầu một method mà nó biết.
- Server nhận path, tìm service/method đã đăng ký và dispatch tới method tương ứng. Khi interceptor của service được gọi, ServerCall cung cấp MethodDescriptor đại diện cho method server đã chọn.

Do đó, không có nghĩa server bỏ qua RPC path. Path là đầu vào để định tuyến, còn authorization sử dụng descriptor phía server sau bước dispatch.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant T as HTTP/2 transport
    participant R as Server dispatch
    participant I as Authorization interceptor
    participant S as Service handler
    C->>T: POST + :path /demo.admin.v1.AdminService/DisableAccount
    T->>R: Resolve registered service and method
    R->>I: ServerCall + MethodDescriptor
    I->>I: Read server-side full method name
    alt Policy allows
        I->>S: next.startCall
        S-->>C: Response
    else Policy denies
        I-->>C: PERMISSION_DENIED
    end
~~~

Generated stub giúp code client gọi đúng contract, nhưng nó không phải ranh giới bảo mật. Một caller có thể dùng raw gRPC client hoặc tự tạo HTTP/2 request để gọi path khác. Server vẫn phải xác thực và kiểm tra quyền cho method thực tế.

## 3. Lấy full method name từ server-side descriptor

Trong grpc-java, ServerCall cung cấp MethodDescriptor:

~~~java
String fullMethodName =
        call.getMethodDescriptor().getFullMethodName();
~~~

Full method name có dạng chính xác:

~~~text
demo.orders.v1.OrderService/GetOrder
demo.orders.v1.OrderService/CancelOrder
demo.admin.v1.AdminService/DisableAccount
~~~

Đây là giá trị phù hợp để đối chiếu policy. Không cần tự tách URL hoặc đọc một header tự đặt để xác định method.

Có thể dùng generated descriptor để tránh lặp chuỗi tên method trong policy:

~~~java
String getOrderMethod =
        OrderServiceGrpc.getGetOrderMethod().getFullMethodName();

String cancelOrderMethod =
        OrderServiceGrpc.getCancelOrderMethod().getFullMethodName();
~~~

Generated descriptor phản ánh tên method trong contract được compile ở server. Khi package/service/method đổi, policy và test cần được cập nhật cùng thay đổi contract.

## 4. Dùng exact allowlist và deny-by-default

Policy nên so khớp full method name chính xác. Tránh kiểm tra bằng prefix, suffix hoặc substring:

~~~java
// Không an toàn: các method có prefix này đều có thể được cho qua.
if (fullMethodName.startsWith("demo.orders.v1.OrderService/")) {
    return true;
}
~~~

Nếu service có method đọc và method quản trị, prefix service không thể biểu diễn sự khác nhau về quyền. Một method mới thêm vào service cũng có thể vô tình được mở.

Ví dụ policy chính xác:

~~~java
package dev.example.security;

import dev.example.orders.v1.OrderServiceGrpc;
import dev.example.admin.v1.AdminServiceGrpc;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class GrpcMethodPolicy {

    private final Map<String, String> requiredPermissions = Map.of(
            OrderServiceGrpc.getGetOrderMethod().getFullMethodName(),
            "orders:read",
            OrderServiceGrpc.getCancelOrderMethod().getFullMethodName(),
            "orders:cancel",
            AdminServiceGrpc.getDisableAccountMethod().getFullMethodName(),
            "accounts:disable");

    public boolean allows(
            GrpcPrincipal principal,
            String fullMethodName) {

        String permission = requiredPermissions.get(fullMethodName);

        // Method chưa khai báo hoặc không có permission đều bị từ chối.
        return permission != null
                && principal.hasPermission(permission);
    }
}
~~~

Map này dùng exact key. Không tìm thấy method đồng nghĩa policy không cấp quyền. Nếu một method cần nhiều permission, policy có thể ánh xạ tới Set<String> và yêu cầu principal có đủ quyền.

Với method public như health check, hãy khai báo ngoại lệ cụ thể theo đúng service/method và network boundary. Không mở toàn bộ service chỉ để health probe hoạt động.

## 5. Authorization interceptor chỉ dùng method descriptor của server

Interceptor cần principal đã được authentication xác minh. Authentication và authorization dùng chung một Context key:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

Authentication interceptor xác minh credential rồi đặt principal vào Context. Authorization interceptor lấy tên method từ ServerCall:

~~~java
package dev.example.security;

import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class MethodAuthorizationInterceptor
        implements ServerInterceptor {

    private final GrpcMethodPolicy policy;

    public MethodAuthorizationInterceptor(GrpcMethodPolicy policy) {
        this.policy = policy;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        GrpcPrincipal principal =
                GrpcSecurityContext.PRINCIPAL.get();

        if (principal == null) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        String fullMethodName =
                call.getMethodDescriptor().getFullMethodName();

        if (!policy.allows(principal, fullMethodName)) {
            call.close(
                    Status.PERMISSION_DENIED
                            .withDescription("Permission denied"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        return next.startCall(call, headers);
    }
}
~~~

Interceptor không đọc một metadata key như x-method-name. Nó dùng descriptor do server dispatch cung cấp, rồi kiểm tra permission trên principal đã xác minh.

Nếu không có principal, trả UNAUTHENTICATED. Nếu principal tồn tại nhưng không có quyền cho method thực tế, trả PERMISSION_DENIED. Nhánh deny đóng call và trả listener rỗng; không gọi next.startCall, vì service handler không được chạy khi policy từ chối.

### 5.1. Đăng ký interceptor theo đúng thứ tự

Với grpc-java, có thể bọc service definition để authentication chạy trước authorization:

~~~java
ServerServiceDefinition securedOrders =
        ServerInterceptors.interceptForward(
                orderService,
                authenticationInterceptor,
                methodAuthorizationInterceptor);

serverBuilder.addService(securedOrders);
~~~

Trong Spring gRPC starter, đăng ký interceptor qua extension point/bean registration mà phiên bản đang dùng hỗ trợ; không tự tạo server thứ hai nếu starter đã quản lý server. Hãy kiểm thử thứ tự thực thi thực tế để bảo đảm principal được đặt trước khi authorization đọc Context.

## 6. Metadata và request field vẫn là input không tin cậy

Client có thể gửi nhiều loại dữ liệu:

- Custom metadata như x-method-name, x-role hoặc x-permissions.
- Request field như operation, action, commandType hoặc method.
- Query/route parameter do gateway chuyển tiếp.
- Trace baggage hoặc correlation metadata.

Các trường này có thể hữu ích cho nghiệp vụ, logging hoặc tracing, nhưng không được thay thế method descriptor khi xác định RPC đang thực thi.

Nếu request body có field action, field đó có thể mô tả **hành động nghiệp vụ bên trong** một RPC tổng quát, ví dụ ExecuteCommand. Khi đó server cần kiểm tra action theo domain policy và resource state. Không được coi action field là tên method gRPC hoặc cho phép nó ghi đè method authorization.

Tương tự, không dùng x-role/x-permissions do client gửi làm principal. Quyền phải đến từ credential đã xác minh hoặc policy engine đáng tin cậy.

## 7. Gateway và path rewrite

Trong triển khai thực tế, gRPC có thể đi qua ingress, reverse proxy hoặc service mesh. Gateway có thể chọn cluster hoặc rewrite path theo cấu hình.

Cần bảo đảm:

- Gateway chỉ route tới backend/service đã được phép.
- Backend vẫn xác thực workload/client theo trust model, ví dụ mTLS hoặc token.
- Authorization ở backend dùng MethodDescriptor mà backend thực sự dispatch.
- Không có route rewrite khiến public path gọi nhầm method đặc quyền.
- Policy và route config được review cùng nhau khi đổi service/method.
- Không coi header do gateway thêm là danh tính nếu backend chưa xác thực gateway và kiểm soát nguồn header đó.

Nếu gateway rewrite path từ một route public sang một method nội bộ, server-side descriptor sẽ phản ánh method nội bộ được gọi. Authorization ở backend phải kiểm tra method đó theo principal thực tế. Nếu backend chỉ tin tên route public do gateway truyền qua metadata, cấu hình có thể bị giả mạo khi request đi vào từ đường khác.

## 8. Method không tồn tại và method không được phép

Hai trường hợp cần được phân biệt:

- **Method tồn tại nhưng principal không có quyền:** server dispatch tới method đã đăng ký, authorization interceptor có thể trả PERMISSION_DENIED.
- **Method không được server đăng ký:** transport/server thường không tìm thấy service/method và trả UNIMPLEMENTED; service interceptor có thể không được gọi vì không có handler tương ứng.

Vì vậy, không dựa vào authorization interceptor để xử lý mọi path không tồn tại. Cần theo dõi lỗi UNIMPLEMENTED ở lớp transport/gateway nếu muốn phát hiện client gọi method sai hoặc dò API.

Không biến method không tồn tại thành allow chỉ vì metadata khai một method hợp lệ. Không tự dispatch theo tên method trong request body.

## 9. Giữ policy nhất quán khi contract thay đổi

Full method name phụ thuộc package, service và method trong proto. Các thay đổi sau có thể làm thay đổi policy key:

- Đổi package, ví dụ demo.orders.v1 sang demo.orders.v2.
- Đổi service name hoặc chuyển method sang service khác.
- Rename method.
- Thêm method mới.
- Tách một method tổng quát thành các method có quyền riêng.

Khi thay đổi contract:

1. Sinh lại code và xác định full method name mới từ generated descriptor.
2. Cập nhật exact policy mapping.
3. Quyết định quyền cho method mới; mặc định deny nếu chưa có rule.
4. Cập nhật gateway route và service registration.
5. Chạy test allow/deny cho method cũ và mới.
6. Kiểm tra logs/metrics để phát hiện caller còn dùng tên method cũ.

Không dùng prefix matching để tránh phải cập nhật policy. Việc phải khai báo rõ method mới là một lớp kiểm soát giúp thay đổi API không vô tình mở quyền.

## 10. Audit mà không tin method name tự khai

Audit log nên ghi method thực tế từ server descriptor:

~~~java
String method =
        call.getMethodDescriptor().getFullMethodName();

audit.record(
        principal.subject(),
        method,
        decision.allowed(),
        decision.reasonCode());
~~~

Không dùng x-method-name do client gửi làm trường method chính trong audit. Nếu cần ghi giá trị caller tự khai để điều tra hành vi giả mạo, ghi riêng dưới tên như claimedMethod, đánh dấu untrusted và không dùng để quyết định policy.

Các trường audit hữu ích gồm principal ID đã chuẩn hóa, server-side full method name, decision, reason code, tenant đã xác minh, correlation ID và policy version. Không ghi token, private key hoặc toàn bộ metadata.

Metrics nên nhóm theo method/status/decision có cardinality kiểm soát. Không dùng claimed method, user ID hoặc request ID làm metric label có cardinality cao.

## 11. Kiểm thử giả mạo method name từ client

Test phải gọi qua gRPC runtime thật hoặc in-process server với interceptor production. Hai trường hợp quan trọng:

| RPC thực tế | Metadata giả | Kết quả mong đợi |
| --- | --- | --- |
| OrderService/GetOrder | AdminService/DisableAccount | Policy đánh giá GetOrder |
| AdminService/DisableAccount | OrderService/GetOrder | Policy đánh giá DisableAccount và từ chối nếu thiếu quyền |
| Method chưa đăng ký | Method hợp lệ trong metadata | Server không dispatch theo metadata; thường trả UNIMPLEMENTED |
| Method hợp lệ nhưng chưa có policy | Tên method khác trong request body | Deny-by-default cho method thực tế |

Ví dụ tạo metadata giả ở client:

~~~java
Metadata.Key<String> claimedMethodKey =
        Metadata.Key.of(
                "x-method-name",
                Metadata.ASCII_STRING_MARSHALLER);

Metadata forged = new Metadata();
forged.put(
        claimedMethodKey,
        "demo.orders.v1.OrderService/GetOrder");
~~~

Gắn metadata này bằng client interceptor hoặc CallCredentials trong test, sau đó gọi generated stub tới method quản trị. Server phải vẫn lấy full method name từ ServerCall descriptor và trả PERMISSION_DENIED nếu principal không có quyền quản trị.

Bổ sung các test:

1. Gọi method đọc với metadata tự khai là method quản trị; quyết định vẫn dựa trên method đọc.
2. Gọi method quản trị với metadata tự khai là method đọc; quyết định vẫn dựa trên method quản trị.
3. Gửi x-role/x-permissions giả; principal trong Context không thay đổi.
4. Method mới không có policy bị từ chối.
5. Handler không được gọi khi interceptor deny.
6. Gateway rewrite path được kiểm thử để backend áp policy cho method cuối cùng được dispatch.
7. Method không tồn tại được quan sát như lỗi routing/UNIMPLEMENTED, không được cấp quyền bởi metadata.

## 12. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo OrderService có GetOrder và CancelOrder; tạo AdminService có DisableAccount.
2. Tạo principal được authentication interceptor xác minh và lưu trong shared gRPC Context key.
3. Xây policy exact-match bằng generated MethodDescriptor full method name.
4. Tạo AuthorizationServerInterceptor lấy method từ call.getMethodDescriptor().getFullMethodName().
5. Gửi custom metadata x-method-name với tên method được phép nhưng gọi RPC quản trị; xác minh server vẫn deny.
6. Gọi RPC đọc với metadata tự khai tên method quản trị; xác minh policy vẫn đánh giá đúng method đọc.
7. Thêm một method mới không có mapping và xác minh deny-by-default.
8. Thử qua gateway có route/rewrite và xác minh backend authorization dùng descriptor của method thực tế.

### Câu hỏi tự kiểm tra

**1. Vì sao không dùng x-method-name từ client để authorize?**  
Vì client kiểm soát metadata và có thể khai một method được phép trong khi gọi method đặc quyền khác.

**2. Client có chọn method bằng HTTP/2 path không?**  
Có. Path là đầu vào định tuyến của giao thức; server dispatch nó tới method đã đăng ký. Authorization phải dùng descriptor server-side sau dispatch.

**3. API nào lấy full method name đáng tin cậy trong ServerInterceptor?**  
call.getMethodDescriptor().getFullMethodName().

**4. Generated stub có phải cơ chế bảo mật không?**  
Không. Caller có thể dùng raw gRPC client hoặc HTTP/2 request; server vẫn phải enforce authorization.

**5. Vì sao exact match an toàn hơn startsWith?**  
Prefix có thể vô tình cho phép method mới hoặc method quản trị trong cùng service. Exact mapping yêu cầu từng method được cấp quyền rõ ràng.

**6. Method không tồn tại có luôn đi qua AuthorizationServerInterceptor không?**  
Không nhất thiết. Nếu server không dispatch được service/method, transport thường trả UNIMPLEMENTED trước khi service interceptor chạy.

**7. Gateway rewrite path có ảnh hưởng authorization không?**  
Backend cần authorize method descriptor cuối cùng mà nó dispatch, không tin một route name do client hoặc gateway tự khai trong metadata.

**8. Audit nên ghi method nào?**  
Ghi full method name từ server-side descriptor; nếu lưu tên caller tự khai để điều tra, phải đánh dấu rõ là untrusted.

## Tổng kết

Không dùng method name trong metadata hoặc request body do client tự khai làm căn cứ authorization. Client chọn RPC path để yêu cầu một method, nhưng server dispatch path tới service/method đã đăng ký và cung cấp MethodDescriptor cho interceptor. Trong Spring gRPC, lấy full method name bằng ServerCall descriptor, so khớp exact policy và deny-by-default. Principal phải đến từ authentication đã xác minh; metadata giả không được thay đổi identity hoặc permission. Khi có gateway rewrite, backend vẫn kiểm tra method thực tế được dispatch. Test cần giả mạo tên method, gọi method đặc quyền và chứng minh policy cùng audit luôn dùng server-side descriptor.


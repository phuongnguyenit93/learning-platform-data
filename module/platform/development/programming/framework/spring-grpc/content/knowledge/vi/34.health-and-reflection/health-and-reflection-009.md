# Bảo vệ health và reflection

gRPC health và server reflection là hai service hỗ trợ vận hành, nhưng chúng công bố hai loại thông tin khác nhau. Health cho biết server hoặc một service đang ở trạng thái nào; reflection cho biết API, method và Protobuf descriptor nào đang được đăng ký. Nếu mở cả hai trên production mà không có chính sách truy cập, người gọi ngoài phạm vi có thể dò trạng thái triển khai hoặc lập bản đồ contract nội bộ.

Trong Spring gRPC, bảo vệ hai service này cần phối hợp đăng ký service, interceptor, TLS, network policy và cách probe của nền tảng. Cần giữ health probe hoạt động ổn định để orchestration điều phối instance chính xác, đồng thời giới hạn reflection cho operator. Authentication của business RPC vẫn phải được áp dụng độc lập; việc cho phép probe đọc health không cấp quyền gọi nghiệp vụ.

## 1. Phân biệt health và reflection

| Service | Dữ liệu công bố | Rủi ro nếu mở rộng |
| --- | --- | --- |
| gRPC Health | Trạng thái SERVING, NOT_SERVING và trạng thái liên quan của server/service | Lộ service tồn tại, trạng thái deploy, thời điểm lỗi hoặc khả năng sẵn sàng |
| Server Reflection | Service, method, message type và descriptor | Lộ cấu trúc API, method nội bộ, schema và capability của hệ thống |

Health không trả lời caller có quyền gọi RPC nghiệp vụ hay không. Reflection không chứng minh handler hoặc dependency đang hoạt động. Hai service có thể được đăng ký trên cùng server nhưng cần policy riêng:

- Health thường cần cho kubelet, load balancer hoặc monitoring agent.
- Reflection thường chỉ cần cho developer, QA hoặc operator.
- Business RPC cần xác thực và phân quyền theo caller, service, method và tài nguyên.

Không nên gắn một quy tắc authentication đồng nhất lên mọi RPC mà không xét cách health probe được gọi. Ngược lại, cũng không nên miễn kiểm tra cho toàn bộ service chỉ để health probe chạy được.

## 2. Health protocol: Check, Watch và trạng thái

gRPC health checking protocol chuẩn nằm trong grpc.health.v1.Health. Nó có hai RPC chính:

- Check: unary RPC, trả trạng thái hiện tại của một service.
- Watch: server-streaming RPC, gửi trạng thái và cập nhật khi trạng thái thay đổi.

Request có field service. Chuỗi rỗng thường biểu thị trạng thái tổng thể của server; tên đầy đủ như acme.orders.v1.OrderService biểu thị một service cụ thể. Ứng dụng cần cập nhật trạng thái cho đúng tên mà probe/client sử dụng.

Các giá trị trạng thái trong health response gồm:

| Trạng thái | Ý nghĩa |
| --- | --- |
| UNKNOWN | Chưa xác định được trạng thái |
| SERVING | Service có thể phục vụ request theo health policy |
| NOT_SERVING | Service không nên nhận traffic |
| SERVICE_UNKNOWN | Trạng thái dùng trong phản hồi Watch khi service được hỏi không được health manager biết |

Với RPC Check, service name không được biết thường dẫn tới status RPC NOT_FOUND; không nhầm điều này với enum SERVICE_UNKNOWN trong phản hồi Watch.

Health status là tín hiệu do ứng dụng công bố. Nó chỉ đáng tin khi được cập nhật theo trạng thái khởi động, readiness và shutdown thực tế; một giá trị SERVING được đặt cố định lúc start không phản ánh các lỗi xuất hiện sau đó.

## 3. Phân biệt startup, liveness và readiness

Ba khái niệm probe của nền tảng có mục tiêu khác nhau:

| Probe | Câu hỏi | Hành động khi thất bại |
| --- | --- | --- |
| Startup | Ứng dụng đã hoàn tất khởi tạo chưa? | Chờ lâu hơn trước khi bắt đầu các probe khác |
| Liveness | Process còn hoạt động và có khả năng tự phục hồi không? | Có thể restart container/process |
| Readiness | Instance hiện có thể nhận traffic không? | Loại instance khỏi traffic cho tới khi sẵn sàng |

Không dùng một health check phụ thuộc mọi downstream làm liveness check. Nếu database tạm ngừng, restart tất cả instance có thể làm sự cố nặng hơn. Readiness có thể phản ánh dependency thiết yếu nếu service thực sự không thể xử lý request khi dependency đó unavailable; liveness nên tập trung vào tình trạng process không thể tự phục hồi.

Một service có thể:

- Chưa SERVING trong lúc khởi tạo schema/cache hoặc nạp cấu hình.
- Chuyển NOT_SERVING khi readiness mất do dependency bắt buộc.
- Chuyển NOT_SERVING khi bắt đầu graceful shutdown để ngừng nhận traffic mới.
- Trở lại SERVING sau khi điều kiện phục vụ được khôi phục.

Health protocol không tự quyết định startup/liveness/readiness. Ứng dụng, kubelet hoặc load balancer phải định nghĩa cách ánh xạ trạng thái vào từng loại probe.

## 4. Đăng ký và cập nhật health service

grpc-java cung cấp HealthStatusManager trong artifact grpc-services. Nó quản lý trạng thái theo service name và cung cấp health service để đăng ký lên server:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;

HealthStatusManager health = new HealthStatusManager();

health.setStatus("", ServingStatus.NOT_SERVING);
health.setStatus(
    "acme.orders.v1.OrderService",
    ServingStatus.NOT_SERVING);

Server server = ServerBuilder.forPort(8443)
    .addService(new OrdersService())
    .addService(health.getHealthService())
    .build()
    .start();

// Sau khi application initialization và readiness checks hoàn tất:
health.setStatus("", ServingStatus.SERVING);
health.setStatus(
    "acme.orders.v1.OrderService",
    ServingStatus.SERVING);
```

Đây là ví dụ grpc-java minh họa lifecycle; trong Spring gRPC starter, inject và đăng ký health service qua server configuration hook được phiên bản starter hỗ trợ. Không tạo một server thứ hai chỉ để phục vụ health, vì probe có thể kiểm tra nhầm listener không đại diện cho business server.

Khi shutdown bắt đầu, cập nhật trạng thái sang NOT_SERVING trước khi ngừng nhận traffic và hoàn tất graceful shutdown. Với nhiều service trên cùng server, đặt trạng thái theo từng service thay vì chỉ dựa vào trạng thái tổng thể nếu chúng có readiness khác nhau.

## 5. Phân quyền riêng cho health và reflection

Một policy thường dùng:

| Caller | Health Check/Watch | Reflection | Business RPC |
| --- | --- | --- | --- |
| Kubelet hoặc probe agent | Chỉ các method cần thiết từ network nội bộ | Từ chối | Không cấp quyền |
| Monitoring agent | Đọc health theo service được phép | Thường từ chối | Chỉ cấp nếu có nhu cầu riêng |
| Developer/operator | Theo quyền vận hành | Cho phép có kiểm soát | Quyền theo vai trò, không tự động mở toàn bộ |
| Application client | Không nhất thiết cần health | Từ chối | Authentication/authorization theo nghiệp vụ |

Health thường có lý do để cho probe truy cập không cần bearer token ứng dụng, vì một số probe tích hợp của nền tảng không hỗ trợ metadata tùy ý. Khi đó, giới hạn đường truy cập bằng network policy, listener nội bộ và port mapping. Nếu dùng probe agent có hỗ trợ TLS/credential, vẫn xác minh identity và chỉ cấp quyền đọc health.

Reflection nên yêu cầu identity operator đã xác thực, ví dụ workload identity hoặc token ngắn hạn, cùng authorization rõ ràng. Không cho phép mọi application client tải descriptor chỉ vì chúng có thể gọi business RPC.

## 6. Bảo vệ bằng interceptor theo method

Health và reflection có full method name riêng. Một interceptor có thể áp dụng policy dựa trên method descriptor:

```java
import io.grpc.*;

final class OperationsAccessInterceptor implements ServerInterceptor {
    private static final String HEALTH_CHECK =
        "grpc.health.v1.Health/Check";
    private static final String HEALTH_WATCH =
        "grpc.health.v1.Health/Watch";
    private static final String REFLECTION_V1 =
        "grpc.reflection.v1.ServerReflection/ServerReflectionInfo";

    private final OperatorAuthenticator operators;
    private final ProbeNetworkPolicy probes;

    OperationsAccessInterceptor(
            OperatorAuthenticator operators,
            ProbeNetworkPolicy probes) {
        this.operators = operators;
        this.probes = probes;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();

        if (method.equals(HEALTH_CHECK) || method.equals(HEALTH_WATCH)) {
            if (probes.isAllowed(call)) {
                return next.startCall(call, headers);
            }
            call.close(Status.PERMISSION_DENIED, new Metadata());
            return new ServerCall.Listener<>() {};
        }

        if (method.equals(REFLECTION_V1)) {
            if (operators.isAuthenticatedOperator(headers)) {
                return next.startCall(call, headers);
            }
            call.close(Status.UNAUTHENTICATED, new Metadata());
            return new ServerCall.Listener<>() {};
        }

        return next.startCall(call, headers);
    }
}
```

Đây là skeleton minh họa policy, không phải implementation hoàn chỉnh. ProbeNetworkPolicy phải dựa trên network identity đáng tin cậy do proxy/transport cung cấp; không tin header IP do caller tự khai. OperatorAuthenticator phải xác minh token/certificate thay vì chỉ kiểm tra header có mặt.

Nếu server hỗ trợ reflection v1alpha, bổ sung method path v1alpha tương ứng vào cùng policy. Khi dùng service-specific interceptor, có thể bọc riêng HealthStatusManager.getHealthService() và ProtoReflectionService thay vì đặt mọi nhánh trong một interceptor global. Chọn cách đăng ký phù hợp với starter và kiểm thử rằng interceptor thật sự nằm trên server production.

Không dùng allowlist method name để bỏ qua toàn bộ authentication rồi vô tình cho phép method khác. Với các method không nằm trong nhóm health/reflection, tiếp tục áp dụng business authentication/authorization thông thường.

## 7. Lưu ý với Kubernetes và probe tích hợp

Kubernetes native gRPC probe gọi health checking protocol tới port của Pod và có thể truyền service name để phân biệt readiness/liveness. Cơ chế probe tích hợp không cung cấp tùy chọn metadata bearer token hoặc cấu hình TLS client identity như một gRPC client tổng quát. Vì vậy, nếu health service bị bảo vệ bằng auth/TLS bắt buộc, probe native có thể không kết nối được.

Các lựa chọn triển khai:

- Dành một listener/port health nội bộ chỉ có thể truy cập từ network của Pod/kubelet phù hợp.
- Cho phép riêng Health/Check hoặc Health/Watch từ probe path được kiểm soát, trong khi giữ các RPC khác được bảo vệ.
- Dùng exec probe hoặc probe agent khi cần TLS, credential hay logic xác minh phức tạp hơn.
- Dùng network policy để giới hạn ai có thể tiếp cận health port; không công khai port đó qua public ingress.

Kiểm tra hành vi của phiên bản Kubernetes và runtime đang triển khai, cũng như cách service mesh/sidecar xử lý HTTP/2 và probe traffic. Không giả định một probe chạy được trong local sẽ chạy được qua network policy production.

## 8. Bảo vệ reflection mà không làm lộ API

Reflection có thể trả descriptor của mọi service được đăng ký trên server. Nếu operator chỉ cần khám phá một tập service, cân nhắc:

- Tắt reflection trên public production listener.
- Chỉ đăng ký reflection trên listener quản trị nội bộ.
- Bảo vệ reflection RPC bằng operator identity và authorization.
- Dùng gateway cho phép đúng reflection method path nếu kiến trúc hỗ trợ gRPC routing an toàn.
- Dùng descriptor set đã version hóa khi không muốn server công bố reflection.

Một listener quản trị riêng phải dùng descriptor đúng release của business server. Không giả định một ProtoReflectionService đặt trên server phụ tự động nhìn thấy service definition từ một server khác. Nếu nhân đôi service registration, tránh vô tình mở các business RPC trên listener quản trị.

TLS/mTLS bảo vệ đường truyền và có thể xác thực client certificate, nhưng authorization vẫn phải quyết định certificate identity nào được đọc descriptor. Reflection disabled cũng không thay thế quyền kiểm soát trên business RPC.

## 9. Health Watch, rate limiting và thông tin log

Watch là stream có thể tồn tại lâu và nhận nhiều cập nhật. Khi bảo vệ health service, cần xem xét:

- Giới hạn số Watch stream đồng thời theo caller hoặc nguồn probe.
- Hủy stream khi client disconnect/cancel và giải phóng tài nguyên.
- Không tạo một Watch mới liên tục nếu probe chỉ cần unary Check.
- Không log mỗi lần gửi status update; tránh tạo log volume lớn.
- Ghi nhận status transition, caller identity và lỗi truy cập ở mức phù hợp.

Với reflection, giới hạn số stream/request và audit operator truy cập. Log nên chứa identity đã xác minh, endpoint, thời điểm, method, allow/deny và status; không ghi token, private key hoặc toàn bộ metadata.

Health response cũng có thể tiết lộ trạng thái dependency. Chỉ công bố mức thông tin mà probe cần. Ví dụ, probe bên ngoài thường chỉ cần SERVING/NOT_SERVING, còn chi tiết database/cache nên nằm trong telemetry nội bộ có quyền truy cập phù hợp.

## 10. Kết hợp Spring health với gRPC health

Spring Boot Actuator health và gRPC Health protocol là hai bề mặt khác nhau. Một ứng dụng có thể có HealthIndicator cho database, message broker hoặc dependency; gRPC health manager cần được cập nhật theo policy của service gRPC.

Có thể xây dựng một adapter ở application layer:

1. Thu thập kết quả từ các dependency thiết yếu bằng cơ chế Spring health.
2. Ánh xạ kết quả sang trạng thái readiness của từng gRPC service.
3. Cập nhật HealthStatusManager khi startup, dependency state thay đổi và shutdown.
4. Giữ liveness policy độc lập với dependency health để tránh restart loop.
5. Không đưa chi tiết lỗi nội bộ hoặc credential vào health response.

Không nên polling mọi dependency quá dày chỉ để cập nhật health. Dùng cache/monitoring phù hợp, timeout ngắn có kiểm soát và circuit breaker khi cần. Nếu health evaluation phụ thuộc một RPC downstream, tránh để health Check tạo thêm tải lớn lên chính dependency đang gặp sự cố.

## 11. Kiểm thử chính sách health và reflection

Kiểm thử phải xác minh caller được phép, caller bị từ chối và business authorization không bị vô tình bỏ qua:

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Probe từ network được phép gọi Health/Check | Nhận trạng thái đúng của service |
| Nguồn ngoài allowlist gọi health | Bị từ chối hoặc không thể kết nối |
| Health Watch được phép | Nhận trạng thái ban đầu và cập nhật khi status đổi |
| Watch bị cancel | Stream và tài nguyên được giải phóng |
| Operator hợp lệ gọi reflection | list/describe trả descriptor theo policy |
| Caller không có operator identity | Reflection bị từ chối |
| Reflection v1/v1alpha | Mọi path được hỗ trợ tuân cùng policy |
| Business RPC từ probe identity | Vẫn bị business authorization từ chối |
| Startup chưa hoàn tất | Readiness không báo SERVING |
| Dependency thiết yếu mất | Readiness chuyển NOT_SERVING theo policy |
| Shutdown bắt đầu | Health chuyển NOT_SERVING trước khi server dừng |
| Kubernetes native probe | Kết nối được theo giới hạn auth/TLS/network thực tế |
| Spring profile/lifecycle | Đúng service được đăng ký, cập nhật và dừng cùng context |
| Audit/rate limit | Ghi nhận truy cập và giới hạn stream bất thường |

In-process test phù hợp cho status transition, method authorization và Watch behavior. Thêm integration test qua TCP/TLS, network policy hoặc môi trường Kubernetes staging để xác minh probe thực tế. Một unit test của interceptor không chứng minh kubelet có thể tiếp cận listener production.

## 12. Bài tập vận dụng

Một ứng dụng Spring gRPC chạy trên Kubernetes có OrderService, InventoryService, health service và reflection. Kubelet cần kiểm tra readiness; monitoring agent theo dõi health; operator dùng grpcurl để khám phá descriptor khi điều tra sự cố. Security yêu cầu application client không được đọc reflection hoặc dùng health identity để gọi business RPC.

**Yêu cầu:**

1. Xác định health status cho toàn server và từng service; mô tả thời điểm chuyển SERVING/NOT_SERVING.
2. Phân biệt startup, liveness và readiness; tránh dùng dependency failure làm liveness failure nếu process có thể phục hồi.
3. Chọn cách cho Kubernetes probe truy cập Health/Check mà không mở public health endpoint.
4. Bảo vệ Health/Watch theo probe network hoặc probe identity; giới hạn Watch stream.
5. Bảo vệ reflection bằng operator authentication/authorization, TLS/mTLS và network policy.
6. Bổ sung reflection v1/v1alpha vào cùng access policy nếu server hỗ trợ.
7. Giữ business RPC authorization độc lập và kiểm tra probe identity không thể gọi OrderService.
8. Viết integration test cho status transition, reflection allow/deny, TLS và Kubernetes probe path.

**Câu hỏi tự kiểm tra:**

- Health và reflection công bố những loại thông tin nào?
- Check khác Watch như thế nào?
- SERVICE_UNKNOWN khác RPC status NOT_FOUND ra sao?
- Vì sao liveness không nên phụ thuộc mọi downstream?
- Vì sao Kubernetes native gRPC probe có thể không hoạt động khi health yêu cầu metadata/TLS client identity?
- Làm thế nào cho probe truy cập health mà không miễn authentication cho business RPC?
- Vì sao reflection cần policy operator riêng?
- Spring Actuator health khác gRPC Health service ở đâu?
- Những test nào cần chạy trên Kubernetes/network thật?

**Ghi nhớ:** Bảo vệ health và reflection bằng hai policy riêng. Health cần đủ khả năng truy cập cho probe được phép và phản ánh readiness/lifecycle chính xác; reflection nên giới hạn cho operator qua identity, TLS và network control. Trong Spring gRPC, đăng ký service trên đúng server lifecycle, áp dụng interceptor theo method/service, giữ business authorization độc lập và kiểm thử probe trên đúng network path production.

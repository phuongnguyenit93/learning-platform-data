# Mapping permission failure sang status

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt lỗi authentication, quyết định authorization từ chối và lỗi không thể đánh giá policy.
- Chọn gRPC status phù hợp cho từng tình huống quyền, resource visibility và business precondition.
- Ánh xạ exception bảo mật của application sang status tập trung trong Spring gRPC.
- Trả lỗi nhất quán từ interceptor và service implementation mà không làm lộ policy, token hoặc dữ liệu nhạy cảm.
- Dùng error details có cấu trúc khi client cần mã lỗi ổn định để xử lý.
- Phân biệt lỗi có thể retry với lỗi từ chối vĩnh viễn; không retry một thao tác ghi chỉ vì status là lỗi.
- Kiểm thử status, trailers, thông tin lỗi và việc business handler không chạy khi bị từ chối.

## 1. Vì sao cần mapping permission failure rõ ràng?

Trong **SPRING_GRPC**, authentication xác minh caller là ai; authorization quyết định principal đó được gọi service/method hoặc thao tác trên resource nào. Khi một yêu cầu thất bại, client cần biết đó là credential không hợp lệ, caller thiếu quyền, resource nằm ngoài phạm vi, hay hệ thống không thể đánh giá policy.

gRPC truyền kết quả RPC bằng **status code** và có thể kèm status description, trailers hoặc error details. Nếu mọi lỗi bảo mật đều bị chuyển thành **UNKNOWN**, client khó phân biệt cần đăng nhập lại, cần yêu cầu quyền, hay nên thử lại sau. Nếu trả status quá chi tiết, server có thể tiết lộ sự tồn tại của resource, permission nội bộ hoặc cấu trúc policy.

Một mapping tốt cần đồng thời đáp ứng:

- **Đúng semantics:** status phản ánh bản chất lỗi.
- **Ổn định:** client có thể xử lý theo mã status, không phụ thuộc chuỗi mô tả.
- **An toàn:** không tiết lộ token, claim, policy rule hoặc dữ liệu tenant.
- **Nhất quán:** cùng loại lỗi được ánh xạ giống nhau ở mọi RPC.
- **Có thể vận hành:** phân biệt deny thực sự với lỗi hạ tầng khiến policy không thể đánh giá.

## 2. Phân biệt authentication failure và permission denial

Hai status quan trọng nhất của luồng bảo mật là **UNAUTHENTICATED** và **PERMISSION_DENIED**.

| Tình huống | Status | Ý nghĩa |
| --- | --- | --- |
| Không gửi credential bắt buộc | **UNAUTHENTICATED** | Server chưa xác minh được caller |
| Token sai chữ ký, hết hạn, sai issuer hoặc audience | **UNAUTHENTICATED** | Credential không chứng minh danh tính hợp lệ |
| mTLS identity không hợp lệ hoặc không được chấp nhận | **UNAUTHENTICATED** | Authentication chưa thành công |
| Principal hợp lệ nhưng thiếu permission cho method | **PERMISSION_DENIED** | Caller đã xác thực nhưng policy từ chối |
| Principal không được phép truy cập tenant/resource | **PERMISSION_DENIED** hoặc **NOT_FOUND** theo chính sách che giấu | Quyết định authorization đã được đánh giá và bị từ chối |
| Method không có rule trong policy deny-by-default | **PERMISSION_DENIED** | Không có quyền được cấp cho method đó |

Quy tắc dễ nhớ:

- **UNAUTHENTICATED:** chưa xác minh được ai đang gọi.
- **PERMISSION_DENIED:** đã xác minh được caller nhưng caller không được phép thực hiện hành động.

Không trả **UNAUTHENTICATED** chỉ vì principal thiếu một permission. Làm vậy khiến client hiểu nhầm rằng token hết hạn và có thể liên tục refresh credential trong khi quyền thực tế chưa được cấp.

Ngược lại, không trả **PERMISSION_DENIED** cho token sai chữ ký. Server chưa thể tin principal được khai báo trong token.

## 3. Mapping các lỗi liên quan đến authorization

Không phải mọi lỗi xuất hiện gần bước kiểm tra quyền đều là permission denial. Hãy phân biệt quyết định policy với lỗi dữ liệu, trạng thái nghiệp vụ và lỗi hạ tầng.

| Nguyên nhân | Status phù hợp thường gặp | Lý do |
| --- | --- | --- |
| Thiếu/sai credential | **UNAUTHENTICATED** | Caller chưa được xác thực |
| Thiếu permission hoặc role grant | **PERMISSION_DENIED** | Policy đã đánh giá và từ chối |
| Tenant không nằm trong membership đã xác minh | **PERMISSION_DENIED** | Caller không có quyền ở tenant đó |
| Cố ý che giấu resource ngoài phạm vi | **NOT_FOUND** | Không tiết lộ resource có tồn tại hay không |
| Resource tồn tại nhưng trạng thái không cho phép action | **FAILED_PRECONDITION** | Đây là điều kiện nghiệp vụ hiện tại |
| Request chứa selector hoặc tham số sai định dạng | **INVALID_ARGUMENT** | Input không hợp lệ, chưa phải quyết định quyền |
| Policy engine không truy cập được | **UNAVAILABLE** | Hệ thống không thể đưa ra quyết định |
| Policy evaluation hết deadline | **DEADLINE_EXCEEDED** | Ngân sách thời gian của call đã hết |
| Caller hủy RPC khi đang kiểm tra policy | **CANCELLED** | Call đã bị hủy |
| Quota/rate limit bị vượt | **RESOURCE_EXHAUSTED** | Giới hạn tài nguyên hoặc lưu lượng đã bị chạm |
| Lỗi lập trình hoặc invariant nội bộ bị phá vỡ | **INTERNAL** | Lỗi server không phải quyết định deny |

Các status này có semantics khác nhau. Ví dụ, **FAILED_PRECONDITION** không nên dùng để thay cho **PERMISSION_DENIED** chỉ vì cả hai đều khiến business action không chạy. **RESOURCE_EXHAUSTED** phù hợp với quota/rate limit; nó không phải status chung cho mọi trường hợp caller thiếu quyền.

### 3.1. Resource concealment: khi nào dùng NOT_FOUND?

Một số API không muốn tiết lộ resource có tồn tại ở tenant khác hay không. Ví dụ, caller tenant A yêu cầu GetOrder với order ID thuộc tenant B. Trả **PERMISSION_DENIED** có thể xác nhận order tồn tại. Một API có thể chọn trả **NOT_FOUND** giống như khi resource không tồn tại.

Đây là quyết định thiết kế bảo mật, không phải quy tắc bắt buộc cho mọi hệ thống. Cần áp dụng nhất quán trên read, update, delete và các API tra cứu liên quan. Nếu contract cần phân biệt "resource không tồn tại" với "caller không có quyền", dùng **PERMISSION_DENIED** và chấp nhận thông tin được tiết lộ tương ứng.

Dù chọn cách nào, repository vẫn phải scope truy vấn theo tenant. Không truy vấn toàn cục rồi dựa vào status **NOT_FOUND** để che một lỗi truy cập dữ liệu.

### 3.2. Policy deny khác policy unavailable

Hai tình huống sau không được nhập làm một:

- **Deny:** policy engine đã trả kết quả rõ ràng rằng principal không đủ quyền. Trả **PERMISSION_DENIED**.
- **Indeterminate/unavailable:** policy engine timeout, mất kết nối hoặc không thể đánh giá. Không được tự coi là allow; fail-closed và trả status phản ánh lỗi hạ tầng như **UNAVAILABLE** hoặc **DEADLINE_EXCEEDED**.

Client có thể retry một lỗi hạ tầng tạm thời theo deadline và retry policy phù hợp. Client không nên retry vô hạn một quyết định **PERMISSION_DENIED**, vì việc thử lại cùng credential và cùng policy thường không làm quyền xuất hiện.

## 4. Thiết kế exception nội bộ trước khi ánh xạ status

Application nên biểu diễn lỗi theo ý nghĩa nghiệp vụ/bảo mật, sau đó chuyển sang gRPC status tại boundary. Điều này giúp domain không phụ thuộc vào chuỗi mô tả của gRPC và tránh mỗi service tự chọn status khác nhau.

Ví dụ exception phân loại:

~~~java
package dev.example.security;

public final class AuthorizationDeniedException
        extends RuntimeException {

    public AuthorizationDeniedException() {
        super("Authorization denied");
    }
}
~~~

~~~java
package dev.example.security;

public final class AuthenticationRequiredException
        extends RuntimeException {

    public AuthenticationRequiredException() {
        super("Authentication required");
    }
}
~~~

~~~java
package dev.example.security;

public final class AuthorizationDependencyException
        extends RuntimeException {

    public AuthorizationDependencyException(Throwable cause) {
        super("Authorization dependency unavailable", cause);
    }
}
~~~

Exception nội bộ có thể chứa nguyên nhân phục vụ log và tracing. Không serialize stack trace, token hoặc policy object vào response cho client.

Nếu ứng dụng đã có exception type chuẩn, hãy dùng chúng thay vì tạo một hệ thống exception thứ hai. Mục tiêu là phân loại nguyên nhân một lần và ánh xạ nhất quán.

## 5. Centralize mapping sang gRPC Status

Một mapper tập trung giúp các gRPC adapter và interceptor dùng cùng semantics:

~~~java
package dev.example.grpc;

import dev.example.security.AuthenticationRequiredException;
import dev.example.security.AuthorizationDeniedException;
import dev.example.security.AuthorizationDependencyException;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Component;

@Component
public class GrpcStatusMapper {

    public StatusRuntimeException map(Throwable error) {
        if (error instanceof AuthenticationRequiredException) {
            return Status.UNAUTHENTICATED
                    .withDescription("Authentication required")
                    .asRuntimeException();
        }

        if (error instanceof AuthorizationDeniedException) {
            return Status.PERMISSION_DENIED
                    .withDescription("Permission denied")
                    .asRuntimeException();
        }

        if (error instanceof AuthorizationDependencyException) {
            return Status.UNAVAILABLE
                    .withDescription("Authorization service unavailable")
                    .asRuntimeException();
        }

        if (error instanceof StatusRuntimeException grpcError) {
            return grpcError;
        }

        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }
}
~~~

Thứ tự kiểm tra loại exception cụ thể trước các fallback tổng quát giúp giữ đúng semantics. Trong thực tế cần bổ sung mapping cho exception domain như resource not found, failed precondition, quota exceeded và cancellation; không nên chuyển tất cả RuntimeException thành **PERMISSION_DENIED**.

Không trả **error.getMessage()** tùy tiện cho client. Message nội bộ có thể chứa SQL, tên permission, tenant ID, token fragment hoặc dữ liệu cá nhân. Dùng description công khai ngắn và ổn định; ghi exception gốc ở server log với redaction.

## 6. Ánh xạ ở gRPC boundary trong Spring

Có hai nơi phổ biến để chuyển exception thành status:

- **ServerInterceptor:** phù hợp với lỗi chung ở ranh giới RPC như thiếu principal, policy từ chối hoặc lỗi authentication.
- **gRPC adapter / exception handler:** phù hợp với exception phát sinh trong application service khi kiểm tra resource, trạng thái hoặc business rule.

Không nên đặt cùng một lỗi vào nhiều lớp mapping theo cách có thể ghi đè status hoặc log trùng. Chọn một nơi sở hữu mapping cuối cùng và bảo đảm exception từ service được chuyển thành status gRPC trước khi thoát khỏi server boundary.

Ví dụ trong adapter:

~~~java
public GetOrderResponse getOrder(
        GetOrderRequest request) {

    try {
        GrpcPrincipal principal = requirePrincipal();

        return useCase.getOrder(
                principal,
                request.getOrderId());

    } catch (RuntimeException error) {
        throw statusMapper.map(error);
    }
}
~~~

Đây là ví dụ rút gọn. Một adapter thực tế nên bắt đúng nhóm exception dự kiến; exception không mong đợi phải được ghi log ở server và ánh xạ thành **INTERNAL**, không nên che mất mọi lỗi thành một status bảo mật.

Nếu Spring gRPC starter của dự án cung cấp exception advice/handler, đăng ký mapper ở extension point của đúng phiên bản starter. Không giả định mọi starter dùng cùng annotation hoặc thứ tự handler. Dù triển khai ở đâu, hãy kiểm thử status quan sát được qua generated stub.

## 7. Trả status từ Authorization ServerInterceptor

Khi policy được kiểm tra trực tiếp trong interceptor, có thể đóng call bằng status:

~~~java
if (principal == null) {
    call.close(
            Status.UNAUTHENTICATED
                    .withDescription("Authentication required"),
            new Metadata());
    return new ServerCall.Listener<ReqT>() {};
}

if (!policy.allows(principal, fullMethodName)) {
    call.close(
            Status.PERMISSION_DENIED
                    .withDescription("Permission denied"),
            new Metadata());
    return new ServerCall.Listener<ReqT>() {};
}
~~~

Trong nhánh deny, không gọi **next.startCall(...)**; service implementation không được chạy. Nếu policy dependency không sẵn sàng, có thể đóng call bằng **UNAVAILABLE** và description chung. Không chuyển dependency error thành **PERMISSION_DENIED**, vì client và operator cần phân biệt "caller không có quyền" với "server chưa thể đánh giá quyền".

Nếu authorization interceptor gọi policy engine bất đồng bộ, phải phối hợp deadline và cancellation. Khi caller đã hủy call, không tiếp tục công việc tốn tài nguyên nếu có thể dừng an toàn; khi deadline hết, không được cho phép chỉ vì policy check chưa trả kết quả.

## 8. Error details và trailers có cấu trúc

Status code phù hợp cho hầu hết logic điều khiển. Khi client cần thêm thông tin có cấu trúc, có thể dùng protobuf error details trong **google.rpc.Status** và **Any**, nếu hệ sinh thái client/server hỗ trợ.

Một số detail type thường gặp:

| Detail type | Mục đích |
| --- | --- |
| **ErrorInfo** | Mã lỗi ổn định và metadata có kiểm soát |
| **RetryInfo** | Gợi ý thời gian chờ trước khi retry |
| **ResourceInfo** | Mô tả loại/tên resource khi được phép tiết lộ |
| **BadRequest** | Chi tiết field input không hợp lệ |
| **Help** | Liên kết tài liệu trợ giúp đã được kiểm duyệt |

Ví dụ về một mã lỗi ổn định có thể là **AUTHORIZATION_DENIED**. Client nên dựa trên status code và reason code được công bố, không parse description tự do như "Permission denied for orders:cancel".

Không đưa các giá trị sau vào error details/trailers:

- Access token, refresh token, private key hoặc credential.
- Danh sách toàn bộ role/permission của principal.
- Policy expression, rule nội bộ hoặc tên nhóm bảo mật.
- Resource ID/tenant ID nhạy cảm nếu API đang che giấu sự tồn tại.
- Stack trace, SQL hoặc thông tin topology nội bộ.

Error details cũng là dữ liệu đi qua network và có thể được ghi log ở proxy/client. Chỉ đưa thông tin mà caller được phép biết.

## 9. Retry, refresh token và client behavior

Client nên xử lý status theo semantics:

| Status | Hành vi client thường phù hợp |
| --- | --- |
| **UNAUTHENTICATED** | Có thể refresh/reacquire credential một lần theo flow được hỗ trợ; tránh vòng lặp vô hạn |
| **PERMISSION_DENIED** | Hiển thị lỗi quyền hoặc yêu cầu quy trình cấp quyền; không retry liên tục |
| **NOT_FOUND** | Xử lý như resource không có trong phạm vi được công bố |
| **FAILED_PRECONDITION** | Yêu cầu thay đổi trạng thái hoặc dữ liệu trước khi gọi lại |
| **UNAVAILABLE** | Có thể retry có giới hạn với backoff/jitter nếu operation an toàn và deadline còn |
| **DEADLINE_EXCEEDED** | Xem xét timeout; không mặc định thao tác server chưa xảy ra |
| **RESOURCE_EXHAUSTED** | Tôn trọng quota/rate limit và RetryInfo nếu được trả |
| **CANCELLED** | Dừng công việc gắn với call; không tự tạo retry ngoài ý muốn |

**UNAUTHENTICATED** không đảm bảo refresh token sẽ giải quyết được mọi lỗi; token có thể bị revoke hoặc client không có quyền xin scope mới. **PERMISSION_DENIED** thường cần thay đổi entitlement/policy, không phải gửi lại cùng request.

Với RPC có side effect, status timeout hoặc connection loss không chứng minh server chưa commit. Retry cần idempotency key và semantics method an toàn. Không tự retry CancelOrder, payment hoặc mutation chỉ vì client chưa nhận được response.

## 10. Status mapping trong các tình huống resource và tenant

Resource authorization thường cần lựa chọn giữa **PERMISSION_DENIED** và **NOT_FOUND** theo chính sách thông tin:

- Dùng **PERMISSION_DENIED** khi API công khai rằng resource tồn tại nhưng caller không có quyền.
- Dùng **NOT_FOUND** khi muốn che giấu resource ngoài tenant/phạm vi.
- Dùng **NOT_FOUND** khi resource không tồn tại trong tenant đã được xác minh.
- Dùng **FAILED_PRECONDITION** khi caller có quyền và resource đúng phạm vi nhưng trạng thái hiện tại không cho phép hành động.

Điều quan trọng là status không được dùng để thay thế tenant-scoped query. Repository vẫn cần điều kiện tenant ID ngay trong truy vấn. Không tải resource tenant khác rồi chỉ đổi status thành **NOT_FOUND**; dữ liệu có thể đã đi vào cache, memory hoặc log.

Đối với cross-tenant administrator, nếu policy cho phép truy cập, response có thể dùng status bình thường nhưng thao tác phải được audit theo principal, tenant mục tiêu và method. Không để status mapping vô tình trở thành cơ chế cấp quyền.

## 11. Audit và observability

Một quyết định bảo mật cần được quan sát mà không làm lộ bí mật. Nên ghi nhận:

- Full gRPC method name.
- Principal ID đã chuẩn hóa hoặc định danh pseudonymous theo chính sách.
- Decision: allow, deny hoặc indeterminate.
- Nhóm reason code ổn định như **missing_permission**, **wrong_tenant**, **policy_unavailable**.
- gRPC status cuối cùng và correlation/trace ID.
- Policy version nếu cần điều tra quyết định tại một thời điểm.

Phân biệt **authorization decision** với **transport outcome**. Một call có thể bị deny với **PERMISSION_DENIED**; một call khác có thể không đánh giá được policy do **UNAVAILABLE**. Gộp hai nhóm thành một counter "authorization failed" sẽ làm operator khó phát hiện lỗi policy dependency.

Không dùng user ID, token, request ID hoặc tenant ID có cardinality cao làm metric labels. Logs cần redact credential và payload nhạy cảm. Status description công khai không thay thế audit log nội bộ.

## 12. Các lỗi mapping thường gặp

| Cách làm sai | Hệ quả | Cách sửa |
| --- | --- | --- |
| Mọi lỗi bảo mật trả **UNKNOWN** | Client không phân biệt authn/authz | Mapping rõ **UNAUTHENTICATED** và **PERMISSION_DENIED** |
| Thiếu permission trả **UNAUTHENTICATED** | Client refresh token dù token hợp lệ | Dùng **PERMISSION_DENIED** |
| Policy engine timeout trả **PERMISSION_DENIED** | Che giấu lỗi hạ tầng thành deny | Fail-closed với **UNAVAILABLE** hoặc **DEADLINE_EXCEEDED** |
| Policy engine lỗi thì allow | Bypass authorization | Fail-closed, không thực hiện action |
| Dùng **FAILED_PRECONDITION** cho mọi deny | Sai semantics và client xử lý sai | Dành status này cho trạng thái nghiệp vụ không phù hợp |
| Trả error message nội bộ | Lộ policy, SQL hoặc dữ liệu nhạy cảm | Description chung, chi tiết ở log |
| Parse description ở client | Dễ vỡ khi thay câu chữ/ngôn ngữ | Dựa vào status và reason code ổn định |
| Retry mọi status lỗi | Retry deny vô ích hoặc lặp side effect | Retry theo status, idempotency và deadline |
| Trả NOT_FOUND nhưng query không scope tenant | Resource vẫn có thể lộ qua side channel | Tenant predicate tại repository/database |

## 13. Kiểm thử status mapping

Test phải đi qua gRPC runtime để xác minh status client thực sự nhận được, không chỉ kiểm tra mapper trả về enum trong unit test.

| Kịch bản | Status mong đợi | Handler/business action |
| --- | --- | --- |
| Không có credential | **UNAUTHENTICATED** | Không chạy |
| Token không hợp lệ | **UNAUTHENTICATED** | Không chạy |
| Principal thiếu permission | **PERMISSION_DENIED** | Không chạy |
| Method chưa có policy | **PERMISSION_DENIED** | Không chạy |
| Resource bị che giấu ngoài tenant | **NOT_FOUND** theo contract | Không có side effect |
| Resource ở trạng thái không thể hủy | **FAILED_PRECONDITION** | Không mutation |
| Policy service unavailable | **UNAVAILABLE** | Không chạy |
| Policy check hết deadline | **DEADLINE_EXCEEDED** | Không được fallback allow |
| Caller cancel | **CANCELLED** | Dừng công việc có thể hủy |
| Quota bị vượt | **RESOURCE_EXHAUSTED** | Không thực hiện action bị giới hạn |

Các test nên bao gồm:

1. Unit test cho exception-to-status mapper.
2. In-process integration test qua generated stub và interceptor thật.
3. Assert status code và reason code; không phụ thuộc description tự do.
4. Verify handler không được gọi khi authentication/authorization deny.
5. Verify policy dependency lỗi không làm business action chạy.
6. Verify error details không chứa token, permission catalog hoặc tenant nhạy cảm.
7. Verify client không retry vô hạn **PERMISSION_DENIED**.
8. Verify mutation có idempotency khi retry sau timeout/connection loss.

## 14. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Định nghĩa exception riêng cho authentication required, authorization denied và policy dependency unavailable.
2. Tạo **GrpcStatusMapper** ánh xạ các exception sang status gRPC.
3. Cấu hình authentication interceptor trả **UNAUTHENTICATED** khi credential không hợp lệ.
4. Cấu hình authorization interceptor trả **PERMISSION_DENIED** khi principal thiếu permission và không gọi **next.startCall**.
5. Trong use case, phân biệt resource ngoài tenant với business state không hợp lệ; ánh xạ **NOT_FOUND** hoặc **FAILED_PRECONDITION** theo contract.
6. Mô phỏng policy engine timeout và xác minh server fail-closed với status hạ tầng.
7. Bổ sung error detail reason code ổn định nhưng không tiết lộ policy/credential.
8. Viết integration test cho mọi status trong bảng và xác nhận deny không tạo side effect.

### Câu hỏi tự kiểm tra

**1. Khi nào dùng UNAUTHENTICATED?**  
Khi server không thể xác minh danh tính caller, ví dụ thiếu hoặc credential không hợp lệ.

**2. Khi nào dùng PERMISSION_DENIED?**  
Khi principal đã được xác minh nhưng policy từ chối quyền gọi method hoặc thao tác trên resource.

**3. Policy engine không truy cập được có phải là permission denial không?**  
Không. Server chưa đánh giá được policy; cần fail-closed và trả lỗi hạ tầng như **UNAVAILABLE** hoặc **DEADLINE_EXCEEDED**.

**4. Khi nào có thể trả NOT_FOUND thay cho PERMISSION_DENIED?**  
Khi API chủ động che giấu sự tồn tại của resource ngoài phạm vi, áp dụng nhất quán và vẫn tenant-scope truy vấn.

**5. Vì sao không dùng FAILED_PRECONDITION cho mọi lỗi quyền?**  
Vì status này biểu diễn trạng thái hiện tại không đáp ứng điều kiện để thực hiện operation; nó khác quyết định authorization từ chối.

**6. Client có nên retry PERMISSION_DENIED không?**  
Thông thường không. Cần thay đổi entitlement hoặc policy; gửi lại cùng credential thường không thay đổi quyết định.

**7. Có thể trả nguyên exception message cho client không?**  
Không nên. Message nội bộ có thể chứa policy, token, SQL hoặc dữ liệu nhạy cảm. Dùng description chung và audit log được bảo vệ.

**8. Làm sao kiểm tra mapping hoạt động ở runtime?**  
Gọi qua generated stub, assert status/trailers và xác nhận handler/side effect không chạy khi authorization deny.

## Tổng kết

Mapping permission failure sang gRPC status cần phân biệt **chưa xác thực** (**UNAUTHENTICATED**), **đã xác thực nhưng bị từ chối** (**PERMISSION_DENIED**) và **không thể đánh giá policy** (**UNAVAILABLE** hoặc **DEADLINE_EXCEEDED**). **NOT_FOUND** có thể được dùng để che giấu resource ngoài phạm vi; **FAILED_PRECONDITION** dành cho trạng thái nghiệp vụ không phù hợp. Trong Spring gRPC, chuẩn hóa exception và mapping ở server boundary, không lộ chi tiết policy trong description/trailers, và chỉ retry lỗi hạ tầng khi operation an toàn. Integration test phải kiểm tra status client nhận được cùng việc business handler không chạy và không có side effect khi authorization deny.


# Không đặt deadline vô hạn mặc định

Trong gRPC, nếu client không đặt deadline, lời gọi mặc định **không có giới hạn thời gian hoàn tất**. Client có thể tiếp tục chờ khi server bị treo, downstream chậm hoặc một request mắc kẹt trong hàng đợi. Những lời gọi như vậy giữ tài nguyên lâu hơn dự kiến và làm hệ thống khó phục hồi khi tải tăng.

Với **Spring gRPC**, nên đặt deadline hữu hạn cho các RPC thông thường ngay tại client boundary, theo ngân sách của từng nhóm nghiệp vụ. Một số stream dài có thể cần vòng đời riêng, nhưng phải là ngoại lệ được thiết kế rõ ràng với idle timeout, giới hạn phiên, cancellation và cơ chế reconnect. Mục tiêu là **không để một RPC vô tình chờ vô hạn chỉ vì người gọi quên cấu hình deadline**.

## 1. Vì sao không có deadline mặc định là rủi ro?

Một gRPC call không có deadline có thể tiếp tục tồn tại cho đến khi hoàn tất, bị hủy hoặc channel bị đóng. Nếu server hoặc downstream không phản hồi, client có thể giữ request, callback, future và tài nguyên liên quan trong thời gian rất dài.

~~~mermaid
flowchart TD
    A["Client gọi RPC"] --> B{"Có deadline?"}
    B -->|"Có"| C["Ngân sách thời gian hữu hạn"]
    C --> D{"Hoàn tất trước hạn?"}
    D -->|"Có"| E["Nhận response"]
    D -->|"Không"| F["DEADLINE_EXCEEDED"]
    B -->|"Không"| G["Chờ không có giới hạn thời gian"]
    G --> H["Server/downstream treo"]
    H --> I["Request và tài nguyên bị giữ"]
~~~

Rủi ro thường xuất hiện theo chuỗi:

- Client giữ một request đang chờ.
- Server giữ context, trạng thái xử lý hoặc subscription.
- Service cha tiếp tục chờ service con.
- Thread pool, connection pool hoặc queue bị chiếm dụng.
- Khi tải tăng, các request mới phải chờ lâu hơn và tạo thêm timeout ở những tầng khác.

Deadline không thay thế giới hạn concurrency, queue capacity hoặc timeout của database. Nó tạo **giới hạn thời gian tổng thể cho RPC**, giúp các cơ chế bảo vệ khác có một mốc kết thúc rõ ràng.

## 2. Đặt deadline hữu hạn cho từng lời gọi

Với gRPC Java, dùng **withDeadlineAfter** trên stub:

~~~java
GetCustomerRequest request = GetCustomerRequest.newBuilder()
    .setCustomerId("customer-42")
    .build();

GetCustomerResponse response = customerStub
    .withDeadlineAfter(700, TimeUnit.MILLISECONDS)
    .getCustomer(request);
~~~

Stub được trả về có deadline cho lời gọi tiếp theo. Stub gốc không bị thay đổi, nên có thể chọn ngân sách khác nhau cho từng thao tác:

~~~java
var readStub = customerStub.withDeadlineAfter(
    500, TimeUnit.MILLISECONDS);

var updateStub = customerStub.withDeadlineAfter(
    1500, TimeUnit.MILLISECONDS);
~~~

Các con số trên chỉ là ví dụ, không phải giá trị mặc định phù hợp cho mọi hệ thống. Deadline cần tính cả thời gian chờ tài nguyên, network, xử lý server và response. Chọn ngân sách theo SLA, latency p95/p99 dưới tải hợp lệ và phần dự phòng để tầng gọi hoàn tất.

Không nên dùng một deadline quá dài chỉ để tránh lỗi timeout. Deadline dài có thể khiến request giữ thread, connection hoặc trạng thái xử lý lâu hơn khi hệ thống đang quá tải.

## 3. Thiết lập fallback deadline ở client boundary

Nếu nhiều nhóm code tạo stub và dễ quên deadline, có thể áp dụng **default deadline interceptor**. Interceptor chỉ thêm deadline dự phòng khi lời gọi chưa có deadline tường minh và không kế thừa deadline từ context cha.

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.Context;
import io.grpc.Deadline;
import io.grpc.MethodDescriptor;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.Objects;
import java.util.function.Predicate;

public final class DefaultDeadlineInterceptor
        implements ClientInterceptor {

    private final Duration fallback;
    private final Predicate<String> requiresFiniteDeadline;

    public DefaultDeadlineInterceptor(
            Duration fallback,
            Predicate<String> requiresFiniteDeadline) {
        if (fallback == null || fallback.isZero() || fallback.isNegative()) {
            throw new IllegalArgumentException(
                "fallback deadline must be positive");
        }
        this.fallback = fallback;
        this.requiresFiniteDeadline =
            Objects.requireNonNull(requiresFiniteDeadline);
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        Deadline effective = callOptions.getDeadline();
        Deadline parent = Context.current().getDeadline();

        // Không để lời gọi con vượt deadline của RPC cha.
        if (parent != null
                && (effective == null || parent.isBefore(effective))) {
            effective = parent;
        }

        // Chỉ dùng fallback cho method thuộc policy có deadline hữu hạn.
        if (effective == null
                && requiresFiniteDeadline.test(method.getFullMethodName())) {
            effective = Deadline.after(
                fallback.toNanos(), TimeUnit.NANOSECONDS);
        }

        CallOptions effectiveOptions = effective == null
            ? callOptions
            : callOptions.withDeadline(effective);
        return next.newCall(method, effectiveOptions);
    }
}
~~~

Interceptor trên minh họa chính sách fallback chung. Có thể đăng ký trên channel khi tạo client:

~~~java
ManagedChannel channel = ManagedChannelBuilder
    .forTarget(target)
    .useTransportSecurity()
    .intercept(new DefaultDeadlineInterceptor(
        Duration.ofSeconds(2),
        methodName -> !methodName.equals(
            "acme.events.v1.EventService/WatchEvents")))
    .build();
~~~

Predicate trong ví dụ loại trừ một subscription dài hạn đã được thiết kế vòng đời riêng. Khi method không thuộc policy deadline hữu hạn và không có deadline từ caller/context cha, interceptor giữ nguyên CallOptions. Trong ứng dụng thực tế, nên quản lý danh sách method theo cấu hình rõ ràng hoặc dùng policy trả về ngân sách theo full method name.

Trong ứng dụng Spring, channel có thể được starter hoặc bean cấu hình quản lý. Hãy gắn interceptor qua cơ chế customizer/interceptor registration mà phiên bản đang dùng hỗ trợ; không giả định mọi starter có cùng property cấu hình.

Fallback chỉ là **lưới an toàn**. Các method có SLA khác nhau vẫn nên đặt deadline rõ ràng tại nơi gọi. Interceptor cũng cần chính sách riêng cho method dài hạn; không áp một timeout ngắn chung cho mọi stream.

## 4. Không ghi đè deadline của caller hoặc context cha

Một lỗi nguy hiểm là interceptor luôn gọi **withDeadlineAfter** và ghi đè deadline đã được caller đặt. Điều đó có thể kéo dài lời gọi vốn được giới hạn ngắn hơn.

Chính sách an toàn:

1. Giữ deadline tường minh trong CallOptions nếu nó đã có.
2. Nếu context cha có deadline sớm hơn, dùng deadline sớm hơn.
3. Chỉ tạo fallback khi không có deadline ở cả hai nơi.
4. Không sao chép lại timeout ban đầu cho mỗi nested call.

Ví dụ: caller còn 300 ms nhưng fallback của client là 2 giây. Lời gọi con vẫn phải kết thúc theo deadline cha, không được nhận thêm 2 giây mới. Ngược lại, nếu caller đặt deadline 5 giây và chính sách fallback chỉ là 2 giây, fallback không nên âm thầm thay đổi deadline tường minh của caller; nếu hệ thống muốn áp dụng mức trần tối đa, đó phải là một **policy cap** riêng, được công bố và kiểm thử rõ ràng.

## 5. Chọn deadline theo loại RPC

Không có một giá trị deadline đúng cho mọi method. Nên phân nhóm theo hành vi:

| Nhóm RPC | Chính sách thường phù hợp |
| --- | --- |
| Unary đọc dữ liệu | Deadline hữu hạn, dựa trên latency và SLA của truy vấn |
| Unary command có transaction | Đủ thời gian kiểm tra, commit và trả kết quả; retry phải an toàn |
| Nested downstream call | Không vượt ngân sách còn lại của request cha; có thể đặt giới hạn con ngắn hơn |
| Client streaming upload | Giới hạn theo kích thước, tốc độ và thời gian tối đa của phiên upload |
| Server streaming subscription | Dùng thời gian sống phiên hoặc chính sách reconnect phù hợp với nhu cầu nhận event |
| Health check | Deadline ngắn, ổn định để phát hiện service không phản hồi |

Với method có SLA khác nhau, dùng cấu hình theo full method name hoặc nhóm nghiệp vụ. Tránh một interceptor duy nhất áp dụng cùng timeout cho GetCustomer, CreatePayment và WatchEvents nếu đặc tính của chúng khác nhau.

## 6. Ngoại lệ: stream dài hạn phải có vòng đời rõ ràng

Một subscription có thể được thiết kế để mở lâu nhằm nhận event liên tục. Đặt deadline vài giây cho stream như vậy sẽ khiến kết nối thường xuyên bị ngắt; nhưng để stream vô hạn mà không có quản lý vòng đời cũng tạo rủi ro giữ tài nguyên.

Nếu một method thực sự cần stream dài hạn, hãy xem đó là **ngoại lệ có chủ đích**, và bổ sung:

- Idle timeout hoặc heartbeat để phát hiện kết nối không còn hữu ích.
- Giới hạn số stream trên mỗi user/tenant và toàn server.
- Giới hạn queue và backpressure khi consumer chậm.
- Cancellation handler để dừng producer và đóng subscription.
- Thời gian sống tối đa cho một phiên nếu hạ tầng cần luân phiên kết nối.
- Cursor/sequence để client reconnect và tiếp tục từ vị trí đã nhận.

Không gửi heartbeat chỉ để giữ một stream mà không kiểm soát trạng thái client. Heartbeat cần giúp phát hiện kết nối hoặc tiến trình không còn hoạt động, và phải có giới hạn tần suất.

## 7. Deadline mặc định không thay thế timeout ở các tầng khác

Một RPC có deadline 2 giây vẫn có thể để lại công việc nếu server không truyền cancellation tới tài nguyên. Mỗi tầng cần giới hạn phù hợp:

| Tầng | Cơ chế bảo vệ |
| --- | --- |
| gRPC client | Deadline hữu hạn cho mỗi RPC |
| gRPC server | Kiểm tra context cancellation và dừng công việc |
| Database | Query timeout, statement cancel và transaction timeout |
| HTTP client | Connect/read/request timeout và API cancel |
| Executor | Queue hữu hạn, giới hạn worker và hủy future |
| Streaming | Backpressure, idle timeout, giới hạn phiên và cleanup |

Deadline tổng nên bao trùm các timeout thành phần. Ví dụ, nếu client deadline là 1 giây, database query timeout không nên là 5 giây; nếu không, server có thể tiếp tục giữ connection sau khi client đã hết thời gian chờ.

## 8. Retry phải nằm trong ngân sách thời gian

Deadline hết thường tạo **DEADLINE_EXCEEDED**, nhưng status này không chứng minh server chưa thực hiện side effect. Nếu client retry một command tạo đơn hoặc thanh toán, thao tác có thể bị thực hiện hai lần.

Khi retry:

1. Giữ nguyên idempotency key cho cùng một ý định nghiệp vụ.
2. Giới hạn tổng thời gian retry trong deadline của request cha.
3. Chỉ retry status và thao tác được xác định là có thể retry.
4. Dùng backoff có giới hạn; không retry liên tục đến khi hết tài nguyên.
5. Nếu kết quả chưa rõ, truy vấn trạng thái theo operation ID trước khi tạo command mới.

Retry policy không được tạo một deadline mới dài hơn ngân sách caller. Nếu request cha còn 100 ms, không bắt đầu một lần retry cần 2 giây.

## 9. Kiểm thử chính sách deadline mặc định

Nên kiểm thử cả fallback và các ngoại lệ:

- Call không có deadline và không có context cha nhận fallback hữu hạn.
- Call có deadline tường minh giữ nguyên deadline đó.
- Context cha có deadline ngắn hơn thì call con không vượt deadline cha.
- Method stream dài được cấu hình theo policy riêng, không bị áp timeout unary ngắn.
- Deadline hết làm server nhận cancellation và dừng công việc có thể hủy.
- Retry không vượt ngân sách tổng và không tạo side effect trùng.

Có thể kiểm tra interceptor bằng một Channel giả ghi lại CallOptions nhận được, hoặc dùng gRPC in-process với server trì hoãn có kiểm soát. Với Spring, integration test nên xác nhận interceptor thực sự được gắn vào channel do cấu hình ứng dụng tạo ra.

## 10. Quan sát RPC không có deadline và timeout

Theo dõi theo full method name:

- Số outbound RPC không có deadline trước khi áp fallback.
- Deadline hiệu lực và thời gian còn lại khi call bắt đầu.
- Tỷ lệ DEADLINE_EXCEEDED, CANCELLED và latency p95/p99.
- Số task còn chạy sau khi RPC kết thúc.
- Số stream dài hạn, tuổi stream, idle timeout và số lần reconnect.
- Tỷ lệ retry và số command được deduplicate bằng idempotency key.

Nếu vẫn có outbound call không deadline, hãy xác định method đó có phải ngoại lệ dài hạn đã được phê duyệt hay là một đường code quên cấu hình. Không nên chỉ đo tỷ lệ timeout; cần đo cả công việc còn chạy sau khi client đã kết thúc RPC.

## 11. Ghi nhớ và tự kiểm tra

gRPC không tự đặt deadline hữu hạn cho client call. Vì vậy, **RPC thông thường cần deadline hữu hạn rõ ràng**, được chọn theo SLA và đặc tính method. Một fallback interceptor có thể bảo vệ call bị quên deadline, nhưng phải giữ deadline caller/context cha và có policy riêng cho stream dài hạn.

Tự kiểm tra:

1. Điều gì có thể xảy ra khi client gọi gRPC mà không đặt deadline?
2. Vì sao fallback interceptor không nên ghi đè deadline caller đã đặt?
3. Khi nào stream dài hạn có thể được miễn fallback deadline, và cần những kiểm soát nào?
4. Vì sao deadline tổng cần phối hợp với query timeout và HTTP client timeout?
5. Tại sao retry sau DEADLINE_EXCEEDED cần idempotency key và vẫn phải nằm trong ngân sách caller?

Đặt deadline hữu hạn theo chính sách giúp Spring gRPC giới hạn thời gian chờ, giải phóng tài nguyên kịp thời và tránh để một lời gọi thiếu cấu hình làm ảnh hưởng toàn bộ chuỗi service.

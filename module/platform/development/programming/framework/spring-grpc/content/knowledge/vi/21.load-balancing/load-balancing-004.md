# Pick first và failover

## 1. Pick first ưu tiên một backend đang kết nối được

Trong **SPRING_GRPC**, client dùng `ManagedChannel` và stub gRPC Java để gọi service được mô tả bằng hợp đồng Protocol Buffers. Khi name resolver trả về nhiều địa chỉ cho cùng một service, load balancing policy quyết định subchannel nào sẽ nhận RPC mới.

Policy **`pick_first`** ưu tiên một endpoint theo thứ tự resolver cung cấp. Client thử kết nối endpoint đó; nếu kết nối không thành công, policy có thể chuyển sang địa chỉ tiếp theo. Khi đã có một subchannel `READY`, các RPC mới thường tiếp tục đi qua kết nối đang được chọn. Đây là cách dùng một backend hoạt động tại một thời điểm, đồng thời giữ các địa chỉ khác làm lựa chọn thay thế khi kết nối gặp sự cố.

Ví dụ resolver trả về ba backend:

~~~text
Thứ tự resolver: [A, B, C]

A không kết nối được
    -> thử B
B kết nối thành công (READY)
    -> RPC mới được gửi đến B
    -> tiếp tục dùng B khi B còn sẵn sàng

B mất kết nối
    -> policy thử địa chỉ còn lại theo danh sách/trạng thái
    -> C có thể trở thành backend được chọn
~~~

`pick_first` không phân phối request đều giữa A, B và C. Nếu muốn tận dụng nhiều backend cùng lúc từ một client, `round_robin` thường phù hợp hơn. `pick_first` hữu ích khi hạ tầng đã có load balancer ở phía trước hoặc khi muốn một kết nối chính và các endpoint dự phòng.

## 2. Resolver cung cấp danh sách và thứ tự địa chỉ

`pick_first` chỉ có thể failover đến địa chỉ mà resolver cung cấp. Ví dụ target DNS:

~~~text
dns:///orders.internal:9090
~~~

DNS có thể phân giải tên service thành:

~~~text
orders.internal
  1. 10.40.2.11:9090  (A)
  2. 10.40.2.12:9090  (B)
  3. 10.40.2.13:9090  (C)
~~~

Policy sử dụng danh sách endpoint từ name resolver để tạo hoặc cập nhật subchannel. Thứ tự địa chỉ có thể ảnh hưởng endpoint được thử trước. Nếu hệ thống muốn ưu tiên vùng, nhóm hoặc backend cụ thể, thứ tự/thuộc tính endpoint phải được cung cấp có chủ đích bởi resolver hoặc control plane.

Không nên giả định DNS luôn trả nhiều địa chỉ riêng biệt. Với Kubernetes ClusterIP, client thường nhìn thấy một virtual IP và việc chọn pod diễn ra ở lớp mạng/service proxy. Với headless Service, DNS có thể trả các pod IP riêng; khi đó client có thể dùng `pick_first` để thử từng endpoint theo kết quả resolver.

Một resolver trả một địa chỉ duy nhất thì `pick_first` không có endpoint khác để failover. Policy không tự tìm pod, không quét subnet và không biết các instance phía sau một virtual IP.

## 3. Cấu hình pick_first trong gRPC Java

Có thể đặt `pick_first` làm policy mặc định cho channel:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders.internal:9090")
        .defaultLoadBalancingPolicy("pick_first")
        .useTransportSecurity()
        .build();
~~~

Sau đó generated stub được sử dụng như bình thường:

~~~java
OrdersGrpc.OrdersBlockingStub orders =
        OrdersGrpc.newBlockingStub(channel);

GetOrderReply reply = orders
        .withDeadlineAfter(2, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(GetOrderRequest.newBuilder()
                .setOrderId("ORD-42")
                .build());
~~~

`defaultLoadBalancingPolicy("pick_first")` là policy mặc định khi resolver không cung cấp service config chỉ định policy khác. Nếu resolver cung cấp service config với load balancing policy, cấu hình đó có thể quyết định policy thực tế. Provider của policy cần có trong runtime.

`useTransportSecurity()` bật TLS. Mỗi backend mà resolver có thể chọn phải trình bày chứng chỉ phù hợp với authority/hostname mà client xác minh. Không tắt xác minh chứng chỉ để xử lý lỗi kết nối đến một endpoint dự phòng.

## 4. Failover xảy ra khi trạng thái kết nối thay đổi

Subchannel có trạng thái kết nối như `IDLE`, `CONNECTING`, `READY` và `TRANSIENT_FAILURE`. `pick_first` sử dụng trạng thái đó để biết endpoint nào có thể nhận RPC:

| Tình huống | Hành vi mong đợi |
|---|---|
| Địa chỉ đầu tiên kết nối thành công | Chọn subchannel đó cho RPC mới |
| Địa chỉ đầu tiên không kết nối được | Thử địa chỉ tiếp theo theo danh sách/trạng thái policy |
| Backend đang chọn mất kết nối | Subchannel rời trạng thái `READY`; policy có thể thử endpoint khác |
| Một backend dự phòng trở thành `READY` | RPC mới có thể được gửi qua backend đó |
| Tất cả endpoint đều không kết nối được | Channel không có subchannel sẵn sàng; RPC có thể lỗi hoặc chờ theo wait-for-ready/deadline |
| Resolver cập nhật danh sách | Policy nhận kết quả mới và điều chỉnh các subchannel |

Failover phụ thuộc vào **phát hiện trạng thái kết nối**, không phải phép đo đầy đủ sức khỏe nghiệp vụ. Một tiến trình có thể chấp nhận TCP/TLS và trả gRPC status lỗi vì database hỏng hoặc dependency không hoạt động. Kết nối `READY` không chứng minh mọi chức năng của service đều khỏe.

Để tránh chọn instance mới khởi động nhưng chưa thể phục vụ, cần kết hợp readiness/health checking ở nền tảng hoặc cơ chế service discovery chỉ công bố endpoint đủ điều kiện.

## 5. Failover không tự chuyển một RPC đang chạy

Đây là giới hạn quan trọng. `pick_first` chọn subchannel khi RPC bắt đầu. Nếu backend được chọn mất kết nối giữa một lời gọi, gRPC không thể chuyển phần còn lại của RPC sang backend khác như thể không có gián đoạn.

~~~text
RPC GetOrder #1
  Client -> backend A
  A xử lý request
  A mất kết nối
  RPC #1 có thể kết thúc bằng UNAVAILABLE

RPC GetOrder #2 (lời gọi mới)
  Client -> backend B sau failover
~~~

Với unary RPC, client có thể thử lại nếu request an toàn và retry policy cho phép. Nhưng nếu backend A đã thực hiện side effect trước khi mất kết nối, client không thể suy ra từ lỗi transport rằng side effect chưa xảy ra. Cần idempotency key hoặc API kiểm tra trạng thái trước khi gửi lại.

Với server streaming, các response đã nhận không được tự động phát lại khi policy chuyển backend. Nếu stream bị ngắt, client cần tạo RPC mới và gửi cursor/sequence đã commit để backend mới đọc lại phần còn thiếu từ nguồn dữ liệu dùng chung.

Do đó cần phân biệt:

- **Connection failover:** channel chuyển lựa chọn sang subchannel khác cho các RPC mới.
- **RPC retry:** runtime/client tạo một lần gọi khác theo điều kiện retry.
- **Stream resume:** ứng dụng tạo RPC mới với cursor/checkpoint để tiếp tục dữ liệu.

Ba cơ chế này liên quan nhưng không thay thế lẫn nhau.

## 6. Phân biệt lỗi kết nối và lỗi nghiệp vụ

`pick_first` phản ứng chủ yếu với trạng thái subchannel. Nó không tự gửi lại request sang backend khác chỉ vì server trả một status nghiệp vụ:

| Kết quả từ backend | Có phải tín hiệu kết nối failover? | Cách xử lý |
|---|---|---|
| Không mở được kết nối hoặc transport lỗi | Có thể làm subchannel mất `READY` | Policy có thể thử endpoint khác |
| Server trả `INVALID_ARGUMENT` | Không | Sửa request; không gửi sang backend khác |
| Server trả `PERMISSION_DENIED` | Không | Xử lý quyền/identity |
| Server trả `NOT_FOUND` | Không | Xử lý theo nghiệp vụ |
| Server trả `INTERNAL` | Không tự động có nghĩa backend mất kết nối | Quan sát lỗi ứng dụng; retry chỉ khi an toàn và được cấu hình |
| Server trả `UNAVAILABLE` ở tầng RPC | Có thể được retry theo retry policy nếu đủ điều kiện | Phân biệt status ứng dụng với trạng thái transport; dùng policy retry có kiểm soát |

Không nên coi mọi `UNAVAILABLE` là bằng chứng backend đã chết. Một server đang `READY` vẫn có thể trả `UNAVAILABLE` cho một dependency tạm thời. Ngược lại, lỗi TCP/TLS có thể xảy ra trước khi server xử lý request. Log, tracing và trạng thái subchannel giúp xác định lớp lỗi.

## 7. wait-for-ready và deadline khi đang failover

Khi không có subchannel `READY`, client có thể thất bại ngay hoặc chờ nếu RPC dùng `withWaitForReady()`. Thời gian chờ vẫn bị giới hạn bởi deadline:

~~~java
GetOrderReply reply = orders
        .withWaitForReady()
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(request);
~~~

`waitForReady` cho channel cơ hội chờ endpoint phục hồi hoặc endpoint dự phòng kết nối thành công. Nó không tạo backend mới, không bảo đảm failover thành công và không làm RPC chờ vô hạn.

Đặt deadline theo ngân sách của nghiệp vụ. Nếu thời gian thử kết nối endpoint A, B và C đã tiêu thụ gần hết deadline, request có thể kết thúc `DEADLINE_EXCEEDED` trước khi backend dự phòng sẵn sàng. Đừng đặt deadline quá ngắn đến mức mọi lần failover đều hết ngân sách, cũng đừng bỏ deadline khiến request treo không giới hạn.

## 8. Failover phụ thuộc thứ tự và cập nhật resolver

Với `pick_first`, thứ tự endpoint có thể tạo ra ưu tiên vận hành. Nếu resolver luôn trả backend ở vùng xa trước, client có thể thường xuyên chọn vùng xa dù có backend gần hơn. Vì vậy:

- Định nghĩa thứ tự endpoint có chủ đích nếu muốn ưu tiên cụ thể.
- Đừng coi thứ tự DNS là cơ chế priority có bảo đảm nếu provider không cam kết.
- Quan sát kết quả resolver và backend thực tế đang nhận RPC.
- Khi endpoint bị loại, cần chờ resolver update được áp dụng; một RPC đang chạy có thể vẫn chịu ảnh hưởng riêng.
- Khi resolver trả danh sách mới, hành vi chọn lại phụ thuộc policy implementation và trạng thái subchannel; không giả định failback ngay lập tức về địa chỉ đầu tiên.

Nếu yêu cầu là primary/standby với quy tắc ưu tiên, phục hồi về primary hoặc failover theo vùng, cần xác minh `pick_first` và thứ tự resolver có đáp ứng chính sách đó trong runtime đang dùng hay cần policy/control plane chuyên biệt.

## 9. Tích hợp channel dùng chung trong Spring

Trong ứng dụng Spring, channel nên được tạo một lần theo target và tái sử dụng. Ví dụ:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersGrpcConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
                .forTarget("dns:///orders.internal:9090")
                .defaultLoadBalancingPolicy("pick_first")
                .useTransportSecurity()
                .build();
    }
}
~~~

Stub có thể được inject vào client service:

~~~java
import com.example.orders.rpc.OrdersGrpc;
import io.grpc.ManagedChannel;
import org.springframework.stereotype.Component;

@Component
public class OrdersClient {
    private final OrdersGrpc.OrdersBlockingStub stub;

    public OrdersClient(ManagedChannel ordersChannel) {
        this.stub = OrdersGrpc.newBlockingStub(ordersChannel);
    }
}
~~~

Không tạo channel mới cho mỗi request hoặc mỗi lần backend lỗi. Channel dài hạn quản lý resolver, subchannel và kết nối; việc tạo channel liên tục làm tăng DNS lookup, TCP/TLS handshake và tài nguyên.

Nếu ứng dụng có nhiều target, khai báo channel bean riêng với qualifier rõ ràng. Cấu hình property cụ thể phụ thuộc starter Spring gRPC đang dùng; ví dụ trên thể hiện API gRPC Java trực tiếp.

## 10. Kiểm thử failover

Một test chỉ có một server không thể chứng minh `pick_first` chuyển sang endpoint dự phòng. Cần nhiều endpoint có thể nhận diện, resolver trả danh sách theo thứ tự đã biết và khả năng dừng backend được chọn:

| Kịch bản | Điều cần xác minh |
|---|---|
| A sẵn sàng, B sẵn sàng | RPC mới đi qua A khi A là endpoint được chọn đầu tiên |
| A không mở được kết nối, B sẵn sàng | Channel có thể kết nối B và RPC mới thành công |
| A đang phục vụ rồi bị dừng | RPC đang chạy có thể lỗi; RPC mới có thể dùng B sau khi failover |
| A phục hồi sau khi B được chọn | Hành vi chọn lại tuân theo implementation/resolution; không giả định failback tức thì |
| A, B đều không sẵn sàng | RPC lỗi hoặc chờ theo wait-for-ready/deadline |
| Resolver loại A khỏi danh sách | RPC mới không tiếp tục chọn A sau khi cập nhật được áp dụng |
| Server trả `INVALID_ARGUMENT` | Không coi đây là lỗi kết nối để failover |
| TLS của B không hợp lệ | B không thể trở thành kết nối phục vụ thành công; lỗi chứng chỉ cần được sửa |
| Server stream bị ngắt ở A | Client mở RPC mới đến backend được chọn và resume bằng cursor nếu cần |

Trong test có thể dùng custom `NameResolverProvider` để trả A và B, hai server in-process hoặc TCP test server để mô phỏng backend. Để kiểm tra lỗi kết nối/TLS thực, cần transport TCP phù hợp; in-process test không mô phỏng đầy đủ handshake, DNS và network failure.

## 11. Quan sát hoạt động và giới hạn của failover

Để xác định failover có hoạt động, cần quan sát cả resolver, subchannel và RPC:

- Danh sách endpoint và thứ tự resolver trả về.
- Số subchannel ở trạng thái `READY`, `CONNECTING`, `TRANSIENT_FAILURE`.
- Backend thực tế nhận RPC mới.
- Thời gian từ lúc endpoint lỗi đến khi endpoint thay thế `READY`.
- Tỷ lệ `UNAVAILABLE`, `DEADLINE_EXCEEDED` và lỗi TLS.
- Số RPC đang chạy bị lỗi trong lúc backend dừng.
- Số lần retry/reconnect và kết quả resume của stream.

Một endpoint có thể vẫn nhận kết nối nhưng xử lý rất chậm. `pick_first` không tự đo latency hoặc tải CPU để chuyển sang endpoint nhanh hơn. Nếu cần lựa chọn theo tải, ưu tiên vùng hoặc trọng số, hãy dùng policy/control plane phù hợp và đo hiệu quả trong môi trường thực.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `pick_first` chia tải qua mọi backend | Nó ưu tiên một subchannel hoạt động tại một thời điểm |
| Failover làm RPC đang chạy tiếp tục ở backend khác | RPC đang chạy có thể thất bại; RPC mới mới dùng endpoint thay thế |
| Mọi lỗi server đều kích hoạt failover | Policy chủ yếu phản ứng với trạng thái kết nối; status nghiệp vụ không đồng nghĩa connection failure |
| Có nhiều IP là chắc chắn failover được | Resolver phải cung cấp endpoint riêng và endpoint dự phòng phải kết nối được |
| Backend `READY` nghĩa ứng dụng hoàn toàn khỏe | `READY` chủ yếu phản ánh kết nối, cần health/readiness ở tầng ứng dụng |
| `waitForReady` bảo đảm thành công | Deadline vẫn giới hạn thời gian chờ |
| `pick_first` luôn quay về endpoint đầu tiên khi nó phục hồi | Failback phụ thuộc policy, resolver update và trạng thái subchannel |

**Ghi nhớ:** `pick_first` ưu tiên một subchannel kết nối được và có thể thử endpoint khác khi kết nối được chọn không sẵn sàng. Failover giúp các **RPC mới** có cơ hội dùng backend thay thế; nó không chuyển một RPC đang chạy sang backend khác. Hãy bảo đảm resolver cung cấp địa chỉ dự phòng, cấu hình TLS/readiness/deadline đúng, phân biệt lỗi kết nối với lỗi nghiệp vụ và thiết kế retry/resume riêng cho unary có side effect hoặc server stream.

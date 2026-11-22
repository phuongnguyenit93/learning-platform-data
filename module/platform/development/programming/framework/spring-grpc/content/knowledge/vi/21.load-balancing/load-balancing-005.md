# Kết nối đến nhiều server instance

## 1. Một service có thể chạy trên nhiều instance

Trong **SPRING_GRPC**, client gọi server bằng gRPC Java, các stub được sinh từ hợp đồng Protocol Buffers và thường được quản lý trong ứng dụng Spring. Khi cần tăng khả năng phục vụ hoặc độ sẵn sàng, cùng một service có thể chạy trên nhiều server instance. Mỗi instance triển khai cùng API, nhưng có địa chỉ và vòng đời tiến trình riêng.

Ví dụ service quản lý đơn hàng có ba instance:

~~~text
orders service
  ├── instance A: 10.50.0.11:9090
  ├── instance B: 10.50.0.12:9090
  └── instance C: 10.50.0.13:9090
~~~

Client cần một target đại diện cho service, một cơ chế tìm endpoint và policy chọn backend. Mỗi RPC mới được gRPC channel điều phối đến một subchannel phù hợp. Nhờ vậy, ứng dụng không phải tự chọn IP trong từng method nghiệp vụ.

Ba khái niệm cần phân biệt:

- **Server instance:** một tiến trình/replica đang cung cấp service gRPC.
- **Endpoint:** địa chỉ mà client có thể kết nối, thường là host và port.
- **ManagedChannel:** đối tượng client dài hạn quản lý name resolution, load balancing, subchannel và transport cho các RPC.

Một channel không đồng nghĩa với một server instance. Một channel có thể biết nhiều endpoint và quản lý nhiều subchannel. Ngược lại, tạo ba channel cho ba địa chỉ cố định không tự tạo ra khả năng discovery, cập nhật instance hoặc phân phối tải bền vững.

## 2. Các instance phải tương thích cùng một hợp đồng

Trước khi kết nối nhiều instance, các backend phải cung cấp cùng service/method và tương thích với schema protobuf mà client sử dụng. Ví dụ:

~~~proto
syntax = "proto3";

package orders.v1;

option java_multiple_files = true;
option java_package = "com.example.orders.rpc";

service OrdersService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderReply);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderReply {
  string order_id = 1;
  string status = 2;
}
~~~

Instance A, B và C cần đăng ký service `orders.v1.OrdersService` và xử lý method `GetOrder` theo cùng hợp đồng. Các phiên bản có thể triển khai rolling upgrade, nhưng schema phải giữ tương thích theo quy tắc Protocol Buffers: không tái sử dụng field number đã xóa, không đổi kiểu field một cách phá vỡ và cần thiết kế rõ khi thêm/xóa field.

Việc nhiều instance dùng cùng port trong ví dụ không có nghĩa chúng chạy trên cùng một máy. Mỗi instance có thể ở host, container hoặc pod khác nhau; port là port mà endpoint công bố cho client.

Nếu một instance chạy phiên bản API không tương thích, load balancer có thể chọn nó như một backend bình thường và client sẽ nhận lỗi khó đoán. Vì vậy, rollout cần bảo đảm mọi instance được công bố vào discovery đều tương thích với client đang hoạt động.

## 3. Một channel kết nối đến service target, không hard-code từng replica

Trong phần lớn ứng dụng, client nên kết nối đến một **service target**:

~~~text
dns:///orders.internal:9090
~~~

Resolver phân giải target thành các endpoint. Load balancing policy tạo/cập nhật subchannel và chọn backend cho mỗi RPC mới. Nếu dùng DNS trả nhiều địa chỉ và policy `round_robin`, một channel có thể phân phối RPC qua các instance đang sẵn sàng.

~~~mermaid
flowchart TD
    A["OrdersClient / generated stub"] --> B["Một ManagedChannel"]
    B --> C["Name resolver"]
    C --> D["Danh sách endpoint A, B, C"]
    D --> E["Load balancing policy"]
    E --> F["Subchannel A"]
    E --> G["Subchannel B"]
    E --> H["Subchannel C"]
    F --> I["Server instance A"]
    G --> J["Server instance B"]
    H --> K["Server instance C"]
~~~

Mô hình này cho phép resolver thêm hoặc gỡ endpoint mà client vẫn giữ channel. Khi danh sách thay đổi, channel nhận kết quả resolution mới và policy điều chỉnh các subchannel.

Không nên tạo một channel mới cho mỗi request hoặc tự luân phiên IP bằng biến đếm trong service method. Cách đó bỏ qua readiness, lỗi kết nối, cập nhật endpoint, TLS và lifecycle của transport.

## 4. DNS có thể cung cấp nhiều địa chỉ

Nếu DNS của service trả nhiều record A/AAAA, DNS resolver của gRPC có thể cung cấp nhiều endpoint cho channel. Ví dụ:

~~~text
orders.internal. A 10.50.0.11
orders.internal. A 10.50.0.12
orders.internal. A 10.50.0.13
~~~

Client dùng target:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders.internal:9090")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();
~~~

Resolver trả địa chỉ; policy chọn cách dùng chúng. `round_robin` có thể phân phối RPC mới qua các subchannel `READY`. Nếu chỉ có một endpoint hoặc chỉ một subchannel sẵn sàng, client không thể phân phối qua các instance khác.

DNS không phải lúc nào cũng cung cấp từng replica riêng. Trong Kubernetes, DNS của Service kiểu ClusterIP thường trả một virtual IP; việc phân phối tiếp đến pod do network/service proxy xử lý. Headless Service có thể trả các pod IP riêng để client-side load balancing nhìn thấy từng instance.

Hãy kiểm tra DNS từ đúng network/namespace nơi client chạy. TTL và cache có thể khiến client tiếp tục nhìn thấy địa chỉ cũ trong một khoảng thời gian sau khi deployment thay đổi.

## 5. Kết nối trực tiếp nhiều endpoint bằng resolver tùy biến

Một hệ thống có service registry hoặc control plane riêng có thể dùng custom `NameResolver` để chuyển danh sách instance thành `ResolutionResult`. Ví dụ phần tạo kết quả:

~~~java
import io.grpc.Attributes;
import io.grpc.EquivalentAddressGroup;
import io.grpc.NameResolver;

import java.net.InetSocketAddress;
import java.util.List;

List<EquivalentAddressGroup> addresses = List.of(
        new EquivalentAddressGroup(
                new InetSocketAddress("10.50.0.11", 9090)),
        new EquivalentAddressGroup(
                new InetSocketAddress("10.50.0.12", 9090)),
        new EquivalentAddressGroup(
                new InetSocketAddress("10.50.0.13", 9090))
);

NameResolver.ResolutionResult result =
        NameResolver.ResolutionResult.newBuilder()
                .setAddresses(addresses)
                .setAttributes(Attributes.EMPTY)
                .build();

// Custom NameResolver gửi kết quả cho listener:
listener.onResult(result);
~~~

Đây là đoạn minh họa tạo kết quả trong custom resolver; `listener` được cung cấp qua lifecycle của `NameResolver`. Ứng dụng dùng DNS resolver có sẵn không cần tự tạo `ResolutionResult`.

Resolver tùy biến cần:

- Lấy endpoint từ nguồn discovery có thẩm quyền.
- Chỉ công bố instance phù hợp với điều kiện readiness/health đã chọn.
- Gửi cập nhật khi instance thêm, xóa hoặc đổi địa chỉ.
- Báo lỗi resolution có ý nghĩa nếu registry không truy cập được.
- Đóng watcher, subscription hoặc client registry khi resolver shutdown.

Không nên tạo resolver đọc registry liên tục theo từng RPC. Resolver là thành phần sống cùng channel và cập nhật danh sách endpoint theo cơ chế của provider.

## 6. Chọn policy khi có nhiều instance

| Policy | Cách sử dụng nhiều instance | Trường hợp phù hợp |
|---|---|---|
| `pick_first` | Ưu tiên một subchannel kết nối được; thử endpoint khác khi cần | Hạ tầng đã cân bằng tải hoặc muốn một kết nối chính và địa chỉ dự phòng |
| `round_robin` | Phân phối RPC mới qua các subchannel `READY` | Client trực tiếp nhìn thấy nhiều replica và muốn tận dụng chúng |
| Policy theo control plane | Có thể áp dụng weighted, priority, locality hoặc routing nâng cao nếu provider hỗ trợ | Cần canary, ưu tiên vùng hoặc chính sách theo thuộc tính endpoint |

Không policy nào tự đo toàn bộ tải CPU hoặc chi phí nghiệp vụ để bảo đảm phân phối đều. Round robin phân phối theo lượt giữa subchannel sẵn sàng; một backend có thể vẫn bận hơn nếu nhận request nặng hoặc stream dài.

Nếu resolver cung cấp service config có policy, cấu hình trong service config có thể quyết định policy thực tế thay cho giá trị mặc định trong channel. Hãy kiểm tra policy/provider được nạp và cấu hình mà resolver gửi đến client.

## 7. Tích hợp ManagedChannel dùng chung trong Spring

Channel là tài nguyên dài hạn, thread-safe và có thể phục vụ nhiều stub/RPC. Trong Spring, khai báo một bean cho target của service:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
                .forTarget("dns:///orders.internal:9090")
                .defaultLoadBalancingPolicy("round_robin")
                .useTransportSecurity()
                .build();
    }
}
~~~

Client service dùng channel đã được inject:

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

Nếu ứng dụng gọi nhiều service, tạo channel bean riêng cho mỗi target và dùng qualifier để tránh inject nhầm. Cấu hình endpoint, TLS credential, resolver và policy qua properties phụ thuộc starter Spring gRPC cụ thể; đoạn code trên minh họa API gRPC Java trực tiếp.

Khi ứng dụng shutdown, Spring gọi `shutdown()` để channel ngừng nhận RPC mới và đóng tài nguyên theo lifecycle. Với service cần dừng có kiểm soát, có thể chờ `awaitTermination(...)` trong thời gian giới hạn rồi dùng `shutdownNow()` nếu cần.

## 8. Một RPC được gửi đến một instance

Load balancer chọn backend khi RPC bắt đầu. Một unary RPC đi đến một instance; một server streaming RPC cũng gắn với instance đã nhận lời gọi đó trong suốt RPC:

~~~text
GetOrder RPC #1  -> instance A -> response
GetOrder RPC #2  -> instance B -> response
WatchProgress    -> instance C -> event 1, 2, 3, ...
~~~

gRPC không chia từng message của cùng một server stream qua nhiều instance. HTTP/2 cho phép multiplex nhiều RPC trên kết nối, nhưng mỗi RPC vẫn có một backend xử lý.

Nếu instance C dừng giữa stream, RPC có thể thất bại. Channel có thể chọn instance khác cho RPC mới, nhưng không tự chuyển phần stream còn lại sang instance D. Client cần reconnect và gửi cursor/checkpoint nếu muốn tiếp tục mà không mất event.

Tương tự, nếu một unary RPC đã tạo side effect ở A trước khi kết nối đứt, gọi lại đến B có thể lặp side effect. Dùng idempotency key hoặc API truy vấn trạng thái để xử lý trường hợp kết quả không xác định.

## 9. Trạng thái phải dùng chung giữa các instance

Khi client có thể gửi hai RPC liên tiếp đến hai replica khác nhau, ứng dụng không nên dựa vào state chỉ nằm trong RAM của một instance nếu nghiệp vụ yêu cầu tính liên tục.

Ví dụ:

~~~text
RPC 1 -> instance A: tạo job J-42
RPC 2 -> instance B: đọc tiến độ job J-42
~~~

Nếu trạng thái job chỉ được giữ trong memory của A, B không thể trả tiến độ chính xác. Những dữ liệu cần chia sẻ có thể gồm:

- Job/session state và trạng thái xử lý.
- Event log, sequence và checkpoint để stream có thể resume.
- Idempotency key và kết quả đã xử lý.
- Cấu hình nghiệp vụ hoặc dữ liệu cần nhất quán giữa replica.

Thường dùng database, cache phân tán hoặc event broker phù hợp. Cache cục bộ vẫn hữu ích cho dữ liệu có thể tái tạo, nhưng không nên là nguồn duy nhất cho state cần truy cập từ mọi instance.

Sticky session có thể giảm việc chuyển backend, nhưng không thay thế lưu trữ bền vững: instance vẫn có thể restart hoặc bị loại khỏi service. Chỉ dùng affinity khi có yêu cầu rõ và có cơ chế dự phòng.

## 10. Readiness, health checking và giới hạn tải

Một endpoint có trong DNS/registry không có nghĩa instance đã sẵn sàng. Quá trình từ khi instance được phát hiện đến khi nhận RPC có thể gồm:

1. Resolver nhận địa chỉ.
2. Channel tạo subchannel.
3. TCP kết nối và TLS handshake hoàn tất.
4. Health/readiness check xác nhận instance phục vụ được.
5. Policy đưa subchannel `READY` vào picker.

Nếu không có subchannel sẵn sàng, RPC có thể thất bại hoặc chờ khi dùng `withWaitForReady()`. Deadline vẫn giới hạn tổng thời gian chờ:

~~~java
GetOrderReply reply = stub
        .withWaitForReady()
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(request);
~~~

`waitForReady` không tạo thêm instance và không làm request chờ vô hạn. Nó chỉ cho channel cơ hội chờ một kết nối phù hợp trong ngân sách deadline.

Nhiều instance cũng không có nghĩa tải được phân phối không giới hạn. Cần theo dõi số RPC đồng thời, thời gian xử lý, số stream dài, connection pool/HTTP2 concurrency và giới hạn tài nguyên của từng replica. Khi hệ thống quá tải, cần admission control, quota hoặc trả status phù hợp thay vì để queue tăng vô hạn.

## 11. Graceful shutdown và cập nhật danh sách instance

Khi triển khai phiên bản mới, nền tảng thường thêm instance mới rồi mới gỡ instance cũ. Để tránh RPC mới đi vào instance sắp dừng:

- Chỉ công bố instance sau khi service đã bind port và sẵn sàng.
- Khi shutdown, đánh dấu instance không còn nhận traffic mới trước khi dừng tiến trình.
- Cho RPC đang chạy một khoảng thời gian kết thúc theo grace period.
- Hủy hoặc kết thúc stream dài theo chính sách đã công bố; client reconnect bằng cursor nếu cần.
- Đóng channel/transport và subscription tới registry đúng lifecycle.

Resolver có thể cần thời gian nhận cập nhật DNS/registry; cache và TTL khiến việc gỡ endpoint không tức thời ở mọi client. Vì vậy, graceful shutdown phía server vẫn cần từ chối RPC mới một cách có kiểm soát và cho các RPC hiện tại thời gian hoàn tất.

Không giả định việc xóa pod khỏi registry lập tức đóng mọi kết nối đã tồn tại. Subchannel đang có transport có thể tiếp tục được sử dụng cho tới khi channel nhận cập nhật hoặc transport thay đổi trạng thái.

## 12. Kiểm thử kết nối nhiều instance

Một test chỉ có một server không chứng minh được channel đang kết nối đến nhiều instance. Bộ kiểm thử cần ít nhất hai backend có thể phân biệt bằng instance ID và resolver trả các endpoint tương ứng.

| Tình huống | Điều cần xác minh |
|---|---|
| Resolver trả A, B, C | Channel nhận đủ endpoint |
| `round_robin`, tất cả backend `READY` | Các RPC unary mới được phân phối qua nhiều instance |
| `pick_first` với nhiều endpoint | Một backend được ưu tiên; địa chỉ khác có thể được thử khi cần |
| Một instance không kết nối được | RPC mới có thể dùng instance sẵn sàng khác theo policy |
| Resolver thêm/xóa instance | Channel cập nhật subchannel theo danh sách mới |
| Instance bị gỡ trong lúc RPC đang chạy | Xác minh RPC hiện tại và RPC mới có kết cục đúng |
| Server stream bị ngắt | Client reconnect và resume theo cursor nếu hợp đồng hỗ trợ |
| Hai instance dùng schema khác nhau | Phát hiện lỗi tương thích khi rollout |
| TLS trên tất cả endpoint | Mọi instance xác thực được bằng authority/trust phù hợp |
| Spring context shutdown | Channel và các tài nguyên được đóng theo lifecycle |

Với custom resolver, dùng test provider phát nhiều `EquivalentAddressGroup`. Với DNS, Kubernetes và TLS, cần integration test trong môi trường mạng tương ứng; in-process test không mô phỏng đầy đủ DNS cache, TCP, certificate hoặc proxy.

## 13. Quan sát phân phối và lỗi theo instance

Để biết client thực sự dùng nhiều server instance, cần ghi nhận backend nhận RPC thay vì chỉ nhìn số replica trong deployment:

- Số RPC theo service, method và instance ID.
- Số subchannel theo trạng thái `READY`, `CONNECTING`, `TRANSIENT_FAILURE`.
- Số endpoint resolver trả về và thời điểm danh sách thay đổi.
- Latency, status code và tỷ lệ lỗi theo instance.
- Số stream đang mở, tuổi stream và số lần reconnect.
- Thời gian từ khi instance được công bố đến khi subchannel sẵn sàng.
- Số lần graceful shutdown kết thúc khi còn RPC đang chạy.

Không ghi token hoặc payload nhạy cảm để phân biệt backend. Có thể dùng instance ID không nhạy cảm trong log/metric và correlation ID để liên kết một RPC với trace.

Nếu một instance nhận ít request hơn, kiểm tra resolver có trả địa chỉ đó không, subchannel có `READY` không, service config có ghi đè policy không và request có bị giữ ở một backend bởi affinity hay không.

## 14. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Hard-code một IP của replica | Client không thấy instance mới hoặc endpoint thay đổi | Dùng service target và resolver |
| Tạo channel mới cho mỗi request | Tốn kết nối, TLS handshake và tài nguyên | Dùng channel bean dài hạn |
| Có nhiều replica nhưng resolver chỉ trả một virtual IP | Client không trực tiếp phân phối đến từng replica | Xác định load balancing ở client hay hạ tầng |
| Dùng `round_robin` nhưng chỉ một subchannel `READY` | RPC vẫn tập trung vào một instance | Kiểm tra readiness và trạng thái kết nối |
| Lưu session/job state chỉ trong RAM một instance | RPC tiếp theo đến instance khác không tìm thấy state | Dùng kho state dùng chung hoặc cơ chế affinity có kiểm soát |
| Nghĩ stream tự chuyển backend khi instance dừng | RPC hiện tại thất bại và dữ liệu có thể bị gián đoạn | Reconnect/resume bằng cursor |
| Gỡ instance ngay khi bắt đầu shutdown | RPC đang chạy bị cắt đột ngột | Graceful shutdown và grace period |
| Không kiểm tra schema giữa các replica | Client gặp hành vi khác nhau tùy backend | Rollout tương thích và kiểm thử nhiều phiên bản |

**Ghi nhớ:** Để kết nối đến nhiều server instance, client nên dùng một `ManagedChannel` hướng đến service target, resolver cung cấp các endpoint và load balancing policy chọn subchannel cho từng RPC mới. Các instance phải tương thích hợp đồng, có readiness và TLS phù hợp, đồng thời chia sẻ state cần thiết. Một RPC đang chạy vẫn gắn với backend đã nhận nó; failover cho RPC mới không tự phục hồi stream hay side effect. Hãy quản lý channel theo lifecycle Spring, kiểm thử với nhiều backend thật và quan sát phân phối theo instance.

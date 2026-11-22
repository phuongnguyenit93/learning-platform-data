# Client-side load balancing

## 1. Client chọn backend cho từng RPC

Trong **SPRING_GRPC**, client và server giao tiếp bằng gRPC, hợp đồng Protocol Buffers và mã Java được sinh. Khi một service có nhiều instance cùng cung cấp một API, client cần biết địa chỉ các instance và quyết định gửi từng RPC đến đâu. **Client-side load balancing** là mô hình trong đó gRPC client nhận danh sách endpoint từ cơ chế name resolution rồi chọn một backend cho mỗi lời gọi.

Ví dụ service `orders` có ba instance:

~~~text
orders.internal
   |
   +--> 10.20.0.11:9090  (instance A)
   +--> 10.20.0.12:9090  (instance B)
   +--> 10.20.0.13:9090  (instance C)

Client tạo một ManagedChannel
   |
   +--> resolver tìm endpoint
   +--> load balancing policy chọn subchannel
   +--> RPC được gửi đến một backend
~~~

Channel không nhất thiết tương ứng với một kết nối TCP duy nhất. Một `ManagedChannel` có thể quản lý nhiều **subchannel**, mỗi subchannel đại diện cho kết nối đến một endpoint. Load balancer dùng trạng thái các subchannel để chọn nơi gửi RPC.

Mục tiêu của client-side load balancing:

- Phân phối RPC đến nhiều instance thay vì dồn mọi request vào một backend.
- Phát hiện endpoint mới hoặc endpoint đã biến mất qua name resolution.
- Chọn kết nối sẵn sàng theo policy.
- Tiếp tục hoạt động khi một số backend không sẵn sàng, trong phạm vi policy và trạng thái kết nối cho phép.

Điều này khác với việc tạo một `ManagedChannel` mới cho mỗi request. Channel nên được tái sử dụng; load balancer bên trong channel mới là thành phần chọn backend cho các RPC.

## 2. Các thành phần phối hợp

Một channel client-side thường có bốn phần:

1. **Target:** tên service hoặc địa chỉ đích, ví dụ `dns:///orders.internal:9090`.
2. **Name resolver:** phân giải target thành danh sách địa chỉ. Resolver có thể dùng DNS hoặc service discovery do hệ thống cung cấp.
3. **Load balancing policy:** nhận danh sách địa chỉ và trạng thái kết nối, rồi chọn subchannel cho RPC.
4. **Subchannel/transport:** duy trì kết nối đến backend và vận chuyển các message gRPC.

~~~mermaid
flowchart TD
    A["Generated stub"] --> B["ManagedChannel"]
    B --> C["Name resolver"]
    C --> D["Danh sách backend addresses"]
    D --> E["Load balancing policy"]
    E --> F["Subchannel A"]
    E --> G["Subchannel B"]
    E --> H["Subchannel C"]
    F --> I["Backend A"]
    G --> J["Backend B"]
    H --> K["Backend C"]
~~~

Resolver không tự cân bằng tải. Nó cung cấp **địa chỉ**. Policy mới quyết định cách sử dụng các địa chỉ đó. Tương tự, policy không tự phát hiện instance mới nếu resolver không cập nhật danh sách endpoint.

Với DNS, target có dạng:

~~~text
dns:///orders.internal:9090
~~~

Ba dấu `/` sau `dns:` biểu thị target dùng DNS resolver với authority rỗng và phần địa chỉ là `orders.internal:9090`. Trong môi trường có resolver riêng, target scheme và cấu hình sẽ phụ thuộc provider mà ứng dụng cài đặt.

## 3. pick_first và round_robin

Hai policy thường gặp trong gRPC Java:

| Policy | Cách chọn | Phù hợp khi |
|---|---|---|
| `pick_first` | Chọn một subchannel sẵn sàng từ danh sách và dùng nó cho các RPC; có thể chuyển sang địa chỉ khác khi kết nối không sẵn sàng theo trạng thái/policy | Muốn một kết nối hoạt động chính, đơn giản và có khả năng chuyển địa chỉ khi lỗi |
| `round_robin` | Phân phối các RPC mới lần lượt qua các subchannel sẵn sàng | Muốn tận dụng nhiều backend cùng lúc |

Ví dụ với ba backend đều sẵn sàng, các RPC mới có thể được phân phối:

~~~text
round_robin:
RPC 1 -> A
RPC 2 -> B
RPC 3 -> C
RPC 4 -> A
RPC 5 -> B
RPC 6 -> C
~~~

Đây là mô hình minh họa, không phải cam kết rằng mọi RPC sẽ luôn theo chuỗi cố định A-B-C. Khi một subchannel chưa sẵn sàng, resolver thay đổi danh sách hoặc policy cập nhật trạng thái, picker có thể chọn một backend khác. Nếu chỉ có một subchannel ready, `round_robin` chỉ có thể chọn subchannel đó.

`pick_first` không có nghĩa là “không bao giờ failover”. Nó ưu tiên một subchannel theo danh sách và có thể thử địa chỉ khác khi địa chỉ hiện tại không hoạt động. Ngược lại, `round_robin` không có nghĩa là chia đều chính xác số request hoặc CPU: các RPC có thời lượng và chi phí khác nhau, và policy thường phân phối theo lượt trên các subchannel ready chứ không đo tải nghiệp vụ của từng instance.

## 4. Cấu hình round_robin trong gRPC Java

Ví dụ client tạo một channel đến DNS target và chọn policy `round_robin`:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders.internal:9090")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();
~~~

Sau đó dùng generated stub như bình thường:

~~~java
OrdersGrpc.OrdersBlockingStub orders =
        OrdersGrpc.newBlockingStub(channel);

GetOrderReply reply = orders
        .withDeadlineAfter(2, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(GetOrderRequest.newBuilder()
                .setOrderId("ORD-42")
                .build());
~~~

Các RPC mới dùng cùng channel sẽ được policy chọn backend. Không cần tự đọc danh sách IP rồi chọn ngẫu nhiên trong từng service method.

`useTransportSecurity()` bật TLS cho kết nối. Chứng chỉ server phải hợp lệ với tên host/authority mà client sử dụng. `usePlaintext()` chỉ nên dùng trong môi trường phát triển được kiểm soát.

`defaultLoadBalancingPolicy("round_robin")` là policy mặc định khi resolver không cung cấp policy trong service config. Service config do resolver cung cấp có thể chỉ định policy riêng và có thể được ưu tiên hơn giá trị mặc định. Provider của policy cũng phải có trong runtime; nếu policy không được đăng ký, channel không thể sử dụng policy đó.

## 5. Tích hợp channel vào Spring

Trong ứng dụng Spring, nên tạo và quản lý `ManagedChannel` như một bean dùng chung. Mỗi request tạo stub từ channel đã có; không tạo channel mới cho từng lần gọi:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GrpcClientConfiguration {

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

Client service nhận channel qua constructor injection:

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

Đây là khung cấu hình minh họa. Nếu ứng dụng có nhiều gRPC target, nên khai báo channel bean riêng cho từng service và đặt tên qualifier rõ ràng. Cấu hình endpoint, TLS credentials, resolver và policy có thể được bind từ properties theo cơ chế của starter Spring gRPC đang sử dụng; tên property cụ thể phụ thuộc thư viện/phiên bản.

Channel là tài nguyên dài hạn, thread-safe và có thể phục vụ nhiều stub/RPC. Khi Spring context dừng, `destroyMethod = "shutdown"` khởi động quá trình đóng channel trật tự. Nếu cần shutdown có thời gian chờ, có thể quản lý `shutdown()`, `awaitTermination(...)` rồi mới `shutdownNow()` theo lifecycle của ứng dụng.

## 6. Name resolution quyết định client nhìn thấy backend nào

Client-side load balancing chỉ phân phối trên những endpoint mà resolver cung cấp. Nếu DNS chỉ trả về một địa chỉ, `round_robin` không thể tự biết phía sau địa chỉ đó có bao nhiêu instance.

Ví dụ trong Kubernetes:

- **Service kiểu ClusterIP:** DNS thường trả một virtual IP. Client nhìn thấy một endpoint; việc phân phối đến pod do mạng/service proxy của Kubernetes đảm nhiệm. Đây là load balancing phía hạ tầng, không phải client trực tiếp chọn từng pod.
- **Headless Service:** DNS có thể trả nhiều pod IP. Resolver có thể nhìn thấy các endpoint riêng biệt; `round_robin` có thể phân phối RPC giữa các địa chỉ đó.
- **Service discovery riêng:** resolver tùy biến có thể lấy endpoint từ registry hoặc control plane, cập nhật địa chỉ và attributes khi instance thay đổi.

Không nên giả định rằng mọi DNS resolver đều trả danh sách pod theo cách giống nhau. Hãy kiểm tra kết quả name resolution trong môi trường triển khai. Nếu resolver chỉ trả một địa chỉ, thay đổi policy từ `pick_first` sang `round_robin` sẽ không tạo ra nhiều backend để phân phối.

Resolver cũng cần cập nhật khi instance thêm, xóa hoặc thay IP. Policy nhận danh sách mới và điều chỉnh subchannel. Khi backend bị gỡ khỏi danh sách, các RPC mới không nên tiếp tục được chọn vào endpoint đó; RPC đang chạy có thể vẫn cần thời gian kết thúc hoặc bị lỗi tùy transport và trạng thái instance.

## 7. Backend readiness và hành vi khi không có endpoint sẵn sàng

Một địa chỉ có trong DNS không đồng nghĩa backend đã sẵn sàng phục vụ. Kết nối có thể đang `CONNECTING`, `TRANSIENT_FAILURE`, `IDLE` hoặc `READY`. Policy sử dụng trạng thái subchannel để chọn kết nối phù hợp.

Nếu không có subchannel ready:

- RPC có thể thất bại với lỗi kết nối tùy trạng thái và cấu hình.
- Client có thể dùng `withWaitForReady()` để đợi channel có backend sẵn sàng, thay vì thất bại ngay khi picker không có kết nối.
- Deadline vẫn áp dụng trong thời gian chờ; `waitForReady` không làm RPC chờ vô hạn.

Ví dụ:

~~~java
GetOrderReply reply = orders
        .withWaitForReady()
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(request);
~~~

`waitForReady` hữu ích khi backend tạm thời chưa sẵn sàng và request còn ý nghĩa sau một khoảng chờ ngắn. Nó không thay thế retry policy, không bảo đảm request sẽ được xử lý, và không nên dùng cho mọi RPC nếu request hết hạn nhanh hoặc không còn ý nghĩa khi chờ.

Readiness ở tầng gRPC chủ yếu phản ánh trạng thái kết nối/subchannel. Để tránh gửi request đến instance đã khởi động nhưng chưa sẵn sàng về nghiệp vụ, cần kết hợp health checking, readiness của nền tảng triển khai hoặc service discovery chỉ công bố endpoint đã sẵn sàng.

## 8. Một server stream được gắn với một backend

Load balancing chọn backend khi một RPC bắt đầu. Với unary RPC, mỗi lời gọi mới có thể được chọn sang backend khác. Với **server streaming**, toàn bộ RPC thường gắn với backend đã nhận lời gọi đó:

~~~text
WatchProgress RPC #1
    -> backend A
    <- event 1 từ A
    <- event 2 từ A
    <- event 3 từ A
    <- stream kết thúc

WatchProgress RPC #2 (lời gọi mới)
    -> backend B có thể được chọn
~~~

gRPC không phân phối từng response của cùng một stream sang các backend khác nhau. Nếu backend A bị dừng giữa stream, RPC đó có thể thất bại; policy không chuyển phần còn lại của stream sang backend B một cách trong suốt. Client cần reconnect bằng RPC mới và dùng cursor/sequence nếu nghiệp vụ yêu cầu tiếp tục từ vị trí đã xử lý.

Điều này đặc biệt quan trọng với server giữ state trong bộ nhớ instance. Nếu stream thứ hai đến backend khác, state cục bộ của backend A không tự xuất hiện ở B. Nên lưu trạng thái job/session ở kho dùng chung hoặc cung cấp cơ chế resume bằng định danh và checkpoint.

## 9. Load balancing không đồng nghĩa retry hay failover trong mọi tình huống

Các cơ chế sau có vai trò khác nhau:

| Cơ chế | Chức năng |
|---|---|
| Client-side load balancing | Chọn subchannel/backend cho một RPC mới |
| Name resolution | Cung cấp và cập nhật danh sách địa chỉ |
| `waitForReady` | Chờ backend/kết nối sẵn sàng trong ngân sách deadline |
| Retry policy | Thử lại RPC theo điều kiện, status và quy tắc commitment |
| Application reconnect/resume | Tạo RPC mới với cursor/checkpoint để tiếp tục stream |
| Server-side/network load balancing | Hạ tầng trung gian chọn backend thay cho client |

Khi một unary RPC lỗi sau khi server có thể đã thực hiện side effect, retry tự động có thể gây lặp nếu request không idempotent. Với server streaming đã phát response, không giả định retry tự động sẽ phát lại dữ liệu. Hãy thiết kế retry/resume riêng theo hợp đồng.

## 10. Session affinity và trạng thái ứng dụng

`round_robin` phân phối RPC giữa các subchannel ready; nó không bảo đảm cùng một người dùng luôn đến cùng một backend. Nếu API cần session affinity, phải có thiết kế rõ:

- Lưu session/job state ở storage dùng chung.
- Dùng định danh hoặc routing key được resolver/policy hỗ trợ nếu hệ thống thật sự yêu cầu affinity.
- Không dựa vào thứ tự round robin để suy ra một caller sẽ luôn đến cùng instance.
- Không nhét dữ liệu bí mật hoặc token thô vào metadata chỉ để tạo khóa định tuyến.

Với gRPC, metadata có thể mang correlation ID hoặc thông tin định tuyến theo hợp đồng hạ tầng, nhưng policy mặc định không tự hiểu một header bất kỳ để chọn backend. Muốn định tuyến theo key cần resolver/load balancer tùy biến hoặc cơ chế proxy phù hợp.

## 11. Kiểm thử và quan sát client-side load balancing

Một bài test load balancing cần xác minh **resolver thực sự cung cấp nhiều địa chỉ** và policy sử dụng chúng. Chỉ khởi tạo một channel đến một server in-process không kiểm tra được phân phối giữa nhiều backend.

Các tình huống nên kiểm thử:

| Tình huống | Điều cần xác minh |
|---|---|
| Resolver trả một endpoint | Mọi RPC đến endpoint duy nhất; không kỳ vọng phân phối |
| Resolver trả ba endpoint ready với `round_robin` | Nhiều RPC mới được phân phối giữa các endpoint |
| Một endpoint không ready | RPC mới được chọn từ các subchannel ready còn lại |
| Resolver thêm endpoint | Channel nhận cập nhật và policy có thể sử dụng endpoint mới |
| Resolver gỡ endpoint | RPC mới không tiếp tục chọn endpoint đã gỡ |
| Không có endpoint ready | Hành vi lỗi hoặc wait-for-ready tuân theo deadline |
| Server stream đang mở và backend dừng | RPC hiện tại có thể lỗi; client reconnect theo cursor nếu cần |
| Nhiều channel được tạo cho mỗi request | Phát hiện lãng phí kết nối và tài nguyên |

Để kiểm thử deterministic, có thể dùng custom `NameResolverProvider` trả danh sách địa chỉ test và nhiều server có thể nhận diện riêng instance. Cần xác minh policy provider `round_robin` được nạp trong runtime. In-process transport phù hợp cho logic gRPC; test resolver/policy nhiều endpoint và TCP/TLS cần fixture tương ứng.

Các metrics hữu ích:

- Số RPC theo backend/target.
- Số subchannel theo trạng thái `READY`, `CONNECTING`, `TRANSIENT_FAILURE`.
- Số lần resolver cập nhật endpoint.
- Tỷ lệ lỗi kết nối, `UNAVAILABLE` và deadline.
- Phân bố latency theo backend để phát hiện một instance chậm.
- Số stream dài theo backend và thời gian sống của stream.

Nếu một backend nhận nhiều request hơn, chưa chắc policy sai: thời lượng RPC, số subchannel ready, resolver trả địa chỉ không đồng đều hoặc request được gửi trước khi mọi backend sẵn sàng đều có thể ảnh hưởng phân bố. Cần quan sát cả endpoint và tải nghiệp vụ.

## 12. Những lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `round_robin` nhưng resolver chỉ trả một IP | Không có nhiều backend để phân phối | Kiểm tra target và kết quả name resolution |
| Tạo channel mới cho từng request | Tăng kết nối, handshake và tài nguyên | Quản lý channel dùng chung theo target |
| Nhầm ClusterIP với danh sách pod | Client không trực tiếp thấy từng instance | Xác định load balancing nằm ở client hay hạ tầng |
| Nghĩ stream tự chuyển backend khi instance chết | RPC hiện tại có thể thất bại giữa chừng | Reconnect bằng RPC mới và resume theo cursor |
| Dùng `waitForReady` mà không deadline | Request có thể chờ quá lâu | Đặt deadline phù hợp cho từng RPC |
| Giả định round robin chia đều CPU | Backend có thể nhận tải không cân xứng | Theo dõi latency, thời lượng và tải thực tế |
| Dùng local session state trên từng backend | RPC mới có thể đến instance khác và mất state | Dùng state store dùng chung hoặc affinity rõ ràng |

**Ghi nhớ:** Client-side load balancing trong gRPC Java kết hợp **name resolver**, **load balancing policy** và các **subchannel** do `ManagedChannel` quản lý. Resolver cung cấp endpoint; `pick_first` ưu tiên một kết nối, còn `round_robin` phân phối RPC mới giữa các subchannel sẵn sàng. Một server stream vẫn gắn với backend đã nhận RPC đó; khi backend lỗi, muốn tiếp tục phải tạo RPC mới và dùng cơ chế resume của ứng dụng. Trong Spring, tái sử dụng channel dùng chung, cấu hình TLS/readiness/deadline và quan sát tải theo backend.

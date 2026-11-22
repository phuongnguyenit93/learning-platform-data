# Round robin và các policy khác

## 1. Load balancing policy quyết định cách chọn backend

Trong **SPRING_GRPC**, một `ManagedChannel` dùng name resolver để tìm endpoint của dịch vụ gRPC. Khi resolver trả về nhiều địa chỉ, channel cần một **load balancing policy** để quyết định subchannel nào nhận RPC mới. Policy ảnh hưởng trực tiếp đến cách sử dụng backend, khả năng tiếp tục khi endpoint lỗi và phân bố tải giữa các instance.

Hai policy cơ bản thường gặp trong gRPC Java là:

- **`pick_first`:** ưu tiên một endpoint kết nối được và tiếp tục dùng endpoint đó; thử địa chỉ khác khi endpoint đang chọn không kết nối được.
- **`round_robin`:** phân phối các RPC mới lần lượt qua những subchannel đang sẵn sàng.

Giả sử resolver cung cấp ba backend A, B và C:

~~~text
Name resolver: [A, B, C]

pick_first:
  RPC 1 -> A
  RPC 2 -> A
  RPC 3 -> A
  ...

round_robin:
  RPC 1 -> A
  RPC 2 -> B
  RPC 3 -> C
  RPC 4 -> A
  ...
~~~

Đây là hành vi khái niệm khi các backend đều `READY`. Thứ tự thực tế phụ thuộc trạng thái kết nối, danh sách resolver và picker hiện tại. Policy không thể phân phối đến endpoint mà resolver không cung cấp.

## 2. Policy hoạt động ở đâu trong vòng đời RPC?

Các thành phần phối hợp theo luồng:

1. **Target** xác định service cần gọi, ví dụ `dns:///orders.internal:9090`.
2. **Name resolver** phân giải target thành một hoặc nhiều `EquivalentAddressGroup`.
3. **Load balancing policy** nhận địa chỉ và trạng thái subchannel, rồi tạo picker.
4. **Picker** chọn subchannel cho RPC mới.
5. **Subchannel** quản lý kết nối đến backend đã chọn.

~~~mermaid
flowchart TD
    A["Generated stub"] --> B["ManagedChannel"]
    B --> C["Name resolver"]
    C --> D["Endpoint list"]
    D --> E["Load balancing policy"]
    E --> F["Picker"]
    F --> G["Subchannel A"]
    F --> H["Subchannel B"]
    F --> I["Subchannel C"]
    G --> J["Backend A"]
    H --> K["Backend B"]
    I --> L["Backend C"]
~~~

Resolver trả lời **có những địa chỉ nào**; policy trả lời **RPC mới đi đến địa chỉ nào**. Vì vậy, thay đổi policy không thể sửa một resolver chỉ trả về một virtual IP. Tương tự, resolver cập nhật danh sách không có nghĩa mọi endpoint mới đã kết nối và sẵn sàng ngay lập tức.

## 3. pick_first: ưu tiên một kết nối hoạt động

`pick_first` phù hợp khi muốn dùng một backend chính tại một thời điểm. Khi có nhiều địa chỉ, policy thử kết nối theo danh sách và chọn một subchannel đạt trạng thái `READY`. Những RPC mới tiếp theo thường tiếp tục đi qua subchannel được chọn đó.

Nếu endpoint hiện tại mất kết nối, policy có thể thử các địa chỉ còn lại. Đây là khả năng chuyển sang endpoint khác khi kết nối không sẵn sàng; nó không phải cơ chế chia đều tải giữa tất cả backend.

**Nên cân nhắc `pick_first` khi:**

- Dịch vụ phía sau đã có load balancer ở tầng mạng hoặc proxy.
- Muốn một kết nối ổn định và không cần client phân phối request qua mọi instance.
- Danh sách địa chỉ chủ yếu phục vụ khả năng thử endpoint dự phòng.
- Tải của một client không cần tận dụng đồng thời nhiều backend.

Không nên hiểu `pick_first` là “luôn luôn chọn địa chỉ đầu tiên bất kể trạng thái”. Endpoint cần kết nối được; khi endpoint đó lỗi, policy có thể chuyển sang địa chỉ khác theo trạng thái và hành vi của implementation.

## 4. round_robin: phân phối RPC mới qua các backend sẵn sàng

`round_robin` tạo/duy trì subchannel cho các địa chỉ resolver cung cấp và phân phối các RPC mới qua những subchannel đang `READY`. Với ba backend sẵn sàng, chuỗi lựa chọn có thể là A, B, C, A, B, C.

Policy này hữu ích khi:

- Client nhìn thấy trực tiếp nhiều instance.
- Các instance cung cấp cùng một service và có thể xử lý request độc lập.
- Muốn một client tận dụng đồng thời nhiều kết nối backend.
- Không có yêu cầu bắt buộc mọi RPC của một caller phải đi cùng một instance.

Round robin **không cân bằng chính xác CPU hoặc thời gian xử lý**. Nó phân phối RPC theo lượt trên các subchannel sẵn sàng, trong khi một RPC có thể tốn 2 ms và RPC khác tốn 2 phút. Một backend cũng có thể nhận tải thực tế cao hơn nếu request gửi đến nó nặng hơn.

Nếu chỉ B đang `READY`, các RPC mới sẽ đi qua B dù resolver vẫn trả A, B và C. Khi A hoặc C trở lại `READY`, chúng có thể tham gia lựa chọn tiếp theo.

## 5. So sánh policy và chọn theo kiến trúc

| Tiêu chí | `pick_first` | `round_robin` |
|---|---|---|
| Mục tiêu | Dùng một subchannel hoạt động | Phân phối RPC mới qua nhiều subchannel ready |
| Kết nối đến backend | Ưu tiên một endpoint; thử địa chỉ khác khi cần | Duy trì các subchannel cho danh sách endpoint |
| Phân phối tải từ một client | Tập trung vào backend đang chọn | Có thể tận dụng nhiều backend |
| Khi endpoint lỗi | Có thể chuyển sang endpoint khác | Loại endpoint không ready khỏi lựa chọn hiện tại |
| Phụ thuộc resolver | Cần resolver cung cấp địa chỉ dự phòng | Cần resolver cung cấp nhiều endpoint riêng biệt |
| Tình huống thường gặp | Hạ tầng đã cân bằng tải ở phía trước | Client trực tiếp nhìn thấy nhiều instance |

Ví dụ:

- Ứng dụng gọi một virtual IP của Kubernetes ClusterIP: hạ tầng Kubernetes phân phối đến pod; `pick_first` có thể là lựa chọn đủ dùng vì client chỉ nhìn thấy một endpoint.
- Ứng dụng gọi headless Service trả nhiều pod IP: `round_robin` có thể phân phối RPC trực tiếp giữa các pod nếu resolver nhận được các IP và các subchannel sẵn sàng.
- Một hệ thống cần định tuyến theo vùng, trọng số hoặc mức tải: policy cơ bản có thể chưa đủ; cần control plane hoặc policy mở rộng hỗ trợ thuộc tính đó.

Không có policy nào tốt nhất trong mọi trường hợp. Chọn dựa trên **nơi đặt load balancing**, số endpoint mà client thực sự nhìn thấy, trạng thái readiness và đặc tính RPC.

## 6. Cấu hình policy trong gRPC Java

Ví dụ đặt `round_robin` làm policy mặc định cho channel:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders.internal:9090")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();
~~~

`defaultLoadBalancingPolicy(...)` là lựa chọn mặc định khi resolver không cung cấp service config chỉ định policy. Resolver có thể cung cấp service config riêng; khi đó cấu hình trong service config có thể quyết định policy được dùng.

Một service config có thể biểu diễn policy bằng JSON:

~~~json
{
  "loadBalancingConfig": [
    {
      "round_robin": {}
    }
  ]
}
~~~

Đây là cấu trúc minh họa cho trường `loadBalancingConfig`; cách cung cấp service config phụ thuộc resolver và cấu hình channel. Policy phải có provider được nạp trong runtime. Nếu chọn một policy mà ứng dụng không có provider tương ứng, channel không thể khởi tạo policy đó như mong muốn.

Trong gRPC Java, `pick_first` là policy cơ bản; `round_robin` cần provider tương ứng có trong dependency/runtime của ứng dụng. Hãy kiểm tra dependency graph và log khởi tạo channel thay vì giả định mọi policy đều có sẵn trong mọi bộ dependency.

## 7. Các policy mở rộng và service mesh

Khi yêu cầu vượt quá hai cách chọn cơ bản, hệ sinh thái gRPC có thể sử dụng policy do extension hoặc xDS control plane cung cấp. Tùy runtime và phiên bản, các khả năng mở rộng có thể gồm:

- **Weighted:** phân phối theo trọng số, ví dụ canary nhận 5% và phiên bản ổn định nhận 95%.
- **Priority/failover:** ưu tiên một nhóm endpoint, chuyển sang nhóm dự phòng khi nhóm chính không còn khả dụng.
- **Locality-aware:** ưu tiên endpoint trong vùng hoặc cụm gần client để giảm độ trễ.
- **Ring hash:** định tuyến ổn định theo khóa, hữu ích khi cần affinity ở tầng định tuyến.
- **Least request:** chọn endpoint theo số request đang hoạt động, nếu policy/control plane hỗ trợ.

Đây không phải danh sách policy mặc định có sẵn trong mọi gRPC Java client. Khả năng sử dụng phụ thuộc xDS integration, provider, service config và phiên bản thư viện. Không thể chỉ gọi `defaultLoadBalancingPolicy("least_request")` rồi kỳ vọng policy xuất hiện nếu runtime không có implementation.

Với canary hoặc locality, control plane thường là nơi quản lý trọng số, endpoint và chính sách. Client nhận cấu hình qua resolver/xDS rồi thực thi lựa chọn. Cần quan sát cấu hình thực tế được áp dụng, không chỉ cấu hình dự định trong manifest.

## 8. Tích hợp channel dùng chung trong Spring

Trong Spring, tạo channel theo target và tái sử dụng trong suốt vòng đời ứng dụng. Mỗi client service có thể tạo stub từ channel:

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
                .defaultLoadBalancingPolicy("round_robin")
                .useTransportSecurity()
                .build();
    }
}
~~~

Stub:

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

Nếu có nhiều target, khai báo channel bean riêng và dùng qualifier rõ ràng. Không tạo channel mới cho từng RPC: điều đó làm tăng DNS lookup, kết nối TCP, TLS handshake và chi phí thread/buffer.

`useTransportSecurity()` yêu cầu chứng chỉ server phù hợp với authority/hostname của target. Với môi trường production, giữ xác minh chứng chỉ và cấu hình trust đúng; `usePlaintext()` chỉ phù hợp môi trường phát triển được kiểm soát.

## 9. Readiness, wait-for-ready và deadline

Policy chọn từ các subchannel có trạng thái phù hợp. Một địa chỉ có trong kết quả resolver chưa có nghĩa kết nối đã `READY`. Subchannel có thể đang `IDLE`, `CONNECTING`, `TRANSIENT_FAILURE` hoặc `READY`.

Nếu chưa có backend ready, client có thể dùng `withWaitForReady()` để chờ kết nối thay vì thất bại ngay:

~~~java
GetOrderReply reply = orders
        .withWaitForReady()
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(request);
~~~

`waitForReady` không tạo endpoint mới và không bỏ qua deadline. Nó chỉ cho phép RPC chờ trong thời gian còn lại của deadline để channel có cơ hội tìm backend sẵn sàng.

Readiness của transport cũng không thay thế health check nghiệp vụ. Một tiến trình có thể mở port gRPC nhưng chưa tải xong dữ liệu hoặc chưa sẵn sàng nhận request. Kết hợp health checking, readiness probe và service discovery chỉ công bố endpoint có thể phục vụ.

## 10. Policy chọn backend cho server stream như thế nào?

Load balancing policy chọn backend **khi RPC bắt đầu**. Với unary RPC, mỗi lời gọi mới có thể được chọn sang một subchannel khác. Với server streaming, toàn bộ RPC thường gắn với backend đã nhận lời gọi đó:

~~~text
WatchProgress RPC #1
    -> backend A
    <- event 1 từ A
    <- event 2 từ A
    <- event 3 từ A
    <- stream kết thúc

WatchProgress RPC #2 (RPC mới)
    -> backend B có thể được policy chọn
~~~

`round_robin` không chuyển từng response của một stream sang các backend khác nhau. Nếu backend A lỗi giữa stream, RPC hiện tại có thể thất bại; policy không thể tiếp tục phần còn lại của stream ở B một cách trong suốt.

Nếu nghiệp vụ cần reconnect:

1. Server phát event có sequence/cursor ổn định.
2. Client lưu checkpoint sau khi xử lý bền vững.
3. Khi stream lỗi, client tạo RPC mới và gửi cursor.
4. Backend mới đọc lại phần còn thiếu từ nguồn dữ liệu dùng chung.

Vì vậy, server stream dài cần state dùng chung hoặc cơ chế replay/resume; state chỉ nằm trong RAM của backend A không tự chuyển sang backend B.

## 11. Kiểm thử và quan sát policy

Một test có một server không thể chứng minh `round_robin` phân phối qua nhiều backend. Để kiểm thử, cần resolver trả nhiều địa chỉ, nhiều server có thể phân biệt bằng instance ID và xác nhận backend đã nhận từng RPC.

| Tình huống | Điều cần xác minh |
|---|---|
| Resolver trả một endpoint | Cả hai policy chỉ có một backend để chọn |
| Nhiều endpoint đều ready với `pick_first` | RPC mới tập trung vào subchannel được chọn |
| Nhiều endpoint ready với `round_robin` | RPC mới được phân phối qua các subchannel |
| Một endpoint chuyển sang lỗi | Picker không tiếp tục chọn endpoint không ready |
| Resolver thêm hoặc xóa endpoint | Policy cập nhật subchannel theo danh sách mới |
| Không có endpoint ready | Lỗi hoặc wait-for-ready tuân theo deadline |
| Server stream đang chạy khi backend dừng | RPC hiện tại có thể lỗi; client resume bằng RPC mới nếu hợp đồng hỗ trợ |
| Policy provider không có trong runtime | Channel không áp dụng được policy đã cấu hình |

Các chỉ số vận hành hữu ích:

- Số RPC theo backend và theo policy.
- Số subchannel theo trạng thái `READY`, `CONNECTING`, `TRANSIENT_FAILURE`.
- Số lần resolver cập nhật địa chỉ.
- Latency và tỷ lệ lỗi theo backend.
- Số stream dài và thời gian sống theo instance.
- Số lần reconnect/resume sau khi backend bị loại hoặc dừng.

Nếu `round_robin` không phân phối như mong đợi, kiểm tra theo thứ tự: resolver có trả nhiều endpoint riêng biệt không, service config có ghi đè policy mặc định không, provider có được nạp không, và có bao nhiêu subchannel đang `READY`. Đừng kết luận chỉ từ cấu hình channel.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `round_robin` luôn chia đều CPU | Policy phân phối RPC mới theo lượt trên subchannel ready, không đo chi phí nghiệp vụ |
| DNS trả nhiều IP thì tự động round robin | DNS cung cấp địa chỉ; gRPC policy chọn subchannel |
| `pick_first` không thể chuyển endpoint | Nó có thể thử địa chỉ khác khi endpoint hiện tại không kết nối được |
| Policy thay đổi backend giữa một stream | Một RPC đang chạy thường gắn với backend đã nhận nó |
| `waitForReady` là retry vô hạn | Deadline vẫn giới hạn thời gian chờ |
| Mọi policy đều có sẵn trong gRPC Java core | Policy mở rộng cần provider/runtime phù hợp |
| Tạo channel mới giúp policy cập nhật nhanh hơn | Channel dài hạn có resolver và subchannel lifecycle để nhận cập nhật |

**Ghi nhớ:** `pick_first` ưu tiên một backend kết nối được; `round_robin` phân phối RPC mới qua các subchannel `READY`. Các policy mở rộng như weighted, priority, locality-aware, ring hash hoặc least request phụ thuộc provider và control plane, không mặc định có trong mọi runtime. Hãy chọn policy theo kiến trúc resolver và vị trí đặt load balancer, cấu hình channel dùng chung trong Spring, đặt deadline/readiness hợp lý và nhớ rằng một server stream không tự chuyển backend giữa chừng.

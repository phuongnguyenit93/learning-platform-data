# Name resolution trả nhiều địa chỉ

## 1. Resolver cung cấp endpoint, policy quyết định cách dùng

Trong **SPRING_GRPC**, client gọi dịch vụ gRPC qua một `ManagedChannel` và các stub được sinh từ hợp đồng Protocol Buffers. Khi một dịch vụ có nhiều instance, client cần phân giải tên service thành các địa chỉ có thể kết nối. **Name resolution trả nhiều địa chỉ** nghĩa là resolver cung cấp cho channel một tập endpoint thay vì một địa chỉ duy nhất.

Ví dụ service `inventory.internal:9090` có ba backend:

~~~text
inventory.internal
  ├── 10.30.1.21:9090
  ├── 10.30.1.22:9090
  └── 10.30.1.23:9090
~~~

Resolver tìm ra các địa chỉ đó và thông báo cho gRPC channel. Một **load balancing policy** tiếp nhận danh sách cùng trạng thái kết nối, rồi chọn subchannel cho RPC mới.

Hai trách nhiệm phải được phân biệt:

- **Name resolver:** “Có những endpoint nào cho service này?”
- **Load balancing policy:** “Trong các endpoint hiện có, RPC tiếp theo sẽ đi đến đâu?”

DNS trả ba địa chỉ không tự động có nghĩa ba địa chỉ sẽ nhận số request bằng nhau. Nếu policy chỉ dùng một endpoint tại một thời điểm, các địa chỉ còn lại có thể chỉ được dùng khi endpoint hiện tại không sẵn sàng. Muốn phân phối RPC mới qua nhiều backend, client cần policy phù hợp, chẳng hạn `round_robin`.

## 2. Target và cơ chế DNS resolution trong gRPC Java

Một target gRPC là URI cho biết cơ chế phân giải và địa chỉ service. Với DNS resolver tích hợp, dạng thường dùng là:

~~~text
dns:///inventory.internal:9090
~~~

Trong URI này:

- `dns` là scheme chọn DNS name resolver.
- Phần authority để trống; vì vậy URI có ba dấu slash sau dấu hai chấm.
- `inventory.internal:9090` là hostname và port cần phân giải.

Resolver tra cứu hostname và có thể nhận nhiều địa chỉ IP, ví dụ bản ghi IPv4 (A) và IPv6 (AAAA). Kết quả thực tế phụ thuộc DNS, môi trường mạng, thứ tự địa chỉ và bộ phân giải của runtime.

~~~text
DNS answer:
  inventory.internal.  A     10.30.1.21
  inventory.internal.  A     10.30.1.22
  inventory.internal.  A     10.30.1.23

Name resolver result:
  10.30.1.21:9090
  10.30.1.22:9090
  10.30.1.23:9090
~~~

Không nên giả định DNS luôn trả nhiều địa chỉ. Nếu DNS chỉ trả một địa chỉ, client chỉ có một endpoint để chọn. Cũng không nên giả định mọi DNS record đều là một backend riêng: một địa chỉ có thể là virtual IP, proxy hoặc load balancer của hạ tầng.

## 3. Resolver trả danh sách địa chỉ cho gRPC channel

Trong gRPC Java, kết quả phân giải được biểu diễn qua `ResolutionResult` và danh sách `EquivalentAddressGroup`. Mỗi group chứa một hoặc nhiều địa chỉ được xem là tương đương cho mục đích kết nối. Với ví dụ đơn giản, mỗi backend có một group:

~~~java
import io.grpc.EquivalentAddressGroup;
import io.grpc.NameResolver;

import java.net.InetSocketAddress;
import java.util.List;

List<EquivalentAddressGroup> endpoints = List.of(
        new EquivalentAddressGroup(
                new InetSocketAddress("10.30.1.21", 9090)),
        new EquivalentAddressGroup(
                new InetSocketAddress("10.30.1.22", 9090)),
        new EquivalentAddressGroup(
                new InetSocketAddress("10.30.1.23", 9090))
);

NameResolver.ResolutionResult result =
        NameResolver.ResolutionResult.newBuilder()
                .setAddresses(endpoints)
                .setAttributes(io.grpc.Attributes.EMPTY)
                .build();

// Trong custom NameResolver, gửi kết quả đến listener:
listener.onResult(result);
~~~

Đây là phần minh họa cách tạo kết quả; `listener` thuộc vòng đời của một custom `NameResolver`. Khi dùng DNS resolver có sẵn, ứng dụng không tự tạo các group này. Resolver gửi danh sách cho channel, rồi policy sử dụng nó để tạo/cập nhật subchannel.

`EquivalentAddressGroup` không phải một request hay một response protobuf. Nó là đơn vị địa chỉ ở tầng transport. Một group có thể chứa nhiều socket address tương đương; số group và cách policy diễn giải chúng có ảnh hưởng đến cách subchannel được tạo.

Resolver có thể gửi các kết quả mới khi địa chỉ thay đổi. Channel không cần được tạo lại chỉ vì DNS record đổi; policy nhận cập nhật và điều chỉnh các subchannel theo kết quả mới.

## 4. Nhiều địa chỉ không đồng nghĩa với round robin

Giả sử resolver trả ba endpoint A, B và C. Kết quả phân phối phụ thuộc policy:

~~~text
Resolver:
  [A, B, C]

pick_first:
  RPC 1 -> A
  RPC 2 -> A
  RPC 3 -> A
  ...
  Nếu A không kết nối được, policy thử endpoint khác theo trạng thái.

round_robin:
  RPC 1 -> A
  RPC 2 -> B
  RPC 3 -> C
  RPC 4 -> A
  ...
~~~

Đây là sơ đồ khái niệm khi các backend đều sẵn sàng. Thứ tự thực tế còn phụ thuộc trạng thái subchannel, cập nhật resolver và picker hiện hành.

| Resolver trả về | Policy | Kết quả mong đợi |
|---|---|---|
| Một địa chỉ A | `pick_first` | RPC đi đến A |
| A, B, C | `pick_first` | Dùng một endpoint đang kết nối được; có thể thử địa chỉ khác khi cần |
| A, B, C | `round_robin` | Phân phối RPC mới giữa các subchannel sẵn sàng |
| A, B, C nhưng chỉ B ready | `round_robin` | RPC mới được chọn từ B khi B là endpoint ready duy nhất |
| Danh sách rỗng | Bất kỳ policy nào | Không có backend để chọn; RPC có thể chờ hoặc thất bại theo readiness/deadline |

Điểm dễ nhầm là **DNS round robin** và **gRPC `round_robin` policy** không phải cùng một cơ chế. DNS có thể xoay thứ tự hoặc trả nhiều record, nhưng cache DNS và resolver có thể khiến thứ tự không đổi giữa các lần tra cứu. gRPC policy mới là thành phần chọn subchannel cho từng RPC dựa trên các endpoint đã phân giải.

## 5. Cấu hình client dùng nhiều địa chỉ với round_robin

Khi resolver trả nhiều endpoint riêng biệt, client có thể cấu hình channel dùng `round_robin`:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///inventory.internal:9090")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();
~~~

Stub được tạo từ channel và sử dụng như bình thường:

~~~java
InventoryGrpc.InventoryBlockingStub inventory =
        InventoryGrpc.newBlockingStub(channel);

StockReply reply = inventory
        .withDeadlineAfter(2, java.util.concurrent.TimeUnit.SECONDS)
        .getStock(StockRequest.newBuilder()
                .setSku("SKU-42")
                .build());
~~~

`defaultLoadBalancingPolicy("round_robin")` chỉ là policy mặc định khi resolver không cung cấp service config có policy khác. Nếu resolver trả service config chứa load balancing policy, cấu hình đó có thể quyết định policy được dùng. Provider của `round_robin` cũng phải có trong runtime; nếu thiếu provider, channel không thể áp dụng policy đó.

Channel nên được tái sử dụng trong suốt vòng đời ứng dụng. Không tạo một channel mới cho từng request vì việc đó làm tăng kết nối, TLS handshake, DNS resolution và chi phí quản lý tài nguyên.

## 6. Khi DNS trả nhiều địa chỉ trong Kubernetes

Kết quả DNS phụ thuộc loại Service và cấu hình cluster:

| Kiểu Service | DNS thường cung cấp | Ai chọn pod/backend? |
|---|---|---|
| ClusterIP | Một virtual IP của Service | Network/service proxy của Kubernetes |
| Headless Service | Có thể trả địa chỉ IP của các pod | Client có thể thấy từng endpoint nếu resolver nhận được danh sách đó |

Với ClusterIP, client-side `round_robin` có thể chỉ nhìn thấy một địa chỉ. Việc chia tải đến pod xảy ra ở lớp mạng của Kubernetes. Đổi policy gRPC sang `round_robin` không khiến client biết các pod phía sau virtual IP.

Với headless Service, DNS có thể trả nhiều pod IP. Khi gRPC resolver nhận các IP đó thành nhiều endpoint, policy như `round_robin` có thể tạo các subchannel và phân phối RPC mới qua những backend sẵn sàng.

Không nên suy luận từ YAML Service rằng client chắc chắn nhìn thấy bao nhiêu địa chỉ. Hãy kiểm tra DNS answer từ đúng namespace/network nơi client chạy, đồng thời quan sát kết quả resolver nếu có công cụ tracing phù hợp. DNS record có thể chịu ảnh hưởng của TTL, cache trong JVM, cache của node hoặc resolver trung gian.

## 7. Resolver refresh và vòng đời endpoint

Danh sách endpoint không cố định. Instance có thể được thêm, xóa, thay IP hoặc tạm thời mất kết nối. Name resolver có thể phát kết quả mới theo cơ chế refresh của provider. Khi nhận cập nhật, channel và policy điều chỉnh subchannel:

~~~mermaid
sequenceDiagram
    participant R as Name resolver
    participant C as ManagedChannel
    participant L as Load balancer
    participant B as Backend instances
    R-->>C: ResolutionResult [A, B]
    C->>L: Cập nhật địa chỉ
    L->>B: Tạo/duy trì subchannel A và B
    Note over B: Instance C được triển khai
    R-->>C: ResolutionResult [A, B, C]
    C->>L: Cập nhật danh sách
    L->>B: Tạo subchannel C
    Note over L: RPC mới có thể chọn C khi ready
~~~

Một số lưu ý:

- Resolver cập nhật địa chỉ không đồng nghĩa kết nối đến endpoint mới đã `READY` ngay lập tức.
- Endpoint mới có thể cần DNS lookup, TCP connect, TLS handshake và health/readiness check.
- Endpoint bị loại khỏi kết quả resolution không nên được picker chọn cho RPC mới sau khi cập nhật được áp dụng; RPC đang chạy có thể vẫn cần thời gian kết thúc hoặc bị lỗi tùy transport.
- Nếu DNS cache giữ kết quả cũ, client có thể chưa nhìn thấy thay đổi ngay. TTL không phải cam kết rằng mọi lớp cache đều refresh đồng thời.
- Resolver có thể trả lỗi resolution; channel cần chuyển trạng thái phù hợp và client cần deadline hoặc wait-for-ready có giới hạn.

Không nên tự đặt một timer trong business service để tạo lại channel mỗi vài giây. Hãy dùng resolver và lifecycle channel đúng cách; việc refresh và cập nhật subchannel thuộc lớp name resolution/load balancing.

## 8. Khi không có địa chỉ hoặc không có backend sẵn sàng

Hai trạng thái này khác nhau:

- **Không có địa chỉ:** resolver chưa tìm thấy endpoint, trả danh sách rỗng hoặc báo lỗi resolution.
- **Có địa chỉ nhưng chưa ready:** resolver đã tìm thấy endpoint, nhưng subchannel chưa kết nối được hoặc đang ở trạng thái lỗi.

Khi không có backend sẵn sàng, client có thể thất bại ngay hoặc chờ nếu RPC dùng `withWaitForReady()`. Dù chờ, deadline vẫn giới hạn tổng thời gian:

~~~java
StockReply reply = inventory
        .withWaitForReady()
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getStock(request);
~~~

`waitForReady` hữu ích khi endpoint có thể xuất hiện hoặc kết nối có thể phục hồi trong một khoảng chờ ngắn. Nó không tạo endpoint mới, không sửa lỗi DNS và không làm request chờ vô hạn. Khi deadline hết, client vẫn nhận kết cục quá hạn.

Một địa chỉ xuất hiện trong DNS cũng chưa chứng minh ứng dụng phía sau đã sẵn sàng về nghiệp vụ. Để tránh gửi RPC đến instance vừa khởi động nhưng chưa thể phục vụ, kết hợp readiness probe/service health checking và chỉ công bố endpoint đủ điều kiện.

## 9. Địa chỉ được phân giải và TLS authority

Name resolution quyết định socket address để kết nối, nhưng không thay thế xác thực server. Client vẫn phải xác minh danh tính TLS theo authority/hostname phù hợp với chứng chỉ.

Ví dụ client kết nối tới target `dns:///inventory.internal:9090`. DNS có thể trả IP `10.30.1.21`, nhưng chứng chỉ server thường được phát hành cho tên service `inventory.internal`. Việc phân giải tên sang IP không có nghĩa client nên đổi danh tính TLS thành IP đó.

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///inventory.internal:9090")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();
~~~

Chỉ cấu hình authority override khi kiến trúc TLS/proxy yêu cầu và đã xác minh tên chứng chỉ tương ứng. Không tắt kiểm tra chứng chỉ để “sửa” lỗi do DNS trả nhiều IP. Nếu các endpoint có danh tính TLS khác nhau, cần một thiết kế authority và trust phù hợp với toàn bộ tập backend.

## 10. Kiểm thử resolver trả nhiều địa chỉ

Một test chỉ gọi một server không thể chứng minh resolver trả nhiều endpoint hay policy phân phối giữa chúng. Nên tách kiểm thử resolver, policy và môi trường DNS:

| Test | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Resolver trả một endpoint | Fake resolver trả A | Channel có một endpoint để chọn |
| Resolver trả nhiều endpoint | Fake resolver trả A, B, C | Policy nhận đủ ba group |
| `pick_first` với nhiều endpoint | Quan sát backend nhận RPC | Một endpoint được ưu tiên; địa chỉ khác có thể được thử khi cần |
| `round_robin` với nhiều endpoint ready | Gửi nhiều RPC unary mới và ghi nhận instance ID | RPC được phân phối qua các backend sẵn sàng |
| Một endpoint mất kết nối | Dừng backend B | RPC mới tiếp tục qua endpoint ready khác theo policy |
| Resolver thêm/xóa địa chỉ | Gửi kết quả resolution mới | Subchannel được cập nhật |
| DNS cache | Thay đổi record trong môi trường test | Xác định độ trễ thực tế trước khi client thấy endpoint mới |
| Không có endpoint ready | Kết hợp wait-for-ready và deadline | RPC chờ trong ngân sách hoặc kết thúc theo status |
| TLS trên nhiều IP | Mỗi backend trình bày chứng chỉ hợp lệ với authority | Kết nối bảo mật đến các endpoint hoạt động |

Đối với custom resolver, có thể tạo `NameResolverProvider` test và phát `ResolutionResult` chứa nhiều `EquivalentAddressGroup`. Đối với DNS thật, kiểm thử trong môi trường gần production vì DNS cache, network policy, headless/ClusterIP và TLS đều có thể làm kết quả khác in-process test.

Metrics nên quan sát:

- Số địa chỉ trong mỗi lần resolution và số lần resolver refresh.
- Số subchannel theo trạng thái `IDLE`, `CONNECTING`, `READY`, `TRANSIENT_FAILURE`.
- Số RPC được chọn theo backend.
- Tỷ lệ `UNAVAILABLE`, deadline và lỗi TLS theo endpoint.
- Thời gian từ khi endpoint xuất hiện đến khi subchannel ready.
- Phân bố latency và số stream dài theo backend.

Nếu ba địa chỉ được resolver trả về nhưng chỉ một backend nhận request, hãy kiểm tra policy thực tế, service config, provider có được nạp không và số subchannel `READY`. Đừng chỉ nhìn DNS answer rồi kết luận load balancing đang hoạt động.

## 11. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nghĩ DNS trả nhiều IP đồng nghĩa request được chia đều | RPC có thể vẫn dồn vào một endpoint theo policy | Cấu hình và xác minh load balancing policy |
| Dùng `round_robin` nhưng resolver chỉ trả một virtual IP | Không có nhiều endpoint client-side để phân phối | Xem xét headless/service discovery hoặc load balancing ở hạ tầng |
| Nhầm DNS round robin với gRPC `round_robin` | Kỳ vọng sai về thứ tự và phân bố | Phân biệt DNS answer với picker của gRPC |
| Tạo channel mới sau mỗi lần resolution | Tăng kết nối và handshake không cần thiết | Giữ channel dài hạn, để resolver cập nhật |
| Giả định endpoint vừa xuất hiện đã `READY` | RPC có thể vẫn chờ hoặc lỗi | Quan sát subchannel state và health/readiness |
| Bỏ qua DNS cache | Client tiếp tục dùng địa chỉ cũ | Kiểm tra TTL và cache trên đường phân giải |
| Dùng IP thay hostname làm TLS identity | Chứng chỉ có thể không khớp | Giữ authority đúng với danh tính server |
| Nghĩ server stream tự chuyển backend khi endpoint lỗi | RPC hiện tại có thể kết thúc giữa chừng | Reconnect bằng RPC mới và resume theo cursor nếu cần |

**Ghi nhớ:** Name resolution trả nhiều địa chỉ giúp gRPC channel biết tập backend có thể kết nối; nó chưa tự quyết định phân phối request. Resolver cung cấp `EquivalentAddressGroup`, còn load balancing policy như `pick_first` hoặc `round_robin` chọn subchannel dựa trên địa chỉ và readiness. Hãy xác minh DNS thực sự trả nhiều endpoint, hiểu khác biệt giữa ClusterIP và headless Service, để channel sống đủ lâu cho resolver cập nhật, và giữ TLS authority khớp với danh tính server.

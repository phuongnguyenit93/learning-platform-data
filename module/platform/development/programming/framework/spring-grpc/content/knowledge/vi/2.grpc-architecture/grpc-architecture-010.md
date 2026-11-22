# Channel lifecycle và tái sử dụng connection

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của **Channel** và **ManagedChannel** trong client gRPC.
- Mô tả cách Channel quản lý name resolution, load balancing, Subchannel và kết nối HTTP/2.
- Giải thích vì sao nên tái sử dụng Channel và stub thay vì tạo mới cho từng RPC.
- Quản lý Channel như tài nguyên Spring bean, bao gồm khởi tạo, graceful shutdown và đóng cưỡng bức.
- Phân biệt trạng thái kết nối với trạng thái sẵn sàng của service và health của nghiệp vụ.
- Nhận biết tác động của idle timeout, keepalive, reconnect/backoff và giới hạn HTTP/2.
- Chọn số Channel hợp lý, kiểm thử tái sử dụng và chẩn đoán rò rỉ connection.

## 1. Channel là ranh giới kết nối của client

Trong **SPRING_GRPC**, generated stub cung cấp các phương thức Java tương ứng với RPC method trong hợp đồng Protocol Buffers. Stub cần một **Channel** để chuyển lời gọi tới server. Với grpc-java, **ManagedChannel** là implementation được client quản lý vòng đời: nó điều phối name resolution, load balancing, Subchannel, transport và các RPC đang chạy.

~~~mermaid
flowchart LR
    A["Spring service"] --> B["Generated stub"]
    B --> C["ManagedChannel"]
    C --> D["NameResolver"]
    D --> E["LoadBalancer / picker"]
    E --> F["Subchannel"]
    F --> G["HTTP/2 transport"]
    G --> H["gRPC server"]
~~~

Một Channel là abstraction logic; nó không nhất thiết tương ứng với đúng một TCP connection. Tùy resolver, policy và topology, một ManagedChannel có thể quản lý nhiều Subchannel và nhiều connection tới các backend khác nhau. Với một endpoint đơn giản, nó thường duy trì một đường kết nối đang hoạt động.

Cần phân biệt:

| Thành phần | Vai trò |
| --- | --- |
| **Channel** | API trừu tượng để tạo RPC |
| **ManagedChannel** | Channel có lifecycle, resolver, load balancer và shutdown |
| **Subchannel** | Đường kết nối logic tới một nhóm địa chỉ backend |
| **Connection** | Kết nối transport thực tế, thường TCP/TLS |
| **HTTP/2 stream** | Một RPC cụ thể chạy trên connection |
| **Stub** | API Java được sinh để gọi method trên Channel |

**Channel tồn tại lâu hơn một RPC.** Một service Spring có thể gọi hàng nghìn RPC thông qua cùng một Channel; mỗi lời gọi tạo một HTTP/2 stream riêng. Điều này cho phép tái sử dụng connection và giảm chi phí thiết lập transport.

## 2. HTTP/2 multiplexing: vì sao một Channel phục vụ nhiều RPC?

gRPC thường dùng HTTP/2. Một HTTP/2 connection có thể mang nhiều stream đồng thời, mỗi stream đại diện một RPC. Các frame của nhiều stream được multiplex trên cùng connection:

~~~text
ManagedChannel
   |
   +-- HTTP/2 connection
         |-- stream 1: GetOrder
         |-- stream 3: UpdateOrder
         |-- stream 5: WatchOrder
         |-- stream 7: GetCustomer
         +-- stream 9: SearchOrders
~~~

Do đó, không cần mở một TCP/TLS connection mới cho từng method call. Channel tái sử dụng connection đã được thiết lập, trong khi runtime vẫn phân biệt metadata, deadline, request/response message và status của từng RPC.

Lợi ích chính:

- Giảm số lần TCP connect và TLS handshake.
- Giảm socket và file descriptor cần quản lý.
- Tận dụng HTTP/2 multiplexing cho các RPC đồng thời.
- Giữ resolver/load balancer hoạt động liên tục để cập nhật backend.
- Tập trung cấu hình TLS, credentials, interceptors và service config tại một Channel.

Multiplexing không có nghĩa số RPC đồng thời là vô hạn. HTTP/2 peer có thể giới hạn **MAX_CONCURRENT_STREAMS**; transport hoặc server có thể xếp hàng, mở thêm connection theo implementation, hoặc từ chối khi quá tải. Cần đo số RPC đang chạy và latency thay vì giả định một Channel chịu được mọi mức tải.

### 2.1. Channel không đồng nghĩa connection pool

Một số ứng dụng HTTP tạo connection pool lớn vì mỗi connection chỉ phục vụ một số request đồng thời. gRPC trên HTTP/2 có thể multiplex nhiều RPC trên một connection, nên cách tiếp cận thường khác:

- Dùng một ManagedChannel dùng chung cho cùng target và cùng cấu hình bảo mật.
- Để gRPC quản lý Subchannel và connection theo resolver/load-balancing policy.
- Chỉ tạo nhiều Channel khi có lý do kiến trúc cụ thể như cô lập tải, identity bảo mật, target hoặc cấu hình độc lập.

Tạo một Channel mới cho mỗi RPC không phải connection pooling. Nó thường làm tăng handshake, DNS resolution, thread/timer và connection churn, đồng thời làm giảm hiệu quả load balancing và reconnect.

## 3. Vòng đời của ManagedChannel

Một Channel thường đi qua các giai đoạn sau:

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Connecting: RPC đầu tiên / kết nối được kích hoạt
    Connecting --> Ready: transport sẵn sàng
    Connecting --> TransientFailure: kết nối lỗi
    TransientFailure --> Connecting: backoff và thử lại
    Ready --> TransientFailure: connection bị mất
    Ready --> Idle: không hoạt động theo policy
    Idle --> Connecting: có RPC mới
    Created --> Shutdown: shutdown()
    Connecting --> Shutdown: shutdown()
    Ready --> Shutdown: shutdown()
    TransientFailure --> Shutdown: shutdown()
    Idle --> Shutdown: shutdown()
    Shutdown --> Terminated: tài nguyên đã giải phóng
    Terminated --> [*]
~~~

Các trạng thái connectivity thường được biểu diễn bởi **ConnectivityState**:

| Trạng thái | Ý nghĩa thực tế |
| --- | --- |
| **IDLE** | Channel chưa có hoạt động cần kết nối hoặc đang ở trạng thái nghỉ |
| **CONNECTING** | Đang phân giải địa chỉ hoặc thiết lập transport |
| **READY** | Có đường kết nối sẵn sàng cho RPC |
| **TRANSIENT_FAILURE** | Kết nối tạm thời thất bại; runtime có thể thử lại theo backoff |
| **SHUTDOWN** | Channel đã nhận yêu cầu đóng và không nhận RPC mới |

Channel thường không phải mở socket ngay tại thời điểm tạo bean. Kết nối có thể được thiết lập khi RPC đầu tiên cần sử dụng hoặc khi runtime được yêu cầu kết nối. Không nên dựa vào thời điểm tạo ManagedChannel để kết luận backend đã sẵn sàng.

Khi connection bị mất, Channel có thể tự reconnect theo policy/backoff. Các RPC mới có thể chờ hoặc thất bại tùy trạng thái, deadline và cấu hình. Một RPC đang chạy trên connection đã mất thường kết thúc lỗi; runtime không thể tự chuyển một streaming RPC đang có message dở dang sang backend khác.

## 4. Tái sử dụng Channel và stub

### 4.1. Channel và generated stub có thể được dùng chung

Các Channel grpc-java được thiết kế để được sử dụng đồng thời. Generated stub là đối tượng cấu hình bất biến; các phương thức như **withDeadlineAfter(...)**, **withCallCredentials(...)** trả về stub mới với call options tương ứng.

Mẫu sử dụng:

~~~java
OrderServiceGrpc.OrderServiceBlockingStub baseStub =
        OrderServiceGrpc.newBlockingStub(managedChannel);

// Mỗi RPC có thể tạo biến thể riêng mà không sửa baseStub.
GetOrderResponse response = baseStub
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getOrder(request);
~~~

Giữ **baseStub** làm bean dùng chung; thiết lập deadline, credentials hoặc call option theo từng use case. Không cần tạo lại ManagedChannel khi muốn thay deadline cho một RPC.

Với async stub, cùng nguyên tắc áp dụng. Tuy nhiên, mỗi streaming call có observer và lifecycle riêng; không dùng lại observer đã kết thúc cho một RPC mới.

### 4.2. Anti-pattern: tạo Channel trong mỗi method

Không nên viết:

~~~java
public GetOrderResponse getOrder(GetOrderRequest request) {
    ManagedChannel channel = ManagedChannelBuilder
            .forAddress("orders.internal", 8443)
            .build();

    try {
        return OrderServiceGrpc.newBlockingStub(channel)
                .getOrder(request);
    } finally {
        channel.shutdownNow();
    }
}
~~~

Mỗi lần gọi phải tạo và đóng transport riêng. Hậu quả thường gặp:

- Tăng TCP/TLS handshake và độ trễ cold-start.
- Tăng số connection, thread, timer và áp lực lên server.
- DNS/service discovery bị gọi thường xuyên hơn.
- Load balancing khó duy trì trạng thái Subchannel ổn định.
- RPC đang xử lý bị cắt khi Channel đóng trong finally.

Hãy tạo Channel một lần cho một phạm vi cấu hình hợp lý và tái sử dụng nó qua nhiều lời gọi.

### 4.3. Khi nào cần nhiều Channel?

Một Channel dùng chung thường là mặc định tốt, nhưng nhiều Channel có thể hợp lý khi:

- Kết nối tới **các target khác nhau** hoặc môi trường khác nhau.
- Cần **identity/credential/TLS trust** độc lập giữa các nhóm backend.
- Cần cô lập một luồng tải đặc biệt để tránh ảnh hưởng RPC quan trọng khác.
- Có policy, resolver hoặc giới hạn tài nguyên riêng mà một Channel không thể biểu đạt rõ.
- Một giới hạn connection/stream đã được đo và chứng minh cần nhiều Channel có kiểm soát.

Không tạo Channel theo từng user, order ID hay request nếu không có yêu cầu cách ly thực sự. Nếu có nhiều Channel, phải giới hạn số lượng và quản lý shutdown tất cả.

## 5. Quản lý Channel trong Spring

Spring container phù hợp để sở hữu Channel vì vòng đời Channel thường bằng hoặc gần bằng vòng đời ứng dụng. Tạo Channel thành bean singleton, tạo stub từ bean đó và inject stub vào service nghiệp vụ.

Ví dụ grpc-java cơ bản:

~~~java
package dev.example.orders.client;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        return ManagedChannelBuilder
                .forAddress("orders.internal", 8443)
                .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderStub(
            ManagedChannel orderChannel) {
        return OrderServiceGrpc.newBlockingStub(orderChannel);
    }
}
~~~

Ví dụ dùng cấu hình transport mặc định của grpc-java; production cần kiểm tra TLS/trust, credentials và resolver theo môi trường. Nếu cần cấu hình TLS hoặc custom load-balancing policy, hãy cấu hình trên cùng Channel bean để mọi stub sử dụng chung chính sách đó.

Service chỉ giữ stub:

~~~java
@Service
public class OrderClient {
    private final OrderServiceGrpc.OrderServiceBlockingStub stub;

    public OrderClient(
            OrderServiceGrpc.OrderServiceBlockingStub stub) {
        this.stub = stub;
    }

    public GetOrderResponse find(String orderId) {
        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId(orderId)
                .build();

        return stub.withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                .getOrder(request);
    }
}
~~~

Đây là cách phân tách trách nhiệm: cấu hình Channel thuộc lớp hạ tầng Spring; service nghiệp vụ dùng stub và đặt call option phù hợp. Không để mỗi method tự biết host, port và cách tạo connection.

### 5.1. Đóng Channel khi Spring dừng

**destroyMethod = "shutdown"** yêu cầu Channel ngừng nhận RPC mới và bắt đầu shutdown. **shutdown()** là yêu cầu graceful; các RPC đang chạy có cơ hội hoàn tất. Ứng dụng có thể chờ một khoảng thời gian hữu hạn rồi mới buộc đóng:

~~~java
static void closeChannel(ManagedChannel channel) {
    channel.shutdown();

    try {
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
            channel.awaitTermination(2, TimeUnit.SECONDS);
        }
    } catch (InterruptedException ex) {
        channel.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

Đoạn code minh họa chính sách shutdown. Trong Spring, cần đặt logic này vào lifecycle bean phù hợp (ví dụ một wrapper **AutoCloseable** hoặc callback đóng ứng dụng) và tránh để cả bean Channel lẫn wrapper cùng đóng tài nguyên không rõ thứ tự. Nếu chỉ dùng **destroyMethod = "shutdown"**, Spring phát yêu cầu shutdown nhưng không tự bảo đảm đã chờ đủ thời gian cho mọi RPC.

**shutdownNow()** yêu cầu hủy các RPC còn lại và giải phóng tài nguyên sớm hơn. Dùng nó sau thời gian drain có giới hạn hoặc khi cần dừng khẩn cấp; không dùng sau mỗi lời gọi.

## 6. Idle timeout, keepalive và reconnect

### 6.1. Idle timeout

Channel có thể được đưa về **IDLE** khi không có RPC trong một khoảng thời gian theo policy. Khi có lời gọi mới, runtime có thể khởi động lại resolution/connection. Idle timeout giúp giảm tài nguyên khi client lâu không sử dụng service, nhưng lời gọi đầu tiên sau giai đoạn idle có thể có thêm độ trễ kết nối.

Chỉ cấu hình idle timeout khi có yêu cầu quản lý tài nguyên rõ ràng. Đặt quá ngắn có thể gây connection churn và cold-start liên tục; để mặc định thường phù hợp nếu không có lý do điều chỉnh.

### 6.2. Keepalive

HTTP/2 keepalive dùng PING để kiểm tra connection theo cấu hình client/server. Nó có thể phát hiện connection không còn đáp ứng, nhưng:

- Keepalive không phải health check nghiệp vụ.
- Keepalive không thay deadline của từng RPC.
- Server/proxy có thể giới hạn tần suất PING; cấu hình quá dày có thể bị từ chối hoặc làm tăng tải.
- Client và server cần phối hợp policy để tránh ping không cần thiết khi không có traffic.

Không bật keepalive cực ngắn như một cách chữa backend chậm. Hãy phân biệt connection chết với RPC xử lý chậm.

### 6.3. Reconnect và backoff

Khi connection thất bại, gRPC thường thử reconnect theo backoff để tránh dồn kết nối liên tục vào backend đang lỗi. Channel được tái sử dụng sẽ giữ được resolver, policy và trạng thái cần thiết để phục hồi.

Reconnect của Channel không có nghĩa **RPC đã gửi sẽ tự động chạy lại an toàn**. Một thao tác ghi có thể đã được server thực hiện trước khi connection mất. Retry phải dựa trên status, deadline, chính sách retry và tính idempotent của method.

## 7. Connectivity state không phải application health

**READY** cho biết transport có thể gửi RPC; nó không khẳng định service đang xử lý nghiệp vụ khỏe. Server có thể nhận kết nối HTTP/2 nhưng database, message broker hoặc dependency quan trọng đang hỏng.

Phân biệt:

| Tín hiệu | Điều nó nói lên |
| --- | --- |
| **Channel READY** | Có transport sẵn sàng tại thời điểm quan sát |
| **gRPC health SERVING** | Health service báo service đang phục vụ |
| **Kubernetes readiness** | Pod/endpoint được phép nhận traffic theo policy triển khai |
| **Business operation success** | Một thao tác nghiệp vụ cụ thể đã hoàn tất |

Có thể quan sát connectivity state bằng API Channel, nhưng không nên polling liên tục hoặc dùng nó thay cho kết quả RPC. Ví dụ, **getState(...)** và **notifyWhenStateChanged(...)** phù hợp cho logic giám sát/cập nhật trạng thái có chủ đích; không dùng trạng thái READY làm bằng chứng rằng mọi method đều thành công.

Với hệ thống cần health checking, hãy triển khai **grpc.health.v1.Health** và cấu hình client/policy tương ứng. Health check và readiness của hạ tầng cần được phối hợp để endpoint không nhận traffic khi chưa sẵn sàng.

## 8. Những lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Latency cao ở những RPC đầu tiên | Cold connection, DNS/TLS handshake hoặc Channel vừa rời IDLE | Tái sử dụng Channel; đo riêng thời gian kết nối và xử lý |
| Số socket tăng theo số request | Tạo ManagedChannel trong từng method | Dùng Channel bean có lifecycle ứng dụng |
| Đóng Channel làm RPC khác thất bại | Channel dùng chung bị shutdown trong code xử lý request | Chỉ đóng khi Spring/app dừng |
| Channel READY nhưng RPC trả UNAVAILABLE | Backend/handler hoặc proxy gặp lỗi sau khi connection sẵn sàng | Kiểm tra status, server logs và dependency |
| RPC streaming mất khi backend restart | Stream đang gắn với connection cũ, không tự migrate | Reconnect ở tầng ứng dụng, dùng cursor/sequence để resume |
| Shutdown ứng dụng làm mất kết quả đang xử lý | Dùng shutdownNow quá sớm | Graceful shutdown và drain trong thời gian hữu hạn |
| Keepalive bị server từ chối | Tần suất PING không phù hợp policy | Phối hợp cấu hình client/server/proxy |
| Connection liên tục đóng/mở | Idle timeout quá thấp hoặc Channel bị tạo/hủy thường xuyên | Điều chỉnh idle policy và kiểm tra lifecycle |
| Tạo nhiều Channel nhưng tải vẫn lệch | Mỗi Channel có resolver/LB state riêng; backend hoặc RPC cost không đồng đều | Quan sát phân phối theo backend, dùng policy phù hợp |
| Thread/resource tăng sau deploy | Channel cũ không được shutdown | Đóng mọi Channel khi context dừng, kiểm tra lifecycle bean |

## 9. Kiểm thử việc tái sử dụng và shutdown

Một số kiểm tra hữu ích trong ứng dụng:

1. Tạo Channel một lần, gọi nhiều unary RPC và xác nhận Channel không bị đóng giữa các call.
2. Gọi đồng thời nhiều RPC qua cùng stub/Channel; kiểm tra response không bị trộn.
3. Đo latency lần gọi đầu và các lần tiếp theo để tách chi phí kết nối khỏi chi phí xử lý.
4. Dừng backend, quan sát connectivity state, reconnect/backoff và status mà caller nhận.
5. Dừng Spring context khi có RPC đang chạy; xác minh shutdown cho phép call hoàn tất trong thời gian drain, sau đó đóng phần còn lại.
6. Kiểm thử streaming qua thời gian dài; khi connection mất, xác minh client reconnect bằng một RPC mới và resume theo cursor nếu nghiệp vụ hỗ trợ.
7. Kiểm tra số Channel/connection sau nhiều lần khởi tạo và dừng context để phát hiện rò rỉ.

**In-process transport** có thể kiểm tra service và lifecycle API ở mức process, nhưng không đo được TCP/TLS handshake, HTTP/2 keepalive, DNS hoặc proxy. Những đặc tính đó cần kiểm thử với transport thật và quan sát connection/metrics tương ứng.

## 10. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo một **ManagedChannel** bean dùng chung cho **OrderService** và inject generated blocking stub vào service Spring.
2. Gọi nhiều lần **GetOrder** qua cùng stub; quan sát Channel/connection và so sánh latency cold-call với các call tiếp theo.
3. Thử tạo Channel theo từng request trong một nhánh test; so sánh số connection, handshake và resource với cách tái sử dụng.
4. Thêm deadline riêng cho mỗi RPC bằng **withDeadlineAfter(...)** mà không tạo Channel mới.
5. Thử shutdown Channel khi có RPC đang chạy: so sánh **shutdown()**, **awaitTermination(...)** và **shutdownNow()**.
6. Mô phỏng backend restart; quan sát reconnect/backoff và xác minh RPC streaming cần resume bằng cursor/sequence ở tầng ứng dụng.
7. Bật TLS trong môi trường test và xác minh Channel tái sử dụng transport mà không bỏ qua hostname/certificate validation.

### Câu hỏi tự kiểm tra

**1. ManagedChannel có phải là một TCP connection duy nhất không?**  
Không. Nó là abstraction quản lý resolver, load balancer, Subchannel và transport; tùy topology có thể quản lý nhiều connection.

**2. Vì sao nên tái sử dụng Channel?**  
Để tận dụng HTTP/2 multiplexing, giảm TCP/TLS handshake, socket và chi phí discovery/reconnect.

**3. Có thể dùng chung generated stub giữa nhiều thread không?**  
Có, stub grpc-java là đối tượng cấu hình bất biến và được thiết kế để tái sử dụng. Mỗi call vẫn có deadline/observer/lifecycle riêng.

**4. shutdown() khác shutdownNow() thế nào?**  
shutdown() bắt đầu graceful shutdown và cho RPC đang chạy cơ hội hoàn tất; shutdownNow() yêu cầu hủy các call còn lại và đóng nhanh hơn.

**5. Channel READY có nghĩa service nghiệp vụ khỏe không?**  
Không. READY chỉ phản ánh transport; health service và kết quả nghiệp vụ là tín hiệu riêng.

**6. Reconnect có tự chạy lại một thao tác ghi không?**  
Không nên giả định như vậy. Retry phụ thuộc policy và tính idempotent; server có thể đã commit trước khi connection mất.

**7. Khi nào nên tạo nhiều Channel?**  
Khi cần target, credentials/TLS identity, policy hoặc cô lập tải độc lập; phải giới hạn và quản lý lifecycle từng Channel.

## Tổng kết

**ManagedChannel** là tài nguyên kết nối lâu dài của gRPC client. Nó quản lý resolver, load balancing, Subchannel và transport; HTTP/2 cho phép nhiều RPC multiplex trên các connection được tái sử dụng. Trong Spring, nên sở hữu Channel bằng bean dùng chung, tạo stub từ Channel và thiết lập call options theo từng RPC. Khi ứng dụng dừng, dùng graceful shutdown có thời gian drain rồi mới buộc đóng. **READY**, keepalive và reconnect phản ánh trạng thái transport, không thay thế health checking hoặc bảo đảm nghiệp vụ; vì vậy cần kiểm thử cả lifecycle, lỗi kết nối và khả năng resume streaming.


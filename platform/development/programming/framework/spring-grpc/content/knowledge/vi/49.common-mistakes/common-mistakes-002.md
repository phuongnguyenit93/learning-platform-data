# Tạo channel mới cho từng request

## 1. Vì sao tạo channel theo từng request là sai?

Trong **SPRING_GRPC**, client gọi dịch vụ từ xa thông qua gRPC channel và stub. Một lỗi thường gặp là tạo ManagedChannel ngay trong mỗi lần xử lý request, gọi RPC rồi bỏ channel mà không tái sử dụng hoặc quản lý vòng đời.

Một ManagedChannel không tương đương một lời gọi hàm đơn giản. Nó quản lý name resolution, load balancing, kết nối HTTP/2, TLS, reconnect, backoff và các tài nguyên nền. Khởi tạo channel liên tục khiến ứng dụng lặp lại công việc thiết lập kết nối, tạo nhiều socket/thread, tăng handshake và làm hệ thống khó kiểm soát tài nguyên.

Thiết kế thông thường là tạo channel theo endpoint và cấu hình bảo mật, giữ nó sống trong vòng đời ứng dụng hoặc một client component, rồi tái sử dụng cho nhiều RPC đồng thời. Stub có thể được tạo từ channel đó và dùng lại; khi cần deadline hoặc call credentials riêng, tạo stub biến thể cho từng call nhưng vẫn chia sẻ channel.

Bài tập trung vào:

- Phân biệt Channel, ManagedChannel và stub.
- Chi phí khi tạo channel mới cho từng request.
- Tái sử dụng channel trong Spring singleton bean.
- Dùng một channel cho nhiều RPC đồng thời.
- Chọn phạm vi channel theo endpoint và cấu hình TLS/identity.
- Quản lý shutdown, drain và reconnect.
- Kiểm thử để phát hiện channel leak và connection storm.

## 2. Channel là client transport được quản lý lâu dài

Trong gRPC Java:

- Channel là abstraction mà stub dùng để gửi RPC.
- ManagedChannel là implementation có lifecycle, quản lý kết nối và tài nguyên transport.
- Stub được sinh từ service trong Protobuf, ví dụ blocking stub hoặc async stub.
- Mỗi RPC là một call riêng chạy trên channel.

Channel không nhất thiết tương ứng một TCP socket cố định. Nó có thể quản lý một hoặc nhiều connection/subchannel tùy resolver, load balancer, endpoint và trạng thái mạng. Với HTTP/2, nhiều RPC có thể multiplex trên cùng connection; channel cũng quản lý reconnect khi connection mất.

Do đó, tái sử dụng channel không có nghĩa mọi RPC dùng chung một request hay một luồng xử lý. Mỗi RPC vẫn có metadata, deadline, request và response riêng.

## 3. Điều gì xảy ra khi tạo channel cho từng request?

Ví dụ anti-pattern:

```java
public OrderReply getOrder(GetOrderRequest request) {
    ManagedChannel channel =
        ManagedChannelBuilder
            .forAddress("orders.internal", 8443)
            .useTransportSecurity()
            .build();

    OrderGrpc.OrderBlockingStub stub =
        OrderGrpc.newBlockingStub(channel);

    return stub.getOrder(request);
}
```

Mỗi lần gọi method tạo một channel mới. Nếu không shutdown, channel và tài nguyên nền có thể tiếp tục tồn tại sau khi method trả về. Nếu shutdown ngay sau mỗi call, ứng dụng lại phải thiết lập transport cho request tiếp theo.

Dưới tải cao, cách làm này có thể gây:

- Tăng số socket và connection tới server.
- TLS handshake và name resolution lặp lại.
- Tăng CPU, memory, thread và context switching.
- Connection churn, reconnect và backoff liên tục.
- Tăng latency p95/p99 do request phải chờ thiết lập kết nối.
- Tạo tải đột biến lên server, proxy, DNS hoặc load balancer.
- Khó drain và quan sát trạng thái client connection.

Nếu quên shutdown channel, đó còn là resource leak. Nếu shutdown ngay sau mỗi RPC, connection reuse và HTTP/2 multiplexing mất phần lớn lợi ích.

## 4. Tạo channel một lần và tái sử dụng

Với Spring, có thể đăng ký ManagedChannel như một bean singleton. Spring quản lý bean trong application context và gọi shutdown khi context đóng:

```java
@Configuration
public class GrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
            .forAddress("orders.internal", 8443)
            .useTransportSecurity()
            .build();
    }

    @Bean
    OrderGrpc.OrderBlockingStub orderBlockingStub(
            ManagedChannel ordersChannel) {
        return OrderGrpc.newBlockingStub(ordersChannel);
    }
}
```

Service inject stub qua constructor:

```java
@Service
@RequiredArgsConstructor
public class OrderQueryService {
    private final OrderGrpc.OrderBlockingStub orderBlockingStub;

    public OrderReply getOrder(String orderId) {
        GetOrderRequest request =
            GetOrderRequest.newBuilder()
                .setOrderId(orderId)
                .build();

        return orderBlockingStub
            .withDeadlineAfter(400, TimeUnit.MILLISECONDS)
            .getOrder(request);
    }
}
```

Mỗi request dùng cùng stub/channel nền nhưng có deadline riêng. Phương thức withDeadlineAfter trả một stub mới mang call option; nó không tạo channel mới.

Ví dụ dùng Spring bean là cấu hình minh họa với gRPC Java. Nếu dự án dùng Spring gRPC starter có channel factory/auto-configuration riêng, hãy đăng ký named channel qua cơ chế của starter và để Spring quản lý lifecycle; tránh tự tạo thêm channel song song cho cùng target.

## 5. Channel và stub có thể dùng đồng thời

ManagedChannel được thiết kế để nhiều thread gọi RPC đồng thời. Stub gRPC sinh tự động là immutable: các phương thức cấu hình như withDeadlineAfter hoặc withCallCredentials tạo stub mới thay vì sửa stub gốc.

Có thể giữ một base stub trong singleton service:

```java
@Service
@RequiredArgsConstructor
public class InventoryClient {
    private final InventoryGrpc.InventoryBlockingStub baseStub;

    public InventoryReply check(
            InventoryRequest request,
            long remainingMillis) {
        return baseStub
            .withDeadlineAfter(
                remainingMillis,
                TimeUnit.MILLISECONDS
            )
            .checkInventory(request);
    }
}
```

Không lưu request-specific mutable data trong field của singleton client. Deadline, metadata, tracing context và credentials theo call phải được gắn vào call/stub tương ứng, không ghi đè cấu hình dùng chung.

Với async stub, nhiều call có thể đang hoạt động đồng thời trên cùng channel. Mỗi call có observer riêng và cần tuân thủ lifecycle/cancellation của chính nó.

## 6. Chọn phạm vi channel theo endpoint và security identity

Tái sử dụng channel không có nghĩa chỉ được có đúng một channel trong toàn ứng dụng. Phạm vi hợp lý thường là một channel cho một target và một bộ cấu hình transport/security tương thích.

Có thể cần channel riêng khi:

- Gọi các target/service khác nhau.
- Dùng authority, resolver hoặc load balancing policy khác nhau.
- Dùng client certificate/TLS identity khác nhau.
- Cần cô lập workload theo yêu cầu vận hành đã đo được.

Không tạo channel riêng cho mỗi user hoặc mỗi request chỉ vì metadata khác nhau. Với bearer token hoặc call credentials thay đổi theo caller, thường nên gắn CallCredentials/metadata trên từng RPC trong khi dùng chung channel. Nếu identity là TLS client certificate ở tầng transport, channel thường gắn với certificate đó và cần tách theo identity/cấu hình.

Nếu có nhiều tenant, hãy phân biệt credentials theo call với transport identity. Không đưa token nhạy cảm vào tên channel, log hoặc metric label.

## 7. Tái sử dụng channel không đồng nghĩa bỏ qua deadline

Channel sống lâu không có nghĩa RPC được phép chờ vô hạn. Deadline thuộc từng call, không phải lifetime của channel.

```java
OrderReply reply = orderBlockingStub
    .withDeadlineAfter(350, TimeUnit.MILLISECONDS)
    .getOrder(request);
```

Mỗi RPC cần deadline theo SLO và remaining budget. Khi gọi downstream từ một RPC khác, truyền deadline cha hoặc phần ngân sách còn lại. Không cấp lại toàn bộ timeout cho từng hop.

Cũng không cần kiểm tra channel connectivity trước mọi request rồi mới gọi. Trạng thái có thể đổi ngay sau khi kiểm tra; hãy để gRPC xử lý reconnect và nhận diện lỗi qua status. Dùng health checking/monitoring cho mục tiêu quan sát, không biến nó thành một round trip bắt buộc trước mỗi RPC.

## 8. Channel quản lý reconnect và backoff

ManagedChannel duy trì kết nối và có thể kết nối lại khi network hoặc server tạm thời mất. Name resolver có thể cập nhật địa chỉ; load balancer chọn subchannel phù hợp; transport thực hiện reconnect theo policy.

Không tạo channel mới mỗi khi một RPC nhận UNAVAILABLE. Điều đó có thể tạo connection storm đúng lúc hệ thống đang phục hồi.

Thay vào đó:

- Giữ channel và để gRPC quản lý reconnect.
- Đặt deadline hữu hạn cho từng call.
- Retry command chỉ khi status và contract cho phép.
- Dùng idempotency key cho side effect có thể đã commit.
- Có backoff/jitter và giới hạn attempt.
- Theo dõi connectivity, call failure và reconnect behavior.

Channel không tự đảm bảo server khỏe mạnh hoặc RPC thành công. Nó chỉ quản lý client-side transport và lựa chọn endpoint theo cấu hình.

## 9. Shutdown và graceful drain

Channel cần được đóng khi application context dừng. ManagedChannel.shutdown() ngừng nhận call mới và cho các call đang chạy cơ hội hoàn tất; shutdownNow() yêu cầu hủy call đang hoạt động mạnh hơn.

Một lifecycle hook có thể chờ graceful termination rồi mới force shutdown:

```java
public final class ManagedChannelOwner
        implements DisposableBean {

    private final ManagedChannel channel;

    public ManagedChannelOwner(ManagedChannel channel) {
        this.channel = channel;
    }

    @Override
    public void destroy() throws Exception {
        channel.shutdown();

        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
            channel.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Ví dụ trên minh họa quyền sở hữu channel. Trong ứng dụng Spring, chỉ chọn một nơi chịu trách nhiệm shutdown để tránh lifecycle bị phân tán. Nếu dùng bean destroyMethod, có thể cấu hình owner tương ứng để chờ termination trước khi process kết thúc.

Thứ tự shutdown của ứng dụng cũng quan trọng: ngừng nhận RPC mới, drain server requests, hoàn tất các tác vụ đang chạy, sau đó đóng client channels. Không shutdown channel khi service vẫn đang nhận request cần gọi downstream.

Nếu thread bị interrupt trong lúc chờ, gọi shutdownNow khi cần, khôi phục interrupt flag và kết thúc cleanup có kiểm soát.

## 10. Khi nào cần nhiều channel hoặc channel pool?

Một channel thường là điểm bắt đầu đúng vì HTTP/2 multiplex được nhiều RPC. Tuy nhiên, một HTTP/2 connection có giới hạn concurrent streams do server/proxy thương lượng; nếu vượt giới hạn, call có thể phải chờ.

Chỉ cân nhắc nhiều channel khi đã đo thấy một giới hạn transport cụ thể và xác nhận tăng channel cải thiện throughput/latency mà không làm quá tải server. Một số trường hợp:

- Một target có workload lớn và giới hạn concurrent streams trở thành bottleneck.
- Cần cô lập traffic latency-sensitive với bulk workload.
- Cần dùng transport identity hoặc network path khác nhau.

Nếu dùng channel pool:

- Đặt số channel cố định và có giới hạn.
- Phân phối call có chủ đích; tránh tạo channel ngẫu nhiên theo request.
- Theo dõi tổng connection trên tất cả replica.
- Quản lý shutdown/drain cho mọi channel.
- Kiểm thử server connection limit, load balancer và reconnect.
- Chứng minh bằng load test rằng pool tốt hơn một channel.

Không dùng channel pool để che giấu query chậm, server saturation hoặc connection leak. Tăng channel có thể làm số connection tăng và gây áp lực lên downstream.

## 11. Cấu hình TLS và plaintext

Channel nên được tạo với transport security phù hợp môi trường:

```java
ManagedChannel secureChannel =
    ManagedChannelBuilder
        .forAddress("orders.internal", 8443)
        .useTransportSecurity()
        .build();
```

Trong môi trường local test có thể dùng plaintext nếu server cũng cấu hình plaintext:

```java
ManagedChannel localChannel =
    ManagedChannelBuilder
        .forAddress("localhost", 9090)
        .usePlaintext()
        .build();
```

Không dùng plaintext cho traffic production qua mạng không tin cậy. Nếu cần custom trust roots, client certificate hoặc authority override, cấu hình transport credentials theo policy của môi trường và giữ channel tái sử dụng cho bộ cấu hình đó.

Khi certificate hoặc trust configuration thay đổi, không cần tạo channel mới cho mỗi call. Tạo channel mới có kiểm soát, chuyển traffic sang channel mới, drain channel cũ rồi shutdown. Quá trình rotation phải tránh khoảng thời gian không có channel khả dụng.

## 12. Quan sát channel và phát hiện tạo channel quá nhiều

Theo dõi các tín hiệu:

- Số ManagedChannel được tạo theo target.
- Số connection/subchannel và socket đang mở.
- TLS handshake/reconnect rate.
- RPC latency p50/p95/p99 và status distribution.
- Call queueing hoặc thời gian chờ stream capacity nếu có metric tương ứng.
- Số channel đang shutdown/termination pending.
- Thread count và memory liên quan tới transport.
- Connection churn sau deploy hoặc autoscaling.

Không gắn user ID hoặc request ID làm metric label cho channel; cardinality sẽ tăng không giới hạn. Dùng label có giới hạn như target, client name, transport profile và outcome.

Nếu thấy số connection tăng gần tuyến tính theo số request, kiểm tra nơi khởi tạo ManagedChannel. Channel thường nên được tạo ở cấu hình/client lifecycle, không phải trong method xử lý RPC.

## 13. Kiểm thử channel lifecycle và reuse

Có thể kiểm thử ở nhiều cấp:

| Test | Điều cần xác nhận |
| --- | --- |
| Nhiều RPC qua một client bean | Cùng channel phục vụ nhiều call |
| Concurrent calls | Nhiều thread dùng channel an toàn |
| Deadline khác nhau | Mỗi call có deadline riêng, không ảnh hưởng call khác |
| Server restart | Channel reconnect theo policy; call thất bại được xử lý rõ |
| Application context đóng | Channel shutdown và kết thúc trong thời hạn |
| TLS certificate rotation | Channel mới được đưa vào dùng, channel cũ drain |
| Load test | Channel reuse giảm connection churn và giữ latency ổn định |
| Leak test | Số channel/socket/thread không tăng theo số request |

Trong integration test, khởi tạo channel/client một lần trong fixture và đóng sau test. Nếu mỗi test method tạo channel riêng, đảm bảo cleanup trong finally hoặc lifecycle hook. Không dùng sleep cố định để chờ channel ready; dùng health check, latch hoặc retry có giới hạn với deadline.

## 14. Checklist review

- ManagedChannel được tạo ở client/configuration lifecycle, không tạo trong từng RPC method.
- Channel được tái sử dụng cho nhiều call đồng thời.
- Stub được giữ như immutable base stub; call options được tạo riêng cho từng request.
- Deadline và metadata được gắn theo call.
- Channel scope gắn với target và transport/security configuration.
- Credentials theo request được gắn bằng call credentials khi phù hợp.
- Không tạo channel mới chỉ vì một call nhận UNAVAILABLE.
- Không kiểm tra connectivity bằng round trip trước mọi RPC.
- Hikari/database work và network call không bị giữ chung trong transaction dài.
- Channel có một owner chịu trách nhiệm shutdown.
- Shutdown ngừng call mới, drain call đang chạy và force shutdown sau grace period.
- Channel pool chỉ dùng sau khi có số liệu chứng minh cần thiết.
- TLS/plaintext được cấu hình đúng môi trường.
- Metrics theo dõi channel count, connection churn, reconnect và RPC latency.
- Integration/load tests xác nhận reuse, concurrency, reconnect và cleanup.

Trong **SPRING_GRPC**, ManagedChannel là tài nguyên transport lâu dài để nhiều RPC dùng chung. Hãy tạo channel theo target và cấu hình bảo mật ở application lifecycle, inject vào service, đặt deadline/metadata riêng trên từng call và đóng channel khi ứng dụng dừng. Tạo channel mới cho từng request làm mất connection reuse, tăng handshake và gây connection churn; chỉ dùng nhiều channel khi metrics và load test chứng minh một giới hạn transport cụ thể.

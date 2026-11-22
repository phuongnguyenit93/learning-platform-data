# Kiểm thử server instance bị lỗi

Một gRPC client thường giữ channel lâu dài và channel có thể kết nối tới nhiều server instance. Khi một instance dừng, mất mạng hoặc không còn đủ sức khỏe để phục vụ, client cần ngừng gửi RPC mới tới instance đó và tiếp tục dùng các instance còn hoạt động. Kiểm thử tình huống này giúp xác minh load balancer, resolver, health checking và retry phối hợp đúng.

**Kiểm thử server instance bị lỗi** tập trung vào cách tạo lỗi có kiểm soát, quan sát client phát hiện endpoint không còn khả dụng, xác minh RPC mới được chuyển sang instance khỏe và hiểu điều gì xảy ra với RPC đang chạy. Bài thuộc chương **Load balancing** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy.

## 1. Phân biệt lỗi instance với lỗi request

Không phải mọi RPC thất bại đều có nghĩa server instance bị lỗi. Một instance có thể đang hoạt động bình thường nhưng từ chối một request do dữ liệu không hợp lệ, quyền truy cập không đủ hoặc trạng thái nghiệp vụ.

| Tình huống | Ví dụ | Ý nghĩa với load balancing |
| --- | --- | --- |
| Instance/process dừng | Process bị kill, container restart. | Kết nối tới instance mất; subchannel có thể chuyển sang TRANSIENT_FAILURE. |
| Network path lỗi | Connection reset, route bị mất, firewall chặn. | Client không giao tiếp được với endpoint dù process có thể vẫn chạy. |
| Instance không healthy | Health service trả NOT_SERVING hoặc readiness probe thất bại. | Endpoint có thể bị loại khỏi lựa chọn RPC mới nếu health checking được bật và hỗ trợ. |
| Instance quá tải | Queue tăng, latency cao, hết connection/database pool. | Cần health/outlier/capacity policy; TCP connection vẫn có thể đang mở. |
| Lỗi nghiệp vụ | INVALID_ARGUMENT, PERMISSION_DENIED, NOT_FOUND. | Không nên loại instance chỉ vì một lỗi request như vậy. |

Khi test, phải xác định loại lỗi cần mô phỏng. Dừng server, ngắt kết nối và đánh dấu health NOT_SERVING kiểm tra các lớp khác nhau. Một bài test chỉ gọi shutdown trên server không chứng minh health checking hoặc outlier detection hoạt động.

## 2. Load balancer phát hiện instance lỗi như thế nào?

Với client-side load balancing, resolver cung cấp danh sách địa chỉ. gRPC tạo subchannel cho endpoint và theo dõi trạng thái kết nối. Policy chọn subchannel đủ điều kiện cho RPC:

~~~text
Name Resolver
     |
     v
Endpoint list: A, B, C
     |
     v
Load Balancing Policy
     |
     +---- Subchannel A: READY
     +---- Subchannel B: READY
     +---- Subchannel C: TRANSIENT_FAILURE
     |
     v
Pick endpoint for each new RPC
~~~

Các trạng thái connectivity thường gặp:

- IDLE: subchannel chưa có kết nối hoạt động.
- CONNECTING: đang thiết lập kết nối.
- READY: kết nối có thể nhận RPC.
- TRANSIENT_FAILURE: kết nối tạm thời thất bại; gRPC có thể tiếp tục reconnect theo backoff.
- SHUTDOWN: subchannel đã đóng và không được dùng lại.

Với round_robin, các subchannel READY được đưa vào tập chọn. Khi một endpoint mất kết nối và chuyển khỏi trạng thái READY, RPC mới sẽ được chọn từ các endpoint còn đủ điều kiện. Với pick_first, client thường dùng một endpoint được chọn; hành vi chuyển sang endpoint khác phụ thuộc trạng thái kết nối và resolver/policy.

Phát hiện lỗi không nhất thiết tức thời. Client có thể chỉ biết instance đã chết khi một RPC ghi/đọc thất bại hoặc transport phát hiện connection mất. Health checking, keepalive, outlier detection và resolver update có thể rút ngắn hoặc thay đổi thời điểm phát hiện, nhưng mỗi cơ chế có mục đích và điều kiện cấu hình riêng.

## 3. RPC đang chạy và RPC mới có hành vi khác nhau

Load balancer chủ yếu chọn endpoint cho RPC mới. Khi một unary RPC đã được gửi tới instance A, nó không tự chuyển phần request đang chạy sang instance B nếu A chết. RPC đang chạy thường kết thúc với lỗi transport, ví dụ UNAVAILABLE, hoặc một status khác tùy điểm lỗi và phản hồi cuối cùng.

Sau khi client phát hiện A không còn khả dụng:

1. Subchannel A rời trạng thái READY.
2. Policy không chọn A cho RPC mới khi A chưa READY.
3. RPC mới có thể được gửi tới B hoặc C.
4. Nếu A khôi phục, subchannel reconnect và có thể trở lại tập READY.

Với streaming RPC, toàn bộ stream gắn với instance đã nhận stream. Nếu instance chết, stream kết thúc lỗi; load balancer không chuyển các message còn lại sang server khác. Ứng dụng phải mở stream mới và dùng cursor, sequence number hoặc resume token nếu cần tiếp tục từ vị trí đã xử lý.

## 4. Chuẩn bị nhiều server instance cho integration test

Để kiểm tra client-side load balancing qua TCP, tạo ít nhất hai server instance độc lập và để resolver trả về địa chỉ của cả hai. Mỗi instance nên trả về một định danh để test biết request đã tới server nào:

~~~java
final class InventoryService extends InventoryGrpc.InventoryImplBase {
    private final String instanceId;

    InventoryService(String instanceId) {
        this.instanceId = instanceId;
    }

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> responseObserver) {
        responseObserver.onNext(StockReply.newBuilder()
                .setInstanceId(instanceId)
                .setAvailableUnits(10)
                .build());
        responseObserver.onCompleted();
    }
}
~~~

Khởi chạy các server trên port động:

~~~java
Server serverA = NettyServerBuilder.forPort(0)
        .addService(new InventoryService("instance-a"))
        .build()
        .start();

Server serverB = NettyServerBuilder.forPort(0)
        .addService(new InventoryService("instance-b"))
        .build()
        .start();
~~~

Resolver test cần trả hai địa chỉ 127.0.0.1:serverA.getPort() và 127.0.0.1:serverB.getPort() dưới cùng một target. Channel dùng policy round_robin. Có thể triển khai resolver test bằng NameResolver.Factory và NameResolver.Listener2, phát ResolutionResult chứa các EquivalentAddressGroup; hoặc dùng discovery/test resolver mà dự án đã có. Không dùng một channel riêng cho mỗi backend, vì như vậy test sẽ bỏ qua hành vi chọn subchannel của load balancer.

Ví dụ cấu hình policy cho channel:

~~~java
Map<String, ?> serviceConfig = Map.of(
        "loadBalancingConfig",
        List.of(Map.of("round_robin", Map.of()))
);

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("test:///inventory")
        .nameResolverFactory(testResolverFactory)
        .defaultServiceConfig(serviceConfig)
        .usePlaintext()
        .build();
~~~

testResolverFactory là resolver fixture do test cung cấp. Target scheme phải khớp với scheme mà factory hỗ trợ. Nếu runtime không đăng ký policy round_robin hoặc resolver không phát endpoint đúng cách, channel có thể không vào READY; hãy kiểm tra lỗi resolver/policy thay vì chờ RPC vô hạn.

## 5. Xác minh phân phối trước khi tạo lỗi

Trước khi dừng một instance, xác minh test fixture thực sự đưa traffic tới cả hai server. Gửi một số unary RPC và thu thập instanceId:

~~~java
Set<String> observedInstances = new HashSet<>();

for (int i = 0; i < 20; i++) {
    StockReply reply = blockingStub
            .withDeadlineAfter(2, TimeUnit.SECONDS)
            .getStock(request);
    observedInstances.add(reply.getInstanceId());
}

assertTrue(observedInstances.contains("instance-a"));
assertTrue(observedInstances.contains("instance-b"));
~~~

Đây là kiểm tra fixture và policy, không phải khẳng định round_robin sẽ tạo một chuỗi luân phiên tuyệt đối. RPC có thể phân phối theo trạng thái READY và timing kết nối; số mẫu nhỏ có thể lệch. Nếu một instance không xuất hiện, kiểm tra resolver result, subchannel connectivity, service config và server listener trước khi bắt đầu fault test.

## 6. Mô phỏng instance dừng và xác minh failover

Sau khi xác nhận cả hai instance đã nhận RPC, dừng A rồi tiếp tục gửi RPC mới:

~~~java
serverA.shutdownNow();
assertTrue(serverA.awaitTermination(2, TimeUnit.SECONDS));

// Trong thời gian client phát hiện A lỗi, một số attempt có thể nhận UNAVAILABLE.
long failoverEnd = System.nanoTime() + TimeUnit.SECONDS.toNanos(8);
boolean reachedB = false;
while (System.nanoTime() < failoverEnd && !reachedB) {
    try {
        StockReply reply = blockingStub
                .withDeadlineAfter(1, TimeUnit.SECONDS)
                .getStock(request);
        reachedB = "instance-b".equals(reply.getInstanceId());
    } catch (StatusRuntimeException failure) {
        if (Status.fromThrowable(failure).getCode()
                != Status.Code.UNAVAILABLE) {
            throw failure;
        }
    }
}
assertTrue(reachedB, "Client không failover sang instance-b trong thời hạn test");

// Sau khi B đã phục vụ được, các RPC mới phải tiếp tục tới B.
for (int i = 0; i < 10; i++) {
    StockReply reply = blockingStub
            .withDeadlineAfter(2, TimeUnit.SECONDS)
            .getStock(request);
    assertEquals("instance-b", reply.getInstanceId());
}
~~~

Test thực tế cần cho client một khoảng thời gian hữu hạn để phát hiện A không còn kết nối. Ví dụ trên retry phép kiểm tra có giới hạn, chỉ tiếp tục khi attempt tạm thời nhận UNAVAILABLE, rồi xác minh các RPC tiếp theo đều tới B. Có thể thay vòng lặp bằng một tín hiệu connectivity/health do fixture quan sát được. Không dùng một sleep cố định rồi giả định subchannel đã chuyển trạng thái. Mỗi lần chờ phải có timeout để test không treo.

Server.shutdownNow() đóng server và các call đang chạy; nó mô phỏng instance dừng từ phía server nhưng không hoàn toàn tương đương process bị kill hoặc network partition. Để kiểm tra connection reset, process crash hoặc proxy mất route, cần test riêng qua TCP với process/container hoặc network fault fixture.

## 7. Phân biệt graceful shutdown và abrupt failure

Hai kiểu dừng instance tạo ra hành vi khác nhau:

| Kiểu dừng | Hành vi | Điều cần kiểm thử |
| --- | --- | --- |
| Graceful shutdown | Server ngừng nhận call mới và có thể cho call đang chạy hoàn tất trong thời gian drain. | Client ngừng chọn instance cho RPC mới; RPC đang chạy có cơ hội hoàn tất. |
| Immediate shutdown | Server đóng call đang chạy và connection. | RPC đang chạy nhận lỗi; RPC mới chuyển sang endpoint khỏe sau khi lỗi được phát hiện. |
| Process crash | Không có giai đoạn drain; socket có thể đóng đột ngột. | Client phát hiện lỗi transport và reconnect/failover. |
| Network partition | Process có thể vẫn chạy nhưng client không tới được. | Deadline/keepalive/health policy giới hạn thời gian chờ và phát hiện endpoint không phục vụ. |

Trong production, graceful drain thường được dùng cho rollout; abrupt failure dùng để kiểm tra khả năng chịu sự cố. Đừng dùng graceful shutdown để kết luận hệ thống đã xử lý đúng process crash.

## 8. Kiểm thử health checking

gRPC Health Checking Protocol định nghĩa service chuẩn grpc.health.v1.Health. Server có thể báo trạng thái SERVING hoặc NOT_SERVING cho service. Khi client bật health checking và load-balancing policy hỗ trợ, client có thể tránh gửi RPC tới endpoint không báo SERVING.

Health checking cần được kiểm tra riêng:

1. Khởi động hai instance và xác minh cả hai báo SERVING.
2. Đổi health của A sang NOT_SERVING trong khi process A vẫn chạy.
3. Chờ client health watcher nhận trạng thái và loại A khỏi tập nhận RPC mới.
4. Xác minh request mới tới B; khôi phục A về SERVING và quan sát A được đưa lại vào tập đủ điều kiện.

Health checking không thay thế kiểm tra connection. Một endpoint có thể báo SERVING nhưng mất network path; ngược lại, process có thể kết nối được nhưng ứng dụng không đủ khả năng phục vụ. Cần chọn health check ở mức phản ánh đúng khả năng xử lý request và cấu hình đúng service name.

Không mặc định mọi gRPC Java load-balancing policy đều bật health checking. Khả năng hỗ trợ và cấu hình phụ thuộc phiên bản grpc-java, resolver, policy và service config đang dùng. Test phải xác nhận tính năng thực sự được bật trong runtime.

## 9. Kiểm thử retry khi một instance lỗi

Failover của load balancer và retry của RPC là hai cơ chế khác nhau:

- Load balancer chọn một endpoint đủ điều kiện cho RPC mới.
- Retry policy quyết định có tạo attempt mới khi một attempt thất bại hay không.

Nếu attempt đầu tới A và A chết giữa chừng, client có thể nhận UNAVAILABLE. Chỉ khi method có retry policy phù hợp và status nằm trong retryableStatusCodes, gRPC mới có thể thử lại theo policy. Ví dụ service config cho một unary method đọc dữ liệu:

~~~java
Map<String, ?> methodConfig = Map.of(
        "name", List.of(Map.of(
                "service", "inventory.Inventory",
                "method", "GetStock")),
        "retryPolicy", Map.of(
                "maxAttempts", 3.0,
                "initialBackoff", "0.1s",
                "maxBackoff", "1s",
                "backoffMultiplier", 2.0,
                "retryableStatusCodes", List.of("UNAVAILABLE"))
);

Map<String, ?> serviceConfig = Map.of(
        "methodConfig", List.of(methodConfig),
        "loadBalancingConfig", List.of(
                Map.of("round_robin", Map.of()))
);
~~~

Đây là cấu hình minh họa cho một method; cần xác minh service/method name đúng với package và service trong proto. maxAttempts bao gồm cả attempt đầu. Retry có backoff và bị giới hạn bởi deadline của RPC. Không bật retry cho mọi method một cách máy móc.

Một số giới hạn quan trọng:

- Retry không bảo đảm attempt đang chạy được chuyển nguyên trạng sang server khác.
- gRPC retry có thể giữ và phát lại request theo retry machinery, nhưng khi RPC đã commit hoặc đã vượt retry commitment point thì không còn được retry theo cách thông thường.
- Với RPC ghi, server có thể đã thực hiện side effect trước khi connection lỗi; cần idempotency key hoặc deduplication.
- Deadline tổng vẫn áp dụng cho tất cả attempt và backoff; không cấp lại timeout đầy đủ cho mỗi lần retry.

Test nên có hai phần: một ca không cấu hình retry để quan sát lỗi của attempt đang chạy, và một ca có retry policy để xác minh một request đọc idempotent có thể hoàn tất qua instance còn khỏe. Không dùng một RPC ghi không idempotent để chứng minh retry thành công.

## 10. Deadline và thời gian phát hiện lỗi

Khi một instance chết, client có thể cần thời gian để phát hiện connection lỗi, cập nhật trạng thái subchannel và chọn endpoint khác. Deadline phải đủ cho:

- Thời gian kết nối/resolve ban đầu nếu channel chưa READY.
- Thời gian phát hiện endpoint lỗi.
- Backoff/reconnect hoặc retry theo policy.
- Thời gian xử lý tại instance thay thế.

Nếu deadline quá ngắn, request có thể hết hạn trước khi failover hoàn tất. Nếu deadline quá dài, caller phải chờ lâu khi tất cả endpoint đều lỗi. Đặt deadline theo SLO và đo thời gian failover thực tế trong môi trường gần production.

Keepalive giúp phát hiện một số kết nối không phản hồi, nhưng cấu hình quá thường xuyên có thể tạo tải và bị proxy/server giới hạn. Health checking đánh giá trạng thái service; connection failure phát hiện khả năng giao tiếp; outlier detection đánh giá hành vi bất thường. Không xem chúng là một cơ chế duy nhất.

## 11. Streaming RPC khi server instance bị lỗi

Một streaming RPC được gắn với server instance đã nhận stream. Khi instance chết:

- Client nhận terminal error hoặc deadline expiry.
- Stream không được load balancer chuyển sang instance khác ở giữa chừng.
- Client phải tạo stream mới nếu muốn tiếp tục.
- Ứng dụng cần sequence number, cursor hoặc resume token để yêu cầu dữ liệu chưa xử lý.

Với server-streaming, có thể xác nhận message cuối cùng đã được client xử lý trước khi reconnect. Với bidirectional streaming, cần định nghĩa cách khôi phục cả trạng thái gửi và nhận. Nếu không có resume protocol, mở stream mới có thể làm mất hoặc lặp message.

## 12. Kiểm thử network failure và process crash

In-process transport hữu ích để kiểm tra logic observer và service, nhưng không mô phỏng đầy đủ TCP reset, process kill, proxy hoặc network partition. Một bộ integration test chịu lỗi nên có:

1. Hai server instance thực sự lắng nghe trên TCP port động.
2. Một resolver trả địa chỉ cả hai instance cho cùng channel.
3. Client channel duy nhất dùng round_robin.
4. Endpoint A được xác nhận đã nhận request trước khi fault injection.
5. Dừng process A hoặc ngắt route tới A trong khi B tiếp tục phục vụ.
6. Xác minh RPC mới tới B sau khi client phát hiện A lỗi.
7. Xác minh RPC đang chạy trên A có kết quả đúng theo semantics lỗi/deadline.
8. Khôi phục A và xác minh resolver/health policy đưa A trở lại đúng cách.

Có thể dùng container test hoặc một process server riêng để kill process A. Nếu chỉ gọi shutdownNow() trong cùng process, ghi rõ test đang mô phỏng server đóng connection chứ chưa mô phỏng crash của host hoặc network partition.

## 13. Quan sát khi test và trong production

Ghi nhận các chỉ số theo method và instance:

- RPC count, success/error rate và status code theo backend.
- Số subchannel ở READY, CONNECTING và TRANSIENT_FAILURE.
- Thời gian từ lúc instance lỗi tới khi client ngừng chọn instance đó.
- Số retry attempt, retry success, deadline exceeded và tổng latency.
- Số stream bị ngắt, reconnect và resume thành công.
- Health state và thời gian từ NOT_SERVING tới khi endpoint bị loại.

Trong log/tracing, thêm instance ID, target, method, attempt number và trace ID. Không dùng request ID hoặc một instance ID ephemeral làm metric label có cardinality không giới hạn. Với dashboard, cần tách lỗi nghiệp vụ khỏi lỗi transport để không loại nhầm một instance chỉ vì nhận request không hợp lệ.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Client vẫn gửi RPC mới tới instance đã chết | Chưa phát hiện connection failure hoặc resolver vẫn quảng bá endpoint. | Kiểm tra subchannel state, resolver refresh, health checking và timeout phát hiện lỗi. |
| Test chỉ có một backend | Không thể chứng minh failover sang instance khỏe. | Dùng ít nhất hai endpoint trên cùng channel. |
| Mỗi backend có một channel riêng | Test không kiểm tra load-balancing policy. | Dùng một channel với resolver trả nhiều địa chỉ. |
| RPC đang chạy tự chuyển sang backend khác | Hiểu nhầm load balancing là migration của call. | Kiểm tra lỗi in-flight; retry hoặc resume là một attempt/stream mới. |
| Tắt server rồi assertion chạy ngay | Client chưa kịp phát hiện connection failure. | Chờ có giới hạn theo trạng thái/lần gọi thực tế, không dùng sleep cố định. |
| Retry tạo dữ liệu trùng | RPC ghi đã commit trước khi attempt lỗi. | Idempotency key, deduplication và status lookup. |
| Health check không loại instance | Health service/config/policy chưa được bật hoặc không hỗ trợ. | Kiểm tra health protocol và cấu hình runtime thực tế. |
| Failover làm request hết deadline | Ngân sách không đủ cho phát hiện lỗi và attempt mới. | Đo failover latency, đặt deadline theo SLO và giới hạn retry. |

## 15. Bài tập thực hành

1. Khởi chạy hai Inventory server instance trên TCP port động; mỗi instance trả về instance ID.
2. Cấu hình một resolver test và một channel round_robin; xác minh cả hai instance nhận RPC trước khi fault injection.
3. Dừng instance A; xác minh RPC mới tiếp tục tới B sau khi client phát hiện A không còn READY.
4. Giữ một RPC đang chạy trên A rồi dừng A; xác minh call đang chạy thất bại thay vì giả định nó được chuyển sang B.
5. Bật health checking, đổi A sang NOT_SERVING và xác minh A không nhận RPC mới; sau đó khôi phục SERVING.
6. Cấu hình retry cho unary read idempotent; xác minh attempt mới có thể hoàn tất trên B trong deadline tổng.
7. Thực hiện test process crash hoặc network partition qua TCP/TLS và ghi nhận thời gian phát hiện/failover.
8. Mở streaming RPC, dừng backend đang phục vụ stream, rồi kiểm tra reconnect/resume bằng sequence number hoặc cursor.

Sau bài này, bạn cần phân biệt lỗi endpoint với lỗi nghiệp vụ, hiểu subchannel state và giới hạn của failover đối với RPC đang chạy, đồng thời xây dựng test có ít nhất hai instance trên cùng channel. Kiểm thử dừng server, health NOT_SERVING, retry và network failure riêng biệt giúp xác nhận Spring gRPC client tiếp tục phục vụ qua instance khỏe mà vẫn giữ đúng deadline và semantics của operation.

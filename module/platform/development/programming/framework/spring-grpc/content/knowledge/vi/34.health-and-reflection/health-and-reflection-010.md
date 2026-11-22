# Kiểm thử health transition

gRPC Health service công bố trạng thái phục vụ của toàn server hoặc từng service. Trạng thái đó thay đổi theo vòng đời ứng dụng: lúc khởi động, khi dependency thiết yếu mất kết nối, khi phục hồi và khi server bắt đầu shutdown. Một test chỉ gọi Health/Check một lần để nhận SERVING chưa chứng minh health implementation đúng; cần kiểm tra cả chuỗi chuyển trạng thái và thời điểm client quan sát được thay đổi.

Trong Spring gRPC, health transition phải phản ánh readiness thật của service được đăng ký trên server. Bài này tập trung vào mô hình trạng thái, HealthStatusManager, khác biệt giữa unary Check và streaming Watch, in-process tests, tích hợp lifecycle Spring, xử lý dependency thay đổi và kiểm tra shutdown/probe.

## 1. Health transition là gì?

Health transition là sự thay đổi trạng thái được công bố khi điều kiện phục vụ thay đổi. Ví dụ với OrderService:

```text
STARTING
   |
   | configuration + dependencies + service initialization complete
   v
SERVING
   |
   | mandatory database becomes unavailable
   v
NOT_SERVING
   |
   | dependency recovers and readiness checks pass
   v
SERVING
   |
   | graceful shutdown begins
   v
NOT_SERVING
```

Health protocol không có enum STARTING riêng. Khi service chưa sẵn sàng, ứng dụng thường công bố NOT_SERVING hoặc chưa công bố trạng thái để probe không hiểu nhầm service đã sẵn sàng. Khi điều kiện phục vụ đạt, ứng dụng chuyển sang SERVING.

Một transition đúng cần đáp ứng:

- Trạng thái phản ánh điều kiện thực tế, không chỉ phản ánh process còn sống.
- Chuyển sang NOT_SERVING đủ sớm để ngừng nhận traffic mới.
- Chỉ trở lại SERVING sau khi readiness prerequisites đã phục hồi.
- Cập nhật nhất quán cho service name mà probe/client đang kiểm tra.
- Không phát transition lặp hoặc đảo trạng thái do callback cũ đến trễ.

## 2. Phân biệt trạng thái server và trạng thái từng service

Health request có field service. Chuỗi rỗng thường đại diện trạng thái tổng thể; tên đầy đủ như acme.orders.v1.OrderService đại diện một service cụ thể.

Một server có thể host nhiều service với readiness khác nhau:

| Service | Điều kiện sẵn sàng | Trạng thái ví dụ |
| --- | --- | --- |
| OrderService | Database đơn hàng và schema đã sẵn sàng | SERVING |
| InventoryService | Inventory store và cache bắt buộc sẵn sàng | NOT_SERVING |
| Reflection | Được đăng ký theo policy môi trường | Không nhất thiết phản ánh readiness nghiệp vụ |
| Server tổng thể (chuỗi rỗng) | Chính sách tổng hợp của ứng dụng | Do readiness coordinator quyết định |

Không mặc định rằng server tổng thể SERVING nghĩa là mọi service đều SERVING. Xác định rõ semantics tổng hợp: server chỉ sẵn sàng khi tất cả service bắt buộc sẵn sàng, hay vẫn nhận traffic nếu một service tùy chọn đang NOT_SERVING.

Test cần gọi Check cho cả service name cụ thể và chuỗi rỗng. Nếu chỉ kiểm tra trạng thái tổng thể, lỗi cập nhật riêng một service có thể bị bỏ sót.

## 3. Check và Watch quan sát transition khác nhau

Health protocol chuẩn có hai RPC:

- Check: unary RPC, trả snapshot trạng thái tại thời điểm xử lý request.
- Watch: server-streaming RPC, gửi trạng thái hiện tại rồi gửi tiếp các thay đổi khi trạng thái được cập nhật.

Check phù hợp với probe định kỳ như Kubernetes. Watch phù hợp với client muốn nhận thay đổi mà không polling liên tục.

Khi test Watch, cần xác minh:

1. Client nhận trạng thái hiện tại ngay sau khi đăng ký watch.
2. Khi manager chuyển trạng thái, client nhận trạng thái mới.
3. Các transition được quan sát theo thứ tự.
4. Khi client cancel hoặc disconnect, stream được giải phóng.
5. Không giả định Watch tự hoàn tất sau response đầu tiên; đây là stream dài hạn.

Với service name không được health manager biết, Check thường kết thúc bằng RPC status NOT_FOUND; Watch có thể gửi enum SERVICE_UNKNOWN. Không trộn enum trong response với status code của RPC.

## 4. Mô hình hóa readiness để test có thể dự đoán

Tránh cập nhật health status rải rác trong nhiều bean hoặc callback. Tạo một coordinator duy nhất nhận tín hiệu từ lifecycle và dependency monitor rồi quyết định trạng thái công bố.

Ví dụ trạng thái nội bộ:

| Trạng thái nội bộ | Điều kiện | Health output |
| --- | --- | --- |
| STARTING | Chưa hoàn tất khởi tạo | NOT_SERVING |
| READY | Tất cả prerequisite bắt buộc đạt | SERVING |
| DEGRADED | Một dependency bắt buộc mất và service không thể xử lý request | NOT_SERVING |
| RECOVERING | Dependency đã kết nối lại nhưng readiness check chưa hoàn tất | NOT_SERVING |
| STOPPING | Đang graceful shutdown | NOT_SERVING |

Trạng thái nội bộ có thể phong phú hơn enum health protocol. Ví dụ DEGRADED vẫn có thể ánh xạ sang SERVING nếu service còn đáp ứng đầy đủ contract ở chế độ suy giảm; quyết định đó phải được định nghĩa theo nghiệp vụ và kiểm thử.

Coordinator nên:

- Nhận sự kiện dependency từ health monitor/circuit breaker thay vì mỗi RPC tự thay đổi trạng thái.
- Đồng bộ hóa cập nhật khi nhiều dependency thay đổi đồng thời.
- Bỏ qua callback lỗi thời nếu một transition mới hơn đã xảy ra.
- Không đánh dấu SERVING chỉ vì TCP connection tới dependency vừa mở lại; cần readiness check thành công.
- Giữ logic tính readiness độc lập với logic restart/liveness.

## 5. Đăng ký HealthStatusManager trong grpc-java

HealthStatusManager trong artifact grpc-services quản lý trạng thái và cung cấp service implementation. Có thể khởi tạo trạng thái ban đầu trước khi đăng ký service:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;

final String ORDER_SERVICE = "acme.orders.v1.OrderService";

HealthStatusManager health = new HealthStatusManager();
health.setStatus("", ServingStatus.NOT_SERVING);
health.setStatus(ORDER_SERVICE, ServingStatus.NOT_SERVING);

Server server = ServerBuilder.forPort(9090)
    .addService(new OrdersService())
    .addService(health.getHealthService())
    .build()
    .start();

// Sau khi readiness prerequisites đã đạt:
health.setStatus(ORDER_SERVICE, ServingStatus.SERVING);
health.setStatus("", ServingStatus.SERVING);
```

Đây là ví dụ grpc-java minh họa API. Trong Spring gRPC starter, đăng ký health.getHealthService() qua server configuration hook hoặc cơ chế BindableService mà phiên bản đang dùng hỗ trợ. Không dựng một server phụ chỉ để health status được cập nhật; probe phải hỏi đúng server nhận business RPC.

Khi có dependency event, coordinator gọi setStatus(serviceName, status) theo readiness policy. Khi shutdown bắt đầu, chuyển các service cần ngừng nhận traffic sang NOT_SERVING trước khi hoàn tất graceful shutdown.

## 6. Unit test cho logic chuyển trạng thái

Unit test nên kiểm tra bảng chuyển trạng thái của coordinator mà không cần mở gRPC server:

| Trạng thái hiện tại | Sự kiện | Trạng thái kế tiếp | Health output |
| --- | --- | --- | --- |
| STARTING | Initialization complete, dependencies ready | READY | SERVING |
| STARTING | Startup dependency check fails | STARTING hoặc DEGRADED theo policy | NOT_SERVING |
| READY | Mandatory dependency unavailable | DEGRADED | NOT_SERVING |
| DEGRADED | Dependency reconnects nhưng probe chưa pass | RECOVERING | NOT_SERVING |
| RECOVERING | Readiness checks pass | READY | SERVING |
| READY | Shutdown requested | STOPPING | NOT_SERVING |
| STOPPING | Callback readiness cũ đến trễ | STOPPING | Giữ NOT_SERVING |

Các assertion quan trọng:

- Mỗi sự kiện tạo đúng health output.
- Dependency tùy chọn không làm service mất readiness nếu policy không yêu cầu.
- Callback cũ không đưa service từ STOPPING trở lại SERVING.
- Hai dependency thay đổi đồng thời không làm mất update.
- Transition lặp cùng trạng thái không tạo side effect không cần thiết.

Nên dùng fake clock hoặc scheduler điều khiển được nếu readiness có debounce, cooldown hay timeout. Tránh test dựa vào Thread.sleep() dài vì dễ flaky và làm suite chậm.

## 7. In-process test cho Health/Check

In-process server/channel kiểm tra health service mà không cần TCP port. Ví dụ sau kiểm tra snapshot trước và sau transition:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.health.v1.HealthCheckRequest;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.health.v1.HealthGrpc;
import io.grpc.protobuf.services.HealthStatusManager;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class HealthTransitionTest {
    private static final String ORDER_SERVICE =
        "acme.orders.v1.OrderService";

    private HealthStatusManager manager;
    private Server server;
    private ManagedChannel channel;

    @BeforeEach
    void setUp() throws IOException {
        String name = InProcessServerBuilder.generateName();
        manager = new HealthStatusManager();
        manager.setStatus(ORDER_SERVICE, ServingStatus.NOT_SERVING);

        server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(manager.getHealthService())
            .build()
            .start();
        channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    @Test
    void checkReflectsEachTransition() {
        HealthGrpc.HealthBlockingStub stub =
            HealthGrpc.newBlockingStub(channel);
        HealthCheckRequest request = HealthCheckRequest.newBuilder()
            .setService(ORDER_SERVICE)
            .build();

        assertEquals(
            ServingStatus.NOT_SERVING,
            stub.check(request).getStatus());

        manager.setStatus(ORDER_SERVICE, ServingStatus.SERVING);
        assertEquals(
            ServingStatus.SERVING,
            stub.check(request).getStatus());

        manager.setStatus(ORDER_SERVICE, ServingStatus.NOT_SERVING);
        assertEquals(
            ServingStatus.NOT_SERVING,
            stub.check(request).getStatus());
    }
}
```

Ví dụ giả định test dependencies có grpc-inprocess, grpc-services, health proto tương thích và JUnit 5. directExecutor() làm test đơn giản hơn; nếu code readiness dùng executor bất đồng bộ, cần kiểm thử cả executor thực tế và đồng bộ hoàn tất trước assertion.

Test này chứng minh Check đọc trạng thái manager qua gRPC. Nó chưa chứng minh Spring starter đã đăng ký health service hoặc lifecycle listener đã gọi coordinator đúng lúc; phần đó cần integration test Spring riêng.

## 8. In-process test cho Health/Watch

Watch phải gửi snapshot ban đầu và cập nhật khi status thay đổi. Có thể dùng BlockingQueue để nhận các trạng thái theo thứ tự, thay vì sleep một khoảng thời gian rồi đoán callback đã chạy:

```java
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

BlockingQueue<ServingStatus> updates = new LinkedBlockingQueue<>();
AtomicReference<ClientCallStreamObserver<HealthCheckRequest>> control =
    new AtomicReference<>();

ClientResponseObserver<HealthCheckRequest, HealthCheckResponse> observer =
    new ClientResponseObserver<>() {
        @Override
        public void beforeStart(
                ClientCallStreamObserver<HealthCheckRequest> requestStream) {
            control.set(requestStream);
        }

        @Override
        public void onNext(HealthCheckResponse response) {
            updates.add(response.getStatus());
        }

        @Override
        public void onError(Throwable error) {
            // Test có thể ghi nhận lỗi để assertion ở cuối.
        }

        @Override
        public void onCompleted() {
            // Health Watch thường là stream dài hạn.
        }
    };

HealthGrpc.newStub(channel).watch(
    HealthCheckRequest.newBuilder()
        .setService(ORDER_SERVICE)
        .build(),
    observer);

assertEquals(
    ServingStatus.NOT_SERVING,
    updates.poll(2, TimeUnit.SECONDS));

manager.setStatus(ORDER_SERVICE, ServingStatus.SERVING);
assertEquals(
    ServingStatus.SERVING,
    updates.poll(2, TimeUnit.SECONDS));

control.get().cancel("test complete", null);
```

Đây là phần thân của test dùng server/channel đã được dựng trong fixture ở mục trước. Trong test hoàn chỉnh, bảo đảm control.get() khác null trước khi cancel và kiểm tra lỗi ngoài dự kiến qua một queue/latch riêng. Không để Watch stream sống sau test; cancel rõ ràng rồi mới shutdown channel/server.

Không giả định mỗi lần gọi setStatus luôn tạo một event mới nếu status không thay đổi. Test nên xác minh semantics cần thiết: snapshot ban đầu và các trạng thái khác nhau đã được công bố, không dựa vào số event của update lặp.

## 9. Kiểm thử unknown service và nhiều service

Health transition thường sai ở service name: ứng dụng cập nhật OrderService nhưng probe lại hỏi chuỗi rỗng hoặc package khác. Thêm test:

- Check cho tên service đã đăng ký trả đúng trạng thái.
- Check cho service không biết trả NOT_FOUND.
- Watch cho service không biết có behavior theo protocol/runtime đã chọn.
- Cập nhật OrderService không vô tình đổi InventoryService.
- Thay đổi trạng thái tổng thể không ghi đè trạng thái service riêng nếu policy không yêu cầu.
- Tên service dùng proto package đầy đủ, không dùng Java package hoặc tên Spring bean.

Với nhiều service, tạo một test matrix cho từng service và trạng thái. Đừng chỉ kiểm tra một service đại diện nếu mỗi service có readiness dependency khác nhau.

## 10. Tích hợp transition với Spring lifecycle và dependency

Trong Spring Boot, có thể dùng ApplicationReadyEvent để bắt đầu quá trình đánh giá readiness cuối cùng và ContextClosedEvent để chuyển trạng thái khi shutdown. Tuy nhiên, không nên mặc định chỉ cần nhận ApplicationReadyEvent là mọi dependency đã đạt readiness nghiệp vụ; coordinator vẫn phải kiểm tra prerequisite của service.

Ví dụ cấu trúc:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class GrpcHealthLifecycle {
    private final GrpcReadinessCoordinator readiness;

    GrpcHealthLifecycle(GrpcReadinessCoordinator readiness) {
        this.readiness = readiness;
    }

    @EventListener
    void onApplicationReady(ApplicationReadyEvent event) {
        readiness.evaluateAndPublish();
    }

    @EventListener
    void onContextClosed(ContextClosedEvent event) {
        readiness.markStopping();
    }
}
```

Đây là skeleton để minh họa hook. evaluateAndPublish() phải hoàn tất các readiness check bắt buộc trước khi công bố SERVING; markStopping() phải cập nhật NOT_SERVING đồng bộ trước khi server dừng nhận traffic. Nếu ứng dụng có nhiều context, lọc event theo context phù hợp để tránh bean nhận event từ context khác.

Dependency monitor hoặc circuit breaker có thể gửi event khi database/cache bắt đầu lỗi hoặc phục hồi. Chỉ dependency ảnh hưởng khả năng đáp ứng contract mới nên làm readiness chuyển NOT_SERVING. Dependency tùy chọn có thể được phản ánh bằng degraded metric/alert mà không nhất thiết rút service khỏi traffic.

## 11. Race condition, debounce và shutdown

Readiness thường được cập nhật từ nhiều nguồn: startup callback, periodic check, dependency event và shutdown. Nếu không điều phối, có thể xảy ra:

- Callback SERVING đến trễ sau khi shutdown đã bắt đầu.
- Hai monitor ghi đè trạng thái của nhau.
- Dependency chập chờn khiến health liên tục đảo SERVING/NOT_SERVING.
- Probe đọc snapshot đúng giữa thời điểm transition và test giả định sai thứ tự.
- Watch client bị bỏ quên, giữ stream và tài nguyên sau khi test kết thúc.

Biện pháp:

- Dùng state machine hoặc coordinator có synchronization/atomic transition.
- Đặt STOPPING thành trạng thái terminal cho vòng đời instance; callback readiness sau đó không được khôi phục SERVING.
- Dùng debounce/hysteresis có giới hạn để tránh flapping, nhưng không trì hoãn NOT_SERVING quá lâu khi service thật sự không thể phục vụ.
- Phân biệt timeout của một lần health check với trạng thái dependency bền vững.
- Dùng fake clock/scheduler trong unit test cho debounce và retry.
- Kiểm tra shutdown order: publish NOT_SERVING, ngừng nhận traffic mới, drain in-flight RPC theo grace period, rồi đóng server.

Health status không thay thế graceful shutdown. Nó báo cho caller/probe rằng instance không còn sẵn sàng; server vẫn cần xử lý call đang chạy và dừng transport đúng quy trình.

## 12. Ma trận kiểm thử và bài tập vận dụng

| Nhóm | Kịch bản | Điều kiện PASS |
| --- | --- | --- |
| Initial state | Server vừa start, dependency chưa sẵn sàng | Check không trả SERVING |
| Startup complete | Các prerequisite đã đạt | Service chuyển SERVING |
| Dependency loss | Dependency bắt buộc unavailable | Service chuyển NOT_SERVING |
| Dependency recovery | Dependency reconnect nhưng check chưa pass | Vẫn NOT_SERVING |
| Recovery complete | Readiness check pass | Chuyển lại SERVING |
| Per-service | Chỉ Inventory lỗi | Order không bị đổi trạng thái ngoài policy |
| Overall status | Một service bắt buộc mất readiness | Trạng thái tổng thể theo aggregation rule |
| Watch | Client subscribe rồi status đổi | Nhận initial state và update theo thứ tự |
| Unknown service | Check service name sai | RPC trả NOT_FOUND |
| Concurrent update | Nhiều event đến đồng thời | State cuối nhất quán, không mất update |
| Shutdown race | Callback readiness đến sau STOPPING | Không quay lại SERVING |
| Spring lifecycle | Context ready/close | Coordinator cập nhật đúng thời điểm |
| Probe integration | Kubelet/monitoring gọi endpoint | Đúng listener, service name và network policy |

**Bài tập:** Một ứng dụng có OrderService phụ thuộc database chính và InventoryService phụ thuộc cache. Database mất kết nối trong 8 giây rồi phục hồi; cache vẫn hoạt động. Trong lúc database phục hồi, ứng dụng bắt đầu graceful shutdown.

1. Định nghĩa state machine và aggregation policy cho hai service cùng server tổng thể.
2. Viết unit test cho startup, database loss, recovery pending, recovery complete và shutdown.
3. Viết in-process Check test để xác minh trạng thái riêng của từng service.
4. Viết Watch test xác minh snapshot ban đầu, transition và cancellation.
5. Tạo race test chứng minh callback recovery đến trễ không đưa instance khỏi NOT_SERVING sau khi đã STOPPING.
6. Tích hợp readiness coordinator với Spring lifecycle và dependency monitor.
7. Viết integration test trên server do Spring quản lý và kiểm tra probe path của môi trường triển khai.

**Câu hỏi tự kiểm tra:**

- Vì sao test một lần Check chưa đủ để xác minh health transition?
- Check và Watch khác nhau thế nào khi trạng thái thay đổi?
- Vì sao health protocol không có trạng thái STARTING?
- Khi nào dependency failure nên làm readiness chuyển NOT_SERVING?
- Làm thế nào ngăn callback cũ đưa service trở lại SERVING sau shutdown?
- Vì sao cần test cả service-specific và overall health?
- Làm thế nào tránh dùng Thread.sleep() khiến Watch test flaky?
- Vì sao health SERVING không thay thế business smoke test?

**Ghi nhớ:** Kiểm thử health transition phải xác minh cả trạng thái ban đầu, thay đổi theo dependency, phục hồi và shutdown. Dùng unit test cho state machine, in-process Check/Watch test cho protocol, và Spring integration test cho lifecycle thật. Quản lý transition tập trung, xử lý race condition và chỉ công bố SERVING khi readiness prerequisites đã đạt.

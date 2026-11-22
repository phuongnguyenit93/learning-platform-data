# Circuit breaker cho dependency gRPC

Trong ứng dụng Spring gRPC, một service thường gọi thêm các gRPC service khác để hoàn tất request. Nếu dependency chậm hoặc liên tục lỗi, request mới có thể tiếp tục chiếm thread, connection và tài nguyên chờ đợi. **Circuit breaker** theo dõi kết quả gọi dependency, tạm ngừng gửi request khi tỷ lệ lỗi hoặc tỷ lệ call chậm vượt ngưỡng, rồi cho phép một số probe kiểm tra khi dependency có cơ hội phục hồi.

Circuit breaker bảo vệ caller khỏi tiếp tục gọi một dependency đang lỗi. Nó không tự sửa dependency, không giới hạn số request đồng thời và không thay thế deadline. Với gRPC, cần kết hợp breaker với deadline, load balancing, retry có giới hạn và xử lý status code đúng semantics.

## 1. Ba trạng thái của circuit breaker

| Trạng thái | Hành vi | Chuyển trạng thái |
| --- | --- | --- |
| `CLOSED` | Cho phép call đi tới dependency và ghi nhận kết quả | Mở khi failure rate hoặc slow-call rate vượt ngưỡng |
| `OPEN` | Từ chối call ngay, không gửi request tới dependency | Chuyển sang HALF_OPEN sau thời gian chờ |
| `HALF_OPEN` | Chỉ cho phép số probe giới hạn | Đóng nếu probe đủ tốt; mở lại nếu probe thất bại hoặc quá chậm |

Luồng cơ bản:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: lỗi hoặc call chậm vượt ngưỡng
    OPEN --> HALF_OPEN: hết thời gian chờ
    HALF_OPEN --> CLOSED: probe phục hồi
    HALF_OPEN --> OPEN: probe tiếp tục lỗi
~~~

Ở `OPEN`, client fail fast thay vì chờ một connection chắc chắn thất bại. Ở `HALF_OPEN`, breaker giới hạn số call thử để tránh một lượng lớn request cùng dồn vào dependency vừa phục hồi.

## 2. Chọn lỗi nào được tính là failure

Không phải mọi gRPC status đều có nghĩa dependency không khỏe. Ví dụ `NOT_FOUND` có thể là kết quả nghiệp vụ bình thường; `INVALID_ARGUMENT` là lỗi caller; `PERMISSION_DENIED` và `UNAUTHENTICATED` là lỗi quyền/danh tính. Nếu tính tất cả các status này là failure, breaker có thể mở dù dependency đang hoạt động đúng.

Một policy thường gặp:

| gRPC status | Có tính failure cho dependency breaker? | Lý do |
| --- | --- | --- |
| `UNAVAILABLE` | Có | Dependency hoặc transport không sẵn sàng |
| `DEADLINE_EXCEEDED` | Thường có | Dependency không hoàn tất trong ngân sách thời gian |
| `INTERNAL` / `UNKNOWN` | Tùy policy; thường có nếu là lỗi server không mong đợi | Có thể phản ánh lỗi dependency |
| `RESOURCE_EXHAUSTED` | Tùy nguyên nhân | Có thể là quota caller, giới hạn message hoặc dependency quá tải |
| `NOT_FOUND` | Thường không | Có thể là kết quả nghiệp vụ hợp lệ |
| `INVALID_ARGUMENT` | Không | Caller cần sửa request |
| `UNAUTHENTICATED` / `PERMISSION_DENIED` | Không | Lỗi credential hoặc authorization |
| `CANCELLED` | Thường không | Caller hoặc call cha đã hủy |

Quy tắc phải dựa trên dependency cụ thể. Ví dụ `RESOURCE_EXHAUSTED` do server downstream quá tải có thể là tín hiệu cần mở breaker; cùng status đó do quota của một tenant cạn không nhất thiết phản ánh sức khỏe toàn dependency.

## 3. Cấu hình Resilience4j trong Spring

Resilience4j cung cấp `CircuitBreaker` có thể bọc lời gọi generated gRPC stub. Ví dụ bean cấu hình một breaker riêng cho dependency inventory:

~~~java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GrpcResilienceConfiguration {

    @Bean
    CircuitBreaker inventoryCircuitBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(
                CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(20)
            .minimumNumberOfCalls(10)
            .failureRateThreshold(50)
            .slowCallRateThreshold(60)
            .slowCallDurationThreshold(Duration.ofMillis(300))
            .waitDurationInOpenState(Duration.ofSeconds(5))
            .permittedNumberOfCallsInHalfOpenState(3)
            .automaticTransitionFromOpenToHalfOpenEnabled(true)
            .recordException(GrpcResilienceConfiguration::isDependencyFailure)
            .build();

        return CircuitBreaker.of("inventory-grpc", config);
    }

    private static boolean isDependencyFailure(Throwable error) {
        if (!(error instanceof StatusRuntimeException grpcError)) {
            return false;
        }

        Status.Code code = grpcError.getStatus().getCode();
        return code == Status.Code.UNAVAILABLE
            || code == Status.Code.DEADLINE_EXCEEDED
            || code == Status.Code.INTERNAL
            || code == Status.Code.UNKNOWN;
    }
}
~~~

Các ngưỡng trong ví dụ chỉ là điểm khởi đầu: cửa sổ 20 call, cần tối thiểu 10 call trước khi đánh giá, mở khi failure rate từ 50% hoặc slow-call rate từ 60%, và chờ 5 giây trước HALF_OPEN. Cần hiệu chỉnh theo traffic, latency SLO và khả năng phục hồi của dependency.

`recordException` quyết định exception nào được tính là failure. Các exception không được predicate chọn sẽ không làm tăng failure rate. Không cấu hình mọi `StatusRuntimeException` là failure nếu dependency có thể trả các status nghiệp vụ như `NOT_FOUND`.

## 4. Bọc lời gọi generated stub

Tách client gọi dependency thành gateway giúp circuit breaker được áp dụng nhất quán:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import java.util.concurrent.TimeUnit;

public final class InventoryGateway {

    private final InventoryServiceGrpc.InventoryServiceBlockingStub stub;
    private final CircuitBreaker circuitBreaker;

    public InventoryGateway(
            InventoryServiceGrpc.InventoryServiceBlockingStub stub,
            CircuitBreaker circuitBreaker) {
        this.stub = stub;
        this.circuitBreaker = circuitBreaker;
    }

    public GetStockResponse getStock(GetStockRequest request) {
        return circuitBreaker.executeSupplier(() ->
            stub.withDeadlineAfter(500, TimeUnit.MILLISECONDS)
                .getStock(request));
    }
}
~~~

`executeSupplier` chỉ gọi supplier khi breaker cho phép. Nếu breaker đang OPEN, Resilience4j ném `CallNotPermittedException` và generated stub không được gọi. Deadline của RPC vẫn cần thiết vì breaker chỉ đánh giá kết quả sau khi call kết thúc; không có deadline, một call bị treo có thể giữ breaker và thread quá lâu.

Trong request chain, deadline của lời gọi con không nên vượt deadline còn lại của request cha. Dùng deadline nhỏ hơn giữa ngân sách riêng của dependency và deadline cha; dành một phần ngân sách cho việc xử lý response sau khi dependency trả kết quả.

## 5. Ánh xạ breaker OPEN về gRPC status ở API bên ngoài

Khi dependency breaker mở, service phía trên cần trả một lỗi có ý nghĩa cho caller thay vì để exception nội bộ rơi thành `UNKNOWN`:

~~~java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.stub.StreamObserver;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;

public final class CatalogGrpcService
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    private final InventoryGateway inventoryGateway;

    public CatalogGrpcService(InventoryGateway inventoryGateway) {
        this.inventoryGateway = inventoryGateway;
    }

    @Override
    public void getAvailability(
            GetAvailabilityRequest request,
            StreamObserver<GetAvailabilityResponse> observer) {
        try {
            GetStockResponse stock = inventoryGateway.getStock(
                GetStockRequest.newBuilder()
                    .setSku(request.getSku())
                    .build());

            observer.onNext(GetAvailabilityResponse.newBuilder()
                .setSku(stock.getSku())
                .setAvailableQuantity(stock.getAvailableQuantity())
                .build());
            observer.onCompleted();
        } catch (CallNotPermittedException openBreaker) {
            observer.onError(Status.UNAVAILABLE
                .withDescription("inventory dependency temporarily unavailable")
                .asRuntimeException());
        } catch (StatusRuntimeException downstreamError) {
            observer.onError(mapDownstreamError(downstreamError));
        }
    }

    private RuntimeException mapDownstreamError(
            StatusRuntimeException error) {
        Status.Code code = error.getStatus().getCode();
        if (code == Status.Code.NOT_FOUND
                || code == Status.Code.INVALID_ARGUMENT
                || code == Status.Code.PERMISSION_DENIED
                || code == Status.Code.UNAUTHENTICATED) {
            return Status.fromCode(code)
                .withDescription("request could not be completed")
                .asRuntimeException();
        }

        if (code == Status.Code.DEADLINE_EXCEEDED) {
            return Status.DEADLINE_EXCEEDED
                .withDescription("inventory dependency timed out")
                .asRuntimeException();
        }

        if (code == Status.Code.UNAVAILABLE
                || code == Status.Code.INTERNAL
                || code == Status.Code.UNKNOWN) {
            return Status.UNAVAILABLE
                .withDescription("inventory dependency failed")
                .asRuntimeException();
        }

        return Status.fromCode(code)
            .withDescription("inventory dependency request failed")
            .asRuntimeException();
    }
}
~~~

Ví dụ mapping cần được điều chỉnh theo hợp đồng API. Không tiết lộ hostname, exception message hoặc chi tiết nội bộ của dependency trong status description. Nếu fallback nghiệp vụ an toàn, service có thể trả dữ liệu cache hoặc trạng thái degraded thay vì lỗi; không tạo giá trị giả làm caller hiểu nhầm tồn kho chính xác.

## 6. Kiểm thử breaker mở và fail fast

Test cần chứng minh sau đủ số lỗi dependency, breaker chuyển OPEN và request tiếp theo không chạm tới server. Dùng in-process server để mô phỏng dependency trả `UNAVAILABLE`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class InventoryCircuitBreakerTest {

    private Server server;
    private ManagedChannel channel;
    private CircuitBreaker breaker;
    private InventoryGateway gateway;
    private AtomicInteger dependencyCalls;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        dependencyCalls = new AtomicInteger();

        InventoryServiceGrpc.InventoryServiceImplBase dependency =
            new InventoryServiceGrpc.InventoryServiceImplBase() {
                @Override
                public void getStock(
                        GetStockRequest request,
                        StreamObserver<GetStockResponse> observer) {
                    dependencyCalls.incrementAndGet();
                    observer.onError(Status.UNAVAILABLE
                        .withDescription("dependency is down")
                        .asRuntimeException());
                }
            };

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(dependency)
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(50)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .recordException(error ->
                error instanceof StatusRuntimeException grpcError
                    && grpcError.getStatus().getCode()
                        == Status.Code.UNAVAILABLE)
            .build();

        breaker = CircuitBreaker.of("inventory-test", config);
        var stub = InventoryServiceGrpc.newBlockingStub(channel);
        gateway = new InventoryGateway(stub, breaker);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (server != null) {
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }

    @Test
    void opensAfterRepeatedUnavailableAndRejectsWithoutCallingServer() {
        GetStockRequest request = GetStockRequest.newBuilder()
            .setSku("SKU-42")
            .build();

        for (int attempt = 0; attempt < 2; attempt++) {
            StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> gateway.getStock(request));
            assertEquals(
                Status.Code.UNAVAILABLE,
                error.getStatus().getCode());
        }

        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());

        assertThrows(
            CallNotPermittedException.class,
            () -> gateway.getStock(request));

        assertEquals(2, dependencyCalls.get());
    }
}
~~~

Hai call đầu tiên đi tới dependency và nhận `UNAVAILABLE`; cửa sổ hai call đạt failure rate 100%, nên breaker mở. Call thứ ba bị từ chối ngay và `dependencyCalls` vẫn bằng hai. Test không cần `Thread.sleep()` vì trạng thái OPEN được kích hoạt ngay khi đủ số mẫu.

Test này tập trung vào trạng thái OPEN. Có thể bổ sung test HALF_OPEN bằng clock điều khiển hoặc cấu hình thời gian chờ ngắn có đồng bộ hóa; không nên dựa vào sleep dài để làm test ổn định.

## 7. Failure rate, slow-call rate và cửa sổ thống kê

Circuit breaker thường dùng một sliding window để tính tỷ lệ lỗi:

- **Count-based window:** tính trên N call gần nhất.
- **Time-based window:** tính trên các call trong một khoảng thời gian.
- **Minimum number of calls:** chỉ đánh giá khi đã có đủ mẫu, tránh một lỗi đơn lẻ làm mở breaker.
- **Failure rate threshold:** tỷ lệ lỗi tối thiểu để mở breaker.
- **Slow-call rate threshold:** tỷ lệ call vượt slow-call duration threshold để mở breaker.

Chọn cửa sổ theo lưu lượng. Với dependency có traffic thấp, count window lớn có thể mất lâu mới đủ mẫu; với traffic cao, time window giúp phản ánh lỗi gần đây. Slow-call threshold nên phù hợp SLO và ngắn hơn deadline của downstream để breaker có thể nhận diện dependency đang suy giảm trước khi mọi call timeout.

## 8. Kết hợp circuit breaker, retry, deadline và bulkhead

Các cơ chế giải quyết vấn đề khác nhau:

| Cơ chế | Bảo vệ điều gì |
| --- | --- |
| Deadline | Giới hạn thời gian một RPC được phép chiếm tài nguyên |
| Retry | Thử lại lỗi tạm thời theo policy |
| Circuit breaker | Ngừng gọi dependency khi tỷ lệ lỗi/chậm quá cao |
| Bulkhead | Giới hạn số call đồng thời hoặc tài nguyên dành cho dependency |
| Load balancing | Chọn backend khác đang phục vụ được |

Không để retry khuếch đại lỗi. Nếu breaker bao quanh toàn bộ retry operation, breaker thường ghi nhận kết quả cuối của một logical call; nếu retry bao quanh breaker, mỗi attempt có thể được tính riêng. Chọn thứ tự decorator có chủ đích và kiểm thử số attempt thực tế.

Không dùng breaker thay cho bulkhead: ở trạng thái CLOSED, nhiều call đồng thời vẫn có thể đi vào dependency. Với blocking stub, giới hạn thread/connection và deadline đặc biệt quan trọng để tránh cạn worker pool.

## 9. Phạm vi breaker và trạng thái HALF_OPEN

Tạo breaker riêng cho dependency hoặc nhóm operation có cùng failure semantics. Không dùng một breaker toàn cục cho mọi gRPC dependency: lỗi inventory không nên làm ngừng call payment hoặc identity service.

Trong HALF_OPEN, chỉ cho phép số probe giới hạn. Probe nên là RPC đại diện cho khả năng phục vụ thật, có deadline ngắn và không tạo side effect. Nếu probe thành công đủ điều kiện, breaker đóng; nếu tiếp tục lỗi hoặc chậm, breaker mở lại và bắt đầu thời gian chờ mới.

Trạng thái Resilience4j thường nằm trong process client. Nếu ứng dụng có nhiều instance, mỗi instance có thể mở/đóng breaker ở thời điểm khác nhau. Không giả định một breaker cục bộ là cơ chế điều phối trạng thái toàn cluster.

## 10. Metrics và quan sát

Theo dõi tối thiểu:

- Trạng thái breaker: CLOSED, OPEN, HALF_OPEN.
- Số call thành công, thất bại, bị từ chối và call chậm.
- Failure rate và slow-call rate.
- Số lần chuyển trạng thái và thời gian ở OPEN.
- Số lần downstream UNAVAILABLE/DEADLINE_EXCEEDED.
- Retry attempt và tỷ lệ retry thành công.
- Latency p50/p95/p99 của dependency.

Resilience4j có event publisher để ghi nhận chuyển trạng thái:

~~~java
inventoryCircuitBreaker.getEventPublisher()
    .onStateTransition(event ->
        log.warn("Inventory breaker transition: {}", event));
~~~

Nếu dùng Micrometer/Actuator integration của Resilience4j, xuất metrics theo dependency name và theo dõi qua dashboard/alert. Tránh gắn user ID, request ID hoặc SKU làm metric tag vì cardinality cao; các giá trị đó phù hợp hơn với trace/log có kiểm soát.

## 11. Kiểm thử qua Spring application context

In-process test xác minh cách breaker bọc generated stub và status được ghi nhận. Nó không chứng minh Spring đã đăng ký đúng bean, property hoặc Micrometer binder. Bổ sung Spring integration test để:

- Khởi động application context với breaker bean và client channel thật.
- Xác minh gateway nhận đúng breaker theo dependency name.
- Gọi dependency giả trả UNAVAILABLE nhiều lần và kiểm tra breaker chuyển OPEN.
- Xác minh call tiếp theo fail fast và không đến server.
- Kiểm tra metrics/event được xuất ra đúng registry.
- Kiểm tra graceful recovery khi dependency phục hồi và breaker chuyển HALF_OPEN rồi CLOSED.

Nếu dùng annotation `@CircuitBreaker`, kiểm tra method có được gọi qua Spring proxy hay không; self-invocation có thể bỏ qua proxy advice. Với gRPC service method và generated stub, cách bọc tường minh trong gateway thường dễ thấy thứ tự deadline/retry/breaker hơn.

## 12. Ma trận kiểm thử đề xuất

| Kịch bản | Kết quả mong đợi | Dependency call |
| --- | --- | --- |
| Dependency trả thành công | Breaker giữ CLOSED | Có |
| Dependency trả UNAVAILABLE đủ ngưỡng | Breaker chuyển OPEN | Các call mẫu có đi tới |
| Breaker OPEN | Call fail fast | Không |
| Hết wait duration | Breaker chuyển HALF_OPEN | Chỉ probe giới hạn |
| Probe thành công | Breaker đóng lại | Có |
| Probe thất bại/chậm | Breaker mở lại | Có probe |
| Dependency trả NOT_FOUND | Không tính failure theo policy ví dụ | Có |
| Caller bị CANCELLED | Không mặc định tính dependency failure | Tùy call đã tới server |
| Retry được bật | Số attempt nằm trong deadline tổng | Theo policy |

## 13. Ghi nhớ và tự kiểm tra

**Circuit breaker cho dependency gRPC** theo dõi lỗi và call chậm để chuyển CLOSED → OPEN → HALF_OPEN, tránh tiếp tục gọi dependency đang suy giảm. Với Spring, dùng Resilience4j bọc generated stub, phân loại gRPC status bằng `recordException`, đặt deadline cho mỗi RPC và ánh xạ breaker OPEN thành lỗi availability phù hợp ở API bên ngoài. Kiểm thử phải chứng minh call bị từ chối không chạm dependency.

Tự kiểm tra:

1. Vì sao NOT_FOUND không nên mặc định được tính là dependency failure?
2. OPEN và HALF_OPEN khác nhau như thế nào?
3. Vì sao circuit breaker không thay thế deadline hoặc bulkhead?
4. Thứ tự retry và circuit breaker ảnh hưởng cách đếm failure ra sao?
5. Vì sao mỗi dependency cần failure policy riêng?
6. Làm thế nào chứng minh call bị từ chối khi breaker OPEN không tới server?

Circuit breaker được cấu hình đúng giúp Spring gRPC fail fast khi dependency lỗi, giới hạn tải trong thời gian phục hồi và đưa traffic trở lại có kiểm soát sau khi dependency khỏe lại.

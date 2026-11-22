# Bulkhead theo client hoặc method

Trong ứng dụng Spring gRPC, một client thường gọi nhiều RPC method trên cùng dependency. Nếu một method chậm hoặc có lượng request tăng đột biến, nó có thể chiếm hết thread và khả năng xử lý dành cho các method còn lại. **Bulkhead** giới hạn số call đồng thời trong từng phạm vi, giúp cô lập tải và giữ phần capacity còn lại cho công việc quan trọng.

Có thể đặt bulkhead ở hai phạm vi:

- **Theo client/dependency:** một giới hạn chung cho tất cả RPC gọi tới một downstream service.
- **Theo method:** mỗi RPC method có giới hạn riêng để method tốn tài nguyên không chiếm hết capacity của method khác.

Hai phạm vi có thể dùng cùng lúc: bulkhead cấp client đặt trần tổng số call tới dependency; bulkhead cấp method đặt trần nhỏ hơn cho từng operation.

## 1. Bulkhead bảo vệ điều gì?

Bulkhead giới hạn concurrency, tức số công việc được phép chạy đồng thời. Khi hết permit, call mới có thể bị từ chối ngay hoặc chờ trong khoảng thời gian được cấu hình. Với gRPC client dùng blocking stub, semaphore bulkhead là lựa chọn đơn giản: acquire permit trước RPC và release khi RPC kết thúc, kể cả khi lỗi hoặc deadline hết.

Bulkhead khác với các cơ chế reliability khác:

| Cơ chế | Mục đích |
| --- | --- |
| Deadline | Giới hạn thời gian một RPC được phép chạy |
| Retry | Thử lại lỗi tạm thời theo policy |
| Circuit breaker | Ngừng gọi dependency khi lỗi/chậm vượt ngưỡng |
| Bulkhead | Giới hạn số call đồng thời và cô lập capacity |
| Load balancing | Chọn backend phù hợp cho call |

Deadline ngăn một call giữ tài nguyên vô hạn, còn bulkhead ngăn quá nhiều call cùng chiếm tài nguyên. Cần cả hai khi downstream có latency biến động.

## 2. Chọn phạm vi: client hay method

Giả sử InventoryService có hai RPC:

- GetStock: truy vấn tồn kho, thường nhanh và có tần suất cao.
- ReserveStock: giữ hàng, có thể kiểm tra nhiều điều kiện và cần nhiều tài nguyên hơn.

Có thể đặt giới hạn như sau:

| Bulkhead | Phạm vi | Ví dụ giới hạn |
| --- | --- | ---: |
| inventory-client | Tổng mọi call tới InventoryService | 30 |
| inventory-get-stock | Chỉ GetStock | 12 |
| inventory-reserve-stock | Chỉ ReserveStock | 5 |

Khi ReserveStock có nhiều call đồng thời, nó chỉ chiếm tối đa 5 permit riêng; các call GetStock vẫn có thể sử dụng capacity của mình, trong khi tổng hai method vẫn bị giới hạn bởi 30 permit cấp client.

Chỉ dùng bulkhead theo method có thể khiến tổng call tới dependency vẫn quá lớn nếu có nhiều method. Chỉ dùng bulkhead theo client có thể khiến một method chiếm gần hết permit chung. Kết hợp hai tầng khi dependency có nhiều operation với chi phí và mức độ ưu tiên khác nhau.

## 3. Cấu hình Resilience4j trong Spring

Với blocking gRPC stub, dùng semaphore bulkhead và đặt maxWaitDuration bằng zero để call vượt giới hạn bị từ chối ngay:

~~~java
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InventoryBulkheadConfiguration {

    @Bean("inventoryClientBulkhead")
    Bulkhead inventoryClientBulkhead() {
        BulkheadConfig config = BulkheadConfig.custom()
            .maxConcurrentCalls(30)
            .maxWaitDuration(Duration.ZERO)
            .build();
        return Bulkhead.of("inventory-client", config);
    }

    @Bean("inventoryGetStockBulkhead")
    Bulkhead inventoryGetStockBulkhead() {
        BulkheadConfig config = BulkheadConfig.custom()
            .maxConcurrentCalls(12)
            .maxWaitDuration(Duration.ZERO)
            .build();
        return Bulkhead.of("inventory-get-stock", config);
    }

    @Bean("inventoryReserveStockBulkhead")
    Bulkhead inventoryReserveStockBulkhead() {
        BulkheadConfig config = BulkheadConfig.custom()
            .maxConcurrentCalls(5)
            .maxWaitDuration(Duration.ZERO)
            .build();
        return Bulkhead.of("inventory-reserve-stock", config);
    }
}
~~~

Các con số trên chỉ minh họa. Chọn giới hạn theo số worker, connection, CPU, latency và khả năng xử lý của dependency. Nếu ứng dụng chạy nhiều replica, mỗi process có bulkhead riêng; tổng concurrency toàn hệ thống có thể bằng giới hạn mỗi process nhân số replica. Không xem giới hạn local là quota cluster.

Đặt maxWaitDuration nhỏ hoặc bằng zero để request quá tải fail fast. Nếu cho chờ, thời gian chờ phải nằm trong deadline tổng của RPC và không làm cạn thread pool của server nhận request.

## 4. Bọc generated stub bằng bulkhead cấp client và cấp method

Gateway là nơi thích hợp để áp dụng giới hạn outbound nhất quán. Ví dụ dưới đây dùng đồng thời bulkhead tổng của client và bulkhead riêng cho GetStock:

~~~java
import io.github.resilience4j.bulkhead.Bulkhead;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;

public final class InventoryGateway {

    private final InventoryServiceGrpc.InventoryServiceBlockingStub stub;
    private final Bulkhead clientBulkhead;
    private final Bulkhead getStockBulkhead;
    private final Bulkhead reserveStockBulkhead;

    public InventoryGateway(
            InventoryServiceGrpc.InventoryServiceBlockingStub stub,
            @Qualifier("inventoryClientBulkhead")
            Bulkhead clientBulkhead,
            @Qualifier("inventoryGetStockBulkhead")
            Bulkhead getStockBulkhead,
            @Qualifier("inventoryReserveStockBulkhead")
            Bulkhead reserveStockBulkhead) {
        this.stub = stub;
        this.clientBulkhead = clientBulkhead;
        this.getStockBulkhead = getStockBulkhead;
        this.reserveStockBulkhead = reserveStockBulkhead;
    }

    public GetStockResponse getStock(GetStockRequest request)
            throws Exception {
        return clientBulkhead.executeCallable(() ->
            getStockBulkhead.executeCallable(() ->
                stub.withDeadlineAfter(2, TimeUnit.SECONDS)
                    .getStock(request)));
    }

    public ReserveStockResponse reserveStock(
            ReserveStockRequest request) throws Exception {
        return clientBulkhead.executeCallable(() ->
            reserveStockBulkhead.executeCallable(() ->
                stub.withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                    .reserveStock(request)));
    }
}
~~~

Lời gọi acquire permit theo thứ tự client rồi method. Nếu method bulkhead từ chối, executeCallable ở tầng client vẫn release permit trong quá trình thoát khỏi supplier. Với cấu hình chờ bằng zero, request không giữ permit client trong lúc đợi permit method.

Đặt deadline bên trong supplier để ngân sách RPC chỉ bắt đầu khi call được phép đi tiếp. Nếu cần tính cả thời gian chờ permit, hãy tạo deadline trước khi vào bulkhead và truyền phần thời gian còn lại cho stub; với maxWaitDuration bằng zero, khoảng chờ permit gần như không đáng kể.

Không tạo bulkhead mới cho từng request. Các bulkhead phải là bean hoặc instance dùng chung theo dependency/method để chúng thực sự giới hạn concurrency tổng hợp.

## 5. Ánh xạ bulkhead rejection về gRPC status

Khi bulkhead hết permit, Resilience4j ném BulkheadFullException trước khi generated stub gửi RPC. Nếu method hiện tại đang phục vụ caller khác, service biên có thể chuyển lỗi từ chối capacity thành status phù hợp với hợp đồng API:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import io.github.resilience4j.bulkhead.BulkheadFullException;

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
        } catch (BulkheadFullException rejected) {
            observer.onError(Status.RESOURCE_EXHAUSTED
                .withDescription("inventory concurrency limit reached")
                .asRuntimeException());
        } catch (io.grpc.StatusRuntimeException downstreamError) {
            observer.onError(downstreamError);
        } catch (Exception unexpected) {
            observer.onError(Status.INTERNAL
                .withDescription("inventory request failed")
                .asRuntimeException());
        }
    }
}
~~~

RESOURCE_EXHAUSTED phù hợp khi API muốn biểu diễn quota/concurrency capacity đã cạn. Một số hệ thống có thể chọn UNAVAILABLE cho tình trạng dependency tạm thời không nhận thêm tải. Chọn một semantics nhất quán và ghi rõ cho client; không biến lỗi nghiệp vụ như NOT_FOUND thành bulkhead rejection.

Không trả exception message nội bộ cho caller. Log riêng nguyên nhân, bulkhead name và method để vận hành có thể phân biệt client-wide saturation với một method cụ thể đã hết permit.

## 6. Kiểm thử method bulkhead cô lập call đồng thời

Test dưới đây giữ một GetStock đang chạy bằng latch. Permit của method chỉ là một, nên call thứ hai bị từ chối ngay và không tới dependency. Client-wide bulkhead có hai permit để chứng minh giới hạn method là nguyên nhân từ chối:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.bulkhead.BulkheadFullException;
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class InventoryBulkheadTest {

    private Server server;
    private ManagedChannel channel;
    private ExecutorService clientExecutor;
    private CountDownLatch firstCallEntered;
    private CountDownLatch releaseFirstCall;
    private AtomicInteger dependencyCalls;
    private InventoryGateway gateway;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        firstCallEntered = new CountDownLatch(1);
        releaseFirstCall = new CountDownLatch(1);
        dependencyCalls = new AtomicInteger();
        clientExecutor = Executors.newSingleThreadExecutor();

        InventoryServiceGrpc.InventoryServiceImplBase service =
            new InventoryServiceGrpc.InventoryServiceImplBase() {
                @Override
                public void getStock(
                        GetStockRequest request,
                        StreamObserver<GetStockResponse> observer) {
                    dependencyCalls.incrementAndGet();
                    firstCallEntered.countDown();
                    try {
                        if (!releaseFirstCall.await(2, TimeUnit.SECONDS)) {
                            observer.onError(Status.DEADLINE_EXCEEDED
                                .asRuntimeException());
                            return;
                        }
                        observer.onNext(GetStockResponse.newBuilder()
                            .setSku(request.getSku())
                            .setAvailableQuantity(7)
                            .build());
                        observer.onCompleted();
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        observer.onError(Status.CANCELLED
                            .asRuntimeException());
                    }
                }
            };

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(service)
            .build()
            .start();
        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        Bulkhead clientBulkhead = Bulkhead.of(
            "inventory-client-test",
            BulkheadConfig.custom()
                .maxConcurrentCalls(2)
                .maxWaitDuration(Duration.ZERO)
                .build());
        Bulkhead getStockBulkhead = Bulkhead.of(
            "inventory-get-stock-test",
            BulkheadConfig.custom()
                .maxConcurrentCalls(1)
                .maxWaitDuration(Duration.ZERO)
                .build());
        Bulkhead reserveBulkhead = Bulkhead.of(
            "inventory-reserve-test",
            BulkheadConfig.custom()
                .maxConcurrentCalls(1)
                .maxWaitDuration(Duration.ZERO)
                .build());

        gateway = new InventoryGateway(
            InventoryServiceGrpc.newBlockingStub(channel),
            clientBulkhead,
            getStockBulkhead,
            reserveBulkhead);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        releaseFirstCall.countDown();
        if (clientExecutor != null) {
            clientExecutor.shutdownNow();
            assertTrue(clientExecutor.awaitTermination(5, TimeUnit.SECONDS));
        }
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
    void secondGetStockIsRejectedWhileFirstCallHoldsMethodPermit()
            throws Exception {
        GetStockRequest request = GetStockRequest.newBuilder()
            .setSku("SKU-42")
            .build();

        Future<GetStockResponse> firstCall =
            clientExecutor.submit(() -> gateway.getStock(request));

        assertTrue(firstCallEntered.await(1, TimeUnit.SECONDS));

        assertThrows(
            BulkheadFullException.class,
            () -> gateway.getStock(request));
        assertEquals(1, dependencyCalls.get());

        releaseFirstCall.countDown();
        GetStockResponse response = firstCall.get(2, TimeUnit.SECONDS);
        assertEquals("SKU-42", response.getSku());
        assertEquals(1, dependencyCalls.get());
    }
}
~~~

directExecutor() làm handler chạy trên luồng dispatch của call đầu tiên; test gửi call đầu qua executor riêng để luồng test chính vẫn có thể gửi call thứ hai. Latch tạo thứ tự xác định: call đầu đã vào server trước khi assertion rejection chạy. Không dùng Thread.sleep() để tạo cạnh tranh giả định.

Test xác minh ba điều: call đầu chiếm permit, call thứ hai bị BulkheadFullException, và dependency chỉ nhận một request. Khi call đầu hoàn tất, permit được release và method có thể nhận call tiếp theo.

Để kiểm tra **bulkhead cấp client**, đảo giới hạn trong fixture: đặt client bulkhead có một permit, còn bulkhead GetStock có hai permit. Giữ call đầu ở server bằng cùng hai latch; call thứ hai sẽ bị từ chối ngay tại client bulkhead và counter downstream vẫn bằng một. Cách đổi giới hạn này giúp xác định rõ tầng nào đang từ chối call.

## 7. Semaphore bulkhead và thread-pool bulkhead

Resilience4j có hai cách cô lập chính:

| Loại | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| Semaphore bulkhead | Giới hạn số call đồng thời bằng permit; không tạo thread pool riêng | Blocking stub hoặc tác vụ đã có executor phù hợp |
| Fixed thread-pool bulkhead | Dùng thread pool và queue có giới hạn | Muốn tách worker pool cho dependency hoặc cô lập tác vụ blocking |

Semaphore bulkhead không tự tạo thread. Nó chỉ kiểm soát số call được phép đi vào. Fixed thread-pool bulkhead thêm executor/queue; queue đầy cũng có thể từ chối call. Không tạo queue lớn để che giấu dependency chậm vì request vẫn tiêu thụ bộ nhớ và có thể hết deadline khi đang chờ.

Với blocking stub, semaphore bulkhead thường dễ kiểm soát: permit được giữ trong toàn bộ thời gian lời gọi đồng bộ chạy. Với async stub hoặc streaming RPC, cần giữ permit đến terminal event (onCompleted, onError hoặc cancellation). Không chỉ bọc thao tác tạo call rồi release ngay khi method trả về, vì khi đó stream vẫn chạy nhưng không còn bị giới hạn.

## 8. Cancellation và deadline phải release permit

Với blocking call, executeCallable quản lý acquire/release trong cả đường thành công và exception. Khi deadline hết hoặc call bị cancel, blocking stub thoát bằng exception và permit được trả lại. Đảm bảo không bắt exception rồi giữ một semaphore thủ công mà quên release trong finally.

Với async call, cần gắn release vào đúng một terminal callback. Tránh release hai lần nếu cả cancellation và error callback cùng đi qua logic cleanup. Khi caller hủy stream, cancel call downstream và release permit sau khi đã kết thúc xử lý callback.

Không để một call giữ permit trong lúc chờ một queue không giới hạn. Cấu hình deadline cho downstream và thời gian chờ bulkhead ngắn hơn phần deadline còn lại.

## 9. Tránh cấu hình bulkhead làm nghẽn toàn hệ thống

Một số lỗi thiết kế thường gặp:

- **Giới hạn quá thấp:** request hợp lệ bị từ chối thường xuyên dù dependency còn capacity.
- **Giới hạn quá cao:** bulkhead không còn bảo vệ dependency hoặc worker pool.
- **Một bulkhead dùng chung mọi dependency:** lỗi hoặc tải cao của một dependency làm cạn permit của dependency khác.
- **Bulkhead riêng từng request:** không có giới hạn tổng hợp thực tế.
- **Queue quá dài:** latency tăng, request hết deadline khi chưa được xử lý.
- **Nested bulkhead chờ lâu:** call giữ permit cấp ngoài trong lúc đợi permit cấp trong.
- **Không tính số replica:** tổng concurrency toàn cluster vượt capacity dependency.

Đo concurrency thực tế, rejection rate, queue wait, latency và số call downstream trước khi điều chỉnh. Nếu một method thường xuyên từ chối nhưng các method khác còn rảnh, cân nhắc tăng quota riêng method đó hoặc giảm tải của operation; không nhất thiết tăng trần toàn client.

## 10. Tích hợp với circuit breaker và retry

Bulkhead, circuit breaker và retry có thể cùng bọc một RPC nhưng thứ tự ảnh hưởng tới tài nguyên và cách thống kê:

- Bulkhead bên ngoài retry giữ một permit cho toàn logical operation, kể cả thời gian backoff.
- Retry bên ngoài bulkhead acquire/release permit cho từng attempt, giúp không giữ permit trong lúc chờ backoff.
- Circuit breaker nên nhận biết lỗi downstream thật; bulkhead rejection nội bộ không nên mặc định bị tính là dependency failure.

Chọn thứ tự theo mục tiêu và kiểm thử số attempt, số permit được giữ và status cuối cùng. Với retry nhiều attempt, deadline tổng phải bao gồm backoff. Không retry BulkheadFullException ngay lập tức vì request mới chỉ làm tăng tải lên hệ thống đang bận.

## 11. Metrics và quan sát

Theo dõi từng bulkhead theo dependency và method:

- Số permit tối đa, số permit đang dùng và số permit còn lại.
- Số call được chấp nhận và số call bị từ chối.
- Thời gian chờ permit nếu cho phép chờ.
- Latency RPC và tỷ lệ deadline exceeded.
- Concurrency theo method.
- Tỷ lệ RESOURCE_EXHAUSTED hoặc UNAVAILABLE do admission policy.

Resilience4j có event publisher để ghi nhận rejection:

~~~java
getStockBulkhead.getEventPublisher()
    .onCallRejected(event ->
        log.warn("GetStock bulkhead rejected a call: {}", event));
~~~

Nếu dùng Micrometer integration, xuất metrics theo tên dependency và method. Tránh dùng user ID, SKU hoặc request ID làm metric tag vì cardinality cao; giữ các giá trị đó trong trace/log có kiểm soát.

## 12. Kiểm thử qua Spring application context

In-process test xác minh gateway và bulkhead hoạt động cùng nhau, nhưng không chứng minh Spring đã inject đúng bean hoặc cấu hình production. Bổ sung integration test để:

- Khởi động application context với các bulkhead bean theo dependency/method.
- Xác minh GetStock và ReserveStock dùng đúng bulkhead riêng.
- Giữ một method bận và chứng minh method khác vẫn được nhận nếu client-wide capacity còn permit.
- Xác minh tổng call tới cùng dependency không vượt client bulkhead.
- Kiểm tra BulkheadFullException được ánh xạ về status công khai theo API contract.
- Kiểm tra metrics và graceful shutdown của channel/executor.

Nếu dùng annotation @Bulkhead, kiểm tra method được gọi qua Spring proxy; self-invocation có thể bỏ qua proxy advice. Gateway bọc tường minh generated stub thường giúp nhìn rõ phạm vi permit và deadline.

## 13. Ma trận kiểm thử đề xuất

| Kịch bản | Kết quả mong đợi | Downstream |
| --- | --- | --- |
| Số call dưới giới hạn | Thành công | Call được gửi |
| Vượt method bulkhead | Bị từ chối nhanh | Không gửi call vượt giới hạn |
| Vượt client bulkhead | Bị từ chối nhanh | Không gửi call vượt giới hạn |
| GetStock bận, ReserveStock còn permit | ReserveStock vẫn được nhận nếu client capacity còn | Có |
| RPC hoàn tất hoặc lỗi | Permit được release | Có thể nhận call mới |
| Deadline/cancellation | Permit được release | Call bị kết thúc |
| Dependency chậm | Concurrency vẫn bị chặn ở ngưỡng | Không vượt giới hạn |
| Nhiều application replica | Tổng capacity được tính theo từng process | Không vượt budget toàn cluster |

## 14. Ghi nhớ và tự kiểm tra

**Bulkhead theo client hoặc method** giới hạn concurrency ở hai tầng: một bulkhead chung bảo vệ tổng call tới dependency, còn bulkhead riêng bảo vệ từng RPC method khỏi chiếm capacity của method khác. Với blocking generated stub, dùng Resilience4j semaphore bulkhead, maxWaitDuration ngắn và deadline hữu hạn. Kiểm thử bằng in-process server, latch và counter để chứng minh call vượt giới hạn bị từ chối trước khi tới downstream.

Tự kiểm tra:

1. Khi nào nên dùng bulkhead chung theo client và khi nào cần bulkhead riêng theo method?
2. Vì sao chỉ dùng bulkhead method có thể chưa giới hạn được tổng tải dependency?
3. Semaphore bulkhead khác fixed thread-pool bulkhead như thế nào?
4. Vì sao async/streaming RPC phải giữ permit đến terminal callback?
5. Vì sao không nên retry ngay khi bulkhead từ chối call?
6. Làm thế nào tính tổng concurrency khi ứng dụng chạy nhiều replica?

Bulkhead được đặt đúng phạm vi giúp Spring gRPC giữ capacity cho các operation quan trọng, giới hạn tác động dây chuyền khi một method tăng tải và từ chối quá tải trước khi nó làm cạn tài nguyên của toàn ứng dụng.

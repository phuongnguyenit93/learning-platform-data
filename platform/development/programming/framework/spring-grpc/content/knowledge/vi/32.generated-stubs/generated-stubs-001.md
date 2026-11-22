# BlockingStub và thread gọi

## 1. BlockingStub thực hiện RPC trên luồng gọi

Trong **SPRING_GRPC**, Protocol Buffers định nghĩa service và message; plugin sinh mã Java tạo stub để ứng dụng gọi các method gRPC. `BlockingStub` là biến thể đồng bộ: khi gọi method, luồng đang gọi chờ kết quả RPC hoặc lỗi rồi mới tiếp tục thực thi.

Ví dụ:

~~~java
GetOrderReply reply = ordersBlockingStub.getOrder(
        GetOrderRequest.newBuilder()
                .setOrderId("ORD-42")
                .build());

// Dòng này chỉ chạy sau khi RPC kết thúc thành công
return toView(reply);
~~~

Với unary RPC, method trả về một response duy nhất. Trong lúc chờ server, caller bị block. `BlockingStub` không tự tạo một thread riêng cho mỗi lời gọi và cũng không biến RPC thành tác vụ nền. Transport vẫn xử lý I/O trên các thread nội bộ của gRPC, còn thread gọi chờ kết quả.

Điểm này quyết định nơi có thể gọi `BlockingStub`: dùng nó trên một thread được phép chờ; tránh gọi trực tiếp trên event loop hoặc thread cần tiếp tục xử lý nhiều sự kiện khác.

## 2. Các loại RPC được hỗ trợ bởi BlockingStub

Trong gRPC Java, generated blocking stub thường cung cấp:

| Kiểu RPC | Cách gọi từ BlockingStub | Hành vi của caller |
|---|---|---|
| Unary | Gọi method và nhận một response | Chờ đến response hoặc lỗi |
| Server streaming | Gọi method và nhận `Iterator<Response>` | Lặp iterator; thao tác lấy phần tử có thể chờ message tiếp theo |
| Client streaming | Không có API blocking tương ứng trong generated stub thông thường | Dùng `AsyncStub` và `StreamObserver` |
| Bidirectional streaming | Không có API blocking tương ứng trong generated stub thông thường | Dùng `AsyncStub` và `StreamObserver` |

Ví dụ server-streaming:

~~~java
Iterator<ProgressEvent> events =
        ordersBlockingStub
                .withDeadlineAfter(30, TimeUnit.SECONDS)
                .watchOrder(
                        WatchOrderRequest.newBuilder()
                                .setOrderId("ORD-42")
                                .build());

while (events.hasNext()) {
    ProgressEvent event = events.next();
    process(event);
}
~~~

Lời gọi `watchOrder(...)` trả về iterator, nhưng việc đọc iterator vẫn là thao tác blocking. `hasNext()` có thể phải chờ server gửi event tiếp theo hoặc kết thúc stream. Nếu server giữ stream mở lâu, thread đang lặp cũng có thể bị giữ lâu.

Không nhầm việc nhận được `Iterator` với việc RPC đã hoàn tất. Với server streaming, RPC chỉ kết thúc khi server đóng stream, client hủy call hoặc deadline/cancellation kết thúc lời gọi.

## 3. BlockingStub và AsyncStub khác nhau ở mô hình thực thi

Generated gRPC Java thường cung cấp các biến thể stub:

- **BlockingStub:** API đồng bộ cho unary và server-streaming; caller chờ kết quả.
- **FutureStub:** API future cho các method unary; caller nhận future và có thể chờ hoặc kết hợp với luồng xử lý khác.
- **AsyncStub:** API bất đồng bộ dùng callback/`StreamObserver`; phù hợp cho client-streaming, bidirectional streaming và tích hợp event-driven.

Ví dụ tạo các stub từ cùng một channel:

~~~java
OrdersGrpc.OrdersBlockingStub blocking =
        OrdersGrpc.newBlockingStub(channel);

OrdersGrpc.OrdersFutureStub future =
        OrdersGrpc.newFutureStub(channel);

OrdersGrpc.OrdersStub async =
        OrdersGrpc.newStub(channel);
~~~

Các stub dùng chung channel, nhưng khác API và cách ứng dụng nhận kết quả. Chọn stub theo mô hình thread của tầng gọi. Không chọn `BlockingStub` chỉ vì code tuyến tính dễ đọc nếu caller đang chạy trên event loop.

## 4. Thread nào phù hợp để gọi BlockingStub?

Một lời gọi blocking giữ thread cho tới khi RPC kết thúc. Vì vậy cần xem thread đó có thể chờ hay không:

| Nơi gọi | Mức độ phù hợp | Lý do |
|---|---|---|
| Spring MVC servlet request thread | Có thể phù hợp | Mô hình request/response vốn đồng bộ; cần giới hạn thời gian và đủ thread phục vụ |
| Dedicated bounded executor | Phù hợp | Có thể kiểm soát concurrency, queue và rejection |
| Java virtual thread | Có thể phù hợp nếu runtime/phiên bản hỗ trợ | Giảm chi phí thread chờ, nhưng không tăng năng lực backend hoặc giới hạn RPC |
| WebFlux/Netty event loop | Không phù hợp | Block event loop sẽ làm chậm nhiều request khác trên cùng loop |
| gRPC server callback/event loop | Không phù hợp | Có thể chiếm thread cần xử lý I/O và callback |
| ForkJoin common pool | Thường không nên dùng mặc định | Blocking có thể làm thiếu worker cho các tác vụ khác |

Trong Spring MVC, một RPC đồng bộ có thể giữ servlet thread trong suốt thời gian gọi. Đây là lựa chọn đơn giản nếu thời gian RPC được giới hạn, số request đồng thời nằm trong năng lực pool và ứng dụng chấp nhận mô hình chờ.

Với Spring WebFlux, không gọi `BlockingStub` trực tiếp trong controller đang chạy trên event loop. Dùng `AsyncStub`/`FutureStub` để tích hợp bất đồng bộ, hoặc chuyển tác vụ blocking sang executor chuyên dụng có giới hạn nếu chưa thể thay đổi API.

## 5. Tích hợp BlockingStub trong Spring

`ManagedChannel` nên được quản lý như tài nguyên dài hạn của ứng dụng. Tạo channel và stub một lần, sau đó inject vào service:

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
                .useTransportSecurity()
                .build();
    }

    @Bean
    OrdersGrpc.OrdersBlockingStub ordersBlockingStub(
            ManagedChannel ordersChannel) {
        return OrdersGrpc.newBlockingStub(ordersChannel);
    }
}
~~~

Service gọi stub:

~~~java
import org.springframework.stereotype.Service;
import java.util.concurrent.TimeUnit;

@Service
public class OrdersFacade {
    private final OrdersGrpc.OrdersBlockingStub orders;

    public OrdersFacade(OrdersGrpc.OrdersBlockingStub orders) {
        this.orders = orders;
    }

    public GetOrderReply getOrder(String orderId) {
        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId(orderId)
                .build();

        return orders
                .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                .getOrder(request);
    }
}
~~~

Stub được sinh từ cùng channel có thể được dùng lại đồng thời. Các stub gRPC Java là immutable và thread-safe; những phương thức như `withDeadlineAfter(...)` trả về một stub mới với `CallOptions` được điều chỉnh, không sửa stub dùng chung ban đầu. Điều này cho phép service giữ một stub nền và tạo biến thể theo deadline của từng request.

Không tạo channel hoặc stub transport mới cho mỗi RPC. Việc đó làm tăng số kết nối, TLS handshake, tài nguyên và chi phí discovery.

## 6. Deadline là giới hạn cho thời gian thread phải chờ

Blocking call không nên chờ vô hạn. Đặt deadline theo ngân sách của nghiệp vụ:

~~~java
GetOrderReply reply = orders
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getOrder(request);
~~~

Deadline áp dụng cho toàn bộ RPC, gồm thời gian chờ kết nối, xử lý ở server và truyền response. Khi hết deadline, caller nhận lỗi như `DEADLINE_EXCEEDED`; thread được giải phóng khi lời gọi kết thúc.

Nếu service gọi nối tiếp nhiều dependency, phải chia ngân sách tổng. Ví dụ HTTP request có 2 giây không nên cấp 2 giây cho từng RPC tuần tự. Có thể truyền phần thời gian còn lại hoặc đặt deadline ngắn hơn cho từng bước để còn thời gian tổng hợp response.

`withWaitForReady()` có thể khiến call chờ channel có backend sẵn sàng, nhưng deadline vẫn giới hạn tổng thời gian. Không dùng wait-for-ready mà không có deadline cho request có SLA rõ ràng.

## 7. Xử lý lỗi và interruption

Các lỗi RPC thường được ném dưới dạng `StatusRuntimeException`. Với blocking call, xử lý status ở ranh giới service để ánh xạ sang lỗi ứng dụng phù hợp:

~~~java
try {
    return orders
            .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
            .getOrder(request);
} catch (StatusRuntimeException ex) {
    Status.Code code = ex.getStatus().getCode();

    if (code == Status.Code.DEADLINE_EXCEEDED) {
        throw new OrderLookupTimeoutException(ex);
    }
    if (code == Status.Code.UNAVAILABLE) {
        throw new OrdersServiceUnavailableException(ex);
    }
    throw ex;
}
~~~

Không retry mọi lỗi chỉ vì call đang blocking. `INVALID_ARGUMENT`, `PERMISSION_DENIED` hoặc `NOT_FOUND` thường cần xử lý theo nghiệp vụ. Retry chỉ phù hợp khi status được cho phép, logical RPC chưa commit và thao tác có thể thực hiện lại an toàn.

Khi thread bị interrupt, coi đó là tín hiệu hủy công việc. Giữ nguyên interrupt flag nếu bắt `InterruptedException` ở tầng executor hoặc orchestration:

~~~java
try {
    return performBlockingWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new RequestCancelledException(ex);
}
~~~

Các blocking API của gRPC Java có thể biểu diễn interruption/cancellation dưới dạng `StatusRuntimeException` tùy đường gọi. Không nuốt interruption rồi tiếp tục xử lý như thể request vẫn còn hiệu lực.

## 8. Giới hạn concurrency của thread gọi

Nếu mỗi RPC đồng bộ giữ một thread, số RPC đồng thời bị giới hạn bởi khả năng của executor hoặc request thread pool. Ví dụ một pool có 40 worker thì tối đa khoảng 40 tác vụ blocking có thể chạy đồng thời trong pool đó; các tác vụ khác phải chờ queue hoặc bị từ chối.

~~~text
HTTP requests
     |
     v
Bounded executor (40 workers)
     |
     +--> worker 1 --> BlockingStub RPC
     +--> worker 2 --> BlockingStub RPC
     +--> ...
     +--> worker 40 -> BlockingStub RPC
     |
     +--> queue có giới hạn
~~~

Thiết kế pool cần dựa trên latency RPC, concurrency dự kiến, giới hạn upstream và thời gian chờ tối đa. Queue không giới hạn có thể biến overload thành độ trễ tăng dần và giữ request quá lâu. Rejection cần được xử lý rõ ràng, ví dụ trả lỗi quá tải thay vì xếp hàng vô hạn.

Đừng tăng thread pool một cách máy móc để xử lý backend chậm. Điều đó có thể làm số RPC đồng thời vượt quá năng lực server, database hoặc connection limit. Kết hợp deadline, admission control, bulkhead và giới hạn concurrency theo dependency.

## 9. Chuyển blocking work sang executor riêng

Nếu một tầng cần API trả về ngay nhưng phía dưới chỉ có blocking client, có thể chạy RPC trên executor riêng:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

@Service
public class AsyncOrdersFacade {
    private final OrdersGrpc.OrdersBlockingStub orders;

    public AsyncOrdersFacade(OrdersGrpc.OrdersBlockingStub orders) {
        this.orders = orders;
    }

    @Async("grpcBlockingExecutor")
    public CompletableFuture<GetOrderReply> getOrder(String orderId) {
        GetOrderReply reply = orders
                .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                .getOrder(GetOrderRequest.newBuilder()
                        .setOrderId(orderId)
                        .build());
        return CompletableFuture.completedFuture(reply);
    }
}
~~~

Executor `grpcBlockingExecutor` cần được khai báo với số worker và queue có giới hạn. `@Async` chỉ chuyển việc thực thi sang executor; nó không làm bản thân `BlockingStub` trở thành non-blocking. Worker của executor vẫn bị giữ trong thời gian RPC.

Không dùng `CompletableFuture.supplyAsync(...)` mặc định nếu tác vụ có thể block lâu, vì nó có thể chiếm common pool dùng chung cho các tác vụ khác. Truyền executor được quản lý rõ ràng.

## 10. Virtual threads không thay thế giới hạn tài nguyên

Java virtual threads có thể giảm chi phí tạo và chờ thread so với platform thread trong nhiều workload blocking. Nếu dùng chúng để gọi `BlockingStub`, cần kiểm tra phiên bản Java, gRPC transport và hành vi thực tế trong môi trường triển khai.

Virtual thread không làm server xử lý vô hạn RPC đồng thời. Mỗi call vẫn tiêu thụ tài nguyên ở client, transport, proxy, server và dependency. Vẫn cần deadline, giới hạn số call in-flight, backpressure và quota. Nếu bỏ giới hạn chỉ vì tạo thread rẻ hơn, hệ thống có thể đẩy overload xuống backend.

## 11. Server streaming giữ thread trong suốt lúc đọc iterator

Với server streaming, thread gọi có thể bị block ở `hasNext()` khi đang đợi event tiếp theo:

~~~java
Iterator<ProgressEvent> stream = orders
        .withDeadlineAfter(60, TimeUnit.SECONDS)
        .watchOrder(request);

while (stream.hasNext()) {
    ProgressEvent event = stream.next();
    handle(event);
}
~~~

Nếu event đến chậm, thread vẫn bị giữ trong lúc chờ. Nếu stream kéo dài nhiều phút và có hàng nghìn client, số thread blocking có thể trở thành giới hạn chính. Khi cần nhiều stream đồng thời, cân nhắc `AsyncStub` và xử lý `StreamObserver` trên executor/event loop phù hợp.

Consumer cũng phải xử lý tốc độ nhận dữ liệu. Nếu `handle(event)` chậm, việc đọc iterator chậm lại; flow control của gRPC giúp điều tiết dữ liệu, nhưng ứng dụng vẫn cần giới hạn buffer và xử lý lỗi consumer.

Với stream có thể kéo dài lâu, thiết kế cursor/checkpoint để client reconnect/resume khi deadline, network hoặc server kết thúc stream. Không giả định blocking iterator sẽ tự chuyển sang backend khác khi instance dừng.

## 12. Khi nào nên chuyển sang AsyncStub?

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Spring MVC đồng bộ, số request có giới hạn, latency có deadline | `BlockingStub` |
| WebFlux hoặc Netty event loop | `AsyncStub` hoặc `FutureStub` |
| Client-streaming/bidirectional streaming | `AsyncStub` |
| Nhiều server stream đồng thời, thời gian sống dài | Thường nên dùng `AsyncStub` |
| Tác vụ nền đồng bộ, có executor giới hạn | `BlockingStub` trên executor chuyên dụng |
| Muốn kết hợp unary với `CompletableFuture` | `FutureStub` hoặc adapter bất đồng bộ |

Không phải cứ dùng async là tự động backpressure đúng. `AsyncStub` vẫn cần quản lý callback, request demand, cancellation và executor. Chọn mô hình sao cho thread đang chạy không bị block ngoài ý muốn.

## 13. Kiểm thử và quan sát thread gọi

Test nên xác minh cả kết quả RPC và cách thread được sử dụng:

| Tình huống | Điều cần xác minh |
|---|---|
| Unary thành công | Caller chỉ tiếp tục sau response |
| Server trả gRPC error | `StatusRuntimeException` được ánh xạ đúng |
| Deadline hết | Call kết thúc theo deadline và thread được giải phóng |
| Server streaming chưa gửi event | Iterator chờ; không chạy trên event loop |
| Stream kết thúc | Iterator kết thúc bình thường |
| Thread bị interrupt | Cancellation/interruption được truyền và interrupt không bị nuốt |
| Executor hết worker/queue | Rejection hoặc overload được xử lý rõ |
| Nhiều RPC đồng thời | Concurrency không vượt giới hạn thiết kế |
| WebFlux controller | Không block Netty event loop |
| Spring shutdown | Channel và executor được đóng theo lifecycle |

Quan sát:

- Số thread đang chạy blocking RPC và số thread chờ trong queue.
- Số RPC in-flight, latency và deadline exceeded.
- Thời gian chờ executor và số lần rejection.
- Số stream mở, tuổi stream và tốc độ event.
- Status code, cancellation và interruption.
- Tỷ lệ thread pool saturation khi upstream chậm.

Nếu latency RPC tăng nhưng CPU client thấp, có thể nhiều thread đang chờ I/O. Nếu servlet pool hoặc executor cạn, kiểm tra số call in-flight, deadline, queue và độ trễ backend thay vì chỉ tăng số thread.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gọi `BlockingStub` trên Netty event loop | Chặn xử lý nhiều request khác | Dùng async API hoặc executor blocking riêng |
| Nghĩ BlockingStub tự tạo thread nền | Caller bị block ngoài dự tính | Gọi từ thread được phép chờ |
| Không đặt deadline | Thread có thể bị giữ quá lâu | Đặt deadline theo ngân sách request |
| Dùng một pool không giới hạn | Queue tăng và overload lan truyền | Bounded executor, rejection và admission control |
| Dùng common pool cho RPC blocking | Starvation các tác vụ dùng chung pool | Executor chuyên dụng |
| Chia sẻ session-specific stub/interceptor có mutable state | Dữ liệu giữa các request có thể lẫn nhau | Stub immutable; giữ dữ liệu từng call ở phạm vi call |
| Dùng blocking iterator cho hàng nghìn stream dài | Cạn thread | Cân nhắc AsyncStub và flow control |
| Bắt lỗi rồi bỏ qua interrupt | Request đã hủy vẫn tiếp tục tiêu thụ tài nguyên | Bảo toàn interruption/cancellation |

**Ghi nhớ:** `BlockingStub` thực hiện unary hoặc server-streaming RPC theo mô hình đồng bộ; thread gọi chờ response hoặc message tiếp theo của iterator. Dùng nó trên servlet thread hoặc executor có giới hạn khi mô hình ứng dụng cho phép chờ; tránh event loop của WebFlux/Netty. Tái sử dụng channel/stub thread-safe, đặt deadline cho từng RPC, giới hạn concurrency và chuyển sang `AsyncStub` khi cần client/bidirectional streaming hoặc nhiều stream đồng thời. `@Async` chỉ đổi executor, không biến lời gọi blocking thành non-blocking.

# FutureStub và ListenableFuture

## 1. FutureStub trả kết quả bất đồng bộ cho unary RPC

Trong **SPRING_GRPC**, Protocol Buffers định nghĩa service và message; plugin gRPC Java sinh các stub để ứng dụng gọi method từ hợp đồng đó. `FutureStub` là biến thể client dành cho unary RPC: thay vì chờ response ngay trong method gọi, nó trả về một `ListenableFuture<Response>` đại diện cho kết quả sẽ hoàn tất sau.

Ví dụ:

~~~java
ListenableFuture<GetOrderReply> result =
        ordersFutureStub.getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("ORD-42")
                        .build());
~~~

Khi `getOrder(...)` trả về, RPC có thể vẫn đang chạy. Ứng dụng có thể đăng ký callback, kết hợp future với một bước xử lý khác hoặc chờ kết quả ở một thread được phép block.

`FutureStub` không tạo một thread ứng dụng riêng cho mỗi RPC và cũng không có nghĩa toàn bộ code phía sau tự động bất đồng bộ. Nó cung cấp một handle để theo dõi kết quả. Nếu gọi `result.get()` ngay sau khi tạo future, thread hiện tại vẫn block và lợi ích của API bất đồng bộ bị mất.

## 2. ListenableFuture bổ sung listener cho Future

`ListenableFuture` thuộc Guava (`com.google.common.util.concurrent`) và mở rộng mô hình `Future` của Java bằng khả năng đăng ký listener:

- `isDone()` kiểm tra future đã hoàn tất hay chưa.
- `isCancelled()` kiểm tra future đã bị hủy hay chưa.
- `get()` chờ kết quả; có thể ném `InterruptedException` hoặc `ExecutionException`.
- `get(timeout, unit)` chỉ chờ trong khoảng thời gian giới hạn ở phía caller.
- `addListener(listener, executor)` đăng ký công việc chạy khi future hoàn tất.

Điểm quan trọng là listener cần một `Executor`. Executor quyết định callback chạy ở đâu. Nếu dùng `MoreExecutors.directExecutor()`, listener có thể chạy ngay trên thread hoàn tất future; callback nặng hoặc block có thể làm chậm thread đó. Với xử lý đáng kể, hãy dùng executor riêng có giới hạn.

`ListenableFuture` vẫn là một Future: gọi `get()` vẫn có thể block. Khả năng bất đồng bộ đến từ cách đăng ký listener và phối hợp kết quả, không phải từ tên kiểu dữ liệu.

## 3. FutureStub chỉ dành cho unary method

Generated gRPC Java thường tạo ba biến thể stub:

| Stub | API điển hình | Loại RPC |
|---|---|---|
| `BlockingStub` | Trả response trực tiếp hoặc `Iterator<Response>` | Unary và server streaming |
| `FutureStub` | Trả `ListenableFuture<Response>` | Unary |
| `AsyncStub` | Dùng callback/`StreamObserver` | Unary, server streaming, client streaming và bidirectional streaming |

`FutureStub` không cung cấp API `ListenableFuture` cho client-streaming hoặc bidirectional-streaming vì các RPC này có nhiều message theo hai chiều. Với server streaming, response là một chuỗi message thay vì một giá trị duy nhất; dùng `BlockingStub` nếu chấp nhận iterator blocking hoặc `AsyncStub` nếu cần xử lý bất đồng bộ.

Ví dụ tạo các stub từ cùng một channel:

~~~java
OrdersGrpc.OrdersBlockingStub blocking =
        OrdersGrpc.newBlockingStub(channel);

OrdersGrpc.OrdersFutureStub future =
        OrdersGrpc.newFutureStub(channel);

OrdersGrpc.OrdersStub async =
        OrdersGrpc.newStub(channel);
~~~

Các stub có thể dùng chung channel. Chọn loại stub theo kiểu RPC và mô hình thread của nơi gọi.

## 4. Đăng ký callback thay vì gọi get ngay

`Futures.addCallback` của Guava giúp xử lý thành công và thất bại tại một nơi:

~~~java
import com.google.common.util.concurrent.FutureCallback;
import com.google.common.util.concurrent.Futures;
import com.google.common.util.concurrent.ListenableFuture;
import io.grpc.Status;

ListenableFuture<GetOrderReply> result =
        ordersFutureStub.getOrder(request);

Futures.addCallback(
        result,
        new FutureCallback<GetOrderReply>() {
            @Override
            public void onSuccess(GetOrderReply reply) {
                publishOrder(reply);
            }

            @Override
            public void onFailure(Throwable failure) {
                Status status = Status.fromThrowable(failure);
                recordFailure(status.getCode(), failure);
            }
        },
        callbackExecutor
);
~~~

`onSuccess` nhận response khi unary RPC hoàn tất thành công. `onFailure` nhận lỗi transport, status gRPC hoặc lỗi hoàn tất khác. Dùng `Status.fromThrowable(...)` để trích xuất status khi lỗi có nguồn gốc từ gRPC; vẫn cần xử lý cancellation hoặc exception ứng dụng theo ngữ cảnh.

Callback không nên thực hiện công việc blocking dài như gọi một service khác bằng `BlockingStub`, truy vấn database đồng bộ hoặc chờ một future khác. Nếu cần bước tiếp theo, hãy compose future hoặc chuyển tác vụ sang executor phù hợp.

## 5. Executor quyết định nơi callback chạy

Không nên mặc định chạy callback nặng trên thread hoàn tất RPC. Trong Spring, inject một executor chuyên dụng có concurrency và queue giới hạn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;

@Configuration
public class GrpcCallbackConfiguration {

    @Bean
    Executor grpcCallbackExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("grpc-callback-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.initialize();
        return executor;
    }
}
~~~

Các con số chỉ là ví dụ; chọn theo latency callback, số RPC đồng thời và năng lực downstream. Queue vô hạn có thể tích tụ kết quả khi callback xử lý chậm. Chính sách rejection cũng cần được quyết định rõ: log/đếm, từ chối tác vụ hoặc chuyển sang cơ chế backpressure phù hợp.

Không dùng event loop của WebFlux/Netty làm executor cho callback có thể block. Nếu callback chỉ cập nhật một trạng thái rất nhỏ, direct executor có thể phù hợp, nhưng phải bảo đảm callback không giữ thread hoàn tất RPC quá lâu.

## 6. Tích hợp FutureStub trong Spring

Channel và stub nên được tạo một lần, quản lý theo lifecycle ứng dụng:

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
    OrdersGrpc.OrdersFutureStub ordersFutureStub(
            ManagedChannel ordersChannel) {
        return OrdersGrpc.newFutureStub(ordersChannel);
    }
}
~~~

Service có thể trả `ListenableFuture` cho tầng gọi:

~~~java
import com.google.common.util.concurrent.ListenableFuture;
import org.springframework.stereotype.Service;
import java.util.concurrent.TimeUnit;

@Service
public class OrdersQueryService {
    private final OrdersGrpc.OrdersFutureStub orders;

    public OrdersQueryService(OrdersGrpc.OrdersFutureStub orders) {
        this.orders = orders;
    }

    public ListenableFuture<GetOrderReply> getOrder(String orderId) {
        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId(orderId)
                .build();

        return orders
                .withDeadlineAfter(700, TimeUnit.MILLISECONDS)
                .getOrder(request);
    }
}
~~~

`FutureStub` là immutable và thread-safe; các method cấu hình như `withDeadlineAfter(...)` trả về stub mới với `CallOptions` tương ứng. Có thể dùng chung stub bean cho nhiều request đồng thời. Future được trả về là đối tượng riêng của từng RPC; không lưu một future đang chạy vào field singleton dùng chung cho mọi caller.

Không cần bọc lời gọi `FutureStub` trong `@Async` chỉ để biến nó thành bất đồng bộ: method gRPC đã trả future. `@Async` có thể hữu ích cho orchestration khác, nhưng nếu chỉ gọi stub rồi trả future, nó thêm một tầng executor không cần thiết.

## 7. Kết hợp nhiều bước bằng Futures

Guava cung cấp các hàm biến đổi future để xây dựng pipeline mà không gọi `get()` ở giữa:

~~~java
ListenableFuture<GetOrderReply> orderFuture =
        ordersFutureStub.getOrder(request);

ListenableFuture<OrderView> viewFuture =
        Futures.transform(
                orderFuture,
                reply -> toView(reply),
                callbackExecutor);
~~~

`Futures.transform` chạy hàm chuyển đổi trên executor được chỉ định sau khi future nguồn thành công. Nếu cần bước tiếp theo cũng trả về `ListenableFuture`, dùng `Futures.transformAsync` để nối future mà không block thread chờ kết quả.

Một số lưu ý:

- Hàm transform nên ngắn và không block.
- Nếu transform cần I/O blocking, chuyển sang executor dành riêng cho blocking work.
- Lỗi từ future nguồn sẽ được truyền sang future kết quả.
- Hủy future kết quả và hành vi lan truyền cancellation cần được kiểm tra theo cách compose đang dùng.
- Không tạo chuỗi callback lồng sâu khó quan sát; đặt tên bước và trace/correlation ID rõ ràng.

## 8. Deadline của RPC khác timeout khi gọi get

Có hai loại thời gian chờ thường bị nhầm:

| Cơ chế | Giới hạn điều gì? | Khi hết thời gian |
|---|---|---|
| `withDeadlineAfter(...)` trên stub | Tổng thời gian RPC ở gRPC | RPC hết hạn; server nhận tín hiệu deadline/cancellation theo transport |
| `future.get(timeout, unit)` | Thời gian thread hiện tại chờ future | Caller nhận `TimeoutException`; RPC có thể vẫn tiếp tục |

Ví dụ đặt deadline cho RPC:

~~~java
ListenableFuture<GetOrderReply> result = ordersFutureStub
        .withDeadlineAfter(700, TimeUnit.MILLISECONDS)
        .getOrder(request);
~~~

Nếu caller chỉ chờ tối đa 200 ms:

~~~java
try {
    GetOrderReply reply = result.get(200, TimeUnit.MILLISECONDS);
    return toView(reply);
} catch (TimeoutException ex) {
    // Local wait hết hạn; RPC có thể vẫn đang chạy.
    result.cancel(true);
    throw new OrderLookupTimeoutException(ex);
}
~~~

`get(timeout, unit)` không tự thay đổi deadline của gRPC call. Nếu caller không còn cần kết quả sau timeout cục bộ, gọi `cancel(...)` để hủy future/RPC. Nếu RPC vẫn có ích cho tác vụ nền, có thể tiếp tục theo dõi future ở một thành phần khác, nhưng phải có giới hạn thời gian và quản lý lifecycle rõ ràng.

## 9. Cancellation và interruption

`ListenableFuture` hỗ trợ `cancel(...)`. Với future do gRPC `FutureStub` trả về, hủy future sẽ yêu cầu hủy RPC tương ứng. Server có thể nhận cancellation qua context, nhưng phải kiểm tra cancellation và dừng công việc hợp tác; không thể giả định mọi side effect đã bắt đầu đều tự rollback.

~~~java
ListenableFuture<GetOrderReply> result =
        ordersFutureStub.getOrder(request);

if (requestNoLongerNeeded()) {
    result.cancel(true);
}
~~~

Tham số `mayInterruptIfRunning` thuộc hợp đồng `Future`; không nên hiểu nó là bảo đảm gRPC sẽ cưỡng bức interrupt mọi thread server đang xử lý. Cancellation là tín hiệu hủy RPC. Server cần thiết kế xử lý cancellation để dừng truy vấn, giải phóng tài nguyên hoặc ngừng phát message.

Nếu dùng `get()` và thread caller bị interrupt, `get()` ném `InterruptedException`. Khôi phục interrupt flag khi xử lý ở tầng phù hợp:

~~~java
try {
    return result.get();
} catch (InterruptedException ex) {
    result.cancel(true);
    Thread.currentThread().interrupt();
    throw new RequestCancelledException(ex);
}
~~~

Không nuốt interruption rồi tiếp tục chờ hoặc thực hiện side effect khi request đã bị hủy.

## 10. Xử lý lỗi từ ListenableFuture

Khi gọi `get()`, lỗi RPC thường được bọc trong `ExecutionException`; nguyên nhân bên trong thường là `StatusRuntimeException`. Có thể phân loại:

~~~java
try {
    return result.get();
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    Status status = Status.fromThrowable(cause);

    if (status.getCode() == Status.Code.NOT_FOUND) {
        throw new OrderNotFoundException(cause);
    }
    if (status.getCode() == Status.Code.UNAVAILABLE) {
        throw new OrdersServiceUnavailableException(cause);
    }
    throw new OrderQueryException(cause);
}
~~~

Khi dùng callback, xử lý lỗi trong `onFailure`. Phân biệt ít nhất:

- `StatusRuntimeException`: RPC kết thúc với gRPC status.
- `CancellationException`: future bị hủy.
- Lỗi ứng dụng trong transform/callback: logic xử lý kết quả thất bại.
- `TimeoutException`: chỉ xuất hiện từ timed `get()` khi caller hết thời gian chờ cục bộ.

Không retry mọi lỗi. `INVALID_ARGUMENT`, `PERMISSION_DENIED` và `NOT_FOUND` thường cần xử lý nghiệp vụ. Retry phải theo status policy, deadline và tính idempotent của operation.

## 11. Thread safety và trạng thái theo từng request

Generated stub là immutable/thread-safe và có thể chia sẻ. Ngược lại, request, future và dữ liệu callback thuộc từng lời gọi:

~~~text
OrdersFutureStub dùng chung
   |
   +--> RPC A -> Future A -> callback A
   |
   +--> RPC B -> Future B -> callback B
   |
   +--> RPC C -> Future C -> callback C
~~~

Không lưu `currentRequest`, `currentFuture` hoặc biến mutable dùng chung trong singleton service để ghép response về đúng caller. Dùng biến local, immutable context hoặc correlation ID theo từng RPC.

Nếu callback cần context của Spring Security, tracing hoặc MDC, phải truyền/khôi phục context có chủ đích khi chuyển executor. Thread pool không tự bảo đảm các thread callback có cùng ThreadLocal context với thread khởi tạo RPC.

## 12. Giới hạn concurrency và backpressure

Future API giảm việc giữ thread chờ kết quả, nhưng không làm backend xử lý vô hạn RPC. Mỗi RPC vẫn tiêu thụ tài nguyên ở client, channel, network, proxy, server và dependency. Nếu caller phát sinh future nhanh hơn tốc độ hoàn tất, số RPC in-flight có thể tăng liên tục.

Cần có:

- Giới hạn số RPC đang chạy theo service hoặc tenant.
- Bounded queue cho công việc callback.
- Admission control khi hệ thống đạt ngưỡng.
- Deadline và cancellation khi kết quả không còn cần thiết.
- Giới hạn concurrency đến database/downstream ở server.
- Metrics cho số future pending và tuổi của future lâu nhất.

Không dùng `ListenableFuture` như một hàng đợi không giới hạn. Future chỉ biểu diễn kết quả đang chờ; nó không tự tạo backpressure cho phía phát request.

## 13. Kiểm thử FutureStub và callback

Test nên xác minh kết quả, executor và vòng đời RPC:

| Tình huống | Điều cần xác minh |
|---|---|
| Unary thành công | Future hoàn tất với đúng response |
| Server trả status lỗi | `onFailure` nhận lỗi và status được phân loại đúng |
| Đăng ký listener sau khi future đã hoàn tất | Listener vẫn được thực thi theo executor |
| Callback chạy trên executor riêng | Thread callback đúng pool, không chạy trên event loop |
| `get(timeout)` hết hạn | Caller nhận `TimeoutException`; RPC chỉ dừng nếu được cancel hoặc deadline hết |
| `cancel(true)` | Future chuyển sang cancelled và RPC nhận tín hiệu hủy |
| Caller bị interrupt khi `get()` | Interrupt được bảo toàn và call được xử lý theo chính sách |
| Transform thất bại | Future kết quả hoàn tất lỗi |
| Callback executor đầy | Rejection được quan sát và xử lý |
| Nhiều RPC đồng thời | Response/callback không lẫn request |
| WebFlux event loop | Không có thao tác `get()` blocking trên event loop |
| Spring shutdown | Channel và executor được đóng theo lifecycle |

Không chỉ kiểm tra `future.isDone()`. Hãy kiểm tra callback có chạy đúng executor, cancellation có tới server và tài nguyên có được giải phóng khi request không còn cần kết quả.

## 14. Metrics và chẩn đoán

Theo dõi:

- Số RPC đang pending và thời gian pending.
- Latency từ lúc tạo future đến khi hoàn tất.
- Số future thành công, thất bại và bị cancel.
- Số callback đang chạy, queue depth và rejection.
- Số `TimeoutException` từ local wait so với `DEADLINE_EXCEEDED` từ RPC.
- Số lỗi theo gRPC status code.
- Số transform/compose thất bại.
- Số RPC còn in-flight khi Spring context shutdown.

Nếu future hoàn tất nhưng callback không chạy, kiểm tra executor bị shutdown, queue/rejection và cách đăng ký listener. Nếu caller vẫn block, tìm `get()`/`join()` trên đường xử lý và xác định thread đó có được phép chờ hay không.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gọi `get()` ngay sau khi nhận future | Thread caller vẫn block | Đăng ký listener hoặc compose future |
| Nghĩ `FutureStub` hỗ trợ mọi kiểu streaming | Không có API phù hợp cho client/bidirectional streaming | Dùng `AsyncStub` cho streaming |
| Dùng `directExecutor` cho callback nặng | Chặn thread hoàn tất RPC | Dùng executor chuyên dụng có giới hạn |
| Nhầm timed `get()` với gRPC deadline | RPC vẫn chạy sau khi caller timeout | Đặt deadline trên stub và cancel nếu không còn cần |
| Không xử lý cancellation | RPC và công việc downstream tiếp tục tiêu tốn tài nguyên | Truyền cancellation và kiểm tra ở server |
| Lưu future mutable trong singleton field | Lẫn kết quả giữa các request | Dùng future riêng theo lời gọi |
| Callback block để gọi service khác | Starvation callback executor | Compose future hoặc dùng executor phù hợp |
| Không giới hạn RPC pending | Tăng bộ nhớ và tải downstream | Admission control, concurrency limit và deadline |

**Ghi nhớ:** `FutureStub` cung cấp API unary bất đồng bộ bằng `ListenableFuture`; future cho phép đăng ký listener và compose kết quả mà không block thread gọi. `get()` vẫn block, còn `get(timeout)` chỉ giới hạn thời gian chờ cục bộ; deadline gRPC phải được đặt trên stub. Dùng executor phù hợp cho callback, xử lý lỗi/cancellation rõ ràng, giới hạn RPC pending và chuyển sang `AsyncStub` cho client hoặc bidirectional streaming.

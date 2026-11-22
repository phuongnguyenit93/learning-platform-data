# Cancellable future và reactive bridge

## 1. Vì sao cần bridge có thể hủy?

Trong **Spring gRPC**, client có thể gọi RPC bằng generated stub bất đồng bộ, future stub hoặc một API reactive như Reactor `Mono`/`Flux`. Mỗi API biểu diễn kết quả theo cách khác nhau, nhưng đều cần giữ đúng vòng đời của một RPC: khi caller không còn quan tâm, request phải được hủy ở gRPC runtime và tài nguyên phía server cần được giải phóng khi có thể.

Một bridge chỉ chuyển response từ callback sang `Mono` nhưng bỏ qua cancellation sẽ tạo ra một lỗi vòng đời: subscriber đã timeout hoặc hủy subscription, trong khi RPC vẫn chạy và tiếp tục tiêu thụ kết nối, CPU, database connection hoặc subscription tới broker.

Một bridge đúng cần truyền tín hiệu theo cả hai chiều:

- **RPC hoàn tất/lỗi:** chuyển kết quả hoặc lỗi gRPC thành terminal signal của Future/Mono/Flux.
- **Caller hủy:** hủy Future hoặc gRPC call tương ứng.
- **Deadline hết:** gRPC kết thúc call; bridge chuyển status timeout tới caller.
- **Race condition:** xử lý trường hợp cancellation xảy ra trước khi bridge nhận được handle của call.

## 2. Các API gRPC Java và khả năng cancellation

gRPC Java cung cấp nhiều dạng stub:

| Stub/API | Kiểu kết quả | Cancellation |
| --- | --- | --- |
| Async stub | Callback qua `StreamObserver` | Dùng `ClientCallStreamObserver.cancel()` khi lấy được call handle |
| Blocking stub | Trả kết quả trực tiếp hoặc ném exception | Chặn thread gọi; dùng deadline để giới hạn thời gian. Không dùng blocking stub làm bridge cho reactive event loop |
| Future stub | `ListenableFuture<T>` cho unary RPC | `future.cancel(true)` hủy future và truyền cancellation tới gRPC call |
| Reactor bridge | `Mono<T>` hoặc `Flux<T>` | Khi subscriber cancel, bridge phải cancel Future hoặc gRPC call |

Generated **future stub chỉ hỗ trợ unary RPC**. Với server-streaming, client-streaming và bidirectional-streaming, dùng async stub và bridge từ callback/stream observer.

Không gọi `.get()` hoặc `.block()` trên event loop chỉ để biến một API bất đồng bộ thành đồng bộ. Điều đó có thể chặn thread xử lý reactive pipeline và làm giảm throughput.

## 3. Cancellation của gRPC Future

Với unary RPC, generated future stub trả về Guava `ListenableFuture`:

```java
ListenableFuture<GetItemResponse> future =
        catalogFutureStub
                .withDeadlineAfter(2, TimeUnit.SECONDS)
                .getItem(request);

// Khi caller không còn cần kết quả:
future.cancel(true);
```

Việc cancel future hủy call gRPC tương ứng. Tham số `true` không nên được hiểu là gRPC sẽ cưỡng bức dừng mọi đoạn code server đang chạy; nó yêu cầu hủy thao tác future/call. Server cần quan sát cancellation/deadline và tự dừng công việc có thể dừng.

Cancellation không phải rollback. Nếu server đã commit một thay đổi database trước khi nhận tín hiệu hủy, thay đổi đó vẫn có thể tồn tại. Với command có tác dụng phụ, cần idempotency và API tra cứu trạng thái để xử lý kết quả không xác định.

## 4. Chuyển ListenableFuture thành Reactor Mono

Reactor `Mono` biểu diễn tối đa một kết quả. Có thể bridge future stub bằng `Mono.create`; điểm quan trọng là đăng ký cancellation để hủy future.

Đặt hàm helper dưới đây trong một class Java; các import được liệt kê trong ví dụ.

```java
import com.google.common.util.concurrent.FutureCallback;
import com.google.common.util.concurrent.Futures;
import com.google.common.util.concurrent.ListenableFuture;
import com.google.common.util.concurrent.MoreExecutors;
import reactor.core.publisher.Mono;
import java.util.function.Supplier;
import java.util.concurrent.TimeUnit;

static <T> Mono<T> fromGrpcFuture(
        Supplier<ListenableFuture<T>> callFactory) {
    return Mono.defer(() -> {
        ListenableFuture<T> call = callFactory.get();
        return Mono.create(sink -> {
            // Đăng ký trước để cancellation từ downstream luôn được chuyển tiếp.
            sink.onCancel(() -> call.cancel(true));

            Futures.addCallback(call, new FutureCallback<>() {
                @Override
                public void onSuccess(T result) {
                    sink.success(result);
                }

                @Override
                public void onFailure(Throwable error) {
                    sink.error(error);
                }
            }, MoreExecutors.directExecutor());
        });
    });
}
```

Sử dụng:

```java
Mono<GetItemResponse> itemMono = fromGrpcFuture(
        () -> catalogFutureStub
                .withDeadlineAfter(2, TimeUnit.SECONDS)
                .getItem(request));
```

`Mono.defer()` bảo đảm RPC chỉ được tạo khi có subscriber. Nếu tạo `ListenableFuture` bên ngoài rồi mới truyền vào bridge, RPC có thể bắt đầu trước khi subscriber đăng ký; khi đó cancellation và thời điểm thực thi khó quản lý hơn.

Bridge giữ nguyên exception từ gRPC, thường là `StatusRuntimeException` hoặc lỗi cancellation. Tầng gọi có thể phân loại status bằng `Status.fromThrowable(error)`; không nên đổi mọi lỗi thành một exception chung làm mất mã trạng thái.

## 5. Chuyển async unary RPC thành Mono

Nếu dùng async stub, `ClientResponseObserver` cung cấp `beforeStart()` để lấy `ClientCallStreamObserver`. Đây là handle cần thiết để hủy call khi reactive subscriber cancel.

```java
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;
import reactor.core.publisher.Mono;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.TimeUnit;
import com.example.catalog.v1.GetItemRequest;
import com.example.catalog.v1.GetItemResponse;

// catalogAsyncStub là async stub được inject vào client component.
Mono<GetItemResponse> getItemReactive(GetItemRequest request) {
    return Mono.create(sink -> {
        AtomicReference<ClientCallStreamObserver<GetItemRequest>> callRef =
                new AtomicReference<>();
        AtomicBoolean cancelled = new AtomicBoolean();

        ClientResponseObserver<GetItemRequest, GetItemResponse> observer =
                new ClientResponseObserver<>() {
            @Override
            public void beforeStart(
                    ClientCallStreamObserver<GetItemRequest> call) {
                callRef.set(call);
                // Xử lý race: subscriber có thể cancel trước khi call handle tới.
                if (cancelled.get()) {
                    call.cancel("Reactive subscriber cancelled", null);
                }
            }

            @Override
            public void onNext(GetItemResponse response) {
                sink.success(response);
            }

            @Override
            public void onError(Throwable error) {
                sink.error(error);
            }

            @Override
            public void onCompleted() {
                // Unary response thường đã được phát trong onNext().
            }
        };

        sink.onCancel(() -> {
            cancelled.set(true);
            ClientCallStreamObserver<GetItemRequest> call = callRef.get();
            if (call != null) {
                call.cancel("Reactive subscriber cancelled", null);
            }
        });

        try {
            catalogAsyncStub.getItem(request, observer);
        } catch (RuntimeException error) {
            sink.error(error);
        }
    });
}
```

Hai nhánh xử lý race là cần thiết:

- Nếu subscriber cancel sau khi `beforeStart()` chạy, `callRef` đã có giá trị và cancellation hủy trực tiếp call.
- Nếu subscriber cancel trước khi `beforeStart()` chạy, cờ `cancelled` được đặt; khi handle xuất hiện, `beforeStart()` lập tức hủy call.

Đây là bridge unary. Với API production, nên bảo đảm callback chỉ phát terminal signal một lần, xử lý trường hợp server hoàn tất mà không phát response theo contract, và giữ nguyên status/trailer cần thiết cho tầng gọi.

## 6. Bridge server-streaming thành Flux

Server-streaming RPC phát nhiều response message, vì vậy kiểu reactive phù hợp là `Flux<T>`. Khi subscriber cancel, phải hủy gRPC call để server nhận cancellation:

```java
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;
import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BiConsumer;
import com.example.orders.v1.OrderEvent;

static <ReqT, RespT> Flux<RespT> toFlux(
        ReqT request,
        BiConsumer<ReqT, ClientResponseObserver<ReqT, RespT>> invoke) {
    return Flux.create(sink -> {
        AtomicReference<ClientCallStreamObserver<ReqT>> callRef =
                new AtomicReference<>();
        AtomicBoolean cancelled = new AtomicBoolean();

        ClientResponseObserver<ReqT, RespT> observer =
                new ClientResponseObserver<>() {
            @Override
            public void beforeStart(ClientCallStreamObserver<ReqT> call) {
                callRef.set(call);
                if (cancelled.get()) {
                    call.cancel("Flux subscriber cancelled", null);
                }
            }

            @Override
            public void onNext(RespT value) {
                if (!sink.isCancelled()) {
                    sink.next(value);
                }
            }

            @Override
            public void onError(Throwable error) {
                sink.error(error);
            }

            @Override
            public void onCompleted() {
                sink.complete();
            }
        };

        sink.onCancel(() -> {
            cancelled.set(true);
            ClientCallStreamObserver<ReqT> call = callRef.get();
            if (call != null) {
                call.cancel("Flux subscriber cancelled", null);
            }
        });

        try {
            invoke.accept(request, observer);
        } catch (RuntimeException error) {
            sink.error(error);
        }
    }, FluxSink.OverflowStrategy.BUFFER);
}
```

Ví dụ gọi:

```java
Flux<OrderEvent> events = toFlux(
        watchRequest,
        (request, observer) ->
                orderEventsAsyncStub.watch(request, observer));
```

Ví dụ dùng `BUFFER` để giữ message nếu producer nhanh hơn subscriber. Đây là buffer không giới hạn của bridge cơ bản; không dùng nguyên trạng cho stream dài hoặc nguồn có tốc độ cao. Production cần thiết kế backpressure rõ ràng: dùng manual inbound flow control của gRPC (`disableAutoRequestWithInitial`/ `request(n)`) để ánh xạ demand của Reactor sang số message được phép nhận, hoặc dùng queue có giới hạn và chính sách overflow cụ thể.

Không gọi `sink.next()` đồng thời từ nhiều producer thread nếu bridge không tuần tự hóa callback. gRPC response callback thông thường có thứ tự trong một call; nếu ứng dụng chuyển message qua executor riêng, cần giữ thứ tự và bảo vệ terminal signal.

## 7. Cancellation, deadline và timeout reactive

Cancellation và deadline có liên quan nhưng khác nhau:

| Cơ chế | Ai khởi tạo? | Ý nghĩa |
| --- | --- | --- |
| Caller cancellation | Người gọi hủy subscription/future/call | Caller không còn quan tâm kết quả |
| gRPC deadline | Caller đặt thời hạn, runtime theo dõi | RPC hết ngân sách thời gian |
| Reactor `timeout()` | Reactive pipeline | Pipeline phát timeout và hủy upstream subscription |
| Server cancellation signal | gRPC runtime báo cho server | Server biết call không còn hoạt động ở phía client |

Ví dụ:

```java
Mono<GetItemResponse> result = fromGrpcFuture(
        () -> catalogFutureStub
                .withDeadlineAfter(3, TimeUnit.SECONDS)
                .getItem(request))
        .timeout(Duration.ofSeconds(2));
```

Ở đây Reactor timeout 2 giây sẽ cancel subscription upstream; bridge chuyển cancellation tới future, rồi tới gRPC call. Deadline gRPC 3 giây là lớp bảo vệ bổ sung nếu call vẫn còn hoạt động vì một lỗi bridge hoặc caller không cancel đúng cách. Thông thường nên chọn một ngân sách thống nhất, tránh các timeout chồng chéo khó giải thích.

Nếu dùng `timeout()` với fallback, hãy nhớ timeout có thể chuyển sang fallback sau khi đã hủy RPC ban đầu. Fallback không chứng minh thao tác server chưa được thực hiện; với command ghi cần idempotency hoặc status lookup.

## 8. Server phải phản ứng với cancellation

Khi client cancel hoặc deadline hết, server có thể nhận tín hiệu cancellation. Với gRPC Java:

- Dùng `ServerCallStreamObserver.setOnCancelHandler()` để dọn subscription/tài nguyên gắn với call.
- Kiểm tra `isCancelled()` trước khi phát message nếu công việc chạy bất đồng bộ.
- Có thể dùng gRPC `Context.current().addListener(...)` để nối cancellation với task phụ thuộc context.
- Hủy scheduled task, broker subscription hoặc công việc có thể dừng.
- Không phát `onNext()` sau terminal signal.

Ví dụ:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;

// Fragment bên trong server method; eventStore/orderId là dependency và
// tham số của service. close() phải an toàn khi được gọi nhiều lần.
ServerCallStreamObserver<OrderEvent> output =
        (ServerCallStreamObserver<OrderEvent>) responseObserver;

AtomicBoolean stopped = new AtomicBoolean();
Object writeLock = new Object();
EventSubscription subscription = eventStore.subscribe(orderId);

output.setOnCancelHandler(() -> {
    synchronized (writeLock) {
        stopped.set(true);
        subscription.close();
    }
});

subscription.start(event -> {
    synchronized (writeLock) {
        if (stopped.get() || output.isCancelled()) {
            stopped.set(true);
            subscription.close();
            return;
        }
        try {
            output.onNext(toProto(event));
        } catch (RuntimeException sendError) {
            stopped.set(true);
            subscription.close();
        }
    }
});
```

Nếu subscription callback có thể chạy đồng thời với cancellation, cần đồng bộ terminal state để không phát message sau khi call đã đóng. Việc close subscription nên idempotent để nhiều đường dọn dẹp không gây lỗi.

Đăng ký cancellation handler trước khi bắt đầu subscription. Implementation của `EventSubscription` nên coi `close()` trước `start()` là trạng thái kết thúc; khi đó `start()` phải không phát event nữa.

Cancellation là tín hiệu hợp tác. Nó không tự interrupt mọi thread, rollback transaction đã commit hoặc hủy một side effect ở hệ thống ngoài. Server cần thiết kế task có thể kiểm tra cancellation và kết thúc an toàn.

## 9. Tránh rò rỉ tài nguyên trong bridge

Một bridge cần có một chủ sở hữu rõ ràng cho call handle, listener và tài nguyên phụ:

1. Đăng ký cancellation handler ngay khi tạo bridge.
2. Xử lý race khi cancel xảy ra trước khi call handle được cung cấp.
3. Chuyển terminal callback đúng một lần.
4. Hủy timer và subscription khi cancel, error hoặc completion.
5. Không giữ tham chiếu tới subscriber sau terminal state.
6. Với Flux dài hạn, giới hạn buffer hoặc áp dụng flow control.
7. Không tạo một scheduler/executor riêng cho mỗi RPC nếu có thể dùng executor được quản lý.

Nếu bridge chuyển Future sang CompletableFuture, phải nối cancellation hai chiều một cách tường minh. `CompletableFuture.cancel()` không tự động hủy một tác vụ bên ngoài nếu code bridge không gọi `grpcFuture.cancel()`.

## 10. Kiểm thử cancellation và reactive bridge

Nên kiểm thử bằng in-process server/channel hoặc test server có thể quan sát cancellation:

| Kịch bản | Assertion |
| --- | --- |
| Future unary thành công | Mono phát đúng một response rồi complete |
| Future unary trả gRPC error | Mono phát error giữ nguyên status |
| Subscriber cancel trước response | Future/call bị cancel |
| Cancel xảy ra trước `beforeStart()` | Call bị hủy ngay khi handle xuất hiện |
| Reactor timeout | Upstream gRPC call nhận cancellation |
| Server-streaming Flux bị cancel | Client call cancel và server cleanup chạy |
| Stream hoàn tất bình thường | Flux complete, không gọi cancel giả |
| Server gửi nhiều event | Thứ tự event được giữ |
| Subscriber chậm | Buffer/flow control không tăng vô hạn |
| Caller cancel sau khi server commit | Client dừng chờ; test không giả định transaction rollback |

Để xác minh cancellation thực sự tới server, server test có thể đếm lần `onCancelHandler` chạy hoặc xác nhận subscription được đóng bằng latch có timeout. Không chỉ kiểm tra `Disposable.dispose()` đã được gọi ở phía Reactor; cần kiểm tra call gRPC tương ứng cũng được cancel.

## 11. Sai lầm thường gặp

1. **Chỉ chuyển callback thành Mono mà không đăng ký `sink.onCancel`.** RPC tiếp tục chạy sau khi subscriber rời đi.
2. **Cho rằng `CompletableFuture.cancel()` tự hủy gRPC.** Bridge phải nối cancellation tới `ListenableFuture.cancel()` hoặc call handle.
3. **Dùng future stub cho streaming RPC.** Future stub chỉ sinh method unary.
4. **Dùng `.block()` trong reactive event loop.** Có thể chặn thread và gây nghẽn.
5. **Bỏ qua race giữa cancel và `beforeStart()`.** Call handle có thể xuất hiện sau khi subscriber đã hủy.
6. **Dùng buffer vô hạn cho Flux dài hạn.** Subscriber chậm có thể làm tăng bộ nhớ không giới hạn.
7. **Coi cancellation là rollback.** Server có thể đã commit side effect.
8. **Chuyển mọi lỗi thành exception chung.** Làm mất gRPC status cần thiết cho retry/fallback.
9. **Không cleanup subscription/server task.** Client đã hủy nhưng tài nguyên phía server vẫn chạy.

## 12. Bài tập vận dụng

Với `catalog.v1.CatalogService`:

1. Tạo unary future stub `GetItem` và bridge sang `Mono<GetItemResponse>`.
2. Cancel subscriber trước khi server trả response; xác minh gRPC future/call bị hủy.
3. Tạo async server-streaming RPC `WatchItems` và bridge sang `Flux<ItemEvent>`.
4. Cancel Flux sau ba event; xác minh server subscription được đóng.
5. Thử Reactor `timeout()` ngắn hơn gRPC deadline và quan sát status/cancellation.
6. Thử subscriber chậm; thiết kế manual flow control hoặc bounded buffer.
7. Mô phỏng server commit trước khi client cancel; xác minh client không suy luận rằng side effect đã rollback.

**Tiêu chí hoàn thành:** người học bridge được unary Future/async callback sang Mono và server-streaming sang Flux, truyền cancellation tới gRPC call, xử lý race condition, deadline, backpressure và cleanup phía server.

### Tài liệu tham khảo

- [gRPC Java FutureStub API](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/AbstractFutureStub.html): future stub cho unary RPC.
- [gRPC Java ClientCallStreamObserver API](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ClientCallStreamObserver.html): cancellation và flow control phía client.
- [gRPC Java ClientResponseObserver API](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ClientResponseObserver.html): lấy call handle trước khi nhận response.
- [Reactor Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): publisher tối đa một phần tử và cancellation.
- [Reactor Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): publisher nhiều phần tử và overflow strategy.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.

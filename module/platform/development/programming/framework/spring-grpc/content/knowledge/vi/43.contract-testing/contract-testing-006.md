# Kiểm tra deadline và cancellation semantics

Trong Spring gRPC, deadline và cancellation xác định thời gian một RPC còn hữu ích và cách dừng công việc khi caller không còn chờ kết quả. Client có thể nhận DEADLINE_EXCEEDED dù server đã bắt đầu xử lý; một call bị caller chủ động hủy thường kết thúc ở client bằng CANCELLED. Ở phía server, cả hai tình huống đều phải được truyền tới logic xử lý để dừng truy vấn, producer hoặc downstream RPC khi có thể.

Đây là một phần của contract giữa consumer và provider. Nếu client đặt deadline 800 ms, server không nên tiếp tục xử lý vô hạn sau khi budget hết. Nếu client hủy stream, server phải ngừng phát message và giải phóng tài nguyên. Contract test cần xác minh status mà client quan sát, cancellation signal phía server, hành vi với downstream call và việc không tạo side effect sau khi request đã mất hiệu lực.

## 1. Phân biệt deadline, timeout và cancellation

- **Timeout** thường là khoảng thời gian cấu hình, ví dụ 800 ms.
- **Deadline** là thời điểm tuyệt đối mà call phải hoàn tất. Client thường cấu hình bằng timeout tương đối; gRPC chuyển thành deadline nội bộ.
- **Cancellation** là tín hiệu call không còn cần tiếp tục, do caller chủ động hủy, deadline hết hoặc một nguyên nhân hủy khác.

Một deadline là ngân sách tổng cho toàn bộ call. Nếu client dành 800 ms cho RPC, thời gian kết nối, truyền request, xử lý server và trả response đều tiêu thụ ngân sách đó. Không nên cấp lại 800 ms cho từng bước downstream, vì tổng thời gian khi đó có thể vượt deadline của caller.

| Tình huống | Kết quả thường thấy ở client | Hành vi mong đợi ở server |
| --- | --- | --- |
| Server hoàn tất trong deadline | OK | Hoàn tất đúng một lần |
| Deadline hết trước khi response đến | DEADLINE_EXCEEDED | Nhận cancellation và dừng công việc có thể dừng |
| Caller chủ động cancel | CANCELLED | Nhận cancellation và dừng producer/downstream |
| Request đã hết hạn trước khi được xử lý | Có thể DEADLINE_EXCEEDED | Có thể không chạy handler hoặc dừng sớm |
| Server hoàn tất nhưng response đến muộn | Client vẫn có thể nhận DEADLINE_EXCEEDED | Không giả định client đã nhận kết quả |

Deadline/cancellation không phải cơ chế rollback transaction. Nếu server đã commit dữ liệu trước khi deadline hết nhưng response đến muộn, client có thể không biết thao tác đã thành công. API ghi dữ liệu cần idempotency key hoặc cơ chế tra cứu kết quả để client xử lý tình huống không chắc chắn.

## 2. Đặt deadline ở client

Với generated blocking stub, cấu hình deadline cho từng call:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub callStub =
        blockingStub.withDeadlineAfter(800, TimeUnit.MILLISECONDS);

try {
    Product product = callStub.getProduct(
            GetProductRequest.newBuilder()
                    .setProductId("P-100")
                    .build());
    handle(product);
} catch (StatusRuntimeException error) {
    Status.Code code = Status.fromThrowable(error).getCode();
    if (code == Status.Code.DEADLINE_EXCEEDED) {
        recordTimeout();
    } else {
        throw error;
    }
}
```

Stub là immutable về call options: withDeadlineAfter trả về stub mới có deadline được áp dụng cho call qua stub đó. Không sửa một stub dùng chung bằng state mutable theo từng request. Có thể giữ base stub trong bean và tạo derived stub cho mỗi operation.

Deadline cần phù hợp với SLO và ngân sách của caller. Nếu API có nhiều bước, chia ngân sách có chủ đích và để một phần cho serialization, network và xử lý response. Giá trị quá ngắn gây timeout giả khi hệ thống tải cao; giá trị quá dài giữ tài nguyên cho request không còn hữu ích.

Với async stub, deadline được cấu hình tương tự:

```java
CatalogServiceGrpc.CatalogServiceStub callStub =
        asyncStub.withDeadlineAfter(800, TimeUnit.MILLISECONDS);

callStub.getProduct(request, new StreamObserver<Product>() {
    @Override
    public void onNext(Product product) {
        handle(product);
    }

    @Override
    public void onError(Throwable error) {
        Status.Code code = Status.fromThrowable(error).getCode();
        if (code == Status.Code.DEADLINE_EXCEEDED) {
            recordTimeout();
        } else {
            recordFailure(error);
        }
    }

    @Override
    public void onCompleted() {
        complete();
    }
});
```

Trong async API, lỗi terminal được chuyển qua onError. Không giả định callback sẽ chạy trên thread gọi stub hoặc trên một thread cố định.

## 3. Đọc deadline và cancellation ở server

Server có thể đọc deadline từ gRPC Context hiện tại:

```java
@Override
public void getProduct(
        GetProductRequest request,
        StreamObserver<Product> observer) {
    Context context = Context.current();
    Deadline deadline = context.getDeadline();

    if (context.isCancelled()) {
        return;
    }

    if (deadline != null
            && deadline.timeRemaining(TimeUnit.MILLISECONDS) <= 0) {
        return;
    }

    Product product = catalog.find(request.getProductId());
    observer.onNext(product);
    observer.onCompleted();
}
```

Ví dụ cho thấy cách đọc context, nhưng kiểm tra isCancelled một lần không đủ cho công việc kéo dài. Cancellation có thể xảy ra ngay sau lần kiểm tra. Công việc dài cần kiểm tra cancellation tại các điểm an toàn, dùng API downstream có hỗ trợ cancel/timeout và tránh giữ thread trong thao tác blocking không thể hủy.

Context có thể đăng ký listener để nhận cancellation:

```java
Context callContext = Context.current();

callContext.addListener(
        cancelledContext -> stopWorkForCurrentCall(),
        cancellationExecutor);
```

Listener được gọi khi context bị cancel hoặc deadline hết. Hãy giữ listener ngắn, thread-safe và không thực hiện I/O blocking trong callback. Nếu đăng ký listener trong một component sống lâu hơn RPC, cần gỡ listener khi call kết thúc để tránh giữ reference không cần thiết.

Deadline không bảo đảm server tự động ngắt mọi đoạn Java code. Server phải hợp tác: truyền cancellation tới repository/client downstream, hủy scheduled task, dừng vòng lặp và ngừng enqueue message. Một truy vấn JDBC hoặc lời gọi HTTP blocking chỉ dừng khi driver/client API hỗ trợ timeout/cancel và ứng dụng gọi đúng cơ chế đó.

## 4. Phân biệt status client với tín hiệu cancellation server

Khi deadline hết, client thường thấy DEADLINE_EXCEEDED. Khi caller chủ động cancel, client thường thấy CANCELLED. Server thường quan sát call context bị cancel; server không nhất thiết nhận cùng status mà client nhìn thấy và cũng không nên cố gửi một status mới sau khi client đã đóng call.

Một số điểm cần kiểm thử riêng:

- Client timeout/cancel được phản ánh thành status đúng ở client.
- Server cancellation listener được kích hoạt.
- Producer hoặc downstream operation nhận cancellation.
- Server không gửi thêm response sau terminal state.
- Nếu side effect đã commit trước cancellation, client có cách xác định kết quả hoặc retry an toàn.

Không map mọi cancellation thành lỗi INTERNAL. Cancellation thường là lifecycle event bình thường khi client rời trang, ngắt kết nối hoặc deadline hết. Log và metric nên phân biệt deadline, caller cancellation và lỗi nghiệp vụ.

## 5. Deadline propagation qua downstream RPC

Một service thường gọi service khác. Nếu incoming RPC có deadline, downstream call phải dùng phần budget còn lại. gRPC Java dùng Context để truyền deadline khi tạo outgoing call trong context hiện tại. Khi chuyển sang executor khác, phải propagate Context; nếu không, downstream call có thể mất deadline và chạy lâu hơn caller cho phép.

Ví dụ chuyển công việc sang executor với context được capture:

```java
Context parentContext = Context.current();

applicationExecutor.execute(parentContext.wrap(() -> {
    ProductDetails details = inventoryStub
            .getDetails(request)
            .getDetails();

    sendResponse(details);
}));
```

Khi code chạy trong context được wrap, outgoing gRPC call có thể kế thừa deadline của call cha. Nếu tự đặt deadline cho downstream, deadline đó phải ngắn hơn hoặc bằng ngân sách còn lại của parent; không reset toàn bộ timeout ban đầu ở mỗi hop.

Không phải mọi thư viện database/HTTP đều tự hiểu gRPC Context. Truyền remaining time vào timeout của dependency hoặc dùng cancellation integration tương ứng. Nếu dependency không hỗ trợ cancel, đặt giới hạn thời gian rõ và bảo đảm kết quả đến muộn không tiếp tục gây side effect.

## 6. Cancellation trong server-streaming và bidirectional streaming

Với server streaming, server thường phát response qua ServerCallStreamObserver. Có thể đăng ký cancellation handler và kiểm tra trạng thái trước khi phát tiếp:

```java
@Override
public void watchProduct(
        WatchProductRequest request,
        StreamObserver<ProductEvent> observer) {
    if (!(observer instanceof ServerCallStreamObserver<?> raw)) {
        throw new IllegalStateException("Expected server stream observer");
    }

    @SuppressWarnings("unchecked")
    ServerCallStreamObserver<ProductEvent> serverObserver =
            (ServerCallStreamObserver<ProductEvent>) raw;

    AtomicBoolean stopped = new AtomicBoolean();
    AtomicReference<Subscription> subscriptionRef = new AtomicReference<>();

    serverObserver.setOnCancelHandler(() -> {
        stopped.set(true);
        Subscription current = subscriptionRef.getAndSet(null);
        if (current != null) {
            current.cancel();
        }
    });

    Subscription created = eventSource.subscribe(event -> {
        if (stopped.get() || serverObserver.isCancelled()) {
            return;
        }
        serverObserver.onNext(toProto(event));
    });
    subscriptionRef.set(created);
    if (stopped.get() && subscriptionRef.compareAndSet(created, null)) {
        created.cancel();
    }
}
```

Đây là khung minh họa; Subscription là kiểu handle của event source trong ứng dụng. Subscription holder xử lý race khi cancel đến trước lúc subscribe trả về: cancellation đánh dấu stopped, còn đoạn sau subscribe sẽ hủy handle vừa tạo. Nếu callback từ event source chạy trên nhiều thread, serialize các lần ghi vào observer. Cancellation handler phải dừng subscription và giải phóng queue.

Với client streaming hoặc bidi, client cũng cần hủy request stream khi không còn quan tâm kết quả. Dùng ClientCallStreamObserver từ ClientResponseObserver.beforeStart để giữ quyền cancel call. Không chỉ ngừng đọc response mà để producer tiếp tục gửi request vô hạn.

## 7. Kiểm thử deadline một cách có kiểm soát

Deadline test nên chứng minh cả hai phía: client nhận DEADLINE_EXCEEDED và server nhận cancellation. Tránh dùng Thread.sleep làm cơ chế đồng bộ chính. Dùng latch để xác nhận handler đã bắt đầu và latch khác để xác nhận cancellation:

```java
final class SlowCatalogService
        extends CatalogServiceGrpc.CatalogServiceImplBase {
    final CountDownLatch entered = new CountDownLatch(1);
    final CountDownLatch cancelled = new CountDownLatch(1);
    final CountDownLatch release = new CountDownLatch(1);
    final ExecutorService worker = Executors.newSingleThreadExecutor();

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<Product> observer) {
        Context callContext = Context.current();
        entered.countDown();

        callContext.addListener(
                ignored -> cancelled.countDown(),
                Runnable::run);

        worker.execute(() -> {
            try {
                release.await();
                if (!callContext.isCancelled()) {
                    observer.onNext(Product.newBuilder()
                            .setProductId(request.getProductId())
                            .build());
                    observer.onCompleted();
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });
    }
}
```

Test gọi service qua in-process channel với deadline hữu hạn:

```java
@Test
void deadlineExpiresAndCancelsServerWork() throws Exception {
    SlowCatalogService service = new SlowCatalogService();
    // server/channel được khởi tạo bằng InProcessServerBuilder
    // và InProcessChannelBuilder trong fixture.
    var shortDeadlineStub = stub.withDeadlineAfter(2, TimeUnit.SECONDS);

    Future<Status.Code> result = testExecutor.submit(() -> {
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> shortDeadlineStub.getProduct(request));
        return Status.fromThrowable(error).getCode();
    });

    assertTrue(service.entered.await(1, TimeUnit.SECONDS));
    assertEquals(Status.Code.DEADLINE_EXCEEDED,
            result.get(3, TimeUnit.SECONDS));
    assertTrue(service.cancelled.await(1, TimeUnit.SECONDS));

    service.release.countDown();
}
```

Trong test thực tế, fixture phải luôn giải phóng latch và shutdown executor/server/channel trong finally hoặc teardown. Deadline 2 giây ở ví dụ tạo khoảng thời gian đủ để xác nhận handler đã vào; điều chỉnh theo môi trường CI và dùng await có timeout. Không dùng một test deadline quá ngắn đến mức call hết hạn trước khi server nhận request.

Bài test không chứng minh một database query cụ thể có thể bị hủy. Muốn xác minh điều đó, thay fixture worker bằng dependency test có cancellation hook và assert hook đã được gọi.

## 8. Kiểm thử caller cancellation riêng với deadline

Caller cancellation là hành động chủ động, nên test nên hủy call rõ ràng thay vì chờ timer. Với async stub, ClientResponseObserver cho phép lấy ClientCallStreamObserver và gọi cancel:

```java
final class CancellableWatch
        implements ClientResponseObserver<WatchRequest, ProductEvent> {
    final CountDownLatch terminal = new CountDownLatch(1);
    volatile ClientCallStreamObserver<WatchRequest> call;
    volatile Status.Code terminalCode;

    @Override
    public void beforeStart(
            ClientCallStreamObserver<WatchRequest> requestStream) {
        this.call = requestStream;
    }

    @Override
    public void onNext(ProductEvent event) {
        // Nhận event nếu call chưa bị hủy.
    }

    @Override
    public void onError(Throwable error) {
        terminalCode = Status.fromThrowable(error).getCode();
        terminal.countDown();
    }

    @Override
    public void onCompleted() {
        terminalCode = Status.Code.OK;
        terminal.countDown();
    }
}
```

Trong test, gọi async stub với observer, chờ một latch riêng ở server-side fixture xác nhận handler đã bắt đầu, sau đó gọi observer.call.cancel("test cancellation", null). Xác minh client nhận CANCELLED và server cancellation handler được gọi. Không dựa vào việc event đầu tiên chắc chắn đến trước khi cancel.

Hai test deadline và explicit cancel phải độc lập. Deadline hết là do ngân sách thời gian; explicit cancel là do caller quyết định. Cả hai đều cần dừng công việc phía server nhưng status client khác nhau.

## 9. Side effect, retry và race condition

Deadline/cancellation có thể xảy ra cùng lúc với commit hoặc gửi response. Vì vậy contract cần trả lời:

- Nếu client hết deadline nhưng server đã commit, client tra cứu kết quả bằng cách nào?
- Retry có thể tạo bản ghi trùng không?
- Idempotency key có được giữ nguyên qua retry không?
- Server có kiểm tra cancellation trước các side effect có thể trì hoãn không?
- Một callback đến muộn có thể gửi response sau khi call đã kết thúc không?

Với operation ghi, tạo idempotency key ổn định theo ý định nghiệp vụ và lưu kết quả để retry có thể trả lại outcome trước đó. Không tạo key mới cho mỗi retry nếu mục tiêu là deduplicate cùng một operation.

Status DEADLINE_EXCEEDED không chứng minh server chưa làm gì. Status CANCELLED cũng không phải transaction rollback. Nếu commit đã hoàn tất, server phải bảo đảm dữ liệu nhất quán; client phải xử lý trạng thái chưa biết bằng idempotent retry hoặc query operation result.

Đối với streaming, terminal signal chỉ được gửi một lần. Khi cancellation đã xảy ra, ngừng onNext, dừng producer và bỏ các message còn trong queue theo policy. Không gọi onCompleted sau onError hoặc tiếp tục ghi sau terminal state.

## 10. Checklist deadline và cancellation contract

- [ ] Mỗi RPC có deadline mặc định hoặc caller policy rõ ràng.
- [ ] Deadline được xem là ngân sách tổng, không reset lại ở mỗi downstream hop.
- [ ] Client test xác minh DEADLINE_EXCEEDED khi vượt hạn.
- [ ] Client explicit-cancel test xác minh CANCELLED.
- [ ] Server đọc Context deadline và nhận cancellation listener.
- [ ] Context được propagate khi chuyển sang executor khác.
- [ ] Downstream gRPC/HTTP/database có timeout/cancel phù hợp.
- [ ] Streaming producer dừng khi ServerCallStreamObserver bị cancel.
- [ ] Không phát message hoặc terminal signal sau khi call đã kết thúc.
- [ ] Test dùng latch/barrier và timeout hữu hạn thay cho sleep làm đồng bộ.
- [ ] Side effect có idempotency strategy khi client không biết kết quả cuối.
- [ ] Channel, server, executor, listener và subscription được giải phóng trong teardown.
- [ ] Metric phân biệt deadline expiry, caller cancellation và lỗi nghiệp vụ.

**Tự kiểm tra**

**Câu 1.** Deadline khác timeout ở điểm nào?

*Đáp án:* Timeout là khoảng thời gian cấu hình; deadline là thời điểm call phải hoàn tất. Nhiều bước trong một RPC cùng tiêu thụ một deadline budget.

**Câu 2.** Client thường nhận status nào khi deadline hết và khi caller chủ động cancel?

*Đáp án:* Deadline hết thường là DEADLINE_EXCEEDED; caller chủ động hủy thường là CANCELLED. Server thường quan sát cả hai qua cancellation của call context.

**Câu 3.** Vì sao server phải kiểm tra cancellation dù gRPC đã đóng call?

*Đáp án:* Việc đóng call không tự dừng mọi task Java, truy vấn database hoặc producer. Ứng dụng phải truyền cancellation tới dependency và dừng công việc có thể dừng.

**Câu 4.** Vì sao không cấp lại toàn bộ timeout cho mỗi downstream RPC?

*Đáp án:* Làm vậy có thể khiến tổng thời gian vượt ngân sách caller. Downstream phải kế thừa deadline hoặc dùng phần thời gian còn lại của parent.

**Câu 5.** DEADLINE_EXCEEDED có chứng minh operation chưa commit không?

*Đáp án:* Không. Server có thể đã commit nhưng response đến muộn. Operation ghi cần idempotency key hoặc cơ chế tra cứu kết quả để retry an toàn.

Contract test deadline và cancellation phải kiểm tra status ở client cùng tín hiệu dừng ở server. Khi deadline được truyền xuyên suốt call chain, cancellation được chuyển tới dependency và streaming producer, còn side effect được bảo vệ bằng idempotency, Spring gRPC có thể giải phóng tài nguyên đúng lúc và giữ hành vi nhất quán khi client ngừng chờ.

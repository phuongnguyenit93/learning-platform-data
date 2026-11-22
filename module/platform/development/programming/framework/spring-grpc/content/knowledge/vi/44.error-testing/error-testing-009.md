# Test cancellation

Trong **SPRING_GRPC**, một RPC có thể kết thúc trước khi application use case hoàn tất. Client có thể chủ động hủy lời gọi, deadline có thể hết hạn hoặc kết nối có thể bị đóng. Server cần nhận biết cancellation, dừng công việc còn có thể dừng an toàn và giải phóng tài nguyên như cursor, subscription, file handle hoặc tác vụ nền.

Kiểm thử cancellation cần xác minh cả hai phía: client nhận kết quả kết thúc phù hợp và server thực sự ngừng xử lý/cleanup. Chỉ assert client nhận `CANCELLED` là chưa đủ, vì worker hoặc database query có thể vẫn tiếp tục chạy. Bài này tập trung vào cancellation trong gRPC Java/Spring adapter, cách propagate tín hiệu vào application layer và cách viết unit/in-process test xác định.

## 1. Phân biệt cancellation, deadline và lỗi nghiệp vụ

Ba tình huống thường bị nhầm:

| Tình huống | Nguyên nhân | Status client thường thấy | Server cần làm |
| --- | --- | --- | --- |
| Client cancel | Caller không cần kết quả nữa | `CANCELLED` | Dừng công việc còn có thể dừng và cleanup |
| Deadline hết hạn | Thời gian RPC vượt giới hạn | `DEADLINE_EXCEEDED` | Xử lý như cancellation ở server, dừng dependency |
| Lỗi nghiệp vụ | Quy tắc nghiệp vụ không cho phép thao tác | Status theo contract, ví dụ `NOT_FOUND` | Trả lỗi nghiệp vụ; không coi là cancellation |

Khi client hủy hoặc deadline hết, server call bị cancel. Ở phía server, hai nguyên nhân này đều cần kích hoạt đường dừng công việc; không nên dựa vào việc phân biệt nguyên nhân để quyết định có cleanup hay không.

Cancellation không có nghĩa là rollback mọi side effect. Nếu transaction đã commit hoặc message đã được publish, gRPC không thể tự hoàn tác. Với thao tác có side effect, cần xác định điểm commit, idempotency và cách truy vấn kết quả khi client không nhận được response.

## 2. Server nhận biết cancellation

Trong generated service implementation, response observer của server thường là `ServerCallStreamObserver`. Adapter có thể đăng ký `setOnCancelHandler` để được thông báo khi client hủy call hoặc deadline hết:

```java
@Override
public void watchItems(
        WatchItemsRequest request,
        StreamObserver<ItemReply> responseObserver) {

    ServerCallStreamObserver<ItemReply> serverObserver =
            (ServerCallStreamObserver<ItemReply>) responseObserver;

    serverObserver.setOnCancelHandler(() -> {
        // Yêu cầu application operation dừng và giải phóng tài nguyên.
        cancellationSignal.cancel();
    });

    // Bắt đầu xử lý stream...
}
```

Chỉ cast observer trong server implementation chạy dưới gRPC runtime. Khi unit test gọi method trực tiếp, test phải truyền observer giả có hành vi tương thích hoặc kiểm tra logic cancellation qua một abstraction riêng.

Không gọi `observer.onError()` từ cancellation handler chỉ để thông báo client đã hủy. Transport đã kết thúc call; server cần dừng producer và cleanup. Sau khi call bị cancel, không phát thêm `onNext`, `onCompleted` hoặc `onError`.

## 3. Tách cancellation signal khỏi gRPC API

Application/domain không nên phụ thuộc `ServerCallStreamObserver` hoặc `io.grpc.Context`. Adapter có thể chuyển cancellation thành một abstraction thuần Java:

```java
public interface CancellationSignal {
    boolean isCancelled();
    void cancel();
}
```

Một implementation đơn giản dùng atomic flag:

```java
public final class AtomicCancellationSignal
        implements CancellationSignal {

    private final AtomicBoolean cancelled = new AtomicBoolean();

    @Override
    public boolean isCancelled() {
        return cancelled.get();
    }

    @Override
    public void cancel() {
        cancelled.set(true);
    }
}
```

Application operation nhận signal khi cần hỗ trợ dừng hợp tác:

```java
public interface WatchItemsUseCase {
    void stream(
            WatchItemsQuery query,
            CancellationSignal cancellation,
            Consumer<ItemView> emit);
}
```

Use case kiểm tra signal ở các điểm an toàn:

```java
@Override
public void stream(
        WatchItemsQuery query,
        CancellationSignal cancellation,
        Consumer<ItemView> emit) {

    try (ItemCursor cursor = repository.openCursor(query)) {
        while (!cancellation.isCancelled() && cursor.hasNext()) {
            // I/O trong hasNext() có thể block; kiểm tra lại trước khi phát.
            if (cancellation.isCancelled()) {
                break;
            }
            emit.accept(ItemView.from(cursor.next()));
        }
    }
}
```

`try-with-resources` bảo đảm cursor được đóng khi vòng lặp dừng bình thường hoặc phát sinh exception. Kiểm tra signal không thể ngắt một lệnh I/O đang block; dependency vẫn cần query timeout hoặc API cancellation riêng.

## 4. Nối server cancellation với application operation

Adapter tạo cancellation signal cho từng RPC, đăng ký handler và truyền signal vào use case:

```java
@Override
public void watchItems(
        WatchItemsRequest request,
        StreamObserver<ItemReply> responseObserver) {

    ServerCallStreamObserver<ItemReply> serverObserver =
            (ServerCallStreamObserver<ItemReply>) responseObserver;

    AtomicCancellationSignal cancellation =
            new AtomicCancellationSignal();

    serverObserver.setOnCancelHandler(cancellation::cancel);

    try {
        watchItemsUseCase.stream(
                new WatchItemsQuery(request.getCategory()),
                cancellation,
                item -> {
                    if (!cancellation.isCancelled()
                            && !serverObserver.isCancelled()) {
                        serverObserver.onNext(mapper.toProto(item));
                    }
                });

        if (!cancellation.isCancelled()
                && !serverObserver.isCancelled()) {
            serverObserver.onCompleted();
        }
    } catch (RuntimeException error) {
        if (!serverObserver.isCancelled()) {
            serverObserver.onError(errors.toStatus(error));
        }
    }
}
```

Đây là dạng xử lý đồng bộ để minh họa ranh giới. Nếu use case chạy lâu hoặc blocking, không nên giữ thread xử lý RPC trong toàn bộ stream; hãy dùng executor có giới hạn và bảo đảm cancellation signal được truyền tới worker.

Mỗi RPC phải có signal riêng. Không lưu signal vào field của singleton Spring service vì nhiều RPC đồng thời sẽ ghi đè hoặc ảnh hưởng trạng thái của nhau.

## 5. Hủy tác vụ bất đồng bộ

Nếu adapter offload công việc sang executor, có thể lưu `Future` và yêu cầu hủy khi call bị cancel:

```java
AtomicReference<Future<?>> taskRef = new AtomicReference<>();

serverObserver.setOnCancelHandler(() -> {
    cancellation.cancel();

    Future<?> task = taskRef.get();
    if (task != null) {
        task.cancel(true);
    }
});

Context rpcContext = Context.current();

Future<?> task = executor.submit(rpcContext.wrap(() -> {
    try {
        watchItemsUseCase.stream(
                query,
                cancellation,
                item -> {
                    if (!rpcContext.isCancelled()
                            && !serverObserver.isCancelled()) {
                        serverObserver.onNext(mapper.toProto(item));
                    }
                });

        if (!rpcContext.isCancelled()
                && !serverObserver.isCancelled()) {
            serverObserver.onCompleted();
        }
    } catch (RuntimeException error) {
        if (!rpcContext.isCancelled()
                && !serverObserver.isCancelled()) {
            serverObserver.onError(errors.toStatus(error));
        }
    } finally {
        closeResources();
    }
}));

taskRef.set(task);

// Bao phủ trường hợp call bị cancel trước khi Future được lưu.
if (serverObserver.isCancelled()) {
    cancellation.cancel();
    task.cancel(true);
}
```

`Context.current().wrap(...)` giữ gRPC Context khi task chạy trên worker thread. Việc này giúp worker quan sát cancellation/deadline hiện tại, nhưng không tự chuyển Spring transaction, MDC hoặc mọi thread-local khác sang thread mới.

Có race giữa lúc đăng ký cancellation handler, submit task và lưu `Future`. Ví dụ trên kiểm tra lại trạng thái sau khi lưu task; ứng dụng thực tế nên đóng gói việc đăng ký, submit và cancel vào một lifecycle helper được kiểm thử riêng. Không gọi observer từ nhiều worker; mỗi stream chỉ nên có một producer chịu trách nhiệm phát response.

## 6. `Future.cancel(true)` không bảo đảm I/O đã dừng

`cancel(true)` yêu cầu interrupt thread đang chạy. Nó hữu ích với tác vụ hợp tác với interrupt, chẳng hạn chờ `CountDownLatch`, nhưng không đảm bảo mọi blocking I/O đều dừng.

Cần kết hợp cancellation với cơ chế của dependency:

- JDBC: query timeout, statement cancel hoặc driver API phù hợp.
- HTTP client: connect/read/response timeout và cancel request nếu client hỗ trợ.
- Blocking gRPC stub: đặt deadline cho downstream call; cancellation của call cha cần được propagate theo thiết kế.
- File/object storage: đóng stream hoặc gọi API abort phù hợp.
- Reactive publisher: dispose/cancel subscription.
- Cursor/transaction: đóng resource ở `finally`/try-with-resources; transaction rollback theo exception và transaction manager, không tự động theo gRPC cancellation.

Không xem `Thread.interrupt()` là cơ chế hủy duy nhất. Test phải xác minh resource cleanup và giới hạn thời gian chờ, không chỉ kiểm tra thread nhận interrupt.

## 7. Deadline cũng kích hoạt cancellation ở server

Client đặt deadline cho RPC:

```java
CatalogServiceGrpc.CatalogServiceStub client =
        CatalogServiceGrpc.newStub(channel)
                .withDeadlineAfter(250, TimeUnit.MILLISECONDS);
```

Khi deadline hết, client thường nhận `DEADLINE_EXCEEDED`; server call được đánh dấu cancelled và cancellation handler được gọi. Phía server cần dùng thời gian còn lại để giới hạn downstream operation, thay vì để query tiếp tục chạy nhiều giây sau khi caller đã timeout.

Deadline của RPC không tự cấu hình query timeout cho JDBC hoặc HTTP client. Hãy lấy remaining time từ `Context.current().getDeadline()` và áp dụng timeout nhỏ hơn giữa budget còn lại với giới hạn riêng của dependency. Dành thời gian cho mapping/response; không dùng toàn bộ budget cho bước I/O cuối.

## 8. Unit test cancellation logic không cần server

Có thể kiểm thử riêng application operation với một cancellation signal giả. Test điều khiển thời điểm hủy bằng latch, không dùng `Thread.sleep`:

```java
@Test
void stopsReadingWhenCancellationIsRequested() throws Exception {
    AtomicCancellationSignal cancellation =
            new AtomicCancellationSignal();

    CountDownLatch waitingForSecondRead = new CountDownLatch(1);
    CountDownLatch releaseSecondRead = new CountDownLatch(1);
    AtomicInteger hasNextCalls = new AtomicInteger();
    AtomicBoolean cursorClosed = new AtomicBoolean();
    List<ItemView> emitted = new CopyOnWriteArrayList<>();

    ItemCursor cursor = new ItemCursor() {
        @Override
        public boolean hasNext() throws InterruptedException {
            if (hasNextCalls.incrementAndGet() == 1) {
                return true;
            }
            waitingForSecondRead.countDown();
            releaseSecondRead.await();
            return true;
        }

        @Override
        public Item next() {
            return new Item("item-1");
        }

        @Override
        public void close() {
            cursorClosed.set(true);
        }
    };
    when(repository.openCursor(query)).thenReturn(cursor);

    Future<?> work = executor.submit(() -> {
        useCase.stream(query, cancellation, emitted::add);
        return null;
    });

    assertTrue(waitingForSecondRead.await(2, TimeUnit.SECONDS));
    cancellation.cancel();
    releaseSecondRead.countDown();

    work.get(2, TimeUnit.SECONDS);
    assertEquals(1, emitted.size());
    assertTrue(cursorClosed.get());
}
```

Ví dụ giả định `ItemCursor` là interface có `hasNext()`, `next()` và `close()`; bổ sung import/Mockito setup theo project. Test cho thấy cancellation có thể đến trong lúc `hasNext()` đang block, nên use case kiểm tra lại signal trước khi phát item tiếp theo và vẫn đóng cursor. Nó không chứng minh gRPC server nhận được client cancellation; việc đó cần test adapter/transport.

## 9. In-process test: client chủ động cancel server-streaming RPC

In-process transport cho phép gọi generated async stub và hủy call mà không mở TCP port. Dùng `ClientResponseObserver` để lấy `ClientCallStreamObserver` trong `beforeStart`.

Service giả lập công việc dài bằng latch:

```java
final class CancellableCatalogService
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    final CountDownLatch started = new CountDownLatch(1);
    final CountDownLatch cancelled = new CountDownLatch(1);
    final CountDownLatch cleaned = new CountDownLatch(1);

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    private final CountDownLatch releaseWorker = new CountDownLatch(1);

    @Override
    public void watchItems(
            WatchItemsRequest request,
            StreamObserver<ItemReply> observer) {

        ServerCallStreamObserver<ItemReply> serverObserver =
                (ServerCallStreamObserver<ItemReply>) observer;

        AtomicReference<Future<?>> taskRef = new AtomicReference<>();

        serverObserver.setOnCancelHandler(() -> {
            cancelled.countDown();
            Future<?> task = taskRef.get();
            if (task != null) {
                task.cancel(true);
            }
        });

        Future<?> task = executor.submit(() -> {
            started.countDown();
            try {
                releaseWorker.await();
                if (!serverObserver.isCancelled()) {
                    serverObserver.onNext(ItemReply.getDefaultInstance());
                    serverObserver.onCompleted();
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } finally {
                cleaned.countDown();
            }
        });

        taskRef.set(task);
        if (serverObserver.isCancelled()) {
            task.cancel(true);
        }
    }

    void shutdown() {
        releaseWorker.countDown();
        executor.shutdownNow();
    }
}
```

Test khởi động in-process server/channel và cancel sau khi xác nhận worker đã bắt đầu:

```java
@Test
void clientCancelStopsServerWorkAndRunsCleanup() throws Exception {
    CancellableCatalogService service =
            new CancellableCatalogService();

    String name = InProcessServerBuilder.generateName();
    Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(service)
            .build()
            .start();

    ManagedChannel channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();

    AtomicReference<ClientCallStreamObserver<WatchItemsRequest>> callRef =
            new AtomicReference<>();

    try {
        ClientResponseObserver<WatchItemsRequest, ItemReply> response =
                new ClientResponseObserver<>() {
                    @Override
                    public void beforeStart(
                            ClientCallStreamObserver<WatchItemsRequest> call) {
                        callRef.set(call);
                    }

                    @Override
                    public void onNext(ItemReply value) {
                    }

                    @Override
                    public void onError(Throwable error) {
                    }

                    @Override
                    public void onCompleted() {
                    }
                };

        CatalogServiceGrpc.newStub(channel).watchItems(
                WatchItemsRequest.getDefaultInstance(), response);

        assertTrue(service.started.await(2, TimeUnit.SECONDS));
        assertNotNull(callRef.get());

        callRef.get().cancel("test cancellation", null);

        assertTrue(service.cancelled.await(2, TimeUnit.SECONDS));
        assertTrue(service.cleaned.await(2, TimeUnit.SECONDS));
    } finally {
        service.shutdown();
        channel.shutdownNow();
        server.shutdownNow();
        channel.awaitTermination(2, TimeUnit.SECONDS);
        server.awaitTermination(2, TimeUnit.SECONDS);
    }
}
```

Test chứng minh client cancel đi qua gRPC runtime, kích hoạt handler server và worker cleanup. Ví dụ rút gọn bỏ qua assertion nội dung response vì mục tiêu là lifecycle cancellation. Trong test suite đầy đủ, nên thu `onError` phía client và xác nhận status `CANCELLED` nếu đó là behavior client API mà test muốn khóa.

`grpc-inprocess` phải cùng version với các dependency grpc-java khác. Không dùng test này để kết luận TLS, HTTP/2 socket hoặc proxy timeout hoạt động đúng.

## 10. Kiểm thử deadline expiry

Deadline test tương tự client cancel nhưng tạo call với thời gian giới hạn ngắn. Service giữ worker ở trạng thái đang chạy bằng latch; test xác nhận cancellation handler được gọi sau khi deadline hết.

```java
CatalogServiceGrpc.CatalogServiceStub client =
        CatalogServiceGrpc.newStub(channel)
                .withDeadlineAfter(150, TimeUnit.MILLISECONDS);

AtomicReference<Throwable> clientError = new AtomicReference<>();
CountDownLatch clientFinished = new CountDownLatch(1);

ClientResponseObserver<WatchItemsRequest, ItemReply> response =
        new ClientResponseObserver<>() {
            @Override
            public void beforeStart(
                    ClientCallStreamObserver<WatchItemsRequest> call) {
            }

            @Override
            public void onNext(ItemReply value) {
            }

            @Override
            public void onError(Throwable error) {
                clientError.set(error);
                clientFinished.countDown();
            }

            @Override
            public void onCompleted() {
                clientFinished.countDown();
            }
        };

client.watchItems(WatchItemsRequest.getDefaultInstance(), response);

assertTrue(clientFinished.await(2, TimeUnit.SECONDS));
assertEquals(
        Status.Code.DEADLINE_EXCEEDED,
        Status.fromThrowable(clientError.get()).getCode());
assertTrue(service.cancelled.await(2, TimeUnit.SECONDS));
assertTrue(service.cleaned.await(2, TimeUnit.SECONDS));
```

Deadline test phụ thuộc scheduler và thời gian chạy của môi trường; dùng khoảng timeout đủ để server bắt đầu xử lý và chờ bằng latch với upper bound rộng hơn deadline. Tránh `Thread.sleep(150)` vì nó không chứng minh server đã nhận call hoặc cleanup đã hoàn tất. Nếu môi trường test tải cao, dùng test timeout hợp lý và log trạng thái latch để chẩn đoán flaky test.

## 11. Cancellation và streaming flow control

Cancellation và backpressure giải quyết hai vấn đề khác nhau:

- Cancellation: caller không cần kết quả nữa; dừng toàn bộ call.
- Flow control/readiness: caller vẫn cần stream nhưng tạm thời chưa nhận thêm message.

Với server-streaming, dùng `ServerCallStreamObserver.isReady()` và `setOnReadyHandler` để điều tiết tốc độ phát. Khi call cancelled, dừng producer và đóng resource. Không dùng readiness như thay thế cancellation check; một call có thể bị hủy trong lúc producer đang chờ consumer.

Với client-streaming/bidirectional streaming, cancellation phải dừng cả phần nhận input lẫn các tác vụ downstream đang xử lý. Nếu mỗi chunk được commit độc lập, các chunk đã commit vẫn tồn tại sau cancellation; contract cần quy định resume, finalize hoặc cleanup.

## 12. Những điều cancellation không tự làm

| Giả định sai | Thực tế | Cần kiểm thử/thiết kế |
| --- | --- | --- |
| Client cancel tự rollback database | Transaction đã commit vẫn tồn tại | Idempotency, transaction boundary và query trạng thái |
| `Future.cancel(true)` dừng mọi I/O | Nhiều driver/SDK không phản ứng với interrupt | Timeout và cancel API của dependency |
| Deadline hết thì server dừng ngay lập tức | Server phải quan sát và propagate cancellation | Cancellation handler và dependency timeout |
| Gọi `onError(CANCELLED)` là cần thiết | Transport đã đóng call do client cancel | Dừng worker, không gửi terminal signal lần hai |
| Context tự truyền sang mọi executor | Executor tùy biến có thể mất Context | Capture và wrap Context khi submit |
| `isReady() == false` nghĩa là cancelled | Chỉ báo transport tạm thời chưa sẵn sàng | Dùng readiness cho flow control, cancellation cho hủy call |
| Test client thấy CANCELLED chứng minh worker dừng | Worker có thể vẫn chạy nền | Assert server cancellation và cleanup latch |

## 13. Các lỗi kiểm thử thường gặp

- Dùng `Thread.sleep` để chờ cancellation, dẫn đến test flaky.
- Chỉ assert status phía client mà không kiểm tra server cleanup.
- Dùng executor không giới hạn khiến test không mô phỏng được overload.
- Không xử lý race khi cancel xảy ra trước khi `Future` được lưu.
- Gọi `onError` từ cancellation handler rồi worker lại gọi `onCompleted`.
- Dùng một cancellation signal dùng chung cho nhiều RPC.
- Giả định interrupt luôn dừng JDBC/HTTP call.
- Dùng in-process test để kết luận behavior TLS hoặc network disconnect.
- Không đóng channel, server, executor hoặc cursor sau test.

## 14. Bài tập thực hành

1. Viết server-streaming adapter đăng ký `ServerCallStreamObserver.setOnCancelHandler`.
2. Tạo `CancellationSignal` thuần Java và truyền nó vào application use case.
3. Dùng fake cursor để xác nhận use case dừng vòng lặp và đóng cursor khi signal bị cancel.
4. Offload worker bằng executor có giới hạn; capture và wrap gRPC Context.
5. Viết in-process test để client chủ động cancel stream sau khi worker đã bắt đầu.
6. Assert server cancellation handler và cleanup latch đều được kích hoạt.
7. Viết deadline test và xác nhận client nhận `DEADLINE_EXCEEDED`, server vẫn cleanup.
8. Mô phỏng dependency blocking; xác nhận query/read timeout giới hạn thời gian dừng.
9. Kiểm tra không có `onNext`/`onCompleted` sau cancellation.
10. Kiểm tra transaction/side effect đã commit không bị giả định rollback khi client cancel.

### Ghi nhớ

**Cancellation là tín hiệu kết thúc RPC và yêu cầu server dừng công việc còn có thể dừng an toàn.** Adapter nhận tín hiệu qua `ServerCallStreamObserver` hoặc gRPC Context, chuyển nó thành cancellation abstraction của application, hủy worker và đóng resource. `Future.cancel(true)` chỉ là best-effort; dependency cần timeout/cancel API riêng. Test tốt phải xác minh cả status phía client, cancellation handler phía server và cleanup thực tế bằng latch, không chỉ chờ một khoảng thời gian cố định.

## Tài liệu tham khảo

- [gRPC — Cancellation](https://grpc.io/docs/guides/cancellation/)
- [gRPC — Deadlines](https://grpc.io/docs/guides/deadlines/)
- [gRPC Java — ServerCallStreamObserver](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ServerCallStreamObserver.html)
- [gRPC Java — ClientCallStreamObserver](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ClientCallStreamObserver.html)
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html)
- [gRPC Java — InProcessServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/inprocess/InProcessServerBuilder.html)

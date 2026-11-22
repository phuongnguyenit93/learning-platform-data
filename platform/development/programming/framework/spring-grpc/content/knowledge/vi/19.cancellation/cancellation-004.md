# Dọn tài nguyên khi RPC bị hủy

Khi client hủy một RPC hoặc deadline hết hạn, server cần dừng công việc liên quan và giải phóng tài nguyên mà lời gọi đang giữ. Nếu handler chỉ ngừng gửi response nhưng vẫn để database query, HTTP request downstream, subscription hoặc worker chạy, hệ thống tiếp tục tiêu tốn tài nguyên cho một kết quả không còn ai chờ.

**Dọn tài nguyên khi RPC bị hủy** là thiết kế vòng đời của những tài nguyên được mở trong lúc xử lý một call: ai sở hữu chúng, cancellation yêu cầu dừng bằng cách nào, cleanup chạy ở đâu và làm sao tránh đóng lặp hoặc rò rỉ khi các sự kiện đến đồng thời. Bài thuộc chương **Cancellation** của mô-đun **SPRING_GRPC**. Mô-đun phát triển dịch vụ gRPC trong hệ sinh thái Spring từ hợp đồng Protocol Buffers và mã Java sinh ra, hỗ trợ unary/streaming RPC, metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát. Trọng tâm ở đây là xử lý tài nguyên theo vòng đời RPC trong server Spring/gRPC Java.

## 1. Lập danh sách tài nguyên theo vòng đời RPC

Một handler có thể mở nhiều tài nguyên trong suốt một call:

| Tài nguyên | Rủi ro khi RPC bị hủy | Hành động cleanup thường dùng |
| --- | --- | --- |
| JDBC ResultSet, Statement, Connection | Query tiếp tục chạy, cursor và connection bị giữ. | Hủy query nếu driver hỗ trợ; đóng result set, statement và connection theo thứ tự. |
| HTTP client call tới dịch vụ khác | Request downstream vẫn chạy dù caller gốc đã rời đi. | Giữ call handle và gọi API cancel của HTTP client. |
| Future/worker task | Thread tiếp tục tính toán hoặc chờ I/O. | Phát cancellation token, Future.cancel(true) và yêu cầu API bên dưới dừng. |
| Subscription/message feed | Producer tiếp tục phát event và giữ buffer. | Hủy subscription, dừng producer và giải phóng hàng đợi. |
| File, stream hoặc buffer | File descriptor, bộ nhớ và dữ liệu tạm không được giải phóng. | Đóng trong finally hoặc try-with-resources, xóa file tạm theo quyền sở hữu. |
| Downstream gRPC call | RPC phụ tiếp tục sau khi RPC gốc bị hủy. | Hủy đúng call handle hoặc truyền deadline/cancellation xuống tầng dưới. |

Nguyên tắc là **tài nguyên có vòng đời ngắn hơn hoặc bằng RPC phải được giải phóng khi RPC kết thúc**. Không đóng tài nguyên dùng chung như DataSource, connection pool, executor hay ManagedChannel chỉ vì một call bị hủy; chúng thuộc vòng đời ứng dụng hoặc bean Spring.

## 2. Phân biệt yêu cầu hủy với thao tác đóng tài nguyên

Cancellation và cleanup liên quan nhưng không phải cùng một việc:

1. **Báo dừng:** đặt cờ hoặc phát tín hiệu để worker biết RPC không còn cần kết quả.
2. **Hủy I/O đang chạy:** gọi API chuyên biệt như Statement.cancel() hoặc Call.cancel() để cố gắng làm thao tác đang block kết thúc sớm.
3. **Đóng tài nguyên:** giải phóng cursor, statement, connection, subscription, file hoặc buffer sau khi công việc đã dừng hoặc theo contract an toàn của tài nguyên.
4. **Ngừng phát response:** không tạo thêm message sau khi call bị hủy; không cố gửi lỗi thay cho response tới một client đã đóng call.

Một cancellation callback nên làm việc ngắn và không chờ worker. Đóng một resource có thể block hoặc không an toàn khi worker vẫn đang dùng nó. Vì vậy, callback thường phát tín hiệu và gọi API cancel chuyên biệt; worker hoặc owner của resource thực hiện close trong finally khi thao tác đã thoát.

Luồng xử lý điển hình: RPC bắt đầu → mở resource thuộc call → thực hiện công việc → client cancel hoặc deadline hết hạn → phát tín hiệu dừng → hủy I/O/worker nếu có thể → worker thoát → đóng resource → hoàn tất lifecycle của call.

Context.CancellationListener và ServerCallStreamObserver.setOnCancelHandler(...) giúp nhận tín hiệu; chúng không tự đóng những tài nguyên do ứng dụng tạo. Cleanup phải được nối rõ ràng tới owner.

## 3. Dùng try-with-resources cho công việc đồng bộ

Nếu handler thực hiện công việc đồng bộ trên cùng luồng, try-with-resources là cách đơn giản và đáng tin cậy để đóng tài nguyên dù thành công, ném lỗi hay thoát sớm:

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> responseObserver) {

        Context rpcContext = Context.current();
        if (rpcContext.isCancelled()) {
            return;
        }

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "select available_units from inventory where sku = ?")) {

            statement.setQueryTimeout(2);
            statement.setString(1, request.getSku());

            try (ResultSet resultSet = statement.executeQuery()) {
                if (rpcContext.isCancelled()) {
                    return;
                }

                int units = resultSet.next() ? resultSet.getInt(1) : 0;
                if (rpcContext.isCancelled()) {
                    return;
                }

                responseObserver.onNext(StockReply.newBuilder()
                        .setAvailableUnits(units)
                        .build());
                responseObserver.onCompleted();
            }
        } catch (SQLException failure) {
            if (!rpcContext.isCancelled()) {
                responseObserver.onError(Status.INTERNAL
                        .withDescription("Không thể đọc tồn kho")
                        .withCause(failure)
                        .asRuntimeException());
            }
        }
    }

Connection, PreparedStatement và ResultSet được đóng theo thứ tự ngược với thứ tự mở. Khi return, exception hoặc cancellation đã được nhận biết tại một điểm kiểm tra, các resource vẫn được đóng. setQueryTimeout(2) là giới hạn bổ sung cho query; khả năng driver thực thi timeout và độ chính xác của nó phụ thuộc JDBC driver/database.

Tuy nhiên, nếu executeQuery() đang block, việc kiểm tra rpcContext.isCancelled() sau câu lệnh chưa giúp query dừng ngay. Muốn ngắt I/O đang chạy, cần nối cancellation tới Statement.cancel() hoặc cơ chế timeout/cancel của driver. try-with-resources bảo đảm close sau khi luồng điều khiển thoát; nó không tự hủy một lời gọi đang block.

## 4. Hủy JDBC query đang chạy và vẫn đóng resource đúng owner

Với JDBC, một cách tiếp cận là giữ tham chiếu tới statement hiện tại, đăng ký listener để yêu cầu hủy query, còn handler đóng result set, statement và connection trong try-with-resources:

    Context rpcContext = Context.current();
    AtomicReference<Statement> activeStatement = new AtomicReference<>();
    AtomicBoolean cancellationRequested =
            new AtomicBoolean(rpcContext.isCancelled());

    Context.CancellationListener listener = ignored -> {
        cancellationRequested.set(true);
        Statement statement = activeStatement.get();
        if (statement != null) {
            cancellationExecutor.execute(() -> {
                try {
                    statement.cancel();
                } catch (SQLException cancelFailure) {
                    log.debug("Không thể hủy JDBC statement", cancelFailure);
                }
            });
        }
    };
    rpcContext.addListener(listener, Runnable::run);

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(SQL)) {

        activeStatement.set(statement);
        statement.setQueryTimeout(3);

        // Cancellation có thể đến trước lúc statement được lưu vào reference.
        if (cancellationRequested.get() || rpcContext.isCancelled()) {
            cancellationExecutor.execute(() -> cancelQuietly(statement));
            return;
        }

        try (ResultSet resultSet = statement.executeQuery()) {
            // Chuyển kết quả thành response khi call vẫn còn cần kết quả.
        }
    } finally {
        activeStatement.set(null);
        rpcContext.removeListener(listener);
    }

cancellationExecutor là executor có giới hạn, được quản lý ở cấp ứng dụng; không tạo thread mới cho mỗi cancellation. Listener chỉ đặt cờ và gửi yêu cầu hủy sang executor để tránh thực hiện JDBC operation có thể block ngay trên callback cancellation. Handler vẫn là owner đóng ResultSet, Statement và Connection bằng try-with-resources.

Ví dụ có hai cơ chế bảo vệ: kiểm tra cờ sau khi statement được lưu để xử lý cancellation đến sớm, và query timeout để giới hạn thời gian nếu driver không phản ứng nhanh với cancel. Trong code thật, cần xử lý trường hợp executor từ chối task, giới hạn thời gian chờ query, log lỗi cancel có chọn lọc và xác nhận driver hỗ trợ Statement.cancel(). Không đóng connection pool dùng chung từ cancellation listener.

## 5. Quản lý worker task và cleanup khi công việc chạy trên executor

Nếu handler chuyển công việc sang ExecutorService, cần giữ task handle và nối cancellation với worker:

    Context rpcContext = Context.current();
    AtomicBoolean cancelled = new AtomicBoolean(rpcContext.isCancelled());
    AtomicReference<Future<?>> taskRef = new AtomicReference<>();

    Context.CancellationListener listener = ignored -> {
        cancelled.set(true);
        Future<?> task = taskRef.get();
        if (task != null) {
            task.cancel(true);
        }
    };
    rpcContext.addListener(listener, Runnable::run);

    try {
        Future<?> task = workers.submit(rpcContext.wrap(() -> {
            try (ReportCursor cursor = reportService.openCursor(request)) {
                if (cancelled.get() || rpcContext.isCancelled()) {
                    return;
                }

                ReportReply reply = buildReply(cursor);
                if (!cancelled.get() && !rpcContext.isCancelled()
                        && !Thread.currentThread().isInterrupted()) {
                    responseObserver.onNext(reply);
                    responseObserver.onCompleted();
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } catch (Exception failure) {
                if (!cancelled.get() && !rpcContext.isCancelled()) {
                    responseObserver.onError(Status.INTERNAL
                            .withDescription("Không thể tạo báo cáo")
                            .withCause(failure)
                            .asRuntimeException());
                }
            } finally {
                rpcContext.removeListener(listener);
            }
        }));

        taskRef.set(task);
        if (cancelled.get() || rpcContext.isCancelled()) {
            task.cancel(true);
        }
    } catch (RejectedExecutionException rejected) {
        rpcContext.removeListener(listener);
        if (!rpcContext.isCancelled()) {
            responseObserver.onError(Status.RESOURCE_EXHAUSTED
                    .withDescription("Server đang quá tải")
                    .withCause(rejected)
                    .asRuntimeException());
        }
    }

ReportCursor là tài nguyên giả định implement AutoCloseable; worker đóng nó trong try-with-resources. rpcContext.wrap(...) truyền context của RPC sang worker. Future.cancel(true) yêu cầu interrupt nhưng không ép dừng một API không hợp tác. Các thao tác blocking vẫn cần timeout hoặc API cancel riêng.

Race cần được xử lý: cancellation có thể xảy ra trước khi taskRef được gán. Listener đặt cờ; sau submit, handler kiểm tra lại cờ và hủy task nếu cần. Một chi tiết bổ sung trong triển khai production: nếu task bị hủy khi còn nằm trong queue và không bao giờ bắt đầu, finally bên trong task có thể không chạy. Vì vậy owner phải có cơ chế gỡ listener/đóng scope khi task bị hủy trước khi thực thi, chẳng hạn dùng một task wrapper có done() cleanup hoặc một lifecycle coordinator idempotent. Không dựa duy nhất vào finally của phần thân task cho trường hợp task chưa từng chạy.

## 6. Cleanup idempotent và thứ tự đóng resource

Cancellation, lỗi và hoàn tất bình thường có thể xảy ra gần nhau. Một resource có thể bị yêu cầu đóng từ nhiều đường; cleanup phải an toàn khi được gọi nhiều lần. Dùng một cờ atomic hoặc một scope có quyền sở hữu rõ ràng:

    public final class RpcResourceScope implements AutoCloseable {

        private final Object lock = new Object();
        private final Deque<AutoCloseable> resources = new ArrayDeque<>();
        private boolean closed;

        public <T extends AutoCloseable> T add(T resource) {
            boolean closeNow;
            synchronized (lock) {
                closeNow = closed;
                if (!closed) {
                    resources.push(resource);
                }
            }
            if (closeNow) {
                closeQuietly(resource);
            }
            return resource;
        }

        @Override
        public void close() {
            Deque<AutoCloseable> snapshot;
            synchronized (lock) {
                if (closed) {
                    return;
                }
                closed = true;
                snapshot = new ArrayDeque<>(resources);
                resources.clear();
            }

            while (!snapshot.isEmpty()) {
                closeQuietly(snapshot.pop());
            }
        }

        private static void closeQuietly(AutoCloseable resource) {
            try {
                resource.close();
            } catch (Exception ignored) {
                // Production code nên ghi log an toàn, không che lỗi chính.
            }
        }
    }

Scope đóng resource theo thứ tự LIFO: tài nguyên được đăng ký sau sẽ được đóng trước. Ví dụ đăng ký connection trước, statement sau, result set cuối cùng thì cleanup đóng result set, statement rồi connection. close() idempotent nhờ cờ closed được kiểm tra/cập nhật trong vùng đồng bộ; resource được thêm sau khi scope đã đóng sẽ được đóng ngay.

Scope này là cơ chế sở hữu tài nguyên, không phải cancellation engine. Không gọi scope.close() ngay trên callback cancellation nếu resource close có thể block hoặc worker vẫn đang sử dụng resource. Callback nên phát tín hiệu dừng hoặc gọi API cancel chuyên biệt; owner đóng scope khi công việc kết thúc. Nếu cleanup bắt buộc phải chạy trên executor, cần đảm bảo executor còn nhận task trong giai đoạn shutdown và có phương án xử lý rejection.

## 7. Dọn tài nguyên của streaming RPC

Streaming RPC thường giữ subscription, cursor hoặc producer lâu hơn một lần gọi hàm. Server cần đóng subscription khi client cancel, khi stream kết thúc bình thường và khi stream lỗi. Một mẫu quản lý handle:

    Context rpcContext = Context.current();
    ServerCallStreamObserver<PriceUpdate> call =
            (ServerCallStreamObserver<PriceUpdate>) responseObserver;
    AtomicBoolean stopped = new AtomicBoolean(rpcContext.isCancelled());
    AtomicReference<Subscription> subscriptionRef = new AtomicReference<>();
    AtomicReference<Context.CancellationListener> listenerRef = new AtomicReference<>();

    Runnable cleanup = () -> {
        stopped.set(true);
        Subscription subscription = subscriptionRef.getAndSet(null);
        if (subscription != null) {
            subscription.close();
        }
        Context.CancellationListener registered = listenerRef.get();
        if (registered != null) {
            rpcContext.removeListener(registered);
        }
    };

    Context.CancellationListener listener = ignored -> cleanup.run();
    listenerRef.set(listener);
    rpcContext.addListener(listener, Runnable::run);

    if (!stopped.get() && !call.isCancelled()) {
        Subscription subscription = priceFeed.subscribe(symbol, update -> {
            if (!stopped.get() && !call.isCancelled()) {
                responseObserver.onNext(toProto(update));
            }
        });
        subscriptionRef.set(subscription);

        // Hủy có thể đến trong lúc subscribe đang tạo handle.
        if (stopped.get() || call.isCancelled()) {
            cleanup.run();
        }
    }

Subscription là handle do priceFeed của ứng dụng cung cấp. Handler được đăng ký trước khi bắt đầu subscribe; nếu cancellation xảy ra trước khi handle được lưu, cờ stopped sẽ được kiểm tra lại ngay sau khi subscription được tạo và handle sẽ được đóng. getAndSet(null) bảo đảm chỉ một nhánh lấy được handle để đóng. Cleanup cũng gỡ listener, vì vậy khi stream hoàn tất bình thường hoặc lỗi, handler chỉ cần gọi cleanup.run() trong terminal path trước khi kết thúc observer.

Subscription.close() trong ví dụ cần là thao tác hủy/đóng phù hợp với contract của priceFeed. Nếu nó có thể block, callback cancellation không nên gọi trực tiếp; hãy phát tín hiệu và giao cleanup cho executor/owner phù hợp. Nếu callback priceFeed chạy đồng thời trên nhiều thread, cần tuần tự hóa onNext theo contract gRPC. Với producer nhanh hơn client, triển khai flow control bằng isReady()/setOnReadyHandler(...) hoặc hàng đợi có giới hạn; không bỏ message chỉ vì observer tạm thời chưa ready.

## 8. Dọn downstream call và tài nguyên liên quan

Một RPC server có thể gọi tiếp một gRPC service khác hoặc HTTP API. Nếu RPC gốc bị hủy, call downstream không nên tiếp tục vô hạn. Giữ call handle hoặc context của downstream để chuyển cancellation:

- Với async gRPC stub, dùng ClientResponseObserver.beforeStart(...) để lấy ClientCallStreamObserver rồi gọi cancel(...) khi RPC gốc bị hủy.
- Với HTTP client, giữ handle của request và gọi cancel/dispose theo API của thư viện.
- Với database, dùng query timeout hoặc Statement.cancel() nếu driver hỗ trợ.
- Với file hoặc stream, đóng đúng owner bằng try-with-resources/finally.

Khi gọi downstream gRPC, truyền deadline còn lại từ context của RPC gốc thay vì cấp lại toàn bộ timeout ban đầu. Nếu deadline đã hết hoặc context đã cancelled, không bắt đầu một downstream call mới. Deadline giới hạn thời gian; cancellation phản ánh caller đã bỏ call; cả hai đều cần được truyền qua các tầng để tránh công việc mồ côi.

## 9. Kiểm thử resource cleanup

Test không nên chỉ xác minh client nhận CANCELLED; cần xác minh resource thực sự được giải phóng. Một test đơn vị có thể dùng fake resource đếm số lần close:

    AtomicInteger closeCount = new AtomicInteger();
    AutoCloseable fakeResource = closeCount::incrementAndGet;

    RpcResourceScope scope = new RpcResourceScope();
    scope.add(fakeResource);

    scope.close();
    scope.close();

    assertEquals(1, closeCount.get());

Test này xác minh RpcResourceScope.close() idempotent. Bổ sung test race: thêm resource đồng thời với close và xác minh resource được đóng đúng một lần. Với JDBC, dùng fake Statement hoặc database test để xác minh cancel() được gọi và result set/statement/connection được đóng.

Với gRPC in-process server, tạo handler giữ một resource giả, đăng ký cancellation listener, rồi hủy client call. Dùng CountDownLatch để chờ tín hiệu và kiểm tra resource close/cancel được thực hiện. Các test quan trọng gồm:

1. Client cancel khi query đang chạy; xác minh statement cancel được yêu cầu và resource đóng sau khi worker thoát.
2. Deadline hết hạn; xác minh cleanup giống đường cancellation và không gửi response tiếp.
3. Handler hoàn tất bình thường; xác minh resource vẫn đóng dù không có cancellation.
4. Handler ném lỗi; xác minh resource đóng và lỗi được chuyển thành status thích hợp.
5. Cancellation đến trước khi subscription/task handle được lưu; xác minh handle được đóng ngay sau khi tạo.
6. Cleanup được gọi từ nhiều đường; xác minh idempotency và không đóng resource dùng chung.

In-process test xác minh logic lifecycle; integration test qua TCP/TLS còn cần thiết để đánh giá cancellation propagation qua proxy, DNS, transport và độ trễ phát hiện client disconnect.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Client hủy nhưng JDBC query vẫn chạy | Chỉ kiểm tra context sau query, không hủy I/O đang block. | Nối cancellation tới Statement.cancel() và đặt query timeout. |
| Connection pool bị đóng khi một RPC hủy | Nhầm resource theo call với resource dùng chung của ứng dụng. | Chỉ đóng connection/statement/result set do call sở hữu; giữ pool sống. |
| Resource đóng trong lúc worker còn sử dụng | Cancellation callback trực tiếp close mọi resource. | Callback phát tín hiệu/cancel; worker owner đóng trong finally. |
| Cleanup chạy hai lần | Cancellation, lỗi và terminal callback cùng gọi close. | Dùng cleanup idempotent hoặc RpcResourceScope. |
| Subscription bị rò khi cancel xảy ra lúc subscribe | Chưa xử lý race trước khi handle được lưu. | Đăng ký listener trước, lưu handle rồi kiểm tra lại cancellation. |
| Task bị hủy khi còn trong queue nhưng listener vẫn tồn tại | finally trong task chưa từng chạy. | Có task wrapper/owner cleanup cho cả trường hợp task chưa bắt đầu. |
| Future.cancel(true) không dừng I/O | Thư viện bên dưới không hợp tác với interrupt. | Dùng API cancel/timeout chuyên biệt của database hoặc HTTP client. |
| Callback cancellation bị chậm | Thực hiện close/blocking work trực tiếp trong listener. | Chỉ phát tín hiệu nhanh, giao cleanup dài cho owner/executor. |
| Retry sau cancellation tạo side effect trùng | Coi cancellation là rollback. | Dùng idempotency key và kiểm tra trạng thái trước retry. |

## 11. Bài tập thực hành

1. Viết handler unary dùng try-with-resources cho JDBC connection, statement và result set; đặt query timeout và kiểm tra context trước khi gửi response.
2. Đăng ký Context.CancellationListener để gọi Statement.cancel() qua executor có giới hạn; xác minh worker đóng resource trong finally.
3. Tạo RpcResourceScope đóng resource theo LIFO và idempotent; test resource được thêm sau khi scope đã đóng.
4. Tạo server-streaming RPC dùng subscription; hủy subscription khi client cancel, stream hoàn tất hoặc stream lỗi.
5. Mô phỏng cancellation xảy ra trước khi worker/subscription handle được lưu; xác minh không rò resource.
6. Gọi downstream gRPC/HTTP từ handler; nối cancellation và deadline còn lại tới call phụ, rồi kiểm tra call phụ cũng kết thúc.
7. Viết in-process test xác minh resource cleanup thực sự xảy ra, không chỉ xác minh client nhận status CANCELLED.

Sau bài này, bạn cần xác định được tài nguyên nào thuộc một RPC, phân biệt yêu cầu hủy với thao tác đóng, nối cancellation tới API I/O chuyên biệt và bảo đảm cleanup idempotent ở đúng owner. Xử lý tốt vòng đời tài nguyên giúp Spring gRPC server tránh query, worker và subscription mồ côi khi client hủy call hoặc deadline hết hạn.

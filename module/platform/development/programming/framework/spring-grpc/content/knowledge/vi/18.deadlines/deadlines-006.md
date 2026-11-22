# Hủy công việc khi deadline hết hạn

Khi deadline của một RPC hết hạn, gRPC kết thúc lời gọi ở phía client và thông báo **DEADLINE_EXCEEDED**. Ở phía server, context của RPC bị đánh dấu **cancelled**. Nếu service tiếp tục truy vấn database, gọi downstream hoặc xử lý file như bình thường, hệ thống vẫn tiêu tốn tài nguyên cho một kết quả mà client không còn chờ.

Trong **Spring gRPC**, hủy công việc cần được thiết kế theo cơ chế **cooperative cancellation**: ứng dụng nhận tín hiệu từ **io.grpc.Context**, truyền tín hiệu tới các tác vụ có thể hủy, kiểm tra trạng thái ở các điểm an toàn và giải phóng tài nguyên. Deadline không tự động dừng mọi thread Java hay rollback transaction đã commit.

## 1. Điều gì xảy ra khi deadline hết hạn?

Giả sử client gọi **GenerateReport** với deadline 700 ms. Nếu RPC chưa hoàn tất khi hết thời gian, client nhận **DEADLINE_EXCEEDED**. gRPC hủy call; context gắn với handler server chuyển sang trạng thái cancelled.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring gRPC server
    participant W as Worker / downstream
    C->>S: GenerateReport (deadline 700 ms)
    S->>W: Bắt đầu tạo báo cáo
    Note over C,S: Deadline hết hạn
    C-->>C: DEADLINE_EXCEEDED
    S->>S: Context.isCancelled() = true
    S->>W: Yêu cầu hủy công việc
    W-->>S: Dừng / giải phóng tài nguyên nếu hỗ trợ
~~~

Hai phía quan sát hai biểu hiện khác nhau:

| Phía | Biểu hiện |
| --- | --- |
| Client | RPC kết thúc với **DEADLINE_EXCEEDED** |
| Server | Context của RPC bị cancelled; call không còn hợp lệ để gửi response |
| Tác vụ Java | Chỉ dừng nếu ứng dụng hoặc API tác vụ xử lý cancellation |
| Database / HTTP client | Chỉ dừng khi driver/client có timeout hoặc API cancel tương ứng |

**DEADLINE_EXCEEDED** không nhất thiết được ném thành exception trong handler server. Server thường cần theo dõi **context cancellation** để dừng công việc. Đồng thời, cancellation có thể do client chủ động hủy hoặc context cha bị hủy; **isCancelled()** chỉ cho biết trạng thái, không khẳng định nguyên nhân.

## 2. Kiểm tra Context trước và trong khi xử lý

Trong callback của gRPC Java, lấy context hiện hành bằng **Context.current()**:

~~~java
Context rpcContext = Context.current();

if (rpcContext.isCancelled()) {
    return;
}

ReportData data = reportService.loadFirstPart(request);

if (rpcContext.isCancelled()) {
    return;
}

ReportData completed = reportService.loadSecondPart(data);

if (rpcContext.isCancelled()) {
    return;
}

responseObserver.onNext(toResponse(completed));
responseObserver.onCompleted();
~~~

Đây là mẫu cho một handler có nhiều bước; các hàm reportService và toResponse đại diện cho nghiệp vụ. Kiểm tra ở ranh giới giữa các bước giúp tránh bắt đầu công việc mới sau khi RPC bị hủy.

Không nên chỉ kiểm tra một lần ở đầu method. Cancellation có thể đến trong khi server đang xử lý. Ngược lại, kiểm tra **isCancelled()** không thể ngắt một lời gọi blocking đang chạy; nếu loadFirstPart() chờ database 20 giây, code chỉ kiểm tra lại sau khi hàm đó trả về.

## 3. Dùng cancellation listener để phản ứng ngay

Với công việc dài hoặc có tài nguyên cần đóng, đăng ký listener trên context:

~~~java
Context rpcContext = Context.current();

rpcContext.addListener(cancelledContext -> {
    stopProducer();
    cancelDownstreamCall();
    closeTemporaryFile();
}, cleanupExecutor);
~~~

Listener được gọi khi context chuyển sang cancelled. cleanupExecutor là executor do ứng dụng quản lý. Callback nên ngắn và không thực hiện I/O chặn lâu trên thread xử lý gRPC.

Listener phù hợp để:

- Hủy một Future hoặc tác vụ đang chạy.
- Đóng subscription tới event source.
- Dừng producer của server streaming.
- Yêu cầu hủy HTTP/gRPC downstream call.
- Đóng file tạm, stream hoặc tài nguyên đang giữ.

Nếu context đã bị hủy trước khi listener được đăng ký, listener vẫn được thông báo theo cơ chế của Context. Vì vậy, nên thiết kế callback an toàn cả khi cancellation xảy ra rất sớm.

## 4. Hủy tác vụ trên Executor hoặc Future

**Context.isCancelled()** không tự interrupt thread. Nếu công việc chạy trên executor, cần nối cancellation với **Future.cancel(true)** và để tác vụ phản ứng với interrupt hoặc trạng thái context:

~~~java
Context rpcContext = Context.current();

Future<?> task = applicationExecutor.submit(
    rpcContext.wrap(() -> {
        try {
            while (!rpcContext.isCancelled() && hasMoreItems()) {
                processNextItem();
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } finally {
            releaseWorkerResources();
        }
    }));

rpcContext.addListener(
    ignored -> task.cancel(true),
    cancellationExecutor);
~~~

rpcContext.wrap(...) giữ context của RPC cha trong task. Khi deadline hết, listener yêu cầu hủy future; cancel(true) có thể interrupt thread đang chạy. Vòng lặp cũng kiểm tra isCancelled() để dừng tại điểm an toàn.

Mẫu này cần điều chỉnh theo loại tác vụ:

- Nếu task hoàn tất trước cancellation, cancel(true) không gây tác dụng phụ đáng kể.
- Nếu task đang chạy code không interruptible, lệnh cancel chỉ gửi yêu cầu; task có thể tiếp tục.
- Nếu task đang chờ I/O, cần API I/O hỗ trợ timeout hoặc cancel.
- Cleanup trong finally phải an toàn khi task bị interrupt giữa chừng.

Không nuốt InterruptedException. Thông thường cần khôi phục cờ interrupt bằng **Thread.currentThread().interrupt()** rồi kết thúc tác vụ hoặc truyền tín hiệu dừng theo thiết kế.

## 5. Hủy lời gọi gRPC downstream

Khi server gọi một service con trong context hiện hành, gRPC Java có thể truyền deadline và cancellation sang outbound call. Nếu call con được tạo trong context đúng, khi RPC cha bị hủy, lời gọi con cũng bị giới hạn bởi context đó.

~~~java
Context rpcContext = Context.current();

Future<InventoryResponse> downstream = applicationExecutor.submit(
    rpcContext.wrap(() ->
        inventoryStub.checkAvailability(inventoryRequest)));

rpcContext.addListener(
    ignored -> downstream.cancel(true),
    cancellationExecutor);
~~~

Ví dụ minh họa việc chạy blocking stub trong worker; trong ứng dụng thật, cân nhắc async stub hoặc API call có handle cancel rõ ràng. Không tạo channel mới cho mỗi request. Channel nên được tái sử dụng, còn deadline/cancellation thuộc về từng call.

Nếu code tạo downstream call sau khi đã chuyển sang executor, phải truyền Context bằng wrap, fixedContextExecutor hoặc cơ chế tương đương. Nếu không, call có thể mất context cha và tiếp tục chạy sau khi client đã hết hạn.

Không nên chỉ hủy Future bọc quanh một blocking call rồi giả định RPC con chắc chắn đã dừng. Với call bất đồng bộ, giữ handle của call và gọi API cancel phù hợp; đồng thời xác nhận service downstream thực sự quan sát cancellation.

## 6. Database và I/O cần cơ chế hủy riêng

Cancellation của gRPC context không tự động dừng mọi truy vấn database hoặc socket I/O. Cần kết nối tín hiệu với API của tài nguyên:

| Tác vụ | Cách giới hạn hoặc hủy |
| --- | --- |
| JDBC query | Đặt query timeout; giữ Statement để gọi cancel() nếu driver hỗ trợ |
| HTTP client | Giữ handle của request và gọi cancel; đặt timeout ở client |
| Đọc file | Đóng stream/channel khi RPC bị hủy |
| Tác vụ CPU dài | Kiểm tra context giữa các bước hoặc chunk |
| Message/event subscription | Hủy subscription và dừng producer |

Ví dụ minh họa với JDBC:

~~~java
Context rpcContext = Context.current();
AtomicReference<Statement> statementRef = new AtomicReference<>();

rpcContext.addListener(ignored -> {
    Statement statement = statementRef.get();
    if (statement != null) {
        try {
            statement.cancel();
        } catch (SQLException ex) {
            log.warn("Unable to cancel JDBC statement", ex);
        }
    }
}, cleanupExecutor);
~~~

Đây là phần phối hợp cancellation; code tạo connection/statement, thực thi query và đóng tài nguyên vẫn phải nằm trong transaction/resource management phù hợp. Statement.cancel() phụ thuộc driver và database, vì vậy cần kiểm chứng với stack thực tế. Luôn đặt query timeout để có giới hạn độc lập khi tín hiệu cancel không đến hoặc driver không phản ứng kịp.

## 7. Cleanup phải idempotent và xử lý race

Deadline có thể hết đúng lúc công việc bình thường cũng hoàn tất. Listener cancellation và nhánh finally có thể cùng yêu cầu đóng một subscription hoặc giải phóng permit. Dùng một cơ chế cleanup chỉ chạy một lần:

~~~java
AtomicBoolean cleaned = new AtomicBoolean(false);

Runnable cleanupOnce = () -> {
    if (cleaned.compareAndSet(false, true)) {
        closeSubscription();
        releaseWorkerPermit();
        deleteTemporaryFile();
    }
};

rpcContext.addListener(
    ignored -> cleanupOnce.run(),
    cleanupExecutor);

try {
    processRequest();
} finally {
    cleanupOnce.run();
}
~~~

Các hàm cleanup là ví dụ. Nếu một bước cleanup có thể ném exception, cần bắt và ghi nhận lỗi riêng để những tài nguyên còn lại vẫn được giải phóng. Không để lỗi cleanup ghi đè kết quả nghiệp vụ đã hoàn tất.

Với StreamObserver, cần tuần tự hóa onNext, onError và onCompleted. Khi call đã bị hủy, không cố gửi response cuối hoặc status lỗi như thể client vẫn đang nhận. Nếu công việc hoàn tất đồng thời với cancellation, chỉ một nhánh được quyền kết thúc stream.

## 8. Hủy công việc trong streaming RPC

Với server streaming, client có thể rời màn hình hoặc không còn cần event. Server nên dừng producer và đóng subscription. **ServerCallStreamObserver** cung cấp **isCancelled()** và **setOnCancelHandler()** để phản ứng ở mức call:

~~~java
ServerCallStreamObserver<Event> serverObserver =
    (ServerCallStreamObserver<Event>) responseObserver;

AtomicBoolean stopped = new AtomicBoolean(false);
Runnable stopOnce = () -> {
    if (stopped.compareAndSet(false, true)) {
        eventSubscription.close();
        producerExecutor.shutdownNow();
    }
};

serverObserver.setOnCancelHandler(stopOnce);

eventSubscription.onEvent(event -> {
    if (serverObserver.isCancelled()) {
        stopOnce.run();
        return;
    }
    responseObserver.onNext(event);
});
~~~

eventSubscription và producerExecutor đại diện cho thành phần của ứng dụng. Trong triển khai thực tế, cần đăng ký handler trước khi producer có thể phát event, tuần tự hóa observer callback và dùng cùng stopOnce cho cả kết thúc bình thường, lỗi và cancellation. Không gọi shutdownNow() trên executor dùng chung của toàn ứng dụng; chỉ dừng tác vụ hoặc executor riêng của stream.

Với client streaming hoặc bidirectional streaming, áp dụng nguyên tắc tương tự cho chiều nhận và chiều gửi: dừng đọc nguồn, hủy tác vụ đang xử lý, ngừng phát message và giải phóng queue khi RPC bị hủy.

## 9. Cancellation không phải rollback

Nếu deadline hết sau khi transaction đã commit, dữ liệu vẫn có thể đã được ghi dù client nhận DEADLINE_EXCEEDED. Cancellation chỉ yêu cầu công việc dừng; nó không đảo ngược side effect đã xảy ra.

Với command có tác dụng phụ:

1. Dùng idempotency key hoặc operation ID ổn định.
2. Ghi nhận trạng thái và kết quả một cách nhất quán với transaction nghiệp vụ.
3. Khi client timeout, cho phép truy vấn trạng thái theo operation ID.
4. Nếu retry, dùng lại cùng key để tránh thực hiện hành động lần hai.

Với công việc dài có thể chia nhỏ, lưu checkpoint để biết phần nào đã hoàn tất. Khi bị hủy, có thể dừng ở ranh giới chunk an toàn thay vì để lại trạng thái nửa chừng không thể phục hồi.

## 10. Kiểm thử hủy công việc khi deadline hết

Kiểm thử không chỉ xác nhận client nhận DEADLINE_EXCEEDED; cần chứng minh server thực sự dừng hoặc yêu cầu dừng công việc:

1. Tạo một RPC có worker chạy lâu hoặc stream mở.
2. Client đặt deadline ngắn hơn thời gian xử lý.
3. Xác nhận client nhận DEADLINE_EXCEEDED.
4. Xác nhận context listener được gọi hoặc call observer nhận cancellation.
5. Xác nhận future, downstream call, query hoặc subscription được yêu cầu hủy.
6. Xác nhận cleanup chỉ chạy một lần dù cancellation và completion xảy ra gần nhau.
7. Xác nhận không có message mới được gửi sau khi stream bị hủy.

Dùng CountDownLatch, CompletableFuture có thể điều khiển hoặc fake resource để đồng bộ test. Tránh dùng Thread.sleep dài vì dễ tạo test không ổn định. Với JDBC hoặc HTTP client, cần test riêng adapter để xác nhận driver/client thực sự dừng I/O khi được yêu cầu.

## 11. Quan sát cancellation trong production

Theo dõi theo full method name và service:

- Số RPC hết deadline và số RPC bị client cancel.
- Thời gian từ lúc context bị cancelled đến khi worker dừng.
- Số future/task vẫn chạy sau cancellation.
- Số query hoặc downstream call được yêu cầu hủy.
- Thời gian cleanup và số lỗi khi đóng tài nguyên.
- Số stream/producer còn tồn tại sau khi client rời đi.
- Tỷ lệ retry và tác dụng phụ trùng được ngăn bằng idempotency.

Nếu client timeout nhưng worker vẫn chạy lâu, tín hiệu cancellation chưa được nối tới tác vụ hoặc I/O. Nếu cancellation đến nhanh nhưng cleanup kéo dài, cần xem thao tác đóng tài nguyên có blocking hoặc đang chờ lock. Trace ID giúp liên kết status client, context server và các lời gọi downstream.

## 12. Ghi nhớ và tự kiểm tra

Khi deadline hết, gRPC hủy RPC và server quan sát context cancelled. **Ứng dụng phải chủ động dừng công việc**: kiểm tra **Context.isCancelled()**, đăng ký listener, hủy future/downstream call, áp dụng timeout/cancel cho I/O và cleanup tài nguyên một cách idempotent. Context cancellation không tự interrupt mọi thread và không rollback transaction đã commit.

Tự kiểm tra:

1. Vì sao Context.isCancelled() không tự dừng một JDBC query đang chạy?
2. Khi nào nên dùng cancellation listener thay vì chỉ kiểm tra trạng thái ở đầu handler?
3. Future.cancel(true) có bảo đảm mọi tác vụ dừng ngay không?
4. Vì sao cleanup phải idempotent khi deadline và completion xảy ra gần nhau?
5. Nếu client nhận DEADLINE_EXCEEDED sau khi transaction commit, cần dùng cơ chế nào để retry an toàn?

Hủy công việc đúng cách giúp Spring gRPC không tiếp tục tiêu tốn thread, connection và tài nguyên downstream sau khi deadline đã hết, đồng thời bảo vệ tính nhất quán của dữ liệu và khả năng phục hồi của hệ thống.

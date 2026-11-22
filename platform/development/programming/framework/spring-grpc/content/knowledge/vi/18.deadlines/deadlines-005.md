# Kiểm tra Context.isCancelled

Khi client hủy RPC hoặc deadline hết hạn, gRPC đánh dấu **context của lời gọi** là cancelled. Phía server cần nhận biết tín hiệu này để dừng công việc không còn cần thiết, hủy các tác vụ downstream và giải phóng tài nguyên. Trong gRPC Java, cách kiểm tra trực tiếp là **Context.current().isCancelled()**.

Trong **Spring gRPC**, Context được gắn với quá trình xử lý RPC. **isCancelled()** cho biết context hiện tại đã bị hủy hay chưa; nó không tự dừng vòng lặp, truy vấn database hoặc tác vụ chạy trên executor. Vì vậy, cần kết hợp kiểm tra tại các điểm xử lý phù hợp với listener và cơ chế cancellation của từng tài nguyên.

## 1. Context.isCancelled() cho biết điều gì?

**io.grpc.Context** mang dữ liệu theo phạm vi một lời gọi, trong đó có deadline và trạng thái cancellation. Ở server handler, lấy context hiện hành bằng:

~~~java
Context rpcContext = Context.current();
boolean cancelled = rpcContext.isCancelled();
~~~

Nếu **isCancelled()** trả về true, lời gọi không còn được xem là đang hoạt động. Các nguyên nhân thường gặp:

- Client chủ động hủy RPC.
- Deadline của client hết hạn.
- Context cha bị hủy và cancellation được truyền xuống context con.
- Ứng dụng chủ động hủy một context được tạo riêng.

Nếu trả về false, chỉ có nghĩa context **chưa bị hủy tại thời điểm kiểm tra**. Nó không bảo đảm RPC sẽ tiếp tục hoạt động đến khi xử lý xong; cancellation có thể xảy ra ngay sau đó. Với tác vụ dài, không nên kiểm tra một lần ở đầu method rồi bỏ qua trạng thái trong suốt quá trình.

## 2. Kiểm tra cancellation trong server handler

Với unary RPC có nhiều bước xử lý, kiểm tra context tại các ranh giới công việc tốn thời gian:

~~~java
@Override
public void getReport(
        ReportRequest request,
        StreamObserver<ReportResponse> responseObserver) {

    Context rpcContext = Context.current();
    if (rpcContext.isCancelled()) {
        return;
    }

    ReportData data = reportService.loadData(request);
    if (rpcContext.isCancelled()) {
        return;
    }

    ReportResponse response = reportService.buildResponse(data);
    if (rpcContext.isCancelled()) {
        return;
    }

    responseObserver.onNext(response);
    responseObserver.onCompleted();
}
~~~

Đây là mẫu minh họa; reportService đại diện cho logic ứng dụng. Khi RPC đã bị hủy, server thường không cần cố gửi thêm response hoặc status lỗi cho client đã rời đi. Các lần kiểm tra giúp tránh bắt đầu bước tiếp theo khi kết quả không còn được sử dụng.

Kiểm tra giữa các bước không thể ngắt một lời gọi blocking đang chạy. Nếu loadData() đang chờ database, cần cấu hình timeout/cancel cho truy vấn hoặc dùng API bất đồng bộ hỗ trợ hủy. **Context.isCancelled()** là tín hiệu để ứng dụng phối hợp, không phải cơ chế tự động interrupt mọi thread.

## 3. Phản ứng ngay khi cancellation xảy ra bằng listener

Với streaming RPC hoặc tác vụ kéo dài, kiểm tra định kỳ có thể chưa đủ. Có thể đăng ký **cancellation listener** để được thông báo khi context bị hủy:

~~~java
Context rpcContext = Context.current();

rpcContext.addListener(cancelledContext -> {
    stopProducer();
    closeSubscription();
    releaseTemporaryResources();
}, cleanupExecutor);
~~~

**addListener** nhận callback và executor thực thi callback. Trong ví dụ, cleanupExecutor là executor do ứng dụng quản lý; các hàm stopProducer, closeSubscription và releaseTemporaryResources đại diện cho tài nguyên thực tế.

Listener hữu ích khi server đang:

- Phát event liên tục trong server streaming.
- Đọc file hoặc upload dữ liệu theo từng chunk.
- Giữ subscription tới event source.
- Chạy tác vụ bất đồng bộ hoặc gọi nhiều service downstream.

Callback cleanup nên ngắn, không block lâu trên thread xử lý gRPC. Nếu cần thao tác I/O hoặc đóng nhiều tài nguyên, chuyển phần việc phù hợp sang executor được quản lý và có giới hạn.

## 4. Cleanup phải idempotent và xử lý race

Cancellation có thể đến gần cùng thời điểm với việc xử lý hoàn tất bình thường. Ví dụ server vừa gửi xong response thì listener cũng được kích hoạt. Nếu cả hai đường đều đóng subscription hoặc giải phóng tài nguyên, code cần chịu được việc cleanup được gọi nhiều lần.

~~~java
AtomicBoolean cleaned = new AtomicBoolean(false);

Runnable cleanup = () -> {
    if (cleaned.compareAndSet(false, true)) {
        subscription.close();
        workerPool.releasePermit();
    }
};

rpcContext.addListener(ignored -> cleanup.run(), cleanupExecutor);

try {
    runStream();
} finally {
    cleanup.run();
}
~~~

subscription và workerPool là tài nguyên giả định của ứng dụng. Cờ AtomicBoolean bảo đảm phần cleanup chỉ chạy một lần ngay cả khi đường cancellation và đường kết thúc bình thường cạnh tranh. Với nhiều tài nguyên, nên cleanup theo thứ tự và vẫn giải phóng các tài nguyên còn lại nếu một thao tác đóng bị lỗi.

Đối với **StreamObserver**, các lệnh onNext, onError và onCompleted cũng cần được tuần tự hóa. Không phát message sau khi RPC đã kết thúc hoặc sau khi context bị hủy.

## 5. Phân biệt isCancelled() với deadline hết hạn

**isCancelled()** kiểm tra trạng thái hủy tổng quát. Nó không chỉ ra nguyên nhân là deadline, client cancel hay context cha bị hủy.

Nếu cần chẩn đoán deadline, có thể đọc deadline gắn với context:

~~~java
Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (rpcContext.isCancelled()) {
    // RPC đã bị hủy.
}

if (deadline != null && deadline.isExpired()) {
    // Deadline đã đến hạn.
}
~~~

Có thể kiểm tra **rpcContext.cancellationCause()** để lấy nguyên nhân nếu context có cung cấp. Đây là thông tin hỗ trợ chẩn đoán; không nên dựa hoàn toàn vào cause để quyết định mọi chính sách nghiệp vụ. Ở phía client, deadline hết thường được thể hiện bằng **DEADLINE_EXCEEDED**; phía server thường quan sát context bị cancelled.

| Kiểm tra | Trả lời câu hỏi |
| --- | --- |
| **isCancelled()** | Context đã bị hủy chưa? |
| **getDeadline()** | Context có deadline nào? |
| **deadline.isExpired()** | Mốc deadline đã qua chưa? |
| **cancellationCause()** | Có nguyên nhân hủy nào được gắn với context không? |

Đừng suy luận **isCancelled() == true** luôn có nghĩa client deadline hết. Client có thể hủy chủ động, hoặc một context cha có thể bị hủy vì lý do khác.

## 6. Context cancellation không đồng nghĩa Thread interruption

Đây là nhầm lẫn thường gặp trong Java:

- **Context.isCancelled()** kiểm tra trạng thái cancellation của gRPC context.
- **Thread.currentThread().isInterrupted()** kiểm tra cờ interrupt của thread Java.
- **Future.cancel(true)** yêu cầu hủy tác vụ và có thể interrupt thread đang chạy tác vụ đó.

Ba cơ chế có liên quan nhưng không tự động tương đương. Khi context bị hủy, không nên giả định thread đang xử lý sẽ tự nhận interrupt. Ứng dụng phải nối cancellation với API của tài nguyên:

| Công việc | Cách phản ứng phù hợp |
| --- | --- |
| Vòng lặp xử lý nhiều bản ghi | Kiểm tra context ở các điểm an toàn giữa các lần xử lý |
| Future chạy trên executor | Đăng ký listener và gọi future.cancel(true) nếu tác vụ hỗ trợ interrupt |
| Truy vấn JDBC | Đặt query timeout hoặc gọi cơ chế cancel của statement/driver |
| HTTP/gRPC downstream | Dùng API call có thể hủy và giữ context/deadline phù hợp |
| Subscription/event producer | Hủy subscription, dừng producer và giải phóng queue |

Không nuốt **InterruptedException**. Khi bắt exception này, thường cần khôi phục cờ interrupt bằng **Thread.currentThread().interrupt()** rồi kết thúc hoặc truyền lỗi theo thiết kế.

## 7. Giữ Context khi chuyển sang executor

**Context.current()** dựa trên context được gắn với luồng thực thi hiện tại. Khi server chuyển công việc sang một thread pool không gắn context, Context.current() trong thread mới có thể là context khác hoặc context gốc. Nếu không truyền context, kiểm tra cancellation và outbound RPC có thể không còn gắn với lời gọi cha.

Capture context trong handler rồi bọc task:

~~~java
Context rpcContext = Context.current();

Future<?> task = applicationExecutor.submit(
    rpcContext.wrap(() -> {
        while (!rpcContext.isCancelled() && hasMoreWork()) {
            processNextItem();
        }
    }));

rpcContext.addListener(
    ignored -> task.cancel(true),
    cancellationExecutor);
~~~

Hoặc dùng executor gắn với context đã capture:

~~~java
Context rpcContext = Context.current();
Executor contextExecutor =
    rpcContext.fixedContextExecutor(applicationExecutor);

contextExecutor.execute(() -> {
    if (!Context.current().isCancelled()) {
        callDownstreamService();
    }
});
~~~

Việc bọc task giữ context của RPC cha trong phạm vi thực thi bất đồng bộ. Listener nối cancellation với Future.cancel(true); vòng lặp vẫn kiểm tra isCancelled() vì interrupt có thể không dừng được mọi loại công việc.

Không giữ context của một RPC đã kết thúc trong singleton hoặc queue nền dài hạn. Tác vụ nền độc lập cần có vòng đời, deadline và context riêng; nó không nên tiếp tục dùng context của request đã hết hạn.

## 8. Kiểm tra cancellation trong streaming RPC

Với server streaming, client có thể hủy khi không còn cần nhận event. Server nên dừng nguồn phát và đóng subscription:

~~~java
Context rpcContext = Context.current();
ServerCallStreamObserver<Event> serverObserver =
    (ServerCallStreamObserver<Event>) responseObserver;

AtomicBoolean closeRequested = new AtomicBoolean(false);
AtomicBoolean subscriptionClosed = new AtomicBoolean(false);
AtomicReference<EventSubscription> subscriptionRef =
    new AtomicReference<>();

Runnable closeOnce = () -> {
    closeRequested.set(true);
    EventSubscription current = subscriptionRef.get();
    if (current != null
            && subscriptionClosed.compareAndSet(false, true)) {
        current.close();
    }
};

EventSubscription subscription = eventSource.subscribe(event -> {
    if (rpcContext.isCancelled() || serverObserver.isCancelled()) {
        closeOnce.run();
        return;
    }
    responseObserver.onNext(event);
});
subscriptionRef.set(subscription);

// Xử lý race nếu cancellation xảy ra trước khi subscription được gán.
if (closeRequested.get()
        && subscriptionClosed.compareAndSet(false, true)) {
    subscription.close();
}

rpcContext.addListener(ignored -> closeOnce.run(), cleanupExecutor);
serverObserver.setOnCancelHandler(closeOnce);
~~~

Ví dụ giả định EventSubscription có phương thức close không ném checked exception và callback event được tuần tự hóa trước khi ghi vào response observer. Trong service thực tế, cần xử lý cả kết thúc bình thường và lỗi qua cùng cơ chế cleanup; nếu event source có thể gọi callback đồng thời, hãy tuần tự hóa các lệnh onNext/onCompleted/onError. Việc kiểm tra cả context và server observer giúp phát hiện cancellation ở phạm vi RPC và call.

Ở phía server, **ServerCallStreamObserver** còn cung cấp **isCancelled()** và **setOnCancelHandler()** để quan sát/hành động theo trạng thái của call. Có thể dùng chúng khi cần chi tiết ở tầng server call; **Context.isCancelled()** vẫn hữu ích để kiểm tra context và truyền cancellation qua nested call. Phía client dùng **ClientCallStreamObserver** cho các thao tác outbound như readiness, request demand hoặc cancel call.

## 9. Kiểm thử Context.isCancelled

Một test tốt cần chứng minh rằng cancellation không chỉ làm client nhận lỗi mà còn khiến server dừng công việc:

1. Gọi một RPC có tác vụ kéo dài hoặc stream mở.
2. Client chủ động cancel hoặc đặt deadline ngắn để tạo cancellation.
3. Server listener được kích hoạt hoặc vòng lặp quan sát isCancelled() == true.
4. Producer, future, subscription và tài nguyên tạm được dọn.
5. Không có message mới được phát sau khi stream kết thúc.
6. Đường hoàn tất bình thường và đường cancellation cùng chạy vẫn chỉ cleanup một lần.

Với gRPC in-process, có thể giữ ClientCall hoặc observer phía client để chủ động hủy; với deadline test, đặt withDeadlineAfter ngắn. Dùng CountDownLatch hoặc CompletableFuture để chờ tín hiệu cleanup thay vì sleep tùy ý.

Ngoài test gRPC, kiểm thử adapter của database hoặc HTTP client để xác nhận cancellation thực sự dừng I/O. Một test chỉ kiểm tra Context.isCancelled() trả true chưa chứng minh truy vấn database hoặc thread pool đã ngừng hoạt động.

## 10. Quan sát và xử lý lỗi

Theo dõi theo RPC method:

- Số lời gọi bị client cancel và số lời gọi hết deadline.
- Thời gian từ lúc context bị cancelled đến lúc cleanup hoàn tất.
- Số task/future vẫn chạy sau cancellation.
- Số subscription, queue và tài nguyên tạm được giải phóng.
- Tỷ lệ message phát sau khi client không còn nhận.
- Status client nhận: **CANCELLED**, **DEADLINE_EXCEEDED** hoặc lỗi khác.

Nếu client thường xuyên thấy DEADLINE_EXCEEDED nhưng server vẫn có nhiều task chạy lâu sau đó, cancellation chưa được nối đầy đủ với công việc nội bộ. Nếu server thấy nhiều CANCELLED, cần phân biệt người dùng rời request, service cha bị hủy hay deadline ở tầng trước đã hết bằng trace và context cause.

Không ghi payload hoặc credential nhạy cảm khi log cancellation. Trace ID, full method name, status, thời gian xử lý và thời gian cleanup thường đủ để điều tra.

## 11. Ghi nhớ và tự kiểm tra

**Context.isCancelled()** cho biết context của RPC đã bị hủy hay chưa. Trên server, context có thể bị hủy do client cancel, deadline hết hoặc context cha bị hủy. Việc kiểm tra trạng thái không tự dừng thread, database hay producer; ứng dụng phải kết nối tín hiệu đó với cơ chế cancellation của từng tài nguyên.

Tự kiểm tra:

1. Vì sao isCancelled() == false ở đầu handler không bảo đảm RPC còn hoạt động ở cuối?
2. Khi client deadline hết, server thường quan sát status hay context cancellation?
3. Vì sao Context.isCancelled() không tương đương Thread.isInterrupted()?
4. Khi chuyển công việc sang executor, cần làm gì để giữ context của RPC cha?
5. Vì sao cleanup phải idempotent khi listener và đường hoàn tất bình thường có thể chạy đồng thời?

Kiểm tra cancellation đúng chỗ, truyền context qua tác vụ bất đồng bộ và cleanup an toàn giúp dịch vụ Spring gRPC không tiếp tục tiêu tốn tài nguyên cho những lời gọi mà client đã hủy hoặc đã hết thời gian chờ.

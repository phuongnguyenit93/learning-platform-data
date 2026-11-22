# Cancellation khác với deadline

Trong gRPC, **cancellation** và **deadline** có liên quan nhưng biểu đạt hai ý định khác nhau. Cancellation có nghĩa một lời gọi không còn cần tiếp tục; deadline đặt thời điểm muộn nhất mà lời gọi được phép tồn tại. Khi deadline hết hạn, gRPC kết thúc RPC bằng cách hủy call. Nhưng caller cũng có thể chủ động hủy trước thời điểm đó, và một call có thể bị hủy do context cha, channel shutdown hoặc kết nối mất.

Phân biệt hai khái niệm giúp Spring gRPC client chọn đúng status, quyết định có retry hay không và truyền ngân sách thời gian qua các service. Bài thuộc chương **Cancellation** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring từ hợp đồng Protocol Buffers và mã Java sinh ra, hỗ trợ unary/streaming RPC, metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát.

## 1. Hai khái niệm khác nhau ở mục đích

**Cancellation** là tín hiệu kết thúc một RPC trước khi nó hoàn tất bình thường. Caller có thể không còn cần kết quả, chẳng hạn người dùng rời màn hình hoặc request HTTP gốc bị hủy. Cancellation cũng có thể đến từ context cha hoặc transport khi peer biến mất.

**Deadline** là giới hạn thời gian của một RPC. Caller đặt một thời lượng hoặc deadline; khi thời điểm đó đến mà RPC chưa hoàn tất, gRPC tự kết thúc lời gọi. Trong gRPC Java, client thường đặt thời lượng tương đối bằng API như withDeadlineAfter(...). Deadline được biểu diễn nội bộ bằng mốc thời gian và ngân sách còn lại, tránh phụ thuộc đồng hồ tuyệt đối giống nhau giữa các máy.

| Thuộc tính | Cancellation | Deadline |
| --- | --- | --- |
| Mục đích | Dừng một RPC vì caller hoặc hệ thống không còn cần tiếp tục. | Giới hạn thời gian tối đa để RPC hoàn tất. |
| Cách khởi phát | Chủ động cancel, context bị hủy, channel/transport kết thúc. | Được cấu hình khi gọi hoặc qua service config; tự hết hạn theo thời gian. |
| Có thể xảy ra trước thời hạn? | Có; caller có thể cancel bất cứ lúc nào. | Chỉ hết hạn khi ngân sách thời gian đã cạn. |
| Có bắt buộc phải có? | Có thể xảy ra dù không đặt deadline. | Có thể không được đặt; khi đó RPC không có giới hạn thời gian hữu hạn từ deadline. |
| Status phía client thường thấy | CANCELLED khi caller chủ động hủy. | DEADLINE_EXCEEDED khi deadline hết hạn. |
| Phía server | Context/call được đánh dấu cancelled. | Khi hết hạn, context/call cũng bị hủy; server có thể đọc deadline để nhận biết đã hết hạn. |

Quan hệ cốt lõi: **deadline hết hạn dẫn tới cancellation**, nhưng không phải mọi cancellation đều do deadline. Vì vậy, thấy Context.isCancelled() ở server chưa đủ để kết luận deadline đã hết.

## 2. Status phía client và tín hiệu phía server

Với client, status cuối cùng thường giúp phân biệt nguyên nhân:

- CANCELLED: lời gọi bị hủy trước khi hoàn tất, thường do caller chủ động hoặc một context/transport liên quan bị hủy.
- DEADLINE_EXCEEDED: lời gọi không hoàn tất trước deadline đã đặt.
- UNAVAILABLE: transport hoặc service không sẵn sàng; không đồng nghĩa với chủ động cancellation hay deadline.
- OK: RPC hoàn tất thành công trước khi bị hủy hoặc hết hạn.

Ở server, cả explicit cancellation và deadline expiration đều làm context của RPC chuyển sang trạng thái cancelled. Server có thể lấy deadline từ context và kiểm tra nó đã hết hay chưa:

~~~java
Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (rpcContext.isCancelled()) {
    if (deadline != null && deadline.isExpired()) {
        // Deadline đã hết tại thời điểm kiểm tra.
    } else {
        // Call bị hủy bởi một nguyên nhân khác hoặc peer đã biến mất.
    }
}
~~~

Đây là phép kiểm tra tại một thời điểm. Nếu deadline tồn tại nhưng chưa hết, call vẫn có thể bị client cancel hoặc kết nối bị mất. Nếu deadline đã hết, đó là bằng chứng deadline đã hết tại lúc kiểm tra; trong một race, không nên dùng phép kiểm tra này làm bằng chứng tuyệt đối về nguyên nhân duy nhất dẫn tới call termination.

ServerCallStreamObserver.setOnCancelHandler(...) nhận thông báo khi call bị hủy. Handler này không tự phân loại nguyên nhân. Context.cancellationCause() có thể cung cấp cause trong một số trường hợp, nhưng không nên dựa vào nó như một mã phân loại ổn định cho mọi transport và mọi nguồn cancellation.

Một server không thể gửi status mới cho client đã hủy hoặc mất kết nối. Khi context đã cancelled, ưu tiên dừng công việc và cleanup thay vì gọi thêm onError(...), onCompleted() hoặc onNext(...).

## 3. Đặt deadline cho client RPC

Với blocking stub, đặt giới hạn thời gian ngay trên bản stub dùng cho call:

~~~java
StockReply reply = inventoryStub
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getStock(request);
~~~

Nếu server không hoàn tất trong 800 ms, client nhận lỗi có status DEADLINE_EXCEEDED. Deadline áp dụng cho toàn bộ RPC, bao gồm thời gian chờ kết nối/sẵn sàng và thời gian trao đổi với server; nó không chỉ đo thời gian thực thi hàm nghiệp vụ ở server.

Đối với async hoặc streaming stub, deadline cũng được đặt trên stub trước khi gọi method:

~~~java
GreeterGrpc.GreeterStub boundedStub =
        greeterStub.withDeadlineAfter(3, TimeUnit.SECONDS);

boundedStub.sayHello(request, responseObserver);
~~~

Đặt deadline mặc định theo service/method bằng gRPC Service Config hoặc interceptor là cách bảo vệ các call không được caller đặt thời hạn riêng. Cần chọn timeout theo SLO, loại RPC và tuổi thọ stream. Một deadline ngắn phù hợp với unary query có thể làm server-streaming subscription kết thúc sớm dù client vẫn muốn nhận dữ liệu.

gRPC Java không tự đặt một deadline hữu hạn cho mọi RPC nếu ứng dụng không cấu hình. Vì vậy, không nên xem channel đã kết nối hoặc keepalive đang bật là bảo đảm RPC sẽ tự kết thúc sau một khoảng thời gian.

## 4. Chủ động hủy một RPC trước deadline

Nếu caller không còn cần kết quả, hãy hủy call ngay thay vì đợi deadline hết. Với async stub, dùng ClientResponseObserver để lấy call handle:

~~~java
AtomicReference<ClientCallStreamObserver<HelloRequest>> activeCall =
        new AtomicReference<>();

ClientResponseObserver<HelloRequest, HelloReply> observer =
        new ClientResponseObserver<>() {
            @Override
            public void beforeStart(
                    ClientCallStreamObserver<HelloRequest> call) {
                activeCall.set(call);
            }

            @Override
            public void onNext(HelloReply reply) {
                handleReply(reply);
            }

            @Override
            public void onError(Throwable failure) {
                handleFailure(failure);
            }

            @Override
            public void onCompleted() {
                handleCompletion();
            }
        };

greeterStub.withDeadlineAfter(10, TimeUnit.SECONDS)
        .sayHello(request, observer);

// Khi caller không còn cần kết quả:
ClientCallStreamObserver<HelloRequest> call = activeCall.get();
if (call != null) {
    call.cancel("User left the screen", null);
}
~~~

Ví dụ minh họa thao tác call-level cancellation. Code production cần xử lý race nếu caller hủy trước khi beforeStart(...) lưu handle: giữ một cờ cancellationRequested và kiểm tra cờ đó trong beforeStart. Cũng cần bảo đảm call handle thuộc đúng RPC; không lưu nó vào field mutable dùng chung của singleton Spring service.

Nếu bọc RPC trong CompletableFuture, nối future.cancel(true) tới ClientCallStreamObserver.cancel(...). Chỉ hủy future ở tầng ứng dụng mà không chuyển tín hiệu xuống call có thể khiến RPC vẫn chạy ở transport/server.

## 5. Server xử lý cả cancellation và deadline như thế nào?

Ở server, cancellation là tín hiệu hợp tác. Handler cần dừng worker, subscription hoặc downstream call; deadline còn cung cấp ngân sách thời gian để các tầng không tiếp tục chờ quá lâu.

~~~java
Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();
AtomicBoolean stopped = new AtomicBoolean(rpcContext.isCancelled());

Context.CancellationListener listener = ignored -> stopped.set(true);
rpcContext.addListener(listener, Runnable::run);

try {
    if (stopped.get()) {
        return;
    }

    long remainingMillis = deadline == null
            ? 0
            : deadline.timeRemaining(TimeUnit.MILLISECONDS);

    if (deadline != null && remainingMillis <= 0) {
        return;
    }

    performWork(stopped);
} finally {
    rpcContext.removeListener(listener);
}
~~~

Ví dụ cho thấy cùng một listener nhận tín hiệu cancellation bất kể nguồn nào. Nếu deadline tồn tại, handler có thể đọc phần thời gian còn lại để giới hạn công việc. Giá trị 0 trong ví dụ biểu thị không có deadline; code production nên dùng một policy mặc định rõ ràng thay vì diễn giải 0 là thời gian chờ bằng không.

Listener nên chỉ đặt cờ hoặc yêu cầu dừng nhanh. Không block để chờ worker, đóng resource có thể block hoặc rollback transaction từ callback chạy trên thread khác. Worker sở hữu tài nguyên phải phản ứng với cờ/interrupt và cleanup trong finally hoặc try-with-resources.

## 6. Truyền ngân sách deadline xuống downstream

Một request có thể đi qua nhiều service. Nếu request gốc chỉ còn 400 ms, không nên cấp mới 2 giây cho mỗi downstream call. Hãy truyền **thời gian còn lại**:

~~~java
Deadline parentDeadline = Context.current().getDeadline();
InventoryGrpc.InventoryBlockingStub downstream = inventoryStub;

if (parentDeadline != null) {
    long remainingNanos =
            parentDeadline.timeRemaining(TimeUnit.NANOSECONDS);
    if (remainingNanos <= 0) {
        throw new UpstreamDeadlineExpiredException();
    }

    downstream = downstream.withDeadlineAfter(
            remainingNanos, TimeUnit.NANOSECONDS);
}

StockReply reply = downstream.getStock(request);
~~~

Nếu parent call bị explicit cancellation trước khi deadline hết, chỉ truyền deadline còn lại là chưa đủ: downstream có thể tiếp tục chạy cho tới deadline. Cần nối cancellation của parent context tới downstream call handle, đặc biệt với async stub:

~~~java
Context parentContext = Context.current();
AtomicBoolean cancelled = new AtomicBoolean(parentContext.isCancelled());
AtomicReference<ClientCallStreamObserver<StockRequest>> downstreamCall =
        new AtomicReference<>();

Context.CancellationListener listener = ignored -> {
    cancelled.set(true);
    ClientCallStreamObserver<StockRequest> call = downstreamCall.get();
    if (call != null) {
        call.cancel("Parent RPC cancelled", null);
    }
};
parentContext.addListener(listener, Runnable::run);
~~~

Khi tạo downstream async call, lưu handle trong beforeStart(...) và kiểm tra lại cancelled để xử lý race. Gỡ listener trong terminal path của parent call. Cần xử lý cả hai hướng: deadline giới hạn thời gian; cancellation chủ động dừng sớm hơn deadline.

## 7. Retry khác nhau theo nguyên nhân kết thúc

Cancellation và deadline dẫn tới quyết định retry khác nhau:

| Kết quả | Có nên retry tự động? | Lý do |
| --- | --- | --- |
| Caller chủ động cancel | Thường không. | Caller đã nói rằng không còn cần kết quả; retry sẽ đi ngược ý định đó. |
| DEADLINE_EXCEEDED | Chỉ khi operation an toàn và còn ngân sách tổng. | Server có thể đã commit side effect dù client không nhận response. |
| UNAVAILABLE | Có thể với retry policy/backoff phù hợp. | Service/transport có thể tạm thời không sẵn sàng; vẫn phải xét idempotency. |
| Server trả CANCELLED | Không suy ra nguyên nhân chỉ từ code. | Cần xem call lifecycle và chính sách của operation. |
| OK | Không retry. | RPC đã hoàn tất thành công. |

Một deadline tổng nên bao trùm toàn bộ retry và backoff. Không cấp lại toàn bộ timeout ban đầu cho mỗi attempt, vì tổng thời gian có thể vượt ngân sách request gốc. Nếu dùng gRPC retry qua Service Config, hãy kiểm tra retry policy và deadline hiệu lực cùng nhau.

Với RPC ghi dữ liệu, DEADLINE_EXCEEDED không chứng minh server chưa thực hiện thao tác. Dùng idempotency key ổn định, truy vấn trạng thái operation hoặc cơ chế deduplication trước khi thử lại. Với explicit cancellation, không tự retry trừ khi một tầng nghiệp vụ khác chủ động tạo một operation mới.

## 8. Cancellation và deadline không phải rollback

Client có thể hủy call sau khi server đã commit transaction. Deadline cũng có thể hết ngay sau commit nhưng trước khi response tới client. Cả hai trường hợp đều khiến caller không biết kết quả, trong khi side effect đã tồn tại.

Đối với thao tác ghi:

- Kiểm tra cancellation trước các bước tốn tài nguyên và trước điểm commit.
- Dùng transaction để rollback thay đổi database nếu cancellation được phát hiện trước commit.
- Dùng idempotency key để retry cùng ý định mà không tạo bản ghi/side effect trùng.
- Với external service hoặc message broker, dùng outbox, state machine và compensation; transaction DB không rollback được hệ thống ngoài.
- Cung cấp API truy vấn trạng thái nếu client có thể mất response sau khi operation đã được chấp nhận.

Cancellation là tín hiệu kết thúc call, deadline là giới hạn thời gian. Không cơ chế nào tự bảo đảm rollback một side effect đã commit.

## 9. Kiểm thử để phân biệt hai trường hợp

Một integration test nên kiểm tra cả status phía client và hành vi context phía server:

1. **Explicit cancel trước deadline:** server giữ RPC chưa hoàn tất; client hủy call; client quan sát CANCELLED, server cancellation handler được gọi và worker dừng.
2. **Deadline hết hạn:** server giữ RPC lâu hơn deadline; client quan sát DEADLINE_EXCEEDED, server context chuyển sang cancelled và deadline được xác định là expired.
3. **Cancel trước khi deadline hết:** xác minh server context cancelled trong khi deadline vẫn còn thời gian.
4. **Deadline rất ngắn:** xác minh handler không bắt đầu downstream work nếu ngân sách đã hết.
5. **Parent cancel khi downstream đang chạy:** xác minh call con bị hủy trước khi deadline gốc hết.
6. **Side effect đã commit trước khi call kết thúc:** xác minh operation vẫn tồn tại và client có thể tra cứu bằng idempotency key.

Với in-process server, dùng CountDownLatch hoặc CyclicBarrier để giữ handler ở một điểm xác định, tránh Thread.sleep() tùy tiện. Kiểm thử qua TCP/TLS bổ sung xác minh transport, proxy và tình huống peer disconnect. In-process test không mô phỏng đầy đủ độ trễ phát hiện mất mạng âm thầm.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Thấy context cancelled và kết luận deadline hết | Explicit cancel hoặc peer disconnect cũng hủy context. | Kiểm tra getDeadline() và isExpired(); không suy nguyên nhân chỉ từ isCancelled(). |
| Đợi deadline hết dù caller đã rời màn hình | Không nối lifecycle caller với call cancellation. | Gọi ClientCallStreamObserver.cancel(...) khi caller không còn cần kết quả. |
| Downstream chạy tới hết deadline dù parent đã cancel | Chỉ truyền deadline, không truyền cancellation. | Nối parent listener với downstream call handle. |
| Retry mọi CANCELLED | Không phân biệt caller intent với cancellation khác. | Tôn trọng caller cancellation và kiểm tra nguyên nhân/lifecycle. |
| Mỗi retry được cấp timeout mới | Không giữ deadline tổng. | Dùng ngân sách còn lại qua các attempt. |
| Tăng deadline để sửa mọi lỗi chậm | Lỗi có thể do quá tải hoặc dependency treo. | Đo latency, giới hạn concurrency và đặt deadline theo SLO. |
| Nghĩ timeout nghĩa là server chưa ghi dữ liệu | Commit có thể xảy ra trước khi response bị mất. | Idempotency, status lookup và reconciliation. |
| Callback cancellation chờ worker kết thúc | Cleanup blocking ngay trong listener. | Listener phát tín hiệu; worker owner tự dừng và cleanup. |

## 11. Bài tập thực hành

1. Gọi một unary RPC với deadline 500 ms và xác minh status DEADLINE_EXCEEDED khi server xử lý chậm.
2. Dùng ClientResponseObserver để chủ động cancel cùng RPC trước deadline; xác minh status client là CANCELLED.
3. Trong server handler, ghi nhận Context.isCancelled() và Deadline.isExpired() cho hai trường hợp; giải thích vì sao cancellation không đồng nghĩa deadline hết.
4. Nối cancellation của parent RPC tới downstream async call và truyền deadline còn lại xuống downstream.
5. Bật retry cho một RPC đọc idempotent; xác minh tổng thời gian và backoff vẫn nằm trong deadline tổng.
6. Thử RPC ghi bị deadline hết sau commit; dùng idempotency key và API truy vấn trạng thái để xác định kết quả.
7. Viết test in-process cho explicit cancel, deadline expiry và cancellation trước khi deadline hết; bổ sung integration test qua TCP/TLS.

Sau bài này, bạn cần phân biệt cancellation là tín hiệu dừng call với deadline là giới hạn thời gian tự động kết thúc call khi hết hạn. Server thường quan sát cả hai qua trạng thái context cancelled, nhưng có thể kiểm tra deadline để biết nó đã hết hay chưa. Phân biệt đúng giúp Spring gRPC client/server dừng công việc đúng lúc, truyền ngân sách qua downstream và đưa ra quyết định retry an toàn.

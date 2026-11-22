# Truyền cancellation sang downstream RPC

Một gRPC server thường gọi thêm các service khác để hoàn tất một request. Ví dụ, Order service gọi Inventory để kiểm tra hàng và Payment để xác thực thanh toán. Nếu client hủy RPC tới Order, các lời gọi downstream vẫn có thể tiếp tục chạy nếu ứng dụng không truyền tín hiệu dừng tới chúng. Khi đó hệ thống tiêu tốn tài nguyên cho một request đã bị bỏ, thậm chí có thể tạo side effect mà caller không còn chờ kết quả.

**Truyền cancellation sang downstream RPC** là nối vòng đời của lời gọi con với lời gọi cha: khi parent RPC bị hủy, các child RPC còn hoạt động được yêu cầu dừng; khi parent deadline sắp hết, child RPC chỉ nhận phần ngân sách thời gian còn lại. Bài thuộc chương **Cancellation** của mô-đun **SPRING_GRPC**, tập trung vào gRPC Java trong ứng dụng Spring, async stub, Context, deadline propagation, race condition, cleanup và kiểm thử.

## 1. Quan hệ parent RPC và downstream RPC

Giả sử client gọi OrderService.GetSummary. Server gọi tiếp InventoryService.GetStock và PricingService.GetPrice. Hai lời gọi con tồn tại để phục vụ lời gọi cha:

~~~mermaid
flowchart TD
    C[Client] -->|GetSummary| P[OrderService - parent RPC]
    P -->|GetStock| I[InventoryService - child RPC]
    P -->|GetPrice| R[PricingService - child RPC]
    C -.->|Cancel / disconnect| P
    P -.->|Propagate cancellation| I
    P -.->|Propagate cancellation| R
~~~

Khi parent bị hủy, server cần:

1. Ngừng khởi tạo downstream call mới.
2. Yêu cầu các child call đang chạy hủy.
3. Bỏ qua kết quả đến muộn sau khi parent đã kết thúc.
4. Giải phóng listener, call handle và tài nguyên thuộc request.

Không đóng ManagedChannel để hủy một child RPC. Channel có thể được nhiều request khác dùng chung; hủy channel sẽ ảnh hưởng những call không liên quan. Hãy hủy đúng ClientCall của child.

## 2. Cancellation và deadline là hai tín hiệu bổ sung

Cancellation biểu thị parent caller không còn cần kết quả. Deadline giới hạn thời gian còn được phép xử lý. Nếu deadline của parent hết hạn, parent call bị hủy; nếu caller chủ động cancel trước đó, parent có thể bị hủy trong khi deadline vẫn còn.

| Tín hiệu từ parent | Hành động với child RPC |
| --- | --- |
| Explicit cancellation | Hủy child call ngay khi nhận tín hiệu. |
| Parent deadline còn hiệu lực | Child chỉ được dùng phần thời gian còn lại của parent. |
| Parent deadline hết hạn | Không tạo child mới; hủy child đang chạy. |
| Parent hoàn tất bình thường | Để child cần thiết hoàn tất; dọn listener và handle. |
| Parent kết thúc do lỗi nghiệp vụ | Áp dụng chính sách của operation; không tự động coi mọi lỗi là cancellation. |

Đặt deadline mới dài hơn cho mỗi child có thể làm tổng thời gian vượt ngân sách request ban đầu. Ngược lại, chỉ truyền deadline mà không truyền explicit cancellation có thể khiến child tiếp tục tới khi deadline hết dù caller đã rời đi sớm.

## 3. Lấy Context của parent trong server handler

Trong gRPC Java, Context.current() trong server handler là context của RPC hiện tại. Context cung cấp deadline và trạng thái cancellation:

~~~java
Context parentContext = Context.current();
Deadline parentDeadline = parentContext.getDeadline();

if (parentContext.isCancelled()) {
    // Parent đã kết thúc; không khởi tạo downstream work.
    return;
}

if (parentDeadline != null && parentDeadline.isExpired()) {
    // Ngân sách của parent đã hết.
    return;
}
~~~

isCancelled() không cho biết nguyên nhân duy nhất. Explicit cancel, deadline expiry và một số tình huống transport đều có thể làm context bị hủy. getDeadline() và isExpired() giúp nhận biết deadline đã hết tại thời điểm kiểm tra.

gRPC Java có cơ chế propagation của Context trong các call path còn gắn context hiện tại. Khi tạo child call trong phạm vi context của parent, deadline/cancellation có thể được kế thừa theo cơ chế của thư viện. Tuy nhiên, khi code chuyển sang executor, detach context hoặc quản lý call handle qua một lifecycle riêng, cần bảo đảm context được capture/propagate và child được dừng đúng lúc. Ví dụ tiếp theo thể hiện cách nối tường minh qua call handle để kiểm soát và kiểm thử vòng đời child.

## 4. Nối parent cancellation tới async child RPC

Với async stub, ClientResponseObserver.beforeStart(...) cung cấp ClientCallStreamObserver đại diện cho child call. Giữ handle này để parent cancellation có thể gọi cancel(...).

Ví dụ Order service gọi Inventory:

~~~java
public void getSummary(
        SummaryRequest request,
        StreamObserver<SummaryReply> responseObserver) {

    Context parentContext = Context.current();
    AtomicBoolean parentCancelled =
            new AtomicBoolean(parentContext.isCancelled());
    AtomicBoolean cancelSent = new AtomicBoolean();
    AtomicBoolean cleaned = new AtomicBoolean();
    AtomicReference<ClientCallStreamObserver<StockRequest>> childCall =
            new AtomicReference<>();
    AtomicReference<StockReply> stockReply = new AtomicReference<>();

    Context.CancellationListener listener = ignored -> {
        parentCancelled.set(true);
        ClientCallStreamObserver<StockRequest> call = childCall.get();
        if (call != null && cancelSent.compareAndSet(false, true)) {
            call.cancel("Parent RPC cancelled", null);
        }
    };

    Runnable cleanup = () -> {
        if (cleaned.compareAndSet(false, true)) {
            parentContext.removeListener(listener);
            childCall.set(null);
        }
    };

    parentContext.addListener(listener, Runnable::run);

    if (parentCancelled.get() || parentContext.isCancelled()) {
        cleanup.run();
        return;
    }

    Deadline deadline = parentContext.getDeadline();
    InventoryGrpc.InventoryStub childStub = inventoryStub;
    if (deadline != null) {
        long remainingNanos =
                deadline.timeRemaining(TimeUnit.NANOSECONDS);
        if (remainingNanos <= 0) {
            cleanup.run();
            if (!parentContext.isCancelled()) {
                responseObserver.onError(Status.DEADLINE_EXCEEDED
                        .withDescription("Hết ngân sách thời gian của parent RPC")
                        .asRuntimeException());
            }
            return;
        }
        childStub = childStub.withDeadlineAfter(
                remainingNanos, TimeUnit.NANOSECONDS);
    }

    ClientResponseObserver<StockRequest, StockReply> childObserver =
            new ClientResponseObserver<>() {
                @Override
                public void beforeStart(
                        ClientCallStreamObserver<StockRequest> call) {
                    childCall.set(call);
                    // Parent có thể bị hủy trước khi child handle xuất hiện.
                    if (parentCancelled.get() || parentContext.isCancelled()) {
                        if (cancelSent.compareAndSet(false, true)) {
                            call.cancel("Parent RPC already cancelled", null);
                        }
                    }
                }

                @Override
                public void onNext(StockReply reply) {
                    if (!parentCancelled.get()
                            && !parentContext.isCancelled()) {
                        stockReply.set(reply);
                    }
                }

                @Override
                public void onError(Throwable failure) {
                    cleanup.run();
                    if (!parentCancelled.get()
                            && !parentContext.isCancelled()) {
                        responseObserver.onError(mapChildFailure(failure));
                    }
                }

                @Override
                public void onCompleted() {
                    cleanup.run();
                    if (parentCancelled.get()
                            || parentContext.isCancelled()) {
                        return;
                    }

                    StockReply stock = stockReply.get();
                    if (stock == null) {
                        responseObserver.onError(Status.INTERNAL
                                .withDescription("Inventory không trả kết quả")
                                .asRuntimeException());
                        return;
                    }

                    responseObserver.onNext(toSummary(request, stock));
                    responseObserver.onCompleted();
                }
            };

    try {
        childStub.getStock(toStockRequest(request), childObserver);
    } catch (RuntimeException failure) {
        cleanup.run();
        if (!parentContext.isCancelled()) {
            responseObserver.onError(mapChildFailure(failure));
        }
    }
}
~~~

Đây là một mẫu cho unary downstream async call; các kiểu InventoryGrpc, StockRequest, StockReply, mapChildFailure(...) và toSummary(...) thuộc ứng dụng minh họa. Cần chú ý:

- Listener của parent đặt cờ và hủy child handle nếu handle đã có.
- beforeStart(...) lưu handle rồi kiểm tra lại cờ. Điều này xử lý trường hợp parent bị hủy trước khi gRPC tạo child call.
- cancelSent tránh gửi lệnh cancel lặp từ listener và beforeStart.
- onNext(...) bỏ qua kết quả đến sau khi parent bị hủy.
- onError(...) và onCompleted() dọn listener. Chúng chỉ gửi terminal callback lên parent nếu parent vẫn còn hoạt động.
- cleanup idempotent để nhiều đường kết thúc không gỡ lifecycle nhiều lần.

Trong code production, nếu parent đã hết deadline trước khi child được tạo, nên kết thúc theo policy của handler và không khởi tạo child. Nếu parent call đã đóng thì không gửi thêm status; nếu call vẫn mở và deadline của một bước xử lý hết, có thể trả status phù hợp.

## 5. Xử lý race khi child handle chưa sẵn sàng

Một race quan trọng xảy ra giữa lúc parent bị hủy và lúc async stub gọi beforeStart(...):

| Thứ tự | Điều gì xảy ra | Cách xử lý |
| --- | --- | --- |
| Child handle có trước | Listener lấy được handle và gọi cancel. | Child dừng theo call-level cancellation. |
| Parent cancel trước | Listener đặt parentCancelled, nhưng chưa có handle để hủy. | beforeStart lưu handle rồi thấy cờ và cancel ngay. |
| Cancel xảy ra đồng thời với beforeStart | Một nhánh có thể chưa thấy handle. | Cả hai nhánh kiểm tra cùng cờ; cancelSent chỉ cho một nhánh phát lệnh. |
| Child hoàn tất trước khi parent cancel | Terminal callback dọn listener và hoàn tất parent nếu parent còn mở. | Parent cancellation đến sau không còn child active để hủy. |

Không lưu child call handle vào field mutable của Spring singleton. Mỗi parent RPC phải có reference, cờ và listener riêng. Nếu một parent gọi nhiều child, dùng registry riêng cho parent đó để hủy toàn bộ child còn active.

## 6. Truyền phần deadline còn lại

Parent có thể đã tiêu tốn một phần ngân sách trước khi gọi downstream. Hãy tính thời gian còn lại ngay trước khi tạo child call:

~~~java
Deadline deadline = parentContext.getDeadline();
InventoryGrpc.InventoryStub childStub = inventoryStub;

if (deadline != null) {
    long remaining = deadline.timeRemaining(TimeUnit.NANOSECONDS);
    if (remaining <= 0) {
        throw new ParentDeadlineExpiredException();
    }

    childStub = childStub.withDeadlineAfter(
            remaining, TimeUnit.NANOSECONDS);
}
~~~

Nếu parent còn 250 ms, child không nên được cấp lại 2 giây. withDeadlineAfter(...) đặt deadline cho child từ thời điểm gọi; vì vậy phải lấy timeRemaining(...) sát thời điểm tạo call, không lưu một giá trị thời gian còn lại quá sớm rồi dùng sau một khoảng chờ dài.

Nếu không có parent deadline, không tự suy ra một giá trị từ null. Hãy dùng policy mặc định của ứng dụng hoặc service config để bảo vệ downstream khỏi việc chờ vô hạn. Khi có deadline parent, child phải bị giới hạn bởi ngân sách còn lại và không được làm request gốc kéo dài hơn.

Trong grpc-java, context deadline có thể được kế thừa tự động trong call path còn gắn context. Việc đặt deadline tường minh hữu ích khi adapter muốn thể hiện ngân sách còn lại hoặc call được tạo sau khi context đã được chuyển qua một ranh giới bất đồng bộ. Không đặt một deadline mới dài hơn deadline cha.

## 7. Parent gọi nhiều downstream RPC

Nếu một handler gọi song song nhiều service, cancellation phải dừng tất cả child còn hoạt động. Có thể quản lý các call handle trong một registry thuộc riêng parent request:

~~~java
final class ChildCallRegistry {
    private final Set<ClientCallStreamObserver<?>> calls = new HashSet<>();
    private boolean cancelled;

    void register(ClientCallStreamObserver<?> call) {
        boolean cancelNow;
        synchronized (this) {
            cancelNow = cancelled;
            if (!cancelNow) {
                calls.add(call);
            }
        }
        if (cancelNow) {
            cancel(call);
        }
    }

    synchronized void unregister(ClientCallStreamObserver<?> call) {
        calls.remove(call);
    }

    void cancelAll() {
        List<ClientCallStreamObserver<?>> snapshot;
        synchronized (this) {
            cancelled = true;
            snapshot = new ArrayList<>(calls);
            calls.clear();
        }
        snapshot.forEach(this::cancel);
    }

    private void cancel(ClientCallStreamObserver<?> call) {
        call.cancel("Parent RPC cancelled", null);
    }
}
~~~

Registry dùng cùng một lock để phối hợp register() và cancelAll(): nếu call được đăng ký trước cancellation, nó nằm trong snapshot để hủy; nếu đăng ký sau, register() thấy cờ cancelled và hủy ngay. Sau khi child hoàn tất hoặc lỗi, gọi unregister(...). Khi parent bị hủy, gọi cancelAll() rồi dọn registry.

Nếu các child được gọi song song, chỉ gửi parent response sau khi các kết quả bắt buộc đã hoàn tất. Khi một child lỗi làm use case không thể tiếp tục, quyết định hủy các child còn lại theo policy của operation; đây là cancellation do lỗi điều phối, khác với parent caller cancellation nhưng cùng dùng cơ chế call-level cancel.

## 8. Context propagation qua executor

Context hiện tại không tự động xuất hiện trên mọi thread do ứng dụng tạo. Nếu handler dispatch công việc sang executor rồi mới tạo child RPC, hãy capture context:

~~~java
Context parentContext = Context.current();

executor.execute(parentContext.wrap(() -> {
    if (parentContext.isCancelled()) {
        return;
    }

    callDownstreamWithParentLifecycle(parentContext);
}));
~~~

wrap(...) gắn context đã capture trong lúc task chạy và khôi phục context trước đó sau khi task kết thúc. Nếu không propagate, child call tạo trên worker có thể không kế thừa đúng deadline/cancellation. Không lưu Context.current() vào field singleton hoặc dùng chung giữa các request.

Nếu worker có Future, nối parent cancellation tới Future.cancel(true) và vẫn hủy downstream call handle. Interrupt thread không phải lúc nào cũng dừng được I/O; call handle là cách điều khiển trực tiếp child gRPC. Các dependency HTTP/database khác cần API cancel/timeout riêng.

## 9. Cancellation không rollback side effect của child

Gọi childCall.cancel(...) chỉ báo rằng caller không còn cần kết quả của child. Child service có thể đã commit database hoặc gửi lệnh tới hệ thống ngoài trước khi nhận tín hiệu. Vì vậy:

- Không xem child cancellation là bằng chứng thao tác chưa xảy ra.
- Với RPC ghi, truyền idempotency key ổn định xuống child.
- Nếu parent cần bảo đảm nhiều bước cùng thành công/thất bại, dùng saga/state machine và compensation phù hợp.
- Nếu child đã chấp nhận command bền vững, cung cấp operation ID và API tra cứu trạng thái; cancellation của parent không tự xóa command đã commit.
- Không retry child chỉ vì parent bị hủy. Retry phải xuất phát từ một operation còn được caller/ứng dụng yêu cầu và phải an toàn với side effect.

Ví dụ: Order service gọi Payment để authorize. Nếu parent bị hủy sau khi Payment đã authorize, child cancel không tự giải phóng authorization. Hệ thống cần idempotency key và một bước void/compensation theo trạng thái thanh toán nếu nghiệp vụ yêu cầu.

## 10. Kiểm thử propagation

Test nên chứng minh parent cancellation thực sự tới child call, không chỉ kiểm tra parent context đã cancelled:

1. Dùng downstream in-process server giữ một RPC chưa hoàn tất.
2. Gọi parent handler qua server in-process thứ hai; parent tạo child async call.
3. Dùng latch xác nhận child handler đã bắt đầu.
4. Hủy parent call từ client bằng ClientCallStreamObserver.cancel(...).
5. Downstream server đăng ký ServerCallStreamObserver.setOnCancelHandler(...); chờ latch và xác minh child nhận cancellation.
6. Xác minh parent không gửi thêm response và listener/registry được dọn.

Các ca bổ sung:

- Parent bị hủy trước khi child beforeStart chạy; child phải bị cancel ngay khi handle xuất hiện.
- Parent deadline hết; child cũng không được chạy vượt ngân sách còn lại.
- Parent explicit cancel khi deadline vẫn còn; child phải dừng trước deadline.
- Một trong nhiều child lỗi; xác minh policy có hủy các child còn lại hay không.
- Child commit side effect trước cancellation; xác minh idempotency/status lookup phản ánh đúng kết quả.
- Executor từ chối task hoặc child call khởi tạo ném exception đồng bộ; listener và handle phải được cleanup.

In-process test xác minh lifecycle gRPC nhưng không thay thế test qua TCP/TLS, proxy và service mesh. Mạng thật giúp đánh giá độ trễ cancellation propagation và trường hợp peer mất kết nối âm thầm.

## 11. Quan sát và lỗi thường gặp

Nên đo số child call active theo parent method, thời gian từ parent cancellation tới child termination, số child bị hủy, status cuối cùng và số listener/handle còn tồn tại sau terminal event. Log nên có parent trace ID, child method, status và thời gian; không log payload hoặc token.

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Parent cancel nhưng child vẫn chạy | Chỉ hủy parent response hoặc không giữ child call handle. | Nối parent listener với ClientCallStreamObserver.cancel(...). |
| Child không bị hủy khi cancel rất sớm | Listener chạy trước khi child handle được tạo. | Dùng cờ cancellation và kiểm tra lại trong beforeStart. |
| Child chạy lâu hơn parent | Cấp timeout mới thay vì truyền ngân sách còn lại. | Dùng Deadline.timeRemaining(...). |
| Child được tạo trên worker không thấy parent context | Context không được propagate qua executor. | Capture context và dùng wrap(...)/context-aware executor. |
| Một request hủy child của request khác | Dùng field call handle chung trong singleton. | Registry và state riêng theo parent RPC. |
| Parent hoàn tất nhưng listener còn giữ tham chiếu | Quên remove listener/unregister child. | Cleanup ở mọi terminal path: complete, error, cancel và start failure. |
| Retry child sau parent cancellation gây ghi trùng | Coi cancellation là rollback. | Idempotency key, trạng thái operation và compensation. |

## 12. Bài tập thực hành

1. Viết server handler gọi một downstream unary async RPC; lấy child call handle bằng ClientResponseObserver.beforeStart(...).
2. Đăng ký Context.CancellationListener để hủy child; xử lý race khi parent cancel trước khi child handle xuất hiện.
3. Truyền deadline còn lại của parent sang child và kiểm tra không cấp lại timeout đầy đủ.
4. Mở hai downstream call song song; dùng registry riêng của parent để hủy mọi child khi parent bị cancel.
5. Chuyển việc tạo child call sang executor; dùng Context.wrap(...) và xác minh deadline/cancellation vẫn được truyền.
6. Viết in-process test chứng minh child server nhận cancellation khi parent client hủy call.
7. Thử cancellation sau khi child đã commit side effect; xác minh idempotency/status lookup và compensation theo nghiệp vụ.

Sau bài này, bạn cần biết nối cancellation của parent RPC tới từng downstream call, truyền deadline còn lại, xử lý race khi call handle chưa sẵn sàng và dọn listener/registry ở mọi terminal path. Parent cancellation giúp ngừng công việc con không còn cần thiết, nhưng không rollback side effect đã commit; idempotency và trạng thái operation vẫn cần thiết để giữ tính đúng đắn của hệ thống Spring gRPC.

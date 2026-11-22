# DEADLINE_EXCEEDED do downstream chậm

Trong **SPRING_GRPC**, một RPC thường gọi một hoặc nhiều dependency như inventory, pricing, database hoặc REST service. Nếu downstream phản hồi chậm, tổng thời gian xử lý có thể vượt deadline mà client đã đặt. Client khi đó nhận `DEADLINE_EXCEEDED`; server cũng nhận trạng thái cancellation trong Context và cần dừng phần công việc còn có thể dừng an toàn.

Lỗi này không đơn giản có nghĩa downstream “bị treo”. RPC có thể hết deadline do queue chờ worker, chờ connection pool, nhiều lần retry, xử lý tuần tự nhiều dependency hoặc thời gian mapping/serialize response. Muốn xử lý đúng, cần theo dõi budget xuyên suốt request, truyền phần thời gian còn lại xuống dependency, đặt timeout riêng cho I/O và tránh retry làm cạn budget.

## 1. Deadline khác timeout của một dependency

**Deadline** là thời điểm cuối cùng mà toàn bộ RPC được phép hoàn tất. **Timeout** thường giới hạn thời gian chờ của một thao tác cụ thể, chẳng hạn query database hoặc HTTP response.

Ví dụ client đặt deadline 900 ms cho `GetOrder`. Server cần gọi inventory và pricing, sau đó tổng hợp kết quả:

| Công đoạn | Budget dự kiến |
| --- | ---: |
| Queue và dispatch | 50 ms |
| Inventory downstream | 300 ms |
| Pricing downstream | 250 ms |
| Mapping và xử lý nghiệp vụ | 150 ms |
| Serialize và gửi response | 100 ms |
| Tổng | 850 ms |

Phần còn lại là headroom cho biến động. Nếu server cho mỗi downstream timeout 900 ms, hai call tuần tự có thể kéo dài gần 1.8 giây, vượt deadline tổng.

Deadline gRPC được biểu diễn theo thời điểm đơn điệu (monotonic time), tránh phụ thuộc trực tiếp vào việc đồng hồ hệ thống bị chỉnh. Khi truyền sang dependency, nên dùng remaining time tại thời điểm chuẩn bị gọi, không lấy lại budget ban đầu của client.

## 2. Client phải đặt deadline cho RPC

Nếu client không đặt deadline, RPC có thể chờ quá lâu tùy behavior của dependency và transport. Đặt deadline theo yêu cầu nghiệp vụ:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub client =
        CatalogServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(900, TimeUnit.MILLISECONDS);

GetOrderReply reply = client.getOrder(
        GetOrderRequest.newBuilder()
                .setOrderId("order-42")
                .build());
```

Chọn deadline theo latency mục tiêu và SLA của operation. Không đặt một giá trị quá ngắn cho mọi RPC; thao tác đọc cache và thao tác tổng hợp nhiều service có profile khác nhau. Cũng không đặt deadline quá dài chỉ để giảm lỗi nhìn thấy được, vì request hết giá trị vẫn chiếm thread, connection và tài nguyên downstream.

Nếu client là service trung gian, deadline của inbound RPC phải được xem là giới hạn tổng. Không bắt đầu một downstream operation với budget lớn hơn thời gian còn lại của request cha.

## 3. Đọc remaining deadline ở server

Trong server handler, gRPC Context hiện tại có thể chứa deadline của inbound call:

```java
Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (rpcContext.isCancelled()) {
    throw Status.CANCELLED
            .withDescription("RPC is no longer active")
            .asRuntimeException();
}

long remainingNanos = deadline == null
        ? TimeUnit.MILLISECONDS.toNanos(900)
        : deadline.timeRemaining(TimeUnit.NANOSECONDS);
```

Nếu không có deadline inbound, service vẫn nên áp dụng một maximum operation budget nội bộ. Không dùng `null` để hiểu rằng downstream được chờ vô hạn.

Cần chừa thời gian cho bước sau downstream. Ví dụ reserve 60 ms cho mapping và response:

```java
long responseReserveNanos =
        TimeUnit.MILLISECONDS.toNanos(60);

long downstreamBudgetNanos =
        Math.min(
                TimeUnit.MILLISECONDS.toNanos(500),
                remainingNanos - responseReserveNanos);

if (downstreamBudgetNanos <= 0) {
    throw Status.DEADLINE_EXCEEDED
            .withDescription("Insufficient time to call dependency")
            .asRuntimeException();
}
```

Budget của dependency là giá trị nhỏ hơn giữa giới hạn riêng của dependency và thời gian inbound còn lại sau khi trừ reserve. Không làm tròn remaining time lên một timeout lớn hơn deadline thực tế.

Đóng phép tính vào helper để các adapter dùng cùng một quy tắc. Khi request không có deadline, helper vẫn áp dụng maximum dependency time làm giới hạn nội bộ:

```java
public long forDownstream(
        Context context,
        Duration maxDependencyTime,
        Duration responseReserve) {

    Deadline deadline = context.getDeadline();
    long remaining = deadline == null
            ? maxDependencyTime.plus(responseReserve).toNanos()
            : deadline.timeRemaining(TimeUnit.NANOSECONDS);

    return Math.min(
            maxDependencyTime.toNanos(),
            remaining - responseReserve.toNanos());
}
```

## 4. Truyền remaining deadline sang gRPC downstream

Một service gọi downstream bằng blocking stub có thể áp dụng budget vừa tính:

```java
long budgetNanos = deadlineBudget.forDownstream(
        Context.current(),
        Duration.ofMillis(500),
        Duration.ofMillis(60));

if (budgetNanos <= 0) {
    throw Status.DEADLINE_EXCEEDED
            .withDescription("Insufficient downstream budget")
            .asRuntimeException();
}

InventoryReply inventory = inventoryStub
        .withDeadlineAfter(budgetNanos, TimeUnit.NANOSECONDS)
        .getStock(
                InventoryRequest.newBuilder()
                        .setSku(order.getSku())
                        .build());
```

`deadlineBudget` là helper ứng dụng thực hiện phép tính ở phần trước. Dùng `withDeadlineAfter` ngay trước call để downstream nhận giới hạn phù hợp với thời gian còn lại tại thời điểm đó.

Không giả định mọi client stub hoặc custom executor đều tự mang đúng deadline của inbound RPC. Với grpc-java, Context có cơ chế propagation, nhưng adapter nên xác minh behavior của phiên bản và cách tạo stub/call options đang dùng. Thiết lập deadline rõ ràng ở outbound boundary làm budget dễ kiểm tra và tránh phụ thuộc vào việc Context có được gắn đúng thread hay không.

Nếu offload call sang executor, capture và wrap Context trước khi submit. Nếu không, worker có thể mất deadline/cancellation context của request:

```java
Context rpcContext = Context.current();

executor.execute(rpcContext.wrap(() -> {
    callInventoryWithRemainingBudget(rpcContext);
}));
```

Executor phải có giới hạn; queue wait cũng tiêu thụ deadline. Nếu task chỉ bắt đầu sau khi budget gần hết, từ chối sớm có thể tốt hơn gọi downstream rồi chắc chắn timeout.

## 5. Một request gọi nhiều downstream

Với call tuần tự, mỗi bước phải tính lại remaining time sau khi bước trước kết thúc:

```java
InventoryReply stock = callInventoryWithBudget(
        order.getSku(), currentBudget());

PricingReply price = callPricingWithBudget(
        order.getSku(), currentBudget());

return orderMapper.toReply(order, stock, price);
```

Không tính hai budget một lần ở đầu request rồi sử dụng nguyên giá trị cho cả hai call. Thời gian inventory đã tiêu thụ làm giảm budget còn lại cho pricing.

Nếu hai downstream độc lập và có thể gọi song song, dùng fan-out có giới hạn concurrency. Mỗi call nhận budget không vượt remaining deadline, nhưng parent chỉ hoàn tất khi các kết quả cần thiết đã về hoặc policy cho phép partial result. Hủy các call còn lại khi kết quả không còn cần thiết hoặc parent đã bị cancel.

Không tạo một thread không giới hạn cho mỗi downstream. Dùng executor/bulkhead có giới hạn và đặt timeout cho queue wait. Với nhiều dependency, tổng thời gian không chỉ là latency mạng mà còn gồm scheduling, connection acquisition, retry và aggregation.

## 6. Đặt timeout ở từng loại dependency

Deadline gRPC không tự cấu hình timeout cho JDBC, HTTP client hoặc SDK. Mỗi dependency cần timeout phù hợp:

| Dependency | Timeout/cancellation cần cấu hình |
| --- | --- |
| gRPC downstream | `withDeadlineAfter` hoặc deadline theo remaining budget |
| HTTP client | Connect timeout, response/read timeout và request cancellation |
| JDBC | Query/statement timeout, network timeout và khả năng cancel của driver |
| Redis/cache client | Command timeout và giới hạn connection acquisition |
| Object storage/SDK | API call timeout, attempt timeout và abort/cancel nếu hỗ trợ |
| Executor | Queue capacity, queue wait limit và rejection policy |

Không đặt HTTP read timeout bằng toàn bộ deadline nếu còn bước khác sau HTTP. Tương tự, một JDBC query timeout quá dài có thể giữ connection sau khi client đã nhận `DEADLINE_EXCEEDED`.

Một số JDBC API chỉ nhận timeout theo giây. Không làm tròn lên tùy tiện nếu remaining budget nhỏ hơn một giây; dùng database/driver timeout có độ phân giải phù hợp hoặc giới hạn operation khác để tránh vượt deadline. Luôn kiểm tra behavior thực tế của driver.

## 7. Retry có thể làm deadline cạn nhanh hơn

Retry hữu ích với lỗi transient, nhưng mỗi lần thử và backoff đều tiêu thụ cùng một end-to-end budget. Không cấp lại toàn bộ timeout cho từng attempt.

Ví dụ budget còn 400 ms:
- Attempt đầu dùng 180 ms rồi nhận lỗi transient.
- Backoff 50 ms.
- Attempt thứ hai chỉ còn khoảng 170 ms, chưa kể response reserve.

Nếu không đủ thời gian cho một attempt có ý nghĩa, dừng retry và trả status phù hợp. Retry cần:
- Chỉ áp dụng cho lỗi được xác định là transient.
- Có backoff và jitter.
- Tôn trọng deadline còn lại.
- Giới hạn số attempt.
- Chỉ retry thao tác idempotent hoặc có idempotency key.
- Tránh retry một operation có thể đã commit nhưng response về trễ.

`DEADLINE_EXCEEDED` không chứng minh server chưa thực hiện operation. Một write có thể đã commit nhưng response không tới client kịp thời. Retry write mà không có idempotency protection có thể tạo side effect trùng lặp.

## 8. Cancellation khi deadline hết

Khi deadline inbound hết, server Context bị cancel. Handler và application work nên kiểm tra cancellation ở các điểm an toàn:

```java
Context context = Context.current();

if (context.isCancelled()) {
    return;
}

InventoryReply result = inventoryStub
        .withDeadlineAfter(
                remainingBudgetNanos(context),
                TimeUnit.NANOSECONDS)
        .getStock(request);

if (context.isCancelled()) {
    return;
}

observer.onNext(mapper.toProto(result));
observer.onCompleted();
```

Đoạn code minh họa luồng đồng bộ. Nếu handler chạy bất đồng bộ, phải wrap Context khi submit và đảm bảo worker không phát response sau khi call đã bị cancel.

Cancellation không tự ngắt mọi I/O. JDBC driver, socket hoặc SDK có thể tiếp tục chạy nếu không có timeout/cancel API riêng. Đăng ký cancellation handler để yêu cầu dừng worker, đóng cursor/stream và giải phóng resource. `Future.cancel(true)` chỉ gửi interrupt; cần kiểm chứng dependency có phản ứng với interrupt hay không.

Không gửi `onError(DEADLINE_EXCEEDED)` từ server sau khi transport đã đóng call do deadline. Client đã nhận status từ gRPC runtime; server cần cleanup và ghi telemetry phù hợp.

## 9. Phân biệt lỗi downstream với deadline tổng

Không phải mọi `DEADLINE_EXCEEDED` đều do downstream chậm. Có thể chia thành:

- **Queue delay**: request chờ worker hoặc connection pool trước khi gọi downstream.
- **Dependency latency**: downstream xử lý lâu hoặc không phản hồi.
- **Retry amplification**: nhiều attempt và backoff ăn hết budget.
- **Fan-out tail latency**: một dependency chậm giữ toàn bộ response.
- **Local processing**: mapping, lock contention hoặc CPU saturation.
- **Response path**: server hoàn tất gần deadline nhưng serialization/network khiến client nhận muộn.

Một downstream call có deadline riêng hết hạn là tín hiệu quan trọng, nhưng cần ghi nhận stage và thời gian đã dùng để biết đó có phải nguyên nhân gốc. Không gán mọi lỗi cho service downstream chỉ từ status cuối cùng.

## 10. Quan sát budget và latency theo từng stage

Để tìm đúng điểm nghẽn, ghi nhận các số liệu có thể so sánh:

| Measurement | Mục đích |
| --- | --- |
| Inbound deadline remaining khi nhận request | Biết caller còn bao nhiêu budget |
| Queue wait và executor active/queue depth | Phát hiện nghẽn worker |
| Connection pool acquisition time | Phát hiện cạn connection |
| Downstream latency theo service/method | Tìm dependency chậm |
| Retry count và backoff duration | Đo retry amplification |
| Local processing/serialization time | Phát hiện chi phí trong service |
| RPC final status và total duration | Đối chiếu deadline với latency thực tế |

Dùng trace span cho từng downstream call để thấy stage nào tiêu tốn budget. Có thể ghi remaining budget lúc bắt đầu call và status lúc kết thúc, nhưng không ghi token hoặc payload nhạy cảm.

Metrics label nên giới hạn ở service, method, dependency và status code. Không đưa order ID, user ID hoặc trace ID vào label vì cardinality cao. Dùng trace/log correlation để tra cứu một request cụ thể.

## 11. Test deadline propagation với downstream chậm

Dùng hai in-process server để kiểm tra cả đường truyền budget: server Inventory chứa `slowDownstream`; server Order chứa `OrderService`, service này gọi Inventory bằng `withDeadlineAfter` theo helper ở trên. Cho Inventory chờ bằng latch và đặt deadline ngắn ở client Order:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub client =
        CatalogServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(150, TimeUnit.MILLISECONDS);

StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> client.getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("order-42")
                        .build()));

assertEquals(
        Status.Code.DEADLINE_EXCEEDED,
        Status.fromThrowable(error).getCode());
assertTrue(slowDownstream.started.await(2, TimeUnit.SECONDS));
assertTrue(slowDownstream.cancelled.await(2, TimeUnit.SECONDS));
assertTrue(slowDownstream.cleaned.await(2, TimeUnit.SECONDS));
```

`slowDownstream` là test service có latch `started`, `cancelled` và `cleaned`; khi call downstream bị cancel/deadline hết, handler ghi nhận cancellation, giải phóng worker và đóng resource. `OrderService` phải tính lại remaining budget rồi đặt deadline cho Inventory call; nếu chỉ đặt deadline ở client Order mà không áp dụng budget ở outbound call, test chưa chứng minh propagation. Trong test hoàn chỉnh, xác nhận worker cleanup và đóng cả hai server, hai channel cùng executor trong `finally`.

Dùng timeout chờ đủ rộng cho CI nhưng vẫn có upper bound. Không dùng `Thread.sleep` để giả lập đồng bộ vì nó không chứng minh downstream đã nhận request hoặc cancellation đã chạy.

## 12. Test helper tính remaining budget

Tách phép tính budget thành helper thuần Java để kiểm tra biên:

```java
long downstreamBudgetNanos(
        long remainingNanos,
        Duration maxDependencyTime,
        Duration responseReserve) {

    return Math.min(
            maxDependencyTime.toNanos(),
            remainingNanos - responseReserve.toNanos());
}
```

Các test cần bao gồm:
- Remaining budget lớn hơn giới hạn dependency → dùng giới hạn dependency.
- Remaining budget nhỏ → dùng phần còn lại sau reserve.
- Remaining budget bằng reserve → kết quả bằng zero.
- Remaining budget nhỏ hơn reserve → kết quả âm và adapter không gọi downstream.
- Deadline không có hoặc không giới hạn → áp dụng maximum operation budget nội bộ.

Đảm bảo adapter kiểm tra `budgetNanos <= 0` trước khi gọi stub. Không truyền duration âm hoặc zero cho downstream và không dựa vào client library để tự diễn giải trường hợp này.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Mỗi downstream dùng timeout bằng deadline tổng | Tổng thời gian vượt deadline | Tính remaining budget cho từng call |
| Không đặt deadline cho client | RPC có thể chờ quá lâu | Đặt deadline theo SLA |
| Không giới hạn queue | Request hết deadline khi chưa chạy | Bounded executor và queue wait limit |
| Retry cấp lại full timeout | Retry kéo dài ngoài budget | Chia sẻ end-to-end budget |
| JDBC/HTTP không có timeout riêng | Worker và connection bị giữ sau RPC | Cấu hình dependency timeout/cancel |
| Không propagate cancellation | Downstream tiếp tục chạy sau khi caller bỏ cuộc | Context, cancel handler và API cancel |
| Làm tròn timeout lên | Dependency chạy lâu hơn budget còn lại | Giữ đơn vị chính xác hoặc giới hạn chặt |
| Retry write không idempotent | Side effect trùng khi response đến muộn | Idempotency key và retry policy |
| Chỉ nhìn status cuối cùng | Quy lỗi nhầm cho downstream | Trace từng stage và queue/connection wait |

## 14. Bài tập thực hành

1. Đặt deadline cho client `GetOrder` và ghi nhận total RPC duration.
2. Trong server, đọc `Context.current().getDeadline()` và tính remaining time.
3. Viết helper trừ response reserve và giới hạn tối đa cho từng dependency.
4. Gọi Inventory bằng stub có `withDeadlineAfter` theo budget còn lại.
5. Gọi Pricing sau đó và tính lại budget sau khi Inventory hoàn tất.
6. Đặt query timeout cho JDBC và response timeout cho HTTP theo cùng budget.
7. Mô phỏng downstream chậm bằng in-process server và latch.
8. Xác nhận client nhận `DEADLINE_EXCEEDED`, server nhận cancellation và worker cleanup.
9. Thử retry có backoff với operation idempotent; xác minh retry dừng khi budget không còn.
10. Thêm trace/metrics cho queue wait, downstream latency, retry count và remaining deadline.

### Ghi nhớ

**`DEADLINE_EXCEEDED` là dấu hiệu end-to-end RPC đã vượt thời gian cho phép; downstream chậm chỉ là một trong các nguyên nhân.** Đọc remaining deadline ở server, chừa response reserve, áp dụng budget nhỏ hơn cho từng downstream, cấu hình timeout riêng cho JDBC/HTTP và giới hạn retry. Khi deadline hết, propagate cancellation và cleanup worker/resource. Dùng trace theo stage và in-process test với latch để xác định đúng điểm tiêu thụ budget.

## Tài liệu tham khảo

- [gRPC — Deadlines](https://grpc.io/docs/guides/deadlines/)
- [gRPC — Cancellation](https://grpc.io/docs/guides/cancellation/)
- [gRPC Java — Deadline](https://grpc.github.io/grpc-java/javadoc/io/grpc/Deadline.html)
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html)
- [gRPC Java — AbstractStub](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/AbstractStub.html)
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)

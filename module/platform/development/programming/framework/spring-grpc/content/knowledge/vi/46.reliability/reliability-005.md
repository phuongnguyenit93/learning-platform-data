# Timeout budget qua nhiều downstream call

## Mục tiêu bài học

Trong **SPRING_GRPC**, một request inbound thường gọi nhiều downstream service theo chuỗi hoặc song song. Nếu mỗi hop tự đặt timeout đầy đủ như thể nó bắt đầu một request mới, tổng thời gian xử lý có thể vượt xa deadline mà caller đã cấp. Request có thể tiếp tục chạy dù caller đã timeout, giữ thread, connection và tài nguyên trong khi kết quả không còn được sử dụng.

Bài học tập trung vào **timeout budget qua nhiều downstream call**: hiểu deadline end-to-end, phân bổ thời gian cho queue và xử lý nội bộ, truyền deadline còn lại sang từng RPC, giới hạn timeout riêng theo dependency, phối hợp retry/backoff với budget chung, hủy công việc khi hết hạn và kiểm thử cả chuỗi call.

Sau bài này, bạn có thể:

1. Phân biệt timeout từng hop với deadline end-to-end.
2. Tính budget cho downstream calls tuần tự và song song.
3. Đọc deadline hiện hành từ gRPC Context và truyền nó tới client stub.
4. Áp dụng timeout cap riêng mà không vượt deadline của request cha.
5. Dành ngân sách cho queue, serialization và response delivery.
6. Dừng retry khi không còn đủ thời gian hoặc operation không an toàn.
7. Propagate cancellation và giải phóng tài nguyên khi deadline hết.
8. Quan sát deadline exhaustion và kiểm thử budget qua nhiều service.

> **Phạm vi:** Ví dụ dùng gRPC Java, Spring và generated stubs. Deadline được biểu diễn bằng io.grpc.Deadline; thời gian còn lại được tính bằng monotonic ticker. Các timeout theo dependency là policy do ứng dụng định nghĩa, không phải property mặc định của mọi Spring gRPC starter.

## 1. Timeout từng hop và deadline end-to-end

**Timeout** thường là giới hạn thời gian của một operation cụ thể, ví dụ kết nối database hoặc gọi Inventory Service. **Deadline** là thời điểm tuyệt đối mà toàn bộ RPC phải kết thúc. Khi một request đi qua nhiều service, deadline end-to-end mới là ngân sách có ý nghĩa với caller.

Ví dụ một request Order có deadline 800 ms và thực hiện:

1. Queue/admission: 40 ms.
2. Đọc profile: tối đa 120 ms.
3. Gọi Inventory: tối đa 250 ms.
4. Gọi Pricing: tối đa 180 ms.
5. Xử lý và serialize response: 70 ms.

Tổng worst-case dự kiến là 660 ms. Phần còn lại 140 ms là headroom cho network jitter, scheduler, response delivery và sai số đo. Nếu mỗi downstream tự đặt timeout 800 ms, chuỗi tuần tự có thể kéo dài hơn 1,6 giây, vi phạm deadline caller.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Connect timeout | Thời gian thiết lập kết nối | DNS/TLS/channel connection |
| Per-call timeout | Giới hạn riêng cho một dependency call | Inventory tối đa 250 ms |
| Deadline end-to-end | Thời điểm cuối của request từ caller | Tổng request không quá 800 ms |
| Queue timeout | Thời gian chờ được nhận vào worker/pool | Không chờ vô hạn |
| Idle timeout | Khoảng thời gian stream không có activity | Giới hạn stream im lặng |
| Retry budget | Thời gian/số attempt dành cho retry | Chỉ retry khi còn thời gian |

Timeout của một hop phải nằm bên trong deadline của request cha. Per-call timeout có thể ngắn hơn deadline còn lại, nhưng không được kéo dài deadline end-to-end.

## 2. Xây dựng budget theo critical path

Với các operation tuần tự, thời gian cần thiết xấp xỉ tổng thời gian của từng bước:

```text
D_total >= Q + L_local + D1 + D2 + ... + Dn + S + R
```

Trong đó:

- Q: queue/admission wait.
- L_local: xử lý nội bộ.
- D1..Dn: thời gian downstream calls.
- S: serialize/deserialize.
- R: response delivery và safety reserve.

Với các downstream chạy song song, tổng thời gian của nhánh song song bị chi phối bởi nhánh chậm nhất, không phải tổng tất cả nhánh:

```text
D_total >= Q + L_local + max(D1, D2, ..., Dn) + S + R
```

Nếu các nhánh song song có dependency nối tiếp bên trong, tính critical path của từng nhánh trước rồi lấy nhánh lớn nhất. Không cộng tất cả thời gian song song, nhưng cũng không giả định chúng hoàn toàn song song nếu executor, connection pool hoặc rate limit khiến chúng phải chờ nhau.

### 2.1. Ví dụ phân bổ ngân sách

Giả sử inbound deadline còn 900 ms tại thời điểm service bắt đầu:

| Giai đoạn | Budget mục tiêu |
| --- | ---: |
| Admission/queue | 50 ms |
| Xử lý local | 80 ms |
| Customer downstream | 180 ms |
| Inventory downstream | 300 ms |
| Pricing downstream | 160 ms |
| Serialize và response | 50 ms |
| Safety reserve | 80 ms |
| Tổng | 900 ms |

Nếu Inventory thực tế mất 260 ms, budget còn lại cho các bước sau giảm tương ứng. Không reset Pricing timeout về 160 ms nếu request đã tiêu thụ nhiều hơn dự kiến ở các bước trước.

Budget là giới hạn trên và mục tiêu thiết kế, không phải lời hứa mỗi hop sẽ được dùng hết phần thời gian được phân bổ. Nếu một dependency hoàn tất sớm, thời gian tiết kiệm được có thể dùng cho bước sau trong giới hạn deadline cha.

## 3. Deadline propagation trong gRPC Java

gRPC Java lưu deadline/cancellation của RPC hiện hành trong io.grpc.Context. Trong server handler, đọc deadline hiện hành bằng Context.current().getDeadline(). Khi tạo downstream call trong context đó, gRPC Java có thể áp dụng deadline từ context; việc này phụ thuộc context còn active tại thời điểm call được tạo.

Để code thể hiện rõ budget và dễ kiểm tra, có thể truyền deadline tường minh vào stub:

```java
Deadline inboundDeadline =
        io.grpc.Context.current().getDeadline();

if (inboundDeadline == null) {
    throw Status.FAILED_PRECONDITION
            .withDescription("Inbound RPC thiếu deadline")
            .asRuntimeException();
}

InventoryGrpc.InventoryBlockingStub inventoryStub =
        InventoryGrpc.newBlockingStub(inventoryChannel)
                .withDeadline(inboundDeadline);

GetStockResponse response =
        inventoryStub.getStock(request);
```

Một API có thể chọn policy default deadline cho caller không gửi deadline, nhưng phải áp dụng ngay tại boundary và ghi nhận policy đó. Với service-to-service API quan trọng, yêu cầu caller gửi deadline hữu hạn thường giúp hành vi dễ dự đoán hơn.

Không lưu deadline trong static field hoặc singleton mutable state. Deadline thuộc về một RPC cụ thể và phải đi cùng execution context của request đó.

### 3.1. Không reset timeout ở mỗi hop

Mẫu sai:

```java
// Sai: mỗi hop lại nhận toàn bộ 800 ms.
InventoryGrpc.InventoryBlockingStub stub =
        InventoryGrpc.newBlockingStub(channel)
                .withDeadlineAfter(800, TimeUnit.MILLISECONDS);
```

Nếu request đã dùng 500 ms trước khi gọi Inventory, cách trên vẫn cấp thêm 800 ms. Downstream có thể tiếp tục chạy sau khi caller đã hết deadline.

Mẫu đúng là truyền deadline tuyệt đối hiện hành:

```java
Deadline parentDeadline =
        io.grpc.Context.current().getDeadline();

InventoryGrpc.InventoryBlockingStub stub =
        InventoryGrpc.newBlockingStub(channel)
                .withDeadline(parentDeadline);
```

Nếu cần timeout riêng ngắn hơn, kết hợp deadline cha với dependency cap ở phần tiếp theo. Không chuyển deadline thành một timeout cố định mới ở mỗi tầng.

## 4. Áp dụng timeout cap cho từng dependency

Mỗi downstream có thể có latency profile và SLA riêng. Ví dụ Inventory có cap 300 ms, Pricing có cap 150 ms. Effective deadline là thời điểm sớm hơn giữa deadline cha và cap của dependency.

gRPC Deadline hỗ trợ phép lấy minimum giữa hai deadline:

```java
static Deadline effectiveDeadline(
        Deadline parent,
        Duration dependencyCap) {

    Deadline dependencyDeadline =
            Deadline.after(
                    dependencyCap.toNanos(),
                    TimeUnit.NANOSECONDS);

    return parent.minimum(dependencyDeadline);
}
```

Sử dụng với stub:

```java
Deadline parent =
        io.grpc.Context.current().getDeadline();

if (parent == null) {
    throw Status.FAILED_PRECONDITION
            .withDescription("Missing inbound deadline")
            .asRuntimeException();
}

Deadline inventoryDeadline =
        effectiveDeadline(parent, Duration.ofMillis(300));

InventoryGrpc.InventoryBlockingStub stub =
        InventoryGrpc.newBlockingStub(inventoryChannel)
                .withDeadline(inventoryDeadline);
```

Nếu deadline cha còn 90 ms, effective deadline vẫn chỉ còn tối đa 90 ms. Dependency cap 300 ms không được kéo dài deadline cha. Nếu dependency cap ngắn hơn, call dừng sớm để service còn cơ hội fallback hoặc trả response trước deadline tổng.

### 4.1. Kiểm tra remaining budget trước khi gọi

Có thể đọc thời gian còn lại:

```java
long remainingNanos =
        parent.timeRemaining(TimeUnit.NANOSECONDS);

if (remainingNanos <= minimumUsefulCallNanos) {
    throw Status.DEADLINE_EXCEEDED
            .withDescription("Không đủ budget cho downstream call")
            .asRuntimeException();
}
```

minimumUsefulCallNanos là ngưỡng policy của ứng dụng, dựa trên latency tối thiểu có ích và thời gian cần để xử lý kết quả. Đừng bắt đầu một call mà gần như chắc chắn không thể hoàn tất trước deadline.

Không dùng System.currentTimeMillis() để tự tính chênh lệch deadline. io.grpc.Deadline dùng monotonic ticker để tránh sai số khi wall clock thay đổi.

## 5. Dành budget cho queue và xử lý nội bộ

Một lỗi phổ biến là cấp gần như toàn bộ deadline cho downstream rồi không còn thời gian xử lý response. Budget cần tính từ lúc request đến service, bao gồm:

- Admission control và chờ worker.
- Lock contention hoặc semaphore wait.
- Deserialize request và validate.
- Business computation.
- Downstream RPC/database.
- Serialize response và gửi về caller.

Nếu queue wait tiêu thụ 200 ms trong budget 500 ms, downstream không còn 500 ms. Khi offload công việc sang executor, deadline phải được giữ qua thread boundary và kiểm tra trước khi bắt đầu task.

Ví dụ truyền gRPC Context sang worker:

```java
io.grpc.Context grpcContext =
        io.grpc.Context.current();

executor.execute(grpcContext.wrap(() -> {
    Deadline deadline = grpcContext.getDeadline();

    if (deadline != null && deadline.isExpired()) {
        return;
    }

    performBusinessWork();
}));
```

Nếu executor từ chối task, map rejection theo policy capacity. Nếu task đã hết deadline trước khi chạy, bỏ qua công việc và giải phóng permit/queue accounting. Không giữ task hết hạn trong queue chỉ để nó chạy rồi phát hiện kết quả không còn hữu ích.

## 6. Downstream tuần tự và song song

### 6.1. Calls tuần tự

Nếu service gọi Customer rồi mới gọi Pricing, call thứ hai phải dùng deadline còn lại sau call đầu. Truyền cùng absolute deadline là cách đơn giản nhất:

```java
Deadline deadline = Context.current().getDeadline();

Customer customer = customerStub
        .withDeadline(deadline)
        .getCustomer(customerRequest);

Price price = pricingStub
        .withDeadline(deadline)
        .getPrice(buildPriceRequest(customer));
```

Pricing nhận cùng deadline tuyệt đối, không nhận lại duration ban đầu. Nếu Customer mất nhiều thời gian, Pricing tự có ít thời gian hơn. Có thể thêm cap riêng bằng minimum như phần trước.

### 6.2. Calls song song

Khi gọi nhiều dependency độc lập, tạo từng call với effective deadline của cùng parent deadline. Chờ kết quả theo remaining budget chung, không chờ mỗi Future với một timeout mới bằng toàn bộ budget.

```java
Deadline parent = Context.current().getDeadline();

Future<Customer> customerFuture =
        executor.submit(() ->
                customerStub.withDeadline(parent)
                        .getCustomer(customerRequest));

Future<Price> priceFuture =
        executor.submit(() ->
                pricingStub.withDeadline(parent)
                        .getPrice(priceRequest));

long remaining =
        parent.timeRemaining(TimeUnit.NANOSECONDS);

Customer customer = customerFuture.get(
        remaining, TimeUnit.NANOSECONDS);

remaining = parent.timeRemaining(TimeUnit.NANOSECONDS);

Price price = priceFuture.get(
        remaining, TimeUnit.NANOSECONDS);
```

Đây là skeleton đơn giản. Trong code production cần xử lý ExecutionException, TimeoutException, cancellation và dọn dẹp cả hai Future. Nếu một nhánh thất bại khiến kết quả tổng thể không thể tạo, có thể hủy nhánh còn lại nếu không còn cần thiết. Nếu cả hai kết quả đều bắt buộc, deadline tổng phải bao phủ critical path và response processing.

Không gọi Future.get() tuần tự với cùng timeout duration ban đầu; làm vậy có thể chờ gấp đôi ngân sách. Luôn tính remaining từ deadline cha tại thời điểm chờ.

## 7. Retry phải tiêu thụ cùng budget

Retry không được tạo ngân sách mới. Tổng thời gian của attempts, backoff, queue và response vẫn nằm trong deadline inbound.

Một policy retry cần giới hạn:

- Số attempt tối đa.
- Tổng retry duration.
- Backoff và jitter.
- Loại status có thể retry.
- Idempotency hoặc deduplication.
- Thời gian tối thiểu còn lại để một attempt có ích.

Trước mỗi attempt, tính remaining từ cùng deadline cha. Nếu còn ít hơn minimumUsefulAttemptBudget, dừng retry và trả lỗi cuối cùng phù hợp.

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    long remaining =
            parentDeadline.timeRemaining(TimeUnit.NANOSECONDS);

    if (remaining <= minimumAttemptBudgetNanos) {
        throw Status.DEADLINE_EXCEEDED
                .withDescription("Retry budget đã cạn")
                .asRuntimeException();
    }

    try {
        return stub.withDeadline(parentDeadline)
                .getStock(request);
    } catch (StatusRuntimeException ex) {
        if (!isRetryable(ex.getStatus())
                || attempt == maxAttempts) {
            throw ex;
        }

        long backoff = computeBackoffWithJitter(attempt);
        if (backoff >= parentDeadline.timeRemaining(
                TimeUnit.NANOSECONDS)
                - minimumAttemptBudgetNanos) {
            throw ex;
        }

        sleepInterruptibly(backoff);
    }
}
```

Đây là pseudocode gần Java; sleepInterruptibly phải giữ interrupt status và xử lý cancellation. Trong production, ưu tiên retry framework/client policy hỗ trợ deadline-aware scheduling thay vì blocking sleep trên gRPC callback thread.

Không retry INVALID_ARGUMENT, PERMISSION_DENIED hoặc lỗi payload cố định. Với UNAVAILABLE/RESOURCE_EXHAUSTED, chỉ retry khi operation an toàn và policy cho phép. Retry không idempotent cần idempotency key hoặc deduplication ở provider.

## 8. Cancellation khi deadline hết

Khi inbound deadline hết hoặc caller hủy RPC, service nên dừng công việc không còn hữu ích. gRPC Context có cancellation signal; downstream call được tạo trong context phù hợp có thể nhận cancellation propagation. Với task chạy trên executor, phải giữ gRPC Context và có đường dừng cho công việc đang chạy.

Các nguyên tắc:

1. Kiểm tra Context cancellation trước khi bắt đầu bước tốn tài nguyên.
2. Truyền cùng deadline/cancellation context tới downstream.
3. Khi call cha kết thúc, hủy Future hoặc downstream operation còn chạy nếu không còn cần.
4. Release semaphore/permit và connection/resource đúng một lần.
5. Không gửi nhiều terminal callbacks cho cùng observer.
6. Không bỏ qua interrupt nếu worker được thiết kế để dừng theo interrupt.
7. Không tiếp tục retry sau deadline/cancellation.

Ví dụ liên kết cancellation của gRPC Context với một worker Future:

```java
io.grpc.Context rpcContext = io.grpc.Context.current();

Future<Result> work = executor.submit(
        rpcContext.wrap(this::performWork));

io.grpc.Context.CancellationListener listener =
        cancelledContext -> work.cancel(true);

rpcContext.addListener(listener, Runnable::run);
try {
    return work.get();
} finally {
    rpcContext.removeListener(listener);
}
```

Đây là pattern minh họa cho worker có thể dừng bằng interrupt. Nếu công việc dùng API async, hãy gọi cancellation API tương ứng của dependency. Listener phải được gỡ ở terminal path; cleanup tài nguyên và release permit cần được bảo vệ để chỉ chạy một lần.

Hủy Future không bảo đảm mọi thư viện downstream dừng ngay. Database driver, blocking I/O hoặc external API cần timeout/cancel support riêng. Kiểm tra semantics thực tế của từng dependency.

## 9. Timeout và status mapping

Status code cần phân biệt nguyên nhân:

| Tình huống | Status thường gặp | Ý nghĩa |
| --- | --- | --- |
| Deadline inbound hết | DEADLINE_EXCEEDED | Caller budget đã cạn |
| Client chủ động hủy | CANCELLED | Operation không còn được yêu cầu |
| Downstream tạm thời unavailable | UNAVAILABLE | Dependency không thể phục vụ tạm thời |
| Capacity cạn | RESOURCE_EXHAUSTED | Admission/quota/resource limit |
| Request sai | INVALID_ARGUMENT | Sửa input |
| Credential thiếu/sai | UNAUTHENTICATED | Xác thực thất bại |
| Identity không đủ quyền | PERMISSION_DENIED | Không retry cùng identity |
| Lỗi ngoài dự kiến | INTERNAL | Lỗi server không được phân loại |

Không map mọi downstream timeout thành UNAVAILABLE. Nếu deadline tổng đã hết, DEADLINE_EXCEEDED phản ánh đúng việc caller không còn budget. Nếu một dependency cap ngắn hơn deadline tổng và hết trước, service có thể trả DEADLINE_EXCEEDED hoặc status domain phù hợp theo public API contract; giữ mapping nhất quán và ghi nguyên nhân chi tiết vào telemetry.

Không trả stack trace hoặc hostname/credential nội bộ trong Status description. Ghi chi tiết đã redaction trong log/trace.

## 10. Streaming RPC và deadline dài

Streaming RPC có lifecycle dài hơn unary call. Deadline thường giới hạn toàn bộ RPC stream, không tự reset cho mỗi message. Cần phân biệt:

- Overall stream deadline.
- Idle timeout giữa các message.
- Per-message processing budget.
- Downstream call budget phát sinh trong lúc xử lý message.

Không đặt lại deadline tổng mỗi khi nhận message, nếu contract không định nghĩa một session mới. Nếu mỗi message gọi downstream, dùng deadline còn lại của stream và cap riêng cho operation đó.

Với stream dài, client có thể cần chia session theo thời gian hoặc reconnect/resume bằng cursor. Đừng giữ stream vô hạn để né deadline. Áp dụng flow control, bounded buffers và cancellation để tránh stream giữ memory/thread/connection không giới hạn.

## 11. Cấu hình deadline policy trong Spring

Có thể bind các cap theo dependency bằng @ConfigurationProperties. Ví dụ namespace app.grpc.deadlines là do ứng dụng tự định nghĩa:

```yaml
app:
  grpc:
    deadlines:
      default-inbound: 2s
      minimum-useful-call: 25ms
      safety-reserve: 60ms
      dependencies:
        inventory: 350ms
        pricing: 180ms
        customer: 220ms
```

Các giá trị cần dựa trên latency distribution, SLO và capacity thực tế. Không sao chép một cấu hình chung cho mọi method nếu workload khác nhau đáng kể.

Một policy object có thể cung cấp dependency cap và reserve:

```java
@ConfigurationProperties(prefix = "app.grpc.deadlines")
public record GrpcDeadlineProperties(
        Duration defaultInbound,
        Duration minimumUsefulCall,
        Duration safetyReserve,
        Map<String, Duration> dependencies) {
}
```

Validate mọi Duration phải dương, hữu hạn và nằm trong giới hạn cho phép. Kiểm tra rằng dependency cap không vượt service policy nếu điều đó gây hiểu nhầm; effective deadline vẫn luôn là minimum với deadline cha.

## 12. Observability cho budget

Để hiểu deadline bị tiêu thụ ở đâu, đo các mốc:

- Inbound deadline remaining khi service bắt đầu.
- Queue/admission wait.
- Local processing duration.
- Mỗi downstream call duration và remaining budget trước call.
- Retry count/backoff duration.
- Cancellation/deadline exceeded count.
- Tổng inbound RPC duration.
- Số operation tiếp tục chạy sau cancellation nếu có thể đo.

Có thể ghi span event hoặc attributes có cardinality thấp:

- dependency.name.
- timeout.policy.
- retry.attempt.
- remaining_budget_ms bucketed.
- deadline.outcome.

Không ghi raw request ID, tenant ID hoặc trace ID làm metric label. Không ghi deadline timestamp tuyệt đối nếu không cần; remaining duration và outcome thường hữu ích hơn.

Dashboard nên phân tách latency của từng downstream với tổng inbound latency. Nếu tổng latency cao nhưng downstream spans thấp, xem queue wait, local lock, serialization hoặc response scheduling.

## 13. Kiểm thử timeout budget

Test một downstream riêng không đủ. Cần test chuỗi nhiều hop để chứng minh deadline không bị reset.

Các tình huống:

1. **Sequential calls:** downstream đầu tiêu thụ một phần budget; downstream sau chỉ nhận deadline còn lại.
2. **Parallel calls:** tổng thời gian chờ bị giới hạn bởi parent deadline, không phải tổng timeout từng Future.
3. **Dependency cap:** cap ngắn hơn deadline cha làm call kết thúc sớm.
4. **Parent budget shorter:** deadline cha ngắn hơn cap; cap không kéo dài request.
5. **Queue delay:** task chờ lâu; không bắt đầu downstream call khi budget không còn đủ.
6. **Retry:** mỗi attempt dùng cùng deadline; backoff không vượt budget.
7. **Cancellation:** caller hủy; downstream và worker được cancel/cleanup.
8. **Streaming:** deadline tổng không reset theo message.
9. **Missing deadline:** default policy hoặc rejection được áp dụng nhất quán.
10. **Concurrent requests:** deadline/context của request này không rò sang request khác.

Dùng InProcessServerBuilder/InProcessChannelBuilder cho logic gRPC, latch và fake downstream để điều khiển latency. Tránh sleep cố định; dùng CountDownLatch, barriers và bounded test timeout. Dùng fake clock/ticker nếu policy code của ứng dụng hỗ trợ injection; gRPC Deadline cũng cho phép test ticker khi cần deterministic time behavior.

### 13.1. Assert deadline propagation

Có thể ghi lại remaining deadline tại fake downstream server khi request đến và xác minh:

- Deadline downstream không muộn hơn deadline cha.
- Remaining budget giảm theo thời gian đã tiêu thụ.
- Downstream cap có thể ngắn hơn parent.
- Call bị hủy khi parent deadline hết.
- Không có attempt mới bắt đầu sau khi hết retry budget.

Không assert millisecond chính xác trên CI vì scheduler và transport có jitter. Assert quan hệ và upper bound có tolerance hợp lý.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chuỗi ba hop vượt deadline caller | Mỗi hop đặt timeout mới bằng toàn bộ budget | Propagate absolute parent deadline |
| Downstream tiếp tục chạy sau khi caller timeout | Context/cancellation không được truyền hoặc dependency không hỗ trợ cancel | Giữ gRPC Context, cancel Future và đặt timeout ở dependency |
| Retry khiến request kéo dài gấp nhiều lần | Mỗi attempt dùng timeout mới | Dùng cùng deadline và retry budget |
| Parallel calls vượt budget | Mỗi Future chờ timeout đầy đủ theo lượt | Tính remaining từ parent trước mỗi lần wait |
| Dependency cap làm request tổng dài hơn | Cap được dùng thay deadline cha | Lấy minimum giữa parent deadline và dependency deadline |
| Queue làm cạn budget | Không đo queue wait hoặc không kiểm tra trước worker | Admission control, bounded queue và check remaining |
| Blocking sleep làm nghẽn callback thread | Retry/backoff chạy trên transport thread | Dùng scheduler/async retry policy |
| Streaming stream không bao giờ kết thúc | Deadline tổng bị reset theo message | Giữ overall deadline và idle timeout riêng |
| Deadline thiếu ở inbound | Caller không gửi deadline | Default policy hoặc yêu cầu deadline hữu hạn |
| Status không nhất quán | Mọi lỗi downstream đều map UNAVAILABLE | Phân biệt DEADLINE_EXCEEDED, CANCELLED và UNAVAILABLE |
| Test flaky | Dùng sleep và assert timing tuyệt đối | Dùng latch/fake ticker và quan hệ deadline |
| Worker/permit bị leak sau timeout | Cleanup không chạy khi cancel/exception | Release trong terminal path exactly once |

## 15. Bài tập thực hành

1. Xây dựng OrderService gọi Customer, Inventory và Pricing theo chuỗi.
2. Đặt inbound deadline hữu hạn từ generated client stub.
3. Đọc deadline từ gRPC Context ở server handler.
4. Truyền cùng absolute deadline tới từng downstream stub.
5. Thêm dependency cap bằng minimum giữa parent deadline và per-service deadline.
6. Dành safety reserve cho serialize/response và kiểm tra minimum useful budget trước mỗi call.
7. Thêm retry cho lỗi transient được phép, dùng cùng deadline và backoff/jitter.
8. Hủy downstream Future/call khi inbound request bị cancel hoặc deadline hết.
9. Tạo biến thể gọi hai downstream song song và chứng minh critical-path budget.
10. Thêm metrics/span events cho remaining budget, queue wait, dependency duration và retry.
11. Viết integration test sequential, parallel, dependency cap, retry exhaustion và cancellation.
12. Viết runbook phân tích DEADLINE_EXCEEDED theo từng hop và xác định nơi tiêu thụ budget.

### Câu hỏi tự kiểm tra

- Timeout từng hop khác deadline end-to-end như thế nào?
- Vì sao mỗi downstream không được cấp lại toàn bộ timeout ban đầu?
- Công thức budget khác nhau thế nào giữa calls tuần tự và song song?
- gRPC Java lưu deadline hiện hành ở đâu?
- Vì sao dùng absolute Deadline tốt hơn tự tính lại bằng wall clock?
- Làm thế nào áp dụng dependency cap mà không vượt deadline cha?
- Queue wait và serialization có cần nằm trong budget không?
- Retry/backoff tiêu thụ budget như thế nào?
- Khi nào phải dừng retry dù status có thể retry?
- Cancellation của inbound RPC cần tác động tới downstream và worker ra sao?
- Streaming overall deadline khác idle timeout và per-message budget thế nào?
- Làm thế nào test chứng minh deadline không bị reset qua nhiều hop?

## Tài liệu tham khảo

- [gRPC — Deadlines](https://grpc.io/docs/guides/deadlines/): deadline, propagation và timeout behavior.
- [gRPC — Cancellation](https://grpc.io/docs/guides/cancellation/): dừng RPC và công việc không còn cần thiết.
- [gRPC — Retry](https://grpc.io/docs/guides/retry/): retry policy và backoff.
- [gRPC Java — Deadline](https://grpc.github.io/grpc-java/javadoc/io/grpc/Deadline.html): deadline và remaining time.
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html): deadline/cancellation context.
- [gRPC Java — AbstractStub](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/AbstractStub.html): cấu hình deadline cho generated stub.
- [Google SRE — Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/): timeout, overload và retry behavior.
- [Google SRE — Handling Overload](https://sre.google/sre-book/handling-overload/): admission control và bảo vệ capacity.
- [OpenTelemetry — Semantic Conventions for RPC](https://opentelemetry.io/docs/specs/semconv/rpc/): quan sát RPC và status attributes.

**Kết quả mong đợi:** Người học thiết kế được timeout budget end-to-end cho Spring gRPC qua nhiều downstream calls, truyền deadline tuyệt đối còn lại thay vì reset timeout, áp dụng dependency cap, tính cả queue/retry/serialization, hủy công việc khi budget hết và kiểm thử được chuỗi tuần tự, song song cùng streaming mà không vượt deadline caller.

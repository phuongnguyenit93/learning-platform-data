# Future và CompletableFuture: một kết quả so với nhiều phần tử

Trong Java, `Future<T>` và `CompletableFuture<T>` mô tả một tác vụ sẽ có **một kết quả hoàn tất** trong tương lai. Kết quả đó có thể là một giá trị, `null`, hoặc một lỗi. Chúng phù hợp khi chương trình gọi một dịch vụ, truy vấn dữ liệu hay thực hiện phép tính và cần nhận lại một kết quả sau khi công việc kết thúc.

Một luồng sự kiện có nhiều phần tử lại có vòng đời khác: dữ liệu có thể đến từng phần tử, kéo dài theo thời gian và cần được điều tiết theo khả năng xử lý của bên nhận. `Future` và `CompletableFuture` không tự cung cấp mô hình truyền nhiều phần tử như vậy. Trong Reactive Programming, `Mono<T>` thường biểu diễn kết quả đơn lẻ, còn `Flux<T>` biểu diễn luồng từ không đến nhiều phần tử. Phân biệt hai mô hình giúp chọn đúng công cụ trong hệ sinh thái Java và tránh dùng một future đơn lẻ như thể nó là một stream.

## 1. Future biểu diễn một kết quả chưa sẵn sàng

`Future<T>` là interface trong Java Concurrency API. Nó đại diện cho kết quả của một tác vụ được thực thi ở nơi khác. Bên gọi có thể kiểm tra tác vụ đã xong chưa, chờ kết quả, chờ trong một khoảng thời gian hoặc yêu cầu hủy:

```java
Future<User> userFuture = executor.submit(
    () -> userRepository.findById(userId)
);

if (userFuture.isDone()) {
    // Tác vụ đã kết thúc; kết quả có thể đã thành công, lỗi hoặc bị hủy.
}

User user = userFuture.get();
```

`submit` trả về ngay một `Future<User>`. Khi gọi `get()`, luồng hiện tại sẽ chờ nếu tác vụ chưa hoàn tất. Đây là điểm quan trọng: việc khởi chạy tác vụ có thể bất đồng bộ, nhưng cách lấy kết quả bằng `get()` vẫn là thao tác blocking.

Các phương thức chính của `Future`:

| Phương thức | Ý nghĩa |
| --- | --- |
| `get()` | Chờ và lấy kết quả; ném `InterruptedException` hoặc `ExecutionException` khi phù hợp |
| `get(timeout, unit)` | Chờ tối đa thời gian chỉ định; có thể ném `TimeoutException` |
| `isDone()` | Kiểm tra tác vụ đã hoàn tất, kể cả thành công, lỗi hoặc hủy |
| `isCancelled()` | Kiểm tra tác vụ đã bị hủy |
| `cancel(mayInterruptIfRunning)` | Yêu cầu hủy; tham số cho biết có yêu cầu ngắt luồng đang chạy hay không |

Khi dùng `get()`, cần xử lý cả ba tình huống thường gặp. `InterruptedException` cho biết luồng đang chờ bị ngắt; thông thường nên khôi phục trạng thái interrupt trước khi chuyển tiếp hoặc kết thúc xử lý. `ExecutionException` bọc exception phát sinh trong tác vụ và có thể xem nguyên nhân qua `getCause()`. `TimeoutException` cho biết hết thời gian chờ, nhưng tự nó không hủy tác vụ nền.

```java
try {
    User user = userFuture.get(2, TimeUnit.SECONDS);
    process(user);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Luồng chờ bị ngắt", e);
} catch (ExecutionException e) {
    throw new UserLookupException("Không thể tải người dùng", e.getCause());
} catch (TimeoutException e) {
    userFuture.cancel(true);
    throw new UserLookupTimeoutException(userId, e);
}
```

Yêu cầu `cancel(true)` chỉ yêu cầu hủy và ngắt luồng thực thi nếu cơ chế chạy tác vụ hỗ trợ. Tác vụ đang gọi thư viện hoặc I/O không phản ứng với interrupt có thể vẫn tiếp tục. Vì vậy, timeout ở nơi chờ và timeout ở client kết nối tới dịch vụ là hai cấu hình khác nhau.

## 2. CompletableFuture bổ sung khả năng hoàn tất và nối bước xử lý

`CompletableFuture<T>` vừa triển khai `Future<T>`, vừa triển khai `CompletionStage<T>`. Ngoài khả năng lấy kết quả như `Future`, nó cho phép đăng ký các bước sẽ chạy khi kết quả sẵn sàng. Nhờ đó, bên gọi có thể mô tả chuỗi xử lý mà không cần chặn luồng để gọi `get()` sau từng bước.

```java
CompletableFuture<User> userFuture = CompletableFuture.supplyAsync(
    () -> userRepository.findById(userId),
    ioExecutor
);

CompletableFuture<UserView> viewFuture = userFuture
    .thenApply(userMapper::toView);

viewFuture.thenAccept(view -> responseSender.send(view));
```

`supplyAsync` khởi chạy hàm trả về một giá trị và hoàn tất future bằng giá trị đó. `thenApply` đăng ký một phép biến đổi nhận kết quả trước và tạo một stage mới. `thenAccept` nhận kết quả để thực hiện hành động không cần trả về giá trị.

Khi một stage hoàn tất, callback tiếp theo có thể được thực thi ngay trên luồng hoàn tất stage đó hoặc luồng gọi đăng ký callback nếu future đã hoàn tất trước khi callback được gắn. Các biến thể có hậu tố `Async` chuyển callback sang cơ chế thực thi bất đồng bộ; nếu không truyền executor, chúng thường dùng `ForkJoinPool.commonPool()`. Khi công việc có đặc tính riêng, nên truyền executor tường minh để kiểm soát tài nguyên và tránh đưa I/O blocking vào pool dùng chung.

```java
CompletableFuture<UserView> viewFuture = userFuture.thenApplyAsync(
    userMapper::toView,
    cpuExecutor
);
```

Ở đây, `ioExecutor` và `cpuExecutor` có thể được cấu hình riêng: executor đầu dành cho thao tác I/O, executor sau dành cho phép biến đổi dữ liệu tiêu tốn CPU. Tách executor giúp giới hạn ảnh hưởng khi một nhóm tác vụ chậm hoặc quá tải.

## 3. Nối tác vụ phụ thuộc và kết hợp tác vụ độc lập

Khi bước tiếp theo trả về một `CompletableFuture`, có hai kiểu nối cần phân biệt:

- `thenApply` biến đổi giá trị thành một giá trị mới. Nếu hàm trả về `CompletableFuture<X>`, kết quả sẽ là `CompletableFuture<CompletableFuture<X>>`.
- `thenCompose` nối future do hàm trả về vào chuỗi hiện tại và làm phẳng thành `CompletableFuture<X>`.

Ví dụ, tải đơn hàng trước rồi mới tải chi tiết giao hàng của đơn đó:

```java
CompletableFuture<Order> orderFuture =
    CompletableFuture.supplyAsync(() -> orderClient.find(orderId), ioExecutor);

CompletableFuture<Delivery> deliveryFuture = orderFuture.thenCompose(
    order -> deliveryClient.findForOrderAsync(order.getId())
);
```

`thenCompose` phù hợp với quan hệ phụ thuộc: phải có `order` mới biết cần tải delivery nào. Nếu hai dịch vụ độc lập, có thể khởi chạy cả hai rồi kết hợp kết quả bằng `thenCombine`:

```java
CompletableFuture<Customer> customerFuture =
    CompletableFuture.supplyAsync(() -> customerClient.find(customerId), ioExecutor);

CompletableFuture<List<Order>> ordersFuture =
    CompletableFuture.supplyAsync(() -> orderClient.findByCustomer(customerId), ioExecutor);

CompletableFuture<CustomerSummary> summaryFuture = customerFuture.thenCombine(
    ordersFuture,
    CustomerSummary::new
);
```

Hai lời gọi được khởi chạy độc lập. `thenCombine` tạo kết quả khi cả hai future hoàn tất thành công. Đây là phối hợp nhiều tác vụ một kết quả: mỗi future vẫn chỉ có một kết quả cuối cùng, và `summaryFuture` cũng chỉ có một `CustomerSummary`.

Với một nhóm tác vụ, `allOf` tạo future hoàn tất khi tất cả future đầu vào hoàn tất:

```java
List<CompletableFuture<Order>> orderFutures = orderIds.stream()
    .map(id -> CompletableFuture.supplyAsync(
        () -> orderClient.find(id), ioExecutor
    ))
    .collect(Collectors.toList());

CompletableFuture<List<Order>> allOrders = CompletableFuture
    .allOf(orderFutures.toArray(new CompletableFuture<?>[0]))
    .thenApply(ignored -> orderFutures.stream()
        .map(CompletableFuture::join)
        .collect(Collectors.toList())
    );
```

`allOf` trả về `CompletableFuture<Void>`, nên ví dụ dùng `thenApply` để thu thập kết quả từ từng future sau khi tất cả đã hoàn tất. `join()` ở đây không phải chờ lần lượt các tác vụ đang chạy; bước này chỉ được gọi sau khi `allOf` hoàn tất. Nếu một future đầu vào hoàn tất lỗi, future tổng hợp cũng hoàn tất lỗi và hàm thu thập thành công sẽ không được chạy.

`anyOf` hoàn tất khi một trong các future đầu vào hoàn tất đầu tiên, dù kết quả đầu tiên là thành công hay lỗi. Nó trả về `CompletableFuture<Object>` vì các future đầu vào có thể mang kiểu khác nhau. Nếu cần kết quả có kiểu cụ thể, cần kiểm tra hoặc chuyển kiểu phù hợp.

`allOf` và `anyOf` vẫn chỉ điều phối các kết quả hữu hạn. Chúng không biến các future đầu vào thành một luồng phát phần tử liên tục và cũng không tạo cơ chế yêu cầu dữ liệu theo nhu cầu.

## 4. Xử lý lỗi trong chuỗi CompletableFuture

Lỗi phát sinh trong hàm của một stage thường làm stage đó hoàn tất exceptional. Các stage xử lý theo đường thành công phía sau sẽ bị bỏ qua cho tới khi có toán tử xử lý lỗi. Ba phương thức thường dùng có mục đích khác nhau:

| Phương thức | Khi nào dùng | Kết quả |
| --- | --- | --- |
| `exceptionally` | Chuyển lỗi thành một giá trị thay thế | Có thể khôi phục thành công bằng giá trị dự phòng |
| `handle` | Xử lý cả giá trị thành công và lỗi | Luôn tạo stage mới từ hàm xử lý |
| `whenComplete` | Ghi log, đo thời gian hoặc quan sát kết quả | Giữ nguyên kết quả/lỗi của stage trước, trừ khi callback tự ném lỗi |

```java
CompletableFuture<UserView> viewFuture = loadUserAsync(userId)
    .thenApply(userMapper::toView)
    .exceptionally(error -> {
        log.warn("Không tải được hồ sơ người dùng {}", userId, error);
        return UserView.unavailable(userId);
    });
```

Ví dụ trên chọn một giá trị dự phòng nên chuỗi có thể tiếp tục như thành công. Nếu lỗi cần được truyền tới API hoặc tầng gọi, không nên âm thầm thay nó bằng một đối tượng mặc định. Có thể dùng `handle` khi cần phân biệt hai trường hợp trong cùng một hàm:

```java
CompletableFuture<Result> resultFuture = loadDataAsync()
    .handle((data, error) -> {
        if (error != null) {
            return Result.failure(unwrap(error));
        }
        return Result.success(data);
    });
```

`get()` thường bọc lỗi tác vụ trong `ExecutionException`; `join()` thường ném `CompletionException`. Khi ghi log hoặc chuyển lỗi nghiệp vụ, nên xem nguyên nhân gốc thay vì chỉ ghi wrapper. Các lỗi có thể xuất hiện trong callback tiếp theo, vì vậy cần đặt xử lý lỗi ở đúng đoạn của chuỗi.

## 5. Hoàn tất thủ công, timeout và hủy

Một `CompletableFuture` cũng có thể được hoàn tất bởi một thành phần khác. Cách này hữu ích khi tích hợp API callback cũ hoặc khi một adapter nhận tín hiệu hoàn tất từ thư viện bên ngoài:

```java
CompletableFuture<Reply> replyFuture = new CompletableFuture<>();

legacyClient.send(request, new Callback() {
    @Override
    public void onSuccess(Reply reply) {
        replyFuture.complete(reply);
    }

    @Override
    public void onFailure(Throwable error) {
        replyFuture.completeExceptionally(error);
    }
});
```

`complete(value)` và `completeExceptionally(error)` chỉ thắng nếu future chưa được hoàn tất trước đó; cả hai trả về `true` nếu lời gọi hiện tại hoàn tất future và `false` nếu future đã có kết quả. Không nên dựa vào chuỗi thao tác `isDone()` rồi mới `complete(...)` để đồng bộ nhiều luồng, vì một luồng khác có thể hoàn tất future giữa hai lời gọi.

Từ Java 9, `orTimeout` có thể làm future hoàn tất lỗi bằng `TimeoutException` nếu hết thời gian; `completeOnTimeout` có thể hoàn tất bằng giá trị dự phòng. Đây là chính sách hoàn tất future, không bảo đảm thao tác I/O bên dưới đã dừng. Cần cấu hình timeout của HTTP client, database driver hoặc thư viện tương ứng để giới hạn thời gian thực thi thực tế.

`CompletableFuture.cancel(...)` làm future hoàn tất với trạng thái hủy, được biểu diễn như một dạng hoàn tất exceptional. Tham số `mayInterruptIfRunning` không có tác dụng trong `CompletableFuture`, vì lớp này không trực tiếp điều khiển phép tính đã tạo ra kết quả. Việc hủy future do đó không bảo đảm ngắt tác vụ nền đã được khởi chạy. Nếu cần dừng công việc thực sự, tác vụ và thư viện bên dưới phải có cơ chế hủy hoặc interrupt phù hợp.

## 6. Một kết quả không giống một luồng nhiều phần tử

Có thể hình dung khác biệt qua thời điểm và số lượng tín hiệu:

```mermaid
flowchart TD
    A[Khởi chạy tác vụ] --> B[Future hoặc CompletableFuture]
    B --> C{Hoàn tất}
    C -->|Thành công| D[Một giá trị]
    C -->|Thất bại| E[Một lỗi]
    C -->|Hủy| F[Cancellation]

    G[Đăng ký nhận luồng] --> H[Publisher: Flux hoặc Flow.Publisher]
    H --> I[Subscription và request(n)]
    I --> J[onNext: phần tử 1..N]
    J --> K{Tiếp tục?}
    K -->|Có nhu cầu mới| I
    K -->|Kết thúc| L[onComplete hoặc onError]
    K -->|Hủy| M[cancel]
```

`Future<T>` và `CompletableFuture<T>` có một lần hoàn tất cuối cùng. Chúng không có `onNext` lặp lại, không có `Subscription.request(n)` và không có giao thức backpressure. Một `CompletableFuture<List<T>>` có thể chứa một danh sách nhiều phần tử, nhưng danh sách đó vẫn được giao như **một kết quả duy nhất** khi toàn bộ tác vụ hoàn tất. Bên nhận không thể yêu cầu từng phần tử tiếp theo trong lúc danh sách đang được tạo.

Ngược lại, `Publisher<T>` trong Reactive Streams có thể phát nhiều tín hiệu `onNext` theo thời gian, rồi kết thúc bằng `onComplete` hoặc `onError`. Subscriber điều khiển nhu cầu qua `request(n)` và có thể hủy bằng `cancel()`. Cơ chế này cho phép phối hợp tốc độ giữa nguồn phát và bên nhận. Trong Reactor, `Mono<T>` mô tả tối đa một phần tử và `Flux<T>` mô tả từ không đến nhiều phần tử.

| Nhu cầu | Kiểu phù hợp | Lý do |
| --- | --- | --- |
| Tải một hồ sơ người dùng và nhận kết quả sau đó | `Future<User>` hoặc `CompletableFuture<User>` | Một kết quả cuối cùng |
| Nối nhiều bước bất đồng bộ để tạo một báo cáo | `CompletableFuture<Report>` | Các bước có thể phụ thuộc hoặc kết hợp trước khi tạo một kết quả |
| Chờ một trong nhiều tác vụ đơn lẻ hoàn tất | `CompletableFuture.anyOf(...)` | Chọn kết quả hoàn tất đầu tiên |
| Nhận nhiều bản ghi được phát dần theo thời gian | `Flux<Record>` hoặc `Publisher<Record>` | Nhiều phần tử và có thể điều tiết nhu cầu |
| Xử lý sự kiện liên tục từ một nguồn | `Flux<Event>` hoặc `Flow.Publisher<Event>` | Luồng sự kiện có vòng đời đăng ký, phát tín hiệu và hủy |

## 7. Kết hợp CompletableFuture với Reactor

Trong ứng dụng đang dùng Reactor, có thể chuyển một future đơn lẻ thành `Mono` bằng `Mono.fromFuture`. Điều này hữu ích khi cần ghép lời gọi API cũ trả về `CompletableFuture` vào một pipeline reactive:

```java
Mono<UserView> userView = Mono
    .fromFuture(userClient.findAsync(userId))
    .map(userMapper::toView)
    .onErrorResume(error -> {
        log.warn("Không tải được người dùng {}", userId, error);
        return Mono.just(UserView.unavailable(userId));
    });
```

`Mono.fromFuture` chuyển một kết quả hoàn tất thành publisher có tối đa một phần tử. Pipeline có thể tiếp tục bằng các toán tử Reactor và truyền lỗi theo tín hiệu reactive. Khi tích hợp, cần lưu ý future có thể đã bắt đầu chạy trước lúc `Mono` được subscribe, tùy cách tạo future. Nếu cần trì hoãn việc tạo future đến lúc subscribe, hãy dùng overload nhận supplier khi phiên bản Reactor đang dùng hỗ trợ.

Nếu nguồn thực sự tạo ra nhiều sự kiện, hãy dùng một publisher nhiều phần tử, ví dụ `Flux` hoặc `Flow.Publisher`, thay vì tạo một `CompletableFuture` cho toàn bộ vòng đời của nguồn. Việc chuyển một `List<T>` hoàn chỉnh thành `Flux.fromIterable(list)` chỉ phát lại danh sách đã có trong bộ nhớ; nó không biến thao tác lấy danh sách ban đầu thành một nguồn streaming.

## 8. Chọn mô hình theo hợp đồng của nguồn dữ liệu

Trước khi chọn API, hãy xác định nguồn dữ liệu cam kết điều gì. Nếu nguồn trả về đúng một kết quả sau khi tác vụ kết thúc, `Future` hoặc `CompletableFuture` là mô hình tự nhiên. Nếu cần nối các bước bất đồng bộ, phục hồi lỗi hoặc kết hợp nhiều kết quả đơn lẻ, `CompletableFuture` và `CompletionStage` cung cấp các phép nối rõ ràng. Nếu nguồn phát nhiều phần tử theo thời gian và bên nhận cần điều tiết tốc độ, hãy dùng `Publisher`, `Flux` hoặc `Flow.Publisher`.

Đừng nhầm số lượng phần tử trong một đối tượng kết quả với số lượng tín hiệu được phát. `CompletableFuture<List<Event>>` có một lần hoàn tất mang theo một danh sách; `Flux<Event>` có thể phát từng sự kiện, cho phép downstream xử lý dần và gửi nhu cầu mới. Đây là khác biệt cốt lõi giữa phối hợp tác vụ có kết quả đơn lẻ và xử lý luồng sự kiện bất đồng bộ trong Reactive Programming.

# Quản lý thread, executor và CompletableFuture trong function

Java function trong môi trường serverless thường xử lý một invocation trong thời gian giới hạn rồi trả kết quả cho nền tảng. Trong lúc xử lý, function có thể gọi nhiều dịch vụ, đọc database, chuyển đổi dữ liệu hoặc thực hiện các tác vụ độc lập. Dùng nhiều thread và CompletableFuture có thể giảm thời gian chờ bằng cách chạy các công việc I/O đồng thời, nhưng cũng làm tăng độ phức tạp về trạng thái, timeout, lỗi và giới hạn tài nguyên.

Một function không phải ứng dụng server chạy liên tục. Execution environment có thể được tái sử dụng, tạm dừng hoặc thu hồi; invocation mới có thể chạy ở một environment khác. Thread pool được tạo trong một environment có thể còn tồn tại qua nhiều invocation trên chính environment đó, nhưng không được chia sẻ toàn cục giữa mọi instance và không phải nơi lưu trạng thái bền vững.

Thiết kế concurrency cần bảo đảm mọi công việc thuộc request đã hoàn tất hoặc đã được chuyển giao bền vững trước khi handler kết thúc. Không được dựa vào background thread để tiếp tục nghiệp vụ sau khi trả response hoặc xác nhận message. Cần giới hạn số thread, số tác vụ đang chạy và số kết nối tới dependency để việc mở rộng function không làm quá tải hệ thống phía sau.

## 1. Vì sao cần quản lý concurrency trong serverless?

Một function có thể thực hiện nhiều bước:

- Xác minh request và quyền truy cập.
- Đọc thông tin người dùng từ database.
- Gọi API thanh toán hoặc dịch vụ bên ngoài.
- Đọc nhiều tài nguyên độc lập.
- Biến đổi dữ liệu và ghi kết quả.
- Phát event hoặc cập nhật trạng thái job.

Nếu các lời gọi độc lập được thực hiện tuần tự, tổng thời gian chờ có thể gần bằng tổng latency của từng dependency. Nếu chạy song song có giới hạn, thời gian có thể gần với lời gọi chậm nhất cộng chi phí điều phối.

Ví dụ, một API cần lấy profile mất 120 ms, lấy lịch sử đơn hàng mất 250 ms và lấy điểm thưởng mất 180 ms. Nếu gọi tuần tự, thời gian chờ mạng có thể xấp xỉ 550 ms. Nếu ba lời gọi độc lập chạy đồng thời, thời gian chờ có thể gần 250 ms, chưa tính overhead và tải của hệ thống.

Song song không làm công việc biến mất. Nó tiêu thụ thêm thread, memory, connection và capacity ở các dịch vụ đích. Nếu mỗi function mở 10 lời gọi đồng thời và nền tảng mở rộng lên 100 execution environment, hệ thống phía sau có thể nhận tới khoảng 1.000 lời gọi đồng thời. Vì vậy, tối ưu latency của một invocation phải đi cùng giới hạn tải ở quy mô toàn hệ thống.

## 2. Phân biệt invocation concurrency và thread concurrency

Có hai lớp concurrency:

- **Invocation concurrency:** số lần gọi function đang được nền tảng xử lý đồng thời trên các execution environment.
- **Thread concurrency:** số luồng công việc đang chạy bên trong một execution environment.

Hai lớp này nhân với nhau khi tính tải. Nếu nền tảng xử lý 50 invocation đồng thời và mỗi invocation tạo 8 tác vụ I/O, dependency có thể nhận đến 400 tác vụ đang chờ hoặc đang chạy, tùy cách điều phối và connection pool.

Không giả định mọi nền tảng hoặc runtime có cùng cách chạy invocation. Một số mô hình tạo environment riêng cho mỗi invocation đồng thời; một số runtime hoặc framework có thể hỗ trợ nhiều request trên một process; event source mapping có thể gọi function theo batch. Hãy đọc contract concurrency của runtime đang dùng và viết code thread-safe khi object dùng chung.

Cần phân biệt:

| Khái niệm | Phạm vi | Ví dụ |
|---|---|---|
| Invocation | Một lần gọi function | Xử lý một HTTP request |
| Execution environment | Runtime/process được nền tảng cấp | Một JVM cùng các dependency đã khởi tạo |
| Thread | Luồng thực thi trong process | Handler thread hoặc worker thread |
| Executor | Cơ chế lập lịch và quản lý tác vụ | ThreadPoolExecutor |
| Future | Đại diện cho kết quả sẽ có trong tương lai | CompletableFuture của lời gọi API |
| Connection pool | Giới hạn và tái sử dụng kết nối | JDBC pool hoặc HTTP connection pool |

Thread pool tĩnh trong một class có thể được tái sử dụng khi environment còn tồn tại. Nó không được chia sẻ giữa các environment khác nhau. Khi scale out, mỗi environment có thể tạo pool riêng; tổng số thread và connection vì vậy tăng theo số environment.

## 3. Vòng đời thread trong execution environment

Thread được tạo bởi ứng dụng sống trong process của runtime. Khi invocation hoàn tất, handler thread có thể trở về trạng thái chờ; worker thread trong executor có thể tiếp tục tồn tại. Nếu environment được tái sử dụng, các thread và object dùng chung có thể vẫn còn.

Một số nền tảng có thể freeze environment khi không có invocation và resume sau đó. Khi freeze, worker thread hoặc callback chưa hoàn tất có thể không tiến triển như một service luôn hoạt động. Nền tảng cũng có thể thu hồi environment mà không cho ứng dụng đủ thời gian chạy cleanup.

Do đó:

1. Không trả response khi còn tác vụ cần thiết đang chạy.
2. Không dựa vào background thread để hoàn tất side effect sau khi handler trả về.
3. Không dùng thread để giữ lịch hẹn hoặc công việc cần chạy đúng thời điểm.
4. Không dựa vào shutdown hook để commit dữ liệu nghiệp vụ.
5. Không giả định thread sẽ tiếp tục chạy ngay khi environment được resume.
6. Chuyển công việc dài hoặc cần chạy độc lập sang queue, workflow hoặc scheduler bền vững.

Một luồng xử lý an toàn:

~~~mermaid
flowchart TD
    A["Invocation bắt đầu"] --> B["Tạo các tác vụ có giới hạn"]
    B --> C["Chờ các tác vụ cần thiết"]
    C --> D{"Tất cả kết quả hợp lệ?"}
    D -->|"Có"| E["Ghi kết quả bền vững"]
    E --> F["Trả response hoặc ack"]
    D -->|"Không"| G["Hủy best-effort / xử lý lỗi"]
    G --> H["Đảm bảo không còn side effect nền ngoài kiểm soát"]
    H --> I["Trả lỗi hoặc để trigger retry"]
~~~

Nếu công việc phải tiếp tục sau khi HTTP response được trả về, hãy ghi job state và gửi message trước khi trả 202 Accepted. Worker độc lập xử lý job và cập nhật trạng thái. Không khởi chạy một thread rồi hy vọng runtime giữ process sống.

## 4. Chọn tác vụ phù hợp để chạy song song

Song song hữu ích khi các tác vụ độc lập và thời gian chờ chiếm phần lớn tổng latency. Ví dụ: gọi hai API đọc dữ liệu khác nhau, đọc các resource độc lập hoặc tải nhiều object.

Không nên song song hóa một chuỗi có phụ thuộc dữ liệu. Nếu bước B cần kết quả bước A, phải dùng composition hoặc thực hiện tuần tự. Việc tạo nhiều thread cho tác vụ CPU-bound nhỏ cũng có thể làm chậm do context switching và cạnh tranh CPU.

| Loại công việc | Chiến lược thường phù hợp |
|---|---|
| I/O-bound: gọi HTTP, database, object storage | Thread pool nhỏ có giới hạn hoặc async client không chặn |
| CPU-bound: mã hóa, nén, tính toán | Giới hạn worker theo CPU được cấp và thời gian invocation |
| Tác vụ phụ thuộc kết quả trước | Nối chuỗi bằng thenCompose hoặc thực hiện tuần tự |
| Tác vụ độc lập cần đủ kết quả | Chạy song song có giới hạn rồi chờ allOf |
| Tác vụ dài hơn giới hạn invocation | Queue hoặc workflow bền vững |
| Tác vụ tùy chọn, có thể bỏ qua | Timeout riêng và fallback được xác định rõ |

Trước khi dùng concurrency, xác định tác vụ nào thực sự độc lập, kết quả nào bắt buộc, kết quả nào tùy chọn, và khi một nhánh lỗi thì toàn bộ request phải thất bại hay có thể trả dữ liệu một phần.

## 5. Executor và vì sao không nên tạo thread tùy tiện

Executor quản lý cách tác vụ được đưa vào hàng đợi và thực thi trên thread. Tạo một thread mới cho mỗi lời gọi có thể làm số thread tăng không giới hạn khi traffic tăng hoặc dependency chậm.

Ví dụ không nên dùng:

~~~java
new Thread(() -> paymentClient.call()).start();
~~~

Đoạn code này tạo thread nhưng không có giới hạn số lượng, không có nơi theo dõi kết quả, không có deadline rõ ràng và không bảo đảm công việc hoàn tất trước khi invocation kết thúc.

Tương tự, cached thread pool có thể tạo nhiều thread khi queue không giữ được tải. Trong serverless, scale out đã tạo thêm execution environment; một pool không giới hạn bên trong mỗi environment có thể khuếch đại tải ngoài dự kiến.

Ưu tiên executor có:

- Số worker tối đa rõ ràng.
- Queue có capacity hữu hạn.
- Tên thread để quan sát log và dump.
- Chính sách từ chối tác vụ khi quá tải.
- Timeout cho tác vụ và dependency.
- Cơ chế đo queue depth, active count và rejected task.
- Thread-safe dependencies hoặc instance riêng cho mỗi tác vụ.

### Ví dụ ThreadPoolExecutor có giới hạn

~~~java
private static final AtomicInteger THREAD_SEQUENCE =
        new AtomicInteger();

private static final ThreadFactory WORKER_FACTORY = task -> {
    Thread thread = new Thread(
            task,
            "function-io-" + THREAD_SEQUENCE.incrementAndGet()
    );
    thread.setDaemon(true);
    return thread;
};

private static final ThreadPoolExecutor IO_EXECUTOR =
        new ThreadPoolExecutor(
                4,
                4,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(32),
                WORKER_FACTORY,
                new ThreadPoolExecutor.AbortPolicy()
        );
~~~

Ví dụ tạo một pool tối đa 4 worker và hàng đợi 32 tác vụ trong mỗi execution environment. Khi hàng đợi đầy và không còn worker khả dụng, AbortPolicy ném RejectedExecutionException để ứng dụng có thể trả lỗi quá tải hoặc áp dụng fallback.

Các con số 4 và 32 chỉ là ví dụ. Cần điều chỉnh theo memory, CPU, thời gian invocation, latency dependency, số environment tối đa và giới hạn dịch vụ đích. Một pool riêng cho mỗi environment nhân lên khi scale out; đừng chỉ nhìn số thread của một JVM.

Không dùng queue không giới hạn. Nếu dependency chậm, queue sẽ tích lũy tác vụ, giữ request context và payload trong memory, tăng latency và có thể gây out-of-memory. Backpressure cần được thực hiện trước khi nhận quá nhiều việc.

### Chọn rejection policy

- **AbortPolicy:** từ chối tác vụ mới bằng exception; phù hợp khi caller cần biết hệ thống đang quá tải.
- **CallerRunsPolicy:** thread submit chạy tác vụ nếu pool đầy; tạo backpressure nhưng có thể khiến handler thread bị block và vượt deadline.
- **DiscardPolicy:** bỏ tác vụ mà không báo lỗi; nguy hiểm nếu tác vụ quan trọng.
- **DiscardOldestPolicy:** bỏ tác vụ cũ nhất trong queue; chỉ phù hợp với một số workload có thể thay thế dữ liệu cũ.

Với side effect nghiệp vụ, không âm thầm bỏ tác vụ. Hãy chọn hành vi rõ ràng, ghi nhận rejection và trả kết quả phù hợp. Nếu không thể xử lý trong invocation, ghi công việc vào queue bền vững.

## 6. Tái sử dụng executor giữa các invocation

Có thể khởi tạo một executor dùng chung trong execution environment để tránh tạo và hủy pool ở mỗi invocation. Cách này giảm overhead và giúp tái sử dụng worker thread.

Tuy nhiên, executor dùng chung có vòng đời dài hơn request. Mọi task phải tự chứa dữ liệu invocation cần thiết và không được đọc một mutable field chứa request hiện tại. Không lưu user ID, tenant, authorization context hoặc payload của invocation vào biến static rồi để worker đọc sau.

Một số quy tắc:

- Tạo executor sau khi kiểm tra runtime và nhu cầu concurrency.
- Giữ pool có giới hạn; không tăng kích thước vô hạn khi thấy queue đầy.
- Không gọi shutdown trên executor dùng chung ở cuối mỗi invocation.
- Không dùng executor như nơi lưu công việc sau khi handler trả về.
- Không để task cũ mang context hoặc dữ liệu sang invocation kế tiếp.
- Theo dõi pool bị kẹt, queue đầy và task chạy quá lâu.
- Chỉ tái sử dụng client hoặc dependency có hợp đồng thread-safe.

Thread daemon giúp worker thread không ngăn process kết thúc trong một số tình huống, nhưng không bảo đảm task hoàn tất. Daemon thread vẫn có thể bị freeze hoặc bị dừng khi environment bị thu hồi. Hãy chờ tác vụ cần thiết trước khi trả kết quả.

Nếu dùng executor theo từng invocation, cần shutdown và chờ hoàn tất trong phạm vi thời gian còn lại. Cách này tăng chi phí tạo thread nhưng có ranh giới ownership rõ. Dù chọn pool dùng chung hay theo invocation, phải có giới hạn concurrency và không để task sống vượt quá phạm vi nghiệp vụ.

## 7. CompletableFuture và mô hình bất đồng bộ

CompletableFuture đại diện cho kết quả có thể hoàn tất trong tương lai. Nó hỗ trợ nối chuỗi bước xử lý, kết hợp nhiều kết quả và xử lý exception mà không cần tự quản lý callback bằng tay.

Các method thường gặp:

| Method | Ý nghĩa |
|---|---|
| supplyAsync | Chạy tác vụ trả về giá trị bất đồng bộ |
| runAsync | Chạy tác vụ không trả về giá trị |
| thenApply | Biến đổi kết quả đồng bộ khi future hoàn tất |
| thenApplyAsync | Biến đổi kết quả trên executor |
| thenCompose | Nối một bước bất đồng bộ khác và làm phẳng future lồng nhau |
| thenCombine | Kết hợp kết quả của hai future độc lập |
| allOf | Chờ tất cả future hoàn tất |
| anyOf | Hoàn tất khi một future bất kỳ hoàn tất |
| exceptionally | Tạo kết quả thay thế khi có lỗi |
| handle | Xử lý cả kết quả thành công và lỗi |
| whenComplete | Quan sát kết quả/lỗi mà không chủ đích thay thế kết quả |
| orTimeout | Hoàn tất future bằng TimeoutException sau thời hạn |
| completeOnTimeout | Hoàn tất future bằng giá trị mặc định sau thời hạn |

Một điểm quan trọng: các method Async không truyền executor tường minh thường dùng ForkJoinPool.commonPool(). Điều đó có thể không phù hợp với blocking I/O hoặc ngân sách thread của function. Với tác vụ blocking, truyền executor có giới hạn hoặc dùng async client không chặn.

### Ví dụ gọi song song hai dependency

~~~java
CompletableFuture<Profile> profileFuture =
        CompletableFuture.supplyAsync(
                () -> profileClient.fetch(userId),
                IO_EXECUTOR
        );

CompletableFuture<List<Order>> ordersFuture =
        CompletableFuture.supplyAsync(
                () -> orderClient.fetchRecent(userId),
                IO_EXECUTOR
        );

CompletableFuture<Void> combined =
        CompletableFuture.allOf(profileFuture, ordersFuture);

combined.join();

Profile profile = profileFuture.join();
List<Order> orders = ordersFuture.join();

return new Dashboard(profile, orders);
~~~

Hai lời gọi bắt đầu độc lập trên IO_EXECUTOR. allOf hoàn tất khi cả hai future hoàn tất. Nếu một future lỗi, combined cũng hoàn tất exceptional; join ném CompletionException. Cần xử lý lỗi ở ranh giới handler và ánh xạ sang response hoặc trigger retry phù hợp.

Không gọi join ngay sau khi tạo từng future rồi mới tạo future tiếp theo; làm vậy sẽ vô tình tuần tự hóa các tác vụ. Tạo tất cả future trước, sau đó mới chờ kết quả chung.

## 8. Nối chuỗi và kết hợp kết quả đúng cách

Dùng thenApply khi bước tiếp theo chỉ biến đổi kết quả đã có:

~~~java
CompletableFuture<String> displayName =
        profileFuture.thenApply(Profile::displayName);
~~~

Dùng thenCompose khi bước tiếp theo tự trả về một CompletableFuture:

~~~java
CompletableFuture<List<Order>> orders =
        profileFuture.thenCompose(profile ->
                orderClient.fetchRecentAsync(profile.userId())
        );
~~~

Nếu dùng thenApply với một function trả CompletableFuture, kết quả sẽ thành CompletableFuture<CompletableFuture<T>>. thenCompose làm phẳng cấu trúc đó.

Dùng thenCombine khi hai future độc lập và cần kết hợp kết quả:

~~~java
CompletableFuture<Dashboard> dashboard =
        profileFuture.thenCombine(
                ordersFuture,
                Dashboard::new
        );
~~~

Dùng allOf khi có nhiều future và cần chờ tất cả. allOf chỉ trả CompletableFuture<Void>, không gom kết quả thành list. Cần giữ tham chiếu tới từng future để đọc kết quả sau khi allOf hoàn tất.

Dùng anyOf khi chỉ cần kết quả đầu tiên hoàn tất, chẳng hạn truy vấn hai replica hoặc endpoint dự phòng. Tuy nhiên, cần xác định cách hủy tác vụ còn lại và tránh để tác vụ thừa tiếp tục tiêu thụ tài nguyên. Hoàn tất future đầu tiên không tự động dừng các tác vụ khác.

## 9. Xử lý exception và kết quả một phần

Exception trong pipeline CompletableFuture thường được bọc trong CompletionException hoặc ExecutionException tùy cách chờ. Hãy unwrap cause ở ranh giới xử lý để phân loại lỗi thực tế.

~~~java
try {
    return future.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();

    if (cause instanceof DependencyUnavailableException) {
        throw new RetryableFunctionException(cause);
    }

    if (cause instanceof ValidationException) {
        throw new InvalidRequestException(cause);
    }

    throw new FunctionExecutionException(cause);
}
~~~

Không biến mọi exception thành giá trị mặc định nếu điều đó làm response có vẻ thành công trong khi dữ liệu bắt buộc bị thiếu. Với dữ liệu tùy chọn, có thể dùng exceptionally hoặc handle để tạo fallback, nhưng cần ghi nhận rằng fallback đã xảy ra.

Ví dụ một dashboard có profile bắt buộc nhưng recommendation tùy chọn:

~~~java
CompletableFuture<Profile> profileFuture =
        CompletableFuture.supplyAsync(
                () -> profileClient.fetch(userId),
                IO_EXECUTOR
        );

CompletableFuture<List<Recommendation>> recommendationsFuture =
        CompletableFuture.supplyAsync(
                () -> recommendationClient.fetch(userId),
                IO_EXECUTOR
        ).exceptionally(error -> List.of());

return profileFuture.thenCombine(
        recommendationsFuture,
        Dashboard::new
);
~~~

Trong ví dụ này, lỗi recommendation tạo danh sách rỗng; lỗi profile vẫn làm toàn bộ thao tác thất bại. Chỉ dùng fallback nếu nghiệp vụ cho phép và response thể hiện rõ dữ liệu có thể không đầy đủ khi cần.

Với message trigger, không nuốt exception nếu runtime dùng exception để quyết định retry. Nếu một phần batch đã commit, cần partial batch acknowledgment hoặc idempotency để lần retry không lặp side effect đã hoàn tất.

## 10. Timeout, deadline và cancellation

Serverless invocation có thời hạn tối đa. Thời gian chờ các future phải nằm trong ngân sách còn lại của invocation, có chừa khoảng cho ghi kết quả, tạo response và cleanup.

Một request có thể có deadline tổng 3 giây. Nếu đã mất 1 giây ở gateway và validation, chỉ còn khoảng 2 giây cho các dependency cùng xử lý. Không đặt timeout 3 giây riêng cho từng dependency rồi kỳ vọng toàn request vẫn kết thúc trong 3 giây.

Cần phân biệt:

- **Invocation timeout:** nền tảng giới hạn thời gian handler được chạy.
- **Request deadline:** thời điểm caller không còn chờ kết quả.
- **Dependency timeout:** thời gian tối đa chờ một API hoặc database.
- **Future timeout:** thời gian chờ future hoàn tất.
- **Cancellation:** yêu cầu một tác vụ dừng; không phải lúc nào cũng dừng được lời gọi I/O bên dưới.

Ví dụ:

~~~java
CompletableFuture<Profile> profileFuture =
        CompletableFuture.supplyAsync(
                () -> profileClient.fetchWithTimeout(userId, Duration.ofMillis(900)),
                IO_EXECUTOR
        );

CompletableFuture<List<Order>> ordersFuture =
        CompletableFuture.supplyAsync(
                () -> orderClient.fetchWithTimeout(userId, Duration.ofMillis(1200)),
                IO_EXECUTOR
        );

try {
    CompletableFuture.allOf(profileFuture, ordersFuture)
            .orTimeout(1500, TimeUnit.MILLISECONDS)
            .join();
} catch (CompletionException ex) {
    profileFuture.cancel(true);
    ordersFuture.cancel(true);
    throw ex;
}
~~~

Ví dụ này minh họa timeout tổng và cancellation best-effort. orTimeout làm future kết thúc exceptional sau thời hạn; nó không bảo đảm socket, JDBC query hoặc tác vụ blocking bên dưới tự dừng. cancel(true) trên CompletableFuture cũng không bảo đảm thread đang thực hiện lời gọi bị interrupt. Hãy cấu hình timeout ở HTTP client, JDBC driver và dependency SDK; dùng API hỗ trợ cancellation thực sự khi cần.

Không trả response rồi để future chạy tiếp. Nếu dependency không thể dừng nhanh, phải thiết kế giới hạn kết nối, deadline phía client và cơ chế idempotency để task không tiếp tục tạo side effect ngoài phạm vi request.

## 11. Context propagation: trace, logging và security

Thread mới không tự động mang đầy đủ context của thread gọi. Những dữ liệu thường được giữ trong ThreadLocal gồm:

- MDC của logging.
- Trace/span context.
- Security principal hoặc tenant context.
- Locale hoặc request-scoped metadata.
- Context của framework.

Khi chuyển sang executor, ThreadLocal có thể không có giá trị hoặc chứa giá trị còn sót từ tác vụ trước nếu không được dọn đúng cách. Không giả định MDC hoặc security context tự động truyền qua mọi executor.

Cách an toàn là truyền context cần thiết tường minh trong tham số hoặc dùng context propagation mechanism của framework/telemetry SDK. Nếu dùng wrapper để copy MDC, phải khôi phục hoặc clear context trong finally:

~~~java
Map<String, String> capturedContext = MDC.getCopyOfContextMap();

Runnable task = () -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (capturedContext == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(capturedContext);
        }

        performWork();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
};

IO_EXECUTOR.execute(task);
~~~

Đây là ví dụ cho MDC của SLF4J/Logback; cần điều chỉnh theo logging framework. Với security context, không copy một object mutable hoặc token có vòng đời dài một cách tùy tiện. Chỉ truyền danh tính đã xác minh và quyền tối thiểu cần cho tác vụ; kiểm tra quyền ở nơi thực hiện thao tác dữ liệu.

## 12. Thread safety, shared state và ThreadLocal

Executor dùng chung nghĩa là nhiều task có thể truy cập cùng một dependency. Hãy kiểm tra thư viện có thread-safe hay không. Nếu một mapper hoặc client không thread-safe, tạo instance riêng cho task hoặc đồng bộ hóa phần truy cập cần thiết.

Không dùng biến static mutable để chứa dữ liệu invocation:

~~~java
private static String currentTenantId;
private static RequestContext currentContext;
~~~

Nhiều task có thể ghi đè các giá trị này, và environment có thể được tái sử dụng qua request khác. Hãy dùng biến cục bộ bất biến và truyền context tường minh.

ThreadLocal có thể hữu ích cho thư viện cần context theo thread, nhưng thread pool tái sử dụng worker thread. Nếu không clear ThreadLocal trong finally, dữ liệu của task trước có thể xuất hiện trong task sau. Điều này đặc biệt nguy hiểm với tenant ID, user identity, token và dữ liệu cá nhân.

Các quy tắc:

- Ưu tiên immutable value và local variable.
- Không chia sẻ mutable collection nếu không có đồng bộ.
- Dùng concurrent collection khi thật sự cần chia sẻ.
- Clear ThreadLocal và MDC sau mỗi task.
- Không dùng thread identity để suy ra user hoặc tenant.
- Kiểm tra thread safety của SDK và connection pool.
- Không giữ request object trong future lâu hơn vòng đời invocation.

## 13. Giới hạn dependency bằng semaphore và connection pool

Giới hạn số thread trong executor chưa chắc đã giới hạn số request tới một dependency. Một worker có thể mở nhiều lời gọi song song; nhiều executor hoặc nhiều function có thể cùng gọi một hệ thống.

Semaphore có thể giới hạn số thao tác đồng thời trong một environment:

~~~java
private static final Semaphore PAYMENT_LIMIT =
        new Semaphore(3);

public PaymentResult charge(PaymentRequest request) {
    boolean acquired = false;

    try {
        acquired = PAYMENT_LIMIT.tryAcquire(
                200,
                TimeUnit.MILLISECONDS
        );

        if (!acquired) {
            throw new DependencyOverloadedException();
        }

        return paymentClient.charge(request);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new RetryableFunctionException(ex);
    } finally {
        if (acquired) {
            PAYMENT_LIMIT.release();
        }
    }
}
~~~

Semaphore này chỉ giới hạn trong một JVM/execution environment. Nếu có 40 environment và mỗi environment cho phép 3 lời gọi, tổng concurrency vẫn có thể đạt 120. Để giới hạn toàn hệ thống, cần quota phía dependency, API gateway, distributed rate limiter hoặc giới hạn concurrency của function.

Connection pool cũng phải được tính theo số environment tối đa. Nếu mỗi environment tạo 5 database connection và nền tảng có thể mở 100 environment, database có thể nhận tới 500 connection. Chọn pool size dựa trên tổng connection budget và khả năng của database, không dựa trên một invocation đơn lẻ.

Khi dependency quá tải, trả lỗi có thể retry với backoff, đưa công việc vào queue hoặc giảm concurrency. Không retry ngay trong nhiều thread vì có thể tạo retry storm.

## 14. CPU-bound, blocking I/O và virtual threads

Thread pool cần phù hợp với loại công việc.

### CPU-bound

Với tính toán CPU-bound, số worker thường nên gần với số CPU được cấp cho environment. Tạo quá nhiều thread không làm CPU nhanh hơn; nó có thể tăng context switching và tranh chấp tài nguyên. Memory setting hoặc CPU allocation của nền tảng có thể ảnh hưởng trực tiếp đến throughput.

### Blocking I/O

Với blocking I/O, một thread thường bị chiếm trong lúc chờ network hoặc database. Thread pool có thể tăng số lời gọi đồng thời, nhưng phải giới hạn theo dependency và deadline. Nếu client có async/non-blocking API, có thể tránh chiếm worker thread trong lúc chờ.

### Virtual threads

Java 21 cung cấp virtual threads để làm cho code blocking-style dễ mở rộng hơn trong nhiều workload I/O-bound. Virtual thread nhẹ hơn platform thread, nhưng không làm database, API đối tác, CPU hoặc giới hạn socket trở nên vô hạn.

Khi dùng virtual threads:

- Kiểm tra runtime và framework serverless hỗ trợ Java version đó.
- Vẫn giới hạn concurrency tới dependency bằng semaphore, connection pool hoặc quota.
- Cấu hình timeout ở client và database.
- Đo memory, throughput và latency trong môi trường thực tế.
- Tránh giữ lock hoặc thực hiện thao tác có pinning lâu trong các tình huống runtime bị ảnh hưởng.
- Không tạo hàng triệu tác vụ mà không có backpressure.

Virtual threads giúp quản lý nhiều tác vụ blocking, nhưng không thay thế queue bền vững cho công việc phải tiếp tục sau invocation.

## 15. Retry và CompletableFuture

Retry bất đồng bộ cần có giới hạn và phân loại lỗi. Không retry mọi exception; validation error, permission denied hoặc trạng thái nghiệp vụ không hợp lệ thường không tự phục hồi. Timeout hoặc throttling có thể retry nhưng phải dùng backoff, jitter và deadline tổng.

Nếu dùng CompletableFuture để retry, tránh tạo chuỗi future mới không giới hạn. Mỗi lần thử cần nằm trong ngân sách thời gian, và retry một side effect phải có idempotency key ổn định.

Một thiết kế đơn giản:

~~~java
CompletableFuture<Inventory> loadInventory(String productId) {
    return CompletableFuture.supplyAsync(
            () -> inventoryClient.fetch(productId),
            IO_EXECUTOR
    ).exceptionallyCompose(error -> {
        Throwable cause = unwrap(error);

        if (cause instanceof RetryableDependencyException) {
            return delayedRetry(productId, Duration.ofMillis(200));
        }

        return CompletableFuture.failedFuture(cause);
    });
}
~~~

Đây là ví dụ khái niệm dùng exceptionallyCompose (Java 12 trở lên). Hàm delayedRetry phải giới hạn số lần thử, deadline và dùng scheduler có quản lý; không dùng Thread.sleep trong worker vì sẽ chiếm thread. Nếu runtime hoặc Java version không hỗ trợ API này, có thể triển khai bằng handle/thenCompose hoặc một retry library có policy rõ ràng.

Đối với message trigger, để broker quản lý retry khi phù hợp thay vì retry dài bên trong một invocation. Nếu function tự retry nhiều lần, nó chiếm thời gian invocation và có thể làm visibility timeout hết hạn. Khi trả lỗi để broker retry, đảm bảo side effect idempotent.

## 16. Batch và xử lý nhiều message song song

Batch trigger có thể đưa nhiều message vào một invocation. Xử lý song song từng message giúp tăng throughput nhưng cần giới hạn số tác vụ và hiểu partial batch acknowledgment.

Không submit toàn bộ batch vào một executor không giới hạn. Nếu batch có 500 message và pool chỉ có 4 worker, queue phải có capacity và thời gian xử lý batch phải nằm trong function timeout. Nếu một message lỗi, xác định các message thành công đã commit hay chưa trước khi trả batch response.

Một mô hình xử lý:

1. Validate envelope và event ID cho từng message.
2. Submit tối đa số tác vụ được phép.
3. Mỗi task xử lý idempotently và commit kết quả bền vững.
4. Thu thập kết quả thành công và lỗi theo message ID.
5. Trả partial failure theo contract của event source mapping hoặc throw để retry batch.
6. Đảm bảo không còn task nền tiếp tục side effect sau khi invocation trả kết quả.

Nếu broker không hỗ trợ partial acknowledgment, các message thành công có thể được giao lại khi một message trong batch thất bại. Idempotency theo từng message là bắt buộc để tránh xử lý lặp.

## 17. Đo lường và chẩn đoán concurrency

Không chỉ đo tổng thời gian handler. Cần biết thời gian bị tiêu thụ ở đâu và executor có đang quá tải không.

Các metric hữu ích:

- Invocation count, concurrency và timeout.
- Số thread đang hoạt động và tổng thread trong mỗi environment.
- Executor queue depth, active count và rejected task count.
- Thời gian chờ trong queue và thời gian chạy mỗi task.
- CompletableFuture success, failure, timeout và cancellation.
- Dependency latency, error rate, connection pool usage.
- Semaphore acquire wait và số lần từ chối.
- Batch size, partial failure và message age.
- p50, p95, p99 latency của toàn request.
- Memory, CPU và cold start.

Log cần có correlation ID hoặc trace context xuyên qua các task. Ghi task name, dependency, thời gian chờ, thời gian chạy và kết quả. Không log token, secret, payload nhạy cảm hoặc toàn bộ context.

Nếu function có latency tăng nhưng CPU thấp, có thể pool đang chờ dependency hoặc connection pool cạn. Nếu CPU cao và queue tăng, có thể tác vụ CPU-bound quá nhiều hoặc worker count không phù hợp. Nếu rejected task tăng, cần giảm tải, tăng capacity có kiểm soát hoặc chuyển công việc sang queue.

## 18. Checklist thiết kế thread và CompletableFuture

Trước khi triển khai, hãy kiểm tra:

1. Tác vụ nào thực sự độc lập và có lợi khi chạy song song?
2. Runtime có hỗ trợ mô hình thread và invocation concurrency như giả định không?
3. Có executor với worker count và queue capacity hữu hạn không?
4. Tổng số thread được tính theo số execution environment tối đa chưa?
5. Rejection policy có báo lỗi thay vì âm thầm bỏ tác vụ quan trọng không?
6. CompletableFuture có dùng executor tường minh cho blocking I/O không?
7. allOf, thenCompose và thenCombine có được dùng đúng quan hệ phụ thuộc không?
8. Exception được unwrap và phân loại đúng chưa?
9. Timeout tổng có nằm trong deadline invocation không?
10. HTTP client, JDBC và SDK có timeout riêng không?
11. Cancellation có thực sự dừng I/O hay chỉ hoàn tất future?
12. Handler có chờ mọi công việc cần thiết trước khi trả response hoặc ack không?
13. Context trace, MDC và security có được truyền và clear đúng cách không?
14. Shared client và mutable state có thread-safe không?
15. Connection pool, semaphore và concurrency cap có bảo vệ dependency không?
16. Retry có giới hạn, backoff, jitter và idempotency không?
17. Có xử lý partial batch failure và duplicate delivery không?
18. Có metric cho queue depth, rejected tasks, task latency và dependency saturation không?

## Kết luận

Thread và CompletableFuture có thể giảm latency của Java function khi nhiều tác vụ I/O độc lập, nhưng concurrency phải được giới hạn theo tài nguyên của execution environment và khả năng của dependency. Executor có worker count và queue capacity hữu hạn giúp kiểm soát tải; CompletableFuture giúp nối chuỗi, kết hợp kết quả và xử lý lỗi; timeout cùng cancellation cần được thiết kế ở cả future lẫn client I/O.

Trong serverless, thread pool có thể được tái sử dụng khi environment còn sống nhưng không phải nơi lưu công việc bền vững. Hãy hoàn tất hoặc chuyển giao công việc trước khi handler trả kết quả, truyền context tường minh, giữ state an toàn luồng, giới hạn connection và theo dõi concurrency ở cả cấp invocation lẫn cấp thread. Với tác vụ cần tiếp tục sau invocation, dùng queue hoặc workflow thay vì background thread.


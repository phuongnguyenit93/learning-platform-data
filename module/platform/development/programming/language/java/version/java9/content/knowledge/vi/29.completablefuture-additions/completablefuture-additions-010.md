# Kết hợp kết quả, lỗi, thời hạn và hủy với CompletableFuture

## Mục tiêu

`CompletableFuture<T>` biểu diễn một kết quả có thể được hoàn thành trong tương lai. Khi xử lý nhiều công việc bất đồng bộ, chương trình thường cần kết hợp kết quả, nối các bước phụ thuộc, phục hồi lỗi, đặt thời hạn hoặc hủy một tác vụ.

API `CompletableFuture` hỗ trợ các việc này thông qua những nhóm phương thức như `thenCombine`, `thenCompose`, `allOf`, `anyOf`, `exceptionally`, `handle`, `whenComplete`, `orTimeout`, `completeOnTimeout` và `cancel`.

Các phương thức kết hợp kết quả và xử lý lỗi thuộc CompletionStage/CompletableFuture từ Java 8. Java 9 bổ sung các tiện ích quan trọng như `orTimeout`, `completeOnTimeout`, `delayedExecutor` và `failedFuture`. Đây đều là API hiện hành.

## 1. CompletableFuture và trạng thái hoàn thành

Một CompletableFuture có thể kết thúc theo ba cách chính:

- **Hoàn thành bình thường:** có một giá trị kết quả, kể cả giá trị null nếu kiểu và hợp đồng cho phép.
- **Hoàn thành bất thường:** có exception làm kết quả không thành công.
- **Bị hủy:** được hoàn thành bất thường bằng CancellationException.

Một CompletableFuture có thể được hoàn thành bằng mã gọi như `complete(value)` hoặc `completeExceptionally(error)`, hoặc được hoàn thành bởi một tác vụ bất đồng bộ được tạo qua `supplyAsync`/`runAsync`.

Các phương thức nối tiếp trả về một stage mới. Có thể tiếp tục xây dựng pipeline mà không cần chặn thread để lấy kết quả ở giữa. Chỉ dùng `join()` hoặc `get()` tại ranh giới mà chương trình thực sự cần kết quả.

## 2. Kết hợp hai kết quả độc lập bằng thenCombine

Khi hai tác vụ độc lập cùng tạo ra kết quả và cần kết hợp cả hai, dùng `thenCombine`:

~~~java
CompletableFuture<Integer> price =
        CompletableFuture.supplyAsync(() -> 100);

CompletableFuture<Integer> shipping =
        CompletableFuture.supplyAsync(() -> 20);

CompletableFuture<Integer> total =
        price.thenCombine(shipping, Integer::sum);
~~~

Hàm kết hợp chỉ chạy khi cả hai stage hoàn thành bình thường. Nếu một stage hoàn thành bất thường, stage kết hợp cũng hoàn thành bất thường và hàm kết hợp không tạo ra kết quả thành công.

Các biến thể liên quan:

| Phương thức | Kết quả sau khi cả hai stage hoàn tất bình thường |
|---|---|
| `thenCombine(other, fn)` | Kết hợp hai giá trị thành một giá trị mới |
| `thenAcceptBoth(other, action)` | Nhận cả hai giá trị để thực hiện hành động, không tạo giá trị mới |
| `runAfterBoth(other, action)` | Chạy hành động sau khi cả hai hoàn thành, không nhận giá trị |

Nếu muốn thực hiện callback bất đồng bộ, có các biến thể `thenCombineAsync`, `thenAcceptBothAsync` và `runAfterBothAsync`. Có thể truyền Executor riêng để kiểm soát thread thực thi.

## 3. Nối các bước phụ thuộc bằng thenCompose

Nếu bước tiếp theo cần giá trị của bước trước để khởi tạo một tác vụ bất đồng bộ khác, dùng `thenCompose`.

Ví dụ: lấy mã khách hàng trước, rồi dùng mã đó để tải hồ sơ:

~~~java
CompletableFuture<String> customerId =
        CompletableFuture.supplyAsync(() -> "C-100");

CompletableFuture<Customer> customer =
        customerId.thenCompose(id -> fetchCustomerAsync(id));
~~~

Giả sử `fetchCustomerAsync` trả về `CompletableFuture<Customer>`. thenCompose nối stage được trả về vào pipeline và làm phẳng kết quả.

Nếu dùng `thenApply` thay cho thenCompose:

~~~java
CompletableFuture<CompletableFuture<Customer>> nested =
        customerId.thenApply(id -> fetchCustomerAsync(id));
~~~

Kết quả là một CompletableFuture lồng nhau. Trong trường hợp hàm chuyển đổi trả về một CompletionStage, thenCompose thường là lựa chọn phù hợp để tiếp tục chuỗi bất đồng bộ.

Phân biệt nhanh:

- `thenApply`: biến đổi giá trị đồng bộ, tương tự map.
- `thenCompose`: gọi một bước bất đồng bộ khác và làm phẳng stage, tương tự flatMap.

## 4. Chờ nhiều tác vụ với allOf

`CompletableFuture.allOf(...)` tạo một CompletableFuture<Void> hoàn thành khi tất cả các future đầu vào hoàn tất.

~~~java
CompletableFuture<Integer> userCount = loadUserCount();
CompletableFuture<Integer> orderCount = loadOrderCount();
CompletableFuture<Integer> productCount = loadProductCount();

CompletableFuture<Void> all = CompletableFuture.allOf(
        userCount, orderCount, productCount
);

CompletableFuture<Integer> total = all.thenApply(ignored ->
        userCount.join() + orderCount.join() + productCount.join()
);
~~~

allOf không tự tạo List chứa các kết quả. Sau khi all hoàn tất bình thường, chương trình lấy kết quả từ từng future rồi tổng hợp theo kiểu dữ liệu mong muốn.

Nếu một future đầu vào hoàn thành bất thường, future allOf cũng hoàn thành bất thường. Hãy xác định chính sách lỗi cho từng tác vụ trước khi tổng hợp nếu muốn giữ lại các kết quả thành công khác.

### allOf và anyOf khác nhau thế nào?

| Phương thức | Điều kiện hoàn thành | Kiểu kết quả |
|---|---|---|
| `allOf(futures...)` | Tất cả future đầu vào đã hoàn tất | `CompletableFuture<Void>` |
| `anyOf(futures...)` | Một future đầu vào hoàn tất đầu tiên | `CompletableFuture<Object>` |

`anyOf` trả về kết quả của future hoàn tất đầu tiên, có thể là hoàn thành bình thường hoặc bất thường. Vì kiểu trả về là Object, phía gọi cần kiểm tra hoặc ép kiểu phù hợp.

Nếu mục tiêu là chấp nhận kết quả thành công đầu tiên trong khi bỏ qua các lỗi từ tác vụ khác, cần thiết kế riêng bằng cách chuyển từng future sang một dạng biểu diễn kết quả có trạng thái rõ ràng. Không nên mặc định anyOf luôn có nghĩa là “thành công đầu tiên”.

## 5. Xử lý lỗi: exceptionally, handle và whenComplete

Một stage hoàn thành bất thường sẽ truyền lỗi xuống các stage phụ thuộc. Có ba phương thức thường dùng để xử lý lỗi hoặc quan sát kết quả.

### exceptionally: cung cấp giá trị thay thế khi có lỗi

~~~java
CompletableFuture<Integer> safeValue = loadValue()
        .exceptionally(error -> 0);
~~~

exceptionally chỉ được gọi khi stage trước đó hoàn thành bất thường. Giá trị trả về của callback trở thành kết quả bình thường để pipeline tiếp tục.

Dùng khi có một giá trị dự phòng hợp lệ, chẳng hạn cache mặc định hoặc số 0 theo quy tắc nghiệp vụ. Không nên biến mọi lỗi thành giá trị mặc định nếu điều đó che giấu lỗi dữ liệu hoặc lỗi hệ thống.

### handle: xử lý cả kết quả lẫn lỗi

~~~java
CompletableFuture<String> description = loadValue()
        .handle((value, error) -> {
            if (error != null) {
                return "Không tải được dữ liệu";
            }
            return "Giá trị: " + value;
        });
~~~

handle luôn được gọi khi stage trước hoàn tất, dù thành công hay thất bại. Callback nhận cả giá trị và exception, rồi quyết định kết quả mới.

Dùng khi logic tạo kết quả tiếp theo cần phân biệt cả hai trường hợp. Nếu callback trả về giá trị bình thường, stage kết quả có thể phục hồi từ lỗi trước đó.

### whenComplete: quan sát mà giữ nguyên kết quả

~~~java
CompletableFuture<Integer> audited = loadValue()
        .whenComplete((value, error) -> {
            if (error != null) {
                logger.error("Tải dữ liệu thất bại", error);
            } else {
                logger.info("Đã tải dữ liệu: {}", value);
            }
        });
~~~

whenComplete phù hợp cho logging, metrics hoặc ghi nhận trạng thái. Nếu callback hoàn thành bình thường, kết quả của stage trước được giữ lại. Nếu callback ném exception khi stage trước thành công, stage mới sẽ hoàn thành bất thường.

Không dùng whenComplete để biến lỗi thành kết quả dự phòng; dùng exceptionally hoặc handle cho mục đích đó.

| Phương thức | Khi callback chạy | Có thể thay kết quả thành công? | Mục đích |
|---|---|---|---|
| `exceptionally` | Khi có lỗi | Có, để phục hồi bằng giá trị | Fallback |
| `handle` | Khi thành công hoặc lỗi | Có | Chuyển cả kết quả và lỗi thành kết quả mới |
| `whenComplete` | Khi thành công hoặc lỗi | Không chủ đích thay kết quả; callback dùng để quan sát | Logging/metrics |

## 6. Đọc và giải mã exception đúng cách

Có hai cách phổ biến để lấy kết quả đồng bộ từ CompletableFuture:

- `get()` khai báo các checked exception như InterruptedException và ExecutionException.
- `join()` không yêu cầu khai báo checked exception; nếu stage thất bại, nó ném CompletionException.

Ví dụ:

~~~java
try {
    String value = future.get();
} catch (InterruptedException error) {
    Thread.currentThread().interrupt();
    // Khôi phục trạng thái interrupt và xử lý việc dừng tác vụ.
} catch (ExecutionException error) {
    Throwable cause = error.getCause();
    // Xử lý nguyên nhân gốc.
}
~~~

Với `join()`, có thể lấy nguyên nhân từ `CompletionException.getCause()`. Không nên chỉ log thông báo chung rồi bỏ mất nguyên nhân gốc.

Nếu callback trong pipeline ném exception, các stage phụ thuộc thường hoàn thành bất thường. Có thể đặt một điểm xử lý lỗi ở cuối pipeline hoặc xử lý riêng tại từng nhánh tùy theo chính sách nghiệp vụ.

Tránh gọi get/join bên trong callback bất đồng bộ chỉ để chờ một future khác nếu có thể biểu diễn quan hệ bằng thenCombine hoặc thenCompose. Chặn thread không cần thiết có thể làm giảm thông lượng hoặc gây starvation trong executor có ít thread.

## 7. Đặt thời hạn với orTimeout và completeOnTimeout

Java 9 bổ sung hai phương thức đặt timeout trực tiếp trên CompletableFuture.

### orTimeout

~~~java
CompletableFuture<String> result = fetchAsync()
        .orTimeout(2, TimeUnit.SECONDS);
~~~

Nếu future chưa hoàn tất trong thời gian cho phép, nó được hoàn thành bất thường bằng TimeoutException. Khi dùng join(), lỗi thường được nhìn thấy qua CompletionException với cause là TimeoutException.

### completeOnTimeout

~~~java
CompletableFuture<String> result = fetchAsync()
        .completeOnTimeout("fallback", 2, TimeUnit.SECONDS);
~~~

Nếu future chưa hoàn tất đúng hạn, nó được hoàn thành bình thường bằng giá trị thay thế.

| Phương thức | Khi hết thời gian | Trạng thái kết quả |
|---|---|---|
| `orTimeout(timeout, unit)` | Hoàn thành bằng TimeoutException | Bất thường |
| `completeOnTimeout(value, timeout, unit)` | Hoàn thành bằng value dự phòng | Bình thường |

Cả hai phương thức trả về chính CompletableFuture được gọi và có thể hoàn tất future đó trước khi tác vụ gốc kết thúc. Timeout không tự động dừng HTTP request, truy vấn cơ sở dữ liệu hoặc công việc đang chạy bên dưới. Nếu cần ngừng tài nguyên thật sự, phải dùng cơ chế hủy tương ứng của API nền.

Có thể đặt timeout trên một stage kết hợp để giới hạn thời gian chờ tổng thể:

~~~java
CompletableFuture<Integer> total = first
        .thenCombine(second, Integer::sum)
        .orTimeout(3, TimeUnit.SECONDS);
~~~

## 8. Lên lịch trì hoãn với delayedExecutor

Java 9 bổ sung `CompletableFuture.delayedExecutor` để tạo Executor chỉ thực thi tác vụ sau một khoảng trì hoãn tối thiểu:

~~~java
Executor delayed = CompletableFuture.delayedExecutor(
        500, TimeUnit.MILLISECONDS
);

CompletableFuture<String> later = CompletableFuture.supplyAsync(
        () -> "Đã bắt đầu",
        delayed
);
~~~

Có thể truyền thêm một Executor nền nếu muốn kiểm soát nơi tác vụ thực sự chạy:

~~~java
Executor delayed = CompletableFuture.delayedExecutor(
        500,
        TimeUnit.MILLISECONDS,
        applicationExecutor
);
~~~

Đây là cơ chế trì hoãn việc gửi tác vụ đến Executor. Nó không phải lịch lặp lại và cũng không bảo đảm callback chạy chính xác tại thời điểm hết 500 ms; thời điểm thực tế còn phụ thuộc lịch thực thi và tải của executor.

Nếu cần lịch định kỳ, quản lý tác vụ theo lịch hoặc hủy lịch, dùng ScheduledExecutorService phù hợp hơn.

## 9. Hủy CompletableFuture và giới hạn của cancel

CompletableFuture triển khai Future nên có phương thức:

~~~java
boolean cancelled = future.cancel(true);
~~~

Nếu future chưa hoàn tất, cancel hoàn thành nó bất thường bằng CancellationException. Các phương thức `isCancelled()` và `isCompletedExceptionally()` giúp kiểm tra trạng thái.

Một điểm rất quan trọng: tham số `mayInterruptIfRunning` không có tác dụng điều khiển việc thực thi trong CompletableFuture. Gọi `cancel(true)` không bảo đảm thread đang chạy supplier bị interrupt. CompletableFuture có thể đại diện cho một tác vụ nhưng không nhất thiết sở hữu hoặc điều khiển tác vụ nền.

Vì vậy:

- Hủy future làm thay đổi trạng thái hoàn thành của future.
- Không mặc định rằng HTTP request, JDBC query hoặc tiến trình con đã dừng.
- Cần gọi API cancel/abort riêng của tác vụ nền nếu API đó hỗ trợ.
- Hủy một stage phụ thuộc không đồng nghĩa tự động hủy mọi stage nguồn hoặc mọi tác vụ liên quan.
- Nếu cần hủy cả một nhóm công việc, phải quản lý các handle hủy riêng và định nghĩa rõ chính sách hủy.

Timeout cũng không phải cơ chế hủy tác vụ nền. `orTimeout` chỉ làm future hoàn thành bất thường khi quá hạn; công việc thực tế có thể vẫn tiếp tục.

## 10. Executor và thread thực thi continuation

Các phương thức có hậu tố `Async` như `thenApplyAsync`, `thenComposeAsync` hoặc `thenCombineAsync` gửi callback đến một Executor. Nếu không truyền Executor, CompletableFuture thường dùng ForkJoinPool.commonPool() làm executor mặc định cho các tác vụ async.

Các phương thức không có hậu tố Async có thể chạy callback trên thread hoàn thành stage trước hoặc thread gọi phương thức nếu stage đã hoàn tất. Vì vậy không nên giả định callback luôn chạy trên thread riêng.

Quy tắc thực hành:

- Dùng callback không Async cho phép biến đổi ngắn, không chặn.
- Dùng hậu tố Async khi muốn tách callback khỏi thread hoàn thành stage trước.
- Truyền Executor riêng cho tác vụ blocking hoặc cần giới hạn tài nguyên.
- Không dùng common pool làm nơi chờ I/O blocking kéo dài nếu ứng dụng cần kiểm soát tải.
- Đóng ExecutorService do ứng dụng tạo khi không còn sử dụng.
- Không chặn trong callback bằng cách join các future khác nếu có thể nối chúng bằng API composition.

Ví dụ truyền executor riêng:

~~~java
ExecutorService ioExecutor = Executors.newFixedThreadPool(8);

CompletableFuture<String> response = CompletableFuture.supplyAsync(
        () -> blockingCall(),
        ioExecutor
);
~~~

Vòng đời của executor thuộc về thành phần tạo ra nó. Trong ứng dụng server, thường quản lý executor ở cấp ứng dụng và đóng khi ứng dụng dừng, thay vì tạo một pool mới cho từng request.

## 11. Ví dụ hoàn chỉnh có thể chạy

Tệp `CompletableFutureCombineDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;

public class CompletableFutureCombineDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> price =
                CompletableFuture.completedFuture(100);
        CompletableFuture<Integer> delivery =
                CompletableFuture.completedFuture(20);

        int total = price.thenCombine(delivery, Integer::sum).join();
        System.out.println("combined total: " + total);

        String greeting = CompletableFuture.completedFuture("An")
                .thenCompose(name ->
                        CompletableFuture.completedFuture("Hello " + name))
                .join();
        System.out.println("composed: " + greeting);

        CompletableFuture<Integer> one =
                CompletableFuture.completedFuture(10);
        CompletableFuture<Integer> two =
                CompletableFuture.completedFuture(20);
        CompletableFuture.allOf(one, two).join();
        System.out.println("allOf sum: " + (one.join() + two.join()));

        Object firstAvailable = CompletableFuture.anyOf(
                CompletableFuture.completedFuture("ready"),
                new CompletableFuture<String>()
        ).join();
        System.out.println("anyOf: " + firstAvailable);

        CompletableFuture<Integer> failed =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("invalid")
                );
        System.out.println("exceptionally: "
                + failed.exceptionally(error -> -1).join());
        System.out.println("handle: "
                + failed.handle((value, error) ->
                        error == null ? value : 0).join());

        int observed = CompletableFuture.completedFuture(5)
                .whenComplete((value, error) ->
                        System.out.println("whenComplete observed: " + value))
                .join();
        System.out.println("whenComplete result: " + observed);

        CompletableFuture<Integer> fallback =
                new CompletableFuture<Integer>()
                        .completeOnTimeout(-1, 20, TimeUnit.MILLISECONDS);
        System.out.println("completeOnTimeout: " + fallback.join());

        try {
            new CompletableFuture<String>()
                    .orTimeout(20, TimeUnit.MILLISECONDS)
                    .join();
        } catch (CompletionException error) {
            System.out.println("orTimeout: "
                    + error.getCause().getClass().getSimpleName());
        }

        CompletableFuture<String> cancelled = new CompletableFuture<>();
        cancelled.cancel(false);
        System.out.println("isCancelled: " + cancelled.isCancelled());

        String delayed = CompletableFuture.supplyAsync(
                () -> "started",
                CompletableFuture.delayedExecutor(10, TimeUnit.MILLISECONDS)
        ).join();
        System.out.println("delayedExecutor: " + delayed);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all CompletableFutureCombineDemo.java
java CompletableFutureCombineDemo
~~~

Kết quả chuẩn:

~~~text
combined total: 120
composed: Hello An
allOf sum: 30
anyOf: ready
exceptionally: -1
handle: 0
whenComplete observed: 5
whenComplete result: 5
completeOnTimeout: -1
orTimeout: TimeoutException
isCancelled: true
delayedExecutor: started
~~~

Ví dụ dùng các future đã hoàn tất để kết quả kết hợp ổn định, sau đó tạo các future chưa hoàn tất riêng cho timeout và cancellation. Các timeout được đặt ngắn để minh họa; trong ứng dụng thực tế, hãy chọn deadline theo yêu cầu của dịch vụ và khả năng xử lý của hệ thống.

## 12. Lỗi thường gặp và checklist

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng thenApply khi callback trả về một future | Tạo CompletableFuture lồng nhau | Dùng thenCompose |
| Dùng thenCombine cho các bước phụ thuộc | thenCombine phù hợp với hai nguồn độc lập | Dùng thenCompose nếu bước sau cần kết quả bước trước |
| Nghĩ allOf trả về danh sách kết quả | allOf chỉ trả CompletableFuture<Void> | Lấy từng kết quả sau khi allOf hoàn tất |
| Nghĩ anyOf luôn chọn kết quả thành công đầu tiên | Future hoàn tất đầu tiên có thể thất bại | Xây dựng chính sách xử lý lỗi riêng |
| Dùng whenComplete để phục hồi lỗi | whenComplete chủ yếu quan sát kết quả | Dùng exceptionally hoặc handle |
| Nuốt mọi exception bằng giá trị mặc định | Có thể che giấu lỗi hệ thống | Chỉ phục hồi lỗi đã xác định và ghi nhận lỗi còn lại |
| Gọi join/get trong callback để chờ stage khác | Chặn thread và có thể gây starvation | Dùng thenCombine/thenCompose để nối stage |
| Nghĩ orTimeout dừng supplier | Timeout chỉ hoàn tất future | Gọi cơ chế cancel của tác vụ nền nếu có |
| Nghĩ cancel(true) luôn interrupt thread | CompletableFuture không dùng tham số này để điều khiển tác vụ | Thiết kế cancellation riêng cho tài nguyên nền |
| Dùng common pool cho mọi tác vụ blocking | Có thể làm nghẽn pool dùng chung | Truyền Executor chuyên biệt |
| Bỏ qua cause của CompletionException | Mất nguyên nhân lỗi ban đầu | Kiểm tra getCause() và log đầy đủ |

Trước khi hoàn thiện pipeline, hãy xác định:

- Các tác vụ độc lập hay phụ thuộc nhau.
- Cần chờ tất cả kết quả hay chỉ một kết quả đầu tiên.
- Lỗi nào có thể phục hồi và giá trị thay thế nào hợp lệ.
- Cần ghi nhận lỗi bằng whenComplete hay chuyển kết quả bằng handle.
- Deadline áp dụng cho một tác vụ hay toàn bộ chuỗi.
- Timeout có cần hủy hoạt động nền hay chỉ trả kết quả đúng hạn.
- Executor nào phù hợp với CPU-bound và blocking I/O.
- Ai chịu trách nhiệm đóng executor và tài nguyên liên quan.

Kết hợp CompletableFuture hiệu quả đòi hỏi phân biệt rõ ghép kết quả, nối tác vụ phụ thuộc, phục hồi lỗi và kiểm soát vòng đời. Khi dùng đúng từng API, pipeline bất đồng bộ dễ đọc hơn, có deadline rõ ràng và tránh nhầm lẫn giữa việc hoàn tất một future với việc dừng công việc thực tế.
# Future và CompletableFuture: biểu diễn công việc chưa hoàn tất

Trong Java, một lời gọi hàm thông thường trả về kết quả khi hàm đã chạy xong. Với tác vụ chạy ở luồng khác, lúc gửi việc đi ta có thể **chưa có kết quả**. **Future** và **CompletableFuture** cung cấp một đối tượng đại diện cho kết quả sẽ có trong tương lai, bao gồm cả khả năng thất bại hoặc bị hủy.

Bài này thuộc nhóm **Nền tảng luồng** trong Spring Framework - concurrency. Trọng tâm là hiểu trạng thái của công việc, cách đợi hoặc kết hợp kết quả, điều khiển lỗi và lựa chọn executor. Phần cuối nối kiến thức Java với Spring **@Async**.

## 1. Phân biệt tác vụ, luồng và đối tượng kết quả

- **Task (tác vụ)**: phần công việc cần thực hiện, chẳng hạn tính toán, gọi dịch vụ hoặc đọc dữ liệu.
- **Thread (luồng)**: tài nguyên thực thi tác vụ. Một executor quản lý việc xếp lịch và chạy task trên các luồng.
- **Future<T>**: tay cầm đại diện cho kết quả kiểu T của task đã gửi. Nó không phải chính luồng chạy task.
- **CompletionStage<T>**: giao ước mô tả các bước xử lý phụ thuộc vào kết quả trước đó.
- **CompletableFuture<T>**: vừa thực hiện giao ước Future, vừa thực hiện CompletionStage và cho phép chủ động hoàn tất kết quả.

Một đối tượng future có thể đang chờ, đã hoàn tất thành công, đã hoàn tất với lỗi hoặc đã bị hủy. **isDone()** báo đã hoàn tất *theo bất cứ trạng thái nào*; nó không có nghĩa là thành công. Sự hoàn tất của future và sự dừng thực sự của tác vụ nền cũng không phải lúc nào trùng nhau.

Luồng tư duy:

~~~text
Caller                    Executor / worker
  | submit(task) ----------------> task chạy
  | nhận Future<T>           ... có thể chưa xong
  | làm việc khác
  | get()/join() ---> đợi nếu cần ---> nhận T hoặc lỗi
~~~

**Bất đồng bộ** nói về cách điều phối công việc, không tự động đồng nghĩa với “không bao giờ chặn”. Gọi get() hoặc join() trên kết quả chưa sẵn sàng vẫn chặn luồng gọi.

## 2. Future: nhận kết quả từ ExecutorService

**ExecutorService.submit(Callable<T>)** nhận một hàm có giá trị trả về và trả ngay một **Future<T>**. Các thao tác cốt lõi:

| API | Ý nghĩa |
| --- | --- |
| submit(callable) | Gửi task và nhận Future đại diện cho kết quả. |
| isDone() | True nếu đã xong, thất bại hoặc bị hủy. |
| get() | Chờ tới khi xong; trả kết quả hoặc ném ngoại lệ. |
| get(timeout, unit) | Chờ tối đa một khoảng thời gian; có thể ném TimeoutException. |
| cancel(mayInterruptIfRunning) | Yêu cầu hủy; với Future của executor, tham số true có thể phát tín hiệu interrupt. |
| isCancelled() | True nếu future đã được hủy thành công. |

Ví dụ Java 17+ độc lập, lưu thành **FutureDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> answer = executor.submit(() -> 6 * 7);

            System.out.println("Đã gửi tác vụ");
            System.out.println("Kết quả: " + answer.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac FutureDemo.java
java FutureDemo
~~~

Kết quả chuẩn:

~~~text
Đã gửi tác vụ
Kết quả: 42
~~~

Ở đây phép tính chạy trên executor; get() là điểm đồng bộ hóa. Nếu task chưa xong, luồng main sẽ đợi. Nếu chỉ gửi task rồi lập tức get(), ta ít tận dụng được khả năng làm việc khác trong lúc chờ.

**Ba nhánh kết quả của get():**

1. Task thành công: nhận T.
2. Task ném ngoại lệ: get() ném **ExecutionException**; lỗi gốc thường nằm ở **getCause()**.
3. Luồng gọi bị interrupt: get() ném **InterruptedException**. Ở tầng xử lý chủ động bắt ngoại lệ này, thường phải phục hồi cờ interrupt bằng **Thread.currentThread().interrupt()** rồi dừng hoặc trả lỗi phù hợp. Nếu vượt quá giới hạn ở get(timeout, unit), nhận **TimeoutException**.

**TimeoutException không tự động hủy task**; task vẫn có thể tiếp tục chạy. Với cancel(true), interrupt là yêu cầu hợp tác, không phải cơ chế cưỡng bức dừng mọi công việc, đặc biệt với thao tác không phản ứng interrupt.

**Hạn chế của Future truyền thống:** cung cấp khả năng chờ/hủy/truy vấn, nhưng không có API chuẩn thuận tiện để đăng ký bước xử lý khi hoàn tất, nối nhiều task phụ thuộc hoặc biến đổi kết quả mà không gọi get().

## 3. CompletableFuture: future có thể hoàn tất và nối nhiều bước

**CompletableFuture<T>** bổ sung hai ý tưởng:

1. **Chủ động hoàn tất:** complete(value), completeExceptionally(error) và một số phương thức hoàn tất khác có thể đặt trạng thái của future. Chỉ một lần hoàn tất đầu tiên theo cách thông thường có hiệu lực.
2. **Đăng ký phụ thuộc:** thenApply, thenCompose, thenCombine, handle... tạo các stage tiếp theo. Khi stage trước hoàn tất, stage phụ thuộc có cơ hội chạy theo quy tắc đã đăng ký.

Các cách tạo thường gặp:

| Cách tạo | Cách hiểu |
| --- | --- |
| CompletableFuture.completedFuture(value) | Future đã thành công ngay với value; không tạo task mới. |
| new CompletableFuture<T>() | Future chưa hoàn tất; một bên khác phải gọi complete hoặc completeExceptionally. |
| CompletableFuture.supplyAsync(supplier, executor) | Gửi công việc có kết quả đến executor, trả CompletableFuture<T>. |
| CompletableFuture.runAsync(runnable, executor) | Gửi công việc không có giá trị trả về, trả CompletableFuture<Void>. |

Nếu **supplyAsync/runAsync** không truyền executor, chúng thường dùng **ForkJoinPool.commonPool()** theo chính sách mặc định của CompletableFuture; không nên mặc định sử dụng common pool cho I/O chặn lâu dài trong ứng dụng server. Với **new CompletableFuture<>()**, không có task nào tự được khởi chạy: quên hoàn tất nó có thể khiến người đợi bị treo vô hạn.

## 4. Biến đổi, nối tiếp và ghép nhiều kết quả

| Phương thức | Khi nào dùng | Kiểu kết quả |
| --- | --- | --- |
| thenApply(fn) | Biến đổi kết quả T thành U bằng hàm thông thường. | CompletableFuture<U> |
| thenAccept(action) | Dùng kết quả để tạo tác động phụ, không trả U. | CompletableFuture<Void> |
| thenRun(action) | Chạy bước tiếp theo không cần giá trị trước đó. | CompletableFuture<Void> |
| thenCompose(fn) | Bước sau tự trả một CompletionStage<U>; nối phẳng thay vì lồng future. | CompletableFuture<U> |
| thenCombine(other, fn) | Hai tác vụ độc lập đều hoàn tất thành công rồi mới ghép hai giá trị. | CompletableFuture<V> |
| allOf(f1, f2, ...) | Chờ tất cả future hoàn tất; không tự gom kết quả thành danh sách. | CompletableFuture<Void> |
| anyOf(f1, f2, ...) | Hoàn tất theo future đầu tiên hoàn tất, kể cả trường hợp lỗi. | CompletableFuture<Object> |

**thenApply so với thenCompose:** khi bước tiếp theo trả về một giá trị thường, dùng thenApply; nếu bước đó *đã là bất đồng bộ và trả future*, dùng thenCompose để tránh CompletableFuture<CompletableFuture<U>>. Tương tự, **thenCombine** giải quyết hai nhánh độc lập, còn **thenCompose** biểu diễn quan hệ phụ thuộc (lấy ID trước rồi mới dùng ID để tải hồ sơ).

Ví dụ độc lập, lưu thành **CompletableFutureDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class CompletableFutureDemo {
    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<Integer> price =
                    CompletableFuture.supplyAsync(() -> 100, pool);
            CompletableFuture<Integer> fee =
                    CompletableFuture.supplyAsync(() -> 15, pool);

            CompletableFuture<String> bill = price
                    .thenCombine(fee, Integer::sum)
                    .thenApply(total -> "Tổng: " + total);

            System.out.println(bill.join());

            CompletableFuture<String> id =
                    CompletableFuture.completedFuture("u-7");
            CompletableFuture<String> profile = id.thenCompose(userId ->
                    CompletableFuture.supplyAsync(
                            () -> "Hồ sơ " + userId, pool));

            System.out.println(profile.join());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac CompletableFutureDemo.java
java CompletableFutureDemo
~~~

Kết quả chuẩn (hai câu được in theo thứ tự join của main, dù thứ tự chạy giữa worker có thể khác):

~~~text
Tổng: 115
Hồ sơ u-7
~~~

Sơ đồ phụ thuộc:

~~~text
price ──┐
        ├─ thenCombine ─ thenApply ─ bill
fee ────┘

id ─ thenCompose(id -> tải profile bất đồng bộ) ─ profile
~~~

Ví dụ sau là **đoạn mã minh họa trong phương thức**, giả sử a và b có kiểu CompletableFuture<String>:

~~~java
CompletableFuture<Void> ready = CompletableFuture.allOf(a, b);
CompletableFuture<java.util.List<String>> both = ready.thenApply(
        unused -> java.util.List.of(a.join(), b.join()));
~~~

Sau khi allOf hoàn tất thành công, hai giá trị đều sẵn sàng; các lệnh join() ở đây chỉ dùng để lấy giá trị. **allOf không trả về List**. Nếu một nhánh lỗi, allOf cũng hoàn tất với lỗi và thenApply không chạy. Đối với **anyOf**, không nên giả định nhánh thắng luôn thành công hoặc tự hủy các nhánh còn lại.

## 5. Thực thi callback: không có Async và có Async

Dù future mô tả luồng dữ liệu, **nó không đảm bảo mỗi stage chạy trên luồng riêng**:

- **thenApply/thenCompose/whenComplete...** (không có Async): callback có thể chạy trên luồng hoàn tất stage trước hoặc một luồng khác đang thực hiện quá trình hoàn tất. Nếu stage đã xong khi đăng ký, callback có thể chạy ngay trên luồng đăng ký. Không dựa vào tên luồng cụ thể.
- **thenApplyAsync(...), thenComposeAsync(...)**: đưa phần thực thi callback tới executor bất đồng bộ. Phiên bản truyền executor cho phép lựa chọn pool rõ ràng; phiên bản không truyền executor dùng cơ chế mặc định của CompletableFuture.
- **supplyAsync(..., executor)**: chỉ định nơi chạy supplier gốc. Một stage thenApply không có Async gắn sau đó không mặc nhiên được chuyển sang executor mới.

Nếu callback làm việc rất nặng hoặc I/O chặn, hãy chọn executor phù hợp thay vì để nó vô tình chiếm luồng hoàn tất một stage khác. **Bất đồng bộ không đồng nghĩa với song song**: pool một luồng vẫn có thể xử lý nhiều task luân phiên. Với ứng dụng có tải, kích thước pool, độ dài hàng đợi và chính sách từ chối task là yếu tố vận hành quan trọng.

## 6. Lỗi đi theo chuỗi như thế nào?

Khi một stage ném ngoại lệ, stage đó hoàn tất **exceptionally**. Các bước chỉ dành cho thành công (như thenApply) thường bị bỏ qua, còn các bước xử lý lỗi có thể phục hồi hoặc ghi nhận thất bại.

| API | Chạy khi | Tác dụng |
| --- | --- | --- |
| exceptionally(fn) | Khi stage trước lỗi | Chuyển lỗi thành giá trị dự phòng cùng kiểu T. |
| handle((value, error) -> result) | Khi thành công hoặc lỗi | Tạo một giá trị mới U dựa trên cả hai nhánh. |
| whenComplete((value, error) -> ...) | Khi thành công hoặc lỗi | Quan sát/log/đo đạc; thông thường giữ nguyên kết quả hoặc lỗi. |
| completeExceptionally(error) | Khi bên sản xuất chủ động báo lỗi | Hoàn tất một future đang chờ bằng ngoại lệ. |

Ví dụ Java 17+ độc lập, lưu thành **FailureDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class FailureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> original = new CompletableFuture<>();
        original.completeExceptionally(
                new IllegalStateException("Không đọc được dữ liệu"));

        CompletableFuture<Integer> recovered =
                original.exceptionally(error -> 0);

        System.out.println("Giá trị dự phòng: " + recovered.join());
        System.out.println("Nguồn lỗi: " + original.isCompletedExceptionally());

        String status = original.handle((value, error) ->
                error == null ? "Thành công: " + value : "Thất bại");
        System.out.println(status);
    }
}
~~~

Chạy:

~~~bash
javac FailureDemo.java
java FailureDemo
~~~

Kết quả chuẩn:

~~~text
Giá trị dự phòng: 0
Nguồn lỗi: true
Thất bại
~~~

Chú ý **recovered** là future mới đã phục hồi; **original** vẫn thất bại. **whenComplete** thường dùng để quan sát; không chọn nó thay exceptionally/handle nếu cần trả fallback. Nếu chính callback xử lý lỗi lại ném ngoại lệ, stage mới vẫn có thể thất bại.

**get() so với join():**

- **get()** là API của Future, chặn và khai báo InterruptedException, ExecutionException; có biến thể timeout. Phù hợp khi cần quản lý interrupt tường minh.
- **join()** cũng chờ nhưng dùng CompletionException không kiểm tra cho các lỗi tính toán bất đồng bộ (hoặc CancellationException khi bị hủy); thuận tiện khi nối pipeline.
- Đừng nuốt lỗi bằng cách trả giá trị mặc định cho mọi thất bại nếu điều đó che mất vấn đề nghiệp vụ. Nên ghi nhận/ngữ cảnh hóa nguyên nhân gốc và quyết định có được fallback hay không.

## 7. Timeout, hủy và vòng đời tác vụ

Có ba cơ chế rất dễ nhầm:

1. **future.get(500, MILLISECONDS)** giới hạn *thời gian chờ của người gọi*. Hết 500 ms thì người gọi nhận TimeoutException, nhưng future/task có thể tiếp tục.
2. **future.orTimeout(500, MILLISECONDS)** làm chính CompletableFuture hoàn tất với TimeoutException nếu chưa xong khi hết hạn; phương thức trả lại **cùng đối tượng future**. **completeOnTimeout(fallback, ...)** cũng tác động lên future đó nhưng hoàn tất bình thường bằng fallback.
3. **future.cancel(true)** yêu cầu hủy. Với CompletableFuture chuẩn, tham số **mayInterruptIfRunning không có tác dụng điều khiển interrupt**; hủy được biểu diễn như một dạng hoàn tất đặc biệt với CancellationException. Điều này **không đảm bảo công việc nền đã dừng**.

Sự khác biệt này thiết yếu với các lời gọi mạng hoặc truy vấn có thể chạy rất lâu. Timeout của future là deadline ở tầng điều phối; cần cấu hình timeout/interrupt/cancellation phù hợp ở client I/O hoặc API thực thi thật sự để kiểm soát tài nguyên. Nếu cần dừng công việc, thiết kế task biết kiểm tra interrupt hoặc cơ chế hủy của thư viện đang dùng.

**Đừng tạo future rồi không ai hoàn tất:** một CompletableFuture chưa được complete/completeExceptionally/cancel sẽ khiến join() chờ vô hạn. Tương tự, dùng get()/join() trong một task đang chiếm hết pool để chờ task khác cũng nằm trong chính pool có thể gây **thread starvation hoặc deadlock**. Nên biểu diễn phụ thuộc bằng thenCompose/thenCombine thay vì block chéo giữa các worker.

**Đừng quên đóng executor tự tạo:** với ExecutorService, gọi shutdown() khi không còn gửi task, rồi dùng awaitTermination hoặc chính sách shutdown thích hợp khi ứng dụng cần chờ dọn dẹp. Các ví dụ trên đã đợi kết quả cần dùng trước khi shutdown.

## 8. Liên hệ trực tiếp với Spring Framework

Spring cung cấp **TaskExecutor** và **@Async** để thực thi phương thức bean trên executor. Future/CompletableFuture vẫn là kiểu đối tượng mà phía gọi nhận để theo dõi hoặc kết hợp kết quả; @Async điều khiển **nơi phương thức chạy**, còn CompletableFuture hỗ trợ **cách các kết quả liên kết với nhau**.

Ví dụ dưới đây là **các đoạn cấu hình/service cho ứng dụng Spring có dependency Spring Context**; không phải một chương trình Java độc lập chạy bằng hai lệnh javac/java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfig {
    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("io-");
        executor.initialize();
        return executor;
    }
}
~~~

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @Async("ioExecutor")
    public CompletableFuture<String> loadReport(String id) {
        // Giả sử ở đây có phép đọc dữ liệu đồng bộ/tác vụ I/O.
        String content = "report:" + id;
        return CompletableFuture.completedFuture(content);
    }
}
~~~

Một bean khác gọi **reportService.loadReport("r-1")** qua Spring proxy sẽ nhận future đại diện cho việc thực thi bất đồng bộ của lời gọi; nó có thể gắn thêm thenApply/exceptionally thay vì chờ ngay. Trong ví dụ, **completedFuture** được trả từ *bên trong* phương thức đã được @Async đưa sang worker: không cần tự tạo thêm supplyAsync chỉ để bọc kết quả đã tính.

Các ràng buộc khi áp dụng:

- Phải bật hỗ trợ async (ví dụ **@EnableAsync**) và gọi qua Spring bean/proxy. **Tự gọi phương thức @Async bên trong cùng đối tượng** trong cấu hình proxy thông thường không đi qua interceptor, nên không tạo chuyển luồng như mong đợi.
- Chỉ định executor có quản trị; cấu hình pool, hàng đợi, rejection và shutdown cho tải dự kiến. Pool I/O và pool CPU có thể có đặc tính khác nhau.
- Phương thức **@Async** có thể trả **Future** hoặc **CompletableFuture** để người gọi theo dõi lỗi; nếu trả void, lỗi không được chuyển cho caller theo cơ chế future (Spring có AsyncUncaughtExceptionHandler).
- Transaction, SecurityContext, MDC và các trạng thái gắn với ThreadLocal **không tự động được chuyển sang luồng khác trong mọi cấu hình**. Khi cần, dùng cơ chế truyền ngữ cảnh được hỗ trợ, và xác định rõ ranh giới transaction.
- Nếu một web request gọi @Async rồi **join() ngay trên luồng request**, vẫn có đoạn chặn; cần đánh giá cơ chế trả lời bất đồng bộ thật sự ở tầng web thay vì chỉ nhìn annotation.

Một CompletableFuture tự khởi chạy bằng supplyAsync trên executor thuần Java **không tự biến thành** phương thức @Async của Spring. Hai cách có thể bổ sung nhau nhưng không cần lồng async vô ích.

## 9. Những lỗi thiết kế phổ biến và cách nhận biết

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| submit rồi get() ngay | Caller chặn, ít chồng lấp công việc. | Làm việc độc lập trước khi đợi hoặc dùng pipeline. |
| Dùng thenApply với hàm trả future | Tạo future lồng, khó điều phối. | Chọn thenCompose. |
| Tin isDone() đồng nghĩa thành công | Bỏ qua lỗi/hủy. | Kiểm tra get/join, isCompletedExceptionally, isCancelled khi phù hợp. |
| Tin cancel(true) của CompletableFuture dừng I/O | Công việc nền có thể tiếp tục tiêu tốn tài nguyên. | Kết hợp timeout và hủy ở tầng tác vụ/client. |
| Block giữa các task trên pool nhỏ | Cạn worker hoặc deadlock. | Kết hợp stage thay vì join chéo; xem lại cấu hình pool. |
| Dùng commonPool cho nhiều tác vụ I/O lâu | Tranh chấp với các công việc khác. | Truyền executor phù hợp và giới hạn tải. |
| Nuốt exception bằng fallback chung | Ẩn sự cố và dữ liệu sai. | Xử lý có chủ đích, log nguyên nhân và phân biệt lỗi dự phòng. |
| Quên complete một future tự tạo | Người gọi chờ mãi. | Quy định ai sở hữu việc hoàn tất mọi nhánh, kể cả lỗi/hủy. |
| Gọi @Async từ chính bean đó | Có thể không qua Spring proxy. | Gọi qua bean được Spring quản lý ở ranh giới phù hợp. |

## 10. Chọn công cụ theo yêu cầu

- **Chỉ cần gửi một phép tính và cuối cùng chờ kết quả:** ExecutorService + Future thường đủ, đặc biệt khi muốn xử lý interrupt/timeout theo mẫu truyền thống.
- **Cần biến đổi hoặc phối hợp nhiều kết quả bất đồng bộ:** CompletableFuture với thenApply, thenCompose, thenCombine, allOf và xử lý lỗi có thể đọc được hơn.
- **Cần nhiều phương thức service chạy ngoài luồng gọi trong ứng dụng Spring:** TaskExecutor + @Async; chọn kiểu trả về CompletableFuture khi caller cần nối stage.
- **Cần kiểm soát hạn chót và tài nguyên:** deadline, chính sách hủy và timeout thực ở tầng I/O là phần thiết kế riêng; future chỉ biểu diễn và điều phối trạng thái.

## 11. Bài tập tự kiểm tra

1. **Dự đoán:** task đã ném IllegalStateException; isDone() là true hay false? **Đáp án:** true, vì task đã hoàn tất với lỗi; get() sẽ ném ExecutionException.
2. **Chọn phép nối:** bước A trả mã người dùng; bước B gọi API bất đồng bộ để tải hồ sơ theo mã đó. **Đáp án:** thenCompose, vì B trả một stage mới phụ thuộc A.
3. **Hai request độc lập trả giá và phí:** muốn tính tổng khi cả hai thành công. **Đáp án:** thenCombine; nếu muốn đợi nhiều request không dùng trực tiếp giá trị thì allOf.
4. **get(timeout) ném TimeoutException:** task có bị hủy không? **Đáp án:** không tự động.
5. **Gọi cancel(true) trên CompletableFuture:** có chắc worker bị interrupt không? **Đáp án:** không; tham số không chi phối interrupt trong triển khai CompletableFuture chuẩn.
6. **Một @Async gọi từ this.loadReport():** có chắc chạy ở executor không? **Đáp án:** không trong chế độ Spring proxy thông thường, vì self-invocation bỏ qua proxy.

## 12. Ghi nhớ bản chất

**Future** là lời hứa *sẽ có kết quả hoặc lỗi* của công việc đã được gửi; sử dụng trực tiếp chủ yếu bằng kiểm tra trạng thái và chờ. **CompletableFuture** còn là một điểm hoàn tất và một đồ thị phụ thuộc: nó giúp mô tả **khi có A thì làm B**, **khi có cả A và B thì ghép**, **khi lỗi thì phục hồi**, mà không cần chặn tại từng bước. Tuy vậy, **lịch chạy trên executor, giới hạn tài nguyên, timeout I/O và cơ chế hủy thực tế** vẫn phải được thiết kế riêng. Trong Spring, @Async đưa phần thực thi của phương thức qua TaskExecutor; CompletableFuture giúp người gọi kết hợp kết quả đó.

**Tài liệu API nên tra cứu:** Java SE 17 java.util.concurrent.Future, CompletionStage, CompletableFuture; Spring Framework Reference, mục Task Execution and Scheduling và @Async.

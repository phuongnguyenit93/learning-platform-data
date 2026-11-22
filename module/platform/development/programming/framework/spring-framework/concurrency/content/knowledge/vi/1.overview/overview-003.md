# Tác vụ, luồng gọi, luồng xử lý và kết quả trong Spring Framework

## Mục tiêu

Sau bài này, bạn có thể phân biệt **tác vụ (task)**, **luồng gọi (caller thread)**, **luồng thực thi (worker/execution thread)** và **kết quả (result)**; lần theo một lời gọi đồng bộ hoặc bất đồng bộ; nhận ra vai trò của `TaskExecutor`, `@Async` và `CompletableFuture`; đồng thời giải thích khi nào luồng gọi còn phải chờ, lỗi đi đâu và những dữ liệu nào không tự đi theo luồng mới.

Phạm vi bài là mô hình thực thi và dòng chảy kết quả trong Spring Framework. Các kỹ thuật lập lịch định kỳ, tinh chỉnh thread pool sâu và lập trình reactive chỉ được nhắc đến để phân biệt, không phải trọng tâm.

## 1. Bốn khái niệm cần tách riêng

| Thành phần | Bản chất | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Task (tác vụ)** | Một đơn vị công việc có thể được thực hiện, ví dụ ghi báo cáo, gọi dịch vụ ngoài, tính toán. Trong Java thường được biểu diễn bằng `Runnable`, `Callable<T>` hoặc thân một phương thức. | *Cần làm việc gì?* |
| **Caller thread (luồng gọi)** | Luồng đang chạy mã gọi phương thức hoặc gửi task cho executor; có thể là `main`, luồng HTTP request hoặc một worker khác. | *Ai khởi phát công việc?* |
| **Execution/worker thread (luồng xử lý)** | Luồng thực sự chạy phần thân công việc sau khi cơ chế thực thi quyết định; có thể là luồng trong pool, luồng mới hoặc ngay luồng gọi nếu dùng bộ thực thi đồng bộ. | *Công việc thực sự chạy ở đâu?* |
| **Result (kết quả)** | Giá trị trả về, trạng thái hoàn tất, ngoại lệ hoặc hủy; với bất đồng bộ có thể được đại diện bởi `Future<T>`/`CompletableFuture<T>` trước khi giá trị sẵn sàng. | *Người gọi nhận gì, lúc nào và bằng cách nào?* |

**Task không đồng nghĩa với thread.** Một thread có thể chạy nhiều task nối tiếp; một executor có thể xếp task vào hàng đợi, dùng lại thread hoặc từ chối task khi quá tải. Việc tạo `CompletableFuture` cũng không tự chứng minh công việc đang chạy trên thread khác: phải xem nơi task được thực thi.

**Kết quả bất đồng bộ có hai lớp:** đối tượng đại diện cho kết quả trong tương lai được trả về trước; giá trị hoặc lỗi thực tế chỉ xuất hiện khi task hoàn thành. Một `CompletableFuture` có thể đã hoàn thành ngay lúc caller nhận được nó; không được dựa vào trạng thái “chưa hoàn thành” để xác định một lời gọi là bất đồng bộ.

## 2. Đường đi của một lời gọi

### Lời gọi đồng bộ

```text
Caller thread
  -> gọi service.process()
  -> chính caller chạy thân phương thức
  -> nhận giá trị hoặc ngoại lệ
  -> mới chạy tiếp câu lệnh kế tiếp
```

Ví dụ `String value = service.process();` chạy trực tiếp theo cách thông thường: nếu `process()` mất 500 ms, caller phải đợi nó kết thúc. Kể cả bên trong phương thức có I/O hoặc `Thread.sleep`, lời gọi vẫn là đồng bộ nếu caller chưa được trả quyền điều khiển.

### Lời gọi bất đồng bộ qua executor

```text
Caller thread            Executor / hàng đợi             Worker thread
  | submit(task)  -------------> |                            |
  | <--- Future/handle           | ---- giao task ----------> |
  | tiếp tục việc khác           |                            | chạy task
  |                              |                            | tạo value/lỗi
  | Future được hoàn tất <----------------------------------- |
  | chỉ đợi nếu gọi get()/join() hoặc có bước phụ thuộc cần chờ
```

Một trình tự thường gặp:

1. Caller tạo dữ liệu đầu vào và gửi công việc; việc gửi có thể tốn thời gian hoặc bị từ chối.
2. Executor chọn lúc và nơi chạy task theo chính sách cấu hình.
3. Caller nhận một handle, thường là `Future`/`CompletableFuture`, và *có thể* làm việc khác.
4. Worker chạy task, rồi ghi nhận giá trị hoặc ngoại lệ vào handle.
5. Caller quan sát kết quả bằng callback/composition hoặc bằng `get()`/`join()` nếu chấp nhận chờ.

**Bất đồng bộ không có nghĩa là không có chỗ nào bị chặn.** `join()` chặn thread đang gọi nó nếu kết quả chưa sẵn sàng; I/O blocking trong worker vẫn chiếm worker. Bất đồng bộ là cách tách thời điểm/địa điểm xử lý khỏi luồng gọi, còn non-blocking là đặc tính của thao tác cụ thể.

## 3. Spring đặt cơ chế thực thi ở đâu?

Spring cung cấp `TaskExecutor` như một cách trừu tượng hóa việc thực thi task. `ThreadPoolTaskExecutor` là một triển khai thường dùng với thread pool và hàng đợi; tùy executor, công việc không nhất thiết luôn chạy trên luồng khác. Không có quy tắc “mỗi task tạo một thread”.

| Cách gọi | Đường thực thi | Cách nhận kết quả |
| --- | --- | --- |
| Gọi phương thức Java thông thường | Thân phương thức chạy ngay trên caller, trừ khi nó tự chuyển việc đi. | Giá trị hoặc ngoại lệ trực tiếp. |
| `taskExecutor.execute(runnable)` | Executor nhận `Runnable`, chọn thread/thời điểm thực thi. | `execute` không trả handle chứa giá trị; phải tự tổ chức tín hiệu/kết quả nếu cần. |
| Gọi bean có `@Async` **qua Spring proxy** | Interceptor gửi lời gọi sang executor được chọn; phần thân phương thức chạy trong executor. | Thường dùng `CompletableFuture<T>`/`Future<T>` hoặc `void`; lỗi phải được quan sát đúng kênh. |
| `CompletableFuture.supplyAsync(supplier, executor)` | Java gửi `Supplier` tới executor được chỉ định. | `CompletableFuture<T>` do JDK quản lý, có thể ghép các bước xử lý. |

Đường đi điển hình của `@Async`:

```text
Bean A (caller)
  -> Spring proxy của Bean B
     -> bộ chặn @Async chọn executor
        -> gửi công việc vào executor
        -> caller nhận CompletableFuture
           -> worker chạy phương thức thật của Bean B
              -> hoàn tất kết quả hoặc lỗi
```

Để `@Async` có tác dụng theo cơ chế proxy mặc định, cần bật hỗ trợ bằng `@EnableAsync`, gọi phương thức qua bean do Spring quản lý và có executor phù hợp. `this.someAsyncMethod()` trong chính bean đó là **self-invocation**: không đi qua proxy, nên thường chạy đồng bộ trên thread hiện tại. Các phương thức không thể được proxy/intercept phù hợp cũng không cho kết quả mong đợi.

`@Async("lessonExecutor")` chọn rõ bean executor có tên `lessonExecutor`. Khi không chỉ định, Spring lựa chọn theo cấu hình async hiện hành; đừng dựa vào một tên thread hoặc executor mặc định nếu chưa kiểm tra cấu hình thực tế.

## 4. Ví dụ Spring Framework có thể chạy với Java 17+

Ví dụ độc lập này cố định Spring Framework 6.2.0 để tái lập. Nó chủ động lưu đối tượng `Thread` vào kết quả **chỉ để kiểm chứng đường thực thi**, không phải mẫu dữ liệu nên trả về từ nghiệp vụ thật.

Cấu trúc:

```text
async-flow-demo/
├── pom.xml
└── src/main/java/example/AsyncFlowDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-flow-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>example.AsyncFlowDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/AsyncFlowDemo.java`:

```java
package example;

import java.util.concurrent.CompletableFuture;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncFlowDemo {
    public record WorkResult(String value, Thread executedBy) {}

    public static class WorkService {
        @Async("lessonExecutor")
        public CompletableFuture<WorkResult> process(String input) {
            WorkResult value = new WorkResult(
                "done:" + input,
                Thread.currentThread()
            );
            return CompletableFuture.completedFuture(value);
        }
    }

    @Configuration
    @EnableAsync
    public static class Config {
        @Bean
        public WorkService workService() {
            return new WorkService();
        }

        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(16);
            executor.setThreadNamePrefix("lesson-");
            return executor;
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            WorkService service = context.getBean(WorkService.class);
            Thread caller = Thread.currentThread();

            CompletableFuture<WorkResult> handle = service.process("A");
            // Ở đây caller đã có handle; task có thể đang chạy hoặc đã xong.
            WorkResult result = handle.join();

            System.out.println("differentThread="
                + (result.executedBy() != caller));
            System.out.println("result=" + result.value());
        }
    }
}
```

Chạy từ thư mục `async-flow-demo` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

Hai dòng do chương trình in ra:

```text
differentThread=true
result=done:A
```

Ý nghĩa từng chặng:

1. `main` giữ tham chiếu `caller` tới thread đã gọi service.
2. `context.getBean(WorkService.class)` lấy bean đã được Spring xử lý; lời gọi `process("A")` qua proxy được gửi tới `lessonExecutor`.
3. Worker của pool chạy thân `process`, tạo `WorkResult("done:A", currentThread)`. `completedFuture(...)` ở **bên trong worker** chỉ đóng gói giá trị đã tính; nó không biến việc thực thi thành đồng bộ trên caller.
4. `handle` là đối tượng kết quả mà caller cầm được. `handle.join()` chờ nếu worker chưa xong, rồi lấy `WorkResult`.
5. `differentThread=true` xác nhận trong cấu hình cụ thể này, worker là thread khác caller. Thứ tự chạy thực tế vẫn do executor và scheduler quyết định.

Nếu cần quan sát tên luồng, tạm thêm `System.out.println(Thread.currentThread().getName())` trong caller và thân `process`. Tên chính xác và thời điểm các dòng log xen kẽ phụ thuộc runtime, nên không nên viết test phụ thuộc thứ tự log giữa các thread.

## 5. Kết quả, lỗi và bước xử lý tiếp theo

### Giá trị và chờ

- `Future<T>.get()` lấy kết quả khi sẵn sàng; có thể chặn và khai báo các ngoại lệ kiểm tra, gồm `InterruptedException` và `ExecutionException`.
- `CompletableFuture<T>.join()` cũng chờ khi cần nhưng báo lỗi hoàn tất thông qua `CompletionException` (unchecked).
- `thenApply` biến đổi giá trị sau khi hoàn thành; `thenCompose` ghép một bước trả về `CompletionStage` khác; `thenCombine` kết hợp hai kết quả độc lập.
- `thenApply` không bảo đảm callback chạy trên một thread riêng: nó có thể chạy trong luồng hoàn tất stage hoặc thread đăng ký nếu stage đã xong. Các biến thể `...Async` chọn cơ chế thực thi bất đồng bộ; nên truyền executor tường minh khi cần kiểm soát tài nguyên.

Đoạn sau minh họa cách dùng trong một phương thức đã có `WorkService service` (không phải một chương trình Java độc lập):

```java
CompletableFuture<String> displayName = service.process("A")
    .thenApply(work -> "Output = " + work.value());

displayName.whenComplete((value, error) -> {
    if (error != null) {
        System.err.println("Task failed: " + error.getMessage());
    } else {
        System.out.println(value);
    }
});
```

`whenComplete` quan sát cả thành công và thất bại; nếu cần *phục hồi* bằng giá trị dự phòng, cân nhắc `exceptionally` hoặc `handle`. Đừng nuốt lỗi bằng cách trả về giá trị giả mà không ghi nhận nguyên nhân.

### Ngoại lệ, timeout, hủy

Với `@Async` trả về `Future`/`CompletableFuture`, ngoại lệ của công việc được ghi vào kết quả bất đồng bộ và chỉ hiện rõ khi bạn quan sát stage (ví dụ `join`, `get`, `whenComplete`). Với phương thức `@Async void`, caller không thể nhận lỗi qua giá trị trả về; cấu hình `AsyncUncaughtExceptionHandler` khi cần xử lý tập trung, tránh cơ chế “fire-and-forget” cho tác vụ quan trọng.

`orTimeout(2, TimeUnit.SECONDS)` có thể làm `CompletableFuture` hoàn tất bằng lỗi timeout; **timeout kết quả không tự bảo đảm dừng tác vụ nền**. Hủy một `CompletableFuture` cũng không phải cam kết ngắt thread đang chạy. Muốn có hủy thực sự cần thiết kế tác vụ hợp tác kiểm tra trạng thái, timeout ở I/O, và cơ chế hủy phù hợp.

Nếu executor hết khả năng nhận task, việc *gửi* có thể thất bại bằng lỗi từ chối (ví dụ `TaskRejectedException` trong Spring). Trường hợp này khác với ngoại lệ phát sinh sau khi worker bắt đầu xử lý; cả hai phải được tính trong thiết kế lỗi.

## 6. Luồng HTTP và luồng tác vụ không phải một

Ví dụ trong một ứng dụng Spring MVC Servlet:

```text
HTTP request -> servlet request thread -> Controller
                 |                        |
                 | gọi @Async service     | có thể nhận CompletableFuture
                 |----------------------> | rồi return / join / xử lý khác
                                          |
                                 worker thread xử lý service
```

Nếu controller gọi `service.process(...).join()` ngay, thread đang thực thi controller vẫn chờ kết quả. Việc service chạy ở worker **không tự động giải phóng HTTP request thread** trong thời gian chờ.

Spring MVC có cơ chế xử lý request bất đồng bộ riêng, ví dụ controller trả về `Callable<T>`, `DeferredResult<T>` hoặc `CompletionStage<T>`/`CompletableFuture<T>` được hỗ trợ. Với `Callable`, Spring MVC gửi phần tính toán tới `AsyncTaskExecutor`, nhả thread Servlet đang phục vụ request rồi dispatch lại khi có kết quả. Với `DeferredResult`, một nguồn bên ngoài hoàn tất kết quả và MVC dispatch lại để trả response. HTTP response vẫn chỉ hoàn tất khi đã có dữ liệu phù hợp hoặc lỗi/timeout.

Vì vậy cần nêu rõ **hai hợp đồng tách biệt** khi thiết kế: (1) phương thức service được thực thi trên executor nào, (2) request HTTP được giữ chờ hay được framework quản lý theo chế độ async. Không coi `@Async` là một cách tự động biến toàn bộ controller thành non-blocking; một worker chạy JDBC blocking vẫn là một thread bị chiếm trong khoảng thời gian đó.

## 7. Dữ liệu đi qua ranh giới thread

**Tham số và đối tượng chia sẻ:** dữ liệu được truyền cho task vẫn tuân theo các quy tắc an toàn luồng của Java. Nếu caller sửa một `ArrayList` hoặc DTO mutable trong lúc worker đọc nó, dễ xảy ra race condition. Ưu tiên dữ liệu bất biến, snapshot trước khi submit hoặc đồng bộ hóa đúng cách.

**`ThreadLocal` và context:** MDC logging, `SecurityContext`, request/locale context và transaction theo thread không mặc nhiên chuyển sang worker. Nếu cần, chọn cơ chế truyền context có chủ đích, ví dụ `TaskDecorator` cho dữ liệu logging và executor hỗ trợ security context. Không dùng context của HTTP request sau khi request kết thúc nếu nó không còn hợp lệ.

**Giao dịch:** giao dịch gắn với thread caller không tự “đi theo” `@Async`. Một thao tác ghi dữ liệu trên worker cần ranh giới giao dịch riêng nếu yêu cầu; thường đặt xử lý transactional ở bean được gọi từ worker thông qua Spring proxy. Tránh dựa vào transaction của caller để bảo đảm atomicity cho công việc nền.

**Vòng đời:** task `@Async` chạy trong tiến trình ứng dụng. Nếu tiến trình dừng, tác vụ chưa hoàn tất có thể mất; task quan trọng phải được thiết kế có tính bền vững, retry/idempotency và có thể cần hàng đợi/broker hoặc job store. Đóng executor và xử lý shutdown có kiểm soát.

## 8. Sai lầm thường gặp và cách xác minh

| Sai lầm | Hậu quả | Cách kiểm tra/sửa |
| --- | --- | --- |
| Nghĩ `@Async` luôn chạy trên luồng khác mà không kiểm tra proxy | Lời gọi có thể vẫn đồng bộ do thiếu `@EnableAsync` hoặc self-invocation. | Gọi qua bean Spring được inject; kiểm tra cấu hình, thread và proxy. |
| Cho rằng task = thread | Kỳ vọng mỗi lời gọi có một thread riêng; khó dự đoán dưới tải. | Đo số worker, queue và hành vi executor. |
| Gọi `join()` ngay rồi tuyên bố caller “không chờ” | Caller bị chặn cho tới khi task xong. | Ghi nhận thời điểm submit, thời điểm join và thời điểm hoàn tất. |
| Đoán thứ tự chạy qua thứ tự câu lệnh submit | Task khác nhau có thể hoàn tất không theo thứ tự gửi. | Ghép kết quả bằng ID hoặc các stage, không dựa vào thứ tự log. |
| Dùng `@Async void` cho việc cần bảo đảm thành công | Không có handle để biết lỗi/kết quả. | Trả `CompletableFuture<T>` hoặc lưu trạng thái công việc bền vững. |
| Đặt executor quá nhỏ, queue không giới hạn hoặc thiếu chính sách từ chối | Độ trễ, bùng bộ nhớ, task bị loại trong giờ cao điểm. | Chọn giới hạn phù hợp, đo queue/active threads/rejection, thiết kế backpressure. |
| Dùng chung state hoặc giả định transaction/context theo thread được kế thừa | Race condition, mất thông tin logging/security, giao dịch không đúng. | Dùng dữ liệu an toàn luồng và truyền context/ràng buộc giao dịch tường minh. |

Một quy trình chẩn đoán ngắn: đặt ID cho task → log thời điểm/caller thread tại điểm gửi → log worker thread tại đầu/cuối task → quan sát trạng thái/completion của handle → xác định nơi `get`/`join` hoặc response HTTP đang chờ → ghi nhận thành công, lỗi, timeout và rejection. Dùng `Thread.currentThread().getName()` để quan sát; không suy luận chỉ từ tên annotation.

## 9. Tự kiểm tra

1. **Controller gọi `@Async` service rồi `join()` ngay.** Service có thể chạy trên worker, nhưng thread controller vẫn chờ; muốn HTTP request bất đồng bộ còn cần hợp đồng trả về phù hợp với Spring MVC.
2. **Một executor chỉ có một worker nhận ba task.** Chúng vẫn là ba task độc lập, nhưng có thể phải chạy nối tiếp; “đã submit” không đồng nghĩa “đã chạy song song”.
3. **Phương thức `@Async` được gọi bằng `this.method()` trong cùng bean.** Với proxy mode mặc định, lời gọi nội bộ không đi qua interceptor, nên không có chuyển việc sang executor nhờ annotation.
4. **Caller nhận `CompletableFuture` đã `isDone() == true`.** Điều đó không chứng minh lời gọi chạy đồng bộ; task có thể hoàn tất rất nhanh trước khi kiểm tra.
5. **Worker ném ngoại lệ.** Với phương thức trả `CompletableFuture`, phải quan sát kết quả bất đồng bộ để biết lỗi; ngoại lệ không nhất thiết được ném ngay tại dòng caller gọi proxy.

### Ghi nhớ

Một lời gọi có bốn câu hỏi độc lập: **việc gì cần chạy, ai gửi việc, thread nào thực sự chạy và kết quả được quan sát lúc nào**. Khi đọc mã Spring concurrency, lần theo cả bốn trước khi kết luận hệ thống có chạy song song, có giải phóng thread hay có xử lý lỗi an toàn.

### Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `ThreadPoolTaskExecutor`, `@EnableAsync`, `@Async`, lựa chọn executor và lỗi.
- [Spring Framework — Asynchronous Requests (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): phân biệt xử lý service task với vòng đời request Servlet bất đồng bộ.

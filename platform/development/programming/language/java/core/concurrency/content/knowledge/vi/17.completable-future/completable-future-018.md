# completedStage(), failedFuture(), failedStage(): kết quả đã có và kết quả lỗi

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích **CompletionStage<T>** và **CompletableFuture<T>** trong Java concurrency; phân biệt **normal completion**, **exceptional completion** và trạng thái chưa hoàn tất.
- Hiểu ba factory **CompletableFuture.completedStage(value)**, **CompletableFuture.failedFuture(exception)**, **CompletableFuture.failedStage(exception)** và đối chiếu với **completedFuture(value)**.
- Biết vì sao completedStage/failedStage có public return type **CompletionStage<U>** tối giản, còn failedFuture/completedFuture có public return type **CompletableFuture<U>** đầy đủ.
- Tổ chức API có kết quả sẵn hoặc lỗi đầu vào ngay lập tức mà vẫn trả về một asynchronous-style contract thống nhất.
- Phân biệt **thenApply**, **thenCompose**, **thenApplyAsync**, **exceptionally**, **exceptionallyCompose**, **handle**, **whenComplete** trên upstream bình thường và upstream đã failed.
- Lấy kết quả/lỗi đúng qua **toCompletableFuture()**, **join()**, **get()**, hiểu **CompletionException** và **ExecutionException**.
- Nhận diện sai lầm về **thread scheduling**, **cancellation**, **mutable result**, **null**, callback chạy ngay, lỗi bị che và retry tưởng tượng.
- Biên dịch và chạy các chương trình Java 17+ với stdout xác định, không dựa vào Thread.sleep hoặc thứ tự scheduling ngẫu nhiên.

Bài thuộc **Java Advance - concurrency**, nhóm **CompletableFuture**, và chỉ trình bày các công cụ concurrency của Java nói chung. Những phần liên quan Spring đã có chương riêng.

## 2. Hai interface nền tảng: CompletionStage và Future

**CompletionStage<T>** diễn tả một giai đoạn của một pipeline tính toán. Nó cho phép đăng ký công việc phụ thuộc vào việc giai đoạn trước hoàn tất, có thể hợp thành cả một đồ thị các bước.

**Future<T>** cung cấp cơ chế quan sát một kết quả có thể đến trong tương lai: **get()**, trạng thái hoàn tất, cancellation.

**CompletableFuture<T>** vừa triển khai **CompletionStage<T>**, vừa triển khai **Future<T>**, lại cung cấp các phương thức để hoàn tất kết quả như **complete()** và **completeExceptionally()**.

~~~text
CompletionStage<T>          Future<T>
  | thenApply                | get()
  | thenCompose              | cancel()
  | exceptionally            | isDone()
  | handle                   |
  +-----------+--------------+
              |
       CompletableFuture<T>
              |
        complete / join
        completeExceptionally
        isCompletedExceptionally
~~~

Trong các method public, chọn kiểu trả về là quyết định thiết kế:

- Trả **CompletionStage<T>** nếu caller chỉ cần composition, tức nối tiếp, kết hợp, hoặc recovery.
- Trả **CompletableFuture<T>** nếu caller thực sự cần một concrete Future có get/join/cancel, hoặc contract cho phép điều khiển completion.
- Không giả định một đối tượng **CompletionStage** có thể cast an toàn sang CompletableFuture rồi gọi mọi method. Một minimal stage có thể không hỗ trợ các thao tác ngoài interface.

### Ba trạng thái quan trọng

1. **Pending:** chưa có kết quả cuối; một task có thể đang thực hiện hoặc chưa được lên lịch.
2. **Normal completion:** hoàn tất với một value, kể cả **null**.
3. **Exceptional completion:** hoàn tất đặc biệt với Throwable; downstream chỉ thành công nếu có recovery.

**Một Future đã failed cũng là Future đã done.** isDone() không trả lời câu hỏi “nghiệp vụ đã thành công hay chưa”.

## 3. Các factory cho kết quả đã biết

| Factory | Public return type | Trạng thái ngay khi trả | Có tạo task/thread? |
| --- | --- | --- | --- |
| **completedFuture(value)** | CompletableFuture<U> | Normal completion | Không |
| **completedStage(value)** | CompletionStage<U> | Normal completion | Không |
| **failedFuture(ex)** | CompletableFuture<U> | Exceptional completion | Không |
| **failedStage(ex)** | CompletionStage<U> | Exceptional completion | Không |

**completedFuture** có trong Java 8. **completedStage**, **failedFuture** và **failedStage** được bổ sung từ Java 9. Java 17 hỗ trợ cả bốn.

Đây là **static factory methods** của lớp CompletableFuture, không phải các constructor khởi động một worker. Bản thân việc tạo completed/failed stage là biểu diễn **trạng thái cuối đã có**.

### Không nhầm result với execution

Một method có thể trả CompletionStage vì người gọi quen dùng mô hình asynchronous, nhưng trong đường **cache hit** hoặc **input invalid**, kết quả đã biết tại thời điểm gọi. Không có lý do bắt buộc phải tạo Thread hoặc supplyAsync giả chỉ để duy trì return type.

~~~java
// Mảnh mã trong một method trả CompletionStage<String>.
if (cached != null) {
    return CompletableFuture.completedStage(cached);
}
if (!valid) {
    return CompletableFuture.failedStage(
            new IllegalArgumentException("invalid input")
    );
}
return loadAsync();
~~~

Các biến và loadAsync là thành phần giả định. Mảnh code không chạy độc lập. Nó diễn đạt một API thống nhất: đường bình thường và đường lỗi đều có thể được caller nối continuation.

## 4. completedStage(value): thành công và chỉ cấp quyền composition

**CompletableFuture.completedStage(value)** trả CompletionStage<U> đã hoàn tất bình thường.

~~~java
CompletionStage<String> s =
        CompletableFuture.completedStage("ready");

CompletionStage<String> upper =
        s.thenApply(String::toUpperCase);
~~~

Không yêu cầu executor. Bởi vì upstream đã complete, callback thenApply **có thể chạy ngay trong thread đăng ký continuation**. Không suy ra mọi callback đều chạy ở thread khác.

### completedStage không đồng nghĩa completedFuture

Cả hai có cùng một **normal result** nếu cùng value, nhưng khác **bề mặt API**.

- completedStage: chỉ hứa **CompletionStage**, thích hợp công bố pipeline mà không cấp quyền complete/cancel trực tiếp.
- completedFuture: trả **CompletableFuture đầy đủ**, thuận tiện nếu caller cần join/get/isDone/cancel.
- Caller có thể gọi **CompletionStage.toCompletableFuture()** để nhận CompletableFuture dùng cho interop; với minimal stage, kết quả có thể là **một đối tượng CompletableFuture khác**.
- Không dùng cast tới implementation runtime của minimal stage, vì các method ngoài CompletionStage có thể không được hỗ trợ và gây UnsupportedOperationException.

### Null là value hợp lệ khi thành công

**completedStage(null)** và **completedFuture(null)** biểu diễn normal completion với value null. Điều này khác hoàn toàn **failedStage(ex)**. Nếu downstream gọi value.toString() mà value là null, chính callback sẽ tạo ra lỗi mới.

Nên dùng **Optional<T>** hoặc domain result rõ nghĩa nếu không muốn null trở thành một trạng thái hợp lệ khó kiểm soát.

## 5. Ví dụ 1: completedStage và completedFuture

Tệp **CompletedStageDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class CompletedStageDemo {
    public static void main(String[] args) {
        CompletionStage<String> stage =
                CompletableFuture.completedStage("ready");
        CompletableFuture<String> future =
                CompletableFuture.completedFuture("ready");

        CompletionStage<String> upper =
                stage.thenApply(String::toUpperCase);

        CompletionStage<String> nullable =
                CompletableFuture.completedStage(null);

        System.out.println("stage = "
                + upper.toCompletableFuture().join());
        System.out.println("future = " + future.join());
        System.out.println("null normal = "
                + (nullable.toCompletableFuture().join() == null));
        System.out.println("done = " + future.isDone());
    }
}
~~~

~~~bash
javac -encoding UTF-8 CompletedStageDemo.java
java CompletedStageDemo
~~~

Stdout:

~~~text
stage = READY
future = ready
null normal = true
done = true
~~~

**Giải thích:**

1. stage và future đều hoàn tất trước khi main đăng ký continuation.
2. thenApply biến giá trị "ready" thành "READY".
3. toCompletableFuture().join() cho phép lấy result từ CompletionStage.
4. Normal completion có thể có giá trị null; biểu thức so sánh null trả true.
5. isDone() true ở đây vì completedFuture đã hoàn tất bình thường.

Đừng dùng ví dụ này để chứng minh một callback không-Async luôn chạy inline. API cho phép một số lựa chọn execution context; muốn đảm bảo một executor cụ thể, hãy chỉ định nó ở overload Async.

## 6. failedFuture(Throwable): Future đầy đủ đã lỗi

**CompletableFuture.failedFuture(ex)** tạo CompletableFuture<U> đã **complete exceptionally** với Throwable ex được cung cấp. Nó **không throw chính ex vào caller lúc tạo factory**.

~~~java
CompletableFuture<Integer> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("not available")
        );
~~~

Trạng thái đáng nhớ:

| Query hoặc thao tác | Kết quả khi failedFuture(IllegalStateException) |
| --- | --- |
| **isDone()** | true |
| **isCompletedExceptionally()** | true |
| **isCancelled()** | false |
| **get()** | ném ExecutionException chứa root cause |
| **join()** | ném CompletionException chứa root cause |
| **thenApply(fn)** | không gọi fn; dependent stage cũng exceptional |
| **exceptionally(fn)** | gọi fn để tạo giá trị hồi phục |

**Lỗi đã có sẵn** khác với task chưa hoàn thành rồi ném lỗi sau. Một Future đã failed không có background job do chính failedFuture factory tạo ra.

### Exception trong factory không đồng nghĩa throw trực tiếp

~~~java
CompletableFuture<String> result =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("bad request")
        );
~~~

Method vẫn **trả result**. Muốn quan sát exception, caller dùng get/join/exceptionally/handle. Điều này khác với code **throw new IllegalArgumentException(...)** làm method thoát theo luồng stack thông thường.

Cách biểu diễn bằng exceptional completion đặc biệt hữu ích nếu API hứa **luôn trả Future/Stage** cho cả validation fail và các lỗi hoàn tất về sau.

## 7. Ví dụ 2: quan sát lỗi qua get và join

Tệp **FailedFutureGetJoinDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class FailedFutureGetJoinDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CompletableFuture<Integer> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("failed")
                );

        System.out.println("done = " + failed.isDone());
        System.out.println("exceptional = "
                + failed.isCompletedExceptionally());
        System.out.println("cancelled = " + failed.isCancelled());

        try {
            failed.get();
        } catch (ExecutionException ex) {
            System.out.println("get wrapper = "
                    + ex.getClass().getSimpleName());
            System.out.println("get cause = "
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            failed.join();
        } catch (CompletionException ex) {
            System.out.println("join wrapper = "
                    + ex.getClass().getSimpleName());
            System.out.println("join cause = "
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FailedFutureGetJoinDemo.java
java FailedFutureGetJoinDemo
~~~

Stdout:

~~~text
done = true
exceptional = true
cancelled = false
get wrapper = ExecutionException
get cause = IllegalStateException
join wrapper = CompletionException
join cause = IllegalStateException
~~~

**Lưu ý về wrappers:** với ví dụ này ex được cung cấp trực tiếp là IllegalStateException, nên get() và join() dùng các wrapper trên. Trong pipeline phức tạp có thể đã có CompletionException từ bước trước; không viết logic giả định mọi lỗi luôn có đúng một lớp bọc.

**Future.get()** còn có checked InterruptedException khi caller bị ngắt; overload get(timeout, unit) có thể ném TimeoutException nếu chưa done. Nhưng failedFuture đã done ngay, nên đoạn này không chờ một worker.

## 8. failedStage(Throwable): lỗi có sẵn theo kiểu CompletionStage

**CompletableFuture.failedStage(ex)** trả CompletionStage<U> đã hoàn tất đặc biệt.

~~~java
CompletionStage<String> stage =
        CompletableFuture.failedStage(
                new IllegalArgumentException("invalid")
        );
~~~

Đặc trưng:

- Chỉ public **CompletionStage API** được hứa.
- **thenApply** và **thenCompose** không chạy lambda thành công vì không có result thành công.
- **exceptionally** có thể tạo fallback.
- **handle** có thể xem cả result và error.
- **whenComplete** có thể quan sát lỗi nhưng không mặc nhiên làm stage trở thành normal.
- **toCompletableFuture()** chuyển sang một CompletableFuture đầy đủ để caller gọi get/join nếu cần.
- Không cast tùy tiện stage sang CompletableFuture rồi gọi complete/cancel/join trên một implementation minimal, vì những method không thuộc CompletionStage có thể không được hỗ trợ.

**Vì sao cần minimal stage?** Nó là cách giảm quyền điều khiển completion qua public API. Điều này hữu ích khi method chỉ muốn trao **khả năng compose** mà không hứa cho consumer quyền mutate trạng thái promise nội bộ.

### Khi phải chọn giữa hai factory failed

- Method khai báo **CompletableFuture<T>**: chọn **failedFuture(ex)** nếu đã có lỗi.
- Method khai báo **CompletionStage<T>**: **failedStage(ex)** diễn đạt rõ chủ đích composition-only.
- Không khác nhau ở “mức độ nghiêm trọng lỗi” hoặc “thời điểm exception xuất hiện”: cả hai đã exceptional trước khi trả.

## 9. Continuation thành công và lỗi

| Phép nối | Nếu upstream normal | Nếu upstream exceptional |
| --- | --- | --- |
| **thenApply(fn)** | gọi fn với value, tạo result | bỏ qua fn, truyền failure |
| **thenCompose(fn)** | gọi fn trả CompletionStage rồi flatten | bỏ qua fn, truyền failure |
| **thenAccept(consumer)** | gọi consumer trên value | bỏ qua consumer |
| **thenRun(runnable)** | gọi runnable | bỏ qua runnable |
| **exceptionally(fn)** | giữ normal result | gọi fn để tạo fallback |
| **handle(fn)** | gọi fn với error null | gọi fn với error khác null |
| **whenComplete(action)** | quan sát success, thông thường giữ outcome | quan sát failure, thông thường giữ outcome |
| **thenApplyAsync(fn, executor)** | lên lịch fn qua executor cung cấp | không chạy success-only fn vì upstream failed |

**Không nhầm whenComplete và handle**: whenComplete chủ yếu quan sát, handle có thể biến result/error thành giá trị mới. Nếu callback lại throw exception, downstream có thể exceptional; việc gắn một handler không đảm bảo không bao giờ lỗi.

Một pipeline minh họa:

~~~text
failedStage(IllegalArgumentException)
   |
   +-- thenApply(parse) -----------> parse không được gọi
   |                                      |
   |                                failed downstream
   |
   +-- exceptionally(fallback) ----> normal result
   |
   +-- handle(result, error) ------> callback trả kết quả tùy error
   |
   +-- whenComplete(log) ----------> log được gọi, lỗi không tự recover
~~~

**Exceptionally nhận Throwable**, nhưng nó có thể là wrapper theo cách bước trước hoàn tất. Đừng unconditionally cast sang domain exception mà không kiểm tra kiểu và cause.

## 10. Ví dụ 3: thenApply bị bỏ qua và exceptionally recovery

Tệp **FailedStageRecoveryDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.atomic.AtomicBoolean;

public class FailedStageRecoveryDemo {
    public static void main(String[] args) {
        AtomicBoolean mapped = new AtomicBoolean();

        CompletionStage<String> failed =
                CompletableFuture.failedStage(
                        new IllegalArgumentException("bad")
                );

        CompletionStage<String> successOnly =
                failed.thenApply(value -> {
                    mapped.set(true);
                    return value.toUpperCase();
                });

        CompletionStage<String> recovered =
                successOnly.exceptionally(error -> "fallback");

        CompletionStage<String> handled =
                failed.handle((value, error) ->
                        error == null ? value : "handled"
                );

        System.out.println("thenApply called = " + mapped.get());
        System.out.println("recovered = "
                + recovered.toCompletableFuture().join());
        System.out.println("handled = "
                + handled.toCompletableFuture().join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FailedStageRecoveryDemo.java
java FailedStageRecoveryDemo
~~~

Stdout:

~~~text
thenApply called = false
recovered = fallback
handled = handled
~~~

Trong ví dụ, **upstream failed trước khi thenApply được đăng ký**. Không có value thành công nên thenApply bị skip. Sau đó **exceptionally** đổi exceptional completion thành normal result "fallback". **handle** đọc error và trả "handled".

Nếu một callback trong exceptionally hoặc handle cũng throw, chính dependent stage có thể lại failed. Recovery cần được kiểm thử, không phải phép bảo đảm tự động.

## 11. Ví dụ 4: whenComplete là quan sát, handle là recovery

Tệp **WhenCompleteDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.atomic.AtomicBoolean;

public class WhenCompleteDemo {
    public static void main(String[] args) {
        AtomicBoolean seenError = new AtomicBoolean();

        CompletionStage<Integer> bad =
                CompletableFuture.failedStage(
                        new IllegalStateException("unavailable")
                );

        CompletionStage<Integer> observed =
                bad.whenComplete((value, error) ->
                        seenError.set(error != null)
                );

        boolean stillFailed = false;
        try {
            observed.toCompletableFuture().join();
        } catch (CompletionException ex) {
            stillFailed = true;
        }

        CompletionStage<Integer> recovered =
                bad.handle((value, error) ->
                        error == null ? value : 42
                );

        System.out.println("error observed = " + seenError.get());
        System.out.println("still failed = " + stillFailed);
        System.out.println("recovered = "
                + recovered.toCompletableFuture().join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 WhenCompleteDemo.java
java WhenCompleteDemo
~~~

Stdout:

~~~text
error observed = true
still failed = true
recovered = 42
~~~

**Vì sao đúng?** Callback whenComplete ghi nhận lỗi nhưng không có giá trị fallback. Nhánh observed tiếp tục exceptional. Ngược lại, handle chủ động trả Integer 42, nên nhánh recovered là normal.

Một callback telemetry không nên thực hiện blocking I/O nặng hoặc tùy tiện throw exception vì có thể tạo thêm lỗi trong chuỗi và làm khó quan sát failure gốc.

## 12. thenCompose để nối một stage đã có

**thenApply** chuyển T thành U. **thenCompose** chuyển T thành CompletionStage<U> rồi **flatten** thành CompletionStage<U> cho downstream.

~~~java
// Minh họa một pipeline:
CompletionStage<Integer> value =
        CompletableFuture.completedStage(20)
            .thenApply(n -> n + 1)
            .thenCompose(n ->
                    CompletableFuture.completedStage(n * 2)
            );
~~~

Stage kết quả có Integer 42, không phải CompletionStage lồng trong CompletionStage. Không cần thread mới, vì cả hai bước ở đây có result sẵn.

### Ví dụ 5: composition không tạo task giả

Tệp **StageCompositionDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class StageCompositionDemo {
    public static void main(String[] args) {
        CompletionStage<Integer> value =
                CompletableFuture.completedStage(20)
                    .thenApply(n -> n + 1)
                    .thenCompose(n ->
                            CompletableFuture.completedStage(n * 2)
                    );

        System.out.println("value = "
                + value.toCompletableFuture().join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StageCompositionDemo.java
java StageCompositionDemo
~~~

Stdout:

~~~text
value = 42
~~~

**Điểm chính:** một async-style API **được phép hoàn tất đồng bộ** trong những trường hợp đã biết kết quả. Không nên tạo supplyAsync chỉ để đáp ứng hình thức.

Nếu downstream cần I/O thật, thenCompose có thể trả một stage của thao tác I/O. Lúc ấy kết quả có thể đến sau; cách viết chain không cần đổi.

## 13. callback chạy ở thread nào?

Một sai lầm phổ biến: **thenApply** trên completedStage luôn chạy tại một worker background. Thực tế, non-Async dependent actions có thể được thực thi bởi thread hoàn tất stage, thread đăng ký continuation hoặc một thread được runtime cho phép theo hợp đồng.

Vì upstream đã complete trước lời đăng ký, **thenApply có thể chạy ngay trong caller**. Nếu callback nặng và blocking, caller có thể bị giữ trong chính lời gọi thenApply.

**thenApplyAsync** yêu cầu scheduling bất đồng bộ, có thể dùng default async execution facility của CompletableFuture hoặc executor do caller truyền.

**Không đồng nghĩa Async = tạo thread mới:** executor có thể dùng pool worker được tái sử dụng.

### Ví dụ 6: truyền executor tường minh

Tệp **ExplicitExecutorDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExplicitExecutorDemo {
    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        Thread caller = Thread.currentThread();

        try {
            CompletionStage<Boolean> value =
                    CompletableFuture.completedStage("ready")
                        .thenApplyAsync(
                            text -> Thread.currentThread() != caller,
                            executor
                        );

            System.out.println("different thread = "
                    + value.toCompletableFuture().join());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExplicitExecutorDemo.java
java ExplicitExecutorDemo
~~~

Stdout:

~~~text
different thread = true
~~~

Callback được chạy trên worker do executor quản lý, không phải main. Ví dụ kiểm tra **Thread object identity**, không dựa vào tên thread ngẫu nhiên.

Với ứng dụng thật, executor cũng có **queue, saturation, rejection, shutdown, thread factory** và giới hạn tài nguyên. Nếu executor không nhận được callback do đóng hoặc quá tải, downstream có thể thất bại. Không nhầm việc upstream completedStage thành công với việc **mọi dependent task trong tương lai chắc chắn chạy được**.

## 14. Factory lỗi trong API public

Giả sử một method phải trả CompletionStage<Integer> dù input có thể sai:

~~~java
// Mảnh minh họa; method parseAsync nằm trong một class.
CompletionStage<Integer> parseAsync(String input) {
    if (input == null) {
        return CompletableFuture.failedStage(
                new IllegalArgumentException("missing input")
        );
    }
    return CompletableFuture.completedStage(
            Integer.parseInt(input)
    );
}
~~~

**Mảnh này chưa xử lý NumberFormatException** từ parseInt: nó có thể throw **trực tiếp** trước khi trả CompletionStage. Nếu API hứa **mọi lỗi validation đều xuất hiện dưới dạng exceptional completion**, hãy catch lỗi parse rồi trả failedStage.

### Ví dụ 7: luôn trả một stage cho lỗi validation

Tệp **ValidationStageDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class ValidationStageDemo {
    static CompletionStage<Integer> parsePositive(String input) {
        if (input == null) {
            return CompletableFuture.failedStage(
                    new IllegalArgumentException("missing")
            );
        }

        try {
            int value = Integer.parseInt(input);
            if (value <= 0) {
                return CompletableFuture.failedStage(
                        new IllegalArgumentException("not positive")
                );
            }
            return CompletableFuture.completedStage(value);
        } catch (NumberFormatException ex) {
            return CompletableFuture.failedStage(ex);
        }
    }

    public static void main(String[] args) {
        CompletionStage<String> valid =
                parsePositive("21")
                    .thenApply(n -> "double=" + (n * 2));

        CompletionStage<String> invalid =
                parsePositive("invalid")
                    .thenApply(n -> "double=" + (n * 2))
                    .exceptionally(error -> "rejected");

        System.out.println(valid.toCompletableFuture().join());
        System.out.println(invalid.toCompletableFuture().join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ValidationStageDemo.java
java ValidationStageDemo
~~~

Stdout:

~~~text
double=42
rejected
~~~

Validation sai được thể hiện bằng **failedStage**, không làm caller phải catch NumberFormatException quanh lời gọi parsePositive. Caller có thể gắn **exceptionally** để tạo fallback.

**Không biến mọi lỗi hệ thống thành lỗi input:** chọn domain exception, cause, retry và thông tin người dùng phù hợp.

## 15. Lỗi của một callback có thể tạo failed downstream

Một normal upstream vẫn có thể tạo failed downstream nếu callback throw:

~~~java
CompletionStage<Integer> stage =
        CompletableFuture.completedStage("not a number")
            .thenApply(Integer::parseInt);
~~~

Ở đây upstream đã normal với String; **Integer.parseInt** throw NumberFormatException khi callback chạy, khiến stage kết quả exceptional.

Tương tự:

~~~java
CompletableFuture.completedStage(null)
        .thenApply(String::length);
~~~

Nếu không kiểm tra null, downstream có thể failed với NullPointerException. Đây là **lỗi của code callback**, không phải lỗi của completedStage(null) factory.

### Phân loại exception

- **Input validation error:** có thể failedStage/failedFuture từ đầu.
- **Error trong callback:** downstream mới exceptional.
- **Cancellation:** trạng thái đặc biệt của Future, không nhất thiết cùng semantics với lỗi nghiệp vụ.
- **Timeout chờ kết quả:** caller hết deadline, nhưng computation có thể tiếp tục.
- **Lỗi từ service bên ngoài:** cần cause, policy retry/idempotency, không tự được chữa bởi factory.

**Đừng bắt mọi Throwable rồi trả "OK"** nếu caller cần phân biệt lỗi dữ liệu với lỗi lập trình hoặc lỗi infrastructure.

## 16. exceptionallyCompose: fallback cũng là một stage

**exceptionally(fn)** cho phép tạo **giá trị bình thường** từ lỗi. Nhưng đôi khi fallback lại cần gọi một API trả CompletionStage. Trong Java 17 có **exceptionallyCompose**, cho phép callback trả **CompletionStage<T>** rồi flatten.

~~~java
// Mảnh minh họa cho một CompletionStage<String> source.
CompletionStage<String> recovered =
        source.exceptionallyCompose(error ->
                CompletableFuture.completedStage("backup")
        );
~~~

**thenCompose** chạy trên nhánh thành công; **exceptionallyCompose** chạy trên nhánh lỗi. Cả hai cho phép nối stage mà không tạo CompletionStage lồng nhau cho caller.

### Ví dụ 8: exceptionallyCompose phục hồi từ failedStage

Tệp **ExceptionallyComposeDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class ExceptionallyComposeDemo {
    public static void main(String[] args) {
        CompletionStage<String> failed =
                CompletableFuture.failedStage(
                        new IllegalStateException("primary failed")
                );

        CompletionStage<String> recovered =
                failed.exceptionallyCompose(error ->
                        CompletableFuture.completedStage("backup")
                );

        System.out.println("value = "
                + recovered.toCompletableFuture().join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExceptionallyComposeDemo.java
java ExceptionallyComposeDemo
~~~

Stdout:

~~~text
value = backup
~~~

Lỗi primary được thay bằng result backup. Nếu backup cũng failed, recovered vẫn exceptional. **Không có retry vô hạn tự động**: gọi join lại trên cùng stage không tạo lại một request.

Một cơ chế retry thực sự phải tạo một attempt mới, có giới hạn lượt, deadline, backoff và idempotency cho side effect.

## 17. Mutable value trong completedStage không tự thành immutable

Một factory đã hoàn tất **giữ reference tới value**; nó **không deep-copy** mọi object result.

~~~java
StringBuilder mutable = new StringBuilder("A");
CompletionStage<StringBuilder> stage =
        CompletableFuture.completedStage(mutable);
mutable.append("B");
~~~

Đọc stage về sau nhận reference cùng StringBuilder chứa "AB". Nếu thread khác sửa cùng StringBuilder đồng thời, không có bảo đảm thread safety chỉ vì object được publish qua CompletableFuture.

### Ví dụ 9: kết quả đã hoàn tất vẫn là cùng object

Tệp **MutableCompletedResultDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class MutableCompletedResultDemo {
    public static void main(String[] args) {
        StringBuilder original = new StringBuilder("A");

        CompletionStage<StringBuilder> stage =
                CompletableFuture.completedStage(original);

        original.append("B");

        StringBuilder returned =
                stage.toCompletableFuture().join();

        System.out.println("same object = " + (returned == original));
        System.out.println("value = " + returned);
    }
}
~~~

~~~bash
javac -encoding UTF-8 MutableCompletedResultDemo.java
java MutableCompletedResultDemo
~~~

Stdout:

~~~text
same object = true
value = AB
~~~

Ví dụ chỉ thực hiện trên main để kết quả xác định; nó **không chứng minh StringBuilder an toàn khi nhiều thread đồng thời sửa**.

Khi cung cấp result cho nhiều continuation, cân nhắc **immutable record**, immutable collection, defensive copy hoặc ownership được thiết kế rõ. **Final field** chứa reference tới mutable object không tự biến object đó thành immutable.

## 18. Null Throwable không phải một failed completion hợp lệ

**failedFuture(exception)** và **failedStage(exception)** yêu cầu đối số Throwable không null. Việc truyền null không tạo “lỗi trống”, mà gây lỗi sử dụng API.

Ngược lại, **completedFuture(null)** hoặc **completedStage(null)** là normal completion với giá trị null.

### Ví dụ 10: so sánh null result và null exception

Tệp **NullFactoryDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class NullFactoryDemo {
    public static void main(String[] args) {
        boolean failedFutureRejected = false;
        boolean failedStageRejected = false;

        try {
            CompletableFuture.<String>failedFuture(null);
        } catch (NullPointerException ex) {
            failedFutureRejected = true;
        }

        try {
            CompletableFuture.<String>failedStage(null);
        } catch (NullPointerException ex) {
            failedStageRejected = true;
        }

        System.out.println("failedFuture null rejected = "
                + failedFutureRejected);
        System.out.println("failedStage null rejected = "
                + failedStageRejected);
        System.out.println("completed null = "
                + (CompletableFuture.completedStage(null)
                    .toCompletableFuture().join() == null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullFactoryDemo.java
java NullFactoryDemo
~~~

Stdout:

~~~text
failedFuture null rejected = true
failedStage null rejected = true
completed null = true
~~~

**Cẩn thận về generic inference:** Khi khai báo kiểu result rõ ràng, compiler có thông tin kiểu từ assignment hoặc explicit type parameter. Không dùng null như một tín hiệu mà API chưa định nghĩa vì dễ làm callback dereference null.

## 19. Cancellation không giống failedFuture với lỗi thông thường

**Cancellation** là một trạng thái Future. Nếu cancel một CompletableFuture **chưa hoàn tất**, get/join có thể ném CancellationException và isCancelled() true. Trong khi:

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("invalid")
        );
~~~

...thì failed.isCancelled() false. Nó đã hoàn tất exceptional, không phải trạng thái hủy.

**Lời gọi cancel sau khi Future đã complete/failed** không thể sửa một completion đã quyết định. Các completed/failed factory không tạo tác vụ background để cancel(true) gửi interrupt.

### failedFuture(Throwable) có thể nhận CancellationException làm cause?

API nhận Throwable; nhưng **không dùng cách thủ công bọc CancellationException như một workflow thay cho giao thức cancel** khi business cần phân biệt FAILED và CANCELLED. Với những path khác nhau của CompletableFuture có thể có các hiệu ứng trạng thái đặc biệt, và điều quan trọng là **contract trạng thái** của ứng dụng được xác định rõ.

### Timeout không làm failedFuture thành success

Future.get(timeout) trên một Future pending có thể ném TimeoutException. Với failedFuture đã hoàn tất, việc chờ đọc ngay failure; timeout không tự retry, không sửa result và không hủy side effect.

## 20. getNow không phải phương thức recover lỗi

Trên CompletableFuture:

- **getNow(defaultValue)** trả result nếu đã hoàn tất bình thường.
- Nếu chưa complete, trả giá trị default.
- Nếu đã complete exceptionally, **ném completion exception**; không phải fallback chuyên dùng cho lỗi.

Do đó, không viết:

~~~java
// Ý định sai: tưởng luôn nhận giá trị mặc định nếu có lỗi.
String value = failed.getNow("default");
~~~

Trong mảnh minh họa này, failed là CompletableFuture<String> exceptional. getNow có thể ném exception thay vì trả "default".

Muốn fallback cho lỗi, dùng **exceptionally**, **handle** hoặc các cách xử lý exception tường minh.

## 21. toCompletableFuture và khả năng kiểm soát trạng thái

**CompletionStage.toCompletableFuture()** giúp chuyển từ interface pipeline sang một CompletableFuture đầy đủ phục vụ interop hoặc các method Future.

Nhưng phải phân biệt:

- Minimal stages của completedStage/failedStage có thể được đại diện bằng các object chỉ hỗ trợ CompletionStage operations.
- toCompletableFuture tạo/cho một CompletableFuture với completion tương ứng; **không yêu cầu luôn là đúng một object identity**.
- Nếu API trả CompletionStage nhằm giấu quyền complete/cancel của nguồn, caller không được suy rằng việc complete/cancel một adapter sẽ thay đổi upstream ban đầu.
- Với một ordinary CompletableFuture gốc, cách toCompletableFuture triển khai có thể trả chính object đó. Vì vậy không đưa ra một khẳng định identity cho **mọi** CompletionStage implementation.

**Hợp đồng đúng đắn nên nói về kết quả và quy tắc phụ thuộc**, không dựa vào class implementation của minimal stage.

## 22. Một API có cache hit và đường lỗi ngay lập tức

Giả sử method trả CompletionStage<User>. Một thiết kế thường là:

~~~java
// Mảnh minh họa; User, cache, fetchAsync do ứng dụng khai báo.
CompletionStage<User> loadUser(String id) {
    if (id == null || id.isBlank()) {
        return CompletableFuture.failedStage(
                new IllegalArgumentException("id required")
        );
    }

    User inCache = cache.get(id);
    if (inCache != null) {
        return CompletableFuture.completedStage(inCache);
    }

    return fetchAsync(id);
}
~~~

Cách này có ba đường:

1. **Validation fail:** trả failed stage, không ném domain error vào caller ngay.
2. **Cache hit:** trả completed stage, không tạo một task giả.
3. **Cache miss:** trả stage của I/O thực tế, có thể pending.

Caller xử lý đồng nhất:

~~~java
CompletionStage<String> response =
        loadUser(id)
            .thenApply(User::displayName)
            .exceptionally(error -> "unavailable");
~~~

Đây là mảnh code minh họa, không phải file độc lập. Nếu cache chứa object User mutable bị thread khác sửa, **completedStage không khóa User**; safe publication và ownership vẫn cần được xem xét riêng.

### Không biến mọi lỗi thành cùng một giá trị

Một giá trị fallback "unavailable" có thể hợp lý cho UI, nhưng không nên dùng cho việc cần phân biệt **invalid input**, **not found**, **timeout**, **unauthorized** hoặc **internal failure**. Recovery strategy phải phù hợp domain.

## 23. So sánh với new CompletableFuture và complete thủ công

Có thể tạo pending Future:

~~~java
CompletableFuture<Integer> future = new CompletableFuture<>();
future.complete(42);
~~~

Nếu kết quả vốn đã có, **completedFuture(42)** ngắn gọn và rõ hơn.

Tương tự:

~~~java
CompletableFuture<Integer> future = new CompletableFuture<>();
future.completeExceptionally(
        new IllegalStateException("failure")
);
~~~

Khi lỗi đã biết, **failedFuture** biểu diễn ý định rõ ràng.

### Khi nào pending CompletableFuture mới cần thiết?

Nếu một sự kiện **sẽ đến trong tương lai** và callback sẽ complete promise, việc tạo pending CompletableFuture có ý nghĩa. Khi đó cần:

- Định nghĩa ai là **owner của complete/completeExceptionally**.
- Tránh nhánh exception/timeout bỏ quên completion làm caller chờ mãi.
- Có deadline/cancel/cleanup hợp lý.
- Tránh complete nhiều lần với kết quả mâu thuẫn, theo hợp đồng chỉ một completion thắng.
- Không dùng completedStage để giả vờ chờ I/O mà thực tế chưa có kết quả.

**Completed/failed factories giải quyết những ca kết quả đã biết**, không phải thay toàn bộ cơ chế asynchronous computation.

## 24. Các lỗi phổ biến

| Nhầm lẫn | Sửa lại |
| --- | --- |
| completedStage tạo Thread mới | Không; tạo stage đã complete |
| failedFuture ném exception ngay tại lời gọi | Thường trả Future exceptional |
| completedStage và completedFuture khác result | Cùng normal result, khác public return type |
| failedStage và failedFuture khác thời điểm lỗi | Cùng exceptional ngay, khác API surface |
| completedStage(null) là failed stage | null có thể là normal result |
| failedStage(null) là failure không có cause | Factory lỗi yêu cầu Throwable không null |
| CompletionStage tối giản chắc chắn cast được rồi complete | Không dựa vào implementation runtime |
| toCompletableFuture luôn trả cùng instance | Không bảo đảm với mọi stage |
| thenApply chạy dù upstream failed | Không; success-only callback bị skip |
| exceptionally luôn chạy | Chỉ gọi cho exceptional upstream |
| whenComplete làm lỗi thành success | Không mặc nhiên recover |
| handle chỉ chạy khi lỗi | Chạy cả normal và exceptional |
| thenCompose tạo stage hai tầng | Kết quả được flatten |
| thenApply của completedStage chắc chạy background | Có thể chạy ngay trên thread đăng ký |
| thenApplyAsync tạo thread mới mỗi lần | Executor có thể tái sử dụng worker |
| isDone=true nghĩa successful | Done gồm lỗi và hủy |
| get và join ném cùng wrapper | get dùng ExecutionException, join dùng CompletionException |
| getNow(default) che lỗi | Nếu đã exceptional, nó có thể ném lỗi |
| join lần nữa sẽ retry | Không, chỉ xem completion cố định |
| completedStage làm result immutable | Không, giữ reference |
| failedFuture tự log lỗi | Không thay hệ thống telemetry |
| Timeout tự cancel | Không; timeout chờ riêng với cancel |

## 25. Bảng quyết định chọn factory

| Nhu cầu API | Lựa chọn | Vì sao |
| --- | --- | --- |
| Stage đã thành công, chỉ expose composition | **completedStage(value)** | Trả CompletionStage tối giản |
| Stage đã lỗi, chỉ expose composition | **failedStage(ex)** | Thống nhất API kiểu CompletionStage |
| Future đã thành công, caller cần CompletableFuture | **completedFuture(value)** | Concrete Future đầy đủ |
| Future đã lỗi, caller cần CompletableFuture | **failedFuture(ex)** | Concrete Future exceptional |
| Computation thật sự pending | **new CompletableFuture** hoặc một API async khác | Cần owner/lifecycle để complete về sau |
| Callback muốn mapping thành result | **thenApply** | Chỉ đường thành công |
| Callback muốn stage khác | **thenCompose** | Flatten stage phụ thuộc |
| Fallback bằng một value | **exceptionally** | Recovery đường exceptional |
| Fallback bằng một stage khác | **exceptionallyCompose** | Flatten fallback stage |
| Cần đọc cả success/error | **handle** | Có thể tạo result mới |
| Chỉ telemetry/cleanup | **whenComplete** | Không mặc nhiên recover |

**Quan trọng hơn chọn factory:** phải xác định **kiểu public API**, quyền hoàn tất, exceptional workflow, executor context và tính đúng đắn của kết quả.

## 26. Bảo đảm về hiệu năng và scheduling

Vì factory trả stage đã complete:

- Không tạo một queued computation chỉ bởi việc gọi factory.
- Không tạo thread chỉ bởi việc gọi factory.
- Không cần đợi một timer hoặc external service để trạng thái complete.
- Nhưng **continuation Async** có thể lên lịch công việc lên executor riêng.
- **Continuation non-Async** có thể chạy ngay trong caller và làm caller bị block nếu callback chậm.
- Việc gắn rất nhiều dependent stages vẫn có chi phí allocation/processing.
- Một already-failed stage không có nghĩa downstream không thể làm việc: recovery callback vẫn được gọi.

**Không dùng completedStage như công cụ benchmark hiệu năng bất đồng bộ.** Nếu cần so sánh callback trên worker, chọn executor cụ thể và đo workload/queue/latency/GC với phương pháp phù hợp.

### Lỗi Async executor

Nếu dùng thenApplyAsync với executor đã shutdown hoặc quá tải, dependent stage có thể lỗi do không được lên lịch. Việc **upstream completedStage normal** không bảo đảm mọi dependent stage normal.

## 27. Java Memory Model và value ownership

Dùng CompletionStage không loại bỏ yêu cầu về **happens-before** và thread safety.

- Khi kết quả một stage được complete, các dependent actions có thể quan sát giá trị theo quan hệ đồng bộ hóa của Future/CompletableFuture.
- **Future.get()** có memory consistency effects tương ứng với thao tác của computation hoàn tất.
- Tuy nhiên, nếu value là object mutable và thread khác **tiếp tục sửa object sau complete**, việc đọc/sửa đồng thời cần lock/atomic/immutable ownership riêng.
- Các callback có thể chạy trên các thread khác nhau; ThreadLocal context không tự đi theo từng stage.
- Không đưa một List mutable cho nhiều callback cùng add/remove rồi nghĩ CompletionStage đã tuần tự hóa toàn bộ truy cập.

Một API an toàn thường trả **immutable snapshot** với các thành phần immutable hoặc chỉ định rõ caller nào được quyền mutate state.

## 28. Checklist khi review

**API và kiểu dữ liệu:**

- [ ] Có biết chắc method đang trả CompletionStage hay CompletableFuture?
- [ ] Dùng completedStage/failedStage khi chỉ muốn caller compose?
- [ ] Dùng completedFuture/failedFuture khi thật sự cần concrete CompletableFuture?
- [ ] Không cast minimal stage để gọi method ngoài CompletionStage?
- [ ] Không giả định toCompletableFuture trả cùng object?
- [ ] Có quy định null result và exception null?

**Pipeline:**

- [ ] thenApply/thenCompose có bị skip đúng khi upstream failed?
- [ ] Đã đặt exceptionally/handle tại chỗ cần recover?
- [ ] whenComplete không bị nhầm là method recovery?
- [ ] get/ join exception wrappers được xử lý đúng?
- [ ] Callback có thể tự throw và tạo failed downstream?
- [ ] Fallback có thể failed và có giới hạn retry?

**Concurrency và nghiệp vụ:**

- [ ] Không giả định callback non-Async chạy background?
- [ ] Executor trong Async callback còn sống và có capacity?
- [ ] Result immutable hoặc có ownership thread-safe?
- [ ] Không coi isDone là domain success?
- [ ] Không coi timeout là cancel hoặc rollback?
- [ ] Có telemetry/error classification cho exceptional completion?

## 29. Câu hỏi tự kiểm tra

**1. completedStage(value) trả kiểu gì?**  
CompletionStage<U> đã hoàn tất thành công, không có task mới được tạo bởi factory.

**2. failedFuture(ex) trả kiểu gì?**  
CompletableFuture<U> đã hoàn tất đặc biệt với exception; có get/join/status methods.

**3. failedStage(ex) khác failedFuture(ex) điều gì?**  
failedStage public API là CompletionStage tối giản; failedFuture là CompletableFuture đầy đủ. Cả hai đều đã failed ngay.

**4. completedStage(null) có lỗi không?**  
Không, null là một normal result được phép.

**5. failedStage(null) có nghĩa lỗi rỗng không?**  
Không. Factory yêu cầu Throwable không null và gây NullPointerException cho tham số không hợp lệ.

**6. Vì sao thenApply không chạy khi upstream failed?**  
Đó là success-only continuation. Nó không có normal value để biến đổi.

**7. Muốn fallback cho exceptional upstream bằng một String, dùng gì?**  
exceptionally hoặc handle theo contract.

**8. Muốn fallback bằng CompletionStage khác, dùng gì trong Java 17?**  
exceptionallyCompose hoặc composition recovery tương đương.

**9. whenComplete có phục hồi lỗi chỉ vì callback ghi log không?**  
Không; khi callback chạy bình thường, outcome exception vẫn được giữ.

**10. join và get khác nhau thế nào đối với lỗi thường?**  
join ném CompletionException unchecked; get ném ExecutionException checked và có thể InterruptedException.

**11. completedStage đảm bảo thenApply chạy trên thread riêng không?**  
Không. Non-Async continuation có thể chạy trên thread đăng ký.

**12. thenApplyAsync với executor có tạo thread mới cho mỗi callback không?**  
Không. Executor có thể dùng worker pool sẵn có và có chính sách từ chối.

**13. completedStage(StringBuilder) có tự deep-copy object không?**  
Không, giữ reference; StringBuilder mutable vẫn không thread-safe khi bị nhiều thread sửa.

**14. toCompletableFuture luôn trả same object instance không?**  
Không, tùy implementation; minimal stage có thể tạo một CompletableFuture mới.

**15. Một failedFuture có tự retry khi join nhiều lần không?**  
Không. Nó đã failed; join chỉ quan sát trạng thái cuối.

**16. Nếu API có cache hit hoặc validation fail sớm, cần tạo supplyAsync không?**  
Không bắt buộc; completedStage và failedStage giữ return type nhất quán mà không tạo task giả.

## 30. Kết luận

**completedStage()**, **failedFuture()** và **failedStage()** biểu diễn **kết quả đã biết** dưới dạng completion của Java concurrency:

- **completedStage(value):** normal completion, expose CompletionStage tối giản.
- **failedFuture(ex):** exceptional completion, expose CompletableFuture đầy đủ.
- **failedStage(ex):** exceptional completion, expose CompletionStage tối giản.
- **completedFuture(value):** normal completion, expose CompletableFuture đầy đủ.

Hãy nhớ **completion khác execution**, **CompletionStage khác concrete CompletableFuture**, và **normal khác exceptional**. Khi ghép pipeline, phân biệt **thenApply/thenCompose** cho thành công, **exceptionally/handle/exceptionallyCompose** cho recovery, **whenComplete** cho quan sát; xử lý get/join wrappers đúng và không quên thread safety của object result.

Một API bất đồng bộ tốt không cố tạo thread cho mọi đường: nếu đã có value thì trả completed stage, nếu đã có lỗi thì trả failed stage, còn khi thật sự có computation pending mới dùng cơ chế scheduling/lifecycle thích hợp.

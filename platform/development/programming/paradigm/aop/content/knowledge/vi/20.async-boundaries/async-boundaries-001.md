# Thời điểm trả kết quả đại diện so với thời điểm công việc hoàn tất trong AOP

## 1. Bài toán: phương thức kết thúc trước tác vụ

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP), aspect thường được dùng để ghi log, đo latency, theo dõi lỗi hoặc tạo trace quanh lời gọi phương thức. Nếu phương thức đồng bộ trả về giá trị sau khi xử lý xong, “lời gọi đã trả về” thường gần với “phần việc do phương thức cam kết đã hoàn tất”. Nhưng với **phương thức bất đồng bộ**, hai sự kiện này có thể cách nhau rất xa.

Xét chữ ký:

~~~java
CompletionStage<Report> generateReportAsync();
~~~

Phương thức có thể chỉ tạo/lên lịch tác vụ rồi trả về một `CompletionStage<Report>` ngay lập tức. Báo cáo vẫn đang được tạo trên executor hoặc hệ thống khác. Khi aspect thấy lời gọi trả về bình thường, nó chỉ biết rằng **đối tượng đại diện cho kết quả tương lai đã được trả về**; chưa thể tuyên bố báo cáo đã hoàn tất thành công.

Điểm cần nắm là: **method return** kết thúc đường gọi Java hiện tại; **work completion** được thông báo bởi hợp đồng của đối tượng đại diện hoặc bởi hệ thống thực thi công việc. Một aspect chỉ bao quanh method call không tự động bao quanh toàn bộ vòng đời của tác vụ được khởi chạy sau return.

Mục tiêu của bài học là xác định chính xác hai ranh giới, chọn chỗ ghi log/metric đúng ý nghĩa, xử lý cả lỗi đồng bộ và lỗi bất đồng bộ, đồng thời bảo toàn tính không chặn của API.

## 2. Dòng thời gian và các mốc sự kiện

~~~text
Caller                  Aspect/advice                 Target / worker
  | --- gọi phương thức ---> |                                |
  |                          | ---> gọi target --------------> |
  |                          |        lên lịch công việc       |
  |                          | <--- trả Future/Stage --------- |
  | <--- nhận handle -------- |                                |
  | tiếp tục làm việc khác    |                  công việc tiếp tục
  |                          |                  thành công / lỗi / hủy
  |                          | <--- tín hiệu hoàn tất --------- |
  |                          |       observer chạy             |
~~~

Có thể ký hiệu:

| Mốc | Điều xảy ra | Điều aspect có thể kết luận |
| --- | --- | --- |
| **T0** | Advice bắt đầu bao lời gọi | Lời gọi đang bắt đầu |
| **T1** | Phương thức đích trả đối tượng đại diện | Phương thức đích đã return bình thường |
| **T2** | Advice trả handle cho bên gọi | Bên gọi đã nhận giá trị trả về cuối cùng của lời gọi |
| **T3** | Tác vụ/handle phát trạng thái terminal | Công việc **theo hợp đồng handle** đã kết thúc thành công, thất bại hoặc hủy |
| **T4** | Completion observer được thực thi | Logic ghi nhận hoàn tất đã chạy; có thể trễ so với T3 |

Với tác vụ bất đồng bộ thông thường, T2 xảy ra trước T3. Tuy nhiên, **không có thứ tự tuyệt đối**: một stage có thể đã hoàn tất trước lúc được return, hoặc tác vụ có thể hoàn tất đúng lúc advice đang xử lý. Nếu đăng ký callback khi stage đã hoàn tất, callback có thể chạy ngay trên luồng đăng ký. Vì vậy không nên dựa vào giả định “log return luôn phải xuất hiện trước log completion”.

Khoảng thời gian T0→T2 đo chi phí lời gọi đến lúc trả handle. Khoảng T0→T3 biểu thị thời gian đến tín hiệu hoàn tất của công việc. Khoảng T3→T4 phản ánh thời gian trễ quan sát callback (nếu có). Đặt tên đúng cho ba khoảng thời gian này là điều kiện để metric không gây hiểu nhầm.

## 3. “Kết quả đại diện” khác “kết quả thật”

Với `T read()` đồng bộ, bên gọi nhận `T` khi phương thức return bình thường. Với `CompletionStage<T> readAsync()`, bên gọi nhận một *handle* để quan sát hoặc lấy kết quả về sau; `T` có thể chưa tồn tại.

| Hợp đồng API | Ý nghĩa của method return | Mốc xác nhận công việc xong |
| --- | --- | --- |
| `T method()` đồng bộ | Trả kết quả thật hoặc ném exception | Thường đã có kết quả tại return, trong phạm vi hợp đồng |
| `Future<T> method()` | Trả handle có thể chưa hoàn tất | Future done và outcome được xác định |
| `CompletionStage<T> method()` | Trả stage | Stage hoàn tất bình thường hoặc đặc biệt |
| `void method(Callback cb)` | Lời gọi đăng ký/khởi tạo đã kết thúc | Callback báo trạng thái, nếu hợp đồng có |
| `Flow.Publisher<T> stream()` | Trả đối tượng mô tả luồng | Theo vòng đời subscription, onComplete/onError/cancel |

Đối tượng đại diện không nhất thiết là công việc đang chạy: publisher kiểu cold có thể chưa bắt đầu làm việc cho đến khi có subscriber; một future có thể đã hoàn tất trước khi return.

Cần phân biệt **done** với **success**. `Future.isDone()` có thể là `true` khi tác vụ hoàn tất bình thường, bị hủy, hoặc kết thúc bằng ngoại lệ. Với `CompletableFuture`, `complete(value)` báo hoàn tất bình thường, `completeExceptionally(error)` báo kết thúc bất thường; `cancel(...)` gắn trạng thái hủy, được coi là một dạng hoàn tất đặc biệt. Ghi “success” chỉ dựa trên `isDone()` là sai.

Cũng phải hỏi rõ “công việc nào được đại diện?”. Nếu stage hoàn tất khi job **được đưa vào hàng đợi**, tín hiệu ấy chỉ xác nhận thao tác enqueue. Nó không chứng minh worker đã xử lý xong job. Một aspect không được suy trạng thái của công đoạn bên ngoài từ completion của handle chỉ đại diện cho công đoạn trước.

## 4. Advice AOP nhìn thấy đến đâu?

Các loại advice AOP thường gặp có ý nghĩa tại ranh giới lời gọi:

- **Before**: chạy trước lời gọi đích; chưa biết kết quả tương lai.
- **After returning**: chạy khi phương thức đích return bình thường. Nếu return `CompletionStage<T>`, đối tượng advice thấy là stage, chưa chắc `T` đã được tạo.
- **After throwing**: nhận exception thoát ra ngay trong lời gọi đích. Lỗi xuất hiện qua stage **sau return** không được ném qua stack đã kết thúc nên không tự đi qua nhánh này.
- **After/finally**: chạy tại lúc lời gọi kết thúc dù return hay throw; không mặc nhiên chờ hết các tác vụ nền.
- **Around**: bao lời gọi đích; có thể đo thời gian gọi, quan sát đối tượng trả về và đăng ký listener cho completion trước khi trả handle lại cho bên gọi.

Đặt log `method.returned` tại after returning là hợp lý; đặt `operation.succeeded` tại cùng thời điểm chỉ hợp lý nếu hợp đồng thật sự bảo đảm return nghĩa là tác vụ đã thành công. Với phương thức trả handle bất đồng bộ, điều này thường không đúng.

### Phân biệt exception ném ngay và stage thất bại

~~~java
CompletionStage<String> start(boolean valid) {
    if (!valid) {
        throw new IllegalArgumentException("Invalid argument");
    }
    return CompletableFuture.failedFuture(
            new IllegalStateException("Worker failed"));
}
~~~

Đây là **đoạn minh họa trong một phương thức**, chưa phải tệp Java độc lập; cần khai báo lớp và import. Gọi `start(false)` khiến chính method call ném `IllegalArgumentException`. Gọi `start(true)` lại **return bình thường** một stage đã ở trạng thái thất bại. Cả hai trường hợp đều có lỗi, nhưng lỗi đi qua hai kênh khác nhau: exception đồng bộ và exceptional completion. Một aspect muốn thống kê thất bại đầy đủ phải bao quát cả hai kênh.

Tác vụ có thể thất bại rất sớm, đúng lúc return, hoặc nhiều giây sau. Thời điểm lỗi xảy ra không thay đổi sự thật rằng một stage báo lỗi qua trạng thái hoàn tất của nó.

## 5. Ví dụ Java 17 hoàn chỉnh, đầu ra xác định

Ví dụ sau mô phỏng chức năng quan sát của around advice bằng một hàm Java bao quanh lời gọi. Mục đích là hiểu ranh giới AOP, không yêu cầu bộ máy proxy hoặc weaving bên ngoài. `CompletableFuture` được chủ động hoàn tất trong `main` để đầu ra luôn có thứ tự xác định.

Lưu dưới tên **`AsyncAspectBoundaryDemo.java`**:

~~~java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.function.Supplier;

public class AsyncAspectBoundaryDemo {
    static <T> CompletionStage<T> around(
            String operation,
            Supplier<? extends CompletionStage<T>> targetCall) {

        System.out.println("[enter] " + operation);
        CompletionStage<T> stage;

        try {
            stage = Objects.requireNonNull(targetCall.get(), "stage");
        } catch (RuntimeException | Error error) {
            System.out.println("[throw-now] " + error.getClass().getSimpleName());
            throw error;
        }

        System.out.println("[return-stage] " + operation);

        stage.whenComplete((value, error) -> {
            if (error == null) {
                System.out.println("[complete-ok] " + value);
            } else {
                System.out.println("[complete-error] "
                        + unwrap(error).getClass().getSimpleName());
            }
        });

        // Giữ nguyên stage mà target trả về.
        return stage;
    }

    static Throwable unwrap(Throwable error) {
        while (error instanceof CompletionException && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }

    public static void main(String[] args) {
        CompletableFuture<String> pending = new CompletableFuture<>();

        CompletionStage<String> stage = around("load", () -> {
            System.out.println("[method] return pending stage");
            return pending;
        });

        System.out.println("[caller] received, done="
                + stage.toCompletableFuture().isDone());

        pending.complete("DATA");
        System.out.println("[caller] result="
                + stage.toCompletableFuture().join());

        CompletableFuture<String> failed = new CompletableFuture<>();
        CompletionStage<String> errorStage = around("send", () -> failed);
        System.out.println("[caller] second stage received");

        failed.completeExceptionally(new IllegalStateException("boom"));

        try {
            errorStage.toCompletableFuture().join();
        } catch (CompletionException error) {
            System.out.println("[caller] caught="
                    + error.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac AsyncAspectBoundaryDemo.java
java AsyncAspectBoundaryDemo
~~~

Đầu ra:

~~~text
[enter] load
[method] return pending stage
[return-stage] load
[caller] received, done=false
[complete-ok] DATA
[caller] result=DATA
[enter] send
[return-stage] send
[caller] second stage received
[complete-error] IllegalStateException
[caller] caught=IllegalStateException
~~~

**Phân tích:**

1. Khi `around("load", ...)` bắt đầu, advice in `[enter]`. Target trả về `pending` còn chưa hoàn tất, nên advice in `[return-stage]` và bên gọi nhận stage với `isDone()==false`.
2. Chỉ khi `pending.complete("DATA")` chạy, future mới có kết quả cuối; listener `whenComplete` báo `[complete-ok] DATA`.
3. Với `send`, return bình thường diễn ra **trước** `failed.completeExceptionally(...)`. Completion listener thấy lỗi; lúc bên gọi `join()`, nó nhận `CompletionException` có cause là `IllegalStateException`.
4. `whenComplete` tự trả một dependent stage mới, nhưng ví dụ không trả dependent stage đó ra ngoài. Advice trả **stage gốc**, giảm nguy cơ vô tình thay ngữ nghĩa của handle chỉ vì mục đích logging.
5. Trong ví dụ completion do `main` gọi sau khi đã gắn listener, nên callback được kích hoạt ngay trong đường đi completion và output đã nêu đáng tin. Ở chương trình đa luồng, callback có thể chạy trên luồng hoàn tất hoặc lúc đăng ký nếu stage đã xong; không được lấy thứ tự output này làm bất biến chung.

Callback logging thực tế nên tự xử lý lỗi nội bộ và không làm việc nặng. Nếu callback ném exception, dependent stage do `whenComplete` trả về có thể thất bại dù stage gốc vẫn giữ outcome ban đầu.

## 6. Hai loại latency và cách đo

Nếu viết:

~~~java
long start = System.nanoTime();
CompletionStage<?> stage = targetCall.get();
long elapsed = System.nanoTime() - start;
~~~

thì `elapsed` chỉ là **thời gian target trả về stage**. Nó không đo việc xử lý dữ liệu kéo dài bao lâu. Nếu phương thức return sau 2 ms còn worker hoàn tất sau 4 giây, metric `2 ms` không được đặt tên “thời gian hoàn tất công việc”.

Định nghĩa một cách nhất quán:

| Chỉ số | Ranh giới | Ý nghĩa |
| --- | --- | --- |
| *Return/invocation latency* | T0→T2 (hoặc T0→T1, nói rõ lựa chọn) | Bao lâu để nhận handle |
| *Completion latency* | T0→T3 | Bao lâu để công việc được handle xác nhận kết thúc |
| *Observation delay* | T3→T4 | Bao lâu sau completion callback mới chạy |

Có thể quan sát gần đúng latency tới lúc nhận callback:

~~~java
long startedAt = System.nanoTime();
CompletionStage<Result> stage = targetCall.get();

stage.whenComplete((value, failure) -> {
    long observedLatencyNanos = System.nanoTime() - startedAt;
    recordLatency(observedLatencyNanos, failure);
});

return stage;
~~~

Đây là **mã minh họa**: `Result`, `targetCall`, `recordLatency` là thành phần do ứng dụng cung cấp. Đo trong callback cho ta thời gian đến **T4**, có thể chứa độ trễ scheduler sau T3. Muốn đo T3 chính xác phải chụp timestamp ngay tại nguồn phát completion hoặc lấy timestamp được contract cung cấp; `whenComplete` không tự mang timestamp T3.

`System.nanoTime()` thích hợp để đo khoảng thời gian vì là đồng hồ đơn điệu. `System.currentTimeMillis()` phản ánh thời gian lịch, có thể bị điều chỉnh. Nếu bài toán đòi hỏi phân tích sâu, cần chia nhỏ thêm thời gian **chờ queue**, **thực thi thật**, **retry/backoff** và **đợi downstream**; các mốc ấy phải được instrument ở nơi chúng thực sự xảy ra.

Nếu `targetCall.get()` ném exception ngay, cần đo outcome của nhánh đó riêng. Không tạo dữ liệu giả rằng một stage đã được trả khi thực tế lời gọi chưa có handle.

## 7. Theo dõi kết quả bất đồng bộ đúng abstraction

### 7.1. `CompletionStage<T>`

`whenComplete((value, failure) -> ...)` được dùng để quan sát cả completion bình thường và bất thường mà không chặn lời gọi. Nhưng cần hiểu sự khác nhau:

| Thao tác | Ý nghĩa | Rủi ro nếu dùng cho logging |
| --- | --- | --- |
| `whenComplete` | Quan sát outcome và trả dependent stage | Callback lỗi có thể ảnh hưởng dependent stage |
| `handle` | Biến outcome thành giá trị tiếp theo | Có thể đổi kết quả hoặc kênh lỗi |
| `exceptionally` | Xử lý lỗi và tạo giá trị phục hồi | Có thể biến thất bại thành thành công |
| `thenApply` | Biến đổi kết quả khi thành công | Không chạy ở mọi exceptional completion |
| `whenCompleteAsync` | Lập lịch callback trên executor | Có thêm scheduling delay/context propagation |

Nếu aspect chỉ làm telemetry, **tránh trả dependent stage khác khi không cần**; việc thay stage có thể đổi identity, semantics truyền lỗi/hủy và quan hệ dependent completion. Cũng không dùng `exceptionally` để “chỉ log” rồi trả giá trị mặc định, bởi điều đó sẽ đổi hành vi nghiệp vụ.

`whenComplete` không bảo đảm callback chạy trên một luồng cố định. Callback có thể chạy khi đã hoàn tất hoặc trên luồng đang kích hoạt completion. Tính nhẹ, an toàn đồng thời và xử lý lỗi của observer cần được thiết kế rõ.

### 7.2. `Future<T>` thuần

`java.util.concurrent.Future` hỗ trợ `get()`, `isDone()`, `isCancelled()` và `cancel(...)`, nhưng **giao diện này không có completion listener**. Nếu aspect chỉ nhận một `Future` từ return, nó có ba lựa chọn mang tính thiết kế:

- Theo dõi ngay tại task/executor nơi kết quả được tạo.
- Dùng abstraction hỗ trợ callback nếu API cho phép.
- Xây wrapper/bridge có hợp đồng rõ về success/failure/cancel/timeouts nếu thực sự cần.

Không gọi `get()`/`join()` ở trong advice chỉ để chờ log kết quả: lời gọi sẽ bị chặn, có thể gây nghẽn hoặc deadlock. Không vòng lặp bận `isDone()` vì tốn tài nguyên và vẫn phải lấy outcome để phân loại. `Future.get()` có thể ném `ExecutionException` nếu task lỗi, `CancellationException` khi bị hủy, hoặc `InterruptedException` khi luồng chờ bị ngắt — những trạng thái này khác nhau.

### 7.3. Callback-based và fire-and-forget

Với `void requestAsync(Callback cb)`, return của method thường chỉ là “đã đăng ký hoặc khởi chạy”. Completion phải đo ở callback thành công/thất bại theo hợp đồng. Nếu aspect bọc callback, wrapper phải chuyển tiếp đúng số lần, đúng thứ tự, giữ nguyên exception và semantics đồng thời.

Một phương thức `void startJob()` không trả handle, không có callback và không phát tín hiệu completion thì advice tại return **không thể xác định tin cậy** khi nào job nền kết thúc. Nếu yêu cầu theo dõi completion, phải instrument ở nguồn tác vụ hoặc nâng cấp hợp đồng API. Không tự suy “xong việc” từ “đã đưa vào executor”.

### 7.4. Publisher, subscription và terminal event

Với `Flow.Publisher<T>` hoặc publisher tương đương, return publisher có thể chỉ tạo mô tả một luồng dữ liệu. Một publisher kiểu *cold* chưa chạy tác vụ cho đến khi subscriber đăng ký. Vì thế cần phân biệt:

- **Return publisher:** đã có đối tượng đại diện.
- **Subscribe:** tạo/khởi động phiên tiêu thụ.
- **onNext:** phát một phần tử; chưa phải hoàn tất toàn stream.
- **onComplete:** luồng kết thúc bình thường.
- **onError:** luồng kết thúc với lỗi.
- **cancel:** subscriber yêu cầu hủy; không chứng minh mọi tác vụ phụ đã dừng tức thì.

Cùng một publisher có thể nhận nhiều subscription, mỗi subscription là một vòng đời riêng. Metric completion của luồng nên gắn theo **mỗi subscription**, không gom tất cả vào một return publisher. Aspect tự subscribe chỉ để quan sát có thể vô tình kích hoạt thêm một lượt xử lý, tiêu thụ dữ liệu hoặc thay đổi demand/backpressure; đây là thay đổi hành vi.

Một publisher có thể chạy lâu dài mà không phát terminal event. Vì vậy completion latency có thể không có giá trị cuối; chính sách timeout và hủy phải được định nghĩa rõ.

## 8. Bảo toàn semantics khi thêm aspect

**Quan sát** cần tách khỏi **điều khiển công việc**. Những hành động sau có thể làm API thay đổi:

1. Gọi `join()`/`get()` trước khi return: mất tính không chặn, giữ luồng bên gọi.
2. Đổi một handle thành wrapper hoặc dependent stage mà chưa kiểm tra: có thể ảnh hưởng danh tính handle, propagation của lỗi, hủy hoặc deadline.
3. Dùng `handle`/`exceptionally` để tạo kết quả thay thế: có thể nuốt lỗi.
4. Gọi `complete`, `completeExceptionally`, `orTimeout` hoặc `cancel` vào future mà aspect không sở hữu: thao túng trạng thái nghiệp vụ.
5. Tự subscribe publisher để tìm completion: kích hoạt thêm luồng xử lý.
6. Thực hiện logging/metric nặng ngay trong callback: có thể chiếm luồng phát tín hiệu hoàn tất.

Nếu thực sự cần tạo wrapper để instrument, phải kiểm tra đầy đủ success, failure, cancellation, timeout, callback timing, identity và đồng thời của API. Không mặc định hai đối tượng cùng triển khai interface thì có hành vi tương đương.

### Failure, cancellation và timeout

- **Success:** handle được xác nhận hoàn tất bình thường.
- **Failure:** handle được xác nhận hoàn tất do lỗi; đôi khi exception có lớp bao như `CompletionException`.
- **Cancellation:** handle hoặc subscription báo bị hủy/đã nhận hủy theo giao thức, nhưng side effect đã xảy ra không tự rollback.
- **Observation timeout:** hệ thống quan sát chưa nhận completion trong hạn chờ; không suy ra tác vụ thật đã dừng. Việc làm future timeout bằng API thay đổi trạng thái là hành động khác với chỉ ghi nhận quá hạn.

Các metric nên có outcome rõ ràng `success`, `failure`, `cancelled`, `timeout` và `unknown` nếu cần. Chỉ unwrap lớp exception có hợp đồng rõ, giữ cause cho trace và chẩn đoán.

### Truyền correlation context qua luồng

Advice ở T0/T2 thường chạy trên luồng bên gọi; callback hoàn tất có thể chạy trên worker khác hoặc ngay trên luồng đăng ký nếu stage đã done. `ThreadLocal` **không tự lan truyền** qua mọi executor và callback. Nếu muốn nối log cùng request, hãy chụp correlation ID tại thời điểm instrument và truyền theo cơ chế context an toàn của ứng dụng, tránh phụ thuộc vào thread name.

Listener có thể chạy đồng thời với code bên gọi; những cấu trúc lưu metric, trạng thái trace hoặc bản đồ correlation dùng chung phải được đồng bộ đúng. Không tin rằng callback luôn chạy sau dòng code nằm ngay sau return trong tất cả lịch thực thi.

### Điểm cắt AOP và phạm vi can thiệp

AOP có thể thực hiện qua decorator/proxy hoặc weaving ở các thời điểm khác nhau. Nếu chỉ intercept lời gọi đi qua wrapper, lời gọi nội bộ đi vòng qua wrapper sẽ không được bao. Weaving có thể mở rộng điểm cắt theo cấu hình, nhưng **join point method call/execution vẫn có ranh giới với work completion**. Muốn biết completion sau return, phải quan sát completion protocol hoặc điểm kết thúc tác vụ thực tế.

## 9. Chọn mốc quan sát theo tình huống

**Trường hợp A — kiểm tra input, tạo job rồi trả handle:** đo return latency để biết overhead khởi tạo. Theo dõi stage nếu muốn biết job xử lý xong.

**Trường hợp B — tạo báo cáo:** nếu stage chỉ hoàn tất khi báo cáo sẵn sàng, completion stage là mốc đúng để đo SLA tạo báo cáo; return latency là số liệu khác.

**Trường hợp C — enqueue job:** completion của stage enqueue chỉ xác nhận gửi hàng đợi, không xác nhận worker xử lý. Muốn đo worker latency cần tín hiệu từ worker hoặc hệ thống job.

**Trường hợp D — stream dữ liệu lazy:** return publisher chưa bắt đầu thực thi. Theo dõi subscribe→terminal event, và có thể đo first-item latency riêng khi cần.

**Trường hợp E — fire-and-forget không có tín hiệu:** chỉ ghi “đã gửi lệnh/đã lên lịch” tại return; muốn đo completed phải instrument tại nguồn tác vụ.

## 10. Các lỗi phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Log “success” tại *after returning* của stage | Chỉ có handle, chưa có outcome thật | Log return riêng, log completion riêng |
| Chỉ đếm lỗi ở *after throwing* | Lỗi phát sinh sau return không đi qua stack cũ | Quan sát exceptional completion |
| Gọi return latency là “thời gian xử lý” | Chỉ đo việc tạo/lấy handle | Tách invocation và completion latency |
| Gọi `join()` trong advice | Biến lời gọi không chặn thành chặn, có thể deadlock | Dùng completion listener |
| Coi `isDone()==true` là success | Done bao gồm failure/cancellation | Phân loại outcome đúng contract |
| Thay stage để thêm logging | Có thể ảnh hưởng identity và propagation | Trả stage gốc nếu hợp lý; wrapper khi được thiết kế |
| Dùng `exceptionally` để log rồi phục hồi mặc định | Vô tình nuốt lỗi | Telemetry tách khỏi biến đổi kết quả |
| Tự subscribe publisher | Có thể khởi chạy thêm tác vụ | Instrument theo subscription thực |
| Dựa vào `ThreadLocal` trên một thread | Callback đổi luồng làm mất context | Truyền correlation context |
| Coi timeout quan sát là task đã dừng | Tác vụ có thể tiếp tục | Phân biệt timeout, cancel và unknown |

## 11. Checklist thiết kế một aspect bất đồng bộ

1. Kiểu trả về là dữ liệu thật, `Future`, `CompletionStage`, callback, publisher hay `void`?
2. Hợp đồng nào xác định completion: return, future done, callback hay terminal event?
3. Completion ấy xác nhận **đúng công việc nào**: enqueue, xử lý thật, hay một chặng downstream?
4. Cần đo return latency hay completion latency; có phải tách queue wait và execution không?
5. Lỗi nào ném ngay, lỗi nào xuất hiện khi handle hoàn tất?
6. Có phân biệt success, failure, cancellation, timeout và trạng thái không rõ không?
7. Advice có chặn, đổi handle, nuốt lỗi, tự hủy hoặc tự subscribe không?
8. Callback có thể chạy ngay, chạy trên luồng khác, hay có nhiều subscription không?
9. Correlation context, metric storage và callback có an toàn đồng thời không?
10. Nếu API không có completion signal, đã thừa nhận giới hạn và chọn điểm instrument phù hợp chưa?

## 12. Kết luận

**Trả về đối tượng đại diện** là một sự kiện của lời gọi phương thức; **công việc hoàn tất** là một sự kiện của vòng đời bất đồng bộ theo đúng hợp đồng handle. Hai sự kiện có thể gần nhau, cách nhau lâu, hoặc completion xảy ra trước khi advice kịp trả handle. Trong AOP, cần đo và log đúng ranh giới, theo dõi lỗi bất đồng bộ ngoài lỗi ném trực tiếp, và giữ nguyên ngữ nghĩa không chặn của API.
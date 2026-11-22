# Timeout budget qua nhiều bước xử lý trong Java Concurrency

## 1. Bài toán: nhiều bước cùng tiêu một quỹ thời gian

Một tác vụ đồng thời thường không chỉ có một thao tác chờ. Ví dụ: lấy dữ liệu từ nguồn A → lấy dữ liệu từ nguồn B → chờ kết quả xử lý trên thread pool → ghi kết quả. Nếu mỗi bước được cấp timeout độc lập 400 ms, tổng thời gian có thể tiến gần 1.600 ms, chưa kể thời gian xếp hàng, retry và xử lý trung gian. Điều này vi phạm yêu cầu của tác vụ nếu người gọi chỉ chấp nhận tối đa 400 ms cho **toàn bộ** công việc.

**Timeout budget** là khoảng thời gian tối đa còn được phép dùng cho toàn bộ tác vụ. Khi nhiều bước dùng chung budget, thời gian đã tiêu ở bước trước phải trừ khỏi thời gian được phép chờ ở bước sau.

Giả sử budget toàn cục là 400 ms:

| Sự kiện | Thời gian đã tiêu | Thời gian còn lại |
| --- | ---: | ---: |
| Bắt đầu tác vụ | 0 ms | 400 ms |
| Hoàn tất bước A | 120 ms | 280 ms |
| Hoàn tất bước B | 270 ms | 130 ms |
| Bước C muốn chờ tối đa 180 ms | 270 ms | Chỉ được chờ tối đa 130 ms |
| Hết budget | 400 ms | 0 ms |

Các con số là minh họa; overhead lập lịch và hủy tác vụ có thể khiến thời gian kết thúc quan sát được vượt mốc một chút. Budget giúp giới hạn **thời gian cho phép chờ và khởi động công việc tiếp theo**, nhưng không tự động bảo đảm mọi thread hoặc thao tác I/O ngừng đúng tại mili giây cuối.

Phạm vi bài này là cơ chế concurrency của **Java nói chung**: thread, executor, Future, CompletionStage, lock, queue và các lời gọi chờ. Các cơ chế cấu hình timeout đặc thù Spring thuộc chương riêng.

## 2. Phân biệt ba khái niệm

- **Timeout của một thao tác**: thời gian tối đa dành cho riêng lời gọi đang chờ, chẳng hạn Future.get(timeout, unit) hoặc Lock.tryLock(timeout, unit).
- **Budget toàn tác vụ**: hạn mức tổng thời gian từ lúc tác vụ bắt đầu đến khi kết thúc. Bao gồm CPU, xếp hàng, chờ lock, I/O, backoff và các lần retry.
- **Deadline**: thời điểm hết budget trên đồng hồ dùng để đo thời gian trôi qua. Mỗi bước tính lại thời gian còn lại từ **cùng một deadline**, thay vì khởi tạo timeout đầy đủ mới.

Nguyên tắc bất biến là:

> remaining = max(0, budget - elapsed); timeout của bước kế tiếp không vượt remaining.

Nếu một bước có giới hạn riêng nhỏ hơn budget chung, dùng min(remaining, stepLimit). Giới hạn riêng chỉ **thu hẹp** thời gian cho bước đó; nó không cấp thêm thời gian cho tác vụ.

Cần tách hai vấn đề: (1) người gọi **ngừng chờ** sau khi hết hạn; (2) công việc đang chạy **thực sự dừng lại**. Future.get với timeout giải quyết (1); muốn (2) còn cần cơ chế hủy, interrupt hoặc timeout riêng của tài nguyên bên dưới.

## 3. Chọn đồng hồ: System.nanoTime thay vì đồng hồ lịch

Để đo elapsed time **trong cùng JVM**, dùng System.nanoTime(). Nó dành cho đo khoảng thời gian và không gắn với ngày giờ tuyệt đối. System.currentTimeMillis() là đồng hồ lịch; người dùng, NTP hoặc hệ điều hành có thể điều chỉnh nó, làm phép đo budget sai.

Ghi nhận:

- startNanos = System.nanoTime() ngay tại ranh giới bắt đầu tác vụ.
- elapsedNanos = System.nanoTime() - startNanos.
- remainingNanos = max(0, budgetNanos - elapsedNanos).

Không so sánh trực tiếp giá trị nanoTime với Unix timestamp. nanoTime có mốc tùy ý của JVM; chỉ **hiệu giữa hai lần đọc cùng nguồn đồng hồ** mang ý nghĩa. Phép trừ trên số nguyên long cho phép đếm qua điểm wrap trong phạm vi khoảng thời gian nhỏ hơn 2^63 nanosecond (xấp xỉ 292 năm), dài hơn mọi timeout thực tế hợp lý.

Ưu tiên đơn vị nanosecond cho tính toán nội bộ và chỉ chuyển sang đơn vị API yêu cầu khi gọi. Chuyển sang mili giây bằng phép chia nguyên có thể làm thời gian dương rất nhỏ thành 0. Đặc biệt **Thread.join(0)** có nghĩa là chờ vô hạn, vì vậy không truyền kết quả làm tròn 0 vào API này khi mục tiêu là timeout hữu hạn.

Duration.toNanos() có thể ném ArithmeticException nếu thời lượng quá lớn; hãy áp giới hạn hợp lý hoặc xử lý lỗi ở ranh giới nhận cấu hình. Từ chối budget âm hoặc bằng 0 nếu hợp đồng API yêu cầu một deadline còn hiệu lực.

## 4. Triển khai Deadline bất biến và kiểm tra bằng đồng hồ giả

Ví dụ dưới đây biên dịch được trên Java 17+. Deadline giữ **một** mốc bắt đầu và tổng hạn mức. LongSupplier cho phép dùng System::nanoTime trong thực tế hoặc đồng hồ giả khi kiểm thử. Chương trình main dùng đồng hồ giả nên kết quả hoàn toàn xác định, không phụ thuộc tốc độ máy.

**Tệp TimeoutBudgetDemo.java**

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public final class TimeoutBudgetDemo {

    static final class Deadline {
        private final LongSupplier nanoClock;
        private final long startedNanos;
        private final long budgetNanos;

        Deadline(Duration budget, LongSupplier nanoClock) {
            Objects.requireNonNull(budget, "budget");
            if (budget.isZero() || budget.isNegative()) {
                throw new IllegalArgumentException("budget must be positive");
            }
            this.budgetNanos = budget.toNanos();
            this.nanoClock = Objects.requireNonNull(nanoClock, "nanoClock");
            this.startedNanos = nanoClock.getAsLong();
        }

        long remainingNanos() {
            long elapsed = nanoClock.getAsLong() - startedNanos;
            if (elapsed < 0 || elapsed >= budgetNanos) {
                return 0L;
            }
            return budgetNanos - elapsed;
        }

        long requireRemainingNanos() throws TimeoutException {
            long remaining = remainingNanos();
            if (remaining == 0L) {
                throw new TimeoutException("Overall timeout budget exhausted");
            }
            return remaining;
        }
    }

    // Hàm áp dụng cho executor thực; main chỉ kiểm chứng phép tính bằng clock giả.
    static <T> T executeWithinBudget(
            ExecutorService executor,
            Callable<T> work,
            Deadline deadline)
            throws InterruptedException, ExecutionException, TimeoutException {

        // Đừng enqueue thêm việc khi budget đã hết.
        deadline.requireRemainingNanos();
        Future<T> future = executor.submit(work);

        try {
            // Đo lại sau submit: thời gian đưa task vào queue cũng tiêu budget.
            T result = future.get(
                    deadline.requireRemainingNanos(), TimeUnit.NANOSECONDS);

            // Nếu yêu cầu là hạn chót nghiêm ngặt, không nhận kết quả quá hạn.
            if (deadline.remainingNanos() == 0L) {
                throw new TimeoutException("Result arrived after deadline");
            }
            return result;
        } catch (TimeoutException e) {
            future.cancel(true);
            throw e;
        } catch (InterruptedException e) {
            future.cancel(true);
            Thread.currentThread().interrupt();
            throw e;
        }
    }

    private static void printRemaining(String label, Deadline deadline) {
        long milliseconds =
                TimeUnit.NANOSECONDS.toMillis(deadline.remainingNanos());
        System.out.println(label + ": " + milliseconds + " ms");
    }

    public static void main(String[] args) throws Exception {
        AtomicLong fakeNanos = new AtomicLong(0L);
        Deadline deadline =
                new Deadline(Duration.ofMillis(250), fakeNanos::get);

        printRemaining("Ban dau", deadline);
        fakeNanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(80));
        printRemaining("Sau A", deadline);
        fakeNanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(120));
        printRemaining("Sau B", deadline);
        fakeNanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(60));
        printRemaining("Sau C", deadline);

        try {
            deadline.requireRemainingNanos();
        } catch (TimeoutException e) {
            System.out.println("Tu choi buoc tiep theo: het budget");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TimeoutBudgetDemo.java
java TimeoutBudgetDemo
~~~

Stdout chính xác:

~~~text
Ban dau: 250 ms
Sau A: 170 ms
Sau B: 50 ms
Sau C: 0 ms
Tu choi buoc tiep theo: het budget
~~~

Chú ý: executeWithinBudget là một phương thức **có thể dùng cho executor thực** nhưng không được main gọi đến; stdout trên chỉ minh họa phép tính deadline. Ở môi trường thực, khởi tạo Deadline bằng System::nanoTime, tạo executor có vòng đời được quản lý rồi truyền **cùng đối tượng Deadline** qua mọi bước. Không dùng đồng hồ giả để điều khiển timeout thật của Future.get: Future dùng thời gian thực.

Ví dụ ý tưởng nối hai bước trên cùng executor và deadline, đặt **bên trong** một phương thức đã có các biến pool và deadline:

~~~java
String first = executeWithinBudget(pool, () -> "step-A", deadline);
String second = executeWithinBudget(pool, () -> first + "/step-B", deadline);
~~~

Đây là đoạn ghép vào chương trình, không phải tệp Java độc lập. Trong ứng dụng thật, mỗi Callable chứa công việc có thể chờ; Future.get tính thời gian còn lại ngay trước lúc chờ.

## 5. Future, ExecutorService và hủy công việc sau timeout

Future.get(timeout, TimeUnit.NANOSECONDS) chỉ giới hạn **thời gian thread gọi chờ kết quả**. Khi ném TimeoutException, task không tự động dừng. Vì vậy phương thức ví dụ gọi future.cancel(true) khi quá hạn.

Ý nghĩa và giới hạn:

1. Nếu task còn trong queue và chưa bắt đầu, hủy có thể ngăn nó chạy.
2. Nếu task đã chạy, cancel(true) cố **interrupt** thread xử lý; việc dừng phụ thuộc task và thư viện bên dưới có hợp tác với interrupt hay không.
3. Task đang xử lý I/O hoặc lời gọi native không hỗ trợ ngắt có thể tiếp tục dù Future đã ở trạng thái cancelled. Phải đặt timeout tại tầng I/O tương ứng và đóng tài nguyên khi cần.
4. Nếu thread gọi Future.get bị InterruptedException, hủy việc đang chờ, khôi phục interrupted flag ở ranh giới phù hợp, rồi truyền lỗi/cancellation lên trên. Không nuốt interrupt và bắt đầu retry như chưa có gì xảy ra.
5. Nếu Callable ném exception, Future.get ném ExecutionException chứa nguyên nhân. **ExecutionException không đồng nghĩa timeout**; cần giữ và phân loại nguyên nhân gốc.

ExecutorService có thể bị đầy queue hoặc từ chối task (RejectedExecutionException). Việc chờ trong queue cũng tiêu budget; timeout của Future.get được tính **từ lúc gọi get**, còn budget chung tính từ đầu tác vụ. Nếu task đã chạy xong nhưng chương trình đã quá hạn, chính sách nghiêm ngặt có thể từ chối kết quả, như ví dụ đã làm.

Không tạo một executor mới cho mỗi bước để “reset” thời gian, và không gọi shutdownNow trên executor dùng chung cho toàn ứng dụng chỉ vì một request timeout. Chủ sở hữu executor quản lý vòng đời; yêu cầu hiện tại chỉ hủy Future thuộc về nó.

## 6. Áp dụng cho lock, queue và các chỗ chờ khác

Mỗi điểm chờ phải lấy **remaining ngay trước lời gọi**. Không giữ một giá trị còn lại cũ rồi tái sử dụng sau nhiều thao tác.

### Chờ lock có giới hạn

~~~java
long waitNanos = deadline.requireRemainingNanos();
if (!lock.tryLock(waitNanos, TimeUnit.NANOSECONDS)) {
    throw new TimeoutException("Could not acquire lock before deadline");
}
try {
    // Vùng được bảo vệ; cần kiểm tra deadline trước bước chờ kế tiếp.
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

Đoạn này cần các biến lock, deadline và hàm updateSharedState từ chương trình chứa nó. Lock.tryLock có timeout có thể ném InterruptedException; hãy để nó truyền lên hoặc xử lý theo chính sách hủy. Sau khi **đã lấy lock**, timeout của tryLock không ép thân critical section dừng: cần giữ critical section ngắn, không đặt I/O chờ dài bên trong lock và kiểm tra deadline ở ranh giới phù hợp.

### Chờ phần tử từ BlockingQueue

~~~java
long waitNanos = deadline.requireRemainingNanos();
Message message = queue.poll(waitNanos, TimeUnit.NANOSECONDS);
if (message == null) {
    throw new TimeoutException("No message before deadline");
}
~~~

Message và queue là kiểu/biến ứng dụng, nên đây là mã minh họa tích hợp. Phân biệt null do queue.poll hết thời gian chờ với giá trị nghiệp vụ: BlockingQueue không cho phép phần tử null.

### Chờ thread hoặc điều kiện

Condition.awaitNanos(remaining) nhận nanosecond và trả thời gian còn lại theo hợp đồng riêng của API; phải kiểm tra điều kiện trong **vòng while** vì có thể thức dậy giả. Thread.join(long millis) lại có trường hợp join(0) = chờ vô hạn. Nếu phải dùng join theo budget nhỏ hơn 1 ms, hãy xử lý phần dư đúng cách hoặc chọn API hỗ trợ precision phù hợp; đừng làm tròn về 0 rồi chờ mãi.

**Thời gian không chờ** (CPU, serialize, kiểm tra điều kiện, xếp hàng, ghi log) vẫn tiêu budget. Timeout của API chặn không bao trọn các đoạn này. Với CPU-intensive task, cần các điểm hợp tác kiểm tra Thread.interrupted() hoặc deadline, thay vì chỉ đặt timeout ở Future.get.

## 7. Nhiều bước tuần tự, retry và backoff

Với pipeline tuần tự A → B → C, cả ba dùng một deadline:

1. Tạo deadline một lần **trước A**.
2. Trước A, tính remaining; truyền cho thao tác chờ A.
3. Khi A xong, tính lại remaining từ đồng hồ; dùng cho B.
4. Lặp lại với C. Nếu remaining = 0, từ chối bắt đầu bước mới và đưa kết quả timeout lên trên.

Nếu retry, **mọi attempt cùng dùng một deadline**. Ví dụ budget 500 ms; attempt đầu tiêu 280 ms, backoff tiêu 100 ms thì attempt hai chỉ còn khoảng 120 ms. Không lặp lại timeout=500 ms ở mỗi attempt. Cần tôn trọng giới hạn số lần thử và chỉ retry lỗi thực sự có thể phục hồi; một tác vụ hết budget không nên tiếp tục thêm retry.

Để giới hạn timeout mỗi attempt:

~~~java
long remaining = deadline.requireRemainingNanos();
long attemptLimit = TimeUnit.MILLISECONDS.toNanos(150);
long thisAttemptTimeout = Math.min(remaining, attemptLimit);
~~~

Sau khi xử lý lỗi, kiểm tra remaining trước sleep backoff; nếu backoff lớn hơn remaining, không ngủ vượt deadline rồi thử lại. TimeUnit.NANOSECONDS.sleep(...) hoặc Thread.sleep(Duration) (Java 19+) là chờ có thể bị interrupt, nhưng thời điểm thức dậy chỉ tương đối; cần kiểm tra lại deadline sau khi thức. Với Java 17, dùng TimeUnit.NANOSECONDS.sleep(nanos).

**Đánh đổi quan trọng:** budget không tự giải quyết idempotency. Nếu bước đã thực hiện side effect (gửi lệnh, ghi dữ liệu) rồi người gọi timeout, retry có thể lặp side effect. Dùng mã định danh thao tác, idempotency key, deduplication hoặc chiến lược kiểm tra kết quả khi nghiệp vụ yêu cầu.

## 8. Các bước song song và CompletableFuture

Nếu A và B chạy song song từ cùng một deadline, tổng wall-clock gần với **max(thời gian A, thời gian B)** cộng chi phí phối hợp, không phải mặc định tổng hai thời gian. Nhưng cả hai vẫn phải nhận thời gian còn lại của **cùng budget chung**. Khi một nhánh timeout, hệ thống cần quyết định dừng toàn tác vụ, dùng kết quả một phần hay có fallback; đây là chính sách nghiệp vụ, không do API timeout tự suy ra.

Ví dụ khi chỉ muốn giới hạn thời gian chờ tập hợp:

~~~java
long remaining = deadline.requireRemainingNanos();
CompletableFuture<Void> combined =
        CompletableFuture.allOf(futureA, futureB);
combined.get(remaining, TimeUnit.NANOSECONDS);
~~~

Đoạn trên giả định futureA và futureB đã được tạo, deadline cùng scope và các Future có kiểu CompletableFuture. Nếu combined.get timeout, **hai công việc nguồn có thể vẫn chạy**. Cần hủy/đóng tài nguyên ở các nhánh theo hợp đồng của chúng; gọi cancel trên CompletableFuture không bảo đảm interrupt tác vụ do supplyAsync tạo ra.

CompletableFuture.orTimeout(timeout, unit) hoàn tất **chính CompletableFuture đó** với TimeoutException nếu chưa xong; completeOnTimeout(value, timeout, unit) hoàn tất nó bằng giá trị dự phòng. Cả hai là chính sách **completion của future**, không phải cơ chế bảo đảm thread nền bị interrupt hoặc I/O bị hủy. Cấp timeout từ remaining chứ không gọi orTimeout với một con số cố định ở mỗi bước.

Khi fork nhiều nhánh, nên ghi nhận deadline **trước khi fork**. Nếu chỉ tạo deadline sau khi các nhánh đã chạy một lúc, chi phí khởi tạo và xếp hàng ban đầu bị bỏ sót khỏi ngân sách.

## 9. Chuyển budget qua API hoặc tiến trình khác

System.nanoTime của JVM A và JVM B **không có cùng gốc thời gian**; không gửi số nanoTime tuyệt đối từ A sang B rồi so sánh với B. Tại ranh giới một lời gọi liên tiến trình, có thể truyền **remaining duration** dưới dạng thời lượng tương đối, ghi nhận thời gian truyền và các overhead phù hợp, rồi tạo deadline nội bộ mới dựa trên System.nanoTime của bên nhận. Nếu giao thức dùng timestamp lịch (ví dụ deadline epoch), phải xét clock skew, network delay và độ tin cậy của đồng hồ hai phía.

Trong ứng dụng có nhiều hop, bên nhận không được tự cấp lại budget gốc sau mỗi hop. Thời lượng được phép xử lý về sau phải được ràng buộc bởi thời gian còn lại do upstream cung cấp và giới hạn nội bộ của chính hop đó.

Với Java HttpClient, request timeout và connect timeout có phạm vi riêng; không mặc định chúng bao trọn mọi thao tác chuẩn bị, xếp hàng, parse và retry của pipeline. Đặt timeout theo remaining tại lúc gọi API, rồi đo lại budget sau khi trả về. Cần hiểu loại exception và chính sách cancel của từng API I/O đang sử dụng.

## 10. Chính sách khi hết hạn: trả lỗi, fallback hay partial result?

Trước khi triển khai, xác định rõ hợp đồng của tác vụ:

| Chính sách | Khi áp dụng | Điều cần giữ |
| --- | --- | --- |
| Fail fast với TimeoutException | Các bước phụ thuộc nhau, phải đủ kết quả | Không bắt đầu bước mới sau hạn; hủy công việc có thể hủy |
| Trả fallback | Có giá trị dự phòng hợp lệ | Fallback phải rẻ, đã biết trước hoặc vẫn nằm trong budget |
| Trả kết quả một phần | Nghiệp vụ cho phép thiếu nhánh | Gắn trạng thái partial, không âm thầm coi là đầy đủ |
| Best effort cleanup | Có tài nguyên phải đóng | Cleanup có giới hạn và chạy trong finally; ghi nhận nếu quá hạn |

Thời gian cleanup và đóng tài nguyên cũng có chi phí. Deadline cho **đường xử lý nghiệp vụ** không nhất thiết có thể cắt bỏ các bước giải phóng bắt buộc như unlock, close hoặc transaction rollback. Thiết kế chính sách cleanup tách biệt, giữ thao tác giải phóng ngắn và không sử dụng một timeout vô hạn khi đã quá hạn.

Không biến mọi timeout thành InterruptedException: TimeoutException nghĩa là **deadline hết**, trong khi InterruptedException là **thread được yêu cầu ngắt**. Hai tín hiệu cần được phân biệt trong log, metrics và luồng điều khiển.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Mỗi bước dùng timeout đầy đủ | Tổng latency tăng theo số bước | Chuyển cùng Deadline qua pipeline |
| Tính remaining một lần rồi giữ nguyên | Bỏ sót CPU, queue, retry và backoff | Tính lại trước mỗi lời gọi chặn |
| Dùng currentTimeMillis để đo trôi qua | Đồng hồ lịch có thể bị điều chỉnh | Dùng System.nanoTime trong một JVM |
| Dùng Future.get(timeout) rồi coi task đã dừng | get chỉ ngừng chờ | Hủy Future, interrupt hợp tác và đặt timeout I/O |
| Catch InterruptedException rồi retry | Bỏ qua yêu cầu hủy | Truyền lỗi hoặc khôi phục interrupt và dừng đúng cách |
| Đổi nanosecond sang millis rồi gọi join(0) | join(0) nghĩa là đợi mãi | Tránh làm tròn về 0; dùng API phù hợp |
| Tạo deadline mới mỗi lần retry | Reset ngân sách | Tất cả retry cùng dùng deadline gốc |
| Chỉ đặt timeout cho từng nhánh CompletableFuture | Không có tổng hạn mức | Đặt deadline toàn tác vụ; xử lý cancel từng nhánh |
| Dùng nanoTime từ tiến trình khác | Mốc đo không tương thích | Truyền remaining duration hoặc giao thức deadline có xét skew |
| Coi timeout là bảo đảm side effect chưa xảy ra | Task có thể đã ghi dữ liệu trước khi hết hạn | Thiết kế idempotency và kiểm tra trạng thái |

## 12. Kiểm thử và quan sát hành vi

Nên kiểm thử phép tính deadline bằng **đồng hồ giả** để không lệ thuộc scheduler: remaining ban đầu, giảm sau mỗi bước, đúng tại ranh giới hết hạn, quá hạn, budget không hợp lệ. Chương trình runnable ở mục 4 là một ví dụ kiểm tra ranh giới như vậy.

Ngoài ra cần thử tích hợp với executor và đồng bộ thật:

- **Queue delay**: task chờ trong executor queue cũng phải trừ budget.
- **Timeout giữa pipeline**: A xong nhưng B bắt đầu khi remaining không đủ; B chỉ được chờ thời gian còn lại.
- **Interrupt**: task hợp tác dừng và giải phóng tài nguyên; caller không nuốt InterruptedException.
- **Task không hợp tác**: Future.cancel(true) trả về nhưng tác vụ có thể còn chạy; phải nhận diện giới hạn thực.
- **Retry/backoff**: budget không reset sau attempt lỗi.
- **Parallel**: khi một nhánh hết hạn, các nhánh còn lại được hủy hoặc cho hoàn thành đúng chính sách.
- **Side effect**: retry sau timeout không nhân đôi thao tác không idempotent.

Trong vận hành, ghi các mốc elapsed tổng, remaining tại lúc bắt đầu mỗi bước, thời gian xếp hàng, số lần retry, timeout theo nguồn và kết quả cleanup. Dùng đồng hồ monotonic để đo thời lượng; nếu cần timestamp cho log, ghi timestamp lịch **riêng**. Tránh log dữ liệu nhạy cảm từ task.

## 13. Checklist thiết kế trước khi đưa vào hệ thống

1. Xác định budget toàn tác vụ và mốc bắt đầu thật (trước enqueue/IO).
2. Tạo một Deadline dùng đồng hồ monotonic và truyền cùng một instance qua các bước nội JVM.
3. Trước **mỗi** thao tác chặn, lấy remaining; dừng khi 0 và kết hợp với giới hạn riêng bằng min khi cần.
4. Đảm bảo các nhánh async có chính sách cancellation, interrupt, timeout I/O và cleanup rõ ràng.
5. Tính cả retry, backoff, queue wait và xử lý trung gian vào cùng ngân sách.
6. Kiểm thử bằng đồng hồ giả cho phép tính; kiểm thử thực cho hủy, đua tranh, tài nguyên và side effect.

**Điểm cốt lõi:** Một timeout ở từng bước không tạo thành timeout cho toàn pipeline. Deadline chung, remaining được tính lại liên tục và cơ chế hủy hợp tác mới giúp một tác vụ Java concurrency tôn trọng giới hạn thời gian tổng thể.

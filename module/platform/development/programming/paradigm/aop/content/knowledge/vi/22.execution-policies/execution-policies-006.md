# Giới hạn thời gian và giới hạn khả năng dừng tác vụ trong AOP

## 1. Bài toán: áp dụng chính sách thời gian tại đúng ranh giới thực thi

Aspect-Oriented Programming (AOP) cho phép tách các chính sách xuyên suốt như đo thời gian, từ chối tác vụ quá hạn, truyền deadline, ghi nhận timeout, yêu cầu hủy và quản lý tài nguyên khỏi logic nghiệp vụ. Một around advice có thể thực hiện kiểm tra trước lời gọi, gọi phương thức đích, quan sát kết quả và xử lý lỗi theo hợp đồng đã định.

Tuy nhiên, việc đặt advice bao quanh lời gọi không tự trao cho advice khả năng ngắt một phương thức Java đang thực thi. Giả sử phương thức readData() chờ I/O trong 30 giây. Quy tắc “thời gian tối đa 2 giây” có thể có nhiều ngữ nghĩa:

- **Giới hạn thời gian đợi của caller:** sau 2 giây, caller nhận thông báo timeout và thôi chờ. Công việc nền có thể tiếp tục.
- **Yêu cầu hủy:** sau 2 giây, runtime gửi cancel/interrupt/token. Task có thể dừng nếu hợp tác hoặc API tài nguyên có hỗ trợ.
- **Xác nhận task đã dừng:** cần tín hiệu hoàn tất thực tế hoặc cơ chế termination thích hợp. Việc nhận timeout hoặc future bị đánh dấu canceled chưa phải bằng chứng.
- **Giới hạn tổng thời gian operation:** tính cả thời gian xếp hàng, nhiều lời gọi con, retry, callback và cleanup theo contract. Mỗi bước tự cấp lại 2 giây có thể làm tổng thời gian vượt xa ngân sách.
- **Giới hạn việc sử dụng tài nguyên:** số luồng, kết nối, tác vụ đang chờ hoặc queue phải được kiểm soát độc lập; caller ngừng chờ không có nghĩa tài nguyên đã được giải phóng.

Trong bài này, ta phân biệt việc **phát hiện quá hạn**, **thực thi timeout đối với caller**, **gửi tín hiệu hủy**, và **đảm bảo kết thúc công việc**. Đây là những trách nhiệm khác nhau của aspect, runtime, code nghiệp vụ và thư viện quản lý tài nguyên.

> Quy tắc nền: TIMEOUT, CANCEL REQUESTED, CANCELED FUTURE và TASK TERMINATED không được gộp thành cùng một trạng thái.

## 2. Những thuật ngữ cần dùng chính xác

**Join point:** điểm thực thi mà một aspect theo dõi/can thiệp, thường là lời gọi phương thức. Một join point ở entry/exit chưa chắc bao quát cả công việc bất đồng bộ phát sinh từ lời gọi.

**Around advice:** mã chạy bao quanh join point. Nó có thể ghi timestamp trước/sau, kiểm tra điều kiện đầu vào, chuyển kết quả hoặc lỗi theo một chính sách đã công bố.

**Timeout:** khoảng thời gian tối đa được chờ hoặc thực thi theo định nghĩa cụ thể, ví dụ timeout khi kết nối, đọc socket, đợi lock, lấy giá trị future, hoặc tổng deadline nghiệp vụ. Không được dùng từ timeout mà bỏ qua đối tượng đang bị giới hạn.

**Deadline:** mốc kết thúc ngân sách thời gian của một operation. Các bước con cần sử dụng phần **thời gian còn lại** thay vì mỗi bước được cấp lại toàn bộ ngân sách.

**Cancellation:** yêu cầu không tiếp tục thực hiện công việc. Có thể là token, interrupt, Future.cancel(), hủy subscription, đóng request handle, hoặc gửi thông điệp đến bộ quản lý tác vụ.

**Cooperative cancellation:** task chủ động kiểm tra tín hiệu hủy hoặc dùng API hỗ trợ ngắt, từ đó thoát và giải phóng tài nguyên.

**Termination acknowledgment:** dấu hiệu đủ tin cậy cho biết task đã đi ra khỏi phần thực thi được quản lý hoặc đã dọn xong tài nguyên cần thiết. Tùy yêu cầu, tín hiệu này khác hoàn toàn với việc future được đánh dấu canceled.

**Soft limit và hard limit:** soft limit có thể chỉ cảnh báo hoặc dừng chờ; hard limit hứa ràng buộc cứng về hành vi/nguồn lực. AOP trên cùng JVM không thể bảo đảm cưỡng chế dừng một đoạn mã Java bất kỳ không hợp tác mà vẫn an toàn với dữ liệu dùng chung.

## 3. Phân biệt kết thúc thời gian chờ và kết thúc thực thi

Một sơ đồ trạng thái thường gặp:

~~~text
Caller                 Around advice           Worker / tài nguyên
  |                           |                         |
  | gọi operation             |                         |
  +-------------------------->| submit work             |
  |                           +------------------------>|
  |                           | chờ kết quả             | đang chạy
  |                           |                         |
  |                           | quá thời gian           | vẫn có thể chạy
  |<--------------------------+ Timeout                 |
  |                           | request cancellation    |
  |                           +------------------------>|
  |                           |                         | thấy/ngó lơ tín hiệu
  |                           |                         | cleanup / hoàn tất
~~~

| Sự kiện quan sát | Điều có thể khẳng định | Điều chưa thể khẳng định |
| --- | --- | --- |
| Future.get(timeout) ném TimeoutException | Caller đã chờ quá thời lượng chỉ định để lấy kết quả | Task bị cancel hoặc thực tế đã dừng |
| Future.cancel(true) trả true | Yêu cầu chuyển future sang canceled được chấp nhận theo contract | Luồng đã hoàn tất; I/O đã đóng; side effect đã rollback |
| Future.isCancelled() trả true | Trạng thái future là canceled | Worker đã cleanup xong |
| Thread nhận interrupt | Đã có tín hiệu interrupt theo Java | Code không hợp tác bắt buộc phải ngừng |
| Completion observer nhận lỗi timeout | Đối tượng được quan sát mang trạng thái lỗi timeout | Thao tác thực tế bên dưới cũng đã ngừng |
| Task báo terminated/cleanup complete | Phần công việc được giám sát thực sự kết thúc theo hợp đồng của tín hiệu | Mọi tác vụ con không được quản lý cũng đã kết thúc |

Nếu caller timeout sau 100 ms nhưng task vẫn chạy 10 giây và ghi dữ liệu, caller không được giả định “timeout = không có side effect”. Điều này đặc biệt quan trọng với thanh toán, ghi database, gửi tin nhắn, thao tác file hoặc retry không có idempotency.

## 4. Đo thời gian sau lời gọi không phải cưỡng chế timeout

Một advice đồng bộ có thể đo thời gian như sau:

~~~java
// Fragment minh họa: invokeTarget và recordLatency đã tồn tại.
long started = System.nanoTime();
try {
    return invokeTarget();
} finally {
    long elapsed = System.nanoTime() - started;
    recordLatency(elapsed);
}
~~~

Nếu invokeTarget bị kẹt vô hạn, khối finally cũng chưa được chạy. Việc kiểm tra elapsed sau khi target trả về chỉ **đo thời gian đã trôi qua**; nó không ngắt target vào đúng mốc deadline.

Một cách sai khác là ném ngoại lệ khi nhận thấy target quá chậm sau khi nó đã thực hiện xong:

~~~java
// Anti-pattern nếu nghiệp vụ chưa chấp thuận semantics này.
long begin = System.nanoTime();
Result result = target();
if (System.nanoTime() - begin > budgetNanos) {
    throw new RuntimeException("late");
}
return result;
~~~

Nếu target đã chuyển tiền hoặc gửi thông điệp, lỗi giả tạo này có thể khiến caller retry và thực hiện side effect lần nữa. Nếu chính sách yêu cầu **observe-only**, chỉ ghi nhận vi phạm SLO, không thay kết quả. Nếu chính sách yêu cầu báo trễ sau hoàn tất, phải xác định rõ trước liệu caller được phép hiểu nó là thất bại nghiệp vụ hay không.

## 5. Các cấp độ chính sách thực thi

| Chính sách | Chức năng | Phạm vi bảo đảm |
| --- | --- | --- |
| Observe-only | Ghi độ trễ và phát cảnh báo khi quá hạn | Không giới hạn thời gian thực tế |
| Pre-invocation admission | Từ chối trước khi bắt đầu nếu deadline đã hết | Không khởi chạy thao tác mới qua join point đó |
| Bounded wait | Giới hạn thời gian caller đợi future hoặc tín hiệu | Caller được giải phóng khỏi chờ quá lâu |
| Cooperative cancellation | Gửi token/interrupt/cancel handle, task tự dừng | Dừng được khi task và API tài nguyên hợp tác |
| API-native timeout | Thiết lập timeout/deadline trực tiếp trên I/O/client/driver | Hành vi do API đó quy định |
| External isolation | Chạy mã nguy cơ treo trong process/container có thể kết thúc | Có thể thu hồi tài nguyên trong phạm vi cô lập; side effect ngoài vẫn cần quản lý |

Nên chọn cấp độ thấp nhất nhưng đáp ứng đúng yêu cầu. Nếu mục tiêu chỉ là thống kê độ trễ, việc chuyển toàn bộ lời gọi sang worker để enforce timeout không cần thiết và có thể đổi ngữ nghĩa. Nếu yêu cầu là caller luôn thôi chờ sau 200 ms, bounded wait là một công cụ; nếu yêu cầu CPU phải được trả lại trong hạn, bounded wait đơn độc là chưa đủ.

## 6. Java interrupt là lời đề nghị dừng hợp tác

Trong Java, Thread.interrupt() thường dùng để truyền yêu cầu ngắt. Khi luồng đang chờ trên API interruptible, như Thread.sleep(), CountDownLatch.await(), BlockingQueue.take() hoặc Object.wait(), lời chờ có thể kết thúc bằng InterruptedException. Với code đang tính toán CPU và không kiểm tra interrupt flag, tín hiệu đó có thể không làm thay đổi luồng điều khiển.

Một tác vụ tính toán chủ động kiểm tra tín hiệu:

~~~java
// Ví dụ fragment có thể đặt trong một class Java 17.
static long calculateUntilCancelled() {
    long result = 0;
    while (!Thread.currentThread().isInterrupted()) {
        result++;
        if (result == 1_000_000) {
            break; // Điểm dừng bình thường chỉ dùng để minh họa.
        }
    }
    return result;
}
~~~

Nếu phép tính kéo dài hơn, code cần chọn nhịp kiểm tra phù hợp: kiểm tra quá thưa làm cancel phản hồi chậm; quá dày có thể tốn overhead. Với API ném InterruptedException, có hai phương án phổ biến:

- Truyền tiếp InterruptedException khi chữ ký/hợp đồng cho phép.
- Nếu phải xử lý tại đây, có thể phục hồi interrupt flag bằng Thread.currentThread().interrupt() trước khi thoát hoặc để tầng trên xử lý.

Ví dụ:

~~~java
// Minh họa Runnable chờ dữ liệu từ blocking queue.
try {
    queue.take();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Đoạn này cần biến queue từ chương trình xung quanh. Không nuốt InterruptedException rồi quay lại vòng lặp vô hạn nếu task được kỳ vọng có thể hủy. Không dùng Thread.stop() để ép dừng: dừng luồng ở điểm tùy ý là nguy hiểm, có thể làm hỏng trạng thái chia sẻ và các bất biến của đối tượng.

Một số I/O hay thư viện native có cơ chế timeout/close/cancel riêng; interrupt không phải lúc nào cũng dừng được chúng. Aspect có thể cấp deadline, nhưng nơi thực hiện I/O phải chuyển nó sang API hỗ trợ thật sự.

## 7. Ví dụ Java 17+ chạy được: chờ hết hạn, yêu cầu hủy, xác nhận interrupt

Ví dụ dưới đây sử dụng ExecutorService và CountDownLatch để tạo một task **đang chờ thực sự**. Có ba tín hiệu được kiểm tra riêng: timeout của caller, trạng thái future nhận yêu cầu cancel, và code worker nhận InterruptedException.

Tạo file **TimeoutPolicyDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TimeoutPolicyDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch interruptSeen = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        Future<String> task = executor.submit(() -> {
            started.countDown();
            try {
                neverReleased.await();
                return "COMPLETED";
            } catch (InterruptedException interrupted) {
                interruptSeen.countDown();
                Thread.currentThread().interrupt();
                return "STOPPED";
            }
        });

        try {
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            try {
                task.get(30, TimeUnit.MILLISECONDS);
                throw new AssertionError("Unexpected completion");
            } catch (TimeoutException expected) {
                System.out.println("WAIT TIMED OUT");
                boolean accepted = task.cancel(true);
                System.out.println("CANCEL ACCEPTED: " + accepted);
            }

            if (!interruptSeen.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Worker did not acknowledge interrupt");
            }

            System.out.println("TASK SAW INTERRUPT");
            System.out.println("FUTURE CANCELED: " + task.isCancelled());
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TimeoutPolicyDemo.java
java TimeoutPolicyDemo
~~~

Đầu ra trong điều kiện thực thi bình thường:

~~~text
WAIT TIMED OUT
CANCEL ACCEPTED: true
TASK SAW INTERRUPT
FUTURE CANCELED: true
~~~

**Phân tích:**

1. started.await bảo đảm worker đã khởi chạy trước khi caller bắt đầu chờ 30 ms. Task đang chờ latch không được nhả, vì thế future chưa thể hoàn tất bình thường.
2. Future.get(30, MILLISECONDS) ném TimeoutException. Đây là **lỗi của thao tác chờ**, không phải bằng chứng worker đã dừng.
3. cancel(true) yêu cầu chuyển future sang canceled và cố gửi interrupt cho worker đang chạy. Với task đang chờ interruptible, yêu cầu hủy được chấp nhận.
4. interruptSeen.await(...) xác minh **code worker đã quan sát InterruptedException**. Nếu worker không hợp tác, sẽ không có tín hiệu này chỉ nhờ future báo canceled.
5. task.isCancelled() kiểm tra trạng thái future; nó là tín hiệu khác với việc worker đã vào nhánh interrupt.
6. shutdownNow() trong finally gửi yêu cầu dừng các task còn lại và không tự bảo đảm một task tùy ý đã chết.

Ví dụ đặt thời gian chờ hữu hạn 5 giây để không treo trong môi trường worker bị thiếu tài nguyên. Nếu worker không được lên lịch hoặc không nhận interrupt trong 5 giây, chương trình chủ động ném IllegalStateException; do đó không nên diễn giải stdout trên như bảo đảm thời gian chính xác cho mọi môi trường.

Trong ví dụ, worker có thể return "STOPPED" sau khi nhận interrupt, nhưng future đã bị cancel, nên caller không nhận giá trị đó từ Future.get(). Trạng thái future và vòng đời code task là hai thứ khác nhau. Chương trình này minh họa cơ chế mà advice có thể phối hợp với executor, không phải một implementation weaving AOP hoàn chỉnh.

## 8. Future.get timeout không giống Future.cancel

Một API như Future.get(timeout, unit) trả kết quả nếu future hoàn tất trong thời gian chờ. Nếu hết hạn, phương thức ném TimeoutException. Theo contract, bản thân thao tác chờ có thời hạn **không tự động cancel** công việc.

~~~java
// Fragment minh họa; future, processValue và recordTimeout có sẵn.
try {
    String value = future.get(200, TimeUnit.MILLISECONDS);
    processValue(value);
} catch (TimeoutException timeout) {
    recordTimeout();
    // Tùy chính sách mới cân nhắc future.cancel(true).
}
~~~

Future.cancel(true) cố yêu cầu ngắt nếu task đang chạy; cancel(false) yêu cầu hủy future mà không gửi interrupt vào task đang chạy. Giá trị boolean từ cancel phản ánh việc hủy được chấp nhận theo trạng thái future; không phải lời hứa task đã ngừng CPU/I/O hoặc đã cleanup. Một future có thể không được tạo bởi FutureTask nên chi tiết cancellation phụ thuộc implementation.

Một lời gọi get có thể phát sinh InterruptedException nếu **chính thread đang chờ** bị interrupt; cũng có thể phát sinh ExecutionException nếu task kết thúc bằng ngoại lệ. Advice cần phân biệt rõ ba nhánh: timeout trong lúc chờ, ngắt caller và lỗi thật của task. Không chuyển mọi ngoại lệ thành TimeoutException.

## 9. CompletableFuture.orTimeout thay outcome của future, không cưỡng chế dừng worker

Trong Java 17, CompletableFuture.orTimeout(timeout, unit) sẽ sắp đặt để **chính CompletableFuture được gọi** hoàn thành exceptional bằng TimeoutException nếu chưa hoàn thành kịp. Nó không có cam kết gửi interrupt để dừng công việc nền tạo ra future.

~~~java
// Fragment minh họa; startAsyncWork tạo CompletableFuture<String>.
CompletableFuture<String> stage = startAsyncWork();
stage.orTimeout(100, TimeUnit.MILLISECONDS);
~~~

Hệ quả quan trọng:

- Future có thể ở trạng thái exceptional do timeout, dù thread đang chạy công việc vẫn tiếp tục xử lý.
- Nếu gọi completeOnTimeout(value, timeout, unit), future có thể nhận giá trị fallback dù kết quả thật chưa đến; đó là **thay đổi outcome hiển thị**, không phải hủy công việc.
- Khi công việc nền sau đó hoàn tất, future đã terminal có thể không nhận được kết quả mới, nhưng tác dụng phụ bên ngoài có thể đã xảy ra.
- Nếu một aspect gọi orTimeout lên future do target trả về, aspect **đang thay đổi trạng thái future gốc**, không chỉ quan sát. Cần có quyền theo contract.
- Cancellation của dependent stage không mặc nhiên lan thành cancellation của task upstream. Cần kiểm tra hợp đồng API cụ thể.

So sánh ngắn:

| API/cơ chế | Điều thay đổi khi hết hạn | Có ngắt công việc thực sự? |
| --- | --- | --- |
| Future.get(t, unit) | Caller không còn chờ; nhận TimeoutException | Không |
| Future.cancel(true) | Yêu cầu đánh dấu hủy và gửi interrupt nếu phù hợp | Không được bảo đảm |
| CompletableFuture.orTimeout | CompletableFuture có thể exceptional bằng TimeoutException | Không |
| CompletableFuture.completeOnTimeout | CompletableFuture có thể hoàn tất bằng fallback | Không |
| Timeout của HTTP/socket/driver | Thao tác I/O nhận deadline theo contract của tài nguyên | Phụ thuộc API và tầng thực thi |
| Task kiểm tra cancellation token | Task có thể tự thoát và cleanup | Phụ thuộc code hợp tác |

Vì thế, nếu một aspect muốn **đo timeout** mà không đổi contract, hãy quan sát thay vì vô tình áp dụng orTimeout. Nếu muốn caller thực sự nhận TimeoutException khi quá hạn, cần mô tả điều này trong chính sách và quyết định riêng có/không yêu cầu hủy công việc.

## 10. Deadline dùng chung qua các lời gọi lồng nhau

Giả sử operation có ngân sách 800 ms:

~~~text
request: deadline tổng 800 ms
   |
   +-- validate input       100 ms
   +-- call service A       450 ms
   +-- call service B       còn gần 250 ms, trừ overhead
   +-- cleanup / respond    cần dự trù thêm theo policy
~~~

Nếu mỗi bước con lại được cấp 800 ms, tổng thời gian vượt xa deadline. Một aspect ở entry có thể tạo context ngân sách; các advice tại tầng con lấy thời gian **còn lại**, hoặc từ chối khi ngân sách không đủ.

Trong cùng JVM, System.nanoTime() phù hợp để đo khoảng thời gian đã trôi qua vì không phụ thuộc chỉnh đồng hồ hệ thống:

~~~java
// Fragment minh họa; nextCall được khai báo ở chương trình xung quanh.
long budgetNanos = TimeUnit.MILLISECONDS.toNanos(800);
long startedNanos = System.nanoTime();

// ... chạy một số bước ...
long elapsedNanos = System.nanoTime() - startedNanos;
long remainingNanos = budgetNanos - elapsedNanos;

if (remainingNanos <= 0) {
    throw new IllegalStateException("Deadline exceeded before next step");
}
nextCall(remainingNanos, TimeUnit.NANOSECONDS);
~~~

Khi triển khai, cần kiểm tra budget âm/0, đơn vị đổi sang nanosecond, overflow trong phép cộng/chuyển đổi, và việc làm tròn gây timeout 0. NanoTime có ý nghĩa để so sánh **thời lượng trên cùng JVM**, không phải timestamp lịch có thể gửi giữa các máy.

Khi deadline truyền qua network/process khác, không truyền trực tiếp giá trị nanoTime của JVM hiện tại và suy đoán máy khác có cùng gốc thời gian. Có thể chuyển ngân sách còn lại hoặc một deadline theo thời gian thực với chính sách xử lý lệch đồng hồ, rồi xác định lại mốc monotonic khi vào từng process.

Nếu operation có deadline 800 ms còn một phương thức con có limit 300 ms, thời gian chờ hữu hiệu là min(thời gian còn lại của cha, 300 ms). Phương thức con không được vô tình kéo dài deadline cha. Hãy tính cả queue, retry, backoff, và nếu cần, phần thời gian dự trữ cho cleanup/response.

## 11. Deadline xuyên ranh giới bất đồng bộ

Một lời gọi phương thức có thể trả về CompletionStage, Future, callback handle, task ID hoặc Publisher trước khi công việc hoàn tất. Around advice tại lời gọi này chỉ biết **invocation đã trả về**. Để quan sát kết quả thật, cần hook đúng cơ chế:

| Mô hình | Ranh giới để theo dõi deadline/cancel |
| --- | --- |
| CompletionStage | Completion callback và timeout policy trên stage phù hợp |
| ExecutorService | Submission, task execution wrapper, future lifecycle |
| Callback API | Wrapper callback nhận result/error, timer và hủy đăng ký theo contract |
| Stream/Publisher | Mỗi subscription, tín hiệu terminal, cancellation handle |
| Queue/fire-and-forget | Consumer, operation ID, completion event hoặc task supervisor |
| I/O chuyên biệt | Request/read/connect timeout hoặc cancel handle của API |

Ví dụ timeline:

~~~text
t0: around advice bắt đầu lời gọi tạo future
t1: target trả future pending; advice trả future
t2: deadline của operation hết hạn; caller nhận timeout
t3: worker vẫn chạy; có hoặc không nhận yêu cầu hủy
t4: worker dừng hoặc hoàn tất muộn; cleanup thực hiện
~~~

Nếu đo latency ở t0 → t1 rồi gọi đó là “thời gian nghiệp vụ”, số đo sai. Nếu muốn biết khi nào tác vụ thật sự kết thúc, cần completion hook hoặc tín hiệu lifecycle khác. Nếu hệ thống cho phép timeout ở t2, ghi riêng **caller timed out** và **work terminated at t4**, không ép chúng vào cùng một mốc.

### Context propagation

ThreadLocal của caller không tự động đi theo tác vụ trên executor/callback khác. Một aspect có thể capture deadline/correlation ID lúc submit, truyền vào task hoặc callback, restore khi thực thi và cleanup trong finally. Không để context của request cũ rò sang request mới trên thread pool.

Một kỹ thuật thực tiễn là truyền cancellation token tường minh qua đối tượng context hoặc tham số công việc. Token cần an toàn khi truy cập đa luồng, và phải có điểm kiểm tra ở những công việc dài. Nếu caller đã rời đi, các callback muộn cần xem còn nên phát kết quả nữa không và xử lý race theo state machine.

## 12. Không dùng executor wrapper một cách vô điều kiện

Việc quanh mỗi target đồng bộ bằng cách chạy nó trên executor rồi chờ get(timeout) thay đổi execution semantics:

1. **Thread identity:** target chạy trên luồng khác; code phụ thuộc thread hiện tại có thể sai.
2. **Locking:** caller đang giữ một lock rồi đợi worker cần cùng lock có thể deadlock.
3. **ThreadLocal/context:** transaction context, tracing, security identity, locale có thể không đi theo.
4. **Exception:** checked exception từ task thường được bao bởi ExecutionException khi tiêu thụ future; không tự động giữ nguyên hợp đồng throw.
5. **Scheduling:** thứ tự side effect có thể thay đổi hoặc xen kẽ với lời gọi khác.
6. **Cancellation:** cancel(true) không bắt buộc worker ngừng nếu code không hợp tác.
7. **Lifecycle:** caller có thể đóng tài nguyên sau timeout trong khi worker vẫn sử dụng.
8. **Load:** số task chờ/còn chạy có thể tăng dù caller timeout nhanh.
9. **Reentrancy:** method được gọi lồng nhau và aspect nhiều tầng có thể tạo executor/task vô ích, thậm chí chờ vòng.
10. **Idempotency:** caller retry khi worker cũ chưa dừng có thể thực hiện cùng side effect nhiều lần.

Nên ưu tiên đặt timeout tại API I/O hoặc cơ chế bất đồng bộ sở hữu tác vụ. Khi thật sự phải chuyển thread để giới hạn thời gian chờ, hãy định nghĩa tường minh sự thay đổi contract, giới hạn số worker/queue và quản lý cleanup.

Cơ chế weaving có thể cho AOP thêm join point, nhưng không tự biến mã bất kỳ thành cancelable. Khả năng dừng vẫn phụ thuộc task và tài nguyên thực thi.

## 13. Cancel không có nghĩa rollback hoặc không có side effect

Giả sử task chuyển tiền:

~~~text
0 ms:  gửi lệnh chuyển tiền đến hệ thống khác
100ms: caller hết thời hạn đợi
120ms: future được yêu cầu cancel
300ms: hệ thống ngoài xác nhận tiền đã chuyển
~~~

Ở t2 caller có thể nhận timeout nhưng lệnh gửi đi từ t0 vẫn được phía ngoài xử lý. Retry ngay có thể chuyển tiền lần nữa nếu không có idempotency. Vì vậy:

- Dùng operation ID/idempotency key ở những nghiệp vụ có khả năng lặp.
- Khi timeout ở ranh giới mạng, cho phép trạng thái **không biết kết quả** nếu không có xác nhận.
- Có API truy vấn/reconcile trạng thái thật khi cần.
- Chỉ retry theo chính sách đã xét idempotency và retry budget.
- Không tuyên bố cancellation đã rollback transaction.
- Nếu task giữ tài nguyên độc quyền, đợi tín hiệu termination/cleanup thích hợp trước khi cấp phát lại.

Nếu code không thể hợp tác và cần đảm bảo không làm treo JVM, cách ly trong process/container với ranh giới quản lý tài nguyên có thể thích hợp hơn. Nhưng kết thúc process cũng không rollback tự động side effect trong database hoặc hệ thống từ xa.

## 14. Hủy hợp tác nên có giao thức rõ ràng

Trong các hệ thống yêu cầu an toàn cao, cancellation là một quy trình thay vì một lệnh:

1. **Request:** deadline watcher/caller yêu cầu hủy.
2. **Delivery:** interrupt, token hoặc native cancellation signal đến worker.
3. **Acknowledgment:** worker báo đã nhận yêu cầu, nếu giao thức hỗ trợ.
4. **Quiescence:** phần công việc cần dừng không còn chạy nữa.
5. **Cleanup:** tài nguyên được đóng hoặc chuyển giao an toàn.
6. **Final status:** kết quả cuối được công bố: succeeded, failed, canceled, timeout hoặc unknown.

Có race khi task hoàn tất gần đúng thời điểm timeout. Cancel có thể trả false vì công việc đã xong, hoặc future đã canceled trước khi cleanup xong. Policy phải quyết định: completion đúng mốc deadline được ưu tiên thế nào, caller nhìn thấy kết quả nào và việc bồi hoàn/đối soát được thực hiện ra sao.

Nếu caller đã timeout và không thể chờ vô hạn, có thể phát yêu cầu hủy rồi trả caller, đồng thời tiếp tục theo dõi cleanup từ một supervisor. Khi công việc không dừng sau khoảng grace hữu hạn, báo trạng thái “timeout; termination not confirmed” thay vì ghi “canceled and stopped”.

Không thay giao thức này bằng việc chỉ đọc Future.isCancelled().

## 15. Vị trí phù hợp của advice và hook

| Điểm chèn | Việc nên làm | Sai lầm cần tránh |
| --- | --- | --- |
| Trước method invocation | Kiểm tra deadline và quyết định có nhận lời gọi không | Cho rằng có thể ngắt target bất kỳ khi đang chạy |
| Around/after-returning | Đo invocation latency và bảo toàn kết quả | Nhầm method returned với async operation completed |
| After-throwing | Ghi nhận lỗi đồng bộ thực sự | Phân loại mọi exception thành timeout |
| Submit task | Gắn context/token, ghi queue timestamp | Xem submit accepted là task success |
| Task wrapper | Kiểm tra hủy trước khi chạy; đo execution; cleanup | Giải phóng permit khi caller hết chờ dù worker còn chạy |
| Future completion | Quan sát success/failure/cancellation thật ở stage được chọn | Cho rằng timeout stage ngắt worker |
| Callback invocation | Xem callback được gọi lúc nào; bảo toàn error channel | Giả định callback luôn chạy thread khác |
| Stream subscription | Quan sát onNext/onError/onComplete/cancel theo protocol | Tự subscribe thêm để đo và làm sinh side effect |
| Resource-native API | Cấu hình read/connect/request deadline | Chỉ đặt timeout ở outer advice mà không giới hạn I/O |

Nếu cơ chế AOP hỗ trợ pointcut trên nhiều method, chính sách cũng cần định nghĩa **bỏ qua/ghép các deadline lồng nhau** và tránh instrument chính infrastructure hẹn giờ, logging, scheduler của aspect, gây reentrancy.

## 16. Retry, circuit breaker, bulkhead và giới hạn tài nguyên

Timeout có liên hệ với những chính sách thực thi khác nhưng không thay thế chúng.

**Retry:** nếu operation được cấp 800 ms, mỗi retry phải dùng ngân sách còn lại sau attempt trước, network latency và backoff. Không cho retry vô hạn khi task trước chưa rõ đã dừng; tránh retry thao tác có side effect chưa idempotent.

**Circuit breaker:** có thể từ chối lời gọi mới khi phụ thuộc liên tục lỗi/chậm. Nó không tự dừng những tác vụ đang chạy. Breaker open và cancellation là hai chức năng khác nhau.

**Bulkhead/concurrency limit:** hạn chế số worker, connection hoặc operation đang chạy. Nếu permit biểu diễn việc worker đang chiếm tài nguyên, phải trả permit khi **worker thật sự kết thúc**, không phải ngay lúc caller timeout.

**Queue limit:** tránh số task đang chờ tăng vô hạn. Queue bị đầy có thể khiến executor ném RejectedExecutionException đồng bộ lúc submit; đây là lỗi admission, không phải lỗi timeout khi chạy.

**Rate limiter:** chỉ kiểm soát tần suất nhận request, không đảm bảo thời gian từng request.

**Fallback:** trả dữ liệu thay thế sau timeout là chính sách nghiệp vụ, có thể che việc worker vẫn đang chạy và làm caller hiểu nhầm. Cần telemetry riêng cho fallback và xác nhận side effect.

Một hệ thống có vẻ đáp ứng nhanh vì caller luôn timeout sau 100 ms, nhưng 1.000 task nền vẫn chạy 30 giây và chiếm mọi worker. Vì vậy, nên đo cả wait-timeout và in-flight work, queue depth, task chưa dừng, late completion, cancel accepted/ignored và thời gian cleanup.

## 17. Bảo toàn ngoại lệ và kết quả theo chính sách

Advice liên quan timeout dễ làm đổi hợp đồng phương thức nếu xử lý ngoại lệ thiếu phân biệt.

| Loại tình huống | Ý nghĩa | Cách xử lý cần quyết định |
| --- | --- | --- |
| Target ném RuntimeException | Lỗi nghiệp vụ đồng bộ | Ném lại theo contract; không tự bọc thành timeout |
| Future.get ném TimeoutException | Caller chờ quá hạn | Báo timeout, tùy policy mới yêu cầu hủy |
| Caller bị InterruptedException | Chính luồng chờ bị ngắt | Truyền hoặc khôi phục cờ interrupt và thoát theo hợp đồng |
| Task thất bại; get ném ExecutionException | Kết quả công việc exceptional | Xem cause, truyền/biến đổi có chủ đích |
| Future canceled; get ném CancellationException | Trạng thái hủy future | Phân loại cancellation; không coi là thành công |
| Executor từ chối task | Lỗi admission/scheduler | Xử lý theo capacity/backpressure policy |
| Telemetry observer bị lỗi | Lỗi của instrumentation | Cô lập theo chính sách quan sát, tránh che business outcome |

Không catch Throwable rồi gán mọi lỗi là DeadlineExceeded. Khi logging/metrics advice ném exception sau khi target đã thành công, nó có thể biến một lời gọi thành công thành thất bại; cần xử lý sự cố instrumentation riêng. Khi callback observation của CompletionStage ném lỗi, dependent stage có thể thất bại dù stage gốc thành công. Các hook đo đạc nên bảo toàn semantics của future nếu không được phép thay đổi contract.

Nếu API cung cấp timeout dưới dạng checked exception, signature của lời gọi phải cho phép nó hoặc có chính sách chuyển đổi được công bố. Không lạm dụng một ngoại lệ unchecked mới để né giao kèo và làm caller không biết khi nào an toàn để retry.

## 18. Trường hợp callback và stream nhiều sự kiện

Callback không nhất thiết chạy bất đồng bộ; nó có thể được gọi ngay trong thao tác đăng ký. Một hệ thống callback một lần cần quyết định trạng thái terminal khi timeout và result cùng xảy ra gần nhau: chỉ một nhánh được công bố nếu contract yêu cầu single completion. Việc bỏ qua callback đến muộn ở caller không tự ngăn tác dụng phụ của worker.

Với stream/Publisher, timeout có thể có nhiều ý nghĩa:

- Chờ phần tử đầu tiên quá hạn.
- Khoảng lặng giữa hai phần tử vượt hạn.
- Tổng thời gian một subscription vượt hạn.
- Subscription bị hủy bởi consumer.
- Tổng lifecycle của nguồn sự kiện nhiều subscription.

Các ý nghĩa này khác nhau và phải gắn với cơ chế/hook stream tương ứng. Một around advice trên hàm trả Publisher chỉ biết đối tượng Publisher đã được tạo, chưa biết subscriber nào hay khi nào kết thúc. Không tự subscribe từ advice chỉ để đợi dữ liệu; việc này có thể kích hoạt công việc phụ và thay đổi side effect.

## 19. Những sai lầm cần tránh

**Sai lầm 1: Sau khi return mới kiểm tra elapsed rồi coi là đã enforce timeout.** Đây chỉ là hậu kiểm và có thể ném lỗi sau side effect đã hoàn thành.

**Sai lầm 2: Nhận TimeoutException từ Future.get rồi ghi “worker stopped”.** Caller chỉ hết hạn đợi; worker vẫn có thể chạy.

**Sai lầm 3: Gọi cancel(true) rồi lập tức tái cấp phát tài nguyên độc quyền.** Future canceled chưa chắc worker đã cleanup.

**Sai lầm 4: Dùng Thread.stop để ép deadline.** Không an toàn cho dữ liệu chia sẻ; ưu tiên cooperative cancellation hoặc isolation.

**Sai lầm 5: Tạo executor trong mọi lời gọi advice.** Dễ đổi thread context, lock, thứ tự side effect và gây quá tải.

**Sai lầm 6: Mỗi downstream call lại có timeout mới đầy đủ.** Làm tổng thời gian vượt deadline; phải chia ngân sách còn lại.

**Sai lầm 7: Coi timeout là rollback.** Side effect từ task hoặc hệ thống ngoài có thể vẫn thực hiện; cần idempotency và reconcile.

**Sai lầm 8: Bắt InterruptedException rồi tiếp tục vòng lặp.** Có thể vô hiệu hóa cancellation/shutdown.

**Sai lầm 9: Cho rằng orTimeout dừng supplier.** CompletableFuture có thể terminal timeout trong khi supplier vẫn chạy.

**Sai lầm 10: Chỉ theo dõi caller latency, không theo dõi task còn chạy.** Số worker treo và queue dồn có thể tăng dù mọi caller “timeout nhanh”.

## 20. Kịch bản kiểm thử quan trọng

Hãy kiểm thử các tình huống phân biệt thật rõ:

1. Target hoàn tất trước deadline, caller nhận chính giá trị và trạng thái bình thường.
2. Task chờ quá thời gian, get timeout nhưng task chưa nhận cancel: worker vẫn có thể hoàn tất sau.
3. Task hợp tác: cancel(true) được chấp nhận, worker xử lý interrupt và phát termination signal.
4. Task không hợp tác: future báo canceled, worker vẫn chạy; không báo nhầm terminated.
5. Task hoàn tất và cancel đua nhau: trạng thái caller/worker nhất quán theo contract.
6. Task bị hủy trước khi được scheduler chạy: có thể không có callback execution.
7. Caller bị interrupt trước khi timeout: phân biệt InterruptedException với TimeoutException.
8. Lời gọi I/O có timeout riêng ngắn hơn tổng deadline: dùng giá trị ngắn hơn.
9. Two nested calls và retry: tổng thời gian không vô tình reset.
10. Caller timeout sau một side effect; retry có idempotency hoặc reconciliation.
11. Logger/observer ném lỗi: không che lỗi nghiệp vụ hoặc đổi stage outcome ngoài chính sách.
12. Task cleanup chậm: trạng thái future canceled xuất hiện trước cleanup; permit được giữ đúng lúc.
13. Executor quá tải: từ chối submit, không báo nhầm là execution timeout.
14. Context thay đổi luồng: deadline/cancellation token được propagation và cleanup đúng.
15. Stream nhiều subscription: mỗi subscription có timer, cancel và terminal state riêng.

Test không nên chỉ assert một TimeoutException; phải quan sát cả **trạng thái caller** lẫn **vòng đời execution/tài nguyên**. Khi có yêu cầu cứng về thời gian và tài nguyên, cần đo cả khả năng chịu tải khi hàng loạt task không hợp tác.

## 21. Câu hỏi tự đánh giá

**Câu 1.** Around advice gọi target trực tiếp trên một thread; sau khi target trả về nó phát hiện đã chạy 2 giây dù ngân sách 1 giây. Có thực thi timeout đúng hạn không?

**Đáp án:** Không. Nó chỉ đo sau khi target kết thúc. Nếu ném timeout sau side effect có thể khiến caller retry nhầm. Muốn giới hạn thực tế cần cơ chế hủy/deadline được target và tài nguyên hỗ trợ, hoặc giới hạn thời gian chờ caller với contract rõ.

**Câu 2.** Future.get(200, MILLISECONDS) ném TimeoutException. Task đã dừng chưa?

**Đáp án:** Chưa thể kết luận. Future không tự bị cancel chỉ vì thao tác get quá hạn. Caller phải quyết định riêng về yêu cầu hủy và quan sát termination nếu cần.

**Câu 3.** Future.cancel(true) trả true, nhưng worker chạy vòng lặp CPU không kiểm tra interrupt. Có điều gì bảo đảm worker dừng?

**Đáp án:** Không. Future có thể canceled, trong khi worker vẫn chạy. Cần cooperative check hoặc cơ chế isolation/resource-native cancel phù hợp.

**Câu 4.** Deadline tổng 800 ms, bước A tiêu 650 ms. Bước B được cấp timeout bao nhiêu?

**Đáp án:** Không quá thời gian còn lại (xấp xỉ 150 ms trừ overhead, chi phí response/cleanup theo policy), không cấp lại 800 ms.

**Câu 5.** CompletableFuture đã bị orTimeout hoàn thành exceptional, nhưng worker vẫn gửi dữ liệu sau đó. Caller retry có nguy cơ gì?

**Đáp án:** Side effect trùng lặp vì timeout future không tự dừng công việc. Cần idempotency, trạng thái operation và xác nhận từ hệ thống đích.

**Câu 6.** Một advice chuyển lời gọi đồng bộ sang worker thread để timeout. Caller đang giữ lock mà worker cần. Vấn đề là gì?

**Đáp án:** Có nguy cơ deadlock: caller đợi worker, worker đợi lock của caller. Thay thread còn có thể mất ThreadLocal và thay ordering; không chuyển execution tùy tiện.

**Câu 7.** Task đã bị cancel và future.isCancelled() bằng true. Có thể dùng lại ngay tài nguyên chỉ dành riêng cho task đó không?

**Đáp án:** Chưa chắc. Cần biết worker đã dừng và hoàn tất cleanup, nhất là khi tài nguyên có thể tiếp tục bị truy cập sau khi future đã canceled.

**Câu 8.** Một stream phát dữ liệu liên tục không có onComplete bình thường. Timeout toàn subscription và timeout chờ phần tử tiếp theo có giống nhau không?

**Đáp án:** Khác nhau. Cần xác định loại timer và hook theo stream: tổng vòng đời subscription, khoảng lặng giữa các phần tử, hoặc thời gian chờ phần tử đầu tiên.

## Kết luận

Trong AOP, **giới hạn thời gian là chính sách; dừng tác vụ là năng lực của code thực thi và mô hình bất đồng bộ/tài nguyên**. Around advice có thể tạo và truyền deadline, từ chối lời gọi khi hết ngân sách, đo độ trễ, giới hạn thời gian caller chờ và yêu cầu hủy. Nhưng advice không thể tự cưỡng chế dừng an toàn mã Java không hợp tác. Hãy phân biệt timeout, yêu cầu cancel, future canceled và termination thực tế; dùng cơ chế native của tác vụ/tài nguyên để áp dụng deadline; kiểm soát context, retry, concurrency và side effect; và kiểm chứng cả kết quả caller lẫn vòng đời worker.
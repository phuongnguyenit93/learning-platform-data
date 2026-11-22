# Ranh giới bất đồng bộ trong AOP: không giữ tài nguyên của lời gọi ngắn cho công việc kéo dài

## 1. Vấn đề cốt lõi

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), một advice có thể bao quanh lời gọi hoặc lần thực thi phương thức để bổ sung logging, đo thời gian, tracing, kiểm tra quyền hoặc quản lý tài nguyên. Với phương thức đồng bộ, thời điểm phương thức kết thúc thường gần với thời điểm công việc kết thúc. Với phương thức bất đồng bộ, hai mốc này tách rời:

1. **Lời gọi ngắn:** phương thức tạo, đăng ký hoặc gửi một công việc rồi trả về rất nhanh (chẳng hạn trả về CompletionStage, Future, một đối tượng phát luồng dữ liệu, hoặc chỉ trả về void).
2. **Công việc kéo dài:** phần xử lý thực tế tiếp tục chạy ở executor, luồng khác, bộ lập lịch hoặc sau một sự kiện bên ngoài; có thể thành công, thất bại, timeout hoặc bị hủy.

**Quy tắc thiết kế:** tài nguyên có vòng đời gắn với lời gọi ngắn phải được đóng khi lời gọi đó kết thúc. Tài nguyên cần cho công việc kéo dài phải được sở hữu, mở và giải phóng theo vòng đời của chính công việc. Không kéo dài một scope chỉ vì muốn advice nhìn thấy kết quả cuối cùng.

Ví dụ tài nguyên của lời gọi ngắn: một scope ngữ cảnh đang gắn với luồng hiện tại, một guard/lock cục bộ, trạng thái đếm thời gian cho invocation, một đối tượng đại diện request chỉ hợp lệ khi lời gọi còn sống. Ví dụ tài nguyên của công việc: kết nối tới hệ thống ngoài, file handle, giao dịch riêng của tác vụ, tài nguyên dành riêng cho từng subscription. Mỗi loại có chủ sở hữu và quy tắc đóng khác nhau; không suy luận thời gian sống từ tên lớp.

## 2. Vì sao around advice thông thường dễ bị hiểu sai?

Giả sử một phương thức khởi động xử lý và lập tức trả về CompletionStage:

~~~java
CompletionStage<Report> generateReportAsync(ReportRequest request);
~~~

Đây là khai báo API minh họa; không phải một chương trình độc lập. Một bộ chặn kiểu around có thể thực hiện:

~~~text
Vào advice
  -> trước proceed(): bắt đầu lời gọi
  -> proceed(): phương thức trả về CompletionStage
  -> sau proceed(): lời gọi đã quay lại, công việc có thể chưa xong
Rời advice
  -> sau đó: CompletionStage mới hoàn thành, thất bại hoặc bị hủy
~~~

Hệ quả đối với các kiểu advice phổ biến:

| Điểm chặn AOP | Điều có thể kết luận | Điều không thể kết luận |
| --- | --- | --- |
| Before | Phương thức sắp được gọi/thực thi | Công việc bất đồng bộ đã bắt đầu hay chắc chắn sẽ hoàn thành |
| After returning | Phương thức đã trả về bình thường một giá trị, có thể là handle của công việc | Handle đó đã thành công |
| After throwing | Phương thức ném lỗi đồng bộ trong lúc được gọi/thực thi | Mọi lỗi sẽ xuất hiện sau đó trong công việc |
| After/finally | Lần thực thi được chặn đã rời khỏi phương thức | Toàn bộ tác vụ bất đồng bộ đã kết thúc |
| Around kết hợp callback hoàn tất | Có thể quan sát mốc trả về lẫn mốc hoàn tất, nếu API hỗ trợ | Callback tự động sở hữu quyền đóng mọi tài nguyên liên quan |

AOP cần xác định đúng **join point** và **vòng đời được quan sát**. Tùy kiểu weaving/proxy/interception, bộ chặn có thể áp dụng tại lời gọi, lần thực thi hoặc một điểm trong chuỗi xử lý; không phải mọi lệnh chạy bất đồng bộ đều tự động đi qua cùng join point.

## 3. Phân biệt bốn vòng đời

**Vòng đời invocation:** bắt đầu ngay khi đi vào join point, kết thúc khi phương thức trả về hoặc ném lỗi đồng bộ. Các thao tác trước/sau proceed(), lock bảo vệ đoạn gọi ngắn và scope gắn với lời gọi thuộc vòng đời này.

**Vòng đời task:** từ khi công việc được lên lịch hoặc bắt đầu thực thi cho tới lúc công việc thực tế dừng. Tài nguyên chỉ dùng trong task nên được cấp phát tại chỗ thực thi và đóng trong finally/try-with-resources của task.

**Vòng đời kết quả bất đồng bộ:** một CompletionStage hoàn tất bằng giá trị hoặc lỗi. Mốc này hữu ích cho metric và trace kết quả. Nhưng stage có thể bị hoàn tất cưỡng bức vì timeout/hủy trong khi mã nền vẫn đang chạy; hoàn tất của handle không luôn chứng minh tài nguyên nền đã được thu hồi.

**Vòng đời ngữ cảnh truyền qua ranh giới:** trace ID, correlation ID, identity tối thiểu hoặc metadata bất biến có thể được chụp tại lúc gửi việc, rồi được tái gắn một cách kiểm soát khi task thực chạy. Không được giả định ThreadLocal, transaction context, request object hay lock của luồng gọi sẽ tự đi theo task.

Đặt câu hỏi cho mỗi tài nguyên: **Ai mở? Ai dùng? Ai đóng? Đóng ở mốc nào kể cả khi có lỗi, hủy hoặc timeout?** Một tài nguyên không có câu trả lời rõ ràng là dấu hiệu cần xem lại ownership.

## 4. Sai lầm: kéo scope invocation qua công việc bất đồng bộ

Một thiết kế dễ mắc lỗi là mở tài nguyên trước proceed(), rồi giữ nó cho đến khi CompletionStage hoàn tất:

~~~text
around:
    resource = openShortLivedResource()
    stage = proceed()
    registerOnCompletion(stage, () -> resource.close())
    return stage
~~~

Đây là giả mã mô tả **phản ví dụ**, không phải một lời khuyên triển khai. Nó có thể gây ra:

- **Giữ tài nguyên quá lâu:** connection, lock, permit hoặc object của request bị giữ cả trong thời gian tác vụ đang đợi hàng đợi hoặc I/O.
- **Sai luồng:** scope đang gắn với thread A được đóng trong callback ở thread B; những abstraction có thread affinity có thể lỗi hoặc làm hỏng trạng thái.
- **Rò rỉ:** task không hoàn tất, không có callback, hoặc đường đi synchronous exception không đóng đúng tài nguyên.
- **Nghẽn hệ thống:** một request ngắn tiêu tốn tài nguyên giới hạn trong suốt công việc nhiều phút, gây cạn pool và tăng tail latency.
- **Sai ranh giới giao dịch:** tài nguyên/giao dịch của invocation bị dùng ngoài phạm vi mà nó được bảo đảm còn hợp lệ.

Chính xác hơn, **không phải mọi tài nguyên đều bắt buộc đóng ngay khi phương thức trả về**: một tài nguyên được thiết kế riêng cho task có thể sống dài. Lỗi nằm ở việc lấy tài nguyên thuộc scope ngắn và mặc nhiên biến nó thành tài nguyên thuộc scope dài.

## 5. Mẫu đúng: tách scope gọi và scope thực thi

Một thiết kế có thể có ba lớp trách nhiệm:

1. **Advice tại invocation:** chụp timestamp và metadata đủ nhỏ, xác định operation, gọi proceed() đúng một lần, xử lý lỗi đồng bộ, giải phóng mọi scope ngắn trước khi return.
2. **Chủ sở hữu task:** khi mã xử lý thực sự chạy, tự lấy tài nguyên cần dùng và đóng trong finally/try-with-resources của chính task; truyền qua ranh giới chỉ dữ liệu cần thiết, có vòng đời độc lập.
3. **Bộ quan sát completion:** nếu kiểu trả về có tín hiệu hoàn tất, đăng ký callback nhẹ để cập nhật outcome và duration. Callback không được giữ lock/connection của invocation và không được nuốt hoặc sửa lỗi nghiệp vụ ngoài ý muốn.

Ví dụ ý tưởng:

~~~text
Caller / advice            Executor / task                  Completion observer
----------------           ----------------                 -------------------
capture immutable context
open invocation scope
try:
    stage = proceed()
finally:
    close invocation scope
return stage                 start task
                             open task resource
                             try: do real work
                             finally: close task resource
                             finish stage ----------------> record outcome/duration
~~~

Ở đây lời gọi ngắn có thể đã kết thúc trước khi task bắt đầu. Nếu task không thể chạy hoặc bị từ chối lên lịch, đường báo lỗi của thao tác submit/proceed cần được xử lý riêng.

## 6. Ví dụ Java 17 chạy được: around-style wrapper quan sát CompletionStage

Ví dụ sau mô phỏng trách nhiệm của around advice bằng một hàm Java thuần để có thể biên dịch và thử nghiệm trực tiếp, không phụ thuộc vào một thư viện weaving cụ thể. Nó minh họa đúng thời điểm đóng tài nguyên của task và đúng thời điểm quan sát completion.

Tạo tệp **AsyncBoundaryDemo.java**:

~~~java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Supplier;

public final class AsyncBoundaryDemo {

    static final class TaskResource implements AutoCloseable {
        TaskResource() {
            System.out.println("RESOURCE_OPEN");
        }

        String process() {
            return "done";
        }

        @Override
        public void close() {
            System.out.println("RESOURCE_CLOSE");
        }
    }

    static <T> CompletionStage<T> observeAround(
            Supplier<? extends CompletionStage<T>> proceed) {

        long startedNanos = System.nanoTime();
        final CompletionStage<T> original;

        try {
            // Tương đương proceed(): lời gọi này chỉ trả về handle.
            original = Objects.requireNonNull(proceed.get(), "stage");
        } catch (RuntimeException | Error failure) {
            System.out.println("SYNC_FAILURE");
            throw failure;
        }

        System.out.println("METHOD_RETURNED");

        // Đo kết quả của stage, không kéo TaskResource ra khỏi task.
        return original.whenComplete((value, failure) -> {
            long elapsedNanos = System.nanoTime() - startedNanos;
            // Trong hệ thống thật, đưa elapsedNanos vào metric.
            if (failure == null) {
                System.out.println("ASYNC_SUCCESS");
            } else {
                System.out.println("ASYNC_FAILURE");
            }
        });
    }

    static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new CompletionException(e);
        }
    }

    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch mayStart = new CountDownLatch(1);

        try {
            CompletionStage<String> result = observeAround(
                    () -> CompletableFuture.supplyAsync(() -> {
                        await(mayStart);
                        // Resource thuộc task: mở khi chạy, đóng trước
                        // khi supplier hoàn thành, kể cả khi process() lỗi.
                        try (TaskResource resource = new TaskResource()) {
                            return resource.process();
                        }
                    }, executor));

            System.out.println("CALLER_CONTINUES");
            mayStart.countDown();

            // join() chỉ để chương trình demo đợi và in kết quả.
            System.out.println(
                    "RESULT=" + result.toCompletableFuture().join());
        } finally {
            mayStart.countDown();
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac AsyncBoundaryDemo.java
java AsyncBoundaryDemo
~~~

Đầu ra xác định bởi CountDownLatch và chuỗi hoàn tất:

~~~text
METHOD_RETURNED
CALLER_CONTINUES
RESOURCE_OPEN
RESOURCE_CLOSE
ASYNC_SUCCESS
RESULT=done
~~~

**Giải thích:** mayStart khiến công việc chưa thể mở TaskResource khi đoạn gọi ngắn vẫn đang chạy; sau khi người gọi tiếp tục, resource mới được tạo bên trong supplier. Try-with-resources đóng resource trước khi stage của supplier hoàn tất. Callback whenComplete quan sát kết quả của stage; nó không giữ resource nào. Không nên đặt join()/get() vào around advice ở luồng request vì như vậy vô tình biến API bất đồng bộ thành chờ đồng bộ.

Lưu ý khi vận dụng mẫu này:

- whenComplete() tạo **một stage phụ thuộc mới**. Nếu callback quan sát tự ném lỗi, stage trả về có thể bị ảnh hưởng (đặc biệt khi upstream thành công). Vì vậy callback phải nhẹ, an toàn, không ném exception ra ngoài; nếu yêu cầu giữ nguyên identity/semantics của stage gốc, cần lựa chọn kỹ cách đăng ký side effect rồi trả chính stage gốc.
- Nếu upstream đã thất bại, callback nhận Throwable biểu diễn failure; tùy đường đi có thể có CompletionException bọc nguyên nhân. Logging có thể unwrap để phân loại nhưng không được vô tình nuốt lỗi.
- Callback không nhất thiết chạy trên luồng của người gọi và có thể chạy ngay lúc đăng ký nếu stage đã hoàn tất. Không dựa vào ThreadLocal hiện tại; callback chậm có thể làm chậm luồng hoàn tất.
- Stage phụ thuộc trả về bởi whenComplete không tự động truyền hủy ngược đến tác vụ gốc. Chính sách cancellation cần được định nghĩa tại nơi sở hữu công việc.

## 7. Tách quan sát kết quả khỏi sở hữu tài nguyên

**Quan sát** và **sở hữu** là hai trách nhiệm khác nhau. Aspect quan sát completion để ghi metric không đồng nghĩa Aspect phải mở/đóng file, transaction hay network connection của task. Đặt cleanup ở đơn vị sở hữu tài nguyên sẽ giúp xử lý đầy đủ các đường thoát:

~~~java
// Đoạn minh họa đặt BÊN TRONG chính thân task.
try (InputStream input = openInput()) {
    process(input);
} finally {
    releaseTaskPermit();
}
~~~

Đoạn trên chỉ là mảnh mã, cần định nghĩa openInput(), process() và releaseTaskPermit() trong ứng dụng. Nếu releaseTaskPermit() có thể được gọi mà permit chưa được cấp, cần theo dõi quyền sở hữu bằng trạng thái cục bộ; finally không tự sửa lỗi cấp phát thất bại một phần.

Với một scope theo thread:

~~~text
invoke thread:
    attach context for invocation
    try: submit immutable context snapshot + task
    finally: detach invocation context

worker thread:
    attach reconstructed task context
    try: process task
    finally: detach worker context
~~~

Không truyền trực tiếp một scope đang mở để thread khác đóng hộ. Với tác vụ chạy lại hoặc chia nhánh, mỗi nhánh cần ngữ cảnh/scope tương ứng, tránh cùng đóng một đối tượng nhiều lần trừ khi hợp đồng API công khai cho phép.

## 8. Lựa chọn điểm hoàn tất theo kiểu API

| Kiểu API | Mốc kết thúc invocation | Cách quan sát kết quả dài hạn | Rủi ro cần xử lý |
| --- | --- | --- | --- |
| CompletionStage / CompletableFuture | Khi trả về stage | whenComplete hoặc completion hook tương đương | Lỗi callback, dependent stage, cancellation và timeout |
| Future thông thường | Khi trả về Future | Chủ sở hữu task/executor báo kết quả; có thể dùng adapter có quản lý phù hợp | Không có callback completion chuẩn; không chặn advice bằng get() |
| Publisher/lazy stream | Khi trả về đối tượng mô tả stream | Tín hiệu subscribe/onNext/onError/onComplete/cancel tại lifecycle subscription | Có thể chưa chạy cho đến lúc subscribe; nhiều subscription và hủy |
| void submit / fire-and-forget | Sau khi gửi việc | Job ID, event, task wrapper hoặc hệ thống theo dõi riêng | Không có handle để advice suy ra trạng thái cuối |
| Callback-based API | Sau khi đăng ký callback | Wrapper trên callback kết quả, tuân hợp đồng callback | Callback nhiều lần, gọi đồng bộ hay bất đồng bộ, thay đổi thứ tự |
| Chuỗi task phân nhánh | Sau khi gửi nhánh ban đầu | Quan sát stage tổng hợp/join chính thức của nghiệp vụ | Hoàn thành một nhánh không phải toàn bộ workflow hoàn thành |

Với Publisher, **không tự subscribe chỉ để đo**: hành động đó có thể kích hoạt công việc thêm một lần. Công cụ AOP phải hiểu tín hiệu kết thúc hoặc hủy của từng subscription. Với Future đơn giản, cố gọi get() trong advice vừa blocking vừa có thể gây deadlock nếu đang chiếm tài nguyên mà worker cần.

## 9. Các lỗi đồng bộ và bất đồng bộ phải có đường xử lý riêng

Một around advice có thể gặp ít nhất các tình huống sau:

- **proceed() ném trực tiếp:** hoàn trả/lan truyền lỗi đồng bộ và đóng scope invocation ngay tại đó. Không có stage hợp lệ để đăng ký observer.
- **proceed() trả stage đã thất bại:** bản thân lời gọi đã trả bình thường; observer completion nhìn thấy lỗi. Không được coi là thành công chỉ vì after-returning đã chạy.
- **Task thất bại sau khi return:** task đóng resource của mình trong finally; completion observer ghi nhận failure; lỗi nghiệp vụ phải tiếp tục tới người dùng stage theo hợp đồng API.
- **Task không được executor nhận:** việc submit có thể ném RejectedExecutionException ngay trong proceed(), tức lỗi đồng bộ; không tạo ra một workflow tưởng tượng chưa được lên lịch.
- **Task bị hủy/timeout:** biết chính xác tín hiệu nào hoàn tất handle và tín hiệu nào xác nhận mã nền thật sự dừng. Cơ chế hoàn tất exceptionally hoặc timeout trên CompletableFuture không bảo đảm code đang chạy bị ngắt hay đã cleanup.
- **Observer tự lỗi:** bảo vệ đường ghi metric/logging, tránh observer biến một tác vụ thành công thành thất bại giả hoặc che dấu nguyên nhân gốc.

Thường nên ghi riêng các trường trạng thái **INVOCATION_RETURNED**, **SCHEDULED/REJECTED**, **TASK_STARTED**, **COMPLETED/FAILED/CANCELLED**, và **RESOURCE_RELEASED** khi chúng thực sự có ý nghĩa trong kiến trúc. Không ghi trạng thái không thể chứng minh.

## 10. Timeout, cancellation và cleanup: ba sự kiện không đồng nhất

Giả sử một job xử lý I/O kéo dài. Người dùng timeout sau 2 giây, nhưng task nền cần thêm thời gian để ngừng hoặc không hỗ trợ ngắt.

- **Timeout của người chờ** nghĩa là không chờ thêm kết quả; nó không chứng minh I/O đã kết thúc.
- **Cancel của handle** có thể chỉ chuyển trạng thái của đại diện kết quả. Việc có gửi tín hiệu ngắt và có ngừng thực tế hay không tùy API/implementation.
- **Cleanup của tài nguyên thực** phải chạy tại owner/task khi mã xử lý rời phạm vi sử dụng tài nguyên.

Vì vậy không được gắn việc đóng một connection còn đang được task sử dụng vào callback timeout ở bên ngoài mà không có giao thức dừng an toàn. Nên thiết kế cooperative cancellation: task kiểm tra tín hiệu hủy, đặt timeout ở thao tác I/O thích hợp, giải phóng trong finally, rồi phát tín hiệu kết thúc thực sự. Nếu có close sớm để buộc thao tác nền dừng, đó phải là hành vi được API tài nguyên cho phép và được đồng bộ hóa.

Đặc biệt, completion của một dependent stage không nhất thiết đồng nhất với lifecycle của original task; phải đo đúng cấp độ mình đang báo cáo.

## 11. Context propagation qua ranh giới

Một Aspect thường chụp correlation ID hoặc thông tin trace ở điểm vào phương thức. Khi chuyển việc qua executor, chỉ nên chuyển **snapshot dữ liệu bất biến, tối thiểu và được phép sử dụng**. Ở worker, tạo scope mới và đóng nó tại chính worker.

**Không nên:**

- Dựa vào ThreadLocal tự được truyền từ caller sang pool thread.
- Mang đối tượng mutable request/session hoặc một transaction đang mở của caller vào background task.
- Giữ một active tracing scope thuộc thread caller và đóng tại completion callback chạy ở thread khác.
- Lưu dữ liệu nhạy cảm trong nhãn metric có cardinality lớn hoặc thông tin không cần thiết.

**Nên:**

- Chụp trace ID/correlation ID, deadline và thông tin cần thiết theo dạng rõ ràng.
- Phân biệt span của việc submit và span của task nếu hai vòng đời khác nhau; biểu diễn quan hệ cha/con hoặc liên kết theo hệ thống tracing.
- Tái gắn rồi tháo ngữ cảnh bên worker trong try/finally, ngay cả khi executor tái sử dụng thread.
- Truyền deadline như một giá trị; để task tự quản lý timeout và cleanup của nó.

## 12. Thiết kế pointcut và advice ở mức nâng cao

Để áp dụng nguyên tắc một cách nhất quán, cần xác định:

**Phạm vi pointcut.** Chọn đúng các method công khai có hợp đồng async hoặc các điểm submit/execute cần quan sát. Không quét tràn lan mọi phương thức trả về CompletionStage: chúng có thể là wrapper, helper hoặc internal callback, dẫn đến đo trùng và khiến observer kích hoạt lại chính advice.

**Loại giá trị trả về.** Không ép kiểu ngầm mọi kết quả sang CompletionStage. Nếu API có thể trả null, hãy có chính sách rõ ràng (xem null là vi phạm hợp đồng hay xử lý như trả về bình thường). Nếu phương thức trả void hoặc Future đơn giản, chọn kỹ thuật hook thích hợp từ bảng ở trên.

**Chỉ gọi proceed() một lần.** Gọi hai lần có thể submit hai task hoặc gây side effect lặp. Nếu advice chủ ý hỗ trợ retry, đó là chính sách nghiệp vụ riêng, cần bảo đảm idempotency và sở hữu resource cho từng attempt.

**Tính đúng đắn khi nested advice.** Nếu nhiều Aspect cùng gắn callback, định nghĩa rõ thứ tự và mốc thời gian đo; tránh đóng cùng resource hai lần, đếm success lặp hoặc coi hoàn tất của wrapper stage là hoàn tất của task gốc.

**Reentrancy và recursion.** Metric logger hoặc callback có thể gọi phương thức cũng khớp pointcut; cần loại trừ các điểm nội bộ hoặc dùng guard có cleanup chắc chắn. Cẩn thận với guard ThreadLocal khi callback chạy ở thread khác.

**Chi phí thực thi.** Mỗi callback tạo thêm allocation và có thể giữ tham chiếu tới object được capture tới khi stage hoàn tất. Không capture toàn bộ request, resource, đối tượng lớn hoặc closure phụ thuộc scope đã đóng. Giới hạn label metric và kích thước log.

**Tách synchronous duration và end-to-end duration.** Duration của proceed() là thời gian lời gọi trả về; duration của completion là thời gian đến tín hiệu hoàn tất. Nếu task nằm trong queue, chỉ số end-to-end còn bao gồm thời gian chờ; cần thêm dấu mốc task start nếu muốn đo thời gian xử lý thuần.

## 13. Kịch bản kiểm thử cần có

Nên kiểm thử với latch/barrier để điều khiển thời điểm, tránh dùng sleep() mong đợi thread scheduler ngẫu nhiên:

1. **Trả về trước khi task bắt đầu:** lời gọi thoát và scope invocation đã đóng; task chỉ mở tài nguyên của nó sau khi được phép chạy.
2. **Hoàn tất thành công:** observer nhìn thấy đúng một success; task resource đã được đóng; không có blocking ở advice.
3. **Lỗi đồng bộ khi submit:** scope invocation đóng; lỗi được ném tiếp; không tạo callback cho stage không tồn tại.
4. **Lỗi bất đồng bộ:** completion được ghi failure, exception còn quan sát được ở phía caller, task resource đóng qua finally.
5. **Cancel và timeout:** kiểm chứng riêng trạng thái handle, task thực dừng và mốc resource closed; không suy diễn một mốc thay cho mốc khác.
6. **Thread pool tái sử dụng thread:** context của task trước không rò sang task sau; scope attach/detach chạy đúng thread.
7. **Nested/recursive pointcut:** không đo trùng ngoài chủ ý, không gọi proceed() nhiều lần, không có vòng lặp instrumentation.
8. **Observer thất bại:** logic metric/logging không phá hỏng kết quả nghiệp vụ theo chính sách đã chọn.

Một assertion đặc biệt có giá trị: tại thời điểm method đã return nhưng task còn bị giữ bởi latch, **số invocation scope đang mở phải bằng 0**, trong khi task resource có thể chưa mở. Sau khi task thực kết thúc, **số task resource còn mở cũng phải bằng 0**.

## 14. Checklist áp dụng trong thiết kế thực tế

- Xác định ranh giới invocation, task, completion và context thay vì gộp chúng.
- Gắn open/close vào đúng owner; sử dụng finally hoặc try-with-resources tại nơi tài nguyên thật sự được sử dụng.
- Chỉ đưa qua async boundary dữ liệu đủ nhỏ, hợp lệ và độc lập về vòng đời.
- Quan sát completion qua cơ chế do chính loại API cung cấp; không blocking trong advice.
- Giữ nguyên hành vi lan truyền lỗi, cancel và semantics của return value.
- Phân biệt timeout của handle với việc task đã dừng và tài nguyên đã được đóng.
- Kiểm thử đường thành công, lỗi, timeout, cancel, từ chối submit, callback lỗi và thread reuse.

**Nguyên tắc nhớ lâu:** lời gọi trả về chỉ cho biết *lời gọi* đã kết thúc. Công việc dài hạn phải tự sở hữu tài nguyên và tự giải phóng đúng lúc; Aspect có thể quan sát mốc hoàn tất mà không buộc tài nguyên ngắn hạn sống theo nó.
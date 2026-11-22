# Đo thời gian tạo tác vụ và hoàn thành tác vụ bất đồng bộ bằng AOP

## 1. Vấn đề: một lời gọi, hai thời điểm hoàn tất khác nhau

Khi một phương thức tạo hoặc gửi tác vụ bất đồng bộ, **phương thức có thể trả về trước khi công việc thực sự hoàn thành**. Một advice kiểu *around* chỉ đo từ lúc bắt đầu lời gọi đến khi phương thức trả về sẽ phản ánh thời gian tạo/gửi tác vụ; nó không tự động phản ánh thời gian thực thi bất đồng bộ.

Ví dụ, phương thức createTask() trả về CompletionStage sau khi gửi công việc vào Executor. Luồng gọi tiếp tục xử lý việc khác, còn tác vụ có thể đang chờ trong hàng đợi, đang chạy hoặc đang chờ I/O. Đo một khoảng duy nhất dễ khiến ta kết luận sai rằng công việc “rất nhanh” chỉ vì hàm tạo tác vụ trả về nhanh.

Mục tiêu của phép đo tại ranh giới bất đồng bộ là phân biệt:

- **Thời gian tạo/gửi tác vụ (creation/submission latency):** chi phí đồng bộ của lời gọi tạo tác vụ và trả về đối tượng theo dõi.
- **Thời gian đến khi hoàn tất (end-to-end completion latency):** từ lúc bắt đầu lời gọi đến khi tín hiệu hoàn tất thành công, thất bại hoặc huỷ được quan sát.
- **Thời gian chạy thực tế (execution time):** từ lúc tác vụ *bắt đầu chạy* đến khi phần công việc được đo kết thúc. Không thể suy ra chính xác số này nếu chỉ nhìn bên ngoài lời gọi gửi tác vụ.

Các mốc thời gian cần tách rõ:

~~~text
Luồng gọi:
t0: bắt đầu advice → gọi phương thức (proceed) → t1: phương thức trả về handle
                                                         |
Luồng bất đồng bộ:             chờ hàng đợi → bắt đầu chạy → kết thúc
                                                         |
                               callback quan sát hoàn tất tại tObserved

creation = t1 - t0
completion_observed = tObserved - t0
~~~

**Lưu ý về cách đặt tên:** tObserved là lúc callback quan sát trạng thái hoàn tất, không nhất thiết chính là thời điểm lõi tác vụ kết thúc. Nếu tác vụ hoàn tất trước khi đăng ký callback, callback có thể chạy ngay khi đăng ký; khi đó tObserved muộn hơn thời điểm hoàn tất thật. Tương tự, không được coi khoảng tObserved − t1 là “thời gian CPU của tác vụ”.

Dùng **System.nanoTime()** để lấy chênh lệch thời gian đơn điệu (monotonic). Không dùng System.currentTimeMillis() để đo duration vì đồng hồ lịch có thể bị điều chỉnh. Quy đổi nano giây sang mili giây bằng cách chia cho 1_000_000.0.

## 2. Đặt phép đo vào advice tại ranh giới nào?

Trong AOP, *join point* là vị trí có thể can thiệp (chẳng hạn lời gọi/thực thi phương thức); *pointcut* chọn những vị trí cần đo; *advice* chứa hành vi đo; *weaving* hoặc cơ chế interceptor/proxy gắn hành vi ấy vào luồng gọi. Phạm vi pointcut nên nhắm đúng các API tạo/gửi tác vụ thay vì quét mọi phương thức bất đồng bộ trong hệ thống.

Một thiết kế *around advice* đúng với phương thức trả về CompletionStage đi theo thứ tự sau:

1. Ghi t0 **trước** khi chuyển quyền điều khiển đến phương thức gốc bằng proceed().
2. Nếu proceed() ném ngoại lệ ngay, ghi nhận lỗi **đồng bộ** và thời gian đến khi ném lỗi, sau đó ném tiếp ngoại lệ đó.
3. Nếu proceed() trả về bình thường, ghi t1 và metric **creation**.
4. Gắn callback **không chặn** lên CompletionStage để quan sát thành công/thất bại/huỷ.
5. Trong callback, ghi tObserved và metric **completion_observed**, kèm trạng thái kết thúc.
6. Trả về handle có hợp đồng phù hợp với kiểu trả về của API; tuyệt đối không gọi get() hoặc join() trong advice để chờ hoàn tất.

Đo riêng **creation** và **completion_observed** giúp nhận ra sự khác biệt giữa “gửi việc chậm” và “gửi việc nhanh nhưng đợi kết quả lâu”. Nếu muốn biết hàng đợi tốn bao lâu, phải bổ sung mốc **task-start** tại chính phần việc được thực thi; nếu muốn biết một chuỗi xử lý hoàn tất, cần theo dõi handle của **giai đoạn cuối** mà người gọi thực sự chờ.

### Các đường đi cần tính đúng

| Đường đi | Metric tạo tác vụ | Metric hoàn tất |
| --- | --- | --- |
| Phương thức trả CompletionStage chưa hoàn tất | Ghi ngay tại t1 | Ghi khi callback chạy |
| Stage đã hoàn tất trước khi advice gắn callback | Vẫn ghi tại t1 | Callback có thể chạy ngay trong luồng đăng ký |
| proceed() ném lỗi đồng bộ | Ghi creation-failed; không có handle hợp lệ | Không giả lập một lần hoàn tất bất đồng bộ |
| Stage hoàn tất với ngoại lệ | Ghi creation bình thường | Ghi FAILED, giữ nguyên lỗi gốc |
| Stage bị huỷ | Ghi creation bình thường | Ghi CANCELLED nếu xác định được kiểu huỷ |
| API trả về void/không cung cấp handle | Chỉ đo được việc gửi tại lời gọi | Phải instrument tác vụ bên trong, không suy đoán khi nào xong |

CompletionStage.whenComplete() nhận cả giá trị kết quả lẫn lỗi; nó **không phải thao tác chờ**. Callback có thể chạy ở luồng hoàn tất stage hoặc ngay khi đăng ký nếu stage đã xong. Vì vậy callback nên cực ngắn, không làm I/O chậm hay công việc nặng; việc ghi metric nên thông qua bộ thu thập có chi phí thấp.

## 3. Ví dụ Java 17 chạy độc lập: mô phỏng around advice

Chương trình sau dùng một lớp bọc có đúng vai trò của *around advice*: bao quanh lời gọi createTask(), đo lúc phương thức trả về, rồi gắn bộ quan sát vào CompletionStage. Đây là cách minh hoạ cơ chế AOP bằng Java thuần để có thể biên dịch trực tiếp; trong hệ thống AOP thực, pointcut và weaving có thể gắn cùng logic vào join point mà không phải tự tạo lớp bọc cho từng dịch vụ.

Tạo tệp **AsyncTimingDemo.java**:

~~~java
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class AsyncTimingDemo {
    interface TaskService {
        CompletionStage<String> createTask(String id);
    }

    static final class AsyncTaskService implements TaskService {
        private final Executor executor;
        private final CountDownLatch release;

        AsyncTaskService(Executor executor, CountDownLatch release) {
            this.executor = executor;
            this.release = release;
        }

        @Override
        public CompletionStage<String> createTask(String id) {
            return CompletableFuture.supplyAsync(() -> {
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new CompletionException(e);
                }
                return "done:" + id;
            }, executor);
        }
    }

    // Lớp bọc mô phỏng advice "around"; không cần thư viện AOP.
    static final class TimingAspect implements TaskService {
        private final TaskService target;

        TimingAspect(TaskService target) {
            this.target = target;
        }

        @Override
        public CompletionStage<String> createTask(String id) {
            long entered = System.nanoTime();
            CompletionStage<String> stage;
            try {
                stage = target.createTask(id); // tương đương proceed()
            } catch (RuntimeException | Error ex) {
                emit("creation failed", System.nanoTime() - entered,
                        id, "SYNC_ERROR");
                throw ex;
            }

            long returned = System.nanoTime();
            emit("creation", returned - entered, id, "RETURNED");
            if (stage == null) {
                throw new IllegalStateException(
                        "TaskService must return a CompletionStage");
            }

            // Không gọi join()/get(): luồng gọi không bị chặn.
            return stage.whenComplete((value, error) -> {
                long finished = System.nanoTime();
                emit("completion", finished - entered, id,
                        error == null ? "SUCCESS" : "FAILED_OR_CANCELLED");
            });
        }

        private static void emit(
                String phase, long nanos, String id, String state) {
            System.out.printf(Locale.ROOT,
                    "%s id=%s state=%s duration=%.3f ms%n",
                    phase, id, state, nanos / 1_000_000.0);
        }
    }

    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch release = new CountDownLatch(1);
        try {
            TaskService service =
                    new TimingAspect(new AsyncTaskService(executor, release));
            CompletionStage<String> result = service.createTask("A");
            System.out.println("caller: tiếp tục công việc khác");
            release.countDown();
            System.out.println(
                    "result: " + result.toCompletableFuture().join());
        } finally {
            release.countDown();
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AsyncTimingDemo.java
java AsyncTimingDemo
~~~

Ví dụ một lần chạy (các thời lượng là **biến thiên**, không phải giá trị cố định):

~~~text
creation id=A state=RETURNED duration=2.478 ms
caller: tiếp tục công việc khác
completion id=A state=SUCCESS duration=25.900 ms
result: done:A
~~~

**Vì sao phép đo đúng ý nghĩa?** CountDownLatch giữ tác vụ chưa thể kết thúc cho đến khi luồng gọi in dòng “caller”. Do đó thời gian creation được in trước, còn thời gian completion xuất hiện sau khi nhả latch. Khoảng completion bao gồm cả thời gian chờ latch; không có cơ sở kết luận rằng thân tác vụ đã chạy CPU trong toàn bộ khoảng đó. Ví dụ này đã được biên dịch với chế độ Java 17 và chạy thành công.

**Vì sao trả về stage.whenComplete()?** Đoạn minh hoạ trả về stage phụ thuộc để người gọi chỉ in kết quả sau khi callback ghi metric chạy xong. Đây là một lựa chọn có chủ đích để quan sát thứ tự trong bài thực hành. Trong advice dùng cho sản phẩm, nếu phải bảo toàn **chính xác đối tượng Future/CompletionStage trả về**, quyền huỷ hoặc kiểu trả về cụ thể như CompletableFuture, hãy đăng ký quan sát bằng stage.whenComplete(...) rồi **trả lại stage gốc**. Một stage phụ thuộc không nhất thiết giữ nguyên identity hay ngữ nghĩa huỷ của stage gốc. Bộ ghi metric cũng phải tránh ném ngoại lệ để không làm thay đổi kết quả nghiệp vụ.

### Nếu lỗi xảy ra ở đâu thì đo ở đó

- **Lỗi đồng bộ:** executor từ chối nhận tác vụ, đối số không hợp lệ hoặc phương thức ném RuntimeException trước khi trả về handle. Advice bắt, ghi creation-failed rồi ném tiếp; không đợi completion.
- **Lỗi bất đồng bộ:** đã trả về CompletionStage nhưng tác vụ thất bại về sau. Callback nhận error; không được nhầm nó với lỗi trong bước tạo tác vụ. Nếu cần phân loại nguyên nhân, hãy bóc các lớp CompletionException theo quy tắc của API và giữ dấu vết lỗi gốc.
- **Huỷ:** CompletionStage là giao diện trừu tượng; huỷ thường đi qua CompletableFuture hoặc API tác vụ cụ thể. Không nên kết luận mọi error đều là lỗi nghiệp vụ. Ví dụ gộp trạng thái FAILED_OR_CANCELLED để tránh gắn nhãn huỷ thiếu kiểm chứng.
- **Kết quả null hợp lệ:** callback có value là null vẫn có thể mang trạng thái SUCCESS nếu error là null. Tránh dùng value == null để phát hiện thất bại.

## 4. Khi API không trả CompletionStage

Không phải tác vụ nào cũng cung cấp CompletionStage. Với **Executor.execute(Runnable)**, bản thân execute() trả về void và thường chỉ đảm bảo đã nhận hoặc từ chối việc gửi. Một around advice đặt quanh execute() chỉ đo việc gửi tác vụ. Để quan sát lúc tác vụ **bắt đầu và kết thúc**, cần bọc Runnable khi gửi:

~~~java
long submitted = System.nanoTime();
Runnable observed = () -> {
    long started = System.nanoTime();
    try {
        originalRunnable.run();
    } finally {
        long finished = System.nanoTime();
        recordQueueDelay(started - submitted);
        recordExecutionTime(finished - started);
        recordTotalTime(finished - submitted);
    }
};
executor.execute(observed);
~~~

Đây là đoạn **minh hoạ**, giả định originalRunnable, executor và các hàm record... được cung cấp từ bên ngoài; nó không phải chương trình Java độc lập. Việc bọc tác vụ phải thực hiện ở đúng đường gửi vào executor, và tách lỗi “bị từ chối ngay khi gửi” khỏi lỗi “xảy ra khi run()”. Nếu hàng đợi huỷ tác vụ trước khi run() được gọi, khối finally này không chạy: muốn đếm chính xác các lần huỷ trước thực thi phải quan sát thêm vòng đời Future/tác vụ của executor.

Với **ExecutorService.submit(Callable)** trả về Future nhưng không phải CompletionStage, không nên mở một luồng chỉ để Future.get() chờ; cách đó tiêu tốn thêm tài nguyên và có thể dẫn đến nghẽn. Có thể bọc Callable hoặc dùng cơ chế theo dõi vòng đời của tác vụ/FutureTask phù hợp. Khi một Future kết thúc, cần phân biệt thành công, lỗi, huỷ và trường hợp đã bị loại khỏi hàng đợi.

Với tác vụ kiểu **fire-and-forget**, nếu chỉ giữ một lời gọi gửi việc và không có handle, AOP bên ngoài không thể suy ra “toàn bộ quá trình hoàn tất” từ lúc phương thức gửi việc trả về. Cần điểm quan sát bên trong tác vụ hoặc tín hiệu kết thúc có tương quan (correlation ID).

## 5. Đo nhiều giai đoạn và ranh giới chuỗi bất đồng bộ

Giả sử API tạo tác vụ A, sau đó kết hợp các bước B và C. Nếu phương thức trả về handle chỉ đại diện cho A, callback của advice sẽ báo A hoàn tất ngay cả khi B và C vẫn đang chạy. Nếu API trả về **stage cuối cùng của chuỗi**, callback đo được thời điểm chuỗi đó kết thúc theo hợp đồng. Các bước tách rời, không nằm trong stage trả về, không tự động thuộc phạm vi đo.

Có ba nhóm mốc thời gian thường cần ghi:

| Khoảng đo | Bắt đầu | Kết thúc | Câu hỏi trả lời |
| --- | --- | --- | --- |
| submission | Vào advice | proceed() trả về | Tạo/gửi công việc có chậm không? |
| queue wait | Gửi tác vụ | Tác vụ thực sự bắt đầu | Việc bị chờ trong hàng đợi bao lâu? |
| execution | Tác vụ bắt đầu | Phần công việc được đo kết thúc | Thân tác vụ chạy trong bao lâu? |
| end-to-end observed | Vào advice | Callback trên handle cam kết kết thúc | Người gọi chờ đến tín hiệu hoàn tất bao lâu? |

Không suy diễn **end-to-end = submission + queue wait + execution** một cách máy móc: các mốc có thể trùng lấn, callback có thể chạy trễ, và chuỗi stage còn có thời gian I/O hoặc các bước bổ sung. Khi phân tích nút thắt hiệu năng, nên ghi các mốc thực tế tại đúng nơi phát sinh.

Nếu một CompletionStage đã kết thúc trước khi advice đăng ký callback, metric completion_observed đo **độ trễ phát hiện** (thời điểm callback được thực thi), không hồi cứu được mốc hoàn thành tuyệt đối của stage từ API này. Muốn chính xác hơn phải instrument nguồn phát tín hiệu hoàn tất.

## 6. Thiết kế AOP đáng tin trong ứng dụng thực

**Chọn pointcut:** nhắm đúng các phương thức chịu trách nhiệm tạo/gửi tác vụ, có hợp đồng trả về xác định. Một pointcut quá rộng có thể đo lặp cùng công việc ở nhiều lớp bọc, tạo số liệu trùng và tăng chi phí. Phân biệt join point “phương thức gửi việc” với join point “thân Runnable/Callable chạy” để tránh gộp hai pha.

**Giữ hợp đồng nghiệp vụ:** lời gọi proceed() chỉ thực hiện **một lần**. Advice phải trả về đúng loại đối tượng mà người gọi mong đợi; không tự chặn chờ, thay đổi exception, nuốt lỗi, đổi luồng thực thi hoặc biến timeout nghiệp vụ thành timeout quan sát. Nếu callback ghi metric gặp lỗi, phần ghi metric không được làm hỏng kết quả tác vụ.

**Giữ ngữ cảnh giữa các luồng:** ID yêu cầu/trace và nhãn metric nên được chụp lại trước khi rời luồng gọi; không giả định ThreadLocal ở luồng callback giống ThreadLocal ở luồng submit. Cẩn thận nếu context dùng tài nguyên cần giải phóng khi hoàn tất hoặc khi bị huỷ.

**Ghi metric có thể vận hành:** dùng histogram/timer cho creation và completion, bộ đếm cho SUCCESS, FAILED, CANCELLED và SYNC_ERROR. Đặt tên nhất quán, chẳng hạn async.task.creation.duration và async.task.completion.duration; nhãn nên có số lượng giá trị hữu hạn như loại tác vụ hoặc endpoint. Không đưa ID request độc nhất, tên người dùng hoặc toàn bộ thông báo ngoại lệ vào label vì sẽ làm bùng nổ số chuỗi thời gian metric.

**Hạn chế observer gây nhiễu:** callback khi hoàn tất có thể chạy ngay trên luồng thực thi tác vụ; logging đồng bộ, ghi file hoặc gửi mạng trong callback làm trễ luồng đó. Khi cần đẩy dữ liệu ra hệ thống thu thập, ưu tiên ghi nhanh vào bộ đệm; nếu dùng callback chuyển executor, phải ghi rõ metric đo thời điểm callback thực thi hay thời điểm tín hiệu hoàn tất.

**Hiểu giới hạn công cụ AOP:** advice chỉ quan sát join point thực sự được cơ chế weaving/interception áp dụng. Những lời gọi nội bộ bỏ qua interceptor hoặc các tác vụ tạo ở nơi khác sẽ không xuất hiện trong số đo trừ khi cơ chế AOP tương ứng bao phủ chúng. Không coi vắng metric là bằng chứng tác vụ không chạy.

## 7. Kiểm thử và lỗi thường gặp

Có thể xác minh phép đo bằng bốn tình huống cụ thể:

1. **Chặn tác vụ bằng latch:** phương thức trả handle nhanh, latch chưa mở thì không được có metric completion; mở latch thì phải có đúng một lần completion.
2. **Ném lỗi ngay khi gửi:** thay executor bằng loại từ chối việc gửi; phải có creation-failed, ngoại lệ được truyền tiếp và không có báo cáo completion giả.
3. **Hoàn tất bất đồng bộ với lỗi:** trả một CompletableFuture được completeExceptionally; phải có creation rồi một completion lỗi, người gọi vẫn nhận được thất bại.
4. **Stage đã hoàn tất hoặc bị huỷ:** callback vẫn phải quan sát kết thúc; trạng thái lỗi/huỷ được phân loại dựa trên dữ liệu thực của API, và không giả định callback sẽ chạy trên luồng worker.

Các lỗi phổ biến cần tránh:

- **Đặt đồng hồ dừng ngay sau proceed() rồi gọi số đó là thời gian chạy tác vụ:** chỉ đo được đường gọi đồng bộ.
- **Dùng join()/get() trong advice:** biến lời gọi bất đồng bộ thành chờ đồng bộ và bóp méo cả hành vi lẫn metric.
- **Coi callback là mốc thực thi CPU:** khoảng end-to-end có cả chờ hàng đợi, I/O, độ trễ callback và các giai đoạn phụ.
- **Dùng currentTimeMillis() cho elapsed:** có thể sai khi đồng hồ hệ thống đổi giờ; dùng nanoTime() để lấy hiệu.
- **Trả về một Future khác mà không xem xét hợp đồng:** có thể thay đổi khả năng huỷ, loại trả về và cách nhận ngoại lệ.
- **Gắn nhiều observer ở nhiều lớp aspect:** dễ đếm cùng một tác vụ nhiều lần.
- **Đếm thành công bằng cách kiểm tra result != null:** kết quả null vẫn có thể thành công.

Một phép đo AOP có ích phải trả lời chính xác **đã đo ranh giới nào**: trả về sau khi gửi công việc, bắt đầu/chạy xong thân tác vụ, hay nhận tín hiệu hoàn tất trên handle được trả về. Đặt tên metric và vị trí advice theo ranh giới đó giúp so sánh số liệu đúng, phát hiện nghẽn ở đúng pha và giữ nguyên bản chất bất đồng bộ của chương trình.

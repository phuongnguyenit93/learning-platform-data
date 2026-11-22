# Kiểm thử các cuộc đua giữa hoàn tất thường và hết hạn

## 1. Hai cách kết thúc cùng cạnh tranh trên một CompletableFuture

Một CompletableFuture<T> chỉ có thể nhận một kết quả cuối cùng: hoàn tất bình thường với một giá trị, hoàn tất exceptional với một lỗi, hoặc bị hủy. Khi một tác vụ có deadline, hai sự kiện có thể xảy ra gần như cùng lúc:

- Tác vụ hoàn tất bình thường và gọi complete(value).
- Bộ đếm thời gian hết hạn và yêu cầu hoàn tất future bằng timeout.

Đây là một cuộc đua (race). Bên nào hoàn tất future thành công trước sẽ quyết định trạng thái cuối cùng. Các lần hoàn tất đến sau không ghi đè được kết quả đã được chốt.

Java 9 bổ sung hai phương thức trên CompletableFuture để gắn hành vi timeout trực tiếp vào future:

- orTimeout(timeout, unit): nếu future chưa hoàn tất khi hết thời gian, hoàn tất nó exceptional bằng TimeoutException.
- completeOnTimeout(value, timeout, unit): nếu future chưa hoàn tất khi hết thời gian, hoàn tất nó bình thường bằng giá trị dự phòng.

Hai phương thức đều trả về chính đối tượng CompletableFuture được gọi. Chúng thay đổi trạng thái của future đó, vì vậy mọi nơi đang dùng chung future đều quan sát cùng kết quả thắng cuộc đua.

## 2. orTimeout: timeout thắng thì future hoàn tất exceptional

Ví dụ:

~~~java
CompletableFuture<String> result = new CompletableFuture<>();

result.orTimeout(2, TimeUnit.SECONDS);
~~~

Nếu một tác vụ gọi result.complete("done") trước khi bộ đếm thời gian thắng, future hoàn tất bình thường. Nếu deadline thắng trước, future hoàn tất exceptional với TimeoutException.

Khi timeout đã thắng:

- result.isDone() trả về true.
- result.isCompletedExceptionally() trả về true.
- result.isCancelled() trả về false; timeout không phải cancellation.
- result.join() ném CompletionException, có TimeoutException là nguyên nhân.
- result.complete("late") trả về false, vì future đã có kết quả cuối cùng.

Với get(), lỗi exceptional được bọc trong ExecutionException; kiểm tra nguyên nhân bằng getCause().

orTimeout không trả một future mới để biểu diễn timeout. Nó gắn timeout vào chính future hiện tại và trả lại future đó. Đây là điểm cần lưu ý khi nhiều thành phần cùng chia sẻ một CompletableFuture.

## 3. completeOnTimeout: timeout thắng thì dùng giá trị dự phòng

Nếu ứng dụng muốn dùng giá trị mặc định khi hết thời gian, dùng:

~~~java
CompletableFuture<String> result = new CompletableFuture<>();

result.completeOnTimeout("fallback", 2, TimeUnit.SECONDS);
~~~

Nếu future chưa hoàn tất khi timeout xảy ra, nó hoàn tất bình thường bằng "fallback". Khi đó:

- join() trả về giá trị dự phòng.
- isDone() là true.
- isCompletedExceptionally() là false.
- Một lần complete("late") sau đó trả về false.

Giá trị dự phòng có thể là null vì CompletableFuture cho phép hoàn tất bình thường bằng null. Hãy chỉ dùng null nếu hợp đồng API của ứng dụng xem null là một kết quả hợp lệ.

completeOnTimeout cũng thay đổi chính future được gọi. Nếu nhiều thành phần dùng chung future, tất cả sẽ quan sát giá trị dự phòng khi timeout thắng.

## 4. Cuộc đua: ai hoàn tất trước sẽ thắng

Các lời gọi hoàn tất của CompletableFuture được phối hợp nguyên tử. Khi có nhiều bên cùng thử hoàn tất một future, chỉ một bên có thể chuyển trạng thái future từ chưa hoàn tất sang hoàn tất.

Ví dụ về hoàn tất thủ công:

~~~java
CompletableFuture<String> future = new CompletableFuture<>();

boolean first = future.complete("normal");
boolean second = future.complete("late");

System.out.println(first);  // true
System.out.println(second); // false
System.out.println(future.join()); // normal
~~~

Trong cuộc đua thật giữa complete và timeout:

- Nếu complete(value) thắng, nó trả true; timeout đến sau không thay đổi kết quả.
- Nếu timeout thắng, future đã hoàn tất theo chính sách timeout; complete(value) trả false.
- Nếu một bên gọi completeExceptionally hoặc cancel trước, các lần hoàn tất khác cũng không thể thay đổi trạng thái đã chốt.

Không được giả định bên thắng chỉ dựa trên thời gian đặt lịch. Hai tác vụ có cùng deadline có thể được bộ lập lịch thực thi theo thứ tự khác nhau tùy tải hệ thống, độ trễ thread và thời điểm thực tế.

## 5. Timeout không tự dừng công việc nền

Giả sử future được tạo từ một tác vụ:

~~~java
CompletableFuture<Result> request =
        CompletableFuture.supplyAsync(this::callRemoteService);

request.orTimeout(2, TimeUnit.SECONDS);
~~~

Nếu timeout xảy ra sau 2 giây, future request hoàn tất exceptional. Tuy nhiên, lời gọi callRemoteService không tự động bị dừng chỉ vì future đã timeout. Tác vụ nền có thể vẫn đang chạy, tiếp tục sử dụng CPU, giữ socket hoặc tạo side effect.

Tương tự, completeOnTimeout có thể trả giá trị dự phòng cho caller trong khi tác vụ nền vẫn tiếp tục. Khi tác vụ nền hoàn tất muộn, kết quả của nó không ghi đè được future đã hoàn tất bằng fallback.

Nếu cần dừng công việc thật sự, phải thiết kế cancellation riêng: giữ handle của tác vụ/executor, dùng timeout hoặc cancellation token mà công việc có thể kiểm tra, đóng tài nguyên phù hợp và xử lý trạng thái dừng. Timeout của CompletableFuture chỉ quyết định kết quả của future; nó không phải cơ chế hủy phổ quát cho mọi tác vụ.

## 6. get(timeout, unit) khác orTimeout

Hai cách viết sau có hành vi khác nhau:

~~~java
value = future.get(2, TimeUnit.SECONDS);
~~~

và:

~~~java
future.orTimeout(2, TimeUnit.SECONDS);
value = future.get();
~~~

get(timeout, unit) chỉ giới hạn thời gian thread gọi chờ kết quả. Nếu thời gian chờ hết, chính lời gọi get ném TimeoutException; bản thân future vẫn có thể tiếp tục pending và hoàn tất sau đó.

Ngược lại, orTimeout đặt timeout lên future. Khi timeout thắng, future chuyển sang trạng thái exceptional với TimeoutException. Tất cả consumer đang quan sát cùng future sẽ thấy trạng thái đó.

| API | Điều gì bị timeout? | Future gốc có bị hoàn tất bởi timeout không? |
|---|---|---|
| get(timeout, unit) | Lần chờ của thread gọi | Không |
| orTimeout(timeout, unit) | Kết quả của chính future | Có, exceptional |
| completeOnTimeout(value, timeout, unit) | Kết quả của chính future | Có, bình thường với fallback |

Nếu chỉ một caller cần deadline riêng trong khi các caller khác vẫn muốn chờ tác vụ gốc, không nên áp timeout trực tiếp lên future dùng chung.

## 7. Dùng copy() để cô lập timeout theo caller

Java 9 bổ sung CompletableFuture.copy(). Phương thức này tạo một future khác phản ánh kết quả của future nguồn. Có thể áp timeout lên bản sao để giới hạn thời gian chờ của một caller mà không làm future nguồn hoàn tất do timeout đó:

~~~java
CompletableFuture<Result> source = callRemoteService();

CompletableFuture<Result> callerView =
        source.copy().orTimeout(2, TimeUnit.SECONDS);
~~~

Nếu callerView timeout, source vẫn có thể pending và hoàn tất sau đó. Bản sao tiếp tục giữ trạng thái timeout của riêng nó; kết quả muộn của nguồn không ghi đè được bản sao đã hoàn tất.

copy() không nhân bản công việc nền và cũng không hủy nguồn. Nó tạo một future riêng để quan sát kết quả. Nếu nguồn hoàn tất trước, kết quả hoặc lỗi của nguồn được phản ánh sang bản sao.

Dùng cách này khi deadline thuộc về một caller hoặc một nhánh xử lý riêng. Nếu timeout là chính sách của toàn bộ tác vụ và mọi consumer phải nhận cùng một timeout, có thể áp orTimeout trực tiếp lên future gốc.

## 8. Kiểm thử cuộc đua mà không phụ thuộc bên thắng

Một test tốt cần kiểm tra cả hai tình huống có kiểm soát:

1. Hoàn tất bình thường trước timeout: kết quả bình thường được giữ lại.
2. Timeout trước khi có kết quả: timeout được giữ lại và completion muộn bị từ chối.

Sau đó có thể tạo cuộc đua thật với hai tác vụ được lên lịch gần cùng thời điểm. Không nên assert một bên cụ thể luôn thắng; thay vào đó, xác minh tính nhất quán: nếu complete trả true thì kết quả là giá trị bình thường, còn nếu timeout thắng thì kết quả là timeout. Chỉ có một trạng thái cuối cùng.

Tránh dùng Thread.sleep làm cơ chế đồng bộ chính của test. Dùng CountDownLatch, CyclicBarrier, ScheduledExecutorService hoặc các primitive đồng bộ phù hợp để điều khiển thời điểm bắt đầu. Timeout là cơ chế dựa trên scheduler, không phải đồng hồ thời gian thực cứng; test nên có khoảng chờ đủ rộng và không phụ thuộc vào độ chính xác đến từng millisecond.

## 9. Ví dụ Java chạy được: hai bên thắng và 20 cuộc đua

Chương trình sau kiểm tra hoàn tất thường, timeout exceptional, fallback bình thường, cô lập timeout bằng copy() và 20 lần cạnh tranh giữa completion thủ công với timeout.

Phần kiểm thử race không yêu cầu timeout hay completion thủ công phải thắng một tỷ lệ cụ thể. Nó chỉ xác minh rằng giá trị cuối cùng luôn khớp với bên đã hoàn tất future thành công.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class CompletableFutureTimeoutRaceDemo {
    public static void main(String[] args) throws Exception {
        normalCompletionWins();
        timeoutWins();
        fallbackWins();
        timeoutOnCopyDoesNotCompleteSource();
        checkCompletionRace();
    }

    private static void normalCompletionWins() {
        CompletableFuture<String> future = new CompletableFuture<>();
        future.orTimeout(1, TimeUnit.MINUTES);
        boolean accepted = future.complete("normal");
        System.out.println("normal completion accepted = " + accepted);
        System.out.println("normal result = " + future.join());
    }

    private static void timeoutWins() {
        CompletableFuture<String> future = new CompletableFuture<>();
        future.orTimeout(1, TimeUnit.MILLISECONDS);
        try {
            future.join();
        } catch (CompletionException ex) {
            System.out.println("timeout cause = "
                    + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("late completion accepted = "
                + future.complete("late"));
        System.out.println("timeout is cancelled = " + future.isCancelled());
    }

    private static void fallbackWins() {
        CompletableFuture<String> future = new CompletableFuture<>();
        future.completeOnTimeout("fallback", 1, TimeUnit.MILLISECONDS);
        System.out.println("fallback result = " + future.join());
        System.out.println("late completion accepted after fallback = "
                + future.complete("late"));
    }

    private static void timeoutOnCopyDoesNotCompleteSource() {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> timedCopy =
                source.copy().orTimeout(1, TimeUnit.MILLISECONDS);
        try {
            timedCopy.join();
        } catch (CompletionException ex) {
            System.out.println("copy timeout cause = "
                    + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("source done after copy timeout = " + source.isDone());
        source.complete("source result");
        System.out.println("source result = " + source.join());
    }

    private static void checkCompletionRace() throws Exception {
        ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(2);
        int attempts = 20;
        try {
            for (int i = 0; i < attempts; i++) {
                CompletableFuture<String> future = new CompletableFuture<>();
                future.orTimeout(2, TimeUnit.MILLISECONDS);
                AtomicBoolean manualAccepted = new AtomicBoolean();
                java.util.concurrent.ScheduledFuture<?> contender = scheduler.schedule(
                        () -> manualAccepted.set(future.complete("manual")),
                        2, TimeUnit.MILLISECONDS);

                String outcome;
                try {
                    outcome = future.join();
                } catch (CompletionException ex) {
                    if (!(ex.getCause() instanceof TimeoutException)) {
                        throw ex;
                    }
                    outcome = "timeout";
                }
                contender.get(1, TimeUnit.SECONDS);
                if (manualAccepted.get() != "manual".equals(outcome)) {
                    throw new AssertionError("Completion winner was inconsistent");
                }
            }
        } finally {
            scheduler.shutdownNow();
        }
        System.out.println("races checked = " + attempts);
        System.out.println("single winner invariant = true");
    }
}
~~~

Lưu mã nguồn trong CompletableFutureTimeoutRaceDemo.java, biên dịch và chạy bằng Java 9 trở lên:

~~~bash
javac --release 9 -Xlint:all CompletableFutureTimeoutRaceDemo.java
java CompletableFutureTimeoutRaceDemo
~~~

Kết quả:

~~~text
normal completion accepted = true
normal result = normal
timeout cause = TimeoutException
late completion accepted = false
timeout is cancelled = false
fallback result = fallback
late completion accepted after fallback = false
copy timeout cause = TimeoutException
source done after copy timeout = false
source result = source result
races checked = 20
single winner invariant = true
~~~

Hai tình huống đầu tiên được điều khiển để xác nhận lần lượt completion thường và timeout thắng. Vòng lặp cuối tạo 20 cuộc đua gần đồng thời; bên thắng có thể thay đổi theo lịch thực thi, nhưng kiểm tra bảo đảm kết quả luôn nhất quán với lần hoàn tất thành công. Chương trình đã được biên dịch bằng javac --release 9 -Xlint:all và stdout được kiểm tra.

## 10. Những lỗi thường gặp

- Cho rằng timeout sẽ hủy tác vụ nền: orTimeout và completeOnTimeout chỉ hoàn tất future; chúng không tự dừng công việc đang chạy.
- Áp timeout lên future dùng chung: mọi consumer của future đó đều thấy trạng thái timeout. Dùng copy() nếu deadline chỉ thuộc về một caller.
- Nhầm get(timeout, unit) với orTimeout: một bên giới hạn lần chờ, bên kia thay đổi trạng thái future.
- Giả định completion muộn ghi đè fallback: khi timeout đã thắng, complete trả false và kết quả đã chốt không đổi.
- Coi timeout là cancellation: future timeout exceptional nhưng isCancelled() vẫn false.
- Assert một winner cố định trong race test: thứ tự chạy phụ thuộc scheduler. Hãy assert bất biến một bên thắng và kết quả phù hợp.
- Dùng sleep làm đồng bộ: sleep không bảo đảm thứ tự giữa thread và timer. Dùng latch/barrier hoặc scheduler để phối hợp.
- Quên xử lý lỗi bọc: join() bọc lỗi trong CompletionException; kiểm tra getCause() để nhận diện TimeoutException.
- Không đóng executor do test tạo: gọi shutdown hoặc shutdownNow trong finally để tránh giữ thread sau khi test kết thúc.

## 11. Checklist khi review

1. Deadline áp dụng cho toàn bộ tác vụ hay chỉ một caller?
2. Cần timeout exceptional bằng orTimeout hay fallback bình thường bằng completeOnTimeout?
3. Future có được chia sẻ cho nhiều consumer không?
4. Nếu timeout thắng, công việc nền có cần dừng riêng không?
5. Mã có xử lý completion muộn và giá trị trả về false từ complete không?
6. Có phân biệt get(timeout, unit) với timeout được gắn vào future không?
7. Race test có chấp nhận cả hai winner và kiểm tra bất biến một lần hoàn tất không?
8. Executor và tài nguyên kiểm thử có được đóng trong mọi đường đi không?

orTimeout và completeOnTimeout giải quyết hai chính sách khác nhau khi deadline thắng. Dù chọn chính sách nào, kết quả future chỉ được chốt một lần: completion thường, timeout hoặc một lỗi khác cạnh tranh để trở thành trạng thái cuối cùng.
# ExecutorCompletionService và thu kết quả theo thứ tự hoàn tất

## 1. Khi thứ tự gửi không phải thứ tự cần xử lý

Giả sử ứng dụng gửi ba công việc độc lập:

```text
Thứ tự gửi:        A -> B -> C
Thứ tự hoàn tất:   B -> C -> A
```

Nếu lưu ba Future vào danh sách rồi gọi `A.get()`, `B.get()`, `C.get()`, nơi thu kết quả phải chờ A trước. B và C có thể đã sẵn sàng nhưng chưa được xử lý.

Cách đó không sai nếu ứng dụng muốn giữ thứ tự đầu vào. Nhưng nếu cần hiển thị, lưu hoặc xử lý mỗi kết quả ngay khi sẵn sàng, cần tách **thứ tự gửi công việc** khỏi **thứ tự thu kết quả**.

`java.util.concurrent.ExecutorCompletionService<V>` hỗ trợ điều này. Nó sử dụng một executor để chạy việc và một hàng đợi để đưa các Future đã hoàn tất tới bên thu nhận.

API này có từ Java 5 và vẫn áp dụng trong Java hiện hành. Các ví dụ hoàn chỉnh trong bài chạy trên Java 17+.

## 2. Ba thành phần trong mô hình

| Thành phần | Trách nhiệm |
|---|---|
| `Executor` hoặc `ExecutorService` | Tổ chức chạy tác vụ |
| `CompletionService<V>` | Hợp đồng gửi tác vụ và lấy Future hoàn tất |
| `ExecutorCompletionService<V>` | Triển khai hợp đồng bằng executor được cung cấp và hàng đợi hoàn tất |

Khai báo minh họa:

```java
ExecutorService pool = Executors.newFixedThreadPool(4);
CompletionService<Result> completions =
        new ExecutorCompletionService<>(pool);
```

`Result` là kiểu dữ liệu của ứng dụng; đây chưa phải chương trình độc lập.

Completion service **không tạo một nhóm luồng riêng** trong lời khai báo này. Nó chuyển công việc tới `pool` đã được cung cấp.

Có hai nơi chờ khác nhau cần phân biệt:

```text
submit
   -> executor nhận việc
   -> hàng đợi công việc chưa chạy của executor, nếu có
   -> luồng thực hiện
   -> hàng đợi Future đã hoàn tất của completion service
   -> bên thu kết quả
```

Hàng đợi đầu chứa việc chờ thực thi. Hàng đợi cuối chứa kết quả đã sẵn sàng để được thu nhận. Không dùng kích thước của một hàng đợi để suy ra tình trạng của hàng đợi còn lại.

Cơ chế chuyển kết quả được mô tả trong [ExecutorCompletionService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html).

## 3. submit trả Future, take lấy một Future đã hoàn tất

Ví dụ minh họa:

```java
Future<Result> handle = completions.submit(task);
Future<Result> completed = completions.take();
Result result = completed.get();
```

`task` là một `Callable<Result>` của ứng dụng.

Hai biến Future có mục đích sử dụng khác nhau:

- `handle` được giữ ngay sau khi gửi để quản lý công việc cụ thể, chẳng hạn yêu cầu hủy.
- `completed` được lấy từ hàng đợi hoàn tất khi một công việc đã sẵn sàng.
- `completed.get()` đọc kết quả hoặc phát hiện thất bại/hủy của công việc ấy.

Nếu có nhiều việc đã gửi, `completed` không nhất thiết là Future của tác vụ đầu tiên được gửi.

`take()` **lấy ra và loại khỏi hàng đợi** một Future đã hoàn tất. Nếu chưa có phần tử, luồng gọi nó chờ và có thể bị ngắt. Nó không trả kết quả nghiệp vụ trực tiếp.

### Đã hoàn tất chưa chắc thành công

Future được thu nhận vẫn có thể đại diện cho tác vụ thất bại hoặc bị hủy. Vì vậy vẫn cần gọi `get()` và xử lý trạng thái phù hợp:

- Thành công: nhận giá trị.
- Thất bại: `ExecutionException`, xem nguyên nhân qua `getCause()`.
- Hủy: `CancellationException`.

`take()` không ném lỗi nghiệp vụ của thân `Callable` thay cho `get()`. Nó chỉ chịu trách nhiệm chờ và lấy đối tượng hoàn tất.

## 4. Chọn take hay poll

| Phương thức | Khi chưa có kết quả để lấy |
|---|---|
| `take()` | Chờ tới khi có phần tử, hoặc bị ngắt |
| `poll()` | Trả `null` ngay |
| `poll(timeout, unit)` | Chờ tối đa khoảng yêu cầu; hết hạn trả `null` |

Khác biệt dễ nhầm: `poll(timeout, unit)` hết thời gian chờ thì **trả null**, còn `future.get(timeout, unit)` hết hạn thì ném `TimeoutException`.

Ví dụ:

```java
Future<Result> completed =
        completions.poll(500, TimeUnit.MILLISECONDS);

if (completed == null) {
    reportNoResultYet();
} else {
    useResult(completed.get());
}
```

Đây là mã minh họa; các hàm xử lý do ứng dụng cung cấp và nơi gọi vẫn phải xử lý ngoại lệ.

`null` từ `poll` có nghĩa chưa lấy được Future nào, không phải kết quả của một tác vụ là `null`. Một Callable có thể trả `null` thành công; khi ấy `poll` trả một Future khác null, rồi `get()` của nó trả null.

Không liên tục gọi `poll()` trong vòng lặp rỗng. Nếu chưa có việc hữu ích khác để làm, dùng `take()` hoặc poll có thời hạn để tránh quay bận.

Các chữ ký được quy định trong [CompletionService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletionService.html).

## 5. Chương trình Java 17+: B được thu trước A

Ví dụ dưới đây giữ A ở một chốt đồng bộ cho tới khi nơi gọi đã thu B. Nhờ đó kết quả B trước A là điều kiện được thiết lập rõ, không dựa vào hai khoảng sleep có thể chạy lệch nhau.

Lưu thành **`CompletionOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletionService;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CompletionOrderDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CompletionService<String> completions =
                new ExecutorCompletionService<>(pool);
        List<Future<String>> submitted = new ArrayList<>();
        CountDownLatch aStarted = new CountDownLatch(1);
        CountDownLatch releaseA = new CountDownLatch(1);

        try {
            submitted.add(completions.submit(() -> {
                aStarted.countDown();
                releaseA.await();
                return "A";
            }));

            aStarted.await();

            System.out.println(
                    "before B, poll empty: "
                    + (completions.poll() == null));

            submitted.add(completions.submit(() -> "B"));

            Future<String> first =
                    nextCompleted(completions);
            System.out.println("first completed: " + first.get());

            releaseA.countDown();

            Future<String> second =
                    nextCompleted(completions);
            System.out.println("second completed: " + second.get());

            submitted.add(completions.submit(() -> {
                throw new IllegalArgumentException("invalid C");
            }));

            Future<String> failed =
                    nextCompleted(completions);

            try {
                failed.get();
            } catch (ExecutionException e) {
                Throwable cause = e.getCause();
                System.out.println(
                        "failure: " + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
            }
        } finally {
            releaseA.countDown();
            for (Future<String> future : submitted) {
                if (!future.isDone()) {
                    future.cancel(true);
                }
            }

            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Executor did not terminate");
                    }
                }
            } catch (InterruptedException e) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
                throw e;
            }
        }
    }

    private static <T> Future<T> nextCompleted(
            CompletionService<T> completions)
            throws InterruptedException {
        Future<T> completed =
                completions.poll(5, TimeUnit.SECONDS);
        if (completed == null) {
            throw new IllegalStateException(
                    "No completion within the wait limit");
        }
        return completed;
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CompletionOrderDemo.java
java CompletionOrderDemo
```

Stdout chính xác:

```text
before B, poll empty: true
first completed: B
second completed: A
failure: IllegalArgumentException: invalid C
```

### Đọc diễn biến

1. A được gửi trước và thông báo đã bắt đầu.
2. A chưa thể hoàn tất vì `releaseA` còn đóng, nên lần poll đầu không có phần tử.
3. B được gửi sau, nhưng có luồng thứ hai để thực thi; nó là công việc duy nhất có thể hoàn tất lúc này.
4. Sau khi thu B, `main` mở chốt A và thu A.
5. C được gửi sau hai kết quả đầu; Future của C vẫn đi qua hàng đợi hoàn tất dù công việc ném lỗi.

Hàm `nextCompleted` dùng poll có thời hạn để báo lỗi nếu thử nghiệm không tiến triển. Nếu ứng dụng muốn chờ không giới hạn, có thể dùng `take()`; yêu cầu về thời hạn phải do bài toán quyết định.

Chỉ `main` in đầu ra nên các dòng có thứ tự xác định. `main` khai báo `throws Exception` để ví dụ tập trung; các ngoại lệ không mong đợi vẫn phải được ứng dụng thực xử lý theo chính sách của nó.

## 6. Thu đủ bao nhiêu kết quả?

Với một nhóm công việc hữu hạn, nên giữ số tác vụ **đã được nhận thành công** và thu đúng số kết quả tương ứng nếu chính sách là xử lý tất cả.

Mã phác thảo:

```java
int accepted = 0;

for (Callable<Result> task : tasks) {
    completions.submit(task);
    accepted++;
}

for (int received = 0; received < accepted; received++) {
    Future<Result> completed = completions.take();
    // Lay ket qua va xu ly loi/huy cua tung cong viec.
}
```

Đây là đoạn minh họa, chưa bao gồm chính sách nếu gửi bị từ chối hoặc nơi thu bị ngắt.

Các lỗi đếm dễ gặp:

- Gửi 5 việc nhưng gọi `take()` 6 lần: lần cuối có thể chờ mãi.
- Lấy một Future nhưng bỏ nó vì thất bại rồi không tăng số đã nhận: thất bại cũng là một lần hoàn tất đã được lấy.
- Đếm mọi việc dự kiến trước khi `submit` thành công: một việc bị từ chối không tạo ra kết quả như việc đã được nhận.
- Trộn nhiều nhóm công việc vào cùng completion service rồi giả định phần tử tiếp theo thuộc đúng nhóm đang xử lý.

Nếu các nhóm cần ranh giới độc lập, thường tạo completion service riêng cho mỗi đợt nhưng có thể dùng chung executor theo quyền sở hữu tài nguyên.

## 7. Hoàn tất gần đồng thời không tạo thứ tự nghiệp vụ ổn định

Cụm “theo thứ tự hoàn tất” có nghĩa bên thu nhận các Future được đưa vào hàng đợi hoàn tất, thay vì chủ động chờ từng Future theo thứ tự gửi.

Nếu hai công việc kết thúc gần như cùng lúc, không nên dựa vào việc kết quả nào sẽ được thấy trước để quyết định một quy tắc nghiệp vụ cần thứ tự ổn định. Thời điểm luồng được lập lịch và công bố hoàn tất có thể khác nhau giữa các lần chạy.

ExecutorCompletionService cũng không làm tác vụ chạy nhanh hơn hoặc thay đổi số luồng xử lý. Nó cải thiện cách **thu nhận** để công việc chậm được gửi sớm không cản nơi gọi xử lý công việc khác đã sẵn sàng.

Nếu cần tái tạo thứ tự đầu vào sau khi thu kết quả, gắn số thứ tự hoặc mã công việc vào dữ liệu trả về, rồi sắp xếp hoặc lưu vào vị trí tương ứng. Việc thu sớm và việc trình bày theo thứ tự có thể được thiết kế riêng.

## 8. Kết quả đầu tiên khác kết quả thành công đầu tiên

Nếu chỉ cần một kết quả hữu ích, không thể luôn viết `take().get()` rồi dừng:

- Future đầu tiên có thể thất bại.
- Giá trị thành công có thể không đáp ứng điều kiện nghiệp vụ.
- Giá trị `null` có thể không được xem là kết quả hữu ích.

Nơi thu phải kiểm tra từng Future đã hoàn tất, ghi nhận lỗi và tiếp tục theo chính sách, tới khi tìm được kết quả phù hợp hoặc hết công việc/thời hạn.

Khi đã có kết quả và không cần công việc còn lại, cần giữ các Future trả từ `submit` để yêu cầu hủy phần còn lại trong `finally`. Không có hành vi tự hủy các việc khác chỉ vì đã gọi `take()` một lần.

`cancel(true)` vẫn là yêu cầu hủy có thể kèm ngắt; công việc đang chạy cần hợp tác dừng. Không tuyên bố mọi tác động bên ngoài của những công việc còn lại đã được hoàn tác.

Nếu bài toán chỉ là “lấy một lần thực thi thành công bất kỳ” mà không cần vòng thu tùy biến, có thể xem xét `ExecutorService.invokeAny`. Completion service phù hợp khi ứng dụng muốn tự quyết định điều kiện kết quả, xử lý từng thất bại hoặc tích lũy nhiều kết quả.

## 9. Hủy và thời điểm xuất hiện trong completion queue

Không nên coi completion queue là nơi tự động báo mọi thay đổi trạng thái Future tức thì.

Với ExecutorCompletionService tiêu chuẩn, công việc được thực thi qua một lớp bọc để công bố Future hoàn tất. Khi hủy một Future đang chạy mà thân công việc không chịu dừng, việc xuất hiện trong completion queue có thể còn phải chờ đường thực thi của lớp bọc đi tới bước công bố.

Chi tiết lớp bọc có thể đối chiếu trong [mã nguồn OpenJDK 25 của ExecutorCompletionService](https://raw.githubusercontent.com/openjdk/jdk/jdk-25-ga/src/java.base/share/classes/java/util/concurrent/ExecutorCompletionService.java).

Tương tự, nếu một công việc chưa chạy bị lấy khỏi hàng đợi của executor khi dừng mạnh, không nên giả định vẫn chắc chắn nhận đủ mọi phần tử bằng `take()` như một đợt thực thi bình thường.

Điều này quan trọng khi thiết kế vòng thu:

- Giữ danh sách Future gốc để điều phối và hủy.
- Có thời hạn hoặc đường thoát phù hợp khi dừng cả đợt.
- Không tiếp tục gọi `take()` vô hạn sau khi đã thay đổi chính sách và bỏ các công việc chưa chạy.
- Quan sát trạng thái nghiệp vụ riêng nếu cần xác nhận công việc thực sự dừng.

Các trạng thái và giới hạn hủy của đối tượng kết quả được mô tả trong [Future API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

## 10. Quản lý tài nguyên và kiểm soát tải

### Completion service không sở hữu thao tác shutdown

Giao diện này không có `shutdown()`. Nếu thành phần hiện tại tạo và sở hữu executor thì phải đóng nó trong vòng đời phù hợp.

Nếu executor được dùng chung do tầng khác quản lý, không đóng nó chỉ vì một đợt thu kết quả đã xong. Quyền sở hữu phải rõ ràng.

Ví dụ hoàn chỉnh tạo pool riêng nên tự đóng trong `finally`. Việc quản lý dừng là trách nhiệm của [ExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html).

### Kết quả cũng có thể tích tụ

Ngay cả khi tác vụ chạy nhanh, nếu nơi thu kết quả quá chậm thì hàng đợi hoàn tất có thể tích tụ Future và các giá trị chúng giữ. Cần kiểm soát cả tốc độ gửi lẫn tốc độ tiêu thụ.

Constructor mặc định dùng một hàng đợi hoàn tất dạng `LinkedBlockingQueue`. Constructor nhận queue riêng không biến nó thành cơ chế chặn đầu vào an toàn.

Theo hợp đồng của ExecutorCompletionService, queue được cung cấp được xem như không giới hạn; nếu thao tác thêm kết quả thất bại, kết quả ấy có thể không lấy được qua dịch vụ. Vì vậy không truyền một queue dung lượng nhỏ rồi kỳ vọng worker sẽ tự đứng chờ đến khi nơi thu lấy bớt.

Cách kiểm soát thường rõ ràng hơn là giới hạn số việc đang được gửi và chưa thu, chẳng hạn chỉ duy trì một cửa sổ công việc: thu một kết quả rồi mới gửi bù một việc tiếp theo. Cấu hình executor và chính sách khi không nhận được tác vụ vẫn phải được thiết kế.

## 11. Những lỗi cần tránh

| Lỗi | Hệ quả |
|---|---|
| Gửi bằng `pool.submit` nhưng thu từ completion service khác | Công việc không được đăng ký để công bố vào queue đó |
| Gọi `take()` nhiều hơn số phần tử có thể tới | Có thể chờ vô hạn |
| Nhầm `poll() == null` với công việc trả null | Bỏ sót hoặc xử lý sai trạng thái |
| Giả định Future lấy ra luôn thành công | Bỏ qua lỗi hoặc hủy |
| Hủy phần còn lại nhưng vẫn đợi chúng như một đợt hoàn tất bình thường | Có thể mắc kẹt nếu công việc không dừng hoặc bị lấy khỏi queue |
| Truyền queue nhỏ để “giới hạn bộ nhớ” mà không đọc hợp đồng | Có thể mất khả năng thu một số kết quả |
| Dùng thứ tự hoàn tất làm thứ tự nghiệp vụ ổn định | Kết quả thay đổi theo thời điểm thực thi |
| Đóng executor dùng chung sau một đợt | Làm ảnh hưởng công việc của thành phần khác |

Khi luồng thu bị ngắt trong `take()` hoặc poll có thời hạn, cần giữ hoặc truyền tín hiệu ngắt đúng hợp đồng, đồng thời quyết định số phận công việc đang thực hiện. Việc ngắt nơi thu không tự hủy toàn bộ đợt.

## 12. Tự kiểm tra

1. Vì sao duyệt danh sách Future theo thứ tự gửi có thể trì hoãn xử lý kết quả đã sẵn sàng?
2. `take()` trả kết quả nghiệp vụ hay một Future?
3. Future của tác vụ thất bại có được thu qua completion service không?
4. `poll(timeout, unit)` hết hạn trả gì?
5. Có thể dùng một completion queue rất nhỏ làm cơ chế backpressure mặc định không?
6. Nếu đã có kết quả hữu ích đầu tiên, các tác vụ khác có tự dừng không?

**Gợi ý:** (1) Nơi gọi có thể đang chờ một việc gửi sớm nhưng chạy lâu. (2) Future. (3) Có, vẫn phải gọi get và xử lý lỗi. (4) Null. (5) Không; thao tác công bố có thể thất bại theo hợp đồng queue riêng. (6) Không; ứng dụng cần quản lý Future và yêu cầu hủy theo chính sách.

ExecutorCompletionService giúp **gửi công việc độc lập với việc thu kết quả**, để nơi gọi xử lý những Future đã sẵn sàng mà không bị thứ tự gửi buộc phải chờ một tác vụ chậm trước tiên.

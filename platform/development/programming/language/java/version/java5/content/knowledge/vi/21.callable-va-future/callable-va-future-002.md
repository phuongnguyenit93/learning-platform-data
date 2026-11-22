# Future và cách theo dõi kết quả bất đồng bộ

## 1. Future đại diện cho một kết quả có thể chưa sẵn sàng

Khi gửi một phép tính cho bộ thực thi, nơi gọi không nhất thiết phải đứng chờ ngay. Nó có thể nhận một đối tượng để quay lại lấy kết quả sau.

Đối tượng đó là `java.util.concurrent.Future<V>`:

- `V` là kiểu kết quả, chẳng hạn `Integer`, `String` hoặc một kiểu dữ liệu nghiệp vụ.
- Future cho phép kiểm tra hoàn tất, chờ kết quả, nhận lỗi và yêu cầu hủy.
- Future không tự nói công việc đã chạy được bao nhiêu phần trăm.
- Việc có một Future không tự tạo ra luồng mới; cơ chế tạo và thực thi công việc vẫn thuộc executor hoặc thành phần khác.

Ví dụ khai báo và gửi một tác vụ, chưa phải chương trình độc lập:

```java
Callable<Integer> calculation = () -> 6 * 7;
Future<Integer> future = executor.submit(calculation);
```

`Callable<Integer>` mô tả phép tính; `executor` tổ chức thực thi; `Future<Integer>` là nơi theo dõi kết quả. Giá trị `42` chưa nằm trực tiếp trong biến `future` theo nghĩa một biến `Integer`; cần lấy bằng API kết quả.

Tác vụ có thể còn chờ, đang chạy hoặc đã hoàn tất ngay trước khi `submit` trả về. Không được suy luận “vừa nhận Future thì chắc chắn công việc chưa bắt đầu”.

## 2. Những trạng thái cần phân biệt

Với API tương thích Java 17, hai phương thức kiểm tra cơ bản là `isDone()` và `isCancelled()`.

| Tình huống | isDone() | isCancelled() | Khi gọi get() |
|---|---:|---:|---|
| Chưa hoàn tất | false | false | Có thể phải chờ |
| Hoàn tất thành công | true | false | Trả giá trị |
| Hoàn tất do lỗi | true | false | Ném `ExecutionException` |
| Đã bị hủy | true | true | Ném `CancellationException` |

**Done không có nghĩa thành công.** Nó bao gồm cả thất bại và hủy.

`isDone() == false` cũng không cho biết tác vụ đang nằm trong hàng đợi hay đã được luồng nhận để chạy. Future là hợp đồng về kết quả, không phải bộ đo mọi trạng thái nội bộ của executor.

Các phương thức và ngoại lệ được mô tả trong [Future API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

### Không dùng vòng lặp rỗng để chờ

```java
while (!future.isDone()) {
    // Cho lien tuc: khong nen dung nhu cach cho mac dinh.
}
```

Đây là ví dụ cách làm cần tránh. Việc kiểm tra liên tục tiêu tốn CPU mà không thực hiện công việc hữu ích. Nếu cần chờ, dùng `get()` hoặc `get(timeout, unit)`. Nếu ứng dụng phải xử lý nhiều kết quả khi chúng sẵn sàng, chọn công cụ thu nhận kết quả phù hợp thay vì quét liên tục.

## 3. get(): nhận kết quả hoặc nhận lý do không thể có kết quả

```java
Integer value = future.get();
```

Nếu chưa có kết quả, **luồng gọi get** chờ. Không phải luồng thực hiện tác vụ bị buộc đứng chờ chỉ vì nơi khác gọi `get()`.

Nếu đã hoàn tất thành công, lời gọi lấy được giá trị mà không cần chờ phép tính chạy thêm. Gọi `get()` nhiều lần trên cùng một kết quả đã hoàn tất không gửi lại tác vụ và không tính lại công việc.

### Bốn kết quả quan sát cần xử lý

| Kết quả của get() | Ý nghĩa |
|---|---|
| Trả `V` | Công việc hoàn tất thành công |
| `ExecutionException` | Công việc ném lỗi; xem `getCause()` |
| `InterruptedException` | Luồng đang chờ bị ngắt |
| `CancellationException` | Future đã bị hủy |

`InterruptedException` ở luồng chờ không tự khẳng định tác vụ đã bị ngắt. Đây là hai luồng và hai diễn biến cần phân biệt.

Một cách tổ chức xử lý minh họa:

```java
try {
    Integer value = future.get();
    useValue(value);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
} catch (ExecutionException e) {
    reportFailure(e.getCause());
} catch (CancellationException e) {
    reportCancellation();
}
```

Đây là đoạn mã trong một phương thức `void`; các phương thức `useValue`, `reportFailure` và `reportCancellation` do ứng dụng cung cấp. Chúng thể hiện ba nhánh xử lý khác nhau, không phải API của Future.

Nếu có thể để ngoại lệ ngắt đi lên tầng chịu trách nhiệm, có thể khai báo truyền tiếp thay vì bắt tại đây. Nếu bắt mà không truyền tiếp, thường cần khôi phục cờ ngắt và dừng luồng xử lý hiện tại theo chính sách của ứng dụng.

### Lỗi của tác vụ khác lỗi khi gửi

`submit` có thể ném `RejectedExecutionException` ngay khi executor không nhận được công việc. Trong trường hợp đó, lời gọi không trả một Future thành công để chờ.

Ngược lại, khi thân tác vụ đã được nhận nhưng sau đó ném `IOException` hoặc `IllegalStateException`, Future có thể hoàn tất do lỗi, và `get()` báo `ExecutionException` chứa nguyên nhân.

Không chỉ in thông điệp của lớp bọc rồi bỏ nguyên nhân. Việc chẩn đoán cần biết công việc nào thất bại và lỗi gốc là gì.

## 4. get(timeout, unit): giới hạn thời gian chờ của nơi gọi

```java
Integer value = future.get(500, TimeUnit.MILLISECONDS);
```

Nơi gọi chỉ chờ tối đa khoảng thời gian yêu cầu để nhận kết quả; nếu chưa sẵn sàng, lời gọi báo `TimeoutException`.

Các điểm cần nhớ:

- Timeout này áp dụng cho **lời gọi chờ**, không tự đặt thời hạn chạy cho thân tác vụ.
- Hết timeout không tự gọi `cancel`.
- Sau timeout, Future vẫn có thể hoàn tất thành công hoặc thất bại.
- Có thể gọi `get` lần nữa nếu chính sách ứng dụng còn muốn chờ.

Ví dụ nếu một lần `get(500 ms)` hết hạn và sau đó lại chờ thêm 500 ms, tổng thời gian đã chờ có thể xấp xỉ một giây. Nếu nghiệp vụ chỉ cho phép tổng cộng 500 ms, phải theo dõi thời hạn chung và truyền phần thời gian còn lại, không cấp lại toàn bộ ngân sách ở mỗi bước.

Khi không còn cần công việc sau timeout, ứng dụng phải quyết định có yêu cầu hủy không. Nếu tác vụ đã tạo tác động như gửi thông báo hoặc ghi dữ liệu, hủy không tự hoàn tác tác động ấy.

## 5. cancel(): yêu cầu hủy một tác vụ

Chữ ký:

```java
boolean accepted = future.cancel(true);
```

Tham số cho biết có được phép cố gắng ngắt luồng đang thực thi để dừng tác vụ hay không:

- `cancel(true)`: có thể yêu cầu ngắt khi biết luồng thực thi.
- `cancel(false)`: không yêu cầu ngắt một công việc đang chạy; nếu việc đang chạy tiếp tục thì trạng thái hủy của Future không có nghĩa thân việc đã kết thúc.

Nếu việc chưa bắt đầu và được hủy thành công, nó không nên chạy. Nếu đã hoàn tất hoặc không thể hủy vì lý do khác, yêu cầu hủy có thể không thành công. Hãy dùng `isCancelled()` khi cần kiểm tra trạng thái hủy, thay vì suy diễn chỉ từ thời điểm đã gọi phương thức.

### Hủy Future khác dừng mã máy tức thì

Với tác vụ gửi vào nhóm luồng tiêu chuẩn, yêu cầu ngắt vẫn cần mã công việc hợp tác: kiểm tra cờ ngắt, thoát khỏi thao tác chặn có hỗ trợ ngắt, dọn dẹp tài nguyên và kết thúc.

Một Future có thể đã ở trạng thái hủy trong khi một phần thân công việc chưa kịp dừng. Vì vậy, không dùng `isDone()` làm bằng chứng vật lý rằng tài nguyên ngoài không còn được sử dụng.

Các triển khai Future có chính sách cụ thể khác nhau. Chẳng hạn `CompletableFuture` không trực tiếp điều khiển phép tính tạo kết quả như `FutureTask`; không áp dụng máy móc giả định ngắt của tác vụ trong thread pool cho mọi đối tượng có kiểu Future.

## 6. Chương trình Java 17+: chờ, timeout, thất bại và hủy

Lưu thành **`FutureTrackingDemo.java`**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTrackingDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch cancelGate = new CountDownLatch(1);

        try {
            Future<Integer> pending = pool.submit(() -> {
                entered.countDown();
                release.await();
                return 42;
            });

            entered.await();
            System.out.println("initial done: " + pending.isDone());

            try {
                pending.get(1, TimeUnit.MILLISECONDS);
                throw new AssertionError("Expected timeout");
            } catch (TimeoutException e) {
                System.out.println("wait: timeout");
            }

            Future<String> failed = pool.submit(() -> {
                throw new IllegalStateException("broken");
            });
            try {
                failed.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException e) {
                Throwable cause = e.getCause();
                System.out.println(
                        "failure: " + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
            }

            release.countDown();
            System.out.println(
                    "result: " + pending.get(5, TimeUnit.SECONDS));
            System.out.println("done after result: " + pending.isDone());
            System.out.println("result again: " + pending.get());

            Future<String> cancelled = pool.submit(() -> {
                cancelGate.await();
                return "late";
            });
            System.out.println(
                    "cancel accepted: " + cancelled.cancel(true));

            try {
                cancelled.get();
            } catch (CancellationException e) {
                System.out.println(
                        "cancelled get: " + e.getClass().getSimpleName());
            }
        } finally {
            release.countDown();
            cancelGate.countDown();
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
}
```

Biên dịch và chạy:

```shell
javac --release 17 FutureTrackingDemo.java
java FutureTrackingDemo
```

Stdout chính xác:

```text
initial done: false
wait: timeout
failure: IllegalStateException: broken
result: 42
done after result: true
result again: 42
cancel accepted: true
cancelled get: CancellationException
```

### Các chốt đồng bộ làm rõ điều gì?

Tác vụ `pending` không thể trả `42` trước khi `main` mở chốt `release`. Vì thế:

1. `initial done` là `false`.
2. Lần chờ một mili giây chắc chắn hết hạn vì chốt vẫn đóng; không dựa vào độ nhanh chậm của phép tính.
3. Timeout không làm mất Future: sau khi mở chốt, vẫn nhận được `42`.
4. Lấy lần thứ hai vẫn nhận `42`, không thực thi lại lambda.

Tác vụ `failed` ném lỗi trên luồng xử lý; `main` nhận nguyên nhân qua `ExecutionException`.

Tác vụ `cancelled` không thể trả `"late"` trước khi chốt của nó được mở. Yêu cầu hủy có thể xảy ra trước hoặc sau lúc nó bắt đầu, nhưng trong cả hai trường hợp của executor tiêu chuẩn này nó chưa hoàn tất và có thể được hủy. Sau đó `get()` báo trạng thái hủy.

Chương trình chỉ in từ `main` nên các dòng đầu ra có thứ tự xác định. `main` khai báo `throws Exception` để giữ ví dụ tập trung; ứng dụng thực phải xử lý thêm những nhánh lỗi không mong đợi theo chính sách nghiệp vụ.

## 7. Future của Runnable vẫn có ích

Không phải mọi Future đều đại diện cho giá trị nghiệp vụ:

```java
Runnable action = () -> saveAuditRecord();
Future<?> completion = executor.submit(action);
```

Đây là đoạn minh họa; `saveAuditRecord()` do ứng dụng cung cấp.

Với overload `submit(Runnable)`, `completion.get()` trả `null` khi thành công. Future vẫn cho phép biết công việc đã xong, có thất bại không hoặc đã bị hủy chưa.

Không dùng `null` làm dấu hiệu “chưa hoàn tất”: một `Callable` cũng có thể trả `null` hợp lệ. Trạng thái và kết quả là hai thông tin khác nhau.

Các overload `submit` được mô tả trong [ExecutorService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html).

## 8. Nhiều Future: thứ tự lấy khác thứ tự hoàn tất

Giả sử A chạy lâu và B chạy nhanh, được gửi vào một executor có khả năng xử lý song song:

```java
Future<Result> first = executor.submit(taskA);
Future<Result> second = executor.submit(taskB);

Result a = first.get();
Result b = second.get();
```

Đây là mã minh họa với các kiểu và tác vụ của ứng dụng.

B có thể xong trước, nhưng nơi gọi vẫn chờ A ở dòng `first.get()` trước khi xử lý B. Điều đó không làm B bị chạy chậm hơn; nó chỉ trì hoãn lúc nơi gọi thu nhận kết quả B.

Nếu yêu cầu là xử lý công việc nào xong trước, có thể dùng `ExecutorCompletionService`. Nó đưa các Future đã hoàn tất vào một hàng đợi; `take()` chờ để nhận một kết quả đã sẵn sàng. Mỗi kết quả lấy ra vẫn cần `get()` và xử lý lỗi hoặc hủy. Xem [ExecutorCompletionService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html).

Ngược lại, nếu thứ tự đầu vào có ý nghĩa nghiệp vụ, thu kết quả theo danh sách ban đầu có thể là lựa chọn đúng. Cần chọn theo yêu cầu, không chỉ theo tác vụ nhanh nhất.

### Đừng gửi rồi chờ từng việc nếu muốn chạy độc lập đồng thời

Nếu gọi `submit(taskA).get()` rồi mới gửi B, hai việc chưa được gửi cùng lúc để có cơ hội thực hiện chồng lấp. Với công việc độc lập, thường gửi một nhóm có kiểm soát trước rồi thu kết quả sau.

Không vì vậy mà gửi không giới hạn mọi công việc. Executor, hàng đợi và số Future được giữ lại vẫn tiêu thụ tài nguyên.

## 9. Kết quả đã nhận và dữ liệu dùng chung

Theo hợp đồng nhất quán bộ nhớ của Future, các hành động của phép tính xảy ra trước những hành động tiếp sau lời gọi `get()` tương ứng trong luồng nhận. Điều này giúp công bố kết quả từ luồng tính toán sang luồng sử dụng.

Tuy nhiên, Future không biến đối tượng kết quả thành bất biến và không tạo bản sao sâu. Nếu `get()` trả một `List` có thể thay đổi và sau đó nhiều luồng cùng sửa danh sách, vẫn cần chính sách đồng bộ hoặc quyền sở hữu dữ liệu.

Tương tự, đừng gửi tác vụ giữ tham chiếu đến đối tượng đầu vào rồi đồng thời sửa các trường của đối tượng ấy mà không có quy tắc chia sẻ. Cách đơn giản hơn thường là dùng đầu vào bất biến và kết quả có cấu trúc rõ ràng.

## 10. Các phương thức quan sát bổ sung trên Java 19+

Nếu dự án chạy từ Java 19 trở lên, Future có thêm:

| API | Mục đích | Điều kiện cần hiểu |
|---|---|---|
| `state()` | Nhận `RUNNING`, `SUCCESS`, `FAILED` hoặc `CANCELLED` | `RUNNING` nghĩa chưa hoàn tất; có thể còn chờ executor |
| `resultNow()` | Lấy ngay kết quả thành công, không chờ | Ném `IllegalStateException` nếu chưa hoàn tất thành công |
| `exceptionNow()` | Lấy ngay lỗi của phép tính thất bại | Ném `IllegalStateException` nếu không ở trạng thái thất bại phù hợp |

Không dùng các API này trong mã biên dịch với `--release 17`. Ví dụ hoàn chỉnh của bài dùng những phương thức nền tảng vẫn áp dụng trên Java hiện hành và tương thích Java 17+.

Các phương thức mới giúp phân loại trạng thái rõ hơn; chúng không cung cấp phần trăm tiến độ hay vị trí tác vụ trong hàng đợi.

## 11. Giới hạn của Future và các lỗi thường gặp

### Không có phần trăm tiến độ mặc định

`isDone()` không thể nói công việc đã xong 30% hay còn bao lâu. Nếu cần tiến độ, tác vụ phải có mô hình báo cáo riêng: số phần đã xử lý, giai đoạn hiện tại hoặc sự kiện nghiệp vụ có ý nghĩa.

### Không tự nối các bước xử lý

Future cơ bản không có các phương thức nối bước như `thenApply` hoặc `thenCompose`. Khi bài toán cần mô tả chuỗi xử lý và phối hợp nhiều kết quả, có thể tìm hiểu `CompletableFuture` cùng `CompletionStage`. Chúng bổ sung khả năng tổ chức các bước phụ thuộc; không chỉ là đổi tên của `Future`.

Chi tiết được mô tả trong [CompletableFuture API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html).

### Không phải mã công việc bền vững qua lần khởi động

Một Future trong bộ nhớ không tự trở thành mã truy vấn trạng thái sau khi tiến trình khởi động lại. Nếu người dùng phải theo dõi công việc lâu dài, cần thiết kế lưu trạng thái và định danh nghiệp vụ phù hợp.

### Không bỏ Future khi cần biết lỗi

Gửi tác vụ bằng `submit` rồi bỏ đối tượng trả về có thể làm nơi chịu trách nhiệm không quan sát thất bại. Phải có nơi thu nhận kết quả hoặc cơ chế ghi nhận lỗi đã thiết kế rõ.

### Không chờ công việc con trong một nhóm đã hết luồng

Một tác vụ chiếm luồng của executor rồi gửi công việc khác vào chính nhóm ấy và gọi `get()` có thể gây bế tắc nếu không còn luồng để chạy công việc con. Future không tự giải quyết sự phụ thuộc này; cần thiết kế cách phối hợp công việc phù hợp.

### Không đồng nhất dừng executor với hoàn tất mọi Future

Tùy triển khai, công việc lấy khỏi hàng đợi khi `shutdownNow()` chưa chắc được hủy Future tương ứng. Cần quản lý các Future đã cấp cho nơi gọi, thay vì cho rằng executor kết thúc thì mọi kết quả tự được giải quyết.

## 12. Tự kiểm tra

1. Vì sao `isDone() == true` chưa đủ để sử dụng kết quả như một lần thành công?
2. Timeout của `get` có tự hủy phép tính không?
3. Gọi `get()` hai lần có chạy lại tác vụ không?
4. Luồng chờ bị ngắt có nghĩa luồng tính toán cũng đã bị ngắt không?
5. Nếu tác vụ B xong trước A nhưng mã gọi `A.get()` trước, chuyện gì bị trì hoãn?
6. Vì sao một `Future<?>` có kết quả thành công là `null` vẫn hữu ích?

**Gợi ý:** (1) Có thể thất bại hoặc bị hủy. (2) Không. (3) Không. (4) Không. (5) Việc nơi gọi thu nhận và xử lý B. (6) Nó vẫn biểu diễn hoàn tất, lỗi và khả năng hủy.

Dùng Future đúng nghĩa là theo dõi riêng **trạng thái hoàn tất, kết quả hoặc lỗi, thời gian chờ của nơi gọi và yêu cầu hủy công việc**.

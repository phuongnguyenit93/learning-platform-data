# Thu kết quả theo thứ tự hoàn tất và xử lý hết thời hạn

## 1. Vì sao không chỉ gọi get theo thứ tự submit?

Giả sử nộp ba tác vụ theo thứ tự A, B, C:

```text
A: đang chờ rất lâu
B: xong nhanh
C: xong sau B nhưng trước A
```

Nếu duyệt danh sách Future theo thứ tự nộp:

```java
for (Future<Result> future : futures) {
    Result result = future.get();
    use(result);
}
```

thì bên thu kết quả bị giữ ở A, dù B và C đã hoàn tất. Đoạn này là minh họa cấu trúc, không phải chương trình chạy độc lập.

Vấn đề nằm ở thứ tự **chờ và xử lý kết quả**, không có nghĩa executor đã ngừng chạy B/C. Nếu ứng dụng muốn dùng ngay kết quả nào sẵn trước, cần một nơi thu các tác vụ đã hoàn tất.

`CompletionService<V>` tách việc nộp tác vụ khỏi việc nhận kết quả. `ExecutorCompletionService<V>` dùng một Executor để chạy và một hàng đợi để đưa các Future hoàn tất tới bên thu. Xem [CompletionService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionService.html).

## 2. Thứ tự hoàn tất khác thứ tự nộp

Luồng khái niệm:

```text
submit A, B, C
    ↓
Executor chạy các tác vụ
    ↓
B hoàn tất → hàng đợi hoàn tất
C hoàn tất → hàng đợi hoàn tất
A hoàn tất → hàng đợi hoàn tất
    ↓
Bên thu lấy B, C, A
```

Khi các tác vụ kết thúc rất gần nhau, thứ tự được quan sát là thứ tự Future được đưa vào/lấy ra từ hàng đợi hoàn tất. Không dùng nó như một phép đo timestamp tuyệt đối để phân định hai sự kiện gần đồng thời.

Các API lấy kết quả:

| API | Hành vi |
| --- | --- |
| `take()` | Chờ đến khi có một Future hoàn tất |
| `poll()` | Lấy ngay nếu có, nếu chưa có trả null |
| `poll(timeout, unit)` | Chờ tối đa khoảng được truyền vào, nếu chưa có thì trả null |

Lấy được Future từ completion queue không đồng nghĩa tác vụ thành công. Nó có thể đã trả kết quả, ném lỗi hoặc bị hủy. Phải gọi `get()` để phân loại.

Với Future đã được completion service trả về là hoàn tất, `get()` không cần chờ thêm công việc tính toán của tác vụ đó; nó vẫn có thể báo `ExecutionException` hoặc `CancellationException`. Không coi `isDone()` là bằng chứng thành công. Xem [Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html).

## 3. Một thời hạn chung khác timeout cho từng lần chờ

Giả sử toàn bộ lượt thu kết quả có ngân sách 1 giây. Cách sau dễ làm tổng thời gian vượt mong muốn:

```java
for (int i = 0; i < taskCount; i++) {
    Future<Result> next = completed.poll(1, TimeUnit.SECONDS);
    // Moi vong lai duoc cap them mot giay.
}
```

Nếu có nhiều tác vụ, mỗi vòng được đợi một giây mới. Đó là timeout cho từng lần chờ, không phải ngân sách chung của cả nhóm.

Cách xử lý ngân sách chung:

```java
long startedAt = System.nanoTime();
long budgetNanos = TimeUnit.SECONDS.toNanos(1);

// Truoc moi lan cho:
long remaining = budgetNanos - (System.nanoTime() - startedAt);
```

Sau đó chỉ chờ bằng `remaining`. Khi không còn thời gian hoặc `poll(remaining,...)` trả null, dừng thu theo chính sách.

Các đoạn trên là mẫu tích hợp; cần import và biến tương ứng. Thời gian xử lý kết quả trước vòng tiếp theo cũng đã trôi qua và làm giảm ngân sách còn lại. Nếu thời hạn phải tính cả giai đoạn submit, đặt mốc trước khi nộp tác vụ; nếu chỉ tính lúc bắt đầu thu, đặt mốc ở vị trí đó và ghi rõ.

Dùng đồng hồ đo thời gian đã trôi, không dùng giờ lịch để trừ timeout. Mẫu hiệu `System.nanoTime() - startedAt` tránh lỗi do cộng deadline bị tràn số; xem [System.nanoTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).

## 4. Xác định chính sách trước khi viết vòng lặp

Cần trả lời:

- Thu tất cả kết quả có thể nhận trước khi hết ngân sách, hay chỉ cần thành công đầu tiên?
- Một tác vụ lỗi có làm hủy cả nhóm không?
- Khi hết hạn, giữ kết quả đã có hay loại bỏ toàn bộ?
- Có hủy các tác vụ còn lại không?
- Ai sở hữu executor và ai được phép dừng nó?
- Ngân sách này giới hạn việc chờ, việc xử lý hay toàn bộ vòng đời, kể cả dọn tài nguyên?

Bài thực hành chọn:

1. Thu nhiều kết quả theo thứ tự sẵn sàng.
2. Ghi nhận lỗi từng tác vụ và tiếp tục thu tác vụ khác.
3. Dùng ngân sách chờ chung bắt đầu ngay trước loạt submit.
4. Khi không thể thu đủ trong ngân sách, giữ những kết quả đã ghi nhận.
5. Yêu cầu hủy tác vụ chưa xong.
6. Dừng executor do chính chương trình tạo và chờ dọn tài nguyên với giới hạn riêng.

Đây không phải chính sách bắt buộc của CompletionService. Với bài toán “chỉ cần một kết quả hợp lệ”, vòng thu có thể kết thúc sớm và hủy phần còn lại. Với tác vụ bắt buộc thành công toàn bộ, cách báo kết quả sẽ khác.

## 5. Ví dụ chạy được: B, C hoàn tất trước A, D thất bại

Chương trình dùng `CountDownLatch` để thiết lập quan hệ:

- A chờ một latch không được mở trong đường chạy bình thường.
- B trả kết quả ngay.
- C chỉ được tiếp tục sau khi bên thu đã nhận B.
- D chỉ được tiếp tục sau khi bên thu đã nhận C; D ném lỗi.
- A còn chờ khi hết ngân sách và nhận yêu cầu hủy có ngắt.

Latches giúp minh họa thứ tự mà không dựa vào giả định “sleep 10 ms luôn nhanh hơn sleep 100 ms”. Thời gian thực thi vẫn phụ thuộc lịch chạy của môi trường.

Lưu thành `CompletionDeadlineDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletionService;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class CompletionDeadlineDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                3, 3, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(8),
                new ThreadPoolExecutor.AbortPolicy());
        CompletionService<String> completed =
                new ExecutorCompletionService<>(pool);
        List<Future<String>> submitted = new ArrayList<>();
        CountDownLatch neverReleased = new CountDownLatch(1);
        CountDownLatch afterB = new CountDownLatch(1);
        CountDownLatch afterC = new CountDownLatch(1);

        long budget = TimeUnit.SECONDS.toNanos(1);
        long start = System.nanoTime();
        int received = 0;
        try {
            submitted.add(completed.submit(() -> {
                neverReleased.await();
                return "A";
            }));
            submitted.add(completed.submit(() -> "B"));
            submitted.add(completed.submit(() -> {
                afterB.await();
                return "C";
            }));
            submitted.add(completed.submit(() -> {
                afterC.await();
                throw new IllegalStateException("D");
            }));

            while (received < submitted.size()) {
                long remaining = budget - (System.nanoTime() - start);
                if (remaining <= 0) {
                    break;
                }
                Future<String> next =
                        completed.poll(remaining, TimeUnit.NANOSECONDS);
                if (next == null) {
                    break;
                }

                received++; // Bao gom ca thanh cong, that bai va huy.
                try {
                    String value = next.get();
                    System.out.println("success=" + value);
                    if (value.equals("B")) {
                        afterB.countDown();
                    } else if (value.equals("C")) {
                        afterC.countDown();
                    }
                } catch (ExecutionException ex) {
                    Throwable cause = ex.getCause();
                    System.out.println("failed="
                            + cause.getClass().getSimpleName()
                            + ":" + cause.getMessage());
                } catch (CancellationException ex) {
                    System.out.println("completed=CANCELLED");
                }
            }
            System.out.println("received=" + received);
            System.out.println("waitBudgetExpired="
                    + (received < submitted.size()));
        } finally {
            int acceptedCancelRequests = 0;
            for (Future<String> future : submitted) {
                if (!future.isDone() && future.cancel(true)) {
                    acceptedCancelRequests++;
                }
            }
            System.out.println("cancelRequestsAccepted="
                    + acceptedCancelRequests);
            pool.shutdownNow();
            if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
                System.err.println("executorNotTerminated");
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 CompletionDeadlineDemo.java
java CompletionDeadlineDemo
```

Một lần chạy bình thường, khi B/C/D được lập lịch trong ngân sách, cho stdout:

```text
success=B
success=C
failed=IllegalStateException:D
received=3
waitBudgetExpired=true
cancelRequestsAccepted=1
```

Nếu máy bị đình trệ quá lâu trước khi B/C/D được phục vụ, số kết quả nhận trong một giây có thể ít hơn. Không dùng một timeout ngắn làm bảo đảm tuyệt đối về lịch chạy của hệ điều hành.

## 6. Phân tích các điểm quyết định trong chương trình

### Không chờ A theo thứ tự nộp

A được submit trước nhưng collector gọi `completed.poll(...)`, không gọi `submitted.get(0).get()`. Vì vậy B và C được xử lý trong khi A vẫn chờ.

Danh sách `submitted` chỉ giữ các Future để quản lý/hủy ở cuối. Hàng đợi hoàn tất mới quyết định tác vụ nào được thu tiếp theo.

### Đếm cả kết quả thất bại

Biến `received` tăng ngay khi lấy được một Future hoàn tất, trước khi gọi `get()`. Một tác vụ lỗi vẫn là một tác vụ đã được thu.

Nếu chỉ tăng khi thành công, sau khi có lỗi collector có thể chờ thêm một “kết quả” không tồn tại hoặc chỉ thoát khi hết hạn dù mọi tác vụ đã kết thúc.

### Lỗi tác vụ không phải lỗi của luồng thu

D ném `IllegalStateException` bên trong `Callable`. Collector nhận lỗi qua `ExecutionException` và đọc `getCause()`. Theo chính sách của bài, nó ghi nhận lỗi và tiếp tục.

Trong hệ thống thật, thông báo lỗi cần được kiểm soát, tránh ghi bí mật hoặc dữ liệu nhạy cảm vào log. Nên gắn mã tác vụ để quy lỗi đúng nguồn, không chỉ dựa vào thông điệp của ngoại lệ.

### Hết thời gian chờ không tự hủy A

`poll(...)` trả null chỉ nói rằng không có Future hoàn tất được lấy trong khoảng chờ đó. A không vì vậy tự kết thúc.

Khối `finally` duyệt các Future đã được nộp thành công và yêu cầu hủy những tác vụ chưa xong. Biến `cancelRequestsAccepted` đếm yêu cầu hủy mà `cancel(true)` trả true, không đếm số hoạt động ngoài tiến trình đã chắc chắn ngừng.

### Executor có vòng đời riêng

Chương trình sở hữu pool, nên được quyền gọi `shutdownNow()` và `awaitTermination()`. Với pool dùng chung do tầng khác quản lý, không dừng toàn bộ executor chỉ vì một nhóm tác vụ hết hạn; chỉ hủy các Future thuộc nhóm của mình theo hợp đồng.

Cách shutdown và chờ kết thúc được mô tả trong [ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html).

## 7. Hủy là yêu cầu hợp tác, không phải nút cưỡng chế

`future.cancel(true)` có thể yêu cầu ngắt luồng đang chạy. Nó không bảo đảm mọi mã hoặc I/O bên trong đều dừng ngay.

Trong mẫu, A gọi `CountDownLatch.await()`, một thao tác có thể đáp ứng ngắt bằng `InterruptedException`, nên cleanup có thể hoàn tất nhanh.

Tác vụ CPU dài cần kiểm tra ngắt ở điểm thích hợp. Tác vụ I/O cần deadline/timeout/cơ chế hủy đúng của thư viện đang dùng. Không nuốt `InterruptedException` rồi tiếp tục vòng lặp vô hạn.

Các trạng thái cần phân biệt:

```text
Collector không chờ nữa
        ≠
Future đã được đánh dấu hủy
        ≠
Mã tác vụ đã thực sự dừng
        ≠
Hoạt động bên ngoài đã được hoàn tác
```

Nếu một tác vụ đã ghi dữ liệu hoặc gọi một dịch vụ ngoài, hủy Future không tự thu hồi tác động đó. Khi có thử lại, cần tính tới khả năng tác vụ cũ đã làm một phần hoặc toàn bộ công việc.

Không hủy được một Future vì nó vừa hoàn tất là một cuộc đua bình thường. Đừng báo “tác vụ chắc chắn còn chạy” chỉ dựa trên việc `cancel()` trả false; hãy xem trạng thái và chính sách kết quả.

## 8. Ngắt collector khác thất bại tác vụ

Có hai đường lỗi riêng:

| Tình huống | Ngoại lệ thường thấy ở collector | Cách suy nghĩ |
| --- | --- | --- |
| Callable ném lỗi | `ExecutionException` từ get | Tác vụ đó thất bại |
| Future bị hủy | `CancellationException` từ get | Tác vụ không còn kết quả thành công để dùng |
| Luồng collector bị ngắt khi chờ | `InterruptedException` | Yêu cầu điều khiển vòng đời của chính collector |
| Không có kết quả trong thời gian poll | Trả null | Ngân sách chờ của thao tác đã hết |
| Không nộp được tác vụ | `RejectedExecutionException` | Executor không nhận thêm công việc |

Mẫu để `InterruptedException` truyền ra ngoài `main`, đồng thời dùng `finally` dọn tác vụ đã nộp. Trong một phương thức thư viện, có thể truyền ngoại lệ lên tầng gọi; nếu bắt mà không truyền tiếp, cần giữ trạng thái ngắt theo hợp đồng, thường bằng `Thread.currentThread().interrupt()`.

Không bắt chung mọi ngoại lệ rồi tiếp tục thu như chưa có gì xảy ra. Nếu collector được yêu cầu dừng mà vẫn chờ, việc hủy ở tầng cao sẽ mất tác dụng.

Nếu submit bị từ chối sau khi một số tác vụ đã được nhận, phải xử lý các Future đã có. Khối `finally` trong mẫu vẫn giữ danh sách ấy để yêu cầu hủy và dọn pool.

## 9. Ngân sách chờ không phải bảo đảm thời gian thực cứng

Vòng lặp tính lại `remaining` hạn chế việc cấp thêm thời gian chờ cho mỗi kết quả. Nhưng chương trình có thể trở lại muộn hơn thời điểm mong muốn vì lập lịch, I/O log hoặc xử lý kết quả.

Một Future lấy được từ `poll(remaining,...)` không tự mang timestamp “Callable hoàn tất trước deadline”. Collector có thể được hệ điều hành chạy lại muộn, trong khi Future đã nằm sẵn trong hàng đợi.

Nếu hợp đồng yêu cầu phân biệt chính xác “hoàn tất trước mốc X” với “được collector nhận trước mốc X”, cần ghi mốc thời gian/định nghĩa hoàn tất ngay tại công việc hoặc tầng điều phối phù hợp và áp dụng chính sách rõ ràng. CompletionService không tự cung cấp định nghĩa nghiệp vụ đó.

Trong mẫu:

- Ngân sách một giây tính từ ngay trước submit.
- Mỗi lần chờ dùng phần còn lại.
- Kết quả đã lấy được sẽ được xử lý.
- Cleanup có thời gian chờ tối đa hai giây riêng, nên tổng thời gian chương trình không được hứa là luôn dưới một giây.
- Việc ngắt tác vụ và kết thúc pool vẫn cần thời gian thực thi.

Nếu API cần phản hồi trước một hạn cụ thể, phải thiết kế cả đường xử lý kết quả và cleanup phù hợp. Không gắn một con số timeout vào một lần gọi rồi coi mọi phần khác tự được giới hạn.

## 10. Hai hàng đợi có trách nhiệm khác nhau

Trong mẫu có:

```text
Hàng đợi công việc của ThreadPoolExecutor
    → chứa công việc chưa được chạy

Hàng đợi hoàn tất của ExecutorCompletionService
    → chứa Future đã hoàn tất nhưng chưa được collector lấy
```

`ArrayBlockingQueue<>(8)` trong constructor pool giới hạn hàng đợi công việc, không phải completion queue.

Constructor CompletionService mặc định dùng một hàng đợi hoàn tất riêng. Không tự thay bằng một queue hữu hạn rồi kỳ vọng nó tạo backpressure an toàn: hợp đồng `ExecutorCompletionService` coi completion queue được cung cấp như không giới hạn; nếu thao tác thêm Future hoàn tất thất bại, kết quả có thể không lấy lại được qua service. Xem [ExecutorCompletionService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html).

Với rất nhiều tác vụ, nên giới hạn số tác vụ đang tồn tại, chẳng hạn nộp theo cửa sổ và chỉ nộp thêm khi đã thu một kết quả. Đồng thời giới hạn kích thước kết quả và tốc độ xử lý phía thu. Không để hàng đợi hoàn tất tăng vô hạn do producer nộp nhanh hơn collector tiêu thụ.

Một CompletionService riêng cho một nhóm cũng giúp tránh trộn kết quả đến muộn từ nhóm đã hết hạn với nhóm mới. Nếu cần dùng chung lâu dài, kết quả phải mang định danh nhóm/tác vụ và có quy tắc xử lý đến muộn.

## 11. Tự kiểm chứng bằng các biến thể

| Biến thể | Điều cần kiểm tra |
| --- | --- |
| Chờ từng Future theo thứ tự nộp | B/C đã xong nhưng collector bị giữ ở A |
| D thay bằng kết quả thành công | received vẫn tăng và không có ExecutionException |
| D lỗi nhưng chỉ đếm thành công | Phát hiện lỗi logic đếm số Future cần thu |
| Bỏ hủy ở finally | Collector dừng chờ nhưng A vẫn có thể chiếm luồng |
| Bỏ xử lý ngắt trong một tác vụ dài | Hủy Future chưa chứng minh luồng đã dừng |
| Đặt lại timeout đầy đủ mỗi vòng | Tổng thời gian chờ có thể vượt ngân sách nhóm |
| Cho tác vụ hoàn tất sát hạn | Kiểm tra chính sách cuộc đua/đến muộn, không dựa vào thứ tự in log |
| Submit bị từ chối giữa chừng | Các tác vụ đã nhận vẫn được quản lý và dọn |

Bài tập:

1. Giữ thứ tự submit A, B, C, D nhưng đổi điều kiện hoàn tất để C được thu trước B. Cần đổi latch ở đâu mà không dùng sleep để đoán thứ tự?
2. Nếu chỉ cần kết quả thành công đầu tiên, collector nên dừng và hủy phần còn lại ở điểm nào?
3. Nếu nghiệp vụ yêu cầu đủ mọi kết quả, cấu trúc phản hồi khi A hết hạn cần biểu diễn phần thành công, phần thất bại và phần chưa thu thế nào?
4. Với một pool dùng chung, hãy sửa vòng đời cleanup để chỉ tác động nhóm tác vụ hiện tại.

Mấu chốt là tách thứ tự nộp, thứ tự hoàn tất và chính sách thời hạn. CompletionService giải quyết đường thu kết quả; ứng dụng vẫn phải quyết định thế nào là đủ, xử lý lỗi ra sao và trách nhiệm nào còn tồn tại sau khi không chờ nữa.

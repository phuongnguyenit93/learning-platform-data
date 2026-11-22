# shutdown, shutdownNow và awaitTermination

## 1. Ba việc khác nhau trong vòng đời ExecutorService

Một bộ thực thi (executor) không chỉ nhận tác vụ; nó còn sở hữu luồng và hàng đợi công việc. Khi thành phần sử dụng kết thúc, cần trả lời ba câu hỏi:

1. Từ lúc nào ngừng nhận công việc mới?
2. Công việc đã nhận sẽ được cho chạy tiếp hay phải yêu cầu dừng?
3. Làm sao biết executor đã kết thúc thật sự?

`shutdown()` khởi động việc dừng có trật tự. `shutdownNow()` yêu cầu dừng mạnh hơn. `awaitTermination(...)` chờ để quan sát việc kết thúc. **Gửi yêu cầu dừng và xác nhận đã kết thúc là hai việc riêng.**

Những API này vẫn được dùng trong Java hiện nay. Ví dụ chính chạy bằng Java 17 trở lên; phần về `close()` ghi rõ yêu cầu phiên bản mới hơn.

## 2. Bảng so sánh

| Thuộc tính | `shutdown()` | `shutdownNow()` | `awaitTermination(timeout, unit)` |
|---|---|---|---|
| Mục đích | Bắt đầu dừng có trật tự | Cố dừng tác vụ đang chạy, bỏ công việc đang chờ | Chờ executor kết thúc trong thời hạn |
| Nhận tác vụ mới sau yêu cầu dừng | Không | Không | Không tự thay đổi khả năng nhận việc |
| Tác vụ đã nằm trong hàng đợi | Vẫn được phép thực hiện | Các tác vụ đang chờ được lấy ra và trả về |
| Tác vụ đang chạy | Không yêu cầu ngắt chỉ vì gọi shutdown | Cố gắng dừng, thường bằng interrupt | Không tự ngắt tác vụ |
| Có chờ toàn bộ executor kết thúc? | Không | Không | Có, đến khi kết thúc/hết hạn/bị ngắt |
| Giá trị trả về | `void` | `List<Runnable>` chưa bắt đầu chạy | `true` nếu đã kết thúc; `false` nếu hết hạn |

Bảng mô tả ý nghĩa chung; ví dụ và các điểm về hàng đợi/Future bên dưới dùng `ThreadPoolExecutor` thông thường. Executor chuyên dụng có thể có thêm chính sách riêng. [Hợp đồng ExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html).

## 3. shutdown: đóng cửa nhận việc, cho công việc đã nhận hoàn tất

Giả sử có một luồng thực thi: A đang chạy, B và C đang chờ. Sau `shutdown()`:

```text
Ngừng nhận công việc mới
    → A tiếp tục
    → B chạy
    → C chạy
    → không còn công việc/luồng hoạt động
    → executor kết thúc
```

Đây là cách phù hợp khi ưu tiên hoàn thành những công việc đã nhận. Lời gọi `shutdown()` có thể trả về rất sớm, trong khi A/B/C còn chưa xong.

Các điểm cần hiểu:

- Gọi lặp `shutdown()` sau khi đã shutdown không tạo thêm một đợt công việc hay khởi động lại executor.
- Không có thao tác “mở lại” một executor đã shutdown; cần tạo executor mới nếu thực sự cần một vòng đời mới.
- Trong `ThreadPoolExecutor` với chính sách mặc định `AbortPolicy`, giao việc sau khi shutdown thường nhận `RejectedExecutionException`. Chính sách từ chối tùy chỉnh có thể xử lý khác, vì vậy không dựa vào việc “không thấy ngoại lệ” để kết luận việc đã được nhận.
- `shutdown()` không biến kết quả tác vụ thành thành công. Tác vụ vẫn có thể ném lỗi; cần quan sát Future hoặc cơ chế báo lỗi riêng.

Không dùng `isShutdown()` để kết luận có thể đóng ngay các tài nguyên tác vụ vẫn đang sử dụng, chẳng hạn kết nối mạng hay tệp đang ghi.

## 4. shutdownNow: yêu cầu dừng, không cưỡng chế mọi mã lập tức dừng

`shutdownNow()` có thể được gọi trực tiếp, hoặc sau `shutdown()` nếu thời gian chờ đã hết. Với `ThreadPoolExecutor`, nó cố ngắt luồng đang chạy và lấy công việc chưa bắt đầu khỏi hàng đợi.

```text
A đang chạy, B/C đang chờ
    → shutdownNow()
    → yêu cầu ngắt A
    → trả B/C cho nơi gọi
    → chờ A phản hồi và thực sự thoát
    → executor mới có thể kết thúc
```

Tên “Now” không có nghĩa khi phương thức trả về thì mọi tác vụ đã dừng. Nếu A không phản hồi tín hiệu ngắt hoặc đang chờ một thao tác không thể ngắt theo cách đó, A vẫn có thể tiếp tục. Cần tiếp tục dùng `awaitTermination` để xác nhận. [ThreadPoolExecutor.shutdownNow](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html#shutdownNow()).

### 4.1. Interrupt là cơ chế hợp tác

Tín hiệu ngắt (interrupt) là yêu cầu để tác vụ phản hồi theo hợp đồng, không phải lệnh giết luồng tại một câu lệnh bất kỳ.

- Khi tác vụ đang chờ ở một số API có thể bị ngắt, chẳng hạn `CountDownLatch.await()` hoặc `Thread.sleep()`, thao tác chờ có thể ném `InterruptedException`.
- Với vòng tính toán dài, tác vụ cần kiểm tra trạng thái ngắt tại các điểm phù hợp và thoát có kiểm soát.
- Với I/O, phải xét đúng thư viện/API; không giả định mọi lời gọi mạng đều dừng ngay khi interrupt. Thời hạn kết nối/đọc và cơ chế đóng tài nguyên vẫn cần được thiết kế.
- Dọn tài nguyên trong `finally` hoặc cơ chế đóng tương ứng để việc hủy không bỏ dở phần dọn dẹp.

Khi bắt `InterruptedException` mà không truyền nó tiếp lên cấp gọi, thường cần khôi phục cờ bằng `Thread.currentThread().interrupt()` rồi kết thúc công việc phù hợp. Chỉ khôi phục cờ nhưng tiếp tục vòng lặp vô hạn không giúp tác vụ dừng. Các phương thức như `sleep`/`wait` có thể xóa cờ khi ném ngoại lệ; tránh nuốt ngoại lệ rồi tiếp tục như chưa có yêu cầu hủy. [Thread.interrupt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#interrupt()).

### 4.2. Danh sách trả về cần được xử lý

`List<Runnable>` trả về từ `shutdownNow()` gồm các tác vụ đã chờ nhưng chưa bắt đầu, không phải mọi tác vụ đã thất bại và không chứa toàn bộ tác vụ đang chạy.

Với `submit` trong `ThreadPoolExecutor` thông thường, đối tượng nằm trong hàng đợi thường là `FutureTask`, không phải trực tiếp đối tượng Callable gốc. Việc lấy đối tượng đó ra khỏi hàng đợi **không tự bảo đảm Future đã chuyển sang trạng thái hủy**. Nếu không xử lý, nơi giữ Future có thể chờ `get()` mãi dù executor đã kết thúc.

Cần chọn chính sách cho công việc chưa chạy: đánh dấu hủy, lưu nhận dạng công việc để chuyển xử lý, hay ghi nhận chưa thực hiện. Nếu hủy các đối tượng Future đã bị lấy khỏi hàng đợi, `cancel(false)` là đủ để đánh dấu chúng vì chúng chưa chạy. Với executor có thêm lớp bọc, nên quản lý các Future đã giao từ phía chủ sở hữu thay vì giả định mọi Runnable trả về đều chính là Future người gọi giữ.

Không tự động gửi lại mọi công việc mà không xem xét danh tính, khả năng lặp an toàn và thời điểm đã tạo tác dụng phụ.

## 5. awaitTermination: chờ một điều kiện, không phát lệnh dừng

Dùng sau một yêu cầu dừng:

```java
pool.shutdown();
boolean terminated = pool.awaitTermination(5, TimeUnit.SECONDS);
```

Đây là đoạn minh họa bên trong phương thức đã có `ExecutorService pool` và xử lý/khai báo `InterruptedException`.

- `true`: executor đã kết thúc.
- `false`: khoảng thời gian chờ đã hết trước khi điều kiện kết thúc được quan sát. Executor có thể kết thúc ngay sau đó; giá trị `false` không tự làm nó dừng mạnh hơn.
- `InterruptedException`: chính **luồng đang gọi awaitTermination** bị ngắt khi chờ. Điều này khác với việc luồng thực thi tác vụ bị `shutdownNow()` ngắt.

Gọi `awaitTermination()` mà chưa shutdown không phải cách bảo executor ngừng nhận việc. Một executor đang mở có thể không có tác vụ nhưng vẫn chưa ở trạng thái terminated.

Không hiểu thời hạn chờ là cam kết toàn hệ thống chắc chắn được giải phóng đúng vào thời điểm đó. Nó giới hạn việc chờ của nơi gọi; tác vụ phớt lờ ngắt vẫn có thể tồn tại sau khi phương thức trả `false`.

## 6. Chương trình kiểm chứng đầy đủ

Thí nghiệm có một tác vụ đang chạy và một tác vụ đang chờ. Latch bảo đảm tác vụ đầu đã bắt đầu và chưa tự hoàn thành. Do đó, lời chờ ngắn sau `shutdown()` phải hết hạn; sau `shutdownNow()`, tác vụ đầu phản hồi interrupt còn tác vụ thứ hai được lấy khỏi hàng đợi.

Lưu thành `ExecutorShutdownDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ExecutorShutdownDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<Runnable>());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean queuedExecuted = new AtomicBoolean();

        try {
            Future<String> running = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                    return "released";
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return "interrupted";
                }
            });

            if (!started.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("First task did not start");
            }
            Future<String> queued = pool.submit(() -> {
                queuedExecuted.set(true);
                return "queued-result";
            });

            pool.shutdown();
            System.out.println("isShutdown: " + pool.isShutdown());
            System.out.println("finished after orderly wait: "
                    + pool.awaitTermination(50, TimeUnit.MILLISECONDS));

            List<Runnable> neverStarted = pool.shutdownNow();
            System.out.println("never started: " + neverStarted.size());
            System.out.println("queued done before cancel: " + queued.isDone());

            cancelReturnedFutures(neverStarted);
            System.out.println("running result: "
                    + running.get(10, TimeUnit.SECONDS));
            System.out.println("queued cancelled: " + queued.isCancelled());
            System.out.println("queued executed: " + queuedExecuted.get());

            boolean terminated = pool.awaitTermination(10, TimeUnit.SECONDS);
            if (!terminated) {
                throw new AssertionError("Executor did not terminate");
            }
            System.out.println("terminated: " + terminated);
        } finally {
            release.countDown();
            cancelReturnedFutures(pool.shutdownNow());
            try {
                if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Cleanup did not terminate");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private static void cancelReturnedFutures(List<Runnable> tasks) {
        for (Runnable task : tasks) {
            if (task instanceof Future<?> future) {
                future.cancel(false);
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 ExecutorShutdownDemo.java
java ExecutorShutdownDemo
```

Stdout khi thí nghiệm hoàn thành bình thường:

```text
isShutdown: true
finished after orderly wait: false
never started: 1
queued done before cancel: false
running result: interrupted
queued cancelled: true
queued executed: false
terminated: true
```

Cách đọc kết quả:

1. `isShutdown: true` chỉ xác nhận đã ngừng nhận việc.
2. `false` sau lời chờ 50 mili giây chứng minh `shutdown()` không ngắt tác vụ đang bị giữ ở latch.
3. Một tác vụ được trả về bởi `shutdownNow()`; nó chưa chạy.
4. Future tác vụ đó vẫn chưa done trước khi chương trình tự hủy nó.
5. Tác vụ đang chạy bắt ngắt và trả chuỗi `interrupted`. Future của nó hoàn thành bình thường theo mã tác vụ, không tự trở thành cancelled chỉ vì executor đã gọi `shutdownNow()`.
6. Sau khi chờ thành công, executor đã kết thúc; công việc đang chờ không được thực hiện.

Mọi dòng kết quả do luồng `main` in. Latch tạo điều kiện kiểm chứng, thay vì dựa vào thứ tự chạy ngẫu nhiên hoặc ngủ để đoán khi nào tác vụ bắt đầu.

## 7. Quy trình dừng hai giai đoạn

Trong ứng dụng cần ưu tiên hoàn thành công việc trước khi hủy, một trình tự thường dùng là:

```text
Ngừng nguồn tạo việc mới ở cấp ứng dụng
    → shutdown()
    → awaitTermination(thời gian cho phép hoàn tất)
        ├─ true → đã kết thúc
        └─ false → shutdownNow()
                    → xử lý công việc chưa chạy được trả về
                    → awaitTermination(thời gian chờ sau ngắt)
                        ├─ true → đã kết thúc
                        └─ false → ghi nhận chưa dừng, điều tra tác vụ còn giữ luồng
```

Thời gian của hai giai đoạn cần nằm trong ngân sách dừng của tiến trình. Nếu giai đoạn đầu chờ 20 giây và giai đoạn sau 10 giây, tổng thời gian chờ có thể khoảng 30 giây cộng phần xử lý khác. Khi có một hạn chót chung, nên tính thời gian còn lại theo đồng hồ đơn điệu (`System.nanoTime`) thay vì cấp lại nguyên thời gian cho từng bước.

Nếu luồng điều phối bị ngắt trong khi chờ, có thể yêu cầu dừng mạnh hơn, xử lý công việc chưa chạy rồi khôi phục trạng thái ngắt hoặc truyền `InterruptedException` lên cấp gọi. Không báo “đã dừng thành công” chỉ vì đã bắt ngoại lệ. Nếu chọn trở về ngay sau khi khôi phục cờ, cần thể hiện rõ rằng việc kết thúc chưa được xác nhận.

Không lặp chờ vô hạn khi yêu cầu vận hành cần một hạn chót. Cũng không dùng `Thread.stop()` hoặc các cách dừng luồng cưỡng chế để thay cho thiết kế hủy hợp tác.

## 8. Phân biệt trạng thái executor với kết quả tác vụ

| Câu hỏi | API/nguồn thông tin phù hợp |
|---|---|
| Executor đã ngừng nhận việc chưa? | `isShutdown()` |
| Executor đã kết thúc chưa? | `isTerminated()` hoặc kết quả `awaitTermination()` |
| Một tác vụ có thành công không? | Future hoặc cơ chế ghi nhận kết quả của tác vụ |
| Một Future đã bị hủy chưa? | `isCancelled()` |
| Công việc có để lại tác dụng phụ một phần không? | Trạng thái nghiệp vụ; không suy ra chỉ từ Future |

`awaitTermination()` trả `true` không chứng minh mọi tác vụ thành công: có thể có tác vụ ném lỗi, bị hủy hoặc bị lấy khỏi hàng đợi. Ngược lại, một Future cancelled không tự chứng minh đoạn mã đang chạy đã ngừng mọi tác dụng phụ. [Hợp đồng Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

Cần tránh gọi `awaitTermination()` từ chính một tác vụ của executor đó: executor phải chờ tác vụ hiện tại hoàn thành mới terminated, trong khi tác vụ hiện tại lại đang chờ executor. Với lời chờ có thời hạn, tình huống thường chỉ thoát khi hết hạn; chờ lặp vô hạn có thể tự làm hệ thống mắc kẹt.

## 9. Chủ sở hữu và thứ tự dọn tài nguyên

Thành phần tạo và sở hữu executor thường chịu trách nhiệm kết thúc nó. Một hàm chỉ mượn executor dùng chung để xử lý một yêu cầu không nên shutdown executor đó khi yêu cầu xong.

Khi dừng một dịch vụ có nhiều thành phần, cần xét đồ thị phụ thuộc:

- Ngừng tiếp nhận yêu cầu mới hoặc nguồn phát công việc.
- Cho công việc đã nhận hoàn tất trong giới hạn cho phép.
- Hủy hợp tác phần còn lại nếu chính sách yêu cầu.
- Xác nhận trạng thái dừng, ghi nhận công việc chưa hoàn thành.
- Đóng tài nguyên mà các tác vụ cần sau khi chúng đã ngừng sử dụng, hoặc đóng sớm có chủ đích nếu đó là cơ chế hủy của API tương ứng.

Ví dụ, đóng nguồn kết nối cơ sở dữ liệu trước khi các tác vụ ghi dữ liệu hoàn tất có thể làm giai đoạn shutdown có trật tự trở thành một loạt tác vụ lỗi. Trong khi đó, với một lời đọc bị chặn, việc đóng kênh theo đúng hợp đồng có thể là bước cần thiết để hủy. Không có một thứ tự dọn chung thay cho phân tích phụ thuộc thực tế.

Đừng dùng luồng daemon như cách thay thế quản lý vòng đời: tiến trình có thể kết thúc trước khi công việc ghi xong. Khi cần bảo đảm nghiệp vụ không mất việc, cần thêm lưu trữ công việc/trạng thái bền vững; ba API dừng executor không tự cung cấp điều đó.

## 10. close() ở Java mới có thay thế việc hiểu ba API này không?

Từ Java 19, `ExecutorService` hỗ trợ `AutoCloseable`, nên có thể dùng `try` với tài nguyên trên phiên bản phù hợp. `close()` bắt đầu dừng có trật tự và **chờ** executor kết thúc. Nó không giống lời gọi `shutdown()` chỉ phát yêu cầu rồi trả về.

Khi luồng gọi `close()` bị ngắt, hợp đồng mặc định yêu cầu cố dừng các tác vụ rồi tiếp tục chờ kết thúc, cuối cùng khôi phục trạng thái ngắt. Nếu tác vụ không hợp tác, việc đóng có thể chờ lâu. Khi cần ngân sách thời gian dừng rõ ràng, quy trình `shutdown`/`awaitTermination`/`shutdownNow` tường minh vẫn có giá trị. Ví dụ Java 17 trong bài dùng `finally` để tương thích phiên bản đó. [ExecutorService.close](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html#close()).

## 11. Lỗi phổ biến và tự kiểm tra

| Lỗi | Điều cần sửa |
|---|---|
| Gọi shutdown rồi lập tức đọc kết quả như thể mọi việc đã xong | Chờ đúng Future hoặc chờ executor kết thúc |
| Gọi awaitTermination nhưng quên phát yêu cầu shutdown | Phân biệt lệnh dừng với lời chờ |
| Gọi shutdownNow rồi báo đã dừng | Kiểm tra tác vụ có thoát và chờ xác nhận |
| Nuốt InterruptedException rồi chạy tiếp | Truyền ngắt hoặc khôi phục cờ và kết thúc thích hợp |
| Bỏ danh sách công việc chưa chạy | Ghi nhận/hủy/chuyển xử lý theo chính sách rõ ràng |
| Dùng isShutdown làm dấu hiệu công việc thành công | Kiểm tra trạng thái từng tác vụ và trạng thái nghiệp vụ |
| Dừng executor dùng chung sau mỗi yêu cầu | Đặt quyền dừng tại chủ sở hữu vòng đời |

Tự trả lời trước khi chạy lại ví dụ:

1. Nếu bỏ `shutdownNow()` và vẫn giữ tác vụ đầu ở latch, lời chờ có tự giải phóng tác vụ không? **Không.** Hết hạn chỉ kết thúc việc chờ của luồng gọi.
2. Vì sao Future của tác vụ đang chạy trả chuỗi mà không ném `CancellationException`? **Tác vụ tự bắt ngắt và trả kết quả; chương trình không gọi cancel trên Future đó.**
3. Executor terminated có bảo đảm Future bị lấy khỏi hàng đợi đã done không? **Không nên giả định như vậy.** Ví dụ chủ động hủy Future chưa chạy.
4. Có thể gọi shutdownNow sau shutdown không? **Có.** Đây là cách nâng mức yêu cầu dừng khi giai đoạn có trật tự quá hạn.

Thực hành: thay việc chặn ở latch bằng một công việc có giới hạn thời gian và cho nó hoàn thành bình thường trước hạn. Dự đoán khi nào `awaitTermination` trả `true` mà không cần ngắt. Tiếp theo, thử truyền `InterruptedException` ra khỏi Callable thay vì trả chuỗi; dự đoán `Future.get()` sẽ báo lỗi bằng `ExecutionException` với nguyên nhân tương ứng. Giữ phần dọn dẹp để chương trình không bỏ lại luồng.

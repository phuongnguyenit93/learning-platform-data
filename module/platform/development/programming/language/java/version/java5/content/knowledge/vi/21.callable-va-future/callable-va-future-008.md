# Giới hạn dừng tác vụ bằng yêu cầu ngắt

## 1. Gửi yêu cầu dừng khác với công việc đã dừng

Khi một phép tính không còn cần thiết, nơi gọi thường dùng `future.cancel(true)` để yêu cầu hủy và cho phép ngắt luồng thực thi. Nếu đang đóng cả bộ thực thi, có thể dùng `shutdownNow()` để cố ngăn công việc chờ và ngắt việc đang chạy.

Nhưng một tác vụ đang chạy không phải tệp có thể xóa khỏi hàng đợi. Nó đã có luồng thực hiện, có thể đang giữ khóa, gọi thư viện hoặc tạo tác động ra bên ngoài.

Vì vậy cần phân biệt ba sự kiện:

1. **Yêu cầu dừng được gửi**.
2. **Đối tượng kết quả được đánh dấu hủy**.
3. **Thân tác vụ thực sự thoát và dọn tài nguyên**.

Ba sự kiện có thể xảy ra ở những thời điểm khác nhau. Một cơ chế hủy có thể giải quyết trạng thái kết quả trước khi công việc vật lý kịp kết thúc.

Bài này tập trung vào giới hạn của yêu cầu ngắt, không coi việc Future đã hủy là bảo đảm mọi xử lý đã dừng.

## 2. Ngắt là một giao thức hợp tác

`Thread.interrupt()` gửi tín hiệu tới luồng đích. Trong nhiều trường hợp nó đặt trạng thái ngắt; với một số lời gọi chặn có hỗ trợ ngắt, lời gọi có thể báo `InterruptedException` hoặc phản hồi theo hợp đồng riêng.

Nó không tự chèn một lệnh `return` vào vòng lặp của ứng dụng.

Một tác vụ đáp ứng ngắt thường cần:

- Có điểm nhận biết tín hiệu, qua trạng thái ngắt hoặc ngoại lệ.
- Có đường thoát khỏi luồng xử lý chính.
- Dọn tài nguyên và chuyển trạng thái nghiệp vụ thích hợp.
- Không tiếp tục công việc như thể chưa có yêu cầu dừng.

Nếu thiếu một mắt xích, yêu cầu ngắt có thể đã được gửi đúng nhưng tác vụ vẫn không kết thúc.

Các quy tắc của luồng được mô tả trong [Thread API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html).

### Không có thời hạn phản hồi cố định

Java không bảo đảm rằng mọi tác vụ sẽ dừng trong 100 ms hay một giây sau `interrupt()`. Thời gian phản hồi phụ thuộc điểm kiểm tra, thao tác chặn, thư viện được gọi, quá trình dọn dẹp và khả năng được bộ lập lịch cấp CPU.

Một tác vụ chỉ kiểm tra ngắt giữa các đơn vị công việc kéo dài mười giây có thể phản hồi chậm dù logic kiểm tra về mặt ý tưởng là đúng.

## 3. Những trường hợp ngắt không làm tác vụ dừng như mong đợi

| Trường hợp | Vì sao yêu cầu chưa đủ? | Hướng xử lý cần xem xét |
|---|---|---|
| Vòng lặp tính toán không kiểm tra cờ | Không có điểm hợp tác | Thêm điểm kiểm tra ở ranh giới đơn vị công việc |
| Bắt `InterruptedException` rồi tiếp tục vô hạn | Tín hiệu bị tiêu thụ nhưng không đổi luồng điều khiển | Truyền ngoại lệ hoặc thoát theo chính sách |
| Khôi phục cờ rồi thử lại liên tục cùng lời gọi chặn | Có thể lặp ngoại lệ ngay | Giữ tín hiệu và dừng hoặc chuyển giai đoạn |
| Chờ đi vào `synchronized` | Xin monitor không được hủy chỉ bằng ngắt | Xem lại thiết kế khóa hoặc cách xin khóa hỗ trợ ngắt |
| I/O hoặc thư viện không hỗ trợ hủy bằng ngắt | Cơ chế chặn không có hợp đồng phản hồi tương ứng | Timeout hoặc API hủy/đóng tài nguyên cụ thể |
| Dọn dẹp cũng chặn vô hạn | Thân xử lý đã dừng nhưng bước kết thúc chưa xong | Thiết kế dọn dẹp có giới hạn |

Không có một lệnh gọi lặp lại `interrupt()` nào tự bổ sung điểm hợp tác còn thiếu trong tác vụ.

### Kiểm tra cờ cho vòng lặp

Mã minh họa:

```java
while (!Thread.currentThread().isInterrupted()) {
    processOneUnit();
}
```

`processOneUnit()` do ứng dụng định nghĩa. Nếu bản thân nó chặn vô hạn mà không hỗ trợ ngắt, điểm kiểm tra ở đầu vòng lặp vẫn chưa giải quyết được vấn đề.

Nếu cần ném ngoại lệ để truyền lên tầng gọi:

```java
if (Thread.interrupted()) {
    throw new InterruptedException("Work interrupted");
}
```

`Thread.interrupted()` kiểm tra và xóa cờ của luồng hiện tại. `isInterrupted()` chỉ đọc, không xóa. Chọn theo cách truyền tín hiệu mà phương thức đang sử dụng.

## 4. Future bị hủy có thể đi trước thời điểm thân tác vụ thoát

Với `FutureTask`, là triển khai thông dụng cho công việc gửi bằng `submit` trong nhóm luồng tiêu chuẩn, một yêu cầu hủy thành công có thể khiến:

- `isCancelled()` là `true`.
- `isDone()` là `true`.
- `get()` báo `CancellationException`.

Những thông tin ấy nói về trạng thái Future. Chúng không phải bằng chứng rằng dòng mã cuối cùng của thân `Callable` đã chạy xong.

Nếu công việc đang chạy và bỏ qua yêu cầu ngắt, nó vẫn có thể tiếp tục sử dụng CPU hoặc tài nguyên ngoài dù nơi gọi không còn nhận kết quả của nó. Hợp đồng đối tượng kết quả và thân xử lý phải được quan sát riêng khi điều đó có ý nghĩa.

Chi tiết lớp kết quả được mô tả trong [FutureTask API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/FutureTask.html).

### cancel(false) không yêu cầu ngắt

Không được đọc `false` thành “chỉ hủy nếu chưa chạy” cho mọi triển khai. Với `FutureTask`, hủy có thể được chấp nhận khi công việc đang thực thi; `false` có nghĩa không dùng ngắt để cố dừng nó. Thân công việc có thể tiếp tục trong khi Future đã hủy.

Nếu tác vụ đã hoàn tất hoặc không thể hủy, lời gọi có thể thất bại. Không giả định yêu cầu hủy luôn thắng cuộc đua với hoàn tất.

### Các triển khai Future không giống hệt nhau

`CompletableFuture.cancel(true)` không dùng tham số `true` để ngắt xử lý. Trong triển khai này, hủy là một dạng hoàn tất do lỗi; nó không trực tiếp điều khiển phép tính tạo kết quả như `FutureTask`.

Vì vậy, không viết một quy tắc chung “mọi Future.cancel(true) đều ngắt luồng đang chạy”. Phải hiểu đối tượng đang dùng và quyền kiểm soát công việc của nó. Xem [CompletableFuture API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html#cancel(boolean)).

## 5. Thí nghiệm Java 17+: Future đã hủy nhưng thân tác vụ còn sống

Ví dụ sau **cố ý tạo một tác vụ không thoát khi nhận ngắt**, để chứng minh giới hạn. Nó chỉ kết thúc khi `main` mở chốt riêng. Đây là thí nghiệm có đường giải phóng rõ ràng, không phải mẫu xử lý ngắt nên sao chép vào công việc thật.

Lưu thành **`InterruptLimitDemo.java`**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class InterruptLimitDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch interruptObserved = new CountDownLatch(1);
        CountDownLatch allowExit = new CountDownLatch(1);
        CountDownLatch bodyExited = new CountDownLatch(1);

        try {
            Future<String> future = pool.submit(() -> {
                boolean interrupted = false;
                started.countDown();
                try {
                    for (;;) {
                        try {
                            allowExit.await();
                            break;
                        } catch (InterruptedException e) {
                            // Deliberately continue for this experiment.
                            interrupted = true;
                            interruptObserved.countDown();
                        }
                    }
                    return "body returned";
                } finally {
                    if (interrupted) {
                        Thread.currentThread().interrupt();
                    }
                    bodyExited.countDown();
                }
            });

            started.await();

            System.out.println(
                    "cancel accepted: " + future.cancel(true));

            if (!interruptObserved.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Interrupt not observed");
            }

            System.out.println("future done: " + future.isDone());
            System.out.println(
                    "body exited before release: "
                    + (bodyExited.getCount() == 0));

            try {
                future.get();
            } catch (CancellationException e) {
                System.out.println(
                        "get: " + e.getClass().getSimpleName());
            }

            allowExit.countDown();

            if (!bodyExited.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Body did not exit");
            }
            System.out.println(
                    "body exited after release: "
                    + (bodyExited.getCount() == 0));
        } finally {
            allowExit.countDown();
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
javac --release 17 InterruptLimitDemo.java
java InterruptLimitDemo
```

Stdout chính xác:

```text
cancel accepted: true
future done: true
body exited before release: false
get: CancellationException
body exited after release: true
```

### Diễn giải thí nghiệm

Chốt `started` bảo đảm công việc đã vào thân tác vụ trước khi yêu cầu hủy được gửi.

Sau `cancel(true)`, công việc nhận `InterruptedException` từ đường chờ và thông báo bằng `interruptObserved`. Tuy vậy, khối `catch` cố ý tiếp tục vòng lặp. Vì `allowExit` vẫn đóng, thân tác vụ chưa thể đi tới `finally`.

Lúc đó Future đã xong theo trạng thái hủy, còn `bodyExited` xác nhận thân công việc chưa thoát. Chỉ khi `main` mở chốt, thân công việc mới kết thúc.

Giá trị `"body returned"` không trở thành kết quả thành công để nơi gọi lấy sau đó, vì Future đã bị hủy. Việc mã công việc cuối cùng có thể đi tới `return` không đảo ngược trạng thái hủy.

Các chốt dùng để chứng minh thứ tự, không dùng `sleep` để đoán thời điểm. Các timeout năm giây chỉ giúp phát hiện thử nghiệm không tiến triển như dự kiến. Trong ứng dụng thật, nên làm tác vụ phản hồi ngắt bằng đường thoát rõ ràng thay vì cố ý tiếp tục như thí nghiệm này.

## 6. Dừng cả executor cũng có giới hạn tương tự

`shutdownNow()` thường cố ngắt luồng xử lý đang chạy và lấy những công việc chưa bắt đầu khỏi hàng đợi. Nó không chờ mọi việc thực sự dừng trước khi trả về.

Nếu một tác vụ tiếp tục như trong ví dụ, executor chưa thể kết thúc chỉ vì đã nhận lệnh dừng. Cần chờ kết thúc bằng `awaitTermination(...)` và kiểm tra kết quả.

Không xem:

```java
pool.shutdownNow();
```

là một cách đồng bộ tương đương với “đến đây mọi tài nguyên của các tác vụ đã được trả lại”.

Quy trình thường dùng là ngừng đầu vào, yêu cầu dừng có trật tự, chờ trong một khoảng, rồi tăng mức yêu cầu dừng nếu cần. Nếu sau thời hạn vẫn còn công việc, phải báo trạng thái ấy và tìm nguyên nhân cụ thể.

Đối với những việc chưa bắt đầu, danh sách lấy khỏi hàng đợi cần được xử lý theo quyền sở hữu ứng dụng; không tự giả định mọi Future tương ứng đã được hủy.

Giới hạn của yêu cầu dừng và thao tác chờ được mô tả trong [ExecutorService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html).

## 7. Timeout của nơi chờ không phải thời hạn của tác vụ

`future.get(1, TimeUnit.SECONDS)` hết hạn chỉ khiến nơi gọi nhận `TimeoutException`. Nó không tự gửi ngắt.

Ngay cả khi sau timeout nơi gọi tiếp tục gọi `cancel(true)`, vẫn chỉ là yêu cầu hủy theo khả năng của triển khai và tác vụ.

Một thiết kế cần tách rõ:

- **Ngân sách chờ kết quả** của người gọi.
- **Thời hạn thực hiện** mà công việc tự kiểm tra hoặc API con hỗ trợ.
- **Thời gian cho dọn dẹp** sau yêu cầu dừng.
- **Thời điểm báo không thể xác nhận kết thúc**.

Nếu gọi nhiều dịch vụ con, mỗi dịch vụ có timeout riêng không tự bảo đảm tổng thời gian ở trong ngân sách chung. Cần tính phần thời gian còn lại cho các bước tiếp theo.

Với đo khoảng thời gian trôi qua trong tiến trình, thường dùng đồng hồ đơn điệu như `System.nanoTime()`, không dựa vào đồng hồ lịch có thể được điều chỉnh. Việc hết thời hạn vẫn cần có điểm kiểm tra và đường thoát.

## 8. I/O, khóa và mã bên ngoài cần cơ chế cụ thể

### Không phải I/O nào cũng phản hồi giống nhau

Một số API phản hồi ngắt; một số cần timeout hoặc thao tác hủy riêng. Không mặc định rằng gửi ngắt sẽ làm mọi lời gọi mạng hoặc cơ sở dữ liệu trở về ngay.

Ví dụ, một thao tác đang chặn trên `InterruptibleChannel` có thể bị ngắt bằng cách đóng channel và ném `ClosedByInterruptException`. Tài nguyên có thể không còn dùng lại được như trước.

Đây là lý do phải kiểm tra hợp đồng của tài nguyên cụ thể, không chỉ lớp `Thread`. Xem [InterruptibleChannel API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/InterruptibleChannel.html).

Không tùy tiện đóng tài nguyên mà nhiều công việc cùng dùng: thao tác đó có thể làm gián đoạn các công việc khác ngoài phạm vi được hủy.

### Chờ khóa

Ngắt không làm luồng đang chờ đi vào `synchronized` tự bỏ việc xin monitor. Nếu cần thời hạn hoặc hỗ trợ ngắt khi xin khóa, phải chọn cơ chế khóa và hợp đồng phù hợp.

### Thư viện hoặc mã không do mình kiểm soát

Nếu một lời gọi bên ngoài không cung cấp khả năng hủy đáng tin cậy, không thể thêm một `Future` bao quanh rồi tuyên bố đã có bảo đảm dừng cứng.

Khi yêu cầu bắt buộc phải có ranh giới cách ly mạnh hơn cho mã không kiểm soát được, có thể cần thiết kế xử lý trong tiến trình riêng và chính sách quản lý tiến trình ở cấp hệ thống. Đó là quyết định kiến trúc; kết thúc một tiến trình cũng không tự hoàn tác tác động đã gửi ra bên ngoài.

## 9. Thiết kế tác vụ có khả năng dừng

Một tác vụ hợp tác có thể tổ chức theo chuỗi:

```text
Nhận một đơn vị công việc
    -> kiểm tra yêu cầu dừng
    -> thực hiện bước có giới hạn
    -> công bố kết quả phù hợp
    -> tiếp tục hoặc dọn dẹp và thoát
```

Các lựa chọn thực tế:

1. Chia phép tính dài thành các đơn vị có thời gian xử lý hợp lý.
2. Dùng lời gọi chặn có hỗ trợ ngắt hoặc timeout theo hợp đồng thư viện.
3. Truyền `InterruptedException` khi phương thức không sở hữu chính sách dừng.
4. Nếu không truyền được, giữ tín hiệu khi thích hợp và thoát công việc.
5. Giải phóng tài nguyên đã sở hữu bằng `finally` hoặc try-with-resources.
6. Có cách quan sát việc thân công việc thực sự kết thúc nếu nghiệp vụ cần xác nhận.

Không chỉ thêm một biến `volatile boolean stopped` rồi cho rằng mọi lời gọi chặn sẽ được đánh thức. Cờ riêng có thể hữu ích cho giao thức hủy, nhưng không tự làm một API đang chặn trở về.

## 10. Hủy không tự hoàn tác tác động

Nếu tác vụ đã gửi email, tạo thanh toán hoặc commit dữ liệu trước lúc nhận ngắt, việc đánh dấu Future hủy không xóa các tác động đó.

Nơi gọi không nhận được kết quả có thể có nhiều nguyên nhân:

- Công việc chưa bắt đầu.
- Đang xử lý.
- Đã tạo tác động nhưng chưa công bố kết quả.
- Đã hoàn tất gần như đồng thời với yêu cầu hủy.

Vì vậy, trước khi thử lại cần có cách xác định trạng thái nghiệp vụ hoặc chống tác động lặp, chẳng hạn mã yêu cầu ổn định và quy tắc xử lý lặp ở nơi nhận.

Với công việc nhiều bước, cần thiết kế điểm cam kết, giao dịch hoặc bước bù phù hợp. Tín hiệu ngắt là cơ chế điều phối thực thi, không phải hệ thống giao dịch.

## 11. Những kết luận không được suy diễn

| Điều quan sát được | Không đủ để kết luận |
|---|---|
| Đã gọi `interrupt()` | Luồng đã thoát |
| `cancel(true)` được chấp nhận | Mọi tác động của công việc đã dừng và được hoàn tác |
| `future.isDone()` là true | Thân công việc đã kết thúc vật lý |
| `get(timeout)` hết hạn | Công việc đã bị hủy |
| `shutdownNow()` trả về | Executor đã kết thúc |
| Không còn nhận kết quả | Công việc chưa tạo tác động nghiệp vụ |

Khi cần xác nhận kết thúc, dùng cơ chế phản ánh đúng điều cần biết: trạng thái nghiệp vụ, tín hiệu hoàn tất dọn dẹp, `join` khi trực tiếp quản lý một luồng, hoặc trạng thái kết thúc của executor khi sở hữu toàn bộ nhóm.

Không gọi `get()` trên một Future đã hủy để chờ thân công việc dọn xong: nó sẽ phản hồi trạng thái hủy, không chờ theo ý nghĩa ấy.

## 12. Tự kiểm tra

1. Vì sao Future có thể `isDone() == true` nhưng tác vụ vẫn sử dụng tài nguyên?
2. Một vòng lặp không kiểm tra cờ và không gọi API hỗ trợ ngắt có tự ném `InterruptedException` không?
3. `CompletableFuture.cancel(true)` có cùng cam kết ngắt như FutureTask không?
4. Vì sao hết timeout rồi retry ngay có thể gây tác động nghiệp vụ lặp?
5. Nếu việc dọn dẹp cũng chặn vô hạn, tác vụ đã được xem là dừng hoàn toàn chưa?
6. Muốn biết một công việc đã giải phóng tài nguyên sau hủy, chỉ nhìn `isCancelled()` có đủ không?

**Gợi ý:** (1) Trạng thái kết quả có thể chuyển sang hủy trước khi mã hợp tác thoát. (2) Không. (3) Không; CompletableFuture không dùng tham số đó để điều khiển xử lý bằng ngắt. (4) Công việc trước có thể đã hoặc vẫn đang tạo tác động. (5) Chưa. (6) Không; cần tín hiệu phản ánh việc dọn dẹp thực sự hoàn tất.

Giới hạn cốt lõi là: **yêu cầu ngắt chỉ mở đường cho tác vụ hợp tác dừng; bảo đảm kết thúc và tính đúng nghiệp vụ phải được thiết kế thêm**.

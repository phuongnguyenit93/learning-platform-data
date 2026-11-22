# Kiểm thử dừng tác vụ bằng tín hiệu ngắt

## 1. Kiểm thử một giao thức hợp tác

`interrupt()` là yêu cầu để luồng đang chạy hợp tác dừng hoặc thay đổi cách xử lý. Nó không phải lệnh cưỡng bức giết luồng.

Vì vậy, một phép kiểm thử tốt không chỉ gọi `interrupt()` rồi kiểm tra rằng lời gọi đã trả về. Nó cần chứng minh chuỗi hành vi:

```text
Tác vụ đã bắt đầu
        ↓
Bên kiểm thử gửi ngắt
        ↓
Tác vụ nhận biết ngắt
        ↓
Thoát phần việc và dọn dẹp
        ↓
Tác vụ hoặc luồng kết thúc theo hợp đồng
```

Điểm cần kiểm tra phụ thuộc mô hình thực thi. Với một Thread chuyên chạy một tác vụ, có thể đợi Thread kết thúc. Với nhóm thực thi tái sử dụng luồng, mục tiêu là thân tác vụ kết thúc và trả tài nguyên; không yêu cầu luồng phục vụ phải chết.

Bài dùng các cơ chế vẫn áp dụng trong Java hiện đại, với chương trình chạy trên JDK 17 trở lên. Không dùng các phương thức dừng luồng cưỡng bức đã lỗi thời.

## 2. Hai cách tác vụ nhận biết ngắt

### Đang chờ ở một API có thể bị ngắt

Các thao tác như `BlockingQueue.take()`, `CountDownLatch.await()` hoặc `Thread.sleep()` có thể ném `InterruptedException`.

Một mẫu ở ranh giới Runnable:

```java
try {
    process(queue.take());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

Đây là đoạn minh họa; `queue` và `process` đại diện cho công việc thực tế. Khi không thể truyền ngoại lệ đã kiểm tra lên tầng gọi, thường khôi phục trạng thái ngắt rồi kết thúc đường xử lý phụ thuộc vào việc chờ.

Khi một thao tác chờ ném `InterruptedException`, cờ ngắt được xóa theo hợp đồng của thao tác đó. Nếu hợp đồng tác vụ yêu cầu khôi phục cờ, kiểm thử phải quan sát nó ngay ở vị trí phù hợp trong tác vụ; không suy ra từ một luồng khác rằng cờ sẽ còn nguyên mãi.

### Đang tính toán hoặc chạy vòng lặp

Đoạn tính toán không gọi API chờ có thể không tự ném ngoại lệ. Nó cần chủ động kiểm tra ở các điểm có thể dừng an toàn:

```java
while (!Thread.currentThread().isInterrupted()) {
    processOneBoundedUnit();
}
```

`processOneBoundedUnit` là một đơn vị công việc hữu hạn. Nếu nó có thể chạy rất lâu mà không kiểm tra ngắt, độ trễ dừng vẫn lớn.

`isInterrupted()` kiểm tra mà không xóa cờ. `Thread.interrupted()` kiểm tra và xóa cờ của chính luồng đang gọi. Vô tình dùng biến thể xóa cờ ở một hàm phụ có thể làm lớp ngoài bỏ lỡ yêu cầu dừng.

Kiểm thử nên bao gồm cả đường thoát bằng ngoại lệ và đường thoát bằng kiểm tra cờ nếu tác vụ thực tế có cả hai.

## 3. Không dùng sleep để đoán tác vụ đã sẵn sàng

Mẫu dễ gây kiểm thử chập chờn:

```java
worker.start();
Thread.sleep(100);
worker.interrupt();
```

Một trăm mili giây không chứng minh worker đã chạy tới vị trí cần kiểm tra. Trên máy chậm, nó có thể chưa được lập lịch; trên máy nhanh, nó có thể đã hoàn tất công việc theo một đường khác.

Dùng một tín hiệu được đặt tại điểm cụ thể:

```text
Worker: báo started → thực hiện thao tác chờ
Test:   đợi started → interrupt(worker)
```

Vẫn cần phân biệt điều tín hiệu chứng minh. Nếu worker báo ngay trước `queue.take()`, nó chứng minh worker đã tới ranh giới đó, không chứng minh nó đã bị treo trong take.

Điều này thường đủ để kiểm thử hợp đồng hủy: dù ngắt tới ngay trước lời gọi hay trong lúc chờ, tác vụ vẫn phải dừng đúng. Nếu mục tiêu riêng là khảo sát một trạng thái chờ nội bộ, cần dụng cụ kiểm thử hoặc bằng chứng phù hợp hơn; đừng giả vờ rằng một latch trước lời gọi chứng minh được vị trí bên trong lời gọi.

Cũng không dùng `Thread.getState()` như giao thức điều khiển nghiệp vụ. Trạng thái chỉ là ảnh chụp theo thời điểm và có thể đổi ngay sau khi đọc.

## 4. Ví dụ chạy được: kiểm tra đường chờ và đường tính toán

Chương trình dùng kiểm tra tường minh bằng `AssertionError`, nên không cần bật `-ea`. Nếu bất kỳ điều kiện bắt buộc nào sai, chương trình thất bại thay vì chỉ in một thông báo.

Lưu thành `InterruptStopTest.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class InterruptStopTest {
    private static final long WAIT_MILLIS = 5000;

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void joinAndCheck(Thread worker)
            throws InterruptedException {
        worker.join(WAIT_MILLIS);
        check(!worker.isAlive(), "Worker did not terminate");
    }

    private static void blockingCase() throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        CountDownLatch started = new CountDownLatch(1);
        boolean[] observed = new boolean[3];

        Thread worker = new Thread(() -> {
            try {
                started.countDown();
                queue.take();
                throw new AssertionError("Empty queue unexpectedly returned");
            } catch (InterruptedException e) {
                observed[0] = true;
                Thread.currentThread().interrupt();
                observed[1] = Thread.currentThread().isInterrupted();
            } finally {
                observed[2] = true;
            }
        }, "interrupt-test-blocking");

        worker.setDaemon(true);
        worker.start();
        try {
            check(started.await(WAIT_MILLIS, TimeUnit.MILLISECONDS),
                    "Worker did not reach the test point");

            worker.interrupt();
            joinAndCheck(worker);

            check(observed[0], "InterruptedException was not observed");
            check(observed[1], "Interrupt status was not restored");
            check(observed[2], "Cleanup was not executed");
            System.out.println("blocking=PASS");
        } finally {
            worker.interrupt();
            joinAndCheck(worker);
        }
    }

    private static void pollingCase() throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        boolean[] observed = new boolean[2];

        Thread worker = new Thread(() -> {
            try {
                started.countDown();
                while (!Thread.currentThread().isInterrupted()) {
                    Thread.onSpinWait();
                }
                observed[0] = true;
            } finally {
                observed[1] = true;
            }
        }, "interrupt-test-polling");

        worker.setDaemon(true);
        worker.start();
        try {
            check(started.await(WAIT_MILLIS, TimeUnit.MILLISECONDS),
                    "Worker did not start the polling loop");

            worker.interrupt();
            joinAndCheck(worker);

            check(observed[0], "Polling did not observe interruption");
            check(observed[1], "Cleanup was not executed");
            System.out.println("polling=PASS");
        } finally {
            worker.interrupt();
            joinAndCheck(worker);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        blockingCase();
        pollingCase();
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 InterruptStopTest.java
java InterruptStopTest
```

Stdout khi môi trường lập lịch được các luồng trong thời hạn kiểm thử:

```text
blocking=PASS
polling=PASS
```

### Vì sao ví dụ không dựa vào may rủi của thời gian ngủ?

Ở trường hợp đầu, queue ban đầu rỗng và không có bên thêm phần tử. Worker không thể hoàn tất bằng đường nhận dữ liệu bình thường. Sau khi nhận tín hiệu started, test gửi ngắt. Nếu worker chưa vào take thì take nhận trạng thái ngắt đã có; nếu đã vào thì việc chờ bị ngắt.

Ở trường hợp thứ hai, vòng lặp chỉ thoát khi quan sát thấy cờ ngắt. `Thread.onSpinWait()` là gợi ý cho vòng quay trong thí nghiệm, không phải thao tác tạo đồng bộ hay cơ chế tự dừng.

Hai mảng boolean không cần volatile ở ví dụ này: mỗi mảng do một worker ghi và luồng kiểm thử chỉ đọc sau khi đã xác nhận worker kết thúc bằng join. Chính quy tắc công bố đó làm kết quả quan sát đáng tin, không phải vì boolean “đủ nhỏ”.

### Daemon chỉ là lớp giới hạn hậu quả của kiểm thử lỗi

Các worker thử nghiệm được đặt daemon để một phiên bản hỏng, không chịu dừng, không giữ JVM sống vô hạn sau khi test đã thất bại. Test vẫn bắt buộc join có thời hạn và kiểm tra `isAlive`; daemon không biến thất bại thành thành công.

Không áp dụng thay đổi daemon như cách sửa tác vụ sản xuất. Tài nguyên và công việc vẫn phải được dừng, dọn dẹp đúng. Với kiểm thử có thể tạo tác vụ thực sự không dừng được, môi trường chạy test nên có thêm giới hạn ở tiến trình riêng để tránh luồng lỗi ảnh hưởng các bài kiểm thử sau.

## 5. Chọn điều kiện kiểm tra theo hợp đồng

Ít nhất nên phân biệt bốn điều:

| Điều cần chứng minh | Bằng chứng phù hợp |
| --- | --- |
| Tác vụ đã đi vào phạm vi muốn kiểm thử | Tín hiệu started tại đúng điểm |
| Tác vụ xử lý yêu cầu ngắt | Cờ/kết quả được ghi tại nhánh xử lý ngắt |
| Tài nguyên được trả hoặc đóng | Xác nhận trong finally hoặc kiểm tra trạng thái tài nguyên sau khi tác vụ kết thúc |
| Tác vụ không tiếp tục chạy vô hạn | Mốc kết thúc có thời hạn; với Thread riêng thì join và isAlive |

Chỉ kiểm tra “finally chạy” có thể chưa đủ: tác vụ vẫn có thể chạy thêm sau khối đó nếu cấu trúc chương trình cho phép. Chỉ kiểm tra “luồng chết” cũng chưa đủ: nó có thể chết bởi lỗi ngoài ý muốn mà không xử lý ngắt đúng.

Trong ví dụ, việc quan sát nhánh ngắt cùng với cleanup và kết thúc luồng tạo bằng chứng mạnh hơn từng kiểm tra riêng.

Với tài nguyên thật, không chỉ đặt `cleaned = true` rồi coi đã kiểm chứng việc đóng. Hãy dùng tài nguyên giả có thể quan sát, bộ đếm giấy phép hoặc trạng thái phù hợp để xác minh hành vi thực. Đồng thời thu nhận ngoại lệ trong worker; lỗi trên luồng con không được tự động biến thành lỗi test trên mọi môi trường chạy.

## 6. Với Future.cancel(true), trạng thái hủy khác với kết thúc thân tác vụ

Khi dùng executor, thường gửi yêu cầu dừng bằng:

```java
future.cancel(true);
```

Đây là đoạn gọi minh họa. Tham số true cho phép cơ chế hủy thử ngắt luồng đang chạy tác vụ khi triển khai biết luồng đó.

Nhưng `future.isCancelled()`, `future.isDone()` hoặc `CancellationException` từ get không tự chứng minh toàn bộ thân tác vụ đã dừng và dọn dẹp xong. Một tác vụ bỏ qua ngắt vẫn có thể còn chạy sau khi future đã báo hủy.

Kiểm thử đường “đã chạy rồi bị hủy” nên có trình tự:

1. Nộp tác vụ và đợi tín hiệu started.
2. Gọi cancel(true) và kiểm tra kết quả hủy theo hợp đồng sử dụng.
3. Đợi một tín hiệu exited riêng ở cuối đường dọn dẹp của tác vụ.
4. Kiểm tra tài nguyên và các tác dụng phụ quan trọng.
5. Dừng executor do test sở hữu và chờ kết thúc theo thời hạn.

Tín hiệu exited trong finally không tự xuất hiện nếu tác vụ bị hủy trước khi bắt đầu. Đó là lý do đợi started quan trọng khi test chủ ý kiểm tra hủy một tác vụ đang chạy. Cần một ca kiểm thử khác cho tác vụ chưa bắt đầu, thay vì trộn hai tình huống và cho kết quả không xác định.

Không lấy một worker trong pool rồi interrupt trực tiếp từ nơi giữ tham chiếu cũ: luồng đó có thể đã chuyển sang chạy tác vụ khác. Future là tay cầm gắn với tác vụ; Thread là đối tượng thực thi có vòng đời khác.

Tương tự, `shutdownNow()` yêu cầu dừng và thường dùng ngắt cho công việc đang chạy, nhưng không bảo đảm mọi công việc dừng tức thời. Vẫn cần chờ kết thúc và kiểm tra giao thức hợp tác.

## 7. Giới hạn thời gian để phát hiện lỗi, không để chứng minh đúng

Mốc năm giây trong ví dụ là giới hạn để test không chờ vô hạn. Nó không có nghĩa tác vụ được phép tiêu tốn đúng năm giây trong mọi yêu cầu thực tế.

Chọn giới hạn đủ rộng cho môi trường CI và tải máy, nhưng vẫn hữu hạn. Khi test thất bại do quá hạn, nên lưu:

- Tên tác vụ/luồng.
- Điểm cuối đã báo.
- Trạng thái và stack nếu lấy được.
- Có ngắt hoặc lỗi ở luồng kiểm thử hay không.
- Trạng thái tài nguyên và hàng đợi liên quan.

Không viết kiểm tra kiểu “phải dừng trong 1 mili giây” để đo một hợp đồng logic nếu hệ thống không cam kết giới hạn đó. Ngược lại, không tăng thời gian vô hạn để che tác vụ không kiểm tra ngắt.

Một kiểm thử chạy thành công nhiều lần giúp phát hiện thêm lịch thực thi, nhưng không thay thế lập luận về điểm đồng bộ. Không thêm sleep ngẫu nhiên để biến lỗi biến mất rồi coi là đã sửa.

## 8. Những lỗi mà ca kiểm thử nên bắt được

### Nuốt ngắt và tiếp tục vòng lặp

```java
// SAI với hợp đồng yêu cầu dừng khi bị ngắt.
for (;;) {
    try {
        process(queue.take());
    } catch (InterruptedException e) {
        // Bỏ qua rồi đợi tiếp.
    }
}
```

Một test chỉ kiểm tra đã gọi interrupt vẫn qua; test kiểm tra tác vụ thoát sẽ thất bại.

### Khôi phục cờ nhưng không thoát hợp lý

Nếu catch khôi phục cờ rồi lập tức gọi lại một thao tác chờ có thể bị ngắt trong vòng lặp vô hạn, nó có thể liên tục ném ngoại lệ và quay CPU. Khôi phục là bảo toàn thông tin, không tự quyết định đường thoát.

### Chỉ kiểm tra ngắt quá xa nhau

Một vòng tính toán gồm đơn vị quá lớn có thể phản hồi rất chậm. Cần chia thành những bước có thể dừng an toàn và kiểm thử ở tải đại diện, bên cạnh ca nhỏ kiểm chứng nhánh logic.

### Trả tài nguyên dù chưa lấy được

Nếu bị ngắt trong acquire, một finally đặt sai có thể release giấy phép chưa lấy. Test hủy phải kiểm tra cả sức chứa sau cùng, không chỉ việc worker đã thoát.

### Cho rằng mọi chờ đều phản ứng giống nhau

Chờ lấy monitor bằng synchronized không phải lời gọi chờ có thể bị ngắt như `lockInterruptibly`. Hành vi I/O cũng tùy API cụ thể. Không khẳng định interrupt sẽ đánh thức mọi thao tác chặn; đọc hợp đồng của thao tác thật mà tác vụ sử dụng.

Một tín hiệu ngắt cũng không hoàn tác yêu cầu mạng, ghi cơ sở dữ liệu hoặc tác dụng phụ đã thực hiện. Kiểm thử dừng cần xác định phần nào được hoàn tất, phần nào bị bỏ và cách giữ tính nhất quán.

## 9. Tự luyện thiết kế ca kiểm thử

Với một worker lấy dữ liệu từ hàng đợi và dùng một giấy phép để xử lý, hãy tạo các ca riêng:

1. Ngắt khi đang đợi dữ liệu.
2. Ngắt trước khi bắt đầu thao tác có thể bị ngắt.
3. Ngắt khi đang đợi giấy phép.
4. Ngắt trong đoạn tính toán có điểm kiểm tra cờ.
5. Công việc hoàn tất bình thường trước khi gửi yêu cầu hủy.
6. Hủy khi tác vụ còn trong hàng đợi và chưa chạy.

Với mỗi ca, viết trước kết quả chấp nhận được, điểm đồng bộ để tạo điều kiện, tài nguyên phải được trả và bằng chứng tác vụ đã kết thúc. Một số cuộc đua hợp lệ có thể dẫn tới nhiều kết quả; nếu ca kiểm thử cần một kết quả duy nhất thì phải điều khiển điều kiện của ca đó đủ rõ.

Mục tiêu là chứng minh tác vụ hợp tác với yêu cầu dừng và để lại trạng thái đúng, không chỉ chứng minh rằng API interrupt có thể được gọi.

## Tài liệu đối chiếu

- [Thread — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): interrupt, trạng thái ngắt và chờ kết thúc.
- [Future — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html): hợp đồng hủy tác vụ.
- [BlockingQueue — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html): các thao tác chờ trên hàng đợi.

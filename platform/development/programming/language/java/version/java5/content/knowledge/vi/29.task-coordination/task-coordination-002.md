# CountDownLatch và bộ đếm hoàn tất một lần

## 1. Cần phối hợp theo mốc, không theo thời gian đoán trước

Giả sử một chương trình chia công việc thành ba phần: mỗi tác vụ tính một kết quả, rồi luồng điều phối tổng hợp cả ba. Ta cần điều kiện:

> Chỉ đọc kết quả tổng hợp sau khi cả ba tác vụ đã đi qua mốc hoàn tất.

Dùng `Thread.sleep(1000)` không biểu diễn được điều kiện đó. Có máy hoàn tất sớm hơn một giây, có máy chậm hơn. Thời gian đã trôi qua không chứng minh công việc đã xong.

`CountDownLatch` giải quyết việc chờ theo **một số lượng tín hiệu hoàn tất**. Có thể hình dung một cánh cổng:

```text
Khởi tạo 3
    ↓ tác vụ 1 phát tín hiệu
Còn 2
    ↓ tác vụ 2 phát tín hiệu
Còn 1
    ↓ tác vụ 3 phát tín hiệu
Còn 0 → cổng mở cho các luồng đang chờ
```

Latch phù hợp với một đợt công việc có số mốc đã biết. Ví dụ: chờ các phần khởi tạo xong, chờ nhiều phần tính toán kết thúc hoặc giữ các tác vụ lại cho đến khi luồng điều phối phát lệnh bắt đầu.

## 2. Hợp đồng cơ bản

`CountDownLatch` thuộc gói `java.util.concurrent` và vẫn là công cụ phối hợp được hỗ trợ trên các JDK hiện đại.

| Thao tác | Ý nghĩa |
| --- | --- |
| `new CountDownLatch(n)` | Tạo bộ đếm ban đầu; `n` không âm |
| `countDown()` | Giảm một đơn vị nếu bộ đếm còn lớn hơn 0 |
| `await()` | Chờ đến khi bộ đếm bằng 0, hoặc bị ngắt |
| `await(timeout, unit)` | Chờ có giới hạn; trả `true` khi đã mở, `false` nếu hết thời gian |
| `getCount()` | Quan sát số đếm tại thời điểm gọi |

Khi đếm về 0, mọi luồng đang chờ được phép tiếp tục; các lần chờ sau cũng đi qua ngay nếu không có tình trạng ngắt theo hợp đồng của `await`. `countDown()` không đợi các bên khác cùng đến. Latch không có thao tác đặt lại bộ đếm. Xem [hợp đồng CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html).

Các điểm cần diễn giải đúng:

- **Đếm tín hiệu, không đếm danh tính luồng.** Một luồng có thể phát nhiều tín hiệu nếu giao thức công việc yêu cầu; một tác vụ cũng có thể chạy trên bất kỳ luồng nào của nhóm thực thi.
- **Một lần** nghĩa là cổng chỉ chuyển từ chưa mở sang đã mở một lần. Không có chiều từ 0 quay về N trên cùng đối tượng.
- **Chờ hoàn tất** nghĩa là chờ những mốc mà chương trình chọn để gọi `countDown()`. Nó không tự theo dõi tiến trình công việc.
- Gọi `countDown()` khi đã bằng 0 không làm số đếm âm. Tuy nhiên, gọi thừa trước khi đủ các mốc thật sự xảy ra có thể mở cổng sớm.

## 3. Thiết kế giao thức trước khi viết mã

Với một đợt N tác vụ, cần xác định ba trách nhiệm:

1. **Đăng ký:** số đếm N biểu diễn chính xác N mốc nào?
2. **Báo hoàn tất:** ai chịu trách nhiệm gọi `countDown()` đúng một lần cho từng mốc?
3. **Đọc kết quả:** ai gọi `await()`, sau đó lấy kết quả và xử lý lỗi?

Với trường hợp “chờ mọi tác vụ đã kết thúc xử lý, kể cả xử lý thất bại”, `countDown()` thường nằm trong `finally`:

```java
// Mã minh họa, các tên hàm biểu diễn logic riêng của ứng dụng.
try {
    processTask();
} finally {
    done.countDown();
}
```

Điều này bảo đảm tín hiệu vẫn được phát khi phần `try` thoát do ngoại lệ. Nó không tự biến ngoại lệ thành một kết quả có thể đọc; cần lưu lỗi hoặc dùng một cơ chế nhận lỗi riêng.

Với trường hợp “chờ khởi tạo thành công”, tín hiệu thất bại cần được thiết kế rõ. Nếu chỉ bỏ qua `countDown()` khi lỗi, luồng điều phối có thể chờ vô hạn. Nếu vẫn giảm đếm, luồng điều phối phải kiểm tra trạng thái khởi tạo để không nhầm “đã kết thúc” thành “đã sẵn sàng”.

## 4. Ví dụ đầy đủ: đợi ba tác vụ và tổng hợp cả lỗi

Chương trình cố ý cho tác vụ thứ hai thất bại. Mỗi tác vụ ghi kết quả hoặc lỗi vào một ô riêng, rồi giảm latch trong `finally`. Luồng chính chỉ đọc sau khi `await` thành công.

Tệp `LatchCompletionDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class LatchCompletionDemo {
    public static void main(String[] args) throws InterruptedException {
        int tasks = 3;
        CountDownLatch done = new CountDownLatch(tasks);
        int[] results = new int[tasks];
        RuntimeException[] failures = new RuntimeException[tasks];
        ExecutorService pool = Executors.newFixedThreadPool(tasks);

        try {
            for (int i = 0; i < tasks; i++) {
                final int index = i;
                pool.execute(() -> {
                    try {
                        if (index == 1) {
                            throw new IllegalArgumentException("rejected input");
                        }
                        results[index] = (index + 1) * 10;
                    } catch (RuntimeException failure) {
                        failures[index] = failure;
                    } finally {
                        done.countDown();
                    }
                });
            }
            pool.shutdown();

            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Tasks did not finish in time");
            }

            int successful = 0;
            for (int i = 0; i < tasks; i++) {
                if (failures[i] == null) {
                    System.out.println("task-" + i + "=" + results[i]);
                    successful++;
                } else {
                    System.out.println("task-" + i + "=FAILED: "
                            + failures[i].getMessage());
                }
            }
            System.out.println("completed=" + (tasks - done.getCount()));
            System.out.println("successful=" + successful);
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 LatchCompletionDemo.java
java LatchCompletionDemo
```

Kết quả của lần chạy hoàn tất trong thời hạn:

```text
task-0=10
task-1=FAILED: rejected input
task-2=30
completed=3
successful=2
```

Tại sao thứ tự dòng ổn định dù thứ tự tác vụ chạy có thể khác? Các tác vụ không in trực tiếp. Sau khi chờ, luồng chính duyệt chỉ số 0, 1, 2 để in.

`completed=3` là số tác vụ đã đi qua mốc cuối trong ví dụ. `successful=2` mới là số kết quả thành công. Cổng đã mở không có nghĩa cả ba tác vụ thành công.

Ví dụ chỉ bắt `RuntimeException` mà phần tính toán này có thể phát sinh. Một hệ thống thực tế phải xác định chính sách cho loại lỗi của nó; latch không thay thế việc thu thập lỗi.

Lệnh `shutdown()` sau khi gửi tác vụ ngừng nhận công việc mới nhưng cho các tác vụ đã nhận tiếp tục chạy. `shutdownNow()` trong `finally` yêu cầu dừng và cố gắng ngắt các tác vụ còn chạy; nó không bảo đảm mọi tác vụ chấm dứt ngay. Xem [vòng đời ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html).

Trong ví dụ, mỗi tác vụ chỉ có phép tính ngắn và không có việc nào sau tín hiệu hoàn tất. Với công việc dài hoặc truy cập bên ngoài, cần chính sách hủy và đóng tài nguyên riêng.

## 5. Vì sao đọc được dữ liệu đã ghi trước tín hiệu?

Giả sử một tác vụ thực hiện theo thứ tự:

```text
Ghi results[index]
    ↓
done.countDown()
    ↓ quan hệ happens-before
Luồng điều phối đi qua done.await() thành công
    ↓
Đọc results[index]
```

Hợp đồng bộ nhớ của latch tạo quan hệ **xảy ra trước (happens-before)** giữa hành động trước `countDown()` và hành động sau lần `await()` trở về thành công tương ứng. Nhờ đó dữ liệu công bố trước tín hiệu được nhìn thấy khi bên chờ tiếp tục. Xem phần Memory consistency effects trong [CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html).

Ở chương trình trên:

- Mỗi tác vụ sở hữu một chỉ số riêng của mảng.
- Nó ghi kết quả hoặc lỗi **trước** `countDown()`.
- Luồng chính không đọc các mảng trước khi chờ thành công.
- Sau tín hiệu, tác vụ không sửa tiếp ô kết quả.

Vì vậy không cần biến từng phần tử kết quả thành một biến nguyên tử chỉ để công bố dữ liệu theo giao thức này.

Nhưng latch không làm mọi thao tác trên cấu trúc dùng chung trở nên an toàn. Nếu ba tác vụ cùng `add()` vào một `ArrayList` thường, chúng vẫn có thể tranh chấp và làm hỏng trạng thái trong lúc chạy. Chờ cả ba kết thúc không sửa được các lần ghi sai trước đó. Cần phân chia vùng ghi, dùng cấu trúc đồng thời hoặc bảo vệ thao tác bằng cơ chế phù hợp.

Tương tự, nếu tác vụ gọi `countDown()` rồi mới ghi kết quả, quan hệ công bố phía trên không bao phủ lần ghi đó. Luồng điều phối có thể đã đi qua cổng trước khi dữ liệu hoàn chỉnh.

## 6. Timeout và ngắt là kết quả điều khiển, không phải thành công

### 6.1. Timeout

```java
// Mã minh họa.
boolean allDone = done.await(2, TimeUnit.SECONDS);
if (!allDone) {
    // Chọn chính sách cho công việc chưa hoàn tất.
    return;
}
// Chỉ tại đây mới xử lý như đợt công việc đã hoàn tất.
```

Nếu trả về `false`, bộ đếm chưa đạt điều kiện trong thời hạn của lần chờ đó. Các tác vụ có thể vẫn đang chạy và có thể giảm đếm sau này. Timeout không đặt lại latch, không đưa bộ đếm về 0 và không tự hủy tác vụ.

Không đọc toàn bộ mảng kết quả như thể nó đã hoàn chỉnh sau nhánh timeout. Nếu muốn hiển thị kết quả từng phần, cần thiết kế cách công bố trạng thái riêng cho từng tác vụ.

Cũng không “giải phóng” luồng chờ bằng cách gọi `countDown()` thay cho tác vụ chưa xong rồi coi tất cả đã hoàn tất. Cách đó thay đổi ý nghĩa bộ đếm, che giấu công việc còn chạy và làm mất bảo đảm về dữ liệu công bố.

### 6.2. InterruptedException

Luồng đang chờ có thể bị ngắt. Có hai lựa chọn thường gặp:

- Cho ngoại lệ đi lên nếu phương thức được phép khai báo `throws InterruptedException`.
- Nếu xử lý tại chỗ, hoàn tất việc dọn dẹp cần thiết, khôi phục cờ ngắt khi không chuyển tiếp ngoại lệ, rồi kết thúc nhánh công việc phù hợp.

```java
// Mã minh họa một phương thức không chuyển tiếp InterruptedException.
try {
    done.await();
    useCompletedResults();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
```

Không bắt rồi bỏ qua ngoại lệ để tiếp tục đọc như đã hoàn tất. Trong ví dụ đầy đủ, `main` chuyển tiếp ngoại lệ và `finally` vẫn yêu cầu nhóm thực thi dừng.

## 7. Hai mẫu sử dụng độc lập

### 7.1. Cổng khởi động

Một latch ban đầu bằng 1 có thể giữ nhiều tác vụ lại cho đến lúc phát lệnh:

```java
// Mã minh họa.
CountDownLatch start = new CountDownLatch(1);

// Mỗi tác vụ:
start.await();
performWork();

// Luồng điều phối, sau khi thiết lập xong:
start.countDown();
```

Tín hiệu này nghĩa là “được phép bắt đầu”. Nó không có nghĩa mọi tác vụ đã thật sự bắt đầu ở cùng một thời điểm vật lý; bộ lập lịch vẫn quyết định khi nào từng luồng được chạy.

### 7.2. Cổng hoàn tất

Một latch ban đầu bằng N biểu diễn N mốc cuối. Luồng điều phối chờ tổng hợp, còn mỗi tác vụ tự báo mốc.

Có thể kết hợp hai latch khác nhau:

```text
start = 1: điều phối mở cổng để các tác vụ được chạy
done  = N: các tác vụ phát tín hiệu để điều phối biết đã xong
```

Không dùng một latch duy nhất vừa làm cổng bắt đầu vừa làm bộ đếm kết thúc nếu số đếm và trách nhiệm tín hiệu không còn diễn đạt được cả hai mục đích.

## 8. Những lỗi làm chương trình treo hoặc mở cổng sai

### 8.1. Số đếm không khớp công việc thật sự

Khởi tạo 5 nhưng chỉ gửi được 4 tác vụ và không có bên nào chịu trách nhiệm cho tín hiệu thứ năm sẽ khiến cổng không mở.

Tình huống này còn xảy ra khi gửi tác vụ bị từ chối hoặc khi một tác vụ bị hủy trước lúc bắt đầu. `finally` bên trong `Runnable` chỉ chạy nếu phần thân tác vụ đã được thực thi; nó không xử lý hộ tác vụ chưa từng chạy.

Nếu cho phép từ chối hoặc hủy, cần quy định rõ bên nào ghi nhận trạng thái đó và phát tín hiệu đúng một lần. Không để đường hủy và đường hoàn tất cùng phát tín hiệu cho cùng một tác vụ.

### 8.2. Tác vụ chờ chính đợt công việc mà nó đang giữ chỗ

Một tác vụ gọi `done.await()` trước `countDown()` của chính nó sẽ tự tạo vòng phụ thuộc: nó đợi bộ đếm về 0, nhưng bộ đếm lại cần chính nó chạy tiếp.

Tương tự, với nhóm thực thi chỉ có một luồng:

```text
Tác vụ điều phối đang chiếm luồng duy nhất và gọi await()
Các tác vụ cần countDown() đang xếp hàng sau nó
→ Không tác vụ nào có cơ hội phát tín hiệu
```

Giải pháp nằm ở thiết kế vị trí chờ và tài nguyên thực thi: để bên điều phối chờ ngoài nhóm, hoặc dùng cơ chế phối hợp không chiếm chỗ của công việc cần chạy. Chỉ tăng timeout không loại bỏ vòng phụ thuộc.

### 8.3. Dùng getCount() như khóa hoặc điều kiện đặt chỗ

`getCount()` hữu ích cho chẩn đoán. Mã “nếu số đếm còn 1 thì tôi là người cuối” không tạo ra một giao dịch nguyên tử với hành động tiếp theo. Luồng khác có thể giảm đếm ngay sau lần đọc.

Nếu cần một bên thực hiện hành động cuối cùng, phải thiết kế cơ chế nhận quyền thực hiện đó riêng. Không suy ra quyền sở hữu từ một giá trị quan sát.

### 8.4. Cố tái sử dụng latch đã mở

Sau khi về 0, latch không còn chặn đợt tiếp theo. Muốn tổ chức nhiều đợt độc lập, tạo đối tượng latch mới cho từng đợt và truyền đúng đối tượng cho các tác vụ. Nếu cần phối hợp qua nhiều pha lặp lại, xem xét `CyclicBarrier` hoặc `Phaser` theo mô hình tham gia tương ứng.

## 9. Chọn công cụ theo điều cần chờ

| Nhu cầu | Công cụ thường phù hợp |
| --- | --- |
| Chờ N tín hiệu trong một đợt | `CountDownLatch` |
| Chờ các bên cùng đến ở nhiều vòng | `CyclicBarrier` |
| Phối hợp nhiều pha với số bên tham gia có thể thay đổi | `Phaser` |
| Lấy kết quả hoặc ngoại lệ của từng tác vụ | `Future` |
| Chờ một luồng cụ thể chấm dứt | `Thread.join()` |

`Future` biểu diễn kết quả tính toán bất đồng bộ, có thể dùng `get()` để chờ và lấy kết quả, đồng thời có cơ chế báo lỗi hoặc hủy. Xem [Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html). Nếu nhu cầu chủ yếu là thu kết quả của từng tác vụ, đây có thể là lựa chọn tự nhiên hơn việc tự tạo mảng kết quả và latch.

`CountDownLatch` có giá trị khi điều cần chờ là một tập mốc mà không nhất thiết trùng với việc một luồng cụ thể kết thúc. Mốc này có thể được phát trước khi luồng quay lại nhóm thực thi để nhận công việc khác.

## 10. Tự kiểm tra trước khi áp dụng

- Bộ đếm ban đầu đại diện cho những mốc cụ thể nào?
- Từng mốc có đúng một bên chịu trách nhiệm phát tín hiệu không?
- Nhánh lỗi, nhánh từ chối và nhánh hủy trước khi chạy được xử lý thế nào?
- Dữ liệu cần đọc có được ghi xong trước tín hiệu không?
- Bên chờ có đang giữ tài nguyên mà bên phát tín hiệu cần không?
- Timeout hoặc ngắt có dẫn tới chính sách rõ ràng thay vì giả vờ thành công không?

Bài tập: đổi số đếm trong ví dụ từ 3 thành 4. Ba tác vụ vẫn kết thúc, nhưng lần chờ sẽ hết thời gian vì thiếu một tín hiệu. Đổi số đếm thành 2 thì cổng có thể mở trước khi tác vụ thứ ba ghi xong; kết quả tổng hợp không còn được bảo đảm đầy đủ.

Điều cần giữ nhất quán là ý nghĩa của bộ đếm: **mỗi lần giảm phải tương ứng với một mốc thật sự đã được xử lý theo giao thức của chương trình**.

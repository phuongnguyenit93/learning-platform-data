# Phân biệt đợi hoàn tất, giới hạn truy cập và hội tụ theo chặng

## 1. Ba câu hỏi khác nhau trong phối hợp tác vụ

Khi nhiều tác vụ chạy đồng thời, “đợi nhau” có thể mang ba ý nghĩa:

1. **Đợi hoàn tất:** chỉ tổng hợp báo cáo sau khi mọi phần việc đã phát tín hiệu kết thúc.
2. **Giới hạn truy cập:** có nhiều việc đang chờ, nhưng chỉ tối đa K việc được dùng một tài nguyên cùng lúc.
3. **Hội tụ theo chặng:** mọi bên phải xong chặng hiện tại trước khi cùng bước sang chặng tiếp theo.

Ba nhu cầu này có mô hình trạng thái khác nhau. Chọn nhầm công cụ thường gây chờ vô hạn, vượt giới hạn tài nguyên hoặc xử lý dữ liệu của chặng chưa hoàn chỉnh.

Ví dụ một hệ thống xử lý ảnh:

- Chờ 20 ảnh xử lý xong để tạo báo cáo: đợi hoàn tất.
- Chỉ cho 3 tác vụ cùng dùng bộ mã hóa: giới hạn truy cập.
- Mỗi vòng xử lý gồm tính phần cục bộ, chờ các phần còn lại, rồi tổng hợp trước vòng sau: hội tụ theo chặng.

Trong Java, ba công cụ tiêu biểu là `CountDownLatch`, `Semaphore` và `CyclicBarrier`. Chúng xuất hiện từ Java 5 và vẫn phù hợp trên Java hiện đại. Các ví dụ dưới đây chạy với Java 17+.

## 2. Bảng phân biệt nhanh

| Tiêu chí | CountDownLatch | Semaphore | CyclicBarrier |
| --- | --- | --- | --- |
| Câu hỏi chính | Đủ N tín hiệu chưa? | Còn giấy phép truy cập không? | Đủ P bên đến điểm gặp của chặng này chưa? |
| Trạng thái cốt lõi | Bộ đếm giảm về 0 | Số giấy phép khả dụng | Số bên còn thiếu trong một thế hệ |
| Thao tác tác vụ | `countDown()` | `acquire()` rồi `release()` | `await()` |
| Ai chờ? | Luồng điều phối hoặc bất kỳ luồng gọi await | Bên cần giấy phép nhưng chưa có | Các bên đến sớm tại điểm gặp |
| Thao tác báo đến có chặn không? | countDown không chờ các bên khác | release không chờ bên khác | await vừa báo đến vừa chờ |
| Dùng lại cùng đối tượng | Không đặt lại bộ đếm | Có, giấy phép được trả rồi lấy tiếp | Có, tự chuyển sang thế hệ kế tiếp khi đủ bên |
| Hành động gộp tại mỗi chặng | Tự thực hiện sau await | Không phải vai trò chính | Có barrier action tùy chọn |
| Tự mang kết quả hoặc lỗi tác vụ | Không | Không | Không |

Số 3 trong ba constructor có ý nghĩa khác nhau:

```java
new CountDownLatch(3); // Cần 3 lần giảm đếm để mở cổng.
new Semaphore(3);      // Ban đầu có 3 giấy phép.
new CyclicBarrier(3);  // Cần 3 lần đến trong mỗi thế hệ.
```

Đây là đoạn minh họa; cần import các lớp tương ứng từ `java.util.concurrent` khi sử dụng.

## 3. Đợi hoàn tất bằng CountDownLatch

### Mô hình

Khởi tạo latch bằng số tín hiệu dự kiến. Mỗi phần việc gọi `countDown()` đúng lúc theo giao thức đã thiết kế. Luồng cần đợi gọi `await()`.

```text
Tác vụ A: làm việc -> countDown
Tác vụ B: làm việc -> countDown
Tác vụ C: làm việc -> countDown
Điều phối: await -----------------> tổng hợp
                         bộ đếm = 0
```

Luồng gọi `countDown()` không phải dừng lại chờ tất cả. Nó có thể kết thúc hoặc làm việc khác ngay. Bên phát tín hiệu và bên chờ cũng không bắt buộc là cùng một nhóm luồng.

Latch là cổng mở **một lần**: khi về 0, các lần `await()` về sau đi qua ngay. Không tăng lại để dùng cho vòng tiếp theo.

### Ví dụ tính ba kết quả rồi tổng hợp

Lưu thành `CompletionDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;

public class CompletionDemo {
    public static void main(String[] args) throws InterruptedException {
        int[] results = new int[3];
        CountDownLatch done = new CountDownLatch(results.length);

        for (int i = 0; i < results.length; i++) {
            final int index = i;
            Thread worker = new Thread(() -> {
                try {
                    int value = index + 1;
                    results[index] = value * value;
                } finally {
                    done.countDown();
                }
            });
            worker.start();
        }

        done.await();
        System.out.println(Arrays.toString(results));
        System.out.println("Sum: " + Arrays.stream(results).sum());
    }
}
```

Chạy:

```shell
javac CompletionDemo.java
java CompletionDemo
```

Stdout khi chạy bình thường:

```text
[1, 4, 9]
Sum: 14
```

Mỗi tác vụ ghi một ô riêng của mảng. Việc đọc diễn ra sau khi `await()` trả về thành công. [Hợp đồng CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html) bảo đảm quan hệ happens-before từ công việc trước tín hiệu giảm đếm đến công việc sau lần đợi tương ứng.

### Hoàn tất không đồng nghĩa thành công

Trong ví dụ, `countDown()` đặt ở `finally` để mỗi tác vụ đã bắt đầu đều phát tín hiệu khi rời vùng xử lý. Nếu xử lý thực tế có lỗi, bộ đếm vẫn có thể về 0.

Do đó, cần xác định “done” nghĩa là:

- Đã kết thúc lần thử, dù thành công hay thất bại: phát tín hiệu ở `finally`, đồng thời thu kết quả/lỗi riêng.
- Đã hoàn thành thành công một mốc nghiệp vụ: chỉ phát tín hiệu khi mốc đó xảy ra; phải có cách kết thúc chờ khi lỗi xảy ra.

Không đơn giản bỏ `countDown()` khi lỗi mà vẫn dùng `await()` vô hạn. Latch cũng không tự nhận biết tác vụ bị từ chối khi gửi vào executor hoặc bị hủy trước khi chạy; bên điều phối phải xử lý những đường đó.

Nếu chỉ cần nhận kết quả và ngoại lệ của một số tác vụ đã gửi, `Future.get()` hoặc một cơ chế hoàn tất tương ứng có thể trực tiếp hơn. Latch phù hợp khi muốn biểu diễn một tập tín hiệu/mốc chung, không phải thay thế mọi cách quản lý tác vụ.

## 4. Giới hạn truy cập bằng Semaphore

### Mô hình

Semaphore quản lý **giấy phép (permit)**. Một tác vụ lấy giấy phép trước khi vào vùng bị giới hạn và trả giấy phép khi rời vùng đó.

```text
Nhiều tác vụ chờ
       |
    acquire
       |
Tối đa K tác vụ trong vùng giới hạn
       |
    release
       |
Giấy phép quay lại cho tác vụ khác
```

Với `new Semaphore(2)`, nếu mọi tác vụ đều tuân thủ đúng giao thức, tối đa hai tác vụ giữ giấy phép cùng lúc. Không có yêu cầu đợi đủ hai tác vụ mới chạy, cũng không có bước tự tổng hợp khi mọi việc đã xong.

### Ví dụ sáu việc, tối đa hai việc trong vùng giới hạn

Lưu thành `AccessLimitDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;

public class AccessLimitDemo {
    public static void main(String[] args) throws Exception {
        Semaphore slots = new Semaphore(2);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        List<Future<Integer>> futures = new ArrayList<>();

        try {
            for (int i = 1; i <= 6; i++) {
                final int value = i;
                futures.add(pool.submit(() -> {
                    slots.acquire();
                    try {
                        return value * value;
                    } finally {
                        slots.release();
                    }
                }));
            }

            int sum = 0;
            for (Future<Integer> future : futures) {
                sum += future.get();
            }
            System.out.println("Sum: " + sum);
            System.out.println("Permits after completion: "
                    + slots.availablePermits());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```shell
javac AccessLimitDemo.java
java AccessLimitDemo
```

Stdout trong lần chạy thành công:

```text
Sum: 91
Permits after completion: 2
```

Executor có bốn luồng chạy nhưng vùng nằm giữa `acquire()` và `release()` chỉ có hai giấy phép. Phần tính bình phương rất ngắn để ví dụ gọn; trong ứng dụng, vùng đó có thể là sử dụng tài nguyên giới hạn.

Chính các `Future.get()` giúp chương trình đợi kết quả sáu việc. Semaphore chỉ giới hạn vùng truy cập. Hai vai trò được phối hợp nhưng không thay thế nhau.

### Quy tắc cấp và trả giấy phép

Đặt `acquire()` **trước** khối `try/finally` dùng để trả giấy phép như ví dụ. Nếu đang đợi mà bị ngắt, `acquire()` ném `InterruptedException` và chưa cấp giấy phép; lúc ấy không được tự ý `release()`.

Các lỗi phổ biến:

- Quên trả giấy phép: giảm sức chứa thực tế, cuối cùng mọi bên có thể chờ.
- Trả hai lần: tăng số giấy phép sai và làm hỏng giới hạn.
- Trả khi chưa lấy thành công: cũng làm tăng sức chứa sai.
- Gọi `availablePermits()`, thấy còn rồi tự đi vào: kiểm tra và lấy không phải một thao tác; phải dùng `acquire` hoặc `tryAcquire`.
- Lấy giấy phép nhưng giữ nó trong lúc chờ một tác vụ khác cũng cần giấy phép ấy: có thể tạo vòng chờ.

Semaphore không gắn quyền sở hữu giấy phép với một luồng như một khóa thông thường. Cơ chế không tự ngăn luồng khác trả sai giấy phép; giao thức ứng dụng phải bảo đảm cân bằng cấp–trả.

Semaphore cũng không tự chọn đối tượng tài nguyên trong một pool, không bảo vệ mọi trường của pool và không giới hạn số yêu cầu **theo giây**. “Tối đa 3 yêu cầu đang xử lý” khác với “tối đa 3 yêu cầu trong một giây”.

Nếu cần công bằng, có thể cân nhắc constructor `new Semaphore(K, true)`. Không diễn giải công bằng thành thứ tự hoàn tất tác vụ hoặc thời gian chờ cố định; `tryAcquire()` không thời hạn còn có quy tắc riêng về vượt hàng. Xem [hợp đồng Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html).

## 5. Hội tụ theo chặng bằng CyclicBarrier

### Mô hình

Barrier dùng cho một nhóm bên tham gia. Mỗi bên thực hiện phần việc của mình rồi gọi `await()`. Bên đến sớm bị chặn; khi đủ số bên, barrier cho nhóm đi tiếp.

```text
A: chặng 1 -> await ----+-> chặng 2 -> await ----+
B: chặng 1 -> await ----+-> chặng 2 -> await ----+
C: chặng 1 -> await ----+-> chặng 2 -> await ----+
                       |                       |
                đủ 3 bên, gộp dữ liệu   đủ 3 bên, gộp dữ liệu
```

Một `barrier action` tùy chọn chạy khi đủ bên, trước khi các bên được thả sang chặng sau. Đối tượng tự dùng tiếp cho các thế hệ tiếp theo sau một lần hội tụ thành công.

### Ví dụ hai vòng tính toán có bước tổng hợp

Lưu thành `StageBarrierDemo.java`:

```java
import java.util.Arrays;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class StageBarrierDemo {
    public static void main(String[] args) throws Exception {
        int parties = 3;
        int[] partials = new int[parties];
        AtomicInteger completedRound = new AtomicInteger();

        CyclicBarrier barrier = new CyclicBarrier(parties, () -> {
            int round = completedRound.incrementAndGet();
            int total = Arrays.stream(partials).sum();
            System.out.println("Round " + round + " total: " + total);
        });

        ExecutorService pool = Executors.newFixedThreadPool(parties);
        List<Future<Void>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < parties; i++) {
                final int index = i;
                futures.add(pool.submit(() -> {
                    for (int round = 1; round <= 2; round++) {
                        partials[index] = (index + 1) * round;
                        barrier.await(10, TimeUnit.SECONDS);
                    }
                    return (Void) null;
                }));
            }

            for (Future<Void> future : futures) {
                future.get();
            }
            System.out.println("All stages completed");
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```shell
javac StageBarrierDemo.java
java StageBarrierDemo
```

Stdout khi không có lỗi, ngắt luồng hoặc hết thời gian đợi:

```text
Round 1 total: 6
Round 2 total: 12
All stages completed
```

Trong vòng đầu, các phần là 1, 2, 3. Trong vòng sau, các phần là 2, 4, 6. Barrier action đọc dữ liệu khi mọi bên đã đến, và hoàn tất trước khi họ sửa dữ liệu cho vòng tiếp theo.

Giới hạn 10 giây trong ví dụ giúp tránh một lần chờ barrier vô hạn khi một bên không tới đúng hạn; đó là tham số thí nghiệm, không phải thời hạn phù hợp cho mọi ứng dụng.

### Hội tụ khác với kết thúc

Một bên rời `barrier.await()` không có nghĩa tác vụ của nó đã kết thúc: nó thường còn chặng tiếp theo. Trong ví dụ, các `Future.get()` mới là nơi main đợi toàn bộ vòng đời các tác vụ.

Barrier không giữ cho các luồng chạy cùng từng nhịp sau khi được thả. Nó chỉ ràng buộc thứ tự giữa các chặng tại điểm gặp đã thiết kế.

Nếu một bên bị ngắt hoặc hết thời gian trong lúc chờ, thế hệ barrier có thể bị phá vỡ. Các bên đang chờ khác nhận `BrokenBarrierException` theo hợp đồng. Nếu một tác vụ lỗi **trước khi đến barrier**, công cụ không tự biết rằng bên ấy sẽ không tới: cần thời hạn, hủy nhóm và xử lý lỗi ở tầng điều phối.

Không dùng `reset()` như cách sửa tự động mọi lỗi. Reset khi các bên chưa được phối hợp lại có thể khiến họ thuộc các thế hệ không như dự kiến. Trước hết cần quyết định cả nhóm dừng, thử lại hay khởi tạo một đợt xử lý mới.

Các quy tắc tái sử dụng, barrier action, phá vỡ barrier và happens-before được quy định trong [CyclicBarrier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CyclicBarrier.html).

## 6. Cùng chặn luồng, nhưng không cùng ý nghĩa

### Latch không phải barrier lặp

`countDown()` không giữ bên báo hiệu lại. Bên đó có thể đi tiếp trong khi bên khác chưa đến. Còn `await()` của barrier vừa báo đến vừa chờ nhóm trong cùng một thế hệ.

Muốn mô hình nhiều vòng bằng latch phải thiết kế latch riêng cho từng vòng và bảo đảm các bên cùng giữ đúng đối tượng. Không được dùng lại một latch đã về 0 rồi tưởng nó tự trở lại N.

### Semaphore không phải bộ đếm việc xong

Nếu một luồng lấy rồi trả giấy phép, semaphore có thể quay lại trạng thái ban đầu dù còn hàng trăm tác vụ chưa chạy. “Có đủ K giấy phép khả dụng” không phải bằng chứng “mọi tác vụ đã hoàn tất”.

Một semaphore khởi tạo 0 có thể được dùng cho tín hiệu trong một giao thức chuyên biệt. Tuy nhiên, tín hiệu semaphore có thể được tiêu thụ bởi lần lấy; nó khác cổng latch đã mở cho mọi bên chờ. Không nên thay latch bằng semaphore chỉ vì cả hai đều có số đếm.

### Barrier không phải giới hạn người vào tài nguyên

Barrier đợi đủ nhóm cùng tới; nó không tạo mô hình “ai có giấy phép thì vào, xong thì nhường người khác”. Dùng barrier để giới hạn số kết nối có thể khiến các bên cố chờ nhau ở nơi vốn chỉ cần sử dụng tài nguyên độc lập.

## 7. Đừng để cách bố trí luồng làm giao thức không thể tiến triển

Giả sử `CyclicBarrier(3)` nhưng executor chỉ có hai luồng chạy. Hai tác vụ đầu tới barrier rồi chiếm cả hai luồng. Tác vụ thứ ba nằm trong hàng đợi, không có luồng để chạy và tới điểm gặp. Nhóm không thể hội tụ nếu không có timeout/hủy.

Lỗi tương tự xảy ra khi đặt tác vụ điều phối đợi latch vào cùng một pool đã bị các tác vụ chờ khác chiếm hết, trong khi tác vụ phát tín hiệu chưa được chạy.

Trước mỗi điểm chờ, kiểm tra:

1. Ai sẽ phát tín hiệu, trả giấy phép hoặc trở thành bên đến cuối?
2. Bên đó có khả năng được lên lịch chạy không?
3. Nó có cần tài nguyên đang bị bên chờ giữ không?
4. Nếu nó lỗi hoặc bị hủy, ai giải phóng nhóm chờ?
5. Sau timeout, các tác vụ còn lại có tiếp tục sửa dữ liệu không?

Timeout chỉ giới hạn lần đợi hiện tại; nó không tự hủy tất cả công việc nền. `shutdownNow()` cũng chỉ yêu cầu ngắt các tác vụ đang chạy; chúng phải hợp tác xử lý ngắt để dừng.

Không dùng `Thread.sleep` để thay cho tín hiệu hoàn tất hoặc rào chặng. Ngủ một khoảng thời gian không chứng minh tác vụ khác đã tới mốc mong muốn.

## 8. Ngắt luồng, thời hạn và dữ liệu chia sẻ

| Công cụ | Biến thể có thời hạn | Khi không đạt điều kiện |
| --- | --- | --- |
| CountDownLatch | `await(timeout, unit)` | Trả false nếu hết hạn |
| Semaphore | `tryAcquire(timeout, unit)` | Trả false nếu không lấy được giấy phép đúng hạn |
| CyclicBarrier | `await(timeout, unit)` | Có thể ném TimeoutException; các bên khác có thể gặp barrier bị phá vỡ |

Các thao tác chờ có thể ngắt dùng `InterruptedException`. Khi bắt ngoại lệ ở nơi không thể truyền tiếp, thông thường cần khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` rồi kết thúc hoặc chuyển sang nhánh hủy phù hợp; không bắt rồi âm thầm tiếp tục như đã được cấp phép hoặc đã hoàn tất.

Các công cụ phối hợp có quy tắc công bố bộ nhớ, nhưng không biến mọi cấu trúc dữ liệu thành an toàn đồng thời. Ví dụ, nhiều tác vụ cùng `ArrayList.add` vẫn cần cơ chế bảo vệ riêng; việc cuối cùng có latch về 0 không sửa lại các lần cập nhật đã đua nhau trước đó.

Tương tự, semaphore với K > 1 cho phép nhiều người cùng vào; nó không tạo loại trừ lẫn nhau cho toàn bộ trạng thái bên trong vùng đó.

## 9. Khi số bên tham gia thay đổi theo chặng

`CyclicBarrier` phù hợp khi số bên cần đến mỗi lần là cố định. Nếu có nhu cầu thêm bên, rút bên hoặc chia tách báo đến với đợi sang chặng mới, Java hiện đại có `Phaser`.

`Phaser` được bổ sung sau Java 5, nên đây chỉ là hướng mở rộng để chọn công cụ khi yêu cầu thực tế vượt mô hình nhóm cố định. Việc tồn tại `Phaser` không làm latch, semaphore hay barrier trở thành API lỗi thời. Xem [Phaser](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Phaser.html) khi cần đăng ký/rút bên động và hiểu kỹ quy tắc kết thúc của nó.

## 10. Chọn theo câu hỏi của bài toán

- “Tôi cần đợi đủ N mốc trong một đợt rồi đi tiếp”: bắt đầu với `CountDownLatch`.
- “Tôi cần tối đa K bên sử dụng tài nguyên cùng lúc”: bắt đầu với `Semaphore`.
- “Một nhóm cố định phải gặp nhau sau từng vòng rồi làm vòng tiếp”: bắt đầu với `CyclicBarrier`.
- “Tôi cần kết quả, ngoại lệ và hủy từng tác vụ”: xét thêm `Future` và cơ chế điều phối vòng đời tác vụ.
- “Số bên thay đổi trong quá trình nhiều chặng”: xét `Phaser`.

Một luồng xử lý có thể cần cả ba vai trò, chẳng hạn semaphore giới hạn dùng tài nguyên, barrier phối hợp các vòng, rồi cơ chế hoàn tất báo toàn bộ công việc đã kết thúc. Mỗi điểm chờ phải có người hoặc sự kiện làm nó tiến triển; đó là câu hỏi quan trọng hơn việc tên API có chữ “đồng bộ” hay không.

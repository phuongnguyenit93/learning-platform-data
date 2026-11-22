# CyclicBarrier và điểm hội tụ có thể tái sử dụng

## 1. Bài toán: một nhóm phải cùng xong mỗi chặng

Giả sử hai tác vụ xử lý hai phần dữ liệu độc lập. Mỗi vòng gồm:

1. Mỗi tác vụ tính kết quả cục bộ của vòng hiện tại.
2. Chờ đủ cả hai kết quả.
3. Tổng hợp kết quả vòng.
4. Bắt đầu vòng sau.

Nếu tác vụ nhanh tự chuyển sang vòng sau, nó có thể ghi đè kết quả trước khi bên tổng hợp kịp đọc. Nếu chỉ đợi mọi tác vụ kết thúc ở cuối chương trình, ta lại không có điểm phối hợp giữa các vòng.

`CyclicBarrier` tạo **điểm hội tụ (barrier)** cho một số lượng bên tham gia cố định. Tác vụ đến sớm dừng tại `await()`; khi đủ bên đến, cả nhóm được phép tiếp tục. Điểm hội tụ được dùng lại cho vòng kế tiếp sau một lần hội tụ thành công.

Đây là API được giới thiệu từ Java 5 và vẫn còn phù hợp trên Java hiện đại. Các ví dụ trong bài chạy với Java 17+, không cần API thử nghiệm.

## 2. Ba khái niệm: bên tham gia, lần đến và thế hệ

### Bên tham gia — party

Constructor xác định số lần đến cần có cho mỗi đợt:

```java
CyclicBarrier barrier = new CyclicBarrier(3);
```

Đoạn minh họa cần import `java.util.concurrent.CyclicBarrier`.

Số 3 nghĩa là mỗi thế hệ cần ba lời gọi `await()` đến điểm hội tụ. Barrier không tự tạo ba luồng, không gửi tác vụ vào executor và không lưu danh sách định danh những bên được phép đến. Ứng dụng phải bảo đảm đúng nhóm cùng tham gia theo giao thức.

### Lần đến — arrival

Gọi `await()` có hai vai trò cùng lúc: báo rằng bên này đã đến và đợi nếu vẫn còn thiếu bên khác.

```text
A: làm phần A -> await -----+
B: làm phần B -> await -----+--> đủ nhóm --> cùng được đi tiếp
C: làm phần C -> await -----+
```

Bên đến cuối kích hoạt việc hoàn tất điểm hội tụ. Không có yêu cầu các luồng phải được bộ lập lịch cho chạy ngay cùng một thời điểm sau đó.

### Thế hệ — generation

Mỗi đợt hội tụ thuộc một thế hệ. Sau khi thế hệ hiện tại hoàn tất bình thường, barrier chuyển sang thế hệ mới và lại đợi đủ số bên.

```text
Thế hệ 1: đủ P bên -> hoàn tất
Thế hệ 2: đủ P bên -> hoàn tất
Thế hệ 3: đủ P bên -> hoàn tất
```

Không cần gọi `reset()` sau mỗi vòng thành công. Chữ “cyclic” thể hiện chính khả năng tự lặp lại này.

## 3. Barrier action nằm giữa hai chặng

Có thể cung cấp một hành động tổng hợp khi tạo barrier:

```java
CyclicBarrier barrier = new CyclicBarrier(3, () -> {
    System.out.println("All parties reached this stage");
});
```

Đây là đoạn minh họa, không phải chương trình độc lập. Barrier action:

- Chạy một lần khi đủ bên của thế hệ hiện tại.
- Do luồng đến cuối thực hiện.
- Hoàn tất trước khi các bên được thả khỏi lần `await()` thành công ấy.

Nhờ vị trí này, action phù hợp với việc gộp các kết quả cục bộ, đổi vai trò hai bộ đệm hoặc cập nhật một điều kiện dừng chung.

Nên giữ action ngắn, có thời gian hoàn thành dự đoán được. Nếu action chờ một công việc chỉ được các bên thực hiện **sau** barrier, cả nhóm có thể mắc kẹt: họ đang đợi action kết thúc để đi tiếp.

Các bảo đảm về điểm hội tụ và hành động tùy chọn được mô tả trong [CyclicBarrier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CyclicBarrier.html).

## 4. Ví dụ chạy đủ ba vòng với cùng một barrier

Hai tác vụ đọc hai hàng dữ liệu. Ở vòng thứ k, mỗi tác vụ đưa giá trị cột k vào ô kết quả riêng. Barrier action cộng hai ô rồi ghi kết quả của vòng đó.

Lưu thành `ReusableBarrierDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ReusableBarrierDemo {
    public static void main(String[] args) throws Exception {
        int[][] input = {
                {2, 4, 6},
                {3, 6, 9}
        };
        int parties = input.length;
        int rounds = input[0].length;
        int[] partials = new int[parties];
        int[] totals = new int[rounds];
        AtomicInteger nextRound = new AtomicInteger();

        CyclicBarrier barrier = new CyclicBarrier(parties, () -> {
            int round = nextRound.getAndIncrement();
            int total = 0;
            for (int value : partials) {
                total += value;
            }
            totals[round] = total;
            System.out.println("Stage " + (round + 1)
                    + " total: " + total);
        });

        ExecutorService pool = Executors.newFixedThreadPool(parties);
        List<Future<Void>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < parties; i++) {
                final int worker = i;
                futures.add(pool.submit(() -> {
                    for (int round = 0; round < rounds; round++) {
                        partials[worker] = input[worker][round];
                        barrier.await(10, TimeUnit.SECONDS);
                    }
                    return (Void) null;
                }));
            }

            for (Future<Void> future : futures) {
                future.get();
            }
            System.out.println("Stages stored: " + totals.length);
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```shell
javac ReusableBarrierDemo.java
java ReusableBarrierDemo
```

Stdout khi các tác vụ chạy thành công trong thời hạn:

```text
Stage 1 total: 5
Stage 2 total: 10
Stage 3 total: 15
Stages stored: 3
```

Phân tích vòng đầu:

1. Tác vụ 0 ghi 2 vào `partials[0]`.
2. Tác vụ 1 ghi 3 vào `partials[1]`.
3. Ai đến trước chờ; người đến cuối thực hiện action.
4. Action đọc hai ô, tính 5 và lưu vào `totals[0]`.
5. Sau khi action xong, hai tác vụ mới tiếp tục ghi dữ liệu vòng hai.

Không có thứ tự cố định giữa hai lần ghi cục bộ. Điều cố định là action chỉ đọc sau khi đủ hai bên đến, và không bên nào bước qua điểm hội tụ trước khi action xong.

Cùng đối tượng `barrier` được gọi ba lần từ mỗi tác vụ. Không có lệnh `reset()` giữa các vòng.

Các `Future.get()` cuối chương trình đợi vòng đời tác vụ và nhận lỗi nếu tác vụ thất bại. Chúng phục vụ mục đích khác với barrier: barrier phối hợp **bên trong** quá trình nhiều vòng.

## 5. Vì sao action đọc được kết quả cục bộ?

Không chỉ đếm số bên, barrier còn có hợp đồng về thứ tự bộ nhớ. Các hành động trước khi một bên gọi `await()` xảy ra-trước (happens-before) hành động trong barrier action; action lại xảy ra-trước công việc sau lần `await()` thành công tương ứng của các bên.

Với ví dụ trên, giao thức là:

```text
Ghi partials cho vòng hiện tại
               |
             await
               |
      action đọc và tổng hợp
               |
        await trả về thành công
               |
        ghi dữ liệu vòng sau
```

Điều này không cho phép tùy ý chia sẻ mọi dữ liệu:

- Mỗi tác vụ ghi một phần tử riêng của `partials`.
- Không có người ngoài giao thức sửa `partials`.
- Đọc tổng hợp nằm trong action.
- Tác vụ không sửa phần tử của vòng sau trước khi được thả.

Nếu hai tác vụ cùng sửa một `ArrayList` không có bảo vệ, việc cuối vòng có barrier không sửa lại những lần cập nhật đã đua nhau. Cần đồng bộ đúng cả những truy cập xảy ra trong cùng một chặng.

Nếu thuật toán cần đọc dữ liệu cũ đồng thời ghi dữ liệu mới, có thể cần hai bộ đệm riêng. Barrier không tự biến đọc–ghi trên cùng bộ đệm thành an toàn chỉ vì có một điểm chờ ở cuối vòng.

## 6. await trả về chỉ số đến, không phải kết quả tính toán

`await()` trả về một `int` là **chỉ số đến (arrival index)**:

- Bên đến đầu nhận `parties - 1`.
- Bên đến cuối nhận 0.

Có thể dùng để chọn một bên thực hiện công việc sau khi được thả:

```java
int arrivalIndex = barrier.await();
if (arrivalIndex == 0) {
    // Công việc chỉ dành cho một bên, sau điểm hội tụ.
}
```

Đoạn này cần xử lý hoặc khai báo các ngoại lệ của `await()` khi đưa vào phương thức.

Điểm cần lưu ý: các bên khác cũng đã được thả và có thể chạy tiếp trong lúc khối `if` còn đang chạy. Nếu kết quả khối này phải sẵn sàng **trước khi bất kỳ bên nào làm chặng tiếp**, hãy đặt nó trong barrier action hoặc thiết kế thêm một điểm hội tụ.

Chỉ số đến không phải mã định danh luồng ổn định. Luồng đến cuối vòng này có thể đến đầu vòng sau; không dùng chỉ số để gắn cố định quyền sở hữu dữ liệu qua các vòng.

## 7. Khi một thế hệ bị phá vỡ

Một điểm hội tụ chỉ có ý nghĩa khi đủ nhóm và mọi bên đồng ý tiếp tục theo cùng giao thức. Nếu một bên không thể tiếp tục chờ bình thường, barrier có cơ chế **phá vỡ (broken)** thế hệ.

| Sự kiện | Phản ứng điển hình |
| --- | --- |
| Một bên bị ngắt khi chờ | Bên đó nhận InterruptedException; nhóm chờ bị ảnh hưởng |
| Một bên hết thời gian chờ | Bên đó nhận TimeoutException; các bên khác có thể nhận BrokenBarrierException |
| Barrier action ném ngoại lệ | Luồng chạy action nhận ngoại lệ đó; các bên chờ khác thấy barrier bị phá vỡ |
| Có lời gọi reset khi người khác đang chờ | Những bên đang chờ không được coi là qua chặng thành công |
| Gọi await khi barrier vẫn broken | Nhận BrokenBarrierException |

Các tình huống ngắt xảy ra sát lúc thế hệ chuyển tiếp có thể có thứ tự khác nhau theo hợp đồng; đừng suy luận rằng mọi bên luôn nhận cùng một loại ngoại lệ.

Một lỗi nghiệp vụ xảy ra **trước khi tác vụ gọi await** không tự báo cho barrier. Tác vụ đó có thể đã rời khỏi nhóm, trong khi những người còn lại vẫn đợi đủ số bên. Cần kế hoạch xử lý ở tầng điều phối: thời hạn, thu lỗi, yêu cầu hủy các tác vụ còn lại và dừng đợt xử lý.

Trong ví dụ trước, thời hạn 10 giây giới hạn mỗi lần đợi barrier, và `finally` yêu cầu ngắt các tác vụ còn lại khi rời khối xử lý. Đây là lựa chọn cho thí nghiệm; ứng dụng thực tế phải chọn thời hạn theo khối lượng việc và có cách dừng tác vụ hợp tác với ngắt.

Không bắt `BrokenBarrierException` rồi giả vờ rằng nhóm đã hội tụ thành công. Dữ liệu của thế hệ lỗi có thể chưa đầy đủ.

## 8. Thí nghiệm timeout và tái sử dụng sau reset có kiểm soát

Đầu tiên chỉ main đến một barrier cần hai bên. Hết thời gian đợi làm nó broken. Sau khi xác nhận không có ai đang dùng thế hệ cũ, chương trình reset rồi tạo một nhóm đủ hai bên.

Lưu thành `BarrierRecoveryDemo.java`:

```java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public class BarrierRecoveryDemo {
    public static void main(String[] args) throws Exception {
        CyclicBarrier barrier = new CyclicBarrier(2);

        try {
            barrier.await(0, TimeUnit.NANOSECONDS);
        } catch (TimeoutException e) {
            System.out.println("Timed out: true");
        }

        System.out.println("Broken: " + barrier.isBroken());

        try {
            barrier.await();
        } catch (BrokenBarrierException e) {
            System.out.println("Old generation rejected: true");
        }

        barrier.reset();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread partner = new Thread(() -> {
            try {
                barrier.await(10, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                failure.set(e);
            } catch (BrokenBarrierException | TimeoutException e) {
                failure.set(e);
            }
        });

        partner.start();
        barrier.await(10, TimeUnit.SECONDS);
        partner.join();

        if (failure.get() != null) {
            throw new IllegalStateException(failure.get());
        }
        System.out.println("Recovered: " + !barrier.isBroken());
    }
}
```

Chạy:

```shell
javac BarrierRecoveryDemo.java
java BarrierRecoveryDemo
```

Stdout nếu nhóm sau reset hội tụ trong thời hạn:

```text
Timed out: true
Broken: true
Old generation rejected: true
Recovered: true
```

Timeout bằng 0 được chọn để tạo trạng thái lỗi ngay, khi chắc chắn chỉ có một bên và còn thiếu bên thứ hai; không phải mẫu thời hạn cho tác vụ thực tế.

Reset trong thí nghiệm là an toàn để hiểu vì chương trình biết rõ không có tác vụ nào còn sử dụng thế hệ cũ. Trong một ứng dụng có nhiều bên đang chạy, cần thống nhất cách dừng/thử lại cả nhóm trước. Tạo một barrier mới cho đợt công việc mới thường dễ quản lý hơn việc cho các bên tự gọi reset độc lập.

Reset không giảm số bên cấu hình, không hồi sinh tác vụ đã chết và không hoàn tác dữ liệu nghiệp vụ mà tác vụ đã ghi.

## 9. Những nguyên nhân chờ vô hạn thường gặp

### Số bên lớn hơn khả năng chạy đồng thời

Barrier cần ba bên nhưng executor chỉ có hai luồng. Hai tác vụ đầu đều dừng tại barrier và giữ hai luồng; tác vụ thứ ba nằm trong hàng đợi, không thể chạy để đến.

Đối với các tác vụ chặn như mô hình này, phải bảo đảm đủ khả năng chạy những bên cần hội tụ. Không suy ra điều đó chỉ từ số tác vụ đã submit.

### Một nhánh bỏ qua await

Nếu một bên `return`, ném lỗi hoặc có điều kiện bỏ qua vòng mà các bên khác vẫn chờ, số lần đến không đủ. Những bên tham gia phải thống nhất số vòng hoặc có giao thức dừng chung.

### Mỗi tác vụ có một barrier riêng

Ba đối tượng `new CyclicBarrier(3)` không tạo thành một nhóm ba bên. Tất cả bên của một điểm gặp phải dùng đúng đối tượng chung.

### Người điều phối vô tình trở thành bên tham gia

Nếu barrier cần ba tác vụ mà main cũng gọi `await()`, main có thể lấp một chỗ của thế hệ hiện tại. Một tác vụ thật đến sau có thể bị đẩy sang thế hệ tiếp theo, làm sai nhóm và chặng.

Nếu main cũng cần tham gia hội tụ, phải tính nó vào mô hình từ đầu. Nếu chỉ muốn chờ kết thúc tác vụ, dùng cơ chế quản lý hoàn tất phù hợp.

### Giữ tài nguyên cần thiết cho bên chưa đến

Một tác vụ giữ khóa rồi gọi `await()`; bên còn lại cần khóa đó để xong phần việc trước khi đến barrier. Hai yêu cầu tạo vòng chờ. Tương tự, đừng giữ giấy phép tài nguyên trong lúc chờ nếu bên còn thiếu cần chính giấy phép ấy để tiến triển.

### Dùng số người chờ làm điều kiện chính xác

`getNumberWaiting()` và `isBroken()` hữu ích để quan sát/chẩn đoán. Giá trị có thể thay đổi ngay sau khi đọc; chúng không thay thế giao thức hội tụ hay xử lý ngoại lệ.

## 10. So với các lựa chọn gần nhau

| Nhu cầu | Công cụ phù hợp để bắt đầu |
| --- | --- |
| Một nhóm cố định phải gặp nhau sau mỗi chặng | CyclicBarrier |
| Đợi đủ một số tín hiệu trong một đợt, bên báo không cần chờ nhau | CountDownLatch |
| Giới hạn số bên cùng sử dụng tài nguyên | Semaphore |
| Nhận kết quả và lỗi của tác vụ đã gửi | Future và cơ chế điều phối tác vụ |
| Số bên đăng ký/rút ra thay đổi theo chặng | Phaser |

[CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html) mở một lần khi bộ đếm về 0 và không đặt lại được. Barrier tự tạo thế hệ mới sau khi đủ nhóm, nhưng các bên gọi await phải chờ nhau trong từng thế hệ.

[Phaser](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Phaser.html) là lựa chọn hiện đại hơn cho đăng ký/rút bên động và quản lý chặng linh hoạt; nó được bổ sung sau Java 5. Không vì có Phaser mà CyclicBarrier trở thành lỗi thời: nhóm cố định, giao thức đơn giản vẫn là tình huống phù hợp với barrier.

## 11. Tự kiểm tra trước khi dùng

1. Có thật sự cần mọi bên xong chặng trước khi bất kỳ bên nào bắt đầu chặng sau không?
2. Số bên có cố định và tất cả có thể được chạy để đến điểm gặp không?
3. Mỗi bên có gọi đúng một lần await cho mỗi chặng không?
4. Dữ liệu nào thuộc vòng hiện tại, ai được ghi và ai được đọc?
5. Việc tổng hợp phải xong trước khi thả nhóm hay chỉ là việc phụ sau hội tụ?
6. Nếu một bên lỗi trước await, các bên khác dừng bằng cách nào?
7. Ai có quyền quyết định thử lại, reset hoặc tạo nhóm mới?

Điểm cốt lõi của CyclicBarrier là một giao thức chặng chung: mọi bên chuẩn bị phần việc, hội tụ, hoàn tất bước chung cần thiết rồi mới đi tiếp. Tái sử dụng bình thường là tự chuyển thế hệ; khôi phục sau lỗi là một quyết định phối hợp của cả nhóm.

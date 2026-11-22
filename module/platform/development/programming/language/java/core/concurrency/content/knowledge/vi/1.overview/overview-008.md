# Race condition, deadlock và livelock: nhận diện ở mức tổng quan trong Java

Trong lập trình đồng thời (concurrency), nhiều luồng có thể cùng truy cập dữ liệu hoặc tài nguyên. Chương trình có thể chạy rất nhanh mà vẫn cho kết quả sai, hoặc tất cả luồng vẫn tồn tại nhưng công việc không tiến triển. Ba vấn đề nền tảng cần phân biệt là **race condition**, **deadlock** và **livelock**. Bài này nói về Java nói chung (Java 17+), không đi vào cơ chế riêng của Spring.

Mục tiêu sau bài học:
- Giải thích được vấn đề xảy ra ở đâu, vì sao và tác động của mỗi loại.
- Nhìn vào kết quả sai, trạng thái luồng, thread dump và dấu hiệu tiến triển để nhận diện ban đầu.
- Biết cách phòng tránh phù hợp mà không nhầm lẫn giữa tính nguyên tử, khả năng nhìn thấy dữ liệu và tình trạng chờ khóa.

## 1. Bức tranh chung: an toàn dữ liệu và khả năng tiến triển

**Thread safety (an toàn luồng)** liên quan đến việc kết quả và các bất biến (invariant) của dữ liệu được giữ đúng khi nhiều luồng chạy đồng thời. **Liveness (khả năng tiến triển)** liên quan đến việc các thao tác có thể hoàn thành thay vì bị kẹt hoặc lặp vô ích.

- **Race condition:** kết quả phụ thuộc vào thứ tự hoặc thời điểm thực thi các thao tác đồng thời, dẫn đến khả năng vi phạm yêu cầu. Ví dụ hai luồng cùng cập nhật bộ đếm nhưng làm mất một lần tăng.
- **Deadlock:** một tập hợp luồng cùng chờ những điều kiện/tài nguyên mà chính các luồng trong tập hợp đó đang giữ, khiến không luồng nào tiến tiếp được.
- **Livelock:** các luồng vẫn hoạt động và phản ứng với nhau (nhường, hủy, thử lại...), nhưng liên tục lặp mà không đạt được tiến triển hữu ích.

Một thao tác Java trông ngắn gọn không có nghĩa là nguyên tử. Với `count++`, logic bao gồm đọc giá trị, tính giá trị mới và ghi lại. Nếu các bước xen kẽ giữa các luồng mà không có cơ chế đồng bộ đúng, kết quả có thể sai.

## 2. Race condition: kết quả sai do thứ tự xen kẽ

### 2.1 Cách nhận diện

Giả sử `count = 0`, hai luồng đều muốn tăng một lần:

| Bước | Luồng T1 | Luồng T2 |
| --- | --- | --- |
| 1 | Đọc `count = 0` | |
| 2 | | Đọc `count = 0` |
| 3 | Tính `0 + 1`, ghi `count = 1` | |
| 4 | | Tính `0 + 1`, ghi `count = 1` |

Giá trị đúng sau hai lần tăng là **2**, nhưng thực tế là **1**: một cập nhật bị mất (*lost update*). Một lần chạy khác có thể cho kết quả đúng; chính sự phụ thuộc vào lịch thực thi khiến lỗi khó tái hiện.

**Race condition** là khái niệm về tính đúng đắn phụ thuộc thời điểm/thứ tự. **Data race** có nghĩa hẹp hơn trong Java Memory Model: hai thao tác truy cập cùng một biến, ít nhất một thao tác ghi, không được sắp thứ tự bởi quan hệ *happens-before* phù hợp. Data race thường là nguồn gây lỗi, nhưng không nên đánh đồng hai khái niệm. Ngoài cập nhật mất dữ liệu còn có lỗi kiểm tra rồi hành động (*check-then-act*), ví dụ hai luồng đều kiểm tra “chưa tồn tại” rồi cùng chèn một phần tử.

### 2.2 Ví dụ Java 17+ tái hiện cập nhật bị mất

Chương trình dưới đây cố ý cho cả hai luồng đọc bộ đếm trước khi cho phép ghi. `CountDownLatch` làm lịch xen kẽ trở nên có thể dự đoán trong **bài minh họa**; nó không biến bước cập nhật chung thành nguyên tử.

~~~java
// RaceConditionDemo.java
import java.util.concurrent.CountDownLatch;

public class RaceConditionDemo {
    static class Counter {
        int value = 0;
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increment = () -> {
            int observed = counter.value;
            bothRead.countDown();
            try {
                allowWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            counter.value = observed + 1;
        };

        Thread first = new Thread(increment, "first");
        Thread second = new Thread(increment, "second");
        first.start();
        second.start();

        bothRead.await();
        allowWrite.countDown();
        first.join();
        second.join();

        System.out.println("Expected: 2");
        System.out.println("Actual: " + counter.value);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac RaceConditionDemo.java
java RaceConditionDemo
~~~

Kết quả:

~~~text
Expected: 2
Actual: 1
~~~

**Vì sao chắc chắn ra 1?** Cả hai luồng đều lưu giá trị `0` vào biến cục bộ `observed` trước khi `bothRead` về 0. Chỉ sau đó, luồng chính mới mở `allowWrite`, nên hai luồng đều ghi `0 + 1`. `join()` đảm bảo luồng chính đợi chúng kết thúc rồi mới in. Trong một ứng dụng bình thường không có hai latch điều phối, lỗi thường xuất hiện không ổn định và phụ thuộc tải/lịch chạy.

### 2.3 Sửa đúng: nguyên tử hóa thao tác hoặc bảo vệ bất biến

Với một bộ đếm độc lập, `AtomicInteger.incrementAndGet()` cung cấp thao tác tăng nguyên tử:

~~~java
// AtomicCounterDemo.java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger();
        Runnable increment = () -> counter.incrementAndGet();

        Thread first = new Thread(increment);
        Thread second = new Thread(increment);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Actual: " + counter.get());
    }
}
~~~

~~~bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
~~~

Kết quả luôn là:

~~~text
Actual: 2
~~~

Các lựa chọn thường gặp:
- `synchronized` hoặc `Lock`: bảo vệ một đoạn tới hạn (*critical section*) có nhiều thao tác phải nhất quán với nhau.
- `AtomicInteger`, `AtomicLong`, `AtomicReference` và các phép cập nhật nguyên tử: phù hợp với thao tác đơn giản trên trạng thái chia sẻ cụ thể.
- Kiểu dữ liệu bất biến, dữ liệu riêng của mỗi luồng hoặc giảm chia sẻ trạng thái: thường đơn giản và ít rủi ro hơn.
- Collection đồng thời như `ConcurrentHashMap`: giúp các thao tác được hỗ trợ an toàn trong phạm vi bảo đảm của API; chuỗi “đọc rồi kiểm tra rồi ghi” vẫn có thể cần một thao tác gộp nguyên tử như `putIfAbsent` hoặc `compute`.

**Không dùng `volatile` để sửa `count++`.** `volatile` giúp bảo đảm khả năng nhìn thấy giá trị và các ràng buộc thứ tự bộ nhớ nhất định, nhưng không gộp phép đọc–tính–ghi thành một hành động nguyên tử. Tương tự, `Thread.sleep()` chỉ thay đổi thời điểm chạy, không tạo cơ chế bảo vệ dữ liệu.

## 3. Deadlock: các luồng chờ lẫn nhau vô thời hạn

### 3.1 Tình huống điển hình

Có hai khóa độc lập `lockA` và `lockB`:

~~~text
T1: giữ lockA  ──> chờ lockB
                      ▲
                      │
T2: giữ lockB  ──> chờ lockA
        ▲             │
        └─────────────┘
~~~

Ví dụ luồng T1 đi vào `synchronized(lockA)` rồi xin `lockB`, trong khi luồng T2 đi vào `synchronized(lockB)` rồi xin `lockA`. Nếu mỗi luồng đã giữ khóa thứ nhất, cả hai không thể lấy khóa thứ hai. Đây là **deadlock theo thứ tự lấy khóa**.

Đoạn sau là **mã minh họa hai đường thực thi**, không phải một chương trình hoàn chỉnh; giả sử `lockA` và `lockB` là hai đối tượng khóa được chia sẻ:

~~~java
// T1
synchronized (lockA) {
    synchronized (lockB) {
        // Công việc cần cả A và B.
    }
}

// T2: thứ tự ngược lại, có nguy cơ deadlock.
synchronized (lockB) {
    synchronized (lockA) {
        // Công việc cần cả B và A.
    }
}
~~~

Bốn điều kiện cổ điển thường được dùng để phân tích deadlock là: loại trừ lẫn nhau (mutual exclusion), giữ tài nguyên trong khi chờ tài nguyên khác (hold and wait), không bị tước tài nguyên cưỡng bức (no preemption), và chờ vòng tròn (circular wait). Phá một điều kiện phù hợp có thể ngăn deadlock trong thiết kế khóa tương ứng.

### 3.2 Dấu hiệu trong ứng dụng Java

- Một số request hoặc tác vụ dừng vô thời hạn, không có log hoàn thành, dù tiến trình JVM còn sống.
- Các luồng liên quan đợi nhau theo chu trình trong *thread dump*: “T1 giữ A và chờ B; T2 giữ B và chờ A”.
- Với monitor của `synchronized`, luồng chờ lấy monitor thường ở `Thread.State.BLOCKED`. Với `ReentrantLock`, luồng có thể hiển thị `WAITING` hoặc `TIMED_WAITING` do cơ chế park; **chỉ nhìn trạng thái luồng chưa đủ để kết luận**.
- CPU có thể thấp vì nhiều luồng đứng chờ, nhưng CPU thấp không tự nó chứng minh có deadlock.

Lấy thông tin khi có dấu hiệu bị kẹt (cần JDK tools và PID của tiến trình):

~~~bash
jcmd <PID> Thread.print -l
~~~

Trong Java, `ThreadMXBean.findDeadlockedThreads()` có thể tìm vòng chờ liên quan đến monitor và *ownable synchronizer* được JVM quản lý, chẳng hạn `ReentrantLock`. Phương thức có thể trả `null` nếu không tìm thấy; nó không bảo đảm phát hiện mọi kiểu chờ logic, chờ I/O hoặc khóa ở hệ thống ngoài JVM. Một thread dump đơn lẻ cũng không chứng minh được mọi trường hợp treo.

### 3.3 Cách phòng tránh

- **Thống nhất thứ tự lấy khóa** trên mọi đường chạy: nếu phải lấy cả A và B, luôn lấy A trước B. Với nhiều đối tượng động, xác định thứ tự ổn định theo khóa/ID; xử lý cả trường hợp bằng nhau.
- Giữ phạm vi khóa ngắn, tránh gọi tác vụ chặn dài hoặc gọi mã bên ngoài khó kiểm soát trong lúc đang giữ khóa.
- Khi phù hợp, dùng `ReentrantLock.tryLock()` hoặc bản có timeout, giải phóng đúng khóa trong `finally` và có chiến lược retry/hủy rõ ràng. Timeout có thể giúp phục hồi nhưng không tự bảo đảm hệ thống luôn tiến triển.
- Tránh lồng nhiều khóa không cần thiết; xem xét một điểm đồng bộ nhất quán khi bất biến phải bảo vệ thực sự là một khối.

Không có quy tắc “thêm `synchronized` ở mọi nơi” để phòng deadlock: càng giữ nhiều khóa theo các thứ tự khác nhau càng có thể tạo chu trình chờ mới.

## 4. Livelock: liên tục phản ứng nhưng công việc không tiến triển

Hai luồng hoặc hai tác nhân cùng muốn “lịch sự”: nếu tranh chấp, mỗi bên nhường tài nguyên rồi lập tức thử lại. Họ có thể liên tục phát hiện nhau và cùng đổi hướng:

~~~text
Vòng 1: T1 thấy xung đột -> nhường; T2 thấy xung đột -> nhường
Vòng 2: T1 thử lại ngay -> xung đột; T2 thử lại ngay -> xung đột
Vòng 3: cùng nhường, cùng thử lại, ...
Kết quả: có hoạt động, nhưng số thao tác hoàn tất vẫn bằng 0
~~~

Đây là **tình huống minh họa cơ chế**; lịch chạy thực tế có thể phá sự đối xứng, vì thế không thể khẳng định cứ retry là livelock. Livelock cũng có thể xảy ra khi nhiều luồng liên tục hủy/gia hạn thao tác nhằm tránh xung đột hoặc khi hai phía liên tục chuyển trạng thái để đáp ứng nhau.

Dấu hiệu thường gặp:
- Log lặp lại “retry”, “conflict”, “yield”, “rollback” hoặc thay đổi trạng thái mà không có tác vụ hoàn tất.
- Các luồng vẫn chạy hoặc thức dậy thường xuyên; CPU có thể cao, nhưng không bắt buộc.
- Không thấy vòng “giữ khóa rồi chờ khóa” như deadlock; thread dump chỉ ở một thời điểm có thể không đủ. Cần theo dõi **tiến độ** qua nhiều thời điểm: số thao tác hoàn thành, số lần retry và thời gian xử lý.

Biện pháp:
- Retry có **giới hạn số lần hoặc deadline**; khi vượt ngưỡng thì báo lỗi rõ ràng/thực hiện phương án dự phòng.
- Dùng *backoff* với khoảng chờ thay đổi, đôi khi thêm độ ngẫu nhiên (*jitter*) để tránh hai tác nhân hành động đồng bộ. Cách này giảm xác suất, không phải một chứng minh bảo đảm tiến triển.
- Tạo thứ tự ưu tiên, điều phối một phía làm trước hoặc dùng hàng đợi để phá đối xứng.
- Thiết kế điều kiện retry có thể đạt điểm kết thúc; đo cả tốc độ hoàn thành, không chỉ hoạt động CPU.

## 5. So sánh nhanh khi gặp sự cố

| Góc nhìn | Race condition | Deadlock | Livelock |
| --- | --- | --- | --- |
| Vấn đề cốt lõi | Thao tác xen kẽ làm sai dữ liệu/quyết định | Các bên chờ lẫn nhau | Các bên phản ứng và retry mãi mà không hoàn thành |
| Luồng có chạy không? | Thường vẫn chạy và kết thúc | Các luồng tham gia bị chặn/chờ | Có hoạt động hoặc lặp thức dậy |
| Triệu chứng dễ thấy | Kết quả sai, mất cập nhật, lỗi thất thường | Tác vụ treo; có chu trình chờ tài nguyên | Nhiều retry, không tăng số việc hoàn thành |
| Bằng chứng cần tìm | Shared state, bất biến, thứ tự thao tác, đồng bộ | Chủ sở hữu khóa, khóa chờ, chu trình | Log retry, trạng thái thay đổi, throughput qua thời gian |
| Hướng xử lý | Nguyên tử hóa thao tác, bảo vệ bất biến, giảm chia sẻ | Thứ tự khóa cố định, giảm lồng khóa, timeout phù hợp | Phá đối xứng, backoff, giới hạn retry, điều phối |

**Phân biệt thêm với starvation:** một luồng chờ quá lâu vì liên tục bị các luồng khác giành tài nguyên/lịch CPU, trong khi các luồng khác vẫn tiến triển. Starvation không nhất thiết có vòng chờ của deadlock hoặc vòng phản ứng đối xứng của livelock. Một hệ thống cũng có thể mắc nhiều vấn đề đồng thời.

## 6. Quy trình nhận diện thực tế

1. **Xác định triệu chứng và bất biến.** Có dữ liệu sai hay tác vụ không hoàn thành? Ghi rõ kết quả mong đợi và kết quả quan sát được (ví dụ tổng số lần tăng, số yêu cầu hoàn tất).
2. **Khoanh vùng shared state và đường lấy khóa.** Với kết quả sai, tìm chuỗi đọc–sửa–ghi hoặc kiểm tra–hành động, kiểm tra xem toàn bộ chuỗi đã được bảo vệ hay chưa. Với tác vụ treo, truy ra các khóa đang giữ và khóa đang chờ.
3. **Thu thập bằng chứng qua thời gian.** Lấy nhiều thread dump cách nhau một khoảng phù hợp, cùng log, số lượng retry và tốc độ hoàn thành. Một snapshot `RUNNABLE` hoặc `WAITING` chưa đủ xác định livelock/deadlock.
4. **Đối chiếu với mô hình.** Dữ liệu sai do xen kẽ -> nghi race condition. Chu trình chờ tài nguyên -> nghi deadlock. Có hoạt động/retry nhưng không có tiến triển -> nghi livelock. Nếu chỉ một luồng bị bỏ đói trong khi luồng khác hoàn thành -> xem xét starvation.
5. **Sửa đúng nguyên nhân rồi kiểm chứng.** Thêm kiểm thử đồng thời, khẳng định bất biến (assertion), theo dõi latency/throughput và chạy dưới nhiều mức tải. Các bài stress test có thể giúp tái hiện race nhưng một lần chạy thành công không chứng minh chương trình không có race.

### Những nhầm lẫn thường gặp

- “Đã thêm `volatile` nên `counter++` an toàn” — **sai**; visibility không thay thế atomicity.
- “Có `ConcurrentHashMap` nên mọi chuỗi thao tác trên map đều nguyên tử” — **sai**; cần xét hợp đồng của từng phương thức và bất biến xuyên nhiều bước.
- “`sleep` vài mili giây làm hết lỗi” — **không bảo đảm**; chỉ thay đổi lịch chạy.
- “CPU thấp nghĩa là deadlock, CPU cao nghĩa là livelock” — **không đủ**; phải dựa trên vòng chờ hoặc thiếu tiến triển.
- “Thấy `BLOCKED` là có deadlock” — **sai**; chờ khóa tạm thời là bình thường. Cần chứng minh vòng chờ kéo dài.
- “Dùng `tryLock` và retry vô hạn sẽ giải quyết deadlock” — **chưa đủ**; có thể đổi thành livelock hoặc starvation nếu không có chiến lược tiến triển.

## 7. Tự kiểm tra

1. Hai luồng cùng cập nhật `balance` theo mẫu “đọc, tính, ghi”; kết quả có lúc bị mất tiền hoặc cộng thừa. Đây là dấu hiệu gì? **Race condition**; phải kiểm tra nguyên tử của toàn bộ phép cập nhật và bất biến liên quan.
2. T1 giữ khóa A, chờ B; T2 giữ B, chờ A. Đây là gì? **Deadlock**; thống nhất thứ tự khóa hoặc thiết kế lại phạm vi khóa.
3. Hai worker luôn phát hiện xung đột, nhường rồi retry hàng nghìn lần, nhưng không hoàn thành tác vụ. Đây có thể là gì? **Livelock**; cần kiểm tra log/throughput và cách phá đối xứng, giới hạn retry.
4. Một worker chờ rất lâu trong khi những worker khác liên tục hoàn thành. Điều này nhất thiết là deadlock? **Không**; có thể là **starvation**.

**Ghi nhớ:** Race condition đe dọa **tính đúng của kết quả**; deadlock và livelock đe dọa **khả năng tiến triển**, nhưng theo hai cơ chế khác nhau. Chẩn đoán dựa trên bất biến, quan hệ chờ và tiến độ thực tế trước khi chọn công cụ sửa.
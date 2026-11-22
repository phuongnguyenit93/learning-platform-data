# Phân biệt BLOCKED, WAITING và TIMED_WAITING

## 1. Trạng thái luồng cho biết điều gì?

Khi một yêu cầu chạy chậm, nhìn thấy “luồng đang chờ” chưa đủ để tìm nguyên nhân. Nó có thể đang đợi vào vùng `synchronized`, chờ một công việc khác kết thúc, đợi dữ liệu, hoặc chủ động ngủ trong một khoảng thời gian. Ba trạng thái `BLOCKED`, `WAITING`, `TIMED_WAITING` giúp phân loại những tình huống này.

Đây là trạng thái do JVM định nghĩa, không phải bản sao trực tiếp của trạng thái luồng ở hệ điều hành. Một luồng chỉ có một `Thread.State` tại một thời điểm, nhưng trạng thái có thể đổi rất nhanh giữa hai lần quan sát. Bộ enum còn có `NEW`, `RUNNABLE` và `TERMINATED`. [Thread.State](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.State.html)

Hình dung ba câu hỏi:

- **BLOCKED:** “Tôi đang chờ lấy monitor để vào hoặc vào lại vùng synchronized nào?”
- **WAITING:** “Tôi đang chờ một sự kiện/hành động khác, chưa đặt thời hạn ở thao tác chờ này?”
- **TIMED_WAITING:** “Tôi đang thực hiện một thao tác chờ có tham số thời gian?”

Những câu hỏi đó định hướng điều tra, không tự kết luận luồng bị lỗi, bị deadlock hay không dùng CPU. Chẩn đoán cần ghép trạng thái với ngăn xếp lời gọi, đối tượng đang chờ, chủ sở hữu khi có, và diễn biến qua nhiều thời điểm.

## 2. Bảng so sánh cốt lõi

| Đặc điểm | BLOCKED | WAITING | TIMED_WAITING |
| --- | --- | --- | --- |
| Nguyên nhân định nghĩa | Chờ lấy monitor | Chờ một hành động khác, không đặt thời hạn chờ | Chờ với thời gian được chỉ định |
| Ví dụ điển hình | Muốn vào `synchronized` khi monitor đang do luồng khác giữ | `Object.wait()`, `Thread.join()`, `LockSupport.park()` | `Thread.sleep`, `Object.wait(timeout)`, `join(timeout)`, `parkNanos`, `parkUntil` |
| Điều thường cần tìm | Monitor nào, luồng nào đang giữ | Điều kiện/sự kiện gì, bên nào sẽ tạo nó | Chờ gì, ngân sách thời gian nào, có được báo hiệu/ngắt trước hạn không |
| Có tự chứng minh lỗi không? | Không | Không | Không |

Các trạng thái chờ có thời gian ở đây nói đến lời gọi có khoảng thời gian thích hợp, thường là dương. Đừng suy từ việc thấy tên phương thức có tham số thời gian rằng mọi giá trị đầu vào đều tạo `TIMED_WAITING`: `Object.wait(0)` có nghĩa chờ không thời hạn; `Thread.join(0)` cũng không đặt giới hạn chờ. [Định nghĩa từng trạng thái](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.State.html)

## 3. BLOCKED là chờ monitor, không phải mọi loại khóa

Mỗi đối tượng Java có thể được dùng làm monitor bởi `synchronized`. Nếu A đang giữ monitor M, B muốn vào `synchronized(M)` thì B chưa thể thực thi phần bên trong. Trong thời gian chờ monitor đó, B có thể được quan sát ở trạng thái `BLOCKED`.

```text
A giữ monitor M
B muốn synchronized(M)
    → B chưa lấy được M: BLOCKED
A rời vùng giữ M
    → B có thể cạnh tranh lấy M
    → lấy được thì tiếp tục chạy
```

`BLOCKED` cũng áp dụng khi luồng cần lấy lại monitor sau `Object.wait`. Nó không chỉ xuất hiện ở lần đi vào `synchronized` đầu tiên. [Thread.State.BLOCKED](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.State.html#BLOCKED)

**Chờ `ReentrantLock` không đồng nghĩa phải có nhãn BLOCKED.** Khóa kiểu này dùng giao thức đồng bộ khác; trên JDK hiện hành, luồng đang park trong đường chờ lấy khóa thường xuất hiện là `WAITING`, hoặc `TIMED_WAITING` nếu đang chờ có thời hạn. Vẫn phải đọc stack và đối tượng đồng bộ để biết nó đang chờ khóa gì.

Ví dụ một worker `WAITING` tại đường `LockSupport.park` và AQS có thể đang chờ `ReentrantLock`, không phải đang rảnh. Không đếm riêng số `BLOCKED` rồi coi đó là toàn bộ cạnh tranh khóa của ứng dụng. [ReentrantLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)

## 4. WAITING là chờ sự kiện, không nhất thiết là có lỗi

Những trường hợp có thể dẫn tới `WAITING` gồm:

- `Object.wait()` chờ điều kiện được báo hiệu theo giao thức monitor.
- `Thread.join()` chờ một luồng khác kết thúc.
- `LockSupport.park()` tạm chờ trong một giao thức đồng bộ.
- Công cụ thư viện sử dụng các cơ chế đó, chẳng hạn worker chờ tác vụ hoặc một bên chờ tín hiệu hoàn tất.

Tên trạng thái không nói điều kiện nghiệp vụ là gì. Một worker đang chờ hàng đợi khi không có việc là bình thường; một luồng yêu cầu chờ tín hiệu mà không ai còn có thể tạo ra là vấn đề. Cùng nhãn `WAITING`, ý nghĩa vận hành khác nhau.

“Không có thời hạn” cũng không có nghĩa “không thể thức dậy”. Nó vẫn có thể tiếp tục khi sự kiện xảy ra, hoặc thao tác chờ phản ứng với ngắt theo hợp đồng; một số cơ chế còn cho phép trở về sớm. Luôn xem điều kiện mà vòng lặp chờ kiểm tra lại, thay vì cho rằng chỉ cần đánh thức là đã có quyền đi tiếp.

## 5. TIMED_WAITING không có nghĩa sắp hoàn thành yêu cầu

`TIMED_WAITING` có thể là:

- Ngủ để trì hoãn một bước hoặc thực hiện chính sách thử lại.
- Chờ một kết quả với giới hạn thời gian.
- Chờ một giấy phép/khóa có thời hạn.
- Park có thời hạn trong công cụ thư viện.

Trạng thái này chỉ mô tả thao tác chờ hiện tại. Một lời chờ hết hạn có thể được theo sau bằng một lần thử lại khác; vì thế một yêu cầu vẫn có thể kéo dài dù mỗi lần chờ riêng có giới hạn. Tương tự, một thread dump có nhãn chờ thời gian không cho biết chính xác còn bao nhiêu thời gian, hoặc thời điểm tác vụ sẽ hoàn thành.

Phải phân biệt **hết thời hạn chờ** với **đã lấy lại được khóa và chạy tiếp**. Sau một lần `wait(timeout)`, luồng vẫn phải lấy lại monitor trước khi trở về cho mã Java của bên gọi. Nếu monitor chưa rảnh, luồng có thể chuyển sang `BLOCKED`. Thời hạn không phải lời hứa được CPU thực thi đúng tại một mốc tuyệt đối. [Hợp đồng Object.wait](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html#wait(long))

## 6. Chuyển tiếp quan trọng: WAITING → BLOCKED

`Object.wait()` chỉ được gọi khi đang giữ monitor tương ứng. Khi bắt đầu chờ, nó nhả monitor đó; khi kết thúc chờ, phải lấy lại monitor trước khi phương thức hoàn thành. `notify` hoặc `notifyAll` không tự nhả monitor của bên gọi. [Quy tắc wait/notify](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html)

```text
Luồng B:
    giữ M → wait() → nhả M → WAITING

Luồng A:
    giữ M → cập nhật điều kiện → notifyAll()
    vẫn đang giữ M

Luồng B:
    đã được báo hiệu nhưng chưa lấy lại M → BLOCKED

Luồng A:
    rời synchronized(M), nhả M

Luồng B:
    lấy lại M → wait() có thể hoàn thành → kiểm tra điều kiện
```

Đây là lý do “đã notify mà luồng chưa chạy” không nhất thiết là mất tín hiệu. Có thể bên báo hiệu vẫn đang làm việc lâu trong vùng đồng bộ. Cần xem luồng đang giữ monitor thực hiện gì sau lệnh báo hiệu.

`sleep` và `park` không tự cung cấp việc nhả/lấy lại monitor như `wait`. Một luồng ngủ trong `synchronized(M)` vẫn có thể giữ M, khiến luồng khác `BLOCKED`. Trạng thái của người giữ có thể là `TIMED_WAITING` trong khi nhiều người khác bị chặn ở cửa vào. [Thread.sleep](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#sleep(long))

## 7. Chương trình quan sát cả ba trạng thái

Lưu thành `ThreadStateDifferenceDemo.java`. Chương trình dùng platform thread từ `new Thread`, cố ý giữ các điều kiện đủ lâu để quan sát, và dọn mọi luồng ở cuối. Hàm `awaitState` chỉ phục vụ thực nghiệm chẩn đoán; không phải mẫu đồng bộ cho mã ứng dụng.

```java
import java.util.concurrent.TimeUnit;

public class ThreadStateDifferenceDemo {
    private static Thread.State awaitState(Thread thread, Thread.State wanted)
            throws InterruptedException {
        long start = System.nanoTime();
        long limit = TimeUnit.SECONDS.toNanos(5);
        for (;;) {
            Thread.State observed = thread.getState();
            if (observed == wanted) {
                return observed;
            }
            if (observed == Thread.State.TERMINATED
                    || System.nanoTime() - start >= limit) {
                throw new IllegalStateException(
                        thread.getName() + ": expected " + wanted
                                + ", observed " + observed);
            }
            // Polling is used only for this diagnostic demonstration.
            Thread.sleep(1);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Object entryMonitor = new Object();
        Thread blocked = new Thread(() -> {
            synchronized (entryMonitor) {
                // The main thread deliberately owns this monitor first.
            }
        }, "monitor-entry");

        synchronized (entryMonitor) {
            blocked.start();
            System.out.println("entry="
                    + awaitState(blocked, Thread.State.BLOCKED));
        }
        blocked.join();

        Object waitMonitor = new Object();
        boolean[] proceed = {false};
        Thread waiting = new Thread(() -> {
            synchronized (waitMonitor) {
                try {
                    while (!proceed[0]) {
                        waitMonitor.wait();
                    }
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "condition-waiter");

        waiting.start();
        try {
            System.out.println("before-notify="
                    + awaitState(waiting, Thread.State.WAITING));
            synchronized (waitMonitor) {
                proceed[0] = true;
                waitMonitor.notifyAll();
                System.out.println("after-notify-before-unlock="
                        + awaitState(waiting, Thread.State.BLOCKED));
            }
        } finally {
            synchronized (waitMonitor) {
                proceed[0] = true;
                waitMonitor.notifyAll();
            }
            waiting.join();
        }

        Thread timed = new Thread(() -> {
            try {
                Thread.sleep(30_000);
            } catch (InterruptedException exception) {
                // The main thread interrupts only to end this demonstration.
                Thread.currentThread().interrupt();
            }
        }, "timed-sleeper");

        timed.start();
        try {
            System.out.println("sleep="
                    + awaitState(timed, Thread.State.TIMED_WAITING));
        } finally {
            timed.interrupt();
            timed.join();
        }
        System.out.println("finished=" + timed.getState());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac ThreadStateDifferenceDemo.java
java ThreadStateDifferenceDemo
```

Stdout khi các mốc được quan sát trong giới hạn năm giây:

```text
entry=BLOCKED
before-notify=WAITING
after-notify-before-unlock=BLOCKED
sleep=TIMED_WAITING
finished=TERMINATED
```

### Đọc từng bước

1. Luồng chính giữ `entryMonitor` trước khi bắt đầu worker. Worker không vào được vùng synchronized, nên được quan sát là `BLOCKED`. Rời vùng đồng bộ cho nó hoàn thành, rồi `join` thu dọn.
2. `condition-waiter` dùng vòng `while` và `wait()` trên `waitMonitor`. Khi điều kiện chưa đúng và đã nhả monitor để chờ, nó là `WAITING`.
3. Luồng chính lấy `waitMonitor`, đặt điều kiện và gọi `notifyAll`, nhưng **vẫn giữ monitor** trong lúc quan sát. Worker đã có cơ hội lấy lại monitor nhưng chưa được vào, nên chuyển thành `BLOCKED`.
4. Luồng `timed-sleeper` ngủ 30 giây; luồng chính quan sát `TIMED_WAITING` rồi ngắt để kết thúc sớm. Chương trình không cần thật sự chờ đủ 30 giây.
5. Sau `join` của sleeper, nó đã kết thúc nên `getState()` trả `TERMINATED`.

Biến `proceed` trong mảng chỉ được đọc/ghi khi giữ cùng `waitMonitor`; tính nhất quán của điều kiện dựa vào monitor đó, không dựa vào `getState`. Vòng `while` xử lý cả khả năng `wait()` trở về mà điều kiện chưa đúng.

Hàm quan sát kiểm tra trạng thái lặp lại có giới hạn, thay vì ngủ một khoảng rồi đoán worker đã đến điểm cần xem. Trên một máy bị treo hoặc quá tải đến mức không quan sát được trong năm giây, chương trình báo lỗi mốc quan sát; không nên sửa bằng cách khẳng định trạng thái phải luôn xuất hiện tại một thời điểm lịch cố định.

Trong phần notify, chính việc giữ monitor khi gọi hàm quan sát là dụng ý để giữ worker ở `BLOCKED`. Không sao chép cách giữ khóa lâu này vào đường xử lý nghiệp vụ. Trong ứng dụng, `Thread.getState()` dành cho giám sát, không dùng làm điều kiện cấp quyền hay quyết định có cần khóa hay không. [Thread.getState](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#getState())

## 8. Từ nhãn trạng thái đến câu hỏi chẩn đoán

Khi đọc thread dump hoặc thông tin quản lý luồng, đi theo một chuỗi ngắn:

1. Ghi nhận tên/định danh luồng và thời điểm chụp.
2. Đọc trạng thái cùng các frame đầu stack và frame thuộc mã ứng dụng.
3. Xác định monitor, đối tượng park hoặc công cụ đồng bộ đang chờ nếu có thông tin.
4. Với cạnh tranh khóa, tìm bên đang giữ và đọc stack của bên đó.
5. Với điều kiện/kết quả/tác vụ, tìm bên có trách nhiệm làm điều kiện đúng.
6. So sánh các ảnh chụp qua thời gian và ghép với thời gian đáp ứng/CPU/tải liên quan.

`ThreadInfo` có thể cung cấp trạng thái, stack, thông tin đối tượng chờ, chủ sở hữu và các khóa đang giữ. Nó là dữ liệu giám sát. Các trường khả dụng tùy loại chờ và khả năng công cụ; không thấy chủ sở hữu không tự chứng minh không ai gây ra sự chờ. [ThreadInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadInfo.html)

Ví dụ cách suy luận, không phải trích một dump thực tế:

| Quan sát | Hướng kiểm tra tiếp |
| --- | --- |
| Nhiều luồng BLOCKED ở cùng điểm vào synchronized | Tìm chủ sở hữu monitor và việc nó đang làm trong vùng giữ khóa |
| WAITING trong đường chờ lấy ReentrantLock | Đọc đối tượng khóa, người giữ nếu công cụ cung cấp, thứ tự lấy khóa |
| WAITING khi lấy việc từ hàng đợi | Kiểm tra còn nguồn công việc không và worker rảnh có đúng với tải không |
| TIMED_WAITING ở một vòng thử lại | Kiểm tra giới hạn số lần thử, nguyên nhân thử lại và ngân sách tổng |
| Sau notify, người chờ BLOCKED | Kiểm tra bên báo hiệu đã nhả monitor chưa |

Không suy CPU cao hay thấp từ nhãn một mình. `RUNNABLE` ở JVM cũng không bảo đảm đang thực hiện lệnh Java trên CPU tại đúng lúc chụp; có thể liên quan tài nguyên hệ điều hành. Muốn kết luận tiêu tốn CPU cần đo CPU theo thời gian và đọc stack tương ứng. [RUNNABLE trong Thread.State](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.State.html#RUNNABLE)

## 9. Công cụ quan sát và giới hạn hiện hành

Có thể lấy dump bằng công cụ JDK như `jcmd`, sau khi chọn đúng tiến trình. Ví dụ cú pháp sau cần thay `12345` bằng PID của JVM muốn quan sát; chỉ là lệnh minh họa, không phải PID của chương trình trong bài:

```shell
jcmd -l
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l
```

Dùng phần help của JVM đích để xác nhận lệnh và tùy chọn được hỗ trợ. Định dạng và chi tiết frame trong dump có thể khác giữa JDK, nên đừng học thuộc một tên frame nội bộ rồi coi đó là hợp đồng chung. [Tài liệu jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html)

Với API quản lý, `ThreadMXBean` hiện hỗ trợ platform thread, không quản lý/giám sát virtual thread như một tập đầy đủ. Khi ứng dụng dùng virtual thread, cần công cụ quan sát phù hợp với chúng trên JDK đang chạy; không dùng thống kê MXBean để kết luận đã bao quát mọi luồng ứng dụng. [Phạm vi ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html)

Các số liệu `getBlockedCount`/`getBlockedTime` trong `ThreadInfo` nói đến chờ vào hoặc vào lại monitor; không phải tổng mọi thời gian chờ `ReentrantLock`. Việc theo dõi thời gian còn phụ thuộc khả năng và trạng thái bật theo dõi của JVM; một giá trị không khả dụng không nên được diễn giải thành “không từng chờ”. [Thống kê ThreadInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadInfo.html)

## 10. Trạng thái chờ khác deadlock và thiếu tiến triển

Một `BLOCKED` kéo dài có thể do vùng giữ monitor quá lâu, hoặc do chu trình chờ khóa. Một `WAITING` kéo dài có thể hoàn toàn bình thường, cũng có thể do thiếu tín hiệu, cạn nguồn công việc hoặc chu trình phụ thuộc tác vụ. Cần xác định **ai đang chờ ai hoặc chờ điều gì**, rồi xem bên tạo tiến triển còn có khả năng chạy không.

Ví dụ:

- A giữ M1, cần M2; B giữ M2, cần M1: có thể hình thành chu trình khóa.
- A chờ latch nhưng mọi đường gọi `countDown` đã bị bỏ qua do lỗi: không nhất thiết có chu trình sở hữu khóa, nhưng công việc không tiến triển.
- Tất cả worker của một nhóm đều đang chờ kết quả các tác vụ con chưa được nhóm đó chạy: cần xem cấu trúc phụ thuộc và dung lượng thực thi.

`findDeadlockedThreads` của `ThreadMXBean` có phạm vi phát hiện các chu trình được hỗ trợ với platform thread và các loại khóa liên quan. Kết quả không thấy chu trình không chứng minh hệ thống không có mọi loại treo logic hoặc thiếu tín hiệu. [Phát hiện deadlock của ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html#findDeadlockedThreads())

## 11. Những nhận định dễ sai

| Nhận định | Điều chỉnh |
| --- | --- |
| Luồng đợi bất kỳ khóa nào đều BLOCKED | BLOCKED chỉ chờ monitor theo định nghĩa JVM; cơ chế park có nhãn khác |
| WAITING luôn là luồng rảnh | Có thể đang chờ khóa, kết quả hoặc tín hiệu quan trọng |
| TIMED_WAITING chắc chắn kết thúc đúng sau N ms | Hết thời gian không bảo đảm lập lịch ngay hoặc đã lấy lại monitor |
| notifyAll làm mọi người chờ chạy ngay | Bên gọi vẫn giữ monitor đến khi nhả; các luồng phải cạnh tranh lấy lại |
| wait nhả mọi khóa luồng đang giữ | Nó nhả monitor liên quan đến lời wait; các khóa khác vẫn cần phân tích riêng |
| sleep trong synchronized giúp người khác lấy monitor | Sleep không nhả monitor đang giữ |
| Một ảnh chụp đủ chứng minh deadlock | Cần thông tin phụ thuộc/khóa và bằng chứng tiến triển phù hợp |
| getState có thể thay điều kiện đồng bộ | Nó là dữ liệu giám sát, có thể thay đổi ngay sau khi đọc |

## 12. Tự kiểm tra

1. **B đang Object.wait(), A notifyAll nhưng vẫn ở trong synchronized. B có thể là gì?** Có thể `BLOCKED` khi đang chờ lấy lại monitor; không cần giả định tín hiệu đã mất.
2. **Một luồng chờ ReentrantLock hiện WAITING có mâu thuẫn với việc nó đang chờ khóa không?** Không. Từ “bị chặn” trong lời nói rộng hơn hằng enum `BLOCKED`.
3. **Có thể coi worker TIMED_WAITING trong vòng thử lại là đã có ngân sách tổng hữu hạn không?** Không. Cần kiểm tra số lần thử và cách cập nhật thời hạn của toàn bộ thao tác.
4. **Vì sao luồng giữ monitor lại có thể TIMED_WAITING?** Nó có thể đang ngủ hoặc chờ theo thời gian bằng thao tác không nhả monitor đó, trong khi các luồng cần monitor bị BLOCKED.
5. **Nếu getState trả WAITING, lần đọc tiếp có chắc vẫn WAITING không?** Không. Nó là ảnh chụp tại thời điểm đọc; cần kiểm tra chuỗi quan sát và ngữ cảnh.

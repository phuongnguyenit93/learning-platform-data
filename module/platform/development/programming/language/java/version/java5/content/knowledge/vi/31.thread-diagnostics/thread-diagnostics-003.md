# Giới hạn của ảnh chụp trạng thái tại một thời điểm

## Khái niệm: ảnh chụp cho biết điều vừa được quan sát

Một bản chụp luồng, trạng thái `Thread.State` hay đối tượng `ThreadInfo` là bằng chứng về thời điểm thu thập, không phải bản ghi đầy đủ quá trình thực thi. Luồng có thể đổi trạng thái ngay sau khi lấy mẫu, trước cả khi người đọc mở tệp kết quả.

Ví dụ, thấy một luồng ở `WAITING` chỉ cho biết nó đang chờ theo cách được công cụ quan sát. Chưa thể kết luận nó bị treo, chờ bao lâu, có ảnh hưởng người dùng hay ai gây ra sự cố. Muốn trả lời các câu hỏi đó cần thêm thời gian, ngữ cảnh và các quan sát khác.

API `Thread.getState()` và `ThreadInfo` được thiết kế cho giám sát, không dùng làm cơ chế điều khiển đồng bộ. Chương trình không nên quyết định được phép sửa dữ liệu chỉ vì vừa thấy luồng khác đang chờ. [Thread.getState](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#getState()), [ThreadInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadInfo.html)

## Vì sao một ảnh dễ dẫn đến kết luận quá mức?

Một sự cố thường là quan hệ theo thời gian: yêu cầu đã chậm từ khi nào, hàng đợi có tăng không, chủ khóa có tiếp tục làm việc không, các tác vụ khác có hoàn tất không. Một ảnh chỉ giữ lại một lát cắt của các quan hệ đó.

Xét ba tình huống có thể cùng cho một dòng stack ở `await()`:

- Luồng nền đang rảnh, chờ công việc mới đúng thiết kế.
- Tác vụ vừa bắt đầu chờ dữ liệu và sẽ được báo ngay sau đó.
- Tác vụ đã chờ rất lâu vì bên tạo dữ liệu không bao giờ báo.

Stack hiện tại có thể giống nhau, nhưng ý nghĩa vận hành khác hẳn. Cần liên hệ với tuổi tác vụ, thời hạn mong đợi, số công việc hoàn tất và vai trò của luồng.

Ngược lại, một lỗi rất ngắn có thể xảy ra hoàn toàn giữa hai lần chụp. Không thấy nó trong ảnh không có nghĩa nó chưa từng xảy ra.

## Đọc trạng thái đúng mức bằng chứng

| Trạng thái quan sát | Có thể nói | Chưa thể suy ra chỉ từ trạng thái |
| --- | --- | --- |
| `RUNNABLE` | Luồng ở trạng thái runnable theo JVM | Đang dùng CPU liên tục hoặc là nguyên nhân CPU cao |
| `BLOCKED` | Chờ lấy monitor | Mọi loại chờ khóa đều dùng trạng thái này |
| `WAITING` | Chờ không có thời hạn theo cơ chế hiện tại | Đang deadlock hoặc không thể thức lại |
| `TIMED_WAITING` | Đang chờ với một giới hạn thời gian | Đã vượt thời hạn nghiệp vụ hoặc hệ thống bị lỗi |
| `TERMINATED` | Luồng đã kết thúc | Mọi công việc của yêu cầu đã thành công |

Đây là trạng thái của máy ảo, không phải bản sao trực tiếp trạng thái luồng của hệ điều hành. Một luồng `RUNNABLE` có thể đang chờ tài nguyên từ hệ điều hành, chẳng hạn CPU; bản thân nhãn này không phải phép đo lượng CPU. `BLOCKED` dành cho chờ monitor, còn nhiều cơ chế dựa trên park có thể xuất hiện dưới dạng chờ khác. [Thread.State](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.State.html)

Vì vậy, nếu chỉ đếm `BLOCKED` để tìm mọi cạnh tranh đồng bộ, ta có thể bỏ sót người đang chờ một khóa dựa trên `LockSupport`. Cần đọc cả stack, đối tượng chờ và thông tin sở hữu có sẵn.

## Giới hạn thứ nhất: mẫu cũ không tự cập nhật

`ThreadInfo` trả về thông tin được thu thập cho một lần quan sát. Giữ tham chiếu đến nó rồi đọc lại sau không yêu cầu JVM làm một lần chụp mới. Trường trạng thái trong thông tin cũ có thể vẫn là `WAITING` dù luồng thật đã kết thúc.

Ngay cả hai lệnh quan sát liên tiếp cũng không phải giao dịch điều khiển trạng thái. Giữa `getState()` và một phép đọc stack khác, luồng có thể chạy tiếp, đổi vị trí hoặc kết thúc. Khi ghép nhiều nguồn, cần ghi rõ chúng có cùng lần thu thập hay chỉ gần thời gian nhau.

Với `Thread.getAllStackTraces()`, tài liệu còn nêu rõ stack của mỗi luồng là một ảnh chụp và có thể được lấy ở các thời điểm khác nhau. Không nên mặc định mọi bảng số liệu tự ghép từ nhiều API là một trạng thái toàn cục đóng băng ở đúng một nanosecond. [Thread.getAllStackTraces](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#getAllStackTraces())

## Minh chứng Java: ảnh lưu vẫn WAITING sau khi luồng kết thúc

Chương trình Java 17+ sau giữ một luồng bằng latch, lấy mẫu `ThreadInfo` khi nó đang chờ rồi mở latch cho luồng kết thúc. Sau đó chương trình so sánh thông tin đã lưu với trạng thái mới của đối tượng `Thread`.

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class SnapshotLimitDemo {
    static ThreadInfo captureWaiting(ThreadMXBean bean, String name) {
        long start = System.nanoTime();
        long budget = TimeUnit.SECONDS.toNanos(5);
        do {
            for (ThreadInfo info : bean.dumpAllThreads(false, false, 3)) {
                if (info != null
                        && name.equals(info.getThreadName())
                        && info.getThreadState() == Thread.State.WAITING) {
                    return info;
                }
            }
            Thread.yield();
        } while (System.nanoTime() - start < budget);
        throw new AssertionError("WAITING sample was not observed");
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        String name = "snapshot-demo-" + Long.toUnsignedString(System.nanoTime());

        Thread worker = new Thread(() -> {
            entered.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, name);
        worker.setDaemon(true);
        worker.start();

        ThreadInfo saved;
        try {
            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Worker did not start");
            }
            saved = captureWaiting(bean, name);
        } finally {
            release.countDown();
            worker.join(5000);
        }

        if (worker.isAlive()) {
            throw new AssertionError("Worker did not finish");
        }
        System.out.println("savedState=" + saved.getThreadState());
        System.out.println("currentState=" + worker.getState());
        System.out.println("savedAgain=" + saved.getThreadState());
    }
}
```

Lưu thành `SnapshotLimitDemo.java`, rồi chạy:

```shell
javac SnapshotLimitDemo.java
java SnapshotLimitDemo
```

Stdout khi chương trình thu được mẫu trong ngân sách kiểm tra:

```text
savedState=WAITING
currentState=TERMINATED
savedAgain=WAITING
```

`saved` mô tả lần đã quan sát `WAITING`; nó vẫn mô tả lần đó khi đọc lại. `worker.getState()` ở cuối là lần quan sát mới, sau `join` và kiểm tra đã kết thúc. Hai kết quả không mâu thuẫn: chúng nói về hai thời điểm khác nhau.

Vòng lấy mẫu có giới hạn 5 giây để một môi trường không thu được trạng thái mong đợi không làm ví dụ quay vô hạn. Latch mới là giao thức cho luồng chạy tiếp; vòng quan sát không dùng để quyết định quyền truy cập dữ liệu nghiệp vụ.

Tên riêng trong ví dụ chỉ để tìm đúng luồng do chương trình nhỏ này tạo. Trong một dịch vụ thật, tên có thể trùng hoặc đổi; không được dùng tên một mình làm định danh chắc chắn cho chuỗi bằng chứng.

Tham số `3` trong `dumpAllThreads(false, false, 3)` cố ý giới hạn độ sâu stack. Một bản thu như vậy vẫn có thông tin trạng thái nhưng không hứa có toàn bộ chuỗi gọi. Hai cờ `false` cũng không yêu cầu danh sách khóa đang giữ. Không thể suy luận từ dữ liệu không được yêu cầu rằng luồng không giữ khóa. [ThreadMXBean: các biến thể dumpAllThreads](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html)

## Giới hạn thứ hai: stack là vị trí, không phải thời lượng

Một frame ở đầu stack cho thấy nơi được quan sát trong lần lấy mẫu. Nó không cho biết toàn bộ thời gian yêu cầu đã tiêu tốn tại đó.

Ví dụ, một hàm kiểm tra hàng đợi chạy rất nhanh nhưng được gọi thường xuyên có thể xuất hiện nhiều trong mẫu. Một phép gọi mạng rất chậm cũng có thể xuất hiện nhiều. Muốn phân biệt, cần loại phép đo phù hợp: CPU, thời gian chờ, sự kiện I/O, thời lượng tác vụ hoặc hồ sơ lấy mẫu.

Hai mẫu liên tiếp giống stack có ít nhất hai cách giải thích:

- Luồng chưa rời được vị trí chờ.
- Luồng đã chạy nhiều vòng và mỗi lần chụp lại gặp cùng một vị trí.

Đối chiếu số công việc hoàn tất hoặc mã tác vụ đang xử lý giúp phân biệt. Cùng một luồng trong nhóm xử lý có thể đã nhận yêu cầu mới giữa hai mẫu; so sánh chỉ stack và tên luồng có thể nhầm nhiều công việc khác nhau thành một công việc bị kẹt.

## Giới hạn thứ ba: bộ đếm tích lũy chưa phải tốc độ

Giả sử thông tin CPU cho một luồng là 80 giây. Con số đó không cho biết nó đang gây CPU cao trong một phút gần đây hay chỉ đã hoạt động từ nhiều giờ trước.

Với một luồng nền tảng còn sống và cùng định danh, có thể lấy hai giá trị hợp lệ:

```text
deltaCpu  = cpu(t2) - cpu(t1)
deltaWall = thời gian đơn điệu giữa hai lần đo
tỷ lệ CPU xấp xỉ = deltaCpu / deltaWall
```

Nếu cả hai đo bằng nanosecond, tỷ lệ gần `1` tương ứng xấp xỉ một CPU logic được luồng đó dùng trong khoảng đo. Đây là giá trị trên một khoảng, không phải nhãn `RUNNABLE` tại một điểm.

Trước khi trừ, phải xác minh đo CPU được hỗ trợ và đã bật, hai giá trị không phải mã không khả dụng, JVM không khởi động lại và định danh vẫn chỉ cùng một luồng. ThreadMXBean mô tả thời gian CPU có độ phân giải nanosecond nhưng không bảo đảm độ chính xác nanosecond. [ThreadMXBean: đo CPU](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html)

Tương tự, thời gian chặn/chờ tích lũy còn phụ thuộc việc bật theo dõi cạnh tranh và có thể trả `-1` khi không có dữ liệu. Giá trị `-1` không phải âm một mili giây chờ; nó là dấu hiệu phải kiểm tra khả năng và cấu hình. `blockedTime` gắn với chờ monitor, không phải một đồng hồ tổng cho mọi loại chờ trong chương trình. [ThreadInfo: thống kê chặn/chờ](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadInfo.html)

## Giới hạn thứ tư: không có thông tin không đồng nghĩa không có sự kiện

Có nhiều lý do một bản chụp thiếu phần mong đợi:

- Luồng kết thúc sau lúc liệt kê định danh nhưng trước lúc yêu cầu thông tin.
- Độ sâu stack bị giới hạn hoặc VM không cung cấp được stack tương ứng.
- Công cụ không thu monitor hay ownable synchronizer trong lần đó.
- Khả năng đo hoặc chế độ theo dõi chưa được hỗ trợ/bật.
- Loại luồng nằm ngoài phạm vi của API đang dùng.

Do đó cần giữ nguyên trạng thái `null`, rỗng hoặc không khả dụng trong diễn giải, thay vì thay chúng bằng kết luận không có luồng/khóa/chờ.

Đặc biệt, ThreadMXBean trong Java hiện đại quản lý và giám sát **luồng nền tảng**, không giám sát luồng ảo. Một dịch vụ dùng virtual thread không thể được mô tả đầy đủ bằng bảng ThreadMXBean rồi kết luận đó là toàn bộ luồng tác vụ. Cũng cần nhớ thread ID có thể được dùng lại sau khi luồng kết thúc; không ghép chuỗi mẫu dài chỉ dựa trên con số ID mà bỏ qua vòng đời. [Phạm vi và định danh của ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html)

## Giới hạn thứ năm: một người chờ chưa chỉ ra nguyên nhân gốc

Thấy nhiều luồng chờ một khóa giúp tìm điểm tập trung, nhưng nguyên nhân có thể nằm ở người giữ khóa: nó gọi I/O, đợi tác vụ khác, giữ khóa quá lâu hoặc bị hạn chế CPU. Cần lần theo bên sở hữu và quan hệ đợi, không chỉ đếm người chờ.

Ngược lại, một chuỗi phụ thuộc không nhất thiết được biểu diễn hoàn toàn bằng monitor hoặc ownable synchronizer. Tác vụ có thể chờ `Future`, tài nguyên ngoài JVM, phản hồi mạng hoặc công việc mà nhóm luồng chưa chạy được.

Công cụ phát hiện deadlock của ThreadMXBean có phạm vi cụ thể với các vòng đợi monitor/ownable synchronizer giữa luồng nền tảng. Kết quả không tìm thấy vòng thuộc phạm vi đó không chứng minh hệ thống không có bế tắc nghiệp vụ, cạn nhóm luồng, livelock hoặc phụ thuộc I/O không kết thúc. [ThreadMXBean.findDeadlockedThreads](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html#findDeadlockedThreads())

Khi viết kết luận, nên phân biệt ba mức:

| Mức | Ví dụ diễn đạt |
| --- | --- |
| Quan sát | Trong mẫu T1, 12 luồng cùng chờ tại đường lấy khóa K |
| Giả thuyết | Người giữ K có thể đang kéo dài vùng tới hạn do gọi dịch vụ ngoài |
| Xác minh tiếp | So sánh mẫu sau, CPU của người giữ, thời lượng I/O và log cùng tác vụ |

Đừng viết nguyên nhân đã xác nhận khi dữ liệu mới đủ hình thành một giả thuyết.

## Thu thêm bằng chứng theo câu hỏi cần trả lời

Một quy trình ngắn có thể đi theo thứ tự:

1. Ghi đúng tiến trình/JVM, phiên bản JDK, thời điểm và cửa sổ sự cố; liên hệ với yêu cầu chậm hoặc số liệu tải.
2. Ghi cấu hình thu: phạm vi luồng, độ sâu stack, có thông tin khóa không và các bộ đếm nào khả dụng.
3. Lấy thêm mẫu trong khoảng liên quan; so sánh trạng thái, vị trí, chủ sở hữu và tiến độ tác vụ.
4. Bổ sung số liệu theo thời gian: chênh lệch CPU, hàng đợi, công việc hoàn tất, thời lượng I/O hoặc bản ghi sự kiện.
5. Viết kết luận gồm điều đã thấy, điều chưa đủ bằng chứng và phép kiểm tra tiếp theo.

Khoảng cách giữa các mẫu nên phù hợp thời lượng vấn đề: lấy quá thưa có thể bỏ mất sự kiện ngắn, còn lấy dày quá mức có thể thêm chi phí và một đống ảnh giống nhau. Không có một số lượng mẫu cố định bảo đảm tìm được mọi lỗi.

Với JDK hiện tại, `jcmd` có thể liệt kê lệnh bằng `jcmd <pid> help` và xem trợ giúp riêng của lệnh trước khi thu. Các lệnh `Thread.print`, `Thread.dump_to_file` và JFR có dữ liệu/phạm vi khác nhau; dùng loại thu đáp ứng câu hỏi và kiểm tra hỗ trợ trên JVM đích. Thu stack nhiều luồng cũng có chi phí, không nên mặc định một thao tác chẩn đoán hoàn toàn không ảnh hưởng ứng dụng. [Tài liệu jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html)

Bản ghi sự kiện theo thời gian như JFR hữu ích khi một ảnh không cho biết thời lượng hoặc trình tự. Tuy vậy cấu hình sự kiện, ngưỡng và cách lấy mẫu vẫn quyết định những gì được ghi. Không thấy một sự kiện trong bản ghi chưa bật đúng loại sự kiện không phải bằng chứng nó không xảy ra. [Công cụ chẩn đoán và Flight Recorder](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html)

## Những kết luận nên sửa khi đọc ảnh chụp

| Kết luận quá mức | Cách diễn giải có cơ sở hơn |
| --- | --- |
| Luồng RUNNABLE nên chắc chắn đang đốt CPU | Nó runnable ở lần quan sát; cần delta CPU hoặc hồ sơ CPU để đo mức sử dụng |
| Nhiều WAITING nghĩa là ứng dụng treo | Có nhiều luồng chờ; cần xem vai trò, tiến độ và thời hạn của công việc |
| Hai stack giống nhau nên luồng không làm gì | Có thể kẹt hoặc đang lặp cùng đường; đối chiếu CPU và số tác vụ hoàn tất |
| Không có owner nghĩa là không có khóa liên quan | Kiểm tra loại chờ, hỗ trợ công cụ và dữ liệu sở hữu có được thu không |
| Không tìm thấy deadlock nên không thể bế tắc | Chỉ chưa thấy vòng thuộc phạm vi detector; vẫn cần xét phụ thuộc khác |
| Danh sách MXBean là mọi luồng trong dịch vụ | Kiểm tra phạm vi platform/virtual thread và vòng đời lúc thu |
| Đọc lại ThreadInfo là trạng thái hiện tại | Nó vẫn là thông tin lần cũ; cần thực hiện lần thu mới |

Để luyện tập, hãy tưởng tượng một nhóm 50 luồng có 45 luồng chờ lấy công việc. Nếu hàng đợi rỗng và các yêu cầu mới vẫn hoàn tất đúng hạn, mẫu đó có thể hoàn toàn bình thường. Nếu hàng đợi tăng liên tục và chỉ năm luồng còn lại chờ cùng một phụ thuộc ngoài, cần điều tra đường phụ thuộc ấy. Cùng một con số `WAITING` có ý nghĩa khác nhau khi gắn với tiến độ.

Ảnh chụp trạng thái là điểm bắt đầu tốt cho một giả thuyết. Kết luận vững hơn xuất hiện khi đặt ảnh vào chuỗi thời gian, biết phạm vi công cụ và đối chiếu với điều ứng dụng thực sự cần hoàn thành.

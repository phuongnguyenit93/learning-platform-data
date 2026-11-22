# Chọn khóa chung khi cần phối hợp nhiều thao tác trên StringBuffer

## Mục tiêu

StringBuffer là bộ đệm chuỗi có thể thay đổi; nhiều phương thức như append(), insert(), delete() được đồng bộ để bảo vệ từng lời gọi trên cùng một đối tượng. Tuy nhiên, **thread-safe ở cấp phương thức không đồng nghĩa một chuỗi phương thức là nguyên tử**. Khi có nhiều luồng cùng kiểm tra điều kiện rồi sửa nội dung, hoặc phải thêm nhiều mảnh văn bản như một bản ghi liền mạch, ta cần một **khóa chung** bao trùm toàn bộ thao tác logic.

Sau bài này, người học cần biết khi nào cần đồng bộ bổ sung, chọn monitor nào, vì sao mọi luồng phải dùng cùng một đối tượng khóa, và cách kiểm tra bất biến sau khi thực thi đồng thời.

## 1. Vì sao đồng bộ từng phương thức là chưa đủ?

Xét yêu cầu: log chỉ có một dòng HEADER ở đầu, sau đó mỗi luồng thêm tên mình. Đoạn mã sau **chưa an toàn cho thao tác ghép**, dù StringBuffer có các phương thức synchronized:

```java
// Minh họa một đoạn xử lý, không phải chương trình chạy độc lập.
if (log.length() == 0) {
    log.append("HEADER\n");
}
log.append(Thread.currentThread().getName()).append('\n');
```

Một trình tự xen kẽ hợp lệ:

1. T1 gọi length() và thấy 0; lời gọi kết thúc, monitor được nhả.
2. T2 gọi length() và cũng thấy 0.
3. T1 append("HEADER\n").
4. T2 append("HEADER\n").
5. Hai luồng thêm bản ghi của mình: log có hai HEADER, vi phạm yêu cầu.

Đây là lỗi **check-then-act**: giá trị đã kiểm tra không còn đáng tin khi hành động được thực hiện ở lời gọi khác. Tương tự, ba lời gọi append("["); append(data); append("]") có thể bị một luồng khác chen vào giữa; từng append() vẫn bảo vệ trạng thái nội bộ của StringBuffer nhưng không bảo đảm ba mảnh là một bản ghi nguyên tử.

**Nguyên tắc:** Nếu quyết định của bước sau phụ thuộc kết quả bước trước, hoặc nhiều bước phải xuất hiện như một đơn vị, hãy bảo vệ toàn bộ chuỗi bước bằng một vùng tới hạn.

## 2. Khóa chung là cùng một đối tượng, không chỉ cùng tên

Trong Java, synchronized(lock) lấy monitor gắn với **danh tính đối tượng** của lock. Hai luồng chỉ chặn nhau khi lấy đúng monitor của cùng một instance. Với một StringBuffer đã được chia sẻ, chọn chính buffer làm khóa thường đơn giản nhất:

```java
// Các luồng phải được chia sẻ cùng tham chiếu buffer.
synchronized (buffer) {
    if (buffer.length() == 0) {
        buffer.append("HEADER\n");
    }
    buffer.append("event: ").append("done").append('\n');
}
```

Phương thức synchronized của StringBuffer cũng sử dụng monitor của chính buffer. Do khóa Java có tính **reentrant**, một luồng đã ở trong synchronized(buffer) có thể gọi các phương thức synchronized trên buffer đó. Luồng khác lấy cùng monitor phải chờ toàn bộ khối kết thúc.

Phạm vi nguyên tử ở đây là cả việc kiểm tra rỗng, quyết định ghi header, và ghi bản ghi. Nếu chỉ khóa riêng length(), rồi nhả khóa trước append(), lỗi vẫn tồn tại. Một luồng chỉ dùng synchronized(otherLock) trong khi luồng kia dùng synchronized(buffer) cũng không phối hợp được; hai monitor không tự liên kết với nhau.

Cần thỏa thuận và thực thi **cùng quy ước khóa trên mọi đường truy cập liên quan đến bất biến**. Một append() đứng ngoài vùng tới hạn vẫn an toàn ở cấp lời gọi, nhưng có thể chen giữa các bước của thao tác ghép và phá vỡ quy tắc nghiệp vụ.

## 3. Chương trình đầy đủ trên Java 17+

Chương trình dưới đây cho hai luồng khởi động gần nhau, mỗi luồng muốn bảo đảm có HEADER rồi ghi tên mình. CountDownLatch chỉ điều phối thời điểm bắt đầu; **synchronized(log) mới bảo vệ điều kiện và cập nhật**.

```java
import java.util.concurrent.CountDownLatch;

public class SharedLockDemo {
    public static void main(String[] args) throws InterruptedException {
        StringBuffer log = new StringBuffer();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Runnable task = () -> {
            ready.countDown();
            try {
                start.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            synchronized (log) {
                if (log.length() == 0) {
                    log.append("HEADER\n");
                }
                log.append(Thread.currentThread().getName()).append('\n');
            }
        };

        Thread first = new Thread(task, "T1");
        Thread second = new Thread(task, "T2");
        first.start();
        second.start();

        ready.await();
        start.countDown();
        first.join();
        second.join();

        String snapshot;
        synchronized (log) {
            snapshot = log.toString();
        }

        long headers = snapshot.lines()
                .filter("HEADER"::equals)
                .count();
        long records = snapshot.lines()
                .filter(s -> s.equals("T1") || s.equals("T2"))
                .count();

        System.out.println("headers=" + headers);
        System.out.println("records=" + records);
        System.out.println("headerFirst=" + snapshot.startsWith("HEADER\n"));
    }
}
```

Lưu thành SharedLockDemo.java và chạy:

```bash
javac SharedLockDemo.java
java SharedLockDemo
```

Kết quả ổn định:

```text
headers=1
records=2
headerFirst=true
```

Thứ tự T1/T2 trong chuỗi có thể thay đổi theo lịch CPU, nên chương trình không in hoặc khẳng định thứ tự ấy. Chỉ luồng vào vùng synchronized(log) đầu tiên thấy log rỗng; luồng sau thấy HEADER đã có. join() khiến main chờ cả hai kết thúc. Việc chụp snapshot trong cùng monitor là mẫu đọc nhất quán, đặc biệt hữu ích nếu ứng dụng sau này vẫn còn luồng ghi chạy.

Nếu bỏ synchronized(log) bao quanh điều kiện và các lần append(), chương trình có **khả năng** ghi trùng HEADER, nhưng không phải lần chạy nào cũng bộc lộ race. Kết quả đúng ở một vài lần chạy không chứng minh mã không có lỗi đồng thời.

## 4. Đối tượng khóa riêng cho lớp quản lý dữ liệu

Khi StringBuffer được quản lý trong một lớp, hoặc một bất biến trải qua cả nội dung chuỗi và dữ liệu khác, dùng một trường khóa riêng thường rõ quyền sở hữu hơn:

```java
// Lớp minh họa dùng trong một dự án Java; không có main() riêng.
final class Transcript {
    private final Object lock = new Object();
    private final StringBuffer buffer = new StringBuffer();
    private int recordCount;

    public void record(String text) {
        synchronized (lock) {
            if (buffer.length() == 0) {
                buffer.append("HEADER\n");
            }
            buffer.append(text).append('\n');
            recordCount++;
        }
    }

    public String snapshotWithCount() {
        synchronized (lock) {
            return "count=" + recordCount + "\n" + buffer.toString();
        }
    }
}
```

Cả buffer và recordCount cùng nằm trong quy tắc cập nhật. Chọn private final Object lock giúp danh tính khóa không đổi và ngăn mã bên ngoài tự ý giữ monitor này. Không trả về tham chiếu buffer để người khác sửa mà không lấy lock.

Phải hiểu sự khác nhau: synchronized(lock) dùng monitor của lock, còn các phương thức synchronized trên StringBuffer dùng monitor của buffer. Các phương thức của StringBuffer **không tự đồng bộ trên khóa riêng**. Thiết kế trên bảo vệ thao tác ghép vì **toàn bộ đường đọc/ghi do lớp sở hữu** đều thống nhất lấy lock. Nếu mã bên ngoài có tham chiếu buffer và trực tiếp append() vào đó, nó có thể chen vào lúc một luồng giữ lock; bất biến cấp lớp không còn được bảo đảm.

Khi toàn bộ dữ liệu chỉ được truy cập qua một khóa riêng, có thể cân nhắc StringBuilder thay StringBuffer để tránh đồng bộ lặp lại ở cấp phương thức. Điều kiện bắt buộc là không còn bất kỳ truy cập StringBuilder nào ngoài giao ước khóa, và việc chọn StringBuilder không làm thay đổi yêu cầu bài học về StringBuffer.

## 5. Cách xác định vùng tới hạn đúng

Trước khi dùng synchronized, hãy xác định rõ:

1. **Bất biến:** điều gì luôn phải đúng? Ví dụ HEADER đúng một lần; tiền tố, nội dung và hậu tố của mỗi bản ghi liền nhau; recordCount bằng số bản ghi đã thêm.
2. **Các bước tạo thành một đơn vị:** kiểm tra trạng thái → quyết định → cập nhật một hay nhiều trường → hoàn tất bản ghi.
3. **Các luồng và lối truy cập:** những phương thức nào có thể quan sát hoặc thay đổi trạng thái ấy, có dùng cùng một khóa không?

Đọc cũng có thể cần chung khóa. Một lần buffer.toString() lấy được chuỗi tại một thời điểm, nhưng nếu sau đó đọc recordCount ở một thời điểm khác, không bảo đảm số đếm khớp ảnh chụp. Nếu cần trạng thái tổng hợp nhất quán, hãy đọc cả nội dung và bộ đếm dưới cùng monitor mà luồng ghi dùng.

Việc nhả một monitor và luồng khác sau đó lấy **cùng monitor** thiết lập quan hệ happens-before theo Java Memory Model: các thay đổi trước khi nhả được công bố để luồng nhận khóa nhìn thấy. Đặt tham chiếu buffer thành volatile chỉ hỗ trợ tính hiển thị tham chiếu, **không làm cho length() rồi append() trở thành nguyên tử**.

Nếu bất biến trải qua **hai StringBuffer**, có thể dùng một khóa riêng chung:

```java
// Giả định mọi truy cập liên quan đến ready/processed đều lấy lock.
synchronized (lock) {
    processed.append(ready);
    ready.setLength(0);
}
```

Một luồng không được chỉ khóa ready rồi nghĩ rằng đã bảo vệ cả processed. Nếu buộc lấy hai monitor lồng nhau, mọi đường đi phải lấy khóa theo một thứ tự nhất quán; T1 giữ khóa A rồi chờ B trong khi T2 giữ B rồi chờ A có thể gây deadlock. Một khóa chung thường dễ kiểm chứng hơn cho bất biến nhỏ liên quan nhiều trường, dù nó cũng có thể tạo nhiều tranh chấp hơn.

## 6. Những cách chọn khóa sai

**Khóa mới mỗi lần gọi:** synchronized(new Object()) dùng các monitor khác nhau giữa các lần gọi và các luồng, nên không phối hợp được.

```java
// Sai cho bài toán nhiều luồng cùng sửa buffer.
synchronized (new Object()) {
    if (buffer.length() == 0) {
        buffer.append("HEADER\n");
    }
}
```

**Khóa ảnh chụp chuỗi:** synchronized(buffer.toString()) khóa một đối tượng String, không khóa monitor của buffer. Những lần toString() có thể tạo đối tượng khác, nên không có giao ước khóa chung.

**Khóa this trên các wrapper khác nhau:** hai instance wrapper có hai monitor this khác nhau; nếu chúng cùng sửa một buffer chia sẻ, synchronized(this) ở mỗi wrapper không bảo vệ chung. Nó chỉ thích hợp khi tất cả luồng thực sự dùng cùng một instance quản lý trạng thái.

**Khóa chuỗi literal:** synchronized("LOG_LOCK") có thể vô tình dùng chung monitor với mã khác bởi cơ chế intern của String, gây chờ đợi hoặc deadlock không mong muốn. Khóa riêng private final thường dễ kiểm soát.

**Thay đối tượng làm khóa:** gán lại biến buffer hoặc lock giữa chừng khiến luồng này khóa instance cũ, luồng kia khóa instance mới. Danh tính khóa dùng để phối hợp phải ổn định và nhất quán.

**Khóa quá hẹp:** chỉ synchronized quanh length(), hoặc quanh từng append() riêng lẻ, không bảo vệ khoảng giữa kiểm tra và cập nhật. Một chuỗi gọi append("["); append(value); append("]") vẫn có thể bị xen kẽ.

**Khóa quá rộng:** giữ monitor trong lúc đợi mạng, thực hiện I/O chậm, sleep hoặc tính toán dài không đụng trạng thái chung làm tăng chờ đợi. Chuẩn bị dữ liệu độc lập trước, rồi giữ vùng tới hạn đủ ngắn nhưng bao trọn các bước duy trì bất biến.

**Dùng hai quy ước khóa cùng lúc:** T1 synchronized(buffer), T2 synchronized(lock) không đủ điều phối thao tác ghép dù các phương thức StringBuffer vẫn an toàn riêng lẻ. Mọi bên có thể ảnh hưởng bất biến phải cùng tuân theo giao ước.

## 7. Khi nào thực sự cần khóa ngoài?

- **Một lời gọi độc lập** như append(wholeRecord), và không có bất biến liên quan nhiều lời gọi hay trường khác: bảo vệ nội bộ của StringBuffer thường đủ cho lời gọi ấy.
- **Nhiều lời gọi cần liền mạch** như check-then-append, ghép tiền tố/nội dung/hậu tố qua nhiều append(), hoặc đọc-sửa-ghi dựa trên nội dung hiện tại: cần khóa chung bao quanh cả chuỗi.
- **Nhiều trường có quan hệ** như buffer với recordCount, hoặc hai buffer phải chuyển dữ liệu cùng nhau: bảo vệ cả dữ liệu liên quan và cả thao tác đọc snapshot tổng hợp.
- **Không có chia sẻ giữa các luồng:** không cần áp đặt khóa bổ sung để bảo vệ dữ liệu chỉ một luồng sở hữu; StringBuilder có thể phù hợp hơn trong phạm vi cục bộ.

Đừng khóa chỉ vì thấy kiểu StringBuffer, và cũng đừng bỏ khóa chỉ vì từng phương thức đã synchronized. Ranh giới nguyên tử phải do **bất biến của ứng dụng** quyết định.

## 8. Kiểm tra và review

Với ứng dụng có nhiều luồng, hãy kiểm tra các thuộc tính ổn định: HEADER đúng một lần; số bản ghi bằng số yêu cầu; mỗi bản ghi có đủ dấu mở/đóng; các bộ đếm khớp với dữ liệu. Lặp kiểm thử và tăng mức cạnh tranh giúp phát hiện lỗi nhưng không thay thế lập luận về khóa. Race có thể không xuất hiện trong hàng nghìn lần chạy.

Trong review, đánh dấu toàn bộ đường vào/ra vùng tới hạn, xác minh tất cả dùng **cùng một instance khóa**, khóa không bị thay tham chiếu, và không có đường ghi nào đi vòng ngoài. Khi nhiều monitor được lấy lồng nhau, kiểm tra thứ tự khóa để tránh deadlock. Khi thấy vùng khóa chứa thao tác chậm, xem có thể chuyển phần độc lập ra ngoài mà vẫn giữ nguyên bất biến hay không.

## Ghi nhớ

**StringBuffer đồng bộ từng phương thức; khóa chung đồng bộ cả một quy trình nhiều phương thức.** Dùng synchronized(buffer) khi nhiều luồng chia sẻ đúng một StringBuffer và cần bảo vệ toàn bộ thao tác ghép. Dùng private final Object lock khi một lớp quản lý nhiều trạng thái liên quan và kiểm soát mọi đường truy cập. Điều kiện cốt lõi là các luồng phải phối hợp trên **chính cùng một monitor**, và khối khóa phải bao trọn việc kiểm tra, quyết định cùng cập nhật cần được nhìn như một đơn vị.

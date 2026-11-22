# offer, poll có thời hạn và kiểm soát thời gian chờ

## 1. Mô hình: chờ một điều kiện, nhưng có giới hạn

`BlockingDeque<E>` là hàng đợi hai đầu hỗ trợ phối hợp giữa các luồng. Luồng sản xuất thêm công việc; luồng tiêu thụ lấy công việc ra. Khi hàng đợi đầy, bên thêm cần chờ chỗ trống; khi hàng đợi rỗng, bên lấy cần chờ phần tử.

Trong một dịch vụ, chờ vô hạn thường không phù hợp với thời hạn của yêu cầu. Ví dụ, yêu cầu chỉ còn 200 ms để được tiếp nhận vào hàng đợi. Nếu hàng đợi vẫn đầy khi hết ngân sách, chương trình cần biết để từ chối hoặc chuyển hướng công việc.

Các biến thể có thời hạn của `offer` và `poll` giải quyết đúng việc này: **thử thực hiện thao tác; chỉ chờ điều kiện cần thiết trong khoảng thời gian được cấp**. Chúng không bắt buộc ngủ đủ thời gian và không giới hạn thời gian xử lý công việc sau khi lấy ra.

Các API dưới đây có từ Java 6 và vẫn áp dụng trong Java hiện đại. Ví dụ dùng Java 17+, không cần thư viện ngoài. Quan hệ giữa các phương thức được quy định trong [tài liệu BlockingDeque của Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html).

## 2. Chọn đúng đầu và đọc đúng kết quả

| Thao tác có thời hạn | Điều kiện có thể phải chờ | Khi thành công | Khi hết thời gian mà chưa thực hiện được |
| --- | --- | --- | --- |
| `offerFirst(e, timeout, unit)` | Có chỗ trống | Thêm ở đầu, trả `true` | Trả `false` |
| `offerLast(e, timeout, unit)` | Có chỗ trống | Thêm ở cuối, trả `true` | Trả `false` |
| `pollFirst(timeout, unit)` | Có phần tử | Lấy và xóa phần tử đầu | Trả `null` |
| `pollLast(timeout, unit)` | Có phần tử | Lấy và xóa phần tử cuối | Trả `null` |

Hai tên ngắn tuân theo hướng FIFO:

- `offer(e, timeout, unit)` tương đương `offerLast(e, timeout, unit)`.
- `poll(timeout, unit)` tương đương `pollFirst(timeout, unit)`.

Chẳng hạn, `offerLast` kết hợp với `pollFirst` tạo luồng vào cuối, ra đầu. Đổi sang `pollLast` sẽ lấy công việc mới nhất trước; đó là thay đổi thứ tự xử lý, không phải một cách tăng thời gian chờ.

So sánh ba nhóm thường gặp:

| Ý định | Thêm | Lấy |
| --- | --- | --- |
| Không chờ điều kiện đầy/rỗng thay đổi | `offer(e)` | `poll()` |
| Chờ điều kiện, không đặt thời hạn | `put(e)` | `take()` |
| Chờ điều kiện trong thời gian cho phép | `offer(e, timeout, unit)` | `poll(timeout, unit)` |

`BlockingDeque` không nhận phần tử `null`, nên `null` từ `poll` có thể dùng để nhận biết không lấy được phần tử. Đừng giải tham chiếu kết quả trước khi kiểm tra. Các phương thức có thời hạn còn có thể ném `InterruptedException`; đây là một nhánh khác với `false` hoặc `null`. Xem [hợp đồng các phương thức BlockingDeque trong Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingDeque.html).

## 3. Thời hạn áp dụng như thế nào?

### Có điều kiện thì tiếp tục ngay

Nếu hàng đợi đang có chỗ, `offerLast(x, 5, SECONDS)` có thể thêm ngay. Nếu đã có phần tử, `pollFirst(5, SECONDS)` có thể lấy ngay. Con số 5 giây là ngân sách chờ, không phải độ trễ phải thực hiện.

Nếu đang phải chờ, thay đổi từ một luồng khác có thể giúp thao tác hoàn thành sớm. Luồng sản xuất lấy được chỗ trống sau khi bên tiêu thụ lấy phần tử; luồng tiêu thụ lấy được dữ liệu sau khi bên sản xuất thêm phần tử. Không cần tự viết vòng lặp `isEmpty()` rồi `sleep()`.

### Đơn vị phải thể hiện rõ ý định

`offerLast(job, 100, TimeUnit.MILLISECONDS)` và `offerLast(job, 100, TimeUnit.SECONDS)` có cùng giá trị số nhưng khác nhau 1.000 lần về thời lượng. Nên đặt tên như `enqueueTimeoutMillis` hoặc chuyển về một đơn vị nội bộ thống nhất.

Khi đổi từ đơn vị nhỏ sang đơn vị lớn, phần lẻ có thể bị cắt: `TimeUnit.NANOSECONDS.toMillis(500_000)` bằng `0`. Vì thế, khi truyền ngân sách còn lại giữa các thao tác, giữ đơn vị nanosecond thường tránh làm mất phần thời gian nhỏ còn lại. Đơn vị nanosecond không có nghĩa hệ điều hành bảo đảm đánh thức chính xác đến một nanosecond. [TimeUnit quy định cách biểu diễn và chuyển đổi thời lượng](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/TimeUnit.html).

### Thời hạn không phải bảo đảm thời gian thực

Không viết kiểm thử yêu cầu `poll(100, MILLISECONDS)` phải trở về đúng 100 ms hoặc tuyệt đối không quá 100 ms. Luồng cần được hệ điều hành lập lịch lại; tranh chấp đồng bộ và hoạt động của JVM cũng ảnh hưởng thời điểm mã gọi chạy tiếp.

Hãy coi thời hạn là cách kiểm soát việc chờ điều kiện, rồi đo thời gian thực tế để theo dõi vận hành. Nó không tự tạo một cam kết cứng cho toàn bộ yêu cầu.

### Trường hợp thời gian bằng hoặc nhỏ hơn 0

Với `LinkedBlockingDeque`, thời gian bằng hoặc nhỏ hơn 0 không cấp thêm thời gian chờ cho điều kiện đầy/rỗng thay đổi. Thao tác vẫn có thể thành công nếu điều kiện đã thỏa mãn. Ví dụ, `pollFirst(0, MILLISECONDS)` trên deque đang có phần tử vẫn lấy được phần tử.

Đây không phải lý do dùng số âm để biểu diễn “chờ vô hạn”. Nếu ứng dụng không chấp nhận cấu hình âm, hãy kiểm tra cấu hình từ đầu. Khi chỉ muốn thử ngay, các biến thể không có thời hạn thường thể hiện ý định rõ hơn.

## 4. Ví dụ chạy đầy đủ: thành công, hết hạn và ngắt luồng

Dùng deque có sức chứa 1 để tạo chắc chắn cả trạng thái đầy lẫn trạng thái rỗng. Không có luồng phụ thay đổi deque trong ví dụ này, nên kết quả giá trị là xác định; thời gian chạy thực tế không được đưa vào stdout.

Lưu thành `TimedDequeDemo.java`:

```java
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.TimeUnit;

public class TimedDequeDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingDeque<String> deque = new LinkedBlockingDeque<>(1);

        System.out.println("offer A: "
                + deque.offerLast("A", 100, TimeUnit.MILLISECONDS));

        // Deque dang day; khong co luong nao lay A ra.
        System.out.println("offer B: "
                + deque.offerLast("B", 20, TimeUnit.MILLISECONDS));

        System.out.println("poll: "
                + deque.pollFirst(100, TimeUnit.MILLISECONDS));

        // Deque dang rong; khong co luong nao them phan tu.
        System.out.println("empty poll: "
                + deque.pollFirst(20, TimeUnit.MILLISECONDS));

        deque.addLast("C");
        System.out.println("zero-time poll: "
                + deque.pollFirst(0, TimeUnit.MILLISECONDS));

        // Minh hoa nhanh huy: dat co ngat truoc loi goi co the bi ngat.
        Thread.currentThread().interrupt();
        try {
            deque.pollFirst(1, TimeUnit.SECONDS);
            throw new AssertionError("Expected InterruptedException");
        } catch (InterruptedException e) {
            System.out.println("interrupted");
            System.out.println("flag in catch: "
                    + Thread.currentThread().isInterrupted());
            Thread.currentThread().interrupt();
            System.out.println("flag restored: "
                    + Thread.currentThread().isInterrupted());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 TimedDequeDemo.java
java TimedDequeDemo
```

Stdout:

```text
offer A: true
offer B: false
poll: A
empty poll: null
zero-time poll: C
interrupted
flag in catch: false
flag restored: true
```

Diễn giải:

1. A được thêm ngay vì còn chỗ.
2. B không được thêm vì deque vẫn đầy sau thời gian chờ. A vẫn nằm trong deque; `false` không tự làm mất A hay lưu B ở nơi khác.
3. `pollFirst` lấy A ra.
4. Lần lấy tiếp theo hết thời gian trên deque rỗng nên trả `null`.
5. C được lấy dù thời gian bằng 0, vì C đã tồn tại.
6. Lời gọi cuối bị ngắt. Khi `InterruptedException` được ném trong tình huống này, cờ ngắt đã được xóa. Ví dụ khôi phục cờ trước khi kết thúc.

Không dùng `Thread.interrupted()` để chỉ quan sát cờ ngắt: phương thức đó còn xóa cờ. Trong ví dụ, `isInterrupted()` chỉ đọc trạng thái.

## 5. Xử lý hết hạn khác với xử lý hủy

Từ góc nhìn ứng dụng, có ba kết quả:

| Kết quả | Ý nghĩa | Quyết định ứng dụng có thể thực hiện |
| --- | --- | --- |
| `true` hoặc phần tử khác `null` | Thao tác đã thành công | Tiếp tục bước tiếp theo |
| `false` hoặc `null` | Chưa thực hiện được trong thời gian cho phép | Từ chối, báo hết thời gian, hoặc thử lại theo chính sách |
| `InterruptedException` | Luồng nhận tín hiệu ngắt | Dừng công việc hoặc truyền tín hiệu hủy lên tầng gọi |

Nếu phương thức của bạn cho phép khai báo `throws InterruptedException`, thường nên truyền ngoại lệ lên để tầng sở hữu vòng đời công việc quyết định. Nếu bắt ngoại lệ ở điểm kết thúc luồng, khôi phục cờ bằng `Thread.currentThread().interrupt()` rồi thoát là mẫu thường dùng.

Không bắt ngắt rồi tiếp tục thử vô hạn. Điều đó có thể khiến dịch vụ không dừng được khi đang tắt. Cũng không đổi mọi trường hợp ngắt thành “hàng đợi hết thời gian”: cách đó làm mất nguyên nhân hủy.

Một lần `offer` trả `true` chỉ chứng minh công việc đã được tiếp nhận vào deque. Nó không chứng minh đã có luồng xử lý, xử lý thành công hay hoàn thành trước thời hạn nghiệp vụ. Nếu cần theo dõi kết quả, phải có cơ chế phản hồi riêng.

Ngược lại, một lần `poll` trả `null` không chứng minh mọi bên sản xuất đã kết thúc. Dữ liệu có thể đến ngay sau đó. Việc kết thúc luồng tiêu thụ cần dựa trên giao thức dừng của ứng dụng, không chỉ một lần hàng đợi rỗng.

## 6. Một ngân sách chung cho nhiều thao tác

Giả sử một bước cần lấy hai công việc và chỉ được chờ tổng cộng khoảng 200 ms. Nếu gọi hai lần `pollFirst(200, MILLISECONDS)`, mỗi lần được cấp lại 200 ms; thời gian chờ cộng dồn có thể tiến tới 400 ms.

Cách phù hợp là ghi nhận thời điểm bắt đầu, đo thời gian đã trôi qua trước mỗi lần chờ, rồi chỉ truyền phần ngân sách còn lại. Dùng `System.nanoTime()` cho thời gian trôi qua. Không dùng `currentTimeMillis()` cho phép đo này vì đồng hồ lịch có thể được điều chỉnh. Nguồn thời gian của `nanoTime()` không phải thời gian lịch; chỉ hiệu giữa các lần đo trong cùng JVM có ý nghĩa ở đây. Xem [System.nanoTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()).

Lưu thành `BudgetedPollDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.TimeUnit;

public class BudgetedPollDemo {
    static <E> List<E> pollUpTo(
            BlockingDeque<E> deque,
            int maxItems,
            long timeout,
            TimeUnit unit) throws InterruptedException {

        Objects.requireNonNull(deque, "deque");
        Objects.requireNonNull(unit, "unit");
        if (maxItems < 0 || timeout < 0) {
            throw new IllegalArgumentException("Negative argument");
        }

        long budgetNanos = unit.toNanos(timeout);
        long started = System.nanoTime();
        List<E> result = new ArrayList<>();

        while (result.size() < maxItems) {
            if (Thread.currentThread().isInterrupted()) {
                throw new InterruptedException("Polling cancelled");
            }

            long elapsed = System.nanoTime() - started;
            long remaining = budgetNanos - elapsed;
            if (remaining <= 0) {
                break;
            }

            E item = deque.pollFirst(remaining, TimeUnit.NANOSECONDS);
            if (item == null) {
                break;
            }
            result.add(item);
        }

        return result;
    }

    public static void main(String[] args) throws InterruptedException {
        BlockingDeque<String> deque = new LinkedBlockingDeque<>(2);
        deque.addLast("A");

        List<String> items =
                pollUpTo(deque, 2, 30, TimeUnit.MILLISECONDS);

        // Chi A ton tai; ket qua co the rong neu luong bi tre qua ngan sach.
        boolean valid = items.isEmpty() || items.equals(List.of("A"));
        System.out.println("valid partial result: " + valid);
        System.out.println("at most two: " + (items.size() <= 2));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 BudgetedPollDemo.java
java BudgetedPollDemo
```

Stdout:

```text
valid partial result: true
at most two: true
```

Trong điều kiện chạy thông thường, phương thức lấy A rồi dùng phần thời gian còn lại để chờ phần tử thứ hai. Nếu JVM hoặc hệ điều hành trì hoãn luồng quá ngân sách trước lần lấy đầu, kết quả rỗng cũng hợp lệ. Vì vậy ví dụ xác minh thuộc tính đúng, không khẳng định thời gian đo được hay số phần tử luôn cố định.

Những quyết định cần hiểu trong mã:

- `timeout == 0` trả danh sách rỗng vì hợp đồng của phương thức tự viết này chỉ bắt đầu thao tác khi còn ngân sách. Đây là lựa chọn của `pollUpTo`, khác với việc gọi trực tiếp `pollFirst(0, unit)`.
- Dùng phép trừ `nanoTime() - started` để đo khoảng thời gian. Ngân sách nghiệp vụ nên hữu hạn, thực tế và rất nhỏ so với phạm vi biểu diễn khoảng thời gian của `long`.
- Kết quả là một phần hoặc toàn bộ số phần tử yêu cầu. Hai lần lấy không phải một giao dịch nguyên tử; lấy được A rồi hết hạn thì A đã rời deque.
- Nếu bị ngắt sau khi đã lấy một số phần tử, phương thức ném ngoại lệ và không hoàn tác những lần lấy trước. Với nghiệp vụ thật, cần quyết định quyền sở hữu và cách khôi phục phần công việc đã lấy; không mặc định đẩy lại mà bỏ qua nguy cơ thay đổi thứ tự hoặc xử lý trùng.
- Tín hiệu ngắt được kiểm tra giữa các vòng lặp, nhưng đây vẫn là phối hợp hủy, không phải bảo đảm ngăn mọi thao tác ngay tại thời điểm ngắt.

Cùng nguyên tắc ngân sách còn lại áp dụng cho nhiều lần `offerLast`. Tuy nhiên, “thêm được một phần rồi hết hạn” cũng cần chính sách nghiệp vụ rõ ràng; các lần thêm thành công không tự được thu hồi.

## 7. Áp dụng vào luồng sản xuất và tiêu thụ

### Đặt sức chứa có chủ đích

Với `new LinkedBlockingDeque<>(capacity)`, có thể giới hạn số công việc đang chờ. Nếu bên sản xuất nhanh hơn bên tiêu thụ, `offerLast` có thời hạn cho bên sản xuất một cơ hội chờ trước khi báo không tiếp nhận được.

Nếu không truyền sức chứa, `LinkedBlockingDeque` dùng giới hạn mặc định `Integer.MAX_VALUE`. Khi đó, thời hạn của `offer` thường không giúp kiểm soát tải như mong muốn: bộ nhớ có thể trở thành vấn đề trước khi chạm giới hạn phần tử. Sức chứa tính theo số phần tử, không theo số byte của đối tượng. Xem [LinkedBlockingDeque và các hàm khởi tạo](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html).

### Quyết định rõ khi không tiếp nhận được

Khi `offerLast` trả `false`, chọn chính sách dựa trên loại công việc: báo bận cho phía gọi, ghi nhận từ chối, hoặc chuyển sang cơ chế lưu bền đã được thiết kế. Không âm thầm bỏ công việc chỉ vì bỏ qua giá trị trả về.

Nếu thử lại, phải giới hạn số lần hoặc dùng ngân sách chung. Vòng lặp thử lại vô hạn với thời hạn 100 ms ở mỗi vòng vẫn có thể chờ vô hạn xét trên toàn bộ yêu cầu.

### Không kiểm tra trước rồi mới thao tác

Mẫu `if (deque.remainingCapacity() > 0) deque.addLast(job);` có khoảng trống cạnh tranh giữa kiểm tra và thêm: một luồng khác có thể chiếm chỗ. Tương tự, `!deque.isEmpty()` không bảo đảm lần lấy tiếp theo có dữ liệu.

Hãy để một lời gọi `offerLast` hoặc `pollFirst` thực hiện việc kiểm tra điều kiện và thay đổi deque, rồi xử lý trực tiếp kết quả của lời gọi đó.

## 8. Lỗi thường gặp và bài tự kiểm tra

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Bỏ qua `false` từ `offer` | Công việc không vào deque nhưng phía gọi tưởng đã nhận | Xử lý nhánh từ chối |
| Gọi phương thức trên kết quả `poll` chưa kiểm tra | Có thể gặp `NullPointerException` khi hết hạn | Kiểm tra `null` trước |
| Coi thời hạn là thời gian bắt buộc ngủ | Hiểu sai lần gọi hoàn thành sớm | Nhớ thao tác có thể thành công ngay |
| Cấp lại nguyên ngân sách trong vòng lặp | Vượt thời hạn tổng của yêu cầu | Đo thời gian trôi qua và truyền phần còn lại |
| Nuốt `InterruptedException` | Khó dừng luồng, mất tín hiệu hủy | Truyền ngoại lệ hoặc khôi phục cờ rồi thoát |
| Dùng `poll` hết hạn làm tín hiệu “không còn dữ liệu mãi mãi” | Luồng tiêu thụ kết thúc quá sớm | Có giao thức dừng riêng |
| Đặt thời hạn cho lấy rồi cho rằng xử lý cũng bị giới hạn | Công việc sau đó vẫn có thể chạy lâu | Quản lý thời hạn xử lý ở tầng sở hữu công việc |

Tự kiểm tra:

1. Deque sức chứa 1 đang chứa A. Không có luồng khác can thiệp. `offerLast("B", 10, MILLISECONDS)` trả gì và deque còn gì? **Trả `false`; A vẫn còn.**
2. Deque đang có A. `pollFirst(1, SECONDS)` có bắt buộc chờ một giây không? **Không; có thể lấy A ngay.**
3. Hai lần lấy đều được cấp 300 ms có bảo đảm tổng thời gian chờ không vượt 300 ms không? **Không; cần chia sẻ phần ngân sách còn lại.**
4. `offerLast` trả `true` có nghĩa công việc đã xử lý thành công không? **Không; mới chỉ xác nhận đã thêm vào deque.**
5. Vì sao phải phân biệt `null` với `InterruptedException`? **Một bên biểu thị không lấy được trong thời gian cho phép; bên kia là tín hiệu ngắt cần xử lý theo vòng đời công việc.**

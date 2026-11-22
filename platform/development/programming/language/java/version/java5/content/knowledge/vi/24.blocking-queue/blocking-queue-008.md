# `DelayQueue`, `Delayed` và thời điểm phần tử được lấy

## 1. Mô hình: đã nằm trong hàng nhưng chưa đến lượt được lấy

Một hàng đợi thông thường trả lời câu hỏi “có phần tử nào không?”. `DelayQueue<E extends Delayed>` còn đặt thêm điều kiện: “phần tử ở đầu đã đến hạn chưa?”. Một phần tử có thể đang nằm trong hàng, được tính vào kích thước, nhưng chưa thể được lấy bằng `take()` hoặc `poll()`.

Ví dụ, sau một lần gọi dịch vụ thất bại, chương trình muốn thử lại sau một khoảng chờ. Thay vì liên tục lấy công việc ra rồi tự kiểm tra thời gian, có thể gắn mốc được phép thử lại vào công việc và đưa nó vào `DelayQueue`. Luồng xử lý gọi `take()` để nhận công việc khi đủ điều kiện.

Cần phân biệt ba sự kiện:

```text
đưa phần tử vào hàng
        ↓
đến hạn: phần tử đủ điều kiện được lấy
        ↓
luồng xử lý lấy phần tử và thực hiện công việc
```

Đến hạn không có nghĩa công việc tự chạy, cũng không có nghĩa phần tử tự biến mất. `DelayQueue` là cấu trúc lưu và phối hợp lấy dữ liệu theo thời gian; nó không tự tạo luồng để thực thi hành động.

Các quy tắc về phần tử đầu hàng, phần tử hết thời gian chờ và phương thức lấy được mô tả trong [Java SE `DelayQueue`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/DelayQueue.html).

## 2. `Delayed`: mỗi phần tử cung cấp thời gian còn lại và thứ tự

`Delayed` kế thừa `Comparable<Delayed>`. Lớp phần tử phải thực hiện hai phương thức:

```java
long getDelay(TimeUnit unit);
int compareTo(Delayed other);
```

Vai trò của chúng khác nhau:

- `getDelay(unit)` trả thời gian còn lại theo đơn vị bên gọi yêu cầu. Giá trị dương nghĩa là còn phải đợi; bằng 0 hoặc âm nghĩa là đã đến hạn.
- `compareTo(other)` xác định thứ tự giữa các phần tử. Phần tử có mốc đến hạn sớm hơn phải đứng trước phần tử có mốc đến hạn muộn hơn.

Hai phương thức phải nhất quán về thứ tự thời gian. Đây là yêu cầu của [giao diện `Delayed`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Delayed.html). Không dùng `compareTo` để xếp theo tên hoặc độ ưu tiên nghiệp vụ trong khi `getDelay` lại dựa trên một mốc thời gian khác: một phần tử chưa đến hạn có thể che khuất phần tử đã đến hạn ở phía sau nếu thứ tự bị định nghĩa sai.

Cách biểu diễn thường dùng cho khoảng chờ trong cùng tiến trình:

```text
deadlineNanos = mốc thời gian ban đầu + khoảng chờ
remainingNanos = deadlineNanos - System.nanoTime()
```

Mốc đến hạn được lưu một lần. Thời gian còn lại được tính lại mỗi khi `getDelay` được gọi, nhờ vậy nó giảm dần theo thời gian.

Nếu mỗi lần gọi `getDelay` lại tạo một mốc “bây giờ cộng thêm 5 giây”, thời gian còn lại sẽ liên tục bị kéo dài và phần tử có thể không bao giờ đến hạn.

## 3. Vì sao dùng `System.nanoTime()` cho khoảng chờ?

`System.currentTimeMillis()` mô tả thời gian đồng hồ gắn với lịch và có thể chịu điều chỉnh đồng hồ hệ thống. Đối với yêu cầu “đợi thêm một khoảng”, `System.nanoTime()` phù hợp để tính chênh lệch thời gian trong cùng JVM.

Theo [tài liệu `System.nanoTime()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()), giá trị này có gốc tùy ý, không phải thời điểm lịch để chuyển trực tiếp thành ngày giờ. Tên đơn vị nanosecond cũng không bảo đảm đồng hồ có độ phân giải thực tế đúng một nanosecond.

Vì vậy:

- Dùng hiệu hai giá trị từ cùng nguồn `nanoTime()` để đo khoảng thời gian.
- Không ghi giá trị `nanoTime()` xuống cơ sở dữ liệu rồi dùng làm thời điểm đến hạn sau khi khởi động lại tiến trình.
- Không so sánh trực tiếp mốc `nanoTime()` của hai máy để đồng bộ lịch.
- Với công việc phải tồn tại qua lần khởi động lại, cần lưu mốc lịch hoặc dữ liệu lập lịch thích hợp và tính lại khoảng chờ khi nạp; `DelayQueue` chỉ là phần bộ nhớ cục bộ của giải pháp.

Phép toán mốc thời gian bằng `long` cần giới hạn khoảng cách giữa các mốc đủ nhỏ để tránh nhầm thứ tự khi tràn số. Ví dụ bên dưới chỉ dùng các mốc quanh cùng một thời điểm và khoảng chờ ngắn; không phải bộ lập lịch cho các mốc cách nhau hàng thế kỷ.

## 4. Những phương thức dễ gây hiểu nhầm

Giả sử hàng chỉ chứa một phần tử còn phải đợi và chưa có phần tử nào đến hạn:

| Phương thức | Kết quả hoặc hành vi |
| --- | --- |
| `size()` | Vẫn tính phần tử chưa đến hạn |
| `isEmpty()` | `false` vì hàng vẫn có phần tử |
| `peek()` | Có thể trả phần tử đầu dù nó chưa đến hạn; không loại phần tử |
| `poll()` | Trả `null` vì chưa có phần tử đầu đã đến hạn để lấy |
| `take()` | Đợi đến khi có phần tử đủ điều kiện; có thể bị ngắt |
| `poll(timeout, unit)` | Chờ phần tử đủ điều kiện trong khoảng cho phép; hết thời gian mà chưa có thì trả `null` |
| `remove()` không đối số | Chỉ lấy phần tử đầu đã đến hạn; không có thì ném `NoSuchElementException` |
| `remove(object)` | Có thể gỡ phần tử được chỉ định dù nó chưa đến hạn |
| `clear()` | Gỡ cả phần tử đến hạn và chưa đến hạn |

Không dùng `isEmpty()` làm điều kiện khẳng định `take()` sẽ trả ngay. Với `DelayQueue`, “đang có dữ liệu” và “đang có dữ liệu được phép lấy” là hai trạng thái khác nhau.

`drainTo` chỉ chuyển các phần tử đang đủ điều kiện được lấy, không phải một cách rút hết mọi lịch hẹn tương lai. Nếu cần xóa toàn bộ, đó là yêu cầu khác với lấy các phần tử sẵn sàng.

Vòng lặp qua iterator cũng không thay thế các phương thức lấy: iterator nhìn thấy cả phần tử chưa đến hạn và không bảo đảm duyệt theo thứ tự đến hạn. Đừng dựa vào thứ tự in cả collection để kiểm chứng thứ tự lấy thực tế.

### Hai khoảng thời gian trong `poll(timeout, unit)`

Giả sử phần tử đầu còn 10 giây mới đến hạn, còn bên gọi chỉ muốn đợi 2 giây. `poll(2, SECONDS)` có thể trả `null` khi hết khoảng chờ của bên gọi; phần tử vẫn còn trong hàng và vẫn giữ mốc đến hạn cũ.

Thời hạn của `poll` không sửa thời gian chờ của phần tử. Nếu một phần tử sớm hơn được thêm trong lúc chờ, thứ tự đầu hàng có thể thay đổi và lời gọi có thể nhận phần tử đủ điều kiện đó. Các thao tác lấy hỗ trợ ngắt qua `InterruptedException`; không đồng nhất bị ngắt với hết thời gian chờ.

## 5. Ví dụ Java 17+ chạy được

Lưu thành `DelayQueueDemo.java`. Lớp `TimedJob` lưu mốc đến hạn bất biến. Hai phần tử dùng chung mốc gốc để thứ tự thời gian rõ ràng, kể cả khi có độ trễ giữa các câu lệnh khởi tạo.

```java
import java.util.Objects;
import java.util.concurrent.DelayQueue;
import java.util.concurrent.Delayed;
import java.util.concurrent.TimeUnit;

public class DelayQueueDemo {
    private static final class TimedJob implements Delayed {
        private final String name;
        private final long deadlineNanos;

        TimedJob(String name, long baseNanos, long delayMillis) {
            if (delayMillis < 0 || delayMillis > TimeUnit.DAYS.toMillis(30)) {
                throw new IllegalArgumentException("delay must be within 30 days");
            }
            this.name = Objects.requireNonNull(name);
            this.deadlineNanos = baseNanos
                    + TimeUnit.MILLISECONDS.toNanos(delayMillis);
        }

        @Override
        public long getDelay(TimeUnit unit) {
            long remaining = deadlineNanos - System.nanoTime();
            return unit.convert(remaining, TimeUnit.NANOSECONDS);
        }

        @Override
        public int compareTo(Delayed other) {
            if (this == other) {
                return 0;
            }
            TimedJob that = (TimedJob) other;
            long difference = this.deadlineNanos - that.deadlineNanos;
            return Long.compare(difference, 0L);
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        DelayQueue<TimedJob> queue = new DelayQueue<>();
        long base = System.nanoTime();
        TimedJob ready = new TimedJob("ready", base, 0);
        TimedJob later = new TimedJob("later", base, 150);

        // Cố ý thêm phần tử đến hạn muộn hơn trước.
        queue.offer(later);
        queue.offer(ready);
        System.out.println("size: " + queue.size());
        System.out.println("peek: " + queue.peek());
        System.out.println("poll: " + queue.poll());

        TimedJob taken = queue.take();
        System.out.println("take: " + taken);
        System.out.println("expired when taken: "
                + (taken.getDelay(TimeUnit.NANOSECONDS) <= 0));
        System.out.println("size after takes: " + queue.size());
        System.out.println("poll empty: " + queue.poll());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 DelayQueueDemo.java
java DelayQueueDemo
```

Stdout:

```text
size: 2
peek: ready
poll: ready
take: later
expired when taken: true
size after takes: 0
poll empty: null
```

Những điểm cần đọc từ ví dụ:

1. `ready` có mốc sớm hơn `later` dù được thêm sau. Hàng đợi ưu tiên mốc đến hạn, không phải thứ tự thêm.
2. `ready` có khoảng chờ bằng 0 nên đủ điều kiện ngay. `poll()` lấy nó ra.
3. `take()` chỉ lấy `later` sau khi mốc của nó đã đạt đến. Nếu luồng chính đã chạy chậm đến mức vượt mốc 150 ms trước khi gọi `take`, lời gọi này có thể trả ngay; nếu chưa, nó đợi phần thời gian còn lại.
4. Chương trình không in thời gian thực tế như một con số cố định. stdout không đòi hỏi JVM phải lập lịch đúng tại mốc 150 ms.
5. Cuối chương trình dùng `poll()` khi trống để nhận `null`; gọi thêm `take()` lúc đó có thể chờ vô hạn vì không còn bên thêm dữ liệu.

Giới hạn 30 ngày trong constructor là ràng buộc riêng của ví dụ, không phải giới hạn của API `DelayQueue`. Trong ví dụ, mọi phần tử có cùng kiểu `TimedJob`, dùng cùng mốc gốc. Phép ép kiểu trong `compareTo` phục vụ thiết kế đó; không trộn các lớp `Delayed` có quy tắc thời gian khác vào cùng hàng.

## 6. Vì sao cách tính và so sánh trong ví dụ quan trọng?

### Đổi đơn vị ở bước trả kết quả

`getDelay` tính phần còn lại bằng nanosecond rồi dùng `unit.convert`. Không trả giá trị millisecond cố định bất kể tham số `unit`. Nếu trả sai đơn vị, hàng đợi có thể đợi sai độ dài hoặc đánh giá sai thời điểm sẵn sàng.

Phép đổi từ nanosecond sang đơn vị lớn hơn có thể làm tròn về 0. Chẳng hạn còn chưa đủ một millisecond thì kết quả theo millisecond có thể bằng 0 dù kết quả theo nanosecond vẫn dương. `DelayQueue` xác định đã đến hạn dựa trên kết quả theo nanosecond; đừng tự dùng kết quả đã làm tròn để khẳng định phần tử đã đến hạn với độ chính xác cao hơn nó thể hiện.

### So sánh các mốc cố định

`compareTo` so sánh mốc đến hạn đã lưu, không gọi lần lượt `getDelay` trên hai đối tượng ở hai thời điểm khác nhau để tạo thứ tự dao động. Mốc sớm hơn phải luôn đứng trước mốc muộn hơn trong phạm vi thiết kế.

Không viết:

```java
return (int) (this.deadlineNanos - that.deadlineNanos);
```

Đoạn trên chỉ minh họa lỗi, không phải một phương thức hoàn chỉnh. Ép hiệu `long` xuống `int` làm mất phần cao và có thể đảo dấu. Ví dụ dùng `Long.compare(difference, 0L)` để giữ dấu của hiệu trong phạm vi chênh lệch được thiết kế.

Phép lấy hiệu cũng đòi hỏi các mốc không cách nhau quá nửa dải số `long` tính theo nanosecond, cỡ 292 năm. Với cùng mốc gốc và khoảng chờ tối đa 30 ngày trong chương trình, điều kiện này được đáp ứng. Không mở rộng ví dụ thành lịch hẹn vô hạn mà bỏ qua giả định ấy.

### Mốc bằng nhau không mặc định giữ thứ tự thêm

Nếu hai phần tử có cùng mốc đến hạn, `compareTo` có thể trả 0. `DelayQueue` không hứa giữ thứ tự thêm giữa những phần tử đồng hạng. Nếu ứng dụng cần thứ tự xác định khi bằng mốc, có thể thêm số thứ tự làm tiêu chí phụ, nhưng vẫn phải để mốc đến hạn là tiêu chí chính.

## 7. Sửa lịch, hủy và xử lý đồng thời

Không sửa trực tiếp mốc đến hạn của một đối tượng đang nằm trong hàng. Hàng đợi không tự biết trường bên trong vừa thay đổi để sắp xếp lại đúng vị trí. Ngoài vấn đề thứ tự, việc sửa không đồng bộ còn có thể tạo lỗi giữa các luồng.

Một thiết kế dễ kiểm soát hơn là giữ đối tượng bất biến. Khi cần đổi lịch, gỡ đối tượng cũ và thêm một đối tượng mới mang mốc mới. Tuy nhiên, hai thao tác đó không tự tạo thành một giao dịch: luồng xử lý có thể đã lấy đối tượng cũ trước khi yêu cầu gỡ đến nơi.

Nếu cần hủy chắc chắn theo yêu cầu nghiệp vụ, nên có trạng thái hoặc phiên bản của công việc được kiểm tra trước khi thực hiện, cùng cơ chế đồng bộ phù hợp. `remove(object)` thành công chỉ chứng minh phần tử đó đã được gỡ khỏi hàng tại thao tác ấy; nó không thu hồi một công việc đã được luồng khác lấy và bắt đầu chạy.

Luồng chờ ở `take()` phải có cách dừng, thường là chính sách ngắt luồng ở lớp quản lý. Khi bắt `InterruptedException`, truyền ra lớp quyết định hoặc khôi phục cờ ngắt và kết thúc vòng lặp theo thiết kế. Một “phần tử báo dừng” mang thời gian chờ xa trong tương lai sẽ không được lấy ngay, nên không thể áp dụng máy móc cách báo dừng của hàng FIFO thường.

## 8. Không có giới hạn dung lượng và không có cam kết chạy đúng giờ

`DelayQueue` không đặt trần dung lượng. `remainingCapacity()` trả `Integer.MAX_VALUE`; `put` không chờ chỗ trống và thời hạn truyền cho `offer(e, timeout, unit)` không tạo một giới hạn dung lượng. Không nhầm thời hạn tiếp nhận của phương thức `offer` với khoảng trì hoãn được mã hóa trong chính phần tử.

Nếu tốc độ thêm lịch lớn hơn tốc độ lấy và xử lý, dữ liệu có thể tích lũy trong heap. Cần giới hạn tiếp nhận ở lớp ứng dụng khi phù hợp, đo số phần tử chờ và tránh giữ dữ liệu lớn không cần thiết trong từng phần tử.

Thời điểm đến hạn chỉ là thời điểm **sớm nhất phần tử đủ điều kiện được lấy**. Luồng có thể được lập lịch muộn, đang xử lý công việc khác hoặc phải chờ tài nguyên. Có nhiều luồng xử lý cũng không bảo đảm công việc đến hạn sớm hơn sẽ hoàn thành trước.

Nếu mục tiêu là “chạy một `Runnable` sau một khoảng chờ” và muốn có sẵn cơ chế thực thi, hủy và quản lý nhóm luồng, hãy phân biệt nhu cầu đó với việc tự dùng `DelayQueue` làm cấu trúc dữ liệu. Bài này tập trung vào điều kiện lấy phần tử, không coi `DelayQueue` là một bộ lập lịch bền vững hay có độ chính xác thời gian thực.

## 9. Tự kiểm tra bằng tình huống

Giả sử `A` được thêm trước, đến hạn sau 30 giây; `B` được thêm sau, đến hạn sau 10 giây; hai mốc đều tính từ cùng một thời điểm, chưa có luồng nào lấy dữ liệu.

1. Ở thời điểm sau 5 giây, `size()`, `peek()` và `poll()` có thể cho thấy gì?
2. Nếu gọi `poll(2, SECONDS)` tại thời điểm đó mà không có phần tử mới, nó có đổi mốc của `B` thành 7 giây không?
3. Khi cả hai đã đến hạn, phần tử nào được lấy trước?
4. Có thể dùng `remove(A)` trước mốc 30 giây để gỡ `A` không?
5. Vì sao không nên cập nhật trực tiếp mốc thời gian của `A` khi nó vẫn nằm trong hàng?

Gợi ý: (1) `size()` là 2; `peek()` trả `B`; `poll()` trả `null`. (2) Không, chỉ giới hạn khoảng chờ của bên gọi; mốc `B` vẫn là 10 giây. (3) `B` trước `A`, dựa trên mốc đến hạn. (4) Có thể, nếu `A` vẫn còn trong hàng và khớp đối tượng cần gỡ. (5) Cấu trúc sắp xếp không tự điều chỉnh vì trường bên trong bị sửa; nên giữ mốc bất biến và thiết kế đổi lịch có xét đến xử lý đồng thời.

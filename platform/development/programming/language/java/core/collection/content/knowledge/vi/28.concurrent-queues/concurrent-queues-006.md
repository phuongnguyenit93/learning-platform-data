# DelayQueue và hợp đồng Delayed

## 1. Hiểu đúng: có trong hàng đợi chưa có nghĩa là được lấy ra

Giả sử một yêu cầu gửi lại chỉ được thử sau một khoảng nghỉ. Ta muốn đặt yêu cầu vào nơi lưu trữ ngay, nhưng chỉ giao nó cho phía xử lý khi đã đến hạn. Nếu dùng hàng đợi thông thường, phần tử đứng đầu được lấy ra theo quy tắc của hàng đợi mà không có điều kiện thời gian này. Nếu tự kiểm tra rồi đưa phần tử chưa đến hạn trở lại, ta phải tự giải quyết việc chờ, đánh thức và sắp lại thứ tự khi có yêu cầu đến hạn sớm hơn.

`DelayQueue<E extends Delayed>` biểu diễn một hàng đợi có điều kiện thời gian. Mỗi phần tử tự mô tả khi nào nó đến hạn thông qua `Delayed`. Hàng đợi tìm ứng viên đến hạn sớm nhất, nhưng các thao tác lấy theo hạn chỉ giao ứng viên khi thời gian còn lại của nó đã hết.

Hãy tách ba việc:

1. **Lưu giữ:** phần tử đã được đưa vào hàng đợi.
2. **Đủ điều kiện lấy:** phần tử đã đến hạn.
3. **Thực hiện công việc:** mã của ứng dụng nhận phần tử rồi quyết định làm gì.

`DelayQueue` làm hai việc đầu. Nó không gọi một phương thức xử lý công việc thay cho ứng dụng. Đưa một đối tượng có phương thức `run()` vào hàng đợi cũng không tự làm phương thức ấy chạy.

Ví dụ, ta đưa lần lượt ba phần tử có hạn 30, 10 và 20 vào cùng một hàng đợi. Tại thời điểm 0, hàng đợi lưu ba phần tử, ứng viên đầu là phần tử có hạn 10, nhưng chưa phần tử nào được phép lấy bằng `poll()`. Tại thời điểm 20, phần tử có hạn 10 và 20 đều đã đủ điều kiện; phần tử có hạn 30 vẫn được lưu lại. Thứ tự đưa vào không quyết định thứ tự lấy.

Trong bài này, **đến hạn** là thời gian còn lại bằng 0 hoặc âm. “Hết thời gian trì hoãn” không đồng nghĩa với “dữ liệu vô hiệu cần xóa bỏ”. Ứng dụng có thể lấy phần tử đến hạn để thực hiện một công việc hoàn toàn hợp lệ, chẳng hạn thử lại một thao tác.

Điểm dễ gây nhầm nhất là hai câu sau có thể cùng đúng:

- `queue.isEmpty()` trả về `false`.
- `queue.poll()` trả về `null`.

Không có mâu thuẫn: hàng đợi có dữ liệu, nhưng chưa có dữ liệu đủ điều kiện giao qua thao tác này. Vì thế, không dùng `size() > 0` làm bằng chứng rằng một lần gọi `take()` tiếp theo sẽ trả về ngay.

**Mục tiêu học:** sau bài này, bạn cần giải thích được hai phương thức của `Delayed`, viết một phần tử có hạn ổn định, phân biệt quan sát với lấy theo hạn, và xử lý đúng việc chờ/ngắt/thử lại. Phần đầu giải thích hợp đồng; ba chương trình phía sau lần lượt kiểm chứng ngữ nghĩa, cơ chế chờ và một luồng thử lại có giới hạn.

## 2. Delayed nối dữ liệu của ứng dụng với quy tắc thời gian

### 2.1. Hai phương thức cùng nói về một hạn

`Delayed` kế thừa `Comparable<Delayed>`. Khi tạo loại phần tử dùng cho `DelayQueue`, ta phải cung cấp cả hai phần:

| Phương thức | Câu hỏi nó trả lời | Điều cần giữ nhất quán |
| --- | --- | --- |
| `getDelay(TimeUnit unit)` | Từ bây giờ đến hạn còn bao nhiêu, theo đơn vị được yêu cầu? | Giá trị giảm theo thời gian và bằng 0 hoặc âm khi đến hạn. |
| `compareTo(Delayed other)` | Phần tử nào có hạn sớm hơn? | Thứ tự phải phù hợp với thứ tự thời gian còn lại. |

Đây là hợp đồng được nêu trong [API Delayed của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Delayed.html). Chỉ viết một `getDelay()` trông hợp lý chưa đủ: nếu `compareTo()` xếp sai ứng viên đầu, hành vi của hàng đợi cũng sai.

Ta phân biệt:

- **Khoảng trì hoãn ban đầu:** ví dụ 5 giây kể từ lúc tạo.
- **Hạn:** mốc cố định thu được từ thời điểm tạo cộng khoảng trì hoãn.
- **Thời gian còn lại:** hạn trừ thời điểm hiện tại.

Với một phần tử thông thường trong bài, hạn là dữ liệu bất biến; thời gian còn lại được tính lại mỗi lần gọi. Thay đổi của đồng hồ làm thời gian còn lại giảm, không cần sửa trường hạn của phần tử.

Một cách viết sai là lưu `delay = 5` rồi luôn trả về đúng 5 giây. Khi hàng đợi kiểm tra lần sau, phần tử vẫn tuyên bố “còn 5 giây”; thời gian đã trôi qua không được phản ánh. Cách viết sai khác là trừ thời điểm hiện tại ngay trong quá trình tạo, lưu kết quả còn lại một lần, rồi trả lại số đã đóng băng đó mãi.

Quy tắc nên dùng là: **ghi nhớ hạn; tính lại phần còn lại**.

### 2.2. Đừng để thứ tự ưu tiên khác thứ tự đến hạn

Giả sử A đến hạn sau một giờ còn B đã đến hạn. Nếu `compareTo()` xếp theo tên và đặt A trước B, một phần tử đã sẵn sàng có thể bị che sau ứng viên chưa sẵn sàng. Không thể sửa lỗi này bằng cách chỉ làm `getDelay()` chính xác.

Trong các chương trình bên dưới, tất cả phần tử trong một hàng đợi dùng cùng một miền thời gian và so sánh trực tiếp các hạn bất biến:

```java
// Trích đoạn ý tưởng; không phải chương trình chạy độc lập.
return Long.compare(deadline, item.deadline);
```

Đừng thay bằng `(int) (deadline - item.deadline)`. Hiệu của hai số `long` có thể vượt miền `int`; phép ép kiểu làm mất thông tin, thậm chí đảo dấu. Ví dụ chênh lệch vài giây khi biểu diễn bằng nano giây đã có thể vượt `Integer.MAX_VALUE`. Dùng `Long.compare` tránh phép trừ trong bản thân phép so sánh, nhưng vẫn cần thiết kế miền hạn sao cho giá trị lưu có ý nghĩa: nó không tự sửa một phép tính hạn đã tràn trước đó.

Cũng không nên gọi `this.getDelay(...)` và `other.getDelay(...)` ở hai thời điểm khác nhau rồi trừ chúng để so sánh. Bạn đang thêm sự dịch chuyển của đồng hồ vào phép so sánh. Khi đã có cùng hệ quy chiếu, so sánh các hạn cố định đơn giản và ổn định hơn.

Các lớp ví dụ chỉ chấp nhận đúng loại phần tử của mình. Lớp dùng đồng hồ kiểm soát còn yêu cầu cùng một đối tượng đồng hồ. Đây là một ràng buộc của ví dụ để tránh trộn các hệ quy chiếu. Một lớp `Delayed` bất kỳ không mặc nhiên có thể so sánh có nghĩa với mọi lớp `Delayed` khác.

Hai phần tử có cùng hạn có thể so sánh bằng 0 dù chúng là hai công việc khác nhau. Đừng suy ra rằng hàng đợi sẽ gộp chúng hoặc giữ thứ tự đưa vào giữa chúng. Nếu bài toán cần một thứ tự ổn định khi trùng hạn, hãy bổ sung một tiêu chí phụ ổn định, chẳng hạn số thứ tự tăng dần, và kiểm soát vòng đời của số này. Bài hiện tại không đặt yêu cầu ấy nên không thêm một cơ chế phụ vào mã.

### 2.3. Đơn vị đo là một phần của hợp đồng

Tham số `unit` không phải lời gợi ý. Nếu phía gọi yêu cầu nano giây mà phần tử trả về số giây chưa chuyển đổi, điều kiện đến hạn bị tính sai rất lớn. Cách viết quen thuộc là lưu hạn theo một đơn vị chung rồi chuyển thời gian còn lại:

```java
// Trích đoạn: remaining được biểu diễn theo nano giây.
return unit.convert(remaining, TimeUnit.NANOSECONDS);
```

[API TimeUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html) phân biệt chuyển đổi đơn vị với độ chính xác đo thời gian. Khi đổi từ đơn vị nhỏ sang lớn, phần lẻ bị bỏ: 1 nano giây trở thành 0 mili giây. Vì vậy `getDelay(MILLISECONDS) == 0` chưa chứng minh phần tử đã đến hạn nếu nó vẫn còn 1 nano giây.

`DelayQueue` dùng dấu của thời gian còn lại theo nano giây để xác định điều kiện này. Chương trình đầu cố ý giữ lại đúng 1 nano giây để bạn nhìn thấy sự khác biệt mà không phụ thuộc tốc độ máy.

Ở chiều chuyển sang đơn vị nhỏ, kết quả quá lớn được `TimeUnit` chặn tại biên của `long`. Đây không phải phép xác thực đầu vào thay cho ứng dụng. Nếu chương trình chỉ hỗ trợ các khoảng ngắn, hãy kiểm tra miền sau chuyển đổi và từ chối khoảng ngoài thiết kế. Các ví dụ dùng đồng hồ thật bên dưới giới hạn khoảng trì hoãn trong cộng/trừ một ngày.

## 3. Chọn đồng hồ và giữ hạn bất biến

### 3.1. Khoảng chờ trong tiến trình khác một ngày giờ trên lịch

Một yêu cầu “đợi thêm 100 mili giây” là bài toán đo thời gian trôi qua. `System.nanoTime()` phù hợp với mục đích đó. Giá trị của nó không phải thời điểm kể từ một mốc lịch chuẩn, có thể âm và chỉ có ý nghĩa khi so sánh trong cùng miền đo của JVM.

Ngược lại, “chạy vào 09:00 ngày mai theo múi giờ của người dùng” là yêu cầu về lịch. Muốn đưa yêu cầu ấy vào một cơ chế chờ tương đối, bạn phải quyết định cách quy đổi và cách phản ứng với việc chỉnh đồng hồ hoặc khởi động lại. Bài này không biến `nanoTime()` thành một lịch lưu bền vững.

Không lưu một giá trị hạn `nanoTime()` vào cơ sở dữ liệu rồi coi nó là thời điểm có thể dùng lại sau khi JVM khởi động lại. Nếu cần lưu lịch, hãy lưu ý nghĩa thời gian thích hợp của bài toán, rồi thiết lập lại khoảng chờ trong tiến trình mới.

[API System.nanoTime()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()) cũng lưu ý miền hiệu thời gian hữu hạn của `long`. Phép đo nano giây không cho ta một trục số vô hạn; các khoảng xấp xỉ 292 năm đã chạm giới hạn của phép biểu diễn hiệu có dấu. Khi kiểm tra một khoảng đã trôi qua, cách viết theo hiệu thời gian thường phù hợp hơn việc giả định một phép cộng hạn luôn không tràn.

### 3.2. Thiết kế ngắn hạn dùng trong các chương trình

Hai chương trình dùng đồng hồ thật bên dưới có một thiết kế có chủ đích:

1. Một `ORIGIN` chung được lấy từ `System.nanoTime()`.
2. `elapsed()` tính khoảng đã trôi qua kể từ gốc ấy.
3. Mỗi phần tử có `deadline = elapsed() + delayNanos`.
4. `getDelay()` tính `deadline - elapsed()`.
5. `compareTo()` so sánh hai `deadline` trong cùng hệ quy chiếu.

`Math.addExact` làm phép cộng báo lỗi khi không thể biểu diễn, thay vì âm thầm cuộn số. Hạn được giữ trong trường `final`. Khoảng trì hoãn bị giới hạn trong cộng/trừ một ngày; chương trình chạy trong thời gian ngắn và không giữ phần tử qua những khoảng cực lớn. Với các giả thiết này, so sánh trực tiếp các độ lệch hạn là rõ ràng.

Đây là thiết kế cho các ví dụ ngắn hạn, không phải chứng minh rằng cộng/trừ hạn theo `long` an toàn với mọi thời gian sống của một hệ thống. `Math.addExact` ở phép cộng không tự bảo vệ mọi phép trừ trong một tiến trình chạy hàng trăm năm. Khi thay đổi miền sử dụng, phải xem lại cả chuyển đơn vị, phép cộng, phép trừ và quy tắc so sánh.

Cho phép khoảng âm trong ví dụ là có ý nghĩa: một phần tử được tạo với hạn ở quá khứ đã đủ điều kiện lấy ngay. “Hạn đã qua” không phải lỗi kiểu dữ liệu. Ứng dụng có thể chọn từ chối nó theo quy tắc nghiệp vụ riêng, nhưng không nên nhầm quy tắc ấy với điều kiện của `Delayed`.

### 3.3. Không sửa hạn khi phần tử còn trong hàng đợi

Bạn có thể khai báo `deadline` là `volatile` rồi sửa nó từ một luồng khác. Điều này chỉ liên quan đến khả năng nhìn thấy giá trị; nó không yêu cầu hàng đợi tự xây lại thứ tự và thay đổi lịch chờ.

Quan sát riêng với [mã nguồn OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/concurrent/DelayQueue.java): `DelayQueue` dùng một `PriorityQueue` bên trong cùng khóa và điều kiện chờ. Việc nhận ứng viên đầu dựa vào cấu trúc ưu tiên ấy. Sửa trực tiếp một khóa sắp xếp của đối tượng đang nằm trong cấu trúc không phải một thao tác cập nhật hàng đợi.

Vì vậy, thiết kế an toàn và dễ giải thích trong bài là: **một lần đưa vào tương ứng một phần tử có hạn bất biến**. Nếu cần lên lịch lại, hãy tạo phần tử mới với hạn mới, kèm quy tắc hủy/phiên bản phù hợp với bài toán. Trường hợp phần tử cũ đã được phía nhận lấy đi là một cuộc đua khác mà thao tác sửa trường không giải quyết được.

## 4. Đọc API theo hai câu hỏi: đang lưu gì, hiện lấy được gì?

Bảng dưới dùng “đến hạn” theo điều kiện nano giây đã giải thích. Nó là bản đồ để đọc các thí nghiệm, không phải lời hứa rằng nhiều thao tác liên tiếp trở thành một giao dịch.

| Nhóm | Thao tác | Cách hiểu cần nhớ |
| --- | --- | --- |
| Đưa vào | `offer(e)`, `put(e)`, `offer(e, timeout, unit)` | Không có giới hạn sức chứa; không chờ một chỗ trống. Tham số thời gian của bản `offer` không tạo thời gian trì hoãn cho phần tử. |
| Quan sát | `peek()`, `element()` | Nhìn ứng viên đầu, kể cả khi chưa đến hạn. `peek()` trả `null` khi không có ứng viên; `element()` báo lỗi khi trống. |
| Lấy ngay | `poll()`, `remove()` không đối số | Chỉ lấy phần tử đến hạn. Khi chưa có phần tử như vậy, `poll()` trả `null`; `remove()` ném `NoSuchElementException`. |
| Lấy có chờ | `take()`, `poll(timeout, unit)` | Chờ phần tử đến hạn; bản có giới hạn thời gian có thể trả `null`. Có thể bị ngắt bằng `InterruptedException`. |
| Kiểm tra lượng lưu | `size()`, `isEmpty()` | Tính cả phần tử chưa đến hạn. |
| Xóa có chủ đích | `remove(Object)`, `clear()` | Có thể xóa phần tử chưa đến hạn; `clear()` xóa toàn bộ phần tử đang lưu. |
| Chuyển phần sẵn sàng | `drainTo(...)` | Chuyển các phần tử đến hạn, có thể giới hạn số lượng bằng biến thể có `maxElements`. |

Nguồn tra cứu cho từng phương thức là [API DelayQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/DelayQueue.html). Với `element()` và `remove()` không đối số, xem thêm các phương thức kế thừa từ [AbstractQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractQueue.html): chúng dựa lần lượt vào `peek()` và `poll()`. Chính sự khác nhau của hai thao tác nền giải thích trường hợp `element()` nhìn thấy phần tử tương lai trong khi `remove()` vẫn báo không có phần tử lấy được.

Ba lưu ý trước khi chạy:

- `offer(e, 10, SECONDS)` không có nghĩa “cho e chờ 10 giây”. Hạn vẫn đến từ chính `e`. Đây là tham số chờ để đưa vào trong giao diện `BlockingQueue`, và `DelayQueue` không cần nó cho sức chứa.
- Không chờ sức chứa không có nghĩa cấu trúc này không dùng khóa hay mọi lời gọi hoàn tất tức thì bất kể cạnh tranh luồng.
- Không cho phép `null`. Giá trị `null` từ `poll()` có ý nghĩa thiếu phần tử đủ điều kiện, không phải một mục dữ liệu bạn đã đưa vào.


## 5. Thí nghiệm thứ nhất: tách đồng hồ khỏi tốc độ chạy của máy

Chương trình này dùng một đồng hồ số do ta điều khiển để quan sát các thao tác **không chờ**. Các số 10, 20, 30 là hạn theo nano giây trên trục thời gian thử nghiệm. Khi đổi đồng hồ từ 0 sang 20, ta không ngủ 20 nano giây; ta chủ động đặt “bây giờ” của các phần tử sang 20.

Nhờ vậy, kết quả không phụ thuộc việc máy mất bao lâu để in một dòng hoặc chạy một lệnh. Ta kiểm chứng quan hệ giữa hạn và thao tác, thay vì cố đo những khoảng quá nhỏ bằng `Thread.sleep()`.

Lưu toàn bộ mã sau vào `DelayQueueSemanticsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.concurrent.DelayQueue;
import java.util.concurrent.Delayed;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public class DelayQueueSemanticsDemo {
    public static void main(String[] args) {
        AtomicLong clock = new AtomicLong(0);
        ManualItem early = new ManualItem("early", 10, clock);
        ManualItem middle = new ManualItem("middle", 20, clock);
        ManualItem late = new ManualItem("late", 30, clock);
        DelayQueue<ManualItem> queue = new DelayQueue<>();
        queue.offer(late);
        queue.offer(early);
        queue.offer(middle);

        require(queue.size() == 3 && queue.peek() == early, "initial ordering");
        System.out.println("stored = " + queue.size());
        System.out.println("peek before expiry = " + queue.peek());
        System.out.println("poll before expiry = " + queue.poll());

        clock.set(20);
        System.out.println("poll at time 20 = " + queue.poll());
        List<ManualItem> drained = new ArrayList<>();
        int transferred = queue.drainTo(drained);
        require(transferred == 1 && drained.get(0) == middle, "expired drain");
        System.out.println("drained = " + drained);
        System.out.println("future-only empty = " + queue.isEmpty());
        System.out.println("element with future only = " + queue.element());
        try {
            queue.remove();
            throw new AssertionError("no expired head should be removable");
        } catch (NoSuchElementException ex) {
            System.out.println("remove without argument -> "
                    + ex.getClass().getSimpleName());
        }
        System.out.println("remove future by object = " + queue.remove(late));
        System.out.println("stored after removal = " + queue.size());

        AtomicLong tinyClock = new AtomicLong(0);
        ManualItem tiny = new ManualItem("tiny", 1, tinyClock);
        DelayQueue<ManualItem> tinyQueue = new DelayQueue<>();
        tinyQueue.offer(tiny);
        System.out.println("tiny delay in milliseconds = "
                + tiny.getDelay(TimeUnit.MILLISECONDS));
        System.out.println("tiny delay in nanoseconds = "
                + tiny.getDelay(TimeUnit.NANOSECONDS));
        System.out.println("tiny poll = " + tinyQueue.poll());
    }

    private static final class ManualItem implements Delayed {
        private final String name;
        private final long deadline;
        private final AtomicLong clock;

        private ManualItem(String name, long deadline, AtomicLong clock) {
            this.name = Objects.requireNonNull(name);
            this.deadline = deadline;
            this.clock = Objects.requireNonNull(clock);
        }

        @Override
        public long getDelay(TimeUnit unit) {
            long remaining = Math.subtractExact(deadline, clock.get());
            return unit.convert(remaining, TimeUnit.NANOSECONDS);
        }

        @Override
        public int compareTo(Delayed other) {
            if (!(other instanceof ManualItem item) || item.clock != clock) {
                throw new ClassCastException("same item type and clock required");
            }
            return Long.compare(deadline, item.deadline);
        }

        @Override
        public String toString() {
            return name;
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all DelayQueueSemanticsDemo.java
java DelayQueueSemanticsDemo
```

Kết quả:

```text
stored = 3
peek before expiry = early
poll before expiry = null
poll at time 20 = early
drained = [middle]
future-only empty = false
element with future only = late
remove without argument -> NoSuchElementException
remove future by object = true
stored after removal = 0
tiny delay in milliseconds = 0
tiny delay in nanoseconds = 1
tiny poll = null
```

### Giải thích từng chuyển trạng thái

Ở đầu chương trình, thứ tự thêm là `late`, `early`, `middle`, nhưng `peek()` nhìn thấy `early`. Điều này kiểm chứng quy tắc xếp theo hạn. `stored = 3` và `poll before expiry = null` cùng xuất hiện vì số lượng đang lưu không phải số lượng đã đến hạn.

Khi `clock.set(20)`, `early` có thời gian còn lại là -10. `poll()` lấy nó trước. `middle` có thời gian còn lại là 0, nên đủ điều kiện cho `drainTo()` tiếp theo. `late` vẫn còn 10 nên không bị chuyển vào danh sách `drained`.

Ở trạng thái chỉ còn `late`, ta quan sát ba khía cạnh của cùng một phần tử:

- Nó vẫn là dữ liệu được lưu, nên `isEmpty()` là `false`.
- Nó là ứng viên đầu, nên `element()` trả nó về.
- Nó chưa đến hạn, nên `remove()` không đối số ném `NoSuchElementException`.

Sau đó `remove(late)` xóa được nó. Đây là thao tác tìm đối tượng cần xóa, không phải thao tác lấy công việc đến hạn tiếp theo. Trong lớp ví dụ, không ghi đè `equals()`, nên việc truyền lại đúng đối tượng `late` làm ý nghĩa xóa rất rõ ràng.

Thí nghiệm `tiny` kiểm chứng đơn vị đo. Cùng một khoảng còn lại là 1 nano giây, đổi sang mili giây cho kết quả 0. Hàng đợi vẫn không giao nó qua `poll()`. Nếu chỉ kiểm tra số mili giây rồi kết luận rằng phần tử đã sẵn sàng, bạn sẽ kết luận sớm hơn điều kiện của hàng đợi.

### Giới hạn của đồng hồ điều khiển

Đừng mở rộng thí nghiệm này bằng cách gọi `take()` rồi chỉ `clock.set(...)` ở luồng khác và kỳ vọng hàng đợi tự thức dậy ngay. Đồng hồ điều khiển nằm trong phần tử; nó không điều khiển bộ chờ thời gian của `DelayQueue`. Đổi một `AtomicLong` không tự gửi tín hiệu đến điều kiện chờ bên trong hàng đợi.

Do đó chương trình chỉ dùng `peek()`, `poll()`, `drainTo()`, các thao tác quan sát và xóa. Nó giúp kiểm chứng điều kiện đến hạn mà không giả làm một bộ lập lịch theo thời gian ảo. Muốn kiểm thử các phương thức chờ, ta chuyển sang đồng hồ thật ở chương trình tiếp theo.

`Math.subtractExact` trong `ManualItem` cũng là một lựa chọn kiểm chứng: các giá trị thử nhỏ, nên không tràn. Nếu thay chúng bằng hai cực của `long`, ngoại lệ cho thấy dữ liệu thử đã vượt thiết kế; nó không chứng minh hàng đợi hỗ trợ mọi cặp hạn bất kỳ.

## 6. Thí nghiệm thứ hai: chờ, có ứng viên sớm hơn và ngắt luồng

Bài toán tiếp theo là phía nhận phải chờ khi chưa có mục đến hạn. Ta đặt một phần tử sau 12 giờ vào hàng đợi, chuẩn bị một lần `take()`, rồi đưa thêm một phần tử đã đến hạn. Phía nhận phải nhận được phần tử mới, không phải cố chờ phần tử 12 giờ chỉ vì nó được thêm trước.

Đây cũng là nơi cần phân biệt:

- **Thời gian chờ được tính từ hạn:** phần tử nào được giao.
- **Giới hạn chờ của lời gọi:** phía gọi chịu chờ tối đa bao lâu trong `poll(timeout, unit)`.
- **Tín hiệu ngắt:** yêu cầu dừng một luồng đang thực hiện thao tác có thể chờ.

Lưu thành `DelayQueueWaitingDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.DelayQueue;
import java.util.concurrent.Delayed;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class DelayQueueWaitingDemo {
    public static void main(String[] args) throws Exception {
        DelayQueue<TimedItem> queue = new DelayQueue<>();
        queue.put(new TimedItem("later", 12, TimeUnit.HOURS));
        CountDownLatch enteringTake = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<TimedItem> consumer = pool.submit(() -> {
                enteringTake.countDown();
                return queue.take();
            });
            await(enteringTake);
            queue.offer(new TimedItem("ready", -1, TimeUnit.SECONDS));
            TimedItem received = consumer.get(5, TimeUnit.SECONDS);
            require("ready".equals(received.name), "wrong head");
            require(received.getDelay(TimeUnit.NANOSECONDS) <= 0, "not expired");
            System.out.println("taken = " + received.name);
            System.out.println("next candidate = " + queue.peek().name);

            TimedItem timed = queue.poll(1, TimeUnit.MILLISECONDS);
            require(timed == null && queue.size() == 1, "timed poll");
            System.out.println("timed poll without expired item = " + timed);
            showInterruption(queue);
            queue.clear();
            System.out.println("empty after clear = " + queue.isEmpty());
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void showInterruption(DelayQueue<TimedItem> queue)
            throws Exception {
        CountDownLatch entering = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();
        Thread receiver = new Thread(() -> {
            entering.countDown();
            try {
                queue.take();
            } catch (InterruptedException ex) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
            } finally {
                finished.countDown();
            }
        });
        try {
            receiver.start();
            await(entering);
            receiver.interrupt();
            await(finished);
            require(interrupted.get(), "take must observe interruption");
            System.out.println("interrupted take observed = " + interrupted.get());
        } finally {
            receiver.interrupt();
            receiver.join(5_000);
            if (receiver.isAlive()) {
                throw new IllegalStateException("receiver did not terminate");
            }
        }
    }

    private static final class TimedItem implements Delayed {
        private static final long ORIGIN = System.nanoTime();
        private static final long MAX_DELAY = TimeUnit.DAYS.toNanos(1);
        private final String name;
        private final long deadline;

        private TimedItem(String name, long delay, TimeUnit unit) {
            this.name = Objects.requireNonNull(name);
            long nanos = Objects.requireNonNull(unit).toNanos(delay);
            if (nanos < -MAX_DELAY || nanos > MAX_DELAY) {
                throw new IllegalArgumentException("delay outside demo range");
            }
            deadline = Math.addExact(elapsed(), nanos);
        }

        private static long elapsed() {
            return System.nanoTime() - ORIGIN;
        }

        @Override
        public long getDelay(TimeUnit unit) {
            return unit.convert(deadline - elapsed(), TimeUnit.NANOSECONDS);
        }

        @Override
        public int compareTo(Delayed other) {
            if (!(other instanceof TimedItem item)) {
                throw new ClassCastException("TimedItem required");
            }
            return Long.compare(deadline, item.deadline);
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("latch timed out");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all DelayQueueWaitingDemo.java
java DelayQueueWaitingDemo
```

Kết quả:

```text
taken = ready
next candidate = later
timed poll without expired item = null
interrupted take observed = true
empty after clear = true
```

### Vì sao kết quả không cần chờ 12 giờ?

`later` có hạn trong tương lai. `ready` được tạo với khoảng -1 giây, vì vậy đã đến hạn khi được đưa vào. Phép so sánh đặt `ready` trước `later`; lần lấy trả `ready`. Sau đó `peek()` vẫn thấy `later`, xác nhận phần tử tương lai không bị mất.

Quan sát triển khai OpenJDK 17u đã dẫn ở trên: khi `offer()` đưa một ứng viên mới lên đầu, việc chờ được báo hiệu để phía nhận đánh giá lại ứng viên đầu. Đây là lời giải thích về triển khai cụ thể cho hành vi trong bài; hợp đồng học ở mức ứng dụng vẫn là thứ tự hạn và điều kiện đủ hạn.

`enteringTake` được đếm xuống ngay trước `take()`. Latch này phối hợp việc bắt đầu, **không chứng minh** luồng nhận đã ngủ trong `take()` trước khi `ready` được thêm. Có thể phần tử đã được thêm ngay trước lúc luồng nhận đi vào lời gọi. Cả hai cách xen kẽ đều phải dẫn đến kết quả hợp lệ như trên.

Đó là lý do chương trình không tuyên bố đã đo được thời gian đánh thức hoặc ép được một lịch xen kẽ duy nhất. Một kiểm thử đúng không cần biến một tín hiệu “sắp gọi” thành bằng chứng “đang bị chặn”.

### Giới hạn thời gian không đổi hạn của phần tử

Sau lần lấy đầu, hàng đợi chỉ còn `later`. `poll(1, MILLISECONDS)` không làm nó đến hạn sớm hơn. Khi không có mục đến hạn trong khoảng chờ này, kết quả là `null` dù hàng đợi vẫn lưu một phần tử.

Chương trình không kiểm tra một mili giây chính xác bằng đồng hồ ngoài. Độ phân giải hẹn giờ, lịch cấp CPU và tạm dừng của JVM có thể làm thời điểm lời gọi tiếp tục muộn hơn. Điều cần kiểm chứng là không lấy nhầm mục tương lai và không chờ vô hạn.

Các mốc 5 giây dùng cho `Future.get()`, latch và kết thúc luồng là giới hạn phát hiện chương trình không tiến triển trong môi trường chạy bình thường. Chúng không phải một bảo đảm thời gian thực của Java. Nếu máy bị dừng đủ lâu bởi trình gỡ lỗi hoặc hệ điều hành, kiểm thử có thể thất bại do giới hạn này.

### Ngắt là một phần của giao thức dừng

`showInterruption()` tạo một luồng nhận riêng, yêu cầu ngắt nó và kiểm tra rằng `InterruptedException` được quan sát. Ngắt có thể đến trước khi `take()` thực sự chờ hoặc trong lúc nó đang chờ; chương trình không dựa vào việc phân biệt hai trường hợp ấy.

Trong nhánh bắt ngoại lệ, luồng khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` rồi kết thúc. Việc khôi phục giúp giữ lại tín hiệu cho mã gọi bao quanh trong những thiết kế có lớp gọi bên ngoài. Tại ví dụ này luồng kết thúc ngay, nên tác dụng chính là minh họa cách không nuốt mất yêu cầu ngắt.

Khối `finally` tiếp tục ngắt và `join` có giới hạn để tránh bỏ lại luồng chạy ngoài ý muốn nếu một kiểm tra trước đó thất bại. Nhóm thực thi cũng được dừng và đợi kết thúc. Việc gọi `clear()` sau cùng chỉ dọn phần tử `later`; nó không thay thế các bước quản lý luồng.

Nếu bạn viết vòng lặp nhận thực tế, phải quyết định một trong các chính sách khi bị ngắt: truyền ngoại lệ lên trên, kết thúc vòng lặp, hoặc xử lý theo một giao thức dừng đã định nghĩa. Bắt ngoại lệ rồi lặp lại `take()` vô điều kiện có thể làm hệ thống không dừng được khi phía quản lý yêu cầu dừng.

### Tại sao trường hạn đều là final?

Ngay cả khi `ready` và `later` được nhìn thấy từ các luồng khác nhau, mã không có nhánh sửa hạn của chúng. Sau khi tạo, mỗi đối tượng giữ nguyên danh tính và hạn; thời gian còn lại thay đổi vì đồng hồ tiếp tục chạy.

Hàng đợi giải quyết việc phối hợp đưa/lấy; nó không khiến mọi dữ liệu tùy ý bên trong phần tử trở thành an toàn để sửa đồng thời. Nếu cần thêm trạng thái có thể thay đổi, phải thiết kế riêng cách đồng bộ hóa và vòng đời của trạng thái ấy. Với ví dụ này, giữ dữ liệu cần thiết bất biến là lựa chọn gọn và dễ kiểm chứng.


## 7. Ghép thành luồng thử lại có giới hạn

Một lần thử thất bại thường không nên được chạy lại ngay trong một vòng lặp nóng. Ta muốn chờ một khoảng ngắn, đồng thời giữ rõ số lần thử và điều kiện dừng.

Ví dụ dưới mô phỏng một công việc: lần 1 và 2 cần thử lại, lần 3 thành công. Nó không gọi mạng và không dùng lỗi ngẫu nhiên, nên kết quả có thể kiểm chứng. Mỗi lần lên lịch lại tạo một `RetryItem` mới với hạn mới; không sửa phần tử đang nằm trong hàng đợi.

Lưu thành `DelayQueueRetryDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.DelayQueue;
import java.util.concurrent.Delayed;
import java.util.concurrent.TimeUnit;

public class DelayQueueRetryDemo {
    public static void main(String[] args) throws Exception {
        DelayQueue<RetryItem> queue = new DelayQueue<>();
        queue.offer(new RetryItem("job-7", 1, 0, TimeUnit.NANOSECONDS));

        boolean completed = false;
        while (!completed) {
            RetryItem item = queue.poll(5, TimeUnit.SECONDS);
            require(item != null, "retry did not become available");
            require(item.getDelay(TimeUnit.NANOSECONDS) <= 0, "not expired");
            if (item.attempt < 3) {
                System.out.println("attempt " + item.attempt + " -> retry");
                queue.offer(new RetryItem(item.id, item.attempt + 1,
                        5, TimeUnit.MILLISECONDS));
            } else {
                System.out.println("attempt " + item.attempt + " -> success");
                completed = true;
            }
        }
        System.out.println("queue empty = " + queue.isEmpty());
    }

    private static final class RetryItem implements Delayed {
        private static final long ORIGIN = System.nanoTime();
        private static final long MAX_DELAY = TimeUnit.DAYS.toNanos(1);
        private final String id;
        private final int attempt;
        private final long deadline;

        private RetryItem(String id, int attempt, long delay, TimeUnit unit) {
            this.id = Objects.requireNonNull(id);
            if (attempt < 1) {
                throw new IllegalArgumentException("positive attempt required");
            }
            this.attempt = attempt;
            long nanos = Objects.requireNonNull(unit).toNanos(delay);
            if (nanos < -MAX_DELAY || nanos > MAX_DELAY) {
                throw new IllegalArgumentException("delay outside demo range");
            }
            deadline = Math.addExact(elapsed(), nanos);
        }

        private static long elapsed() {
            return System.nanoTime() - ORIGIN;
        }

        @Override
        public long getDelay(TimeUnit unit) {
            return unit.convert(deadline - elapsed(), TimeUnit.NANOSECONDS);
        }

        @Override
        public int compareTo(Delayed other) {
            if (!(other instanceof RetryItem item)) {
                throw new ClassCastException("RetryItem required");
            }
            return Long.compare(deadline, item.deadline);
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all DelayQueueRetryDemo.java
java DelayQueueRetryDemo
```

Kết quả:

```text
attempt 1 -> retry
attempt 2 -> retry
attempt 3 -> success
queue empty = true
```

### Theo dõi đường đi của một yêu cầu

Lần đưa vào đầu tiên có khoảng trì hoãn 0. Nó đã đến hạn khi phía nhận kiểm tra, nên lần lấy đầu không cần chờ cho một hạn tương lai.

Sau khi nhận lần 1, chính vòng lặp trong `main` quyết định rằng cần thử lại. Nó tạo lần 2 với khoảng 5 mili giây rồi gọi `offer()`. Khi vòng lặp lấy tiếp, phần tử chỉ được giao nếu đã đến hạn. Nếu máy đã tiêu thụ quá 5 mili giây giữa lúc thêm và lúc gọi lấy, việc trả về ngay cũng đúng: thời gian trì hoãn đã trôi qua.

Sau lần 2, quy trình tương tự tạo lần 3. Lần 3 thành công, `completed` thành `true` và vòng lặp kết thúc. Không còn phần tử để hẹn lại, nên `queue empty = true`.

Điểm quyết định không nằm ở một cơ chế bí mật của `DelayQueue`. Mã ứng dụng chủ động:

1. Lấy một phần tử đến hạn.
2. Thực hiện hoặc mô phỏng một lần thử.
3. Quyết định kết thúc hay lên lịch lại.
4. Nếu lên lịch lại, tạo một phần tử bất biến mới.

Khoảng 5 mili giây là khoảng trì hoãn đến lúc **đủ điều kiện lấy**, không phải cam kết rằng câu lệnh xử lý sẽ bắt đầu đúng sau 5 mili giây. Khi có nhiều yêu cầu hoặc phía nhận còn bận, một mục đã đến hạn vẫn có thể nằm trong hàng đợi.

Ví dụ giới hạn ba lần để có một vòng đời hoàn chỉnh. Khi áp dụng vào công việc thật, cần định nghĩa rõ số lần tối đa, lỗi nào được thử lại, xử lý khi dừng và cách tránh thực hiện trùng. Một hàng đợi theo hạn không tự biến một thao tác bên ngoài thành “thực hiện đúng một lần”.

Trong chương trình, `poll(5, SECONDS)` chỉ là một giới hạn chờ để phát hiện bất thường trong minh họa. Nó không phải chính sách thử lại sau 5 giây; chính khoảng truyền cho `RetryItem` mới tạo hạn. Phân biệt hai tham số này giúp tránh một lỗi thiết kế rất phổ biến: nhầm thời gian phía nhận chịu chờ với thời gian công việc cần trì hoãn.

## 8. Những lỗi cần nhận ra từ triệu chứng

### 8.1. Hàng đợi có nhiều phần tử nhưng phía nhận vẫn chờ

Trước tiên hãy hỏi: các phần tử ấy đã đến hạn chưa? Quan sát `peek()` rồi đọc `getDelay(NANOSECONDS)` để hiểu ứng viên tại thời điểm quan sát. Đây là thông tin chẩn đoán, không phải một thao tác đặt chỗ: một luồng khác có thể lấy hoặc thêm phần tử ngay sau đó.

Nếu ứng viên còn thời gian dương, việc `take()` chờ là bình thường. Nếu một phần tử bạn tin là đến hạn bị đứng sau ứng viên tương lai, kiểm tra `compareTo()` và việc có sửa khóa sắp xếp sau khi thêm hay không.

Đừng chữa bằng vòng lặp:

```java
// Phản ví dụ: chỉ là trích đoạn, không chạy độc lập.
while (!queue.isEmpty()) {
    Object item = queue.poll();
    // item vẫn có thể là null; vòng lặp có thể quay liên tục.
}
```

Một vòng lặp không chờ như vậy có thể tiêu thụ CPU khi toàn bộ mục còn ở tương lai. Nếu mô hình yêu cầu đợi mục kế tiếp, dùng thao tác có chờ và có chính sách dừng; nếu chỉ cần kiểm tra tức thời, xử lý kết quả `null` rồi trả quyền điều khiển cho bên gọi.

### 8.2. Phần tử không bao giờ được lấy

Kiểm tra xem `getDelay()` có đang trả mãi khoảng trì hoãn ban đầu hay không. Cũng kiểm tra đơn vị trả về, dấu phép trừ và việc hai loại phần tử có dùng cùng gốc thời gian.

Nếu viết `now - deadline` thay vì `deadline - now`, một mục tương lai có thể có dấu âm và được lấy sớm. Nếu luôn trả về một số dương, mục không đến hạn theo lời khai của nó. Nếu so sánh theo tên trong khi thời gian theo hạn, ứng viên đầu không còn đại diện cho mục sớm nhất.

Các lỗi này thuộc hợp đồng của phần tử. Thêm `synchronized` quanh lời gọi `poll()` không sửa được một biểu diễn thời gian sai.

### 8.3. Muốn hẹn lại nhưng chỉ thay một trường

Thay hạn trực tiếp có thể để thứ tự bên trong và thời gian chờ không còn phù hợp với giá trị mới. Dùng trường `volatile` cũng không biến thao tác sửa ấy thành “xóa rồi chèn lại”.

Với một công việc có thể được hẹn lại từ nhiều luồng, chỉ gọi `remove(oldItem)` rồi thêm bản mới chưa đủ để bảo đảm không có lần chạy cũ: phía nhận có thể đã lấy `oldItem`. Bạn cần quyết định kết quả cạnh tranh ấy ở cấp ứng dụng, chẳng hạn kiểm tra phiên bản công việc trước khi thực hiện hoặc có trạng thái hủy được đồng bộ thích hợp. Bài này chỉ yêu cầu nhận diện ranh giới; không giả định một giao thức hủy duy nhất đúng cho mọi ứng dụng.

`remove(Object)` dùng quy tắc khớp đối tượng. Trong ba lớp ví dụ, hai đối tượng có cùng tên hoặc mã công việc vẫn là hai đối tượng khác nhau vì không ghi đè `equals()`. Khi tự thiết kế `equals()`, phải cân nhắc liệu nhiều lần thử của cùng công việc có cần được phân biệt hay không. Đừng mặc nhiên coi mã công việc giống nhau là đã xác định đúng lần hẹn cần xóa.

### 8.4. Đưa nhiều dữ liệu vào rồi kỳ vọng hàng đợi tự giới hạn

`DelayQueue` không có sức chứa cấu hình để tự tạo áp lực ngược cho phía gửi. `remainingCapacity()` trả `Integer.MAX_VALUE` không có nghĩa JVM có bộ nhớ vô hạn hay có thể giữ đúng ngần ấy đối tượng trong thực tế.

Một mục đã đến hạn không tự biến mất chỉ vì thời gian trôi qua. Phải có thao tác lấy/xóa nó. Nếu phía gửi liên tục thêm, phía nhận bị dừng hoặc xử lý chậm, dữ liệu có thể tích tụ trong bộ nhớ.

Vì thế cần phân biệt hai bài toán:

- Quy tắc đủ hạn trả lời **khi nào được lấy**.
- Kiểm soát lượng công việc trả lời **có cho phép nhận thêm không**.

Nếu hệ thống cần giới hạn lượng mục đang chờ, phải bổ sung chính sách nhận việc phù hợp và giải phóng hạn mức đúng vòng đời. Không thể đạt điều ấy chỉ bằng cách chọn bản `offer` có tham số thời gian.

### 8.5. Gọi clear rồi chờ mọi luồng kết thúc

`clear()` xóa dữ liệu đang lưu. Nó không đóng hàng đợi và không quy định rằng các lần `take()` đang chờ phải kết thúc với một tín hiệu “đã đóng”. Một phía nhận vẫn có thể tiếp tục đợi mục đến hạn mới.

Quản lý dừng là giao thức khác: ứng dụng có thể giữ tham chiếu luồng để ngắt, dùng nhóm thực thi và hủy công việc đang chờ, hoặc thiết kế một tín hiệu kết thúc phù hợp. Phải đợi việc kết thúc nếu vòng đời tài nguyên yêu cầu điều ấy.

Đừng sao chép máy móc một phần tử báo dừng từ hàng đợi FIFO:

- Nếu phần tử báo dừng có hạn xa, phía nhận vẫn có thể phải chờ.
- Nếu nó đến hạn ngay, phía nhận có thể dừng trước các công việc tương lai mà bạn còn muốn xử lý.
- Nếu có nhiều phía nhận, cần quyết định tín hiệu kết thúc dành cho bao nhiêu phía.

Câu hỏi đúng là “khi dừng, các mục đang chờ được hoàn tất, hủy hay lưu lại?”, rồi mới chọn cách báo dừng.

### 8.6. Duyệt để suy ra thứ tự sắp nhận

Bộ duyệt của `DelayQueue` có tính nhất quán yếu và không bảo đảm thứ tự hạn. Nó có thể quan sát cả phần tử tương lai. Mảng thu được từ `toArray()` cũng không phải một danh sách đã sắp theo thời điểm được nhận.

Nếu chỉ cần hiển thị chẩn đoán, có thể sao chép rồi sắp xếp bản sao theo dữ liệu hạn đã biết, đồng thời hiểu rằng các luồng khác vẫn tiếp tục thay đổi hàng đợi. Bản sao ấy không phải ảnh chụp nguyên tử của mọi trạng thái trong hệ thống và không đặt chỗ cho lần lấy tiếp theo.

Nếu cần xử lý theo điều kiện của hàng đợi, hãy dùng thao tác lấy của chính hàng đợi. Đừng dùng vòng `for-each` làm bộ lập lịch.

### 8.7. Coi drainTo là “xóa tất cả” hoặc chuyển giao không thể thất bại

Chương trình đầu đã cho thấy `late` còn lại sau `drainTo()`. Đây là thao tác chuyển phần đủ điều kiện, không phải cách sao chép/xóa mọi phần tử đang được lưu. Muốn dọn toàn bộ dữ liệu là một yêu cầu khác.

Hãy chọn nơi nhận có khả năng thêm phần tử bình thường. Theo hợp đồng `drainTo`, nếu việc thêm sang nơi nhận ném ngoại lệ, không được suy ra một giao dịch đã tự hoàn tác hoàn toàn. Tránh chuyển vào chính hàng đợi nguồn. Khi cần tính nguyên tử trên hai cấu trúc hoặc xử lý nghiệp vụ ngoài bộ nhớ, phải thiết kế một giao thức riêng; một lời gọi chuyển hàng loạt không cung cấp mọi bảo đảm ấy.

## 9. Chọn đúng công cụ cho câu hỏi đang giải

`DelayQueue` phù hợp khi ứng dụng muốn sở hữu loại phần tử, điều kiện hạn và vòng nhận/xử lý. Chẳng hạn chương trình thử lại vừa rồi muốn kiểm soát rõ từng lần nhận và tạo lại phần tử.

Nếu yêu cầu chính là “chạy đoạn mã sau một khoảng” hoặc “chạy định kỳ”, hãy xem [ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html). Giao diện ấy có thao tác lập lịch thực hiện và trả về đối tượng để theo dõi/hủy công việc. `DelayQueue` chỉ cung cấp nền lưu và lấy theo hạn; nếu dùng nó, bạn tự sở hữu phần thực thi.

Nếu chỉ cần trao đổi dữ liệu giữa các luồng mà không có điều kiện thời gian trên từng mục, hãy bắt đầu từ yêu cầu thứ tự và sức chứa của một `BlockingQueue` phù hợp. Đừng thêm `Delayed` khi không có ý nghĩa nghiệp vụ nào cho hạn.

Nếu mục tiêu là dữ liệu hết hạn cần được dọn, việc chọn `DelayQueue` vẫn chưa tạo ra một hệ thống dọn tự động: cần có phía nhận và logic xóa tài nguyên. Nếu cần khôi phục sau khi tiến trình dừng, còn phải có nguồn lưu bền vững và quy tắc dựng lại lịch. Hàng đợi trong bộ nhớ không thay thế các yêu cầu ấy.

Các lựa chọn trên đều không tự bảo đảm bắt đầu xử lý đúng vào một thời điểm tuyệt đối. Đến hạn tạo điều kiện chạy; CPU, luồng xử lý, độ trễ hệ thống và công việc trước đó vẫn ảnh hưởng lúc thực hiện thật.

## 10. Tự kiểm tra và thực hành có lời giải

### Câu 1. Hàng đợi chỉ có một mục còn 30 giây. Dự đoán các kết quả

Giả sử không có luồng khác thêm/xóa và hạn chưa đến trong lúc quan sát. `size()`, `peek()`, `poll()` và `remove()` không đối số cho kết quả gì?

**Lời giải:** `size()` là 1; `peek()` trả mục ấy; `poll()` trả `null`; `remove()` ném `NoSuchElementException`. Phải phân biệt tồn tại với đủ điều kiện lấy. `remove(mucDo)` lại có thể xóa mục khi khớp đối tượng.

**Thực hành:** dùng đồng hồ điều khiển của chương trình đầu, tạo một mục có hạn 30 thay vì ngủ 30 giây. Kiểm chứng trạng thái trước hạn, đúng hạn và sau hạn. Chỉ dùng các thao tác không chờ trong thí nghiệm này.

### Câu 2. Sửa compareTo để ưu tiên công việc có mã nhỏ hơn có hợp lý không?

Giả sử mục mã 1 còn một giờ, mục mã 2 đã đến hạn. Bạn muốn mã 1 có “ưu tiên nghiệp vụ cao hơn”.

**Lời giải:** không thể thay thứ tự đến hạn bằng thứ tự mã mà vẫn giữ hợp đồng đang cần. Khi mục chưa đến hạn đứng trước, mục đã đến hạn có thể bị che. Nếu có ưu tiên nghiệp vụ, trước tiên phải định nghĩa cách nó tương tác với điều kiện thời gian. Một tiêu chí phụ cho các hạn bằng nhau khác với việc bỏ qua hạn hoàn toàn.

**Thực hành:** trên một bản thử riêng dùng đồng hồ điều khiển, cố ý đảo phép so sánh hạn rồi quan sát `peek()`/`poll()`. Giải thích bằng ứng viên đầu, sau đó phục hồi phép so sánh đúng. Không dùng phiên bản cố ý sai cho xử lý công việc thật.

### Câu 3. Tại sao thấy 0 mili giây mà poll vẫn trả null?

**Lời giải:** phép đổi đơn vị có thể bỏ phần lẻ. Khoảng 1 nano giây vẫn dương ở đơn vị nano giây nhưng là 0 ở mili giây. Điều kiện của hàng đợi dựa vào nano giây.

**Thực hành:** trong chương trình đầu, cho `tinyClock` chuyển từ 0 sang 1, rồi gọi lại `poll()`. Lúc này phần tử `tiny` phải được trả về. Không thêm một độ trễ thật vào bài kiểm chứng đơn vị.

### Câu 4. Vừa gọi remove(oldItem) nhưng một lần xử lý cũ vẫn xảy ra. Có thể không?

**Lời giải:** có. Phía nhận có thể đã lấy phần tử trước thao tác xóa; hoặc đối tượng bạn truyền không khớp mục cần xóa theo quy tắc bằng nhau. Hàng đợi không quay ngược việc đã giao phần tử. Nếu yêu cầu hủy phải tác động cả công việc đã được nhận, cần một trạng thái/giao thức hủy ở cấp công việc và một thời điểm kiểm tra rõ ràng.

**Thực hành:** mô tả hai lịch xen kẽ: xóa trước lần lấy, và lần lấy trước thao tác xóa. Ghi kết quả kỳ vọng của thao tác xóa trong từng lịch, rồi nêu điều bạn vẫn chưa biết về việc công việc bên ngoài đã thực hiện hay chưa.

### Câu 5. Thay 5 mili giây thử lại bằng 5 giây có phải chỉ sửa poll không?

**Lời giải:** không. Muốn hẹn lần thử sau 5 giây, phải đổi khoảng truyền cho `RetryItem` mới. `poll(timeout, unit)` chỉ giới hạn lần chờ của phía nhận. Nếu thời gian chờ ngắn hơn hạn của mục, kết quả `null` là một khả năng hợp lệ cần xử lý, không phải bằng chứng mất mục.

**Thực hành:** chọn một khoảng trì hoãn dài hơn giới hạn chờ, rồi thiết kế nhánh xử lý `null` rõ ràng. Xác định lúc nào tiếp tục chờ và lúc nào toàn bộ công việc bị hủy. Không chỉ xóa kiểm tra `require` rồi để vòng lặp quay vô hạn.

### Câu 6. Muốn dừng luồng nhận khi chưa có mục đến hạn thì clear có đủ không?

**Lời giải:** không. `clear()` dọn dữ liệu nhưng không đóng hàng đợi. Luồng đang nhận cần một giao thức dừng, chẳng hạn bị ngắt và kết thúc khi nhận `InterruptedException`, sau đó phía quản lý đợi nó kết thúc.

**Thực hành:** đọc lại `showInterruption()` và chỉ ra ba việc khác nhau: gửi yêu cầu ngắt, phía nhận quan sát yêu cầu, và phía quản lý đợi luồng kết thúc. Giải thích vì sao latch đặt trước `take()` không xác nhận trạng thái đang chờ.

## 11. Kiểm chứng và tài liệu tra cứu

Ba chương trình trong bài được biên dịch với `javac --release 17 -encoding UTF-8 -Xlint:all` và chạy trên OpenJDK 24.0.2; kết quả đầu ra khớp các khối `text` đã nêu. `--release 17` kiểm tra khả năng dùng cú pháp/API ở mức Java 17 khi biên dịch; nó không có nghĩa lần chạy này đã diễn ra trên một JVM 17.

Khi tự chạy, giữ đúng tên tệp, dùng JDK 17 trở lên và chạy từng chương trình độc lập. Chương trình đầu không đo thời gian thật; hai chương trình sau dùng hạn tương đối và có giới hạn chờ để tránh bỏ lại vòng nhận vô hạn trong minh họa. Không có kết quả nào yêu cầu một thời điểm thực hiện chính xác đến nano giây.

Các nguồn gốc để đối chiếu hợp đồng:

- [Delayed — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Delayed.html): thời gian còn lại và thứ tự so sánh nhất quán.
- [DelayQueue — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/DelayQueue.html): quy tắc lấy, quan sát, xóa, chuyển và duyệt.
- [AbstractQueue — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractQueue.html): hành vi của `remove()` và `element()` kế thừa.
- [TimeUnit — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): chuyển đơn vị, bỏ phần lẻ và giới hạn biểu diễn.
- [System.nanoTime() — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): đo thời gian trôi qua và giới hạn của hiệu thời gian.
- [ScheduledExecutorService — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): lập lịch thực hiện khi cần quản lý việc chạy.
- [Mã nguồn DelayQueue trong OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/concurrent/DelayQueue.java): phần quan sát triển khai về cấu trúc ưu tiên và báo hiệu khi ứng viên đầu thay đổi; không thay thế hợp đồng API.

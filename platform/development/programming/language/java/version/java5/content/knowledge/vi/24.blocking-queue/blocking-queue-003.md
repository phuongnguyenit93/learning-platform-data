# So sánh remove, poll, take và poll có thời hạn

## 1. Bài toán: làm gì khi chưa có phần tử để lấy?

Một luồng tạo dữ liệu (producer) đưa công việc vào hàng đợi; một luồng xử lý (consumer) lấy công việc ra. Nếu tại thời điểm lấy, hàng đợi chưa có phần tử sẵn sàng, luồng xử lý cần một chính sách rõ ràng: báo lỗi, nhận kết quả rỗng để làm việc khác, chờ công việc tiếp theo, hay chỉ chờ trong một khoảng thời gian.

Trong `BlockingQueue<E>`, bốn cách lấy phần tử đầu là `remove()`, `poll()`, `take()` và `poll(long timeout, TimeUnit unit)`. Khi lấy được, cả bốn đều trả về phần tử kiểu `E` và đồng thời loại phần tử đó khỏi hàng đợi. Khác biệt chính là cách xử lý khi chưa lấy được. Đây vẫn là các API dùng được trong Java hiện đại; ví dụ trong bài biên dịch được với Java 17 trở lên.

“Đầu hàng đợi” do loại hàng đợi quyết định. `ArrayBlockingQueue` dùng thứ tự vào trước, ra trước (FIFO), nhưng không được suy rộng thứ tự FIFO cho mọi `BlockingQueue`, chẳng hạn hàng đợi ưu tiên. Nếu chỉ muốn xem phần tử mà giữ nguyên hàng đợi, cần `peek()` hoặc `element()`, không phải bốn phương thức đang so sánh.

## 2. Bảng so sánh

| Phương thức | Khi có phần tử lấy được | Khi chưa có phần tử lấy được | Có chờ phần tử xuất hiện? | Khai báo `InterruptedException`? |
| --- | --- | --- | --- | --- |
| `E remove()` | Lấy và xóa phần tử đầu | Ném `NoSuchElementException` | Không | Không |
| `E poll()` | Lấy và xóa phần tử đầu | Trả `null` | Không | Không |
| `E take()` | Lấy và xóa phần tử đầu | Chờ cho đến khi lấy được, hoặc bị ngắt | Có, không có thời hạn do lời gọi đặt ra | Có |
| `E poll(long timeout, TimeUnit unit)` | Lấy và xóa phần tử đầu | Chờ; nếu hết thời gian chờ mà chưa lấy được thì trả `null` | Có giới hạn | Có |

`remove()` và `poll()` không đợi dữ liệu mới. Tuy nhiên, cách gọi “không chờ” trong bảng không cam kết rằng chúng không bao giờ chịu tranh chấp khóa nội bộ, cũng không cam kết độ trễ thời gian thực.

`BlockingQueue` không cho phép lưu `null`. Vì vậy, `null` do `poll()` trả về là tín hiệu không lấy được phần tử, không phải một công việc có giá trị `null`. API này cũng không dùng `null` để báo “hàng đợi đã đóng”. Theo hợp đồng API, cách xử lý lỗi/rỗng/chờ được phân biệt trong [BlockingQueue — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

## 3. Hiểu từng chính sách lấy

### 3.1. `remove()`: thiếu phần tử là tình huống bất thường

Dùng `remove()` khi thiết kế đã bảo đảm một phần tử phải tồn tại tại thời điểm lấy, và việc không có phần tử là lỗi cần bộc lộ. Ví dụ: kiểm thử một chuỗi thao tác trong một luồng sau khi vừa thêm dữ liệu và không có bên nào khác được phép lấy mất nó.

Trong một hệ thống nhiều luồng, producer chưa kịp đưa dữ liệu vào thường là chuyện bình thường. Dùng ngoại lệ làm nhịp điều khiển cho trường hợp ấy khiến mã khó đọc và xử lý lỗi bị lẫn với hoạt động thường ngày.

### 3.2. `poll()`: thử lấy một lần rồi quyết định ngay

`poll()` phù hợp khi luồng có thể làm việc khác nếu không có công việc. Luôn lưu kết quả vào biến rồi kiểm tra biến đó:

```java
// Đoạn minh họa bên trong một phương thức; queue là BlockingQueue<String>.
String job = queue.poll();
if (job == null) {
    System.out.println("No job available");
} else {
    System.out.println("Received: " + job);
}
```

Không gọi `poll()` hai lần để kiểm tra rồi xử lý, vì mỗi lần gọi thành công đều lấy mất một phần tử. Nếu hàng đợi chỉ có một phần tử, lần đầu có thể lấy được nhưng lần sau lại trả `null`.

### 3.3. `take()`: công việc tiếp theo là điều luồng cần chờ

`take()` hợp với luồng chuyên xử lý công việc liên tục. Khi chưa có công việc, luồng chờ thay vì liên tục kiểm tra hàng đợi. Chờ ở đây không đồng nghĩa với vòng lặp tự quay dùng CPU, và cũng không phải bảo đảm cả tiến trình ngừng chạy: các luồng khác vẫn có thể hoạt động.

Không có đối số thời hạn nghĩa là lời gọi có thể chờ mãi nếu không ai đưa thêm phần tử và không có cơ chế ngắt phù hợp. Việc producer đã kết thúc không tự đánh thức consumer để thông báo hết dữ liệu. Khi dùng `take()`, cần thiết kế riêng cách dừng: ngắt luồng hoặc một thông điệp kết thúc có ý nghĩa trong giao thức ứng dụng.

### 3.4. `poll(timeout, unit)`: lấy ngay nếu được, nếu chưa được thì chờ có giới hạn

`poll(200, TimeUnit.MILLISECONDS)` không bắt buộc ngủ 200 ms rồi mới kiểm tra. Nếu có phần tử lấy được ngay thì nó có thể trả về ngay; nếu phần tử xuất hiện trong lúc chờ, lời gọi có thể hoàn tất sớm; nếu hết thời gian chờ mà chưa lấy được, kết quả là `null`.

Thời hạn này áp dụng cho việc chờ lấy phần tử. Nó không phải thời hạn xử lý công việc sau khi lấy, không hủy công việc, và không bảo đảm toàn bộ lời gọi cùng việc xử lý sẽ kết thúc đúng một mốc đồng hồ. Lập lịch luồng và tranh chấp tài nguyên vẫn có thể ảnh hưởng thời điểm chương trình tiếp tục.

Một lần trả `null` không chứng minh producer sẽ không tạo dữ liệu nữa. Chỉ dừng consumer sau `null` nếu giao thức ứng dụng thực sự định nghĩa rằng không có dữ liệu trong khoảng thời gian đó là lý do kết thúc. Truyền `TimeUnit` rõ ràng giúp tránh nhầm giây với mili giây; không truyền `null` cho đơn vị thời gian. Thời hạn bằng 0 hoặc âm không dành thời gian đợi một phần tử sẽ xuất hiện trong tương lai; điều này không làm lời gọi trở thành một cam kết độ trễ bằng 0.

## 4. Chương trình chạy đầy đủ

Lưu nội dung sau trong `QueueRemovalDemo.java`. Ví dụ dùng hàng đợi FIFO có sức chứa 2, kiểm tra hành vi lúc rỗng, lúc có dữ liệu và khi có producer riêng. Những kiểm tra bằng `check` ném lỗi nếu kết quả khác dự kiến, không phụ thuộc tùy chọn bật Java assertions.

```java
import java.util.NoSuchElementException;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class QueueRemovalDemo {
    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected queue result");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

        try {
            queue.remove();
            throw new AssertionError("remove must fail on an empty queue");
        } catch (NoSuchElementException expected) {
            System.out.println("remove(empty): NoSuchElementException");
        }

        check(queue.poll() == null);
        System.out.println("poll(empty): null");

        check(queue.poll(20, TimeUnit.MILLISECONDS) == null);
        System.out.println("timed poll(empty): null");

        queue.put("A");
        queue.put("B");
        check("A".equals(queue.remove()));
        check("B".equals(queue.poll()));
        System.out.println("remove/poll: A, B");

        CountDownLatch ready = new CountDownLatch(1);
        Thread producer = new Thread(() -> {
            try {
                ready.await();
                queue.put("C");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        producer.start();
        ready.countDown();
        String item = queue.take();
        producer.join();
        check("C".equals(item));
        System.out.println("take: " + item);

        queue.put("D");
        check("D".equals(queue.poll(1, TimeUnit.SECONDS)));
        System.out.println("timed poll(nonempty): D");

        check(queue.isEmpty());
        check(!queue.remove("missing"));
        System.out.println("remove(Object): false");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 QueueRemovalDemo.java
java QueueRemovalDemo
```

Stdout:

```text
remove(empty): NoSuchElementException
poll(empty): null
timed poll(empty): null
remove/poll: A, B
take: C
timed poll(nonempty): D
remove(Object): false
```

Hai phần tử `A`, `B` được lấy theo FIFO vì ví dụ chọn `ArrayBlockingQueue`. Lần `poll` có thời hạn đầu tiên chạy trên hàng đợi rỗng và không có producer nào đang hoạt động, nên chắc chắn trả `null`; không cần đo hay khẳng định thời gian thực tế chính xác là 20 ms.

`CountDownLatch` cho producer biết khi nào được phép đưa `C` vào hàng đợi. Tùy lịch chạy, producer có thể đưa `C` vào ngay trước khi `take()` bắt đầu hoặc trong khi nó chờ. Cả hai đều hợp lệ; ví dụ bảo đảm giá trị trả về và stdout, không dùng một lần chạy để khẳng định luồng đã chờ bao lâu. `join()` đợi producer kết thúc trước phần kiểm tra tiếp theo.

Lần lấy `D` minh họa rằng `poll(1, TimeUnit.SECONDS)` có thể thành công trên hàng đợi đã có dữ liệu; một giây là thời gian chờ cho phép khi cần, không phải độ trễ bắt buộc.

## 5. Ngắt luồng là kết quả khác với hết thời gian chờ

`take()` và `poll(timeout, unit)` có thể ném `InterruptedException`. Đó là thông báo luồng bị yêu cầu ngắt trong quá trình chờ có thể bị ngắt, không phải kết quả rỗng thông thường. Không biến mọi `InterruptedException` thành `null` rồi tiếp tục như thể chưa có dữ liệu.

Nếu phương thức hiện tại cho phép chuyển ngoại lệ lên bên gọi, có thể khai báo `throws InterruptedException` như `main` trong ví dụ. Nếu đang viết `Runnable` hoặc một phương thức không chuyển được ngoại lệ đó lên, một cách xử lý thường gặp là khôi phục cờ ngắt rồi kết thúc tác vụ:

```java
// Đoạn minh họa thân một tác vụ; queue là BlockingQueue<String>.
try {
    while (!Thread.currentThread().isInterrupted()) {
        String job = queue.take();
        System.out.println("Received: " + job);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Kết thúc tác vụ sau khối catch; không quay lại vòng lặp lấy việc.
}
```

Khi `InterruptedException` được ném, cờ ngắt thường đã được xóa theo cơ chế của thao tác chờ; khôi phục cờ giúp phần mã ở tầng ngoài vẫn nhận biết yêu cầu dừng. Bản thân việc gọi `interrupt()` không chứng minh một công việc đã được xử lý hay chưa. Nếu một công việc đã được lấy ra, cần chính sách riêng cho xử lý lỗi, thử lại hoặc ghi nhận hoàn tất. Cơ chế cờ ngắt được trình bày trong [Thread — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#interrupt()).

## 6. An toàn nhiều luồng: thao tác đơn lẻ khác chuỗi thao tác

Mỗi thao tác lấy của `BlockingQueue` là an toàn khi nhiều luồng cùng truy cập. Điều đó không làm cho đoạn `isEmpty()` rồi `remove()` trở thành một thao tác duy nhất:

```java
// Đoạn minh họa có tranh chấp: không dùng làm cách lấy an toàn.
if (!queue.isEmpty()) {
    String job = queue.remove();
}
```

Sau khi `isEmpty()` trả `false`, consumer khác có thể lấy mất phần tử cuối cùng. `remove()` tiếp theo vẫn ném `NoSuchElementException`. Nếu không muốn chờ, dùng một lần `poll()` và kiểm tra chính kết quả của lần đó. Nếu muốn chờ công việc tiếp theo, chọn `take()` hoặc `poll` có thời hạn.

`size()` và `peek()` trước khi lấy cũng không “giữ chỗ” phần tử. Tương tự, tính an toàn của thao tác lấy không có nghĩa rằng xử lý nghiệp vụ sau khi lấy là nguyên tử cùng hàng đợi. Nếu luồng lỗi sau khi lấy, hàng đợi không tự khôi phục công việc vừa bị xóa.

Cũng cần phân biệt dữ liệu đã được đưa vào hàng đợi với khả năng lấy dữ liệu tại thời điểm hiện tại. Với loại chuyên biệt như `DelayQueue`, một phần tử chưa hết thời gian trì hoãn chưa đủ điều kiện để lấy. Vì thế, không suy luận đơn giản rằng `size() > 0` luôn khiến mọi cách lấy đều thành công ngay; xem hợp đồng riêng của [DelayQueue — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/DelayQueue.html).

## 7. Đừng nhầm `remove()` với `remove(Object)`

| Lời gọi | Ý nghĩa | Kiểu trả về | Khi không có phần tử phù hợp |
| --- | --- | --- | --- |
| `queue.remove()` | Lấy và xóa phần tử đầu | `E` | Ném `NoSuchElementException` nếu không lấy được phần tử đầu |
| `queue.remove(value)` | Tìm và xóa một phần tử bằng `value` theo `equals` | `boolean` | Trả `false` |

`remove(Object)` không phải biến thể chờ của `remove()`, không nhất thiết xóa phần tử đầu và thường không phải đường lấy công việc chính của consumer. Với `BlockingQueue<Integer>`, lời gọi `queue.remove(1)` yêu cầu xóa giá trị `Integer` bằng 1; nó không có nghĩa là xóa phần tử ở chỉ số 1 như một số cách dùng `List`.

Hợp đồng lấy phần tử đầu và sự khác biệt giữa `remove()` với `poll()` được mô tả trong [Queue — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Queue.html).

## 8. Chọn theo điều luồng cần làm

| Nhu cầu | Lựa chọn thường phù hợp | Điều phải xử lý rõ |
| --- | --- | --- |
| Thiếu phần tử thể hiện vi phạm giả định chương trình | `remove()` | `NoSuchElementException` và nguyên nhân giả định sai |
| Thử lấy một lần, không có thì làm việc khác | `poll()` | Nhánh `null` |
| Dành riêng một luồng chờ công việc tiếp theo | `take()` | Ngắt luồng và giao thức kết thúc |
| Cho phép chờ một khoảng rồi kiểm tra việc dừng hoặc việc khác | `poll(timeout, unit)` | Phân biệt `null`, phần tử nhận được và `InterruptedException` |

Tránh vòng `while (queue.poll() == null) {}` chỉ để chờ dữ liệu: nó kiểm tra liên tục và có thể tiêu tốn CPU. Đổi sang phương thức chờ phù hợp với yêu cầu. Cũng không cần tự ghép `isEmpty()` với `Thread.sleep(...)` để mô phỏng `take()`: cách đó thêm độ trễ và vẫn không làm chuỗi kiểm tra–lấy trở nên nguyên tử.

## 9. Tự kiểm tra

1. Hai consumer cùng thấy `isEmpty() == false`. Vì sao một bên vẫn có thể nhận `NoSuchElementException` khi gọi `remove()`? Vì quan sát và lấy là hai thao tác; bên kia có thể lấy mất phần tử giữa chúng.
2. `poll(5, TimeUnit.SECONDS)` gặp hàng đợi đã có phần tử lấy được. Có phải chờ đủ 5 giây không? Không; nó có thể trả phần tử ngay.
3. Một lần timed `poll` trả `null`. Có thể kết luận mọi producer đã dừng không? Không; kết quả chỉ nói lần chờ đó chưa lấy được phần tử trước khi hết thời gian chờ.
4. Khi cần hủy tác vụ đang chờ `take()`, có nên nuốt `InterruptedException` rồi tiếp tục chờ không? Không; cần tuân theo chính sách hủy, thường chuyển ngoại lệ lên hoặc khôi phục cờ ngắt và thoát.
5. `remove()` và `poll()` thành công có giữ phần tử trong hàng đợi không? Không; cả hai đều lấy và xóa. Muốn quan sát mà không xóa thì dùng phương thức xem.

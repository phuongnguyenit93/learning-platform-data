# Phân biệt remove, poll, element và peek

## 1. Hai câu hỏi khi làm việc với đầu hàng đợi

Bốn phương thức không tham số này của `Queue<E>` đều liên quan đến phần tử ở đầu hàng đợi (head), nhưng khác nhau theo hai trục:

1. Chỉ xem phần tử hay đồng thời lấy nó ra khỏi hàng đợi?
2. Nếu hàng đợi rỗng, ném ngoại lệ hay trả giá trị báo không có phần tử?

| Phương thức | Hành động khi có phần tử | Có thay đổi hàng đợi? | Khi hàng đợi rỗng |
| --- | --- | --- | --- |
| `E remove()` | Trả và loại bỏ phần tử đầu | Có | Ném `NoSuchElementException` |
| `E poll()` | Trả và loại bỏ phần tử đầu | Có | Trả `null` |
| `E element()` | Trả phần tử đầu để xem | Không | Ném `NoSuchElementException` |
| `E peek()` | Trả phần tử đầu để xem | Không | Trả `null` |

Một cách nhớ có ích:

- `remove` / `poll`: lấy ra.
- `element` / `peek`: xem.
- `remove` / `element`: yêu cầu phải có phần tử.
- `poll` / `peek`: cho phép biểu diễn trạng thái không có bằng null.

Các phương thức này vẫn là API thông thường trong Java hiện đại. Bài dùng JDK 17+ và không cần thư viện ngoài.

## 2. “Đầu hàng đợi” không phải lúc nào cũng là phần tử thêm trước nhất

Interface Queue không áp đặt mọi cài đặt đều FIFO.

- `ArrayDeque` khi dùng như Queue qua các thao tác thêm cuối/lấy đầu cho hành vi FIFO: phần tử vào trước được lấy trước.
- `PriorityQueue` chọn đầu theo thứ tự tự nhiên hoặc Comparator: đầu là phần tử nhỏ nhất theo thứ tự đã chọn.
- Nếu nhiều phần tử có cùng mức so sánh trong PriorityQueue, không được giả định lấy theo thứ tự thêm.

Vì vậy, bốn phương thức khác nhau về hành động và cách xử lý rỗng; phần tử nào được xem là đầu do cài đặt và quy tắc sắp thứ tự của hàng đợi quyết định.

Không dùng thứ tự in trực tiếp toàn bộ PriorityQueue hoặc thứ tự iterator để suy ra thứ tự poll. PriorityQueue không cam kết phép duyệt trả phần tử theo thứ tự ưu tiên.

## 3. Chương trình đầy đủ: xem, lấy và kiểm tra rỗng

Lưu thành `QueueHeadMethodsDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.NoSuchElementException;
import java.util.PriorityQueue;
import java.util.Queue;

public class QueueHeadMethodsDemo {
    public static void main(String[] args) {
        Queue<String> fifo = new ArrayDeque<>();
        fifo.offer("A");
        fifo.offer("B");

        System.out.println("peek=" + fifo.peek());
        System.out.println("size after peek=" + fifo.size());
        System.out.println("element=" + fifo.element());
        System.out.println("size after element=" + fifo.size());

        System.out.println("poll=" + fifo.poll());
        System.out.println("size after poll=" + fifo.size());
        System.out.println("remove=" + fifo.remove());
        System.out.println("size after remove=" + fifo.size());

        System.out.println("empty peek=" + fifo.peek());
        System.out.println("empty poll=" + fifo.poll());

        try {
            fifo.element();
        } catch (NoSuchElementException exception) {
            System.out.println("empty element="
                    + exception.getClass().getSimpleName());
        }

        try {
            fifo.remove();
        } catch (NoSuchElementException exception) {
            System.out.println("empty remove="
                    + exception.getClass().getSimpleName());
        }

        Queue<Integer> priority = new PriorityQueue<>();
        priority.offer(30);
        priority.offer(10);
        priority.offer(20);

        System.out.println("priority peek=" + priority.peek());
        System.out.println("priority size=" + priority.size());

        StringBuilder order = new StringBuilder();
        Integer value;
        while ((value = priority.poll()) != null) {
            if (order.length() > 0) {
                order.append(",");
            }
            order.append(value);
        }
        System.out.println("priority poll order=" + order);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 QueueHeadMethodsDemo.java
java QueueHeadMethodsDemo
```

Kết quả:

```text
peek=A
size after peek=2
element=A
size after element=2
poll=A
size after poll=1
remove=B
size after remove=0
empty peek=null
empty poll=null
empty element=NoSuchElementException
empty remove=NoSuchElementException
priority peek=10
priority size=3
priority poll order=10,20,30
```

Hai thao tác xem không làm giảm kích thước. Hai thao tác lấy làm giảm kích thước khi thành công. Khi đã hết phần tử, `peek` và `poll` trả null, còn `element` và `remove()` ném ngoại lệ.

Ở PriorityQueue, số 30 được thêm đầu tiên nhưng số 10 nằm ở đầu theo thứ tự tự nhiên. `peek` không lấy 10 ra; chỉ vòng lặp poll sau đó mới lấy lần lượt 10, 20, 30.

## 4. Chọn phương thức theo hợp đồng của đoạn mã

### 4.1. Rỗng là trạng thái bình thường: poll hoặc peek

Ví dụ xử lý hết các công việc đang có trong một hàng đợi không chứa null:

```java
// Đoạn minh họa bên trong một phương thức:
String job;
while ((job = queue.poll()) != null) {
    process(job);
}
```

`queue` và `process` là các thành phần của chương trình sử dụng, nên đoạn trên không chạy độc lập.

Ở đây, không có công việc là điều kiện kết thúc bình thường; poll thể hiện ý định đó mà không dùng ngoại lệ để điều khiển vòng lặp.

Nếu chỉ muốn xem công việc tiếp theo:

```java
String next = queue.peek();
if (next != null) {
    System.out.println("Next job: " + next);
}
```

Nhánh này chỉ quan sát. Nó không xác nhận công việc đã được nhận hoặc được xử lý, vì phần tử vẫn còn trong hàng đợi.

### 4.2. Bắt buộc phải có dữ liệu: remove hoặc element

Nếu hợp đồng tại một vị trí yêu cầu phải có phần tử và trạng thái rỗng là lỗi, có thể dùng:

```java
String current = queue.remove();
```

Hoặc chỉ xem mà không lấy:

```java
String current = queue.element();
```

Nếu rỗng, `NoSuchElementException` làm lỗi lộ ra thay vì âm thầm đưa null đi tiếp.

Dù vậy, cần đánh giá thông báo và ranh giới lỗi của ứng dụng. Có lúc muốn dùng poll rồi tự ném một ngoại lệ mang ngữ cảnh rõ hơn. Sự lựa chọn nên phản ánh hợp đồng dữ liệu, không chỉ dựa trên thói quen “ngoại lệ thì không tốt”.

Không dùng remove trong vòng lặp rồi bắt `NoSuchElementException` để dừng nếu hàng đợi rỗng vốn là trường hợp thường xuyên và poll đã biểu đạt đúng yêu cầu.

## 5. Null là giá trị báo rỗng: vì sao không nên chứa null?

Queue dùng null làm kết quả đặc biệt của poll và peek khi không có phần tử. `ArrayDeque` và `PriorityQueue` không cho phép thêm phần tử null.

Một số cài đặt khác có thể cho phép null, nhưng dùng chúng qua mô hình Queue với dữ liệu null làm kết quả khó hiểu: một lần poll trả null có thể là đã lấy một phần tử null hoặc không có phần tử nào.

Vì vậy:

- Với hàng đợi công việc, ưu tiên không dùng null làm phần tử.
- Nếu cần biểu diễn công việc có dữ liệu thiếu, dùng một đối tượng chứa trạng thái rõ ràng.
- Khi dùng vòng lặp `while ((item = queue.poll()) != null)`, phải biết hàng đợi không chứa phần tử null.

Không tự bỏ hộp kết quả trước khi xử lý rỗng:

```java
Queue<Integer> numbers = new ArrayDeque<>();

// Không an toàn khi rỗng:
// int first = numbers.poll();

Integer first = numbers.poll();
if (first == null) {
    System.out.println("No number");
} else {
    System.out.println("Number: " + first);
}
```

Dòng bị chú thích sẽ gây `NullPointerException` do bỏ hộp null thành int. Đây là lỗi tại phép chuyển đổi, khác với `NoSuchElementException` của `remove()`.

## 6. remove() và remove(Object) là hai thao tác khác nhau

Tên `remove` dễ bị hiểu nhầm vì Queue kế thừa thao tác từ Collection.

| Chữ ký | Kết quả | Phần tử bị xóa | Không tìm thấy hoặc rỗng |
| --- | --- | --- | --- |
| `E remove()` | Phần tử đầu được lấy ra | Đầu hàng đợi | Ném NoSuchElementException nếu rỗng |
| `boolean remove(Object value)` | Có xóa được hay không | Một phần tử khớp giá trị theo hợp đồng equals | Trả false nếu không có phần tử khớp |

Ví dụ minh họa:

```java
Queue<Integer> numbers = new PriorityQueue<>();
numbers.offer(10);
numbers.offer(20);

boolean removedTwenty = numbers.remove(20);
Integer first = numbers.remove();
```

`remove(20)` có đối số, nên gọi phiên bản tìm và xóa giá trị 20, trả boolean. `remove()` không đối số mới lấy đầu, lúc đó là 10.

Không suy từ việc `remove(20)` trả false sang kết luận `remove()` cũng trả false khi rỗng. Hai phương thức có chữ ký và hợp đồng khác nhau.

Với PriorityQueue, `remove(Object)` còn có đặc điểm chi phí khác: phải tìm một đối tượng theo giá trị, trong khi remove() lấy đầu theo cấu trúc ưu tiên.

## 7. Độ phức tạp phụ thuộc cài đặt

Với PriorityQueue:

- `peek()` và `element()` xem đầu mà không chỉnh lại cấu trúc: thời gian O(1).
- `poll()` và `remove()` không đối số lấy đầu và phục hồi thứ tự ưu tiên: O(log n).
- `remove(Object)` tìm đối tượng cần xóa: O(n).

Với ArrayDeque dùng làm Queue, các thao tác xem/lấy đầu thường có chi phí O(1); hợp đồng hiệu năng tổng quát của lớp mô tả phần lớn thao tác theo thời gian hằng số khấu hao.

Không được coi các mức này là cam kết cho mọi cài đặt Queue. Interface mô tả hành vi; cấu trúc dữ liệu cụ thể quyết định chi phí.

Cũng không có cơ sở chọn peek chỉ vì O(1) nếu bài toán thực sự cần lấy phần tử ra. Nếu đổi poll thành peek mà không xóa ở nơi khác, vòng lặp có thể tiếp tục đọc mãi cùng một đầu.

## 8. Không phương thức nào trong bốn phương thức này tự chờ dữ liệu

`poll()` không đối số trả ngay null khi không có phần tử. `peek()`, `element()` và `remove()` cũng không chờ cho đến khi có dữ liệu.

Nếu bài toán cần chờ công việc từ luồng khác, `BlockingQueue` có các thao tác riêng như `take()` hoặc `poll(timeout, unit)`. Chúng không phải hành vi tự có của `Queue.poll()`.

Với một hàng đợi đồng thời, tránh ghép kiểm tra và lấy thành một giả định nguyên tử:

```java
// Có thể sai giả định nếu luồng khác cũng lấy dữ liệu:
// if (!queue.isEmpty()) {
//     String job = queue.remove();
// }
```

Một luồng khác có thể lấy phần tử cuối sau `isEmpty()`. Nếu dùng một cài đặt hàng đợi an toàn luồng không cho null, một thao tác poll rồi xử lý kết quả thường phù hợp hơn cho yêu cầu “lấy ngay nếu có”.

Tương tự, xem bằng peek rồi gọi poll là hai thao tác riêng; không bảo đảm kết quả poll vẫn là đúng phần tử vừa xem khi có thay đổi đồng thời.

ArrayDeque và PriorityQueue trong chương trình chính không phải hàng đợi an toàn cho truy cập đồng thời không đồng bộ hóa. Đổi cú pháp vòng lặp không tự biến chúng thành cấu trúc an toàn luồng.

## 9. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng peek trong vòng lặp nhưng không xóa | Lặp mãi trên cùng phần tử | Dùng poll nếu mục tiêu là xử lý và lấy ra |
| Gọi remove khi rỗng là tình huống bình thường | Phải dùng ngoại lệ cho luồng điều khiển | Cân nhắc poll và kiểm tra null |
| Bỏ hộp kết quả poll thành int ngay | Có thể ném NullPointerException | Giữ Integer rồi xử lý null |
| Tưởng PriorityQueue là FIFO | Xử lý sai thứ tự | Xác định Comparator/thứ tự tự nhiên |
| Tưởng remove(value) lấy đầu | Xóa phần tử theo giá trị khác | Đọc đúng chữ ký |
| Kiểm tra isEmpty rồi giả định remove chắc chắn thành công | Có thể lỗi khi truy cập đồng thời | Dùng thao tác phù hợp trên hàng đợi an toàn luồng |
| Poll trả null rồi kết luận không bao giờ có thêm dữ liệu | Dừng hệ xử lý quá sớm | Phân biệt rỗng hiện tại với kết thúc nguồn dữ liệu |

Rỗng hiện tại không đồng nghĩa hệ thống đã hoàn thành vĩnh viễn. Trong chương trình một luồng đã nạp xong toàn bộ dữ liệu, poll null có thể là điều kiện kết thúc hợp lệ. Trong hệ sản xuất/tiêu thụ, cần giao thức kết thúc riêng nếu nguồn vẫn có thể thêm công việc.

## 10. Thực hành

1. Thay `fifo.poll()` đầu tiên bằng `fifo.peek()` trong ví dụ. Dự đoán kích thước và phần tử được remove tiếp theo trước khi chạy.
2. Đổi Comparator của PriorityQueue thành `Comparator.reverseOrder()`. Giải thích vì sao đầu chuyển thành số lớn nhất theo giá trị số, dù vẫn là phần tử nhỏ nhất theo Comparator đã chọn.
3. Thêm `priority.remove(Integer.valueOf(20))` trước vòng lặp poll. Phân biệt boolean trả về với giá trị Integer của poll.
4. Viết một vòng lặp xử lý Queue<Integer> không chứa null bằng biến Integer; giải thích vì sao không gán trực tiếp vào int ở điều kiện kết thúc.
5. Chọn đúng cặp thao tác cho hai yêu cầu: “xem trước công việc mà vẫn giữ nguyên hàng đợi” và “nhận ngay một công việc nếu hiện có”. Lần lượt là peek/element theo chính sách rỗng và poll/remove theo chính sách rỗng.

## Tài liệu đối chiếu

- [Queue — Các cặp thao tác xem/lấy và chính sách khi rỗng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Queue.html).
- [PriorityQueue — Thứ tự đầu hàng đợi và độ phức tạp](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PriorityQueue.html).
- [ArrayDeque — Hàng đợi hai đầu, null và truy cập đồng thời](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayDeque.html).
- [BlockingQueue — Các thao tác chờ dữ liệu](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

# Collections.asLifoQueue và view hàng đợi theo LIFO trong Java

## 1. Vấn đề cần giải quyết

Thông thường, một chương trình dùng giao diện `Queue<E>` để gửi các phần tử vào và lấy chúng ra qua `offer`/`poll`. Với hàng đợi FIFO (first in, first out), phần tử vào trước được xử lý trước. Nhưng có những trường hợp vẫn muốn truyền một đối tượng kiểu `Queue<E>` cho API hiện có, trong khi yêu cầu xử lý phần tử **mới đưa vào trước**: LIFO (last in, first out), tương tự ngăn xếp.

`Collections.asLifoQueue(deque)` giải quyết chính xác bài toán tương thích giao diện này. Nó trả về một **view (khung nhìn) kiểu `Queue<E>`** được hỗ trợ bởi một `Deque<E>`: những thao tác đưa phần tử vào qua view được thực hiện ở **đầu deque**, và thao tác lấy phần tử ra cũng lấy ở **đầu deque**.

API này xuất hiện từ Java 6 và **vẫn được hỗ trợ trong Java hiện đại**. Nó hữu ích nhất khi một hàm/thiết kế nhận `Queue<E>`, còn yêu cầu nghiệp vụ lại cần LIFO. Nếu tự mình kiểm soát cả nơi lưu và nơi sử dụng, gọi trực tiếp `Deque.push`/`pop` thường ngắn gọn hơn.

### Phân biệt ba khái niệm

- **`Queue<E>`**: hợp đồng thao tác đưa vào, xem đầu và lấy ra; cách ưu tiên phần tử cụ thể phụ thuộc triển khai.
- **`Deque<E>`**: cấu trúc hai đầu, có thể thêm/xóa ở đầu hoặc cuối; khi làm stack, `push` và `pop` hoạt động ở đầu.
- **LIFO view**: cách sử dụng **cùng một deque** qua giao diện `Queue<E>`; không sao chép hay tạo một hàng đợi dữ liệu độc lập.

## 2. Cách tạo view và cơ chế hoạt động

Chữ ký API:

~~~java
public static <T> Queue<T> asLifoQueue(Deque<T> deque)
~~~

Ví dụ cách khởi tạo:

~~~java
Deque<String> backing = new ArrayDeque<>();
Queue<String> lifo = Collections.asLifoQueue(backing);
~~~

Ở đây, biến `lifo` có kiểu `Queue<String>`, còn `backing` mới giữ các phần tử. Mỗi lần gọi `lifo.offer("x")` sẽ thêm phần tử vào **đầu** `backing`, vì thế `lifo.poll()` lấy phần tử vừa thêm gần nhất qua view trước.

| Thao tác trên `Queue` view | Tác động tương ứng ở `Deque` | Khi rỗng |
| --- | --- | --- |
| `add(e)` | Đưa `e` vào đầu, tương ứng `push(e)`/`addFirst(e)` | Không áp dụng |
| `offer(e)` | Thử đưa `e` vào đầu, tương ứng `offerFirst(e)` | Không áp dụng |
| `remove()` | Lấy và xóa phần tử đầu, tương ứng `pop()`/`removeFirst()` | Ném `NoSuchElementException` |
| `poll()` | Lấy và xóa phần tử đầu, tương ứng `pollFirst()` | Trả về `null` |
| `element()` | Xem phần tử đầu, tương ứng `getFirst()` | Ném `NoSuchElementException` |
| `peek()` | Xem phần tử đầu, tương ứng `peekFirst()` | Trả về `null` |

Với deque có giới hạn dung lượng, `offer(e)` có thể trả `false` nếu không thêm được; `add(e)` có thể ném ngoại lệ khi việc thêm thất bại. `ArrayDeque` thông thường có khả năng tăng dung lượng nên ít gặp tình huống này.

**Điểm then chốt:** `asLifoQueue` đổi ý nghĩa của một số **thao tác thêm/lấy**, nhưng **không đảo ngược thứ tự duyệt**. `iterator()`, `toArray()` và cách hiển thị phần tử vẫn đi từ đầu đến cuối deque. Nếu chỉ muốn nhìn các phần tử theo chiều ngược, sử dụng `descendingIterator()` của `Deque` hoặc `Deque.reversed()` trong Java 21 trở lên; đó là nhu cầu khác với việc chuyển API `Queue` sang LIFO.

## 3. Ví dụ hoàn chỉnh: thay đổi trên hai phía đều được nhìn thấy

Tạo tệp **LifoViewDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.Queue;

public class LifoViewDemo {
    public static void main(String[] args) {
        Deque<String> history = new ArrayDeque<>();
        Queue<String> lifo = Collections.asLifoQueue(history);

        lifo.offer("A");
        lifo.offer("B");
        lifo.add("C");

        System.out.println("backing = " + history);
        System.out.println("peek = " + lifo.peek());
        System.out.println("poll = " + lifo.poll());

        history.addFirst("D");
        System.out.println("view = " + lifo);
        System.out.println("remove = " + lifo.remove());
        System.out.println("remaining = " + history);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac LifoViewDemo.java
java LifoViewDemo
~~~

Kết quả chuẩn:

~~~text
backing = [C, B, A]
peek = C
poll = C
view = [D, B, A]
remove = D
remaining = [B, A]
~~~

Giải thích lần lượt:

1. `offer("A")`, `offer("B")`, `add("C")` đều đẩy vào đầu deque, nên thứ tự từ đầu đến cuối là `[C, B, A]`.
2. `peek()` chỉ đọc `C`; `poll()` lấy và xóa `C`. Đầu deque lúc này là `B`.
3. Gọi `history.addFirst("D")` trực tiếp vẫn làm `lifo` nhìn thấy `D`, do cả hai tham chiếu đến cùng dữ liệu.
4. `lifo.remove()` lấy `D`; còn lại `[B, A]`.

Đây là **view sống** (backed view), không phải snapshot. Nếu một bên thêm, xóa hoặc `clear()`, bên còn lại thấy thay đổi. Mỗi lần gọi `Collections.asLifoQueue` tạo một đối tượng view mới, nhưng không nhân bản dữ liệu của deque.

## 4. Khi truyền cho API chỉ nhận Queue: FIFO và LIFO khác nhau

Hãy hình dung một phương thức tiêu thụ công việc chỉ biết kiểu `Queue<String>`. Chương trình sau đưa cùng chuỗi công việc vào hai hàng đợi, rồi xử lý bằng **cùng một phương thức**.

Tạo tệp **QueueProcessingDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.List;
import java.util.Queue;
import java.util.StringJoiner;

public class QueueProcessingDemo {
    private static String consumeAll(Queue<String> work) {
        StringJoiner result = new StringJoiner(" -> ");
        while (!work.isEmpty()) {
            result.add(work.remove());
        }
        return result.toString();
    }

    public static void main(String[] args) {
        Queue<String> fifo = new ArrayDeque<>();

        Deque<String> storage = new ArrayDeque<>();
        Queue<String> lifo = Collections.asLifoQueue(storage);

        for (String step : List.of("fetch", "validate", "save")) {
            fifo.offer(step);
            lifo.offer(step);
        }

        System.out.println("FIFO: " + consumeAll(fifo));
        System.out.println("LIFO: " + consumeAll(lifo));
    }
}
~~~

Chạy:

~~~bash
javac QueueProcessingDemo.java
java QueueProcessingDemo
~~~

Kết quả:

~~~text
FIFO: fetch -> validate -> save
LIFO: save -> validate -> fetch
~~~

`consumeAll` không phải sửa code hay ép kiểu. Sự khác biệt đến từ **cách triển khai thao tác `Queue`**: `ArrayDeque` dùng trực tiếp như `Queue` thì `offer` thêm ở cuối; view LIFO thì `offer` thêm ở đầu. Cả hai cùng `remove` ở đầu.

**Khi áp dụng thực tế:** chỉ chọn LIFO nếu nghiệp vụ thật sự cho phép ưu tiên phần tử mới hơn (ví dụ, duyệt công việc theo kiểu depth-first hoặc xử lý những tác vụ có thể hoàn nguyên theo thứ tự ngược). Với các bước có ràng buộc bắt buộc thực hiện trước–sau, tự ý đảo sang LIFO sẽ làm sai nghiệp vụ.

## 5. Những trường hợp dễ gây nhầm

### 5.1. `addAll` đẩy từng phần tử vào đầu

Theo hợp đồng API, `addAll` trên LIFO view được thực hiện bằng cách gọi `addFirst` lần lượt cho các phần tử của collection nguồn. Vì vậy các phần tử vừa thêm xuất hiện theo chiều ngược với thứ tự duyệt đầu vào.

Xét đoạn mã sau **đặt bên trong một phương thức Java** (đã import `java.util.*`):

~~~java
Deque<Integer> backing = new ArrayDeque<>(List.of(10, 20, 30));
Queue<Integer> lifo = Collections.asLifoQueue(backing);

lifo.addAll(List.of(40, 50));
System.out.println(backing); // [50, 40, 10, 20, 30]
System.out.println(lifo.peek()); // 50
~~~

Đừng nhầm `lifo.addAll(items)` với `backing.addAll(items)`: thao tác thứ hai trên `ArrayDeque` thêm ở **cuối**, không phải đầu.

### 5.2. LIFO không đồng nghĩa với “đảo iterator”

Sau khi deque chứa `[50, 40, 10, 20, 30]`, duyệt `lifo` bằng `for (var e : lifo)` sẽ bắt đầu với `50`, rồi `40`, `10`, `20`, `30`. View trả về các phần tử theo thứ tự **đang có trong deque**, không tự đảo chiều lần nữa. Phương thức `reversed()` (Java 21+) được thiết kế cho **reverse-ordered view**, còn `asLifoQueue` dành cho **LIFO qua hợp đồng Queue**.

### 5.3. `remove()` khác `remove(Object)`

- `lifo.remove()` không tham số: lấy và xóa **phần tử đầu**, ném ngoại lệ nếu rỗng.
- `lifo.remove("B")`: tìm và xóa một phần tử bằng `"B"` theo quy tắc của collection; không có nghĩa “pop phần tử mới nhất”. Trong deque có giá trị trùng, thao tác loại bỏ theo giá trị thường tìm lần xuất hiện đầu tiên từ đầu deque.

Tương tự, `poll()` dùng khi chấp nhận trường hợp rỗng bằng kết quả `null`; `remove()`/ `element()` thích hợp khi rỗng là sai điều kiện chương trình và cần phát hiện bằng ngoại lệ.

### 5.4. `Deque` và view có thể nhận lệnh thêm ở hai đầu khác nhau

Nếu viết `lifo.offer("X")`, phần tử vào **đầu**. Nếu viết `backing.offer("Y")` trực tiếp trên `ArrayDeque`, phần tử vào **cuối**. Cùng một backing deque có thể nhận thao tác từ cả hai phía; điều này hợp lệ, nhưng người đọc code cần biết đường thêm nào đang được dùng. Không nên trộn hai cách thêm khi toàn bộ thuật toán giả định mọi phần tử mới luôn ở đỉnh stack.

### 5.5. View không tạo thêm các bảo đảm khác

- **Không sao chép:** view phản ánh mọi thay đổi từ backing deque, kể cả `clear` và các thao tác xóa.
- **Không tự đồng bộ hóa:** với backing `ArrayDeque`, các thao tác từ nhiều luồng phải được điều phối thích hợp. Nếu cần truy cập đồng thời, hãy chọn backing deque có hợp đồng concurrent phù hợp và xem lại yêu cầu nhất quán của thuật toán.
- **Không cho phép `null` chỉ vì dùng `Queue`:** `ArrayDeque` cấm phần tử `null`, và `peek`/`poll` dùng `null` làm tín hiệu rỗng. Quy tắc nhận phần tử phụ thuộc deque được bọc.
- **Không thay đổi kiểu trả về:** view là `Queue<E>`; không ép kiểu nó thành `Deque<E>` để gọi `push` hoặc `addFirst`. Khi cần chức năng hai đầu, giữ tham chiếu `Deque<E>` ban đầu.
- **Không tự bảo đảm thứ tự ưu tiên khác LIFO:** nếu cần xếp hạng theo độ ưu tiên hoặc theo thời điểm, hãy chọn cấu trúc/phương pháp phù hợp với hợp đồng yêu cầu.

### 5.6. Hiệu năng phụ thuộc backing deque

Với `ArrayDeque`, thêm/xóa/xem ở đầu thường có độ phức tạp thời gian trung bình phân bổ **O(1)**; việc tạo view không sao chép toàn bộ phần tử. Các thao tác duyệt, tìm kiếm hoặc xóa theo giá trị có thể tốn **O(n)**. Không suy ra các con số này cho mọi `Deque` tùy ý: đặc tính thật sự phụ thuộc triển khai backing.

## 6. Cách chọn API trong Java hiện đại

| Tình huống | Cách làm thích hợp |
| --- | --- |
| Hàm nhận `Queue<E>`, nhưng phải xử lý phần tử mới nhất trước | `Collections.asLifoQueue(deque)` |
| Toàn bộ code của bạn thao tác kiểu stack | Dùng `Deque<E>` và `push`/`pop` trực tiếp |
| Cần hàng đợi FIFO | Dùng `Queue<E>` với triển khai FIFO, chẳng hạn `ArrayDeque` |
| Cần duyệt deque theo thứ tự ngược | `descendingIterator()`; hoặc `reversed()` từ Java 21 |
| Nhiều luồng cùng đưa/lấy phần tử | Chọn triển khai deque concurrent đáp ứng yêu cầu, sau đó đánh giá việc dùng view |

**Quy tắc thực hành:** hãy thể hiện rõ trong tên biến và tài liệu của phương thức nhận `Queue` rằng luồng xử lý cần LIFO. Đây là một lựa chọn **thứ tự xử lý nghiệp vụ**, không phải tối ưu tự động cho mọi bài toán.

## 7. Tự kiểm tra hiểu biết

Xét:

~~~java
Deque<Integer> deque = new ArrayDeque<>();
Queue<Integer> queue = Collections.asLifoQueue(deque);

queue.offer(1);
deque.addLast(2);
queue.offer(3);
System.out.println(queue.poll());
System.out.println(deque);
~~~

**Đáp án:** dòng đầu in `3`, dòng sau in `[1, 2]`. Hai lần `queue.offer` chèn vào đầu, `deque.addLast(2)` chèn vào cuối. Trước khi `poll`, deque là `[3, 1, 2]`; `poll` loại phần tử ở đầu.

Kiểm tra cuối bài:

1. Có cần copy deque trước khi dùng `asLifoQueue`? **Không**; đây là view trên cùng dữ liệu.
2. `lifo.offer` thêm phần tử vào đâu? **Đầu deque**.
3. `lifo.poll` trả gì khi rỗng? **`null`**; trong khi `remove()` ném `NoSuchElementException`.
4. `asLifoQueue` có đảo chiều `iterator` không? **Không**; nó đổi hành vi thao tác chứ không đảo encounter order.
5. Khi nào không cần adapter này? Khi code chủ động làm việc với `Deque` và có thể gọi `push`/`pop` trực tiếp.

## 8. Tài liệu API chính thức (đang áp dụng)

- [Java SE 25 — Collections.asLifoQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#asLifoQueue(java.util.Deque))
- [Java SE 25 — Deque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html)
- [Java SE 25 — ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html)

Các ví dụ độc lập ở mục 3–4 dùng JDK 17+; phần nói về `Deque.reversed()` chỉ áp dụng từ JDK 21. Những giải thích còn lại dựa trên hợp đồng `asLifoQueue` và `Deque` hiện hành.

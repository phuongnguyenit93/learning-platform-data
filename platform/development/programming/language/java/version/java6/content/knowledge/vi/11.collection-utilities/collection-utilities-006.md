# Quan hệ thay đổi giữa queue view và Deque gốc

## 1. Hai cách thao tác trên cùng một Deque

Trong Java, `Deque<E>` là hàng đợi hai đầu: có thể thêm, đọc và xóa phần tử ở đầu (head) hoặc cuối (tail). Khi một API chỉ nhận `Queue<E>` nhưng ta cần thứ tự LIFO (*Last In, First Out*: vào sau, ra trước), có thể dùng `Collections.asLifoQueue(Deque)`:

~~~java
Deque<String> deque = new ArrayDeque<>();
Queue<String> lifoView = Collections.asLifoQueue(deque);
~~~

`lifoView` là **queue view được chống lưng bởi chính `deque`** (backed view). Phương thức này **không sao chép các phần tử**, không tạo kho dữ liệu riêng và không yêu cầu làm mới view. Hai tham chiếu dùng chung một trạng thái của cùng deque:

- **Sửa qua queue view → Deque gốc đổi:** `lifoView.add(x)` chèn `x` ở **đầu deque**; `lifoView.poll()` lấy và xóa phần tử ở đầu; `lifoView.clear()` làm rỗng deque gốc.
- **Sửa trực tiếp Deque gốc → view quan sát được:** `deque.addFirst(x)` làm `lifoView.peek()` trả về `x`; `deque.removeLast()` làm giảm kích thước mà `lifoView.size()` nhìn thấy.
- **Thứ tự duyệt không tự đảo:** iterator của queue view vẫn đi từ đầu đến cuối deque. Tính LIFO đến từ vị trí **thêm/lấy** phần tử, không đến từ việc đảo iterator.

Ví dụ, ký hiệu `[A, B]` mô tả các phần tử từ **head → tail**:

~~~text
deque ban đầu          [A, B]
view.add(C)            [C, A, B]       // chèn ở đầu
deque.addFirst(D)      [D, C, A, B]    // sửa trực tiếp Deque
view.peek()            D
view.poll()            D               // lấy và xóa đầu
deque còn lại          [C, A, B]
~~~

Không tồn tại bước `refresh()` hay `sync()` giữa view và deque: mỗi thao tác đọc trạng thái của deque gốc tại thời điểm thực hiện (với các ràng buộc đồng bộ luồng thông thường).

## 2. Không nhầm Queue trực tiếp trên Deque với queue view LIFO

`Deque` kế thừa `Queue`. Tuy nhiên, khi gọi các phương thức `Queue` **trực tiếp trên một deque**, `deque.add(e)` thêm vào **cuối**, còn `deque.remove()` lấy phần tử **đầu** (cách dùng FIFO). View LIFO thay đổi ý nghĩa thao tác thêm: `lifoView.add(e)` thêm vào **đầu**. Vì vậy, cùng tên phương thức `add` nhưng thực thi trên hai tham chiếu cho kết quả khác nhau.

| Gọi trên `lifoView` | Tác động tương ứng lên `deque` |
| --- | --- |
| `add(e)` | `push(e)` = `addFirst(e)` |
| `offer(e)` | `offerFirst(e)` |
| `remove()` | `pop()` = `removeFirst()` |
| `poll()` | `pollFirst()` |
| `element()` | `getFirst()` |
| `peek()` | `peekFirst()` |
| `addAll(items)` | Lần lượt `addFirst(e)` cho từng phần tử theo thứ tự duyệt `items` |
| `size()`, `isEmpty()`, `contains(o)` | Quan sát chính deque nền |
| `remove(o)`, `clear()` | Xóa trên chính deque nền |
| `iterator()` | Duyệt từ head đến tail, **không đảo thứ tự** |

**Lưu ý về khả năng thêm:** `ArrayDeque` thường không giới hạn sức chứa nên thao tác thêm thường thành công. Nếu deque nền có giới hạn sức chứa, `offer(e)` có thể trả `false`, còn `add(e)` có thể ném ngoại lệ khi không thể chèn. View không làm mất các ràng buộc của deque nền.

**Quy tắc để giữ đúng LIFO:** khi đưa công việc mới vào cùng luồng xử lý, thống nhất dùng `lifoView.add/offer` hoặc `deque.push/addFirst`; khi lấy dùng `lifoView.poll/remove` hoặc `deque.pop/removeFirst`. Nếu đồng thời có lời gọi `deque.addLast(e)`, công việc mới thêm ở cuối **không nhất thiết được lấy trước** bằng `lifoView.poll()`.

## 3. Chương trình Java hoàn chỉnh: thay đổi theo hai chiều

Đoạn mã dưới đây dùng các API còn được hỗ trợ trên JDK hiện hành, biên dịch/chạy được với **Java 17+**. Lưu thành tệp `LifoQueueViewDemo.java`:

~~~java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Collections;
import java.util.Deque;
import java.util.Queue;

public class LifoQueueViewDemo {
    public static void main(String[] args) {
        Deque<String> deque = new ArrayDeque<>();
        deque.addLast("A");
        deque.addLast("B");
        Queue<String> lifo = Collections.asLifoQueue(deque);

        System.out.println("Ban dau deque: " + deque);
        System.out.println("Ban dau view: " + lifo);

        lifo.add("C");
        System.out.println("Sau view.add(C): " + deque);

        deque.addFirst("D");
        System.out.println("Sau deque.addFirst(D), view.peek(): " + lifo.peek());
        System.out.println("view.poll(): " + lifo.poll());
        System.out.println("Deque sau view.poll(): " + deque);

        deque.removeLast();
        System.out.println("Sau deque.removeLast(), view: " + lifo);

        lifo.clear();
        System.out.println("Sau view.clear(), deque rong: " + deque.isEmpty());

        lifo.addAll(Arrays.asList("X", "Y", "Z"));
        System.out.println("Sau view.addAll(X,Y,Z), deque: " + deque);
        System.out.println("Lan luot poll: " + lifo.poll() + ", " + lifo.poll() + ", " + lifo.poll());
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~text
javac LifoQueueViewDemo.java
java LifoQueueViewDemo
~~~

Kết quả (đã đối chiếu bằng cách biên dịch và thực thi trên JDK):

~~~text
Ban dau deque: [A, B]
Ban dau view: [A, B]
Sau view.add(C): [C, A, B]
Sau deque.addFirst(D), view.peek(): D
view.poll(): D
Deque sau view.poll(): [C, A, B]
Sau deque.removeLast(), view: [C, A]
Sau view.clear(), deque rong: true
Sau view.addAll(X,Y,Z), deque: [Z, Y, X]
Lan luot poll: Z, Y, X
~~~

**Diễn giải từng bước:**

1. Sau khi tạo view, hai đối tượng in ra cùng `[A, B]` vì các phần tử nằm trong cùng deque.
2. `lifo.add("C")` ghi vào đầu deque: biến `deque` quan sát ngay `[C, A, B]`.
3. `deque.addFirst("D")` sửa từ phía deque gốc: `lifo.peek()` thấy `D`; `lifo.poll()` trả `D` và xóa nó khỏi deque.
4. `deque.removeLast()` xóa `B`; view giờ chỉ có `[C, A]`. `lifo.clear()` tiếp tục làm deque gốc rỗng.
5. `lifo.addAll([X, Y, Z])` chèn `X`, sau đó `Y`, rồi `Z` vào **đầu**. Bởi vậy deque có `[Z, Y, X]` và các lần `poll()` trả `Z`, `Y`, `X`.

`addAll` là chuỗi các lần thêm đầu, **không phải** thao tác nối toàn bộ danh sách vào cuối như queue FIFO. Không giả định `addAll` là giao dịch nguyên tử: nếu việc chèn một phần tử thất bại sau vài lần chèn thành công, deque có thể đã bị thay đổi một phần.

## 4. Các kiểu thay đổi mà view cùng quan sát

### Thêm/xóa và kích thước

Sau `deque.addFirst("Q")`, `lifoView.peek()` cho `Q`. Sau `lifoView.remove("Q")`, phần tử `Q` bị xóa khỏi deque nền. `size()` và `isEmpty()` của view phản ánh trạng thái hiện có của deque; chúng không dùng bộ đếm riêng.

`lifoView.clear()` tác động lên toàn deque; `lifoView.remove(o)` xóa phần tử phù hợp trong deque (nếu có). Nếu dùng `Iterator.remove()` đúng hợp đồng của iterator, phần tử bị xóa cũng biến mất khỏi deque nền.

### Đọc trên queue rỗng

Khi view rỗng, `poll()` và `peek()` trả `null`; `remove()` và `element()` ném `NoSuchElementException`. `ArrayDeque` không cho phép lưu `null`, vì vậy `null` từ `peek/poll` trong ví dụ này là dấu hiệu rỗng. View không thay đổi quy định về phần tử hợp lệ của deque gốc.

### LIFO không đồng nghĩa đảo thứ tự duyệt

Nếu deque đang chứa `[A, B, C]` (head → tail), vòng lặp qua `lifoView` vẫn đọc `A` rồi `B` rồi `C`, giống `deque.iterator()`. Việc thêm phần tử qua view tạo LIFO là do nó chèn vào head. Đây là khác biệt giữa **thứ tự thao tác queue** và **thứ tự encounter/iteration**. Nếu cần một view đảo thứ tự duyệt, `Deque.reversed()` là API khác (có từ Java 21), không phải ý nghĩa của `Collections.asLifoQueue`.

### Thay đổi lúc đang duyệt hoặc giữa nhiều luồng

Với `ArrayDeque`, tránh sửa deque từ một lối gọi khác trong khi iterator của view đang duyệt rồi trông đợi kết quả ổn định. Iterator có thể phát hiện sửa đổi và ném `ConcurrentModificationException` ở mức best effort; không nên dùng đặc tính này làm cơ chế đồng bộ.

`Collections.asLifoQueue` **không bổ sung tính thread-safe**. `ArrayDeque` không tự an toàn cho nhiều luồng ghi/đọc đồng thời. Khi thực sự cần chia sẻ giữa nhiều luồng, phải lựa chọn cấu trúc deque có đặc tính đồng thời phù hợp và thiết kế đồng bộ cho các chuỗi thao tác; view không khiến nhiều lời gọi riêng lẻ thành một thao tác nguyên tử.

## 5. Backed view khác bản sao độc lập

Giả sử deque hiện chứa `[A, B]`:

- `Queue<String> view = Collections.asLifoQueue(deque);` tạo **view dùng chung dữ liệu**. `view.add("C")` khiến deque thành `[C, A, B]`; `deque.clear()` khiến view rỗng.
- `Deque<String> copy = new ArrayDeque<>(deque);` tạo **Deque có cấu trúc lưu phần tử riêng** tại thời điểm sao chép. Việc thêm/xóa phần tử trong `copy` không tự thêm/xóa ở deque gốc và ngược lại. Đây vẫn là sao chép nông: bản thân đối tượng phần tử có thể được tham chiếu chung nếu là kiểu có thể sửa.

View gắn với **đối tượng deque đã truyền vào hàm**, chứ không gắn với tên biến. Gán biến `deque` trỏ sang một deque mới sau đó không khiến view chuyển sang deque mới.

## 6. Khi nào dùng và những lỗi dễ mắc

**Nên dùng `asLifoQueue`** khi một API/thư viện nhận `Queue<E>` nhưng ta cần xử lý phần tử vừa đưa vào trước, đồng thời muốn các thao tác qua queue cùng thay đổi deque mà phần khác của chương trình đang giữ. Nếu API của chính bạn đã nhận `Deque<E>`, có thể gọi `push()/pop()` trực tiếp mà không cần adapter.

Các lỗi thường gặp:

1. **Tưởng view là bản copy:** thực tế mọi thay đổi qua view được ghi vào deque gốc và ngược lại.
2. **Tưởng `deque.add(e)` giống `view.add(e)`:** deque trực tiếp thêm ở tail (FIFO), view thêm ở head (LIFO).
3. **Tưởng iterator của view tự đảo:** iterator vẫn theo head → tail; LIFO là quy ước thêm/lấy từ head.
4. **Trộn `deque.addLast(e)` vào luồng LIFO:** thêm ở cuối có thể làm thứ tự lấy không còn “mới nhất trước” trên toàn bộ sự kiện thêm.
5. **Tưởng wrapper bảo vệ đồng thời:** không có đồng bộ mới; nhiều thao tác liên tiếp cũng không tự bảo đảm nguyên tử.
6. **Tưởng `Queue<E>` có mọi phương thức của `Deque<E>`:** kiểu trả về của `asLifoQueue` là `Queue<E>`. Muốn gọi `addFirst`, `addLast` hay `descendingIterator` thì dùng tham chiếu `Deque` gốc.

## 7. Tự kiểm tra

Khởi tạo deque `[A, B]`, tạo `view = Collections.asLifoQueue(deque)`, sau đó lần lượt gọi:

~~~java
view.add("C");
deque.addLast("D");
String result = view.poll();
~~~

**Hỏi:** `result` là gì và deque còn gì?

**Đáp:** `result` bằng `"C"` và deque còn `[A, B, D]`. `C` được thêm vào đầu nên bị lấy trước; `D` thêm ở cuối nên không đứng ở đầu queue view. Nếu gọi tiếp `view.clear()`, deque gốc sẽ rỗng.

**Kết luận cần nhớ:** `Collections.asLifoQueue(deque)` cho một **LIFO Queue view sống trên đúng deque ấy**. Sửa qua view ảnh hưởng deque; sửa deque ảnh hưởng view. Hiểu chính xác phép thêm/xóa ở **đầu hay cuối** là chìa khóa để dự đoán kết quả và giữ đúng thứ tự xử lý.

### Tài liệu tham khảo (API vẫn được hỗ trợ)

- [Java SE API: `Collections.asLifoQueue(Deque)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#asLifoQueue(java.util.Deque)).
- [Java SE API: `Deque` và quan hệ với `Queue`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html).

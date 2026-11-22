# Thiết kế hàng đợi và ngăn xếp bằng ArrayDeque trong Java

## 1. Bài toán và mục tiêu thực hành

Khi xử lý công việc theo **thứ tự đến trước làm trước**, ta cần một **hàng đợi (queue, FIFO)**. Khi muốn lấy phần tử **mới được đưa vào gần nhất**, ta cần **ngăn xếp (stack, LIFO)**. Java có class `java.util.ArrayDeque<E>` triển khai interface `Deque<E>` (double-ended queue): cho phép thao tác ở cả đầu lẫn cuối, vì vậy chỉ một implementation có thể làm hai nhiệm vụ.

Bài học này là một bài **thực hành Java**. Các mục tiêu cụ thể:

1. Khai báo đúng interface `Queue<E>` khi ứng dụng chỉ cần FIFO và `Deque<E>` khi cần stack hoặc hai đầu.
2. Dùng `offer/poll/peek` để thiết kế FIFO và `push/pop/peek` để thiết kế LIFO.
3. Xử lý queue/stack rỗng, exceptions và quy tắc không chèn `null`.
4. Hiểu `ArrayDeque` là mảng tự mở rộng, không phải hàng đợi có giới hạn dung lượng.
5. Đánh giá độ phức tạp, iterator và thao tác ở hai đầu.
6. Áp dụng vào BFS, DFS, kiểm dấu ngoặc và sliding-window maximum.
7. Tạo history undo/redo bằng hai stacks, tránh lỗi redo sau khi tạo nhánh mới.
8. Xây bounded queue **đơn luồng**, rồi so sánh với `LinkedBlockingDeque` khi có nhiều threads.
9. Biên dịch và chạy **ba chương trình Java 17+ hoàn chỉnh** có assertions và stdout đã được xác minh.

Các API `ArrayDeque`, `Deque` và `Queue` đã có từ lâu nhưng **vẫn đang được Java 17–26 hỗ trợ**. Đây là kiến thức hiện hành, không dựa vào cơ chế legacy. JavaDoc `Deque` khuyến nghị dùng interface này thay cho class `Stack` kiểu cũ trong code LIFO mới. Điều đó **không** có nghĩa class `Stack` đã bị xóa khỏi JDK.

## 2. FIFO và LIFO khác nhau ở đâu?

Một deque có hai đầu:

~~~text
                FRONT / HEAD                  BACK / TAIL
                     |                             |
                     v                             v
                  +----+----+----+----+----+----+
                  | A  | B  | C  | D  | E  | F  |
                  +----+----+----+----+----+----+
                     ^                             ^
                pollFirst()                  offerLast(x)
                addFirst(x)                  pollLast()
~~~

Hình vẽ biểu diễn **thứ tự logic**. Không cần biết chỉ số mảng nội bộ hoặc vị trí wrap-around mới dùng được API.

**FIFO — First In, First Out:**

~~~text
offer("A")  -> [A]
offer("B")  -> [A, B]
offer("C")  -> [A, B, C]
peek()      -> A       deque vẫn là [A, B, C]
poll()      -> A       deque thành [B, C]
poll()      -> B       deque thành [C]
poll()      -> C       deque thành []
poll()      -> null    không còn phần tử
~~~

Phần tử được đưa vào **cuối**, lấy ra từ **đầu**.

**LIFO — Last In, First Out:**

~~~text
push("save1") -> [save1]
push("save2") -> [save2, save1]
push("save3") -> [save3, save2, save1]
peek()        -> save3    không xóa
pop()         -> save3    còn [save2, save1]
pop()         -> save2    còn [save1]
pop()         -> save1    còn []
~~~

Phần tử được **push ở đầu** và cũng được **pop ở đầu**, vì vậy lần cuối vào sẽ ra trước. Cùng một method `peek()` đọc **đầu deque**, nhưng khi dùng như FIFO đó là phần tử cũ nhất còn chờ; khi dùng như LIFO đó là phần tử vừa push gần nhất.

### 2.1. Ba interface/class cần phân biệt

~~~java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Queue;

Queue<String> pending = new ArrayDeque<>();
Deque<String> undo = new ArrayDeque<>();
~~~

Đây là **snippet khai báo**, các source files độc lập có `main` nằm phía sau.

- `Queue<E>` định nghĩa enqueue/dequeue/inspect theo FIFO.
- `Deque<E>` extends `Queue<E>` và cung cấp thêm các phương thức đầu/cuối, stack operations.
- `ArrayDeque<E>` là một implementation dựa trên resizable array, không thread-safe, không chấp nhận null.
- Đặt biến với type interface thường tốt hơn gắn caller chặt với class `ArrayDeque`, giúp thay implementation nếu cần bounded hoặc concurrent behavior.

## 3. Bảng phương thức FIFO đầy đủ

| Nhu cầu | API nên dùng khi “rỗng/không thêm được” là trạng thái bình thường | API ném exception trong tình huống tương ứng |
| --- | --- | --- |
| Thêm một phần tử vào cuối | `offer(e)` → boolean | `add(e)` |
| Lấy/xóa phần tử đầu | `poll()` → null khi rỗng | `remove()` → `NoSuchElementException` khi rỗng |
| Xem phần tử đầu, không xóa | `peek()` → null khi rỗng | `element()` → `NoSuchElementException` khi rỗng |
| Thêm trực tiếp vào cuối deque | `offerLast(e)` | `addLast(e)` |
| Lấy từ đầu deque | `pollFirst()` | `removeFirst()` |
| Xem đầu deque | `peekFirst()` | `getFirst()` |

Với một `Deque`, các cặp tương đương: `offer(e)==offerLast(e)` về vị trí, `poll()==pollFirst()`, `peek()==peekFirst()`, `remove()==removeFirst()` và `element()==getFirst()`.

~~~java
Queue<String> queue = new ArrayDeque<>();
queue.offer("ticket-1");
queue.offer("ticket-2");

System.out.println(queue.peek()); // ticket-1
System.out.println(queue.poll()); // ticket-1
System.out.println(queue.poll()); // ticket-2
System.out.println(queue.poll()); // null
~~~

Đây là snippet hoạt động trong một method Java, không phải một file độc lập. Khi queue rỗng, `poll()` trả null; không cần try/catch `NoSuchElementException` nếu rỗng là tình huống đã dự kiến.

### 3.1. `offer` khác `add` ở contract

Interface `Queue` có cả hai vì có các queue bị giới hạn capacity. Khi không thể chèn ngay vì hết chỗ:

- `offer(e)` có thể báo `false`.
- `add(e)` có thể ném `IllegalStateException`.

Nhưng `ArrayDeque` **không có hard maximum capacity** theo constructor; nó tăng backing storage khi cần. Vì vậy với một element hợp lệ, `offer` trên `ArrayDeque` không phải cơ chế backpressure, và không tự trả false chỉ vì đạt mức initial capacity. Nếu cấp phát bộ nhớ thất bại thì hành vi có thể là lỗi tài nguyên, không phải một giới hạn queue được thiết kế.

### 3.2. `remove()` và `remove(Object)` là hai thao tác khác nhau

~~~java
Queue<String> queue = new ArrayDeque<>();
queue.offer("A");
queue.offer("B");

queue.remove();       // Lấy/xóa A ở đầu.
queue.remove("B");    // Tìm B ở giữa/cuối rồi xóa nếu có.
~~~

Method `remove()` không đối số xử lý **head**; method `remove(Object)` tìm theo equals và có thể mất O(n). Không đánh đồng hai overload khi phân tích hiệu năng.

## 4. Bảng phương thức LIFO

Khai báo:

~~~java
Deque<Integer> stack = new ArrayDeque<>();
stack.push(10);
stack.push(20);
stack.push(30);
~~~

Các operations:

| Nhiệm vụ | Method | Tương đương ở Deque | Trường hợp rỗng |
| --- | --- | --- | --- |
| Push lên đỉnh | `push(e)` | `addFirst(e)` | Element hợp lệ được chèn |
| Pop đỉnh | `pop()` | `removeFirst()` | Ném `NoSuchElementException` |
| Xem đỉnh | `peek()` | `peekFirst()` | Trả null |
| Lấy đỉnh nhưng không throw | `pollFirst()` | `poll()` | Trả null |
| Xem đỉnh, rỗng là lỗi | `getFirst()` | `element()` | Ném `NoSuchElementException` |

Trong ví dụ, lần lượt `stack.pop()` sẽ trả 30, 20, 10. `stack.peek()` trước khi pop sẽ trả 30 nhưng không giảm `size()`.

**Quy tắc thiết kế:** Nếu đang dùng deque làm stack, đừng tùy tiện chèn thêm bằng `offerLast` rồi vẫn kỳ vọng thứ tự LIFO. Duy trì một “đỉnh stack” thống nhất: `push/pop` ở đầu.

### 4.1. `isEmpty` và phép lấy phần tử

Trong code đơn luồng:

~~~java
if (!stack.isEmpty()) {
    Integer next = stack.pop();
    System.out.println(next);
}
~~~

Nếu stack có thể bị một thread khác thay đổi, sequence `isEmpty` rồi `pop` không atomic. Nhưng quan trọng hơn, bản thân `ArrayDeque` **không thread-safe**, nên không được chia sẻ không đồng bộ giữa threads. Các giải pháp concurrent được giải thích ở phần sau.

## 5. Hai đầu deque: vì sao không phải lúc nào cũng là queue hoặc stack?

`Deque` có thể làm nhiều hơn FIFO/LIFO:

| Tác vụ | Phía trước | Phía sau |
| --- | --- | --- |
| Thêm | `addFirst(e)` / `offerFirst(e)` | `addLast(e)` / `offerLast(e)` |
| Xóa/lấy và trả null nếu rỗng | `pollFirst()` | `pollLast()` |
| Xóa/lấy, throw nếu rỗng | `removeFirst()` | `removeLast()` |
| Xem, trả null nếu rỗng | `peekFirst()` | `peekLast()` |
| Xem, throw nếu rỗng | `getFirst()` | `getLast()` |

~~~java
Deque<Integer> deque = new ArrayDeque<>();
deque.addFirst(1);
deque.addLast(2);
deque.addFirst(0);
deque.addLast(3);

System.out.println(deque);           // [0, 1, 2, 3]
System.out.println(deque.peekFirst()); // 0
System.out.println(deque.peekLast());  // 3
System.out.println(deque.pollFirst()); // 0
System.out.println(deque.pollLast());  // 3
System.out.println(deque);           // [1, 2]
~~~

Thứ tự iterate mặc định là **front → back**. Khi cần duyệt ngược dùng `descendingIterator()`:

~~~java
Deque<String> values = new ArrayDeque<>(
        java.util.List.of("A", "B", "C"));
java.util.Iterator<String> it = values.descendingIterator();
while (it.hasNext()) {
    System.out.println(it.next()); // C, B, A (mỗi dòng).
}
~~~

`ArrayDeque` không phải `List`: không có indexed `get(i)` hay `set(i,value)` để truy cập random access. Nếu bài toán chủ yếu cần vị trí i, chọn cấu trúc phù hợp như `ArrayList`.

## 6. Empty, null và exceptions — hợp đồng quan trọng

`ArrayDeque` **cấm chèn null**:

~~~java
Deque<String> d = new ArrayDeque<>();
d.offer(null); // NullPointerException.
~~~

Lý do thực dụng: nhiều API của `Deque` trả null để báo **không có phần tử**. Nếu null cũng là một phần tử hợp lệ, code không thể phân biệt “lấy được null” với “deque rỗng” qua `poll` hoặc `peek`.

| Tình huống | Kết quả |
| --- | --- |
| `new ArrayDeque<String>().peek()` | null |
| `new ArrayDeque<String>().poll()` | null |
| `new ArrayDeque<String>().peekFirst()` | null |
| `new ArrayDeque<String>().pollLast()` | null |
| `new ArrayDeque<String>().remove()` | `NoSuchElementException` |
| `new ArrayDeque<String>().pop()` | `NoSuchElementException` |
| `new ArrayDeque<String>().offer(null)` | `NullPointerException` |
| `new ArrayDeque<String>().push(null)` | `NullPointerException` |

Nếu cần “poison pill” báo consumer dừng, dùng một event/command object có type rõ ràng, không dùng null. Nếu empty là điều bình thường, dùng `poll`/`peek`. Nếu empty đại diện bug của thuật toán, `pop`/`remove` giúp fail fast.

### 6.1. Đừng chuyển lỗi rỗng thành giá trị giả

Ví dụ anti-pattern:

~~~java
int next = 0;
try {
    next = stack.pop();
} catch (java.util.NoSuchElementException ignored) {
    // Sai nếu 0 là một giá trị nghiệp vụ thực sự.
}
~~~

Đây là snippet mô tả code **không nên dùng**. Một queue rỗng không có nghĩa kết quả số 0; định nghĩa trạng thái rõ ràng hoặc để exception chỉ ra bug logic.

## 7. Initial capacity không phải maximum capacity

~~~java
ArrayDeque<Integer> deque = new ArrayDeque<>(2);
for (int i = 0; i < 128; i++) {
    deque.offerLast(i);
}
System.out.println(deque.size()); // 128
~~~

Với `new ArrayDeque<>(2)`, tham số 2 chỉ là **initial capacity hint**, không phải giới hạn 2 elements. `ArrayDeque` tự mở rộng mảng khi cần đến giới hạn bộ nhớ. Vì vậy:

- Không dùng constructor capacity để thực thi “chỉ nhận tối đa N jobs”.
- Không dựa vào một growth factor hoặc exact internal array length của một bản JDK.
- Không coi `offerLast` trả false khi queue đầy, vì ArrayDeque không có giới hạn logic cố định.
- Không có public method `ensureCapacity` giống `ArrayList`.
- Nếu producer quá nhanh và không có consumer/backpressure, bộ nhớ có thể tăng không kiểm soát.

Muốn bounded single-thread queue, cần kiểm size trước khi chèn và bao bằng interface. Muốn bounded multi-thread queue, dùng `ArrayBlockingQueue` hoặc `LinkedBlockingDeque` tùy cần FIFO hay hai đầu.

## 8. Chi phí và đặc tính bộ nhớ

`ArrayDeque` là resizable-array deque; **hầu hết phép thêm/xóa/xem ở đầu/cuối** có chi phí amortized O(1). Có thể có một lần resize O(n), nhưng phân bổ qua chuỗi thao tác thì trung bình O(1).

| Operation | Chi phí điển hình | Giải thích |
| --- | --- | --- |
| `offerLast / addLast` | O(1) amortized | Có thể resize |
| `offerFirst / addFirst / push` | O(1) amortized | Chèn đầu |
| `pollFirst / removeFirst / pop` | O(1) | Xóa đầu |
| `pollLast / removeLast` | O(1) | Xóa cuối |
| `peekFirst / peekLast` | O(1) | Chỉ xem |
| `size / isEmpty` | O(1) | Không cần quét |
| `contains(value)` | O(n) | Tìm tuyến tính |
| `removeFirstOccurrence / removeLastOccurrence` | O(n) | Tìm và dịch chuyển khi cần |
| `remove(Object)` | O(n) | Không giống `remove()` |
| Duyệt tất cả phần tử | O(n) | N phần tử |
| `Iterator.remove` | Có thể O(n) | Xóa ở vị trí không phải endpoint |
| Bulk operations | Có thể O(n) hoặc hơn theo input | Xét từng operation cụ thể |
| Index-based `get(i)` | Không có API | Chọn List nếu cần |

ArrayDeque thường có locality tốt hơn linked nodes và JavaDoc nhận xét nó **có xu hướng nhanh hơn Stack khi làm stack, LinkedList khi làm queue**, nhưng không phải performance guarantee tuyệt đối. Benchmark theo JDK, kích thước, memory pressure, pattern thao tác và GC trước khi tối ưu cho production.

`ArrayDeque` dùng internal array/circular indexing theo implementation; application code **không được phụ thuộc** private head/tail indices hoặc chi tiết tăng capacity. `clear()` xóa elements logic nhưng không nên coi là một lời hứa thu nhỏ backing array về initial capacity.

## 9. Iterator, equality và tránh dùng fail-fast làm concurrency control

~~~java
Deque<String> colors = new ArrayDeque<>(
        java.util.List.of("red", "green", "blue"));
java.util.Iterator<String> it = colors.iterator();
while (it.hasNext()) {
    if ("green".equals(it.next())) {
        it.remove();
    }
}
// colors là [red, blue].
~~~

`Iterator.remove()` xóa phần tử vừa được iterator trả về trong một vòng duyệt hợp lệ. Tránh tự sửa `colors.remove(...)` trong `for-each` đang chạy; iterator có thể phát hiện concurrent structural modification và ném `ConcurrentModificationException`.

**Cảnh báo:** Fail-fast là **best effort**. Nó không được bảo đảm khi có unsynchronized concurrent modification và không phải “khóa tự động”. Không dùng việc **không** thấy ConcurrentModificationException làm bằng chứng code thread-safe.

### 9.1. So sánh hai deque có cùng nội dung

Không viết:

~~~java
boolean same = new ArrayDeque<>(java.util.List.of(1, 2))
        .equals(new ArrayDeque<>(java.util.List.of(1, 2)));
~~~

rồi kỳ vọng `same==true` theo semantics `List.equals`. `ArrayDeque` không mặc định có element-wise sequence equality; JavaDoc `Deque` lưu ý implementations thường kế thừa identity-based equals/hashCode từ Object. Khi cần so nội dung theo thứ tự, lấy snapshot:

~~~java
boolean sameContents =
        java.util.List.copyOf(left).equals(
                java.util.List.copyOf(right));
~~~

Đây là snippet; `left` và `right` là deque không có null. Với concurrent queues, cần snapshot policy/consistency phù hợp, không mặc nhiên rằng đọc snapshot có transaction isolation.

## 10. Ví dụ chạy #1: các phép cơ bản và giới hạn

### 10.1. Mục tiêu kiểm thử

File `ArrayDequeWorkshop.java` tự xác nhận FIFO, LIFO, hai đầu, rỗng/exception, null, capacity, iterator.remove và equality semantics. Tất cả assertions thật đều thực thi; không chỉ in văn bản PASS mà không kiểm tra.

### 10.2. Source đầy đủ: ArrayDequeWorkshop.java

~~~java
import java.util.*;

public class ArrayDequeWorkshop {
    static void check(boolean b) {
        if (!b) throw new AssertionError();
    }

    public static void main(String[] args) {
        Queue<String> q = new ArrayDeque<>();
        q.offer("A"); q.offer("B"); q.offer("C");
        check(List.copyOf(q).equals(List.of("A", "B", "C")));
        System.out.println("FIFO before: " + List.copyOf(q));

        check("A".equals(q.peek()) && q.size() == 3);
        System.out.println("FIFO peek: " + q.peek());

        check("A".equals(q.poll()));
        System.out.println("FIFO after poll: " + List.copyOf(q));

        List<String> out = new ArrayList<>();
        while (!q.isEmpty()) out.add(q.poll());
        check(out.equals(List.of("B", "C")));
        System.out.println("FIFO drained: " + out);

        check(q.peek() == null && q.poll() == null);
        System.out.println("FIFO empty peek/poll null: true");

        try {
            q.remove();
            throw new AssertionError();
        } catch (NoSuchElementException expected) {
            System.out.println("FIFO empty remove throws: true");
        }

        Deque<String> stack = new ArrayDeque<>();
        stack.push("save1"); stack.push("save2"); stack.push("save3");
        check(List.copyOf(stack).equals(
                List.of("save3", "save2", "save1")));
        System.out.println("LIFO top to bottom: " + List.copyOf(stack));

        check("save3".equals(stack.peek()) && stack.size() == 3);
        System.out.println("LIFO peek: " + stack.peek());

        List<String> popped = new ArrayList<>();
        while (!stack.isEmpty()) popped.add(stack.pop());
        check(popped.equals(List.of("save3", "save2", "save1")));
        System.out.println("LIFO pops: " + popped);

        try {
            stack.pop();
            throw new AssertionError();
        } catch (NoSuchElementException expected) {
            System.out.println("LIFO empty pop throws: true");
        }

        Deque<Integer> d = new ArrayDeque<>();
        d.addFirst(1); d.addLast(2); d.addFirst(0); d.addLast(3);
        check(List.copyOf(d).equals(List.of(0, 1, 2, 3)));
        System.out.println("DEQUE front to back: " + List.copyOf(d));

        check(d.peekFirst() == 0 && d.peekLast() == 3);
        System.out.println("DEQUE ends: 0,3");

        List<Integer> reversed = new ArrayList<>();
        Iterator<Integer> desc = d.descendingIterator();
        while (desc.hasNext()) reversed.add(desc.next());
        check(reversed.equals(List.of(3, 2, 1, 0)));
        System.out.println("DEQUE descending: " + reversed);

        check(d.pollFirst() == 0 && d.pollLast() == 3);
        check(List.copyOf(d).equals(List.of(1, 2)));
        System.out.println("DEQUE after ends removed: " + List.copyOf(d));

        try {
            new ArrayDeque<String>().offer(null);
            throw new AssertionError();
        } catch (NullPointerException expected) {
            System.out.println("NULL insertion rejected: true");
        }

        ArrayDeque<Integer> growth = new ArrayDeque<>(2);
        for (int i = 0; i < 128; i++) growth.offerLast(i);
        check(growth.size() == 128
                && growth.peekFirst() == 0 && growth.peekLast() == 127);
        System.out.println("INITIAL CAPACITY 2 grows to size: "
                + growth.size());

        Deque<String> colors =
                new ArrayDeque<>(List.of("red", "green", "blue"));
        Iterator<String> it = colors.iterator();
        while (it.hasNext()) {
            if ("green".equals(it.next())) it.remove();
        }
        check(List.copyOf(colors).equals(List.of("red", "blue")));
        System.out.println("ITERATOR remove green: "
                + List.copyOf(colors));

        check(!new ArrayDeque<>(List.of(1, 2))
                .equals(new ArrayDeque<>(List.of(1, 2))));
        System.out.println("DEQUE equals is not List value equality: true");
        System.out.println("ALL ArrayDeque assertions passed: true");
    }
}
~~~

### 10.3. Compile và stdout đã kiểm

~~~sh
javac --release 17 ArrayDequeWorkshop.java
java ArrayDequeWorkshop
~~~

Chạy với JDK24, biên dịch source compatibility Java17. Stdout **chính xác 19 dòng**:

~~~text
FIFO before: [A, B, C]
FIFO peek: A
FIFO after poll: [B, C]
FIFO drained: [B, C]
FIFO empty peek/poll null: true
FIFO empty remove throws: true
LIFO top to bottom: [save3, save2, save1]
LIFO peek: save3
LIFO pops: [save3, save2, save1]
LIFO empty pop throws: true
DEQUE front to back: [0, 1, 2, 3]
DEQUE ends: 0,3
DEQUE descending: [3, 2, 1, 0]
DEQUE after ends removed: [1, 2]
NULL insertion rejected: true
INITIAL CAPACITY 2 grows to size: 128
ITERATOR remove green: [red, blue]
DEQUE equals is not List value equality: true
ALL ArrayDeque assertions passed: true
~~~

### 10.4. Phân tích

- `List.copyOf(q)` tạo snapshot theo iterator order để dễ so sánh. Không lầm `ArrayDeque` là List.
- `peek()` không xóa, nhưng `poll()` và `pop()` có xóa.
- `poll()` trên empty trả null; `remove()` và `pop()` trên empty ném exception.
- `descendingIterator()` duyệt tail→head, còn for-each duyệt head→tail.
- `new ArrayDeque<>(2)` vẫn chứa 128 values: **capacity hint khác hard capacity**.
- Xóa bằng iterator.remove trong cùng iterator là hợp lệ trong điều kiện single-thread.
- Hai ArrayDeque cùng data không mặc nhiên value-equal theo List.

## 11. BFS: queue để duyệt đồ thị theo lớp

Với đồ thị không trọng số, BFS tìm được số cạnh tối thiểu từ nguồn đến từng đỉnh reachable. Trong Java:

~~~java
Queue<Integer> queue = new ArrayDeque<>();
queue.offer(start);
seen[start] = true;
while (!queue.isEmpty()) {
    int u = queue.remove();
    for (int v : adjacency.get(u)) {
        if (!seen[v]) {
            seen[v] = true;
            parent[v] = u;
            queue.offer(v);
        }
    }
}
~~~

Đây là snippet trong graph traversal, có `start`, `seen`, `parent`, `adjacency` được khai báo. Mark `seen[v]` **khi enqueue** để tránh chèn đỉnh đó nhiều lần. Với adjacency list, BFS O(V+E).

Đồ thị bài tập:

~~~text
0: [1, 2]
1: [3, 4]
2: [5]
3: [6]
4: [6]
5: [7]
6: [7]
7: []
~~~

Từ 0, BFS order là `[0,1,2,3,4,5,6,7]` theo adjacency order đã khai báo. Shortest path theo số cạnh từ 0 đến 7 là `[0,2,5,7]`, 3 cạnh.

**Giới hạn:** BFS theo số cạnh không tự giải weighted shortest path. Nếu edges có trọng số, chọn thuật toán phù hợp (Dijkstra với nonnegative weights, v.v.).

## 12. DFS: stack để đi sâu theo một nhánh

DFS iterative dùng LIFO:

~~~java
Deque<Integer> stack = new ArrayDeque<>();
stack.push(start);
while (!stack.isEmpty()) {
    int u = stack.pop();
    if (seen[u]) continue;
    seen[u] = true;

    for (int i = adjacency.get(u).size() - 1; i >= 0; i--) {
        int v = adjacency.get(u).get(i);
        if (!seen[v]) stack.push(v);
    }
}
~~~

Vì stack lấy phần tử push **sau cùng** trước, việc push neighbors theo **thứ tự đảo** khiến neighbor đầu tiên trong adjacency được xử lý trước.

Ví dụ đầy đủ đánh dấu visited **khi pop**. Do đó cùng một đỉnh có thể nằm trong stack nhiều lần trước khi được đánh dấu; dòng `if(seen[u]) continue` là điều kiện quan trọng để không xử lý lặp. Có biến thể đánh dấu khi push, nhưng thứ tự DFS có thể khác, hãy chọn rõ semantics.

Trong graph ở mục trước, DFS order từ 0 là `[0,1,3,6,7,4,2,5]` với implementation ví dụ. DFS không bảo đảm shortest path như BFS.

## 13. Kiểm dấu ngoặc bằng stack

Một ứng dụng stack rất trực quan:

- Mở `(`, `[`, `{`: `stack.push(c)`.
- Đóng `)`, `]`, `}`: nếu rỗng, biểu thức sai; nếu không, pop và so đúng loại.
- Kết thúc: stack phải rỗng.

| Chuỗi | Hợp lệ? | Lý do |
| --- | --- | --- |
| `a{b[c](d)}` | true | Cặp ngoặc lồng đúng |
| `([)]` | false | Đóng sai thứ tự |
| `(()` | false | Còn ngoặc mở |
| `)()` | false | Ngoặc đóng khi stack rỗng |

Đây là parser **chỉ xét ký tự ngoặc**. Nó bỏ qua mọi ký tự khác, không xử lý string/comment/escape theo cú pháp Java. Muốn parse Java source thật, dùng lexer/parser đúng ngữ pháp.

## 14. Sliding-window maximum: dùng deque để đạt O(n)

Với dãy `[1,3,-1,-3,5,3,6,7]` và cửa sổ width=3, các maximum liên tiếp là `[3,3,5,5,6,7]`.

Giữ deque chứa **indices**, không chỉ raw values:

1. Xóa ở **đầu** indices đã rời window: `index <= i - width`.
2. Xóa ở **cuối** những indices có value `<= current`: vì phần tử mới hơn luôn tốt hơn/bằng trong mọi window tương lai.
3. Thêm i vào cuối.
4. Khi đã đủ width phần tử, đọc max từ `numbers[deque.peekFirst()]`.

~~~java
Deque<Integer> indices = new ArrayDeque<>();
for (int i = 0; i < numbers.length; i++) {
    while (!indices.isEmpty()
            && indices.peekFirst() <= i - width) {
        indices.removeFirst();
    }
    while (!indices.isEmpty()
            && numbers[indices.peekLast()] <= numbers[i]) {
        indices.removeLast();
    }
    indices.addLast(i);
    if (i >= width - 1) {
        maxima.add(numbers[indices.peekFirst()]);
    }
}
~~~

Snippet này yêu cầu `numbers`, `width`, `maxima` hợp lệ. Code đầy đủ ở mục 15 kiểm width. Vì mỗi index vào deque **một lần** và ra tối đa **một lần**, thuật toán chạy O(n); dùng quét lại toàn bộ k phần tử cho mỗi window dễ thành O(nk).

## 15. Chương trình đầy đủ #2: BFS, DFS, ngoặc và sliding window

### 15.1. Source: DequeAlgorithmsDemo.java

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Deque;
import java.util.List;
import java.util.Queue;

public final class DequeAlgorithmsDemo {
    private static final List<List<Integer>> GRAPH = List.of(
        List.of(1, 2),
        List.of(3, 4),
        List.of(5),
        List.of(6),
        List.of(6),
        List.of(7),
        List.of(7),
        List.of()
    );

    private static void check(boolean okay, String message) {
        if (!okay) throw new AssertionError(message);
    }

    private static List<Integer> bfsOrder(int start, int[] parent) {
        Arrays.fill(parent, -1);
        boolean[] seen = new boolean[GRAPH.size()];
        Queue<Integer> queue = new ArrayDeque<>();
        queue.offer(start);
        seen[start] = true;
        List<Integer> order = new ArrayList<>();
        while (!queue.isEmpty()) {
            int u = queue.remove();
            order.add(u);
            for (int v : GRAPH.get(u)) {
                if (!seen[v]) {
                    seen[v] = true;
                    parent[v] = u;
                    queue.offer(v);
                }
            }
        }
        return order;
    }

    private static List<Integer> pathTo(int[] parent, int target) {
        List<Integer> reversed = new ArrayList<>();
        for (int at = target; at != -1; at = parent[at]) {
            reversed.add(at);
        }
        Collections.reverse(reversed);
        return reversed;
    }

    private static List<Integer> dfsOrder(int start) {
        boolean[] seen = new boolean[GRAPH.size()];
        Deque<Integer> stack = new ArrayDeque<>();
        List<Integer> order = new ArrayList<>();
        stack.push(start);
        while (!stack.isEmpty()) {
            int u = stack.pop();
            if (seen[u]) continue;
            seen[u] = true;
            order.add(u);
            List<Integer> next = GRAPH.get(u);
            for (int i = next.size() - 1; i >= 0; i--) {
                int v = next.get(i);
                if (!seen[v]) stack.push(v);
            }
        }
        return order;
    }

    private static boolean balanced(String input) {
        Deque<Character> stack = new ArrayDeque<>();
        for (char c : input.toCharArray()) {
            if (c == '(' || c == '[' || c == '{') {
                stack.push(c);
            } else if (c == ')' || c == ']' || c == '}') {
                if (stack.isEmpty()) return false;
                char open = stack.pop();
                boolean pair = (open == '(' && c == ')')
                        || (open == '[' && c == ']')
                        || (open == '{' && c == '}');
                if (!pair) return false;
            }
        }
        return stack.isEmpty();
    }

    private static List<Integer> windowMax(int[] numbers, int width) {
        if (width <= 0 || width > numbers.length) {
            throw new IllegalArgumentException("Invalid window");
        }
        Deque<Integer> candidates = new ArrayDeque<>();
        List<Integer> maxima = new ArrayList<>();
        for (int i = 0; i < numbers.length; i++) {
            while (!candidates.isEmpty()
                    && candidates.peekFirst() <= i - width) {
                candidates.removeFirst();
            }
            while (!candidates.isEmpty()
                    && numbers[candidates.peekLast()] <= numbers[i]) {
                candidates.removeLast();
            }
            candidates.addLast(i);
            if (i >= width - 1) {
                maxima.add(numbers[candidates.peekFirst()]);
            }
        }
        return maxima;
    }

    public static void main(String[] args) {
        int[] parent = new int[GRAPH.size()];
        List<Integer> bfs = bfsOrder(0, parent);
        check(bfs.equals(List.of(0, 1, 2, 3, 4, 5, 6, 7)), "BFS order");
        System.out.println("BFS FIFO order: " + bfs);
        List<Integer> shortest = pathTo(parent, 7);
        check(shortest.equals(List.of(0, 2, 5, 7)), "BFS shortest path");
        System.out.println("BFS shortest path 0->7: " + shortest);
        System.out.println("BFS path edge count: " + (shortest.size() - 1));

        List<Integer> dfs = dfsOrder(0);
        check(dfs.equals(List.of(0, 1, 3, 6, 7, 4, 2, 5)), "DFS order");
        System.out.println("DFS LIFO order: " + dfs);

        check(balanced("a{b[c](d)}"), "valid brackets");
        check(!balanced("([)]"), "crossed brackets");
        check(!balanced("(()"), "unmatched opener");
        check(!balanced(")()"), "unmatched closer");
        System.out.println("BRACKETS a{b[c](d)}: true");
        System.out.println("BRACKETS ([)]: false");
        System.out.println("BRACKETS ((): false");
        System.out.println("BRACKETS )(): false");

        int[] data = {1, 3, -1, -3, 5, 3, 6, 7};
        List<Integer> max = windowMax(data, 3);
        check(max.equals(List.of(3, 3, 5, 5, 6, 7)),
                "window maxima");
        System.out.println("SLIDING MAX k=3: " + max);
        boolean rejected = false;
        try {
            windowMax(data, 0);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, "invalid window accepted");
        System.out.println("SLIDING MAX invalid width rejected: true");
        System.out.println("ALL algorithm assertions passed: true");
    }
}
~~~

### 15.2. Compile và đầu ra

~~~sh
javac --release 17 DequeAlgorithmsDemo.java
java DequeAlgorithmsDemo
~~~

**Stdout chính xác đã kiểm trên JDK24 — 11 dòng:**

~~~text
BFS FIFO order: [0, 1, 2, 3, 4, 5, 6, 7]
BFS shortest path 0->7: [0, 2, 5, 7]
BFS path edge count: 3
DFS LIFO order: [0, 1, 3, 6, 7, 4, 2, 5]
BRACKETS a{b[c](d)}: true
BRACKETS ([)]: false
BRACKETS ((): false
BRACKETS )(): false
SLIDING MAX k=3: [3, 3, 5, 5, 6, 7]
SLIDING MAX invalid width rejected: true
ALL algorithm assertions passed: true
~~~

### 15.3. Chú ý khi mở rộng

- BFS path ở demo hợp lệ vì đích reachable; với unreachable target, cần kiểm `seen[target]` trước khi truy ngược parent.
- DFS iteration order phụ thuộc adjacency order và chiến lược đánh dấu visited; không có một “thứ tự DFS duy nhất” cho mọi cách triển khai.
- Với graph có chu trình, đừng bỏ visited guard, nếu không có thể lặp vô hạn.
- Balanced brackets ở demo không hiểu escape sequences hoặc strings/comments.
- Window maximum từ chối width=0 hoặc width lớn hơn số elements bằng `IllegalArgumentException`. Khi thiết kế library, ghi rõ behavior của empty input và k=0.

## 16. Undo/redo dùng hai ArrayDeque stacks

Một editor đơn giản lưu current state và hai history stacks:

- `undo`: các trạng thái trước đó, đỉnh là trạng thái sẽ quay lại.
- `redo`: các trạng thái mới hơn đã bị undo, đỉnh là trạng thái có thể áp lại.
- Khi **áp dụng chỉnh sửa mới** sau một lần undo, **phải clear redo** để không quay lại một history branch cũ.

Ví dụ:

~~~text
current = "";   undo=[]          redo=[]
apply("A")      undo=[""]        current="A"   redo=[]
apply("AB")     undo=["A",""]    current="AB"  redo=[]
undo()          undo=[""]        current="A"   redo=["AB"]
redo()          undo=["A",""]    current="AB"  redo=[]
undo()          undo=[""]        current="A"   redo=["AB"]
apply("AX")     undo=["A",""]    current="AX"  redo=[]  (nhánh mới)
~~~

Các thao tác:

~~~java
void apply(String next) {
    Objects.requireNonNull(next);
    if (!text.equals(next)) {
        undo.push(text);
        text = next;
        redo.clear();
    }
}

boolean undo() {
    if (undo.isEmpty()) return false;
    redo.push(text);
    text = undo.pop();
    return true;
}

boolean redo() {
    if (redo.isEmpty()) return false;
    undo.push(text);
    text = redo.pop();
    return true;
}
~~~

Đây là **snippets** trong class có fields `text`, `undo` và `redo`. Chương trình hoàn chỉnh có class này trong mục 19.

**Điểm thiết kế:** Khi không thể undo/redo, trả false là phù hợp với hành vi UI bình thường. Không nhất thiết ném exception. Khi `apply` nhận state giống hiện tại, tránh tạo history entry vô nghĩa.

### 16.1. Giới hạn của lưu snapshots

Với String nhỏ, lưu toàn bộ state là cách dạy dễ hiểu. Với document khổng lồ, history snapshots có thể tốn memory. Hệ thống production có thể lưu diffs/commands, checkpoints, giới hạn số bước và có transaction/authorization semantics riêng. `ArrayDeque` chỉ cung cấp LIFO, **không tự thực hiện rollback của database, file, network side effects**.

## 17. Manual bounded queue cho ứng dụng một thread

`new ArrayDeque<>(2)` không đặt max 2. Muốn hard bound tự quản lý ở app đơn luồng:

~~~java
final class SingleThreadBoundedQueue<E> {
    private final int max;
    private final Queue<E> pending = new ArrayDeque<>();

    SingleThreadBoundedQueue(int max) {
        if (max <= 0) {
            throw new IllegalArgumentException("max must be positive");
        }
        this.max = max;
    }

    boolean offer(E value) {
        Objects.requireNonNull(value);
        return pending.size() < max && pending.offer(value);
    }

    E poll() {
        return pending.poll();
    }
}
~~~

Đây là snippet yêu cầu imports `ArrayDeque`, `Queue`, `Objects`. Ví dụ với max=2:

~~~text
offer(J1) -> true     [J1]
offer(J2) -> true     [J1, J2]
offer(J3) -> false    [J1, J2]
poll()    -> J1       [J2]
offer(J3) -> true     [J2, J3]
~~~

**Quan trọng:** Check `pending.size()<max` và `pending.offer(value)` là **hai thao tác riêng**. Nếu hai producer threads cùng truy cập, cả hai có thể thấy còn chỗ và enqueue, vượt limit. Ngoài race trên limit, `ArrayDeque` bản thân không thread-safe. Đừng dùng wrapper này trong nhiều threads nếu không có cơ chế đồng bộ atomic và visibility đầy đủ.

## 18. Nếu cần queue đa luồng, chọn đúng collection

| Nhu cầu | Lựa chọn |
| --- | --- |
| Queue FIFO một thread | `ArrayDeque` như `Queue` |
| Stack LIFO một thread | `ArrayDeque` như `Deque` |
| Deque concurrent không blocking | `ConcurrentLinkedDeque` |
| Queue FIFO concurrent có fixed capacity | `ArrayBlockingQueue` |
| Deque concurrent có bounded capacity | `LinkedBlockingDeque<>(capacity)` |
| FIFO concurrent không giới hạn logic | `ConcurrentLinkedQueue` hoặc `LinkedBlockingQueue` theo semantics |
| Queue priority thay FIFO | `PriorityQueue` hoặc `PriorityBlockingQueue` tùy concurrency |

`LinkedBlockingDeque<String> queue = new LinkedBlockingDeque<>(2)` khác `new ArrayDeque<>(2)`: với LinkedBlockingDeque, **2 là maximum capacity thật**. Ví dụ:

~~~java
java.util.concurrent.BlockingDeque<String> queue =
        new java.util.concurrent.LinkedBlockingDeque<>(2);

System.out.println(queue.offerLast("A")); // true
System.out.println(queue.offerLast("B")); // true
System.out.println(queue.offerLast("C")); // false, đã đầy.
System.out.println(queue.pollFirst());     // A
~~~

Ngoài `offerLast/pollFirst`, blocking deque hỗ trợ `putLast` (có thể chờ khi đầy), `takeFirst` (chờ khi trống), và overload timeout. Thiết kế cancellation/interrupt/shutdown và backpressure rõ ràng; tránh consumer kẹt vô hạn ở `takeFirst` khi producers đã dừng.

**Không coi ConcurrentLinkedDeque là blocking deque.** Nó thread-safe nhưng không cung cấp cùng blocking/backpressure semantics như LinkedBlockingDeque.

## 19. Chương trình đầy đủ #3: undo/redo và bounded queues

### 19.1. Source: DequeWorkflowsDemo.java

~~~java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Objects;
import java.util.Queue;
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.LinkedBlockingDeque;

public final class DequeWorkflowsDemo {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    private static final class EditorHistory {
        private String text = "";
        private final Deque<String> undo = new ArrayDeque<>();
        private final Deque<String> redo = new ArrayDeque<>();

        void apply(String next) {
            Objects.requireNonNull(next, "text");
            if (!text.equals(next)) {
                undo.push(text);
                text = next;
                redo.clear();
            }
        }
        boolean undo() {
            if (undo.isEmpty()) return false;
            redo.push(text);
            text = undo.pop();
            return true;
        }
        boolean redo() {
            if (redo.isEmpty()) return false;
            undo.push(text);
            text = redo.pop();
            return true;
        }
        String text() { return text; }
        int undoDepth() { return undo.size(); }
        boolean canRedo() { return !redo.isEmpty(); }
    }

    private static final class SingleThreadBoundedQueue<E> {
        private final int max;
        private final Queue<E> pending = new ArrayDeque<>();

        SingleThreadBoundedQueue(int max) {
            if (max <= 0) {
                throw new IllegalArgumentException(
                        "max must be positive");
            }
            this.max = max;
        }
        boolean offer(E element) {
            Objects.requireNonNull(element, "element");
            return pending.size() < max
                    && pending.offer(element);
        }
        E poll() { return pending.poll(); }
        List<E> snapshot() { return List.copyOf(pending); }
    }

    public static void main(String[] args) {
        EditorHistory editor = new EditorHistory();
        editor.apply("A");
        editor.apply("AB");
        check("AB".equals(editor.text()), "initial history");
        System.out.println("EDIT after two changes: 'AB'");
        check(editor.undo()
                && "A".equals(editor.text()), "undo");
        System.out.println("UNDO => 'A'");
        check(editor.redo()
                && "AB".equals(editor.text()), "redo");
        System.out.println("REDO => 'AB'");
        check(editor.undo()
                && "A".equals(editor.text()), "second undo");
        System.out.println("UNDO again => 'A'");
        editor.apply("AX");
        check("AX".equals(editor.text()), "branch edit");
        System.out.println("BRANCH edit => 'AX'");
        check(!editor.canRedo() && !editor.redo(),
                "redo was not cleared");
        System.out.println("REDO cleared after branch: true");
        check(editor.undo()
                && "A".equals(editor.text()), "undo branch");
        System.out.println("UNDO branch => 'A'");
        check(editor.redo()
                && "AX".equals(editor.text()), "redo branch");
        System.out.println("REDO branch => 'AX'");
        int depth = editor.undoDepth();
        editor.apply("AX");
        check(editor.undoDepth() == depth,
                "no-op changed history");
        System.out.println("NOOP edit keeps undo depth: true");

        SingleThreadBoundedQueue<String> manual =
                new SingleThreadBoundedQueue<>(2);
        check(manual.offer("J1") && manual.offer("J2"),
                "initial offers");
        check(!manual.offer("J3"), "manual bound ignored");
        System.out.println("MANUAL bound rejects third offer: true");
        check("J1".equals(manual.poll())
                && manual.offer("J3"), "manual slot reuse");
        check(manual.snapshot().equals(List.of("J2", "J3")),
                "manual FIFO");
        System.out.println(
                "MANUAL bound after drain and add: [J2, J3]");

        BlockingDeque<String> concurrent =
                new LinkedBlockingDeque<>(2);
        check(concurrent.offerLast("J1")
                && concurrent.offerLast("J2"),
                "blocking deque initial");
        check(!concurrent.offerLast("J3"),
                "blocking bound ignored");
        System.out.println("BLOCKING deque rejects third offer: true");
        check("J1".equals(concurrent.pollFirst())
                && concurrent.offerLast("J3"),
                "blocking slot reuse");
        check(List.copyOf(concurrent).equals(
                List.of("J2", "J3")), "blocking FIFO");
        System.out.println(
                "BLOCKING deque FIFO after slot reuse: [J2, J3]");
        System.out.println("ALL workflow assertions passed: true");
    }
}
~~~

### 19.2. Compile và stdout

~~~sh
javac --release 17 DequeWorkflowsDemo.java
java DequeWorkflowsDemo
~~~

Chạy thật trên JDK24 với Java17 source compatibility. **Stdout chính xác 14 dòng:**

~~~text
EDIT after two changes: 'AB'
UNDO => 'A'
REDO => 'AB'
UNDO again => 'A'
BRANCH edit => 'AX'
REDO cleared after branch: true
UNDO branch => 'A'
REDO branch => 'AX'
NOOP edit keeps undo depth: true
MANUAL bound rejects third offer: true
MANUAL bound after drain and add: [J2, J3]
BLOCKING deque rejects third offer: true
BLOCKING deque FIFO after slot reuse: [J2, J3]
ALL workflow assertions passed: true
~~~

### 19.3. Phạm vi đã được xác minh

- Undo/redo cập nhật đúng trạng thái và clear redo khi tạo một nhánh edit mới.
- Gọi apply với cùng state không tạo thêm undo entry.
- Manual size-bound wrapper từ chối chèn thứ ba khi max=2 trong code **đơn luồng**.
- Bounded `LinkedBlockingDeque` trả false khi đầy và nhận lại phần tử sau khi có slot.
- Bài kiểm `LinkedBlockingDeque` là basic semantic test, **không phải multi-thread stress test**.
- Không có file ngoài/JAR thư viện ngoài hoặc server cần chạy kèm.

## 20. Chọn cấu trúc khi triển khai thật

~~~text
Bài toán lấy element nào trước?
             |
      +------+------+
      |             |
     FIFO          LIFO
      |             |
      v             v
  Queue<E>       Deque<E>
      |             |
Single thread?    Single thread?
   /    \            /     \
  yes   no          yes     no
   |     |            |       |
ArrayDeque  cần bounded?  ArrayDeque  concurrency-aware design
            /      \
           yes      no
            |        |
 ArrayBlockingQueue  ConcurrentLinkedQueue /
 hoặc LinkedBlockingDeque  LinkedBlockingQueue
~~~

Đây là cây lựa chọn minh họa. Nếu cần deque concurrent **hai đầu**, dùng `ConcurrentLinkedDeque` hoặc `LinkedBlockingDeque` tùy cần blocking/capacity bound. Nếu chỉ làm DFS bằng một method trong một thread, `new ArrayDeque<>()` là lựa chọn đơn giản và hiện hành.

**Thứ tự ra quyết định đúng:** semantics FIFO/LIFO → empty/null contract → đồng bộ hay một thread → giới hạn dung lượng/backpressure → benchmark nếu thực sự cần tối ưu.

## 21. Test matrix thực tế

| Test | Thiết lập | Mong đợi |
| --- | --- | --- |
| FIFO order | Offer A, B, C rồi poll | A, B, C |
| FIFO peek | Peek trước poll | Không giảm size |
| FIFO empty | Poll rỗng | null |
| FIFO empty exception | Remove rỗng | `NoSuchElementException` |
| LIFO order | Push 1, 2, 3 rồi pop | 3, 2, 1 |
| LIFO empty | Pop rỗng | `NoSuchElementException` |
| Deque endpoints | addFirst/addLast | Đúng thứ tự đầu/cuối |
| Deque inspection | peekFirst/peekLast | Hai đầu chính xác |
| Reverse iterator | descendingIterator | Ngược thứ tự |
| Null insertion | offer(null), push(null) | `NullPointerException` |
| Capacity | ArrayDeque<>(2), 128 inserts | Size 128 |
| Iterator remove | Xóa bằng iterator | Không fail-fast sai cách |
| Equality | Hai ArrayDeque cùng data | Không tự value-equal theo List |
| BFS order | Adjacency cụ thể | [0,1,2,3,4,5,6,7] |
| BFS shortest | 0→7 graph không trọng số | [0,2,5,7] |
| BFS seen | Mark khi enqueue | Không enqueue trùng đỉnh |
| DFS order | Push neighbor đảo | [0,1,3,6,7,4,2,5] |
| DFS cycle | Graph có chu trình | Có visited guard |
| Brackets good | a{b[c](d)} | true |
| Brackets crossed | ([)] | false |
| Brackets incomplete | (() | false |
| Sliding max | k=3, input đã cho | [3,3,5,5,6,7] |
| Sliding max bounds | k=0 | `IllegalArgumentException` |
| Undo | Undo edit gần nhất | Trạng thái cũ |
| Redo | Redo sau undo | Trạng thái mới |
| Undo branching | Edit mới sau undo | Redo bị clear |
| No-op edit | Apply cùng text | History depth không đổi |
| Manual bound | Max 2, offer 3 | false |
| Manual slot reuse | Poll rồi offer | Đúng FIFO |
| Blocking bound | LinkedBlockingDeque(2) đầy | offerLast trả false |
| Blocking slot reuse | Poll rồi offer | Đúng FIFO |
| Concurrency | Nhiều producers | Không dùng ArrayDeque unsynchronized |
| Shutdown | Blocking consumers | Có cancellation/interruption policy |
| Java17 compile | `javac --release 17` | Cả ba ví dụ chạy |
| API note | Java SE26/17 docs | Không dùng API legacy làm giải pháp mới |

### 21.1. Kiểm thử gì chưa làm?

Bài đã kiểm các chức năng ở trên bằng chương trình Java thật. Nó **không** kiểm benchmark throughput thực tế, multi-thread stress test cho `LinkedBlockingDeque` hay latency dưới load. Với production work queue, cần thêm tests đồng thời, shutdown/cancel, timeout, duplicate-job và metrics.

## 22. Bài tập có đáp án định hướng

**Bài 1: FIFO.** Khởi tạo `Queue<String>`, chèn `email`, `billing`, `report` rồi poll đến hết. Kỳ vọng thứ tự `email → billing → report`. Vì sao dùng `push` làm sai thứ tự?

**Bài 2: LIFO.** Push `v1`, `v2`, `v3` rồi pop. Kỳ vọng `v3 → v2 → v1`. Dùng `peek` trước pop để xác nhận không xóa đỉnh.

**Bài 3: Đảo chuỗi ASCII.** Push từng char trong `JAVA` rồi pop để tạo `AVAJ`. Với Unicode có surrogate pairs hoặc grapheme clusters, cần thiết kế theo code points/graphemes; đảo từng `char` đơn giản có thể phá text.

**Bài 4: Kiểm dấu ngoặc.** `()[]{}` và `([{}])` đúng; `([)]` và `((()` sai. Chứng minh chỉ đếm số dấu mở/đóng không đủ.

**Bài 5: BFS/DFS.** Dùng graph ở mục 11–15, tính cả traversal order và shortest path. Đổi adjacency order rồi dự đoán DFS order; lưu ý BFS shortest distance vẫn đúng nhưng có thể đổi parent nếu có nhiều đường ngắn nhất.

**Bài 6: Sliding max.** Dùng dãy `[4,2,12,3,8,7]` với k=2. Kết quả phải là `[4,12,12,8,8]`. Tại sao cần lưu **indices** trong deque?

**Bài 7: Bounded queue.** Chứng minh `new ArrayDeque<Integer>(1)` có thể chứa 50 phần tử. Sau đó tạo wrapper max=10 và giải thích race khi hai threads cùng đọc size=9 rồi chèn.

**Bài 8: Undo/redo.** Làm chuỗi `"" → "a" → "ab"`, undo về `"a"`, apply `"ax"`. Kiểm redo không còn. Làm sao giới hạn history tối đa 100 steps mà vẫn giữ đúng thứ tự?

**Bài 9: Chọn collection.** Một HTTP server có nhiều producer threads và một consumer đang đợi jobs. Bạn cần 1.000 slots, từ chối quá tải thay vì tăng memory vô hạn. Tại sao `ArrayDeque(1000)` không đáp ứng? Một lựa chọn là `ArrayBlockingQueue<>(1000)` hoặc `LinkedBlockingDeque<>(1000)` với offer và metrics.

**Bài 10: Xử lý empty.** Nêu lúc nào nên chọn `poll` và lúc nào chọn `remove/pop`. Nếu queue rỗng là trạng thái bình thường, đừng dùng exception làm control flow thường xuyên.

## 23. Câu hỏi tự kiểm tra

**1. ArrayDeque là FIFO hay LIFO?** Cả hai, tùy methods bạn dùng.

**2. Queue lấy ở đầu hay cuối?** Thêm cuối, lấy đầu.

**3. Stack push và pop ở đâu?** Đều ở đầu.

**4. `push(e)` tương đương method nào?** `addFirst(e)`.

**5. `pop()` tương đương method nào?** `removeFirst()`.

**6. `offer(e)` tương đương method nào?** `offerLast(e)`.

**7. `poll()` tương đương method nào?** `pollFirst()`.

**8. `peek()` đọc đầu hay cuối?** Đầu, cả queue và stack view.

**9. Queue rỗng poll cho kết quả gì?** null.

**10. Stack rỗng pop cho kết quả gì?** `NoSuchElementException`.

**11. Có được offer(null) không?** Không, ném `NullPointerException`.

**12. Constructor ArrayDeque(2) có cố định size=2 không?** Không, là capacity hint.

**13. ArrayDeque có thread-safe không?** Không.

**14. ArrayDeque có get(index) không?** Không.

**15. Hầu hết endpoint operations là O(1)?** O(1) amortized cho phần lớn operations ở đầu/cuối.

**16. contains(value) là O(1)?** Không, O(n) với ArrayDeque.

**17. remove() và remove(Object) giống nhau?** Không; remove() xóa đầu, remove(Object) tìm element.

**18. Fail-fast iterator có đảm bảo phát hiện mọi concurrent bug?** Không; best effort.

**19. Dùng ArrayDeque làm BFS như thế nào?** `Queue<Integer>` với offer/poll.

**20. Dùng ArrayDeque làm DFS như thế nào?** `Deque<Integer>` với push/pop.

**21. BFS trong unweighted graph tìm gì?** Shortest path theo số cạnh từ nguồn tới đỉnh reachable.

**22. Sliding-window maximum lưu gì trong deque?** Các indices ứng viên.

**23. Undo/redo cần mấy stack trong ví dụ?** Hai stack.

**24. Khi edit mới sau undo cần làm gì?** Xóa redo history.

**25. Manual bounded ArrayDeque size-check có dùng đa luồng được không?** Không nếu không có đồng bộ atomic; ArrayDeque cũng không thread-safe.

**26. LinkedBlockingDeque<>(2) có capacity limit thật không?** Có.

**27. ConcurrentLinkedDeque có blocking semantics không?** Không.

**28. Stack class có bị xóa khỏi Java không?** Không; Deque được khuyến nghị cho LIFO mới.

**29. Vì sao không dùng ArrayDeque làm unlimited job queue không giám sát?** Dễ tăng memory, cần backpressure/shutdown.

**30. Ghi nhớ cốt lõi?** **FIFO offerLast/pollFirst; LIFO push/pop; xử lý empty và null rõ ràng; ArrayDeque không bounded, không thread-safe.**

## 24. Kết luận và tài liệu hiện hành

`ArrayDeque<E>` là một giải pháp **hiện đại, đơn giản và hiệu quả** cho queue/stack **trong phạm vi một thread**. Interface `Queue` biểu đạt FIFO, `Deque` biểu đạt stack/hai đầu. Những thuật toán như BFS, DFS, dấu ngoặc và sliding window cho thấy việc chọn thao tác đầu/cuối ảnh hưởng trực tiếp tới tính đúng đắn.

Ba chương trình `ArrayDequeWorkshop.java`, `DequeAlgorithmsDemo.java` và `DequeWorkflowsDemo.java` đã được biên dịch bằng `javac --release 17` và chạy trên JDK24 với tổng cộng **44 dòng output được kiểm chứng** (19 + 11 + 14). Bài không nhầm capacity hint thành giới hạn, không khẳng định thread safety và không dùng Stack legacy làm lựa chọn mới.

**Tóm tắt ngắn:** Queue = vào cuối, ra đầu; Stack = vào đầu, ra đầu; deque cho phép cả hai đầu. Không chèn null. Đừng phụ thuộc fail-fast để đồng bộ. Nếu có nhiều producers/consumers, dùng đúng concurrent collection và policy backpressure thay vì chia sẻ ArrayDeque không đồng bộ.

### Tài liệu chính thức

- [Oracle Java SE 26 — ArrayDeque](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ArrayDeque.html): mảng tự mở rộng, null, concurrency, complexity và iterator.
- [Oracle Java SE 26 — Deque](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Deque.html): method mappings FIFO/LIFO, two-ended operations, legacy Stack recommendation.
- [Oracle Java SE 26 — Queue](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Queue.html): offer/add, poll/remove, peek/element.
- [Oracle Java SE 26 — LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html): bounded concurrent double-ended queue.
- [Oracle Java SE 26 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded blocking FIFO queue.
- [Oracle Java SE 26 — ConcurrentLinkedDeque](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html): lock-free concurrent deque.
- [Oracle Java SE 26 — Iterator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Iterator.html): iteration và remove contract.
- [Oracle Java SE 17 — ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html): xác nhận tương thích API Java 17.

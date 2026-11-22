# Quy tắc null trong các triển khai Queue

## 1. Null có hai vai trò dễ bị lẫn

Khi làm việc với hàng đợi, cần phân biệt:

1. **Null là một phần tử được đưa vào hàng đợi.**
2. **Null là giá trị đặc biệt do phương thức trả về để báo không có phần tử.**

Ví dụ, `poll()` trên một hàng đợi rỗng trả về null. Nếu cùng hàng đợi còn cho phép lưu một phần tử null, chỉ nhìn giá trị trả về sẽ không biết vừa lấy được phần tử null hay hàng đợi vốn đã rỗng.

Phần lớn cách triển khai `Queue` không nhận phần tử null. Tuy nhiên, không thể kết luận rằng **mọi** đối tượng có kiểu `Queue<E>` đều cấm null: `LinkedList` là một ngoại lệ vẫn có trong Java hiện hành. Tài liệu [Queue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Queue.html) cũng khuyến cáo không đưa null vào hàng đợi ngay cả với cách triển khai cho phép.

Bài dùng API còn áp dụng hiện nay và chương trình kiểm chứng Java 17+.

## 2. Chính sách null thuộc về hợp đồng cụ thể

| Kiểu triển khai hoặc hợp đồng | Nhận phần tử null? | Khi thử thêm null |
|---|---|---|
| `ArrayDeque` | Không | `NullPointerException` |
| `PriorityQueue` | Không | `NullPointerException` |
| `LinkedList` dùng như Queue | Có | `offer(null)` và `add(null)` thành công |
| `ConcurrentLinkedQueue` | Không | `NullPointerException` |
| `ArrayBlockingQueue` | Không | `NullPointerException` |
| `LinkedBlockingQueue` | Không | `NullPointerException` |
| Các cách triển khai tuân theo hợp đồng `BlockingQueue` | Không | Thao tác thêm null bị từ chối |

Không dựa vào generic để quyết định chính sách này:

```java
Queue<String> first = new ArrayDeque<>();
Queue<String> second = new LinkedList<>();
```

Cả hai biến cùng có kiểu `Queue<String>`, nhưng đối tượng thực tế có quy tắc khác nhau. Tham số kiểu `String` không tự tạo bảo đảm “khác null” của hệ thống kiểu Java thông thường.

`LinkedList` công bố việc nhận null trong [tài liệu lớp](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedList.html). Ngược lại, [BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html) cấm null ở cấp hợp đồng của interface mở rộng này; đây không chỉ là một đặc điểm tình cờ của một lớp cụ thể.

### Offer trả false không có nghĩa mọi dữ liệu sai đều được trả false

Với hàng đợi có sức chứa cố định, `offer(e)` có thể trả false khi không còn chỗ. Nhưng null vi phạm hợp đồng của một hàng đợi cấm null thì vẫn gây `NullPointerException`.

Không dùng cách diễn giải “`offer` là phiên bản không ném ngoại lệ của `add`” cho mọi trường hợp. Hai phương thức khác cách báo không nhận thêm vì sức chứa, nhưng vẫn có thể từ chối dữ liệu không hợp lệ bằng ngoại lệ.

## 3. Chương trình so sánh add(null) và offer(null)

Lưu tệp `QueueNullPolicyDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Comparator;
import java.util.LinkedList;
import java.util.PriorityQueue;
import java.util.Queue;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.function.Supplier;

public class QueueNullPolicyDemo {
    static void check(String name, Supplier<Queue<String>> factory) {
        Queue<String> offerQueue = factory.get();
        try {
            System.out.println(name + " offer=" + offerQueue.offer(null));
        } catch (NullPointerException ex) {
            System.out.println(name + " offer=NullPointerException");
        }

        Queue<String> addQueue = factory.get();
        try {
            System.out.println(name + " add=" + addQueue.add(null));
        } catch (NullPointerException ex) {
            System.out.println(name + " add=NullPointerException");
        }
    }

    public static void main(String[] args) {
        check("ArrayDeque", ArrayDeque::new);
        check("PriorityQueue", PriorityQueue::new);
        check("LinkedList", LinkedList::new);
        check("ConcurrentLinkedQueue", ConcurrentLinkedQueue::new);
        check("ArrayBlockingQueue", () -> new ArrayBlockingQueue<>(2));
        check("LinkedBlockingQueue", LinkedBlockingQueue::new);
        check("PriorityQueue nullsFirst",
                () -> new PriorityQueue<>(Comparator.nullsFirst(
                        Comparator.naturalOrder())));
    }
}
```

Chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -Xlint:all -Werror QueueNullPolicyDemo.java
java QueueNullPolicyDemo
```

Stdout:

```text
ArrayDeque offer=NullPointerException
ArrayDeque add=NullPointerException
PriorityQueue offer=NullPointerException
PriorityQueue add=NullPointerException
LinkedList offer=true
LinkedList add=true
ConcurrentLinkedQueue offer=NullPointerException
ConcurrentLinkedQueue add=NullPointerException
ArrayBlockingQueue offer=NullPointerException
ArrayBlockingQueue add=NullPointerException
LinkedBlockingQueue offer=NullPointerException
LinkedBlockingQueue add=NullPointerException
PriorityQueue nullsFirst offer=NullPointerException
PriorityQueue nullsFirst add=NullPointerException
```

Mỗi thao tác dùng một hàng đợi mới do `factory` tạo ra. Nhờ vậy, kết quả `add` không phụ thuộc phần tử mà `offer` có thể đã thêm trước đó.

Ví dụ chạy hoàn toàn trong một luồng. Các kiểu concurrent/blocking được dùng để kiểm chứng quy tắc null; chương trình không tạo luồng và không gọi thao tác chờ.

### Comparator.nullsFirst không thay hợp đồng của PriorityQueue

Dòng kiểm chứng cuối tạo `PriorityQueue` với comparator có thể so sánh null. Tuy nhiên, `PriorityQueue` vẫn từ chối chính phần tử null.

Có hai lớp điều kiện khác nhau:

- Comparator có chấp nhận các đối số null để so sánh hay không?
- Cấu trúc hàng đợi có cho phép lưu null làm phần tử hay không?

Comparator không thể mở rộng tập phần tử mà hợp đồng của hàng đợi cấm. Việc một comparator hỗ trợ null không buộc `PriorityQueue` gọi comparator trước khi kiểm tra dữ liệu đầu vào.

## 4. Null trả về từ poll và peek

Với một hàng đợi không chứa null:

| Trạng thái | `peek()` | `poll()` |
|---|---|---|
| Có phần tử | Trả đầu, giữ nguyên hàng đợi | Trả đầu và loại bỏ đầu |
| Rỗng | Trả null | Trả null |

Nếu cách triển khai cấm phần tử null và mọi bên tuân theo hợp đồng đó, null từ `poll()` là dấu hiệu rõ ràng rằng lời gọi này không lấy được phần tử.

Nhưng với `LinkedList` chứa null ở đầu:

- `peek()` trả null dù hàng đợi chưa rỗng.
- `poll()` trả null **và đã loại bỏ phần tử null**.
- Một phần tử khác vẫn có thể còn phía sau.

Không được suy ra `poll() == null` đồng nghĩa “không có thay đổi cấu trúc” khi đã cho phép dữ liệu null.

### Element và remove báo rỗng bằng ngoại lệ

`element()` và `remove()` không dùng null để báo hàng đợi rỗng; chúng ném `NoSuchElementException`.

Tuy nhiên, với `LinkedList` có phần tử đầu là null, chúng có thể trả về null một cách bình thường:

- `element()` trả phần tử đầu null nhưng không loại bỏ.
- `remove()` trả phần tử đầu null và loại bỏ nó.

Đừng kết luận rằng “phương thức có dạng ném ngoại lệ sẽ không bao giờ trả null”. Ngoại lệ ở đây mô tả trường hợp **rỗng**, không tự cấm nội dung null mà cách triển khai cho phép.

## 5. Chương trình quan sát sự nhập nhằng và lỗi dừng sớm

Lưu tệp `QueueNullAmbiguityDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.LinkedList;
import java.util.NoSuchElementException;
import java.util.Queue;

public class QueueNullAmbiguityDemo {
    public static void main(String[] args) {
        Queue<String> queue = new LinkedList<>();
        queue.offer(null);
        queue.offer("B");
        System.out.println("initial size=" + queue.size());
        System.out.println("peek=" + queue.peek() + ", size=" + queue.size());
        System.out.println("element=" + queue.element());
        System.out.println("poll=" + queue.poll() + ", size=" + queue.size());
        System.out.println("next=" + queue.poll() + ", size=" + queue.size());
        System.out.println("poll empty=" + queue.poll());
        try {
            queue.element();
        } catch (NoSuchElementException ex) {
            System.out.println("element empty: NoSuchElementException");
        }

        Queue<String> input = new LinkedList<>();
        input.offer("A");
        input.offer(null);
        input.offer("B");
        String item;
        while ((item = input.poll()) != null) {
            System.out.println("processed=" + item);
        }
        System.out.println("remaining=" + input.size() + ", head=" + input.peek());

        Queue<Integer> numbers = new ArrayDeque<>();
        try {
            int value = numbers.poll();
            System.out.println(value);
        } catch (NullPointerException ex) {
            System.out.println("unboxing empty poll: NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror QueueNullAmbiguityDemo.java
java QueueNullAmbiguityDemo
```

Kết quả:

```text
initial size=2
peek=null, size=2
element=null
poll=null, size=1
next=B, size=0
poll empty=null
element empty: NoSuchElementException
processed=A
remaining=1, head=B
unboxing empty poll: NullPointerException
```

### Phần đầu: null không đồng nghĩa hàng đợi rỗng

Ban đầu, hàng đợi có hai phần tử:

```text
đầu → [null, "B"] ← đuôi
```

`peek` và `element` đều trả null trong khi kích thước vẫn là 2. Lần `poll` đầu loại bỏ phần tử null, nên kích thước giảm còn 1. Lần `poll` tiếp theo vẫn lấy được B.

Chỉ đến sau đó hàng đợi mới thực sự rỗng. `poll` trả null ở trạng thái rỗng và `element` ném ngoại lệ.

### Phần giữa: vòng lặp tưởng đã hết dữ liệu

Vòng lặp quen thuộc:

```java
String item;
while ((item = input.poll()) != null) {
    System.out.println("processed=" + item);
}
```

dừng khi gặp giá trị null. Với dữ liệu A, null, B:

1. Nó xử lý A.
2. Nó lấy và loại bỏ phần tử null, rồi điều kiện thành false.
3. Nó dừng dù B vẫn còn chờ.

Đây là lỗi do dữ liệu vi phạm giả định của mẫu vòng lặp, không phải do `poll` làm mất B. Mẫu này phù hợp khi hàng đợi không chứa phần tử null.

Nếu đang xử lý một `LinkedList` có sẵn dữ liệu null trong một luồng và không có thay đổi đồng thời, có thể dùng:

```java
while (!input.isEmpty()) {
    String item = input.remove();
    if (item == null) {
        // Xử lý phần tử thiếu theo quy tắc của ứng dụng.
    } else {
        System.out.println(item);
    }
}
```

Đây là mảnh mã minh họa cách phân biệt “có phần tử null” với “hết phần tử” trong điều kiện đã nêu. Nó không biến chuỗi `isEmpty()` rồi `remove()` thành một thao tác nguyên tử cho nhiều luồng, và cũng không phải lý do khuyến khích đưa null vào một hàng đợi mới.

### Phần cuối: lỗi mở hộp không phải lỗi lưu null

```java
Queue<Integer> numbers = new ArrayDeque<>();
int value = numbers.poll();
```

`ArrayDeque` không chứa phần tử null ở đây. Hàng đợi rỗng nên `poll()` trả về một tham chiếu `Integer` null; phép gán cho `int` yêu cầu mở hộp, từ đó gây `NullPointerException`.

Cách xử lý thường gặp là giữ kiểu bao để kiểm tra:

```java
Integer value = numbers.poll();
if (value != null) {
    int number = value;
    System.out.println(number);
}
```

Không quy mọi `NullPointerException` gần một hàng đợi về việc đã thêm null. Cần xác định ngoại lệ phát sinh khi thêm phần tử, khi gọi phương thức trên kết quả hay khi mở hộp.

## 6. Null của phần tử khác null trong thuộc tính của phần tử

Một hàng đợi cấm phần tử null không tự cấm mọi trường null nằm bên trong đối tượng phần tử.

Ví dụ:

```java
record Task(String label) {
}
```

`new Task(null)` tạo một đối tượng `Task` khác null; chỉ thuộc tính `label` là null. Hàng đợi thấy một tham chiếu đối tượng hợp lệ. Nếu ứng dụng muốn cấm `label` null, phải kiểm tra bằng hợp đồng của `Task` hoặc tầng thêm dữ liệu.

Đối với hàng đợi ưu tiên, còn phải xét comparator có xử lý thuộc tính đó hay không. Đây là nơi `Comparator.nullsFirst` có thể hữu ích mà không thay đổi quy tắc cấm phần tử null của `PriorityQueue`.

Lưu tệp `QueueNullFieldDemo.java`:

```java
import java.util.Comparator;
import java.util.PriorityQueue;
import java.util.Queue;

public class QueueNullFieldDemo {
    record Task(String label) {
    }

    public static void main(String[] args) {
        Comparator<Task> order = Comparator.comparing(Task::label,
                Comparator.nullsFirst(Comparator.naturalOrder()));
        Queue<Task> tasks = new PriorityQueue<>(order);
        tasks.offer(new Task("B"));
        tasks.offer(new Task(null));
        tasks.offer(new Task("A"));

        Task task;
        while ((task = tasks.poll()) != null) {
            System.out.println("label=" + task.label());
        }
    }
}
```

Chạy:

```shell
javac --release 17 -Xlint:all -Werror QueueNullFieldDemo.java
java QueueNullFieldDemo
```

Kết quả:

```text
label=null
label=A
label=B
```

Giải thích:

1. Ba phần tử đều là đối tượng `Task` khác null.
2. Comparator lấy `label` và dùng một comparator chấp nhận null cho **khóa so sánh**.
3. Công việc có nhãn null được xếp trước các công việc có nhãn A và B.
4. Vòng lặp dừng theo `task == null`, không theo `task.label() == null`, nên nó vẫn xử lý công việc có nhãn null.

Nếu dùng comparator mặc định trên chuỗi mà không xử lý null của nhãn, một phép so sánh có thể gây ngoại lệ. Null hợp lệ với hàng đợi không bảo đảm mọi thao tác nghiệp vụ trên nội dung đều hợp lệ.

## 7. Thiết kế hợp đồng dữ liệu không dùng null làm tín hiệu

### Kiểm tra ở nơi thêm dữ liệu

Nếu viết một hàm nhận `Queue<E>` do bên khác cung cấp, không nên giả định rằng mọi cách triển khai đều tự chặn null giống nhau. Có thể công bố quy tắc riêng và kiểm tra rõ:

```java
static <E> boolean enqueue(java.util.Queue<E> queue, E value) {
    java.util.Objects.requireNonNull(queue, "queue");
    java.util.Objects.requireNonNull(value, "value");
    return queue.offer(value);
}
```

Đoạn trên là phương thức để đặt trong một lớp. Nó giữ nguyên kết quả `offer` để bên gọi xử lý trường hợp không nhận được phần tử. Dù đối tượng thực tế là `LinkedList`, hàm vẫn thực thi hợp đồng không nhận null.

Không chỉ kiểm tra ở một hàm rồi tuyên bố rằng hàng đợi dùng chung chắc chắn không có null nếu những nơi khác vẫn có thể thêm trực tiếp. Quy tắc phải được giữ trên toàn bộ đường đưa dữ liệu vào.

### Dữ liệu thiếu cần một cách biểu diễn riêng

Tùy nghiệp vụ, có thể:

- Dùng một đối tượng công việc khác null có trạng thái rõ ràng.
- Dùng một kiểu thông điệp riêng để thể hiện “thiếu dữ liệu” hoặc “kết thúc”.
- Từ chối dữ liệu thiếu trước khi thêm vào hàng đợi.

Các lựa chọn này phải có hợp đồng cụ thể. Không âm thầm bỏ qua null nếu việc đó làm mất một yêu cầu xử lý mà ứng dụng cần ghi nhận.

### Kết thúc xử lý không phải một lần poll trả null

Với hàng đợi đồng thời không chặn, `poll()` trả null chỉ cho biết lời gọi đó không lấy được phần tử; nó không tự xác nhận rằng không bao giờ còn dữ liệu được thêm trong tương lai. `ConcurrentLinkedQueue` cấm phần tử null như [tài liệu lớp](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html) công bố, nhưng quy trình kết thúc vẫn phải được thiết kế riêng.

Với `BlockingQueue`, không dùng `put(null)` hoặc `offer(null)` làm “tín hiệu dừng”: hợp đồng cấm null. Một thông điệp kết thúc khác null là một cách thiết kế có thể dùng; hệ thống còn phải xác định cách chuyển nó đến đủ các bên tiêu thụ. Bài không suy ra toàn bộ giao thức dừng chỉ từ một đối tượng đánh dấu.

## 8. Lỗi thường gặp

| Suy luận sai | Cách hiểu đúng |
|---|---|
| Khai báo `Queue<String>` là chắc chắn cấm null | Cần xem hợp đồng cách triển khai và hợp đồng ứng dụng |
| `offer(null)` phải trả false thay vì ném ngoại lệ | Hàng đợi cấm null vẫn ném `NullPointerException` |
| `PriorityQueue` nhận null nếu comparator có `nullsFirst` | Comparator không bỏ lệnh cấm phần tử null của cấu trúc |
| `peek() == null` luôn chứng minh hàng đợi rỗng | Chỉ kết luận chắc chắn theo giả định không có phần tử null |
| `poll() == null` nghĩa là không phần tử nào bị loại bỏ | Với `LinkedList` chứa null ở đầu, phần tử null đã bị loại bỏ |
| `element()` không bao giờ trả null | Có thể trả null là dữ liệu trong cách triển khai cho phép |
| Null bên trong thuộc tính làm cả phần tử null | Đối tượng phần tử vẫn có thể khác null; thuộc tính là một hợp đồng khác |
| NPE sau `int value = queue.poll()` chứng minh đã thêm null | Có thể chỉ là mở hộp kết quả null khi hàng đợi rỗng |
| Null là tín hiệu dừng phù hợp cho BlockingQueue | Null bị cấm; cần thiết kế tín hiệu khác null |
| Kiểm tra `isEmpty()` rồi lấy là đủ cho mọi trường hợp nhiều luồng | Hai lời gọi riêng không tự tạo bảo đảm nguyên tử |

## 9. Thực hành phân tích trạng thái

### Tình huống 1

Một `LinkedList` dùng như `Queue<String>` chứa null rồi “done”. Lần `poll()` đầu trả gì, hàng đợi còn gì?

**Đáp án:** Trả null và loại bỏ phần tử null. Hàng đợi vẫn còn “done”.

### Tình huống 2

Một `ArrayDeque<Integer>` rỗng gây NPE ở `int next = queue.poll();`. Có cần đổi sang `LinkedList` để cho phép null không?

**Đáp án:** Không. Vấn đề là mở hộp kết quả null của thao tác trên hàng đợi rỗng. Giữ kết quả dưới dạng `Integer` và xử lý trường hợp chưa có phần tử.

### Tình huống 3

`PriorityQueue<Task>` không nhận phần tử null. Điều đó có bảo đảm `Task.label` luôn khác null không?

**Đáp án:** Không. Cần kiểm tra dữ liệu bên trong đối tượng theo hợp đồng của `Task` và comparator nếu thuộc tính đó được dùng để so sánh.

### Tình huống 4

Muốn dùng `while ((item = queue.poll()) != null)` làm vòng tiêu thụ, cần giả định gì về dữ liệu?

**Đáp án:** Hàng đợi không chứa phần tử null. Với mã đồng thời, còn phải phân biệt “hiện tại chưa có phần tử” với “quy trình đã kết thúc”.

Khi gặp null, hãy xác định **null là phần tử, kết quả báo vắng mặt hay một thuộc tính → cách triển khai cho phép gì → thao tác có thay đổi hàng đợi không → mã sau đó có mở hộp/gọi phương thức không → hợp đồng ứng dụng xử lý trạng thái đó thế nào**.

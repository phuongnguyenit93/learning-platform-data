# Hợp đồng Queue và các cách tổ chức thứ tự phần tử

## 1. Queue mô tả việc chờ xử lý, không mặc định một thứ tự duy nhất

`Queue<E>` là một interface thuộc Java Collections Framework, dùng để chứa các phần tử đang chờ được xử lý. Hợp đồng cốt lõi gồm ba việc:

1. Thêm một phần tử.
2. Lấy và loại bỏ phần tử tiếp theo.
3. Xem phần tử tiếp theo nhưng giữ nguyên nó trong hàng đợi.

**Đầu hàng đợi (head)** là phần tử mà `poll()` hoặc `remove()` sẽ lấy ra. “Đầu” là khái niệm theo chính sách chọn phần tử của hàng đợi, không bắt buộc là phần tử được thêm sớm nhất.

Đây là điểm dễ nhầm: nhiều hàng đợi dùng FIFO, nhưng **interface `Queue` không buộc mọi cách triển khai phải FIFO**. Hàng đợi ưu tiên và hàng đợi LIFO vẫn có thể đáp ứng hợp đồng `Queue`.

Nếu thay lớp triển khai sau một biến `Queue<E>`, các tên phương thức giữ nguyên nhưng thứ tự xử lý có thể đổi. Vì vậy, phải đọc cả hợp đồng interface lẫn chính sách thứ tự của lớp hoặc bộ điều hợp đang dùng. [Tài liệu Queue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Queue.html) nêu rõ sự phân biệt này.

Bài dùng API còn áp dụng hiện nay, với mã Java 17+.

## 2. Sáu phương thức cốt lõi và hai cách báo không thành công

| Mục đích | Dạng dùng ngoại lệ | Dạng trả giá trị đặc biệt |
|---|---|---|
| Thêm phần tử | `add(e)` | `offer(e)` |
| Lấy và loại bỏ đầu hàng đợi | `remove()` | `poll()` |
| Xem đầu, không loại bỏ | `element()` | `peek()` |

Cần hiểu giá trị đặc biệt trong đúng tình huống:

- Khi hàng đợi rỗng, `poll()` và `peek()` trả về `null`.
- Khi hàng đợi rỗng, `remove()` và `element()` ném `NoSuchElementException`.
- Với hàng đợi bị giới hạn sức chứa, nếu hiện tại không còn chỗ, `offer(e)` trả về `false`, còn `add(e)` ném `IllegalStateException`.
- Khi thêm thành công, `offer(e)` và `add(e)` trả về `true`.

`peek()`/`element()` không lấy phần tử ra, nên gọi chúng nhiều lần trong một hàng đợi không thay đổi sẽ quan sát cùng đầu hàng đợi. `poll()`/`remove()` thay đổi cấu trúc bằng cách loại bỏ phần tử trả về.

### Offer không phải phương thức “không bao giờ ném ngoại lệ”

`false` chủ yếu phục vụ tình huống không thể nhận phần tử vì hạn chế sức chứa. Một phần tử vi phạm quy tắc vẫn có thể gây ngoại lệ, chẳng hạn:

- `null` trong một hàng đợi cấm null: `NullPointerException`.
- Phần tử không đáp ứng yêu cầu so sánh của hàng đợi ưu tiên: có thể gây `ClassCastException`.
- Các hạn chế riêng khác do cách triển khai công bố.

Đừng bắt mọi ngoại lệ rồi đổi thành `false`; như vậy sẽ làm lẫn việc hàng đợi đầy với dữ liệu đầu vào không hợp lệ.

### Phân biệt remove() và remove(Object)

`Queue` kế thừa các thao tác từ `Collection`, nên còn có `remove(Object)`:

```java
queue.remove();       // Lấy và loại bỏ đầu; trả về phần tử.
queue.remove(target); // Tìm và loại bỏ một phần tử phù hợp; trả boolean.
```

Hai lời gọi không có cùng hợp đồng. Với `Queue<Integer>`, `remove(10)` tìm giá trị 10 qua phương thức `remove(Object)`; nó không có nghĩa “xóa phần tử ở vị trí chỉ số 10”. `Queue` không cung cấp mô hình truy cập theo chỉ số như `List`.

## 3. Những chính sách chọn đầu hàng đợi thường gặp

Giả sử lần lượt thêm các giá trị 30, 10, 20:

| Chính sách | Phần tử được xử lý trước | Thứ tự lấy hết |
|---|---|---|
| FIFO: vào trước, ra trước | Phần tử được thêm sớm nhất | 30, 10, 20 |
| Ưu tiên nhỏ trước | Phần tử nhỏ nhất theo quy tắc so sánh | 10, 20, 30 |
| Ưu tiên lớn trước | Phần tử được xếp trước theo comparator đảo thứ tự | 30, 20, 10 |
| LIFO: vào sau, ra trước | Phần tử vừa được thêm gần nhất | 20, 10, 30 |

### FIFO

Với `ArrayDeque` được dùng qua các thao tác `Queue`, thêm vào đuôi và lấy từ đầu tạo thành FIFO:

```text
offer(30), offer(10), offer(20)

đầu → [30, 10, 20] ← đuôi
poll() lấy 30
```

`ArrayDeque` là một deque có thể thao tác ở hai đầu. Trong ví dụ FIFO, ta chỉ sử dụng góc nhìn và các thao tác của `Queue`. Nếu một tham chiếu khác đồng thời gọi `addFirst(...)` trên cùng deque, đó là một luồng thao tác khác phải được tính đến khi phân tích thứ tự.

### Hàng đợi ưu tiên

`PriorityQueue` xác định đầu dựa trên thứ tự tự nhiên hoặc `Comparator` được cung cấp. Theo quy tắc so sánh đang dùng, phần tử nhỏ nhất nằm ở đầu.

Với số nguyên và thứ tự tự nhiên, 10 được lấy trước dù 30 được thêm trước. Với comparator đảo thứ tự, số lớn được xếp trước theo quy tắc mới.

“Số ưu tiên lớn hơn thì chạy trước” là quy ước nghiệp vụ cần cấu hình, không phải mặc định của mọi `PriorityQueue`. Phải diễn đạt nó bằng comparator phù hợp. [Tài liệu PriorityQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PriorityQueue.html) mô tả rõ cách chọn đầu và cách xử lý phần tử ngang mức ưu tiên.

### LIFO

LIFO lấy phần tử thêm gần nhất trước. Trong Java, có thể dùng `Deque` cho thao tác ngăn xếp, hoặc dùng `Collections.asLifoQueue(deque)` để nhìn một deque như một `Queue` theo LIFO.

Bộ điều hợp này làm rõ rằng cùng lời gọi `offer` và `poll` không bảo đảm FIFO khi đối tượng thực tế có chính sách khác.

## 4. Chương trình so sánh thứ tự

Lưu tệp `QueueOrderDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Queue;

public class QueueOrderDemo {
    static <E> List<E> drain(Queue<E> queue) {
        List<E> result = new ArrayList<>();
        E next;
        while ((next = queue.poll()) != null) {
            result.add(next);
        }
        return result;
    }

    static void show(String label, Queue<Integer> queue) {
        queue.offer(30);
        queue.offer(10);
        queue.offer(20);
        System.out.println(label + "=" + drain(queue));
    }

    public static void main(String[] args) {
        show("FIFO", new ArrayDeque<>());
        show("MIN", new PriorityQueue<>());
        show("MAX", new PriorityQueue<>(Comparator.reverseOrder()));
        show("LIFO", Collections.asLifoQueue(new ArrayDeque<>()));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror QueueOrderDemo.java
java QueueOrderDemo
```

Stdout:

```text
FIFO=[30, 10, 20]
MIN=[10, 20, 30]
MAX=[30, 20, 10]
LIFO=[20, 10, 30]
```

Hàm `show` dùng chung interface `Queue<Integer>`; sự khác nhau đến từ đối tượng được truyền vào.

Hàm `drain` liên tục gọi `poll()` để quan sát **thứ tự lấy ra**. Nó làm rỗng hàng đợi. Tên hàm và kết quả trả về thể hiện rõ đây là thao tác tiêu thụ dữ liệu, không phải xem nhanh nội dung mà giữ nguyên hàng đợi.

Vòng lặp dừng khi `poll()` trả null. Cách viết này phù hợp với những hàng đợi trong ví dụ vì chúng không chứa phần tử null. Nếu tự chọn một cách triển khai cho phép null, phải xem lại giả định ấy.

### Không thay poll bằng iterator rồi kết luận thứ tự xử lý

Không có một quy tắc chung rằng vòng `for`, `iterator()`, `toArray()` hoặc `toString()` của mọi `Queue` sẽ hiển thị theo thứ tự các lần `poll()`.

Đặc biệt, iterator của `PriorityQueue` không bảo đảm duyệt theo thứ tự ưu tiên. Việc một lần in tình cờ trông có thứ tự không trở thành hợp đồng API.

Khi muốn lấy ra theo ưu tiên, dùng các thao tác ở đầu hàng đợi. Nếu cần giữ nguyên dữ liệu, có thể tạo một bản sao phù hợp rồi lấy dần từ bản sao, hoặc sắp xếp một bản chụp theo đúng comparator; không mặc định rằng mọi kiểu sao chép đều giữ lại comparator mà không kiểm tra constructor/API đang dùng.

## 5. Chương trình kiểm chứng hợp đồng thao tác

Lưu tệp `QueueContractDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.NoSuchElementException;
import java.util.Queue;
import java.util.concurrent.ArrayBlockingQueue;

public class QueueContractDemo {
    public static void main(String[] args) {
        Queue<String> queue = new ArrayDeque<>();
        System.out.println("peek empty=" + queue.peek());
        System.out.println("poll empty=" + queue.poll());
        try {
            queue.element();
        } catch (NoSuchElementException ex) {
            System.out.println("element empty: NoSuchElementException");
        }
        try {
            queue.remove();
        } catch (NoSuchElementException ex) {
            System.out.println("remove empty: NoSuchElementException");
        }

        System.out.println("offer A=" + queue.offer("A"));
        System.out.println("add B=" + queue.add("B"));
        System.out.println("peek=" + queue.peek() + ", size=" + queue.size());
        System.out.println("remove=" + queue.remove() + ", size=" + queue.size());
        System.out.println("poll=" + queue.poll() + ", size=" + queue.size());

        Queue<Integer> bounded = new ArrayBlockingQueue<>(2);
        System.out.println("bounded offer 1=" + bounded.offer(1));
        System.out.println("bounded offer 2=" + bounded.offer(2));
        System.out.println("bounded offer 3=" + bounded.offer(3));
        try {
            bounded.add(3);
        } catch (IllegalStateException ex) {
            System.out.println("bounded add 3: IllegalStateException");
        }
        System.out.println("bounded head=" + bounded.peek());

        try {
            queue.offer(null);
        } catch (NullPointerException ex) {
            System.out.println("offer null: NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror QueueContractDemo.java
java QueueContractDemo
```

Stdout:

```text
peek empty=null
poll empty=null
element empty: NoSuchElementException
remove empty: NoSuchElementException
offer A=true
add B=true
peek=A, size=2
remove=A, size=1
poll=B, size=0
bounded offer 1=true
bounded offer 2=true
bounded offer 3=false
bounded add 3: IllegalStateException
bounded head=1
offer null: NullPointerException
```

### Nhóm hàng đợi rỗng

Bốn dòng đầu xác minh hai cách báo rỗng:

- `peek` và `poll` trả null.
- `element` và `remove` ném ngoại lệ.

Không phải “thấy null thì có lỗi” trong mọi trường hợp. Null là một phần của hợp đồng các phương thức trả giá trị đặc biệt.

### Nhóm xem và lấy

Sau khi thêm A rồi B vào FIFO:

- `peek` trả A nhưng kích thước vẫn là 2.
- `remove` lấy A và kích thước còn 1.
- `poll` lấy B và kích thước còn 0.

Các lời gọi khác tên vẫn cùng tuân theo chính sách chọn đầu của đối tượng.

### Nhóm giới hạn sức chứa

`ArrayBlockingQueue<>(2)` tạo một hàng đợi sức chứa 2. Ví dụ chỉ sử dụng nó để quan sát `add`/`offer`; không tạo luồng và không dùng thao tác chờ.

Sau khi nhận 1 và 2:

- `offer(3)` trả false.
- `add(3)` ném `IllegalStateException`.
- Đầu vẫn là 1; hai lần thêm không thành công không đưa 3 vào hàng đợi.

`offer` trong ví dụ không tự chờ đến lúc có chỗ trống. Các phương thức chờ của lập trình đồng thời thuộc hợp đồng bổ sung như `BlockingQueue`, không nằm trong sáu phương thức cốt lõi của `Queue`.

### Nhóm null

`ArrayDeque` cấm null, nên `offer(null)` ném `NullPointerException`. Điều này cũng chứng minh rằng dạng “trả giá trị đặc biệt” không phải lời hứa loại bỏ mọi ngoại lệ.

## 6. Sức chứa và thứ tự là hai trục độc lập

Không suy ra đặc điểm sức chứa chỉ từ tên chính sách thứ tự:

- FIFO có thể dùng cấu trúc tăng kích thước khi cần, hoặc một cấu trúc có sức chứa cố định.
- Hàng đợi ưu tiên không tự đồng nghĩa với “chỉ chứa tối đa N phần tử”.
- Tính an toàn luồng cũng là một đặc điểm khác, không được suy ra từ FIFO hay ưu tiên.

Ví dụ, `new PriorityQueue<>(10)` đặt sức chứa ban đầu của cấu trúc bên trong, không đặt một giới hạn cứng rằng phần tử thứ 11 phải bị từ chối. `PriorityQueue` tăng sức chứa khi cần theo hợp đồng của nó.

Tương tự, `ArrayDeque` tăng kích thước khi cần và không phải hàng đợi có sức chứa cố định theo con số truyền vào constructor. “Không có giới hạn cố định do API đặt” vẫn không có nghĩa tài nguyên bộ nhớ là vô hạn.

[Tài liệu ArrayDeque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayDeque.html) công bố rõ khả năng tăng kích thước, cấm null và việc lớp này không tự đồng bộ hóa.

Interface `Queue` tự nó cũng không bảo đảm tính an toàn luồng, tính nguyên tử của chuỗi nhiều thao tác hoặc cơ chế chờ. Chọn cách triển khai theo toàn bộ yêu cầu, không chỉ nhìn tên phương thức.

## 7. Ngang mức ưu tiên không tự thành FIFO

Nếu hai phần tử được comparator xem là ngang nhau, `PriorityQueue` không bảo đảm giữ thứ tự thêm giữa chúng. Đây không phải cấu trúc sắp xếp ổn định mặc định.

Nếu nghiệp vụ cần “ưu tiên cao trước; cùng ưu tiên thì đến trước xử lý trước”, hãy đưa cả thứ tự đến vào comparator. Phải có dữ liệu mô tả thứ tự đến; không yêu cầu hàng đợi đoán thông tin không được lưu.

Lưu tệp `JobOrderDemo.java`:

```java
import java.util.Comparator;
import java.util.PriorityQueue;
import java.util.Queue;

public class JobOrderDemo {
    record Job(String name, int priority, long sequence) {
    }

    public static void main(String[] args) {
        Comparator<Job> order = Comparator.comparingInt(Job::priority)
                .reversed()
                .thenComparingLong(Job::sequence);
        Queue<Job> jobs = new PriorityQueue<>(order);
        jobs.offer(new Job("low", 1, 1));
        jobs.offer(new Job("urgent-first", 5, 2));
        jobs.offer(new Job("urgent-second", 5, 3));

        Job job;
        while ((job = jobs.poll()) != null) {
            System.out.println(job.name());
        }
    }
}
```

Chạy:

```shell
javac --release 17 -Xlint:all -Werror JobOrderDemo.java
java JobOrderDemo
```

Kết quả:

```text
urgent-first
urgent-second
low
```

Trong ví dụ:

1. `priority` lớn hơn được xếp trước nhờ `reversed()`.
2. Khi `priority` bằng nhau, `sequence` nhỏ hơn được xếp trước.
3. Ba công việc có giá trị thứ tự được cấp rõ ràng; đây là thí nghiệm một luồng.

Ở hệ thống có nhiều bên thêm dữ liệu, cách cấp `sequence` và chính sách hòa khi vẫn trùng giá trị phải được thiết kế riêng. `PriorityQueue` không tự giải quyết việc đó.

Các trường dùng để so sánh trong ví dụ là thành phần của record, không thay đổi sau khi tạo. Đừng thay đổi thuộc tính quyết định thứ tự của một đối tượng khi nó đang nằm trong hàng đợi ưu tiên rồi kỳ vọng cấu trúc tự sắp lại. Nếu cần đổi ưu tiên, phải thiết kế thao tác cập nhật phù hợp, chẳng hạn loại bỏ rồi thêm lại theo quy tắc đã xác định.

## 8. Những giới hạn hợp đồng dễ bỏ sót

### Không nên đưa null vào Queue

Dù một vài cách triển khai có thể cho phép null, dùng null làm phần tử khiến khó phân biệt “lấy được dữ liệu null” với “hàng đợi đã rỗng” khi dùng `poll()`.

Nên dùng đối tượng biểu diễn trạng thái hoặc một kiểu dữ liệu có ý nghĩa cụ thể nếu nghiệp vụ cần mô tả dữ liệu thiếu. Đừng dùng null làm dấu kết thúc xử lý trong một hàng đợi cấm null.

### Queue có thể giữ phần tử trùng

`Queue` không phải `Set`. Hai phần tử bằng nhau hoặc có cùng độ ưu tiên không tự bị gộp thành một. Với `PriorityQueue`, ngang nhau theo comparator không có nghĩa “phần tử thứ hai bị bỏ qua”.

### Xem trước rồi lấy không phải một thao tác duy nhất

Trong một luồng với hàng đợi không bị tác động ở nơi khác, `peek()` rồi `poll()` thường đọc và lấy cùng phần tử đầu. Trong mã có nhiều luồng hoặc nhiều tham chiếu cùng sửa dữ liệu, phần tử có thể đã thay đổi giữa hai lời gọi. Không suy ra bảo đảm nguyên tử từ việc dùng interface `Queue`.

Trong phạm vi một vòng tiêu thụ, thường nên xử lý trực tiếp kết quả `poll()` như các ví dụ thay vì kiểm tra `isEmpty()` rồi giả định lần lấy tiếp theo chắc chắn thành công.

### Chọn lớp triển khai là một phần của thiết kế

| Nhu cầu trong các ví dụ | Lựa chọn minh họa |
|---|---|
| FIFO một luồng, tăng kích thước khi cần | `ArrayDeque` qua thao tác `Queue` |
| Lấy theo thứ tự ưu tiên | `PriorityQueue` với thứ tự tự nhiên hoặc comparator |
| LIFO qua cùng interface Queue | `Collections.asLifoQueue(new ArrayDeque<>())` |
| Quan sát việc từ chối khi đầy | `ArrayBlockingQueue` với sức chứa cố định |

Bảng này là ánh xạ cho các tình huống đã kiểm chứng, không phải kết luận rằng chỉ có một lớp đáp ứng mỗi nhu cầu.

## 9. Tự kiểm tra

### Câu 1

Thêm lần lượt 8, 3, 5 vào một biến có kiểu `Queue<Integer>`. Có thể kết luận `poll()` trả 8 chỉ từ kiểu biến không?

**Đáp án:** Không. Cần biết đối tượng thực tế và chính sách thứ tự. FIFO trả 8; `PriorityQueue` dùng thứ tự tự nhiên trả 3.

### Câu 2

`peek()` trả phần tử đầu rồi kích thước giảm 1: phát biểu này đúng không?

**Đáp án:** Sai. `peek()` chỉ xem, không loại bỏ. `poll()` mới lấy và loại bỏ đầu.

### Câu 3

`offer(e)` trả false có nghĩa phần tử bị trùng không?

**Đáp án:** Không theo hợp đồng chung của `Queue`. Trong ví dụ sức chứa cố định, nó có nghĩa không còn chỗ. Không mang cách hiểu về tập hợp sang hàng đợi.

### Câu 4

Có thể dùng kết quả `PriorityQueue.toString()` làm bằng chứng rằng các lần xử lý sẽ theo thứ tự được in không?

**Đáp án:** Không. Cần kiểm tra thứ tự các lần lấy ở đầu; thứ tự duyệt không được bảo đảm là thứ tự ưu tiên.

### Câu 5

Muốn cùng độ ưu tiên thì xử lý theo thứ tự đến, chỉ dùng `Comparator.comparingInt(Job::priority)` đã đủ chưa?

**Đáp án:** Chưa. Comparator còn cần tiêu chí phụ mô tả thứ tự đến, và dữ liệu thứ tự ấy phải được cấp theo hợp đồng của hệ thống.

Khi thiết kế một hàng đợi, hãy xác định **phần tử nào là đầu → chính sách thứ tự → cách báo rỗng/đầy → quy tắc dữ liệu → sức chứa → yêu cầu đồng thời**. Sáu phương thức của `Queue` là giao diện thao tác chung; chính sách chọn đầu quyết định phần tử nào được xử lý tiếp theo.

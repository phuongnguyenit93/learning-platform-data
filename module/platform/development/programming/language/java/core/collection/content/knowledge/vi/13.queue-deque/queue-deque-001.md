# Queue, FIFO và những hàng đợi không theo FIFO

## 1. Queue là giao diện thao tác; FIFO là một chính sách thứ tự

Trong Java, `Queue<E>` biểu diễn một tập hợp giữ các phần tử để chờ xử lý. Nó cung cấp những thao tác như thêm phần tử, xem phần tử ở đầu hàng và lấy phần tử ở đầu hàng ra.

Một điểm cần phân biệt ngay:

- **Queue** là giao diện và mô hình thao tác.
- **FIFO** là chính sách “vào trước, ra trước” — first in, first out.
- Không phải mọi đối tượng có kiểu `Queue` đều chọn phần tử theo FIFO.

Tài liệu `Queue` nói rõ các hàng đợi thường theo FIFO nhưng có ngoại lệ, gồm hàng đợi ưu tiên và hàng đợi LIFO. Mỗi triển khai phải mô tả quy tắc thứ tự của nó. [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)

Khái niệm chung cho mọi chính sách là **đầu hàng (head)**: phần tử mà thao tác lấy ra như `poll()` hoặc `remove()` sẽ chọn theo hợp đồng của triển khai.

Vì vậy, tên phương thức `poll` không tự có nghĩa “lấy phần tử được thêm sớm nhất”. Nó có nghĩa lấy phần tử ở đầu theo chính sách đang dùng.

Ví dụ, cùng thêm lần lượt:

```text
30, 10, 20
```

có thể có ba kết quả hợp lệ:

| Chính sách | Thứ tự lấy ra |
| --- | --- |
| FIFO | `30, 10, 20` |
| Ưu tiên số nhỏ trước | `10, 20, 30` |
| LIFO, vào sau ra trước | `20, 10, 30` |

Muốn dự đoán chương trình, phải biết cả giao diện đang gọi lẫn chính sách của đối tượng thực tế.

## 2. FIFO: thêm ở cuối, lấy ở đầu

### 2.1. Mô hình đầu và cuối

Một hàng đợi FIFO có hai vai trò khác nhau:

```text
lấy ra ← đầu hàng [A] [B] [C] cuối hàng ← thêm mới
```

Nếu `A`, `B`, `C` được thêm tuần tự theo thứ tự đó và không có thao tác khác thay đổi hàng, các lần lấy sẽ trả `A`, rồi `B`, rồi `C`.

| Thao tác | Trạng thái FIFO sau thao tác | Kết quả lấy ra |
| --- | --- | --- |
| Thêm A | `[A]` | Chưa lấy |
| Thêm B | `[A, B]` | Chưa lấy |
| Thêm C | `[A, B, C]` | Chưa lấy |
| Lấy đầu | `[B, C]` | `A` |
| Lấy đầu | `[C]` | `B` |
| Lấy đầu | `[]` | `C` |

Một phần tử mới thêm vào cuối không vượt qua các phần tử đang chờ trước nó. Đó là ý nghĩa của vào trước, ra trước.

### 2.2. Một cách dùng FIFO trong một luồng

```java
// Đoạn minh họa; có chương trình đầy đủ ở phần sau.
Queue<String> pending = new ArrayDeque<>();
pending.offer("A");
pending.offer("B");
pending.offer("C");

String next = pending.poll(); // A
```

Khi dùng `ArrayDeque` qua các thao tác hàng đợi như trên, thêm diễn ra ở cuối và lấy ở đầu.

FIFO nói về thứ tự lấy khỏi hàng, không nhất thiết là thứ tự hoàn thành xử lý ở ngoài hàng. Nếu nhiều bên cùng xử lý và một công việc lâu hơn công việc khác, kết quả hoàn tất có thể khác thứ tự lấy. Hàng đợi không tự biến thời gian xử lý của mọi phần tử thành giống nhau.

### 2.3. FIFO không có nghĩa phải loại trùng

Một hàng đợi không phải `Set`. Các triển khai trong bài có thể giữ hai phần tử bằng nhau:

```text
thêm A, thêm A
lấy ra: A, A
```

Nếu yêu cầu chỉ xử lý mỗi mã một lần, cần thiết kế riêng việc nhận diện đã gặp, không suy ra từ việc dữ liệu nằm trong một `Queue`.

## 3. Sáu phương thức cốt lõi và cách đọc đúng đầu hàng

`Queue` chia các thao tác cơ bản thành hai cách báo một số tình huống không thực hiện được:

| Mục đích | Dạng báo bằng ngoại lệ | Dạng trả giá trị đặc biệt |
| --- | --- | --- |
| Thêm phần tử | `add(e)` | `offer(e)` |
| Lấy và xóa đầu hàng | `remove()` | `poll()` |
| Xem đầu hàng, giữ nguyên hàng | `element()` | `peek()` |

Chính sách thứ tự quyết định **phần tử nào là đầu**. Các cặp phương thức chủ yếu khác cách báo trạng thái thất bại tương ứng, không đổi FIFO thành ưu tiên hoặc ngược lại.

### 3.1. offer và add

`offer(e)` thử thêm phần tử ngay. Với một hàng đợi bị giới hạn dung lượng, nó trả `false` khi không thể thêm vì hiện không còn chỗ.

`add(e)` trả `true` khi thành công; nếu không có chỗ do giới hạn dung lượng, nó báo bằng `IllegalStateException`.

Không hiểu “dạng trả giá trị đặc biệt” là mọi lỗi đều được chuyển thành `false`. Phần tử không hợp lệ, chẳng hạn `null` trong một hàng không chấp nhận `null`, vẫn có thể gây ngoại lệ.

Cũng không hiểu `offer` là lời gọi tự chờ tới khi có chỗ. Các thao tác chờ thuộc giao diện chuyên biệt như `BlockingQueue`, với những phương thức riêng. [Queue: add và offer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)

### 3.2. poll và remove không đối số

Với các hàng đợi thông thường trong chương trình đầu:

- `poll()`: trả và xóa đầu hàng; khi hàng rỗng trả `null`.
- `remove()`: trả và xóa đầu hàng; khi hàng rỗng ném `NoSuchElementException`.

Đây là `remove()` **không có đối số**. Nó khác với `remove(Object value)` kế thừa từ `Collection`, vốn tìm và xóa một phần tử phù hợp theo giá trị và trả `boolean`.

Không đọc hai chữ ký này như cùng một thao tác.

### 3.3. peek và element

Hai phương thức đều xem đầu hàng mà không xóa:

- `peek()`: khi rỗng trả `null`.
- `element()`: khi rỗng ném `NoSuchElementException`.

Với một FIFO có `[A, B, C]`, nhiều lần `peek()` khi không có thay đổi khác vẫn nhìn thấy `A`, không lần lượt đi qua `A`, `B`, `C`.

### 3.4. Tránh dùng null như một công việc hợp lệ

`ArrayDeque` và `PriorityQueue` không cho thêm `null`. Giao diện `Queue` còn có những triển khai với quy tắc khác, nhưng ngay cả khi một triển khai cho phép, dùng `null` làm phần tử vẫn gây mơ hồ với các kết quả đặc biệt của `poll` và `peek`.

Nên giữ miền công việc không chứa `null` khi có thể. Khi lấy ra, kiểm tra kết quả trước khi dùng như một đối tượng hoặc mở hộp sang kiểu nguyên thủy.

Các hàng đợi chuyên biệt còn có điều kiện phần tử được phép lấy; ví dụ `DelayQueue` được phân biệt ở phần sau. Không khái quát một vòng lặp xử lý đơn giản cho mọi triển khai mà chưa đọc hợp đồng của nó. [Queue: quy tắc null](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)

## 4. Chương trình đầy đủ: cùng giao diện, ba thứ tự lấy

Lưu mã vào **QueuePoliciesDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.PriorityQueue;
import java.util.Queue;

public class QueuePoliciesDemo {
    private static <E> List<E> drain(Queue<E> queue) {
        List<E> result = new ArrayList<>();
        E value;
        while ((value = queue.poll()) != null) {
            result.add(value);
        }
        return result;
    }

    public static void main(String[] args) {
        Queue<Integer> fifo = new ArrayDeque<>();
        Queue<Integer> priority = new PriorityQueue<>();
        Queue<Integer> lifo =
                Collections.asLifoQueue(new ArrayDeque<>());

        List<Integer> input = List.of(30, 10, 20);
        for (Integer value : input) {
            fifo.offer(value);
            priority.offer(value);
            lifo.offer(value);
        }

        System.out.println("input: " + input);
        System.out.println("FIFO head: " + fifo.peek());
        System.out.println("priority head: " + priority.peek());
        System.out.println("LIFO head: " + lifo.peek());
        System.out.println("FIFO size after peek: " + fifo.size());
        System.out.println("FIFO removal order: " + drain(fifo));
        System.out.println("priority removal order: " + drain(priority));
        System.out.println("LIFO removal order: " + drain(lifo));
        System.out.println("FIFO empty: " + fifo.isEmpty());
        System.out.println("empty peek: " + fifo.peek());
        System.out.println("empty poll: " + fifo.poll());

        try {
            fifo.remove();
        } catch (NoSuchElementException ex) {
            System.out.println("empty remove: NoSuchElementException");
        }
        try {
            fifo.element();
        } catch (NoSuchElementException ex) {
            System.out.println("empty element: NoSuchElementException");
        }

        Queue<String> repeated = new ArrayDeque<>();
        repeated.offer("A");
        repeated.offer("A");
        System.out.println("duplicates: " + drain(repeated));
    }
}
```

Biên dịch theo mức Java 17 và chạy:

```shell
javac --release 17 -encoding UTF-8 QueuePoliciesDemo.java
java QueuePoliciesDemo
```

Stdout:

```text
input: [30, 10, 20]
FIFO head: 30
priority head: 10
LIFO head: 20
FIFO size after peek: 3
FIFO removal order: [30, 10, 20]
priority removal order: [10, 20, 30]
LIFO removal order: [20, 10, 30]
FIFO empty: true
empty peek: null
empty poll: null
empty remove: NoSuchElementException
empty element: NoSuchElementException
duplicates: [A, A]
```

Cách đọc kết quả:

1. Ba biến đều có kiểu `Queue<Integer>`, nhưng đối tượng phía sau có ba chính sách khác nhau.
2. FIFO trả đầu `30`, vì đó là phần tử được thêm trước.
3. Hàng đợi ưu tiên tự nhiên trả đầu `10`, không phải phần tử được thêm trước.
4. Khung nhìn LIFO trả đầu `20`, phần tử được thêm sau cùng.
5. `peek` không làm giảm kích thước.
6. Hàm `drain` liên tục gọi `poll` và vì thế làm các hàng trong ví dụ rỗng.
7. Kết quả khi rỗng phân biệt rõ cặp `poll/remove` và `peek/element`.
8. Hai giá trị `A` cùng được giữ và cùng được lấy ra.

Hàm `drain` được dùng ở đây cho ba hàng đợi không trì hoãn và không chứa `null`. Với chúng, `poll()` trả `null` khi không còn phần tử. Hàm không được giới thiệu như một thuật toán “chắc chắn lấy hết mọi phần tử” cho tất cả hàng đợi chuyên biệt.

Chương trình lấy thứ tự bằng các lần `poll`. Nó không dùng thứ tự `for-each` của một hàng đợi ưu tiên để suy ra thứ tự xử lý.

## 5. PriorityQueue: ưu tiên quyết định đầu hàng

### 5.1. Phần tử được lấy trước có thể đến sau

`PriorityQueue` chọn đầu theo thứ tự tự nhiên của phần tử hoặc một `Comparator` được truyền vào.

Theo thứ tự tự nhiên của số nguyên, phần tử nhỏ nhất hiện có là đầu. Nếu thêm `30`, rồi `10`, rồi `20`, lần lấy đầu tiên là `10`.

Điều này phù hợp với chính sách ưu tiên và không phải một hàng đợi FIFO bị hỏng. Quy tắc chọn phần tử của nó khác ngay từ thiết kế. [PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

Nếu không truyền `Comparator`, phần tử phải có thứ tự tự nhiên tương thích, thường qua `Comparable`. Một lớp công việc không tự được so theo trường tên `priority` chỉ vì trường đó tồn tại; cần cung cấp quy tắc so sánh phù hợp.

Với đối tượng công việc, “số nhỏ ưu tiên trước” hay “số lớn ưu tiên trước” là quy ước phải thiết kế. Tên trường `priority` không tự quyết định chiều so sánh.

Ví dụ:

```java
Queue<Integer> greatestFirst =
        new PriorityQueue<>(Comparator.reverseOrder());
```

giúp số lớn nhất theo thứ tự số thông thường được chọn trước, vì nó nhỏ nhất theo bộ thứ tự đảo đã cung cấp.

### 5.2. Bằng mức ưu tiên không có nghĩa FIFO trong nhóm

Nếu chỉ so sánh `priority`, hai công việc có cùng mức sẽ cho kết quả so sánh bằng `0`. `PriorityQueue` không cam kết công việc tới trước trong nhóm đó được lấy trước; trường hợp hòa được chọn tùy ý theo hợp đồng.

Không dùng một lần chạy thấy “A trước B” để suy ra tính ổn định cho mọi dữ liệu hoặc mọi phiên bản.

Nếu cần FIFO trong cùng mức ưu tiên, phải đưa thứ tự tới vào tiêu chí phụ, chẳng hạn một trường `sequence` được gán theo quy tắc đã xác định:

```java
Comparator<Job> order = Comparator.comparingInt(Job::priority)
        .thenComparingLong(Job::sequence);
```

Quy tắc tổng thể vẫn là ưu tiên trước, rồi mới đến sequence. Nó **không trở thành FIFO toàn cục**: một công việc ưu tiên cao tới sau vẫn có thể đi trước một công việc ưu tiên thấp tới sớm.

Trong ví dụ một luồng ở phần sau, các sequence `0, 1, 2, 3` biểu diễn thứ tự đưa công việc vào. Với một thiết kế nhiều luồng, cần định nghĩa riêng cách cấp và ý nghĩa thứ tự này; hàng đợi không tự tạo trường sequence cho người dùng.

### 5.3. PriorityQueue giữ các phần tử cùng độ ưu tiên

`PriorityQueue` không phải `TreeSet`. Kết quả so sánh bằng `0` không làm hai công việc tự bị gộp thành một phần tử.

Hai công việc khác nhau cùng priority có thể cùng nằm trong hàng. Việc thiếu tiêu chí phụ làm thứ tự lấy giữa chúng không được cam kết, không có nghĩa một công việc bị loại trùng.

Nếu ứng dụng cần không có hai công việc cùng mã, cần một quy tắc quản lý mã riêng. Bộ so sánh ưu tiên không phải cơ chế loại trùng.

### 5.4. Không dùng iterator để chứng minh thứ tự ưu tiên

Hợp đồng `PriorityQueue` không bảo đảm `iterator`, `for-each` hoặc mảng lấy từ hàng được sắp đúng thứ tự các lần `poll`.

Một hàng đợi ưu tiên dựa trên heap không cần duy trì cả cấu trúc thành một dãy đã sắp xếp hoàn chỉnh. Nó cần cung cấp đúng đầu hàng cho các thao tác truy xuất tương ứng.

Nếu muốn xem thứ tự lấy mà giữ nguyên hàng gốc, có thể tạo một bản sao ưu tiên với cùng quy tắc rồi `poll` bản sao. Nếu muốn một danh sách sắp xếp để trình bày, tạo danh sách và sắp bằng bộ so sánh phù hợp.

Đừng in trực tiếp `PriorityQueue` rồi chép output đó thành thứ tự xử lý được bảo đảm. [PriorityQueue: đầu hàng, trường hợp hòa và duyệt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

### 5.5. Khóa ưu tiên cần ổn định khi công việc đang chờ

Nếu sửa trường dùng để so sánh của một đối tượng đã ở trong hàng, cấu trúc không tự biết phải sắp lại vì người gọi vừa đổi một trường.

Ưu tiên đối tượng công việc có khóa so sánh bất biến hoặc thiết kế rõ quy trình cập nhật. Trong ví dụ, record có các thành phần `String`, `int`, `long` ổn định.

## 6. LIFO và Deque: chọn đầu thêm/lấy làm thay đổi chính sách

LIFO là **vào sau, ra trước** — last in, first out, thường gọi là ngăn xếp (stack).

Nếu thêm `A`, `B`, `C` rồi lấy theo LIFO, kết quả là:

```text
C, B, A
```

`Deque` là hàng hai đầu, cho phép thao tác ở cả đầu và cuối. Cùng một triển khai như `ArrayDeque` có thể phục vụ hai cách sử dụng:

| Cách dùng | Thêm | Lấy | Thứ tự với A, B, C được thêm lần lượt |
| --- | --- | --- | --- |
| FIFO | `offerLast` | `pollFirst` | A, B, C |
| LIFO theo đầu trước | `push` hoặc thao tác thêm đầu tương ứng | `pop` hoặc thao tác lấy đầu tương ứng | C, B, A |

`push` thêm vào đầu trước; `pop` lấy và xóa từ đầu trước. Thêm và lấy cùng phía làm phần tử mới nhất được lấy trước. [Deque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

Khi sử dụng các phương thức `Queue` thông thường của `ArrayDeque`, thêm/lấy có ý nghĩa FIFO. Khi dùng `push/pop`, ta đang sử dụng nó như ngăn xếp.

Không trộn tùy tiện các thao tác hai đầu rồi vẫn khẳng định mọi dữ liệu tuân thủ một lịch sử FIFO. Chính sách sử dụng phải thống nhất giữa các phần của chương trình có quyền sửa cùng cấu trúc.

### Có thể có một biến kiểu Queue mà hành vi là LIFO

Java cung cấp một khung nhìn:

```java
Queue<String> lifo =
        Collections.asLifoQueue(new ArrayDeque<>());
```

Khung nhìn chuyển các thao tác hàng đợi sang các thao tác ngăn xếp tương ứng trên deque nền. Đây là ví dụ trực tiếp rằng kiểu `Queue` không tự bảo đảm FIFO.

Nó là một khung nhìn dùng deque nền, không phải một bản sao dữ liệu độc lập. Nếu giữ thêm tham chiếu tới deque, thao tác qua hai phía đều tác động tới cùng dữ liệu. [Collections.asLifoQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#asLifoQueue(java.util.Deque))

## 7. Chương trình đầy đủ: ưu tiên có tiêu chí phụ và cách dùng Deque

Lưu mã vào **PriorityAndStackDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Queue;

public class PriorityAndStackDemo {
    private record Job(String name, int priority, long sequence) {
    }

    private static List<String> jobOrder(Queue<Job> jobs) {
        List<String> result = new ArrayList<>();
        Job job;
        while ((job = jobs.poll()) != null) {
            result.add(job.name());
        }
        return result;
    }

    public static void main(String[] args) {
        Comparator<Job> order = Comparator.comparingInt(Job::priority)
                .thenComparingLong(Job::sequence);
        Queue<Job> jobs = new PriorityQueue<>(order);
        jobs.offer(new Job("report", 2, 0));
        jobs.offer(new Job("parse", 1, 1));
        jobs.offer(new Job("index", 1, 2));
        jobs.offer(new Job("notify", 2, 3));
        System.out.println("priority then sequence: " + jobOrder(jobs));

        Queue<Job> tied = new PriorityQueue<>(
                Comparator.comparingInt(Job::priority));
        tied.offer(new Job("A", 1, 0));
        tied.offer(new Job("B", 1, 1));
        System.out.println("equal-priority count: " + tied.size());
        List<String> tiedNames = jobOrder(tied);
        tiedNames.sort(Comparator.naturalOrder());
        System.out.println("all tied names, sorted afterward: " + tiedNames);

        Queue<Integer> greatestFirst =
                new PriorityQueue<>(Comparator.reverseOrder());
        greatestFirst.addAll(List.of(30, 10, 20));
        List<Integer> descending = new ArrayList<>();
        Integer number;
        while ((number = greatestFirst.poll()) != null) {
            descending.add(number);
        }
        System.out.println("reverse-comparator order: " + descending);

        Deque<String> fifo = new ArrayDeque<>();
        fifo.offerLast("A");
        fifo.offerLast("B");
        fifo.offerLast("C");
        System.out.println("deque FIFO first: " + fifo.pollFirst());

        Deque<String> stack = new ArrayDeque<>();
        stack.push("A");
        stack.push("B");
        stack.push("C");
        System.out.println("deque stack first: " + stack.pop());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 PriorityAndStackDemo.java
java PriorityAndStackDemo
```

Stdout:

```text
priority then sequence: [parse, index, report, notify]
equal-priority count: 2
all tied names, sorted afterward: [A, B]
reverse-comparator order: [30, 20, 10]
deque FIFO first: A
deque stack first: C
```

Cách đọc kết quả:

1. `report` được thêm sớm nhất nhưng priority `2`; hai công việc priority `1` được lấy trước theo quy ước số nhỏ trước của ví dụ.
2. Trong nhóm priority `1`, sequence `1` của `parse` đứng trước sequence `2` của `index`.
3. Hai công việc chỉ được so theo cùng priority vẫn cùng tồn tại: kích thước là `2`.
4. Danh sách tên của nhóm hòa được **sắp sau khi lấy ra** trước khi in. Dòng `[A, B]` đó không khẳng định hàng ưu tiên đã lấy A trước B.
5. Bộ so sánh đảo cho dãy số lấy `30` trước `20`, rồi `10`.
6. Deque dùng FIFO trả `A`; deque dùng ngăn xếp trả `C`.

Hai chương trình độc lập trong bài đã được biên dịch bằng `--release 17` và chạy đối chiếu đúng stdout. Tùy chọn này kiểm tra mức ngôn ngữ/API và tạo bytecode tương thích Java 17; nó không khẳng định JVM thực thi chính là JDK 17.

## 8. Các chính sách khác và những thuộc tính không được gộp với FIFO

### 8.1. Hàng đợi trì hoãn còn xét khi nào được lấy

`DelayQueue` là một ví dụ chuyên biệt: phần tử mang thông tin trì hoãn và chỉ có thể được lấy theo các điều kiện hết hạn của lớp.

Một phần tử được đưa vào sau nhưng tới thời điểm được phép lấy sớm hơn không phải chờ chỉ vì nó được thêm sau. Thứ tự xử lý không được suy ra đơn thuần từ thứ tự chèn.

Một chi tiết quan trọng: `poll()` có thể trả `null` khi chưa có phần tử nào hết hạn, dù cấu trúc vẫn giữ các phần tử chưa tới hạn. Vì vậy, vòng lặp dừng khi `poll` trả `null` không đồng nghĩa đã lấy hết mọi phần tử của loại hàng này. [DelayQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/DelayQueue.html)

Bài này không dùng ví dụ stdout dựa vào chờ thời gian, vì trọng tâm là phân biệt chính sách lấy với thứ tự chèn.

### 8.2. Chính sách thứ tự, giới hạn và chờ là các trục riêng

| Thuộc tính | Câu hỏi |
| --- | --- |
| Thứ tự | FIFO, LIFO, ưu tiên hay theo điều kiện thời gian? |
| Dung lượng | Có giới hạn số phần tử hay tự tăng? |
| Cách thất bại/chờ | Trả ngay, ném ngoại lệ hay có thao tác chờ? |
| Truy cập đồng thời | Triển khai có hỗ trợ nhiều luồng theo hợp đồng nào? |

Một hàng FIFO có thể có giới hạn. Một hàng ưu tiên có thể không có giới hạn cố định theo API. Có khả năng chờ không có nghĩa nó tự phải là FIFO.

`Queue` không khai báo các phương thức chờ như `put` và `take`; chúng thuộc `BlockingQueue`. Giao diện mở rộng bổ sung khả năng chờ, còn thứ tự cụ thể vẫn cần đọc ở triển khai. [BlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

Ví dụ `ArrayBlockingQueue` có dung lượng cố định và chính sách phần tử FIFO. `PriorityQueue` là hàng ưu tiên tự tăng dung lượng lưu nội bộ, không có giới hạn cố định kiểu đó theo hợp đồng của lớp. Không suy ra cơ chế chờ hay khả năng nhiều luồng từ tên biến `Queue`. [ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html), [PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

`ArrayDeque` và `PriorityQueue` thông thường không tự đồng bộ cho nhiều luồng cùng sửa. Những ví dụ trong bài được xét trong một luồng, không phải mẫu điều phối đa luồng.

## 9. Chọn cấu trúc theo yêu cầu xử lý

| Yêu cầu | Hướng sử dụng phù hợp |
| --- | --- |
| Xử lý theo thứ tự được đưa vào trong một luồng | Queue dùng ArrayDeque với kỷ luật FIFO |
| Cần lấy công việc theo một mức ưu tiên | PriorityQueue với quy tắc so sánh rõ |
| Cùng ưu tiên phải theo thứ tự đã xác định | Thêm tiêu chí phụ phù hợp, chẳng hạn sequence |
| Cần quay lại bước mới nhất trước | Deque dùng như ngăn xếp |
| Chỉ lấy khi đã tới hạn | Cân nhắc cấu trúc thời gian như DelayQueue |
| Có giới hạn và cần thao tác chờ giữa các luồng | Xem hợp đồng BlockingQueue và triển khai cụ thể |

Một số câu hỏi thiết kế cần trả lời trước:

1. Điều gì quyết định công việc tiếp theo?
2. Có cho phần tử bằng nhau xuất hiện nhiều lần không?
3. Nếu cùng ưu tiên, có cần một thứ tự phụ được bảo đảm không?
4. Khi hết chỗ hoặc không có phần tử lấy được, muốn trả ngay hay chờ?
5. Ai sở hữu và được phép sửa hàng đợi?

Với hàng ưu tiên, nếu các công việc ưu tiên cao liên tục tới, một công việc ưu tiên thấp có thể phải chờ lâu. Đây là hệ quả chính sách cần được xét trong bài toán, không phải lỗi vì “queue lẽ ra phải FIFO”. Việc thay đổi ưu tiên theo thời gian hoặc bảo đảm cơ hội xử lý là thiết kế bổ sung, không có sẵn chỉ từ `PriorityQueue`.

## 10. Hiểu chi phí theo triển khai thay vì gán một con số cho Queue

Tên giao diện `Queue` không hứa mọi thao tác của mọi triển khai đều O(1).

Một vài đặc tính liên quan tới các ví dụ:

- `ArrayDeque` có mô hình thời gian hằng số khấu hao cho phần lớn thao tác hai đầu thông thường.
- `PriorityQueue` cần duy trì cấu trúc ưu tiên; tài liệu mô tả thêm và lấy đầu theo O(log n), trong khi xem đầu là O(1).
- Tìm hoặc xóa một phần tử theo giá trị bằng các thao tác của `Collection` có thể có chi phí khác với lấy đầu hàng.

Những khác biệt đó phù hợp với nhiệm vụ của cấu trúc: lấy đúng ưu tiên khác với chỉ quản lý hai đầu theo lịch sử thao tác. Không lựa chọn một hàng ưu tiên cho một yêu cầu FIFO chỉ vì cả hai đều có `offer` và `poll`. [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html), [PriorityQueue: chi phí thao tác](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

Không dùng thứ tự `toString` hoặc một phép chạy nhỏ để đo tốc độ hay chứng minh mọi bảo đảm thứ tự. Tính đúng của chính sách được đọc từ hợp đồng và kiểm chứng bằng thao tác tương ứng.

## 11. Những lỗi thường gặp

| Cách hiểu hoặc cách viết | Vấn đề | Cách sửa |
| --- | --- | --- |
| Mọi Queue đều FIFO | Nhầm giao diện với chính sách triển khai | Xác định phần tử đầu được chọn theo quy tắc nào |
| PriorityQueue phải lấy phần tử đến sớm nhất | Ưu tiên mới là tiêu chí chính | Đọc Comparator hoặc thứ tự tự nhiên |
| Số priority lớn luôn được xử lý trước | Chiều ưu tiên là quy ước của bộ so sánh | Viết và kiểm tra chiều so sánh |
| Cùng priority chắc chắn FIFO | Trường hợp hòa không được PriorityQueue cam kết ổn định | Thiết kế tiêu chí phụ khi cần |
| Compare bằng 0 làm PriorityQueue loại trùng | Mang quy tắc của tập sắp xếp sang hàng đợi | Phân biệt thứ tự với việc giữ phần tử |
| For-each của PriorityQueue chính là thứ tự poll | Bộ duyệt không hứa thứ tự ưu tiên | Poll hoặc sắp một bản sao để quan sát đúng câu hỏi |
| Peek làm chuyển sang phần tử tiếp theo | Peek không xóa đầu hàng | Dùng poll khi cần lấy và loại khỏi hàng |
| Offer không bao giờ có ngoại lệ | Vẫn có thể có phần tử không hợp lệ | Phân biệt thiếu dung lượng với vi phạm miền đầu vào |
| Offer tự chờ khi đầy | Queue không cung cấp thao tác chờ theo nghĩa đó | Dùng giao diện/phương thức chờ phù hợp nếu cần |
| Gọi push/pop rồi vẫn nghĩ đang FIFO | Đã dùng cùng một đầu như ngăn xếp | Giữ nhất quán cách dùng hai đầu |
| Poll null luôn có nghĩa mọi hàng đều không chứa phần tử | Hàng chuyên biệt có điều kiện lấy như DelayQueue | Đọc hợp đồng cụ thể |
| FIFO bảo đảm hoàn thành công việc cùng thứ tự | Thứ tự lấy và thời gian xử lý bên ngoài khác nhau | Tách hai khái niệm |

Khi dự đoán output, hãy ghi lại loại triển khai, các thao tác đã dùng để đưa vào/lấy ra, và quy tắc chọn đầu. Chỉ nhìn tên biến `queue` không đủ.

## 12. Tự luyện và đối chiếu

### Bài 1: cùng dữ liệu, ba chính sách

Đưa lần lượt `8, 3, 5` vào ba hàng rỗng: FIFO, ưu tiên số nhỏ trước và LIFO. Lấy cho tới khi hết các phần tử có thể lấy của ba hàng thông thường này.

Đối chiếu:

```text
FIFO:     8, 3, 5
Ưu tiên:  3, 5, 8
LIFO:     5, 3, 8
```

Cần giải thích mỗi phần tử đầu tiên được chọn theo quy tắc nào.

### Bài 2: xem hay lấy?

Một FIFO có `[A, B]`:

```text
peek() → A; hàng vẫn [A, B]
poll() → A; hàng còn [B]
peek() → B; hàng vẫn [B]
poll() → B; hàng rỗng
poll() → null
```

Nếu thay lời gọi cuối bằng `remove()`, với hàng đã rỗng sẽ nhận `NoSuchElementException`.

### Bài 3: ưu tiên trước, sequence sau

Ba công việc được đưa vào:

```text
A: priority=2, sequence=0
B: priority=1, sequence=1
C: priority=1, sequence=2
```

Với bộ so ưu tiên tăng dần rồi sequence tăng dần, thứ tự là `B, C, A`.

Nếu bỏ tiêu chí sequence và chỉ so priority, vẫn có ba phần tử, A vẫn đứng sau nhóm priority 1, nhưng không được khẳng định B hay C lấy trước chỉ dựa vào thứ tự tới.

### Bài 4: Deque đang là FIFO hay LIFO?

- Thêm A, B, C bằng `offerLast`, lấy bằng `pollFirst`: FIFO.
- Thêm A, B, C bằng `push`, lấy bằng `pop`: LIFO.
- Trộn thêm ở hai đầu mà không có một quy tắc chung: không thể chỉ gọi tên cấu trúc để kết luận lịch sử là FIFO.

### Bài 5: đọc đúng offer thất bại

Một `ArrayBlockingQueue` dung lượng 2 đang có `A, B`. `offer("C")` trả về `false` vì không có chỗ để thêm ngay. Hai phần tử cũ vẫn ở đó theo FIFO.

Nếu dùng `add("C")` trong trạng thái đầy đó, tình huống thiếu chỗ được báo bằng `IllegalStateException`. Đó là khác biệt cách báo thất bại, không phải một chính sách thứ tự mới.

## 13. Tài liệu tra cứu

- [Queue Java 17 — giao diện, đầu hàng và các chính sách thứ tự](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)
- [ArrayDeque — triển khai deque cho cách dùng FIFO/LIFO](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)
- [Deque — thao tác hai đầu và ngăn xếp](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)
- [PriorityQueue — ưu tiên, trường hợp hòa và giới hạn thứ tự duyệt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)
- [Collections.asLifoQueue — khung nhìn Queue theo LIFO](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#asLifoQueue(java.util.Deque))
- [BlockingQueue — các khả năng chờ riêng](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [ArrayBlockingQueue — hàng FIFO có giới hạn](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)
- [DelayQueue — điều kiện hết hạn trước khi lấy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/DelayQueue.html)

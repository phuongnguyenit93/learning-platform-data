# PriorityQueue và xử lý dữ liệu theo độ ưu tiên trong Java 27

`PriorityQueue<E>` trong `java.util` là một cấu trúc thuộc Java Collections Framework để chọn **phần tử có thứ tự ưu tiên cao nhất theo quy tắc so sánh do chương trình xác định**. Khác với queue FIFO (vào trước, ra trước), thứ tự lấy phần tử của `PriorityQueue` do **natural ordering** (`Comparable`) hoặc một `Comparator` quyết định.

Đối với Java 27, `PriorityQueue` là API Java SE ổn định, không phải tính năng preview. Ví dụ trong bài sử dụng generics, record, method reference và comparator đã được hỗ trợ chính thức; không dựa vào kỹ thuật lỗi thời. Bài học đi từ khái niệm priority heap đến cách thiết kế hàng đợi tác vụ, Top-K và những lưu ý khi dùng trong hệ thống thực tế.

## 1. Hiểu đúng priority queue và phần tử đầu hàng đợi

Giả sử một hệ thống có ba yêu cầu:

- Yêu cầu A: mức ưu tiên 3 (thấp).
- Yêu cầu B: mức ưu tiên 1 (khẩn cấp).
- Yêu cầu C: mức ưu tiên 2 (trung bình).

Nếu quy ước **số nhỏ hơn là khẩn cấp hơn**, thứ tự xử lý cần là **B → C → A**, dù A được đưa vào trước. Với `PriorityQueue`, ta khai báo thứ tự so sánh tương ứng rồi gọi `poll()` để lấy từng yêu cầu.

Theo đặc tả `PriorityQueue` của Java SE 27:

- Queue dựa trên **priority heap**; phần tử đầu (*head*) là phần tử **nhỏ nhất theo comparator/natural ordering**.
- `offer`/`add` thêm phần tử và duy trì thuộc tính heap.
- `peek` xem phần tử đầu mà không xóa; `poll` lấy và xóa phần tử đầu.
- Không bảo đảm thứ tự FIFO cho các phần tử có thứ tự so sánh bằng nhau.
- Không cho phép phần tử `null`. Nếu không cung cấp comparator, các phần tử cần có natural ordering so sánh được với nhau.
- Cấu trúc **không giới hạn số phần tử theo API** (*unbounded*), nhưng vẫn chịu giới hạn bộ nhớ thực tế.
- Không đồng bộ hóa nội bộ để nhiều thread cùng sửa an toàn.

### 1.1. Min-heap không phải danh sách đã sắp xếp

Một **min-heap** bảo đảm phần tử ở gốc nhỏ hơn hoặc bằng các phần tử con theo quy tắc so sánh, nhưng **không** bảo đảm các phần tử còn lại nằm theo thứ tự tăng dần khi duyệt bằng iterator.

Một cách hình dung với các số `[2, 4, 3, 9, 8, 7]`:

```text
          2        ← phần tử nhỏ nhất ở gốc
        /   \
       4     3
      / \   /
     9   8 7

    2 ≤ 4 và 2 ≤ 3
    4 ≤ 9 và 4 ≤ 8
    3 ≤ 7
```

Cây trên chỉ minh họa thuộc tính heap; **không phải biểu diễn bộ nhớ hoặc thứ tự nội bộ được Java cam kết**. Khi thêm/xóa, cấu trúc có thể được sắp xếp lại để giữ bất biến heap.

Vì thế:

- `peek()` cho biết phần tử được ưu tiên tiếp theo.
- Liên tục `poll()` cho ra các phần tử theo thứ tự ưu tiên.
- `iterator()`, `forEach`, `toArray()`, `toString()` và `stream()` **không được xem là một cách lấy toàn bộ phần tử theo thứ tự ưu tiên**.

## 2. Tạo PriorityQueue và sử dụng các thao tác cơ bản

Ví dụ chạy độc lập với JDK 27:

```java
// File: PriorityNumbersDemo.java
import java.util.PriorityQueue;

public class PriorityNumbersDemo {
    public static void main(String[] args) {
        PriorityQueue<Integer> queue = new PriorityQueue<>();

        queue.offer(8);
        queue.offer(3);
        queue.offer(5);
        queue.offer(3);
        queue.offer(1);

        System.out.println("Số lượng: " + queue.size());
        System.out.println("Đầu hàng đợi: " + queue.peek());

        Integer next;
        while ((next = queue.poll()) != null) {
            System.out.println("Xử lý: " + next);
        }

        System.out.println("Đã rỗng: " + queue.isEmpty());
    }
}
```

Kết quả:

```text
Số lượng: 5
Đầu hàng đợi: 1
Xử lý: 1
Xử lý: 3
Xử lý: 3
Xử lý: 5
Xử lý: 8
Đã rỗng: true
```

`Integer` có natural ordering tăng dần, nên phần tử đầu là số nhỏ nhất. Queue cho phép giá trị lặp lại: hai số `3` đều được giữ và được lấy ra. `poll()` trả `null` khi rỗng; vì `PriorityQueue` cấm chứa phần tử `null`, vòng lặp có thể dùng giá trị trả về để kết thúc.

### 2.1. Các cặp phương thức của Queue

`PriorityQueue` triển khai interface `Queue<E>`. Interface này cung cấp các cặp phương thức có cùng mục đích nhưng **khác cách xử lý khi thất bại/rỗng**.

| Mục đích | Trả giá trị đặc biệt | Phiên bản ném exception | Đặc điểm với PriorityQueue |
| --- | --- | --- | --- |
| Thêm phần tử | `offer(e)` | `add(e)` | Cả hai thêm theo mức ưu tiên; không dùng giá trị `false` làm tín hiệu queue đã đầy vì PriorityQueue không có giới hạn dung lượng logic |
| Xem head | `peek()` trả `null` nếu rỗng | `element()` ném `NoSuchElementException` nếu rỗng | Không xóa phần tử |
| Lấy và xóa head | `poll()` trả `null` nếu rỗng | `remove()` ném `NoSuchElementException` nếu rỗng | Có điều chỉnh lại heap sau khi xóa |
| Xóa phần tử cụ thể | — | `remove(Object)` trả `boolean` | Xóa một phần tử bằng nhau theo `equals`; **khác** `remove()` không tham số |
| Kiểm tra sự hiện diện | `contains(Object)` | — | Quét theo `equals`, không tìm kiếm nhị phân theo comparator |
| Kiểm tra kích thước | `size()` | — | Trả số phần tử hiện có |
| Xem cách so sánh | `comparator()` | — | Trả comparator đã cấu hình hoặc `null` nếu dùng natural ordering |

Nếu queue có thể rỗng trong luồng làm việc bình thường, `poll()` và `peek()` thường thuận tiện. Nếu phần tử bắt buộc phải tồn tại tại điểm gọi, `remove()` hoặc `element()` khiến vi phạm giả định lộ rõ bằng exception.

### 2.2. Độ phức tạp theo tài liệu Java SE 27

| Thao tác | Độ phức tạp của triển khai PriorityQueue |
| --- | --- |
| `offer(e)`, `add(e)` | `O(log n)` |
| `poll()`, `remove()` (xóa head) | `O(log n)` |
| `peek()`, `element()` | `O(1)` |
| `size()` | `O(1)` |
| `contains(Object)` | `O(n)` |
| `remove(Object)` | `O(n)` |

Với `n` là số phần tử. Các độ phức tạp trên là ghi chú triển khai trong API của `PriorityQueue`, không phải lời hứa rằng mọi `Queue` có cùng hiệu năng. Bất kỳ thao tác nào gọi comparator phức tạp cũng phải tính thêm chi phí so sánh.

## 3. Điều khiển mức ưu tiên bằng Comparable và Comparator

### 3.1. Natural ordering: phần tử nhỏ nhất đi trước

Khi không truyền comparator:

```java
PriorityQueue<Integer> minQueue = new PriorityQueue<>();
minQueue.offer(10);
minQueue.offer(30);
minQueue.offer(20);

System.out.println(minQueue.poll()); // 10
System.out.println(minQueue.poll()); // 20
System.out.println(minQueue.poll()); // 30
```

Các kiểu như `Integer` và `String` có natural ordering được định nghĩa qua `Comparable`. Với kiểu tự tạo không triển khai `Comparable`, nếu muốn dùng natural ordering phải tự cài đặt một quy tắc so sánh có ý nghĩa.

Ví dụ:

```java
record Score(String student, int points) implements Comparable<Score> {
    @Override
    public int compareTo(Score other) {
        return Integer.compare(points, other.points);
    }
}
```

Quy tắc ở đây ưu tiên điểm thấp trước; các `Score` bằng điểm vẫn có thể ra theo thứ tự bất kỳ. Lưu ý `record` **không tự triển khai `Comparable`**: chỉ khi khai báo `implements Comparable<Score>` và cài đặt `compareTo` như trên thì mới dùng được natural ordering.

### 3.2. Max-heap: phần tử lớn nhất đi trước

`PriorityQueue` luôn cho ra phần tử **nhỏ nhất theo thứ tự đã cấu hình**. Muốn lấy số lớn nhất trước, hãy **đảo comparator**:

```java
import java.util.Comparator;
import java.util.PriorityQueue;

public class MaxQueueDemo {
    public static void main(String[] args) {
        PriorityQueue<Integer> highestFirst =
                new PriorityQueue<>(Comparator.reverseOrder());

        highestFirst.offer(10);
        highestFirst.offer(30);
        highestFirst.offer(20);

        while (!highestFirst.isEmpty()) {
            System.out.println(highestFirst.poll());
        }
    }
}
```

Kết quả:

```text
30
20
10
```

`Comparator.reverseOrder()` là cách rõ ràng để diễn đạt thứ tự giảm dần của các phần tử có natural ordering. Không cần đổi dữ liệu đầu vào thành số âm để giả lập max-heap.

### 3.3. Comparator nhiều tiêu chí cho tác vụ thực tế

Giả sử hệ thống dùng quy ước:

- Mức độ khẩn cấp `1` được xử lý trước `2`, rồi `3`.
- Các tác vụ cùng mức ưu tiên được xử lý theo **số thứ tự tiếp nhận** (`sequence`), nhỏ trước lớn.

Mã đầy đủ:

```java
// File: PriorityTaskDemo.java
import java.util.Comparator;
import java.util.PriorityQueue;

public class PriorityTaskDemo {
    record Task(String id, int priority, long sequence) {
    }

    public static void main(String[] args) {
        Comparator<Task> byPriorityThenSequence =
                Comparator.comparingInt(Task::priority)
                          .thenComparingLong(Task::sequence);

        PriorityQueue<Task> tasks =
                new PriorityQueue<>(byPriorityThenSequence);

        tasks.offer(new Task("generate-report", 3, 0));
        tasks.offer(new Task("critical-incident", 1, 1));
        tasks.offer(new Task("answer-ticket", 2, 2));
        tasks.offer(new Task("review-payment", 2, 3));

        Task next;
        while ((next = tasks.poll()) != null) {
            System.out.println(next.priority() + ": " + next.id());
        }
    }
}
```

Kết quả:

```text
1: critical-incident
2: answer-ticket
2: review-payment
3: generate-report
```

`Comparator.comparingInt(Task::priority)` quyết định tiêu chí chính; `thenComparingLong(Task::sequence)` quyết định thứ tự cho các trường hợp bằng nhau ở tiêu chí chính. `record` mang dữ liệu bất biến theo component, giúp bảo đảm các khóa so sánh không vô tình đổi trong lúc đang nằm trong queue.

**Lưu ý về tính ổn định:** `PriorityQueue` không bảo đảm FIFO nếu comparator đánh giá hai phần tử bằng nhau. Ví dụ trên có kết quả xác định vì mọi `sequence` là duy nhất và không đổi. Nếu cả `priority` và `sequence` đều trùng, thứ tự giữa các tác vụ đó lại không được bảo đảm. Trong hệ thống đa luồng, bộ đếm thứ tự cần được tạo theo cách đồng bộ/atomic thích hợp.

### 3.4. Quy tắc so sánh đúng và dễ bảo trì

`Comparator` phải tạo ra thứ tự nhất quán: không tùy tiện thay đổi kết quả so sánh của cùng cặp phần tử trong thời gian chúng nằm trong queue.

- Ưu tiên `Comparator.comparingInt(...)`, `comparingLong(...)`, `thenComparing(...)` hoặc `Integer.compare(a, b)`.
- Tránh viết `a.priority() - b.priority()`: phép trừ `int` có thể **overflow** và tạo thứ tự sai.
- Đặt tiêu chí phụ đủ rõ khi cần kết quả lặp lại được (deterministic).
- Tránh gọi I/O, tạo side effect hoặc đọc giá trị biến động theo thời gian từ comparator; heap giả định quy tắc so sánh nhất quán.
- Hai phần tử có `compare(a,b) == 0` **không nhất thiết** có `a.equals(b) == true`. Queue cho phép phần tử trùng; nó **không phải Set**.
- `PriorityQueue` cấm `null` bất kể comparator có xử lý null hay không.

## 4. Duyệt và xuất dữ liệu đúng thứ tự ưu tiên

Một lỗi phổ biến là tin rằng `for (E value : queue)` hoặc `queue.stream()` sẽ trả các phần tử theo thứ tự `poll()`. Điều này **không được bảo đảm**.

Không nên sử dụng mã sau để hiển thị danh sách ưu tiên:

```java
// Không bảo đảm thứ tự ưu tiên:
for (Task task : tasks) {
    System.out.println(task);
}

// stream() cũng không cung cấp thứ tự ưu tiên sẵn có:
tasks.stream().forEach(System.out::println);
```

### 4.1. Lấy theo thứ tự bằng poll — đồng thời xóa queue

```java
while (!queue.isEmpty()) {
    System.out.println(queue.poll());
}
```

Mỗi lần `poll` lấy head, rồi duy trì heap để head kế tiếp đúng theo comparator. Khi vòng lặp kết thúc, queue nguồn đã **rỗng**.

### 4.2. Tạo bản sao để duyệt có thứ tự mà không phá queue gốc

```java
PriorityQueue<Task> snapshot = new PriorityQueue<>(tasks);

while (!snapshot.isEmpty()) {
    Task next = snapshot.poll();
    System.out.println(next.id());
}

System.out.println("Queue gốc còn: " + tasks.size());
```

Constructor sao chép từ `PriorityQueue` giữ quy tắc ordering của queue nguồn. Việc liên tục `poll()` trên **bản sao** cho kết quả theo ưu tiên và không thay đổi cấu trúc queue ban đầu. Tuy nhiên, đây là sao chép **nông**: phần tử vẫn là các object tham chiếu ban đầu. Nếu phần tử mutable và khóa comparator bị đổi, chỉ sao chép queue không giải quyết được vấn đề.

Nếu cần danh sách cuối cùng có thứ tự, có thể chụp phần tử sang `List` rồi gọi `sort(comparator)` với **cùng comparator**. Khi dùng natural ordering, sắp xếp theo natural ordering tương ứng. Thao tác này phù hợp để xuất báo cáo, trong khi `PriorityQueue` tối ưu cho việc lặp lại chọn phần tử ưu tiên nhất.

## 5. Thay đổi độ ưu tiên, xóa hoặc hủy tác vụ

`PriorityQueue` không có API kiểu `decreaseKey` hoặc `updatePriority` để sửa trực tiếp khóa so sánh của một phần tử rồi tự tái tạo heap.

**Không nên sửa trường khóa của object đang ở trong queue rồi kỳ vọng `peek()` hoặc `poll()` tự thay đổi thứ tự.** Comparator không được chạy lại cho toàn bộ phần tử chỉ vì object bị mutate.

Cách xử lý với tập dữ liệu vừa phải:

1. Xác định phần tử cần thay bằng định danh hoặc reference đang quản lý.
2. Xóa phần tử cũ bằng `remove(Object)`.
3. Tạo bản ghi mới với độ ưu tiên mới rồi `offer(...)` trở lại.

Ví dụ (dùng record `Task` khai báo trong `PriorityTaskDemo` ở trên):

```java
Task oldTask = new Task("answer-ticket", 2, 2);

// Giả sử oldTask đúng bằng phần tử đang có trong queue:
if (tasks.remove(oldTask)) {
    tasks.offer(new Task(oldTask.id(), 1, oldTask.sequence()));
}
```

`remove(Object)` dùng quy tắc `equals` để tìm một phần tử và có chi phí `O(n)`. Nếu hai phần tử bằng nhau theo `equals` cùng có mặt, API chỉ bảo đảm xóa **một** phần tử khớp. Vì vậy, ứng dụng quản lý tác vụ nên có định danh rõ ràng, không lấy mỗi `priority` làm định danh.

Với bài toán thuật toán lớn (chẳng hạn đường đi ngắn nhất), một kỹ thuật phổ biến là **thêm bản ghi mới và bỏ qua bản ghi cũ** khi lấy ra, bằng cách so sánh bản ghi với trạng thái mới nhất trong map. Kỹ thuật *lazy invalidation* chỉ nên dùng khi ứng dụng kiểm soát được tính đúng đắn và chi phí bộ nhớ của các bản ghi cũ.

## 6. Ví dụ ứng dụng: tìm K giá trị lớn nhất trong một dòng dữ liệu

Nếu cần giữ **K số lớn nhất** trong `n` số, ta có thể dùng một **min-heap có tối đa K phần tử**:

1. Khi heap chưa đủ K phần tử, thêm phần tử mới.
2. Khi đủ K, head là phần tử **nhỏ nhất trong nhóm K giá trị đã giữ**.
3. Nếu số mới lớn hơn head, xóa head rồi thêm số mới; nếu không, bỏ qua.
4. Sau khi xử lý hết đầu vào, heap chứa K số lớn nhất (hoặc ít hơn nếu đầu vào ngắn).

Mã độc lập:

```java
// File: TopKDemo.java
import java.util.ArrayList;
import java.util.List;
import java.util.PriorityQueue;

public class TopKDemo {
    static List<Integer> largestK(List<Integer> values, int k) {
        if (k < 0) {
            throw new IllegalArgumentException("k must not be negative");
        }
        if (k == 0) {
            return List.of();
        }

        PriorityQueue<Integer> minHeap = new PriorityQueue<>();

        for (int number : values) {
            if (minHeap.size() < k) {
                minHeap.offer(number);
            } else if (number > minHeap.peek()) {
                minHeap.poll();
                minHeap.offer(number);
            }
        }

        List<Integer> result = new ArrayList<>(minHeap.size());
        while (!minHeap.isEmpty()) {
            result.add(minHeap.poll()); // Thứ tự tăng dần trong nhóm Top-K
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println(largestK(List.of(9, 4, 8, 16, 12, 3), 3));
    }
}
```

Kết quả:

```text
[9, 12, 16]
```

Ví dụ trả **K phần tử lớn nhất (giữ cả giá trị trùng nếu có)** và danh sách kết quả theo thứ tự **tăng dần**. Nếu mục tiêu là đưa phần tử lớn nhất ra đầu danh sách, có thể đảo/sắp xếp bản kết quả sau khi thuật toán kết thúc.

- Thời gian: `O(n log k)` khi `k ≥ 1` và nhỏ hơn đáng kể so với `n` (chính xác hơn, heap có tối đa `min(k,n)` phần tử).
- Bộ nhớ bổ sung: `O(min(k,n))` cho heap, cộng danh sách kết quả có cùng bậc.
- Nếu `k` lớn hơn số lượng đầu vào, trả toàn bộ số đã nhập theo thứ tự tăng dần.
- Nếu `k == 0`, trả danh sách rỗng. Nếu `k < 0`, ném `IllegalArgumentException`.

Đây là một trường hợp `PriorityQueue` thường hiệu quả hơn việc sắp xếp toàn bộ `n` phần tử chỉ để lấy một nhóm K nhỏ.

## 7. Ví dụ ứng dụng: chọn công việc có hạn xử lý gần nhất

`PriorityQueue` cũng có thể xếp các công việc theo thời điểm cần chạy:

```java
// File: DueTasksDemo.java
import java.time.Instant;
import java.util.Comparator;
import java.util.PriorityQueue;

public class DueTasksDemo {
    record DueTask(String id, Instant dueAt) {
    }

    public static void main(String[] args) {
        PriorityQueue<DueTask> jobs =
                new PriorityQueue<>(Comparator.comparing(DueTask::dueAt));

        jobs.offer(new DueTask(
                "invoice", Instant.parse("2026-11-27T10:00:00Z")));
        jobs.offer(new DueTask(
                "notification", Instant.parse("2026-11-27T09:00:00Z")));

        Instant now = Instant.parse("2026-11-27T09:30:00Z");

        while (!jobs.isEmpty() && !jobs.peek().dueAt().isAfter(now)) {
            System.out.println("Ready: " + jobs.poll().id());
        }
        DueTask waiting = jobs.peek();
        System.out.println("Waiting: "
                + (waiting == null ? "(none)" : waiting.id()));
    }
}
```

Kết quả:

```text
Ready: notification
Waiting: invoice
```

`peek` giúp kiểm tra công việc sớm nhất. Khi `dueAt` chưa đến thời điểm `now`, chương trình để công việc trong queue thay vì xử lý ngay. Nhánh kiểm tra `waiting == null` cũng xử lý an toàn trường hợp tất cả công việc đã được lấy ra.

**Cảnh báo:** `PriorityQueue` không tự gọi callback, không đợi tới mốc thời gian, không có cơ chế `take()` chờ khi rỗng. Ví dụ trên chỉ minh họa việc **chọn** công việc đến hạn trong một lần kiểm tra. Để triển khai scheduler thực sự, có thể cân nhắc `ScheduledExecutorService`; với hàng đợi phần tử có độ trễ và nhu cầu chờ đến hạn, dùng `DelayQueue` (phần tử phải triển khai `Delayed`). Không xây scheduler bằng vòng lặp bận liên tục gọi `peek()` mà không có chiến lược chờ.

## 8. Giới hạn an toàn và vận hành

### 8.1. PriorityQueue không thread-safe

Theo Java SE 27, `PriorityQueue` không được đồng bộ hóa. Nếu có nhiều thread truy cập cùng queue và ít nhất một thread sửa nội dung, chương trình phải dùng chiến lược đồng bộ phù hợp hoặc thay bằng cấu trúc thread-safe tương ứng.

Đối với producer–consumer có nhiều thread và cần ưu tiên:

```java
import java.util.concurrent.PriorityBlockingQueue;

PriorityBlockingQueue<Integer> work = new PriorityBlockingQueue<>();
work.offer(3);
work.offer(1);

Integer highestPriority = work.take(); // 1; take() chờ khi queue rỗng
```

Ví dụ trên là **mảnh code đặt trong method có thể khai báo `throws InterruptedException`** hoặc bắt/khôi phục ngắt thích hợp. `PriorityBlockingQueue` hỗ trợ đồng bộ và `take()` chờ khi chưa có phần tử; nhưng queue này vẫn **unbounded**, không tự cung cấp cơ chế giới hạn số việc tồn đọng. Các phần tử đồng mức ưu tiên cũng không được bảo đảm thứ tự FIFO nếu không có khóa phụ.

Với hệ thống cần **backpressure hoặc giới hạn dung lượng**, phải thiết kế cơ chế giới hạn bên ngoài, hoặc chọn loại queue/kiến trúc phù hợp. `new PriorityQueue<>(1000)` và `new PriorityBlockingQueue<>(1000)` chỉ chỉ định **sức chứa ban đầu**, không phải giới hạn tối đa 1000 phần tử.

### 8.2. Không để ưu tiên phụ thuộc vào state mutable

Nếu comparator đọc `task.priority()` từ một object mutable, việc sửa `priority` sau khi `offer` sẽ làm heap có thể bị sai thứ tự. Hãy:

- Ưu tiên record hoặc object bất biến cho các khóa so sánh.
- Khi thay đổi mức ưu tiên, xóa và thêm lại một bản ghi mới, hoặc dùng chiến lược lazy invalidation có kiểm soát.
- Không dùng comparator tham chiếu đồng hồ hiện tại, bộ nhớ ngoài hoặc biến cấu hình thay đổi liên tục.
- Tránh gọi method có side effect trong comparator vì comparator có thể được gọi nhiều lần, với thứ tự không được API cam kết.

### 8.3. Độ ưu tiên không bảo đảm tính công bằng

Một tác vụ mức `3` có thể phải chờ rất lâu nếu dòng tác vụ mức `1` tiếp tục được thêm vào. Đây là nguy cơ **starvation** của chính sách ưu tiên, không phải lỗi của heap.

Nếu hệ thống cần thời gian chờ có giới hạn, cân nhắc bổ sung chính sách như **aging** (tăng dần ưu tiên của tác vụ đang chờ), phân nhóm mức ưu tiên, quota cho từng loại việc, hoặc lịch xử lý vòng. Nếu giá trị ưu tiên thay đổi theo aging, phải cập nhật cấu trúc queue đúng cách; không để comparator đọc biến ưu tiên đang đổi mà không tái cấu trúc heap.

### 8.4. Khả năng dùng bộ nhớ

`PriorityQueue` được mô tả là *unbounded*: số phần tử không bị giới hạn bởi một tham số maximum capacity. Kích thước mảng heap bên trong tăng khi cần; chi tiết chính sách tăng dung lượng **không** phải hợp đồng ổn định của API.

Với hệ thống nhận tác vụ nhanh hơn tốc độ xử lý, cần quan sát chiều dài queue, tốc độ vào/ra và dung lượng heap. `size()` lớn liên tục là tín hiệu cần điều tiết luồng dữ liệu, tăng năng lực xử lý hoặc đặt chính sách từ chối/giảm tải phù hợp.

## 9. Chọn cấu trúc dữ liệu phù hợp

| Nhu cầu | Cấu trúc/API cân nhắc | Vì sao |
| --- | --- | --- |
| Liên tục lấy phần tử nhỏ nhất/lớn nhất theo comparator | `PriorityQueue` | `peek` hằng số, `offer`/`poll` logarithmic |
| Duyệt toàn bộ dữ liệu đã sắp xếp một lần | `List` rồi `sort` | Không cần heap nếu chủ yếu xử lý theo một lượt |
| Nhận phần tử theo thứ tự FIFO | `ArrayDeque` hoặc queue FIFO phù hợp | Thứ tự theo thời điểm vào, không theo ưu tiên |
| Cần xem cả min và max/tra cứu tập hợp có thứ tự | `TreeSet`/`TreeMap` tùy bài toán | Có phép duyệt theo thứ tự, nhưng semantics của set/map khác queue và loại phần tử trùng theo comparator |
| Nhiều thread cùng xử lý công việc theo thứ tự ưu tiên | `PriorityBlockingQueue` | Thread-safe, có `take()`; vẫn không giới hạn dung lượng và không tự ổn định các tie |
| Lấy phần tử chỉ sau khi hết thời gian delay | `DelayQueue` | `take()` chờ đến khi một phần tử `Delayed` đủ điều kiện |
| Cần chạy tác vụ sau delay/theo lịch bằng executor | `ScheduledExecutorService` | Quản lý lập lịch thực thi, không chỉ dữ liệu chờ xử lý |
| Chỉ cần giữ K phần tử lớn nhất của tập dữ liệu lớn | `PriorityQueue` kích thước ≤ K | Không cần sắp xếp toàn bộ nguồn |

Đừng lựa chọn `PriorityQueue` chỉ vì tên nghe có vẻ xử lý nhanh. Nó phù hợp nhất khi cần **lặp lại việc chọn phần tử đứng đầu theo một quy tắc ưu tiên**, không phải khi cần truy cập ngẫu nhiên hoặc tìm kiếm một phần tử theo mã định danh.

## 10. Lỗi thường gặp và cách khắc phục

| Vấn đề | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `poll()` trả thứ tự ngược mong muốn | Comparator đang xếp theo hướng trái với chính sách ưu tiên | Định nghĩa rõ ưu tiên số nhỏ/lớn; dùng `reverseOrder()` hoặc comparator phù hợp |
| `forEach`/`stream` in ra thứ tự không đúng kỳ vọng | Iterator và spliterator không cam kết sorted order | Sao chép queue rồi `poll`, hoặc sắp xếp snapshot với comparator |
| Hai task cùng mức ưu tiên đổi thứ tự giữa các lần chạy | `PriorityQueue` không stable khi comparator đánh giá bằng nhau | Thêm khóa phụ `sequence`, bảo đảm thứ tự đó là duy nhất |
| Chèn `null` gặp `NullPointerException` | PriorityQueue cấm phần tử null | Biểu diễn trạng thái thiếu dữ liệu bằng kiểu khác; không dùng null làm nhiệm vụ |
| Chèn kiểu không so sánh được gặp `ClassCastException` | Không có comparator hợp lệ/natural ordering phù hợp | Cung cấp `Comparator<E>` hoặc triển khai `Comparable` nhất quán |
| `peek()` trả `null` rồi gọi method bị lỗi | Queue rỗng | Kiểm tra `peek() != null` hoặc `isEmpty()` trước khi dùng |
| `remove()` ném `NoSuchElementException` | Đang gọi phiên bản không tham số trên queue rỗng | Dùng `poll()` nếu rỗng là trạng thái bình thường |
| `remove(task)` chậm khi queue lớn | Xóa phần tử cụ thể là `O(n)` | Giảm cập nhật tùy ý; cân nhắc tổ chức lại dữ liệu |
| Sửa `task.priority` nhưng queue không đổi thứ tự | Heap không tự reheapify khi key trong object thay đổi | Dùng object bất biến, remove rồi offer lại |
| `new PriorityQueue<>(100)` vẫn vượt 100 phần tử | Tham số là initial capacity, không phải maximum | Cài đặt backpressure/giới hạn bên ngoài |
| Race condition khi nhiều thread truy cập | `PriorityQueue` không đồng bộ hóa | Đồng bộ hoặc dùng `PriorityBlockingQueue` |
| Task mức ưu tiên thấp bị chờ vô hạn | Chính sách ưu tiên gây starvation | Thiết kế aging/quota/fairness ở tầng scheduling |
| Lấy task chưa đến hạn | PriorityQueue chỉ xếp thứ tự, không tự chờ đồng hồ | Kiểm tra `dueAt` hoặc dùng `DelayQueue`/`ScheduledExecutorService` |

## 11. Checklist trước khi đưa PriorityQueue vào ứng dụng Java 27

1. **Xác định ý nghĩa ưu tiên**: số nhỏ nhất lên trước hay số lớn nhất lên trước; quy tắc đó cần được phản ánh trực tiếp trong comparator.
2. **Giữ comparator nhất quán**: tránh overflow, side effect và khóa so sánh có thể thay đổi sau khi thêm.
3. **Xử lý tie rõ ràng**: nếu cần FIFO trong cùng một mức ưu tiên, dùng khóa phụ như `sequence`.
4. **Nhớ tính chất min-heap**: chỉ head luôn nhỏ nhất; không giả định iterator, stream hay mảng snapshot đã được sắp xếp.
5. **Hiểu chính xác thao tác**: `peek` xem, `poll` lấy và xóa, `remove(Object)` xóa theo `equals` và quét tuyến tính.
6. **Kiểm tra queue rỗng**: `poll/peek` trả `null`, trong khi `remove()/element()` ném exception khi rỗng.
7. **Ước lượng quy mô**: `O(log n)` cho thêm/xóa đầu, `O(n)` cho tìm/xóa tùy ý, dữ liệu unbounded theo hợp đồng.
8. **Xem xét concurrency**: không dùng một `PriorityQueue` bị sửa đồng thời bởi nhiều thread mà không bảo vệ.
9. **Xem xét fairness**: ưu tiên cao không đồng nghĩa các công việc thấp hơn sẽ được xử lý trong thời gian hữu hạn.
10. **Phân biệt chọn dữ liệu với lập lịch**: nếu cần chờ đến giờ chạy hoặc điều phối thread, dùng API scheduling/concurrent thích hợp.
11. **Kiểm tra hành vi bằng test**: kiểm thử phần tử trùng, queue rỗng, comparator đảo, cập nhật ưu tiên, kích thước lớn, và chính sách tie-break.

## Tài liệu tham khảo chính thức (Java SE 27)

- [`PriorityQueue<E>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/PriorityQueue.html) — heap, natural ordering/comparator, ties, iterator, thread-safety và độ phức tạp.
- [`Queue<E>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Queue.html) — các cặp `add/offer`, `remove/poll`, `element/peek`.
- [`Comparator<T>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Comparator.html) — `comparingInt`, `thenComparingLong`, `reverseOrder` và hợp đồng so sánh.
- [`PriorityBlockingQueue<E>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html) — priority queue thread-safe, `take()`, không giới hạn dung lượng và thứ tự tie.
- [`DelayQueue<E>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/DelayQueue.html) — queue có điều kiện delay cho phần tử `Delayed`.
- [`ScheduledThreadPoolExecutor` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html) — executor chạy tác vụ sau delay hoặc định kỳ.

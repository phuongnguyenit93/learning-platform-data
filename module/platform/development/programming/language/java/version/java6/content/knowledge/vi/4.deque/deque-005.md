# Dùng Deque cho FIFO và LIFO

## 1. Một cấu trúc, hai quy tắc lấy phần tử

`Deque<E>` là giao diện của một hàng đợi hai đầu: có thể thêm, lấy ra và xem phần tử ở cả đầu lẫn cuối. Từ `Deque` viết tắt của “double-ended queue”.

Hai quy tắc thường gặp:

- **FIFO — vào trước, ra trước:** công việc được đưa vào trước được lấy ra trước. Ví dụ: xử lý lần lượt các yêu cầu đã nhận.
- **LIFO — vào sau, ra trước:** phần tử mới thêm được lấy ra trước. Ví dụ: hoàn tác thay đổi gần nhất hoặc lưu các công việc đang chờ khi duyệt theo chiều sâu.

`Deque` không có nút chuyển chế độ FIFO/LIFO. **Cặp thao tác mà chương trình sử dụng tạo ra quy tắc đó.**

Trong bài này, ta thống nhất:

```text
đầu / first / head                      cuối / last / tail
        ↓                                          ↓
       [A,                 B,                 C]
```

Với dữ liệu được đưa vào lần lượt A, B, C:

| Cách dùng | Thêm ở đâu? | Lấy ở đâu? | Thứ tự lấy ra |
|---|---|---|---|
| FIFO theo quy ước Queue | Cuối | Đầu | A → B → C |
| LIFO theo các hàm stack của Deque | Đầu | Đầu | C → B → A |

Bài học dùng `ArrayDeque`, phù hợp cho ví dụ xử lý trong một luồng trên Java 17+. Không cần JDK 6 để áp dụng kiến thức này.

## 2. Khai báo theo vai trò cần dùng

Các đoạn mã ngắn trong phần giải thích là trích đoạn minh họa; chương trình đầy đủ có import và hàm main nằm ở phần 6.

```java
Deque<String> jobs = new ArrayDeque<>();
```

`Deque` mô tả các thao tác được phép dùng; `ArrayDeque` là lớp triển khai cụ thể. `<String>` cho biết phần tử là chuỗi. Trong mã thực tế, phần tử có thể là một đối tượng công việc hoặc bản ghi trạng thái.

`ArrayDeque` dùng mảng có thể mở rộng, không cho phép phần tử `null`, không an toàn khi nhiều luồng cùng truy cập mà thiếu đồng bộ phù hợp. Các thao tác ở hai đầu có chi phí O(1) theo trung bình khấu hao: một lần mở rộng mảng có thể tốn hơn, nhưng chi phí trải trên chuỗi thao tác vẫn là hằng số trung bình. Tìm hoặc xóa theo giá trị có thể phải duyệt O(n). [Tài liệu ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html).

Để giữ mã dễ đọc, nên đặt tên theo mục đích như `pendingJobs`, `undoHistory` hoặc `frontier`; tên `deque` chỉ nói cấu trúc lưu trữ.

Nếu một thành phần chỉ nên làm việc với vai trò hàng đợi, có thể thu hẹp kiểu biến hoặc tham số thành `Queue<E>`:

```java
Queue<String> pendingJobs = new ArrayDeque<>();
pendingJobs.offer("job-1");
String nextJob = pendingJobs.poll();
```

Lúc này, nơi sử dụng biến không gọi được `push` hoặc `addFirst` qua kiểu `Queue`. Đây là cách giảm khả năng vô tình phá quy ước thêm cuối/lấy đầu.

Cần biết rằng giao diện `Queue` nói chung không cam kết mọi lớp triển khai đều FIFO: hàng đợi ưu tiên có chính sách khác. Với `ArrayDeque` được dùng qua các thao tác Queue, ta có quy tắc FIFO. [Hợp đồng Queue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Queue.html).

## 3. FIFO: thêm cuối, lấy đầu

Giả sử A, B, C là ba công việc đến theo thứ tự đó:

```text
offerLast(A)       [A]
offerLast(B)       [A, B]
offerLast(C)       [A, B, C]

pollFirst() → A    [B, C]
pollFirst() → B    [C]
pollFirst() → C    []
```

Phần tử đến trước nằm gần đầu hơn. Sau mỗi lần lấy ra, công việc kế tiếp trở thành đầu mới.

Các tên gọi thông dụng tương đương trên Deque:

| Theo vai trò Queue | Viết rõ hai đầu |
|---|---|
| add(e) | addLast(e) |
| offer(e) | offerLast(e) |
| remove() | removeFirst() |
| poll() | pollFirst() |
| element() | getFirst() |
| peek() | peekFirst() |

Các phép tương đương này được quy định trong [giao diện Deque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html).

`peekFirst()` chỉ xem công việc kế tiếp. Nó không giảm kích thước và không chuyển sang công việc khác. Muốn lấy và loại bỏ phần tử khỏi hàng đợi, dùng `pollFirst()` hoặc `removeFirst()`.

Với hàng đợi công việc trong một luồng, mẫu xử lý đơn giản là:

```java
String job;
while ((job = jobs.pollFirst()) != null) {
    System.out.println("process " + job);
}
```

Đây là **đoạn mã minh họa**, giả sử `jobs` là `Deque<String>` đã khởi tạo, không chứa null và không có luồng khác sửa đồng thời. Nó tiêu thụ toàn bộ phần tử hiện có. Trong một hệ thống có nhà sản xuất chạy nền, thấy rỗng tại một thời điểm chưa có nghĩa toàn bộ hệ thống đã hoàn tất.

## 4. LIFO: thêm đầu, lấy đầu

Với ngăn xếp, đầu Deque đóng vai trò đỉnh:

```text
push(A)           [A]
push(B)           [B, A]
push(C)           [C, B, A]

pop() → C         [B, A]
pop() → B         [A]
pop() → A         []
```

Ba tên thường dùng:

| Tên theo vai trò ngăn xếp | Tương đương ở đầu Deque |
|---|---|
| push(e) | addFirst(e) |
| pop() | removeFirst() |
| peek() | peekFirst() |

Nếu rỗng là tình huống bình thường, có thể lấy đỉnh bằng `pollFirst()`, nhận `null` khi không còn phần tử. `pop()` phù hợp khi logic yêu cầu chắc chắn phải có đỉnh; gọi trên cấu trúc rỗng sẽ ném `NoSuchElementException`. [Các thao tác ngăn xếp của Deque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html).

Ví dụ hoàn tác:

```text
tài liệu hiện tại: draft-1
lưu draft-1 rồi sửa thành draft-2
lưu draft-2 rồi sửa thành draft-3

lịch sử ở đỉnh trước: [draft-2, draft-1]
undo lấy đỉnh: draft-2
lịch sử còn lại: [draft-1]
```

Điều cần lưu là trạng thái **trước khi thay đổi**. Nếu chỉ đẩy trạng thái sau sửa vào ngăn xếp rồi lấy lại ngay, thao tác “undo” có thể trả về chính trạng thái đang hiển thị.

Khi lưu đối tượng có thể thay đổi, cần xác định lịch sử giữ bản chụp hay giữ tham chiếu tới đối tượng dùng chung. Đẩy cùng một đối tượng rồi tiếp tục sửa nó không tự tạo ra nhiều bản trạng thái độc lập. Ví dụ bên dưới dùng `String` bất biến để tránh vấn đề đó.

## 5. Chọn cách xử lý rỗng và thêm thất bại

Các cặp thao tác giúp bộc lộ ý định:

| Thao tác | Trường hợp không thực hiện được | Cách báo |
|---|---|---|
| removeFirst(), removeLast(), pop() | Rỗng | NoSuchElementException |
| getFirst(), getLast() | Rỗng | NoSuchElementException |
| pollFirst(), pollLast() | Rỗng | null |
| peekFirst(), peekLast() | Rỗng | null |
| addFirst(e), addLast(e), push(e) | Bị giới hạn dung lượng và không còn chỗ | IllegalStateException |
| offerFirst(e), offerLast(e) | Bị giới hạn dung lượng và không còn chỗ | false |

`offer` trả `false` khi không thể thêm vì giới hạn dung lượng; nó không cam kết nuốt mọi lỗi. Chẳng hạn, đưa `null` vào `ArrayDeque` vẫn gây `NullPointerException`. [Queue.offer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Queue.html#offer(E)), [ArrayDeque.offerLast](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html#offerLast(E)).

`new ArrayDeque<>(2)` chỉ yêu cầu dung lượng khởi tạo đủ chứa ít nhất hai phần tử. Nó không đặt giới hạn “tối đa hai phần tử”; mảng có thể tăng khi cần. Vì vậy, đừng dùng tham số này để áp dụng giới hạn số công việc đang chờ. [ArrayDeque(int)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html#%3Cinit%3E(int)).

Với `ArrayDeque`, cấm null còn giúp `poll`/`peek` có tín hiệu rỗng rõ ràng. Nếu chọn một lớp triển khai cho phép null rồi dùng vòng lặp dừng ở null, chương trình có thể dừng trước khi xử lý hết dữ liệu. Quy tắc “không dùng null làm phần tử” nên là một phần hợp đồng sử dụng.

## 6. Chương trình Java 17+ chạy đầy đủ

Lưu thành `DequeOrderLab.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Queue;

public final class DequeOrderLab {
    private DequeOrderLab() {
    }

    private static List<String> drainFifo(Deque<String> deque) {
        List<String> result = new ArrayList<>();
        String item;
        while ((item = deque.pollFirst()) != null) {
            result.add(item);
        }
        return result;
    }

    private static List<String> drainLifo(Deque<String> deque) {
        List<String> result = new ArrayList<>();
        while (!deque.isEmpty()) {
            result.add(deque.pop());
        }
        return result;
    }

    public static void main(String[] args) {
        Deque<String> fifo = new ArrayDeque<>();
        fifo.offerLast("A");
        fifo.offerLast("B");
        fifo.offerLast("C");
        System.out.println("fifo before=" + fifo);
        System.out.println("fifo peek=" + fifo.peekFirst());
        System.out.println("fifo size=" + fifo.size());
        System.out.println("fifo order=" + drainFifo(fifo));
        System.out.println("fifo empty poll=" + fifo.pollFirst());

        Deque<String> lifo = new ArrayDeque<>();
        lifo.push("A");
        lifo.push("B");
        lifo.push("C");
        System.out.println("lifo before=" + lifo);
        System.out.println("lifo peek=" + lifo.peek());
        System.out.println("lifo order=" + drainLifo(lifo));
        try {
            lifo.pop();
        } catch (NoSuchElementException ex) {
            System.out.println("empty pop=" + ex.getClass().getSimpleName());
        }

        Queue<String> queueView = new ArrayDeque<>();
        queueView.offer("first");
        queueView.offer("second");
        System.out.println("queue view=" + queueView.poll());

        Deque<String> history = new ArrayDeque<>();
        String document = "draft-1";
        history.push(document);
        document = "draft-2";
        history.push(document);
        document = "draft-3";
        document = history.pop();
        System.out.println("undo=" + document);
        System.out.println("older history=" + history);

        Deque<Integer> growing = new ArrayDeque<>(2);
        for (int i = 1; i <= 4; i++) {
            growing.addLast(i);
        }
        System.out.println("growing size=" + growing.size());
        try {
            fifo.offerLast(null);
        } catch (NullPointerException ex) {
            System.out.println("null=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -Xlint:all -Werror DequeOrderLab.java
java DequeOrderLab
```

Stdout:

```text
fifo before=[A, B, C]
fifo peek=A
fifo size=3
fifo order=[A, B, C]
fifo empty poll=null
lifo before=[C, B, A]
lifo peek=C
lifo order=[C, B, A]
empty pop=NoSuchElementException
queue view=first
undo=draft-2
older history=[draft-1]
growing size=4
null=NullPointerException
```

### Giải thích theo từng nhóm kết quả

**FIFO:** ba lần `offerLast` tạo thứ tự đầu → cuối là A, B, C. Sau `peekFirst`, kích thước vẫn là 3. Hàm `drainFifo` lần lượt lấy đầu cho đến khi rỗng, nên danh sách kết quả giữ thứ tự đưa vào.

**LIFO:** `push` thêm vào đầu; sau ba lần gọi, đầu → cuối là C, B, A. Hàm `drainLifo` lấy C trước. Lệnh `pop` sau khi đã lấy hết phát sinh ngoại lệ; khối `catch` chỉ dùng để minh họa hợp đồng rỗng.

**Giao diện Queue:** biến `queueView` chỉ thể hiện các thao tác của hàng đợi. Đối tượng vẫn là `ArrayDeque`; `offer`/`poll` thêm cuối/lấy đầu, nên phần tử được lấy ra là `first`.

**Hoàn tác:** chương trình lưu hai trạng thái cũ, sau đó lấy trạng thái mới nhất trong lịch sử để khôi phục. Bài này minh họa một bước undo; chức năng redo cần thiết kế lịch sử riêng và quy tắc khi có chỉnh sửa mới.

**Dung lượng và null:** `growing` chứa được 4 phần tử dù khởi tạo với 2; `fifo.offerLast(null)` vẫn ném ngoại lệ. Đây là hai đặc tính độc lập.

Hai hàm `drainFifo` và `drainLifo` **làm rỗng cấu trúc đầu vào**. Việc trả lại một `List` không có nghĩa Deque gốc còn giữ dữ liệu; khi thiết kế API, tác dụng này cần được thể hiện rõ.

## 7. Duyệt và lấy ra là hai việc khác nhau

`for-each` thông thường của Deque duyệt từ đầu tới cuối; nó không tự lấy phần tử ra. [Deque.iterator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html#iterator()).

Trong ví dụ:

- FIFO đang có `[A, B, C]`; duyệt đầu → cuối thấy A, B, C.
- LIFO sau ba lần push đang có `[C, B, A]`; duyệt đầu → cuối thấy C, B, A.
- Việc duyệt không thay cho `poll`/`pop` nếu mục tiêu là tiêu thụ công việc.

Không nên vừa dùng `for-each` vừa gọi `pop` trên cùng `ArrayDeque` để lấy dần phần tử. Đó là sửa cấu trúc trong khi đang dùng một bộ duyệt khác; bộ duyệt có thể báo `ConcurrentModificationException`. Cơ chế phát hiện này không phải bảo đảm đồng bộ giữa các luồng. Với mục tiêu lấy hết dữ liệu, dùng vòng lặp `poll`/`pop` như chương trình đầy đủ. [Quy tắc bộ duyệt ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html).

Một lời gọi như `remove("B")` cũng khác `removeFirst()`: nó tìm phần tử theo giá trị. Thêm/xóa ở giữa theo giá trị có thể phá quy tắc FIFO/LIFO mà phần còn lại của chương trình đang dựa vào.

## 8. Giữ quy ước nhất quán trong mã thực tế

Có thể chọn thêm cuối/lấy cuối để làm LIFO, nhưng `push`/`pop` của Deque đã quy ước dùng đầu. Khi một cấu trúc có nhiều nơi truy cập, nên chọn một quy ước và ghi rõ trong hợp đồng.

Ví dụ các thao tác dễ trộn nhầm:

```java
Deque<String> work = new ArrayDeque<>();
work.push("A");
work.push("B");
String next = work.pollLast();
```

Đây là đoạn mã minh họa thứ tự. Sau hai lần push, cấu trúc là `[B, A]`; `pollLast()` lấy A. Người đọc nhìn thấy `push` có thể nghĩ “ngăn xếp”, nhưng cách lấy ra ở cuối đã tạo quy tắc khác.

Tương tự, thêm cuối/lấy cuối lấy phần tử mới nhất, nên không đáp ứng yêu cầu “xử lý theo thứ tự đến” của FIFO. Để kiểm tra, hãy viết một chuỗi ba phần tử A, B, C và dự đoán thứ tự lấy ra trước khi chạy.

Một số quan hệ ứng dụng:

- Hàng đợi công việc tuần tự: ưu tiên tính dễ hiểu của `offerLast`/`pollFirst` hoặc giao diện `Queue`.
- Hoàn tác: dùng `push`/`pop`, kiểm soát trạng thái lưu và tác động của dữ liệu có thể thay đổi.
- Duyệt đồ thị: FIFO thường gắn với duyệt theo chiều rộng, LIFO gắn với duyệt theo chiều sâu. Còn cần quản lý các nút đã thăm và thứ tự thêm nút kề; đổi cấu trúc không tự hoàn thành thuật toán.

## 9. Ranh giới khi có nhiều luồng

Chương trình mẫu chạy trong một luồng. Mẫu `if (!deque.isEmpty()) deque.pop()` hoặc vòng lặp kiểm tra rỗng rồi lấy chỉ an toàn theo giả định đó. Nếu cấu trúc được chia sẻ và một luồng khác lấy mất phần tử giữa hai bước, kết quả kiểm tra có thể đã lỗi thời.

Khi yêu cầu là “chờ đến khi có công việc” hoặc “chờ đến khi còn chỗ”, hãy xem hợp đồng `BlockingDeque`, với `takeFirst`, `putLast` và các biến thể có thời gian chờ. Giao diện này có các triển khai an toàn cho nhiều luồng; không nên mô phỏng chờ bằng vòng lặp liên tục gọi `poll`. [Tài liệu BlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html).

Đây là ranh giới lựa chọn công cụ. Thiết kế kết thúc nhà sản xuất/tiêu thụ, hủy công việc và giới hạn tải cần hợp đồng riêng; thấy hàng đợi tạm rỗng chưa phải tín hiệu dừng đầy đủ.

## 10. Tự kiểm chứng

1. Thay `fifo.offerLast` bằng `fifo.offerFirst`, giữ nguyên cách lấy. Dự đoán thứ tự mới rồi chạy để kiểm chứng.
2. Giữ cách thêm FIFO, thay `pollFirst` bằng `pollLast`. Chỉ ra đầu nào đang là “đỉnh” của cấu trúc mới.
3. Gọi `peek` hai lần trước khi lấy. Kiểm tra phần tử trả về và kích thước để phân biệt xem với lấy.
4. Thêm kiểm tra rằng cả hai Deque rỗng sau khi gọi các hàm `drain`; giải thích tác dụng làm thay đổi đầu vào.
5. Với yêu cầu hàng đợi tối đa 100 công việc, giải thích vì sao `new ArrayDeque<>(100)` chưa thực hiện yêu cầu đó.
6. Với lịch sử hoàn tác của một đối tượng có thể thay đổi, xác định phải lưu tham chiếu hay bản chụp để khôi phục đúng trạng thái trước đó.

Khi đánh giá một đoạn mã dùng Deque, hãy xác định được ba điều cụ thể: **thêm ở đầu nào, lấy ở đầu nào, và xử lý thế nào khi rỗng**. Ba quyết định đó làm rõ hành vi FIFO/LIFO hơn tên biến hay tên lớp đơn lẻ.

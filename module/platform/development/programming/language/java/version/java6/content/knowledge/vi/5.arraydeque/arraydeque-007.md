# Chọn ArrayDeque cho ngăn xếp và hàng đợi trong một luồng

## 1. Bắt đầu từ thứ tự xử lý

Giả sử chương trình đang giữ ba công việc A, B, C theo thứ tự được tạo:

- Nếu A phải được xử lý trước B rồi C, ta cần **hàng đợi FIFO**: phần tử vào trước được lấy ra trước.
- Nếu thao tác C phải được hoàn tác trước B rồi A, ta cần **ngăn xếp LIFO**: phần tử vào sau được lấy ra trước.

Cả hai đều có thể dùng `ArrayDeque`. Điểm quyết định là **quy ước đầu thêm và đầu lấy**, không phải đổi sang một lớp khác cho mỗi thuật toán.

`Deque` là hàng đợi hai đầu: có đầu trước và đầu sau. `ArrayDeque` là một cách cài đặt `Deque` bằng mảng có thể mở rộng. Khi chỉ một luồng sở hữu và sử dụng cấu trúc, đây là lựa chọn thực tế cho danh sách công việc chờ hoặc lịch sử thao tác. Bài học dùng API hiện còn áp dụng trong Java hiện đại; toàn bộ chương trình minh họa biên dịch được với Java 17 trở lên. Xem hợp đồng hiện hành của [ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html).

Học theo thứ tự: chọn FIFO hay LIFO → chọn kiểu biến → ghép đúng phương thức thêm/lấy → xác định cách xử lý khi rỗng → kiểm tra ai có quyền truy cập cấu trúc.

## 2. Chọn kiểu biến để bộc lộ ý định

Đây là các khai báo minh họa, cần đặt trong phương thức và có các lệnh import tương ứng:

```java
Deque<String> undoHistory = new ArrayDeque<>();
Queue<String> pendingJobs = new ArrayDeque<>();
```

- Biến `undoHistory` có kiểu `Deque` để dùng các thao tác ngăn xếp như `push`, `pop`, `peek`.
- Biến `pendingJobs` có kiểu `Queue` để nơi sử dụng chỉ thấy giao diện hàng đợi như `offer`, `poll`, `peek`. Cách khai báo này giúp tránh vô tình thêm công việc vào đầu trước bằng `push`.
- Cả hai đối tượng thực tế đều là `ArrayDeque`. Kiểu giao diện diễn đạt cách dùng; lớp cài đặt cung cấp nơi lưu phần tử.

Cần lưu ý: `Queue` nói chung không luôn có thứ tự FIFO; chẳng hạn hàng đợi ưu tiên có quy tắc khác. Trong bài này, FIFO xuất phát từ hợp đồng của `ArrayDeque` khi dùng các phương thức hàng đợi. Xem [Queue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Queue.html).

Đặt tên theo vai trò như `undoHistory`, `pendingJobs`, `nodesToVisit` giúp người đọc kiểm tra thứ tự xử lý ngay tại nơi sử dụng.

## 3. Hai quy ước thao tác cần nhớ

Quy ước hiển thị dưới đây luôn viết **đầu trước ở bên trái, đầu sau ở bên phải**.

| Mục đích | Thêm phần tử | Lấy và xóa phần tử | Xem mà không xóa |
| --- | --- | --- | --- |
| Ngăn xếp LIFO | `push(e)`, tương đương `addFirst(e)` | `pop()`, tương đương `removeFirst()` | `peek()`, tương đương `peekFirst()` |
| Hàng đợi FIFO | `offer(e)`, tương đương `offerLast(e)` | `poll()`, tương đương `pollFirst()` | `peek()`, tương đương `peekFirst()` |

Ví dụ tự lần theo:

```text
Ngăn xếp:
push(A) -> [A]
push(B) -> [B, A]
push(C) -> [C, B, A]
pop()   -> C, còn [B, A]

Hàng đợi:
offer(A) -> [A]
offer(B) -> [A, B]
offer(C) -> [A, B, C]
poll()   -> A, còn [B, C]
```

Vì `push` và `pop` cùng thao tác ở đầu trước nên phần tử vừa thêm đứng ngay tại nơi sẽ lấy tiếp theo. Với FIFO, thêm ở đầu sau và lấy ở đầu trước giữ cho công việc cũ đứng trước công việc mới.

Có thể tự dùng `addLast` và `removeLast` để tạo LIFO ở đầu sau, nhưng nên giữ một quy ước nhất quán trong cùng thuật toán. Đừng thêm bằng `push` rồi lấy bằng `pollLast` và vẫn gọi đó là ngăn xếp: cặp ấy lấy phần tử cũ nhất. Các quan hệ phương thức ở trên được quy định trong [Deque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html).

## 4. Quyết định cách xử lý khi rỗng

Đọc/lấy phần tử có hai nhóm phương thức:

| Ý định | Trả về `null` khi rỗng | Ném `NoSuchElementException` khi rỗng |
| --- | --- | --- |
| Xem đầu trước | `peek()`, `peekFirst()` | `element()`, `getFirst()` |
| Lấy và xóa đầu trước | `poll()`, `pollFirst()` | `remove()`, `removeFirst()`, `pop()` |

Đây là quy ước của [Deque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html).

Chọn theo ý nghĩa nghiệp vụ:

- Hàng đợi đã xử lý hết là tình huống bình thường: dùng `poll()` và dừng khi nhận `null`.
- Thuật toán khẳng định ngăn xếp phải có phần tử: `pop()` làm lỗi vi phạm giả định lộ ra ngay.
- Thao tác hoàn tác khi lịch sử rỗng là bình thường: dùng `pollFirst()` rồi xử lý `null`, thay vì bắt ngoại lệ để điều khiển luồng chương trình.

Trong `ArrayDeque`, không được thêm `null`; việc đó ném `NullPointerException`. Vì vậy `poll()` trả `null` có thể dùng để nhận diện rỗng. Cẩn thận với tự mở hộp:

```java
// Minh họa lỗi khi numbers đang rỗng:
int next = numbers.poll(); // null bị chuyển sang int -> NullPointerException

// Cách kiểm tra kết quả:
Integer value = numbers.poll();
if (value != null) {
    int next = value;
    // Dùng next ở đây.
}
```

Đoạn trên là minh họa, không phải chương trình độc lập; `numbers` cần là một `Queue<Integer>` hoặc `Deque<Integer>` đã được khởi tạo.

## 5. Chương trình chạy được: cùng dữ liệu, hai thứ tự

Lưu đúng tên tệp `DequeChoiceDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.NoSuchElementException;
import java.util.Queue;

public class DequeChoiceDemo {
    public static void main(String[] args) {
        Deque<String> undoHistory = new ArrayDeque<>();
        undoHistory.push("A");
        undoHistory.push("B");
        undoHistory.push("C");

        System.out.println("stack=" + undoHistory);
        System.out.println("stack.peek=" + undoHistory.peek());
        System.out.println("stack.size=" + undoHistory.size());

        while (!undoHistory.isEmpty()) {
            System.out.println("undo=" + undoHistory.pop());
        }

        Queue<String> pendingJobs = new ArrayDeque<>();
        pendingJobs.offer("A");
        pendingJobs.offer("B");
        pendingJobs.offer("C");

        System.out.println("queue=" + pendingJobs);
        System.out.println("queue.peek=" + pendingJobs.peek());
        System.out.println("queue.size=" + pendingJobs.size());

        String job;
        while ((job = pendingJobs.poll()) != null) {
            System.out.println("run=" + job);
        }

        System.out.println("empty.peek=" + pendingJobs.peek());
        System.out.println("empty.poll=" + pendingJobs.poll());

        try {
            undoHistory.pop();
        } catch (NoSuchElementException ex) {
            System.out.println("empty.pop=NoSuchElementException");
        }

        try {
            pendingJobs.offer(null);
        } catch (NullPointerException ex) {
            System.out.println("offer.null=NullPointerException");
        }

        Queue<Integer> growing = new ArrayDeque<>(2);
        for (int i = 1; i <= 4; i++) {
            growing.offer(i);
        }
        System.out.println("initial.two.size=" + growing.size());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp, với JDK 17 trở lên:

```shell
javac --release 17 DequeChoiceDemo.java
java DequeChoiceDemo
```

Stdout chính xác:

```text
stack=[C, B, A]
stack.peek=C
stack.size=3
undo=C
undo=B
undo=A
queue=[A, B, C]
queue.peek=A
queue.size=3
run=A
run=B
run=C
empty.peek=null
empty.poll=null
empty.pop=NoSuchElementException
offer.null=NullPointerException
initial.two.size=4
```

Các điểm cần tự đối chiếu:

1. Sau `peek`, kích thước vẫn bằng 3: xem phần tử không làm thay đổi cấu trúc.
2. C được hoàn tác trước A, nhưng A được chạy trước C.
3. Sau vòng lặp xử lý công việc, `peek` và `poll` đều trả `null`.
4. Hai khối `catch` cuối phần xử lý rỗng/null chỉ để quan sát hợp đồng API, không phải mẫu xử lý nghiệp vụ bắt buộc.
5. Tham số `2` của constructor là sức chứa ban đầu tối thiểu, không phải giới hạn hai phần tử. Bốn phần tử vẫn được thêm; không thể dùng tham số này để chặn tồn đọng công việc.

## 6. Vì sao ArrayDeque thường phù hợp?

Khi thuật toán chủ yếu thêm/lấy ở hai đầu, mảng có thể mở rộng đáp ứng mô hình này mà không cần mỗi phần tử có một nút liên kết riêng. Phần lớn thao tác của `ArrayDeque` có thời gian hằng số khấu hao: một lần mở rộng có thể đắt hơn, nhưng chi phí được phân bổ qua nhiều lần thêm. Tìm một phần tử theo giá trị như `contains` hoặc `remove(Object)` cần duyệt và có chi phí tuyến tính. Vì vậy đừng biến hàng đợi thành nơi tìm/xóa tùy ý liên tục rồi kỳ vọng mọi thao tác đều nhanh như `poll`. Xem [đặc tính ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html).

Khi chọn cấu trúc, hỏi thuật toán cần làm gì thường xuyên:

| Nhu cầu thực tế | Hướng chọn |
| --- | --- |
| Giữ các bước cần hoàn tác theo thứ tự ngược, một luồng | `Deque<E>` với `ArrayDeque<E>`, dùng `push/pop` |
| Giữ công việc chờ theo thứ tự đến, một luồng | `Queue<E>` với `ArrayDeque<E>`, dùng `offer/poll` |
| Truy cập trực tiếp phần tử theo vị trí thứ i | Xem xét `List`; giao diện `Deque` không có `get(i)` |
| Lấy công việc theo độ ưu tiên | Xem xét hàng đợi ưu tiên; đổi yêu cầu thứ tự trước khi đổi lớp |
| Đặt trần công việc đang chờ và chờ khi đầy/rỗng | Xem xét `BlockingQueue` có sức chứa giới hạn |

Bảng là hướng suy luận từ cách truy cập, không phải cam kết một lớp luôn nhanh nhất. Với dữ liệu lớn hoặc yêu cầu độ trễ cụ thể, đo đúng khối lượng công việc của ứng dụng. Không dựa vào tỷ lệ tăng mảng, vị trí chỉ số nội bộ hay một con số sức chứa cố định của một phiên bản JDK để viết thuật toán.

`offer` trên `ArrayDeque` không có nghĩa là cấu trúc sẽ từ chối thêm khi đạt sức chứa ban đầu. Cấu trúc tự mở rộng; bộ nhớ vẫn hữu hạn. Nếu tốc độ tạo công việc vượt tốc độ xử lý trong thời gian dài, cần giới hạn hoặc chính sách điều tiết của ứng dụng.

## 7. “Trong một luồng” là điều kiện sở hữu dữ liệu

Chương trình có thể có nhiều luồng nhưng mỗi tác vụ vẫn tạo và dùng `ArrayDeque` riêng. Điều cần xác nhận là **không có truy cập đồng thời không được đồng bộ tới cùng đối tượng**.

Ví dụ cách tổ chức dễ kiểm soát là tạo deque bên trong phương thức và không truyền nó ra cho tác vụ nền. Ngược lại, đặt deque trong trường `static` hoặc trường của một đối tượng được nhiều yêu cầu cùng sử dụng có thể làm nhiều luồng chạm vào cùng dữ liệu. Từ khóa `final` trên biến chỉ ngăn gán lại tham chiếu, không tự bảo vệ các thao tác trên deque.

Khi thật sự cần chia sẻ:

- `ConcurrentLinkedDeque` hỗ trợ truy cập đồng thời ở hai đầu; phù hợp khi cần deque dùng chung mà không cần đợi phần tử xuất hiện. Các chuỗi nhiều thao tác vẫn không tự trở thành một giao dịch nguyên tử. Xem [ConcurrentLinkedDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html).
- `BlockingQueue` hỗ trợ các thao tác chờ dữ liệu hoặc chờ chỗ trống; chọn cách cài đặt có giới hạn nếu yêu cầu là giới hạn số công việc chờ. Đây là hướng dành cho mô hình bên tạo/bên xử lý công việc giữa các luồng. Xem [BlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Không dùng việc “chạy thử chưa thấy lỗi” làm bằng chứng rằng một deque dùng chung đã an toàn. Cần xác định rõ quyền truy cập và cơ chế phối hợp.

## 8. Những lỗi chọn đúng lớp nhưng dùng sai

### Trộn FIFO và LIFO

Trong một hàng đợi công việc, thay `offer` bằng `push` khiến công việc mới chen lên đầu. Có thể chương trình vẫn chạy, nhưng thứ tự nghiệp vụ đã thay đổi. Giữ biến kiểu `Queue` và dùng duy nhất `offer/poll` giúp ý định rõ hơn.

### Duyệt để xóa nhưng làm mất phần tử kế tiếp

Muốn xử lý hết hàng đợi thì dùng một lần `poll` cho mỗi lượt:

```java
// Minh họa, pendingJobs đã được khởi tạo:
String job;
while ((job = pendingJobs.poll()) != null) {
    process(job);
}
```

`process` ở đây đại diện cho hàm xử lý của ứng dụng. Không gọi thêm `poll()` ở điều kiện và lại `poll()` trong thân vòng lặp: khi đó mỗi lượt có thể lấy mất hai phần tử nhưng chỉ xử lý một.

### Nghĩ peek đã hoàn tất việc lấy

Nếu cứ đọc bằng `peek()` rồi lặp mà không xóa, phần tử đầu vẫn giữ nguyên. Chương trình có thể xử lý mãi một công việc. Chọn `poll()` khi cần lấy khỏi hàng chờ.

### Dùng trạng thái rỗng để suy luận sai trong chương trình nhiều luồng

Trong ví dụ một luồng, `!isEmpty()` rồi `pop()` là dễ hiểu vì không có luồng khác lấy mất phần tử ở giữa. Khi thay đổi sang dữ liệu dùng chung, không mang nguyên giả định ấy sang thiết kế mới: ngay cả khi từng thao tác riêng lẻ an toàn, việc kiểm tra rồi lấy vẫn là hai thao tác khác nhau.

## 9. Tự thực hành

1. Trong ví dụ, đổi phần hàng đợi thành `Deque<String>` và thay ba lời gọi `offer` bằng `push`, giữ nguyên `poll`. Dự đoán kết quả trước khi chạy.
2. Viết hàm lấy thao tác hoàn tác bằng `pollFirst()`, trả thông báo riêng khi lịch sử rỗng mà không bắt ngoại lệ.
3. Với `new ArrayDeque<>(2)`, thêm 100 số rồi kiểm tra `size()`. Giải thích tại sao kết quả không phải 2.
4. Một ứng dụng tạo việc trên luồng A và xử lý trên luồng B cần chờ khi chưa có việc. Nêu vì sao `ArrayDeque` dùng chung chưa đáp ứng hợp đồng ấy và cần lựa chọn theo yêu cầu đồng thời nào.

Đáp án định hướng: câu 1 lấy C, B, A vì thêm và lấy đều ở đầu trước; câu 2 phải kiểm tra giá trị `null`; câu 3 nhận 100 vì constructor không đặt giới hạn; câu 4 cần cơ chế truy cập đồng thời và thao tác chờ, chẳng hạn một cách cài đặt `BlockingQueue` phù hợp.

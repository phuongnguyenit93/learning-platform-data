# ConcurrentLinkedQueue và hàng đợi không chặn

Một luồng tạo công việc, luồng khác thử nhận công việc để xử lý. Nếu bên nhận không muốn ngủ chờ dữ liệu ngay trong thao tác hàng đợi, nó cần một API trả kết quả ngay: có phần tử thì lấy, chưa có thì tiếp tục công việc khác.

`ConcurrentLinkedQueue<E>` là hàng đợi liên kết an toàn khi nhiều luồng truy cập, theo thứ tự vào trước ra trước (FIFO), không đặt giới hạn dung lượng logic và sử dụng thuật toán không chặn (non-blocking). Nó thuộc giao diện `Queue`, không phải `BlockingQueue`. API này vẫn áp dụng trong Java hiện đại; ví dụ dưới chạy với Java 17 trở lên.

## 1. Không chặn có ý nghĩa gì?

Với hàng đợi này, `poll()` không chờ đến khi một bên sản xuất gửi phần tử mới. Khi không lấy được phần tử vì hàng đợi rỗng, nó trả `null`. `offer()` không chờ chỗ trống do một mức dung lượng tối đa cố định, vì lớp không có giới hạn dung lượng đó.

Ở mức thuật toán, lớp được thiết kế bằng một thuật toán không chặn thay cho việc bắt mọi thao tác đi qua một khóa loại trừ chung. Hợp đồng lớp và nguồn thuật toán được trình bày tại [ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html).

Có thể hiểu cơ chế ở mức khái quát qua ba bước: đọc trạng thái liên kết hiện tại, thử cập nhật bằng phép so sánh và hoán đổi (compare-and-set, CAS), rồi quan sát lại nếu một luồng khác đã thắng trước. Trong triển khai OpenJDK 25, việc nối nút mới dùng cập nhật nguyên tử lên liên kết, còn việc nhận phần tử đánh dấu lấy bằng cập nhật nguyên tử trên dữ liệu nút. Các con trỏ hỗ trợ sau đó có thể được điều chỉnh để tối ưu việc duyệt. Đây là mô tả cơ chế triển khai, không phải thuật toán cần tự viết lại khi dùng lớp. [Mã nguồn ConcurrentLinkedQueue của OpenJDK 25](https://raw.githubusercontent.com/openjdk/jdk/jdk-25-ga/src/java.base/share/classes/java/util/concurrent/ConcurrentLinkedQueue.java).

Tuy nhiên, “không chặn” không có nghĩa:

- Mỗi lời gọi hoàn tất trong đúng một số nano giây đã biết.
- Mỗi luồng luôn hoàn tất sau một số bước cố định, bất kể cạnh tranh.
- Không có chi phí cấp phát, thu gom rác hoặc chuyển lịch chạy.
- Toàn bộ chương trình sẽ bất đồng bộ chỉ vì thay loại hàng đợi.

Đặc biệt, không đồng nhất thuật toán không chặn với bảo đảm chờ hữu hạn theo số bước riêng của mỗi luồng (wait-free). Khi nhiều bên cạnh tranh cập nhật, một bên có thể phải thử lại; không được suy ra cam kết thời gian thực từ tên lớp.

Việc `process(item)` thực hiện I/O chậm vẫn có thể làm bên tiêu thụ chờ I/O. Cơ chế hàng đợi không làm thay đổi hợp đồng của bước xử lý bên ngoài.

## 2. Các thao tác chính

| Phương thức | Hành vi |
|---|---|
| `offer(e)` | Thêm e vào cuối; trả `true` nếu hoàn tất bình thường |
| `poll()` | Lấy và xóa đầu hàng đợi, hoặc trả `null` nếu rỗng |
| `peek()` | Xem đầu hàng đợi, không lấy ra; trả `null` nếu rỗng |
| `add(e)` | Thêm vào cuối; trong lớp này không bị từ chối bởi giới hạn dung lượng |
| `remove()` | Lấy và xóa đầu, ném `NoSuchElementException` nếu rỗng |
| `element()` | Xem đầu, ném `NoSuchElementException` nếu rỗng |

Cặp `poll`/`remove()` và `peek`/`element` khác nhau ở cách báo hàng đợi rỗng. Đừng nhầm `remove()` không tham số với `remove(object)`, vốn tìm và loại một phần tử bằng đối tượng đã chỉ định. Tổng quan các cặp API ở [Queue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Queue.html).

`ConcurrentLinkedQueue` không nhận `null`. Nhờ vậy, `null` từ `poll()` hoặc `peek()` có ý nghĩa rõ ràng, không lẫn với một công việc hợp lệ.

“Không giới hạn” là đặc tính logic, không phải bộ nhớ vô hạn. Việc thêm vẫn có thể không hoàn tất nếu không còn tài nguyên; không dùng hàng đợi này như một cơ chế tự động từ chối đầu vào khi hệ thống quá tải.

## 3. FIFO khi có nhiều luồng

Nếu một bên gửi lần lượt A rồi B, hoàn tất lần thêm A trước khi bắt đầu lần thêm B, thứ tự hàng đợi giữ A trước B.

Nếu hai bên cùng thêm tại những thời điểm chồng lấn, ta không thể dự đoán thứ tự toàn cục chỉ từ tên luồng hoặc từ việc lời gọi nào bắt đầu trước. Hàng đợi vẫn có thứ tự FIFO theo thứ tự các thao tác thêm được phân xử, nhưng các phần tử của hai bên có thể xen kẽ theo nhiều cách hợp lệ.

Ví dụ hai bên tạo các dãy:

```text
Bên 0: 0-0, 0-1, 0-2
Bên 1: 1-0, 1-1, 1-2

Một thứ tự hợp lệ: 0-0, 1-0, 1-1, 0-1, 0-2, 1-2
```

Mỗi dãy riêng vẫn giữ thứ tự. Không cần đòi toàn bộ dãy của bên 0 luôn đứng trước dãy của bên 1.

Nhiều bên tiêu thụ có thể cùng gọi `poll()`. Một lần lấy thành công nhận một lần xuất hiện của phần tử trong hàng đợi; nhưng nếu ứng dụng chủ động thêm cùng tham chiếu hai lần, đó là hai lần xuất hiện có thể được lấy riêng. FIFO cũng không hứa công việc nhận trước sẽ hoàn thành trước khi nhiều luồng xử lý đồng thời.

## 4. Chương trình chạy đầy đủ

Lưu thành `NonBlockingQueueDemo.java`. Phần đầu minh họa API; phần sau cho hai luồng thêm đồng thời rồi mới lấy để kiểm tra số lượng và thứ tự riêng từng bên gửi.

```java
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

public class NonBlockingQueueDemo {
    record Item(int producer, int index) {}

    public static void main(String[] args) throws InterruptedException {
        Queue<String> names = new ConcurrentLinkedQueue<>();
        System.out.println("offer alpha: " + names.offer("alpha"));
        names.offer("beta");
        System.out.println("peek: " + names.peek());
        System.out.println("poll 1: " + names.poll());
        System.out.println("poll 2: " + names.poll());
        System.out.println("poll empty: " + names.poll());

        ConcurrentLinkedQueue<Item> work = new ConcurrentLinkedQueue<>();
        Thread first = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                work.offer(new Item(0, i));
            }
        }, "producer-0");
        Thread second = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                work.offer(new Item(1, i));
            }
        }, "producer-1");

        first.start();
        second.start();
        first.join();
        second.join();

        // Production is finished; no later offers can occur.
        int[] expectedIndex = new int[2];
        boolean orderedWithinProducer = true;
        int consumed = 0;
        Item item;
        while ((item = work.poll()) != null) {
            int source = item.producer();
            if (item.index() != expectedIndex[source]) {
                orderedWithinProducer = false;
            }
            expectedIndex[source]++;
            consumed++;
        }

        System.out.println("consumed: " + consumed);
        System.out.println("per-producer FIFO: " + orderedWithinProducer);
        System.out.println("queue empty: " + work.isEmpty());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 NonBlockingQueueDemo.java
java NonBlockingQueueDemo
```

Stdout trong lượt chạy bình thường:

```text
offer alpha: true
peek: alpha
poll 1: alpha
poll 2: beta
poll empty: null
consumed: 2000
per-producer FIFO: true
queue empty: true
```

Giải thích:

1. `peek()` không xóa `alpha`, nên lần `poll()` tiếp theo vẫn nhận `alpha`.
2. Không cần `synchronized` bên ngoài khi hai luồng cùng `offer` vào cùng hàng đợi.
3. `Item` giữ hai số nguyên bất biến bằng `record`, thuận tiện cho việc kiểm tra và bàn giao.
4. Sau `join()` của cả hai bên sản xuất, không còn lần gửi nào trong chương trình. Vì thế vòng lặp lấy đến `null` có thể coi việc rỗng là kết thúc giai đoạn thu thập.
5. Chương trình không in thứ tự toàn bộ 2.000 phần tử vì thứ tự xen kẽ giữa hai bên sản xuất không cố định. Nó kiểm tra điều kiện ổn định: mỗi bên vẫn giữ thứ tự chỉ số của mình.

Trong ví dụ, `join()` cũng tạo quan hệ bộ nhớ để luồng chính quan sát công việc đã hoàn tất. Hàng đợi tự có bảo đảm công bố dữ liệu cho những trường hợp sản xuất và tiêu thụ diễn ra đồng thời, như phần sau.

## 5. Quan hệ bộ nhớ khi nhận phần tử

Các hành động trước khi một luồng đưa đối tượng vào `ConcurrentLinkedQueue` happens-before những hành động sau khi một luồng khác truy cập hoặc lấy chính đối tượng đó từ hàng đợi. Vì vậy, dữ liệu được chuẩn bị trước lần gửi được công bố qua ranh giới hàng đợi. Quy tắc chung cũng được nêu tại [java.util.concurrent — Memory Consistency Properties](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility).

Nhưng hàng đợi không sao chép đối tượng và không tự bảo vệ mọi lần sửa sau đó. Nếu bên gửi tiếp tục sửa một mảng sau `offer()` trong lúc bên nhận đọc, cần một giao thức đồng bộ hóa hoặc bàn giao quyền sở hữu rõ ràng.

Cách dùng dễ kiểm soát là gửi dữ liệu bất biến hoặc ngừng sửa thông điệp sau khi gửi cho đến khi nhận lại quyền sử dụng qua một cơ chế phù hợp.

## 6. Rỗng tạm thời không có nghĩa đã kết thúc

Đoạn sau chỉ xử lý phần hiện có, không phải vòng đời đầy đủ của một bên tiêu thụ chạy lâu dài:

```java
// Minh họa trong phạm vi có Queue<Job> queue và hàm process.
Job job;
while ((job = queue.poll()) != null) {
    process(job);
}
```

Nếu bên sản xuất vẫn hoạt động, hàng đợi có thể rỗng đúng lúc `poll()` chạy rồi nhận việc mới ngay sau khi vòng lặp kết thúc. Không được suy ra “không còn công việc nào về sau”. Ví dụ chạy đầy đủ tránh điều này bằng cách chờ hai bên sản xuất xong trước khi bắt đầu vòng lấy.

Đoạn lặp liên tục sau cũng không phải cách mặc định phù hợp để chờ công việc:

```java
// Minh họa vấn đề: quay vòng liên tục khi chưa có phần tử.
while (running) {
    Job job = queue.poll();
    if (job != null) {
        process(job);
    }
}
```

`running` cần một giao thức nhìn thấy dữ liệu phù hợp, nhưng kể cả cờ được khai báo đúng thì vòng lặp vẫn có thể tiêu tốn CPU khi rỗng. `Thread.onSpinWait()` chỉ là gợi ý cho vòng quay có chủ đích, không biến nó thành một cơ chế chờ tiết kiệm tài nguyên hoặc cung cấp thông báo khi có phần tử mới.

Nếu bên tiêu thụ cần ngủ chờ cho đến khi có việc, `BlockingQueue.take()` thường diễn đạt đúng nhu cầu hơn. Các phương thức chờ và chờ có thời hạn thuộc [BlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html), không có trên `ConcurrentLinkedQueue`.

Nếu kiến trúc đã có cơ chế đánh thức bên xử lý riêng, có thể dùng hàng đợi không chặn làm vùng đệm. Khi tự phối hợp thông báo và kiểm tra rỗng, cần thiết kế tránh mất tín hiệu; đó là một giao thức bổ sung, không phải chức năng sẵn có của lớp.

## 7. size, kiểm tra rồi lấy và duyệt

`size()` phải duyệt các nút, không phải phép đọc thời gian hằng số. Khi luồng khác thêm hoặc lấy trong lúc duyệt, kết quả có thể không phản ánh chính xác một ảnh chụp trạng thái duy nhất.

Vì vậy, không dùng:

```java
// Minh họa sai cách giữ giới hạn đầu vào.
if (queue.size() < limit) {
    queue.offer(job);
}
```

Ngoài chi phí duyệt, nhiều bên có thể cùng thấy còn chỗ rồi cùng thêm vượt giới hạn. Hàng đợi không bị ràng buộc dung lượng này không trở thành có giới hạn chỉ bằng phép kiểm tra bên ngoài.

Tương tự, không cần `isEmpty()` trước `poll()`. `poll()` đã trả kết quả cho lần thử nhận của chính nó; kết quả kiểm tra trước không giữ hộ một phần tử cho lần gọi sau.

Iterator là **yếu nhất quán (weakly consistent)**: cho phép duyệt cùng lúc với cập nhật, không ném `ConcurrentModificationException` vì các cập nhật đồng thời đó, nhưng không phải ảnh chụp bất biến tại một thời điểm duy nhất. Không dùng một lượt duyệt như chứng cứ mọi công việc đã được xử lý hoặc như một giao dịch khóa toàn bộ hàng đợi.

Các thao tác hàng loạt như `addAll`, `removeIf`, `forEach` cũng không được bảo đảm nguyên tử trên toàn nhóm. Một bên quan sát có thể thấy chỉ một phần những phần tử được thêm trong một thao tác hàng loạt.

## 8. Chọn theo nhu cầu chờ và áp lực đầu vào

| Nhu cầu | Hướng lựa chọn |
|---|---|
| Nhiều luồng dùng chung FIFO, bên nhận chỉ cần thử lấy rồi làm việc khác | `ConcurrentLinkedQueue` |
| Bên nhận cần chờ dữ liệu và cần sức chứa tối đa cố định | `ArrayBlockingQueue` |
| Cần các API chờ, hàng đợi liên kết và muốn tự đặt sức chứa | `LinkedBlockingQueue` với giới hạn dung lượng tường minh |
| Chỉ một luồng sử dụng, không cần đồng bộ hóa | Cân nhắc `ArrayDeque` theo yêu cầu của chương trình |

Không có loại hàng đợi nhanh nhất cho mọi tải. Cần đo với số bên gửi/nhận thực tế, kích thước thông điệp, mức tranh chấp và tốc độ xử lý. Hàng đợi liên kết có chi phí nút và thu gom rác; một vòng `poll` quay liên tục có thể làm kết quả đo sai mục tiêu vì đổi độ trễ lấy CPU.

Đặc biệt, nếu tốc độ thêm dài hạn vượt tốc độ xử lý, số phần tử tồn đọng và bộ nhớ sẽ tăng. Cần điều tiết, từ chối, giảm tải hoặc một hàng đợi có sức chứa phù hợp thay vì trông chờ cơ chế không chặn giải quyết quá tải.

## 9. Dừng và xử lý lỗi

`ConcurrentLinkedQueue` không có `close()`, `take()` hay cơ chế chờ phản ứng với ngắt. `poll()` cũng không khai báo `InterruptedException`. Nếu một luồng chạy vòng xử lý, chính vòng đó phải có chính sách dừng, kiểm tra tín hiệu và xử lý phần việc đã nhận.

Không thêm `null` làm dấu kết thúc. Một dấu kết thúc hợp lệ là giao thức ứng dụng và phải tính đến nhiều bên sản xuất/tiêu thụ; gửi dấu quá sớm có thể làm bỏ sót công việc đến sau.

Lấy phần tử ra không phải xác nhận xử lý thành công. Nếu bên tiêu thụ lỗi sau `poll()`, hàng đợi bộ nhớ không tự đưa lại phần tử, lưu bền vững hoặc bảo đảm xử lý đúng một lần. Những yêu cầu đó cần thiết kế vòng đời và cơ chế khôi phục riêng.

## 10. Tự kiểm tra

1. `poll()` trả `null` có làm luồng ngủ cho đến khi có việc không? — Không; lời gọi đã kết thúc với kết quả rỗng.
2. Có dùng `put()` hoặc `poll(timeout, unit)` trên `ConcurrentLinkedQueue` không? — Không; đó không phải API của lớp này.
3. Hai luồng cùng gửi có tạo một thứ tự xen kẽ cố định không? — Không; giữ đúng thứ tự các lần gửi tuần tự, nhưng các lần gửi chồng lấn có thể được phân xử theo nhiều cách.
4. Vì sao ví dụ có thể dừng vòng lấy khi gặp `null`? — Hai bên sản xuất đã hoàn tất và không còn lần gửi nào về sau.
5. `size() < limit` rồi `offer()` có bảo đảm dung lượng không? — Không.

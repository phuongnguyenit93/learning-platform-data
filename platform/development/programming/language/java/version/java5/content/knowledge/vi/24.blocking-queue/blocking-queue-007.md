# PriorityBlockingQueue và thứ tự ưu tiên

Một hàng đợi công việc thông thường thường lấy phần tử theo thứ tự vào trước ra trước. Nhưng trong hệ thống xử lý yêu cầu, một yêu cầu thanh toán có thể cần được chọn trước tác vụ tạo báo cáo dù được gửi sau. Khi nhiều luồng cùng gửi và nhận công việc, ta cần vừa có **quy tắc ưu tiên**, vừa có **thao tác hàng đợi an toàn khi truy cập đồng thời**.

`PriorityBlockingQueue<E>` đáp ứng hai nhu cầu đó: chọn phần tử theo thứ tự so sánh và cho phép bên tiêu thụ chờ khi chưa có phần tử. Nó vẫn là API hiện hành trong Java; ví dụ dưới chạy với Java 17 trở lên.

## 1. Đầu hàng đợi là phần tử nào?

`PriorityBlockingQueue` lấy phần tử nhỏ nhất theo một trong hai quy tắc:

- **Thứ tự tự nhiên:** kiểu phần tử triển khai `Comparable`.
- **Thứ tự riêng:** truyền `Comparator` khi tạo hàng đợi.

“Nhỏ nhất” là kết quả so sánh, không tự có nghĩa là mức ưu tiên nghiệp vụ thấp nhất. Nếu quy ước `1 = khẩn cấp`, `2 = bình thường`, `3 = chạy nền`, so sánh tăng dần cho kết quả mong muốn. Nếu quy ước số lớn hơn là quan trọng hơn, phải đảo chiều phần so sánh mức ưu tiên.

Ví dụ suy luận với tất cả phần tử đã có sẵn và chỉ một luồng lấy:

| Công việc | Thứ tự gửi | Mức ưu tiên | Thứ tự lấy mong muốn |
|---|---:|---:|---:|
| Tạo báo cáo | 1 | 3 | 4 |
| Thanh toán A | 2 | 1 | 1 |
| Thanh toán B | 3 | 1 | 2, nếu có khóa phụ phân xử |
| Gửi email | 4 | 2 | 3 |

Hai phần tử được so sánh bằng nhau **không được bảo đảm lấy theo thứ tự gửi**. Hàng đợi cũng không loại phần tử trùng như một tập hợp: `compare(a, b) == 0` không khiến phần tử thứ hai bị bỏ đi. Các quy tắc này được mô tả trong [PriorityBlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html), cùng quy tắc chọn đầu hàng đợi của [PriorityQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/PriorityQueue.html).

## 2. Comparator là chính sách nghiệp vụ

Ví dụ một công việc có ba thuộc tính:

```java
record Job(String name, int priority, long sequence) {}

Comparator<Job> order =
        Comparator.comparingInt(Job::priority)
                  .thenComparingLong(Job::sequence);
```

Đây là đoạn khai báo minh họa. `priority` quyết định nhóm ưu tiên; `sequence` là số thứ tự dùng khi hai công việc cùng nhóm. `thenComparingLong` chỉ được xét khi khóa trước bằng nhau. Xem hợp đồng ghép quy tắc tại [Comparator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html).

Với quy ước số lớn hơn quan trọng hơn, chỉ đảo chiều khóa chính:

```java
Comparator<Job> highestFirst =
        Comparator.comparingInt(Job::priority)
                  .reversed()
                  .thenComparingLong(Job::sequence);
```

Đặt `reversed()` sau toàn bộ chuỗi sẽ đảo cả thứ tự `sequence`, có thể làm công việc mới hơn được chọn trước khi cùng ưu tiên.

Không viết comparator bằng `a.priority() - b.priority()`: phép trừ số nguyên có thể tràn và trả dấu sai. Các hàm `comparingInt`, `Integer.compare` và `Long.compare` giúp thể hiện đúng phép so sánh. Comparator cần nhất quán, có tính bắc cầu, không thay đổi câu trả lời tùy thời điểm, và nên chạy nhanh vì nó tham gia thao tác trên cấu trúc dùng chung.

### Số thứ tự có đồng nghĩa thứ tự vào hàng đợi không?

Trong một luồng gửi, tăng dần `sequence` rồi thêm ngay vào hàng đợi có thể biểu diễn đúng thứ tự gửi. Với nhiều luồng, một `AtomicLong` có thể cấp số duy nhất nhưng chưa bảo đảm thứ tự thêm thực tế:

```text
Luồng A nhận sequence = 10 rồi tạm dừng.
Luồng B nhận sequence = 11 và thêm công việc vào hàng đợi.
Bên tiêu thụ lấy công việc 11.
Luồng A mới thêm công việc 10.
```

Khóa phụ không thể sắp lại công việc đã được lấy. Vì vậy, hãy gọi đây là **thứ tự theo số đã cấp**; nếu cần thứ tự tiếp nhận nghiêm ngặt, phải thiết kế một điểm tiếp nhận quản lý việc cấp số và gửi. Khi số thứ tự có thể tràn sau thời gian vận hành rất dài, chính sách khóa phụ cũng cần xử lý thay vì giả định `long` tăng mãi.

## 3. “Blocking” ở phía lấy, không phải giới hạn dung lượng

`PriorityBlockingQueue` không có giới hạn dung lượng logic. Số `2` trong `new PriorityBlockingQueue<>(2, order)` là dung lượng khởi tạo, không phải mức tối đa hai phần tử.

| Phương thức | Ý nghĩa cần nhớ |
|---|---|
| `take()` | Chờ khi rỗng; có thể bị ngắt bằng `InterruptedException` |
| `poll()` | Lấy ngay hoặc trả `null` |
| `poll(timeout, unit)` | Chờ phần tử tới hạn cho phép; trả `null` nếu chưa lấy được |
| `peek()` | Xem đầu hàng đợi, không lấy ra |
| `put(e)` | Thêm phần tử; không chờ một chỗ trống do giới hạn dung lượng |
| `offer(e, timeout, unit)` | Không tạo cơ chế chờ chỗ trống cho hàng đợi không bị chặn dung lượng này |
| `remainingCapacity()` | Trả `Integer.MAX_VALUE`, không phải số phần tử bộ nhớ còn chứa được |

Không giới hạn logic vẫn có thể hết bộ nhớ nếu tốc độ gửi vượt tốc độ xử lý. Đặt thời gian chờ cho `offer` không giải quyết tồn đọng. Nếu cần kiểm soát áp lực đầu vào (backpressure), phải có chính sách tiếp nhận riêng, chẳng hạn hạn mức công việc đang tồn đọng, từ chối yêu cầu hoặc cơ chế điều tiết có quản lý vòng đời đầy đủ. Không dùng `if (queue.size() < limit) queue.offer(job)` như giới hạn an toàn: nhiều luồng có thể cùng vượt qua phép kiểm tra.

## 4. Chương trình chạy đầy đủ

Lưu thành `PriorityQueueDemo.java`. Toàn bộ bốn công việc được thêm trước khi lấy để kết quả thứ tự không phụ thuộc lịch chạy luồng.

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.PriorityBlockingQueue;
import java.util.concurrent.TimeUnit;

public class PriorityQueueDemo {
    record Job(String name, int priority, long sequence) {}

    static final Comparator<Job> ORDER =
            Comparator.comparingInt(Job::priority)
                      .thenComparingLong(Job::sequence);

    public static void main(String[] args) throws InterruptedException {
        PriorityBlockingQueue<Job> queue =
                new PriorityBlockingQueue<>(2, ORDER);

        // All submissions finish before any removal.
        queue.put(new Job("report", 3, 0));
        queue.put(new Job("payment-A", 1, 1));
        queue.put(new Job("payment-B", 1, 2));
        queue.put(new Job("email", 2, 3));

        System.out.println("size: " + queue.size());
        System.out.println("remaining capacity: "
                + queue.remainingCapacity());

        List<Job> snapshot = new ArrayList<>(queue);
        snapshot.sort(ORDER);
        System.out.println("sorted snapshot: "
                + snapshot.stream().map(Job::name).toList());
        System.out.println("size after snapshot: " + queue.size());

        for (int i = 0; i < 4; i++) {
            Job job = queue.take();
            System.out.println("take: " + job.name());
        }
        System.out.println("empty poll: " + queue.poll());
        System.out.println("timed poll: "
                + queue.poll(10, TimeUnit.MILLISECONDS));

        BlockingQueue<Job> incoming =
                new PriorityBlockingQueue<>(2, ORDER);
        Thread consumer = new Thread(() -> {
            try {
                System.out.println("consumer got: "
                        + incoming.take().name());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");
        consumer.start();
        incoming.put(new Job("later", 2, 4));
        consumer.join();
        System.out.println("consumer finished: "
                + !consumer.isAlive());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 PriorityQueueDemo.java
java PriorityQueueDemo
```

Stdout trong lượt chạy bình thường, không có tác nhân bên ngoài ngắt luồng:

```text
size: 4
remaining capacity: 2147483647
sorted snapshot: [payment-A, payment-B, email, report]
size after snapshot: 4
take: payment-A
take: payment-B
take: email
take: report
empty poll: null
timed poll: null
consumer got: later
consumer finished: true
```

Những điều cần quan sát:

1. Khởi tạo với `2` nhưng chứa được bốn công việc. Đây không phải hàng đợi có sức chứa tối đa hai.
2. `payment-A` và `payment-B` cùng ưu tiên, được phân xử bằng `sequence`. Không phải tên công việc hay thứ tự duyệt nội bộ quyết định kết quả này.
3. Bản sao được sắp xếp chỉ phục vụ quan sát; hàng đợi gốc vẫn có bốn phần tử.
4. Sau khi lấy hết, `poll()` trả `null`. `poll` có thời gian chờ cũng trả `null` vì không có bên gửi cho hàng đợi đó.
5. Phần cuối dùng hai luồng cùng hàng đợi `incoming`. Nếu bên tiêu thụ tới trước thì `take()` chờ; nếu bên gửi tới trước thì lấy được ngay. Không cần giả định luồng nào chạy trước để có kết quả `later`.

## 5. Lấy theo ưu tiên khác với duyệt có sắp xếp

`for-each`, iterator và `toArray()` không bảo đảm liệt kê phần tử theo thứ tự ưu tiên. Cấu trúc bên trong chỉ cần phục vụ lấy đầu hàng đợi đúng quy tắc, không phải giữ toàn bộ dãy đã được sắp xếp để duyệt.

Nếu cần bảng quan sát đã sắp xếp, sao chép rồi `sort` bằng chính comparator như chương trình. Khi có luồng khác hoạt động, bản sao chỉ là dữ liệu quan sát trong lúc sao chép; nó không hứa phản ánh trạng thái mới nhất lúc hiển thị.

Nếu muốn lấy ra một nhóm theo ưu tiên, có thể dùng `drainTo`:

```java
// Đoạn minh họa trong phạm vi có queue là PriorityBlockingQueue<Job>.
List<Job> selected = new ArrayList<>();
queue.drainTo(selected, 10);
```

Thao tác này **thay đổi hàng đợi**, đưa tối đa mười phần tử sang danh sách; nó không chờ cho đủ mười phần tử. Đừng dùng nó như một thao tác đọc phục vụ giao diện. Những gì được gửi tới sau đó không thể làm thay đổi thứ tự của nhóm đã lấy ra.

## 6. Đừng thay đổi khóa ưu tiên khi phần tử đang chờ

An toàn luồng của hàng đợi không biến mọi đối tượng chứa bên trong thành bất biến hoặc an toàn khi sửa đồng thời. Nếu sửa trường ưu tiên của một phần tử đang nằm trong hàng đợi, cấu trúc không tự biết để sắp xếp lại.

Ví dụ suy luận: công việc A được thêm với ưu tiên 5, rồi một luồng đổi thuộc tính đó thành 1. Không được suy ra rằng A sẽ trở thành đầu hàng đợi ngay. Tương tự, comparator dùng thời gian hiện tại để “tăng ưu tiên theo tuổi” có thể thay đổi quan hệ so sánh của các phần tử đã nằm yên trong cấu trúc mà không có thao tác tái sắp xếp.

Chọn khóa sắp xếp bất biến trong thời gian chờ. Nếu cần đổi ưu tiên, thiết kế thao tác cập nhật có phối hợp: xác định công việc còn chờ hay đã được nhận, loại bản cũ nếu còn, rồi thêm bản mới. `remove` và `offer` là hai thao tác riêng; ghép chúng không tự thành giao dịch, và bên tiêu thụ có thể đã lấy công việc giữa các bước. Hệ thống thực tế thường cần định danh công việc, trạng thái nhận việc và xử lý bản đã hủy hoặc phiên bản cũ.

## 7. Ba giới hạn của “ưu tiên” trong hệ thống đồng thời

**Không bảo đảm thứ tự toàn cục giữa mọi lần gửi.** Nếu công việc ưu tiên 3 đã được lấy trước khi công việc ưu tiên 1 được gửi vào, nó không bị thu hồi. Hàng đợi lựa chọn từ các công việc đang có ở thời điểm lấy.

**Không bảo đảm thứ tự hoàn thành.** Hai luồng có thể lần lượt nhận A rồi B nhưng B hoàn thành trước vì chạy nhanh hơn. Cũng không thể lấy thứ tự các dòng log giữa các luồng làm bằng chứng đầy đủ về thứ tự nhận công việc.

**Không tự ngắt công việc đang chạy.** Yêu cầu khẩn cấp mới tới có thể đứng đầu hàng đợi, nhưng nếu mọi luồng đều đang bận thì vẫn phải chờ một luồng sẵn sàng. Mức ưu tiên của phần tử khác với độ ưu tiên luồng của JVM/hệ điều hành.

Các nhận xét trên giúp phân biệt **chính sách chọn việc chờ** với một bộ lập lịch có quyền điều khiển toàn bộ quá trình thực thi.

Nếu công việc khẩn cấp tới liên tục, công việc ưu tiên thấp có thể chờ rất lâu hoặc bị bỏ đói (starvation). Khóa phụ chỉ phân xử trong cùng mức ưu tiên, không giải quyết vấn đề này. Cần chính sách nghiệp vụ riêng như dành tỷ lệ xử lý cho từng nhóm hoặc chọn việc theo lượt giữa nhiều hàng đợi; không chỉ thêm trường `sequence` rồi coi là đã công bằng.

## 8. Lựa chọn và lỗi thường gặp

| Nhu cầu | Lựa chọn cần cân nhắc |
|---|---|
| Một luồng, cần chọn theo ưu tiên | `PriorityQueue` thường đủ; nó không hỗ trợ an toàn truy cập đồng thời khi có sửa đổi |
| Nhiều luồng, cần lấy theo ưu tiên và chờ khi rỗng | `PriorityBlockingQueue` |
| Cần FIFO với dung lượng tối đa cố định | `ArrayBlockingQueue`, nếu không cần chọn theo ưu tiên |
| Chỉ cho phép lấy sau một thời điểm | Cơ chế trì hoãn như `DelayQueue`; ưu tiên cao không tự tạo điều kiện “chưa tới giờ” |

Các lỗi cần tránh:

- Cho rằng mọi `BlockingQueue` đều FIFO.
- Dùng kiểu không `Comparable` với thứ tự tự nhiên mà không truyền comparator phù hợp.
- Thêm `null` như một dấu kết thúc; hàng đợi không chấp nhận `null`.
- Dựa vào thứ tự in `queue` để xác nhận thứ tự lấy.
- Dùng comparator có trạng thái thay đổi hoặc thao tác I/O tốn thời gian.
- Nhầm dung lượng khởi tạo với giới hạn bộ nhớ.

`PriorityBlockingQueue` không cung cấp thao tác đóng chung, lưu trữ bền vững hay xác nhận xử lý. Việc dừng các bên tiêu thụ và bảo toàn công việc đang chạy thuộc thiết kế vòng đời của ứng dụng, không phải hệ quả tự động của thứ tự ưu tiên.

## 9. Tự kiểm tra

1. Hai công việc có cùng `priority` thì có tự FIFO không? — Không; cần khóa phụ phù hợp với ý nghĩa thứ tự mong muốn.
2. Tạo hàng đợi với dung lượng khởi tạo 100 có từ chối phần tử thứ 101 không? — Không; đó không phải giới hạn sức chứa.
3. Công việc khẩn cấp tới sau có dừng ngay công việc thường đang chạy không? — Không; thứ tự chỉ áp dụng khi chọn từ hàng đợi.
4. Vì sao dùng `record Job` có ích trong ví dụ? — Các khóa sắp xếp được giữ bất biến, tránh việc sửa ưu tiên âm thầm làm sai giả định của cấu trúc.
5. Sao chép rồi sắp xếp và `drainTo` khác nhau thế nào? — Cách đầu chỉ tạo dữ liệu quan sát; cách sau lấy phần tử khỏi hàng đợi.

# Giới hạn an toàn luồng của PriorityQueue

## 1. Quy tắc cốt lõi: PriorityQueue không tự đồng bộ hóa

PriorityQueue thông thường không phải cấu trúc an toàn luồng. Nếu nhiều luồng cùng truy cập một instance và có luồng thay đổi hàng đợi, ứng dụng phải có cơ chế đồng bộ hóa phù hợp.

“Thay đổi” gồm các thao tác như offer, poll, remove, clear và các thao tác khác làm đổi nội dung. Không thể chỉ khóa luồng ghi rồi để luồng đọc peek hoặc size tự do trên cùng đối tượng đang được sửa.

Nguyên nhân không chỉ là hai lần thêm có thể va chạm. Cấu trúc còn có mảng, kích thước và quan hệ heap cần được quan sát nhất quán. Đồng bộ hóa đúng cũng thiết lập quan hệ công bố và nhìn thấy dữ liệu giữa các luồng.

Bài dùng các API hiện hành và ví dụ chạy được trên Java 17+. Không dùng việc một lần chạy “chưa thấy lỗi” để chứng minh mã thiếu đồng bộ là đúng.

## 2. Những tình huống cần phân biệt

| Tình huống | Điều kiện cần chú ý |
| --- | --- |
| Mỗi luồng sở hữu một PriorityQueue riêng | Không có chia sẻ hàng đợi; vẫn xem xét các đối tượng phần tử có được chia sẻ không |
| Một luồng tạo và dùng hàng đợi | Phù hợp với PriorityQueue thông thường |
| Nhiều luồng chỉ đọc một hàng đợi đã chuẩn bị xong | Cần công bố an toàn, không sửa hàng đợi và giữ dữ liệu dùng để so sánh ổn định |
| Nhiều luồng dùng cùng hàng đợi, có sửa | Cần một giao thức khóa chung hoặc cấu trúc đồng thời phù hợp |
| Một luồng đọc trong khi luồng khác sửa | Vẫn là trường hợp cần đồng bộ hóa |

“Chỉ đọc sau khi xây xong” khác với “đang đọc trong lúc xây”. Đưa một tham chiếu sang luồng khác không có nghĩa mọi cách truyền tham chiếu đều tạo công bố an toàn.

Những cơ chế như bắt đầu luồng sau khi khởi tạo dữ liệu, dùng khóa đúng cách hoặc các cơ chế công bố được mô hình bộ nhớ Java quy định có thể thiết lập quan hệ cần thiết. Chọn cơ chế theo thiết kế toàn bộ ứng dụng, không chỉ theo kiểu của biến.

## 3. Những cách tưởng an toàn nhưng chưa đủ

### Biến tham chiếu volatile

```java
// Minh họa, chưa làm các thao tác hàng đợi an toàn:
volatile PriorityQueue<Job> queue;
```

Volatile có thể đóng vai trò công bố tham chiếu và dữ liệu theo quy tắc bộ nhớ, nhưng không biến các lần `queue.offer(...)` và `queue.poll()` thành thao tác đồng bộ trên cấu trúc bên trong.

Mảng, size và các bước điều chỉnh heap vẫn là trạng thái của đối tượng PriorityQueue. Không thể sửa chúng đồng thời chỉ nhờ biến tham chiếu là volatile.

### Chỉ khóa một vài thao tác

Nếu offer dùng khóa A nhưng poll không khóa, hoặc poll dùng khóa B, giao thức bảo vệ trạng thái không còn nhất quán.

Một wrapper chỉ có tác dụng khi mọi đường truy cập tới hàng đợi đều đi qua nó. Trả trực tiếp hàng đợi hoặc iterator ra ngoài để bên gọi sửa sẽ phá giả định đó.

### Dựa vào ConcurrentModificationException

Iterator fail-fast của PriorityQueue có thể phát hiện một số thay đổi không đúng giao thức. Nó không phải cơ chế đồng bộ hóa và không bảo đảm phát hiện mọi tranh chấp.

Không có ngoại lệ không đồng nghĩa không có race condition. Ngoại lệ xuất hiện cũng không sửa lại trạng thái đã bị truy cập sai.

## 4. Cách thứ nhất: bọc bằng một khóa chung

Với nhu cầu đơn giản, có thể giữ PriorityQueue riêng bên trong một lớp và đồng bộ mọi thao tác truy cập.

Ví dụ chạy đầy đủ, lưu thành `LockedPriorityQueueDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class LockedPriorityQueueDemo {
    record Job(int priority, String name) {
    }

    static final class LockedQueue<E> {
        private final PriorityQueue<E> queue;

        LockedQueue(Comparator<? super E> comparator) {
            queue = new PriorityQueue<>(comparator);
        }

        synchronized void offer(E item) {
            queue.offer(Objects.requireNonNull(item));
        }

        synchronized E poll() {
            return queue.poll();
        }

        synchronized int size() {
            return queue.size();
        }

        synchronized List<E> drainInPriorityOrder() {
            List<E> result = new ArrayList<>(queue.size());
            E item;
            while ((item = queue.poll()) != null) {
                result.add(item);
            }
            return result;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        LockedQueue<Job> queue = new LockedQueue<>(
                Comparator.comparingInt(Job::priority)
                        .thenComparing(Job::name));

        CountDownLatch start = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread first = new Thread(() -> produce(
                queue, start, failure,
                new Job(30, "C"), new Job(10, "A")));

        Thread second = new Thread(() -> produce(
                queue, start, failure,
                new Job(40, "D"), new Job(20, "B")));

        first.start();
        second.start();
        start.countDown();

        first.join();
        second.join();

        if (failure.get() != null) {
            throw new AssertionError("Producer failed", failure.get());
        }

        System.out.println("size=" + queue.size());

        List<Job> jobs = queue.drainInPriorityOrder();
        StringBuilder order = new StringBuilder();
        for (Job job : jobs) {
            if (order.length() > 0) {
                order.append(",");
            }
            order.append(job.name());
        }

        System.out.println("order=" + order);
        System.out.println("remaining=" + queue.size());
    }

    static void produce(
            LockedQueue<Job> queue,
            CountDownLatch start,
            AtomicReference<Throwable> failure,
            Job... jobs) {
        try {
            start.await();
            for (Job job : jobs) {
                queue.offer(job);
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            failure.compareAndSet(null, exception);
        } catch (RuntimeException exception) {
            failure.compareAndSet(null, exception);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 LockedPriorityQueueDemo.java
java LockedPriorityQueueDemo
```

Kết quả:

```text
size=4
order=A,B,C,D
remaining=0
```

Các nhà sản xuất có thể thêm theo thứ tự thực thi khác nhau. Kết quả lấy ra vẫn xác định vì phần main chờ cả hai luồng kết thúc trước khi rút hàng đợi, và Comparator có quy tắc rõ ràng.

Tính đúng đắn đến từ giao thức khóa, đóng gói trạng thái và quan hệ đồng bộ giữa các luồng. Ví dụ không tuyên bố chỉ một lần chạy là phép chứng minh đầy đủ cho mọi mã đồng thời.

## 5. Vì sao phương thức rút toàn bộ giữ khóa suốt vòng lặp?

Mỗi phương thức synchronized dùng monitor của cùng instance LockedQueue. Queue bên trong là private và không bị trả ra ngoài, nên các đường truy cập được bảo vệ bằng cùng khóa.

`drainInPriorityOrder` giữ khóa cho toàn bộ thao tác lấy ra danh sách. Không luồng nào gọi các phương thức của wrapper có thể chen vào thay đổi hàng đợi trong lúc vòng lặp đó chạy.

Nếu chỉ gọi poll nhiều lần ở bên ngoài wrapper, mỗi poll vẫn an toàn riêng lẻ, nhưng các luồng khác có thể thêm/lấy giữa hai lần gọi.

Đổi lại, rút toàn bộ một hàng đợi lớn giữ khóa lâu và làm các bên khác chờ. Thiết kế này phù hợp để minh họa một thao tác tổng hợp có ranh giới rõ; ứng dụng thực cần cân nhắc độ trễ, kích thước batch và chính sách xử lý.

Danh sách trả ra là một đối tượng khác nhưng vẫn chứa tham chiếu tới các phần tử. Khóa của wrapper không tự làm mọi đối tượng phần tử bất biến hoặc an toàn luồng. Ví dụ dùng record với các thành phần ổn định để tránh vấn đề thay đổi khóa ưu tiên.

## 6. Cách thứ hai: dùng PriorityBlockingQueue

Nếu cần chia sẻ hàng đợi ưu tiên giữa nhiều luồng, `PriorityBlockingQueue` cung cấp thao tác truy cập đồng thời và các phương thức chờ phần tử như take.

Đoạn minh họa:

```java
import java.util.Comparator;
import java.util.concurrent.PriorityBlockingQueue;

// Bên trong một phương thức có thể ném InterruptedException:
// PriorityBlockingQueue<Job> queue = new PriorityBlockingQueue<>(
//         11, Comparator.comparingInt(Job::priority));
// queue.offer(new Job(10, "A"));
// Job job = queue.take();
```

Đây là minh họa API, không phải chương trình độc lập thứ hai. Job có thể dùng record của ví dụ trước.

Cần hiểu các giới hạn:

- `take()` chờ khi chưa có phần tử; `poll()` không đối số trả ngay null khi rỗng.
- Hàng đợi về mặt hợp đồng là không giới hạn sức chứa; số 11 ở constructor là sức chứa ban đầu, không phải giới hạn số công việc.
- Cung cấp nhiều công việc hơn khả năng xử lý vẫn có thể làm bộ nhớ tăng. Tên Blocking không tự tạo cơ chế gây sức ép ngược lên bên thêm.
- Các phần tử có cùng mức ưu tiên không tự được bảo đảm FIFO. Cần khóa phụ nếu nghiệp vụ yêu cầu.
- Nó không tự chờ đến “thời điểm đến hạn” của một công việc. Hàng đợi ưu tiên khác hàng đợi trì hoãn như DelayQueue.
- Nó không làm các đối tượng phần tử hoặc Comparator có thể thay đổi trở nên an toàn một cách tự động.

Sử dụng cấu trúc đồng thời giải quyết đồng bộ cho các thao tác của cấu trúc đó. Nó không thay thế việc thiết kế giao thức hoàn thành, hủy, giới hạn tải hoặc ngừng hệ thống.

## 7. An toàn từng thao tác không đồng nghĩa nguyên tử cả chuỗi

Ngay cả với PriorityBlockingQueue, đoạn sau có race condition về logic:

```java
// Không nên dựa vào kiểm tra này như một cam kết:
// if (!queue.isEmpty()) {
//     Job job = queue.remove();
// }
```

Một luồng khác có thể lấy phần tử cuối sau isEmpty. Nếu muốn lấy ngay khi có, gọi poll một lần và xử lý null. Nếu muốn chờ, dùng take theo chính sách của ứng dụng.

Tương tự:

```java
// Job expected = queue.peek();
// Job actual = queue.poll();
```

hai biến không được bảo đảm cùng phần tử khi có luồng khác sửa hàng đợi.

Đặt `synchronized(queue)` quanh các lời gọi PriorityBlockingQueue cũng không tự buộc mọi luồng dùng nội bộ khóa đó. Các thao tác của lớp sử dụng cơ chế đồng bộ riêng; một giao dịch ở mức ứng dụng cần giao thức mà mọi bên tham gia đều tuân thủ.

Nếu cần “chỉ lấy khi thỏa điều kiện và đồng thời cập nhật trạng thái khác”, phải thiết kế thao tác nguyên tử phù hợp ở lớp quản lý, không ghép vài lời gọi an toàn riêng lẻ rồi coi cả chuỗi đã nguyên tử.

## 8. Thứ tự lấy công việc không phải thứ tự hoàn thành

PriorityQueue và PriorityBlockingQueue chỉ quyết định công việc nào ở đầu **trong số các phần tử hiện có** theo Comparator.

Chúng không bảo đảm:

- công việc ưu tiên cao đến muộn được chạy trước một công việc đã lấy ra;
- công việc đã bắt đầu bị ngắt để nhường chỗ cho công việc mới ưu tiên cao hơn;
- nhiều worker hoàn thành theo thứ tự poll/take;
- worker không bị trì hoãn bởi bộ lập lịch của hệ điều hành.

Trong ví dụ chính, mọi nhà sản xuất đã kết thúc trước khi rút hàng đợi nên thứ tự A,B,C,D rõ ràng. Nếu vừa thêm vừa xử lý, một công việc ưu tiên thấp có thể được lấy trước lúc công việc ưu tiên cao được thêm vào. Điều đó không tự là lỗi của hàng đợi.

Nếu cần điều phối ưu tiên mạnh hơn, phải xác định thêm thời điểm nhận công việc, quyền ngắt, số worker và chính sách hoàn thành.

## 9. Comparator và khóa ưu tiên phải ổn định

Khóa chung chỉ bảo vệ thao tác trên hàng đợi nếu mọi thay đổi liên quan đều tuân thủ giao thức. Nếu một luồng ngoài sửa priority của phần tử đang nằm trong heap, cấu trúc không tự sắp lại.

Ngay cả dùng một trường priority volatile cũng không giải quyết việc phục hồi heap. Nhìn thấy giá trị mới và duy trì đúng quan hệ heap là hai vấn đề khác nhau.

Nên giữ các khóa dùng so sánh bất biến trong thời gian phần tử nằm trong hàng đợi; muốn đổi ưu tiên thì thiết kế thao tác xóa/thay/thêm lại phù hợp. Với nhiều luồng, toàn bộ quy trình đó cũng cần ranh giới đồng bộ đúng.

Comparator không nên dựa vào trạng thái bên ngoài thay đổi tùy thời điểm. Nếu nhiều lời gọi compare cho cùng dữ liệu có kết quả bất nhất, việc dùng một collection đồng thời không thể sửa hợp đồng thứ tự bị phá.

## 10. Cách kiểm tra và áp dụng

1. Xác định ai sở hữu hàng đợi và những luồng nào truy cập.
2. Nếu có chia sẻ và thay đổi, chọn một giao thức khóa bao phủ toàn bộ đường truy cập hoặc dùng cấu trúc đồng thời phù hợp.
3. Phân biệt thao tác riêng lẻ với yêu cầu nguyên tử nhiều bước.
4. Quy định chính sách rỗng, chờ, ngừng và giới hạn lượng công việc.
5. Giữ phần tử và Comparator phù hợp với hợp đồng thứ tự.
6. Dùng kiểm thử đồng thời để hỗ trợ phát hiện lỗi, nhưng không dựa vào sleep hoặc “chạy nhiều lần chưa hỏng” thay cho phân tích đồng bộ.

Bài tập: bỏ synchronized ở riêng offer của wrapper. Giải thích bằng giao thức trạng thái vì sao mã đã sai, kể cả nếu một số lần chạy vẫn in đúng. Không cần tìm một stdout lỗi cố định để thừa nhận race condition tồn tại.

## Tài liệu đối chiếu

- [PriorityQueue — Yêu cầu đồng bộ hóa khi dùng nhiều luồng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PriorityQueue.html).
- [PriorityBlockingQueue — Truy cập đồng thời và các giới hạn](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html).
- [BlockingQueue — Hợp đồng thao tác chờ và hiệu ứng bộ nhớ](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html).
- [JLS §17.4.5 — Quan hệ happens-before](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5).

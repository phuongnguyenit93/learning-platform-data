# PriorityBlockingQueue và giới hạn dung lượng thực tế

`PriorityBlockingQueue` giải quyết việc **chọn phần tử theo ưu tiên trong môi trường nhiều luồng**. Nó không tự giải quyết việc **giới hạn lượng công việc được nhận**.

Hai yêu cầu đó thường đi cùng nhau trong một bộ lập lịch, nhưng là hai quyết định độc lập:

- Trong các công việc đã được nhận và còn chờ, việc nào được lấy trước?
- Khi công việc chưa xử lý đã quá nhiều, có được nhận thêm không?

Sai lầm phổ biến là nghĩ `new PriorityBlockingQueue<>(100)` chỉ cho chứa `100` việc, hoặc nghĩ `put` sẽ chặn bên sản xuất khi đạt mức đó. Đối số constructor là **dung lượng khởi tạo**, không phải sức chứa tối đa.

Bài học dùng API Java 17, giải thích thứ tự ưu tiên, các giới hạn bộ nhớ thực tế và một ví dụ giới hạn tiếp nhận có giao thức giấy phép rõ ràng.

Các thuật ngữ cần phân biệt:

- **Dung lượng khởi tạo (initial capacity):** quy mô lưu trữ ban đầu để cấu trúc có thể tự tăng khi thêm.
- **Giới hạn tiếp nhận:** số lượng mà ứng dụng cho phép giữ trong phạm vi đã định nghĩa.
- **Ưu tiên lấy ra:** thứ tự chọn trong các phần tử hiện đang đủ điều kiện được lấy.
- **Công việc đang chạy:** phần tử đã rời queue và không còn tham gia lựa chọn trong queue.
- **Điều tiết ngược (backpressure):** phản hồi quá tải về phía gửi bằng chờ, từ chối hoặc một chính sách rõ ràng.
- **Giấy phép (permit):** một đơn vị ngân sách được cấp trước khi tiếp nhận và trả lại theo đúng điểm giải phóng tài nguyên.

## 1. PriorityBlockingQueue thực sự bảo đảm gì?

`PriorityBlockingQueue` là hàng đợi đồng thời **không có giới hạn sức chứa theo chính sách của lớp**, dùng thứ tự tự nhiên hoặc một `Comparator` để chọn phần tử. Việc thêm vẫn có thể thất bại do cạn tài nguyên, chẳng hạn `OutOfMemoryError`; “không giới hạn” không có nghĩa máy có bộ nhớ vô hạn. [Java 17: PriorityBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html)

Từ `Blocking` cần được đọc theo hợp đồng cụ thể:

- `take` có thể chờ khi chưa có phần tử.
- `poll(timeout, unit)` có thể chờ phần tử trong một khoảng thời gian.
- `put` không chờ một chỗ trống do queue đầy, vì lớp không có giới hạn sức chứa kiểu đó.
- Timed `offer` không tạo thêm một giới hạn tiếp nhận.

Có thể hình dung:

~~~text
Phía gửi:
    thêm hợp lệ -> queue có thể tăng vùng lưu trữ

Phía nhận:
    queue rỗng -> take chờ
    queue có phần tử -> lấy phần tử đứng đầu theo thứ tự ưu tiên
~~~

Đây là hàng đợi chặn ở phía lấy khi rỗng, không phải một bộ đệm ưu tiên có sức chứa cố định.

## 2. initialCapacity không phải maximumCapacity

Đoạn minh họa trong một phương thức:

~~~java
java.util.concurrent.PriorityBlockingQueue<Integer> queue =
        new java.util.concurrent.PriorityBlockingQueue<>(1);

queue.offer(30);
queue.offer(10);
queue.offer(20);
~~~

Ba phần tử có thể được nhận dù constructor có số `1`. Lớp được phép mở rộng vùng lưu trữ.

Điều tương tự không đúng với `ArrayBlockingQueue<>(1)`, nơi đối số là sức chứa cố định của bộ đệm. Đọc cùng một số ở hai constructor khác nhau nhưng bỏ tên tham số có thể dẫn đến một thiết kế quá tải sai hoàn toàn.

### 2.1. remainingCapacity là dấu hiệu hợp đồng

`PriorityBlockingQueue.remainingCapacity()` luôn trả `Integer.MAX_VALUE` vì lớp không bị ràng buộc sức chứa theo hợp đồng. [Java 17: PriorityBlockingQueue.remainingCapacity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html#remainingCapacity())

Không diễn giải kết quả ấy thành:

- Máy còn đủ bộ nhớ cho đúng từng đó phần tử.
- Đây là một số lượng chỗ trống thực đang được đặt sẵn.
- `size + remainingCapacity` là giới hạn nghiệp vụ của ứng dụng.
- Lần thêm kế tiếp chắc chắn không thể lỗi vì cạn tài nguyên.

Đó là giá trị báo rằng queue không có chính sách giới hạn nội tại kiểu bounded buffer.

### 2.2. Đặt initialCapacity rất lớn cũng không tạo giới hạn

Đặt trước dung lượng lớn có thể ảnh hưởng việc cấp phát ban đầu và số lần mở rộng về sau. Nó không cấm queue phát triển vượt mức đó.

Nếu cần một ngân sách công việc, phải có cơ chế tiếp nhận riêng. Không dùng cấu hình lưu trữ ban đầu thay cho một quy tắc nghiệp vụ.

## 3. put và timed offer không làm producer chờ vì đầy

| Phương thức trên PriorityBlockingQueue | Ý nghĩa liên quan sức chứa |
|---|---|
| `offer(item)` | Không trả `false` vì hết chỗ theo một giới hạn capacity nội tại. |
| `add(item)` | Thêm theo hợp đồng của lớp; không dùng làm phép kiểm tra một mức tối đa do constructor đặt ra. |
| `put(item)` | Không chờ chỗ trống do queue đầy. |
| `offer(item, timeout, unit)` | Không đợi sức chứa; tham số thời hạn không tạo cơ chế tiếp nhận có giới hạn. |
| `take()` | Có thể chờ vì queue rỗng. |
| `poll(timeout, unit)` | Có thể chờ phần tử khi rỗng, rồi trả `null` nếu hết thời gian mà chưa có. |

Javadoc nêu rõ `put` không chặn do sức chứa và timed `offer` không chặn hoặc trả `false` theo điều kiện đầy; tham số thời gian của timed offer bị bỏ qua ở lớp này. [Java 17: put và timed offer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html#offer(E,long,java.util.concurrent.TimeUnit))

Cần hiểu “không chờ vì đầy” đúng phạm vi. Lớp vẫn phải phối hợp truy cập nội bộ, so sánh và có thể cấp phát/mở rộng mảng. Không suy rằng một lần thêm luôn hoàn tất trong một khoảng thời gian cố định, hoàn toàn không có tranh chấp hay không có chi phí cấp phát.

Mã nguồn OpenJDK 17 cho thấy `put` và timed `offer` chuyển sang đường thêm của `offer`, còn đường này vẫn dùng khóa nội bộ và xử lý tăng vùng chứa. [OpenJDK 17: PriorityBlockingQueue](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/concurrent/PriorityBlockingQueue.java)

### 3.1. Đổi ArrayBlockingQueue sang PriorityBlockingQueue thay đổi cả điều tiết tải

Một hệ thống đang dựa vào `ArrayBlockingQueue.put` để làm chậm producer sẽ mất chính cơ chế chờ sức chứa đó nếu chỉ thay bằng PriorityBlockingQueue.

Thay đổi có thể vẫn biên dịch vì hai lớp cùng là `BlockingQueue`. Nhưng hợp đồng sức chứa khác nhau. Kiểm tra tương thích kiểu chưa đủ để chứng minh tương thích hành vi.

### 3.2. Không chờ đầy không có nghĩa chấp nhận mọi đầu vào

PriorityBlockingQueue không chấp nhận `null`. Nếu dùng thứ tự tự nhiên, phần tử phải có khả năng so sánh phù hợp; dữ liệu không so sánh được có thể gây `ClassCastException`.

Một comparator sai, dữ liệu không hợp lệ hoặc cạn tài nguyên vẫn là các vấn đề riêng. Đừng gộp mọi thất bại thành kết quả quá tải theo capacity.

## 4. Ưu tiên là thứ tự lấy trong tập đang chờ

Priority queue chọn phần tử nhỏ nhất theo thứ tự đã quy định. Nếu muốn số `1` biểu diễn khẩn hơn số `5`, comparator tăng dần theo trường priority là phù hợp.

Ví dụ kiểu dữ liệu bất biến và comparator:

~~~java
record Work(String name, int priority, long sequence) {}

java.util.Comparator<Work> order =
        java.util.Comparator.comparingInt(Work::priority)
                            .thenComparingLong(Work::sequence);
~~~

Đây là đoạn minh họa dùng cú pháp Java 17 trong phạm vi khai báo phù hợp. Comparator xét priority trước, sequence sau. Các hàm tạo comparator giúp tránh cách trừ hai số có thể bị tràn khi so sánh. [Java 17: Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)

### 4.1. Ưu tiên bằng nhau không tự có FIFO

PriorityBlockingQueue không bảo đảm thứ tự giữa các phần tử bằng nhau về ưu tiên. Nếu cần thứ tự phụ, hãy đưa nó vào comparator.

Một số thứ tự được cấp lúc tạo yêu cầu có thể làm tiêu chí phụ. Tuy nhiên, trong môi trường nhiều luồng, thứ tự cấp số và thứ tự thực sự được nhận vào queue có thể khác nhau. Phải định nghĩa “đến trước” nghĩa là tạo trước, bắt đầu gọi trước hay đã được tiếp nhận trước.

Ví dụ trong chương trình dùng sequence đã được gán rõ, nên kiểm chứng thứ tự theo metadata đó; nó không tuyên bố tự khôi phục mọi khái niệm FIFO ngoài hệ thống.

### 4.2. Phần tử đang chạy không còn bị queue sắp lại

Một công việc ít khẩn đã được consumer lấy ra có thể đang chạy khi việc khẩn hơn được đưa vào. Queue ưu tiên không tự dừng hoặc lấy lại công việc đang chạy.

Với nhiều consumer, thứ tự lấy ra cũng không bảo đảm thứ tự hoàn tất. Các công việc có thể tốn thời gian khác nhau hoặc bị ảnh hưởng bởi tài nguyên khác.

### 4.3. Tính ưu tiên không tạo tính công bằng dài hạn

Nếu việc khẩn liên tục xuất hiện, việc ít khẩn có thể đợi rất lâu. Đó là vấn đề đói tài nguyên của chính sách lập lịch, khác với tính an toàn của queue.

Nếu cần giới hạn thời gian chờ theo nhóm, có thể cần ngân sách theo nhóm, luân phiên có trọng số hoặc cơ chế tăng ưu tiên được thiết kế riêng. Không chỉ thêm một trường priority rồi mặc nhiên có mọi bảo đảm công bằng.

### 4.4. Không sửa trường làm thay đổi thứ tự khi phần tử còn nằm trong heap

Queue không tự theo dõi mọi thay đổi trong đối tượng đã được thêm. Nếu sửa priority tại chỗ, heap không mặc nhiên được sắp lại theo giá trị mới.

Ưu tiên giá trị bất biến. Khi cần đổi ưu tiên, phải có giao thức cập nhật rõ, có thể là gỡ rồi thêm lại; riêng hai lời gọi đó không tự là một giao dịch chung với các bên khác.

Tương tự, comparator phụ thuộc vào dữ liệu ngoài đang thay đổi, chẳng hạn thời gian hiện tại, không tự làm heap tái cân bằng liên tục. Cần thiết kế thuật toán lập lịch tương ứng.

## 5. Duyệt khác với lấy theo ưu tiên

Một heap chỉ bảo đảm cách chọn phần tử đứng đầu; mảng bên trong không cần được sắp tăng hoàn toàn.

Vì vậy không dùng `iterator`, `for-each`, `toString` hoặc `toArray` để suy rằng mọi phần tử đang xuất hiện theo thứ tự ưu tiên. PriorityBlockingQueue không hứa thứ tự duyệt đó.

Nếu chỉ muốn xem hoặc xuất dữ liệu có thứ tự:

1. Lấy một bản dữ liệu riêng theo API phù hợp.
2. Sắp bản đó bằng đúng comparator.
3. Hiểu rằng các cập nhật sau có thể khiến bản xem khác nguồn hiện tại.

Nếu muốn **lấy ra để xử lý**, dùng `take`/`poll` theo hợp đồng hoặc `drainTo` để lấy một nhóm theo thứ tự ưu tiên. `drainTo` làm thay đổi queue, không phải phép xem không tác động.

PriorityQueue thông thường cũng có sự khác nhau giữa thứ tự đầu heap và thứ tự iterator, nhưng nó không cung cấp đồng bộ cho các cập nhật cạnh tranh như PriorityBlockingQueue. [Java 17: PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

Không thay PriorityBlockingQueue bằng PriorityQueue rồi chỉ dựa vào việc chương trình vẫn “lấy đúng số nhỏ nhất” trong một phép thử một luồng.

## 6. Giới hạn thực tế đến từ bộ nhớ và công việc chưa hoàn tất

Queue có thể mở rộng, nhưng mỗi phần tử vẫn giữ dữ liệu:

- Tham chiếu trong cấu trúc lưu trữ.
- Payload mà phần tử dẫn tới.
- Dữ liệu gián tiếp như mảng, chuỗi, ngữ cảnh yêu cầu hoặc đối tượng tác vụ.
- Công việc đang được tạo ở producer trước khi tiếp nhận.
- Công việc đã lấy ra nhưng đang chạy.

Nếu tốc độ đưa vào vượt tốc độ xử lý đủ lâu, số việc chờ có thể tăng đến khi độ trễ hoặc bộ nhớ không còn chấp nhận được.

Ưu tiên chỉ chọn thứ tự phục vụ trong phần đã nhận. Nó không làm tổng khối lượng xử lý giảm đi và không tự ngăn việc ít khẩn tích lũy.

### 6.1. Số phần tử không bằng số byte

Một giới hạn `N` phần tử cũng chưa trực tiếp giới hạn byte nếu kích thước payload chênh lệch lớn. Cần xác định ngân sách phù hợp với dữ liệu.

Có thể giới hạn số việc, tổng trọng lượng dữ liệu ước tính, số phiên đang hoạt động hoặc một tổ hợp điều kiện. Cách đếm phải gắn với tài nguyên cần bảo vệ.

### 6.2. OutOfMemoryError không phải chính sách tiếp nhận

Không đợi đến lúc cấp phát thất bại để coi đó là tín hiệu “queue đầy” thông thường. Khi ấy nhiều phần khác của tiến trình cũng có thể không còn tài nguyên để hoạt động hoặc phản hồi.

Hãy đặt giới hạn chủ động theo ngân sách bộ nhớ, độ trễ và khả năng xử lý. Ví dụ trong bài chỉ thêm một lượng nhỏ để chứng minh initialCapacity không phải giới hạn; nó không thử làm cạn bộ nhớ.

### 6.3. Chọn thời điểm giải phóng ngân sách

Có ít nhất hai phạm vi khác nhau:

- **Giới hạn số việc chờ:** trả ngân sách khi lấy phần tử khỏi queue.
- **Giới hạn số việc đã nhận nhưng chưa xong:** giữ ngân sách qua cả xử lý, chỉ trả khi hoàn tất hoặc hủy theo giao thức.

Một semaphore có thể tham gia cả hai mô hình, nhưng vị trí `release` khác nhau. Trả lúc `take` rồi tuyên bố đã giới hạn toàn bộ việc chưa hoàn tất là sai phạm vi.

## 7. Một ví dụ giới hạn tiếp nhận bằng Semaphore

Ý tưởng là lấy một giấy phép trước khi đưa vào PriorityBlockingQueue và trả lại khi phần tử đã bị lấy ra.

`Semaphore` quản lý số giấy phép bằng các thao tác lấy/trả; nó tách việc quản lý ngân sách khỏi cách queue sắp thứ tự phần tử. [Java 17: Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)

Quy tắc của ví dụ:

~~~text
Trước khi nhận:
    phải lấy được một giấy phép

Nếu thêm không thành công:
    trả lại giấy phép vừa giữ

Khi poll/take thực sự lấy một phần tử:
    trả lại đúng một giấy phép

Nếu poll thấy rỗng:
    không trả giấy phép
~~~

Phần tử vừa được một producer giữ giấy phép nhưng chưa công bố vào queue cũng chiếm ngân sách. Nhờ vậy hai producer không cùng tiêu thụ một chỗ trống chỉ vì cùng thấy `size` còn nhỏ.

### 7.1. Giữ queue bên trong kín

Không để bên ngoài lấy trực tiếp queue rồi gọi `offer` mà bỏ qua việc lấy giấy phép. Không cho phép một đường `clear`/`remove`/`drainTo` tự ý lấy phần tử mà quên trả ngân sách.

Ví dụ chỉ cung cấp một số phương thức đã được nối với giấy phép. Nó **không triển khai toàn bộ giao diện BlockingQueue**, nên không phải lớp thay thế dùng được ở mọi nơi đòi một BlockingQueue.

Nếu mở rộng API, mỗi đường thêm, lấy, hủy và xử lý lỗi đều phải duy trì cùng bất biến.

### 7.2. Không đợi trong lúc giữ khóa mà bên lấy cần

Semaphore có thể đợi giấy phép. Việc đợi không được giữ một khóa ngoài đang ngăn consumer lấy phần tử/trả giấy phép.

Giấy phép là ngân sách, không phải một lối tắt thay thế mọi đồng bộ của cấu trúc dữ liệu. Queue vẫn dùng hợp đồng đồng thời của chính nó.

## 8. Chương trình chạy độc lập

Lưu tệp `PriorityCapacityDemo.java`. Chương trình dùng API Java 17, đã được biên dịch với `javac --release 17` và chạy trên OpenJDK Zulu 24.0.2. Không coi đây là bằng chứng đã chạy trên JVM 17.

Phần `PriorityBuffer` là ví dụ giới hạn **phần đang chờ cùng các chỗ đã được đặt nhưng chưa công bố**, không giới hạn mọi công việc đang thực thi. Nó dùng comparator rõ ràng và không lộ queue nền.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.PriorityBlockingQueue;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class PriorityCapacityDemo {
    record Work(String name, int priority, long sequence) {}

    static final Comparator<Work> ORDER =
            Comparator.comparingInt(Work::priority)
                      .thenComparingLong(Work::sequence);

    static final class PriorityBuffer<E> {
        private final PriorityBlockingQueue<E> queue;
        private final Semaphore free;

        PriorityBuffer(int capacity, Comparator<? super E> comparator) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            queue = new PriorityBlockingQueue<>(Math.min(capacity, 11),
                                                Objects.requireNonNull(comparator));
            free = new Semaphore(capacity);
        }

        private void publishReserved(E item) {
            boolean inserted = false;
            try {
                inserted = queue.offer(item);
                if (!inserted) {
                    throw new AssertionError("Unexpected priority queue rejection");
                }
            } finally {
                if (!inserted) {
                    free.release();
                }
            }
        }

        boolean offer(E item) {
            Objects.requireNonNull(item);
            if (!free.tryAcquire()) {
                return false;
            }
            publishReserved(item);
            return true;
        }

        boolean offer(E item, long timeout, TimeUnit unit)
                throws InterruptedException {
            Objects.requireNonNull(item);
            if (!free.tryAcquire(timeout, unit)) {
                return false;
            }
            publishReserved(item);
            return true;
        }

        void put(E item) throws InterruptedException {
            Objects.requireNonNull(item);
            free.acquire();
            publishReserved(item);
        }

        E poll() {
            E item = queue.poll();
            if (item != null) {
                free.release();
            }
            return item;
        }

        E take() throws InterruptedException {
            E item = queue.take();
            free.release();
            return item;
        }
    }

    static List<String> names(List<Work> work) {
        return work.stream().map(Work::name).toList();
    }

    static void await(CountDownLatch event) throws InterruptedException {
        if (!event.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Event timed out");
        }
    }

    static void finish(Thread thread, AtomicReference<Throwable> problem)
            throws InterruptedException {
        thread.join(5000);
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Thread timed out");
        }
        if (problem.get() != null) {
            throw new AssertionError("Thread failed", problem.get());
        }
    }

    public static void main(String[] args) throws Exception {
        PriorityBlockingQueue<Integer> raw = new PriorityBlockingQueue<>(1);
        raw.offer(5);
        raw.offer(2);
        raw.offer(8);
        raw.offer(1);
        raw.put(3);
        System.out.println("timed-offer-zero = "
                + raw.offer(4, 0, TimeUnit.NANOSECONDS));
        System.out.println("initial-one-current-size = " + raw.size());
        System.out.println("raw-remainingCapacity = " + raw.remainingCapacity());
        List<Integer> rawOrder = new ArrayList<>();
        raw.drainTo(rawOrder);
        System.out.println("raw-priority-order = " + rawOrder);

        PriorityBlockingQueue<Work> scheduled = new PriorityBlockingQueue<>(1, ORDER);
        scheduled.add(new Work("low", 5, 3));
        scheduled.add(new Work("same-later", 1, 2));
        scheduled.add(new Work("same-earlier", 1, 1));
        List<Work> display = new ArrayList<>(scheduled);
        display.sort(ORDER);
        System.out.println("sorted-display = " + names(display));
        List<Work> drained = new ArrayList<>();
        scheduled.drainTo(drained);
        System.out.println("drained-order = " + names(drained));
        System.out.println("scheduled-size-after-drain = " + scheduled.size());

        PriorityBlockingQueue<String> empty = new PriorityBlockingQueue<>();
        CountDownLatch beforeTake = new CountDownLatch(1);
        AtomicReference<String> received = new AtomicReference<>();
        AtomicReference<Throwable> takeProblem = new AtomicReference<>();
        Thread taker = new Thread(() -> {
            try {
                beforeTake.countDown();
                received.set(empty.take());
            } catch (Throwable ex) {
                takeProblem.set(ex);
            }
        }, "empty-taker");
        taker.setDaemon(true);
        taker.start();
        await(beforeTake);
        System.out.println("take-received-before-offer = " + (received.get() != null));
        empty.offer("ready");
        finish(taker, takeProblem);
        System.out.println("take-received-after-offer = " + received.get());

        PriorityBuffer<Work> bounded = new PriorityBuffer<>(2, ORDER);
        System.out.println("bounded-offer-low = "
                + bounded.offer(new Work("low", 5, 1)));
        System.out.println("bounded-offer-high = "
                + bounded.offer(new Work("high", 1, 2)));
        System.out.println("bounded-offer-urgent-full = "
                + bounded.offer(new Work("urgent", 0, 3)));
        System.out.println("bounded-timed-offer-full = "
                + bounded.offer(new Work("later", 2, 4), 0, TimeUnit.NANOSECONDS));
        System.out.println("bounded-first = " + bounded.take().name());
        System.out.println("bounded-offer-urgent-after-space = "
                + bounded.offer(new Work("urgent", 0, 3)));
        System.out.println("bounded-next = " + bounded.take().name());
        System.out.println("bounded-last = " + bounded.take().name());
        System.out.println("bounded-poll-empty = " + bounded.poll());

        PriorityBuffer<Integer> waiting = new PriorityBuffer<>(1, Integer::compare);
        waiting.put(9);
        CountDownLatch beforePut = new CountDownLatch(1);
        CountDownLatch afterPut = new CountDownLatch(1);
        AtomicReference<Throwable> putProblem = new AtomicReference<>();
        Thread putter = new Thread(() -> {
            try {
                beforePut.countDown();
                waiting.put(1);
                afterPut.countDown();
            } catch (Throwable ex) {
                putProblem.set(ex);
            }
        }, "bounded-putter");
        putter.setDaemon(true);
        putter.start();
        await(beforePut);
        System.out.println("bounded-put-returned-before-space = "
                + (afterPut.getCount() == 0));
        System.out.println("bounded-existing-item = " + waiting.take());
        await(afterPut);
        finish(putter, putProblem);
        System.out.println("bounded-new-item = " + waiting.take());

        PriorityBuffer<Integer> cancelled = new PriorityBuffer<>(1, Integer::compare);
        cancelled.put(7);
        CountDownLatch attempting = new CountDownLatch(1);
        AtomicBoolean wasInterrupted = new AtomicBoolean();
        AtomicReference<Throwable> cancelProblem = new AtomicReference<>();
        Thread cancelledPutter = new Thread(() -> {
            try {
                attempting.countDown();
                cancelled.put(1);
            } catch (InterruptedException ex) {
                wasInterrupted.set(true);
                Thread.currentThread().interrupt();
            } catch (Throwable ex) {
                cancelProblem.set(ex);
            }
        }, "cancelled-putter");
        cancelledPutter.setDaemon(true);
        cancelledPutter.start();
        await(attempting);
        cancelledPutter.interrupt();
        finish(cancelledPutter, cancelProblem);
        System.out.println("bounded-cancelled = " + wasInterrupted.get());
        System.out.println("bounded-offer-while-held = " + cancelled.offer(2));
        System.out.println("bounded-held-item = " + cancelled.poll());
        System.out.println("bounded-offer-after-take = " + cancelled.offer(2));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 PriorityCapacityDemo.java
java PriorityCapacityDemo
~~~

Stdout đã kiểm chứng:

~~~text
timed-offer-zero = true
initial-one-current-size = 6
raw-remainingCapacity = 2147483647
raw-priority-order = [1, 2, 3, 4, 5, 8]
sorted-display = [same-earlier, same-later, low]
drained-order = [same-earlier, same-later, low]
scheduled-size-after-drain = 0
take-received-before-offer = false
take-received-after-offer = ready
bounded-offer-low = true
bounded-offer-high = true
bounded-offer-urgent-full = false
bounded-timed-offer-full = false
bounded-first = high
bounded-offer-urgent-after-space = true
bounded-next = urgent
bounded-last = low
bounded-poll-empty = null
bounded-put-returned-before-space = false
bounded-existing-item = 9
bounded-new-item = 1
bounded-cancelled = true
bounded-offer-while-held = false
bounded-held-item = 7
bounded-offer-after-take = true
~~~

Các latch đặt thứ tự của phép thử, không dùng `Thread.sleep` để suy đoán trạng thái chờ. Các thời hạn năm giây chỉ giúp phép kiểm chứng báo lỗi thay vì đợi mãi.

## 9. Đọc kết quả

### 9.1. Dung lượng khởi tạo 1 vẫn chứa 6 phần tử

~~~text
timed-offer-zero = true
initial-one-current-size = 6
raw-remainingCapacity = 2147483647
~~~

Queue nhận bốn lần offer, một lần put và một timed offer với thời hạn `0`. Không có mức tối đa `1` do constructor thiết lập. Thời hạn `0` của offer không từ chối vì một “capacity 1” tưởng tượng.

Dòng `remainingCapacity` là `Integer.MAX_VALUE` theo hợp đồng, không phải kết quả đo bộ nhớ trống của máy.

### 9.2. Thứ tự đầu ra đến từ thao tác lấy

~~~text
raw-priority-order = [1, 2, 3, 4, 5, 8]
~~~

`drainTo` lấy các phần tử ra theo ưu tiên khi không có bên khác cập nhật trong giai đoạn kiểm chứng.

Với các `Work`, comparator dùng priority trước, sequence sau:

~~~text
sorted-display = [same-earlier, same-later, low]
drained-order = [same-earlier, same-later, low]
~~~

Bản xem được sắp xếp riêng; bản drain được lấy ra từ queue. Dữ liệu giống nhau trong thí nghiệm yên không có nghĩa hai thao tác có cùng tác dụng. Sau drain, queue rỗng.

### 9.3. Phần Blocking thể hiện ở take khi rỗng

~~~text
take-received-before-offer = false
take-received-after-offer = ready
~~~

Latch báo luồng nhận đã tới đoạn gọi `take`. Khi chưa có phần tử và chưa có bên offer, nó chưa thể nhận được gì. Sau khi `ready` được thêm, lần take hoàn tất.

Không cần dùng Thread state để chứng minh một đợt chờ nội bộ cụ thể; điều cần kiểm chứng là phần tử chỉ được trả sau khi có dữ liệu.

### 9.4. Giới hạn ở wrapper khác với giới hạn của queue nền

~~~text
bounded-offer-low = true
bounded-offer-high = true
bounded-offer-urgent-full = false
bounded-timed-offer-full = false
~~~

Wrapper có hai giấy phép. Hai phần tử đã chiếm ngân sách nên yêu cầu mới bị từ chối hoặc không lấy được giấy phép trong thời hạn `0`.

Đây là `false` do quy tắc tiếp nhận của wrapper, không phải do PriorityBlockingQueue nền tự đạt initialCapacity.

### 9.5. Việc cực khẩn vẫn có thể bị từ chối khi chưa được nhận

`urgent` có priority `0`, cao hơn theo quy ước của ví dụ, nhưng vẫn bị từ chối khi hai chỗ đều đã được dùng.

Sau khi lấy `high` ra, giấy phép được trả; `urgent` được nhận và trở thành phần tử tiếp theo:

~~~text
bounded-first = high
bounded-offer-urgent-after-space = true
bounded-next = urgent
bounded-last = low
~~~

Điều này tách **chính sách được vào hệ thống** với **chính sách lấy ra**. Ưu tiên không tự cho phép một yêu cầu vượt ngân sách hoặc đẩy một phần tử cũ ra ngoài.

### 9.6. put của wrapper có thể chờ, put của PBQ nền thì không chờ sức chứa

Wrapper sức chứa một đã có `9`. Lần put `1` chưa hoàn tất trước khi có chỗ. Consumer vẫn lấy `9` vì `1` chưa được tiếp nhận vào queue:

~~~text
bounded-put-returned-before-space = false
bounded-existing-item = 9
bounded-new-item = 1
~~~

Không được suy rằng producer có một việc khẩn đang chờ giấy phép thì việc ấy đã tham gia thứ tự heap. Chỉ các phần tử đã được nhận mới được queue chọn.

### 9.7. Hủy trước khi có giấy phép không trả thừa ngân sách

Trong phần hủy, một chỗ đang bị `7` chiếm. Producer chờ giấy phép cho `1` và bị ngắt.

~~~text
bounded-cancelled = true
bounded-offer-while-held = false
bounded-held-item = 7
bounded-offer-after-take = true
~~~

Lần chờ bị hủy chưa giữ được giấy phép nên không được gọi release như thể đã lấy được. Khi `7` thực sự bị lấy ra, đúng một giấy phép được trả và lần offer tiếp theo thành công.

## 10. Lập luận về bất biến của ví dụ

Với capacity `C`, mỗi phần tử nằm trong queue phải được bảo chứng bởi một giấy phép đã lấy và chưa trả. Một producer chưa lấy được giấy phép không thể gọi đường công bố.

Các giấy phép đang dùng có thể tương ứng với:

- Phần tử đã công bố và còn trong queue.
- Chỗ producer đã giữ nhưng chưa thêm xong.
- Phần tử vừa bị lấy khỏi queue nhưng thao tác trả giấy phép chưa thực hiện xong.

Do đó số phần tử thực trong queue không vượt `C` nếu mọi đường truy cập đều đi qua wrapper và comparator/phần tử tuân thủ hợp đồng.

### 10.1. Nhánh thêm thất bại

Sau khi đã lấy giấy phép, nếu đường thêm không hoàn tất thành công, `finally` trả lại giấy phép. Điều này tránh giữ vĩnh viễn một đơn vị ngân sách cho việc chưa được nhận.

Comparator trong ví dụ là phép so sánh ngắn, ổn định trên các thành phần bất biến. Không xây giao thức dựa vào comparator có tác dụng bên ngoài, thay đổi ngẫu nhiên hoặc ném lỗi để điều khiển tiếp nhận.

### 10.2. Nhánh lấy rỗng

`poll` chỉ release khi thực sự trả một phần tử khác `null`. Nếu mỗi lần poll rỗng cũng release, giấy phép có thể tăng vượt capacity và wrapper mất giới hạn.

Đây là lỗi dễ xuất hiện khi dùng `finally` ở sai phạm vi: “phương thức lấy đã được gọi” khác với “một phần tử đã bị lấy”.

### 10.3. Nhánh chờ bị ngắt

`free.acquire` ném `InterruptedException` trước khi có giấy phép thì không cần trả giấy phép. Nếu đã giữ giấy phép và thêm thành công, phần tử đi theo vòng đời tiếp nhận bình thường.

Ví dụ hủy được đặt trong giai đoạn không có giấy phép, nên kết quả xác định. Nó không tuyên bố rằng một lệnh interrupt ở thời điểm bất kỳ luôn thu hồi được một phần tử đã được nhận. Hủy tác vụ và hoàn tác tiếp nhận cần một giao thức riêng.

### 10.4. Timed offer chỉ đặt ngân sách chờ giấy phép

Trong wrapper, tham số thời gian được áp dụng cho `Semaphore.tryAcquire`. Sau khi có giấy phép, đường thêm vẫn cần thực hiện thao tác queue và so sánh.

Không coi đây là một cam kết thời gian thực cho toàn bộ phương thức. Nếu API sản phẩm cần thời hạn tổng nghiêm ngặt, cần định nghĩa phạm vi và xử lý các bước còn lại tương ứng.

### 10.5. Mở rộng API đòi mở rộng chứng minh

Nếu thêm `remove`, `clear`, `drainTo` hoặc một iterator có thể xóa, phải trả ngân sách đúng số phần tử thực sự bị lấy/gỡ và xử lý lỗi nhất quán.

Không đưa trực tiếp queue nền cho một executor hoặc một tiện ích khác rồi mong nó biết trả giấy phép. Lớp minh họa cố ý chỉ có các phương thức đã thể hiện đầy đủ giao thức; mọi tích hợp rộng hơn cần một thiết kế hoàn chỉnh cho giao diện đó.

## 11. Giới hạn tiếp nhận không giải quyết mọi vấn đề lập lịch

### 11.1. Khi đầy toàn việc ít khẩn

Một việc khẩn đến muộn có thể bị từ chối như ví dụ. Nếu yêu cầu là luôn có chỗ cho nhóm khẩn, cần một chính sách khác: dành ngân sách theo lớp, quản lý nhiều hàng đợi hoặc chọn thay thế công việc theo quy tắc rõ ràng.

Không chỉ thêm một lệnh `remove` tùy ý trước offer rồi xem đó là một bộ đệm ưu tiên có giới hạn đúng. Quyết định gỡ ai, nhận ai, hoàn trả ngân sách và báo việc bị loại phải được phối hợp.

### 11.2. Giới hạn số chờ khác với giới hạn chưa xong

Wrapper trả giấy phép khi take/poll lấy phần tử. Nếu có nhiều consumer, phần đang chạy ở ngoài queue vẫn giữ tài nguyên.

Muốn giới hạn tổng việc đã nhận nhưng chưa hoàn tất, cần giữ ngân sách qua quá trình xử lý và có cách xác nhận hoàn tất/hủy đúng một lần. Khi ấy phải xét cả consumer lỗi, thử lại và khôi phục. Đó là một giao thức khác với lớp đang minh họa.

### 11.3. Chờ giấy phép không làm producer khác tự ngừng tạo payload

Một producer có thể đã xây một đối tượng rất lớn rồi mới chờ put. Nếu có rất nhiều producer như vậy, lượng dữ liệu đứng ngoài queue vẫn lớn.

Cần đặt ranh giới ngân sách phù hợp với nơi tài nguyên được tạo và truyền tín hiệu quá tải về nguồn thật. Không chỉ đếm nội dung heap của queue rồi bỏ các đối tượng chờ bên ngoài.

### 11.4. Poison object trong priority queue cần đặc biệt thận trọng

Một dấu dừng cũng chịu comparator. Nếu nó được xem là khẩn nhất, consumer có thể lấy dấu dừng trước các việc thường còn chờ. Nếu nó ít khẩn nhất, các đợt việc mới có thể khiến nó chờ rất lâu.

PriorityBlockingQueue không có close nội tại. Giao thức ngừng nhận, xử lý nốt và dừng consumer cần được thiết kế cùng thứ tự ưu tiên, không sao chép nguyên mẫu dấu dừng của FIFO queue mà bỏ qua comparator. [Java 17: BlockingQueue và shutdown](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

## 12. Nếu dùng với ThreadPoolExecutor

`ThreadPoolExecutor` thường thử đưa tác vụ vào work queue sau khi đã đạt số luồng lõi. Nếu queue chấp nhận, tác vụ tiếp tục xếp hàng; việc mở thêm đến số luồng tối đa gắn với trường hợp không đưa được vào queue theo thuật toán tiếp nhận. [Java 17: ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

Vì PriorityBlockingQueue thông thường không trả `false` do đầy, chọn nó không tự khiến pool mở rộng theo backlog đến mức tối đa hoặc kích hoạt từ chối theo một capacity nhỏ do constructor đặt ra.

Ngoài ra, mọi tác vụ thực sự được đặt trong priority queue phải so sánh được bằng quy tắc của queue. Các tầng bọc tác vụ có thể thay đổi kiểu đối tượng được đưa vào, nên thiết kế ưu tiên của executor phải kiểm tra đường gửi cụ thể.

Ví dụ `PriorityBuffer` ở trên không triển khai BlockingQueue và không được trình bày như một work queue có thể truyền thẳng cho constructor executor. Nếu cần tích hợp, phải có một giao diện hoàn chỉnh duy trì giới hạn trên tất cả đường mà executor sử dụng.

Mục đích của ví dụ là chứng minh cách tách **ngân sách tiếp nhận** khỏi **thứ tự heap**, không giả định các thành phần ngoài đã biết giao thức giấy phép.

## 13. Quan sát và kiểm thử giới hạn thực tế

Theo dõi những số liệu trả lời đúng câu hỏi:

- Số phần tử đang chờ và thời gian chờ theo từng nhóm ưu tiên.
- Tốc độ được nhận, bị từ chối, bị hủy và hoàn tất.
- Số producer đang đợi ngân sách.
- Số công việc đang chạy ngoài queue.
- Dung lượng payload được giữ và độ trễ xử lý.
- Khả năng các việc ít khẩn bị chờ kéo dài.

Phép thử cần kiểm tra bất biến trực tiếp:

1. Constructor capacity ban đầu không bị nhầm thành giới hạn tối đa.
2. Wrapper từ chối/chờ đúng lúc hết giấy phép.
3. Poll rỗng và hủy trước khi lấy giấy phép không làm tăng ngân sách.
4. Lấy phần tử thành công trả đúng một giấy phép.
5. Thứ tự lấy chỉ được kiểm tra trên tập phần tử đã thực sự được nhận.
6. Khi cần một thứ tự phụ, nó đã được đưa vào comparator và được mô tả rõ.
7. Nơi xử lý vẫn có thể tiến triển trong khi producer đang chờ.

Không kiểm chứng bằng cách cố làm cạn heap hoặc dự đoán một thời gian ngủ sẽ buộc các luồng chạy theo ý muốn. Các latch trong chương trình tạo các trạng thái kiểm tra rõ, còn việc tăng từ initial capacity `1` lên `6` đã đủ chứng minh điểm hợp đồng cần học.

## 14. Bài tập tự kiểm tra

### Bài 1 — Số 100 trong constructor

`new PriorityBlockingQueue<>(100)` đã có `100` phần tử. Lần offer kế tiếp có buộc phải trả `false` không?

**Đáp án:** Không. `100` là initial capacity, không phải giới hạn tiếp nhận. Lớp có thể tăng lưu trữ và không trả `false` vì một giới hạn sức chứa nội tại như vậy.

### Bài 2 — Thời hạn offer

Vì sao `offer(item, 1, SECONDS)` trên PriorityBlockingQueue không tự tạo backpressure khi backlog tăng?

**Đáp án:** Lớp không chờ chỗ trống vì không có giới hạn capacity theo chính sách; tham số thời gian của dạng offer đó không tạo một ngưỡng tiếp nhận.

### Bài 3 — Integer.MAX_VALUE

`remainingCapacity` trả `Integer.MAX_VALUE`. Có thể xem đó là số payload lớn còn chắc chắn chứa được trên heap không?

**Đáp án:** Không. Đó là giá trị theo hợp đồng queue không bị giới hạn capacity, không phải phép đo bộ nhớ và không phải một lời hứa cấp phát.

### Bài 4 — Duyệt có thứ tự?

Một vòng for-each in dữ liệu không tăng dần, nhưng các lần poll cho phần tử đúng ưu tiên. Queue có vi phạm hợp đồng không?

**Đáp án:** Không. Iterator không được hứa duyệt theo thứ tự ưu tiên. Cần sắp bản xem riêng hoặc lấy ra bằng API của queue tùy mục đích.

### Bài 5 — Việc khẩn đến khi đầy

Wrapper đang chứa đủ các việc ít khẩn, một việc khẩn hơn được offer và bị từ chối. Có mâu thuẫn với ưu tiên không?

**Đáp án:** Không. Quy tắc tiếp nhận và quy tắc lấy ra là hai tầng khác nhau. Muốn dành chỗ cho việc khẩn phải có chính sách ngân sách/lập lịch bổ sung.

### Bài 6 — Poll rỗng

Một wrapper dùng semaphore release trong mọi lần poll, kể cả lúc trả null. Điều gì sai?

**Đáp án:** Nó trả giấy phép dù không giải phóng phần tử nào, làm ngân sách tăng và có thể vượt giới hạn. Chỉ release khi thật sự lấy được phần tử.

### Bài 7 — Đã take nhưng vẫn đang chạy

Wrapper trả giấy phép ngay sau take. Nó có giới hạn toàn bộ số việc chưa hoàn tất không?

**Đáp án:** Không. Nó giới hạn phần đang chờ cùng các chỗ đã được đặt. Công việc đã lấy ra vẫn đang dùng tài nguyên ngoài queue. Muốn giới hạn toàn bộ phải chọn điểm trả ngân sách khác và có giao thức hoàn tất.

### Bài 8 — Dấu dừng khẩn nhất

Một priority queue có nhiều việc thường. Đưa dấu dừng với ưu tiên cao nhất rồi cho consumer thoát khi lấy nó có bảo đảm xử lý hết backlog không?

**Đáp án:** Không. Dấu dừng có thể được lấy trước các việc đang chờ. Cần ngừng nhận và xác định rõ chính sách xử lý nốt/hủy trước khi dừng consumer.

PriorityBlockingQueue mang lại thứ tự chọn việc và khả năng chờ khi rỗng. Giới hạn tài nguyên thực tế phải được thiết kế ở ranh giới tiếp nhận, với ngân sách và điểm giải phóng rõ ràng; chỉ khi hai tầng ấy cùng phù hợp thì bộ lập lịch mới có hành vi quá tải có thể kiểm chứng.

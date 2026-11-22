# Chính sách công bằng và giới hạn bảo đảm lập lịch

Khi nhiều luồng cùng cần một khóa, không chỉ có câu hỏi “ai được vào vùng bảo vệ?”, mà còn có câu hỏi “luồng chờ lâu có tiếp tục bị luồng khác vượt qua không?”. Chính sách công bằng (fairness) của khóa giải quyết cách lựa chọn trong tình huống cạnh tranh.

Tuy nhiên, khóa không điều khiển toàn bộ bộ lập lịch, tốc độ chạy, I/O hoặc thời gian xử lý nghiệp vụ. Bật công bằng không tạo ra cam kết mọi luồng chạy theo vòng cố định hay hoàn tất trong một số mili giây.

Bài tập trung vào `ReentrantLock`, có liên hệ với `Condition` và khóa đọc/ghi khi cần phân biệt phạm vi bảo đảm. Các API và ngữ nghĩa được dùng vẫn áp dụng trong Java hiện đại.

## 1. Bật và kiểm tra chính sách

```java
ReentrantLock defaultLock = new ReentrantLock();
ReentrantLock nonFairLock = new ReentrantLock(false);
ReentrantLock fairLock = new ReentrantLock(true);
```

Đây là đoạn khai báo minh họa cần import `ReentrantLock`. Constructor không tham số chọn chế độ không công bằng. `isFair()` trả cấu hình chính sách, không đo xem mọi lượt cấp khóa trước đó có tình cờ đúng thứ tự hay không.

| Chế độ | Khi có cạnh tranh | Điều không được suy ra |
|---|---|---|
| Không công bằng, mặc định | Không cam kết thứ tự truy cập cụ thể | Không có nghĩa mọi lượt đều đảo thứ tự hoặc một luồng chắc chắn bị bỏ đói |
| Công bằng | Ưu tiên luồng đã chờ khóa lâu hơn theo chính sách của lớp | Không bảo đảm chia đều CPU, thời hạn hay thứ tự hoàn tất nghiệp vụ |

Tài liệu mô tả khóa công bằng giúp tránh bỏ đói trong việc cấp khóa và giảm dao động thời gian lấy khóa, đồng thời có thể làm giảm thông lượng. Những đặc tính này phải được hiểu cùng các giới hạn về lập lịch và cách gọi API. [ReentrantLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html).

## 2. “Chờ trước” khác với “start trước”

Không dùng thứ tự gọi `thread.start()` làm bằng chứng thứ tự vào hàng chờ của khóa. Sau `start`, JVM mới cho luồng cơ hội được bộ lập lịch chạy; luồng được khởi chạy sau có thể tới lời gọi lấy khóa trước.

```text
main gọi A.start()
main gọi B.start()
B được chạy trước và tới lock.lock()
A mới tới lock.lock() sau đó
```

Khóa công bằng không biết một thứ tự yêu cầu nghiệp vụ được tưởng tượng từ tên luồng hoặc thời điểm tạo đối tượng. Nó xử lý những yêu cầu lấy khóa thực sự đến cạnh tranh.

Cũng không dùng thứ tự dòng log nằm trước hoặc sau vùng khóa để suy ra chắc chắn thứ tự được cấp khóa. Bản thân việc in ra màn hình có thêm chi phí và sự xen kẽ.

## 3. Hai giới hạn quan trọng: tryLock và tái nhập

### 3.1. tryLock() không tham số có thể chen trước

`ReentrantLock.tryLock()` không tuân theo chính sách công bằng. Nếu khóa đang khả dụng tại lần thử, một luồng có thể lấy được nó dù đã có luồng khác đang chờ.

Đây là hành vi chen trước (barging) được API công bố, không phải lỗi tình cờ. Vì vậy, một vòng thử liên tục `tryLock()` trên một khóa công bằng có thể phá mục tiêu phân xử công bằng của ứng dụng.

Nếu muốn một phép thử không chờ mà vẫn tôn trọng chính sách fair của `ReentrantLock`, API chỉ ra dạng có thời gian bằng 0:

```java
// Đoạn minh họa trong hàm có chính sách xử lý InterruptedException.
if (fairLock.tryLock(0, TimeUnit.NANOSECONDS)) {
    try {
        useSharedState();
    } finally {
        fairLock.unlock();
    }
}
```

Khác với dạng không tham số, dạng có thời gian còn phát hiện ngắt. Không xem hai dạng là hoàn toàn tương đương. Nếu gọi `tryLock()` trước rồi mới gọi dạng có thời gian khi thất bại, bước thử đầu vẫn cho phép chen trước. [ReentrantLock.tryLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html#tryLock()).

### 3.2. Luồng đang sở hữu vẫn có thể tái nhập

Fairness không buộc chủ khóa phải đứng sau các luồng khác mỗi khi gọi lại `lock()`. Tính tái nhập cho phép chủ khóa lấy lại, tăng số lần giữ; các bên khác tiếp tục chờ tới khi số lần giữ giảm về 0.

Vì vậy, một chuỗi hàm gọi lồng nhau dùng cùng khóa vẫn hoạt động trong chế độ công bằng. Nó không biến thành một giao thức luân phiên bắt buộc giữa các luồng.

## 4. Chương trình chạy đầy đủ

Ví dụ dưới cố ý giữ khóa tại `main`, quan sát A đã xếp chờ rồi mới khởi chạy và quan sát B. Sau đó `main` minh họa tái nhập và cuối cùng trả khóa cho hai bên đang chờ.

Lưu thành `FairLockDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class FairLockDemo {
    static void awaitQueued(ReentrantLock lock, Thread thread)
            throws InterruptedException {
        long started = System.nanoTime();
        long budget = TimeUnit.SECONDS.toNanos(5);
        while (!lock.hasQueuedThread(thread)) {
            if (System.nanoTime() - started >= budget) {
                throw new IllegalStateException("Worker was not observed queued");
            }
            Thread.sleep(1);
        }
    }

    static Thread worker(
            ReentrantLock lock, List<String> order, String name) {
        return new Thread(() -> {
            lock.lock();
            try {
                order.add(name);
            } finally {
                lock.unlock();
            }
        }, name);
    }

    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock(true);
        List<String> order = new ArrayList<>();
        Thread first = worker(lock, order, "A");
        Thread second = worker(lock, order, "B");

        System.out.println("default fair: " + new ReentrantLock().isFair());
        System.out.println("configured fair: " + lock.isFair());

        lock.lock();
        try {
            first.start();
            awaitQueued(lock, first);
            second.start();
            awaitQueued(lock, second);

            // Reentrancy is allowed even when other threads are waiting.
            lock.lock();
            try {
                System.out.println("owner hold count: " + lock.getHoldCount());
            } finally {
                lock.unlock();
            }
        } finally {
            lock.unlock();
        }

        first.join();
        second.join();
        System.out.println("acquisition order: " + order);
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```shell
javac -encoding UTF-8 --release 17 FairLockDemo.java
java FairLockDemo
```

Stdout khi các bước quan sát xếp chờ hoàn tất trong ngân sách thí nghiệm:

```text
default fair: false
configured fair: true
owner hold count: 2
acquisition order: [A, B]
```

Nếu môi trường không cho một bên tiến triển để được quan sát trong năm giây, hàm kiểm tra ném ngoại lệ thay vì hứa kết quả trên. Đây là giới hạn phục vụ thí nghiệm, không phải một cam kết thời gian chờ của khóa công bằng.

### Điều ví dụ thật sự kiểm chứng

- A đã ở hàng chờ trước khi B được khởi chạy; cả hai không có chính sách tự hủy hoặc thời hạn lấy khóa.
- Khi `main` còn giữ khóa, không bên nào được thêm tên vào `order`.
- `main` lấy tái nhập làm số lần giữ là 2 dù A/B đang chờ, rồi mở đủ hai lần qua hai phạm vi `finally`.
- A và B cùng dùng `lock()`, không có lời gọi `tryLock()` không tham số chen trước.
- Mọi lần thêm vào `ArrayList` đều xảy ra trong cùng khóa; sau `join` cả hai bên, `main` mới đọc danh sách kết quả.

`hasQueuedThread` là API quan sát, thường phục vụ kiểm tra/giám sát. Ví dụ chỉ dùng nó dựng một tình huống nhỏ có kiểm soát, khi `main` đang giữ khóa và các bên không tự hủy. Không dùng kết quả quan sát đó như một quyết định cấp tài nguyên trong mã nghiệp vụ: trạng thái hàng chờ nói chung có thể đổi ngay sau khi đọc.

Nếu đổi `true` thành `false`, kết quả vẫn **có thể** là `[A, B]`. Một lượt chạy theo đúng thứ tự không chứng minh chế độ không công bằng có cam kết FIFO; không được viết một stdout cố định kiểu “non-fair luôn cho B trước”.

## 5. Công bằng của khóa khác với công bằng của lập lịch

Một luồng có thể phải trải qua nhiều giai đoạn:

```text
Đủ điều kiện được chạy
  → được bộ lập lịch cho chạy
  → gọi lấy khóa
  → chờ theo chính sách khóa
  → sở hữu khóa
  → thực hiện vùng bảo vệ
  → trả khóa
  → hoàn tất các bước ngoài khóa
```

Fairness chỉ là một phần của chuỗi. Nó không bảo đảm:

- Một luồng sẵn sàng luôn được cấp CPU trong khoảng thời gian giới hạn.
- Các luồng nhận cùng số lượt lấy khóa trong mọi khoảng thời gian.
- Mỗi vùng bảo vệ có cùng chi phí hoặc cùng độ dài.
- Tác vụ đã lấy khóa trước sẽ hoàn tất toàn bộ công việc trước.
- Loại bỏ bế tắc do thứ tự lấy nhiều khóa sai.
- Một luồng giữ khóa quá lâu hoặc chờ I/O trong vùng khóa sẽ tự bị thay thế.

Một luồng có thể lấy khóa nhiều lần liên tiếp nếu những luồng khác chưa được chạy tới bước cạnh tranh. Điều đó không tự chứng minh vi phạm fairness.

Nếu một bên không bao giờ được lập lịch hoặc chủ khóa không bao giờ trả khóa, chính sách công bằng không cung cấp tiến triển thần kỳ. Tránh nhầm bảo đảm chống bị vượt qua trong cấp khóa với một mức thời gian đáp ứng toàn hệ thống.

## 6. Condition có thêm một hàng chờ

Với `Condition` của `ReentrantLock`, một luồng gọi `await()` nhả khóa khi chờ và phải lấy lại khóa trước khi tiếp tục. Cần phân biệt:

1. Thứ tự chờ và được báo hiệu ở condition.
2. Thứ tự cạnh tranh để lấy lại khóa.
3. Thời điểm luồng thực sự được bộ lập lịch cho chạy.

Condition do `ReentrantLock.newCondition()` tạo báo hiệu các bên chờ theo FIFO; việc lấy lại khóa tuân chính sách lấy khóa của lớp. Chi tiết nằm tại [ReentrantLock.newCondition](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html#newCondition()).

`signal()` không chuyển ngay quyền sở hữu khóa sang luồng được báo hiệu. Bên báo hiệu còn giữ khóa cho tới khi nó mở; sau đó bên chờ mới có thể tiếp tục khi lấy lại được. Điều kiện nghiệp vụ cũng có thể đổi trong thời gian đó, nên phải kiểm tra trong vòng `while`, không dùng fairness để bỏ việc kiểm tra điều kiện.

Không suy rộng thứ tự FIFO của condition triển khai này thành quy tắc chung cho mọi `Condition` tùy biến. Hợp đồng của lớp cụ thể là căn cứ quyết định.

## 7. Đánh đổi giữa thông lượng và thời gian chờ

Khóa không công bằng có thể cho một luồng đang chạy tiếp tục lấy khóa đang rảnh mà không chờ bàn giao theo thứ tự. Điều đó có thể giảm chi phí chuyển giao và cải thiện thông lượng, nhưng làm thời gian chờ của các bên dao động hơn.

Khóa công bằng hướng tới thứ tự chờ ổn định hơn trong cạnh tranh. Đổi lại, nó có thể phải chờ cơ hội chạy của bên đứng trước và có thêm chi phí phân xử. Mức chênh lệch phụ thuộc tải; không có một tỷ lệ chậm cố định cho mọi chương trình.

Khi đánh giá, cần đo cả:

- Thông lượng hoàn tất công việc.
- Phân bố thời gian chờ lấy khóa, đặc biệt các trường hợp chờ lâu.
- Thời gian giữ khóa và công việc thực hiện trong vùng khóa.
- Số luồng cạnh tranh, độ lệch tải giữa chúng và các lần hủy/hết thời gian chờ.

Đừng chỉ đếm số lần mỗi luồng lấy khóa trong một thí nghiệm quá ngắn rồi gọi đó là bằng chứng về công bằng hoặc bỏ đói. Dữ liệu quan sát cần được giải thích cùng hợp đồng API và thiết kế thí nghiệm.

## 8. Khóa đọc/ghi có chính sách riêng

`ReentrantReadWriteLock(true)` cũng có chế độ công bằng, nhưng không thể mô tả đơn giản là từng luồng lấy độc quyền theo FIFO: nhiều bên đọc có thể cùng được cấp quyền theo nhóm, trong khi bên ghi cần độc quyền. Dạng `tryLock()` không tham số của read lock/write lock cũng có ngoại lệ đối với fairness. [ReentrantReadWriteLock — Acquisition order](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html).

Điều cần học là đọc đúng hợp đồng của loại khóa đang dùng. Không lấy một khẩu hiệu “fair = FIFO tuyệt đối” áp lên mọi khóa và mọi phương thức lấy khóa.

## 9. Tự kiểm tra

1. A được gọi `start()` trước B thì fair lock bắt buộc A lấy trước không? — Không; cần phân biệt thứ tự khởi chạy với thứ tự thực sự cạnh tranh.
2. `tryLock()` không tham số có giữ chính sách fair không? — Không.
3. Chủ khóa công bằng có tái nhập được khi bên khác đang chờ không? — Có.
4. Bật fair có bảo đảm mỗi yêu cầu được phục vụ trong 100 ms không? — Không.
5. `signal()` có đồng nghĩa bên chờ lập tức sở hữu khóa không? — Không; nó phải lấy lại khóa theo giao thức.

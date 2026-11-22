# So sánh phương án bảo vệ dữ liệu bằng Lock, Atomic và collection đồng thời

## 1. Chọn phạm vi cần nguyên tử trước khi chọn công cụ

Một lỗi khi viết chương trình nhiều luồng là chọn ngay “dùng Atomic cho nhanh” hoặc “đổi HashMap thành ConcurrentHashMap” mà chưa xác định dữ liệu nào phải nhất quán cùng nhau.

Câu hỏi đầu tiên là: **điều kiện nào phải luôn đúng và thao tác nào phải được xem như một bước không thể chia nhỏ?**

Ví dụ đặt chỗ có sức chứa ban đầu `capacity`:

```text
remaining >= 0
booked >= 0
remaining + booked == capacity
```

Mỗi yêu cầu thành công cần giảm `remaining` và tăng `booked` đúng một lần. Khi hết chỗ, yêu cầu phải bị từ chối mà không thay đổi trạng thái.

Ba cách tiếp cận:

- **Lock**: bảo vệ một vùng thao tác trên trạng thái dùng chung.
- **Atomic**: cập nhật nguyên tử một biến; có thể là tham chiếu tới toàn bộ trạng thái bất biến.
- **Collection đồng thời**: dùng thao tác có hợp đồng đồng thời của cấu trúc dữ liệu, chẳng hạn lấy một phần tử bằng `poll()`.

Chúng không phải ba từ thay thế cho cùng một bảo đảm. Cách biểu diễn dữ liệu và phạm vi thao tác quyết định phương án nào phù hợp.

## 2. Khả kiến bộ nhớ và tính nguyên tử là hai yêu cầu liên quan nhưng khác nhau

Một luồng nhìn thấy giá trị mới chưa có nghĩa toàn bộ chuỗi đọc–kiểm tra–cập nhật là nguyên tử.

Ví dụ sai về ý tưởng, dù từng biến là AtomicInteger:

```java
if (remaining.get() > 0) {
    remaining.decrementAndGet();
    booked.incrementAndGet();
}
```

Đây là đoạn minh họa lỗi, không phải phiên bản đặt chỗ hợp lệ. Hai luồng có thể cùng thấy `remaining == 1`, rồi cùng giảm, khiến số chỗ còn lại âm.

Ngay cả khi sửa phép giảm để không âm, hai biến Atomic riêng vẫn chưa tự tạo thành một giao dịch cho cặp `remaining/booked`. Một người đọc có thể quan sát giữa hai cập nhật và thấy tổng không đúng.

Gói `java.util.concurrent.atomic` cung cấp thao tác nguyên tử trên các biến tương ứng; nó không tự gộp một chuỗi phương thức trên nhiều đối tượng thành một bước. Xem [java.util.concurrent.atomic](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/package-summary.html).

Tương tự, `volatile` không biến `count++` hay `if (...) then update` thành thao tác nguyên tử. Cần bảo vệ đúng toàn bộ điều kiện và thay đổi liên quan.

## 3. Phương án Lock: một vùng tới hạn cho điều kiện và cập nhật

Với `ReentrantLock`, đoạn kiểm tra và thay đổi cả hai trường nằm trong cùng vùng được khóa.

```text
lock
    ↓
kiểm tra remaining
    ↓
nếu có chỗ: remaining--, booked++
    ↓
unlock trong finally
```

Ưu điểm:

- Dễ biểu diễn điều kiện liên quan nhiều trường.
- Có thể trả một snapshot nhất quán khi đọc dưới cùng lock.
- Mã cập nhật phức tạp thường dễ hiểu hơn một vòng CAS lớn.
- Có các khả năng như khóa có thời hạn, khóa có thể ngắt hoặc Condition khi thực sự cần.

Đổi lại, các luồng có thể phải chờ lock, và giữ lock quá lâu làm tăng tranh chấp. Không làm I/O chậm hoặc gọi mã bên ngoài tùy ý trong vùng tới hạn.

Mẫu `lock.lock(); try { ... } finally { lock.unlock(); }` giúp thả khóa cả khi thân xử lý ném lỗi. Mọi đường truy cập trạng thái được bảo vệ phải tuân thủ cùng quy tắc; một getter đọc không khóa có thể phá hợp đồng. Xem [ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html).

Một lock “fair” cũng không làm lịch chạy luồng trở nên hoàn toàn công bằng và không tự tối ưu hiệu năng. Cần chọn theo yêu cầu chờ/tranh chấp thực tế.

## 4. Phương án Atomic: gộp trạng thái vào một tham chiếu bất biến

Nếu cặp số là một đối tượng bất biến:

```java
record State(int remaining, int booked) {}
```

thì có thể dùng `AtomicReference<State>` để thay toàn bộ phiên bản trạng thái cùng một lúc:

```text
đọc before
    ↓
kiểm tra điều kiện trên before
    ↓
tạo after từ before
    ↓
compareAndSet(before, after)
    ├── thành công → đặt chỗ thành công
    └── thất bại   → có luồng khác thay trạng thái; đọc lại và tính lại
```

Hai số chuyển phiên bản cùng nhau vì thao tác nguyên tử nằm trên **một tham chiếu**. Record ở đây chỉ chứa các trường primitive bất biến, nên không có phần trạng thái con bị sửa bên ngoài.

`compareAndSet` so sánh tham chiếu hiện tại với tham chiếu mong đợi theo identity, không gọi `State.equals()`. Vì vậy phải giữ đúng đối tượng `before` đã đọc, không tự tạo một State “bằng giá trị” rồi dùng nó làm expected reference. Xem [AtomicReference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html).

Những giới hạn:

- Khi tranh chấp, CAS có thể thất bại và cần thử lại.
- Mỗi phiên bản trạng thái mới có thể tạo cấp phát.
- Một luồng riêng lẻ không được bảo đảm sẽ thắng CAS ngay hoặc thắng theo thứ tự đến.
- Phần tính `after` cần không có tác động phụ không thể lặp lại.

Không gửi email, trừ tiền ngoài hệ thống hoặc ghi một sự kiện nghiệp vụ không idempotent bên trong phần tính có thể chạy lại. Kể cả sau khi CAS thành công, việc ghép trạng thái trong bộ nhớ với một tác động bên ngoài vẫn cần thiết kế nhất quán riêng.

Một `AtomicReference` trỏ tới một `ArrayList` có thể thay đổi không tự làm mọi sửa đổi trong list an toàn. Bất biến của đối tượng được tham chiếu là phần quan trọng của phương án này.

## 5. Phương án collection đồng thời: thay cách biểu diễn bài toán

Thay vì hai bộ đếm, có thể tạo một hàng đợi chứa sẵn các vé/chỗ còn trống. Đặt chỗ là lấy một vé:

```java
Integer ticket = tickets.poll();
boolean accepted = ticket != null;
```

`poll()` thực hiện việc lấy và loại phần tử theo hợp đồng của queue. Không cần viết `if (!isEmpty()) remove()` với hai thao tác tách rời.

`ConcurrentLinkedQueue` là hàng đợi an toàn cho truy cập đồng thời và không nhận phần tử null. `poll()` trả null khi không có phần tử để lấy. Tuy nhiên, `size()` phải duyệt và có thể không phản ánh một snapshot chính xác khi đang có cập nhật. Xem [ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html).

Trong mô hình này:

- Chỗ còn lại được biểu diễn bằng số vé chưa lấy.
- Mỗi lần lấy được một vé là một lần thành công.
- Sau khi tất cả luồng cập nhật đã kết thúc, có thể đếm chỗ còn lại để kiểm tra tổng.

Đó là thay đổi mô hình dữ liệu, không phải chỉ đổi cú pháp của hai bộ đếm.

Nếu yêu cầu là “lấy hai chỗ hoặc không lấy chỗ nào”, gọi `poll()` hai lần không tự tạo giao dịch hai phần tử. Nếu vừa lấy vé vừa ghi một đơn hàng vào cấu trúc khác, collection cũng không tự bảo vệ quan hệ giữa hai cấu trúc.

## 6. Chương trình so sánh tính đúng đắn của ba phương án

Bài thực hành có 8 luồng, mỗi luồng thử đặt 200 lần, tổng cộng 1.600 yêu cầu. Với sức chứa 1.000 và không hoàn trả chỗ, phải có đúng 1.000 lần thành công, còn lại 0.

Chương trình kiểm tra:

```text
accepted bằng min(capacity, 1.600)
remaining không âm
booked khớp tổng số lần worker báo thành công
remaining + booked bằng capacity
```

Nó không đo thời gian và không dùng kết quả để xếp hạng hiệu năng.

Lưu thành `ProtectionStrategiesDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.ReentrantLock;

public class ProtectionStrategiesDemo {
    record State(int remaining, int booked) {}

    interface Seats {
        boolean reserve();
        State snapshotAfterWorkers();
    }

    static final class LockedSeats implements Seats {
        private final ReentrantLock lock = new ReentrantLock();
        private int remaining;
        private int booked;

        LockedSeats(int capacity) {
            remaining = capacity;
        }

        public boolean reserve() {
            lock.lock();
            try {
                if (remaining == 0) {
                    return false;
                }
                remaining--;
                booked++;
                return true;
            } finally {
                lock.unlock();
            }
        }

        public State snapshotAfterWorkers() {
            lock.lock();
            try {
                return new State(remaining, booked);
            } finally {
                lock.unlock();
            }
        }
    }

    static final class AtomicSeats implements Seats {
        private final AtomicReference<State> state;

        AtomicSeats(int capacity) {
            state = new AtomicReference<>(new State(capacity, 0));
        }

        public boolean reserve() {
            while (true) {
                State before = state.get();
                if (before.remaining() == 0) {
                    return false;
                }
                State after = new State(
                        before.remaining() - 1, before.booked() + 1);
                if (state.compareAndSet(before, after)) {
                    return true;
                }
            }
        }

        public State snapshotAfterWorkers() {
            return state.get();
        }
    }

    static final class QueuedSeats implements Seats {
        private final int capacity;
        private final ConcurrentLinkedQueue<Integer> tickets =
                new ConcurrentLinkedQueue<>();

        QueuedSeats(int capacity) {
            this.capacity = capacity;
            for (int id = 0; id < capacity; id++) {
                tickets.add(id);
            }
        }

        public boolean reserve() {
            return tickets.poll() != null;
        }

        public State snapshotAfterWorkers() {
            // Chi goi khi tat ca worker da ket thuc.
            int remaining = tickets.size();
            return new State(remaining, capacity - remaining);
        }
    }

    static void check(String label, Seats seats, int capacity)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Integer>> results = new ArrayList<>();
        try {
            for (int worker = 0; worker < 8; worker++) {
                results.add(pool.submit(() -> {
                    start.await();
                    int accepted = 0;
                    for (int attempt = 0; attempt < 200; attempt++) {
                        if (seats.reserve()) {
                            accepted++;
                        }
                    }
                    return accepted;
                }));
            }
            start.countDown();

            int accepted = 0;
            for (Future<Integer> result : results) {
                accepted += result.get();
            }

            State snapshot = seats.snapshotAfterWorkers();
            if (accepted != Math.min(capacity, 8 * 200)
                    || snapshot.remaining() < 0
                    || snapshot.booked() != accepted
                    || snapshot.remaining() + snapshot.booked() != capacity) {
                throw new AssertionError("Invariant failed: " + label);
            }
            System.out.println(label + " accepted=" + accepted
                    + " remaining=" + snapshot.remaining());
        } finally {
            start.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not terminate");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        int capacity = args.length == 0 ? 1000 : Integer.parseInt(args[0]);
        if (capacity < 0) {
            throw new IllegalArgumentException("Negative capacity");
        }
        check("LOCK", new LockedSeats(capacity), capacity);
        check("ATOMIC", new AtomicSeats(capacity), capacity);
        check("QUEUE", new QueuedSeats(capacity), capacity);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 ProtectionStrategiesDemo.java
java ProtectionStrategiesDemo
```

Stdout:

```text
LOCK accepted=1000 remaining=0
ATOMIC accepted=1000 remaining=0
QUEUE accepted=1000 remaining=0
```

Chạy khi số chỗ lớn hơn số yêu cầu:

```shell
java ProtectionStrategiesDemo 2000
```

Stdout:

```text
LOCK accepted=1600 remaining=400
ATOMIC accepted=1600 remaining=400
QUEUE accepted=1600 remaining=400
```

Chạy khi hết chỗ ngay từ đầu:

```shell
java ProtectionStrategiesDemo 0
```

Stdout:

```text
LOCK accepted=0 remaining=0
ATOMIC accepted=0 remaining=0
QUEUE accepted=0 remaining=0
```

Phân bố lượt thành công giữa từng worker không được cố định và không cần cố định cho hợp đồng này. Tổng kết quả mới là bất biến đang kiểm tra.

## 7. Đọc từng triển khai trong chương trình

### LockedSeats

Cả điều kiện `remaining == 0`, phép giảm và phép tăng đều nằm trong cùng lock. Snapshot cũng khóa trước khi đọc cặp trường.

Điểm thành công có thể được xem là lần cập nhật trạng thái trong vùng khóa. Luồng khác tuân thủ cùng lock không quan sát phần chuyển tiếp giữa hai trường.

Không trả tham chiếu tới một đối tượng nội bộ có thể bị sửa ngoài lock; ví dụ trả một record mới gồm hai giá trị.

### AtomicSeats

Mỗi vòng đọc một State. Nếu còn chỗ, tạo một State mới có tổng không đổi rồi cố thay bằng CAS. Chỉ luồng CAS thành công trả `true`.

Nếu thất bại, không dùng lại phép tính cũ để ghi đè. Nó phải đọc trạng thái mới, vì số chỗ có thể đã thay đổi hoặc đã hết.

Snapshot đọc `state.get()` đúng một lần. Nếu tự đọc `state.get().remaining()` rồi đọc `state.get().booked()` ở một thời điểm khác, có thể ghép hai phiên bản và mất tính nhất quán của cặp.

Ví dụ không đưa các State cũ trở lại tham chiếu và chỉ giảm số chỗ. Không suy ra mọi thuật toán CAS đều miễn nhiễm vấn đề phiên bản/tham chiếu được tái sử dụng.

### QueuedSeats

Vé được tạo trước khi công bố đối tượng tới worker. Trong giai đoạn đặt chỗ chỉ có thao tác lấy vé, không có bổ sung/hoàn trả.

`snapshotAfterWorkers()` của phương án này có tiền điều kiện quan trọng: **mọi worker đã kết thúc**. Khi đó queue không còn thay đổi, nên phép đếm được dùng để đối chiếu kết quả cuối.

Nó không phải một API snapshot nguyên tử hai trường khi queue đang bị cập nhật. Giá trị `booked = capacity - remaining` được suy ra ở thời điểm yên, không phải một bộ đếm độc lập được cập nhật cùng `poll()`.

### Phần điều phối kiểm tra

`CountDownLatch` tạo một điểm mở đầu chung cho worker; nó không bắt hệ điều hành chạy mọi luồng đúng cùng một thời điểm.

Mỗi worker giữ bộ đếm thành công cục bộ và trả qua Future. Luồng chính lấy hết kết quả trước khi đọc snapshot cuối. Không có nhiều luồng cùng sửa một biến tổng kiểu `int` không được bảo vệ.

Nếu worker ném lỗi, `get()` không bị bỏ qua: ngoại lệ đi lên và phép thử không được báo là thành công. Executor được dọn trong `finally`.

## 8. ConcurrentHashMap không biến mọi chuỗi thao tác thành giao dịch

Một collection an toàn cho truy cập đồng thời bảo vệ theo hợp đồng thao tác của nó, không theo mọi bất biến mà ứng dụng có thể đặt ra.

Ví dụ ý tưởng dễ sai:

```java
if (!map.containsKey(key)) {
    map.put(key, value);
}
```

Giữa hai lệnh, một luồng khác có thể đã thêm cùng key. Khi mục tiêu là “thêm nếu chưa có”, dùng thao tác phù hợp như `putIfAbsent()` hoặc `computeIfAbsent()`.

Nhưng ngay cả `compute()` trên một key cũng không tự làm cập nhật hai key hoặc hai map thành một giao dịch. Việc chuyển giá trị từ tài khoản A sang B cần bảo vệ quan hệ toàn bộ, không chỉ từng entry riêng.

Một lỗi khác:

```java
ConcurrentHashMap<String, List<String>> groups = new ConcurrentHashMap<>();
```

Kiểu map này không tự làm `ArrayList` được lưu làm value an toàn khi nhiều luồng gọi `add()`. Cần chọn value bất biến, collection phù hợp hoặc quy tắc khóa/cập nhật rõ.

Các thao tác tổng hợp, duyệt và kích thước của ConcurrentHashMap cũng không nên được xem là một snapshot giao dịch của toàn map đang thay đổi. Xem [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

## 9. Bảng chọn phương án theo bất biến và kiểu truy cập

| Nhu cầu | Phương án thường đáng cân nhắc | Điều phải kiểm tra thêm |
| --- | --- | --- |
| Một biến đếm độc lập, tăng/giảm nguyên tử | AtomicInteger/AtomicLong | Chuỗi check–update có cần CAS hay không |
| Nhiều trường chuyển cùng phiên bản, trạng thái nhỏ bất biến | AtomicReference<State> | CAS retry, cấp phát, tác động phụ, snapshot đọc một phiên bản |
| Điều kiện/cập nhật nhiều trường hoặc nhiều bước | Lock hoặc synchronized phù hợp | Mọi đường đọc/ghi, thứ tự khóa, thời gian giữ khóa |
| Lấy/giao phần tử giữa producer và consumer | Queue đồng thời/BlockingQueue phù hợp | Giới hạn dung lượng, chờ, hủy và backpressure |
| Cập nhật độc lập theo key | ConcurrentHashMap với thao tác phù hợp | Tính nguyên tử theo key, value có thể thay đổi, bất biến nhiều key |
| Danh sách đọc nhiều, ghi ít | Cấu trúc phù hợp như CopyOnWriteArrayList nếu hợp đồng khớp | Chi phí sao chép khi ghi và ý nghĩa iterator |
| Thống kê số lượt với nhiều luồng cập nhật | LongAdder khi đúng mục tiêu thống kê | Không dùng snapshot tổng để cấp hạn mức nghiêm ngặt |

`LongAdder.sum()` không phải snapshot nguyên tử trong lúc có cập nhật. Vì thế không dùng mẫu `if (adder.sum() < limit) adder.increment()` để bảo đảm không vượt hạn mức. Xem [LongAdder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html#sum()).

Không có quy tắc “Atomic luôn nhanh nhất” hoặc “Lock luôn chậm”. Hiệu năng còn phụ thuộc mức tranh chấp, số luồng, kích thước trạng thái, cấp phát, phần cứng và thời gian ở vùng tới hạn.

Muốn đo hiệu năng, cần một thí nghiệm riêng với cùng hợp đồng, cùng dữ liệu và cách đo phù hợp. Ba phương án trong bài dùng cấu trúc bộ nhớ khác nhau; chỉ nhìn một lượt chạy không đủ để chọn cho mọi hệ thống.

## 10. Các lỗi thiết kế cần tránh

| Lỗi | Vì sao không đủ bảo vệ |
| --- | --- |
| Hai AtomicInteger cho hai trường rồi cập nhật lần lượt | Không tạo một bước nguyên tử cho cả cặp |
| Đọc ngoài lock vì “chỉ đọc” | Có thể phá khả kiến/nhất quán của hợp đồng |
| Khóa ở setter nhưng getter dùng một lock khác | Hai đường không phối hợp cùng cơ chế |
| Tạo lại expected State bằng giá trị rồi CAS | AtomicReference so sánh reference identity |
| Sửa một đối tượng mutable sau khi đặt vào AtomicReference | Chưa bảo vệ các trường bên trong đối tượng đó |
| isEmpty rồi remove ở queue | Điều kiện có thể thay đổi giữa hai thao tác |
| Lấy nhiều phần tử bằng nhiều poll rồi coi như một giao dịch | Có thể chỉ lấy được một phần yêu cầu |
| Dùng size đang thay đổi để ra quyết định cấp hạn mức | Giá trị tổng hợp không phải hợp đồng nguyên tử cần thiết |
| Cho rằng collection bảo vệ cả value mutable | Cấu trúc và phần tử có trách nhiệm riêng |
| Dùng thử nhiều lần thấy đúng nên coi là chứng minh | Lịch chạy chưa chắc đã chạm cuộc đua cần tìm |

Một bài kiểm tra nhiều luồng có thể phát hiện lỗi nhưng không thay thế việc phân tích hợp đồng và điểm cập nhật nguyên tử. Các bất biến nên được kiểm tra bằng cả đọc mã lẫn ca thực thi.

## 11. Bài tập mở rộng

1. Thêm thao tác trả lại chỗ. Cần điều kiện nào để không trả thừa hoặc trả cùng một vé hai lần?
2. Đổi yêu cầu sang đặt 2 chỗ cùng lúc hoặc không đặt chỗ nào. Với Lock, CAS State và queue, thao tác nào phải thay đổi?
3. Thêm tên người đặt. Việc giảm chỗ và ghi danh sách người đặt có còn nằm trong cùng bất biến không?
4. Yêu cầu đọc snapshot trong khi worker đang chạy. Vì sao snapshot của queue trong mẫu chưa đủ, còn snapshot dưới lock hoặc một lần get State có hợp đồng khác?
5. Thử thay CAS State bằng hai AtomicInteger và viết ra một lịch xen kẽ làm tổng tạm thời sai. Không cần trông chờ máy tình cờ tái hiện nó.
6. Đo phân bố số lượt thành công theo worker. Vì sao hợp đồng “không vượt sức chứa” không tự bảo đảm chia đều?

Khi chọn cách bảo vệ dữ liệu, hãy viết bất biến, xác định đơn vị cần cập nhật nguyên tử và quy tắc đọc trước. Sau đó chọn Lock, Atomic hay collection sao cho hợp đồng của công cụ bao trùm đúng đơn vị đó.

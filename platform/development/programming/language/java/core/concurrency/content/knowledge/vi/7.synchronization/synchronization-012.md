# Vấn đề khi gọi callback hoặc blocking I/O trong `synchronized`

Trong Java, `synchronized` bảo vệ một **critical section** bằng intrinsic monitor lock. Khi một thread giữ monitor, thread khác cần cùng monitor phải chờ. Đây là cách hữu ích để bảo vệ invariant của trạng thái dùng chung. Nhưng nếu code **gọi callback do bên ngoài cung cấp** hoặc **thực hiện thao tác có thể block** ngay trong critical section, thời gian giữ monitor trở nên khó dự đoán. Hậu quả có thể là latency tăng, lock contention, deadlock, nghẽn tài nguyên và lỗi vòng đời khó truy tìm.

Một nguyên tắc thiết kế quan trọng:

> **Giữ vùng `synchronized` ngắn và chỉ bảo vệ những thao tác trạng thái thật sự cần atomic. Không gọi mã người dùng không kiểm soát hoặc chờ I/O kéo dài khi đang giữ monitor, trừ khi đã chứng minh rõ hợp đồng và lý do.**

Bài này thuộc phần **Synchronization** của **Java concurrency nói chung**. Ví dụ dùng Java SE 17+ (`Thread`, monitor, `java.util.concurrent`, callback và các thao tác blocking thông dụng), không sử dụng cơ chế đồng bộ riêng của Spring Framework.

## 1. `synchronized` khóa gì và khóa trong bao lâu?

Ví dụ:

```java
synchronized (monitor) {
    updateSharedState();
    slowOperation();
}
```

Đây là đoạn minh họa, `monitor` và các phương thức chưa được khai báo. Thread vào block phải lấy **monitor của đúng đối tượng `monitor`**. Monitor được giữ từ lúc vào cho đến khi rời block, kể cả khi có `return` hoặc exception làm thoát block. JVM bảo đảm nhả intrinsic lock khi luồng điều khiển rời vùng `synchronized`.

Ba cách viết cần phân biệt:

| Cú pháp | Monitor được giữ |
| --- | --- |
| `synchronized (lock) { ... }` | Chính đối tượng `lock` |
| `synchronized void method() { ... }` | `this` của instance |
| `static synchronized void method() { ... }` | Đối tượng `Class` tương ứng |

Các monitor khác nhau **không tự loại trừ nhau**. Nếu hai phương thức bảo vệ cùng một invariant nhưng khóa hai đối tượng khác nhau, chúng chưa có mutual exclusion đúng.

Ngoài mutual exclusion, `synchronized` còn có ý nghĩa của Java Memory Model: **unlock trên một monitor happens-before lần lock tiếp theo trên cùng monitor**. Các ghi trước unlock được công bố phù hợp cho thread đã lock lại, với điều kiện các đường truy cập cũng theo giao thức bảo vệ.

**`synchronized` không tự biết thao tác nào sẽ chậm.** Nếu code trong vùng khóa ngủ 10 giây, gọi mạng 30 giây hoặc đợi callback không quay về, lock tiếp tục bị giữ trong thời gian đó. Thời gian chờ lock của các thread khác tăng theo thời gian chủ lock chưa rời vùng khóa.

## 2. Vì sao callback là ranh giới đặc biệt nguy hiểm?

**Callback** là mã được gọi lại thông qua một đối tượng, interface, lambda hoặc listener mà logic của nó có thể nằm ngoài quyền kiểm soát của class hiện tại.

Ví dụ anti-pattern:

```java
final class UnsafeNotifier {
    private final java.util.List<java.util.function.Consumer<String>>
            listeners = new java.util.ArrayList<>();

    public synchronized void addListener(
            java.util.function.Consumer<String> listener) {
        listeners.add(listener);
    }

    public synchronized void publish(String event) {
        for (var listener : listeners) {
            listener.accept(event); // Gọi mã không kiểm soát dưới monitor this.
        }
    }
}
```

Class trên là ví dụ minh họa, không có `main`. Nó có thể đồng bộ truy cập tới `listeners` nhưng **đang giữ monitor của notifier trong khi chạy `listener.accept(event)`**. Listener do client đăng ký có thể:

- Thực hiện logging hoặc I/O đồng bộ rất chậm.
- Chờ `Future.get()`, `Thread.join()`, `CountDownLatch.await()` hoặc một task khác.
- Gọi lại `publish` hoặc `addListener` (reentrancy).
- Gọi một component khác đang giữ lock của chính nó, tạo nguy cơ **lock-order inversion**.
- Đăng ký hoặc hủy đăng ký listener khi đang duyệt.
- Ném unchecked exception và dừng lượt dispatch giữa chừng.
- Gọi một API đã bị đóng hoặc bắt đầu thao tác `shutdown` làm phát sinh vòng chờ.

Vì vậy, lời hứa "thread-safe notifier" chỉ đúng nếu class còn xử lý **callback policy**, **lifecycle** và **giao thức đồng bộ** của mọi nhánh. Khóa bảo vệ cấu trúc `listeners` không đồng nghĩa callback an toàn.

## 3. Rủi ro 1: lock contention và convoy

Hãy xét chuỗi:

```text
Thread A                       Thread B                  Thread C
--------                       --------                  --------
lock notifier
update list
gọi listener chậm
    |
    |                         gọi addListener()
    |                         -> chờ monitor
    |                                                     gọi snapshot()
    |                                                     -> chờ monitor
    |
listener trả về
unlock notifier
                              lấy được monitor ...
```

Trong thời gian listener chậm, thread B và C không thể vào các vùng `synchronized` dùng cùng monitor. Chúng có thể ở trạng thái `BLOCKED` khi chờ intrinsic monitor; nếu có nhiều caller, thời gian chờ bị dồn lại, tạo **lock convoy** hoặc contention kéo dài.

Điều này không đồng nghĩa JVM bị deadlock. Nếu callback trả về, hệ thống có thể tiếp tục. Nhưng **độ trễ của những lời gọi không liên quan trực tiếp đến callback** vẫn bị kéo dài do bị buộc xếp hàng sau callback đó.

Ví dụ nếu `getStatus()` chỉ đọc một số nguyên và được khai báo `synchronized` trên cùng object, nó cũng có thể bị chặn bởi listener đang làm HTTP request mặc dù thao tác đọc chỉ cần rất ít thời gian.

**Mức độ nghiêm trọng phụ thuộc hợp đồng:** trong công cụ nội bộ đơn giản, callback cực ngắn và được kiểm soát, giữ lock có thể chấp nhận được; trong public API nhận callback tùy ý, đây là giả định rủi ro lớn và cần tránh.

## 4. Rủi ro 2: callback đợi thread khác cần chính monitor — deadlock

Một ví dụ tự tạo vòng chờ:

```text
Thread A (giữ monitor M)
  -> gọi callback dưới lock M
     -> callback submit task T rồi đợi T hoàn tất

Thread B (thực thi task T)
  -> cần lock M để gọi một method synchronized
  -> bị BLOCKED vì A đang giữ M

A đợi B; B đợi A nhả M => deadlock.
```

Đoạn Java sau chỉ để phân tích **anti-pattern**, tuyệt đối không chạy nó như một test tự động không có timeout:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ExecutionException;

final class DeadlockIllustration {
    private int value;

    synchronized int readValue() {
        return value;
    }

    synchronized void wrongWait(ExecutorService pool)
            throws InterruptedException, ExecutionException {
        // Caller giữ monitor của this.
        pool.submit(this::readValue).get();
        // Worker cần chính monitor đó trước khi Future hoàn tất.
    }
}
```

Nếu executor thực thi task trên **thread khác**, và task này cố lấy monitor trước khi hoàn tất, thread caller `wrongWait` giữ monitor trong lúc đợi future: vòng phụ thuộc không thể tự giải quyết. Nếu executor có chính sách chạy task inline trên caller thread, hành vi có thể khác. Điểm cần rút ra là **đừng chờ một công việc có thể cần lock mình đang giữ**.

### Nhưng intrinsic lock là reentrant, có phải callback gọi ngược luôn deadlock?

**Không.** Java intrinsic monitor có tính **reentrant**: cùng một thread đang giữ monitor có thể vào lại phương thức `synchronized` trên **chính monitor đó**. Ví dụ một listener chạy ngay trong thread A và gọi `notifier.addListener(...)` có thể lấy lại monitor `notifier` mà không tự deadlock do monitor đó.

Tuy nhiên, reentrancy vẫn có vấn đề:

- Callback có thể thay đổi state giữa một operation tưởng chừng đang thực thi atomic ở lớp gọi.
- Listener có thể thêm/xóa phần tử khi đang duyệt `ArrayList` bằng iterator, gây `ConcurrentModificationException` hoặc phá giả định về iteration.
- Callback có thể gọi lại `publish` đệ quy, dẫn đến dispatch lồng nhau, thứ tự event khó hiểu hoặc `StackOverflowError`.
- Callback có thể lấy **một lock khác** rồi tạo vòng chờ với thread khác, cho dù monitor ban đầu là reentrant.

Phân biệt chính xác: **gọi lại trên cùng monitor từ cùng thread không tự deadlock**; **chờ thread khác hoặc đảo thứ tự nhiều lock** có thể deadlock.

## 5. Rủi ro 3: lock-order inversion giữa hai component

Một deadlock phổ biến không cần `Future.get()`:

```text
Thread A: lock ServiceA -> callback gọi ServiceB -> chờ lock ServiceB
Thread B: lock ServiceB -> callback gọi ServiceA -> chờ lock ServiceA
```

Ở thời điểm này:

- A giữ khóa của ServiceA và chờ khóa của ServiceB.
- B giữ khóa của ServiceB và chờ khóa của ServiceA.

Không thread nào có thể tiến, dù callback ban đầu chỉ định "thông báo thay đổi". Khi mỗi class tự quản lý lock, nguy cơ càng khó phát hiện: không một class nào có thể nhìn thấy toàn bộ **thứ tự khóa** của các thành phần khác.

Giải pháp nền tảng là **không gọi callback bên ngoài khi đang giữ lock nội bộ**. Trong những đoạn thật sự cần lấy nhiều lock, hãy định nghĩa **thứ tự lock nhất quán** và tránh chạy mã không kiểm soát khi giữ chúng.

Với `ReentrantLock`, `tryLock(timeout, unit)` có thể giúp một số thiết kế tránh chờ vô hạn; nó **không tự loại bỏ deadlock** nếu logic lock acquisition và tài nguyên phụ thuộc chéo vẫn sai.

## 6. Rủi ro 4: exception, partial work và invariant

Khi callback ném exception, intrinsic monitor sẽ được JVM nhả khi phương thức thoát bất thường. Nhưng **nhả lock không đồng nghĩa rollback mọi thay đổi**:

```java
synchronized (lock) {
    status = Status.UPDATING;
    listener.onUpdate(); // Ném RuntimeException.
    status = Status.READY; // Bị bỏ qua.
}
```

Đây là đoạn minh họa với `lock`, `status`, `Status` và `listener` giả định. Nếu callback ném unchecked exception, trạng thái có thể nằm lại ở `UPDATING`. Các caller sau đó lấy được monitor nhưng có thể gặp invariant hoặc lifecycle không như thiết kế.

Cần quyết định **thứ tự thay đổi state và phát callback**:

1. Cập nhật state hợp lệ trong lock.
2. Tạo dữ liệu event hoặc immutable snapshot.
3. Nhả lock.
4. Gọi callback bên ngoài lock.
5. Xử lý exception của callback theo chính sách: propagate, ghi nhận rồi tiếp tục, retry hoặc thông báo kết quả từng listener.

Không có chính sách duy nhất đúng với mọi API. Nhưng với public API, **callback exception behavior** phải được document: nếu listener A ném lỗi, listener B có còn được gọi không? Thay đổi state trước callback có giữ nguyên không? Có phát lại event không?

### Tính atomic của state khác với "all-or-nothing delivery"

Cập nhật một danh sách dưới lock có thể là một thay đổi atomic đối với state nội bộ. Nhưng nếu event được gửi cho A, rồi B ném exception trước khi C nhận event, việc giao thông báo đã **thành công một phần**. Đừng hứa "exactly once to all listeners" nếu không có giao thức delivery và lỗi phù hợp.

Nếu cần giao dịch bao gồm external system, khóa trong bộ nhớ JVM cũng **không tạo transaction** bao trùm HTTP request hoặc ghi database.

## 7. Rủi ro 5: callback có thể làm hỏng iterator

Ví dụ:

```java
synchronized (this) {
    for (var listener : listeners) {
        listener.onEvent(event);
    }
}
```

Nếu listener được gọi trên cùng thread và đăng ký một listener mới thông qua phương thức `synchronized` của cùng notifier, monitor reentrant không chặn callback. Trong lúc iterator của `ArrayList` đang hoạt động, sửa đổi cấu trúc list qua `add` có thể dẫn đến `ConcurrentModificationException` khi iterator kiểm tra lại.

**Tính reentrant của lock không biến `ArrayList` iterator thành ổn định trước sửa đổi cấu trúc.** Một giải pháp phổ biến là **chụp danh sách listener dưới lock** rồi duyệt bản chụp bên ngoài lock.

Cần định nghĩa snapshot semantics:

- Listener đăng ký **sau khi snapshot được tạo** sẽ không nằm trong lượt dispatch hiện tại.
- Listener bị xóa **sau khi snapshot được tạo** vẫn có thể nhận event trong lượt dispatch đang diễn ra.
- Hai `publish` có thể được gọi đồng thời, dẫn đến hai callback trên **cùng listener object** chạy cùng lúc nếu không có cơ chế serialization khác.
- Thứ tự callback trong một lượt có thể là thứ tự trong snapshot; không hứa thứ tự toàn cục giữa các lượt publish concurrent.

## 8. Mẫu an toàn: snapshot dưới lock, callback bên ngoài lock

Lưu thành `CallbackOutsideLockDemo.java`, chạy với JDK 17+:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;

public class CallbackOutsideLockDemo {
    static final class Notifier {
        private final List<Consumer<String>> listeners =
                new ArrayList<>();

        public synchronized void subscribe(Consumer<String> listener) {
            listeners.add(Objects.requireNonNull(listener));
        }

        public synchronized int listenerCount() {
            return listeners.size();
        }

        public void publish(String event) {
            List<Consumer<String>> snapshot;
            synchronized (this) {
                snapshot = List.copyOf(listeners);
            }

            // Không giữ monitor của Notifier ở đây.
            for (Consumer<String> listener : snapshot) {
                listener.accept(event);
            }
        }
    }

    public static void main(String[] args) {
        Notifier notifier = new Notifier();

        notifier.subscribe(event -> {
            System.out.println("Under notifier lock: "
                    + Thread.holdsLock(notifier));
            System.out.println("Listener count: "
                    + notifier.listenerCount());
        });

        notifier.subscribe(event ->
                System.out.println("Second listener: " + event));

        notifier.publish("READY");
    }
}
```

Biên dịch và chạy:

```bash
javac CallbackOutsideLockDemo.java
java CallbackOutsideLockDemo
```

Stdout chính xác:

```text
Under notifier lock: false
Listener count: 2
Second listener: READY
```

**Giải thích chi tiết:**

- `subscribe` và `listenerCount` cùng dùng monitor của `Notifier`, nên truy cập list được bảo vệ.
- `publish` chỉ giữ monitor trong lúc `List.copyOf(listeners)` tạo snapshot. Sau block đó, callback chạy **không giữ monitor của notifier**.
- `Thread.holdsLock(notifier)` cho biết **thread hiện tại** đang sở hữu monitor của đối tượng đó hay không tại thời điểm kiểm tra. Dòng `false` minh họa đúng thiết kế, không đo các lock khác mà callback có thể tự lấy.
- Callback được gọi ngay trên **caller thread** của `publish`. Code không tự chuyển callback sang background hoặc tự làm chúng serial giữa hai lượt publish đồng thời.
- `List.copyOf` chụp danh sách reference listener; nó không biến object listener mutable thành thread-safe. Nếu cùng listener được gọi đồng thời bởi hai caller, logic bên trong listener cần tự đảm bảo an toàn.

Ở đây callback nhận `String` immutable. Nếu event là một mutable object, phải thiết kế thêm **ownership/safe publication** để listener không đọc object đang bị thread khác sửa.

### Lựa chọn thay thế: `CopyOnWriteArrayList`

Đối với tập listener nhỏ, **đọc và phát event rất thường xuyên nhưng đăng ký/hủy hiếm**, `CopyOnWriteArrayList<Listener>` có thể phù hợp:

- Thao tác ghi danh sách được cấu trúc tự đồng bộ.
- Iterator có snapshot semantics; có thể duyệt mà không tự giữ monitor registry.
- Chi phí sửa danh sách thường cao hơn vì phải copy cấu trúc mảng; không phù hợp mọi workload.
- Callback vẫn có thể chậm, ném exception hoặc chạy đồng thời trên cùng listener, nên không phải "lá chắn" cho callback logic.

Đổi từ `ArrayList` có lock sang `CopyOnWriteArrayList` chỉ giải quyết **cấu trúc lưu danh sách**, không giải quyết toàn bộ giao thức callback.

## 9. Callback nằm ngoài lock vẫn cần xác định điểm commit

Vì callback chạy sau khi nhả lock, state có thể tiếp tục được update trước hoặc trong lúc listener xử lý event.

Ví dụ:

```text
Thread A                             Thread B
--------                             --------
lock
  state = VERSION_1
  snapshot event VERSION_1
unlock
                                     lock
                                       state = VERSION_2
                                     unlock
gọi listener với VERSION_1
```

Khi callback nhận event `VERSION_1`, state hiện tại của service có thể đã là `VERSION_2`. Điều này **không phải lỗi** nếu API định nghĩa event là một immutable snapshot của update đã xảy ra, không phải lời hứa callback luôn nhìn thấy trạng thái mới nhất.

Nếu callback **đọc lại live state**, có thể thấy phiên bản mới hơn event. Tài liệu nên nói rõ:

- Event mang dữ liệu snapshot, version hay ID nào?
- Callback có được xem state mới nhất bằng lời gọi khác không, và hai giá trị có nhất thiết đồng nhất?
- Có bảo đảm **thứ tự callback** bằng thứ tự commit toàn cục không?
- Hai caller cùng cập nhật state có thể phát callback song song không?
- Listener nào có thể xuất hiện/bị xóa khi dispatch đang diễn ra?

**Chụp ngoài khóa không thay thế ordering policy.** Nếu cần dispatch tuần tự đúng theo thứ tự commit, dùng một queue được quản lý cùng giao thức bảo vệ khi enqueue, rồi một worker tiêu thụ event theo thứ tự xác định. Nhưng phải tính đến backlog, queue đầy, worker chết và shutdown, không chỉ vấn đề lock.

## 10. Blocking I/O trong `synchronized` nguy hiểm ở đâu?

Một thao tác **blocking I/O** có thể đợi dữ liệu từ mạng, file, socket, pipe, stream, database driver hoặc tài nguyên khác. Thời gian chờ phụ thuộc bên ngoài JVM và có thể lâu hoặc không có giới hạn nếu không thiết lập timeout/cancellation phù hợp.

Ví dụ anti-pattern:

```java
synchronized (lock) {
    updateMetadata();
    outputStream.write(payload);
    outputStream.flush();
}
```

Đây là đoạn minh họa với các biến/phương thức giả định. `write` hoặc `flush` có thể chờ bên nhận, buffer hoặc thiết bị; trong lúc đó **monitor `lock` vẫn được giữ**. Các thread muốn truy cập metadata qua cùng monitor phải chờ, dù việc đọc metadata không liên quan đến mạng.

Các tác hại thường gặp:

1. **Lock hold time** khó dự đoán vì phụ thuộc I/O latency.
2. **Throughput giảm** do các lời gọi cần cùng monitor bị xếp hàng phía sau I/O.
3. **Tail latency** tăng mạnh khi một lần I/O chậm bất thường.
4. **Lock inversion** nếu I/O gián tiếp kích hoạt callback hoặc thread khác cần monitor ban đầu.
5. **Shutdown/cancellation khó** khi thread giữ lock mắc kẹt trong một lời gọi không đáp ứng interruption.
6. **Inconsistent business state** nếu cập nhật state trước I/O rồi I/O thất bại, nhưng caller tưởng hai việc đã cùng commit.

Lưu ý: **không phải mọi I/O đều block trong mọi lần gọi**. Vấn đề là API **có thể block** và thời gian chờ không được critical section giới hạn. Một lần benchmark nhanh không chứng minh an toàn trên mọi tải.

## 11. Những lời gọi chờ nào nhả lock, lời gọi nào không?

Rất dễ nhầm từ "waiting" trong tiếng Anh với việc "JVM tự nhả monitor".

| Thao tác gọi khi đang giữ monitor `M` | Có tự nhả monitor `M` khi chờ? | Ghi chú |
| --- | --- | --- |
| `Thread.sleep(...)` | **Không** | Thread ngủ nhưng vẫn giữ các monitor đang sở hữu |
| `Thread.join()` | **Không tự nhả monitor M** | Có thể chờ target thread; nếu target cần M có nguy cơ deadlock |
| `Future.get()` | **Không** | Có thể chờ task khác cần chính monitor |
| `CountDownLatch.await()` | **Không** | Đợi latch; latch countDown có thể phụ thuộc thread cần M |
| `BlockingQueue.take()/put()` | **Không** | Queue tự quản lý đồng bộ của nó nhưng không nhả monitor M do caller giữ |
| Blocking socket/file I/O | **Không** | I/O không tự unlock monitor do caller giữ |
| `Object.wait()` gọi trên **M** khi giữ monitor M | **Có: nhả monitor M trong lúc wait** | Lấy lại monitor M trước khi `wait()` trả về; dùng vòng `while` kiểm tra điều kiện |
| `Condition.await()` dưới `ReentrantLock L` | Nhả và lấy lại **lock L** theo hợp đồng Condition | Không nhả các monitor/lock **khác** đang giữ |

Một nuance quan trọng: nếu gọi `otherObject.wait()`, thread phải sở hữu monitor của **otherObject**; lời gọi đó nhả monitor của otherObject, **không có nghĩa** nó nhả mọi monitor đang giữ, kể cả monitor M của service. Vì vậy "dùng `wait` trong synchronized là ổn" chỉ đúng khi thiết kế chờ trên **đúng monitor và đúng predicate**, không giữ các khóa phụ khác gây vòng chờ.

Tương tự, `Condition.await()` có cơ chế atomically release/reacquire **lock gắn với Condition**, không phải công cụ giải phóng toàn bộ lock trên stack.

## 12. Race giữa I/O bên ngoài và cập nhật state sau khi mở khóa

Giải pháp "cứ đưa network call ra ngoài lock" là điểm khởi đầu nhưng **chưa đủ** khi I/O lấy dữ liệu từ state và kết quả I/O quyết định bước cập nhật tiếp theo.

Mẫu ba pha:

```text
Pha 1 — dưới lock:
  đọc state và tạo immutable snapshot / operation ID / version
  hoặc đặt trạng thái "đang xử lý" theo invariant

Pha 2 — ngoài lock:
  thực hiện I/O hoặc callback có thể chậm
  kiểm tra timeout, cancellation, lỗi

Pha 3 — dưới lock:
  kiểm tra version/ownership/invariant
  commit kết quả nếu còn hợp lệ
  nếu stale: từ chối, retry có giới hạn hoặc xử lý conflict
```

Hai loại thiết kế phổ biến:

- **Snapshot + validate:** nếu state có thể đổi khi I/O đang diễn ra, ghi thêm version/token và chỉ commit nếu version vẫn đúng.
- **Reservation/state machine:** nếu nghiệp vụ cần giữ quyền sử dụng tài nguyên trong khi I/O, tạo reservation hoặc state chuyển tiếp trong lock trước, nhả lock cho I/O, rồi commit/abort qua operation được đồng bộ. Đảm bảo timeout và rollback/resolution khi I/O thất bại.

Đừng giữ monitor chỉ vì "muốn I/O và cập nhật là một thao tác atomic". Khóa monitor JVM **không biến I/O ngoài process thành transaction**, và việc giữ lock lâu chỉ khuếch đại contention. Nếu external side effect đã xảy ra rồi commit nội bộ thất bại, cần cơ chế idempotency/compensation hoặc giao thức giao dịch phù hợp; không thể chỉ dựa vào `synchronized`.

## 13. Ví dụ Java 17+: queue `put` có thể chờ nhưng không giữ monitor của state

`BlockingQueue.put` là một thao tác **blocking coordination** dễ kiểm chứng để minh họa nguyên tắc giống I/O có thể block: producer đợi queue còn chỗ. Nó không phải socket I/O, nhưng cho thấy cùng lỗi thiết kế sẽ xảy ra nếu code giữ monitor trong lúc chờ.

Lưu thành `QueueOutsideLockDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class QueueOutsideLockDemo {
    static final class State {
        private int value = 10;

        public synchronized void increment() {
            value++;
        }

        public synchronized int get() {
            return value;
        }

        public void send(
                BlockingQueue<Integer> queue,
                CountDownLatch snapshotTaken)
                throws InterruptedException {
            int snapshot;
            synchronized (this) {
                snapshot = value;
            }

            // Đã nhả monitor trước thao tác queue.put có thể block.
            snapshotTaken.countDown();
            queue.put(snapshot);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        State state = new State();
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(1);
        CountDownLatch snapshotTaken = new CountDownLatch(1);

        queue.put(-1); // Làm queue đầy trước khi worker gửi.

        Thread sender = new Thread(() -> {
            try {
                state.send(queue, snapshotTaken);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        sender.start();
        snapshotTaken.await();

        // State vẫn truy cập được, dù sender có thể đang đợi queue.
        state.increment();
        System.out.println("State now: " + state.get());

        System.out.println("Removed: " + queue.take());
        sender.join();
        System.out.println("Sent: " + queue.take());
    }
}
```

Biên dịch/chạy:

```bash
javac QueueOutsideLockDemo.java
java QueueOutsideLockDemo
```

Stdout chính xác trong lần chạy bình thường:

```text
State now: 11
Removed: -1
Sent: 10
```

**Điểm cần quan sát:**

- Worker chụp `value == 10` dưới monitor và nhả monitor trước `snapshotTaken.countDown()`.
- Main chỉ cập nhật sau khi nhận signal snapshot đã chụp; do vậy giá trị state mới là 11, trong khi message được gửi vẫn là snapshot 10.
- Queue ban đầu đã đầy. `queue.put(snapshot)` **có thể phải chờ** đến khi main lấy `-1` ra. Không có yêu cầu worker nhất định đã gọi `put` tại thời điểm main in dòng đầu; kết quả vẫn xác định nhờ latch và snapshot.
- Nếu `send` giữ monitor suốt `queue.put`, main có thể bị chặn trong `increment()` trong khi chính main là thread duy nhất sau đó lấy item khỏi queue: một vòng chờ khó tiến triển sẽ xuất hiện.
- `CountDownLatch.await` ở main là điều phối hợp lệ; worker nhả monitor trước tín hiệu. `Thread.sleep` không thể thay thế việc chứng minh snapshot đã được tạo.

Cùng nguyên tắc áp dụng khi gửi dữ liệu qua socket hoặc ghi file: **chụp payload hợp lệ dưới lock, gửi ngoài lock**, rồi xử lý kết quả bằng một pha commit riêng nếu nghiệp vụ yêu cầu.

## 14. Snapshot có thể cũ: kiểm tra version trước khi commit

Một response từ bên ngoài có thể quay về sau khi state đã bị thread khác thay đổi. Nếu cứ ghi response xuống state mà không kiểm tra, có thể ghi đè dữ liệu mới bằng thông tin cũ.

Ví dụ Java 17+ sau tập trung vào **logic validate/commit**, không tạo network call. Phần xử lý bên ngoài được mô phỏng bằng một giá trị cố định để stdout không phụ thuộc mạng.

Lưu thành `VersionedCommitDemo.java`:

```java
public class VersionedCommitDemo {
    private record Snapshot(long value, long version) {}

    private static final class State {
        private long value = 10;
        private long version;

        synchronized Snapshot snapshot() {
            return new Snapshot(value, version);
        }

        synchronized void incrementLocally() {
            value++;
            version++;
        }

        synchronized boolean commitIfUnchanged(
                Snapshot expected, long externalResult) {
            if (version != expected.version()) {
                return false;
            }
            value = externalResult;
            version++;
            return true;
        }

        synchronized long get() {
            return value;
        }
    }

    public static void main(String[] args) {
        State state = new State();

        Snapshot beforeExternalWork = state.snapshot();

        // Một cập nhật khác xuất hiện khi pha xử lý ngoài lock diễn ra.
        state.incrementLocally();

        // Cố gắng commit kết quả đã tính trên snapshot cũ.
        boolean accepted = state.commitIfUnchanged(
                beforeExternalWork, 99);

        System.out.println("Accepted stale result: " + accepted);
        System.out.println("Current value: " + state.get());
    }
}
```

```bash
javac VersionedCommitDemo.java
java VersionedCommitDemo
```

Stdout chính xác:

```text
Accepted stale result: false
Current value: 11
```

Đây là **optimistic concurrency control** ở mức state trong process: chỉ commit nếu version chưa đổi. Phương thức `commitIfUnchanged` giữ monitor trong cả bước kiểm tra và cập nhật nên không có khoảng xen kẽ giữa hai thao tác.

Các giới hạn:

- Version phải tăng khi **mọi thay đổi liên quan tới invariant** xảy ra; nếu bỏ sót một mutation, kiểm tra version có thể sai.
- Trong một hệ thống dài hạn cần tính đến version overflow và cách quản lý identity/generation; không dùng một version nhỏ dễ tái sử dụng nếu điều đó tạo vấn đề ABA.
- Nếu external request đã tạo side effect không thể hoàn tác, việc bỏ commit nội bộ không tự rollback side effect ngoài JVM.
- Nếu cần retry, phải xác định timeout, cancellation, giới hạn retry, idempotency và thứ tự phát event.
- Đoạn demo chạy tuần tự để giải thích semantics; trong ứng dụng thật, các pha giữa snapshot và commit có thể chạy ở thread khác. Invariant vẫn được bảo vệ khi mọi mutation đi qua đúng monitor.

## 15. Callback chờ nhưng registry vẫn xử lý request khác

Mẫu chụp snapshot rồi gọi callback ngoài lock có lợi ngay cả khi callback không làm I/O mà chờ một tín hiệu.

Ví dụ Java 17+ có callback cố tình đợi latch, trong khi thread chính vẫn đọc được registry:

Lưu thành `CallbackProgressDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class CallbackProgressDemo {
    static final class Hub {
        private final List<Runnable> callbacks = new ArrayList<>();

        synchronized void register(Runnable callback) {
            callbacks.add(callback);
        }

        synchronized int count() {
            return callbacks.size();
        }

        void fire() {
            List<Runnable> snapshot;
            synchronized (this) {
                snapshot = List.copyOf(callbacks);
            }
            for (Runnable callback : snapshot) {
                callback.run(); // Không giữ monitor của Hub.
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Hub hub = new Hub();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        hub.register(() -> {
            System.out.println("Callback entered");
            entered.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            System.out.println("Callback released");
        });

        Thread caller = new Thread(hub::fire);
        caller.start();
        entered.await();

        try {
            System.out.println(
                    "Registry size while callback waits: " + hub.count());
        } finally {
            release.countDown();
            caller.join();
        }
    }
}
```

```bash
javac CallbackProgressDemo.java
java CallbackProgressDemo
```

Stdout chính xác trên đường chạy bình thường:

```text
Callback entered
Registry size while callback waits: 1
Callback released
```

**Vì sao ví dụ không bị kẹt?**

- `fire` giữ monitor của Hub **chỉ để copy callback list**.
- Callback có thể đợi `release` nhưng không còn giữ monitor Hub. Main vẫn gọi được `hub.count()` và sau đó mở latch.
- Nếu viết `synchronized void fire()` rồi gọi callback ngay trong method, main sẽ chờ lock trong `count()`, trong khi callback đợi main gọi `release.countDown()`: chương trình có nguy cơ mắc kẹt.
- `Thread.join()` được gọi sau `release.countDown()` để chờ thread callback kết thúc, không phải vòng polling `Thread.getState()`.

Trong production, tránh chờ vô hạn khi có dữ liệu hoặc callback không đáng tin: thêm timeout, chính sách hủy và giám sát lỗi. Ở đây latch được dùng để mô phỏng chính xác một callback đang chờ.

## 16. Khi muốn thực hiện callback bất đồng bộ, dùng executor có phải đủ?

Không hẳn. Một kiến trúc thường thấy:

```text
Thread ghi state
   |
   v
[lock, update state, create immutable event, unlock]
   |
   v
[executor/queue]
   |
   v
[callback trên worker khác]
```

Ý tưởng tốt là không buộc thread thay đổi state chạy callback nặng. Tuy nhiên, cần hiểu:

1. **Submit có thể bị từ chối** nếu executor shutdown hoặc queue đầy; `RejectedExecutionException` hoặc chính sách rejection phải được xử lý.
2. Một số chính sách như **CallerRunsPolicy** có thể chạy tác vụ ngay trên thread gọi; một số executor thực hiện trực tiếp trên caller. Do đó, **không gọi `executor.execute(callback)` bên trong lock rồi mặc nhiên tin rằng callback sẽ luôn chạy ngoài lock**. Hãy nhả lock **trước khi submit**.
3. Executor có thể sử dụng nhiều worker, nên callback cùng listener **có thể chạy đồng thời** hoặc event hoàn thành lệch thứ tự.
4. Future và exception cần được thu thập/định tuyến. Nếu callback ném lỗi trên worker, publisher có thể không nhận được lỗi theo cách trực tiếp như callback đồng bộ.
5. Queue không giới hạn có thể tích tụ backlog; queue bounded yêu cầu chính sách backpressure hoặc drop/retry có kiểm soát.
6. Khi shutdown, phải quyết định các event đã accepted có được gửi hết không, timeout khi drain, cách hủy và cách giải phóng tài nguyên.

Nếu API cam kết **thứ tự event theo commit**, phải định nghĩa cách enqueue tương ứng với thứ tự commit và worker dispatch. Hai thread có thể commit lần lượt dưới lock rồi submit ngoài lock theo thứ tự đảo; queue FIFO khi đó vẫn dispatch theo thứ tự enqueue, không nhất thiết thứ tự commit. Có thể dùng sequence number và một dispatcher phù hợp hoặc reservation/queue protocol được thiết kế rõ ràng.

**Async callback không xóa yêu cầu thread safety của listener.** Nó chỉ chuyển ranh giới thực thi. Listener vẫn có thể chia sẻ mutable state hoặc gọi ngược API đang được dùng.

## 17. Có cần giữ lock qua I/O để bảo đảm cùng thứ tự ghi?

Đôi khi mục tiêu của code là "đừng gửi message B trước message A". Giữ một monitor qua toàn bộ network send có thể **tình cờ** ép serialization, nhưng đổi lại mọi caller phải chờ network. Cần tách hai yêu cầu:

- **Bảo vệ state và gán thứ tự:** critical section ngắn để tạo sequence, lấy snapshot hoặc enqueue event theo thứ tự.
- **Thực hiện I/O:** một worker sở hữu output channel hoặc một hàng đợi đã xác định ordering; worker xử lý ngoài monitor state.

Với socket hoặc stream mà nhiều thread ghi, phải hiểu **atomicity của message framing**. Một `OutputStream.write(byte[])` không tạo ra hợp đồng transaction đa message cho protocol tùy ý; dữ liệu có thể phải đóng gói frame và gửi bởi một owner duy nhất hoặc khóa riêng chuyên dụng cho writer.

Một lock riêng cho **writer** cũng có thể cần thiết nếu giao thức output yêu cầu serialization. Nhưng **đừng dùng chính monitor quản lý toàn bộ state** để giữ xuyên một network call lâu, trừ khi đã chứng minh tradeoff là cần thiết và có timeout rõ ràng.

**Không có bảo đảm rằng file write hay socket write có thể cancel ngay bằng `Thread.interrupt()`.** Tính interruptible phụ thuộc API, loại channel và hệ điều hành. Với blocking network I/O, đặt timeout, thiết kế close/cancel theo API và xử lý partial write/retry theo protocol.

## 18. Giữ dữ liệu nhất quán trong khi gọi callback bên ngoài lock

Khi chụp state cho callback, nên ưu tiên **immutable event**:

```java
record AccountEvent(long accountId, long version, long balance) {}
```

Nếu thread thay đổi state sau khi event được tạo, callback vẫn đọc được payload đã chụp. Đây là ví dụ record immutable vì chỉ chứa kiểu primitive. Với record chứa `List<Item>` và `Item` mutable, cần copy cấu trúc và xử lý mutable element riêng.

Giải pháp "chụp dưới lock" chỉ đúng nếu các giá trị đang đọc được bảo vệ bởi **cùng giao thức lock**. Nếu một writer khác có quyền sửa field mà không giữ lock này, snapshot vẫn có thể thiếu nhất quán.

### Một event và một callback có thể chạy đồng thời với event khác

Khi publisher đã nhả lock, thread khác có thể commit thay đổi mới, trong khi event cũ chưa dispatch. Nếu listener kỳ vọng thứ tự commit nghiêm ngặt, phải tạo thêm chính sách ordering. Nếu chỉ cần **at-least-once notification** hoặc **eventual update**, cần xác định duplicate/retry/out-of-order và giải pháp idempotent.

Public contract nên trả lời:

- "Event mang snapshot tại thời điểm nào?"
- "Callback được gọi đồng bộ hay bất đồng bộ, trên thread nào?"
- "Có thể gọi trùng, gọi đồng thời hoặc gọi lệch thứ tự không?"
- "`unsubscribe` có ngăn callback đã được chụp snapshot không?"
- "Event đã được queue nhưng chưa gửi khi close sẽ ra sao?"
- "Callback lỗi thì state đã commit có bị hoàn tác không?"

Không nên viết chỉ "listener thread-safe" mà bỏ qua các điểm kể trên.

## 19. Khi bắt buộc phải giữ lock qua mã chậm

Có những hệ thống cần tính tuần tự mạnh hoặc tài nguyên legacy không có thiết kế owner/queue. Khi không thể tách ngay, cần làm rõ tradeoff và giảm rủi ro:

1. Xác định monitor nào đang giữ và ai khác cần monitor đó.
2. Đặt **timeout** hoặc deadline cho những lời gọi có hỗ trợ. Đừng mặc định một lời gọi I/O luôn trả về.
3. Không gọi callback tùy ý của khách hàng nếu thiếu contract về không block/reentrance/locking order.
4. Tránh giữ đồng thời nhiều lock; nếu cần, dùng một thứ tự lấy lock thống nhất.
5. Đặt rollback, reset hoặc trạng thái lỗi hợp lệ trong `try/finally` khi cần, nhưng nhớ rằng external side effect có thể không rollback được.
6. Theo dõi **lock contention**, thời gian chờ, queue depth, callback duration, deadlock và timeout.
7. Đánh giá chuyển sang snapshot + ngoài lock, state machine, producer–consumer hoặc actor-like owner khi có thể.

Với `ReentrantLock`, người viết phải nhả bằng `unlock()` trong `finally`; còn block `synchronized` được JVM tự nhả khi thoát. **Không** nhầm `finally` với khả năng hủy một blocking call: nếu thread kẹt mãi trong lời gọi I/O, control flow chưa chạy đến `finally`.

Một đặc tính của `ReentrantLock.lockInterruptibly()` là có thể đợi **lấy khóa** theo cách interruptible; nó không làm những network call đã được gọi trong critical section tự cancel.

## 20. Callback dưới lock có bao giờ là đúng?

Không phải mọi callback đều bị cấm tuyệt đối. Một số internal hook rất ngắn, do chính implementation kiểm soát, không block, không tái nhập và không lấy lock khác có thể được gọi trong critical section khi contract rõ ràng.

Ví dụ:

- Một pure function được kiểm soát nội bộ, không gọi code tùy ý, dùng để tính nhanh giá trị từ state đã khóa.
- Một thao tác cập nhật invariant trên object phụ mà thread-safe protocol đã xác định.
- Một callback nội bộ được audit và không có đường chờ/lấy lock ngược.

Nhưng đối với callback nhận từ **public API** như `Consumer<T>` hoặc `Runnable`, implementation không kiểm soát hành vi. Hợp đồng "callback này phải nhanh và không block" có thể là một ràng buộc, song nó khó bảo đảm caller nào cũng tuân thủ. Thiết kế không chạy callback dưới monitor vẫn thường dễ bảo trì và robust hơn.

Ngoài ra, ngay cả pure callback không block cũng có thể ném unchecked exception. Nếu toàn bộ operation kỳ vọng invariant đang ở trạng thái chuyển tiếp, cần khôi phục invariant trước khi trả control ra bên ngoài.

## 21. Checklist code review: có call-out khi giữ monitor không?

Khi review một class dùng `synchronized`, hãy tìm những lời gọi sau:

| Dấu hiệu trong critical section | Câu hỏi cần kiểm tra |
| --- | --- |
| `listener.accept(...)`, `callback.run()` | Callback có thể block, tái nhập, ném lỗi hoặc lấy lock khác không? |
| `InputStream.read`, `OutputStream.write/flush` | Có timeout không, chi phí I/O có giới hạn không, partial I/O xử lý thế nào? |
| `Future.get`, `join`, `await` | Task đang được đợi có thể cần chính monitor để hoàn tất không? |
| `BlockingQueue.put/take` | Queue có thể đầy/rỗng, cần thread giữ monitor mới có tiến độ không? |
| `Thread.sleep` | Có vô tình giữ monitor trong lúc ngủ không? Sleep không nhả lock |
| `executor.execute(...)` | Executor có thể inline task, reject hoặc block trong custom implementation không? |
| `log(...), serialize(...), toString()` | Có callback/collaborator user-defined hoặc I/O ẩn không? |
| `otherService.method(...)` | Có lock bên kia, callback ngược hoặc lock-order inversion không? |

**Những rủi ro gián tiếp cũng đáng kiểm tra.** Một method tên `format` hoặc `toString` có thể gọi formatter do người dùng cung cấp; một logger có appender chậm; một serializer có custom adapter; một thao tác collection có comparator do caller định nghĩa. Không chỉ nhìn tên hàm "I/O" hay "callback".

### Công cụ phát hiện

- Thread dump và `ThreadMXBean` có thể hỗ trợ xem monitor owner, thread chờ monitor và một số trường hợp deadlock.
- Java Flight Recorder (JFR) hoặc profiler phù hợp có thể đo monitor contention, blocking và thời gian callback.
- Test dùng `CountDownLatch` để tạo lịch chờ chủ động giúp lộ vòng phụ thuộc; đừng chỉ dùng `Thread.sleep` rồi đoán thứ tự.
- Stress test hữu ích nhưng không thay được phân tích ownership, thứ tự lock và happens-before.

Một `Thread.State.BLOCKED` là dấu hiệu thread đang đợi intrinsic monitor, **không tự chứng minh deadlock**. Cần phân tích lock owner và vòng phụ thuộc hoặc progress qua thời gian.

## 22. Lỗi phổ biến và cách giải thích chính xác

**"Synchronized khiến callback tự động thread-safe."** Không. Nó chỉ giới hạn những thread muốn giữ cùng monitor; callback có thể truy cập state khác hoặc được các publisher khác gọi đồng thời.

**"Callback gọi lại method synchronized của chính object luôn deadlock."** Không. Intrinsic monitor reentrant với cùng thread. Nhưng callback có thể tạo đệ quy, iterator invalidation hoặc deadlock khi chờ thread khác.

**"Chỉ cần chuyển `listener.accept` ra ngoài lock là giữ nguyên mọi semantics."** Không. Snapshot và ordering thay đổi; listener có thể nhận event cũ trong lúc state mới đã commit. Cần document rõ.

**"`Thread.sleep` tạm nhả lock."** Sai. Sleep không tự nhả intrinsic monitor đang giữ.

**"`Future.get` hoặc `BlockingQueue.take` sẽ nhả mọi lock khi chờ."** Sai. Chúng không nhả monitor bên ngoài của caller.

**"`Object.wait` sẽ nhả tất cả lock đang sở hữu."** Sai. `wait` nhả monitor của **đối tượng mà nó được gọi trên**, không nhả tùy ý những monitor khác.

**"Nhả lock trước I/O đồng nghĩa thao tác đã atomic."** Sai. State có thể đổi khi I/O diễn ra. Nếu cần commit theo snapshot, phải kiểm tra version/reservation và xử lý stale result.

**"Dùng executor nghĩa là callback chắc chắn ở thread khác."** Sai. Có direct executor và rejection policy chạy tác vụ trên caller thread. Hãy nhả monitor trước cả bước submit.

**"Có `finally` thì lock được nhả ngay khi thread bị block."** Sai. `finally` chỉ chạy khi control rời khỏi `try`; một lời gọi block vô hạn ngăn code đến bước cleanup.

**"Một monitor có thể bảo vệ cả network transaction."** Không thể bảo đảm transaction bên ngoài JVM bằng intrinsic monitor. Cần giao thức transaction/idempotency/compensation tương ứng.

**"Không có exception thì không có vấn đề."** Không. Contention và deadlock có thể làm ứng dụng treo mà không ném exception; slow callback có thể chỉ làm tail latency tăng.

## 23. Câu hỏi tự kiểm tra

**Câu 1:** Một `synchronized void publish(...)` duyệt `ArrayList` listener rồi gọi callback. Listener gọi `addListener` synchronized trên cùng instance. Điều gì đúng?

**Trả lời:** Monitor reentrant nên lời gọi cùng thread không tự deadlock vì lock đó. Nhưng việc thêm vào `ArrayList` trong khi iterator đang duyệt có thể phá iterator, và callback vẫn được chạy dưới monitor. Cần snapshot và callback ngoài lock hoặc một protocol khác.

**Câu 2:** Thread A giữ monitor khi gọi `Future.get()`. Task của future muốn gọi method synchronized trên cùng object. Có nguy cơ gì?

**Trả lời:** Nếu task chạy trên thread khác, A đợi task; task đợi A nhả monitor: **deadlock**. Tách việc đợi future khỏi critical section.

**Câu 3:** `Object.wait()` có tương đương `Thread.sleep()` về monitor không?

**Trả lời:** Không. `wait` gọi đúng trên monitor đang giữ sẽ tạm nhả monitor đó và lấy lại trước khi trả về; `sleep` không nhả monitor.

**Câu 4:** Snapshot listener rồi gọi callback bên ngoài lock có bảo đảm callback luôn thấy state hiện tại mới nhất không?

**Trả lời:** Không. Callback nhận snapshot tại một mốc, trong khi thread khác có thể cập nhật state sau đó. Nếu yêu cầu ordering, phải thêm protocol dispatch/version.

**Câu 5:** Vì sao queue `put` trong ví dụ an toàn hơn khi không giữ monitor state?

**Trả lời:** Queue có thể đầy làm `put` đợi; nhả monitor trước `put` cho phép thread khác cập nhật state/tiêu thụ queue để hệ thống tiếp tục.

**Câu 6:** Nếu I/O gửi thành công nhưng `commitIfUnchanged` trả `false`, intrinsic monitor có rollback external side effect không?

**Trả lời:** Không. Phải thiết kế idempotency, compensation hoặc giao thức đồng bộ với tài nguyên bên ngoài.

**Câu 7:** Gọi callback qua `executor.execute` khi đang `synchronized` đã chắc chắn an toàn chưa?

**Trả lời:** Chưa. Một executor hoặc rejection handler có thể chạy task inline ngay trên caller. Ngoài ra task có thể bị reject. Nhả monitor trước submit và định nghĩa chính sách lỗi, backlog và ordering.

**Câu 8:** Khi nào gọi callback dưới lock có thể chấp nhận được?

**Trả lời:** Khi mã callback được kiểm soát, rất ngắn, không block/tái nhập/lấy lock ngược, invariant và exception đã được chứng minh phù hợp. Với callback không kiểm soát từ public API, nên tránh.

## 24. Checklist triển khai

1. **Xác định invariant** cần đồng bộ: field nào phải đọc/ghi như một đơn vị, monitor nào bảo vệ?
2. **Vạch ranh giới call-out:** mọi callback, I/O, queue/future/await, logging/serialization có thể block hoặc gọi code ngoài quyền kiểm soát.
3. **Rút ngắn critical section:** copy immutable event/snapshot hoặc thay đổi state hợp lệ rồi nhả monitor.
4. **Thực thi chậm ngoài monitor:** callback, I/O, future wait, submit task; thiết kế timeout/cancel nếu API hỗ trợ.
5. **Kiểm tra lại state nếu cần:** version, token, reservation hoặc state machine khi commit kết quả sau pha ngoài lock.
6. **Giữ thứ tự nếu đó là contract:** queue/dispatcher với protocol commit–enqueue có thể chứng minh đúng.
7. **Xử lý exception rõ ràng:** callback fail, I/O fail, partial side effect, rejected task, lỗi shutdown, permit/lock release.
8. **Công bố concurrency contract:** callback thread model, concurrent delivery, removal semantics, snapshot visibility, failure policy, blocking, reentrancy và ordering.
9. **Test trường hợp xấu:** callback chờ, callback tái nhập, hai monitor ngược thứ tự, queue đầy, timeout, lỗi I/O, close khi còn task.
10. **Đo contention và tiến độ:** monitor wait, callback duration, queue depth, tail latency; đừng đánh đổi tính đúng để chỉ giảm thời gian đo được.

Với Java concurrency, câu hỏi mấu chốt không chỉ là **"đã synchronized chưa?"** mà còn là **"mình đang giữ monitor trong khi trao quyền chạy cho ai, đợi điều gì, và state có thể thay đổi thế nào trước khi tiếp tục?"**. Bảo vệ state bằng critical section ngắn, xử lý callback/I/O ở ngoài và xác nhận lại invariant khi commit giúp giảm đáng kể deadlock, nghẽn và những lỗi khó tái hiện.
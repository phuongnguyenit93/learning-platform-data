# 19.7. Ảnh hưởng của suspend, breakpoint và đánh giá biểu thức tới thread hoặc khóa

## Mục tiêu

Khi gỡ lỗi Java bằng debugger, việc chương trình **dừng ở breakpoint** không chỉ ảnh hưởng đến dòng code đang xem. Thread có thể bị tạm dừng khi đang giữ monitor, các thread khác có thể không lấy được khóa, timeout có thể hết hạn trong lúc bạn đang đọc biến và một biểu thức tưởng như “chỉ để xem giá trị” có thể thực thi code thật trong JVM đích.

Sau bài này, bạn có thể:

1. Phân biệt **debugger suspend**, **breakpoint**, **step** và `-agentlib:jdwp=...suspend=y` khi khởi động JVM.
2. Giải thích ba **suspend policy** trong Java Debug Interface (JDI): `SUSPEND_ALL`, `SUSPEND_EVENT_THREAD`, `SUSPEND_NONE`.
3. Phân tích tác động của breakpoint bên trong `synchronized`, `ReentrantLock`, đoạn I/O hoặc một luồng quan trọng đối với **lock owner, blocked thread, request latency và timeout**.
4. Hiểu vì sao **Evaluate Expression**, Watches, getters và `toString()` có thể thay đổi trạng thái chương trình hoặc bị treo vì chờ khóa; biết lưu ý đặc biệt của JDI `invokeMethod`.
5. Chạy một chương trình Java 17+ độc lập để quan sát thread giữ monitor và thread chờ monitor, rồi thực hành đặt breakpoint theo từng chính sách.
6. Chẩn đoán hiện tượng “ứng dụng chỉ treo khi debug” và áp dụng một quy trình gỡ lỗi giảm tác động lên production.

> **Ý chính:** **Suspend không đồng nghĩa với nhả khóa**. Debugger đang dừng một thread giữ monitor có thể khiến các thread khác `BLOCKED`, ngay cả khi bạn chỉ chọn “Suspend: Thread”. Đánh giá một method có thể thực sự chạy method đó trong JVM, nên kết quả debug có thể không còn phản ánh trạng thái trước khi bạn bấm Evaluate.

## 1. Khi gắn debugger vào JVM, điều gì đang xảy ra?

Trong hệ sinh thái Java, các thành phần thường xuất hiện gồm:

- **JVM đích (debuggee):** tiến trình Java chứa ứng dụng đang chạy.
- **Debugger client:** IDE như IntelliJ IDEA, Eclipse, VS Code hoặc công cụ dòng lệnh `jdb`.
- **JDWP (Java Debug Wire Protocol):** giao thức truyền yêu cầu/sự kiện debug giữa client và JVM.
- **JDI (Java Debug Interface):** API Java để debugger làm việc với thread, stack, breakpoint, object, class và method.
- **JVMTI:** giao diện công cụ cấp thấp mà VM/agent có thể sử dụng; bạn thường không cần gọi trực tiếp khi debug trong IDE.

```text
IDE / jdb                    JDWP                      JVM debuggee
+----------------+       +-------------+          +--------------------+
| Breakpoint     | <---> | Debug agent | <------> | Thread A           |
| Resume / Step  |       | / transport |          | Thread B           |
| Variables      |       +-------------+          | Monitor / Lock     |
| Evaluate       |                                | Heap / Shared data |
+----------------+                                +--------------------+
```

**Breakpoint** là một yêu cầu dừng/nhận sự kiện khi thực thi đi tới một vị trí, điều kiện hoặc một điểm theo tính năng debugger. **Suspend** là việc làm cho một hay nhiều thread tạm ngừng tiến triển khi có yêu cầu/sự kiện debug. **Step Into / Over / Out** thường đưa thread chạy đến điểm dừng kế tiếp, rồi lại tạm dừng theo hành vi debugger; chúng không phải công cụ “chạy an toàn không ảnh hưởng đến các thread khác”.

Cần phân biệt hai tình huống:

| Tình huống | Ý nghĩa |
| --- | --- |
| JVM khởi động với `-agentlib:jdwp=...,suspend=y` | JVM chờ debugger kết nối/cho phép chạy **trước khi `main` bắt đầu** theo JDWP VM-start suspension. |
| JVM chạy với `suspend=n` | Ứng dụng chạy ngay, dù chưa có debugger attach. |
| Breakpoint có **Suspend: All** | Khi breakpoint phát sinh, debugger yêu cầu đình chỉ tất cả thread thuộc phạm vi JDI trong VM. |
| Breakpoint có **Suspend: Thread** | Đình chỉ **thread chạm breakpoint**, các thread khác có thể tiếp tục. |
| Breakpoint không suspend (log/trace breakpoint, nếu debugger hỗ trợ) | Có thể ghi nhận sự kiện mà không yêu cầu ngừng thread, nhưng vẫn có chi phí instrumentation và biểu thức được đánh giá. |

`-agentlib:jdwp=...suspend=y` lúc startup **không phải** lựa chọn “Suspend All/Thread” riêng cho từng breakpoint. Tên đều có chữ *suspend*, nhưng điều kiện kích hoạt khác nhau.

## 2. Ba suspend policy trong JDI: dừng ai?

`com.sun.jdi.request.EventRequest` định nghĩa:

| JDI policy | Hành vi khi sự kiện được nhận | Ảnh hưởng điển hình |
| --- | --- | --- |
| `SUSPEND_ALL` | Tạm dừng tất cả thread của JVM đích trong phạm vi JDI. | Dễ chụp trạng thái hệ thống tại một điểm, nhưng **toàn ứng dụng có thể ngừng tiến triển** cho tới khi Resume. |
| `SUSPEND_EVENT_THREAD` | Tạm dừng **thread đã phát sinh sự kiện**. | Các thread khác còn cơ hội chạy, nhưng có thể mắc kẹt khi chờ dữ liệu/lock do thread bị dừng đang giữ. |
| `SUSPEND_NONE` | Không yêu cầu dừng thread vì sự kiện đó. | Hữu ích cho trace/logpoint; không nhất thiết đọc được locals/stack một cách ổn định khi chương trình vẫn chạy. |

Trong JDI, **mặc định của `EventRequest` là `SUSPEND_ALL`** nếu debugger không thay đổi. Giao diện IDE có thể ánh xạ bằng tên khác hoặc chọn mặc định riêng; **hãy đọc cấu hình của breakpoint cụ thể**, không suy đoán chỉ dựa vào tên IDE.

### `SUSPEND_ALL` có luôn có nghĩa là “mọi thứ đứng im tuyệt đối”?

Không nên hiểu như thế. JDWP/JDI quản lý trạng thái dừng các thread được debugger quan sát; các hoạt động bên ngoài JVM như thời gian thực, client, server từ xa và timeout ở hệ thống khác **vẫn tiếp tục**. Ngoài ra, một số thao tác của debugger như **method invocation trong Evaluate** có thể tạm thời cho các thread tiếp tục theo quy tắc JDI. Do đó, cả khi đang ở một breakpoint `Suspend All`, không được giả định JVM luôn hoàn toàn bất biến trong suốt quá trình đánh giá biểu thức.

### `SUSPEND_EVENT_THREAD` không đảm bảo phần còn lại của hệ thống chạy được

Giả sử thread A đang giữ một monitor mà B, C, D cần:

```text
Thread A: synchronized (LOCK) {
             ... BREAKPOINT: Suspend Thread ...
          }

Thread B: synchronized (LOCK) { ... }  // BLOCKED
Thread C: synchronized (LOCK) { ... }  // BLOCKED
Thread D: công việc độc lập              // Có thể vẫn chạy
```

A bị dừng **không tự động nhả monitor**. B và C có thể chạy đến bước lấy monitor rồi `BLOCKED` cho tới khi A tiếp tục và thoát vùng `synchronized`. D không phụ thuộc lock có thể vẫn hoạt động. Ứng dụng có thể vừa “đang chạy” vừa **không đáp ứng** các request quan trọng.

## 3. Vì sao suspend khi giữ khóa có thể gây treo?

Java có nhiều cơ chế đồng bộ, mỗi cơ chế có ý nghĩa chờ và nhả khóa khác nhau.

### 3.1. `synchronized` và monitor ownership

```java
synchronized (LOCK) {
    updateSharedState();
    callOtherMethod();   // Dừng ở đây vẫn giữ monitor LOCK
}
```

Đây là **đoạn minh họa**, không phải một chương trình độc lập.

Khi thread đã vào `synchronized (LOCK)` thành công, nó sở hữu monitor cho tới khi rời vùng đồng bộ (hoàn tất bình thường hoặc do exception và cơ chế mở khóa tương ứng). **Debugger tạm dừng thread không biến thành một lệnh rời `synchronized`**. Nếu thread khác cố vào chính monitor, nó có thể ở trạng thái `BLOCKED`.

- `Thread.sleep(...)` **không nhả monitor** mà thread đang giữ.
- `LockSupport.park(...)` **không tự nhả monitor**.
- `Object.wait()` gọi hợp lệ trong vùng sở hữu monitor **tạm nhả monitor tương ứng trong lúc đợi**, sau đó cần lấy lại trước khi trả về. Nhưng **debugger suspend không phải `Object.wait()`**.
- Java monitor là **reentrant**: chính thread đang sở hữu monitor có thể vào lại `synchronized` trên monitor đó; đây là điểm quan trọng khi diễn giải Evaluate.

### 3.2. `ReentrantLock` và `Condition`

```java
lock.lock();
try {
    updateState();
    inspectHere();       // Breakpoint: lock vẫn do thread giữ
} finally {
    lock.unlock();
}
```

Đây cũng là **đoạn minh họa**, với `lock` đã được khởi tạo và các method có sẵn ở ứng dụng. Breakpoint ở `inspectHere()` sẽ khiến thread dừng **trước khi vào `finally`**. Đến khi thread thực sự đi tiếp và thực hiện `unlock()`, lock mới được nhả.

Khác với intrinsic monitor, thread chờ `ReentrantLock` thường có thể ở `WAITING`/`TIMED_WAITING` qua cơ chế `LockSupport.park`, **không nhất thiết `BLOCKED`**. Đừng kết luận “không có thread BLOCKED thì không có lock contention”.

Một `Condition.await()` hợp lệ tạm nhả **lock liên kết** trong thời gian chờ; khi tỉnh lại sẽ cần lấy lại lock. Đừng suy ngược rằng debugger pause cũng nhả lock.

### 3.3. Khi nào đây là “debugger-induced stall”, khi nào là deadlock thật?

**Debugger-induced stall:**

```text
Thread A giữ LOCK -> breakpoint dừng A
Thread B cần LOCK -> chờ A
Resume A -> A chạy tiếp và nhả LOCK -> B tiến triển
```

Đây là **tình trạng chậm/đứng do breakpoint**, không đủ để kết luận đã có deadlock trong logic ứng dụng khi chạy bình thường.

**Deadlock thật:** các thread chờ nhau theo một chu trình không thể tự giải quyết, chẳng hạn A giữ lock X chờ Y trong khi B giữ Y chờ X. Một breakpoint có thể làm lộ hoặc tạo ra chuỗi chờ, nhưng chỉ hai thread chờ lâu **không đủ** chứng minh chu trình deadlock. Cần kiểm tra **ai giữ từng monitor/lock**, stack, graph phụ thuộc và kết quả sau Resume.

## 4. Chương trình Java 17+ để quan sát trực tiếp

Ta tạo một ví dụ độc lập dùng **hai platform thread**:

- `lock-owner` nắm monitor `LOCK`, báo đã nắm khóa rồi chờ tín hiệu từ waiter.
- `lock-waiter` xác nhận sắp cố vào cùng monitor; trong khoảng owner giữ khóa, waiter có thể ở trạng thái `BLOCKED`.
- Một lệnh trên thread owner là **vị trí breakpoint** ở bên trong `synchronized`.
- Biến `EVENTS` dùng để chứng minh **Evaluate Expression có tác dụng phụ** khi gọi method làm thay đổi giá trị.

Tạo file **`DebugSuspendLab.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class DebugSuspendLab {
    private static final Object LOCK = new Object();
    private static final CountDownLatch HOLDER_ENTERED = new CountDownLatch(1);
    private static final CountDownLatch WAITER_READY = new CountDownLatch(1);
    private static final AtomicInteger EVENTS = new AtomicInteger();

    public static int peekEvents() {
        return EVENTS.get();
    }

    public static int changeEvents() {
        return EVENTS.incrementAndGet();
    }

    public static int readUnderLock() {
        synchronized (LOCK) {
            return EVENTS.get();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread owner = new Thread(() -> {
            synchronized (LOCK) {
                System.out.println("owner: has lock");
                HOLDER_ENTERED.countDown();
                try {
                    if (!WAITER_READY.await(3, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("waiter not ready");
                    }
                    Thread.sleep(500);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }

                int seen = EVENTS.get(); // ĐẶT BREAKPOINT Ở DÒNG NÀY.
                System.out.println("owner: checkpoint=" + seen);
                EVENTS.incrementAndGet();
                System.out.println("owner: releasing");
            }
        }, "lock-owner");

        Thread waiter = new Thread(() -> {
            try {
                HOLDER_ENTERED.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            System.out.println("waiter: attempting lock");
            WAITER_READY.countDown();
            synchronized (LOCK) {
                System.out.println("waiter: acquired lock");
            }
        }, "lock-waiter");

        owner.start();
        waiter.start();
        owner.join();
        waiter.join();
        System.out.println("main: finished counter=" + EVENTS.get());
    }
}
```

### 4.1. Chạy bình thường, không debugger

Biên dịch với debug information để có line numbers/local variables khi gỡ lỗi:

```bash
javac --release 17 -g DebugSuspendLab.java
java DebugSuspendLab
```

Kết quả của chương trình này khi chạy bình thường (không gọi Evaluate, không thay đổi mã):

```text
owner: has lock
waiter: attempting lock
owner: checkpoint=0
owner: releasing
waiter: acquired lock
main: finished counter=1
```

**Đã kiểm tra chương trình với một JDK mới hơn ở chế độ `--release 17`.** Hai latch bảo đảm owner nhận khóa trước khi waiter cố vào, và waiter đã phát tín hiệu trước khi owner đi qua checkpoint. Khoảng ngủ 500 ms giúp dễ quan sát trạng thái chờ monitor; khi thực sự debug, thời lượng và thứ tự thời gian có thể khác vì scheduling và việc suspend.

Giải thích:

- `HOLDER_ENTERED` chỉ được mở sau khi owner đã nắm monitor.
- `WAITER_READY` xác nhận waiter sắp đi vào `synchronized (LOCK)`. Owner vẫn đang giữ monitor trong khi `Thread.sleep(500)`.
- `int seen = EVENTS.get()` nằm **trong** vùng đồng bộ và là vị trí thích hợp để đặt breakpoint.
- Dòng `EVENTS.incrementAndGet()` ở bên dưới checkpoint làm tăng biến một lần khi chương trình hoàn tất bình thường.
- `owner.join()` và `waiter.join()` khiến `main` chờ cả hai thread. Nếu owner bị dừng quá lâu ở breakpoint, **`main` cũng chưa hoàn tất**; đây là phụ thuộc bình thường, không phải lỗi của `join()`.

### 4.2. Khởi động JVM ở chế độ debug qua loopback

Để có thời gian đặt breakpoint trước khi worker thread chạy:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 DebugSuspendLab
```

Ở ví dụ này:

- `transport=dt_socket`: dùng socket JDWP.
- `server=y`: JVM đích lắng nghe debugger kết nối.
- `suspend=y`: JVM dừng **trước khi chạy `main`** cho tới khi được resume từ debugger.
- `address=127.0.0.1:5005`: chỉ lắng nghe trên **localhost IPv4**, tránh mở cổng debugger ra mạng.

Trong IDE, tạo cấu hình **Remote JVM Debug / Attach**, host `127.0.0.1`, port `5005`, bảo đảm IDE dùng source đúng với class đã biên dịch. Tạo **line breakpoint tại dòng `int seen = EVENTS.get();`**, không phải ở dòng comment, rồi cho phép VM chạy.

**Lưu ý:** port 5005 chỉ là ví dụ, cần đổi nếu đã có tiến trình khác chiếm. Debugger có thể hiển thị nội dung source và frame khác nhau tùy IDE/JDK; nếu đặt breakpoint ở dòng không sinh bytecode, IDE có thể dịch chuyển breakpoint sang dòng thực thi gần nhất.

### 4.3. Thí nghiệm A: Suspend All

1. Đặt breakpoint ở `int seen = EVENTS.get();`.
2. Chọn **Suspend: All** (hoặc “Suspend all threads” theo tên của IDE).
3. Tiếp tục chạy tới breakpoint và quan sát trạng thái các thread.
4. Khi dừng, **owner vẫn giữ `LOCK`**, nên waiter không thể vào block `synchronized` của mình.
5. Trong lúc toàn VM bị suspend, console không còn tiến triển theo hoạt động ứng dụng. Không thể lấy việc console đứng im làm bằng chứng deadlock.
6. Bấm **Resume** để cho owner thực thi nốt và nhả lock. Chương trình thường hoàn tất với output bình thường như mục 4.1 nếu bạn không thực hiện Evaluate có tác dụng phụ.

**Kết luận:** `SUSPEND_ALL` phù hợp chụp trạng thái nhất quán hơn khi đặt các thread cạnh nhau, nhưng bản thân pause đủ dài có thể làm sai phép đo latency hoặc khiến client bên ngoài timeout.

### 4.4. Thí nghiệm B: Suspend Thread (event thread)

1. Chạy lại ví dụ từ đầu, thay breakpoint thành **Suspend: Thread / Event thread**.
2. Thread `lock-owner` dừng tại checkpoint trong `synchronized`.
3. Các thread khác không bị **suspend trực tiếp bởi breakpoint đó**. Tuy nhiên:
   - `lock-waiter` có thể tiếp tục tới `synchronized (LOCK)` rồi `BLOCKED`.
   - `main` tiếp tục đợi `owner.join()` và chưa thể kết thúc.
   - Một thread **không phụ thuộc monitor** (nếu có) vẫn có thể chạy.
4. Khi Resume owner, monitor được nhả và waiter hoàn tất.

**Kết luận:** Suspend Thread làm giảm phạm vi pause trực tiếp, **không loại bỏ** hiệu ứng lan truyền do khóa và phụ thuộc giữa các thread.

### 4.5. Thí nghiệm C: Không suspend hoặc dùng logpoint

Nếu IDE hỗ trợ logpoint/tracepoint không suspend, thay line breakpoint bằng **in log mà không dừng**. Chương trình không bị giữ tại checkpoint chỉ vì yêu cầu debug đó; vẫn có overhead truyền event và format/log. Nếu logpoint có cấu hình tính biểu thức, biểu thức có thể thực thi code thật nên **không tự động an toàn**.

## 5. Evaluate Expression: quan sát không phải lúc nào cũng “read-only”

IDE thường có cửa sổ **Evaluate Expression**, **Watch**, **Variables**, **Inspect** và tùy chọn tự gọi getter/`toString()`. Chúng có thể dùng nhiều cơ chế khác nhau:

- **Đọc field trực tiếp qua JDI:** lấy giá trị được lưu trong object mà không nhất thiết chạy Java method.
- **Gọi method trong JVM đích:** ví dụ `list.size()`, `object.toString()`, `getState()`, `service.load()`, `someMap.computeIfAbsent(...)`; method đó có thể **thay đổi trạng thái, khóa, cấp phát, I/O hoặc throw exception**.
- **Tính điều kiện breakpoint:** tùy IDE/kiểu biểu thức, debugger có thể đánh giá điều kiện bằng cách đọc field hoặc gọi method trong target.
- **Render biến tự động:** IDE có thể gọi `toString()` hoặc getter để hiển thị preview dù bạn chưa cố ý gõ lời gọi.

### 5.1. Ví dụ đọc và sửa trạng thái trong lab

Trong lúc dừng ở `int seen = EVENTS.get();`, thử **theo thứ tự**:

```java
DebugSuspendLab.peekEvents()
```

Hàm này trả giá trị hiện có từ `AtomicInteger` và **đoạn mã của chính nó không chủ động thay đổi `EVENTS`**. Tuy nhiên, việc gọi nó qua debugger vẫn có thể ảnh hưởng scheduling vì JVM phải chạy method trong ngữ cảnh debug.

Tiếp theo, **chỉ trên chương trình thí nghiệm**:

```java
DebugSuspendLab.changeEvents()
```

Method này thực sự gọi `incrementAndGet()`, nên **tăng `EVENTS`**. Sau khi Resume, giá trị ở `owner: checkpoint=...` và `main: finished counter=...` có thể **khác output không debug**. Đây là bằng chứng Evaluate không phải thao tác chỉ đọc.

Ví dụ:

```text
Bình thường:  checkpoint=0, counter=1
Sau khi evaluate changeEvents() đúng một lần tại breakpoint:
               checkpoint=1, counter=2
```

Các con số ở dòng thứ hai là **kỳ vọng logic nếu chỉ có một lần gọi làm thay đổi và không có tác động khác**, không phải cam kết bất kể debugger có tự evaluate lại nhiều lần hay không.

### 5.2. Khi Evaluate gọi method có `synchronized`

Chương trình có thêm:

```java
DebugSuspendLab.readUnderLock()
```

Method đó vào `synchronized (LOCK)` rồi trả số đếm. Khi debugger thực thi method trên **chính `lock-owner` đã sở hữu monitor**, việc vào lại có thể thành công vì monitor là **reentrant**. Không được nói đơn giản “mọi Evaluate khi đang giữ lock đều deadlock”.

Nhưng nếu debugger gọi một method trên thread khác mà method phải lấy monitor **do một thread đang suspend giữ**, lời gọi có thể bị chặn. Tình huống này tùy **thread được chọn để invoke**, lock owner, trạng thái suspend, debugger settings và chính method.

**Ví dụ nguy hiểm khác** (chỉ để đọc/hiểu, không thực thi trên hệ thống quan trọng):

```java
// Có thể là method được Evaluate gọi:
public String describe() {
    synchronized (sharedLock) {
        return expensiveLookup();
    }
}
```

Nếu `sharedLock` đang được thread **khác đang suspend** giữ, Evaluate `describe()` có thể chờ mãi. `expensiveLookup()` còn có thể gọi network, file, database hoặc thực hiện thay đổi không mong muốn.

### 5.3. Điều đặc biệt quan trọng của JDI `invokeMethod`

Theo hợp đồng API `com.sun.jdi.ObjectReference.invokeMethod(...)` (cùng ý tưởng với các API invoke khác):

1. Debugger có thể yêu cầu **chạy một method trong thread cụ thể của target VM** khi thread đó được đình chỉ bởi một event phù hợp, chẳng hạn breakpoint. Đây không phải lúc nào cũng hợp lệ nếu thread chỉ bị suspend bằng lệnh khác.
2. Lời gọi có thể **chặn debugger** cho tới khi method trả về hoặc ném exception; với ứng dụng có khóa/chờ, nó có thể kéo dài ngoài dự kiến.
3. **Mặc định JDI có thể resume các thread khác trong target trong lúc method invocation**, nhằm giảm nguy cơ method phải chờ monitor do thread khác sở hữu. Sau invocation, JDI đặt lại trạng thái suspend theo hợp đồng API. Vì vậy **Evaluate có thể cho code ngoài thread hiện tại chạy tiếp**.
4. Nếu debugger sử dụng cờ **`INVOKE_SINGLE_THREADED`**, chỉ thread dùng cho invocation được cho chạy; các thread khác vẫn suspend. Điều này có thể khiến method chờ lock, future hoặc timer mà **không có thread khác được chạy để giải phóng**.
5. Số lần suspend (*suspend count*), breakpoint mới xảy ra trong lúc invoke và các event đang chờ debugger xử lý vẫn có thể tạo tình huống deadlock hoặc treo, **kể cả khi không bật single-threaded**.

**Không nên suy ra rằng mọi IDE đều sử dụng đúng một chế độ invoke**. Một IDE có thể tối ưu đọc field, tạm bật/tắt breakpoint, đổi flags hoặc từ chối Evaluate trong một số trạng thái. Nguyên tắc ứng dụng là **kiểm tra tùy chọn “Evaluate in single thread”, “Resume other threads”, “Invoke methods”, “Show toString” nếu công cụ cung cấp** và tránh gọi method chưa biết tác dụng phụ.

### 5.4. `toString()`, getter và property không vô hại theo tên gọi

Ví dụ một getter có lazy initialization:

```java
public synchronized Data getData() {
    if (cached == null) {
        cached = loadFromDatabase();
    }
    return cached;
}
```

Đây là **mã minh họa**, `Data`, `cached`, `loadFromDatabase()` thuộc ngữ cảnh một class ứng dụng. IDE gọi `getData()` khi render một object có thể:

- Lấy monitor của instance và làm tăng contention.
- Gọi database trong lúc JVM đang bị debug pause.
- Gán `cached`, biến đổi trạng thái trước khi bạn đo hoặc chụp snapshot.
- Throw exception/timeout khiến IDE hiển thị lỗi Evaluate, thậm chí làm app hoạt động khác đi.

`toString()` cũng có thể lồng nhiều getter, truy cập collection đang thay đổi, gọi remote service hoặc recurse theo object graph. **Đừng bật auto-evaluate cho các method đắt/không chắc chắn trên production**.

## 6. Conditional breakpoint, watchpoint, logpoint và Step cũng có chi phí

### 6.1. Conditional breakpoint

Ví dụ breakpoint chỉ dừng khi:

```java
requestId.equals("R-42")
```

Đây là **biểu thức minh họa** trong scope có biến `requestId`. Việc đánh giá `equals` là method call; có thể tương đối đơn giản ở `String`, nhưng **không thể tổng quát** rằng mọi method tên `equals` đều an toàn. IDE có thể gọi biểu thức mỗi lần code đi qua location, ngay cả khi điều kiện không thỏa.

Nếu breakpoint đặt trong vòng lặp nóng hàng triệu lần/giây, việc gửi event/đánh giá điều kiện có thể ảnh hưởng throughput nghiêm trọng. Chọn **thread filter, hit count, instance filter** khi debugger hỗ trợ, và tránh điều kiện gọi DB/network/lock hoặc sửa state.

### 6.2. Logpoint không bằng “zero impact”

Một logpoint có thể in thông tin mà không suspend thread. Nhưng vẫn có overhead xử lý event, format chuỗi, evaluate biểu thức và truyền dữ liệu. Nếu logpoint gọi `object.toString()` có side effect, ứng dụng vẫn có thể bị thay đổi dù không dừng ở breakpoint.

### 6.3. Step Into/Over/Out

- **Step Over** tiếp tục thực thi code cho tới vị trí dừng tiếp theo trong phương thức hiện tại; nó vẫn phải **chạy đoạn code thật**. Nếu code đó gọi hàm blocking/lock, thread có thể chờ.
- **Step Into** có thể vào method thực thi; không cho phép bỏ qua lock hoặc side effects.
- **Step Out** chạy cho tới khi thoát frame hiện tại; nếu frame đang giữ monitor, nó có thể chỉ nhả khóa khi thật sự rời vùng đồng bộ.
- Các IDE có thể có **Smart Step**, **Run to Cursor**, **Force Return** hoặc **Drop Frame**. Đừng xem các tính năng đó như rollback giao dịch: I/O, cập nhật DB, ghi file, counter increment trước đó **không tự được hoàn tác**.

Nếu cần biết nhiều lần gọi mà không pause nhiều, ưu tiên logging có kiểm soát, JFR, profiler hoặc metric thích hợp thay vì step từng iteration trên production.

## 7. Bốn mẫu sự cố thường gặp do debugger gây ra

| Mẫu sự cố | Cơ chế | Cách xác minh |
| --- | --- | --- |
| API không trả lời khi breakpoint dừng ở `synchronized` | Owner giữ lock nhưng bị suspend; worker khác chờ monitor. | Kiểm tra frame owner ở trong critical section, thread khác `BLOCKED`; Resume rồi xem hoạt động có phục hồi không. |
| Không thấy heartbeat/timeout/callback khi **Suspend All** | Thread xử lý các công việc đó cũng bị suspend. | Xem breakpoint policy, runtime timeline, kiểm tra client/đồng hồ bên ngoài vẫn trôi. |
| Evaluate `toString()`/getter treo | Method đang chờ khóa/future/I/O hoặc gặp breakpoint mới; debugger chờ invocation. | Kiểm tra có method invocation, policy resume, breakpoints/conditions và lock ownership. |
| Sau Evaluate, giá trị dữ liệu hoặc thứ tự thread thay đổi | Biểu thức làm side effect hoặc debugger tạm resume thread khác. | So snapshot trước Evaluate; tắt auto-evaluate; thử lại với cách đọc field đơn giản. |

### 7.1. Timeout và retry khi pause

Giả sử request A dự kiến hoàn tất trong 200 ms. Bạn suspend nó 30 giây ở breakpoint, còn client HTTP ở **tiến trình khác** vẫn chạy. Client có thể timeout và retry. Khi Resume, JVM có thể nhận dữ liệu cũ, ghi trùng hoặc gặp kết nối đã đóng.

```text
t=0 ms       request đi vào critical section
t=40 ms      breakpoint, thread bị suspend
t=2000 ms    client ở tiến trình khác timeout
t=30000 ms   bạn Resume
t=30001 ms   ứng dụng tiếp tục với trạng thái/thế giới đã thay đổi
```

Không kết luận “logic timeout của app sai” nếu timeout chỉ xảy ra khi bạn dừng JVM lâu. Cần tái hiện với số liệu **không có debugger pause** và xem deadline ở client, service khác và bộ hẹn giờ.

Ngay cả khi `Suspend All` tạm dừng các thread trong JVM, **thời gian thực không dừng**; sau Resume, các deadline có thể đã trôi qua và nhiều timeout/callback xảy ra dồn.

### 7.2. Một thread đứng ở `BLOCKED` không nhất thiết là deadlock

Có thể quan sát `lock-waiter` ở trạng thái `BLOCKED` khi owner pause trong lab. Nếu Resume owner khiến waiter qua được ngay, đó là **tác động dự đoán được của debugger**. Deadlock trong production thường cần bằng chứng vòng chờ hoặc không thể tiến triển ngay cả khi không còn debugger dừng thread.

### 7.3. Suspend và thread dump không cung cấp cùng loại bằng chứng

- **Breakpoint:** dừng ở một location/điều kiện cụ thể và cho phép xem locals/stack tại thời điểm debug.
- **Thread dump:** snapshot stack/trạng thái thread tại thời điểm thu; có thể xác định owner/monitor đang chờ khi tool/runtime hỗ trợ.
- **JFR:** chuỗi event theo thời gian (lock contention, park, GC, socket I/O, samples) theo recording settings; không tự ghi mọi dòng thực thi.

Trong tình trạng JVM đang bị suspend mạnh, lệnh chẩn đoán ngoài như `jcmd` có thể **trả về chậm hoặc không khả dụng ngay**, tùy loại suspend và runtime. **Không tự động quy lỗi “JVM deadlock” chỉ vì công cụ chẩn đoán không phản hồi khi debugger đang pause**.

## 8. Quy trình kiểm tra khi ứng dụng “đứng” trong phiên debug

Một quy trình an toàn, có thể lặp lại:

1. **Xác nhận debugger thực sự đang pause hay không.** Xem trạng thái session và thread nào đang dừng; có breakpoint vô tình bật `Suspend All` không?
2. **Tìm dòng dừng và monitor/lock đang giữ.** Kiểm tra các frame `synchronized`, `ReentrantLock.lock`, `try/finally`, các thao tác I/O dưới khóa.
3. **Kiểm tra thread khác**: cái nào đang `BLOCKED`, `WAITING`, `TIMED_WAITING`, và chúng chờ lock/future/condition nào? Đừng suy deadlock chỉ từ tên state.
4. **Kiểm tra Evaluate đang chạy hay không**: có watch/condition/toString/getter được debugger tự gọi? Có method invocation đang chờ không?
5. **Dừng việc làm phát sinh tác dụng phụ mới**: không spam Evaluate, không liên tục bấm Step khi chưa hiểu tình trạng. Thận trọng khi dùng “Force Return”, “Drop Frame”, thay đổi biến.
6. **Khi đã có đủ dữ liệu để quan sát**, vô hiệu hóa breakpoint gây dừng hoặc đổi sang logpoint có kiểm soát; Resume theo scope phù hợp. Lưu ý số lần suspend có thể lớn hơn 1 nếu nhiều lệnh pause cùng áp dụng.
7. **Đối chiếu hành vi sau Resume**: waiter có vượt qua monitor không? Request timeout đã xảy ra ở hệ thống bên ngoài chưa?
8. **Tái hiện không có debugger** với log/JFR/metrics. Nếu vẫn có stall thì mới ưu tiên bug concurrency thực; nếu chỉ có khi pause, điều tra tác động của debugger.
9. **Nếu phải debug production**, cần thẩm quyền vận hành, giới hạn thời lượng, phạm vi và kế hoạch khôi phục rõ ràng; không dùng breakpoint nóng trên đường request có tải cao.

**Dấu hiệu hữu ích:** Sau Resume, thread chờ monitor lập tức tiến triển là bằng chứng breakpoint đã góp phần gây dừng. Tuy nhiên, nó không loại trừ các vấn đề khác; cần kiểm tra workload bình thường.

## 9. Đặt breakpoint đúng chỗ để giảm sai lệch kết quả

| Thực hành | Lợi ích | Điểm phải nhớ |
| --- | --- | --- |
| Dừng trước khi lấy lock hoặc sau khi nhả lock | Tránh cố tình giữ critical section lâu khi đọc biến. | Có thể không quan sát được trạng thái **bên trong** critical section; dùng snapshot/log thích hợp. |
| Ưu tiên **Suspend Thread** khi chỉ cần một worker và không cần trạng thái toàn JVM | Giảm phạm vi pause trực tiếp. | Nếu worker nắm khóa chung, tác động vẫn lan rộng. |
| Dùng logpoint có giới hạn/throttle trên hot path | Giảm dừng dịch vụ. | Logpoint vẫn có overhead và side effects của biểu thức. |
| Giới hạn condition bằng kiểm tra trường đơn giản | Ít hành vi phụ và ít call hơn. | Ngay cả đọc field cũng là snapshot đang biến đổi; thread khác có thể thay đổi state. |
| Tắt tự gọi `toString`/getter khi không tin cậy | Tránh Evaluate ngoài ý muốn. | IDE khác nhau có tên setting khác nhau. |
| Sử dụng JFR, logs, metrics thay cho breakpoint trên production | Có thể quan sát lâu hơn với tác động thấp hơn khi cấu hình đúng. | Vẫn có overhead, threshold và giới hạn lấy mẫu. |
| Dùng môi trường staging và dữ liệu không nhạy cảm | Có thể tạm dừng và thử side effects an toàn hơn. | Concurrency/tải có thể khác production. |

### Bảo mật JDWP

Cổng JDWP cho debugger quyền truy cập rất mạnh tới trạng thái và thực thi trong JVM. Không mở cổng debug ra Internet hoặc network không tin cậy, vì nó có thể cho phép đọc dữ liệu nhạy cảm và điều khiển thực thi trong ứng dụng.

Trong bài lab dùng:

```text
address=127.0.0.1:5005
```

để giới hạn trên loopback. Khi cần debug JVM ở máy từ xa, dùng đường kết nối bảo mật/được kiểm soát (ví dụ tunnel được phê duyệt), chính sách mạng và xác thực ở lớp hạ tầng; không mặc định JDWP tự bảo vệ bằng cơ chế xác thực đủ mạnh. **Không tự thêm `address=*:5005` trên production** vì nó mở cổng lắng nghe trên tất cả interface khi server hỗ trợ cú pháp đó.

Khi xong, dừng session debug an toàn và kiểm tra app đã được resume; không để debugger/port bật lâu hơn cần thiết.

## 10. Các nhận định sai thường gặp

| Nhận định sai | Giải thích đúng |
| --- | --- |
| “Suspend Thread thì thread khác chắc chắn không bị ảnh hưởng.” | Thread khác vẫn có thể chờ khóa, latch, queue hoặc dữ liệu do thread bị suspend đang giữ/điều phối. |
| “Pause sẽ nhả tất cả monitor.” | Debugger suspend **không** thực thi `monitorexit` hay `unlock()` thay ứng dụng. |
| “`sleep()` trong `synchronized` làm monitor trống.” | `Thread.sleep()` không nhả monitor. |
| “`Object.wait()` giống debugger suspend.” | `Object.wait()` hợp lệ tạm nhả monitor tương ứng, debugger suspend không làm như vậy. |
| “Có `BLOCKED` nghĩa là Java bị deadlock.” | Có thể chỉ là chờ owner đang pause; phải xem owner/chu trình chờ và Resume. |
| “Không có thread BLOCKED tức là không có lock contention.” | `ReentrantLock` hoặc các primitive khác có thể dùng park, dẫn đến `WAITING/TIMED_WAITING`. |
| “Evaluate chỉ tính toán trên UI của IDE.” | Method trong biểu thức có thể chạy thực trong **JVM debuggee**. |
| “`toString()` và getter chắc chắn không làm thay đổi dữ liệu.” | Chúng có thể lazy-init, lock, I/O, ghi cache, throw hoặc recurse. |
| “Khi Suspend All thì không thread nào chạy khi Evaluate.” | JDI method invocation mặc định có thể tạm resume các thread khác; phụ thuộc flags/IDE. |
| “Chỉ bật single-threaded evaluation luôn an toàn hơn.” | Nó có thể làm invoked method deadlock vì thread giữ lock/đánh thức đang bị suspend. |
| “Step Over bỏ qua tác dụng phụ của method.” | Nó vẫn **chạy** method; chỉ khác cách debugger chọn điểm dừng tiếp theo. |
| “Timeout trong lúc pause chứng minh network hoặc code có vấn đề.” | Đồng hồ/remote client vẫn hoạt động; pause có thể tự tạo timeout. |
| “Breakpoint không suspend không có overhead.” | Vẫn có thể phải gửi event, kiểm tra condition, format log và invoke method. |
| “Detach luôn lập tức sửa mọi treo.” | Phải xem suspend count, method invocation đang kẹt, trạng thái thực và cách IDE detach; không bảo đảm hết stall. |

## 11. Bài tập suy luận

### Tình huống A: gián đoạn vì monitor

`lock-owner` bị suspend tại `int seen = EVENTS.get()` khi vẫn giữ `LOCK`. `lock-waiter` chờ đi vào `synchronized (LOCK)`.

**Hỏi:** `Suspend Thread` có giúp waiter hoàn tất trước khi owner Resume không?

**Trả lời:** Không, vì owner vẫn sở hữu monitor. Waiter không bị suspend trực tiếp nhưng có thể `BLOCKED` chờ monitor cho tới khi owner đi tiếp và nhả khóa.

### Tình huống B: Evaluate thay đổi output

Ở checkpoint, Evaluate `DebugSuspendLab.changeEvents()` đúng một lần.

**Hỏi:** Sau Resume, counter cuối có thể thay đổi như thế nào?

**Trả lời:** Khi không có tác động khác và method chỉ chạy đúng một lần, `EVENTS` tăng do Evaluate, rồi tăng lần nữa trong owner: kết quả cuối có thể là `2` thay vì `1`. Không nên coi số liệu sau Evaluate như ảnh chụp của trạng thái ban đầu.

### Tình huống C: gọi getter bị treo

Debugger dừng thread A và khi render object lại gọi một getter cần lock do thread B đang nắm. B cũng đang suspend.

**Hỏi:** Vì sao Evaluate có thể treo và `INVOKE_SINGLE_THREADED` có thể làm tình hình tệ hơn?

**Trả lời:** Method được gọi thật, phải chờ lock; B không được resume để nhả lock. Chế độ single-threaded chỉ resume thread invoke, không đảm bảo có tiến triển của thread sở hữu lock.

### Tình huống D: pause kéo dài trên production

Bạn Suspend All 20 giây trong request, client timeout sau 3 giây. Resume và thấy exception hoặc retry.

**Hỏi:** Có thể kết luận root cause là network không?

**Trả lời:** Không. Cần tái hiện không pause, đối chiếu timeout deadline, log/trace và I/O thật. Breakpoint là một biến can thiệp vào thí nghiệm.

### Tình huống E: breakpoint không có pause

Bạn thay breakpoint bằng logpoint nhưng condition gọi `cache.computeIfAbsent(key, ...)`.

**Hỏi:** Có an toàn tuyệt đối không?

**Trả lời:** Không. Method có thể cập nhật cache, cấp phát, lock hoặc gọi code tạo value, dù debugger không suspend thread. Dùng điều kiện đọc field/giá trị rẻ và hạn chế số event.

## 12. Checklist trước và trong khi debug Java đa luồng

- [ ] Xác định đúng JVM, build/source và loại breakpoint.
- [ ] Kiểm tra chính sách **Suspend All / Thread / None**, không nhầm với `suspend=y` khi startup.
- [ ] Xem breakpoint có nằm **trong critical section** hoặc khi thread đang giữ `ReentrantLock` không.
- [ ] Tìm **owner của lock** trước khi coi thread `BLOCKED` là lỗi logic.
- [ ] Kiểm tra `Thread.State`: `BLOCKED` cho intrinsic monitor; `WAITING/TIMED_WAITING` có thể đến từ park/condition; `RUNNABLE` không nhất thiết đang sử dụng CPU.
- [ ] Không đánh giá method/`toString()`/getter chưa hiểu tác dụng phụ, đặc biệt trong runtime có locks.
- [ ] Nếu buộc Evaluate, lưu ý JDI có thể **resume thread khác**, hoặc single-threaded invocation có thể **deadlock**.
- [ ] Không dùng thời lượng pause do debugger để tính latency thực của chương trình.
- [ ] Dùng Resume/disable breakpoint theo scope đúng và xác minh worker/lock đã tiến triển.
- [ ] Tái hiện ngoài debugger khi cần kết luận về deadlock hoặc bottleneck thực tế.
- [ ] Bảo vệ cổng JDWP, dữ liệu trong debugger và kế hoạch khôi phục dịch vụ.

## Tài liệu tham khảo

- [Oracle Java SE 21 — `EventRequest` (`SUSPEND_ALL`, `SUSPEND_EVENT_THREAD`, `SUSPEND_NONE`)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/request/EventRequest.html).
- [Oracle Java SE 21 — `ThreadReference.suspend()` và nguy cơ deadlock khi thread giữ monitor](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/ThreadReference.html).
- [Oracle Java SE 21 — `ObjectReference.invokeMethod`, resume behavior và `INVOKE_SINGLE_THREADED`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/ObjectReference.html).
- [Oracle Java SE 21 — JPDA Connection and Invocation Details, các option JDWP](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html).
- [Oracle Java SE 21 — `java` command, `-agentlib:jdwp`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Java Language Specification §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html).

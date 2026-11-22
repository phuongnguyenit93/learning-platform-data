# Khái niệm thread-local handshake trong HotSpot

**Chủ đề:** Handshake theo luồng — Java 10 trở lên.

**Thread-local handshake** là một cơ chế **nội bộ của HotSpot JVM** cho phép JVM yêu cầu một thao tác ngắn, an toàn đối với **một JavaThread cụ thể** (hoặc một nhóm/những JavaThread được chọn) mà **không nhất thiết phải đưa tất cả JavaThread vào một global safepoint**. Cơ chế này được giới thiệu trong **Java 10 — JEP 312: Thread-Local Handshakes**. Nó vẫn hiện diện trong mã nguồn HotSpot hiện đại và là một thành phần hạ tầng để giảm sự phụ thuộc vào các lần dừng toàn JVM cho công việc chỉ liên quan một hoặc một số thread.

**Ý chính cần nhớ:** *global safepoint* phối hợp trạng thái an toàn trên toàn bộ tập JavaThread liên quan; *thread-local handshake* phối hợp hoạt động tại **mức từng thread**. Khi chỉ có một thread cần được xử lý, các thread khác **không phải mặc định cùng dừng chờ** vì chính handshake đó. Tuy nhiên, điều này **không có nghĩa HotSpot đã loại bỏ mọi global safepoint**, không cam kết “không bao giờ có pause”, và cũng không có nghĩa callback chạy tại thời điểm tùy ý bất chấp điều kiện an toàn.

Bài phân tích động cơ, cơ chế polling, callback và trạng thái handshake-safe, điểm khác với safepoint, các giới hạn thực tế, ý nghĩa với GC/diagnostics, và cách quan sát bằng công cụ được hỗ trợ. Kèm **bốn chương trình Java độc lập** biên dịch/chạy được ở mức `javac --release 10`, với kết quả đã kiểm chứng trên **OpenJDK HotSpot 24.0.2**. Các ví dụ Java công khai chỉ minh họa thao tác **quan sát hoặc điều khiển thread ở tầng ứng dụng**; **không giả vờ rằng Java standard library có API công khai để tự tạo một `HandshakeClosure` của HotSpot**.

## 1. Vì sao JVM cần một cơ chế handshake theo từng thread?

HotSpot cần biết trạng thái một JavaThread ở những thời điểm thích hợp để thực hiện các tác vụ nội bộ. Ví dụ, JVM có thể cần đọc hoặc cập nhật metadata liên quan stack/thread, tiến hành một số hình thức deoptimization hay hỗ trợ các thao tác quản lý bộ nhớ và công cụ quan sát. Các thao tác đó không phải lúc nào cũng an toàn nếu được thực hiện **bất kỳ lúc nào** khi thread đang chạy mã biên dịch hay giữ các giá trị tạm trong thanh ghi.

Một cách truyền thống là yêu cầu các JavaThread đạt **global safepoint**, khi JVM biết trạng thái đủ ổn định để thực hiện công việc cần phối hợp toàn cục. Nhưng nếu tác vụ chỉ liên quan **thread A**, bắt cả **A, B, C, D** cùng dừng có thể gây phạm vi gián đoạn lớn không cần thiết.

~~~text
BỐI CẢNH: Có ba JavaThread đang chạy

   Thread A: xử lý request 1
   Thread B: xử lý request 2
   Thread C: xử lý request 3

             YÊU CẦU CÔNG VIỆC CHỈ LIÊN QUAN A
                              |
                   Trước đây thường cần
                   cơ chế dừng toàn VM
                              v
GLOBAL SAFEPOINT:
   A ---- [đợi và tham gia safepoint] ---->
   B ---- [đợi và tham gia safepoint] ---->
   C ---- [đợi và tham gia safepoint] ---->
             JVM làm tác vụ cần thiết
             rồi cho các luồng tiếp tục

THREAD-LOCAL HANDSHAKE:
   A ---- [điểm an toàn][callback cho A] ---->
   B --------------------------------------->  tiếp tục chạy
   C --------------------------------------->  tiếp tục chạy
~~~

Sơ đồ trên minh họa sự khác nhau về **phạm vi phối hợp**; không khẳng định các thread thực tế luôn chạy song song hoặc một handshake luôn mất thời gian bằng 0. Thread B/C vẫn có thể chịu tác động từ CPU scheduling, GC hoặc các cơ chế khác độc lập với handshake đang xét.

### Mục tiêu của JEP 312

- Cho phép JVM thực hiện một **callback nội bộ** ở trạng thái an toàn cho thread được chọn.
- Làm cho việc xử lý riêng một thread trở nên khả thi mà **không cần yêu cầu global VM safepoint chỉ vì tác vụ đó**.
- Tạo nền tảng để các subsystem HotSpot có thể chuyển một số công việc **từ phối hợp tất cả thread sang phối hợp đúng các thread cần thiết**.
- Hỗ trợ cải thiện độ trễ và khả năng mở rộng trong những tình huống việc dừng toàn cục là thừa.
- Vẫn giữ đúng các bất biến an toàn của JVM khi quan sát/sửa trạng thái thread.

**Không phải mục tiêu:** thay toàn bộ GC, thay thế Java `Thread`, bảo đảm không có stop-the-world pause, hoặc tạo ra API lập trình Java mới cho ứng dụng tự chọn callback VM nội bộ.

## 2. Trước hết phải hiểu “safepoint”

**Safepoint** trong HotSpot là khái niệm nội bộ: JVM có thể đưa thread đến **trạng thái mà dữ liệu liên quan đủ xác định/an toàn** để thực hiện những hoạt động nhất định. Nó **không đồng nghĩa** với một dòng source Java cụ thể, cũng không đồng nghĩa với giá trị `Thread.State.WAITING` hay `Thread.State.BLOCKED` được nhìn thấy ở ứng dụng.

Trong luồng thực thi mã Java:

- JVM/JIT đặt **safepoint polls** ở các vị trí phù hợp của chương trình được diễn dịch hoặc mã máy đã biên dịch.
- Khi không có yêu cầu, các lần poll cần có đường xử lý nhanh để giảm overhead.
- Khi có yêu cầu handshake/safepoint, trạng thái poll tương ứng có thể được đánh dấu (*armed*) để thread xử lý yêu cầu khi đạt vị trí an toàn.
- Trạng thái thread và chuyển tiếp vào/ra Java, native/JVM code cũng liên quan đến việc xác định khi nào thao tác an toàn.
- Nếu thread đang ở một trạng thái không phù hợp, JVM **không thực hiện callback một cách tùy tiện** lên các thanh ghi/stack thiếu ổn định; nó phải phối hợp đến trạng thái được phép.

**Điểm phân biệt:** `Thread.sleep(...)`, `Thread.yield()` hoặc `Thread.interrupt()` **không phải** lời gọi API để “thực thi handshake của HotSpot”. Đây là các hành vi Java công khai với hợp đồng riêng. Ngược lại, safepoint poll là cơ chế do VM/JIT quản lý, không cần programmer đặt một lệnh `sleep()` thủ công trong vòng lặp.

### Global safepoint

Với một **global safepoint**, HotSpot yêu cầu những JavaThread liên quan chuyển sang trạng thái phù hợp để JVM tiến hành một hoạt động có phạm vi toàn VM. Những thread đang thực thi Java cần phối hợp; những thread ở trạng thái đã an toàn như blocked/native có cơ chế xử lý tương ứng. Khi điều kiện toàn cục đạt, JVM có thể tiến hành tác vụ cần một điểm nhìn nhất quán rộng hơn.

Ví dụ một số GC phase hoặc hoạt động quản lý runtime vẫn có thể yêu cầu global synchronization. **JEP 312 không phải tuyên bố từ Java 10 trở đi mọi GC đều hoàn toàn concurrent.**

### Thread-local handshake

Với một **thread-local handshake**, yêu cầu được gắn với **target JavaThread**. Callback chạy khi JVM có điều kiện an toàn cho target. Không cần chờ *tất cả* JavaThread cùng tới một global safepoint nếu công việc không yêu cầu điều đó.

Hiệu quả phụ thuộc: chính sách callback, trạng thái target, tiến độ polling, CPU scheduling và các synchronization khác trong JVM. **Không có bảo đảm rằng mọi handshake hoàn thành ngay lập tức**.

## 3. Quy trình khái niệm của một handshake

Phân tích theo từng giai đoạn:

1. **JVM subsystem phát sinh yêu cầu:** một thành phần HotSpot cần thao tác trên thread A (ví dụ kiểm tra/thao tác trạng thái liên quan thread).
2. **Chọn đối tượng mục tiêu:** request có thể nhắm **một JavaThread** hoặc được áp dụng cho một tập JavaThread; không nhất thiết là tất cả trong một lần dừng toàn VM.
3. **Ghi nhận thao tác chờ:** HotSpot lưu yêu cầu/closure vào trạng thái handshake liên quan target. Cấu trúc cụ thể thay đổi theo phiên bản.
4. **Báo tín hiệu cho target qua polling mechanism:** cơ chế thread-local polling cho phép thread nhận ra có việc JVM cần xử lý tại vị trí thích hợp.
5. **Đạt trạng thái handshake-safe:** target tự tới điểm hợp lệ hoặc JVM thấy trạng thái của target phù hợp để xử lý thay.
6. **Thực hiện callback:** tùy loại closure, callback có thể chạy **trên target thread**, hoặc do **thread khởi tạo/VMThread** thực hiện trong khi giữ target ở trạng thái bị chặn an toàn.
7. **Hoàn tất/phát tín hiệu:** trạng thái handshake được giải quyết theo hợp đồng của thao tác; target có thể tiếp tục thực thi công việc ứng dụng khi phù hợp.

~~~text
HotSpot component cần kiểm tra thread A
                  |
                  v
       Gắn handshake operation
                  |
                  v
  Thread-local poll / trạng thái A
                  |
             A đã safe?
              /       \
            Có         Chưa
             |           |
             |       Đợi A chuyển
             |       đến trạng thái
             |       handshake-safe
             |           |
             +-----+-----+
                   v
           Callback cho A
            (do A hoặc
         handshaker khác,
        tùy loại operation)
                   |
                   v
             Hoàn tất A
                   |
                   v
        A tiếp tục làm việc

Thread B/C không bắt buộc bị dừng chỉ vì thao tác của A.
~~~

**Đây là sơ đồ giải thích, không phải mã thuật toán hoàn chỉnh.** Các bản OpenJDK mới có thêm mô hình queue, handshake asynchronous, coordination với virtual threads/continuations hoặc các invariant mới. Không nên chép một bản pseudo-code Java 10 và tuyên bố nó mô tả chính xác mọi dòng mã HotSpot của JDK hiện đại.

## 4. Ai thực thi callback?

Một hiểu nhầm thường gặp:

> “Thread-local handshake nghĩa là target Java thread phải luôn tự chạy callback.”

**Không chính xác.** Theo mã nguồn `src/hotspot/share/runtime/handshake.hpp` của OpenJDK hiện đại, `HandshakeClosure` được thực thi đối với `JavaThread` khi target ở **safepoint/handshake-safe state**. Tùy bản chất closure, callback có thể được thực thi **bởi target thread, thread khởi xướng, hoặc VMThread**. Nếu không phải chính target chạy callback, target được giữ **blocked** cho đến khi callback xong.

Do đó, cụm từ **thread-local** nhấn mạnh **đối tượng cần phối hợp**, không cam kết **CPU thread thực sự đang chạy callback** luôn là target.

Các khái niệm nên phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Target / handshakee** | `JavaThread` mà thao tác có liên quan và trạng thái phải an toàn |
| **Initiator / handshaker** | Thành phần/thread yêu cầu và có thể xử lý handshake tùy loại closure |
| **`HandshakeClosure`** | Callback **nội bộ HotSpot** mô tả công việc cho target |
| **Handshake-safe state** | Trạng thái phù hợp để callback thao tác mà không vi phạm invariants của JVM |
| **Thread-local polling** | Cơ chế từng thread kiểm tra có yêu cầu handshake/safepoint hay không |
| **Synchronous/asynchronous operation** | Mô hình phối hợp/lifecycle của handshake phụ thuộc implementation; không nên mặc định mọi thao tác cùng một kiểu blocking |

**Không đồng nhất `HandshakeClosure` (C++/HotSpot internal) với `java.util.function.Consumer<Thread>`, `Runnable` hoặc `Callable` của Java standard library.** Đó là các interface ở lớp lập trình ứng dụng, không phải API đưa callback vào hàng đợi handshake của VM.

### Một request “tất cả thread” vẫn có thể là nhiều handshake riêng

Một subsystem có thể muốn thao tác trên nhiều thread. HotSpot có cơ chế phối hợp trên toàn bộ tập target bằng các operation mức từng thread. Tuy vậy, điều này **không tự biến thành global safepoint** theo nghĩa buộc tất cả thread dừng tại cùng một ranh giới thời gian.

**Global safepoint** có yêu cầu về tính đồng thời của trạng thái toàn VM khi cần. **All-thread handshakes** có thể để từng thread xử lý xong rồi tiếp tục khi thích hợp. Hai dạng **không thay thế mọi lúc** vì hợp đồng nhất quán của tác vụ có thể khác nhau.

## 5. Vì sao cần polling theo luồng?

Nếu mọi JavaThread dùng một cờ hoặc một polling page toàn cục, VM dễ báo “mọi người hãy kiểm tra yêu cầu dừng”. Nhưng yêu cầu chỉ nhắm A thì muốn **A phản ứng mà B/C không tự nhận cùng một yêu cầu**.

JEP 312 bổ sung hạ tầng **thread-local polling**: HotSpot có thể đánh dấu yêu cầu phù hợp cho **từng JavaThread**. Khi mã thực thi ở các điểm poll đã được biên dịch/diễn dịch, JVM có thể chuyển quyền điều khiển đến logic xử lý handshake/safepoint.

Ở một số HotSpot version/kiến trúc, cơ chế dùng **protected polling pages** hoặc các giá trị địa chỉ/generation flags phù hợp. Không nên quy mọi implementation về đúng **một instruction assembly** hoặc đúng **một mô hình page**: tối ưu và cơ chế an toàn có thể thay đổi theo phiên bản JVM, kiến trúc CPU và loại code.

### Tại sao không kiểm tra mọi lệnh máy?

- Poll có chi phí, dù đường không có yêu cầu đã được tối ưu.
- JVM cần một trạng thái mà stack/register/object references có thể được diễn giải chính xác.
- Đặt poll ở các vị trí đã được compiler/VM xác định mang lại sự cân bằng giữa độ trễ phản hồi và overhead.
- Thao tác nội bộ không được ép thread chuyển sang trạng thái tùy tiện có thể phá invariant runtime.

Khi thread đang chạy native code hoặc ở một bước chuyển trạng thái, HotSpot có quy tắc xử lý riêng để bảo đảm hành động của VM là hợp lệ. Điều này lý giải tại sao **không thể dự đoán chắc latency của handshake chỉ từ số JavaThread**.

## 6. Không có public Java API “bắt tay HotSpot một thread”

**Trong Java standard library không có phương thức dạng `HotSpot.handshake(Thread, Runnable)` dành cho ứng dụng.** JEP 312 là tính năng **VM-internal**, phục vụ triển khai JVM và các subsystem liên quan.

Những API quen thuộc sau **không phải** handshake API:

| API Java công khai | Công việc thật | Vì sao không phải HotSpot handshake? |
| --- | --- | --- |
| `ThreadLocal<T>` | Mỗi thread truy cập giá trị riêng của nó | Là **cơ chế lưu biến theo thread**, không phải callback VM |
| `Thread.interrupt()` | Gửi yêu cầu interrupt theo hợp đồng Java | Tương tác với interrupt flag và các thao tác blocking, không là callback handshake |
| `Thread.yield()` | Gợi ý cho scheduler | Không yêu cầu thread chuyển đến một handshake-safe point |
| `Thread.sleep(...)` | Tạm chờ theo thời gian | Không tạo một yêu cầu VM-internal handshake |
| `Thread.join()` | Chờ thread hoàn thành | Không phải cơ chế xử lý callback ở VM safepoint |
| `ThreadMXBean.getThreadInfo(id)` | Lấy thông tin thread qua management API | **API quan sát**, không công bố hợp đồng “đã dùng handshake” |
| `Thread.getStackTrace()` | Lấy stack trace quan sát được | Không được dùng làm bằng chứng một handshake cụ thể đã xảy ra |
| `Thread.getAllStackTraces()` | Lấy snapshot nhiều thread | Không có cam kết về loại đồng bộ nội bộ VM được dùng |

Có thể một API quan sát được HotSpot triển khai **bằng một số cơ chế handshake trong một JDK cụ thể**, nhưng đó là **chi tiết implementation**. Mã ứng dụng **không được coi Java API này là lệnh gọi trực tiếp tới `Handshake::execute`** hoặc tuyên bố snapshot của nó chắc chắn không tạo global safepoint.

**Quan trọng:** `ThreadLocal` và *thread-local handshake* chỉ tình cờ cùng có cụm từ “thread-local”. Một cái là **kho lưu giá trị theo thread** ở Java; cái kia là **giao thức phối hợp VM để xử lý một JavaThread ở trạng thái an toàn**.

## 7. Chương trình chạy được 1 — Quan sát đúng một thread

Để tìm hiểu ngữ cảnh “xử lý một thread”, có thể dùng Java Management API để **quan sát một thread theo ID**. Đoạn dưới **không phải implementation handshake**; nó chỉ thể hiện việc Java cho phép target một thread riêng để lấy thông tin.

Lưu file **`TargetedThreadInfoDemo.java`**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class TargetedThreadInfoDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread target = new Thread(() -> {
            ready.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "target-worker");
        target.start();
        ready.await();

        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        ThreadInfo info = bean.getThreadInfo(target.getId(), 32);

        System.out.println("target-found=" + (info != null));
        System.out.println("target-name=" + info.getThreadName());
        System.out.println("id-matches=" +
                (info.getThreadId() == target.getId()));
        System.out.println("stack-nonempty=" +
                (info.getStackTrace().length > 0));

        AtomicInteger otherWork = new AtomicInteger();
        Thread other = new Thread(otherWork::incrementAndGet,
                "other-worker");
        other.start();
        other.join();
        System.out.println("other-work-completed=" +
                (otherWork.get() == 1));

        release.countDown();
        target.join();
        System.out.println("target-terminated=" + !target.isAlive());
    }
}
~~~

Lệnh:

~~~bash
javac --release 10 TargetedThreadInfoDemo.java
java TargetedThreadInfoDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
target-found=true
target-name=target-worker
id-matches=true
stack-nonempty=true
other-work-completed=true
target-terminated=true
~~~

**Giải thích đúng phạm vi:**

1. `CountDownLatch` giữ `target-worker` còn sống để tránh race “thread đã kết thúc trước khi đọc thông tin”.
2. `getThreadInfo(target.getId(), 32)` yêu cầu thông tin **một thread theo ID** và tối đa 32 stack frames; nó không phải API yêu cầu HotSpot handshake.
3. `stack-nonempty=true` chỉ nói rằng management API trả được stack trong lần quan sát.
4. `other-work-completed=true` cho thấy một thread khác hoàn tất công việc trong chương trình demo, **không chứng minh trong toàn bộ khoảng lấy snapshot tuyệt đối không có global safepoint**.
5. `CountDownLatch` là cơ chế đồng bộ Java ứng dụng; nó **khác** polling/safepoint handshake của VM.
6. Không dùng `Thread.State` để suy ra một JavaThread đang ở internal `handshake-safe state`; hai mô hình trạng thái không giống nhau.

Ví dụ có tính ứng dụng trong công cụ diagnostics, nhưng đừng dùng nó để suy ra **lịch trình callback C++ chính xác bên trong HotSpot**.

## 8. Chương trình chạy được 2 — `ThreadLocal` hoàn toàn khác

Lưu file **`ThreadLocalContrastDemo.java`**:

~~~java
public class ThreadLocalContrastDemo {
    public static void main(String[] args) throws Exception {
        ThreadLocal<String> storage =
                ThreadLocal.withInitial(() -> "default");
        String[] result = new String[2];

        Thread one = new Thread(() -> {
            storage.set("one");
            result[0] = storage.get();
            storage.remove();
        }, "one");

        Thread two = new Thread(() -> {
            storage.set("two");
            result[1] = storage.get();
            storage.remove();
        }, "two");

        one.start();
        two.start();
        one.join();
        two.join();

        System.out.println("thread-one=" + result[0]);
        System.out.println("thread-two=" + result[1]);
        System.out.println("main-value=" + storage.get());
        System.out.println("isolated=" +
                !result[0].equals(result[1]));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 ThreadLocalContrastDemo.java
java ThreadLocalContrastDemo
~~~

**Stdout:**

~~~text
thread-one=one
thread-two=two
main-value=default
isolated=true
~~~

`ThreadLocal` cấp một giá trị khác nhau cho mỗi thread và `remove()` xóa giá trị của chính thread gọi nó. Đó là **Java API cho dữ liệu gắn với thread**. Không có lời gọi nào ở chương trình trên yêu cầu callback nội bộ `HandshakeClosure`. Vì vậy không nên dùng cụm từ “thread-local handshake” để chỉ `ThreadLocal.set/get/remove`.

Với các ứng dụng hiện đại dùng **virtual threads** (được chuẩn hóa từ Java 21), việc sử dụng `ThreadLocal` cũng phải xét đặc điểm vòng đời và chi phí riêng; điều này **không biến ThreadLocal thành handshake VM**.

## 9. Chương trình chạy được 3 — `interrupt()` không phải handshake

Một người mới học có thể nghĩ rằng vì `Thread.interrupt()` nhắm một thread, nó tương đương với handshake theo luồng. Không phải vậy.

Lưu file **`InterruptContrastDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptContrastDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch blocker = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean(false);

        Thread waiting = new Thread(() -> {
            ready.countDown();
            try {
                blocker.await();
            } catch (InterruptedException e) {
                caught.set(true);
                Thread.currentThread().interrupt();
            }
        }, "interrupt-target");

        waiting.start();
        ready.await();
        waiting.interrupt();
        waiting.join();

        System.out.println("interrupt-observed=" + caught.get());
        System.out.println("interrupted-flag-restored=" +
                waiting.isInterrupted());
        System.out.println("thread-terminated=" +
                !waiting.isAlive());
    }
}
~~~

Chạy:

~~~bash
javac --release 10 InterruptContrastDemo.java
java InterruptContrastDemo
~~~

**Stdout chính xác:**

~~~text
interrupt-observed=true
interrupted-flag-restored=true
thread-terminated=true
~~~

Tại đây, `interrupt` tác động đến trạng thái gián đoạn theo **hợp đồng Java**, làm `CountDownLatch.await()` ném `InterruptedException`. Code `catch` chủ động đặt lại interrupt flag để bảo tồn tín hiệu. Đó là **đồng bộ/lifecycle ở tầng ứng dụng**, không phải VM-internal callback ở một handshake-safe state.

Bài học tổng quát: **“thao tác chỉ nhắm một thread” không đồng nghĩa “thread-local handshake”**. Cần phân biệt ngữ nghĩa của API mà application thực sự gọi.

## 10. Quan sát HotSpot bằng unified logging

HotSpot có hệ thống **Unified JVM Logging**. Bạn có thể hỏi JVM hiện tại những **log tags** nào được hỗ trợ thay vì đoán dựa trên bài blog cũ:

~~~bash
java -Xlog:help
~~~

Trong **HotSpot OpenJDK 24.0.2** dùng để kiểm thử bài, danh sách có cả tag `handshake` lẫn `safepoint`. Có thể chạy một chương trình với cấu hình log mang tính chẩn đoán:

~~~bash
java -Xlog:handshake=debug -cp . TargetedThreadInfoDemo
~~~

Hoặc cho JVM ghi dữ liệu của các tag vào file:

~~~bash
java -Xlog:handshake*=debug,safepoint*=info:file=vm-events.log:uptime,level,tags -cp . TargetedThreadInfoDemo
~~~

**Giới hạn quan trọng:**

- Được launcher chấp nhận tag `handshake` **không có nghĩa** mọi lần chạy sẽ có dòng log handshake.
- Một chương trình chạy quá ngắn, không phát sinh handshake nào được ghi ở mức log chọn, hoặc một VM thay đổi logging internals có thể **không in gì ngoài stdout ứng dụng**.
- **Không thấy log handshake không chứng minh rằng HotSpot không hỗ trợ handshake** hoặc VM chưa từng xử lý handshake.
- Có log handshake cũng **không mặc nhiên chứng minh** một API Java công khai cụ thể dùng handshake thay global safepoint; cần đọc ngữ cảnh operation và mã nguồn phiên bản VM đang phân tích.
- `-Xlog:safepoint=info` quan sát các log thuộc phạm vi safepoint theo implementation; đừng lấy số dòng log để suy ra tuyệt đối “mọi pause” của JVM.
- Log debug/trace có overhead; chỉ bật đủ mức cần thiết trong môi trường chẩn đoán, không dùng kết quả startup với logging nặng làm benchmark mặc định.

**Một test ổn định nên kiểm tra khả năng nhận log tag và hành vi Java; không khẳng định một bộ log handshake bắt buộc phải có số dòng cố định.**

### Chương trình chạy được 4 — Kiểm tra tag theo JVM đang chạy

Lưu file **`HotSpotLogCapabilityDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Paths;
import java.util.Locale;

public class HotSpotLogCapabilityDemo {
    public static void main(String[] args) throws Exception {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win");
        String javaExecutable = Paths.get(
                System.getProperty("java.home"),
                "bin", windows ? "java.exe" : "java").toString();

        Process process = new ProcessBuilder(
                javaExecutable, "-Xlog:help")
                .redirectErrorStream(true)
                .start();

        ByteArrayOutputStream captured = new ByteArrayOutputStream();
        try (InputStream input = process.getInputStream()) {
            byte[] buffer = new byte[4096];
            int n;
            while ((n = input.read(buffer)) != -1) {
                captured.write(buffer, 0, n);
            }
        }

        int code = process.waitFor();
        String output = new String(
                captured.toByteArray(), StandardCharsets.UTF_8);

        System.out.println("java-feature-at-least-10=" +
                (Runtime.version().feature() >= 10));
        System.out.println("xlog-help-exit-zero=" + (code == 0));
        System.out.println("handshake-tag-listed=" +
                output.matches("(?s).*\\bhandshake\\b.*"));
        System.out.println("safepoint-tag-listed=" +
                output.matches("(?s).*\\bsafepoint\\b.*"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 10 HotSpotLogCapabilityDemo.java
java HotSpotLogCapabilityDemo
~~~

**Stdout trên HotSpot 24.0.2:**

~~~text
java-feature-at-least-10=true
xlog-help-exit-zero=true
handshake-tag-listed=true
safepoint-tag-listed=true
~~~

**Hạn chế:** chương trình kiểm tra **sự tồn tại của tag logging trong VM cụ thể**, không kích hoạt một `HandshakeClosure` và không xác minh handshake đã diễn ra. Với một JVM implementation khác HotSpot hoặc phiên bản không có tag, kết quả có thể khác. `-Xlog:help` là công cụ vendor/VM-specific nên kiểm tra exit code trước khi dựa vào log.

Chương trình đọc output từ JVM con bằng `ProcessBuilder`; trong ứng dụng production, cần lưu ý timeout/giới hạn output khi chạy một command bên ngoài. Đây là một tool demo nhỏ, không phải bộ giám sát process hoàn chỉnh.

## 11. Một phép kiểm tra ứng dụng không phải bằng chứng cho HotSpot internals

Khi người dùng báo “đọc stack của một thread làm các request khác bị pause”, cần đặt đúng các câu hỏi:

1. **Ứng dụng gọi API nào?** `ThreadMXBean`, `Thread.getStackTrace`, JVMTI qua profiler, hay một diagnostic command?
2. **JDK/vendor/GC nào đang chạy?** Code VM, safepoint/handshake policy và profiler implementation có thể khác.
3. **Có thread-local handshake không?** Nếu có, callback nào và nhắm đối tượng nào? Cần log/source/diagnostics phù hợp.
4. **Có global safepoint không?** Cần quan sát các event safepoint riêng và sự liên quan theo thời điểm.
5. **Các thread khác chậm do gì?** CPU contention, lock contention, GC, I/O, OS scheduling và safepoint đều có thể gây độ trễ.
6. **Có bản ghi nào xác nhận nguyên nhân?** Chỉ nhìn hai thời điểm log của request không đủ để buộc tội một handshake.
7. **Có benchmark với cấu hình đồng nhất không?** Đừng so một JVM debug/log trace với JVM production ít logging rồi quy chênh lệch cho handshake.

Dùng **JFR**, `jcmd`, Java Flight Recorder events liên quan, log safepoint hoặc thread dump có thể giúp điều tra theo **bản JDK cụ thể**. Nhưng **một câu lệnh tạo thread dump không tự động chứng minh đường triển khai của VM luôn là handshake**.

Ví dụ nếu JVM hỗ trợ lệnh:

~~~bash
jcmd <pid> Thread.print
~~~

Đây là **câu lệnh minh họa**, thay `<pid>` bằng PID thực tế của tiến trình Java. Đầu ra cho biết các thread và stack/state để chẩn đoán. Nó **không phải API để phát lệnh C++ `Handshake::execute` tùy ý**, và việc JVM thực hiện thread dump có thể phụ thuộc cơ chế/safepoint khác nhau theo phiên bản.

## 12. Ứng dụng của handshake trong HotSpot hiện đại

Thread-local handshake là **hạ tầng VM**. Các subsystem có thể dùng nó để xử lý một phần công việc liên quan từng thread mà không bắt buộc mọi JavaThread dừng đồng thời. Ví dụ phạm vi có thể gồm:

- **Phân tích/đọc trạng thái thread và stack** cho những hoạt động nội bộ cần state an toàn.
- **Deoptimization** hoặc bảo trì metadata theo thread trong những trường hợp HotSpot hỗ trợ.
- **Các công việc hỗ trợ GC liên quan thread/stack roots**, tùy thuật toán GC và giai đoạn cụ thể.
- **Một số hành vi của JVMTI/profiling/monitoring** khi implementation đã tích hợp handshake hoặc công cụ hợp tác với VM.
- **Phối hợp suspend/resume hoặc xử lý ngoại lệ bất đồng bộ nội bộ**, tùy loại closure và JDK.

**Không biến danh sách này thành lời khẳng định “tất cả hoạt động trên luôn dùng handshake”.** Một thao tác có thể dùng handshake, global safepoint, cơ chế lock, hoặc một tổ hợp, tùy JVM version/GC và các điều kiện.

Đối với HotSpot hiện hành, mã nguồn `runtime/handshake.hpp` thể hiện cả `HandshakeClosure`, `HandshakeState` và các overload `Handshake::execute(...)` để xử lý tập target hoặc target cụ thể. Có sự hỗ trợ thao tác asynchronous, nhưng chi tiết của nó là **native VM implementation**, không phải một public contract cho Java application.

### Thread stack roots và GC

Một thuật toán GC cần nhận diện những **object reference** còn sống trong stack/register. Muốn chạm đến các dữ liệu ấy, VM phải bảo đảm có một điểm quan sát an toàn. Nếu công việc có thể được chia theo từng thread, handshake giúp tránh một số yêu cầu “dừng tất cả thread để làm một việc của một thread”.

Tuy vậy, **bản thân tính năng handshake không làm mọi phase GC trở thành concurrent**. Các GC khác nhau có thiết kế và mức pause khác nhau; với một số tác vụ, điểm nhìn toàn cục vẫn được yêu cầu.

### Global safepoint vẫn tồn tại

Theo mã nguồn HotSpot hiện hành, `SafepointSynchronize::begin/end` vẫn thực hiện các cơ chế đưa những JavaThread liên quan vào global safepoint khi cần. Hai cơ chế **cùng tồn tại**, không phải Handshake thay thế toàn bộ SafepointSynchronize.

## 13. Phân biệt thread của ứng dụng, JavaThread và virtual thread

Tên “thread-local” dễ gây hiểu nhầm khi Java hiện đại có **virtual threads** (chuẩn hóa ở Java 21):

- `java.lang.Thread` là abstraction Java API dùng để quản lý công việc và trạng thái thread.
- **Platform thread** gắn với OS thread theo mô hình thực thi thông thường và được HotSpot quản lý qua những cấu trúc nội bộ.
- **HotSpot JavaThread** là cấu trúc native VM dùng trong logic safepoint/handshake. Đây không phải một object `ThreadLocal<T>`.
- **Virtual thread** là abstraction Java có thể được mount/unmount trên carrier platform thread, không phải lúc nào cũng duy trì quan hệ **một virtual thread ↔ một OS thread**.
- Mã nguồn HotSpot mới có các đường phối hợp handshake liên quan virtual thread, nhưng **không được suy ra JEP 312 ban đầu đã hỗ trợ mọi ngữ nghĩa virtual thread của Java 21**.

Trong bài này, các chương trình Java thuần dùng **platform threads** qua `new Thread(...).start()` để ví dụ dễ quan sát và biên dịch ở mức Java 10. Với hệ thống dùng virtual threads, muốn phân tích nội bộ VM cần nguồn tài liệu của **JDK và profiler đúng phiên bản**.

## 14. Thread-local handshake có đảm bảo “không pause thread khác” không?

Phát biểu cần chính xác:

- **Đúng theo mục đích cơ chế:** để xử lý một thread mục tiêu, VM **không bắt buộc phải yêu cầu global safepoint của tất cả thread** chỉ vì handshake đó.
- **Không đúng nếu suy rộng:** các thread khác **không có cam kết cứng** rằng trong toàn thời gian handshake sẽ luôn chạy, không chịu scheduling, GC, lock contention hay bộ nhớ bận.
- **Không có giới hạn latency cố định** được JEP 312 đảm bảo cho tất cả workloads/hardware.
- **Không phải lock-free/công việc bằng 0**. Việc phối hợp trạng thái, queue, memory ordering và handshaker vẫn có chi phí.
- **Không phải lệnh arbitrary callback** ở bất kỳ vị trí bytecode nào. Callback phải thực thi khi điều kiện handshake-safe thỏa.

Với benchmark, phân biệt **VM-wide pause time**, **handshake completion latency**, **CPU utilization**, **tail latency của request** và **throughput**. Một con số đơn lẻ không đại diện hết các khía cạnh.

### Handshake một thread và many-thread handshake

Trong hướng tiếp cận thread-local, một thao tác có thể nhắm **một target** hoặc nhiều thread. Mục tiêu “không dừng toàn VM” đặc biệt rõ với một target, nhưng một thao tác trên nhiều target cũng có thể cho từng thread hoàn thành và tiếp tục theo tiến độ riêng.

Đừng gọi thao tác nhắm **mọi thread** bằng handshake là “chắc chắn tương đương global safepoint”. Một global safepoint có thể cần mọi thread cùng ở trạng thái phù hợp để đạt **tính nhất quán toàn cục tại cùng một giai đoạn**.

## 15. Những ngộ nhận phổ biến

| Ngộ nhận | Vì sao sai? | Nhớ điều gì? |
| --- | --- | --- |
| “Thread-local handshake là `ThreadLocal`” | Hai cơ chế khác hoàn toàn | Handshake = VM coordination; ThreadLocal = per-thread storage |
| “Thread-local handshake là `Thread.interrupt()`” | Interrupt có hợp đồng Java riêng | Interrupt không phải HotSpot `HandshakeClosure` |
| “JEP 312 tạo public Java API handshake” | Đây là cải tiến nội bộ HotSpot | Ứng dụng chỉ dùng API công khai phù hợp |
| “Callback luôn chạy do chính target thread” | Implementation có thể cho initiator/VMThread xử lý khi target blocked | Target phải an toàn; executor tùy closure |
| “Handshake có thể chạy tại bất kỳ instruction nào” | Cần trạng thái handshake-safe | Polls/chuyển trạng thái VM bảo đảm invariant |
| “Handshake bắt mọi thread cùng dừng” | Đó là mục tiêu khác của global safepoint | Có thể xử lý từng target |
| “Từ Java 10 không còn global safepoint” | Global safepoint vẫn cần cho một số tác vụ | Hai cơ chế cùng tồn tại |
| “Mọi GC là pause-free nhờ handshake” | GC có nhiều pha và mô hình khác nhau | Không suy ra mọi STW pause biến mất |
| “`ThreadMXBean.getThreadInfo` là lệnh handshake công khai” | API chỉ cam kết snapshot thread | Nội bộ triển khai không phải public contract |
| “Có tag `handshake` trong `-Xlog:help` nghĩa là mọi thao tác đều log” | Logging phụ thuộc event/level/JDK | Không coi log rỗng là lỗi handshake |
| “Không có log handshake thì JDK không hỗ trợ handshake” | Có thể không phát sinh sự kiện được log | Dùng JEP/source và diagnostics phù hợp |
| “Đọc thread dump không thể gây global safepoint” | Cơ chế phụ thuộc version và đường gọi | Không hứa không STW chỉ từ tên API |
| “Một virtual thread luôn là một OS JavaThread” | Virtual threads có mô hình carrier | Phân biệt virtual thread và HotSpot JavaThread |
| “Các callback có thể tự truy cập stack bất kỳ lúc nào” | Ràng buộc safety và lifecycle | Chỉ hành động ở trạng thái an toàn |
| “Tất cả JDK vendor triển khai giống HotSpot” | JEP 312 là tính năng HotSpot | Kiểm tra runtime/vendor cụ thể |
| “Thread A handshake thì thread B chắc chắn không từng bị pause” | B vẫn chịu các pause độc lập | Chỉ khẳng định không bắt buộc global safepoint bởi handshake của A |

## 16. Checklist chẩn đoán và kiểm thử

Nếu cần giải thích về thread-local handshake trong một buổi code review hoặc điều tra JVM latency:

1. **Xác định JVM:** HotSpot hay một implementation khác? Xem `java -version`; tránh áp code HotSpot cho mọi JVM.
2. **Xác định version:** JEP 312 thuộc Java 10, nhưng implementation có thể tiến hóa mạnh theo các bản JDK mới.
3. **Phân biệt target:** một JavaThread riêng, nhiều thread hay toàn bộ VM?
4. **Phân biệt trạng thái an toàn:** handshake-safe state không đồng nhất với Java `Thread.State`.
5. **Xác định callback thuộc JVM:** không gán `ThreadLocal`, `Runnable` hoặc `interrupt` làm handshake closure.
6. **Xác định ai thực hiện callback:** có thể là target, initiator hay VMThread tùy implementation và closure.
7. **Có cần global consistency không?** Một số tác vụ vẫn cần global safepoint.
8. **Kiểm tra `-Xlog:help`:** tag `handshake`, `safepoint` có thật trong VM hiện chạy không?
9. **Bật log có chọn lọc:** `-Xlog:handshake=debug` / `-Xlog:safepoint=info` theo tài liệu/JDK; không bật vô điều kiện trong production.
10. **Không assert số dòng log cố định:** chỉ vì không thấy log không có nghĩa handshake bị tắt.
11. **Dùng công cụ quản lý thread đúng phạm vi:** `ThreadMXBean` hoặc `jcmd` có thể cho dữ liệu quan sát, nhưng không bảo đảm lối triển khai nội bộ.
12. **Test Java công khai:** bảo đảm thread còn sống, không race, join đầy đủ, tránh sleep tùy ý để đồng bộ.
13. **Tách dữ liệu đo:** startup pause, safepoint pause, GC pause, handshake hoạt động và request latency là các chỉ số khác nhau.
14. **Kiểm tra workload:** native/JNI, thread pinned, scheduling và compiler có thể ảnh hưởng tiến trình đạt điểm an toàn.
15. **Đọc tài liệu/mã nguồn đúng JDK:** không copy những assertion về C++/VM từ một phiên bản cũ sang bản mới.
16. **Không chỉnh cờ VM thử nghiệm không có nguồn đáng tin:** dùng các lệnh chẩn đoán đang được hỗ trợ trước; đừng đặt các diagnostic/develop flags vào production vô lý.
17. **Không dùng kết quả một API Java để tuyên bố đã quan sát handshake callback:** ví dụ `getThreadInfo` chỉ kiểm tra snapshot của thread.
18. **Khi trình bày lợi ích:** viết “có thể giảm việc phải đồng bộ toàn VM cho công việc theo thread” thay vì “đã loại bỏ mọi pause”.

### Mẫu báo cáo chính xác

~~~text
Đã xác minh: môi trường sử dụng HotSpot, JDK version X.
Quan sát: có thể lấy thread info và log safepoint/handshake được
theo các tag được JVM hỗ trợ. Handshake là cơ chế VM nội bộ.

Chưa suy ra chỉ từ điều đó:
- Mọi thread dump đều dùng handshake thay global safepoint.
- Không còn stop-the-world pause trong hệ thống.
- Mọi request tail latency được cải thiện do JEP 312.

Muốn kết luận mạnh hơn:
- Cần event/log hoặc mã nguồn đúng phiên bản cho operation cụ thể.
- Cần đo end-to-end theo workload và kiểm soát yếu tố nhiễu.
~~~

Đây là **mẫu cách đọc bằng chứng**, không phải stdout của một chương trình Java.

## 17. Câu hỏi tự kiểm tra

1. Thread-local handshake được giới thiệu bằng JEP nào, từ Java mấy?
2. Tại sao HotSpot muốn thực hiện một callback trên một JavaThread mà không dừng cả VM?
3. Handshake-safe state có giống `Thread.State.WAITING` không?
4. Cơ chế polling theo luồng giúp tránh yêu cầu gì đối với những JavaThread không liên quan?
5. Callback phải luôn do target JavaThread chạy không?
6. Một operation nhắm nhiều JavaThread có đồng nghĩa global safepoint không?
7. `ThreadLocal<String>` có tạo ra handshake VM không?
8. `Thread.interrupt()` có phải lệnh phát một `HandshakeClosure` không?
9. `ThreadMXBean.getThreadInfo(id)` có bảo đảm dùng handshake và không global safepoint không?
10. Tại sao gọi `java -Xlog:handshake=debug` không bắt buộc in log handshake?
11. Nếu Java 10 có JEP 312, có thể kết luận mọi garbage collector từ đó là pause-free không?
12. Những giới hạn nào ảnh hưởng latency của handshake?
13. Virtual thread Java 21 có luôn tương đương một HotSpot JavaThread riêng không?
14. Nếu thấy log chỉ ra global safepoint, có mâu thuẫn với sự tồn tại thread-local handshake không?
15. Bạn sẽ dùng nguồn dữ liệu nào để biết một VM version cụ thể dùng handshake cho một diagnostic operation?
16. Vì sao không nên benchmark hiệu năng với logging trace nặng rồi tuyên bố kết quả production?

**Đáp án:**

1. **JEP 312**, từ **Java 10**.
2. Tránh phối hợp toàn VM không cần thiết khi tác vụ chỉ liên quan một/số thread; có thể giảm phạm vi gián đoạn.
3. Không. Một bên là trạng thái nội bộ VM đủ an toàn, bên kia là trạng thái Java API.
4. Không cần mặc định đưa các thread khác vào global safepoint chỉ vì một target.
5. Không. Tùy closure, callback có thể do target, initiator hoặc VMThread thực hiện khi target được giữ an toàn.
6. Không. Global safepoint có yêu cầu phối hợp nhất quán toàn cục riêng.
7. Không; chỉ là per-thread value storage.
8. Không; interrupt có hợp đồng Java riêng.
9. Không có public contract như vậy. API trả thông tin thread; nội bộ phụ thuộc VM.
10. Log phụ thuộc event được ghi, mức log, workload và implementation. Không có log không chứng minh không có handshake.
11. Không; GC có nhiều pha và global safepoint vẫn tồn tại.
12. Trạng thái target, điểm poll, native transitions, scheduling, synchronization và chính callback.
13. Không. Virtual threads có thể được mount/unmount trên carrier threads.
14. Không. Hai cơ chế cùng tồn tại vì có những công việc yêu cầu phạm vi khác nhau.
15. JEP, mã nguồn HotSpot đúng tag/commit, diagnostic logs/JFR tương ứng và thử nghiệm operation cụ thể.
16. Logging có overhead và có thể ảnh hưởng timing; cần benchmark có đối chứng và cấu hình gần production.

## 18. Tài liệu chính thức và nguồn xác minh còn áp dụng

- **OpenJDK JEP 312 — Thread-Local Handshakes (Java 10):** https://openjdk.org/jeps/312
- **Mã nguồn HotSpot hiện hành — `runtime/handshake.hpp`, `HandshakeClosure` và `HandshakeState`:** https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/handshake.hpp
- **Mã nguồn HotSpot hiện hành — `runtime/safepoint.hpp`, global safepoint synchronization:** https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/safepoint.hpp
- **Mã nguồn HotSpot hiện hành — `runtime/safepoint.cpp`, polling và safepoint:** https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/safepoint.cpp
- **Oracle JDK 25 — `java` command / `-Xlog:help`, unified logging tags/levels:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **Oracle Java SE 25 — `ThreadMXBean` và `getThreadInfo`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html
- **Oracle Java SE 25 — `java.lang.ThreadLocal` và `java.lang.Thread`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ThreadLocal.html
- **Inside.java — JVM Logging (phân biệt log tag và tác động của logging):** https://inside.java/2022/11/07/sip071/
- **Aleksey Shipilëv — Safepoint Polls, phân tích cơ chế JVM và JEP 312:** https://shipilev.net/jvm/anatomy-quarks/22-safepoint-polls/
- **Foojay — The Inner Workings of Safepoints, cơ chế polling và global/thread-local safepoints:** https://foojay.io/today/the-inner-workings-of-safepoints/

**Kết luận:** *Thread-local handshake* là **cơ chế phối hợp VM nội bộ được HotSpot đưa vào Java 10** để xử lý callback của một JavaThread hoặc một tập target khi trạng thái an toàn, **không bắt buộc đưa mọi JavaThread vào global safepoint chỉ vì công việc của một thread**. Callback có thể do target hoặc một handshaker khác thực thi theo điều kiện VM; `ThreadLocal`, `interrupt` hay `ThreadMXBean` không phải public handshake APIs. **Global safepoints vẫn tồn tại**, và tối ưu có hay không còn phụ thuộc workload/VM. Khi vận hành, xác minh bằng tài liệu, mã nguồn và logging đúng JDK; đừng dùng một thread dump hoặc thời gian request làm bằng chứng duy nhất cho handshake.
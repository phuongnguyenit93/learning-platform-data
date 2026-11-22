# Kiểm tra bỏ đăng ký transformer khi callback đang chạy và ngừng thu thập có thứ tự

Trong Java Instrumentation, lời gọi **Instrumentation.removeTransformer(transformer)** có nhiệm vụ **bỏ đăng ký** một ClassFileTransformer; nó **không phải lệnh chờ tất cả callback kết thúc**. Javadoc Java SE 17 nói rõ rằng do **class loading đa luồng**, transformer vẫn **có thể nhận callback sau khi đã bị remove**. Điều này có nghĩa một agent ghi metric/tracing hoặc tạo bytecode không thể đóng exporter ngay khi nhận **removed=true**.

Ví dụ: thread A đang thực hiện **transform(ClassA)**, đã được agent chấp nhận và đang ghi event; thread B gọi **removeTransformer** rồi đóng queue/file exporter; thread A tiếp tục và ghi vào tài nguyên đã đóng. Đó là lỗi thứ tự shutdown của agent, không nhất thiết là lỗi JVM.

Mẫu giải quyết là: **đóng admission gate → bỏ đăng ký đúng transformer → drain những callback đã nhận → xử lý hết queue và flush → đóng exporter/resources**. Nếu agent đã chèn runtime hooks vào bytecode, cần tắt thêm **hook admission**, vì bỏ đăng ký transformer **không gỡ các lời gọi hook đã được cài trong class**.

Bài học thuộc nhóm **Kiểm thử và chẩn đoán**, dành cho Java 17+. Ngoài hợp đồng API, bài còn có một **chương trình đầy đủ** tạo callback class-load thật, cố ý giữ callback trong khi gọi removeTransformer, dùng CountDownLatch để xác minh lịch trình và mô phỏng callback đến muộn để kiểm tra hành vi phòng vệ.

## 1. Hiểu chính xác API

~~~java
// Đoạn minh họa trong premain/agentmain có Instrumentation inst.
ClassFileTransformer t = new MyTransformer();
inst.addTransformer(t, false);

// Bỏ đúng instance đã add.
boolean removed = inst.removeTransformer(t);
~~~

Theo tài liệu Java SE 17:

- **addTransformer(transformer, false)** đăng ký transformer nhận các class definitions phù hợp, trong đó false có nghĩa không gọi lại transformer này khi **retransform**. Nếu cần canRetransform=true, JVM và manifest phải hỗ trợ.
- **removeTransformer(transformer)** trả **true** khi tìm thấy và bỏ đăng ký phù hợp, **false** khi không tìm thấy.
- Nếu cùng một transformer instance được đăng ký **nhiều lần**, một lần remove chỉ bỏ **registration matching mới nhất**. Đăng ký trùng được cho phép nhưng không khuyến khích.
- **removeTransformer(null)** ném **NullPointerException**.
- Vì class loading có thể chạy trên nhiều threads, **callback vẫn có thể xuất hiện sau khi remove**. Transformer phải được viết để xử lý điều này.

**Removed=true không hàm ý inFlight=0**, cũng không hàm ý đã flush exporter. Khi kiểm thử, phải tách **registration state**, **callback state** và **event delivery state**.

### 1.1. Phân biệt lifecycle

| Trạng thái | Nghĩa |
| --- | --- |
| REGISTERED | Instrumentation đang giữ đăng ký của transformer |
| CALLBACK_INVOKED | JVM thực sự gọi transform, chưa chắc agent đã nhận thu thập |
| ADMITTED | Gate cho phép callback làm việc và tăng inFlight |
| IN_FLIGHT | Callback đã admitted nhưng chưa leave |
| ADMISSION_CLOSED | Từ thời điểm này, callback mới bị gate từ chối |
| DETACHED | removeTransformer đã xử lý đăng ký |
| PRODUCERS_DRAINED | Những callback/hook đã admitted đều kết thúc |
| QUEUE_DRAINED | Queue/batch exporter không còn dữ liệu cần xử lý |
| FLUSHED | Exporter đã flush theo contract của nó |
| STOPPED | Những resources cần đóng đã đóng; late calls an toàn |

Đây là **những nhãn agent tự thiết kế**, không phải enum của Java Instrumentation. **DETACHED** và **IN_FLIGHT=1** có thể đồng thời đúng.

## 2. Hai race điển hình khi stop

### 2.1. Callback đã chạy trước remove

~~~text
Thread class-loader                        Thread controller
----------------------------------------   ------------------------
JVM gọi transform(ClassA)
callback vượt gate; inFlight = 1
callback chờ I/O hoặc latch
                                           removeTransformer(t) -> true
                                           exporter.close()  (QUÁ SỚM)
callback tiếp tục
callback ghi event                          write-after-close!
callback finally leave; inFlight = 0
~~~

Bởi removeTransformer không chờ callback, exporter.close ngay sau remove không an toàn. Phải **drain accepted work** trước khi close.

### 2.2. Callback tới sau remove

~~~text
Thread class-loader                        Thread controller
----------------------------------------   ------------------------
JVM đã chuẩn bị đường gọi transformer
                                           removeTransformer(t) -> true
transform callback bắt đầu muộn
~~~

Java API cho phép callback muộn, nhưng **không bắt buộc nó xảy ra trong mỗi test run**. Vì vậy transformer cần một **guard ở ngay đầu phần thu thập**:

~~~java
if (!gate.enter()) {
    return null;          // Bị stop: không sửa bytes, không ghi event.
}
try {
    // Biến đổi/thu thập đã được chấp nhận.
    return null;
} finally {
    gate.leave();
}
~~~

**return null** có nghĩa transformer không cung cấp thay đổi. Đừng throw exception chỉ để thông báo shutdown: theo hợp đồng ClassFileTransformer, JVM vẫn có thể tiếp tục transformers khác, còn side effect của việc throw sẽ khiến diagnostics phức tạp.

### 2.3. Lượt đã chấp nhận có được ghi event sau close gate?

**Có**, nếu chính sách shutdown là **drain những lượt accepted trước khi stop**. Sau close gate, callback mới không được admitted, nhưng callback đã vào trước stop có thể hoàn thành, enqueue event rồi leave. Vì vậy exporter phải còn hoạt động đến lúc **producers drained + queue flushed**. Mốc **gate closed** là ranh giới **không nhận việc mới**, không phải mốc **mọi event đã biến mất ngay**.

## 3. Invariant cần được kiểm thử

**I1 — Atomic admission:** Sau khi **close()** của gate hoàn tất, không callback nào có thể vừa đọc trạng thái OPEN vừa tăng inFlight muộn mà controller không biết.

**I2 — Exactly-once in-flight:** Mỗi successful enter tăng inFlight một lần; finally giảm một lần, kể cả exception/interrupt/early return.

**I3 — Remove đúng instance:** Chỉ owner của transformer gọi remove, không tạo instance mới. Không vô tình add cùng instance nhiều lần.

**I4 — Late callback no-op:** Callback đi qua gate sau close nhận false và return null, không dùng queue/exporter đã đóng.

**I5 — Drain thật:** Điều kiện **inFlight=0** phải được chờ bằng primitive đồng bộ, không suy đoán từ Thread.sleep.

**I6 — Không đóng sớm:** Exporter.close chỉ sau khi producers và queue drain hoặc sau một chính sách timeout/fallback được quyết định rõ.

**I7 — Không self-join:** Callback không chờ drain của một nhóm công việc mà chính nó đang được đếm trong nhóm.

**I8 — Không rollback giả:** removeTransformer không làm bytecode đã được cài trở lại phiên bản gốc.

## 4. Gate sử dụng synchronized để chặn race

Một triển khai Java 17 gọn và dễ kiểm chứng:

~~~java
// Thành phần của ví dụ đầy đủ ở phần sau.
private static final class Gate {
    private boolean accepting = true;
    private int inFlight;

    synchronized boolean enter() {
        if (!accepting) {
            return false;
        }
        inFlight++;
        return true;
    }

    synchronized void leave() {
        inFlight--;
        if (inFlight == 0) {
            notifyAll();
        }
    }

    synchronized void close() {
        accepting = false;
    }

    synchronized int active() {
        return inFlight;
    }

    synchronized void awaitZero() throws InterruptedException {
        while (inFlight != 0) {
            wait();
        }
    }
}
~~~

Hai thao tác **check accepting** và **increment inFlight** diễn ra trong một synchronized region, cùng monitor với close. Vì vậy có đúng hai trường hợp:

1. **enter chiếm lock trước**: callback được admitted và inFlight đã tăng; shutdown sau đó phải đợi nó.
2. **close chiếm lock trước**: callback thấy accepting=false và không tăng inFlight.

Đừng giữ gate monitor trong lúc thực hiện I/O, logging hoặc bytecode transformation. Monitor chỉ quản lý lifecycle counters. **Object.wait()** được dùng trong vòng while để xử lý cả spurious wakeups và thay đổi điều kiện không như kỳ vọng.

### 4.1. Vì sao hai atomic variables riêng không đủ?

~~~java
// Pseudocode SAI: check-then-increment có race.
if (!closed.get()) {         // A thấy false
    // B: closed=true; thấy active=0; đóng exporter.
    active.incrementAndGet();
    sendEvent();             // A chạm exporter đã đóng!
    active.decrementAndGet();
}
~~~

AtomicBoolean và AtomicInteger bảo đảm thao tác riêng lẻ, nhưng **check + increment** không tự nguyên tử. Muốn làm lock-free cần một state machine CAS chung mã hóa cả **closed bit và active count** với chứng minh đầy đủ. Với học tập và nhiều agent, synchronized gate rõ ràng và ít rủi ro hơn.

## 5. Ví dụ Java 17 hoàn chỉnh: callback thật bị giữ khi remove

Demo dùng một source **UnregisterLab.java**, vừa là Java agent (có **premain**) vừa là chương trình test (có **main**). Code không cần thư viện ngoài.

Quy trình:

1. **premain** đăng ký **Observer** một lần, **canRetransform=false**.
2. Main tạo loader thread, yêu cầu JVM định nghĩa class **UnregisterLab$Subject** qua Class.forName.
3. JVM gọi **transform** thật; callback vượt gate, thông báo **ENTERED**, rồi chờ **RELEASE**.
4. Main đợi ENTERED để biết callback đã đang chạy, đóng gate rồi gọi **removeTransformer(observer)**. Ở thời điểm kiểm tra, inFlight vẫn là 1.
5. Main **gọi trực tiếp transform** với tên class **UnregisterLab$Late** để mô phỏng late callback; gate đã đóng nên return null. Đây là **unit-level simulation**, không phải một callback late do JVM tự tạo.
6. Một waiter thread chờ awaitZero, không thể kết thúc khi RELEASE chưa mở.
7. Main countDown RELEASE; callback thật tăng EVENTS, gọi finally leave, waiter hoàn thành.
8. Các assertions xác nhận kết quả và in tám dòng stdout cố định.

**Chú ý:** Transformer demo **luôn return null**, vì bài tập về vòng đời callback, không phải thử sửa classfileBuffer. Nếu agent thật cần biến đổi, logic transform có thể ở đoạn đã admitted và phải trả byte[] mới hợp lệ khi thay đổi, không mutate input bytes.

### 5.1. UnregisterLab.java

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class UnregisterLab {
    private static final Gate GATE = new Gate();
    private static final CountDownLatch ENTERED = new CountDownLatch(1);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final AtomicInteger EVENTS = new AtomicInteger();
    private static volatile Instrumentation instrumentation;
    private static volatile Observer observer;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        observer = new Observer();
        inst.addTransformer(observer, false);
    }

    public static final class Subject {
        public static int answer() {
            return 42;
        }
    }

    private static final class Gate {
        private boolean accepting = true;
        private int inFlight;

        synchronized boolean enter() {
            if (!accepting) {
                return false;
            }
            inFlight++;
            return true;
        }

        synchronized void leave() {
            inFlight--;
            if (inFlight == 0) {
                notifyAll();
            }
        }

        synchronized void close() {
            accepting = false;
        }

        synchronized int active() {
            return inFlight;
        }

        synchronized void awaitZero()
                throws InterruptedException {
            while (inFlight != 0) {
                wait();
            }
        }
    }

    private static final class Observer
            implements ClassFileTransformer {

        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] classfileBuffer) {

            if (!"UnregisterLab$Subject".equals(className)
                    && !"UnregisterLab$Late".equals(className)) {
                return null;
            }

            if (!GATE.enter()) {
                return null;
            }

            try {
                if ("UnregisterLab$Subject".equals(className)) {
                    ENTERED.countDown();

                    try {
                        RELEASE.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        return null;
                    }

                    EVENTS.incrementAndGet();
                }

                return null;  // Không thay class bytes.
            } finally {
                GATE.leave();
            }
        }
    }

    public static void main(String[] args)
            throws Exception {

        if (instrumentation == null || observer == null) {
            throw new IllegalStateException(
                    "Run with -javaagent");
        }

        AtomicReference<Throwable> loadFailure =
                new AtomicReference<>();

        Thread loader = new Thread(() -> {
            try {
                Class.forName(
                        "UnregisterLab$Subject",
                        true,
                        UnregisterLab.class.getClassLoader());
            } catch (Throwable failure) {
                loadFailure.set(failure);
            }
        }, "load-subject");

        loader.start();

        if (!ENTERED.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError(
                    "No real JVM callback arrived");
        }

        GATE.close();
        boolean removed =
                instrumentation.removeTransformer(observer);
        int activeAtRemove = GATE.active();

        // Giả lập callback tới sau close để kiểm tra gate.
        byte[] skipped = observer.transform(
                null, "UnregisterLab$Late",
                null, null, new byte[] { 0 });

        int beforeRelease = EVENTS.get();

        CountDownLatch drained = new CountDownLatch(1);
        Thread waiter = new Thread(() -> {
            try {
                GATE.awaitZero();
                drained.countDown();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }, "await-drain");
        waiter.start();

        boolean drainedBeforeRelease =
                drained.await(100, TimeUnit.MILLISECONDS);

        RELEASE.countDown();
        loader.join(5000);
        waiter.join(5000);

        if (loader.isAlive() || waiter.isAlive()
                || loadFailure.get() != null) {
            throw new AssertionError(
                    "Loader/drain did not complete",
                    loadFailure.get());
        }

        if (!removed || activeAtRemove != 1
                || skipped != null || beforeRelease != 0
                || drainedBeforeRelease || EVENTS.get() != 1
                || GATE.active() != 0) {
            throw new AssertionError(
                    "Shutdown contract violated");
        }

        System.out.println("CALLBACK_ENTERED=true");
        System.out.println("REMOVED=true");
        System.out.println("ACTIVE_AT_REMOVE=" + activeAtRemove);
        System.out.println("LATE_CALLBACK_SKIPPED=true");
        System.out.println(
                "DRAIN_BLOCKED_UNTIL_RELEASE=true");
        System.out.println(
                "EVENTS_AFTER_DRAIN=" + EVENTS.get());
        System.out.println(
                "ACTIVE_AFTER_DRAIN=" + GATE.active());
        System.out.println("SHUTDOWN_OK");
    }
}
~~~

Java 9 trở lên có overload **ClassFileTransformer.transform(Module, ...)**; default implementation có thể chuyển tiếp về overload năm tham số dùng trong ví dụ. Filter so sánh chuỗi bằng **"name".equals(className)** an toàn nếu className null.

### 5.2. agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: UnregisterLab
~~~

Giữ một newline cuối file. Demo chỉ kiểm tra initial class definition nên không cần **Can-Retransform-Classes: true**.

### 5.3. Build và chạy

~~~bash
mkdir -p out

javac --release 17 -d out UnregisterLab.java

jar cfm unregister-agent.jar agent.mf -C out .

java -javaagent:unregister-agent.jar \
     -cp unregister-agent.jar UnregisterLab
~~~

JAR chứa class chính và mọi nested classes. Trên Windows PowerShell hoặc cmd.exe, gõ lệnh java thành một dòng:

~~~text
java -javaagent:unregister-agent.jar -cp unregister-agent.jar UnregisterLab
~~~

### 5.4. Kết quả

~~~text
CALLBACK_ENTERED=true
REMOVED=true
ACTIVE_AT_REMOVE=1
LATE_CALLBACK_SKIPPED=true
DRAIN_BLOCKED_UNTIL_RELEASE=true
EVENTS_AFTER_DRAIN=1
ACTIVE_AFTER_DRAIN=0
SHUTDOWN_OK
~~~

**Kiểm chứng:** Core logic ở trên đã được biên dịch bằng **javac --release 17** và chạy thành công trên **OpenJDK 24** trong thư mục tạm. Test thực tế đạt các assertions về callback JVM thật đang in-flight, remove trả true, late callback giả lập bị skip và waiter chỉ hoàn tất sau release. Mã chưa được kiểm thử trên mọi JVM vendor/build; nên chạy lại trên JDK đích.

### 5.5. Từng dòng có nghĩa gì?

| Dòng | Bằng chứng |
| --- | --- |
| CALLBACK_ENTERED=true | JVM đã thực sự gọi transformer cho Subject |
| REMOVED=true | Đã bỏ đăng ký đúng instance |
| ACTIVE_AT_REMOVE=1 | Có callback chưa kết thúc tại thời điểm remove trả về |
| LATE_CALLBACK_SKIPPED=true | Gate chặn lời gọi transform trực tiếp sau close |
| DRAIN_BLOCKED_UNTIL_RELEASE=true | awaitZero không thể xong khi callback đang chờ |
| EVENTS_AFTER_DRAIN=1 | Callback đã admitted trước stop vẫn hoàn thành |
| ACTIVE_AFTER_DRAIN=0 | Không còn callback in-flight đã được chấp nhận |
| SHUTDOWN_OK | Toàn bộ invariant của bài test đạt |

**LATE_CALLBACK_SKIPPED** là **unit test giả lập**, không được gọi là “JVM chắc chắn đã phát callback sau remove”. JVM chỉ có thể xảy ra điều đó theo API; không thể ép mọi execution phải có interleaving ấy.

## 6. Vì sao CountDownLatch quan trọng hơn sleep?

Nếu chỉ làm:

~~~java
Thread loader = new Thread(() -> Class.forName("..."));
loader.start();
Thread.sleep(100);
inst.removeTransformer(transformer);
~~~

test không biết callback đã vào hay chưa. Một máy chạy chậm có thể chưa tạo class; máy khác callback có thể đã kết thúc. Đó là flaky race test.

Ở demo, **ENTERED.await** chỉ hoàn thành sau khi callback thật gọi ENTERED.countDown. Callback dừng ở RELEASE.await cho đến khi main cho phép. Waiter thread dùng **awaitZero** để kiểm tra điều kiện drain độc lập. Test có thời gian chờ/join có giới hạn, nên khi thread kẹt sẽ báo **AssertionError** thay vì giả vờ thành công.

Hãy phân biệt **callback JVM thật** với **lời gọi transform giả lập để kiểm tra guard**. Kết hợp hai phép thử này mạnh hơn việc trông chờ JVM tự tạo late callback trong mỗi lượt.

## 7. Shutdown hoàn chỉnh cho collector/exporter

Với agent có queue và runtime hooks, trình tự:

~~~text
ACTIVE
   |
   v
CLOSE_ADMISSION       transformerGate.close(), hookGate.close()
   |
   v
REMOVE_TRANSFORMER    removeTransformer đúng reference
   |
   v
DRAIN_PRODUCERS       inFlight callbacks và runtime hooks về 0
   |
   v
DRAIN_QUEUE           consumer xử lý hết accepted events
   |
   v
FLUSH_EXPORTER        nhận kết quả flush/ack
   |
   v
CLOSE_RESOURCES       exporter.close()
   |
   v
STOPPED
~~~

Nếu exporter là asynchronous, **inFlight==0** chỉ chứng minh callback đã rời collector, **không chứng minh queue hoặc network buffers đã rỗng**.

~~~java
// Pseudocode service-level, không phải file chạy độc lập.
transformerGate.close();
hookGate.close();

boolean removed = instrumentation.removeTransformer(transformer);

transformerGate.awaitZero();
hookGate.awaitZero();

queue.awaitDrained();
exporter.flush();
exporter.close();
~~~

Lời gọi remove có thể trả false nếu đã remove trước đó, nhưng chỉ một state machine quản lý ownership mới cho phép coi đó là idempotent stop. Nếu flush timeout, phải báo **FLUSH_FAILED/TIMED_OUT**, không tự coi đã giao hết events.

## 8. Runtime hooks đã chèn không biến mất khi remove

Nếu transformer từng chèn:

~~~text
INVOKESTATIC my/agent/Hooks.record()V
~~~

thì instruction này còn trong bytecode đã được JVM cài. **removeTransformer không rewrite những method đó**. Những invocation mới và active frames vẫn có thể gọi helper. Vì thế hook cần **no-op khi collection đã đóng**:

~~~java
// Pseudocode thiết kế; Gate và exporter là thành phần riêng.
public static void record() {
    if (!hookGate.enter()) {
        return;
    }
    try {
        enqueueSafely();
    } finally {
        hookGate.leave();
    }
}
~~~

Đừng unload helper hoặc xóa dependency mà bytecode vẫn cần. Nếu thực sự cần gỡ advice khỏi class đã load, hãy cân nhắc **retransformClasses/redefineClasses** trong giới hạn capability và class schema, kiểm tra các transformers khác cùng chuỗi và xác minh behavior. removeTransformer không tự rollback class definitions.

## 9. Timeout, interruption và trường hợp khó

**Timeout:** Một callback có thể kẹt do classloader locks, I/O hoặc recursion. Không nên đợi vô hạn trong production. Dùng **Condition.awaitNanos** hay phương thức wait có deadline, khi hết thời gian trả trạng thái **TIMED_OUT** với số inFlight còn lại, không tuyên bố DRAINED.

~~~java
// Pseudocode trong Gate sử dụng ReentrantLock và Condition.
long remaining = timeout.toNanos();
lock.lock();
try {
    while (inFlight > 0) {
        if (remaining <= 0) {
            return false;
        }
        remaining = zero.awaitNanos(remaining);
    }
    return true;
} finally {
    lock.unlock();
}
~~~

**Interrupt:** Nếu controller nhận InterruptedException, phải propagate hoặc khôi phục interrupt flag theo policy. Không đánh dấu drain thành công khi wait bị hủy. Callback demo có thể bị interrupt và luôn giảm inFlight trong finally.

**Self-deadlock:** Không gọi awaitZero từ chính transform đã enter, vì callback sẽ chờ chính nó leave. Controller nên chạy ở thread riêng.

**Logger recursion:** ClassFileTransformer không nên giữ gate lock trong lúc logging/network I/O; logger có thể tự kích hoạt class loads và callback lồng nhau.

**Native/classloader state:** Không cưỡng ép Thread.stop trên class-loader threads. Nếu shutdown quá thời gian, ghi thread dump và chọn policy an toàn thay vì giết tùy tiện JVM thread đang giữ lock.

## 10. Đăng ký trùng, sai instance và dừng hai lần

~~~java
ClassFileTransformer a = new MyTransformer();
inst.addTransformer(a, false);

// Đây là một object khác dù cùng class:
boolean wrong = inst.removeTransformer(new MyTransformer());

// Đây là registration ban đầu:
boolean right = inst.removeTransformer(a);
~~~

Đừng phụ thuộc vào override equals/hashCode của một class transformer để thay thế identity/ownership. Lưu reference chính xác.

Nếu add cùng instance hai lần, API loại một registration matching gần nhất mỗi lần remove. Tốt nhất dùng **single owner** và không add trùng.

Nếu SIGTERM, shutdown hook và operator API cùng gọi stop, cần state **ACTIVE → STOPPING → STOPPED** chỉ cho **một controller** chạy close/remove/drain/flush. Controller khác chờ cùng completion; tránh double-close exporter, double-flush, hoặc nhầm remove=false với thất bại nghiêm trọng.

## 11. Callback đã trả bytes trước close thì sao?

Nếu transformer có thay đổi bytecode, có ba thời điểm:

1. Callback tới sau close → gate từ chối, return null.
2. Callback đã admitted nhưng chưa return → có thể hoàn thành hoặc kiểm tra generation trước return theo policy.
3. Callback đã return bytes trước close → JVM có thể còn đang verify/define class, và **remove không thu hồi byte[] đã trả**.

Do đó một gate không bảo đảm tuyệt đối “không thể có class definition mới mang advice sau thời điểm T”. Nếu nghiệp vụ yêu cầu điểm cắt code deployment mạnh hơn, cần chiến lược class loading/quiescence/redefinition riêng. Với **ngừng thu thập**, hook gate/no-op là phương án khác với gỡ bytecode.

Nếu transformer return null khi stopped, đó là no-op theo hợp đồng. Nếu transformer trả dữ liệu mới phải tạo **byte[] khác**, giữ **classfileBuffer bất biến**. Không dùng unchecked exception trong callback làm cơ chế control flow cho shutdown; JVM vẫn có thể tiếp tục transformation pipeline.

## 12. Ma trận test bắt buộc

| Kịch bản | Assertion |
| --- | --- |
| Gate OPEN | enter=true, inFlight tăng |
| Gate CLOSED | enter=false, không tăng |
| enter đua close | Không callback nào admitted sau mốc close |
| Exception/interrupt trong callback | finally giảm inFlight |
| JVM class load Subject | Callback thật vào trước removal |
| remove khi callback bị giữ | removed=true, inFlight có thể bằng 1 |
| Late callback giả lập | Return null, không event mới |
| Drain khi chưa release | Không hoàn tất |
| Drain sau release | inFlight=0 |
| Wrong transformer instance | remove=false |
| Add cùng object hai lần | Một remove chưa chắc gỡ hết |
| Stop hai lần | Không double-close, trạng thái idempotent |
| Callback block lâu | TIMEOUT có báo rõ |
| Callback thread tự đợi drain | Không cho phép self-deadlock |
| Queue còn pending | Exporter không close trước flush |
| Already instrumented class | Hook vẫn có thể gọi; guard no-op |
| Multiple class loaders | Không race/nhầm className |
| Multiple agents | Stop agent này không remove transformer agent khác |
| Stress class loading | Không deadlock và event counters đúng |

Stress test có thể không gặp late callback ngay cả sau nhiều lượt. Vì API chỉ nói **có thể**, sự vắng mặt của late callback **không chứng minh an toàn**. Unit test mô phỏng và deterministic latch integration là cần thiết.

## 13. Metrics và chẩn đoán

Nên tách:

| Tên | Định nghĩa |
| --- | --- |
| callback_invocations_total | Mỗi lần JVM gọi transform |
| callback_admitted_total | Vượt gate khi OPEN |
| callback_rejected_total | Đến sau close bị từ chối |
| inflight_callbacks | Đã admitted chưa leave |
| events_enqueued_total | Đưa vào queue |
| events_exported_total | Exporter xác nhận đã xử lý |
| events_dropped_total | Bị loại theo chính sách |
| exporter_pending | Records tồn đọng |
| shutdown_duration_ms | Thời gian từ stop request tới STOPPED |
| shutdown_timeout_total | Drain/flush quá deadline |
| remove_false_total | Không tìm thấy registration phù hợp |

Nếu **callback_invocations_total** còn tăng sau remove, điều đó không tự là bug. Điều quan trọng là **admitted_total không tăng sau close** và không có write-after-close. LongAdder.sum() khi writers còn chạy không phải snapshot nguyên tử của mọi metric; lấy snapshot sau producer drain nếu cần một báo cáo nhất quán.

### 13.1. Triệu chứng thường gặp

| Triệu chứng | Nguyên nhân | Sửa |
| --- | --- | --- |
| remove=true nhưng còn callback | Race được Javadoc cho phép | Gate, return null, drain |
| remove=false ngay lần đầu | Sai reference/chưa add/đã remove | Track registration owner |
| inFlight mãi >0 | Thiếu finally hoặc callback block | Thread dump, timeout |
| inFlight âm | Leave lặp hoặc enter thất bại vẫn leave | Assert invariants |
| Đã stop mà events vẫn xuất | Hook đã chèn hoặc queue chưa flush | Tách hook gate và exporter lifecycle |
| Class loading treo | Logging recursion/lock contention | Giảm blocking trong transform |
| Test race flaky | Dùng sleep, class Subject load quá sớm | Latches và filter class chính xác |
| Event bị mất khi close | Exporter đóng trước producers/queue drain | Đổi thứ tự |
| Bytecode vẫn instrumented | remove không rollback definitions | Hook no-op hoặc retransform hợp lệ |

## 14. Câu hỏi tự kiểm tra

1. **removeTransformer trả true đã chắc inFlight=0 chưa?** Chưa.
2. **JVM có thể gọi transformer sau remove không?** Có, theo Java 17 Javadoc về concurrency.
3. **Close gate trước hay sau remove?** Trước, để chặn admission mới từ điểm close.
4. **Vì sao AtomicBoolean và AtomicInteger rời rạc có race?** Check và increment không được tuyến tính hóa cùng close.
5. **Vì sao finally cần thiết?** Đảm bảo leave trên mọi đường thoát của admitted callback.
6. **Vì sao CountDownLatch tốt hơn sleep?** Có tín hiệu callback thật đã vào và cách giữ nó in-flight.
7. **Late callback trong demo là callback JVM tự phát?** Không, là lời gọi trực tiếp để test guard.
8. **Callback admitted trước stop có thể emit sau stop không?** Có khi drain accepted work; exporter phải còn mở.
9. **Remove có xóa các lệnh INVOKESTATIC đã chèn không?** Không.
10. **inFlight=0 có đồng nghĩa queue đã flush không?** Không.
11. **Stop từ chính callback có nên chờ tất cả inFlight không?** Không, dễ self-deadlock.
12. **Nếu remove trả false có nên đóng exporter ngay?** Không nếu chưa xác minh ownership và những producers.
13. **Có nên register cùng transformer nhiều lần?** Không nên; một remove chỉ gỡ lần matching gần nhất.
14. **Muốn bảo đảm runtime hooks ngừng emit thì làm sao?** Gate/no-op riêng cho hook và drain trước exporter close.

## 15. Checklist triển khai

- Hiểu **removeTransformer chỉ hủy đăng ký, không drain callback**.
- Có đúng reference transformer và single-owner registration.
- Gate check/enter/close có tính nguyên tử với nhau.
- Mọi callback admitted giảm inFlight bằng finally.
- Chỉ đóng exporter sau producers drained + queue flushed.
- Có timeout/interrupt/failure policy khi callback block.
- Test callback JVM thật đang chạy lúc remove.
- Test giả lập callback late và verify no-op.
- Không giữ gate lock trong transform body hay exporter I/O.
- Runtime hooks đã chèn vẫn tồn tại và trở thành no-op khi collection closed.
- Stop idempotent, không double-remove/double-close.
- Không hứa automatic rollback class definitions sau remove.
- Có metrics cho admitted/rejected/inFlight/queue/flush/drops.
- Smoke và stress test trên JDK vendor/version đang triển khai.

## 16. Tài liệu chuẩn

- [Java SE 17 — Instrumentation.removeTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#removeTransformer(java.lang.instrument.ClassFileTransformer)): contract remove, boolean, duplicate instance và callbacks sau removal.
- [Java SE 17 — Instrumentation.addTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#addTransformer(java.lang.instrument.ClassFileTransformer,boolean)): đăng ký và chế độ canRetransform.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): class-load callbacks, return null/new byte[] và immutable input.
- [Java SE 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): cách khởi động agent và entry points.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ threads cho deterministic tests.
- [Java SE 17 — Object.wait/notifyAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): condition waiting và spurious wakeups.
- [Java SE 17 — ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): alternative lock/condition dùng bounded wait.

**Kết luận:** Khi agent dừng thu thập, **removeTransformer không phải hàng rào bảo đảm callback đã thoát**. Hãy **đóng admission gate → remove đúng instance → drain callbacks/hooks → drain queue và flush → close resources**. Phải kiểm thử cả một **callback JVM thực sự đang in-flight lúc remove** lẫn **callback late giả lập bị từ chối**, đồng thời nhớ rằng **bytecode đã instrument không tự được gỡ** chỉ vì transformer đã bị remove.

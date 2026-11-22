# Aspect dùng chung với nhiều lời gọi đồng thời

Một **aspect** trong **Aspect-Oriented Programming (AOP – lập trình hướng khía cạnh)** có thể được áp dụng cho rất nhiều join point và nhiều lời gọi. Nếu cùng **một instance aspect** được dùng chung, các advice của nó có thể được thực thi **đồng thời trên nhiều thread**. Điều này thường xảy ra với các concern như logging, tracing, metrics, authorization, cache, retry, transaction observation và audit.

**Vấn đề không nằm ở việc “dùng chung” tự nó nguy hiểm**, mà nằm ở việc nhiều lần gọi cùng truy cập **trạng thái mutable** của aspect hoặc dependency mà không có hợp đồng đồng thời phù hợp. Một aspect dùng chung nhưng không giữ trạng thái biến đổi giữa các lời gọi có thể rất dễ an toàn. Ngược lại, chỉ một field như `currentUser`, `startedAt`, `lastRequest` hoặc `int count` đã có thể gây **ghi đè dữ liệu, sai thời gian đo, mất lượt cập nhật hoặc rò dữ liệu giữa người dùng**.

Mục tiêu của bài:
- Hiểu sự khác nhau giữa **aspect instance scope** và **invocation scope**.
- Biết những field/đường dependency nào thực sự được chia sẻ.
- Phân biệt **race condition**, **visibility**, **atomicity**, **ordering** và **reentrancy**.
- Chọn **biến cục bộ**, **đối tượng bất biến**, **atomic**, **khóa**, **state store** hoặc **context propagation** đúng yêu cầu.
- Bảo toàn kết quả, ngoại lệ, side effect và yêu cầu bảo mật khi aspect chạy đồng thời.
- Kiểm chứng bằng ví dụ **Java 17 chạy độc lập** cho hai lời gọi đồng thời trên cùng aspect instance: bộ đếm không an toàn mất lượt, bộ đếm `AtomicInteger` cho kết quả đúng.

Bài tập trung vào **AOP nói chung, cả cơ bản và nâng cao**. Ví dụ dùng wrapper Java để diễn đạt advice/continuation; không phải mọi nền tảng AOP dùng cùng cơ chế proxy, cú pháp pointcut hay vòng đời instance.

## 1. Khi nào một aspect thực sự “dùng chung”?

Trong AOP:
- **Aspect** nhóm một hoặc nhiều pointcut/advice cho một concern.
- **Join point** là điểm chương trình có thể được can thiệp.
- **Pointcut** chọn những điểm phù hợp.
- **Advice** là hành vi before, after, around hoặc dạng khác được hỗ trợ.
- **Aspect instance scope/lifecycle** xác định **instance nào** chạy advice cho một lần gọi.
- **Invocation** là một lần thực thi qua điểm can thiệp cụ thể.

Một aspect có thể được cấp một instance chung cho tất cả lời gọi phù hợp, một instance theo target, theo đối tượng thực thi, theo flow hoặc cách khác nếu mô hình hỗ trợ.

~~~text
Thread T1 ── invocation A ──┐
                            │
Thread T2 ── invocation B ──┼──> cùng SharedAspect instance
                            │        |
Thread T3 ── invocation C ──┘        +--> advice(...)
                                     +--> shared fields?
                                     +--> dependencies?
~~~

**Một instance không có nghĩa mỗi lần chỉ một thread được vào.** Nếu không có cơ chế khóa/serialization, các advice trong object dùng chung có thể chạy xen kẽ.

Cũng không được giả định **một instance được tạo cho mỗi target sẽ chỉ có một thread**: một target dùng chung vẫn có thể nhận nhiều lời gọi đồng thời. Ngược lại, một aspect dùng chung giữa nhiều target không nhất thiết chứa shared mutable state.

### 1.1 Scope của instance khác scope của dữ liệu

Có ít nhất bốn phạm vi cần tách:
1. **Per-invocation:** biến cục bộ, tham số và context chỉ sống trong một lần advice.
2. **Per-aspect-instance:** field và dependency được lưu trong instance; sống qua nhiều lời gọi dùng instance đó.
3. **Per-target/per-flow/per-principal:** state được phân vùng theo đối tượng hoặc ngữ cảnh nghiệp vụ, có thể lưu trong/ngoài aspect.
4. **External/global/distributed:** cache, metrics aggregator, database hoặc store chung qua nhiều instance/process.

Bài toán đồng thời chỉ được giải khi xác định **ai thật sự đọc/ghi cùng một state**. Một `private final Repository repository` có thể trỏ đến một repository mutable dùng chung; `final` chỉ làm tham chiếu field không đổi, không biến đối tượng đích thành immutable.

### 1.2 Shared aspect và singleton không đồng nghĩa stateless

Một instance dùng chung có thể:
- **Stateless:** advice chỉ đọc args/current context, dùng biến local, gửi event qua sink an toàn.
- **Stateful được kiểm soát:** lưu `AtomicInteger`, immutable policy snapshot hoặc một máy trạng thái có khóa.
- **Stateful không an toàn:** lưu `currentRequest` trong field để dùng sau `proceed`, dùng `HashMap` mutable đồng thời không bảo vệ, tăng `int` không đồng bộ.

Cách tổ chức các concern không chỉ nằm ở số lượng object được tạo. Nếu aspect A stateless nhưng gọi service B có mutable state và B không an toàn đa luồng, toàn đường gọi vẫn có nguy cơ race.

## 2. Tại sao nhiều lời gọi có thể chồng lấn?

Xem một around advice được dùng chung:

~~~text
around invocation:
    before()
    result = proceed()
    after(result)
    return result
~~~

Khi T1 đang chờ I/O trong `proceed()`, T2 có thể vào **cùng instance advice** và thực hiện một invocation khác. Nếu `before` của hai lời gọi cùng sửa một field, invocation sau có thể thay đổi dữ liệu invocation trước vẫn cần.

Một thứ tự thực thi hợp lệ:

~~~text
T1: before(A) ------ proceed(A) -------- after(A)
T2:       before(B) ------ proceed(B) ------ after(B)
                   ^ hai invocation chồng lấn
~~~

Không có bảo đảm advice được chạy tuần tự chỉ vì nó là một phương thức của cùng object. Thứ tự dòng log giữa thread cũng không tự chứng minh lỗi. Cần kiểm tra **bất biến dữ liệu** và **thứ tự trong từng invocation**, không đòi mọi thread dùng một thứ tự tổng giả.

## 3. Sai lầm kinh điển: field chứa state riêng của mỗi lời gọi

Giả sử một aspect đo thời gian:

~~~java
// MẢNH MINH HỌA LỖI: không phải chương trình chạy độc lập.
class UnsafeTimingAspect {
    private long startedAtNanos;

    String around(java.util.function.Supplier<String> next) {
        startedAtNanos = System.nanoTime();
        try {
            return next.get();
        } finally {
            long elapsed = System.nanoTime() - startedAtNanos;
            record(elapsed);
        }
    }

    void record(long nanos) {
        // chuyển cho bộ nhận metric
    }
}
~~~

Nếu T1 bắt đầu A, ghi `startedAtNanos=t1`, sau đó T2 bắt đầu B và ghi `startedAtNanos=t2`, T1 kết thúc sẽ lấy **t2** làm mốc cho A. Sai dù bản thân `System.nanoTime()` hoạt động đúng.

**Sửa bằng biến cục bộ theo invocation**:

~~~java
// MẢNH MINH HỌA: mỗi stack frame có startedAtNanos riêng.
class SafeTimingAspect {
    String around(java.util.function.Supplier<String> next) {
        long startedAtNanos = System.nanoTime();
        try {
            return next.get();
        } finally {
            long elapsed = System.nanoTime() - startedAtNanos;
            record(elapsed);
        }
    }

    void record(long nanos) {
        // bộ nhận metric chịu trách nhiệm thread safety
    }
}
~~~

Biến `startedAtNanos` thuộc **mỗi lần gọi**, không bị T2 ghi đè trong frame của T1. Với lời gọi lồng nhau, mỗi frame cũng có local riêng. Nếu `record` ghi vào một sink mutable dùng chung, sink vẫn cần hợp đồng đồng thời của riêng nó.

### 3.1 Cùng nguyên lý với identity và dữ liệu nhạy cảm

Sai lầm nguy hiểm hơn:

~~~text
aspect.currentUser = callerUser
proceed()
authorizeUsing(aspect.currentUser)
~~~

Invocation B có thể thay `currentUser` trong lúc invocation A đang chạy, khiến kiểm tra quyền A dùng danh tính B. **Không bao giờ dùng một field dùng chung để lưu principal/tenant/request payload tạm của lời gọi hiện tại.**

Phải lấy identity từ ngữ cảnh đã xác thực của chính invocation đó và mang qua đường xử lý bằng cơ chế đáng tin. Nếu cần cache policy theo user, key phải gắn **principal, action, resource, version/expiry** phù hợp; tránh nhầm thông tin giữa người dùng/tenant.

## 4. Race condition, atomicity, visibility và ordering

Bốn khái niệm thường bị gọi chung là “thread safety” nhưng giải quyết những việc khác nhau.

### 4.1 Race condition

Kết quả phụ thuộc vào thứ tự xen kẽ các thao tác của nhiều thread. Ví dụ `calls++` trên một field chung có thể mất cập nhật vì hai thread cùng đọc giá trị cũ, cùng cộng, rồi cùng ghi.

~~~text
Ban đầu calls = 0

T1 reads 0         T2 reads 0
T1 computes 1      T2 computes 1
T1 writes 1        T2 writes 1

Mong đợi 2, thực tế có thể chỉ là 1.
~~~

Đây là **lost update**. Không phải cứ chạy thử một lần thấy kết quả 2 là code an toàn; race có thể chỉ lộ dưới một lịch thực thi khác.

### 4.2 Atomicity

Một thao tác hoặc nhóm thao tác phải được quan sát là **không chia cắt** theo hợp đồng.

- `AtomicInteger.incrementAndGet()` là thao tác tăng có bảo đảm nguyên tử cho một biến.
- `counter++` trên `int` thông thường không có atomic read-modify-write.
- `volatile int counter` cũng **không** khiến `counter++` thành thao tác nguyên tử.
- Với bất biến **nhiều field**, bảo vệ từng field bằng các atomic riêng chưa chắc đủ để bảo đảm chúng thay đổi **cùng nhau**.

Ví dụ nếu `successes + failures == attempts` cần luôn đúng tại một snapshot được công bố, ba bộ đếm độc lập có thể bị đọc ở các thời điểm xen kẽ khác nhau. Cần chọn hợp đồng snapshot/locking/immutable state phù hợp.

### 4.3 Visibility

Một thread ghi giá trị mới không có nghĩa thread khác **luôn thấy ngay** nếu không có quan hệ đồng bộ hóa đúng theo **Java Memory Model (JMM)**. Các cơ chế như `synchronized`, atomic/volatile với điều kiện thích hợp, `Future.get()`, các thao tác của thư viện concurrent cung cấp quan hệ **happens-before** theo hợp đồng của chúng.

**Không sửa race bằng `Thread.sleep(...)` hoặc thêm logging**. Chúng có thể thay đổi timing nhưng không phải thiết kế đồng bộ có thể chứng minh đúng.

### 4.4 Ordering

Compiler/JVM/CPU có thể thực hiện tối ưu hóa và tái sắp xếp trong giới hạn JMM. Điều cần xác định là **thứ tự quan sát được** giữa các thread qua cơ chế đồng bộ, không phải giả định source code ở mọi thread sẽ được đọc như một chuỗi chung tuyệt đối.

Một aspect đọc policy mutable với nhiều field cần snapshot nhất quán để tránh:
- Đọc `limit` phiên bản mới nhưng `policyVersion` phiên bản cũ.
- Đọc `enabled` true trong before và false ở after theo hai cấu hình khác nhau.
- Áp dụng tenant của invocation A cho dữ liệu B.

### 4.5 Deadlock và contention

Thêm khóa để ngăn race vẫn có thể gây lỗi:
- **Deadlock:** aspect A giữ L1 rồi gọi B cần L2; thread khác giữ L2 rồi gọi A cần L1.
- **Lock convoy/contension:** một global lock bao quanh `proceed()` làm tất cả request bị tuần tự hóa; đặc biệt tệ khi target thực hiện I/O.
- **Reentrancy:** advice cùng thread tái nhập một chuỗi khác; khóa hoặc state machine phải tính tới điều này.
- **Starvation:** một nhóm thread liên tục không được thực thi phần quan trọng.

Không khóa toàn bộ lời gọi chỉ vì cần tăng một bộ đếm. Nếu đủ, chỉ bảo vệ **một thao tác cập nhật nhỏ**; để `proceed` thực thi ngoài khóa.

## 5. Bảng chọn kỹ thuật lưu state

| Nhu cầu | Cách tiếp cận | Giới hạn cần nhớ |
| --- | --- | --- |
| Thời gian bắt đầu một invocation | Biến local | Không kéo dài qua async completion nếu không giữ context đúng |
| Cấu hình chỉ đọc | Object immutable dùng chung | Những object tham chiếu bên trong cũng phải immutable theo hợp đồng |
| Bật/tắt tính năng động | `AtomicReference<Policy>` hoặc giá trị volatile thích hợp | Snapshot phải nhất quán, không thay nhiều mutable field riêng lẻ |
| Đếm attempts chính xác trên một JVM | `AtomicInteger` / `AtomicLong` | Theo phạm vi instance; không tự là tổng toàn cụm |
| Tổng metric chịu ghi rất nhiều | `LongAdder` | `sum()` dưới cạnh tranh không là snapshot nguyên tử toàn bộ |
| Ánh xạ key tới state | `ConcurrentHashMap` và thao tác atomic phù hợp | Một chuỗi nhiều thao tác/map entries không tự là transaction |
| Máy trạng thái nhiều field | `synchronized`, lock hoặc immutable CAS state | Phải bảo toàn bất biến cho toàn nhóm field |
| Ngữ cảnh một request logic | Context tường minh, snapshot bất biến | Thread-local không tự đi theo async hoặc remote request |
| Cache/rate limit toàn cụm | Store chuyên trách/distributed coordination | Chọn consistency, TTL, partition, failure mode |
| Trạng thái theo target | Per-target instance hoặc registry keyed đúng domain | Một target vẫn có thể bị nhiều thread cùng gọi |
| Kênh log/metric | Sink có thread-safe contract | Không giả định mọi logger/exporter tự có cùng bảo đảm |

Không có lựa chọn “đồng thời tốt nhất” cho mọi aspect. Phương án phụ thuộc vào **bất biến cần giữ**, tốc độ, contention, vòng đời và khả năng giải thích cho người vận hành.

## 6. Ví dụ Java 17: hai lời gọi, một aspect instance, kết quả xác định

Ví dụ dưới đây có **hai lời gọi đồng thời** đi qua **cùng một instance aspect**. Một aspect lưu bộ đếm `int` và cố ý đồng bộ điểm đọc của hai thread bằng `CyclicBarrier`, để minh họa **lost update** một cách xác định. Một aspect khác dùng `AtomicInteger` đếm đúng số attempts. Một aspect không trạng thái chỉ dùng local `label` theo invocation.

**Quan trọng:** `CyclicBarrier` bên trong `UnsafeCounterAspect` là **thiết bị thử nghiệm tạo lịch xen kẽ**, tuyệt đối không phải kỹ thuật nên dùng trong advice production; nếu chỉ có một lời gọi, barrier hai bên có thể khiến nó chờ mãi. Việc sử dụng barrier đảm bảo **hai task đã đọc cùng giá trị cũ trước khi có task nào ghi**, nên có thể quan sát chính xác kết quả sai.

Lưu file `SharedAspectConcurrencyDemo.java`:

~~~java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class SharedAspectConcurrencyDemo {
    @FunctionalInterface
    interface Work {
        String execute(String id);
    }

    static final class Business implements Work {
        @Override
        public String execute(String id) {
            if ("bad".equals(id)) {
                throw new IllegalArgumentException("bad request");
            }
            return "ok:" + id;
        }
    }

    // Chỉ dùng cho demo 2 thread: cố ý tạo lost update.
    static final class UnsafeCounterAspect {
        private int calls;
        private final CyclicBarrier bothHaveRead = new CyclicBarrier(2);

        void before() {
            int previouslySeen = calls;

            try {
                bothHaveRead.await();
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(error);
            } catch (BrokenBarrierException error) {
                throw new IllegalStateException(error);
            }

            calls = previouslySeen + 1;
        }

        int calls() {
            return calls;
        }
    }

    // Một instance dùng chung, nhưng cập nhật count bằng atomic.
    static final class SafeCounterAspect {
        private final AtomicInteger attempts = new AtomicInteger();

        String around(Supplier<String> proceed) {
            attempts.incrementAndGet();
            return proceed.get();
        }

        int attempts() {
            return attempts.get();
        }
    }

    // Stateless: mỗi invocation có một biến cục bộ.
    static final class StatelessLabelAspect {
        String around(String id, Supplier<String> proceed) {
            String localLabel = "[" + id + "]";
            return localLabel + proceed.get();
        }
    }

    static Work withAll(
            Work target,
            UnsafeCounterAspect unsafe,
            SafeCounterAspect safe,
            StatelessLabelAspect labels) {
        return id -> {
            unsafe.before();
            return labels.around(
                    id, () -> safe.around(() -> target.execute(id)));
        };
    }

    static Work withoutUnsafe(
            Work target,
            SafeCounterAspect safe,
            StatelessLabelAspect labels) {
        return id -> labels.around(
                id, () -> safe.around(() -> target.execute(id)));
    }

    public static void main(String[] args) throws Exception {
        Work target = new Business();

        UnsafeCounterAspect unsafe = new UnsafeCounterAspect();
        SafeCounterAspect safe = new SafeCounterAspect();
        StatelessLabelAspect labels = new StatelessLabelAspect();

        Work shared = withAll(target, unsafe, safe, labels);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<String> first =
                    executor.submit(() -> shared.execute("A"));
            Future<String> second =
                    executor.submit(() -> shared.execute("B"));

            // Lấy Future theo thứ tự đã submit, không theo lịch thread.
            System.out.println("RESULT " + first.get());
            System.out.println("RESULT " + second.get());
        } finally {
            executor.shutdownNow();
        }

        System.out.println("UNSAFE calls=" + unsafe.calls());
        System.out.println("SAFE attempts=" + safe.attempts());

        // Nhánh lỗi dùng cùng safe/labels, không dùng barrier demo.
        Work safeOnly = withoutUnsafe(target, safe, labels);
        System.out.println("CASE error");
        try {
            safeOnly.execute("bad");
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }
        System.out.println("SAFE attempts=" + safe.attempts());
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac SharedAspectConcurrencyDemo.java
java SharedAspectConcurrencyDemo
~~~

Stdout được xác định bởi mã và hai `Future.get()`:

~~~text
RESULT [A]ok:A
RESULT [B]ok:B
UNSAFE calls=1
SAFE attempts=2
CASE error
CALLER bad request
SAFE attempts=3
~~~

### 6.1 Vì sao bộ đếm không an toàn bằng 1?

Trong `UnsafeCounterAspect.before()`:
1. T1 đọc `calls=0` vào `previouslySeen`.
2. T2 đọc `calls=0` vào `previouslySeen`.
3. Barrier cho cả hai qua sau khi **cùng đọc**.
4. T1 ghi `1`; T2 cũng ghi `1`, theo thứ tự nào cũng cho giá trị cuối `1`.
5. `Future.get()` hoàn thành giúp thread chính quan sát các hành động của task theo hợp đồng concurrent library.

Ở production không có barrier, `calls++` có thể đôi khi cho 2 và đôi khi mất lượt. Kịch bản được dựng để **chứng minh lịch gây mất cập nhật**, chứ không dự đoán mọi lần chạy thật luôn mất đúng một lượt.

### 6.2 Vì sao bộ đếm an toàn bằng 2 rồi 3?

`SafeCounterAspect` lưu **một** `AtomicInteger`. Cả T1 và T2 gọi `incrementAndGet()`, hai increment được đồng bộ nguyên tử, nên sau khi cả hai hoàn tất, `attempts=2`.

Sau đó `safeOnly.execute("bad")` cũng đi qua **cùng instance safe**, tăng lên 3 **trước khi target ném ngoại lệ**. Vì thế đây là bộ đếm **attempts**, không phải successes. Nếu muốn đếm thành công, phải tăng sau khi `proceed.get()` trả về bình thường và đặt tên metric phù hợp.

### 6.3 Vì sao kết quả A và B không bị lẫn?

`StatelessLabelAspect` tạo `localLabel` ở **stack frame của invocation**. T1 giữ `[A]`, T2 giữ `[B]`, không có field mutable như `lastId` để hai thread tranh nhau. Có một instance `labels` duy nhất được dùng bởi cả hai mà kết quả vẫn đúng.

`Future.get()` được gọi theo thứ tự `first`, `second` để stdout có thứ tự **cố ý**, không giả định task A thực hiện xong trước task B.

### 6.4 Đây là AOP mô phỏng, không là weaving toàn cục

Chương trình dùng **wrapper** để lắp chuỗi advice vào `Work.execute`. Nó không khai báo pointcut của một bộ weaver hay instrument bytecode của `Business`. Nếu code gọi trực tiếp `target.execute(...)`, nó **bypass các wrapper**. Trong mô hình weaving trực tiếp method execution, tập join point có thể khác.

Tính an toàn của `AtomicInteger` không phụ thuộc vào cú pháp AOP; nó là đặc tính của cơ chế cập nhật state trong Java. Phạm vi áp dụng advice mới quyết định **những lần gọi nào được đếm**.

## 7. Around advice, `proceed` và trạng thái từng invocation

Một around advice thường cần nhớ:
- Mốc bắt đầu.
- Số lần retry trong **lần gọi logic** này.
- Context tracing.
- Một status ghi sau completion.
- Thông tin để cleanup trong `finally`.

Nếu mọi dữ liệu này chỉ thuộc một invocation, dùng local/closure thường đơn giản nhất:

~~~java
// MẢNH MINH HỌA, không phải lớp chạy độc lập.
String around(java.util.function.Supplier<String> proceed) {
    long start = System.nanoTime();
    try {
        return proceed.get();
    } finally {
        long duration = System.nanoTime() - start;
        emitLatency(duration);
    }
}
~~~

`finally` chạy khi `proceed` trả bình thường hoặc ném exception đồng bộ, nên thích hợp cho cleanup quanh đoạn xử lý **đồng bộ**. Nếu method trả `CompletionStage` ngay, `finally` có thể chạy **trước khi tác vụ bất đồng bộ hoàn tất**. Muốn đo end-to-end completion, cần buộc xử lý vào completion hook hoặc API async phù hợp.

### 7.1 Không dùng shared field làm continuation

Sai hướng:

~~~text
aspect.currentProceed = thisInvocation.proceed
aspect.currentArgs = args
...
aspect.currentProceed()
~~~

T2 có thể thay `currentProceed` khi T1 đang giữ instance aspect, khiến T1 tiếp tục lời gọi của T2 hoặc dùng args sai. Đây là lỗi nghiêm trọng cả về tính đúng đắn và bảo mật.

Mỗi invocation nên giữ continuation/args/context trong **tham số hoặc local state**, trừ khi một state holder có key/scope và đồng bộ đúng được thiết kế rõ ràng.

### 7.2 Multiple proceeds và retry

Trong một số mô hình AOP, around advice có thể gọi continuation nhiều lần. Mỗi lần có thể lặp nghiệp vụ, side effects, transaction hoặc advice bên trong. Nếu cần retry:
- State số attempt nên thuộc **một request logic** hoặc workflow được xác định.
- Dùng deadline và giới hạn attempts.
- Phân loại lỗi transient, không retry vô hạn.
- Phân biệt `requestCount`, `attemptCount`, `executionCount`.
- Yêu cầu idempotency/dedup nếu thao tác có tác dụng phụ.
- Kiểm tra thứ tự `Retry(Transaction(Target))` và `Transaction(Retry(Target))`.

Một bộ đếm dùng chung đúng thread-safe vẫn có thể **đếm sai đơn vị**, nếu đặt vào sai vị trí của chuỗi advice.

## 8. Đồng thời không có nghĩa mọi advice chạy cùng một lúc

Một aspect có thể thực hiện một thao tác blocking, nhưng không nên giả định toàn bộ hệ thống bị tuần tự hóa. Cần xét ranh giới:
- Advice dùng shared state và khóa quanh đoạn cập nhật nhỏ.
- Advice gọi `proceed` có I/O lâu.
- Interceptor khác bên ngoài có thể short-circuit.
- Một callback từ target có thể quay lại advice trên cùng hoặc thread khác.
- Một logger/exporter có queue và thread nội bộ.

Ví dụ chuỗi:

~~~text
Authorization(Cache(Metrics(Target)))
~~~

Nếu Cache trả hit, Metrics bên trong không được vào. **Thread-safe** không làm Metrics tự thấy cache hit. Nếu Auth dùng shared boolean `lastAllowed` thiếu phân vùng, cache hit còn có thể dùng quyền của caller khác.

Vì vậy kiểm thử cần cả **concurrency correctness** lẫn **coverage correctness**: đúng invocation được vào, đúng thứ tự/nhánh, state đúng scope.

## 9. Chọn AtomicInteger, LongAdder, locks hay immutable snapshot?

### 9.1 AtomicInteger cho một counter chính xác

~~~java
import java.util.concurrent.atomic.AtomicInteger;

final class AttemptCounter {
    private final AtomicInteger attempts = new AtomicInteger();

    int recordAttempt() {
        return attempts.incrementAndGet();
    }

    int snapshot() {
        return attempts.get();
    }
}
~~~

Đây là **mảnh khai báo riêng**. `incrementAndGet` có linearization point và trả số mới; phù hợp khi cần thứ tự cập nhật trên một biến. Nếu có nhiều JVM, mỗi object đếm **trong phạm vi instance/JVM**, không tạo một counter phân tán.

### 9.2 LongAdder cho thống kê contention cao

~~~java
import java.util.concurrent.atomic.LongAdder;

final class ThroughputCounter {
    private final LongAdder attempts = new LongAdder();

    void increment() {
        attempts.increment();
    }

    long approximateSnapshot() {
        return attempts.sum();
    }
}
~~~

Đây là **mảnh riêng**, không thay thế lớp trong demo. `LongAdder` tối ưu cho nhiều cập nhật tranh chấp; giá trị `sum()` khi đang concurrent **không phải snapshot nguyên tử tuyệt đối**. Không dùng nó khi cần cấp ID duy nhất hoặc đảm bảo đếm chính xác tại mọi thời điểm xen kẽ.

### 9.3 Khóa cho bất biến nhiều field

Một máy trạng thái circuit breaker có thể đồng thời cập nhật `status`, `failures`, `openedAt`. Nếu các field phải nhất quán như một giao dịch trong bộ nhớ, cần khóa hoặc chuyển trạng thái immutable bằng CAS đúng cách. Chỉ thêm `volatile` riêng lẻ chưa đảm bảo invariant toàn bộ.

**Tránh giữ khóa khi gọi `proceed` hoặc gọi service không kiểm soát**, vì có thể gây deadlock, reentrancy và contention cực lớn. Thông thường cập nhật state ngắn trong vùng bảo vệ, rồi gọi nghiệp vụ ngoài khóa.

### 9.4 Cấu hình động bất biến

Nếu advice cần policy có thể thay đổi:

~~~java
record Policy(boolean traceEnabled, int limit) {}

java.util.concurrent.atomic.AtomicReference<Policy> current =
        new java.util.concurrent.atomic.AtomicReference<>(
                new Policy(false, 100));
~~~

Đây là **mảnh khai báo**, được đặt trong context phù hợp của lớp hoặc method. Một invocation có thể lấy `Policy policy = current.get()` **một lần**, rồi dùng snapshot ấy xuyên suốt xử lý. Tránh lần đọc trước lấy trace flag phiên bản cũ, lần đọc sau lấy limit phiên bản mới mà logic yêu cầu chúng đi cùng nhau.

Cấu hình mới phải được validate trước khi publish; `AtomicReference` không làm đối tượng mutable chứa bên trong tự thread-safe.

## 10. ThreadLocal, context và bảo mật trong thread pool

Một phương pháp quen thuộc là dùng `ThreadLocal` để giữ correlation ID. Nhưng `ThreadLocal` là **per Java thread**, không phải per logical request. Thread pool có thể tái sử dụng thread cho request khác, và một request async có thể nhảy qua nhiều thread.

Nếu quên cleanup, user B có thể đọc context cũ của user A. Nếu lưu token hoặc secret, hậu quả nghiêm trọng hơn một dòng log sai.

Mẫu quản lý context:

~~~java
// MẢNH MINH HỌA: TRACE_ID được khai báo trong cùng lớp.
static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

static void withTrace(String id, Runnable action) {
    String previous = TRACE_ID.get();
    TRACE_ID.set(id);
    try {
        action.run();
    } finally {
        if (previous == null) {
            TRACE_ID.remove();
        } else {
            TRACE_ID.set(previous);
        }
    }
}
~~~

Phục hồi `previous` giúp nested scope đúng khi một advice tái nhập. Không chỉ `set(null)` rồi mặc định không còn resource; `remove()` thể hiện ý định xóa value của thread khi không có scope ngoài.

**Quan trọng:** code trên không tự truyền context sang task thực thi trên executor khác. Đối với async, phải chọn cơ chế context propagation được hỗ trợ và truyền **dữ liệu tối thiểu**, không giữ nguyên cả HTTP request, user object hoặc secrets quá vòng đời cần thiết.

### 10.1 ThreadLocal không phải cách sửa shared-field race tổng quát

Chuyển `currentUser` từ field aspect sang `ThreadLocal` có thể tránh ghi đè giữa hai thread **trong một đoạn đồng bộ**, nhưng chưa giải quyết:
- Async completion trên thread khác.
- Scheduler dùng lại thread cho request khác.
- Nested invocation có context khác.
- Context cần hủy sau cancellation.
- Data propagation qua process/remote call.

Nếu có thể, **truyền context như tham số** hoặc snapshot của invocation vẫn dễ chứng minh hơn.

## 11. Reentrancy: một lời gọi có thể kích hoạt chính advice lại

Một LoggingAspect có pointcut quá rộng có thể gọi `Logger.write()`, mà `write()` cũng nằm trong tập điểm được chọn:

~~~text
Business -> LoggingAdvice
              |
              v
           Logger.write()
              |
              v
           LoggingAdvice (again)
              |
              +--> ...
~~~

Điều này có thể tạo đệ quy vô hạn ngay cả **một thread**. Khi nhiều thread, số sự kiện có thể tăng nhanh hơn và làm các shared buffers/queues quá tải.

**Giải pháp ưu tiên:** loại những helper/sink hạ tầng khỏi phạm vi advice quan sát chung, hoặc dùng một sink tầng thấp không quay lại đường proxy/weaving tương tự. Không dùng cờ guard để bỏ qua authorization, validation hay audit bắt buộc.

Nếu dùng reentrancy guard cho một concern **được phép giảm bớt**, phải restore context trong `finally` và tính tới async/thread pool. Một guard theo thread không chặn vòng đi qua queue/remote service rồi quay lại thread khác.

### 11.1 Tái nhập khác với concurrent invocation

- **Concurrency:** T1 và T2 vào cùng aspect instance.
- **Reentrancy:** một invocation kích hoạt lời gọi lồng nhau quay vào advice khi invocation ngoài chưa hoàn tất.
- **Recursion:** một đường gọi quay lại chính nó; có thể có base case hợp lệ hoặc vô hạn.

Một aspect có thể thread-safe cho nhiều thread nhưng **không reentrant-safe**. Ví dụ khóa `ReentrantLock` cho phép cùng thread lấy lại khóa, nhưng state machine của advice vẫn có thể bị ghi đè hoặc logic đi vào nhánh sai.

## 12. Stateful aspect theo target vẫn có thể bị gọi đồng thời

~~~text
Target A ----> Aspect instance A [counter A]
Target B ----> Aspect instance B [counter B]
~~~

Phân vùng state theo target giúp A/B không giẫm dữ liệu nhau. Tuy nhiên, nếu target A được nhiều thread dùng chung, counter A vẫn là shared mutable state. Per-target **không tự là per-invocation** và không bảo đảm thread safety.

Các câu hỏi cần hỏi:
- Một target có nhiều proxy trỏ tới không? State nên theo **proxy** hay **target**?
- Hai object biểu diễn cùng logical account có cần **chia sẻ** rate limit không?
- State được key theo **object identity** hay ID nghiệp vụ?
- Object target có thể bị garbage collect không, hay registry giữ strong reference mãi?
- Khi đổi target/phiên bản aspect, state cũ có migrate/reset không?
- Nếu cần tổng state toàn cụm, một aspect instance trong JVM có đủ không?

Không dùng `Map<Target, State>` vô hạn mà không có lifecycle/eviction. Nếu map giữ strong references, nó có thể giữ target sống và gây rò bộ nhớ; weak-key cũng cần hiểu giá trị có tham chiếu ngược tới key hay không.

## 13. Dữ liệu mutable bên ngoài aspect

Một advice có thể trông stateless:

~~~text
around invocation:
    policy.check(args)
    metrics.increment()
    return proceed()
~~~

Nhưng `policy` và `metrics` là dependency. Nếu chúng dùng `HashMap`, `ArrayList` hoặc bộ đếm mutable không đồng bộ trong một đối tượng dùng chung, đường gọi vẫn nguy hiểm.

Cần kiểm tra **toàn bộ chuỗi**:
1. Aspect instance và fields.
2. Các helper được tái sử dụng.
3. Metrics/logging/cache store.
4. Các callback và event listeners.
5. Context/ThreadLocal.
6. Target và trạng thái bên trong target (nếu advice gọi tới).
7. Bất kỳ global/static registry hoặc class loader scope nào.

**Dùng `final` cho tham chiếu** hữu ích cho immutability của cấu trúc tham chiếu, nhưng không tự giải quyết mutable state bên trong object đích.

## 14. Phạm vi đo metrics trong nhiều aspect đồng thời

Một hệ thống có thể có:

~~~text
Metrics(Retry(Transaction(Business)))
Retry(Transaction(Metrics(Business)))
~~~

Ở cấu trúc đầu, Metrics có thể đếm **lời gọi logic** và đo tổng thời gian qua nhiều attempts. Ở cấu trúc sau, Metrics có thể đếm **từng attempt**, tùy ranh giới continuation của công cụ.

Khi có nhiều request đồng thời, counter an toàn mới chỉ đảm bảo **không mất cập nhật**. Nó không thể tự đảm bảo **đếm đúng đơn vị** nếu đặt sai chỗ.

Tên các số liệu nên rõ:
- `incoming_requests`: số request qua boundary đã chọn.
- `attempts`: tổng số lượt thử có thể gồm retry.
- `successful_calls`: số invocation trả bình thường theo định nghĩa.
- `target_executions`: số lần target thật được vào.
- `cache_hits`: lần trả từ cache, có thể không chạy target.
- `completed_operations`: hoàn tất business hay async completion, không chỉ trả future.

Nếu outer cache short-circuit, metric bên trong không chạy; nếu logging dùng thread-local trace ID từ request trước, attribution có thể sai dù counter nguyên tử.

## 15. Đồng thời, exception và cleanup

Một shared aspect có thể cùng lúc xử lý nhánh thành công của T1 và nhánh lỗi của T2. Vì vậy:
- Không lưu `lastException` dùng chung như thông tin lỗi của invocation hiện tại.
- Không lưu `success=true` vào field aspect rồi dùng trong `finally` nếu một invocation khác có thể thay nó.
- Dùng `try/finally` cho cleanup **riêng invocation**.
- Nếu advice phát sinh exception, không vô tình che exception gốc, đặc biệt từ logging/exporter không bắt buộc.
- Nếu checked exceptions/return type bị advice biến đổi, tuân thủ hợp đồng phương thức.
- Không thay toàn bộ return value/exception chỉ để “khắc phục race” nếu như vậy làm sai nghiệp vụ.

Với phương thức trả `CompletionStage`, phần advice sau khi nhận stage **chưa chắc là kết thúc của công việc**. Muốn ghi lỗi/latency của công việc async, phải xử lý đúng callback completion và propagation, không gắn state tạm vào một shared field rồi đợi callback.

### 15.1 Khác nhau giữa fail-open và fail-closed

Một logging/metrics concern không bắt buộc có thể có chính sách **bỏ qua ghi nhận khi sink lỗi**, nhưng một aspect kiểm tra quyền hoặc audit bắt buộc có hợp đồng khác. Không dùng cùng một `try/catch` nuốt mọi lỗi của mọi concern.

Nếu policy bảo mật cần fail-closed, việc một shared mutable flag race dẫn tới “allow” khi không kiểm chứng được là lỗi nghiêm trọng. Quy tắc bảo mật phải độc lập với trạng thái tình cờ của invocation trước.

## 16. Chiến lược kiểm thử concurrent advice

Một test đơn luồng có thể pass hàng nghìn lần nhưng vẫn không phát hiện race. Cần kiểm tra:

| Ca | Điều cần chứng minh |
| --- | --- |
| Nhiều thread dùng chung aspect instance | Không ghi đè invocation-local state |
| Counter đơn giản | Tổng attempts không bị lost update |
| Trả giá trị của A/B cùng lúc | Không đổi args/result giữa hai caller |
| Target throw trong một thread | Error state không rò sang thread khác |
| Nested invocation | Local context không bị ghi đè bởi lần lồng nhau |
| Snapshot config giữa call | Mỗi invocation dùng một policy nhất quán |
| Cùng target, nhiều caller | Per-target state được đồng bộ đúng |
| Thread pool tái sử dụng | Không mang context/user từ request trước |
| Async completion ở thread khác | Tracing/cleanup đúng thời điểm, context đúng |
| Retry nhiều lần | Không double-count sai định nghĩa |
| Cache hit/short-circuit | Coverage và security không bị bỏ qua |
| Logging sink lỗi | Không tạo vòng reentrancy/log storm |
| Lock order khác nhau | Không deadlock |
| Nhiều JVM | State local và distributed aggregate được phân biệt |
| Rollout aspect mới | State migrate/reset theo chính sách, không trộn phiên bản |
| Sensitive input | Không log hoặc giữ token/PII ngoài hợp đồng |

### 16.1 Dùng điểm đồng bộ để tái hiện race một cách có kiểm soát

`CountDownLatch`, `CyclicBarrier` và `Future.get()` giúp viết bài kiểm thử có các điểm xen kẽ rõ thay vì may rủi do scheduler. Nhưng **đừng chèn barrier bắt buộc hai bên vào advice production**: một request cô lập có thể bị chặn vĩnh viễn.

Để kiểm tra code thực tế, dùng stress tests với nhiều lần lặp, các assertions về **bất biến cuối**, race testing phù hợp và giám sát thread dumps khi nghi deadlock. Một test chỉ thấy log đúng thứ tự không thay thế kiểm tra dữ liệu.

### 16.2 Không tạo yêu cầu thứ tự tổng vô ích

Hai invocation độc lập có thể hoàn tất theo thứ tự B rồi A. Điều cần giữ là:
- Kết quả của A thuộc về A, kết quả B thuộc về B.
- Thứ tự advice của **mỗi invocation** đúng hợp đồng.
- Shared counters/state thỏa invariant.
- Không lộ context hoặc dữ liệu.
- Những thao tác có quan hệ nghiệp vụ (transaction/order) được đồng bộ thích hợp.

Trừ khi ứng dụng **có yêu cầu thứ tự toàn cục** thật sự, không đặt một global lock quanh mọi advice chỉ để log hiển thị thành một hàng đẹp.

## 17. Checklist thiết kế shared aspect

Trước khi triển khai một aspect dùng chung:

- [ ] Xác định aspect được khởi tạo **một lần, theo target, flow hay scope nào**.
- [ ] Xác định **những thread nào** có thể vào instance đồng thời.
- [ ] Liệt kê tất cả instance/static fields và mutable dependencies.
- [ ] Đưa request-local data về tham số/local/immutable context.
- [ ] Không giữ principal/tenant/current request trong shared field tạm.
- [ ] Chọn atomic/lock/immutable snapshot cho state thật sự phải chia sẻ.
- [ ] Không hiểu nhầm `volatile` là bảo đảm `counter++` nguyên tử.
- [ ] Với nhiều field, thiết kế invariant và cách đọc snapshot nhất quán.
- [ ] Không giữ khóa khi gọi `proceed` hoặc callback ngoài không kiểm soát.
- [ ] Biết số liệu đang đếm request, attempt, execution hay success.
- [ ] Nếu dùng `ThreadLocal`, restore/remove trong `finally` và kiểm tra async.
- [ ] Kiểm tra pointcut không tự chặn logger/metric sink gây recursion.
- [ ] Giới hạn cache/registry và quản lý retention, eviction, memory.
- [ ] Không suy rằng một AtomicInteger giải quyết state toàn cụm.
- [ ] Test concurrency, reentrancy, exception, cancellation, short-circuit.
- [ ] Đo overhead/lock contention và hoạt động hạ tầng quan sát.
- [ ] Kiểm tra chính sách bảo mật và audit không bị bypass.
- [ ] Có cách phát hiện lỗi, rollback và kiểm chứng version aspect lúc deploy.

## 18. Những ngộ nhận phổ biến

1. **“Một aspect instance thì advice tự chạy tuần tự.”** Không: nhiều thread có thể vào cùng object.
2. **“Một aspect stateless là không có tác dụng phụ.”** Không: có thể gửi log/metric nhưng không giữ mutable invocation state.
3. **“`final` field đồng nghĩa dependency thread-safe.”** Sai nếu object được tham chiếu vẫn mutable.
4. **“`volatile int x; x++` là atomic.”** Sai: tăng gồm nhiều bước.
5. **“Counter `AtomicInteger` là số liệu toàn cụm.”** Không nếu mỗi JVM có instance riêng.
6. **“LongAdder luôn cho snapshot chính xác tức thời.”** Không với các lần tăng đang chạy.
7. **“Per-target nghĩa chỉ một thread.”** Một target dùng chung vẫn có concurrent calls.
8. **“Dùng `ThreadLocal` sẽ là per-request trong mọi hệ thống.”** Thread pool/async phá giả định đó.
9. **“Cứ dùng `synchronized` bao `proceed` là giải quyết hết.”** Có thể gây contention và deadlock.
10. **“Lời gọi sau của T1 chắc dùng `startedAt` của T1.”** Không nếu mốc được giữ trong shared field.
11. **“Một lúc chỉ có một after advice chạy.”** Nhiều invocation có thể đi vào after/error/finally đồng thời.
12. **“Concurrent logs không theo thứ tự nghĩa dữ liệu sai.”** Phải kiểm tra invariant, không suy từ log xen kẽ.
13. **“Retry chỉ cần đếm attempts nguyên tử.”** Còn idempotency và transaction boundary.
14. **“Kết quả async trả về là công việc đã hoàn tất.”** Thường chưa; cần completion hook đúng.
15. **“Guard bỏ qua advice tái nhập phù hợp mọi concern.”** Có thể bỏ qua security/audit bắt buộc.
16. **“Không thấy race ở test lần đầu nghĩa an toàn.”** Race có thể cần interleaving hiếm.
17. **“Chọn ConcurrentHashMap là mọi thao tác nhiều bước tự atomic.”** Không: phải dùng phép cập nhật/bảo vệ đúng hợp đồng.
18. **“Càng ít aspect instance càng luôn nhanh.”** Contention của shared mutable state có thể lớn hơn chi phí tạo/lưu instance.
19. **“Đọc config mới nhiều lần trong một request luôn tốt.”** Có thể tạo một request với policy nửa cũ nửa mới.
20. **“Bảo vệ counter là bảo vệ toàn bộ hợp đồng nghiệp vụ.”** Cần cả coverage, result/exception, side effects, privacy và scope đúng.

## 19. Câu hỏi ôn tập

**Câu 1.** Một instance aspect dùng chung cho 100 threads, advice chỉ tính duration bằng biến local rồi gọi metrics sink thread-safe. Đây có phải một thiết kế hợp lý?

**Đáp:** có thể hợp lý. Biến local không bị các invocation khác ghi đè; metrics sink phải thật sự giữ hợp đồng thread-safe, và phạm vi đo phải phù hợp sync/async.

**Câu 2.** Tại sao `volatile int calls` cộng bằng `calls++` chưa giải quyết lost update?

**Đáp:** volatile giúp visibility/ordering theo quy tắc JMM, nhưng read–modify–write không trở thành một thao tác nguyên tử. Dùng `AtomicInteger.incrementAndGet()` hoặc đồng bộ phù hợp.

**Câu 3.** Có một aspect per-target với counter trên target A, nhiều thread cùng gọi A. Có cần đồng bộ counter không?

**Đáp:** có nếu yêu cầu cập nhật chính xác. Per-target chỉ phân vùng state giữa A/B, không phân vùng giữa các thread trên cùng A.

**Câu 4.** Aspect stateless gọi một helper ghi vào `HashMap` mutable dùng chung không khóa. Toàn chương trình có an toàn không?

**Đáp:** không thể kết luận an toàn. Stateless của bản thân aspect không thay thế thread-safety của dependency được gọi.

**Câu 5.** Nếu advice dùng `ThreadLocal` cho correlation ID rồi xử lý async qua thread pool, có tự động giữ ID đúng không?

**Đáp:** không. Phải dùng cơ chế context propagation phù hợp và cleanup khi hoàn thành, kể cả cancellation/error.

**Câu 6.** Trong ví dụ, hai lần gọi concurrent đều chạy xong nhưng `unsafe.calls() == 1`. Điều gì được chứng minh?

**Đáp:** mất cập nhật do hai invocation cùng đọc 0 rồi cùng ghi 1. `Future.get()` không biến những bước cập nhật trước đó thành nguyên tử; nó chỉ giúp đợi/quan sát kết quả task.

**Câu 7.** Một `SafeCounterAspect` tăng `attempts` trước `proceed`, target ném lỗi. Counter có tăng không?

**Đáp:** có. Vì đây là counter cho **attempts**, không phải successes; một lần gọi đi tới aspect rồi ném lỗi vẫn là attempt.

**Câu 8.** Nếu Metrics nằm trong Cache, cache hit trả sớm, AtomicInteger có tự đếm cache hit không?

**Đáp:** không. Advice không được gọi trên nhánh đó. Thread-safety không thay thế đúng vị trí interception.

**Câu 9.** Shared AuthorizationAspect giữ `currentUser` field cho mỗi invocation. Nguy cơ gì?

**Đáp:** người dùng khác có thể ghi đè field khi concurrent, khiến kiểm tra quyền sai hoặc rò dữ liệu. Identity phải thuộc context của invocation và được xác minh từ nguồn tin cậy.

**Câu 10.** Khi nào nên dùng `LongAdder` thay `AtomicLong`?

**Đáp:** khi mục tiêu là thống kê tổng có contention cao và chấp nhận semantics snapshot của `sum()`; không dùng LongAdder nếu cần sequence ID hoặc yêu cầu nguyên tử cho từng giá trị trả về.

## 20. Kết luận

**Aspect dùng chung với nhiều lời gọi đồng thời** là thiết kế bình thường trong AOP, miễn các đường gọi có hợp đồng chia sẻ state rõ ràng:

1. **Giữ dữ liệu của invocation trong local/immutable context**, không đặt `currentRequest` hoặc `startedAt` vào shared field.
2. **Chia sẻ state có chủ đích**, chọn atomic, lock, state store hoặc immutable snapshot theo bất biến cần giữ.
3. **Phân biệt phạm vi và đơn vị đo**: per-instance, per-target, per-request, per-thread và toàn cụm không đồng nghĩa.
4. **Xem cả dependencies và lifecycle**: ThreadLocal, async, proxy bypass, reentrancy, caches, logging sinks và generated advice đều có thể làm thay đổi giả định đồng thời.
5. **Kiểm thử interleaving, outcome và security**: không chỉ thấy chương trình trả kết quả một lần là đủ.

Ghi nhớ: **một aspect dùng chung không bắt buộc phải có shared mutable state; nếu thật sự cần state dùng chung, hãy chứng minh đồng thời đúng bằng cấu trúc dữ liệu, bất biến và kiểm thử, không dựa vào lịch thực thi tình cờ.**

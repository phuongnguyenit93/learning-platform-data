# Biến khả biến, tranh chấp dữ liệu và tính nhìn thấy trong AOP

## 1. Một aspect có thể phục vụ nhiều luồng

Trong **Aspect-Oriented Programming (AOP)**, aspect mô tả một mối quan tâm xuyên cắt qua **pointcut** (quy tắc chọn join point) và **advice** (logic áp dụng). Logging, tracing, authorization, metrics, cache, retry hoặc audit có thể được kích hoạt từ rất nhiều invocation đồng thời. Nếu cùng một **aspect/interceptor instance** chứa **mutable fields**, các lời gọi đến từ nhiều luồng có thể đọc và ghi cùng vùng trạng thái.

~~~text
Thread A -> Target.method -> Shared aspect object
                                  |
                                  +-- mutable counter
                                  +-- mutable cache
                                  +-- current request field
                                  |
Thread B -> Target.method --------+
~~~

Bốn câu hỏi khác nhau cần hiểu:

1. **Mutability:** trạng thái có thể thay đổi sau khi khởi tạo hay không?
2. **Data race:** các memory accesses xung đột có thiếu quan hệ đồng bộ hóa thích hợp không?
3. **Visibility/ordering:** luồng khác có được bảo đảm nhìn thấy những writes đã diễn ra theo **Java Memory Model (JMM)** không?
4. **Atomicity:** một operation như tăng counter hay kiểm tra rồi cập nhật có được thực hiện như một bước không thể bị xen ngang về mặt logic không?

Ngoài data race còn có **race condition ở tầng nghiệp vụ**, khi từng thao tác riêng lẻ thread-safe nhưng chuỗi check-then-act không được bảo vệ như một đơn vị.

**Điểm quan trọng:** AOP không tự làm advice thread-safe. Việc bytecode đã weave, proxy được tạo, hay pointcut match chính xác không làm biến mất các quy tắc concurrency của Java.

Bài trình bày AOP nói chung, không mặc định mọi runtime đều dùng một aspect instance singleton. Java 17 được dùng cho demo chạy độc lập, không cần một compiler AOP cụ thể.

## 2. Phân loại trạng thái trong lời gọi AOP

| Nơi giữ trạng thái | Ví dụ | Hệ quả |
|---|---|---|
| Local trong một advice invocation | startNanos, local attempt index | Mỗi invocation có local riêng; object mà nó tham chiếu vẫn có thể chia sẻ |
| Field của aspect/interceptor | calls, currentActor, Map | Nếu aspect instance shared thì nhiều threads dùng chung |
| Field của target | balance, mutable list | Có thể bị nhiều threads thao tác, độc lập với cách weave |
| Collaborator của aspect | logger buffer, cache service | Có thể mutable dù reference field là final |
| Static/global state | static counter, registry | Có thể chia sẻ qua nhiều instances |
| ThreadLocal | request context theo thread | Có lifecycle và propagation riêng, không tự theo task async |

Một **final reference** trỏ đến mutable object vẫn không bảo đảm object đó immutable:

~~~java
final List<String> events = new ArrayList<>();
~~~

Đây là snippet minh họa cần imports/class context. Final làm reference field không được gán lại sau khi khởi tạo hợp lệ, nhưng ArrayList vẫn có thể bị mutate bởi nhiều luồng và không thread-safe nếu dùng đồng thời mà không có synchronization.

### 2.1. Local variables không biến shared object thành local

~~~java
List<String> localRef = sharedList;
localRef.add("event");
~~~

Biến localRef được giữ riêng theo invocation, nhưng các threads vẫn có thể cùng sửa **sharedList**. Cần quan sát **object graph** chứ không chỉ vị trí khai báo reference.

### 2.2. Stateless advice là ưu tiên hữu ích

Nếu một advice chỉ nhận argument, đo thời gian bằng biến local, gọi proceed rồi ghi vào một logger thread-safe được thiết kế đúng, việc review concurrency thường đơn giản hơn so với mutable fields như lastUser, lastStartTime hoặc currentRequest.

Tuy nhiên một advice không có mutable field vẫn có thể sử dụng **shared target** hoặc **mutable collaborator** không thread-safe.

## 3. Data race và race condition khác nhau

Ví dụ **data race**:

~~~java
int calls;

void before() {
    calls++;
}
~~~

Nhiều threads cùng increment một field không có synchronization; các memory accesses read/write xung đột có thể thiếu happens-before. Kết quả có thể mất cập nhật.

Ví dụ **race condition logic**:

~~~text
Thread A: account.hasFunds(100) -> true
Thread B: account.hasFunds(100) -> true
Thread A: account.withdraw(100)
Thread B: account.withdraw(100)
~~~

Giả sử các methods hasFunds và withdraw được synchronized **riêng từng method**, điều đó chưa bảo vệ nguyên tử toàn bộ chuỗi check-then-withdraw. Nếu invariant là “không bao giờ rút quá số dư”, cần một operation hoặc transaction đúng ở tầng sở hữu invariant.

Điều tương tự xảy ra trong advice:

- Rate limit kiểm tra counter rồi tăng counter.
- Cache kiểm tra miss rồi gọi target và put.
- Dedup đọc trạng thái rồi ghi marker.
- Security kiểm tra resource state rồi tiến hành update.
- Retry logic đọc shared attempt number rồi thay.
- Metrics cập nhật nhiều fields vốn cần nhất quán.

**Thao tác thread-safe riêng lẻ không tự biến workflow nhiều bước thành atomic.**

## 4. Lost update với phép tăng counter

Biểu thức:

~~~java
calls++;
~~~

Có ý nghĩa đọc giá trị cũ, tính cộng một, rồi ghi lại. Hai threads có thể xen kẽ:

~~~text
calls = 0
A đọc calls = 0
B đọc calls = 0
A tính 1
B tính 1
A ghi 1
B ghi 1
Kết quả: calls = 1 dù có hai lượt gọi
~~~

Nếu aspect dùng calls để đếm calls, metric sẽ thiếu. Nếu dùng nó để điều khiển số lần retry hoặc giới hạn truy cập, lỗi có thể ảnh hưởng quyết định nghiệp vụ.

### 4.1. Dùng volatile vẫn có thể mất lượt

~~~java
volatile int calls;

void before() {
    calls++;
}
~~~

Volatile có những bảo đảm về visibility và ordering, nhưng **không hợp nhất read–modify–write thành một thao tác nguyên tử**. Hai threads vẫn có thể cùng đọc 0 rồi ghi 1.

Đây là ranh giới quan trọng nhất của chủ đề: **visibility không bằng atomicity**.

## 5. Java Memory Model và happens-before

**Java Memory Model** mô tả quan hệ giữa các actions ở các threads, những đồng bộ hóa được nhận diện và những giá trị các reads có thể quan sát. Khái niệm **happens-before** cho phép lý giải việc một write được bảo đảm hiển thị đối với một read khác khi có quan hệ thích hợp.

Một số nguồn happens-before tiêu biểu:

- Program order giữa các actions trong cùng thread theo quy tắc JMM.
- Unlock monitor rồi lock tiếp theo trên **cùng monitor**.
- Volatile write rồi volatile read tương ứng theo synchronization order.
- Thread.start và Thread.join theo quy tắc JMM.
- Các concurrent APIs có memory-consistency effects, ví dụ Future.get, CountDownLatch và concurrent collections theo contract.
- Safe publication của object qua synchronized, volatile hoặc cách thiết lập final fields hợp lệ.

**Không suy rằng “happens-before” là đồng hồ thời gian thực duy nhất.** Đó là quan hệ ngữ nghĩa trong memory model.

### 5.1. Khi thiếu happens-before

Một thread có thể đọc stale state hoặc quan sát những giá trị mà code không hề dự tính là có thể thấy trong execution thiếu đồng bộ. Compiler/JIT/CPU được phép tối ưu trong phạm vi JMM; không được giả định các writes sẽ tự hiện ra đúng lúc chỉ vì chương trình chạy lâu.

Cũng không nên mô tả sai rằng “Java luôn giữ một bản copy vĩnh viễn cho mỗi thread”. Điều đúng cần nắm là **không có bảo đảm visibility cần thiết** nếu dùng shared mutable state sai.

### 5.2. Happens-before chưa đủ để bảo vệ compound invariant

Một volatile field có thể publish một immutable config snapshot, nhưng ba volatile fields riêng có thể bị đọc tại các thời điểm khác nhau, không tạo một snapshot nhất quán.

Một shared invariant gồm balance + pending + version thường cần lock hoặc atomic immutable state transition phù hợp, không chỉ các field được đánh dấu volatile.

## 6. Volatile dùng đúng chỗ

Ví dụ stop flag:

~~~java
private volatile boolean stopped;

void stop() {
    stopped = true;
}

void runLoop() {
    while (!stopped) {
        // Định kỳ kiểm tra điều kiện dừng.
    }
}
~~~

Đây là code minh họa, không là chương trình độc lập. Volatile hỗ trợ visibility/ordering cho flag, nhưng không tự hủy một I/O blocking hoặc một task đang chờ lock; cancellation/interruption phải được thiết kế phù hợp.

### 6.1. Volatile reference không bảo vệ nội dung object

~~~java
volatile MutableConfig config;
~~~

Nếu object MutableConfig tiếp tục được mutate từ nhiều threads không có synchronization, volatile chỉ trên reference **không khiến toàn bộ object graph thread-safe**.

Một mẫu tốt hơn là xây dựng **immutable snapshot**, publish reference và không mutate snapshot sau đó.

### 6.2. Config reload và in-flight invocation

Nếu policy thay đổi trong lúc một advice đang xử lý request, nên quyết định invocation có cần dùng một **config version nhất quán** hay có thể quan sát nhiều versions. Một local reference capture từ volatile Policy ở đầu invocation thường giúp dùng một snapshot duy nhất.

## 7. AtomicInteger và AtomicLong

Khi cần counter chính xác theo một instance:

~~~java
private final AtomicInteger calls = new AtomicInteger();

void before() {
    calls.incrementAndGet();
}
~~~

Đây là snippet cần import AtomicInteger và class context. incrementAndGet là atomic update cho counter. AtomicInteger/AtomicLong còn có các operation như get, compareAndSet, getAndIncrement.

Nhưng **AtomicInteger không tự biến một workflow thành transaction**. Ví dụ:

~~~text
if (counter.get() < limit):
    counter.incrementAndGet()
    allow()
~~~

Hai threads có thể cùng thấy dưới limit, sau đó cùng increment. Cần một CAS loop hoặc cơ chế synchronization để check-and-reserve thành **một quyết định logic nguyên tử**.

### 7.1. CAS và side effects

Với compare-and-set, một thread có thể phải thử lại khi expected value không còn đúng. Không đưa side effects không idempotent (charge, send email) vào phần tính toán có thể chạy lại mà không có giao thức an toàn.

### 7.2. Exact counter và lifecycle

Counter thuộc **aspect instance**. Nếu runtime có nhiều aspect instances (theo target, caller hoặc một scope riêng), đọc một counter chỉ đếm invocation vào instance đó, không mặc nhiên là tổng số toàn ứng dụng.

## 8. LongAdder dùng khi nào?

LongAdder hữu ích cho metric counter được cập nhật nhiều trong môi trường contention cao.

~~~java
private final LongAdder calls = new LongAdder();

void before() {
    calls.increment();
}
~~~

LongAdder thường được dùng để tăng throughput cập nhật, nhưng **sum không phải atomic snapshot đối với concurrent updates**. Vì vậy nó không phải lựa chọn phù hợp mặc định cho logic quyết định hard limit từng request.

Không khẳng định LongAdder luôn nhanh hơn AtomicLong; cần benchmark workload thật, tần suất đọc/ghi và yêu cầu consistency.

## 9. Synchronized và monitor identity

Khi cần bảo vệ compound state, một critical section có thể cần dùng synchronized:

~~~java
private final Object lock = new Object();
private long total;
private long failures;

void record(boolean failed) {
    synchronized (lock) {
        total++;
        if (failed) {
            failures++;
        }
    }
}
~~~

Đoạn mã minh họa cần class context. Nếu reader muốn snapshot nhất quán của total/failures, nó cũng cần cùng synchronization hoặc cơ chế snapshot có bảo đảm tương đương.

### 9.1. Proxy và target có thể là hai locks

Trong mô hình proxy wrapper P và target T là hai objects khác nhau:

~~~text
synchronized(P) khóa monitor P
synchronized(T) khóa monitor T
~~~

Hai locks không hợp nhất dù P.equals(T) được override trả true. Nếu advice khóa proxy còn target khóa chính target, chúng có thể không bảo vệ cùng invariant.

### 9.2. Giữ lock qua proceed là một quyết định lớn

~~~text
synchronized(sharedLock):
    proceed()  // Có thể I/O, lock khác hoặc callback
~~~

Cách này có thể serialize toàn bộ requests, tăng tail latency hoặc deadlock. Nếu chỉ đếm calls, chọn atomic counter/synchronized ngắn thay vì giữ global lock cho toàn operation.

### 9.3. Deadlock và lock order

~~~text
Thread A: giữ L1 rồi chờ L2
Thread B: giữ L2 rồi chờ L1
~~~

Nếu một aspect và target cùng lấy locks theo thứ tự ngược, có thể deadlock. Đặt chính sách lock order thống nhất và tránh gọi code không kiểm soát trong critical sections.

## 10. ReentrantLock và ownership

Với ReentrantLock:

~~~java
lock.lock();
try {
    return proceed();
} finally {
    lock.unlock();
}
~~~

Đây là snippet minh họa, cần định nghĩa lock/proceed. Chỉ unlock sau khi acquire thành công. Với tryLock hoặc lockInterruptibly cần kiểm tra return/InterruptedException và thread ownership.

ReentrantLock hỗ trợ cùng thread reenter theo contract, nhưng không tự giải quyết **AOP recursion** nếu một logging advice gọi logger được pointcut chọn lại.

## 11. ConcurrentHashMap: an toàn cấu trúc chưa chắc an toàn nghiệp vụ

Một mutable HashMap không phù hợp cho concurrent mutations không đồng bộ. Có thể dùng ConcurrentHashMap:

~~~java
ConcurrentHashMap<String, AtomicInteger> perOperation =
    new ConcurrentHashMap<>();

void count(String operation) {
    perOperation
        .computeIfAbsent(operation, key -> new AtomicInteger())
        .incrementAndGet();
}
~~~

Đây là snippet cần imports/class context. Nó phù hợp đếm theo key khi chấp nhận consistency theo từng atomic counter.

Tuy nhiên:

- Không phải mọi sequence read–check–put đều atomic.
- Không có transaction atomic qua nhiều keys.
- Values mutable bên trong vẫn phải được bảo vệ đúng.
- Iteration và tổng hợp counts dưới concurrent mutation không tự cho một snapshot cùng thời điểm.
- Mapping callbacks cần tuân thủ API và tránh recursive update vào cùng map hoặc I/O kéo dài.

Nếu cache dùng map để deduplicate một side effect không idempotent, còn cần chính sách **single-flight/idempotency**, không chỉ chọn concurrent collection.

## 12. Ví dụ Java 17: tạo lost update xác định và sửa bằng AtomicInteger

Chương trình **AspectConcurrencyDemo.java** dùng một object RacyAdvice có **volatile int calls**, một AtomicAdvice và một ContextAdvice. Nó mô phỏng around invocation nhưng không tự dệt bytecode.

Để tạo kết quả ổn định, **CyclicBarrier** khiến cả hai threads đọc calls trước khi ghi lại. Không dùng sleep hoặc kỳ vọng scheduler tình cờ gây race.

~~~java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class AspectConcurrencyDemo {
    @FunctionalInterface
    interface Work {
        int execute();
    }

    static final class RacyAdvice {
        volatile int calls;
        final CyclicBarrier barrier = new CyclicBarrier(2);

        int around(Work work) {
            int before = calls;
            try {
                barrier.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            } catch (BrokenBarrierException e) {
                throw new IllegalStateException(e);
            }
            calls = before + 1;
            return work.execute();
        }
    }

    static final class AtomicAdvice {
        final AtomicInteger calls = new AtomicInteger();

        int around(Work work) {
            calls.incrementAndGet();
            return work.execute();
        }
    }

    static final class ContextAdvice {
        final ThreadLocal<String> context = new ThreadLocal<>();

        void within(String label, Runnable body) {
            String previous = context.get();
            context.set(label);
            try {
                body.run();
            } finally {
                if (previous == null) {
                    context.remove();
                } else {
                    context.set(previous);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            RacyAdvice racy = new RacyAdvice();
            Future<Integer> r1 = pool.submit(() -> racy.around(() -> 7));
            Future<Integer> r2 = pool.submit(() -> racy.around(() -> 7));
            int sum1 = r1.get() + r2.get();
            System.out.println("racy-results=" + sum1);
            System.out.println("racy-calls=" + racy.calls);

            AtomicAdvice safe = new AtomicAdvice();
            Future<Integer> a1 = pool.submit(() -> safe.around(() -> 7));
            Future<Integer> a2 = pool.submit(() -> safe.around(() -> 7));
            int sum2 = a1.get() + a2.get();
            System.out.println("atomic-results=" + sum2);
            System.out.println("atomic-calls=" + safe.calls.get());
        } finally {
            pool.shutdown();
        }

        ContextAdvice scope = new ContextAdvice();
        scope.within("outer", () -> {
            System.out.println("context-outer=" + scope.context.get());
            scope.within("inner", () ->
                System.out.println("context-inner=" + scope.context.get())
            );
            System.out.println("context-restored=" + scope.context.get());
        });
        System.out.println("context-after=" + scope.context.get());

        try {
            scope.within("failure", () -> {
                throw new IllegalStateException("boom");
            });
        } catch (IllegalStateException e) {
            System.out.println("caught=" + e.getMessage());
        }
        System.out.println("context-after-failure=" + scope.context.get());
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 AspectConcurrencyDemo.java
java AspectConcurrencyDemo
~~~

**Stdout đã chạy kiểm chứng:**

~~~text
racy-results=14
racy-calls=1
atomic-results=14
atomic-calls=2
context-outer=outer
context-inner=inner
context-restored=outer
context-after=null
caught=boom
context-after-failure=null
~~~

### 12.1. Vì sao racy-calls = 1?

Hai invocation dùng **cùng instance RacyAdvice**. Mỗi thread đọc calls = 0 vào local before. Barrier đảm bảo cả hai đã đến đây trước khi một thread tiếp tục ghi. Cả hai sau đó thực hiện calls = 0 + 1, nên kết quả là 1.

**Barrier chỉ là công cụ test** ép một interleaving; không nên đặt một barrier đợi đúng hai threads bên trong advice thật. Nó cũng không làm phép increment trở thành atomic.

### 12.2. Vì sao atomic-calls = 2?

AtomicInteger.incrementAndGet thực hiện atomic update cho counter. Hai invocations đóng góp đủ hai increments; Future.get chờ completion và bảo đảm các memory consistency effects theo API.

**Không nên hiểu điều này là toàn bộ advice đã thread-safe** nếu những fields khác vẫn dùng mutable HashMap hoặc unsafe state.

### 12.3. Vì sao context-inner rồi context-restored?

ContextAdvice dùng ThreadLocal:

- Outer lưu previous null rồi set outer.
- Inner lưu previous outer rồi set inner.
- Inner finally restore outer.
- Outer finally remove vì trước đó null.

Đây là cách tránh làm mất outer context khi advice lồng nhau.

### 12.4. Vì sao context-after-failure null?

Body ném IllegalStateException nhưng finally trong within vẫn chạy. Context bị remove trước khi lỗi được caller catch. Điều này tránh rò request/user/tracing context khi worker thread được tái sử dụng.

### 12.5. Những giới hạn của demo

Nó chứng minh lost update trong một interleaving cụ thể, không chứng minh race luôn xuất hiện nếu bỏ barrier. Nó không đo hiệu năng. Context nested chạy ở một thread, không chứng minh ThreadLocal tự truyền sang task chạy ở executor. Nó là Java wrapper minh họa, không phải engine AOP cụ thể.

## 13. ThreadLocal: state theo thread, không theo request bất biến

Một advice sai:

~~~java
class UnsafeTrace {
    String currentUser;

    void before(String user) {
        currentUser = user;
    }

    void after() {
        System.out.println(currentUser);
    }
}
~~~

Nếu một UnsafeTrace instance phục vụ hai threads, request A có thể set user A, request B set user B, rồi request A log nhầm user B. Với security context, lỗi có thể nghiêm trọng hơn sai tracing.

### 13.1. Ưu tiên local state

Nếu around advice cần start timestamp và operation ID để tạo metric, lưu chúng trong **local variables của chính invocation** là cách đơn giản nhất. Nó tránh việc có một field currentStartTime chung giữa requests.

### 13.2. Khi cần ThreadLocal

ThreadLocal có thể phù hợp nếu nhiều helper sâu trong **cùng thread** cần truy cập context mà không nhận param trực tiếp. Nhưng phải:

- Set khi vào scope.
- Lưu previous value nếu có outer scope.
- Restore/remove trong finally.
- Tránh để request mới thấy context cũ trên thread pool.
- Không đặt shared mutable object vào ThreadLocal rồi coi nó được bảo vệ.

### 13.3. InheritableThreadLocal không sửa thread pool propagation

InheritableThreadLocal có semantics tại child thread creation. Pool threads được tạo trước hoặc tái sử dụng, nên context lúc task chạy không nhất thiết khớp context lúc thread được tạo. Không dựa vào nó như propagation tự động an toàn cho ExecutorService.

## 14. Async: context phải đi qua một boundary khác

~~~text
Caller Thread:
    set traceId = A
    submit task
    restore traceId cũ

Worker Thread:
    run task trên một thread khác
~~~

ThreadLocal không tự gắn traceId A sang worker. Cần capture một **immutable context snapshot** hoặc truyền parameters, sau đó install context hợp lệ ở worker trong một scope try/finally, rồi restore worker's previous value.

Đừng chuyển một mutable Map chưa thread-safe qua worker rồi cho hai threads cùng mutate. Nếu code trả CompletableFuture ngay lập tức, Logging after-returning của method khởi tạo future chỉ ghi nhận **submission/handle return**, không tự có nghĩa async task đã hoàn tất.

### 14.1. Thread-bound resource

Không được cleanup ReentrantLock, transaction context hoặc resource có thread affinity trên một thread khác nếu contract không cho phép. Context propagation khác resource ownership, cần thiết kế riêng.

### 14.2. Cancellation/exception

Một future bị cancel không bảo đảm worker đã ngừng dùng resource ngay. Phải xử lý completion/error/cancellation và cleanup đúng scope. Đừng nuốt InterruptedException hoặc làm rò ThreadLocal khi task throw.

## 15. Aspect instance lifecycle không đồng nghĩa thread confinement

Một số mô hình AOP hỗ trợ instance scope theo global/singleton-like, **per-this**, **per-target** hoặc **per-control-flow**. Những scope này phụ thuộc ngôn ngữ/engine và join point semantics.

Ví dụ một aspect **per-target** không được tự coi thread-safe:

~~~text
Thread A ----+
             +----> Shared target T ----> Aspect instance X
Thread B ----+
~~~

Cùng target T có thể được hai threads gọi đồng thời, nên mutable fields của X vẫn chia sẻ. Per-this gắn theo vai trò this của join point, cũng không tự đồng nghĩa “mỗi thread một aspect”.

Một aspect instance per-invocation có thể tránh shared instance field nhưng không bảo vệ **global collaborators, static caches hay target state**. Phải xác định object nào thực sự được chia sẻ.

## 16. Immutable snapshot và safe publication

Nếu policy có ba fields version, limit, enabled, đừng update từng mutable field rồi mong reader nhìn một trạng thái nhất quán.

Ví dụ một immutable record chứa primitives:

~~~java
record Policy(int version, int limit, boolean enabled) {}
~~~

Publish object mới qua volatile reference:

~~~java
private volatile Policy policy = new Policy(1, 10, true);

void reload() {
    policy = new Policy(2, 20, true);
}

void handle() {
    Policy snapshot = policy;
    // Dùng snapshot trong phạm vi invocation này.
}
~~~

Đây là snippets cần class context, không phải một chương trình độc lập. Volatile publication làm reader dùng một object Policy đã chuẩn bị; capture snapshot một lần giúp một request không đọc trộn nhiều versions.

Nếu Policy chứa reference đến mutable List, cần copy/bảo vệ List; một record không tự deep-immutable toàn bộ object graph.

### 16.1. Tránh this escape

Không publish reference đến một object đang xây dựng ra shared registry hoặc thread khác trước khi constructor hoàn tất mà không có protocol đúng. Final-field semantics có điều kiện; unsafe publication làm mất những bảo đảm reader cần.

## 17. Cache, dedup và atomicity của side effects

Một caching advice thường:

~~~text
if cache contains key:
    return cached
value = proceed()
cache[key] = value
return value
~~~

Hai threads có thể cùng miss và cùng proceed. Nếu target tạo side effect, có thể có duplicate. Chuyển HashMap thành ConcurrentHashMap bảo vệ các map operations theo API nhưng **không tự làm cả workflow đúng một lần**.

Cần xác định:

- Duplicate computation có được chấp nhận không?
- Có cần single-flight theo key không?
- Loader/mapping function có side effects hoặc reentrancy không?
- Cached value có immutable/thread-safe không?
- Có transaction version/invalidation policy không?
- Cache key dùng business identity hay proxy object reference?

Nếu caching có thể short-circuit target, counter advice **bên ngoài cache** sẽ khác counter advice **bên trong cache**. Phải đặt tên metric đúng boundary.

## 18. Metrics phải gắn đúng pointcut và precedence

Một request có thể đi qua RetryAround và thực thi target nhiều attempts:

~~~text
Caller -> RetryAround -> Target
                | 
                +-- proceed #1 fails
                +-- proceed #2 succeeds
~~~

Nếu một counter nằm ngoài Retry, nó có thể tăng một lần; nếu nằm bên trong, nó có thể tăng cho mỗi attempt. Cả hai có thể đúng theo mục đích metric nhưng không có cùng ý nghĩa.

Nên tách:

- Logical request count.
- Advice invocation count.
- Target execution count.
- Retry attempt count.
- Transaction committed count.
- Failure count theo từng boundary.

Atomic increments không khắc phục **sai điểm quan sát**. Khi đọc nhiều counters để tạo invariant, những reads riêng lẻ không nhất thiết là atomic snapshot của cả tập.

## 19. Lock scope, deadlock và reentrancy

Một aspect có thể vô tình serialize cả hệ thống nếu dùng shared lock bao proceed:

~~~text
synchronized(globalLock):
    log
    proceed()  // Có thể gọi I/O hoặc cần lock khác
~~~

Khi proceed chậm, mọi requests tranh lock. Khi target gọi ngược một method advice cần lock khác, có thể deadlock.

Một giải pháp là đặt critical section ngắn quanh đúng shared invariant; lưu thời gian và attempt number ở local state; chỉ dùng lock cho các operations thực sự cần phối hợp.

Nếu logging helper cũng được pointcut match, advice có thể reenter chính nó và tạo recursion. Reentrancy guard cần scope riêng và restore trong finally, không dùng một global boolean không synchronized.

## 20. Kiểm thử concurrency và visibility

Một test chạy thành công một lần không chứng minh code không có race.

Nên kết hợp:

1. **Deterministic interleavings** bằng CyclicBarrier/CountDownLatch để tái hiện read-modify-write sai.
2. **Load/stress tests** với nhiều threads và traffic patterns.
3. **Invariant assertions** (ví dụ reservations không vượt limit, counters không mất increments).
4. **Negative tests** cho pointcut không nên match.
5. **Nested ThreadLocal tests** cho previous context restore.
6. **Thread pool reuse** để phát hiện context leak sang request sau.
7. **Async propagation tests** giữa caller và Executor worker.
8. **Config reload tests** trong lúc nhiều invocations đang đọc.
9. **Concurrent cache tests** trên same key và nhiều keys.
10. **Lock order/deadlock tests** nếu có nested locks.
11. **Retry/exception fault injection** để xác nhận finally cleanup.
12. **Metrics semantics tests** khi cache hit, short-circuit hoặc retry làm số target calls khác số advice events.

### 20.1. Stress test không thay thế JMM reasoning

Một race có thể không xuất hiện ở một JVM run do scheduling. Cần chứng minh thuật toán đúng dưới interleavings được phép và sử dụng memory consistency primitives có contract rõ.

### 20.2. Benchmark khác correctness test

Nếu cần so chi phí volatile, AtomicLong, LongAdder và synchronized, đo bằng JMH hoặc benchmark tương đương với warmup, forks và workload hợp lệ. Ví dụ println hoặc một vòng main tùy ý không cho kết luận overhead đáng tin.

## 21. Bảng quyết định

| Nhu cầu | Công cụ/thiết kế | Cảnh báo |
|---|---|---|
| Per-invocation timestamp/attempt | Local variable | Object tham chiếu vẫn có thể shared |
| Counter chính xác một biến | AtomicInteger/AtomicLong | Compound invariant vẫn cần bảo vệ |
| Counter thống kê contention cao | LongAdder | sum không atomic snapshot khi đang updates |
| Nhiều fields có invariant chung | synchronized/Lock | Cùng lock cho read và write |
| Cache/counters theo key | ConcurrentHashMap + atomic values | Compound workflow không tự atomic |
| Config reload | Immutable snapshot + volatile reference | Không mutate snapshot sau publication |
| Context cùng thread | ThreadLocal + save/restore finally | Thread pool cleanup bắt buộc |
| Async context | Explicit immutable context handoff | Không tự kéo theo ThreadLocal |
| Per-target aspect state | Phân tích sharing của target | Một target có thể nhiều threads |
| Security context | Per-request immutable object | Không lưu currentUser trong shared field |
| Global circuit breaker | Atomic state machine/lock | Nhiều conditions cần invariant |
| Dedup side effects | Idempotency/single-flight protocol | ConcurrentMap một mình không đủ |

## 22. Các lỗi thường gặp

**Lỗi 1:** Coi aspect luôn dùng một thread và shared fields là local state.

**Lỗi 2:** Dùng volatile int với ++ rồi tin increment atomic.

**Lỗi 3:** Coi AtomicInteger khiến mọi state của advice thread-safe.

**Lỗi 4:** Coi final reference biến object mutable thành immutable.

**Lỗi 5:** Đưa HashMap không thread-safe vào shared aspect và cập nhật đồng thời.

**Lỗi 6:** Cho rằng ConcurrentHashMap làm mọi multi-key operation atomic.

**Lỗi 7:** Coi per-target aspect instance như per-thread instance.

**Lỗi 8:** Chuyển một shared object reference vào local rồi tin nó đã thread-confined.

**Lỗi 9:** Tin ThreadLocal tự propagate qua Executor/CompletableFuture.

**Lỗi 10:** Remove ThreadLocal ở nested scope và làm mất context của outer scope.

**Lỗi 11:** Đưa shared mutable List vào ThreadLocal rồi coi List thread-safe.

**Lỗi 12:** Dùng synchronized(proxy) và synchronized(target) như cùng một monitor.

**Lỗi 13:** Đếm outer advice mà đặt metric name là target executions.

**Lỗi 14:** Atomic get rồi atomic increment và coi check-then-act atomic.

**Lỗi 15:** Đo race bằng Thread.sleep rồi kết luận không có vấn đề.

**Lỗi 16:** Dùng volatile reference nhưng mutate những fields trong object không synchronized.

**Lỗi 17:** Giữ global lock qua network call và tạo contention/deadlock.

**Lỗi 18:** Quên cleanup context khi advice/target throw.

**Lỗi 19:** Coi thread-safe aspect nghĩa target cũng thread-safe.

**Lỗi 20:** Coi successful stress test đủ chứng minh không có data race.

## 23. Quy trình thiết kế aspect an toàn

1. Xác định scope của aspect/interceptor, target, proxy handler và collaborator.
2. Liệt kê mutable fields, maps, counters, globals, context objects.
3. Xác định reader/writer threads cho từng state.
4. Xác định **invariant**: exact counter, approximate metric, hard limit, config version, per-request context.
5. Ưu tiên stateless advice và local variables cho state riêng invocation.
6. Dùng volatile cho publication đúng ngữ nghĩa, không dùng nó như lock.
7. Dùng Atomic* cho atomic updates của từng biến theo contract.
8. Dùng synchronized/Lock hoặc một state machine đúng cho multi-step invariant.
9. Dùng concurrent containers cùng một giao thức compound operation đúng.
10. Dùng immutable context/snapshots khi cần chia sẻ dữ liệu.
11. Restore/remove ThreadLocal bằng finally; test nested và thread pool reuse.
12. Thiết kế context propagation qua async boundaries.
13. Tránh giữ lock lâu qua proceed hoặc các I/O khó kiểm soát.
14. Thử interleavings, retry, cancellation và failure paths.
15. Đo performance sau khi correctness đã được kiểm chứng.

## 24. Câu hỏi ôn tập

**Câu 1.** Volatile calls++ có thể mất updates không?

**Đáp:** Có. Read–modify–write không phải một atomic operation.

**Câu 2.** Vì sao demo racy-calls bằng 1?

**Đáp:** Barrier ép cả hai threads đọc 0 trước khi ghi 1.

**Câu 3.** Vì sao demo atomic-calls bằng 2?

**Đáp:** AtomicInteger.incrementAndGet được dùng cho hai increments.

**Câu 4.** Một AtomicInteger làm toàn bộ advice thread-safe chưa?

**Đáp:** Chưa nếu còn shared mutable collaborators hoặc multi-field invariants.

**Câu 5.** final ArrayList có immutable không?

**Đáp:** Không. Reference final và collection immutable là hai chuyện khác.

**Câu 6.** Aspect per-target có thể được nhiều threads dùng đồng thời không?

**Đáp:** Có, khi target được nhiều threads gọi.

**Câu 7.** Local variable trỏ vào shared Map có loại bỏ race trên Map không?

**Đáp:** Không, Map object vẫn dùng chung.

**Câu 8.** Vì sao inner ThreadLocal phải restore previous?

**Đáp:** Để không xóa context của outer scope.

**Câu 9.** CompletableFuture tự mang ThreadLocal từ caller sang worker không?

**Đáp:** Không mặc định; cần context propagation rõ ràng.

**Câu 10.** Atomic read rồi atomic increment có đảm bảo rate limit không?

**Đáp:** Không nếu check và increment chưa là một quyết định logic atomic.

**Câu 11.** LongAdder.sum có snapshot atomic khi đang cập nhật không?

**Đáp:** Không bảo đảm atomic snapshot.

**Câu 12.** ConcurrentHashMap có đảm bảo mọi compound workflow an toàn không?

**Đáp:** Không, chỉ những operations có contract thread-safe tương ứng.

**Câu 13.** synchronized(P) và synchronized(T) có cùng monitor nếu P khác T không?

**Đáp:** Không.

**Câu 14.** Outer advice count có luôn bằng target method executions không?

**Đáp:** Không, vì retry/cache/short-circuit hoặc nested points.

**Câu 15.** Test race bằng sleep có đủ không?

**Đáp:** Không. Dùng deterministic scheduling/synchronization và invariant reasoning.

**Câu 16.** Volatile policy reference có khiến mutable fields bên trong luôn an toàn không?

**Đáp:** Không. Cần immutable snapshot hoặc synchronization thích hợp.

## 25. Sơ đồ ghi nhớ

~~~text
                Multiple threads
                       |
                       v
             Shared aspect instance
                       |
            +----------+----------+
            |          |          |
            v          v          v
         Local      Mutable     ThreadLocal
         per call   shared      per thread
            |          |          |
            |       +--+------+   +-- restore scope
            |       |         |
            v       v         v
          Simple  volatile   Atomic / Lock
                  visibility state consistency
                  != atomic
                       |
                       v
              Test pointcut semantics
             Retry, async, exception,
              publication, happens-before
~~~

**Kết luận:** một aspect có thể dùng chung mutable state qua nhiều luồng, gây lost update, visibility bugs, context mixing và race ở tầng nghiệp vụ. Cần phân biệt volatile visibility với atomic read–modify–write, dùng AtomicInteger/LongAdder/synchronized/Lock đúng ngữ nghĩa, quản lý ThreadLocal theo scope và chủ động propagate immutable context qua async. Thread safety của advice, target và collaborator là các điều kiện riêng biệt; kiểm thử phải bao cả concurrency interleavings lẫn số lượt advice/target thực sự diễn ra.

## Tài liệu tham khảo

- [Java Language Specification 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): JMM, happens-before, synchronization, volatile.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic operations.
- [Java SE 17 — LongAdder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counters under contention.
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): thread-bound context.
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): concurrent keyed state.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): completion và memory effects.
- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): aspect instantiation, pointcut và advice trong một ngôn ngữ AOP cụ thể.

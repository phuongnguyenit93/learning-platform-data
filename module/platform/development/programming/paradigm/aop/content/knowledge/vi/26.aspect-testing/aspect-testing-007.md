# Kiểm thử trạng thái dùng chung trong điều kiện đồng thời của Aspect

## 1. Vì sao cần kiểm thử riêng tính đồng thời của Aspect?

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), một **aspect** áp dụng lời khuyên (**advice**) tại những **join point** mà **pointcut** lựa chọn. Khi cùng một aspect quan sát nhiều lời gọi đến từ các thread hoặc các tác vụ chồng lấn, những field và dependency mà advice sử dụng có thể trở thành **trạng thái dùng chung (shared state)**.

Ví dụ, một advice ghi nhận số operation hoàn tất:

~~~text
Thread A --\
            -> CountingAdvice -> businessOperation
Thread B --/
                  |
            shared count
~~~

Nếu mỗi lần advice đọc giá trị count rồi ghi count + 1 mà không đồng bộ hóa phù hợp, hai lời gọi có thể cùng đọc 0 và cùng ghi 1. Hai operation thực sự đã chạy, nhưng counter cuối chỉ bằng 1. Đây là **lost update**.

Một ví dụ nguy hiểm hơn: aspect giữ **currentUser** hoặc **correlationId** trong field của instance dùng chung. Khi yêu cầu của Alice và Bob đi qua cùng advice, một yêu cầu có thể ghi đè thông tin của yêu cầu kia. Lúc ấy lỗi không chỉ là số liệu sai mà còn có thể là **rò rỉ ngữ cảnh, ghi audit sai danh tính hoặc ra quyết định quyền sai**.

**Mục tiêu:** kiểm thử chính xác những trạng thái nào được chia sẻ, những trạng thái nào phải cô lập, cách advice tương tác với Java Memory Model, sự lồng nhau của lời gọi và vòng đời asynchronous. Đồng thời, phải kiểm tra số lần proceed, bảo toàn kết quả/ngoại lệ và điểm cắt thực của hệ thống AOP.

Bài chỉ đề cập đến AOP nói chung, không phụ thuộc vào một bộ công cụ AOP cụ thể. Các ví dụ Java 17 hoạt động độc lập; một số đoạn là mô hình minh họa cách advice sử dụng state.

## 2. Điều gì thực sự được chia sẻ?

Không phải cứ thấy một field trong aspect là nó được chia sẻ trên toàn bộ chương trình. Phạm vi của field phụ thuộc **mô hình tạo instance (aspect instantiation model)**, phạm vi classloader, cách proxy/weaving được cấu hình và vòng đời dependency.

Các loại state thường gặp:

| Trạng thái | Chủ sở hữu hợp lý | Rủi ro khi chia sẻ sai |
| --- | --- | --- |
| Tổng số operation đã hoàn tất | Metric recorder chung, thread-safe | Lost update, thống kê thấp hơn thực tế |
| Danh mục chính sách bất biến | Config immutable dùng chung | Rủi ro thấp nếu mọi thành phần chỉ đọc |
| Cache có thay đổi | Cache concurrent với key/scope hợp lệ | Race, stale data, cross-tenant leak |
| Current principal | Ngữ cảnh của một invocation/task | Caller A bị nhầm thành caller B |
| Correlation/trace context | Logical operation hoặc task | Trộn trace, sai parent-child relation |
| Start timestamp | Mỗi invocation | Duration bị ghép từ hai lời gọi khác nhau |
| Span đang mở | Scope của một đoạn công việc | Kết thúc nhầm span của lời gọi khác |
| Transaction/connection | Scope transaction cụ thể | Chia sẻ tài nguyên không an toàn, cleanup nhầm |
| Rate-limit bucket | Khóa giới hạn có chủ đích, concurrent | Vượt hạn mức hoặc từ chối nhầm |
| Attempt counter của retry | Một operation hoặc retry invocation | Attempts của nhiều lời gọi trộn nhau |

**Điểm xuất phát của kiểm thử** không phải “aspect có synchronized hay không”, mà là: **state này thuộc về ai, tồn tại bao lâu, và ai được phép truy cập đồng thời?**

## 3. Những mô hình tạo Aspect ảnh hưởng đến state

Các cơ chế AOP khác nhau hỗ trợ các phạm vi tạo aspect khác nhau. Về khái niệm, có thể gặp:

- **Singleton/shared aspect:** một instance phục vụ nhiều join point/lời gọi. Các instance field mutable có thể được nhiều thread truy cập.
- **Per-target/per-object:** mỗi object gắn với một aspect instance. Nếu object đó dùng chung giữa nhiều thread thì aspect state vẫn có thể chịu race.
- **Per-this/caller object:** gắn state với object phía gọi hoặc đang thực thi theo loại join point; không tương đương một instance cho mỗi request.
- **Per-control-flow:** tạo state cho một luồng thực thi động. Luồng này không tự động theo công việc được đẩy sang executor khác.
- **Per-type:** state gắn theo kiểu/lớp, không gắn theo từng object.
- **Per-invocation state:** các biến cục bộ của một lần chạy advice; thường là lựa chọn hợp lý cho timestamp, outcome và tham số của một lời gọi.

**Một per-target aspect không tự thread-safe**: một service singleton có thể là target của hàng nghìn request. **Một singleton aspect cũng không nhất thiết sai** nếu nó stateless, chỉ đọc immutable config hoặc dùng cấu trúc concurrent thích hợp.

Trong kiểm thử, phải xác định model thực được dùng thay vì suy đoán từ tên kiểu. Unit tests có thể chứng minh một handler thread-safe với các dependency giả; integration tests với weaving/proxy cần xác minh **instance thực sự được tạo và tái sử dụng theo phạm vi mong muốn**.

## 4. Bốn nhóm lỗi concurrency phải phân biệt

### 4.1. Data race và lost update

Hai thread truy cập cùng vị trí mutable, ít nhất một thread ghi và không có quan hệ đồng bộ phù hợp. Với phép đọc–sửa–ghi, cả hai có thể cùng đọc giá trị cũ và làm mất một cập nhật.

~~~text
initial count = 0
A read 0
B read 0
A write 1
B write 1
final count = 1, nhưng có 2 operation
~~~

Dùng **volatile int** không biến câu lệnh count++ thành nguyên tử: volatile cung cấp thuộc tính visibility/order nhất định, không gộp ba thao tác đọc–cộng–ghi thành một atomic read-modify-write.

### 4.2. Race logic dù từng thao tác riêng lẻ thread-safe

Một ConcurrentHashMap làm get và put an toàn ở mức từng phương thức, nhưng đoạn:

~~~text
if (!map.containsKey(key)):
    map.put(key, value)
~~~

không phải một thao tác nguyên tử. Hai thread có thể cùng vượt qua check. Cần dùng những primitive phù hợp như computeIfAbsent, putIfAbsent hoặc khóa bảo vệ toàn bộ invariant theo đúng contract.

Lưu ý **computeIfAbsent** có các ràng buộc riêng đối với mapping function: nên giữ function ngắn, không gây cập nhật đệ quy nguy hiểm, và hiểu semantics khi tính toán concurrent. Một concurrent collection không tự giải quyết mọi business invariant.

### 4.3. Rò context giữa các lời gọi

Một field currentPrincipal của shared aspect bị A ghi rồi B ghi trước khi A đọc. Một ThreadLocal không được remove cũng có thể làm task sau trên pooled thread thấy principal trước, dù hai task không chạy cùng lúc.

### 4.4. Vi phạm vòng đời bất đồng bộ

Advice đồng bộ mở scope rồi method trả một Future; background task tiếp tục trên thread khác. Nếu advice đóng resource quá sớm, task bị lỗi. Nếu giữ scope/counter cho tới callback không được thiết kế đúng, có thể rò tài nguyên hoặc đóng scope ở sai thread. Đây là lỗi lifecycle, không đơn thuần là vấn đề atomic counter.

## 5. Java Memory Model: nhìn từ kiểm thử AOP

Java Memory Model xác định khi nào các ghi của thread này **có thể được bảo đảm nhìn thấy** bởi thread khác và thứ tự nào được bảo toàn. Những quan hệ **happens-before** quan trọng:

- Các thao tác trước một lời gọi unlock trên monitor được bảo đảm nhìn thấy sau một lần lock tương ứng.
- Một volatile write happens-before volatile read tương ứng nhìn thấy ghi đó theo quy tắc đồng bộ.
- Các thao tác trước khi gọi **Thread.start()** happens-before hành động của thread mới.
- Hành động của thread kết thúc happens-before thread khác quay về thành công từ **Thread.join()** tương ứng.
- Với CountDownLatch, những thao tác trước countDown() được công bố tới thao tác sau await() thành công theo contract của latch.
- Các primitive trong java.util.concurrent như AtomicInteger, Future và concurrent collections có hợp đồng đồng bộ riêng.

Điều đó có nghĩa test không nên dùng một biến boolean thường để yêu cầu worker “đã xong chưa” rồi busy-spin vô hạn; chưa có ràng buộc visibility phù hợp. Dùng CountDownLatch, CyclicBarrier, Future, join hoặc primitive concurrent đúng chức năng.

Phải phân biệt ba thuộc tính:

**Atomicity:** nhiều bước có được thực hiện như một đơn vị không thể xen vào?

**Visibility:** thread khác có được thấy giá trị vừa ghi theo contract không?

**Ordering:** những thao tác có được quan sát theo thứ tự có thể dự đoán không?

Một biến volatile có thể cải thiện visibility nhưng không thay một cơ chế atomic increment. Một khóa có thể đồng thời đáp ứng mutual exclusion và visibility khi dùng đúng. Một AtomicInteger đáp ứng các thao tác nguyên tử được cung cấp, nhưng không tự ràng buộc với trạng thái nghiệp vụ khác.

## 6. Thiết kế kiểm thử không phụ thuộc vào may rủi

Cách sai thường gặp:

~~~text
Tạo 2 thread
Mỗi thread gọi advice 10 lần
sleep(100)
Nếu count cuối đúng thì kết luận an toàn
~~~

Chạy thử như vậy có thể pass hàng nghìn lần dù một lost update vẫn có thể xảy ra trong production. Sleep không chỉ định thứ tự xen kẽ; tải CI, scheduler, JIT và GC có thể thay đổi kết quả.

Cách tốt hơn: **điều phối một lịch interleaving xác định**.

~~~text
Thread A: read count -> báo "đã đọc" -> chờ cổng mở
Thread B: read count -> báo "đã đọc" -> chờ cổng mở
Test main: đợi đủ cả hai -> mở cổng
Thread A và B: ghi snapshot + 1
Test main: join hai thread rồi kiểm tra kết quả
~~~

Ta không khẳng định mọi cuộc đua dữ liệu đều tái hiện được bằng một lịch duy nhất. Nhưng bằng cách buộc hai lần đọc xảy ra trước bất kỳ lần ghi nào, test này chứng minh **một triển khai đọc–sửa–ghi không nguyên tử có thể mất cập nhật**.

Đối với triển khai đúng, dùng AtomicInteger.incrementAndGet hoặc một cơ chế bảo vệ toàn bộ thao tác tương đương, sau đó assert tổng bằng số lời gọi thực.

## 7. Chương trình Java 17 hoàn chỉnh: lost update và cô lập context

Ví dụ thực thi hai phép kiểm tra tách biệt:

1. Hai thread cùng thực hiện increment không nguyên tử theo một interleaving được điều phối, sau đó thực hiện increment nguyên tử.
2. Một executor chỉ có **một worker thread** chạy các task nối tiếp, nhằm xác minh context được restore/remove qua nested calls, thành công, ngoại lệ và thread reuse.

Điều này phản ánh hai nhóm state trong advice: **counter chia sẻ có chủ đích** và **identity/correlation riêng theo invocation**.

Tạo file **SharedAspectConcurrencyDemo.java**:

~~~java
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class SharedAspectConcurrencyDemo {

    // Minh họa một field mutable có thể nằm trong shared aspect.
    static final class SharedCounter {
        int unsafeCount;
        final AtomicInteger safeCount = new AtomicInteger();
    }

    // Một carrier scope theo thread, chỉ minh họa execution đồng bộ.
    static final class InvocationContext {
        private static final ThreadLocal<String> CURRENT =
                new ThreadLocal<>();

        static String current() {
            return CURRENT.get();
        }

        static <T> T withIdentity(
                String principal, Callable<T> action) throws Exception {
            Objects.requireNonNull(principal);
            Objects.requireNonNull(action);

            String previous = CURRENT.get();
            CURRENT.set(principal);
            try {
                return action.call();
            } finally {
                if (previous == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(previous);
                }
            }
        }
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void testLostUpdate() throws InterruptedException {
        SharedCounter state = new SharedCounter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch releaseWrites = new CountDownLatch(1);

        Runnable adviceCall = () -> {
            // Cố ý tách read và write để tái hiện một lịch lỗi.
            int snapshot = state.unsafeCount;
            bothRead.countDown();
            try {
                releaseWrites.await();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new AssertionError(interrupted);
            }

            state.unsafeCount = snapshot + 1;
            state.safeCount.incrementAndGet();
        };

        Thread first = new Thread(adviceCall, "caller-a");
        Thread second = new Thread(adviceCall, "caller-b");
        first.start();
        second.start();

        // Không có write nào xảy ra trước khi cả hai read.
        bothRead.await();
        releaseWrites.countDown();

        first.join();
        second.join();

        require(state.unsafeCount == 1,
                "expected forced lost update");
        require(state.safeCount.get() == 2,
                "atomic counter should record both calls");
        System.out.println("unsafe_count=" + state.unsafeCount);
        System.out.println("atomic_count=" + state.safeCount.get());
    }

    static void testContextLifecycle() throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            Future<String> first = worker.submit(() ->
                    InvocationContext.withIdentity("alice", () -> {
                        require("alice".equals(InvocationContext.current()),
                                "outer identity");

                        String nested =
                                InvocationContext.withIdentity(
                                        "service", InvocationContext::current);
                        require("service".equals(nested),
                                "nested identity");
                        require("alice".equals(InvocationContext.current()),
                                "outer identity not restored");

                        return InvocationContext.current();
                    }));

            require("alice".equals(first.get()), "first result");
            System.out.println("nested_restored=true");

            // Cùng một worker thread phải không còn principal cũ.
            Future<Boolean> reuse = worker.submit(
                    () -> InvocationContext.current() == null);
            require(reuse.get(), "leak into next task");
            System.out.println("thread_reuse_clean=true");

            Future<Boolean> failure = worker.submit(() -> {
                try {
                    InvocationContext.withIdentity("bob", () -> {
                        throw new IllegalStateException("failure");
                    });
                    return false;
                } catch (IllegalStateException expected) {
                    return InvocationContext.current() == null;
                }
            });

            require(failure.get(), "context leak on exception");
            System.out.println("exception_cleanup=true");
        } finally {
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                worker.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        testLostUpdate();
        testContextLifecycle();
        System.out.println("ALL CHECKS PASSED");
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac SharedAspectConcurrencyDemo.java
java SharedAspectConcurrencyDemo
~~~

Stdout khi hoàn thành bình thường:

~~~text
unsafe_count=1
atomic_count=2
nested_restored=true
thread_reuse_clean=true
exception_cleanup=true
ALL CHECKS PASSED
~~~

### Giải thích kết quả

**unsafe_count=1:** cả hai worker phải đọc snapshot trước khi cổng releaseWrites mở. Vì cả hai snapshot đều bằng 0, mỗi worker đều ghi giá trị 1. Thứ tự ghi sau khi mở cổng có thể khác nhau, nhưng kết quả cuối đều là 1. Đây là một minh họa **cố ý của bug**, không phải mẫu code nên dùng trong hệ thống thật.

**atomic_count=2:** cả hai worker cùng gọi incrementAndGet() của một AtomicInteger. Phép tăng tương ứng được thực hiện nguyên tử nên cả hai lần cập nhật đều được ghi nhận. AtomicInteger không cung cấp giao dịch nguyên tử cho những biến khác nằm ngoài nó.

**nested_restored=true:** scope inner tạm dùng principal service rồi khôi phục Alice; việc đóng một scope không được xóa nhầm context của scope ngoài.

**thread_reuse_clean=true:** executor một thread chạy task thứ hai trên thread đã dùng cho task thứ nhất. Context cũ đã được remove ở cuối scope trước.

**exception_cleanup=true:** ngay cả khi task ném IllegalStateException, finally của scope vẫn xóa principal Bob. Đây là điều kiện đặc biệt quan trọng nếu worker pool tái sử dụng thread để xử lý một yêu cầu thuộc người dùng khác.

**ALL CHECKS PASSED:** các assertion về hai loại state đã pass. Bài không có framework assertion bên ngoài; require() sẽ ném AssertionError nếu điều kiện sai.

### Phân biệt demo và một integration test AOP

Chương trình tự gọi những lớp helper thông thường; nó **không dùng weaver**. Do đó nó kiểm chứng cách xử lý shared state và context scope, không chứng minh rằng một aspect thực tế được gắn đúng join point hoặc được tạo với model mong muốn. Trong hệ thống dùng AOP, còn phải có kiểm thử tích hợp để xác nhận instance aspect cùng được dùng cho hai lời gọi, pointcut đúng và việc chặn diễn ra tại thời điểm dự kiến.

## 8. Kiểm thử bằng số lần proceed và outcome

Cùng với state, quanh một invocation cần xác minh **số lần advice cho phép computation tiếp tục**.

- Với logging/metrics observer bình thường: proceed() thường đúng **một lần** cho mỗi invocation.
- Với authorization deny: proceed() bằng **không**, nhằm ngăn side effect.
- Với retry có chủ đích: proceed() có thể nhiều lần, mỗi lần được ghi là một **attempt**.
- Với cache hit hoặc circuit breaker đang mở: proceed() có thể bằng **không** theo contract.
- Với một around advice vô tình gọi proceed() hai lần: operation nghiệp vụ có thể chạy hai lần, không chỉ counter sai.

Một phép đo counter đúng không có nghĩa invocation được thực thi đúng số lần. Ví dụ retry adapter gọi target ba lần nhưng chỉ tăng business-operation counter một lần là hợp lệ nếu có ba attempts và một logical operation. Test phải phân biệt các tầng đếm.

Khi có nhiều aspect, nên dùng **spy invocation** hoặc fake target ghi lại các lần proceed, sau đó assert business outcome, event count và state. Đừng chỉ nhìn stdout vì một event có thể được phát nhiều lần bởi các logger hoặc exporter khác nhau.

## 9. Bài test đúng phải xác định đơn vị của counter

Các chỉ số sau có thể khác nhau mà vẫn đúng:

| Counter | Đơn vị | Có thể lớn hơn cái gì? |
| --- | --- | --- |
| request_total | Một request giao thức | Số operation trong một số mô hình |
| operation_total | Một business operation | Số request khi một request sinh nhiều operation |
| attempt_total | Một lần thử | Số operation nếu retry |
| dependency_call_total | Một dependency call | Số operation do fan-out |
| advice_invocation_total | Một lần chạy advice | Số business operation nếu pointcut match nhiều join points |

Nếu aspect singleton của logging ghi **business_operation_total**, hai lời gọi song song phải làm tổng tăng hai. Nếu còn một advice khác cũng tăng cùng metric cho cùng operation, số cuối có thể là bốn. Đó là **semantic duplicate** và không được chữa bằng AtomicInteger: atomic chỉ đảm bảo cập nhật không mất, không đảm bảo định nghĩa phép đo đúng.

Nên có ownership matrix:

~~~text
business_operation_total   -> một boundary observer sở hữu
attempt_total              -> retry observer sở hữu
dependency_total           -> dependency boundary sở hữu
trace span                 -> instrumenter sở hữu từng scope
~~~

Việc kiểm thử concurrency phải xác minh cả **độ an toàn cập nhật** lẫn **ngữ nghĩa phép đo**.

## 10. Khi nào dùng AtomicInteger, LongAdder, synchronized và lock?

### AtomicInteger / AtomicLong

Phù hợp khi cần một counter nguyên tử với phương thức increment, get, compareAndSet hoặc atomic update. Có semantics rõ, dễ assert count cuối trong unit test.

Giới hạn: một atomic counter không tự đảm bảo một tuple state liên quan được cập nhật nguyên tử cùng nhau. Nếu advice phải đổi trạng thái từ OPEN sang CLOSED đồng thời thêm sự kiện hoặc thay timestamp, cần thiết kế invariant tổng thể.

### LongAdder

Phù hợp cho bộ đếm có tần suất cập nhật rất cao và contention lớn. Các phép cộng trải trên nhiều ô nội bộ để tối ưu throughput. Tuy nhiên **sum() khi đang có cập nhật đồng thời không phải snapshot nguyên tử tuyến tính hóa**; tránh assert số trung gian chính xác tại một thời điểm chưa quiescent. Sau khi tất cả tác vụ hoàn tất và có đồng bộ phù hợp, có thể assert tổng cuối.

### synchronized và ReentrantLock

Dùng khi cần bảo vệ một invariant bao gồm nhiều field hoặc một chuỗi thao tác phải atomic. Lock phải bảo vệ **cả đọc và ghi của invariant**, không chỉ một phía. Hạn chế scope lock; không giữ lock xuyên network I/O, logger blocking hoặc callback async tùy tiện.

### Immutable state

Nếu aspect chỉ cần policy/config không thay đổi, immutable record hoặc Map.copyOf giúp giảm tình trạng race do mutation. Nhưng bất biến của **tham chiếu** chưa đủ nếu các object lồng nhau vẫn mutable; cần deep immutability hoặc ranh giới sở hữu rõ.

### Concurrent collections

ConcurrentHashMap, concurrent queues hoặc atomic references có thể hữu ích. Đọc tài liệu từng API: các thao tác riêng lẻ có thể thread-safe nhưng tổ hợp nhiều thao tác chưa chắc duy trì business invariant.

**Không dùng volatile để thay atomic increment hoặc thay lock bảo vệ state nhiều trường.**

## 11. Test tính đồng thời phải kiểm tra cả safety và liveness

**Safety property:** điều xấu không xảy ra. Ví dụ không lost update, không cross-user context, không đóng span hai lần, không trả một permit đã cấp cho task khác.

**Liveness property:** hệ thống còn tiến triển. Ví dụ các lời gọi eventually complete, không deadlock, không starvation vô hạn, không giữ khóa trong khi chờ callback không thể chạy.

Một test chỉ assert count cuối sau join sẽ phát hiện một số safety bug nhưng có thể **treo vô hạn** nếu worker deadlock. Trong môi trường CI nên dùng deadline ở wait, đảm bảo giải phóng latch trong finally, shutdown executor và báo thông tin về thread còn chờ. **Timeout trong test chỉ là cơ chế phát hiện treo**, không chứng minh mọi thực thi production đều an toàn.

Các primitive nên dùng:

- CountDownLatch để chờ một lượng sự kiện đã xảy ra.
- CyclicBarrier hoặc Phaser để điều phối nhiều vòng xen kẽ.
- Future.get với timeout để chặn việc treo mãi.
- Semaphore để giới hạn số lượt đồng thời.
- ExecutorService để quản lý worker và cleanup.
- AtomicInteger và các primitive đồng bộ để đo chính xác số lượt.

Không gọi Thread.sleep như cơ chế đồng bộ chính. Sleep có thể dùng để mô phỏng latency trong benchmark/test khác, nhưng không bảo đảm hai thread đến một điểm theo thứ tự mong muốn.

## 12. Một pattern unit test chống lost update

Khi nghi một field mutable trong advice có phép đọc–sửa–ghi không nguyên tử:

1. Tách phần cập nhật state ra một handler/service nhỏ có thể gọi trực tiếp.
2. Dùng **hai invocation giả** của handler.
3. Đặt **barrier/latch** sau bước đọc snapshot và trước bước ghi trong phiên bản instrumented để ép cùng một lịch.
4. Cho hai thread chạy tới barrier.
5. Mở barrier, chờ cả hai hoàn tất.
6. Assert count đúng theo policy và đánh giá có mất cập nhật hay không.
7. Thay bằng primitive nguyên tử hoặc lock, sau đó viết lại test hành vi công khai (không dựa mã internals) để đảm bảo tổng operation thực sự đúng.

Một anti-pattern của test là **chỉnh implementation chỉ để test đi qua**: giữ một bản test-only instrumented dễ gây khác biệt so với mã sản phẩm. Tốt hơn là thiết kế state update trong một component có seam, kiểm thử riêng tính thread-safe và thêm integration test với advice thật. Lịch ép xen kẽ là công cụ giải thích lỗi, không phải bằng chứng hình thức về mọi interleaving.

## 13. Test read/write một cấu trúc state nhiều trường

Giả sử aspect giữ:

~~~text
lastOutcome = "SUCCESS"
lastOperationId = "O-31"
lastTimeNanos = 123456
~~~

Nếu các trường được cập nhật tách rời, một thread khác có thể đọc cặp outcome của operation A và ID của operation B. AtomicInteger không giải quyết lỗi **tính nhất quán của bản ghi nhiều trường**.

Các cách tổ chức phù hợp:

- Một immutable snapshot record và AtomicReference thay thế toàn bộ snapshot.
- Một lock bao quanh mọi cập nhật/đọc có tính nhất quán.
- Mỗi invocation giữ state cục bộ, chỉ phát immutable event vào thread-safe sink.
- Nếu cần lưu lịch sử, dùng queue phù hợp thay vì các “last” field dùng chung.

Một bài test có thể dùng barrier giữa lần ghi hai field để ép observer đọc đúng thời điểm không nhất quán; sau sửa, assert mọi snapshot đều thuộc một occurrence hoàn chỉnh. Tuy nhiên, cần tránh test tự đọc những biến thường từ nhiều thread khi không có contract đồng bộ; test nên tương tác qua API có semantics rõ.

## 14. Không để context của request trong field dùng chung

Một thiết kế sai:

~~~java
// Đoạn minh họa lỗi, không phải chương trình đầy đủ.
class BadAdviceState {
    String currentPrincipal;

    Object around(String principal, Invocation invocation)
            throws Exception {
        currentPrincipal = principal;
        return invocation.proceed();
    }
}
~~~

Nếu hai caller dùng chung instance này, field currentPrincipal có thể bị thay giữa lúc một operation còn chạy. Cả static field lẫn instance field của singleton aspect đều nguy hiểm khi dùng để lưu ngữ cảnh riêng từng lời gọi.

Các cách thay:

1. **Biến local** cho principal, start time, result và error của một invocation đồng bộ.
2. **Tham số tường minh** truyền identity/context tới những component cần nó.
3. **ThreadLocal có scope rõ** khi thực sự phục vụ call stack đồng bộ trên cùng thread.
4. **Task context immutable** khi công việc chuyển executor hoặc callback.
5. **Registry keyed theo operation ID** khi cần trạng thái workflow kéo dài, có cleanup/TTL/capacity/concurrency policy.

Nếu dùng ThreadLocal, giá trị chưa chắc là danh tính đáng tin; bảo mật vẫn cần trusted authentication và authorization. ThreadLocal là phương tiện mang context, không phải chứng cứ quyền.

## 15. Kiểm thử ThreadLocal đúng vòng đời

ThreadLocal có tính cô lập giữa các thread, nhưng test vẫn cần xét:

- Một lời gọi đặt context rồi trả bình thường → context được xóa hoặc restore.
- Một lời gọi ném exception → finally vẫn cleanup.
- Scope lồng nhau thay context → sau inner, outer giữ nguyên context cũ.
- Worker thread được tái sử dụng → task kế tiếp không thấy context của task trước.
- Caller thread và worker thread khác nhau → worker không tự có principal từ caller.
- Callback có thể chạy trên worker hoặc caller → không dựa vào vị trí chạy không được bảo đảm.
- Task hủy/timeout → scope được đóng ở điểm thực sự sở hữu lifecycle; handle timeout không đồng nghĩa task dừng.

Không chỉ test “hai thread có ThreadLocal khác nhau”. Một lỗi thường gặp nhất là **không remove() trong thread pool**, vì hai request có thể chạy nối tiếp trên cùng thread mà vẫn lẫn principal.

Với nested scope, lưu previous, set mới, và trong finally restore previous hoặc remove nếu previous null. Chỉ gọi remove sau inner scope sẽ làm mất context của outer. Chương trình Java ở trên kiểm tra cả nested restore và thread reuse.

## 16. Vì sao InheritableThreadLocal không phải lời giải cho executor?

**InheritableThreadLocal** có thể chuyển một giá trị từ thread cha sang một thread con vào thời điểm **tạo thread**. Nó không cung cấp cơ chế truyền context theo **mỗi task** của một executor có thread pool sống dài.

Các tác hại:

- Worker thường được tạo từ trước khi task được submit.
- Thread reuse làm giá trị kế thừa không đại diện cho invocation hiện hành.
- Nếu giá trị mutable, việc chia sẻ hoặc copy semantics có thể gây rò dữ liệu.
- Với nhiều caller, một pooled thread không thuộc riêng caller nào.

Thiết kế phù hợp hơn là tạo immutable context snapshot tại trusted boundary, truyền snapshot vào task wrapper, attach scope tại worker, và restore/remove trong finally. Với security context, còn cần kiểm tra hạn dùng/quyền bị thu hồi khi workflow kéo dài.

Một unit test tốt submit lần lượt nhiều task có context khác nhau vào cùng một executor một thread và xác minh task thứ ba không có context khi không được cấp. Sau đó kiểm thử exception path và cancellation path.

## 17. Trạng thái trong advice khi có lời gọi đệ quy/nested

Ngay cả khi chỉ có một thread, **shared mutable field** vẫn gây lỗi nếu lời gọi lồng nhau:

~~~text
Advice A begins operation outer, sets field start=100
    method outer calls inner
    Advice A begins operation inner, sets field start=120
    method inner ends, reads start=120
method outer ends, reads start=120 (mất start=100)
~~~

Đây là **reentrancy bug** không cần hai thread cùng chạy. Vì thế các biến như start time, error, result nên là local của mỗi advice invocation hoặc nằm trong một context stack được thiết kế rõ.

Các test nên bao phủ:

- Method được aspect chặn gọi một method khác cũng khớp pointcut.
- Có một exception ở inner nhưng outer tiếp tục, hoặc ngược lại.
- Scope inner được đóng đúng, outer còn nguyên.
- Counter cấp operation chỉ tăng theo semantics đã định: hai operation độc lập hoặc một operation chứa helper.
- Advice không tự intercept logging/helper của mình gây recursion vô hạn.

Không thêm một global Boolean "đang trong advice" để chữa bừa: nó có thể chặn nhầm invocation của thread khác. Thread-local reentrancy guard cũng cần cleanup và phân biệt nested operation hợp lệ với recursion không mong muốn.

## 18. Kiểm thử aspect singleton không có nghĩa ép nó thành stateless

Một singleton aspect có thể mang **shared state hợp lệ**, ví dụ:

- Bộ đếm tổng cho mỗi loại operation, thông qua thread-safe recorder.
- Chính sách bất biến dùng chung.
- Registry thread-safe quản lý các task có vòng đời rõ.
- Rate limiter chia sẻ số permit cho một tập caller.
- Cache concurrent có key/TTL/invalidation phù hợp.

Vấn đề không phải sự tồn tại của state, mà là **quyền sở hữu, invariant và primitive bảo vệ nó**.

Một bài test cho metric recorder phải phân biệt hai trường hợp:

- Sau N lời gọi hoàn tất, tổng cuối phải bằng N trong điều kiện không sampling/dedup.
- Trong khi N lời gọi đang chạy, một phép đọc giữa chừng có thể thấy giá trị trung gian; không bắt buộc mọi lần đọc là một snapshot của toàn hệ thống nếu API không hứa điều đó.

Nếu dùng LongAdder, sum() giữa chừng không phải snapshot nguyên tử. Với AtomicInteger, get() có semantics riêng; với nhiều metric fields, vẫn cần cơ chế đọc snapshot nhất quán nếu dashboard khẳng định chúng mô tả cùng một thời điểm.

## 19. Async completion và nhiều callback cùng sửa state

Một method được AOP quan sát có thể trả CompletableFuture hoặc CompletionStage. Có hai mốc:

~~~text
method called
    -> method returns stage (invocation kết thúc)
         -> background work
         -> stage completes (logical outcome)
~~~

Nếu một advice tăng counter khi method return và một callback khác cũng tăng counter khi stage hoàn tất, có thể đếm trùng hoặc đếm sai semantic scope. Nếu nhiều callback cùng cập nhật một mutable event object, chúng còn có thể gặp data race.

Thiết kế kiểm thử async cần:

1. Tạo một CompletableFuture chưa hoàn tất.
2. Gọi handler/adapter và xác minh chưa phát final business outcome nếu contract yêu cầu completion.
3. Hoàn tất stage bằng success, exception hoặc cancellation.
4. Assert event phù hợp được phát **đúng một lần**.
5. Khi có callback song song, bảo vệ state dùng chung hoặc phát immutable events qua thread-safe sink.
6. Kiểm tra handler không làm đổi outcome của task vì observer callback ném lỗi.
7. Phân biệt cancellation/timeout trên wrapper với việc task nền đã thực sự dừng và giải phóng tài nguyên.

Một callback có thể chạy ngay trên thread hiện tại nếu stage đã hoàn tất trước khi đăng ký, hoặc chạy trên thread khác về sau. Vì thế không thể giả định ThreadLocal ở method caller còn tồn tại trong callback.

## 20. Một mẫu test async có điều khiển

Đoạn minh họa dưới đây **không phải chương trình độc lập**, vì method observeCompletion và event sink thuộc handler của ứng dụng:

~~~java
CompletableFuture<String> task = new CompletableFuture<>();
List<String> events = new CopyOnWriteArrayList<>();

CompletionStage<String> watched =
        observeCompletion("order.submit", task, events::add);

// Task vẫn chưa hoàn tất: không được có final outcome.
require(events.isEmpty(), "premature completion event");

// Test chủ động hoàn tất kết quả, không cần sleep.
task.complete("DONE");

require(events.equals(List.of("operation=order.submit outcome=success")),
        "wrong completion event");
~~~

Kiểm thử tương tự với completeExceptionally() và cancellation theo contract. Việc CompletableFuture có thể thực hiện callback đồng bộ trên thread gọi complete() giúp test tránh dùng timer may rủi, nhưng handler thực vẫn phải xử lý trường hợp race giữa đăng ký callback và completion.

Nếu API test trả completion stage phụ thuộc mà callback tạo thêm lỗi, cần assert liệu lỗi observer có bị cô lập hay làm hỏng dependent stage theo contract. Đối với event ghi bền vững, không đơn giản nuốt lỗi như telemetry best-effort.

## 21. Kiểm thử shared map/caches trong Aspect

Một aspect có thể giữ cache để nhớ policy decision, metadata của method, compiled pattern hoặc state rate-limiting.

Cần phân biệt:

**Immutable initialization:** tạo một map lúc khởi tạo rồi không thay đổi, công bố theo cách thread-safe. Đây thường là rủi ro thấp.

**Concurrent read/write:** dùng một concurrent collection hoặc lock, nhưng phải xem lại invariant nhiều bước.

**Cache theo principal/tenant:** key phải chứa đủ ngữ cảnh; cache từ user A không được trả kết quả ALLOW cho user B.

**Expiry/eviction:** chỉ dùng một map không giới hạn gây memory leak; chính sách TTL và dung lượng phải rõ.

**Compute operation:** mapping function chạy bao nhiêu lần, có side effect không, có recursive update không? Dùng API theo contract thay vì giả định một lambda luôn được gọi đúng một lần dưới mọi hoàn cảnh.

Kiểm thử:

- Hai thread cùng đưa cùng key vào cache.
- Hai thread dùng key khác nhau không chia sẻ nhầm value.
- Cache invalidation và lookup xảy ra đồng thời.
- Resource/permission thay đổi làm cache cũ không bị sử dụng trái policy.
- Mapping function ném exception không để entry hỏng.
- TTL được kiểm bằng fake clock, không bằng sleep.
- Concurrent put không gây mất cấu trúc map hay exception ngoài contract.

Không cố thay domain transaction bằng một cache lock trong aspect. Invariant phải được bảo đảm tại điểm sở hữu dữ liệu nếu có tranh chấp đồng thời.

## 22. Rate limiter và semaphore: state chia sẻ có chủ đích

Rate limiter là ví dụ rõ ràng về state **phải** dùng chung theo một khóa nhất định. Nếu từng invocation tự tạo một limiter mới, tất cả lời gọi đều được cấp quota như chưa từng có request trước.

Nhưng khóa chia sẻ phải đúng:

- Theo service toàn cục?
- Theo principal?
- Theo tenant?
- Theo resource/endpoint?
- Theo node hay toàn cụm?
- Theo cửa sổ thời gian nào?

Một semaphore đồng bộ có thể giới hạn số lời gọi đang hoạt động trong một tiến trình. Khi test, cần xác minh:

1. Không quá N operations cùng giữ permit.
2. Khi deny/timeout/acquire interrupted, không phát sinh permit giả.
3. Sau khi target thành công hoặc ném lỗi, permit được trả đúng một lần.
4. Với async, permit tồn tại đúng tới mốc task completion nếu quota là concurrency của task, không chỉ tới lúc method trả stage.
5. Một lời gọi nested không bị deadlock do cố lấy lại permit theo cơ chế không reentrant, nếu thiết kế đó không cho phép.

Các assertion về số operations đồng thời có thể dùng AtomicInteger theo dõi active/maxActive và CountDownLatch để dừng worker ở critical section. Không dựa vào timestamp của các dòng log để đoán số worker đồng thời.

## 23. Testing concurrency không chỉ là test một counter

Một ma trận kiểm thử thiết kế tốt:

| Tình huống | Loại lỗi nhắm đến | Cách kiểm tra |
| --- | --- | --- |
| N advice invocation tăng shared counter | Lost update | Latch/barrier, assert total sau join |
| Hai request với principal khác nhau | Cross-request contamination | Gọi chồng lấn, assert identity ở từng pha |
| Hai task liên tiếp trên cùng worker | ThreadLocal leak | Single-thread executor, assert null ở task sau |
| Scope lồng nhau | Restore sai | Assert principal của outer sau inner |
| Advice target ném lỗi | Cleanup thiếu | Spy close, assert finally |
| Shared map check-then-put | Race logic | Controlled interleaving/atomic API |
| Metric observer được đăng ký hai lần | Semantic duplicate | Assert một final event/operation |
| Retry nhiều attempt | Nhầm counter | Operation count 1, attempts N |
| Future hoàn tất sau method return | Lifecycle lệch | Controlled future, assert không ghi sớm |
| Callback hoàn tất song song | Double completion / race | Atomic guard hoặc event ownership test |
| Multiple aspects cùng sửa shared state | Composition | Weaving integration test |
| Một target phục vụ nhiều thread | Per-target không thread-safe | Shared object, concurrent calls |
| Shared lock bị giữ khi observer lỗi | Deadlock/liveness | Timeout và spy release |
| Config hot reload | Publication race | Immutable snapshot/atomic reference |
| Task bị cancel/timeout | Cleanup sai lifecycle | Controlled cancellation và state assertions |

Không nhất thiết có một test duy nhất kiểm tra toàn bộ bảng. Unit tests nhỏ giúp xác định chính xác nguyên nhân; integration tests kiểm chứng những giả định phụ thuộc wiring AOP.

## 24. Tách kiểm thử logic và kiểm thử weaving

**Unit test logic advice** có thể gọi handler trực tiếp, truyền fake invocation, fake clock và fake metrics recorder. Phần này nên nhanh, xác định, không cần compiler/weaver hoặc agent chạy.

**Integration test AOP** cần cơ chế interception thật để xác nhận:

- Pointcut match đúng những join point.
- Advice không chạy ở helper hoặc những đường không mong muốn.
- Aspect instance được tạo theo model khai báo.
- Nhiều thread thực sự đi qua cùng instance nếu đó là thiết kế.
- Thứ tự advice với retry, transaction, authorization, tracing có hiệu lực.
- Lời gọi trực tiếp/self-invocation có được instrument hay bỏ qua theo kiểu AOP được chọn.
- Những aspect khác không cùng ghi một event trùng ngữ nghĩa.
- Với async, observer được đặt tại đúng lifecycle boundary.

**End-to-end test** còn xác minh business side effects, quyền truy cập, dữ liệu lưu trữ và telemetry khi đi qua các tầng. Một unit test chứng minh AtomicInteger tăng đúng không chứng minh rằng pointcut bắt đúng operation hoặc toàn bộ pipeline metrics không scrape trùng.

## 25. Không test bằng một global flag chống recursion

Một số advice tự kích hoạt lại khi ghi log hoặc gọi helper thuộc pointcut. Có người thêm:

~~~text
static boolean insideAdvice = false
if (insideAdvice) proceed()
else:
    insideAdvice = true
    try observeAndProceed()
    finally insideAdvice = false
~~~

Đây là giả mã của thiết kế **sai trong concurrency**: thread A đặt true có thể khiến thread B bỏ qua monitoring của một operation hoàn toàn độc lập.

Thay thế:

- Thu hẹp pointcut để loại helper của instrumentation.
- Dùng một reentrancy guard theo scope phù hợp, có cleanup trong finally.
- Phân biệt nested business operations hợp lệ và self-recursion không mong muốn.
- Kiểm thử hai threads đồng thời cùng qua advice; không để flag của A ảnh hưởng B.
- Nếu context được truyền sang async task, dùng task-specific identity/scope phù hợp; ThreadLocal guard không tự di chuyển sang thread mới.

Một **ThreadLocal<Boolean>** cũng không phải “tất cả đã ổn”: nếu nó không được reset, pooled thread có thể bỏ qua những operation tiếp theo. Nếu guard chặn mọi nested invocation, nó có thể làm mất metric hợp lệ của use case con.

## 26. Khi concurrency bug nằm ngoài Aspect

Một request có thể bị đếm trùng hoặc ghi sai không phải do aspect state:

- Hai collectors nhận cùng metric và dashboard cộng hai lần.
- Retry trong nghiệp vụ thực thi nhiều attempts.
- Message broker giao lại sự kiện nên có nhiều processing attempts thật.
- Database transaction gặp race và trả kết quả sai bất chấp aspect thread-safe.
- Một logger/appender chuyển cùng event qua hai pipeline.
- Một component giữ mutable singleton context mà advice chỉ đọc.
- Pointcut áp dụng nhiều lần do cấu hình instrumentation chồng lấn.

Phương pháp điều tra:

1. Đặt điểm kiểm tra ngay ở handler/advice, xem số lần gọi và state.
2. Xác định source event ID và semantic unit.
3. Theo dõi event qua exporter, collector, storage, query.
4. Kiểm tra những điểm shared mutable state khác trong đường gọi.
5. Tách lỗi race thực khỏi sự kiện hợp lệ do retry, fan-out hoặc nested operations.

Không sửa một counter bằng synchronized rồi kết luận mọi vấn đề quan sát đã hết. Thread safety và đo đúng đơn vị là hai tiêu chí độc lập.

## 27. Một thử nghiệm stress bổ sung

Sau những test điều phối deterministic, có thể chạy **stress test**:

- Cố định số thread và số operation trên mỗi thread.
- Đồng bộ thời điểm bắt đầu bằng latch/barrier.
- Ghi tổng số proceed và business completions.
- Chạy nhiều vòng với các mức concurrency khác nhau.
- Thử xen kẽ nested calls, exception, cancellation và timeout.
- Assert trạng thái sau khi toàn bộ workers hoàn tất; kiểm tra liveness bằng deadline.
- Chẩn đoán khi fail bằng operation ID và event record ít dữ liệu, không log secrets.

Stress test có giá trị khám phá interleavings chưa nghĩ tới; **pass không phải bằng chứng không có data race**. Review code, primitive đồng bộ, kiểm thử deterministic và phân tích concurrency thích hợp đều cần thiết. Nếu test fail không ổn định, cố tái tạo lịch gây lỗi thay vì tăng sleep một cách tùy ý.

## 28. Những sai lầm và cách sửa

### Sai lầm 1: “Aspect singleton nên mọi biến trong nó đều có thể dùng chung”

**Sai:** Một singleton aspect có thể chứa configuration chung, nhưng currentUser/startTime riêng cho invocation không nên là shared field. Dùng local variables hoặc context có scope đúng.

### Sai lầm 2: “Thêm volatile là count++ thread-safe”

**Sai:** volatile không biến read-modify-write thành atomic operation. Dùng AtomicInteger, LongAdder theo mục tiêu hoặc synchronized/lock.

### Sai lầm 3: “Dùng ConcurrentHashMap là mọi check-then-act đã nguyên tử”

**Sai:** các chuỗi thao tác cần API atomic hoặc lock bảo vệ invariant. Test theo các interleavings có thể xảy ra.

### Sai lầm 4: “ThreadLocal tự xóa khi request kết thúc”

**Sai:** worker pool tái sử dụng thread. Cần restore/remove trong finally, kiểm thử với một executor cùng worker.

### Sai lầm 5: “ThreadLocal tự truyền sang Future”

**Sai:** executor có thread riêng. Truyền context của task một cách tường minh và kiểm tra expiry/reauthorization khi cần.

### Sai lầm 6: “Một bài test dùng sleep đã chứng minh không có race”

**Sai:** sleep không điều phối thứ tự. Dùng latch/barrier và assert qua synchronization.

### Sai lầm 7: “Aspect pertarget có nghĩa mỗi request một instance”

**Sai:** target object có thể là singleton phục vụ nhiều request; field pertarget vẫn cần thread-safe nếu mutable.

### Sai lầm 8: “Count bằng số request là đủ”

**Sai:** một request có thể sinh nhiều operations; một operation có retry attempts. Phải định nghĩa semantic unit trước.

### Sai lầm 9: “Chỉ cần unit test handler”

**Sai:** pointcut hoặc weaving có thể sai; cần integration test cho instance lifetime, match và composition.

### Sai lầm 10: “Một lock quanh toàn advice sẽ an toàn”

**Không chắc:** lock rộng gây contention, deadlock khi nested/reentrant hoặc giữ qua blocking I/O. Lock chỉ bảo vệ những invariants cần thiết trong scope được thiết kế.

### Sai lầm 11: “Task timeout là đã cleanup xong”

**Sai:** wrapper có thể timeout trong khi worker vẫn chạy. Resource ownership phải theo task lifecycle thật.

### Sai lầm 12: “Logger không thể gây race”

**Sai:** mutable event objects, context fields và callbacks có thể race; logger có thể giữ tham chiếu vào object mutable để serialize về sau. Gửi immutable snapshot và có schema/redaction.

## 29. Quy trình triển khai bài kiểm thử concurrency cho một Aspect

**Bước 1 — Kiểm kê state.** Liệt kê mọi field của aspect, các dependency mutable, static state, ThreadLocal, cache, metric recorder và scope.

**Bước 2 — Xác định ownership.** State thuộc toàn bộ process, target object, một operation, một attempt hay task? Có bao nhiêu thread cùng đọc/ghi?

**Bước 3 — Viết invariant.** Ví dụ: “mỗi operation hoàn tất tăng counter đúng một lần”, “không invocation nào quan sát principal khác”, “mọi scope mở đều được đóng đúng chỗ”.

**Bước 4 — Chọn primitive.** Immutable snapshots, atomic counter, synchronized/lock, concurrent map hoặc task context theo từng invariant.

**Bước 5 — Tạo seam test.** Handler độc lập với weaver, fake invocation, fake clock, event sink và executor/latch điều khiển được.

**Bước 6 — Kiểm tra đường success và failure.** Target trả bình thường, ném lỗi, callback thất bại, observer lỗi, authorization DENY, retry và cancellation.

**Bước 7 — Điều phối race.** Buộc các interleavings rủi ro tại điểm read/write hoặc critical section; không dựa vào sleep.

**Bước 8 — Kiểm tra state sau kết thúc.** Dùng join/Future/get và những assertion trên counter, event count, context, resource cleanup.

**Bước 9 — Kiểm thử runtime AOP.** Với weaving/proxy thật, xác minh các lời gọi đồng thời cùng dùng đúng aspect instance và pointcut.

**Bước 10 — Stress và theo dõi.** Thử tải đại diện, quan sát throughput/latency/contention và memory leak; giữ test deterministic thành regression test.

## 30. Bài tập tự kiểm tra

**Câu 1:** Một aspect dùng singleton scope, field int total và advice gọi total++. Hai lời gọi concurrent có chắc tổng tăng 2 không?

**Đáp án:** Không. total++ không nguyên tử; có thể lost update. Dùng primitive phù hợp và test interleaving.

**Câu 2:** Đổi total sang volatile int có đủ không?

**Đáp án:** Không. volatile không tự biến thao tác tăng thành atomic.

**Câu 3:** Dùng AtomicInteger đã ngăn mọi hình thức đo trùng chưa?

**Đáp án:** Chưa. Nếu hai aspect đều phát cùng completion event cho một operation, cả hai increment có thể an toàn nhưng số đo vẫn sai gấp đôi.

**Câu 4:** Tại sao test hai task liên tiếp trong cùng một single-thread executor hữu ích?

**Đáp án:** Nó phát hiện ThreadLocal không được cleanup và rò context giữa hai task dù không chạy đồng thời.

**Câu 5:** Một aspect pertarget có field lastUser. Service target là singleton. Có an toàn không?

**Đáp án:** Không mặc nhiên. Một target dùng chung có thể khiến lastUser bị nhiều caller ghi đè.

**Câu 6:** Một span scope kết thúc ở method return nhưng work còn chạy trong Future. Điều gì sai?

**Đáp án:** Phạm vi đo không còn biểu diễn lifecycle của work; nếu muốn đo work phải dùng completion/task observer với context và cleanup phù hợp.

**Câu 7:** Vì sao LongAdder.sum() giữa những increment đang chạy không luôn là một snapshot nguyên tử?

**Đáp án:** Các ô cộng dồn có thể được đọc tại những thời điểm khác nhau; API tối ưu tranh chấp hơn là tính linearizable của mọi lần đọc tổng giữa concurrency.

**Câu 8:** Test handler đúng có chứng minh pointcut áp dụng đúng method không?

**Đáp án:** Không. Cần một integration test có cơ chế AOP thật để xác minh match, binding và instantiation.

## 31. Checklist QA trước khi triển khai

- [ ] Đã xác định mọi state mutable mà advice đọc/ghi.
- [ ] Mỗi state có ownership và lifecycle rõ.
- [ ] Singleton/per-object/per-flow model được hiểu theo thực tế, không theo suy đoán.
- [ ] Shared counters dùng atomic/lock phù hợp, không dùng volatile++.
- [ ] Các invariants nhiều trường được cập nhật/đọc nhất quán.
- [ ] Immutable configuration được công bố an toàn giữa các threads.
- [ ] Không có currentUser/correlationId riêng invocation trong shared field.
- [ ] ThreadLocal được restore/remove trong finally; nested scope đã có test.
- [ ] Executor reuse và async context propagation đã được kiểm chứng.
- [ ] Đồng thời không làm thay đổi số lần proceed ngoài policy.
- [ ] Retry/attempt và operation metric phân biệt rõ, không đo trùng.
- [ ] Timing dùng clock đơn điệu, không dùng sleep để đồng bộ test.
- [ ] Latches/barriers/Futures được quản lý đúng, test có phương án timeout nếu treo.
- [ ] Cancellation và callback exception có semantics được kiểm thử.
- [ ] Cache/key/TTL/tenant isolation được bảo vệ.
- [ ] Scope và permit được release đúng số lần, không giữ tài nguyên quá lifecycle.
- [ ] Pointcut, precedence và model tạo aspect được test bằng AOP integration.
- [ ] Stress tests bổ sung nhưng không thay deterministic tests.
- [ ] Event/log không chứa credentials, không giữ mutable request object về sau.

## 32. Kết luận

**Aspect dùng chung không đồng nghĩa trạng thái nào cũng nên dùng chung.** Bộ đếm và registry có thể chia sẻ khi được bảo vệ bởi primitive phù hợp; identity, timestamp, outcome và scope của một invocation cần được cô lập theo đúng lifecycle. Nhiều lỗi xuất hiện không chỉ khi hai thread thực sự chạy cùng lúc, mà còn khi nested calls ghi đè field hoặc worker thread tái sử dụng ThreadLocal chưa cleanup.

Một chiến lược kiểm thử vững chắc kết hợp **unit test handler với fake dependencies**, **lịch đồng thời điều khiển bằng latch/barrier**, **kiểm thử cleanup và async completion**, cùng **integration test weaving/pointcut/instance scope**. Kết quả cuối không chỉ là số counter đúng: mỗi operation phải được ghi nhận với **đúng ngữ nghĩa, đúng chủ sở hữu state và đúng ranh giới thực thi**.
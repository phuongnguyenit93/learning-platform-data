# Thiết kế aspect an toàn khi chạy song song

## 1. Vì sao aspect dễ trở thành điểm lỗi đồng thời?

Trong **Aspect-Oriented Programming (AOP)**, một aspect có thể can thiệp vào nhiều join point và nhiều đối tượng nghiệp vụ. Một advice thường trông rất ngắn: đo thời gian, ghi trace, tăng bộ đếm, thêm thông tin request, kiểm tra chính sách rồi tiếp tục vào target. Nhưng cùng một **aspect instance** có thể được nhiều threads gọi **đồng thời**, đặc biệt khi aspect có phạm vi dùng chung hoặc gắn với một target được gọi song song.

Nếu aspect giữ dữ liệu của từng lần gọi trong **field dùng chung**, các invocations có thể ghi đè dữ liệu của nhau. Nếu advice dùng `ThreadLocal` nhưng không cleanup, thread pool có thể chuyển dữ liệu request này sang request sau. Nếu dùng lock quá rộng quanh `proceed()`, aspect có thể vô tình biến một target vốn xử lý song song thành xử lý tuần tự, tăng tail latency hoặc tạo deadlock. Nếu advice ghi metric sau `proceed()` nhưng không có `finally`, exception có thể làm bộ đếm đang chạy không được giảm.

Một thiết kế an toàn phải trả lời đồng thời các câu hỏi:

1. **Aspect instance được chia sẻ với ai?** Một module, nhiều targets, một target, một invocation hay một control-flow scope?
2. **State nào có thể dùng chung?** Configuration bất biến, aggregate metric, cache có kiểm soát hay dữ liệu thuộc từng request?
3. **State của mỗi invocation sống bao lâu?** Tới khi method return, tới async task completion hay tới khi logical operation kết thúc?
4. **Tính nhất quán nào được yêu cầu?** Atomic update cho một counter, invariant nhiều field, snapshot nhất quán hay thứ tự có ý nghĩa nghiệp vụ?
5. **Advice có thay đổi hành vi target không?** Serialization do lock, retry, caching, timeout, exception transformation, callback và context propagation?
6. **Làm sao kiểm thử thực sự có overlap và chứng minh cleanup đúng?** Không dựa vào `Thread.sleep()` hoặc vài dòng log tình cờ.

**Trọng tâm:** An toàn đồng thời của AOP không chỉ là “đổi `int` sang `AtomicInteger`”. Nó là sự phối hợp giữa **state ownership**, **memory visibility**, **synchronization**, **lifetime**, **reentrancy**, **async boundaries**, **error semantics** và **độ phủ interception**.

### Mục tiêu học tập

Sau bài này bạn có thể:
- Phân biệt **stateless advice**, **shared aspect state**, **per-target state** và **per-invocation state**.
- Nhận diện race trên `lastStartNanos`, `currentUser`, bộ đếm, cache, shared builder và mutable collection.
- Dùng local variables, immutable configuration, `AtomicInteger`, `LongAdder`, concurrent collections và lock đúng trường hợp.
- Giải thích vì sao **atomicity** khác **visibility**, **thread safety** khác **đúng nghĩa dữ liệu**, và **per-target** khác **per-thread**.
- Viết around advice có cleanup trên success/failure và không biến exception thành false success.
- Dùng `ThreadLocal` với `try/finally`, hiểu nested scope, thread pools và vấn đề context propagation qua async.
- Biết rủi ro của việc giữ lock khi gọi `proceed()`, việc retry/recursion và self-invocation bypass proxy.
- Đọc và chạy **Java 17** với hai invocations được đồng bộ bằng `CountDownLatch`, chứng minh kết quả và counters chính xác.
- Thiết kế test về concurrent invocation, visibility, exception, cancellation, shutdown và giới hạn bộ nhớ.

Nội dung chỉ xét các cơ chế AOP cơ bản và nâng cao nói chung. Tên scope và hành vi đồng thời của từng công cụ cần được kiểm chứng bằng tài liệu/kiểm thử của chính công cụ ấy.

## 2. Hiểu các đối tượng tồn tại trong một lần can thiệp

Một hệ thống có thể đồng thời có:

| Thành phần | Ví dụ | Có phải riêng cho mỗi lời gọi không? |
| --- | --- | --- |
| **Aspect definition** | Quy tắc pointcut và advice code. | Không nhất thiết có runtime instance. |
| **Aspect instance** | Object chứa cấu hình và bộ đếm. | Có thể chia sẻ giữa nhiều threads/targets. |
| **Target** | Một service xử lý công việc. | Có thể singleton hoặc được tạo cho mỗi request. |
| **Proxy/interceptor chain** | Wrapper chuyển tiếp tới target. | Có thể được dùng chung; phụ thuộc mô hình. |
| **Advice invocation** | Một lần thực thi advice tại join point. | Là một lần chạy cụ thể. |
| **Invocation-local state** | `startNanos`, `correlationId`, `attemptId`. | Có thể tách riêng mỗi lượt bằng local variables. |
| **Logical task state** | Trace context dùng tới async completion. | Có thể sống lâu hơn method invocation. |
| **Shared aggregate** | Tổng số calls/failures, histogram. | Có thể đồng thời được cập nhật. |

**Một aspect instance không đồng nghĩa một lời gọi.** Một aspect dùng chung có thể nhận hàng nghìn invocations đang xen kẽ giữa nhiều threads. Cũng không thể suy rằng per-target aspect an toàn: cùng một target có thể được nhiều threads gọi cùng lúc.

### 2.1. “Không có field mutable” là một điểm khởi đầu tốt

Một advice có thể nhận arguments, lấy `long started=System.nanoTime()`, gọi continuation rồi tính duration bằng **local variable**. Mỗi invocation có call frame riêng, tránh việc hai lời gọi ghi đè `started` của nhau. Việc aspect instance được dùng chung không biến local variable thành một field dùng chung.

Tuy nhiên, local variable có thể tham chiếu một **mutable object shared** như một `ArrayList` toàn cục. An toàn hay không còn phụ thuộc **object được reference**, không chỉ tên biến local.

### 2.2. State của aspect và state của target là hai vấn đề độc lập

Một aspect thread-safe không khiến target tự thread-safe. Nếu target có `int balance` và hai threads cùng sửa không đồng bộ, lỗi vẫn xảy ra sau `proceed()`. Ngược lại, một target hoàn toàn an toàn vẫn có thể bị advice làm sai kết quả/exception hoặc gây race ở logging/counters.

Khi đánh giá, viết rõ invariant cho **cả target lẫn aspect** và những tương tác giữa chúng.

## 3. Đề xuất kiến trúc: hai lớp trạng thái, ba vòng đời

Sau khi đã hiểu race condition và Java Memory Model, hãy dựng một aspect quan sát production theo hợp đồng. Ví dụ một hệ thống tiếp nhận hàng nghìn thao tác độc lập, aspect dùng chung cần đếm số invocation đang chạy, theo dõi thời lượng và ghi outcome an toàn.

Tách **dữ liệu để quyết định** khỏi **dữ liệu để quan sát**:

```text
Shared Aspect instance
   |
   +-- Immutable policy snapshot   (read-only; có revision)
   +-- Shared concurrent aggregates (inFlight / failures / throughput)
   +-- Bounded telemetry sink       (queue có giới hạn và policy lỗi)
   |
Each advice invocation
   +-- local startNanos
   +-- local operation identity (đã lọc)
   +-- snapshot policy at entry
   +-- result/error của đúng invocation
   |
Async continuation, nếu có
   +-- minimal immutable context đã capture
   +-- ownership/deadline/cleanup theo logical task
```

Các vòng đời phải được nêu rõ: **aspect/module** sở hữu shared aggregates và sink; **mỗi invocation** sở hữu local state; **mỗi task bất đồng bộ** sở hữu context và quá trình hoàn tất của chính nó. Không biến mọi thứ thành field vì chúng được sử dụng bởi cùng một aspect definition.

## 4. Viết bất biến trước khi chọn công cụ đồng bộ hóa

Thay vì bắt đầu bằng “dùng lock hay atomic?”, hãy viết điều phải luôn đúng trong một phạm vi xác định.

| Bất biến | Owner | Bằng chứng kiểm thử |
| --- | --- | --- |
| Mỗi lời gọi đã vào advice tăng in-flight một lần | Scope advice | Khi hai lời gọi overlap, in-flight đạt 2 |
| Mỗi scope đã vào sẽ giảm in-flight đúng một lần | Scope advice | Sau success và throw, in-flight trở lại 0 |
| Mỗi outcome quan sát được quy về đúng lời gọi | Context theo invocation | A không nhận trace ID/result của B |
| Kết quả/ngoại lệ caller giữ đúng hợp đồng | Advice wrapper | Trả đúng hoặc ném đúng ngoại lệ gốc |
| Snapshot policy trong một invocation nhất quán | Immutable snapshot cục bộ | Reload giữa chừng không tạo nửa phiên bản cũ/mới |
| Sink hết dung lượng có policy rõ ràng | Owner hạ tầng | Đo được drop/backpressure/error, không phát sinh vòng instrumentation |
| Shutdown chỉ kết thúc khi phần việc cần hoàn tất đã được xử lý theo policy | Owner cấp module | Không đóng shared sink vì một request kết thúc |

Nhiều bất biến tồn tại **ở ranh giới khác nhau**. Ví dụ in-flight đếm scope advice đồng bộ có thể trở về 0 khi method trả một `CompletionStage` còn pending; nếu cần số logical tasks đang chạy, phải gắn phép tăng/giảm với completion của task, không tái sử dụng metric scope đồng bộ rồi đổi nhãn.

## 5. Số liệu tổng hợp: chọn semantics trước độ hạt atomic

Từ bảng bất biến, mỗi metric cần mô tả **đơn vị đếm, thời điểm tăng/giảm và mức nhất quán khi đọc**:

- `invocationsStarted`: số lần join point thật sự đi vào advice được chọn; nếu một request qua nhiều join points thì có thể có nhiều lượt.
- `inFlight`: số scopes đã mở nhưng chưa hoàn tất theo ranh giới đã định nghĩa.
- `failures`: số scopes kết thúc bằng exception theo góc nhìn của observer; lỗi bị xử lý ở tầng trong có thể không được đếm tại tầng ngoài.
- `duration`: thời gian quanh đúng scope; nếu cần end-to-end async duration, mốc kết thúc phải theo task completion.

`AtomicInteger` thích hợp với những chuyển trạng thái cần đọc giá trị chính xác và CAS của **một biến**; `LongAdder` hữu ích cho cập nhật tổng throughput cao khi không đòi `sum()` là snapshot tuyến tính trong lúc vẫn ghi. Dù mỗi counter được cập nhật an toàn, **đọc ba counter liên tiếp không tạo ra một transaction snapshot**. Nếu báo cáo bắt buộc có bất biến liên trường tại một thời điểm, cần thêm cơ chế snapshot/quiescence phù hợp.

Đừng gắn user ID, request ID hoặc giá trị cardinality không giới hạn làm nhãn metric; chúng có thể gây bùng nổ series và kéo dài vòng đời dữ liệu nhạy cảm.

## 6. Một invocation cần một hợp đồng đi qua bốn ranh giới

Xét chuỗi `Observe(Policy(Business))`. Khi áp dụng bất biến cho một lời gọi, đặt các câu hỏi theo đúng thứ tự:

1. **Admission:** pointcut/proxy/weaving có chọn đúng join point không? Bỏ qua proxy hoặc match cả logger có thể làm metrics thiếu hoặc đệ quy.
2. **Entry:** đã capture policy revision và thông tin cần thiết một lần chưa? Counter in-flight đã tăng sau khi chắc chắn scope được mở chưa?
3. **Continuation:** method gốc được gọi bao nhiêu lần? Retry, cache hit, short-circuit và nested advice có làm đổi đơn vị đếm không?
4. **Exit:** return, exception, timeout/cancel, callback failure và cleanup có cùng owner theo đúng lifetime không?

```text
on selected call:
  snapshot minimal policy + invocation identity
  mark entry / update inFlight
  try:
      invoke next according to contract
  catch original:
      observe failure best effort, preserve original
      rethrow original
  finally:
      close owned scope and update aggregate
```

Đây là **giả mã synchronous**. Không có engine AOP chung nào bảo đảm `proceed` được gọi một lần nếu around advice chủ động short-circuit hoặc retry. Nếu telemetry failure bắt buộc làm hỏng thao tác, cần ghi rõ hợp đồng; với logging tùy chọn nên xử lý lỗi phụ để không che exception gốc.

## 7. Shared map, cache và registry cần owner riêng

Một `ConcurrentHashMap` bảo đảm một số thao tác đồng thời trên **cấu trúc map**, nhưng không làm cho value mutable tự thread-safe hay cho một chuỗi nhiều bước thành transaction.

Một cache trong aspect cần làm rõ:

| Quyết định | Ví dụ câu hỏi |
| --- | --- |
| Identity | Key theo method, target identity, tenant, config revision hay full arguments? |
| Isolation | Có cache dữ liệu của tenant A rồi trả cho B không? |
| Consistency | Điều kiện invalidation khi policy hoặc target thay đổi? |
| Size | TTL, capacity và eviction có giới hạn không? |
| Duplication | Khi nhiều threads cache miss, có cho chạy song song hay cần single-flight? |
| Ownership | Nếu value giữ target/classloader, ai xóa khi owner hết vòng đời? |

Một `computeIfAbsent` có thể giải quyết một số race tạo entry, nhưng mapping function không nên thực hiện blocking I/O hay gọi đệ quy vào cùng map khi API cấm hoặc cơ chế đồng bộ bên trong có thể gây vấn đề. Với nhu cầu “chỉ một computation trên mỗi key”, cần thiết kế single-flight và đường timeout/exception rõ ràng, thay vì suy từ tên concurrent map.

## 8. Scope nhỏ, cleanup đúng và telemetry không làm chậm nghiệp vụ

Một advice tốt để đo/ghi sự kiện nên ngắn gọn: thu thập những trường tối thiểu, cập nhật counter, chuyển tiếp nghiệp vụ và giải phóng đúng scope. Nếu phải đồng bộ hóa aggregate, chỉ khóa **đoạn cập nhật thật sự cần bảo vệ**, không giữ mutex chung xuyên `proceed()` hoặc một lời ghi log qua mạng.

Đối với logging/tracing tùy chọn:

- Chọn trường được phép thay vì serialize toàn bộ request/result.
- Không ghi event khi đang giữ lock bảo vệ nghiệp vụ, trừ khi invariant yêu cầu.
- Dùng queue có giới hạn và chính sách backpressure/drop rõ ràng nếu xuất bất đồng bộ.
- Loại trừ logger/exporter khỏi pointcut để ngăn advice tự can thiệp.
- Phục hồi scope/context trong `finally`; không giữ `ThreadLocal` từ request này qua request khác.
- Xử lý lỗi formatter/sink theo hợp đồng để không thay outcome nghiệp vụ ngoài chủ đích.

Đối với audit hoặc policy bắt buộc, “best effort” có thể không đáp ứng yêu cầu; phải thiết kế độ bền, mức nhất quán và failure policy riêng. Phần tiếp theo sử dụng ví dụ Java 17 để **kiểm chứng invariant in-flight và kết quả của hai lời gọi cùng chạy**, rồi mở rộng test cho lỗi, concurrency, shutdown và async.

## 9. Ví dụ Java 17 runnable: hai lời gọi thật sự chồng lấn và thống kê an toàn

Chương trình **`ConcurrentAspectDemo.java`** mô phỏng một aspect quan sát bằng JDK dynamic proxy:

- Có **một target** và **một aspect state dùng chung**.
- Hai worker threads gọi `proxy.execute("A")` và `proxy.execute("B")`.
- Target dùng `CountDownLatch(2)` để bảo đảm **cả hai invocations đồng thời vào target trước khi cả hai được phép trả**.
- Advice dùng `LongAdder` cho các bộ đếm tổng, `AtomicInteger` cho số invocation đang chạy và max overlap.
- Các exceptions reflective được gỡ khỏi `InvocationTargetException` để caller thấy lỗi gốc.
- Một lời gọi `"BAD"` sau khi hai calls thành công minh họa cleanup trên failure.
- Các threads **không in log trong lúc chạy song song**; main chỉ in results sau `Future.get()`, nên output không phụ thuộc scheduling giữa A và B.

**Quan trọng:** JDK dynamic proxy trong ví dụ là một hình thức interception tại interface boundary, **không phải bytecode weaving**. Nó chỉ quan sát các calls đi qua proxy.

Tạo file **`ConcurrentAspectDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public class ConcurrentAspectDemo {
    interface Service {
        String execute(String id);
    }

    static final class Target implements Service {
        private final CountDownLatch bothEntered = new CountDownLatch(2);

        @Override
        public String execute(String id) {
            bothEntered.countDown();
            try {
                bothEntered.await();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted", interrupted);
            }

            if ("BAD".equals(id)) {
                throw new IllegalArgumentException("bad id");
            }
            return "OK:" + id;
        }
    }

    static final class MetricsAspect {
        final LongAdder calls = new LongAdder();
        final LongAdder successes = new LongAdder();
        final LongAdder failures = new LongAdder();
        final AtomicInteger inFlight = new AtomicInteger();
        final AtomicInteger maxInFlight = new AtomicInteger();
    }

    static Service observed(Service target, MetricsAspect aspect) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] { Service.class },
                (proxy, method, args) -> {
                    String invocationId = (String) args[0]; // local từng call
                    if (invocationId == null) {
                        throw new IllegalArgumentException("null id");
                    }

                    aspect.calls.increment();
                    int concurrent = aspect.inFlight.incrementAndGet();
                    aspect.maxInFlight.accumulateAndGet(concurrent, Math::max);

                    try {
                        Object value = method.invoke(target, args);
                        aspect.successes.increment();
                        return value;
                    } catch (InvocationTargetException wrapped) {
                        aspect.failures.increment();
                        throw wrapped.getCause();
                    } finally {
                        aspect.inFlight.decrementAndGet();
                    }
                }
        );
    }

    public static void main(String[] args) throws Exception {
        MetricsAspect aspect = new MetricsAspect();
        Target target = new Target();
        Service proxy = observed(target, aspect);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> first = pool.submit(() -> proxy.execute("A"));
            Future<String> second = pool.submit(() -> proxy.execute("B"));

            // Hai targets phải cùng đến latch trước khi được trả.
            // Future.get() cũng bảo đảm đọc kết quả sau completion.
            System.out.println("RESULT A=" + first.get());
            System.out.println("RESULT B=" + second.get());

            try {
                proxy.execute("BAD");
            } catch (IllegalArgumentException ex) {
                System.out.println("RESULT ERROR=" + ex.getMessage());
            }

            System.out.println("STATS calls=" + aspect.calls.sum()
                    + " success=" + aspect.successes.sum()
                    + " failure=" + aspect.failures.sum()
                    + " inFlight=" + aspect.inFlight.get()
                    + " maxInFlight=" + aspect.maxInFlight.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac ConcurrentAspectDemo.java
java ConcurrentAspectDemo
~~~

**Stdout kỳ vọng, đúng thứ tự:**

~~~text
RESULT A=OK:A
RESULT B=OK:B
RESULT ERROR=bad id
STATS calls=3 success=2 failure=1 inFlight=0 maxInFlight=2
~~~

### 9.1. Vì sao chắc chắn hai lời gọi có overlap?

Target có `CountDownLatch(2)`. Invocation đầu tiên gọi `countDown()` rồi chờ `await()`. Chỉ khi invocation thứ hai cũng gọi `countDown()`, latch mới bằng 0 và hai invocations có thể tiếp tục. Cả hai handler đã tăng `inFlight` trước khi target chờ, và invocation đầu không thể giảm `inFlight` trước khi invocation thứ hai đã tăng.

Vì thế `maxInFlight` **chắc chắn đạt ít nhất 2**. Có đúng 2 worker threads và không có invocation khác trước khi cả hai futures hoàn tất, nên max là **2**. Đây là bằng chứng đồng thời mạnh hơn dùng `Thread.sleep` hay quan sát thứ tự log ngẫu nhiên.

### 9.2. Vì sao kết quả `RESULT A` luôn được in trước `RESULT B`?

Main gọi `first.get()` rồi in A, sau đó gọi `second.get()` và in B. Dù thread nào hoàn tất trước, thứ tự **in của main** luôn là A rồi B. Không được hiểu output này là “worker A hoàn thành trước B”.

`Future.get()` giúp đợi task completion và cung cấp những bảo đảm memory-visibility cần thiết để main đọc kết quả tasks.

### 9.3. Vì sao có 3 calls, 2 successes, 1 failure?

Hai calls A/B đi qua proxy, target trả `OK:A` và `OK:B`, nên `successes` tăng 2. Call `BAD` được thực hiện sau, vẫn qua proxy; target ném `IllegalArgumentException`. `Method.invoke` bọc lỗi bằng `InvocationTargetException`, handler gỡ `getCause()`, tăng `failures` rồi ném lại. Caller bắt đúng loại lỗi `IllegalArgumentException`.

`calls` tăng một lần ở mỗi invocation đi qua handler, tổng 3. Số này được tính **sau khi cả ba invocations đã kết thúc**, không phải snapshot đang tranh chấp concurrent updates.

### 9.4. Vì sao `inFlight=0` sau khi có lỗi?

`inFlight.decrementAndGet()` nằm trong `finally`. Nó chạy khi target trả bình thường và khi `Method.invoke` ném `InvocationTargetException`. Sau ba lời gọi, active count trở về 0.

Đây là thói quen quan trọng: mọi state “đang hoạt động” phải có **một điểm cleanup chắc chắn** khi rời synchronous advice scope. Nếu advice có thể return early hoặc throw ở đoạn setup trước `try`, cần điều chỉnh biên cleanup cho mọi đường đã thực sự tăng counter.

### 9.5. Vì sao `LongAdder` phù hợp demo?

`calls/successes/failures` chỉ cần tổng aggregate sau khi tasks đã hoàn tất; không dùng mỗi increment làm ID, cũng không đòi snapshot nhất quán tại mọi microsecond. `LongAdder` phù hợp cho dạng metrics này.

`inFlight` lại cần giá trị vừa tăng tại mỗi invocation để tính **max overlap**; dùng `AtomicInteger.incrementAndGet()` và `accumulateAndGet(Math::max)` phù hợp.

### 9.6. Code thể hiện state nào là riêng từng invocation?

`invocationId` là **local variable** của callback handler; invocation A và B có local riêng. Nó không được lưu vào shared aspect field, vì vậy không có `aspect.currentId` để thread A/B ghi đè. `MetricsAspect` chỉ chứa aggregate counters được đồng bộ qua API atomic/concurrent.

### 9.7. Ranh giới và giả định demo

- Latch gồm **đúng hai arrivals** dùng để chứng minh overlap; nếu chỉ gửi một call, method sẽ đợi mãi. Không dùng latch này trong service production; đây là **test harness**.
- `ExecutorService` có hai workers; `Future.get()` có thể block nếu test bị lỗi. Một integration test thực nên có **timeout** và thông báo thất bại rõ để tránh treo.
- Method `Service.execute` chỉ đại diện cho một interface method; handler chưa định nghĩa riêng `equals/hashCode/toString` hay pointcut matching phức tạp. Trên API thật, cần chính sách cho Object methods, overloads và reflection.
- Trường hợp input null bị từ chối **trước khi đếm calls** theo một chính sách minh họa; vì vậy định nghĩa metric calls của demo là “các invocation có input id hợp lệ đã qua bước validation”. Nếu phải đếm cả rejected calls, di chuyển phép đếm ra boundary khác và test lại.
- `MetricsAspect` không ghi logs per-thread và không gắn metrics trực tiếp vào target. Direct call tới `target.execute` bỏ qua handler của proxy.
- Không có async `CompletionStage` trong demo; `ExecutorService` chỉ dùng để tạo hai concurrent synchronous invocations, cho phép stdout được quyết định bởi main.
- Không chứng minh `LongAdder.sum()` là snapshot tuyến tính khi updates còn đang chạy; ở đây đọc **sau completion**.
- Đây là AOP qua proxy, không phải một công cụ source/bytecode weaving; không áp kết quả về self-call hoặc class identity cho mọi engine.

## 10. Vì sao đặt một lock quanh toàn bộ proceed có thể gây lỗi?

Một cách “sửa race” vội vàng:

~~~java
synchronized (aspect) {
    return proceed();
}
~~~

Đây chỉ là **mã minh họa**: giả định `aspect` và `proceed()` được khai báo trong một advice. Nó khiến một aspect instance dùng chung trở thành **nút thắt khóa** cho mọi target invocation nếu tất cả cần lock đó.

Hậu quả có thể là:
- Tăng throughput contention, p95/p99 latency.
- Một method I/O chậm khiến các methods khác cùng aspect phải chờ.
- Blocking trong `proceed()` dẫn tới deadlock khi một lời gọi cần callback từ công việc cũng phải qua lock.
- Reentrancy/lock ordering với locks của target hoặc các aspects khác trở nên khó quản lý.
- Dễ che giấu data race của aspect mà không sửa ownership sai của state.

**Giải pháp ưu tiên:** tách state per-invocation thành local, dùng atomic primitives cho aggregate, giới hạn scope lock chỉ quanh **bất biến chung thật sự cần bảo vệ**. Nếu business contract bắt buộc serial execution, khóa rộng có thể hợp lý, nhưng đó là **quyết định ngữ nghĩa** cần được công bố và đo.

### 10.1. Lock scope nên nhỏ

Đừng giữ lock chỉ để log I/O hoặc đợi network. Nếu phải bảo vệ một map và value, thao tác khóa chỉ nên thực hiện phần chuyển trạng thái tối thiểu, sau đó thả lock trước khi gọi các API ngoài.

### 10.2. Lock ordering giữa nhiều aspects

Nếu aspect A luôn khóa L1 rồi L2, còn aspect B khóa L2 rồi L1, hai threads có thể deadlock. Khi nhiều advice cùng join point, **precedence/ordering** không chỉ tác động log mà còn thứ tự acquire locks. Nên đặt chính sách lock order toàn hệ thống hoặc tránh nested locks qua continuation.

### 10.3. Reentrancy và callback

`synchronized` trên Java monitor là reentrant cho cùng thread, nhưng điều này **không** làm mọi pattern callback an toàn. Một callback chạy ở thread khác không có cùng reentrant ownership; lock đang giữ có thể ngăn callback cần để task hiện tại kết thúc.

## 11. ThreadLocal: cách dùng đúng và vì sao vẫn có thể rò

Một `ThreadLocal<TraceContext>` gắn giá trị với **thread hiện tại**, không gắn tự nhiên với logical request hay aspect instance. Khi thread pool worker xử lý request A rồi B, một giá trị không được dọn có thể “rò” sang B.

### 11.1. Scope có restore/remove trong finally

Mã minh họa Java:

~~~java
// Giả định TRACE và ctx, proceed() đã tồn tại.
TraceContext previous = TRACE.get();
TRACE.set(ctx);
try {
    return proceed();
} finally {
    if (previous == null) {
        TRACE.remove();
    } else {
        TRACE.set(previous);
    }
}
~~~

Kỹ thuật giữ previous value cho **nested scopes**. Nếu chỉ `remove()` vô điều kiện ở inner advice, nó có thể làm mất context outer còn đang cần sau khi inner return.

Ở production, cần định nghĩa rõ semantics nếu một scope trước đó đã `set(null)` có ý nghĩa khác “chưa có value”; đoạn minh họa xử lý cả hai như không có context.

### 11.2. Thread pool không có nghĩa request-local

Một `ExecutorService` tái sử dụng worker threads. Nếu advice viết `TRACE.set(request)` nhưng chỉ `remove()` ở nhánh success, request A ném lỗi rồi B được thực thi trên cùng thread có thể nhìn thấy A. Vấn đề bao gồm cả **dữ liệu riêng tư**, không chỉ log sai.

### 11.3. Không truyền ThreadLocal “tự động” qua async

`CompletableFuture.supplyAsync()` hoặc callback có thể chạy trên thread khác. Value trong `ThreadLocal` của caller không tự có mặt ở worker. `InheritableThreadLocal` cũng không phải giải pháp tổng quát cho thread pools, vì inheritance xảy ra lúc tạo thread, không theo mỗi logical task.

Cần snapshot **dữ liệu tối thiểu cần truyền** và thiết lập/restore trong scope của task tại thread mới, hoặc dùng abstraction context propagation có hợp đồng rõ. Không giữ context của caller mở mãi trong pool thread để chờ task completion.

### 11.4. Scope theo logical operation khác scope theo thread

Một logical operation có thể đi qua các threads T1, T2 và T3. Ngược lại một thread T1 có thể chạy nhiều operations nối tiếp. Nếu requirement là trace theo operation, gắn state vĩnh viễn vào T1 là sai owner. Đây là khác biệt nền tảng giữa **per-thread aspect state** và **per-control-flow/task state**.

## 12. Async và CompletionStage: aspect cần biết mình đo đến mốc nào

Method:

~~~java
CompletionStage<String> fetchAsync(String key);
~~~

trả về một **handle**; tác vụ có thể hoàn tất sau khi method return. Around advice đồng bộ:

~~~text
started = now()
result = proceed()         # có thể return CompletionStage đang pending
record(now() - started)     # đo invocation/dispatch latency
return result
~~~

không tự đo tới khi stage completed. Nếu muốn đo end-to-end, observer có thể đăng ký callback dựa trên một **per-task snapshot** `started` và operation ID, sau đó record outcome khi task completed.

### 12.1. Tạo dependent stage có thể đổi semantics

Trong Java, `stage.whenComplete(observer)` trả **một dependent stage**; bản thân lời gọi đăng ký callback không thay đổi stage gốc. Nếu advice return dependent stage thay original, lỗi ném ra từ observer có thể ảnh hưởng outcome của dependent stage.

Nếu mục tiêu chỉ quan sát và cần giữ identity/lifecycle của handle, có thể đăng ký callback rồi **return original**. Nhưng vẫn phải quyết định xử lý lỗi của observer và tránh giữ unbounded callbacks với futures không bao giờ complete.

### 12.2. Không làm blocking join chỉ để “dễ lấy result”

Một advice gọi `join()` trên future pending có thể block caller thread, đổi API async thành synchronous wait, tạo deadlock khi executor không còn workers và làm tail latency xấu. Async completion cần được xử lý như async, không chỉ có `try/catch` quanh method return.

### 12.3. Cancellation và timeout

Một future bị cancel không bảo đảm I/O đang chạy dừng tức thì; callback/metrics cleanup phải dựa trên trạng thái task và ownership hợp lệ. Một timeout observer không được coi là phép hủy remote action đã cam kết. Nếu aspect giữ in-flight task count, phải quy định chính xác mốc decrement: khi method return handle, khi task completed, khi caller cancel hay khi resource thực sự dừng.

### 12.4. Bounded state

Nếu một aspect lưu `Map<Id,TaskContext>` cho mọi pending task, các tasks treo có thể giữ memory vô hạn. Cần quota, timeout/expiry, cleanup trên success/error/cancel và bảo đảm không giữ toàn bộ arguments/target khi chỉ cần một ID và timestamp.

## 13. Reentrancy và recursion trong aspect

Một aspect có thể kích hoạt chính nó gián tiếp:

~~~text
Service method
  -> Metrics advice
      -> MetricsExporter.record()
          -> Metrics advice
              -> MetricsExporter.record()
                  -> ...
~~~

Nếu pointcut chọn cả các methods của metrics exporter, instrumentation có thể đệ quy vô hạn hoặc làm số liệu trùng. Nên cấu hình exclude phù hợp hoặc dùng một cơ chế **reentrancy guard** với lifecycle đúng, theo khả năng engine.

### 13.1. Guard bằng ThreadLocal phải cleanup

Một guard thread-scoped có thể lưu `Boolean` đang ở trong advice:

~~~text
if guard == true:
    proceedWithoutMetrics()
else:
    guard = true
    try:
        metrics(); proceed()
    finally:
        restorePreviousGuard()
~~~

Đây là giả mã. Cần lưu previous state để hỗ trợ nesting và không giữ guard vĩnh viễn sau error. Nhưng với async task được chuyển thread, guard thread-local không tự bao logical operation. Ngoài ra, một advice được dệt trực tiếp vào code khác proxy boundary có semantics riêng.

### 13.2. Guard có thể che nested operations quan trọng

Không tự bỏ metric mọi nested call chỉ vì “tránh recursion”. Nếu yêu cầu đo nested service calls, chỉ loại những đường instrumentation gây vòng lặp hoặc phân loại event rõ; một guard quá rộng có thể làm thiếu telemetry.

### 13.3. Advice chạy nhiều lần do retry

Một around advice thực hiện retry có thể gọi continuation nhiều lần, nếu engine cho phép. Nếu nested metric nằm bên trong retry, nó có thể chạy mỗi attempt; nếu ở ngoài, nó đo logical operation. Phải định nghĩa rõ lúc nào tăng `calls`, `attempts`, `failures` và `inFlight`, tránh đếm một lỗi nhiều lần do nhiều advice cùng catch/rethrow.

## 14. Exception handling và độ an toàn của advice

Một observer không nên tự nhiên biến lỗi nghiệp vụ thành success hoặc loại lỗi khác chỉ vì chạy song song.

### 14.1. Gỡ wrapper reflection đúng cách

Với JDK dynamic proxy, `Method.invoke` bọc exception từ target trong `InvocationTargetException`. Handler thường lấy `getCause()` rồi ném lại nguyên lỗi khi mục tiêu là transparency.

Nếu interface có checked exceptions, phải giữ đúng throws contract của proxy; không tùy ý ném checked type không được khai báo rồi mong caller luôn nhận trực tiếp.

### 14.2. Metrics có thể khác nếu advice throw trước khi target chạy

Một advice before validation có thể throw trước `proceed()`. Nếu increment `calls` sau validation, metric không đếm denied attempts. Nếu increment trước, nó đếm cả denied attempts. Đây là **định nghĩa measurement boundary**, không phải mặc định một cách đúng cho mọi hệ thống.

Trong ví dụ Java 17, handler kiểm tra null ID trước khi increment. Vì thế `calls` có nghĩa là **valid-id intercepted invocations**, không phải mọi API entry.

### 14.3. Lỗi của instrumentation không nên che lỗi target nếu policy là best effort

Một `finally` gọi log sink mà sink tự throw có thể thay exception target hoặc return value. Nếu telemetry được thiết kế best-effort, cần cách cô lập/ghi nhận lỗi logger, không nuốt mọi `Throwable` rồi để mất lỗi nghiêm trọng.

Với audit bắt buộc, chính sách có thể ngược lại: ghi audit thất bại khiến operation bị từ chối. Nhưng đây là một **quyết định hợp đồng**, phải được nói rõ và test ở cả single-thread lẫn concurrent load.

### 14.4. Handler và shared fields cần lifecycle rõ

Khi aspect shutdown, nếu vẫn có invocations active, việc đóng exporter/buffer quá sớm có thể làm advice errors. Một `closed` flag atomic có thể giúp quyết định nhận mới/flush sau khi active về 0, nhưng chỉ một flag không tự bảo đảm invariant đa bước. Cần owner và shutdown protocol hợp lệ.

## 15. Proxy, weaving và độ phủ đồng thời

Một proxy interface chặn các lời gọi **đi qua proxy**. Target tự gọi `this.inner()` hoặc caller gọi target trực tiếp có thể bypass handler của delegating proxy. Điều đó làm metrics thiếu, nhưng không nhất thiết làm target chạy tuần tự hay an toàn hơn.

Một weaver source/bytecode có thể chèn hook trực tiếp vào method execution, có thể quan sát cả internal call nếu join point được weave. Tuy nhiên:
- Không phải mọi công cụ hỗ trợ cùng loại join point.
- Scope weaving có thể bỏ qua classes/loader.
- Thứ tự nhiều aspects có thể làm thay đổi lock acquisition.
- Hook bytecode có thể được nhiều threads chạy đồng thời như thường.
- Dệt trực tiếp không tự biến mutable state của aspect thành thread-safe.

### 15.1. Không dùng synchronized wrapper như “bản vá” cho target tùy tiện

Một proxy khóa mọi lời gọi có thể làm giảm race của target, nhưng direct-target call hoặc self-call bypass proxy vẫn có thể không chịu lock đó. Nếu business invariant cần serialization, bảo vệ ở **trusted concurrency boundary** phù hợp và test mọi entry path, không dựa vào “tất cả callers chắc chắn qua proxy” khi chưa chứng minh.

### 15.2. Object identity và locks

`synchronized(proxy)` và `synchronized(target)` dùng **hai monitors khác nhau** nếu proxy/target là objects riêng. Nếu một số callers khóa target và số khác khóa proxy, chúng không điều phối cùng một critical section. Đây là lỗi substitutability/concurrency rất khó nhận ra.

### 15.3. Advice có thể đổi thread-affinity

Một around advice tự đưa target execution sang worker thread có thể vi phạm API vốn đòi chạy trên caller thread (UI, actor, thread-confined resource). Tính an toàn không chỉ là state không race, mà còn giữ đúng thread-affinity, ordering và cancellation semantics đã công bố.

## 16. Performance, contention và quan sát đúng khi tải cao

Một advice thread-safe vẫn có thể gây bottleneck.

### 16.1. Những metric cần đo

- Số concurrent invocations, in-flight high-water mark.
- Latency của advice trước/sau target.
- CPU contention hoặc thời gian chờ locks.
- Throughput, p50/p95/p99 và tail amplification.
- Logging queue depth/dropped events.
- Cache hit/miss/collision/eviction.
- Số tasks pending và context entries giữ trong registry.
- Time spent in metrics exporter/serializer.
- GC retention do aspects/handlers/callbacks.

Một global lock bảo đảm không mất update nhưng có thể serialize toàn ứng dụng. Một lock-free counter giảm contention nhưng vẫn có thể tạo quá nhiều logs hoặc cardinality.

### 16.2. Không dùng wall-clock làm duration monotonic

`System.currentTimeMillis()` có thể chịu ảnh hưởng wall-clock adjustments. Với elapsed time trong một JVM, dùng `System.nanoTime()` và tính chênh lệch; không dùng giá trị tuyệt đối `nanoTime` như timestamp để lưu liên tiến trình.

### 16.3. LongAdder và snapshot

`LongAdder.sum()` trong lúc updates đang chạy không phải snapshot atomic. Nếu dashboard đọc `calls`, `success`, `failure` ở thời điểm hơi khác nhau, tổng có thể tạm thời không khớp. Trong test của bài, đọc sau khi workers hoàn tất để nhận con số xác định.

### 16.4. Sampling và data privacy

Ghi args/result của mọi concurrent call có thể chứa secrets và chiếm nhiều băng thông. Dùng sampling/bounded queues/sanitization nhưng phải phân biệt **sampled trace** với **đếm sự kiện bắt buộc**. Metrics cardinality theo raw request ID có thể tăng vô hạn; đừng đưa per-request state vào metric labels tùy tiện.

## 17. Kiểm thử aspect chạy song song đúng cách

### 17.1. Test bắt buộc phải có overlap

Chỉ chạy 1.000 tasks trong thread pool không chứng minh có hai advice cùng hoạt động tại một thời điểm. Chúng có thể chạy nối tiếp rất nhanh. Dùng:
- `CountDownLatch` để buộc nhiều workers vào một barrier.
- `CyclicBarrier` nếu cần nhiều vòng, kèm timeout.
- `Phaser` nếu số participants/lifecycle phức tạp.
- Bắt thời điểm `inFlight >= 2` trong một critical region có kiểm soát.

Tránh `Thread.sleep` như phép chứng minh timing: máy chậm/nhanh hoặc scheduling khác có thể làm test flaky.

### 17.2. Ma trận test

| Trường hợp | Kỳ vọng |
| --- | --- |
| Hai calls cùng vào target | `maxInFlight >= 2` khi không chủ đích serialize. |
| N calls thành công | `successes=N`, tổng theo policy, inFlight về 0. |
| Một target throw | Exception type/cause giữ đúng, failure +1, inFlight về 0. |
| Before advice throw | Không có target invocation; counters đúng theo boundary khai báo. |
| Around advice skip | Không có target execution; result/failure theo policy. |
| Retry attempts | Phân biệt logical count và attempts. |
| Target tự gọi nội bộ | Proxy có thể không thấy inner; kết quả test phải theo mechanism. |
| Reentrant advice | Không recursion vô hạn; nested context restore đúng. |
| ThreadLocal cleanup | Request B không nhìn context A trên reused worker. |
| Async stage pending | Không đếm task completion ở method return nếu policy end-to-end. |
| Async error/cancel | Completion context được giải phóng đúng. |
| Concurrent map/cache | Không tạo value trùng ngoài contract; map bounded. |
| Shared target state | Target invariants giữ đúng dưới concurrent calls. |
| Shutdown with active calls | Không đóng resource khi advice vẫn đang dùng nếu contract cấm. |
| High contention | Throughput/tail latency còn trong ngân sách. |

### 17.3. Test exception bằng loại lỗi thật

Với JDK proxy, muốn assert handler bảo toàn `IllegalArgumentException`, nên chạy method target ném lỗi đó rồi kiểm loại/cause ở caller; không chỉ assert “có exception bất kỳ”.

### 17.4. Test ThreadLocal cùng một worker thread

Để chứng minh cleanup, có thể dùng **single-thread executor** cho hai requests liên tiếp: A set context rồi throw, B đọc context lúc bắt đầu và phải thấy giá trị mặc định đúng, không phải A. Nếu dùng 2 threads không kiểm soát, B có thể chạy trên thread khác và test vẫn pass dù leak trên A thread.

### 17.5. Test concurrency không nên dựa vào thứ tự stdout của workers

Hai threads có thể in xen kẽ; nếu output order không phải yêu cầu nghiệp vụ, assert **counts/outcomes** và happens-before được thiết kế. Ví dụ runnable trong bài in từ main sau `Future.get`, nhờ đó stdout là deterministic nhưng vẫn xác nhận overlap qua latch và `maxInFlight`.

### 17.6. Dùng timeout cho barrier trong test thực

`CountDownLatch.await()` không timeout trong ví dụ tối giản có thể treo nếu worker thứ hai không chạy. Khi biến demo thành test CI, dùng `await(timeout, unit)` và `Future.get(timeout, unit)`, báo lỗi rõ khi thiếu participant; đảm bảo shutdown trong `finally`.

## 18. Thiết kế shutdown, lifecycle và không giữ state vô hạn

### 18.1. Aspect shared thường sống lâu hơn một target

Một exporter/registry chung có thể phục vụ nhiều target. Khi target A kết thúc, không được đóng exporter khi B vẫn đang dùng. Cần owner cấp module/service và shutdown ordering hợp lệ.

### 18.2. Per-target state cũng có thể bị nhiều threads cùng gọi

Nếu một target singleton nhận 20 threads, per-target aspect state là **state dùng chung cho 20 concurrent calls**. Không coi “per-target” là “per-request”. Muốn đo request riêng, dùng per-invocation context.

### 18.3. Memory retention

Một global registry giữ `Map<Target,State>` với strong keys không được remove có thể làm target còn reachable vô hạn. Một aspect lưu `lastThrowable` hoặc `lastArgs` có thể giữ object graph chứa secrets. Cần cleanup, bounded cardinality và quyền sở hữu rõ.

### 18.4. Không dựa vào GC để đóng resource

Nếu aspect giữ file, socket, listener hay callback registration, giải phóng theo `close/unregister/cancel` của owner, không chờ finalization/GC có thời điểm không xác định.

### 18.5. Shutdown đồng thời với advice

Nếu shutdown có thể chạy cùng lúc với invocations, xác định chính sách:
- Chặn invocations mới trước hay sau khi đánh dấu closing?
- Đợi in-flight về 0 hay deadline?
- Flush/close metrics buffer khi nào?
- Một invocation sau khi shutdown bắt đầu phải fail loại lỗi nào?
- Nếu close tự ném, có được che lỗi target đang xử lý không?

Cần state machine/lifecycle contract, không chỉ thêm một `volatile boolean closed` rồi bỏ qua các chuyển trạng thái.

## 19. Những lỗi phổ biến trong AOP đồng thời

**“Aspect dùng chung nên lưu `startTime` vào field cho tiện.”** Sai khi nhiều calls chồng lấn; dùng per-invocation local state.

**“Đánh dấu field là volatile đủ sửa mọi race.”** Không. Volatile không làm compound update atomic và không tách context từng invocation.

**“Per-target aspect chắc chắn chỉ có một thread.”** Không. Một target singleton có thể nhận nhiều workers.

**“LongAdder luôn cho tổng chính xác tại mọi thời điểm.”** Không. `sum()` không phải atomic snapshot khi updates đồng thời.

**“AtomicInteger cho từng field bảo đảm invariant giữa tất cả fields.”** Không. Cần giao thức cập nhật/đọc đồng bộ ở phạm vi invariant.

**“ConcurrentHashMap nghĩa là check-then-put tự atomic.”** Không; nhiều operations độc lập có thể interleave.

**“Dùng synchronized quanh toàn bộ proceed là tối ưu.”** Không mặc định; có thể gây contention/deadlock và làm thay đổi throughput semantics.

**“Một ThreadLocal là state per-request.”** Không với thread pools/async; phải restore/remove.

**“InheritableThreadLocal luôn truyền đúng request context tới executor.”** Không; thread pool reuse khiến inheritance không đại diện mỗi task.

**“Finally chạy khi async future hoàn tất.”** Không nếu finally bao synchronous method invocation đã return stage.

**“Future cancelled nghĩa là remote work chắc chắn dừng.”** Không; phụ thuộc task/resource contract.

**“Advice nhận Throwable nào cũng nên catch rồi return success để tránh lỗi.”** Sai; che lỗi nghiệp vụ và có thể mất invariants.

**“Logging ở nhiều aspects trước/sau luôn có một thứ tự toàn hệ thống.”** Không với concurrent invocations; chỉ có quan hệ order trong từng flow theo thiết kế.

**“Proxy chặn mọi lời gọi của target.”** Không với direct target/self-invocation trong delegating proxy.

**“Dệt trực tiếp method body sẽ tự làm state aspect thread-safe.”** Không. Hook có thể được nhiều threads chạy song song.

**“Demo có hai futures thì chắc chắn hai methods cùng chạy.”** Không nếu không có barrier/overlap evidence.

**“Một test happy path chứng minh aspect an toàn.”** Không; cần throw, timeout, cancellation, overlap, reentrancy và shutdown.

## 20. Bài tập vận dụng có đáp án

### Bài 1 — Timer dùng chung

Hai threads A/B cùng dùng một aspect có field `long started`. B overwrite sau khi A ghi; A tính duration sai. Chỉ thêm `volatile` có sửa không?

**Đáp án:** Không. Visible value vẫn có thể là của B; dùng start local theo mỗi invocation.

### Bài 2 — Bộ đếm

100 threads cùng chạy `int count++` trong shared aspect. Có chắc count tăng 100 không?

**Đáp án:** Không. Dùng `AtomicInteger`, `LongAdder` hoặc synchronization phù hợp với semantics.

### Bài 3 — Snapshot metrics

`calls` và `successes` là LongAdder. Khi tasks đang chạy, `calls.sum()` có thể không bằng `successes.sum()+failures.sum()`. Có nhất thiết bug không?

**Đáp án:** Không. Còn in-flight calls và các reads không phải snapshot atomic; xác minh boundary trước khi kết luận.

### Bài 4 — Target singleton

Một aspect per-target gắn với singleton service. Có thể lưu `currentUser` mutable trong field của aspect không?

**Đáp án:** Không an toàn nếu service nhận concurrent users; dùng invocation/task context, không dùng field per-target chung cho per-request data.

### Bài 5 — Thread pool

Advice `ThreadLocal.set(user)` rồi target throw; cleanup chỉ ở nhánh success. Request sau có thể thấy user cũ không?

**Đáp án:** Có nếu worker thread được tái sử dụng. Dùng finally để restore/remove.

### Bài 6 — Lock rộng

Aspect dùng `synchronized` bao trọn một method I/O chậm. Tại sao có thể giảm throughput?

**Đáp án:** Invocations cùng lock bị serialize và đợi I/O; cần rút ngắn critical section hoặc đổi ownership, trừ khi serialization là hợp đồng chủ đích.

### Bài 7 — Barrier

Hai worker threads được tạo nhưng không có synchronization nào, test có chắc maxInFlight=2 không?

**Đáp án:** Không. Scheduler có thể chạy xong A rồi mới chạy B. Dùng latch/barrier phù hợp như chương trình demo.

### Bài 8 — Error cleanup

Around advice tăng inFlight trước proceed, target ném exception. Nếu decrement chỉ ở đường return thì sao?

**Đáp án:** inFlight bị giữ cao sai; đặt cleanup trong finally sau khi tăng.

### Bài 9 — Async

Method trả future pending. Advice decrement inFlight trong finally ngay sau return. Điều đó đúng không?

**Đáp án:** Đúng **nếu** metric định nghĩa inFlight của synchronous invocation; sai nếu metric định nghĩa số logical tasks còn pending. Phải ghi rõ scope.

### Bài 10 — Proxy bypass

Một target gọi `this.inner()`, aspect interceptor chỉ trên proxy inner. Có tăng counter inner không?

**Đáp án:** Không trong delegating proxy path ấy. Phải test coverage hoặc đổi boundary/weaving, không sửa bằng atomic counter.

### Bài 11 — LongAdder dùng làm ID

Aspect gọi `adder.increment(); id=adder.sum()` để cấp unique ID dưới concurrent traffic. Có đúng không?

**Đáp án:** Không bảo đảm uniqueness/linearizable sequence. Dùng atomic increment-and-get hoặc ID allocator phù hợp.

### Bài 12 — Cache map

Hai threads cùng `containsKey` false rồi cùng load network, `put`. ConcurrentHashMap có bảo đảm chỉ một load không?

**Đáp án:** Không. Cần single-flight/compute policy đúng semantics, xử lý lỗi và bounded cache.

### Bài 13 — Shared data leak

Một aspect ghi `lastArgs` vào field để debug, chạy 1 triệu requests. Rủi ro?

**Đáp án:** Ghi đè giữa concurrent invocations, giữ reference tới dữ liệu nhạy cảm/large object và tạo race. Giữ snapshot tối thiểu hoặc dùng logging có sanitization và bounded buffering.

### Bài 14 — Log order

Log của request B xuất hiện giữa hai dòng của request A. Có chứng minh advice precedence sai không?

**Đáp án:** Không. Các invocations song song có thể xen kẽ. Phải dùng correlation ID và kiểm thứ tự **trong từng invocation**.

### Bài 15 — Lock monitor

Một caller dùng `synchronized(proxy)`, caller khác dùng `synchronized(target)` với JDK delegating proxy. Có dùng cùng lock không?

**Đáp án:** Không nếu là hai objects khác nhau. Synchronization boundary phải rõ.

## 21. Checklist review một aspect production

1. **Ownership:** Aspect instance dùng chung ở scope nào: module, target, proxy, thread, invocation?
2. **State classification:** Field nào immutable, shared mutable, per-target, per-call hoặc per-task?
3. **Happens-before:** Dữ liệu publish giữa threads được bảo đảm visibility thế nào?
4. **Atomicity:** Counters/CAS updates có đúng yêu cầu không?
5. **Multi-field invariants:** Có cần lock/state machine/consistent snapshot không?
6. **Metric semantics:** Đếm logical calls, attempts, target executions hay async tasks?
7. **Cleanup:** Có decrement/restore/close trên normal return, exception và cancellation?
8. **ThreadLocal:** Có restore previous value, remove ở outer scope và không leak thread pools?
9. **Async:** Return-handle khác task completion; context propagation và stage ownership thế nào?
10. **Reentrancy:** Advice có thể tự chọn lại chính nó qua logging/exporter/callback không?
11. **Locks:** Lock ordering, contention, deadlock, không giữ lock qua blocking proceed?
12. **Cache:** Key đầy đủ/đúng security scope, bounded eviction, thundering herd policy?
13. **Memory:** Aspect có giữ target/args/Throwable/future references quá lâu không?
14. **Proxy coverage:** Caller có bypass proxy bằng direct target hoặc self-invocation không?
15. **Weaving coverage:** Classes/join points thực sự được weave và có nhiều transformer xung đột không?
16. **Error transparency:** Original exception/result có được bảo toàn theo contract?
17. **Return types:** Primitive/null/Optional/async stage không bị thay ngoài ý định?
18. **Target thread safety:** Target có an toàn độc lập với aspect không?
19. **Load tests:** Có kiểm overlap bằng latch/barrier và benchmark p99, contention, memory?
20. **Bounded tests:** Barriers/Futures có timeout trong CI để tránh treo?
21. **Lifecycle:** Close/shutdown khi còn active calls, metrics flush và registration cleanup?
22. **Privacy:** Log/context có bị trộn user hoặc lộ dữ liệu khi chạy song song?
23. **Integration:** Kiểm thử với đúng engine/runtime/config/classloader, không suy từ JDK proxy demo?
24. **Rollback:** Có thể tắt/rollback aspect an toàn nếu phát hiện regression đồng thời?

## Kết luận

Thiết kế aspect an toàn khi chạy song song bắt đầu bằng việc **đặt state đúng scope**. Giữ dữ liệu của từng invocation trong local/context riêng, chia sẻ cấu hình bất biến qua safe publication, dùng atomic/concurrent primitives cho aggregate state và dùng synchronization đúng mức cho bất biến nhiều bước. Đặc biệt, **per-target không có nghĩa per-thread**, `volatile` không làm compound operations atomic, `LongAdder.sum()` không phải atomic snapshot lúc updates đang diễn ra, và `ThreadLocal` không tương đương request context trong executor.

Với around advice, cần bảo toàn **result/exception** và cleanup trong `finally`; với async, phải tách method return khỏi task completion; với proxy, phải xác minh call path để metrics/enforcement không bị bypass. Một aspect đáng tin là aspect vừa **thread-safe**, vừa giữ đúng **hợp đồng nghiệp vụ, performance, lifecycle, security và observability** khi nhiều invocations xảy ra đồng thời, được chứng minh bằng test có overlap thật chứ không dựa trên vận may scheduling.

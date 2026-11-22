# Chọn aspect không trạng thái hoặc có trạng thái trong vòng đời AOP

Khi thiết kế một **aspect** trong **Aspect-Oriented Programming (AOP – lập trình hướng khía cạnh)**, quyết định quan trọng không chỉ là **advice chạy ở join point nào**, mà còn là **aspect có giữ trạng thái giữa các lần advice được thực thi hay không**. Quyết định này ảnh hưởng trực tiếp tới phạm vi dùng chung, vòng đời đối tượng, tính an toàn đa luồng, khả năng mở rộng, kết quả kiểm thử và nguy cơ giữ dữ liệu quá lâu.

Quy tắc khởi đầu thường hữu ích: **ưu tiên aspect không trạng thái (stateless) cho những concern độc lập giữa các lời gọi**, và chỉ dùng **aspect có trạng thái (stateful)** khi có yêu cầu nghiệp vụ hoặc cơ chế rõ ràng phải nhớ thông tin giữa các sự kiện. Nếu cần trạng thái, phải xác định **trạng thái thuộc về ai, tồn tại trong bao lâu, được đồng bộ thế nào và được hủy khi nào**.

Đừng đồng nhất ba điều sau:

1. **Số instance của aspect** – dùng một instance chung, tạo theo target, theo đối tượng đang thực thi, theo luồng điều khiển hay theo một cơ chế khác.
2. **Tính có trạng thái của hành vi** – advice có giữ dữ liệu mutable sống qua nhiều lần gọi không?
3. **Vị trí thật của trạng thái** – field trong aspect, một service/cache bên ngoài, `ThreadLocal`, map keyed theo target hay biến cục bộ của một lần invocation.

Một aspect được cấu hình **chỉ có một instance** vẫn có thể hoàn toàn stateless. Ngược lại, một aspect chỉ có field `final` trỏ tới **đối tượng mutable dùng chung** vẫn có thể mang trạng thái gián tiếp. Vấn đề cốt lõi là **ngữ nghĩa dữ liệu và vòng đời**, không phải chỉ số lượng instance.

## 1. Nhắc lại: aspect, advice, join point và vòng đời

Trong AOP:

- **Aspect** là đơn vị tổ chức một concern cắt ngang, chẳng hạn tracing, validation, audit, retry hoặc cache.
- **Join point** là điểm chương trình mà mô hình AOP có thể can thiệp, ví dụ method call hoặc method execution khi được hỗ trợ.
- **Pointcut** xác định những join point phù hợp.
- **Advice** là đoạn hành vi chạy tại điểm được chọn: before, after, around hoặc biến thể khác tùy mô hình.
- **Weaving** kết hợp aspect/advice với chương trình bằng compiler, biến đổi binary, load-time hoặc một cơ chế trung gian phù hợp.
- **Aspect instance và lifecycle** mô tả khi nào đối tượng chứa advice/state được tạo, được gắn vào phạm vi nào, dùng chung với ai và khi nào kết thúc.

**Pointcut selection khác aspect instantiation.** Pointcut xác định nơi có thể chạy advice; cơ chế vòng đời xác định **instance nào** phục vụ lần thực thi ấy. Hai join point cùng match một pointcut có thể sử dụng cùng một instance hoặc hai instance khác nhau, tùy chính sách khởi tạo aspect.

Một hình dung đơn giản:

~~~text
Nhiều invocation cùng pointcut
          |
          v
   Chọn aspect instance
     /         |         \
    /          |          \
shared      per-target   per-flow
instance     instance    instance
    |           |           |
  advice      advice      advice
    |           |           |
  state?      state?      state?
~~~

Dấu hỏi là cố ý: **mỗi phạm vi instance đều có thể thiết kế theo hướng stateless hoặc stateful**, nếu mô hình cung cấp phạm vi đó. Không phải cứ per-target là bắt buộc có bộ đếm, hoặc cứ shared là bắt buộc có biến toàn cục.

## 2. Định nghĩa “không trạng thái” và “có trạng thái”

### 2.1 Aspect không trạng thái – stateless

Một advice stateless **không phụ thuộc vào dữ liệu mutable được nó giữ lại từ những invocation trước** để quyết định kết quả hiện tại. Nó có thể dùng:
- Tham số của invocation hiện tại.
- Chữ ký, target, ngữ cảnh join point hiện tại.
- Biến cục bộ trong advice.
- Giá trị cấu hình bất biến.
- Một dependency được sử dụng theo hợp đồng phù hợp, ví dụ clock hoặc emitter chỉ nhận sự kiện.

Giả mã:

~~~text
before each selected invocation:
    operation = safeOperationName(currentJoinPoint)
    recordEvent(operation, "START")
~~~

Không có bộ đếm hay `lastUser` tồn tại xuyên suốt các lần gọi. Các biến cục bộ được tạo lại cho mỗi invocation, nên không tự gây tranh chấp giữa hai thread chỉ vì cùng dùng một aspect instance.

**Lưu ý:** stateless **không nhất thiết là hàm thuần (pure function)**. Một advice có thể gửi log/metric (tác dụng phụ) mà bản thân không giữ trạng thái giữa các invocation. Việc service log ở bên ngoài có bộ đệm hoặc tài nguyên không làm biến cục bộ trong advice trở thành bộ đếm, nhưng dependency ấy vẫn có yêu cầu thread safety riêng.

### 2.2 Aspect có trạng thái – stateful

Một aspect có trạng thái lưu thông tin **vượt quá vòng đời của một invocation**, chẳng hạn:
- Số lần phương thức của một đối tượng đã được gọi.
- Một máy trạng thái nghiệp vụ tích lũy qua nhiều sự kiện.
- Token bucket/rate limit theo một chủ thể.
- Thời điểm lần cuối một tài nguyên được truy cập.
- Cache có vòng đời được quản lý.
- Số lần thất bại liên tiếp để quyết định circuit breaker.
- Trạng thái một phiên theo dõi hoặc một luồng điều khiển.

Ví dụ giả mã:

~~~text
state calls = 0

before each selected invocation:
    calls = calls + 1
    emit("calls", calls)
~~~

Đây là stateful vì kết quả invocation thứ hai phụ thuộc **lịch sử** của invocation thứ nhất. Nhưng code này **chưa bảo đảm an toàn đa luồng**: tăng một số nguyên là thao tác read-modify-write; nếu nhiều thread dùng cùng instance, có thể mất lượt cập nhật.

### 2.3 Trạng thái cục bộ theo invocation không làm aspect tự thành stateful

~~~text
around invocation:
    start = monotonicTimeNow()
    try:
        return proceed()
    finally:
        duration = monotonicTimeNow() - start
        emitLatency(duration)
~~~

`start` và `duration` thuộc **mỗi lần gọi**, dù có nhiều invocation chạy song song trên một instance aspect. Chúng không phải field sống qua nhiều lần gọi. Một timing advice có thể stateless dù nó sử dụng các giá trị thay đổi trong thân advice.

Phải tách:
- **Ephemeral invocation state**: cục bộ, kết thúc theo invocation.
- **Persistent aspect state**: duy trì qua các invocation.
- **External shared state**: trạng thái nằm ở một thành phần khác nhưng advice truy cập được.

## 3. Vì sao mặc định stateless thường dễ đúng hơn?

Một aspect stateless có lợi thế:

1. **Ít chia sẻ mutable state:** giảm race condition, lost updates và nhu cầu khóa.
2. **Dễ tái sử dụng:** một instance có thể phục vụ nhiều target/invocation nếu mô hình cho phép.
3. **Dễ kiểm thử:** kết quả ít phụ thuộc thứ tự chạy các test trước.
4. **Dễ mở rộng:** không cần đồng bộ hoặc chuyển trạng thái tích lũy giữa nhiều aspect instances.
5. **Vòng đời đơn giản:** không có state của user/session phải dọn khi target mất tham chiếu.
6. **Giảm rủi ro lộ dữ liệu:** không giữ tham số, token hoặc object liên quan cá nhân lâu hơn cần thiết.
7. **Ít ảnh hưởng đến reentrancy:** lời gọi advice lồng nhau không đè lên một field như `currentRequest`.
8. **Rõ ràng hơn khi retry:** mỗi invocation tạo local context riêng thay vì dùng một biến đếm/mốc thời gian toàn cục khó phân biệt.

Ví dụ concern thường hợp với stateless:
- Validation dựa trên dữ liệu invocation hiện tại.
- Ghi log an toàn bằng schema cố định.
- Đo thời gian bằng biến cục bộ `start`.
- Ghi một sự kiện audit độc lập vào kênh đã định nghĩa.
- Chuẩn hóa dữ liệu đầu vào theo một hàm không phụ thuộc lịch sử.
- Kiểm tra quyền **dựa trên danh tính đáng tin và policy hiện hành** thông qua một dịch vụ rõ ràng, thay vì ghi `lastAuthorizedUser` vào aspect.

**Ngoại lệ:** Một bộ ghi metrics bên ngoài vẫn có state để tổng hợp số liệu. Điều đó không bắt buộc logic advice giữ state riêng. Ta có thể để hệ thống metrics chuyên dụng quản lý aggregation, đồng bộ và retention.

## 4. Khi nào stateful là hợp lý?

Dùng aspect stateful khi **hợp đồng thực sự yêu cầu nhớ quá khứ** và có thể định nghĩa phạm vi phù hợp.

| Yêu cầu | Trạng thái cần thiết | Phạm vi gợi ý | Điều kiện thiết kế |
| --- | --- | --- | --- |
| Đếm lượt của mỗi target | Counter theo object | Per-target hoặc registry keyed theo target | Xác định identity, đồng thời và cleanup |
| Circuit breaker | Số lỗi, trạng thái CLOSED/OPEN/HALF_OPEN, mốc thời gian | Theo dependency/endpoint được bảo vệ | Đồng bộ chuyển trạng thái, giới hạn retry |
| Rate limiting | Token/đếm trong cửa sổ | Theo principal/tenant/resource tùy hợp đồng | Không dùng một counter chung sai phạm vi |
| Cache | Key → value và TTL | Phạm vi dữ liệu phù hợp | Quyền, consistency, eviction, đồng thời |
| Máy trạng thái workflow | Pha xử lý giữa nhiều sự kiện | Theo workflow/session/correlation | Vòng đời, timeout, thứ tự sự kiện |
| Dedup/idempotency | Key yêu cầu → trạng thái/kết quả | Theo operation/domain có bảo đảm | Chống race và trạng thái đang xử lý |
| Chống lặp lại hành vi | Dấu đã kiểm tra/lần xử lý trước | Theo object hoặc request logic | Tránh biến state thành quyền truy cập |
| Theo dõi thời gian trong một nested flow | Context theo flow | Per-control-flow hoặc context tường minh | Hỗ trợ nested, async propagation, cleanup |

**Phạm vi phải được chọn từ ý nghĩa của dữ liệu.** Ví dụ rate limit theo người dùng không thể dùng chung một counter cho tất cả người dùng rồi cho rằng “đã bảo vệ từng người”. Ngược lại, circuit breaker của một backend dùng chung nhiều caller có thể cần state **chia sẻ theo dependency**, không phải một bộ breaker riêng bị vô hiệu tác dụng cho từng caller.

## 5. Các mô hình vòng đời aspect thường gặp

AOP tổng quát có nhiều phương án; các tên/cú pháp kích hoạt chỉ có ở hệ thống hỗ trợ chúng.

### 5.1 Shared/single instance

Một instance phục vụ nhiều join point hoặc nhiều target:

~~~text
Target A ----              -> Shared aspect instance
Target B ----/
Target C ----/
~~~

- **Stateless + shared**: thường phù hợp log, validation, tracing thuần ngữ cảnh.
- **Stateful + shared**: hợp lý khi cố ý cần bộ đếm toàn cục, circuit breaker theo endpoint hoặc registry chia sẻ; nhưng phải thread-safe và phân vùng đúng dữ liệu.
- **Rủi ro:** field `currentUser`, `lastTarget`, `startTime` trong instance dùng chung rất dễ bị ghi đè bởi invocation khác.

Nếu dùng một instance chung cho audit, không nên có field lưu `mostRecentPassword` hay payload của user gần nhất. Ngoài nguy cơ rò dữ liệu, đây còn là thiết kế khó đồng bộ.

### 5.2 Per-target instance

Một aspect instance được gắn với **target object** có thể phục vụ nhiều invocation trên target đó:

~~~text
Target A ---> Aspect A [callsA, lastSuccessA]
Target B ---> Aspect B [callsB, lastSuccessB]
~~~

Phù hợp khi dữ liệu mô tả **lịch sử của từng target**. Lưu ý:
- Một target có thể được gọi đồng thời bởi nhiều thread. Per-target **không phải** per-thread.
- Cần xác định thế nào là "cùng target": identity hay logical ID?
- Nếu registry giữ key target quá lâu, target sẽ không được garbage collect.
- Nếu có nhiều proxy trỏ cùng target, phải quyết định dùng **một state chung** hay state riêng theo từng proxy.
- Khi target bị thay hoặc reload, state cũ có cần di chuyển hay được bỏ?

### 5.3 Per-executing-object hoặc per-caller

Ở những mô hình AOP phân biệt **`this` của join point** với target, một aspect có thể được gắn theo object đang thực thi. Nhưng ở **method call join point**, `this` phía caller có thể khác target là object nhận lời gọi. Ở **method execution** của một phương thức instance, this thường chính là object đang chạy phần thân.

Không đồng nhất **per-this** với **per-target** nếu ngữ nghĩa join point không bảo đảm hai object là một.

### 5.4 Per-control-flow hoặc theo một luồng xử lý logic

Một số mô hình AOP hỗ trợ instance theo **dynamic control flow**, ví dụ một chuỗi lời gọi lồng nhau hoặc một hoạt động nghiệp vụ.

~~~text
Flow 1: entry -> a -> b -> exit    Aspect state F1
Flow 2: entry -> c -> d -> exit    Aspect state F2
~~~

Trạng thái kiểu này phù hợp cho correlation hoặc theo dõi pha, nhưng phải xử lý **nested flow** và **phát sinh task bất đồng bộ**. Một Java thread có thể phục vụ nhiều request liên tiếp, còn một request có thể chuyển qua nhiều thread. Do đó **per-thread không tự đồng nghĩa per-request hoặc per-flow**.

### 5.5 Per-invocation và trạng thái ngắn hạn

Nếu chỉ cần thời gian bắt đầu hoặc số lần retry **trong cùng một invocation**, đặt trạng thái ở **biến cục bộ/closure của around advice** thường đơn giản hơn tạo aspect instance mới cho từng lời gọi.

Ví dụ:

~~~text
around:
    attempts = 0
    while attempts < maxAttempts:
        attempts++
        try:
            return proceed()
        catch transientError:
            continue
~~~

Đây là **giả mã**, chỉ áp dụng khi nền tảng AOP cho phép continuation được gọi lại theo cách phù hợp. Retry nhiều lần có thể lặp side effects; phải xem idempotency. Biến `attempts` cục bộ thuộc vòng đời một invocation, không chứng minh aspect object là stateful.

## 6. Sai lầm: dùng field của shared aspect làm biến tạm

Mẫu dễ sai:

~~~java
class BadTimingAdvice {
    long startedAtNanos;

    Object around(Proceed next) throws Throwable {
        startedAtNanos = System.nanoTime();
        try {
            return next.call();
        } finally {
            long elapsed = System.nanoTime() - startedAtNanos;
            // Có thể dùng mốc của invocation khác.
        }
    }

    interface Proceed {
        Object call() throws Throwable;
    }
}
~~~

Đây là **mảnh minh họa lỗi thiết kế**, không có chương trình `main`. Nếu một instance được nhiều thread hoặc lời gọi lồng nhau dùng chung, invocation B có thể ghi đè `startedAtNanos` giữa hai bước của invocation A. Kết quả đo A sẽ sai dù `System.nanoTime()` hợp lệ.

Cách tốt hơn dùng biến cục bộ:

~~~java
class BetterTimingAdvice {
    Object around(Proceed next) throws Throwable {
        long startedAtNanos = System.nanoTime();
        try {
            return next.call();
        } finally {
            long elapsed = System.nanoTime() - startedAtNanos;
            // Ghi elapsed qua một API nhận số liệu an toàn.
        }
    }

    interface Proceed {
        Object call() throws Throwable;
    }
}
~~~

Trạng thái `startedAtNanos` được giữ trong **stack frame của mỗi lần gọi**. Lời gọi lồng nhau có stack frame riêng; hai thread cũng có biến cục bộ riêng. Không cần khóa để bảo vệ biến này.

**Không được biến lời khuyên này thành tuyệt đối:** nếu mục đích là đo một hoạt động **trải qua nhiều invocation** thì phải có một context sống đủ lâu hơn, nhưng context nên có phạm vi được đặt tên rõ ràng.

## 7. Java 17 chạy độc lập: stateless tracing và stateful per-target

Ví dụ sau có:
- Hai target nghiệp vụ `Worker A` và `Worker B`.
- Một `TraceAdvice` **không có field mutable**, dùng chung cho cả A và B.
- Hai `CounterAdvice` riêng, lần lượt gắn với A và B. Mỗi counter lưu số **attempts qua wrapper** của target tương ứng.
- Một wrapper nhận invocation, chạy trace, tăng counter rồi chuyển tiếp tới target.
- Nhánh lỗi chứng minh counter đếm **lượt thử**, dù target không trả về thành công.
- Lời gọi trực tiếp tới target chứng minh **state chỉ được cập nhật khi đi qua ranh giới đã lắp advice**.

Đây là Java thuần mô phỏng vòng đời aspect bằng wrapper; nó không tự là một ngôn ngữ khai báo pointcut hoặc bộ bytecode weaver. Nội dung quan trọng là **state thuộc phạm vi nào**.

Tạo file `AspectStateLifecycleDemo.java`:

~~~java
public class AspectStateLifecycleDemo {
    interface Task {
        String run(String request);
    }

    @FunctionalInterface
    interface Proceed {
        String call();
    }

    static final class Worker implements Task {
        private final String name;

        Worker(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        @Override
        public String run(String request) {
            System.out.println("BUSINESS " + name + " " + request);
            if ("error".equals(request)) {
                throw new IllegalStateException("boom:" + name);
            }
            return name + ":" + request;
        }
    }

    // Một instance dùng chung. Không giữ state giữa các invocation.
    static final class TraceAdvice {
        String around(Worker target, Proceed next) {
            System.out.println("TRACE before " + target.name());
            try {
                String result = next.call();
                System.out.println("TRACE after " + target.name()
                        + " result=" + result);
                return result;
            } catch (RuntimeException error) {
                System.out.println("TRACE error " + target.name()
                        + " " + error.getClass().getSimpleName());
                throw error;
            }
        }
    }

    // Một instance trên mỗi target theo cách khởi tạo của demo.
    static final class CounterAdvice {
        private final String label;
        private int calls;

        CounterAdvice(String label) {
            this.label = label;
        }

        String around(Proceed next) {
            calls++;
            System.out.println("COUNTER " + label + " calls=" + calls);
            return next.call();
        }

        int calls() {
            return calls;
        }
    }

    static Task instrument(
            Worker target,
            CounterAdvice counter,
            TraceAdvice trace) {
        return request -> trace.around(
                target,
                () -> counter.around(() -> target.run(request)));
    }

    public static void main(String[] args) {
        Worker a = new Worker("A");
        Worker b = new Worker("B");
        TraceAdvice sharedTrace = new TraceAdvice();
        CounterAdvice aCounter = new CounterAdvice("A");
        CounterAdvice bCounter = new CounterAdvice("B");

        Task proxyA = instrument(a, aCounter, sharedTrace);
        Task proxyB = instrument(b, bCounter, sharedTrace);

        System.out.println("CASE first-A");
        System.out.println("RESULT " + proxyA.run("one"));

        System.out.println("CASE first-B");
        System.out.println("RESULT " + proxyB.run("two"));

        System.out.println("CASE second-A");
        System.out.println("RESULT " + proxyA.run("three"));

        System.out.println("STATE A=" + aCounter.calls()
                + " B=" + bCounter.calls());

        System.out.println("CASE failure-B");
        try {
            proxyB.run("error");
        } catch (IllegalStateException error) {
            System.out.println("CALLER " + error.getMessage());
        }

        System.out.println("STATE A=" + aCounter.calls()
                + " B=" + bCounter.calls());

        System.out.println("CASE direct-A");
        System.out.println("DIRECT " + a.run("bypass"));

        System.out.println("STATE A=" + aCounter.calls()
                + " B=" + bCounter.calls());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac AspectStateLifecycleDemo.java
java AspectStateLifecycleDemo
~~~

Stdout chính xác của ví dụ:

~~~text
CASE first-A
TRACE before A
COUNTER A calls=1
BUSINESS A one
TRACE after A result=A:one
RESULT A:one
CASE first-B
TRACE before B
COUNTER B calls=1
BUSINESS B two
TRACE after B result=B:two
RESULT B:two
CASE second-A
TRACE before A
COUNTER A calls=2
BUSINESS A three
TRACE after A result=A:three
RESULT A:three
STATE A=2 B=1
CASE failure-B
TRACE before B
COUNTER B calls=2
BUSINESS B error
TRACE error B IllegalStateException
CALLER boom:B
STATE A=2 B=2
CASE direct-A
BUSINESS A bypass
DIRECT A:bypass
STATE A=2 B=2
~~~

### 7.1 Chứng minh phần stateless

`TraceAdvice` không có instance field mutable. Phương thức `around` nhận **target** và **continuation** của invocation hiện tại, viết sự kiện before, chờ kết quả rồi viết after/error. Một instance `sharedTrace` được cả `proxyA` và `proxyB` dùng mà không cần giữ `currentTarget` hay `lastResult` vào field.

Số lần trace in ra nhiều dòng không biến object này thành stateful. Nó **đang thực hiện tác dụng phụ** với `System.out`, nhưng nội dung bản thân `TraceAdvice` không cần nhớ lịch sử invocation để hoạt động.

### 7.2 Chứng minh phần stateful

`CounterAdvice` có field `calls` thay đổi sau mỗi lần qua wrapper. Hai instance được tạo độc lập:
- `aCounter` chỉ dùng trong wrapper của A.
- `bCounter` chỉ dùng trong wrapper của B.

Sau ba lần gọi bình thường: `A=2`, `B=1`. Lần B ném lỗi vẫn tăng đếm thành `B=2`, bởi code tăng trước khi gọi nghiệp vụ. Đây là **đếm attempts**, không phải số lần **thành công**.

Nếu muốn đếm thành công, phải tăng **sau khi `next.call()` trả về bình thường**, và làm rõ cùng tên metric đếm điều gì.

### 7.3 Vì sao nhánh direct không tăng state?

`a.run("bypass")` gọi trực tiếp target; nó không đi qua `proxyA`, nên không chạy `TraceAdvice` hoặc `CounterAdvice`. Điều này phản ánh **giới hạn của mô hình wrapper**, không phải một thuộc tính của mọi weaving ở method execution.

Nếu chính sách bắt buộc audit **mọi lần** chạy nghiệp vụ, chỉ đặt counter trong một proxy có thể bị bypass là chưa đủ. Cần quản lý mọi đường gọi hoặc chọn cơ chế can thiệp khác phù hợp.

### 7.4 Quan trọng: per-target không tự thread-safe

`CounterAdvice` ở ví dụ dùng `int calls` vì phần demo là **đơn luồng** và output cần xác định. Nếu nhiều thread gọi `proxyA.run(...)` đồng thời, `calls++` có thể bị mất lượt.

Một cách sửa cho phép đếm concurrent attempts trong cùng JVM là dùng `AtomicInteger`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

final class ThreadSafeCounter {
    private final AtomicInteger calls = new AtomicInteger();

    int incrementAndGet() {
        return calls.incrementAndGet();
    }

    int calls() {
        return calls.get();
    }
}
~~~

Đây là **mảnh khai báo riêng** về counter, không phải phần của file demo. Nó giải quyết **cập nhật counter nguyên tử trên một instance trong JVM**, không tự tạo trạng thái phân tán nhất quán giữa nhiều tiến trình. Cũng không giải quyết tự động logic phức tạp gồm nhiều field phải cập nhật cùng lúc.

## 8. An toàn đa luồng: chọn đúng loại trạng thái và đồng bộ

### 8.1 Shared mutable state là nguồn race condition

Ví dụ tăng biến đếm bằng `calls++` gồm các bước đọc–cộng–ghi không nguyên tử theo nghĩa cần thiết cho counter concurrent. Nếu hai invocation cùng đọc giá trị 5, cả hai có thể ghi 6; một lượt bị mất.

Với state đơn giản, `AtomicInteger`, `AtomicLong` hoặc `LongAdder` có thể phù hợp tùy yêu cầu:
- **AtomicInteger/AtomicLong** hỗ trợ cập nhật nguyên tử và đọc giá trị có ngữ nghĩa rõ.
- **LongAdder** có thể giảm contention khi tăng nhiều, nhưng `sum()` dưới cạnh tranh không phải snapshot nguyên tử toàn bộ cập nhật; không dùng nó như một bộ phát số thứ tự chính xác.
- **ConcurrentHashMap** hữu ích cho registry concurrent, nhưng không tự biến mọi chuỗi nhiều thao tác trên nhiều phần tử thành transaction.

Nếu máy trạng thái có nhiều bước (ví dụ circuit breaker), cần giữ **bất biến toàn trạng thái**. Chỉ đổi từng field thành `volatile` không đảm bảo nhóm field cập nhật nguyên tử.

### 8.2 Per-target vẫn có thể bị nhiều thread chạm tới

Một target có thể là service dùng chung. Nếu 100 thread gọi cùng target, **một CounterAdvice gắn theo target** vẫn nhận 100 concurrent invocations. Vì vậy per-target là **phạm vi logic dữ liệu**, không phải một kỹ thuật đồng bộ.

### 8.3 `volatile` không thay phép tăng nguyên tử

`volatile int counter` cung cấp các bảo đảm visibility/ordering nhất định, nhưng `counter++` vẫn không thành thao tác read-modify-write nguyên tử. Chọn primitive đồng bộ theo **hợp đồng**: đếm chính xác, thống kê gần đúng, cập nhật nhiều biến hay throughput.

### 8.4 Trạng thái bất biến và snapshot

Nếu một aspect cần giữ cấu hình động, có thể dùng object `Policy` bất biến được thay bằng `AtomicReference<Policy>`. Mỗi invocation đọc một snapshot đầu vào nhất quán. Điều này thường an toàn và dễ kiểm thử hơn thay từng field cấu hình mutable.

Tuy nhiên, `AtomicReference` chỉ bảo vệ việc thay **tham chiếu policy**; nó không làm những object mutable mà policy trỏ tới tự trở thành bất biến.

## 9. Trạng thái theo thread, control flow và bất đồng bộ

### 9.1 Vì sao `ThreadLocal` hấp dẫn nhưng rủi ro?

`ThreadLocal<T>` cung cấp một giá trị riêng theo **Java thread**, không theo user hay request logic. Có thể dùng cho một số ngữ cảnh đồng bộ đã được quản lý; nhưng trong thread pool, thread được tái sử dụng cho nhiều request. Nếu quên dọn context, dữ liệu của request trước có thể còn tồn tại ở request sau.

Mẫu tối thiểu:

~~~java
static final ThreadLocal<String> TRACE =
        new ThreadLocal<>();

static void handle(String traceId, Runnable next) {
    String previous = TRACE.get();
    TRACE.set(traceId);
    try {
        next.run();
    } finally {
        if (previous == null) {
            TRACE.remove();
        } else {
            TRACE.set(previous);
        }
    }
}
~~~

Đây là mảnh minh họa có ý thức **khôi phục giá trị trước** cho nested calls. Nó không giải quyết tự động propagation sang thread khác; cũng không cho phép lưu token hoặc bí mật không cần thiết trong TRACE.

### 9.2 Async làm phạm vi flow phức tạp hơn

Một request có thể bắt đầu trên thread T1, chuyển sang executor trên T2, rồi tiếp tục trên T3. Một aspect dùng `ThreadLocal` trên T1 không thể mặc định T2 và T3 nhận cùng context.

Cách tiếp cận an toàn:
- Chỉ truyền **context tối thiểu** có mục đích rõ ràng.
- Dùng cấu trúc bất biến và cơ chế truyền context được hỗ trợ.
- Định nghĩa nơi bắt đầu/kết thúc hoạt động logic, cancellation và cleanup.
- Không giữ trực tiếp request/target lớn chỉ để lấy một correlation ID.
- Với nested hoặc recursive flows, dùng stack/scope thay vì một field `currentFlow` bị ghi đè.

### 9.3 Thread-per-request không phải định nghĩa AOP

Một hệ thống có thể dùng event loop, thread pool, virtual threads hoặc mô hình khác. Ngữ nghĩa **per-control-flow** trong AOP không nhất thiết đồng nghĩa **per-thread**; không chuyển đổi hai khái niệm chỉ vì code chạy đúng trong một demo đơn luồng.

## 10. Vòng đời, tham chiếu và nguy cơ rò bộ nhớ

Một aspect stateful có thể giữ tham chiếu tới target, principal hoặc kết quả trong registry:

~~~text
Shared aspect
    |
    v
Map<Target, State>
    |
    +--> Target A -> Counter A
    +--> Target B -> Counter B
    +--> Target C -> Counter C
~~~

Nếu map giữ **strong references** tới các target đã hết vòng đời, GC không thể thu hồi chúng cho đến khi entry được xóa. Đây là một nguy cơ **memory leak** đặc biệt khi target được tạo nhiều hoặc có dữ liệu lớn.

Một số giải pháp tùy tình huống:
- Gắn state trong object sở hữu có lifecycle rõ.
- Xóa entry khi target được release/dispose.
- Dùng registry có eviction/TTL nếu dữ liệu được phép hết hạn.
- Cân nhắc weak-key association nếu semantics cho phép, nhưng hiểu cách weak reference, equality và vòng đời hoạt động.
- Không dùng `WeakHashMap` rồi mặc định an toàn nếu **value giữ tham chiếu mạnh trở lại key**, khiến key vẫn không thể được thu hồi.
- Đặt giới hạn kích thước và cơ chế dọn dẹp có thể quan sát.

### 10.1 Tránh nhầm identity với logical key

Nếu hai object `CustomerAccount` đại diện cùng một logical account, aspect stateful per-instance sẽ có **hai state khác nhau**. Nếu yêu cầu là rate limit hoặc breaker theo **account ID**, gắn state theo object identity có thể là phạm vi sai.

Ngược lại, hai target objects bằng nhau theo `equals` không nhất thiết là cùng một đối tượng có vòng đời. `HashMap` dùng equals/hashCode; `IdentityHashMap` dùng identity. Lựa chọn phải theo **ngữ nghĩa nghiệp vụ** và quy tắc lifecycle, không theo thói quen dùng loại Map quen thuộc.

### 10.2 Khi nào phải xóa state?

Đặt câu hỏi ngay lúc thiết kế:
- Sau một invocation?
- Sau khi target bị hủy?
- Sau khi workflow hoàn tất?
- Khi session hết hạn?
- Khi tenant/logout/permission thay đổi?
- Sau một khoảng TTL?
- Khi phiên bản aspect mới được triển khai?

Nếu không thể mô tả **thời điểm kết thúc**, nguy cơ state tồn tại lâu hơn hợp đồng là rất lớn.

## 11. Tác động của precedence, short-circuit và retry lên state

Một aspect stateful chỉ quan sát những sự kiện **đi tới nó**.

Ví dụ:

~~~text
Cache(Counter(Target))
~~~

Nếu Cache ở ngoài và có cache hit mà không gọi continuation, Counter bên trong **không tăng**. Nếu mục đích là đếm **mọi yêu cầu**, cấu trúc này sai phạm vi.

~~~text
Counter(Cache(Target))
~~~

Ở cấu trúc thứ hai, Counter ở ngoài nhìn thấy cả cache hit, giả sử mọi caller đều đi qua outer wrapper.

**Không có bộ đếm nào “đúng” tự thân**: cần định nghĩa đang đếm requests, attempts, method executions, successes, failures hay cache misses.

### 11.1 Retry làm số lượng lần thực thi khác số yêu cầu

~~~text
Retry(Counter(Target))
Counter(Retry(Target))
~~~

Nếu Retry gọi continuation nhiều lần, Counter nằm trong có thể tăng theo mỗi attempt; Counter ở ngoài chỉ tăng một lần cho toàn lời gọi logic. Nhưng ngữ nghĩa chính xác còn tùy một cơ chế AOP có cho gọi lại `proceed` và ranh giới transaction/exception như thế nào.

### 11.2 Counter trước hay sau `proceed`?

~~~text
before proceed: attempts++
after successful proceed: successes++
on exception: failures++
finally: completedInvocations++
~~~

Đây là **giả mã**. Nếu một outer advice short-circuit, counter bên trong không được vào; nếu một inner advice short-circuit thành công, counter ngoài có thể vẫn coi đó là success. Cần đặt tên metric theo **phạm vi quan sát**.

### 11.3 State của security advice

Không lưu `lastAuthorizedUser` hoặc một boolean `authorized=true` dùng chung để quyết định lời gọi tiếp theo. Quyền thường phụ thuộc **chủ thể đã xác thực, tài nguyên, hành động và thời điểm**. Nếu dùng cache kết quả phân quyền, cần khóa đầy đủ, timeout/revocation phù hợp và cơ chế chống nhầm người dùng/tenant. Một stateful security aspect thiết kế sai có thể trở thành lỗ hổng nghiêm trọng.

## 12. State có thể nằm ngoài aspect

Một cách thiết kế khác:

~~~text
Stateless advice
      |
      +--> metrics recorder (thread-safe)
      |
      +--> rate limit store (theo key được duyệt)
      |
      +--> correlation provider (context tối thiểu)
~~~

Advice không giữ state theo user/target dưới dạng field mutable. Nó **ủy quyền việc quản lý state** cho thành phần chuyên trách có hợp đồng: API thread-safe, TTL, key scope, concurrency, đo đạc và cleanup.

Cách này thường tốt cho state chia sẻ nhiều instance hoặc nhiều process. Nhưng nói "aspect stateless" **không loại bỏ** yêu cầu kiểm thử độ nhất quán, tính sẵn sàng và bảo mật của store bên ngoài.

### 12.1 Trạng thái trong nhiều JVM

Một `AtomicInteger` trong một JVM chỉ đếm các lời gọi đi qua đúng instance đó. Nếu triển khai bốn process, có thể có bốn counter độc lập. Nếu yêu cầu nghiệp vụ là giới hạn **toàn hệ thống**, phải dùng một giải pháp đồng bộ/distributed store phù hợp, với quy tắc consistency và thất bại được định nghĩa.

Không cố thay điều này bằng biến `static` vì biến static cũng chỉ sống trong phạm vi class loader/JVM liên quan; nó không tự chia sẻ giữa máy hoặc tiến trình.

### 12.2 Cache không phải cứ có state là xấu

Cache stateful có thể tăng hiệu năng đáng kể nếu dữ liệu **được phép tái sử dụng**. Điều kiện tiên quyết gồm:
- Khóa cache đầy đủ theo args, tenant, quyền, version và môi trường khi cần.
- Chính sách TTL/invalidation.
- Chống cache stampede khi nhiều miss đồng thời.
- Không trả dữ liệu stale nếu hợp đồng đòi consistency chặt.
- Giới hạn bộ nhớ/eviction.
- Không bỏ qua một advice authorization nằm bên trong khi cache hit.

Stateful là một **công cụ**, không phải lỗi mặc định. Lỗi là dùng state sai phạm vi hoặc thiếu cơ chế quản lý.

## 13. Vòng đời aspect khi thay đổi cấu hình hoặc phiên bản

Với aspect stateless, thay định nghĩa advice thường tập trung vào **tập join point, precedence và hành vi mới**. Với aspect stateful, còn cần xác định:

1. Instance cũ có tiếp tục sống sau khi deploy/reload hay không?
2. Trạng thái cũ có tương thích kiểu và ý nghĩa với aspect mới không?
3. Counter/cache/policy cần reset, migrate hay giữ nguyên?
4. Những active invocations đang dùng state nào?
5. Class loader cũ có thể bị giữ sống bởi aspect registry hoặc ThreadLocal không?
6. Bảo mật có đòi xóa state gắn với user/session ngay khi logout hoặc revoke không?
7. Có giai đoạn triển khai hai phiên bản aspect đồng thời không?

Không nên mặc định sửa source aspect trong repository là JVM đã cập nhật state. Compile-time/post-compile weaving thường tạo artifact mới; load-time weaving thường áp dụng tại thời điểm class được nạp; runtime proxy có thể đọc config động nếu được thiết kế vậy. **Cập nhật code và chuyển đổi state** là hai bài toán riêng.

## 14. Bảng lựa chọn thực tế

| Tình huống | Phương án nên ưu tiên | Lý do | Kiểm tra thêm |
| --- | --- | --- | --- |
| Ghi log bắt đầu/kết thúc mỗi call | Stateless advice | Không cần nhớ lịch sử | Không log dữ liệu nhạy cảm |
| Đo latency mỗi invocation | Stateless với biến local | Mốc thời gian thuộc từng call | Exception/finally, monotonic clock |
| Đếm attempts theo target | Stateful per-target | Lịch sử gắn target | Thread safety, identity, cleanup |
| Đếm tổng requests theo ứng dụng | Stateless advice + metrics backend, hoặc shared counter có kiểm soát | Aggregation có scope riêng | Multi-JVM, request vs attempt |
| Circuit breaker theo dependency | Stateful theo dependency | Cần trạng thái xuyên nhiều call | Atomic transitions, timeout, half-open |
| Tương quan một request async | Context tường minh/per-logical-flow | Thread có thể thay đổi | Context propagation và cleanup |
| Authorization từng invocation | Stateless kiểm tra policy hiện tại | Tránh nhầm trạng thái user | Trusted identity, tất cả đường vào |
| Cache kết quả đọc | Stateful cache chuyên trách | Cần lưu giá trị giữa call | Key scope, TTL, security, memory |
| Retry limit trong một around invocation | Biến local `attempts` | State chỉ sống trong một call | Side effects, idempotency |
| Giới hạn toàn cụm theo tenant | Shared state store đúng domain | Một instance aspect không đủ | Distributed consistency và failure modes |
| Theo dõi một workflow phức tạp | Stateful theo workflow ID/lifecycle | Trạng thái qua nhiều sự kiện | TTL, persistence, transaction và replay |

### 14.1 Quy tắc quyết định theo thứ tự

**Câu 1:** Có cần nhớ kết quả từ lần gọi trước không? Nếu **không**, ưu tiên stateless.

**Câu 2:** Nếu có, state thuộc **một invocation, target, caller, flow, tenant, dependency hay toàn hệ thống**? Đặt scope theo câu trả lời này.

**Câu 3:** Có nhiều thread/process cùng truy cập không? Chọn đồng bộ và consistency theo hợp đồng.

**Câu 4:** State kết thúc khi nào? Thiết kế cleanup, TTL hoặc lifecycle event.

**Câu 5:** Nếu advice được bypass hoặc short-circuit, state có còn phản ánh đúng đơn vị đo không? Kiểm tra vị trí trong chuỗi.

**Câu 6:** State có thông tin nhạy cảm không? Tối thiểu hóa và bảo vệ quyền truy cập, retention và lưu trữ.

Nếu một trong các câu trên chưa có câu trả lời, việc thêm field vào aspect thường là giải pháp quá sớm.

## 15. Kiểm thử stateless và stateful

Một chiến lược kiểm thử cần phản ánh đúng **phạm vi state**, **thứ tự thực thi** và **bộ dệt/proxy** đang được dùng.

| Phép thử | Stateless | Stateful |
| --- | --- | --- |
| Hai invocation liên tiếp | Không bị ảnh hưởng do state riêng từ invocation trước | Kết quả/counter biến đổi đúng theo lịch sử |
| Hai target độc lập | Không vô tình giữ dữ liệu target cũ | Trạng thái phải tách hay chia theo thiết kế |
| Đồng thời trên một target | Không dùng chung field tạm | Không lost updates/race, giữ invariant |
| Invocation lồng nhau | Local state của frame riêng | Không bị ghi đè state flow ngoài |
| Exception trước/sau `proceed` | Cleanup/log error đúng | Counter success/failure đúng đơn vị |
| Cache hit/short-circuit ngoài | Biết advice nào không được vào | Counters không bị hiểu nhầm là requests |
| Retry nhiều attempt | Local attempt count đúng | State shared không tăng ngoài ý định |
| Direct-call bypass proxy | Biết giới hạn coverage | State chỉ tính những call được instrument |
| Garbage collection/cleanup | Không giữ object không cần | Registry, ThreadLocal, cache được giải phóng |
| Redeploy/reload | Advice mới chạy đúng phiên bản | State reset/migrate theo policy |
| Nhiều JVM | Advice hoạt động ở từng process | State phân tán có quy tắc rõ |
| Sensitive args | Không ghi raw dữ liệu | Không lưu secret qua vòng đời dài |

### 15.1 Đảm bảo số lần đúng hơn dòng log

Nếu đang kiểm tra counter, assert chính **giá trị counter**, không chỉ đọc stdout. Log có thể bị sampling hoặc mất ở exporter. Với async/concurrent, kết quả xuất dòng có thể xen kẽ; nên kiểm tra bất biến cuối hoặc event ID/correlation thay vì dựa vào thứ tự print của nhiều thread.

### 15.2 Dùng test độc lập để tránh order dependence

Một test stateful có thể pass khi chạy riêng, nhưng fail khi chạy sau test khác nếu aspect instance dùng chung chưa reset state. Hãy:
- Tạo instance state mới cho mỗi test khi hợp đồng cho phép.
- Có cơ chế reset/cleanup rõ cho shared state.
- Kiểm tra cả một chuỗi nhiều test để phát hiện state leak.
- Không sửa test cho phụ thuộc vào thứ tự chạy của framework test runner.

## 16. Những sai lầm phổ biến

1. **“Singleton aspect là stateful.”** Sai: số instance và có state là hai thuộc tính khác nhau.
2. **“Aspect chỉ có field `final` chắc chắn stateless.”** Sai nếu field trỏ vào object mutable chứa state.
3. **“Biến local làm aspect stateful.”** Không nếu biến thuộc riêng từng invocation và không sống qua call.
4. **“Per-target thì không có race.”** Sai: một target thường được gọi đồng thời.
5. **“Dùng `volatile` là tăng counter an toàn.”** `counter++` vẫn không nguyên tử.
6. **“`ThreadLocal` đồng nghĩa per-request.”** Sai khi dùng thread pool hoặc async.
7. **“State của target chính là state của aspect.”** Hai loại state có thể liên quan nhưng khác nơi sở hữu và vòng đời.
8. **“Đếm sau `proceed` là đếm mọi lời gọi.”** Nó có thể chỉ đếm successes.
9. **“Đếm trước `proceed` là đếm mọi request từ người dùng.”** Chỉ đếm những call thực sự đi tới advice.
10. **“Một shared counter phản ánh tổng toàn cụm.”** Sai khi có nhiều JVM/instance.
11. **“Dùng map keyed theo target không cần cleanup.”** Có thể giữ strong references khiến target không được GC.
12. **“Weak key tự động giải quyết mọi leak.”** Value có thể tham chiếu lại key hoặc dữ liệu còn bị giữ ở nơi khác.
13. **“Cache hit bên ngoài không ảnh hưởng state của advice bên trong.”** Nó có thể skip phần bên trong hoàn toàn.
14. **“Stateful luôn tốt hơn vì có thêm thông tin.”** Càng nhiều state càng có chi phí đồng bộ, retention, memory và bảo mật.
15. **“Stateless nghĩa là không có side effect.”** Một advice stateless vẫn có thể ghi log và gửi metric.
16. **“Thay aspect code là state cũ tự chuyển.”** State migration/reset là vấn đề riêng khi đổi phiên bản.

## 17. Câu hỏi ôn tập

**Câu 1.** Một aspect có một instance dùng chung và một phương thức before chỉ in tên thao tác từ invocation hiện tại. Nó stateless hay stateful?

**Đáp:** stateless, nếu không giữ giá trị mutable của invocation này để dùng cho lần sau. Việc dùng chung một instance không biến nó thành stateful.

**Câu 2.** Một around advice có biến cục bộ `long startedAt` để đo thời gian; có cần tạo aspect per-invocation không?

**Đáp:** không nhất thiết. Biến cục bộ đã phân biệt từng invocation; một aspect instance có thể xử lý nhiều lời gọi khi các dependency của nó an toàn.

**Câu 3.** Một aspect per-target giữ `int calls`; 10 thread cùng gọi target. Số đếm có chắc chính xác không?

**Đáp:** không nếu tăng bằng `calls++` không đồng bộ. Per-target là phạm vi lưu state, không cung cấp thread safety.

**Câu 4.** Một aspect lưu `lastAuthorizedUser` để kiểm soát quyền cho lần gọi kế tiếp. Vấn đề gì?

**Đáp:** dữ liệu của chủ thể này có thể bị dùng nhầm cho chủ thể khác, gây vi phạm bảo mật. Kiểm tra quyền phải dựa vào identity đáng tin và tài nguyên của chính invocation hiện tại; nếu cache quyền, cần scope và invalidation rõ.

**Câu 5.** `Counter(Cache(Target))` và `Cache(Counter(Target))` đếm cùng một số lần khi có cache hit?

**Đáp:** không nhất thiết. Khi Cache ở ngoài và trả hit, Counter bên trong không chạy.

**Câu 6.** Dùng `ThreadLocal` trong aspect per-thread có bảo đảm trạng thái đi theo một workflow bất đồng bộ qua thread pool không?

**Đáp:** không. Phải truyền context phù hợp một cách tường minh hoặc dùng cơ chế propagation được hỗ trợ, đồng thời cleanup khi hoàn tất.

**Câu 7.** Một registry `Map<Target, State>` giữ state của object đã hết sử dụng có thể gây gì?

**Đáp:** giữ strong reference làm object không được GC, gây memory leak. Cần lifecycle/eviction/disposal hoặc weak association được thiết kế đúng.

**Câu 8.** Khi chạy nhiều JVM, `AtomicInteger` trong một shared aspect có phản ánh tổng số requests toàn hệ thống không?

**Đáp:** không. Nó chỉ phản ánh phạm vi instance/process liên quan. Nếu cần tổng toàn cụm phải có cơ chế aggregation hoặc state chia sẻ được kiểm soát.

## 18. Tài liệu tham khảo

- [Java SE 17 – AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): bộ đếm nguyên tử trên một instance.
- [Java SE 17 – ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): trạng thái theo thread và phương thức `remove()`.
- [Java SE 17 – WeakHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys và lưu ý value tham chiếu key.
- [Java SE 17 – AtomicReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): thay một cấu hình bất biến theo snapshot.
- [Java SE 17 – ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): bản đồ concurrent và thao tác phối hợp.
- [AspectJ Programming Guide – Aspect Instantiation](https://eclipse.dev/aspectj/doc/released/progguide/semantics-aspects.html): ví dụ về các phạm vi instantiation aspect; cú pháp cụ thể của công cụ chỉ để tham khảo, không bắt buộc cho mô hình AOP tổng quát.

**Kết luận:** chọn **stateless** nếu advice chỉ cần ngữ cảnh của invocation hiện tại; chọn **stateful** khi cần ghi nhớ một lịch sử có ý nghĩa và quản lý được vòng đời. Sau đó xác định **scope thực tế** (shared/per-target/per-executing-object/per-flow/ngoài aspect), **thread safety**, **retention/cleanup**, **coverage của advice** và **ý nghĩa số liệu**. Câu hỏi đúng không phải “aspect có field hay không?”, mà là **“ai sở hữu state, ai có thể thay đổi nó, nó được dùng cho những lần gọi nào và khi nào nó hết hiệu lực?”**

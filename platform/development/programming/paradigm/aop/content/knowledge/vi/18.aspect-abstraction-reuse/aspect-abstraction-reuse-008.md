# Đóng gói aspect theo một mối quan tâm có trách nhiệm rõ

## 1. Bài toán: aspect cũng có thể trở thành một khối quá tải

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, **aspect** là đơn vị đóng gói một **mối quan tâm cắt ngang (cross-cutting concern)**, thường được mô tả bằng **pointcut** chọn các **join point** và **advice** quyết định hành vi tại những điểm được chọn. AOP giúp loại bỏ phần code cắt ngang bị sao chép ở nhiều method nghiệp vụ, nhưng bản thân aspect vẫn cần có ranh giới thiết kế đúng.

Một lỗi kiến trúc phổ biến là tạo một `CommonAspect` hoặc `GlobalAspect` làm mọi việc:

```text
MegaAspect:
    - authorization
    - audit
    - logging
    - request tracing
    - timing metrics
    - retry and timeout
    - cache
    - transaction
    - exception translation
```

Các hành vi ấy thường **có chủ sở hữu chính sách, độ tin cậy và lý do thay đổi khác nhau**. Nếu audit cần thay schema mà phải sửa cùng code với retry, hoặc đổi timing metric khiến authorization test thất bại, aspect đang có cohesion thấp và coupling cao.

**Nguyên tắc cốt lõi:** *Một aspect nên thể hiện một trách nhiệm rõ, có hợp đồng quan sát hoặc can thiệp được mô tả ngắn gọn, có pointcut đúng phạm vi và có thể kiểm thử độc lập.*

Một cấu trúc có thể dễ hiểu hơn:

```text
AuthorizationAspect    -- Quyết định một operation được phép hay từ chối.
AuditAspect            -- Ghi sự kiện audit theo hợp đồng.
TimingAspect           -- Đo thời lượng và outcome.
RetryAspect            -- Điều khiển các attempt theo chính sách.
ErrorMappingAspect     -- Chuyển lỗi tại ranh giới abstraction.
```

Các aspect có thể cùng khớp một method, nhưng **không vì thế mà chúng là một concern duy nhất**.

> **Phạm vi:** Bài này trình bày AOP cơ bản và nâng cao nói chung. Cú pháp pointcut/advice, những loại join point được hỗ trợ, chính sách tạo aspect instance và weaving phụ thuộc từng engine. Ví dụ Java 17+ bên dưới dùng Java Dynamic Proxy làm một interceptor đơn giản để **minh họa tổ chức trách nhiệm**, không phải một ngôn ngữ AOP đầy đủ hoặc một cú pháp pointcut chuẩn cho mọi runtime.

## 2. SRP trong AOP là “một lý do thay đổi”, không phải “một advice”

Nguyên tắc trách nhiệm đơn nhất (**Single Responsibility Principle – SRP**) không quy định một aspect chỉ được có một method hay một advice. Tiêu chí thiết kế tốt hơn là **những thành phần của aspect có cùng lý do thay đổi chủ đạo không**.

Ví dụ một `AuditAspect` hoàn toàn có thể bao gồm:

- Pointcut chọn các thao tác cần ghi audit.
- Before advice tạo bản ghi bắt đầu.
- After-returning advice ghi outcome thành công.
- After-throwing advice ghi thất bại.
- Cơ chế tạo event theo một schema audit chung.
- Dependency `AuditRecorder` chịu trách nhiệm lưu event.

Tất cả phục vụ **một hợp đồng audit**. Một aspect có ba advice vẫn có thể rất đúng SRP.

Ngược lại, một aspect chỉ có một around advice nhưng bên trong lại kiểm quyền, thử lại network, cập nhật cache, commit transaction và ghi audit có thể **vi phạm SRP nặng**, dù mã chỉ có một method.

### Một câu hỏi kiểm tra

Hãy hoàn thành câu:

> “Aspect này chịu trách nhiệm **[mục tiêu]** đối với **[tập join point]**, với hợp đồng **[outcome/failure policy]**.”

Nếu cần liệt kê nhiều mục tiêu không liên quan bằng “và nó còn...”, nên cân nhắc tách concerns.

## 3. Phân biệt “cross-cutting” và “one concern”

**Cross-cutting** chỉ nói rằng một behavior được sử dụng ở nhiều nơi trong cấu trúc phần mềm. Nó **không** có nghĩa mọi behavior xuất hiện ở nhiều nơi đều thuộc cùng một aspect.

| Concern | Mục đích | Ràng buộc riêng |
| --- | --- | --- |
| **Logging** | Chẩn đoán kỹ thuật | Lọc mức độ, masking, volume |
| **Audit** | Bằng chứng hành động, chủ thể và kết quả | Retention, durability, access control |
| **Tracing** | Quan hệ các operation | Trace/span IDs, context propagation |
| **Timing/metrics** | Đo lượng, độ trễ, tỉ lệ lỗi | Counter, histogram, label cardinality |
| **Authorization** | Cho phép hoặc từ chối thao tác | Principal đã xác minh, tài nguyên, fail-closed |
| **Retry** | Kiểm soát các lần thử | Deadline, budget, idempotency |
| **Cache** | Dùng lại kết quả | Key, TTL, consistency, invalidation |
| **Transaction** | Ranh giới thay đổi nhất quán | Begin, commit, rollback |
| **Exception mapping** | Giữ abstraction contract | Type, cause, caller expectations |

### Logging và audit không đồng nghĩa

Logging có thể cho phép sampling, buffer hoặc best-effort delivery. Audit bắt buộc có thể cần lưu bền vững, giữ đúng identity và ghi cả hành động bị từ chối. Nếu gom hai concern chỉ vì “đều in sự kiện”, một lỗi mất log có thể vô tình làm mất bằng chứng audit hoặc một lỗi audit bắt buộc lại bị nuốt như log phụ trợ.

### Timing và tracing cũng không đồng nghĩa

Một trace span có duration, nhưng tracing còn có parent/links và propagation qua task boundaries; timing metric thường cần aggregate durations với labels có cardinality thấp. Chúng có thể chia sẻ một clock helper, nhưng policy ownership khác nhau.

### Validation, authorization và nghiệp vụ

Validation có thể kiểm tính hợp lệ của input; authorization kiểm quyền; nghiệp vụ quyết định một thao tác có hợp lệ theo domain rule. Nếu một aspect gom cả ba, dễ nhầm lỗi “sai dữ liệu” thành “không có quyền” hoặc chuyển nhầm trách nhiệm vốn cần nằm trong domain service.

## 4. Pointcut và advice cùng phục vụ một trách nhiệm

Một aspect thường gói:

```text
             Concern contract
                   |
          +--------+--------+
          |                 |
       Pointcut            Advice
     Chọn ở đâu?        Làm hành vi gì?
          |                 |
          +--------+--------+
                   |
                 Aspect
```

**Pointcut** phải chọn **đúng tập join point** cho concern. **Advice** chỉ xử lý behavior theo hợp đồng của concern.

Một aspect `TimingAspect` có thể match các method xử lý request; advice của nó tạo timestamp local, gọi tiếp target rồi ghi elapsed duration. Nó không cần quyết định request có được phép hay không hoặc có phải retry.

Một `AuditAspect` có thể chọn các thao tác tạo/sửa/xóa dữ liệu nhạy cảm; advice của nó tạo audit event đúng schema. Nó không cần đếm mọi method execution để đo performance.

### Một concern có thể dùng nhiều named pointcuts

```text
mutationOperation =
      createOperation
  OR  updateOperation
  OR  deleteOperation
```

Nếu tất cả cùng thuộc hợp đồng audit, chúng có thể tạo thành một audit pointcut tổng hợp. **Số lượng pointcuts không phải thước đo số trách nhiệm**.

## 5. Thiết kế từ lý do thay đổi thực tế

Hãy thử ba yêu cầu mới:

- “Thêm bộ lọc dữ liệu nhạy cảm cho audit event.”
- “Đổi histogram bucket và đơn vị latency.”
- “Điều chỉnh thời gian backoff khi dependency timeout.”

Nếu ba yêu cầu cùng phải sửa một `CrossCuttingAspect`, có khả năng aspect đó gộp policy không liên quan.

Khi tách:

```text
Audit change  -> AuditAspect / AuditRecorder / AuditPolicy
Metric change -> TimingAspect / MetricsRegistry
Retry change  -> RetryAspect / RetryPolicy
```

Mỗi concern có test và owner riêng. Các aspects **vẫn phải được test khi composition**, nhưng code của một policy không bắt buộc chứa logic của policy khác.

### Những lý do thay đổi khác nhau có thể cùng xảy ra

Một lần phát hành có thể yêu cầu vừa sửa audit vừa sửa metrics. Sự trùng thời điểm ấy **không chứng minh chúng là một trách nhiệm**. Hãy xem chúng có cần thay cùng nhau vì một hợp đồng duy nhất hay chỉ được yêu cầu trong một đợt triển khai.

## 6. Cohesion và coupling của aspect

**Cohesion cao**: pointcut, advice, state, event model và dependencies của aspect đều phục vụ một concern.

**Coupling thấp**: thay đổi nội bộ concern A không buộc hiểu/sửa implementation concern B.

Các dấu hiệu cohesion tốt:

- Advice có mục đích mô tả được.
- Những helper trực tiếp hỗ trợ một hợp đồng.
- Tên field phản ánh state đúng owner.
- Có thể thử behavior bằng fake dependencies.
- Exception và failure policy rõ.

Các dấu hiệu coupling xấu:

- Một around advice chứa nhiều `if (featureEnabled)` thuộc các lĩnh vực không liên quan.
- Shared field `currentRequestId` bị cả audit lẫn timing cùng ghi.
- Một helper vừa là logger vừa có retry policy vừa sửa exception.
- Có nhiều module owner thay cùng class một cách thường xuyên.
- Không test timer nếu thiếu database audit.

**Một aspect nhỏ vẫn có thể cohesion thấp; một aspect dài vẫn có thể cohesion cao** nếu tất cả dòng code cùng phục vụ một contract.

## 7. Tách aspect không có nghĩa xóa bỏ thứ tự tương tác

Giả sử trên một method áp dụng:

```text
Caller
  |
  AuthorizationAspect
    |
    AuditAspect
      |
      TimingAspect
        |
        Business Method
```

Đây chỉ là **một ví dụ precedence**, không phải quy tắc bắt buộc.

**Authorization ở ngoài Audit:** nếu authorization từ chối trước `proceed`, Audit ở trong có thể không thấy denied attempt.

**Audit ở ngoài Authorization:** có thể ghi nhận cả denied attempt, nếu audit contract yêu cầu.

**Retry ở ngoài Timing:** mỗi attempt có thể chạy một TimingAspect bên trong, metric đếm per-attempt.

**Timing ở ngoài Retry:** duration có thể bao gồm mọi attempts và backoff.

**Mapping ở trong Retry:** retry có thể thấy exception đã map thay vì lỗi dependency gốc.

**Transaction ở trong Retry:** mỗi attempt có thể mở transaction riêng. Đảo thứ tự có thể đổi semantics.

Vì vậy tách concerns làm rõ ownership, nhưng **ordering vẫn là một hợp đồng liên-aspect quan trọng**.

## 8. GodAspect không được sửa chỉ bằng cách tách thành private methods

Một đoạn giả mã:

```text
around everyMethod:
    checkPermission()
    readCache()
    startTimer()
    beginTransaction()
    retry(...)
    audit(...)
    updateCache()
    endTimer()
    translateException()
```

Nếu tách thành mười method private nhưng vẫn giữ **một aspect là chủ sở hữu mọi policy và state**, SRP chưa được cải thiện đáng kể.

Một refactor thiết kế tốt hơn:

1. Xác định từng concern và failure policy.
2. Xác định join points và những trường hợp cần bao phủ.
3. Tách advice và state theo concern.
4. Dùng interface cho dependency recording/config.
5. Cấu hình/ghi rõ precedence cần thiết.
6. Kiểm thử outcome, số target executions và side effects sau refactor.

Không chỉ nhìn source code sạch hơn; phải xem **runtime behavior vẫn đúng không**.

## 9. Một ví dụ Java 17+ chạy được: hai aspects, hai trách nhiệm

Dưới đây là một chương trình Java SE độc lập sử dụng **Java Dynamic Proxy** để mô phỏng việc composition các interceptor:

- **`AuditAspect`:** chỉ chọn `transfer` và ghi ba event: bắt đầu, thành công hoặc thất bại.
- **`TimingAspect`:** quan sát mọi lời gọi qua proxy, đo duration và tăng shared metrics.
- **`LedgerImpl`:** chỉ chứa logic nghiệp vụ, không biết hai aspect.
- **`Metrics`:** giữ counter tổng hợp thread-safe bằng `LongAdder`.
- Hai proxy được lồng **Audit bên ngoài, Timing bên trong**, nên cùng một `transfer` có cả audit và timing.

Nội dung audit trong demo **không in mã tham chiếu riêng tư**. Demo chỉ phục vụ mục tiêu học về responsibility và ordering, không triển khai một audit sink đáng tin cậy ở production.

### 9.1. Tệp `AspectResponsibilityDemo.java`

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.LongAdder;

public class AspectResponsibilityDemo {
    interface Ledger {
        String transfer(String privateReference, int units);
        int balance();
    }

    static final class LedgerImpl implements Ledger {
        @Override
        public String transfer(String privateReference, int units) {
            // Không in privateReference ra output.
            System.out.println("ledger.transfer");
            if (units <= 0) {
                throw new IllegalArgumentException(
                        "units must be positive");
            }
            return "receipt:" + units;
        }

        @Override
        public int balance() {
            System.out.println("ledger.balance");
            return 100;
        }
    }

    static final class Metrics {
        final LongAdder calls = new LongAdder();
        final LongAdder failures = new LongAdder();
        final LongAdder totalNanos = new LongAdder();
    }

    static Object invoke(
            Ledger target, Method method, Object[] arguments)
            throws Throwable {
        try {
            return method.invoke(target, arguments);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static Ledger proxy(
            Ledger target,
            java.lang.reflect.InvocationHandler handler) {
        return (Ledger) Proxy.newProxyInstance(
                Ledger.class.getClassLoader(),
                new Class<?>[]{Ledger.class},
                handler);
    }

    // Một trách nhiệm: đo thời gian và outcome.
    static final class TimingAspect {
        private final Metrics metrics;

        TimingAspect(Metrics metrics) {
            this.metrics = metrics;
        }

        Ledger wrap(Ledger target) {
            return proxy(target, (p, method, args) -> {
                String operation = method.getName();
                long started = System.nanoTime();
                System.out.println("timing.start " + operation);

                try {
                    Object result = invoke(target, method, args);
                    System.out.println("timing.success " + operation);
                    return result;
                } catch (Throwable original) {
                    metrics.failures.increment();
                    System.out.println(
                            "timing.failure " + operation + " "
                            + original.getClass().getSimpleName());
                    throw original;
                } finally {
                    metrics.calls.increment();
                    metrics.totalNanos.add(
                            System.nanoTime() - started);
                    System.out.println("timing.end " + operation);
                }
            });
        }
    }

    // Một trách nhiệm: audit thao tác được chọn.
    static final class AuditAspect {
        Ledger wrap(Ledger target) {
            return proxy(target, (p, method, args) -> {
                boolean auditable =
                        "transfer".equals(method.getName())
                        && method.getParameterCount() == 2;

                if (!auditable) {
                    return invoke(target, method, args);
                }

                System.out.println("audit.request transfer");
                try {
                    Object result = invoke(target, method, args);
                    System.out.println("audit.success transfer");
                    return result;
                } catch (Throwable original) {
                    System.out.println(
                            "audit.failure transfer "
                            + original.getClass().getSimpleName());
                    throw original;
                }
            });
        }
    }

    public static void main(String[] args) {
        Metrics metrics = new Metrics();
        Ledger business = new LedgerImpl();

        Ledger timed = new TimingAspect(metrics).wrap(business);
        Ledger observed = new AuditAspect().wrap(timed);

        System.out.println("== successful transfer ==");
        System.out.println("caller "
                + observed.transfer("private-reference", 5));

        System.out.println("== read balance ==");
        System.out.println("caller balance=" + observed.balance());

        System.out.println("== failed transfer ==");
        try {
            observed.transfer("private-reference", -2);
        } catch (IllegalArgumentException error) {
            System.out.println("caller error " + error.getMessage());
        }

        System.out.println("metrics calls=" + metrics.calls.sum()
                + " failures=" + metrics.failures.sum());
    }
}
```

### 9.2. Lệnh biên dịch/chạy

Dùng JDK 17+ và lưu đúng tên tệp `AspectResponsibilityDemo.java`:

```bash
javac --release 17 -encoding UTF-8 AspectResponsibilityDemo.java
java AspectResponsibilityDemo
```

**Standard output** (các giá trị nanoseconds thay đổi theo môi trường nên không được in trong ví dụ):

```text
== successful transfer ==
audit.request transfer
timing.start transfer
ledger.transfer
timing.success transfer
timing.end transfer
audit.success transfer
caller receipt:5
== read balance ==
timing.start balance
ledger.balance
timing.success balance
timing.end balance
caller balance=100
== failed transfer ==
audit.request transfer
timing.start transfer
ledger.transfer
timing.failure transfer IllegalArgumentException
timing.end transfer
audit.failure transfer IllegalArgumentException
caller error units must be positive
metrics calls=3 failures=1
```

### 9.3. Vì sao transfer được audit và timing?

`observed` là Audit proxy. Nó nhận `transfer`, selector trả true rồi ghi `audit.request`. Audit gọi `timed`, tức Timing proxy, nên Timing tạo local `started` và ghi `timing.start`. Target trả receipt, Timing ghi success/end trước, rồi Audit ghi success sau.

Từng component biết **đủ về trách nhiệm của mình**:

- Audit biết operation được chọn, không biết metrics histogram.
- Timing biết method bắt đầu/kết thúc, không lưu raw private reference.
- Target biết nghiệp vụ, không import aspect.
- Shared Metrics đếm aggregate, không giữ current request state.

### 9.4. Vì sao balance chỉ có timing?

`AuditAspect` chỉ chọn `transfer` hai parameters. `balance()` không khớp, nên proxy gọi tiếp target (vẫn là Timing proxy) **mà không phát audit event**. Timing tiếp tục chạy.

**Không match pointcut không có nghĩa bỏ qua target.** Interceptor vẫn phải gọi tiếp với đúng return/exception contract nếu không có chính sách cố ý chặn.

### 9.5. Khi target ném lỗi

`transfer` với `units=-2` ném `IllegalArgumentException`. Helper unwrap `InvocationTargetException` từ Reflection và ném lại cause gốc. Timing ghi failure và `finally`, Audit ghi failure rồi rethrow. Caller nhận message `units must be positive`.

**Một Throwable được hai aspects quan sát không phải hai business failures**. Metric shared chỉ tăng một failure cho một Timing invocation.

### 9.6. Vì sao dùng local timer và shared counter?

Mốc `started` thuộc **một lần advice invocation**, nên là local variable. Nếu dùng field `currentStart` trên singleton TimingAspect, hai calls concurrent hoặc nested có thể ghi đè nhau.

Bộ đếm `calls`/`failures` phục vụ **tổng số liệu**, nên có shared lifecycle và dùng `LongAdder` phù hợp. Lưu ý `LongAdder.sum()` không nhất thiết là atomic snapshot trong khi concurrent updates còn diễn ra; ở demo mọi lời gọi đã hoàn tất trước khi in.

### 9.7. Thứ tự composition là hợp đồng

`Audit outside Timing` tạo event:

```text
audit.request
  timing.start
    ledger.transfer
  timing.end
audit.success / audit.failure
```

Nếu đảo vị trí proxy, timing có thể đo cả overhead audit. Đừng kết luận hai aspects hoàn toàn độc lập về runtime ordering chỉ vì source code tách biệt.

### 9.8. Giới hạn của demo

- Java Dynamic Proxy chỉ intercept invocation qua interface proxy.
- Raw target call hoặc self-invocation của target có thể bypass wrapper.
- `matches` ở đây là một condition trong handler, không phải DSL pointcut/weaver.
- `System.out.println` không phải audit durable hoặc chuẩn compliance.
- Demo không triển khai auth, retry, transaction, async completion.
- Object methods (`toString`, `equals`, `hashCode`) trên proxy có thể cần cách xử lý riêng nếu dùng.
- Failure từ metric sink/audit recorder thật phải có policy; demo chỉ in stdout và tăng counter.
- Kết quả biên dịch/chạy kiểm chứng cách tổ chức và thứ tự **trong cơ chế này**, không đại diện mọi AOP runtime.

## 10. Những mối quan tâm cùng áp dụng một join point không phải cùng sở hữu nhau

Một API `transfer` có thể cần:

1. Authorization trước mutation.
2. Audit request/outcome.
3. Timing.
4. Transaction.
5. Retry một dependency bên trong nếu có.
6. Exception translation ở public boundary.

Tất cả liên quan đến thao tác `transfer`, nhưng mỗi concern có **đối tượng chịu trách nhiệm khác nhau**. Có thể có một **composition root** cấu hình chain, còn mỗi aspect chỉ sở hữu logic của mình.

### Một thứ tự minh họa

```text
API boundary
  -> AuthAspect
     -> AuditAspect
        -> TimingAspect
           -> TransactionAspect
              -> Target
```

Không thể khẳng định đây là thứ tự đúng cho mọi nghiệp vụ. Nếu Audit nằm trong Auth, denied attempt có thể không được ghi; nếu Audit ngoài Auth, nó có thể ghi cả denied attempts. Nếu transaction nằm ngoài timing, metric có thể bao gồm commit; nếu ở trong, duration khác.

**Thứ tự là một yêu cầu nghiệp vụ/vận hành**, không chỉ lựa chọn sắp xếp cho đẹp.

## 11. Phạm vi của aspect quyết định correctness

Một aspect nhỏ với pointcut sai vẫn nguy hiểm. Ví dụ `AuthorizationAspect` chỉ match method tên `delete` mà quên overload `delete(String,boolean)` có thể cho phép một đường bypass.

Xem các yếu tố:

- **Join point kind:** call hay execution?
- **Method signature:** tên, overload, return, parameter types.
- **Target type:** interface, implementation, subclass, bridge method.
- **Metadata:** annotation ở interface hay method implementation.
- **Argument binding:** null, subtype, primitive/boxing, varargs.
- **Dynamic control flow:** có cần giới hạn theo cflow hay request context không?
- **Interception coverage:** class/method được weave hay caller chỉ đi qua proxy?
- **Self-invocation:** method nội bộ gọi `this` có bypass không?
- **Async:** worker/callback execution được instrument ở boundary nào?
- **Runtime class loader/module:** có thuộc phạm vi weaving không?

**Pointcut là một phần hợp đồng của concern**, không phải một filter ngẫu nhiên.

### Security không được phụ thuộc một đường proxy có thể bypass

Nếu authorization là bắt buộc, cần đảm bảo mọi entry point không tin cậy đều được bảo vệ; chỉ có một proxy wrapper không chứng minh không ai có reference tới raw target. Defense-in-depth ở boundary tin cậy có thể cần thiết.

## 12. Một aspect có thể có nhiều hooks nhưng vẫn một trách nhiệm

Một `TraceContextAspect` có thể:

- Trên entry: lấy/gán trace context.
- Trước `proceed`: mở span.
- Khi target throw: gắn failure status.
- Trong `finally`: đóng scope/restore context.
- Với callback async: truyền context qua carrier có lifecycle rõ.

Dù có nhiều hooks, nó vẫn có một concern: **quản lý trace scope**. Cần phân biệt **giữa cùng concern gồm nhiều bước** với **trộn nhiều concerns độc lập**.

Tương tự, AuditAspect có thể chọn các operation tạo/cập nhật/xóa và dùng chung event schema. Việc có ba pointcuts không biến nó thành ba trách nhiệm nếu audit policy thống nhất.

## 13. Helper và dependency: tách implementation chi tiết nhưng giữ ownership

Một aspect không nên tự chứa mọi I/O. Có thể viết:

```text
AuditAspect
    |
    +--> AuditRecorder (interface)
            |
            +--> DurableRecorder
            +--> TestRecorder
```

AuditAspect quyết định **khi nào tạo event**. Recorder quyết định **cách ghi event** theo audit contract. Có thể mock/fake recorder trong unit tests.

Một TimingAspect có thể dùng `Clock` abstraction và `MetricRecorder`. Một RetryAspect dùng `RetryPolicy` và scheduler/backoff helper.

**Không biến shared helper thành GodService**: một helper vừa lưu audit, quyết định quyền và quản lý transaction sẽ tái tạo coupling dưới tên gọi khác.

### Shared mutable helper vẫn có thể sai

Hai aspects dù là hai class khác nhau nhưng cùng ghi vào một singleton helper có field `currentId` vẫn có nguy cơ race. SRP ở cấp class không tự sửa lỗi ownership/correlation sâu trong object graph.

## 14. State và vòng đời phải khớp trách nhiệm

| Dữ liệu | Owner đúng thường gặp | Không nên mặc định |
| --- | --- | --- |
| Thời điểm bắt đầu method | Invocation-local trong TimingAspect | Shared field `start` |
| Attempt count | Một operation retry | Singleton field `currentAttempt` |
| Trace ID | Request/task context đã truyền đúng | Aspect-global `currentTraceId` |
| Total calls | Shared metrics recorder | Local counter bị bỏ sau call |
| Audit policy | Immutable config snapshot | Mutable config bị sửa giữa lời gọi |
| Target metadata cache | Shared concurrency-safe cache có key phù hợp | Map không cleanup/không tính loader |
| Current Throwable | Advice invocation local | Shared field `lastError` |
| Audit write queue | Audit recorder có concurrency contract | Request object giữ mãi trên aspect |

### Reentrancy không cần nhiều thread

Nếu một advice gọi helper rồi helper tạo một join point cũng được instrument, advice có thể tái nhập ngay trên **cùng thread**. Một field `currentId` chung vẫn bị ghi đè. `volatile` hay `synchronized` đơn giản trên setter/getter không biến nó thành state per-invocation.

Giải pháp thường là **local variables**, invocation context hoặc scope stack đúng vòng đời, không là một slot shared.

## 15. Failure policy của mỗi concern phải độc lập

Điều gì xảy ra nếu concern tự thất bại?

**Timing metric sink lỗi:** nhiều hệ thống không muốn việc ghi metric phụ trợ làm fail business operation. Nhưng vẫn cần ghi nhận lỗi vận hành phù hợp, không nuốt mọi Throwable nghiêm trọng.

**Audit bắt buộc lỗi:** có thể cần fail-closed, hoặc cần event durable trước commit. Đây là hợp đồng compliance riêng.

**Authorization policy không tải được:** không nên tự “allow” vì một lỗi infrastructure.

**Retry lỗi:** phải phân biệt transient/permanent, deadline, cancel và idempotency; retry không tự là recovery an toàn.

**Exception translation:** chỉ mapping tại abstraction boundary, giữ `cause` và declared checked/unchecked contract.

Một catch block kiểu “catch mọi Exception rồi return null” trong aspect tổng hợp có thể phá các hợp đồng này cùng lúc.

## 16. `finally`, exception và return contract

Một advice quan sát nên mặc định **bảo toàn return value và Throwable của target**. Ví dụ timing:

```java
// Pseudocode around advice, không phải Java SE API chuẩn.
long start = System.nanoTime();
try {
    return proceed();
} finally {
    recordDuration(System.nanoTime() - start);
}
```

Nếu `recordDuration` tự throw, caller có thể thấy lỗi metric thay vì exception target. Policy của TimingAspect phải xử lý phù hợp.

Nếu AuditAspect lại yêu cầu ghi bền vững mới cho phép completion, policy xử lý lỗi audit khác timing là **một lý do mạnh để tách concerns**.

### After-throwing khác around

After-throwing advice có thể quan sát Throwable nhưng không nhất thiết được quyền biến failure thành return value. Around advice có thể kiểm soát `proceed`/return/throw nếu engine hỗ trợ. Chọn loại advice theo trách nhiệm, không kỳ vọng một hook quan sát có quyền đổi outcome vô hạn.

### Checked exception cần giữ contract

Một proxy/interface method có declared checked exceptions cụ thể. Nếu handler ném checked Throwable ngoài declared throws, Java Dynamic Proxy có thể bọc thành `UndeclaredThrowableException`. Aspect chỉ đo thời gian không nên tự wrap mọi exception rồi bất ngờ phá caller expectations.

## 17. Async boundaries cần được phân biệt theo trách nhiệm

Một method trả `CompletableFuture<T>` có thể return một future chưa hoàn tất. Nếu TimingAspect đo tới method return, nó đo **submission latency**, không nhất thiết **operation completion latency**.

```text
t0: method starts
t1: returns future
t2: future completes

submissionDuration = t1 - t0
completionDuration = t2 - t0
```

Một timing concern muốn đo end-to-end operation có thể cần callback/stage instrumentation và per-operation context.

AuditAspect có thể cần event khi operation thật sự commit, không khi future object được tạo. TracingAspect cần context propagation xuyên executor. AuthorizationAspect cần kiểm tại boundary thực hiện side effect nếu quyền có thể thay đổi.

**Các concern khác nhau có cách định nghĩa “operation kết thúc” khác nhau.** Không gộp chúng vào một after-returning advice rồi gọi mọi thứ là success.

## 18. Pointcut và behavior được tái sử dụng thế nào?

Một số mô hình tái sử dụng:

1. **Named pointcut composition:** ghép predicates để xác định scope.
2. **Abstract aspect/abstract pointcut:** định nghĩa advice chung, để concrete aspects chuyên biệt hóa pointcut nếu ngôn ngữ hỗ trợ.
3. **Selector strategy:** inject policy/selector vào interceptor.
4. **Recorder abstraction:** advice gọi interface, implementation thay đổi độc lập.
5. **Shared immutable config:** nhiều invocations đọc một snapshot đã validate.

### Tái sử dụng theo trách nhiệm, không theo cú pháp

Hai aspects có vài dòng `System.nanoTime()` giống nhau không bắt buộc phải kế thừa một GodAspect. Có thể chia sẻ clock abstraction hoặc utility nhỏ. Nếu policy và scope khác nhau, giữ aspects riêng thường dễ hiểu.

Ngược lại, nếu hai concrete audit scopes có cùng behavior và failure policy, abstract pointcut là một điểm mở rộng hợp lý để tránh sao chép advice. Nhưng nó không tự giải quyết weaving scope, ordering hoặc checked return contract.

## 19. Cấu hình và thay đổi runtime

Một TimingAspect có thể nhận immutable policy:

```java
// Một data holder Java 17+ minh họa.
record TimingPolicy(String revision, boolean enabled) { }
```

Nếu cần hot reload nhiều field config, một `AtomicReference<TimingPolicy>` hoặc `volatile` snapshot reference có thể công bố nguyên một object bất biến. Invocation có thể chọn snapshot một lần rồi dùng xuyên suốt để tránh trộn version before/after.

AuditAspect có policy schema/retention riêng; RetryAspect có budget/backoff policy riêng. **Không dùng một global mutable map không owner rõ ràng** để mọi aspect cùng update.

### Freshness khác consistency

Snapshot-at-entry cho một invocation có consistency tốt, nhưng authorization/token revocation có thể cần kiểm tra quyền mới nhất ở đúng security boundary. Không biến một nguyên tắc config thuận tiện thành quy tắc security luôn đúng.

## 20. Hiệu năng và nguy cơ aspect quá rộng

Một GodAspect match mọi method có thể tạo overhead:

- Dynamic pointcut evaluation mỗi call.
- Argument binding/context allocation.
- Metric/log event ngay ở hot methods.
- Retry và exception wrapping ngoài ý muốn.
- Recursive interception, log storm, stack growth.
- Sink contention và memory retention.

Tách aspects cho phép scope chính xác, nhưng **số lớp advice có thể tăng** nếu nhiều aspects cùng chọn một join point.

Không tối ưu bằng cách bỏ qua security/audit checks bắt buộc; cân nhắc sampling chỉ cho observability được phép. Cần đo performance bằng workload thực và kiểm chứng target execution count, advice activation count, volume events.

### Logging helper tự bị instrument

Nếu pointcut chọn cả audit sink, lời gọi `AuditAspect → AuditRecorder.record` có thể kích hoạt lại chính audit aspect, tạo recursion. Cần **scope/exclusions rõ** hoặc cơ chế guard đúng contract. Một guard chung không được vô tình tắt authorization trên nested business operation.

## 21. Test từng aspect và test composition riêng

### 21.1. Unit test pointcut

- Method đúng scope được chọn.
- Method ngoài scope không được chọn.
- Overload, null, type erasure, annotation metadata xử lý đúng.
- Runtime argument-value selection không được cache sai theo method name.
- Raw/proxy routes được phân biệt.

### 21.2. Unit test advice

- Caller nhận đúng return value.
- Original Throwable được preserve khi concern chỉ quan sát.
- Per-invocation state không lẫn giữa concurrent/nested calls.
- Recorder failure được xử lý theo policy.
- Sensitive input không bị đưa vào log sai.
- Cleanup được thực hiện trên return và throw.

### 21.3. Integration test composition

- Precedence của hai aspects đúng.
- Một target success được quan sát theo đúng order.
- Một Throwable không thành nhiều business failures giả.
- Audit không bị skip bởi cache/authorization khi contract bắt buộc.
- Retry count và transaction boundary đúng.
- Async completion được phân biệt với method return.
- Tất cả target executions bắt buộc đều thực sự được instrument.

### 21.4. Contract test phía caller

Không chỉ kiểm advice có log; phải kiểm **số lần target chạy, output và side effects caller thực sự nhận**, bao gồm exception path, self-invocation, worker callbacks và class-loader boundaries.

## 22. Ma trận kiểm thử trách nhiệm

| Kịch bản | AuditAspect | TimingAspect | Kết quả cần đúng |
| --- | --- | --- | --- |
| Transfer thành công | Một success event | Một call metric | Receipt đúng |
| Balance thành công | Không audit mutation | Một call metric | Balance đúng |
| Transfer lỗi | Một failure event | Một failure metric | Original exception |
| Metric sink lỗi | Không sửa audit policy | Theo metrics failure policy | Không che target lỗi ngoài ý muốn |
| Audit sink lỗi | Theo audit contract | Không sở hữu lỗi audit | Có thể fail-closed |
| Two calls concurrent | Per-call event tách biệt | Shared counter an toàn | Không cross-talk |
| Nested execution | Không shared current ID | Start local từng invocation | Scope unwind chính xác |
| Raw target bypass | Proxy có thể không audit | Proxy có thể không timing | Phải phát hiện coverage thiếu |
| Cache hit ngoài audit | Có nguy cơ thiếu event | Tùy order | Contract được test |
| Authorization deny | Ghi denied hay không tùy order | Tùy order | Không bypass quyền |
| Retry ba attempts | Audit attempt/operation có định nghĩa | Duration count có định nghĩa | Target attempts đúng |
| Future pending | Audit outcome cần completion logic | Submission/completion khác nhau | Không báo success giả |
| Config reload | Dùng đúng version policy | Snapshot nhất quán | Không mixed-version |
| Method overload mới | Recheck scope | Recheck selection | Không bỏ sót |
| Sensitive references | Redact/không xuất secrets | Labels an toàn | Không lộ dữ liệu |

## 23. Quy trình refactor một aspect quá tải

Một hướng làm có kiểm soát:

**Bước 1 — Inventory:** liệt kê advice, pointcut, fields, dependencies, return/throw transformations và side effects hiện tại.

**Bước 2 — Gom theo policy owner:** audit, timing, auth, retry, transaction, cache, error mapping.

**Bước 3 — Viết contract cho từng concern:** scope, failure policy, data ownership, timing/async semantics.

**Bước 4 — Tách helpers:** recorder/clock/policy interface; tránh shared mutable request state.

**Bước 5 — Chuyển per-call state ra local/invocation context:** không dùng singleton fields `currentId`, `start`, `attempt`.

**Bước 6 — Tách advice và pointcut:** mỗi aspect chỉ chọn operation phục vụ concern của mình.

**Bước 7 — Thiết kế precedence công khai:** authorization, audit, retry, cache, timing, transaction và mapping không sắp tùy tiện.

**Bước 8 — Chạy regression tests:** so sánh number of target calls, outcome, event count, exception identity và effect order.

**Bước 9 — Kiểm tra coverage thực:** weaving vs proxy, self-invocation, overload, async, class loader.

**Bước 10 — Đo overhead và failure behavior:** ghi nhận memory/log volume, audit durability, metrics correctness.

**Refactor structure chỉ được xem thành công nếu semantics nghiệp vụ và concern contracts vẫn đúng.**

## 24. Những anti-pattern dễ nhận biết

1. **“Một aspect chỉ nên có một advice.”** SRP nói về trách nhiệm.
2. **“Gộp mọi cross-cutting code sẽ tái sử dụng tốt hơn.”** Gộp policy khác làm coupling.
3. **“Aspect càng nhiều càng tốt.”** Quá nhiều aspects vụn làm ordering phức tạp.
4. **“Đổi tên GodAspect thành CommonAspect là đủ.”** Không thay ownership.
5. **“Tách thành private methods là xong SRP.”** Chính sách vẫn chung owner.
6. **“Cùng một join point nghĩa là cùng một concern.”** Nhiều aspects có thể khớp cùng method.
7. **“Logger thay thế audit.”** Durable/audit semantics khác logging.
8. **“Metric recording không bao giờ có failure.”** Sink cũng có thể throw.
9. **“Audit recorder failure luôn có thể bỏ qua.”** Tùy compliance.
10. **“Retry có thể wrap mọi operation không cần idempotency.”** Có thể lặp side effects.
11. **“Timing outside và inside retry tương đương.”** Có total vs attempt duration.
12. **“Authorization inside cache vẫn bảo vệ cache hit.”** Cache bên ngoài có thể skip proceed.
13. **“Pointcut chỉ match tên method là đủ.”** Overload/types/binding có thể khác.
14. **“Một aspect nhỏ không thể có security bug.”** Scope thiếu có thể bypass.
15. **“Một shared startNanos field sẽ đúng nhờ volatile.”** Sai per-invocation correlation.
16. **“ThreadLocal tự đi theo future.”** Async propagation cần explicit.
17. **“Hai aspects tách biệt không có runtime coupling.”** Precedence và nested proceed tạo liên hệ.
18. **“Return future nghĩa là tác vụ xong.”** Completion là boundary khác.
19. **“Aspect phù hợp điều phối mọi nghiệp vụ.”** Domain workflow nên explicit khi cần.
20. **“Aspect outcome không cần test nếu chỉ log.”** Logging failure có thể che exception.
21. **“Có annotation trên method là proxy nhất định thấy.”** Metadata và weaving scope cần test.
22. **“Dùng một helper có currentRequest là an toàn vì aspects đã tách.”** Shared mutable helper vẫn rủi ro.
23. **“Không có log đồng nghĩa advice không chạy.”** Sampling/sink cũng ảnh hưởng.
24. **“Số failure events bằng số business failures.”** Một Throwable có thể được nhiều layers quan sát.
25. **“Đổi pointcut không ảnh hưởng behavior.”** Scope thay đổi nơi policy chạy.
26. **“Java Dynamic Proxy tương đương mọi execution weaver.”** Coverage khác nhau.
27. **“Một test helper đủ chứng minh advice.”** Cần integration qua interception.
28. **“Aspect lớn luôn sai.”** Cohesion và ownership mới là tiêu chí.
29. **“Aspect nhỏ luôn đúng.”** Một method ngắn vẫn có hai policies độc lập.
30. **“Bảo mật chỉ cần được instrument một phần.”** Kiểm boundary đầy đủ theo contract.

## 25. Checklist thiết kế trước khi thêm một aspect

### Trách nhiệm

- Có một câu mô tả concern rõ không?
- Có một policy owner chính không?
- Điều gì là lý do thay đổi độc lập?
- Những behavior trong aspect có cùng failure contract không?

### Pointcut và coverage

- Chọn đúng call hay execution join points?
- Có bỏ sót overload, inheritance, self-invocation, async worker?
- Có vô tình match helper/recorder của chính aspect không?
- Có kiểm cả path đi qua proxy và path bypass nếu contract yêu cầu?

### Advice và outcome

- Khi success có preserve return value?
- Khi failure có giữ original Throwable/cause khi cần?
- Nếu có retry/cache/authorization, số `proceed` calls đúng không?
- Có explicit policy khi recorder/metric/helper lỗi?

### State và lifecycle

- Per-invocation state được giữ local/đúng context?
- Shared configuration có immutable snapshot?
- Shared counters/cache có thread-safe và lifecycle đúng?
- Context qua executor có capture/restore/remove?

### Composition

- Thứ tự tương tác với các aspects khác đã quyết định chưa?
- Audit các denied/cached attempts ra sao?
- Timing tính total operation hay từng attempt?
- Transaction và retry có quan hệ đúng?

### Verification

- Có unit tests cho selector và advice?
- Có integration tests trên runtime interception thật?
- Có contract tests cho caller và side effects?
- Có test concurrency/reentrancy, error paths và async completion?

## 26. Bài tập thực hành

1. Biên dịch và chạy `AspectResponsibilityDemo.java`, đối chiếu stdout.
2. Vì sao `balance()` chỉ chạy TimingAspect?
3. Đảo thứ tự hai proxy, dự đoán thứ tự events của transfer.
4. Thêm method `refund`; khi nào nên audit nó cùng `transfer`?
5. Tạo overload `transfer`, kiểm vì sao selector chỉ so method name không luôn đủ.
6. Thử gọi raw target thay vì wrapper; quan sát advice nào không chạy.
7. Chuyển `started` thành field dùng chung rồi gọi nested/concurrent; giải thích sai correlation.
8. Thêm fake `AuditRecorder`, viết test khi recorder thành công và thất bại.
9. Đề xuất policy khi audit bắt buộc fail-closed nhưng timing metric best-effort.
10. Tạo AuthorizationAspect từ chối transfer; xếp trong/ngoài AuditAspect rồi kiểm denied event.
11. Tạo RetryAspect chỉ retry lỗi transient; so sánh duration khi Timing ở trong/ngoài Retry.
12. Tạo cache advice có thể skip proceed; phát hiện audit coverage của cache hit.
13. Viết một contract test rằng return value và exception của LedgerImpl không bị hai aspects làm đổi.
14. Tạo test xác minh một Throwable được audit và timing quan sát nhưng caller vẫn chỉ thấy một business failure.
15. Chia GodAspect thành các concerns, liệt kê lý do thay đổi của từng class.
16. Thiết kế một pointcut không match AuditRecorder của chính nó.
17. Xác định dữ liệu nào có thể ghi trong audit event mà không lộ raw reference.
18. Viết integration test cho method overload và callback worker nhằm phát hiện scope bị bỏ sót.
19. Cho một method trả `CompletableFuture` pending; timing đến return và completion khác nhau ra sao?
20. Đề xuất một shared Clock helper dùng được cho nhiều concerns nhưng không chứa request state.
21. Tạo một immutable TimingPolicy với revision; reload khi call đang chạy và xác định version được dùng.
22. Thiết kế ma trận regression khi đổi precedence của authorization/audit/timing/transaction.
23. Tạo một aspect có nhiều advice nhưng vẫn một policy owner, giải thích vì sao hợp SRP.
24. Tạo một aspect chỉ có một advice nhưng trộn cache và auth, giải thích vì sao vi phạm SRP.
25. Xây checklist review một aspect: **what, where, state owner, failure policy, precedence, verification**.

**Tự kiểm tra:** Vì sao một aspect có thể có nhiều advice mà vẫn một trách nhiệm? Audit khác logging ở điểm nào? Tại sao tách aspects vẫn phải quản lý precedence? Trạng thái mốc thời gian thuộc invocation hay singleton? Vì sao một failure có thể được ghi hai lần nhưng vẫn chỉ là một lỗi nghiệp vụ? Một aspect nhỏ nhưng chọn pointcut sai có đúng SRP không? Những tình huống nào nên giữ logic nghiệp vụ explicit thay vì chuyển vào aspect?

## Kết luận

**Đóng gói aspect theo một mối quan tâm có trách nhiệm rõ** là cách biến AOP thành công cụ module hóa thực sự thay vì chỉ chuyển code lặp sang một nơi khác. Một aspect tốt có **mục tiêu, pointcut, advice behavior, data ownership và failure policy nhất quán**; có thể chứa nhiều advice nếu chúng cùng phục vụ một contract.

Tách audit, timing, authorization, retry và các concerns độc lập giúp giảm coupling, tăng cohesion và dễ kiểm thử, nhưng **không xóa bỏ trách nhiệm kiểm tra thứ tự advice, ranh giới interception, cách xử lý exception và async**. Điểm đến không phải số aspect nhiều hay ít, mà là mỗi concern **có thể được hiểu, thay đổi, kiểm thử và vận hành riêng**, đồng thời tương tác dự đoán được khi cùng áp dụng một join point.
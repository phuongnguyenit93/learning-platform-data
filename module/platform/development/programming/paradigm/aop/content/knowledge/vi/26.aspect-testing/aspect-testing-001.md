# Kiểm thử phần xử lý của advice độc lập với bộ dệt trong AOP

## 1. Bài toán: logic đúng chưa đủ nếu chỉ kiểm thử cả hệ thống dệt

Trong **Aspect-Oriented Programming (AOP)**, một aspect thường kết hợp hai trách nhiệm: **chọn nơi can thiệp** và **thực thi hành vi xuyên suốt**. Một pointcut xác định những join point phù hợp; advice thực hiện logging, đo thời gian, kiểm tra quyền, quản lý scope, retry hoặc một chính sách khác. Bộ dệt (**weaver**) hoặc cơ chế interception có nhiệm vụ đưa advice vào đường chạy của chương trình.

Nếu mọi bài kiểm thử đều phải khởi tạo weaver, nạp lớp đã instrument và chạy một luồng nghiệp vụ lớn, việc kiểm thử logic advice có thể chậm, giòn, khó tạo các trường hợp lỗi và khó xác định nguyên nhân khi test thất bại.

**Mục tiêu của bài:** thiết kế và kiểm thử **phần xử lý bên trong advice** như một thành phần Java thông thường, có thể gọi trực tiếp bằng fake invocation, stub policy, fake clock và bộ ghi sự kiện trong bộ nhớ. Kiểm thử logic không cần bộ dệt; kiểm thử pointcut/weaving được thực hiện riêng ở tầng tích hợp.

Phương pháp này không phủ nhận vai trò của weaving. Nó giải quyết hai câu hỏi khác nhau:

- **Logic advice có đúng không?** Khi cho một join point giả lập với kết quả hoặc exception xác định, advice có xử lý đúng, gọi tiếp đúng số lần, giữ nguyên hợp đồng, cleanup scope và phát event đúng không?
- **Aspect có được áp dụng đúng trong chương trình không?** Pointcut có khớp đúng method, thứ tự advice có đúng, các lời gọi nội bộ có được intercept theo cơ chế đã chọn không?

Một bài test chỉ chứng minh câu đầu tiên **không chứng minh** câu thứ hai. Ngược lại, một test dệt thành công có thể không bao phủ các nhánh lỗi tinh vi của logic advice.

## 2. Đọc đúng các thuật ngữ AOP

| Thuật ngữ | Ý nghĩa đối với kiểm thử |
| --- | --- |
| **Join point** | Điểm thực thi thật có thể được intercept, ví dụ method call/execution |
| **Pointcut** | Điều kiện chọn join point; cần kiểm thử ở mức weaving/integration |
| **Advice** | Hành vi chạy before, after, around, on throwing; có thể tách logic để unit test |
| **Aspect** | Đơn vị tập hợp pointcut/advice, có thể chứa state và quy tắc composition |
| **Weaver** | Cơ chế nối aspect với bytecode/đường thực thi; không bắt buộc cho unit test của phần logic |
| **Proceed** | Tiếp tục tới phần còn lại của chuỗi advice hoặc computation tại join point |
| **Invocation adapter** | Lớp mỏng chuyển dữ liệu của join point thật thành lời gọi tới advice logic |
| **Test double** | Fake/stub/spy thay thế invocation, logger, policy, clock, executor hoặc context |

Một **before advice** thường cần dữ liệu về operation và một handler được gọi ở trước phần thân. Một **around advice** khó hơn vì phải kiểm soát lệnh tiếp tục và bảo toàn kết quả/ngoại lệ. Vì vậy bài này tập trung vào around advice và những trường hợp dễ sai: gọi tiếp hai lần, gọi tiếp khi chưa cho phép, nuốt exception, phát log sai, giữ state xuyên invocation.

## 3. Nguyên tắc kiến trúc: tách phần gắn dệt và phần xử lý

Một thiết kế dễ kiểm thử chia thành hai lớp trách nhiệm:

~~~text
             Bộ dệt / interceptor thật
                        |
                Thin AOP adapter
      (pointcut, binding args, this/target,
       convert proceed into callable)
                        |
                        v
                Advice handler
       (policy, timing, logging, cleanup)
             /          |          \
       Clock fake    Sink fake     Invocation fake
~~~

**Adapter** phụ thuộc vào cú pháp/cơ chế interception; **handler** nên phụ thuộc vào các interface nhỏ có ý nghĩa. Một handler có thể nhận:

- tên operation ổn định;
- metadata đã được binding/validate;
- một đối tượng có khả năng **proceed** đúng hợp đồng;
- đồng hồ dùng đo duration;
- event sink/logger;
- authorization policy hoặc context provider;
- cơ chế tạo/đóng scope.

Nếu adapter chỉ thực hiện chuyển đổi tham số và gọi handler, phần lớn nhánh xử lý có thể được unit test mà không nạp aspect hoặc weaver.

Tuy nhiên, **không cố loại mọi đặc trưng AOP** khỏi test: các điều kiện match pointcut, sự khác nhau giữa call và execution, self-invocation, precedence hoặc per-clause instantiation cần test với cơ chế AOP thực sự.

## 4. Viết hợp đồng cho advice trước khi kiểm thử

Một advice đáng tin có hợp đồng quan sát được. Ví dụ với advice logging:

1. Nếu target trả bình thường, trả **đúng giá trị** đó cho caller.
2. Nếu target ném exception, để **nguyên exception hợp lệ** tới caller.
3. Gọi phần computation tiếp theo **đúng một lần**, không âm thầm lặp nghiệp vụ.
4. Phát một event hoàn tất theo contract của **invocation đồng bộ**.
5. Đo duration bằng đồng hồ đơn điệu, không đòi số nanosecond cố định từ máy thật.
6. Khi sink lỗi, hành vi theo chính sách: logging best-effort không được che lỗi nghiệp vụ; audit bắt buộc có hợp đồng thất bại khác.
7. Không tự log dữ liệu đầu vào/đầu ra nhạy cảm.
8. Với scope, phải cleanup trong `finally` kể cả khi target ném exception.

Với authorization advice, contract khác:

1. Lấy danh tính từ nguồn tin cậy; định danh đúng action/resource.
2. **DENY** khi không đủ quyền hoặc không thể xác định quyền theo chính sách an toàn.
3. Khi DENY, **không gọi proceed**, tức target không được thực hiện side effect.
4. Khi ALLOW, gọi proceed đúng một lần và giữ nguyên result/exception.
5. Không lấy quyền từ dữ liệu caller tự gán hoặc một ThreadLocal chưa được thiết lập đáng tin.

Với retry advice, `proceed` có thể được gọi nhiều lần **có chủ đích**; cần một hợp đồng riêng về idempotency, số attempt, retryable failure, deadline và backoff. Không dùng cùng assertion “proceed luôn bằng 1” cho mọi kiểu advice.

## 5. Đặt seam kiểm thử ở đâu?

**Seam** là điểm có thể thay dependency thật bằng dependency kiểm thử. Những seam phổ biến:

| Dependency thật | Test double | Điều cần xác minh |
| --- | --- | --- |
| Proceed tới computation tiếp theo | Fake invocation/spy action | Số lần gọi, result, exception, thứ tự |
| System clock | Fake monotonic clock | Duration theo các mốc chủ động |
| Logger/telemetry exporter | In-memory event sink | Event count, schema, outcome, không lộ dữ liệu |
| Policy engine | Stub permit/deny/throw | Quyết định ALLOW/DENY, fail closed |
| Context source | Fake trusted context provider | Context hiện hành đúng, không rò |
| Scope manager | Spy open/close | Cleanup dù exception |
| Retry sleeper | Fake sleeper | Attempt count, delay policy, không ngủ thật |
| Executor | Controlled/manual executor | Submission, propagation, completion |
| Repository/resource resolver | Fake metadata provider | Quyền trên đúng resource, lỗi dữ liệu |

Ưu tiên interface nhỏ gắn với hành vi, thay vì mock toàn bộ API reflection/weaver. Một interface có phương thức `T proceed() throws Exception` đã đủ cho nhiều unit test đồng bộ.

Hạn chế của abstraction: join point thật có thể cho phép ném `Throwable`, có return type đặc biệt, hoặc có metadata về target/this/args. Adapter cần giải quyết sự khác biệt đó và được kiểm thử tích hợp, không âm thầm đổi loại ngoại lệ hoặc tham số.

## 6. Ví dụ Java 17 hoàn chỉnh: unit test handler không cần weaver

Chương trình dưới đây chạy **chỉ với JDK 17+**, không cần một thư viện AOP, test framework hay quá trình weaving. Nó minh họa:

- `CheckedAction<T>`: một invocation giả, tương đương khái niệm proceed;
- `ObservationAdvice`: advice logic ghi event cho return/exception;
- `SequenceClock`: đồng hồ giả cho duration hoàn toàn xác định;
- `List<Observed>`: fake event sink để assert event;
- `AuthorizationAdvice`: advice logic kiểm tra policy trước khi gọi tiếp;
- các test bằng assertion tường minh, có stdout xác định.

Trong chương trình thật, một adapter mỏng tại join point sẽ tạo action gọi proceed rồi chuyển cùng metadata vào handler. **Chương trình sau chỉ kiểm thử handler; nó cố ý không tuyên bố kiểm thử weaving.**

Tạo tệp **AdviceLogicUnitDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.LongSupplier;

public final class AdviceLogicUnitDemo {

    @FunctionalInterface
    interface CheckedAction<T> {
        T proceed() throws Exception;
    }

    record Observed(
            String operation,
            String outcome,
            long durationNanos,
            String errorType) { }

    static final class SequenceClock implements LongSupplier {
        private final long[] values;
        private int next;

        SequenceClock(long... values) {
            this.values = values.clone();
        }

        @Override
        public long getAsLong() {
            if (next >= values.length) {
                throw new AssertionError("unexpected clock read");
            }
            return values[next++];
        }
    }

    static final class ObservationAdvice {
        private final LongSupplier monotonicClock;
        private final Consumer<Observed> sink;

        ObservationAdvice(
                LongSupplier monotonicClock,
                Consumer<Observed> sink) {
            this.monotonicClock = Objects.requireNonNull(monotonicClock);
            this.sink = Objects.requireNonNull(sink);
        }

        <T> T around(String operation, CheckedAction<T> action)
                throws Exception {
            Objects.requireNonNull(operation);
            Objects.requireNonNull(action);

            long start = monotonicClock.getAsLong();
            try {
                T value = action.proceed();
                long elapsed = monotonicClock.getAsLong() - start;
                emitBestEffort(new Observed(
                        operation, "returned", elapsed, null));
                return value;
            } catch (Exception error) {
                long elapsed = monotonicClock.getAsLong() - start;
                emitBestEffort(new Observed(
                        operation, "threw", elapsed,
                        error.getClass().getSimpleName()));
                throw error;
            }
        }

        private void emitBestEffort(Observed event) {
            try {
                sink.accept(event);
            } catch (RuntimeException ignored) {
                // Chỉ thích hợp cho telemetry best-effort.
                // Một hệ thống audit bắt buộc cần hợp đồng riêng.
            }
        }
    }

    @FunctionalInterface
    interface Permit {
        boolean allowed(String operation, String resource);
    }

    static final class AuthorizationAdvice {
        private final Permit policy;

        AuthorizationAdvice(Permit policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        <T> T around(
                String operation,
                String resource,
                CheckedAction<T> action) throws Exception {
            if (!policy.allowed(operation, resource)) {
                throw new SecurityException("access denied");
            }
            return action.proceed();
        }
    }

    static final class DomainFailure extends Exception { }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void testSuccess() throws Exception {
        List<Observed> events = new ArrayList<>();
        AtomicInteger proceedCalls = new AtomicInteger();
        ObservationAdvice advice = new ObservationAdvice(
                new SequenceClock(100, 135),
                events::add);

        String value = advice.around("order.submit", () -> {
            proceedCalls.incrementAndGet();
            return "ACCEPTED";
        });

        require("ACCEPTED".equals(value), "result changed");
        require(proceedCalls.get() == 1, "proceed count");
        require(events.equals(List.of(
                new Observed("order.submit", "returned", 35, null))),
                "wrong success event");
        System.out.println("PASS success: result, once, event");
    }

    static void testFailure() throws Exception {
        List<Observed> events = new ArrayList<>();
        AtomicInteger proceedCalls = new AtomicInteger();
        DomainFailure original = new DomainFailure();
        ObservationAdvice advice = new ObservationAdvice(
                new SequenceClock(200, 225),
                events::add);

        boolean caughtSameObject = false;
        try {
            advice.around("order.submit", () -> {
                proceedCalls.incrementAndGet();
                throw original;
            });
        } catch (DomainFailure caught) {
            caughtSameObject = caught == original;
        }

        require(caughtSameObject, "original exception not preserved");
        require(proceedCalls.get() == 1, "proceed count");
        require(events.equals(List.of(
                new Observed("order.submit", "threw", 25,
                        "DomainFailure"))),
                "wrong failure event");
        System.out.println("PASS failure: original exception, event");
    }

    static void testBrokenObserver() throws Exception {
        ObservationAdvice advice = new ObservationAdvice(
                new SequenceClock(0, 10),
                event -> {
                    throw new IllegalStateException("sink unavailable");
                });

        String result = advice.around("order.submit", () -> "OK");
        require("OK".equals(result), "observer changed result");
        System.out.println("PASS observer: result preserved");
    }

    static void testAuthorization() throws Exception {
        AtomicInteger proceedCalls = new AtomicInteger();
        AuthorizationAdvice advice = new AuthorizationAdvice(
                (operation, resource) ->
                        operation.equals("order.approve")
                                && resource.equals("owned"));

        boolean denied = false;
        try {
            advice.around("order.approve", "other", () -> {
                proceedCalls.incrementAndGet();
                return "BAD";
            });
        } catch (SecurityException expected) {
            denied = true;
        }

        require(denied, "missing denial");
        require(proceedCalls.get() == 0, "proceeded after denial");

        String value = advice.around("order.approve", "owned", () -> {
            proceedCalls.incrementAndGet();
            return "APPROVED";
        });

        require("APPROVED".equals(value), "allow result changed");
        require(proceedCalls.get() == 1, "allow must proceed once");
        System.out.println("PASS authorization: deny=0, allow=1");
    }

    public static void main(String[] args) throws Exception {
        testSuccess();
        testFailure();
        testBrokenObserver();
        testAuthorization();
        System.out.println("ALL TESTS PASSED");
    }
}
~~~

Chạy:

~~~bash
javac AdviceLogicUnitDemo.java
java AdviceLogicUnitDemo
~~~

Stdout chính xác:

~~~text
PASS success: result, once, event
PASS failure: original exception, event
PASS observer: result preserved
PASS authorization: deny=0, allow=1
ALL TESTS PASSED
~~~

### Điều gì đã được kiểm chứng?

**testSuccess:** fake invocation trả ACCEPTED, advice trả lại giá trị nguyên vẹn, action được gọi một lần và đúng một event `returned` có duration 35 nanosecond theo đồng hồ giả. Đây là số **giả lập để kiểm thử**, không phải duration đo máy thật.

**testFailure:** action ném một đối tượng DomainFailure cụ thể. Test xác minh caller nhận **chính cùng đối tượng exception** (so sánh tham chiếu), proceed đúng một lần và event `threw` ghi đúng loại lỗi.

**testBrokenObserver:** sink ném IllegalStateException nhưng kết quả nghiệp vụ vẫn OK vì mẫu này quy định **telemetry best-effort**. Không áp dụng mô hình nuốt lỗi này cho audit bắt buộc hoặc những log được coi là bằng chứng nghiệp vụ.

**testAuthorization:** policy từ chối resource "other" trước khi computation chạy, nên proceed count bằng 0. Với resource "owned", policy cho phép, invocation chạy đúng một lần và trả APPROVED.

**Không có weaver trong bốn bài test.** Điều được kiểm thử là các branch và hợp đồng của handler, không phải khả năng AspectJ hoặc một cơ chế AOP cụ thể chặn đúng method.

### Giới hạn quan trọng của ví dụ

Ví dụ dùng `Exception` để có chữ ký Java đơn giản. Một advice quanh API có thể ném `Throwable`, bao gồm `Error`; adapter thực phải có chiến lược lan truyền lỗi tương ứng. Ngoài ra, `ObservationAdvice` trong ví dụ giả định clock có sẵn và monotonic; trường hợp clock selbst ném lỗi, hoặc overflow/âm do nguồn đồng hồ sai, cần chính sách phù hợp. Đo **System.nanoTime()** trong chương trình thật là cách đo chênh lệch cùng tiến trình; fake clock giúp test không phụ thuộc tốc độ máy.

Trong mã ví dụ, `ObservationAdvice` phân loại **lời gọi đồng bộ** thành returned/threw, không tự xác định business success/failure của một `Result` object hoặc Future chưa hoàn tất. Khi yêu cầu là outcome nghiệp vụ, nên dùng bộ phân loại outcome riêng có test tương ứng.

## 7. Cách gắn handler vào advice thật

Ở mã có cơ chế AOP thực, lớp adapter chịu trách nhiệm:

1. Chọn join point bằng pointcut hoặc cấu hình tương đương.
2. Lấy tên operation ổn định và các binding phù hợp.
3. Chuyển lời gọi proceed của công cụ AOP thành một callback đáp ứng interface handler.
4. Trả result hoặc lan truyền throwable đúng contract.
5. Không tự lặp lại policy hoặc logic logging bên trong adapter.

Sơ đồ khái niệm:

~~~text
around selectedJoinPoint:
    metadata = readValidatedJoinPointMetadata()
    action = adapterForProceed()
    return adviceHandler.around(metadata.operation, action)
~~~

Đây là **giả mã** để minh họa ranh giới trách nhiệm, không phải một đoạn AspectJ có thể biên dịch nguyên xi. Mỗi công cụ AOP có kiểu advice và chữ ký proceed khác nhau; một số áp dụng weaving ở compile time hoặc load time, một số dùng proxy/interceptor. Adapter phải xử lý các quy tắc đó thay vì buộc handler phụ thuộc trực tiếp vào toàn bộ API weaving.

Một adapter mỏng có thể được review riêng: nó không nên biết giá, inventory, policy nghiệp vụ, hay cách serialize log; handler và các policy phụ trợ sở hữu hành vi đó. Khi đổi cơ chế weaving, phần lớn unit tests của handler vẫn giữ nguyên, còn adapter/integration tests phải được cập nhật.

## 8. Unit test advice, test adapter và test weaving khác nhau thế nào?

| Cấp kiểm thử | Đối tượng | Cần weaver không? | Ví dụ câu hỏi |
| --- | --- | --- | --- |
| Pure policy test | Bộ tính policy, classifier, formatter | Không | Lỗi nào là rejected? Ai được quyền? |
| Advice handler unit test | Xử lý proceed/exception/scope/event | Không | Có gọi đúng một lần, trả đúng value? |
| Adapter unit test | Binding và chuyển tiếp metadata/callback | Có thể không nếu adapter tách được | Có lấy đúng operation, args và throwable? |
| Weaving/pointcut test | Pointcut + advice thật + code được instrument | Có | Method này có thật sự được chặn? |
| Composition test | Nhiều aspect cùng join point | Có | Precedence, retry, transaction đúng? |
| End-to-end test | Business flow qua ranh giới thật | Thường có hoặc chạy hệ thống thực | Thao tác hoàn tất đúng và telemetry nhất quán? |

**Không thay thế test weaving bằng test handler.** Một handler hoàn hảo nhưng pointcut sai package sẽ không chạy. Một advice unit test thành công cũng không chứng minh rằng gọi nội bộ trong cùng object đi qua proxy, hoặc execution/call join point được công cụ hỗ trợ như dự kiến.

Một suite cân bằng dùng nhiều unit tests nhanh để bao phủ hành vi, một số ít integration tests có mục tiêu để kiểm tra **điểm nối với AOP** và một vài end-to-end tests quan trọng cho các đường nghiệp vụ nhạy cảm.

## 9. Kiểm thử proceed: một lần, không lần nào, hay nhiều lần có chủ đích?

**Around advice** có quyền tác động tới số lần tiếp tục computation. Vì thế số lần proceed là một trong những assertion có giá trị nhất.

### Observer thuần

Ghi log, metric hoặc tracing thông thường nên gọi proceed **đúng một lần**. Nếu lời gọi bị ném lỗi, advice vẫn lan truyền lỗi và cleanup các scope mà nó tạo.

### Authorization/guard

Khi DENY trước side effect, phải gọi proceed **0 lần**. Khi ALLOW, thường gọi **1 lần**. Ngoài assert response hoặc exception, cần spy đếm hành vi thật để đảm bảo target không chạy sau DENY.

### Retry

Một retry advice có thể gọi proceed **N lần** theo policy. Unit tests phải kiểm tra:

- Lỗi retryable được thử lại đúng số lần tối đa.
- Lỗi non-retryable không bị thử lại.
- Khi lần sau thành công, trả đúng result.
- Khi hết số lượt, giữ hoặc chuyển exception theo hợp đồng đã định.
- Delay/backoff/deadline kiểm thử qua fake sleeper/clock, không ngủ thật.
- Các side effect có idempotency hoặc không được retry nếu unsafe.
- Attempt metric và operation metric không bị đếm trùng.

### Cache hoặc circuit breaker

Cache hit có thể khiến proceed bằng **0**, cache miss bằng **1**. Circuit breaker open có thể fail fast không gọi target. Unit test phải đối chiếu hành vi với policy và trạng thái giả của breaker, không mặc định mọi advice đều thực thi computation.

**Điểm chung:** expected proceed count đến từ hợp đồng của concern, không đến từ một nguyên tắc duy nhất áp dụng cho toàn bộ AOP.

## 10. Dùng spy invocation để kiểm thử thứ tự side effect

Một spy đơn giản có thể lưu trình tự sự kiện:

~~~java
// Đoạn minh họa riêng: event log cho kiểm thử thứ tự.
List<String> steps = new ArrayList<>();
CheckedAction<String> action = () -> {
    steps.add("proceed");
    return "DONE";
};
~~~

Nếu handler có scope:

~~~text
open-scope
before-log
proceed
after-log
close-scope
~~~

Test nên assert **toàn bộ thứ tự** theo contract, chứ không chỉ kiểm tra "có đủ 5 event". Bởi đóng scope trước khi ghi log có thể làm mất correlation context, còn log trước khi cập nhật outcome có thể khiến bản ghi mô tả sai trạng thái.

Một cách tổ chức rõ ràng là dùng in-memory recorder chung cho những dependency giả: logger fake, scope fake và invocation spy cùng append vào một danh sách. Với exception, danh sách mong đợi có thể là:

~~~text
open-scope
before-log
proceed
error-log
close-scope
~~~

Nếu code cần cleanup ngay cả khi event sink lỗi, test thêm đường sink throw và kiểm tra close vẫn xảy ra. Không nên dựa vào sleep hoặc điều kiện race để xác nhận thứ tự trong unit test đồng bộ.

## 11. Kiểm thử bảo toàn result và exception

Một advice chỉ quan sát không được ngầm chuyển đổi kết quả. Các trường hợp cần thử:

| Trường hợp | Assertion |
| --- | --- |
| Target trả object | Chính cùng object được trả nếu contract giữ tham chiếu |
| Target trả null | Vẫn trả null, không ép thành Optional hoặc lỗi |
| Target trả primitive qua adapter | Boxing/unboxing hoặc return type không bị đổi |
| Target ném checked exception | Caller nhận exception hợp lệ ban đầu |
| Target ném runtime exception | Không bị nuốt hoặc bọc bất ngờ |
| Target ném Error | Cần bảo toàn/cleanup theo chính sách, adapter có test riêng |
| Handler precondition sai | Không tự tiến hành nghiệp vụ nếu không hợp lệ |
| Observer ném lỗi | Không che lỗi gốc nếu observer là best-effort |
| Handler thay result có chủ đích | Phải có contract riêng và test chuyển đổi |

Với reflection, `Method.invoke` thường bọc lỗi target trong `InvocationTargetException`; adapter phải unwrap khi hợp đồng yêu cầu giữ lỗi gốc. Fake invocation không tự kiểm chứng được chi tiết reflection đó. Vì vậy cần một adapter test bổ sung với một method thật ném exception.

Nếu advice cố ý chuyển lỗi sang một loại exception chung, hãy xác định **nguyên nhân, stack/cause và mã lỗi** nào được giữ lại. Không biến mọi checked exception thành generic RuntimeException chỉ vì interface test double cho tiện.

## 12. Kiểm thử timing mà không phụ thuộc đồng hồ thật

Việc viết test dạng “method chạy trong khoảng 5–10 ms” rất dễ flaky vì CPU scheduling, JIT warm-up, GC, máy CI và sleep không có độ chính xác tuyệt đối.

Phương án tốt hơn:

1. Truyền clock qua dependency.
2. Dùng fake clock trả một dãy thời điểm xác định.
3. Cho invocation fake trả kết quả hoặc ném lỗi.
4. Kiểm tra duration = end − start và event được phát đúng một lần.
5. Test clock được gọi bao nhiêu lần nếu đó là phần của contract.

Ví dụ trong chương trình Java ở trên, fake clock trả `100` và `135`, nên elapsed = `35` chính xác. Không cần sleep.

Trong môi trường thật, dùng đồng hồ **đơn điệu** như `System.nanoTime()` để đo duration; không dùng chênh lệch wall clock để suy ra thời gian trôi qua vì đồng hồ hệ thống có thể được điều chỉnh.

Nếu advice đo thời gian task bất đồng bộ, unit test đồng hồ vẫn chưa đủ: cần fake completion signal hoặc controlled executor để kiểm tra lúc nào "done" xảy ra. Đây là một hợp đồng lifecycle khác.

## 13. Kiểm thử logging và metric ở mức semantics

Một advice ghi log/metric cần được test theo **schema và ý nghĩa**, không lệ thuộc vào một chuỗi text formatting ngẫu nhiên.

**Nên assert:**

- event type ổn định (invocation_returned, operation_finished, attempt_failed...);
- operation name ổn định;
- outcome đúng theo contract;
- duration và đơn vị chính xác;
- số event: một hay nhiều theo từng occurrence;
- correlation ID được dùng đúng hoặc bị bỏ nếu không hợp lệ;
- error code/exception class đã được chuẩn hóa;
- không chứa secret hoặc dữ liệu nhạy cảm.

**Không nên gắn test vào:** timestamp thực của máy, địa chỉ bộ nhớ, thứ tự trường JSON nếu schema không yêu cầu, log formatter của thư viện hoặc sleep time.

Một test kiểm tra count cũng cần biết **đơn vị đo**. Một operation có retry ba lần có thể hợp lệ với một event cấp operation và ba event cấp attempt. Đừng viết test “mọi event cùng trace ID phải có đúng một bản ghi”; trace có thể chứa rất nhiều sự kiện hợp lệ.

Nếu instrumentation có sampling, unit test nên dùng sampler fake luôn cho phép hoặc luôn từ chối, rồi assert event count tương ứng; không dựa vào random sampling trong bài test quyết định.

## 14. Authorization và context: lỗi unit test phải bắt được

Một authorization handler có thể phụ thuộc vào trusted identity context. Test nên bao phủ:

- Không có context → DENY.
- Danh tính đã xác thực nhưng thiếu permission → DENY.
- Có permission nhưng không có quyền trên resource/tenant → DENY.
- Policy evaluator trả lỗi/timeout → xử lý theo chính sách fail-closed.
- Đủ điều kiện → proceed một lần.
- DENY → proceed bằng 0 và không có side effect.
- Caller cố giả mạo role/tenant trong args → không được nâng thành quyền.
- Delegation có scope → không được mở rộng action/resource ngoài scope được cấp.
- Audit event cho DENY không chứa token hoặc thông tin nhạy cảm.

Thay policy evaluator bằng stub `Permit` như ví dụ giúp kiểm tra chính xác **behavior của advice**. Nhưng việc context thật được lấy từ nguồn xác thực, binding resource đúng và mọi protected method đều được chặn phải có integration/security tests riêng.

Một lời gọi ALLOW ở method entry cũng không bảo đảm quyền chưa bị thu hồi trước lúc commit. Nếu thao tác nhạy cảm phụ thuộc vào state thay đổi, cần test domain/storage invariant hoặc kiểm tra quyền tại mốc cập nhật có thẩm quyền; unit test advice không tự khử race condition này.

## 15. Cleanup scope trong success, throw và early return

Nhiều aspect tạo scope: trace span, thread context, lock, permit hoặc transaction. Mỗi resource có vòng đời khác nhau và không phải resource nào cũng phù hợp với quanh một lời gọi ngắn.

Đối với scope invocation đồng bộ, cấu trúc đúng thường là:

~~~text
scope = open()
try:
    return proceed()
finally:
    scope.close()
~~~

Đây là giả mã. Unit tests nên kiểm tra:

1. Target trả → scope được đóng đúng một lần.
2. Target ném exception → scope vẫn đóng đúng một lần.
3. Advice từ chối trước proceed → những scope đã mở vẫn được cleanup.
4. Scope đóng ném lỗi → exception precedence/cause tuân hợp đồng; không vô tình che lỗi gốc.
5. Nested scopes → khôi phục parent context, không chỉ remove vô điều kiện.
6. Không giữ ThreadLocal cũ sau lời gọi; đặc biệt với pooled threads.
7. Không đóng scope được tạo ở caller thread từ một callback chạy trên worker khác nếu scope yêu cầu thread affinity.

Với một transaction hoặc audit có yêu cầu bền vững, việc đóng scope có thể tác động business behavior. Hãy kiểm thử cả thứ tự commit/rollback và error semantics; không dùng quy tắc best-effort logging cho mọi resource.

## 16. Test advice có state và concurrency

Một singleton aspect có thể chứa field mutable dùng chung giữa các lời gọi. Unit test tuần tự đôi khi vẫn pass dù production có race.

Những điều cần xác minh:

- Counter dùng cho metrics có cơ chế atomic/thread-safe thích hợp.
- Mutable context không được lưu trong field singleton rồi dùng chung giữa request.
- State per-object không bị nhầm là per-request nếu service instance sống lâu.
- State per-control-flow không tự động đi theo task qua executor.
- Khi task chạy song song, context snapshot của task A không bị lẫn với B.
- Callback hoàn tất không gọi lại observer hai lần nếu contract yêu cầu một event duy nhất.
- Scope/thread-local luôn cleanup, kể cả khi cancellation hoặc exception.

Có thể dùng **CountDownLatch** hoặc controlled executor để điều phối một interleaving có ý nghĩa thay vì sleep và cầu may. Nhưng một test chạy được không chứng minh tuyệt đối code không có race; dùng thêm thiết kế immutable data, synchronization và kiểm tra tải phù hợp.

Nếu logic advice dùng một map cache, cần test eviction, lifetime, key collisions, size limit, tenant separation và concurrency. Một fake clock giúp kiểm thử TTL ổn định.

## 17. Async advice: callback được kích hoạt ở mốc nào?

Với một API trả `CompletionStage<T>`, method return chỉ nói rằng caller có một handle tới kết quả, không đồng nghĩa task đã hoàn thành. Một observer muốn ghi **operation outcome** phải hiểu completion lifecycle.

Một thiết kế phù hợp là tách:

- **invocation_returned**: xảy ra khi method trả stage;
- **operation_completed**: xảy ra khi stage hoàn tất theo contract;
- **task_terminated**: xảy ra khi công việc nền thực sự dừng và cleanup.

Ba sự kiện này có thể khác nhau. Nếu timeout/cancellation chỉ tác động lên wrapper stage, task nền có thể tiếp tục chạy.

Bài test async nên dùng một `CompletableFuture` điều khiển được, không hoàn tất ngay từ đầu:

~~~java
// Chỉ là đoạn minh họa cho một test khác, không thuộc
// chương trình runnable ở mục 6.
CompletableFuture<String> future = new CompletableFuture<>();

// Gọi adapter/handler async đã được định nghĩa trong dự án.
// Tại đây future chưa xong: chưa được phát final completion.
future.complete("DONE");

// Bây giờ assertion mới mong có final success event.
~~~

Nếu có lỗi, dùng `completeExceptionally` để xác nhận outcome failure, exception unwrapping và số callback event. Với cancellation, test semantic contract của API, không mặc định task thực sự dừng.

Một callback observer có thể chạy ngay khi đăng ký nếu stage đã hoàn tất, hoặc chạy ở thread hoàn tất về sau. Bởi vậy không nên giả định ThreadLocal caller tự còn hợp lệ; context cần được truyền theo task và cleanup đúng scope.

**Kiểm thử logic async độc lập với weaver** vẫn là phương pháp hữu ích, nhưng cần một handler/adapter cho completion, không dùng around handler đồng bộ rồi gán nhầm returned thành success.

## 18. Không cần mock cả đối tượng join point

Một lỗi thường gặp là viết hàng chục mock cho method signature, declaring type, annotation, args, this, target, source location và proceed chỉ để kiểm thử việc phát một event.

Cách tốt hơn:

1. Tách phần **đọc metadata từ join point** vào adapter nhỏ.
2. Biến metadata thành một record bất biến như `OperationInfo(name, category, resourceId)`.
3. Cho handler nhận record đó cùng `CheckedAction<T>`.
4. Test handler bằng record và fake action.
5. Test adapter riêng bằng một số case có metadata đặc trưng.
6. Test pointcut thực với weaver ở tầng tích hợp.

Nếu handler thật sự cần reflection metadata, vẫn có thể dùng interface trung gian hoặc fixture Method/Annotation thật, nhưng đừng để unit test phụ thuộc vào toàn bộ hệ thống weaving.

Ưu điểm là các bài test mô tả **hành vi cần đạt** thay vì thao tác của API. Điều này giúp đổi cơ chế weaving hoặc nâng cấp thư viện AOP với ít test giòn hơn.

## 19. Điều gì bắt buộc phải kiểm thử với bộ dệt?

Các thuộc tính sau không được chứng minh chỉ bằng unit test của advice handler:

| Thuộc tính weaving | Ví dụ kiểm thử |
| --- | --- |
| Pointcut matching | Method có annotation thực sự bị chọn; method khác không bị chọn |
| Call vs execution join point | Advice chạy ở điểm caller hay trong method execution theo cấu hình |
| Self-invocation/direct call | Những đường gọi này có đi qua interception không |
| Type/argument binding | Advice lấy đúng tham số, target, this và annotation |
| Advice precedence | Around/before/after lồng nhau theo thứ tự đã khai báo |
| Abstract aspect inheritance | Concrete subaspect thực sự áp dụng inherited advice/pointcut |
| Aspect instantiation | Singleton, per-object, per-flow hoặc per-type theo mô hình hỗ trợ |
| Weaving scope | Class/library cần instrument thật sự được xử lý |
| Exception boundary | Exception được truyền qua các lớp advice với semantics đúng |
| Multiple aspects | Không gây duplicate business completion hoặc thay đổi thứ tự ngoài ý muốn |

Với chương trình Java, tích hợp thực tế có thể là compile-time weaving, load-time weaving hoặc proxy/interceptor, tùy công cụ được sử dụng. Mỗi cách có những đường gọi, khả năng join point và chi phí khác nhau. Test chỉ dùng fake invocation sẽ không phát hiện lỗi không nạp agent, không weave bytecode hoặc pointcut vô tình không khớp.

## 20. Tổ chức test suite theo hai lớp

Một tổ chức dễ duy trì:

~~~text
tests/
  advice-logic/
    observation-success-failure
    authorization-allow-deny
    scope-cleanup
    retry-policy
    async-completion
  aspect-integration/
    pointcut-selection
    metadata-binding
    advice-order
    aspect-instantiation
    bypass-cases
  end-to-end/
    protected-business-flow
    transaction-and-outcome
~~~

Đây là sơ đồ cấu trúc, không phải các tệp bắt buộc hay dự án đã tồn tại. Mục tiêu là tách lỗi:

- **Logic test thất bại:** nhiều khả năng bug trong handler/policy.
- **Logic test pass, integration test thất bại:** xem adapter, pointcut, weaving configuration, thứ tự hoặc giới hạn join point.
- **Integration pass, end-to-end thất bại:** xem dữ liệu, transaction, concurrency, lifecycle, external dependencies hoặc assumptions giữa các module.

Không nhất thiết tạo test case cho từng method helper chỉ vì pointcut từng khớp nó. Hãy kiểm thử behavior được hứa hẹn và vài trường hợp đại diện bao phủ cả match lẫn exclusion.

## 21. Anti-pattern trong kiểm thử Advice

### Anti-pattern A: gọi thẳng method bị instrument rồi coi là unit test của advice

Test này có thể hữu ích ở tầng integration, nhưng buộc logic test phụ thuộc weaver, cấu hình, thứ tự aspect và môi trường. Khó mô phỏng lỗi sink hoặc clock.

**Cải thiện:** rút logic vào handler rồi test trực tiếp; giữ một số test dệt thật.

### Anti-pattern B: kiểm thử chỉ bằng số dòng stdout

Một lời gọi có thể in hai dòng start/end hợp lệ; nhiều logger hoặc appenders có thể tạo bản sao. Thay đổi định dạng cũng làm test vỡ.

**Cải thiện:** kiểm tra event có schema/type/scope và số occurrence đúng; dùng in-memory sink.

### Anti-pattern C: sleep để ép timeout/latency

Test thất bại ngẫu nhiên khi CPU scheduler/CI thay đổi.

**Cải thiện:** fake clock, fake sleeper hoặc controlled executor.

### Anti-pattern D: kiểm tra exception type nhưng không kiểm tra nguyên nhân gốc

Advice có thể bọc lại hoặc thay stack/cause ngoài ý muốn.

**Cải thiện:** assert exact reference khi contract là preserve; nếu transform có chủ đích, assert cause và error code.

### Anti-pattern E: bỏ qua proceed call count

Một advice có thể gọi target hai lần trong đường success hoặc gọi dù authorization DENY.

**Cải thiện:** spy đếm proceed, quan sát side effect và kiểm tra đúng số lần theo policy.

### Anti-pattern F: dùng static shared fixture mutable

Các bài test có thể ảnh hưởng nhau và thất bại khi chạy song song.

**Cải thiện:** tạo handler và fake dependencies mới cho mỗi test; cleanup ThreadLocal/registry và test isolation.

### Anti-pattern G: giả lập outcome thành công cho Future chưa hoàn tất

Method return không chứng minh task success.

**Cải thiện:** tách test invocation khỏi test completion, dùng CompletableFuture do test kiểm soát.

### Anti-pattern H: cho rằng test handler pass nên bảo mật đầy đủ

Pointcut có thể bỏ sót protected operation hoặc target vẫn được gọi trực tiếp ngoài proxy.

**Cải thiện:** integration/architecture tests xác minh interception coverage và domain invariants trên các đường quan trọng.

## 22. Ma trận test cho các loại Advice thường gặp

| Loại advice | Test logic độc lập với weaver | Cần test weaving riêng |
| --- | --- | --- |
| Logging | Event, level, outcome, sanitize, sink failure | Những operation nào được log |
| Metrics | Counter/histogram, duration, sampling, dedup | Không đo trùng khi nhiều aspect |
| Tracing | Start/end, span status, scope close | Parent/child binding và order |
| Authorization | ALLOW/DENY, no proceed on deny, resource scope | Protected methods đều bị chặn |
| Retry | Attempt count, backoff, exception classification | Join points an toàn cho retry |
| Transaction boundary | Begin/commit/rollback contract, cleanup | Advice order và phạm vi thật |
| Caching | Hit/miss, key, TTL, invalidation | Những method được cache |
| Rate limiting | Permit/reject/release, timeout | Boundary và identity/key binding |
| Async completion | Return vs completion, failure, cancellation | Binding callback tới lời gọi thật |
| Audit | Event meaning, identity, durability policy | Event phát ở đúng business milestone |

Không phải mọi loại concern đều phù hợp để đưa vào aspect. Một business invariant quan trọng có thể cần được kiểm tra trong domain/storage boundary thay vì chỉ dựa vào advice được chọn bằng pointcut.

## 23. Rà soát thiết kế trước khi áp dụng

**Bước 1:** viết một bản mô tả đầu vào, đầu ra, exception và side effect cho advice. Quy định đây là observer, guard, retry hay transaction manager.

**Bước 2:** tách phần weaving-specific thành adapter mỏng. Không để handler truy cập trực tiếp quá nhiều API của trình dệt.

**Bước 3:** tạo interface nhỏ cho proceed, clock, event sink, policy/context và scheduler nếu cần.

**Bước 4:** thiết kế test doubles chủ động: fake invocation trả value/throw, clock trả dãy mốc, sink ghi list, policy trả allow/deny.

**Bước 5:** kiểm thử các nhánh chính và đường lỗi: success, exception, denial, observer failure, cleanup, null result, retry, nested calls.

**Bước 6:** bổ sung test state/concurrency/async nếu logic advice liên quan. Dùng controlled executor và coordination primitive thay vì sleep.

**Bước 7:** triển khai adapter cho cơ chế AOP đã chọn, kiểm thử riêng việc chuyển dữ liệu và exception.

**Bước 8:** chạy ít nhất một integration test với weaving thật để xác minh pointcut, order, instantiation và một số đường bypass.

**Bước 9:** kiểm thử end-to-end cho operation có side effect hoặc invariant quan trọng.

**Bước 10:** giữ tốc độ của tầng unit test để team có thể chạy thường xuyên; chỉ tăng số test weaving khi có rủi ro thực sự, không thay mọi test bằng integration.

## 24. Checklist hoàn thành một Advice có thể kiểm thử

- [ ] Logic advice có thể được gọi bằng interface thông thường mà không nạp weaver.
- [ ] Invocation giả có thể trả result, ném exception và đếm proceed.
- [ ] Result và exception gốc được bảo toàn theo contract.
- [ ] Deny/circuit-break/cache-hit không vô tình gọi target.
- [ ] Retry có attempt count, idempotency và failure semantics rõ.
- [ ] Clock, logger, metric sink và policy có thể thay bằng test doubles.
- [ ] Unit test không dùng sleep để khẳng định duration.
- [ ] Audit/telemetry failure có chính sách phù hợp, không che lỗi bất ngờ.
- [ ] Scope được đóng/khôi phục trong success, exception và early exit.
- [ ] Thread-local hoặc state của aspect không rò giữa các bài test.
- [ ] Async return và completion được kiểm thử theo mốc riêng.
- [ ] Pointcut, adapter, precedence và weaving coverage có integration tests.
- [ ] Một test bảo mật kiểm tra không có đường gọi nguy hiểm bypass enforcement.
- [ ] Không nhầm test logic handler thành bằng chứng rằng aspect đã được gắn vào runtime.
- [ ] Test tập trung vào **nghĩa** của event và policy, không vào chi tiết formatter.

## 25. Ghi nhớ

**Kiểm thử advice độc lập với bộ dệt** là kỹ thuật tách hai loại rủi ro:

1. **Rủi ro xử lý:** code quanh invocation có gọi tiếp đúng số lần, bảo toàn return/throw, cleanup, tính duration, kiểm tra quyền và phát event chính xác hay không.
2. **Rủi ro gắn kết:** pointcut có chọn đúng join point, adapter có binding đúng, weaving có hiệu lực, precedence và mô hình tạo aspect có phù hợp hay không.

Đưa xử lý có thể tái sử dụng vào một handler được gọi trực tiếp giúp test nhanh, xác định và dễ ép các nhánh khó như sink failure hoặc authorization DENY. **Sau đó vẫn phải kiểm thử bằng cơ chế AOP thật** ở những ranh giới quan trọng: logic đúng mà không được weave thì không có tác dụng; pointcut đúng nhưng advice logic sai cũng không an toàn.

Đây là cách đạt cả **khả năng kiểm thử ở mức đơn vị** lẫn **độ tin cậy của tích hợp AOP** mà không biến mọi bài kiểm thử thành một bài thử hệ thống lớn.
# Thiết kế giao diện cấu hình rõ ràng cho aspect trong AOP

## 1. Vấn đề cần giải quyết

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, một **aspect** đóng gói logic xuyên suốt như logging, metrics, audit, authorization, transaction, cache, validation hay retry. Một **pointcut** lựa chọn những **join point** phù hợp với mô hình của công cụ AOP; **advice** thực hiện hành vi tại các điểm đã chọn.

Khi chỉ có một aspect và một điểm áp dụng cố định, hard-code giá trị có vẻ nhanh:

```text
TraceAspect:
  target = "mọi method"
  enabled = true
  logFullArgs = true
  failureMode = "ignore"
  maxRetry = 5
```

Nhưng ngay khi nhiều nhóm nghiệp vụ cùng dùng logic, cách ấy tạo ra vấn đề:

- Không rõ ai có quyền chọn phạm vi áp dụng.
- Một thay đổi pointcut có thể vô tình áp advice lên logger, audit sink hoặc cả method bảo mật.
- Cấu hình theo chuỗi `"failmode"` dễ sai chính tả mà chỉ phát hiện lúc chạy.
- “Tắt logging” bị hiểu nhầm là “tắt validation bắt buộc”.
- Caller không biết một lỗi audit có chặn nghiệp vụ hay không.
- Các aspect dùng chung helper nhưng tự hiểu khác nhau về thứ tự, exception, timeout.
- Cập nhật config giữa các thread có thể làm một invocation thấy nửa cũ nửa mới.
- Giá trị mặc định có thể vô tình thay đổi contract khi nâng cấp.
- Chỉ nhìn file cấu hình không đủ biết class nào đã được weave.

**Giao diện cấu hình aspect rõ ràng** là một hợp đồng định nghĩa **những lựa chọn hợp lệ**, **ý nghĩa**, **mặc định**, **giới hạn**, **thời điểm có hiệu lực** và **đường kiểm chứng** của từng lựa chọn, sao cho việc thay đổi cấu hình không tạo hành vi bất ngờ.

Trong bài này, “giao diện” có thể là Java typed API, record/configuration object, properties/XML/YAML có schema, builder, một API quản trị hoặc một biểu thức pointcut được công cụ hỗ trợ. **Không có một định dạng cấu hình thống nhất cho mọi engine AOP.** Mục tiêu là thiết kế contract độc lập với công cụ, rồi ánh xạ chính xác sang cơ chế can thiệp thực tế.

## 2. Mục tiêu học tập

Kết thúc bài, người học có thể:

1. Phân chia cấu hình aspect thành **phạm vi**, **hành vi**, **thứ tự**, **lifecycle** và **vận hành**.
2. Thiết kế các **kiểu có ý nghĩa**, enum, immutable value object và các điều kiện kiểm tra hợp lệ.
3. Phân biệt cấu hình một **pointcut** với cấu hình **policy của advice**.
4. Mô tả rõ hành vi mặc định, trạng thái disabled và failure modes.
5. Quản lý cấu hình của **abstract aspect** và những concrete aspects tái sử dụng hành vi chung.
6. Không nhầm tính năng **proxy interception** với **compile-time/load-time weaving**.
7. Hiểu vì sao precedence, retry, timeout, context và log masking thuộc contract.
8. Thiết kế và kiểm thử cập nhật cấu hình an toàn khi có concurrent invocation.
9. Biết giới hạn của cấu hình pointcut qua XML ở một công cụ có hỗ trợ.
10. Viết một ví dụ Java 17 runnable để kiểm tra cấu hình typed, lựa chọn operation, best-effort/fail-closed, đường ngoại lệ và bypass.

## 3. Một giao diện cấu hình tốt phải trả lời điều gì?

Một bản mô tả config cần có ít nhất:

| Lĩnh vực | Câu hỏi |
| --- | --- |
| Identity | Cấu hình thuộc aspect nào? Có version và owner không? |
| Applicability | Operation/join point nào được chọn? Bao gồm/exclude gì? |
| Binding | Advice cần args, target, signature, annotation hay runtime context nào? |
| Behavior | Advice chỉ quan sát hay được chặn, sửa args, retry, trả fallback? |
| Failure | Lỗi của dependency phụ trợ có ảnh hưởng return/exception target không? |
| Ordering | Nếu nhiều aspect cùng match, ai ở ngoài/ở trong? |
| Lifecycle | Config là immutable, per instance, per request hay global? |
| Defaults | Không cung cấp option thì hành vi cụ thể là gì? |
| Validation | Giá trị nào hợp lệ, kiểm tra ở lúc nào? |
| Security | Ai được sửa scope hoặc disable aspect? Có dữ liệu nhạy cảm không? |
| Change model | Config áp ngay, chỉ với invocation mới hay phải restart/reweave? |
| Evidence | Có cách xem *effective configuration* và kiểm tra coverage không? |

**Điểm mấu chốt:** một giao diện được gọi là rõ ràng khi *người dùng không cần đọc implementation để hiểu hậu quả hành vi*. Tên `enabled` hoặc `timeout=1000` không đủ nếu không biết **enable cái gì**, **1000 đơn vị gì**, và nó được áp ở đâu.

## 4. Phân tách năm nhóm cấu hình

### 4.1. Cấu hình phạm vi

Ví dụ:

```text
aspectId = order-tracing
joinPointKind = method-execution
include = OrderService.submit, OrderService.cancel
exclude = TraceSink.write
boundary = woven-method-execution
```

Đây là schema minh họa, **không phải cú pháp cấu hình của một công cụ AOP cụ thể**.

Định nghĩa phạm vi cần biết **join-point kind** và **interception boundary**. Một câu “áp cho mọi service” không đủ xác nhận runtime coverage.

### 4.2. Cấu hình hành vi

```text
emitStart = true
emitSuccess = true
emitFailure = true
captureArguments = allowlisted-fields-only
onObserverFailure = BEST_EFFORT
```

Các lựa chọn này không quyết định method có match pointcut hay không; chúng quyết định **advice làm gì khi đã được kích hoạt**.

### 4.3. Cấu hình thứ tự

```text
outermost: Authorization
middle: Transaction
innermost: DiagnosticTrace
```

Đây là sơ đồ precedence dự kiến, không phải lời khẳng định engine nào cũng hỗ trợ cùng cú pháp. Vị trí của advice ảnh hưởng chuyện có thấy lỗi, thấy kết quả đã biến đổi, hoặc có bị short-circuit không.

### 4.4. Cấu hình lifecycle và context

```text
configScope = application-snapshot
invocationState = per-invocation
traceContext = propagate-with-task
guardContext = local-emission-only
```

Đừng trộn **configuration data** vốn tương đối ổn định với **state của một invocation** như start time, current depth hoặc correlation ID.

### 4.5. Cấu hình vận hành

```text
observerTimeout = PT250MS
maxAttempts = 1
maxEventBytes = 4096
failurePolicy = BEST_EFFORT
```

Đây là các **ví dụ giá trị** để minh họa ý nghĩa trường, **không phải khuyến nghị mặc định áp dụng cho mọi hệ thống**. Cần chọn số từ nhu cầu nghiệp vụ, chi phí thực tế và mô hình lỗi.

## 5. Nguyên tắc thiết kế: tách selection khỏi policy

Một cấu trúc tốt có thể gồm:

```text
AspectDefinition
  |
  +-- SelectionSpec
  |     joinPointKind
  |     includeRules
  |     excludeRules
  |     dynamicConditions
  |
  +-- AdvicePolicy
  |     enabled
  |     eventKinds
  |     failureMode
  |     transformOrObserve
  |
  +-- OrderingSpec
  |     relativePrecedence
  |
  +-- RuntimeSpec
        timeouts
        sampling
        contextPropagation
        lifecycle
```

**Selection** trả lời “ở đâu”; **policy** trả lời “làm gì”.

Tách riêng có lợi:

- Có thể tái sử dụng cùng audit behavior cho Order và Payment với selection khác nhau.
- Có thể giữ nguyên pointcut nhưng thay cách ghi event.
- Có thể review thay đổi scope như thay đổi về coverage.
- Có thể review thay đổi exception/fallback như thay đổi hợp đồng API.
- Có thể khóa một số lựa chọn trong profile production mà vẫn cho phép đổi sampling.

### 5.1. Những option dễ đặt sai nhóm

```text
enableAudit = false
```

Câu này mơ hồ. Nó có thể có nghĩa:

1. Không weave audit aspect.
2. Pointcut không chọn invocation nào.
3. Advice vẫn chạy nhưng không ghi event.
4. Ghi event nội bộ nhưng không gửi sink.
5. Chỉ tắt metrics, giữ audit bắt buộc.

Giao diện rõ nên dùng tên/hợp đồng riêng cho các ý nghĩa này, ví dụ `auditSinkEnabled`, `traceSamplingEnabled`, `aspectScopeEnabled`, và giới hạn quyền tắt bảo vệ bắt buộc.

## 6. Chọn kiểu dữ liệu thay vì chuỗi mơ hồ

Ví dụ cấu hình kém:

```text
mode = "beSt-effrot"
retry = "-2"
timeout = "100"
scope = "*"
```

Nếu mọi thứ là `String`, lỗi có thể xuất hiện xa nơi người vận hành nhập cấu hình.

Phương án cải thiện:

- `enum FailureMode { BEST_EFFORT, FAIL_CLOSED }`.
- `Duration` cho timeout, kèm ràng buộc dương và giới hạn.
- Số nguyên đã validate cho max attempts.
- `Set<OperationId>` thay cho một chuỗi ngăn cách bằng dấu phẩy không rõ escaping.
- `boolean` cho các option thật sự hai trạng thái.
- Một object `SelectionSpec` mô tả include/exclude rõ.
- Một enum `ConfigStage` khi cần phân biệt compile/weave/load/runtime.

### 6.1. Không phải mọi boolean đều dễ hiểu

```text
strict = true
```

“Strict” nghĩa là gì? Có thể là validation nghiêm, audit fail-closed, điểm chọn hẹp, hoặc chống fallback.

Tên tốt hơn:

```text
rejectInvalidArguments = true
onAuditSinkFailure = FAIL_CLOSED
allowFallback = false
```

Dù vậy, muốn hiểu đúng vẫn phải có **tài liệu ngữ nghĩa**, không chỉ tên biến đẹp.

### 6.2. Dùng đơn vị rõ ràng

```text
timeoutMillis = 500
```

tốt hơn `timeout=500`; nhưng với Java API, `Duration.ofMillis(500)` còn truyền đạt đơn vị rõ và hỗ trợ kiểm hợp lệ.

Một config typed nên từ chối `Duration.ZERO` hoặc âm nếu timeout bắt buộc dương, thay vì chấp nhận rồi biến thành “không timeout” không có tài liệu.

## 7. Immutable configuration và snapshot nhất quán

Một config thường được đọc rất nhiều lần. Nếu thay từng field trên object dùng chung:

```text
Thread A: reads enabled=true
Thread B: sets failureMode=FAIL_CLOSED
Thread A: reads failureMode=FAIL_CLOSED
Thread B: sets enabled=false
```

một invocation có thể thấy tổ hợp trạng thái **chưa bao giờ được công bố như một phiên bản config hoàn chỉnh**.

Cách thiết kế an toàn hơn:

1. Đọc input cấu hình thô.
2. Parse và validate **toàn bộ**.
3. Tạo một immutable `AspectConfig`.
4. Công bố atomically một reference tới config mới.
5. Mỗi invocation lấy **một snapshot** khi bắt đầu và dùng xuyên suốt.

Trong Java, một `record` với các component immutable/được copy phù hợp giúp làm object cấu hình rõ hơn. Tuy nhiên **record chỉ shallowly immutable**: nếu chứa `Set` hoặc `List` mutable do caller giữ, cần defensive copy như `Set.copyOf`.

### 7.1. Config immutable khác invocation state

Không đặt `currentDepth`, `startedAt`, `lastException` hoặc `retryAttempt` vào `AspectConfig`. Chúng thuộc mỗi lần gọi, có vòng đời khác.

### 7.2. Atomic publication không sửa được mọi thứ

Thay reference config atomically không tự thay **điểm đã weave** hoặc rút/đổi method signature. Nó chỉ giúp những behavior **đọc config runtime** nhìn bản snapshot nhất quán. Scope weaving có thể đã được quyết định sớm hơn.

## 8. Kiểm tra giá trị ngay tại ranh giới cấu hình

Một validator nên từ chối:

- `null` trong tập field bắt buộc.
- Tên operation rỗng hoặc chỉ whitespace.
- Duplicate IDs không rõ có cho phép hay không.
- Enum không được hỗ trợ.
- Timeout âm hoặc quá lớn ngoài policy.
- Retry attempts bằng 0/âm khi hợp đồng yêu cầu ít nhất một lần.
- Bật fallback nhưng không có fallback policy hợp lệ.
- Bật audit bắt buộc nhưng không có sink/config credentials cần thiết.
- Phạm vi include/exclude mâu thuẫn theo quy tắc policy.
- Precedence cycle giữa nhiều aspects.
- Cấu hình đòi capture data không được phép.
- Một rule dựa trên feature A nhưng feature A bị tắt.

### 8.1. Parse, validate, activate là ba pha

```text
raw input
   -> parse syntax
   -> semantic validation
   -> construct immutable config
   -> verify compatibility with deployed weaver
   -> publish/activate
```

Parse thành công không có nghĩa **pointcut chọn được join point** hoặc aspect có quyền chạy tại runtime. Validation semantic và integration verification vẫn cần.

### 8.2. Kiểm dependency giữa option

Ví dụ:

```text
if retryEnabled:
    maxAttempts >= 2
    operation must be safe to retry or protected by idempotency
```

Điều kiện thứ hai không thể chứng minh chỉ từ một boolean. Nó cần API metadata/hợp đồng nghiệp vụ hoặc danh sách operation cho phép. Interface tốt không hứa rằng cấu hình đúng cú pháp đồng nghĩa retry an toàn.

## 9. Mặc định phải được công bố, không phụ thuộc tình cờ

Ví dụ một policy tracing có thể chọn:

| Option | Mặc định minh họa | Điều phải giải thích |
| --- | --- | --- |
| enabled | false | Tắt emission hay tắt interception? |
| selected operations | empty set | Không chọn thao tác nào khi chưa khai báo |
| failure mode | BEST_EFFORT | Lỗi observer không làm lỗi business trong phạm vi cho phép |
| argument logging | disabled | Không log toàn bộ dữ liệu đầu vào |
| sampling | 100% hoặc 0% tùy mục tiêu | Đơn vị phần trăm và cách quyết định |
| max attempts | 1 | Không tự retry, tránh nhân đôi side effect |
| output redaction | mandatory | Không cho tắt khi chứa thông tin nhạy cảm |
| config reload | restart-required | Bảo đảm khi nào có hiệu lực |

Đây là **những lựa chọn gợi ý để bàn về contract**, không phải “default đúng cho mọi aspect”. Với authorization, “disabled by default” có thể cực kỳ nguy hiểm; chính sách bảo mật phải được thiết kế trên trust boundary và fail-safe behavior.

### 9.1. Đặt lại mặc định là thay đổi tương thích

Nếu release mới đổi `maxAttempts=1` thành `3`, một operation trước đây chạy một lần có thể chạy đến ba lần khi lỗi. Dù caller không thay config, behavior public **đã thay đổi**.

Vì vậy version của config schema và các giá trị mặc định phải thuộc release notes.

## 10. Scope: cấu hình chỉ định join-point kind thật sự

Một câu `include="OrderService.*"` chưa nói được:

- Chọn **method call** hay **method execution**?
- Có tính constructor, field access, getter không?
- Có method private/final/static không?
- Có self-invocation không?
- Target binary có nằm trong weaving scope không?
- Có runtime guard dựa trên args/annotation không?
- Có lựa chọn method inherited/bridge/generic không?

**Không chuẩn hóa các câu hỏi này bằng suy đoán.** Một mô hình AOP có thể hỗ trợ call sites, một mô hình khác chỉ intercept interface proxy, mô hình khác có bytecode weaving.

### 10.1. Hai chiều coverage

1. **Pointcut match:** logic chọn join point có đúng không?
2. **Execution reachability:** invocation có thực sự đi qua boundary được can thiệp không?

Với proxy interface, target được tạo bằng `new` và dùng trực tiếp có thể bỏ qua checker. Với compile-time weaving vào execution body, phạm vi có thể khác.

### 10.2. Include/exclude và ưu tiên

Nếu cùng một operation nằm trong `include` và `exclude`, config phải quy định kết quả. Một quy tắc dễ giải thích là **exclude thắng include**, nhưng không tự nhận mọi tool dùng thứ tự này.

Nếu dùng matcher phức tạp, cần có API mô tả match result và lý do:

```text
operation=OrderService.cancel
selected=false
reason=excluded-by-audit-internals
```

Ví dụ là output chẩn đoán thiết kế, không phải output từ một engine cụ thể.

## 11. Cấu hình hành vi advice: observation hay transformation?

Một aspect **quan sát** được kỳ vọng:

```text
Target returns R -> caller receives R
Target throws E -> caller receives E
Target execution count is not changed
```

Nhưng nếu observer ném lỗi, cách triển khai sơ suất có thể phá tính trong suốt. Vì vậy cần option `onObserverFailure` với contract rõ.

Một aspect **thay đổi** hành vi có thể:

- Từ chối trước khi gọi target.
- Sửa args truyền xuống.
- Thay result trả lên.
- Đổi exception thành domain exception.
- Trả fallback.
- Retry `proceed` nhiều lần.
- Điều chỉnh transaction/bảo mật context.

**Không đặt tất cả dưới một option chung `mode=ENABLED`.** Với transformation, mỗi lựa chọn cần ràng buộc bảo toàn API contract và các test tương ứng.

### 11.1. Fallback không chỉ là một giá trị

Nếu target cập nhật dữ liệu nhưng fallback trả `"OK"` sau lỗi từ audit sink, caller có thể hiểu sai giao dịch đã được commit. Cấu hình fallback phải mô tả loại outcome, thời điểm sử dụng và trạng thái thật đã xác minh được.

### 11.2. Retry không phải một tính năng logging

Chọn `retryAttempts=3` có thể nhân side effects, độ trễ và số event. Nó cần semantics riêng: loại lỗi được retry, backoff, idempotency, transaction boundary, cancellation và time budget. Đừng đặt retry vào tracing aspect chỉ vì cơ chế quanh-advice hỗ trợ `proceed` nhiều lần.

## 12. Error modes: BEST_EFFORT và FAIL_CLOSED

### 12.1. BEST_EFFORT

Một observer phụ trợ như metrics exporter có thể thất bại nhưng caller vẫn nhận outcome target. Policy:

```text
On observer error:
  record a safe local diagnostic
  do not alter target return/exception
  do not re-run target
```

Cần giới hạn: nếu helper ghi diagnostic lại dùng chính sink hỏng, có thể tạo recursion; nếu target chưa chạy, việc observer thất bại vẫn cần policy rõ.

### 12.2. FAIL_CLOSED

Khi không hoàn thành bước bắt buộc trước target, một policy có thể **từ chối thực hiện target**. Ví dụ ghi audit trước khi thực hiện thao tác nhạy cảm được yêu cầu bởi nghiệp vụ.

```text
On mandatory pre-operation audit failure:
  do not execute target
  propagate a documented failure
```

**Không tự suy rằng FAIL_CLOSED luôn rollback.** Nếu bắt lỗi phụ trợ xảy ra **sau khi target chạy**, caller có thể nhận exception trong khi side effect đã xảy ra. Hợp đồng phải chia theo **phase**.

### 12.3. Đừng bắt tất cả RuntimeException rồi gọi là observer error

Ví dụ sai:

```text
try:
    emitStart()
    result = target()
    emitSuccess()
    return result
catch anyError:
    if bestEffort: return fallbackSuccess
```

Catch trên bao cả **business error** và observer error; hành vi best-effort có thể nuốt lỗi nghiệp vụ. Cần giới hạn phạm vi catch tới đúng call observer, và truyền business error theo hợp đồng.

## 13. Ví dụ Java 17 chạy được: cấu hình typed, immutable và hai failure modes

Ví dụ sau không dùng weaver bên ngoài. Nó là một **interceptor/decorator viết bằng Java**, minh họa **cách thiết kế interface cấu hình**, không phải một abstract aspect hay pointcut compiler.

Các cấu hình:

- `AspectConfig` là Java record và copy tập operation thành set immutable.
- `FailureMode` là enum, không nhận chuỗi tùy ý.
- `enabled` quyết định có áp wrapper behavior hay không.
- `selected` là tập operation được aspect áp dụng.
- `traceEnabled` quyết định có gửi event sang observer hay không.
- Lỗi observer dưới `BEST_EFFORT` được xử lý trong **chính hàm emit**, không nuốt business exception.
- `FAIL_CLOSED` cho phép lỗi observer trước target chặn lời gọi.
- Direct target call bỏ qua wrapper.
- Một config invalid bị từ chối khi tạo, trước khi chạy nghiệp vụ.

Tạo file `AspectConfigDemo.java`:

```java
import java.util.Objects;
import java.util.Set;

public class AspectConfigDemo {
    enum FailureMode {
        BEST_EFFORT,
        FAIL_CLOSED
    }

    record AspectConfig(
            boolean enabled,
            Set<String> selected,
            boolean traceEnabled,
            FailureMode failureMode) {

        AspectConfig {
            Objects.requireNonNull(selected, "selected");
            Objects.requireNonNull(failureMode, "failureMode");
            selected = Set.copyOf(selected);

            for (String operation : selected) {
                if (operation.isBlank()) {
                    throw new IllegalArgumentException(
                            "selected contains blank operation");
                }
            }
        }
    }

    @FunctionalInterface
    interface Work {
        String run(String operation);
    }

    @FunctionalInterface
    interface Observer {
        void emit(String event);
    }

    static void emit(AspectConfig config,
                     Observer observer,
                     String event) {
        if (!config.traceEnabled()) {
            return;
        }

        try {
            observer.emit(event);
        } catch (RuntimeException error) {
            if (config.failureMode() == FailureMode.FAIL_CLOSED) {
                throw error;
            }
            System.out.println("aspect:observer-failure:" + event);
        }
    }

    static Work configured(
            Work target, AspectConfig config, Observer observer) {
        Objects.requireNonNull(target, "target");
        Objects.requireNonNull(config, "config");
        Objects.requireNonNull(observer, "observer");

        return operation -> {
            if (!config.enabled()
                    || !config.selected().contains(operation)) {
                return target.run(operation);
            }

            System.out.println("aspect:enter:" + operation);
            try {
                emit(config, observer, "start:" + operation);

                String result;
                try {
                    result = target.run(operation);
                } catch (RuntimeException businessError) {
                    System.out.println("aspect:business-error:"
                            + operation + ":"
                            + businessError.getClass().getSimpleName());
                    emit(config, observer, "error:" + operation);
                    throw businessError;
                }

                emit(config, observer, "success:" + operation);
                System.out.println("aspect:return:" + operation);
                return result;
            } finally {
                System.out.println("aspect:exit:" + operation);
            }
        };
    }

    static void call(String label, Work work, String operation) {
        System.out.println("case:" + label);
        try {
            System.out.println("caller:" + work.run(operation));
        } catch (RuntimeException error) {
            System.out.println("caller:error:"
                    + error.getClass().getSimpleName()
                    + ":" + error.getMessage());
        }
    }

    public static void main(String[] args) {
        Work target = operation -> {
            System.out.println("business:" + operation);
            if ("FAIL".equals(operation)) {
                throw new IllegalStateException("operation failed");
            }
            return "ok:" + operation;
        };

        Observer observer = event -> {
            if ("start:FAULT".equals(event)) {
                throw new IllegalStateException("sink offline");
            }
            System.out.println("observer:" + event);
        };

        Set<String> selected =
                Set.of("SAVE", "FAIL", "FAULT");

        AspectConfig bestEffort = new AspectConfig(
                true, selected, true, FailureMode.BEST_EFFORT);
        AspectConfig failClosed = new AspectConfig(
                true, selected, true, FailureMode.FAIL_CLOSED);
        AspectConfig disabled = new AspectConfig(
                false, selected, true, FailureMode.FAIL_CLOSED);

        Work managed = configured(target, bestEffort, observer);
        Work strict = configured(target, failClosed, observer);
        Work noAdvice = configured(target, disabled, observer);

        call("selected", managed, "SAVE");
        call("unselected", managed, "SKIP");
        call("business-error", managed, "FAIL");
        call("best-effort-sink", managed, "FAULT");
        call("fail-closed-sink", strict, "FAULT");
        call("disabled", noAdvice, "SAVE");
        call("direct-target", target, "SAVE");

        System.out.println("case:invalid-config");
        try {
            new AspectConfig(
                    true, Set.of(" "),
                    true, FailureMode.BEST_EFFORT);
        } catch (IllegalArgumentException error) {
            System.out.println("config:error:" + error.getMessage());
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AspectConfigDemo.java
java AspectConfigDemo
```

**Stdout chính xác cho chương trình:**

```text
case:selected
aspect:enter:SAVE
observer:start:SAVE
business:SAVE
observer:success:SAVE
aspect:return:SAVE
aspect:exit:SAVE
caller:ok:SAVE
case:unselected
business:SKIP
caller:ok:SKIP
case:business-error
aspect:enter:FAIL
observer:start:FAIL
business:FAIL
aspect:business-error:FAIL:IllegalStateException
observer:error:FAIL
aspect:exit:FAIL
caller:error:IllegalStateException:operation failed
case:best-effort-sink
aspect:enter:FAULT
aspect:observer-failure:start:FAULT
business:FAULT
observer:success:FAULT
aspect:return:FAULT
aspect:exit:FAULT
caller:ok:FAULT
case:fail-closed-sink
aspect:enter:FAULT
aspect:exit:FAULT
caller:error:IllegalStateException:sink offline
case:disabled
business:SAVE
caller:ok:SAVE
case:direct-target
business:SAVE
caller:ok:SAVE
case:invalid-config
config:error:selected contains blank operation
```

### 13.1. Vì sao dùng record và `Set.copyOf`?

`AspectConfig` có các component được gắn như state cuối của record. Trong compact constructor, `Set.copyOf(selected)` tạo một tập không thể sửa qua reference trả về. Nếu caller ban đầu có một `HashSet` rồi sửa nó, config đã tạo không phải tự đổi theo.

Cần ghi nhớ: immutable container không đồng nghĩa immutable mọi element. Với `Set<String>`, `String` immutable nên phù hợp. Nếu selected chứa object mutable, cần xem defensive copy sâu/identity semantics.

### 13.2. Vì sao selected=SKIP không có advice?

Operation `"SKIP"` không thuộc `Set.of("SAVE","FAIL","FAULT")`, nên wrapper chuyển tiếp thẳng đến target. Điều đó mô phỏng **điều kiện lựa chọn runtime**. Trong một engine có pointcut DSL, matching có thể diễn ra ở giai đoạn compile/weave khác.

### 13.3. Vì sao lỗi nghiệp vụ không bị nuốt trong BEST_EFFORT?

`target.run("FAIL")` ném `IllegalStateException`. Nó được bắt ở khối try **chỉ bao target**, ghi phân loại `business-error` rồi ném lại lỗi gốc. `emit` chỉ bắt lỗi phát sinh từ `observer.emit`.

Một interface cấu hình ghi `BEST_EFFORT` phải nói rõ **best effort của observer**, chứ không có nghĩa “nuốt mọi exception trong chuỗi AOP”.

### 13.4. Vì sao FAULT khác nhau giữa hai chế độ?

Observer cố ý ném `IllegalStateException("sink offline")` ở sự kiện `start:FAULT`.

- Với **BEST_EFFORT**, emit bắt lỗi và in `aspect:observer-failure:start:FAULT`; business vẫn thực thi và caller nhận `ok:FAULT`.
- Với **FAIL_CLOSED**, lỗi phát ra trước target nên caller nhận lỗi sink, **không có dòng `business:FAULT` ở ca này**.

Việc in dòng `aspect:exit:FAULT` trên đường fail-closed là do `finally` bao toàn bộ khối trong wrapper. Nó không chứng minh business đã chạy.

### 13.5. Disabled và direct target

Trường hợp disabled trả về từ wrapper ngay qua nhánh không áp advice. Trường hợp direct target hoàn toàn không dùng wrapper. Output giống nhau, nhưng nguyên nhân khác:

- Disabled: lời gọi đi qua wrapper, policy nói bỏ instrumentation.
- Direct: lời gọi không đi qua wrapper.

Trong production, đặc biệt với authorization hoặc validation bắt buộc, cả hai đường cần chính sách bảo vệ rõ.

### 13.6. Không coi ví dụ Java này là một AOP engine

Nó **không** tự chọn method execution/call join points từ bytecode, không hỗ trợ pointcut DSL, không weave class, không xử lý self-invocation/proxy infrastructure hay multiple-advice precedence. Nó chỉ cho thấy **một thiết kế giao diện cấu hình hợp lệ, typed và có thể kiểm thử**.

### 13.7. Giới hạn failure modes của demo

Nếu observer trên đường `success` ném lỗi dưới FAIL_CLOSED, business có thể đã hoàn tất nhưng caller sẽ nhận exception. Đây là hậu quả quan trọng cần ghi trong hợp đồng. Một giao diện production có thể phải phân tách lỗi ở **before**, **after normal return** và **after exceptional completion** thay vì dùng cùng một `FailureMode` cho cả ba giai đoạn.

## 14. Cấu hình như một phần của hợp đồng public API

Một config có thể đổi behavior caller nhìn thấy mà **không đổi chữ ký method**.

Ví dụ:

- Từ `BEST_EFFORT` sang `FAIL_CLOSED`: một lỗi sink mới có thể chặn target.
- Từ `maxAttempts=1` sang `3`: operation có thể chạy nhiều lần.
- Từ `traceEnabled=false` sang `true`: có thêm I/O/latency và rủi ro dữ liệu nhạy cảm.
- Đổi pointcut: một method trước đây không được advice giờ bị từ chối bởi validation.
- Đổi precedence: một authorization advice có thể chạy trước transaction thay vì sau.
- Đổi default sampling: số event/chi phí và khả năng audit thay đổi.
- Đổi exception translation: caller phải xử lý loại lỗi mới.
- Đổi scope từ execution sang call: coverage và self-invocation có thể thay đổi.

**Đừng xem config là “chuyện nội bộ” nếu nó thay lời hứa public.** Version hóa và review nó như thay đổi API/behavior.

## 15. Giao diện cấu hình cho abstract aspect và concrete aspect

Khi dùng một **abstract aspect** để tái sử dụng phần hành vi chung:

```text
AbstractAudit:
  abstract selectOperations()
  common audit-before/after/throw logic

OrderAudit extends AbstractAudit:
  selectOperations = Order-related join points

PaymentAudit extends AbstractAudit:
  selectOperations = Payment-related join points
```

Base aspect cung cấp hợp đồng ổn định, concrete aspect cung cấp phạm vi/chính sách chuyên biệt.

Một mô hình config rõ có thể tách:

```text
SharedAuditConfig:
  event schema
  redaction
  sink behavior
  error mode

OrderAuditSelection:
  order scope include/exclude

PaymentAuditSelection:
  payment scope include/exclude
```

### 15.1. Đừng biến base aspect thành “god aspect”

Nếu base vừa chọn mọi operation, vừa quyết định authorization, transaction, retry, log formatter, error translation và sink configuration, mọi concrete aspect sẽ bị coupling với quá nhiều điều không liên quan.

Nên để base thể hiện những **bất biến của behavior dùng chung**, còn các chính sách tùy biến ở những component/hook/strategy rõ ràng.

### 15.2. Một abstract pointcut là một phần của config contract

Ở ngôn ngữ hỗ trợ, concrete aspect có thể hiện thực abstract pointcut bằng biểu thức lựa chọn khác. Cần biết:

- Pointcut có tham số/binding hay không.
- Có cho phép execution/call/constructor hay chỉ một tập join-point kind?
- Các dynamic guards có ý nghĩa gì?
- Mỗi concrete aspect được kích hoạt theo lifecycle nào?
- Có bao nhiêu concrete aspects có thể chọn cùng một method?
- Precedence giữa chúng được công bố ở đâu?

Một pointcut biến thiên là **configuration boundary có hậu quả đúng đắn**, không chỉ là nơi để tùy ý viết wildcard.

## 16. Ví dụ cấu hình công cụ cụ thể: AspectJ và `aop.xml`

Một khả năng của **AspectJ load-time weaving** là dùng `META-INF/aop.xml` để xác định những aspects được dùng, những types được weave và một số option của weaver.

Phần này **chỉ minh họa cú pháp của công cụ đó**. Nó không phải định dạng cấu hình AOP chung và không thể chạy chỉ với `javac`.

Ví dụ abstract aspect theo cú pháp **AspectJ code-style**:

```java
package demo;

public abstract aspect AbstractTrace {
    public abstract pointcut scope();

    before(): scope() {
        System.out.println("trace:before");
    }
}
```

Một file `META-INF/aop.xml` minh họa:

```xml
<aspectj>
  <aspects>
    <concrete-aspect
        name="demo.ConfiguredOrderTrace"
        extends="demo.AbstractTrace">
      <pointcut
          name="scope"
          expression="execution(* demo.OrderService.*(..))"/>
    </concrete-aspect>
  </aspects>
  <weaver>
    <include within="demo..*"/>
  </weaver>
</aspectj>
```

Ý nghĩa:

1. `AbstractTrace` khai báo một abstract pointcut `scope()`.
2. `concrete-aspect` chỉ định một concrete aspect được tạo dựa trên abstract aspect.
3. `pointcut name="scope"` cung cấp biểu thức cụ thể.
4. `weaver/include` giới hạn types được weave, **khác với** biểu thức pointcut.
5. Class `demo.OrderService` cần thực sự tồn tại, và build/deployment phải hỗ trợ weaving.

Không được coi snippet này là một “file cấu hình chạy được ngay” nếu chưa có class target, compiler/weaver, runtime library và VM agent thích hợp.

### 16.1. Những giới hạn quan trọng của cơ chế này

Theo tài liệu chính thức về concrete aspects trong `aop.xml` của AspectJ:

- Parent aspect phải **abstract**.
- Những abstract pointcut được cung cấp theo cơ chế này phải là loại đơn giản **không expose state/bind arguments** như những pointcut có `args()`, `this()`, `target()` hay `if()`.
- Concrete aspect định nghĩa trong XML phải hoàn thành **tất cả abstract pointcuts**.
- Cơ chế XML này không hiện thực arbitrary **abstract methods** của parent aspect; nếu base có abstract methods thì cần mô hình kế thừa bằng code phù hợp.
- Aspect name được dùng tạo một concrete type; không được xung đột với class name đã có.
- Availability và weaving scope phụ thuộc classloader/configuration.
- Muốn inheritance phức tạp, có thể cần **regular aspect inheritance**, thay vì XML.

Đây là giới hạn **công cụ cụ thể**, không phải ràng buộc của mọi cách tổ chức abstract aspects.

### 16.2. Ba lớp lựa chọn khác nhau

Trong ví dụ AspectJ:

- `<aspect>` hoặc `<concrete-aspect>`: **những aspect nào** được giới thiệu cho weaver.
- `<weaver><include .../>`: **những type nào** nằm trong phạm vi weaving.
- `<pointcut expression="..."/>`: **những join point nào** được advice chọn khi weaving/runtime conditions phù hợp.

Tập chọn ở một tầng rộng **không bảo đảm** tầng khác cũng bao phủ. “Pointcut khớp trong lý thuyết” không tương đương “advice chạy trên binary production”.

### 16.3. Khi nào dùng cấu hình theo deployment?

Khi phạm vi weaving/selection thay đổi theo deployment và công cụ hỗ trợ, external configuration có thể tiện. Nhưng những khác biệt ảnh hưởng type binding, argument capture hoặc requirement của advice vẫn có thể buộc thay source/build.

Cần version `aop.xml` cùng artifact, không đổi tùy ý trên production mà không regression test.

## 17. Không trộn cấu hình build-time với runtime feature flags

Một số thuộc tính quyết định **class nào được weave trước khi load**. Một số chỉ là policy được advice đọc **khi invocation xảy ra**.

Ví dụ:

| Thuộc tính | Thường gắn với pha | Hệ quả |
| --- | --- | --- |
| Join-point kind được compiler hỗ trợ | Language/toolchain | Không thể thêm một loại mới chỉ bằng flag |
| Class include/exclude ở load-time weaving | Before class definition | Class đã nạp có thể không được can thiệp lại |
| Pointcut được compile thành advice | Compile/weave | Phải giữ compiler/runtime tương thích |
| Sampling rate của logger | Runtime | Có thể thay nếu advice đã hỗ trợ đọc policy |
| Sink endpoint/timeout | Runtime hoặc startup | Phụ thuộc lifecycle client/sink |
| FailureMode runtime | Invocation snapshot | Thay đổi error behavior quan sát được |
| New interface/method introduction | Structural weaving | Không phải feature flag runtime đơn giản |

### 17.1. Nạp class và giới hạn cập nhật

Đừng hứa “config đổi thì mọi class vừa chạy sẽ được can thiệp ngay”. Trong nhiều mô hình weaving, chỉ những class **chưa được định nghĩa cho VM** mới có thể được biến đổi ở load-time. JVM class redefinition/retransformation có những hạn chế riêng, đặc biệt với **đổi cấu trúc type**.

### 17.2. Snapshot theo invocation

Với runtime-configurable advice, nên có quy tắc:

```text
Each invocation obtains one effective config version on entry.
That version is used until the invocation reaches its documented completion boundary.
```

Nếu async continuation hoàn tất sau này, cần quyết định dùng config snapshot ban đầu hay bản mới khi completion callback chạy. Cả hai có thể hợp lý, nhưng phải **được công bố**.

## 18. Mô hình precedence cần rõ ràng

Khi có nhiều aspect, thứ tự làm thay đổi kết quả.

```text
Authorization(
    Transaction(
        Audit(
            Business
        )
    )
)
```

Theo lồng nhau đó:

- Authorization có thể từ chối trước Transaction.
- Transaction có thể bắt exception từ phần bên trong.
- Audit có thể thấy outcome của Business trước một số biến đổi ở lớp ngoài.
- Cleanup chạy theo phạm vi cụ thể của mỗi advice.
- Nếu Authorization không tiếp tục, Audit không chạy trừ khi một lớp ngoài khác có trách nhiệm ghi rejected attempts.

**Không có một precedence mặc định chung cho mọi AOP engine.** Một giao diện cấu hình nên mô tả quan hệ như `before/after` hoặc một thứ tự tổng đã kiểm tra.

### 18.1. Kiểm chu trình quan hệ

Nếu operator cấu hình:

```text
A before B
B before C
C before A
```

đó là một chu trình ràng buộc. Validator nên từ chối thay vì “chọn đại” một thứ tự.

### 18.2. Precedence giữa abstract và concrete aspects

Với ngôn ngữ có aspect inheritance, có thể có nhiều concrete aspects kế thừa cùng base và cùng chọn một join point. Base được viết một lần **không đồng nghĩa advice chạy một lần**. Config phải nhận diện từng concrete aspect và mô tả overlap/precedence.

## 19. Scope exclusions để tránh aspect tự kích hoạt

Logging advice gọi logger, logger lại có thể khớp pointcut. Với cấu hình quá rộng:

```text
Business.method
  -> TraceAdvice
      -> TraceSink.write
          -> TraceAdvice
              -> TraceSink.write ...
```

Các chiến lược:

1. Chọn scope nghiệp vụ hẹp ngay từ đầu.
2. Loại chính xác logger/audit sink/formatting helpers nếu không cần advice.
3. Dùng lexical exclusion nếu engine hỗ trợ.
4. Dùng control-flow exclusion khi cần phân biệt cùng helper được gọi từ advice và business.
5. Dùng reentrancy guard hẹp theo invocation/scope; cleanup bằng `finally`.
6. Test nested business calls vẫn được instrument nếu chúng thuộc hợp đồng.

Không dùng config đơn giản kiểu `skipAllNestedCalls=true` để chữa recursion mà không hiểu tác động: nó có thể tắt cả audit/authorization của operation lồng nhau hợp lệ.

## 20. Thiết kế thay đổi config an toàn trong nhiều luồng

Một hệ thống có thể muốn đổi sampling hoặc timeout khi đang chạy.

Một trình tự triển khai hợp lý:

```text
Read candidate configuration
  -> Parse
  -> Validate syntax
  -> Validate semantic dependencies
  -> Check security authorization of actor changing config
  -> Build immutable snapshot
  -> Record candidate version
  -> Publish atomically
  -> Observe metrics and rollback if necessary
```

Nếu bất kỳ bước nào thất bại, **giữ config cũ đang có hiệu lực** theo chính sách. Không phát hành nửa config.

### 20.1. Ví dụ Java pseudo-architecture

```java
// Fragment minh họa, không phải chương trình độc lập.
private final java.util.concurrent.atomic.AtomicReference<AspectConfig>
        current = new java.util.concurrent.atomic.AtomicReference<>();

AspectConfig snapshot = current.get();
// Dùng cùng snapshot trong một invocation.

AspectConfig validated = parseAndValidate(candidate);
current.set(validated);
// Publish bản hoàn chỉnh, không sửa field lẻ trên object đã công bố.
```

Lưu ý: đoạn này giả định `AspectConfig` và `parseAndValidate` được định nghĩa ở nơi khác. Việc đặt một AtomicReference chỉ giúp công bố **reference** an toàn; nó không xử lý đồng bộ của sink/retry counters, cũng không tự đổi pointcut đã weave.

### 20.2. Cần version và rollback

Một snapshot nên có version/identifier để log và truy vết, chẳng hạn:

```text
policyId = trace-orders
schemaVersion = 2
revision = 2026-10-20.1
activatedAt = known deployment time
```

Đây là dữ liệu minh họa, không phải bản ghi production thật. Cần giữ quan hệ giữa **source config**, **validated snapshot** và **effective config ở runtime**.

### 20.3. Không hứa strong atomicity của side effects

Nếu đổi endpoint của sink khi đang có event inflight, một phần event có thể đi endpoint cũ, phần khác đi endpoint mới. Atomic swap config không tự bảo đảm việc gửi event, transaction hoặc network I/O là atomic.

## 21. Bảo mật của giao diện cấu hình

Config aspect có thể làm thay đổi một **security boundary**. Do đó:

- Không để người dùng không có quyền tắt authorization aspect.
- Không cho phép pointcut wildcard rộng trên mã chứa dữ liệu nhạy cảm nếu chưa được review.
- Không cho phép bật `logFullArgs` ngoài policy dữ liệu.
- Phân tách quyền thay sampling và quyền đổi fail-open/fail-closed.
- Không ghi secrets trực tiếp trong log config/diagnostics.
- Có audit cho những lần sửa policy quan trọng.
- Validate URI/endpoint/certificates phù hợp trước khi sử dụng.
- Xem config từ nguồn ngoài là input không tin cậy; không nối thẳng vào biểu thức có thể thực thi code tùy ý nếu engine không bảo đảm sandbox.
- Nếu parser hỗ trợ regex, phải đánh giá chi phí, phạm vi và điều kiện tránh catastrophic backtracking.
- Nếu một aspect bảo vệ bất biến cốt lõi, không dựa duy nhất vào toggle có thể bị vô hiệu hóa dễ dàng.

**Configuration is code-like policy** ở những hệ thống mà nó điều khiển quyền, ngoại lệ và phạm vi can thiệp. Review và kiểm thử thay đổi config là một phần phát triển an toàn.

## 22. Cấu hình logging và dữ liệu nhạy cảm

Một interface tốt có thể chỉ cho phép:

```text
captureArguments = NONE | ALLOWLIST
captureResult = STATUS_ONLY
sensitiveFieldPolicy = REDACT
maxRecordedBytes = 4096
```

Không mặc định log `args.toString()` hoặc serialize toàn bộ object graph, vì:

- Có thể lộ token, mật khẩu, thông tin cá nhân.
- `toString()`/getter có thể làm I/O hoặc bị aspect chọn, gây self-interception.
- Object graph lớn/có vòng có thể gây memory/CPU cao.
- Dữ liệu đầu vào có thể chứa nội dung không tin cậy gây log injection.
- Thay đổi serializer có thể tự làm đổi behavior.

### 22.1. Một giới hạn size không thay quy tắc bảo mật

Cắt log xuống 4096 bytes **không làm an toàn** một token nằm ở 32 bytes đầu. Cần masking/redaction đúng trường, trước khi áp size limit hoặc xuất event.

### 22.2. Ghi rõ mức bảo đảm của observer

```text
emitEvent()
```

có thể nghĩa gửi vào bộ đệm, đẩy queue, broker ack hoặc lưu bền vững. Contract phải phân biệt các mốc. Không hứa exactly-once hay durable auditing nếu sink không cung cấp.

## 23. Retry, timeout và idempotency

Đây là nhóm cấu hình dễ gây tác dụng phụ lớn.

### 23.1. Retry attempts

Không chỉ có `maxAttempts`. Cần ít nhất:

- Retry-on exception classification.
- Backoff policy.
- Idempotency condition/key.
- Time budget tổng.
- Cancellation.
- Interaction với transaction.
- Logging mỗi attempt hay mỗi logical request.
- Có thể retry lỗi phát sinh **sau khi business đã hoàn thành** không?

Nếu một after advice ném lỗi sau commit, retry ngoài có thể lặp mutation. Chỉ retry các trường hợp **được chứng minh an toàn**.

### 23.2. Timeout

Cần phân biệt:

- Timeout của việc gửi metric/audit.
- Timeout của business.
- Timeout đợi lock.
- Timeout của Future/task completion.
- Timeout network request.
- Deadline tổng cho một logical operation.

Một timeout exception không tự bảo đảm side effect chưa xảy ra hoặc đã được rollback.

### 23.3. Sampling

Nếu `sampling=10%`, phải nói:

- Là 10% của requests, attempts hay join point invocations?
- Quyết định theo random, hash stable key hay mỗi event?
- Có áp cho failures không?
- Security audit có được sampling không?
- Cách đồng nhất sampling trong distributed trace ra sao?

Không xem sampling là option vô hại nếu consumer/vận hành dựa vào completeness của audit.

## 24. Hợp đồng cấu hình khi có async

Một method có thể trả `CompletableFuture<Result>`:

```text
method execution returns Future
  -> task continues
  -> Future completes later
```

Nếu advice after-returning chạy khi method trả Future, một `emitSuccess=true` có thể chỉ ghi **Future được trả**, không phải công việc hoàn tất.

Giao diện nên nêu:

- `completionBoundary = METHOD_RETURN | ASYNC_COMPLETION` (nếu engine/implementation hỗ trợ).
- Exception nằm ở method invocation hay completion stage?
- Context được truyền qua executor như thế nào?
- Cancellation/timeout có được coi là failure không?
- Snapshot config cũ hay mới dùng khi completion xảy ra?
- Lỗi trong callback quan sát có làm stage mới thất bại không?
- Observer có quyền thay completion result không?

Không đưa enum này vào cấu hình nếu implementation **không thể thực hiện**: option đẹp nhưng không có hiệu lực sẽ tạo contract giả.

## 25. Phân biệt schema config và cú pháp pointcut của công cụ

Một schema độc lập công cụ có thể khai báo:

```yaml
aspect:
  id: order-trace
  enabled: true
  selection:
    kind: METHOD_EXECUTION
    include:
      - OrderService.submit
      - OrderService.cancel
    exclude:
      - InternalTraceSink.write
  behavior:
    traceEnabled: true
    observerFailureMode: BEST_EFFORT
  version: 1
```

**YAML trên chỉ là ví dụ cấu trúc dữ liệu**, không phải schema được AOP engine nào nhận trực tiếp.

Cần một adapter/compiler/translator có trách nhiệm:

1. Parse YAML.
2. Validate config semantics.
3. Ánh xạ `METHOD_EXECUTION` và include/exclude sang pointcut thực sự được hỗ trợ.
4. Xác minh module/class loading/weaving scope.
5. Áp policy runtime phù hợp.
6. Cung cấp diagnostics về **effective selection** và warnings.

**Không đưa một ngôn ngữ pointcut tùy ý vào config string rồi coi đó là một giao diện chuẩn.** DSL có thể có ngữ nghĩa tinh vi về overload, package wildcard, annotation, dynamic conditions, caller/target hoặc control flow.

## 26. Mẫu tài liệu cấu hình có thể tái sử dụng

Một trang reference nên có:

```markdown
# Aspect Configuration Contract

## Identity
- Aspect ID:
- Config schema version:
- Owner:
- Purpose:

## Applicability
- Join-point kinds:
- Include patterns:
- Exclude patterns:
- Dynamic guards:
- Weaving/proxy boundary:
- Known bypass paths:

## Behavior
- Observes or transforms:
- Before behavior:
- Normal completion behavior:
- Exceptional completion behavior:
- Continuation/proceed semantics:
- Return/exception transparency:

## Configuration fields
| Key | Type | Default | Required? | Constraints | Meaning |
| --- | --- | --- | --- | --- | --- |

## Ordering
- Precedence rules:
- Known overlaps:

## State and lifecycle
- Config lifetime:
- Invocation state:
- Concurrent reload semantics:
- Async context and completion boundary:

## Failure semantics
- Observer failure mode:
- Business exception handling:
- Retry/idempotency:
- Timeout:
- Cleanup policy:

## Security and operations
- Who may change:
- Redaction policy:
- Logging/diagnostics:
- Effective config visibility:
- Rollback procedure:

## Compatibility
- Breaking changes:
- Migration:
- Verification tests:
```

Đây là **template cho người triển khai điền giá trị**, không phải một policy cụ thể. Khi công bố artifact production, phải thay tất cả mục trống bằng nội dung có thể kiểm chứng; không coi ô trống là lời hứa mặc định.

### 26.1. Đừng ép quá nhiều option vào một constructor dài

Một constructor 20 boolean khó đọc và dễ truyền nhầm vị trí. Có thể dùng:

- **Typed record nhóm theo chức năng**.
- Builder có validation sau cùng.
- Static factories với tên có ý nghĩa.
- Nhiều cấu hình nhỏ composable.
- Enum thay cho cụm boolean mâu thuẫn.

Nhưng builder không sửa được semantic contract kém: tên rõ, default rõ và tổ hợp hợp lệ vẫn cần thiết.

## 27. Đánh giá một API cấu hình kém và cách cải thiện

### 27.1. Cách làm mơ hồ

```java
configure("*", true, false, 3, 250, "ignore");
```

Vấn đề:

- `"*"` match cái gì?
- `true/false` chỉ những chính sách nào?
- `3` là số attempt hay số event?
- `250` là milliseconds hay seconds?
- `"ignore"` bỏ lỗi observer hay lỗi business?
- Config áp trên mọi target hay chỉ proxy?
- Không có constraints.

### 27.2. Tường minh hơn

```java
// Fragment minh họa API; không phải chương trình độc lập.
AspectConfig config = new AspectConfig(
    true,
    Set.of("SAVE", "CANCEL"),
    true,
    FailureMode.BEST_EFFORT
);
```

Mẫu này cải thiện thông qua kiểu `Set<String>` và enum, nhưng vẫn còn điểm yếu: ba tham số boolean/string không nêu rõ trong call site nếu người đọc không mở constructor. Với API lớn, builder/static factories hoặc cấu hình record phân nhóm sẽ dễ đọc hơn.

### 27.3. Tính nhất quán quan trọng hơn số dòng

```text
selectionPolicy = selected business mutations
observerPolicy = best effort
capturePolicy = status only
reloadPolicy = invocation snapshot
```

Một cấu hình có thêm vài dòng nhưng giảm khả năng hiểu nhầm sẽ tiết kiệm nhiều chi phí bảo trì hơn một hàm ngắn khó đọc.

## 28. Những lỗi cấu hình thường gặp

**“enabled=false nghĩa toàn bộ code được bảo vệ vẫn an toàn.”** Không. Nếu advice cung cấp validation/authorization bắt buộc, tắt nó có thể bỏ protection.

**“Pointcut khớp nghĩa advice luôn chạy.”** Không nếu class chưa được weave, caller đi vòng proxy, guard sai hoặc continuation bị short-circuit.

**“Mọi option đều đổi được nóng.”** Không. Weaving/class loading và thay type structure có những giới hạn.

**“Config record luôn immutable sâu.”** Không. Những component chứa collections mutable cần defensive copy.

**“BEST_EFFORT nghĩa nuốt mọi lỗi.”** Không. Nó phải được giới hạn ở chính dependency phụ trợ được định nghĩa.

**“FAIL_CLOSED nghĩa mọi mutation được rollback.”** Sai. Nếu failure phát sinh sau side effect, state có thể đã thay đổi.

**“Timeout ném exception nghĩa server chưa làm gì.”** Không. Kết quả có thể chưa xác định.

**“Retry=3 chỉ ảnh hưởng độ trễ.”** Sai. Nó có thể nhân side effects và số lần audit.

**“Thêm option mới với default an toàn là luôn backward compatible.”** Không nếu default đổi behavior được consumer/vận hành dựa vào.

**“Log full args giúp debug tốt hơn nên luôn bật.”** Không. Có rủi ro lộ dữ liệu, vòng instrumentation và overhead.

**“Precedence có thể đoán từ tên class.”** Không nên. Phải công bố hoặc cấu hình khi engine hỗ trợ.

**“Một chính sách áp cho tất cả concrete aspects vì chúng cùng extends base.”** Không. Từng concrete pointcut và lifecycle có thể khác.

**“YAML là cấu hình AOP chuẩn.”** Không. Nó chỉ có hiệu lực nếu có adapter/engine được xây để hiểu schema đó.

**“Chỉ cần test parse config.”** Không. Cần cả tests actual selection, return/throw, side effects, concurrency và deployment.

**“Một global boolean là cách dễ nhất để dynamic enable.”** Nguy hiểm. Nó gây race, không đảm bảo per-invocation snapshot, và có thể thay đổi security boundary.

## 29. Ma trận kiểm thử cấu hình

| Test | Điều cần kiểm |
| --- | --- |
| Thiếu required key | Báo lỗi ở config boundary trước invocation |
| Field null hoặc blank | Báo lỗi xác định, không bỏ qua silently |
| Enum không hợp lệ | Parse/validation từ chối |
| Timeout âm | Không activate config |
| Retry attempts invalid | Từ chối hoặc áp constraint được tài liệu hóa |
| Include operation hợp lệ | Chỉ operation đúng phạm vi được advice |
| Excluded operation | Không xuất advice ngoài chủ đích |
| Pointcut chọn logger | Guard/exclusion ngăn recursion |
| Config disabled | Behavior đúng nghĩa disabled được công bố |
| BEST_EFFORT observer failure | Kết quả/lỗi business không bị đổi |
| FAIL_CLOSED pre-operation failure | Target không chạy |
| FAIL_CLOSED post-operation failure | Contract nói rõ khả năng side effect đã xảy ra |
| Business failure | Không bị best-effort nuốt mất |
| Two concurrent invocations | Mỗi invocation thấy snapshot config nhất quán |
| Hot reload invalid candidate | Giữ config cũ, không publish partial |
| Hot reload valid candidate | Invocation mới dùng version mới theo contract |
| Two concrete aspects match | Event count/precedence đúng |
| Proxy direct target | Được nhận diện là bypass |
| Class outside weaving scope | Không giả định advice hiện diện |
| Async completion | Success không bị ghi nhầm tại Future creation |
| Retry attempts | Không nhân side effects ngoài policy |
| Masking | Không log thông tin nhạy cảm |
| Regression config version | Mọi defaults/migrations đúng release notes |

### 29.1. Test cả những thứ không được xảy ra

Một test chỉ xem “đã có log ở SAVE” chưa đủ. Cần assert:

- Không có log ở operation không chọn.
- Không gọi target nếu pre-operation mandatory sink fail theo FAIL_CLOSED.
- Không chạy target hai lần vì observer error.
- Không swallow `IllegalStateException` của business.
- Không ghi dữ liệu nhạy cảm.
- Không bỏ advice của invocation khác do một cờ guard toàn cục.
- Không làm mất state khi reload config.

### 29.2. Cấu hình và kết quả phải cùng phiên bản

Trong integration test, log effective config revision và danh tính aspect/pointcut. Nếu test đọc một config nhưng runtime đang dùng một artifact khác, kết quả pass giả sẽ khó nhận ra.

## 30. Bài tập kèm đáp án

### Bài 1 — Trộn scope và behavior

Một cấu hình có `enabled=false` nhưng security policy vẫn phải hoạt động. Nên làm gì?

**Đáp án:** Phân biệt việc tắt telemetry/observer khỏi tắt security enforcement. Security policy bắt buộc phải được bảo vệ ở trust boundary phù hợp và không phó mặc cho một toggle chung.

### Bài 2 — Sai đơn vị timeout

Cùng key `timeout=1000`, đội A hiểu mili giây, đội B hiểu giây. Là lỗi gì?

**Đáp án:** Hợp đồng cấu hình thiếu đơn vị. Dùng `Duration` hoặc tên trường/định dạng rõ, validate phạm vi và tài liệu defaults.

### Bài 3 — Cấu hình đang cập nhật

Một invocation đọc `enabled` trước khi reload và `failureMode` sau reload. Hậu quả?

**Đáp án:** Có thể thấy tổ hợp không nhất quán. Tạo immutable snapshot và dùng một reference cho cả invocation.

### Bài 4 — Best effort và lỗi nghiệp vụ

Observer có lỗi, còn target ném `IllegalArgumentException`. Có được nuốt lỗi target khi `BEST_EFFORT` không?

**Đáp án:** Không theo hợp đồng “best effort của observer”. Catch phải giới hạn vào observer call.

### Bài 5 — Pointcut và class loading

Biểu thức pointcut được thay ở config nhưng target class đã được load ở một mô hình LTW không hỗ trợ weave lại. Có chắc advice áp ngay?

**Đáp án:** Không. Cần đối chiếu pha hiệu lực và khả năng weaver/class loader; có thể cần restart/redeploy.

### Bài 6 — Trạng thái sau fail-closed

Business đã ghi dữ liệu rồi after audit thất bại. Caller nhận exception. Có chắc dữ liệu chưa được ghi?

**Đáp án:** Không. Không có rollback tự động; exceptional guarantee phải chỉ ra trạng thái thật và cách kiểm tra/idempotency.

### Bài 7 — Retry và operation không idempotent

Config đổi maxAttempts từ 1 sang 3 cho operation tạo hóa đơn. Có nguy hiểm không?

**Đáp án:** Có thể tạo hóa đơn trùng khi lỗi xảy ra sau side effect. Phải có phân loại lỗi, idempotency và test trước khi bật.

### Bài 8 — Concrete aspects dùng chung

Hai concrete aspects kế thừa base audit, cùng match một method. Vì mã base chỉ viết một lần, method chỉ có một event?

**Đáp án:** Không. Hai concrete aspects có thể cùng áp advice; cần precedence/overlap policy và test số lần.

### Bài 9 — Cấu hình XML aspect

Một abstract pointcut cần bind `args()` nhưng cơ chế concrete-aspect qua XML cụ thể chỉ hỗ trợ abstract pointcut đơn giản. Có thể đặt expression vào XML và chắc chắn chạy?

**Đáp án:** Không. Phải theo giới hạn cơ chế concrete aspect của tool, hoặc dùng code-style inheritance/solution khác.

### Bài 10 — Schema version

Một field mới được thêm nhưng mặc định đổi chính sách xử lý lỗi. Có cần major version không?

**Đáp án:** Phụ thuộc quy ước versioning, nhưng đây là thay đổi behavior có thể breaking. Phải được công bố, đánh giá compatibility và migration, không chỉ dựa vào việc có thêm field.

## 31. Quy trình thiết kế config aspect từng bước

1. **Xác định consumer của cấu hình:** lập trình viên, operator hay platform owner.
2. **Chốt contract public:** aspect chỉ quan sát hay thay đổi behavior?
3. **Phân loại scope:** join-point kind, include/exclude, guard và boundary.
4. **Chọn type:** enum, Duration, Set of IDs, immutable records hoặc config objects.
5. **Ghi tất cả defaults và constraints:** đặc biệt các trường tùy chọn.
6. **Xác định failure policies theo phase:** before, normal return, exceptional return và cleanup.
7. **Rà soát thay đổi security/transaction/idempotency:** không cho policy nguy hiểm bị bật tùy tiện.
8. **Chốt ordering/preference:** xác định precedence/overlaps.
9. **Chốt vòng đời config:** startup, deployment, per-invocation snapshot hoặc dynamic reload.
10. **Phân biệt cấu hình engine và cấu hình advice runtime.**
11. **Thiết kế validation atomic:** parse → validate → publish, giữ bản cũ nếu thất bại.
12. **Cung cấp effective-config diagnostics** với redaction phù hợp.
13. **Viết test dương/âm:** selected và excluded operations.
14. **Viết test lỗi:** business failure, sink failure trước/sau target, cleanup.
15. **Viết test concurrency/async:** nếu scope thực tế dùng multi-thread/Future.
16. **Kiểm thử packaging/weaving cuối:** source và classloader thực sự đúng.
17. **Theo dõi khi rollout:** sự kiện/latency và policy revision.
18. **Đánh giá compat khi nâng cấp:** không đổi default/behavior âm thầm.
19. **Ghi tài liệu migration:** khi xóa/đổi option hoặc giới hạn mới.
20. **Thiết kế rollback:** quay về config trước mà không đổi semantics bất ngờ.

## 32. Checklist công bố cấu hình

- [ ] Có tên aspect, version, owner và mục đích.
- [ ] Có schema/type rõ, không phụ thuộc nhiều chuỗi tùy ý.
- [ ] Phân biệt selection, advice behavior, ordering và runtime operation.
- [ ] Có include/exclude và join-point kind được tài liệu hóa.
- [ ] Có weaving/proxy boundary và bypass paths.
- [ ] Biết option nào cần restart/reweave.
- [ ] Có default rõ cho từng field, cả những trường không cung cấp.
- [ ] Có validation ở construction/activation boundary.
- [ ] Có kiểm tra tổ hợp option mâu thuẫn.
- [ ] Có defensive copy cho mutable collections.
- [ ] Có một immutable snapshot nhất quán per invocation.
- [ ] Có failure mode riêng cho observer, không nuốt business error.
- [ ] Phân biệt fail-closed trước và sau target.
- [ ] Không hứa rollback vì một exception từ advice.
- [ ] Không bật retry cho operation không idempotent ngoài chủ đích.
- [ ] Timeout có đơn vị và completion boundary.
- [ ] Không đưa dữ liệu nhạy cảm vào args/result log.
- [ ] Có masking và retention policy phù hợp.
- [ ] Có precedence/overlap policy rõ khi nhiều aspects match.
- [ ] Không biến config thành cách bypass security bắt buộc.
- [ ] Có test pointcut selection, negative cases và proxy bypass.
- [ ] Có test business error, observer error và finally cleanup.
- [ ] Có test hot reload/concurrent invocation nếu áp dụng.
- [ ] Có test async completion nếu scope chọn async operations.
- [ ] Có effective-config version/diagnostics.
- [ ] Có release notes và migration cho changes to defaults/contracts.
- [ ] Có bằng chứng build/weave/classloader đúng với production.
- [ ] Có phương án rollback/disable telemetry an toàn khi vận hành.
- [ ] Không gọi cấu hình XML/YAML tự thiết kế là chuẩn phổ quát.
- [ ] Có kiểm thử tổng hợp cho tất cả concrete aspects tái sử dụng base.

## 33. Tài liệu đối chiếu

Các tài liệu sau cung cấp ngữ nghĩa cho **một công cụ AOP cụ thể** và Java 17; không tự biến cú pháp đó thành chuẩn của mọi AOP engine:

- [Eclipse AspectJ – Load-Time Weaving và cấu hình `META-INF/aop.xml`](https://eclipse.dev/aspectj/doc/latest/devguide/ltw.html): sections của cấu hình, `concrete-aspect`, abstract pointcut limitations, weaving/classloader scope.
- [Eclipse AspectJ – Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): pointcut/advice, aspect inheritance và precedence.
- [Eclipse AspectJ – Pointcuts](https://eclipse.dev/aspectj/doc/released/progguide/semantics-pointcuts.html): type patterns, join-point kinds và điều kiện chọn.
- [Java SE 17 – `Objects`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): kiểm null và tiền điều kiện ở API.
- [Java SE 17 – `Set`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): `Set.copyOf`, tập không sửa được qua interface.
- [Java SE 17 – `Record Classes`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): cấu trúc record và compact constructor.
- [Java SE 17 – `AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): cơ sở cho atomic config publication.

## 34. Kết luận

**Thiết kế giao diện cấu hình rõ ràng cho aspect không chỉ là tạo một file có vài khóa và giá trị.** Đó là việc công bố một **hợp đồng lựa chọn và hành vi**: can thiệp ở đâu, khi nào, theo thứ tự nào, lỗi được xử lý ra sao, state nào là per invocation, config nào được phép đổi và thay đổi có tác động gì đến caller.

Ba nguyên tắc quan trọng nhất:

1. **Phân biệt scope với behavior:** pointcut/weaving lựa chọn join points; runtime policy quy định advice làm gì sau khi được kích hoạt.
2. **Có typed/validated/immutable config:** giá trị mặc định, constraints và snapshot nhất quán giúp tránh lỗi vận hành khó tái hiện.
3. **Tôn trọng public contract và giới hạn engine:** một option đổi failure mode, precedence, retry hoặc class coverage có thể là breaking change. Cấu hình không thể tự cung cấp một join-point kind hoặc cơ chế weaving mà công cụ không hỗ trợ.

Dùng **Java record/enum/validation** hoặc giải pháp tương đương để diễn đạt policy; dùng **tài liệu engine cụ thể** để thực hiện pointcut và weaving; và dùng **kiểm thử có cả selected, excluded, error và bypass paths** để chứng minh hệ thống vận hành đúng những gì giao diện cấu hình cam kết.

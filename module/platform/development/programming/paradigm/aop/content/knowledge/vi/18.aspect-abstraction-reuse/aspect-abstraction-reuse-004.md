# Tham số hóa chính sách thay vì chép lại advice trong AOP

## 1. Bài toán: một cơ chế, nhiều biến thể chính sách

Trong **Aspect-Oriented Programming (AOP)**, một **aspect** mô-đun hóa mối quan tâm xuyên cắt bằng **pointcut** (quy tắc chọn join point) và **advice** (hành vi bổ sung tại điểm được chọn). Những concern phổ biến như ghi nhật ký, kiểm tra quyền, theo dõi hiệu năng, retry, audit, rate limiting hoặc kiểm tra đầu vào thường cần những thay đổi nhỏ theo từng nhóm thao tác.

Ví dụ cùng một cơ chế ghi nhận lời gọi:

- Với thao tác tạo dữ liệu: ghi bắt đầu, thành công và thất bại.
- Với thao tác xóa: bắt buộc ghi audit, nhưng ẩn payload nhạy cảm.
- Với thao tác đọc: có thể chỉ theo dõi một tỷ lệ nhỏ hoặc không ghi.
- Với thao tác tính toán nội bộ: chỉ ghi lỗi quan trọng.
- Với thao tác có dữ liệu nhạy cảm: chỉ ghi tên operation và mã lỗi được phép, không in secret.

Cách ngây thơ là chép toàn bộ advice:

~~~text
Aspect_AuditCreate:
    before create -> log
    after create -> log success
    on error -> log failure

Aspect_AuditDelete:
    before delete -> log
    after delete -> log success
    on error -> log failure

Aspect_AuditUpdate:
    before update -> log
    after update -> log success
    on error -> log failure
~~~

Ba đoạn gần giống nhau dễ dẫn tới:

1. **Thay đổi không đồng đều:** sửa xử lý exception ở Create nhưng quên Delete.
2. **Khác biệt ẩn:** cùng quy tắc redaction nhưng có một bản sao bỏ sót.
3. **Test bị nhân đôi:** phải kiểm tra cùng logic ở nhiều places.
4. **Precedence khó quản lý:** nhiều aspects cùng chặn một join point có thể tạo log trùng.
5. **Tăng coupling:** chi tiết triển khai advice và chính sách nghiệp vụ bị trộn lẫn.
6. **Rủi ro bảo mật:** một advice copy có thể log dữ liệu nhạy cảm sai chuẩn.

Giải pháp kiến trúc là **tham số hóa chính sách**: giữ một cơ chế interception tái sử dụng được, còn những điểm thay đổi được biểu diễn bằng **Policy/Strategy/Configuration** có hợp đồng rõ ràng.

~~~text
               Join point / operation
                        |
                        v
                Reusable advice engine
                    /         \
                   /           \
       Policy for CREATE     Policy for DELETE
        audit + redact       audit + fail-closed
                   \           /
                    \         /
                 Same around skeleton
~~~

**Ý chính:** Không biến mọi khác biệt thành một advice mới. Nếu các biến thể chỉ khác **quy tắc chọn operation, dữ liệu được ghi, ngưỡng, quyết định hoặc cách biểu diễn**, hãy đưa chúng vào cấu hình/chính sách. Nếu chúng khác **hợp đồng điều khiển luồng hoặc semantics**, cần cân nhắc các mechanisms/advice riêng thay vì nhồi tất cả vào một bộ cờ.

Bài này trình bày AOP cơ bản và nâng cao nói chung; các ví dụ Java 17 minh họa around-advice composition mà không đòi hỏi một framework ứng dụng hoặc bộ dệt cụ thể.

## 2. Phân biệt mechanism và policy

**Mechanism (cơ chế):** thao tác có tính lặp lại và chịu trách nhiệm cho vòng đời interception.

Ví dụ:

- Nhận thông tin join point đã chọn.
- Gọi proceed đúng số lần theo contract.
- Đo thời gian hoặc thu thập result/error.
- Bảo đảm cleanup trong finally.
- Gọi một policy object để quyết định cách xử lý.
- Bảo toàn exception propagation và result type.
- Cung cấp hooks trước/sau có thứ tự rõ.

**Policy (chính sách):** quyết định khác nhau giữa các hoàn cảnh:

- Operation nào được quan sát?
- Sự kiện success/failure nào cần ghi?
- Có redaction message/error/payload không?
- Ngưỡng thời gian nào cần báo cáo?
- Có được retry lỗi này không, retry bao nhiêu lần?
- Ai được phép tiếp tục execution?
- Fail-open hay fail-closed khi một dependency gặp lỗi?
- Khi nào record audit phải bền vững?

Một nguyên tắc:

~~~text
Mechanism biết CÁCH chạy an toàn.
Policy quyết định KHI NÀO và THEO QUY TẮC NÀO chạy.
~~~

Tuy nhiên ranh giới không tuyệt đối: cơ chế có thể cần các hooks hỗ trợ nhiều policies, và policy không nên điều khiển các hành động làm mất invariant cơ bản.

### 2.1. Tư duy Template Method / Strategy

Một **around advice** có thể cung cấp template:

~~~text
if policy.selects(joinPoint):
    policy.before(context)

try:
    result = proceed()
    policy.afterSuccess(context, result)
    return result
catch error:
    policy.afterFailure(context, error)
    rethrow original error
finally:
    policy.cleanup(context)
~~~

Đây là **giả mã**, không phải Java độc lập và cần thiết kế kỹ policy exception handling. Nó minh họa chỗ hành vi cố định và chỗ thay đổi.

**Strategy:** truyền một policy object hoặc function quyết định, không viết lại toàn bộ skeleton.

**Template:** thống nhất vòng đời try/catch/finally/proceed, giữ những bất biến chung.

**Configuration:** các dữ liệu đơn giản như tập operation, mức log, ngưỡng, danh sách lỗi có thể dùng immutable value object.

### 2.2. Khi nào không nên tham số hóa?

Nếu một advice để thực hiện **authorization bắt buộc** còn advice khác chỉ là **telemetry best-effort**, chúng có exception/lifecycle contracts khác nhau. Gộp vào một class có 20 boolean flags có thể khiến policy khó đọc và tạo trạng thái config không hợp lệ.

Đừng đánh đổi ba đoạn dễ hiểu thành một “siêu advice” với nhiều nhánh mà không có invariant chung. **Tái sử dụng thực chất** là giảm lặp về semantics, không chỉ giảm số dòng mã.

## 3. Trục tham số hóa thứ nhất: phạm vi chọn join point

Có ít nhất hai tầng:

1. **Pointcut selection:** engine AOP chọn các join point có thể được advise, dựa trên method/type/call/execution/annotation/runtime condition nếu được hỗ trợ.
2. **Policy selection:** sau khi đã vào mechanism, chính sách quyết định có xử lý operation cụ thể và theo mức độ nào.

Ví dụ:

~~~text
Static candidate pointcut:
  public operations in a service boundary

Runtime policy:
  create -> AUDIT
  delete -> AUDIT
  read   -> NO-OP
~~~

Một runtime operation filter không **thay thế hoàn toàn pointcut**; nó chỉ trả lời điều kiện trong vùng candidate đã bị interception.

### 3.1. Vì sao nên thu hẹp static candidate set?

Nếu weaver chặn cả triệu lời gọi helper nhỏ nhưng policy thường trả “không xử lý”, overhead kiểm tra vẫn có thể đáng kể. Nên chọn pointcut đủ hẹp khi thông tin tĩnh có thể biểu đạt requirement, rồi dùng policy cho những điều kiện còn cần tính động.

### 3.2. Pointcut động cũng có vai trò

Một số policy cần actor, args, target state hoặc dynamic control flow. Khi đó pointcut/guard có thể phụ thuộc runtime. Nhưng runtime checks có chi phí và có thể gắn với asynchronous boundaries. Đừng dùng một operation-name string filter đơn giản như bằng chứng rằng ta đã thực hiện đủ **authorization** cho mọi đường gọi.

### 3.3. Không tự gắn policy vào method name mơ hồ

Operation name có thể bị overload, rename hoặc reuse. Một mapping theo một string tự đặt cần có contract rõ, validation và tests. Với API quan trọng, sử dụng **operation identity** được quản trị, metadata type-safe hoặc explicit mapping thay vì phụ thuộc Method.toString và cấu trúc tên tùy tiện.

## 4. Trục thứ hai: quyết định hành động tại các điểm lifecycle

Một cơ chế logging tái sử dụng có thể tách:

| Giai đoạn | Cơ chế chung | Policy quyết định |
|---|---|---|
| Entry | Nhận event context | Có log attempt không? |
| Before proceed | Chuẩn bị trace / check | Log field nào, có sampling không? |
| Normal return | Nhận kết quả | Có log success không; result có được xem không? |
| Exception | Nhận lỗi | Có log failure không; redact thế nào? |
| Finally | Khôi phục context | Có emit metrics, dọn resource ra sao? |
| Commit outcome | Một boundary riêng nếu có transaction | Có ghi committed event không? |
| Async completion | Callback/completion boundary | Success của task được định nghĩa thế nào? |

Cơ chế phải giữ đúng thứ tự những bước **bắt buộc**, policy mới quyết định những gì có thể tùy biến.

### 4.1. “Không log failure” khác “nuốt failure”

Nếu policy tắt log failure, **exception vẫn phải được propagate** theo hợp đồng của target/advice. Logging policy không được biến một business failure thành return OK trừ khi aspect thực sự có trách nhiệm làm exception translation.

### 4.2. “Log success” có nghĩa nào?

After-returning của method nghiệp vụ không nhất thiết nghĩa transaction đã commit. Nếu cần sự kiện **committed**, phải quan sát transaction boundary thích hợp hoặc dùng cơ chế ghi outbox/audit có semantics bền vững; không sửa tên field trong policy để giả vờ biết trạng thái commit.

## 5. Biểu diễn Policy bằng giá trị bất biến

Một policy tốt thường là **immutable**, có validation và có tên dễ hiểu. Ví dụ:

~~~java
record Policy(
    String name,
    Set<String> operations,
    boolean logSuccess,
    boolean logFailure,
    boolean redactFailure
) {
    Policy {
        Objects.requireNonNull(name);
        Objects.requireNonNull(operations);
        if (name.isBlank()) {
            throw new IllegalArgumentException("blank-policy-name");
        }
        operations = Set.copyOf(operations);
    }
}
~~~

Đây là đoạn Java minh họa (imports được cung cấp trong chương trình đầy đủ ở phần sau). Constructor compact bảo vệ name/operations và copy tập operations thành một set không cho mutate qua reference bên ngoài.

**Điểm cần hiểu:** Java record không tự đảm bảo deep immutability nếu một component chứa mutable object. Với Set.copyOf, collection component được cố định ở mức tập các String bất biến. Nếu policy chứa một mutable collaborator, phải thiết kế riêng vòng đời/thread safety của collaborator.

### 5.1. Policy IDs

Tên/chỉ số policy phục vụ audit và diagnostics. Một id như AUDIT hay TRACE nên có nghĩa quản trị được, không dùng giá trị user input chưa kiểm chứng để chọn một policy đặc quyền.

### 5.2. Ràng buộc hợp lệ

Một số combinations phải bị từ chối khi tạo policy:

- Permission policy không được cấu hình “allow tất cả” khi thiếu policy.
- Audit bắt buộc không được vô tình disable bằng một flag logging chung.
- Redaction bắt buộc không được tùy ý tắt với dữ liệu nhạy cảm.
- Timeout/retry count phải nằm trong range hợp lệ.
- Operation identifiers không được null hoặc chứa ký tự rác.
- Policy version phải có semantics rõ cho các requests đang chạy.

**Validation tại boundary** giúp lỗi cấu hình xuất hiện sớm thay vì chỉ bộc lộ dưới traffic.

## 6. Khi flags bắt đầu bùng nổ: chuyển sang kiểu diễn tả mạnh hơn

Một record với ba booleans có thể phù hợp cho demo, nhưng 12 booleans tạo ra rất nhiều combinations khó hiểu.

Ví dụ:

~~~text
Policy(
  true, false, true, false, true, true, false, ...
)
~~~

Không ai dễ kiểm toán rằng combination này có được phép hay không.

Có thể thay bằng các lựa chọn thể hiện meaning:

~~~java
enum OutcomeMode {
    SUCCESS_ONLY, FAILURE_ONLY, BOTH, NONE
}

enum FailureDetailMode {
    REDACTED, ERROR_CLASS_ONLY
}
~~~

Đây là đoạn minh họa, không phải chương trình hoàn chỉnh. Khi cần nhiều loại policy, sử dụng sealed hierarchy, strategy interfaces hoặc các value objects riêng theo concern.

### 6.1. Tách policy data và policy behavior

Một ngưỡng 200ms, danh sách operations hoặc enum logLevel thường là dữ liệu cấu hình.

Một policy quyết định “có retry lỗi X với idempotency key Y không” có thể là một function/Strategy vì nó phải xét exception, attempt và context.

Không cố nhồi mọi quyết định phức tạp vào boolean flags chỉ để có một config object.

## 7. Java 17 runnable: một around engine, hai chính sách

Chương trình dưới đây là **Java 17 thuần**, mô phỏng reusable around advice bằng một hàm nhận:

- Operation identifier.
- Một immutable Policy.
- Continuation được biểu diễn bằng Callable.
- Cách in success/failure/exit theo policy.

Hai policy cụ thể:

- **AUDIT:** chọn create và delete, log success/failure, redact chi tiết lỗi.
- **TRACE:** chỉ chọn create, log success, không log failure.

Khi hai wrappers cùng được áp vào create, output bộc lộ **precedence lồng nhau**. Khi operation không được policy chọn, mechanism vẫn gọi continuation **đúng một lần** và không emit event. Khi continuation throw, policy có thể quyết định log hay không, nhưng exception vẫn được ném lại.

**Quan trọng:** Đây là simulation của around chain để học policy parameterization, **không phải một implementation của pointcut engine, transaction, security audit sink hoặc compiler weaving**.

Tạo file **ParameterizedAdviceDemo.java**:

~~~java
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.Callable;

public class ParameterizedAdviceDemo {
    record Policy(String name,
                  Set<String> operations,
                  boolean logSuccess,
                  boolean logFailure,
                  boolean redactFailure) {
        Policy {
            Objects.requireNonNull(name);
            Objects.requireNonNull(operations);
            if (name.isBlank()) {
                throw new IllegalArgumentException("blank-policy-name");
            }
            operations = Set.copyOf(operations);
        }
    }

    static String around(String operation, Policy policy,
                         Callable<String> proceed) throws Exception {
        if (!policy.operations().contains(operation)) {
            return proceed.call();
        }

        System.out.println("enter:" + policy.name() + ":" + operation);
        try {
            String result = proceed.call();
            if (policy.logSuccess()) {
                System.out.println("success:" + policy.name() + ":" + operation);
            }
            return result;
        } catch (Exception error) {
            if (policy.logFailure()) {
                String detail = policy.redactFailure()
                    ? "redacted" : error.getClass().getSimpleName();
                System.out.println("failure:" + policy.name() + ":" + detail);
            }
            throw error;
        } finally {
            System.out.println("exit:" + policy.name() + ":" + operation);
        }
    }

    @FunctionalInterface
    interface Scenario {
        String run() throws Exception;
    }

    static void test(String label, Scenario scenario) {
        System.out.println("=== " + label + " ===");
        try {
            System.out.println("result:" + scenario.run());
        } catch (Exception e) {
            System.out.println("caught:" + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Policy audit = new Policy("AUDIT",
                Set.of("create", "delete"), true, true, true);
        Policy trace = new Policy("TRACE",
                Set.of("create"), true, false, false);

        test("create", () ->
                around("create", audit, () ->
                    around("create", trace, () -> "CREATED")));
        test("delete", () ->
                around("delete", audit, () ->
                    around("delete", trace, () -> "DELETED")));
        test("read", () ->
                around("read", audit, () ->
                    around("read", trace, () -> "READ")));
        test("error", () ->
                around("create", audit, () ->
                    around("create", trace, () -> {
                        throw new IllegalStateException("secret-disk-path");
                    })));
    }
}
~~~

Biên dịch và chạy với JDK 17:

~~~bash
javac --release 17 ParameterizedAdviceDemo.java
java ParameterizedAdviceDemo
~~~

**Stdout đã biên dịch/chạy kiểm chứng:**

~~~text
=== create ===
enter:AUDIT:create
enter:TRACE:create
success:TRACE:create
exit:TRACE:create
success:AUDIT:create
exit:AUDIT:create
result:CREATED
=== delete ===
enter:AUDIT:delete
success:AUDIT:delete
exit:AUDIT:delete
result:DELETED
=== read ===
result:READ
=== error ===
enter:AUDIT:create
enter:TRACE:create
exit:TRACE:create
failure:AUDIT:redacted
exit:AUDIT:create
caught:IllegalStateException
~~~

### 7.1. Một mechanism được cấu hình khác nhau

Không có phiên bản khác nhau của around method. Cả AUDIT và TRACE dùng **cùng skeleton**, nhưng operation sets và flags làm behavior khác.

- Create: hai policies cùng active.
- Delete: chỉ AUDIT active.
- Read: cả hai policies skip việc logging nhưng vẫn proceed.
- Error: TRACE không log failure; AUDIT log redacted detail.

Điều này thể hiện ưu điểm rõ nhất của **policy parameterization**: sửa cách catch/rethrow hoặc cleanup ở đúng một mechanism.

### 7.2. Error message nhạy cảm không bị in

Business exception có message "secret-disk-path". AUDIT redact nên chỉ in **failure:AUDIT:redacted**. Code test() chỉ in exception class, không in message.

**Nhưng đây chỉ là redaction tối giản ở một log line.** Không có đảm bảo toàn bộ hệ thống không log secret ở logger khác, stack trace collector hoặc diagnostic handler. Redaction thực tế cần xem schema fields, access control, retention, exceptions và structured logging.

### 7.3. TRACE không log lỗi, nhưng vẫn throw

Câu lệnh catch trong around luôn rethrow error sau khi policy xét logging. Vì thế caller cuối in caught:IllegalStateException. Việc cấu hình logFailure=false **không thay kết quả nghiệp vụ**.

### 7.4. Finally chạy từ trong ra ngoài

Khi create thành công, exit TRACE chạy trước exit AUDIT. Khi lỗi, finally của TRACE vẫn chạy rồi AUDIT thấy exception. Điều này minh họa precedence của **hai wrapper lồng nhau**.

### 7.5. Vì sao ví dụ dùng Callable?

Callable<String> biểu diễn một continuation có thể throw Exception, cho phép Java demo mà không cần công cụ weave. Trong AOP thực, proceed có contract riêng với kiểu trả về, arguments, exception propagation và số lần gọi.

### 7.6. Vì sao demo chưa đủ để production?

- System.out không phải audit sink bền vững.
- Tập operation string chưa là type-safe pointcut.
- Không có request context, data classification hoặc policy registry.
- catch(Exception) không catch mọi Throwable/Error.
- Không có transaction commit semantics.
- Policy selection chưa giải quyết authentication/authorization.
- Không có runtime refresh, metrics, async propagation hoặc sampling.
- Không xử lý logger failure thay đổi exception gốc ở các công cụ logging thực.

Chương trình chứng minh **khả năng tái sử dụng cơ chế**, không chứng minh tính đúng của một sản phẩm audit/security hoàn chỉnh.

## 8. Tách cơ chế khỏi concern-specific semantics

Một logging advice và một retry advice đều có thể dùng around, nhưng **không nên dùng một tham số retryCount trong logging engine để làm nó ngầm retry target**.

Ví dụ retry có contract:

~~~text
around retry:
    for attempt in 1..maxAttempts:
        try:
            return proceed()
        catch retriableError:
            decide delay/backoff
    throw lastError
~~~

Ngược lại logging có contract:

~~~text
around logging:
    record attempt
    try:
        result = proceed()
        record completion
        return result
    catch error:
        record failure
        rethrow
~~~

Nếu trộn chúng thành một advice với nhiều flags, dễ vô tình biến một request thành nhiều executions hoặc che exception sai policy.

Một lựa chọn tốt là **một generic around template cho instrumentation**, cùng các **Strategy policies theo concern**, còn Retry/Transaction/Security giữ boundaries rõ.

## 9. Thiết kế interface chính sách thay vì nhiều bản sao advice

Nếu logic quyết định phức tạp hơn vài giá trị:

~~~java
interface EventPolicy {
    boolean selects(OperationContext context);
    Event toSuccessEvent(OperationContext context, Object result);
    Event toFailureEvent(OperationContext context, Throwable error);
}
~~~

Đây là code minh họa, cần định nghĩa OperationContext và Event.

Một reusable advice chỉ gọi policy khi tới giai đoạn tương ứng. Concrete policies có thể là:

- SecurityAuditPolicy.
- PerformanceEventPolicy.
- BusinessOperationTracePolicy.

Nhưng **không phải mọi EventPolicy implementation đều có cùng bảo đảm độ bền**. Mechanism cần nêu rõ event sink, failure policy, thread safety và versioning.

### 9.1. Có nên tạo class riêng cho từng policy?

Nếu khác biệt chỉ là dữ liệu, tạo một instance immutable cấu hình thường đủ. Nếu khác biệt là thuật toán (vd. policy threshold theo percentile hoặc exception classifier nhiều rules), class/Strategy riêng có thể rõ hơn.

Phân biệt **reuse behavior** và **reuse data shape** để tránh cả duplicate code lẫn một switch statement quá lớn.

### 9.2. Function parameters

Java có thể truyền Predicate, Function, BiPredicate hoặc functional interfaces riêng để cấu hình policy. Khi policy phải được audit, versioning hoặc serialization, một named class/record có thể dễ theo dõi hơn một lambda vô danh.

Không tùy tiện serialize arbitrary lambdas chỉ để lưu policy; một declarative policy schema có thể dễ quản trị và validate hơn.

## 10. Phân biệt pointcut tái sử dụng và advice tái sử dụng

Một số AOP languages cho phép **named pointcuts**, **abstract pointcuts** hoặc **abstract aspects** để tách nơi nào được match khỏi hành vi áp dụng.

Về mặt kiến trúc:

~~~text
Abstract mechanism:
    around(selectedOperations):
        common intercept logic

Concrete binding A:
    selectedOperations = calls for billing
    policy = billingAudit

Concrete binding B:
    selectedOperations = calls for inventory
    policy = inventoryAudit
~~~

Đây là giả mã để biểu diễn thiết kế, không phải cú pháp hợp lệ chung của mọi AOP language.

### 10.1. Named pointcut

Một pointcut được đặt tên giúp tránh lặp lại một expression dài trên nhiều advices. Tuy nhiên trùng pointcut và trùng advice body là **hai vấn đề khác**:

- Named pointcut giảm lặp quy tắc chọn join points.
- Shared advice mechanism/policy Strategy giảm lặp xử lý return/error/cleanup.

### 10.2. Abstract aspect hoặc template

Một abstract aspect có thể định nghĩa skeleton, còn concrete aspect chọn pointcut hoặc policy trong phạm vi ngôn ngữ hỗ trợ. Các chi tiết như method override, kiểu generic và context binding khác nhau giữa engines.

Không suy rằng mọi AOP language đều cho override pointcut như override Java method; kiểm tra semantics công cụ nếu dùng thật.

### 10.3. Một aspect hay nhiều aspect instances?

Một reusable mechanism không nhất thiết chỉ có một aspect instance. Nếu engine tạo aspect per-target hoặc per-flow, mỗi instance có thể có policy/config riêng. Ngược lại, shared aspect instance có thể dùng cùng immutable Policy cho nhiều threads.

**Policy object bất biến** giúp tránh race ở cấu hình, nhưng không bảo đảm state của target hay sink cũng thread-safe.

## 11. Context nên là input tường minh

Chính sách đôi khi cần:

- Operation ID.
- Actor/tenant đã được xác thực.
- Method metadata.
- Target identity.
- Result category.
- Exception class.
- Correlation/request ID.
- Attempt number.
- Elapsed time.
- Policy version.

Đóng gói vào một context object với hợp đồng rõ:

~~~java
record OperationContext(
    String operation,
    String correlationId,
    String actorId,
    int attempt
) {}
~~~

Đây là snippet minh họa, không phải implementation xác thực actor. Chỉ nên đưa dữ liệu cần cho policy; không biến context thành một global mutable bag.

### 11.1. Thông tin đáng tin và không đáng tin

Một request parameter như "role=admin" do client gửi không tự là authenticated actor role. Security policies cần context có nguồn tin cậy, được kiểm tra authorization theo từng resource và được áp trước side effect không được phép.

Tham số hóa security bằng một boolean "allowed" do caller có thể tự điều khiển là **đưa quyết định quyền cho bên không đáng tin**.

### 11.2. Capture immutable snapshot

Nếu policy cần dùng cùng actor, tenant và policy version xuyên suốt operation, capture một immutable snapshot tại boundary phù hợp. Đọc các mutable global fields tại nhiều điểm có thể tạo inconsistent decisions trong cùng invocation.

## 12. Policy lookup: tĩnh, theo operation hay theo invocation?

Có một số cách resolve policy:

| Cách | Đặc điểm | Rủi ro |
|---|---|---|
| Inject immutable Policy cố định | Dễ test, không phải lookup mỗi call | Khó thay đổi runtime nếu cần |
| Immutable map operation → Policy | Chọn theo key, cấu hình rõ | Key mapping sai hoặc missing policy |
| Registry có version | Có thể reload policy | In-flight invocation dùng version nào? |
| Policy function theo context | Linh hoạt theo actor/operation | Cần threat model và purity |
| Annotation/metadata mapping | Dễ gắn với type/method | Reflection/caching/class loader cần quản lý |
| Remote policy service | Quyết định cập nhật tập trung | Network, timeouts, failure semantics |

Một lời gọi nên xác định rõ **policy được resolve lúc nào**, có được thay đổi giữa before và after hay không, và exception nào đến từ policy lookup.

### 12.1. Missing policy: fail-open hay fail-closed?

- Logging best-effort thiếu config có thể dùng một conservative default theo chính sách vận hành.
- Authorization hoặc audit bắt buộc thiếu config có thể phải **fail-closed**.
- Một registry lỗi không nên tự động biến "no policy" thành "allow" đối với những operation nhạy cảm.

Default policy là **quyết định nghiệp vụ/bảo mật**, không chỉ kỹ thuật.

### 12.2. Policy version cho trace

Ghi policy ID/version nếu cần audit. Khi điều tra hai requests xử lý khác nhau, biết hai invocations dùng rule versions nào thường quan trọng hơn biết chỉ method name.

## 13. Dynamic reload và tính nhất quán trong một lời gọi

Nếu application muốn đổi policy mà không khởi động lại, một registry có thể giữ **volatile reference đến immutable PolicySet**:

~~~text
PolicySet version 5
    |
reload creates a NEW immutable PolicySet version 6
    |
publish new reference atomically
~~~

Một around advice có thể capture snapshot tại entry và dùng snapshot cho toàn bộ before/success/failure/finally.

Nếu mỗi hook lại đọc registry mới, một invocation có thể:

~~~text
before under version 5
after under version 6
~~~

Điều này có thể gây event schema khác nhau hoặc exception policy inconsistency.

### 13.1. Atomic reference không thay thế compound correctness

Dùng volatile/AtomicReference để publish immutable snapshot giúp visibility, nhưng nếu version update phải tương quan với resource state, transaction hoặc distributed policy propagation, cần giao thức consistency phù hợp. Đừng suy “có volatile” là đã bảo đảm cùng version trên mọi processes.

### 13.2. Không mutate PolicySet đang được dùng

Nếu một shared HashMap policy bị mutate trực tiếp trong lúc nhiều invocations đọc, có data race hoặc inconsistent view. Dùng immutable copy + atomic swap, hoặc một concurrent map và semantics cập nhật rõ, thay vì mutate object đang được chia sẻ.

## 14. Policy composition: nhiều quy tắc đồng thời

Một operation có thể cần audit, tracing và performance metrics. Hai lựa chọn:

1. Nhiều aspects khác nhau, mỗi aspect có policy riêng.
2. Một instrumentation mechanism kết hợp nhiều event policies theo trình tự có kiểm soát.

Ví dụ:

~~~text
AuditPolicy + TracePolicy + PerformancePolicy
              |
              v
        CompositePolicy
              |
              v
         Around engine
~~~

Để composition an toàn cần quyết định:

- Thứ tự gọi các policies.
- Mỗi policy có thể throw không?
- Khi policy A từ chối, có gọi policy B không?
- Có phát trùng record không?
- Lỗi của telemetry policy có làm fail nghiệp vụ không?
- Có resource state riêng cần cleanup không?
- Có được reorder vì tối ưu hiệu năng không?

### 14.1. Không trộn policy quyết định với policy chỉ quan sát

Authorization policy có thể **từ chối proceed**. Logging policy lý tưởng **chỉ quan sát** và không đổi business result trừ khi contract về audit failure quy định rõ.

Khi một CompositePolicy có cả hai, phải nêu rõ stage ra quyết định trước khi làm side effects, và stage instrumentation sau. Không giao toàn quyền gọi proceed cho một plugin policy không đáng tin.

### 14.2. Precedence của nhiều around advices

~~~text
Audit(Trace(Business))
~~~

Khi thành công: Audit.before → Trace.before → Business → Trace.after → Audit.after.

Khi lỗi: inner finally/exception handler chạy trước outer. Đổi thứ tự có thể làm audit thấy hoặc không thấy transaction commit exception, hoặc làm đo latency bao gồm/không bao gồm logging. **Tham số hóa không loại bỏ nhu cầu xác định precedence rõ ràng.**

## 15. Truyền result và exception cho policy an toàn

Một policy logging thường không cần full result object. Nếu toSuccessEvent nhận result và gọi toString vô điều kiện, có thể:

- Lộ dữ liệu nhạy cảm.
- Gây chi phí serialization lớn.
- Kích hoạt lazy-loading hoặc side effects.
- Gặp exception trong toString.
- Tạo recursion nếu logger cũng được aspect match.

Thay vì truyền raw result cho mọi policy, có thể tạo một **whitelisted result summary** theo domain và data classification.

### 15.1. Exception policy

Một failure policy có thể chọn:

- Log exception class, không log message.
- Log error code cố định.
- Redact stack trace paths/secrets.
- Group errors để đo metrics.
- Retry một nhóm lỗi được xác định.
- Translate exception ở một boundary được công bố.

**Không mặc định mọi error cần log raw stack trace.** Một policy rõ giúp mọi operations áp cùng redaction rules.

### 15.2. Giữ lỗi gốc khi policy thất bại

Nếu logging policy throw trong lúc target đã throw, nó có thể che original exception. Có thể yêu cầu best-effort logging failure, giữ original error và lưu secondary diagnostics theo contract; audit bắt buộc có thể cần fail-closed.

Với try/finally, cleanup có thể throw và thay original error nếu không quản lý. Khi có AutoCloseable, Java try-with-resources cung cấp suppressed exceptions cho lỗi close phát sinh đồng thời với lỗi body.

Không có một exception policy thích hợp cho tất cả concerns: định nghĩa riêng cho logging, security, transaction, retry và audit.

## 16. Retry policy là ví dụ cần phân biệt semantics

Một retry policy có thể gồm:

- Maximum attempts.
- Backoff strategy.
- Predicate chọn retriable exception.
- Deadline/cancellation.
- Idempotency/side-effect rules.
- Attempt ID/correlation.
- Transaction per attempt.

Cơ chế retry dùng policy cho **điều kiện tiếp tục hoặc dừng**. Nó có thể gọi proceed **nhiều lần** nếu AOP engine hỗ trợ và contract cho phép.

### 16.1. Không dùng lại advice code bằng cách copy/paste

Nếu ba operations retry cùng một điều kiện lỗi và chỉ khác maxAttempts, nên có một retry mechanism và ba policies. Khi sửa overflow/backoff/cancellation, chỉ thay một implementation.

### 16.2. Nhưng policy không thể tạo idempotency từ con số

Một thao tác charge đã gửi request tới hệ thống bên ngoài không trở nên an toàn để retry chỉ vì RetryPolicy.maxAttempts = 3. Cần idempotency key và xác định result của attempt trước.

### 16.3. Transaction scope và retry order

~~~text
Retry(Transaction(Business))
~~~

Có thể tạo transaction mới mỗi attempt nếu transaction aspect mở scope mỗi lần proceed.

~~~text
Transaction(Retry(Business))
~~~

Có thể retry nhiều lần bên trong một transaction đang bị rollback-only hoặc giữ locks lâu. Cần chọn precedence phù hợp invariant. Một policy parameterization tốt phải làm rõ **nơi cơ chế retry bao transaction**.

## 17. Performance policy và ngưỡng đo

Một timer advice có thể chia sẻ cùng skeleton, thay đổi policy về:

- Operation nào được đo.
- Ngưỡng slow call (ms).
- Success/failure event schema.
- Sampling rate.
- Tagging/correlation.
- Độ phân giải và clock source.

### 17.1. Đo đúng boundary

Nếu muốn đo elapsed time của Business, ghi time ngay trước/ sau proceed. Nếu muốn đo **toàn bộ transaction completion**, timer phải bao cả transaction wrapper. Không chỉ sửa threshold để giải quyết boundary semantics.

### 17.2. Clock

Với elapsed duration trong Java, ưu tiên một monotonic time source như System.nanoTime thay vì lấy chênh lệch wall-clock timestamps. Policy định nghĩa threshold, mechanism chọn clock và thực hiện đo nhất quán.

### 17.3. Sampling và chi phí

Nếu sampling policy chỉ chọn 1% requests, có thể giảm cost của expensive event serialization, nhưng runtime interceptor/check vẫn có chi phí. Nếu metric/audit bắt buộc thì không được sampling làm mất sự kiện quan trọng theo policy.

Sampling phải xác định theo request ID, trace ID hoặc probabilistic random để không tạo bias ngoài ý muốn; không dùng một shared mutable Random không an toàn theo cách sai.

## 18. Authorization policy: mức độ nguy hiểm khi tham số hóa sai

Policy tái sử dụng có thể làm authorization rules dễ kiểm toán, nhưng cũng có thể làm **một sai sót áp dụng rộng**.

Các nguyên tắc:

- Policy decision phải dựa identity đã authenticated, operation và resource.
- Một caller không đáng tin không được chọn policy ID để nâng quyền.
- Missing policy xử lý fail-closed khi yêu cầu.
- Denial trước side effect không được phép.
- Resource-level authorization có thể cần kiểm tra bên trong transaction để tránh TOCTOU.
- Việc log denial phải không rò token, password hoặc PII.
- Một authorization policy có thể ném exception/return decision, nhưng không được tùy tiện swallow denial ở advice ngoài.

### 18.1. Policy reuse không thay scope coverage

Một pointcut chỉ match các calls đi qua proxy có thể bị bypass bởi một direct target reference hoặc self-invocation tùy mechanism. Dù policy authorization hoàn hảo, operation không được intercept sẽ không được bảo vệ bởi policy đó.

Vì vậy review phải kiểm tra **tập join points được bao phủ**, không chỉ nội dung policy object.

### 18.2. Security policy per tenant

Nếu mỗi tenant có rule khác, sử dụng mapping tenant ID → immutable policy có xác thực và authorization của tenant context. Không để mutable singleton field currentTenant đổi theo thread, gây context mixing giữa requests.

## 19. Thread safety và state ownership

Một reusable advice có thể được nhiều threads gọi đồng thời. Chính sách bất biến thường dễ chia sẻ nhưng mechanism vẫn có thể chứa state:

~~~text
Shared around engine
    Policy immutable     -> safe to share as value
    Mutable event buffer -> needs synchronization or thread-safe sink
    Current request ID   -> must not be shared mutable field
    Retry attempt index  -> per invocation local variable
~~~

Nếu advice lưu currentPolicy vào một mutable field để đổi theo mỗi invocation:

~~~text
Thread A sets currentPolicy = AUDIT
Thread B sets currentPolicy = TRACE
Thread A proceeds expecting AUDIT, sees TRACE
~~~

Đây là context mixing. Tốt hơn là truyền Policy/reference qua local variable hoặc per-invocation context.

### 19.1. Per-target aspect cũng có thể concurrent

Một aspect instance gắn mỗi target không mặc nhiên thuộc một thread. Một target có thể được nhiều requests gọi. Introduced mutable fields, caches hoặc counters cần thread-safety tùy yêu cầu.

### 19.2. ThreadLocal không thay policy registry

ThreadLocal có thể lưu request context cho helper cùng thread, nhưng không phải nơi mặc định tốt để lưu mọi policy. Nó cần cleanup trong finally và không tự theo async work. Một policy immutable/versioned trong registry với per-request snapshot thường rõ hơn.

### 19.3. Async propagation

Nếu advice trả CompletableFuture khi task chưa hoàn tất, after returning của wrapper có thể chỉ nhìn thấy future được tạo. Chính sách đo completion của task phải gắn vào completion boundary, truyền context hợp lệ và cleanup state khi task kết thúc; không coi scheduling success là business success.

## 20. Lựa chọn cấu hình tĩnh hay policy nạp runtime

| Tiêu chí | Compile/configure-time policy | Runtime-loaded policy |
|---|---|---|
| Khi đổi rule | Thường cần reconfigure/build/deploy | Có thể reload |
| Type safety | Có cơ hội kiểm tra nhiều thứ sớm | Cần schema validation |
| Độ phức tạp runtime | Thường thấp hơn | Lookup, versioning, consistency |
| Khả năng audit | Dễ gắn với artifact version | Cần policy ID/version logs |
| Rủi ro | Rule lỗi lan qua deploy | Reload sai giữa chừng, stale nodes |
| Testing | Fixtures cố định | Cần old/new/in-flight cases |

Không phải càng dynamic càng tốt. Nếu policy là invariant quan trọng và ít đổi, explicit immutable config lúc deploy có thể an toàn và dễ hiểu hơn remote policy resolution mỗi lần gọi.

### 20.1. Runtime policy thay đổi ngoài ý muốn

Nếu registry dùng một Map mutable và nhiều threads update trực tiếp, có thể thiếu happens-before hoặc thấy inconsistent data. Dùng snapshot publication hoặc synchronization đúng.

### 20.2. Không nạp code tùy ý từ nguồn không đáng tin

Nếu policy dưới dạng expressions/scripts hoặc plugins, cần sandbox/security review, validation, resource limits và khả năng audit. Cơ chế advice có quyền chặn/mở business operation nên policy code có thể thành attack surface.

## 21. Thiết kế để tránh policy explosion

Một hệ thống quá tham số hóa có thể tạo:

~~~text
Policy A -> 12 flags
Policy B -> 12 flags
Policy C -> 12 flags
... mọi tổ hợp đều có thể được tạo
~~~

Nếu flags tương tác, số combinations tăng nhanh và khó test hết. Giải pháp:

1. Nhóm cấu hình theo concern: logging, retry, security, metrics.
2. Sử dụng enums/named modes cho mutually exclusive choices.
3. Ràng buộc combinations không hợp lệ trong constructor/factory.
4. Dùng sealed policies nếu cần các variants có cấu trúc khác nhau.
5. Tách aspects có **control-flow contract** khác nhau.
6. Định nghĩa immutable defaults được review, không phụ thuộc những field optional khó hiểu.
7. Có unit tests cho từng policy mode và integration tests cho composition.

**Tái sử dụng không có nghĩa mọi thứ phải có cùng interface.** Một interface quá tổng quát như Policy.execute(Object[]) rất khó type-check, document và test.

## 22. So sánh trước và sau refactor

### 22.1. Trước: lặp advice

~~~text
CreateAdvice:
    log start
    try proceed, log success, catch log error, rethrow
    finally cleanup

DeleteAdvice:
    log start
    try proceed, log success, catch log error, rethrow
    finally cleanup

UpdateAdvice:
    log start
    try proceed, log success, catch log error, rethrow
    finally cleanup
~~~

Sửa logic cleanup hoặc redaction phải sửa ba nơi.

### 22.2. Sau: shared mechanism và policy mapping

~~~text
LoggingMechanism:
    captures invocation
    calls proceed once
    handles success/error/finally consistently

PolicyRegistry:
    create -> AUDIT_CREATE
    delete -> AUDIT_DELETE
    update -> AUDIT_UPDATE
~~~

Các policies khác nhau theo operation scope, event types, redaction và severity; tất cả dùng cùng tested execution skeleton.

### 22.3. Lợi ích được kiểm chứng thế nào?

- Số bản copy của try/catch/finally giảm.
- Một fix exception propagation áp dụng cho mọi variants.
- Unit tests policy logic độc lập với AOP weaving.
- Integration tests xác minh pointcut binding và advice precedence.
- Review security rules đơn giản hơn vì redaction policy được định nghĩa nhất quán.
- Có thể thêm operation mới bằng validated policy entry khi semantics giữ nguyên.

### 22.4. Trường hợp refactor có thể thất bại

Nếu CreateAdvice trước đây bắt exception và trả fallback còn DeleteAdvice phải rethrow, gộp thành một LoggingMechanism luôn rethrow có thể thay business contract. Cần tách concern hoặc mô hình hóa chính sách exception translation một cách tường minh, rồi kiểm tra caller contract.

Không chỉ so số dòng mã để tuyên bố refactor tương đương.

## 23. Thiết kế kiểm thử theo hai tầng

### 23.1. Unit test mechanism

Với một fake continuation có đếm số lần gọi:

- Policy không chọn operation: proceed một lần, không emit event.
- Success được chọn: proceed một lần, đúng order before/success/finally.
- Failure được chọn: exception được preserve/rethrow.
- Log failure bị tắt: exception vẫn thoát.
- Redaction bật: không có error message nhạy cảm.
- Logging sink throw: exception policy được thực hiện như thiết kế.
- Around short-circuit chỉ khi concern cho phép và có contract.
- Finally vẫn chạy khi proceed throw.
- Policy immutable không bị đổi khi caller mutate collection ban đầu.

### 23.2. Unit test policies

- Operation allowlist/denylist.
- Mode log success/failure.
- Redaction theo data classification.
- Threshold/sampling.
- Missing policy defaults.
- Policy version và validation.
- Security deny/allow theo trusted context.
- Retry classifier và max attempts.
- Invalid combinations bị reject khi khởi tạo.

### 23.3. Integration test AOP binding

- Pointcut thực sự match đúng methods/operations.
- Không áp advice sai vào helper không thuộc scope.
- Precedence giữa Audit/Trace/Transaction phù hợp semantics.
- Direct target/self-invocation không bypass bảo mật ngoài dự kiến.
- Generic/overloaded methods có pointcut đúng.
- Nested calls không tạo log trùng ngoài policy.
- Exception từ target/advice được quan sát đúng boundary.
- Async completion/context propagation đúng.

### 23.4. Regression test cho policy reload

- Request đang chạy dùng snapshot policy nào?
- Version cũ được dọn/giữ bao lâu?
- Invalid new policy có bị reject mà không phá old policy?
- Nhiều nodes có log đúng version đang dùng?
- Thay đổi config không tạo data race hoặc leak state.

## 24. Ma trận tình huống thực hành

| Tình huống | Chính sách | Behavior kỳ vọng |
|---|---|---|
| Create thành công | AUDIT, TRACE | Hai policies active theo precedence |
| Delete thành công | AUDIT | Chỉ event của AUDIT |
| Read không chọn | AUDIT/TRACE đều skip | Proceed, không emit log |
| Create throw | AUDIT redact failure | Lỗi vẫn được rethrow |
| Failure logging disabled | TRACE | Không log failure nhưng không nuốt lỗi |
| Policy config thiếu | Security fail-closed | Không tự allow operation |
| Request chứa secret | Redaction mandatory | Không log raw token/payload |
| Policy immutable | Set.copyOf | Caller không mutate selection set |
| Policy version đổi | Snapshot | Một invocation dùng version nhất quán |
| Retry attempt | RetryPolicy | Không vượt limit, idempotency rõ |
| Async task | CompletionPolicy | Không log task success ngay khi schedule |
| Logging sink down | Explicit failure mode | Không ngẫu nhiên che original error |
| Multiple aspects | Precedence configured | Log/transaction semantics đúng |
| Method overload | Pointcut method identity | Không lẫn các overloads |
| Direct target call | Coverage tested | Không bypass required enforcement |
| Shared mutable collaborator | Thread safety | Không race/context mixing |
| Rate limit exact | Atomic reservation | Không check-then-increment race |
| Audit committed event | Transaction-outcome policy | Không gọi success trước commit |
| New operation | Validated registry entry | Không phải copy advice skeleton |

## 25. Các lỗi thường gặp

**Lỗi 1 — Chép nguyên advice chỉ để thay một ngưỡng.** Sửa chung sẽ không đồng bộ.

**Lỗi 2 — Chỉ dùng named pointcut mà vẫn copy/paste toàn bộ advice body.** Chưa giải quyết duplication của mechanism.

**Lỗi 3 — Dùng một giant aspect có hàng chục booleans.** Tạo nhiều tổ hợp khó kiểm chứng.

**Lỗi 4 — Policy có thể gọi proceed tùy ý khi thực sự chỉ cần ghi log.** Làm thay control-flow contract.

**Lỗi 5 — logFailure=false nghĩa là nuốt exception.** Không; log selection và business error propagation độc lập.

**Lỗi 6 — Logging success đồng nghĩa transaction committed.** Không nếu boundary chưa bao commit.

**Lỗi 7 — Một immutable Policy khiến toàn bộ system thread-safe.** Target/sink/collaborators có thể mutable.

**Lỗi 8 — Dùng mutable field currentPolicy trong shared advice.** Có thể mix policies giữa threads.

**Lỗi 9 — Mỗi hook đọc một policy version khác.** In-flight invocation bị inconsistent.

**Lỗi 10 — Để user input chọn authorization policy đặc quyền.** Tạo privilege escalation.

**Lỗi 11 — Thiếu policy thì allow tất cả.** Không phù hợp với fail-closed security requirements.

**Lỗi 12 — Log raw result hoặc exception message theo một flag tiện lợi.** Có thể làm lộ dữ liệu.

**Lỗi 13 — Shared retry mechanism mà không xét idempotency.** Có thể nhân đôi side effects.

**Lỗi 14 — Gắn runtime guard vào mọi helper.** Tăng overhead candidate checking không cần thiết.

**Lỗi 15 — Runtime filter thay thế pointcut coverage.** Một method không bị intercept sẽ không qua policy.

**Lỗi 16 — Gộp audit bắt buộc và telemetry best-effort thành cùng failure mode.** Hai concerns có contracts khác nhau.

**Lỗi 17 — Config loading không validation.** Lỗi chỉ xuất hiện ở runtime sau deploy.

**Lỗi 18 — Tái sử dụng advice mà không kiểm soát precedence.** Thứ tự có thể làm log outcomes sai.

**Lỗi 19 — Thay operation name mà quên policy registry.** Coverage có thể bị mất im lặng.

**Lỗi 20 — Chỉ unit test policy object, không test actual weaving/proxy boundary.** Có thể không hề có invocation được bảo vệ.

## 26. Quy trình thiết kế một advice tái sử dụng

1. **Liệt kê các bản advice đang trùng nhau** và chỉ ra những dòng khác nhau.
2. **Xác định invariant chung**: số lần proceed, exception propagation, resource cleanup, event semantics.
3. **Tách những khác biệt thành policy fields hoặc Strategy methods**.
4. **Chọn representation có nghĩa**: named enum, record, interface thay vì nhiều flags lẫn lộn.
5. **Validate policy khi tạo** và document defaults/missing policy behavior.
6. **Thu hẹp pointcut candidate set** bằng tiêu chí tĩnh nếu có thể.
7. **Xác định runtime policy lookup** theo operation và trusted context.
8. **Capture immutable policy/context snapshot** mỗi invocation khi cần.
9. **Giữ mechanism stateless** hoặc bảo vệ shared mutable collaborators.
10. **Thiết kế exception policy** rõ cho business failure, policy failure, logger failure.
11. **Kiểm tra các concerns làm đổi control flow** như retry/security riêng.
12. **Cấu hình precedence** với transaction, logging, security và các aspects khác.
13. **Viết unit tests** cho mechanism và cho từng policy độc lập.
14. **Viết integration tests** cho pointcut, weaving, proxy, self-invocation, async.
15. **Đo chi phí runtime** sau khi đã chứng minh correctness.
16. **Ghi decision record** để người sau biết vì sao sử dụng parameterization và ranh giới của nó.

## 27. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Ba advice khác nhau chỉ ở danh sách methods và mức log, nên chọn gì?

**Đáp:** Xem xét một reusable advice mechanism với ba policy configs, sau khi chứng minh lifecycle/exception semantics chung.

**Câu 2.** Một named pointcut có giải quyết việc ba advice copy cùng try/catch không?

**Đáp:** Không hoàn toàn; nó tái sử dụng pointcut selection, còn thân advice cần mechanism abstraction.

**Câu 3.** Policy logFailure=false có nghĩa throw từ target được nuốt không?

**Đáp:** Không. Chính sách ghi log độc lập với exception propagation.

**Câu 4.** Tại sao nên dùng Set.copyOf với tập operations?

**Đáp:** Để policy không bị mutate qua collection reference do caller cung cấp; đây là một phần của immutable policy design.

**Câu 5.** Java record có mặc định deep immutable không?

**Đáp:** Không, object references bên trong vẫn có thể trỏ mutable objects.

**Câu 6.** Nếu có 20 booleans trong policy, nên làm gì?

**Đáp:** Xem xét enum/named modes, Strategy hoặc tách concerns; validate invalid combinations.

**Câu 7.** Một policy registry chỉ return "allow" khi không tìm thấy config có an toàn không?

**Đáp:** Không với authorization bắt buộc; missing policy cần explicit fail-closed contract nếu yêu cầu.

**Câu 8.** Vì sao policy version cần được capture đầu invocation?

**Đáp:** Để before/after/failure trong cùng operation không vô ý dùng rules khác nhau sau reload.

**Câu 9.** Nếu policy logging throw khi business đã throw, rủi ro là gì?

**Đáp:** Có thể che original error hoặc đổi transaction behavior; cần xử lý failure của sink theo contract.

**Câu 10.** Có thể dùng cùng mechanism cho Logging và Retry không?

**Đáp:** Có thể chia sẻ vài utilities, nhưng retry có thể gọi proceed nhiều lần còn logging thường quan sát một continuation; không gộp khác biệt control flow vô tội vạ.

**Câu 11.** Vì sao đặt policy lookup bên trong shared mutable field currentPolicy nguy hiểm?

**Đáp:** Các threads có thể ghi chồng và áp sai policy của request khác.

**Câu 12.** Dynamic policy selection có thay pointcut không?

**Đáp:** Không hoàn toàn; nó chỉ xử lý những joins mà mechanism thực sự được áp vào.

**Câu 13.** Nếu chỉ cần đo elapsed time toàn operation, có cần copy một advice cho từng method không?

**Đáp:** Thường không; một around mechanism và threshold/operation policy là phù hợp.

**Câu 14.** Ghi success sau method return có chứng minh DB commit không?

**Đáp:** Không nếu transaction completion nằm ngoài boundary được quan sát.

**Câu 15.** Làm sao kiểm tra refactor policy giữ behavior cũ?

**Đáp:** Characterization tests trước/sau, unit tests cho mechanism/policies và integration tests cho pointcut/precedence/exception paths.

**Câu 16.** Tái sử dụng mechanism có buộc mọi policy cùng failure mode không?

**Đáp:** Không. Failure mode là contract phải cấu hình/tách riêng một cách rõ, đặc biệt giữa telemetry và audit/security.

## 28. Sơ đồ ghi nhớ

~~~text
     Nhiều advice có logic gần giống nhau?
                    |
                    v
         Khác nhau do POLICY hay SEMANTICS?
               /                \
           POLICY              SEMANTICS
              |                   |
              v                   v
      Shared around engine      Tách mechanisms
              |                / security / retry
              v
      Validated immutable
         Policy objects
        /       |       \
       v        v        v
   Selection  Events  Redaction
       \        |       /
        +-------+------+
                |
                v
      One consistent lifecycle
   before -> proceed -> success/failure
                |
                v
       finally cleanup / rethrow
                |
                v
       Tests + versioning + metrics
       pointcuts / context / async
~~~

**Kết luận:** Tham số hóa chính sách trong AOP là tách **quy trình interception có thể dùng chung** khỏi **những quyết định thay đổi theo operation hoặc ngữ cảnh**. Nó giúp giảm duplication, thống nhất redaction, exception handling và lifecycle. Tuy nhiên phải phân biệt điểm chọn join point với runtime policy selection, giữ semantics của proceed và exception, dùng immutable policy snapshots, bảo vệ shared state, xét precedence/async/transaction và không nhồi những concerns có control-flow contracts khác nhau vào một siêu advice. Thiết kế tốt là **dễ hiểu, dễ test và đúng hợp đồng**, không đơn thuần có ít dòng code hơn.

## Tài liệu tham khảo

- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): pointcut, advice, around, abstract pointcuts và aspect abstraction trong một ngôn ngữ AOP.
- [Java SE 17 — Records](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): nền tảng record values.
- [Java SE 17 — Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): unmodifiable sets và Set.copyOf.
- [Java SE 17 — Callable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html): continuation abstraction minh họa.
- [Java Language Specification SE 17 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): exception propagation và contracts.
- [Java Language Specification SE 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): memory model, synchronization và safe publication.

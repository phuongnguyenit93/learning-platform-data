# Advice bao quanh và quyền kiểm soát luồng thực thi

## 1. Bản chất của around advice

Trong **Aspect-Oriented Programming (AOP)**, một **pointcut** chọn những **join point** mà hành vi xuyên suốt có thể được áp dụng. **Advice** là hành vi ấy; **around advice** (advice bao quanh) có vị trí đặc biệt vì nó không chỉ làm việc *trước* hoặc *sau* điểm được chọn: nó thường có **quyền quyết định có tiếp tục vào phần thực thi bên trong hay không, tiếp tục khi nào, và kết quả hoặc ngoại lệ nào được trả ra**.

Hãy tưởng tượng lời gọi nghiệp vụ:

```text
caller -> operation(input) -> result/error
```

Khi có một around advice, đường đi có thể trở thành:

```text
caller
  |
  v
around advice
  |-- thực hiện hành vi trước
  |-- [tiếp tục vào join point hoặc chuỗi advice bên trong]
  |-- thực hiện hành vi sau
  |-- [có thể xử lý/thay đổi result hoặc error]
  v
caller
```

Phần trong ngoặc vuông **không mặc nhiên phải chạy**: tùy công cụ và hợp đồng, around advice có thể tiếp tục vào target một lần, không lần nào hoặc nhiều lần. Vì thế đây là công cụ mạnh nhưng dễ làm thay đổi tính đúng đắn của chương trình.

Bài học này giúp bạn:

1. Hiểu **around advice**, **proceed** và ranh giới điều khiển so với before/after advice.
2. Phân tích các trường hợp **tiếp tục, chặn, thay kết quả, sửa đối số, ném/chuyển lỗi, gọi lại** và các hệ quả hợp đồng.
3. Hiểu thứ tự lồng nhau của nhiều advice, quy tắc cleanup và xử lý ngoại lệ.
4. Phân biệt **proxy**, **weaving** và những đường lời gọi mà advice thực sự nhìn thấy.
5. Tự chạy ví dụ Java 17 minh họa quanh một lời gọi interface bằng dynamic proxy.
6. Biết khi nào nên dùng around advice và khi nào cần cơ chế tường minh hơn như decorator, domain policy hoặc workflow.

**Phạm vi:** Đây là kiến thức **AOP nói chung**. Không có một cú pháp around advice hay `proceed` duy nhất bắt buộc mọi ngôn ngữ/công cụ tuân theo. Tập join point, thời điểm weaving, cách truyền đối số, kiểu kết quả và số lần được phép tiếp tục phải kiểm chứng ở công cụ cụ thể.

## 2. Các khái niệm cần thống nhất trước khi điều khiển luồng

| Khái niệm | Nghĩa trong bài | Lưu ý |
| --- | --- | --- |
| **Concern** | Nhu cầu xuyên suốt như đo latency, audit, retry hoặc điều phối kỹ thuật ở nhiều vị trí. | Không phải mọi quy tắc nghiệp vụ đều nên ẩn vào aspect. |
| **Join point** | Sự kiện/điểm thực thi được mô hình AOP hỗ trợ, ví dụ một lần method execution hoặc method call. | Không đồng nghĩa một dòng source duy nhất. |
| **Pointcut** | Predicate/quy tắc chọn các join point cần advice. | Có thể dùng thông tin tĩnh và/hoặc ngữ cảnh runtime. |
| **Target** | Mã/đối tượng thực thi công việc chính. | Lời gọi có thể đi qua nhiều advice trước target. |
| **Around advice** | Lớp xử lý bao quanh phần bên trong join point theo cơ chế AOP. | Có thể thay đổi flow và kết cục nếu công cụ cho phép. |
| **Proceed / continuation** | Thao tác tiếp tục thực thi phần bên trong advice hoặc target. | Không nhất thiết đi thẳng vào target; có thể là advice kế tiếp. |
| **Weaving/interception** | Cách kết hợp advice với mã đang chạy. | Runtime proxy, class proxy, biến đổi source/bytecode hoặc công cụ khác. |

Trong một số API, `proceed()` là method do công cụ cung cấp. Trong những API khác, continuation có thể là callback, hàm bọc, closure hoặc lời gọi tới object gốc. Dù hình thức khác, hãy luôn hỏi: **“Khi gọi tiếp, chính xác phần nào sẽ chạy?”**

### 2.1. Around advice khác before và after ở mức quyền điều khiển

- **Before:** Thường chạy trước join point đã chọn; có thể gây thất bại bằng cách ném lỗi nhưng không nhất thiết cung cấp cơ chế chọn số lần gọi target.
- **After returning:** Phản ứng khi điểm kết thúc bình thường.
- **After throwing:** Phản ứng khi điểm kết thúc bằng ngoại lệ thoát ra.
- **After/finally:** Dọn dẹp hoặc ghi nhận khi kết thúc qua các đường hợp lệ.
- **Around:** Có thể tổ chức cả các hành vi trên trong một cấu trúc bao quanh **và chủ động gọi hoặc không gọi phần thực thi bên trong**.

Không đồng nhất “around có thể làm mọi việc” với “nên dùng around cho mọi concern”. Nếu chỉ cần bộ đếm khi method trả về, advice sau khi trả về có thể diễn đạt ý định rõ và giảm nguy cơ vô tình bỏ qua target.

### 2.2. Vì sao continuation là ranh giới kiến trúc quan trọng?

Một câu lệnh thường gặp ở around advice:

```text
result = proceed()
```

mang nhiều ý nghĩa đồng thời: chuyển quyền điều khiển vào phần bên trong, chấp nhận rằng side effect có thể xảy ra, chờ phần đó trả kết quả hoặc ném lỗi, rồi tiếp tục đoạn code phía sau của around advice.

Không phải mọi engine đều bảo đảm `proceed` chỉ gọi target một lần. Khi có nhiều aspect, nó có thể chạy chuỗi advice bên trong; do vậy chính advice bên trong lại có thể bỏ qua hoặc chạy nhiều lần. Để phân tích đúng, phải xét **toàn bộ chuỗi continuation**, không chỉ một wrapper.

## 3. Mô hình điều khiển: ba đường đi cơ bản

Giả sử target `charge()` được chọn và around advice có quyền bao quanh.

### 3.1. Tiếp tục một lần

```text
around:
    before()
    result = proceed()
    after()
    return result
```

Luồng là `before → target/inner advice → after` trên đường thành công. Nếu `proceed()` ném lỗi thì `after()` viết ngay phía sau **không chạy**, trừ khi có `finally` hoặc `catch` phù hợp.

Dùng khi muốn quan sát latency, correlation, logging kỹ thuật, nhưng vẫn cần xác định hành vi nếu chính `before`/`after` ném lỗi.

### 3.2. Không tiếp tục

```text
around:
    if resultCanBeReused():
        return cachedResult
    return proceed()
```

Ở nhánh cache hit, target **không chạy**. Điều này có thể hợp lý nếu giá trị cache còn hiệu lực, hợp đồng cho phép bỏ qua target và không bỏ sót side effect cần thiết.

Các ví dụ khác: từ chối yêu cầu tại biên, trả fallback, mô phỏng kết quả trong test, rate limiting. Tuy nhiên, chặn một thao tác nghiệp vụ có side effect không phải quyết định nhẹ: caller có thể tưởng thao tác đã được thực hiện nếu advice trả về một “kết quả thành công” giả.

### 3.3. Tiếp tục nhiều lần

```text
around:
    for attempt in allowedAttempts:
        try:
            return proceed()
        catch transientFailure:
            if canRetrySafely():
                continue
            throw
```

Đây là cách diễn đạt ý tưởng **retry**, không phải cú pháp chạy trực tiếp. Nếu cho phép gọi tiếp nhiều lần, target hoặc advice bên trong có thể thực thi nhiều lượt. Phải xác định phương thức có **idempotent** không, có thể tạo side effect nào, ngoại lệ nào có thể thử lại, backoff/timeout tổng, số lần tối đa và cách chống lặp.

Một số engine **không hỗ trợ** gọi continuation nhiều lần theo ngữ nghĩa bạn mong muốn. Trước khi thiết kế retry bằng around advice, phải xác minh tài liệu công cụ và chạy thử cùng target có side effect để hiểu contract.

## 4. `proceed`: quyền tiếp tục chứ không đơn thuần là “gọi hàm đích”

### 4.1. `proceed()` thường có một continuation cụ thể

Ví dụ có hai around advice A và B, trong đó A ở ngoài B:

```text
caller
  |
  v
A.before
  |
  v
A.proceed() ---> B.before
                   |
                   v
                B.proceed() ---> target
                   |
                B.after
  |
A.after
  |
caller
```

Nếu cả hai gọi tiếp đúng một lần và target trả về bình thường, thứ tự dễ dự đoán:

```text
A before
B before
TARGET
B after
A after
```

Nếu B **không gọi tiếp**, target không chạy, nhưng A vẫn có thể nhìn thấy **một kết quả trả về bình thường** từ B. Nếu B tự ném lỗi thì A có thể thấy lỗi đó trong `catch`. Nếu A không gọi tiếp, B và target không được chạm tới ở đường đó.

### 4.2. Thứ tự advice ảnh hưởng đến ngữ nghĩa

Đảo thứ tự thành B ngoài A sẽ đảo vùng quan sát. Ví dụ, đặt đo latency ở ngoài retry đo **toàn bộ khoảng thời gian nhiều lần thử**, còn đo latency bên trong retry có thể đo **mỗi attempt** riêng.

Với cache, một thứ tự có thể kiểm tra cache trước khi ghi trace của target; thứ tự khác ghi lại cả cache hit. Với audit, việc ghi “thành công” trước transaction commit không có cùng ngữ nghĩa với xác nhận kết quả bền vững sau commit.

Không dựa vào thứ tự viết file, tên class hoặc thứ tự load tình cờ. Hãy xác nhận quy tắc precedence/order của công cụ và có test ghi nhận thứ tự thực tế.

### 4.3. Kiểu kết quả và đối số phải tuân theo hợp đồng

Một continuation có thể có chữ ký tương đương:

```text
proceed(): Result
proceed(newArguments): Result
```

Các chữ ký này chỉ là giả mã. Không phải công cụ AOP nào cũng cho phép thay đối số khi tiếp tục; với cơ chế proxy tự viết, handler có thể chuyển một mảng đối số khác vào target. Khi được phép, cần giữ đúng số lượng, thứ tự, kiểu, quy tắc `null`, generic/primitive và những bất biến của phương thức.

Tương tự, around advice trả kết quả thay thế phải tương thích return type theo hợp đồng. Nếu method Java có kiểu `int`, cố trả `null` từ handler có thể dẫn tới lỗi khi unboxing; nếu trả object sai kiểu có thể phát sinh `ClassCastException` hoặc lỗi khác khi caller nhận kết quả. Với `void`, không nên dùng giá trị trả về như tín hiệu nghiệp vụ tùy ý.

## 5. Around advice có thể can thiệp vào năm thứ khác nhau

### 5.1. Trước khi target chạy

Một advice có thể ghi thời điểm bắt đầu, khởi tạo span, kiểm tra ngưỡng kỹ thuật hoặc gắn context. Điều này tương tự before advice nhưng thuộc lớp around bao quanh.

**Cần lưu ý:** Nếu thao tác trước `proceed` lỗi, target có thể **không được gọi**. Đây là thay đổi quan sát được ở caller; chính sách “best-effort logging” không nên vô tình làm hỏng nghiệp vụ vì backend log tạm thời thất bại.

### 5.2. Quyết định có gọi tiếp hay không

Bằng cách `return` sớm hoặc `throw`, around advice có thể chặn phần bên trong. Ví dụ:

```text
if exceededRateLimit:
    throw TooManyRequests
else:
    return proceed()
```

Giả mã này biểu đạt rate limiting tại một **biên có hợp đồng rõ**. Trả lỗi từ advice khác với target đã thực hiện một phần công việc rồi lỗi. Nếu logic cho phép chặn là chính sách bảo mật/ủy quyền, còn phải bảo đảm **mọi đường đi cần được bảo vệ thực sự đi qua điểm can thiệp**; một proxy bị bypass không phải lớp bảo vệ duy nhất đáng tin.

### 5.3. Thay đổi input trước khi tiếp tục

Nếu công cụ hỗ trợ, advice có thể chuẩn hóa dữ liệu kỹ thuật:

```text
newArgs = sanitizeForProtocol(originalArgs)
return proceed(newArgs)
```

Nhưng “sanitize” không được âm thầm sửa lệnh nghiệp vụ hoặc đổi đối tượng được ủy quyền. Những biến đổi đầu vào ảnh hưởng giá trị đơn hàng, quyền truy cập hoặc logic tính toán cần có vị trí tường minh và test domain.

### 5.4. Thay đổi kết quả sau khi tiếp tục

```text
result = proceed()
return decorateResult(result)
```

Ví dụ chuyển đổi một đối tượng kết quả thành wrapper thống nhất ở biên giao tiếp. Phải kiểm soát type, `null`, identity, immutability và side effect. Nếu method vốn chỉ trả trạng thái thành công sau khi thao tác bền vững, advice không nên tự dựng kết quả làm caller hiểu sai rằng commit đã xong.

### 5.5. Bắt, truyền hoặc biến đổi ngoại lệ

```text
try:
    return proceed()
catch error:
    recordFailureBestEffort(error)
    throw same error
```

Nếu mục tiêu chỉ là quan sát, **ném lại ngoại lệ gốc** thường là lựa chọn bảo toàn hợp đồng. Nếu chuyển `IOException` thành lỗi domain hoặc fallback, cần chính sách có chủ đích, phân biệt loại lỗi được chuyển và giữ `cause` thích hợp. Tránh che lỗi gốc bằng lỗi logging/cleanup.

## 6. Cấu trúc `try/catch/finally` quanh `proceed`

Với around advice đo thời gian, một cấu trúc điển hình:

```text
start = monotonicClock()
try:
    return proceed()
catch error:
    recordFailure(error)
    throw same error
finally:
    recordDuration(monotonicClock() - start)
    closeContext()
```

Đây là giả mã tổng quát. `monotonicClock` là nguồn thời gian đơn điệu (không phụ thuộc chỉnh lại đồng hồ lịch) dùng để đo khoảng thời gian. Thời gian đo **bao gồm những lớp advice nằm bên trong**, không chỉ thân target.

### 6.1. Khi `proceed` trả về bình thường

- Giá trị từ phần bên trong được đưa về around advice.
- Around advice có thể giữ nguyên, biến đổi hoặc thay thế nó.
- `finally` vẫn cần dọn context trên đường `return`.
- Thông điệp “thành công” có thể chỉ nghĩa **execution trả về bình thường**, chưa chắc nghĩa **giao dịch đã commit** hoặc công việc async đã hoàn thành.

### 6.2. Khi `proceed` ném lỗi

- `catch` của advice ngoài có thể thấy ngoại lệ **thoát qua vùng continuation**.
- Nếu advice dưới bắt lỗi rồi trả fallback, advice trên có thể thấy kết quả bình thường.
- Nếu advice dưới đổi lỗi, advice trên thấy lỗi mới.
- `finally` thường chạy khi unwind dù có lỗi, nhưng chính code trong `finally` cũng có thể ném lỗi và **che lỗi ban đầu**.

Với Java, nếu `recordDuration` ném lỗi khi target đã ném lỗi, caller có thể nhận lỗi đo lường thay vì lỗi target. Nếu instrumentation không bắt buộc ảnh hưởng nghiệp vụ, hãy bao các thao tác telemetry bằng chính sách lỗi best-effort rõ ràng. Không có giải pháp một dòng áp dụng được cho mọi mức độ quan trọng của audit, metrics và cleanup.

### 6.3. Bắt `Throwable` không đồng nghĩa nuốt mọi `Error`

Trong Java, `Throwable` gồm `Exception` và `Error`. Một implementation quanh `proceed` có thể cần giữ nguyên *mọi* throwable để cleanup, nhưng không nên “xử lý thành công” các `Error` nghiêm trọng bằng fallback ngẫu nhiên. Bắt → quan sát tối thiểu → ném lại khác với bắt → che lỗi.

### 6.4. Checked exceptions trong proxy

Khi tự dùng JDK dynamic proxy, nếu handler ném **checked exception** không phù hợp danh sách `throws` của method interface, proxy có thể bọc trong `UndeclaredThrowableException`. Nếu dùng reflection `Method.invoke`, exception của target bị bọc trong `InvocationTargetException` và cần gỡ `getCause()` một cách có chủ đích. Cơ chế weaving khác có thể có hợp đồng ngoại lệ khác.

## 7. Around advice và các khái niệm cache, retry, circuit breaker

### 7.1. Cache hit là trường hợp `proceed` có thể chạy 0 lần

```text
around readOperation(key):
    hit = cache.lookup(key)
    if hit is valid:
        return hit
    value = proceed()
    cache.store(key, value)
    return value
```

Những điều kiện cần trước khi dùng:

- Phương thức có thể được gọi là **read-like** hay có side effect quan trọng?
- Khóa cache có đủ tham số/tenant/user/locale/phiên bản dữ liệu?
- Kết quả lỗi hoặc giá trị `null` được cache theo chính sách nào?
- Có yêu cầu invalidation, TTL hoặc consistency?
- Có race giữa nhiều caller cùng cache miss không?
- Advice có thay đổi identity hoặc quyền truy cập dữ liệu không?

Cache skip có thể phù hợp với thao tác đọc thuần; rất nguy hiểm với thao tác “đọc đồng thời tăng số lượt xem” nếu việc tăng là side effect phải xảy ra.

### 7.2. Retry là trường hợp gọi continuation nhiều lần

Một retry đúng cần:

1. **Giới hạn số lần thử** và ngân sách thời gian tổng.
2. Chỉ retry các lỗi thực sự **transient** được công bố.
3. **Idempotency key** hoặc bảo đảm khác nếu thao tác có side effect.
4. Chiến lược **backoff/jitter** hợp lý, không tạo retry storm.
5. Phân biệt log **attempt failure** và **logical-operation failure**.
6. Xác định các lớp advice ở trong/ngoài retry; context từng lần thử được quản lý đúng.
7. Không retry theo phương pháp dựa vào exception message ngẫu nhiên.
8. Xác minh engine có cho phép gọi lại `proceed` với ngữ nghĩa phù hợp hay không.

Ví dụ một thao tác `transferMoney`: nếu lời gọi thứ nhất đã ghi nợ nhưng response bị mất, tiếp tục lần hai có thể trừ tiền lần nữa. Vấn đề nằm ở nghiệp vụ phân tán và idempotency, **không** được giải bằng việc chỉ thêm vòng `for` vào around advice.

### 7.3. Circuit breaker và giới hạn lưu lượng

Một around advice có thể trả fallback hoặc từ chối lời gọi khi một circuit đang mở. Nhưng trạng thái breaker có ý nghĩa theo endpoint/nguồn lỗi, cần concurrency control, time window, half-open probe và metrics chính xác. Nếu mọi giao dịch đều bị chặn bằng fallback “thành công”, hệ thống có thể mất tính đúng đắn.

Rate limiting có thể chặn trước target khi vượt hạn ngạch. Hãy xác định ranh giới tin cậy, tính nhất quán khi nhiều instance và exception/error contract, thay vì chỉ gắn một aspect tại vài method được gọi.

## 8. Ví dụ Java 17 hoàn chỉnh: continuation, skip và exception

Ta minh họa một **around advice** bằng JDK dynamic proxy. Đây là **một cơ chế mô phỏng AOP** với continuation do chính ta định nghĩa; nó không phải cú pháp phổ quát của mọi công cụ và không cung cấp mọi loại join point.

Cấu trúc:

- `TaskApi` là interface của target.
- `TaskService` thực hiện logic nghiệp vụ.
- `Proxy.newProxyInstance` tạo proxy để caller gọi qua.
- `traceAround` là around advice **bên ngoài**, ghi enter, returning/throwing và exit.
- `filterAround` là around advice **bên trong**, bỏ qua target nếu đối số là `"SKIP"`.
- `Proceed` là continuation mô phỏng `proceed` bằng Java functional interface.
- `invokeTarget` dùng reflection, gỡ wrapper để exception gốc tiếp tục tới caller.

Tạo file **`AroundControlDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AroundControlDemo {
    interface TaskApi {
        String run(String input);
    }

    static final class TaskService implements TaskApi {
        @Override
        public String run(String input) {
            System.out.println("TARGET " + input);
            if ("FAIL".equals(input)) {
                throw new IllegalStateException("target failed");
            }
            return "DONE:" + input;
        }
    }

    @FunctionalInterface
    interface Proceed {
        Object call() throws Throwable;
    }

    static Object traceAround(String methodName, Proceed next)
            throws Throwable {
        System.out.println("TRACE enter " + methodName);
        try {
            Object value = next.call();
            System.out.println("TRACE returning " + methodName);
            return value;
        } catch (Throwable original) {
            System.out.println("TRACE throwing "
                    + original.getClass().getSimpleName());
            throw original;
        } finally {
            System.out.println("TRACE exit " + methodName);
        }
    }

    static Object filterAround(Method method, Object[] args, Proceed next)
            throws Throwable {
        if (method.getName().equals("run")
                && "SKIP".equals(args[0])) {
            System.out.println("FILTER skip");
            return "SKIPPED";
        }
        return next.call();
    }

    static Object invokeTarget(TaskApi target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    static TaskApi wrapped(TaskApi target) {
        return (TaskApi) Proxy.newProxyInstance(
                TaskApi.class.getClassLoader(),
                new Class<?>[] { TaskApi.class },
                (proxy, method, args) ->
                        traceAround(method.getName(),
                                () -> filterAround(method, args,
                                        () -> invokeTarget(target, method, args)))
        );
    }

    public static void main(String[] args) {
        TaskApi target = new TaskService();
        TaskApi proxy = wrapped(target);

        System.out.println("CALLER " + proxy.run("A"));
        System.out.println("CALLER " + proxy.run("SKIP"));

        try {
            proxy.run("FAIL");
        } catch (IllegalStateException ex) {
            System.out.println("CALLER caught " + ex.getMessage());
        }

        System.out.println("CALLER " + target.run("DIRECT"));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac AroundControlDemo.java
java AroundControlDemo
```

**Stdout kỳ vọng:**

```text
TRACE enter run
TARGET A
TRACE returning run
TRACE exit run
CALLER DONE:A
TRACE enter run
FILTER skip
TRACE returning run
TRACE exit run
CALLER SKIPPED
TRACE enter run
TARGET FAIL
TRACE throwing IllegalStateException
TRACE exit run
CALLER caught target failed
TARGET DIRECT
CALLER DONE:DIRECT
```

### 8.1. Giải thích đường bình thường

`proxy.run("A")` vào `traceAround`. Advice ngoài in `TRACE enter run`, gọi continuation vào `filterAround`. `filterAround` không thấy `SKIP`, nên gọi tiếp `invokeTarget`, target in `TARGET A` rồi trả `DONE:A`. Advice ngoài in `TRACE returning run`, `finally` in `TRACE exit run`, sau cùng caller in kết quả.

Ở đường này, target thực thi **đúng một lần**.

### 8.2. Giải thích đường skip

`proxy.run("SKIP")` vẫn vào `traceAround` trước. Advice bên trong thấy đối số đặc biệt, in `FILTER skip` và trả `SKIPPED` **mà không gọi `next.call()`**. Vì vậy không có `TARGET SKIP`.

Điều quan trọng: advice ngoài thấy `filterAround` **trả về bình thường**, nên nó in `TRACE returning run`, dù target chưa từng chạy. Đây chính là lý do không đồng nhất “around trả kết quả thành công” với “target thực hiện thành công”.

`"SKIP"` chỉ là tín hiệu thực hành. Trong hệ thống thật, việc có được skip hay không cần dựa vào hợp đồng rõ về cache, policy hoặc trạng thái; không nên dựa vào một chuỗi input đặc biệt tùy tiện.

### 8.3. Giải thích đường lỗi

`proxy.run("FAIL")` đi qua cả hai advice rồi vào target. Target in `TARGET FAIL` trước khi ném `IllegalStateException`. Reflection bọc lỗi target vào `InvocationTargetException`; `invokeTarget` gỡ wrapper và ném đúng cause. `traceAround` ghi `TRACE throwing IllegalStateException`, ném lại cùng lỗi và chạy `finally`; caller bắt `IllegalStateException` và in message.

Nếu `filterAround` chọn trả fallback thay vì truyền lỗi, `traceAround` sẽ quan sát một lần return bình thường; các tầng advice không nhất thiết nhìn thấy cùng một kết cục.

### 8.4. Giải thích lời gọi không qua proxy

`target.run("DIRECT")` gọi trực tiếp vào đối tượng thật nên chỉ in `TARGET DIRECT`; không có dòng `TRACE` hoặc `FILTER`. JDK dynamic proxy chỉ chặn **lời gọi được thực hiện qua proxy**. Đây không phải giới hạn áp dụng nguyên xi cho mọi công cụ AOP có weaving bytecode.

### 8.5. Hệ quả của thứ tự advice

Đang dùng `traceAround` bên ngoài `filterAround`. Nếu đổi thành `filterAround` ở ngoài và `traceAround` ở trong, với input `SKIP`, `filterAround` có thể trả sớm **trước khi trace chạy**, nên không có dòng TRACE cho cache/skip. Hai thứ tự đo hai phạm vi khác nhau. Phải đặt theo mục tiêu quan sát, không đơn giản theo thứ tự thuận mắt.

### 8.6. Các giới hạn cố ý của ví dụ

- Demo chỉ có một method interface; không minh họa metadata pointcut DSL hay field/constructor join point.
- Không có policy retry, mutation đối số hoặc replacement result vượt ngoài nhánh skip; các quyền đó đã được phân tích ở phần khác.
- Không thể dùng demo này để suy ra mọi around advice của mọi engine cho phép nhiều lần `proceed`.
- Lệnh in log có thể có side effect và lỗi; đây chỉ là cách nhìn thấy thứ tự trong bài học.
- Với method checked exception, JDK proxy có quy tắc về `throws` và `UndeclaredThrowableException`; demo dùng unchecked exception để tránh nhầm lẫn khi tập trung vào continuation.
- `TaskService.run` có thể được gọi trực tiếp, nhấn mạnh nhu cầu bảo đảm call path khi sử dụng proxy trong ứng dụng thật.

## 9. Around advice trong môi trường bất đồng bộ

Một method Java có thể trả `CompletableFuture<Result>`, `CompletionStage<Result>` hoặc một handle bất đồng bộ khác. Around advice ở execution của method có thể thấy:

```text
enter method
  -> target lập lịch công việc
  -> trả future ngay
exit method
                  ... công việc chạy sau ...
                  -> future hoàn tất (success/failure)
```

Nếu advice chỉ đo từ trước `proceed()` đến khi `proceed()` trả future, số đo là **thời gian gọi/tạo tác vụ**, không phải toàn bộ thời gian xử lý. Tương tự, method trả future bình thường vẫn có thể tạo một future sau đó hoàn thành exceptionally.

Muốn quan sát **completion**, cần gắn hook tại future/task completion bằng API thích hợp, nhưng phải xác minh:

- Hook có vô tình **thay đổi result hoặc exception** của future trả cho caller không?
- Cancellation và timeout được ghi như success, failure hay trạng thái riêng?
- Callback chạy trên thread nào? Context có được truyền và dọn đúng?
- Nếu callback đo lường ném lỗi, stage nào bị ảnh hưởng?
- Thời gian end-to-end có tính cả queue delay, retry và scheduling không?

Ví dụ mã minh họa **không chạy độc lập**:

```java
CompletionStage<String> resultStage = invokeAsync();
resultStage.whenComplete((value, error) -> {
    if (error != null) {
        // Ghi failure theo policy; không làm lộ dữ liệu nhạy cảm.
    }
});
```

Đoạn này chỉ mô tả hook completion, giả định `invokeAsync()` đã tồn tại. Không giả định chỉ gọi `whenComplete` sẽ bảo toàn mọi chi tiết exception/cancellation; phải xem hợp đồng API, đặc biệt nếu callback ném lỗi hoặc dùng stage được trả về từ phép đăng ký.

### 9.1. Context và vòng đời tài nguyên

Một around advice tạo correlation ID hoặc span có thể dùng `ThreadLocal`. Nếu continuation chuyển công việc sang executor, context theo thread không tự theo sang task khác. Mở scope lúc bắt đầu và đóng scope trong `finally` ở thread ban đầu là một chuyện; đóng span khi task thực sự hoàn tất là chuyện khác. Tránh để tài nguyên “mở mãi” hoặc đóng quá sớm vì coi return của future là completion.

## 10. Proxy, weaving và giới hạn quyền kiểm soát

Không phải mọi engine AOP nhìn thấy cùng những sự kiện, dù tên advice cùng là “around”.

### 10.1. Interface proxy

Với dynamic proxy theo interface:

```text
caller -> proxy/handler -> target.method(...)
caller ----------------> target.method(...)   // đi tắt
```

Chỉ đường đầu đi qua advice trong handler. Lời gọi nội bộ trên `this` ở target không mặc nhiên quay lại proxy. Một around advice không thể kiểm soát luồng thực thi mà cơ chế của nó chưa từng nhận.

### 10.2. Class proxy

Một số công nghệ tạo proxy dựa trên lớp/subclass hoặc bytecode đặc thù. Khả năng can thiệp có thể phụ thuộc `final`, `private`, `static`, constructor, visibility, dispatch và cách đối tượng được tạo. Không nên suy từ interface proxy rằng class proxy sẽ có tập điểm hệt nhau.

### 10.3. Weaving vào source/bytecode

Weaving có thể chèn hoặc biến đổi hành vi ở compile-time, load-time hoặc một thời điểm công cụ hỗ trợ. Tập join point có thể rộng hơn proxy đơn giản, nhưng phụ thuộc cấu hình build, classloader, loại instruction và phiên bản runtime.

Một pointcut khớp method trên giấy không chứng minh mã đang chạy đã được weave. Phải xác nhận artifact thật, danh sách lớp trong phạm vi và positive/negative integration tests.

### 10.4. Quyền điều khiển chỉ có giá trị trong phạm vi được bảo đảm

Nếu dùng around advice để bảo vệ thao tác có tính an ninh cao, có đường gọi trực tiếp target hoặc module chưa được weave là một lỗ hổng lớn. Những bất biến như quyền sở hữu dữ liệu, hạn mức giao dịch hoặc kiểm soát trạng thái quan trọng nên được áp ở **biên tin cậy và mô hình nghiệp vụ**, thay vì phụ thuộc hoàn toàn vào một lời khuyên “gắn aspect là đủ”.

## 11. Các rủi ro nâng cao của around advice

### 11.1. Tính trong suốt của hợp đồng (semantic transparency)

Một advice quan sát được xem là “trong suốt” khi caller nhận cùng **giá trị, exception, side effect, thứ tự hợp lệ** như không có advice, trừ overhead/telemetry được công bố. Around advice có thể phá điều này bằng skip, gọi lặp, đổi đối số, biến đổi kết quả hoặc exception.

Cần ghi rõ: advice **chỉ quan sát**, **chuyển đổi có hợp đồng** hay **điều phối control flow**. Không quảng cáo một aspect điều phối thành “chỉ thêm log”.

### 11.2. Reentrancy và đệ quy không mong muốn

Một advice ghi metric bằng một method cũng bị pointcut chọn có thể tạo vòng:

```text
around advice
  -> metrics.record()
       -> around advice
            -> metrics.record()
                -> ...
```

Cần giới hạn pointcut và loại trừ code instrumentation, không chỉ dùng cờ tạm thời mà bỏ qua tính thread-safe và cleanup. Nếu engine hỗ trợ chọn theo luồng điều khiển (*control-flow pointcut*), hãy xác minh ngữ nghĩa trong recursion và async.

### 11.3. Thread safety và trạng thái aspect

Một aspect singleton giữ biến mutable `currentStartTime` có thể bị caller đồng thời ghi đè, dẫn tới số đo sai. Thời điểm bắt đầu thường nên nằm trong **local variable của lần invocation** hoặc một context được quản lý rõ. Nếu lưu per-thread state, cần cleanup và chiến lược truyền context khi async.

### 11.4. Result conversion và nullability

Around advice trả object `null` cho method trả primitive có thể dẫn đến lỗi. Đổi kiểu exception hoặc kết quả khi caller không dự kiến sẽ làm test pass ở nhánh đơn giản nhưng fail ở nhánh đa hình, generic, serialization hoặc API công khai. Với một engine có type checking tại compile-time, một số lỗi bị bắt sớm; với reflection/proxy, có thể chỉ lộ ở runtime.

### 11.5. Side effect của advice

Advice không chỉ quan sát “miễn phí”: log đồng bộ, I/O mạng, ghi audit, lock, cấp phát, đo metrics có thể làm trễ target hoặc ném lỗi. Một around advice có thể tăng latency mỗi lời gọi, tạo deadlock khi đặt lock sai, hoặc làm mất tín hiệu lỗi gốc nếu `finally` ném ngoại lệ.

### 11.6. Tần suất và hiệu năng

Một pointcut rộng ở hot path có thể kích hoạt rất nhiều around advice. Nếu bên trong có nhiều wrapper, overhead và số lần logger gọi tăng. Đánh giá theo **lần runtime thực tế**, không đếm số method đã đánh dấu. Dùng benchmark phù hợp, giới hạn cardinality và sampling, tránh log toàn bộ arguments/results nhạy cảm.

## 12. Thiết kế thứ tự advice một cách có chủ đích

Hãy xét hai khía cạnh: **thứ tự lồng** và **ý nghĩa của thành công**.

| Chuỗi ví dụ | Điều quan sát được | Nguy cơ |
| --- | --- | --- |
| `Trace(Retry(Target))` | Trace ngoài bao cả các attempt và backoff. | Một trace chỉ thấy lỗi cuối cùng, bỏ lỡ chi tiết từng attempt nếu không instrument bên trong. |
| `Retry(Trace(Target))` | Mỗi attempt có thể có trace riêng. | Có nhiều trace cho một logical operation; cần correlation. |
| `Metrics(Cache(Target))` | Đo cả cache hit/miss. | Không phân biệt độ trễ cache hit và target nếu thiếu nhãn. |
| `Cache(Metrics(Target))` | Metrics bên trong có thể chỉ chạy lúc cache miss. | Metric không đại diện tổng request. |
| `Audit(Transaction(Target))` | Audit ngoài có thể quan sát kết cục transaction boundary. | Cần xác minh audit có được ghi bền vững và thứ tự commit. |
| `Transaction(Audit(Target))` | Audit trong transaction boundary. | Audit thành công có thể xảy ra trước khi commit hoàn tất. |

Tên hàm trong bảng chỉ là **ký hiệu lồng nhau**: `Outer(Inner(Target))`. Không có bảo đảm chính sách transaction/audit nào được hiện thực chỉ nhờ thứ tự aspect; phải xem engine và hệ thống lưu trữ.

### Nguyên tắc để chọn thứ tự

1. Viết rõ **định nghĩa outcome**: target return, commit, async completion hay logical operation sau retry.
2. Xác định advice nào được gọi khi nhánh bên trong skip.
3. Xác định nơi cần quan sát attempt riêng, nơi cần quan sát tổng.
4. Xác định ai có quyền swallow/convert exception.
5. Dùng test ghi log tên advice để xác minh precedence thực, không suy đoán.

## 13. Kiểm thử around advice theo ma trận luồng thực thi

Không thể kiểm thử around advice chỉ với một ca target trả “OK”. Ít nhất cần positive/negative tests theo control flow:

| Ca | Thiết lập | Điều phải xác nhận |
| --- | --- | --- |
| **Proceed một lần** | Target trả bình thường. | Target thực thi đúng một lần; result và side effect không đổi ngoài phần công bố. |
| **Skip** | Điều kiện cho phép bỏ qua target. | Target không chạy, result/fallback đúng hợp đồng, cleanup advice ngoài vẫn chính xác. |
| **Exception từ target** | Target ném unchecked/checked exception. | Advice ngoài quan sát đúng lỗi; caller nhận exception phù hợp. |
| **Exception từ advice** | Logging/filter tự ném lỗi. | Vùng `catch/finally` nào chạy; có che lỗi target không? |
| **Thay result** | Advice chuyển đổi output. | Kiểu, nullability, identity, consistency được bảo đảm. |
| **Thay args** | Advice thay đối số khi proceed (nếu hỗ trợ). | Target nhận đúng đối số và không phá invariant. |
| **Retry** | Target lỗi lần đầu rồi thành công hoặc lỗi luôn. | Số lần target chạy, backoff, timeout, idempotency và metric đúng. |
| **Nhiều advice** | Hai hoặc ba wrapper cùng chọn join point. | Thứ tự nesting, kết cục từng tầng và số lần advice chạy đúng. |
| **Direct target call** | Caller giữ tham chiếu target thay vì proxy. | Phạm vi can thiệp đúng với cơ chế đang dùng. |
| **Self-invocation** | Target gọi method khác bằng `this`. | Không suy đoán: kiểm tra thực tế theo proxy/weaving. |
| **Async return** | Target trả stage rồi lỗi ở tương lai. | Phân biệt return bình thường và completion failure. |
| **Concurrency** | Nhiều caller đồng thời. | Context không rò, state không trộn, không race. |
| **Hot path** | Gọi nhiều lần qua pointcut rộng. | Overhead chấp nhận được, log/metric cardinality được kiểm soát. |

Đối với skip/retry, nên dùng **bộ đếm target invocation** trong test để chứng minh số lần phần đích thật sự chạy. Việc thấy log của advice “before/after” không đủ vì advice có thể trả sớm hoặc chạy tiếp nhiều lần.

## 14. So sánh around advice với các kỹ thuật thay thế

| Nhu cầu | Kỹ thuật đáng xem xét | Vai trò around advice |
| --- | --- | --- |
| Đo thời gian/log lỗi ở nhiều method độc lập. | Advice before/after; instrumentation tại biên, decorator. | Hữu ích nếu cần bao quanh và cleanup cả success/failure; không nhất thiết là lựa chọn duy nhất. |
| Caching các truy vấn thuần và có khóa rõ. | Memoization/decorator/cache client. | Có thể skip target, nhưng phải bảo đảm semantics cache. |
| Retry I/O transient. | Retry tại client/boundary với idempotency và timeout. | Có thể điều phối continuation nếu engine cho phép, cần test nghiêm ngặt. |
| Điều phối giao dịch nhiều bước. | Domain service, workflow/state machine. | Không nên che các quyết định nghiệp vụ trong pointcut/advice. |
| Kiểm tra quyền truy cập bắt buộc. | Trusted boundary + domain authorization. | Có thể hỗ trợ tại điểm được bảo đảm, không là lớp bảo vệ duy nhất khi có bypass. |
| Transform protocol tại một biên cụ thể. | Adapter/interceptor minh bạch. | Chỉ nên dùng nếu tập điểm và hợp đồng type/result rõ. |
| Quan sát hoàn tất bất đồng bộ. | Completion callback/instrumentation tại async boundary. | Around method call đơn lẻ có thể kết thúc quá sớm. |

**Nguyên tắc:** Dùng quyền điều khiển của around advice khi vấn đề thật sự cần nó và tập join point được bảo đảm. Nếu chỉ muốn code ngắn hơn cho một luồng nghiệp vụ phức tạp, around advice có thể làm kiến trúc khó hiểu thay vì đơn giản hơn.

## 15. Những ngộ nhận thường gặp

**“Around advice luôn gọi target.”** Không. Nó có thể trả sớm hoặc ném lỗi trước continuation; target có thể không chạy.

**“Around advice luôn có thể gọi `proceed` nhiều lần.”** Không thể kết luận cho mọi công cụ. Cần xác minh engine và loại join point đang dùng.

**“Một lần `proceed` đồng nghĩa target chạy đúng một lần.”** Chưa chắc khi phần bên trong có advice khác cho phép retry/skip. Phải xem toàn chuỗi.

**“Trả về bình thường từ around nghĩa là nghiệp vụ thành công.”** Không nếu kết quả do cache/fallback/filter tạo ra mà target chưa chạy; cũng không bảo đảm transaction đã commit hoặc task async hoàn tất.

**“Bắt Throwable rồi trả mặc định giúp hệ thống bền vững.”** Có thể nuốt lỗi nghiêm trọng hoặc phá hợp đồng caller. Recovery chỉ nên thực hiện ở biên có chính sách rõ.

**“Đặt code sau `proceed` bảo đảm cleanup.”** Không nếu `proceed` ném exception. Dùng `finally` và có chính sách lỗi cleanup.

**“Gắn pointcut là mọi lời gọi đều được around.”** Phụ thuộc mô hình join point, proxy/weaving, classloader, marker và đường gọi thực.

**“Có thể dùng around advice để thay mọi validation nghiệp vụ.”** Những bất biến quan trọng cần hiện diện tại nơi xác định kết quả nghiệp vụ và biên tin cậy.

**“Thứ tự A/B không quan trọng vì cả hai cùng chạy.”** Sai: advice ngoài đo phạm vi khác advice trong và có thể thấy kết quả/lỗi đã được tầng khác chuyển đổi.

## 16. Tự đánh giá

### Câu 1

Around advice gọi `proceed()` đúng một lần, target trả `42`, advice trả `0`. Caller nhận gì? Có phải “advice chỉ quan sát” không?

**Đáp án:** Caller nhận `0`, nếu kiểu/hợp đồng cho phép. Advice **đã thay đổi kết quả**, không còn chỉ quan sát.

### Câu 2

Một around advice trả cached value mà không gọi continuation. Advice outside báo “returning”. Target đã chạy chưa?

**Đáp án:** Chưa chắc; nếu nhánh cache hit không gọi tiếp thì target không chạy. “Returning” của tầng ngoài nói **continuation bên trong trả bình thường**, không chứng minh target đã thực hiện.

### Câu 3

Trong `Trace(Retry(Target))`, nếu retry thất bại hai lần rồi thành công lần ba, Trace ngoài thường quan sát bao nhiêu logical call?

**Đáp án:** Một logical invocation có thể chứa ba attempt; số lần target chạy là ba nếu retry thật sự gọi tiếp ba lần. Muốn metrics từng attempt cần điểm đo phù hợp, không chỉ trace ngoài.

### Câu 4

Tại sao không nên retry một thao tác chuyển tiền chỉ dựa trên ngoại lệ timeout?

**Đáp án:** Timeout không chứng minh thao tác chưa commit. Gọi lại có thể nhân side effect; phải có idempotency, chính sách retry, thời hạn tổng và khả năng truy vấn trạng thái.

### Câu 5

Một around advice ghi latency trong code sau `return proceed()` mà không có `finally`. Nếu target ném lỗi thì sao?

**Đáp án:** Lệnh sau `return` không chạy; cũng không chạy trên exception. Phải đo trong `finally` hoặc thiết kế đường lỗi riêng.

### Câu 6

Target trả `CompletableFuture` sau 1 ms và future thất bại sau 2 giây. Around advice đo thời gian `proceed` thấy gì?

**Đáp án:** Thường đo khoảng thời gian lời gọi trả future, không phải đến khi future thất bại. Muốn đo end-to-end phải quan sát completion.

### Câu 7

Bạn dùng interface dynamic proxy; một code path giữ target gốc và gọi thẳng. Around advice có chạy không?

**Đáp án:** Handler proxy không chạy ở đường bypass đó. Cần thống nhất cách caller nhận proxy hoặc dùng cơ chế khác có tập điểm phù hợp.

### Câu 8

Nếu advice B bên trong bắt exception rồi trả fallback, advice A bên ngoài sẽ thấy after-throwing hay after-returning?

**Đáp án:** Nếu B trả bình thường và không ném lỗi, A có thể quan sát completion bình thường của continuation; A không nhất thiết thấy exception target đã bị B xử lý.

### Câu 9

Vì sao advice đo thời gian nên giữ biến thời điểm bắt đầu ở local scope của invocation?

**Đáp án:** Tránh nhiều lời gọi đồng thời ghi đè trạng thái chung của aspect và làm sai latency; local variable cũng giúp cleanup rõ từng invocation.

## 17. Checklist trước khi đưa around advice vào production

1. **Tập điểm:** Pointcut chọn loại join point nào và có đủ đường gọi cần thiết không?
2. **Call path:** Proxy có bị bypass, self-invocation có nằm ngoài phạm vi, artifact weaving có đúng không?
3. **Continuation:** Có quyền gọi 0/nhiều lần không? Nếu có, áp điều kiện nào?
4. **Hợp đồng:** Điều kiện skip/replace có được caller hiểu và chấp nhận không?
5. **Result/args:** Type, nullability, side effect và security invariant có được giữ đúng không?
6. **Exception:** Đường target error và advice error được xử lý, truyền cause và cleanup thế nào?
7. **Ordering:** Advice ngoài/trong đặt theo đúng phạm vi metric, retry, cache, transaction chưa?
8. **Async:** Lời gọi trả stage hay công việc đã hoàn tất? Context có được truyền/đóng đúng không?
9. **Concurrency:** State trong advice có thread-safe, không rò ThreadLocal/span/resource không?
10. **Hiệu năng:** Số runtime occurrences, logging volume, allocation và latency đã được đo ở tải thực tế chưa?
11. **Kiểm thử:** Có ca success, skip, retry, failure, direct target, self-call, nhiều advice và async chưa?
12. **Giải thích được:** Người bảo trì có dễ xác định tại sao target chạy hoặc không chạy cho một request cụ thể không?

## Kết luận

**Around advice** không chỉ thêm hành vi quanh join point mà có thể **điều khiển chính luồng thực thi**: quyết định gọi tiếp hay không, bao quanh lỗi và kết quả, thậm chí gọi lại hoặc biến đổi dữ liệu nếu cơ chế cho phép. Sức mạnh đó tạo ra rủi ro với idempotency, tính trong suốt của hợp đồng, thứ tự advice, đồng bộ/bất đồng bộ và phạm vi weaving. Muốn dùng an toàn, hãy viết rõ **continuation nào được gọi, bao nhiêu lần, giá trị/lỗi nào đến caller và đường nào có thể bypass**; sau đó chứng minh bằng positive/negative integration tests chứ không chỉ nhìn tên pointcut hoặc annotation.

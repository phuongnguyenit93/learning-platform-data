# Kiểm thử thứ tự nhiều aspect và lời gọi lồng nhau

## 1. Vì sao kiểm thử thứ tự là cần thiết?

Trong **Aspect-Oriented Programming (AOP)**, một thao tác nghiệp vụ có thể đồng thời thuộc pointcut của nhiều aspect: phân quyền, transaction, ghi audit, đo hiệu năng, retry hoặc quản lý ngữ cảnh. Mỗi advice có thể chạy trước, sau hay bao quanh lời gọi. Khi một phương thức còn gọi tiếp một phương thức khác cũng được instrument, quá trình thực thi tạo thành **nhiều lớp aspect lồng nhau**.

Thứ tự không chỉ làm thay đổi log. Nó quyết định liệu kiểm tra quyền có xảy ra trước side effect, retry có tạo một transaction mới trên mỗi attempt hay không, metric có đo cả overhead của các advice khác, và liệu cleanup vẫn thực thi đúng khi có ngoại lệ. Một chương trình có thể trả kết quả nghiệp vụ đúng nhưng thứ tự aspect sai, gây lỗi khó phát hiện.

Bài này cung cấp phương pháp **kiểm thử cụ thể** thay vì chỉ giải thích lý thuyết:

- Phân biệt thứ tự **entry**, **body** và **exit**, đặc biệt với `around`.
- Xác định quan hệ ưu tiên của các aspect bằng một khai báo rõ ràng.
- Xây dựng event trace để chứng minh cấu trúc `outer() -> inner()`.
- Test cả nhánh trả về bình thường và nhánh ném ngoại lệ.
- Phân biệt **join point khác nhau**, **aspect khác nhau** và **lời gọi trùng do cấu hình sai**.
- Kiểm tra khác biệt giữa weaving tại execution join point và interception chỉ qua proxy.
- Mở rộng sang recursion, retry, short-circuit, các tác vụ bất đồng bộ và concurrent.
- Viết kiểm thử Java 17 bằng **AspectJ code-style**, biên dịch/weave/chạy được với output đã xác minh.

Nội dung tập trung vào kiến thức AOP nói chung. AspectJ được dùng làm công cụ minh họa có weaving thực, không ngầm áp đặt các quy tắc của nó cho mọi công cụ AOP khác.

## 2. Từ pointcut đến chuỗi thực thi

Những thành phần cần biết:

| Thành phần | Vai trò khi kiểm thử |
|---|---|
| **Join point** | Điểm thực thi có thể bị chặn; ví dụ việc thực thi `Business.outer(String)` |
| **Pointcut** | Quy tắc chọn một hay nhiều join point |
| **Advice** | Hành vi bổ sung chạy tại join point đã chọn |
| **Aspect** | Đơn vị chứa pointcut, advice và state liên quan |
| **Precedence** | Quan hệ ưu tiên khi nhiều aspect cùng áp dụng |
| **Proceed** | Hành động gọi tiếp đoạn thực thi mà `around` bao quanh |
| **Weaving** | Tích hợp advice vào bytecode để nó thật sự thực thi |
| **Nested invocation** | Một method tạo join point mới trong body của method đang được chặn |

Cần kiểm tra **hai điều khác nhau**: (1) pointcut chọn đúng method; (2) lời gọi thật thực sự đi qua advice đúng thứ tự. Một kiểm thử chỉ dùng reflection để khẳng định pointcut match không thay thế integration test trên bytecode đã weave.

## 3. Mô hình bao lồng của hai around advice

Giả sử aspect A có precedence cao hơn B, cả hai cùng match execution của method `work()` và đều có cấu trúc:

```text
around:
    record enter
    try:
        return proceed()
    finally:
        record exit
```

Khi đó chuỗi kỳ vọng:

```text
A.enter
B.enter
work.body
B.exit
A.exit
```

Lý do: A nằm **ngoài** B. A vào trước, gọi `proceed` để đi vào B; B gọi `proceed` để đến body. Khi body kết thúc, stack tháo từ trong ra ngoài: B thoát trước A.

Sơ đồ:

```text
caller
  └─ A around
       └─ B around
            └─ target method
```

Vì vậy, diễn đạt “aspect ưu tiên cao chạy trước” chỉ chính xác cho phần **đi vào**; không có nghĩa toàn bộ phần sau `proceed()` của nó phải chạy trước phần sau `proceed()` của aspect ít ưu tiên hơn.

Với exception, `finally` vẫn chạy:

```text
A.enter
B.enter
work.body throws
B.exit
A.exit
caller catches error
```

Nếu advice ghi audit hoặc trả lại lock/scope trong `finally`, test thứ tự **exit** quan trọng không kém thứ tự **entry**.

## 4. Lồng nhiều join point: outer gọi inner

Giả sử `outer()` gọi `inner()`; **cả hai đều thuộc pointcut của A và B**. Chuỗi phải tạo thêm một cặp advice lồng bên trong body của outer:

```text
A.enter outer
B.enter outer
  body outer starts
    A.enter inner
    B.enter inner
      body inner
    B.exit inner
    A.exit inner
  body outer ends
B.exit outer
A.exit outer
```

Đây là **hai execution join point khác nhau**, nên có hai lượt kích hoạt advice. Đừng kết luận advice bị chạy “hai lần sai” chỉ vì log chứa hai event cùng tên aspect.

Ngược lại, nếu chỉ có event cho outer dù pointcut dự kiến chọn cả inner, cần điều tra:

- Pointcut có thực sự match `inner` không?
- Bytecode chứa **execution của inner** có được weave không?
- Ứng dụng đang dùng proxy interception thay vì weaving execution?
- Lời gọi nội bộ đi thẳng vào object gốc, bỏ qua proxy?
- Method có modifier/overload/annotation khác với điều kiện chọn?
- Dữ liệu quan sát có bị filter/drop ở collector không?

Điểm mấu chốt: **thứ tự tại một join point** khác với **cấu trúc của những join point lồng nhau**. Bộ kiểm thử phải xác minh cả hai.

## 5. Khai báo thứ tự rõ ràng

Trong ví dụ AspectJ code-style, khai báo:

```java
public aspect OrderPolicy {
    declare precedence: GuardAspect, TraceAspect;
}
```

Điều này đặt `GuardAspect` ưu tiên cao hơn `TraceAspect`. Khi cùng match một method execution, `GuardAspect` là lớp bao phía ngoài `TraceAspect`. Các aspect vẫn cần được weave vào target phù hợp.

Không nên dựa vào:

- Tên file đứng trước theo alphabet.
- Thứ tự file trong lệnh compiler.
- Thứ tự import, thứ tự source code hoặc thứ tự load class.
- Một kết quả vô tình ổn định của phiên bản runtime mà không có hợp đồng thứ tự.
- Thứ tự callback từ logging backend có queue bất đồng bộ.

Nếu công cụ hỗ trợ quan hệ precedence riêng hoặc có precedence theo kế thừa, phải đọc và kiểm chứng semantics của chính cơ chế đó. Không phải mọi công cụ AOP có cú pháp `declare precedence` giống AspectJ.

Trước khi chọn thứ tự, hãy lập ma trận concern. Ví dụ một retry ở ngoài transaction thường có thể tạo transaction riêng cho mỗi attempt; transaction ở ngoài retry có thể giữ attempt sau trong cùng ranh giới đã hỏng. Phân quyền, timeout, audit và metric cần quyết định trước/sau theo yêu cầu nghiệp vụ, không theo sở thích đặt tên class.

## 6. Thiết kế kiểm thử bằng event trace

Một kiểm thử đáng tin tạo **chuỗi sự kiện dự kiến** rồi assert **bằng nhau toàn bộ**, không chỉ kiểm tra một vài substring.

Schema dùng trong test có thể gồm:

- Mã aspect hoặc loại advice: `guard`, `trace`.
- Giai đoạn: enter, exit, error.
- Tên semantic operation hoặc signature: outer/inner.
- Invocation ID và parent ID nếu nhiều lời gọi cùng tên.
- Thread/task correlation khi test concurrent/async.

Ở demo đơn luồng, string event ngắn là đủ: `guard+outer`, `trace+inner`, `trace-inner`. Ở hệ thống thật, không lấy raw argument để tạo log thử nghiệm, nhất là token/dữ liệu nhạy cảm.

Những assertion quan trọng:

1. **Coverage**: có event cho cả outer và inner.
2. **Precedence**: `guard+` xảy ra trước `trace+` của **cùng** join point.
3. **LIFO**: `trace-` xảy ra trước `guard-` của **cùng** join point.
4. **Nested order**: mọi event inner nằm bên trong khoảng thời gian outer đang thực thi.
5. **Target count**: body của từng method chạy đúng số lần cần thiết.
6. **Outcome**: giá trị trả về và ngoại lệ không bị advice thay đổi ngoài hợp đồng.
7. **Negative coverage**: method không thuộc pointcut không phát các event đó.
8. **Cleanup**: dù exception, mọi scope đã mở vẫn được đóng theo thứ tự.

Test `equals(expected)` giúp phát hiện cả **thiếu**, **thừa**, **sai tên**, **đảo thứ tự** và **log đôi**.

## 7. Ví dụ Java 17 + AspectJ chạy được

Bộ ví dụ gồm bốn file. Kết quả đã được xác minh bằng **AspectJ 1.9.24**, compiler `ajc` với mức ngôn ngữ Java 17.

- `Demo.java`: hai method lồng nhau, recorder và hai assertion thành công/lỗi.
- `GuardAspect.aj`: around advice bao cả outer và inner.
- `TraceAspect.aj`: around advice có cùng pointcut để kiểm thử thứ tự.
- `OrderPolicy.aj`: khai báo precedence.

Tên `Guard` chỉ biểu diễn thứ tự trong bài học, không thay thế một bộ kiểm tra quyền thật. Trong hệ thống production, logic guard phải tính allow/deny theo policy và bảo vệ side effect một cách độc lập.

### 7.1. Demo.java

```java
import java.util.ArrayList;
import java.util.List;

public class Demo {
    static final List<String> EVENTS = new ArrayList<>();

    static final class Business {
        String outer(String id) {
            EVENTS.add("body outer:start");
            String nested = inner(id);
            EVENTS.add("body outer:end");
            return "outer:" + nested;
        }

        String inner(String id) {
            EVENTS.add("body inner");
            if (id.equals("boom")) throw new IllegalStateException("planned");
            return "inner:" + id;
        }
    }

    static void verify(String scenario, List<String> expected) {
        if (!EVENTS.equals(expected)) {
            throw new AssertionError(scenario + " expected=" + expected + " actual=" + EVENTS);
        }
        System.out.println(scenario + "=PASS");
        EVENTS.forEach(System.out::println);
        EVENTS.clear();
    }

    public static void main(String[] args) {
        Business service = new Business();
        String value = service.outer("A");
        EVENTS.add("caller:" + value);
        verify("success", List.of(
                "guard+outer", "trace+outer",
                "body outer:start",
                "guard+inner", "trace+inner",
                "body inner",
                "trace-inner", "guard-inner",
                "body outer:end",
                "trace-outer", "guard-outer",
                "caller:outer:inner:A"));

        try {
            service.outer("boom");
            throw new AssertionError("The method should fail");
        } catch (IllegalStateException expected) {
            EVENTS.add("caller:caught");
        }
        verify("failure", List.of(
                "guard+outer", "trace+outer",
                "body outer:start",
                "guard+inner", "trace+inner",
                "body inner",
                "trace-inner", "guard-inner",
                "trace-outer", "guard-outer",
                "caller:caught"));
    }
}
```

Giải thích:

- `Demo.EVENTS` là `ArrayList` chỉ phù hợp cho bài test **đơn luồng tuần tự**. Nếu ứng dụng chạy song song, cần collector thread-safe và correlation per invocation.
- `Business.outer` ghi `body outer:start`, gọi `inner`, rồi ghi `body outer:end` khi inner trả bình thường.
- `inner("boom")` ném `IllegalStateException("planned")` sau event `body inner`.
- `verify` so sánh **toàn bộ chuỗi event** với `List.of(...)`. Nếu sai, nó ném `AssertionError`; chỉ khi đúng mới in `PASS` và từng event.
- Test chạy success trước, rồi exception. Không có `sleep` hoặc phụ thuộc đồng hồ để quyết định thứ tự.

### 7.2. GuardAspect.aj

```java
public aspect GuardAspect {
    pointcut operation():
        execution(String Demo.Business.outer(String))
        || execution(String Demo.Business.inner(String));

    String around(): operation() {
        String name = thisJoinPointStaticPart.getSignature().getName();
        Demo.EVENTS.add("guard+" + name);
        try {
            return proceed();
        } finally {
            Demo.EVENTS.add("guard-" + name);
        }
    }
}
```

Pointcut chọn execution của chính hai phương thức có signature `String outer(String)` và `String inner(String)`. `thisJoinPointStaticPart` cung cấp chữ ký join point, từ đó lấy tên method để gắn nhãn event.

Advice có return type `String` phù hợp target, gọi `proceed()` đúng một lần, và ghi event thoát trong `finally`. Vì vậy event `guard-` xuất hiện cả khi body trả về lẫn khi ném lỗi.

### 7.3. TraceAspect.aj

```java
public aspect TraceAspect {
    pointcut operation():
        execution(String Demo.Business.outer(String))
        || execution(String Demo.Business.inner(String));

    String around(): operation() {
        String name = thisJoinPointStaticPart.getSignature().getName();
        Demo.EVENTS.add("trace+" + name);
        try {
            return proceed();
        } finally {
            Demo.EVENTS.add("trace-" + name);
        }
    }
}
```

Cùng pointcut, chỉ khác nhãn sự kiện. Đây là cách cô lập nguyên nhân khi test: mọi khác biệt về order đến từ **precedence/weaving/nesting**, không do hai aspect có logic nghiệp vụ khác nhau.

### 7.4. OrderPolicy.aj

```java
public aspect OrderPolicy {
    declare precedence: GuardAspect, TraceAspect;
}
```

File này làm **quan hệ ưu tiên thành một hợp đồng tường minh**. Nếu bỏ nó, test không còn được bảo đảm bởi khai báo precedence mà bài học muốn chứng minh.

## 8. Biên dịch, weaving và stdout đã kiểm chứng

Có thể lấy bộ AspectJ compiler và runtime qua Maven:

```bash
mvn -B dependency:get -Dartifact=org.aspectj:aspectjtools:1.9.24 -Dtransitive=false
mvn -B dependency:get -Dartifact=org.aspectj:aspectjrt:1.9.24 -Dtransitive=false
```

Lưu bốn file trong cùng một thư mục. Trên **Windows PowerShell**:

```powershell
$repo = Join-Path $HOME ".m2/repository/org/aspectj"
$tools = Join-Path $repo "aspectjtools/1.9.24/aspectjtools-1.9.24.jar"
$rt = Join-Path $repo "aspectjrt/1.9.24/aspectjrt-1.9.24.jar"

New-Item -ItemType Directory -Force out | Out-Null
java -cp $tools org.aspectj.tools.ajc.Main -17 -classpath $rt -d out Demo.java GuardAspect.aj TraceAspect.aj OrderPolicy.aj
if ($LASTEXITCODE -ne 0) { throw "AspectJ compilation failed" }

java -cp "out;$rt" Demo
if ($LASTEXITCODE -ne 0) { throw "Test failed" }
```

Các câu lệnh dùng `-17` để chọn mức Java 17 và `-d out` để tạo bytecode đã weave. Trên Linux/macOS, dấu phân tách classpath khi chạy ứng dụng là `:`:

```bash
REPO="$HOME/.m2/repository/org/aspectj"
TOOLS="$REPO/aspectjtools/1.9.24/aspectjtools-1.9.24.jar"
RT="$REPO/aspectjrt/1.9.24/aspectjrt-1.9.24.jar"

mkdir -p out
java -cp "$TOOLS" org.aspectj.tools.ajc.Main -17 -classpath "$RT" -d out \
    Demo.java GuardAspect.aj TraceAspect.aj OrderPolicy.aj
java -cp "out:$RT" Demo
```

**Stdout chính xác đã chạy trên JVM sau weaving:**

```text
success=PASS
guard+outer
trace+outer
body outer:start
guard+inner
trace+inner
body inner
trace-inner
guard-inner
body outer:end
trace-outer
guard-outer
caller:outer:inner:A
failure=PASS
guard+outer
trace+outer
body outer:start
guard+inner
trace+inner
body inner
trace-inner
guard-inner
trace-outer
guard-outer
caller:caught
```

Nếu test không được weave, không match pointcut hoặc precedence sai, `verify` sẽ báo lỗi; câu `success=PASS` hoặc `failure=PASS` sẽ không được in thành công tương ứng.

## 9. Phân tích nhánh success: cấu trúc stack

`outer("A")` tạo trình tự:

1. Guard ở outer ghi `guard+outer`.
2. Guard gọi `proceed`, Trace ở outer ghi `trace+outer`.
3. Trace gọi `proceed`, body outer ghi `body outer:start`.
4. Outer gọi inner trên cùng object. Vì đây là **execution pointcut đã được weave**, inner lại tạo Guard → Trace.
5. Body inner chạy và trả `inner:A`; Trace inner ghi `trace-inner`, Guard inner ghi `guard-inner`.
6. Body outer tiếp tục, ghi `body outer:end`, trả `outer:inner:A`.
7. Trace outer rời scope trước, Guard outer rời sau.
8. Caller nhận return value và ghi `caller:outer:inner:A`.

Chuỗi push/pop:

```text
push Guard(outer)
    push Trace(outer)
        outer body begins
            push Guard(inner)
                push Trace(inner)
                    inner body
                pop Trace(inner)
            pop Guard(inner)
        outer body completes
    pop Trace(outer)
pop Guard(outer)
caller receives value
```

Mỗi `pop` phải tương ứng một `push` **cùng invocation**. Với recursion, một method name có thể xuất hiện ở nhiều stack depth; nên gắn parent/child invocation ID khi cần kiểm tra chính xác.

## 10. Phân tích nhánh failure: cleanup và propagate

Với `outer("boom")`, body inner ghi event rồi ném `IllegalStateException`. Dòng `body outer:end` **không** được thực thi. Tuy vậy `finally` của Trace inner, Guard inner, Trace outer và Guard outer vẫn chạy theo LIFO; caller bắt được exception gốc và ghi `caller:caught`.

Điều này chứng minh ba khía cạnh khác nhau:

- **Advice execution:** đúng các scope đã đi vào đều được rời.
- **Business execution:** body outer không tiếp tục sau inner thất bại.
- **Error semantics:** exception lan đến caller, không bị advice nuốt hoặc đổi thành kết quả thành công giả.

Đừng chỉ assert `assertThrows` mà bỏ qua những event cleanup. Nếu advice quản lý resource, lock, trace span hoặc transaction scope, sai thứ tự cleanup có thể gây rò tài nguyên hoặc context của request trước.

Bản thân cleanup cũng có thể ném exception. Nếu một lời gọi logger trong `finally` ném lỗi, nó có nguy cơ che mất lỗi nghiệp vụ. Cơ chế telemetry cần có chính sách cô lập lỗi, nhưng không được che đậy lỗi bắt buộc của giao dịch nếu hợp đồng yêu cầu xử lý nghiêm ngặt.

## 11. Before, after returning, after throwing và around

Không nên coi các loại advice là những callback giống nhau chỉ khác tên.

| Kiểu advice | Thời điểm | Test phù hợp |
|---|---|---|
| `before` | Trước khi join point tiếp tục | Có chạy đúng vị trí, không thực thi side effect khi policy deny? |
| `after returning` | Chỉ sau kết thúc bình thường | Không chạy khi target ném exception |
| `after throwing` | Khi ném exception phù hợp | Bắt đúng loại lỗi và giữ error contract |
| `after` | Sau join point theo semantics của nó | Cleanup cả success và failure |
| `around` | Bao lời gọi, có `proceed()` | Nesting entry/exit, short-circuit, retry, return value |

Ở các aspect khác nhau, precedence giúp quy định mô hình bao lồng. Với **nhiều advice bên trong cùng một aspect**, quy tắc ordering cụ thể còn phụ thuộc loại advice và cú pháp/công cụ; không suy ra máy móc từ thứ tự dòng source. Khi thứ tự có ý nghĩa, test phải dùng **đúng tổ hợp advice thực tế**.

Ví dụ chính dùng hai around advice vì rõ mô hình stack, không phải vì mọi concern nhất thiết cần around. Với logging đơn giản, before/after có thể đủ; với thay đổi luồng điều khiển như block/retry/cache hit, around có hợp đồng rộng hơn và rủi ro cao hơn.

## 12. Execution weaving, call weaving và self-invocation

Đây là khác biệt quan trọng nhất khi kiểm thử nested calls.

`outer` gọi `inner` trong cùng instance. **AspectJ execution weaving** sửa bytecode tại execution của inner, vì vậy inner vẫn được instrument mà không cần đi qua một proxy bên ngoài.

Các trường hợp khác:

- **Call join point:** được quan sát tại chỗ gọi method; phải weave caller phù hợp. Nếu caller chuyển module/classloader, pointcut `call` có thể bỏ sót.
- **Execution join point:** được quan sát khi thân method được thực thi, miễn target class đã được weave.
- **Proxy interception:** nhiều cơ chế chỉ chặn những lời gọi đi qua proxy. `this.inner()` gọi trực tiếp từ một method của target có thể bỏ qua proxy.
- **Không được weave:** annotation/metadata có tồn tại cũng không biến thành interception tự động.

Do đó, một test chỉ gọi `methodPointcut.matches(inner)` không đủ. Cần chạy thật `outer()` qua đường vào giống ứng dụng và xác nhận event inner.

Nếu dùng cả `call` và `execution` trên cùng logical operation, có thể thấy hai vòng advice do **hai join point khác loại**. Phân biệt chúng trong test bằng kind hoặc signature, đừng quy tất cả thành “aspect chạy trùng”.

## 13. Negative test, refactoring và coverage

Ngoài test hai method được chọn, cần test method **không được chọn**. Ví dụ thêm `Business.health()` không thuộc pointcut và kiểm tra rằng lời gọi đó không sinh `guard+health` hoặc `trace+health`. Đó là một bước mở rộng test, không phải phần đã thêm trong chương trình mẫu.

Các trường hợp cần xem xét:

1. Đổi tên `inner` nhưng quên sửa pointcut.
2. Chuyển `Business` sang package khác; selector gắn tên type cũ không match.
3. Thêm overload cùng tên với ý nghĩa khác; wildcard `inner(..)` chặn thừa.
4. Đổi implementation hoặc thay đường gọi; advice không còn được weave.
5. Dùng interface/annotation metadata nhưng weaver đọc method implementation.
6. Biên dịch đồng thời hai phiên bản aspect làm cùng một concern, gây event trùng.
7. Một aspect tự gọi helper cũng thuộc pointcut rộng, tạo recursion ngoài ý muốn.

Kiểm thử coverage gồm **positive**, **negative** và **integration test trên đường gọi thật**. Khi thay đổi pointcut hoặc refactor cấu trúc code, bộ test phải phát hiện cả **false negative** lẫn **false positive**.

## 14. Short-circuit: around không gọi proceed

Một around advice có thể trả kết quả trực tiếp hoặc ném lỗi mà không gọi `proceed()`:

```text
OuterAdvice enters
   -> InnerAdvice enters
      -> policy denies OR cache hit
      -> returns/throws without proceed
   <- InnerAdvice exits
<- OuterAdvice exits
```

Khi một advice short-circuit, **những advice và body ở bên trong nó không được chạy**. Vì vậy kiểm thử order phải kiểm tra cả **số lần body được gọi** và side effects, không chỉ kiểm tra entry/exit.

Ví dụ khi deny, yêu cầu cơ bản là target không thực thi; nếu cache hit, phải chứng minh dữ liệu trả lại thuộc đúng actor/tenant và hợp đồng cache. Một result từ cache mà đúng order nhưng sai quyền vẫn là lỗi nghiêm trọng.

Nếu advice chỉ log rồi vẫn gọi `proceed()` trên nhánh deny, test đếm số body invocation sẽ phát hiện vấn đề mà test dựa trên log có thể bỏ sót.

## 15. Retry và nhiều lượt thực thi

Một logical operation có thể tạo nhiều attempts nếu một aspect retry có quyền gọi tiếp nhiều lần:

```text
Retry -> Trace -> Transaction -> Business
  attempt 1
  attempt 2
```

So với:

```text
Trace -> Retry -> Transaction -> Business
  Trace đo cả logical operation và các attempts bên trong
```

Số event của Trace và Transaction thay đổi theo vị trí của chúng trong stack. Thử lại có thể làm `inner` chạy nhiều lần, nên việc thấy lặp nhiều event không luôn là cấu hình trùng.

Nhưng **retry không bảo đảm thao tác an toàn khi lặp**. Với lệnh ghi có side effect, cần idempotency key và cơ chế chống duplicate/đối soát. Một bài test đủ tốt kiểm tra cả logical operation ID, attempt number, số lượt body, trạng thái cuối và số hiệu ứng thực.

Tránh nested retries ở nhiều tầng vô tình nhân số attempts. Với lỗi sau commit hoặc timeout mơ hồ, không giả định rằng attempt trước chưa làm gì.

## 16. Lời gọi đệ quy: cùng method nhưng nhiều depth

Nếu `inner` gọi lại chính nó, mỗi execution phù hợp có thể tạo thêm cặp advice:

```text
A.enter depth1
  B.enter depth1
    A.enter depth2
      B.enter depth2
        body depth2
      B.exit depth2
    A.exit depth2
  B.exit depth1
A.exit depth1
```

Chỉ ghi tên method không đủ phân biệt các cấp. Khi kiểm thử recursion hoặc cây lời gọi lớn, bổ sung:

- `invocationId`, `parentInvocationId`.
- `depth` được quản lý bằng push/pop và `try/finally`.
- Giới hạn recursion và base case rõ.
- Bộ lọc để aspect không tự instrument các helper ghi log của chính nó.

Aspect singleton có field mutable dùng chung không tự tạo isolation theo request. `ThreadLocal` có thể chứa state trong luồng đồng bộ nhưng cần restore khi rời scope; nó không tự lan qua executor và không thay thế parent/child IDs trong thực thi bất đồng bộ.

## 17. Async và concurrency: không thể dùng một global order

Một method trả `CompletableFuture` có thể kết thúc **execution của method** khi trả handle, trong khi tác vụ nghiệp vụ chạy sau đó trên thread khác. Một around advice bao method có thể in `exit` trước lúc future hoàn thành. Vì vậy phải phân biệt:

- `method_returned_handle`.
- `async_job_started`.
- `async_job_completed` hoặc `async_job_failed`.
- Join point tại callback/worker nếu được instrument riêng.

Kiểm thử nên điều khiển completion bằng future/scheduler giả, không dùng `Thread.sleep` để hy vọng một thứ tự xảy ra. Context tracing/security cần được truyền và restore khi chuyển luồng, nếu có.

Với nhiều request concurrent, log toàn cục có thể xen kẽ:

```text
guard+outer requestA
guard+outer requestB
trace+outer requestA
trace+outer requestB
...
```

Không assert một chuỗi global duy nhất nếu ứng dụng không bảo đảm thứ tự giữa các request. Thay vào đó:

1. Dùng event collector thread-safe hoặc buffer theo request.
2. Gắn request ID/invocation ID cho mỗi event.
3. Assert quan hệ **happens-before** hoặc stack nesting **trong cùng logical invocation**.
4. Sử dụng latch/barrier để chủ động dựng interleaving cạnh tranh.
5. Không suy ra thứ tự advice chỉ từ timestamp hoặc thứ tự flush trong logging queue.

Ví dụ `ArrayList` của bài này **chỉ là test đơn luồng**; không sử dụng nó như một audit logger concurrent trong production.

## 18. Lỗi phổ biến và hướng kiểm tra

| Hiện tượng | Nguyên nhân có thể | Cách phát hiện hoặc sửa |
|---|---|---|
| Thiếu event inner | Pointcut không match, target chưa weave, self-invocation qua raw object | Integration test outer→inner |
| Event exit ngược thứ tự mong đợi | Hiểu sai nesting/LIFO | Vẽ stack và test `finally` |
| Cùng tên aspect xuất hiện hai lần | Hai join point lồng nhau, retry hoặc duplicate thật | Gắn joinPointId/attemptId để phân biệt |
| `after returning` không chạy khi lỗi | Đó là semantics của after-returning | Test after-throwing/cleanup phù hợp |
| Lỗi gốc bị thay bằng lỗi logger | Cleanup ném exception | Cách ly lỗi telemetry theo hợp đồng |
| Aspect priority thay đổi bất ngờ | Không khai báo precedence rõ | Khai báo và test order |
| Around không gọi target | Short-circuit hoặc quên `proceed` | Assert invocation count/side effect |
| Retry tạo hiệu ứng lặp | Không có idempotency | Kiểm tra state và effect chứ không chỉ event |
| Test flaky khi song song | So sánh log global không correlation | Per-invocation assertions |
| Lồng quá sâu bị tràn stack | Đệ quy + advice quá rộng | Base case, depth limit và pointcut scope |
| Future báo success sớm | Chỉ quan sát lúc trả handle | Hook completion và test scheduler |
| Test pass nhưng production khác | Khác classloader, weaving/agent hoặc pointcut | Test trên build/deploy thực tế |

## 19. Quy trình kiểm thử trong một dự án AOP

**Bước 1.** Liệt kê các aspect cùng bao một business operation và những method được gọi lồng nhau. Vẽ ma trận operation × aspect.

**Bước 2.** Xác định hợp đồng precedence. Tại mỗi join point, aspect nào ở ngoài, aspect nào ở trong? Có trường hợp thứ tự không quan trọng hay không?

**Bước 3.** Dùng recorder thử nghiệm phát event khi vào, trước/ sau `proceed`, khi lỗi và khi dọn resource. Gắn invocation ID khi cần.

**Bước 4.** Viết test một method đơn, assert toàn bộ chuỗi sự kiện và return value. Thêm test method không thuộc pointcut.

**Bước 5.** Thêm nested outer→inner, test thành công và exception; đếm body invocations.

**Bước 6.** Thêm các trường hợp đặc biệt: short-circuit, retry, recursion, overloaded method, execution-vs-call.

**Bước 7.** Với async/concurrency, đo lifecycle theo correlation và thứ tự nhân quả, không cố ép global ordering.

**Bước 8.** Chạy integration test bằng cùng cơ chế interception/weaving mà sản phẩm dùng, và lưu các assertion vào CI.

### Checklist

- [ ] Pointcut match đúng cả outer và inner.
- [ ] Precedence giữa các aspect có ảnh hưởng thực tế được khai báo rõ.
- [ ] Entry và exit tuân thủ stack nesting.
- [ ] Error path vẫn thực hiện cleanup và giữ exception.
- [ ] Có assertion exact cho sự kiện, body count và kết quả.
- [ ] Có negative test cho method ngoài scope.
- [ ] Self-invocation và loại join point được hiểu theo cơ chế thật.
- [ ] Retry/short-circuit không tạo side effect sai.
- [ ] Async không bị nhầm handle return với job completion.
- [ ] Concurrent test có correlation và event collector an toàn.
- [ ] Toolchain build thực sự weave class cần thiết.

## 20. Kết luận

**Kiểm thử thứ tự nhiều aspect là kiểm thử cấu trúc bao lồng và luồng điều khiển, không phải chỉ nhìn số dòng log.** Khi A ưu tiên cao hơn B, A thường bao ngoài B: vào trước và ra sau. Khi outer gọi inner và cả hai là execution join point được weave, mỗi lời gọi tạo một stack advice riêng nằm trong stack của lời gọi cha. Thực hành hiệu quả là khai báo precedence rõ, **assert toàn bộ event trace ở cả success và failure**, kiểm tra số lần body/side effect, rồi mở rộng sang recursion, retry, concurrency và asynchronous completion.

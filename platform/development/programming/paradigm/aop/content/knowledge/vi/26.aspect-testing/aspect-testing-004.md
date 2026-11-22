# Kiểm thử kiểu trả về, ngoại lệ và giá trị null trong Aspect (AOP)

## 1. Kiểm thử aspect là kiểm thử sự bảo toàn hợp đồng

Trong Aspect-Oriented Programming (AOP), pointcut chọn các join point; advice chạy trước, sau hoặc bao quanh một join point. Một aspect có thể đo thời gian, ghi log, kiểm tra quyền, cache hoặc thử lại thao tác. Chính vì advice nằm ngoài mã nghiệp vụ, việc đọc thân phương thức không đủ để xác nhận người gọi thực sự nhận đúng kết quả.

Một around advice chỉ có nhiệm vụ quan sát nhưng viết sai có thể gây những lỗi sau:

- Trả null thay vì object mà phương thức gốc trả về.
- Trả object sai kiểu, gây ClassCastException ở phía caller.
- Trả null cho phương thức có kiểu trả về nguyên thủy, dẫn đến lỗi unboxing.
- Nhầm phương thức void với phương thức có kiểu tham chiếu trả null.
- Nuốt checked exception hoặc unchecked exception, biến lỗi thành “thành công”.
- Bọc ngoại lệ gốc sai hợp đồng hoặc che ngoại lệ gốc bởi lỗi trong đoạn ghi metric.
- Gọi proceed() nhiều lần, nhân đôi cập nhật dữ liệu hoặc tác dụng phụ.
- Chỉ quan sát việc trả về một Future/CompletionStage rồi báo đã thành công dù tác vụ còn đang chạy.
- Không thực sự áp dụng lên join point mong đợi vì pointcut/weaving không phù hợp.

**Mục tiêu bài học:** kiểm thử đầy đủ return type, return value, nullability, exception propagation, số lượt gọi target và thứ tự advice. Cần tách unit test của logic advice với integration test trên đường thực thi được weave/intercept thật.

## 2. Hợp đồng tĩnh và hợp đồng động

Một interface Java có thể có dạng:

~~~java
interface Operations {
    String lookup(String key);
    int count();
    void refresh();
    String load(String key) throws java.io.IOException;
}
~~~

Đây là mảnh interface minh họa, chưa phải chương trình độc lập. Các phương thức đặt ra hai mặt hợp đồng:

**Hợp đồng tĩnh** gồm chữ ký, kiểu trả về, danh sách checked exceptions trong throws, khả năng nhìn thấy và giao diện mà caller biên dịch được.

**Hợp đồng động** gồm kết quả thật, null hợp lệ hay không, object identity khi cần, exception type/cause, thời điểm hoàn tất, số lượt gọi và tác dụng phụ.

Một aspect **chỉ quan sát** thường phải bảo toàn cả hai. Aspect **có chủ đích biến đổi** (ví dụ mapping ngoại lệ, cache hoặc retry) có thể được phép khác ở các điểm đã công bố, nhưng phải có hợp đồng riêng để kiểm thử.

| Đường thực thi gốc | Kết quả kỹ thuật advice có thể quan sát | Người gọi mong đợi khi aspect chỉ quan sát |
| --- | --- | --- |
| Trả object P | RETURN_VALUE | Nhận đúng object P |
| Trả null được phép | RETURN_NULL | Nhận null |
| Trả int 7 | RETURN_VALUE | Nhận giá trị nguyên thủy 7 |
| Void kết thúc bình thường | RETURN_VOID | Không có giá trị trả về; tác dụng phụ đúng |
| Ném IOException E | THROW_IOException | Nhận E theo hợp đồng checked |
| Ném IllegalStateException E | THROW_IllegalStateException | Nhận E, không bị nuốt |
| Ném AssertionError E | THROW_AssertionError | E được truyền, không đổi thành success |
| Before advice từ chối quyền | DENY | Target không được thực thi |

So sánh reference bằng == là một phép thử mạnh cho **aspect chỉ quan sát**: nó phát hiện việc thay object. Với một aspect được phép copy immutable value, hợp đồng có thể yêu cầu bằng giá trị thay vì cùng identity.

## 3. Các loại return type cần kiểm riêng

### 3.1. Kiểu tham chiếu

Ví dụ String, Product, List, mảng hoặc một subtype của interface. Nên kiểm:

1. Giá trị không bị đổi.
2. Object identity được giữ nếu hợp đồng yêu cầu.
3. Runtime class hoặc subtype hợp lệ không bị ép sai.
4. Kết quả mutable không bị advice sửa hoặc tiêu thụ trước caller.
5. Generic type và collection elements không bị biến dạng.

Nếu mọi phép thử dùng Object và không gọi qua interface thật, có thể bỏ sót ClassCastException chỉ phát sinh tại call site khi trả sai kiểu.

### 3.2. Kiểu nguyên thủy

Tất cả boolean, byte, short, char, int, long, float, double đều cần được chuyển tiếp đúng. Khi sử dụng reflection hoặc Java dynamic proxy, các giá trị nguyên thủy được **boxing** trong quá trình xử lý Object và **unboxing** khi về caller. Một handler trả null cho phương thức int không thể biến thành “không có dữ liệu” an toàn; kết quả là lỗi.

Cần test ít nhất một kiểu nguyên thủy và bổ sung trường hợp biên theo domain, ví dụ giá trị âm, zero, boolean false, NaN nếu thực sự liên quan. Với aspect chỉ quan sát, không được làm tròn hoặc tính toán lại mà không có chủ đích.

### 3.3. Void không phải nullable reference

Trong reflection, Method.invoke() trả null cho phương thức void, nhưng điều đó không biến void thành “phương thức trả null”. Nếu dùng null làm dấu hiệu duy nhất để ghi nhận, log/metric có thể báo sai.

~~~java
String outcome = method.getReturnType() == void.class
        ? "RETURN_VOID"
        : result == null ? "RETURN_NULL" : "RETURN_VALUE";
~~~

Đây là đoạn mã trong một InvocationHandler, cần các biến method và result phù hợp. Với void, phải xác nhận side effect xảy ra đúng số lần, không chỉ xác nhận lời gọi không ném exception.

### 3.4. Optional, collection, stream và async

- Optional.empty() là **một đối tượng không-null**, khác với method trả null.
- List hoặc mảng có thể chứa phần tử null dù chính container không null.
- Stream, Iterator và InputStream có thể chỉ dùng được một lần; advice đọc trước để ghi log có thể làm caller mất dữ liệu.
- Future/CompletionStage trả về bình thường là **handle của tác vụ**. Trạng thái cuối của tác vụ phải được quan sát tại completion, không suy ra từ lúc method vừa return.
- Generic và covariant return cần được test từ caller đúng chữ ký, tránh ép object bằng kiểu không tương thích.

## 4. Null: phải đọc theo hợp đồng chứ không đoán từ giá trị

Ba trạng thái quan trọng:

1. **Nullable contract:** tìm một bản ghi không thấy có thể trả null bình thường. Advice không được đổi thành exception chỉ vì null.
2. **Non-null contract:** trả null vi phạm lời hứa của method. Nếu aspect chịu trách nhiệm xác thực non-null thì đó là policy có chủ đích, phải test exception được quy định.
3. **Không có return value:** void không phải một trường hợp nullable.

Một phương thức có thể vừa trả giá trị bình thường vừa trả null ở hai lượt gọi khác nhau. Bộ test nên thử cả hai và chứng minh outcome khác nhau. Cũng nên kiểm tra null argument và null nằm bên trong container khi thuộc phạm vi pointcut.

Ví dụ lỗi thường gặp:

~~~java
Object result = proceed();
System.out.println(result.getClass().getSimpleName());
return result;
~~~

Đây là pseudocode dạng Java của around advice, không thể biên dịch độc lập vì proceed() chưa được định nghĩa. Nếu result là null, chính logic log gây NullPointerException, dù target hoàn tất bình thường. Việc ghi log phải kiểm null trước, và không tạo ra một loại lỗi mới ngoài contract.

## 5. Ngoại lệ: đúng kiểu, nguyên nhân và identity

Trong Java, phân biệt:

- **Checked exception:** ví dụ IOException. Caller được yêu cầu khai báo hoặc xử lý.
- **Unchecked exception:** RuntimeException và subclass như IllegalArgumentException, IllegalStateException.
- **Error:** đại diện những tình huống nghiêm trọng hoặc lỗi lập trình. Với advice chỉ quan sát, không nên nuốt hoặc tự đổi thành success.

Không đủ để test “có ném một exception”. Cần so sánh:

- Exception class.
- Tham chiếu tới cùng exception instance nếu không có chính sách translation.
- Message và cause khi chúng thuộc hợp đồng.
- Target có được thực thi hay không và số lần gọi.
- Exception xảy ra từ **target**, **advice** hay **cơ chế interceptor**.
- Đường lỗi không bị ghi nhầm success và không tự đổi giá trị trả về.

Một cấu trúc around advice đúng về mặt quan sát:

~~~text
try:
    result = proceedExactlyOnce()
    recordNormalCompletionBestEffort()
    return result
catch originalThrowable:
    recordFailureBestEffort(originalThrowable)
    throw originalThrowable
~~~

Đây là pseudocode, không phải một ngôn ngữ AOP cụ thể. Chú ý: nếu recordNormalCompletionBestEffort() có thể ném exception, catch tổng quát phía ngoài có thể nhầm đó là lỗi target. Cần tách vùng try/catch của telemetry để giữ đúng nguồn lỗi và không che exception gốc.

### Ngoại lệ khi dùng reflection

Method.invoke() bọc exception từ phương thức đích trong InvocationTargetException. Nếu proxy chỉ ném nguyên wrapper này thì người gọi không còn thấy IOException hoặc IllegalStateException như hợp đồng gốc. Handler nên unwrap:

~~~java
try {
    return method.invoke(target, args);
} catch (java.lang.reflect.InvocationTargetException ex) {
    throw ex.getCause();
}
~~~

Đây là mảnh code thuộc InvocationHandler.invoke(...) có throws Throwable. Với Java dynamic proxy, checked exception từ handler phải phù hợp với throws của interface. Nếu ném một checked exception không được khai báo, caller có thể gặp UndeclaredThrowableException. Không sử dụng một wrapper đó như bằng chứng rằng target ném sai: cần xác định lỗi được biến đổi ở tầng nào.

## 6. Ví dụ Java 17 hoàn chỉnh và có thể chạy

Ví dụ dùng dynamic proxy để **mô phỏng một around advice tại ranh giới interface**. Đây không phải toàn bộ ngữ nghĩa của mọi cơ chế weaving, nhưng giúp viết bộ test độc lập và xác minh chính xác những bất biến giá trị/ngoại lệ.

Cần kiểm: Token object giữ nguyên identity; int 7; null; String bình thường; void side effect; cùng instance IOException, IllegalStateException và AssertionError; chính xác tám lần gọi target; outcomes theo thứ tự.

Tạo file **AspectContractTest.java**:

~~~java
import java.io.IOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public class AspectContractTest {
    record Token(String id) {}

    interface Endpoint {
        Token token();
        int number();
        String nullable(boolean present);
        void touch();
        String checked() throws IOException;
        String unchecked();
        String fatal();
    }

    static final class Core implements Endpoint {
        final Token token = new Token("A");
        final IOException io = new IOException("storage");
        final IllegalStateException bad = new IllegalStateException("invalid");
        final AssertionError fatal = new AssertionError("crash");
        int calls;
        int touches;

        public Token token() { calls++; return token; }
        public int number() { calls++; return 7; }
        public String nullable(boolean present) {
            calls++;
            return present ? "ok" : null;
        }
        public void touch() { calls++; touches++; }
        public String checked() throws IOException { calls++; throw io; }
        public String unchecked() { calls++; throw bad; }
        public String fatal() { calls++; throw fatal; }
    }

    static final class Recorder implements InvocationHandler {
        final Endpoint target;
        final List<String> outcomes = new ArrayList<>();

        Recorder(Endpoint target) { this.target = target; }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            try {
                Object result = method.invoke(target, args);
                String outcome = method.getReturnType() == void.class
                        ? "RETURN_VOID"
                        : result == null ? "RETURN_NULL" : "RETURN_VALUE";
                outcomes.add(method.getName() + ":" + outcome);
                return result;
            } catch (InvocationTargetException ex) {
                Throwable cause = ex.getCause();
                outcomes.add(method.getName() + ":THROW_"
                        + cause.getClass().getSimpleName());
                throw cause;
            }
        }
    }

    static void check(String name, boolean condition) {
        if (!condition) throw new AssertionError(name);
        System.out.println("PASS " + name);
    }

    public static void main(String[] args) throws IOException {
        Core core = new Core();
        Recorder recorder = new Recorder(core);
        Endpoint endpoint = (Endpoint) Proxy.newProxyInstance(
                Endpoint.class.getClassLoader(),
                new Class<?>[] { Endpoint.class }, recorder);

        check("reference identity", endpoint.token() == core.token);
        check("primitive", endpoint.number() == 7);
        check("null", endpoint.nullable(false) == null);
        check("normal value", "ok".equals(endpoint.nullable(true)));
        endpoint.touch();
        check("void side effect", core.touches == 1);

        try {
            endpoint.checked();
            throw new AssertionError("checked exception missing");
        } catch (IOException actual) {
            check("checked identity", actual == core.io);
        }
        try {
            endpoint.unchecked();
            throw new AssertionError("runtime exception missing");
        } catch (IllegalStateException actual) {
            check("unchecked identity", actual == core.bad);
        }
        try {
            endpoint.fatal();
            throw new AssertionError("Error missing");
        } catch (AssertionError actual) {
            check("Error identity", actual == core.fatal);
        }

        check("proceed once", core.calls == 8);
        check("outcomes", recorder.outcomes.equals(List.of(
                "token:RETURN_VALUE", "number:RETURN_VALUE",
                "nullable:RETURN_NULL", "nullable:RETURN_VALUE",
                "touch:RETURN_VOID", "checked:THROW_IOException",
                "unchecked:THROW_IllegalStateException",
                "fatal:THROW_AssertionError")));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 AspectContractTest.java
java AspectContractTest
~~~

**Stdout chính xác:**

~~~text
PASS reference identity
PASS primitive
PASS null
PASS normal value
PASS void side effect
PASS checked identity
PASS unchecked identity
PASS Error identity
PASS proceed once
PASS outcomes
~~~

Chương trình trên **đã được biên dịch bằng javac --release 17 và chạy thành công** trong môi trường JDK 21. Tất cả mười phép kiểm đều PASS. Việc dùng --release 17 buộc compiler kiểm tra API và cú pháp phù hợp với Java 17.

### Cách đọc các kiểm thử

1. **Reference:** method token() qua proxy trả đúng instance do Core tạo, chứng minh aspect quan sát không thay đổi object.
2. **Primitive:** number() vẫn trả int 7; reflection có thể dùng Integer trung gian nhưng caller vẫn thấy int đúng.
3. **Null:** nullable(false) trả null hợp lệ. Đường khác nullable(true) trả String "ok", nên recorder phải phân biệt.
4. **Void:** touch() không trả giá trị; tác dụng phụ touches tăng đúng một.
5. **Checked exception:** IOException gốc được ném lại, không thành InvocationTargetException hoặc RuntimeException khác.
6. **Unchecked exception:** IllegalStateException gốc không bị nuốt.
7. **Error:** AssertionError gốc không bị đổi thành exception khác.
8. **Proceed count:** Core nhận tám lời gọi, không bị retry hoặc gọi trùng từ recorder.
9. **Outcomes:** recorder ghi RETURN_VOID khác RETURN_NULL, và giữ ba trạng thái lỗi theo loại Throwable.

Bộ test chạy tuần tự, nên ArrayList trong recorder chỉ là cấu trúc đơn giản để assert dữ liệu. Với nhiều luồng, collector cần thiết kế thread-safe và chính sách giới hạn tài nguyên. Java dynamic proxy chỉ chặn lời gọi **qua proxy interface**; không được suy ra rằng method call trực tiếp vào Core hoặc self-invocation cũng bị advice chặn.

## 7. Test logic advice riêng và test điểm weave thật

Một bộ kiểm thử đầy đủ nên có hai tầng.

### 7.1. Unit test cơ chế advice

Tạo test double cho proceed/target có thể:

- Trả cùng một object cố định.
- Trả kiểu primitive.
- Trả null hợp lệ.
- Trả void kèm bộ đếm side effect.
- Ném đúng instance checked, unchecked hoặc Error.
- Theo dõi số lần gọi proceed.
- Có thể làm collector telemetry ném lỗi để đo ảnh hưởng đến target.
- Kiểm thử kết quả mutable, mảng, Optional, generic và stream nếu API cần.

Tầng này xác nhận logic branching và propagation, nhưng **chưa đảm bảo pointcut chọn đúng join point**.

### 7.2. Integration test qua interception/weaving thực

Khởi chạy app hoặc test fixture với cấu hình AOP thật để xác nhận:

1. Pointcut chọn đúng method call/execution, overload, annotation hoặc loại tham số.
2. Advice chạy theo thứ tự đã thiết kế.
3. Caller thật thấy return value/null/checked exception đúng contract.
4. Lời gọi trực tiếp, self-invocation, static context hoặc method không đi qua proxy được xử lý đúng phạm vi cơ chế.
5. Khi nhiều aspect cùng tham gia (cache, authorization, retry, transaction, tracing), giá trị và exception còn chính xác.
6. Bật/tắt riêng phần quan sát tùy chọn không thay đổi nghiệp vụ.

Đặc biệt, không test mỗi class lõi rồi khẳng định aspect đã áp dụng: phép thử đó không chứng minh weaving. Với code-style AspectJ, compile/weave bằng công cụ tương ứng và chạy trên những class đã weave thực sự; ví dụ Java dynamic proxy ở đây chỉ là một phép thử hợp đồng giá trị, không thay thế integration test của AspectJ.

## 8. Test collector lỗi mà không che kết quả nghiệp vụ

Xét advice ghi metric trong finally:

~~~text
start = monotonicClock.now()
try:
    return proceed()
finally:
    metrics.record(elapsed)
~~~

Đây là pseudocode. Nếu metrics.record(...) ném exception, lỗi ấy có thể **thay thế return value hoặc exception gốc**. Nếu metric chỉ best-effort, phải cô lập lỗi ghi metric để giữ kết quả nghiệp vụ.

| Target | Collector | Mong đợi của aspect best-effort |
| --- | --- | --- |
| Trả object P | Thành công | Trả P |
| Trả object P | Ném lỗi | Vẫn trả P |
| Trả null | Ném lỗi | Vẫn trả null |
| Trả void | Ném lỗi | Vẫn hoàn tất void |
| Ném IOException E | Thành công | Ném E |
| Ném IOException E | Ném lỗi | Vẫn ném đúng E |
| Ném Error E | Ném lỗi | Vẫn truyền đúng Error gốc |

Cần kiểm source của lỗi và số lần proceed. Đừng đơn giản catch toàn bộ Throwable rồi return null. Nếu chức năng đang kiểm thử là **audit bắt buộc** theo domain chứ không phải metric best-effort, chính sách lỗi có thể yêu cầu thất bại; phải ghi rõ hợp đồng riêng đó.

### Zero, one và multiple proceed

- Với aspect quan sát và target thực thi bình thường: thường phải gọi proceed đúng một lần.
- Với advice từ chối authorization: phải gọi proceed **zero** lần ở nhánh bị từ chối.
- Với retry policy có chủ đích: có thể gọi nhiều lần **chỉ khi** hợp đồng, idempotency và giới hạn retry cho phép.
- Với cache hit: có thể không gọi target; khi đó test phải xác nhận trả đúng kết quả cache theo ngữ cảnh.

Vì vậy, “proceed once” là invariant của **loại aspect trong ví dụ**, không phải định luật của mọi around advice.

## 9. Exception từ advice, target và proxy khác nhau ra sao?

Để chẩn đoán đúng, phân biệt:

1. Exception từ before/around advice trước proceed: target chưa được gọi.
2. Exception từ target: cần bảo toàn kiểu, cause và identity theo hợp đồng.
3. Exception từ after-returning/after/finally: có thể che kết quả gốc.
4. Exception từ reflection/proxy: có thể là InvocationTargetException, UndeclaredThrowableException, IllegalAccessException, ClassCastException hoặc lỗi unboxing tùy cách triển khai.

Một phép kiểm chỉ có assertThrows(Exception.class) quá yếu: nó có thể PASS khi target ném IOException nhưng interceptor trả ClassCastException. Nên assert đúng lớp ngoại lệ, thông điệp/cause, số lượt target thực thi, và nếu cần cùng instance exception.

Nếu aspect **cố ý chuyển đổi** ngoại lệ, phải có bảng mapping được xác nhận, giữ nguyên nhân cần thiết và test ngoại lệ không thuộc mapping không bị thay đổi.

## 10. Trường hợp bất đồng bộ: return không phải completion

Với CompletionStage<T>, phương thức có thể trả handle thành công ngay trước khi tác vụ thật hoàn tất.

Bộ test phải tách:

**Return-boundary tests**
- Advice trả đúng handle hoặc wrapper được phép theo hợp đồng.
- Không tự join()/get() làm blocking.
- Không tạo coupling cancellation bất ngờ giữa nhiều caller.
- Không coi trả Future thành công là operation success cuối.

**Completion-boundary tests**
- Stage hoàn tất với giá trị non-null.
- Stage hoàn tất bình thường với null.
- Stage hoàn tất exceptional, giữ nguyên nhân gốc phù hợp.
- Cancellation được ghi nhận khác với success và general failure theo hợp đồng.
- Callback quan sát không biến stage thành thất bại do lỗi ghi metric.

Với Future.get() hoặc join(), ngoại lệ wrapper xuất hiện ở API đợi có thể khác exception bên trong task; cần xác minh nguyên nhân gốc. Đường nhận kết quả của stream, iterator hoặc publisher cũng cần test tại thời điểm tiêu thụ, không chỉ thời điểm method return.

## 11. Bảng kiểm thử hồi quy tối thiểu

| Nhóm | Case | Bất biến chính |
| --- | --- | --- |
| Reference | Trả object | Type, giá trị, identity nếu cần |
| Reference | Trả subtype | Không bị cast sai |
| Primitive | int/boolean | Giá trị/kiểu chính xác |
| Void | Side effect | Gọi đúng số lần, hoàn tất bình thường |
| Nullable | Trả null | Không chuyển thành lỗi hay object giả |
| Nullable | Trả non-null | Không đổi giá trị |
| Checked | IOException | Lỗi gốc theo hợp đồng, không wrap ngoài ý muốn |
| Unchecked | IllegalStateException | Lỗi không bị nuốt |
| Error | AssertionError | Không đổi thành success |
| Recorder | Ghi metric lỗi | Không che return/exception nếu best-effort |
| Pointcut | Call qua advice | Advice có chạy đúng ranh giới |
| Pointcut | Không match | Không làm thay đổi code ngoài phạm vi |
| Composition | Nhiều aspect | Thứ tự và kết quả theo chính sách |
| Async | Future trả trước completion | Không ghi nhận success cuối quá sớm |
| Async | Completion null/error/cancel | Trạng thái được phân biệt |
| Concurrency | Nhiều luồng | Collector an toàn, không race/đếm sai |

### Những lỗi phổ biến

- Kiểm một String return rồi kết luận tương thích với primitive/void.
- Coi result == null luôn là lỗi hoặc luôn là void.
- Dùng result.getClass() khi chưa kiểm null.
- Dùng Method.invoke() mà không unwrap InvocationTargetException.
- Nuốt RuntimeException hoặc Error để giữ dashboard “xanh”.
- Assert chỉ exception message nhưng không kiểm type/cause.
- Metric sink ném lỗi trong finally và che IOException gốc.
- Tự động retry làm tăng số tác dụng phụ mà không có idempotency.
- Test trực tiếp class lõi nhưng không test đường gọi đã weave.
- Không kiểm completion thực tế của tác vụ async.

## 12. Checklist áp dụng cho dự án

1. Ghi rõ những kiểu return mà pointcut có thể chọn, gồm primitive, void và nullable reference.
2. Xác định null có hợp lệ không cho từng phương thức, không suy từ object type chung.
3. Xác định advice chỉ quan sát hay có chủ đích biến đổi kết quả.
4. Test đúng giá trị, identity nếu phù hợp và side effect.
5. Test checked, unchecked, Error; so sánh type và cause/identity cần thiết.
6. Khi dùng reflection, kiểm quy tắc unwrap và throws của interface.
7. Test lỗi do chính logic advice gây ra, nhất là collector trong finally.
8. Kiểm số lần proceed trên từng nhánh.
9. Kiểm pointcut/weaving thật bằng integration test, không chỉ unit test.
10. Test async ở cả method-return và task-completion boundaries.
11. Đưa các test dạng negative path vào CI và chạy lại khi đổi method signature hoặc thứ tự aspect.
12. Dùng trace/log tối thiểu để chẩn đoán mà không tiết lộ tham số nhạy cảm.

**Kết luận:** Aspect được viết đúng không chỉ chạy ở đúng join point mà còn phải **tôn trọng hợp đồng của phương thức gốc**. Reference, primitive, void, null bình thường, checked/unchecked exceptions, Error và async completion đều cần những phép thử riêng. Kiểm thử logic advice kết hợp kiểm thử weaving thực tế là cách bảo vệ hiệu quả trước những lỗi khó thấy do AOP tạo ra.

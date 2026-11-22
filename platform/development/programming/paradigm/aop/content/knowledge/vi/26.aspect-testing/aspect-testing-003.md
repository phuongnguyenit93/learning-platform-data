# Kiểm thử âm để phát hiện can thiệp ngoài phạm vi trong AOP

## 1. Mục tiêu và cách hiểu đúng “kiểm thử âm”

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, **AOP**), pointcut chọn những **join point** mà advice sẽ chạy. Kiểm thử thường tập trung vào đường dương tính: một phương thức nằm trong phạm vi được chọn thì advice có thực thi hay không. Nhưng thiết kế aspect chỉ đúng khi nó **không can thiệp vào những điểm ngoài phạm vi**.

**Kiểm thử âm (negative testing) trong bài này** là chủ động thực thi các đường gọi mà một aspect **không được áp dụng**, rồi xác nhận không có dấu vết can thiệp tương ứng. Ví dụ, một advice đo nghiệp vụ không được chạy khi phương thức ghi metric được gọi; một retry advice không được tự động lặp tác vụ gửi thanh toán chưa có idempotency; một advice ghi log thông số không được đọc payload bí mật của phương thức nằm trong danh sách loại trừ.

Điểm phân biệt quan trọng:

- **Điểm phải được can thiệp nhưng advice không chạy:** lỗi **thiếu độ bao phủ**, cần kiểm thử dương tính phát hiện.
- **Điểm bị loại trừ nhưng advice vẫn chạy:** lỗi **can thiệp ngoài phạm vi**, cần kiểm thử âm phát hiện.
- **Điểm bị loại trừ và advice không chạy vì cơ chế AOP bị tắt hoàn toàn:** chưa đủ bằng chứng; phải có kiểm soát dương tính cho thấy aspect thực sự đang hoạt động ở điểm được phép.
- **Advice có chạy nhưng không phát log vì logger bị tắt:** không được coi là bằng chứng advice không chạy. Cần quan sát trực tiếp lời gọi advice hoặc tác động đặc trưng của nó bằng một probe tin cậy.

Kiểm thử âm không đồng nghĩa chỉ kiểm tra rằng kết quả trả về bình thường. Một advice không mong muốn có thể chạy rồi vẫn giữ nguyên kết quả, nhưng làm tăng chi phí, ghi lộ dữ liệu, gọi API ngoài, đổi transaction context hoặc tạo telemetry thừa.

Sau bài này, người học có thể lập danh sách điểm được chọn và bị loại trừ, xây test oracle, kiểm thử lớp proxy/weaving theo ngữ nghĩa AOP thực tế, dùng probe và assertions đáng tin, kiểm tra tương tác nhiều aspect, cũng như thiết kế regression test chống nới pointcut ngoài ý muốn.

## 2. Xác định hai tập điểm trước khi viết test

Gọi:

- **J** là tập join point có thể xuất hiện trong phạm vi công cụ AOP đang kiểm tra.
- **R** là tập **required**: join point phải có một advice cụ thể.
- **F** là tập **forbidden**: join point không được áp dụng advice ấy.
- **A** là tập thực tế đã được advice áp dụng trong phép chạy kiểm thử.

Hai bất biến cần kiểm tra:

~~~text
Required coverage:     R ⊆ A
Forbidden exclusion:   F ∩ A = ∅
~~~

Điều kiện đầu là kiểm thử dương tính; điều kiện sau là **kiểm thử âm**. Một hệ thống muốn tự tin về phạm vi cần kiểm tra **cả hai**.

Ví dụ với một aspect ghi số liệu thời gian ở tầng nghiệp vụ:

| Join point hoặc đường gọi | Phạm vi kỳ vọng | Vì sao? |
| --- | --- | --- |
| Thực thi thao tác submitOrder | REQUIRED | Là ranh giới nghiệp vụ cần đo |
| Thực thi phương thức healthCheck | FORBIDDEN | Không thuộc operation được đo |
| Thực thi MetricsExporter.publish | FORBIDDEN | Advice có thể tự gọi exporter, gây recursion |
| Thực thi passwordFormatter hoặc logSecret | FORBIDDEN | Có nguy cơ đọc hoặc ghi dữ liệu nhạy cảm |
| Thực thi phương thức của một thành phần mới | REVIEW | Chưa xác định nên thêm hay loại |
| Gọi submitOrder từ một callback mới | REVIEW/REQUIRED tùy cơ chế | Phải xác minh join point có thực sự được weaving |

**R và F luôn gắn với một advice cụ thể.** Một lời gọi có thể thuộc R của logging nhưng thuộc F của retry. Không nên tạo một danh sách “cấm mọi AOP” cho cả hệ thống mà không giải thích tính chất của từng aspect.

Các thông tin phải được chốt cho mỗi test case:

1. Loại join point: method execution, method call hay loại khác.
2. Chữ ký/kiểu và vị trí mã chứa join point.
3. Đối tượng thực nhận lời gọi: proxy, target, object đã được weave hay đối tượng khác.
4. Aspect/advice nào đang được xét, thứ tự áp dụng của advice nếu có nhiều.
5. Tín hiệu test dùng để kết luận advice chạy hoặc không chạy.
6. Tác dụng phụ mà advice bị cấm có thể gây ra nếu chạy.
7. Phạm vi build/runtime đã bật instrumentation và có tính đại diện cho sản phẩm.

## 3. Những dạng can thiệp ngoài phạm vi thường cần phát hiện

### 3.1. Pointcut quá rộng

Ví dụ một biểu thức chọn “mọi phương thức public trong toàn module” có thể match thêm utility, health endpoint, logger, exporter hoặc lớp mới được thêm sau khi viết pointcut.

~~~text
Dự kiến:
  OrderService.placeOrder -> advice
  OrderService.health     -> không advice

Sau khi nới pointcut:
  OrderService.placeOrder -> advice
  OrderService.health     -> advice ngoài ý muốn
~~~

Một bài kiểm thử âm gọi health() rồi xác minh advice không chạy sẽ phát hiện sự thay đổi này, ngay cả khi kết quả health vẫn trả về bình thường.

### 3.2. Bỏ sót điều kiện loại trừ

Một pointcut vừa chọn operation nghiệp vụ vừa loại trừ infrastructure có thể được mô hình hóa như:

~~~text
selected = businessOperations AND NOT telemetryInternals
~~~

Nếu điều kiện NOT bị mất trong một lần refactor, cùng một advice logging có thể chặn cả chính phương thức exporter. Kết quả thường là log storm hoặc vòng gọi lồng nhau không kết thúc.

Kiểm thử âm nên có một case riêng cho từng nhóm loại trừ trọng yếu, thay vì kiểm tra chỉ một trường hợp bất kỳ.

### 3.3. Sai vị trí lexical hoặc sai kiểu join point

Trong các mô hình AOP có phân biệt method-call và method-execution:

- Advice tại **call site** có thể chạy vì đoạn mã gọi được match, dù phương thức được gọi thuộc một module khác.
- Advice tại **method execution** bám theo việc thực thi thân phương thức đã được instrument.
- Điều kiện phạm vi như **within** thường giới hạn vùng mã chứa join point theo ngữ nghĩa của công cụ.

Một pointcut định giới hạn code gọi trong module A nhưng lại chọn thêm call site ở module B là lỗi ngoài phạm vi. Ngược lại, một điểm execution ở callee không nhất thiết nằm trong cùng vùng lexical với caller.

Vì vậy, testcase phải ghi rõ kỳ vọng **không advice ở call site cụ thể** hay **không advice ở execution cụ thể**. Nếu chỉ assert kết quả cuối, rất khó biết loại điểm bị chọn sai.

### 3.4. Lời gọi lồng nhau gây advice hai lần

Giả sử một lời gọi nghiệp vụ bên ngoài dẫn vào phương thức con cùng match pointcut. Nếu chính sách chỉ muốn ghi **một kết quả cuối cho operation**, advice ghi kết quả chạy ở cả cha và con có thể tạo hai sự kiện.

~~~text
processOrder  -> RecordFinal?
    reserveInventory -> RecordFinal? (không mong muốn nếu đây chỉ là bước con)
~~~

Kiểm thử âm cần xác nhận **không có sự kiện final ở join point con**, chứ không chỉ xác nhận tổng số log lớn hơn 0. Có thể vẫn có trace/span cấp con nếu đó là một aspect khác đã được phép.

### 3.5. Retry áp dụng vào thao tác không được lặp

Một method gửi email, tạo thanh toán hoặc phát message có thể thuộc ngoài phạm vi của retry advice nếu chưa có idempotency. Nếu advice vô tình chạy, một lỗi tạm thời có thể khiến proceed() được gọi nhiều lần.

Kiểm thử âm phải tiêm lỗi và xác nhận **số lượt thực hiện effect** không bị nhân đôi. Không nên chỉ nhìn vào việc người gọi cuối cùng nhận exception.

### 3.6. Recorder, transaction hoặc context advice chạm sai lifecycle

Một aspect có thể vô tình mở transaction ở hàm chỉ đọc, giữ connection qua callback, hoặc đính correlation context vào thread pool rồi không khôi phục. Các lỗi ấy có thể xảy ra ngay cả khi giá trị trả về giống nhau.

Đối với join point nằm ngoài phạm vi, testcase nên xác minh không phát sinh transaction begin, không thay context, không mở/đóng tài nguyên và không ghi metric đáng lẽ chỉ thuộc operation được chọn.

## 4. Test oracle: làm sao chứng minh “không có advice”?

**Oracle** là điều kiện mà bài test dùng để xác định pass/fail. Chứng minh một điều không xảy ra khó hơn nhìn thấy một sự kiện đã xảy ra. Vì vậy cần thiết kế chứng cứ trực tiếp.

### 4.1. Dùng probe ghi số lần advice vào/ra

Tạo một probe độc lập ghi lại:

~~~text
ADVICE_ENTER: operation-name
ADVICE_RETURN: operation-name
ADVICE_THROW: operation-name
~~~

Với điểm thuộc F, số event advice tương ứng phải **bằng 0**. Với điểm thuộc R, số event phải phù hợp với hợp đồng, thường ít nhất một hoặc chính xác một trong phép thử đơn giản.

Nếu advice chỉ ghi vào logger trong production, trong test có thể sử dụng một recorder/fake có thể quan sát được. Recorder này phải **không bị chính pointcut đang kiểm thử intercept**.

### 4.2. Kết hợp với phép kiểm tra hành vi đích

Một bài test tốt không chỉ assert số advice bằng 0; nó còn xác nhận đường gọi **đã thực thi thật**:

~~~text
invoke excludedOperation()
assert targetInvocations == 1
assert adviceInvocations == 0
assert returnValue == expected
~~~

Nếu targetInvocations cũng bằng 0, có thể test chưa gọi đúng đường, nên giá trị adviceInvocations bằng 0 không nói lên được điều gì.

Với một operation không có side effect, có thể dùng spy/counting stub để chứng minh target được gọi đúng một lần. Với effect nhạy cảm, cần kiểm tra trạng thái tài nguyên thực và số lần gửi thông điệp/đòi tiền bằng stub hoặc sandbox phù hợp.

### 4.3. Không dựa vào “không thấy log”

Vắng log có thể do:

- Advice không chạy.
- Advice chạy nhưng log level không cho phép in.
- Sampling loại bỏ event.
- Exporter mất sự kiện.
- Ghi log bất đồng bộ chưa flush.
- Lỗi logger bị nuốt.
- Logger bị instrument rồi xảy ra recursion hoặc deadlock.

Do đó, đo số lần advice bằng probe/spy trực tiếp trong test là dấu hiệu đáng tin hơn. Log có thể là chứng cứ phụ trợ, không phải oracle duy nhất.

### 4.4. Kiểm soát dương tính chống phép thử rỗng

Luôn có ít nhất một case thuộc R trên **cùng cấu hình và build runtime** để bảo đảm advice hoạt động. Ví dụ:

~~~text
Case positive: approvedOperation()
    targetInvocations = 1
    adviceInvocations = 1

Case negative: health()
    targetInvocations = 1
    adviceInvocations = 0
~~~

Nếu cả hai case đều có adviceInvocations = 0, test âm không được tính là bằng chứng loại trừ đúng; rất có thể aspect chưa được đăng ký hoặc weaving bị tắt.

## 5. Ví dụ Java 17+ tự chạy: kiểm thử âm và kiểm soát dương tính

Đoạn chương trình sau sử dụng **Java Dynamic Proxy** để minh họa cơ chế interception dựa trên interface. Nó không thay thế cơ chế AOP tổng quát hoặc bytecode weaving. Một annotation tên Observed biểu diễn allowlist do bài test định nghĩa. Proxy ghi event khi một phương thức được chọn bị intercept; các phương thức không được chọn vẫn gọi target bình thường.

Ví dụ có các ca sau:

1. Phương thức transfer() thuộc phạm vi: phải có advice.
2. health() bị loại: không được có advice.
3. emitMetric() thuộc hạ tầng quan sát: không được bị instrument bởi cùng advice.
4. batch() không được chọn; nó gọi transfer() trên chính target. Test chứng minh lời gọi nội bộ không đi qua proxy trong mô hình này.
5. Lời gọi thẳng target.transfer() cũng không đi qua proxy.
6. Một proxy **cố tình chọn mọi method** được dùng làm mutation: kiểm thử âm phải nhận ra rằng health() đã bị can thiệp ngoài phạm vi.

Tạo tệp **AspectNegativeTestDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;

public final class AspectNegativeTestDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Observed {}

    interface Gateway {
        @Observed
        void transfer();
        void health();
        void emitMetric();
        void batch();
    }

    static final class RealGateway implements Gateway {
        private final List<String> events;

        RealGateway(List<String> events) {
            this.events = events;
        }

        public void transfer() {
            events.add("business.transfer");
        }

        public void health() {
            events.add("business.health");
        }

        public void emitMetric() {
            events.add("infrastructure.metric");
        }

        public void batch() {
            events.add("business.batch");
            transfer(); // Lời gọi trực tiếp trên target, không qua proxy.
        }
    }

    static Object invokeTarget(
            Gateway target, Method method, Object[] args) throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static Gateway instrument(
            Gateway target,
            Predicate<Method> selected,
            List<String> events) {
        return (Gateway) Proxy.newProxyInstance(
                Gateway.class.getClassLoader(),
                new Class<?>[]{Gateway.class},
                (proxy, method, args) -> {
                    if (!selected.test(method)) {
                        return invokeTarget(target, method, args);
                    }

                    events.add("advice.before " + method.getName());
                    try {
                        Object result = invokeTarget(target, method, args);
                        events.add("advice.after " + method.getName());
                        return result;
                    } catch (Throwable failure) {
                        events.add("advice.throw " + method.getName());
                        throw failure;
                    }
                });
    }

    static void expectSequence(List<String> actual, String... expected) {
        if (!actual.equals(List.of(expected))) {
            throw new AssertionError(
                    "expected=" + List.of(expected) + ", actual=" + actual);
        }
    }

    static void expectNoAdvice(List<String> events) {
        boolean intercepted = events.stream()
                .anyMatch(event -> event.startsWith("advice."));
        if (intercepted) {
            throw new AssertionError("Unexpected advice: " + events);
        }
    }

    public static void main(String[] args) {
        List<String> events = new ArrayList<>();
        RealGateway raw = new RealGateway(events);

        Gateway scoped = instrument(
                raw,
                method -> method.isAnnotationPresent(Observed.class),
                events);

        scoped.transfer();
        expectSequence(events,
                "advice.before transfer",
                "business.transfer",
                "advice.after transfer");
        System.out.println("PASS: selected method intercepted");
        events.clear();

        scoped.health();
        expectSequence(events, "business.health");
        expectNoAdvice(events);
        System.out.println("PASS: health excluded");
        events.clear();

        scoped.emitMetric();
        expectSequence(events, "infrastructure.metric");
        expectNoAdvice(events);
        System.out.println("PASS: metric exporter excluded");
        events.clear();

        scoped.batch();
        expectSequence(events, "business.batch", "business.transfer");
        expectNoAdvice(events);
        System.out.println("PASS: internal target call not intercepted");
        events.clear();

        raw.transfer();
        expectSequence(events, "business.transfer");
        expectNoAdvice(events);
        System.out.println("PASS: raw target bypass observed");
        events.clear();

        // Mutation: nới pointcut sai thành "mọi phương thức".
        Gateway tooBroad = instrument(raw, method -> true, events);
        tooBroad.health();
        boolean detected = false;
        try {
            expectNoAdvice(events);
        } catch (AssertionError expected) {
            detected = true;
        }
        if (!detected) {
            throw new AssertionError("Negative test failed to detect mutation");
        }
        System.out.println("PASS: broadened pointcut detected");
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac AspectNegativeTestDemo.java
java AspectNegativeTestDemo
~~~

Stdout:

~~~text
PASS: selected method intercepted
PASS: health excluded
PASS: metric exporter excluded
PASS: internal target call not intercepted
PASS: raw target bypass observed
PASS: broadened pointcut detected
~~~

### 5.1. Diễn giải chính xác các phép thử

**Selected method intercepted:** khi gọi scoped.transfer(), Method object của interface mang annotation Observed, nên interceptor chạy. Bài test so đúng cả thứ tự advice-before, business, advice-after.

**health excluded:** gọi qua chính proxy nhưng Predicate không chọn health(). Điều này chứng minh loại trừ của predicate có hiệu lực; không phải vì test bỏ qua proxy.

**metric exporter excluded:** ghi telemetry không tự kích hoạt cùng advice. Đây là một dạng negative test quan trọng chống recursion và event amplification.

**Internal target call not intercepted:** scoped.batch() chuyển tới target.batch(), sau đó target tự gọi transfer() trên chính nó. Vì target không gọi proxy, advice cho transfer() không xuất hiện. Đây là hành vi của **mô hình proxy minh họa**, không phải quy tắc cho mọi cơ chế weaving.

**Raw target bypass observed:** gọi thẳng raw.transfer() không có advice. Bài test chứng minh được giới hạn của proxy; **đây không phải kết quả an toàn mong muốn nếu transfer() cần bắt buộc kiểm soát quyền**. Phải phân biệt negative test cho một aspect quan sát được phép bỏ qua đường raw với positive/security test đòi mọi đường tới effect nhạy cảm đều được bảo vệ.

**Broadened pointcut detected:** khi predicate biến thành true cho mọi method, health() bị advice chọn sai. expectNoAdvice ném AssertionError như dự kiến; test harness bắt đúng lỗi để chứng minh oracle sẽ báo lỗi nếu pointcut bị nới rộng.

### 5.2. Giới hạn của ví dụ

- Đây là một chương trình Java thuần **mô phỏng cơ chế chọn join point bằng proxy**, không phải test integration cho một AspectJ weaving pipeline.
- Dynamic Proxy nhận lời gọi qua interface; method được gọi trực tiếp trên target không đi qua InvocationHandler. Với method-execution weaving, kết luận về self-invocation có thể khác.
- Test thực tế không nên chỉ chọn bằng annotation; có thể dùng pointcut expression theo cú pháp công cụ AOP, nhưng vẫn cần bảng expected matches độc lập.
- Một chương trình demo dùng List và thao tác đồng bộ; với nhiều thread, recorder phải thread-safe và bảo đảm thứ tự/correlation. Không lấy output ngẫu nhiên hoặc phụ thuộc thời gian làm oracle cứng.
- Không nên cố tình nới pointcut trong production. Mutation ở đây là một thay đổi giả lập chỉ nằm trong testcase.

## 6. Ma trận kiểm thử âm theo loại aspect

Không có một bộ test chung đủ cho mọi chính sách. Mỗi aspect cần negative tests phù hợp rủi ro riêng.

| Aspect/policy | Join point ngoài phạm vi cần thử | Oracle âm tối thiểu | Rủi ro nếu sai |
| --- | --- | --- | --- |
| Logging | Hàm chứa secret, formatter, logger internals | Không có advice capture, không ghi payload/secret | Rò dữ liệu hoặc recursion |
| Metrics | Exporter, health(), utility quá nhỏ | Không advice đo/không tăng counter tương ứng | Metric sai, overhead cao |
| Tracing | Bootstrap tracer, exporter, vùng excluded | Không tạo span/scope ở điểm cấm | Recursion, trace không đúng |
| Retry | Gửi tiền/email chưa idempotent; validation lỗi cố định | Không gọi proceed() lặp, không backoff retry | Effect trùng, sai semantics |
| Transaction | Utility/read-only bị loại; callback không thuộc transaction | Không begin/commit ngoài scope, không giữ resource | Lock thừa, commit sai |
| Authorization | Các tiện ích được phép bỏ guard, nhưng **không** sensitive effect | Không guard ở utility; đồng thời sensitive effect phải được bảo vệ bằng test dương tính | Overhead hoặc bypass bảo mật |
| Cache | Method có effect bắt buộc | Không short-circuit/hit cache ngoài scope | Bỏ qua effect nghiệp vụ |
| Fallback | Lỗi quyền hoặc vi phạm bất biến nghiệp vụ | Không tạo fallback success ngoài policy | Che lỗi và bỏ kiểm tra |
| Correlation context | Formatter/exporter hoặc worker không thuộc scope | Không rò context, không tạo scope mới ngoài dự kiến | Log sai ID hoặc rò context |
| Audit | Những operation không thuộc diện audit bắt buộc | Không phát record bắt buộc/trùng | Sai bằng chứng, chi phí và độ nhạy dữ liệu |

**Bảo mật:** không được diễn giải việc “authorization advice không chạy ở sensitive method” là pass nếu sensitive method thực sự cần authorization. Với operation nhạy cảm, các đường bypass cần được coi là lỗi qua một test khác; negative tests ở đây chỉ áp dụng cho **điểm được phê duyệt loại trừ**.

## 7. Kiểm thử âm ở tầng join point, advice và hậu quả

Có ba tầng oracle bổ trợ nhau.

### 7.1. Tầng chọn join point

Xác minh pointcut có chọn điểm bị cấm không. Công cụ kiểm thử có thể dùng một probe để ghi các static join point signature, tên kiểu, tên method và loại join point.

Ví dụ bảng oracle:

~~~text
method execution Business.placeOrder   expected=selected
method execution Business.health       expected=excluded
method call from Telemetry.export      expected=excluded
method execution PolicyEngine.evaluate expected=excluded
~~~

Việc assert sai signature phải báo lỗi trước khi suy luận về effect nghiệp vụ.

### 7.2. Tầng chạy advice

Một điểm được pointcut chọn nhưng advice có guard nội bộ và quyết định bỏ qua thao tác có thể **vẫn chạy advice**. Nếu yêu cầu là “tuyệt đối không thực thi advice tại điểm ấy”, việc chỉ kiểm tra không thấy metric cuối là chưa đủ.

Phải phân biệt:

- **Không match pointcut:** advice không vào.
- **Match pointcut nhưng advice early-return/no-op:** advice đã vào, dù không tạo effect chính.
- **Advice chạy và bị logger/sampling làm mất dấu:** không thể kết luận bằng log.

Nếu chính sách chỉ yêu cầu “không có tác dụng phụ X”, early-return có thể được chấp nhận. Nếu yêu cầu “không bị can thiệp”, chỉ số advice invocation cần bằng 0.

### 7.3. Tầng hành vi và side effect

Ngay cả khi advice chạy nhưng không thay giá trị trả về, nó có thể:

- Mở transaction/connection không cần thiết.
- Đọc dữ liệu nhạy cảm để format log.
- Chặn thread khi exporter chậm.
- Ghi metric trùng.
- Gây retry một effect chưa được thiết kế chống lặp.
- Đặt/sai khôi phục ThreadLocal.
- Nuốt một exception mà caller cần thấy.

Do đó, negative tests quan trọng nên assert thêm số connection mở, số event đã ghi, số lượt effect, trạng thái context trước/sau và loại exception giữ nguyên theo hợp đồng.

## 8. Chứng minh kiểm thử âm không “pass giả”

Một negative test chỉ có giá trị khi nó thật sự có khả năng **phát hiện advice bị áp vào điểm cấm**. Nếu toàn bộ bộ dệt không được nạp, handler không được đăng ký hoặc test gọi nhầm đối tượng gốc, kiểm tra `adviceCount == 0` có thể “xanh” trong khi bảo vệ đang hỏng. Vì vậy, xây một **phép thử có chứng cứ dương tính ngay trong cùng runtime** thay vì chỉ viết assertion âm.

### 8.1. Quy trình ba chốt kiểm soát

| Chốt | Quan sát cần có | Khi sai phải làm gì? |
| --- | --- | --- |
| **Target activation** | Điểm ngoài phạm vi đã thật sự được gọi và phát effect dự kiến | Báo lỗi fixture hoặc đường gọi, không kết luận exclude đúng |
| **Instrumentation canary** | Một điểm được phép trong cùng artifact/runtime vẫn nhận đúng advice | Báo lỗi weaving, proxy wiring hoặc recorder, không chấp nhận test âm |
| **Forbidden match assertion** | Điểm cấm có advice invocation **bằng 0**, theo đúng loại aspect và join point | Báo lỗi pointcut quá rộng, thiếu exclusion hoặc wrong join point kind |

Ví dụ bộ kiểm chứng theo event recorder riêng biệt:

~~~text
setup:
    reset deterministic recorder
    verify selectedJoinPoint and forbiddenJoinPoint share test runtime

positive control:
    call requiredOperation
    assert targetCount(requiredOperation) == 1
    assert adviceCount(TracingAspect, requiredOperation) == 1

negative control:
    call excludedOperation
    assert targetCount(excludedOperation) == 1
    assert adviceCount(TracingAspect, excludedOperation) == 0

assert recorder is not disabled, sampled away or intercepted recursively
~~~

Đây là *mã giả*, không phải API dùng chung của mọi công cụ AOP. Tên aspect cần được gắn vào event vì có thể một join point bị loại khỏi **TracingAspect** nhưng vẫn hợp lệ cho **AuthorizationAspect**. Nếu chỉ so tổng số event của mọi aspect, phép thử có thể kết luận nhầm.

### 8.2. Kiểm tra sức phát hiện bằng mutation có mục đích

Để chứng minh negative test thực sự nhạy với lỗi, trong môi trường kiểm thử có thể:

1. Bỏ điều kiện exclusion của đúng aspect đang xét hoặc nới predicate để nó match một điểm cấm.
2. Chạy lại **cùng case âm**; kiểm tra nó thất bại với lý do “forbidden advice observed”.
3. Khôi phục cấu hình đúng; chạy lại cả positive canary và negative test; cả hai phải pass.
4. Lặp lại ở các nhóm cấm có rủi ro khác nhau như logger, serializer, health check và thao tác không được retry.

Mutation phải nằm trong test/build thử nghiệm, không gây tác động ngoài ý muốn tới môi trường production. Nếu test vẫn pass sau khi nới pointcut, có thể đường bị cấm chưa được gọi, recorder không thấy advice, hoặc loại join point đang quan sát không trùng loại join point của rule.

### 8.3. Không nhầm exclusion với đường bypass bảo mật

Trong một proxy-based test, việc gọi trực tiếp target có thể bỏ qua proxy, nên không có advice. Nhưng nếu điểm cần bảo vệ **bắt buộc** đi qua authorization, đó là một *coverage failure*, không phải một negative test thành công. Nhãn “forbidden” phải được thiết kế theo **hợp đồng của từng concern**, không suy từ việc hệ thống tình cờ không intercept.

Các phần tiếp theo triển khai phép thử âm cho những join point cụ thể: `call` và `execution`, self-invocation, overload, hành vi lỗi, context và tài nguyên. Mỗi nhóm phải chứng minh đúng **đường được gọi**, **loại advice được kiểm tra** và **tác dụng không được xảy ra**.

## 9. Kiểm thử âm với `call`, `execution` và vùng mã chứa join point

Một số hệ thống AOP hỗ trợ phân biệt join point ở **vị trí gọi** và **thực thi phương thức**. Tùy cơ chế, trường hợp:

~~~text
A.run() --> B.work()
~~~

có thể có:

~~~text
call(B.work)      ở mã A.run
execution(B.work) ở thân B.work
~~~

Nếu cấu hình cần instrument execution của B nhưng **không** instrument call site trong A, test âm phải khẳng định **không có call-advice**, đồng thời test dương xác nhận **có execution-advice**.

Nếu một pointcut giới hạn theo vùng lexical, cần kiểm tra cả trường hợp call site trong vùng được phép và ngoài vùng:

~~~text
CallerAllowed.invoke  -> call B.work  expected advice at call
CallerExcluded.invoke -> call B.work  expected no call advice
B.work execution      -> xem như một kỳ vọng riêng
~~~

Đừng gộp tất cả event của cùng một phương thức vào một counter. Một lượt gọi có thể có cả call và execution join point; đếm trùng không thể phân biệt nếu event chỉ ghi tên method.

Với những phương thức được gọi từ nhiều package/module, thiết kế test cho từng nhóm caller và **biến thể nơi viết lời gọi**. Di chuyển một câu lệnh từ CallerA sang Helper có thể làm điều kiện lexical thay đổi dù nghiệp vụ không đổi; negative test phải phản ánh quy tắc thực sự mong muốn.

## 10. Self-invocation và đối tượng gốc: test âm không được che một lỗ hổng

Trong interception dựa vào proxy:

~~~text
caller -> proxy.operation()
            -> target.operation()
                  -> this.helper()
~~~

Lời gọi this.helper() có thể không đi qua proxy. Nếu helper **được phê duyệt không có advice telemetry**, việc không có telemetry ở helper là kết quả kỳ vọng. Nhưng nếu helper **bắt buộc có authorization**, cùng hiện tượng ấy là lỗi nghiêm trọng.

Đối với một số cơ chế weaving tại method-execution join point, self-call không nhất thiết bỏ qua advice. Vì vậy test nên dùng đúng loại runtime đang triển khai, không sao chép kỳ vọng từ hệ thống proxy sang weaving hoặc ngược lại.

Cần có các ca:

1. Gọi phương thức qua proxy/đối tượng được instrument.
2. Gọi cùng method từ một method khác trên target.
3. Gọi trực tiếp target nếu đường đó tồn tại trong kiến trúc.
4. Gọi từ callback, worker, job hoặc một entry point khác.
5. Kiểm tra riêng **expected no-advice** và **required guard** cho các hành vi nhạy cảm.

**Không dùng sự thiếu advice trên một đường bypass làm lý do để tuyên bố chính sách bảo mật an toàn.**

## 11. Kiểm thử nhiều aspect có thể cùng match một điểm

Khi có nhiều advice, chỉ kiểm tra tổng số invocation là chưa đủ. Một method có thể được phép tracing nhưng không được phép retry. Nếu test chỉ thấy “có một advice chạy”, nó không chứng minh advice đúng loại.

Ví dụ:

~~~text
Allowed:
    Tracing(BusinessOperation)

Forbidden:
    Retry(NonIdempotentPayment)
    LoggingRawPayload(SecretFormatter)
~~~

Trong test, tạo bộ đếm riêng:

~~~text
traceAdviceEnter
retryAdviceEnter
logPayloadAdviceEnter
transactionAdviceEnter
~~~

Kỳ vọng phải gắn với từng join point và **từng concern**, không chỉ một cờ “intercepted”.

Ngoài ra, thứ tự advice có thể khiến một advice không được chạy dù pointcut thực sự match. Ví dụ Cache ở ngoài Authorization có thể trả kết quả từ cache mà không gọi proceed(); test âm chỉ thấy Authorization không chạy không chứng minh Authorization bị loại khỏi pointcut. Để xác minh selection, tạo một đường khiến outer advice có proceed hoặc đo trực tiếp tập match, rồi kiểm tra thêm các nhánh short-circuit để đảm bảo policy của toàn hệ thống đúng.

## 12. Các biến thể lỗi nên đưa vào test âm

### 12.1. Phương thức overload

Một pointcut chỉ dành cho **save(String)** không được tự động áp cho **save(byte[])** nếu byte[] thuộc danh sách cấm. Gọi cả hai overload trong test và assert match đúng chữ ký.

### 12.2. Kiểu kế thừa hoặc interface

Một lớp con có thể override method hoặc sinh bridge method vì generic. Với proxy và weaving, phạm vi interception khác nhau. Không tự suy đoán từ tên lớp; kiểm tra object thực, chữ ký và điểm join point.

### 12.3. Phương thức final/private/static

Khả năng can thiệp phụ thuộc cơ chế AOP. Subclass proxy không thể override final method theo kiểu thông thường, trong khi weaving có thể áp dụng kỹ thuật khác. Test âm phải chạy trên đúng implementation, không chuyển một giới hạn công cụ thành quy tắc phổ quát.

### 12.4. Reflection, method handle và callback

Reflection vào proxy có thể đi qua handler; reflection vào target có thể không. Method handle cũng phụ thuộc receiver và cơ chế instrument. Callback có thể chạy trên thread khác và không đi qua cùng entry point. Các test này cần nêu rõ receiver, thread, thời điểm và ranh giới xử lý.

### 12.5. Các phương thức tiện ích được gọi từ chính advice

Log formatter có thể gọi toString(), equals(), hashCode() hoặc serializer. Một pointcut quá rộng có thể chặn các lời gọi ấy, tạo vòng đệ quy hoặc chi phí lớn. Gọi trực tiếp các tiện ích trong test và xác nhận không có advice bị cấm.

### 12.6. Constructor và khởi tạo đối tượng

Nếu policy chỉ dành cho method execution, hãy kiểm tra nó không vô tình áp vào constructor/initialization join point nếu runtime AOP hỗ trợ loại điểm đó. Không dùng sai pattern constructor rồi coi kết quả âm là bằng chứng.

## 13. Kiểm thử tình huống âm liên quan lỗi và kết quả trả về

Một aspect bị áp ngoài phạm vi có thể làm thay đổi cách lỗi được quan sát.

Ví dụ một method bị loại trừ ném một exception nghiệp vụ nhất định. Test:

~~~text
Given excludedOperation throws DomainException("invalid")
When call excludedOperation
Then target invoked exactly once
And forbidden advice invoked zero times
And caller receives DomainException with preserved meaning
And no retry, no fallback, no transaction side effect occurred
~~~

Đối với một method trả về kết quả hợp lệ mang trạng thái BUSINESS_REJECTED, cũng không được tự biến nó thành success khác qua fallback nếu policy không áp dụng.

Với retry:

~~~text
Given nonIdempotentAction sends one external message then fails
When invoke through configured AOP boundary
Then forbidden retry advice invocations = 0
And action invocations = 1
And external sends = 1
And original failure is propagated
~~~

Không dùng một dịch vụ thanh toán hoặc email thật trong unit test; sử dụng stub/in-memory recorder hoặc môi trường sandbox. Những bài kiểm thử về độ an toàn của retry nên có integration/fault-injection test bổ sung tại nơi effect thực được tạo.

## 14. Kiểm thử âm cho ngữ cảnh và tài nguyên

Aspect quản lý correlation context, transaction context hay scope tracing có thể rò trạng thái dù không đổi giá trị trả về.

Một testcase ngoài phạm vi cần quan sát:

~~~text
before:
    currentContext = previousContext
    activeTransactions = 0

invoke excludedOperation()

after:
    currentContext == previousContext
    activeTransactions == 0
    unexpectedSpanCount == 0
    unexpectedAdviceCount == 0
~~~

Nếu method được chạy trong thread pool, test một nhiệm vụ **tiếp theo trên cùng worker** để xem có context bị giữ sót không. Phải phân biệt ngữ cảnh do caller hợp lệ gắn sẵn với ngữ cảnh mới do aspect bị cấm tạo ra.

Với asynchronous API, ranh giới hoàn tất là quan trọng: một method có thể trả future ngay nhưng tác vụ vẫn chạy. Không kết luận không có advice/effect chỉ vì trước lúc callback chạy chưa thấy sự kiện. Test cần chờ completion hoặc tạo scheduler điều khiển được để kết quả không phụ thuộc may rủi.

Với Publisher có thể có nhiều subscription, một assertion ở lúc tạo publisher không đủ chứng minh không có advice tại subscribe/terminal signal. Hãy thiết kế test theo lifecycle mà policy thật sự định áp dụng.

## 15. Test âm không ổn định và các cách làm cho kết quả đáng tin

### 15.1. Không dùng sleep tùy ý để chờ event

Nếu test phát triển dựa trên Thread.sleep(100), kết quả có thể pass/fail tùy CPU. Hãy dùng synchronization primitives hoặc hoàn tất của future/scheduler do test điều khiển, cộng với deadline hợp lý.

### 15.2. Cô lập event giữa các test

Reset counter và event list trước mỗi case. Nếu dùng recorder toàn cục, một event từ testcase trước có thể khiến case sau fail giả. Trong môi trường concurrent, gắn call ID hoặc test ID và chỉ assert những event thuộc phạm vi hiện tại.

### 15.3. Không ghi nhận event bằng chính aspect bị test

Nếu probe nằm trong phạm vi pointcut, kết quả có thể đệ quy hoặc méo. Recorder nên ở ngoài phạm vi can thiệp hoặc có điều kiện loại trừ độc lập đã được xác minh.

### 15.4. Đối chiếu cả kết quả và absence

Một negative test tốt thường assert:

- Đúng method/đường gọi đã được thực thi.
- Giá trị trả về và exception không bị thay đổi ngoài hợp đồng.
- Số advice bị cấm bằng 0.
- Số side effect phụ do advice bị cấm bằng 0.
- Không có rò resource/context sau khi hoàn tất.

Không cần mọi testcase đều assert tất cả; chọn theo rủi ro. Nhưng riêng absence của một log không đủ.

### 15.5. Dùng kiểm soát dương tính trên cùng runtime

Nếu test âm chạy với weaving bị tắt còn test dương dùng một runtime khác, không chứng minh exclusion đúng trong production. Cấu hình instrumentation phải được xác thực trong môi trường tương đương, hoặc có integration suite kiểm tra đúng build/artefact.

## 16. Mutation testing: cố tình nới pointcut để kiểm tra chất lượng phép thử

Một negative test chỉ đáng tin nếu nó **fail khi vùng cấm bị can thiệp**. Có thể kiểm tra bằng mutation:

1. Bỏ một điều kiện loại trừ khỏi pointcut ở cấu hình test.
2. Thay allowlist predicate bằng một predicate rộng hơn.
3. Thay package giới hạn bằng tập bao phủ toàn module.
4. Đổi điều kiện loại trừ đối với telemetry internals.
5. Chuyển method ngoài phạm vi sang group được match và xem test có phát hiện.

Kỳ vọng: testcase dành cho vùng cấm phải fail. Nếu nó vẫn pass, có thể đang:

- Không gọi đúng method.
- Đo sai loại advice.
- Đọc log của observer bị tắt.
- Kiểm tra kết quả cuối mà bỏ qua việc advice đã chạy.
- Không kích hoạt đúng điều kiện khiến pointcut mới match.
- Dùng runtime không có instrumentation.

Trong ví dụ Java ở phần trước, proxy tooBroad là mutation cố ý; expectNoAdvice bắt được việc health() bị chọn sai. Đó là kiểm chứng chất lượng oracle, không phải yêu cầu đưa mutation vào production.

Không dùng mutation testing để thay thế kiểm thử tích hợp với cơ chế AOP thật. Nó giúp kiểm tra rằng suite có khả năng phát hiện **một loại sai lệch** được mô phỏng.

## 17. Kiểm thử tích hợp trên runtime AOP thật

Ví dụ tự chạy bằng Java Dynamic Proxy chứng minh nguyên lý, nhưng một dự án dùng bytecode weaving hoặc interception khác cần kiểm thử trực tiếp công cụ đang dùng.

### 17.1. Cấu hình cần cố định

- Bản build và tập class được instrument.
- Loại weaving/interception: trước biên dịch, sau biên dịch, tại class load, hoặc proxy.
- Classloader/module và tập điểm được áp dụng.
- Thứ tự/precedence của advice khi nhiều aspect match.
- Các flag tắt/bật hoặc điều kiện môi trường cho instrumentation.
- Phiên bản Java và compiler tương thích.

Một suite test có thể pass vì test chạy trên class chưa được weave, trong khi production đã bật weaving rộng hơn. Ngược lại, test có thể fail vì double-instrument một lớp. Cần kiểm tra cấu hình thực tế tương ứng.

### 17.2. Hai kiểu kiểm thử bổ sung

**Unit test policy-selection:** dùng fake join point hoặc một adapter phân loại method để kiểm thử các rule ALLOW/DENY nhanh và rõ.

**Integration test interception:** thực thi qua cơ chế AOP thật rồi xác minh advice nào chạy, số lần, thứ tự, exception và side effect. Đây là bằng chứng quan trọng cho việc “ngoài phạm vi thực sự không bị can thiệp”.

Một pointcut dạng chuỗi có thể match theo quy tắc rất khác với predicate đơn giản trong unit test. Vì vậy **unit test của predicate không tự chứng minh một expression thật được áp dụng đúng**.

### 17.3. Kiểm thử class mới

Khi thêm lớp mới vào package/mô-đun, pointcut dùng wildcard có thể đột nhiên chọn cả những phương thức chưa từng tồn tại trước đó. Cần:

- Review những loại method mới.
- Thêm negative case cho các loại được loại trừ.
- Kiểm tra signature pattern trong runtime.
- Chạy lại một bộ regression cố định để phát hiện can thiệp mở rộng.

Đây là lý do không nên coi negative testing là một bài test viết một lần rồi quên.

## 18. Chiến lược kiểm thử theo ranh giới bảo mật

Một thiết kế có thể phân tách hai loại yêu cầu:

1. **Advice X không được áp vào operation Y**, vì nó sẽ gây tác động ngoài ý muốn.
2. **Chính sách bảo mật Z phải được thực thi trên mọi đường có thể tới sensitive effect**, kể cả khi đường đó không qua interception của advice khác.

Ví dụ, không muốn tracing aspect đọc thông tin nhạy cảm khi gọi secretFormatter(), nên negative test có kỳ vọng “tracing advice count = 0” tại formatter. Nhưng việc bảo vệ secretFormatter() khỏi caller không có quyền là một vấn đề khác. Không thể suy ra “không tracing” đồng nghĩa “không kiểm tra quyền”.

Để tránh sai lệch kiến trúc:

- Ánh xạ từng điều kiện bảo mật tới principal, action, resource và điểm cưỡng chế tin cậy.
- Kiểm thử mọi đường gọi tới effect nhạy cảm, kể cả đường ngoài proxy hoặc callback.
- Đối với điểm không được áp một aspect quan sát cụ thể, vẫn cho phép một lớp kiểm soát quyền hợp lệ khác chạy.
- Không dùng điểm cấm của một advice làm điểm mù bảo mật của toàn ứng dụng.

Nếu negative test phát hiện một advice authorization không chạy trên một đường phải được bảo vệ, kết quả phải được phân loại **security coverage failure**, không được ghi “excluded as expected”.

## 19. Các sai lầm phổ biến khi viết kiểm thử âm

**Sai lầm 1 — Chỉ viết test dương tính.** Pointcut có thể được nới rộng và bắt thêm health(), exporter hoặc dữ liệu nhạy cảm mà tất cả test dương vẫn pass. Bổ sung test cho từng nhóm điểm cấm.

**Sai lầm 2 — Chỉ kiểm tra không có log.** Logger có thể tắt/sampling/drop. Dùng probe trực tiếp đếm advice invocation, kết hợp assertions trên side effect.

**Sai lầm 3 — Không kiểm tra target thực sự chạy.** Một testcase không gọi đúng đường có thể cho advice count = 0 và pass giả. Assert target invocations/giá trị kết quả.

**Sai lầm 4 — Tắt toàn bộ AOP khi test.** Mọi negative case pass giả. Bắt buộc có positive control chạy trên cùng runtime.

**Sai lầm 5 — Gộp tất cả advice thành một biến intercepted.** Một aspect được phép, aspect khác bị cấm. Đếm riêng theo concern/join point.

**Sai lầm 6 — Không phân biệt call và execution.** Một event execution có thể bị hiểu nhầm là call advice; cần lưu loại điểm và nơi phát sinh.

**Sai lầm 7 — Khẳng định self-call luôn bỏ qua AOP.** Đúng với một số proxy, không đúng như một quy luật cho mọi weaving. Test phải dùng đúng cơ chế đang triển khai.

**Sai lầm 8 — Đánh đồng việc không có advice với không có tác dụng phụ.** Target có thể tạo effect hợp lệ, hoặc một advice khác tạo effect. Kỳ vọng phải cụ thể về advice bị cấm và loại side effect cấm.

**Sai lầm 9 — Không test exception path.** Advice sai có thể chỉ kích hoạt retry, rollback hay fallback khi target ném lỗi. Cần tiêm lỗi để kiểm tra các nhánh này.

**Sai lầm 10 — Test async bằng sleep ngắn.** Event đến sau assertion có thể làm pass giả. Chờ completion theo hợp đồng hoặc dùng scheduler điều khiển được.

**Sai lầm 11 — Coi pointcut mở rộng là vô hại nếu output giống nhau.** Instrumentation quá rộng vẫn có thể làm mất dữ liệu, lộ secret, tăng chi phí, giữ lock hoặc tạo recursion.

**Sai lầm 12 — Không cập nhật nhóm cấm khi refactor.** Một helper mới có thể bị wildcard match. Review và cập nhật regression suite mỗi khi thay đổi module/typing/entry points.

## 20. Bảng checklist trước khi phê duyệt aspect

| Câu hỏi | Điều kiện đạt |
| --- | --- |
| Pointcut có phạm vi rõ không? | Có danh sách required và forbidden theo từng concern |
| Mỗi negative case có kích hoạt join point? | Xác minh target hoặc call site chạy thật |
| Có positive control không? | Advice chạy ở điểm required trên cùng runtime |
| Có oracle trực tiếp không? | Advice count, join point identity, side effect được đo rõ |
| Có kiểm tra telemetry internals? | Không recursion; exporter/logger không bị aspect quan sát chặn |
| Có kiểm tra exception và retry? | Không lặp proceed ngoài policy; lỗi được bảo toàn |
| Có kiểm tra dữ liệu nhạy cảm? | Không capture/log trường bị cấm |
| Có kiểm tra tài nguyên/context? | Không transaction/span/context phát sinh hoặc rò ngoài scope |
| Có kiểm tra call/execution? | Loại join point và vị trí code chứa được phân biệt |
| Có kiểm tra self-call, raw target và callback? | Kỳ vọng dựa vào interception model thật |
| Có xét aspect cùng tồn tại? | Không advice bị cấm nào xuất hiện, dù advice khác được phép |
| Có kiểm tra mutation? | Bỏ exclusion/nới pointcut làm negative test fail |
| Có test trên build được weave thực không? | Runtime/config trong test có chứng cứ đại diện |
| Có đo kết quả async đúng thời điểm? | Không assert trước khi công việc liên quan hoàn tất |
| Có regression test khi thêm class? | Kiểm tra wildcard và nhóm loại trừ mới |

## 21. Bài tập tự kiểm tra

### Tình huống 1

Một aspect ghi log được thiết kế chỉ chạy quanh các phương thức nghiệp vụ. Test gọi health() trả về UP và không in dòng “advice”. Đã chứng minh health() bị loại khỏi pointcut chưa?

**Đáp án:** Chưa đủ. Log có thể bị tắt. Cần xác nhận health() đã chạy qua đúng đối tượng được instrument, probe advice không ghi event và có positive control chứng minh aspect vẫn hoạt động trên operation được chọn.

### Tình huống 2

Một bộ test âm dùng trực tiếp target thay vì proxy và quan sát advice count bằng 0. Nó kết luận rằng pointcut loại trừ method đúng. Sai ở đâu?

**Đáp án:** Nếu interception chỉ diễn ra tại proxy thì gọi raw target không thể chứng minh quy tắc loại trừ của proxy. Phải gọi qua proxy để kiểm tra exclusion, hoặc nếu mục tiêu là kiểm tra bypass bảo mật thì coi đường raw là một ca phủ định khác.

### Tình huống 3

Pointcut có hai loại join point: call và execution cho cùng một phương thức. Một phép thử ghi nhận hai event rồi cho rằng aspect chạy dư một lần. Nhận định ấy có chắc đúng?

**Đáp án:** Không. Một lượt gọi được instrument đầy đủ có thể tạo một call join point và một execution join point. Phải nêu rõ đơn vị đo mong muốn và loại advice nào được phép; nếu metric định đếm một operation thì thiết kế chọn cả hai có thể gây trùng.

### Tình huống 4

Một aspect retry được loại trừ khỏi sendEmail(), nhưng test chỉ chạy đường thành công. Có đủ phát hiện retry ngoài phạm vi không?

**Đáp án:** Không chắc. Khi không có exception, retry advice ngoài phạm vi vẫn có thể gọi proceed() đúng một lần, khiến test không thấy lặp. Cần tiêm lỗi retryable và đếm số invocation/effect hoặc đếm chính advice retry.

### Tình huống 5

Test âm cho thấy advice tracing không chạy trên secretFormatter(). Có thể kết luận bí mật được bảo vệ khỏi mọi đường truy cập không?

**Đáp án:** Không. Negative test chỉ chứng minh một aspect cụ thể không can thiệp tại điểm đó. Quyền truy cập và bảo vệ dữ liệu cần test riêng, ở ranh giới tin cậy.

### Tình huống 6

Sau khi xóa điều kiện NOT telemetryInternals trong pointcut, bộ test âm vẫn pass. Khả năng nào cần điều tra?

**Đáp án:** Test có thể không gọi đúng exporter, không đo trực tiếp advice, chưa bật instrumentation, hoặc predicate trong unit test khác expression thật. Mutation phải khiến test fail nếu rule được kiểm tra đúng.

### Tình huống 7

Một method tạo CompletableFuture trả handle ngay, advice bị cấm chỉ chạy khi completion callback sau vài giây. Test assert “không có event” ngay sau method return có đủ không?

**Đáp án:** Không. Phải chờ completion hoặc điều khiển scheduler để quan sát đúng vòng đời, rồi assert không có advice bị cấm trong toàn scope đã xác định.

### Tình huống 8

Một nhóm muốn loại trừ metric exporter khỏi timing advice, nhưng việc loại trừ khiến họ sợ mất thông tin về lỗi exporter. Có mâu thuẫn không?

**Đáp án:** Không. Có thể theo dõi exporter bằng một cơ chế riêng không tạo recursion, thay vì dùng chính timing advice mà exporter được gọi bên trong. Negative test cần tập trung chứng minh **advice bị cấm** không chạy ở exporter; observability của exporter vẫn có thể thực hiện ở ranh giới độc lập.

## 22. Kết luận

**Kiểm thử âm để phát hiện can thiệp ngoài phạm vi** là kiểm tra tính chính xác của ranh giới pointcut từ phía ngược lại: không chỉ “nơi cần advice thì có advice”, mà còn “nơi cấm advice thì thật sự không có advice”. Phải kích hoạt các đường bị loại trừ, quan sát trực tiếp lượt advice và tác dụng phụ, đồng thời có positive control chống việc test pass giả do instrumentation bị tắt.

Một bộ kiểm thử tốt bao gồm:

- Ma trận required/forbidden riêng cho từng aspect.
- Assertions cho join point thực, advice count, kết quả và side effect.
- Các trường hợp proxy/weaving, call/execution, lời gọi nội bộ, callback và exception.
- Mutation test cố tình mở rộng pointcut để xác minh oracle phát hiện sai lệch.
- Integration/regression test chạy trên build, classloader và cấu hình can thiệp thực tế.

Cuối cùng, việc một advice **không chạy đúng nơi bị loại** không được đánh đồng với việc một **đường tới tài nguyên nhạy cảm được bảo vệ**. Hai yêu cầu này phải được xác minh độc lập để AOP vừa không gây can thiệp thừa vừa không tạo lỗ hổng thiếu bảo vệ.
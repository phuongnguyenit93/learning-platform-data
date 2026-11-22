# Kiểm thử hồi quy khi cấu trúc mã thay đổi trong AOP

## 1. Vì sao refactor có thể làm aspect hỏng mà nghiệp vụ vẫn chạy đúng?

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, **AOP**), một **aspect** áp dụng lời khuyên (**advice**) tại các **join point** được một **pointcut** lựa chọn. Khi cấu trúc mã thay đổi — chuyển lớp sang package khác, đổi tên phương thức, thêm overload, tách helper, thay interface, thay cơ chế tạo đối tượng hoặc chuyển xử lý sang tác vụ bất đồng bộ — tập join point thực tế có thể thay đổi dù chức năng nghiệp vụ nhìn từ ngoài gần như giữ nguyên.

Ví dụ trước khi refactor, một pointcut chọn mọi lần thực thi phương thức public của kiểu OrderService. Sau khi tách logic đặt hàng sang OrderCoordinator và một helper khác, advice có thể:

1. **Không chạy ở chỗ cần chạy:** operation mới bị bỏ khỏi pointcut.
2. **Chạy thêm ở chỗ không được phép:** wildcard chọn cả helper, exporter hoặc phương thức mới, làm ghi log hai lần hoặc mở transaction thừa.
3. **Đổi số lần chạy:** một lời gọi nghiệp vụ trở thành hai lời gọi con cùng match pointcut.
4. **Đổi thứ tự thực thi:** thay mô hình ủy quyền hoặc precedence làm retry, transaction và recorder lồng nhau khác trước.
5. **Đổi thời điểm kết thúc:** trước đây method chạy đồng bộ, sau refactor method trả Future nên advice ghi thành công quá sớm.
6. **Bỏ sót đường gọi mới:** một entry point, callback hoặc đối tượng tạo trực tiếp không đi qua cơ chế interception.
7. **Làm đổi ngoại lệ, tác dụng phụ hoặc context:** advice vô tình retry thao tác không idempotent, nuốt lỗi hoặc giữ dữ liệu của lời gọi trước.

**Kiểm thử hồi quy aspect** nhằm phát hiện những thay đổi ngoài ý định này bằng cách xác nhận *hợp đồng quan sát và thực thi* vẫn đúng sau refactor. Nó khác với việc chỉ kiểm tra rằng phương thức nghiệp vụ vẫn trả giá trị mong đợi.

Bài này tập trung vào nguyên tắc AOP cơ bản và nâng cao, độc lập với một hệ sinh thái ứng dụng cụ thể. Ví dụ Java 17+ mô phỏng interception qua Java Dynamic Proxy; khi dùng kỹ thuật weaving khác cần chạy thêm kiểm thử tích hợp trên công cụ thực tế.

## 2. Hợp đồng của aspect phải được mô tả trước khi sửa mã

Không thể làm regression testing tốt nếu kỳ vọng chỉ là “có vẻ vẫn chạy”. Trước khi refactor, hãy ghi lại **hợp đồng AOP** ở các cấp sau:

| Cấp | Câu hỏi | Ví dụ tiêu chí |
| --- | --- | --- |
| Business operation | Một thao tác logic là gì? | Một yêu cầu đặt hàng được xem là một operation |
| Join point được chọn | Method-call, method-execution hay vị trí khác nào? | Thực thi entry point của nghiệp vụ |
| Advice bắt buộc | Tại điểm nào advice phải kích hoạt? | Tracing quanh submitOrder |
| Advice bị cấm | Tại điểm nào advice tuyệt đối không được kích hoạt? | Không instrument chính exporter |
| Thứ tự | Các advice bao nhau như thế nào? | RecordFinal(Retry(Transaction(operation))) |
| Số lần | proceed() và advice chạy bao nhiêu lần? | Một final record cho mỗi operation |
| Kết quả/lỗi | Advice được phép biến đổi return/throw không? | Observer không che ngoại lệ gốc |
| Ngữ cảnh | Correlation và principal sống trong scope nào? | Khôi phục context sau khi kết thúc |
| Tác dụng phụ | Effect nào có thể lặp hoặc bị rollback? | Gửi thanh toán không bị retry trùng |
| Bất đồng bộ | Khi nào operation hoàn tất về mặt logic? | Completion của task, không chỉ return handle |

Mỗi refactor nên xác định trước điều gì **được phép thay đổi**. Chẳng hạn chuyển method sang một lớp triển khai khác có thể làm tên class thay đổi, nhưng mục tiêu “một tracing event cho mỗi business operation” vẫn giữ nguyên. Khi đó test không nên đóng băng tên của lớp cũ nếu tên lớp không phải một phần hợp đồng, nhưng vẫn phải giữ số event và đường đi bắt buộc.

Ngược lại, nếu chuyển một method sang lớp khác cũng chủ đích thay đổi ranh giới giao dịch hoặc đơn vị ghi log, hãy cập nhật hợp đồng bằng một quyết định thiết kế được review, không im lặng cập nhật expected output chỉ để test xanh.

## 3. Hai loại hồi quy: mất bao phủ và can thiệp thừa

Gọi tập join point phải được aspect X can thiệp là **R**, tập không được aspect X can thiệp là **F**, và tập điểm mà X thực sự chạy trong bài test là **A**.

~~~text
Phải có:         R ⊆ A
Không được có:   F ∩ A = ∅
~~~

Đây là hai điều kiện độc lập:

- **Positive regression test:** lời gọi mới hoặc đã đổi chỗ vẫn đi qua advice bắt buộc.
- **Negative regression test:** một helper, logger hoặc API mới không bị pointcut vô tình chọn thêm.

Một test dương có thể tiếp tục pass dù pointcut được mở rộng bừa bãi. Một test âm có thể pass giả nếu AOP bị vô hiệu hoàn toàn. Vì vậy, mỗi test suite phải có **cả kiểm soát dương và kiểm soát âm** trên cùng build/runtime.

Ví dụ bảng hợp đồng cho advice OperationTrace:

| Phần chương trình | Trước refactor | Sau refactor mong muốn | Kỳ vọng |
| --- | --- | --- | --- |
| Entry point submit | OrderService.submit | OrderFacade.submit | Một lần advice tại ranh giới operation |
| Hàm trợ giúp tính phí | OrderService.calculate | PricingEngine.calculate | Không phát thêm final-operation advice |
| Exporter ghi trace | Telemetry.publish | TelemetryWriter.publish | Không bị chính OperationTrace instrument |
| Xử lý hoàn tất tác vụ | Đồng bộ trong submit | Callback sau khi submit trả Future | Final outcome phải theo completion nếu hợp đồng yêu cầu |
| Entry point batch mới | Chưa tồn tại | BatchHandler.submit | Vẫn kiểm tra quyền trước effect nếu cùng loại thao tác nhạy cảm |

Hợp đồng phải nói rõ cấp **method execution** hay **business operation**: một operation có thể bao gồm nhiều method execution, nhất là sau khi chia nhỏ thành các thành phần.

## 4. Các thay đổi cấu trúc dễ gây hồi quy AOP

### 4.1. Đổi tên package hoặc chuyển class

Một pointcut chọn theo tên package/type có thể không còn match khi chuyển implementation sang module khác:

~~~text
Trước:
  app.orders.OrderService.submit()

Sau:
  app.checkout.OrderCoordinator.submit()
~~~

Nếu expression chỉ bao phủ app.orders, advice sẽ biến mất ở implementation mới. Mặt khác, việc dời một utility vào package đang bị wildcard chọn có thể khiến advice chạy ở utility đó dù trước đây không chạy.

**Regression cần kiểm tra:** entry point mới vẫn được bảo vệ, class đã chuyển khỏi scope không còn nhận advice thừa, và các điểm bị loại trừ vẫn không match.

### 4.2. Đổi tên method, chữ ký hoặc overload

Ví dụ:

~~~text
submit(Order)
submit(Order, Options)
submit(String)
~~~

Một biểu thức dựa trên tên và danh sách tham số có thể match một overload nhưng bỏ sót overload mới. Refactor đổi return type hoặc modifier cũng có thể làm signature pattern không còn đúng.

**Regression cần kiểm tra:** từng overload có kỳ vọng riêng; không chỉ gọi một overload bất kỳ rồi kết luận toàn bộ operation được bao phủ.

### 4.3. Tách phương thức thành helper

Trước refactor, một method làm toàn bộ công việc. Sau refactor, nó ủy quyền:

~~~text
OrderFacade.submit()
    -> Validation.check()
    -> Pricing.calculate()
    -> Storage.save()
~~~

Nếu pointcut chọn wildcard mọi method dưới một package, bốn method có thể đều bị aspect nhìn thấy. Với recorder “một event cuối cho một operation”, đây là **đếm trùng**. Với transaction, scope giao dịch có thể bị tạo nhiều lần hoặc tương tác với transaction có sẵn. Với retry, hiệu ứng còn đáng ngại hơn: proceed() có thể chạy lặp trên một helper vốn không an toàn để lặp.

**Regression cần kiểm tra:** số lượt advice và loại advice tại từng ranh giới, không chỉ tổng số dòng log.

### 4.4. Trộn hoặc gộp method

Nếu nhiều operation riêng được gộp thành một method tổng quát với tham số mode, một pointcut trước đó phân biệt nghiệp vụ qua tên method có thể mất khả năng chọn chính xác.

**Regression cần kiểm tra:** mỗi loại operation vẫn có đúng quyền, tracing và outcome; không gán cùng transaction/retry policy cho các mode có tác dụng phụ khác nhau.

### 4.5. Chuyển interface hoặc thay đường tạo đối tượng

Một proxy dựa trên interface có thể nhìn thấy lời gọi qua interface nhưng không intercept lời gọi trực tiếp tới target. Sau refactor, nếu code lưu raw target hoặc tự gọi phương thức trên this, đường gọi có thể không đi qua interception tương tự trước.

Một cơ chế weaving tại method-execution có thể khác proxy ở chính tình huống self-invocation. Không được sao chép kỳ vọng của một cơ chế sang mọi dạng AOP.

**Regression cần kiểm tra:** receiver thực sự là proxy hay target, class nào được weave, và những entry point mới nào tiếp cận được sensitive effect.

### 4.6. Thêm inheritance, generic hoặc bridge method

Khi đổi từ một lớp cụ thể sang interface/generic base class, method có thể bị override hoặc compiler tạo bridge method. Một pointcut quá rộng có thể tạo thêm event; một type pattern quá hẹp có thể bỏ implementation mới.

**Regression cần kiểm tra:** signature ở các lớp runtime thật, số event trên một lần gọi và thứ tự advice; không suy đoán chỉ theo tên lớp/interface.

### 4.7. Chuyển từ đồng bộ sang bất đồng bộ

Một method trước đây trả kết quả cuối, sau refactor trả CompletionStage/Future hoặc Publisher. Nếu advice chỉ quan sát return đồng bộ, nó có thể báo success trước khi task fail.

**Regression cần kiểm tra:** định nghĩa completion của operation, thời gian đóng transaction/resource, propagation context và outcome cuối khi task async lỗi hoặc hủy.

### 4.8. Thêm callback, job hoặc event consumer

Cùng hành vi nghiệp vụ có thể được kích hoạt từ nhiều điểm vào. Một advice ở controller không đảm bảo job/callback mới cũng bị kiểm soát.

**Regression cần kiểm tra:** mọi đường tới effect nhạy cảm, kể cả entry point mới; dùng principal đáng tin cậy và kiểm tra quyền tại ranh giới thực sự có thể ngăn effect.

## 5. Những phép đo có giá trị hơn việc chỉ assert output

Một test chỉ xác nhận submit() trả OK chưa chứng minh AOP đúng. Cần thêm dấu vết:

| Quan sát | Phát hiện vấn đề gì? |
| --- | --- |
| Danh tính join point và loại call/execution | Chọn nhầm vị trí can thiệp |
| Advice enter/return/throw | Mất bao phủ hoặc advice chạy ngoài phạm vi |
| Số lần proceed() | Retry hoặc around advice gọi nhiều/ít lần |
| Thứ tự event | Đổi thứ tự transaction, retry và recorder |
| Return value và exception | Aspect nuốt/bọc lỗi hoặc thay giá trị trái hợp đồng |
| Transaction begin/commit/rollback | Scope giao dịch bị tách/gộp sau refactor |
| Số external effects | Thao tác ngoài transaction bị nhân đôi |
| Scope correlation/principal | Ngữ cảnh rò giữa lời gọi hoặc mất qua thread |
| Async terminal signal | Ghi outcome trước khi công việc thực sự hoàn tất |
| Latency và overhead theo ranh giới | Instrumentation rộng hơn gây suy giảm |
| Trạng thái resource sau khi rời scope | Lock/connection/transaction bị rò |

**Oracle của regression** phải định nghĩa cho từng phép đo:

~~~text
given một yêu cầu submit hợp lệ
when chạy qua đường gọi mới sau refactor
then:
    đúng một business operation được hoàn tất
    advice tracing operation chạy đúng một lần
    authorization kiểm tra trước effect nhạy cảm
    helper và exporter không bị final recorder can thiệp
    kết quả/ngoại lệ giữ đúng hợp đồng
    không có external effect thừa
    context và tài nguyên được khôi phục
~~~

Trong các phép thử bất đồng bộ, phải chờ hoặc điều khiển được terminal event. Không assert “không có thêm event” ngay sau khi nhận future nếu callback vẫn chưa chạy.

## 6. Thiết kế test theo hợp đồng, không đóng băng chi tiết refactor hợp lệ

Giả sử một nghiệp vụ trước đây in các bước:

~~~text
OrderService.validate
OrderService.calculate
OrderService.save
~~~

Sau refactor được gộp và đổi lớp:

~~~text
CheckoutEngine.process
~~~

Nếu metric đúng cần là **một operation completed**, test bám cứng ba method cũ sẽ fail dù hành vi AOP tổng thể có thể đúng. Hãy tách:

- **Contract-level assertions:** số event nghiệp vụ, thứ tự chính sách, dữ liệu an toàn, outcome và scope.
- **Implementation-level assertions:** chữ ký, class/package cụ thể chỉ khi chúng thực sự là một phần pointcut cần kiểm tra.

Với pointcut dùng tên package cụ thể, vẫn cần kiểm tra ở tầng implementation vì nó là cấu hình có thể hỏng sau khi đổi cấu trúc. Nhưng expected baseline của hợp đồng nghiệp vụ nên được quản lý độc lập.

Một chiến lược tốt là tạo **bản đồ expectation**:

~~~text
OperationContract:
  name: submit-order
  requiredAdvices:
    - authorization-before-sensitive-effect
    - tracing-around-operation
  forbiddenAdvices:
    - retry-on-non-idempotent-payment
    - log-raw-secret
  cardinality:
    finalOutcomeEvents: 1
  result:
    businessStatus: explicit
  asyncCompletion:
    onlyIfOperationIsAsync: terminal-signal
~~~

Đây là YAML minh họa cho ý tưởng, không phải cấu hình mặc định của một công cụ AOP. Nó cho thấy **cần mô tả điều gì**, không áp đặt schema cụ thể.

## 7. Ví dụ Java 17+ có thể chạy: kiểm tra hồi quy trước và sau khi tách lớp

Ví dụ sau dùng **Java Dynamic Proxy** để minh họa việc chọn method bằng một metadata hợp đồng ổn định, thay vì dựa vào tên lớp triển khai.

Bối cảnh:

- Interface Api định nghĩa các operation và đánh dấu những operation được quan sát bằng annotation Observed.
- LegacyApi thực thi nghiệp vụ trực tiếp.
- RefactoredApi chuyển logic sang Engine, nhưng giữ nguyên hợp đồng công khai.
- Interceptor bao quanh các lời gọi qua proxy, ghi advice.before, advice.return, advice.throw.
- Bộ test xác minh cùng kết quả, thứ tự event và phương thức health() vẫn ngoài phạm vi sau khi refactor.
- Hai mutation được tiêm riêng: pointcut quá hẹp bỏ sót cancel() và pointcut quá rộng vô tình chọn health(). Bộ test phải phát hiện được cả hai.

Đây là phép mô phỏng nguyên lý của AOP, **không phải** một cơ chế bytecode weaving. Khi dùng AOP thật cần kiểm tra runtime pointcut và phạm vi can thiệp tương ứng.

Tạo tệp **AspectRefactorRegressionDemo.java**:

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
import java.util.function.Function;
import java.util.function.Predicate;

public final class AspectRefactorRegressionDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Observed {}

    interface Api {
        @Observed String save(String id);
        @Observed String cancel(String id);
        String health();
    }

    static final class LegacyApi implements Api {
        private final List<String> events;

        LegacyApi(List<String> events) {
            this.events = events;
        }

        public String save(String id) {
            events.add("business.save " + id);
            if (id.equals("bad")) {
                throw new IllegalArgumentException("bad id");
            }
            return "saved-" + id;
        }

        public String cancel(String id) {
            events.add("business.cancel " + id);
            return "cancelled-" + id;
        }

        public String health() {
            events.add("business.health");
            return "UP";
        }
    }

    // Sau refactor, logic được dời từ lớp triển khai sang helper.
    static final class Engine {
        private final List<String> events;

        Engine(List<String> events) {
            this.events = events;
        }

        String save(String id) {
            events.add("business.save " + id);
            if (id.equals("bad")) {
                throw new IllegalArgumentException("bad id");
            }
            return "saved-" + id;
        }

        String cancel(String id) {
            events.add("business.cancel " + id);
            return "cancelled-" + id;
        }

        String health() {
            events.add("business.health");
            return "UP";
        }
    }

    static final class RefactoredApi implements Api {
        private final Engine engine;

        RefactoredApi(List<String> events) {
            this.engine = new Engine(events);
        }

        public String save(String id) {
            return engine.save(id);
        }

        public String cancel(String id) {
            return engine.cancel(id);
        }

        public String health() {
            return engine.health();
        }
    }

    static Object invokeTarget(
            Api target, Method method, Object[] args) throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static Api instrument(
            Api target,
            List<String> events,
            Predicate<Method> selected) {
        return (Api) Proxy.newProxyInstance(
                Api.class.getClassLoader(),
                new Class<?>[]{Api.class},
                (proxy, method, args) -> {
                    if (!selected.test(method)) {
                        return invokeTarget(target, method, args);
                    }

                    String name = method.getName();
                    events.add("advice.before " + name);
                    try {
                        Object result = invokeTarget(target, method, args);
                        events.add("advice.return " + name);
                        return result;
                    } catch (Throwable error) {
                        events.add("advice.throw " + name);
                        throw error;
                    }
                });
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void expectEvents(List<String> actual, String... expected) {
        List<String> wanted = List.of(expected);
        if (!actual.equals(wanted)) {
            throw new AssertionError(
                    "expected=" + wanted + "; actual=" + actual);
        }
    }

    static void verifyContract(
            String label,
            Function<List<String>, Api> factory) {
        List<String> events = new ArrayList<>();
        Api raw = factory.apply(events);
        Api guarded = instrument(raw, events,
                method -> method.isAnnotationPresent(Observed.class));

        require("saved-A".equals(guarded.save("A")), "save result");
        require("cancelled-B".equals(guarded.cancel("B")),
                "cancel result");
        require("UP".equals(guarded.health()), "health result");

        expectEvents(events,
                "advice.before save",
                "business.save A",
                "advice.return save",
                "advice.before cancel",
                "business.cancel B",
                "advice.return cancel",
                "business.health");
        events.clear();

        try {
            guarded.save("bad");
            throw new AssertionError("expected IllegalArgumentException");
        } catch (IllegalArgumentException failure) {
            require("bad id".equals(failure.getMessage()),
                    "error identity/message");
        }

        expectEvents(events,
                "advice.before save",
                "business.save bad",
                "advice.throw save");

        System.out.println("PASS: " + label);
    }

    static void verifyMutations() {
        List<String> events = new ArrayList<>();
        Api raw = new RefactoredApi(events);

        // Lỗi quá hẹp: chỉ chọn save, bỏ mất cancel.
        Api tooNarrow = instrument(raw, events,
                method -> method.getName().equals("save"));
        tooNarrow.cancel("C");
        boolean missingDetected = false;
        try {
            expectEvents(events,
                    "advice.before cancel",
                    "business.cancel C",
                    "advice.return cancel");
        } catch (AssertionError expected) {
            missingDetected = true;
        }
        require(missingDetected, "must detect missing advice");
        System.out.println("PASS: missing coverage detected");

        events.clear();

        // Lỗi quá rộng: health không được chọn nhưng vẫn bị can thiệp.
        Api tooBroad = instrument(raw, events, method -> true);
        tooBroad.health();
        boolean extraDetected = false;
        try {
            expectEvents(events, "business.health");
        } catch (AssertionError expected) {
            extraDetected = true;
        }
        require(extraDetected, "must detect overbroad pointcut");
        System.out.println("PASS: overbroad selection detected");
    }

    public static void main(String[] args) {
        verifyContract("legacy implementation", LegacyApi::new);
        verifyContract("moved implementation", RefactoredApi::new);
        verifyMutations();
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac AspectRefactorRegressionDemo.java
java AspectRefactorRegressionDemo
~~~

Stdout:

~~~text
PASS: legacy implementation
PASS: moved implementation
PASS: missing coverage detected
PASS: overbroad selection detected
~~~

### Vì sao chương trình này đáng dùng để học regression?

**Hai implementation khác nhau, một hợp đồng:** LegacyApi và RefactoredApi tạo cùng return value/exception và chuỗi event ở ranh giới Api. Sau khi logic được dời vào Engine, test vẫn bảo toàn các điều kiện quan trọng của aspect.

**Chính sách gắn ở ranh giới interface:** Dynamic Proxy nhận một Method của interface Api, nên annotation Observed đặt ở interface được đọc bởi selected predicate. Không nên suy ra rằng annotation trên interface luôn tự được kế thừa vào mọi method implementation của mọi cơ chế weaving; với cơ chế khác, cần kiểm tra khả năng match annotation trên method khai báo/implement thực tế.

**Exception được quan sát và truyền ra:** invokeTarget bỏ lớp InvocationTargetException do reflection tạo, nên người gọi tiếp tục nhận IllegalArgumentException từ nghiệp vụ theo hợp đồng. Advice ghi advice.throw nhưng không nuốt lỗi.

**Thử nghiệm mutation có ý nghĩa:** quá hẹp bỏ mất advice trên cancel; quá rộng áp cả vào health. Regression suite chỉ được xem là có giá trị nếu nhận ra hai loại sai lệch đó.

**Không áp dụng proxy cho method gọi nội bộ:** ví dụ chỉ gọi qua Api proxy ở test. Nếu Engine gọi một phương thức nội bộ có yêu cầu bảo vệ riêng, phải kiểm thử thêm đường gọi thật. Cơ chế proxy theo interface không tự biến các lời gọi bên trong Engine thành join point trên proxy.

**Không đánh đồng với security:** dù advice về observability có thể đặt ở proxy, một bất biến bảo mật quan trọng phải được cưỡng chế ở ranh giới đáng tin cậy. Một caller lấy raw target có thể bỏ proxy; với chính sách authorization, đó có thể là security coverage failure.

## 8. Regression theo loại pointcut: tránh chuyển refactor thành mất match

Các hình thức pointcut cần kiểm thử theo ngữ nghĩa riêng:

### 8.1. Method execution

Một execution pointcut chọn thân phương thức đích. Sau khi dời logic sang lớp khác, cần xác định **điểm thực thi nào** nay đại diện đúng business operation. Nếu pointcut chọn theo tên kiểu/phương thức cũ, advice có thể không còn chạy.

Nếu giữ method façade mỏng nhưng đẩy toàn bộ công việc sang helper, execution advice tại façade có thể vẫn chạy **đúng một lần**; điều này có thể đáp ứng hợp đồng “quan sát operation tại API boundary”. Nhưng nếu mục tiêu là đo execution time của phần xử lý thực tế, façade chỉ trả future hoặc delegate có thể làm giá trị đo trở nên khác.

### 8.2. Method call

Một call pointcut chọn **vị trí phát sinh lời gọi**. Di chuyển câu lệnh gọi sang một helper trong package khác có thể làm điều kiện theo vùng mã chứa call site không còn match.

Ví dụ:

~~~text
Trước: Client.submit() gọi RemoteApi.send()
Sau:   Client.submit() gọi NetworkHelper.dispatch()
       NetworkHelper.dispatch() gọi RemoteApi.send()
~~~

Nếu pointcut chọn call(RemoteApi.send) **chỉ tại mã Client**, call site mới ở NetworkHelper có thể không được can thiệp. Regression cần bao phủ đường caller mới theo mục đích kiến trúc, không chỉ method đích.

### 8.3. Vùng mã chứa join point

Một điều kiện lexical theo type/package có thể bị thay đổi khi dời code. Nếu aspect chỉ dành cho mã trong một tầng, việc move class sang tầng khác có thể chủ ý khiến advice không áp; nếu không chủ ý, đó là lỗi.

Hãy ghi rõ “được phép theo kiểu **vị trí mã hiện tại**” hay “được phép theo **vai trò nghiệp vụ**”. Hai cách định nghĩa dẫn đến cách update pointcut khác nhau sau refactor.

### 8.4. Annotation-based selection

Metadata có thể ổn định khi implementation đổi lớp, như ví dụ Java trên. Nhưng cũng có các rủi ro:

- Annotation bị mất khi đổi method hoặc tách interface.
- Annotation đặt ở interface nhưng cơ chế instrument đọc trực tiếp method triển khai và không thấy nó theo cùng cách.
- Một annotation được copy vào helper ngoài dự kiến, khiến advice chạy hai nơi.
- Retention hoặc target của annotation không phù hợp cho runtime selection.
- Một overload mới không được đánh dấu.

Kiểm thử contract và runtime điểm cắt phải phân biệt được các trường hợp này.

### 8.5. Type hierarchy, inheritance và bridge method

Sau refactor về generic interface hoặc subclass, compiler có thể sinh bridge method; dynamic dispatch có thể chuyển từ method khai báo ở base sang override. Một pointcut có thể match nhiều hoặc ít điểm hơn trước tùy cơ chế.

Cần test trên lớp thực tế, không chỉ mock theo tên method. Đo đúng số event nghiệp vụ để tránh việc một lời gọi bị quan sát hai lần do hai join point mà không có chủ ý.

## 9. Regression đối với thứ tự advice và control flow

Một refactor có thể không đổi tập method match nhưng đổi **thứ tự bao quanh advice**. Ví dụ một cơ chế registration thay đổi priority hoặc classpath load order.

Ký pháp:

~~~text
RecordFinal(
  Retry(
    Transaction(
      operation
    )
  )
)
~~~

trong đó Retry bao transaction, mỗi attempt có thể có ranh giới transaction độc lập theo chính sách thực tế. So sánh:

~~~text
Transaction(
  Retry(
    operation
  )
)
~~~

attempt có thể dùng chung transaction, không an toàn khi lỗi đầu khiến transaction bị rollback-only.

Regression nên ghi event theo thứ tự:

~~~text
retry attempt=1
transaction begin T1
business failure
transaction rollback T1
retry attempt=2
transaction begin T2
business return
transaction commit T2
operation final success
~~~

Những event trên là ví dụ cho **mô hình thử lại toàn giao dịch**, không phải trình tự bắt buộc của mọi AOP. Test thật cần khớp transaction manager và chính sách retry.

Nếu recorder được dời vào bên trong transaction, nó có thể ghi success **trước commit**. Nếu recorder ở ngoài retry bị chuyển vào mỗi attempt, một operation có thể có nhiều final records. Các thay đổi này khó phát hiện nếu test chỉ nhìn vào return value.

Với fallback, một advice ở ngoài retry có thể chỉ trả fallback sau khi hết attempts; nếu nằm bên trong, nó có thể che lỗi ngay và khiến retry không chạy. Test nên assert cả số attempt, loại lỗi và outcome cuối.

## 10. Regression kiểm soát quyền khi đường gọi thay đổi

Refactor có thể tạo đường vào mới tới một thao tác nhạy cảm:

~~~text
UI request --> proxy --> resource operation
Batch job -----------------------> raw resource operation
~~~

Nếu authorization chỉ nằm trên proxy, job có thể bỏ qua kiểm tra quyền. Không được coi hiện tượng này là test âm “đúng vì không có advice”; đó là **lỗi thiếu bảo vệ** nếu resource operation bắt buộc được kiểm soát.

Các test bảo mật sau refactor nên:

1. Xác định principal, action, resource và trust boundary.
2. Liệt kê mọi entry point mới và cũ có thể tạo sensitive effect.
3. Gọi từng đường với principal có và không có quyền.
4. Xác nhận **không có tác dụng phụ nhạy cảm xảy ra với principal không được phép**.
5. Kiểm tra chính sách fail-closed khi thiếu dữ liệu danh tính hoặc quyền.
6. Không tin rằng tên annotation/aspect chứng minh mọi đường gọi được instrument.

Nếu chuyển từ xử lý đồng bộ sang job, principal có thể là danh tính hệ thống thay vì người dùng tương tác. Phải định nghĩa quyền theo vai trò tác vụ, không tự cho rằng mọi background job đều có toàn quyền.

## 11. Regression khi chuyển sang API bất đồng bộ

Một thay đổi API như:

~~~text
Trước:
    Receipt submit(Order)          // trả kết quả cuối

Sau:
    CompletionStage<Receipt> submit(Order)
                                   // trả handle
~~~

có thể khiến advice theo before/after-returning quan sát sai **mốc hoàn tất**. Nếu transaction advice mở transaction ở method submit rồi đóng khi trả future, worker tiếp tục xử lý có thể chạy ngoài transaction dự kiến.

Cần xác định riêng:

- **Invocation start/return:** khi method được gọi và khi nó trả handle.
- **Logical completion:** future hoàn tất thành công, lỗi hoặc bị hủy.
- **Transaction ownership:** nơi resource được tạo/dùng/đóng, thread nào tham gia.
- **Retry boundary:** gọi lại function tạo future hay chỉ chờ lại future cũ?
- **Context propagation:** correlation/principal được capture/bind/restore đúng thời điểm.
- **Timeout/cancellation:** caller hết thời gian chờ không có nghĩa task hoặc side effect đã dừng.

Test hồi quy cần tiêm các kết quả: hoàn tất bình thường, completion exceptional, cancellation, timeout, callback trên thread khác và kết quả commit chưa rõ. Nếu mỗi method return thành công nhưng task lỗi sau đó, recorder final phải nhìn thấy thất bại **theo completion contract**, không báo thành công quá sớm.

Với publisher/reactive API, method tạo publisher có thể kết thúc trước subscription; nhiều subscriptions có thể tạo nhiều executions. Cần đo ở đúng lifecycle thay vì sao chép test cho method đồng bộ.

## 12. Regression đối với lỗi và tác dụng phụ

Một aspect có thể thay đổi hành vi dù refactor không làm đổi return cuối:

**Retry và idempotency.** Nếu pointcut vô tình mở rộng để bao một lệnh gửi email/thanh toán, một lỗi tạm thời có thể tạo effect lặp. Test đếm số lần effect dưới fault injection; không chỉ kiểm tra rằng retry cuối cùng thành công.

**Transaction và commit.** Một method có thể return bình thường trước khi commit thất bại. Test ghi committed-success phải đặt observer sau ranh giới commit thực và xét trạng thái commit không chắc chắn.

**Logging/metric best effort.** Nếu recorder bị ném lỗi trong một advice nằm dưới retry, hệ thống có thể gọi lại nghiệp vụ đã commit. Test tiêm lỗi vào exporter rồi assert số business invocations không tăng ngoài hợp đồng.

**Exception mapping.** Advice có thể bọc, nuốt hoặc thay lỗi gốc. Test xác nhận caller vẫn phân biệt lỗi nghiệp vụ, lỗi retryable, timeout và cancellation theo contract.

**Side effect ngoài transaction.** Rollback cơ sở dữ liệu không tự thu hồi email, HTTP request hoặc message đã gửi. Nếu refactor chuyển effect vào vùng retry, cần thiết kế idempotency/outbox/deduplication/compensation phù hợp.

**Context/thread-local state.** Một scope kết thúc mà không restore có thể làm request sau mang correlation ID của request trước. Test worker xử lý liên tiếp hai operation và đối chiếu context trước/sau.

Hãy đưa các failure point quan trọng vào bài kiểm thử, không chỉ happy path.

## 13. Xây test matrix cho một lần refactor thực tế

Ví dụ tình huống thay đổi cấu trúc:

- Chuyển OrderService sang CheckoutCoordinator.
- Tách PricingEngine ra một package khác.
- Thêm overload submit(Order, Flags).
- Thay lời gọi trực tiếp remote client bằng NetworkHelper.
- Chuyển một bước hậu xử lý sang executor.

Bảng regression:

| Hạng mục thay đổi | Positive test | Negative test | Thứ phải đo |
| --- | --- | --- | --- |
| Chuyển class nghiệp vụ | Advice chính vẫn chạy | Không chạy trên class cũ/utility nếu không còn được chọn | Join point identity, advice count |
| Tách helper | Operation vẫn có một final record | Helper không phát final record thừa | Event count, operation scope |
| Thêm overload | Overload được phê duyệt vẫn được kiểm soát | Overload không thuộc policy không bị áp nhầm | Signature, return/throw |
| Dời call site | Call advice được cập nhật nếu cần | Call site ở package không được phép không bị chọn | Call/execution distinction |
| Đổi interface/proxy | Đường hợp lệ đi qua interception | Raw target không vô tình trở thành đường bypass security | Receiver, target state |
| Thêm worker async | Logical completion được quan sát | Không ghi success ngay khi trả handle | Completion, context, resource |
| Đổi precedence | Transaction/retry/record đúng thứ tự | Không retry ngoài policy | Event order, transaction outcomes |
| Thêm exporter | Trace pipeline hoạt động | Exporter không bị cùng tracer intercept | Recursion, event count |
| Đổi kết cấu exception | Lỗi gốc bảo toàn | Observer không che lỗi | Exception class/cause |
| Thêm cache | Cache hit/miss có chính sách rõ | Cache không bỏ qua authorization | Resource visibility, guard events |

Sau refactor, chạy cả test dương, âm và integration test. Nếu pointcut dựa vào wildcard của package, các test phải đủ đại diện cho **những kiểu mới có thể vô tình bị match**.

## 14. Regression bằng cặp baseline và phiên bản đã sửa

Một chiến thuật hiệu quả:

1. **Chụp baseline có ý nghĩa:** tập join point mong đợi, event order, counts, outcome, resource state trên phiên bản trước.
2. **Tách stable contract:** phần nào bắt buộc giữ nguyên sau refactor, phần nào được phép đổi.
3. **Chạy cùng bộ scenario** trên implementation cũ và mới nếu có thể.
4. **So sánh những thuộc tính ổn định:** không cần snapshot từng tên helper, nhưng phải giữ chính sách và ranh giới operation.
5. **Đánh giá chênh lệch có chủ ý:** thay đổi event name hoặc join point do thiết kế mới phải được review và thêm test.
6. **Đưa thành regression suite chạy định kỳ:** không chỉ kiểm tra một lần vào ngày refactor.

Không nhất thiết cần giữ cả hai implementation trong production. Có thể duy trì một fake hoặc một bộ test contract độc lập để kiểm tra implementation mới. Với điểm cắt phụ thuộc cấu trúc thực, vẫn cần integration test trên artifact mới.

### Snapshot testing có giới hạn

Snapshot một danh sách join point/event có thể hữu ích để phát hiện thay đổi bất ngờ, nhưng không nên tự động chấp nhận snapshot mới khi test fail. Cần xem:

- Event mới có phải instrument thừa không?
- Event biến mất có phải mất authorization/tracing không?
- Thứ tự thay đổi có ảnh hưởng tới commit/retry không?
- Tên helper thay đổi có phải biến động hợp lệ, còn business contract vẫn nguyên?
- Thay đổi classloader/build có khiến runtime không còn weave?

Snapshot là tín hiệu để review, không phải bằng chứng tự động rằng một thay đổi đúng.

## 15. Mutation testing để chứng minh regression suite nhạy với lỗi

Một bộ test xanh chưa đủ nếu nó không thể phát hiện thay đổi pointcut. Hãy chủ động tạo các mutation **trong môi trường test**:

- Thu hẹp pointcut làm thiếu một method bắt buộc.
- Nới rộng pointcut để bắt helper hoặc exporter.
- Bỏ điều kiện exclusion cho logging internals.
- Đổi thứ tự advice để recorder nằm trước commit.
- Thay một around advice gọi proceed() một lần thành hai lần.
- Xóa logic khôi phục context trong finally.
- Thay async completion observer bằng after-returning observer.
- Đổi matcher theo interface thành matcher quá phụ thuộc tên lớp triển khai.

Test phù hợp phải fail. Nếu vẫn pass, có thể nó chỉ kiểm tra output nghiệp vụ, không đo advice, hoặc chỉ thử một đường gọi không đại diện.

Ví dụ Java trong bài dùng hai mutation đối nghịch: **tooNarrow** bỏ sót cancel và **tooBroad** chọn cả health. Đây là kiểm chứng rằng bộ test thực sự phát hiện lỗi phạm vi, không chỉ in pass khi chức năng nghiệp vụ vẫn đúng.

Mutation không thay thế việc kiểm tra cơ chế AOP thật; nó giúp đánh giá chất lượng test oracle.

## 16. Kiểm thử trên cơ chế AOP đang triển khai

Java Dynamic Proxy, subclass proxy và bytecode weaving có các ranh giới khác nhau. Sau refactor, phải test theo cơ chế production:

### Proxy interception

- Caller có dùng proxy hay raw target?
- Method còn thuộc interface được proxy cung cấp không?
- Có tự gọi trên this hoặc delegate tới target mà bỏ qua proxy không?
- Proxy có được tạo trước khi khởi tạo xong các phụ thuộc cần thiết không?
- Refactor có làm thay đổi scope hoặc vòng đời của proxy không?

### Subclass interception

- Method có thể override không?
- Có final/private method hoặc constructor được kỳ vọng can thiệp sai cách không?
- Đường gọi nào sử dụng subclass instrumented và đường nào dùng lớp gốc?
- Có thay đổi class hierarchy hoặc generic bridge method không?

### Weaving tại build/load time

- Class/method mới có nằm trong phạm vi weave không?
- Cấu hình build và runtime có đồng nhất không?
- Module, classloader, class nạp động và thư viện bên thứ ba có được instrument như mong muốn không?
- Các loại call/execution join point có được chọn đúng sau khi di chuyển mã không?
- Thứ tự advice trên cùng join point có còn như thiết kế không?

Không suy ra “self-invocation luôn bypass AOP” từ đặc điểm của một proxy; ở một cơ chế method-execution weaving đã cấu hình đúng, lời gọi nội bộ có thể vẫn kích hoạt advice. Tương tự, một file chứa aspect được biên dịch thành công không chứng minh join point mới đã được weave trong production.

### Unit test và integration test làm hai việc khác nhau

**Unit test** xác minh logic selection, policy, return/error handling bằng fake/spy nhỏ, nhanh và có oracle rõ. **Integration test** xác minh chính runtime interception chọn và chạy advice đúng trên build thực, kể cả classloader, method pattern và thứ tự weaving.

Regression suite tốt có cả hai: unit test bắt lỗi logic, integration test bắt lỗi thay đổi cấu trúc và cấu hình.

## 17. Tránh test pass giả vì AOP bị tắt hoặc recorder không hoạt động

Một negative test thấy **không có event** có thể pass giả nếu:

- Không chạy qua đối tượng được instrument.
- Bộ weaving chưa được bật trong môi trường test.
- Advice vẫn chạy nhưng logger sampling/drop event.
- Test kết thúc trước khi callback async phát event.
- Event list bị reset sai lúc.
- Một outer advice short-circuit và không gọi inner advice.
- Spy đo sai instance hoặc chỉ đo một lớp cũ sau refactor.

Để tránh:

1. Dùng **positive control** trên cùng runtime: một điểm bắt buộc có advice và xuất hiện event.
2. Gọi thật đường bị loại trừ và assert target/call site đã chạy.
3. Dùng probe trực tiếp tại advice, không chỉ dựa vào log phát ra ngoài.
4. Gắn operation ID/correlation ID cho event của test concurrent.
5. Chờ completion hoặc dùng scheduler điều khiển được cho async.
6. Quan sát số event **theo loại advice và join point**, không chỉ tổng số.
7. Kiểm tra fixture thực sự tạo đúng proxy/đối tượng đã được weave.

Với một pointcut rất rộng, negative test phải cố tình gọi những hàm nằm trong vùng nguy hiểm như logger, exporter, equals/hashCode/toString hoặc helper, nếu chúng đã được khai báo là điểm cấm của aspect đó.

## 18. Test đồng thời và dữ liệu ngữ cảnh sau refactor

Khi di chuyển code sang executor hoặc chia một operation thành nhiều task, ThreadLocal và state được aspect giữ có thể hoạt động khác.

Các tình huống:

**Cùng thread, hai yêu cầu nối tiếp.** Request A hoàn tất; request B chạy trên thread được tái sử dụng. Nếu advice không restore/remove context của A, log của B có thể mang correlation ID của A.

**Hai task song song.** Nếu aspect giữ per-call state trong một trường mutable trên instance dùng chung, task này có thể ghi đè context của task kia. Dùng snapshot/context bất biến và scope propagation phù hợp.

**Callback hoàn tất sau khi caller return.** Advice theo method execution đã kết thúc nhưng task mới báo lỗi. Final recorder phải gắn với logical completion nếu hợp đồng yêu cầu.

**Cancellation và timeout.** Tác vụ có thể vẫn chạy sau khi caller bỏ chờ. Một refactor chuyển đoạn mã gửi message sang worker có thể tạo message sau một lỗi timeout ở caller. Regression nên xác nhận policy idempotency và cách đối soát.

Test concurrent cần synchronization primitives hoặc scheduler deterministic; tránh sleep ngẫu nhiên rồi assert thiếu event. Điều kiện cleanup phải kiểm tra sau **mọi** đường return, throw và completion.

## 19. Rủi ro khi refactor telemetry và aspect infrastructure

Aspect có thể dùng một Logger, MetricsExporter hoặc PolicyEvaluator. Nếu refactor chuyển các lớp này vào package đang được pointcut chọn, advice có thể tự intercept chính hạ tầng của nó.

Ví dụ:

~~~text
before any selected method:
    MetricsExporter.publish("start")
        -> method bị pointcut chọn
            -> advice lại gọi MetricsExporter.publish
                -> ...
~~~

Kết quả có thể là recursion, log storm hoặc lỗi hiệu năng nghiêm trọng. Negative regression test cần xác minh:

- Exporter và logger internals không bị aspect cùng loại can thiệp.
- Gọi trực tiếp các phương thức của infrastructure không tạo thêm business-operation event.
- Một event nghiệp vụ không khuếch đại thành chuỗi event vô hạn.
- Nếu recorder gặp lỗi, best effort telemetry không làm thay đổi kết quả nghiệp vụ ngoài hợp đồng.

Loại trừ ở pointcut là hàng rào chính; reentrancy guard theo scope chỉ là lớp phòng vệ bổ sung và phải được restore trong finally. Nếu code chuyển thread, ThreadLocal guard không tự lan truyền sang thread khác.

## 20. Đo lường hiệu năng như một regression riêng

Một refactor có thể tạo nhiều method nhỏ hơn, khiến pointcut wildcard bắt thêm hàng nghìn lượt gọi. Kết quả nghiệp vụ không thay đổi nhưng độ trễ tăng.

Cần đo:

- Advice invocations per operation.
- Số event/span/log phát ra trên một request.
- Số lần tạo context hoặc đo thời gian.
- Tỷ lệ CPU/memory/allocations do instrumentation.
- Số time series do nhãn metric sinh ra.
- Latency ở các phân vị phù hợp, không chỉ trung bình.
- Thời gian chờ hoặc mức sử dụng resource do transaction/retry.

Đặc biệt không dùng correlation ID hoặc attempt ID làm metric label có cardinality gần như vô hạn. Nếu trước refactor mỗi operation tạo một span mà sau tạo hàng chục span, cần xem đó là instrumentation chi tiết được phê duyệt hay một sự nới pointcut ngoài ý muốn.

Test hiệu năng có nhiễu nên không cần ép so một con số cứng thiếu căn cứ. Đặt ngân sách/độ lệch theo thực nghiệm và kết hợp event counts mang tính quyết định để xác định nguyên nhân.

## 21. Checklist cho pull request có thay đổi cấu trúc

| Câu hỏi | Bằng chứng cần bổ sung |
| --- | --- |
| Có chuyển class/package không? | Danh sách pointcut phụ thuộc kiểu hoặc vùng mã, test match mới |
| Có đổi tên/signature/overload không? | Contract test cho từng method cần được chọn/loại |
| Có tách/gộp helper không? | Advice cardinality và final-operation count |
| Có đổi interface/proxy/delegation không? | Đường qua proxy và raw target, test self-call |
| Có đổi generic/hierarchy không? | Test override/bridge và số lượt instrument |
| Có thêm entry point không? | Test mọi đường tới sensitive effect |
| Có đổi sync thành async không? | Completion, cancellation, timeout, context |
| Có thay thứ tự advice không? | Event order và transaction/retry semantics |
| Có chuyển code hạ tầng quan sát không? | Negative test chống recursion/instrument thừa |
| Có đổi lỗi/return không? | Exception mapping, result contract |
| Có đổi effect được retry không? | Idempotency, số external effects, in-doubt commit |
| Có đổi weaving/classloader/build không? | Integration test trên cấu hình runtime tương ứng |
| Negative test có positive control không? | Chống pass giả do aspect không hoạt động |
| Test có phát hiện pointcut mutation không? | Thu hẹp và nới rộng đều được phát hiện |
| Có quyền cập nhật golden snapshot không? | Review thay đổi hợp đồng, không auto-accept |

## 22. Các lỗi phổ biến và cách sửa

**Lỗi 1 — Chỉ rerun unit test nghiệp vụ.** Logic vẫn đúng nhưng advice không chạy hoặc chạy hai lần. Cần event/assertions riêng cho AOP contract.

**Lỗi 2 — Bám cứng tên helper cũ.** Refactor hợp lệ làm test fail giả, trong khi hợp đồng operation không đổi. Tách kiểm thử business boundary khỏi kiểm thử cấu trúc thực sự thuộc pointcut.

**Lỗi 3 — Chỉ test dương tính.** Pointcut rộng thêm khiến exporter cũng bị instrument mà mọi positive test vẫn pass. Cần negative test cho từng vùng loại trừ quan trọng.

**Lỗi 4 — Chỉ test âm tính.** AOP bị tắt làm mọi excluded case pass. Thêm positive control trên cùng build.

**Lỗi 5 — Dựa vào vắng log.** Log có thể bị sampling/drop; dùng probe đếm trực tiếp lượt advice và join point.

**Lỗi 6 — Bỏ qua self-invocation sau khi tách lớp.** Với một số proxy, lời gọi nội bộ không quay qua interceptor. Test đường gọi thực tế; không áp dụng giả định ấy cho mọi dạng weaving.

**Lỗi 7 — Quên overload mới.** Một chữ ký mới không được bảo vệ vì pointcut quá hẹp; test mỗi public path có yêu cầu policy.

**Lỗi 8 — Không kiểm tra thứ tự retry/transaction.** Exception ở attempt đầu có thể làm transaction không còn dùng được; recorder có thể ghi success trước commit. Kiểm tra chuỗi event và số transaction.

**Lỗi 9 — Ghi success ở method-return sau khi đổi sang async.** Future vẫn có thể hoàn tất lỗi. Kiểm tra terminal outcome.

**Lỗi 10 — Coi timeout là rollback chắc chắn.** Task hoặc remote effect có thể tiếp tục. Cần idempotency/reconciliation, test trạng thái sau timeout.

**Lỗi 11 — Bỏ qua tác dụng phụ ngoài database.** Retry có thể gửi email hoặc thanh toán trùng. Test count và khóa chống lặp.

**Lỗi 12 — Cập nhật expected output theo implementation mà không review.** Có thể vô tình hợp thức hóa pointcut sai. Mỗi thay đổi hợp đồng phải có lý do rõ ràng và được đánh giá lại.

## 23. Bài tập tự kiểm tra

**Bài 1.** Một pointcut chọn execution của OrderService.submit(). Sau refactor toàn bộ logic chuyển vào CheckoutCoordinator.execute(), OrderService.submit() chỉ delegate. Có nhất thiết phải chuyển pointcut không?

**Đáp án:** Không nhất thiết. Nếu hợp đồng là quan sát một lần gọi API submit(), giữ pointcut tại façade có thể đúng. Nếu muốn đo chính phần tính toán hoặc bảo vệ effect ở implementation mới, phải đánh giá lại ranh giới và cập nhật pointcut/test tương ứng.

**Bài 2.** Method đặt hàng được tách thành bốn helper; metric operation_total tăng từ 1 lên 5 cho mỗi yêu cầu. Chức năng nghiệp vụ vẫn đúng. Đây có phải regression AOP không?

**Đáp án:** Có nếu hợp đồng yêu cầu một event cuối cho mỗi operation. Pointcut có thể mở rộng sang helper; cần negative tests và tách số liệu operation khỏi span/attempt cấp con.

**Bài 3.** Một test âm xác nhận MetricsExporter.publish không phát tracing event, nhưng cũng không có tracing event ở Business.submit. Có kết luận loại trừ exporter đúng không?

**Đáp án:** Chưa. AOP có thể không được bật. Cần positive control chứng minh Business.submit được trace trên cùng runtime.

**Bài 4.** Sau khi dời lời gọi RemoteApi.send từ Client sang NetworkHelper, call advice chỉ áp trong Client không còn chạy. Vì sao?

**Đáp án:** Call site mới nằm trong mã của NetworkHelper. Nếu pointcut ràng buộc vị trí từ vựng của caller, tập match đã đổi; phải đánh giá mục đích và cập nhật test/pointcut.

**Bài 5.** Một retry advice sau refactor cũng chọn sendPayment() chưa có idempotency. Một lỗi kết nối có thể gây hậu quả gì?

**Đáp án:** Có thể thực hiện thanh toán lặp dù attempt đầu đã có effect. Cần loại operation khỏi retry hoặc thiết kế idempotency key bền và đối soát trạng thái.

**Bài 6.** Trước đây method trả Receipt, nay trả CompletionStage<Receipt>. Advice after-returning báo success ngay. Điều gì sai?

**Đáp án:** Return handle không đồng nghĩa logical completion; future có thể hoàn tất lỗi. Cần observer completion đúng hợp đồng, transaction/context phù hợp.

**Bài 7.** Một bộ test unit chọn method qua annotation trên interface và luôn pass. Có chứng minh weaving thực ở implementation sau refactor sẽ nhìn thấy annotation đó không?

**Đáp án:** Không. Dynamic Proxy có thể cung cấp Method từ interface, trong khi cơ chế weaving khác có cách xử lý annotation trên method implementation khác. Phải kiểm thử trên runtime AOP thật và chữ ký runtime cụ thể.

**Bài 8.** Sau refactor, recorder và transaction đổi thứ tự. Test chỉ thấy operation cuối trả OK. Cần bổ sung gì?

**Đáp án:** Chuỗi begin/commit/rollback, thời điểm recorder, số attempt và kết quả khi commit thất bại. Return cuối thành công không chứng minh recorder đã nhìn thấy commit.

**Bài 9.** Một method được chuyển sang classloader khác và execution advice biến mất. Đây là lỗi gì?

**Đáp án:** Có thể do phạm vi weaving/classloader không còn bao phủ lớp mới, hoặc do type pattern không match. Kiểm tra build/load-time config và integration test runtime.

**Bài 10.** Mutation đổi selector chỉ nhận save() khiến cancel() mất advice; test mới vẫn pass. Điều này nói gì?

**Đáp án:** Regression suite không đủ nhạy với lỗi mất độ bao phủ. Cần case assert advice count/join point cho cancel() và kiểm tra target thực sự chạy.

## 24. Kết luận

Refactor là thay đổi cấu trúc, nhưng **tập join point và vòng đời advice có thể thay đổi theo cấu trúc**. Vì vậy, hồi quy AOP phải kiểm tra cả ba lớp:

1. **Selection:** điểm cần có advice vẫn có; điểm cấm không bị advice chọn thêm.
2. **Semantics:** thứ tự, số lượt proceed(), return/throw, transaction, retry, authorization và lifecycle async vẫn theo hợp đồng.
3. **Effects:** không lặp tác dụng phụ, không lộ dữ liệu, không rò context/tài nguyên, không tạo thêm telemetry ngoài phạm vi.

Một bộ regression đáng tin có expected contract độc lập với chi tiết refactor hợp lệ, positive/negative tests trên cùng runtime, kiểm thử ngoại lệ và tác dụng phụ, mutation để chứng minh phát hiện lỗi, cùng integration test của cơ chế proxy/weaving thực sự được triển khai.

**Điều phải bảo toàn sau mỗi lần đổi cấu trúc không phải là tên lớp cũ, mà là hành vi và ranh giới can thiệp đã được phê duyệt.**
# Aspect trừu tượng và phần hành vi dùng chung trong AOP

## 1. Vấn đề: cùng một hành vi, nhiều phạm vi áp dụng

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, một **aspect** là mô-đun tập hợp những mối quan tâm xuyên suốt như logging, metrics, audit, validation, policy hoặc kiểm tra hợp đồng. **Pointcut** chọn những **join point** mà công cụ AOP có thể nhận diện; **advice** cung cấp hành vi tại những điểm được chọn.

Giả sử ứng dụng có ba nhóm thao tác:

- Thao tác đơn hàng phải ghi thông tin bắt đầu/kết thúc.
- Thao tác thanh toán phải ghi thông tin tương tự, nhưng với tiêu chí chọn khác.
- Thao tác báo cáo chỉ cần đo thời gian, dùng lại một số bước quan sát.

Nếu tạo ba aspect gần như giống hệt, mã có thể lặp lại:

```text
Aspect A: chọn Order -> before -> run -> after/exception -> cleanup
Aspect B: chọn Payment -> before -> run -> after/exception -> cleanup
Aspect C: chọn Report -> before -> run -> after/exception -> cleanup
```

Một hướng trừu tượng hóa hợp lý là **tách hành vi dùng chung khỏi quyết định phạm vi**:

```text
             AbstractTracingAspect
             + common advice logic
             + common helper methods
             + abstract selection contract
                        ^
                        |
            +-----------+-----------+
            |                       |
    OrderTracingAspect      PaymentTracingAspect
    + pointcut for Order    + pointcut for Payment
    + optional hook         + optional hook
```

Nhờ đó:

1. Phần **chung** được viết, kiểm tra và bảo trì tập trung.
2. Phần **thay đổi** được hiện thực ở từng aspect cụ thể.
3. Consumer vẫn hiểu từng aspect được áp dụng cho những operation nào.
4. Hành vi xử lý return, exception và cleanup nhất quán, nếu chính sách yêu cầu.

Trong những ngôn ngữ AOP có hỗ trợ **aspect inheritance**, cấu trúc này có thể được biểu diễn bằng **aspect trừu tượng (abstract aspect)**. Nhưng **không phải mọi framework hoặc AOP engine đều hỗ trợ abstract aspect**; ở hệ thống dùng interceptor/proxy, ý tưởng tương tự có thể được triển khai qua strategy, abstract base class, composition hoặc template method.

**Phạm vi của bài:** kiến thức Aspect/AOP tổng quát từ cơ bản đến nâng cao. Những đoạn cú pháp AspectJ được ghi rõ là ví dụ của **một công cụ cụ thể**, không được coi là cú pháp AOP phổ quát hoặc mã Java 17 thuần.

## 2. Định nghĩa “aspect trừu tượng”

Một **abstract aspect** là cấu trúc mô-đun được khai báo trừu tượng trong một ngôn ngữ AOP có hỗ trợ, nhằm chia sẻ:

- Các method/hook/field chung.
- Các pointcut đã xác định hoàn toàn.
- Các **abstract pointcut** để aspect con cung cấp biểu thức lựa chọn.
- Advice dựa trên những pointcut được mở rộng hoặc hiện thực.
- Những quy tắc tổ chức khác nếu công cụ cho phép.

Một aspect cụ thể (*concrete aspect*) hoàn thành các phần trừu tượng cần thiết và tham gia cơ chế áp dụng advice thực tế.

Ví dụ khái niệm:

```text
abstract aspect BaseAudit:
    abstract selectedOperations()

    before selectedOperations():
        auditStart()

    afterReturning selectedOperations():
        auditSuccess()

concrete aspect OrderAudit extends BaseAudit:
    selectedOperations() = execution of order operations
```

Đây là **mã giả**, không phải cú pháp của mọi AOP language.

### 2.1. Abstract aspect không giống một aspect “bị tắt”

Một aspect trừu tượng có thể chứa advice hợp lệ về mặt cú pháp nhưng không được sử dụng độc lập như một **concrete aspect đầy đủ**. Việc advice trừu tượng được đưa vào runtime khi nào còn phụ thuộc mô hình inheritance/instantiation của engine.

Trong AspectJ code-style, cần **concrete aspect** kế thừa và hoàn thiện abstract pointcut để áp dụng advice; không thể nghĩ rằng khai báo một abstract aspect duy nhất sẽ tự động weave ra cùng hành vi như một concrete aspect có lựa chọn hợp lệ.

### 2.2. Abstract aspect và abstract class Java

Chúng có sự tương đồng về mục đích **dùng lại thiết kế**, nhưng khác về trách nhiệm:

| Đặc điểm | Java abstract class | Abstract aspect (ở công cụ hỗ trợ) |
| --- | --- | --- |
| Phần trừu tượng | Abstract method | Có thể có abstract pointcut và abstract method |
| Phần dùng chung | Field, method, template method | Helper, pointcut, advice, state |
| Phạm vi ảnh hưởng | Object/interface/hợp đồng Java | Những join point được công cụ AOP chọn |
| Triển khai vào runtime | Gọi method bình thường | Compiler/weaver/interception theo ngữ nghĩa công cụ |
| Tạo instance | Qua subclass concrete và `new` (nếu hợp lệ) | Aspect instance thường do runtime/weaver quản lý |
| Tự áp advice vào code nghiệp vụ | Không | Có thể sau khi cấu hình/build/weave đúng |

Một Java abstract class chỉ dùng làm cơ sở cho interceptor **không tự động** là abstract aspect thật.

## 3. Vị trí của abstract aspect trong hệ thống khái niệm AOP

Ba cấu phần có trách nhiệm khác nhau:

**Join point:** một điểm/sự kiện trong mô hình thực thi, như method execution hoặc method call, nếu engine hỗ trợ.

**Pointcut:** biểu thức hay predicate chọn join points. Nó trả lời “ở đâu/khi nào aspect có thể tác động”.

**Advice:** “làm gì tại điểm được chọn”, với các loại before, after returning, after throwing, around hay hình thức tương ứng.

**Abstract aspect:** một **cách tổ chức mô-đun**, không phải một loại join point mới. Nó có thể nắm giữ pointcut/advice/hook chung, để những concrete aspects lựa chọn phạm vi chuyên biệt.

Sơ đồ:

```text
Abstract aspect defines:
    selected()     <-- extension point
    before selected(): commonBefore()
    after selected(): commonAfter()

Concrete aspect A:
    selected() = join points of Service A

Concrete aspect B:
    selected() = join points of Service B
```

Hai aspect có thể tái sử dụng cùng hành vi nhưng chọn các join point **khác nhau**. Nếu hai tập giao nhau, **cả hai concrete aspects có thể áp advice lên cùng join point**; đây là vấn đề phải kiểm soát, không được mặc định hành vi chỉ chạy một lần vì mã nguồn chung nằm ở một base aspect.

## 4. Lợi ích của việc gom hành vi dùng chung

### 4.1. Giảm trùng lặp có ý nghĩa

Khi nhiều aspect cùng dùng:

- Cùng cách ghi trace start/end.
- Cùng cách phân loại lỗi.
- Cùng quy tắc bảo vệ dữ liệu trước khi logging.
- Cùng cơ chế lưu và khôi phục ngữ cảnh.
- Cùng quy ước tên metric, invocation ID hoặc audit ID.

ta có thể sửa ở một nơi thay vì sao chép cùng bug-fix vào nhiều aspect.

### 4.2. Một hợp đồng quan sát nhất quán

Nếu mọi nhóm nghiệp vụ đều cần:

```text
before: emit attempt
after success: emit completed
after error: emit failure
finally: release context
```

việc giữ phần dùng chung sẽ giúp tránh tình trạng một aspect quên cleanup hoặc phân loại exception khác aspect kia.

### 4.3. Cho phép phạm vi thay đổi độc lập

Một pointcut chọn Order execution có thể thay đổi mà không sửa logic audit chung. Ngược lại, quy định mask dữ liệu nhạy cảm có thể thay đổi tập trung mà không cần sửa từng pointcut.

### 4.4. Tăng khả năng kiểm thử

Có thể test **hợp đồng chung** một lần theo các tình huống nền tảng và test **mỗi concrete aspect** về matching, exclusion và tác động kết hợp.

Nhưng tái sử dụng không tự loại bỏ nhu cầu integration tests: compiler, precedence, dynamic guards, proxy bypass và build configuration vẫn có thể khác nhau giữa những concrete aspects.

## 5. Thiết kế phần biến đổi: abstract pointcut

Một **abstract pointcut** biểu thị một điểm mở rộng: base aspect biết hành vi sẽ chạy ở những join point “được chọn”, nhưng **chưa cố định tập được chọn**.

Mã giả:

```text
Base:
    abstract scope()

    before scope():
        sharedBefore()

Concrete A:
    scope() = call sites of A

Concrete B:
    scope() = executions of B
```

Cần phân biệt:

1. **Chữ ký pointcut:** tên và danh sách dữ liệu nó có thể expose/bind.
2. **Biểu thức lựa chọn cụ thể:** tập join point của một concrete aspect.
3. **Điều kiện runtime:** `args`, `target`, `this`, control flow hoặc guard nếu engine hỗ trợ.
4. **Join-point kind:** call và execution khác nhau; một base advice không làm hai loại tương đương.

### 5.1. Pointcut không phải method kiểm tra dữ liệu Java

Một abstract pointcut của AspectJ không đơn giản là:

```java
abstract boolean isSelected(Method method);
```

Đây chỉ là **một ý tưởng chiến lược Java**, có thể dùng cho proxy/interceptor thuần. Abstract pointcut của một AOP language thường tham gia vào **quá trình chọn join point** với semantics của compiler/weaver, không tương đương lời gọi hàm Java trả boolean.

### 5.2. Đừng tự mở rộng phạm vi khi hiện thực pointcut

Nếu base aspect chỉ cho phép hành vi audit tại các operation nghiệp vụ, concrete aspect không nên định nghĩa pointcut wildcard đến cả logger/audit sink nếu điều đó khiến aspect tự kích hoạt.

Một bản contract nên ghi rõ:

- Inclusions.
- Exclusions.
- Join-point kind.
- Dynamic binding.
- Weaving/proxy boundary.
- Các đường bypass và các điểm không thể advice.
- Điều kiện precedence/instantiation.

## 6. Cú pháp AspectJ: abstract aspect và abstract pointcut

**AspectJ** là ví dụ về một ngôn ngữ AOP có cú pháp *code-style aspect* và hỗ trợ aspect extension.

Ví dụ khung:

```java
public abstract aspect BaseTrace {
    protected abstract pointcut operations();

    before(): operations() {
        System.out.println("trace:before");
    }
}
```

Một aspect cụ thể:

```java
public aspect OrderTrace extends BaseTrace {
    protected pointcut operations():
        execution(* OrderService.*(..));
}
```

Hai đoạn này là **cú pháp AspectJ**, không phải Java source có thể biên dịch bằng `javac`. Compiler/weaver phải hỗ trợ file `.aj`, Java language level và bytecode version phù hợp.

Trong mô hình này:

- `BaseTrace` khai báo **cách xử lý chung**.
- `operations()` là điểm mở rộng chưa có biểu thức lựa chọn.
- `OrderTrace` cung cấp pointcut cụ thể.
- Advice từ base aspect được **kế thừa** vào concrete aspect theo quy tắc AspectJ.
- `execution(* OrderService.*(..))` là **mẫu riêng công cụ** chọn execution của những method phù hợp thuộc `OrderService`; không thể lấy mẫu này áp lên mọi engine.

### 6.1. Ngữ nghĩa liên quan từ đặc tả AspectJ

Một vài ràng buộc đáng nhớ:

- Aspect có thể **extends class** và **implements interfaces**, nhưng không được tạo với `new` như class thông thường; aspect instances do cơ chế AOP quản lý.
- Class Java thông thường **không được extends một aspect**.
- Aspect có thể extends một aspect khác **chỉ khi aspect cha là abstract** theo quy tắc code-style AspectJ.
- Fields, methods và pointcuts có thể được thừa kế; advice/declared behaviors của base được áp dụng theo semantics của engine.
- Một concrete aspect phải hoàn thiện những thành phần abstract còn thiếu.
- Aspect instantiation model được **kế thừa từ parent aspect** trong AspectJ; không mặc định mọi abstract aspect trở thành singleton.
- Thứ tự advice giữa subaspect và superaspect có những quy tắc precedence riêng.

Đây là **quy tắc công cụ**, không phải đặc tả AOP chung.

## 7. Tái sử dụng logic xử lý qua helper/hook

Ngoài abstract pointcut, một base aspect có thể khai báo **helper methods**:

```text
BaseTracing:
    abstract selected()
    before selected(): logStart()
    after selected(): logExit()

    logStart(): format trace event
    logExit(): format completion event
```

Các helper có thể:

- Chuẩn hóa tên operation.
- Mask hoặc redact thông tin nhạy cảm.
- Tạo metric labels.
- Lưu start time.
- Tạo sự kiện audit.
- Phân loại lỗi và lựa chọn mức độ log.
- Dọn context sau mỗi invocation.

### 7.1. Hook cho biến thể hợp lệ

Một base aspect có thể giữ quy trình chung nhưng cung cấp hook:

```text
formatOperationName(joinPoint)
shouldSample(joinPoint)
errorCategory(error)
recordEvent(event)
```

Một concrete aspect có thể tùy biến một số hook, với điều kiện ngôn ngữ/công cụ hỗ trợ và hook có semantics rõ ràng.

### 7.2. Không biến mọi helper thành abstract

Nếu một helper chỉ có một cách thực hiện đúng, để nó concrete. Quá nhiều abstract hooks làm base aspect trở thành một framework nhỏ khó hiểu, dễ phát sinh bug do các subclass kết hợp logic không tương thích.

Một tiêu chí tốt: chỉ tạo extension point cho **sự khác biệt có ý nghĩa**, đã xuất hiện ở nhiều consumer hoặc chắc chắn thuộc hợp đồng trừu tượng.

## 8. Template Method và Strategy là hai cách nghĩ hữu ích

**Template Method**: base class/aspect xác định thứ tự xử lý, subclass chỉ thay một vài bước.

```text
before -> validateContext -> emitStart
proceed -> business or inner advice
afterReturn/afterThrow -> emitOutcome
finally -> cleanup
```

Nếu một lớp thay đổi việc đi qua các bước này tùy ý, hợp đồng chung có thể không còn đúng.

**Strategy**: phần lựa chọn hoặc xử lý biến đổi được truyền vào qua một đối tượng chính sách thay vì inheritance.

```text
ReusableAdvice(SelectionStrategy, FormattingStrategy, Sink)
```

Ưu điểm của composition:

- Có thể cấu hình nhiều cách chọn mà không tăng số subclass.
- Test strategy riêng.
- Giảm coupling giữa phần xử lý và tập join points.
- Không phụ thuộc engine hỗ trợ abstract aspect inheritance.

**Khác biệt:** abstract aspect là một **khả năng của mô hình AOP/công cụ**; Template Method và Strategy là **mẫu thiết kế** có thể dùng để triển khai mục tiêu tương tự ngay cả khi engine không hỗ trợ syntax kế thừa aspect.

## 9. Ví dụ hoàn chỉnh với AspectJ: base advice + concrete selection

Ví dụ này gồm một class Java bình thường và hai file `.aj`. Nó minh họa **một concrete aspect thừa hưởng advice chung** và chọn method của mình.

**Tệp `Jobs.java`:**

```java
public class Jobs {
    public void run() {
        System.out.println("business:run");
    }

    public void skip() {
        System.out.println("business:skip");
    }
}
```

**Tệp `AbstractJobTrace.aj`:**

```java
public abstract aspect AbstractJobTrace {
    protected abstract pointcut selected();

    before(): selected() {
        System.out.println("trace:before:"
                + thisJoinPointStaticPart.getSignature().getName());
    }

    after() returning: selected() {
        System.out.println("trace:returned:"
                + thisJoinPointStaticPart.getSignature().getName());
    }

    after() throwing(Throwable error): selected() {
        System.out.println("trace:threw:"
                + error.getClass().getSimpleName());
    }
}
```

**Tệp `ConcreteJobTrace.aj`:**

```java
public aspect ConcreteJobTrace extends AbstractJobTrace {
    protected pointcut selected():
        execution(void Jobs.run());
}
```

**Tệp `Demo.java`:**

```java
public class Demo {
    public static void main(String[] args) {
        Jobs jobs = new Jobs();
        jobs.run();
        jobs.skip();
    }
}
```

### 9.1. Mối quan hệ giữa ba thành phần

- `Jobs` là nghiệp vụ bình thường, không biết `AbstractJobTrace` hoặc `ConcreteJobTrace`.
- `AbstractJobTrace` chứa advice chung, **không cố định** những execution được chọn.
- `ConcreteJobTrace` định nghĩa tập execution theo `selected()`.
- `Jobs.run` thuộc phạm vi và có advice.
- `Jobs.skip` không thuộc phạm vi.
- Nếu thay pointcut ở concrete aspect bằng một lựa chọn rộng hơn, cùng advice sẽ áp lên những điểm khác — không cần sửa body advice.

### 9.2. Build và chạy

**Chỉ minh họa lệnh cho môi trường đã cài compiler AspectJ phù hợp Java 17**:

```bash
ajc -17 -d out Jobs.java AbstractJobTrace.aj ConcreteJobTrace.aj Demo.java
java -cp "out:<path-to-aspectjrt.jar>" Demo
```

Trên Windows, dấu phân cách classpath là `;` thay vì `:`. `<path-to-aspectjrt.jar>` phải được thay bằng đường dẫn runtime thật. Đây **không phải** chương trình chỉ cần cài JDK là chạy được; cần `ajc` đúng phiên bản và thiết lập classpath thích hợp.

**Đầu ra theo ngữ nghĩa ví dụ khi weave đúng:**

```text
trace:before:run
business:run
trace:returned:run
business:skip
```

Không có `trace` cho `skip`, vì concrete pointcut không chọn execution đó.

### 9.3. Ranh giới của ví dụ

- Đây là **một** concrete aspect, vì vậy không có xung đột precedence do nhiều concrete aspects trong demo.
- `after() throwing` đã được định nghĩa, nhưng demo chưa tạo đường lỗi.
- Nếu method `run` ném, after-returning không chạy trên đường lỗi ấy; after-throwing có thể chạy nếu match và lỗi được truyền ra theo semantics tương ứng.
- Việc chọn execution khác chọn call site; đừng thay đổi join-point kind mà không xem kết quả mong muốn.
- Chỉ khi class/module nằm trong phạm vi build/weave thích hợp thì advice mới được áp dụng.
- Ví dụ không đưa ra cam kết mọi AspectJ version đều hỗ trợ Java 17; phải chọn toolchain tương thích.

## 10. Tại sao nên giữ pointcut trừu tượng đủ rõ?

Một abstract pointcut là **hợp đồng mở rộng**. Tên của nó phải chỉ ra đúng mục tiêu.

Tên kém rõ:

```text
abstract pointcut stuff();
abstract pointcut anything();
```

Tên tốt hơn:

```text
abstract pointcut selectedBusinessOperations();
abstract pointcut auditedMutations();
abstract pointcut measuredExecutions();
```

Nếu pointcut cần bind dữ liệu, phải thiết kế chữ ký và các ràng buộc binding rõ ràng. Không nên tự khẳng định mọi cấu hình concrete XML hoặc mọi loại pointcut runtime đều hỗ trợ expose args/state như nhau.

### 10.1. Binding và advice parameters

Một before advice có thể muốn truy cập:

- Join-point signature.
- Target hoặc receiver.
- Arguments.
- Annotation/metadata.
- Runtime context/correlation ID.

Tùy mô hình, abstract pointcut có thể được định nghĩa với tham số/binding. Những concrete pointcut phải giữ tương thích binding để advice lấy được dữ liệu đúng.

Một abstract pointcut không expose state sẽ đơn giản hơn cho nhiều hình thức cấu hình tự động. Khi cần dynamic binding phức tạp, xem cơ chế **kế thừa aspect bằng code** thay vì kỳ vọng mọi cấu hình deployment đều hiện thực được.

### 10.2. Không khiến consumer phải hiểu implementation helper

Consumer chỉ cần biết: aspect áp dụng ở đâu, thay đổi điều gì và có thể gây exception/side effect nào. Chi tiết như class `EventFormatter` hoặc một private helper nên được tách thành tài liệu triển khai.

## 11. Ví dụ Java 17 độc lập: trừu tượng hóa interceptor tương đương về thiết kế

Java 17 thuần **không có cú pháp abstract aspect / abstract pointcut weaving tích hợp**. Ví dụ sau dùng **abstract class + wrapper** để minh họa **tách hành vi chung khỏi phạm vi được chọn**.

Các yêu cầu kiểm chứng:

1. Hai concrete policies cùng kế thừa một xử lý enter/return/throw/finally.
2. Policy ngoài áp cho **mọi action**.
3. Policy trong chỉ áp cho action bắt đầu bằng `A` hoặc đúng `FAIL`.
4. Advice của lớp ngoài và trong có thứ tự lồng nhau rõ ràng.
5. Một action không khớp policy trong vẫn được policy ngoài quan sát.
6. Một exception lan qua hai policy, finally được thực thi đúng.
7. Caller gọi raw target trực tiếp thì **không đi qua wrapper**, làm rõ giới hạn proxy/adapter.

Tạo file `AbstractPolicyDemo.java`:

```java
public class AbstractPolicyDemo {
    @FunctionalInterface
    interface Work {
        String run(String action);
    }

    abstract static class BasePolicy {
        private final String id;

        BasePolicy(String id) {
            this.id = id;
        }

        protected abstract boolean matches(String action);

        protected void before(String action) {
            System.out.println(id + ":before:" + action);
        }

        protected void afterReturning(String action, String result) {
            System.out.println(id + ":return:" + action + ":" + result);
        }

        protected void afterThrowing(
                String action, RuntimeException error) {
            System.out.println(id + ":throw:" + action + ":"
                    + error.getClass().getSimpleName());
        }

        protected void afterFinally(String action) {
            System.out.println(id + ":finally:" + action);
        }

        final Work wrap(Work next) {
            return action -> {
                if (!matches(action)) {
                    return next.run(action);
                }

                before(action);
                try {
                    String value = next.run(action);
                    afterReturning(action, value);
                    return value;
                } catch (RuntimeException error) {
                    afterThrowing(action, error);
                    throw error;
                } finally {
                    afterFinally(action);
                }
            };
        }
    }

    static final class AllActions extends BasePolicy {
        AllActions() {
            super("all");
        }

        @Override
        protected boolean matches(String action) {
            return true;
        }
    }

    static final class SelectedActions extends BasePolicy {
        SelectedActions() {
            super("selected");
        }

        @Override
        protected boolean matches(String action) {
            return action.startsWith("A") || "FAIL".equals(action);
        }
    }

    static void call(String label, Work work, String action) {
        System.out.println("case:" + label);
        try {
            System.out.println("caller:" + work.run(action));
        } catch (RuntimeException error) {
            System.out.println("caller:error:"
                    + error.getClass().getSimpleName()
                    + ":" + error.getMessage());
        }
    }

    public static void main(String[] args) {
        Work target = action -> {
            System.out.println("business:" + action);
            if ("FAIL".equals(action)) {
                throw new IllegalStateException("operation failed");
            }
            return "done:" + action;
        };

        Work managed = new AllActions().wrap(
                new SelectedActions().wrap(target));

        call("both", managed, "A1");
        call("outer-only", managed, "skip");
        call("error", managed, "FAIL");
        call("direct-target", target, "A2");
    }
}
```

Chạy với JDK 17 hoặc mới hơn:

```bash
javac AbstractPolicyDemo.java
java AbstractPolicyDemo
```

**Stdout xác định:**

```text
case:both
all:before:A1
selected:before:A1
business:A1
selected:return:A1:done:A1
selected:finally:A1
all:return:A1:done:A1
all:finally:A1
caller:done:A1
case:outer-only
all:before:skip
business:skip
all:return:skip:done:skip
all:finally:skip
caller:done:skip
case:error
all:before:FAIL
selected:before:FAIL
business:FAIL
selected:throw:FAIL:IllegalStateException
selected:finally:FAIL
all:throw:FAIL:IllegalStateException
all:finally:FAIL
caller:error:IllegalStateException:operation failed
case:direct-target
business:A2
caller:done:A2
```

### 11.1. Điều gì được tái sử dụng?

`BasePolicy.wrap` hiện thực chung chu trình:

```text
matches?
  no -> next.run()
  yes ->
      before()
      try next.run()
      on success: afterReturning()
      on RuntimeException: afterThrowing(), rethrow
      finally: afterFinally()
```

`AllActions` và `SelectedActions` chỉ xác định **chiến lược lựa chọn** khác nhau. Nếu thay đổi format sự kiện hoặc cách dọn context chung trong `BasePolicy`, cả hai sẽ dùng hành vi đó mà không phải copy mã.

### 11.2. Vì sao hai policy có thể chạy cùng một operation?

`A1` khớp cả `AllActions` lẫn `SelectedActions`. Hai wrapper là **hai instance độc lập** trong chuỗi; vì vậy caller thấy hai cặp trước/sau.

Tái sử dụng base code **không loại bỏ hiện tượng double instrumentation** khi selection sets chồng lấn.

### 11.3. Vì sao after của policy trong xuất hiện trước?

`AllActions` là wrapper ngoài, `SelectedActions` là wrapper trong:

```text
AllActions(
    SelectedActions(
        Business
    )
)
```

Trên đường về, phần trong hoàn tất trước phần ngoài. Đây là **thứ tự đã được định nghĩa bằng lồng wrapper Java**. Nó minh họa logic tổng quát nhưng không phải tuyên bố thứ tự của mọi compiler AOP.

### 11.4. Vì sao lỗi có hai sự kiện throw?

`FAIL` khiến business ném `IllegalStateException`. Policy trong ghi lỗi rồi ném lại; policy ngoài bắt lỗi do continuation bên trong ném và cũng ghi lỗi. Finally mỗi tầng được thực thi.

Nếu log cả hai sự kiện, cần phân biệt **hai lần quan sát cùng một exception** với **hai exception độc lập**. Trace ID và span context giúp tránh đếm sai.

### 11.5. Vì sao direct target không có advice?

`call("direct-target", target, "A2")` gọi `Work` target trực tiếp, không đi qua wrapper. Đây là **giới hạn của cách triển khai dựa trên wrapping**. Trong một cơ chế weaving trực tiếp vào method execution, phạm vi áp dụng có thể khác.

### 11.6. Chương trình không phải một AspectJ abstract aspect

Đây là Java 17 thuần, nên:

- Không có pointcut DSL.
- Không tự động nhận join point.
- Không có bytecode weaving.
- Caller phải dùng `managed` reference.
- `BasePolicy` chỉ là **thiết kế trừu tượng hóa interceptor**, không phải `abstract aspect` theo ngữ nghĩa công cụ.
- Giới hạn bắt `RuntimeException` thuộc lựa chọn ví dụ, không phải đặc tả mọi loại after-throwing advice.

## 12. Abstract pointcut và concrete pointcut: chú ý loại join point

Một abstract aspect có thể định nghĩa advice chung:

```text
before selectedOperation():
    emitStart()
```

Nhưng concrete aspects chọn:

```text
A: execution of method
B: call to method
```

Với công cụ phân biệt `call` và `execution`, hai lựa chọn quan sát ở **vị trí khác nhau**:

- **Call join point:** tại chỗ gọi, có thể phụ thuộc call site được weave.
- **Execution join point:** tại phần thực thi thân method, có thể bao cả direct invocations sau khi class được weave.

Điều này ảnh hưởng:

- Receiver/target.
- Runtime binding.
- Exceptions.
- Overhead.
- Phạm vi khi code ở library/JDK.
- Việc một lời gọi nội bộ `this.inner()` được can thiệp hay không.
- Khả năng coverage khi chỉ một số module được weave.

**Đừng gộp mọi concrete pointcut chỉ vì chúng cùng implement tên `selected()`.** Một base advice có thể cần những giả định tối thiểu về join-point kind để hoạt động đúng với tất cả.

## 13. Reuse và aspect lifecycle

Trong các hệ thống AOP có aspect instances, một base aspect có thể có fields dùng để lưu state. Nhưng state ấy có ngữ nghĩa theo **aspect instantiation model**.

Những mô hình phổ biến trong AOP nâng cao có thể là:

- Một aspect instance dùng chung.
- Một instance gắn với target object.
- Một instance theo một đối tượng ở call site/receiver.
- Một instance theo control-flow scope.
- Một instance theo một request hoặc một vùng ngữ cảnh do engine cung cấp.

**Không có mặc định chung cho mọi công cụ.**

Trong AspectJ, các mô hình như `issingleton()`, `perthis(...)`, `pertarget(...)`, `percflow(...)` hoặc `percflowbelow(...)` được đặc tả. Theo tài liệu AspectJ, tiêu chí instantiation của concrete aspect được **thừa kế từ parent aspect**. Đây là chi tiết quan trọng khi thiết kế base aspect có mutable state.

### 13.1. Cấm hiểu sai “base aspect có một field chung”

Một field ở abstract aspect có thể trở thành state của **mỗi concrete aspect instance** theo lifecycle của engine; không thể khẳng định đó luôn là field chung cho toàn chương trình.

Một `static` field trong mã lại có semantics khác. Điều này đặc biệt ảnh hưởng counters, caches, correlation IDs và mutable policy config.

### 13.2. Không để trạng thái invocation vào field singleton chung

Sai lầm phổ biến:

```text
baseAspect.startTime = now()

outer enters: startTime=T0
inner enters: startTime=T1
outer exits: duration=now()-T1 (sai)
```

Ngay cả khi chỉ một thread, nested invocation có thể ghi đè mốc. Cần dùng local frame per advice invocation, một stack đúng ownership, hoặc context tương ứng.

### 13.3. Thread safety và reentrancy

Nhiều concrete aspects có thể tồn tại đồng thời; một concrete aspect có thể phục vụ nhiều thread. State mutable phải được quản lý theo contract:

- Invocation-local variables.
- Immutable metadata.
- Thread-local có cleanup nếu phù hợp.
- Context propagation khi async.
- Synchronization/atomic state cho counters dùng chung.
- Tránh gọi logger/metric client cũng nằm trong pointcut của chính mình.

Kế thừa code không tự đem lại thread safety.

## 14. Aspect extension trong AspectJ: quy tắc quan trọng

Tài liệu AspectJ mô tả:

1. **Aspects may extend classes** và implement interfaces, nhưng vẫn có ràng buộc aspect instantiation.
2. **Classes may not extend aspects.**
3. **Aspects extending aspects:** aspect có thể kế thừa abstract aspect; concrete aspect không thể được dùng làm superaspect theo mô hình code-style thông thường.
4. Fields, methods, pointcuts (và advice theo ngữ nghĩa inheritance) có thể được dùng lại.
5. Một concrete aspect cần hoàn thành những abstract declarations còn lại.
6. Việc advice được áp dụng gắn với **concrete aspect instance và điểm được match**, không chỉ tồn tại khai báo base.

### 14.1. Không xây cây kế thừa sâu không cần thiết

```text
BaseAspect
   |
PolicyAspect
   |
TracingAspect
   |
OrderTracingAspect
```

Càng nhiều tầng, càng khó biết pointcut đã thay đổi ở đâu, method hook được override ở tầng nào, và advice đến từ aspect nào. Một cây kế thừa dài làm tăng cognitive load và nguy cơ đổi behavior không chủ ý.

Ưu tiên:

- Một hoặc vài base aspects thật sự ổn định.
- Interface hoặc composition cho policy phụ trợ.
- Concrete aspect mỏng, có pointcut rõ.
- Integration test cho behavior tổng hợp.

## 15. “Inherited advice” không có nghĩa chỉ một lần advice

Giả sử base aspect:

```text
AbstractAudit:
    before selection: emitEvent()
```

Hai concrete aspects cùng mở rộng base:

```text
ConcreteA -> selection of operation X
ConcreteB -> selection of operation X
```

Nếu cả hai đều được weave/activated, operation X có thể nhận **hai lần advice**. Đây không phải lỗi kế thừa của ngôn ngữ; đó là kết quả **hai concrete aspects cùng match**.

Để tránh double-count:

- Kiểm tra tập pointcut A và B có giao nhau không.
- Nếu có giao nhau có chủ đích, định nghĩa ý nghĩa hai event và tên aspect nguồn.
- Nếu không có chủ đích, thu hẹp scope/exclusions.
- Gắn invocation/correlation ID và aspect ID khi ghi log.
- Không dùng một cờ global đơn giản bỏ mọi nested advice để che duplicate.
- Có test đúng số lượng trước/sau/throw events.

### 15.1. Một base aspect có thể tái sử dụng nhưng vẫn cần policy riêng

Audit event được dùng chung về format không đồng nghĩa cùng một số lượng event hoặc cùng retention level. Hành vi giống nhau về **mẫu xử lý** vẫn có thể khác hợp đồng về **phạm vi**, **bảo mật** và **side effects**.

## 16. Precedence: thứ tự giữa concrete aspects và các advice

Khi nhiều concrete aspects cùng áp dụng ở một join point, cần biết **precedence**.

Trong AspectJ, tài liệu định nghĩa:

- Có thể khai báo quan hệ precedence bằng `declare precedence`.
- Nếu subaspect và superaspect cùng ảnh hưởng một join point, subaspect có precedence cao hơn superaspect theo quy tắc mặc định liên quan.
- Các concrete aspects độc lập không có precedence quan hệ rõ ràng có thể có thứ tự **không được bảo đảm**.
- Một around advice precedence cao hơn có thể quyết định có `proceed` xuống advice thấp hơn không.

**Không viết code dựa trên tên class/alphabetical/source order** trừ khi engine chính thức bảo đảm.

### 16.1. Before và after có thể đảo thứ tự quan sát

Với mô hình:

```text
Outer(
    Inner(
        Business
    )
)
```

Thứ tự:

```text
Outer.before
Inner.before
Business
Inner.after
Outer.after
```

Đây là đặc tính của **lớp bao**. Không có nghĩa “aspect ưu tiên cao hơn thì tất cả các câu lệnh của nó đều xuất hiện sớm hơn”.

### 16.2. Conrete aspect trong `declare precedence`

Ví dụ cú pháp AspectJ:

```java
declare precedence: SecurityAudit, OrderTrace, *;
```

Đây là fragment ngôn ngữ công cụ, không phải Java thuần. Quan hệ precedence có ý nghĩa trên các concrete aspects được chọn; khai báo chỉ nêu tên abstract aspects có thể không áp đúng như mong đợi với những concrete aspects phát sinh.

Đặc tả AspectJ còn hỗ trợ type patterns có hậu tố `+` khi muốn chọn subtype/descendant aspect theo phạm vi được cho phép.

## 17. Hành vi chung trên đường lỗi

Để dùng chung logic một cách đúng đắn, cần phân biệt:

- **Before advice:** có thể chặn target nếu ném lỗi trước khi tiếp tục.
- **After returning advice:** chỉ áp dụng khi phần được quan sát kết thúc bình thường.
- **After throwing advice:** áp dụng khi phần được quan sát kết thúc bằng exception phù hợp.
- **Finally/after advice:** được thực hiện trong phạm vi mà công cụ xác định.
- **Around advice:** có thể bắt lỗi, đổi lỗi, trả fallback hoặc gọi lại continuation nếu ngôn ngữ cho phép.

Một base aspect chỉ ghi lỗi trong `after throwing` không tự bảo đảm business state được rollback. Nếu after logging tự ném lỗi, caller có thể nhận lỗi mới chứ không còn thấy lỗi gốc.

### 17.1. Khi kết hợp aspect dùng chung với retry

```text
RetryAround(
    SharedAuditAdvice(
        Business
    )
)
```

Với nhiều attempts, audit bên trong có thể chạy nhiều lần. Nếu đảo:

```text
SharedAuditAdvice(
    RetryAround(
        Business
    )
)
```

audit bên ngoài có thể chỉ quan sát outcome tổng thể của một logical request. Hai thứ tự phục vụ hợp đồng khác nhau.

**Không cho rằng dùng chung base aspect tự động thống nhất semantics retry.** Contract cần phân biệt request count, attempt count và actual business execution count.

## 18. Dùng chung advice quanh method trả bất đồng bộ

Với Java `CompletableFuture<Result>`:

```text
Caller -> advised method -> returns Future
                       -> task completes later
```

Nếu base aspect dùng after-returning tại method execution, nó có thể chỉ ghi **method returned Future**, không phải **logical task succeeded**.

Một concrete aspect chọn async method cần quyết định:

- Ghi sự kiện khi method trả Future hay khi Future hoàn tất?
- Có xử lý exceptional completion không?
- Correlation ID có được truyền qua executor không?
- Khi cancellation/timeout, có ghi khác success/failure không?
- Một completion callback của chính aspect có gây reentrancy hoặc lỗi làm đổi outcome không?

Một base aspect giả định mọi method đều synchronous sẽ **không tự đúng** khi subclass concrete chọn điểm async. Có thể cần base strategy riêng hoặc hợp đồng chung rõ về completion boundary.

## 19. Tái sử dụng với interface, helper class và composition

Có ít nhất bốn cấp tái sử dụng:

| Cấp | Cách làm | Tính di động |
| --- | --- | --- |
| Common utility | Helper định dạng event, mask data, error mapping | Thường dùng được với Java thường |
| Template interceptor | Abstract Java class giữ order before/after/finally | Dùng khi có wrapper/interceptor |
| Strategy/composition | Truyền matcher, sink, error translator | Ít ràng buộc kế thừa, dễ test |
| Abstract aspect | Aspect base + abstract pointcut/inherited advice | Phụ thuộc AOP language/compiler hỗ trợ |

Đôi khi giải pháp tốt nhất là **kết hợp**:

- Base aspect chỉ phụ trách pointcut và advice boundary.
- Business-independent formatting nằm ở utility/strategy.
- Concrete aspect chỉ quyết định scope.
- Những ràng buộc bảo mật/giao dịch được bảo vệ ở boundary đáng tin.

Tránh đặt mọi thứ vào một base aspect khổng lồ; nó dễ thành “god aspect” áp chính sách trái ngược cho nhiều miền nghiệp vụ.

## 20. Tránh tự can thiệp khi dùng chung helper

Một shared logging helper có thể vô tình thuộc pointcut của chính concrete aspect. Ví dụ:

```text
ConcreteOrderTrace.before
  -> BaseTrace.logStart
      -> Logger.write
          -> ConcreteOrderTrace.before
              -> ...
```

Các phương án:

1. **Chọn pointcut hẹp** theo operation thật sự cần can thiệp.
2. Loại helper/logger/sink theo loại join point và type phù hợp.
3. Dùng lexical exclusion khi công cụ hỗ trợ, nhưng hiểu khác biệt call/execution.
4. Dùng dynamic control-flow guard nếu helper cũng cần được advice trong ngữ cảnh khác.
5. Đặt guard phạm vi ngắn quanh emission, cleanup bằng `finally`.
6. Kiểm thử nested business calls vẫn được advice, không loại quá rộng.

Một base aspect dùng chung mà tự gọi logger rộng có thể lan lỗi recursion tới **tất cả concrete aspects**, làm lỗi nghiêm trọng hơn so với bản sao nhỏ ở một điểm.

## 21. Hợp đồng trừu tượng và nguyên tắc thay thế

Base aspect nên công bố:

- Preconditions của hook implementations.
- Những side effects base sẽ luôn thực hiện.
- Quy tắc masking/tracing.
- Guarantee của return/exception.
- Quy tắc giữ cause/suppressed.
- Tối đa bao nhiêu lần gọi continuation.
- Yêu cầu thread safety và reentrancy.
- Các join-point kinds được cho phép.
- Những operation **không được** chọn vì sẽ tạo vòng hoặc bypass security.

Nếu concrete aspect override helper mà ném một exception mới hoặc bỏ cleanup, nó có thể làm **hợp đồng base mất hiệu lực**.

### 21.1. Không siết precondition âm thầm

Ví dụ một base validator cho phép mọi request có ID hợp lệ, nhưng concrete aspect đổi hook để từ chối thêm một loại request hợp lệ mà không cập nhật public API contract. Đây có thể là breaking behavior change.

### 21.2. Không làm yếu postcondition của common advice

Nếu base logging promise “không thay return/exception target”, concrete hook không nên bỏ exception gốc và trả false success. Nếu cần biến đổi behavior, nên tách thành **một chính sách khác được mô tả công khai**.

### 21.3. Không dùng abstract aspect để che dependency ẩn

Một concrete aspect không nên phải đoán rằng base secretly đọc một thread-local, sử dụng service locator hoặc gọi network. Dependencies chung phải được tài liệu hóa và kiểm thử failure mode.

## 22. Phiên bản hóa base aspect: tác động dây chuyền

Một thay đổi ở base aspect có thể ảnh hưởng mọi concrete aspect đang dùng nó.

Ví dụ:

- Đổi tên hoặc signature abstract pointcut.
- Đổi hook từ return void thành trả giá trị khác.
- Thêm mandatory abstract hook.
- Đổi error translation.
- Bổ sung một advice mới trong base.
- Đổi order giữa before/after/around.
- Đổi default sampling.
- Đổi aspect instantiation model hoặc state ownership.
- Nới rộng base pointcut làm nhiều join points cùng match.
- Đổi visibility helper được concrete aspects gọi.

### 22.1. Source compatibility khác behavior compatibility

Một concrete aspect vẫn biên dịch sau khi base được sửa nhưng logging có thể tăng gấp đôi hoặc loại exception công khai thay đổi. Regression tests phải xét **event order**, **target call count**, **return/throw** và **state** chứ không chỉ compiler báo pass.

### 22.2. Cấu hình weaving là một phần artifact

Nếu consumer runtime nạp class chưa weave hoặc chỉ một số aspect được kích hoạt, behavior có thể khác build/test. Khi phát hành shared aspect module, cần ghi rõ:

- Compiler/weaver version tương thích.
- Java language/bytecode target.
- Danh sách concrete aspects mong đợi.
- Quy tắc precedence.
- Artifact/source weaving scope.
- Module/classloader assumptions.
- Release notes cho breaking pointcut changes.

## 23. Khi nào không nên dùng abstract aspect?

Không phải mọi khác biệt nhỏ đều cần inheritance.

**Không nên ưu tiên abstract aspect nếu:**

- Chỉ có một aspect cụ thể và chưa có nhu cầu reuse rõ.
- Chỉ muốn chia sẻ vài utility methods.
- Engine đang dùng chỉ hỗ trợ proxy/interceptor, không hỗ trợ aspect inheritance.
- Các concrete aspects có error semantics trái ngược.
- Các nhóm nghiệp vụ có lifecycle hoặc completion boundary khác nhau.
- Một base pointcut buộc tất cả concrete aspects dùng cùng join-point kind dù không phù hợp.
- Nhu cầu cần thay đổi policy lúc runtime thường xuyên; strategy có thể linh hoạt hơn.
- Base aspect phải chứa quá nhiều type checks/branching theo tên concrete aspect.
- Một chuỗi kế thừa sâu làm khó hiểu thứ tự advice.
- Tái sử dụng làm các module phụ thuộc chặt vào compiler/weaver đặc thù ngoài chủ đích.

**Nguyên tắc:** trừu tượng hóa phần **ổn định về mặt ý nghĩa**, không chỉ dòng code giống nhau ngẫu nhiên.

## 24. Các mẫu thiết kế hay dùng

### 24.1. Template Advice

Base cung cấp advice chung, concrete aspect cung cấp selection và một vài hooks.

Ưu điểm: nhất quán quy trình. Nhược điểm: coupling giữa base và subclasses.

### 24.2. Policy Strategy

Base logic gọi object policy:

```text
ReusableInterceptor(
   Matcher,
   EventSink,
   ErrorPolicy,
   SamplingPolicy
)
```

Ưu điểm: dễ unit-test/tùy biến. Nhược điểm: phải quản lý object/configuration và lựa chọn điểm intercept riêng.

### 24.3. Role-specific mixin + advice

Nếu công cụ hỗ trợ **inter-type declaration**, có thể bổ sung role/state cho target và dùng advice để cập nhật tại join points. Đây là bài toán **structural crosscutting** khác với abstract aspect; có thể kết hợp nhưng không đồng nhất.

### 24.4. Marker/annotation-driven selection

Concrete aspect hoặc strategy có thể chọn operation dựa trên annotation/metadata. Phải hiểu:

- Annotation retention/visibility.
- Nơi annotation được kế thừa hoặc không.
- Method bridge/generics.
- Annotation trên interface khác annotation trên implementation.
- Runtime proxy/weaver chọn method nào.

Đừng nghĩ một marker annotation là bảo đảm mọi engine đều sẽ áp advice.

## 25. Kiểm thử base aspect và concrete aspects theo lớp

Một chiến lược test tốt gồm ba mức.

**Mức 1 — Shared logic unit tests:**

- Helper format/mask.
- Error classification.
- Lifecycle của context.
- Guard reset sau exception.
- Idempotency nếu có.

**Mức 2 — Concrete scope tests:**

- Pointcut chọn đúng positive cases.
- Pointcut loại đúng negative cases.
- Không match logger/audit sink vô tình.
- Call vs execution đúng với use case.
- Dynamic conditions hoạt động khi arguments thay đổi.

**Mức 3 — Integration/weaving tests:**

- Advice base thực sự áp dụng qua concrete aspect.
- Compiler/weaver và runtime setup đúng.
- Hai concrete aspects cùng match có được phát hiện.
- Return/error precedence và exception wrapping đúng.
- Direct target/proxy bypass được kiểm tra nếu sử dụng wrapping.
- Thread, nested invocation, async completion đúng contract.

### 25.1. Test được tái sử dụng không thay thế test theo phạm vi

Một base aspect có thể đạt 100% branch coverage trong unit tests nhưng concrete pointcut `execution(* *(..))` áp quá rộng. Scope là **một phần của correctness**; mỗi concrete aspect cần chứng cứ riêng.

### 25.2. Negative tests đặc biệt quan trọng

Không chỉ assert “operation A có log”. Hãy assert:

- Operation không thuộc scope **không có log**.
- Logger/helper không tự bị aspect xử lý.
- Target không bị gọi khi security precondition từ chối.
- Một method có annotation tương tự nhưng sai type không bị chọn.
- Khi nhiều aspects cùng match, số lần advice đúng chính sách.

## 26. Ma trận kiểm thử đề xuất

| Ca | Kỳ vọng |
| --- | --- |
| Base aspect trừu tượng chưa có concrete aspect | Không tự giả định advice được triển khai |
| Concrete pointcut chọn một method | Chỉ method đó nhận inherited advice |
| Concrete pointcut không chọn method khác | Method kia không nhận inherited advice |
| Hai concrete aspects chọn cùng method | Phát hiện overlap và số lần advice |
| Before advice chung | Chạy ở pha đúng cho các join points được chọn |
| After returning chung | Chỉ quan sát normal completion thuộc scope |
| After throwing chung | Quan sát exception được chọn theo type binding |
| Around advice chung | Proceed/short-circuit đúng contract |
| Concrete hook tùy biến | Không phá return/error/cleanup guarantee |
| Helper chung ném lỗi | Chính sách best-effort/fail-closed rõ |
| Reentrant/nested invocation | Context từng invocation độc lập |
| Multi-thread | Không trộn mutable state qua requests |
| Retry | Phân biệt operation logic và từng attempt |
| Async Future | Không nhầm return Future với completion |
| Pointcut trùng logger | Không sinh self-interception vô hạn |
| Missing class weaving | Phát hiện cấu hình thiếu, không silently pass |
| Incorrect compiler version | Build báo lỗi rõ ràng |
| Precedence đổi | Event order và behavior đúng tài liệu |
| Base upgrade | Regression tests của mọi concrete aspect |
| Raw target bypass proxy | Nếu cơ chế wrapping, test đúng giới hạn |
| Null/invalid args | Các điều kiện trước được áp tại ranh giới đúng |

### 26.1. Event collector tốt hơn chỉ xem stdout

Trong bài minh họa, stdout giúp hiểu thứ tự. Trong test thực, thu event có cấu trúc:

```text
aspectId
joinPointId
invocationId
parentInvocationId
phase
outcome
attemptId
```

rồi so khớp số lần và thứ tự. Điều này hữu ích với nested calls và nhiều aspects, đồng thời tránh dùng timestamp đơn thuần làm bằng chứng một total order trong hệ thống async.

## 27. Gỡ lỗi khi inherited advice không chạy

Hãy đi theo thứ tự:

1. Có concrete aspect nào **thực sự được kích hoạt** không?
2. Nó có kế thừa đúng base abstract aspect không?
3. Nó đã hiện thực toàn bộ abstract pointcuts/methods chưa?
4. Pointcut cụ thể có chọn đúng loại join point không?
5. Target/caller code có nằm trong **phạm vi weaving** không?
6. Nếu dùng proxy, caller có giữ proxy reference không?
7. Dynamic guard/binding có đúng không?
8. Advice ưu tiên cao hơn có short-circuit trước khi xuống chain không?
9. Có helper/pointcut exclusions loại nhầm method không?
10. Có nhiều aspect cùng match rồi log bị ghi đè/lọc không?
11. Aspect instance có được tạo đúng lifecycle không?
12. Build/deployment có nạp đúng binary/configuration không?

Đừng giải quyết chỉ bằng cách đổi pointcut thành wildcard rộng. Nó có thể làm advice chạy được trên một ca test nhưng gây recursion và can thiệp nhầm ở production.

## 28. Gỡ lỗi khi advice chạy nhiều lần

Những nguyên nhân thường gặp:

- Hai concrete aspects kế thừa cùng base và scope giao nhau.
- Một operation vừa được chọn ở method call vừa ở method execution.
- Around advice có retry `proceed` nhiều lần.
- Nested business methods đều được advice.
- Logging helper lại thuộc pointcut.
- Caller đi qua hai tầng proxy/wrapper.
- Một test/app đã kích hoạt cùng aspect bằng nhiều cơ chế weaving/configuration.
- Cấu hình quan sát ghi trùng event dù target chỉ chạy một lần.

Để phân biệt, thu:

- Concrete aspect ID.
- Join-point kind và signature.
- Receiver/target identity nếu được phép.
- Invocation/attempt ID.
- Business execution counter.
- Advice enter/exit counter.
- Event sink acknowledgement (nếu có).

**Số dòng log nhiều hơn không luôn chứng minh business chạy nhiều lần.** Tương tự, một lần business execution có thể nhận nhiều lời advice hợp lệ.

## 29. Những hiểu nhầm thường gặp

**“Abstract aspect là interface Java đổi tên.”** Không. Nó có thể chứa advice, pointcut, lifecycle và semantics weaving riêng.

**“Chỉ cần khai báo abstract aspect là advice chạy.”** Không theo mô hình AspectJ code-style thông thường; cần concrete aspect và weaving phù hợp.

**“Mọi AOP engine đều hỗ trợ abstract aspect.”** Không. Một số chỉ có interceptor chain hoặc decorators.

**“Abstract pointcut là Java method boolean.”** Không trong AspectJ; đó là một declaration được compiler/weaver diễn giải để chọn join points.

**“Kế thừa code chung bảo đảm mỗi operation chỉ bị advice một lần.”** Sai nếu nhiều concrete aspects match hoặc nhiều wrapper được lồng nhau.

**“Concrete aspect có thể luôn extends bất kỳ concrete aspect.”** Không trong mô hình AspectJ code-style được đặc tả; aspect-to-aspect extension yêu cầu parent abstract.

**“Method helper chung là thread-safe vì nằm trong base.”** Không. Mutable state và lifecycle quyết định thread safety.

**“Một field trong base abstract aspect luôn shared singleton.”** Không thể khẳng định; tùy instantiation model và static/instance field.

**“Subaspect precedence cao hơn nghĩa mọi after đều chạy trước.”** Không; nesting và advice kinds quyết định thứ tự vào/ra.

**“Một concrete pointcut là call, concrete khác là execution vẫn có cùng coverage.”** Không; đây là hai loại join point khác nhau.

**“Một advice trả thành công sau khi Future được tạo nghĩa tác vụ async đã thành công.”** Sai; method-return khác task completion.

**“Tái sử dụng là gom mọi policy vào một base aspect.”** Không. Một base có quá nhiều behavior làm coupling cao và khó kiểm thử.

**“Dùng abstract class wrapper Java là làm abstract aspect thật.”** Không: Java wrapper cần reference đi qua nó, không tự weave join points.

**“Đổi base hook signature không ảnh hưởng consumer nếu API nghiệp vụ giữ nguyên.”** Sai; concrete aspects có thể không compile hoặc thay behavior.

**“Không có log nghĩa business không chạy.”** Sai khi không match, bypass, short-circuit hoặc logger lỗi.

**“Một aspect chung về logging đủ làm security boundary.”** Không nếu caller còn đường bypass hoặc policy có thể bị vô hiệu hóa; cần bảo vệ bất biến ở ranh giới tin cậy.

## 30. Bài tập tự luyện

### Bài 1 — Phân tách chung và riêng

Order và Payment cùng cần log start/end, nhưng chọn method bằng biểu thức khác nhau. Nên đặt phần nào ở base, phần nào ở concrete aspect?

**Gợi ý đáp án:** Base chứa advice/hook chung; concrete aspect định nghĩa pointcut cho từng miền, thêm policy riêng nếu thực sự cần.

### Bài 2 — Abstract pointcut

Một base aspect có `abstract pointcut selected()` nhưng chưa có concrete aspect. Có thể khẳng định mọi business method đã được advice không?

**Gợi ý:** Không. Phải có concrete implementation, build/weaving và pointcut matching phù hợp.

### Bài 3 — Kế thừa aspect

Trong AspectJ code-style, một concrete aspect muốn extends một concrete aspect khác. Điều gì cần kiểm tra?

**Gợi ý:** Theo tài liệu, aspect có thể extends **abstract aspect**, không dùng concrete aspect làm superaspect bình thường; nên refactor shared logic vào abstract base hoặc composition.

### Bài 4 — Điểm chọn chồng lấn

Hai concrete aspects kế thừa cùng base, cả hai chọn `execution(* Order.submit(..))`. Có thể nhận một hay nhiều sự kiện before?

**Gợi ý:** Có thể nhận nhiều advice, mỗi concrete aspect có một ứng dụng riêng. Kiểm tra precedence và số lần chính xác.

### Bài 5 — State trong singleton aspect

Base giữ `long startedAt`; outer method được advice rồi gọi inner method cũng được advice. Tại sao duration outer có thể sai?

**Gợi ý:** Inner ghi đè state của outer. Dùng local frame per invocation hoặc context phù hợp.

### Bài 6 — Policy giới hạn lỗi

Base audit giữ nguyên exception gốc; concrete hook lại ném lỗi sink mà không giữ `cause`. Có còn đúng hợp đồng base không?

**Gợi ý:** Không nếu đã cam kết transparent error propagation. Phải cô lập lỗi phụ trợ hoặc công bố thay đổi failure policy.

### Bài 7 — Async

Một concrete aspect chọn method trả `CompletableFuture` nhưng inherited after-returning advice ghi “thành công” ngay khi method trả. Điều này đúng không?

**Gợi ý:** Chỉ đúng nếu “thành công” có nghĩa **trả Future thành công**. Nếu muốn task success, phải quan sát completion riêng.

### Bài 8 — Không có abstract aspect trong công cụ đang dùng

Bạn có interface proxy và một base Java abstract interceptor; có đạt mục tiêu tái sử dụng không?

**Gợi ý:** Có thể tái sử dụng logic thiết kế, nhưng không gọi đó là language-level abstract aspect hay tự giả định mọi method được weave.

### Bài 9 — Override pointcut rộng quá

Concrete aspect định nghĩa pointcut bao toàn bộ `execution(* *(..))` và inherited logging advice gọi logger bị chọn. Nguy cơ?

**Gợi ý:** Self-interception/recursion, overhead và can thiệp nhầm; cần scope/exclusions phù hợp.

### Bài 10 — Release base aspect

Một bản cập nhật base thêm after-throwing advice. API business không đổi. Có cần regression tests không?

**Gợi ý:** Có. Exception propagation, event count, performance và behavior của mọi concrete aspects có thể thay đổi.

## 31. Checklist thiết kế và triển khai

- [ ] Có ít nhất hai use cases thật sự chia sẻ logic/hợp đồng.
- [ ] Đã tách phần dùng chung và phần biến thiên có ý nghĩa.
- [ ] Engine thực sự hỗ trợ abstract aspect hay cần pattern tương đương.
- [ ] Các abstract pointcuts có tên và contract rõ.
- [ ] Concrete aspect hiện thực chính xác join-point kinds và scope.
- [ ] Có exclusions tránh logger/metric/audit sink recursion.
- [ ] Không chọn wildcard toàn chương trình ngoài chủ đích.
- [ ] Đã kiểm tra binding của tham số và dynamic conditions.
- [ ] Đã kiểm tra visibility/access rules của aspect language.
- [ ] Hiểu lifecycle/instantiation model của base và concrete aspects.
- [ ] Không dùng mutable singleton field làm state per invocation.
- [ ] Hooks giữ contract về return/exception/cleanup.
- [ ] Không cho concrete aspects phá pre/postconditions của public API ngoài chủ đích.
- [ ] Phân biệt direct call/proxy bypass và weaving coverage.
- [ ] Có policy precedence khi nhiều aspects match.
- [ ] Có test overlap của concrete selections.
- [ ] Có test before, normal return, throwing, finally và short-circuit.
- [ ] Có test nested/reentrant operations và cleanup sau lỗi.
- [ ] Có test retry, số lần target chạy và side effects.
- [ ] Có test async completion nếu concrete scope có Future/task.
- [ ] Có test concurrency nếu aspect giữ state.
- [ ] Có error taxonomy và quy tắc cause/suppressed nếu lỗi phụ trợ ném.
- [ ] Có unit tests của helper/strategy chung.
- [ ] Có compile/weave integration tests cho concrete aspects.
- [ ] Có source/binary/deployment compatibility tests khi nâng cấp base.
- [ ] Không đặt mọi dependency/hành vi vào một “god aspect”.
- [ ] Đã công bố cấu hình, target operations và known limitations cho consumer.
- [ ] Có release notes cho những thay đổi scope/hook/precedence.
- [ ] Không dựa vào tên class hoặc source order thay cấu hình precedence chính thức.
- [ ] Đã đối chiếu compiler/runtime version với tài liệu công cụ.

## 32. Tài liệu tham khảo và ranh giới áp dụng

Các tài liệu sau là nguồn ngữ nghĩa cho **AspectJ như một ví dụ AOP có abstract aspects**. Chúng **không** biến cú pháp hay giới hạn của AspectJ thành chuẩn chung của mọi engine:

- [Eclipse AspectJ Programming Guide — Aspects](https://eclipse.dev/aspectj/doc/released/progguide/semantics-aspects.html): aspect extension, abstract parent, instantiation lifecycle.
- [Eclipse AspectJ Programming Guide — Static crosscutting](https://eclipse.dev/aspectj/doc/released/progguide/semantics-declare.html): abstract aspect mẫu, abstract pointcuts và precedence của concrete aspects.
- [Eclipse AspectJ Programming Guide — Advice](https://eclipse.dev/aspectj/doc/released/progguide/semantics-advice.html): before, after, around, exception handling và precedence.
- [Eclipse AspectJ Development Guide — Concrete Aspects](https://eclipse.dev/aspectj/doc/latest/devguide/ltw.html): một hình thức biến abstract pointcut thành concrete aspect qua cấu hình deploy, cùng giới hạn riêng của cơ chế này.
- [Java SE 17 — Language Specification](https://docs.oracle.com/javase/specs/jls/se17/html/index.html): abstract class, inheritance, method overriding và exception semantics dùng trong ví dụ Java thuần.

Khi triển khai production, cần đọc tài liệu **đúng phiên bản compiler/weaver và runtime** thực tế, rồi kiểm chứng bằng build/test trong môi trường tương tự deployment.

## 33. Kết luận

**Aspect trừu tượng là một cách tái sử dụng hành vi cắt ngang khi mô hình AOP hỗ trợ kế thừa/abstraction ở cấp aspect.** Base aspect giữ advice và helper ổn định; concrete aspect định nghĩa pointcut/hook phù hợp miền nghiệp vụ. Mục tiêu là tránh trùng lặp mà không trộn lẫn những phạm vi có hợp đồng khác nhau.

Có ba điều phải giữ rõ:

1. **Tái sử dụng hành vi** không đồng nghĩa **mọi concrete aspect đều chọn cùng join points**.
2. **Một base advice** không đồng nghĩa **mỗi join point chỉ nhận advice một lần** khi nhiều concrete aspects cùng match.
3. **Abstract aspect ở ngôn ngữ AOP** khác **abstract class/interceptor wrapper Java**: cơ chế áp dụng, lifecycle và weaving boundary khác nhau.

Một thiết kế tốt phải nêu rõ **scope, lifecycle, precedence, extension contract và error semantics**; dùng tests dương/âm cho từng concrete aspect và tests tổng hợp khi có nhiều aspect. Nếu engine không hỗ trợ abstract aspects, hãy dùng **composition, strategy hoặc template interceptor** mà vẫn trung thực về khả năng can thiệp thực tế.

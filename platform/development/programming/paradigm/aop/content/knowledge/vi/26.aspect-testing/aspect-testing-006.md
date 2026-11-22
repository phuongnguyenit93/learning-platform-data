# Kiểm thử lời gọi nội bộ, đường gọi trực tiếp và mã không được dệt trong AOP

## 1. Mục tiêu: kiểm chứng advice thật sự có mặt trên đường chạy

Trong **Aspect-Oriented Programming (AOP)**, *pointcut* chọn tập *join point* còn *advice* thực hiện hành vi cắt ngang như logging, tracing, đo lường, kiểm soát truy cập hoặc transaction. Tuy nhiên, **pointcut được khai báo không có nghĩa advice chắc chắn chạy**: đường gọi thực tế có thể không đi qua proxy, bytecode chứa join point chưa được dệt, hoặc điều kiện pointcut không khớp.

Bài học tập trung vào ba đường dễ bị bỏ sót:

1. **Lời gọi nội bộ (`self-invocation`):** một method của target gọi method khác của chính nó, ví dụ `this.inner()`.
2. **Đường gọi trực tiếp (`direct call`):** caller giữ tham chiếu target gốc và gọi không qua proxy/wrapper mong muốn.
3. **Mã không được dệt (`non-woven code`):** classfile hoặc vị trí gọi chưa được biến đổi bằng compile-time, post-compile hay load-time weaving.

Cần trả lời **ba câu hỏi độc lập** trước khi kết luận kiểm thử pass:

- **Pointcut có chọn đúng join point không?** Kiểm tra `call` so với `execution`, chữ ký, overload, annotation, phạm vi package, điều kiện động.
- **Cơ chế gắn advice có áp dụng tại đó không?** Với proxy, object thực tế có đi qua proxy không? Với bytecode weaving, phần thân method hoặc call site cần thiết đã được weave chưa?
- **Hành vi runtime có đúng không?** Advice chạy 0, 1 hay nhiều lần; original method được gọi bao nhiêu lần; return, exception, side effect và ngữ cảnh có được bảo toàn?

Đây là nội dung AOP cơ bản/nâng cao nói chung. Ví dụ bên dưới dùng **JDK dynamic proxy** và **AspectJ code-style** để phân biệt hai cơ chế, không coi quy tắc một cơ chế là quy tắc phổ quát cho tất cả AOP.

## 2. Ba khái niệm: pointcut match, interception và hợp đồng runtime

Một lời gọi có thể được mô hình hóa:

~~~text
caller
  -> đường gọi / call site
  -> (proxy hoặc bytecode đã weave nếu có)
  -> advice được chọn
  -> thao tác nghiệp vụ
~~~

**Pointcut match** nói một join point thỏa điều kiện chọn. **Interception** nói cơ chế AOP thật sự nằm trên đường thực thi. **Advice contract** nói advice được phép quan sát, short-circuit, retry, biến đổi lỗi hoặc quản lý tài nguyên thế nào.

Ví dụ một pointcut chọn mọi method tên `charge`, nhưng một job nền gọi trực tiếp implementation thay vì đi qua proxy. Logic charge vẫn có thể chạy, nhưng advice audit/authorization được áp tại proxy **không chạy**. Ngược lại, một class đã được weave nhưng không thuộc pointcut thì advice cũng không chạy. Tương tự, advice có thể chạy nhưng return sớm trước khi gọi nghiệp vụ; chỉ kiểm tra log “advice entered” vẫn chưa đủ.

Đối với chính sách bắt buộc như quyền truy cập hoặc audit, **thiếu advice có thể là lỗi an toàn** chứ không chỉ mất telemetry. Bài kiểm thử phải chứng minh mọi entrypoint tới tài nguyên nhạy cảm đều có cơ chế cưỡng chế phù hợp, có thể gồm kiểm soát bổ sung tại data/resource boundary.

## 3. Proxy và lời gọi nội bộ

### 3.1 Proxy chặn lời gọi nào?

Một proxy là đối tượng trung gian:

~~~text
Client -> ServiceProxy -> advice -> ServiceTarget.outer()
~~~

Giả sử `ServiceTarget.outer()` gọi:

~~~java
String outer(String value) {
    return "outer(" + inner(value) + ")";
}
~~~

Nếu đây là cơ chế **JDK dynamic proxy** chuyển tiếp method interface sang target, `inner(value)` được gọi trên `this` chính là target, **không tự quay lại invocation handler của proxy**.

~~~text
Client
  -> Proxy.outer()       [advice: outer]
       -> Target.outer()
            -> this.inner()  [gọi trực tiếp Target.inner]
~~~

Lời gọi `Proxy.inner()` từ caller bên ngoài có thể bị advice chặn, nhưng `Target.outer() -> this.inner()` không tạo thêm một interception của proxy. Đây là đặc điểm đường tham chiếu, không phải do tên `inner`.

### 3.2 Khi direct call bỏ qua proxy

Nếu caller giữ cả hai object:

~~~java
Service proxy = createProxy(target);
proxy.operation();    // có thể đi qua advice
target.operation();   // không qua proxy
~~~

Đây là mã minh họa, không độc lập. Tương tự, `new ServiceImpl()` tạo đối tượng chưa được bọc; lời gọi trên nó không chịu advice của proxy. Việc một class *có thể* được proxy không có nghĩa mọi instance và mọi đường gọi đã được proxy.

**Lưu ý giới hạn:** Các kỹ thuật proxy hoặc weaving khác có thể hỗ trợ bề mặt interception khác nhau. Không phát biểu “mọi self-invocation đều bỏ qua AOP”; điều đúng ở đây là **lời gọi nội bộ trên target bỏ qua handler của JDK dynamic proxy**.

## 4. Ví dụ Java 17+ chạy độc lập: ba đường gọi

Ví dụ sau tự dựng JDK dynamic proxy, lưu các method **thật sự đi qua handler** và so sánh với việc gọi trực tiếp. Không cần dependency ngoài JDK.

**Tệp `ProxyPathTest.java`:**

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public class ProxyPathTest {
    public interface Service {
        String outer(String value);
        String inner(String value);
    }

    public static final class ServiceImpl implements Service {
        @Override
        public String outer(String value) {
            return "outer(" + inner(value) + ")";
        }

        @Override
        public String inner(String value) {
            return "inner(" + value + ")";
        }
    }

    public static final class CountingAdvice implements InvocationHandler {
        private final Service target;
        private final List<String> calls;

        CountingAdvice(Service target, List<String> calls) {
            this.target = target;
            this.calls = calls;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            if (method.getDeclaringClass() == Object.class) {
                try {
                    return method.invoke(target, args);
                } catch (InvocationTargetException error) {
                    throw error.getCause();
                }
            }

            calls.add(method.getName());
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException error) {
                throw error.getCause();
            }
        }
    }

    static Service wrapped(Service target, List<String> calls) {
        return (Service) Proxy.newProxyInstance(
            Service.class.getClassLoader(),
            new Class<?>[] { Service.class },
            new CountingAdvice(target, calls)
        );
    }

    public static void main(String[] args) {
        ServiceImpl target = new ServiceImpl();
        List<String> calls = new ArrayList<>();
        Service proxy = wrapped(target, calls);

        System.out.println("through-proxy=" + proxy.outer("A"));
        System.out.println("observed=" + calls);

        System.out.println("explicit-proxy=" + proxy.inner("B"));
        System.out.println("observed=" + calls);

        System.out.println("direct-target=" + target.inner("C"));
        System.out.println("observed=" + calls);

        Service unwrapped = new ServiceImpl();
        System.out.println("unwrapped=" + unwrapped.outer("D"));
        System.out.println("observed=" + calls);

        if (!calls.equals(List.of("outer", "inner"))) {
            throw new AssertionError("Incorrect proxy interception");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ProxyPathTest.java
java ProxyPathTest
~~~

**Stdout xác định:**

~~~text
through-proxy=outer(inner(A))
observed=[outer]
explicit-proxy=inner(B)
observed=[outer, inner]
direct-target=inner(C)
observed=[outer, inner]
unwrapped=outer(inner(D))
observed=[outer, inner]
~~~

**Giải thích từng lần:**

- `proxy.outer("A")` đi qua handler nên ghi `outer`. `ServiceImpl.outer()` gọi `this.inner()` trực tiếp trên target, vì thế handler **không** ghi một lần `inner` cho lời gọi nội bộ.
- `proxy.inner("B")` được caller gọi trực tiếp **trên proxy**, nên ghi thêm `inner`.
- `target.inner("C")` gọi đối tượng gốc, không làm thay đổi danh sách lần interception.
- `unwrapped.outer("D")` không qua proxy từ đầu; bản thân `outer` và `inner` đều không được handler trên ghi nhận.
- Kiểm tra `List.of("outer", "inner")` chứng minh **số lần và thứ tự advice** mong đợi, không chỉ kết quả nghiệp vụ.

Mã dùng một `ArrayList` trong thử nghiệm tuần tự. Nếu nhiều thread cùng gọi proxy, recorder cần cơ chế đồng bộ an toàn và phải đợi tất cả lần chạy hoàn tất trước khi đọc kết quả.

## 5. Bytecode weaving khác proxy: phân biệt `call` và `execution`

Ở AspectJ, weaving biến đổi bytecode tại join point phù hợp. Hai loại quan trọng:

- **`execution(void Worker.inner())`:** chọn lúc vào *thân phương thức* `Worker.inner()`. Muốn advice tại execution chạy, classfile chứa method `Worker.inner` phải được weave đúng.
- **`call(void Worker.inner())`:** chọn tại *vị trí gọi* `worker.inner()`. Muốn advice tại call chạy, bytecode chứa **call site** phải được weave.

Đây là khác biệt quyết định khi kiểm thử mã không được dệt.

| Tình huống | `execution` advice của target | `call` advice tại caller |
| --- | --- | --- |
| Caller woven, target woven, pointcut match | Có thể chạy | Có thể chạy |
| Caller **không** woven, target woven | Vẫn có thể chạy | Không chạy tại call site chưa woven |
| Caller woven, target **không** woven | Không chạy ở method execution chưa woven | Vẫn có thể chạy tại call site woven |
| Caller và target đều chưa woven | Không có advice do weaving ở hai vị trí | Không có advice tại call site |
| Pointcut không match | Không chạy dù target woven | Không chạy dù caller woven |

“Có thể” còn phụ thuộc điều kiện pointcut/runtime và phạm vi weaving. **Target chưa weave không đồng nghĩa mọi `call` advice đều mất**, và **caller chưa weave không đồng nghĩa `execution` advice của target woven bị bỏ qua**.

### Self-invocation với execution đã weave

Nếu `outer()` gọi `this.inner()`, nhưng thân `inner()` đã được weave bằng một `execution` advice, thì khi JVM thực thi `inner()`, advice **vẫn có thể chạy** dù đây là lời gọi nội bộ. Vì vậy không lấy kết luận của proxy thuần áp thẳng sang AspectJ weaving.

### Self-invocation với call đã weave

Một lời gọi `this.inner()` bên trong `outer()` cũng có một call site. Nếu bytecode chứa call site ấy được weave và pointcut match, `call` advice có thể chạy; nếu call site không weave thì không. Điều kiện quan trọng là **vị trí lệnh gọi**, không chỉ vị trí implementation.

## 6. Ví dụ AspectJ: lời gọi nội bộ vẫn kích hoạt execution advice

Ví dụ này gồm một tệp Java và một tệp AspectJ code-style. Tác vụ `outer` gọi `inner` trong cùng một object; aspect chọn **method execution** của `inner`.

**Tệp `WovenSelfCallDemo.java`:**

~~~java
public class WovenSelfCallDemo {
    public static void main(String[] args) {
        Worker worker = new Worker();
        worker.outer();
    }
}

class Worker {
    void outer() {
        inner();
    }

    void inner() {
        System.out.println("body inner");
    }
}
~~~

**Tệp `WovenSelfCallAspect.aj`:**

~~~java
public aspect WovenSelfCallAspect {
    before(): execution(void Worker.inner()) {
        System.out.println("advice inner");
    }
}
~~~

Sử dụng JDK 17 và AspectJ compiler `ajc` tương thích Java 17, cùng `aspectjrt.jar`. Hai tệp nằm trong cùng một thư mục:

~~~bash
mkdir -p out
ajc -17 -d out WovenSelfCallDemo.java WovenSelfCallAspect.aj
java -cp "out:aspectjrt.jar" WovenSelfCallDemo
~~~

Nếu môi trường chưa đưa runtime vào classpath khi compile, thêm `-classpath aspectjrt.jar` vào lệnh `ajc` theo toolchain đang dùng. Trên Windows, dấu phân tách classpath dùng `;` thay `:`.

**Stdout khi weave thành công:**

~~~text
advice inner
body inner
~~~

Lệnh gọi `worker.outer()` đi vào `inner()` qua lời gọi nội bộ, nhưng vì **body `Worker.inner` đã weave** nên advice xuất hiện trước thông điệp nghiệp vụ.

### Đối chứng với bản classfile không được weave

Biên dịch **chỉ tệp Java thường** vào thư mục khác:

~~~bash
mkdir -p plain
javac -d plain WovenSelfCallDemo.java
java -cp plain WovenSelfCallDemo
~~~

**Stdout của bản plain:**

~~~text
body inner
~~~

Kết quả nghiệp vụ giống nhau nhưng advice không hiện diện. Hai bản build riêng giúp tránh nhầm classfile stale: không nên compile `javac` đè lên cùng output đã weave rồi khẳng định đó là kiểm thử đối chứng hợp lệ.

**Phân biệt công cụ:** `.aj` với cú pháp `aspect` không biên dịch bằng `javac` thuần. Ví dụ Java 17 ở phần 4 chạy bằng JDK đơn thuần, còn ví dụ này cần **trình biên dịch và runtime AspectJ**. Nếu build có lỗi hoặc classpath không đúng, không được giả định chương trình đã weave.

## 7. Lập kế hoạch test theo ba tầng

### Tầng 1: pointcut coverage

Ghi danh mục các operation:

| Operation / entrypoint | Advice bắt buộc? | Join point muốn kiểm tra | Điều cần loại trừ |
| --- | --- | --- | --- |
| Lệnh ghi dữ liệu | Authorization và audit | Method execution tại boundary được bảo vệ | Helper thuần túy |
| Lệnh đọc dữ liệu nhạy cảm | Authorization | Boundary/resource access | Endpoint công khai đã khai báo |
| Call tới resource bên ngoài | Metrics/circuit breaker theo thiết kế | Call site hoặc execution cụ thể | Client nội bộ ngoài phạm vi |
| Job nền thay đổi dữ liệu | Policy bắt buộc | Entry job và đường dữ liệu | Không bỏ sót vì không qua API |
| Metrics/exporter code | Thường loại trừ | Không để tự instrument đệ quy | Tránh recursion |

Từ danh mục này tính:
- **False negative:** điểm *phải* có advice nhưng không match/chưa được intercept.
- **False positive:** điểm *không nên* có advice nhưng bị áp dụng, gây overhead hoặc thay đổi semantics.

Đừng dùng tiền tố tên method làm bằng chứng quyền. Quy tắc truy cập phải dựa vào principal đã xác thực, action, resource và context thật; pointcut chỉ là phương tiện gắn policy.

### Tầng 2: wiring và weaving

Với proxy cần xác minh:

- Entry point nhận **proxy hay target**? Có object nào tạo thẳng bằng `new`?
- Handler chặn đúng method interface/chữ ký không?
- Có đường self-invocation, callback hoặc job dùng target gốc không?
- Có nhiều proxy lồng nhau gây chạy advice nhiều lần không?

Với bytecode weaving cần xác minh:

- Classfile nào thực sự được weave; class chứa call site hay method execution?
- Build dùng compile-time, binary/post-compile hay load-time weaving?
- Include/exclude package/module/jar và điều kiện runtime có đúng không?
- Bytecode chạy thật có đến từ build output đã weave, hay build cache/Classpath chứa bản plain?
- Load-time transformer có hoạt động **trước** khi class đích được định nghĩa không?
- Classloader, module access, compiler và runtime có tương thích không?

### Tầng 3: runtime behavior

Ở mỗi test cần xác nhận:

- Advice thực thi **đúng số lần** (0/1/n theo hợp đồng).
- Original method được gọi đúng số lần; không tự thêm side effect.
- Return value và exception gốc được giữ nguyên nếu advice thuần quan sát.
- Advice được phép chặn truy cập thì business method không chạy khi bị deny.
- Khi lỗi, timeout, cancellation, resource được giải phóng đúng theo vòng đời.
- Thứ tự nhiều advice phù hợp hợp đồng: authorization, transaction, retry, audit, metrics có thể cho hành vi khác khi đổi order.

Có metadata đúng hoặc class proxy đúng kiểu **chưa đủ** nếu test không quan sát được hành vi.

## 8. Ma trận test cho đường gọi nội bộ và direct call

| Trường hợp | Cách gọi | Kỳ vọng trong JDK proxy minh họa |
| --- | --- | --- |
| Qua proxy | `proxy.inner("X")` | Handler ghi `inner` |
| Proxy tới outer | `proxy.outer("X")` | Handler ghi `outer` |
| Self-invocation | `outer -> this.inner` trong target | Không có interception **thêm** của `inner` trong handler |
| Direct target | `target.inner("X")` | Không có interception |
| Object chưa bọc | `new ServiceImpl().inner("X")` | Không có interception |
| Method ngoài interface | Caller trực tiếp gọi method chỉ có ở target | JDK proxy không tự cung cấp method đó |
| Reflection trên proxy | `Method.invoke(proxy, ...)` với interface method phù hợp | Có thể đi qua handler |
| Reflection trên target | `Method.invoke(target, ...)` | Bỏ qua handler proxy |
| Target ném exception | Proxy gọi target | Handler chuyển tiếp đúng lỗi gốc |
| Nhiều thread | Nhiều caller cùng proxy | Count đúng và state thread-safe nếu cần |
| Callback dùng target | Task giữ target gốc | Không bị handler proxy chặn |
| Callback dùng proxy | Task giữ proxy | Có thể bị handler chặn khi gọi method interface |

**Reflection không tự động có nghĩa bypass.** Điều quyết định là receiver thực của lời gọi và join point/cơ chế sử dụng. Với execution advice đã weave, reflection gọi vào target woven vẫn có thể kích hoạt advice ở execution.

Khi một test kiểm tra “direct call không có advice”, đó là mô tả bề mặt proxy. **Không được dùng test ấy làm bằng chứng mọi direct call đều an toàn** nếu policy yêu cầu mọi thao tác ghi nhạy cảm phải được kiểm soát; kiến trúc phải đóng đường bypass hoặc có kiểm soát bổ sung.

## 9. Kiểm thử mã không được dệt và chẩn đoán build

### 9.1 Compile-time, binary và load-time weaving

- **Compile-time weaving:** compiler xử lý source/aspect và tạo bytecode đã chứa advice.
- **Binary/post-compile weaving:** mã đã biên dịch được weave tiếp ở một bước build.
- **Load-time weaving:** bytecode được biến đổi khi class được nạp theo cấu hình loader/agent.

Một class được viết trong cùng project với aspect **không chứng minh đã weave**. Điều cần kiểm tra là bytecode mà JVM thật sự nạp.

### 9.2 Nguyên nhân phổ biến gây thiếu weaving

1. Một module được build bằng `javac` rồi đưa vào runtime mà không qua weaver.
2. Dependency JAR nằm ngoài phạm vi include, `inpath` hoặc loader phù hợp.
3. Refactor đổi tên package, method hoặc annotation khiến pointcut không còn match.
4. Load-time weaver khởi động **sau** thời điểm class đích đã được nạp.
5. Classloader khác không tham gia cùng cấu hình biến đổi.
6. Build cache chứa classfile cũ; classpath ưu tiên bản plain trước bản woven.
7. Bytecode version/JDK/compiler/runtime không tương thích.
8. Aspect không được đưa vào build hoặc không được đăng ký với runtime đúng cách.

### 9.3 Các bằng chứng nên thu thập

- Danh sách điểm weave/match do compiler/weaver cung cấp khi có hỗ trợ.
- Thông tin đường classpath, version JDK/compiler/weaver và checksum artifact được chạy.
- Một probe advice tại join point bắt buộc, xác nhận nó chạy trong **tích hợp thật**.
- Một negative test ở điểm excluded, xác nhận advice không chạy.
- Diff số join point trước/sau refactor.
- Phép đối chứng hai output directory woven/plain như trong ví dụ.

Đừng trộn hai bản build trong một thư mục, và đừng chỉ nhìn sự hiện diện của `.aj` hoặc annotation trong source để kết luận bytecode có advice.

## 10. Async, callback, thread và nguồn sự kiện

Một phương thức có thể trả `CompletionStage` hoặc `Future` rất nhanh rồi thực thi ở executor. Around advice bao quanh **lời gọi tạo stage** có thể kết thúc trước công việc thật. Bài test cần phân biệt:

- Advice có chạy ở method return stage không?
- Task nền gọi method trên proxy hay target?
- Context như danh tính xác thực, trace ID, deadline có được truyền sang thread khác đúng cách không?
- Nếu mục tiêu đo **completion**, callback được gắn vào terminal outcome đúng một lần chưa?
- Cancellation của future có đồng nghĩa công việc nền đã dừng hay chưa? Không tự giả định.

Với một publisher sự kiện, lời gọi tạo publisher chưa chắc tạo subscription hoặc phát phần tử. Một publisher có thể có nhiều subscriber, nhiều `onNext` và tín hiệu `onError`, `onComplete` hoặc `cancel`. Cần xác định đang kiểm thử lời gọi tạo publisher, từng subscription, hay vòng đời stream. Advice đo/ghi log không được tự subscribe thêm, thay đổi `request(n)` hoặc tạo queue vô hạn làm hỏng backpressure.

Nếu một callback chạy sau khi outer method trả về, cấu trúc call stack và control-flow pointcut của lời gọi ban đầu có thể không còn. Không coi `ThreadLocal` tự động lan qua executor.

## 11. Kiểm tra advice chạy nhưng sai thứ tự hoặc chạy lặp

Một test chỉ kiểm tra có log `before` vẫn chưa chứng minh advice đúng. Ví dụ:

~~~text
Metrics(Retry(Transaction(Operation)))
~~~

Khi metrics nằm ngoài retry, một request logic có thể được đo một lần bao gồm mọi attempt. Nếu metrics nằm trong retry:

~~~text
Retry(Metrics(Transaction(Operation)))
~~~

nó có thể đếm từng attempt riêng. Điều tương tự xảy ra khi audit nằm trong hoặc ngoài cache/authorization: một nhánh short-circuit có thể ngăn các advice bên trong chạy.

Bài test cần mô tả **outer → inner**, số lần gọi gốc, số lần advice và hành vi success/deny/error. Cũng cần loại trừ code infrastructure khỏi pointcut để tránh advice gọi logger rồi logger lại bị advice, tạo đệ quy hoặc nhân đôi telemetry.

Nếu một request qua API → service → repository, ba join point có thể đều được instrument; đó là ba interceptions, **không phải** ba request người dùng. Metrics phải đặt tên theo đơn vị thực.

## 12. Mẫu kiểm thử âm tính và bất biến quan trọng

**Positive test:** một thao tác bắt buộc đi qua entrypoint production, advice được ghi nhận đúng lần, side effect phù hợp.

**Negative test:** một thao tác không thuộc scope đi qua cùng entrypoint, advice không được ghi nhận.

**Bypass test:** thử gọi trực tiếp target/đường nội bộ; nếu cơ chế cho phép bỏ qua policy bắt buộc, test phải phát hiện lỗ hổng kiến trúc thay vì coi bypass là ngoại lệ an toàn.

**Unwoven test:** chạy artifact plain đối chứng với woven; quan sát sự khác biệt đã dự kiến.

Các bất biến tốt:

1. Khi bị authorization deny, số lần business method chạy là **0**, không chỉ “có exception”.
2. Khi được allow và advice quan sát thuần túy, original method chạy **đúng một lần** và caller nhận giá trị/lỗi gốc.
3. Mỗi join point được chọn nhận số lần advice theo hợp đồng, không thiếu/nhân đôi ngoài chủ ý.
4. Khi thay đổi tên/package/overload, danh mục điểm bắt buộc vẫn được kiểm tra.
5. Khi có exception, advice vẫn ghi nhận đúng outcome và không che lỗi nghiệp vụ.
6. Khi async hoàn tất, resource/context được giải phóng và event được ghi một lần.
7. Khi không weave hoặc không đi qua proxy, bài test chẩn đoán trạng thái đó và không báo thành công giả.

## 13. Cách điều tra khi advice không xuất hiện

Một trình tự ngắn giúp tìm đúng nguồn lỗi:

1. **Kiểm tra join point:** method thực tế là call hay execution? Tên, chữ ký, annotation, modifier và điều kiện động khớp không?
2. **Kiểm tra receiver và đường gọi:** proxy hay target? Self-invocation? Callback giữ object nào?
3. **Kiểm tra wiring:** đã khởi tạo proxy đúng nơi? Đường job/message consumer có đi qua nó không?
4. **Kiểm tra weaving:** class chứa call site hoặc execution body có nằm trong build/loader đã weave không?
5. **Kiểm tra artifact:** JVM chạy classfile nào, đúng output directory/classpath/classloader/version không?
6. **Kiểm tra advice semantics:** advice bị pointcut condition loại ra, bị một advice ngoài short-circuit hoặc ném lỗi trước khi recorder chạy không?
7. **Kiểm tra công cụ đo test:** recorder có bị reset, sampling, async flush hay race làm mất event không?

Nếu pointcut metadata trông đúng nhưng runtime không chạy, nghiêng về **interception/wiring/weaving**. Nếu advice có chạy mà business method không chạy như kỳ vọng, nghiêng về **contract/order**. Nếu business chạy mà chính sách bắt buộc không chạy, cần xử lý như một **đường bypass**.

## 14. Lưu ý về loại phương thức và annotation

JDK dynamic proxy hoạt động qua **interface method** được khai báo. Nó không trực tiếp chặn constructor, private method, static method hoặc method riêng của implementation chỉ vì chúng tồn tại trên target.

Bytecode weaving có thể hỗ trợ thêm các loại join point, nhưng cần xác minh kỹ thuật và include/exclude của công cụ cụ thể. `final`, generic bridge method, overload và default method còn có thể ảnh hưởng cách matcher tra chữ ký hoặc metadata.

Annotation trên interface method không nhất thiết xuất hiện trong reflection của implementation method theo cùng cách, và ngược lại. Bài test phải kiểm tra **Method thực tế mà handler/weaver nhìn thấy**, thay vì khẳng định một annotation được “kế thừa” theo suy đoán.

Một phương thức `toString()` bị interceptor hoặc logger gọi có thể mang dữ liệu nhạy cảm; không vô tình instrument toàn bộ object method mà không có chính sách rõ.

## 15. Chiến lược test không làm mất tính ổn định

Để test nhanh và tin cậy:

- Dùng **fake advice recorder** hoặc counter thay cho log mạng thật. Tái khởi tạo recorder giữa các test.
- Với nhiều thread, dùng `CountDownLatch`, `Future` hoặc barrier để điều phối; không chỉ dựa vào `Thread.sleep()`.
- Chỉ đọc counter sau khi các tác vụ liên quan kết thúc, hoặc dùng snapshot đồng bộ khi cần.
- Tách riêng test business unit khỏi **integration test đi qua cơ chế AOP thật**.
- Tách classfile output cho bản woven và plain, giữ thông tin compiler/weaver/runtime.
- Viết test trường hợp **không match** cũng như **có match**.
- Với aspect bắt buộc về bảo mật/audit, dùng coverage assertion trên danh mục operation thay vì chỉ smoke test một method.
- Chạy regression sau thay đổi pointcut, tên package, chữ ký, cách tạo object, thứ tự advice hoặc đường async.
- Đo overhead của probe/instrumentation trên hot path khi cần; recorder rất nặng có thể làm thay đổi p95/p99 và điều kiện race.

Không dùng số lần log từ hệ thống quan sát vốn có sampling để khẳng định số advice invocation chính xác. Khi cần test logic, một recorder có thể kiểm soát/đếm deterministic đáng tin hơn.

## 16. Checklist trước khi hoàn tất bài kiểm thử AOP

- [ ] Xác định cơ chế: proxy hay weaving, compile-time/post-compile/load-time.
- [ ] Xác định join point: call site hay execution body.
- [ ] Có test lời gọi qua proxy, self-invocation và direct target.
- [ ] Có test object không được bao bọc hoặc đường mới tạo bằng `new`.
- [ ] Có test woven vs plain artifact và không trộn output directory.
- [ ] Ghi danh sách operation **bắt buộc** advice, phát hiện thiếu coverage.
- [ ] Kiểm tra cả join point không được áp dụng advice.
- [ ] Đếm số lần advice và số lần original method thật sự chạy.
- [ ] Kiểm tra return, exception, side effects, thứ tự advice và nhánh short-circuit.
- [ ] Kiểm tra callback, thread pool, async completion/cancellation nếu có.
- [ ] Kiểm tra reflection đúng receiver proxy hay target.
- [ ] Xem xét classloader, build cache, include/exclude, overload và metadata.
- [ ] Phân biệt thiếu telemetry tùy chọn với thiếu kiểm soát bắt buộc.
- [ ] Regression khi refactor và thay đổi toolchain/wiring.
- [ ] Đã tài liệu hóa đường bypass được hỗ trợ và biện pháp bảo vệ bổ sung.

## 17. Kết luận

**Đường gọi quyết định advice có chạy hay không.** Với JDK dynamic proxy, lời gọi nội bộ trên target, gọi thẳng target và object không được bọc bỏ qua invocation handler. Với bytecode weaving, lời gọi nội bộ vẫn có thể nhận `execution` advice nếu thân method đã weave; `call` advice lại phụ thuộc call site đã weave. Bởi vậy kiểm thử cần phân biệt **pointcut match**, **cơ chế gắn advice** và **hành vi runtime**, có đối chứng woven/plain và proxy/direct, cùng kiểm tra số lần gọi và side effect thực tế. Với audit, authorization hoặc transaction bắt buộc, **không có advice phải được phát hiện như một lỗi bao phủ**, không được coi là tình huống vô hại chỉ vì business method vẫn trả kết quả đúng.
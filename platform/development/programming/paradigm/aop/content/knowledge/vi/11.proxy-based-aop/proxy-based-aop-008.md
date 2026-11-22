# Khác biệt về phạm vi can thiệp giữa proxy và biến đổi mã

## 1. Bài toán: một advice được khai báo nhưng không chạy ở mọi nơi

Trong **Aspect-Oriented Programming (AOP)**, **pointcut** chọn những *join point* mà hệ thống có thể can thiệp; **advice** là hành vi được thực thi tại những điểm được chọn. Tuy nhiên, từ “pointcut khớp một phương thức” tới “lần thực thi đó thật sự có advice” còn một điều kiện quan trọng: **cơ chế AOP phải nhìn thấy và can thiệp được đường thực thi ấy**.

Hai nhóm triển khai thường gặp có phạm vi khác nhau:

- **Proxy/interceptor:** caller gọi vào **một đối tượng trung gian**. Chỉ những lời gọi đi qua trung gian, thuộc những phương thức nó hỗ trợ, mới được xử lý.
- **Biến đổi mã (code/bytecode weaving/instrumentation):** công cụ bổ sung logic vào những điểm được chọn trong mã hoặc bytecode. Nếu một method execution thực sự đã được biến đổi, lời gọi vào method đó có thể kích hoạt advice **dù caller không đi qua một proxy ngoài**.

Vì vậy, cùng một ý định “ghi audit mỗi lần thực thi `process()`” có thể đem lại kết quả khác:

~~~text
Proxy ở ranh giới:
  caller -> proxy.process() -> target.process() -> audit chạy
  caller -> target.process()                 -> proxy audit KHÔNG chạy
  target -> this.process()                   -> proxy audit KHÔNG chạy

Giả sử đã woven đúng method execution process:
  caller -> process()                        -> advice trong execution chạy
  target -> this.process()                   -> advice trong execution chạy
~~~

Các dòng “đã woven” chỉ đúng **nếu loại join point ấy được engine hỗ trợ và class/method thực sự nằm trong phạm vi biến đổi**. Không được suy ra mọi công cụ weaving sẽ thấy mọi thao tác Java.

**Mục tiêu của bài:** nhận diện độ phủ theo đường gọi, phân biệt `call` và `execution`, hiểu self-invocation, phương thức `private/final/static`, constructor/field, giới hạn classloader/agent, và thiết kế kiểm thử để không nhầm **“có khai báo pointcut”** với **“được instrument thật”**.

## 2. Phân biệt rõ proxy, weaving và instrumentation

| Thành phần | Trách nhiệm | Điều kiện để can thiệp |
| --- | --- | --- |
| **JDK interface proxy** | Triển khai một interface, chuyển mỗi lời gọi trên proxy qua `InvocationHandler` | Caller dùng proxy; method thuộc interface mà proxy expose |
| **Subclass proxy** | Dùng subclass ghi đè những method được phép override | Lời gọi đi qua subclass instance và cơ chế dispatch phù hợp |
| **Compile-time weaving** | Kết hợp advice khi biên dịch | Source/class và join point được dệt vào artifact build |
| **Post-compile/binary weaving** | Sửa class/JAR đã biên dịch | Đúng artifact và bytecode được weaver xử lý |
| **Load-time weaving** | Biến đổi class khi JVM nạp/định nghĩa nó | Transformer/weaver có mặt đúng lúc và class được chọn |
| **Runtime retransformation** | Biến đổi lại class đã định nghĩa, nếu JVM/agent hỗ trợ | Phải thỏa capability và giới hạn thay đổi class |
| **Interceptor chain** | Tập handler bao quanh một lời gọi đi qua một ranh giới | Đường gọi nằm trong chuỗi interceptors được thiết lập |

**Proxy có thể triển khai hành vi AOP mà không sửa bytecode của target.** Vì thế “AOP qua proxy” không nên bị gọi bừa là “đã dệt bytecode vào class”. Ngược lại, một class có bytecode được biến đổi vẫn có thể được gọi trực tiếp mà advice ở method execution chạy đúng, không cần proxy như điểm vào bắt buộc.

**Thời điểm kết hợp** và **phạm vi pointcut** là hai trục độc lập: weaving trong build không tự cho phép can thiệp mọi join point; dùng proxy lúc runtime cũng không tự giới hạn advice chỉ ở kiểu `before` — proxy có thể bao quanh kết quả và ngoại lệ của những lời gọi nó nhìn thấy.

## 3. Đơn vị cốt lõi: lời gọi qua proxy hay method execution thật?

Giả sử:

~~~java
interface Service {
    void save();
}

class ServiceCore implements Service {
    public void save() { /* business logic */ }
}
~~~

Đây chỉ là đoạn khai báo minh họa, không phải chương trình Java độc lập.

Nếu `Service proxy = makeProxy(new ServiceCore())` thì:

- `proxy.save()` đi qua lớp proxy và có thể kích hoạt handler.
- `new ServiceCore().save()` đi trực tiếp vào target khác; proxy không nhìn thấy.
- `core.save()` với một tham chiếu giữ chính target bên trong proxy cũng bỏ qua handler.
- Nếu `save()` từ chính `ServiceCore` gọi `this.save()` ở một phương thức khác, đường gọi nội bộ thường không đi qua proxy bên ngoài.

Ngược lại, nếu một **execution join point của `ServiceCore.save()` đã được woven vào bytecode**, thì lần nào JVM đi vào thân `save()` cũng có thể kích hoạt đoạn đã chèn, kể cả khi caller dùng tham chiếu trực tiếp hay gọi `this.save()`.

**Không đánh đồng:** “proxy chặn lời gọi vào một interface method” với “ngôn ngữ AOP chọn mọi `method call join point`”. JDK `InvocationHandler` đứng ở **ranh giới lời gọi đi qua proxy**, còn một bytecode weaver có thể biểu đạt `call` tại từng vị trí gọi hoặc `execution` trong thân callee, tùy mô hình của công cụ.

## 4. Bảng độ phủ so sánh

| Tình huống | Interface proxy điển hình | Subclass proxy điển hình | Bytecode weaving khi hỗ trợ điểm đó |
| --- | --- | --- | --- |
| Gọi public method qua proxy | Có thể intercept | Có thể intercept nếu method override hợp lệ | Có thể, nếu callee/call site đã woven |
| Gọi trực tiếp target bỏ qua proxy | Không qua handler proxy | Không qua instance subclass proxy | Có thể tại execution đã woven |
| `this.otherMethod()` bên trong target | Thường bypass proxy ngoài | Có thể khác tùy thiết kế subclass và dispatch; không khái quát mọi trường hợp | Có thể tại execution/call đã woven |
| Private method | Không là public interface method để JDK proxy chặn trực tiếp | Không override được private method | Có thể nếu pointcut/weaver hỗ trợ |
| Final instance method | **Có thể intercept** lời gọi qua interface proxy | Không override final method | Có thể instrument body/call site nếu engine hỗ trợ |
| Static method | Không có dispatch instance qua interface proxy | Không override method static | Có thể với engine hỗ trợ static execution/call |
| Constructor execution | Không phải lời gọi method qua proxy đã tồn tại | Không tương đương một method override | Có thể với engine hỗ trợ constructor join point |
| Field get/set trực tiếp | Không tự chặn field access | Không tự intercept field opcode | Có thể khi field join point được hỗ trợ |
| Một lệnh `throw` hoặc `catch` trong thân method | Handler có thể quan sát exception thoát khỏi method, không tự thấy từng `catch` | Tương tự ở ranh giới override | Phụ thuộc engine có loại join point tương ứng |
| Method trả `CompletableFuture` | Có thể thấy đối tượng Future được trả từ method qua proxy | Có thể ở method được override | Có thể thấy method return; không tự có task completion |
| Mã thuộc JDK/native hoặc thư viện ngoài | Chỉ API/đường gọi proxy expose | Phụ thuộc subclassing/access | Tùy quyền biến đổi, phạm vi và giới hạn JVM/tool |

Bảng thể hiện **khả năng**, không phải lời hứa mọi AOP engine sẽ cung cấp đủ. Với bytecode weaving, cần kiểm tra **mô hình join point, phạm vi class, classloader, module, quyền công cụ và thời điểm biến đổi**. Với proxy, phải biết caller thực tế có sử dụng proxy hay không.

### 4.1. “Final method proxy không chặn được” có luôn đúng?

Không. Một **subclass proxy** cần override target method, nên `final` cản việc override. Nhưng một **JDK interface proxy** đứng trước lời gọi trên interface: handler vẫn có thể chạy rồi gọi vào implementation mà method là `final`. Hai kỹ thuật đều được gọi là proxy nhưng hạn chế khác nhau.

### 4.2. “Private method không thể có advice” có luôn đúng?

Không. JDK interface proxy không intercept trực tiếp private method vì nó không thuộc interface public mà proxy expose. Song một **weaver có hỗ trợ bytecode execution join point** có thể chèn logic vào private method. Quyết định có thực sự chèn được còn phụ thuộc class và công cụ.

### 4.3. Constructor có kết quả trả về không?

Constructor là một loại điểm riêng với lifecycle khởi tạo đối tượng, không đơn thuần là một phương thức instance trả về object qua interface proxy. Một weaving model có thể định nghĩa constructor call/execution hoặc initialization; **không suy ra** từ việc proxy chặn `run()` rằng nó cũng chặn mọi `new Target()`.

## 5. Self-invocation: nguyên nhân phổ biến nhất của “advice biến mất”

Ví dụ minh họa:

~~~java
class InvoiceService {
    void submit() {
        validate();
        persist();
    }

    void validate() { /* logic */ }
    void persist() { /* logic */ }
}
~~~

Đây là mã minh họa không độc lập. Nếu caller gọi `proxy.submit()`, proxy ngoài có thể intercept `submit`. Nhưng `submit()` gọi `validate()` và `persist()` trên **`this` của target**. Trong mô hình wrapper bên ngoài, hai lời gọi đó không đi qua proxy nên những interceptor chỉ gắn trên method qua proxy có thể không chạy.

Ngược lại, nếu bytecode của `validate()` và `persist()` thực sự được woven ở **execution join point**, các lần gọi nội bộ vẫn có thể đi qua mã chèn.

### Giải pháp với proxy

- Đặt chính sách tại **ranh giới public API** thực sự đi qua proxy, nếu chính sách cho phép.
- Tổ chức lại các thao tác cần interception thành hợp đồng service/đối tượng khác và gọi qua **proxy được quản lý**, không qua tham chiếu target thô.
- Tránh dùng self-reference/proxy injection không minh bạch chỉ để “ép” advice chạy; dễ tạo vòng phụ thuộc và khó test.
- Nếu một chính sách bảo mật hoặc tính nhất quán bắt buộc không được phép bypass, cân nhắc thực thi bất biến ấy ngay trong domain boundary hoặc dùng cơ chế can thiệp có độ phủ được xác minh.

Điều không nên làm là giả định **mọi lời gọi nội bộ luôn bị bypass trong mọi kỹ thuật proxy**: subclass dispatch và những cơ chế proxy đặc biệt có thể khác. Hãy mô tả **chính xác wrapper, target instance và đường dispatch** được dùng.

## 6. Method call và method execution khác nhau ra sao?

Trong những mô hình AOP phân biệt hai loại join point:

- **Call join point:** một điểm **gọi** phương thức, gắn với call site của caller.
- **Execution join point:** một lần **thực thi thân** phương thức, gắn với callee.

Một method `Service.process()` có thể được gọi từ hai caller khác nhau:

~~~text
ControllerA ---- call site A ----+
                                  |
                                  v
                         execute Service.process()
                                  `
                                  |
ControllerB ---- call site B ----+
~~~

Nếu pointcut chọn **call sites**, việc dệt có thể cần áp dụng trên code caller tương ứng; nếu chọn **execution**, nó cần đặt tại thân implementation thực sự.

Hệ quả:

1. Bạn có thể kiểm soát code callee nhưng không kiểm soát mọi caller. Execution weaving tại callee có thể có độ phủ thích hợp hơn khi engine hỗ trợ.
2. Bạn có thể chỉ muốn can thiệp lời gọi từ một nhóm caller; một mô hình call join point có thể biểu đạt ngữ cảnh khác với việc bao mọi execution.
3. Nếu một đường đi gồm một call join point và một execution join point, hai advice khác nhau có thể cùng chạy **một cách hợp lệ**. Không kết luận double weaving chỉ vì có hai event.
4. Interface method declaration, method implementation và overload có thể làm bộ chọn ký hiệu/hàm khác nhau; kiểm tra chữ ký thực thay vì chỉ tên.

**JDK dynamic proxy trong ví dụ sau không phải một implementation của toàn bộ ngôn ngữ pointcut call/execution.** Nó chỉ chặn các lời gọi đến object proxy theo interface, nên đừng dùng nó để suy luận mọi tính năng của bytecode-based AOP.

## 7. Ví dụ Java 17 chạy được: thấy ranh giới proxy

Chương trình dùng Java Reflection và `java.lang.reflect.Proxy`:

- Interface `Service` có `work()` và `internally()`.
- `Target.work()` được khai báo **`final`** nhưng vẫn có thể được JDK proxy quan sát khi caller gọi qua interface proxy.
- `Target.internally()` dùng `this.work()`, bỏ qua handler của proxy ở **lời gọi `work` nội bộ**.
- `Target.helper()` là `private` và `Target.utility()` là `static`, không có method tương ứng được expose qua interface proxy.
- Constructor in `BODY constructor`; nó xảy ra trước khi proxy được tạo.
- Lần gọi trực tiếp `target.work()` không đi qua proxy.
- Nhánh target ném ngoại lệ được bóc khỏi `InvocationTargetException` để caller nhìn thấy đúng lỗi gốc.

**Ranh giới mô phỏng:** các dòng `BODY ...` là những câu lệnh `println` được **viết tay trong mã target** để chỉ ra chỗ thực thi. Chúng **không phải kết quả bytecode weaving**. Nếu một bytecode weaver thực sự chèn advice vào body/call site được hỗ trợ, nó có thể thực hiện những quan sát tương tự ở các điểm đã dệt.

Tạo file `AopCoverageDemo.java`:

~~~java
import java.lang.reflect.*;

public class AopCoverageDemo {
    interface Service { String work(String s); String internally(String s); }

    static final class Target implements Service {
        Target() {
            System.out.println("BODY constructor");
        }

        public final String work(String s) {
            System.out.println("BODY work");
            if (s.equals("bad")) {
                throw new IllegalArgumentException("invalid code");
            }
            return helper(s);
        }

        private String helper(String s) {
            System.out.println("BODY private");
            return "ok:" + s;
        }

        public String internally(String s) {
            System.out.println("BODY internally");
            return this.work(s);
        }

        static void utility() {
            System.out.println("BODY static");
        }
    }

    static Object dispatch(Service target, Method m, Object[] args)
            throws Throwable {
        try {
            return m.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    static Service wrap(Service target) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[]{Service.class},
                (p, m, args) -> {
                    if (!m.getName().equals("work")) {
                        return dispatch(target, m, args);
                    }

                    System.out.println("PROXY before");
                    try {
                        Object result = dispatch(target, m, args);
                        System.out.println("PROXY after");
                        return result;
                    } catch (Throwable error) {
                        System.out.println("PROXY throwing "
                                + error.getClass().getSimpleName());
                        throw error;
                    }
                });
    }

    public static void main(String[] args) {
        Target target = new Target();
        Service proxy = wrap(target);

        System.out.println("CALLER " + proxy.work("A"));
        System.out.println("CALLER " + proxy.internally("B"));
        System.out.println("CALLER " + target.work("C"));
        Target.utility();

        try {
            proxy.work("bad");
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }
    }
}
~~~

Biên dịch với target Java 17 và chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 AopCoverageDemo.java
java AopCoverageDemo
~~~

Đầu ra đã được kiểm chứng bằng trình biên dịch Java với `--release 17` và chạy thực:

~~~text
BODY constructor
PROXY before
BODY work
BODY private
PROXY after
CALLER ok:A
BODY internally
BODY work
BODY private
CALLER ok:B
BODY work
BODY private
CALLER ok:C
BODY static
PROXY before
BODY work
PROXY throwing IllegalArgumentException
CALLER invalid code
~~~

### 7.1. Lời gọi `proxy.work("A")`

Lời gọi đi vào `InvocationHandler`. Handler in `PROXY before`, chuyển tiếp tới `Target.work`, target in `BODY work` và `BODY private`, handler in `PROXY after`, cuối cùng caller nhận `ok:A`.

Dù implementation `work` là **`final`**, JDK interface proxy vẫn intercept vì proxy nhận **lời gọi qua interface**, không phải subclass override method `final` của `Target`.

### 7.2. Lời gọi `proxy.internally("B")`

Handler vẫn nhận lời gọi `internally`, nhưng bộ lọc của ví dụ chỉ ghi `PROXY` cho tên `work`. Sau khi chuyển tiếp tới `Target.internally`, target gọi `this.work("B")` **trực tiếp trên chính target**. Vì vậy có `BODY internally`, `BODY work` và `BODY private`, nhưng không có `PROXY before/after` của `work`.

Đây là **self-invocation bypass** ở proxy ngoài. Nếu `Target.work` đã được weaving tại execution, body instrumentation có thể chạy cho lời gọi này (tùy mô hình công cụ).

### 7.3. Lời gọi `target.work("C")`

Caller giữ tham chiếu `target` thật. Dù proxy `proxy` đã tồn tại, **việc tạo một proxy không tự sửa target**. `target.work("C")` đi thẳng vào `Target.work` nên có dòng `BODY` nhưng không có dòng `PROXY`.

### 7.4. `Target.utility()` và constructor

Constructor của `Target` chạy khi gọi `new Target()`, trước lúc `wrap(target)` trả proxy. Method `static utility()` được gọi qua class, không qua interface proxy; chương trình chỉ in marker `BODY static` viết tay.

Một weaver có hỗ trợ constructor/static join points **có thể** thêm behavior ở những nơi đó. Nhưng ví dụ không chứng minh mọi weaver đều làm được, và không thể lấy một handler method trên interface để thay thế sự hỗ trợ constructor/field join point.

### 7.5. `proxy.work("bad")` và ngoại lệ

Handler in `PROXY before`, target in `BODY work` rồi ném `IllegalArgumentException`. Reflection bọc ngoại lệ trong `InvocationTargetException`; `dispatch` bóc `getCause()` và ném lại. Handler in `PROXY throwing IllegalArgumentException`, caller bắt ngoại lệ nghiệp vụ gốc.

Quan sát chỉ khi **lời gọi đi qua proxy**. Một advice sau trả về bình thường không nên chạy ở nhánh này; một around wrapper có thể quan sát exceptional exit. Không được tự thay lỗi gốc chỉ vì bọc target qua Reflection.

## 8. Weaving thật có thể làm được gì hơn proxy?

Một bytecode weaver có thể biến đổi **class định nghĩa method** hoặc **call site** theo mô hình join point:

~~~text
Source / class bytes
       |
       v
Weaver matches selected join points
       |
       v
Woven class bytes:
  before original operation -> advice logic
  original operation
  on normal/exceptional exit -> advice logic
       |
       v
JVM executes woven code
~~~

Đây là **sơ đồ ý niệm**, không phải trình tự bytecode bắt buộc. Một engine có thể dùng helper method, jump, injected dispatch, synthetic members hoặc kỹ thuật khác để hiện thực advice.

Nếu `Target.work()` đã được dệt ở execution join point, mọi lần vào body của bản class **đã dệt** có thể tạo advice: qua proxy, qua lời gọi trực tiếp hoặc qua `this.work()`. Do đó độ phủ không phụ thuộc riêng object proxy.

Nhưng khả năng đó bị giới hạn bởi:

1. **Engine có định nghĩa loại join point không?** Một engine chỉ hỗ trợ method execution không tự có field access hoặc constructor call.
2. **Class có nằm trong phạm vi dệt không?** Thư viện ngoài, class sinh động hoặc các module riêng có thể không được xử lý.
3. **Công cụ có thể thay đổi bytecode hợp lệ không?** Bytecode verifier, classfile version, stack maps và giới hạn JVM rất quan trọng.
4. **Dệt được chạy đúng thời điểm không?** Với load-time, class đã nạp trước transformer có thể không nằm trong lần dệt.
5. **Có ràng buộc module/classloader không?** Class từ loader khác có thể bỏ qua agent policy.
6. **Native method hoặc runtime internals có giới hạn không?** Không suy luận sửa được thân phương thức không có Java bytecode.
7. **Có nhiều tầng instrumentation không?** Weaving cộng proxy có thể ghi sự kiện trùng nếu thiếu policy ownership.

Từ “weaving mạnh hơn proxy” nên được thay bằng nhận định cụ thể: **weaving có thể nhìn những loại join point/đường gọi mà proxy ngoài không thấy, nếu công cụ và môi trường thật sự hỗ trợ**. Đổi lại là chi phí build/deployment/compatibility và yêu cầu kiểm thử khác.

## 9. Dùng các modifier để xác định *vị trí* can thiệp

Một method `final` cấm **subclass override**, nhưng một interface proxy vẫn có thể intercept lời gọi **trước khi** chuyển tiếp đến implementation final; bytecode weaving có thể xử lý execution/call tương ứng nếu engine hỗ trợ.

Method `private` không được subclass override và không phải API của JDK interface proxy, nhưng một execution hook được dệt trong method private vẫn có thể chạy. Method `static` không dùng virtual instance dispatch để đi qua proxy, song call-site hoặc execution weaving có thể có khả năng riêng.

Đây không phải bảng xếp hạng công cụ. Khi thiếu advice, hãy ghi rõ **modifier → loại join point → ranh giới proxy hoặc class bytes đã weave → đường gọi thật**; việc biết một modifier đơn lẻ không chứng minh advice sẽ chạy hay không.

## 10. Constructor, field, exception handler: khác hẳn method wrapper

Ví dụ:

~~~java
class Counter {
    int value;

    Counter() { value = 0; }

    void increment() { value++; }
}
~~~

Đây là mã minh họa chưa có `main`. Có ba loại thao tác khác nhau:

- `new Counter()` và constructor initialization.
- `Counter.increment()` là method execution.
- `value++` gồm field read/write ở bytecode, nếu không bị tối ưu/biến đổi đặc biệt.

JDK interface proxy của một `CounterService` có thể quan sát method `increment()` **nếu caller đi qua proxy**, nhưng không tự nhìn từng opcode đọc/ghi `value`. Một weaver hỗ trợ field get/set join point có thể làm việc sâu hơn nếu class/call site trong phạm vi.

Tương tự, proxy handler có thể quan sát exception được **ném ra khỏi lời gọi mà nó bao**, nhưng không biết mọi lần có `throw` hoặc `catch` nằm sâu trong thân target. Một exception được ném rồi bắt **bên trong target** có thể không làm method kết thúc ngoại lệ từ góc nhìn proxy. Một weaving model có các điểm exception handler có thể cho quan sát khác, nếu có hỗ trợ.

Đừng dùng phương pháp intercept method để tuyên bố đã thực thi policy tại **mọi field mutation**. Nếu đó là yêu cầu nghiệp vụ bắt buộc, cần xây điểm enforcement tin cậy hoặc kiểm tra khả năng instrument đầy đủ.

## 11. Proxy identity, object graph và phạm vi thật

Không chỉ method modifier ảnh hưởng độ phủ, mà còn **tham chiếu nào được đưa tới caller**:

~~~text
Factory tạo:
  Target raw = new Target()
  Service proxy = wrap(raw)

Caller A giữ proxy -> có interception
Caller B giữ raw   -> không có interception qua proxy ấy
~~~

Một vài tình huống phải kiểm tra:

- **Dependency wiring:** lớp cần advice nhận proxy hay target?
- **Object creation ngoài factory:** người khác gọi `new Target()` và giữ raw reference?
- **Callback và lambda:** callback có giữ `this` của target hay giữ proxy?
- **Serialization/deserialization:** object được phục hồi có còn wrapper không?
- **Equals/hashCode/toString:** proxy có forwarding contract riêng hay không?
- **Dynamic dispatch:** class cast sang concrete implementation có hợp lệ với interface proxy không? Thường **không** vì proxy chỉ implements interfaces.
- **Subclass proxy:** có giới hạn constructor/final class/final method không?
- **Multiple proxies:** cùng policy có vô tình bọc hai lần, khiến advice chạy hai lần không?

Đối với một **advice chỉ quan sát**, tiêu chí tốt là giá trị trả về, loại ngoại lệ và số lần target chạy không đổi ngoài các sự kiện quan sát được. Nhưng một proxy dùng cho authorization/retry/cache có thể có chính sách thay đổi luồng; phải công bố rõ để kiểm thử.

## 12. Weaving và thời điểm class loading

**Compile-time hoặc binary weaving** xử lý class trước runtime, có thể kiểm tra artifact cuối trong pipeline. **Load-time weaving** biến đổi class khi nó đang được JVM định nghĩa và yêu cầu agent/weaver/config có mặt đúng lúc.

Với LTW:

~~~text
raw class bytes
       |
ClassLoader begins defining class
       |
Transformer / Weaver chooses class + join points
       |
transformed bytes (if applicable)
       |
JVM defines class
       |
future method executions may carry advice
~~~

Các lỗi phổ biến:

- Agent khởi động quá muộn: class đã được định nghĩa trước khi transformer xuất hiện.
- Sai classloader: cùng binary name nhưng object runtime thuộc loader khác.
- Pointcut đúng về cú pháp nhưng class ngoài exclude/include policy.
- Bytecode version, module access hoặc JVM verifier không chấp nhận transformation.
- Chỉ một số phương thức được biến đổi, nhưng test giả định toàn class đã được instrument.
- Có transformer khác chèn logic tương đương gây double instrumentation.

**Retransformation/redefinition** là khả năng riêng của JVM instrumentation. Không suy luận rằng gọi retransform nhiều lần sẽ luôn thêm một lớp advice, hoặc tháo agent sẽ hoàn nguyên class ngay lập tức. Phải tuân theo hợp đồng engine/JVM và kiểm thử bytes/behavior thực.

## 13. Method call vs execution: thêm góc nhìn theo artifact

Điểm `call` nằm ở **call site**; điểm `execution` nằm ở **callee**. Điều này ảnh hưởng khả năng áp dụng weaving khi code trải trên nhiều artifacts:

- Nếu chỉ được phép dệt **module callee**, một execution join point có thể dễ kiểm soát hơn những call sites ở các module caller không sửa được.
- Nếu mục tiêu chỉ là lời gọi từ một nhóm caller nhất định, một engine hỗ trợ call join points có thể biểu đạt chính sách chọn theo caller.
- Với proxy, caller không cần được bytecode-weave nhưng phải gọi qua **đúng proxy reference**.
- Một thư viện được load hai phiên bản từ hai classloaders có thể khiến chỉ một bản callee được weaving.
- Method overload, bridge/synthetic methods có thể làm pointcut chọn khác với điều người đọc chỉ nhìn source nghĩ tới.

**Lựa chọn đúng là lựa chọn dựa trên join point cần bao phủ**, không phải chọn phương pháp vì tên “weaving” nghe rộng hơn.

## 14. Generic bridge và synthetic methods

Java compiler có thể tạo **bridge method** do type erasure và covariant return. Một đường gọi có thể đi qua bridge rồi chuyển tới implementation.

Ví dụ:

~~~java
class Parent<T> {
    T value() { return null; }
}

class Child extends Parent<String> {
    @Override
    String value() { return "ok"; }
}
~~~

Đây là đoạn minh họa, không phải chương trình độc lập. Compiler có thể tạo bridge method trong `Child` để bảo toàn đa hình ở bytecode level. Nếu một weaver chọn **method executions** trên cả bridge và implementation, một logical API call có thể kích hoạt advice ở hai join points khác nhau, dù không hề có double weaving.

Với Reflection có thể kiểm tra `Method.isBridge()` và `Method.isSynthetic()` khi phù hợp. Nhưng không loại mọi synthetic method mù quáng: cần hiểu cách engine ánh xạ source pointcut sang bytecode và các đường caller thực sự đi qua.

Proxy handler nhận `Method` đại diện cho lời gọi qua interface; metadata này chưa chắc trùng với method implementation bên dưới ở mọi tình huống override/bridge. Cần test contract thay vì chỉ so tên.

## 15. Ngoại lệ, kết quả trả về và loại advice

Proxy có thể gắn hành vi `before`, `after returning`, `after throwing` hoặc `around` **ở ranh giới lời gọi mà nó thấy**. Bytecode weaving cũng có thể hỗ trợ những loại advice ấy trên tập join point lớn hơn.

Nhưng độ phủ không được đánh giá chỉ bằng việc có log `before`:

- **Normal return:** target trả `null`, `false` hoặc `Result.failure(...)` vẫn có thể là normal completion; after-returning có thể chạy nếu pointcut khớp.
- **Exceptional exit:** target ném ngoại lệ ra khỏi ranh giới, advice ở nhánh throwing/around có thể quan sát.
- **Target tự catch lỗi:** ở ranh giới proxy có thể chỉ thấy normal return, không có thông tin về exception nội bộ.
- **Advice tự ném lỗi:** caller có thể nhìn lỗi của advice thay vì lỗi target; cần chính sách fail-open/fail-closed rõ.
- **Around retry:** có thể gọi `proceed` nhiều lần khiến target thực thi nhiều lần; phải tách số advice entries và business invocations.
- **Async return:** một method trả `CompletableFuture` normal chưa chứng minh task bên trong đã hoàn tất; cả proxy lẫn method-execution weaving đều có thể chỉ thấy handle.

Nếu cần quan sát completion của tác vụ bất đồng bộ, phải gắn vào lifecycle của task/Future hoặc một điểm thích hợp khác, không giả định một after-returning của method có kết quả cuối.

## 16. Bảo mật: độ phủ không phải tính năng phụ

Hãy giả sử advice có nhiệm vụ kiểm tra quyền truy cập. Nếu chính sách chỉ chạy qua proxy, mọi đường dùng **target raw** có thể bypass chính sách đó. Dù code người gọi bình thường đều dùng proxy, một factory khác, bài test, extension hoặc callback có thể vô tình giữ raw reference.

Cần cân nhắc:

1. **Ranh giới tin cậy:** caller không tin cậy có thể tự tạo/giữ target không?
2. **Policy bắt buộc hay chỉ hỗ trợ:** metrics thiếu một số lời gọi có thể là hạn chế quan sát; kiểm quyền bị bypass có thể là lỗi bảo mật.
3. **Đường gọi nội bộ:** self-invocation có thể bỏ qua proxy; audit/enforcement có cần thấy nó không?
4. **Các method không expose qua proxy:** tác động dữ liệu có thể xảy ra ở `private`, `static`, constructor, field access?
5. **Fail-open/fail-closed:** khi engine hoặc policy không áp được, hệ thống xử lý thế nào?
6. **Version/config drift:** production có thực sự instrument class và đường gọi dự kiến không?

Không nên biến AOP thành cơ chế bảo vệ duy nhất cho những bất biến nghiệp vụ quan trọng nếu không thể chứng minh phạm vi áp dụng đầy đủ. Có thể kết hợp kiểm tra ngay trong domain/service boundary, database constraints và cơ chế authorization tại API đáng tin, tùy bài toán.

Weaving sâu hơn có thể giúp độ phủ nhưng cũng cần chẩn đoán **những lớp/điểm không dệt được**; không có “bảo đảm phủ 100%” mặc định từ một công cụ.

## 17. Hiệu năng và quan sát

So sánh hiệu năng không chỉ dựa vào “proxy hay bytecode”:

| Thành phần chi phí | Proxy | Bytecode weaving |
| --- | --- | --- |
| Khởi tạo | Tạo proxy, handler, metadata | Build-time transform hoặc load-time transform |
| Mỗi lời gọi | Dispatch qua wrapper, kiểm pointcut, Reflection tùy cách triển khai | Mã đã chèn, dispatch/helper và advice tương ứng |
| Bộ nhớ | Proxy instances, handler chain, cached metadata | Class bytes biến đổi, metadata, helper/instrumentation state |
| JIT | Inlining phụ thuộc shape và số tầng dispatch | JIT có thể tối ưu nhưng code instrumentation cũng có chi phí |
| I/O | Ghi log/metrics/network có thể là phần chi phí lớn nhất | Tương tự |
| Độ phủ | Giới hạn ở đường gọi proxy | Giới hạn ở class/join point thực sự được woven |

Nếu pointcut quá rộng, cả hai cách đều có thể khiến hot path chậm. Nên đo overhead trên workload thật, có warm-up, đo số lần advice thực thi và tình huống đồng thời. Không tuyên bố một mô hình “luôn nhanh hơn” mô hình khác nếu chưa có benchmark tương ứng.

**Trùng instrumentation** là rủi ro khi kết hợp proxy và weaver: một lượt operation có thể chạy hai audit/metrics. Cần thống nhất policy ownership và đo số lần target thực thi độc lập với số lần advice.

## 18. Quy trình kiểm thử độ phủ đáng tin

Một phép kiểm thử chỉ gọi `adviceMethod()` trực tiếp có thể xác minh logic của advice, nhưng **không chứng minh hệ thống AOP thật sự áp dụng nó**. Hãy có integration test đi qua đúng ranh giới.

### 18.1. Ma trận kiểm thử

| Ca thử | Kỳ vọng với interface proxy minh họa | Điều cần xác minh với weaving |
| --- | --- | --- |
| `proxy.work("A")` | Handler `work` chạy một lần | Cùng invocation có thể còn woven advice nếu class được dệt |
| `proxy.internally("B")` | Không có handler `work` trên `this.work()` | Execution `work` đã woven có thể chạy |
| `target.work("C")` | Không có handler proxy | Execution đã woven có thể chạy |
| Method `final` qua interface proxy | Handler vẫn thấy interface invocation | Bytecode method execution tùy engine |
| Private helper | Proxy không intercept trực tiếp | Weaving private execution nếu hỗ trợ |
| Static method | Proxy instance không intercept trực tiếp | Weaving static join point nếu hỗ trợ |
| Constructor | Proxy không thấy construction của target trước đó | Weaving constructor join point nếu hỗ trợ |
| Field access | Proxy không thấy trực tiếp | Weaving field get/set nếu hỗ trợ |
| Target ném exception | Handler thấy exceptional exit của lời gọi đã chọn | Advice throwing tại đúng join point có thể chạy |
| Internal exception được catch | Handler ngoài có thể chỉ thấy normal return | Inner exception points nếu engine hỗ trợ |
| Proxy bị bypass | Không có advice của proxy | Weaving coverage không phụ thuộc proxy nếu callee dệt |
| Two pointcuts match | Tùy handler chain được lắp | Có thể có nhiều advice hợp lệ, cần đếm |
| Future trả pending | Chỉ thấy handle được return | Method weaving cũng không tự chứng minh task completion |

### 18.2. Các assertion cần thiết

- **Matching:** join point được chọn và không được chọn hoạt động đúng.
- **Interception:** method thật có đi qua proxy hoặc bytecode đã woven không?
- **Behavior preservation:** kết quả trả về, ngoại lệ gốc và side effect nghiệp vụ giữ nguyên nếu advice chỉ quan sát.
- **Call count:** advice entry và target execution count được đo **riêng**.
- **Ordering:** hai advice cùng chọn một điểm có thứ tự như hợp đồng engine.
- **Class identity:** target runtime class có đúng loader, version, artifact được instrument không?
- **Lifecycle:** với LTW, classload/transformer thực sự xảy ra vào thời điểm mong đợi.
- **Negative coverage:** lời gọi không qua proxy phải không bị ghi nhầm là đã intercept; những method ngoài weaving scope không được coi là đã bảo vệ.

### 18.3. Thử nghiệm đối chứng

Có thể chạy một test harness theo các trạng thái:

~~~text
Case A: target raw, không bytecode weaving
Case B: proxy(raw target)
Case C: woven target, gọi trực tiếp
Case D: proxy(woven target)

Đếm riêng:
- số lần business chạy
- số proxy handler entries
- số woven advice entries
- kết quả caller
- exception type
~~~

Đây là thiết kế kiểm thử giả định, **không phải bốn chế độ có sẵn** của ví dụ Java. Ở `Case D`, cùng chính sách được cài cả proxy và woven code có thể sinh event trùng; nếu chủ đích khác nhau, cần phân biệt event semantics.

## 19. Checklist lựa chọn kiến trúc theo độ phủ

Trước khi chọn cơ chế AOP, tự hỏi:

1. **Cần quan sát những loại join point nào?** Public API calls hay cả private/static/constructor/field/exception handler?
2. **Đường gọi đi qua đâu?** Mọi caller có thể được buộc dùng một proxy đáng tin không?
3. **Có self-invocation không?** Method nội bộ cần advice không?
4. **Cần can thiệp class không sở hữu source không?** Có quyền/capability biến đổi bytecode không?
5. **Cần chọn call site hay method execution?** Muốn hạn chế theo caller hay bao mọi lần callee chạy?
6. **Modifier có quan trọng không?** Final/private/static/constructor nằm trong scope chứ?
7. **Có nhiều classloader/module không?** Cùng class name có thể được nạp nhiều bản?
8. **Khi nào instrumentation chạy?** Build, classload hoặc runtime proxy?
9. **Có yêu cầu hot update không?** Policy runtime khác với retransform class đã load.
10. **Các advice có thay đổi luồng không?** Retry/caching/authorization yêu cầu contract và test khác logging.
11. **Có yêu cầu bảo mật/audit bắt buộc không?** Đã loại mọi đường bypass chưa?
12. **Làm sao chứng minh coverage?** Integration test + negative test + production observability.
13. **Nếu weaving thất bại thì sao?** Fail-open/fail-closed theo chính sách.
14. **Có trùng tầng không?** Proxy và woven code có đang áp cùng một logical event hai lần?
15. **Chi phí vận hành nào chấp nhận được?** Build complexity, agent compatibility, debugging hay per-call overhead?

Chỉ chọn proxy khi **ranh giới API được kiểm soát** đủ thỏa yêu cầu; chọn biến đổi mã khi cần những điểm sâu hơn và có khả năng kiểm chứng đúng scope. Cũng có thể kết hợp hai mô hình, nhưng cần bản đồ instrumentation và quy tắc tránh duplicate policy.

## 20. Những lỗi hiểu sai phổ biến

1. **“Đã khai báo pointcut khớp tên method là chắc chắn có advice.”** Sai: còn phải có đường proxy hoặc class/join point thực sự woven.
2. **“Có proxy thì mọi method của target được chặn.”** Sai: interface/override/scope và đường gọi giới hạn độ phủ.
3. **“Self-invocation luôn đi qua proxy.”** Sai trong wrapper bên ngoài như ví dụ.
4. **“Final method không bao giờ intercept được.”** Sai: interface proxy vẫn có thể nhận call đến implementation `final`.
5. **“Bytecode weaving không thể áp dụng cho private method.”** Không có quy tắc chung; phụ thuộc engine/pointcut.
6. **“Proxy tự nhìn constructor/field access.”** Không: method proxy thông thường không chặn các opcode ấy.
7. **“Weaving chắc chắn instrument mọi constructor và field.”** Sai: phải xem mô hình join point và phạm vi thực.
8. **“Method call và execution là cùng một điểm.”** Sai: vị trí caller và callee khác nhau.
9. **“Chỉ cần có `-javaagent` là mọi class được dệt.”** Sai: timing, filters, classloader và capability ảnh hưởng.
10. **“Tắt agent sẽ tự tháo advice khỏi class đã load.”** Không mặc định; phụ thuộc redefinition/restart.
11. **“Proxy biến đổi bytecode target mỗi lần gọi.”** Không phải hoạt động bắt buộc của proxy; JDK `Proxy` có thể chỉ là wrapper.
12. **“Nhìn hai log chứng minh double weaving.”** Không: có thể hai join points, hai proxies, retry hoặc redelivery ở sink.
13. **“Mọi exception nội bộ đều được after-throwing của proxy nhìn thấy.”** Sai nếu target đã catch trước khi thoát ra.
14. **“Future return đồng nghĩa task đã hoàn tất.”** Sai: cần quan sát completion riêng.
15. **“Unit test của advice chứng minh coverage.”** Không: phải test đường can thiệp thật.
16. **“Weaving luôn nhanh hơn proxy.”** Không có kết luận chung khi chưa benchmark.
17. **“Bảo mật có thể đặt hoàn toàn ở một proxy dễ bypass.”** Nguy hiểm nếu người gọi có thể giữ target raw.
18. **“Tên method là đủ xác định join point.”** Không: overload, bridge/synthetic, declaring type và kind cũng có ý nghĩa.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Một JDK proxy bọc `Service`; caller gọi thẳng `target.work()`. Handler có chạy không?  
**Đáp án:** Không qua handler của proxy đó. Caller đã bỏ qua đối tượng trung gian.

**Câu 2.** `Target.work()` khai báo `final`, nhưng implements method của `Service`. Proxy interface có quan sát call `proxy.work()` được không?  
**Đáp án:** Có thể. Nó nhận interface invocation trước khi gọi target; không cần subclass override final method.

**Câu 3.** `proxy.internally()` chuyển tới target, target gọi `this.work()`. Vì sao không có proxy event của `work`?  
**Đáp án:** Đây là self-invocation trên target, không đi qua tham chiếu proxy ở lời gọi nội bộ.

**Câu 4.** Một class đã woven ở `execution(work)`. `this.work()` có thể kích hoạt advice không?  
**Đáp án:** Có, nếu bytecode thực thi của `work` đã được biến đổi đúng và engine hỗ trợ điểm ấy.

**Câu 5.** Bytecode weaving có luôn thấy constructor, private method, field write không?  
**Đáp án:** Không. Phải kiểm tra join point model, class scope, transformer và giới hạn JVM/công cụ.

**Câu 6.** Tại sao một proxy không thấy exception đã bị target tự catch?  
**Đáp án:** Vì lời gọi ngoài có thể hoàn tất bình thường; exception không thoát khỏi ranh giới mà handler quan sát.

**Câu 7.** Khi `call` và `execution` advice đều chạy, có chắc dệt lặp không?  
**Đáp án:** Không. Chúng là hai loại join point; có thể cùng được chọn hợp lệ.

**Câu 8.** Chạy Java agent sau khi target class đã load thì LTW thông thường có chắc áp dụng không?  
**Đáp án:** Không; có thể cần khả năng retransformation riêng và vẫn bị giới hạn của JVM/tool.

**Câu 9.** Hai lớp audit cùng chạy khi proxy bọc một target đã woven. Nên làm gì?  
**Đáp án:** Xác định policy ownership, tầng và đơn vị event; loại trừ trùng ngoài ý định nhưng giữ những advice khác mục đích.

**Câu 10.** Điều nào chứng minh an toàn cho một policy quan trọng: test hàm advice hay integration test đường gọi?  
**Đáp án:** Cần integration test qua đường instrumentation thật, cả đường bypass/không khớp và các loại join point quan trọng; unit test advice là cần nhưng không đủ.

## 22. Tổng kết

**Khác biệt căn bản giữa AOP qua proxy và biến đổi mã là vị trí đặt điểm can thiệp.** Proxy nhìn thấy **lời gọi qua đối tượng trung gian**; weaving/instrumentation có thể đặt logic tại **call site, method execution hoặc các join point sâu hơn** nếu công cụ hỗ trợ và class thực sự được biến đổi. Vì vậy, self-invocation, direct target calls, `private`, `final`, `static`, constructor và field access có thể có độ phủ khác nhau.

Không có mô hình nào tự bảo đảm “bao mọi thao tác”. Để chọn đúng, hãy xác định join point cần kiểm soát, đường đi thực tế, modifier, classloader/lifecycle, policy lỗi và yêu cầu bảo mật. **Kiểm thử integration với cả đường được chọn và đường bypass** là bằng chứng quan trọng nhất; đánh giá thêm performance, double instrumentation và tính tương thích runtime để advice vận hành đúng ý định mà không thay đổi kết quả, ngoại lệ hoặc số lần thực thi nghiệp vụ ngoài hợp đồng.
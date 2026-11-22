# Đối tượng trung gian và đối tượng đích có danh tính khác nhau thế nào trong AOP qua proxy

## 1. Proxy và target là ai?

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), một kỹ thuật triển khai mối quan tâm xuyên cắt là tạo một **proxy** làm trung gian giữa bên gọi (**caller**) và object thực hiện nghiệp vụ (**target**). Caller giữ reference đến proxy, gửi invocation qua nó; interceptor có thể chạy advice trước/sau/bao quanh hành vi gốc, rồi ủy quyền tới target nếu chính sách cho phép.

~~~text
Caller ---> Proxy P ---> Interceptor/advice ---> Target T
               |                                |
         object trung gian               object nghiệp vụ
~~~

**Với proxy dạng wrapper có target instance riêng, P và T là hai object khác nhau trong Java.** Chúng có thể cùng implement một interface, cùng đại diện một service hoặc dùng cùng dữ liệu nghiệp vụ, nhưng **reference identity của chúng khác nhau**.

Cần phân biệt:

1. **Reference identity:** hai reference có trỏ đúng cùng object Java không?
2. **Logical identity:** hai object có đại diện cùng entity/service/tài nguyên không?
3. **Equality:** P.equals(T) và T.equals(P) được định nghĩa thế nào?
4. **Runtime type:** class thực tế của P có giống class T không?
5. **Call path:** lời gọi có qua proxy để kích hoạt advice không?
6. **State và lifecycle:** state, lock, cache key, handler và target tồn tại theo phạm vi nào?
7. **AOP this/target:** vai trò ở join point có phải chính P/T không?

**Không được kết luận mọi cơ chế AOP đều có hai instance P và T.** Một subclass-based proxy có thể sử dụng chính generated subclass instance để xử lý logic; một binary weaver có thể chèn code trực tiếp vào method body mà không cần proxy tách biệt. Phải xác định chiến lược runtime cụ thể.

## 2. Cùng interface không đồng nghĩa cùng reference

Xét khai báo minh họa:

~~~java
interface Service {
    int compute(int value);
}
~~~

Một factory có thể tạo target Core và wrapper P đều implement Service:

~~~text
reference core: Service  --------> Core T
reference observed: Service -----> Proxy P -----> Core T
~~~

Khi caller thực hiện observed.compute(3), lời gọi đi qua handler. Nếu thực hiện core.compute(3), lời gọi đi trực tiếp tới target. Hai lần có thể trả cùng kết quả nhưng chỉ một lần kích hoạt interceptor của P.

Type khai báo **Service** chỉ nói object tương thích API, không chứng minh object là Core, proxy hoặc bất cứ implementation cụ thể nào. Đây là nguyên nhân nên thiết kế API theo interface ổn định, còn test coverage AOP phải kiểm tra reference thực tế được cấp cho caller.

## 3. Reference identity: toán tử ==

Với object reference trong Java, **==** trả true khi hai reference chỉ cùng object (hoặc cả hai null), chứ không so dữ liệu nghiệp vụ.

Trong wrapper model:

~~~text
P == T    --> false
P == P    --> true

Tạo P1 và P2 là hai wrapper mới cùng delegate T:
P1 == P2  --> false
P1 == T   --> false
P2 == T   --> false
~~~

Hai proxy cùng target có thể quan sát cùng business state và return value. Chúng vẫn là các object riêng nếu được tạo bằng hai lần cấp phát instance.

**Logical identity** là câu hỏi khác. Một service có thể đại diện một chức năng; một entity có thể có ID cố định. Hai object biểu diễn cùng entity có thể cần được coi là tương đương theo domain contract, nhưng điều đó **không thay đổi kết quả ==**.

Một proxy được tạo lại sau đổi cấu hình sẽ có object identity mới dù target cũ vẫn tồn tại. Điều này ảnh hưởng cache keyed by reference, monitor synchronization, metrics gắn instance và lifecycle.

## 4. Equals không giống ==

**equals** của Object mặc định có identity semantics khi class không override, nhưng class nghiệp vụ có thể so sánh ID hoặc value fields. Proxy có thể chuyển equals vào InvocationHandler, rồi handler chủ động chọn policy.

| Câu hỏi | Cơ chế | Nhận xét |
|---|---|---|
| P và T có cùng object? | P == T | False nếu wrapper/target riêng |
| P coi T bằng nhau? | P.equals(T) | Tùy implementation |
| T coi P bằng nhau? | T.equals(P) | Có thể khác nếu viết sai |
| P và T có cùng class? | P.getClass() == T.getClass() | Thường false với JDK interface proxy |
| P dùng interface Service? | P instanceof Service | Có thể true |
| P là Core object? | P instanceof Core | False trong ví dụ JDK proxy |

### 4.1. Hợp đồng equality

Java yêu cầu equals có các tính chất:

- **Reflexive:** x.equals(x) là true.
- **Symmetric:** x.equals(y) và y.equals(x) thống nhất.
- **Transitive:** nếu x bằng y và y bằng z thì x bằng z.
- **Consistent:** không đổi tùy tiện nếu dữ liệu so sánh không đổi.
- **Non-null:** x.equals(null) false.
- Nếu x.equals(y) thì x.hashCode() phải bằng y.hashCode().

### 4.2. Nguy hiểm khi forward equals xuống target

Một handler có thể viết theo ý tưởng:

~~~text
P.equals(X) := T.equals(X)
~~~

Với T dùng identity equality mặc định:

~~~text
P.equals(T) = T.equals(T) = true
T.equals(P) = false
~~~

Điều này **phá tính đối xứng**. Vì vậy không được forward tất cả method, kể cả Object.equals, một cách máy móc.

Các chiến lược hợp lý:

1. **Identity theo wrapper:** proxy chỉ bằng chính nó và hashCode identity-based.
2. **Logical equality theo domain key:** cần bảo đảm mọi class tham gia cùng một contract đối xứng/bắc cầu.
3. **Tách domain key:** dùng một ID/value object độc lập cho cache và nghiệp vụ, giữ identity của wrapper riêng.

Với nhiều service không có entity key, cách 1 thường dễ kiểm soát; khi cần logical identity, cách 3 thường rõ nghĩa hơn. Không có giải pháp phổ quát cho mọi domain.

## 5. HashCode và IdentityHashMap

**P.hashCode()** có thể do InvocationHandler xử lý; nó không nhất thiết bằng **System.identityHashCode(P)**. Identity hash là một giá trị số từ quy tắc identity hashing, **không phải định danh duy nhất tuyệt đối** vì có thể trùng số.

**HashMap** và **HashSet** dựa trên equals/hashCode. **IdentityHashMap** phân biệt key bằng reference equality. Trong wrapper model, P và T là hai key khác nhau của IdentityHashMap, ngay cả khi một equality policy coi chúng bằng nhau.

Ví dụ khái niệm:

~~~text
map.put(P, "tracked")
map.get(P) --> "tracked"
map.get(T) --> có thể không thấy nếu equality khác nhau
~~~

Nếu cache nên gộp nhiều proxy theo cùng entity/service logic, dùng một **key nghiệp vụ bất biến** và tài liệu hóa ý nghĩa, không dựa vào tên class hoặc identityHashCode của proxy.

### 5.1. ToString không đại diện identity

Handler có thể trả **TrackedProxy** cho toString; hai proxy khác nhau có thể cùng trả tên này. Không dùng toString làm ID duy nhất, khóa cơ sở dữ liệu, correlation key hoặc bằng chứng P == T.

## 6. Runtime class và type compatibility

**JDK dynamic proxy** implement interface mà factory yêu cầu. Nó không trở thành instance của concrete target class chỉ vì nó delegate đến target.

Một tình huống điển hình:

~~~text
                 Service interface
                  /            \
          Core target T        JDK proxy P
          implements           implements
~~~

Hệ quả trong chương trình mẫu:

- P instanceof Service là true.
- T instanceof Service là true.
- P instanceof Core là false.
- P.getClass() == T.getClass() là false.
- P == T là false.

Không nên cố cast JDK interface proxy thành Core để gọi method không nằm trong interface. Tương tự, không nên dùng tên generated proxy class làm nguồn sự thật về implementation; tên đó có thể thay đổi theo nền tảng và version.

### 6.1. Subclass proxy khác

Một class-based proxy có thể là subclass của concrete implementation, khiến **P instanceof Core** có thể true nếu engine/type cho phép. Nhưng instanceof vẫn không chứng minh **P == T**. Một số engine dùng proxy subclass làm receiver chính; một số giữ delegate target riêng.

### 6.2. Bytecode weaving khác proxy

Một bộ dệt bytecode có thể instrument trực tiếp **execution join point** của Core.method. Khi đó không cần P riêng để có advice. Nếu code tự gọi method nội bộ trong class đã weave, execution advice có thể vẫn chạy tùy engine/pointcut. Không áp giới hạn JDK proxy cho mọi AOP.

## 7. Object methods và InvocationHandler

Một **InvocationHandler** của JDK dynamic proxy có thể nhận lời gọi của **equals, hashCode, toString**. Nó còn nhận method được gọi qua interface Service, bao gồm Object[] args runtime.

Handler cần quyết định rõ:

~~~text
if method == equals:
    return proxy == other
if method == hashCode:
    return identityHashCode(proxy)
if method == toString:
    return "TrackedProxy"
otherwise:
    run advice
    invoke target method
~~~

Đây là giả mã, không phải Java độc lập.

Một lời gọi proxy.toString() không nhất thiết đi qua code Object.toString mặc định; handler có thể trả một chuỗi tùy chỉnh. Một lời gọi proxy.equals(target) không được giả định delegate chính xác tới target.equals(target).

Các method của Object như getClass, wait và notify có ngữ nghĩa nền tảng riêng; không đồng nhất toàn bộ Object methods với các method được JDK dynamic proxy chuyển tới handler.

## 8. Ví dụ Java 17 chạy được: P và T có identity khác nhau

Chương trình sau sử dụng **JDK dynamic proxy** để quan sát trực tiếp:

- P và T khác reference/class.
- P implement Service nhưng không phải Core.
- P xử lý equals/hashCode/toString theo identity policy.
- Target trả **this**, có thể lộ reference T.
- Self-invocation của T không quay lại handler P.
- Số lượt interception khác số lần body target chạy.

Tạo file **ProxyIdentityDemo.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

public class ProxyIdentityDemo {
    interface Service {
        int run(int value);
        void internal();
        Service self();
    }

    static final class Core implements Service {
        private int runs;
        private int internals;

        @Override
        public int run(int value) {
            runs++;
            System.out.println("core: run " + value);
            internal();
            return value * 2;
        }

        @Override
        public void internal() {
            internals++;
            System.out.println("core: internal");
        }

        @Override
        public Service self() {
            return this;
        }
    }

    static Service observe(Service target, AtomicInteger observedCalls) {
        return (Service) Proxy.newProxyInstance(
            Service.class.getClassLoader(),
            new Class<?>[] {Service.class},
            (proxy, method, args) -> {
                if (method.getDeclaringClass() == Object.class) {
                    return switch (method.getName()) {
                        case "equals" -> proxy == args[0];
                        case "hashCode" -> System.identityHashCode(proxy);
                        case "toString" -> "TrackedProxy";
                        default -> throw new UnsupportedOperationException();
                    };
                }

                observedCalls.incrementAndGet();
                System.out.println("advice: " + method.getName());
                try {
                    return method.invoke(target, args);
                } catch (InvocationTargetException e) {
                    throw e.getCause();
                }
            });
    }

    public static void main(String[] args) {
        Core core = new Core();
        AtomicInteger calls = new AtomicInteger();
        Service observed = observe(core, calls);

        System.out.println("proxy == target: " + (observed == core));
        System.out.println("proxy instanceof Service: " + (observed instanceof Service));
        System.out.println("proxy instanceof Core: " + (observed instanceof Core));
        System.out.println("target instanceof Service: " + (core instanceof Service));
        System.out.println("same runtime class: " + (observed.getClass() == core.getClass()));
        System.out.println("proxy.equals(proxy): " + observed.equals(observed));
        System.out.println("proxy.equals(target): " + observed.equals(core));
        System.out.println("target.equals(proxy): " + core.equals(observed));
        System.out.println("hashCode uses proxy identity: "
            + (observed.hashCode() == System.identityHashCode(observed)));
        System.out.println("proxy.toString(): " + observed);

        System.out.println("proxy.self() == target: " + (observed.self() == core));
        System.out.println("proxy.self() == proxy: " + (observed.self() == observed));

        System.out.println("through proxy:");
        System.out.println("result=" + observed.run(3));

        System.out.println("through returned target:");
        System.out.println("result=" + observed.self().run(4));

        System.out.println("direct target:");
        System.out.println("result=" + core.run(5));

        System.out.println("direct proxy internal:");
        observed.internal();

        System.out.println("core runs=" + core.runs);
        System.out.println("core internals=" + core.internals);
        System.out.println("intercepted calls=" + calls.get());
    }
}
~~~

Biên dịch và chạy trên Java 17:

~~~bash
javac --release 17 ProxyIdentityDemo.java
java ProxyIdentityDemo
~~~

**Stdout chính xác:**

~~~text
proxy == target: false
proxy instanceof Service: true
proxy instanceof Core: false
target instanceof Service: true
same runtime class: false
proxy.equals(proxy): true
proxy.equals(target): false
target.equals(proxy): false
hashCode uses proxy identity: true
proxy.toString(): TrackedProxy
advice: self
proxy.self() == target: true
advice: self
proxy.self() == proxy: false
through proxy:
advice: run
core: run 3
core: internal
result=6
through returned target:
advice: self
core: run 4
core: internal
result=8
direct target:
core: run 5
core: internal
result=10
direct proxy internal:
advice: internal
core: internal
core runs=3
core internals=4
intercepted calls=5
~~~

### 8.1. P == T false nhưng cùng Service

**observed** là một object dynamic proxy; **core** là instance Core. Chúng cùng implement Service nên caller có thể gọi run/internal/self qua interface. Nhưng JVM nhận diện chúng là hai object và hai runtime classes khác nhau.

### 8.2. Equality của proxy được quy định trong handler

Handler chủ động định nghĩa P.equals(P) là true, P.equals(T) là false và P.hashCode() dùng identityHashCode(P). Core không override equals nên T.equals(P) là false. Đây là một policy **của demo**, không phải đáp án bất biến cho mọi proxy.

### 8.3. Return-this làm lộ target

Core.self trả reference **this của Core**, không phải P. Handler chuyển kết quả nguyên trạng. Vì vậy:

~~~text
observed.self() -> handler -> core.self() -> Core T
~~~

Sau đó observed.self().run(4) gọi trực tiếp trên T nên có **advice: self**, nhưng không có **advice: run** ở lần gọi ấy.

Một số engine có thể chọn trả proxy khi target method trả this, tùy contract và khả năng của engine; điều đó **không được mặc định**.

### 8.4. Self-invocation bỏ qua JDK proxy

Core.run tự gọi internal() trên chính Core. Handler không nhận được lời gọi internal từ nội bộ ấy. Nhưng observed.internal() do caller phát qua proxy được handler quan sát.

Do đó:

- **core runs=3**: body run chạy 3 lần.
- **core internals=4**: ba self-calls từ run và một call qua proxy.
- **intercepted calls=5**: ba lần self, một run, một internal đi qua proxy.

**Advice invocation count không bằng method execution count** trong mô hình này.

### 8.5. Exception propagation

Method.invoke có thể bao exception target ném vào InvocationTargetException. Handler unwrap cause để lan truyền lỗi nghiệp vụ phù hợp, tránh làm biến đổi exception contract chỉ vì có interceptor.

## 9. Target reference có thể thoát ra khỏi proxy bằng đường nào?

Không chỉ có self():

1. Factory cấp cả target T và proxy P cho hai thành phần khác nhau.
2. Target method trả this, handler trả nguyên object T.
3. Target đăng ký this vào registry, listener hoặc event bus.
4. Callback/lambda/method reference giữ receiver T từ trước khi tạo P.
5. Một component tự tạo Core bằng new, không qua factory cấp proxy.
6. Một API công bố target object qua reflection/introspection khi code có quyền.
7. Một caller giữ reference T từ lúc lắp ghép hệ thống, dù caller khác nhận P.

Mỗi trường hợp có thể làm bypass những concern chỉ được gắn vào P. Nếu AOP thực hiện chính sách bảo mật hay kiểm toán bắt buộc, cần kiểm soát tất cả đường có thể gọi T, hoặc sử dụng cơ chế có độ bao phủ phù hợp và đã được kiểm chứng.

### 9.1. Fluent API

Một method builder thường trả this:

~~~java
Service configure(int level) {
    this.level = level;
    return this;
}
~~~

Đây là đoạn minh họa chưa đầy đủ. Nếu P delegate configure đến T và trả nguyên reference T, chuỗi:

~~~text
P.configure(3).execute()
~~~

có thể chỉ intercept configure, còn execute chạy trực tiếp trên T. Một số proxy engine có chính sách xử lý return-this riêng; cần test rõ thay vì suy đoán.

### 9.2. Callback và method reference

Nếu callback đóng trên T, invocation xảy ra trong tương lai vẫn có thể đi thẳng T, không qua P. Muốn advice chạy phải tổ chức callback giữ proxy thích hợp hoặc instrument execution tại điểm mà engine hỗ trợ.

## 10. This/target trong pointcut không mặc định là P/T

Một ngôn ngữ AOP có thể có pointcut designators **this** và **target**. Nhưng ý nghĩa của chúng gắn với **join point kind**, không phải tên biến trong InvocationHandler.

Trong một mô hình như AspectJ:

- Ở method-call join point, **this** thường là object đang thực thi mã phía caller; **target** là receiver được gọi nếu có.
- Ở method-execution join point của instance method, **this** và **target** thường là object đang thực thi method.
- Trong static context, một số điểm không có instance this/target.

~~~text
Caller C gọi object T.work()

Call join point:
    this ≈ C, target ≈ T

Execution join point:
    this ≈ T, target ≈ T
~~~

Sơ đồ này là mô tả khái niệm trong mô hình có call/execution join points, không phải ngữ nghĩa chung của mọi công cụ AOP.

Với JDK dynamic proxy, biến **proxy** của InvocationHandler là object P mà JDK chuyển cho handler, còn biến **target** thường là reference T mà handler giữ. **Đừng ánh xạ hai biến ấy sang designators this/target của mọi pointcut language**.

### 10.1. Per-this và per-target

Một số mô hình AOP có cách tạo aspect instance theo this hoặc target tại join point. Ví dụ ở call join point, **per-this** có thể phân biệt các caller C1/C2, còn **per-target** có thể gắn state với T.

Nếu có nhiều wrapper P1/P2 cùng delegate T, cần quyết định rõ state/metrics thuộc về wrapper, target, caller hay logical entity; không suy ra một mapping từ tên per-this/per-target.

## 11. Proxy identity và synchronized

Java sử dụng **monitor của object receiver** với synchronized:

~~~java
synchronized (proxy) {
    // lock P
}

synchronized (target) {
    // lock T
}
~~~

Đoạn minh họa cần biến proxy/target được định nghĩa. Nếu P và T là hai object, **hai monitor khác nhau**, kể cả khi P.equals(T) được tùy chỉnh để true.

Một caller giữ monitor P không tự bảo vệ biến mutable trong T khỏi code khác synchronized(T). Chọn một lock ổn định được mọi đường dùng chung, hoặc đặt synchronization tại nơi thực sự sở hữu invariant.

Các thao tác Object.wait/notify cũng gắn với monitor của object, không theo equals. Không thể đợi trên P và thông báo trên T mà coi là cùng monitor.

### 11.1. Concurrency và interceptor state

P có thể giữ counters, cache hoặc một handler mutable. Nếu nhiều thread gọi qua P, handler phải được thiết kế thread-safe theo contract. Một target T được nhiều proxy P1/P2 delegate vẫn có thể có race trên business fields nếu T không thread-safe.

Proxy không tự đồng bộ mọi method chỉ nhờ tồn tại.

## 12. State, lifetime và garbage collection

Một wrapper thường tạo object graph:

~~~text
Caller -> Proxy P -> Handler H -> Target T
~~~

Nếu Caller giữ P và H giữ T bằng strong reference, T có thể còn reachable. Nhưng T cũng có thể sống nhờ một reference khác sau khi P không còn được sử dụng.

Các câu hỏi cần trả lời:

- Proxy được tạo mỗi request hay tái sử dụng?
- Target có state theo request, session hay application?
- Nhiều proxy có cùng target không?
- Handler có giữ target mạnh, hay lấy từ provider khác?
- Một callback giữ reference P cũ hay T cũ?
- Cache dùng P identity làm key hay dùng stable business key?
- Có classloader/cache nào giữ generated proxy class lâu hơn dự kiến không?

Một WeakHashMap keyed by P không tự có cùng lifecycle với T; value có thể gián tiếp giữ key hoặc handler có reference mạnh khác. Hãy phân tích reachability/object graph thay vì đoán qua tên proxy.

## 13. Nhiều lớp proxy có thể làm identity và số lượt advice phức tạp hơn

~~~text
Caller -> P2 (tracing) -> P1 (authorization) -> T (business)
~~~

Ở wrapper model, P2, P1 và T đều có thể là ba object reference riêng. Caller dùng P2 sẽ qua tracing và authorization; caller có P1 thì thiếu tracing của P2; caller giữ T sẽ bỏ qua cả hai interceptor.

Nếu P2 short-circuit, P1/T có thể không chạy. Nếu P2 retry, P1/T có thể chạy nhiều lần cho một caller invocation. Vì vậy phải phân biệt:

- Số lượt vào proxy ngoài.
- Số lượt vào proxy trong.
- Số lần target thực thi.
- Số self-calls không đi qua proxy.
- Số result/exception đã quan sát.

Không được cộng mọi counter rồi gọi là số request.

### 13.1. Equality qua nhiều proxy

Nếu P2 forward equals về P1, còn P1 forward về T, có thể phát sinh sự khác biệt giữa P2.equals(T), T.equals(P2) và hashCode. Nên giữ một policy nhất quán và dùng domain key riêng cho các yêu cầu so sánh business identity.

## 14. Cache, reflection và serialization

### 14.1. Cache keyed by object

Một HashMap keyed by proxy có thể miss khi tra bằng target; một IdentityHashMap chắc chắn phân biệt P/T ở mô hình wrapper riêng. Nếu ý nghĩa là cùng một entity, dùng immutable entity ID.

### 14.2. Reflection

Một annotation resolver đọc P.getClass() có thể nhận generated proxy class thay vì Core. JDK proxy InvocationHandler có thể nhận Method từ interface, còn annotation lại đặt trên implementation method. Nguồn metadata cần được xác định đúng: interface contract, implementation hoặc join point description.

### 14.3. Serialization

Serialize/deserialize một proxy không có nghĩa giữ nguyên reference identity. Khả năng serialize còn phụ thuộc handler/target và contract công nghệ; kết quả thường là object mới nếu serialization được hỗ trợ. Test equality, state, cache và wiring sau deserialize thay vì mong P == P cũ.

### 14.4. Classloader

Java class identity liên quan binary name và defining ClassLoader. Hai interface/class cùng tên nhưng từ loader khác có thể không tương thích kiểu. Proxy factory phải dùng loader có thể thấy những interface được yêu cầu, còn binding/matching phải chú ý classloader context.

## 15. Ứng dụng vào các concern AOP

| Concern | Câu hỏi identity/coverage phải hỏi |
|---|---|
| Tracing | Lời gọi nào không qua proxy làm mất event? |
| Metrics | Counter đo proxy invocation hay target execution? |
| Authorization | Target reference thoát ra làm bypass policy không? |
| Cache | Cache theo wrapper identity hay theo business key? |
| Retry | Một caller call làm target chạy mấy lần? |
| Logging | toString/getClass của P có làm hiểu sai implementation không? |
| Audit | Có đường gọi nội bộ/direct thiếu sự kiện bắt buộc không? |
| Concurrency | Lock trên P hay T, hai đường có chung monitor không? |
| Lifecycle | P được tạo mới có giữ T cũ hoặc handler cũ không? |

Đối với một concern bắt buộc, xác nhận coverage trên những đường thực tế quan trọng hơn việc code advice chạy trong một test happy path.

## 16. Quy trình kiểm chứng một proxy AOP

1. **Xác định strategy**: JDK interface proxy, decorator, subclass proxy hay bytecode weaving.
2. **Vẽ object graph**: ai giữ P, ai giữ T, handler delegate đến đâu.
3. **Kiểm tra reference identity**: P == T ở mô hình cụ thể.
4. **Kiểm tra runtime type**: instanceof interface/class, getClass.
5. **Kiểm tra equality/hashCode**: reflexive/symmetric/transitive, hash consistency.
6. **Kiểm tra direct vs proxied calls**: đúng số lượt interceptor và target.
7. **Kiểm tra self-invocation và return this**: reference nào được trả và chain có bypass không.
8. **Kiểm tra callbacks và multiple proxies**: caller có được cấp đúng boundary không.
9. **Kiểm tra concurrency**: lock nào bảo vệ state nào.
10. **Kiểm tra exception**: reflection wrapper và advice failures.
11. **Kiểm tra lifecycle/cache**: thay proxy, thay target, serializing nếu liên quan.
12. **Tạo integration tests** cho positive và negative join point coverage.

Để tránh hỏng equality, có thể viết riêng test dùng HashMap, IdentityHashMap, hai proxy bao cùng target và trường hợp proxy/target ở cả hai vế của equals.

## 17. Ma trận test gợi ý

| Kịch bản | Kỳ vọng cần xác minh |
|---|---|
| P và T là wrapper riêng | P == T false |
| Hai proxy cùng target | P1 == P2 false nếu tạo hai object |
| JDK proxy | P instanceof interface true |
| JDK interface proxy vs Core | P instanceof Core false |
| Equals/hashCode | Tuân theo hợp đồng Java và policy đã chọn |
| ToString | Không coi text là identity |
| Return this | Có trả T thô hay được map về P? |
| Fluent chain | Bước tiếp theo còn đi qua handler không? |
| Target self-call | Handler có bị bypass không? |
| Direct target call | Có làm thiếu policy bắt buộc không? |
| Multiple proxy layers | Số và thứ tự advice đúng |
| Exception target | Handler có unwrap/lan truyền phù hợp? |
| synchronized(P)/synchronized(T) | Không nhầm hai monitor |
| Cache/Map keyed by P | Có tìm bằng T được theo policy không? |
| Recreate proxy | Reference identity và cache key thay đổi thế nào? |
| Reflection annotation | Đang đọc interface hay implementation? |
| Classloader khác | Generated proxy type có tương thích không? |

## 18. Những lỗi phổ biến

**Lỗi 1:** Coi proxy và target là một object vì cùng interface.

**Lỗi 2:** Coi proxy là bản sao đầy đủ của target, trong khi nó có thể chỉ delegate.

**Lỗi 3:** Coi equals luôn tương đương toán tử == hoặc ngược lại.

**Lỗi 4:** Forward equals một chiều làm sai symmetry.

**Lỗi 5:** Coi identityHashCode là ID duy nhất.

**Lỗi 6:** Cast JDK interface proxy thành implementation class.

**Lỗi 7:** Dùng proxy.getClass để tra annotation chỉ có trên target class.

**Lỗi 8:** Target trả this gây target leak, làm các call sau bỏ qua advice.

**Lỗi 9:** Coi target self-invocation là proxy invocation.

**Lỗi 10:** synchronized trên P rồi giả định bảo vệ T.

**Lỗi 11:** Coi perthis/pertarget là tên khác của proxy/target bất kể join point.

**Lỗi 12:** Dùng proxy reference làm domain ID cho cache.

**Lỗi 13:** Nhiều proxy cùng delegate T nhưng counters được coi là một.

**Lỗi 14:** Tưởng mọi class-based proxy có hai object riêng.

**Lỗi 15:** Chỉ test return value mà không test số advice invocations.

**Lỗi 16:** Cho target thô thoát ra ngoài khi cần interceptor bắt buộc.

## 19. Câu hỏi ôn tập và đáp án

**Câu 1.** Hai biến đều có compile-time type Service. Chúng chắc chắn == nhau?

**Đáp:** Không; chúng có thể giữ P và T khác nhau.

**Câu 2.** P != T nhưng cả hai trả cùng kết quả getBalance. Mâu thuẫn không?

**Đáp:** Không; P có thể delegate trực tiếp tới T.

**Câu 3.** P.equals(T) true, T.equals(P) false có lỗi gì?

**Đáp:** Vi phạm tính đối xứng của equals.

**Câu 4.** IdentityHashMap có gộp P và T khi equals trả true không?

**Đáp:** Không; nó dùng reference identity.

**Câu 5.** Vì sao observed.self().run(4) trong demo không có advice: run?

**Đáp:** Self trả target T nên run được gọi trực tiếp trên T.

**Câu 6.** Vì sao Core.run tự gọi internal mà handler không nhận thêm event?

**Đáp:** Self-invocation trên T không đi qua reference proxy P.

**Câu 7.** P instanceof Service true thì P instanceof Core chắc true không?

**Đáp:** Không; JDK dynamic proxy không là Core instance.

**Câu 8.** synchronized(P) và synchronized(T) có cùng monitor nếu P.equals(T) true không?

**Đáp:** Không; monitor dựa vào reference identity.

**Câu 9.** Pointcut this() ở method-call join point luôn chỉ P?

**Đáp:** Không; có thể chỉ caller object theo semantics của ngôn ngữ AOP.

**Câu 10.** Một subclass proxy instanceof Core true chứng minh nó cùng reference với T không?

**Đáp:** Không; quan hệ type khác object identity.

**Câu 11.** Nhiều proxy cùng T muốn cache chung theo entity ID nên dùng gì?

**Đáp:** Domain key ổn định, không mặc định dùng proxy reference.

**Câu 12.** Có thể dùng proxy kiểm tra quyền bắt buộc mà vẫn cho caller giữ T gốc không?

**Đáp:** Rất rủi ro; đường gọi T có thể bypass kiểm tra. Cần thiết kế boundary và coverage phù hợp.

## 20. Sơ đồ ghi nhớ

~~~text
                    Caller
                       |
                Service reference
                       |
                       v
                   Proxy P
               identity của P
               class của P
               equals/hashCode của P
                       |
                       v
                 Interceptor
                       |
                       v
                   Target T
               identity của T
               class của T
               business state của T
                       |
                       v
                  Method body
                       |
                       +-- return value
                       +-- throw exception
                       +-- return this (có thể trả T thô)
                                   |
                                   v
                           Caller có thể bypass P
~~~

**Kết luận:** với proxy wrapper và target riêng, **P != T theo reference identity**, dù cả hai có thể cùng Service interface, logic nghiệp vụ và dữ liệu. Equality không tự được hợp nhất; runtime class/monitor/lifecycle có thể khác nhau; return-this, direct reference và self-invocation có thể bypass proxy. Khi dùng AOP, hãy xác nhận **đúng object đang nhận lời gọi, đúng loại join point, đúng equality contract và đúng giới hạn của cơ chế interception**.

## Tài liệu đối chiếu

- [Java SE 17 — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): JDK dynamic proxy và Object methods.
- [Java SE 17 — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): tham số proxy/Method/args và exception contract.
- [Java SE 17 — Object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): equals, hashCode, getClass và monitor.
- [Java SE 17 — IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): equality theo reference.
- [Java Language Specification, Java SE 17 — Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html): reference comparison và dynamic method dispatch.
- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): this/target join point semantics và mô hình aspect instantiation.

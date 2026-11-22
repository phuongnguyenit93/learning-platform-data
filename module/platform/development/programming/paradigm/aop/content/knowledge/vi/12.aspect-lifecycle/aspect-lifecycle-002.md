# Vòng đời gắn với từng đối tượng khi công cụ hỗ trợ trong AOP

> **Mục tiêu:** Hiểu cách một số mô hình Aspect-Oriented Programming (AOP) gắn **một aspect instance với một đối tượng cụ thể**, thay vì chia sẻ một instance duy nhất cho toàn bộ ứng dụng. Phân biệt singleton, per-object, per-this, per-target, per-proxy, per-invocation, per-type và per-control-flow. Xác định thời điểm tạo, tái sử dụng, giải phóng state, cùng rủi ro về object identity, đồng thời, garbage collection và độ bao phủ của pointcut. Các ví dụ Java 17 dùng Java thuần để minh họa; không giả định mọi công cụ AOP có cùng API hoặc cùng ngữ nghĩa.

## 1. Tại sao cần vòng đời aspect theo đối tượng?

Giả sử một ứng dụng quản lý hai worker A và B. Ta muốn đếm riêng số lần hoạt động được quan sát trên từng worker.

~~~text
A.run("x")
A.run("y")
B.run("z")
~~~

Nếu aspect có duy nhất một bộ đếm, các lần được đánh số 1, 2 và 3. Nếu muốn **đếm theo từng object**, kết quả phải là A #1, A #2 và B #1.

Bài toán không nằm ở cú pháp advice chạy trước hay sau, mà ở **vòng đời của instance giữ trạng thái advice**. Có hệ AOP hỗ trợ gắn instance của aspect với mỗi object thỏa điều kiện; hệ khác chỉ đưa ra interceptor chung, buộc người triển khai tự quản lý state.

Điểm cần nhớ: **mỗi object một state** không đồng nghĩa **mỗi lần gọi tạo một state mới**. Các lời gọi của cùng object thường muốn **tái sử dụng** state của object ấy.

## 2. Ba cấp độ cần tách bạch

| Cấp độ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Aspect type** | Định nghĩa mối quan tâm xuyên suốt và advice | Một loại aspect Counter |
| **Aspect instance** | Một đối tượng cụ thể chứa trạng thái của aspect type | Counter dành riêng cho A |
| **Advice invocation** | Một lần advice chạy tại điểm được chọn | Lần gọi A thứ hai |

Sơ đồ:

~~~text
CounterAspect (định nghĩa)
     |
     +--- Aspect instance for A: count=2
     |           |              |
     |       invocation 1   invocation 2
     |
     +--- Aspect instance for B: count=1
                 |
             invocation 1
~~~

Nếu nhầm aspect instance với advice invocation, người viết dễ tạo mới bộ đếm ở mọi lần gọi khiến số luôn bằng 1. Nếu nhầm aspect instance với aspect type, người viết có thể dùng biến static và làm trộn trạng thái A/B.

## 3. Các khái niệm AOP liên quan

**Join point** là điểm/sự kiện trong mô hình thực thi mà cơ chế AOP có thể nhận diện. **Pointcut** là điều kiện chọn các điểm ấy. **Advice** là hành vi bổ sung. **Weaving** hoặc một cơ chế interception tương ứng giúp advice được thực thi ở đúng ranh giới. **Aspect instance lifecycle** quyết định instance nào được sử dụng khi advice chạy.

Cần trả lời bốn câu khác nhau:

1. Công cụ có hỗ trợ loại join point cần quan sát không?
2. Pointcut có chọn điểm trong lần thực thi này không?
3. Đường gọi có đi qua proxy hoặc mã đã được dệt không?
4. Nếu advice chạy, aspect instance nào nhận lời gọi?

Một registry theo target chỉ giải câu số 4. Nó không thể tạo thêm một loại join point mà công cụ không hỗ trợ, cũng không làm lời gọi trực tiếp tới target tự quay qua proxy.

## 4. Những chiến lược vòng đời thường gặp

| Chiến lược | Phạm vi dùng chung state |
|---|---|
| Singleton | Một instance chung trong phạm vi do mô hình xác định |
| Per-object | Một instance cho mỗi object đủ điều kiện |
| Per-target | Một instance theo object đóng vai target của join point |
| Per-this | Một instance theo object đóng vai this của join point |
| Per-proxy | Một state riêng cho từng đối tượng proxy hoặc wrapper |
| Per-invocation | Một state/context mới cho mỗi lần thực thi |
| Per-control-flow | Một state cho phạm vi luồng điều khiển được chọn |
| Per-type | Một instance theo type/phạm vi type |

Các tên per-this và per-target là thuật ngữ có thể gặp trong một số ngôn ngữ AOP; **không có bảo đảm mọi công cụ đều công khai chính xác cùng cách khởi tạo**.

Một aspect quan sát thời gian có thể dùng state **per-object** để lưu tổng thời lượng và state **per-invocation** để lưu mốc bắt đầu từng lần gọi. Hai vòng đời có thể cùng tồn tại trong một thiết kế.

## 5. Singleton aspect khác per-object

Một singleton có thể chứa:

~~~text
total = 0
on every selected join point:
    total = total + 1
~~~

Khi A gọi hai lần và B gọi một lần, tổng là 3. Đây là kết quả đúng nếu mục tiêu là **thống kê toàn cục**.

Nếu mục tiêu là thống kê theo object, cần có association theo A và B. Một singleton chứa map từ object sang state có thể **mô phỏng một phần** hành vi per-object, nhưng vẫn phải tự giải quyết danh tính object, cleanup, concurrency và thời điểm tạo mapping.

Không mặc định singleton-with-map hoàn toàn tương đương với cơ chế per-object aspect instantiation bản địa: bộ máy AOP có thể quy định những thời điểm association khác, API tra cứu aspect instance khác và cách garbage collection khác.

## 6. Per-this và per-target có thể là hai chính sách khác nhau

Một số mô hình join point phân biệt:

- **This**: object được mô hình gọi là this tại join point.
- **Target**: object được mô hình gọi là target/receiver.

Ở một method-call join point, this có thể liên quan object đang thực thi lời gọi, trong khi target là receiver được gọi. Tại method-execution join point, hai vai trò có thể khác hoặc trùng theo quy tắc của mô hình.

~~~text
Caller C   -------- call -------->   Target T
    |                                 |
  per-this(C)                       per-target(T)
~~~

Vì vậy per-this không tự đồng nghĩa per-target. Đặc biệt, **this của một join point** không nhất thiết là biến Java this trong đoạn mã đang được người đọc nhìn tới.

Một số loại join point không có receiver instance thích hợp, ví dụ static method. Không nên giả định mọi điểm đều có object target để gắn một aspect instance.

## 7. Per-proxy khác per-target

Hai proxy có thể ủy quyền cho cùng một đối tượng nghiệp vụ A.

~~~text
Proxy P1 -----+
              +----> Target A
Proxy P2 -----+
~~~

Nếu state nằm bên trong P1 và P2, mỗi proxy có thể đếm riêng từ 1. Nếu chính sách là **một aspect instance duy nhất theo A**, cả hai proxy cần dùng chung một association theo target identity.

Một chuỗi proxy bọc proxy cũng đặt ra câu hỏi proxy nào được xem là target ở mỗi tầng. Không được gọi chung “per-object” mà không nói rõ **object làm khóa** là proxy gần nhất, target cuối cùng hay object this trong join point model.

## 8. Per-invocation khác per-object

Per-object state tồn tại qua nhiều lời gọi của cùng một đối tượng. Per-invocation state chỉ dành cho một lần xuất hiện động.

Ví dụ:

~~~text
State gắn Worker A:
    totalCalls = 12
    totalDurationNanos = 10000000

Lần gọi hiện tại:
    startNanos
    currentError
    safeArgumentSummary
~~~

Nếu đưa startNanos của từng lần gọi vào một trường chung của aspect A, hai lời gọi đồng thời hoặc lồng nhau có thể ghi đè mốc thời gian của nhau.

Giải pháp là giữ trạng thái tạm **trong local variable hoặc invocation context**, còn số liệu tổng hợp có thể ở aspect instance theo đối tượng.

## 9. Per-control-flow, per-type và per-thread

**Per-type** gắn state theo class hoặc một phạm vi kiểu, không theo từng instance của class. Hai đối tượng khác nhau cùng loại có thể dùng chung state type.

**Per-control-flow** gắn state với một lần thực thi trong vùng luồng điều khiển đã được chọn, không phải với một object sống lâu qua nhiều request.

**Per-thread** gắn state theo thread; một thread pool có thể dùng cùng thread cho nhiều request, còn một hoạt động bất đồng bộ có thể di chuyển qua nhiều thread.

~~~text
Thread T1: A.run(), B.run()
Thread T2: A.run()

Per-object:  hai lời gọi A có thể dùng chung State A
Per-thread:  T1 và T2 không dùng chung thread state
Per-call:    mỗi run có context riêng
~~~

Không sử dụng ThreadLocal làm giải pháp per-target mặc định: ThreadLocal trả lời câu hỏi “đang ở thread nào”, không phải “đang thao tác object nào”.

## 10. Vòng đời bắt đầu khi nào?

Một mô hình instantiation theo object có thể hoạt động lazily:

~~~text
T0: Target A được tạo
T1: A tồn tại, chưa có join point khớp
T2: Một join point thỏa điều kiện association trên A
T3: Aspect instance của A được tạo hoặc truy xuất
T4: Advice chạy bằng instance đó
T5: Những lần phù hợp sau dùng lại instance
T6: Không còn association theo hợp đồng → có thể thu hồi
~~~

Đây là **một mô hình khái niệm**, không phải trình tự bắt buộc của mọi engine.

Không nên suy rằng mỗi lần new target sẽ lập tức new aspect instance. Một công cụ có thể chỉ khởi tạo khi pointcut tạo association khớp lần đầu. Có thể có object chưa bao giờ được liên kết vì nó không phát sinh điểm tương ứng.

## 11. Pointcut tạo association có thể khác pointcut chạy advice

Một số mô hình phân biệt:

1. **Điều kiện để tạo hoặc gắn aspect instance với object**.
2. **Những join point mà advice trong instance ấy cần chạy**.

Pseudocode:

~~~text
associationCondition:
    target là Worker
    AND có lần thực thi run(...) phù hợp

adviceCondition:
    một điểm thao tác khác trên target đã được liên kết
~~~

Đây không phải cú pháp của công cụ AOP cụ thể.

Điều này ảnh hưởng giải thích trường hợp object A đã tồn tại lâu nhưng advice vẫn chưa có state; có thể association pointcut chưa bao giờ khớp. Ngược lại, aspect instance đã tồn tại cũng không có nghĩa mọi method của A đều được advice chọn.

## 12. Ví dụ Java 17 số 1: một state trên mỗi wrapper

Ví dụ đầu tiên dùng decorator thuần Java để chứng minh hai wrapper của cùng target **không tự dùng chung bộ đếm**.

Lưu **PerWrapperLifecycleDemo.java**:

~~~java
public class PerWrapperLifecycleDemo {
    interface Task {
        String run(String value);
    }

    static final class RealTask implements Task {
        private final String name;

        RealTask(String name) {
            this.name = name;
        }

        @Override
        public String run(String value) {
            System.out.println("[business] " + name + " " + value);
            return name + ":" + value;
        }
    }

    static final class ObservedTask implements Task {
        private final Task target;
        private final String wrapperName;
        private int calls;

        ObservedTask(Task target, String wrapperName) {
            this.target = target;
            this.wrapperName = wrapperName;
        }

        @Override
        public String run(String value) {
            int number = ++calls;
            System.out.println("[advice " + wrapperName
                    + "] before #" + number);
            try {
                return target.run(value);
            } finally {
                System.out.println("[advice " + wrapperName
                        + "] after #" + number);
            }
        }
    }

    public static void main(String[] args) {
        Task target = new RealTask("A");
        Task w1 = new ObservedTask(target, "W1");
        Task w2 = new ObservedTask(target, "W2");

        System.out.println("[caller] " + w1.run("x"));
        System.out.println("[caller] " + w1.run("y"));
        System.out.println("[caller] " + w2.run("z"));
    }
}
~~~

Chạy:

~~~bash
javac PerWrapperLifecycleDemo.java
java PerWrapperLifecycleDemo
~~~

**Stdout:**

~~~text
[advice W1] before #1
[business] A x
[advice W1] after #1
[caller] A:x
[advice W1] before #2
[business] A y
[advice W1] after #2
[caller] A:y
[advice W2] before #1
[business] A z
[advice W2] after #1
[caller] A:z
~~~

### 12.1. Giải thích

Cả W1 và W2 ủy quyền cho cùng target A, nhưng trường calls nằm **trong mỗi wrapper**. Vì thế W1 đi tới #2, còn W2 bắt đầu #1.

Đây là **per-wrapper**, không tự là per-target. Nếu chính sách yêu cầu state duy nhất cho A, phải bảo đảm chỉ dùng một wrapper hoặc có cơ chế liên kết state chung theo đúng target A.

### 12.2. Lưu ý về finally và đồng thời

Finally chạy khi hoạt động rời phạm vi normal/exceptional trong trường hợp unwinding thông thường. Nó không hứa chạy nếu tiến trình bị kết thúc cưỡng bức hoặc hoạt động không bao giờ thoát. Nếu chính logging trong finally ném lỗi, nó còn có thể che ngoại lệ gốc.

Trường int calls trong ví dụ không thread-safe. Bài minh họa lời gọi tuần tự để stdout xác định, không nên dùng phép ++calls không đồng bộ trong hệ nhiều thread.

## 13. Ví dụ Java 17 số 2: registry theo đúng target identity

Bây giờ hai proxy khác nhau phải cùng truy xuất state nếu chúng trỏ tới **cùng object target**. Chúng ta dùng **IdentityHashMap** có đồng bộ để phân biệt object identity với equals.

**Đây là Java thuần mô phỏng association theo target**, không phải engine AOP tự dệt bytecode. Registry dùng strong references và cần release tường minh.

Lưu **PerTargetRegistryDemo.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.IdentityHashMap;

public class PerTargetRegistryDemo {
    interface Job {
        String run(String value);
    }

    static final class JobImpl implements Job {
        private final String name;

        JobImpl(String name) {
            this.name = name;
        }

        @Override
        public String run(String value) {
            System.out.println("[business] " + name + " " + value);
            return name + ":" + value;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof JobImpl;
        }

        @Override
        public int hashCode() {
            return 17;
        }
    }

    static final class State {
        private int calls;

        synchronized int next() {
            return ++calls;
        }
    }

    static final class Registry {
        private final IdentityHashMap<Job, State> states =
                new IdentityHashMap<>();

        synchronized State stateFor(Job target) {
            State state = states.get(target);
            if (state == null) {
                state = new State();
                states.put(target, state);
            }
            return state;
        }

        synchronized void release(Job target) {
            states.remove(target);
        }

        synchronized int size() {
            return states.size();
        }
    }

    static Job wrap(Job target, String label, Registry registry) {
        return (Job) Proxy.newProxyInstance(
                Job.class.getClassLoader(),
                new Class<?>[] {Job.class},
                (proxy, method, args) -> {
                    int n = registry.stateFor(target).next();
                    System.out.println("[advice] " + label + " #" + n);
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException e) {
                        throw e.getCause();
                    }
                }
        );
    }

    public static void main(String[] args) {
        Registry registry = new Registry();
        JobImpl a = new JobImpl("A");
        JobImpl b = new JobImpl("B");

        System.out.println("a.equals(b)=" + a.equals(b));

        Job a1 = wrap(a, "A", registry);
        Job a2 = wrap(a, "A", registry);
        Job b1 = wrap(b, "B", registry);

        System.out.println("[caller] " + a1.run("x"));
        System.out.println("[caller] " + a2.run("y"));
        System.out.println("[caller] " + b1.run("z"));
        System.out.println("registry size=" + registry.size());

        registry.release(a);
        System.out.println("registry size after release A="
                + registry.size());

        System.out.println("[caller] " + a1.run("again"));
        System.out.println("registry size end=" + registry.size());
    }
}
~~~

Chạy:

~~~bash
javac PerTargetRegistryDemo.java
java PerTargetRegistryDemo
~~~

**Stdout:**

~~~text
a.equals(b)=true
[advice] A #1
[business] A x
[caller] A:x
[advice] A #2
[business] A y
[caller] A:y
[advice] B #1
[business] B z
[caller] B:z
registry size=2
registry size after release A=1
[advice] A #1
[business] A again
[caller] A:again
registry size end=2
~~~

### 13.1. Tại sao A có #1 rồi #2?

Hai proxy a1 và a2 dùng chung target object a. Registry tra cứu bằng đúng reference a, vì thế cả hai lời gọi dùng chung State A.

B là object khác, có State B và bắt đầu #1. Đây là hành vi **per-target** được tự định nghĩa rõ trong demo.

### 13.2. Tại sao a.equals(b) bằng true vẫn tạo hai state?

Phương thức equals trong demo cố tình coi mọi JobImpl là bằng nhau. Nhưng A và B không phải cùng reference. IdentityHashMap dùng **identity** chứ không dùng logical equality, vì vậy tách riêng state của hai object.

Override equals như vậy chỉ nhằm dạy khác biệt; không phải mẫu equality nên dùng trong phần mềm thực tế.

### 13.3. Tại sao release rồi A chạy lại có #1?

registry.release(a) gỡ association cũ, nhưng target a và proxy a1 vẫn tồn tại. Khi a1.run("again") gọi registry.stateFor(a), một State A mới được tạo, nên số đếm bắt đầu lại.

Bài học: **thời điểm release phải phù hợp với vòng đời sử dụng**, không chỉ kết thúc một lời gọi. Nếu release quá sớm, object đang sống có thể bị gắn lại state mới và mất lịch sử quan sát.

### 13.4. Giới hạn của registry demo

IdentityHashMap giữ strong reference tới target. Nếu không release, target/state có thể sống lâu hơn cần thiết. synchronized bảo vệ thao tác trên map và việc tăng đếm, nhưng không tự cung cấp giao thức release an toàn khi có in-flight invocations. Handler chỉ quan sát những lời gọi **đi qua proxy**.

Object methods như equals, hashCode và toString của proxy có thể được chuyển tới handler theo cơ chế Java Dynamic Proxy; ví dụ chỉ gọi run trên proxy. Production handler phải xử lý riêng những method ấy và tránh recursion.

## 14. Identity khác equality và business ID

Có ba cách nhận diện thường bị trộn:

1. **Reference identity:** a và b thật sự là cùng object; kiểm tra bằng ==.
2. **Logical equality:** a.equals(b) là true theo implementation.
3. **Business identity:** hai object có thể cùng mã tài khoản, đơn hàng hoặc entity ID.

Một per-object lifecycle theo reference identity sẽ coi hai instance khác nhau là hai đối tượng, ngay cả khi chúng có cùng business ID.

Nếu nghiệp vụ yêu cầu trạng thái chung theo entity ID, đó là một **chính sách keyed by business identity**, không nên tự gọi là per-object runtime instance. ID có thể bị tái sử dụng hoặc đại diện nhiều bản sao object trong nhiều request.

## 15. Strong references và rò rỉ bộ nhớ

Một singleton registry chứa map với strong keys có thể giữ sống hàng nghìn target đã không còn được ứng dụng dùng:

~~~text
Registry
   |
   +---strong---> Target A
   |
   +---strong---> State A
~~~

Garbage collector không thể thu hồi Target A nếu Registry vẫn có strong reference. Đây là điểm dễ bỏ qua khi dùng per-target state.

Có thể quản lý bằng explicit release, scope được đóng đúng lúc hoặc một dạng association yếu phù hợp nếu công cụ/cấu trúc dữ liệu hỗ trợ. Không được suy rằng bộ máy AOP tự dọn mọi per-object instance khi target hết được dùng.

## 16. WeakHashMap không mặc nhiên là weak identity map

WeakHashMap của Java sử dụng **weak keys** nhưng vẫn so sánh khóa theo **equals/hashCode**. Nó khác IdentityHashMap.

Cần chú ý:

- Hai object equals=true vẫn có thể bị gộp theo một entry.
- Value có thể giữ strong reference tới chính key, làm key không được thu hồi.
- WeakHashMap không tự thread-safe.
- GC không chạy vào thời điểm xác định.
- Entry biến mất vì GC không phải callback đáng tin để đóng resource.

Nếu yêu cầu là weak association **theo reference identity**, cần cấu trúc riêng có weak reference, cơ chế so sánh identity, xử lý key đã bị thu hồi và thread safety, hoặc dùng cơ chế của công cụ đã được kiểm chứng.

## 17. Garbage collection không thay thế close/release

Không nên dựa vào lúc target hoặc aspect instance bị GC để:

- Đóng connection/socket/file ở thời điểm bắt buộc.
- Cam kết ghi audit cuối cùng.
- Commit/rollback transaction.
- Giải phóng ngay tài nguyên có quota.
- Báo rằng toàn bộ nghiệp vụ đã kết thúc.

GC có thời điểm không xác định. Một resource cần cleanup đúng thời điểm phải có scope hoặc close/release tường minh. Per-object aspect lifecycle giải quyết **association của state**, không phải mọi loại vòng đời tài nguyên.

## 18. Đồng thời trên cùng target

Hai thread cùng gọi target A có thể dùng chung một aspect instance A.

~~~text
Thread T1: A.run("x")
Thread T2: A.run("y")
~~~

Nếu aspect state chứa int calls và dùng ++calls không đồng bộ, số cuối có thể mất cập nhật. Có thể dùng AtomicInteger cho bộ đếm đơn giản hoặc synchronized/lock cho invariant phức tạp.

Per-object **không đồng nghĩa per-thread**. Mỗi object có một state không có nghĩa state chỉ được một thread chạm tới.

### 18.1. Synchronized không giải quyết mọi release race

Một thread có thể lấy State A, thread khác release mapping, rồi thread thứ ba tạo State A mới. Trong lúc đó có thể có hai state đang được sử dụng cho cùng một target.

Nếu hợp đồng cần bảo đảm tuyệt đối một state cho mọi in-flight call, phải có quy tắc quản lý lifetime, shutdown hoặc khóa theo scope, không chỉ synchronized cho từng method tra map.

## 19. Lời gọi lồng nhau và reentrancy

Một target A có thể chạy outer rồi gọi inner:

~~~text
A.outer()
    -> A.inner()
~~~

Nếu cả hai được advice quan sát trên cùng aspect A, việc lưu currentStartTime hay currentArguments trong một field đơn giản của aspect sẽ bị lời gọi trong ghi đè.

Vì vậy dùng **local variable hoặc per-invocation context** cho dữ liệu lần gọi. Chỉ lưu **aggregate counters** hay trạng thái lâu dài trong aspect A và bảo vệ cập nhật khi cần.

Lỗi reentrancy có thể xuất hiện ngay trên một thread, không đòi hỏi đồng thời nhiều thread.

## 20. Self-invocation và giới hạn của proxy

Với một interface proxy, client gọi proxy.outer(), handler chuyển tiếp tới target.outer(); bên trong target dùng this.inner() thì lời gọi inner thường **không đi qua proxy**.

~~~text
Client -> Proxy -> Target.outer()
                       |
                       +-> this.inner()
~~~

Registry per-target có thể hoạt động đúng nhưng không thấy một advice invocation riêng cho inner.

Một cơ chế weaving ở method execution có thể quan sát inner nếu mã liên quan đã được dệt. Một subclass proxy có thể có tình huống virtual dispatch quay tới override trên proxy instance. Vì vậy không tuyên bố mọi self-invocation đều bỏ qua mọi loại AOP.

Cần kiểm tra **join point model, dispatch và runtime path**, không chỉ association map.

## 21. Pointcut và vòng đời là hai tầng độc lập

Một aspect per-target instance không có nghĩa mọi method của target sẽ được advice quan sát.

Nếu pointcut chỉ chọn run(...) mà target còn có getName(), getState() và reset(), những lời gọi không khớp không tự tạo advice invocation. Một cơ chế cũng có thể chọn kiểu method execution mà proxy chỉ cung cấp interception ở lời gọi interface.

Nếu object A chưa có một join point khớp pointcut tạo association, instance aspect của nó có thể **chưa được tạo** trong mô hình lazy.

Không dùng wildcard pointcut để bù cho loại join point mà công cụ không hỗ trợ: biểu thức rộng không biến constructor/field access thành method interception.

## 22. Vấn đề dữ liệu riêng tư và state lâu dài

Một per-object aspect có thể tồn tại lâu và giữ tham chiếu tới object, đối số hoặc ngoại lệ. Việc đó có rủi ro:

- Giữ dữ liệu bí mật trong heap lâu hơn cần thiết.
- Vô tình lưu toàn bộ object graph lớn.
- Lưu Throwable có stack trace hoặc tham chiếu tới các object khác.
- Dùng business ID nhạy cảm làm metric label.
- Nhầm trạng thái nghiệp vụ cốt lõi với trạng thái quan sát.

Nên lưu dữ liệu tối thiểu như count, aggregateDuration hoặc mã lỗi đã chuẩn hóa. Những đối số, exception và mốc thời gian **của lần gọi hiện tại** nên ở scope ngắn hạn.

Đừng dùng aspect per-object để ẩn các quy tắc nghiệp vụ bắt buộc trong một ranh giới proxy có thể bị bỏ qua.

## 23. Một aspect instance có thể bị gọi lại bao nhiêu lần?

Cần phân biệt ba bộ đếm:

- **Số lần join point được chọn và advice chạy.**
- **Số lần continuation/proceed được gọi.**
- **Số lần phần gốc thực sự thực thi.**

Một around advice có thể short-circuit, không gọi proceed. Một advice khác có thể retry phần tiếp theo khi được cơ chế cho phép. Do đó một lần advice không nhất thiết tương ứng một lần chạy phần gốc.

Nếu aspect per-object dùng counter để đo nghiệp vụ, hãy xác định đang đếm **sự kiện nào**, đồng thời kiểm tra return value, exception và thứ tự nhiều advice.

## 24. Tương tác nhiều aspect với vòng đời khác nhau

Một lần method execution có thể được quan sát bởi:

~~~text
Singleton Metrics Aspect
     |
Per-target Counter Aspect
     |
Control-flow Trace Aspect
     |
Original method
~~~

Sơ đồ là một thứ tự minh họa, không phải thứ tự mặc định của các hệ AOP.

Aspect singleton có thể đo tổng số lượt, per-target giữ thống kê A/B riêng, còn control-flow giữ correlation context của một yêu cầu. Khi một around advice bao ngoài short-circuit, advice bên trong có thể không chạy và một association chưa chắc được tạo.

Không suy số lần aspect instance được tạo từ số lần advice xuất hiện nếu chưa xác minh chính sách instantiation và nesting.

## 25. Ma trận kiểm thử per-object lifecycle

| Tình huống | Kỳ vọng kiểm chứng |
|---|---|
| A gọi hai lần | Cùng State A được dùng lại |
| B gọi lần đầu | State B độc lập, bắt đầu từ 1 |
| Hai proxy cùng target A | Chia sẻ hay tách state đúng thiết kế |
| Hai target equals=true nhưng identity khác | Nếu yêu cầu identity, phải có hai state |
| Object chưa khớp join point tạo association | Lazy instance có được tạo đúng thời điểm? |
| Release rồi gọi lại A | Reassociation/reset đúng hợp đồng |
| A được gọi đồng thời | Counter/invariant không hỏng |
| A có lời gọi lồng nhau | Context per-invocation không ghi đè |
| Caller gọi target trực tiếp | Độ bao phủ đúng với proxy/weaver thực tế |
| Self-invocation | Có hay không có join point độc lập đúng mô hình |
| Exception từ phần gốc | Advice không tự nuốt hoặc thay lỗi ngoài chủ đích |
| Object hết được dùng | Association không giữ sống mãi nếu mục tiêu cần thu hồi |

Unit test cho registry chỉ chứng minh **association logic**. Cần integration test với công cụ AOP thực để chứng minh **độ bao phủ join point**.

## 26. Những lỗi phổ biến

**Lỗi 1 — State mới mỗi lần gọi:** mọi invocation bắt đầu từ 1; đó là per-call, không phải per-target.

**Lỗi 2 — Biến static chung:** A và B dùng cùng counter dù cần số riêng.

**Lỗi 3 — Nhầm proxy identity với target identity:** hai proxy cùng target vẫn có hai bộ state.

**Lỗi 4 — HashMap thay IdentityHashMap:** hai object logical equals bị gộp không đúng ngữ nghĩa.

**Lỗi 5 — WeakHashMap như weak-identity map:** weak key không làm thay đổi equality semantics.

**Lỗi 6 — Registry strong keys không cleanup:** giữ object sống và gây memory leak.

**Lỗi 7 — Dựa vào GC đóng resource:** không có thời điểm bảo đảm.

**Lỗi 8 — currentStartTime là field dùng chung của aspect:** lời gọi đồng thời/lồng nhau ghi đè.

**Lỗi 9 — Release khi vẫn còn in-flight calls:** hai state khác nhau có thể tồn tại trong một khoảng thời gian.

**Lỗi 10 — Nhầm this và target:** association theo caller khác association theo receiver.

**Lỗi 11 — Quên đường gọi bỏ qua proxy:** thiếu advice invocation dù nghiệp vụ đã chạy.

**Lỗi 12 — Mặc định aspect được tạo cùng target constructor:** có mô hình tạo lazy theo join point phù hợp.

**Lỗi 13 — Lưu raw arguments và Throwable mãi:** dữ liệu nhạy cảm/object graph bị giữ lâu.

**Lỗi 14 — Dùng per-object aspect làm hàng rào bảo mật duy nhất:** pointcut/weaving path có thể không bao phủ mọi entry point bắt buộc.

## 27. Lưu ý hiệu năng và số lượng aspect instance

Nếu ứng dụng có vài object sống lâu, per-object state thường dễ hiểu. Nếu có hàng trăm nghìn object ngắn hạn, mỗi object được liên kết một state có thể tạo chi phí đáng kể:

- Cấp phát state mới và lookup mapping.
- Đồng bộ trong registry.
- Retention của target và dữ liệu liên quan.
- GC, heap footprint và cleanup.
- Logging/metrics có cardinality quá lớn.
- Tăng chi phí đối với method có tần suất gọi cao.

Đừng dùng per-object khi chỉ cần một bộ đếm chung theo loại operation. Ngược lại, nếu requirement cần state độc lập theo target thật sự, đừng thay bằng singleton global chỉ vì rẻ hơn.

Có thể đo số association còn sống, tốc độ tạo state, heap/GC pressure, contention và chênh lệch giữa số lần nghiệp vụ và số lần advice.

## 28. Quy trình thiết kế một aspect theo đối tượng

1. Xác định rõ state thuộc về object runtime nào.
2. So sánh per-object với singleton, per-type và per-call.
3. Xác định join point được công cụ hỗ trợ.
4. Xác định this/target/proxy identity theo mô hình.
5. Chọn điều kiện pointcut tạo association.
6. Xác định instance tạo sớm hay lazy.
7. Xác định các advice dùng lại state.
8. Xác định cấu trúc registry hoặc cơ chế instantiation của AOP.
9. Xác định lifecycle cleanup/release và garbage collection.
10. Tách aggregate state khỏi per-invocation context.
11. Thiết kế đồng thời, nested calls và release khi đang hoạt động.
12. Kiểm thử hai proxy cùng target.
13. Kiểm thử equals=true nhưng object identity khác.
14. Kiểm thử các đường ngoài proxy/weaving.
15. Đảm bảo advice quan sát không đổi return/exception ngoài chủ đích.
16. Đo chi phí vận hành và viết rõ giới hạn chưa được cam kết.

## 29. Câu hỏi tự kiểm tra

### Câu 1: Hai proxy cùng target

P1 và P2 cùng bọc A, mỗi proxy có bộ đếm riêng. Sau một lần gọi qua mỗi proxy, có chắc counter target A là 2 trong một state chung không?

**Đáp án:** không. Có thể P1 là 1 và P2 là 1; đó là per-wrapper.

### Câu 2: Equals và identity

A và B được tạo riêng, nhưng equals trả true. Nếu lifecycle theo reference identity, chúng có dùng chung state không?

**Đáp án:** không. IdentityHashMap giúp mô phỏng sự phân biệt đó.

### Câu 3: Aspect khởi tạo lúc target new

Có bắt buộc mọi per-object aspect instance xuất hiện ngay khi object target được tạo không?

**Đáp án:** không. Nhiều mô hình có thể tạo lazily khi join point phù hợp khớp.

### Câu 4: Strong key registry

Một singleton registry giữ target làm strong key. Nếu không release, target có thể bị giữ sống không?

**Đáp án:** có. Registry giữ tham chiếu tới target.

### Câu 5: Hai thread và một counter

Hai thread cùng cập nhật trường int calls bằng ++calls. Có bảo đảm tăng hai lần không?

**Đáp án:** không. Cần atomic/synchronized phù hợp.

### Câu 6: Per-this và per-target

Một method-call join point có caller C và target T. Có chắc per-this và per-target chọn cùng object không?

**Đáp án:** không. Phụ thuộc mô hình join point.

### Câu 7: Self-invocation

Một proxy bọc A.outer(), bên trong target gọi this.inner(). Không thấy advice inner; có chắc inner không chạy?

**Đáp án:** không. Có thể là lời gọi nội bộ không qua proxy.

### Câu 8: Thời gian bất đồng bộ

Advice đo thời gian từ vào method tới khi method trả một future. Đây có phải thời gian thực sự hoàn tất công việc không?

**Đáp án:** không. Cần một ranh giới hoàn tất của tác vụ nếu muốn đo vòng đời công việc.

### Câu 9: Cleanup bằng GC

Có nên trông chờ per-object aspect bị GC để đóng transaction đúng lúc?

**Đáp án:** không. GC không có thời điểm xác định; cleanup bắt buộc cần cơ chế tường minh.

### Câu 10: Singleton vs per-target

Một singleton với map theo target có thể tạo số đếm per-target. Có thể tuyên bố nó tương đương mọi ngữ nghĩa per-target instantiation của AOP không?

**Đáp án:** không. Cần kiểm tra thời điểm association, API, identity, cleanup, pointcut và concurrency.

## 30. Kết luận

**Vòng đời per-object** là việc liên kết trạng thái hoặc instance aspect với **một đối tượng xác định**, trong phạm vi mà công cụ AOP thực sự hỗ trợ. Nó không đồng nghĩa một instance mỗi lần gọi, một instance mỗi proxy hay một instance mỗi thread.

Muốn làm đúng phải xác định ba tầng riêng:

1. **Loại join point và pointcut**: lần xuất hiện nào được chọn?
2. **Đường can thiệp**: lời gọi có thật sự đi qua proxy hoặc vùng mã đã weaving?
3. **Association và vòng đời**: state được gắn theo this, target, proxy hay identity khác; khi nào tạo, dùng lại và giải phóng?

Per-object state có thể hữu ích cho số liệu hoặc policy riêng của từng đối tượng, nhưng mang theo trách nhiệm về concurrency, reentrancy, strong/weak references, memory leak và cleanup. Khi hiểu rõ các ranh giới đó, người thiết kế có thể lựa chọn giữa cơ chế per-object có sẵn của công cụ và một giải pháp registry/decorator có hợp đồng tường minh, thay vì phụ thuộc vào giả định “mỗi object tự động có một aspect”.

**Câu hỏi cần trả lời khi đánh giá thiết kế:** *“Aspect instance này thuộc về object nào, sự kiện nào tạo liên kết đó, những lời gọi nào được dùng lại state, và điều gì đảm bảo liên kết không tồn tại quá lâu hoặc biến mất quá sớm?”*

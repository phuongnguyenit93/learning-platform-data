# Giới hạn hành vi theo chuỗi lời gọi thay vì vị trí mã đơn lẻ

## 1. Tư duy cốt lõi: cùng một method, hành vi AOP có thể khác theo đường đi

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, một **pointcut** chọn những *join point* mà cơ chế AOP có thể can thiệp; **advice** định nghĩa hành vi chạy ở các điểm được chọn. Nhiều quy tắc quen thuộc chỉ xét vị trí mã hoặc chữ ký, ví dụ “mọi execution của method `reserve()`”. Nhưng trong thực tế, cùng `reserve()` có thể cần chính sách khác khi được gọi từ một quy trình **checkout** so với lúc chạy từ tác vụ bảo trì hoặc một API kiểm tra riêng.

Ví dụ:

~~~text
Đường A: checkout(orderId)       Đường B: nightlyRepair()
             |                            |
             v                            v
        validate()                     reserve()
             |
             v
          reserve()
             |
             v
          audit()
~~~

Tại những lần `reserve()`, **vị trí implementation có thể giống hệt nhau**, nhưng **ngữ cảnh gọi động** khác:

- Khi `reserve` nằm trong chuỗi lời gọi đang hoạt động bắt đầu từ `checkout`, ta có thể muốn gắn một trace span đặc biệt hoặc kiểm tra invariant dành riêng cho workflow checkout.
- Khi `reserve` chạy độc lập hoặc từ `nightlyRepair`, advice dành riêng cho checkout **không nên chạy**.

Ý tưởng **giới hạn hành vi theo chuỗi lời gọi (dynamic control-flow scoping)** là:

> Chọn một join point mục tiêu `Q` **chỉ khi** trong chuỗi lời gọi đang hoạt động có một join point gốc `P` đã được chọn, thay vì chỉ xét vị trí mã của `Q`.

Về mặt logic:

~~~text
Q  AND  insideDynamicControlFlow(P)
~~~

Ví dụ:

~~~text
Q = execution(reserve(..))
P = execution(checkout(..))

Chỉ quan sát reserve khi một checkout đang hoạt động ở chuỗi gọi hiện tại.
~~~

Đây là **mô hình khái niệm**, không phải cú pháp bắt buộc của mọi AOP engine. Một số ngôn ngữ pointcut gọi các phép chọn theo luồng động là `cflow(P)` và `cflowbelow(P)`; những công cụ khác có thể dùng tên/API hoặc cơ chế context propagation khác, hoặc không hỗ trợ tính năng này.

### Kết quả học tập

Sau bài này, có thể:

1. Phân biệt **bộ chọn theo vị trí mã** và **bộ chọn theo luồng điều khiển động**.
2. Xác định chính xác lúc một luồng `P` bắt đầu/kết thúc và join point `Q` nào thuộc luồng ấy.
3. Phân biệt logic bao gồm root (`cflow`) và loại trừ root hiện tại (`cflowbelow`).
4. Hiểu tác động của recursion, nested root, exception, proxy bypass và các thread/async boundary.
5. Mô phỏng cơ chế với Java 17, nhưng không nhầm simulation với một bytecode weaver thật.
6. Thiết kế advice có state theo flow an toàn về hiệu năng, đồng thời và cleanup.
7. Viết integration tests chứng minh điểm nào **được chọn** và điểm nào **không được chọn**.

## 2. Vị trí mã tĩnh và chuỗi lời gọi động không cùng một câu hỏi

Một pointcut theo vị trí hoặc cấu trúc thường quan tâm:

- Loại join point: call hay execution, field get/set, constructor, v.v., nếu engine hỗ trợ.
- Kiểu/owner của method, method name, return type, parameters, modifiers.
- Annotation hoặc metadata được engine cung cấp.
- Vị trí lexical, chẳng hạn mã nằm trong một kiểu/khối nhất định.
- Quan hệ với caller được mô tả từ cấu trúc tĩnh trong những mô hình phù hợp.

Một pointcut theo control flow hỏi thêm:

- **Tại thời điểm join point này thực thi**, một lời gọi/root `P` nào đang ở **dynamic call stack**?
- Flow bắt đầu ở đâu và chưa kết thúc hay đã rời phạm vi?
- Mục tiêu `Q` có xảy ra khi flow đang active không?
- Nếu có nhiều root lồng nhau, `Q` thuộc root nào hoặc bao nhiêu root?

Bảng so sánh:

| Tiêu chí | Chọn theo vị trí/chữ ký | Chọn theo luồng điều khiển động |
| --- | --- | --- |
| Nguồn thông tin | Thường dựa trên join point tĩnh và metadata của nó | Dựa thêm vào lịch sử lời gọi **đang active** |
| Cùng method `reserve` từ hai workflow | Thường cùng match nếu signature giống | Có thể match ở checkout, không match ở repair |
| Cần biết root hiện tại đang nằm trên stack? | Không nhất thiết | Có |
| Matching tại build-time | Có thể đánh giá phần tĩnh sớm | Điều kiện flow thường phải đánh giá lúc chạy |
| Phạm vi bao phủ | Những join points được tool instrument/match | Giao của join points được instrument và điều kiện runtime |
| Async/thread hop | Phụ thuộc join point gốc/tầng mã | Phải xét propagation của ngữ cảnh động |
| Chi phí runtime | Có thể ít khi chỉ dùng matching tĩnh | Có thể phải duy trì depth/context hoặc kiểm stack |
| Nguy cơ | Match quá rộng theo chữ ký | Scope leak, nhầm flow, overhead và propagation sai |

**Luồng điều khiển động không bằng cây lời gọi tĩnh (static call graph).** Call graph mô tả những cạnh *có thể* xuất hiện; dynamic call stack chỉ phản ánh những khung lời gọi *đang thực thi*. Một path có trong source nhưng không đi qua ở request cụ thể thì không tự làm flow active.

## 3. Ba sơ đồ để đọc flow scope

### 3.1. Target chạy ngoài mọi root

~~~text
main
  └── reserve()           <- Q có, P=checkout không active
~~~

`Q` theo tên method match, nhưng `Q AND cflow(P)` là false.

### 3.2. Target chạy bên dưới root

~~~text
main
  └── checkout()          <- P bắt đầu
        ├── validate()
        ├── reserve()     <- Q trong flow P
        └── audit()       <- có thể là Q khác
      checkout() returns  <- P kết thúc
~~~

Khi `reserve()` chạy, `checkout()` vẫn còn ở dynamic call stack. Vì vậy điều kiện `cflow(P)` là true cho `reserve`; nếu target Q không trùng root, trường hợp này cũng là `cflowbelow(P)`.

### 3.3. Root đã return, target chạy lại

~~~text
main
  ├── checkout()          <- P đã kết thúc
  └── reserve()           <- Q sau đó, P không còn active
~~~

Một lời gọi `checkout` **đã từng** xảy ra không đủ để làm những lần `reserve` sau đó nằm trong flow checkout. Flow là phạm vi **động và có ranh giới thời gian**, không phải một cờ “đã gọi checkout một lần”.

## 4. Kết hợp root `P` và target `Q`

Cách xây pointcut nên tách hai vai trò:

- **P = root selector:** một loại join point mở phạm vi, ví dụ execution của `checkout(..)`.
- **Q = target selector:** một loại join point được advice muốn can thiệp, ví dụ execution của `reserve(..)`.
- **C = dynamic flow condition:** tại `Q`, có root `P` đang active không?

Ta cần **giao**:

~~~text
SelectedJoinPoints = Match(Q) ∩ WithinActiveFlow(P)
~~~

Một số phép logic hữu ích:

~~~text
Q AND cflow(P)
Q AND cflowbelow(P)
Q AND cflow(P1) AND NOT cflow(P2)
(Q1 OR Q2) AND cflow(P)
~~~

Đây là cú pháp **ý niệm**. Tính khả dụng của `AND`, `NOT`, `OR`, các biến/ngữ cảnh và sự ràng buộc tham số phụ thuộc ngôn ngữ pointcut thực tế. Tránh tự áp vào mọi engine.

### 4.1. Không nên đặt `P` quá rộng

Nếu `P` chọn một wrapper chung bao mọi request, gần như mọi `Q` trong ứng dụng đều ở trong flow. Khi đó điều kiện động không còn thu hẹp hữu ích mà còn thêm chi phí kiểm tra.

Nếu `P` quá hẹp hoặc bị proxy bypass, những flows thực tế cần được quan sát có thể không mở, làm advice không chạy.

### 4.2. Không nên đặt `Q` quá rộng

Một `Q` match **mọi method execution** bên trong checkout có thể tạo lượng event lớn, kể cả helper, logging, instrumentation và thư viện mà engine hỗ trợ. Điều này dễ tăng overhead và gây recursion của chính advice.

Hãy thu hẹp **cả P lẫn Q**, và có test âm (negative coverage) cho các loại join point không được phép.

## 5. Giao giữa target Q và luồng động P

Với một **root occurrence P duy nhất**, `cflow(P)` có thể chọn chính P và các join point bên trong; `cflowbelow(P)` chọn phần bên dưới, không chọn **chính occurrence bắt đầu phạm vi đó**. Khi có **P lồng trong P**, inner P lại là descendant của outer P, nên tại inner P điều kiện `cflowbelow(P)` có thể đúng. Không được rút gọn thành “loại mọi method có cùng tên P”.

~~~text
P checkout(outer)            cflow: có; below: không (nếu không có ancestor P)
  Q reserve()                cflow: có; below: có
  P checkout(inner)          cflow: có; below: có (do outer)
    Q reserve()              cflow: có; below: có
outside Q reserve()          cflow: không; below: không
~~~

## 6. Áp dụng vào đường nghiệp vụ thay vì chỉ dựa trên tên mã

Mục tiêu bài này là **cùng Q nhưng chỉ chọn khi một P cụ thể còn nằm trên đường gọi thực tế**. Ghép `Q AND cflow(P)` hoặc `Q AND cflowbelow(P)` nếu engine có designator đó, rồi kiểm tra cả luồng checkout và lời gọi Q từ workflow khác. Kết hợp **pointcut Q đủ hẹp** để tránh áp dụng advice lên mọi join point bên trong P. Một root P quá rộng khiến flow condition mất ý nghĩa chọn lọc.

Đây là mô tả ngữ nghĩa chung; call-vs-execution, nested roots, quyền binding và khả năng observe của proxy/weaving vẫn cần kiểm thử theo công nghệ. Trọng tâm tiếp theo là **thiết kế một chính sách theo đường đi thực**, không dạy lại bảng định nghĩa pointcut.

## 7. Ví dụ thực tế: bật audit riêng trong luồng checkout

Giả sử `reserve(resourceId)` là một API được tái sử dụng:

~~~text
API A:
  checkout() -> reserve() -> persist()

API B:
  performMaintenance() -> reserve() -> persist()
~~~

Nhu cầu: ghi audit `RESERVATION_IN_CHECKOUT` chỉ khi `reserve` được gọi từ checkout, nhưng không ghi event này khi reserve nằm trong maintenance.

Thay vì sao chép hai implementations `reserveForCheckout()` và `reserveForMaintenance()`, có thể mô tả:

~~~text
Q = execution(reserve)
P = execution(checkout)

observe(Q) only if cflow(P)
~~~

Ưu điểm:

- Target `reserve` không phải biết mọi workflow caller.
- Aspect có thể diễn đạt **ý định theo ngữ cảnh**, không theo package.
- Audit được giới hạn theo scope của logical operation cụ thể.
- Có thể quan sát nhiều join points Q bên trong cùng P.

Điều cần cân nhắc:

- Nếu yêu cầu audit mang tính bắt buộc về bảo mật, **không dựa duy nhất** vào flow có thể bị bỏ qua do proxy/raw target/cross-thread.
- Nếu luồng checkout gọi một API async, điều kiện control flow theo stack có thể không đi qua thread worker.
- Nếu `reserve` đồng thời được gọi ở một flow khác lồng trong checkout, dynamic scope vẫn có P trên stack; cần thêm điều kiện nếu đó không phải intent.

## 8. Ví dụ Java 17 hoàn chỉnh: root lồng nhau, lời gọi ngoài flow và ngoại lệ

Chương trình **CallFlowScopeDemo.java** dùng Java 17 và **JDK interface proxy** để mô phỏng hai lớp can thiệp:

1. Proxy cho `Checkout.checkout()` mở một flow scope bằng `Flow.inRoot()`.
2. Proxy cho `Steps.step()` kiểm tra có checkout root nào đang active ở **thread hiện tại** rồi in trạng thái pointcut điều kiện.
3. `CheckoutCore("outer")` gọi thêm `checkout("inner")` **qua proxy đã lắp**, tạo hai root lồng nhau.
4. `outer` cũng khởi tạo một thread mới gọi `Steps.step()`; thread mới không tự nhận context ThreadLocal của thread ngoài.
5. `checkout("bad")` ném exception, nhưng `finally` vẫn pop root và loại bỏ ThreadLocal khi stack rỗng.
6. Khi gọi `Steps.step()` bên ngoài checkout, condition flow là false.

**Lưu ý về ngữ nghĩa mô phỏng:** dòng `ROOT enter ... below=...` đo root hiện tại có **một root ancestor** hay không; còn `POINT step ... below=...` xem `step` là descendant không phải root, nên `below=true` khi có ít nhất một root active. Đây là phép minh họa các quan hệ `cflow`/`cflowbelow`, **không phải một implementation pointcut đầy đủ hay bytecode weaving**.

Tạo file `CallFlowScopeDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayDeque;
import java.util.Deque;

public final class CallFlowScopeDemo {
    @FunctionalInterface interface Action<T> { T run() throws Throwable; }
    interface Steps { void step(String name); }
    interface Checkout { String checkout(String id); }

    static final class Flow {
        private final ThreadLocal<Deque<String>> roots =
                ThreadLocal.withInitial(ArrayDeque::new);

        <T> T inRoot(String name, Action<T> action) throws Throwable {
            Deque<String> stack = roots.get();
            stack.push(name);
            System.out.println("ROOT enter " + name
                    + " cflow=true below=" + (stack.size() > 1)
                    + " depth=" + stack.size());
            try {
                return action.run();
            } finally {
                System.out.println("ROOT exit " + name);
                stack.pop();
                if (stack.isEmpty()) roots.remove();
            }
        }

        void report(String name) {
            Deque<String> stack = roots.get();
            boolean active = !stack.isEmpty();
            System.out.println("POINT step " + name
                    + " cflow=" + active
                    + " below=" + active
                    + " depth=" + stack.size());
            if (!active) roots.remove();
        }

        int depth() {
            Deque<String> stack = roots.get();
            int count = stack.size();
            if (count == 0) roots.remove();
            return count;
        }
    }

    static Object invoke(Object target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapper) {
            throw wrapper.getCause();
        }
    }

    static final class StepCore implements Steps {
        public void step(String name) {
            System.out.println("BODY step " + name);
        }
    }

    static Steps observe(Steps target, Flow flow) {
        return (Steps) Proxy.newProxyInstance(
                Steps.class.getClassLoader(),
                new Class<?>[] { Steps.class },
                (proxy, method, args) -> {
                    if ("step".equals(method.getName())) {
                        flow.report((String) args[0]);
                    }
                    return invoke(target, method, args);
                });
    }

    static final class CheckoutCore implements Checkout {
        private final Steps steps;
        Checkout nestedProxy;

        CheckoutCore(Steps steps) { this.steps = steps; }

        public String checkout(String id) {
            steps.step("begin-" + id);
            if ("outer".equals(id)) {
                System.out.println("NESTED result=" + nestedProxy.checkout("inner"));
                Thread child = new Thread(() -> steps.step("new-thread"));
                child.start();
                try {
                    child.join();
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("interrupted", error);
                }
            }
            if ("bad".equals(id)) {
                throw new IllegalArgumentException("invalid order");
            }
            steps.step("end-" + id);
            return "ok:" + id;
        }
    }

    static Checkout scope(Checkout target, Flow flow) {
        return (Checkout) Proxy.newProxyInstance(
                Checkout.class.getClassLoader(),
                new Class<?>[] { Checkout.class },
                (proxy, method, args) -> {
                    if (!"checkout".equals(method.getName())) {
                        return invoke(target, method, args);
                    }
                    String id = (String) args[0];
                    return flow.inRoot(id, () -> invoke(target, method, args));
                });
    }

    public static void main(String[] args) {
        Flow flow = new Flow();
        Steps steps = observe(new StepCore(), flow);
        CheckoutCore core = new CheckoutCore(steps);
        Checkout checkout = scope(core, flow);
        core.nestedProxy = checkout;

        steps.step("outside");
        System.out.println("RESULT " + checkout.checkout("outer"));
        steps.step("outside-again");

        try {
            checkout.checkout("bad");
        } catch (IllegalArgumentException error) {
            System.out.println("CAUGHT " + error.getMessage());
        }
        steps.step("after-error");
        if (flow.depth() != 0) {
            throw new AssertionError("flow leaked");
        }
        System.out.println("ASSERT depth=0");
    }
}
~~~

Biên dịch/chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 CallFlowScopeDemo.java
java CallFlowScopeDemo
~~~

**Đầu ra chính xác** đã được kiểm chứng bằng trình biên dịch và JVM:

~~~text
POINT step outside cflow=false below=false depth=0
BODY step outside
ROOT enter outer cflow=true below=false depth=1
POINT step begin-outer cflow=true below=true depth=1
BODY step begin-outer
ROOT enter inner cflow=true below=true depth=2
POINT step begin-inner cflow=true below=true depth=2
BODY step begin-inner
POINT step end-inner cflow=true below=true depth=2
BODY step end-inner
ROOT exit inner
NESTED result=ok:inner
POINT step new-thread cflow=false below=false depth=0
BODY step new-thread
POINT step end-outer cflow=true below=true depth=1
BODY step end-outer
ROOT exit outer
RESULT ok:outer
POINT step outside-again cflow=false below=false depth=0
BODY step outside-again
ROOT enter bad cflow=true below=false depth=1
POINT step begin-bad cflow=true below=true depth=1
BODY step begin-bad
ROOT exit bad
CAUGHT invalid order
POINT step after-error cflow=false below=false depth=0
BODY step after-error
ASSERT depth=0
~~~

### 8.1. Vì sao `outside` không thuộc flow?

`steps.step("outside")` được gọi khi không có `checkout()` qua root proxy đang active. `Flow.report` thấy stack rỗng, in `cflow=false below=false depth=0`. Target `StepCore.step` vẫn chạy.

Điều này cho thấy **không match flow không nhất thiết là không thực thi method nghiệp vụ**. Trong chương trình, proxy `Steps` vẫn quan sát vị trí gọi và in trạng thái `false` để học; một pointcut `Q AND cflow(P)` thực sự có thể chọn **không chạy advice chuyên biệt** trên những lời gọi ấy.

### 8.2. Vì sao root `outer` có `below=false`?

`Flow.inRoot("outer")` đẩy root đầu tiên vào stack, nên `depth=1`. Chính occurrence root đầu tiên thuộc `cflow(P)` nhưng **không nằm bên dưới một occurrence P khác**. Vì vậy `below=false` cho **root event**.

Sau đó `step("begin-outer")` là một join point Q khác root. Nó chạy **bên dưới checkout đang active**, vì vậy `below=true` dù chỉ có một root và `depth=1`.

### 8.3. Vì sao root `inner` có `below=true`?

`CheckoutCore` gọi `nestedProxy.checkout("inner")` từ bên trong `checkout("outer")`. Proxy root được vào lần nữa, stack có `["inner","outer"]`, `depth=2`.

`inner` vừa là root P của chính nó, vừa **nằm dưới root `outer`**, nên `cflowbelow(P)` có thể true ở inner-root. Đây là ca dễ làm lộ sai lầm `cflowbelow(P) = cflow(P) && !P`.

### 8.4. Vì sao thread mới có `cflow=false` dù được tạo trong checkout?

`outer` tạo một Java thread mới và gọi `steps.step("new-thread")` ở thread đó. `Flow` dùng `ThreadLocal` thông thường, nên thread con **không thừa hưởng root stack** của caller thread.

Nội dung `POINT step new-thread cflow=false...` là kết quả đúng với cơ chế mô phỏng này. Không nên suy rộng rằng **mọi** hệ AOP hoặc distributed tracing đều mất ngữ cảnh qua async: một số hệ thống có cơ chế explicit propagation hoặc mô hình flow khác. Phải biết chính xác hợp đồng của công nghệ đang dùng.

### 8.5. Vì sao flow không bị rò khi target ném lỗi?

`checkout("bad")` mở root, chạy một `step` rồi ném `IllegalArgumentException`. `Flow.inRoot()` dùng `finally` để pop root kể cả khi `action.run()` throw, và gọi `roots.remove()` khi stack rỗng.

Sau đó `steps.step("after-error")` lại có `cflow=false`; `ASSERT depth=0` xác nhận scope không còn active.

Nếu quên `finally/remove`, một thread pool worker được tái sử dụng có thể mang sai context từ request trước, gây **giới hạn hành vi sai** hoặc rò dữ liệu.

### 8.6. Proxy vs weaving trong ví dụ

- `scope(...)` là **JDK interface proxy**; root được mở vì caller thực sự gọi **`checkout` qua proxy**.
- `observe(...)` cũng là proxy; `step` được quan sát vì `CheckoutCore` giữ `Steps` proxy.
- Nếu caller giữ `CheckoutCore` raw hoặc tự tạo `StepCore` raw, lớp proxy tương ứng có thể bị bỏ qua.
- `nestedProxy` được truyền vào core để nested checkout đi qua root wrapper; gọi `this.checkout(...)` trong target thường bypass wrapper bên ngoài.
- Code mô phỏng này **không tự động nhận dạng join point bằng cú pháp pointcut và không biến đổi bytecode**.
- Một AOP engine dệt được `execution(checkout)` có thể có hành vi khác với proxy trước self-invocation, nhưng vẫn phải kiểm capability và scope thực.

**Bài học được kiểm chứng là điều kiện dynamic root stack và cleanup**, không phải bảo đảm mọi công cụ AOP có `ThreadLocal` implementation giống nhau.

## 9. Tại sao `ThreadLocal` hữu ích nhưng chưa đủ?

`ThreadLocal` cho phép mỗi thread có stack trạng thái riêng. Một stack thay vì một `boolean` đơn lẻ giúp xử lý nested roots:

~~~text
enter outer: [outer]
enter inner: [inner, outer]
exit inner:  [outer]
exit outer:  []
~~~

Nếu chỉ dùng `boolean active = true/false`:

~~~text
outer sets true
  inner sets true
  inner finally sets false  <- SAI: outer vẫn active
outer continues            <- bị hiểu là ngoài flow
~~~

Kỹ thuật có thể dùng:

- **Counter depth:** tăng tại root enter, giảm tại exit; đủ nếu chỉ cần biết có bao nhiêu roots cùng loại active.
- **Stack:** lưu identity/context của từng root, dùng khi cần đúng request ID, parent scope và nested lifecycle.
- **Immutable context token:** truyền rõ ràng qua các ranh giới async khi áp dụng.
- **Scoped execution context:** runtime abstraction có lifecycle rõ, khả năng propagate tùy API.
- **Instrumentation-provided state:** engine có thể tự quản lý flow, không cần ứng dụng viết ThreadLocal.

**Cleanup phải đối xứng**. Với `ThreadLocal` ở thread pool, `remove()`/restore previous value khi rời scope là quan trọng. Một value giữ payload, user info hoặc classloader lâu quá có thể tạo memory leak và lộ context giữa requests.

### 9.1. Tại sao không dùng một biến `static boolean`?

Vì mọi threads có thể chia sẻ cùng cờ. Request A chạy checkout bật true, request B gọi reserve độc lập cũng có thể bị hiểu là trong checkout. `volatile` chỉ giúp visibility, không biến cờ global thành trạng thái theo chuỗi lời gọi riêng.

### 9.2. Có nên dùng `InheritableThreadLocal`?

Không coi đó là giải pháp mặc định. `InheritableThreadLocal` có thể sao chép giá trị khi thread con được **tạo**, nhưng trong thread pools các threads được tạo từ trước và tái sử dụng, nên đó **không phải context propagation đáng tin** cho logical task boundaries. Nó còn có thể mang context quá lâu hoặc ngoài phạm vi dự kiến.

## 10. Đường điều khiển động khác đường liên hệ nghiệp vụ

Một luồng gọi có thể bao nhiều bước:

~~~text
checkout()
  validation()
    loadUser()
  reserve()
    persist()
  notify()
~~~

Một root `checkout()` có thể bao tất cả chúng, kể cả code thư viện nếu pointcut Q chọn và engine có thể instrument. Tuy nhiên, **cùng nằm dưới root checkout không có nghĩa tất cả thao tác thuộc cùng transaction**.

- Control-flow scope là **quan hệ lời gọi**.
- Transaction scope là **quan hệ commit/rollback của tài nguyên**.
- Trace scope là **quan hệ quan sát của logical operations**.
- Security scope là **quan hệ quyền đáng tin cậy**.
- Async operation scope có thể tồn tại sau khi method root return.

Một flow pointcut không tự tạo database transaction, không bảo đảm identity được xác minh và không ngăn một caller khác bypass code bảo mật.

Nếu yêu cầu kiểm quyền tuyệt đối, nên đặt enforcement ở boundary đáng tin cậy, không phụ thuộc duy nhất vào việc một method có `checkout` trên stack trong mọi đường gọi.

## 11. Recursion, nested roots và per-flow state

### 11.1. Recursion cùng root selector

~~~text
process(level=3)   <- P root #1
  process(level=2) <- P root #2, dưới #1
    process(1)     <- P root #3, dưới cả #1 và #2
~~~

Nếu dùng `cflow(P)`, cả ba method executions có thể match. Với `cflowbelow(P)`, root #1 không ở dưới chính mình, nhưng root #2 và #3 nằm dưới những roots ngoài.

Một counter `depth` cho biết số root occurrences đang active, nhưng không chỉ ra **root nào** nếu cần phân biệt actor/order/request context. Với logic per-flow, dùng stack hoặc context frames có định danh riêng.

### 11.2. Per-flow aspect instantiation khác per-invocation

Một engine có thể cho một aspect instance tồn tại cho **một root control flow**, dùng chung cho các join points con, và cleanup khi root kết thúc. Đây không đồng nghĩa tạo instance mới ở **mọi** `reserve` invocation.

Ví dụ một trace context có `traceId` tạo ở `checkout` và được `reserve`, `persist` dùng chung. Nếu `checkout` lồng nhau, phải định nghĩa inner dùng trace của outer hay tạo span/context con.

Không tự giả định mọi AOP engine cung cấp loại scope này. Có thể mô phỏng bằng explicit context object, nhưng cần ownership và propagation thật.

### 11.3. Root có thể xuất hiện trong advice

Nếu một advice quanh Q gọi một method cũng match P, flow mới có thể mở **bên trong code advice**. Nếu một advice quanh P tự gọi P và không có guard, recursion có thể xảy ra.

Cần test những trường hợp:
- advice tạo logging/metrics call lại đi vào pointcut;
- nested root được mở trong exceptional path;
- root được mở rồi target return sớm;
- root mở nhưng `proceed` không được gọi (short-circuit);
- outer root còn active sau khi inner root kết thúc.

## 12. Ngoại lệ và các đường rút khỏi flow

Một root P có thể kết thúc bằng:

- Return bình thường.
- Throw exception.
- Advice quanh root catch exception và return fallback.
- Advice short-circuit trước khi gọi target.
- Target/inner advice ném lỗi trong cleanup.

**Nguyên tắc:** flow scope phải kết thúc theo **lifecycle của root mà engine thực sự định nghĩa**, không chỉ theo kết quả thành công. Với implementation tự viết, dùng `try/finally` và restore/remove context.

Mẫu Java khái niệm:

~~~java
Context previous = current.get();
current.set(next);
try {
    return proceed();
} finally {
    if (previous == null) current.remove();
    else current.set(previous);
}
~~~

Đây là pseudocode không độc lập; `Context`, `current`, `next` và `proceed` phải được cung cấp. Nó minh họa **restore previous context** khi rời nested scope, không chỉ gán null một cách thô.

### 12.1. Lỗi do advice trước root

Nếu advice định nghĩa root scope trước `proceed` nhưng phần khởi tạo context ném exception, phải biết liệu scope đã được cài vào ThreadLocal hay chưa và cần cleanup gì. Đừng làm `push` rồi gọi logic không tin cậy **trước khi vào vùng `try/finally`**.

### 12.2. Cleanup cũng có thể lỗi

Nếu `close()` của resource trong flow ném lỗi, nó có thể che exception từ target. Cleanup tốt cần phân biệt lỗi chính và lỗi thứ cấp, sử dụng hợp đồng phù hợp (`try-with-resources` có hỗ trợ suppressed exception trong những trường hợp Java định nghĩa).

### 12.3. Flow nào còn active khi callback after chạy?

Nếu advice `around(P)` vẫn đang ở trong `try` trước khi pop, các hoạt động trong `afterReturning` hoặc `finally` của nó có thể **còn nằm trong flow P** tùy cách tổ chức. Nếu gọi Q từ chính cleanup logic, Q cũng có thể thỏa dynamic condition.

Muốn loại bỏ advice-internal logging khỏi Q, nên thiết kế pointcut loại trừ vùng instrumentation hoặc chuyển công việc ra sau khi đã restore context, tùy mục tiêu. Đừng giả định root kết thúc đúng lúc method target vừa return nếu outer advice vẫn giữ scope.

## 13. Thread hop, async và distributed call: ranh giới khó nhất

Call stack đồng bộ truyền thống:

~~~text
Thread A:
  checkout()
    reserve()
      persist()
  return
~~~

Nếu có async handoff:

~~~text
Thread A: checkout()
            submit(task) --------+
          return                |
                                v
Thread B:                   reserve()
                               persist()
~~~

Tại lúc Thread B chạy `reserve`, stack của Thread B **không chứa khung `checkout()` của Thread A**. Thậm chí `checkout` có thể đã return. Với định nghĩa cflow theo call stack vật lý, `reserve` không thuộc flow đang hoạt động của P trên Thread B.

### 13.1. Muốn flow qua async thì phải định nghĩa lại scope

Có thể dùng **logical operation context** để truyền `operationId`, security principal, trace IDs, deadline... tới task B. Nhưng đây là **một cơ chế propagation bổ sung**, không mặc nhiên cùng ngữ nghĩa với `cflow(P)`.

Cần trả lời:

1. Context được capture trước khi `submit` ở đâu?
2. Task nhận context bằng tham số, wrapper, scheduler API hay abstraction nào?
3. Nếu task chạy sau root method return, context còn hợp lệ bao lâu?
4. Có thể dùng context đó để **mở một root logic mới** hay chỉ dùng làm dữ liệu tracing?
5. Ai restore/remove context trong worker thread sau task?
6. Khi cancellation/retry xảy ra, context nào kết thúc, resource nào được đóng?
7. Context có chứa secrets hoặc thông tin cá nhân cần hạn chế propagation không?

### 13.2. Async method return không bằng operation completion

Một method trả `CompletableFuture<T>` có thể kết thúc **ngay sau khi lập lịch tác vụ**. Around advice bao method có thể pop control-flow scope ở method return, trong khi công việc thực vẫn đang pending. Nếu audit cần theo dõi toàn operation, phải chọn một lifecycle khác, gắn vào Future completion/cancellation.

Không tự `join()` trong advice để kéo dài stack scope nếu điều đó làm biến API async thành blocking và có nguy cơ deadlock.

### 13.3. Distributed tracing là mối liên hệ, không phải stack chung

Service A gọi Service B qua HTTP. B không có Java call stack của A. Một trace context có thể được gửi qua request headers và liên kết spans, nhưng điều đó không khiến một JVM-local `cflow(checkout)` pointcut ở B tự động true. Phải có policy rõ ở B dựa trên context được xác thực/cho phép.

## 14. Call join point và execution join point làm thay đổi ranh giới flow

Trong một số mô hình AOP:

- **Call join point** nằm tại **vị trí caller thực hiện lời gọi**.
- **Execution join point** nằm tại **thân thực thi của callee**.

Với `P=call(checkout(..))` và `P=execution(checkout(..))`, flow root có thể bắt đầu ở các điểm logic hơi khác nhau. Tương tự, `Q=call(reserve(..))` khác `Q=execution(reserve(..))`.

Các hệ quả:

- Nếu chỉ instrument **caller call sites**, những cuộc gọi không qua caller đã được dệt có thể không được chọn.
- Nếu instrument **callee execution**, mọi lần thực sự vào callee đã dệt có thể được chọn, kể cả direct calls.
- Với **proxy**, JDK `InvocationHandler` chỉ quan sát lời gọi qua proxy. Nó không tự tương đương mọi call/execution join point trong ngôn ngữ AOP.
- Nếu `checkout()` gọi `this.checkout()`, proxy ngoài có thể bị bypass ở lần gọi nội bộ; một execution weaving có thể vẫn thấy nó nếu class đã dệt.

Do đó khi chọn P/Q cần xác định **join point kind**, không chỉ tên method.

## 15. Độ phủ của weaver/proxy là điều kiện trước khi nói đến flow

Dù flow concept đúng, nếu join point không được instrument thì advice không chạy:

| Kịch bản | Câu hỏi cần kiểm |
| --- | --- |
| JDK interface proxy | Caller có thật sự giữ proxy của P và Q không? |
| Subclass proxy | Override/dispatch của method có hợp lệ? |
| Compile-time weaving | Artifact cuối đã chứa các join points cần quan sát? |
| Binary/post-compile weaving | Raw/woven output có bị trộn? |
| Load-time weaving | Transformer được cài trước lúc class cần xử lý được định nghĩa? |
| Classloader riêng | P/Q runtime classes có thuộc loader được chọn? |
| Method `final`, `private`, `static` | Engine hỗ trợ những điểm đó hay chỉ method qua proxy? |
| Constructor/field | Pointcut model có định nghĩa loại join point ấy? |
| Native/JDK internals | Có được instrument hợp lệ trong runtime hiện tại? |

Một proxy wrapper có thể can thiệp lời gọi `checkout` nhưng **không nhìn thấy `reserve` nếu reserve được gọi qua raw target**. Vì vậy test “`checkout` mở flow đúng” chưa chứng minh `Q AND cflow(P)` có độ phủ đúng.

## 16. Tối ưu hiệu năng cho dynamic control-flow pointcut

Một pointcut thuần tĩnh có thể được engine tối ưu ở compile/load-time. Điều kiện dynamic flow có thể yêu cầu **kiểm runtime** hoặc duy trì context/counter.

Chi phí có thể đến từ:

- Nhiều Q join points được instrument và phải kiểm active flag/depth.
- Root enter/exit phải push/pop context.
- `ThreadLocal` lookup, allocations hoặc context object creation.
- Stack inspection trong những implementation dùng kỹ thuật kiểm call stack.
- Advice chạy nhiều lần ở nested flows.
- Async context capture/restore.
- Logging/metrics/I/O bên trong advice, đôi khi đắt hơn phần matching.

Không nên tuyên bố `cflow` luôn tốn một độ phức tạp cố định cho mọi công cụ. Một engine có thể tối ưu bằng counter/marker; engine khác dùng chiến lược khác, cùng một expression có overhead khác nhau.

### 16.1. Thu hẹp `Q` trước

Thay vì match mọi method rồi hỏi “có trong checkout không?”, có thể chọn `Q` hẹp như những operations thật cần audit. Điều này giảm số join points có khả năng thực thi điều kiện dynamic.

### 16.2. Giữ context nhẹ

Một flow scope chỉ cần identifier, depth và vài thông tin immutable có thể rẻ hơn một object đầy tài nguyên. Tránh tạo HTTP clients/loggers mỗi Q invocation.

### 16.3. Tránh ghi log vô hạn do self-interception

Nếu advice gọi logger mà logger method cũng thuộc Q, có thể xảy ra recursion. Phân biệt advice implementation với domain join points, và test negative coverage.

### 16.4. Đo chi phí trên workload thật

Đo `Q` hit frequency, flow active ratio, allocation rate, p95/p99 latency và throughput. So với baseline không instrument hoặc chỉ dùng static pointcut. Không dùng một microbenchmark đơn luồng rồi kết luận hiệu năng production dưới concurrency.

## 17. Khi nào nên dùng dynamic flow và khi nào nên truyền context tường minh?

| Bài toán | Hướng có thể phù hợp |
| --- | --- |
| Thêm tracing/logging cho các helper calls **đồng bộ** bên dưới một root | Dynamic control-flow pointcut nếu engine có |
| Chọn Q khi method thuộc một workflow đồng bộ nhất định | `Q AND cflow(P)` hoặc tương đương |
| Logic bắt buộc đúng qua async/thread/distributed boundaries | Explicit/context propagation với ownership rõ |
| Authorization bắt buộc đối với mọi caller | Enforce tại trust boundary, không dựa duy nhất vào stack root |
| Audit theo business commit | Gắn event vào commit/outbox boundary thay vì chỉ method flow |
| Per-request timing | Per-invocation local state hoặc context propagation |
| Theo dõi nested/recursive operations | Stack frames hoặc scoped context hỗ trợ nesting |
| Mọi method trong một package cần same behavior | Static structural pointcut có thể đơn giản hơn |
| Control flow quá rộng và hot path nhiều | Cân nhắc thu hẹp Q hoặc thiết kế lại |

**Không phải tính năng càng động càng tốt.** Nếu ý định là “mọi method của một type”, một pointcut static dễ hiểu và thường ít runtime work hơn. Flow condition chỉ có giá trị khi **ngữ cảnh runtime mới phân biệt đúng nhu cầu**.

## 18. Kiểm thử: chứng minh cả positive và negative coverage

Bảng test tối thiểu cho `P=checkout` và `Q=reserve/step`:

| Ca | Flow P active? | Kỳ vọng với Q |
| --- | --- | --- |
| `reserve` độc lập | Không | Không kích hoạt advice theo `cflow(P)` |
| `checkout → reserve` | Có | Kích hoạt |
| `checkout → helper → reserve` | Có | Kích hoạt dù không gọi trực tiếp |
| `checkout` return rồi `reserve` | Không | Không kích hoạt |
| Nested `checkout(inner)` | Có outer P ancestor | Inner root có thể được `cflowbelow(P)` chọn |
| Recursion nhiều cấp | Có nhiều P frames | Scope/depth đúng, không leak |
| Target throw | Có trước lúc thoát | Cleanup; lần gọi sau phải không còn flow |
| Advice around root catch/recover | Tùy lifecycle root | Scope kết thúc đúng nơi |
| `checkout` qua raw target bypass proxy | Không mở scope proxy | Test phát hiện thiếu coverage |
| `reserve` qua raw target bypass Q proxy | Không thấy Q proxy | Không giả vờ Q advice đã chạy |
| Child thread dùng ThreadLocal thường | Không tự có context | Không kích hoạt flow theo mô phỏng |
| Explicit propagation được cấu hình | Tùy hợp đồng | Test capture/restore, timeout và cancellation |
| Có hai requests đồng thời | Scope riêng mỗi thread/task | Không lẫn flow của request khác |
| Một root call chạy `proceed` hai lần | Có thể 2 downstream flows | Đếm Q invocations rõ ràng |
| Q có overload khác | Tùy signature pointcut | Không match nhầm |

### 18.1. Assertion nên có những gì?

- **Outcome của caller:** result/exception gốc được bảo toàn nếu advice chỉ quan sát.
- **Root depth/context:** thay đổi đúng khi P enter và exit.
- **Advice event count:** Q trong flow chạy đúng số lần.
- **Target execution count:** không dùng advice count thay business count nếu retry/cache.
- **Negative coverage:** Q ngoài flow không ghi event flow-specific.
- **Exception cleanup:** sau lỗi, ThreadLocal/stack sạch.
- **Concurrency:** hai flows khác nhau không dùng nhầm root ID.
- **Async propagation:** không suy từ logical relation rằng thread stack đã có P.

### 18.2. Tại sao chỉ test một Q call trong checkout chưa đủ?

Nó không chứng minh:
- `reserve` độc lập sẽ không có advice.
- Exception không làm scope bị giữ mãi.
- Nested roots hoạt động đúng.
- Một callback thread khác có/không có context theo thiết kế.
- Code AOP thật được lắp qua đúng proxy hoặc woven artifact.

Tính đúng của flow-based AOP nằm ở **ranh giới**; cần test những lúc vào, ra và xuyên ranh giới.

## 19. Những lỗi thường gặp

1. **“Cùng method thì advice phải luôn chạy giống nhau.”** Không với dynamic flow; context caller có thể khác.
2. **“Static call graph đủ chứng minh P active.”** Không; dynamic stack chỉ chứa calls đang diễn ra.
3. **“`cflow(P)` chỉ chọn các method con.”** Thường còn bao gồm root P.
4. **“`cflowbelow(P)` chỉ là `cflow(P) && !P`.”** Sai ở nested/recursive P.
5. **“Có P trong lịch sử request thì flow còn active mãi.”** Không; root kết thúc thì scope phải được đóng.
6. **“Một `boolean active` đủ cho mọi nested roots.”** Sai nếu inner exit tắt outer flow.
7. **“Một `static boolean` theo dõi đúng flow nhiều threads.”** Sai; context global lẫn requests.
8. **“ThreadLocal tự đi theo mọi Future và executor.”** Không.
9. **“Thread con luôn kế thừa đúng logical control-flow scope.”** Không; propagation cần hợp đồng cụ thể.
10. **“Một cflow pointcut cũng là transaction.”** Không có atomic commit/rollback chỉ từ quan hệ stack.
11. **“Pointcut khớp Q thì proxy nào cũng thấy self-invocation.”** Không đối với nhiều wrappers.
12. **“Compile-time weaving không có điều kiện runtime.”** Một số điều kiện flow vẫn được đánh giá lúc chạy.
13. **“Một root proxy mở flow thì mọi Q đều instrument.”** Q còn có coverage riêng.
14. **“`cflowbelow` luôn loại mọi P occurrence.”** Không khi P lồng dưới P khác.
15. **“Flow cleanup chỉ cần ở normal return.”** Sai; exceptional exit cũng phải pop/restore.
16. **“Để ThreadLocal nguyên trong worker pool không sao.”** Dễ rò memory và context giữa requests.
17. **“Các control-flow selectors có cùng cú pháp ở mọi engine.”** Không; capability/semantics khác nhau.
18. **“Chỉ cần root method name, không cần call/execution kind.”** Không; kind ảnh hưởng coverage.
19. **“Q càng rộng càng an toàn.”** Q quá rộng có thể instrument advice/logging chính nó.
20. **“cflow luôn nhanh như static matching.”** Không có bảo đảm; có runtime checks.
21. **“Đặt security hoàn toàn dựa trên checkout có mặt trong stack là đủ.”** Nguy hiểm khi có bypass/async và trust boundary khác.
22. **“Method trả Future đồng nghĩa toàn operation đã kết thúc.”** Không; task có thể tiếp tục.
23. **“ThreadMX/stack trace lúc bất kỳ đều luôn hiển thị context đúng.”** Instrumentation và async có thể thay ngữ cảnh.
24. **“Mọi nested root phải tạo một aspect instance.”** Tùy scope/lifecycle của engine.
25. **“Chỉ có direct child mới thuộc cflow.”** Không; cháu và các lời gọi sâu hơn cũng nằm dưới root nếu flow vẫn active.
26. **“Một advice return fallback vẫn tự giữ P active cho các cuộc gọi sau.”** Không nếu root đã rời scope.
27. **“Hễ Q ở cùng type với P là cflow(P).”** Không; quan hệ type không đủ chứng minh dynamic ancestry.
28. **“Một log `cflow=true` là bằng chứng mọi method đều woven.”** Không; phải test Q coverage từng nhóm.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** `reserve()` được gọi một lần từ `checkout()` và một lần độc lập. Điểm code `reserve` có thay đổi không?  
**Đáp án:** Không nhất thiết. Nhưng điều kiện dynamic control-flow có thể true ở lần trong checkout và false ở lần độc lập.

**Câu 2.** `cflow(P)` có bao root P không?  
**Đáp án:** Trong ngữ nghĩa thông dụng của mô hình này, có.

**Câu 3.** `cflowbelow(P)` có bao root P đầu tiên không?  
**Đáp án:** Không nếu nó không nằm dưới occurrence P nào khác.

**Câu 4.** Trong `checkout outer → checkout inner`, root inner có thể match `cflowbelow(P)` không?  
**Đáp án:** Có, vì root inner nằm **bên dưới root outer**, dù tự nó cũng thuộc P.

**Câu 5.** Tại sao `boolean active` gây lỗi với nested roots?  
**Đáp án:** Inner exit có thể đặt false khi outer vẫn active; cần counter/stack hoặc restore previous context.

**Câu 6.** Nếu checkout throw, điều kiện flow trên lời gọi kế tiếp phải là gì?  
**Đáp án:** False khi root đã thoát; scope phải cleanup trong `finally`.

**Câu 7.** Nếu một `reserve` chạy trong child thread được tạo từ checkout, ThreadLocal thường có tự thấy P không?  
**Đáp án:** Không; thread mới có context riêng nếu không có propagation được thiết kế.

**Câu 8.** Một distributed trace context sang service khác có làm `cflow(P)` ở remote tự true không?  
**Đáp án:** Không. Tracing context là dữ liệu truyền qua network, không phải call stack chung của hai JVM.

**Câu 9.** Vì sao Q cần được giới hạn riêng ngoài P?  
**Đáp án:** Q quyết định loại join point có thể nhận advice; Q quá rộng gây overhead, recursion và event noise.

**Câu 10.** Phân biệt dynamic flow condition với lexical location bằng câu ngắn.  
**Đáp án:** Lexical chọn dựa trên vị trí/cấu trúc mã; dynamic flow chọn dựa trên lời gọi **đang active** tại thời điểm thực thi.

**Câu 11.** Trong ví dụ `CallFlowScopeDemo`, vì sao `ROOT enter inner` có `below=true`?  
**Đáp án:** Vì `inner` được gọi qua proxy khi `outer` root vẫn active, nên root inner là hậu duệ của root outer.

**Câu 12.** Tại sao `POINT step new-thread` có `cflow=false`?  
**Đáp án:** Demo dùng ThreadLocal thông thường và không truyền stack sang thread mới.

**Câu 13.** Có thể dùng một `cflow` condition làm phương tiện duy nhất bảo vệ quyền không?  
**Đáp án:** Không nên khi tồn tại proxy bypass, async boundary hoặc đường gọi không qua root; quyền phải được enforce ở ranh giới đáng tin.

**Câu 14.** Một instrumented method Q được gọi sau checkout đã return. Nó có còn ở trong flow không?  
**Đáp án:** Không, trừ khi có một root P khác đang active trong ngữ cảnh đang xét.

## 21. Quy trình áp dụng

1. **Xác định P rõ ràng:** đâu là workflow root thực sự, call hay execution join point?
2. **Xác định Q rõ ràng:** loại methods/operations nào chỉ cần advice khi nằm trong P?
3. **Chọn inclusive/exclusive:** cần bao root hay chỉ các hậu duệ? Xem nested roots.
4. **Xác định cơ chế can thiệp:** proxy, code weaving hoặc instrumentation khác có đủ coverage không?
5. **Thiết kế context scope:** depth/stack/owner, khi nào push/pop, cách cleanup trên exception.
6. **Phân tích recursion/nesting:** inner root có cần context riêng hay dùng chung outer?
7. **Phân tích async/thread hop:** có cần explicit propagation hay chỉ hỗ trợ synchronous scope?
8. **Không dùng flow làm bằng chứng security/transaction nếu chưa xác minh** các ranh giới thật.
9. **Thu hẹp P và Q:** tránh match mọi thứ rồi lọc ở runtime.
10. **Kiểm thử positive và negative paths:** cùng Q trong/ngoài P; root return/throw; nested P; multithreading.
11. **Kiểm thử trên artifact/deployment cuối:** classloader, agent, proxy references và precedence.
12. **Đo overhead:** instrumented joinpoint count, Q frequency, memory/context cleanup và latency.
13. **Ghi tài liệu semantic:** flow lifetime theo stack hay logical task, ai propagate và ai dispose?
14. **Theo dõi drift:** khi gọi từ workflow mới hoặc khi chuyển sang async, cập nhật test scope.

## 22. Tổng kết

**Giới hạn hành vi theo chuỗi lời gọi thay vì vị trí mã đơn lẻ** cho phép diễn đạt một ý định AOP mang tính ngữ cảnh: **chọn join point Q khi nó xảy ra bên trong dynamic control flow của root P đang active**. Các điều kiện theo `cflow(P)` thường bao root và hậu duệ; `cflowbelow(P)` thường loại chính root occurrence nhưng vẫn có thể chọn một P lồng dưới P khác.

Điểm quyết định là **quan hệ thời gian và call stack**, không phải chỉ method signature hoặc sơ đồ call graph. Vì thế thiết kế phải xử lý đúng nested/recursive roots, exception cleanup, per-flow state, proxy/weaving coverage, thread/async boundaries và runtime overhead. Java `ThreadLocal` + stack có thể mô phỏng ý tưởng cho một luồng đồng bộ nhưng không tự trở thành pointcut engine hoặc context propagation xuyên hệ thống.

Hãy kết hợp **root selector P, target selector Q và dynamic condition có phạm vi rõ**, sau đó test cả trường hợp Q nằm trong P lẫn những trường hợp nó phải ở ngoài. Khi cùng một method được tái sử dụng ở nhiều workflow, cách nhìn theo flow giúp định nghĩa chính xác **khi nào** một advice thực sự có ý nghĩa, thay vì áp một chính sách quá rộng lên mọi lời gọi.
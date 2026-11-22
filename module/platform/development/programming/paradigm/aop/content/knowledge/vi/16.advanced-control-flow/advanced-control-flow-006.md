# Lời gọi đệ quy và ý nghĩa của độ sâu can thiệp trong AOP

## 1. Đệ quy tạo ra nhiều lần thực thi, nhưng có chắc tạo nhiều lần advice?

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, một **join point** là một vị trí/sự kiện mà mô hình AOP cho phép can thiệp; **pointcut** lựa chọn các join point, còn **advice** thực thi hành vi cắt ngang như tracing, logging, auditing, đo thời gian hoặc kiểm tra chính sách.

Đối với một phương thức đệ quy, **cùng một phương thức có thể được gọi nhiều lần trước khi lần gọi trước kết thúc**. Thí dụ:

```java
// Mã minh họa ý tưởng.
int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}
```

`factorial(4)` tạo chuỗi gọi `factorial(4) → factorial(3) → factorial(2) → factorial(1)` trước khi lần lượt return. Nhưng liệu advice cũng chạy bốn lần? **Không thể trả lời chỉ từ source của method.** Điều đó phụ thuộc:

1. **Loại join point** được chọn: *method call*, *method execution* hay loại khác.
2. **Phạm vi can thiệp**: bytecode caller/callee có được dệt không, hay chỉ lời gọi qua proxy mới được intercept?
3. **Đường gọi đệ quy**: lời gọi quay qua boundary được intercept hay gọi nội bộ trực tiếp qua `this`?
4. **Điều kiện pointcut**: có chọn tất cả lần gọi, chỉ lần ngoài cùng, chỉ mức sâu nào đó, hay theo ngữ cảnh luồng điều khiển?
5. **Hành vi advice**: around advice có gọi `proceed` không, một lần hay nhiều lần, có tự sinh thêm lời gọi không?
6. **Ngữ nghĩa độ sâu**: đang đếm call stack nghiệp vụ, số advice activation, độ sâu control flow, hay số lần thử lại?

**Mệnh đề nền tảng:** *Một call site trong bytecode có thể tạo nhiều sự kiện runtime. Ngược lại, nhiều lần gọi nghiệp vụ không nhất thiết đều đi qua cùng một interception boundary.* Khi nghiên cứu AOP với đệ quy, phải phân biệt **độ sâu thực thi của chương trình** với **độ sâu can thiệp thực tế của advice**.

> Bài này trình bày AOP cơ bản và nâng cao nói chung, không dựa vào một công cụ riêng. Những cách diễn đạt như `cflow`, `cflowbelow`, around/proceed hoặc call/execution là khái niệm/mô hình thường gặp; **cú pháp chính xác và loại join point được hỗ trợ tùy engine**. Ví dụ Java 17+ sử dụng Java Dynamic Proxy để chứng minh những khác biệt quan sát được, không khẳng định proxy là hình thức AOP duy nhất.

## 2. Ba loại độ sâu cần tách biệt

**Độ sâu đệ quy nghiệp vụ (business recursion depth)** phản ánh số tầng gọi lồng nhau của thuật toán. **Độ sâu advice (advice activation depth)** đếm những lần một advice/interceptor cụ thể đang hoạt động trên một đường thực thi. **Độ sâu control-flow (dynamic control-flow depth)** diễn tả mức lồng nhau của các flow được xác định bởi pointcut gốc hoặc phạm vi động.

```text
Call stack logic:              Các advice activation (giả sử có interception):
factorial(4)                   advice[factorial(4)]  depth=0
  factorial(3)                   advice[factorial(3)] depth=1
    factorial(2)                   advice[factorial(2)] depth=2
      factorial(1)                   advice[factorial(1)] depth=3
```

Sơ đồ bên phải chỉ đúng nếu **mọi bước đệ quy đều được advice quan sát**. Nếu proxy chỉ thấy lời gọi ngoài cùng, cột advice chỉ có một entry với depth 0, dù call stack nghiệp vụ có bốn tầng.

| Khái niệm | Đối tượng đếm | Có luôn bằng số lần đệ quy? |
| --- | --- | --- |
| Recursion depth | Mức lồng nhau của lời gọi bài toán | Chính là độ sâu theo quy ước nghiệp vụ đã chọn |
| Advice activation depth | Số lời gọi advice đang chưa kết thúc | **Không**; tùy pointcut, interception và ordering |
| `cflow`/flow nesting | Số tầng của dynamic flow được định nghĩa | **Không**; tùy join point mở flow và semantics engine |
| Thread stack depth | Số frame thực thi trên thread | **Không**; còn runtime/internal frames/JIT |
| Retry attempt count | Số lần around gọi `proceed` | **Không**; retry không đồng nghĩa recursion |
| Distributed trace depth | Quan hệ span cha–con theo carrier | **Không**; có thể trải qua nhiều thread/process |

Đừng dùng một field tên `depth` mà không định nghĩa nó đo **độ sâu của cái gì** và lấy mốc 0 hay 1 ở đâu.

## 3. Lời gọi đệ quy trực tiếp và gián tiếp

### 3.1. Đệ quy trực tiếp

```java
// Ví dụ minh họa trong class nghiệp vụ.
int gcd(int a, int b) {
    return b == 0 ? a : gcd(b, a % b);
}
```

Một method gọi chính nó. Nếu execution join point của `gcd` được weave đầy đủ, mỗi lượt thực thi `gcd` có thể sinh một advice activation riêng. Nhưng nếu caller chỉ đi qua proxy ở lần đầu và lời gọi nội bộ bypass, advice của wrapper có thể chỉ chạy một lần.

### 3.2. Đệ quy tương hỗ (mutual recursion)

```java
// Đoạn minh họa, không phải tệp hoàn chỉnh.
boolean even(int n) {
    return n == 0 || odd(n - 1);
}
boolean odd(int n) {
    return n != 0 && even(n - 1);
}
```

Ở đây flow `even → odd → even → ...`. Pointcut chỉ chọn `even` sẽ thấy **ít activation hơn** tổng số method executions thuộc chuỗi. Một pointcut chọn cả hai có thể thấy tất cả, nếu các join point đều được intercept.

**Recursion không bắt buộc method gọi chính tên của nó.** Điều quan trọng là có đường đi trong call graph quay lại một node đang nằm trên dynamic call stack.

### 3.3. Recursion qua nhiều object/module

```text
OrderService.process()
  -> BillingService.charge()
      -> RetryCoordinator.dispatch()
          -> OrderService.process()
```

Một vòng gọi có thể đi qua nhiều target, class loader hoặc module. Trong AOP:

- Advice chọn execution của `OrderService.process` có thể kích hoạt lại khi flow quay về method ấy.
- Advice chọn call site ở `BillingService` không nhất thiết thấy call site từ `RetryCoordinator`.
- Proxy có thể được dùng ở một cạnh của call graph nhưng bỏ qua ở cạnh khác.
- Một context theo thread hoặc per-target không tự đại diện chính xác mọi vòng lặp trong call graph.

Khi phân tích độ sâu, cần vẽ **đường gọi thực** thay vì chỉ đếm số câu lệnh gọi hàm trong source.

## 4. Join point được dệt ở đâu quyết định độ sâu quan sát

Hai loại join point quan trọng:

- **Method call join point:** vị trí phát lời gọi, thường nằm trong bytecode **caller**.
- **Method execution join point:** thời điểm chạy phần thân phương thức, thường liên quan bytecode **callee**.

```text
callerMethod()
    |
    | [call join point ở caller]
    v
targetMethod()
    |
    | [execution join point ở callee]
    v
target body
```

Một source call site đệ quy như `factorial(n - 1)` có thể được **thực thi nhiều lần**. Nếu công cụ dệt call site ấy, mỗi lần đi qua instruction có thể tương ứng một call join point occurrence. Nếu chọn method execution và method body được weave, mỗi lần bắt đầu execution của method ấy có thể kích hoạt advice.

### Lần gọi gốc và lần gọi đệ quy không cùng call site

Giả sử:

```java
int value = service.factorial(4); // Call site của caller ngoài.
```

Trong `factorial` lại có instruction gọi `factorial(n-1)`. Nếu pointcut chỉ chọn **call site từ caller ngoài**, nó không tự chọn **call site bên trong factorial**. Ngược lại, execution pointcut cho `factorial` (nếu đã weave đúng method) có thể thấy mọi execution không phân biệt nguồn caller.

Đừng suy ra “đã chọn method name” nghĩa là engine tự chọn cả call và execution. **Loại join point và scope class weaving phải tường minh**.

### Cùng một join point tĩnh, nhiều occurrence động

Một call instruction nằm trong class file chỉ xuất hiện **một vị trí bytecode**, nhưng loop/recursion có thể chạy nó nhiều lần. AOP thường xử lý **những lần xuất hiện ở runtime**, không phải chỉ đếm số vị trí trong source/bytecode.

## 5. AOP qua proxy: self-invocation có thể làm advice depth thấp hơn recursion depth

Với một wrapper proxy đặt trước target:

```text
caller -> proxy.factorial(4)
           |
           -> target.factorial(4)
                -> this.factorial(3)
                     -> this.factorial(2)
                          -> this.factorial(1)
```

Chỉ lời gọi **đầu tiên** đi qua proxy. Những lời gọi `this.factorial(...)` nội bộ trên raw target **không quay ra wrapper proxy**, vì vậy handler không nhận thêm activation.

**Không nên kết luận thuật toán không đệ quy chỉ vì handler log một lần.** Độ sâu advice phụ thuộc đường interception.

### Đi qua proxy ở mỗi bước

Nếu target giữ một reference `self` trỏ tới proxy và gọi:

```java
// Mã minh họa, không phải chương trình độc lập.
return n * self.factorial(n - 1);
```

thì mỗi bước có thể quay vào proxy:

```text
proxy.factorial(4) -> advice depth 0
  target.factorial(4)
    proxy.factorial(3) -> advice depth 1
      target.factorial(3)
        proxy.factorial(2) -> advice depth 2
          ...
```

Đây là một **cách thử nghiệm có chủ đích**, không phải lời khuyên chung nên bắt mọi target giữ self-proxy. Thiết kế self-reference có thể tạo coupling, vòng dependency, khó test và lộ raw/proxy identity. Một phương án thiết kế khác là tách operation thành một component mà những lời gọi thật sự cần interception đi qua một contract công khai.

### Các loại proxy không hoàn toàn giống nhau

Một subclass proxy có cơ chế override/dispatch khác wrapper proxy. Với một số cách triển khai, `this.method()` có thể dispatch qua override bị intercept; với cách khác, không. Final/private/static methods lại có giới hạn riêng. Vì vậy kết luận **“self-invocation luôn bypass mọi proxy” là quá rộng**. Ví dụ trong bài sử dụng chính xác **Java Dynamic Proxy bao quanh target**.

## 6. Ví dụ Java 17+ hoàn chỉnh: một thuật toán, ba độ sâu

Chúng ta sẽ triển khai:

1. Đệ quy qua `this`: target thực thi ba tầng nhưng advice chỉ kích hoạt một lần.
2. Đệ quy qua `self` đang trỏ tới proxy: advice kích hoạt ba tầng với độ sâu **0, 1, 2**.
3. Ném ngoại lệ: advice in dòng throw, khôi phục bộ đếm trong `finally`.
4. Lời gọi tiếp theo: depth trở về **0**, chứng minh state không rò sang invocation mới.

Proxy handler giữ **ThreadLocal<Integer>` để minh họa việc theo dõi *advice activation depth*** trên cùng thread. Mã có `remove` ở tầng ngoài cùng và `set(d)` để khôi phục depth của tầng ngoài khi inner kết thúc.

**Chú ý:** ThreadLocal ở đây đo **advice nesting synchronous** trong một demo Java SE, không đại diện tự động cho request scope, distributed trace hay mọi mô hình AOP. Một around advice chỉ cần biết depth của chính call có thể dùng local variable; ThreadLocal được chọn để **liên kết các activation lồng nhau**.

### 6.1. Tệp `RecursionAspectDepthDemo.java`

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class RecursionAspectDepthDemo {
    interface MathTask {
        int factorial(int n);
    }

    static final class Factorial implements MathTask {
        private final boolean throughProxy;
        private MathTask self;

        Factorial(boolean throughProxy) {
            this.throughProxy = throughProxy;
        }

        void bind(MathTask proxy) {
            self = proxy;
        }

        @Override
        public int factorial(int n) {
            System.out.println("target n=" + n);
            if (n < 0) {
                throw new IllegalArgumentException("negative");
            }
            if (n <= 1) {
                return 1;
            }
            return n * (throughProxy
                    ? self.factorial(n - 1)
                    : this.factorial(n - 1));
        }
    }

    static final class TracingHandler
            implements java.lang.reflect.InvocationHandler {
        private final MathTask target;
        private final ThreadLocal<Integer> depth =
                ThreadLocal.withInitial(() -> 0);

        TracingHandler(MathTask target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            int d = depth.get();
            depth.set(d + 1);
            System.out.println(
                    "advice.enter depth=" + d + " n=" + args[0]);

            try {
                Object value;
                try {
                    value = method.invoke(target, args);
                } catch (InvocationTargetException wrapped) {
                    throw wrapped.getCause();
                }

                System.out.println(
                        "advice.exit depth=" + d + " value=" + value);
                return value;
            } catch (Throwable error) {
                System.out.println(
                        "advice.throw depth=" + d + " "
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                if (d == 0) {
                    depth.remove();
                } else {
                    depth.set(d);
                }
                System.out.println("advice.cleanup depth=" + d);
            }
        }
    }

    static MathTask wrap(Factorial target) {
        MathTask proxy = (MathTask) Proxy.newProxyInstance(
                MathTask.class.getClassLoader(),
                new Class<?>[]{MathTask.class},
                new TracingHandler(target));
        target.bind(proxy);
        return proxy;
    }

    public static void main(String[] args) {
        System.out.println("== direct self call ==");
        MathTask direct = wrap(new Factorial(false));
        System.out.println(
                "caller result=" + direct.factorial(3));

        System.out.println("== recursive call through proxy ==");
        MathTask reenter = wrap(new Factorial(true));
        System.out.println(
                "caller result=" + reenter.factorial(3));

        System.out.println("== exceptional unwind ==");
        try {
            reenter.factorial(-1);
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "caller caught=" + error.getMessage());
        }
        System.out.println(
                "caller result=" + reenter.factorial(2));
    }
}
```

### 6.2. Lệnh biên dịch và chạy

Đặt đúng tên file `RecursionAspectDepthDemo.java`, dùng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 RecursionAspectDepthDemo.java
java RecursionAspectDepthDemo
```

**Standard output chính xác đã kiểm bằng cách biên dịch/chạy với JDK:**

```text
== direct self call ==
advice.enter depth=0 n=3
target n=3
target n=2
target n=1
advice.exit depth=0 value=6
advice.cleanup depth=0
caller result=6
== recursive call through proxy ==
advice.enter depth=0 n=3
target n=3
advice.enter depth=1 n=2
target n=2
advice.enter depth=2 n=1
target n=1
advice.exit depth=2 value=1
advice.cleanup depth=2
advice.exit depth=1 value=2
advice.cleanup depth=1
advice.exit depth=0 value=6
advice.cleanup depth=0
caller result=6
== exceptional unwind ==
advice.enter depth=0 n=-1
target n=-1
advice.throw depth=0 IllegalArgumentException
advice.cleanup depth=0
caller caught=negative
advice.enter depth=0 n=2
target n=2
advice.enter depth=1 n=1
target n=1
advice.exit depth=1 value=1
advice.cleanup depth=1
advice.exit depth=0 value=2
advice.cleanup depth=0
caller result=2
```

### 6.3. Phân tích nhánh đệ quy trực tiếp qua `this`

Trong trường hợp `throughProxy=false`:

- Caller gọi `direct.factorial(3)` trên proxy, handler chạy ở depth **0**.
- Target thực hiện `factorial(3)`.
- Đường gọi `this.factorial(2)` và `this.factorial(1)` chạy trực tiếp trong target.
- Handler không nhận activation ở hai mức trong.
- Target trả `6`; handler in exit/cleanup depth 0.

Số **target executions = 3**, số **advice activations = 1**.

**Kết quả không chứng minh pointcut không hỗ trợ recursion**; nó chứng minh hai recursion calls đã bypass **wrapper proxy boundary**. Nếu method executions của target thực sự được bytecode-weave, coverage có thể khác.

### 6.4. Phân tích nhánh mỗi bước quay qua proxy

Với `throughProxy=true`:

- Outer handler lấy `d=0`, lưu `depth=1` trước khi proceed.
- Target tại `n=3` gọi `self.factorial(2)`, tức gọi **proxy**.
- Inner handler lấy `d=1`, lưu `depth=2`.
- Target tại `n=2` gọi `self.factorial(1)`, handler thứ ba lấy `d=2`.
- Tầng `n=1` trả `1`, advice ở depth 2 in exit/cleanup rồi restore `depth=2`.
- Tầng `n=2` tính `2*1=2`, advice depth 1 in exit/cleanup, restore `depth=1`.
- Tầng `n=3` tính `3*2=6`, advice depth 0 in exit/cleanup, `depth.remove()`.

Số **target executions = 3**, số **advice activations = 3**, advice depth theo quy ước **0, 1, 2**.

### 6.5. Tại sao thứ tự log “đi vào” và “đi ra” ngược nhau?

Đệ quy có dạng **nested LIFO**: đi vào outer → inner → innermost; khi trả về đi ra innermost → inner → outer.

```text
enter 0
  enter 1
    enter 2
    exit 2
  exit 1
exit 0
```

Nếu một after/finally advice ghi kết quả theo **thứ tự vào** thay vì **thứ tự unwind**, nó có thể đang dùng sai scope hoặc dữ liệu shared bị ghi đè. Tuy vậy, trong đa luồng/async không thể suy từ mọi log toàn cục một trật tự LIFO đơn nhất vì các luồng khác nhau có thể xen kẽ.

### 6.6. Khi ném lỗi, độ sâu phải được khôi phục

`reenter.factorial(-1)` ném `IllegalArgumentException`. Handler:

1. Ghi enter depth 0.
2. Reflection nhận lỗi target trong `InvocationTargetException`.
3. Handler mở wrapper, ném đúng cause gốc.
4. Nhánh catch ghi `advice.throw depth=0` và rethrow.
5. `finally` gọi `remove()` vì `d==0`.
6. Caller bắt ngoại lệ.
7. Lời gọi mới `factorial(2)` lại bắt đầu depth **0**, không phải **1**.

**Cleanup theo `finally` thiết yếu ngay cả khi target throw.** Nhưng resource exhaustion nghiêm trọng như `StackOverflowError` có thể làm việc cleanup/log không đáng tin cậy; không nên cố dựa vào advice để phục hồi mọi trường hợp cạn kiệt stack.

### 6.7. Ý nghĩa của depth được ghi

Biến `d` là **số advice activations đang bao ngoài** của handler cùng đối tượng `TracingHandler` trên thread hiện tại. Nó không phải:

- Số Java stack frames thực tế.
- Số lần method factorial từng được gọi trong lịch sử.
- Mức sâu toàn cục của mọi aspect hoặc mọi proxy.
- Request/trace depth xuyên thread.
- Một giá trị đảm bảo đúng cho native/async/distributed code.

**Nếu dùng một handler khác hoặc một ThreadLocal khác**, độ sâu quan sát của nó có thể khác dù chạy trong cùng call graph.

## 7. Control flow trong AOP: `cflow` và `cflowbelow`

Một số mô hình AOP cung cấp biểu thức chọn join point theo **luồng điều khiển động** (dynamic control flow).

Về ý tưởng:

- **`cflow(P)`:** chọn join point nằm **trong** dynamic control flow được khởi tạo khi một join point khớp `P` xuất hiện; thông thường bao gồm chính điểm gốc theo semantics của mô hình hỗ trợ.
- **`cflowbelow(P)`:** chọn join point **bên dưới** một điểm gốc khớp `P` trong dynamic control flow, không lấy **chính điểm gốc đó làm điểm được chọn vì flow của nó**.

Hai khái niệm này không giống việc lọc dựa vào **call stack text** hay số thread. Chúng yêu cầu engine quản lý/đánh giá ngữ cảnh động theo hợp đồng riêng.

### Một ví dụ khái niệm

```text
Root P: Checkout.run()          [điểm mở flow]
  |
  +-- Validate.check()          [bên dưới P]
  |
  +-- Billing.charge()          [bên dưới P]
       |
       +-- Retry.execute()      [bên dưới P]
```

Với một pointcut Q chọn execution của `Billing.charge`:

- `Q && cflow(P)` có thể chọn `Billing.charge` khi nằm trong flow `Checkout.run`.
- `Q && cflowbelow(P)` cũng có thể chọn `Billing.charge` nếu nó là điểm **phía dưới root P**.
- Chính `Checkout.run` không được chọn **bởi cflowbelow của lần P làm root**, theo định nghĩa “below”.

**Mốc root P được quyết định bởi một pointcut**, không phải mọi method trong chương trình mặc định đều mở flow AOP.

### Lưu ý khi chính P có recursion

```text
P(3)      [P đầu tiên, root]
  |
  +-- P(2)  [bên dưới P(3), đồng thời lại khớp P]
        |
        +-- P(1) [bên dưới P(2) và P(3)]
```

Đây là chi tiết nâng cao dễ nhầm:

- `P(3)` là điểm mở flow đầu tiên ở cấp ngoài.
- `P(2)` **không phải root P(3)**; nó nằm bên dưới flow của `P(3)`, nên **có thể khớp `cflowbelow(P)` nhờ một ancestor P**.
- `P(1)` tương tự.
- Nếu engine có semantics cflowbelow đặc thù, cần xác minh predicate tại các recursive occurrences theo contract của engine.

Không phát biểu đơn giản **“mọi join point khớp P đều không bao giờ khớp cflowbelow(P)”**. Một recursive occurrence P có thể nằm **bên dưới một occurrence P khác**. Cũng không kết luận `cflow(P)` tự đếm số tầng: predicate Boolean “có nằm trong flow” khác với integer “có bao nhiêu root P đang active”.

## 8. Chọn mức ngoài cùng và mức bên trong

Một nhu cầu phổ biến: **chỉ log một lần cho toàn bộ phép đệ quy**, thay vì log từng tầng. Có hai nhóm cách tiếp cận:

### 8.1. Dựa trên control flow (nếu engine hỗ trợ)

Với một pointcut P đủ chính xác cho method recursion, biểu thức kiểu:

```text
P AND NOT cflowbelow(P)
```

thường được dùng theo ý tưởng để chọn **occurrence P ở tầng ngoài cùng**, tức P không nằm bên dưới một occurrence P khác đang active trong cùng dynamic flow.

Ví dụ `factorial(4)` → `factorial(3)`:

- `factorial(4)` không có ancestor P, nên phù hợp.
- `factorial(3)` nằm dưới `factorial(4)`, bị loại.
- `factorial(2)` cũng bị loại.

**Điều kiện rất quan trọng:** engine phải hỗ trợ kiểu pointcut/control-flow đó, P phải match đúng những occurrence cần xét, và scope weaving phải bao phủ chúng. Nếu proxy chỉ thấy outer, kết quả “một advice” không chứng minh cflow filter đã hoạt động.

### 8.2. Dùng một guard đo advice depth

Trong interceptor custom, có thể:

```java
// Pseudocode: d là depth của advice activation hiện tại.
boolean outermost = (d == 0);
if (outermost) {
    emitStartEvent();
}
try {
    return proceed();
} finally {
    if (outermost) {
        emitEndEvent();
    }
}
```

Ở đây điều kiện dựa trên **độ sâu advice thực sự được gọi**, không nhất thiết trên toàn bộ recursion. Nếu inner recursion bypass interception, d vẫn là 0 ở mỗi lời gọi ngoài độc lập; không thể suy từ guard đó rằng toàn bộ business call graph đã được quan sát.

### Khi nào nên quan sát mọi tầng?

- Cần debug từng bước của thuật toán.
- Muốn đo duration riêng từng recursive activation.
- Cần đếm số node visited hoặc số tầng logic.
- Muốn kiểm chứng stop condition, input mỗi bước, exception propagation.
- Cần phân tích chi phí hoặc số lần chạm một dependency.

### Khi nào chỉ log tầng ngoài?

- Event audit đại diện **một thao tác business**.
- Một trace span cấp cao để hạn chế log volume.
- Muốn đo tổng elapsed time của cả phép đệ quy.
- Inner event đã có representation khác để tránh log trùng.

**“Chỉ tầng ngoài” là lựa chọn quan sát, không mặc nhiên là lựa chọn security enforcement đúng.** Một kiểm tra bắt buộc ở mỗi execution không nên bị guard depth tắt bừa.

## 9. Đếm chiều sâu: quy ước bắt đầu từ 0 hay 1?

Ví dụ demo:

```text
advice.enter depth=0  // không có advice activation cùng handler đang bao ngoài
advice.enter depth=1  // có một activation bao ngoài
advice.enter depth=2  // có hai activation bao ngoài
```

Đó là **zero-based nesting depth**. Nếu muốn “mức thứ mấy đang chạy”, có thể hiển thị `level = d + 1`.

Một số hệ thống định nghĩa depth là **số frame hiện đang active**, nghĩa là lúc vừa vào advice đầu tiên depth=1. Cả hai đều hợp lệ nếu được tài liệu hóa và kiểm tra.

### Tính depth trước hay sau khi tăng?

```java
int previous = depth.get();
depth.set(previous + 1);
try {
    log("depth=" + previous);
    return proceed();
} finally {
    restore(previous);
}
```

Ở đây `previous` là số activation đang bao ngoài. Nếu log `depth.get()` **sau tăng**, log sẽ hiển thị 1,2,3 thay cho 0,1,2. Không phải lỗi, nhưng **khác quy ước**.

Nếu nhiều advice cùng dùng một counter chung mà không xác định loại event nào làm tăng, depth có thể phản ánh **advice chain** thay vì **method recursion**.

## 10. Reentrancy của advice: đệ quy có thể xảy ra trong chính concern

Một aspect logging có thể gọi một helper để ghi audit; helper ấy lại khớp pointcut đang dùng. Khi advice chạy:

```text
advice.before()
   |
   +-- AuditWriter.write()
           |
           +-- matches pointcut -> advice.before()
                   |
                   +-- AuditWriter.write()
                           |
                           +-- ... recursion không mong muốn
```

Đó là **advice-induced recursion** hoặc reentrancy do concern tự kích hoạt mình, khác với recursion có chủ đích của thuật toán nghiệp vụ.

### Biểu hiện

- Stack tăng liên tục và có thể `StackOverflowError`.
- Event audit/log lặp lại quá nhiều.
- Latency tăng mạnh, CPU bị tiêu tốn.
- Advice không bao giờ tới `proceed`.
- Một exception từ helper làm chuỗi xử lý lỗi lại gọi helper lần nữa.

### Xử lý đúng: thu hẹp phạm vi can thiệp

Những hướng thiết kế:

1. **Loại trừ code runtime của aspect** khỏi pointcut nếu phù hợp.
2. Chọn **boundary nghiệp vụ thực sự**, thay vì match tất cả method bất kể package/type.
3. Tránh gọi lại chính API bị instrument từ trong logging sink, hoặc dùng một writer ở boundary không bị match.
4. Sử dụng **reentrancy guard có cleanup** nếu phải có.
5. Kiểm chứng exception path và nested calls để không vô tình khóa vĩnh viễn instrumentation.
6. Không tắt toàn bộ security/audit checks chỉ để giảm log nếu những kiểm tra đó là bắt buộc.

### Guard khác filter control flow

Một `ThreadLocal<Boolean> inAdvice` có thể tạm chặn **chính đoạn logic logging** khi reenter, nhưng **không tự phản ánh mọi business recursion**. Nếu guard làm around advice bỏ qua `proceed`, nó còn có thể khiến **target không chạy**. Một guard bảo vệ sink nên giới hạn đúng concern, vẫn giữ hành vi nghiệp vụ theo policy.

## 11. Giới hạn recursion: giới hạn nghiệp vụ khác giới hạn advice

Một thuật toán có thể có stop condition:

```java
if (n <= 1) return 1;
```

Stop condition này liên quan **business recursion**, không phải độ sâu advice. Một guard kiểu:

```java
if (adviceDepth > 100) throw new IllegalStateException("too deep");
```

chỉ có nghĩa phù hợp khi **adviceDepth phản ánh chính phạm vi cần giới hạn**. Nếu self-call bypass proxy, business depth có thể hàng nghìn trong khi adviceDepth vẫn bằng 0.

### An toàn hơn cho giới hạn nghiệp vụ

- Thiết kế thuật toán có base case/termination condition đúng.
- Đặt giới hạn theo **input và domain constraints**.
- Với dữ liệu không tin cậy, bảo vệ resource bằng budget/visited-state/explicit stack khi cần.
- Phân biệt recursion bất tận với một bài toán có depth lớn hợp lệ.
- Không trông cậy vào việc bắt `StackOverflowError` để quản lý depth bình thường.

Một aspect có thể hỗ trợ **đo và cảnh báo** độ sâu ở join point được quan sát; nó không thay cho chứng minh thuật toán luôn dừng hoặc giới hạn tài nguyên thực tế.

## 12. Around advice, `proceed` và độ sâu không phải lúc nào cũng 1:1

Một around advice có thể:

- Gọi `proceed` **một lần**: target/inner chain chạy một lần.
- **Không gọi**: skip target, trả fallback hoặc chặn theo policy.
- Gọi `proceed` **nhiều lần**: retry hoặc xử lý mô hình đặc biệt, nếu engine cho phép.
- Chuyển ngữ cảnh, bọc return hay thay Throwable theo contract.

Do đó:

```text
1 advice activation
   |
   +-- proceed attempt #1
   |
   +-- proceed attempt #2
   |
   +-- proceed attempt #3
```

Có thể có **một around advice activation** nhưng **ba lần target execution**. Nếu mỗi `proceed` chạm một join point khác lại được instrument, những advice ở bên trong có thể chạy nhiều lần, trong khi around ở ngoài vẫn chỉ có một activation.

**Đừng dùng retry count làm recursion depth**, cũng đừng suy số lần target chạy từ số lần logging quanh advice.

### Khi một around không `proceed`

Nếu advice ngoài quyết định chặn:

- Advice bên trong có thể không chạy.
- Method đệ quy có thể không được bắt đầu.
- Một “độ sâu” ghi trong logging bên ngoài không chứng minh tồn tại bất kỳ recursive target frame nào.
- Outcome cuối cùng được quy định bởi around advice, không phải body target.

### Advice ordering

```text
OuterAround
   -> InnerAround
        -> Target.recursive()
```

Nếu OuterAround và InnerAround cùng được áp dụng vào mỗi recursion execution, mỗi một mức nghiệp vụ có thể chứa **hai advice activations ở các layer khác nhau**. Counter đếm mọi interceptor entries có thể là 2× số recursion levels đang active, không bằng mức recursion.

Hãy xác định counter đếm **aspect nào** và **loại join point nào**.

## 13. Thời gian thực thi và đệ quy: inclusive vs exclusive

Một around advice có thể đo thời gian:

```java
// Pseudocode: proceed và metric recorder do công cụ/ứng dụng cung cấp.
long startedAt = System.nanoTime();
try {
    return proceed();
} finally {
    recordDuration(System.nanoTime() - startedAt);
}
```

Nếu advice chạy ở **mỗi recursive execution**, duration của outer **bao gồm** thời gian của inner. Đây là **inclusive time**.

```text
factorial(3)  [------------------ outer duration ------------------]
  factorial(2)    [---------- inner duration ------------]
    factorial(1)       [---- innermost ----]
```

Nếu **cộng tất cả inclusive durations**, tổng có thể lớn hơn elapsed time của cả phép gọi vì thời gian inner bị đếm lại ở outer.

### Exclusive time cần thiết kế riêng

**Exclusive time** là thời gian mà invocation hiện tại sử dụng, trừ thời gian ở những child operations được chọn để loại. Muốn tính đúng thường cần giữ **stack state của từng invocation**, lưu child elapsed và xử lý nested scopes:

```text
outerInclusive = outerEnd - outerStart
outerExclusive = outerInclusive - sum(selectedChildInclusive)
```

Công thức chỉ đúng khi những child durations **không chồng lấn theo cách gây đếm trùng**, semantics selected children phù hợp và đo trên cùng đồng hồ/thời gian. Với async/concurrent subtasks, phép trừ đơn giản có thể sai vì các khoảng thời gian chồng lấp.

### Dùng `System.nanoTime()` đúng mục đích

`System.nanoTime()` dành cho **elapsed duration**, không phải timestamp lịch hoặc distributed clock. Dữ liệu log có thể mang thêm wall-clock timestamp để đối chiếu, nhưng không trừ tùy tiện timestamps từ hai máy để suy elapsed time với độ chính xác cao.

## 14. Độ sâu, sampling và chi phí instrumentation

Đệ quy sâu có thể khiến advice kích hoạt rất nhiều lần:

```text
Recursion levels:      10,000
One advice per level:  10,000 advice activations
Three advices/level:   up to 30,000 advice activations
```

Đây là mô hình số đếm đơn giản, không phải cam kết mọi join point đều match. Chi phí có thể bao gồm:

- Pointcut dynamic predicate.
- Tạo context/argument bindings.
- ThreadLocal read/set/remove.
- Log formatting và output.
- Tạo trace span/metric event.
- Stack trace extraction nếu có.
- Resource/writer contention.
- GC từ allocation per-invocation.

Một event nhỏ có thể trở nên đắt khi nhân theo recursion depth.

### Chọn chính sách quan sát

**Ghi mỗi tầng** khi cần hiểu thuật toán cụ thể.

**Ghi root và failure** khi chỉ cần outcome của toàn thao tác.

**Sampling theo depth** khi quá nhiều tầng, ví dụ chọn các mức `0,1,2,4,8,16,...` cho mục tiêu debug — phải tài liệu hóa vì đây không phải số lượng event đầy đủ.

**Đếm tổng bằng counter** khi chỉ cần metric aggregate và không muốn tạo log ở mỗi mức.

**Không dùng sampling để tự tắt những enforcement checks bắt buộc**. Sampling nên giới hạn observability phụ trợ, không giới hạn logic an toàn quan trọng.

## 15. Dynamic control flow khác lexical nesting

Một method A gọi B nhưng B được gọi từ nơi khác nữa:

```text
Request path 1: Checkout -> Billing -> Storage
Request path 2: AdminTool ------> Billing -> Storage
```

Nếu một pointcut chọn `Billing` **chỉ khi nó nằm trong flow của Checkout**, việc chọn phụ thuộc **đường gọi runtime**, không chỉ vì Billing thuộc một package hoặc có static call graph gần Checkout.

Đệ quy càng làm rõ điều này: cùng method có thể xuất hiện ở các độ sâu khác nhau dưới các roots khác nhau.

- **Lexical/static location:** class/method/call site được biên dịch.
- **Dynamic control flow:** các join point đang active trong đường thực thi tại thời điểm runtime.
- **Aspect instance association:** singleton/per-object/per-flow nếu công cụ hỗ trợ.
- **Control-flow predicate:** cho biết một điểm có nằm trong scope đang mở hay không.

Không đồng nhất “một method được gọi trong source” với “một dynamic cflow context cụ thể”.

## 16. `cflowbelow` và điều kiện chọn root ngoài cùng

Xét một pointcut P chọn execution của một phương thức recursion. Về mặt ý tưởng, ta muốn:

```text
P and not cflowbelow(P)
```

khi có hỗ trợ để chỉ chọn occurrence P **không nằm bên dưới P khác**.

Tuy nhiên, hãy chú ý các trường hợp:

1. **Nested recursion:** inner P có P ancestor → bị loại.
2. **Mutual recursion:** nếu P chỉ chọn method A, các method B ở giữa không phải P; occurrence A quay lại vẫn có P ancestor.
3. **Call vs execution:** chọn call site P ở caller ngoài có thể không match các inner call sites; guard kết quả khác.
4. **Multiple roots:** nếu một flow P được mở bên trong flow P khác, điểm P mới có thể được coi là nested, không phải root độc lập.
5. **Self-invocation proxy bypass:** inner P execution không được intercept thì cflow predicate không “sửa” coverage thiếu.
6. **Advice-triggered calls:** logging helper khớp P có thể mở một flow P mới ngoài ý định.
7. **Thread hop:** task ở thread khác không tự nằm trong cflow đồng bộ của caller.
8. **Engine-specific semantics:** ký hiệu, khả năng dùng trong advice hay pointcut và chính xác điểm included/excluded phải theo tài liệu engine.

**Kết luận:** `cflowbelow` có thể giúp phân biệt root/inner dynamic context, nhưng **không phải công tắc “giới hạn recursion của Java”**. Nó là tiêu chí chọn join point trong một mô hình AOP có hỗ trợ.

## 17. `per-control-flow` và instance aspect

Một số mô hình AOP có thể tạo **aspect instance theo flow**: một lượt vào join point gốc tạo scope aspect riêng, các join point bên dưới liên kết với instance đó.

```text
Flow A: start P
   Aspect[A]
     -> recursive P
     -> recursive P

Flow B: start P
   Aspect[B]
     -> recursive P
```

Điều này khác shared singleton aspect:

- Một shared aspect có thể phục vụ cả Flow A và Flow B cùng lúc.
- Per-flow aspect có thể cô lập state giữa các flows theo semantics engine.
- Nhưng **một per-flow aspect vẫn có thể được gọi lại đệ quy** trong cùng flow, vì vậy một field `currentMethod` có thể bị ghi đè bởi inner invocation.
- **Per-flow ≠ per-invocation**.
- Scope flow cần cleanup và nested-flow handling rõ.

### Aspect instance và advice local state

Ngay cả khi aspect singleton, mỗi lần around advice chạy vẫn có **local variables riêng**. Một per-flow aspect giúp giữ **state chung của flow**, nhưng state chỉ có ý nghĩa trong một recursive level vẫn cần per-invocation local/scope tương ứng.

Ví dụ:

- **Flow trace ID:** có thể chia sẻ cho cả chuỗi recursion.
- **Current argument của một level:** cần riêng cho từng level.
- **Thời điểm bắt đầu của mỗi level:** cần riêng.
- **Tổng số node visited trong flow:** có thể gắn per-flow và cập nhật an toàn.
- **Global metric tổng lượt gọi:** thuộc shared metric sink, không cần per-flow instance.

## 18. ThreadLocal stack: khi nào giúp, khi nào sai?

Trong demo, `ThreadLocal<Integer>` lưu depth để các advice activations đồng bộ cùng thread nhận biết nhau. Một mô hình cần nhiều dữ liệu hơn có thể dùng `ThreadLocal<Deque<Frame>>`:

```text
enter outer: push Frame(outer)
enter inner: push Frame(inner)
exit inner:  pop  Frame(inner)
exit outer:  pop  Frame(outer)
```

Một stack LIFO đúng giúp khôi phục scope khi nested invocation return/throw.

### Những bất biến cần kiểm

1. Một entry thành công phải có một exit/cleanup tương ứng.
2. `push` trước khi code có thể gọi join point khác.
3. `pop` trong `finally` để xử lý return/throw.
4. Khi stack rỗng, `ThreadLocal.remove()` để tránh giữ state trong thread pool.
5. Nếu nested, restore outer frame chính xác.
6. Không phụ thuộc việc một callback chạy trên cùng thread nếu API không bảo đảm.
7. Khi advice chỉ được áp dụng một phần, stack đếm **những entry đã intercept**, không phải mọi business call.

### Không thay stack bằng một field duy nhất

`ThreadLocal<Frame> current` chỉ giữ một frame cho mỗi thread. Nếu inner ghi đè, outer sẽ bị mất context trừ khi bạn giữ previous và restore. **ThreadLocal cô lập giữa threads, không tự cô lập nested invocations trên cùng thread.**

### Khi thread pool tái sử dụng worker

Nếu một task để lại depth/context trên ThreadLocal, task kế tiếp trên cùng worker có thể bắt đầu ở depth > 0 dù không có outer advice nào của task mới. `finally` và `remove()` ở scope gốc là quan trọng để tránh lỗi logic lẫn memory retention.

## 19. Có nên dùng `StackWalker` hoặc stack trace để đếm depth?

Không nên xem việc đi qua Java stack trace là lời giải chung cho AOP control-flow depth.

- Stack trace có thể gồm proxy, reflection, compiler-generated và helper frames.
- Việc JIT tối ưu, inlining và lựa chọn runtime có thể ảnh hưởng cách quan sát/chi phí.
- Cùng method có thể được gọi từ nhiều đường khác nhau.
- Stack trace extraction có chi phí cao nếu diễn ra ở mọi recursive level.
- Một pointcut cflow không nhất thiết được triển khai bằng cách đọc stack trace mỗi lần.
- Async/distributed flows không nằm trên cùng một Java stack.

`StackWalker` là API Java có thể hữu ích cho những tình huống diagnostics, nhưng **không thay thế một semantics AOP cflow đã được định nghĩa**.

### Tail-call optimization

Java/JVM **không bảo đảm tổng quát việc tối ưu tail calls** như một phần contract mà mọi chương trình có thể dựa vào để đệ quy vô hạn không tốn stack. Đừng kết luận thuật toán an toàn với input không giới hạn chỉ vì một implementation có thể tối ưu một vài trường hợp.

Một around advice được chèn vào còn có thể thay shape của call stack/performance. **Không dùng call-stack depth quan sát được làm chuẩn duy nhất cho business recursion depth.**

## 20. Recursion qua async: không còn một stack đồng bộ

```text
Thread A:
  process(3)
     submit process(2)
     return

Thread B:
  process(2)
     submit process(1)
     return

Thread C:
  process(1)
```

Về nghiệp vụ có một chuỗi công việc đệ quy, nhưng tại runtime nó **không nằm trên một call stack đồng bộ duy nhất**. Một `ThreadLocal` ở A không tự xuất hiện ở B/C. Một `cflow` dựa trên call stack đồng bộ không tự bao phủ continuation qua executor.

Muốn nối operations async, cần:

- Correlation/trace ID có contract.
- Explicit context carrier hoặc propagation phù hợp.
- Parent/child operation references nếu cần.
- Cleanup khi complete/cancel/timeout.
- Chính sách lifecycle khi callback sống lâu hơn request.
- Quy tắc security đối với context đã được truyền.

**Distributed trace/span depth không đồng nghĩa AOP advice nesting depth.** Một span con có thể chạy đồng thời với span khác mà không có quan hệ LIFO.

## 21. Exception unwinding khi đệ quy

Nếu exception phát sinh ở tầng sâu:

```text
level 0 enters
  level 1 enters
    level 2 enters
      level 2 throws
    level 1 observes / rethrows
  level 0 observes / rethrows
caller receives error
```

Tùy loại advice và pointcut, nhiều lớp có thể ghi lỗi **cho cùng một Throwable**. Nếu mỗi tầng ghi full stack trace, số log có thể tăng rất nhanh. Cần phân biệt:

- **Một exception object** lan qua nhiều advice activations.
- **Nhiều exception objects** nếu các tầng wrap/translate lỗi.
- **Một business failure** có thể tạo nhiều error events ở các depth.
- **Một cleanup failure** có thể che lỗi gốc.

### Preserve lỗi khi unwind

```java
// Pseudocode trong around advice.
try {
    return proceed();
} catch (Throwable original) {
    recordFailureAtThisDepth(original);
    throw original;
} finally {
    restoreDepth();
}
```

Việc `throw original` giữ loại, cause, identity và trace của lỗi gốc theo Java semantics. Nếu advice tạo wrapper mới ở mỗi recursive level, cause chain có thể tăng theo depth mà không thêm ý nghĩa mới. Hãy map tại boundary thích hợp, không wrap tự động mọi tầng.

### Không suy ra “mỗi advice.throw = một lỗi nghiệp vụ mới”

Trong một recursive unwind, cùng một failure có thể được quan sát ở nhiều level. Nếu metric “business failures” tăng ở mọi level, nó có thể **đếm trùng**. Cân nhắc chỉ ghi final failure ở root, còn từng tầng có event kỹ thuật riêng nếu cần debug.

## 22. Security và recursion: guard không được làm mất kiểm tra bắt buộc

Một số advice dùng để kiểm tra quyền, validation hoặc những bất biến nghiệp vụ. Nếu dùng guard:

```java
// Pseudocode có thể nguy hiểm nếu chặn toàn bộ advice bắt buộc.
if (depth > 0) {
    return proceed();
}
checkPermission();
return proceed();
```

Các recursive executions ở depth > 0 bỏ qua `checkPermission`. Điều này **chỉ hợp lý nếu policy chứng minh kiểm tra một lần ở root là đủ cho toàn bộ những thao tác bên trong**. Nếu inner recursion truy cập đối tượng khác, tenant khác hoặc tài nguyên có quyền khác, cách làm trên có thể vi phạm bảo mật.

**Nên phân biệt guard chống log trùng** với **guard tắt một security decision**. Một aspect audit bắt buộc cũng cần kiểm tra coverage của mọi entry point: proxy/self-invocation bypass, load-time weaving scope và async boundaries có thể ảnh hưởng.

Một số kiểm tra nên đặt ở boundary không thể bị caller không tin cậy bypass, thay vì chỉ dựa vào giả định “aspect luôn bao phủ mọi đường”.

## 23. Những sai lầm thường gặp

1. **“Method đệ quy N mức thì advice luôn chạy N lần.”** Proxy/self-invocation và pointcut có thể khác.
2. **“Một dòng call site nghĩa là advice chỉ chạy một lần.”** Một call instruction có thể chạy nhiều occurrence.
3. **“Execution pointcut và call pointcut tương đương.”** Chúng nằm ở hai vị trí khác nhau.
4. **“`this.recursive()` luôn đi qua wrapper proxy.”** Không với Java Dynamic Proxy bao target riêng.
5. **“Mọi self-invocation của mọi kiểu proxy đều bypass.”** Quá rộng; còn tùy dispatch/interception model.
6. **“Depth của advice là depth của thuật toán.”** Chỉ có thể trùng khi coverage và quy ước phù hợp.
7. **“`cflow` là một bộ đếm nguyên.”** Nó là khái niệm điều kiện luồng điều khiển; nesting count riêng.
8. **“`cflowbelow(P)` không bao giờ khớp một occurrence P.”** Inner recursive P có thể nằm dưới ancestor P.
9. **“Chỉ cần `!cflowbelow(P)` là mọi thứ tự động được weave.”** Nó không sửa coverage bị thiếu.
10. **“Đệ quy chỉ là gọi cùng method.”** Mutual recursion đi qua nhiều method/object.
11. **“Một ThreadLocal slot tự xử lý nested context.”** Inner có thể ghi đè; cần stack/restore.
12. **“`volatile depth` đúng cho mọi thread.”** Một global counter không phản ánh nesting riêng từng thread/flow.
13. **“Tăng depth trong before nhưng không giảm khi exception.”** Dẫn tới depth rò sang lời gọi mới.
14. **“Một synchronized block sửa được sai scope.”** Lock không tạo invocation state riêng.
15. **“Per-flow aspect chắc giữ current argument an toàn.”** Nhiều tầng trong flow vẫn dùng cùng instance.
16. **“Một around advice chạy = một target execution.”** Around có thể skip hoặc gọi proceed nhiều lần.
17. **“Retry depth và recursion depth giống nhau.”** Số lần thử lại là trục khác.
18. **“Inclusive time của các tầng cộng lại bằng wall elapsed.”** Inner bị cộng lặp trong outer.
19. **“Log một lần ở root luôn tốt nhất.”** Debug/per-level accounting có thể cần từng tầng.
20. **“Log mọi tầng luôn vô hại.”** Deep recursion có thể làm bùng nổ event/chi phí.
21. **“Advice tự gọi logging helper thì helper không bao giờ bị intercept.”** Có thể tạo recursion trong chính aspect.
22. **“Guard chống recursion được phép bỏ qua permission check.”** Phải có chứng minh policy.
23. **“ThreadLocal tự truyền qua executor.”** Thread khác có context riêng.
24. **“Một recursive call async vẫn là một stack LIFO.”** Nhiều tasks có thể chạy đồng thời.
25. **“StackWalker luôn cho AOP cflow semantics.”** Diagnostics stack khác model pointcut.
26. **“JVM chắc luôn tail-call optimize recursion.”** Không có bảo đảm tổng quát.
27. **“Catch StackOverflowError để chữa thuật toán vô hạn.”** Không phải cơ chế kiểm soát resource đáng tin.
28. **“Exception ở ba depth là ba failure độc lập.”** Có thể là một Throwable đang unwind.
29. **“Độ sâu log toàn cục luôn tăng/giảm có trật tự.”** Nhiều thread khiến event interleave.
30. **“Một test factorial qua proxy chứng minh bytecode weaving của engine khác.”** Chỉ chứng minh cơ chế đã thực thi trong test.

## 24. Quy trình kiểm thử độ sâu advice

**Bước 1 — Chọn nghĩa của depth.** Zero-based active advice count, số business frames, hay số flow roots?

**Bước 2 — Xác định loại join point.** Method call hay execution? Caller/callee nào cần được instrument?

**Bước 3 — Xác định object/path.** Lời gọi qua proxy, self-reference, raw target hay execution weaving?

**Bước 4 — Test recursion bình thường.** Với `factorial(3)`, dự đoán ba target executions và advice entries tương ứng.

**Bước 5 — Test direct self-call.** Khẳng định boundary wrapper proxy không thấy inner `this` calls.

**Bước 6 — Test explicit proxy reentry.** Khẳng định nested advice depths 0,1,2.

**Bước 7 — Test return unwinding.** Thứ tự advice exits theo LIFO, kết quả đúng.

**Bước 8 — Test exception unwinding.** Throwable preserved, `finally` restore, không rò depth sau lỗi.

**Bước 9 — Test mutual recursion.** Chọn điểm A/B khác nhau để quan sát số activation.

**Bước 10 — Test guard/filter.** Root-only logging không loại bỏ những checks cần thực hiện ở inner.

**Bước 11 — Test concurrency.** Hai thread gọi cùng target/proxy không làm mất state của nhau.

**Bước 12 — Test async.** Đừng mong ThreadLocal/cflow đồng bộ tự propagate qua executor.

**Bước 13 — Test overhead.** Đo log/metric growth khi depth tăng và tình trạng resource.

### Ma trận cần có

| Tình huống | Kỳ vọng quan sát |
| --- | --- |
| Target recursion 3 tầng qua `this`, wrapper proxy | 3 target executions, 1 advice activation |
| Target recursion 3 tầng quay qua proxy | 3 target executions, 3 advice activations |
| Execution bytecode weaving đầy đủ 3 tầng | Có thể 3 advice activations nếu pointcut match mọi execution |
| Pointcut chỉ chọn root call site | Inner call sites không tự được chọn |
| Root-only flow filter | Chỉ outer P nếu inner P nằm dưới ancestor P |
| Around skip `proceed` | Target có thể không chạy |
| Around retry 3 lần | Có thể 3 target attempts với 1 outer around activation |
| Inner target throw, outer propagates | Một Throwable có thể được quan sát ở nhiều depth |
| Cleanup trong `finally` | Depth trở về 0 sau root |
| Nested advice trên cùng thread | Outer context không bị inner ghi đè |
| Hai threads cùng handler | Thread-local nesting tách theo thread |
| Thread pool tái sử dụng worker | Không còn ThreadLocal cũ sau scope |
| Async task tạo trên executor | Không mặc nhiên nằm trong synchronous cflow |
| Logging helper cũng match pointcut | Phải có scope/exclusion tránh recursion ngoài ý định |
| Deep recursion | Không bùng log và không dựa vào `StackOverflowError` làm policy |

### Không test chỉ bằng số dòng log

Một advice có thể chạy nhưng sampling/filter log không xuất event. Một target có thể chạy nhưng bypass proxy. Một exception được nhìn thấy nhiều lần nhưng vẫn là một failure. Test nên đếm riêng **target entries, advice entries, advice depth, returns, throws, scope cleanup** và kết quả cuối caller.

## 25. Bài tập tự luyện

1. Chạy `RecursionAspectDepthDemo.java` và đối chiếu toàn bộ stdout.
2. Với `factorial(4)`, dự đoán số dòng `target n=` và `advice.enter` trong hai chế độ.
3. Vẽ cây/stack của `factorial(4)`: biểu diễn depth 0,1,2,3 và thứ tự unwind.
4. Vì sao `this.factorial(n-1)` không quay vào Java Dynamic Proxy wrapper trong demo?
5. Thay `self.factorial(n-1)` bằng `this.factorial(n-1)`, giữ handler; output nào biến mất?
6. Sửa demo để in `level = d+1`, so sánh quy ước depth với level.
7. Bỏ `depth.remove()` ở tầng root; suy luận rủi ro giữ state trong thread pool. Chạy lời gọi tiếp theo và xem depth với/không có restore phù hợp.
8. Cố ý chuyển cleanup ra khỏi `finally`, rồi gây exception; đo depth của invocation sau.
9. Thêm một method `even` gọi `odd` và ngược lại; pointcut chỉ chọn `even` sẽ quan sát bao nhiêu activation?
10. Viết pointcut khái niệm cho “chọn P chỉ khi không nằm bên dưới P khác” nếu engine hỗ trợ dynamic control flow.
11. Giải thích vì sao inner occurrence P có thể khớp `cflowbelow(P)` do ancestor P.
12. Một method recursive được dệt execution join point: tại sao tạo object bằng `new` chưa chắc loại bỏ advice?
13. Một pointcut call chỉ dệt caller bên ngoài: tại sao không tự chọn recursive call site bên trong target?
14. Tạo một advice cố ý gọi lại method cùng pointcut. Quan sát số activation tăng và đề xuất exclusion an toàn.
15. Tạo guard chỉ log ở depth=0 nhưng vẫn proceed ở inner. Vì sao không dùng guard đó cho authorization bắt buộc mà thiếu chứng minh?
16. Thêm elapsed-time metric từng level, giải thích vì sao tổng inclusive time lớn hơn root duration.
17. Tính exclusive time khi có hai child invocations tuần tự và tổng time phù hợp; điều gì thay đổi khi hai child chạy song song?
18. Cho một around advice gọi `proceed` hai lần, xác định số advice entries bên ngoài và số target executions.
19. Cho hai advice lồng nhau quanh mỗi recursion level. Phân biệt depth của từng aspect và tổng stack advice frames.
20. Viết test hai thread dùng cùng `TracingHandler`, xác minh depth mỗi thread đều bắt đầu 0.
21. Dùng executor cho recursion theo task; tại sao ThreadLocal depth ở thread caller không xuất hiện ở worker?
22. Một Throwable ném ở depth 3 rồi được rethrow qua depth 2,1,0: làm sao tránh đếm thành bốn business failures?
23. Đưa ra budget giới hạn input recursion thay vì dựa vào advice depth; tại sao đáng tin cậy hơn khi proxy coverage không đầy đủ?
24. Thiết kế trace gồm root event, nested events được sample và một final failure event; giải thích cách tránh nhầm số business operations.
25. Lập checklist kiểm tra call/execution, proxy/weaving scope, `cflow` support, cleanup, concurrency và performance cho một ứng dụng thực.

**Tự kiểm tra:** Recursion depth và advice activation depth khác nhau như thế nào? Vì sao trong demo một thuật toán có ba target executions nhưng có lúc chỉ một advice? Một recursive occurrence P có thể nằm trong `cflowbelow(P)` không? `P && !cflowbelow(P)` cần những điều kiện nào để thật sự chọn root? Khi exception đi ra, vì sao phải khôi phục depth ở `finally`? Có thể dùng `ThreadLocal` làm distributed call depth không? Nếu một around advice retry, số lần `proceed` có bằng số advice activations không?

## Kết luận

**Lời gọi đệ quy làm lộ rõ khác biệt giữa độ sâu của chương trình và độ sâu can thiệp thực tế của AOP.** Một method có thể thực thi nhiều lần nhưng wrapper proxy chỉ quan sát lần đầu nếu inner `this` calls bypass; ngược lại execution weaving hoặc explicit proxy reentry có thể khiến mỗi tầng đệ quy kích hoạt advice. **`cflow`/`cflowbelow`** giúp mô tả vị trí của join point trong dynamic control flow khi engine hỗ trợ, nhưng **không tự bổ sung những join point chưa được weave** và không phải bộ đếm độ sâu universal.

Để thiết kế đúng, hãy xác định **loại join point, đường interception, nghĩa của depth, thứ tự quanh `proceed`, trạng thái riêng mỗi activation và cleanup khi exception**. Quan sát ở root hay mỗi tầng là lựa chọn theo nhu cầu debug, metric và nghiệp vụ; không dùng guard quan sát để bỏ qua kiểm tra bắt buộc. Với recursion có nhiều thread hoặc async, cần context propagation riêng chứ không giả định còn cùng call stack. **Chỉ khi phân biệt các tầng khái niệm ấy, depth mà advice ghi nhận mới có ý nghĩa và đáng tin cậy.**
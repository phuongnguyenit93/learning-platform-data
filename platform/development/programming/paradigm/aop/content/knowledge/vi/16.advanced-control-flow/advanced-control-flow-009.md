# Thiết kế ví dụ để kiểm chứng chính xác phạm vi điều khiển trong AOP

Một ví dụ về **luồng điều khiển nâng cao** trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**) không chỉ cần in ra vài dòng log rồi kết luận rằng pointcut chạy đúng. Cần thiết kế một **thí nghiệm có giả thuyết, tập join point có thể quan sát, kết quả kỳ vọng độc lập, phản ví dụ và tiêu chí kiểm chứng cụ thể**. Đặc biệt khi dùng các khái niệm **`cflow(P)`** và **`cflowbelow(P)`**, một test chỉ có một entrypoint và một lời gọi con rất dễ bỏ sót lỗi ở root, recursion, ngoại lệ, boundary của proxy và bất đồng bộ.

**Mục tiêu:** tự xây được một ví dụ đủ nhỏ để giải thích và đủ chặt để kiểm tra **điểm khởi đầu P, các điểm nằm dưới P, những điểm nằm ngoài phạm vi, những P lồng nhau và các đường không phát sinh join point**; từ đó phân biệt lỗi ngữ nghĩa control flow với lỗi khả năng intercept của công cụ.

Bài trình bày AOP **nói chung**, không quy định một bộ weaver, framework hay cú pháp DSL cụ thể. Hai chương trình Java 17 dùng instrumentation tường minh và JDK dynamic proxy để kiểm nghiệm những **tính chất được nêu**, chứ **không giả vờ** rằng Java thuần tự cung cấp mọi pointcut control-flow. Mỗi ví dụ có lệnh chạy, stdout xác định và giải thích rõ điều gì được chứng minh, điều gì chưa.

## 1. Xác định chính xác “phạm vi điều khiển” cần kiểm chứng

Các khái niệm gốc:
- **Join point:** một điểm chương trình có thể được AOP can thiệp, như method call hoặc method execution khi mô hình hỗ trợ.
- **Pointcut:** điều kiện chọn các join point; có thể dùng thông tin cấu trúc, runtime args/target, hoặc dynamic control flow.
- **Advice:** hành vi before, after, around hoặc dạng khác thực thi ở những join point phù hợp.
- **Weaving:** quá trình đưa advice vào mã, bytecode, lúc nạp lớp hoặc qua proxy/interceptor.
- **Control flow động:** quan hệ các lần thực thi/lời gọi đã thực sự diễn ra trong một hoạt động; nó phụ thuộc vào stack và đường điều khiển runtime.
- **P:** pointcut dùng để chọn **các occurrence có thể mở phạm vi**.
- **Root occurrence:** một lần xảy ra join point thực sự khớp P.
- **Descendant/below:** một join point occurrence xảy ra khi một root P ở phía ngoài **vẫn đang active**.

Khi P là điều kiện khớp nhiều lần, không thể đơn giản gọi “method này là root nên chắc không phải below”. Tính chất root/below là quan hệ **giữa những occurrence trên đường thực thi**, không phải nhãn cố định trên tên method.

Hai lựa chọn khái niệm phổ biến:

- **`cflow(P)`**: tại join point j đúng nếu có một P occurrence đang bao gồm chính j hoặc bao một đường thực thi chứa j.
- **`cflowbelow(P)`**: tại j đúng nếu có một P occurrence **ở bên ngoài j**, tức j nằm **bên dưới** lần P ấy, chứ không phải chính occurrence P khởi đầu phạm vi ấy.

Ví dụ đơn giản:

~~~text
entry()  <- P: root ngoài
   |
   +--> validate()   <- bên dưới P
   +--> persist()    <- bên dưới P

unrelated()            <- nằm ngoài phạm vi P
~~~

| Occurrence | `cflow(P)` | `cflowbelow(P)` |
| --- | --- | --- |
| `entry()` root ngoài cùng | Có | Không |
| `validate()` dưới entry | Có | Có |
| `persist()` dưới entry | Có | Có |
| `unrelated()` sau khi entry kết thúc | Không | Không |

**Bẫy quan trọng:** khi `entry()` gọi chính `entry()` lần nữa, root **bên trong** có thể thuộc **`cflowbelow(P)`** vì nó nằm dưới root **bên ngoài**. Một ví dụ không kiểm tra tình huống này chưa đủ chặt.

## 2. Phát biểu hợp đồng trước khi viết code

Một test tốt cần định nghĩa đủ sáu thành phần:

1. **Loại join point:** P chọn method **call**, method **execution**, hay một ranh giới proxy được mô phỏng? Không dùng lẫn các khái niệm.
2. **Vị trí gốc:** đâu là P occurrence bắt đầu phạm vi? P có thể được gọi lồng hoặc đệ quy không?
3. **Universe các điểm quan sát:** root, child, sibling, ngoài root, lỗi, async; **không** tính những phương thức chưa thực sự chạy.
4. **Semantics đối chiếu:** root có được tính trong `cflow`? Thế nào là “below”? Khi có nhiều P, chọn root nào?
5. **Tín hiệu quan sát:** một dòng event có loại occurrence, active ancestor depth, kết quả match và correlation phù hợp; không chỉ `println("advice fired")`.
6. **Điều kiện pass/fail:** giá trị và thứ tự dự kiến độc lập với code đang tính kết quả; mọi điểm không chọn cũng được kiểm tra.

Một hợp đồng thí nghiệm ví dụ:

~~~text
P := execution occurrence of operation root()

cflow(P):
  true at P itself and at every observable join point
  dynamically nested inside any active P occurrence.

cflowbelow(P):
  true at a join point j when there exists an active
  P ancestor distinct from the occurrence j itself.

When no P is active and j is not P, both false.
~~~

Đây là **giả mã ngữ nghĩa**, không phải cú pháp của mọi AOP language. Với mô hình **method-execution** trong ví dụ tự instrument, ta sẽ ghi nhận P tại thời điểm bắt đầu body rồi đẩy root lên stack cho các child events.

**Đừng chuyển ngay từ ý tưởng sang code:** nếu không thống nhất call hay execution, một test nhìn đúng về output vẫn có thể kiểm chứng sai điều kiện thực tế cần dùng.

## 3. Thiết kế bộ tình huống: dương, âm và biên

Một bộ test nên có cả những trường hợp **advice phải xuất hiện** và **advice không được xuất hiện**.

| ID | Đường chạy | Kỳ vọng cần kiểm chứng |
| --- | --- | --- |
| T0 | `outside()` khi chưa có P | Cả `cflow` và `cflowbelow` false |
| T1 | Bắt đầu P ngoài cùng | `cflow` true; `cflowbelow` false tại root |
| T2 | Child trực tiếp trong P | Cả hai true |
| T3 | Grandchild nhiều tầng bên dưới P | Cả hai true, dù không gọi trực tiếp từ P |
| T4 | Một P khác được gọi bên trong P ngoài | Cả hai true **ngay tại P trong** |
| T5 | Child bên trong P trong | Cả hai true; có hơn một P đang active |
| T6 | Quay ra P ngoài sau khi P trong kết thúc | Cả hai vẫn true ở child của P ngoài |
| T7 | Sibling/đường ngoài sau P return | Cả hai false |
| T8 | Root P ném exception | Cleanup, event sau root không bị đánh dấu P |
| T9 | Root P short-circuit trước child | Không có child occurrence để chọn |
| T10 | Nhánh `if` không được thực thi | Không phát event cho một điểm chỉ tồn tại trên sơ đồ tĩnh |
| T11 | Async worker được scheduling bên trong P | Không tự ở trong call stack P của caller |
| T12 | Một method được gọi cả trong và ngoài P | Cùng signature, kết quả membership khác |
| T13 | Proxy intercept outer, inner được gọi trên target | Có thể thiếu advice ở inner nếu bypass proxy |
| T14 | Hai thread cùng chạy hai flow độc lập | State P không rò từ flow này sang flow kia |
| T15 | Advice/handler ném lỗi | Phân biệt matcher với loại advice và exception path |
| T16 | Root P đệ quy nhiều tầng | Inner P vẫn có thể là below outer P |
| T17 | Helper/logging bên trong P | Không vô tình instrument thêm điểm gây recursion |

**Đừng cố gắng có 17 test chỉ bằng 17 dòng log không điều kiện.** Các ca được chọn phải liên kết với một giả thuyết rõ và kết quả độc lập. Nếu một join point không tồn tại do nhánh không chạy, **sự vắng mặt của event chính là kỳ vọng**.

## 4. “Oracle” độc lập là gì?

**Oracle** là bộ dữ liệu/kết quả dùng để xác định việc triển khai có đúng hay không. Nếu test xác nhận bằng cách **tính expected bằng chính hàm production đang được kiểm tra**, test có thể cùng sai với code mà vẫn pass.

Ví dụ dễ mắc lỗi:

~~~java
// Mảnh minh họa phản ví dụ, không phải chương trình độc lập.
boolean actual = matcher.isInControlFlow(event);
boolean expected = matcher.isInControlFlow(event);
assert actual == expected; // Không kiểm chứng điều gì.
~~~

Tốt hơn:
- Vẽ **timeline** của các P occurrences và điểm child.
- Tự lập **bảng expected** trước khi viết matcher.
- Dùng **literal expectations** trong test hoặc một oracle dựa trên stack mô tả riêng, không lấy expected từ matcher.
- Kiểm tra mỗi event theo **location + expected result**, không chỉ số event tổng.
- Thêm **negative controls** (outside, no-execution, direct call, cross-thread).
- Kiểm chứng cả **thứ tự** và **số lần** advice khi ngữ nghĩa yêu cầu.

Ở ví dụ đầy đủ bên dưới, mỗi event được đưa các expected booleans **ghi tường minh tại call site** và test ném `AssertionError` nếu lệch. Điều này đáng tin hơn việc nhìn một log được tính từ chính matcher rồi tự kết luận đúng.

## 5. Xác định điểm khởi đầu P và con nào là “below”

Một sơ đồ dễ đối chiếu:

~~~text
Time -------------------------------------------------------->

T0       outside()                            outside -> false,false
T1       P outer enters                       outer   -> true,false
T2         child A                            child A -> true,true
T3         P inner enters                     inner   -> true,true
T4           child B                          child B -> true,true
T5         P inner exits
T6         child C                            child C -> true,true
T7       P outer exits
T8       outside()                            outside -> false,false
~~~

Hai vấn đề quan trọng:

**Một:** `cflowbelow(P)` là **quan hệ với một occurrence P ở phía trên**. Chính P trong (T3) cũng là hậu duệ P ngoài (T1); do đó below=true tại inner root khi P ngoài đang active.

**Hai:** một join point có thể có **nhiều P ancestors**. Nếu muốn chỉ chọn “child trực tiếp của P ngoài” hoặc “chỉ một root ngoài cùng”, `cflowbelow(P)` **chưa đủ**, vì nó cũng nhận grandchild và nested P. Khi đó cần thêm điều kiện độ sâu, kind, entrypoint identity hoặc hợp đồng khác.

### 5.1 Sử dụng số root active thay vì một boolean ngây thơ

Một state thủ công có thể dùng:
- Boolean `inRoot`: đủ cho việc hỏi "có ít nhất một P active" nếu cleanup đúng, nhưng không phân biệt root lồng.
- Counter `activeRootDepth`: mô tả số P occurrences đang active.
- Stack root IDs: lưu thứ tự và root cụ thể, hữu ích khi cần binding theo root gần nhất/ngoài cùng.

Cẩn thận: không dùng `static boolean inRoot` dùng chung cho nhiều thread; nó có thể khiến một task độc lập bị đánh dấu nhầm ở trong P khi thread khác đang chạy root.

## 6. Java 17 hoàn chỉnh: bộ kiểm thử có expected literals

Chương trình dưới đây **mô phỏng** method-execution join point P bằng một `root(...)` có instrumentation tường minh. Một `ThreadLocal<Deque<String>>` chỉ chứa những P occurrences đang hoạt động trên **thread hiện tại**. Khi quan sát event:
- Nếu event **chính là P mới**: `cflow=true` ngay cả khi chưa có ancestor P; `below=true` chỉ nếu đã có root P phía ngoài.
- Nếu event **không phải P**: cả `cflow` và `below` true khi có ít nhất một root P active.
- Nếu không phải P và không có root active: cả hai false.

Điểm có chủ đích: **event P được kiểm tra trước khi push chính nó vào stack**. Nếu push trước rồi tính `below = depth>0`, root ngoài sẽ bị tính sai là below! Sau khi kiểm tra root, code mới push để các child nhìn thấy root đang active.

Mỗi event so sánh với **depth/cflow/below kỳ vọng ghi thành literal**, giúp phát hiện các sai lệch ở root, inner root và cleanup. Worker async **chỉ trả chuỗi** về main để stdout không phụ thuộc scheduler.

Lưu vào **`ControlFlowScopeVerification.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ControlFlowScopeVerification {
    private static final ThreadLocal<Deque<String>> ACTIVE =
            new ThreadLocal<>();

    static int ancestorDepth() {
        Deque<String> stack = ACTIVE.get();
        return stack == null ? 0 : stack.size();
    }

    static String inspect(
            String label,
            boolean thisEventMatchesP,
            int expectedDepth,
            boolean expectedCflow,
            boolean expectedBelow) {
        int depth = ancestorDepth();

        boolean cflow = thisEventMatchesP || depth > 0;
        boolean below = depth > 0;

        if (depth != expectedDepth
                || cflow != expectedCflow
                || below != expectedBelow) {
            throw new AssertionError("scope mismatch at " + label);
        }

        return label
                + " depth=" + depth
                + " cflow=" + cflow
                + " below=" + below;
    }

    static void event(
            String label,
            int depth,
            boolean cflow,
            boolean below) {
        System.out.println(
                inspect(label, false, depth, cflow, below));
    }

    static void root(
            String name,
            int expectedAncestors,
            boolean expectedBelow,
            Runnable body) {
        // Tại P occurrence: chưa push chính P vào stack.
        System.out.println(
                inspect("P:" + name, true,
                        expectedAncestors, true, expectedBelow));

        Deque<String> stack = ACTIVE.get();
        if (stack == null) {
            stack = new ArrayDeque<>();
            ACTIVE.set(stack);
        }

        stack.push(name);
        try {
            body.run();
        } finally {
            stack.pop();
            if (stack.isEmpty()) {
                ACTIVE.remove();
            }
        }
    }

    static void workerProbe(ExecutorService pool) {
        try {
            Future<String> future = pool.submit(
                    () -> inspect("async-worker", false,
                            0, false, false));
            System.out.println(future.get());
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    public static void main(String[] args) {
        event("outside-before", 0, false, false);

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            root("outer", 0, false, () -> {
                event("child:first", 1, true, true);
                root("inner", 1, true, () ->
                        event("child:inside-inner",
                                2, true, true));
                event("child:after-inner", 1, true, true);
                workerProbe(pool);
            });
        } finally {
            pool.shutdown();
        }

        event("outside-after", 0, false, false);

        // Short-circuit: root mở phạm vi nhưng không chạy child.
        root("short", 0, false, () -> {});
        event("after-short", 0, false, false);

        try {
            root("error", 0, false, () -> {
                event("child:before-error", 1, true, true);
                throw new IllegalArgumentException("boom");
            });
        } catch (IllegalArgumentException error) {
            System.out.println("CAUGHT " + error.getMessage());
        }

        event("after-error", 0, false, false);
    }
}
~~~

Biên dịch/chạy với **JDK 17+**:

~~~bash
javac ControlFlowScopeVerification.java
java ControlFlowScopeVerification
~~~

Stdout xác định:

~~~text
outside-before depth=0 cflow=false below=false
P:outer depth=0 cflow=true below=false
child:first depth=1 cflow=true below=true
P:inner depth=1 cflow=true below=true
child:inside-inner depth=2 cflow=true below=true
child:after-inner depth=1 cflow=true below=true
async-worker depth=0 cflow=false below=false
outside-after depth=0 cflow=false below=false
P:short depth=0 cflow=true below=false
after-short depth=0 cflow=false below=false
P:error depth=0 cflow=true below=false
child:before-error depth=1 cflow=true below=true
CAUGHT boom
after-error depth=0 cflow=false below=false
~~~

### 6.1 Ca root ngoài cùng: tránh off-by-one

Ngay tại event `P:outer`, depth **trước khi push P** là 0. `cflow` true vì **chính event khớp P**, còn `below` false vì chưa có P ancestor nào.

Nếu vô tình push root vào ACTIVE trước khi tính, code có thể suy `below=true` cho P ngoài. Một test chỉ kiểm child sẽ không phát hiện bug này; vì vậy test root là **bắt buộc**.

### 6.2 Ca root lồng: không loại mọi P occurrence

Tại `P:inner`, stack đã có `outer`, nên `depth=1`. Inner là P occurrence **mới**, nhưng cũng nằm dưới outer P. Kỳ vọng `cflow=true`, `below=true`.

Đây là **case phân biệt ngữ nghĩa**: một matcher sai kiểu `below = depth > 0 && !matchesP` sẽ trượt ca inner root, dù qua test outer root/leaf bình thường.

### 6.3 Ca child bên trong và sau root lồng

`child:inside-inner` thấy hai root active: outer và inner. `child:after-inner` chỉ còn outer sau khi inner kết thúc. Cả hai vẫn được chọn bởi `cflow` và `below`.

Bộ test này phát hiện lỗi **không pop stack khi inner root rời**: khi đó `child:after-inner` sẽ có depth 2 thay vì 1. Nếu chỉ ghi booleans, cả hai vẫn true và bug depth bị che.

### 6.4 Ca outside và cleanup

Khi `outer` kết thúc, `ACTIVE.remove()` xóa trạng thái của thread. Event `outside-after` có depth=0. Tương tự, khi `root("error")` ném lỗi, `finally` vẫn pop/remove; event `after-error` phải ở ngoài phạm vi.

**Lỗi điển hình**: chỉ xóa marker khi thành công, dẫn tới một request sau trên thread pool bị đánh dấu nhầm bên trong control flow của request trước.

### 6.5 Ca short-circuit

`root("short", ...)` có **root event**, nhưng body rỗng, không có child occurrence. Không thể yêu cầu một advice ở `cflowbelow(P)` ghi sự kiện cho một method không bao giờ chạy. Kỳ vọng là **không có dòng `child:short`**, chứ không phải một dòng child có `below=false`.

### 6.6 Ca async: một thread khác không tự kế thừa dynamic stack

`workerProbe(pool)` được gọi **khi root outer còn active trên caller thread**, nhưng callable thực thi trên một worker khác. Worker không có stack ACTIVE của caller nên depth=0, cả hai booleans false.

Đây là mô hình **per-thread dynamic stack**. Nó không cấm ứng dụng **chủ động truyền trace/correlation context** qua async boundary. Tuy nhiên, **logical context propagation** không đồng nhất với câu hỏi một method execution có thuộc cùng **dynamic call-stack control flow** hay không.

### 6.7 Mã này chứng minh đến đâu?

Nó minh họa **oracle và các quy tắc kiểm chứng** cho phạm vi P trong một instrumentation tự xây. Nó **không chứng minh** rằng:
- Java tự có một pointcut `cflow/cflowbelow` ngầm.
- Bất cứ advice nào ở bất cứ công cụ nào cũng quan sát được toàn bộ method execution.
- Mọi async task đều nằm ngoài mọi định nghĩa logic operation (những framework tracing có thể định nghĩa khái niệm flow mở rộng).
- Một `ThreadLocal` chứa root stack có thể dùng thay security context.
- Demo tự bao phủ tất cả loại join point, annotations, generics hoặc các đường gọi bypass.

Một test **cơ chế AOP thực tế** phải lấy sơ đồ này làm **bảng expected**, sau đó cấu hình **pointcut thật**, tạo những lời gọi thật và quan sát advice tương ứng. Không dùng implementation mô phỏng làm bằng chứng nền tảng có khả năng weaving mà nó không hỗ trợ.

## 7. Ví dụ Java 17 thứ hai: kiểm chứng giới hạn proxy không phải cflow

Một tình huống dễ chẩn đoán sai: child đang **nằm dưới root về mặt call stack**, nhưng advice đặt trên proxy **không nhận được lời gọi child**. Nếu chỉ nhìn “advice không chạy” rồi kết luận child ở ngoài `cflow`, ta đã nhầm **phạm vi động** với **khả năng intercept**.

Chương trình JDK dynamic proxy sau minh họa đúng ranh giới. `Real.outer()` gọi `this.inner()` trên chính target; `InvocationHandler` chỉ thấy lời gọi **đi qua proxy**.

Tạo file `ProxyBoundaryVerification.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class ProxyBoundaryVerification {
    interface Work {
        void outer();
        void inner();
    }

    static final class Real implements Work {
        @Override
        public void outer() {
            System.out.println("TARGET outer");
            this.inner();
        }

        @Override
        public void inner() {
            System.out.println("TARGET inner");
        }
    }

    static Work wrap(Work target) {
        return (Work) Proxy.newProxyInstance(
                Work.class.getClassLoader(),
                new Class<?>[] { Work.class },
                (proxy, method, args) -> {
                    System.out.println("HANDLER " + method.getName());
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException error) {
                        throw error.getCause();
                    }
                });
    }

    public static void main(String[] args) {
        Real original = new Real();
        Work proxy = wrap(original);

        System.out.println("CASE through-proxy-outer");
        proxy.outer();

        System.out.println("CASE through-proxy-inner");
        proxy.inner();

        System.out.println("CASE direct-inner");
        original.inner();
    }
}
~~~

Lệnh chạy:

~~~bash
javac ProxyBoundaryVerification.java
java ProxyBoundaryVerification
~~~

Stdout xác định:

~~~text
CASE through-proxy-outer
HANDLER outer
TARGET outer
TARGET inner
CASE through-proxy-inner
HANDLER inner
TARGET inner
CASE direct-inner
TARGET inner
~~~

### 7.1 Bằng chứng về coverage

- Qua `proxy.outer()`: handler in `HANDLER outer`, target chạy outer rồi **tự gọi** inner. Không có `HANDLER inner` cho lời gọi này, vì `this.inner()` nằm trên target `Real`.
- Qua `proxy.inner()`: handler thấy inner.
- Qua `original.inner()`: bypass proxy hoàn toàn.

Do đó: **“target inner được thực thi”** và **“advice trong invocation handler chạy cho inner”** là hai mệnh đề khác nhau.

### 7.2 Không tuyệt đối hóa với mọi loại weaving

Một mô hình **bytecode weaving ở method execution** có thể quan sát cả inner method execution dù được gọi từ `this`; một cơ chế subclass proxy có thể có dispatch khác mô hình delegation nêu trên. Ví dụ chỉ khẳng định khả năng của **JDK interface proxy cụ thể được code tạo ra**.

Khi thiết kế test `cflowbelow(P)` của một bộ AOP, phải xác nhận công cụ có **khả năng quan sát child join point** trước khi dùng việc thiếu log để suy về control flow.

## 8. Ranh giới call và execution phải được kiểm chứng riêng

Trong những mô hình AOP phân biệt **method call** và **method execution**, một thao tác nguồn có thể có hai loại join point:

~~~text
Caller.doSomething()
   |
   | CALL of Target.handle(...)
   v
Target.handle(...)
   | EXECUTION of handle
   v
 business body
~~~

Nếu P là `call(Target.handle)`, root là **điểm phát sinh lời gọi**. Nếu P là `execution(Target.handle)`, root là **điểm thực thi phần thân**. Trong một call đơn giản hai phạm vi có thể gần như trùng nhau, nhưng:
- CALL có thể xảy ra rồi target execution chưa bắt đầu hoặc không thành công do dispatch.
- EXECUTION có thể bắt đầu từ một đường call không được pointcut/cơ chế hiện tại nhìn thấy.
- Caller-side `this` của call có thể khác target của execution.
- Proxy handler có thể thêm một boundary mà không thay thế mọi execution join point.

Một test đủ chặt cần ghi:
1. Tên loại join point.
2. Nguồn khai báo/target, đúng overload/descriptor.
3. Thời điểm root event được quan sát.
4. Các child events có thực sự nằm trong phần thân được instrument hay không.
5. Kỳ vọng khi lời gọi lỗi trước khi target body bắt đầu.
6. Kỳ vọng khi gọi cùng method qua một đường khác.

**Không gọi một phương thức cùng tên là cùng occurrence.** Nếu `handle()` được gọi hai lần, hai execution occurrences khác nhau; P có thể active trong lần này và không active ở lần kia.

## 9. Lồng nhau và đệ quy: test không được chỉ có một P

Để kiểm tra đầy đủ `cflowbelow(P)`, tạo cả:
- Một P **ngoài cùng**.
- Một P **bên trong**, được gọi khi P ngoài vẫn active.
- Một child **bên trong P trong**.
- Một child **sau khi P trong kết thúc nhưng trước khi P ngoài kết thúc**.
- Một invocation **ngoài mọi P**.

Ví dụ với P chọn execution của `calculate(int)`:

~~~text
P calculate(2)                 <- outer P: below false
   |
   +--> P calculate(1)         <- inner P: below true
   |      |
   |      +--> leaf()          <- below true
   |
   +--> finish()               <- below true; inner đã thoát
~~~

Một matcher sai có thể:
- Tính `below=false` trên mọi occurrence cũng match P.
- Quên giảm depth khi P trong thoát.
- Chỉ lưu boolean và ghi đè trong recursion.
- Chỉ kiểm một root ID mà bỏ qua root lồng.
- Tính depth sau khi push root nhưng lại dùng depth ấy để kết luận root ngoài thuộc below.

Các lỗi này thường **không lộ trong test chỉ có outer P + one leaf**.

### 9.1 Root ID và binding

Nếu P có binding giá trị `requestId` hoặc tham số, nested P có thể tạo nhiều context:

~~~text
P(request=A)
   |
   +--> P(request=B)
          |
          +--> child
~~~

Child nằm dưới cả P(A) và P(B). Nếu advice cần giá trị root, phải xác định dùng **root gần nhất**, **root ngoài cùng** hay một ngữ nghĩa khác do ngôn ngữ AOP quy định. Không mặc định một biến `currentRequest` toàn cục có thể trả lời đúng mọi trường hợp.

Một test binding nên dùng **hai giá trị phân biệt** và assert value được truyền tại child, không chỉ assert `true` cho membership. Khi có security context, không dùng giá trị binding từ pointcut như chứng cứ quyền nếu nguồn chưa được xác thực.

### 9.2 Kiểm tra cả thời điểm thoát và quay lại

Test chỉ ghi lại **khi root vào** không chứng minh root được dọn đúng. Sau khi P trong kết thúc phải còn root ngoài; sau khi P ngoài kết thúc phải về không. Nhánh exception phải cho kết quả tương tự nhánh return bình thường.

Với instrumentation tự viết, đặt pop/remove trong `finally`, không chỉ trong nhánh thành công.

## 10. Thiết kế thử nghiệm cho exception, short-circuit và retry

### 10.1 Exception

Tạo một child ném exception:

~~~text
P enters
  child throws
P finally exits
outside executes
~~~

Yêu cầu:
- Child là điểm có occurrence thực, nên trước lúc ném nó có thể nằm dưới P.
- Sau khi P thoát qua exception, outside không nằm trong P.
- Một **after-returning** advice không xuất hiện khi join point ném lỗi **không chứng minh cflow sai**; cần phân biệt loại advice và nhánh execution.
- Một **after-throwing** hoặc finally-like advice có điều kiện riêng, không được dùng thay matcher membership.

### 10.2 Short-circuit

Nếu around advice ở P **không gọi continuation**, các child dự kiến trong target body có thể **không xảy ra**:

~~~text
P/around before
  deny or cache hit
return without proceed

(no business child event)
~~~

Test đúng phải kiểm tra **sự vắng mặt của child event**. Không sinh một event giả với membership=false rồi ghi “child outside P”: nó chưa từng là join point runtime.

### 10.3 Retry

Nếu around advice gọi continuation nhiều lần theo hợp đồng của công cụ, một request logic có thể có **nhiều occurrences của target/child**. Metric số join point không tự là số request. Thiết kế test cần phân biệt:
- Request count.
- Attempt count.
- Execution/join-point occurrence count.
- Success/failure count.
- Retry limit và side effects.

Không retry thao tác có side effect bừa bãi chỉ để thu thêm log; cần idempotency/dedup và failure policy phù hợp.

### 10.4 Advice chính nó tạo join point

Một logging advice có thể gọi formatter, exporter hoặc sink nằm trong tập pointcut. Khi đó advice tự sinh thêm join point ở dưới P, có thể tạo recursion. Tách infrastructure khỏi phạm vi lựa chọn phù hợp hoặc dùng guard có chính sách rõ cho concern **được phép** giảm ghi nhận, không bỏ qua authorization/audit bắt buộc.

## 11. Đồng thời và bất đồng bộ: hai loại “flow” khác nhau

Trong ví dụ đồng bộ, dynamic cflow thường được hiểu theo một đường thực thi đang active. Khi `P()` gửi task sang executor:

~~~text
Thread T1                       Thread T2
P execution starts
  executor.submit(task) ---------> task starts
P execution ends                    task may continue
~~~

Nếu task thực thi trên T2, **stack của T2 không tự chứa P occurrence từ T1**. Một `ThreadLocal` trên caller không tự được truyền sang executor worker.

Phân biệt:
- **Dynamic call flow:** đường lời gọi/thực thi còn active; là cơ sở của `cflow/cflowbelow` theo nghĩa stack thông thường.
- **Logical operation:** request/tracing workflow có thể kéo dài sau khi method return.
- **Causal relationship:** task được scheduling do P, nhưng chưa chắc nằm trong dynamic stack P.
- **Explicit context propagation:** snapshot correlation/trace/tenant metadata được truyền có chủ đích qua task/network.

Một trace ID được truyền sang worker **không tự chứng minh `cflow(P)` true** trong ngôn ngữ pointcut. Một công cụ AOP có thể có mở rộng riêng cho async flow, nhưng phải đọc định nghĩa chính thức của cơ chế đó trước khi dùng.

### 11.1 Negative test quan trọng

Tạo một executor worker không có P đang active và gửi một callable trong lúc caller đang ở P. Test worker depth=0 trong mô hình stack địa phương. Nếu dùng một biến `static boolean inP` chung, worker có thể đọc true sai; ca này sẽ vạch ra lỗi cross-thread contamination.

### 11.2 Nếu muốn test logical context propagation

Đó là **một bài test khác**:
1. Caller capture snapshot an toàn ở submission.
2. Task wrapper install snapshot trên worker.
3. Task thực hiện và đọc correlation context.
4. Worker restore/remove trong `finally`.
5. Task kế tiếp không thấy context cũ.

Không trộn kết luận của bài test logical propagation vào kỳ vọng `cflowbelow(P)` **nếu công cụ không công bố cùng semantics**.

## 12. Điểm quan sát phải được phân loại

Một test trace nên có schema tối thiểu:

~~~text
operation=checkout
joinPointKind=execution
eventId=child-2
matchesRootP=false
activePAncestors=1
expectedCflow=true
expectedBelow=true
~~~

Các trường có giá trị:
- **eventId:** phân biệt occurrence, nhất là đệ quy/cùng method tên.
- **joinPointKind:** call/execution/proxy boundary.
- **matchesRootP:** occurrence hiện tại có thỏa P hay không.
- **activePAncestors:** P occurrences phía ngoài còn active.
- **expectedCflow/expectedBelow:** oracle đã viết độc lập.
- **actual advice hits:** khi chạy trong công cụ thực, advice nào được vào.
- **execution thread/flow ID:** chỉ dùng để phân biệt đường, không coi thread ID là identity người dùng.

Tránh:
- Log toàn bộ `args` hoặc payload.
- In `target.toString()` khi chưa kiểm duyệt dữ liệu.
- Lưu access token/credential.
- Chuyển exception message thô vào audit khi có bí mật.
- Dùng một global mutable `currentUser` để gắn các event.

Một test định danh root không cần PII. Dùng ID giả ngắn và event label cố định; kết quả phải kiểm chứng được từ text đơn giản.

## 13. Cách chạy kiểm chứng với một bộ AOP thực tế

Sau khi có một **mô hình oracle Java thuần**, để kiểm chứng một hệ thống AOP thật:
1. **Khai báo P chính xác**, gồm loại call/execution, method signature và ranh giới scope.
2. Viết advice **quan sát có kiểm soát**, không sửa args/result hay policy trong lần kiểm thử đầu.
3. Tạo một fixture **cố định đường gọi**, tương ứng với bảng T0–T17.
4. Ghi event mỗi join point theo tên phân biệt, không đếm mù.
5. Chạy và so sánh **đủ giá trị lẫn các event không xuất hiện**.
6. Kiểm tra nesting/recursion và exception cleanup.
7. Kiểm tra các điểm mà cơ chế không thể instrument (direct/proxy/self-call, private/static khi thích hợp).
8. Khi sai, xác định **matcher, weaving coverage, advice type, runtime condition hay telemetry** gây ra sai lệch.
9. Pin phiên bản weaver/runtime khi muốn regression ổn định.
10. Với security policy quan trọng, kiểm tra **tất cả đường vào** chứ không dựa duy nhất vào control-flow pointcut.

**Không giả vờ thiếu log luôn là pointcut false.** Một lời gọi có thể không qua proxy; một before advice bên ngoài có thể ném lỗi; around advice có thể short-circuit; logger có thể bị filter hoặc async exporter chưa flush.

### 13.1 Trình tự chẩn đoán có chứng cứ

~~~text
Observed event missing
     |
     +--> Join point really executed?
     |      |
     |      +-- No: branch/short-circuit; no event expected.
     |      +-- Yes
     |           |
     |           +--> Mechanism intercepts this kind of join point?
     |                  |
     |                  +-- No: instrumentation coverage issue.
     |                  +-- Yes
     |                       |
     |                       +--> P ancestor active for this occurrence?
     |                              |
     |                              +-- No: cflow condition false.
     |                              +-- Yes
     |                                   |
     |                                   +--> cflow vs cflowbelow?
     |                                   +--> advice type/runtime filter?
     |                                   +--> logging/telemetry visible?
~~~

Đây là **sơ đồ chẩn đoán**, không phải một API hay thuật toán mặc định. Mục tiêu là không sửa pointcut trước khi biết nguyên nhân mất event.

## 14. Một số ngộ nhận mà bộ test cần bác bỏ

1. **“`cflow(P)` và `cflowbelow(P)` khác nhau ở mọi child.”** Sai: với child dưới P, cả hai thường true; khác biệt rõ ở root ngoài.
2. **“`cflowbelow(P)` loại mọi điểm cũng khớp P.”** Sai với P lồng dưới P khác.
3. **“Chỉ cần một root và một child là kiểm chứng đủ.”** Sai: chưa phủ nested/recursive P, exception và outside.
4. **“Expected lấy từ cùng matcher đang được test vẫn ổn.”** Test có thể đồng thời sai cả expected và actual.
5. **“Không có log advice nghĩa không nằm trong flow.”** Có thể là proxy bypass, wrong advice type hoặc log filter.
6. **“Một method nằm trong cùng class với P thì thuộc cflow(P).”** Dynamic flow không là lexical scope.
7. **“Call graph tĩnh có cạnh P→child nghĩa child luôn chạy.”** Chỉ khi đường gọi thực sự xảy ra.
8. **“Một `static boolean` là đủ mô phỏng P active trên toàn JVM.”** Có race và cross-thread contamination.
9. **“Root bên trong recursion phải bị bỏ khỏi below vì nó khớp P.”** Không: nó là hậu duệ của P ngoài.
10. **“Sau exception, root marker vẫn active cho request kế.”** Phải cleanup trong finally.
11. **“Task được submit bên trong P tự giữ `cflow(P)`.”** Không mặc định qua worker khác.
12. **“Truyền trace context biến worker thành con của P trong dynamic stack.”** Hai loại quan hệ khác nhau.
13. **“Proxy thấy outer thì chắc cũng thấy self-invocation inner.”** Không trong mọi mô hình delegation.
14. **“After-returning không chạy là lỗi control flow.”** Có thể là exception path.
15. **“Around advice không proceed nhưng child vẫn phải match.”** Child không có occurrence nếu body không chạy.
16. **“Cộng thời gian tất cả child luôn bằng root latency.”** Có thể double-count do nesting.
17. **“Join point cùng tên là cùng occurrence.”** Đệ quy và lặp tạo occurrence khác nhau.
18. **“Mọi công cụ AOP hỗ trợ call và execution như nhau.”** Phải kiểm tra capability thực tế.
19. **“Test chạy một lần ra đúng stdout chứng minh không có race.”** Concurrency cần test riêng.
20. **“Quan sát root đủ để khẳng định audit/security đầy đủ.”** Đường vào không qua root có thể bypass.

## 15. Checklist xây bài thực hành chất lượng

- [ ] Viết một câu ngắn mô tả **P chọn join point loại gì**.
- [ ] Viết rõ **`cflow` bao root; `cflowbelow` cần P ancestor**.
- [ ] Lập bảng expected cho root/child/outside trước khi code.
- [ ] Thêm **một P lồng/đệ quy** với expected below=true.
- [ ] Kiểm tra child sau khi inner P rời nhưng outer P còn active.
- [ ] Kiểm tra method giống nhau nhưng chạy ngoài P.
- [ ] Thêm nhánh không thực thi để khẳng định **không có event giả**.
- [ ] Thêm short-circuit để phân biệt missing join point và false pointcut.
- [ ] Thêm exception và kiểm tra cleanup bằng event sau root.
- [ ] Thêm task async và phân biệt dynamic stack với logical trace.
- [ ] Nếu dùng proxy, kiểm tra direct-call/self-invocation boundary.
- [ ] Ghi tên occurrence khác nhau cho các lần gọi cùng method.
- [ ] Ghi expected độc lập, không gọi lại matcher để tạo expected.
- [ ] So sánh đủ **event values, sequence, hit count và absence**.
- [ ] Tách **matcher problem** khỏi **instrumentation coverage**.
- [ ] Không coi missing after-returning trên exception là false cflow.
- [ ] Dùng dữ liệu giả; không log raw args, secrets hoặc principal.
- [ ] Đảm bảo Java example có source/class filename, lệnh javac/java và stdout khớp.
- [ ] Định nghĩa những semantics phụ thuộc model/weaver là **giới hạn**, không bịa bảo đảm chung.
- [ ] Đưa những ca đã phát hiện lỗi vào regression suite.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Một P ngoài cùng vừa xảy ra. Expected `cflow(P)` và `cflowbelow(P)` tại occurrence ấy là gì?

**Đáp:** cflow=true, below=false nếu không có P khác đang bao quanh.

**Câu 2.** Một method con chạy trong P. Cả hai có thể true không?

**Đáp:** có. Child nằm dưới root P active.

**Câu 3.** P gọi đệ quy chính P. Tại P trong, below có thể true không?

**Đáp:** có. P trong nằm dưới P ngoài, dù tự khớp P.

**Câu 4.** Child được gọi từ đường ngoài P nhưng cùng chữ ký với một child trong P. Có tự ở trong cflow không?

**Đáp:** không. Membership phụ thuộc đường thực thi và P active, không chỉ method signature.

**Câu 5.** Root trả về qua exception; test nào chứng minh cleanup?

**Đáp:** gọi một event ngoài sau khi catch và assert depth=0, cflow=false, below=false.

**Câu 6.** Advice thiếu log cho inner trong proxy delegation. Có thể dùng kết quả đó để khẳng định inner ở ngoài P không?

**Đáp:** không. Inner có thể nằm dưới P về call stack nhưng bypass proxy qua self-invocation; phải kiểm tra coverage.

**Câu 7.** Bằng cách nào kiểm tra P short-circuit đúng?

**Đáp:** root event có mặt, nhưng **không có child occurrence**. Không tạo child event giả.

**Câu 8.** Tại sao expected cần viết trước khi chạy matcher?

**Đáp:** để tránh test tính lại cùng một logic sai và tự xác nhận; oracle phải độc lập.

**Câu 9.** Nếu executor task chạy trên thread khác khi caller vẫn ở P, task tự thuộc cflow(P) không?

**Đáp:** không mặc định theo ngữ nghĩa dynamic stack; truyền trace context là cơ chế riêng.

**Câu 10.** Trong ví dụ Java, tại sao `P:inner` có `depth=1` nhưng `child:inside-inner` có `depth=2`?

**Đáp:** depth trong event đo **số P ancestors active trước occurrence hiện tại**. P trong đang có P ngoài là một ancestor; child bên trong có cả hai P active.

## 17. Tóm kết phương pháp

Một ví dụ kiểm chứng **phạm vi điều khiển** tốt phải trả lời được ba nhóm câu hỏi:

1. **Ngữ nghĩa:** root P nào đang active, occurrence hiện tại chính là P hay nằm dưới một P ancestor, và `cflow(P)` khác `cflowbelow(P)` ở đâu?
2. **Khả năng quan sát:** join point có thực sự xảy ra, được weaver/proxy hỗ trợ và advice phù hợp có được vào hay không?
3. **Chứng cứ:** bảng expected độc lập có đủ positive/negative/boundary cases, test có kiểm tra exception cleanup, recursion, short-circuit và async không?

**Quy tắc dễ nhớ:** thiết kế **bảng kỳ vọng trước**, dựng một fixture nhỏ có **root–child–nested P–outside**, rồi thêm những tình huống có thể **bác bỏ lời giải sai**. Một ví dụ chỉ cho thấy advice chạy trong happy path chưa đủ chứng minh control-flow scope đúng.

# Phân biệt điểm khởi đầu với các điểm nằm bên dưới luồng gọi trong AOP

Khi thiết kế **Aspect-Oriented Programming (AOP – lập trình hướng khía cạnh)** theo **luồng điều khiển động (dynamic control flow)**, đôi khi ta không chỉ muốn chọn một join point bởi tên hoặc chữ ký phương thức, mà còn muốn biết: **join point đang xảy ra có nằm trong quá trình xử lý được bắt đầu bởi một join point khác hay không?**

Một nhầm lẫn quan trọng là đánh đồng **điểm khởi đầu** với **những điểm xảy ra ở bên dưới nó**. Hai kiểu lựa chọn thường được diễn đạt bởi các khái niệm:

- **`cflow(P)` – control flow của P:** chọn join point khớp P đóng vai trò bắt đầu luồng **và** các join point xảy ra động bên trong quá trình xử lý đó.
- **`cflowbelow(P)` – control flow nằm dưới P:** chọn các join point xảy ra **bên dưới** một lần khớp P đang hoạt động, thay vì chính lần P tạo ra phạm vi ấy.

Ở trường hợp đơn giản chỉ có **một P ngoài cùng**, `cflow(P)` bao gồm P và hậu duệ động; `cflowbelow(P)` bao gồm hậu duệ nhưng không tính P ngoài cùng. Tuy nhiên, **nếu một P khác được gọi lồng nhau/đệ quy dưới P ngoài**, chính P bên trong đó vẫn có thể được `cflowbelow(P)` chọn: nó **nằm dưới lần P ngoài**, dù bản thân cũng khớp P. Vì thế không nên mô tả `cflowbelow(P)` là “loại trừ mọi join point khớp P” trong mọi tình huống.

Đây là **khái niệm AOP tổng quát** về phạm vi control-flow. Các tên cú pháp trên phổ biến trong những ngôn ngữ pointcut có khả năng chọn control flow; **không phải mọi AOP proxy/interceptor tự hỗ trợ cùng cú pháp hay tập join point**. Bài phân tích ngữ nghĩa, vận dụng, trường hợp lồng/đệ quy, khác biệt tĩnh–động, xử lý async và cung cấp ví dụ **Java 17 độc lập** để trực quan hóa các phạm vi.

## 1. Chọn điểm khởi đầu và các điểm bên dưới

Trong AOP, **join point** là sự kiện can thiệp được mô hình hỗ trợ; **pointcut** chọn join point và **advice** chạy tại điểm được chọn nếu cơ chế weaving/interception thực sự bao phủ đường gọi. Với một pointcut động theo luồng điều khiển, cần phân biệt **occurrence P mở phạm vi** với các occurrence **xảy ra bên dưới P khi P còn hoạt động**.

~~~text
Caller
  └─ P: Checkout.process()  ← gốc
       ├─ validate()         ← bên dưới P
       └─ reserve()          ← bên dưới P
Caller tiếp tục sau khi P kết thúc → ngoài phạm vi P
~~~

Hai câu hỏi chính của bài: **tại chính occurrence P** thì điều kiện có đúng không, và **tại một occurrence P lồng trong P khác** thì vì sao quan hệ “bên dưới” lại có thể đúng? Điều này phụ thuộc *dynamic invocation tree*, không phải chỉ tên method, vị trí source hoặc mối liên hệ nghiệp vụ suy đoán.

**Ranh giới quan trọng:** P có thể là method call hoặc method execution tùy công cụ, và chúng không phải cùng một join point. Trong proxy, chỉ đường đi qua proxy được quan sát; trong bytecode weaving, class/call site phải thực sự được weave. Các phần sau dùng tập hợp occurrence và ví dụ đệ quy để phân định chính xác root với descendant.

## 2. Công thức tư duy: bao gồm gốc và loại trừ gốc của cùng một phạm vi

Giả sử có một lần xảy ra join point **p** khớp P.

~~~text
                p = start of control flow P
                |
                +--> j1
                |     |
                |     +--> j2
                |
                +--> j3
~~~

Theo cách mô hình hóa một **instance control-flow** bắt đầu tại p:

~~~text
cflow_started_at(p)      = {p, j1, j2, j3}
cflowbelow_started_at(p) = {j1, j2, j3}
~~~

Đây là **ký hiệu tập hợp giải thích ý nghĩa**, không phải cú pháp của một ngôn ngữ AOP. Nó chỉ xét **một** p cụ thể. Khi P có nhiều lần xuất hiện, cần xét **hợp của những phạm vi đang hoạt động**.

Một tiêu chí ở runtime:

- `cflow(P)` đúng tại j nếu **có ít nhất một** join point p khớp P sao cho j là chính p **hoặc** nằm dưới p trong luồng điều khiển động.
- `cflowbelow(P)` đúng tại j nếu **có ít nhất một** join point p khớp P sao cho j nằm **bên dưới** p (j không phải chính p ấy).

Điểm tinh tế nằm ở từ **“có ít nhất một”**. Một j có thể chính là điểm khởi đầu của phạm vi P bên trong, đồng thời là điểm con của một P bên ngoài.

### 2.1 Ví dụ lồng nhau

~~~text
P_outer()                      <-- khớp P, bắt đầu flow ngoài
  |
  +--> helper()                <-- ở dưới P_outer
  |
  +--> P_inner()               <-- cũng khớp P
         |
         +--> nestedWork()     <-- ở dưới P_outer lẫn P_inner
~~~

Ở `P_outer`: có `cflow(P)`; chưa có `cflowbelow(P)` khi đó là root ngoài cùng.

Ở `P_inner`: có `cflow(P)` **và** `cflowbelow(P)`, vì `P_inner` nằm **dưới P_outer**. Không thể nói "mọi execution của một phương thức khớp P đều bị loại bởi `cflowbelow(P)`".

Ở `nestedWork`: cả hai điều kiện đều đúng.

### 2.2 Phân biệt điểm (join point) và một đoạn code

Một phương thức có thể được gọi nhiều lần. `P_outer` và `P_inner` trong sơ đồ có thể cùng là **một phương thức `process()` được gọi đệ quy**, nhưng là **hai lần occurrence của join point** trong runtime. Chúng có vai trò root khác nhau, tùy stack động tại thời điểm đó.

Một bảng phân loại theo **method name** cố định không thể thay thế việc xem **occurrence và active flow**.

## 3. Vì sao đây là dynamic control flow, không phải phạm vi từ vựng?

Xét mã minh họa:

~~~java
void start() {
    helper();
}

void helper() {
    perform();
}
~~~

Đây chỉ là một mảnh Java, chưa là chương trình độc lập. Khi `helper()` thực sự được gọi từ `start()`, execution của `perform()` nằm bên dưới start, nếu P chọn execution của `start()`.

Nhưng cùng `helper()` có thể được gọi từ đường khác:

~~~java
void unrelated() {
    helper();
}
~~~

Khi gọi `unrelated()` trực tiếp **không qua start**, `helper()` và `perform()` **không nằm trong cflow(P)**, dù đây là **cùng source code** và cùng method signature.

**Kết luận:** pointcut control-flow không chỉ xét method nằm trong class/package nào hoặc được viết bên trong method khác. Nó xét **đường thực thi đã xảy ra**, chứ không chỉ nhìn cấu trúc source.

### 3.1 So với lựa chọn theo phạm vi mã tĩnh

| Loại lựa chọn | Căn cứ | Có đổi theo caller runtime? |
| --- | --- | --- |
| Signature/metadata matching | Method name, owner type, annotation, modifier | Thường mang phần cấu trúc cố định |
| Lexical scope | Vị trí join point được định nghĩa trong type/code block | Cơ bản dựa trên cấu trúc source/bytecode |
| Dynamic control flow | Một P có đang active trên đường thực thi không | Có |
| Runtime argument/target tests | Tham số và object của occurrence hiện tại | Có thể có |
| Proxy boundary | Caller có thực sự gọi qua proxy được instrument không | Có thể có |

Một biểu thức P có thể là **structural pointcut**, còn phần `cflow(P)` thêm **điều kiện động**: join point hiện tại nằm trong phạm vi thực thi được khởi phát bởi P hay không.

### 3.2 Call graph tĩnh không đủ

Một sơ đồ call graph tĩnh chỉ nói `start()` **có thể** gọi `perform()`. Nhưng nếu một nhánh `if` không được đi vào, hoặc method thực tế không chạy, sẽ **không có occurrence** tương ứng để advice được áp dụng. Dynamic pointcut không tạo sự kiện cho những phương thức chưa chạy.

Một indirect call qua interface, callback đồng bộ hay dispatch đa hình vẫn có thể nằm trong cflow nếu lời gọi thực tế xảy ra **bên dưới root đang active** và mô hình AOP quan sát được join point đó.

## 4. Phân biệt method-call và method-execution tại điểm khởi đầu

Trong các mô hình có cả **method call join point** và **method execution join point**, cùng một lời gọi source có thể gắn các điểm khác nhau:

~~~text
Caller.method()
    |
    | method-call join point tại call site
    v
Target.operation()
    | method-execution join point tại target body
    v
  business implementation
~~~

Nếu P chọn **call** của `operation()`, phạm vi gốc bắt đầu tại **call join point**. Nếu P chọn **execution** của `operation()`, gốc bắt đầu tại **execution join point**.

Hai phạm vi thường chồng lên nhau trong một lời gọi đồng bộ bình thường, nhưng **không được mặc định giống nhau** trong mọi tình huống:
- Một call có thể đi qua dispatch khác hoặc ném lỗi trước execution target.
- Một method-execution có thể xảy ra từ call site không được mô hình/công cụ chọn.
- Proxy interception thường quan sát **lời gọi qua ranh giới proxy**, không phải toàn bộ method execution trên mọi đường.
- Dynamic bytecode weaving có thể có khả năng điểm nối khác với một wrapper thủ công.

**Cần ghi cụ thể P chọn loại join point nào.** Nói “cflow của hàm `checkout`” mà không nói call hay execution có thể khiến test hiểu sai ngay tại ranh giới gốc.

### 4.1 Nếu P chọn nhiều phương thức

Ví dụ P chọn `execute` và `retry`. Khi `retry` chạy bên trong `execute`, một occurrence khớp P có thể nằm dưới occurrence P khác. Khi ấy **chính occurrence `retry`** có thể khớp `cflowbelow(P)`.

Muốn "chỉ loại gốc khởi đầu ở mức ngoài cùng", phải định nghĩa rõ **outermost root** theo hợp đồng của bài toán; đừng mặc định `cflowbelow(P)` sẽ loại mọi occurrence match P.

## 5. Ví dụ Java 17 hoàn chỉnh: gốc, hậu duệ và root đệ quy

Chương trình sau dùng Java 17 thuần, **không dùng bộ weaver**. Nó đặt một `ThreadLocal<Integer>` làm bộ đếm số root P **đang active trên thread hiện tại**, tăng khi bắt đầu một root và giảm/khôi phục trong `finally`.

Ta mô phỏng hai nhóm điểm:
- **Root event**: execution occurrence của `root(...)`, giả định khớp P. Tại root, `cflow(P)=true`. `cflowbelow(P)` chỉ true nếu đã có root P **bên ngoài**.
- **Other event**: execution occurrence của `leaf(...)`, không khớp P. Nếu đang có ít nhất một root active, cả `cflow(P)` lẫn `cflowbelow(P)` đều true.

Chương trình còn dùng executor một thread để minh họa **`ThreadLocal` của caller không tự chuyển sang một worker thread khác**. Theo ý nghĩa **dynamic call stack**, một task được queue sang worker cũng **không còn tự là hậu duệ cùng call stack** chỉ vì được lên lịch khi root đang hoạt động.

Lưu toàn bộ thành `ControlFlowEntryDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ControlFlowEntryDemo {
    // Số lần execution khớp P đang bao quanh đường gọi trên thread.
    private static final ThreadLocal<Integer> ROOT_DEPTH =
            ThreadLocal.withInitial(() -> 0);

    static String inspect(String name, boolean isRootP) {
        int depth = ROOT_DEPTH.get();

        boolean inCflow = depth > 0;
        boolean inCflowBelow =
                isRootP ? depth > 1 : depth > 0;

        return name
                + " depth=" + depth
                + " cflow=" + inCflow
                + " cflowbelow=" + inCflowBelow;
    }

    static void leaf(String name) {
        System.out.println(inspect("leaf:" + name, false));
    }

    static void root(
            String name,
            boolean callNestedRoot,
            ExecutorService executor)
            throws Exception {
        int previous = ROOT_DEPTH.get();
        ROOT_DEPTH.set(previous + 1);

        try {
            // Đây là occurrence của root execution được mô phỏng.
            System.out.println(inspect("root:" + name, true));
            leaf(name + "-a");

            if (callNestedRoot) {
                root("inner", false, executor);
            }

            if ("outer".equals(name)) {
                // Worker khác không có ROOT_DEPTH của caller.
                Future<String> async = executor.submit(
                        () -> inspect("async-worker", false));
                System.out.println(async.get());
            }

            leaf(name + "-b");
        } finally {
            // Đóng đúng phạm vi: không phá root bên ngoài.
            if (previous == 0) {
                ROOT_DEPTH.remove();
            } else {
                ROOT_DEPTH.set(previous);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println(inspect("outside-before", false));

        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        try {
            root("outer", true, executor);
        } finally {
            executor.shutdown();
        }

        System.out.println(inspect("outside-after", false));
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac ControlFlowEntryDemo.java
java ControlFlowEntryDemo
~~~

Stdout dự kiến và có thứ tự xác định:

~~~text
outside-before depth=0 cflow=false cflowbelow=false
root:outer depth=1 cflow=true cflowbelow=false
leaf:outer-a depth=1 cflow=true cflowbelow=true
root:inner depth=2 cflow=true cflowbelow=true
leaf:inner-a depth=2 cflow=true cflowbelow=true
leaf:inner-b depth=2 cflow=true cflowbelow=true
async-worker depth=0 cflow=false cflowbelow=false
leaf:outer-b depth=1 cflow=true cflowbelow=true
outside-after depth=0 cflow=false cflowbelow=false
~~~

### 5.1 Vì sao `root:outer` không ở below?

Ở root đầu tiên, `ROOT_DEPTH=1`. Chính occurrence `root:outer` là **điểm khởi đầu của phạm vi đang xét**, không có P khác trên stack ngoài nó. `cflow(P)` true vì bao gồm root; `cflowbelow(P)` false vì chưa có **root P ở phía trên**.

### 5.2 Vì sao `leaf:outer-a` ở dưới P?

`leaf` không phải root P; nhưng khi nó được gọi, root ngoài còn active (`depth=1`). Nó là **hậu duệ động**, nên cả `cflow(P)` và `cflowbelow(P)` đều true.

### 5.3 Vì sao `root:inner` vẫn là `cflowbelow(P)`?

Đây là tình huống quan trọng nhất. Khi `root("inner")` được gọi trong `root("outer")`, **hai occurrence của P đang lồng nhau** và `depth=2`. `root:inner`:
- Là chính P **mới**, nên tự khởi đầu một phạm vi `cflow(P)`.
- Đồng thời **nằm bên dưới P ngoài**, nên khớp `cflowbelow(P)` nếu xem quan hệ với P ngoài.

Suy ra: `cflowbelow(P)` không có nghĩa "mọi method cũng khớp P đều không được chọn". Nó có nghĩa "bên dưới **một occurrence P đang hoạt động**"; cùng một join point có thể là root trong và là hậu duệ của root ngoài.

### 5.4 Vì sao `async-worker` không ở dưới P?

`executor.submit(...)` diễn ra khi `root:outer` vẫn active **trên caller thread**, nhưng callable chạy **trên thread pool worker khác**. `ThreadLocal` của caller không tự chuyển sang worker, và **dynamic call stack** của worker không chứa execution occurrence P của caller.

Điều này **không ngăn** ta chủ động truyền một `traceId` hoặc logical operation context sang task. Nhưng **propagate logical trace** và **đúng là hậu duệ trong dynamic call stack** là hai khái niệm khác nhau. Không nên giả định `cflow(P)` tự áp dụng trên mọi executor task nếu mô hình không định nghĩa cách mở rộng phạm vi qua async boundary.

### 5.5 Vì sao có `finally`?

Phạm vi root phải chấm dứt khi execution root trả về **hoặc ném ngoại lệ**. `finally` giúp:
- Giảm độ sâu khi root lồng nhau kết thúc.
- Khôi phục độ sâu root ngoài nếu còn.
- `remove()` nếu không còn root active, tránh ThreadLocal tồn tại trên thread pool lâu hơn cần thiết.

**Giới hạn:** đây là một **mô hình theo dõi control-flow tự xây**, không phải hiện thực đầy đủ của mọi `cflow/cflowbelow` pointcut. Một hệ thống weaving có thể theo dõi occurrence, bindings và loại join point phức tạp hơn; ở đây `isRootP` được truyền tường minh để minh họa điều kiện.

## 6. Phân biệt cflow và cflowbelow bằng biểu thức pointcut khái niệm

Giả sử P chọn execution của một entrypoint:

~~~text
P = execution of Checkout.process(..)

Select cflow(P):
    entrypoint execution itself
    AND every observable join point dynamically inside it

Select cflowbelow(P):
    join points dynamically underneath an active P
    excluding the particular P occurrence that starts that scope
~~~

Đây là **giả mã diễn đạt**, không phải cú pháp dùng chung cho mọi bộ AOP. Với cùng lời gọi:

~~~text
Checkout.process()     <-- cflow yes, cflowbelow no (nếu root ngoài)
  Inventory.check()    <-- cflow yes, cflowbelow yes
  Checkout.process()   <-- cflow yes, cflowbelow yes (P lồng dưới P ngoài)
~~~

### 6.1 Khi dùng `cflow(P)`

Chọn `cflow(P)` khi concern **cần áp dụng cả ở chính root và những join point dưới nó**, theo khả năng của mô hình. Ví dụ:
- Tạo một phạm vi quan sát bao gồm cả entrypoint.
- Áp dụng một chính sách logging/metrics cho mọi join point thuộc thao tác logic khởi đầu từ P.
- Phân loại các sự kiện bên trong một hoạt động được bắt đầu tại root P.

Nhưng khi advice được áp dụng **tại P** và lại gọi helper cũng thuộc pointcut, cần cân nhắc **đệ quy instrumentation** và chi phí quan sát. Không phải cứ chọn `cflow(P)` là đủ cho bảo mật: một lời gọi trực tiếp nằm ngoài phạm vi P vẫn có thể tồn tại.

### 6.2 Khi dùng `cflowbelow(P)`

Chọn `cflowbelow(P)` khi concern **chỉ có ý nghĩa với hoạt động con sau khi một entrypoint đã được bắt đầu**, ví dụ:
- Đo số lượng internal method executions bên dưới một use case, nhưng không tính execution entrypoint ấy như một "internal call".
- Chỉ áp dụng diagnostic logging cho các bước bên trong một thao tác lớn.
- Phân biệt root latency với latency của các thành phần con.

**Đặt câu hỏi về P lồng nhau:** nếu P có thể tự gọi lại hoặc nhiều P occurrences xuất hiện trong một flow, inner P có thể được tính như một điểm nằm bên dưới. Nếu yêu cầu phải loại tất cả inner P theo signature, cần **thêm một điều kiện exclude phù hợp** hoặc thiết kế guard/outermost matching riêng theo hợp đồng; đừng đổi nghĩa của `cflowbelow(P)`.

## 7. Control flow và pointcut binding

Một số mô hình AOP cho phép P **ràng buộc giá trị** (binding) từ join point khởi đầu để advice ở bên dưới dùng, chẳng hạn một request ID hoặc tham số đã được kiểm tra.

Giả mã:

~~~text
P(requestId) = execution of Checkout.process(requestId)

for join points in cflow(P(requestId)):
    emit safeEvent(operation, requestId)
~~~

Điều cần xác định:
1. Giá trị đến từ **root occurrence nào** khi có nhiều P lồng nhau?
2. Có dùng giá trị root gần nhất, root ngoài cùng hay một collection of contexts?
3. Nếu có nhiều root phù hợp, cách xử lý binding của nền tảng là gì?
4. Giá trị có được phép mang tới advice khác về bảo mật và retention không?
5. Với tham số mutable, có cần snapshot để không bị thay sau lúc root bắt đầu?
6. Khi root kết thúc, binding được dọn đúng không?

**Không tự bịa** một quy tắc binding chung: một ngôn ngữ AOP cụ thể sẽ có semantics riêng về `cflow`, tham số và precedence khi nhiều pointcut match.

### 7.1 Root gần nhất và root ngoài cùng khác nhau

~~~text
P(tenant A)
  helper()
  P(tenant B)
    charge()
~~~

Một advice ở `charge()` có thể nằm dưới **cả hai** P occurrences. Nếu chỉ có một trường `currentTenant`, phải quy định nó mang tenant A hay B, và quyền thực tế phải được xác minh như thế nào.

Một **stack of scoped contexts** có thể phù hợp cho một instrumentation tự viết, nhưng security không thể chỉ dựa vào chuỗi tenant được binding từ một method không đáng tin. Với authorization, source xác thực và principal phải được xử lý độc lập.

## 8. Ứng dụng thường gặp

### 8.1 Tracing: root span và child spans

Trong trace một thao tác:
- **Root span** thường được tạo tại entrypoint.
- **Child span** tạo cho các bước nội bộ.
- Một điểm **bên dưới root** có thể là vị trí hợp lý để tạo child span, tránh tạo thêm root-level span trên cùng một entrypoint.

Điều quan trọng: tracing logical operation **có thể kéo dài qua async và remote boundary**, trong khi dynamic call-stack `cflow` theo nghĩa chặt có thể không. Đừng đồng nhất cấu trúc parent/child spans với stack frame thực của một thread.

### 8.2 Audit cho use case

Một thao tác có thể phát sự kiện:
- START ở entrypoint.
- ACTION cho các bước quan trọng bên dưới.
- SUCCESS/ERROR khi root kết thúc.

Nếu audit bắt buộc ghi denied requests ngay tại entrypoint, chỉ dùng `cflowbelow(P)` có thể **bỏ qua chính root** và những lần bị từ chối trước khi có hoạt động con. Cần thiết kế việc ghi nhận ở đúng ranh giới, với event schema an toàn.

### 8.3 Performance profiling

Nếu đo `cflow(P)` và ghi metric cho mọi method, có thể **đếm cả root và các phương thức con**. Tổng thời gian các method có thể lớn hơn wall-clock của request do lồng nhau; không cộng mù quáng mà coi là request latency.

Nếu muốn số method nội bộ, `cflowbelow(P)` có thể giúp loại root ngoài cùng trong trường hợp không có P lồng. Nếu P đệ quy, phải quyết định có tính nested root như một internal method hay không.

### 8.4 Validation và phân quyền

Một chính sách validation có thể chỉ cần áp dụng tại entrypoint. Một chính sách quyền có thể cần áp dụng cả ở các thao tác con độc lập, kể cả khi chúng được gọi ngoài flow P. Sử dụng `cflow(P)` như **điều kiện duy nhất** cho authorization thường có nguy cơ để lọt đường gọi không bắt đầu từ P.

Hãy xác định những **invariants bắt buộc** trước rồi mới dùng dynamic pointcut để tối ưu hóa observability hoặc chọn những hoạt động liên quan.

## 9. Ngữ nghĩa với before, after, around và ngoại lệ

### 9.1 Before advice

Nếu before advice chọn `cflow(P)`, nó có thể chạy ở occurrence root P và cả các join point khác trong control flow, tùy pointcut được ghép thêm.

Nếu chọn `cflowbelow(P)`, nó có thể chỉ chạy tại các điểm bên dưới một P active. Với P lồng, một occurrence P bên trong cũng có thể được chọn.

### 9.2 After-returning, after-throwing và finally

Một advice kiểu **after-returning** không chạy tại một join point kết thúc bằng ngoại lệ, kể cả join point đó nằm trong `cflow(P)`. **After-throwing** chỉ liên quan khi join point kết thúc bằng throw phù hợp; **finally-like advice** phục vụ cleanup theo scope nó đã vào.

Vì vậy, "không thấy after" không chứng minh `cflowbelow(P)` false. Có thể join point đúng nhưng **nhánh điều khiển** đi qua exception.

### 9.3 Around advice có thể short-circuit

Một around advice ở root P có thể **không gọi continuation**:
- Target/root body không chạy.
- Không phát sinh các join point con dự kiến.
- Advice chọn các điểm bên dưới không có cơ hội được thực thi.

Đây không phải lỗi lựa chọn `cflowbelow(P)`, mà là **control flow thực tế không đi qua chúng**.

Nếu quanh root gọi continuation nhiều lần (một số mô hình cho phép), nhiều tập join point con có thể xuất hiện theo từng attempt. Metric đếm các điểm con phải phân biệt **request**, **attempt** và **execution**.

### 9.4 Cleanup khi root ném lỗi

Một cơ chế tracking root tự cài bằng stack/depth cần cleanup trong `finally`. Nếu không, exception có thể để marker `P active` trên thread pool; invocation không liên quan sau đó bị nhận nhầm nằm trong `cflow(P)`.

Nếu dùng phương tiện weaving có sẵn, hãy xác minh lifecycle của control-flow state theo hợp đồng. Nếu viết wrapper/handler riêng, test exception path và nested restoration là bắt buộc.

## 10. Đệ quy, nested roots và nhiều P đồng thời

### 10.1 Root đệ quy

~~~text
P(n=2)
  |
  +--> P(n=1)
         |
         +--> P(n=0)
~~~

Khi vào `P(n=2)` ngoài cùng: không có P tổ tiên, nên `cflowbelow(P)` false tại occurrence này.

Khi vào `P(n=1)`: có P ngoài, nên `cflowbelow(P)` true **tại chính occurrence P(n=1)**.

Khi vào `P(n=0)`: tương tự, vì nằm dưới hai P occurrences.

Một **boolean `inP`** tự tạo có thể cho biết có P đang active, nhưng không đủ nếu bài toán cần phân biệt **độ sâu/root gần nhất/outermost root**. Một depth counter hoặc stack context có thể tốt hơn.

### 10.2 Hai lần P độc lập theo thời gian

~~~text
P request A enters -> leaves
P request B enters -> leaves
~~~

Khi request A đã rời, `cflow(P)` của A không tiếp tục áp dụng cho request B. Không có "vùng P vĩnh viễn" chỉ vì method từng chạy.

### 10.3 Hai thread độc lập

~~~text
Thread T1: P(A) -> child(A)
Thread T2: independentTask(B)
~~~

Dynamic call stack của T2 không tự chứa P(A) của T1. Không dùng một field `static boolean inP` để theo dõi cflow cho cả process: nó có thể làm T2 bị đánh dấu sai và gây race. Một cơ chế AOP có cflow state phải bảo vệ **phạm vi thực thi**; ThreadLocal depth chỉ là một minh họa đơn giản cho synchronous per-thread stack.

### 10.4 Nếu P khớp nhiều join point khác nhau

Một P có thể chọn nhiều entrypoints, ví dụ `checkout` và `refund`. Khi `checkout` gọi `refund`, `refund` là **root thứ hai** bên trong root thứ nhất. Điều kiện `cflowbelow(P)` tại `refund` có thể true vì có P `checkout` ở phía ngoài.

Nếu yêu cầu chỉ áp dụng khi **đúng loại** root gọi con, cần giữ thông tin lựa chọn root cụ thể, kết hợp thêm pointcut về operation hoặc dùng policy scope rõ.

## 11. Async, executor và control flow logic

Một lời gọi có thể tạo tác vụ async:

~~~text
Thread T1:
  P() --------------------- returns
    |
    +-- executor.submit(task)

Thread T2:
  task.run() ---------------------------- completes
~~~

Nếu P là **method execution** ở T1, P kết thúc trước khi task ở T2 chạy cũng có thể xảy ra. Task không nằm trong dynamic call stack của P theo nghĩa truyền thống, dù nó bắt nguồn **về mặt nghiệp vụ** từ P.

Do đó phân biệt:
- **Dynamic call-flow scope:** mối quan hệ trong quá trình thực thi/lời gọi đang active, như `cflow(P)`.
- **Logical operation context:** trace/correlation/cancellation context có thể được truyền có chủ đích qua async task hoặc network.
- **Causal relationship:** task được scheduling do P, nhưng không nhất thiết còn nằm trong runtime stack của P.

**Không coi propagation trace ID là cách “làm cho cflow trở thành true”** trừ khi một cơ chế cụ thể có semantics mở rộng như vậy. Một AOP pointcut về dynamic cflow và một distributed tracing context phục vụ hai mục tiêu khác nhau.

### 11.1 Nếu cần truyền context qua task

Cách làm ở cấp khái niệm:
1. Capture một snapshot **tối thiểu, đã được phép** ở submission boundary.
2. Bọc task để activate snapshot khi execution trên worker.
3. Restore/remove context trong `finally`, kể cả khi lỗi.
4. Theo dõi completion, cancellation và timeout.
5. Không dùng trace ID như bằng chứng xác thực quyền.
6. Không mang mutable request object hoặc thread-bound transaction resource tùy tiện qua executor.

Đây là thiết kế **logical context propagation**; không nên mô tả nó là AOP `cflowbelow` tự xuất hiện trên một thread khác.

### 11.2 Callback đồng bộ khác callback async

Một callback được gọi trực tiếp trên **cùng call stack** khi P còn active có thể nằm trong control flow của P. Một callback được gửi vào queue rồi chạy về sau ở worker khác có thể không nằm trong stack đó. Cùng một callback implementation không quyết định membership; **thời điểm và đường thực thi** mới quyết định.

## 12. Những giới hạn khi dùng AOP qua proxy

Proxy-based AOP thường chặn những lời gọi thực sự đi **qua proxy**. Trong mô hình delegation:

~~~text
Client -> Proxy.root() -> Target.root()
                              |
                              +--> this.child()
~~~

Lời gọi `this.child()` trên target có thể **bypass proxy**. Nếu child không được instrument ở một join point khác, advice gắn vào child qua proxy không chạy; dù child đang thực thi động bên trong root nghiệp vụ, hệ thống proxy vẫn có thể **không tạo được join point được advice nhìn thấy tại child**.

Vì vậy cần tách hai điều kiện:
1. **Ngữ nghĩa control flow:** child thật sự có xảy ra bên trong một root P active không?
2. **Khả năng quan sát của mô hình AOP:** child có phải join point mà cơ chế weaving/proxy này intercept được không?

Nếu một hệ thống chỉ cung cấp proxy interceptor cho entrypoints, nó có thể không hỗ trợ pointcut `cflow/cflowbelow` với cùng mức chi tiết như một bộ dệt method-execution. Không được suy từ cú pháp khái niệm rằng mọi private/static/constructor call đều được chọn.

### 12.1 Call và execution dưới cùng root

Ở một pointcut call, caller-side context và object `this` có thể khác target. Ở execution join point của instance method, `this` thường liên quan đối tượng đang chạy method. Đừng dùng tên `this`, `target` hay `args` của một InvocationHandler để khẳng định đồng nhất với mọi pointcut cflow.

### 12.2 Instrumentation của advice helper

Một advice có thể gọi helper cũng nằm trong tập join point thuộc cflow P. Nếu điểm helper bị instrument:
- Số lần advice có thể tăng ngoài dự kiến.
- Logger có thể tự gọi lại logging advice.
- Tracing/metrics có thể sinh thêm sự kiện do chính việc ghi log.

Nên dùng pointcut phạm vi hẹp và các exclude được phép cho helper/infrastructure; đồng thời không bỏ qua những policy bảo mật bắt buộc chỉ để giảm chi phí.

## 13. Hiệu năng và chi phí runtime của control-flow selection

Pointcut chỉ chọn method signature có thể được xác định phần lớn ở compile/weaving time; một điều kiện **dynamic cflow** phải xem xét trạng thái runtime để biết root còn active không.

Tùy công cụ, có thể dùng:
- Counter theo thread/flow.
- Stack context.
- Runtime test ở join point ứng viên.
- Instrumentation tại entry và exit của P.
- Một cơ chế tương đương khác.

**Không giả định một thuật toán hoặc chi phí cụ thể cho mọi weaver.** Nhưng về nguyên tắc, việc kiểm tra cflow có thể thêm overhead tại cả root và các join point được xét, nhất là nếu P/pointcut chọn quá rộng.

### 13.1 Giảm chi phí bằng selection rõ

- Chọn P là **entrypoint có ý nghĩa**, không phải mọi method.
- Chỉ xét cflow ở những **join point ứng viên** cần quan sát.
- Tránh advice logging sâu trên toàn bộ thư viện nền.
- Phân biệt root metrics và child metrics thay vì phát event cho mỗi helper nhỏ.
- Không thu thập raw arguments/return values chỉ để xác định flow.
- Đo chi phí thật trong workload thực tế, kể cả recursion và exception paths.

### 13.2 Không lạm dụng marker toàn cục

Một flag dùng chung kiểu `static boolean inCheckout` có thể:
- Bị request khác ghi đè.
- Bật sai trên thread khác.
- Không về false nếu có lỗi.
- Không biểu diễn root lồng nhau.
- Nhầm P A với P B.

Thread-local depth/stack cho synchronous flow là một mô hình an toàn hơn flag toàn cục ở nhiều tình huống, nhưng vẫn cần cleanup và không giải quyết async tự động.

## 14. Ma trận tình huống cần kiểm thử

| Tình huống | `cflow(P)` | `cflowbelow(P)` | Điểm cần xác nhận |
| --- | --- | --- | --- |
| Root P ngoài cùng vừa bắt đầu | Có | Không | Không có P tổ tiên |
| Method con trực tiếp của P | Có | Có | Child thực sự chạy bên trong P |
| Method con nhiều tầng | Có | Có | P vẫn active |
| P lồng/đệ quy dưới P khác | Có | Có | Inner P ở dưới outer P |
| Method con bên trong inner P | Có | Có | Có một hoặc nhiều root tổ tiên |
| Sibling method sau khi P return | Không | Không | Root đã kết thúc |
| Cùng method con nhưng gọi ngoài P | Không | Không | Static signature không đủ |
| P kết thúc do exception | Không tại những điểm về sau | Không | Cleanup scope đúng |
| P short-circuit trước khi gọi child | Tại P có thể có | Không có child occurrence | Đừng tạo event cho code chưa chạy |
| Callback đồng bộ dưới P | Có thể có | Có thể có | Cần join point được instrument |
| Async task trên worker khác | Không tự động | Không tự động | Dynamic stack khác logical context |
| P ở T1, công việc độc lập ở T2 | Không ở T2 | Không ở T2 | Không dùng global flag |
| Direct call bypass proxy | Tùy join point được hỗ trợ | Tùy | Proxy không thấy mọi execution |
| Instrumented helper trong P | Có thể có | Có thể có | Cẩn thận reentrancy/overhead |

**Bảng mô tả ngữ nghĩa ở những join point có thể quan sát được** trong một mô hình có hỗ trợ control-flow selection. Không kết luận rằng mọi công cụ AOP đều instrument tất cả các tình huống ấy.

## 15. Phương pháp chẩn đoán khi advice chọn sai

Khi lời gọi root/child không kích hoạt như mong muốn:

1. **Xác định P:** chọn call hay execution? Chữ ký và overload có đúng không?
2. **Xác định root occurrence:** đây là P ngoài cùng hay P lồng?
3. **Xác định đường thực thi:** child có thực sự xảy ra trong thời gian P còn active không?
4. **Xác định khả năng instrument:** mô hình hiện tại chặn được join point của child không?
5. **Phân biệt cflow/cflowbelow:** đang kỳ vọng advice tại root hay chỉ các điểm dưới root?
6. **Xem precedence:** around advice ngoài có short-circuit hoặc không proceed không?
7. **Xem exception:** after-returning có bị bỏ do error path không?
8. **Xem concurrency:** flow đang ở thread nào? Có dùng global flag sai không?
9. **Xem async:** đã chuyển sang worker khác chưa? Có đang nhầm logical trace với cflow không?
10. **Xem logging:** advice có chạy nhưng sink/sampling không ghi sự kiện không?
11. **Kiểm tra root cleanup:** một exception có để marker active sai tới request sau không?
12. **Kiểm thử nested roots:** inner P có được tính là below outer P đúng không?

Một cách debug an toàn là ghi **event schema tối thiểu**, ví dụ:

~~~text
joinPoint=Checkout.process
matchesP=true
activeRootDepth=1
insideCflow=true
belowActiveRoot=false
~~~

Không tự ghi token, password, full args, target object hoặc exception message tùy ý vào log. Đặc biệt khi root/child hoạt động trên nhiều tenant, việc debug không được kéo theo rò dữ liệu của request khác.

## 16. Các lỗi hiểu sai phổ biến

1. **“`cflow(P)` chỉ là P.”** Sai: nó còn bao gồm những điểm xảy ra trong control flow được P khởi đầu.
2. **“`cflowbelow(P)` luôn loại mọi occurrence match P.”** Sai khi P lồng dưới P khác.
3. **“`cflowbelow(P)` và `cflow(P)` luôn đồng nghĩa.”** Root ngoài cùng phân biệt hai điều kiện.
4. **“Một method nằm trong cùng package nên ở dưới P.”** Không: dynamic scope không phải lexical scope.
5. **“Static call graph có cạnh A→B nghĩa B luôn nằm trong cflow(A).”** Không: chỉ khi đường gọi thực tế diễn ra.
6. **“Root P chạy hôm trước khiến các lời gọi sau mãi ở trong P.”** Không: scope kết thúc khi occurrence P rời.
7. **“Hai thread khác nhau cùng dùng một `static boolean` để mô phỏng cflow an toàn.”** Không: dễ cross-request race.
8. **“Task được submit trong P đương nhiên ở trong cflow(P) khi chạy sau.”** Không tự động trên worker khác.
9. **“Truyền trace ID bằng ThreadLocal làm `cflow` tự true.”** Trace context và dynamic call stack khác nhau.
10. **“Pointcut trên proxy thấy mọi self-invocation.”** Không trong mọi mô hình proxy.
11. **“Khi child không được instrument, cflowbelow phải sai.”** Cần phân biệt scope thực và cơ hội quan sát join point.
12. **“After-returning không thấy log nghĩa pointcut không khớp.”** Có thể target đã ném lỗi.
13. **“Around không proceed vẫn tạo các điểm con giả định.”** Không: không có child occurrence nếu phần đó chưa được thực thi.
14. **“Đếm mọi method trong cflow luôn bằng số lời gọi nghiệp vụ.”** Có helper, nested roots, retry và callback.
15. **“Đếm thời gian của tất cả child rồi cộng sẽ ra root wall-clock.”** Có thể double count do nesting.
16. **“Một boolean depth đủ cho root lồng nhau.”** Không nếu cần số tầng/outermost binding.
17. **“Có cùng method name thì là cùng join point occurrence.”** Occurrences khác nhau theo runtime.
18. **“Mọi AOP framework/proxy đều có cflow với cùng semantics.”** Cần kiểm tra khả năng cụ thể.
19. **“Có thể dùng cflow như hàng rào bảo mật duy nhất.”** Đường vào ngoài root có thể bypass.
20. **“Vì cflow là runtime nên không cần quan tâm loại pointcut P.”** Call vs execution vẫn làm khác ranh giới gốc.

## 17. Checklist vận dụng

- [ ] Định nghĩa root P bằng **một loại join point cụ thể**.
- [ ] Chọn `cflow(P)` nếu phải xét cả root và hậu duệ.
- [ ] Chọn `cflowbelow(P)` nếu mục tiêu là các điểm nằm dưới một P active.
- [ ] Viết test cho **root ngoài cùng** và **inner P occurrence**.
- [ ] Ghi rõ root lồng/đệ quy có được tính là “internal” không.
- [ ] Phân biệt dynamic cflow với lexical scope và static call graph.
- [ ] Kiểm tra advice có làm short-circuit hoặc retry continuation không.
- [ ] Kiểm thử before, after-success, after-error và finally theo đúng ngữ nghĩa.
- [ ] Nếu tự tracking depth, restore đúng trong `finally` và khi nested.
- [ ] Không dùng một mutable flag global để biểu thị P đang active.
- [ ] Xác minh ranh giới thread và executor; không gộp logical trace với cflow.
- [ ] Kiểm tra coverage thực tế của proxy/weaver cho các child join point.
- [ ] Cẩn thận pointcut chọn cả helper của advice gây recursion.
- [ ] Đo overhead khi root kéo dài hoặc pointcut bao phủ quá rộng.
- [ ] Tối thiểu hóa dữ liệu log và context bindings.
- [ ] Không đặt security invariant bắt buộc chỉ trên một đường gọi dễ bypass.
- [ ] Dùng regression tests cho đồng bộ, nested recursion, error và async.

## 18. Bài tập tự kiểm tra

**Bài 1.** P chọn execution `checkout()`; gọi `checkout()` rồi `inventory()` bên trong. `cflow(P)` có chọn execution checkout ngoài không?

**Đáp:** có. Nó bao gồm điểm khởi đầu P và các điểm bên dưới theo ngữ nghĩa dynamic cflow.

**Bài 2.** Trên occurrence checkout ngoài cùng ấy, `cflowbelow(P)` có đúng không nếu không còn P nào đang bao quanh?

**Đáp:** không. Chính occurrence đó là điểm khởi đầu ngoài cùng, không nằm dưới P khác.

**Bài 3.** `checkout()` gọi đệ quy `checkout()`. Occurrence bên trong có thể khớp `cflowbelow(P)` không?

**Đáp:** có, vì nó nằm dưới occurrence P ngoài. Không nên diễn giải `cflowbelow(P)` là loại mọi root theo signature.

**Bài 4.** `inventory()` cũng được gọi từ `profile()` khi không có checkout trên stack. Invocation ấy có thuộc `cflow(P)` không?

**Đáp:** không chỉ vì trùng method name; phải có P active trên đường thực thi liên quan.

**Bài 5.** Checkout submit task sang executor; worker chạy task sau khi checkout trả về. Task mặc nhiên ở trong dynamic cflow của checkout không?

**Đáp:** không. Đường stack đã tách; nếu cần logical context phải có propagation được thiết kế, và nó không tự đồng nghĩa cflow.

**Bài 6.** Around advice ở root từ chối và không gọi continuation, tại sao child advice không chạy?

**Đáp:** vì các child join point không hề xảy ra. Không thể chọn một điểm không được thực thi.

**Bài 7.** AOP qua proxy chặn `Checkout.process`, bên trong target gọi `this.validate()`. Tại sao validate advice có thể không chạy?

**Đáp:** trong mô hình delegation, self-invocation có thể bypass proxy. Cần phân biệt membership của flow với khả năng instrument child.

**Bài 8.** Nếu chỉ muốn đếm method thực thi bên dưới root nhưng không tính root ngoài cùng, lựa chọn nào phù hợp khi không có P lồng?

**Đáp:** `cflowbelow(P)`, có thể kết hợp selector của nhóm method cần đếm để tránh helper ngoài ý định.

**Bài 9.** Một exception làm root kết thúc. Vì sao phải cleanup tracking depth bằng `finally`?

**Đáp:** để không giữ trạng thái P active sai cho các invocation sau, nhất là trên thread pool.

**Bài 10.** Tại sao một inner P có thể vừa là “root” vừa là “below”?

**Đáp:** vì root/below là **quan hệ giữa những occurrence**. Inner P mở phạm vi riêng đồng thời là hậu duệ của outer P.

## 19. Kết luận

Khi áp dụng **control-flow pointcuts** trong AOP, phải xác định **điểm P nào bắt đầu một phạm vi động**, rồi mới quyết định có chọn **chính điểm khởi đầu** hay **chỉ các join point xảy ra bên dưới**.

- `cflow(P)` bao gồm root occurrence P và các điểm nằm trong control flow ấy.
- `cflowbelow(P)` chọn các điểm nằm bên dưới **một** P active, thường loại root ngoài cùng nhưng **vẫn có thể chọn P lồng/đệ quy**.
- Dynamic control flow khác lexical scope, static call graph, logical tracing context và phạm vi được proxy instrument.
- Điều kiện dùng được còn phụ thuộc đường gọi thực, nested roots, loại join point P, exception, short-circuit và ranh giới async.
- Bài toán nghiệp vụ cần kiểm thử **root/child, nested P, outside flow, error và async**, không chỉ một nhánh thành công.

**Ghi nhớ:** “điểm khởi đầu” và “điểm ở dưới” là **vai trò tương đối của những join point occurrences trên đường thực thi**, không phải nhãn cố định của một method hoặc class.

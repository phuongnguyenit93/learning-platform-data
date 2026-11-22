# Pointcut theo luồng điều khiển và phạm vi lời gọi động trong Aspect/AOP

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming — AOP**), **pointcut** chọn những **join point** nơi **advice** được áp dụng. Một điều kiện pointcut theo tên phương thức hoặc package mang tính **tĩnh**: cùng một phương thức vẫn có thể khớp bất kể nó được gọi từ đâu. Nhưng nhiều yêu cầu lại phụ thuộc **đường gọi đang diễn ra**. Ví dụ, chỉ đo việc truy cập dữ liệu **khi một lượt checkout còn đang thực thi**, chứ không đo cùng thao tác khi được chạy bởi một công việc bảo trì độc lập.

Đó là **pointcut theo luồng điều khiển động** (*dynamic control-flow pointcut*): nó chọn điểm không chỉ vì kiểu/chữ ký mà còn vì **đang có một điểm gốc được chọn nằm trên chuỗi lời gọi runtime**. Trong những ngôn ngữ AOP hỗ trợ, hai khái niệm quen thuộc là **`cflow(P)`** và **`cflowbelow(P)`**, với P là pointcut chọn **root join point**.

- `cflow(P)` thường bao gồm chính join point root P và những join point trong phạm vi thực thi động bên dưới root.
- `cflowbelow(P)` thường chọn phần **bên dưới** root P, không tính chính điểm đang mở root đó.
- Trong **nested roots**, một root P bên trong vẫn có thể thuộc `cflowbelow(P)` của **root P bên ngoài**. Không được suy rằng `cflowbelow` luôn loại mọi phương thức có tên root.
- Một pointcut theo flow chỉ là **điều kiện chọn điểm**: nó **không tự tạo một aspect instance cho từng flow**. Chính sách vòng đời kiểu `percflow`, nếu công nghệ hỗ trợ, là khái niệm khác.

**Giới hạn ngữ nghĩa:** dynamic call flow đồng bộ khác lexical scope, trạng thái per-thread, logical HTTP request và một correlation ID được truyền qua executor. Khả năng chọn method call, method execution, field access, constructor hay các điểm khác phụ thuộc **mô hình AOP và công cụ**.

Bài này chỉ bàn **Aspect/AOP cơ bản và nâng cao nói chung**. Ví dụ cú pháp AspectJ được ghi rõ là đặc thù ngôn ngữ đó, không phải mã biên dịch bằng `javac`; ví dụ Java 17 hoàn chỉnh phía dưới **mô phỏng** cflow để học mà không cần một AOP weaver.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể giải thích phạm vi động khác phạm vi tĩnh; xác định điểm root/child nào khớp `cflow` hoặc `cflowbelow`; phân tích nested/recursive call và ngoại lệ; ghép điều kiện flow với join point chính xác; phân biệt binding, per-flow instance và ThreadLocal; nhận ra giới hạn proxy, weaving và async; đo hiệu năng; thiết kế kiểm thử cả đường được chọn lẫn đường không được chọn.

## 2. Những thuật ngữ quan trọng

| Khái niệm | Vai trò |
| --- | --- |
| **Join point** | Điểm trong chương trình mà mô hình AOP cho phép can thiệp |
| **Pointcut** | Biểu thức hoặc luật chọn những join point |
| **Advice** | Hành vi bổ sung chạy trước, sau, quanh điểm được chọn |
| **Aspect** | Đơn vị đóng gói pointcut, advice và đôi khi có state |
| **Root pointcut P** | Chọn những điểm mở dynamic flow cần theo dõi |
| **Dynamic scope** | Thời gian root còn hiện diện trên đường thực thi |
| **Weaving/composition** | Kết hợp chính sách với chương trình theo cơ chế compiler, bytecode, proxy... |
| **`cflow(P)`** | Quan hệ membership: đang trong flow của một P |
| **`cflowbelow(P)`** | Membership trong phần dưới một P, loại chính root tương ứng |
| **Binding** | Lấy dữ liệu từ join point/root/context vào advice nếu công nghệ hỗ trợ |
| **Instantiation policy** | Quy định bao nhiêu instance aspect; khác pointcut membership |

Pointcut có thể gồm phần tĩnh `execution(Repository.save(..))` và điều kiện động `cflow(checkoutRoot)`. **Phần tĩnh hỏi “điểm nào?”; phần động hỏi “ở trong đường thực thi nào?”**.

## 3. Đường gọi động khác vị trí khai báo tĩnh

```text
Đường A:
main -> Checkout.checkout() -> Repository.reserve()
                              [in checkout flow]

Đường B:
main -> MaintenanceJob.run() -> Repository.reserve()
                               [outside checkout flow]
```

Ở cả A và B, mã `Repository.reserve` có thể là cùng một phương thức, cùng package và cùng chữ ký. Bộ lọc tĩnh theo tên/package có thể chọn cả hai, nhưng điều kiện `cflow(checkoutRoot)` thường **chỉ đúng ở A** khi root còn hoạt động.

Điểm này khác hoàn toàn với “phương thức repository nằm trong package checkout”. Một utility trong package khác vẫn có thể ở trong flow khi được checkout gọi. Ngược lại, mã trong package checkout có thể chạy ngoài flow do được gọi độc lập.

Các điều kiện như `within` và `withincode` trong một số ngôn ngữ AOP thể hiện ranh giới **tĩnh/lexical**; chúng không tự phát biểu quan hệ một root đang tồn tại trên call stack.

### 3.1. Cùng tên nhưng overload khác

```java
void checkout(String orderId);
void checkout(String orderId, boolean dryRun);
```

Đây là chữ ký minh họa, không phải chương trình độc lập. Một root pointcut chỉ chọn `checkout(String)` không tự tạo flow khi bản overload thứ hai được thực thi. Nếu sử dụng wildcard chọn mọi overload, phải đánh giá **đó có đúng yêu cầu nghiệp vụ không**.

### 3.2. Root có thể là nhiều phương thức

P có thể chọn nhiều join point của nhiều lớp. Nếu chương trình đang thực thi root P1 rồi lại gọi root P2 mà cả hai thỏa P, **hai activation P có thể đồng thời hoạt động**. Đây là lý do một biến `boolean inRoot` không đủ để biểu diễn toàn bộ quan hệ.

## 4. Hiểu `cflow(P)` qua entry và exit

```text
Checkout.checkout() entered   <-- Root P begins
  Validation.check()          <-- inside cflow(P)
  Repository.reserve()        <-- inside cflow(P)
  Notification.prepare()      <-- inside cflow(P)
Checkout.checkout() returns   <-- Root P ends

Repository.reserve()          <-- outside cflow(P)
```

Khi root được vào theo **loại join point P đã định nghĩa**, những điểm thực thi bên dưới nó có thể được xét theo flow. Root kết thúc khi execution/call tương ứng rời phạm vi, dù return bình thường hay unwinding vì exception.

**Không phải “đã có checkout trong 5 giây gần đây”.** Một lời gọi repository ở thời điểm sau khi checkout đã kết thúc không còn thuộc dynamic call stack ấy.

Nếu root trả về `CompletableFuture` chưa hoàn tất, execution đồng bộ của root có thể đã kết thúc trong khi công việc async vẫn chạy. Không tự suy `cflow` phải tồn tại tới khi future hoàn tất.

### 4.1. Ngoại lệ

Một root có thể ném lỗi. Khi phương thức rời call stack vì lỗi, flow của activation đó không còn hoạt động trên đường thực thi sau đó. Cơ chế manual muốn mô phỏng phải dọn state trong `finally` sau khi mở thành công scope.

Nếu chỉ tắt cờ trong nhánh after-returning, flow có thể rò vào lượt gọi khác khi exception xảy ra.

### 4.2. Root lồng nhau và recursion

```text
checkout(outer)         Root P1
   -> checkout(inner)   Root P2 (inside P1)
       -> reserve()     Inside P1 and P2
   -> reserve()         Still inside P1, P2 ended
```

Trong recursion, P1/P2 thậm chí có thể là các execution của **cùng một phương thức** ở những depth khác nhau. Flow không chỉ là tên method, mà gồm **những lần kích hoạt khác nhau**.

## 5. `cflow` khác `cflowbelow` ở đâu?

Với **một root không lồng**:

| Join point đang xét | `cflow(P)` | `cflowbelow(P)` |
| --- | --- | --- |
| Chính root P | Có | Không |
| Child method trong root | Có | Có |
| Child sâu nhiều tầng | Có | Có |
| Cùng method child ngoài root | Không | Không |
| Phương thức khác sau root return | Không | Không |

Tuy nhiên, ở **nested roots**:

```text
P(outer)
   -> P(inner)
      -> child()
```

Tại **execution của P(inner)**, điểm này là root của inner, nhưng nó **nằm bên dưới outer**. Do vậy nó có thể thỏa `cflowbelow(P)` vì **root outer** đang hoạt động. Đây là một ngoại lệ quan trọng với diễn giải quá đơn giản “cflowbelow luôn bỏ qua mọi execution có tên P”.

Với child bên trong inner, cả outer và inner là các activation đang hoạt động, và child nằm dưới cả hai. Nhưng Boolean membership **không có nghĩa advice bắt buộc chạy hai lần**. Số lượt dispatch và instance còn phụ thuộc join point/advice/instantiation của công cụ.

### 5.1. Biên root tùy loại join point

Nếu P chọn **method call**, root là thao tác lời gọi ở phía caller. Nếu P chọn **method execution**, root là sự kiện thực thi thân phương thức đích. Không đồng nhất hai ranh giới ấy khi xét điều kiện ở đúng chính điểm root.

Cần xác nhận loại join point, lớp nào đã được weave và pointcut/around advice nào có thể chặn lời gọi trước khi root thực sự bắt đầu.

## 6. Kết hợp bộ lọc tĩnh với điều kiện flow

Một yêu cầu cụ thể: “Chỉ log việc `Inventory.reserve` khi checkout đang chạy.”

Mô hình:

```text
execution of Inventory.reserve(...)
AND
cflow(execution of Checkout.checkout(...))
```

Đây là **giả mã**, không phải Java chuẩn. Phần `execution` chọn **điểm con cần đo**, `cflow` xác nhận bối cảnh runtime của nó. Nếu chỉ dùng `cflow(checkout)` không kèm bộ lọc con, số điểm phù hợp có thể rộng hơn mong muốn.

Các phép AND, OR, NOT hoặc pointcut có tên có thể giúp đọc và tái sử dụng điều kiện, tùy ngôn ngữ AOP. Cần đặt ngoặc rõ để tránh thay nghĩa giữa biểu thức “A AND (B OR C)” và “(A AND B) OR C”.

### 6.1. Loại bỏ hạ tầng advice

Nếu advice ghi log nhưng logger lại gọi phương thức nằm trong pointcut, nó có thể gây **reentrancy** và log đệ quy. Nên chọn điểm hẹp và loại những package/method hạ tầng có thể tự kích hoạt advice, khi được công nghệ hỗ trợ.

Không giả định `cflow` tự bảo vệ bạn khỏi advice tự gọi lại root/child.

### 6.2. Chọn đúng overload, annotation và access

Một pointcut theo tên `reserve` có thể chọn nhiều overload; một điều kiện annotation có thể chỉ chọn những phương thức thật sự mang metadata tương ứng; một `private` hoặc field access có thể không phải join point của cơ chế proxy đang dùng. Tất cả phải được kiểm tra theo **join point model**.

## 7. Cú pháp AspectJ minh họa — không phải Java `javac` tiêu chuẩn

Ví dụ **riêng cho ngôn ngữ AspectJ** (cần AOP-aware compiler/weaver và các lớp đích phù hợp):

```java
package demo;

public aspect CheckoutFlowAspect {
    pointcut checkoutRoot():
        execution(* demo.CheckoutService.checkout(..));

    pointcut reservation():
        execution(* demo.InventoryRepository.reserve(..));

    before(): reservation() && cflow(checkoutRoot()) {
        System.out.println("reserve inside checkout");
    }
}
```

Ý nghĩa: advice `before` được chọn tại `reserve` khi một execution `checkout` phù hợp đang nằm trong dynamic flow. Lời gọi `reserve` từ một job độc lập không thỏa điều kiện flow. Cú pháp `..` là ký hiệu của pointcut language, không phải danh sách tham số Java trong mọi chỗ.

Ví dụ thay điều kiện bằng `cflowbelow(checkoutRoot())`:

```java
package demo;

public aspect CheckoutBelowAspect {
    pointcut root():
        execution(* demo.CheckoutService.checkout(..));

    before(): execution(* demo.InventoryRepository.reserve(..))
              && cflowbelow(root()) {
        System.out.println("reserve below checkout");
    }
}
```

Vì `reserve` là join point bên dưới `checkout`, cả hai ví dụ có thể cho kết quả tương tự ở trường hợp đơn giản. Muốn nhìn khác biệt, test thêm **chính root** và **nested root**. Hai đoạn trên không có `main`, không tự chạy bằng lệnh `javac` của ví dụ bên dưới.

**Không có bảo đảm chung** rằng mọi hệ AOP chấp nhận cú pháp trên hoặc hỗ trợ đủ field/constructor/method call join points. Dùng những đoạn này để học cách diễn đạt, không sao chép nguyên vào một công nghệ khác mà không kiểm tra.

## 8. Lọc theo flow không đồng nghĩa tạo aspect instance theo flow

Giả sử một singleton aspect có field `int total` và advice của nó chỉ chạy khi `cflow(P)`. Hai lượt root khác nhau vẫn có thể cập nhật **cùng một `total`**: `cflow` chỉ lọc việc chạy advice.

Một cơ chế **per-control-flow aspect instantiation** như `percflow(P)` trong những mô hình hỗ trợ có thể tạo/khôi phục instance riêng theo mỗi root activation. Đây là **vòng đời object**, không phải chỉ Boolean membership.

| Cần đạt | Cơ chế phù hợp để cân nhắc |
| --- | --- |
| Advice chỉ kích hoạt khi root còn hoạt động | `cflow(P)` |
| Chỉ áp tại các điểm bên dưới root | `cflowbelow(P)` |
| Một counter độc lập cho mỗi root | Per-flow instance hoặc scope được quản lý riêng |
| Một tổng counter cho tất cả root | Shared counter thread-safe |
| Giá trị chỉ sống trong một lần around advice | Biến cục bộ theo invocation |
| Context qua nhiều thread cho logical request | Explicit propagation/lifecycle, không chỉ cflow đồng bộ |

Nếu một root bên ngoài gọi root bên trong, có thể có nhiều instance theo activation. Cơ chế xác định **instance nào được advice sử dụng** phụ thuộc ngôn ngữ/công cụ, đặc biệt khi có binding theo flow; không suy chỉ từ tên `cflow`.

## 9. Binding đối số và dữ liệu ngữ cảnh

Một chính sách muốn biết **order ID của checkout root** ngay khi `reserve` chạy. Khái niệm cần tách:

- **Đối số của join point hiện tại**: ví dụ các tham số truyền vào `reserve`.
- **Đối số của root**: ví dụ `orderId` của `checkout` làm bắt đầu flow.
- **Target/this**: ngữ cảnh đối tượng ở join point đang xét.
- **Flow membership**: có một root phù hợp đang hoạt động không.
- **Flow instance state**: state được một instantiation policy quản lý nếu công nghệ hỗ trợ.

Không mặc định các đối số của `reserve` giống `checkout`. Với nested checkout, cũng không thể tự khẳng định một phép binding luôn trả **root ngoài cùng** hoặc **root gần nhất** khi chưa xem semantics của công nghệ.

Nếu cần lưu giá trị root trong scope thủ công, nên giữ dữ liệu **nhỏ, bất biến**, có thời hạn, thay vì giữ nguyên request/session/payload lớn. Lời gọi có exception phải dọn scope đúng; lời gọi trong thread pool không được dùng dữ liệu stale.

## 10. Java 17 runnable: mô hình root, cflowbelow, nested flow và async

**Đây là chương trình Java 17 thuần mô phỏng membership**, không phải compiler AOP hoặc ví dụ native `cflow` tự động. Nó dùng `ThreadLocal<Deque<String>>` để lưu các root được **mở tường minh** bởi `enterRoot`, giúp nhìn rõ khác biệt giữa root hiện tại và root cha. Thao tác `leaf` mô phỏng một join point con.

Tạo file `DynamicFlowPointcutDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class DynamicFlowPointcutDemo {
    private static final ThreadLocal<Deque<String>> ROOTS =
            new ThreadLocal<>();

    static List<String> names(Deque<String> stack) {
        if (stack == null || stack.isEmpty()) {
            return List.of();
        }
        ArrayList<String> result = new ArrayList<>(stack);
        Collections.reverse(result);
        return result;
    }

    static List<String> belowNewRoot(Deque<String> stack) {
        ArrayList<String> result = new ArrayList<>(stack);
        result.remove(0); // Root mới chưa nằm dưới chính nó.
        Collections.reverse(result);
        return result;
    }

    static void leaf(String name) {
        List<String> active = names(ROOTS.get());
        System.out.println("LEAF " + name
                + " cflow=" + active + " below=" + active);
    }

    static <T> T enterRoot(String name, Callable<T> body)
            throws Exception {
        Deque<String> stack = ROOTS.get();
        if (stack == null) {
            stack = new ArrayDeque<>();
            ROOTS.set(stack);
        }

        stack.push(name);
        System.out.println("ENTER " + name + " depth=" + stack.size());
        System.out.println("ROOT " + name
                + " cflow=" + names(stack)
                + " below=" + belowNewRoot(stack));

        try {
            return body.call();
        } finally {
            String removed = stack.pop();
            if (!removed.equals(name)) {
                throw new IllegalStateException("flow stack corrupted");
            }
            if (stack.isEmpty()) {
                ROOTS.remove();
            }
            System.out.println("EXIT " + name + " depth=" + stack.size());
        }
    }

    public static void main(String[] args) throws Exception {
        leaf("outside");

        enterRoot("outer", () -> {
            leaf("A");
            enterRoot("inner", () -> {
                leaf("B");
                return null;
            });
            leaf("C");
            return null;
        });

        try {
            enterRoot("error", () -> {
                leaf("throw-path");
                throw new IllegalArgumentException("stop");
            });
        } catch (IllegalArgumentException error) {
            System.out.println("CAUGHT " + error.getMessage());
        }
        leaf("after-error");

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            enterRoot("parent", () -> {
                Future<?> one = pool.submit(
                        () -> leaf("async-default"));
                one.get();

                Future<?> two = pool.submit(() -> {
                    try {
                        enterRoot("child-async", () -> {
                            leaf("async-explicit");
                            return null;
                        });
                    } catch (Exception error) {
                        throw new RuntimeException(error);
                    }
                });
                two.get();

                leaf("after-task");
                return null;
            });
        } finally {
            pool.shutdown();
        }

        System.out.println("END");
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 DynamicFlowPointcutDemo.java
java DynamicFlowPointcutDemo
```

Stdout dự kiến chính xác:

```text
LEAF outside cflow=[] below=[]
ENTER outer depth=1
ROOT outer cflow=[outer] below=[]
LEAF A cflow=[outer] below=[outer]
ENTER inner depth=2
ROOT inner cflow=[outer, inner] below=[outer]
LEAF B cflow=[outer, inner] below=[outer, inner]
EXIT inner depth=1
LEAF C cflow=[outer] below=[outer]
EXIT outer depth=0
ENTER error depth=1
ROOT error cflow=[error] below=[]
LEAF throw-path cflow=[error] below=[error]
EXIT error depth=0
CAUGHT stop
LEAF after-error cflow=[] below=[]
ENTER parent depth=1
ROOT parent cflow=[parent] below=[]
LEAF async-default cflow=[] below=[]
ENTER child-async depth=1
ROOT child-async cflow=[child-async] below=[]
LEAF async-explicit cflow=[child-async] below=[child-async]
EXIT child-async depth=0
LEAF after-task cflow=[parent] below=[parent]
EXIT parent depth=0
END
```

### 10.1. Root outer: vì sao below trống?

`outer` vừa bắt đầu, nên nó thuộc `cflow` của chính mình. Nhưng root không “nằm dưới chính nó”; không có root cha nên `below=[]`. Điểm `leaf A` được gọi sau khi vào outer nên ở dưới outer: hai danh sách đều chứa `outer`.

### 10.2. Root inner: điểm kiểm tra dễ nhầm

`ROOT inner cflow=[outer, inner] below=[outer]` có nghĩa **inner là root của flow inner** nhưng vẫn **nằm dưới flow outer**. `leaf B` ở bên dưới cả hai root. Sau inner kết thúc, `leaf C` lại chỉ có outer; đó là tính chất khôi phục outer scope.

### 10.3. Khi root ném ngoại lệ

`enterRoot("error")` có `finally`. Dù body ném lỗi, nó pop root rồi `ROOTS.remove()` nếu stack rỗng. Sau đó caller catch `stop`, và `leaf after-error` không còn flow. Không cần chờ GC để kiểm chứng logic này.

### 10.4. Thread khác và explicit child root

`ExecutorService` chạy `async-default` trên worker với ThreadLocal riêng, nên nó in `cflow=[]` dù parent trên thread gọi vẫn đang hoạt động. Task thứ hai tự mở root **mới** `child-async` trên worker. Root đó **không phải phần mở rộng tự động của call stack parent**. `Future.get()` giúp thứ tự stdout xác định.

### 10.5. Giới hạn mô hình

Mô hình dùng `enterRoot()` tường minh và `leaf()` thủ công; nó không weave các method execution/call join points. `ThreadLocal` hỗ trợ dữ liệu per-thread đồng bộ nhưng không tự xác định pointcut, không đảm bảo lifetime của logical request xuyên async và không bảo đảm dữ liệu được truyền sang executor. Trạng thái stack không được truy cập đồng thời từ nhiều thread trong ví dụ.

## 11. Đệ quy và số lượng root activation

Khi `checkout(3)` gọi `checkout(2)`, rồi `checkout(1)`, ba execution P có thể đang hoạt động. Một điểm con dưới mức 1 có thể nằm trong flow của cả ba.

Đó không có nghĩa một `before` advice với điều kiện `cflow(P)` chắc chắn chạy **ba lần** tại cùng một join point. Membership Boolean là **có root phù hợp hay không**. Số lần chạy advice, việc áp vào bao nhiêu instance và precedence do công nghệ quy định.

Một cài đặt thủ công chỉ dùng Boolean:

```text
enter P: inFlow = true
exit P:  inFlow = false
```

sẽ sai khi inner thoát còn outer đang hoạt động. Nếu chỉ cần biết membership, counter depth với `try/finally` có thể đủ; nếu cần tên/đối số/state của từng root, một stack activation phù hợp hơn.

## 12. Giới hạn với proxy, weaving và self-invocation

**JDK dynamic proxy** thường chỉ chặn lời gọi đi qua **đối tượng proxy** và những phương thức của giao diện được đại diện. Một target gọi `this.inner()` có thể bypass interception của inner. Caller có tham chiếu target gốc và gọi trực tiếp cũng có thể bỏ qua proxy.

Điều này **khác** với việc một phương thức tự nó nằm trong dynamic call stack của root. Một helper ở cùng thread có thể đọc context thủ công nhưng không có advice riêng nếu cơ chế proxy không chặn nó.

Một weaver có thể chọn execution join point ở bytecode của target hoặc call join point ở phía caller, tùy loại điểm hỗ trợ và lớp đã weave. Nếu chỉ xử lý code của target, không mặc định đã xử lý mọi call-site ở các caller bên ngoài.

Ba câu hỏi kiểm chứng riêng:

1. Lời gọi có thuộc **flow P** theo đường thực thi không?
2. Join point cần can thiệp có được **cơ chế AOP áp dụng** thật không?
3. Dữ liệu/instance aspect theo flow có được **tạo và dọn đúng** không?

Có cho câu thứ nhất **không tự chứng minh** hai câu còn lại.

## 13. `ThreadLocal`, thread pool và asynchronous propagation

Một worker pool thường tái sử dụng thread. Nếu code thủ công đặt `ThreadLocal` khi vào root nhưng quên `remove()`, tác vụ sau có thể đọc flow/context **stale** từ tác vụ trước. Đây là lỗi dữ liệu và nguy cơ giữ bộ nhớ, nhất là khi state tham chiếu tới request/session/payload.

Không đồng nhất `ThreadLocal` với native `cflow`. Nếu tự quản lý một scope per-call:

```text
previous = currentContext
install(newContext)
try:
    executeTask()
finally:
    restore(previous) or remove()
```

Với nested scope, phải **khôi phục parent**, không remove toàn bộ state của outer. Nếu task trên thread khác, nên capture những metadata tối thiểu, bất biến (ví dụ correlation ID) lúc submit và cài một scope mới trên worker lúc chạy; sau đó restore/cleanup.

`InheritableThreadLocal` có thể kế thừa giá trị ở **thời điểm tạo thread**, không tạo propagation per-submit tự động cho thread pool. Một callback/future có thể hoàn tất sau khi method root đồng bộ đã trả về. Copy một ID **không đồng nghĩa native `cflow` kéo dài qua thread**.

Nếu cần “toàn bộ logical checkout kể cả tác vụ async”, phải định nghĩa lifecycle và propagation riêng, không suy từ stack quan hệ đồng bộ.

## 14. Thứ tự aspect và luồng điều khiển

Vị trí của flow-root advice so với Cache, Authorization, Retry có thể thay đổi phạm vi quan sát:

```text
FlowScope(Retry(Target))    -- một flow có thể bao nhiều attempts
Retry(FlowScope(Target))    -- có thể có flow riêng mỗi attempt
```

Trong mô hình around advice, `proceed` có thể chạy phần còn lại của chain. Nếu Cache trả sớm **trước** điểm mở root, flow chưa hình thành. Nếu root được mở bên ngoài Cache, một logical call vẫn có thể có flow dù target không được thực thi.

Với retry, điều quan trọng là **mỗi attempt thực sự đi lại qua join point root hay không**. Các cơ chế AOP có thể khác nhau về khả năng gọi `proceed` nhiều lần.

Cần phân biệt các loại chỉ số:

- **Logical requests**: bao nhiêu yêu cầu được tiếp nhận;
- **Attempts**: bao nhiêu lần thử gọi target;
- **Target executions**: thực sự có bao nhiêu execution;
- **Effects committed**: nghiệp vụ tạo bao nhiêu tác dụng phụ;
- **Advice invocations**: lời gọi advice khớp bao nhiêu lần.

Pointcut theo flow không tự gộp tất cả thành một đại lượng.

## 15. Tối ưu hiệu năng và độ phủ

`cflow` là điều kiện phụ thuộc runtime; công cụ có thể tối ưu phần tĩnh rồi kiểm tra trạng thái flow tại những điểm còn lại. Không mặc định mọi weaver đều dùng stack trace ở mỗi join point.

Một chính sách tốt cần:

- Root pointcut hẹp, đúng chữ ký và overload;
- Bộ lọc join point con chính xác, ví dụ chỉ `Repository.reserve`;
- Không vô tình chọn logging/trace infrastructure mà advice sẽ gọi lại;
- Thử cả match và non-match path;
- Kiểm tra nested/recursive calls và exception cleanup;
- Benchmark trên hot path cùng logging/serialization thực tế;
- Xác minh toolchain đã weave đúng classes/artifact.

Nếu `cflow(P)` đứng một mình và chọn quá nhiều điểm, chi phí có thể lớn hơn yêu cầu. Nếu root bị bỏ sót do config/overload/không đi qua proxy, advice có thể **không chạy** dù người phát triển tưởng đã bảo vệ toàn bộ thao tác.

**Lưu ý bảo mật:** một guard chỉ chạy dưới `cflow(checkout)` sẽ không bảo vệ một đường độc lập gọi tới effect ngoài checkout. Chính sách bảo mật bắt buộc cần ranh giới đáng tin và test mọi đường bypass; không dùng cflow làm bảo đảm quyền truy cập duy nhất.

## 16. Ma trận kiểm thử

| Trường hợp | Điều phải kiểm chứng |
| --- | --- |
| Điểm con đúng chữ ký trong root | Điều kiện `cflow` khớp |
| Cùng điểm con ngoài root | Không khớp |
| Chính root P không lồng | `cflow` khớp, `cflowbelow` không |
| Điểm con nhiều tầng dưới P | Hai điều kiện flow khớp theo semantics |
| Root P bên trong root P khác | Root trong có thể thỏa below của root ngoài |
| Recursion P nhiều mức | Depth/activation đúng, không nhân số advice vô cớ |
| Root return bình thường | Scope của root kết thúc |
| Root throw | Scope được dọn, lỗi gốc được giữ |
| Overload P khác | Khớp/không khớp đúng chữ ký |
| Method call vs execution | Đúng join point kind và mã được weave |
| Advice tự gọi code khớp pointcut | Không đệ quy hoặc áp thừa ngoài ý muốn |
| Proxy self-invocation/direct target | Đường bypass được hiểu và kiểm soát |
| Thread A submit worker B | Không mặc định B có call flow từ A |
| Thread pool tái sử dụng | Không còn state stale |
| Singleton aspect dùng cflow | Không tự tuyên bố instance độc lập mỗi root |
| Per-flow instantiation nếu hỗ trợ | State theo root được tách và cleanup đúng |
| Artifact đã weave | Kiểm thử trên output triển khai thật |
| Advice quan sát | Giữ nguyên return/exception và số hiệu ứng |

Ngoài test đúng pointcut, cần test **tác động nghiệp vụ**: một around advice có thể gọi tiếp nhiều lần, đổi ngoại lệ hoặc trả fallback, khiến số lần effect không còn như mong đợi.

## 17. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi lexical package scope là dynamic call flow | Chọn nhầm các đường gọi | Dùng điều kiện đúng về root đang hoạt động |
| Coi `cflowbelow` là luôn loại mọi execution P | Bỏ qua root lồng nhau | Xét outer activation |
| Dùng Boolean global `inFlow` | Sai khi thread khác/nested root | Depth/scope có ownership |
| Chỉ cleanup ở after-returning | Rò flow sau exception | `finally` và nested restore |
| Coi `cflow` tự tạo state per-request | State singleton bị chia sẻ | Per-flow policy hoặc scoped state |
| Coi ThreadLocal là request scope | Worker pool giữ giá trị cũ | Scope per-task, `remove`/restore |
| Truyền correlation ID rồi nói đã kéo dài cflow | Suy sai ngữ nghĩa call stack | Propagation/lifecycle riêng |
| Đặt root pointcut quá rộng | Tăng overhead, áp advice thừa | Thu hẹp loại/chữ ký root |
| Không lọc điểm con | Có thể chọn nhiều join point ngoài ý định | Ghép `execution`/bộ lọc tương ứng |
| Nhầm method call với execution | Weaving sai phía caller/target | Kiểm tra join point model |
| Tin proxy xử lý self-invocation | Thiếu advice trên đường nội bộ | Xác minh đường gọi và reference |
| Cho rằng cflow bảo vệ mọi effect | Đường ngoài root bypass guard | Bảo vệ ranh giới đáng tin |

## 18. Bài tập và đáp án

**Bài 1.** `Repository.load` chạy từ checkout A và một maintenance job B. Pointcut là `execution(load) AND cflow(execution(checkout))`. Lượt nào khớp?

**Đáp án:** A khớp khi checkout root còn hoạt động và các điểm được weaver hỗ trợ; B không vì không có root checkout trong đường gọi.

**Bài 2.** Chính root P không lồng đang chạy. So sánh `cflow(P)` và `cflowbelow(P)`.

**Đáp án:** `cflow` thường gồm root; `cflowbelow` thường loại chính root ấy.

**Bài 3.** `P(outer) -> P(inner) -> child`. Tại execution P(inner), `cflowbelow(P)` có thể đúng không?

**Đáp án:** Có, bởi P(inner) nằm bên dưới root P(outer), dù không nằm dưới chính mình.

**Bài 4.** Ba lời gọi P đệ quy đang hoạt động. Advice `before(): child && cflow(P)` phải chạy ba lần trên một execution child không?

**Đáp án:** Không suy như vậy. Có nhiều root activation không tự đồng nghĩa nhiều lần advice dispatch tại cùng join point.

**Bài 5.** Một singleton aspect có `int counter` và advice chỉ chạy trong `cflow(P)`. Nó có tự đếm riêng cho từng root không?

**Đáp án:** Không. Điều kiện flow không tạo instance riêng. Cần instantiation/state theo scope nếu muốn dữ liệu tách biệt.

**Bài 6.** Worker B thực thi task submit từ root trên thread A. Có tự nằm trong `cflow(P)` đồng bộ của A không?

**Đáp án:** Không. Task trên B có call stack riêng. Truyền một trace ID không tự mở rộng pointcut cflow.

**Bài 7.** Target `this.inner()` từ phương thức ngoài đang được proxy chặn. Có chắc advice riêng ở inner chạy không?

**Đáp án:** Không. Self-invocation qua target có thể bypass proxy; đó là vấn đề coverage khác với membership động trong call stack.

**Bài 8.** Cần đo chỉ `Repository.save` trong flow checkout, nên dùng mỗi `cflow(checkout)` hay thêm bộ lọc execution của save?

**Đáp án:** Ghép cả hai. Điều kiện flow một mình có thể chọn nhiều điểm hơn mục tiêu, làm tăng overhead.

**Bài 9.** Root kết thúc do exception, context thủ công chỉ dọn ở after-returning. Nguy cơ gì?

**Đáp án:** State stale có thể tồn tại sau lỗi và rò sang lần gọi khác. Dọn trong finally và xử lý nested scopes.

**Bài 10.** Muốn chặn mọi tác dụng phụ của một phương thức nhạy cảm, có thể dùng duy nhất guard trong `cflow(checkout)` không?

**Đáp án:** Không nếu còn đường gọi effect ngoài checkout. Kiểm soát phải nằm ở ranh giới đáng tin, được xác minh bằng test độ phủ.

## 19. Tóm tắt

- **Pointcut theo dynamic control flow** phụ thuộc root đang hoạt động trên call stack; nó không chỉ chọn theo vị trí mã nguồn.
- **`cflow(P)`** thường bao gồm root và các điểm con; **`cflowbelow(P)`** chọn phần bên dưới một root, nhưng **nested P** có thể nằm dưới P ngoài.
- Ghép điều kiện flow với bộ lọc join point **chính xác**; phân biệt method call và method execution.
- **Lọc theo flow khác tạo aspect instance per-flow**; binding dữ liệu, lifecycle và context propagation là những hợp đồng riêng.
- **Nested/recursive flows** cần quản lý depth/stack và cleanup trên cả return/throw.
- **Executor, thread pool, async** không tự tiếp nối call stack đồng bộ; ThreadLocal không phải request scope và propagation ID không phải native cflow.
- Test dương, âm, nested, ngoại lệ, bypass và woven artifact; không dựa vào cflow như guard bảo mật duy nhất.

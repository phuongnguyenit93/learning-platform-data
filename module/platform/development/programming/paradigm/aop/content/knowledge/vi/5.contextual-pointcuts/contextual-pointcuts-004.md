# Chọn theo luồng điều khiển của một lời gọi

## 1. Bài toán: cùng một phương thức nhưng khác ngữ cảnh gọi

Một **pointcut** trong lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP) chọn những **join point** mà một hành vi cắt ngang cần áp dụng. Nhiều pointcut cơ bản chọn theo thông tin tĩnh: tên và chữ ký phương thức, kiểu khai báo, mức truy cập hoặc annotation. Tuy nhiên, đôi khi yêu cầu không nằm ở **phương thức nào**, mà là **phương thức đó được gọi trong luồng xử lý nào**.

Ví dụ, ứng dụng có thao tác `reserve()` để giữ tồn kho. Phương thức này có thể chạy ở hai tình huống:

- Được gọi **bên trong một lần xử lý `checkout()`** để hoàn tất đơn hàng.
- Được gọi **trực tiếp** từ một luồng nghiệp vụ khác, không liên quan đến thanh toán.

Nếu một chính sách ghi sự kiện chỉ muốn quan sát thao tác giữ kho thuộc quá trình thanh toán, pointcut chọn mọi `reserve()` theo tên sẽ quá rộng. Ta muốn diễn đạt:

> “Chọn join point `reserve()` **khi nó đang nằm trong luồng điều khiển động của một lời gọi `checkout()` đã được chọn**.”

Đây là ý tưởng của **pointcut theo luồng điều khiển (control-flow pointcut)**. Một nhóm khái niệm phổ biến là `cflow(P)` và `cflowbelow(P)`, trong đó `P` là pointcut xác định **điểm bắt đầu** của phạm vi quan sát. Không phải mọi công cụ AOP đều hỗ trợ các toán tử hay cú pháp này; trong bài, chúng được dùng để giải thích *ngữ nghĩa* trước khi xét giới hạn triển khai.

## 2. “Luồng điều khiển” là gì?

**Luồng điều khiển động** là những gì đang thực sự chạy theo chuỗi gọi và quay về tại thời điểm hiện tại. Nếu `checkout()` gọi `reserve()`, rồi `reserve()` gọi `audit()`, thì trong lúc `audit()` được thực thi đồng bộ, cả `checkout()` và `reserve()` vẫn đang hoạt động phía ngoài.

~~~text
Caller
  |
  v
checkout()             <- điểm bắt đầu P
  |
  +--> reserve()
  |      |
  |      +--> audit("reserve")
  |
  +--> audit("checkout")
  |
  v
return
~~~

Một lần gọi `audit()` khác từ bên ngoài `checkout()` có thể đi tới **cùng một phương thức**, nhưng không nằm trong luồng điều khiển này.

Cần phân biệt:

| Đặc điểm | Khớp tĩnh theo chữ ký | Khớp động theo luồng điều khiển |
| --- | --- | --- |
| Câu hỏi chính | “Đây là phương thức/điểm nào?” | “Điểm này đang chạy bên trong chuỗi gọi nào?” |
| Dữ liệu quyết định | Kiểu, tên, modifier, annotation, v.v. | Trạng thái ngăn xếp gọi và điểm bắt đầu đang hoạt động |
| Hai lần gọi cùng phương thức | Thường có cùng kết quả khi xét điều kiện tĩnh | Có thể một lần khớp, lần còn lại không |
| Thời điểm đánh giá | Có thể xác định trước ở nhiều trường hợp | Phụ thuộc đường thực thi tại runtime |
| Chi phí | Có thể tối ưu nhiều thông tin tĩnh | Có thể cần theo dõi hoạt động của luồng thực thi |
| Mục đích | Chọn nhóm API, lớp và vai trò kỹ thuật | Chọn hành vi khi đang ở trong một tiến trình nghiệp vụ cụ thể |

Không nên hiểu “luồng điều khiển” như **luồng dữ liệu** hoặc “đồ thị nơi một phương thức *có khả năng* gọi tới phương thức khác”. Đồ thị lời gọi tĩnh cho biết khả năng; cflow quan tâm **lời gọi nào đang diễn ra thật** tại đúng thời điểm join point xuất hiện.

## 3. Ngữ nghĩa của `cflow(P)`

Cho `P` là pointcut chọn những join point đóng vai trò **điểm gốc** của luồng cần theo dõi. Trong mô hình AOP có hỗ trợ khái niệm này:

**`cflow(P)` chọn các join point diễn ra trong luồng điều khiển của join point khớp `P`, bao gồm chính điểm khớp `P`.**

Điều đó có nghĩa:

1. Khi chưa có join point nào khớp `P` đang hoạt động, một join point bên ngoài không được chọn chỉ vì cùng tên với một lời gọi trong tương lai.
2. Khi vào join point gốc khớp `P`, gốc đó **nằm trong `cflow(P)`**.
3. Trong khi gốc chưa kết thúc, các join point xảy ra bên dưới theo luồng gọi đồng bộ có thể thuộc `cflow(P)`.
4. Khi gốc kết thúc bình thường hoặc rời đi vì ngoại lệ, phạm vi của lần kích hoạt ấy kết thúc; các join point về sau không còn thuộc phạm vi ấy, trừ khi có một gốc khác đang hoạt động.

Ví dụ với `P` là “execution của `checkout()`”:

~~~text
POINT checkout              cflow(P) = true
  POINT reserve             cflow(P) = true
    POINT audit             cflow(P) = true
  POINT audit               cflow(P) = true
RETURN FROM checkout

POINT reserve (gọi riêng)  cflow(P) = false
  POINT audit              cflow(P) = false
~~~

Sơ đồ nêu ngữ nghĩa khái niệm. Nó không chỉ ra kiểu join point của từng công nghệ; chẳng hạn “method call” có thể được xem là một điểm tại caller, còn “method execution” ở callee.

Nếu cần quan sát **chỉ các lời gọi `audit()` trong quá trình checkout**, pointcut tổng hợp có thể mô tả:

~~~text
isAuditJoinPoint AND cflow(checkoutStart)
~~~

Ở đây `isAuditJoinPoint` là điều kiện chọn đối tượng cần quan sát, còn `checkoutStart` xác định **phạm vi ngữ cảnh**. Hai vai trò này khác nhau: bỏ điều kiện `isAuditJoinPoint` có thể khiến mọi join point bên trong checkout đều được chọn.

## 4. Khác biệt của `cflowbelow(P)`

**`cflowbelow(P)`** mô tả các join point **nằm bên dưới một join point khớp `P` đang hoạt động**, **không bao gồm chính điểm gốc khớp `P` của lần kích hoạt đó**.

Với `P` chọn lần vào `checkout()` từ bên ngoài:

| Join point | `cflow(P)` | `cflowbelow(P)` | Lý do |
| --- | --- | --- | --- |
| Điểm vào `checkout()` gốc | Có | Không | `cflow` gồm gốc; `cflowbelow` không gồm chính gốc ấy |
| `reserve()` gọi bên trong `checkout()` | Có | Có | Nằm thấp hơn gốc đang hoạt động |
| `audit()` gọi sâu từ `reserve()` | Có | Có | Vẫn ở trong ngăn xếp có gốc |
| `audit()` gọi trực tiếp ngoài checkout | Không | Không | Không có gốc đang hoạt động |
| `reserve()` sau khi checkout kết thúc | Không | Không | Phạm vi gốc đã kết thúc |

### 4.1. Vì sao cần loại bỏ điểm gốc?

Có những chính sách cần áp dụng **chỉ cho thao tác con** của một tác vụ, không áp dụng trực tiếp lên điểm bắt đầu. Chẳng hạn muốn đo mọi thao tác kho và audit thực hiện *bên dưới checkout* nhưng không tính cả điểm `checkout()` vào một bộ đếm join point. Lúc đó `cflowbelow(P)` diễn đạt đúng hơn `cflow(P)`.

### 4.2. Đệ quy và nhiều điểm gốc lồng nhau

Với đệ quy, `checkout()` có thể gọi một `checkout()` khác khi lần ngoài chưa kết thúc. **Lần `checkout()` bên trong** vẫn là join point khớp `P`, nhưng nó đồng thời **nằm bên dưới gốc khớp `P` phía ngoài**. Vì vậy, trong ngữ nghĩa luồng động, có thể có một join point mang nhãn `P` mà vẫn thuộc `cflowbelow(P)` do đang ở dưới **một gốc khác**.

Không nên phát biểu đơn giản rằng “mọi điểm khớp `P` đều bị `cflowbelow(P)` loại trừ” trong mọi trường hợp. Cách diễn đạt chính xác hơn là **loại chính điểm gốc của phạm vi đang xét; những điểm khớp `P` lồng bên trong có thể nằm dưới một gốc ngoài**.

### 4.3. Không coi “below” là một tầng trực tiếp

`cflowbelow(P)` không chỉ chọn lời gọi con trực tiếp. Một join point nằm sâu nhiều tầng (`checkout → reserve → audit → persist`) vẫn có thể khớp vì nó thuộc phần dưới trong cùng luồng điều khiển. Nếu yêu cầu chỉ chọn **callee trực tiếp** của một lời gọi, đó là bài toán khác, không được giải quyết chỉ bằng “below”.

## 5. Kết hợp pointcut luồng điều khiển với lựa chọn mục tiêu

Một điểm dễ gây lỗi là chỉ viết quy tắc phạm vi và quên điều kiện chọn đối tượng. Ví dụ mục tiêu:

> “Ghi metrics cho những lần `reserve()` diễn ra khi `checkout()` đang chạy, nhưng không ghi metrics cho mọi phương thức khác của checkout.”

Mô tả khái niệm:

~~~text
P = execution(checkout(...))
Q = execution(reserve(...))

selected = Q AND cflowbelow(P)
~~~

Các từ `execution`, `AND` và ký hiệu dấu ba chấm trong sơ đồ là **ký pháp giải thích**, không bảo đảm là cú pháp chung của mọi AOP engine.

Ý nghĩa: `Q` xác định *loại join point cần can thiệp*; `cflowbelow(P)` xác định *ngữ cảnh cần có tại thời điểm xảy ra*. Nếu `reserve()` chạy từ một đường gọi khác, `Q` vẫn đúng nhưng điều kiện ngữ cảnh sai, nên không được chọn. Nếu một `audit()` chạy trong checkout, ngữ cảnh đúng nhưng `Q` sai, nó cũng không thuộc pointcut tổng hợp này.

Có thể dùng các phép ghép khác khi cơ chế cho phép:

| Mô tả | Kết quả mong muốn |
| --- | --- |
| `Q AND cflow(P)` | Chọn `Q` khi thuộc luồng của `P`, có thể gồm gốc nếu gốc cũng khớp `Q` |
| `Q AND cflowbelow(P)` | Chọn `Q` nằm dưới điểm gốc `P` |
| `Q AND NOT cflow(P)` | Chọn `Q` khi **không** ở trong luồng của `P` |
| `(Q OR R) AND cflow(P)` | Chọn `Q` hoặc `R` nhưng chỉ trong ngữ cảnh `P` |
| `Q AND cflow(P) AND inBoundary(B)` | Chọn `Q` trong luồng `P` và phạm vi `B` đã định nghĩa |

Phủ định rộng `NOT cflow(P)` có thể chọn vô số join point không liên quan. Hãy luôn giới hạn nó bằng bộ chọn mục tiêu như `Q` để quy tắc diễn đạt đúng ý định và tránh overhead.

## 6. Ví dụ Java 17+ chạy được: mô phỏng cflow và cflowbelow

Ví dụ sau dùng **JDK dynamic proxy** và **`ThreadLocal` ghi độ sâu các lần `checkout()` đang hoạt động** để *mô phỏng trực quan* điểm gốc của luồng điều khiển. Đây **không phải engine AOP đầy đủ** và không khẳng định tên `cflow` là một API tích hợp của Java. Nó cho thấy cách một **bộ chọn có ngữ cảnh** thay đổi kết quả ở các lần gọi khác nhau.

Để mọi lời gọi nội bộ cũng đi qua proxy, `Core` nhận một tham chiếu `calls` trỏ tới interface proxy. Nếu gọi `this.reserve()` trực tiếp, proxy sẽ không quan sát lời gọi ấy. Mô hình này chỉ theo dõi **lời gọi đồng bộ qua proxy trên cùng thread**.

Tạo file `ControlFlowPointcutDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class ControlFlowPointcutDemo {
    interface Operations {
        String checkout(String id);
        String reserve(String id);
        void audit(String event);
    }

    static final class Core implements Operations {
        private Operations calls;

        void bind(Operations calls) {
            this.calls = calls;
        }

        @Override
        public String checkout(String id) {
            System.out.println("CORE checkout");
            calls.reserve(id);
            calls.audit("checkout " + id);
            if ("bad".equals(id)) {
                throw new IllegalArgumentException("invalid order");
            }
            return "done " + id;
        }

        @Override
        public String reserve(String id) {
            System.out.println("CORE reserve");
            calls.audit("reserve " + id);
            return "reserved " + id;
        }

        @Override
        public void audit(String event) {
            System.out.println("CORE audit " + event);
        }
    }

    static final class FlowHandler implements java.lang.reflect.InvocationHandler {
        private final Operations target;
        private final ThreadLocal<Integer> checkoutDepth =
                ThreadLocal.withInitial(() -> 0);

        FlowHandler(Operations target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            int depthAtEntry = checkoutDepth.get();
            boolean isCheckout = method.getName().equals("checkout");
            boolean inCheckoutFlow = isCheckout || depthAtEntry > 0;
            boolean strictlyBelowCheckout = depthAtEntry > 0;

            System.out.println("POINT " + method.getName()
                    + " cflow=" + inCheckoutFlow
                    + " cflowbelow=" + strictlyBelowCheckout);

            if (isCheckout) {
                checkoutDepth.set(depthAtEntry + 1);
            }
            try {
                try {
                    return method.invoke(target, args);
                } catch (InvocationTargetException wrapped) {
                    throw wrapped.getCause();
                }
            } finally {
                if (isCheckout) {
                    if (depthAtEntry == 0) {
                        checkoutDepth.remove();
                    } else {
                        checkoutDepth.set(depthAtEntry);
                    }
                }
            }
        }
    }

    public static void main(String[] args) {
        Core core = new Core();
        Operations operations = (Operations) Proxy.newProxyInstance(
                Operations.class.getClassLoader(),
                new Class<?>[] { Operations.class },
                new FlowHandler(core));
        core.bind(operations);

        operations.audit("outside");
        System.out.println("RESULT " + operations.checkout("A-1"));
        System.out.println("RESULT " + operations.reserve("B-2"));
        try {
            operations.checkout("bad");
        } catch (IllegalArgumentException error) {
            System.out.println("ERROR " + error.getMessage());
        }
        operations.audit("after-error");
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 ControlFlowPointcutDemo.java
java ControlFlowPointcutDemo
~~~

Đầu ra chính xác, đã kiểm chứng với Java 17 language target:

~~~text
POINT audit cflow=false cflowbelow=false
CORE audit outside
POINT checkout cflow=true cflowbelow=false
CORE checkout
POINT reserve cflow=true cflowbelow=true
CORE reserve
POINT audit cflow=true cflowbelow=true
CORE audit reserve A-1
POINT audit cflow=true cflowbelow=true
CORE audit checkout A-1
RESULT done A-1
POINT reserve cflow=false cflowbelow=false
CORE reserve
POINT audit cflow=false cflowbelow=false
CORE audit reserve B-2
RESULT reserved B-2
POINT checkout cflow=true cflowbelow=false
CORE checkout
POINT reserve cflow=true cflowbelow=true
CORE reserve
POINT audit cflow=true cflowbelow=true
CORE audit reserve bad
POINT audit cflow=true cflowbelow=true
CORE audit checkout bad
ERROR invalid order
POINT audit cflow=false cflowbelow=false
CORE audit after-error
~~~

### 6.1. Giải thích năm đoạn quan trọng

1. **`audit("outside")`:** không có `checkout()` nào đang hoạt động, nên cả `cflow` lẫn `cflowbelow` đều `false`.
2. **Điểm `checkout("A-1")`:** đây là gốc vừa được chọn, vì vậy `cflow=true` nhưng `cflowbelow=false`. Bộ đếm độ sâu được tăng trước khi gọi vào target.
3. **`reserve()` và `audit()` lồng nhau:** khi checkout còn hoạt động, các lời gọi qua proxy nằm **dưới gốc** nên cả hai cờ là `true`. `audit("checkout A-1")` dù được gọi trực tiếp từ checkout cũng thuộc `cflowbelow`.
4. **`reserve("B-2")` gọi độc lập:** nó có cùng chữ ký với `reserve("A-1")` nhưng không nằm dưới checkout đang hoạt động; vì vậy cờ đều `false`. Đây chính là giá trị của pointcut theo ngữ cảnh.
5. **`checkout("bad")` có ngoại lệ:** trong `finally`, bộ đếm được phục hồi, sau đó `audit("after-error")` chạy bên ngoài với cả hai cờ `false`. Nếu quên cleanup khi lỗi, lời gọi sau có thể bị nhận nhầm vào luồng cũ.

### 6.2. Vì sao dùng bộ đếm thay vì boolean?

Nếu `checkout()` gọi lồng một `checkout()` khác, đặt cờ `true` khi vào rồi đặt `false` khi ra sẽ sai: inner checkout kết thúc có thể xóa trạng thái mà outer checkout vẫn đang hoạt động. **Đếm độ sâu** và khôi phục `depthAtEntry` trong `finally` cho phép quản lý phạm vi lồng nhau an toàn hơn.

Ví dụ chỉ xét một điểm gốc là `checkout()` và xử lý `cflowbelow` qua `depthAtEntry > 0`. Trong một engine AOP thực, việc khớp điểm gốc, precedence và tính toán các điểm thuộc luồng có thể được thực hiện khác; không xem ví dụ proxy này như đặc tả cho mọi công cụ.

### 6.3. Những giới hạn của ví dụ

- Chỉ intercept phương thức được gọi qua interface proxy `Operations`.
- Bộ chọn gốc ở đây so tên `checkout`; ứng dụng thật cần xét chữ ký/overload/annotation để tránh khớp nhầm.
- Dữ liệu trong `ThreadLocal` thuộc **thread hiện tại**, không tự động theo một tác vụ chuyển thread.
- Proxy quan sát các điểm vào phương thức, không tự phát hiện constructor, truy cập field, lời gọi trực tiếp tới target hoặc join point được bytecode weaving hỗ trợ sâu hơn.
- Không có advice tách riêng; chương trình in kết quả lựa chọn tại handler để minh họa semantics. Muốn thực hiện chính sách, kết hợp điều kiện ngữ cảnh với một bộ chọn join point mục tiêu và đặt advice vào đó.

## 7. Khác biệt giữa cflow và đồ thị gọi tĩnh

Giả sử mã có thể đi theo hai đường:

~~~text
Path A: checkout() -> reserve() -> audit()
Path B: adminTask() -> reserve() -> audit()
~~~

Nếu chỉ phân tích source hoặc đồ thị gọi, cả hai đường đều có `reserve()` gọi `audit()`. Một pointcut tĩnh chỉ chọn `audit()` sẽ khớp cả hai. Nhưng `cflow(checkout)` **chỉ đúng trên Path A khi một checkout đang thực sự hoạt động**.

Cũng không phải cứ code của `checkout()` từng tạo ra một tác vụ thì những công việc xảy ra sau đó đều nằm dưới stack của checkout. **Nguồn gốc dữ liệu** và **ngăn xếp điều khiển hiện tại** là hai mối quan hệ khác nhau. Muốn theo một request xuyên qua tác vụ bất đồng bộ hoặc hàng đợi, có thể cần correlation ID hoặc context propagation, không thể chỉ dựa vào `cflow` trên một stack đồng bộ.

Cách tự hỏi giúp chọn đúng phương pháp:

- “Một phương thức được khai báo trong class nào?” → pointcut theo metadata tĩnh.
- “Một phương thức được gọi khi `checkout()` vẫn đang nằm trên đường gọi?” → pointcut theo luồng điều khiển.
- “Một tác vụ có cùng request ID với checkout ban đầu dù chạy sau, ở thread khác?” → cần theo ngữ cảnh tương quan/phân tán; không mặc định `cflow` đáp ứng.
- “Một đối số có cùng đối tượng đã xuất hiện trong lời gọi gốc?” → bài toán identity/value flow khác với chỉ theo call stack.

## 8. Đệ quy, reentrancy và ngoại lệ

### 8.1. Đệ quy và sự lồng nhau

Trong thuật toán đệ quy, điểm gốc `P` có thể được kích hoạt nhiều lần trước khi lần đầu trả về. Nếu dùng một cờ boolean đơn giản, kết thúc một lần bên trong có thể làm mất trạng thái lần ngoài. Cấu trúc stack hoặc **depth counter** là mô hình phù hợp để biểu diễn có bao nhiêu phạm vi gốc đang hoạt động.

**`cflowbelow(P)` không đơn giản là NOT P.** Một lần kích hoạt `P` lồng bên trong có thể vừa thuộc tập `P` vừa nằm dưới lần `P` bên ngoài. Khi viết pointcut cho đệ quy, cần xác định muốn áp dụng trên **mọi cấp** hay chỉ **đỉnh đầu tiên** của call chain.

### 8.2. Ngoại lệ và cleanup

Khi lời gọi gốc ném ngoại lệ, các khối `finally` dọn trạng thái nên được thực thi trong phạm vi đã đi vào. Nếu cơ chế tự quản lý cflow, ta cần tin vào hợp đồng về kết thúc phạm vi; khi tự mô phỏng như ví dụ, buộc phải đặt cập nhật trạng thái trong `try/finally`.

Lưu ý: việc chính advice ghi sự kiện gây ngoại lệ có thể ảnh hưởng quá trình tháo stack. Nếu mục đích chỉ là đo lường, hãy có chính sách lỗi độc lập cho logging/metrics để không vô tình che ngoại lệ gốc.

### 8.3. Gọi lặp vào cùng target và thứ tự advice

Nếu cùng một join point bị bao bởi nhiều advice `around`, mỗi advice có thể gọi `proceed` hoặc đổi đường thực thi. Khi retry, một target có thể chạy nhiều lần dưới cùng một gốc hoặc dưới nhiều gốc khác nhau, tùy vị trí advice retry. Vì vậy, **cflow theo số lần kích hoạt thực tế**, không theo ý định “chỉ thực hiện một lần” của caller.

Hãy xác minh thứ tự advice và số lần target thực thi khi có cache, retry, kiểm quyền hoặc giao dịch, đặc biệt khi chính sách cắt ngang có tác dụng phụ.

## 9. Cflow với bất đồng bộ, thread, coroutine và tác vụ phân tán

Luồng điều khiển động của lời gọi đồng bộ thường dựa trên trạng thái call stack tại thời điểm join point xảy ra. Khi chuyển sang **thread khác, callback sau này, event loop hoặc tiến trình khác**, việc giữ nguyên stack đang hoạt động không được bảo đảm. Ví dụ:

~~~text
Thread A:
checkout()
  submitAsync(task)
  return                  <- phạm vi checkout kết thúc

Thread B (về sau):
task()
  reserve()
  audit()
~~~

Ở Thread B, không thể chỉ nhìn tên `reserve()` rồi kết luận `cflow(checkout)` đúng theo call stack của Thread A. Nếu cần tiếp tục theo dõi “cùng thao tác checkout”, hãy xem xét **truyền ngữ cảnh** qua tác vụ: request ID, trace ID hoặc một token đại diện cho workflow, kèm quy tắc vòng đời và cleanup rõ ràng.

Cần phân biệt:

| Cơ chế | Theo dõi | Phù hợp khi |
| --- | --- | --- |
| Control-flow pointcut | Join point nằm dưới một điểm gốc đang hoạt động | Tác vụ/lời gọi đồng bộ trong đường thực thi có thể quan sát |
| Thread-local state | Dữ liệu gắn với thread | Cần ngữ cảnh trong thread hiện tại; phải xử lý pool/reuse |
| Context propagation | Ngữ cảnh chuyển giữa các tác vụ/thread | Tác vụ bất đồng bộ cần giữ correlation |
| Distributed tracing | Quan hệ các span/trace giữa tiến trình | Theo dõi luồng phân tán qua mạng và dịch vụ |

Các công nghệ AOP khác nhau có thể mở rộng hoặc diễn giải phạm vi theo mô hình riêng. **Không tự suy luận rằng toán tử tên `cflow` tự động truyền qua thread hoặc tiến trình**. Chỉ coi một cơ chế có khả năng đó khi tài liệu và kiểm thử của chính công cụ xác nhận.

`ThreadLocal` cũng cần được xóa hoặc khôi phục ở phạm vi phù hợp, đặc biệt với thread pool dùng lại thread. Nếu không, lời gọi không liên quan sau đó có thể bị chọn nhầm.

## 10. Giới hạn theo công nghệ AOP

### 10.1. Không phải mọi pointcut engine hỗ trợ `cflow`

Có những engine chỉ hỗ trợ khớp chữ ký, annotation hoặc lời gọi qua proxy. Có những engine hỗ trợ điều kiện pointcut động, nhưng không có cú pháp `cflow` hay `cflowbelow`. Một bộ máy weaving có thể có ngôn ngữ pointcut phong phú hơn, tuy nhiên vẫn phải kiểm tra phạm vi join point thực tế.

Một phép thử khả năng tối thiểu:

1. Công cụ có toán tử chọn theo luồng động hay chỉ metadata tĩnh?
2. Toán tử có hỗ trợ loại join point gốc cần dùng (call/execution) không?
3. Nó có làm rõ **bao gồm hay loại trừ gốc** không?
4. Phạm vi weaving có bao gồm tất cả phương thức/lớp cần quan sát không?
5. Có giới hạn do classloader, module, proxy, lời gọi nội bộ, `private` hoặc `final` không?
6. Nó có bảo toàn ngữ nghĩa khi exception, recursion, thread switch và nested pointcut không?
7. Điều kiện runtime được đánh giá thế nào và chi phí ước lượng ra sao?

### 10.2. Method call khác method execution

Một số mô hình AOP phân biệt:

- **Call join point:** nơi mã caller thực hiện lời gọi tới phương thức.
- **Execution join point:** nơi thân phương thức được thực thi ở phía callee.

Điểm được chọn làm gốc `P` sẽ quyết định ranh giới của cflow bắt đầu và kết thúc. Nếu chọn call join point, một số vị trí quanh lệnh gọi có thể nằm trong phạm vi khác với execution join point. Cần chọn điểm gốc phù hợp với ý định quan sát và không tùy tiện coi hai loại tương đương.

### 10.3. Proxy và lời gọi nội bộ

Proxy thường chỉ quan sát lời gọi **đi qua proxy**. Lời gọi `this.reserve()` bên trong target có thể bỏ qua proxy, khiến lời gọi ấy không tạo join point theo mô hình proxy dù nó xảy ra trên call stack Java. Khi cần quan sát sâu, kiểm tra khả năng của công cụ và đường lời gọi thực; không dùng “cflow có vẻ đúng” để bỏ qua giới hạn can thiệp.

Trong ví dụ chạy được, `Core` cố ý gọi `calls.reserve()` và `calls.audit()` qua proxy để ta nhìn được các điểm lồng nhau. Điều này chỉ là kỹ thuật minh họa, không phải yêu cầu thiết kế áp dụng cho mọi codebase.

### 10.4. Chi phí tại runtime

Một pointcut theo metadata tĩnh có thể được quyết định trước ở nhiều trường hợp. Một pointcut theo luồng động thường cần biết “gốc `P` có đang hoạt động hay không”, dẫn đến việc duy trì trạng thái, kiểm tra mỗi join point hoặc thao tác bổ sung khi vào/ra vùng chọn.

Chi phí thực phụ thuộc engine, số join point, phương pháp triển khai và tần suất gọi. Không khẳng định `cflow` luôn đắt một mức cố định; thay vào đó, đo overhead thực tế dưới tải đại diện, giới hạn bộ chọn mục tiêu `Q`, và tránh phủ định/điều kiện rộng không cần thiết.

### 10.5. Không che khuất hợp đồng nghiệp vụ

Nếu một chức năng chỉ được phép chạy khi checkout đang hoạt động vì **bất biến nghiệp vụ**, cần cân nhắc biểu diễn bất biến đó trong API và logic nghiệp vụ. Pointcut theo cflow thích hợp hơn cho những **chính sách cắt ngang phụ thuộc ngữ cảnh** như audit/metrics/tracing, không nên biến việc có/không có advice thành cơ chế duy nhất bảo vệ dữ liệu miền nếu ranh giới đó có thể bị bỏ qua.

## 11. Thiết kế một control-flow pointcut có thể bảo trì

Một quy trình thực hành:

1. **Xác định chính sách:** cần chọn log, metrics hoặc quan sát gì? Viết một câu diễn đạt ngữ cảnh, ví dụ “ghi audit ở thao tác kho chỉ trong quy trình checkout đồng bộ”.
2. **Chọn gốc `P`:** đây là join point biểu thị rõ “checkout bắt đầu”; phân biệt call/execution và overload, tránh chọn quá rộng vì cùng tên.
3. **Chọn mục tiêu `Q`:** phương thức hoặc join point nào trong luồng cần advice? `Q` giúp tránh gắn advice vào mọi điểm dưới gốc.
4. **Quyết định `cflow` hay `cflowbelow`:** có muốn tính cả join point gốc vào tập chọn không?
5. **Liệt kê đường khớp và đường không khớp:** gọi lồng một tầng, nhiều tầng, độc lập, đệ quy, ném lỗi, tự gọi `this`, bất đồng bộ.
6. **Xác minh khả năng công cụ:** pointcut theo ngữ cảnh, weaving, proxy, runtime binding, visibility và module/classloader.
7. **Đo tác dụng phụ:** advice có làm thay đổi kết quả, số lần chạy, ngoại lệ, độ trễ hoặc lượng dữ liệu log không?
8. **Kiểm thử theo đường chạy thực tế:** kiểm tra cùng một phương thức `reserve` khi được gọi từ checkout và khi được gọi độc lập; xác minh cleanup sau lỗi.

Ví dụ bảng test cho `Q AND cflowbelow(P)` với `P=checkout`, `Q=reserve`:

| Trường hợp | Kỳ vọng |
| --- | --- |
| `checkout → reserve` trên đường gọi quan sát được | Khớp |
| `checkout → helper → reserve` nhiều tầng | Khớp |
| `reserve` gọi độc lập | Không khớp |
| `reserve` gọi sau khi checkout trả về | Không khớp |
| `checkout` là điểm gốc nhưng không khớp `reserve` | Không khớp `Q` |
| `checkout` ném lỗi, sau đó `reserve` gọi độc lập | Không khớp; cleanup phải đúng |
| Checkout đệ quy | Xác định rõ quan hệ với gốc bên ngoài |
| `checkout` tạo task chạy trên thread khác | Tùy mô hình công cụ; không tự nhận là cùng cflow |
| `this.reserve()` bỏ qua proxy | Không kỳ vọng proxy tạo join point cho reserve |

### Khi một flow có nhiều gốc

Nếu có hai lần `checkout()` nằm lồng nhau, quy tắc `cflow(checkout)` có thể đúng do **ít nhất một gốc** đang hoạt động. Nếu chính sách yêu cầu chỉ gắn sự kiện với *một* lần checkout cụ thể, boolean/depth không đủ phân biệt danh tính của gốc. Khi đó cần một context token hoặc stack của **định danh tác vụ**, cùng quy tắc truyền/khôi phục ngữ cảnh an toàn.

Đây là điểm khác nhau giữa kiểm tra **“có nằm trong một checkout?”** và **“nằm trong checkout có ID X?”**. Loại thứ hai đòi hỏi binding ngữ cảnh hoặc chính sách bổ sung ngoài toán tử cflow thuần túy.

## 12. Những lỗi hiểu sai phổ biến

- **Cho rằng cflow chọn phương thức theo tên:** nó chọn dựa trên trạng thái luồng động; thường cần kết hợp một pointcut mục tiêu theo tên/chữ ký.
- **Nhầm `cflow` với `cflowbelow`:** thứ nhất tính cả điểm gốc; thứ hai chọn các điểm dưới gốc.
- **Hiểu `cflowbelow` chỉ chọn con trực tiếp:** nó có thể chọn điểm ở sâu nhiều tầng trong ngăn xếp.
- **Coi `cflowbelow(P)` là `NOT P`:** đệ quy/lồng nhau cho thấy điều này không đúng.
- **Nhìn đồ thị source rồi suy ra runtime cflow:** khả năng gọi không chứng minh lời gọi đó đang hoạt động.
- **Đặt cờ boolean không khôi phục khi lỗi:** trạng thái rò rỉ sang lời gọi sau, đặc biệt nguy hiểm trên thread pool.
- **Bỏ qua self-invocation hoặc đường gọi trực tiếp:** proxy không quan sát mọi lời gọi của target.
- **Cho rằng một task bất đồng bộ vẫn nằm trên stack gốc:** cần ngữ cảnh được truyền rõ nếu muốn theo dõi giữa thread.
- **Dùng `NOT cflow(P)` quá rộng:** có thể áp advice lên cả hệ thống ngoài ý muốn.
- **Tin mọi công cụ đều có cùng cú pháp cflow:** pointcut model, loại join point và weaving khác nhau.
- **Đặt nghiệp vụ quan trọng chỉ trong advice có ngữ cảnh:** làm quy tắc miền khó nhìn thấy và dễ bị bỏ qua bởi những đường không được can thiệp.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `reserve()` được gọi trực tiếp và cũng được gọi từ `checkout()`. Có thể dùng pointcut chỉ theo chữ ký `reserve()` để phân biệt hai tình huống không?  
**Trả lời:** Không. Chữ ký giống nhau; cần thêm điều kiện ngữ cảnh luồng điều khiển hoặc ngữ cảnh runtime tương đương.

**Câu 2.** Pointcut `P` chọn `checkout()`. Chính điểm gốc này có thuộc `cflow(P)` và `cflowbelow(P)` không?  
**Trả lời:** Thuộc `cflow(P)`, nhưng không thuộc `cflowbelow(P)` do *chính lần kích hoạt gốc đó*. Nếu một `checkout` khác lồng dưới gốc ngoài, nó có thể thuộc `cflowbelow(P)` nhờ gốc ngoài.

**Câu 3.** Một `audit()` gọi sâu ba tầng dưới checkout có thuộc `cflowbelow(P)` không?  
**Trả lời:** Có thể có, nếu nó là một join point được công cụ quan sát và luồng gốc vẫn đang hoạt động; “below” không giới hạn một tầng.

**Câu 4.** Checkout tạo một `CompletableFuture` rồi trả về, còn `reserve()` chạy sau trên thread khác. Có thể mặc định `cflow(checkout)` đúng ở `reserve()` không?  
**Trả lời:** Không. Call stack động có thể đã kết thúc hoặc khác thread; cần kiểm tra hợp đồng công nghệ và cơ chế truyền ngữ cảnh nếu muốn theo dõi quan hệ tác vụ.

**Câu 5.** Tại sao trong ví dụ cần `finally` và bộ đếm độ sâu?  
**Trả lời:** `finally` đảm bảo phục hồi trạng thái trên nhánh lỗi; bộ đếm giữ được các phạm vi gốc lồng nhau mà boolean đơn giản có thể xử lý sai.

## 14. Tổng kết

**Pointcut theo luồng điều khiển** lựa chọn join point dựa trên **ngữ cảnh lời gọi đang diễn ra tại runtime**, thay vì chỉ dựa trên chữ ký hoặc vị trí khai báo. Ý tưởng `cflow(P)` gồm điểm gốc khớp `P` và những điểm thuộc luồng thực thi của nó; `cflowbelow(P)` chọn những điểm ở bên dưới gốc. Trong thực tế, cần kết hợp điều kiện chọn mục tiêu, chọn đúng loại join point gốc, bảo toàn trạng thái khi ngoại lệ/đệ quy, và hiểu giới hạn của proxy, weaving, thread cùng tác vụ bất đồng bộ. Kiểm thử cả đường trong luồng và ngoài luồng mới chứng minh advice áp dụng đúng ý định.
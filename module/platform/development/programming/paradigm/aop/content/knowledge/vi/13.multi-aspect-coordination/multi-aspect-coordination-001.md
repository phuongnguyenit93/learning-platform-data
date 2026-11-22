# Một join point đồng thời phù hợp với nhiều aspect trong AOP

> **Mục tiêu:** Hiểu hiện tượng nhiều aspect đồng thời chọn **cùng một join point** trong lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP). Nắm được cơ chế pointcut overlap, advice composition, thứ tự ưu tiên, chuỗi around/proceed, short-circuit, retry, return/exception và tác động phụ khi nhiều chính sách cùng quan sát hoặc điều chỉnh một thao tác. Biết thiết kế ca kiểm thử chứng minh chính xác số lần advice và phần gốc thực thi, đồng thời không giả định mọi công cụ AOP có cùng ngữ nghĩa mặc định.

## 1. Tình huống: một thao tác đồng thời cần ba chính sách

Một phương thức nghiệp vụ nhận yêu cầu thanh toán:

~~~text
PaymentService.pay(orderId, amount)
~~~

Có ba mối quan tâm xuyên suốt:

- **Tracing:** ghi nhận điểm bắt đầu/kết thúc để theo dõi yêu cầu.
- **Validation:** kiểm tra một điều kiện đầu vào khi thao tác được chọn.
- **Audit:** phát sự kiện quan sát ở những thời điểm quan trọng.

Nếu pointcut của ba aspect đều khớp **method execution join point** của pay, cả ba có thể đóng góp advice tại điểm đó. Điều này không có nghĩa ba advice tự động chạy song song; cách chúng được kết hợp còn phụ thuộc mô hình AOP và precedence.

~~~text
                  pay(orderId, amount)
                           |
               +-----------+-----------+
               |           |           |
             Trace       Validate     Audit
               |           |           |
               +-----------+-----------+
                           |
                        Business
~~~

Sơ đồ chỉ thể hiện **tập chính sách cùng quan tâm một điểm**, chưa thể hiện thứ tự hoặc quyền điều khiển.

Câu hỏi đúng cần đặt ra là: **Những advice nào thực sự được chạy, theo trình tự nào, mỗi advice quan sát ranh giới nào, và nếu một advice không gọi tiếp thì điều gì xảy ra?**

## 2. Những thành phần AOP phải phân biệt

| Thuật ngữ | Ý nghĩa đối với bài này |
|---|---|
| **Join point** | Điểm hoặc sự kiện thuộc mô hình thực thi có thể can thiệp |
| **Pointcut** | Điều kiện chọn tập join point |
| **Advice** | Hành vi bổ sung được áp dụng tại điểm đã chọn |
| **Aspect** | Đơn vị tổ chức một mối quan tâm xuyên suốt, có thể chứa nhiều advice |
| **Weaving / interception** | Cơ chế kết hợp hành vi aspect vào đường thực thi |
| **Precedence / ordering** | Quy tắc quyết định cách sắp xếp advice khi nhiều lời khai cùng khớp |

Một aspect có thể chứa nhiều advice; vì vậy **ba aspect khớp không nhất thiết bằng ba lần advice invocation**. Một pointcut có thể khớp nhưng advice bên trong lại không chạy vì lớp bao ngoài đã short-circuit.

Tương tự, **một method name không phải danh tính duy nhất của join point**. Cần biết loại điểm (call/execution...), chữ ký, vị trí và lần xuất hiện động cụ thể.

## 3. Tập giao của nhiều pointcut

Đặt:

- **P_A:** tập các join point mà pointcut của Aspect A chọn.
- **P_B:** tập các join point mà pointcut của Aspect B chọn.
- **J:** một join point cụ thể được quan sát.

Khi J thuộc P_A và đồng thời thuộc P_B, J nằm trong **giao của P_A và P_B**.

~~~text
J ∈ P_A
J ∈ P_B
────────────
J ∈ P_A ∩ P_B
~~~

Không cần P_A và P_B hoàn toàn giống nhau. Ví dụ:

~~~text
Aspect A: mọi method execution của PaymentService
Aspect B: chỉ method execution có tên pay trong PaymentService
~~~

Một execution của pay có thể được cả hai chọn, còn preview có thể chỉ được A chọn.

### 3.1. Overlap không mặc nhiên là lỗi

Một operation được tracing, đo hiệu năng và audit cùng lúc là yêu cầu thông thường. Điều cần kiểm soát không phải xóa mọi vùng giao, mà là **nghĩa của mỗi advice** và cách phối hợp của chúng.

Overlap trở thành rủi ro khi hai aspect cùng phát một sự kiện audit không phân biệt, cùng biến đổi đối số trái ngược nhau, cùng retry, hoặc cùng sở hữu một resource mà không thống nhất ownership.

## 4. Matching tĩnh và điều kiện động

Pointcut có thể dùng điều kiện tĩnh trên tên phương thức, kiểu khai báo hoặc chữ ký. Một số mô hình còn cho phép điều kiện phụ thuộc đối số, target hoặc ngữ cảnh runtime.

Ví dụ:

~~~text
A: chọn mọi lần execution pay(...)
B: chọn execution pay(...) khi amount > 100
~~~

Với amount=10, A có thể được chọn nhưng B không. Với amount=150, cả hai có thể phù hợp.

Cần phân biệt:

1. **Điều kiện cấu trúc** cho biết điểm có thể được chọn.
2. **Điều kiện động** quyết định một lần xuất hiện cụ thể có thỏa quy tắc hay không.
3. **Dòng điều khiển thực** cho biết advice có được chạy tới hay không.

Nếu around advice phía ngoài không gọi continuation, advice phía trong có thể không được vào dù pointcut của nó phù hợp.

## 5. Nhiều aspect không tự động là nhiều thread

Một nhầm lẫn phổ biến là nghĩ các aspect khớp cùng một join point sẽ chạy đồng thời trên các luồng khác nhau.

Trong một chuỗi around đồng bộ, cách hình dung thường hữu ích là **các lớp bao lồng nhau**:

~~~text
A enters
    B enters
        Original executes
    B exits
A exits
~~~

Đây là một chuỗi điều khiển có thứ tự. Một advice có thể chủ động tạo tác vụ bất đồng bộ, nhưng đó là hành vi riêng của advice và có hợp đồng completion/context khác, không phải hệ quả tất yếu của overlap.

### 5.1. Cùng khớp không phải cùng thời điểm

Một before advice quan sát khi vào; một after-returning advice chỉ có dữ liệu hoàn tất bình thường; một after-throwing advice quan sát lỗi đi qua ranh giới tương ứng. Cùng pointcut không có nghĩa mọi advice phát log vào cùng một lúc.

## 6. Thứ tự ưu tiên là phần của ngữ nghĩa

Nếu hai aspect cùng có around advice, thứ tự bao ngoài và bên trong có thể ảnh hưởng kết quả.

~~~text
Caller
  |
  A.before
    |
    B.before
      |
      Original
      |
    B.after
    |
  A.after
  |
Caller
~~~

Với lớp bao đồng bộ đi hết đường normal return, thứ tự vào là **A rồi B**, nhưng thứ tự ra là **B rồi A**.

Không có quy tắc chung cho mọi công cụ AOP rằng aspect được khai báo đầu file, đặt tên alphabet trước hoặc được biên dịch trước sẽ luôn bao ngoài. Cần xác minh **precedence semantics thực tế**.

### 6.1. Những câu hỏi về precedence

- Aspect nào phải ghi nhận yêu cầu **kể cả bị chặn**?
- Aspect nào chỉ cần quan sát **lần phần gốc thực sự chạy**?
- Chính sách nào được phép sửa dữ liệu hoặc trả fallback?
- Exception do phần gốc ném có thể bị advice khác chuyển đổi không?
- Retry nên ở **trong hay ngoài** một transaction boundary?
- Metrics cần đo cả cache hit hay chỉ execution thật?

Nếu trả lời chưa rõ, đổi thứ tự cho tới khi log trông hợp lý không phải cách thiết kế vững chắc.

## 7. Những loại advice khi nhiều aspect cùng khớp

| Loại advice | Ý nghĩa điển hình | Điều dễ nhầm |
|---|---|---|
| **Before** | Xử lý trước phần được chọn | Một around ngoài có thể chặn trước |
| **After-returning** | Quan sát hoàn tất bình thường | Không nhất thiết là thành công nghiệp vụ |
| **After-throwing** | Quan sát lỗi đi ra khỏi ranh giới | Lỗi có thể đã được aspect trong biến đổi |
| **After/finally** | Xử lý kết thúc theo hợp đồng | Không phải mọi lối thoát đều có return value |
| **Around** | Bao quanh và điều khiển phần tiếp theo | Proceed không nhất thiết gọi thẳng phần gốc |

Mỗi công cụ có thể quy định thứ tự trong và giữa các nhóm advice khác nhau. Bảng là **mô hình học tập**, không phải danh sách cú pháp bắt buộc.

## 8. Around advice và chuỗi continuation

Với ba around advice A, B và C, một thứ tự có thể là:

~~~text
A.around
   |
   +-- proceed → B.around
                     |
                     +-- proceed → C.around
                                       |
                                       +-- proceed → Original
~~~

**Proceed** (hoặc cơ chế tiếp tục tương đương) biểu diễn việc chuyển quyền điều khiển tới **phần còn lại của chuỗi**, có thể gồm nhiều advice khác trước khi tới phần gốc.

Hệ quả:

- A gọi proceed một lần chưa chứng minh Original chạy một lần.
- B có thể không tiếp tục, khiến C và Original không chạy.
- B có thể thử lại phần trong, khiến C và Original chạy nhiều lần khi công cụ cho phép.
- C có thể biến đổi kết quả hoặc lỗi trước khi B/A quan sát.

Cần phân biệt **số lần advice được vào**, **số lần continuation được gọi** và **số lần Original thực thi**.

## 9. Short-circuit: aspect trong có thể không chạy

Một around advice có thể từ chối yêu cầu trước khi gọi tiếp:

~~~text
Guard:
    nếu amount < 0:
        từ chối, không gọi tiếp
    ngược lại:
        proceed
~~~

Giả sử chuỗi:

~~~text
Trace → Guard → Audit → Original
~~~

Nếu Guard chặn, Trace và Guard đã được vào, nhưng Audit và Original **không chạy**. Audit không xuất hiện không phải bằng chứng điểm không thuộc pointcut của Audit.

### 9.1. Tác động tới kiểm toán

Nếu Audit phải ghi **tất cả yêu cầu, kể cả từ chối**, đặt Audit ở phía trong một Guard short-circuit có thể bỏ sót các sự kiện từ chối.

Nếu Audit chỉ ghi **những lần thực thi phần gốc**, vị trí phía trong Guard có thể đúng.

Đừng gọi một thứ tự là “tốt hơn” khi chưa xác định mục tiêu audit cần theo dõi **request**, **approved attempt** hay **business execution**.

## 10. Các aspect cùng biến đổi kết quả

Hai phép biến đổi theo thứ tự khác nhau có thể cho kết quả khác nhau.

~~~text
Original returns 5

AddOne(Double(5)) = 11
Double(AddOne(5)) = 12
~~~

Trong thực tế, A có thể chuẩn hóa result còn B lọc trường nhạy cảm. Nếu thay thứ tự, B có thể nhận dữ liệu trước hoặc sau khi A biến đổi.

Một policy chỉ nhằm quan sát thường nên **bảo toàn return value**; nếu được phép biến đổi phải khai báo rõ:

- Kiểu trả về hợp lệ.
- Trách nhiệm sở hữu phép biến đổi.
- Thứ tự với các aspect khác.
- Điều kiện khi không gọi proceed.
- Các tác dụng phụ và lời hứa với caller.

Không được suy rằng advice của các aspect độc lập sẽ **giao hoán** chỉ vì chúng được đặt trong các class khác nhau.

## 11. Phân biệt lỗi phần gốc với lỗi advice

Giả sử Original ném E. Inner advice có thể:

- Ghi nhận E rồi ném lại E.
- Bắt E rồi thay bằng E2.
- Bắt E rồi trả fallback bình thường.
- Tự ném lỗi mới trong cleanup.

Outer advice nhìn thấy **điều mà inner truyền ra**, không bắt buộc còn là E gốc.

~~~text
Outer A
    Inner B
        Original throws E
    B catches E and returns fallback
A sees normal return
~~~

Một after-throwing advice ở ngoài **không có lý do phải thấy E** nếu E đã được xử lý trong phần bên trong và không thoát ra ranh giới của nó.

### 11.1. Lỗi logger che lỗi gốc

Nếu Original ném E rồi advice finally gọi logger và logger ném F, caller có thể thấy F thay vì E. Aspect quan sát cần chính sách lỗi tường minh. Với logging best-effort thường muốn tránh phá nghiệp vụ; với audit bắt buộc có thể cần chính sách khác, không đơn giản bỏ qua mọi lỗi.

## 12. Ví dụ Java 17 số 1: ba aspect cùng trên một operation

Ví dụ dưới đây mô phỏng ba around aspect: **Trace**, **Guard**, **Audit**. Người viết tự lắp chain với thứ tự rõ ràng, không sử dụng một weaver hoặc pointcut parser. Nó giúp quan sát chính xác việc nhiều advice cùng quan tâm một operation được kết hợp ra sao.

**Đây là Java thuần minh họa AOP composition, không phải cú pháp một công cụ AOP cụ thể.**

Lưu **MultipleAspectsDemo.java**:

~~~java
import java.util.List;

public class MultipleAspectsDemo {
    @FunctionalInterface
    interface Next {
        String proceed();
    }

    interface Around {
        String invoke(String operation, int amount, Next next);
    }

    static final class TraceAspect implements Around {
        @Override
        public String invoke(String operation, int amount, Next next) {
            System.out.println("[trace] enter " + operation);
            try {
                String result = next.proceed();
                System.out.println("[trace] return " + result);
                return result;
            } catch (RuntimeException error) {
                System.out.println("[trace] throw "
                        + error.getClass().getSimpleName());
                throw error;
            }
        }
    }

    static final class GuardAspect implements Around {
        @Override
        public String invoke(String operation, int amount, Next next) {
            if (amount < 0) {
                System.out.println("[guard] blocked");
                throw new IllegalArgumentException("negative amount");
            }
            System.out.println("[guard] passed");
            return next.proceed();
        }
    }

    static final class AuditAspect implements Around {
        @Override
        public String invoke(String operation, int amount, Next next) {
            System.out.println("[audit] before");
            try {
                String result = next.proceed();
                System.out.println("[audit] success");
                return result;
            } catch (RuntimeException error) {
                System.out.println("[audit] failure "
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                System.out.println("[audit] finally");
            }
        }
    }

    static String original(String operation, int amount) {
        System.out.println("[business] " + operation + " " + amount);
        if (amount == 0) {
            throw new IllegalStateException("zero amount");
        }
        return operation + ":" + amount;
    }

    static String runChain(
            List<Around> chain, int index,
            String operation, int amount) {
        if (index == chain.size()) {
            return original(operation, amount);
        }
        Around current = chain.get(index);
        return current.invoke(
                operation, amount,
                () -> runChain(chain, index + 1, operation, amount));
    }

    static void runCase(
            List<Around> chain, String operation, int amount) {
        System.out.println("== amount " + amount + " ==");
        try {
            String result = runChain(chain, 0, operation, amount);
            System.out.println("[caller] result " + result);
        } catch (RuntimeException error) {
            System.out.println("[caller] caught "
                    + error.getClass().getSimpleName()
                    + ": " + error.getMessage());
        }
    }

    public static void main(String[] args) {
        List<Around> chain = List.of(
                new TraceAspect(),
                new GuardAspect(),
                new AuditAspect());

        runCase(chain, "pay", 2);
        runCase(chain, "pay", -1);
        runCase(chain, "pay", 0);
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac MultipleAspectsDemo.java
java MultipleAspectsDemo
~~~

**Stdout chính xác:**

~~~text
== amount 2 ==
[trace] enter pay
[guard] passed
[audit] before
[business] pay 2
[audit] success
[audit] finally
[trace] return pay:2
[caller] result pay:2
== amount -1 ==
[trace] enter pay
[guard] blocked
[trace] throw IllegalArgumentException
[caller] caught IllegalArgumentException: negative amount
== amount 0 ==
[trace] enter pay
[guard] passed
[audit] before
[business] pay 0
[audit] failure IllegalStateException
[audit] finally
[trace] throw IllegalStateException
[caller] caught IllegalStateException: zero amount
~~~

### 12.1. Đường thành công

Với amount=2, thứ tự là Trace enter → Guard passed → Audit before → Original → Audit success/finally → Trace return → Caller.

Trace **vào trước**, nhưng Trace **ra sau** Audit do nó bao ngoài chuỗi.

### 12.2. Đường bị Guard chặn

Với amount=-1, Guard ném IllegalArgumentException trước khi gọi next. Không có dòng Audit và không có dòng Business. Trace vẫn ghi lỗi vì Trace là lớp ngoài Guard.

Nếu hoán đổi Guard thành lớp ngoài Trace, ở nhánh từ chối có thể không có dòng Trace. Đây là một khác biệt **ngữ nghĩa quan sát**, không chỉ khác thứ tự trang trí.

### 12.3. Đường Original ném lỗi

Với amount=0, Original được gọi rồi ném IllegalStateException. Audit ghi failure và finally, sau đó Trace nhìn thấy cùng lỗi được truyền ra và Caller bắt được. Hai aspect cùng quan sát lỗi ở ranh giới của mình.

### 12.4. Vì sao đây chưa phải một engine AOP?

Hàm runChain được gọi thủ công với danh sách đã sắp xếp. Không có weaving vào mã method, không có ngôn ngữ pointcut và không có engine chọn join point. Chương trình chỉ minh họa **continuation composition** để người học dễ thấy hiệu ứng lồng nhau.

Trong hệ AOP thật, phải kiểm tra cách engine chọn advice và precedence theo đặc tả, thay vì cho rằng cách lắp List này là quy tắc chung.

## 13. Thay order làm thay số sự kiện

So sánh hai chuỗi:

~~~text
Chuỗi X: Trace → Guard → Audit → Original
Chuỗi Y: Guard → Trace → Audit → Original
~~~

Khi Guard chặn:

- Ở X, Trace đã được vào và có thể ghi một sự kiện từ chối.
- Ở Y, Trace chưa được vào nên không có sự kiện đó.

Điều này quyết định **sự kiện được cam kết ghi**. Khi cần observability hoặc audit của mọi yêu cầu, phải bố trí ranh giới quan sát bao được cả nhánh bị từ chối.

Khi chỉ cần đo chi phí của những lượt phần gốc đã chạy, đặt metric phía trong một policy chặn sớm có thể có ý nghĩa hơn.

## 14. Retry có thể khiến aspect trong chạy nhiều lần

Một around advice có thể được phép gọi continuation nhiều lần. Nếu A nằm ngoài Retry và B nằm trong Retry:

~~~text
A
  Retry
     → B → Original lần 1: lỗi
     → B → Original lần 2: thành công
~~~

A có thể chạy một lần, trong khi B và Original chạy hai lần.

Đây là lý do quan trọng nhất để phân biệt:

- **Một lời gọi từ caller**.
- **Một lần advice của lớp ngoài**.
- **Một lần Retry advice**.
- **Một lần attempt phía trong**.
- **Một lần Original thực sự thực thi**.

Những số này không nhất thiết bằng nhau.

### 14.1. Retry không tự an toàn

Nếu attempt 1 đã gửi một lệnh chuyển tiền rồi nhận lỗi mạng, attempt 2 có thể gửi lệnh lần nữa. Một policy retry cần giới hạn loại lỗi được retry, khả năng idempotent, transaction semantics và số lần tối đa.

Một around advice retry có thể làm lặp audit/log/metrics ở **bên trong**. Điều này có thể đúng nếu mỗi attempt phải có event riêng, nhưng sai nếu một event chỉ được phát mỗi yêu cầu ở bên ngoài.

## 15. Ví dụ Java 17 số 2: Retry ở giữa hai aspect khác

Chương trình này minh họa **Trace bên ngoài**, **RetryOnce ở giữa**, **Observer bên trong**. Original cố ý lỗi ở attempt đầu và thành công ở attempt thứ hai.

Lưu **NestedRetryAspectsDemo.java**:

~~~java
import java.util.List;

public class NestedRetryAspectsDemo {
    @FunctionalInterface
    interface Next {
        String proceed();
    }

    interface Around {
        String invoke(Next next);
    }

    static final class Trace implements Around {
        @Override
        public String invoke(Next next) {
            System.out.println("[trace] enter");
            String result = next.proceed();
            System.out.println("[trace] return " + result);
            return result;
        }
    }

    static final class RetryOnce implements Around {
        @Override
        public String invoke(Next next) {
            System.out.println("[retry] attempt 1");
            try {
                return next.proceed();
            } catch (IllegalStateException failure) {
                System.out.println("[retry] caught "
                        + failure.getClass().getSimpleName());
            }
            System.out.println("[retry] attempt 2");
            return next.proceed();
        }
    }

    static final class Observer implements Around {
        @Override
        public String invoke(Next next) {
            System.out.println("[observer] enter");
            try {
                String result = next.proceed();
                System.out.println("[observer] return " + result);
                return result;
            } catch (RuntimeException failure) {
                System.out.println("[observer] throw "
                        + failure.getClass().getSimpleName());
                throw failure;
            } finally {
                System.out.println("[observer] finally");
            }
        }
    }

    static final class Business {
        private int calls;

        String execute() {
            int n = ++calls;
            System.out.println("[business] attempt " + n);
            if (n == 1) {
                throw new IllegalStateException("temporary");
            }
            return "ok-" + n;
        }

        int calls() {
            return calls;
        }
    }

    static String run(List<Around> chain, int index, Next original) {
        if (index == chain.size()) {
            return original.proceed();
        }
        return chain.get(index).invoke(
                () -> run(chain, index + 1, original));
    }

    public static void main(String[] args) {
        Business business = new Business();
        List<Around> chain = List.of(
                new Trace(),
                new RetryOnce(),
                new Observer());

        String result = run(chain, 0, business::execute);
        System.out.println("[caller] " + result);
        System.out.println("[count] original=" + business.calls());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac NestedRetryAspectsDemo.java
java NestedRetryAspectsDemo
~~~

**Stdout chính xác:**

~~~text
[trace] enter
[retry] attempt 1
[observer] enter
[business] attempt 1
[observer] throw IllegalStateException
[observer] finally
[retry] caught IllegalStateException
[retry] attempt 2
[observer] enter
[business] attempt 2
[observer] return ok-2
[observer] finally
[trace] return ok-2
[caller] ok-2
[count] original=2
~~~

### 15.1. Số lần của từng thành phần

| Thành phần | Số lần được vào |
|---|---:|
| Trace | 1 |
| RetryOnce | 1 |
| Observer | 2 |
| Original | 2 |

RetryOnce vào một lần, nhưng gọi continuation trong **hai attempts**. Observer nằm bên trong continuation nên được vào hai lần.

### 15.2. Đổi vị trí Retry làm thay đổi kết quả quan sát

Nếu Retry được đưa **ra ngoài Trace**, việc retry có thể khiến Trace được vào hai lần. Khi Trace ở ngoài Retry, nó ghi một entry cho cả request.

Sự khác biệt này phải phản ánh đúng **đơn vị quan sát**: một request hay một attempt.

### 15.3. Không đồng nhất continuation với gọi Original trực tiếp

Trong chương trình, RetryOnce gọi next, không tự gọi business.execute. Next chuyển tới Observer rồi mới tới Original. Đó là điều cốt lõi khi nhiều quanh advice cùng chọn điểm: các lớp trung gian có thể được chạy lại.

## 16. Before của hai aspect có thứ tự nào?

Nếu A-before và B-before cùng khớp J, cả hai có thể chạy trước phần gốc khi phần điều khiển thật sự tới chúng. Nhưng thứ tự A rồi B hay B rồi A phụ thuộc **quy tắc của engine**.

Không nên viết B-before giả định A-before luôn đã đặt correlation ID, trừ khi công cụ có quy tắc precedence rõ và kiểm thử bảo đảm quan hệ đó.

Nếu các aspect phụ thuộc chặt nhau, hãy cân nhắc một context owner duy nhất và cung cấp dữ liệu theo interface rõ, tránh để những aspect độc lập tranh quyền khởi tạo.

## 17. After của hai aspect: cần quan sát đúng exit

Với chuỗi quanh advice lồng nhau:

~~~text
A before
  B before
    Original
  B after
A after
~~~

Thứ tự after có thể **ngược** thứ tự before. Nhưng các công cụ khác nhau có semantics riêng cho after-returning, after-throwing, finally và thứ tự advice trong cùng aspect.

Khi thử nghiệm, nên xác minh:

- Advice nào thực sự bao ngoài?
- Ai nhìn thấy return value trước khi bị biến đổi?
- Exception nào đi qua ranh giới của ai?
- Cleanup lỗi có thay lỗi gốc không?
- Có advice nào chỉ chạy ở normal return nhưng test lại dùng exceptional exit?

Không kết luận thứ tự exit chỉ từ tên loại advice.

## 18. Normal return không đồng nghĩa nghiệp vụ thành công

Một method có thể trả kết quả bình thường biểu thị DECLINED hoặc INVALID. Một after-returning advice có thể ghi “returned normally”, trong khi policy nghiệp vụ phân loại trạng thái là “failed”.

Hai mô tả không mâu thuẫn nếu ranh giới của chúng khác nhau.

Tương tự, một method trả về Future/CompletionStage có thể đã hoàn tất **lời gọi Java** trong khi công việc bất đồng bộ còn chạy. Nếu tracing muốn đo end-to-end task, phải quan sát completion event, không chỉ return của method.

Một aspect không nên tự suy thành công nghiệp vụ chỉ từ tên method hoặc việc không thấy exception.

## 19. Một method có thể liên quan nhiều join point

Một số mô hình AOP phân biệt:

- **Method call join point:** hoạt động ở call site bên caller.
- **Method execution join point:** hoạt động khi phần thân method được thực thi.

Hai aspect in cùng method name chưa chắc cùng khớp đúng một join point. Một aspect có thể chọn call site, aspect kia chọn execution.

~~~text
Caller call site ----> Target method execution
     Aspect A                    Aspect B
~~~

Đây là **hai loại điểm** liên quan cùng operation, không mặc định là một điểm duy nhất.

Để phân tích overlap phải xác định loại join point, chữ ký đầy đủ, declaring type, thời điểm và ngữ cảnh runtime phù hợp, không chỉ dòng log có tên pay.

## 20. Một aspect có thể có nhiều advice khớp cùng J

Giả sử Aspect A có:

- Before advice trên pay.
- After-returning advice trên pay.
- Around advice trên pay.

Aspect B lại có một around advice trên pay. Tổng cộng có **bốn khai báo advice** liên quan, không phải chỉ hai do có hai aspect.

Các câu hỏi cần kiểm tra:

1. Quy tắc giữa advice của **cùng aspect** là gì?
2. Quy tắc precedence **giữa các aspect** là gì?
3. Có advice nào không chạy ở exceptional exit?
4. Có short-circuit hoặc multiple proceed?
5. Có policy chỉ chọn một số lần gọi do dynamic condition không?

Không xây sơ đồ chỉ có A rồi B nếu trong A còn nhiều advice cần được sắp xếp.

## 21. Hai aspect cùng thay đổi đối số

Nếu Aspect A chuẩn hóa số liệu và Aspect B xác nhận chữ ký của dữ liệu đầu vào, thứ tự có thể ảnh hưởng kết quả.

~~~text
Original input
    |
    A normalizes
    |
    B validates transformed input
    |
    Original
~~~

Khác với B kiểm tra **input gốc** rồi A mới chuẩn hóa.

Nếu một engine cho phép truyền đối số mới xuống continuation, cần quy định rõ:

- Aspect nào nhìn thấy raw input?
- Aspect nào nhìn thấy transformed input?
- Validation diễn ra trước hay sau biến đổi?
- Ai chịu trách nhiệm bảo toàn hợp đồng kiểu?
- Có dữ liệu nhạy cảm nào không nên chuyển xuống một policy quan sát?

Không phải mọi engine đều cho phép thay tham số theo cùng cách; cần tuân thủ API và join point model tương ứng.

## 22. Cùng ghi log không nhất thiết là sự kiện bị lặp

Nếu tracing ghi ENTER còn audit ghi APPROVED, đó là hai sự kiện khác semantics. Nếu hai aspect cùng ghi **một** sự kiện AUDIT_COMPLETED không phân biệt, người sử dụng có thể đếm trùng.

Các nguyên nhân của “hai log cho một thao tác” có thể gồm:

- Hai aspect cùng ghi một loại event.
- Hai advice trong một aspect.
- Hai lớp proxy lồng nhau.
- Một retry ở ngoài logging.
- Một lời gọi business lồng nhau hoặc recursive.
- Một logger/sink phát hai bản ghi.

Không thể chỉ nhìn số log để kết luận Original chạy hai lần.

### 22.1. Định nghĩa event ownership

Một cách phối hợp tốt là quy định **một owner chịu trách nhiệm phát từng loại event**. Các aspect khác có thể cung cấp metadata hoặc phát event khác loại. Khi cần chống trùng ở mức request, phải có một correlation key và hợp đồng uniqueness phù hợp, không dựa trên method name ngắn.

## 23. Shared context giữa các aspect

Nhiều aspect có thể cần chung correlation ID, operation descriptor hoặc một snapshot ngữ cảnh. Tuy nhiên dùng **biến static mutable currentRequest** tạo nguy cơ trộn dữ liệu giữa nhiều thread.

Nên xác định:

- State nào là **per-invocation**.
- State nào là **per-object** nếu công cụ hỗ trợ.
- State nào là **per-control-flow**.
- State nào là **singleton**.
- Context nào cần lan truyền qua async boundary.

Với lời gọi lồng nhau, một ThreadLocal đơn giản phải có giao thức **lưu và phục hồi** trong finally, tránh làm mất context của lời ngoài. Với async, ThreadLocal không tự đảm bảo lan truyền sang thread khác.

Không đưa toàn bộ raw join point hoặc mảng đối số mutable vào nhiều aspect khi chỉ cần các trường đã chuẩn hóa và che dữ liệu nhạy cảm.

## 24. Transaction, resource và thứ tự policy

Hai around aspect cùng kiểm soát transaction/resource có thể tạo cấu trúc:

~~~text
Transaction A starts
    Transaction B starts
        Original executes
    Transaction B ends
Transaction A ends
~~~

Sơ đồ không đủ để suy rằng có hai transaction thật hoặc rollback/commit hoạt động theo kiểu nào. Nó phụ thuộc transaction manager, propagation semantics và chính sách.

Cần làm rõ:

- Ai thực sự sở hữu transaction boundary?
- Retry nằm trong hay ngoài transaction?
- Có aspect nào chỉ tham gia transaction đã có?
- Nếu inner lỗi và outer catch, trạng thái transaction có còn hợp lệ?
- Cleanup của mỗi resource phải chạy khi nào?

Không mặc định thứ tự around nesting tương đương atomicity hoặc isolation.

## 25. Tính giao hoán: đổi thứ tự có làm thay kết quả không?

Hai policy độc lập **có thể giao hoán** trong những điều kiện hẹp, ví dụ cả hai chỉ tăng những counter độc lập, không ném lỗi, không short-circuit và không thay return.

Nhưng một chính sách retry, cache, transform hoặc exception conversion thường có thể làm thứ tự trở nên quan trọng.

Phân tích:

~~~text
A(B(J))  versus  B(A(J))
~~~

So sánh về:

- Return value và ngoại lệ caller thấy.
- Số lần Original thật sự chạy.
- Tác dụng phụ.
- Audit/metrics/tracing events.
- Resource/transaction scope.
- Dữ liệu mà mỗi policy nhìn thấy.
- Chi phí thực thi.

Nếu hai thứ tự khác nhau theo yêu cầu quan trọng, cần **khai báo và kiểm thử thứ tự** hoặc tái thiết kế để loại bỏ phụ thuộc.

## 26. Rủi ro recursion khi các aspect gọi chéo nhau

Một audit advice gọi AuditSink.write, nhưng pointcut logging lại chọn cả AuditSink.write. Có thể sinh vòng:

~~~text
Audit advice
   → AuditSink.write
       → Audit advice
           → AuditSink.write
               → ...
~~~

Một aspect khác có thể khiến vòng lặp phức tạp hơn, ví dụ metrics gọi logger còn logger được tracing advice bao lại.

Biện pháp:

- Loại trừ mã hạ tầng của aspect khỏi pointcut khi phù hợp.
- Tránh gọi lại chính lời gọi đang bị chặn thay cho continuation.
- Nếu dùng guard reentrancy, định nghĩa scope rõ và cleanup trong finally.
- Không dùng một boolean global cho mọi thread.
- Kiểm thử cả đường ném ngoại lệ và lời gọi lồng nhau.

Một vòng recursion không nhất thiết là lỗi weaving; nó có thể là hiệu ứng **đúng theo pointcut nhưng sai theo thiết kế nghiệp vụ quan sát**.

## 27. Lỗi advice có thể phá nghiệp vụ gốc

Một aspect dùng để logging nhưng tự ném exception khi định dạng đối số. Nếu advice chạy trước Original, nghiệp vụ có thể **không được gọi**. Nếu logger ném trong finally, lỗi gốc có thể bị che.

Do đó cần định nghĩa chính sách:

- Logging/metrics **best-effort** có được phép thất bại ảnh hưởng caller không?
- Audit bắt buộc nên fail-open hay fail-closed trong điều kiện nào?
- Ai sở hữu quyết định **không gọi proceed**?
- Có được phép convert exception không?
- Có cần ghi nhận thất bại của sink qua kênh riêng không?

Một bộ catch-all bỏ mọi lỗi không thích hợp cho mọi loại aspect, nhất là chính sách kiểm soát bắt buộc. Nhưng một observer thuần túy cũng không nên ngẫu nhiên biến operation thành thất bại chỉ vì logger thiếu tài nguyên.

## 28. Hiệu năng của nhiều aspect cùng khớp

Mỗi advice có thể thêm:

1. Kiểm tra pointcut động.
2. Dispatch qua proxy/bytecode hook.
3. Đọc signature hoặc runtime args.
4. Tạo context snapshot.
5. Logging hoặc metrics I/O.
6. Lock hoặc synchronized state.
7. Allocation và GC.
8. Retry hoặc recursive invocation ngoài ý muốn.

Chi phí tổng **không đơn giản luôn bằng tổng chi phí riêng lẻ**. Các aspect có thể tranh lock, nhân số attempts, lặp serialization hoặc tăng áp lực GC.

Để đánh giá đúng, đo trên **composition đầy đủ với precedence thật**, workload hợp lý và ranh giới instrumentation thực tế. Không chỉ benchmark từng aspect độc lập rồi suy tổng là chính xác trong mọi tình huống.

### 28.1. Không lấy mọi đối số để log

Khi nhiều aspect cùng truy cập raw arguments, khả năng lộ token, account ID hoặc dữ liệu cá nhân tăng. Nên có allowlist, masking, giới hạn kích thước và tránh toString trên object tùy ý.

Sở hữu metadata join point không đồng nghĩa được phép lưu vô hạn mọi dữ liệu runtime quan sát được.

## 29. Ma trận kiểm thử phối hợp nhiều aspect

| Ca | Điều cần xác minh |
|---|---|
| J khớp cả A và B | Cả hai có thể chạy khi chain không bị chặn |
| J chỉ khớp A | B không chạy |
| Điều kiện động B sai | Không nhầm với lỗi weaving |
| A bao ngoài B | Enter/exit theo đúng precedence |
| Outer Guard chặn | Inner không chạy ngoài chủ đích |
| Original trả bình thường | Return value bảo toàn nếu chỉ observer |
| Original ném lỗi | Mỗi lớp thấy lỗi theo ranh giới của nó |
| Inner bắt lỗi và trả fallback | Outer có thể thấy normal return |
| Inner chuyển exception | Outer thấy exception đã chuyển |
| Inner biến đổi kết quả | Outer nhận giá trị mới |
| Retry gọi next hai lần | Số lần inner advice và Original phù hợp |
| Audit yêu cầu một event mỗi request | Không bị nhân theo số attempts |
| Gọi trực tiếp target | Độ bao phủ đúng cơ chế proxy/weaving |
| Lời gọi lồng nhau | Context không bị ghi đè |
| Đồng thời nhiều thread | Không trộn state hoặc correlation |
| Async return | Đúng mốc hoàn tất cần đo |
| Logger trong finally bị lỗi | Chính sách bảo toàn lỗi gốc |
| Thêm aspect thứ ba | Không phá giả định về order/side effects |

Một unit test của từng advice **không thay thế** integration test toàn bộ chain. Cần cả **test dương và âm của pointcut** cùng kiểm tra số lần phần gốc thực thi.

## 30. Quy trình chẩn đoán khi thiếu hoặc thừa advice

1. Xác định **loại join point** chính xác.
2. Xác nhận operation và chữ ký thực tế.
3. Liệt kê các pointcut cùng khớp về cấu trúc.
4. Kiểm tra điều kiện động ở lần gọi cụ thể.
5. Kiểm tra phạm vi weaving hoặc proxy path.
6. Liệt kê mọi advice, không chỉ tên aspect.
7. Ghi precedence/ordering thực tế.
8. Kiểm tra short-circuit.
9. Kiểm tra multiple proceed/retry.
10. Kiểm tra exception conversion hoặc fallback.
11. Phân biệt original count với advice count.
12. Kiểm tra log sink có bị lọc, lỗi hoặc nhân bản.
13. Kiểm tra recursion và calls nội bộ.
14. Kiểm tra state dùng chung, concurrency, async.
15. Rút thành một ca tái hiện tối thiểu, sửa từng biến một.

Không sửa cùng lúc pointcut, ordering và error handling: khi nhiều biến thay đổi, rất khó xác định nguyên nhân thực.

## 31. Sai lầm thường gặp

**Sai lầm 1: Hai aspect cùng khớp thì cả hai chắc chắn chạy.** Around ngoài có thể short-circuit trước khi vào inner.

**Sai lầm 2: Thứ tự phụ thuộc tên file hay thứ tự class.** Không phải quy tắc AOP chung; phải xem precedence được engine cam kết.

**Sai lầm 3: Proceed gọi một lần thì Original chạy một lần.** Inner có thể bỏ qua hoặc retry.

**Sai lầm 4: Every after chạy theo thứ tự before.** Wrapper lồng nhau thường có exit đảo lại, còn loại after advice chịu semantics riêng.

**Sai lầm 5: Cùng tên method nghĩa là cùng join point.** Call và execution khác loại; overload và call site còn khác nhau.

**Sai lầm 6: Hai dòng audit có nghĩa hai business executions.** Có thể do hai aspect hoặc một advice phát hai event.

**Sai lầm 7: Đặt audit bên trong guard nhưng vẫn muốn ghi mọi yêu cầu từ chối.** Guard có thể chặn trước khi audit được vào.

**Sai lầm 8: Đo latency ở trong cache rồi gọi là client latency.** Ranh giới đo không bao cả cache-hit.

**Sai lầm 9: Retry luôn an toàn.** Side effect có thể xảy ra trước khi lỗi được ném; retry có thể nhân giao dịch.

**Sai lầm 10: Không thấy advice là lỗi pointcut.** Có thể do proxy bypass, class ngoài weaving, outer short-circuit hoặc log bị lọc.

**Sai lầm 11: Cho mọi aspect đọc raw args.** Tăng rủi ro quyền riêng tư và chi phí.

**Sai lầm 12: Dùng static currentRequest giữa nhiều aspect.** Lời gọi đồng thời có thể trộn dữ liệu.

**Sai lầm 13: Test mỗi aspect riêng lẻ là đủ.** Phụ thuộc thứ tự và số lần sẽ chỉ xuất hiện khi kết hợp.

**Sai lầm 14: Aspect quan sát không thể gây lỗi nghiệp vụ.** Advice/cleanup tự ném exception có thể thay hành vi caller thấy.

## 32. Checklist thiết kế trước khi thêm aspect mới

1. Join point nào được chọn và thuộc loại điểm nào?
2. Những aspect nào đã chọn điểm đó?
3. Pointcut của aspect mới có giao với những pointcut nào?
4. Có điều kiện động làm số aspect khớp thay đổi theo input không?
5. Precedence được công cụ bảo đảm hay đang dựa mặc định?
6. Những around advice nào có thể short-circuit?
7. Những advice nào có quyền gọi continuation nhiều lần?
8. Return value có bị thay đổi không?
9. Exception có bị bắt, chuyển đổi hoặc che mất không?
10. Audit đang theo **request**, **attempt** hay **execution**?
11. Metrics đo tổng thời gian ngoài hay thời gian của một phần trong?
12. Có event nào bị phát trùng bởi hai aspect?
13. Context được tạo và truyền theo phạm vi nào?
14. Có nguy cơ self-invocation, recursion hoặc logging loop?
15. Có dữ liệu nào không được lộ cho aspect khác không?
16. Có integration test cho cả chain, đường lỗi và đường thành công không?
17. Có test short-circuit và retry kiểm tra chính xác số lần Original không?
18. Có kiểm thử concurrency và async khi phù hợp không?
19. Có đo overhead với tất cả aspect đang bật không?
20. Có thể giải thích mỗi log/metric từ đúng ranh giới quan sát không?

## 33. Câu hỏi tự kiểm tra

### Câu 1 — Giao pointcut

A chọn mọi execution trên PaymentService, B chọn execution pay. Một lần execution pay có thể được cả hai chọn?

**Đáp án:** có. Nhưng nếu outer advice chặn trước, một trong các advice phía trong có thể không chạy.

### Câu 2 — Thứ tự enter/exit

A bao ngoài B theo around wrapper. Original thành công. Thứ tự thông thường?

**Đáp án:** A enter, B enter, Original, B exit, A exit.

### Câu 3 — Guard trước Audit

Guard từ chối mà không gọi continuation, Audit nằm trong. Có Audit event không?

**Đáp án:** thông thường không. Muốn audit yêu cầu bị từ chối phải dùng boundary phù hợp.

### Câu 4 — Retry bên trong Trace

Trace ngoài, Retry giữa, Observer trong. Retry gọi phần trong hai lần. Trace/Observer vào bao nhiêu lần ở ví dụ?

**Đáp án:** Trace một lần, Observer hai lần, Original hai lần.

### Câu 5 — Return transformation

Original trả 5; AddOne cộng một, Double nhân đôi. Đổi thứ tự có thể thay kết quả?

**Đáp án:** có: AddOne(Double(5))=11, Double(AddOne(5))=12.

### Câu 6 — Exception conversion

Original ném lỗi E, Inner bắt rồi trả fallback. Outer after-throwing có chắc thấy E?

**Đáp án:** không. Outer có thể chỉ thấy normal return của Inner.

### Câu 7 — Hai dòng log

Một request sinh hai log. Có chắc Original chạy hai lần?

**Đáp án:** không. Có thể hai aspect khác nhau hoặc nhiều advice ghi sự kiện cho cùng execution.

### Câu 8 — Call và execution

A chọn method call; B chọn method execution của cùng tên pay. Có chắc cùng chọn đúng một join point?

**Đáp án:** không khi mô hình phân biệt các loại điểm. Đây có thể là hai join point liên quan nhưng khác nhau.

### Câu 9 — Precedence mặc định

A được đặt tên đứng trước B theo alphabet. Có chắc A chạy trước B?

**Đáp án:** không. Thứ tự cần được engine AOP định nghĩa và kiểm thử.

### Câu 10 — Retry và idempotency

Một around retry gọi next hai lần, attempt đầu đã có side effect trước khi lỗi. Rủi ro?

**Đáp án:** side effect có thể bị lặp; cần policy retry, transaction và idempotency phù hợp.

### Câu 11 — Timing và cache

Timing ở ngoài Cache, Cache trả sớm. Timing vẫn ghi thời lượng còn Original không chạy. Có sai không?

**Đáp án:** không nếu metric là độ trễ ranh giới ngoài. Nếu metric được hứa là thời gian Original thì cách đo không đúng phạm vi.

### Câu 12 — Shared static context

A ghi currentUser vào biến static, B đọc; hai thread chạy đồng thời. Rủi ro?

**Đáp án:** dữ liệu các invocation có thể trộn; cần context theo scope thích hợp và quy tắc truyền/cleanup rõ.

## 34. Kết luận

**Một join point đồng thời phù hợp với nhiều aspect** nghĩa là có nhiều pointcut cùng chọn một điểm trong miền join point của mô hình AOP. Để hiểu hành vi cuối cùng, còn phải phân tích **thứ tự advice, cấu trúc bao quanh, điều kiện động, quyền tiếp tục, ngoại lệ và những biến đổi được phép**.

Các nguyên tắc quan trọng:

- **Pointcut overlap là bình thường**, nhưng các chính sách cần có trách nhiệm riêng và hợp đồng phối hợp.
- **Match không bảo đảm mọi advice thực thi**, do short-circuit và phạm vi runtime.
- **Precedence ảnh hưởng cả enter và exit**, đôi khi ảnh hưởng kết quả, lỗi và phạm vi quan sát.
- **Proceed không mặc nhiên gọi thẳng Original**; nó có thể đi qua các advice phía trong.
- **Retry có thể nhân số invocation của inner advice và Original** mà outer advice vẫn chỉ chạy một lần.
- **Exception và return value có thể được chuyển đổi nhiều lớp**; mỗi aspect quan sát dữ liệu ở ranh giới riêng.
- **Request, attempt, advice invocation và business execution** là các đơn vị cần phân biệt khi ghi metrics và audit.
- **Không dùng thứ tự không được cam kết** làm điều kiện đúng đắn; phải kiểm thử toàn bộ chain trong môi trường và cơ chế thực tế.
- **Bảo vệ dữ liệu và bảo toàn hành vi nghiệp vụ** vẫn là trách nhiệm khi nhiều aspect cùng tác động.

**Câu hỏi quyết định trước khi thêm aspect:** *Nếu aspect này được chèn vào chuỗi, nó có thể chặn, lặp, biến đổi hoặc làm thay đổi những gì các aspect khác và caller quan sát hay không?*

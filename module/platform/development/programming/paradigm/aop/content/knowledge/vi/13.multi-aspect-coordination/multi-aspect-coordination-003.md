# Chuỗi advice bao quanh và thứ tự tháo lớp khi trả về

## 1. Bài toán: nhiều aspect bao cùng một điểm thực thi

Trong **Aspect-Oriented Programming (AOP)**, một **pointcut** chọn các *join point* mà công nghệ AOP có thể can thiệp; **advice** là hành vi chạy ở các điểm được chọn. Một aspect có thể chứa một hay nhiều pointcut/advice. Khi **nhiều aspect hoặc nhiều around advice cùng áp dụng lên một lời gọi**, chúng thường kết hợp thành **chuỗi bao quanh (nested advice chain)**.

Hãy hình dung một thao tác `placeOrder()` cần các concern:

- **Tracing**: mở và đóng một phạm vi quan sát.
- **Authorization**: kiểm tra quyền truy cập.
- **Retry**: thử lại theo chính sách có giới hạn.
- **Audit**: ghi sự kiện bắt đầu, thành công hoặc thất bại.
- **Metrics**: đo latency.

Mỗi concern có thể được cài bằng một around advice, nhưng kết quả cuối không chỉ phụ thuộc **có những advice nào**. Nó còn phụ thuộc **thứ tự lồng nhau**: advice nào ở ngoài, advice nào ở trong, advice nào quyết định gọi `proceed()`, và advice nào xử lý **giá trị trả về hoặc ngoại lệ khi luồng rút ra**.

Ý tưởng trọng tâm:

> Với chuỗi around advice lồng nhau, đi vào theo thứ tự **ngoài → trong → target**; khi các lời gọi chuyển tiếp hoàn tất bình thường, luồng rút ra theo thứ tự **target → trong → ngoài**. Mỗi advice có thể thực hiện hành vi sau `proceed()`, biến đổi kết quả, chốt `finally`, hoặc ném lại/biến đổi ngoại lệ theo hợp đồng riêng.

Điều này thường được gọi là **nested wrappers**, **interceptor chain** hoặc “mô hình củ hành”: các lớp vào theo chiều này và tháo ra theo chiều ngược lại.

**Quan trọng:** không phải mọi engine AOP có cú pháp `proceed` giống nhau, cũng không có một quy tắc thứ tự các aspect phổ quát. Mô hình này đúng khi chuỗi đã được ghép thành các around wrappers lồng nhau. Precedence thực tế phải căn cứ vào **quy tắc và cấu hình của công cụ đang dùng**.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa và vai trò |
| --- | --- |
| **Join point** | Một vị trí/sự kiện được mô hình AOP hỗ trợ, ví dụ method execution |
| **Pointcut** | Quy tắc chọn tập join point |
| **Advice** | Hành vi thực hiện tại join point được chọn |
| **Around advice** | Advice có thể làm việc trước/sau, chuyển tiếp hoặc chủ động thay đổi luồng gọi |
| **`proceed()`** | Thao tác chuyển tới lớp bên trong/target theo API của công cụ |
| **Outer advice** | Advice bao bên ngoài những lớp còn lại |
| **Inner advice** | Advice được gọi bởi một outer advice và đứng gần target hơn |
| **Precedence** | Quy tắc quyết định thứ tự và quan hệ lồng các advice |
| **Unwinding** | Quá trình rút ngăn xếp khi kết quả hoặc lỗi đi ngược lên |
| **Normal completion** | Một lớp hoàn tất bằng cách trả một giá trị hợp lệ |
| **Exceptional completion** | Một lớp kết thúc bằng ngoại lệ thoát ra |
| **Short-circuit** | Advice chủ động trả kết quả hoặc ném lỗi mà không gọi lớp kế tiếp |
| **Reentrant/retry** | Lớp điều khiển có thể đi vào chuỗi dưới nhiều lần hoặc gọi tiếp nhiều lần |

**Thứ tự khai báo trong source không nhất thiết là precedence.** Một engine có thể dùng chỉ thị order, type hierarchy, độ ưu tiên pointcut, thứ tự interceptor đăng ký hoặc những quy tắc khác. Chỉ khi **đã xác định outer/inner thật sự**, ta mới suy ra thứ tự vào và thứ tự rút ra.

## 3. Mô hình củ hành với ba lớp

Giả sử có ba around advice được lồng như sau:

~~~text
Caller
  |
  v
[A OUTER]
  |
  +-- A.before
  |
  +-- proceed() ---------> [B MIDDLE]
  |                         |
  |                         +-- B.before
  |                         |
  |                         +-- proceed() ----> [C INNER]
  |                         |                     |
  |                         |                     +-- C.before
  |                         |                     +-- proceed() --> TARGET
  |                         |                     +-- C.after / finally
  |                         |
  |                         +-- B.after / finally
  |
  +-- A.after / finally
  |
  v
Caller nhận result hoặc exception
~~~

Với target trả bình thường và cả ba advice đều chuyển tiếp **đúng một lần**:

~~~text
A before
B before
C before
TARGET
C after
B after
A after
CALLER
~~~

Sự đối xứng này là hệ quả của **hàm bao hàm hàm**:

~~~text
A( B( C( TARGET ) ) )
~~~

Ta **không** gọi `A.after` ngay sau `A.before`, bởi vì `A` đang chờ `B` hoàn tất trong `proceed()`. Tương tự, `B` đang chờ `C`, và `C` đang chờ target.

Nếu advice chứa `finally`, `finally` của lớp trong sẽ thực hiện khi scope của lớp trong rời đi, **trước** khi `proceed()` tương ứng trả hoặc ném lỗi lên lớp ngoài. Vì vậy thứ tự của riêng các `finally` cũng thường **trong → ngoài**.

## 4. Nhìn qua call stack để không nhầm “tháo lớp”

Ở thời điểm cả ba advice đã vào và target đang chạy, ngăn xếp thực thi có thể trông như sau:

~~~text
TOP
  target.run()
  C.around()  -- đang chờ target
  B.around()  -- đang chờ C.proceed
  A.around()  -- đang chờ B.proceed
  caller()
BOTTOM
~~~

Khi `target.run()` trả một kết quả:

1. Kết quả trở lại **C**, không đi thẳng tới caller.
2. C có thể xử lý kết quả, trả result mới hoặc gốc; trước khi rời C thì `finally` của C chạy.
3. Result trở lại **B**; B lại có quyền xử lý result, rồi rời scope B.
4. Result trở lại **A**; A xử lý, rồi rời scope A.
5. Caller cuối cùng mới nhận giá trị.

Đây là ý nghĩa thực dụng của “thứ tự tháo lớp khi trả về”. Cùng một result **có thể có ba phiên bản** tại ba ranh giới khác nhau.

Ví dụ:

~~~text
TARGET -> "ok"
INNER  -> "ok!"
OUTER  -> "[ok!]"
CALLER -> "[ok!]"
~~~

Nếu advice chỉ quan sát mà không biến đổi thì các ranh giới có thể thấy cùng giá trị, nhưng thứ tự callback vẫn đảo chiều.

### 4.1. Vì sao `after` khác `finally`?

Trong Java:

~~~java
try {
    Object result = next.proceed();
    observeReturn(result);
    return result;
} finally {
    releaseScope();
}
~~~

Đây là đoạn minh họa, chưa độc lập vì `next`, `observeReturn` và `releaseScope` là các thành phần do ứng dụng cung cấp.

Nếu `next.proceed()` trả bình thường, `observeReturn` chạy rồi `finally` mới giải phóng scope. Nếu `next.proceed()` ném exception, `observeReturn` **bị bỏ qua**, nhưng `releaseScope` trong `finally` vẫn chạy khi phạm vi rời đi.

Vì thế:

- **After returning logic**: chạy trên đường bình thường của lớp mà nó quan sát.
- **After throwing logic**: chạy trên đường exceptional exit được bắt hoặc được engine cung cấp.
- **Finally-style logic**: chạy khi phạm vi kết thúc theo cả hai đường thông thường của Java.

Không nên gọi mọi đoạn code “sau target” là after-returning, vì `finally` có ngữ nghĩa khác.

## 5. Đường trả về bình thường: outer thấy kết quả đã được inner xử lý

Giả sử:

~~~text
A around: add "[" + value + "]"
B around: uppercase(value)
C around: add "!"
TARGET:   return "hello"
~~~

Với cách lồng `A(B(C(TARGET)))`:

~~~text
TARGET produces "hello"
C sees "hello", returns "hello!"
B sees "hello!", returns "HELLO!"
A sees "HELLO!", returns "[HELLO!]"
CALLER sees "[HELLO!]"
~~~

Kết quả **không tương đương** với việc đổi thứ tự tự do. Nếu `uppercase` và thêm ngoặc có những quy tắc riêng, hai phép biến đổi có thể hoặc không thể giao hoán. Đặc biệt các phép biến đổi như mã hóa, nén, ký số hoặc chuẩn hóa dữ liệu thường **không giao hoán**.

Đây là lý do precedence phải là một **phần của hợp đồng**, không phải chi tiết do runtime tình cờ quyết định.

### 5.1. Giá trị target, giá trị observed và giá trị caller

Có thể đặt ba tên:

- `rawResult`: giá trị target trả.
- `innerResult`: giá trị sau một hoặc nhiều advice bên trong.
- `callerResult`: giá trị sau advice ngoài cùng.

Một advice ở lớp trong có thể ghi `rawResult=hello`; lớp ngoài log `innerResult=HELLO!`; caller thấy `[HELLO!]`.

Nếu audit cần ghi **kết quả đã được công bố tới caller**, nên đặt audit ở ranh giới quan sát thích hợp; nếu audit cần ghi **result gốc của target**, phải đặt bên trong lớp biến đổi phù hợp. Không dùng tên `originalResult` cho kết quả vốn đã đi qua các transformer khác.

### 5.2. Tác dụng phụ trên object mutable

Ngay cả khi advice “trả cùng object” nhưng thay đổi nội dung của `List` hoặc DTO mutable, giá trị caller quan sát có thể đã thay đổi. Đây là một **biến đổi trạng thái**, không còn là quan sát thuần túy.

Với advice chỉ đo/log, ưu tiên không sửa result và không gọi `toString()` có thể gây I/O, lộ dữ liệu hoặc ném exception; chỉ ghi metadata được phép.

## 6. Đường ngoại lệ: tháo lớp cũng đi từ trong ra ngoài

Giả sử target ném `IllegalArgumentException`. Nếu cả ba around advice đều chỉ ghi lỗi rồi **ném lại nguyên exception**:

~~~text
A before
B before
C before
TARGET -> throws IllegalArgumentException
C catches/observes error
C finally
B catches/observes error
B finally
A catches/observes error
A finally
CALLER catches IllegalArgumentException
~~~

Điểm khác biệt so với normal return:

- Những câu lệnh chỉ chạy khi `proceed()` trả bình thường bị **bỏ qua**.
- Các `catch` thích hợp có thể quan sát hoặc biến đổi exception.
- Các `finally` được thực thi khi rời scope (trừ những tình huống dừng tiến trình bất thường không bảo đảm cleanup).
- Một lớp ngoài có thể nhận **ngoại lệ đã biến đổi** bởi lớp trong, không nhất thiết lỗi gốc từ target.
- Nếu một lớp **bắt lỗi và trả fallback**, những lớp ngoài hơn có thể nhìn thấy **normal return** thay vì exceptional exit.

Vì vậy lời khẳng định “target lỗi thì tất cả after-throwing advices chắc chắn chạy” là **quá mạnh**. Nếu một advice bên trong phục hồi bằng fallback, lớp ngoài không còn thấy exception ở ranh giới `proceed` tương ứng.

### 6.1. Ví dụ phục hồi thay đổi kịch bản

~~~text
OUTER audit
  INNER fallback
    TARGET -> throws IOException

INNER catch -> return "cached-value"
OUTER proceed() returns "cached-value"
OUTER after-returning runs
CALLER receives "cached-value"
~~~

Nếu audit bên ngoài ghi “target thành công” chỉ từ việc `proceed()` trả bình thường, nó có thể diễn giải sai **nghiệp vụ gốc đã thất bại nhưng được fallback khôi phục**. Cần phân biệt `normal completion of wrapper` với `business success of target`.

### 6.2. Khi `finally` tự ném exception

Nếu một advice đang tháo lớp vì lỗi nghiệp vụ mà `finally` tự ném lỗi metrics/cleanup, caller có thể nhận **lỗi mới thay vì lỗi gốc**. Dọn dẹp không tự an toàn chỉ vì đặt trong `finally`.

Với tài nguyên Java `AutoCloseable` dùng qua `try-with-resources`, exception do `close()` có thể được gắn **suppressed** khi đã có exception chính. Nhưng nếu tự viết `finally` ném một exception khác, hợp đồng và kết quả có thể khác. Hãy lựa chọn chính sách rõ, thử cả đường success và failure.

## 7. Thứ tự cố định của cấu trúc và thứ tự tùy thuộc precedence

Đối với một chuỗi wrapper **đã xây dựng xong**, Java call stack và `try/finally` tuân theo thứ tự vào/rút ra tương ứng. Nhưng câu hỏi **advice nào là outer** không có một câu trả lời toàn cục cho tất cả AOP engines.

Có thể tồn tại:

- Explicit order/priority của advice hoặc aspect.
- Thứ tự các interceptor khi đăng ký vào chain.
- Quy tắc phân giải ưu tiên khi nhiều aspect cùng chọn một join point.
- Thứ tự của những method được sinh hoặc woven vào call/execution.
- Quy tắc riêng giữa các advice cùng aspect hoặc cùng precedence.
- Trường hợp thứ tự không được bảo đảm, có thể thay đổi giữa versions/configs.

**Không suy ra precedence từ tên class, tên file, thứ tự khai báo hoặc thứ tự dependency** trừ khi tài liệu công nghệ thực sự quy định. Đặc biệt không coi số priority nhỏ luôn là outer: một số hệ thống định nghĩa chiều ưu tiên khác.

Khi tài liệu dự án ghi `Trace → Auth → Business`, cần nói rõ đó là **thứ tự vào** hay **thứ tự lúc rút ra**. Một cách biểu diễn ít mơ hồ:

~~~text
OUTER Trace {
    MIDDLE Auth {
        INNER Metrics {
            Business
        }
    }
}
~~~

Khi đó ý nghĩa “before” và “after” đã rõ mà không cần biết API sắp xếp của công cụ nào.

## 8. Viết code rõ ràng theo cấu trúc `try / catch / finally`

Mẫu ý niệm cho một around advice:

~~~java
Object around(Proceed next) throws Throwable {
    before();
    try {
        Object value = next.proceed();
        afterReturning(value);
        return value;
    } catch (Throwable error) {
        afterThrowing(error);
        throw error;
    } finally {
        cleanup();
    }
}
~~~

**Đây là Java pseudocode minh họa**: `Proceed` và các hàm callback chưa được định nghĩa. Code chạy độc lập đầy đủ ở phần 10.

Ngữ nghĩa cần hiểu:

1. `before()` chạy trước vùng `try`. Nếu chính `before()` ném lỗi, `finally` bên trong cấu trúc này **chưa được vào**, nên không chạy. Nếu cần cleanup sau khi trước-call khởi tạo tài nguyên một phần, hãy bố trí `try` bao quanh phần cần bảo đảm.
2. `next.proceed()` là ranh giới gọi lớp trong. Nó có thể return hoặc throw.
3. `afterReturning(value)` trong `try` chỉ chạy nếu `proceed` return.
4. Nếu **chính `afterReturning` ném exception**, `catch (Throwable)` cũng sẽ bắt nó; không được nhầm với “target throw”. Trong design cần phân biệt nguồn lỗi hoặc chia các vùng `try/catch` cho rõ.
5. `cleanup()` trong `finally` chạy khi scope rời đi theo cơ chế Java bình thường.
6. Nếu `cleanup` lỗi, caller có thể mất result/exception ban đầu; cần policy cho cleanup.

### 8.1. Tránh catch mọi `Throwable` chỉ để ghi log

Một ví dụ chạy thử có thể bắt `Throwable` để **ném lại nguyên lỗi** và quan sát thứ tự. Trong production, `Error` cũng là `Throwable`: không nên nuốt `Error` hoặc biến mọi lỗi thành success. Nếu advice chỉ đo duration, có thể chỉ cần `try/finally` thay vì catch rộng.

### 8.2. `return` trong `finally` là một bẫy

~~~java
try {
    return "business-result";
} finally {
    return "overridden"; // Không làm như thế.
}
~~~

Đây là minh họa Java; nó cho thấy `return` trong `finally` có thể **thay thế kết quả trước đó**; nếu `try` đang ném exception, nó còn có thể **nuốt luôn exception**. Around advice cleanup nên thực hiện giải phóng/quan sát, không dùng `return` trong `finally`.

## 9. Vai trò của lời gọi `proceed`

Trong nhiều cách hiện thực AOP, `proceed` đại diện cho **thao tác chuyển tiếp vào thành phần bên trong chuỗi**. Nó không luôn trực tiếp gọi target ngay; trước target có thể còn nhiều lời gọi advice khác.

Ba trường hợp:

### 9.1. Gọi đúng một lần

~~~text
OUTER before
  proceed() --> INNER --> TARGET
OUTER after
~~~

Đây là dạng thường dùng cho logging, metrics và kiểm quyền khi đã cho phép truy cập.

### 9.2. Không gọi lần nào: short-circuit

~~~text
CACHE checks key
  hit -> return cached value immediately
  miss -> proceed()
~~~

Nếu cache nằm giữa OUTER và INNER, một cache hit có thể khiến **INNER và target không chạy**. Nhưng những advice **ngoài** cache vẫn có thể được kích hoạt và thấy cache result.

Vì vậy số lần `afterReturning` của OUTER không phải số lần target đã thực thi, trừ khi chain đảm bảo mọi đường đều gọi target.

### 9.3. Gọi nhiều lần: retry hoặc fan-out

~~~text
RETRY around
  attempt 1 -> proceed() -> exception
  attempt 2 -> proceed() -> value
  return value
~~~

Một outer advice bao retry có thể được vào một lần, trong khi inner advice và target chạy **hai lần**. Số lượng log/metrics tùy vị trí của advice:

- Timer **ngoài retry** đo toàn bộ request bao gồm mọi attempt và backoff.
- Timer **bên trong retry** có thể ghi một mẫu cho mỗi attempt.
- Audit **ngoài retry** có thể ghi outcome cuối; audit **bên trong** có thể ghi mỗi attempt.

Không giả định mọi công cụ AOP cho phép gọi `proceed` nhiều lần hoặc thay đổi arguments giống nhau; đó là capability/hợp đồng của engine và tác vụ. Với method có side effects, retry sai có thể tạo giao dịch trùng.

## 10. Ví dụ Java 17 hoàn chỉnh: outer, inner, ngoại lệ và short-circuit

Để học chính xác **vòng vào và thứ tự tháo lớp**, chương trình sau dùng các hàm Java lồng nhau, **không phụ thuộc vào framework AOP**:

- `Proceed` biểu thị lời gọi sang lớp kế tiếp.
- `Around` là hợp đồng của từng advice.
- `Layer` ghi `enter`, `returning`, `throwing` và `finally`.
- `execute()` lắp danh sách theo **thứ tự từ ngoài vào trong**, nhưng **duyệt ngược khi xây** để tạo được đúng chain.
- Lớp INNER thêm dấu `!` vào result; lớp OUTER thêm ngoặc vuông `[ ]`.
- Có một ca target ném `IllegalArgumentException` và một ca `CACHE` chủ động trả kết quả mà **không gọi `next.proceed()`**.
- Bộ đếm `TARGET_CALLS` chứng minh lượt cache hit không gọi target.

Tạo file `AroundChainDemo.java`:

~~~java
import java.util.List;
import java.util.function.UnaryOperator;

public final class AroundChainDemo {
    @FunctionalInterface
    interface Proceed { String proceed() throws Throwable; }

    @FunctionalInterface
    interface Around { String apply(Proceed next) throws Throwable; }

    static final class Core {
        int calls;
        String greet(String input) {
            calls++;
            System.out.println("TARGET greet " + input);
            if ("bad".equals(input)) {
                throw new IllegalArgumentException("invalid input");
            }
            return "core:" + input;
        }
    }

    record Layer(String name, UnaryOperator<String> transform) implements Around {
        @Override
        public String apply(Proceed next) throws Throwable {
            System.out.println(name + " enter");
            try {
                String result = next.proceed();
                System.out.println(name + " returning " + result);
                return transform.apply(result);
            } catch (Throwable error) {
                System.out.println(name + " throwing "
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                System.out.println(name + " finally");
            }
        }
    }

    static String execute(List<Around> outerToInner, Proceed core) throws Throwable {
        Proceed chain = core;
        for (int i = outerToInner.size() - 1; i >= 0; i--) {
            Around layer = outerToInner.get(i);
            Proceed next = chain;
            chain = () -> layer.apply(next);
        }
        return chain.proceed();
    }

    public static void main(String[] args) throws Throwable {
        Core core = new Core();
        Around outer = new Layer("OUTER", value -> "[" + value + "]");
        Around inner = new Layer("INNER", value -> value + "!");
        List<Around> normalChain = List.of(outer, inner);

        System.out.println("CALLER " +
                execute(normalChain, () -> core.greet("A")));

        try {
            execute(normalChain, () -> core.greet("bad"));
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER caught " + error.getMessage());
        }

        Around cacheHit = next -> {
            System.out.println("CACHE short-circuit");
            return "stored:B";
        };
        System.out.println("CALLER " +
                execute(List.of(outer, cacheHit, inner),
                        () -> core.greet("B")));
        System.out.println("TARGET_CALLS " + core.calls);
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 AroundChainDemo.java
java AroundChainDemo
~~~

Đầu ra **đã đối chiếu bằng biên dịch và chạy thực**:

~~~text
OUTER enter
INNER enter
TARGET greet A
INNER returning core:A
INNER finally
OUTER returning core:A!
OUTER finally
CALLER [core:A!]
OUTER enter
INNER enter
TARGET greet bad
INNER throwing IllegalArgumentException
INNER finally
OUTER throwing IllegalArgumentException
OUTER finally
CALLER caught invalid input
OUTER enter
CACHE short-circuit
OUTER returning stored:B
OUTER finally
CALLER [stored:B]
TARGET_CALLS 2
~~~

### 10.1. Trường hợp thành công: giải thích từng dòng

Lớp OUTER thực hiện `enter` trước rồi gọi `next.proceed()`; kết quả là lớp INNER bắt đầu. INNER gọi core và thấy `"core:A"`. INNER in `returning core:A`, tạo result mới `"core:A!"`, chạy `finally` của INNER rồi trả sang OUTER. OUTER nhận **result đã được INNER biến đổi**, in `returning core:A!`, tạo `"[core:A!]"`, chạy `finally` của OUTER rồi caller mới in `CALLER [core:A!]`.

Điểm cần thuộc: **`finally` của INNER xuất hiện trước `returning` của OUTER.** Không có một “vòng after của tất cả advice” chạy tách khỏi call stack; đó là các hàm lồng nhau đang lần lượt trả điều khiển.

### 10.2. Trường hợp ngoại lệ

Lần gọi `core.greet("bad")` tăng counter và ném `IllegalArgumentException`. INNER ghi `throwing`, thực thi `finally` rồi ném lại. OUTER nhận lỗi từ `proceed`, ghi `throwing` và `finally` rồi cũng ném lại. Caller bắt đúng `IllegalArgumentException` gốc.

**Không có dòng `returning`** ở cả INNER lẫn OUTER bởi chúng không nhận được normal result. Nếu một advice xử lý exception và trả fallback, kịch bản của lớp ngoài có thể thay đổi thành normal completion.

### 10.3. Trường hợp short-circuit

Chuỗi thứ ba được xây `OUTER → CACHE → INNER → TARGET`. CACHE trả `"stored:B"` mà không gọi next:

~~~text
OUTER enter
CACHE short-circuit
OUTER returning stored:B
OUTER finally
CALLER [stored:B]
~~~

Không có `INNER enter` và cũng không có `TARGET greet B`. Vì core chỉ từng chạy với `A` và `bad`, `TARGET_CALLS 2`.

**Hệ quả:** một advice ngoài cache không nên lấy “số lần được gọi” làm “số lần target đã thực thi”. Các chính sách audit/metrics phải xác định event đang ghi là **invocation tới public boundary** hay **execution thực tế của target**.

### 10.4. Đây có phải ví dụ bytecode weaving không?

Không. `execute()` xây chain theo code Java, để quan sát trực tiếp quy tắc lồng và rút ra. Một công nghệ AOP có thể hiện thực cấu trúc tương đương bằng proxy hoặc woven bytecode, nhưng chương trình này **không sửa class file hoặc tự chọn join point theo pointcut language**.

Điểm quan trọng được kiểm chứng là **ngữ nghĩa hàm bao quanh và Java call stack**, không phải cú pháp của một engine đặc biệt. Khi chuyển sang công nghệ thật, cần thêm integration test xác minh **precedence và join point coverage**.

## 11. Tại sao code lắp chain phải duyệt ngược?

Trong ví dụ:

~~~java
Proceed chain = core;
for (int i = outerToInner.size() - 1; i >= 0; i--) {
    Around layer = outerToInner.get(i);
    Proceed next = chain;
    chain = () -> layer.apply(next);
}
~~~

Danh sách người đọc cung cấp là `[OUTER, INNER]` theo thứ tự **muốn nhìn thấy khi bắt đầu gọi**. Nhưng một wrapper cần nhận **lớp ở bên trong** làm next. Vì thế:

1. Khởi đầu `chain = target`.
2. Lấy INNER từ cuối danh sách và tạo `INNER(target)`.
3. Lấy OUTER và tạo `OUTER(INNER(target))`.
4. Gọi outermost closure.

Nếu duyệt xuôi mà mỗi bước bọc ngoài chain hiện có, bạn sẽ tạo `INNER(OUTER(target))` thay vì mong muốn. Trong các interceptor frameworks có thể có quy ước order khác; hãy xác minh cách chúng lắp chain thực sự, không áp công thức duyệt ngược máy móc lên mọi API.

### 11.1. Closure cần chụp next ở mỗi vòng

`Proceed next = chain` tạo biến cục bộ cố định cho lambda của vòng hiện tại. Nếu vô tình dùng một tham chiếu mutable chia sẻ đến `chain` sau khi thay nó, closure có thể gọi nhầm chính mình hoặc lớp không mong muốn, gây recursion vô hạn. Chú ý này là vấn đề **kỹ thuật ghép wrapper**, không phải một quy luật AOP mới.

### 11.2. Chuỗi trên được xây lại mỗi lần hay tái sử dụng?

Ví dụ dựng chain mỗi lần `execute` được gọi. Trong ứng dụng thực, engine có thể xây interceptor chain một lần rồi tái sử dụng cho nhiều invocations. Nếu handler giữ trạng thái mutable dùng chung, thread-safety và lifecycle phải được xem xét. **Thứ tự vào/rút ra theo nesting không thay đổi**, nhưng số object advice và cấu hình runtime có thể khác.

## 12. Nhiều loại advice: before, after-returning, after-throwing, finally

Một AOP engine có thể cung cấp cả những advice chuyên dụng ngoài `around`. Khi chúng được kết hợp tại một join point, ý nghĩa thông thường:

| Hành vi | Khi nào chạy về mặt ngữ nghĩa? |
| --- | --- |
| **Before** | Trước khi tiến vào công việc mà advice quan sát |
| **After returning** | Khi ranh giới đang quan sát hoàn tất bình thường |
| **After throwing** | Khi ranh giới đang quan sát hoàn tất ngoại lệ |
| **After/finally** | Khi rời ranh giới theo cả normal/exceptional exit nếu engine hỗ trợ |
| **Around** | Có thể kiểm soát chuyển tiếp và các hành vi ở cả hai phía |

Tuy nhiên, thứ tự chính xác giữa advice **của những aspect khác nhau** vẫn do precedence quyết định. Không nên suy ra: “mọi before chạy trước mọi around” hoặc “mọi after-returning chạy sau mọi finally” nếu không hiểu chúng được dệt/bọc thế nào.

### 12.1. Advice ngoài và advice trong có thể thấy outcome khác nhau

Giả sử INNER around catch exception và trả fallback. Ở ranh giới INNER có exceptional target; ở ranh giới OUTER có normal return. Một after-throwing gắn vào target execution và một after-returning gắn vào outer call boundary **có thể đều hợp lệ** trong cùng một workflow.

Vì vậy một dashboard gộp mọi `afterReturning` thành “target success count” có thể báo sai. Hãy gắn outcome với **loại join point và ranh giới cụ thể**.

### 12.2. Một advice sau trả về có thể ném lỗi

Nếu target return bình thường, nhưng after-returning callback tự ném exception, lớp ngoài có thể thấy exceptional completion. Nếu business response đã được tạo trước đó, caller vẫn có thể nhận lỗi callback thay vì result nếu callback chạy đồng bộ trong chain. Ngược lại, nếu callback chỉ được đưa vào một hàng đợi async, caller có thể nhận result trước khi callback lỗi. Không áp một kịch bản chung cho mọi tool.

## 13. Phạm vi quan sát khi có cache, authorization, retry và metrics

Một ví dụ có nhiều concern:

~~~text
TRACE (outer)
  AUTH
    CACHE
      RETRY
        METRICS (inner)
          BUSINESS
~~~

**Đây chỉ là một thứ tự minh họa**, không phải thiết kế nên áp dụng máy móc.

### 13.1. Authorization ở ngoài cache hay trong cache?

Nếu `AUTH` **ngoài** `CACHE`, mọi request phải đi qua kiểm quyền trước khi cache có thể trả. Nếu chuyển cache ra ngoài auth, cache hit có thể short-circuit trước khi kiểm quyền, làm mất bước enforcement. Với dữ liệu nhạy cảm, thứ tự này có thể tạo lỗ hổng, trừ khi cache key và ranh giới bảo mật đã được thiết kế đầy đủ.

Không dùng `CACHE` short-circuit để bỏ qua một policy bắt buộc ngoài ý định.

### 13.2. Metrics ngoài hay trong retry?

- **Metrics ngoài retry:** báo elapsed end-to-end, kể cả backoff và nhiều lần thử.
- **Metrics trong retry:** mỗi attempt có metric riêng.
- **Metrics ngoài cache:** có thể đo cả cache hit và cache miss.
- **Metrics trong cache:** bỏ qua các lượt hit nếu cache không gọi next.

Nên dùng tên như `request_duration` và `attempt_duration` thay vì gọi cả hai là `method_duration` không phân biệt.

### 13.3. Audit có được chạy khi cache hit không?

Nếu audit cần ghi **mỗi yêu cầu API**, hãy đặt ở ngoài lớp có thể short-circuit. Nếu audit cần ghi **mỗi target execution**, đặt ở tầng nhìn thấy business thật và kiểm tra đường bypass. Hai mục tiêu là khác nhau; không có một vị trí luôn đúng.

### 13.4. Tracing và span nesting

Một trace span ở outer layer có thể bao các span con ở inner layers. Khi scope đóng theo thứ tự **inner trước, outer sau**, cây span có cấu trúc hợp lý. Nhưng với async operations, nếu method return Future trước task completion, một `finally` trên method có thể đóng span quá sớm; cần tách method invocation scope và task completion scope theo contract.

### 13.5. Transaction, retry và tính idempotent

Nếu target có side effects, retry có thể lặp lại việc ghi dữ liệu. Vị trí transaction boundary và retry quyết định mỗi attempt có transaction riêng hay toàn bộ workflow chung một scope. Điều này ảnh hưởng consistency và idempotency, không thể quyết định chỉ từ câu “outer hơn sẽ after sau hơn”. Cần hiểu khả năng rollback, external I/O và giới hạn retry.

## 14. Thứ tự advice không giao hoán: ví dụ phân tích

Hai transformer:

~~~text
A: encrypt(result)
B: compress(result)
~~~

Các chuỗi thường không tương đương:

~~~text
encrypt(compress(data))
compress(encrypt(data))
~~~

Nén sau khi mã hóa thường rất khác nén trước khi mã hóa. Tương tự:

- Normalize trước hay sau validate có thể thay outcome.
- Masking trước hay sau audit thay thông tin được ghi.
- Authorization trước hay sau cache thay mức bảo vệ.
- Retry ngoài hay trong transaction thay số lần/thời điểm commit.
- Timeout ngoài hay trong retry thay deadline áp dụng.

Vì vậy, với nhiều aspect, phải viết **thứ tự cấu trúc có ý nghĩa nghiệp vụ** rồi kiểm thử. Nếu hai advice là phép toán giao hoán và stateless, thứ tự có thể ít quan trọng hơn; nhưng đừng suy từ hai ví dụ đơn giản rằng mọi advice có thể sắp xếp tùy ý.

## 15. Runtime exceptions, cancellation và resource cleanup

### 15.1. Kết quả `null` và phương thức `void`

Một method `String load()` có thể **trả `null` bình thường**; `null` không có nghĩa target ném exception. Lớp after-returning nên xử lý `null` an toàn.

Một method `void reset()` **không có return value**, nhưng vẫn có normal completion hoặc exceptional completion. Một adapter proxy dùng `Object` có thể biểu diễn `void` qua `null` theo hợp đồng Reflection; điều đó không biến `void` thành `String` result.

### 15.2. Primitive và result transformation

Nếu method khai báo `int` mà around wrapper trả `null` qua adapter, việc unboxing có thể lỗi. Advice có nhiệm vụ **biến đổi result** phải tôn trọng return type của join point. Với method generic/bridge, cần xác minh metadata thực tế ở ranh giới call/execution.

### 15.3. Cancellation và timeout

Hủy task có thể thể hiện bằng một exception, một trạng thái Future hoặc việc dừng chuyển tiếp. Một around advice đồng bộ không tự nhìn được mọi sự kiện cancellation của tác vụ bất đồng bộ. `finally` lúc method return chỉ đóng scope lời gọi đồng bộ; nó không chờ tất cả công việc con hoàn tất.

### 15.4. Cleanup thất bại

Một `finally` ghi metric qua network có thể mất thời gian hoặc ném lỗi, làm caller nhận exception không phải từ target. Với advice quan sát, thường cần policy giảm ảnh hưởng lên nghiệp vụ, nhưng những concern bắt buộc như audit có thể chọn fail-closed. Chính sách phải minh bạch và có tests.

## 16. Lời gọi lồng nhau không đồng nghĩa một lời gọi có nhiều aspect

Có hai nguồn “lồng” khác nhau:

1. **Advice nesting:** nhiều wrappers cùng áp dụng lên **một** join point hoặc ranh giới call.
2. **Business nesting:** target A gọi target B, mỗi target lại có chain advice riêng.

Ví dụ:

~~~text
Caller -> Aouter -> Ainner -> methodA()
                               |
                               +-> Bouter -> Binner -> methodB()
~~~

Đầu ra tổng thể có thể xen kẽ các events của hai chains. Việc `Bouter` chạy trong lúc `Ainner` chưa return không có nghĩa engine đảo precedence; đó là do **business method A gọi method B**.

Tương tự, recursion có thể tạo nhiều lần vào **cùng một chain**. Hãy gắn `invocationId`, `parentSpanId` hoặc call-depth với logs khi điều tra.

### 16.1. Đếm advice entry và target execution riêng

Một lớp outer được vào một lần có thể gọi inner hai lần do retry. Một cache có thể được vào một lần rồi không gọi inner lần nào. Do đó:

~~~text
outer advice entries = 1
inner advice entries = 0, 1 hoặc nhiều lần
target executions    = 0, 1 hoặc nhiều lần
~~~

Tương quan giữa ba số đếm phụ thuộc cấu trúc và logic, không thể mặc định đều bằng nhau.

### 16.2. Double weaving và hai pointcut cùng chọn

Nếu một class đã được instrument ở nhiều tầng, hai advice cùng loại có thể chạy **ngoài ý định**, tạo hai event giống nhau. Nhưng hai lời gọi after-returning khác nhau không tự chứng minh double weaving: có thể thuộc hai joins (call/execution), hai nghiệp vụ lồng nhau hoặc hai policies hợp lệ.

Chẩn đoán cần kết hợp aspect identity, join point kind, signature, invocation ID, target count và instrumentation layer.

## 17. Khi proxy hoặc weaving quyết định độ phủ chuỗi

Một chuỗi advice **chỉ tồn tại trên những đường mà hệ thống can thiệp được**.

- **Interface proxy:** caller phải gọi qua proxy để handler nhận lời gọi tương ứng.
- **Subclass proxy:** còn bị giới hạn bởi khả năng override và dispatch.
- **Bytecode weaving:** method execution có thể được instrument ngay trong body nếu công cụ hỗ trợ và class nằm trong phạm vi.
- **Load-time weaving:** cần transformer hoạt động trước khi class được định nghĩa hoặc cơ chế retransformation được hỗ trợ riêng.
- **Self-invocation:** gọi `this.method()` có thể bỏ qua proxy ngoài; một execution join point đã woven có thể vẫn chạy.

Cần phân biệt **độ phủ** và **thứ tự**: pointcut khớp rồi được engine can thiệp là điều kiện đầu; precedence mới xác định chain trên đường ấy. Nếu một lớp bị bypass do gọi raw target, không có “after” nào của lớp ấy để tháo ra.

Không giả định mọi AOP engine đều hỗ trợ cùng các loại method `private`, `final`, `static`, constructor, field access hoặc exception handler.

## 18. Thread safety và state trong nhiều advice

Khi chain được tái sử dụng, các advice có thể phục vụ nhiều threads đồng thời. Lỗi phổ biến:

~~~java
class UnsafeTimingAdvice {
    long started;

    void before() {
        started = System.nanoTime();
    }

    long elapsed() {
        return System.nanoTime() - started;
    }
}
~~~

Đây là đoạn mã minh họa, không phải chương trình có `main`. Nếu thread A và B gọi `before()` xen kẽ trên cùng instance, `elapsed()` có thể dùng mốc của thread khác. **Thứ tự vào/rút ra trong một invocation không tự tạo thread safety giữa các invocations.**

Một thiết kế tốt dùng **local variable per call**, hoặc per-invocation context. Cẩn trọng với:

- Shared metric counters: dùng cấu trúc atomic/concurrent phù hợp.
- Mutable transform state: không chia sẻ object không thread-safe nếu handler dùng chung.
- `ThreadLocal`: phải restore/remove trong `finally` khi thread pool tái sử dụng thread.
- Async propagation: `ThreadLocal` không tự truyền qua mọi executor/task.
- Retry: nếu một advice được reentrant, state của lần thử trước không được làm bẩn lần sau.
- Cleanup: dừng advice mới và chờ in-flight operations trước khi đóng tài nguyên chung.

Một chain có thể **lồng đúng** nhưng **sai kết quả** vì race hoặc state leakage. Kiểm thử concurrency phải bổ sung cho test order đơn luồng.

## 19. Kiểm thử thứ tự theo một hợp đồng rõ

### 19.1. Ma trận kịch bản

| Kịch bản | Kỳ vọng |
| --- | --- |
| Hai advice, target trả bình thường | `outer.enter → inner.enter → target → inner.return/finally → outer.return/finally` |
| Target ném lỗi | `inner.throwing/finally` trước `outer.throwing/finally`, nếu cả hai chỉ rethrow |
| INNER biến đổi result | OUTER nhận result đã biến đổi |
| OUTER biến đổi result | Caller nhận result sau OUTER |
| Cache hit nằm giữa OUTER và INNER | OUTER chạy; INNER và target không chạy |
| Authorization ở ngoài cache, bị từ chối | Cache và target không chạy |
| Retry bao ngoài INNER | INNER và target có thể chạy nhiều lần |
| Metrics ngoài retry | Đo cả các attempts và khoảng chờ |
| Metrics trong retry | Có metric cho từng attempt được phép |
| INNER phục hồi exception | OUTER có thể thấy normal return |
| `finally` tự ném lỗi | Xác minh chính sách bảo toàn/suppression ngoại lệ |
| Target return `null` | Normal return, không nhầm exceptional |
| Return `CompletableFuture` pending | Method wrapper rút ra trước task completion |
| Caller bypass proxy | Không kỳ vọng proxy handler chạy |
| Class đã woven | Xác minh đúng join points thực sự instrument |
| Nhiều requests đồng thời | Per-invocation state không ghi đè nhau |

### 19.2. Tránh assertion chỉ dựa vào dòng log

Một test mạnh hơn nên dùng **event list** được ghi theo thứ tự:

~~~text
expectedNormal = [
    "OUTER.enter",
    "INNER.enter",
    "TARGET.call",
    "INNER.return",
    "INNER.finally",
    "OUTER.return",
    "OUTER.finally"
]
~~~

Đây là **pseudocode assertion**. Trên Java, có thể dùng `List<String> events` và so sánh với danh sách kỳ vọng, hoặc giữ stdout được ghi nhận tất định như ví dụ đã chạy. Khi test trong môi trường đồng thời, không nên đòi event global có thứ tự tuyệt đối nếu nhiều invocation chạy xen kẽ; cần gom theo invocation ID.

### 19.3. Kiểm đúng thứ tự lẫn đúng phạm vi

Unit test `Layer.apply()` chỉ chứng minh code trong advice. Với AOP engine thật, phải có integration test xác minh **pointcut chọn đúng, precedence đúng, lời gọi qua đúng proxy/weaving boundary**, sau đó mới so chuỗi events. Nếu lớp không được instrument, nó sẽ không thể có `enter/return/finally` trong test dù function logic hoàn toàn chính xác.

## 20. Checklist thiết kế nhiều aspect trước khi triển khai

1. **Vẽ chain có tên lớp ngoài/trong.** Không chỉ liệt kê danh sách aspect mà không nói thứ tự.
2. **Định nghĩa event đang quan sát:** request, attempt, target execution hay task completion?
3. **Chọn precedence theo mục tiêu nghiệp vụ:** authorization, cache, retry, transaction, tracing và audit có ranh giới khác nhau.
4. **Xác định từng advice có gọi `proceed` không:** có thể short-circuit hoặc retry không?
5. **Đặt chính sách biến đổi result rõ:** lớp nào được phép sửa return value/exception?
6. **Kiểm cả normal lẫn exceptional path:** `afterReturning` khác `finally`.
7. **Định nghĩa cleanup:** dọn theo thứ tự trong→ngoài; không để lỗi sink che lỗi target ngoài chủ đích.
8. **Không dùng tên “after” mơ hồ:** phân biệt after-returning, after-throwing và finally-style.
9. **Kiểm tra pointcut coverage:** proxy bypass, self-invocation, method modifiers và phạm vi weaving.
10. **Kiểm soát state lifetime:** shared handler không chứa mutable per-call state.
11. **Phân biệt sync và async:** khi Future return, scope nào thực sự đã hoàn tất?
12. **Đo overhead:** mỗi wrapper, reflection, logging và I/O có chi phí.
13. **Đếm target invocations:** đặc biệt với retry và cache.
14. **Tránh double instrumentation:** nếu hai policies tương đương ở hai tầng, xác định ownership.
15. **Integration test precedence thật:** thứ tự tùy engine không được suy từ thứ tự source.
16. **Tài liệu hóa điều kiện lỗi:** fallback/timeout/denial và expected caller outcome.

## 21. Những lỗi hiểu sai thường gặp

1. **“After của OUTER chạy trước after của INNER vì OUTER được gọi trước.”** Sai với nested wrappers bình thường; OUTER phải chờ INNER trả.
2. **“Mỗi advice after đều chạy dù target throw.”** Sai với after-returning; `finally` mới là cơ chế cleanup cho cả hai đường thông thường.
3. **“Một `afterReturning` luôn thấy raw target result.”** Sai nếu lớp trong đã biến đổi result.
4. **“Một `afterThrowing` ngoài luôn thấy target exception.”** Sai nếu lớp trong đã catch và trả fallback.
5. **“Cả ba `finally` chạy sau khi caller nhận result.”** Sai: `finally` xảy ra trước khi từng layer thực sự trả điều khiển cho caller.
6. **“Một `proceed()` chắc chắn gọi ngay target.”** Sai: có thể còn nhiều advice bên trong.
7. **“Mọi around advice đều bắt buộc gọi `proceed()` đúng một lần.”** Tùy engine/policy; cache có thể bỏ qua, retry có thể lặp.
8. **“Outer advice entries bằng business calls.”** Không khi short-circuit, retry hoặc multiple call paths.
9. **“Priority nhỏ hơn luôn ở ngoài.”** Phụ thuộc quy ước công cụ.
10. **“Đổi thứ tự aspect chỉ đổi vị trí log.”** Có thể đổi permission, outcome, value và consistency.
11. **“Cleanup trong `finally` không bao giờ hỏng.”** Chính cleanup có thể ném lỗi, block hoặc side effect.
12. **“`return` trong `finally` là cách giữ kết quả.”** Nó có thể nuốt result/exception trước đó.
13. **“Biến đổi object mutable là quan sát thuần túy.”** Nó có thể tác động caller.
14. **“Method trả Future là toàn workflow đã complete.”** Không; task có thể còn chạy.
15. **“Hai log giống nhau chứng minh double weaving.”** Có thể do các join points hợp lệ hoặc events delivery trùng.
16. **“Thử advice trực tiếp chứng minh precedence runtime.”** Không; phải test chain/instrumentation thật.
17. **“Một chain đúng thứ tự thì chắc thread-safe.”** Không; shared fields vẫn có thể race.
18. **“Proxy AOP tự thấy mọi method nội bộ.”** Không đối với nhiều mô hình wrapper bên ngoài.
19. **“Mọi engine hỗ trợ cùng một cú pháp và ngữ nghĩa around advice.”** Không; phải kiểm tra tài liệu công nghệ đang dùng.
20. **“Bất kỳ cache hit nào cũng có thể bỏ qua authorization.”** Nguy hiểm nếu policy bắt buộc không được bảo đảm.
21. **“Trả fallback trong INNER không ảnh hưởng outcome của OUTER.”** Thực tế OUTER thấy normal return nếu exception đã được phục hồi.
22. **“Một phép đo latency ở OUTER và INNER có thể cộng mà không trùng.”** Outer thường bao gồm thời gian inner; cộng như duration độc lập có thể double-count.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** `A(B(C(target)))`, target trả bình thường. `after` của advice nào chạy trước?  
**Đáp án:** C trước, tiếp đến B rồi A, nếu mỗi around wrapper chuyển tiếp một lần và after tương ứng được đặt sau lời `proceed`.

**Câu 2.** INNER biến `"x"` thành `"x!"`; OUTER thêm ngoặc vuông. Caller thấy gì?  
**Đáp án:** `"[x!]"` vì outer nhận kết quả đã đi qua inner.

**Câu 3.** INNER short-circuit trả cached result. OUTER có thể chạy `afterReturning` không?  
**Đáp án:** Có; OUTER nhận một normal return từ INNER, dù target không chạy.

**Câu 4.** Target ném exception, INNER ghi lỗi rồi `finally`. OUTER chạy ở nhánh nào?  
**Đáp án:** Nếu INNER ném lại thì OUTER thấy exceptional completion; nếu INNER chuyển lỗi thành fallback thì OUTER thấy normal return.

**Câu 5.** Vì sao `finally` của INNER thường xuất hiện trước câu lệnh sau `proceed` ở OUTER?  
**Đáp án:** OUTER đang chờ INNER hoàn tất; INNER phải rời scope và chạy `finally` trước khi trả điều khiển.

**Câu 6.** Có thể suy ra ai outer từ tên class hoặc thứ tự khai báo trong source không?  
**Đáp án:** Không có quy tắc chung. Phải xác định precedence theo công cụ và kiểm thử đường gọi thật.

**Câu 7.** Outer retry gọi `proceed` hai lần; inner metrics đo mỗi attempt hay cả request?  
**Đáp án:** Nếu metrics nằm bên trong retry, mỗi lần `proceed` chạy lại nó có thể tạo mẫu theo attempt; metrics ngoài retry đo toàn bộ request.

**Câu 8.** `finally` tự `return` một giá trị khác có an toàn không?  
**Đáp án:** Không. Nó có thể thay return hoặc nuốt exception trước đó.

**Câu 9.** Trong demo Java, vì sao `TARGET_CALLS 2` dù có ba lần gọi `execute`?  
**Đáp án:** Ca thứ ba cache short-circuit, không gọi tới Core; chỉ A và bad tới target.

**Câu 10.** Method trả `CompletableFuture` chưa hoàn tất. Around `finally` chạy khi nào?  
**Đáp án:** Nếu scope đo method invocation thông thường, nó chạy khi method trả Future, không đợi completion của task.

**Câu 11.** Đặt cache ngoài authorization có thể ảnh hưởng gì?  
**Đáp án:** Cache hit có thể bỏ qua kiểm quyền nếu chính sách không được kiểm ở ranh giới khác. Thứ tự cần dựa trên hợp đồng bảo mật.

**Câu 12.** Khi hai advice cho hai join point khác nhau cùng chạy, có chắc double weaving?  
**Đáp án:** Không. Có thể là hai events hợp lệ; cần phân biệt identity của join point, aspect và logical operation.

## 23. Tổng kết

**Chuỗi around advice được hiểu bằng sự lồng nhau của các lời gọi.** Lớp ngoài chạy trước trên đường vào, lớp trong chạy trước trên đường trả kết quả hoặc tháo ngăn xếp ngoại lệ. Mỗi lớp có thể quan sát hoặc biến đổi result, ném lại/khôi phục lỗi và cleanup trong `finally`. Nếu một lớp **không gọi `proceed`**, những lớp phía trong có thể không chạy; nếu **gọi nhiều lần**, lớp trong và target có thể thực thi nhiều lần.

Điều thiết yếu khi phối hợp nhiều aspect không phải ghi nhớ thứ tự A/B/C máy móc, mà là **định nghĩa outer/inner theo precedence thật, xác định ranh giới quan sát và kiểm thử normal/exceptional/short-circuit/retry paths**. Với các concern nhạy cảm như kiểm quyền, audit, cache hay transaction, đổi thứ tự có thể thay đổi cả tính đúng đắn nghiệp vụ. Hãy bảo toàn kết quả và ngoại lệ của caller khi advice chỉ quan sát, quản lý `finally`/resource cleanup cẩn thận, tách method return khỏi asynchronous completion, và kiểm chứng thực tế qua đúng proxy/weaving join point.
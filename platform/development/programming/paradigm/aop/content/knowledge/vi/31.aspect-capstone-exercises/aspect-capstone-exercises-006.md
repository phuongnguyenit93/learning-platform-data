# Thiết kế hai aspect có thứ tự và kiểm chứng chuỗi thực thi

## Mục tiêu bài tập tổng hợp

Khi một join point khớp nhiều aspect trong lập trình hướng khía cạnh (**Aspect-Oriented Programming, AOP**), **thứ tự chạy advice quyết định thứ tự quan sát hành vi**. Hai aspect đều đúng khi chạy riêng vẫn có thể tạo log, metric hoặc ngữ nghĩa khác nhau khi kết hợp. Đặc biệt, với **around advice**, việc đi vào và đi ra tạo nên **cấu trúc lồng nhau**: advice bên ngoài chạy phần “trước” đầu tiên nhưng chạy phần “sau” cuối cùng.

Trong bài này, bạn sẽ thiết kế **hai aspect có trách nhiệm riêng**, chỉ định thứ tự bọc, tính tay chuỗi sự kiện mong đợi, chạy chương trình Java 17+ để kiểm chứng cả đường thành công lẫn lỗi, rồi đảo thứ tự để quan sát sự khác biệt. Đây là một bài tập có lời giải và các tiêu chí tự kiểm tra, không chỉ là ví dụ ghi log hai lần.

Sau khi hoàn thành, bạn cần:

1. Phân biệt **aspect**, **join point**, **pointcut**, **before/after/around advice** và **weaving**.
2. Dự đoán được chuỗi `before → proceed → afterReturning/afterThrowing → finally` khi hai advice bao quanh nhau.
3. Thiết kế hai aspect có nhiệm vụ tách biệt, không ghi trùng và không thay đổi giá trị trả về/ngoại lệ gốc.
4. Nêu được thứ tự áp dụng bằng một chính sách rõ ràng; không phụ thuộc thứ tự tình cờ của classpath, reflection hay lần khởi tạo.
5. Viết phép kiểm tra xác nhận thứ tự sự kiện, bao gồm cả trường hợp đổi thứ tự và nghiệp vụ ném lỗi.
6. Biết mở rộng kiểm thử cho điểm cắt chồng nhau, lời gọi lồng nhau, bất đồng bộ, thread khác và lỗi ngay trong advice.

**Phạm vi:** kiến thức AOP cơ bản và nâng cao theo nghĩa chung. Không có một cú pháp khai báo thứ tự chung cho mọi công cụ AOP; chương trình bên dưới dùng JDK dynamic proxy để **mô phỏng chính xác việc lồng hai around advice theo thứ tự được chỉ định**, từ đó minh họa nguyên tắc thứ tự mà không lệ thuộc vào thư viện AOP cụ thể.

## 1. Ôn lại đúng các khái niệm cần dùng

| Khái niệm | Vai trò trong bài tập |
| --- | --- |
| **Aspect** | Thành phần gom một trách nhiệm xuyên suốt, ví dụ tracing hoặc audit |
| **Join point** | Vị trí có thể được chặn, ở đây là lời gọi tới `Service.execute(...)` qua proxy |
| **Pointcut** | Điều kiện quyết định những join point nào được áp dụng advice |
| **Advice** | Hành vi bổ sung tại join point, có thể chạy trước/sau/bao quanh |
| **Around advice** | Bao lấy thao tác gốc; có thể gọi tiếp (`proceed`), quan sát kết quả và lỗi |
| **Weaving/interception** | Cơ chế gắn advice vào thực thi: có thể là biến đổi bytecode hoặc chặn qua proxy, tùy công nghệ |
| **Precedence/order** | Quy tắc xác định aspect nào là tầng ngoài và tầng trong ở một join point có nhiều aspect |

Lưu ý: **thứ tự đăng ký aspect, thứ tự chạy advice, thứ tự các join point và thứ tự xuất hiện bản ghi ở sink bất đồng bộ là các vấn đề khác nhau**. Ví dụ này kiểm chứng **thứ tự thực thi trong một lời gọi đồng bộ** bằng cách thêm sự kiện vào danh sách trong cùng thread. Nó không tuyên bố rằng các log đi qua hàng đợi bất đồng bộ sẽ đến hệ thống lưu trữ theo đúng thứ tự đó.

Trong các cơ chế AOP khác nhau, việc ưu tiên advice có thể được cấu hình theo annotation, khai báo precedence, trình tự wrapper hoặc quy tắc weaving. Không tự giả định “aspect nào viết trước trong tệp thì chạy trước”. Bạn phải biết cơ chế cụ thể rồi kiểm chứng trên chương trình thật.

## 2. Đề bài: hai aspect, một phương thức nghiệp vụ

Giả sử có interface nghiệp vụ:

```java
// Giao diện bài toán.
interface Service {
    String execute(String input);
}
```

Nghiệp vụ:

- Khi input khác `"fail"`: trả `"ok:" + input`.
- Khi input bằng `"fail"`: ném `IllegalStateException("rejected")`.
- Bản thân nghiệp vụ chỉ ghi một dấu vết “đang thực thi” và thêm một dấu vết trả kết quả hoặc ném lỗi.

Bạn cần thiết kế:

**Aspect 1 — TraceAspect**

- Trước khi đi vào tầng tiếp theo: thêm `Trace.before`.
- Khi tầng tiếp theo hoàn tất bình thường: thêm `Trace.afterReturning`.
- Khi tầng tiếp theo ném ngoại lệ: thêm `Trace.afterThrowing:<ExceptionType>`.
- Ở mọi đường thoát: thêm `Trace.finally`.
- Không thay đổi kết quả nghiệp vụ và không nuốt ngoại lệ.

**Aspect 2 — AuditAspect**

- Trước khi đi vào tầng tiếp theo: thêm `Audit.before`.
- Khi tầng tiếp theo hoàn tất bình thường: thêm `Audit.afterReturning`.
- Khi tầng tiếp theo ném ngoại lệ: thêm `Audit.afterThrowing:<ExceptionType>`.
- Ở mọi đường thoát: thêm `Audit.finally`.
- Không tự ý thay đổi kết quả/ngoại lệ, không ghi tham số nhạy cảm.

Trong bài thực tế, trace thường gắn với correlation/span và audit thường là sự kiện có cấu trúc về hành động/kết quả. Để tập trung vào **thứ tự thực thi**, bản demo ghi các chuỗi sự kiện ngắn, dễ đối chiếu. Hai aspect có thể có code khung giống nhau vì cùng áp dụng dạng around advice; **mục đích, chính sách dữ liệu và mức độ tin cậy của chúng vẫn khác nhau** khi triển khai thật.

### Yêu cầu kiểm chứng

Thực hiện ít nhất bốn kịch bản:

1. **Trace bên ngoài, Audit bên trong — thành công.**
2. **Trace bên ngoài, Audit bên trong — nghiệp vụ ném lỗi.**
3. **Audit bên ngoài, Trace bên trong — thành công.**
4. **Audit bên ngoài, Trace bên trong — nghiệp vụ ném lỗi.**

Với mỗi kịch bản, lưu chuỗi sự kiện thành một danh sách có thứ tự, so sánh với chuỗi mong đợi và chỉ in `CHECK=PASS` nếu khớp **đúng từng phần tử, đúng thứ tự, đúng số lần**. Nếu sai, chương trình phải báo lỗi kiểm chứng.

## 3. Phân tích trước khi viết code: quy tắc lồng nhau

Gọi hai aspect là A và B. Nếu **A là tầng ngoài**, **B là tầng trong**, còn J là join point nghiệp vụ, luồng đồng bộ có dạng:

```text
Caller
  |
  v
A.before
  |
  v
B.before
  |
  v
J: business execution
  |
  v
B.afterReturning / B.afterThrowing
  |
  v
B.finally
  |
  v
A.afterReturning / A.afterThrowing
  |
  v
A.finally
  |
  v
Caller nhận result / exception
```

Những sự kiện `afterReturning` và `afterThrowing` loại trừ nhau đối với **mỗi advice trong một lần thực thi** theo contract của demo: thành công thì nhánh return, lỗi thì nhánh throw. `finally` chạy trong cả hai trường hợp. Điều này không có nghĩa mọi framework AOP đều định nghĩa advice riêng tên tương tự với cách ưu tiên y hệt nhau; đây là ngữ nghĩa của hai khối `try/catch/finally` trong bài.

Cách hiểu chính xác hơn cho một around advice:

```java
// Mã giả: proceed() đại diện cho lời gọi tầng tiếp theo.
Object around() throws Throwable {
    events.add("A.before");
    try {
        Object result = proceed();
        events.add("A.afterReturning");
        return result;
    } catch (Throwable error) {
        events.add("A.afterThrowing");
        throw error;
    } finally {
        events.add("A.finally");
    }
}
```

Chú ý: `A.afterReturning` diễn ra **sau khi toàn bộ tầng bên trong đã trở về bình thường**. Nếu B dùng `finally`, thì `B.finally` phải chạy trước khi A thấy tầng trong đã hoàn tất. Ngược lại, nếu J ném lỗi, B xử lý hoặc truyền lỗi lên trước; A chỉ thấy lỗi nếu B tiếp tục ném lỗi.

### 3.1. Một phép thử suy luận

Giả sử A bao ngoài B và J trả kết quả bình thường:

```text
A.before
B.before
J
B.afterReturning
B.finally
A.afterReturning
A.finally
```

Nếu đảo A và B:

```text
B.before
A.before
J
A.afterReturning
A.finally
B.afterReturning
B.finally
```

Thứ tự các sự kiện trước và sau **đảo theo cấu trúc bọc**, chứ không phải tất cả `before` chạy theo một thứ tự rồi tất cả `after` cũng chạy cùng chiều. Đây là ý tưởng trọng tâm phải nắm trước khi viết chương trình.

### 3.2. Lỗi có thể làm thay đổi chuỗi ra sao?

Nếu J ném `IllegalStateException`, với A ngoài B:

```text
A.before
B.before
J.execute
J.throw
B.afterThrowing:IllegalStateException
B.finally
A.afterThrowing:IllegalStateException
A.finally
```

Nhưng nếu B **bắt lỗi rồi trả một kết quả dự phòng**, A có thể chạy nhánh `afterReturning` vì **từ góc nhìn A, tầng B đã trả bình thường**. Đây là lý do không thể suy luận chuỗi chỉ từ việc “nghiệp vụ có ném lỗi” mà bỏ qua hành vi của từng advice.

Trong lời giải chính, cả hai aspect đều truyền tiếp lỗi nguyên trạng, nên chuỗi dễ kiểm chứng hơn.

## 4. Thiết kế trước khi triển khai

Mỗi aspect trong demo là một **wrapper** quanh đối tượng cùng interface. Wrapper gọi tầng tiếp theo và sinh event theo kết quả; tầng sâu nhất là đối tượng nghiệp vụ.

Khi cấu hình **Trace ngoài, Audit trong**:

```text
Client
  |
  +--> TraceProxy
         |
         +--> AuditProxy
                |
                +--> BusinessService
```

Phần tạo cấu trúc:

```java
// Mã minh họa, các hàm định nghĩa ở chương trình hoàn chỉnh.
Service traceOutsideAudit = trace(audit(business, events), events);
```

Phải đọc từ trong ra ngoài: `audit(business, events)` tạo proxy Audit bọc business; sau đó `trace(...)` tạo proxy Trace bọc proxy Audit. **Lớp wrapper cuối cùng được gắn ở ngoài cùng**.

Cấu hình đảo:

```java
Service auditOutsideTrace = audit(trace(business, events), events);
```

Trong một hệ thống AOP sử dụng thứ tự qua cấu hình, thao tác tương đương là định nghĩa **rõ precedence** cho hai aspect; không nhất thiết viết hai lệnh bao bọc thủ công. Việc bọc proxy trong ví dụ giúp thứ tự nhìn thấy được, phù hợp cho kiểm chứng.

### Các bất biến cần bảo toàn

- Một lời gọi đến nghiệp vụ gốc chỉ diễn ra **một lần**, trừ khi yêu cầu retry được thiết kế tường minh (bài này không có retry).
- `before` của mỗi aspect chỉ chạy một lần cho một lượt chặn.
- Nếu tầng tiếp theo hoàn thành bình thường: chỉ chạy `afterReturning`.
- Nếu tầng tiếp theo ném lỗi: chỉ chạy `afterThrowing`, truyền lại lỗi gốc.
- `finally` luôn chạy sau nhánh return hoặc throw tương ứng.
- Không tự ghi event quá chi tiết đến mức làm thay đổi thời gian hoặc phụ thuộc trạng thái async.
- Chuỗi sự kiện kết thúc ở caller có kết quả/ngoại lệ nhất quán với nghiệp vụ.

## 5. Lời giải Java 17+: hai aspect có thứ tự rõ ràng

Dùng JDK dynamic proxy để minh họa hai around advice. Chương trình có thể lưu trong một tệp, không cần thư viện ngoài.

Tạo tệp **`AspectOrderExercise.java`** với toàn bộ nội dung dưới đây:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public class AspectOrderExercise {

    public interface Service {
        String execute(String input);
    }

    static final class BusinessService implements Service {
        private final List<String> events;

        BusinessService(List<String> events) {
            this.events = events;
        }

        @Override
        public String execute(String input) {
            events.add("Business.execute");

            if ("fail".equals(input)) {
                events.add("Business.throw");
                throw new IllegalStateException("rejected");
            }

            events.add("Business.return");
            return "ok:" + input;
        }
    }

    // Gọi tầng tiếp theo, rồi gỡ wrapper của reflection nếu có lỗi.
    private static Object callNext(
            Service next, Method method, Object[] args) throws Throwable {
        try {
            return method.invoke(next, args);
        } catch (InvocationTargetException wrapper) {
            throw wrapper.getCause();
        }
    }

    static final class TraceAspect implements InvocationHandler {
        private final Service next;
        private final List<String> events;

        TraceAspect(Service next, List<String> events) {
            this.next = next;
            this.events = events;
        }

        @Override
        public Object invoke(
                Object proxy, Method method, Object[] args) throws Throwable {
            events.add("Trace.before");

            try {
                Object result = callNext(next, method, args);
                events.add("Trace.afterReturning");
                return result;
            } catch (Throwable error) {
                events.add("Trace.afterThrowing:"
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                events.add("Trace.finally");
            }
        }
    }

    static final class AuditAspect implements InvocationHandler {
        private final Service next;
        private final List<String> events;

        AuditAspect(Service next, List<String> events) {
            this.next = next;
            this.events = events;
        }

        @Override
        public Object invoke(
                Object proxy, Method method, Object[] args) throws Throwable {
            events.add("Audit.before");

            try {
                Object result = callNext(next, method, args);
                events.add("Audit.afterReturning");
                return result;
            } catch (Throwable error) {
                events.add("Audit.afterThrowing:"
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                events.add("Audit.finally");
            }
        }
    }

    private static Service wrap(
            InvocationHandler advice) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] {Service.class},
                advice
        );
    }

    private static Service trace(
            Service next, List<String> events) {
        return wrap(new TraceAspect(next, events));
    }

    private static Service audit(
            Service next, List<String> events) {
        return wrap(new AuditAspect(next, events));
    }

    private static void verify(
            String label,
            Service service,
            String input,
            List<String> events,
            List<String> expected) {

        events.clear();
        System.out.println("== " + label + " ==");

        String outcome;
        try {
            outcome = "result=" + service.execute(input);
        } catch (IllegalStateException error) {
            outcome = "error="
                    + error.getClass().getSimpleName()
                    + ":" + error.getMessage();
        }

        for (String event : events) {
            System.out.println(event);
        }
        System.out.println(outcome);

        if (!events.equals(expected)) {
            throw new AssertionError(
                    "Expected: " + expected + ", actual: " + events);
        }
        System.out.println("CHECK=PASS");
    }

    public static void main(String[] args) {
        List<String> events = new ArrayList<>();
        Service business = new BusinessService(events);

        // Trace là tầng ngoài, Audit là tầng trong.
        Service traceOutsideAudit =
                trace(audit(business, events), events);

        verify(
                "trace > audit, success",
                traceOutsideAudit, "good", events,
                List.of(
                        "Trace.before",
                        "Audit.before",
                        "Business.execute",
                        "Business.return",
                        "Audit.afterReturning",
                        "Audit.finally",
                        "Trace.afterReturning",
                        "Trace.finally"
                )
        );

        verify(
                "trace > audit, failure",
                traceOutsideAudit, "fail", events,
                List.of(
                        "Trace.before",
                        "Audit.before",
                        "Business.execute",
                        "Business.throw",
                        "Audit.afterThrowing:IllegalStateException",
                        "Audit.finally",
                        "Trace.afterThrowing:IllegalStateException",
                        "Trace.finally"
                )
        );

        // Đảo thứ tự: Audit là tầng ngoài, Trace là tầng trong.
        Service auditOutsideTrace =
                audit(trace(business, events), events);

        verify(
                "audit > trace, success",
                auditOutsideTrace, "good", events,
                List.of(
                        "Audit.before",
                        "Trace.before",
                        "Business.execute",
                        "Business.return",
                        "Trace.afterReturning",
                        "Trace.finally",
                        "Audit.afterReturning",
                        "Audit.finally"
                )
        );

        verify(
                "audit > trace, failure",
                auditOutsideTrace, "fail", events,
                List.of(
                        "Audit.before",
                        "Trace.before",
                        "Business.execute",
                        "Business.throw",
                        "Trace.afterThrowing:IllegalStateException",
                        "Trace.finally",
                        "Audit.afterThrowing:IllegalStateException",
                        "Audit.finally"
                )
        );
    }
}
```

### 5.1. Biên dịch và chạy

Bằng JDK 17 trở lên, ở thư mục chứa tệp:

```bash
javac AspectOrderExercise.java
java AspectOrderExercise
```

Đầu ra mong đợi:

```text
== trace > audit, success ==
Trace.before
Audit.before
Business.execute
Business.return
Audit.afterReturning
Audit.finally
Trace.afterReturning
Trace.finally
result=ok:good
CHECK=PASS
== trace > audit, failure ==
Trace.before
Audit.before
Business.execute
Business.throw
Audit.afterThrowing:IllegalStateException
Audit.finally
Trace.afterThrowing:IllegalStateException
Trace.finally
error=IllegalStateException:rejected
CHECK=PASS
== audit > trace, success ==
Audit.before
Trace.before
Business.execute
Business.return
Trace.afterReturning
Trace.finally
Audit.afterReturning
Audit.finally
result=ok:good
CHECK=PASS
== audit > trace, failure ==
Audit.before
Trace.before
Business.execute
Business.throw
Trace.afterThrowing:IllegalStateException
Trace.finally
Audit.afterThrowing:IllegalStateException
Audit.finally
error=IllegalStateException:rejected
CHECK=PASS
```

Bản demo dùng danh sách `ArrayList` thông thường vì mỗi kịch bản chạy **tuần tự trên một thread**, không chia sẻ danh sách để nhiều thread ghi đồng thời. Khi áp dụng cách thu thập event trong một chương trình concurrent, hãy gắn event vào từng invocation hoặc dùng collector có hợp đồng đồng bộ rõ ràng; không tự thay `ArrayList` thành danh sách dùng chung rồi kỳ vọng sự kiện từ các request khác nhau vẫn có thứ tự tuyến tính hữu ích.

### 5.2. Vì sao dùng reflection và unwrap ngoại lệ?

`Proxy.newProxyInstance(...)` tạo một đối tượng triển khai interface `Service`; khi gọi method qua proxy, `InvocationHandler.invoke(...)` nhận `Method` và mảng đối số rồi chủ động chuyển tiếp xuống tầng tiếp theo. Với `method.invoke(next, args)`, ngoại lệ do method đích ném được reflection bọc trong `InvocationTargetException`.

Hàm `callNext(...)` lấy lại `wrapper.getCause()` để hai aspect thấy **ngoại lệ thực từ nghiệp vụ**, thay vì nhìn thấy một wrapper không thuộc ngữ nghĩa nghiệp vụ. Trong demo, `Service.execute` có thể ném `IllegalStateException` (unchecked), nên kết quả rõ ràng.

Với phương thức khai báo checked exceptions hoặc API AOP có quy tắc xử lý lỗi khác, việc truyền ngoại lệ cần theo đúng hợp đồng. Dynamic proxy có thể bọc checked throwable không được khai báo vào `UndeclaredThrowableException`; không nên tổng quát hóa behavior của demo cho mọi chữ ký phương thức.

### 5.3. Vì sao thứ tự được quyết định bằng phép bọc?

Cấu trúc:

```java
Service traceOutsideAudit =
        trace(audit(business, events), events);
```

được tạo từ trong ra ngoài:

1. `audit(business, events)` trả về proxy Audit gọi tiếp `business`.
2. `trace(innerProxy, events)` trả về proxy Trace gọi tiếp proxy Audit.
3. Caller gọi `traceOutsideAudit.execute("good")` nên Trace được đi vào trước.
4. Trace gọi tiếp Audit; Audit gọi tiếp nghiệp vụ.
5. Khi nghiệp vụ trả bình thường, Audit ghi `afterReturning` rồi `finally`, trả về Trace; Trace ghi `afterReturning` rồi `finally`.
6. Caller cuối cùng nhận `"ok:good"`.

Nếu đảo thứ tự tạo proxy, thứ tự vào và đi ra đảo tương ứng. Nếu chỉ đổi tên biến `traceOutsideAudit` thành `auditOutsideTrace` thì **không đổi được thứ tự**; phải thay đổi cấu trúc bọc hoặc cấu hình ưu tiên trong hệ thống AOP thật.

### 5.4. Giới hạn của mô hình proxy

Đây là bài thực hành **around-style interception** bằng proxy của Java, không phải một thư viện aspect tổng quát. Những khác biệt khi đưa kiến thức vào cơ chế weaving thật:

- Proxy JDK hoạt động qua interface; không tự động chặn mọi constructor, field access hoặc method call trong bytecode.
- Lời gọi không đi qua proxy có thể không được chặn; ví dụ lời gọi nội bộ trên chính target có đặc tính khác tùy công nghệ AOP.
- Một framework AOP có thể điều khiển precedence bằng metadata hoặc declaration thay vì gọi `trace(audit(...))`.
- Với nhiều loại advice khác nhau, thứ tự `before/after/around` chịu quy tắc ưu tiên và composition của framework; cần đọc hợp đồng cụ thể.
- Kết quả của bài chứng minh ngữ nghĩa của **hai wrapper đã tạo**, không chứng minh tất cả hệ thống AOP đều áp dụng cùng một cơ chế proxy.

## 6. Đọc kết quả theo từng lớp: chuỗi thành công

Trong kịch bản `trace > audit, success`:

| Bước | Component | Event | Điều gì xảy ra? |
| --- | --- | --- | --- |
| 1 | Trace | `Trace.before` | Caller đi vào wrapper ngoài |
| 2 | Audit | `Audit.before` | Trace gọi tiếp wrapper trong |
| 3 | Business | `Business.execute` | Nghiệp vụ bắt đầu |
| 4 | Business | `Business.return` | Nghiệp vụ chuẩn bị trả kết quả |
| 5 | Audit | `Audit.afterReturning` | Lời gọi xuống business trả bình thường |
| 6 | Audit | `Audit.finally` | Audit rời scope |
| 7 | Trace | `Trace.afterReturning` | Toàn bộ Audit đã hoàn tất |
| 8 | Trace | `Trace.finally` | Trace rời scope |

**Quy tắc tổng quát:** Với \(n\) around advice lồng nhau theo thứ tự ngoài vào trong \(A_1, A_2, \ldots, A_n\), mỗi advice có đúng một `proceed()`, không có advice nào short-circuit hoặc ném thêm ngoại lệ, thì chuỗi vào là:

\[
A_1.before \to A_2.before \to \cdots \to A_n.before \to J
\]

Sau khi J hoàn tất bình thường, các tầng rút lui theo thứ tự **ngược**:

\[
A_n.after \to A_{n-1}.after \to \cdots \to A_1.after
\]

Nếu mỗi tầng còn có `finally`, ta phải chèn `A_i.finally` ngay **sau nhánh after tương ứng và trước khi trả về tầng ngoài**. Vì vậy không đúng nếu chỉ liệt kê tất cả `afterReturning` rồi mới liệt kê tất cả `finally`.

Có thể tự kiểm tra bằng cách xem mỗi tầng như một cặp dấu ngoặc:

```text
Trace.before (
    Audit.before (
        Business
    ) Audit.afterReturning, Audit.finally
) Trace.afterReturning, Trace.finally
```

Nếu một chuỗi có `Trace.afterReturning` xuất hiện trước `Audit.finally` trong chính mẫu code này, đó là dấu hiệu mô hình thứ tự hoặc việc ghi sự kiện đã sai.

## 7. Đọc kết quả theo từng lớp: chuỗi ngoại lệ

Trong kịch bản `trace > audit, failure`:

1. Trace ghi `Trace.before`.
2. Audit ghi `Audit.before`.
3. Business ghi `Business.execute` và `Business.throw` rồi ném `IllegalStateException("rejected")`.
4. Reflection ở Audit unwrap ngoại lệ về `IllegalStateException`.
5. Audit bắt `Throwable`, ghi `Audit.afterThrowing:IllegalStateException` rồi ném tiếp lỗi gốc.
6. Khối `finally` của Audit chạy, ghi `Audit.finally`.
7. Trace nhận cùng exception, ghi `Trace.afterThrowing:IllegalStateException` rồi ném tiếp.
8. Khối `finally` của Trace ghi `Trace.finally`.
9. Caller bắt `IllegalStateException` và in `error=IllegalStateException:rejected`.

Không có event `afterReturning` trong đường lỗi này vì mỗi lời gọi `callNext` đều kết thúc bằng ngoại lệ. Nhánh `finally` vẫn chạy.

Một câu hỏi để kiểm tra suy luận: **Nếu Audit nuốt `IllegalStateException` và trả `"fallback"` thì Trace chạy nhánh nào?** Đáp án: nếu Audit thật sự trả giá trị bình thường mà không phát sinh lỗi tiếp theo, Trace nhìn thấy một return, nên ghi `Trace.afterReturning`. Bởi vậy trạng thái “nghiệp vụ từng ném lỗi” khác với “điều mà một advice bên ngoài quan sát được”.

Một câu hỏi khác: **Nếu Audit ghi sự kiện trong `finally` nhưng đoạn ghi đó ném exception thì chuyện gì xảy ra?** Trong Java, ngoại lệ ném từ `finally` có thể **thay thế** return value hoặc exception đang được truyền ra. Lời giải sử dụng thao tác thêm event đơn giản để cô lập bài toán thứ tự; trong hệ thống thật phải có chính sách rõ ràng cho lỗi ghi log/tracing/audit, đặc biệt nếu chúng là chức năng bắt buộc.

## 8. Vai trò của thứ tự khi hai aspect có nhiệm vụ khác nhau

Không phải cứ “aspect nào ngoài cũng được” miễn là chuỗi event đẹp. Precedence có thể ảnh hưởng đến những gì được đo hoặc quan sát.

Giả sử aspect Trace đo thời gian còn Audit thực hiện một thao tác ghi audit:

- **Trace bên ngoài Audit:** nếu đồng hồ bắt đầu trước `proceed()` và kết thúc sau khi tầng Audit trả, thời lượng đo có thể **bao gồm phần chi phí do Audit thực hiện bên trong**.
- **Audit bên ngoài Trace:** phép đo của Trace có thể **không bao gồm** phần logic trước/sau thuộc Audit bên ngoài, vì Trace chỉ sống trong khoảng gọi tầng được nó bọc.
- Nếu Audit có bước kiểm tra điều kiện và quyết định không gọi tiếp nghiệp vụ, việc Trace có được kích hoạt hay không phụ thuộc Trace nằm trong hay ngoài Audit.
- Nếu một aspect sửa tham số hoặc bọc exception, aspect ngoài có thể thấy giá trị đã sửa thay vì giá trị gốc.

Ví dụ minh họa khái niệm:

```text
Trace( Audit( Business ) )

Trace.start
  Audit.before + audit overhead
    Business
  Audit.after + audit overhead
Trace.stop

=> Duration của Trace có thể bao gồm overhead bên trong Audit.
```

Ngược lại:

```text
Audit( Trace( Business ) )

Audit.before + audit overhead
  Trace.start
    Business
  Trace.stop
Audit.after + audit overhead

=> Duration của Trace không bao gồm hai phần Audit bao ngoài nó.
```

Trong hệ thống thật, startup/JIT, lập lịch, GC, buffering và logging bất đồng bộ có thể ảnh hưởng kết quả đo; sơ đồ chỉ mô tả **ranh giới thời gian** theo vị trí của logic đồng bộ, không dự đoán con số cụ thể.

### 8.1. Quyết định thứ tự dựa trên mục tiêu

| Mục tiêu | Quy tắc thiết kế cần cân nhắc |
| --- | --- |
| Đo toàn bộ latency của call stack có các advice bên trong | Đặt timing/tracing ở tầng ngoài tương ứng |
| Đo riêng nghiệp vụ sau khi các thao tác phụ đã hoàn tất bên ngoài | Đặt timing ở gần nghiệp vụ hơn |
| Ghi audit cho mọi lần **attempt**, kể cả bị một aspect trong chặn | Audit có thể cần bao ngoài aspect có khả năng short-circuit |
| Chỉ ghi audit khi thao tác thực sự được thực thi | Đặt audit tại boundary có thể xác minh hành vi gốc đã chạy |
| Giữ context cho tất cả advice bên trong | Aspect thiết lập context cần bao ngoài những advice tiêu thụ context |
| Kiểm soát lỗi telemetry | Quy định rõ aspect nào được bắt/chuyển tiếp và có thể làm biến đổi exception |

Đây là **các tiêu chí lựa chọn**, không phải một precedence bắt buộc dùng cho mọi ứng dụng. Nếu dùng nhiều loại audit với ý nghĩa pháp lý/nghiệp vụ, không thể tùy tiện đổi thứ tự chỉ để tăng hiệu năng mà chưa xem lại các sự kiện bắt buộc phải ghi.

## 9. Kiểm chứng chuỗi thực thi: cách làm chắc chắn

Chương trình sử dụng một danh sách sự kiện và `List.of(...)` cho chuỗi kỳ vọng. Phép kiểm tra:

```java
if (!events.equals(expected)) {
    throw new AssertionError(...);
}
```

Kiểm tra **cả thứ tự và nội dung**. Nếu một sự kiện thiếu, thừa, trùng hoặc đảo vị trí, `List.equals(...)` trả false. Đây là bằng chứng mạnh hơn việc chỉ grep thấy `Trace.before` hoặc chỉ đếm tổng số log.

Khi viết kiểm thử thực tế:

1. Chọn một danh sách event theo từng invocation; dùng ID nếu có nhiều lời gọi.
2. Xác định expected trace **trước khi chạy**, từ hợp đồng advice và thứ tự cấu hình.
3. Thực hiện lời gọi thành công và lời gọi ném lỗi đã biết.
4. So sánh expected và actual, báo chỗ sai đầu tiên khi có mismatch.
5. Kiểm tra return value/exception identity, không chỉ event sequence.
6. Lặp lại khi đảo thứ tự, thay đổi pointcut hoặc thêm aspect thứ ba.
7. Kiểm thử cả lời gọi không được pointcut chọn: event từ hai aspect **không được xuất hiện**.
8. Nếu môi trường concurrent, không so sánh một chuỗi global trộn nhiều request với chuỗi của một request; phải lọc theo correlation ID hoặc tách bộ thu riêng.

### 9.1. Bảng expected trace dạng tóm tắt

| Thứ tự bọc | Thành công | Ngoại lệ |
| --- | --- | --- |
| Trace ngoài → Audit trong | Trace.before → Audit.before → Business → Audit.afterReturning/finally → Trace.afterReturning/finally | Trace.before → Audit.before → Business.throw → Audit.afterThrowing/finally → Trace.afterThrowing/finally |
| Audit ngoài → Trace trong | Audit.before → Trace.before → Business → Trace.afterReturning/finally → Audit.afterReturning/finally | Audit.before → Trace.before → Business.throw → Trace.afterThrowing/finally → Audit.afterThrowing/finally |

Bảng viết gọn bằng “/finally” để dễ nhìn; phép kiểm tra Java ở trên vẫn yêu cầu **từng event riêng lẻ** đúng thứ tự, không gộp hai sự kiện thành một.

### 9.2. Ba mức bằng chứng khác nhau

- **Bằng chứng cấu hình:** precedence của hai aspect đã được khai báo rõ và được build/deploy đúng.
- **Bằng chứng hành vi:** event thực tế ở success/failure khớp chuỗi dự đoán trên đúng join point.
- **Bằng chứng nghiệp vụ:** kết quả, exception và hiệu ứng nghiệp vụ không bị thay đổi ngoài hợp đồng.

Chỉ có output `CHECK=PASS` từ ví dụ chưa chứng minh mức thứ nhất cho một công nghệ AOP khác. Phải kiểm chứng phiên bản, rule weaving, pointcut và lời gọi thực tế trong ứng dụng sử dụng công nghệ đó.

## 10. Những biến thể nâng cao để tự thực hành

Sau khi chạy thành công lời giải, hãy thực hiện từng biến thể trên **một bản sao chương trình**, tính expected trace trước rồi mới sửa phép kiểm tra.

### Bài 1 — Audit quyết định không gọi tiếp

Yêu cầu: nếu `input` bằng `"blocked"`, Audit trả `"denied"` **mà không gọi `callNext(...)`**. Hãy đặt Trace ngoài Audit và so sánh với Audit ngoài Trace.

Gợi ý lập luận:

- Khi Trace ngoài Audit, Trace được vào trước; Audit có thể short-circuit, nên Trace vẫn nhìn thấy một return từ Audit.
- Khi Audit ngoài Trace, nếu Audit short-circuit trước khi đi vào tầng Trace thì **Trace không được chạy**.
- Nếu Audit đóng vai trò kiểm tra quyền bắt buộc, cần thiết kế chuỗi hành vi chính xác và tránh để request nhạy cảm đi qua xử lý không được phép.

**Không dùng hành vi short-circuit này làm ví dụ cho mọi aspect**. Một số aspect chỉ nên quan sát và luôn phải tiếp tục; một số aspect có chủ đích sửa luồng điều khiển như retry, cache hoặc enforcement.

### Bài 2 — Một aspect thay đổi exception

Yêu cầu: cho Audit chuyển `IllegalStateException` thành `IllegalArgumentException` tại nhánh `catch` và ném lại. Kiểm tra Trace bên ngoài thấy **loại lỗi mới** hay loại gốc.

Đáp án suy luận: Trace bên ngoài sẽ bắt lỗi từ Audit sau khi Audit ném lại, nên thấy loại lỗi mà Audit phát ra. Nếu thứ tự đảo, Trace nằm trong có thể thấy lỗi gốc trước khi Audit bao ngoài chuyển đổi. Đây là minh chứng rằng precedence không chỉ ảnh hưởng độ đẹp của log mà còn ảnh hưởng **error contract**.

Trong ứng dụng thật, việc chuyển ngoại lệ phải có lý do, bảo toàn cause khi phù hợp và không che mất dữ liệu chẩn đoán cần thiết.

### Bài 3 — Trace đo thời lượng bằng biến cục bộ

Yêu cầu: thêm `long start = System.nanoTime();` vào `TraceAspect.invoke`, tính `elapsedNanos` ở `finally` và ghi vào metric collector. So sánh ranh giới phép đo khi Trace nằm ngoài/ở trong Audit.

Không in con số nanosecond rồi assert giá trị chính xác vì phụ thuộc môi trường. Thay vào đó, kiểm tra rằng **đúng một mẫu thời gian** được ghi cho mỗi invocation, thời điểm ghi là khi thoát advice, và không dùng một field `startTime` chung giữa các yêu cầu.

### Bài 4 — Pointcut chỉ chọn một phương thức

Bổ sung `Service.health()` và quy định cả hai aspect chỉ áp dụng `execute(...)`. Kiểm tra:

- `execute(...)` đi qua cả hai aspect.
- `health()` trả bình thường mà không có sự kiện advice.
- Những tên method, overload và interface method khác nhau không vô tình khớp do chỉ kiểm tra prefix chuỗi.

Với dynamic proxy demo, có thể thêm điều kiện trên `method.getName()` và chữ ký; với AOP thật, ưu tiên matcher theo capability/cấu hình pointcut được hỗ trợ. Đừng vội kết luận có thể chặn mọi lời gọi nội bộ của đối tượng chỉ vì wrapper nhìn thấy một phương thức trên interface.

### Bài 5 — Advice tự gây lỗi

Yêu cầu: buộc `Audit.afterReturning` ném một ngoại lệ mô phỏng lỗi sink. Dự đoán nhánh nào của Trace chạy. Câu trả lời là Trace có thể thấy **thất bại từ Audit**, dù nghiệp vụ đã trả kết quả tốt. Đây là thay đổi ngữ nghĩa cần chủ động xử lý.

Điều tra thêm trường hợp `Audit.finally` ném lỗi, hoặc lỗi telemetry xuất hiện đồng thời với lỗi nghiệp vụ. Cần có chính sách bảo toàn lỗi gốc, ghi lỗi phụ an toàn và không tạo vòng lặp logger → advice → logger.

### Bài 6 — Một lời gọi có nhiều thread

Chạy hai request đồng thời. Mỗi request cần có **trace riêng** và context riêng. Không dùng field `currentRequestId` trong một aspect instance dùng chung; không dùng một `ArrayList` global không đồng bộ cho sự kiện từ nhiều thread. Có thể dùng collector theo invocation hoặc sự kiện bất biến chứa correlation ID, rồi nhóm theo ID khi kiểm chứng.

Nếu công việc trả về `CompletionStage` hay một đối tượng tương lai khác, một around advice đồng bộ có thể thoát **trước khi tác vụ hoàn thành**. Lúc đó cần tách chuỗi “thời điểm method trả về stage” và “thời điểm stage hoàn tất”; callback xử lý completion không nhất thiết chạy trên thread ban đầu. Thứ tự log giữa các tác vụ phải được diễn giải theo **happens-before** thực tế, không ghép chung mọi event thành một chuỗi tuyến tính tưởng tượng.

## 11. Những lỗi điển hình khi giải bài

### Lỗi 1 — Nhầm ngoài và trong

`trace(audit(business))` nghĩa là **Trace ngoài, Audit trong**. Đảo tên biến không đổi cấu trúc. Phải theo dõi wrapper mà caller thực sự giữ.

### Lỗi 2 — Nghĩ after chạy cùng chiều với before

Trong around advice, hoạt động đi ra chạy theo chiều ngược của hoạt động đi vào vì cấu trúc lồng nhau. Nếu Audit nằm trong Trace, Audit phải hoàn tất toàn bộ khối xử lý của nó, gồm `finally`, rồi Trace mới hoàn tất `callNext`.

### Lỗi 3 — Quên xử lý lỗi

Chỉ kiểm tra success không đủ. Một aspect logging tưởng “đúng thứ tự” có thể vô tình nuốt exception, biến lỗi thành return, hoặc để một lỗi logger che ngoại lệ từ nghiệp vụ.

### Lỗi 4 — Gọi `proceed()` không chính xác số lần

Around advice có quyền kiểm soát việc gọi tiếp. Nếu không gọi, nghiệp vụ có thể bị bỏ qua; nếu gọi hai lần, nghiệp vụ có thể có tác dụng phụ hai lần. Với demo, mục tiêu là **một lần gọi tầng tiếp theo** ở mỗi advice trên cả success và failure. Retry phải là một chính sách riêng, không phải hệ quả vô ý của cấu trúc catch.

### Lỗi 5 — Dựa vào thứ tự đăng ký không được cam kết

Một số hệ thống có thứ tự mặc định nhưng không bảo đảm ổn định; có nơi precedence được khai báo tường minh. Muốn đúng trong build khác hoặc sau nâng cấp, cần xác định hợp đồng thứ tự của công nghệ đang dùng và có test chứng minh.

### Lỗi 6 — Dùng dữ liệu thu thập bất đồng bộ làm bằng chứng thứ tự đồng bộ

Một event có thể được enqueue theo thứ tự A → B nhưng xuất hiện trên hệ thống tập trung theo thứ tự khác do worker, retry hoặc batching. Nếu cần kiểm tra **thứ tự gọi advice**, ghi vào collector đồng bộ gắn với invocation trong môi trường test; còn nếu cần kiểm tra **thứ tự phát tán từ hệ thống quan sát**, đó là một bài toán khác.

### Lỗi 7 — Dùng state dùng chung cho một invocation

Một field `startTime` hoặc `currentRequestId` trong aspect instance được dùng nhiều lần có thể bị ghi đè bởi request song song hoặc gọi lồng nhau. Đặt state theo invocation vào biến local hoặc scope riêng; nếu truyền bất đồng bộ thì quản lý context theo logical task.

### Lỗi 8 — Quá chú trọng chuỗi event mà quên tác động nghiệp vụ

Bài test nên kiểm tra cả return value/exception, số lần gọi nghiệp vụ và mức độ an toàn của logging. Một chương trình có thứ tự event “đẹp” nhưng trả sai kết quả hoặc chạy nghiệp vụ hai lần vẫn sai.

## 12. Checklist kiểm thử khi chuyển sang công cụ AOP thật

Trước khi coi bài làm hoàn tất trong một hệ thống sử dụng pointcut/weaving thực tế, hãy đối chiếu:

- [ ] Tìm đúng join point nghiệp vụ mà **cả hai aspect thực sự khớp**.
- [ ] Định nghĩa precedence của hai aspect rõ ràng theo tài liệu công nghệ.
- [ ] Kiểm tra success: outer.before → inner.before → business → inner.after/finally → outer.after/finally.
- [ ] Kiểm tra exception: mỗi tầng bắt và truyền đúng lỗi, `finally` vẫn chạy.
- [ ] Đảo precedence: expected trace đảo tương ứng mà kết quả nghiệp vụ giữ đúng.
- [ ] Không có advice khác vô tình tham gia cùng join point làm thay đổi trace.
- [ ] Pointcut không chặn logger, metric recorder, proxy helper hoặc chính công cụ quan sát gây đệ quy.
- [ ] Các ràng buộc về lời gọi nội bộ, proxy, classloader, bridge method hoặc weaving time đã được kiểm tra đúng công nghệ.
- [ ] Có test âm tính cho method **không** được pointcut chọn.
- [ ] Nếu runtime có concurrency, events/context được cô lập theo invocation.
- [ ] Nếu workflow bất đồng bộ, thứ tự completion không bị đánh đồng với thứ tự return đồng bộ.
- [ ] Advice không làm lộ dữ liệu nhạy cảm, không che lỗi gốc và không thêm overhead quá giới hạn.
- [ ] Kết quả kiểm chứng đi kèm artifact, phiên bản Java/công cụ và cấu hình precedence để tái lập.

## 13. Tiêu chí tự chấm bài tập

| Tiêu chí | Điểm gợi ý | Bằng chứng |
| --- | ---: | --- |
| Mô tả đúng pointcut, join point và hai trách nhiệm | 15 | Thiết kế ngắn, phân biệt Trace/Audit |
| Xác định rõ aspect ngoài/trong | 15 | Sơ đồ lồng hoặc cấu hình precedence |
| Chuỗi success chính xác | 15 | So khớp expected event đầy đủ |
| Chuỗi failure chính xác và ngoại lệ gốc được giữ | 15 | Test exception và `finally` |
| Đảo thứ tự, kiểm chứng khác biệt | 15 | Cặp kịch bản Trace/Audit và Audit/Trace |
| Code Java 17+ chạy được và assert rõ ràng | 15 | Lệnh biên dịch/chạy, `CHECK=PASS` |
| Giải thích giới hạn, lỗi thường gặp và bối cảnh thực tế | 10 | Phần phân tích về công cụ, concurrency, logging |

**Điểm tối đa: 100.** Phần chấm điểm là gợi ý để tự đánh giá; quan trọng hơn cả là giải thích được vì sao sự kiện đi ra xuất hiện theo thứ tự ngược, và vì sao việc bắt/biến đổi lỗi ở tầng trong ảnh hưởng tới những gì tầng ngoài nhìn thấy.

## 14. Tổng kết kiến thức

Với hai around advice đồng bộ được bọc theo thứ tự **A ngoài, B trong**, đường thành công có cấu trúc:

```text
A.before
  B.before
    Business
  B.afterReturning
  B.finally
A.afterReturning
A.finally
```

Đường lỗi (khi cả hai advice truyền tiếp lỗi) có cấu trúc tương tự, nhưng thay `afterReturning` bằng `afterThrowing` và giữ nguyên `finally`.

Khi đảo thứ tự bọc, thứ tự vào/ra đổi theo. Khi một advice short-circuit, retry, biến đổi ngoại lệ, phát lỗi mới hoặc xử lý bất đồng bộ, chuỗi cần suy luận lại từ **hợp đồng thực tế**. Một bài giải đúng phải kiểm chứng **thứ tự, số lần thực thi, kết quả và ngoại lệ**, đồng thời không giả định có một cú pháp precedence hoặc một loại join point dùng chung cho mọi công nghệ AOP.

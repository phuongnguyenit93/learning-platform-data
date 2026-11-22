# Advice là hành vi được thực hiện tại điểm đã chọn

## 1. Advice trong mô hình lập trình hướng khía cạnh

Trong **Aspect-Oriented Programming (AOP)**, **advice** là hành vi bổ sung được chạy tại một điểm thực thi được lựa chọn. Nếu **pointcut** trả lời “chọn điểm nào?”, **advice** trả lời “phải làm gì tại điểm ấy và khi nào?”. Advice thường dùng cho logging, audit, đo hiệu năng, truy vết, kiểm soát truy cập ở ranh giới kỹ thuật hoặc quản lý tài nguyên. Nó giúp các chính sách cắt ngang không trộn vào thuật toán nghiệp vụ.

Ví dụ, một thao tác `pay()` có thể cần ghi “bắt đầu”, thực hiện thanh toán, ghi “thành công” hoặc “thất bại”, và luôn cập nhật số liệu đo thời gian. Tính tiền và kiểm tra số dư vẫn là nghiệp vụ; những hành vi quan sát bao quanh nó có thể được mô hình hóa bằng advice.

Các thành phần liên hệ với nhau:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Join point** | Một điểm thực thi có thể can thiệp | Một lần thực thi hoặc gọi phương thức `pay()` |
| **Pointcut** | Biểu thức/điều kiện chọn tập join point | Chỉ chọn các thao tác thanh toán |
| **Advice** | Hành vi được kích hoạt tại điểm đã chọn | Ghi audit trước/sau thanh toán |
| **Aspect** | Mô-đun chứa chính sách cắt ngang, thường gồm pointcut và advice | Chính sách audit thanh toán |
| **Target** | Đối tượng hoặc logic gốc | Bộ xử lý thanh toán |
| **Weaving** | Cách kết hợp aspect vào đường thực thi | Proxy, biến đổi mã lúc biên dịch hoặc nạp lớp |

**Advice và pointcut là hai quyết định khác nhau.** Việc có một hàm tên `beforeAudit` không tự động khiến nó được gọi tại mọi thao tác. Cơ chế AOP chỉ kích hoạt khi join point phát sinh, được pointcut chọn và nằm trong phạm vi mà công nghệ can thiệp được.

## 2. Những loại advice quan trọng

Các tên gọi sau là mô hình khái niệm phổ biến của AOP. Khả năng và cú pháp cụ thể phụ thuộc vào cơ chế thực thi, vì vậy không suy luận rằng mọi bộ máy AOP có chính xác cùng tập tính năng.

| Loại advice | Khi chạy | Dữ liệu có thể biết | Cách dùng tiêu biểu |
| --- | --- | --- | --- |
| **Before** | Trước khi logic gốc được chuyển quyền điều khiển | Ngữ cảnh, tham số đầu vào | Ghi bắt đầu, kiểm tra điều kiện kỹ thuật |
| **After returning** | Sau khi logic gốc hoàn tất bình thường | Kết quả trả về, kể cả `null` | Ghi thành công, thống kê kết quả |
| **After throwing** | Khi logic gốc thoát bằng ngoại lệ | Ngoại lệ phát sinh | Audit thất bại, thống kê lỗi |
| **After / finally** | Khi phạm vi được bao kết thúc bất kể thành công/lỗi | Tình trạng kết thúc theo hợp đồng cơ chế | Dọn tài nguyên, đo thời gian, bộ đếm |
| **Around** | Bao lấy lời thực thi và quyết định chuyển tiếp | Đầu vào, kết quả, ngoại lệ, quyền gọi tiếp | Thời gian, cache, kiểm soát thực thi, retry |

### Before

Before chạy trước khi chuyển vào thao tác gốc. Nó thích hợp với hành vi như gắn correlation ID hoặc thông báo thao tác bắt đầu. Advice có thể tự gây lỗi hoặc có cơ chế từ chối thao tác, nhưng cách ngăn việc chạy target phải phù hợp hợp đồng AOP đang dùng. **Không đồng nhất before với quy tắc nghiệp vụ**: kiểm tra “số tiền phải dương” thường thuộc logic miền, trong khi kiểm tra danh tính đã xác thực ở ranh giới có thể là chính sách cắt ngang.

### After returning

After returning chỉ chạy khi thao tác hoàn tất bình thường. Trả về `null` vẫn là trả về bình thường; ném ngoại lệ thì không. Nếu advice quan sát kết quả, nó phải tôn trọng kiểu trả về và tránh vô tình sửa đối tượng mutable mà caller cũng đang dùng.

### After throwing

After throwing chạy theo nhánh ngoại lệ từ thao tác được quan sát. Đây không đồng nghĩa với “ngoại lệ đã được xử lý”. Một advice chỉ ghi lỗi nên chuyển tiếp ngoại lệ theo đúng hợp đồng. Việc đổi lỗi nghiệp vụ thành một thông báo “thành công” làm caller hiểu sai trạng thái thực thi.

### After / finally

After/finally dành cho việc phải thực hiện ở cả nhánh thành công và thất bại, như giải phóng tài nguyên hoặc chốt số liệu đo. Từ “finally” chỉ có ý nghĩa **trong phạm vi đã thực sự được bao**: nếu lời gọi không đi qua ranh giới aspect/proxy, advice không chạy. Ngay cả khi có `finally`, việc code chính advice ném ngoại lệ cũng có thể ảnh hưởng ngoại lệ gốc.

### Around

Around nắm quyền bao quanh lời thực thi: làm việc trước, **gọi tiếp**, làm việc sau, hoặc có chủ đích quyết định không gọi tiếp. Một advice `around` có thể hỗ trợ các chính sách như cache, retry hoặc timeout, nhưng cần đặc biệt cẩn trọng vì nó có khả năng thay đổi số lần thực thi, kết quả hoặc ngoại lệ.

## 3. Điều gì xảy ra tại một join point đã chọn?

Hãy giả sử pointcut chọn phương thức `pay(int)` nhưng không chọn `health()`. Một sơ đồ ý niệm:

~~~text
Caller
  |
  +-- health() ------------------------> Target.health()
  |                                      (không khớp pointcut)
  |
  +-- pay(7) --> [Điểm được chọn]
                    |
                    v
                [Before]
                    |
                    v
              [Target.pay(7)]
                    |
            +-------+--------+
            |                |
       return bình thường   ném lỗi
            |                |
            v                v
    [After returning]  [After throwing]
            |                |
            +--------+-------+
                     v
               [After/finally]
                     |
                     v
              Caller nhận kết quả
                 hoặc ngoại lệ
~~~

Sơ đồ không quy định thứ tự của tất cả công nghệ AOP. Khi nhiều aspect cùng khớp, thứ tự cụ thể cần được định nghĩa theo cơ chế precedence. Ngoài ra, **join point là lời gọi** và **join point là lần thực thi** không nhất thiết là một: nơi phát sinh lời gọi và nơi thực thi có thể khác nhau.

Để một advice thực sự kích hoạt, cần xác định đủ bốn điều kiện: loại join point được hỗ trợ, pointcut khớp, đường chạy đi qua vị trí đã weaving/proxy, và advice được kết hợp thành công theo thứ tự đã khai báo.

## 4. Ngữ cảnh và dữ liệu mà advice có thể quan sát

Tùy bộ máy AOP, một advice có thể lấy tên/chữ ký phương thức, thông tin kiểu, annotation, target, đối tượng gọi, tham số, giá trị trả về, ngoại lệ hoặc thông tin ngữ cảnh như correlation ID. Around thường được trao một thao tác chuyển tiếp gọi là `proceed`.

Không phải tất cả các loại advice đều thấy tất cả dữ liệu. **Before** chưa thể quan sát kết quả chưa được tính; **after returning** có kết quả bình thường; **after throwing** có nguyên nhân lỗi; **around** có thể kiểm soát cách chuyển tiếp và quan sát nhánh kết thúc.

Các giá trị đầu vào có thể là mutable. Nếu advice sửa danh sách, mảng hoặc đối tượng truyền vào, nó có thể làm thay đổi hành vi nghiệp vụ. Với audit, tracing và metrics, nên ưu tiên **quan sát** và xử lý dữ liệu tối thiểu cần thiết. Không đưa token, mật khẩu, dữ liệu cá nhân hoặc toàn bộ nội dung thanh toán vào log chỉ vì join point cho phép truy cập.

## 5. Ví dụ Java 17+: một điểm chọn, nhiều thời điểm chạy advice

Ta sử dụng **JDK dynamic proxy** để minh họa cơ chế chọn điểm và bao quanh lời gọi thông qua interface. Đây là một bản dựng nhỏ để học cách advice hoạt động, **không phải một engine AOP đầy đủ**. Bộ chọn đơn giản là `method.getName().equals("pay")`; `Proceeding` là giao diện chuyển tiếp do ví dụ tự định nghĩa.

Tạo tệp `AdviceDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class AdviceDemo {
    interface Payment {
        String pay(int amount);
        String health();
    }

    static final class PaymentCore implements Payment {
        @Override
        public String pay(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            System.out.println("BUSINESS pay " + amount);
            return "receipt:" + amount;
        }

        @Override
        public String health() {
            return "OK";
        }
    }

    @FunctionalInterface
    interface Proceeding {
        Object proceed() throws Throwable;
    }

    static final class AuditAdvice {
        int finishedCalls;

        Object around(Method method, Proceeding next) throws Throwable {
            System.out.println("AROUND enter");
            try {
                System.out.println("BEFORE " + method.getName());
                Object result;
                try {
                    result = next.proceed();
                } catch (Throwable failure) {
                    System.out.println("AFTER_THROWING "
                            + failure.getClass().getSimpleName());
                    throw failure;
                }
                System.out.println("AFTER_RETURNING " + result);
                return result;
            } finally {
                finishedCalls++;
                System.out.println("AFTER_FINALLY");
                System.out.println("AROUND exit");
            }
        }
    }

    static Object callTarget(Object target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapper) {
            throw wrapper.getCause();
        }
    }

    static Payment withAdvice(Payment target, AuditAdvice advice) {
        return (Payment) Proxy.newProxyInstance(
                Payment.class.getClassLoader(),
                new Class<?>[] { Payment.class },
                (proxy, method, args) -> {
                    if (!method.getName().equals("pay")) {
                        return callTarget(target, method, args);
                    }
                    return advice.around(
                            method, () -> callTarget(target, method, args));
                });
    }

    public static void main(String[] args) {
        AuditAdvice advice = new AuditAdvice();
        Payment payment = withAdvice(new PaymentCore(), advice);
        System.out.println("HEALTH " + payment.health());
        System.out.println("RESULT " + payment.pay(7));
        try {
            payment.pay(0);
        } catch (IllegalArgumentException failure) {
            System.out.println("CALLER " + failure.getMessage());
        }
        System.out.println("FINALLY_COUNT " + advice.finishedCalls);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AdviceDemo.java
java AdviceDemo
~~~

Đầu ra chính xác (đã kiểm chứng trên JDK với `javac --release 17`):

~~~text
HEALTH OK
AROUND enter
BEFORE pay
BUSINESS pay 7
AFTER_RETURNING receipt:7
AFTER_FINALLY
AROUND exit
RESULT receipt:7
AROUND enter
BEFORE pay
AFTER_THROWING IllegalArgumentException
AFTER_FINALLY
AROUND exit
CALLER amount must be positive
FINALLY_COUNT 2
~~~

Cách diễn giải:

1. `health()` không khớp pointcut, nên không có dòng audit nào.
2. `pay(7)` khớp: around vào → before → nghiệp vụ → after returning → finally → around ra → caller nhận `receipt:7`.
3. `pay(0)` khớp: around vào → before → nghiệp vụ ném `IllegalArgumentException` → after throwing → finally → around ra → caller nhận lỗi gốc. Không có `AFTER_RETURNING` trên nhánh lỗi.
4. `finishedCalls` bằng `2` bởi chỉ hai lời gọi `pay()` đi qua `AuditAdvice`; `health()` không được tính.

`callTarget()` bóc `InvocationTargetException` do reflection tạo ra. Nhờ vậy advice thấy loại ngoại lệ thực tế thay vì lớp bọc từ API phản chiếu. Code `PaymentCore` không cần biết advice hay proxy đang tồn tại: lớp đó tập trung vào nghiệp vụ.

## 6. Around và `proceed`: quyền lực đi kèm trách nhiệm

Around không chỉ “chạy ở trước và sau”. Nó có thể quyết định số lần target được thực thi. Bảng sau nêu rõ tác động:

| Quyết định trong around | Hệ quả | Điều kiện thiết kế |
| --- | --- | --- |
| Gọi `proceed` đúng một lần | Target có thể chạy đúng một lần | Giữ kết quả, ngoại lệ và hợp đồng |
| Không gọi `proceed` | Target không chạy | Cache hit hoặc từ chối có chủ đích, được phép |
| Gọi `proceed` nhiều lần | Target có thể thực hiện nhiều lần | Retry có giới hạn, phân loại lỗi và idempotency |
| Bắt rồi nuốt ngoại lệ | Caller không biết thao tác gốc lỗi | Chỉ làm nếu đặc tả API cho phép |
| Chuyển kết quả hoặc ngoại lệ | Caller thấy hợp đồng khác ban đầu | Phải được mô tả và kiểm thử rõ ràng |

Một minh họa ý niệm cho around đo thời gian (không phải chương trình chạy độc lập):

~~~java
Object measure(Proceeding next) throws Throwable {
    long started = System.nanoTime();
    try {
        return next.proceed();
    } finally {
        long nanos = System.nanoTime() - started;
        recordDuration(nanos); // Dịch vụ metrics giả định.
    }
}
~~~

`System.nanoTime()` phù hợp để đo thời lượng, không phải thời điểm theo lịch. Nếu `recordDuration()` ném ngoại lệ trong `finally`, lỗi ấy có thể che lỗi gốc đang thoát ra; việc ghi metrics thất bại phải có chính sách xử lý riêng. Đừng tự chọn “nuốt tất cả lỗi” hay “luôn ném lỗi metrics” khi chưa định nghĩa yêu cầu.

**Retry đặc biệt nhạy cảm.** Gọi `proceed` lần nữa có thể thu tiền hai lần hoặc tạo hai đơn hàng. Chỉ retry khi xác định được lỗi tạm thời, giới hạn số lần, không retry những lỗi vĩnh viễn và có cơ chế chống lặp an toàn đối với thao tác có tác dụng phụ.

## 7. Nhiều advice khớp cùng một điểm: thứ tự thực thi

Một phương thức có thể đồng thời khớp advice đo thời gian, audit và kiểm quyền. Nếu chúng được bao theo thứ tự ngoài vào trong:

~~~text
Timing.enter
  Audit.enter
    Authorization.enter
      Business
    Authorization.exit
  Audit.exit
Timing.exit
~~~

Ở nhánh bình thường, wrapper ngoài bắt đầu trước và kết thúc sau wrapper trong. Với `finally`, các tầng đã đi vào sẽ được tháo ngăn xếp theo thứ tự ngược khi một tầng trong ném lỗi. Nhưng **thứ tự aspect không được bảo đảm bởi tên lớp hoặc vị trí trong file**; hãy xác định rõ thứ tự theo quy tắc precedence hoặc cấu hình của cơ chế AOP.

Thứ tự thay đổi ý nghĩa của số liệu:

- Timing bao cả kiểm quyền thì đo thời gian xử lý toàn bộ yêu cầu; timing nằm phía trong bước kiểm quyền thì không tính thời gian kiểm quyền.
- Audit nằm sau bước kiểm quyền có thể bỏ lỡ việc ghi lại lời gọi bị từ chối trước khi nghiệp vụ chạy. Nếu cần ghi từ chối, đặt audit bao ngoài hoặc bổ sung một đường ghi rõ ràng.
- Nếu retry ở ngoài metrics, mỗi lần thử có thể tạo một phép đo; nếu metrics ở ngoài retry, một phép đo có thể tính tổng thời gian các lần thử.
- Nếu advice ngoài đổi ngoại lệ thành kết quả mặc định, caller không nhận được lỗi vốn đã được advice trong quan sát.

Vì vậy, thiết kế cần nêu chính sách ưu tiên, đường lỗi, số lần chạy target, và điều kiện bắt đầu/kết thúc của mỗi advice.

## 8. Phạm vi thực thi và các góc cạnh nâng cao

### 8.1. Lời gọi trực tiếp, self-invocation và proxy

JDK dynamic proxy trong ví dụ chỉ can thiệp lời gọi **qua proxy**, trên interface được khai báo. Nếu thực hiện `new PaymentCore().pay(7)` trực tiếp, `AuditAdvice` không chạy. Khi target gọi phương thức khác của chính nó qua `this`, lời gọi nội bộ có thể không đi qua proxy; hiện tượng này thường gọi là **self-invocation**.

Không được mặc định rằng một bộ máy proxy can thiệp được constructor, phương thức `private`, truy cập field, `final` hay bất kỳ điểm thực thi nào. Một cách weaving ở mức bytecode có thể có tập join point khác. Phạm vi được hỗ trợ phải được kiểm tra theo cơ chế áp dụng thực tế.

### 8.2. Ngoại lệ do advice tự tạo

Lỗi không chỉ phát sinh từ target. `before`, `after returning`, `after throwing`, `finally` hoặc bộ chuyển tiếp đều có thể tự gây ngoại lệ. Trong ví dụ, `AFTER_THROWING` chỉ bao đường gọi `next.proceed()`, vì vậy nó đại diện cho lỗi tầng tiếp theo, không coi mọi lỗi logging sau đó là lỗi nghiệp vụ. Cần xác định khi nào lỗi hạ tầng audit gây thất bại thao tác, khi nào được báo riêng, và làm sao bảo toàn nguyên nhân gốc.

### 8.3. Bất đồng bộ: return chưa đồng nghĩa với hoàn tất

Một phương thức có thể trả về `CompletableFuture` trước khi tác vụ nền hoàn thành. `After returning` tại điểm phương thức trả về chỉ biết đã nhận một Future, **không bảo đảm công việc bên trong đã thành công**. Muốn đo tổng thời gian hoặc audit kết quả cuối, cần theo dõi sự kiện hoàn tất của Future bằng cơ chế phù hợp. Ngữ cảnh tracing cũng có thể cần được truyền rõ qua biên giới thread.

### 8.4. Trạng thái dùng chung và đồng thời

Advice có thể dùng chung một instance cho nhiều lời gọi. Biến `int finishedCalls` trong ví dụ là minh họa tuần tự; nếu nhiều thread cùng cập nhật, phép `++` không an toàn đồng thời. Với bộ đếm chung, có thể dùng `AtomicLong`, `LongAdder` hoặc hệ thống metrics thích hợp. Không cất tham số hay dữ liệu nhạy cảm của lần gọi hiện tại trong field dùng chung nếu chưa có cơ chế cô lập.

### 8.5. Chi phí và khả năng quan sát

Advice chạy tại các điểm được chọn; pointcut quá rộng có thể làm tăng chi phí reflection, ghi log, đo metrics hoặc bùng nổ sự kiện. Hãy đo overhead trên tải đại diện và dùng pointcut đủ cụ thể. Một chính sách ẩn trong AOP cũng cần tài liệu: tìm được pointcut ở đâu, thứ tự advice ra sao, những phương thức nào bị ảnh hưởng và cách theo dấu khi có lỗi.

## 9. Kiểm thử advice như một hợp đồng thực thi

| Tình huống | Đường gọi | Kết quả cần kiểm chứng |
| --- | --- | --- |
| Target thành công | `pay(7)` qua proxy | Before → target → after returning → finally; return giữ nguyên |
| Target ném lỗi | `pay(0)` qua proxy | Before → after throwing → finally; ngoại lệ gốc còn nguyên |
| Pointcut không khớp | `health()` qua proxy | Không có audit, không tăng bộ đếm |
| Đi đường không được can thiệp | `PaymentCore.pay()` trực tiếp | Không kích hoạt advice trên proxy |
| Nhiều advice | Hai wrapper cùng khớp | Thứ tự đúng, số lần thực thi nghiệp vụ đúng |
| Advice ném lỗi | Hệ thống ghi audit gặp lỗi | Xử lý theo chính sách đã mô tả, không vô tình che lỗi gốc |
| Async | Target trả `CompletableFuture` | Phân biệt trả Future với tác vụ hoàn tất |

Kiểm thử trực tiếp phương thức `around()` là kiểm thử logic bên trong; nó **không đủ** chứng minh pointcut chọn đúng hoặc weaving/proxy áp dụng đúng. Phải gọi qua ranh giới tích hợp thật, thử cả trường hợp khớp và không khớp.

Một tiêu chuẩn cơ bản của advice chỉ quan sát: **kết quả, ngoại lệ và số lần thực thi nghiệp vụ phải giữ nguyên**. Nếu advice cố ý thay đổi một trong ba điều đó (ví dụ cache, retry, từ chối), hãy coi đó là hợp đồng chức năng có kiểm thử riêng.

## 10. Sai lầm thường gặp

1. **Lẫn advice với pointcut:** advice là hành vi; pointcut mới xác định điểm áp dụng.
2. **Gọi mọi hành vi tái sử dụng là advice:** quy tắc tính toán và bất biến nghiệp vụ vẫn cần sống trong logic miền.
3. **Cho rằng after returning chạy cả khi lỗi:** nó chỉ chạy khi có kết thúc bình thường.
4. **Cho rằng after throwing tự xử lý hết ngoại lệ:** ghi lỗi khác với quyết định nuốt, đổi hoặc ném tiếp.
5. **Dùng around cho mọi việc:** nếu chỉ cần quan sát trước/sau, hãy ưu tiên hành vi đơn giản ít quyền can thiệp.
6. **Quên `proceed` hoặc gọi nhiều lần vô ý:** làm mất hoặc nhân đôi tác dụng phụ.
7. **Mặc định advice được chạy ở mọi đường gọi:** phải kiểm tra proxy, weaving, loại join point và self-invocation.
8. **Không quy định thứ tự nhiều aspect:** có thể audit thiếu sự kiện từ chối hoặc đo sai phạm vi.
9. **Để lỗi quan sát che lỗi nghiệp vụ:** cần thiết kế cách xử lý lỗi trong advice.
10. **Ghi log dữ liệu nhạy cảm và giữ state theo lời gọi trong field dùng chung:** dễ rò rỉ thông tin hoặc gặp race condition.

## 11. Câu hỏi tự kiểm tra

**Q1.** Pointcut chỉ khớp `pay()`, vậy `health()` có kích hoạt advice không?  
**Đáp án:** Không, nếu `health()` không được bộ chọn chấp nhận.

**Q2.** `pay()` ném `IllegalArgumentException`. Nhánh nào có thể chạy?  
**Đáp án:** `after throwing` quan sát ngoại lệ; phần `finally` trong phạm vi bao vẫn chạy. `after returning` không có kết quả bình thường để quan sát.

**Q3.** Vì sao around có thể gây lỗi nghiêm trọng?  
**Đáp án:** Nó quyết định có chuyển tiếp không, bao nhiêu lần chuyển tiếp và trả gì cho caller; nếu không kiểm soát, nó có thể nhân đôi thao tác hoặc che ngoại lệ.

**Q4.** Một Future vừa được trả về đã đủ kết luận tác vụ thành công chưa?  
**Đáp án:** Chưa. Hoàn tất phương thức trả Future khác với hoàn tất công việc bất đồng bộ bên trong.

**Q5.** Vì sao kiểm thử riêng logic advice chưa đủ?  
**Đáp án:** Vì cần xác minh cả chọn join point, đường đi qua proxy/weaving, thứ tự thực thi và hợp đồng đầu ra.

## 12. Kết luận

**Advice là hành vi được thực thi tại một join point đã được chọn**, còn pointcut xác định tập điểm mà chính sách cần áp dụng. Phân biệt `before`, `after returning`, `after throwing`, `after/finally` và `around` giúp dự đoán chính xác điều xảy ra khi target thành công, thất bại hoặc được bỏ qua. Khi thiết kế advice, phải nêu rõ **điểm được chọn, ngữ cảnh quan sát, thời điểm thực thi, quyền chuyển tiếp, thứ tự với các advice khác và hợp đồng trả về/lỗi**. Nhờ vậy hành vi cắt ngang được tái sử dụng mà nghiệp vụ vẫn rõ ràng và kiểm thử được.
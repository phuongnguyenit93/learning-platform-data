# Aspect là đơn vị đóng gói mối quan tâm cắt ngang

Trong lập trình hướng khía cạnh (*Aspect-Oriented Programming*, AOP), **aspect** là đơn vị mô-đun hóa một **mối quan tâm cắt ngang** (*cross-cutting concern*): một chính sách hoặc hành vi cần tác động nhất quán tại nhiều vị trí của chương trình. Thay vì rải cùng một đoạn mã vào các lớp nghiệp vụ, aspect gom **hành vi cần thực hiện** và **quy tắc xác định nơi áp dụng** thành một đơn vị có tên, có trách nhiệm, có thể xem xét và kiểm thử.

Ví dụ: `CheckoutService`, `ReportService` và `MessageService` thực hiện những nghiệp vụ khác nhau, nhưng đều cần ghi lại thời gian thực thi. Nếu từng phương thức tự ghi thời gian, logic kỹ thuật sẽ bị phân tán. Ta có thể tạo một aspect `ExecutionTiming` để nêu quy tắc đo thời gian tại những ranh giới được chọn. Ba lớp nghiệp vụ vẫn tập trung vào mục đích riêng.

**Điểm cốt lõi:** Một aspect không chỉ là “một hàm chạy trước/sau”. Aspect thể hiện một *chính sách xuyên suốt* cùng cách gắn chính sách ấy vào chương trình. AOP nói chung là mô hình thiết kế và kết hợp các đơn vị này; cú pháp định nghĩa aspect, tập join point và kỹ thuật thực thi phụ thuộc hệ thống AOP cụ thể.

## 1. Vì sao cần một đơn vị đóng gói riêng?

Mô-đun thông thường thường được tổ chức theo các trách nhiệm dọc, chẳng hạn “xử lý đơn hàng”, “quản lý người dùng”, “tạo báo cáo”. Một số yêu cầu lại cắt qua nhiều trách nhiệm dọc: logging, tracing, kiểm toán (*audit*), đo hiệu năng, kiểm soát truy cập hoặc quản lý ngữ cảnh tài nguyên.

Hai hiện tượng thường gặp khi xử lý trực tiếp tại từng điểm:

- **Scattering – phân tán:** Một quy tắc chung xuất hiện trong nhiều phương thức hoặc lớp. Khi quy tắc thay đổi, phải sửa nhiều vị trí.
- **Tangling – đan xen:** Một phương thức vừa thực hiện nghiệp vụ vừa chứa nhiều đoạn xử lý kỹ thuật không trực tiếp mô tả nghiệp vụ.

Ví dụ minh họa ý tưởng, **không phải chương trình Java độc lập**:

```java
// BEFORE: ba nơi có cùng mẫu xử lý kỹ thuật.
void createOrder() {
    audit("createOrder: begin");
    createOrderCore();
    audit("createOrder: done");
}

void cancelOrder() {
    audit("cancelOrder: begin");
    cancelOrderCore();
    audit("cancelOrder: done");
}

void submitReport() {
    audit("submitReport: begin");
    submitReportCore();
    audit("submitReport: done");
}
```

Đoạn này còn thiếu xử lý ngoại lệ, nghĩa là bản ghi “done” không xuất hiện khi thao tác thất bại. Nếu bổ sung nhánh lỗi và thông tin ngữ cảnh ở từng phương thức, mã lặp sẽ phình to và dễ khác nhau giữa các nơi.

Với AOP, ta hướng đến:

```text
Mô-đun nghiệp vụ             Mô-đun aspect
------------------          ----------------------------
Order operations             Audit aspect
Report operations    <----   - Chọn thao tác cần audit
Message operations           - Trước: ghi nhận bắt đầu
                             - Thành công: ghi nhận kết quả
                             - Lỗi: ghi nhận thất bại

        Cơ chế AOP kết hợp hai phía tại điểm thực thi được chọn.
```

Đây là sự tách **trách nhiệm sở hữu**: nghiệp vụ quyết định *làm việc gì*; aspect quản lý một chính sách *áp dụng tại các ranh giới nào và theo cách nào*. Việc tách này có ý nghĩa khi nó làm trách nhiệm rõ ràng hơn, không phải chỉ để giảm vài dòng code.

## 2. Những thành phần được đóng gói trong một aspect

Một mô hình aspect thường liên hệ các khái niệm sau:

| Thành phần | Vai trò trong aspect | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Concern** | Mục đích duy nhất của mô-đun | Aspect đang giải quyết vấn đề xuyên suốt nào? |
| **Join point** | Điểm thực thi *có thể* chịu tác động, theo mô hình AOP đang dùng | Có những điểm thực thi nào được hệ thống hỗ trợ? |
| **Pointcut** | Quy tắc chọn một tập join point | Chính xác thao tác nào thuộc phạm vi áp dụng? |
| **Advice** | Hành vi bổ sung tại join point được chọn | Trước, sau, khi lỗi hay bao quanh cần làm gì? |
| **Context** | Thông tin được phép quan sát/đưa vào advice | Có thể đọc phương thức, đối số, kết quả hay ngữ cảnh nào? |
| **Ordering/precedence** | Quy tắc kết hợp khi nhiều aspect cùng khớp | Aspect nào bao ngoài, aspect nào ở trong? |
| **Lifecycle/state** | Cách tồn tại và quản lý trạng thái, nếu có | State dùng chung hay theo đối tượng/lần gọi? |

**Không phải mọi công cụ đều yêu cầu khai báo các mục trên cùng một file hoặc class.** Có công cụ diễn đạt pointcut và advice bằng khai báo chuyên biệt, có công cụ biểu diễn aspect qua cấu hình và interceptor, có công cụ ghép vào bytecode. Khái niệm “aspect là đơn vị đóng gói” mô tả **ranh giới trách nhiệm**, không ép một hình thức cú pháp duy nhất.

### 2.1. Aspect khác join point, pointcut và advice

Xét yêu cầu “ghi audit cho mọi lần thực thi thao tác phát hành dữ liệu”:

- **Join point:** một lần thực thi cụ thể của phương thức `publish(...)`.
- **Pointcut:** tiêu chí chọn những lần thực thi `publish(...)` thuộc phạm vi phát hành.
- **Advice:** mã ghi audit trước thao tác, ghi thành công hoặc thất bại sau thao tác.
- **Aspect:** đơn vị `PublicationAudit` gói quy tắc chọn và hành vi audit.

Nếu chỉ viết một advice nhưng rải tiêu chí chọn ở nhiều nơi không liên quan, trách nhiệm chưa thật sự được mô-đun hóa tốt. Ngược lại, một aspect có thể chứa **nhiều advice/pointcut liên quan cùng một concern**, ví dụ audit bắt đầu, audit thành công và audit thất bại.

### 2.2. Cohesion: một aspect nên có một lý do thay đổi

Một aspect `AuditTrail` có thể chứa các quy tắc ghi sự kiện audit cho nhiều loại thao tác nếu cùng chung chính sách. Nhưng ghép cả audit, cache, phân quyền, retry và chuyển đổi ngoại lệ vào `CommonAspect` khiến đơn vị này có nhiều lý do thay đổi, rất khó kiểm thử và bảo trì.

Quy tắc thiết kế hữu ích: **gom theo một mục tiêu xuyên suốt nhất quán**. Không phải “mỗi phương thức một aspect”, cũng không phải “mọi việc kỹ thuật vào một aspect lớn”. Nếu hai concern có quy tắc áp dụng, độ tin cậy hoặc vòng đời thay đổi khác nhau, chúng thường nên có mô-đun riêng.

## 3. Aspect và hợp đồng hành vi

Một aspect dù nằm ngoài mã nghiệp vụ vẫn có thể ảnh hưởng đến kết quả quan sát được của chương trình. Bởi vậy aspect cần có **hợp đồng hành vi** (*behavioral contract*) rõ ràng.

### 3.1. Phạm vi can thiệp

Viết được một pointcut “chọn mọi phương thức” không có nghĩa đó là lựa chọn đúng. Một phạm vi dễ kiểm soát thường trả lời được:

1. Những thao tác nào **phải** khớp?
2. Những thao tác nào **không được** khớp?
3. Lời gọi qua interface, lời gọi trực tiếp target và lời gọi nội bộ có đi qua cơ chế can thiệp hay không?
4. Khi đổi tên, overload, di chuyển lớp hoặc bổ sung phương thức, quy tắc khớp có đổi ngoài ý muốn không?

Đây là một phần của hợp đồng aspect, vì **khớp thiếu** làm bỏ lọt chính sách, còn **khớp thừa** làm chính sách tác động nhầm chỗ.

### 3.2. Mức độ tác động

Không phải mọi advice đều “chỉ quan sát”:

- **Observation:** ghi log/metric/tracing, cố gắng không đổi giá trị trả về hoặc ngoại lệ.
- **Guard:** kiểm tra trước khi cho phép thao tác tiếp tục; có thể chặn thao tác.
- **Transformation:** biến đổi đối số, kết quả hoặc ngoại lệ nếu cơ chế cho phép.
- **Execution control:** around advice có thể quyết định lúc nào gọi tiếp, có gọi tiếp hay không, thậm chí gọi lại.

Mức độ can thiệp càng lớn, yêu cầu tài liệu, kiểm thử và xác định thứ tự càng cao. “Dùng AOP” tự nó không bảo đảm advice giữ nguyên semantics của phương thức đích.

### 3.3. Đối số, kết quả và ngoại lệ

Một aspect được phép quan sát/biến đổi dữ liệu gì phụ thuộc API và cơ chế weaving. Thiết kế cần trả lời: có cần đọc đối số không; kết quả có được thay thế không; ngoại lệ có cần truyền nguyên vẹn không; liệu việc ghi audit thất bại có phải khiến nghiệp vụ thất bại?

Ví dụ, một aspect đo thời gian đúng nghĩa thường dùng cấu trúc `try/finally` quanh điểm chuyển tiếp để vẫn ghi nhận khi target ném lỗi. Một aspect chỉ dùng “after returning” sẽ không quan sát được các lần kết thúc bằng ngoại lệ. Một aspect audit có thể cần phân biệt rõ hai trường hợp ấy.

## 4. Đi từ định nghĩa aspect đến hành vi đang chạy

Ở mức khái niệm, quá trình áp dụng gồm bốn bước:

1. **Khai báo một concern** và những advice đại diện cho hành vi chung.
2. **Định nghĩa pointcut** để chỉ ra tập join point mà aspect được phép tác động.
3. **Kết hợp (weave)** aspect với mã đích bằng cơ chế mà công cụ hỗ trợ.
4. **Thực thi**: khi chương trình đi qua một join point khớp, advice của aspect được chạy theo ngữ nghĩa và thứ tự tương ứng.

```text
                +-----------------------+
                | Aspect: AuditTrail    |
                | concern = audit       |
                | pointcut = publish(*) |
                | advice = around       |
                +-----------+-----------+
                            |
                     kết hợp/weaving
                            |
Caller -----> [điểm publish được chọn] -----> Target.publish()
                            |
               audit attempt / result / error
```

Sơ đồ chỉ mô tả *ý tưởng*, không xác định cú pháp pointcut chuẩn. Điểm kết hợp có thể được cài bằng proxy, interceptor, biến đổi bytecode lúc biên dịch hoặc lúc nạp class. **Không mặc định có proxy trong mọi kỹ thuật AOP.**

Một khác biệt quan trọng là **lời gọi phương thức** (*method call*) và **thực thi phương thức** (*method execution*) có thể là hai loại join point khác nhau. Công cụ chỉ hỗ trợ interception tại proxy thường quan sát được những lời gọi thực sự đi qua proxy; một công cụ weaving ở cấp bytecode có thể nhận diện thêm loại điểm thực thi, tùy khả năng của nó.

## 5. Ví dụ Java 17+: hai aspect là hai mô-đun độc lập

Ví dụ dưới đây dùng Java SE để tạo một cơ chế AOP nhỏ trên `java.lang.reflect.Proxy`. Mỗi aspect **tự chứa pointcut `matches` và advice `around`**. Cơ chế ghép advice chung nằm trong một hàm trung gian, không nằm trong nghiệp vụ. Đây là ví dụ học tập chạy được, **không phải một triển khai AOP đầy đủ**.

Lưu toàn bộ vào tệp **`AspectModuleDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.List;

public class AspectModuleDemo {
    // Mô tả thao tác bên trong chuỗi advice.
    @FunctionalInterface
    interface Proceed {
        Object call() throws Throwable;
    }

    // Mỗi mô-đun aspect tự quyết định nơi áp dụng và hành vi.
    interface AspectRule {
        boolean matches(Method method);

        Object around(Method method, Object[] args, Proceed next)
                throws Throwable;
    }

    static final class TraceAspect implements AspectRule {
        @Override
        public boolean matches(Method method) {
            return method.getDeclaringClass() != Object.class;
        }

        @Override
        public Object around(Method method, Object[] args, Proceed next)
                throws Throwable {
            System.out.println("[trace:begin] " + method.getName());
            try {
                Object result = next.call();
                System.out.println("[trace:ok] " + method.getName());
                return result;
            } catch (Throwable error) {
                System.out.println("[trace:failed] " + method.getName());
                throw error;
            } finally {
                System.out.println("[trace:end] " + method.getName());
            }
        }
    }

    static final class PublicationAuditAspect implements AspectRule {
        @Override
        public boolean matches(Method method) {
            return method.getName().equals("publish")
                    && method.getParameterCount() == 1;
        }

        @Override
        public Object around(Method method, Object[] args, Proceed next)
                throws Throwable {
            System.out.println("[audit:attempt] " + method.getName());
            try {
                Object result = next.call();
                System.out.println("[audit:ok] " + method.getName());
                return result;
            } catch (Throwable error) {
                System.out.println("[audit:failed] " + method.getName());
                throw error;
            }
        }
    }

    public interface PublicationService {
        String publish(String id);
        String status();
    }

    public static final class PublicationServiceImpl
            implements PublicationService {
        @Override
        public String publish(String id) {
            if ("bad".equals(id)) {
                throw new IllegalArgumentException("id bị từ chối");
            }
            return "published:" + id;
        }

        @Override
        public String status() {
            return "READY";
        }
    }

    static Object invokeTarget(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static PublicationService weave(
            PublicationService target, List<AspectRule> aspects) {
        return (PublicationService) Proxy.newProxyInstance(
                PublicationService.class.getClassLoader(),
                new Class<?>[]{PublicationService.class},
                (proxy, method, args) -> {
                    Proceed chain = () -> invokeTarget(method, target, args);

                    // Aspect đầu danh sách là lớp ngoài cùng.
                    for (int i = aspects.size() - 1; i >= 0; i--) {
                        AspectRule aspect = aspects.get(i);
                        if (aspect.matches(method)) {
                            Proceed next = chain;
                            chain = () -> aspect.around(method, args, next);
                        }
                    }

                    return chain.call();
                });
    }

    public static void main(String[] args) {
        PublicationService target = new PublicationServiceImpl();
        PublicationService service = weave(
                target,
                List.of(new TraceAspect(), new PublicationAuditAspect()));

        System.out.println(service.publish("P-7"));
        System.out.println(service.status());

        try {
            service.publish("bad");
        } catch (IllegalArgumentException error) {
            System.out.println("caller:" + error.getMessage());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa file, với nội dung tệp lưu bằng UTF-8:

```bash
javac -encoding UTF-8 AspectModuleDemo.java
java AspectModuleDemo
```

Kết quả chuẩn:

```text
[trace:begin] publish
[audit:attempt] publish
[audit:ok] publish
[trace:ok] publish
[trace:end] publish
published:P-7
[trace:begin] status
[trace:ok] status
[trace:end] status
READY
[trace:begin] publish
[audit:attempt] publish
[audit:failed] publish
[trace:failed] publish
[trace:end] publish
caller:id bị từ chối
```

### 5.1. Aspect đóng gói những gì trong ví dụ?

**`TraceAspect`** là một mô-đun theo concern “theo dõi luồng thực thi”:

- `matches` chọn phương thức do interface nghiệp vụ khai báo, ngoại trừ các phương thức khai báo trực tiếp trên `Object`.
- `around` in mốc bắt đầu, thành công/thất bại và kết thúc.
- `try/catch/finally` bảo đảm dòng kết thúc được in dù thao tác ném ngoại lệ.

**`PublicationAuditAspect`** là một mô-đun khác theo concern “audit thao tác phát hành”:

- `matches` chọn các phương thức tên `publish` có đúng một tham số trong phạm vi proxy demo.
- `around` ghi nhận việc thử phát hành và kết cục của lời gọi.
- `status()` không khớp pointcut nên không ghi audit, nhưng vẫn được trace.

**`PublicationServiceImpl`** là target: chỉ chứa thao tác thật. Nó không cần gọi `TraceAspect` hay `PublicationAuditAspect`. Tính độc lập của target khỏi các lớp aspect là ví dụ của việc *giảm đan xen*, nhưng caller bắt buộc gọi qua `service` (proxy) để advice chạy.

**`weave(...)`** là cơ chế ghép chuỗi cho ví dụ. Nó tách khỏi hai concern nên việc thêm một aspect mới không phải sửa `PublicationServiceImpl`. Tên hàm “weave” ở đây chỉ tính năng ghép advice bằng proxy tại runtime; nó không thực hiện compile-time hoặc bytecode weaving.

### 5.2. Vì sao thứ tự log như vậy?

Danh sách aspect là `TraceAspect` trước `PublicationAuditAspect`. Vòng lặp xây từ cuối lên nên trace trở thành **lớp ngoài**, audit là lớp trong:

```text
Trace.before
    Audit.before
        Target.publish()
    Audit.after-success-or-error
Trace.after-success-or-error
Trace.finally
```

Khi `publish("bad")` ném `IllegalArgumentException`, `Method.invoke` tạm bọc ngoại lệ vào `InvocationTargetException`. Hàm `invokeTarget` mở lớp bọc, để cả hai aspect nhìn thấy và chuyển tiếp lỗi gốc. Nhánh “ok” không chạy khi có lỗi.

### 5.3. Các giới hạn có chủ đích

Đây là cơ chế interception qua interface proxy, vì vậy:

- `target.publish(...)` gọi trực tiếp sẽ **không** kích hoạt hai aspect.
- Lời gọi nội bộ từ target qua `this` không đi ngược qua proxy.
- Pointcut kiểm tra tên và số tham số để dễ học; trong hệ thống lớn, hai điều kiện này có thể khớp nhầm overload hoặc không ổn định khi refactor.
- Không có hỗ trợ riêng cho truy cập trường, constructor, compile-time weaving hoặc ngôn ngữ pointcut tổng quát.
- Thông tin audit được in ra stdout chỉ nhằm minh họa; audit thực tế cần chính sách bảo mật, lưu trữ và độ tin cậy riêng.

Vì thế, **giá trị mô hình** của ví dụ nằm ở `AspectRule`: một đơn vị sở hữu đồng thời tiêu chí áp dụng và hành vi xuyên suốt. Kỹ thuật proxy chỉ là một cách thực hiện mô hình đó.

## 6. Aspect khác utility class, decorator và interceptor ở đâu?

Các kỹ thuật cùng có thể xử lý mã dùng chung, nhưng cách biểu đạt trách nhiệm khác nhau.

| Cách tổ chức | Điều gì được đóng gói? | Cách áp dụng |
| --- | --- | --- |
| **Utility/function** | Thao tác có thể tái sử dụng | Call site chủ động gọi hàm. |
| **Decorator** | Hành vi bao quanh một đối tượng/interface được bọc | Đối tượng được xây dựng hoặc cấu hình qua wrapper. |
| **Interceptor/middleware** | Hành vi xử lý tại một pipeline hay ranh giới lời gọi | Áp dụng ở pipeline/hook đã định. |
| **Aspect** | Một concern cùng quy tắc chọn điểm áp dụng và advice | Kết hợp tại những join point mà mô hình AOP cho phép. |

Một interceptor có thể làm *cơ chế thực thi* cho một aspect, nhưng không phải interceptor nào cũng là aspect đầy đủ. Decorator có thể rất phù hợp khi chỉ cần bao quanh một đối tượng hoặc giao diện cụ thể và muốn giữ tất cả cấu hình tường minh.

**Khi nào aspect đem lại lợi ích hơn?** Khi quy tắc phủ nhiều thành phần rời nhau và cần biểu đạt tập vị trí áp dụng như một phần của chính sách. Nếu chỉ có một điểm gọi duy nhất, một hàm hoặc decorator rõ ràng có thể dễ bảo trì hơn.

Aspect cũng **không thay thế encapsulation của OOP**. Lớp nghiệp vụ vẫn giữ bất biến và hành vi miền nghiệp vụ; aspect đóng gói chính sách cắt ngang ở ranh giới thích hợp.

## 7. Thiết kế ranh giới của aspect: chọn đúng tập điểm thực thi

Một aspect chỉ được đóng gói tốt khi **pointcut chọn đúng các thao tác thuộc cùng mối quan tâm cắt ngang**. Ví dụ, `PublicationAuditAspect` phải ghi audit cho hành vi phát hành thật, không phải mọi helper có tên giống `publish`.

| Cách chọn | Lợi thế với trách nhiệm của aspect | Rủi ro cần kiểm chứng |
| --- | --- | --- |
| Tên/chữ ký | Dễ xác định trên giao diện mã | Đổi tên, overload hoặc sửa chữ ký có thể chọn thiếu/thừa |
| Annotation/metadata | Diễn đạt rõ “thao tác cần audit” | Phải đọc đúng interface/implementation, retention và lookup; marker không tự kích hoạt advice |
| Package/kiểu | Gắn concern với ranh giới kiến trúc | Thêm/chuyển helper, callback hoặc class làm đổi tập match |
| Điều kiện động | Chọn theo đối số, receiver hoặc ngữ cảnh | Tốn chi phí, khác kết quả theo luồng/dữ liệu; không tự bảo vệ mọi đường vào |

Nếu matcher Java dùng reflection tại runtime, annotation phải có retention phù hợp (chẳng hạn `RetentionPolicy.RUNTIME`) và được tra cứu tại đúng method. Một bộ weaving bytecode có thể dùng cơ chế metadata khác.

Kiểm thử cả **positive** (phải chọn) và **negative** (không được chọn). Khi giới hạn pointcut, ưu tiên hợp đồng của concern hơn wildcard khiến ca hiện tại đi qua. Cách đọc bốn trường hợp:

```text
                         Pointcut chọn?
Cần áp dụng + Có chọn      → ĐÚNG
Cần áp dụng + Không chọn   → LỌT CHÍNH SÁCH
Không cần + Có chọn        → ÁP DỤNG NHẦM
Không cần + Không chọn     → ĐÚNG
```

## 8. Aspect phối hợp với nhau: composition và precedence

Khi nhiều aspect chọn cùng một join point, chương trình có một **chuỗi hành vi tổng hợp**. Chuỗi này không nhất thiết giao hoán: đổi thứ tự có thể đổi kết quả quan sát được.

Ví dụ có hai aspect: `Authorization` (kiểm tra quyền) và `Audit` (ghi nhật ký thao tác). Nếu audit nằm ngoài authorization, nó có thể quan sát cả yêu cầu bị từ chối. Nếu audit nằm trong authorization, một yêu cầu bị chặn bên ngoài có thể không được audit. Không có một thứ tự luôn đúng cho mọi ứng dụng; hợp đồng của hệ thống phải quyết định.

Hai hệ quả quan trọng:

1. **Advice không chỉ nối đuôi nhau:** với around advice, hành vi lồng nhau như các wrapper; nhánh hoàn tất chạy ngược thứ tự bắt đầu.
2. **Precedence là một quyết định kiến trúc:** khi aspect giao nhau, cần ghi rõ thứ tự bằng cơ chế mà công cụ hỗ trợ, không dựa trên giả định thứ tự ngẫu nhiên.

Một sơ đồ kết hợp:

```text
             Caller
               |
        Security around
               |
          Audit around
               |
           Target work
               |
       quay ra qua Audit
               |
      quay ra qua Security
               |
             Caller
```

Thay `Security` và `Audit` theo thứ tự ngược có thể làm thay đổi chính sách ghi nhận các yêu cầu bị chặn. Nếu một advice cố ý **không gọi tiếp** (*proceed*), các advice bên trong và target có thể không chạy. Nếu gọi tiếp hai lần, target có thể chạy hai lần. Điều này đặc biệt rủi ro với thanh toán, phát hành sự kiện, ghi dữ liệu và các thao tác không idempotent.

### 8.1. Phụ thuộc giữa các aspect

Hai aspect cần phối hợp không đồng nghĩa nên gộp chúng thành một aspect. Có thể giữ mỗi concern riêng nhưng mô tả một contract: ví dụ “ngữ cảnh truy vết được tạo trước khi audit ghi sự kiện” hoặc “kiểm tra quyền phải diễn ra trước khi cập nhật dữ liệu”.

Khi các aspect có thứ tự bắt buộc, nên có **một nơi quản lý precedence** và test bảo vệ thứ tự ấy. Phụ thuộc vòng tròn kiểu “A phải trước B, B phải trước C, C phải trước A” cho thấy thiết kế không thể sắp thành một chuỗi nhất quán.

### 8.2. Không nuốt lỗi ngoài ý muốn

Một aspect quan sát thông thường nên truyền tiếp ngoại lệ sau khi ghi nhận. Nếu một aspect thay đổi hoặc nuốt lỗi, người gọi có thể nhận kết quả “thành công” dù thao tác đích thất bại. Chỉ thực hiện thay đổi như vậy nếu đó là chính sách công khai, có phạm vi rõ và được kiểm thử.

## 9. Trạng thái và vòng đời của aspect

Aspect có thể **không có trạng thái riêng cho từng lần gọi**, hoặc có state dùng cho một target, một ngữ cảnh hoặc một đối tượng aspect. Mô hình vòng đời cụ thể thay đổi theo kỹ thuật AOP. Không nên giả định mỗi lời gọi có một aspect instance mới.

### 9.1. Stateless thường dễ kiểm soát

Aspect ghi log chỉ dùng dữ liệu từ lời gọi và một logger an toàn để chia sẻ thường đơn giản hơn aspect giữ “tên người dùng hiện tại” trong trường instance. Nếu một instance dùng chung cho nhiều luồng, trường mutable có thể bị ghi đè chéo.

Ví dụ thiết kế nguy hiểm:

```java
// Pseudocode minh họa anti-pattern: trường này có thể bị nhiều luồng ghi đè.
class UnsafeAuditState {
    String currentRequestId;
}
```

Nếu cùng một instance được chia sẻ, request A ghi ID rồi request B ghi ID trước khi A hoàn tất thì bản ghi của A có thể mang nhầm ID của B.

### 9.2. State theo invocation và context propagation

Dữ liệu tạm như thời điểm bắt đầu nên ưu tiên biến cục bộ của advice, vì mỗi lần gọi có một ngữ cảnh riêng. Khi cần ngữ cảnh xuyên qua nhiều lời gọi hoặc chạy bất đồng bộ, phải thiết kế cách truyền ngữ cảnh tường minh hoặc sử dụng cơ chế ngữ cảnh đã được kiểm chứng. Không mặc định dữ liệu gắn với một thread sẽ tự đi theo công việc khi thay đổi thread, executor hay callback.

### 9.3. Reentrancy và recursion

Một aspect ghi log có thể gọi vào thành phần logging; nếu thành phần ấy cũng khớp pointcut của chính aspect, hệ thống có nguy cơ tự gọi lặp vô hạn. Cách phòng ngừa gồm thu hẹp pointcut, loại trừ hạ tầng của advice, hoặc đặt guard có phạm vi chính xác. Guard toàn cục dùng chung dễ làm bỏ lọt các lời gọi độc lập khi chạy đồng thời.

## 10. Cross-cutting tĩnh và động

Aspect giúp mô-đun hóa các tác động **động** như chạy advice quanh phương thức. Một số mô hình AOP còn hỗ trợ kiểu tác động **tĩnh**, ví dụ khai báo bổ sung thành viên, interface hoặc quan hệ cấu trúc cho một loại (*inter-type declaration/introduction*).

Đây là năng lực nâng cao và **không phổ quát**. Công cụ chỉ dùng proxy ở ranh giới interface thường không thể tùy ý thêm trường hay phương thức vào một class đã biên dịch. Vì vậy khi đánh giá một mô-đun aspect, cần phân biệt:

- **Behavioral cross-cutting:** thêm logic vào những thời điểm thực thi được chọn.
- **Structural cross-cutting:** bổ sung hoặc thay đổi cấu trúc loại chương trình, khi mô hình và cơ chế hỗ trợ.

Cả hai đều hướng tới đóng gói một concern, nhưng phạm vi tác động và nguy cơ tương thích khác nhau. Các thay đổi cấu trúc đòi hỏi đặc biệt chú ý đến API công khai, biên dịch, reflection và người dùng type đó.

## 11. Weaving ảnh hưởng đến khả năng đóng gói như thế nào?

Mô-đun aspect mô tả ý định; **cơ chế weaving/interception** quyết định ý định ấy tác động tới chương trình thực tế ở đâu.

| Cơ chế | Đặc trưng chính | Điều cần kiểm chứng |
| --- | --- | --- |
| **Compile-time weaving** | Advice được kết hợp trong giai đoạn biên dịch | Artifact đã được weave theo đúng cấu hình chưa? |
| **Post-compile weaving** | Bytecode đã biên dịch được biến đổi ở bước riêng | Có tác động đến build, debug và tương thích bytecode không? |
| **Load-time weaving** | Kết hợp lúc class được nạp | Class loader và thứ tự nạp có bảo đảm cơ chế áp dụng không? |
| **Runtime proxy** | Lời gọi được chuyển qua đối tượng trung gian | Có đường gọi trực tiếp hoặc nội bộ bỏ qua proxy không? |

Định nghĩa `AuditAspect` có thể trông rất sạch, nhưng nếu một số đường gọi bỏ qua cơ chế AOP thì audit không thật sự được thực thi ở mọi nơi mong đợi. Mô-đun hóa trên giấy chỉ đạt giá trị khi **ranh giới tác động được kiểm chứng bằng hành vi thực tế**.

Một nguyên tắc an toàn: không chọn AOP như lớp kiểm soát an ninh duy nhất nếu vẫn tồn tại đường truy cập bỏ qua advice; các bất biến nghiệp vụ và ranh giới bảo mật cốt lõi phải được bảo vệ tại nơi bảo đảm bao phủ.

## 12. Định lượng lợi ích và cái giá

Lợi ích của một aspect thiết kế tốt:

- **Tập trung chính sách:** thay đổi format audit/metric hoặc quy tắc áp dụng ở ít vị trí hơn.
- **Tăng cohesion:** mã nghiệp vụ tập trung vào nghiệp vụ; aspect tập trung vào concern chung.
- **Tái sử dụng:** cùng một aspect có thể áp dụng cho một tập join point có quy tắc rõ ràng.
- **Đồng nhất:** bớt nguy cơ mỗi lớp tự xử lý ngoại lệ, thời gian hay ngữ cảnh khác nhau.
- **Kiểm thử ở mức mô-đun:** có thể kiểm riêng logic advice, pointcut và sự phối hợp với target.

Chi phí cần tính đúng:

- **Hành vi không hiển thị tại call site:** đọc một phương thức chưa chắc thấy đầy đủ kiểm soát diễn ra quanh nó.
- **Pointcut giòn:** đổi code có thể làm tập khớp thay đổi không mong muốn.
- **Precedence phức tạp:** nhiều aspect giao nhau làm tăng số tổ hợp và khả năng tương tác.
- **Overhead:** thêm lời gọi trung gian, reflection, kiểm tra pointcut, tạo metric/log hoặc bytecode được chèn.
- **Debug khó hơn:** stack trace và breakpoint có thể đi qua lớp code mà nghiệp vụ không gọi trực tiếp.

Hiệu năng phải đo trên đường chạy thật, đặc biệt những join point tần suất cao. Không khẳng định một tỷ lệ overhead cố định cho mọi công cụ; mức chi phí phụ thuộc cơ chế triển khai, pointcut, lời khuyên và khối lượng công việc.

## 13. Tách trách nhiệm theo ranh giới kiến trúc

Một cấu trúc khái niệm dễ hiểu:

```text
business/
  PublicationService       (contract nghiệp vụ)
  PublicationServiceImpl   (quy trình thực hiện)

crosscutting/
  TraceAspect              (điểm áp dụng + hành vi trace)
  PublicationAuditAspect   (điểm áp dụng + hành vi audit)

composition/
  AspectConfiguration      (kích hoạt, thứ tự và cơ chế áp dụng)
```

Đây là **sơ đồ tổ chức gợi ý**, không phải cấu trúc folder bắt buộc. Ý nghĩa của nó:

- Mã nghiệp vụ không phụ thuộc trực tiếp vào class aspect.
- Mỗi aspect có tên diễn đạt mục đích và một lý do thay đổi.
- Phần lắp ghép xác định aspect nào có hiệu lực, theo thứ tự nào.
- Các cấu hình quan trọng nằm ở nơi có thể tìm thấy và kiểm toán được.

Không nên biến module aspect thành một “hộp đen” chứa các quyết định miền nghiệp vụ quan trọng. Ví dụ, “chỉ được hoàn tiền khi trạng thái đơn cho phép” là bất biến nghiệp vụ; nó cần hiện diện ở mô hình nghiệp vụ và được bảo vệ trực tiếp. Aspect có thể bổ sung log/audit quanh thao tác hoàn tiền, nhưng không nên là nơi duy nhất ẩn quy tắc trạng thái cốt lõi.

## 14. Kiểm thử aspect như một mô-đun độc lập và khi kết hợp

Kiểm thử AOP cần chứng minh **cả chính sách chọn điểm** và **hành vi advice**.

| Trường hợp | Xác nhận cần có |
| --- | --- |
| Join point khớp pointcut | Advice chạy đúng số lần và đúng vị trí tương đối. |
| Join point không khớp | Advice không chạy, nghiệp vụ vẫn hoạt động như dự kiến. |
| Target trả về bình thường | Giá trị trả về và nhánh sau thành công chính xác. |
| Target ném ngoại lệ | Nhánh lỗi/finally chính xác; ngoại lệ được bảo toàn nếu contract yêu cầu. |
| Hai aspect cùng khớp | Thứ tự vào/ra đúng precedence đã định. |
| Lời gọi trực tiếp và nội bộ | Kiểm chứng đúng giới hạn của cơ chế interception. |
| Tác vụ đồng thời | Không rò hoặc ghi đè context/state giữa các invocation. |
| Pointcut sau refactor | Không xuất hiện khớp thiếu/khớp thừa. |

Đối với ví dụ Java ở mục 5, có thể bắt đầu bằng bốn khẳng định:

1. `service.publish("P-7")` ghi trace và audit, trả `published:P-7`.
2. `service.status()` chỉ ghi trace, trả `READY`.
3. `service.publish("bad")` ghi nhánh thất bại của cả hai aspect, và người gọi nhận `IllegalArgumentException`.
4. `target.publish("P-7")` không sinh log của hai aspect vì không đi qua proxy.

Kiểm thử thứ tư có giá trị lớn: nó ngăn nhầm lẫn “aspect đã được định nghĩa” với “mọi đường gọi đến target đều được bao phủ”.

Ngoài unit test cho từng aspect, nên có **integration test** cho cấu hình weaving thực tế và **regression test** trên tập join point đặc trưng. Một unit test của `matches` không đủ để chứng minh class thực tế đã được biến đổi hoặc proxy đang được sử dụng bởi caller.

## 15. Các sai lầm thiết kế thường gặp

### “Aspect chỉ là nơi gom các hàm tiện ích”

Nếu concern không có quy tắc áp dụng tại join point và mọi nơi vẫn phải gọi utility một cách tường minh, đó có thể chỉ là utility module. Điều này không xấu; cần gọi đúng khái niệm để thiết kế cơ chế phù hợp.

### “Một aspect xử lý toàn bộ vấn đề kỹ thuật”

Gom audit, cache, authorization, exception mapping, retry và metric vào một aspect tạo coupling mạnh và làm khó kiểm thử precedence. Hãy xác định cohesion theo concern, tách khi trách nhiệm thay đổi độc lập.

### “Có pointcut thì bao phủ hoàn toàn”

Phạm vi thực tế còn phụ thuộc khả năng join point và đường gọi qua cơ chế AOP. Với proxy, gọi trực tiếp target hoặc gọi nội bộ có thể bỏ qua advice; với weaving bytecode, phải xác minh bước build/load thực sự áp dụng.

### “Advice chỉ bổ sung log nên không ảnh hưởng nghiệp vụ”

Log đồng bộ có thể tạo độ trễ; lỗi ghi log có thể làm lời gọi thất bại nếu không được xử lý; in toàn bộ đối số có thể lộ dữ liệu nhạy cảm. Ngay cả aspect quan sát cũng cần hợp đồng thất bại và chính sách dữ liệu.

### “Around advice có thể retry bất kỳ thao tác nào”

Gọi `proceed` nhiều lần có thể tạo side effect trùng lặp. Chỉ retry khi có chính sách rõ về idempotency, timeout, thứ tự và điều kiện ngoại lệ.

### “Aspect luôn không có state”

Một số mô hình có trạng thái theo aspect instance, target hoặc ngữ cảnh. Khi chia sẻ state mutable giữa nhiều luồng, phải kiểm soát race condition, vòng đời, leak và reentrancy.

### “Càng nhiều aspect càng sạch”

Chia quá nhỏ có thể làm mất khả năng thấy được chuỗi hành vi cuối cùng, tăng precedence và khó debug. Mục tiêu là mô-đun có trách nhiệm rõ, không phải tối đa số lượng aspect.

## 16. Bài tập củng cố

Từ `AspectModuleDemo.java`:

1. Thêm một phương thức `health()` vào interface và implementation, chạy qua proxy và giải thích tại sao `TraceAspect` khớp còn `PublicationAuditAspect` không khớp.
2. Đổi thứ tự hai phần tử trong `List.of(...)`, chạy lại `publish("P-7")` và quan sát thứ tự bản ghi ngoài/trong thay đổi.
3. Thêm một phương thức overload `publish(int version)` rồi phân tích vì sao pointcut hiện tại có thể chọn nhầm. Sửa `matches` để kiểm tra kiểu tham số cần thiết.
4. Thử gọi `target.publish("P-7")` trực tiếp sau lời gọi qua `service`. Vì sao lần gọi trực tiếp không có bản ghi trace/audit?
5. Chuyển phần logic cố ý không gọi `next.call()` vào một aspect riêng. Mô tả những nguy cơ nếu dùng aspect này cho phương thức có side effect.
6. Phác thảo hai aspect độc lập `ExecutionTiming` và `PublicationAudit`. Chỉ ra điều kiện áp dụng, dữ liệu được ghi, cách xử lý lỗi và thứ tự nên có trong một tình huống cụ thể.

**Tự kiểm tra nhanh:** Aspect khác advice như thế nào? Vì sao pointcut là một phần quan trọng của ranh giới mô-đun? Một aspect có thể chứa nhiều advice không? Thứ tự hai around advice ảnh hưởng điều gì? Với proxy, tại sao lời gọi trực tiếp target không bị chặn? Khi nào một wrapper đơn giản phù hợp hơn aspect?

## Kết luận

**Aspect là đơn vị đóng gói một mối quan tâm cắt ngang**, có mục tiêu nhất quán, tiêu chí chọn điểm áp dụng và hành vi tương ứng. Giá trị thiết kế nằm ở việc làm rõ *ai sở hữu chính sách dùng chung*, *chính sách có hiệu lực ở đâu* và *nó thay đổi điều gì trong luồng chạy*. Để aspect thực sự hữu ích, cần giữ cohesion, giới hạn pointcut chính xác, công bố tác động lên kết quả/ngoại lệ, xác định precedence và kiểm thử cơ chế weaving trên những đường gọi thật.
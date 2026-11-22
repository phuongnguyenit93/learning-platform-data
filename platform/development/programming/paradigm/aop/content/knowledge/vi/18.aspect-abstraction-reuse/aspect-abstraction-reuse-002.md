# Pointcut trừu tượng làm điểm tùy biến phạm vi trong AOP

## 1. Vì sao cần một pointcut trừu tượng?

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, một **aspect** đóng gói mối quan tâm cắt ngang bằng **pointcut** (chọn những join point cần áp dụng) và **advice** (hành vi xảy ra khi join point khớp). Chẳng hạn, một advice có thể đo thời gian, ghi audit, theo dõi lỗi hoặc chặn thao tác không hợp lệ.

Khi viết những aspect cho nhiều khu vực của hệ thống, ta dễ gặp tình huống:

- **Hành vi advice giống nhau**: cùng định dạng log, cùng đồng hồ đo, cùng chính sách xử lý exception.
- **Phạm vi áp dụng khác nhau**: module A cần can thiệp vào các thao tác đọc; module B chỉ áp dụng cho thao tác xóa; module C dùng quy tắc tên phương thức, annotation hoặc một điều kiện theo ngữ cảnh.
- **Không muốn sao chép advice** cho từng module vì mỗi bản sao có thể dần khác nhau, khó cập nhật và khó kiểm thử.

Một **pointcut trừu tượng (abstract pointcut)** là ý tưởng **để trống phần lựa chọn join point tại một định nghĩa AOP trừu tượng**, rồi yêu cầu một định nghĩa cụ thể hơn cung cấp quy tắc lựa chọn. Nhờ đó:

> **Hành vi cắt ngang dùng chung được định nghĩa một lần; phạm vi được chuyên biệt hóa ở điểm mở rộng.**

Ở mô hình hỗ trợ abstract aspect và pointcut inheritance, abstract aspect có thể định nghĩa advice dùng lại và khai báo một pointcut chưa có expression cụ thể. Concrete aspect cung cấp expression tương ứng. Một số hệ thống AOP không có cú pháp abstract pointcut trực tiếp nhưng vẫn đạt ý tưởng tương tự bằng **pointcut provider, selector strategy, predicate hoặc cấu hình interception**.

**Quan trọng:** “pointcut trừu tượng” không có nghĩa “một pointcut mơ hồ chạy ở mọi nơi”. Nó là **một hợp đồng chưa được cụ thể hóa**; một aspect được triển khai hữu hiệu chỉ khi quy tắc matching và cơ chế can thiệp đã được xác định.

> **Phạm vi:** Bài này đề cập AOP cơ bản và nâng cao nói chung. Ví dụ ký pháp `abstract aspect`/`pointcut` chỉ minh họa một *mô hình ngôn ngữ AOP có hỗ trợ khái niệm ấy*, không phải cú pháp chuẩn bắt buộc cho mọi công cụ. Demo Java 17+ phía sau mô phỏng cơ chế mở rộng bằng Java Dynamic Proxy để dễ chạy và kiểm chứng, **không tự nhận là một trình biên dịch pointcut đầy đủ**.

## 2. Ôn nhanh: join point, pointcut và advice

Ba tầng cần phân biệt:

| Khái niệm | Câu hỏi | Minh họa |
| --- | --- | --- |
| **Join point** | Một vị trí/sự kiện nào có thể được can thiệp? | Method call/execution, constructor hoặc event do engine hỗ trợ |
| **Pointcut** | Những join point **nào** được chọn? | Chọn execution của method đọc, chọn caller context hoặc argument phù hợp |
| **Advice** | Khi khớp, hành vi **gì** được thực hiện? | Before log, around đo latency, after-throwing ghi lỗi |

```text
Tập join point mà engine có thể quan sát
    |
    +-- J1: Repository.fetch(...)
    +-- J2: Repository.erase(...)
    +-- J3: MessageSender.send(...)
    +-- J4: Service.calculate(...)
    |
    +--> Pointcut P(J) [true / false]
             |
          J được chọn
             |
          Advice dùng chung
```

Một pointcut không nhất thiết chỉ kiểm tên method. Nó có thể kết hợp **type/signature, target, argument type/value, annotation, dynamic control flow**, tùy khả năng của engine.

### “Định nghĩa pointcut” không phải “gọi phương thức”

Một pointcut được khai báo bằng ký pháp trông như một method/function trong một số ngôn ngữ AOP, nhưng nó là **quy tắc chọn join point**, không phải một business method mà caller gọi để thực hiện side effect. Advice sẽ được áp dụng ở những join point được runtime/weaver chọn; không vì có một tên pointcut trong class mà Java tự gọi pointcut ấy.

### Một join point có thể khớp nhiều pointcut

Các pointcut có thể trùng phạm vi. Nếu hai concrete aspects cùng áp dụng advice tới một execution, **có thể có hai advice activations**, theo quy tắc precedence/ordering của engine. Việc tách điểm tùy biến không tự ngăn advice chạy hai lần.

## 3. Abstract pointcut là hợp đồng mở rộng phạm vi

Một hình dung:

```text
         AbstractAuditAspect
         +--------------------------+
         | abstract pointcut scope  |
         | before advice            |
         | after / around advice    |
         | error handling           |
         +--------------------------+
                      ^
              concrete specialization
               /                \
              v                  v
        ReadAuditAspect     SensitiveAuditAspect
        scope = read()      scope = selected delete()
               \                /
                v              v
             Cùng logic advice,
            tập join point khác nhau
```

Abstract aspect giữ **logic chung** nhưng không quyết định đầy đủ scope. Concrete aspect xác định một quy tắc **khớp join point** cho abstract pointcut đó.

### So với abstract method thông thường

Có nét tương tự nguyên tắc *Template Method* trong hướng đối tượng:

- Lớp cha định nghĩa khung hành vi.
- Một điểm mở rộng được lớp con cụ thể hóa.
- Khung hành vi dùng giá trị/quy tắc do lớp con cung cấp.

Nhưng điểm khác:

- Abstract method trong Java là hợp đồng **gọi phương thức**; abstract pointcut trong AOP là hợp đồng **matching join points**.
- Một concrete pointcut expression có thể chứa static/dynamic predicates và binding.
- Engine quyết định thời điểm kiểm và áp dụng advice; không nhất thiết “advice gọi một hàm tên scope” như Java method bình thường.
- Pointcut selection cần xét **weaving/interception coverage**, khác với method dispatch ở một object thông thường.

Vì vậy so sánh Template Method giúp hiểu **điểm tùy biến**, nhưng không thay thế semantics AOP.

## 4. Phác thảo cú pháp AOP mang tính khái niệm

Một mô hình ngôn ngữ hỗ trợ abstract pointcut có thể được diễn đạt:

```text
abstract aspect AuditTemplate {
    abstract pointcut selectedOperation(String id);

    before(String id): selectedOperation(id) {
        writeAuditBefore(id);
    }

    after(String id): selectedOperation(id) {
        writeAuditAfter(id);
    }
}

aspect ReadAudit extends AuditTemplate {
    pointcut selectedOperation(String id):
        execution(readOperation(String)) AND args(id);
}

aspect SensitiveDeleteAudit extends AuditTemplate {
    pointcut selectedOperation(String id):
        execution(deleteOperation(String))
        AND args(id)
        AND runtimeValueCondition(id);
}
```

Đây **không phải mã Java hoặc DSL có cam kết biên dịch**. Các tên `execution`, `args`, `before`, `after` diễn đạt ý tưởng, không phải một cú pháp phổ quát. Một engine có thể hỗ trợ abstract pointcut nhưng không cho phép mọi phép binding/điều kiện runtime được biểu diễn theo cách trên; một engine khác chỉ hỗ trợ interceptor selectors do ứng dụng cấu hình.

Điểm cần thấy:

1. **`AuditTemplate` chứa advice một lần**.
2. **`selectedOperation` chưa được định nghĩa tại template**.
3. **`ReadAudit` và `SensitiveDeleteAudit` chọn các tập join point khác nhau**.
4. **Cùng một advice** được áp vào tập join point do concrete definition xác định.
5. **Binding `id` phải tương thích** với dữ liệu mà advice mong đợi.

### Nếu không có cú pháp abstract pointcut?

Có thể thiết kế tương đương bằng:

```text
Abstract advice/interceptor template
          |
          +--> Strategy: matches(joinPoint, args)
          |
          +--> Advice handler when matched
```

Java interface `PointcutSelector`, một `Predicate<Invocation>` hoặc một selector cấu hình cũng thể hiện **separation of concern between matching and action**. Nhưng đừng gọi mọi predicate Java là một “pointcut ngôn ngữ” nếu nó chỉ kiểm lời gọi đã đi vào handler; đó là **một mô phỏng runtime ở cấp interceptor**, không phải khả năng dệt join point của engine.

## 5. Chuyên biệt hóa phạm vi mà không sao chép advice

Xét một audit concern: mỗi method được chọn cần:

- Ghi event trước khi thực hiện.
- Gọi target.
- Ghi success và một số dữ liệu kết quả.
- Nếu target throw, ghi failure rồi giữ nguyên Throwable theo hợp đồng.
- Không làm biến đổi những method **không được chọn**.

Nếu viết ba aspects tách biệt có nội dung advice giống hệt, ta có rủi ro:

- Một aspect sửa logic xử lý exception, hai aspect còn giữ bản cũ.
- Nhãn, dữ liệu bảo mật hoặc định dạng log không đồng nhất.
- Những lỗi về retry/cleanup bị sao chép.
- Cần viết cùng bộ test logic cho nhiều bản advice.
- Khi thay đổi chính sách, khó chắc mọi bản sao được cập nhật.

Với abstract pointcut:

```text
                 Shared audit advice
          before -> proceed -> after / error
                          |
            +-------------+-------------+
            |             |             |
       Scope READ      Scope DELETE     Scope annotated
```

Tập join point có thể khác nhau; **logic đo/ghi nhận được chuẩn hóa**. Điều này làm **điểm biến thiên** rõ ràng hơn và hỗ trợ tái sử dụng.

### Tái sử dụng không đồng nghĩa “chỉ có một instance”

Một abstract aspect được chuyên biệt hóa thành hai concrete aspects có thể dẫn tới **hai instance aspect**, hai chính sách instantiation hoặc hai advice chains. Chúng tái sử dụng **định nghĩa/logic**, không bắt buộc chia sẻ một object singleton duy nhất. Instance scope tùy engine.

## 6. Phân biệt abstract aspect, abstract pointcut và concrete advice

- **Abstract aspect:** một định nghĩa aspect chưa thể dùng như một concrete aspect độc lập theo mô hình của ngôn ngữ, vì có điểm mở rộng chưa được cung cấp hoặc được đánh dấu abstract.
- **Abstract pointcut:** một pointcut được khai báo như hợp đồng nhưng chưa có rule matching cụ thể ở mức đó.
- **Concrete pointcut:** expression/selector đã xác định cách chọn join point.
- **Concrete advice:** hành vi before/after/around thực tế có thể nằm trong abstract aspect và được thừa kế/tái sử dụng theo semantics engine.
- **Abstract helper method:** một method OOP bình thường chưa có implementation, không tự trở thành pointcut dù đặt trong class aspect.

Những khái niệm này tương tác nhưng **không thể dùng thay thế nhau**.

### Một abstract pointcut có thể không có binding?

Có. Nếu advice không cần dữ liệu từ join point, pointcut có thể chỉ làm nhiệm vụ xác định phạm vi. Khi advice cần đối số, target, method metadata hoặc context, **hợp đồng binding** phải được bảo toàn trong concrete definition.

## 7. Binding là phần thiết yếu của hợp đồng pointcut

Một abstract pointcut có thể có tham số để advice nhận dữ liệu:

```text
abstract pointcut selected(String customerId);

before(String customerId): selected(customerId) {
    audit(customerId);
}
```

Concrete definition phải chọn những join point có thể **cung cấp giá trị tương ứng** cho `customerId` theo semantics engine.

### Vì sao chỉ match tên method chưa đủ?

Giả sử hệ thống có overload:

```java
// Mã minh họa:
void save(String id);
void save(long id);
void save(String id, boolean overwrite);
```

Nếu advice mong `String customerId`, một concrete pointcut match **mọi method tên save** nhưng lại cố bind `long id` vào `String` có thể không compile, không match hoặc thất bại ở runtime, tùy engine/cách provider viết.

Phải làm rõ:

- Signature/overload được chọn.
- Binding type và vị trí argument.
- Primitive vs wrapper, null và subtype.
- Join point có target hay không.
- Binding từ `this`/`target`/`args` theo định nghĩa hỗ trợ.
- Điều kiện runtime có thể thay đổi tại từng invocation.

**Abstract pointcut là contract không chỉ về “bao nhiêu join points”, mà còn về dữ liệu mà advice có thể sử dụng tại các join points đã chọn.**

### Đừng suy rằng binding đến từ biến trùng tên

Việc một parameter advice và một business parameter cùng tên `id` không tự tạo binding theo tên Java. Một engine có thể dùng explicit binding semantics, positional argument, type annotations hoặc metadata do weaving cung cấp.

## 8. Quy tắc specialization: thay thế, bổ sung và giao nhau

Một concrete aspect có thể xác định phạm vi theo các kiểu logic:

- **Exact specialization:** chọn đúng một operation hoặc signature.
- **Union:** cho nhiều nhóm hoạt động.
- **Intersection:** operation phù hợp **và** có annotation **và** thuộc module được phép.
- **Difference/exclusion:** chọn broad scope rồi loại code hạ tầng hoặc helper mà advice không nên intercept.
- **Dynamic filter:** chọn dựa trên runtime value hoặc cflow nếu engine hỗ trợ.

Ký pháp tập hợp:

```text
P_read = {J | operation(J) = fetch}

P_delete = {J | operation(J) = erase}

P_sensitive = P_delete ∩ {J | argument0(J) startsWith "SEC-"}

P_safe = P_broad \ P_infrastructure
```

### Chuyên biệt hóa không nhất thiết chỉ thu hẹp

Nếu lớp con định nghĩa lại một abstract pointcut bằng **union lớn hơn**, advice có thể chạy tại **nhiều join point hơn**. Từ “specialization” nói về **cụ thể hóa điểm mở rộng**, không bảo đảm toán học rằng tập mới luôn là tập con của một tập cũ, vì abstract pointcut không nhất thiết có tập gốc nào.

Một concrete pointcut cố ý mở rộng scope cần được review giống thay đổi quan trọng về behavior và performance.

## 9. Ví dụ Java 17+ hoàn chỉnh — cùng advice, hai pointcut cụ thể

Dưới đây là một chương trình Java SE tự chạy được. Nó dùng **Java Dynamic Proxy** để mô phỏng AOP qua interceptor.

**Thiết kế:**

- `AbstractAuditAspect` giữ **một** implementation advice chung: before, invoke target, after, error.
- Method `protected abstract boolean matches(Method,Object[])` là một **selector trừu tượng** tương tự vai trò abstract pointcut.
- `ReadAudit` chỉ chọn operation `fetch`.
- `SensitiveDeleteAudit` chỉ chọn operation `erase` khi đối số bắt đầu bằng `"SEC-"`.
- Cả hai dùng **cùng code advice**, không copy logic logging.
- Target có một đường lỗi `erase("SEC-FAIL")` để chứng minh advice giữ đúng error type và message.

**Lưu ý chính xác:** Trong Java SE, `matches(...)` **là abstract Java method**, không phải abstract pointcut khai báo theo một DSL AOP. Demo thể hiện **cơ chế tùy biến phạm vi của advice** ở tầng proxy/interceptor; không giả làm language-level abstract pointcut hoặc hỗ trợ execution join points ngoài proxy.

### 9.1. Tệp `AbstractPointcutDemo.java`

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Objects;

public class AbstractPointcutDemo {

    public interface Operations {
        String fetch(String id);
        String erase(String id);
    }

    static final class Repository implements Operations {
        @Override
        public String fetch(String id) {
            System.out.println("target.fetch " + id);
            return "value:" + id;
        }

        @Override
        public String erase(String id) {
            System.out.println("target.erase " + id);
            if ("SEC-FAIL".equals(id)) {
                throw new IllegalStateException("storage refused");
            }
            return "removed:" + id;
        }
    }

    static abstract class AbstractAuditAspect {
        // Hợp đồng "pointcut" ở mô hình interceptor này:
        // concrete aspect quyết định một invocation có thuộc scope.
        protected abstract boolean matches(
                Method method, Object[] arguments);

        protected abstract String label();

        // Template advice chung; các lớp con không lặp lại logic.
        public final Operations advise(Operations target) {
            Objects.requireNonNull(target);

            return (Operations) Proxy.newProxyInstance(
                    Operations.class.getClassLoader(),
                    new Class<?>[]{Operations.class},
                    (proxy, method, args) -> {
                        Object[] actual = args == null
                                ? new Object[0] : args;

                        if (!matches(method, actual)) {
                            return invokeTarget(method, target, args);
                        }

                        String id = (String) actual[0];
                        System.out.println(
                                label() + ".before "
                                + method.getName() + " " + id);

                        try {
                            Object result = invokeTarget(
                                    method, target, args);

                            System.out.println(
                                    label() + ".after "
                                    + method.getName() + " " + result);

                            return result;
                        } catch (Throwable original) {
                            System.out.println(
                                    label() + ".error "
                                    + method.getName() + " "
                                    + original.getClass().getSimpleName());
                            throw original;
                        }
                    });
        }

        private static Object invokeTarget(
                Method method, Operations target, Object[] args)
                throws Throwable {
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException wrapped) {
                throw wrapped.getCause();
            }
        }
    }

    static final class ReadAudit extends AbstractAuditAspect {
        @Override
        protected boolean matches(
                Method method, Object[] arguments) {
            return "fetch".equals(method.getName());
        }

        @Override
        protected String label() {
            return "readAudit";
        }
    }

    static final class SensitiveDeleteAudit
            extends AbstractAuditAspect {
        @Override
        protected boolean matches(
                Method method, Object[] arguments) {
            return "erase".equals(method.getName())
                    && arguments.length == 1
                    && arguments[0] instanceof String id
                    && id.startsWith("SEC-");
        }

        @Override
        protected String label() {
            return "sensitiveAudit";
        }
    }

    public static void main(String[] args) {
        Operations target = new Repository();

        System.out.println("== read scope ==");
        Operations auditedReads =
                new ReadAudit().advise(target);

        System.out.println("caller "
                + auditedReads.fetch("A"));
        System.out.println("caller "
                + auditedReads.erase("SEC-9"));

        System.out.println("== sensitive delete scope ==");
        Operations auditedDeletes =
                new SensitiveDeleteAudit().advise(target);

        System.out.println("caller "
                + auditedDeletes.fetch("B"));
        System.out.println("caller "
                + auditedDeletes.erase("PUBLIC-1"));
        System.out.println("caller "
                + auditedDeletes.erase("SEC-9"));

        try {
            auditedDeletes.erase("SEC-FAIL");
        } catch (IllegalStateException original) {
            System.out.println(
                    "caller caught " + original.getMessage());
        }
    }
}
```

### 9.2. Biên dịch và chạy

Yêu cầu JDK 17 hoặc mới hơn:

```bash
javac --release 17 -encoding UTF-8 AbstractPointcutDemo.java
java AbstractPointcutDemo
```

**Standard output dự kiến theo logic chương trình:**

```text
== read scope ==
readAudit.before fetch A
target.fetch A
readAudit.after fetch value:A
caller value:A
target.erase SEC-9
caller removed:SEC-9
== sensitive delete scope ==
target.fetch B
caller value:B
target.erase PUBLIC-1
caller removed:PUBLIC-1
sensitiveAudit.before erase SEC-9
target.erase SEC-9
sensitiveAudit.after erase removed:SEC-9
caller removed:SEC-9
sensitiveAudit.before erase SEC-FAIL
target.erase SEC-FAIL
sensitiveAudit.error erase IllegalStateException
caller caught storage refused
```

Output được suy ra từ luồng gọi và cấu trúc if/try/catch. Trong một ứng dụng thực, nên thực thi bằng JDK để kiểm chứng, đồng thời viết integration test với chính cơ chế AOP được dùng.

### 9.3. Vì sao thao tác đọc được audit trong scope thứ nhất?

`ReadAudit.matches` trả `true` cho method tên `fetch`. Handler chạy chung template:

```text
readAudit.before fetch A
target.fetch A
readAudit.after fetch value:A
```

Trong khi đó `erase("SEC-9")` **không match** pointcut này. Handler vẫn gọi target để bảo toàn hoạt động nghiệp vụ, nhưng **không chạy logic advice audit**.

**Không match pointcut không có nghĩa phải bỏ qua target.** Với around/interceptor chain, code cần tiếp tục invocation đúng contract, trừ khi có policy chủ động chặn.

### 9.4. Vì sao scope thứ hai chỉ audit một số thao tác xóa?

`SensitiveDeleteAudit.matches` kiểm:

1. Method tên `erase`.
2. Có đúng một argument.
3. Argument đầu là `String`.
4. Giá trị `String` bắt đầu bằng `SEC-`.

Vì vậy:

- `fetch("B")`: không match.
- `erase("PUBLIC-1")`: không match.
- `erase("SEC-9")`: match, chạy before/after.
- `erase("SEC-FAIL")`: match, chạy before rồi error.

**Đây là dynamic argument-value selection**. Một engine AOP chỉ hỗ trợ pointcut static metadata có thể yêu cầu advice guard hoặc một interceptor selector runtime riêng để kiểm giá trị. Không suy rằng mọi ngôn ngữ abstract pointcut đều có sẵn hàm `startsWith` trong pointcut expression.

### 9.5. Vì sao logic advice được tái sử dụng thật?

Hai concrete classes chỉ chứa:

- `matches`: chọn scope.
- `label`: nhãn quan sát.

Chúng **không chứa bản sao** của before/after/error handling hoặc đoạn Reflection unwrap. Nếu đổi cách ghi event ở `AbstractAuditAspect.advise`, cả hai scope dùng logic mới — miễn là chúng được chạy qua template ấy.

### 9.6. Vì sao ngoại lệ không bị biến đổi ngoài ý muốn?

`Repository.erase("SEC-FAIL")` ném `IllegalStateException("storage refused")`. Reflection bọc Throwable của target trong `InvocationTargetException`; helper `invokeTarget` lấy `wrapped.getCause()` rồi throw đúng Throwable gốc.

Advice ghi `sensitiveAudit.error erase IllegalStateException` rồi `throw original`. Caller bắt `IllegalStateException` với message như ban đầu.

**Bài này tập trung vào scope selection**, nhưng demo vẫn tôn trọng hợp đồng exception. Pointcut thay đổi *nơi* advice chạy, không phải giấy phép tự động đổi outcome của target.

### 9.7. Một target, hai proxy, không có nghĩa hai scope được áp đồng thời

`auditedReads` và `auditedDeletes` là **hai proxy khác nhau** cùng tham chiếu `target`. Khi gọi `auditedReads`, chỉ template/selector của `ReadAudit` chạy. Khi gọi `auditedDeletes`, chỉ selector của `SensitiveDeleteAudit` chạy. Demo **không ghép hai aspects vào cùng một advice chain**.

Nếu lồng proxy hoặc dùng weaver áp nhiều concrete aspects lên cùng join point, thứ tự và khả năng advice chạy nhiều lần sẽ khác. **Tái sử dụng template không tự quyết định precedence.**

### 9.8. Giới hạn của Java Dynamic Proxy trong demo

- Chỉ intercept method được gọi qua `Operations` proxy reference.
- Lời gọi raw `target.fetch(...)` không chạy advice.
- Lời gọi nội bộ trong target qua `this` không tự đi qua wrapper proxy.
- Proxy không trực tiếp biểu diễn constructor/field access execution join points.
- `matches` chạy sau khi method đã đi qua proxy; nó không phải một static weaver pointcut parser.
- Không có cflow, weaving-time specialization hoặc abstract aspect compiler trong demo.
- Không tự chứng minh mọi engine cho phép subclass concrete aspect như ở Java classes.
- Nếu phương thức có overload, `matches` nên dùng signature đầy đủ thay vì chỉ method name.
- Nếu exception là checked, cần xem declared throws và contract của Java Dynamic Proxy.

**Đây là minh họa đúng về thiết kế reusable advice + customizable scope trong Java SE, không là bằng chứng của một DSL pointcut cụ thể.**

## 10. Điểm tùy biến chỉ thay scope, không nên thay hợp đồng hành vi tùy tiện

Mục tiêu tái sử dụng là **giữ ổn định một tập bất biến hành vi**:

- Method được chọn có advice before/after/error nhất quán.
- Method không được chọn vẫn hoạt động bình thường.
- Outcome target được giữ hoặc được biến đổi **theo một policy riêng có contract**.
- Logging/metric chỉ chứa dữ liệu được phép.
- Resource và context được dọn đúng dù exception xảy ra.

Nếu các concrete aspects đồng thời override quá nhiều method advice, template có thể mất ý nghĩa. Khi đó cân nhắc:

- Tách **policy object** hoặc **strategy** cho phần thực sự thay đổi.
- Tách nhiều abstract templates khi hành vi đã thực sự khác nhau.
- Đưa các biến thể vào metadata/parameter có kiểu rõ.
- Không dùng inheritance quá sâu chỉ để thay một điều kiện Boolean nhỏ.

**Điểm mở rộng có ích nhất là điểm có phạm vi trách nhiệm rõ và contract dễ kiểm thử.**

## 11. Inheritance và khả năng “override” pointcut

Trong một ngôn ngữ AOP hỗ trợ abstract pointcut, concrete specialization thường cần thỏa:

- Concrete definition có tên/hợp đồng tương ứng.
- Dữ liệu binding và kiểu tương thích.
- Kiểu aspect/concrete declaration hợp lệ theo engine.
- Quy tắc visibility/inheritance cho phép advice sử dụng pointcut.
- Pointcut expression đủ cụ thể để chọn join point thực tế.
- Engine có thể weave những join point được pointcut chọn.

**Không nên áp quy tắc Java override method 1:1 sang mọi AOP language.** Một số công cụ cho phép override named pointcut; một số có cơ chế specialization khác; một số pointcut definitions có tính static/declarative không hoạt động như virtual dispatch của Java methods.

### Thay thế hay cộng dồn?

Khi concrete definition cung cấp một pointcut mới, cần xác định trong engine:

- Nó **thay** định nghĩa abstract (định nghĩa vốn chưa có expression).
- Nó có **bổ sung** những pointcut cụ thể ở lớp cha khác không?
- Advice được **thừa kế** hay được áp riêng trên mỗi aspect?
- Có thể có nhiều concrete descendants hoạt động cùng lúc không?

Không mặc định “một abstract pointcut được cụ thể hóa” nghĩa là engine sẽ chỉ tạo một advice chain trong toàn tiến trình. Hai concrete aspects có thể cùng tồn tại và cùng match một join point.

## 12. Abstract pointcut là điểm mở rộng, không phải công tắc tắt toàn bộ AOP

Nếu định nghĩa pointcut cụ thể luôn false hoặc chọn tập rỗng:

```text
scope(J) = false for all eligible J
```

advice liên quan không chạy ở join point nào của scope ấy. Điều này khác:

- Engine không hỗ trợ/dệt loại join point cần chọn.
- Class target không thuộc weaving scope.
- Caller bypass proxy.
- Một around advice bên ngoài chặn `proceed`.
- Advice có chạy nhưng logger/sink bị disable.

Trong debugging, **“không thấy advice” chưa đủ kết luận “pointcut abstract không được override”**. Cần quan sát matching, interception boundary, advice selection, ordering và output sink độc lập.

### Một concrete scope có thể nguy hiểm vì quá rộng

Một selector như “mọi method của mọi class” có thể bắt cả:

- Logging/sink methods được advice gọi.
- Runtime helper của weaver/interceptor.
- Constructors hoặc lifecycle helpers ngoài dự kiến.
- Methods cực nóng trong chương trình.
- Security-sensitive methods mà advice không được phép thay outcome.

Điều đó có thể gây **advice-induced recursion**, event storm hoặc tác động hiệu năng lớn. Nên có **scope rõ và exclusion cụ thể**, tránh một expression rộng thiếu kiểm soát.

## 13. Pointcut composition và khả năng tái sử dụng ở nhiều cấp

Một abstract pointcut có thể được concretize bằng cách ghép **những named pointcuts khác**:

```text
businessOperation(J) = inBusinessModule(J) AND publicMethod(J)

auditable(J) = businessOperation(J)
               AND NOT insideAuditInfrastructure(J)

selectedRead(J) = auditable(J) AND namedFetch(J)
```

Tách những khái niệm như `businessOperation` hay `insideAuditInfrastructure` ra named pointcuts có thể hữu ích nếu chúng là quy tắc tái sử dụng độc lập.

Nhưng có hai dạng tái sử dụng khác nhau:

1. **Named pointcut composition:** các expression dùng lại nhau như các khối logic.
2. **Abstract pointcut specialization:** một advice/template cố tình **chưa định nghĩa scope**, để một concrete aspect cung cấp sau.

Một hệ thống có thể hỗ trợ một dạng mà không hỗ trợ đầy đủ dạng kia. Không đánh đồng việc đặt tên một expression với việc có hợp đồng abstract pointcut.

## 14. Static selection và dynamic selection

Điểm nối giữa concrete pointcut và advice có thể gồm:

**Static predicates:** type name, method signature, visibility, annotation, caller/callee pattern; phần lớn có thể đánh giá bằng metadata khi weave hoặc khi tạo proxy.

**Dynamic predicates:** argument type/value, receiver object, runtime state, dynamic control flow; có thể cần kiểm **ở từng occurrence** của join point.

```text
Static filter (có thể tối ưu trước)
   method name = erase
       |
Runtime condition
   first argument starts with "SEC-"
       |
Apply advice
```

### Tối ưu và correctness

Nếu một engine đã xác định method chắc chắn không khớp static part, nó có thể bỏ qua dynamic check. Nhưng một proxy handler như demo nhận method invocation rồi mới gọi `matches`. Hiệu năng hai mô hình có thể khác rõ.

Không cache kết quả **runtime argument-value matching** theo **method name** mà quên argument values. Nếu `erase("SEC-9")` match nhưng `erase("PUBLIC-1")` không match, cache `"erase" → true` sẽ làm sai scope.

### Type erasure, overload và bridge methods

Trong Java:

- Generic type erasure có thể làm runtime signature khác source-level parameterization.
- Method overload có cùng tên nhưng type arguments khác.
- Bridge/synthetic methods có thể tồn tại do compiler tạo cho generics/covariant return.
- Proxy interface Method có thể không cùng DeclaringClass với implementation method metadata.
- Annotation có thể xuất hiện ở interface, implementation hoặc override với quy tắc khác.

Một concrete pointcut chuyên biệt hóa bằng reflection cần nêu rõ **metadata được đọc ở đâu**. Với engine weaving, semantics signature/annotation matching cũng phải được kiểm thử theo công cụ thực tế.

## 15. Binding target, receiver, argument: đừng gộp làm một

Một abstract pointcut có thể muốn ràng buộc:

- **`this`** theo nghĩa object của ngữ cảnh join point.
- **`target`** theo nghĩa receiver/target, khi có.
- **`args`** theo runtime argument values.
- **Method/execution metadata**, annotation, caller location.

Những tên này có semantics phụ thuộc **loại join point và engine**. Với method call, caller context và target receiver có thể là **hai object khác nhau**. Với static method có thể không có target instance. Với constructors hoặc asynchronous callbacks, “current receiver” có thể không giống một business target được dự đoán.

Nếu advice template đòi binding một target object cụ thể, concrete pointcut phải chọn **tập join point thực sự có binding ấy**. Không mặc định mọi join point đều có `target` non-null.

### Null/primitive/varargs

Nếu selector dựa trên `args`:

- `null` không cung cấp runtime subtype cụ thể.
- Primitive/wrapper có boxing tùy API/interceptor.
- Varargs ở Java thường thể hiện qua array ở runtime.
- Một số interceptor API nhận `Object[]` argument values với quy tắc riêng.
- Binding vào một loại không tương thích có thể không match hoặc lỗi theo engine.

**Phải kiểm tra signature và binding contract, không chỉ điều kiện string trong advice.**

## 16. Điểm tùy biến phạm vi và điểm tùy biến dữ liệu là hai việc

Giả sử advice audit chung cần một `String id`. Một concrete pointcut chọn `delete` nhưng trong module khác id là một `UUID` hoặc nested field trong request object. Có hai hướng:

1. **Giữ hợp đồng `String id`:** concrete specialization phải cung cấp một binding có dạng String phù hợp nếu ngôn ngữ hỗ trợ.
2. **Tách selection khỏi extraction:** concrete aspect cung cấp scope và một extractor/metadata provider riêng để chuyển join point data sang event model dùng chung.

Điều này tránh dùng một abstract pointcut với signature phi thực tế rồi buộc mọi method cũng nhận `String` giống nhau.

### Không làm mất semantics dữ liệu

Một ID do caller đưa tới có thể không phải canonical business ID. Nếu audit hoặc policy dựa trên nó, cần xác minh identity sau normalization/authorization. Pointcut binding chỉ đưa giá trị vào advice; **không bảo đảm dữ liệu đáng tin hay đã được xác thực**.

## 17. Phạm vi advice và hợp đồng bảo mật

Abstract pointcut rất hữu ích khi tái sử dụng **logging/timing/audit**, nhưng cũng có rủi ro nếu dùng để chọn các **enforcement checks**.

Ví dụ template chung:

```text
checkPermission(target, currentPrincipal);
proceed();
```

Concrete scope xác định **những thao tác nào bắt buộc phải kiểm quyền**. Nếu một concrete pointcut thiếu một overload, một execution path hoặc một callback worker, enforcement có thể bị bypass.

**Không được xem pointcut chỉ là tối ưu chọn log khi scope của nó là một security boundary.**

Cần:

- Xác định danh sách entry points cần được bảo vệ.
- Kiểm cả proxy/raw target, self-invocation, reflection, callback/async.
- Kiểm pointcut trên overload/inheritance/module boundaries.
- Có defense-in-depth ở ranh giới đáng tin.
- Không dùng sampling hoặc “root-only guard” để lược bỏ kiểm tra bắt buộc.
- Test coverage bằng lời gọi từ những đường thực mà ứng dụng cho phép.

### Advice chung không tự có trust level chung

Một concrete aspect áp template lên một package không biến các method ấy thành trusted. Context/current principal phải được cung cấp và xác thực từ hệ thống phù hợp; pointcut chỉ chọn **nơi logic chạy**, không xác minh nội dung identity.

## 18. Tương tác với proxy, self-invocation và weaving

Một concrete pointcut có thể chọn **method execution**, nhưng nếu triển khai AOP qua wrapper proxy, điều mà runtime intercept thường là **lời gọi đi qua proxy**.

```text
caller -> proxy.fetch() -> advice -> target.fetch()
                           |
                    selector.matches()

target.this.otherMethod()  [có thể bypass wrapper proxy]
```

Nếu code target gọi `this.otherMethod()` trực tiếp, Java Dynamic Proxy bên ngoài target **không được gọi lần thứ hai**. Concrete scope dù “chọn method otherMethod” cũng không thể tự khiến handler chạy trên đường bypass đó.

Một bytecode weaver hỗ trợ execution join points có thể can thiệp trực tiếp vào callee body (khi đã weave), và coverage có thể khác. **Abstract pointcut customization không tạo join points mới ngoài những điểm engine có thể quan sát**.

### Loại join point là phần của khả năng áp dụng

Nếu concrete pointcut chọn constructor call, nhưng runtime chỉ hỗ trợ method calls qua interface proxy, selector không thể biến proxy thành công cụ can thiệp constructor. Cần chọn engine/pointcut model phù hợp, hoặc thiết kế lại boundary.

## 19. Khi dùng nhiều concrete aspects cùng một template

Giả sử:

```text
AbstractTimingAspect
    |
    +-- BusinessTiming:  all business execution
    |
    +-- SlowQueryTiming: selected database query execution
```

Một database query nằm trong business execution có thể **khớp cả hai scopes**. Tùy cơ chế, có thể ghi hai durations hoặc tạo hai nested advice activations.

Những câu hỏi bắt buộc:

1. Có hai concrete aspect instances cùng active không?
2. Chúng áp cùng advice body hay hai bản được chuyên biệt hóa?
3. Precedence/order do ai quyết định?
4. Around advice có nesting thế nào?
5. Metric có bị đếm hai lần không?
6. Nếu một advice không proceed, advice còn lại có chạy không?
7. Có state dùng chung bị ghi đè không?
8. Exception sẽ đi qua những layer mapping nào?

**Tái sử dụng bằng inheritance có thể làm tăng số advice occurrences** nếu các concrete scopes chồng lấn. Đó là behavior cần được thiết kế và test, không phải lỗi hiển nhiên của abstraction.

## 20. Abstract pointcut và vòng đời của aspect instance

Một số mô hình AOP cho phép aspect instance dùng chung hoặc liên kết với target/object/control flow. Điểm tùy biến scope **khác trục** với instantiation policy:

| Quyết định | Câu hỏi |
| --- | --- |
| Pointcut scope | Join point nào match? |
| Advice kind | Before/after/around làm gì? |
| Aspect lifecycle | Một instance hay nhiều instance, gắn với đâu? |
| Invocation state | Dữ liệu tạm của lời gọi được lưu ở đâu? |
| Interception coverage | Có thật sự quan sát được join point đó không? |
| Advice precedence | Nhiều aspects khớp thì thứ tự nào? |

Nếu một template advice dùng field `currentId` mutable trên singleton aspect, hai concrete scopes không khắc phục lỗi data race/reentrancy. Dù có per-target aspect, hai calls trên cùng target vẫn có thể đồng thời chia sẻ state.

**Giữ trạng thái per-invocation trong local variables hoặc invocation context**, dùng shared immutable config và concurrency-safe metrics cho dữ liệu thực sự dùng chung. Không dùng abstract pointcut để che một lỗi quản lý state.

## 21. Kiểu dữ liệu và hợp đồng của around advice

Một around advice có quyền chặn, thay return hoặc throw tùy engine. Nếu template chung áp lên nhiều signatures:

- `void` vs reference return vs primitive return có khác biệt.
- Checked exceptions của API caller có thể khác.
- Method async trả `CompletableFuture<T>` có semantics completion riêng.
- Một generic binding/return phải tôn trọng runtime cast và type erasure.

Một template around trả `null` khi skip target có thể chạy với reference return nhưng sẽ gây vấn đề cho primitive return. Một template catch mọi exception rồi trả fallback có thể phá contract của nhiều methods được concrete pointcut mới mở rộng lựa chọn.

**Khi concrete scope mở rộng, phải kiểm tra *hợp đồng của các method mới được chọn* chứ không chỉ syntax của expression.**

### Advice template tối thiểu hóa can thiệp outcome

Với concern quan sát như timing/logging, ưu tiên preserve return/exception:

```text
around:
    start timer
    try:
        return proceed()
    finally:
        record duration
```

Đây là pseudocode AOP. Việc recorder thất bại có thể che target exception nếu `finally` ném lỗi; phải có error policy phù hợp. Nếu advice thực sự thay outcome, policy ấy là một phần contract chứ không chỉ là “pointcut customization”.

## 22. Abstract pointcut và configuration ngoài thời gian biên dịch

Có hai cách thay đổi scope khác nhau:

1. **Compile/weave-time specialization:** concrete pointcut expression được xác định khi aspect được biên dịch/dệt, không đổi theo từng request một cách tùy tiện.
2. **Runtime selection:** interceptor/pointcut provider đọc cấu hình hoặc argument values để quyết định match khi invocation xảy ra, trong giới hạn engine.

Một **abstract pointcut theo ngôn ngữ AOP** không đồng nghĩa một cấu hình có thể **hot reload scope** trong khi chương trình đang chạy. Đổi concrete aspect code có thể đòi build/weave lại hoặc khởi động runtime; dynamic selector lại có thể cập nhật config theo snapshot.

### Khi cần reload runtime

Tách:

- **Immutable policy snapshot**: tập operation/condition được phép.
- **Safe publication**: `volatile` hoặc `AtomicReference` tùy yêu cầu Java.
- **Per-invocation selection**: chọn snapshot một lần nếu cần consistency.
- **Matching semantics**: dynamic condition nào có thể đánh giá lúc runtime?
- **Weaving scope**: các join points chưa được instrument không tự xuất hiện khi reload.

Đừng hứa “thay file config là pointcut bytecode tự mở rộng sang mọi class” nếu runtime AOP không hỗ trợ.

## 23. Hiệu năng: scope càng rộng càng đắt, nhưng có hai lớp chi phí

Một concrete pointcut rộng có thể làm tăng:

- Số join point candidates được dệt.
- Chi phí dynamic predicate per invocation.
- Số lần advice thực thi.
- Allocation của advice context, log event, trace span.
- Locking/metric sink contention.
- Chi phí xử lý exception/unwind.
- Tác động lên hot methods hoặc recursive execution.

Một abstract pointcut **không bắt buộc khiến mỗi invocation phải gọi một method Java virtual `matches`**. Trong mô hình bytecode weaving, expression có thể được compile/optimize để giảm runtime check. Ngược lại Java proxy demo luôn thực hiện selector mỗi handler invocation.

**Đánh giá performance của actual engine và actual scope**, không suy số overhead từ hình thức “abstract” của pointcut.

### Narrow scope một cách có nghĩa

Không nên chọn “mọi public method” khi yêu cầu chỉ là audit thao tác xóa có tác động. Giới hạn theo operation/type/signature, dùng exclusions cho helper/runtime methods và dynamic condition chỉ khi cần.

Nhưng cũng không thu hẹp scope đến mức bỏ sót entry point bắt buộc. Với audit/security, correctness coverage quan trọng hơn chi phí một vài checks.

## 24. Thiết kế module dễ thay đổi bằng abstract pointcut

Một cấu trúc có thể tổ chức theo ba lớp:

```text
Concern contract:
    AuditTemplate
       - event shape
       - exception/return semantics
       - safe logger
       - abstract pointcut "auditScope"

Domain-specific aspect:
    ProductAudit
       - auditScope = product mutation operations

Infrastructure composition:
    proxy/weaver setup
       - enables selected aspects
       - precedence
       - instance lifecycle
       - metrics/security policy
```

Cách tổ chức này tách:

- **Concern ownership:** nhóm sở hữu audit/tracing behavior.
- **Domain scope ownership:** nhóm biết method/module nào thuộc nghiệp vụ.
- **Runtime ownership:** nhóm kiểm soát weaving/proxy, deployment, context propagation.

Không buộc domain team sao chép định dạng log hoặc viết lại exception management, và không buộc người viết core audit biết tên mọi domain method.

### Một rủi ro: thay đổi method name làm scope lặng lẽ rỗng

Nếu concrete pointcut dựa vào pattern tên `erase*`, một lần rename có thể khiến advice ngừng áp dụng dù business behavior vẫn cần audit. Giải pháp gồm:

- Dựa trên contract/interface/annotation có chính sách, nếu phù hợp.
- Viết integration tests xác nhận selected join points.
- Dùng build-time validation/crosscutting reports nếu engine cung cấp.
- Kiểm tra output instrumented trong môi trường test.
- Phân biệt “chắc chắn không match” với “không được weave”.

## 25. Cách tránh scope quá mơ hồ

Một concrete pointcut tốt nên trả lời được:

1. **Đối tượng nào?** Target type/interface/module?
2. **Hoạt động nào?** Signature/constructor/event?
3. **Loại join point nào?** Call hay execution?
4. **Bối cảnh nào?** Runtime args, annotations, cflow?
5. **Excluded paths nào?** Logging/metrics sink, helper, startup?
6. **Số lần kỳ vọng?** Một operation, mỗi attempt hay mỗi execution?
7. **Proxy/weaver có thật sự quan sát đường đó không?**
8. **Điều gì thay đổi nếu method có overload?**
9. **Điều gì xảy ra với subclass, override và generics?**
10. **Mỗi match có cung cấp bindings advice cần không?**
11. **Nếu hai concrete aspects overlap thì ai chạy trước?**
12. **Nếu target throw, advice giữ contract ra sao?**

Nếu không trả lời được, pointcut expression có thể “đúng cú pháp nhưng sai ý nghĩa”.

## 26. Unit test selector và integration test advice

Tách hai tầng kiểm thử:

**Unit test concrete selector**

- `fetch("A")` match scope read.
- `erase("SEC-9")` không match scope read.
- `erase("SEC-9")` match scope sensitive delete.
- `erase("PUBLIC-1")` không match scope sensitive delete.
- `erase(null)` có xử lý đúng theo contract không?
- Signature overload có bị chọn nhầm không?

**Integration test thực qua interceptor/weaver**

- Advice được gọi chính xác ở join point được chọn.
- Target vẫn chạy khi selector không match.
- Return/Throwable được preserve theo contract.
- Raw target/proxy self-invocation được hiểu đúng.
- Nhiều concrete aspects chồng lấn có precedence đúng.
- Advice không tự instrument logging sink gây recursion.
- Async worker/callback thuộc phạm vi nào?
- Các module/class loaders cần thiết có được weave không?
- Bảo mật/audit bắt buộc không bị bỏ sót.

### Chỉ test `matches` chưa đủ

Một selector trả true trong unit test nhưng **không bao giờ được gọi ở runtime** nếu caller không đi qua proxy hoặc execution chưa được weave. Ngược lại, một advice có thể chạy ở method do pattern quá rộng dù selector unit test chỉ kiểm vài ví dụ đơn giản.

**Coverage của pointcut và correctness của advice là hai loại test riêng.**

## 27. Ma trận chọn pointcut cho cùng một template

| Concrete scope | Điều kiện điển hình | Rủi ro cần kiểm |
| --- | --- | --- |
| Method đọc | Operation name/signature | Method rename, overload, cache read ngoài proxy |
| Method ghi/xóa | Mutation entry points | Bypass, self-call, side effects |
| Theo annotation | Annotation trên method/type | Interface vs implementation annotation, inheritance |
| Theo target type | Subclass/implements interface | Runtime subtype, proxy type, loader |
| Theo tham số | Argument type/value | Null, boxing, runtime-only matching |
| Theo tenant/request | Verified context + scope | Security, propagation, stale context |
| Theo control flow | Join point trong flow gốc | Async boundary, nested flow, recursion |
| Theo source module | Package/module naming | Refactor làm scope đổi im lặng |
| Theo exception outcome | Around/after-throwing behavior | Type contract, retry/translation |
| Theo profile/config | Runtime selector snapshot | Reload, cache invalidation, weaving coverage |

**Điểm tùy biến không nhất thiết phải nằm ở một concrete inheritance tree.** Nếu hệ thống cần hàng trăm tổ hợp động, composition strategies hoặc cấu hình có thể đơn giản hơn đa cấp subclassing.

## 28. Lỗi thiết kế phổ biến

1. **“Abstract pointcut là một method Java có thể gọi.”** Không, đó là hợp đồng chọn join point trong mô hình AOP hỗ trợ.
2. **“Abstract aspect nghĩa là advice chưa được viết.”** Advice có thể đã được định nghĩa đầy đủ; chỉ scope trừu tượng.
3. **“Concrete pointcut mặc nhiên chỉ thu hẹp scope.”** Có thể chọn tập rộng khác hoàn toàn.
4. **“Tái sử dụng advice nghĩa là chỉ có một instance aspect.”** Logic reuse và lifecycle khác nhau.
5. **“Khai báo abstract pointcut là được weave tất cả method.”** Cần concrete definition và weaving scope.
6. **“Một pointcut tên giống nhau ở mọi engine có cùng binding semantics.”** Không có cú pháp phổ quát.
7. **“Tên parameter trùng nhau là binding tự động.”** Phải theo contract engine.
8. **“Match method name là đủ với overload.”** Cần signature khi semantics khác.
9. **“Dynamic argument value luôn đánh giá lúc weave-time.”** Giá trị runtime có thể chỉ biết khi gọi.
10. **“Đổi concrete scope không thể đổi hành vi.”** Caller có thể được thêm/bớt advice và outcome/latency thay đổi.
11. **“Hai subclasses không thể áp cùng join point.”** Scopes có thể overlap.
12. **“Template advice chung bảo đảm không chạy hai lần.”** Precedence/composition cần được kiểm.
13. **“Per-target aspect bảo đảm per-invocation state an toàn.”** Hai calls trên cùng target có thể concurrent.
14. **“Thêm synchronized vào singleton sửa state correlation.”** Chọn đúng scope per-call quan trọng hơn.
15. **“Pointcut có thể thay security boundary.”** Bypass raw/proxy/async cần phòng vệ thích hợp.
16. **“Callback được đăng ký trong method được chọn thì callback cũng được chọn.”** Registration khác execution.
17. **“Call pointcut tương đương execution pointcut.”** Hai vị trí runtime khác nhau.
18. **“Self-invocation trong wrapper proxy chắc được can thiệp.”** Có thể bypass.
19. **“Abstract pointcut làm dynamic config reload tự động.”** Phụ thuộc runtime và weaving model.
20. **“Một map cache kết quả match theo method name luôn đúng.”** Dynamic args/loader/revision có thể khác.
21. **“Một Java Predicate chính là cú pháp abstract pointcut native.”** Predicate chỉ mô phỏng khái niệm matching.
22. **“Pointcut rộng chỉ gây thêm log, không tác động correctness.”** Advice có thể chặn, retry, alter exception.
23. **“Không có log nghĩa là không match pointcut.”** Có thể thiếu interception hoặc sink bị tắt.
24. **“Một compiled aspect dùng được qua mọi class loader.”** Weaving/type identity có thể khác.
25. **“Aspect inheritance giống 100% Java method override.”** Semantics DSL và weaving có thể khác.
26. **“Tất cả return types đều phù hợp một around advice trả null.”** Primitive/non-null contract khác.
27. **“Một concrete aspect luôn thay thế aspect khác.”** Nhiều aspects có thể cùng active.
28. **“Không cần test khi sửa pointcut expression.”** Đây là thay đổi phạm vi hành vi.
29. **“Logging helper ngoài scope theo trực giác.”** Nếu pattern rộng, advice có thể tự gọi lại mình.
30. **“Cụ thể hóa pointcut bảo đảm áp vào mọi async task của request.”** Cflow/ThreadLocal không tự xuyên thread.

## 29. Câu hỏi nâng cao: một abstract pointcut có nên biết domain không?

Có hai xu hướng:

**Template tối thiểu:** `AuditTemplate` chỉ khai báo `scope(...)` và xử lý event generic, không biết `Product` hay `Payment`.

**Template domain-aware:** một abstract template có thể biết một abstraction domain chung như `BusinessOperation`, nhưng cụ thể hóa subtypes vẫn để concrete definitions.

Không có một mức trừu tượng tối ưu cho mọi hệ thống. Nếu template phải chứa nhiều `if (module == ...)` hoặc hiểu hàng loạt DTO riêng của từng domain, abstraction đã có dấu hiệu **đưa variability ngược vào core**.

### Một hướng khác: composition hơn inheritance

```java
// Chỉ minh họa ý tưởng strategy, không phải ứng dụng chạy độc lập.
interface InvocationSelector {
    boolean matches(Invocation invocation);
}

final class AuditInterceptor {
    private final InvocationSelector selector;
    // Logic advice chung; selector được inject.
}
```

Composition phù hợp khi runtime cần kết hợp selectors linh hoạt. Abstract aspect inheritance phù hợp khi ngôn ngữ AOP hỗ trợ và việc chuyên biệt hóa có cấu trúc ổn định.

Hai hướng đều đạt mục tiêu **tách where khỏi what**, nhưng khác về runtime semantics, lifecycle, tooling và khả năng biểu đạt pointcut.

## 30. Bài tập thực hành

1. Chạy `AbstractPointcutDemo.java` và đối chiếu output của từng lời gọi.
2. Vì sao `ReadAudit` và `SensitiveDeleteAudit` không sao chép mã `try/catch` của template?
3. Thêm `Operations.update(String id)`; thiết kế concrete scope chỉ áp dụng cho update và giữ nguyên template.
4. Thử đổi `ReadAudit.matches` thành match mọi method. Những dòng log nào được thêm và vì sao?
5. Sửa `SensitiveDeleteAudit` để chỉ match `SEC-` nhưng không match `SEC-FAIL`; caller có còn nhận lỗi không?
6. Thêm overload method có hai arguments vào interface; vì sao match theo `getName()` có thể quá rộng?
7. Tạo hai proxies lồng nhau, một read selector bên ngoài và một broad selector bên trong. Dự đoán thứ tự before/after khi cả hai match.
8. Viết một named pointcut khái niệm `businessOperation`, rồi dùng nó để dựng `selectedMutation` bằng intersection.
9. Thiết kế abstract pointcut cần bind một `String id`; nếu domain dùng `UUID`, bạn sẽ thích ứng thế nào?
10. So sánh abstract pointcut với một abstract Java method; điều gì giống và khác về runtime execution?
11. Pointcut chọn annotation trên implementation method; nếu proxy chỉ có `Method` từ interface, metadata có thể khác ra sao?
12. Thử gọi raw target thay vì proxy trong demo. Vì sao selector không được gọi?
13. Tạo một target method gọi nội bộ một method khác; wrapper proxy thấy những lời gọi nào?
14. Thiết kế integration test bảo đảm method nhạy cảm được audit từ mọi đường đi bắt buộc.
15. Với một pointcut dynamic theo argument, vì sao cache kết quả chỉ theo method name có thể sai?
16. Tách một template logging ra hai concrete aspects có scopes giao nhau. Metric counting bị ảnh hưởng thế nào?
17. Thêm một aspect đo thời gian around, kiểm inclusive duration khi nested advice và target gọi lồng nhau.
18. Xây một selector theo immutable config snapshot và đổi scope runtime; phân biệt với compile-time pointcut specialization.
19. Vẽ trình tự matching → advice → target → result/throw khi scope có match và không match.
20. Thiết kế một test phân biệt “pointcut không match” với “join point chưa được instrument”.
21. Đề xuất exclusions để advice audit không tự intercept audit writer của mình.
22. Với một async method trả `CompletableFuture`, xác định phần nào được advice sync quan sát và phần nào cần observer hoàn tất.
23. Phân tích concrete scope có thể vi phạm security contract khi chỉ match method public nhưng code có đường raw/internal bypass.
24. So sánh inheritance và strategy composition cho một sản phẩm có hàng trăm policy scopes tùy tenant.
25. Lập checklist review khi sửa expression của một concrete pointcut đã dùng trong hệ thống production.

**Tự kiểm tra:** Abstract pointcut là gì, khác named pointcut thông thường ra sao? Tại sao advice đã có thể được viết đầy đủ khi pointcut chưa cụ thể? Binding nào phải được concrete specialization bảo toàn? Tập join points của hai concrete aspects có thể chồng lấn không? Vì sao một selector Java trong proxy chỉ là mô phỏng? Một pointcut cụ thể có tự vượt qua self-invocation proxy bypass không? Khi scope thay đổi, loại kiểm thử nào cần thực hiện để bảo đảm không bỏ sót audit/security?

## Kết luận

**Pointcut trừu tượng là một điểm tùy biến phạm vi của AOP:** thay vì lặp lại cùng advice cho nhiều module, ta giữ **hành vi cắt ngang dùng chung** và để mỗi concrete specialization cung cấp **điều kiện chọn join point** tương ứng. Cách thiết kế này giúp chuẩn hóa logging, timing, audit và xử lý lỗi, đồng thời đưa kiến thức domain về phạm vi áp dụng ra khỏi logic concern dùng chung.

Tuy nhiên, abstract pointcut không làm thay nhiệm vụ của pointcut matching chính xác, binding đúng kiểu, weaving/proxy coverage, aspect lifecycle, advice ordering và kiểm thử hợp đồng caller. Hãy xác định rõ **what (advice làm gì)**, **where (pointcut chọn đâu)**, **when (join point runtime nào xuất hiện)** và **how (engine nào can thiệp)**. Khi bốn yếu tố đó được kiểm chứng, pointcut trừu tượng trở thành một cơ chế tái sử dụng mạnh mà không che đi các giới hạn thực tế của AOP.
# Giới hạn kiểu trả về và tính tương thích của advice bao quanh

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), **around advice** (lời khuyên bao quanh) có thể đặt hành vi trước và sau một **join point**; ở những cơ chế hỗ trợ, nó còn có thể quyết định có gọi tiếp thao tác đích (*proceed*) hay không, chuyển đổi kết quả hoặc xử lý ngoại lệ. Tuy vậy, **khả năng trả về một giá trị từ advice không đồng nghĩa với quyền trả về bất kỳ loại dữ liệu nào cho người gọi**.

Nếu một phương thức khai báo trả về `String`, `int`, `void`, một kiểu generic hoặc một đối tượng bất đồng bộ, kết quả mà chuỗi advice cuối cùng đưa tới caller phải phù hợp với **hợp đồng kiểu và ngữ nghĩa của chính join point**. Một giá trị sai kiểu có thể gây `ClassCastException`, lỗi unboxing, lỗi chỉ phát sinh muộn ở caller, hoặc làm sai kết quả nghiệp vụ dù code chạy được.

**Nguyên tắc cốt lõi:** Around advice có khả năng *điều khiển outcome* khi công cụ cho phép, nhưng outcome mới vẫn phải tương thích với chữ ký thực thi, quy tắc kiểu của ngôn ngữ và hợp đồng của API. Phải phân biệt **loại giá trị ở code advice**, **loại trả về của target**, **giá trị thực sự tới caller** và **giới hạn của cơ chế AOP đang dùng**.

> Bài này trình bày AOP cơ bản và nâng cao nói chung, không phụ thuộc một framework. Các từ `around`, `proceed`, `return value`, `join point` và `weaving` mô tả các khái niệm; cú pháp khai báo advice, quy tắc binding, quyền thay kết quả và thời điểm kiểm tra kiểu phải xác minh theo công cụ triển khai thực tế.

## 1. Ba tầng cần phân biệt khi nói “kiểu trả về”

Xét phương thức Java:

```java
// Một khai báo minh họa:
String format(String input);
```

Ta có ba tầng khác nhau:

1. **Kiểu trả về của phương thức đích:** `String`, thể hiện API mà caller sử dụng.
2. **Kiểu mà around advice tự khai báo hoặc cơ chế dispatch nhận:** có thể là `Object` trong API interceptor tổng quát; có thể là một kiểu cụ thể hoặc giá trị trừu tượng khác.
3. **Kiểu và giá trị thực tế được chuyển tới caller:** ví dụ một object `String`, `null`, hoặc một object sai kiểu khiến runtime không chuyển thành `String` được.

Nếu interceptor có chữ ký `Object intercept(...)`, việc hàm này biên dịch được với `return 42;` **không biến `42` thành một `String` hợp lệ** cho phương thức `format`. Thông thường, runtime/proxy sẽ ép kiểu kết quả trả về trước khi chuyển nó tới caller. Ở một cơ chế weaving khác, lỗi có thể được phát hiện sớm hoặc muộn hơn, nhưng **hợp đồng kết quả của phương thức đích không biến mất**.

### Kết quả là một trong hai outcome

Với một thao tác đồng bộ, hãy hình dung:

```text
Outcome<T> =
    Return(T value)
    OR
    Throw(Throwable error)
```

Đây là ký pháp tư duy, **không phải khai báo Java độc lập**. Around advice có thể giữ nguyên một outcome hoặc biến đổi nó nếu được hỗ trợ:

```text
Return(original) -> Return(transformed)
Throw(error)     -> Throw(mappedError)
Throw(error)     -> Return(fallback)
Return(value)    -> Throw(policyViolation)
```

Mỗi phép biến đổi là một quyết định có hệ quả khác nhau. Ví dụ chuyển một lỗi nghiệp vụ thành fallback hợp lệ về kiểu vẫn chưa chắc hợp lệ về nghiệp vụ.

## 2. Khi nào around advice có quyền thay kết quả?

Một mô hình advice bao quanh thường hoạt động theo ý tưởng:

```text
around(joinPoint):
    before()
    result = proceed()          // gọi chuỗi advice / target tiếp theo
    after(result)
    return transform(result)
```

Một around advice có thể **không gọi `proceed`**, trả kết quả từ cache hoặc trả fallback; có thể gọi tiếp nhiều lần để retry khi engine cho phép. Tuy nhiên, nhiều công cụ áp đặt ràng buộc:

- Chỉ hỗ trợ around trên một số loại join point, ví dụ method call hoặc execution.
- Có engine cho phép truyền argument mới vào `proceed`; engine khác chỉ cho gọi tiếp với đối số cũ.
- Advice có thể buộc khai báo cùng loại trả về với target hoặc sử dụng một kiểu bao quát rồi kiểm tra tại runtime.
- Một số môi trường chỉ có callback before/after, không có quyền trả kết quả thay thế.
- Quyền thay outcome của advice có thể bị giới hạn bởi phương thức `void`, primitive, checked exception hoặc cơ chế proxy.

**Không coi một đoạn code viết trong class tên “Aspect” là around advice có đầy đủ quyền.** Cần xem API của cơ chế can thiệp và kiểm thử caller thực sự nhận gì.

### Quan sát kết quả không đồng nghĩa thay kết quả

After-returning advice thường thích hợp để **đọc** giá trị thành công. Việc một biến tên `result` được truyền cho nó không chứng minh rằng `result = replacement` sẽ đổi giá trị caller nhận. Nếu caller phải thấy reference mới hoặc kết quả khác, cần API có quyền thay outcome, thường là around hay hook tương đương.

Ngược lại, sửa *trạng thái* của một object mutable được trả về có thể làm caller thấy dữ liệu đổi dù reference kết quả vẫn giữ nguyên. **Mutation object** và **replacement kết quả** là hai hành vi riêng, có độ rủi ro khác nhau.

## 3. Ma trận tương thích kiểu trả về

| Khai báo target | Around có thể trả | Sai lầm dễ gặp |
| --- | --- | --- |
| `String` | Object thực tế là `String` hoặc `null` nếu contract cho phép | Trả `Integer` chỉ vì API advice khai báo `Object` |
| `Object` | Bất kỳ reference object hợp lệ theo nghiệp vụ; `null` nếu được phép | Nghĩ rằng mọi kiểu đều đúng về ý nghĩa nghiệp vụ |
| `Number` | Một object thuộc subtype của `Number` (ví dụ `Integer`) | Trả `String` hoặc object không có quan hệ gán kiểu |
| `int` | Giá trị phù hợp primitive, thường qua `Integer` khi dùng proxy Java | Trả `null`, `String` hoặc wrapper không tương thích |
| `boolean` | `Boolean` phù hợp cho bước unboxing trong proxy Java | Trả chuỗi `"true"` thay vì boolean |
| `void` | Theo Java dynamic proxy, handler trả về sẽ bị bỏ qua; `null` là lựa chọn rõ ràng | Tưởng có thể truyền một giá trị thành công tới caller qua phương thức `void` |
| `List<String>` | Một đối tượng phù hợp contract `List<String>` | Dùng `List<Integer>` vì cả hai đều qua được raw `List` |
| `Optional<T>` | Một `Optional` hợp lệ với nội dung phù hợp `T` | Trả `null` hoặc nhét kiểu phần tử sai |
| `CompletableFuture<T>` | Future/stage hợp lệ theo declared return type | Trả ngay `T` thay cho object future |
| `T` trong generic method | Kết quả phải hợp đồng với kiểu được suy ra/bound tại caller | Chỉ nhìn type erasure rồi trả object sai kiểu cụ thể |

Bảng mô tả hướng đánh giá, **không bảo đảm một engine AOP sẽ cho phép mọi phép thay thế ở cột giữa**. Một giá trị hợp lệ về Java type vẫn phải đáp ứng non-null contract, bất biến nghiệp vụ, quyền truy cập và tác dụng phụ đã được API cam kết.

## 4. Reference return: subtype, null và kiểu thực tế

Một method khai báo trả về `CharSequence` có thể trả `String` hoặc `StringBuilder` vì cả hai triển khai `CharSequence`. Một method khai báo `String` thì không thể trả `StringBuilder` trực tiếp vì `StringBuilder` không phải subtype của `String`.

Ví dụ:

```java
// Khai báo minh họa, không phải chương trình độc lập.
CharSequence text();
String fixedText();
```

Giả sử around cho phép thay return object:

- Với `text()`, `return new StringBuilder("ok")` có thể tương thích về mặt type.
- Với `fixedText()`, cùng object đó không tương thích `String`.
- Trả `null` về mặt JVM có thể gán cho reference return, nhưng nếu contract không cho null thì caller có thể lỗi khi sử dụng.

**Nullability** là một phần của hợp đồng rộng hơn hệ thống kiểu cơ bản trong nhiều API Java. Vì vậy quanh một method có annotation hoặc quy ước “non-null”, không nên trả `null` để biểu thị “không tìm thấy” trừ khi contract thực sự cho phép.

### 4.1. Tại sao `Object` trong advice dễ gây hiểu nhầm?

Một interceptor Java SE thường có API kiểu:

```java
Object invoke(Object proxy, java.lang.reflect.Method method, Object[] args)
        throws Throwable;
```

Đó là kiểu trả về của **handler**, không phải của mọi phương thức được intercept. Với method trả `String`, proxy được sinh phải chuyển object handler trả về thành `String`. Một object `Integer` có thể gây `ClassCastException` khi proxy thực hiện phép chuyển này, **ngay cả khi handler chạy xong mà không tự báo lỗi**.

### 4.2. Kiểu ở compile time và runtime

Java có các phép kiểm tra kiểu tại compile time, nhưng một API interceptor dùng `Object` có thể trì hoãn kiểm tra tới runtime. Do đó:

- Code advice **biên dịch** không phải chứng cứ kết quả hợp lệ.
- Một câu lệnh `(String) result` chỉ ép kiểu, không tự biến object kiểu khác thành String.
- `String.valueOf(object)` tạo chuỗi biểu diễn; đó là **phép biến đổi có chủ đích**, khác với cast. Giá trị chuỗi mới cũng cần đáp ứng semantics của target.

## 5. Primitive return: boxing, unboxing và lỗi null

Trong Java, method trả primitive không trả trực tiếp một reference `null`. Tuy vậy, handler proxy có thể sử dụng `Object` nên nó phải trả một wrapper phù hợp để proxy **unbox**.

Ví dụ contract:

```java
int count();
boolean isEnabled();
long duration();
```

Trong mô hình Java dynamic proxy, những giá trị tương thích thông thường là `Integer`, `Boolean` và `Long` tương ứng. **Đừng kỳ vọng `Integer` tự động được proxy coi như `Long`** chỉ vì cả hai là số. Unboxing wrapper cụ thể là bước runtime do code được sinh thực hiện, và giá trị kiểu khác có thể gây `ClassCastException`.

Nếu handler trả `null` cho method trả `int`, proxy cố unbox một reference null và có thể gây `NullPointerException`. Nếu handler trả `"17"` thì không có cơ chế chuyển chuỗi thành số tự động chỉ vì method khai báo `int`.

### 5.1. Around thay primitive result

Một around advice có thể đọc `int` đã được boxing rồi tính toán:

```java
// Pseudocode logic của một interceptor đã biết target trả int.
int original = (Integer) proceed();
int adjusted = original + 1;
return Integer.valueOf(adjusted);
```

Đây là đoạn minh họa **không độc lập**, giả định `proceed()` trả `Object` với object `Integer`. Kết quả trả về phải được boxing thành wrapper phù hợp để hệ thống chuyển về `int`.

Các rủi ro khác vẫn còn: overflow số nguyên, giá trị không nằm trong miền hợp lệ, giới hạn trên/dưới, hoặc điều kiện nghiệp vụ có thể bị phá vỡ vì advice cộng/trừ tùy ý.

### 5.2. Primitive khác wrapper reference

`Integer getCount()` là **reference return**, nên về mặt kiểu có thể trả `null`. `int getCount()` là **primitive return**, không thể trả null như một giá trị hoàn tất bình thường. Nếu ứng dụng dùng null làm tín hiệu “không có dữ liệu”, việc đổi return type từ `Integer` sang `int` ảnh hưởng sâu tới lựa chọn fallback của around.

## 6. `void` return: có thể chạy logic, không có giá trị cho caller

Một method `void publish(String message)` có thể có side effect nhưng caller không nhận một giá trị kết quả từ method. Around advice vẫn có thể ghi log, chặn, ném exception hoặc điều khiển có gọi target hay không nếu cơ chế cho phép; nhưng **không thể biến API `void` thành API trả `String` chỉ bằng cách `return "done"` trong interceptor**.

Với **Java dynamic proxy** theo contract của `InvocationHandler`, object handler trả về cho phương thức khai báo `void` được **bỏ qua**. Vì vậy convention rõ ràng là `return null` sau khi hoàn thành interception.

Với một **hệ thống advice khai báo tĩnh**, việc trả một object cho một join point `void` có thể bị cấm hoặc đòi hỏi cú pháp riêng. Không lấy hành vi “proxy bỏ qua return object” làm luật áp dụng chung cho mọi ngôn ngữ AOP.

### 6.1. `void` vẫn có thể thất bại

`void` không có kết quả trả về hữu ích, nhưng method vẫn có thể **throw**. Around có thể quan sát hoặc thay đổi luồng lỗi nếu được hỗ trợ. Khả năng ghi log “done” sau proceed không chứng minh publish đã thành công nếu target ném ngoại lệ hoặc công việc chỉ được gửi đi bất đồng bộ.

### 6.2. Phân biệt không có kết quả với “thành công”

Một method `void` có thể chỉ ghi vào queue, cập nhật trạng thái tạm hoặc khởi động công việc khác. Việc nó return không nhất thiết đồng nghĩa tác vụ cuối cùng hoàn tất; advice cần hiểu contract và các kênh trạng thái bên ngoài.

## 7. Ví dụ Java 17+ chạy được: kiểu đúng, kiểu sai và kết quả caller thấy

Ví dụ này dùng **`java.lang.reflect.Proxy`** trong Java SE. Một proxy thứ nhất minh họa around advice biến đổi hợp lệ kết quả `String` và `int`, đồng thời giữ đúng semantics của `void`. Một proxy thứ hai cố tình trả giá trị không tương thích để quan sát lỗi tại ranh giới caller.

Đây là ví dụ **runtime interception**, không phải một DSL pointcut đầy đủ và không khẳng định mọi công cụ AOP có cùng quyền thay kết quả. Chỉ những lời gọi đi qua proxy mới chịu tác động.

Lưu toàn bộ vào tệp **`AroundReturnCompatibilityDemo.java`** (UTF-8):

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AroundReturnCompatibilityDemo {
    public interface Operations {
        String label(String name);
        int doubleValue(int value);
        void notifyEvent(String event);
    }

    public static final class Target implements Operations {
        @Override
        public String label(String name) {
            System.out.println("target label " + name);
            return "hello " + name;
        }

        @Override
        public int doubleValue(int value) {
            System.out.println("target double " + value);
            return value * 2;
        }

        @Override
        public void notifyEvent(String event) {
            System.out.println("target notify " + event);
        }
    }

    static Object proceed(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static Operations compatibleAround(Operations target) {
        return (Operations) Proxy.newProxyInstance(
                Operations.class.getClassLoader(),
                new Class<?>[] { Operations.class },
                (proxy, method, args) -> {
                    String name = method.getName();
                    System.out.println("around enter " + name);

                    try {
                        Object original = proceed(method, target, args);

                        if (method.getReturnType() == void.class) {
                            System.out.println("around leave void");
                            return null;
                        }

                        if (name.equals("label")) {
                            String mapped = "[" + (String) original + "]";
                            System.out.println("around leave label");
                            return mapped;
                        }

                        if (name.equals("doubleValue")) {
                            Integer mapped = ((Integer) original) + 1;
                            System.out.println("around leave doubleValue");
                            return mapped;
                        }

                        return original;
                    } finally {
                        System.out.println("around finally " + name);
                    }
                });
    }

    // Proxy cố ý trả các giá trị vi phạm return contract.
    // Không gọi target: chỉ nhằm quan sát cơ chế kiểm tra kiểu.
    static Operations incompatibleAround() {
        return (Operations) Proxy.newProxyInstance(
                Operations.class.getClassLoader(),
                new Class<?>[] { Operations.class },
                (proxy, method, args) -> {
                    return switch (method.getName()) {
                        case "label" -> Integer.valueOf(42);
                        case "doubleValue" ->
                                ((Integer) args[0]) == 0
                                        ? null : "wrong type";
                        case "notifyEvent" -> {
                            System.out.println("bad around void");
                            yield "ignored";
                        }
                        default -> throw new AssertionError("unexpected");
                    };
                });
    }

    public static void main(String[] args) {
        Operations service = compatibleAround(new Target());

        System.out.println("caller " + service.label("Ana"));
        System.out.println("caller " + service.doubleValue(4));
        service.notifyEvent("ready");

        Operations bad = incompatibleAround();

        try {
            bad.label("Q");
        } catch (ClassCastException error) {
            System.out.println("bad label: ClassCastException");
        }

        try {
            bad.doubleValue(1);
        } catch (ClassCastException error) {
            System.out.println("bad int type: ClassCastException");
        }

        try {
            bad.doubleValue(0);
        } catch (NullPointerException error) {
            System.out.println("bad int null: NullPointerException");
        }

        bad.notifyEvent("Q");
        System.out.println("caller after bad void");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 AroundReturnCompatibilityDemo.java
java AroundReturnCompatibilityDemo
```

**Standard output dự kiến chính xác:**

```text
around enter label
target label Ana
around leave label
around finally label
caller [hello Ana]
around enter doubleValue
target double 4
around leave doubleValue
around finally doubleValue
caller 9
around enter notifyEvent
target notify ready
around leave void
around finally notifyEvent
bad label: ClassCastException
bad int type: ClassCastException
bad int null: NullPointerException
bad around void
caller after bad void
```

### 7.1. Tại sao `label` hợp lệ?

Target trả về `"hello Ana"` kiểu `String`. Around bọc kết quả thành `"[hello Ana]"`, vẫn là một `String`, nên proxy có thể chuyển tới caller. Việc biến đổi có hợp lệ về nghiệp vụ hay không phụ thuộc contract API, nhưng **hợp lệ về kiểu** trong ví dụ.

### 7.2. Tại sao `doubleValue` hợp lệ?

Target trả primitive `int` bằng `8`. Reflection qua `Method.invoke` đưa kết quả cho interceptor dưới dạng object `Integer`. Around chuyển thành `Integer.valueOf(9)` thông qua phép cộng rồi boxing tự động. Proxy có thể unbox `Integer` thành `int` cho caller. Đây là một phép biến đổi **đúng wrapper type**, không phải tự động chuyển mọi `Number` thành primitive yêu cầu.

### 7.3. Tại sao `void` hợp lệ?

Target `notifyEvent` in sự kiện rồi kết thúc, `Method.invoke` trả `null` cho phương thức `void`. Around in dòng thông tin và trả `null`. Không có giá trị cho caller. Điều quan trọng là caller vẫn nhận lại quyền điều khiển bình thường nếu không ném ngoại lệ.

### 7.4. Tại sao proxy sai gặp `ClassCastException`?

Với `label`, handler cố ý trả object `Integer(42)` trong khi method khai báo `String`. Proxy cần chuyển kết quả thành `String`, nên runtime báo `ClassCastException`. Với `doubleValue(1)`, handler trả chuỗi `"wrong type"` trong khi return contract là primitive `int`; proxy cần `Integer` để unbox và gặp lỗi tương thích kiểu.

### 7.5. Tại sao `null` gây lỗi ở primitive?

Với `doubleValue(0)`, handler trả `null` cho `int`. Proxy cần unbox một `Integer`, nhưng reference là null nên `NullPointerException`. Đây là vấn đề của **kiểu trả về**, không phải vì Java không thể chứa null trong biến `Object` của handler.

### 7.6. Tại sao return từ bad `void` bị bỏ qua?

`incompatibleAround` trả chuỗi `"ignored"` khi method được khai báo `void`. Với **Java dynamic proxy**, return object của handler cho method `void` bị bỏ qua; caller chỉ thấy lời gọi hoàn tất. Điều này **không có nghĩa target đã chạy**: trong proxy sai, target không được gọi. Ví dụ cố ý chỉ cho thấy giới hạn của return contract, không phải một implementation ứng dụng đúng.

### 7.7. Vì sao ví dụ phải có cả caller và target?

Chỉ đọc code handler chưa đủ. Ta cần xác nhận **target có chạy không**, **target tạo giá trị gì**, **around trả gì**, **caller nhận gì** hoặc **caller gặp exception nào**. Một matcher/handler có thể chạy đúng nhưng kết quả chuyển tới caller sai kiểu; lỗi chỉ xuất hiện ở bước trả kết quả.

## 8. Around có thể không gọi tiếp: khi nào phải tạo kết quả thay thế?

Nếu around không gọi `proceed`, nó có thể trả một giá trị từ cache, fallback hoặc một kết quả tổng hợp **nếu contract và cơ chế cho phép**. Nhưng nó phải đảm bảo:

- **Type:** cùng kiểu hoặc subtype tương thích với khai báo.
- **Nullability:** không vi phạm non-null/primitive.
- **Business contract:** caller không bị báo thành công giả nếu nghiệp vụ bắt buộc chưa thực thi.
- **Side effects:** bỏ qua target có làm thiếu ghi dữ liệu, audit, transaction hoặc phát sự kiện không?
- **Ordering:** những advice nằm phía trong around có thể **không chạy** nếu bị bỏ qua.
- **Exceptions:** người gọi vẫn có thể chờ một số loại lỗi; fallback phải được định nghĩa rõ.

Ví dụ một method `int availableSeats()` có thể sử dụng cache đã được xác thực để trả về một `Integer` phù hợp trong proxy. Nhưng method `void chargeMoney()` không thể “báo đã thu tiền” chỉ bằng cách around không gọi target và trả một chuỗi; caller thậm chí không có kênh return value để nhận chuỗi đó.

### “Đúng kiểu” không đồng nghĩa “đúng dữ liệu”

Trả `0` cho mọi lỗi của `availableSeats()` có thể khiến hệ thống tưởng không còn chỗ thay vì hiểu rằng dịch vụ dữ liệu đang thất bại. Trả `true` cho một thao tác cấp quyền khi chưa được kiểm tra có thể gây lỗ hổng. **Fallback có nghĩa nghiệp vụ** cần được thiết kế như một phần hợp đồng API, không thêm ngẫu nhiên trong aspect.

## 9. Around gọi tiếp nhiều lần: cùng một chữ ký, nhiều kết quả

Một số cơ chế AOP cho phép around gọi `proceed` nhiều lần để retry. Mỗi lần có thể tạo một return value hoặc exception khác nhau. Around phải quyết định outcome cuối cùng cho caller.

```text
Caller gọi send() một lần
  around:
    proceed #1 -> timeout
    proceed #2 -> Return("ok")
    return "ok"
```

Ký pháp trên là sơ đồ khái niệm. Tương thích kiểu của `"ok"` chỉ là một khía cạnh; nếu lần #1 **đã gửi thành công nhưng phản hồi bị mất**, retry có thể gửi trùng. Những thao tác có side effect như thanh toán, gửi thông điệp, ghi dữ liệu cần idempotency key hoặc cơ chế chống lặp phù hợp.

Với method `void`, retry vẫn có thể gây side effect trùng dù caller không nhận giá trị. Với primitive return, các lỗi của retry vẫn có thể xảy ra ở bước unboxing. Đừng dùng retry chỉ vì API around cho phép gọi tiếp.

## 10. Checked exceptions, unchecked exceptions và return contract

Một phương thức có thể khai báo:

```java
// Ví dụ khai báo.
String load(String key) throws java.io.IOException;
```

Quá trình chạy có thể **return String** hoặc **throw IOException** hay lỗi khác theo quy tắc Java. Around advice bao quanh lời gọi có thể cần chuyển tiếp ngoại lệ.

Một số điểm quan trọng:

- Việc method có kiểu trả `String` **không ngăn** nó ném ngoại lệ.
- `return fallbackString` ở around có thể chuyển outcome từ throw sang return nếu API cho phép.
- Nếu advice tự ném một checked exception **không thuộc contract** của interface method, một số cơ chế proxy có thể bọc nó vào loại ngoại lệ không kiểm tra được dự kiến, thay vì truyền thẳng cho caller.
- Reflection `Method.invoke` có thể bọc lỗi target trong `InvocationTargetException`; interceptor cần xử lý lớp bọc này nếu muốn giữ nguyên throwable gốc.
- Nếu advice có `finally` và logic cleanup ném lỗi mới, lỗi cleanup có thể che đi return/throw trước đó tùy cách xử lý.

**Đổi ngoại lệ thành return hợp lệ về kiểu chưa chắc hợp lệ về nghiệp vụ**. Recovery cần phân loại lỗi có thể phục hồi và giữ thông tin quan sát/tracing phù hợp.

## 11. Return generic: type erasure không xóa hợp đồng của caller

Java generics có *type erasure*. Tại runtime, `List<String>` thường được nhìn qua raw type `List`, còn kiểu phần tử `String` được kiểm tra bởi logic/chèn cast ở nơi sử dụng.

Giả sử API khai báo:

```java
// Minh họa, không phải chương trình độc lập.
java.util.List<String> names();
```

Một around trả `List<Integer>` có thể **lọt qua một phép kiểm tra raw `List`**. Nhưng caller vẫn mong các phần tử là String:

```java
// Mã minh họa:
String first = names().get(0);
```

Nếu phần tử đầu thực tế là `Integer`, lỗi cast có thể phát sinh **ở caller khi lấy phần tử**, không nhất thiết ngay tại thời điểm proxy trả list. Đây là **heap pollution/vi phạm hợp đồng generic**, không phải dấu hiệu kết quả hợp lệ.

### 11.1. Generic method và biến kiểu `T`

Với:

```java
// Minh họa một chữ ký generic:
<T> T identity(T input);
```

Sau erasure, phương thức có thể có descriptor dựa trên `Object` (với upper bound phù hợp). Around trả một object bất kỳ có thể qua được ranh giới raw `Object`, nhưng caller sử dụng kết quả ở một kiểu `T` cụ thể có thể gặp `ClassCastException`.

Ví dụ về mặt ý tưởng, caller mong nhận `String` khi truyền `String`. Around trả `Integer` làm sai contract dù runtime handler chỉ thấy return metadata bao quát. Vì vậy cần **bảo toàn mối quan hệ kiểu giữa input và output**, không chỉ kiểm tra raw return type.

### 11.2. Generic bound và wildcard

`List<? extends Number>`, `List<Number>` và `List<Integer>` có các quan hệ gán kiểu khác nhau ở compile time. Một interceptor chỉ thấy raw `List` có thể không bảo vệ toàn bộ thông tin đó. Cần kiểm thử các phép sử dụng tại caller và các method contract, không coi type erasure là giấy phép trả dữ liệu sai loại.

### 11.3. Bridge methods và synthetic methods

Khi generic/covariant override được biên dịch, compiler có thể tạo **bridge methods** để giữ overriding đúng sau erasure. Một cơ chế AOP làm việc ở bytecode có thể thấy bridge method bên cạnh method do lập trình viên viết. Nếu advice được áp dụng không đúng vùng, có thể tạo can thiệp trùng hoặc không khớp như kỳ vọng.

`Method.isBridge()` và `Method.isSynthetic()` là công cụ reflection hữu ích để phân tích. **Không tự kết luận** mọi engine AOP tự gộp hay loại bridge theo cùng quy tắc.

## 12. Covariant return và interface/implementation

Java cho phép một overriding method trả về **subtype** của return type ở lớp cha/giao diện khi quy tắc ngôn ngữ cho phép. Ví dụ:

```java
// Khai báo minh họa, có thể đặt trong các class thích hợp.
class Animal { }
class Dog extends Animal { }

class AnimalFactory {
    Animal create() { return new Animal(); }
}

class DogFactory extends AnimalFactory {
    @Override
    Dog create() { return new Dog(); }
}
```

`DogFactory.create()` khai báo `Dog`, hẹp hơn `Animal` của lớp cha. Một interceptor quan sát phương thức ở góc nhìn lớp cha có thể thấy metadata khác so với interception trực tiếp ở implementation. Nếu advice biến đổi kết quả thành một `Animal` không phải `Dog`, nó có thể hợp với contract **cha** nhưng không hợp với contract **override trả Dog**.

Đây là lý do khi thiết kế quanh phương thức đa hình cần biết:

- Join point là **call** hay **execution**?
- Return metadata phản ánh interface/base method hay implementation method?
- Cơ chế proxy dùng chữ ký method nào khi tạo phương thức chuyển tiếp?
- Có bridge method nào được compiler sinh ra không?
- Caller thấy kiểu compile-time nào, và implementation có ràng buộc hẹp hơn không?

**Không chọn fallback chỉ theo supertype rộng nhất** nếu một đường gọi thực tế đòi kiểu hẹp hơn.

## 13. `Optional<T>` và các kiểu bao kết quả

Một API có thể dùng:

```java
// Minh họa chữ ký:
java.util.Optional<String> find(String key);
```

Một around trả `null` có thể vượt qua kiểm tra Java reference type nhưng phá contract thiết kế vì caller thường mong **một object `Optional`** chứ không phải null. Nếu “không tìm thấy” là trạng thái hợp lệ, kết quả thường phải là `Optional.empty()`; nếu tìm thấy, là `Optional.of(...)` hoặc dạng phù hợp.

Ngay cả khi trả một `Optional` object đúng loại raw, nội dung bên trong phải phù hợp `String`. Một `Optional<Integer>` đưa vào contract `Optional<String>` qua unchecked cast là một vi phạm tiềm ẩn và có thể gây lỗi khi caller lấy dữ liệu.

Tương tự, các kiểu bao như `Result<T>`, `Either<L,R>` hoặc response object tự định nghĩa có **ngữ nghĩa thành công/thất bại** của riêng chúng. Around cần bảo toàn contract của wrapper, không chỉ làm cho cast runtime qua được.

## 14. Bất đồng bộ: method return khác completion của tác vụ

Một method có thể khai báo:

```java
// Minh họa chữ ký:
java.util.concurrent.CompletableFuture<String> fetchAsync(String key);
```

Trong trường hợp này **giá trị trả về ngay lập tức** là `CompletableFuture<String>`, **không phải String**. Around trả `"data"` trực tiếp thay vì future là sai kiểu. Around có thể, nếu engine hỗ trợ:

- Trả nguyên future của target.
- Trả một future thay thế đã hoàn tất theo contract phù hợp.
- Trả future được tạo từ stage biến đổi, ví dụ map String sau khi tác vụ kết thúc.
- Tạo future thất bại/được hủy theo chính sách rõ ràng, nhưng phải giữ đúng ngữ nghĩa API.

### 14.1. Biến đổi đối tượng future khác biến đổi giá trị bên trong

```java
// Minh họa logic kiểu Java, không phải chương trình độc lập.
java.util.concurrent.CompletableFuture<String> original = fetchAsync("K");
java.util.concurrent.CompletableFuture<String> mapped =
        original.thenApply(value -> value.toUpperCase(java.util.Locale.ROOT));
```

Ở đây `mapped` vẫn là `CompletableFuture<String>` phù hợp declared return, còn biến đổi chuỗi thực hiện khi stage hoàn tất thành công. Việc này **khác** với biến đổi giá trị ngay lúc phương thức `fetchAsync` return.

Nếu muốn theo dõi cả outcome thất bại, phải quan tâm `CompletionException`, ngoại lệ được bao, cancellation và callback semantics. Một after-returning advice đối với `fetchAsync` chỉ biết phương thức đã **trả về future**, chưa thể mặc định biết tác vụ tương lai thành công hay thất bại.

### 14.2. Thread/context propagation

Callback xử lý future có thể chạy trên thread khác. Nếu advice dùng context gắn với thread (chẳng hạn trace ID), phải có cơ chế truyền ngữ cảnh phù hợp qua ranh giới callback. **Return type đúng** không chứng minh context đúng hoặc dữ liệu bảo mật được xử lý an toàn.

## 15. Chuỗi nhiều advice: loại kết quả ở ranh giới nào?

Khi nhiều around advice cùng khớp, chúng thường được tổ chức lồng nhau theo precedence:

```text
OuterAround
    |
    InnerAround
        |
        Target
        |
    InnerAround returns valueA
    |
OuterAround returns valueB
    |
Caller sees valueB
```

Một advice bên trong có thể trả kết quả **đúng kiểu**; advice bên ngoài lại biến nó thành object sai kiểu trước khi caller nhận. Ngược lại, inner có thể ném lỗi và outer bắt để trả fallback.

Các câu hỏi thiết kế bắt buộc:

1. Aspect nào là **lớp ngoài cùng**?
2. Advice nào thấy **argument gốc** và advice nào thấy argument đã biến đổi?
3. Advice nào thấy **kết quả đích** và advice nào thấy kết quả đã bọc?
4. Nếu inner thất bại nhưng outer recover, advice after-returning ở **ngoài** có xem kết quả là thành công không?
5. Loại dữ liệu cuối cùng tại **ranh giới caller** có đúng hợp đồng method không?

Không chỉ QA từng advice riêng lẻ. Cần integration test **composition** vì tính tương thích cuối cùng phụ thuộc toàn bộ chuỗi.

### “Nhiều lần proceed” và type

Nếu inner around trả `Integer` cho method `int`, outer quanh nó có thể nhận object đó rồi biến đổi. Nhưng nếu inner trả `String` sai kiểu, tùy kiến trúc, lỗi có thể xuất hiện khi nó được ép về kiểu method hoặc ở một lớp proxy/handler ngoài. **Vị trí phát hiện lỗi phụ thuộc cách engine ghép advice**, không phải cứ tại dòng `return` của advice sai.

## 16. Type compatibility không thay thế semantic compatibility

Một around trả đúng Java type vẫn có thể làm sai contract. Ví dụ:

| API target | Replacement đúng Java type | Vì sao vẫn có thể sai |
| --- | --- | --- |
| `boolean isAuthorized()` | `true` | Bỏ qua kiểm tra quyền thực tế |
| `int inventoryCount()` | `0` | Nhầm dữ liệu lỗi với “hết hàng” |
| `String paymentStatus()` | `"PAID"` | Thông báo đã trả tiền khi giao dịch chưa xong |
| `Optional<User> findUser()` | `Optional.empty()` | Che lỗi backend thành “không tìm thấy” |
| `List<Item> fetchItems()` | Danh sách rỗng | Che lỗi timeout thành dữ liệu hợp lệ |
| `CompletableFuture<Result> runAsync()` | Future đã complete mặc định | Tác vụ thật chưa chạy hoặc còn side effect |

Đó là lý do **fallback, cache, retry, exception mapping** cần một chính sách nghiệp vụ rõ, giới hạn phạm vi và test hồi quy. Không nên dùng around để “làm đẹp kết quả” mà không thảo luận với nơi sở hữu hợp đồng API.

### Non-null và invariant

Một số API có invariant không biểu diễn đầy đủ trong kiểu Java: chuỗi không được rỗng, collection đã được sắp xếp, ID đúng định dạng, trạng thái giao dịch nhất quán. Around không được phá invariant chỉ vì JVM vẫn chấp nhận kiểu object đó.

## 17. Những giới hạn của kỹ thuật weaving/interception

Không phải một advice có quyền giống nhau trong mọi công cụ. Cần phân biệt:

| Cơ chế | Điểm mạnh thông thường | Giới hạn cần kiểm chứng |
| --- | --- | --- |
| **Runtime proxy dựa trên interface** | Có một handler nhận Method và argument, dễ chặn lời gọi qua proxy | Gọi trực tiếp target hoặc tự gọi nội bộ có thể bỏ qua; return contract vẫn phải được proxy kiểm tra |
| **Proxy kiểu subclass** | Có thể bao quanh những method cho phép override/intercept | `final`, `private`, `static` và đường gọi không qua proxy có thể giới hạn |
| **Compile-time weaving** | Chèn advice vào phần mã khi biên dịch | Chỉ tác động artifact được build/weave; quyền đổi return tùy ngôn ngữ AOP |
| **Post-compile weaving** | Biến đổi bytecode đã biên dịch | Tương thích bytecode và việc dùng đúng artifact đã weave |
| **Load-time weaving** | Biến đổi class trong quá trình load | Class loader, agent, thứ tự load và tập class được weave ảnh hưởng coverage |
| **Interceptor tại pipeline/hook** | API rõ ở một ranh giới được thiết kế sẵn | Có thể chỉ hỗ trợ đọc hoặc đổi một số thành phần dữ liệu |

Trong Java, method có modifier `private` hoặc `static` vẫn có return type, nhưng **proxy dựa trên interface** không tự intercept được những lời gọi đó như một instance method trong interface. Constructor có semantic return đặc biệt; không suy từ `return Object` ở interceptor thành quyền tùy ý đổi object được tạo bởi constructor.

### Bỏ qua đường proxy

`Target` có thể được gọi trực tiếp; một method có thể gọi `this.helper()` bên trong target. Nếu chỉ có interceptor ở proxy ngoài, các đường đó có thể không chạy advice dù signature matcher khớp. **Return transformation chỉ tác động đến những lời gọi thật sự đi qua nơi advice được áp dụng.**

Bytecode weaving có thể hỗ trợ thêm các join point nội bộ tùy engine; không phát biểu rằng “mọi self-invocation đều không thể được advice” trong AOP nói chung.

## 18. Method call và method execution: return ở hai phía

Trong một số mô hình AOP có **method call join point** và **method execution join point**, around advice có thể được đặt ở hai ranh giới khác nhau.

- **Call-side:** nằm tại biểu thức gọi, nơi caller yêu cầu thực thi phương thức.
- **Execution-side:** nằm ở ranh giới method body đích thực sự chạy.

Cả hai đều có thể quan sát result/exception khi cơ chế cho phép, nhưng ngữ cảnh và phạm vi weave khác nhau. Một call site qua interface có thể liên quan kiểu compile-time `Base`, còn execution thực tế có thể thuộc override trả kiểu hẹp hơn.

Nếu thao tác bị lỗi khi tính argument ở caller trước khi target bắt đầu, execution advice ở target có thể chưa chạy. Một call-side advice có thể có quy tắc quan sát khác, tùy thời điểm triển khai. **Không thể mặc định mọi loại advice đều nhìn thấy cùng một return/throw outcome trên mọi đường gọi.**

## 19. Reflection, bytecode và thời điểm phát hiện lỗi

Một proxy dùng reflection có thể nhận result dưới dạng `Object`, nhưng khi generated method trả cho caller, bytecode phải chuyển nó về declared return type. Với generic methods, bridge hoặc cast trong caller có thể khiến lỗi phát sinh **sau khi interceptor đã trả về thành công**.

Các điểm quan sát hữu ích khi debug:

- **Method.getReturnType():** return type đã erasure ở cấp `Class<?>`.
- **Method.getGenericReturnType():** metadata `Type` có thể chứa thông tin generic (không phải kiểu phần tử runtime).
- **Method.getDeclaringClass():** class/interface thực sự khai báo Method.
- **Method.isBridge()/isSynthetic():** dùng để nhận diện một số method compiler sinh.
- **InvocationTargetException.getCause():** lấy lỗi target khi reflection bọc.
- **Stack trace/caller test:** chỉ ra nơi lỗi cast/unbox thực sự phát sinh.

**Không sửa lỗi bằng cách bắt `ClassCastException` rồi trả một object bất kỳ.** Cần truy ngược ai đã thay return, method contract nào bị vi phạm và có chặng generic/covariant nào đang đưa ra yêu cầu kiểu hẹp hơn.

## 20. Thiết kế around advice tương thích kiểu

Một quy trình thực tế:

1. **Xác định join point:** phương thức nào, call hay execution, metadata có thể lấy.
2. **Xác định declared return:** reference, primitive, void, generic wrapper hay asynchronous result?
3. **Xác định desired behavior:** quan sát, map kết quả, fallback, cache, retry hay chặn?
4. **Chỉ chọn quyền cần thiết:** nếu chỉ cần quan sát, dùng advice/handler không đổi outcome.
5. **Nếu thay result:** kiểm tra assignability, nullability, wrapper primitive và generic/semantic contract.
6. **Nếu target throw:** xác định giữ lỗi, map lỗi hay recover; đừng che side effect đã xảy ra.
7. **Nếu không proceed:** xác nhận caller được nhận một outcome phù hợp dù target không chạy.
8. **Nếu nhiều aspect:** quy định precedence và kiểm chuỗi tổng hợp.
9. **Nếu async:** phân biệt object future trả về và completion value.
10. **Nếu nhiều đường gọi:** kiểm tra coverage proxy/weaving, self-invocation, reflection và tác vụ chạy ngoài boundary.
11. **Kiểm thử ở caller thật:** xác minh kiểu/kết quả/exception ở nơi sử dụng, không chỉ return của handler.
12. **Đo và theo dõi:** tránh các phép biến đổi gây overhead, log nhạy cảm hoặc kết quả không lường trước.

### Kiểm tra type ở runtime có thể làm gì?

Một interceptor tổng quát có thể thực hiện kiểm tra phòng vệ trước khi trả object:

```java
// Mã Java minh họa, không phải chương trình độc lập.
static boolean compatibleReference(Class<?> returnType, Object result) {
    return !returnType.isPrimitive()
            && (result == null || returnType.isInstance(result));
}
```

Điều kiện này chỉ kiểm tra **reference return ở mức raw Class**. Nó không xử lý primitive/void, không kiểm tra nội dung generic và không kiểm tra business contract. Vì vậy nó chỉ là một phần nhỏ của validation, **không phải bộ chứng minh mọi outcome đều an toàn**.

## 21. Kiểm thử toàn diện cho return compatibility

| Trường hợp | Kỳ vọng cần kiểm tra |
| --- | --- |
| `String` -> `String` khác | Caller nhận đúng chuỗi đã map |
| `String` -> `Integer` | Ranh giới trả kết quả báo lỗi kiểu |
| `String` -> `null` | Có vi phạm non-null contract không? |
| `int` -> `Integer` | Proxy unbox thành công |
| `int` -> `String` | Runtime không nhận wrapper sai |
| `int` -> `null` | Bước unbox không thể dùng null |
| `boolean` -> `Boolean` | Trả primitive đúng |
| `void` -> handler trả object | Xác minh engine xử lý return handler ra sao |
| `List<String>` -> `List<Integer>` | Test cả khi caller truy cập phần tử |
| `Optional<T>` -> `null` | Có vi phạm contract wrapper không? |
| `CompletableFuture<T>` -> `T` | Có trả sai loại object không? |
| `CompletableFuture<T>` -> mapped future | Completion, error và cancellation có đúng không? |
| Covariant override | Replacement có hợp kiểu hẹp nhất caller cần không? |
| Around không proceed | Side effect cần thiết có bị bỏ qua không? |
| Around retry | Có chạy target nhiều lần, dữ liệu có bị lặp không? |
| Target throw | Có giữ Throwable gốc hoặc recovery đúng contract không? |
| Hai around lồng nhau | Kết quả cuối cùng caller nhận là kiểu gì? |
| Gọi trực tiếp target | Có bỏ qua transformation vì không qua proxy không? |
| Async/concurrency | Có mất context hoặc lẫn kết quả mutable giữa tasks không? |

### Ba mức xác minh

- **Unit test advice:** một giá trị ban đầu và một outcome cụ thể có biến đổi như mong muốn không?
- **Integration test weaving/interception:** lời gọi đi qua đúng ranh giới, type cast/unbox, precedence và return cuối có phù hợp không?
- **Contract test phía caller:** caller xử lý kết quả với kiểu khai báo thật, truy cập generic element, nhận exception đúng và nhìn thấy trạng thái nghiệp vụ nhất quán không?

Đặc biệt, unit test chỉ gọi trực tiếp hàm `Object transform(Object)` có thể **không bắt được** `ClassCastException` chỉ xảy ra ở proxy generated method hoặc caller generic cast.

## 22. Những hiểu lầm thường gặp

1. **“Advice khai báo trả Object nên trả gì cũng được.”** Return contract của target/caller vẫn tồn tại.
2. **“Có thể đổi String thành Integer bằng cast.”** Cast kiểm tra kiểu, không chuyển nội dung dữ liệu.
3. **“Return null cho primitive là tương đương 0.”** Không; unboxing null gây lỗi.
4. **“Long có thể thay Integer cho method trả int.”** Wrapper yêu cầu có thể không tương thích.
5. **“Method void có thể gửi một giá trị cho caller từ handler.”** Caller của void không có return value như vậy; một số handler bỏ qua object trả về.
6. **“After-returning luôn sửa được giá trị caller nhận.”** Nhiều API chỉ cho quan sát.
7. **“Đúng Java type là đúng nghiệp vụ.”** Return fallback vẫn phải tuân thủ invariant và side effects.
8. **“Generic List<String> được kiểm tra đầy đủ ở proxy.”** Type erasure có thể trì hoãn lỗi đến lúc caller đọc phần tử.
9. **“Optional không có dữ liệu thì trả null.”** Thường cần object `Optional.empty()` theo contract.
10. **“Future là String kết quả cuối.”** Future object và completion value là hai kiểu/thời điểm.
11. **“Override trả subtype nên fallback kiểu cha luôn được.”** Covariant return có thể đòi kết quả hẹp hơn.
12. **“Một around đúng kiểu đảm bảo chuỗi các around đúng kiểu.”** Advice ngoài cùng vẫn có thể đổi outcome thành sai.
13. **“Có return hợp lệ thì target chắc đã chạy.”** Around có thể không proceed; return không chứng minh side effect.
14. **“Proxy match method thì mọi đường gọi cùng method đều qua advice.”** Direct call/self-invocation có thể bypass.
15. **“Runtime lỗi ngay dòng return sai.”** Lỗi có thể xảy ra khi proxy cast/unbox hoặc caller generic cast.
16. **“Retry hợp lệ chỉ vì lần cuối return đúng kiểu.”** Các lần trước có thể đã tạo side effect trùng.

## 23. Bài tập thực hành

1. Chạy `AroundReturnCompatibilityDemo.java`, đối chiếu thứ tự `around enter`, `target`, `around leave`, `around finally` và dòng `caller`.
2. Sửa around của `label` để trả `StringBuilder` thay `String`. Chạy và giải thích lỗi kiểu tại proxy.
3. Sửa around của `doubleValue` để trả `Long.valueOf(9)`. Vì sao một object `Number` hợp lệ chưa đủ cho `int`?
4. Đổi handler của `doubleValue` để trả `Integer.valueOf(-1)`. Nó có tương thích Java type không, và có phù hợp contract “double” không?
5. Cho `label` trả null. So sánh kiểm tra kiểu Java với giả định “label phải non-null” ở caller.
6. Thêm method `boolean enabled()` và cho interceptor trả `Boolean.TRUE`, `"true"`, và `null`. Dự đoán kết quả.
7. Đổi `notifyEvent` để handler cố ý trả `Integer(1)`. Giải thích vì sao Java dynamic proxy bỏ qua giá trị này nhưng target có thể đã không chạy.
8. Định nghĩa method `List<String> words()`. Thử trả một list chứa `Integer` bằng unchecked cast trong ví dụ thử nghiệm; xác định lỗi phát sinh khi nào ở caller.
9. Định nghĩa `Optional<String> find()`. So sánh `Optional.empty()` với `null` như hai fallback.
10. Cho `fetchAsync` trả `CompletableFuture<String>`; tạo stage mapped bằng `thenApply`, rồi kiểm thử success và exception completion.
11. Tạo hierarchy có covariant return `Animal`/`Dog`; xem kiểu `Method.getReturnType()` ở lời gọi qua interface/base và ở implementation.
12. Đặt hai around lồng nhau: inner map `String` thành `String`, outer cố map thành `Integer`. Vị trí lỗi ở caller nằm ở đâu?
13. Thử bỏ qua `proceed` trong một thao tác có side effect. Xác định một test chứng minh target không được chạy.
14. Viết một bảng quyết định cho các nhóm return `void`, primitive, nullable reference, generic và future, mô tả outcome phù hợp và invalid cases.
15. Viết một contract test dựa vào **caller thực**, gồm return bình thường, failure, null, generic cast và gọi trực tiếp target bypass proxy.

**Tự kiểm tra:** Vì sao handler trả `Object` không hủy return type của phương thức đích? Primitive khác wrapper như thế nào khi advice trả null? Generic erasure khiến lỗi kiểu xuất hiện muộn ra sao? Around ở ngoài cùng có thể thay outcome mà advice bên trong vừa trả không? Return đúng kiểu có chứng minh nghiệp vụ hoàn thành không?

## Kết luận

**Around advice có thể được phép biến đổi kết quả, nhưng không vượt khỏi hợp đồng kiểu và ngữ nghĩa của join point.** Phải bảo toàn khả năng gán kiểu đối với reference, wrapper/unboxing đối với primitive, semantics của `void`, generic contract, covariant return, các kiểu bao kết quả và asynchronous completion. Đồng thời phải xét null, exception, việc có gọi `proceed` hay không, số lần target chạy và precedence của nhiều advice. Kiểm thử đúng là kiểm thử **giá trị hoặc lỗi mà caller thực sự quan sát** qua cơ chế AOP đang dùng, không chỉ việc một hàm advice biên dịch thành công.
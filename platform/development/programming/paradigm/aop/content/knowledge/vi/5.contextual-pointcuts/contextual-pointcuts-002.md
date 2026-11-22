# Chọn pointcut theo kiểu hoặc giá trị tham số khi được hỗ trợ

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), **pointcut** xác định những **join point** (điểm can thiệp) mà một **advice** có thể áp dụng. Ngoài tên phương thức, kiểu khai báo hoặc chữ ký phương thức, một số cơ chế AOP còn cho phép **chọn hoặc ràng buộc điểm can thiệp dựa trên tham số được truyền vào**.

Có hai câu hỏi liên quan nhưng khác bản chất:

1. **Tham số có kiểu gì?** Có thể nói đến **kiểu khai báo** trong chữ ký hoặc **kiểu thực tế** của đối tượng tại thời điểm gọi.
2. **Tham số mang giá trị gì?** Chẳng hạn đối tượng có trạng thái được phép xử lý, chuỗi có tiền tố nhất định hay số tiền vượt một ngưỡng.

Điều kiện về kiểu khai báo thường có thể biết từ metadata của phương thức trước khi lời gọi xảy ra. Điều kiện về **kiểu runtime** và nhất là **giá trị runtime** đòi hỏi quan sát đối số của *từng lượt gọi*. Khả năng biểu đạt trực tiếp các điều kiện đó trong pointcut, cách binding tham số và thời điểm đánh giá là **đặc tính của hệ thống AOP cụ thể**, không phải một khả năng bắt buộc của mọi công cụ.

> **Trọng tâm:** Hiểu khác biệt giữa **declared parameter type**, **runtime argument type** và **argument value**; biết cách thiết kế quy tắc chọn có điều kiện, kiểm thử các đường thực thi và nhận diện giới hạn của AOP động. Những biểu thức minh họa như `argumentType(0) == String` hoặc `value(0).startsWith("VIP-")` bên dưới chỉ là **ký pháp mô tả ý tưởng**, không phải cú pháp AOP phổ quát.

## 1. Bối cảnh: tại sao cần pointcut theo ngữ cảnh tham số?

Giả sử một ứng dụng có phương thức:

```java
void process(Object message)
```

Một cơ chế audit có thể muốn thực hiện các hành vi khác nhau:

- Chỉ ghi thông tin bổ sung khi **đối số thực tế là chuỗi**, dù tham số được khai báo là `Object`.
- Chỉ gắn nhãn ưu tiên khi chuỗi **bắt đầu bằng `VIP-`**.
- Chỉ ghi metric cho yêu cầu có **độ dài dữ liệu vượt ngưỡng**.
- Chỉ kiểm soát số lần gọi khi một thuộc tính của đối tượng cho biết yêu cầu thuộc một nhóm xử lý đặc biệt.

Một pointcut chỉ chọn chữ ký `process(Object)` không phân biệt được các trường hợp ấy. Nhưng việc dùng tham số để quyết định cần được thiết kế cẩn thận: **chọn một join point theo metadata tĩnh** khác với **đánh giá điều kiện động theo từng lượt gọi**.

### Điểm cần phân biệt

```text
Tại thời điểm biết metadata phương thức:
    method = process
    parameterTypes = [Object]
             |
             v
Tại một lượt gọi cụ thể:
    actualArgument = "VIP-72"
    runtimeType = String
    value = "VIP-72"
             |
             v
Quy tắc động:
    runtimeType là String?
    value bắt đầu bằng "VIP-"?
             |
             +-- Có --> chạy advice theo chính sách
             |
             +-- Không --> bỏ qua advice có điều kiện
```

**Một phương thức có thể được gọi nhiều lần với những giá trị khác nhau.** Pointcut động có thể khớp ở lần thứ nhất và không khớp ở lần thứ hai dù chữ ký method, vị trí gọi và target không đổi.

## 2. Ba mức độ thông tin về tham số

| Thông tin | Ví dụ | Biết được lúc nào? | Đặc điểm |
| --- | --- | --- | --- |
| **Kiểu tham số khai báo** | `process(Object)` có `Object.class` | Từ method metadata | Không thay đổi theo mỗi lần gọi |
| **Kiểu đối tượng lúc chạy** | Một lượt nhận `String`, lượt khác nhận `Integer` | Khi có đối số thực tế không null | Có thể thay đổi giữa các lượt gọi |
| **Giá trị thực tế** | `"VIP-72"`, `42`, `null` | Khi đối số được đánh giá và truyền tới join point | Có thể thay đổi từng lượt, và với object mutable còn có thể thay đổi theo thời gian |

**Kiểu khai báo** là một phần của chữ ký phương thức Java. **Kiểu runtime** là loại của object thực sự được tham chiếu; với reference `null` thì không có object để hỏi `getClass()`. **Giá trị** có thể được kiểm tra theo thuộc tính miền nghiệp vụ, nhưng pointcut không nhất thiết có hỗ trợ sẵn cho những biểu thức tùy ý đó.

Ví dụ:

```java
Object first = "VIP-72";
Object second = 42;
Object third = null;
```

Cả ba biến có **kiểu tĩnh `Object`**, nhưng đối tượng của `first` có runtime type `String`, `second` có runtime type `Integer`, và `third` không trỏ tới object. Nếu cả ba được truyền tới `process(Object)` thì **chữ ký phương thức không đổi**.

### Tránh ngộ nhận về “kiểu của tham số”

Câu “chỉ chọn phương thức có tham số String” có thể có hai ý nghĩa khác nhau:

- Chọn **phương thức khai báo** `process(String)`, bất kể giá trị thực tế có nội dung gì.
- Chọn **lượt gọi** `process(Object)` mà giá trị đối số thực tế là instance của `String`.

Hai điều kiện này **không tương đương**. Khi thiết kế AOP, phải ghi rõ đang lọc *method metadata* hay *invocation data*.

## 3. Bộ lọc theo kiểu khai báo: nền tảng tĩnh

Kiểu tham số khai báo cho phép phân biệt overload chính xác.

```java
// Minh họa khai báo, không phải chương trình độc lập.
class MessageHandler {
    void accept(String text) { }
    void accept(Object payload) { }
    void accept(int priority) { }
}
```

Một matcher theo metadata:

```text
methodName = accept
declaredParameterTypes = [String]
```

sẽ chọn `accept(String)` và không chọn `accept(Object)` hoặc `accept(int)`. Bộ lọc này có thể được xác định từ danh sách `Class<?>` phản ánh tham số phương thức.

Nếu một biến được khai báo `Object payload = "hello"`, lời gọi `accept(payload)` trong Java có thể chọn overload `accept(Object)` ở **compile time**; việc giá trị bên trong là `String` **không tự làm Java chọn lại overload `accept(String)` ở runtime**. Dynamic dispatch của method override là một vấn đề riêng; **overload resolution** dựa trên kiểu và biểu thức tại điểm gọi theo quy tắc của Java.

Điểm mấu chốt: **lọc signature không phải lọc runtime value**.

### Primitive và wrapper

`int` trong chữ ký và `Integer` trong runtime metadata không giống nhau. Khi dùng reflection, `int.class` khác `Integer.class`. Lời gọi có thể boxing/unboxing theo quy tắc Java, nhưng matcher dựa vào danh sách kiểu khai báo sẽ không tự coi hai phương thức này là một signature.

### Array và varargs

`String...` được biểu diễn với kiểu tham số array `String[]`. Hai khai báo `process(String[])` và `process(String...)` **không tạo hai overload hợp lệ** trong cùng class; ở reflection cả hai đều có parameter type `String[].class`, còn metadata `isVarArgs()` có thể phân biệt cách khai báo. Khi xét *giá trị runtime*, đối số array là một object kiểu array; mỗi phần tử trong array không tự trở thành một đối số join point riêng biệt.

## 4. Chọn theo kiểu thực tế của đối số

**Runtime type matching** xét loại đối tượng được truyền vào tại một lượt gọi. Ý tưởng này hữu ích khi API được khai báo qua interface, lớp cha hoặc kiểu tổng quát.

```java
// Minh họa ngắn, không có main().
interface Command { }

final class CreateCommand implements Command { }

final class CancelCommand implements Command { }

void dispatch(Command command) {
    // ...
}
```

Nếu cơ chế pointcut hỗ trợ kiểm tra kiểu đối số runtime, ta có thể yêu cầu “áp dụng advice khi `command` thực tế là `CreateCommand`” mà không cần tạo overload riêng cho từng subtype.

**Tuy nhiên, ý nghĩa phép khớp phải được làm rõ:**

- **Exact type:** runtime class chính xác là `CreateCommand`.
- **Subtype/assignability:** runtime object là `CreateCommand` hoặc subtype phù hợp.
- **Interface membership:** object triển khai một interface nào đó.
- **Declared parameter type:** kiểu ghi trong phương thức `dispatch(Command)`, hoàn toàn khác ba điều kiện trên.

Một lựa chọn `instanceof CreateCommand` có ý nghĩa **tương thích kiểu**, không phải “đúng class duy nhất”. Nếu cần exact type, Java có thể kiểm tra `obj != null && obj.getClass() == CreateCommand.class`. Công cụ AOP có thể cung cấp ký pháp riêng, thường với các giới hạn do ngôn ngữ pointcut và cách triển khai.

### Khi nào null khớp?

Với `null`, không thể gọi `getClass()`. Tùy biểu thức được dùng, kiểm tra `instanceof` sẽ trả về `false`. Nhưng **không nên suy rộng rằng mọi DSL AOP đều xử lý null giống một phép `instanceof` Java**; một số ngôn ngữ có binding hoặc match type dựa trên tham số khai báo và quy tắc đặc biệt cho null.

Trong ví dụ tự viết matcher, hãy định nghĩa tường minh:

```java
static boolean isRuntimeString(Object value) {
    return value instanceof String;
}
```

Điều kiện này là `false` với `null`, số nguyên hay một object khác. Nó kiểm tra type **runtime**, không thay đổi signature khai báo.

### Interface, superclass và subclass

Giả sử một tham số khai báo `CharSequence` và lượt gọi truyền `StringBuilder` hoặc `String`. Matcher theo **declared type** chọn cùng một method; matcher theo **runtime type** có thể phân biệt. Nếu dùng `instanceof CharSequence` thì cả hai có thể khớp. Nếu dùng `value.getClass() == String.class` thì chỉ object `String` khớp.

Việc chọn đúng phép toán kiểu quan trọng hơn tên biến hay tên pointcut.

## 5. Chọn theo giá trị tham số

**Value-based condition** sử dụng nội dung/thuộc tính thực của đối số, ví dụ:

```text
arg[0] instanceof String
AND arg[0] startsWith "VIP-"
```

Hoặc:

```text
arg[0] instanceof PaymentRequest
AND arg[0].amount > 100000
```

Đây là **pseudocode**, chưa phải cú pháp pointcut chuẩn. Có công cụ chỉ cho phép **bind argument** vào advice rồi kiểm tra giá trị bên trong advice; có công cụ hỗ trợ predicate/điều kiện tại điểm khớp; có công cụ chỉ cho phép match tĩnh và không cung cấp value matching.

### Phân biệt “pointcut khớp” với “advice tự kiểm tra điều kiện”

Hai cách cài có thể quan sát tương tự nhưng khác trách nhiệm:

1. **Dynamic pointcut:** hệ thống AOP đánh giá predicate theo đối số; chỉ khi điều kiện đúng, advice tương ứng mới được áp dụng.
2. **Pointcut rộng + guard trong advice:** advice được gọi cho nhiều join point, sau đó tự kiểm tra và có thể không thực hiện hành vi bổ sung nếu điều kiện sai.

Ở phương án 2, **advice vẫn được vào**, do đó có thể có overhead hoặc các tác động khác ngay cả khi phần hành vi chính được bỏ qua. Nếu advice là around và đi qua guard, nó vẫn phải tiếp tục lời gọi gốc theo contract; bỏ qua bước chuyển tiếp có thể làm nghiệp vụ không chạy.

### Khi nào chọn theo giá trị?

- Thu thập **metric tùy thuộc nhóm yêu cầu** mà dữ liệu đã đủ ổn định.
- Ghi thêm thông tin **tracing** khi một loại payload đặc biệt xuất hiện.
- Áp dụng giới hạn, bộ lọc hoặc kiểm tra tại ranh giới đã xác định.
- Phân loại thao tác để audit theo một nhãn nghiệp vụ.

Với **quyết định nghiệp vụ cốt lõi** hoặc **bảo mật bắt buộc**, cần đảm bảo quy tắc được thực thi ở ranh giới đáng tin cậy và không tồn tại đường bypass. Một điều kiện AOP chỉ chạy khi lời gọi đi qua proxy không bảo vệ được tất cả các đường gọi nếu đối tượng đích vẫn có thể được gọi trực tiếp.

## 6. Ví dụ Java 17+ độc lập: một method, nhiều giá trị runtime

Ví dụ dưới đây dùng **Java Dynamic Proxy** và `InvocationHandler` để mô phỏng **bộ lọc tĩnh theo chữ ký** kết hợp **kiểu runtime** và **điều kiện giá trị động**. Mỗi điều kiện là một hàm độc lập, vì vậy ta nhìn rõ cái gì được biết từ metadata và cái gì phụ thuộc vào lượt gọi.

**Quan trọng:** Đây là **một ví dụ interception bằng Java SE**, không phải một ngôn ngữ pointcut AOP chung. Dynamic proxy chỉ quan sát những lời gọi đi qua proxy cho các phương thức interface. Với công cụ AOP khác, cách binding tham số và điểm thực thi được hỗ trợ có thể khác.

Lưu tệp `RuntimeArgumentPointcutDemo.java` bằng UTF-8:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;

public class RuntimeArgumentPointcutDemo {
    interface Inbox {
        String accept(Object payload);
        String accept(String payload);
        String check(Object payload);
    }

    static final class InboxImpl implements Inbox {
        @Override
        public String accept(Object payload) {
            return "OBJECT:" + String.valueOf(payload);
        }

        @Override
        public String accept(String payload) {
            return "STRING:" + String.valueOf(payload);
        }

        @Override
        public String check(Object payload) {
            return "CHECK:" + String.valueOf(payload);
        }
    }

    // Điều kiện tĩnh: chỉ chọn overload accept(Object).
    static boolean matchesDeclaredMethod(Method method) {
        return method.getDeclaringClass() == Inbox.class
                && method.getName().equals("accept")
                && Arrays.equals(
                        method.getParameterTypes(),
                        new Class<?>[] { Object.class });
    }

    // Điều kiện động: object thực tế là một String.
    static boolean matchesRuntimeType(Object[] args) {
        return args != null
                && args.length == 1
                && args[0] instanceof String;
    }

    // Điều kiện động theo nội dung String.
    static boolean matchesValue(Object[] args) {
        return ((String) args[0]).startsWith("VIP-");
    }

    static Inbox withAdvice(Inbox target) {
        return (Inbox) Proxy.newProxyInstance(
                Inbox.class.getClassLoader(),
                new Class<?>[] { Inbox.class },
                (proxy, method, args) -> {
                    if (matchesDeclaredMethod(method)
                            && matchesRuntimeType(args)) {
                        System.out.println("[type] String");

                        // Cast an toàn vì matchesRuntimeType() đã đúng.
                        if (matchesValue(args)) {
                            System.out.println("[value] VIP");
                        }
                    }

                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException error) {
                        // Giữ nguyên ngoại lệ được target ném ra.
                        throw error.getCause();
                    }
                });
    }

    public static void main(String[] args) {
        Inbox target = new InboxImpl();
        Inbox proxy = withAdvice(target);

        System.out.println(proxy.accept((Object) "VIP-42"));
        System.out.println(proxy.accept((Object) "NORMAL-1"));
        System.out.println(proxy.accept((Object) 17));
        System.out.println(proxy.accept((Object) null));

        // Java chọn overload accept(String) tại compile time.
        System.out.println(proxy.accept("VIP-99"));

        // Đối số đủ điều kiện về giá trị, nhưng method name khác.
        System.out.println(proxy.check((Object) "VIP-42"));
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac -encoding UTF-8 RuntimeArgumentPointcutDemo.java
java RuntimeArgumentPointcutDemo
```

**Standard output chính xác:**

```text
[type] String
[value] VIP
OBJECT:VIP-42
[type] String
OBJECT:NORMAL-1
OBJECT:17
OBJECT:null
STRING:VIP-99
CHECK:VIP-42
```

### Phân tích từng lượt gọi

| Lời gọi | Overload được chọn | Runtime type của payload | Value condition | Có in advice? |
| --- | --- | --- | --- | --- |
| `accept((Object) "VIP-42")` | `accept(Object)` | `String` | Đúng | `[type]`, `[value]` |
| `accept((Object) "NORMAL-1")` | `accept(Object)` | `String` | Sai | Chỉ `[type]` |
| `accept((Object) 17)` | `accept(Object)` | `Integer` (boxing) | Không xét | Không |
| `accept((Object) null)` | `accept(Object)` | Không có object | Không xét | Không |
| `accept("VIP-99")` | `accept(String)` | `String` | Không xét do method khác | Không |
| `check((Object) "VIP-42")` | `check(Object)` | `String` | Không xét do tên khác | Không |

**Tại sao có cast `(Object)`?** Trong Java, overload resolution dựa trên kiểu biểu thức tại điểm gọi. `accept("VIP-42")` chọn overload `accept(String)`; `accept((Object) "VIP-42")` chọn `accept(Object)`. Dù object runtime đều là `String`, **metadata của method đã chọn khác nhau**. Cast giúp demo cố ý truyền `String` qua overload khai báo `Object`, để minh họa phần kiểm tra type động.

**Tại sao không lỗi với null?** `matchesRuntimeType` dùng `instanceof String` nên với `null` sẽ trả `false`. Vì có toán tử `&&` ngắn mạch, `matchesValue` chỉ chạy khi đối số chắc chắn là `String`. Phương thức target tiếp tục nhận null và `String.valueOf(null)` trả chuỗi `"null"`. Nếu viết guard sai rồi ép kiểu/dereference trước khi kiểm tra null, advice có thể ném lỗi trước khi nghiệp vụ chạy.

**Tại sao đầu ra cho `"VIP-99"` không có advice?** Lời gọi chọn `accept(String)`; `matchesDeclaredMethod` chỉ cho phép `accept(Object)`. Điều kiện type/value của argument không thể làm thay đổi overload đã được Java chọn.

**Tại sao `check("VIP-42")` không có advice?** Bộ lọc tĩnh kiểm tra tên `accept`. Một đối số trùng kiểu/trùng giá trị không đủ để làm khớp pointcut thuộc phương thức khác.

### Điều gì là “pointcut” trong ví dụ?

Cơ chế proxy chỉ gọi một `InvocationHandler` chung. `matchesDeclaredMethod` đại diện điều kiện tĩnh, `matchesRuntimeType` và `matchesValue` đại diện hai lớp điều kiện động. Việc in log trong handler được dùng để dễ nhìn cơ chế chọn. Trong một engine có **dynamic pointcut thực sự**, predicate có thể quyết định có kích hoạt advice hay không; handler demo chỉ làm một mô hình đơn giản.

## 7. Binding argument và vị trí tham số

Một số mô hình AOP cho phép **ràng buộc tham số được chọn** vào biến của advice để tránh đọc thủ công một mảng `Object[]`. Điều quan trọng là xác định:

- **Index:** tham số ở vị trí nào (0, 1, ...).
- **Type:** khai báo là gì và actual argument có phù hợp với kiểu bind không.
- **Nullability:** có cho phép null hay không.
- **Mỗi lần gọi:** giá trị bind của lượt gọi này không được lẫn với lượt khác.
- **Điều kiện khớp:** chỉ match type hay còn match value.

Ví dụ một chính sách áp dụng cho phương thức:

```java
void transfer(String source, String destination, long amount)
```

Nếu muốn kiểm tra ngưỡng `amount`, **đối số ở vị trí thứ ba** (index 2) mới là dữ liệu cần đọc. Nếu nhầm index 0 hoặc 1, advice có thể gặp sai kiểu hoặc kiểm tra nhầm dữ liệu.

**Với method đã được chọn bằng exact signature**, index/type thường có thể được xác định trước. Với wildcard “mọi method có một tham số bất kỳ”, phải kiểm tra số lượng và type trước khi ép kiểu. Một cơ chế binding tốt có thể làm bước này theo contract của DSL, nhưng không có bảo đảm chung rằng mọi hệ thống sẽ tự chuyển đổi kiểu an toàn.

## 8. Type matching, subtype và polymorphism

Khi một method khai báo tham số interface:

```java
interface Event { }

final class CreatedEvent implements Event { }

final class DeletedEvent implements Event { }

void handle(Event event) { }
```

Đây là mã minh họa. `handle(Event)` vẫn là một chữ ký duy nhất, nhưng mỗi lượt gọi có thể truyền loại event khác nhau.

Những matcher có ý nghĩa riêng:

```java
value instanceof CreatedEvent
value instanceof Event
value != null && value.getClass() == CreatedEvent.class
```

- `instanceof CreatedEvent` nhận object của loại đó và subtype tương thích (nếu có).
- `instanceof Event` có thể nhận nhiều implementation khác nhau.
- So class chính xác bằng `getClass() == ...` không nhận subtype và cần kiểm tra null trước.

Nếu loại `CreatedEvent` là `final`, nó không có subclass thông thường; ví dụ vẫn giúp làm rõ ý nghĩa khác nhau của **exact type** và **assignable type**.

### Generics và erasure

Giả sử:

```java
void handle(java.util.List<String> messages)
```

Ở runtime, phần generic `String` thường bị xóa theo **type erasure**. Một object `ArrayList<String>` không có runtime class duy nhất là “ArrayList of String” để kiểm tra bằng `instanceof List<String>`; phép `instanceof` trên generic parameterized type như vậy không hợp lệ trong Java. Runtime có thể kiểm tra `value instanceof java.util.List<?>`, nhưng điều đó **không chứng minh mọi phần tử là String**.

Nếu chính sách phụ thuộc nội dung phần tử, phải kiểm tra dữ liệu theo một contract phù hợp; không sử dụng cast unchecked rồi giả định kiểu generic được JVM kiểm tra đầy đủ. Việc duyệt phần tử chỉ để chọn pointcut cũng có thể tạo overhead, chạm dữ liệu nhạy cảm hoặc gặp collection bị sửa đồng thời.

### Bridge methods và method metadata

Khi generic method được override sau erasure, compiler có thể sinh **bridge method**. Công cụ AOP dựa trên bytecode/reflection có thể thấy nhiều method đại diện cho một ý định nghiệp vụ. Các API `Method.isBridge()` và `Method.isSynthetic()` có thể hỗ trợ phân tích, nhưng việc hệ thống AOP loại/gộp chúng như thế nào không có quy tắc phổ quát. Cần kiểm thử thực tế để tránh advice chạy trùng hoặc thiếu.

## 9. Value predicate cần đặc biệt cẩn thận với trạng thái thay đổi

Các kiểu bất biến như `String` tương đối dễ xử lý. Nhưng nếu đối số là một object mutable, giá trị dùng để xét khớp **có thể thay đổi** trước khi nghiệp vụ sử dụng nó.

Ví dụ:

```java
// Pseudocode minh họa, không phải chương trình Java độc lập.
if (request.amount > threshold) {
    runSpecialAdvice();
}
proceedWithTarget(request);
```

Nếu một thread khác thay đổi `request.amount` giữa lúc advice kiểm tra và lúc target xử lý, hai bên có thể dùng giá trị khác nhau. Đây là vấn đề **time-of-check/time-of-use (TOCTOU)**.

Một số cách thiết kế an toàn hơn:

1. Sử dụng đối tượng yêu cầu bất biến hoặc snapshot bất biến được chia sẻ giữa phần kiểm tra và thực thi.
2. Ràng buộc nghiệp vụ cốt lõi phải được xác nhận tại tầng thực thi đáng tin cậy.
3. Nếu cần tính nguyên tử, dùng chiến lược đồng bộ/giao dịch phù hợp chứ không dựa vào “đã kiểm tra một lần trong aspect”.
4. Tránh predicate đọc các nguồn dữ liệu thay đổi ngoài ý muốn hoặc tạo tác dụng phụ.

**Pointcut theo giá trị chỉ mô tả điều kiện áp dụng tại một thời điểm.** Nó không tự tạo khóa, snapshot hay giao dịch.

## 10. Điểm khác nhau giữa method call và method execution

Một loại pointcut **method call** có thể quan sát thông tin ở vị trí caller khi một lời gọi được phát ra; **method execution** gắn với ranh giới phương thức đích thật sự bắt đầu chạy.

Nếu dùng điều kiện runtime argument, phải biết engine có cho phép truy cập/bind đối số tại loại join point đó không. Thứ tự đánh giá đối số, receiver và thời điểm chạy advice có thể khác nhau theo ngôn ngữ và cơ chế weaving.

Một số tình huống:

- **Đối số ném lỗi khi đang được tính:** thân target có thể chưa được vào; execution advice của target không nhất thiết chạy.
- **Receiver là null:** không có target instance để thực thi phương thức instance; không suy ra có execution join point của target.
- **Reflection/callback:** phương thức đích có thể thực thi từ đường gọi gián tiếp, không có call site `target.method()` tường minh trong source.
- **Proxy:** handler thấy lời gọi qua proxy; lời gọi trực tiếp target hoặc từ bên trong target có thể bypass.
- **Async:** method gửi tác vụ có thể trả về trước khi tác vụ kết thúc; điều kiện tại call không đồng nghĩa với điều kiện lúc task thực sự thực thi.

Không coi pointcut theo tham số là thứ tự “đánh giá trước mọi thứ” bất biến. Hãy tham khảo semantics của công cụ và kiểm thử ngoại lệ ở phía caller lẫn callee.

## 11. Điều kiện động và thứ tự advice

Giả sử có hai concern:

- `TraceAspect` áp dụng lên mọi execution của `handle(Event)`.
- `PriorityAspect` chỉ áp dụng nếu đối số thỏa predicate về loại hoặc giá trị.

Nếu engine cho phép cả hai, có thể tồn tại nhiều chuỗi hành vi khác nhau:

```text
Trace.before
  Priority.before (nếu match)
    Target.handle(...)
  Priority.after
Trace.after
```

hoặc một thứ tự khác, tùy **precedence**. Nếu `Trace` là lớp ngoài, metric của trace có thể bao gồm overhead từ priority advice; nếu đổi thứ tự, phạm vi đo thay đổi.

**Pointcut quyết định nơi advice được áp dụng; precedence quyết định thứ tự khi nhiều advice cùng áp dụng.** Với around advice, việc có thực hiện hành vi gốc hay không phụ thuộc việc gọi tiếp theo contract. Một advice có thể bỏ qua hoặc gọi lại thao tác nếu cơ chế hỗ trợ; quyết định ấy phải được quản lý cẩn thận, nhất là với thao tác tạo tác dụng phụ.

Điều kiện động cũng có thể được đánh giá **nhiều lần** nếu chính sách hoặc cơ chế gọi lại đoạn xử lý. Vì vậy một predicate nên **không tạo side effect**, có kết quả dễ hiểu trong một trạng thái đã xác định và không thực hiện I/O nặng chỉ để xét khớp.

## 12. Hiệu năng của kiểm tra theo kiểu và theo giá trị

Bộ lọc tĩnh theo tên/kiểu/chữ ký có thể được phân tích hoặc tối ưu từ metadata. Điều kiện động theo đối số cần thông tin runtime, vì vậy thường phải đánh giá ở những lượt gọi phù hợp. Không có một tỷ lệ overhead cố định cho mọi cơ chế.

Chi phí có thể đến từ:

- Kiểm tra runtime type, ép kiểu hoặc truy xuất các trường của object.
- Tạo object trung gian, boxing/unboxing, reflection hoặc proxy dispatch.
- Predicate phải parse dữ liệu, duyệt collection hoặc gọi hàm có tính toán lớn.
- Ghi log/metric ngay trong advice, nhất là trên đường gọi tần suất cao.
- Đồng bộ hoặc lấy ngữ cảnh chung khi nhiều luồng chạy song song.

Cách tối ưu đúng là **hạn chế số join point phải xét điều kiện động** bằng pointcut tĩnh đủ hẹp, sau đó kiểm tra type/value trên các lời gọi còn lại. Ví dụ điều kiện:

```text
method = Inbox.accept(Object)
AND runtimeArgument[0] is String
AND runtimeArgument[0] startsWith "VIP-"
```

thường hợp lý hơn việc chạy phép đọc/parse payload VIP trên **mọi method của chương trình**. Nhưng thứ tự tối ưu thật sự và khả năng cache do engine quyết định; không khẳng định engine nào cũng tự áp dụng thứ tự lọc đó.

## 13. Những sai lầm về kiểu và giá trị tham số

### 13.1. Coi overload resolution là dispatch theo runtime value

Trong Java, `accept("VIP")` và `accept((Object) "VIP")` có thể chọn hai overload khác nhau. Việc object runtime là `String` không thay thế quyết định overload compile time. Phải phân biệt **static signature** và **runtime object type**.

### 13.2. Kiểm tra `getClass()` khi giá trị null

`null` không có runtime class. Gọi `value.getClass()` sẽ ném `NullPointerException`. Dùng guard trước khi dereference; ghi rõ ý nghĩa của null trong chính sách thay vì ngầm loại bỏ nếu bài toán cần xử lý null đặc biệt.

### 13.3. Coi kiểu tham số generic là được JVM bảo đảm đầy đủ

`List<String>` và `List<Integer>` có thể cùng runtime raw class. `instanceof List<?>` chỉ xác nhận object là một danh sách, không xác nhận kiểu phần tử. Không dùng cast unchecked như bằng chứng điểm khớp đúng.

### 13.4. Đặt logic nghiệp vụ cốt lõi vào điều kiện AOP mà không kiểm soát đường bypass

Một method có thể được gọi trực tiếp vào target, qua self-invocation hoặc qua một cơ chế không được weave. Nếu điều kiện value trong aspect là lớp bảo vệ duy nhất cho bất biến nghiệp vụ/bảo mật, những đường này có thể bỏ lọt kiểm tra. Điều kiện bắt buộc nên được bảo vệ tại ranh giới có tính toàn diện.

### 13.5. Dùng predicate có side effect

Predicate ghi dữ liệu, gửi thông báo hoặc thay đổi argument trước khi trả boolean có thể khiến lời gọi không còn thuần là “chọn điểm”. Khi quy tắc hoặc advice bị đánh giá lại, tác dụng phụ có thể lặp. Nên giữ predicate là kiểm tra nhẹ và dễ dự đoán.

### 13.6. Không kiểm tra concurrency

Một aspect giữ “argument hiện tại” trong trường mutable của instance dùng chung có thể trộn dữ liệu giữa các thread. Dữ liệu theo lượt gọi nên đi qua biến cục bộ, đối số đã bind hoặc cơ chế context propagation phù hợp. Đặc biệt khi async, không mặc định dữ liệu gắn với thread của caller được chuyển sang task khác.

### 13.7. Ghi toàn bộ argument vào log

Pointcut theo giá trị thường làm người viết advice muốn in trực tiếp payload để debug. Đối số có thể chứa token, mật khẩu, thông tin cá nhân hoặc dữ liệu không cần thiết. Nên tạo field audit/metric có kiểm soát, tránh chuỗi nhãn với cardinality vô hạn, và kiểm tra chính sách bảo mật dữ liệu.

### 13.8. Đánh đồng “advice không in log” với “pointcut không khớp”

Trong cơ chế pointcut rộng + guard, advice có thể **đã chạy** rồi quyết định không in. Nếu chỉ dựa vào stdout để kết luận pointcut có khớp hay không, rất dễ nhầm. Kiểm thử nên phân biệt: matcher/engine có chọn join point, handler có vào, guard có đúng, và hành vi bổ sung có xảy ra.

## 14. Kiểm thử điểm can thiệp có điều kiện

Bộ test tốt cần bao phủ **kiểu khai báo**, **kiểu runtime**, **giá trị** và **đường gọi**.

| Tình huống | Điều cần xác minh |
| --- | --- |
| `accept(Object)` nhận `String` VIP | Bộ lọc tĩnh đúng; type match; value match. |
| `accept(Object)` nhận `String` thường | Type match; value không match. |
| `accept(Object)` nhận `Integer` | Overload đúng; runtime type không match. |
| `accept(Object)` nhận `null` | Không dereference null; semantics đúng contract. |
| `accept(String)` nhận chuỗi VIP | Có phân biệt overload theo chữ ký khai báo. |
| `check(Object)` nhận chuỗi VIP | Tên method khác nên không khớp static filter. |
| Gọi trực tiếp target | Có thể bypass proxy; không khẳng định policy được áp dụng. |
| Object mutable đổi trạng thái | Predicate và target có dùng cùng snapshot/ngữ nghĩa không? |
| Nhiều luồng gọi đồng thời | Không lẫn dữ liệu giữa các invocation. |
| Target ném ngoại lệ | Handler không nuốt lỗi trái contract. |
| Advice cùng khớp | Thứ tự, số lần gọi tiếp và dữ liệu context chính xác. |
| Reflection hoặc method kế thừa | Có bao phủ theo cơ chế weaving thực tế không? |

### Tách ba mức kiểm thử

1. **Unit test matcher**: cho `Method` và argument fixture, kiểm từng predicate tĩnh/động độc lập.
2. **Integration test interception/weaving**: gọi qua cơ chế AOP đang dùng và xác nhận advice có/không chạy đúng ở những đường gọi quan trọng.
3. **Behavioral test**: xác nhận giá trị trả về, lỗi, số lần thực thi target và chính sách dữ liệu vẫn đúng.

Một test khớp thành công không đủ; cần test cả **false positive** (chạy ở điểm không mong muốn) lẫn **false negative** (bỏ lọt điểm cần áp dụng).

## 15. Khi nào nên chọn theo tham số?

**Chọn theo kiểu runtime** khi một contract rộng nhận nhiều subtype nhưng concern chỉ dành cho một nhóm subtype, và engine có khả năng quan sát/bind argument đúng. Chẳng hạn các handler chung nhận interface event, nhưng metric cần tách một loại event quan trọng.

**Chọn theo giá trị** khi hành vi bổ sung thực sự chỉ cần ở một trạng thái/nhóm dữ liệu nhất định, điều kiện ổn định và chi phí kiểm tra hợp lý. Ví dụ đặt nhãn tracing cho yêu cầu ưu tiên, có giới hạn quyền riêng tư và cardinality phù hợp.

**Không nên ép AOP làm mọi thứ** nếu điều kiện là quy tắc miền nghiệp vụ phức tạp quyết định kết quả chính, cần giao dịch/khóa/snapshot hoặc phải luôn được thấy tại call site. Khi đó, một hàm nghiệp vụ tường minh, thành phần policy hoặc validation ở boundary đáng tin cậy thường dễ kiểm soát hơn. AOP có thể tiếp tục dùng cho việc quan sát/audit xuyên suốt quanh logic ấy.

### Checklist thiết kế

- **Join point:** Call, execution hay điểm nào được engine hỗ trợ?
- **Static filter:** Đã thu hẹp bằng type/name/signature đủ chính xác chưa?
- **Runtime type:** Match exact class, subtype hay interface? Xử lý null ra sao?
- **Value:** Điều kiện có thuần, rẻ và có kết quả ổn định theo thời gian không?
- **Binding:** Index tham số, kiểu ép và vùng đời dữ liệu có chính xác không?
- **Semantics:** Advice chỉ quan sát hay có thể thay đổi luồng, kết quả hoặc ngoại lệ?
- **Coverage:** Có đường gọi trực tiếp, nội bộ, reflection hoặc async bỏ qua advice không?
- **Privacy:** Có in hoặc lưu thông tin đối số không cần thiết không?
- **Tests:** Có test cả trường hợp khớp, không khớp, lỗi, null và chạy đồng thời không?

## 16. Bài tập vận dụng

1. Trong `RuntimeArgumentPointcutDemo.java`, đổi điều kiện giá trị từ `startsWith("VIP-")` sang `endsWith("-42")`. Dự đoán chính xác các dòng `[value]` và chạy xác minh.
2. Sửa `matchesDeclaredMethod` để chọn `accept(String)` thay cho `accept(Object)`. Vì sao `accept("VIP-99")` bắt đầu có log, còn `accept((Object) "VIP-42")` thì không?
3. Thêm một overload `accept(Integer)`. Phân biệt `accept(17)` với `accept((Object) 17)` bằng overload resolution và runtime type.
4. Thay `instanceof String` bằng một điều kiện kiểu chính xác dùng `getClass()` và kiểm tra null trước. Trong ví dụ này kết quả có đổi không?
5. Viết một matcher cho `process(Number)` chỉ ghi metric khi runtime object là `Integer` và giá trị dương. Nếu đối số là `Long` cùng giá trị, nên khớp hay không? Nêu contract rõ ràng.
6. Tạo một class yêu cầu có trường `priority` thay đổi được. Giải thích nguy cơ khi priority bị sửa giữa lúc pointcut xét khớp và lúc target xử lý.
7. Bổ sung test gọi trực tiếp target để chứng minh handler proxy không quan sát được đường gọi đó.
8. Tạo một predicate có counter ghi số lần đánh giá, chạy nhiều lượt gọi và giải thích vì sao counter đó không nhất thiết bằng số lần target thực thi trong mọi hệ thống AOP.
9. Xây bảng có đủ ba trục: declared type, runtime type và actual value. Viết tối thiểu hai ca khớp và bốn ca không khớp cho một chính sách ưu tiên cụ thể.
10. Đề xuất cách đo thời gian hoàn tất của tác vụ async nếu một method chỉ trả về `CompletableFuture` ngay sau khi gửi tác vụ; nêu điểm nào cần quan sát thêm ngoài thời điểm call.

**Tự kiểm tra:** Runtime `String` có biến `accept(Object)` thành `accept(String)` không? Với `null`, có thể gọi `getClass()` để match type không? `instanceof List<?>` có chứng minh phần tử đều là `String` không? Vì sao matcher theo giá trị có thể thay đổi kết quả giữa hai lượt gọi cùng phương thức? Nếu target được gọi mà không đi qua proxy, chính sách advice có chắc chắn chạy không?

## Kết luận

Pointcut theo tham số mở rộng khả năng chọn điểm từ metadata **tĩnh** của phương thức sang **ngữ cảnh từng lượt gọi**. Cần phân biệt **kiểu tham số khai báo**, **kiểu đối tượng runtime** và **giá trị thực tế**; xác nhận engine có hỗ trợ binding hoặc điều kiện động phù hợp; xử lý đúng overload, null, generics, mutability và concurrency. Một thiết kế tốt thường **thu hẹp tập join point bằng điều kiện tĩnh trước**, rồi đánh giá điều kiện runtime ở phạm vi cần thiết, đồng thời kiểm thử đường can thiệp thật và giữ các bất biến quan trọng tại ranh giới đáng tin cậy.
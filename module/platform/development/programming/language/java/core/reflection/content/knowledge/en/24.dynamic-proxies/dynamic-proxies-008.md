# Kiểu trả về, unboxing và giới hạn của `null` trong Java Dynamic Proxy

Trong Java Dynamic Proxy, phương thức trên interface có thể khai báo kiểu trả về cụ thể như `int`, `String`, `Integer` hoặc `void`, nhưng `InvocationHandler.invoke(...)` luôn có kiểu trả về **`Object`**. Khi phương thức của proxy được gọi, lớp proxy do JDK tạo ra chịu trách nhiệm chuyển giá trị `Object` đó sang kiểu mà interface đã công bố. **Sai kiểu gây `ClassCastException`; trả về `null` cho primitive gây `NullPointerException`.** Với kiểu tham chiếu, `null` thường hợp lệ; với `void`, giá trị trả về từ handler bị bỏ qua.

Bài này tập trung vào **hợp đồng kiểu trả về tại ranh giới giữa `InvocationHandler` và phương thức proxy**, không nhầm nó với phép gọi `Method.invoke` trên một đối tượng đích bất kỳ.

## 1. Giá trị đi qua proxy như thế nào?

Giả sử interface công bố:

~~~java
interface Counter {
    int getCount();
}
~~~

Phương thức `Counter.getCount()` buộc phía người gọi nhận một `int`, nhưng handler có chữ ký:

~~~java
Object invoke(Object proxy, Method method, Object[] args) throws Throwable;
~~~

Đây là **hai mức kiểu khác nhau**:

~~~text
Người gọi: Counter.getCount() -> int
                |
                v
Phương thức trong lớp proxy do JDK sinh ra
                |
                v
InvocationHandler.invoke(...) -> Object
                |
                v
Proxy kiểm tra/ép kiểu wrapper rồi unbox thành int
                |
                v
Trả int cho người gọi, hoặc ném lỗi khi chuyển đổi
~~~

Về **ý nghĩa**, đoạn chuyển đổi cho `int` gần giống:

~~~java
Object result = handler.invoke(proxy, method, args);
return ((Integer) result).intValue();
~~~

Đây chỉ là **mã giả minh họa**: không thể chèn hai dòng này trực tiếp vào một phương thức thường mà chưa định nghĩa các biến và xử lý ngoại lệ. Bytecode của lớp proxy thực tế do JDK tạo và có thể khác cách trình bày trên.

- Handler trả về `Integer.valueOf(7)`: ép sang `Integer` thành công, `intValue()` tạo ra `7`.
- Handler trả về `null`: phép ép kiểu tham chiếu sang `Integer` vẫn cho `null`, nhưng gọi `intValue()` trên `null` gây `NullPointerException`.
- Handler trả về `Long.valueOf(7)`: ép từ `Long` sang `Integer` không hợp lệ, gây `ClassCastException`.
- Handler trả về giá trị kiểu `int` bằng `return 7;`: trình biên dịch **autobox** thành `Integer` trước khi handler trả `Object`.

**Thời điểm lỗi:** Trong những tình huống trên, handler có thể đã kết thúc bình thường. NPE/CCE phát sinh khi mã của proxy chuyển kết quả sang kiểu interface yêu cầu; một khối `try/catch` chỉ bao quanh phần xử lý bên trong handler sẽ không tự bắt được lỗi xảy ra sau khi handler `return`.

## 2. Hợp đồng kiểu trả về cần nhớ

| Kiểu trả về ở interface | Giá trị handler trả về | Kết quả của lời gọi trên proxy |
|---|---|---|
| `int` | `Integer.valueOf(7)` hoặc `return 7;` | `7`, unbox thành `int` |
| `int` | `null` | `NullPointerException` |
| `int` | `Long.valueOf(7)` | `ClassCastException` |
| `long` | `Long.valueOf(7)` hoặc `return 7L;` | `7L`, unbox thành `long` |
| `long` | `Integer.valueOf(7)` | `ClassCastException`, **không** tự nới rộng `int` thành `long` |
| `boolean` | `Boolean.TRUE` | `true` |
| `boolean` | `null` hoặc wrapper khác `Boolean` | NPE nếu `null`; CCE nếu sai wrapper |
| `Integer` | `null` hoặc một `Integer` | Hợp lệ vì `Integer` là kiểu tham chiếu |
| `String` | `null` hoặc một `String` | Hợp lệ |
| `String` | `Integer.valueOf(7)` | `ClassCastException` |
| `Object` | Bất kỳ đối tượng nào hoặc `null` | Hợp lệ |
| `void` | `null`, `Integer.valueOf(1)`, hay đối tượng khác | Giá trị bị bỏ qua; người gọi không nhận kết quả |

**Với mọi kiểu nguyên thủy (primitive), wrapper phải tương ứng đúng:**

| Primitive | Wrapper cần trả từ handler |
|---|---|
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

Một điểm dễ nhầm: trong Java thông thường, `long value = 7;` được phép nhờ chuyển đổi primitive từ `int` sang `long`. Nhưng nếu **phương thức proxy khai báo `long`**, handler trả về `Integer` thì proxy cần `Long` để unbox. Nó không nhận `Integer` rồi tự suy diễn một phép widening. Tương tự, `Float` không thay cho `Double`.

Đối với kiểu tham chiếu `T`, giá trị khác `null` phải là instance có thể gán cho `T` (kể cả subtype/interface triển khai phù hợp). Thí dụ phương thức trả `CharSequence` có thể nhận `String`, nhưng phương thức trả `String` không thể nhận `StringBuilder`.

## 3. Chạy một ví dụ Java 17+ bao phủ các trường hợp

Lưu chương trình hoàn chỉnh sau thành **`ProxyReturnDemo.java`**. Chương trình tạo các proxy thực sự qua `Proxy.newProxyInstance`, rồi thử cả kết quả hợp lệ và lỗi đã kiểm soát. `check(...)` chỉ in **tên lớp ngoại lệ** để stdout ổn định, không phụ thuộc thông điệp lỗi của từng bản JDK.

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public class ProxyReturnDemo {
    interface Probe {
        int primitive();
        long wider();
        Integer boxed();
        String text();
        void tick();
    }

    static Probe create(InvocationHandler handler) {
        return (Probe) Proxy.newProxyInstance(
                Probe.class.getClassLoader(),
                new Class<?>[]{Probe.class}, handler);
    }

    static void check(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + " -> OK");
        } catch (RuntimeException e) {
            System.out.println(label + " -> " + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Probe normal = create((proxy, method, values) ->
                switch (method.getName()) {
                    case "primitive" -> 7;
                    case "wider" -> 9L;
                    case "boxed", "text" -> null;
                    case "tick" -> 123;
                    default -> throw new UnsupportedOperationException(method.getName());
                });

        System.out.println("int = " + normal.primitive());
        System.out.println("long = " + normal.wider());
        System.out.println("Integer null = " + (normal.boxed() == null));
        System.out.println("String null = " + (normal.text() == null));
        normal.tick();
        System.out.println("void = OK");

        Probe nullResult = create((proxy, method, values) -> null);
        check("int <- null", () -> nullResult.primitive());

        Probe longForInt = create((proxy, method, values) -> 7L);
        check("int <- Long", () -> longForInt.primitive());

        Probe intForLong = create((proxy, method, values) -> 7);
        check("long <- Integer", () -> intForLong.wider());

        Probe intForString = create((proxy, method, values) -> 7);
        check("String <- Integer", () -> intForString.text());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac --release 17 -encoding UTF-8 ProxyReturnDemo.java
java ProxyReturnDemo
~~~

Đầu ra chuẩn (stdout):

~~~text
int = 7
long = 9
Integer null = true
String null = true
void = OK
int <- null -> NullPointerException
int <- Long -> ClassCastException
long <- Integer -> ClassCastException
String <- Integer -> ClassCastException
~~~

Diễn giải những điểm quan trọng:

1. `case "primitive" -> 7` trả `Integer` do autoboxing; `Probe.primitive()` nhận `int` sau unboxing.
2. `case "wider" -> 9L` trả `Long`, đúng wrapper của `long`.
3. `boxed()` và `text()` đều trả `null` thành công vì interface khai báo kiểu tham chiếu.
4. `tick()` khai báo `void`. Handler cố ý trả `123`, nhưng proxy **bỏ giá trị này**, nên gọi `normal.tick()` vẫn thành công.
5. `nullResult.primitive()` phát sinh NPE dù lời gọi handler đã trả `null` bình thường.
6. `longForInt.primitive()` và `intForLong.wider()` đều CCE: wrapper không khớp chính xác; phép chuyển số tự động như mã Java tĩnh không được thực hiện ở ranh giới này.
7. `intForString.text()` gây CCE do giá trị `Integer` không thể gán cho kiểu trả về `String`.

Ví dụ `Probe` không khai báo tham số; với những lời gọi này, `values` mà handler nhận được là `null`. Nếu một method có tham số primitive, phần tử tương ứng trong `args` mà handler nhận được là wrapper, ví dụ đối số `int` được boxing thành `Integer`. **Boxing tham số đầu vào** và **unboxing giá trị đầu ra** là hai quá trình cần phân biệt.

## 4. `null` có thể xuất hiện ở những nơi khác nhau

`null` là giá trị của kiểu tham chiếu; bản thân biến primitive không chứa `null`. Hãy phân biệt ít nhất ba tình huống:

**Tình huống A — interface trả primitive**

~~~java
int count = proxy.primitive();
~~~

Mã ở vị trí gọi là hợp lệ lúc biên dịch vì khai báo của `Probe.primitive()` là `int`. Nếu handler trả `null`, proxy ném NPE **trong quá trình xử lý lời gọi**; người gọi không nhận được một `int` nào.

**Tình huống B — interface trả wrapper**

~~~java
Integer maybeCount = proxy.boxed();  // có thể là null
~~~

Đây là lời gọi hợp lệ. Tuy nhiên, nếu phía người gọi tiếp tục:

~~~java
int count = proxy.boxed();          // tự unbox null -> NPE
~~~

NPE lần này do **mã người gọi unbox một `Integer` bằng `null`**, không phải do proxy vi phạm hợp đồng của `boxed()`. Hai nơi phát sinh có thể thể hiện khác nhau trên stack trace.

**Tình huống C — interface trả `void`**

~~~java
proxy.tick();
~~~

Bên ngoài không có kết quả để lưu; handler vẫn phải hoàn thành phương thức `Object invoke(...)` bằng một giá trị `Object` như `null`. **Thực hành thông thường** là trả `null` cho method `void`, nhằm làm rõ ý nghĩa thay vì trả giá trị bị bỏ đi.

Một phương thức trả `Void` (chữ `V` hoa, là lớp wrapper tham chiếu) **không giống** phương thức trả primitive `void`: `Void` có thể nhận `null` như các reference type. Đừng đồng nhất `Void.class` với `void.class`.

## 5. Thiết kế hợp đồng khi dữ liệu có thể thiếu

Khi không có giá trị, chọn kiểu trả về theo nhu cầu nghiệp vụ trước khi viết handler:

- **Luôn có một số đếm hợp lệ:** interface trả `int`; handler đảm bảo luôn trả `Integer` không `null`. Nếu dữ liệu thiếu là lỗi, ném ngoại lệ có ý nghĩa thay vì trả `null`.
- **Số đếm được phép vắng mặt:** interface trả `Integer` và mô tả rõ nghĩa của `null`; người gọi kiểm tra trước khi unbox.
- **Muốn thể hiện thiếu dữ liệu một cách tường minh:** cân nhắc `OptionalInt` cho số nguyên không có giá trị hoặc `Optional<T>` cho reference type; handler phải trả chính một instance `OptionalInt`/`Optional` tương thích, chẳng hạn `OptionalInt.empty()`, thay vì trả `null` mơ hồ.
- **Thao tác chỉ tạo tác dụng phụ:** interface trả `void` và handler trả `null` sau khi làm xong; không dùng một giá trị bị bỏ qua để báo kết quả.
- **Cần báo thành công/thất bại:** cân nhắc `boolean` với `Boolean.TRUE`/`Boolean.FALSE`, hoặc một kiểu kết quả có cấu trúc nếu cần thông tin lỗi, thay vì dùng `null` cho `boolean`.

`0`, `false` hoặc chuỗi rỗng **không phải** giá trị mặc định do Dynamic Proxy tự tạo khi handler trả `null`. Nếu nghiệp vụ cho phép giá trị dự phòng, **handler phải chủ động quyết định** giá trị đó.

## 6. Phát hiện lỗi sớm trong `InvocationHandler`

Trong hệ thống có nhiều method, trả `null` như một giá trị mặc định cho mọi method chưa xử lý là nguy hiểm: có thể gây NPE ở method trả primitive, làm mất dữ liệu ở method trả reference, và phá các method của `Object`.

Một hướng thiết kế là dựa trên `method.getReturnType()`:

~~~java
Class<?> returnType = method.getReturnType();

if (returnType == void.class) {
    // Thực hiện tác dụng phụ xong rồi return null.
} else if (returnType == int.class) {
    // Trả Integer không null, hoặc ném lỗi nghiệp vụ rõ ràng.
} else if (returnType == Integer.class) {
    // Có thể trả Integer hoặc null nếu hợp đồng cho phép.
}
~~~

Đây là **đoạn minh họa nằm trong handler**, không phải chương trình Java hoàn chỉnh. Với những giao diện lớn, nên định nghĩa hợp đồng trả về và phân phối method rõ ràng hơn là chỉ suy luận hành vi từ kiểu trả về.

Nếu muốn fail-fast, handler có thể kiểm tra kết quả **trước khi return**:

~~~java
static Object requireIntResult(Method method, Object result) {
    if (method.getReturnType() != int.class) {
        throw new IllegalArgumentException("Method must return int");
    }
    if (!(result instanceof Integer)) {
        throw new IllegalStateException("Expected non-null Integer result");
    }
    return result;
}
~~~

Đây là **một phương thức hỗ trợ minh họa**, cần đặt trong một lớp và `import java.lang.reflect.Method;` trước khi dùng. Handler cho method trả `int` có thể gọi `return requireIntResult(method, calculated);`. Cách này biến một lỗi unboxing khó tìm thành ngoại lệ có thông điệp rõ ngay tại nơi dựng kết quả; nó không thay đổi quy tắc chuyển đổi của proxy. Với primitive khác, kiểm tra wrapper tương ứng; với reference type, dùng `returnType.isInstance(result)` cho giá trị không `null`.

Đặc biệt, khi trả về `String`, `List` hoặc kiểu class khác, **runtime chỉ kiểm tra kiểu có thể gán**. Với `List<String>`, generics bị xóa kiểu ở runtime; proxy không tự kiểm tra từng phần tử có phải `String`. Việc lấy phần tử sai kiểu và ép về `String` sau đó vẫn có thể gây CCE ở nơi sử dụng.

## 7. Những bẫy dễ gặp

| Sai lầm | Vì sao sai | Cách xử lý |
|---|---|---|
| `return null;` cho mọi method chưa biết | `int`, `boolean`, `long`... sẽ NPE; `hashCode()` của `Object` cũng trả `int` | Xử lý từng method, hoặc ném `UnsupportedOperationException` khi chưa có hợp đồng |
| Trả `7` cho method trả `long` | `7` autobox thành `Integer`, trong khi proxy cần `Long` | Trả `7L` hoặc `Long.valueOf(7)` |
| Dùng `return null` và mong nhận `0`/`false` | Dynamic Proxy không tự sinh mặc định primitive | Chọn giá trị dự phòng rõ ràng hoặc ném lỗi |
| Nghĩ mọi `null` đều làm proxy lỗi | Reference và `Void`/`Integer` có thể nhận `null` | Kiểm tra loại trả về và hợp đồng nghiệp vụ |
| Nghĩ `void` buộc handler phải trả `null` | Proxy bỏ qua giá trị; nhưng `null` là lựa chọn dễ đọc | Trả `null` vì rõ ý nghĩa, không trông chờ giá trị khác |
| Chỉ bắt lỗi **bên trong** handler | NPE/CCE chuyển kiểu có thể xuất hiện **sau** handler `return` | Kiểm tra kết quả sớm trong handler hoặc xử lý ngoại lệ tại caller |
| Dùng `== Integer.class` để phát hiện `int` | Primitive `int.class` khác wrapper `Integer.class` | So `getReturnType()` với đúng `int.class`/`Integer.class` |
| Bỏ qua `equals`, `hashCode`, `toString` | Các lời gọi này cũng tới handler và có hợp đồng trả về riêng | Xử lý method của `Object` một cách chủ ý |

Với phương thức trùng tên và danh sách tham số từ nhiều interface, Java Dynamic Proxy còn có quy tắc về **tính tương thích của kiểu trả về** khi tạo proxy. Nếu một chữ ký trùng có kiểu trả về primitive hoặc `void`, các interface đó phải khai báo cùng kiểu trả về; với kiểu reference, cần một kiểu có thể gán cho các kiểu trả về còn lại. Đừng suy luận rằng chỉ vì hai method cùng tên mà handler có thể tùy ý trả một kiểu bất kỳ.

## 8. Phân biệt Dynamic Proxy với phản chiếu gọi method

Hai API dễ bị lẫn:

- `InvocationHandler.invoke(proxy, method, args)` được **lớp Dynamic Proxy** gọi. Handler trả `Object` và lớp proxy chuyển kết quả theo chữ ký của interface.
- `Method.invoke(target, args)` là **Reflection API** gọi trực tiếp method trên target, cũng trả `Object`; kết quả primitive được boxing, method trả `void` cho `null`. Nếu method đích ném ngoại lệ, `Method.invoke` thông thường bọc trong `InvocationTargetException`.

Handler có thể dùng `method.invoke(delegate, args)` để ủy quyền cho implementation thật. Khi đó cần xử lý ngoại lệ phản chiếu cho phù hợp, và vẫn phải đảm bảo **giá trị cuối cùng handler trả cho proxy** khớp kiểu mà interface đòi hỏi. Chuyển kiểu của proxy không được bỏ qua chỉ vì handler gọi Reflection nội bộ.

Nếu handler ném một **checked exception** không được khai báo bởi interface method, lời gọi qua proxy thường chuyển thành `UndeclaredThrowableException`. Đây là quy tắc về **ngoại lệ**, khác hoàn toàn với NPE/CCE do **kiểu kết quả**; không nên trộn chúng thành một nguyên nhân.

## 9. Tự kiểm tra kiến thức

1. Với `boolean active()`, handler trả `Boolean.FALSE`, `Integer.valueOf(0)` và `null` thì từng lời gọi cho kết quả/lỗi gì? Vì sao `0` không tự biến thành `false`?
2. Với `Long total()` (wrapper), handler trả `null` có lỗi tại proxy không? Nếu caller viết `long x = proxy.total();`, lỗi phát sinh tại đâu?
3. Vì sao `double avg()` cần `Double` và `return 2.5f;` không phù hợp? Hãy thử thay bằng `return 2.5d;`.
4. Vì sao handler trả một đối tượng với method `void tick()` không làm người gọi nhìn thấy đối tượng đó?
5. Viết quy tắc cho `String name()` chấp nhận `null` nhưng vẫn từ chối đối tượng `Integer`, và cho `int count()` không chấp nhận `null`.
6. Bổ sung method `int hashCode()` vào kịch bản handler xử lý mọi method; nhận xét tác động nếu handler trả `null` khi client gọi `proxy.hashCode()`.

**Ghi nhớ:** kiểu trả về của `InvocationHandler.invoke` luôn là `Object`, nhưng hợp đồng bên ngoài thuộc về **interface method**. Proxy phải ép kiểu và unbox để trả đúng kết quả. `null` hợp lệ cho reference và bị bỏ qua khi method là `void`; `null` cho primitive gây NPE, còn đối tượng không tương thích gây CCE. Hãy quyết định rõ ý nghĩa “không có dữ liệu” ngay trong hợp đồng API và kiểm tra kết quả trước khi đưa ra khỏi handler nếu cần chẩn đoán sớm.

### Tài liệu tham khảo

- [Javadoc Java 17 — `InvocationHandler.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html#invoke(java.lang.Object,java.lang.reflect.Method,java.lang.Object%5B%5D))
- [Javadoc Java 17 — `Proxy`, quy tắc proxy class và các method trùng chữ ký](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html)

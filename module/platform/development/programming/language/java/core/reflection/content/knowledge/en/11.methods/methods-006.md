# Gọi phương thức static bằng receiver `null` qua Java Reflection

## 1. Ý nghĩa của receiver trong `Method.invoke`

Trong Java Reflection, đối tượng `java.lang.reflect.Method` đại diện cho một phương thức và cho phép gọi nó ở runtime bằng API:

```java
Object result = method.invoke(receiver, arg1, arg2);
```

Chữ ký API là:

```java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException
```

Có **hai vai trò khác nhau** trong lệnh gọi:

- `obj` (hay `receiver`): đối tượng mà phương thức **instance** sẽ chạy trên đó.
- `args`: các **tham số thực tế** được truyền vào phương thức, theo đúng thứ tự khai báo.

Với phương thức **`static`**, lệnh gọi không gắn với một instance cụ thể. Theo hợp đồng của `Method.invoke`, tham số `obj` **bị bỏ qua và có thể là `null`**. Vì vậy, cách gọi đúng, rõ ràng nhất là:

```java
Method method = Example.class.getDeclaredMethod("hello");
method.invoke(null); // Gọi Example.hello() nếu method là static và có thể truy cập
```

Ở đây `null` là **receiver**, không phải tham số đầu tiên của `hello()`. Ví dụ trên giả định có lớp `Example` và phương thức `hello()` không tham số.

**Kết luận trực tiếp:** `method.invoke(null, ...)` là cách gọi bình thường cho `static` method; không cần tạo đối tượng bằng `new Example()` trước.

## 2. Vì sao `static` nhận receiver `null` còn instance method thì không?

Xét hai kiểu phương thức:

```java
class Demo {
    static String staticHello() {
        return "static";
    }

    String instanceHello() {
        return "instance";
    }
}
```

Biểu thức Java thông thường:

```java
Demo.staticHello();             // Không cần instance
new Demo().instanceHello();     // Cần instance
```

Tương ứng trong Reflection:

```java
Method staticMethod = Demo.class.getDeclaredMethod("staticHello");
String a = (String) staticMethod.invoke(null);

Method instanceMethod = Demo.class.getDeclaredMethod("instanceHello");
String b = (String) instanceMethod.invoke(new Demo());
// instanceMethod.invoke(null); // Ném NullPointerException
```

Đây là các **đoạn minh họa** đặt trong ngữ cảnh có xử lý checked exceptions, chẳng hạn phương thức `main` khai báo `throws Exception`.

Với instance method, `receiver` phải là instance tương thích với lớp/giao diện khai báo phương thức. Nếu receiver là `null`, `Method.invoke` ném `NullPointerException`; nếu là đối tượng **không đúng kiểu**, nó ném `IllegalArgumentException`.

Với `static` method, runtime không tra cứu đối tượng instance để chạy phương thức. Thậm chí nếu truyền một object khác `null`, Reflection **bỏ qua object ấy**. Ví dụ `staticMethod.invoke(new Object())` vẫn gọi phương thức static, miễn là access và arguments đều hợp lệ. Tuy nhiên, **nên truyền `null`** để thể hiện đúng ý nghĩa: không cần instance.

| Method được phản ánh | Receiver truyền vào | Kết quả về receiver |
| --- | --- | --- |
| `static` | `null` | Hợp lệ; không cần object |
| `static` | Object khác `null`, kể cả không cùng kiểu | Bị bỏ qua |
| Instance | Object đúng kiểu | Có thể gọi; còn tùy access/arguments |
| Instance | `null` | `NullPointerException` |
| Instance | Object không phải instance tương thích | `IllegalArgumentException` |

Bảng chỉ bàn về **receiver**; việc gọi thành công còn cần số lượng/kiểu tham số, quyền truy cập và không có lỗi phát sinh khi thực thi.

## 3. Nhận diện phương thức `static` trước khi gọi

Khi xử lý các `Method` được phát hiện động, hãy dùng:

```java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

boolean isStatic = Modifier.isStatic(method.getModifiers());
```

`Method.getModifiers()` trả về tập modifier của phương thức. `Modifier.isStatic(...)` kiểm tra cờ `static`. Đây là cách rõ ràng để quyết định receiver mà Reflection cần:

```java
Object receiver = Modifier.isStatic(method.getModifiers())
        ? null
        : existingInstance;
Object result = method.invoke(receiver, args);
```

Đây là **mẫu mã**: `method`, `existingInstance` và `args` phải được xác định trước. Với instance method, cần bảo đảm `existingInstance` đúng kiểu. Nếu caller không có instance nhưng phương thức không phải static, không tự suy ra có thể truyền `null`.

### Cách lấy đúng `Method`

- `SomeClass.class.getMethod("name", ParamType.class)` tìm phương thức `public` theo tên và **kiểu tham số**, bao gồm public method được thừa kế theo quy tắc API.
- `SomeClass.class.getDeclaredMethod("name", ParamType.class)` tìm phương thức khai báo **trực tiếp** trong lớp/giao diện đó, kể cả không `public`, nhưng không tìm tự động trên superclass.
- Cả hai trả `Method` và có thể ném `NoSuchMethodException` khi không khớp tên/chữ ký.
- Khi có overload, phải chọn đúng các `Class<?>` của kiểu tham số. `getDeclaredMethod("add", int.class, int.class)` khác `getDeclaredMethod("add", Integer.class, Integer.class)`.

`getDeclaredMethod` không tự cấp quyền gọi một method `private`. Đối với một `static` private method, **receiver `null` vẫn hợp lệ**, nhưng truy cập có thể bị chặn bởi Java access control / JPMS. Dùng `trySetAccessible()` có kiểm soát nếu thực sự cần truy cập sâu.

## 4. Ví dụ Java 17+ hoàn chỉnh

Lưu toàn bộ chương trình vào tệp **`StaticReceiverDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class StaticReceiverDemo {
    public static String greet(String name) {
        return "Hi " + name;
    }

    public static int add(int a, int b) {
        return a + b;
    }

    public static void ping() {
        System.out.println("ping");
    }

    public static String join(String[] values) {
        return String.join("-", values);
    }

    public static void fail() {
        throw new IllegalStateException("failure");
    }

    public String instanceHello() {
        return "instance";
    }

    public static void main(String[] args) throws Exception {
        Class<StaticReceiverDemo> type = StaticReceiverDemo.class;

        Method greet = type.getMethod("greet", String.class);
        System.out.println("null receiver: "
                + greet.invoke(null, "Lan"));
        System.out.println("ignored receiver: "
                + greet.invoke(new Object(), "Minh"));
        System.out.println("is static: "
                + Modifier.isStatic(greet.getModifiers()));

        Method add = type.getMethod("add", int.class, int.class);
        Object sum = add.invoke(null, 3, 4);
        System.out.println("sum: " + sum
                + ", type: " + sum.getClass().getSimpleName());

        Method ping = type.getMethod("ping");
        Object noResult = ping.invoke(null);
        System.out.println("void result is null: "
                + (noResult == null));

        Method join = type.getMethod("join", String[].class);
        System.out.println("join: "
                + join.invoke(null, (Object) new String[] {"red", "blue"}));

        try {
            // Cố tình truyền 2 đối số thay vì 1 đối số String[].
            join.invoke(null, (Object[]) new String[] {"red", "blue"});
        } catch (IllegalArgumentException e) {
            System.out.println("spread array: IllegalArgumentException");
        }

        Method instance = type.getMethod("instanceHello");
        try {
            instance.invoke(null);
        } catch (NullPointerException e) {
            System.out.println("instance null: NullPointerException");
        }

        Method fail = type.getMethod("fail");
        try {
            fail.invoke(null);
        } catch (InvocationTargetException e) {
            System.out.println("target failure: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac StaticReceiverDemo.java
java StaticReceiverDemo
```

**Stdout chính xác:**

```text
null receiver: Hi Lan
ignored receiver: Hi Minh
is static: true
sum: 7, type: Integer
ping
void result is null: true
join: red-blue
spread array: IllegalArgumentException
instance null: NullPointerException
target failure: IllegalStateException
```

**Phân tích chương trình:**

1. `greet.invoke(null, "Lan")` gọi `greet` dù không có `StaticReceiverDemo` instance, vì phương thức có modifier `static`.
2. `greet.invoke(new Object(), "Minh")` cũng thành công: `new Object()` là receiver **bị bỏ qua**. Cách này hợp lệ nhưng gây nhầm lẫn; khi viết code thực tế nên dùng `null`.
3. `Modifier.isStatic(greet.getModifiers())` nhận đúng kiểu phương thức, trả `true`.
4. `add.invoke(null, 3, 4)` truyền hai tham số int (được đưa vào mảng `Object...` và boxing bởi Java). Reflection tự chuyển `Integer` về `int` khi gọi. `Method.invoke` trả về `Object` nên kết quả primitive `int` được **box** lại thành `Integer`.
5. `ping` có kiểu trả về `void`: thân phương thức in `ping`, sau đó `invoke` trả `null`.
6. `join(String[])` nhận **một** tham số là mảng. Phép cast `(Object)` giúp truyền mảng thành một đối số duy nhất của `Method.invoke`.
7. Phép cast `(Object[])` ở nhánh lỗi khiến nội dung mảng được xem thành **hai** đối số của varargs `invoke`; phương thức `join` chỉ nhận **một** tham số nên Reflection ném `IllegalArgumentException`.
8. `instanceHello` không có modifier `static`; gọi với receiver `null` ném `NullPointerException`.
9. Phương thức `fail` chạy thật rồi ném `IllegalStateException`. Reflection bọc lỗi của phương thức đích bằng `InvocationTargetException`; `getCause()` trả nguyên nhân gốc.

## 5. Phân biệt receiver `null` và tham số `null`

`Method.invoke` có hai “tầng” tham số:

```java
method.invoke(obj, args...);
              ^    ^
              |    +-- đối số của phương thức đích
              +------- receiver của lệnh invoke
```

Với phương thức:

```java
public static String describe(String text) {
    return text == null ? "<null>" : text;
}
```

Lấy `Method` rồi gọi:

```java
Method describe = Example.class
        .getMethod("describe", String.class);

Object a = describe.invoke(null, (Object) null);
```

Đây là **đoạn minh họa**, không phải tệp độc lập. `Example` phải có phương thức `describe` như đã khai báo ở trên.

Trong `describe.invoke(null, (Object) null)`:

- `null` thứ nhất là receiver, bị bỏ qua vì `describe` static.
- `(Object) null` thứ hai là **một tham số `String` có giá trị `null`**, nên lệnh gọi hợp lệ.
- Kết quả là chuỗi `"<null>"`.

Điểm đặc biệt của varargs `Object... args`: `describe.invoke(null, (Object[]) null)` có **mảng đối số là `null`**, được xem như **không truyền tham số**. Với `describe` đòi đúng một tham số, điều này gây `IllegalArgumentException` do sai số lượng tham số. Tương tự, `describe.invoke(null, new Object[0])` là lời gọi không có tham số đích, không phải một tham số `null`.

Tránh viết `describe.invoke(null, null)` khi chủ đích là truyền một tham số null; Java có thể xử lý `null` cuối cùng như một varargs array null và trình biên dịch cảnh báo lời gọi không varargs. Hãy viết tường minh `(Object) null` hoặc `new Object[] {null}`.

| Mục đích | Cú pháp rõ ràng |
| --- | --- |
| Static method không tham số | `method.invoke(null)` |
| Static method nhận một tham số String `"a"` | `method.invoke(null, "a")` |
| Static method nhận một tham số có giá trị `null` | `method.invoke(null, (Object) null)` |
| Static method nhận một tham số mảng `String[]` | `method.invoke(null, (Object) new String[] {"a", "b"})` |
| Static method nhận hai tham số `int` | `method.invoke(null, 1, 2)` |

**`null` receiver và `null` parameter là hai quyết định hoàn toàn khác nhau.** Đừng nhầm một lời gọi không có receiver với một phương thức nhận đầu vào null.

## 6. Vì sao tham số mảng dễ gây lỗi?

`Method.invoke` được khai báo nhận `Object... args`; về mặt Java, đây là biến thể của một mảng `Object[]` chứa các tham số thực tế. Điều đó **không đồng nhất** với lời khai báo varargs của **phương thức đích**.

Ví dụ, dù phương thức đích chỉ nhận đúng một `String[]`, khi viết:

```java
Method m = SomeClass.class.getMethod("process", String[].class);
String[] input = {"x", "y"};

m.invoke(null, (Object) input);           // 1 tham số String[]: đúng
m.invoke(null, new Object[] {input});     // 1 tham số String[]: đúng
// m.invoke(null, (Object[]) input);      // 2 tham số String: sai
```

Đây là đoạn minh họa giả định `SomeClass` có public static method `process(String[])`, không phải chương trình độc lập.

- `(Object) input` ngăn mảng `String[]` bị **trải** thành nhiều phần tử của varargs `invoke`.
- `new Object[] {input}` biểu diễn tường minh mảng **chứa một đối số**, và đối số đó mới là mảng `String[]`.
- `(Object[]) input` biến mảng `String[]` thành mảng varargs truyền cho `invoke`, khiến Reflection thấy mỗi phần tử String là **một tham số riêng**.
- Không suy luận từ `m.isVarArgs()` rằng `Method.invoke` sẽ tự động gộp các đối số thành mảng cho phương thức đích. Reflection yêu cầu cung cấp bộ đối số tương thích với số/kiểu tham số hình thức.

Đây là lỗi thuộc **đóng gói `args`**; nó không liên quan đến tính đúng sai của `receiver = null`.

## 7. Điều kiện truy cập vẫn áp dụng cho static method

`null` receiver **không** có nghĩa là bỏ qua Java access control.

Ví dụ:

```java
class Secrets {
    private static String token() {
        return "hidden";
    }
}
```

`Secrets.class.getDeclaredMethod("token")` có thể trả đối tượng `Method`, nhưng một caller từ lớp/package/module **không đủ quyền** có thể gặp `IllegalAccessException` khi gọi `invoke(null)`. Nếu cần deep reflection, dùng:

```java
Method method = Secrets.class.getDeclaredMethod("token");
if (method.trySetAccessible()) {
    Object value = method.invoke(null);
}
```

Đây là đoạn minh họa cần xử lý checked exceptions. Việc `trySetAccessible()` trả `true` phụ thuộc vào caller, quyền trong Java và JPMS; không bảo đảm thành công khi package của named module chưa mở cho caller. `setAccessible(true)` có thể ném `InaccessibleObjectException` nếu module boundary cấm yêu cầu.

Phân biệt ba lớp vấn đề:

1. **Loại phương thức:** `static` cho phép receiver `null`.
2. **Quyền truy cập:** caller có được phép gọi phương thức (hoặc yêu cầu suppress access checks) hay không.
3. **Đối số:** số lượng/kiểu tham số đích có tương thích hay không.

Một lớp phương thức có thể là static và receiver null đúng, nhưng lời gọi vẫn thất bại vì `IllegalAccessException` hoặc `IllegalArgumentException`.

Khi code đặt trong framework, caller thực sự của `trySetAccessible` có thể nằm ở module framework. Cần mở package cho module **đó**, không đoán rằng module chứa ứng dụng khởi chạy luôn là caller Reflection.

## 8. Giá trị trả về, static initialization và phương thức bị ẩn

### 8.1. Kết quả của `invoke` luôn là `Object`

Dù phương thức đích trả về `int`, `boolean`, `double` hay kiểu tham chiếu, `Method.invoke` khai báo trả về `Object`:

- Với primitive, kết quả được **box** thành wrapper tương ứng, ví dụ `int` thành `Integer`.
- Với kiểu tham chiếu, trả về chính giá trị tham chiếu theo hợp đồng.
- Với `void`, trả về `null`.
- Nếu phương thức trả về một mảng primitive như `int[]`, kết quả là **mảng `int[]`**, không được tự động biến thành `Integer[]`.

```java
Method count = Example.class.getMethod("count");
Object result = count.invoke(null);
int value = (Integer) result;
```

Mã minh họa này giả định `Example.count()` là public static method trả về `int`. Nên kiểm tra `getReturnType()` khi xử lý chữ ký động, tránh cast sai kiểu.

### 8.2. Phương thức static có thể kích hoạt khởi tạo lớp

Nếu lớp khai báo phương thức static chưa được khởi tạo, `Method.invoke` sẽ khiến **lớp khai báo được khởi tạo trước khi phương thức static chạy**. Đây là hành vi của Java, không phải hệ quả riêng của tham số `null`.

```java
class LazyInit {
    static {
        System.out.println("initialized");
    }

    public static void ping() {
        System.out.println("called");
    }
}
```

Nếu `LazyInit` chưa từng khởi tạo và một caller có quyền lấy `Method` rồi gọi `invoke(null)`, static initializer chạy trước `ping()`, nên log theo thứ tự `initialized` rồi `called`. Khi kiểm thử, chú ý những thao tác khởi tạo lớp khác đã chạy trước đó có thể làm log `initialized` không lặp lại.

Nếu khởi tạo lớp thất bại, Reflection có thể phát sinh `ExceptionInInitializerError`, khác với `InvocationTargetException` bọc exception do **thân phương thức đích** ném.

### 8.3. Static method không dispatch theo instance

Method static thuộc kiểu khai báo; Java không override static method theo cơ chế polymorphism của instance method. Nếu lớp con khai báo một static method cùng chữ ký, đó là **method hiding**, không phải overriding.

Khi đã có một `Method` đại diện cho static method trong lớp A, việc truyền một instance lớp B vào tham số receiver **không** làm Reflection chuyển sang một static method khác trong B. Receiver vốn bị bỏ qua; `Method` nào được lựa chọn mới quyết định phương thức đích.

Đừng dùng `method.invoke(instance, ...)` với static method rồi suy luận từ kiểu runtime của `instance` về đích gọi.

## 9. Chẩn đoán lời gọi static thất bại

Receiver `null` là hợp lệ cho static method, nhưng lời gọi vẫn cần **đúng Method, đúng quyền truy cập và đúng danh sách đối số**. Khi chẩn đoán, tách ba giai đoạn:

| Giai đoạn | Dấu hiệu | Điều cần kiểm tra |
| --- | --- | --- |
| Tra cứu | `NoSuchMethodException` | Tên, erased parameter types, `getMethod` so với `getDeclaredMethod` |
| Chuẩn bị gọi | `IllegalAccessException`, `IllegalArgumentException` | Quyền truy cập/JPMS, số lượng và kiểu `args`; `null` receiver không giải quyết các lỗi này |
| Thực thi | `InvocationTargetException` | `getCause()` để đọc lỗi do thân static method ném |
| Khởi tạo lớp | `ExceptionInInitializerError` | Lỗi trong quá trình khởi tạo declaring class trước lần gọi static |

Nếu `setAccessible(true)` bị `InaccessibleObjectException`, xem xét quyền mở package; không coi receiver `null` là cách vượt kiểm tra truy cập. Trước khi gọi trong code framework, dùng `Modifier.isStatic(method.getModifiers())` để xác nhận thực sự là static.

## 10. Mẫu hàm gọi động an toàn hơn

Nếu công cụ của bạn chỉ cần hỗ trợ **static methods**, có thể kiểm tra tường minh để phát hiện sai hợp đồng sớm:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Objects;

public final class StaticCaller {
    private StaticCaller() {
    }

    public static Object invokeStatic(Method method, Object... arguments)
            throws IllegalAccessException, InvocationTargetException {
        Objects.requireNonNull(method, "method");
        if (!Modifier.isStatic(method.getModifiers())) {
            throw new IllegalArgumentException("Method is not static: "
                    + method.getName());
        }
        return method.invoke(null, arguments);
    }
}
```

Đây là **lớp tiện ích có thể biên dịch độc lập**, lưu dưới tên `StaticCaller.java`; nó không tự tìm phương thức, không tự thay đổi quyền truy cập và không nuốt exception từ phương thức đích. Caller cần truyền `Method` hợp lệ và, nếu `arguments` chứa một mảng làm đối số đơn, phải đóng gói mảng đúng cách.

Khi gọi utility:

```java
Method add = Math.class.getMethod("addExact", int.class, int.class);
Object answer = StaticCaller.invokeStatic(add, 20, 22);
System.out.println(answer); // 42
```

Ví dụ sử dụng này cần import `java.lang.reflect.Method` và xử lý checked exceptions (chẳng hạn đặt trong `main` có `throws Exception`), cùng class `StaticCaller` ở trên. `Math.addExact(int,int)` là public static method; từ đoạn gọi có thể kiểm tra không cần tạo `Math` instance.

Nếu sử dụng Reflection lặp lại ở đường chạy hiệu năng cao, có thể cân nhắc cơ chế gọi được kiểm soát khác như `MethodHandle`. Dù dùng cơ chế nào, phải tôn trọng kiểm tra access và chữ ký; không cần tạo instance chỉ để gọi static method.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `Method m` trỏ tới `public static int add(int a, int b)`. Lệnh `m.invoke(null, 2, 3)` có hợp lệ không, và kiểu kết quả ở phía Reflection là gì?

**Đáp án:** Hợp lệ nếu access và các điều kiện chạy khác đáp ứng; trả về `Object` chứa một `Integer` giá trị `5`.

**Câu 2.** Vì sao `m.invoke(null)` với một instance method không tham số thất bại?

**Đáp án:** `null` được dùng làm receiver của instance method; Reflection ném `NullPointerException`. “Không tham số” không có nghĩa “không cần instance”.

**Câu 3.** Với `public static void process(String[] items)`, hai dòng có tương đương không?

```java
m.invoke(null, (Object) new String[] {"x", "y"});
m.invoke(null, (Object[]) new String[] {"x", "y"});
```

**Đáp án:** Không. Dòng đầu truyền **một tham số mảng**; dòng sau truyền **hai tham số `String`** vào varargs của `invoke` và không khớp phương thức chỉ có một tham số.

**Câu 4.** `private static` method có thể luôn chạy với `invoke(null)` không?

**Đáp án:** `null` receiver là đúng về mặt static, nhưng không bảo đảm **quyền truy cập**. Phương thức có thể bị từ chối khi caller không được phép truy cập hay chưa có quyền deep reflection.

**Câu 5.** Với `Method` đại diện cho static method trong lớp cha, truyền instance lớp con vào `invoke` có gọi static method bị ẩn trong lớp con không?

**Đáp án:** Không. Receiver bị bỏ qua; mục tiêu gọi là static method mà `Method` đã đại diện.

**Câu 6.** Khi thân static method ném `IllegalStateException`, caller thường thấy gì?

**Đáp án:** `Method.invoke` ném `InvocationTargetException`, và `getCause()` chứa `IllegalStateException` của phương thức đích.

## 12. Ghi nhớ

`Method.invoke(Object receiver, Object... args)` diễn giải tham số đầu tiên theo **loại phương thức**: static method **bỏ qua receiver**, vì vậy nên dùng `null`; instance method cần một object tương thích. `null` receiver không phải tham số null của method đích. Phân biệt **receiver**, **mảng varargs `args`**, **access control**, **khởi tạo lớp** và **exception của phương thức đích** để chẩn đoán lỗi chính xác.

Tài liệu chuẩn: [Java SE 21 — java.lang.reflect.Method, invoke](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html) và [Java SE 21 — java.lang.reflect.Modifier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Modifier.html).

# Phương thức abstract, default và phương thức interface trong Java Reflection

Trong Java Reflection, một đối tượng `java.lang.reflect.Method` mô tả phương thức được khai báo ở **class hoặc interface**. Không phải mọi `Method` đều có thân mã để chạy trực tiếp: phương thức `abstract` đặt ra hợp đồng, phương thức `default` trong interface cung cấp phần cài đặt mặc định, phương thức `static` thuộc về interface, còn phương thức `private` của interface chỉ phục vụ logic nội bộ. Cách Reflection **phát hiện** một phương thức và cách `Method.invoke(...)` **thực thi** nó là hai vấn đề cần tách bạch.

Bài này hướng dẫn xác định loại phương thức bằng `Modifier.isAbstract(...)`, `Method.isDefault()` và `Modifier.isStatic(...)`; phân biệt phạm vi `getDeclaredMethod(s)` và `getMethod(s)`; thực thi phương thức interface bằng Reflection; hiểu kế thừa, override, xung đột default method; và tránh nhầm *default method* với *default value* của annotation.

## 1. Nhận diện đúng các loại phương thức

Ví dụ một interface khai báo bốn loại method:

~~~java
interface Named {
    String name(); // public abstract ngầm định

    default String greeting() {
        return decorate("Hi " + name());
    }

    static String source() {
        return "interface-static";
    }

    private String decorate(String text) {
        return "[" + text + "]";
    }
}
~~~

Đây là **đoạn minh họa**, chưa phải chương trình độc lập. Java 8 giới thiệu `default` và `static` method trong interface; từ Java 9, interface có thể có `private` method (instance hoặc static) để chia sẻ logic nội bộ. Interface method `private` có thân mã, nhưng không phải default method và không được kế thừa như API public.

| Khai báo trên interface | Có thân mã? | Modifier/phương thức Reflection cần quan sát | `Method.isDefault()` |
| --- | --- | --- | --- |
| `String name();` | Không | `Modifier.isAbstract(method.getModifiers()) == true` | `false` |
| `default String greeting() {...}` | Có | Public, không abstract, không static; `method.isDefault() == true` | `true` |
| `static String source() {...}` | Có | `Modifier.isStatic(...) == true` | `false` |
| `private String decorate(...) {...}` | Có | `Modifier.isPrivate(...) == true` | `false` |

Một method ở class thường có thân mã cũng **không** trở thành default method. `isDefault()` dành cho **public instance method có phần cài đặt và được khai báo trong interface**, không chỉ mang nghĩa chung là "có code". Không có `Modifier.isDefault(...)`; hãy gọi `Method.isDefault()`.

### `Method` nào mang thông tin gì?

`Method` cho phép đọc:

- `getName()`: tên phương thức.
- `getDeclaringClass()`: class/interface **thực sự khai báo** method.
- `getModifiers()`: cờ như `public`, `private`, `abstract`, `static`, `final`. Kiểm tra bằng `java.lang.reflect.Modifier`.
- `isDefault()`: phân biệt chính xác default method của interface.
- `getParameterTypes()`, `getReturnType()`: chữ ký runtime; các phiên bản `getGenericParameterTypes()` và `getGenericReturnType()` phục vụ metadata generic.
- `isBridge()`, `isSynthetic()`: nhận biết một số method do compiler sinh ra, rất hữu ích khi quét toàn bộ danh sách.
- `invoke(receiver, args...)`: thực thi khi có receiver, đối số và quyền truy cập phù hợp.

`getDeclaringClass().isInterface()` giúp biết method **được khai báo trên interface**, nhưng **không đủ** kết luận nó là abstract hay default. Interface vẫn có static/private method.

## 2. Phương thức abstract: nhận biết bằng `Modifier.isAbstract`

Một interface có thể khai báo abstract instance method:

~~~java
interface Shape {
    double area(); // public abstract
}
~~~

Với `Method m = Shape.class.getDeclaredMethod("area")`:

~~~java
boolean abstractMethod = Modifier.isAbstract(m.getModifiers());
boolean defaultMethod = m.isDefault();
~~~

Hai kết quả lần lượt là `true` và `false`. Đây là các đoạn minh họa; cần import `java.lang.reflect.Method` và `java.lang.reflect.Modifier` khi đặt trong chương trình độc lập.

Lớp `abstract` cũng có thể khai báo abstract method, ví dụ `abstract class Base { abstract void work(); }`. `Modifier.isAbstract` vẫn là API đúng để nhận biết; `isDefault()` tiếp tục trả `false` vì đây không phải interface default method.

**Quan trọng:** một `Method` phản chiếu abstract method **vẫn có thể được gọi** bằng `Method.invoke(...)` nếu receiver là đối tượng thuộc lớp triển khai cụ thể và quá trình dispatch tìm được implementation. `Method.invoke` trên instance method sử dụng cơ chế tra cứu động dựa trên **kiểu runtime của receiver**. Nó không có nghĩa JVM sẽ cố chạy thân mã của một phương thức abstract vốn không tồn tại.

Ví dụ nếu `Named` khai báo `String name()` và `BasicNamed` triển khai `name()` trả `"An"`, lời gọi sau sẽ trả `"An"`:

~~~java
Method method = Named.class.getDeclaredMethod("name");
Object result = method.invoke(new BasicNamed());
~~~

Đoạn trên giả sử `Named`, `BasicNamed` đã có khai báo như ví dụ đầy đủ ở phần tiếp theo. Receiver phải tương thích với interface khai báo method; nếu truyền đối tượng không phù hợp, `invoke` ném `IllegalArgumentException`.

## 3. Default method: phát hiện bằng `Method.isDefault()`

Từ Java 8, interface được phép khai báo instance method có thân mã bằng từ khóa `default`:

~~~java
interface Loggable {
    default String label() {
        return "item";
    }
}
~~~

`Loggable.class.getDeclaredMethod("label").isDefault()` là `true`. Phương thức này là `public`, không `abstract` và không `static`. Class triển khai có thể **kế thừa default implementation**, hoặc **override** nó bằng một method riêng.

Một override viết trong class triển khai là **class method**, nên `isDefault()` trên đối tượng `Method` phản chiếu override đó là `false` dù nó thay thế hành vi của một default method ở interface.

Vì vậy, cần phân biệt:

1. **Nơi method được khai báo:** `method.getDeclaringClass()`.
2. **Nó là default method thật sự không:** `method.isDefault()`.
3. **Lời gọi thực tế chạy implementation nào:** phụ thuộc receiver và dynamic dispatch của `Method.invoke(...)`.

`isDefault()` mô tả **Method object**, không trả lời câu hỏi "đối tượng này có đang sử dụng default implementation hay đã override chưa" chỉ bằng một boolean.

## 4. Ví dụ đầy đủ Java 17+: abstract, default, static và private interface method

Tạo tệp **`InterfaceMethodReflectionDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

interface Named {
    String name();

    default String greeting() {
        return decorate("Hi " + name());
    }

    private String decorate(String text) {
        return "[" + text + "]";
    }

    static String source() {
        return "interface-static";
    }
}

class BasicNamed implements Named {
    @Override
    public String name() {
        return "An";
    }
}

class CustomNamed implements Named {
    @Override
    public String name() {
        return "Binh";
    }

    @Override
    public String greeting() {
        return "overridden";
    }
}

public class InterfaceMethodReflectionDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> iface = Named.class;

        Method requirement = iface.getDeclaredMethod("name");
        Method fallback = iface.getDeclaredMethod("greeting");
        Method staticMethod = iface.getDeclaredMethod("source");
        Method helper = iface.getDeclaredMethod("decorate", String.class);

        System.out.println("abstract = "
                + Modifier.isAbstract(requirement.getModifiers())
                + ", default = " + requirement.isDefault());
        System.out.println("default = "
                + fallback.isDefault()
                + ", abstract = " + Modifier.isAbstract(fallback.getModifiers()));
        System.out.println("static = "
                + Modifier.isStatic(staticMethod.getModifiers())
                + ", default = " + staticMethod.isDefault());
        System.out.println("private = "
                + Modifier.isPrivate(helper.getModifiers())
                + ", default = " + helper.isDefault());

        System.out.println("inherited declaring type = "
                + BasicNamed.class.getMethod("greeting")
                        .getDeclaringClass().getSimpleName());

        try {
            BasicNamed.class.getDeclaredMethod("greeting");
        } catch (NoSuchMethodException expected) {
            System.out.println("basic declared default = missing");
        }

        System.out.println("default invoke = "
                + fallback.invoke(new BasicNamed()));
        System.out.println("overridden invoke = "
                + fallback.invoke(new CustomNamed()));
        System.out.println("abstract invoke = "
                + requirement.invoke(new BasicNamed()));
        System.out.println("static invoke = " + staticMethod.invoke(null));

        BasicNamed target = new BasicNamed();
        System.out.println("private accessible before = "
                + helper.canAccess(target));
        System.out.println("private open = " + helper.trySetAccessible());
        System.out.println("private invoke = "
                + helper.invoke(target, "OK"));
    }
}
~~~

Chạy bằng Java 17+:

~~~bash
javac --release 17 InterfaceMethodReflectionDemo.java
java InterfaceMethodReflectionDemo
~~~

**Stdout:**

~~~text
abstract = true, default = false
default = true, abstract = false
static = true, default = false
private = true, default = false
inherited declaring type = Named
basic declared default = missing
default invoke = [Hi An]
overridden invoke = overridden
abstract invoke = An
static invoke = interface-static
private accessible before = false
private open = true
private invoke = [OK]
~~~

### Phân tích từng phần

- `name()` là `public abstract` ngầm định của interface. `Modifier.isAbstract(...)` trả `true`; `isDefault()` trả `false`.
- `greeting()` là `default` nên `isDefault()` trả `true`. Nó gọi `decorate(...)` là private helper nội bộ của interface.
- `source()` là `static`. Có thân mã nhưng không phải default; gọi Reflection bằng receiver `null`.
- `decorate(String)` là `private` instance method của interface. Nó có thân mã, nhưng không public và không default.
- `BasicNamed.class.getMethod("greeting")` tìm được public method kế thừa từ interface `Named`; `getDeclaringClass()` là `Named.class`.
- `BasicNamed.class.getDeclaredMethod("greeting")` ném `NoSuchMethodException` vì `BasicNamed` không **tự khai báo** method này.
- `fallback.invoke(new BasicNamed())` chạy default implementation, kết hợp tên `An` thành `[Hi An]`.
- `fallback.invoke(new CustomNamed())` chạy **override** của `CustomNamed` và trả `overridden` dù biến `fallback` vẫn biểu diễn method gốc của interface. Đây là minh chứng cho dynamic dispatch.
- `requirement.invoke(new BasicNamed())` gọi implementation của abstract interface method và trả `An`.
- `helper.trySetAccessible()` thành công trong ví dụ vì các lớp chạy trong unnamed module cùng class loader. Quyền deep reflection có thể khác khi thư viện Reflection chạy ở module khác.

**Đừng hiểu nhầm:** `getDeclaredMethod(...)` có thể tìm private interface method, nhưng tìm thấy metadata không đồng nghĩa gọi được ngay. `Method.invoke(...)` còn xét quyền truy cập; nếu `trySetAccessible()` trả `false` ở môi trường khác thì không được giả định việc gọi tiếp sẽ thành công.

## 5. `getMethod(s)` và `getDeclaredMethod(s)`: tên giống nhưng phạm vi khác

| API trên `Class<?>` | Phạm vi tìm | Với `BasicNamed.class` và `Named#greeting` |
| --- | --- | --- |
| `getDeclaredMethod(name, types...)` | Method **được khai báo trực tiếp** trên class/interface đó, bất kể mức truy cập | Không tìm thấy `greeting()` vì `BasicNamed` không khai báo |
| `getMethod(name, types...)` | Method **public** khả dụng trên class/interface, gồm method public được kế thừa | Có thể tìm `greeting()` với declaring class `Named` |
| `getDeclaredMethods()` | Mảng method được khai báo trực tiếp, kể cả private, static, default, abstract | Không chứa default method chỉ được kế thừa |
| `getMethods()` | Mảng public methods của kiểu, gồm public methods kế thừa | Có thể chứa interface default/abstract methods khả dụng |

Không được giả định thứ tự mảng `getMethods()` hoặc `getDeclaredMethods()` là thứ tự trong file mã nguồn. Phần mềm quét metadata nên lọc theo tên, kiểu tham số, declaring class, modifier, `isBridge()` hoặc `isSynthetic()` khi cần.

### Method `static` ở interface **không được kế thừa**

`Named.source()` là lời gọi hợp lệ theo tên interface, nhưng `BasicNamed.source()` không hợp lệ trong Java source. Với Reflection, nên tra `Named.class.getDeclaredMethod("source")` hoặc `Named.class.getMethod("source")`. Không mong đợi `BasicNamed.class.getMethod("source")` tìm thấy vì static method của interface không được kế thừa bởi class triển khai.

Ngược lại, một default method `public` có thể được kế thừa, nên `BasicNamed.class.getMethod("greeting")` là trường hợp hợp lệ.

### Khi xem nhiều superinterface

Một interface con có thể kế thừa method của interface cha; `getDeclaredMethods()` trên interface con vẫn chỉ cho thấy method nó **khai báo trực tiếp**. `getMethods()` giúp quan sát public method được kế thừa và độ ưu tiên của các phương thức có cùng chữ ký theo quy tắc API. Nếu cần biết **nguồn gốc**, dùng `method.getDeclaringClass()` thay vì suy luận từ `Class<?>` mà bạn gọi `getMethod` trên đó.

## 6. Khác biệt giữa loại `Method` và hành vi `invoke(...)`

`Method.invoke(Object receiver, Object... args)` có hai tình huống chính:

1. Với **instance method** (abstract, default hoặc implementation trong class), truyền một receiver tương thích. JVM thực hiện **dynamic method lookup** trên kiểu runtime của receiver; một override có thể được chọn.
2. Với **static method**, không có receiver instance; dùng `null`. Lời gọi đi tới static method được phản chiếu, không có cơ chế override của instance method.

Điều này dẫn tới điểm dễ sai:

~~~java
Method m = Named.class.getDeclaredMethod("greeting");
System.out.println(m.isDefault()); // true: method khai báo tại Named
System.out.println(m.invoke(new CustomNamed())); // overridden
~~~

`m.isDefault()` vẫn là `true` vì nó mô tả `Named#greeting`; nhưng lời gọi qua `CustomNamed` chạy override của `CustomNamed`. Đừng dùng `Method.invoke` trên default method của interface để cố ép JVM bỏ qua override.

Nếu bạn thực sự cần gọi **chính phần thân default implementation** của interface như biểu thức `SomeInterface.super.m()`, đó là bài toán *special invocation*. Nó khác cơ chế dispatch thông thường của `Method.invoke` và thường được thực hiện bằng API `java.lang.invoke.MethodHandles` với quyền `Lookup` phù hợp. Đừng xử lý bằng cách đổi tên method hoặc gọi `setAccessible(true)` với hy vọng vô hiệu hóa override.

### Khi gọi method abstract

Một `Method` đại diện abstract declaration vẫn có thể được dùng với receiver có implementation cụ thể:

~~~java
Method abstractMethod = Named.class.getDeclaredMethod("name");
Object result = abstractMethod.invoke(new BasicNamed()); // "An"
~~~

Nhưng không thể tạo instance trực tiếp của interface hoặc abstract class chỉ để gọi method. Nếu bytecode/runtime không tìm được implementation hợp lệ, việc thực thi có thể gặp lỗi liên kết/phân giải phương thức; chương trình Java biên dịch nhất quán thông thường đảm bảo implementation thích hợp.

### Khi gọi private interface method

Private interface method được định nghĩa để giúp các method **bên trong interface** chia sẻ logic, không tạo API public. `getDeclaredMethod` vẫn có thể phản chiếu nó. Gọi qua `invoke` từ code bên ngoài interface có thể đòi hỏi `trySetAccessible()`, và Java module/package openness có thể giới hạn việc bật quyền. Trong chương trình bình thường, nên gọi public/default API của interface thay vì dựa vào private helper.

## 7. Khi có nhiều default method cùng chữ ký

Java có cơ chế phát hiện xung đột nếu hai interface cung cấp default implementation cùng chữ ký mà class không có cách kế thừa không mơ hồ. Ví dụ một class triển khai `Left` và `Right`, cả hai có `default String choose()`, thì class phải giải quyết xung đột, thường bằng một override.

Tạo tệp **`DefaultConflictDemo.java`**:

~~~java
import java.lang.reflect.Method;

interface Left {
    default String choose() {
        return "L";
    }
}

interface Right {
    default String choose() {
        return "R";
    }
}

class Choice implements Left, Right {
    @Override
    public String choose() {
        return Left.super.choose() + "+" + Right.super.choose();
    }
}

public class DefaultConflictDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Method leftMethod = Left.class.getDeclaredMethod("choose");
        Method implementation = Choice.class.getDeclaredMethod("choose");

        System.out.println("Interface method default: "
                + leftMethod.isDefault());
        System.out.println("Class override default: "
                + implementation.isDefault());
        System.out.println("Interface Method.invoke: "
                + leftMethod.invoke(new Choice()));
    }
}
~~~

~~~bash
javac --release 17 DefaultConflictDemo.java
java DefaultConflictDemo
~~~

**Stdout:**

~~~text
Interface method default: true
Class override default: false
Interface Method.invoke: L+R
~~~

Ở đây `Left.super.choose()` và `Right.super.choose()` là lời gọi **đặc biệt viết trực tiếp trong mã nguồn của `Choice`**. Trái lại, `leftMethod.invoke(new Choice())` không ép chạy riêng thân `Left#choose`: nó thực hiện dynamic dispatch tới `Choice#choose` và nhận `L+R`.

Nếu bỏ override trong `Choice`, chương trình nguồn sẽ không biên dịch vì xung đột default method. Reflection không thể "chọn tùy ý" một implementation để sửa lỗi thiết kế này sau khi biên dịch.

## 8. Abstract method trong interface, abstract class và kế thừa

Cần phân biệt các cấp:

- **Interface abstract method:** thường ngầm định `public abstract`. Class triển khai cụ thể cần cung cấp implementation nếu chưa có cách kế thừa implementation hợp lệ.
- **Abstract method trong abstract class:** có thể có mức truy cập `protected` hoặc package-private tùy quy tắc Java; `Modifier.isAbstract(...)` là `true`, `Method.isDefault()` luôn `false`.
- **Concrete method trong abstract class:** dù class chứa nó là `abstract`, bản thân method có thể không `abstract` và không phải default method.
- **Default method trong interface:** phương thức public có thân mã, được `isDefault()` nhận biết; class triển khai có thể kế thừa hoặc override.
- **Public concrete method trong class:** không phải interface default method dù class cung cấp implementation cho một chữ ký được khai báo ở interface.

Một method của superclass có thể đáp ứng interface abstract declaration của subclass. Vì vậy không nên suy luận rằng "mọi method khai báo trong interface phải có một method tương ứng do class triển khai tự khai báo". Hãy dùng `getDeclaringClass()` và phạm vi tìm của `getMethod/getDeclaredMethod` để trả lời đúng câu hỏi.

Ở Java source thông thường, method implementation trong class phải đáp ứng yêu cầu visibility của interface method; ví dụ implementation cho một interface `public` abstract method không được giảm visibility xuống `private`.

## 9. Phân biệt `Method.isDefault()` và `Method.getDefaultValue()`

Hai tên API dễ nhầm nhưng mục đích **hoàn toàn khác nhau**.

| API | Tác dụng | Trường hợp dùng |
| --- | --- | --- |
| `Method.isDefault()` | Kiểm tra method có phải **default method của interface** hay không | Phân tích hành vi interface, tìm phương thức có implementation mặc định |
| `Method.getDefaultValue()` | Lấy **giá trị mặc định của phần tử annotation** nếu được khai báo | Đọc metadata của `@interface`; có thể trả `null` |

Ví dụ annotation có default value:

~~~java
@interface Role {
    String level() default "viewer";
}
~~~

`Role.class.getDeclaredMethod("level").isDefault()` là `false`. Đây là annotation element method (abstract theo hợp đồng của annotation type), **không** phải interface default method có thân mã. `getDefaultValue()` trên `Method` ấy trả `"viewer"`.

Đừng suy luận `getDefaultValue() != null` thì `isDefault() == true`. Đối với annotation element mặc định, sự thật thường là **ngược lại**: có giá trị mặc định trong metadata annotation nhưng method không có thân cài đặt default của Java interface.

## 10. Kiểu tham số, generics và varargs khi tra cứu interface methods

Quy tắc chữ ký của `getDeclaredMethod` hay `getMethod` không thay đổi vì method nằm trong interface:

~~~java
interface Processor {
    void consume(String... values);
    void register(java.util.List<String> values);
}
~~~

Tra cứu chính xác (đoạn minh họa):

~~~java
Method consume = Processor.class.getDeclaredMethod(
        "consume", String[].class);
Method register = Processor.class.getDeclaredMethod(
        "register", java.util.List.class);
~~~

- `String...` được biểu diễn bằng `String[]` ở chữ ký bytecode/runtime; `consume.isVarArgs()` cho biết khai báo là varargs.
- `List<String>` chịu type erasure thành `List.class` khi tra cứu method. Metadata generic có thể đọc từ `getGenericParameterTypes()`.
- `int.class` khác `Integer.class`; tra cứu không áp dụng autoboxing hoặc widening để tự dò một method gần giống.
- Các phương thức compiler sinh như bridge method có thể hiện diện trong danh sách `getDeclaredMethods()`. Muốn phân tích khai báo từ mã nguồn, nên lọc và kiểm tra `isBridge()`/`isSynthetic()` thay vì xem mọi `Method` là khai báo thủ công.

## 11. Access control, Java modules và lỗi thường gặp

Reflection lấy được `Method` không đồng nghĩa chắc chắn gọi được `invoke(...)`. Khi phân tích:

1. Tìm đúng `Class<?>` khai báo method hoặc tra cứu public method kế thừa nếu đó là mục tiêu.
2. So khớp tên và **chữ ký runtime**; `NoSuchMethodException` có nghĩa method không được tìm thấy trong phạm vi API đang xét.
3. Đọc `getModifiers()`, `isDefault()` và `getDeclaringClass()` để phân loại.
4. Với `invoke(...)`, chuẩn bị receiver instance hoặc `null` cho method static.
5. Xem quyền truy cập; `trySetAccessible()` có thể cần thiết cho private method. Java Platform Module System có thể từ chối truy cập sâu vào package chưa mở cho caller ở module khác.
6. Khi method thực thi và ném ngoại lệ, `Method.invoke` bọc ngoại lệ đó trong `InvocationTargetException`; xem `getCause()` để biết nguyên nhân từ method gốc.

| Nhầm lẫn | Điều chỉnh |
| --- | --- |
| Thấy method có code là `default` | Chỉ interface public non-abstract instance method mới là `Method.isDefault() == true` |
| Dùng `Modifier.isAbstract` cho mọi method interface | Interface có abstract, default, static và private method |
| `getDeclaredMethods()` trên class triển khai phải chứa default method kế thừa | Không; đó là phạm vi trực tiếp của class, dùng `getMethods()` cho public method kế thừa |
| Interface static method được kế thừa như default method | Không; tra trên chính interface khai báo |
| `Method.invoke` với default method luôn ép chạy thân interface | Không; instance method theo dynamic dispatch và có thể chạy override |
| Phải dùng `trySetAccessible()` cho mọi method interface | Không; public method có thể được gọi bình thường khi đáp ứng quyền, chỉ deep access khi cần |
| Annotation element có `default "x"` là Java interface default method | Không; dùng `getDefaultValue()` cho annotation metadata |
| Thứ tự `getDeclaredMethods()` trùng thứ tự mã nguồn | Không bảo đảm; cần lọc/sắp xếp chủ động nếu muốn hiển thị ổn định |

### Lưu ý với dynamic proxy

Java dynamic proxy có cơ chế riêng: lời gọi interface method trên proxy được chuyển tới `InvocationHandler#invoke`. Từ Java 16, API `InvocationHandler.invokeDefault(proxy, method, args...)` có thể gọi trực tiếp default method của proxy interface trong những điều kiện phù hợp; nó khác với `Method.invoke(...)` thông thường. Chỉ sử dụng cơ chế proxy này khi thật sự đang xây `Proxy`, không xem nó là cách tổng quát để gọi mọi default method trên mọi object.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `interface I { void run(); }`. `I.class.getDeclaredMethod("run").isDefault()` có trả `true` không?

**Đáp án:** Không. `run()` là abstract instance method, `Modifier.isAbstract(...) == true` và `isDefault() == false`.

**Câu 2.** `interface I { default void run() {} }`, class `C implements I` không override. `C.class.getDeclaredMethod("run")` có tìm thấy method không?

**Đáp án:** Không. `run()` do `I` khai báo. `C.class.getMethod("run")` mới tìm được public method được kế thừa.

**Câu 3.** `I.class.getDeclaredMethod("run")` cho default method; receiver là object của lớp `C` override `run()`. `Method.invoke(...)` thực thi cái nào?

**Đáp án:** Override của `C` theo dynamic dispatch. `Method.isDefault()` trên method phản chiếu từ `I` vẫn là `true`.

**Câu 4.** Tại sao static method `I.make()` không tìm được bằng `C.class.getMethod("make")`, dù `C implements I`?

**Đáp án:** Static method của interface không được class triển khai kế thừa. Tra trên `I.class` và dùng receiver `null` khi `invoke`.

**Câu 5.** Interface có `private String helper()`. `helper.isDefault()` là gì?

**Đáp án:** `false`. Private method có thể có thân mã nhưng không phải public interface default method; truy cập từ caller khác có thể cần bật quyền Reflection hợp lệ.

**Câu 6.** `@interface Role { String level() default "viewer"; }`. Vì sao `isDefault()` và `getDefaultValue()` khác nhau?

**Đáp án:** `isDefault()` là phép thử cho **interface default method có body**; `getDefaultValue()` trả metadata `"viewer"` của annotation element. Hai khái niệm "default" khác nhau.

**Câu 7.** Làm sao nhận biết một method lấy từ `Class#getMethods()` được khai báo ở interface?

**Đáp án:** Kiểm tra `method.getDeclaringClass().isInterface()`. Sau đó tiếp tục xem `isDefault()`, `Modifier.isAbstract(...)`, `Modifier.isStatic(...)`; riêng việc khai báo trên interface chưa kết luận được loại method.

## Tài liệu chuẩn để kiểm tra

- [JDK 21 — java.lang.reflect.Method](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): `isDefault()`, `invoke(...)`, `getDefaultValue()` và metadata.
- [JDK 21 — java.lang.Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getMethod(s)`, `getDeclaredMethod(s)` và phạm vi kế thừa.
- [JDK 21 — InvocationHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationHandler.html): `invokeDefault(...)` đối với dynamic proxy.

**Ghi nhớ:** `Modifier.isAbstract(method.getModifiers())` kiểm tra method có abstract không; `method.isDefault()` kiểm tra method có phải **public default instance method của interface** không. `getDeclaringClass()` cho biết method được khai báo ở đâu; `getMethod` và `getDeclaredMethod` có phạm vi khác nhau. Cuối cùng, `Method.invoke` trên instance method tuân theo dynamic dispatch, nên Method phản chiếu từ interface **không đảm bảo** sẽ chạy phần thân default của interface khi receiver override method ấy.

# 3.6 Phân phối phương thức ghi đè khi gọi `Method` của lớp cha trên đối tượng lớp con

Trong Java Reflection, việc lấy đối tượng `java.lang.reflect.Method` từ **lớp cha** không đồng nghĩa với việc lệnh gọi sẽ chạy **thân phương thức của lớp cha**. Nếu phương thức là **instance method có thể ghi đè** và đối tượng đích thực tế là lớp con, `Method.invoke(...)` thực hiện **dynamic method lookup**: JVM chọn implementation phù hợp dựa trên **kiểu runtime của đối tượng đích**. Đây là điểm cốt lõi khi viết framework, bộ gọi method động, công cụ kiểm thử, mapper hoặc hệ thống plugin.

Bài này tập trung vào tình huống: đã có `Method` đại diện cho khai báo của lớp cha, rồi dùng nó để gọi trên instance lớp con. Ta sẽ đi từ cơ chế phân phối tới ví dụ chạy được, các ngoại lệ như `static`/`private`/`final`, cách gọi thật sự vào `super`, và cách chẩn đoán lỗi.

## 1. Hai câu hỏi khác nhau: tìm `Method` nào, và thực thi implementation nào?

Giả sử:

~~~java
class Parent {
    public String say() { return "parent"; }
}
class Child extends Parent {
    @Override
    public String say() { return "child"; }
}
~~~

Lệnh:

~~~java
Method method = Parent.class.getMethod("say");
Object result = method.invoke(new Child());
~~~

có **hai giai đoạn**:

1. **Tra cứu metadata:** `Parent.class.getMethod("say")` tìm phương thức public có tên `say`, không có tham số, nhìn từ `Parent`. `method.getDeclaringClass()` là `Parent.class`.
2. **Thực thi trên receiver:** `method.invoke(new Child())` nhận đối tượng có kiểu runtime `Child`. Vì `Child.say()` ghi đè `Parent.say()`, Java phân phối đến `Child.say()` và trả `"child"`.

Do đó cần phân biệt:

| Thông tin | Kết quả trong ví dụ | Nó nói điều gì? |
| --- | --- | --- |
| `method.getDeclaringClass()` | `Parent.class` | Phương thức được chọn để phản chiếu khai báo ở đâu |
| `method.getName()` | `"say"` | Tên phương thức của metadata |
| `method.getParameterTypes()` | Mảng rỗng | Danh sách kiểu tham số của khai báo |
| `receiver.getClass()` | `Child.class` | Kiểu runtime thực tế của đối tượng nhận lệnh |
| `method.invoke(receiver)` | `"child"` | Kết quả của implementation được phân phối lúc gọi |

**Quy tắc:** `Method` phản ánh **khai báo được tìm thấy**, còn lời gọi virtual phản ánh **implementation được chọn ở runtime**. Không dùng `getDeclaringClass()` để kết luận thân method nào đã chạy.

Tài liệu API Java SE 17 của `Method.invoke` nêu rõ: với instance method, dynamic method lookup có thể chọn phương thức ghi đè dựa trên kiểu runtime của target (theo JLS `15.12.4.4`). Đó là hành vi do Java quy định, không phải đặc tính may rủi của HotSpot.

## 2. Ví dụ chuẩn: cùng một `Method` của lớp cha gọi được nhiều implementation

Lưu chương trình hoàn chỉnh dưới tên **`ReflectionDispatchDemo.java`**:

~~~java
import java.lang.reflect.Method;

public class ReflectionDispatchDemo {
    static class Parent {
        public String name() { return "Parent.name"; }
        public String role(String prefix) { return prefix + ":Parent.role"; }
    }

    static class Child extends Parent {
        @Override public String name() { return "Child.name"; }
        @Override public String role(String prefix) {
            return prefix + ":Child.role";
        }
    }

    static class GrandChild extends Child {
        @Override public String name() { return "GrandChild.name"; }
    }

    public static void main(String[] args) throws Exception {
        Parent target = new Child();
        Method nameFromParent = Parent.class.getMethod("name");
        Method roleFromParent = Parent.class.getMethod("role", String.class);

        System.out.println(nameFromParent.getDeclaringClass().getSimpleName());
        System.out.println(target.getClass().getSimpleName());
        System.out.println(nameFromParent.invoke(target));
        System.out.println(nameFromParent.invoke(new Parent()));
        System.out.println(nameFromParent.invoke(new GrandChild()));
        System.out.println(roleFromParent.invoke(target, "Hello"));
        System.out.println(((Parent) target).name());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~sh
javac ReflectionDispatchDemo.java
java ReflectionDispatchDemo
~~~

**Stdout chính xác:**

~~~text
Parent
Child
Child.name
Parent.name
GrandChild.name
Hello:Child.role
Child.name
~~~

Giải thích từng kết quả:

- `getDeclaringClass().getSimpleName()` in `Parent`: `nameFromParent` đúng là metadata lấy từ cha; nó không bị thay thành `Child.class.getMethod(...)`.
- `target.getClass().getSimpleName()` in `Child`: biến `target` khai báo kiểu `Parent` nhưng tham chiếu tới object thực sự của `Child`.
- `nameFromParent.invoke(target)` in `Child.name`: lời gọi reflection phân phối override.
- Cùng đối tượng `Method`, khi receiver là `new Parent()` thì chạy `Parent.name`; receiver `new GrandChild()` thì chạy `GrandChild.name`. Không cần lấy lại `Method` theo từng class con.
- `roleFromParent.invoke(target, "Hello")` in `Hello:Child.role`: dynamic dispatch vẫn áp dụng với method có tham số nếu chữ ký thực sự được ghi đè.
- Ép kiểu `((Parent) target)` không đổi kiểu runtime, nên `((Parent) target).name()` vẫn in `Child.name`.

Có thể hình dung quá trình:

~~~text
Parent.class.getMethod("name")  ->  Method khai báo bởi Parent
                                            |
                                            v
                                 Method.invoke(receiver)
                                            |
                         +------------------+------------------+
                         |                  |                  |
                  receiver: Parent   receiver: Child   receiver: GrandChild
                         |                  |                  |
                         v                  v                  v
                   Parent.name()      Child.name()      GrandChild.name()
~~~

Ở đây mỗi nhánh phụ thuộc **receiver thực tế**, chứ không phụ thuộc câu lệnh `getMethod` đã được gọi ở lớp nào.

## 3. Vì sao JVM phân phối như vậy?

Đối với instance method được ghi đè hợp lệ, lời gọi Java thông thường kiểu `parentRef.name()` dùng cơ chế virtual dispatch. Reflection không cố tình “khóa” `Method` về body của class khai báo. `Method.invoke` dùng cơ chế dynamic lookup tương ứng với đặc tả Java.

Ba bước tư duy đủ để giải thích đa số ca thực tế:

1. **Chọn chữ ký của phương thức:** tên và kiểu tham số được xác định ở lúc lấy `Method`, ví dụ `getMethod("role", String.class)`. Reflection không tự chọn một overload mới dựa trên class runtime của đối số.
2. **Xác minh target và quyền truy cập:** instance method cần receiver không `null` và thuộc class/interface khai báo phương thức hoặc kiểu con/kiểu triển khai tương ứng; quyền truy cập cũng phải hợp lệ.
3. **Phân phối override:** nếu receiver runtime có implementation ghi đè đúng phương thức instance đó, gọi implementation phù hợp nhất. Nếu không có override, gọi implementation được kế thừa.

Ví dụ, `Child` không ghi đè `role(String)` thì lời gọi `Parent.class.getMethod("role", String.class).invoke(new Child(), "...")` sẽ dùng body `Parent.role`. Ngược lại, chỉ cần có override hợp lệ là runtime chọn body mới.

Điều này không yêu cầu method xuất hiện trực tiếp trên biến có kiểu lớp con. Dù receiver được lưu trong biến `Object`, `Parent` hoặc một interface, runtime type vẫn giữ nguyên. JVM còn phải tôn trọng cơ chế ghi đè nhiều tầng (ví dụ `GrandChild`) và quan hệ kế thừa/interface tương ứng.

### Lớp cha `abstract` và interface cũng tham gia dispatch

Khi `Method` đại diện cho phương thức abstract của lớp cha hoặc một interface, nó có thể gọi implementation của object cụ thể. Chương trình hoàn chỉnh **`InterfaceDispatchDemo.java`**:

~~~java
import java.lang.reflect.Method;

public class InterfaceDispatchDemo {
    interface Reporter { String report(); }

    static class ReporterImpl implements Reporter {
        @Override public String report() { return "implementation"; }
    }

    abstract static class BaseTask {
        public abstract String execute();
    }

    static class Work extends BaseTask {
        @Override public String execute() { return "concrete"; }
    }

    public static void main(String[] args) throws Exception {
        Method viaInterface = Reporter.class.getMethod("report");
        Method viaAbstractBase = BaseTask.class.getMethod("execute");
        System.out.println(viaInterface.invoke(new ReporterImpl()));
        System.out.println(viaAbstractBase.invoke(new Work()));
    }
}
~~~

~~~sh
javac InterfaceDispatchDemo.java
java InterfaceDispatchDemo
~~~

~~~text
implementation
concrete
~~~

Ở cả hai lệnh `invoke`, declaring type không có body thông thường để chạy; receiver cung cấp implementation cụ thể. Nguyên tắc tương tự cũng áp dụng khi interface có default method: implementation ghi đè trong class, nếu có, sẽ được chọn theo quy tắc dispatch. Đừng suy diễn rằng reflection luôn chạy thân default của interface.

## 4. Ngoại lệ quan trọng: `static`, `private`, `final` và overload

Không phải mọi method cùng tên ở lớp cha và lớp con đều có quan hệ **override**. Có những trường hợp tên giống nhau nhưng Java **không thực hiện virtual override dispatch**.

| Trường hợp | Có override? | Khi invoke `Method` từ lớp cha trên instance lớp con |
| --- | --- | --- |
| Public/protected instance method được lớp con override hợp lệ | Có | Chạy implementation lớp con |
| Instance method kế thừa, lớp con không override | Không có override mới | Chạy implementation kế thừa từ cha |
| `abstract` method của cha, có implementation ở lớp con | Có implementation cụ thể | Chạy implementation của lớp con |
| Interface method, object triển khai/ghi đè | Theo quy tắc interface dispatch | Chạy implementation áp dụng cho object |
| `static` method cùng tên ở cha/con | **Không**: đây là method hiding | Chạy static method do `Method` đại diện; receiver bị bỏ qua |
| `private` method ở cha, method cùng tên ở con | **Không**: private cha không được override | Với quyền truy cập hợp lệ, chạy method private của cha |
| `final` instance method ở cha | Không thể override hợp lệ | Chạy body của cha |
| Cha có `render(Object)`, con chỉ thêm `render(String)` | **Không**: đây là overload | `Method` của `render(Object)` vẫn gọi implementation `render(Object)` |

Để kiểm chứng tất cả các trường hợp trong một chương trình độc lập, lưu **`ReflectionRulesDemo.java`**:

~~~java
import java.lang.reflect.Method;

public class ReflectionRulesDemo {
    static class Base {
        public static String kind() { return "Base.static"; }
        private String secret() { return "Base.private"; }
        public final String id() { return "Base.final"; }
        public String render(Object value) { return "Base(Object)"; }
    }

    static class Derived extends Base {
        public static String kind() { return "Derived.static"; }
        public String secret() { return "Derived.public"; }
        public String render(String value) { return "Derived(String)"; }
    }

    public static void main(String[] args) throws Exception {
        Derived target = new Derived();

        System.out.println(Base.class.getMethod("kind").invoke(target));
        System.out.println(Derived.class.getMethod("kind").invoke(null));

        Method privateOfBase = Base.class.getDeclaredMethod("secret");
        System.out.println(privateOfBase.invoke(target));
        System.out.println(Derived.class.getMethod("secret").invoke(target));

        System.out.println(Base.class.getMethod("id").invoke(target));
        System.out.println(
            Base.class.getMethod("render", Object.class).invoke(target, "A")
        );
        System.out.println(
            Derived.class.getMethod("render", String.class).invoke(target, "A")
        );
    }
}
~~~

~~~sh
javac ReflectionRulesDemo.java
java ReflectionRulesDemo
~~~

~~~text
Base.static
Derived.static
Base.private
Derived.public
Base.final
Base(Object)
Derived(String)
~~~

**Giải thích rõ từng ngoại lệ:**

- **`static`:** `Base.kind()` và `Derived.kind()` là hai static methods có quan hệ *hiding*, không phải override. Với `Base.class.getMethod("kind")`, kết quả luôn là `Base.static`. Tham số receiver trong `invoke` bị bỏ qua; ở đây truyền `target` chỉ để nhấn mạnh điều đó. Gọi `Derived.class.getMethod("kind").invoke(null)` mới nhận `Derived.static`.
- **`private`:** `Base.secret()` không được lớp con kế thừa để override. `Derived.secret()` là method riêng biệt. `Base.class.getDeclaredMethod("secret").invoke(target)` chạy body `Base.private`. Chương trình mẫu truy cập được method private nhờ các nested classes thuộc cùng **nest** với lớp bao ngoài trong Java 17; caller khác có thể nhận `IllegalAccessException`, còn can thiệp `setAccessible` chịu ràng buộc module.
- **`final`:** `Base.id()` không thể bị override, nên invoke trên `Derived` vẫn cho `Base.final`. Nếu cố khai báo `@Override public String id()` trong `Derived`, chương trình không biên dịch.
- **Overload:** `Base.render(Object)` và `Derived.render(String)` có kiểu tham số khác nhau, do đó **không override**. Dù truyền `"A"` là `String`, `Method` được chọn bằng `getMethod("render", Object.class)` sẽ chạy `Base.render(Object)`. Reflection không chuyển sang overload `String` chỉ vì argument runtime phù hợp hơn.

Trong code reflection thật, lỗi nhầm **overload thành override** đặc biệt phổ biến khi thiết kế dispatcher. Phải kiểm tra tên và danh sách `Class<?>` của kiểu tham số, không chỉ nhìn tên method.

### Ghi đè với generic và kiểu trả về hiệp biến

Ở mức Java source, một phương thức có thể override với kiểu trả về **covariant** (cụ thể hơn), và generic type erasure có thể khiến compiler sinh **bridge method** để giữ đúng hành vi đa hình ở JVM. Khi duyệt `getDeclaredMethods()`, đôi khi thấy thêm method mà source không viết trực tiếp.

- `Method.isBridge()` cho biết method có phải bridge method hay không; `isSynthetic()` là metadata khác có thể xuất hiện.
- Việc bridge xuất hiện **không làm mất** hợp đồng dynamic dispatch của `Method.invoke` trên instance method.
- Khi xây công cụ liệt kê API, cân nhắc lọc hoặc xử lý bridge methods có chủ đích; không dựa vào số lượng method nhìn thấy để suy ra số overload trong source.
- Chỉ chữ ký (bao gồm tham số và các quy tắc overriding của Java) mới quyết định quan hệ override; không dùng chuỗi tên method đơn lẻ.

## 5. `getMethod`, `getDeclaredMethod` và `getDeclaringClass` ảnh hưởng ra sao?

Các API tra cứu metadata không thay đổi bản chất dispatch khi `invoke` trên receiver:

| Cách lấy `Method` | Phạm vi tra cứu | Hệ quả cần chú ý |
| --- | --- | --- |
| `Parent.class.getMethod("name")` | Phương thức `public` nhìn thấy từ `Parent`, gồm public methods kế thừa | Với method public instance, vẫn phân phối tới override trên `Child` |
| `Parent.class.getDeclaredMethod("name")` | Chỉ phương thức khai báo **trực tiếp** trong `Parent`, bất kể access modifier | Lấy chính metadata của cha, nhưng không ép runtime chạy body cha |
| `Child.class.getMethod("name")` | Public method nhìn thấy từ `Child` | Nếu `Child` override public method, metadata thường khai báo bởi `Child` |
| `Child.class.getDeclaredMethod("name")` | Chỉ method khai báo trong `Child` | Ném `NoSuchMethodException` nếu `Child` chỉ kế thừa method mà không khai báo lại |
| `method.getDeclaringClass()` | Class/interface thực sự khai báo metadata đó | Cho biết nguồn khai báo của `Method`, không cho biết body nào chạy trên mọi receiver |

Ví dụ khi lớp con có override:

~~~java
Method parentMethod = Parent.class.getMethod("name");
Method childMethod = Child.class.getMethod("name");

System.out.println(parentMethod.getDeclaringClass() == Parent.class); // true
System.out.println(childMethod.getDeclaringClass() == Child.class);   // true
~~~

Đoạn này **minh họa** trong ngữ cảnh hai nested types `Parent`/`Child` của `ReflectionDispatchDemo`, không phải chương trình độc lập.

**Access check không phải dispatch.** Nếu một method không public, reflection có thể từ chối gọi vì `IllegalAccessException` dù receiver phù hợp. `trySetAccessible()`/`setAccessible(true)` có thể thay đổi việc kiểm tra quyền trong phạm vi Java module cho phép, nhưng **không biến lời gọi virtual thành lời gọi `super`**. Từ Java 9+, strong encapsulation có thể ngăn truy cập reflective vào thành phần của module không mở phù hợp; không nên xem `setAccessible(true)` là cách chắc chắn để vượt qua mọi rào cản.

## 6. Muốn chạy đúng thân lớp cha thì làm gì?

Giả sử `Child.say()` override `Parent.say()`. Kết quả của:

~~~java
Method fromParent = Parent.class.getMethod("say");
fromParent.invoke(new Child());
~~~

vẫn là `Child.say()`. **`Method.invoke` không có tùy chọn “bỏ qua override”**. Kể cả lấy method bằng `getDeclaredMethod`, casting receiver thành `Parent`, hoặc gọi `setAccessible(true)`, điều đó cũng không ép dispatch về body lớp cha.

Trong code lớp con, cách tự nhiên để gọi implementation cha là **`super.say()`**. Nếu đang làm việc ở tầng runtime với method handle, Java hỗ trợ ngữ nghĩa special invocation qua `MethodHandles.Lookup.findSpecial(...)` với lookup có quyền phù hợp. Đây là một cơ chế **khác** với `Method.invoke`.

Ví dụ độc lập **`SuperInvocationDemo.java`**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public class SuperInvocationDemo {
    static class Parent {
        public String say() { return "parent"; }
    }

    static class Child extends Parent {
        @Override public String say() { return "child"; }

        public String callSuper() { return super.say(); }

        public String callParentHandle() throws Throwable {
            MethodHandle handle = MethodHandles.lookup().findSpecial(
                Parent.class, "say", MethodType.methodType(String.class),
                Child.class
            );
            return (String) handle.invokeExact(this);
        }
    }

    public static void main(String[] args) throws Throwable {
        Child child = new Child();
        Method fromParent = Parent.class.getMethod("say");

        System.out.println(fromParent.invoke(child));
        System.out.println(child.callSuper());
        System.out.println(child.callParentHandle());
    }
}
~~~

~~~sh
javac SuperInvocationDemo.java
java SuperInvocationDemo
~~~

~~~text
child
parent
parent
~~~

Trong `Child.callParentHandle()`, `MethodHandles.lookup()` được tạo **ngay trong ngữ cảnh lớp con**, có quyền phù hợp cho `findSpecial(Parent.class, ..., Child.class)`. Method handle mô phỏng lời gọi special từ `Child`, nên có thể chạy `Parent.say()` bất chấp override tại `Child`. Không thể sao chép tùy tiện đoạn `findSpecial` sang một lớp ngoài bất kỳ: kiểm tra `Lookup`, `specialCaller` và quyền truy cập vẫn áp dụng, và có thể ném `IllegalAccessException`.

Cách so sánh nhanh:

| Lời gọi | Chạy method nào? |
| --- | --- |
| `new Child().say()` | `Child.say()` |
| `((Parent) new Child()).say()` | `Child.say()` |
| `Parent.class.getMethod("say").invoke(new Child())` | `Child.say()` |
| `super.say()` bên trong `Child` | `Parent.say()` |
| `findSpecial(...)` có lookup phù hợp như ví dụ | `Parent.say()` |

Đối với method interface `default`, cú pháp `InterfaceName.super.method()` hoặc cơ chế special invocation phù hợp cũng có quy tắc truy cập riêng; không mặc định lấy `Method` của interface rồi `invoke` là sẽ bỏ qua override.

## 7. Các lỗi lúc gọi reflective method và cách phân biệt

`Method.invoke(Object obj, Object... args)` có hợp đồng về receiver, argument, access và exception. Những lỗi này thường bị lẫn với chuyện dispatch:

- **`IllegalArgumentException`:** receiver không phải instance của declaring class/interface hoặc subtype tương thích, số argument sai, kiểu argument không thể chuyển đổi phù hợp; reflection không tự “đoán” overload khác.
- **`NullPointerException`:** receiver `null` khi gọi instance method. Với `static`, receiver có thể là `null`.
- **`IllegalAccessException`:** caller không đủ quyền truy cập method khi reflective access checks được thực thi.
- **`InvocationTargetException`:** code trong method được gọi ném exception; lấy **`getCause()`** để biết nguyên nhân gốc của method được invoke.
- **`NoSuchMethodException`:** lỗi tại bước `getMethod` hoặc `getDeclaredMethod` nếu không có phương thức tương ứng, chưa đến bước dispatch.
- **`ExceptionInInitializerError`:** initialization của lớp bị kích hoạt lúc gọi có thể lỗi, đặc biệt với static method.

Ví dụ độc lập **`InvocationFailureDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class InvocationFailureDemo {
    static class Parent {
        public String speak() { return "ok"; }
        public void explode() { throw new IllegalStateException("broken"); }
    }

    static class Child extends Parent {}

    public static void main(String[] args) throws Exception {
        Method speak = Parent.class.getMethod("speak");

        try {
            speak.invoke(new Object());
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }

        try {
            speak.invoke(null);
        } catch (NullPointerException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }

        Method explode = Parent.class.getMethod("explode");
        try {
            explode.invoke(new Child());
        } catch (InvocationTargetException ex) {
            Throwable cause = ex.getCause();
            System.out.println(
                cause.getClass().getSimpleName() + ": " + cause.getMessage()
            );
        }
    }
}
~~~

~~~sh
javac InvocationFailureDemo.java
java InvocationFailureDemo
~~~

~~~text
IllegalArgumentException
NullPointerException
IllegalStateException: broken
~~~

Trong phần cuối, `explode` là instance method kế thừa từ `Parent`; body chạy rồi ném `IllegalStateException`. Reflection bọc nó trong `InvocationTargetException`. Nếu method được override để ném lỗi khác, vẫn nên điều tra nguyên nhân qua `getCause()` và stack trace của exception gốc.

### Lưu ý về kết quả trả về

`invoke(...)` trả về `Object`: giá trị primitive được boxing (ví dụ `int` thành `Integer`), còn method `void` trả `null`. Đối với overload hoặc caller yêu cầu kiểu cụ thể, cần ép kiểu/kiểm tra giá trị kết quả thích hợp. Không nhầm kiểu trả về của `Method.invoke` trong API (luôn `Object`) với kiểu trả về thật của phương thức phản chiếu (`method.getReturnType()`).

## 8. Những ngộ nhận rất dễ làm sai chương trình Reflection

**Ngộ nhận 1: “Lấy Method từ cha thì chắc chắn chạy code của cha.”** Sai với instance method được ghi đè: dispatch căn cứ receiver runtime.

**Ngộ nhận 2: “`getDeclaredMethod` giúp gọi implementation cha.”** Sai. Nó chỉ giới hạn nguồn tìm metadata, không thay virtual dispatch thành special call.

**Ngộ nhận 3: “Ép kiểu object sang cha sẽ ép chạy method cha.”** Sai. `((Parent) child).say()` vẫn gọi override nếu method virtual; cast không đổi runtime class.

**Ngộ nhận 4: “Method cùng tên ở con là override.”** Sai. Phải kiểm tra kiểu tham số, quy tắc override, `static`, `private`, `final`. `render(String)` không override `render(Object)`.

**Ngộ nhận 5: “`Method.invoke` tự chọn overload tốt nhất từ giá trị argument.”** Sai. Bạn chọn method bằng metadata `name + parameterTypes` trước; `invoke` làm kiểm tra/chuyển đổi tham số tương thích với method đã chọn.

**Ngộ nhận 6: “`Method.getDeclaringClass()` chỉ ra class thực thi method vừa gọi.”** Sai. Nó chỉ ra declaring class của metadata; class thực thi có thể là subclass.

**Ngộ nhận 7: “`setAccessible(true)` có thể bỏ qua override.”** Sai. Nó liên quan access checks và có giới hạn module, không điều khiển dispatch.

**Ngộ nhận 8: “Static method của cha sẽ bị static method của con override.”** Sai. Đây là hiding; `Method.invoke` đối với static bỏ qua receiver.

**Ngộ nhận 9: “Nếu `invoke` ném `InvocationTargetException` thì lỗi nằm ở API Reflection.”** Chưa chắc. Thường cần xem `getCause()` vì code của method được gọi đã ném exception.

**Ngộ nhận 10: “Có thể tùy ý gọi `findSpecial` từ mọi nơi để chạy cha.”** Sai. `Lookup` và `specialCaller` có ràng buộc chặt, khác quyền của ordinary reflection.

## 9. Cách kiểm tra một ca dispatch ngoài thực tế

Khi gặp hiện tượng “đã lấy `Method` của cha nhưng gọi ra hành vi con”, hãy ghi những thông tin sau:

1. **Metadata được chọn:** `method.getDeclaringClass()`, `method.getName()`, `method.getParameterTypes()`, `method.getReturnType()` và `method.getModifiers()`.
2. **Đối tượng đích:** `target.getClass()` (sau khi kiểm tra `target != null` đối với instance method). Đừng dựa vào kiểu khai báo của biến đang giữ receiver.
3. **Quan hệ override:** với chữ ký method đã chọn, tìm implementation phù hợp của runtime class; phân biệt `@Override` thật với overload, hiding hoặc private method riêng biệt.
4. **Phạm vi Reflection:** `getMethod` chỉ lấy public method nhìn thấy, `getDeclaredMethod` chỉ lấy method khai báo trực tiếp; đánh giá access/module riêng.
5. **Bridge hoặc generic:** nếu danh sách `getDeclaredMethods()` bất thường, kiểm tra `isBridge()` và `isSynthetic()`.
6. **Kết quả và lỗi:** so sánh runtime output; nếu ném `InvocationTargetException`, theo `getCause()` và stack trace của code được gọi.
7. **Nếu thực sự muốn implementation cha:** dùng `super.method()` ở vị trí Java phù hợp hoặc `MethodHandles.Lookup.findSpecial` có quyền truy cập chính xác.

Có thể dùng đoạn kiểm tra metadata dưới đây trong phạm vi chương trình có sẵn đối tượng `method`/`target` (đây là **snippet minh họa**, không độc lập):

~~~java
System.out.println("declaring = " + method.getDeclaringClass().getName());
System.out.println("receiver  = " + target.getClass().getName());
System.out.println("name      = " + method.getName());
System.out.println("parameters= " +
    java.util.Arrays.toString(method.getParameterTypes()));
System.out.println("static    = " +
    java.lang.reflect.Modifier.isStatic(method.getModifiers()));
System.out.println("bridge    = " + method.isBridge());
~~~

Các dòng log này xác định **method đã chọn** và **target có thể phân phối đến override nào**. Chúng không phải phép đo trực tiếp toàn bộ call graph; nếu có nhiều tầng delegation, tiếp tục dùng debugger/stack trace hoặc instrumentation để xác nhận hành vi của body.

## 10. Tự luyện tập

**Bài 1.** `Base.run()` là public instance method; `Sub.run()` ghi đè. `Method m = Base.class.getMethod("run"); m.invoke(new Sub());` chạy method nào?

**Đáp án:** `Sub.run()`, do dynamic dispatch trên receiver `Sub`. `m.getDeclaringClass()` vẫn là `Base.class`.

**Bài 2.** `Sub` không override `Base.run()` mà chỉ thêm `run(String)`. `Base.class.getMethod("run").invoke(new Sub())` chạy gì?

**Đáp án:** `Base.run()` vì method `run(String)` là overload khác chữ ký.

**Bài 3.** `Base.version()` và `Sub.version()` đều `static`. Lấy `Base.class.getMethod("version")` rồi `invoke(new Sub())` có gọi `Sub.version()` không?

**Đáp án:** Không; static method không override. Runtime bỏ qua tham số receiver, dùng method static mà `Method` đại diện trong `Base`.

**Bài 4.** Vì sao gọi `Parent.class.getDeclaredMethod("say").invoke(child)` không đồng nghĩa `super.say()`?

**Đáp án:** `getDeclaredMethod` chỉ tìm khai báo trong `Parent`; `invoke` vẫn dùng dynamic dispatch cho instance method overridable. `super.say()` là special invocation từ ngữ cảnh lớp con.

**Bài 5.** `Method m` đại diện method `abstract` ở lớp cha. `m.invoke(instanceLopCon)` có thể chạy không?

**Đáp án:** Có, nếu receiver hợp lệ có implementation cụ thể và thỏa access checks. Reflection gọi implementation phù hợp ở runtime.

**Bài 6.** Vì sao một lệnh `Method.invoke` có thể ném `InvocationTargetException` nhưng method ứng dụng thực tế ném `IllegalStateException`?

**Đáp án:** Reflection bọc exception phát sinh bên trong target method; xem `InvocationTargetException.getCause()` để lấy lỗi gốc.

## 11. Tài liệu tham khảo

- Java SE 17, `java.lang.reflect.Method.invoke` — mô tả dynamic method lookup, phân phối override theo runtime type, tham số và ngoại lệ: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)
- Java SE 17, `Class.getMethod` / `Class.getDeclaredMethod`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java Language Specification 17, `15.12.4.4` — Locate Method to Invoke: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.4
- Java SE 17, `MethodHandles.Lookup.findSpecial` — special invocation và kiểm tra access: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#findSpecial(java.lang.Class,java.lang.String,java.lang.invoke.MethodType,java.lang.Class)
- Java SE 17, `Method.isBridge`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#isBridge()

**Kết luận học thuật:** Trong `Method.invoke`, **khai báo của `Method`** quyết định method/chữ ký đang được gọi; với instance method có override, **kiểu runtime của receiver** quyết định body thực thi. Để gọi body cha bất chấp override cần special invocation đúng quyền, điển hình `super.method()` hoặc `Lookup.findSpecial(...)`.
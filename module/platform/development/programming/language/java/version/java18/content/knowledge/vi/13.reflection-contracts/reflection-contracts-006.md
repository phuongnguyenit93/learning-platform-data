# getParameterTypes(), getReturnType(), getDeclaringClass() và isVarArgs() để mô tả lời gọi

## 1. Mục tiêu và bối cảnh

Trong Java, `java.lang.reflect.Method` cho phép đọc chữ ký của method tại runtime. Khi xây dựng công cụ kiểm tra API, command dispatcher, serializer, framework gắn annotation hoặc hệ thống chẩn đoán, ta cần biết **method nhận những tham số nào, trả về kiểu gì, được khai báo ở lớp nào và có phải varargs không**.

Bốn phương thức phản ánh những khía cạnh khác nhau:

- `getParameterTypes()`: dãy kiểu tham số hình thức, theo thứ tự khai báo.
- `getReturnType()`: kiểu trả về khai báo của một `Method`.
- `getDeclaringClass()`: lớp/interface thực sự khai báo member.
- `isVarArgs()`: method hoặc constructor có được khai báo với tham số biến độ dài hay không.

Bài thuộc chương **Hợp đồng reflection** của module `JAVA_VERSION_JAVA18`. Module tập trung vào những thay đổi từ Java 18 vẫn hữu ích trên JDK hiện đại, gồm UTF-8 mặc định, Simple Web Server, Javadoc snippets và việc kiểm chứng hợp đồng API liên quan tới phân giải tên, reflection, MethodHandle. Với reflection, Java 18 có JEP 416 tái hiện thực Core Reflection dựa trên method handles; tuy nhiên, **hợp đồng public API của các phương thức trong bài vẫn có giá trị trên JDK hiện đại**. Ta kiểm chứng API công khai thay vì dựa vào lớp nội bộ hoặc thủ thuật reflection cũ.

**Kết quả mong đợi:** sau bài học, bạn có thể đọc metadata của `Method`/`Constructor`, in chữ ký dễ hiểu, tìm method đúng overload, mô tả biến độ dài chính xác, phân biệt metadata với phép gọi thực tế và tự kiểm tra các edge case.

## 2. Bản đồ API: Method, Constructor, Executable và Member

`Method` và `Constructor<?>` là hai loại executable khác nhau, cùng kế thừa `java.lang.reflect.Executable`. Cả hai đều hiện thực ý niệm `Member`.

~~~text
                  java.lang.reflect.Member
                         ^
                         |
                  java.lang.reflect.Executable
                      /          \
                     /            \
                 Method       Constructor<?>
~~~

Các phương thức liên quan:

| Phương thức | Nơi khai báo chính | Kết quả | Phạm vi áp dụng |
| --- | --- | --- | --- |
| `getParameterTypes()` | `Executable` (cụ thể hóa bởi `Method`/`Constructor`) | `Class<?>[]` | Method và constructor |
| `getReturnType()` | `Method` | `Class<?>` | Chỉ method |
| `getDeclaringClass()` | Hợp đồng `Member`, hiện thực trong executable | `Class<?>` (constructor có kiểu trả về chuyên biệt `Class<T>`) | Method và constructor |
| `isVarArgs()` | `Executable` | `boolean` | Method và constructor |

Lưu ý quan trọng: **`Constructor` không có `getReturnType()`**. Constructor tạo instance, nhưng trong Core Reflection nó không được mô tả như method có kiểu trả về là lớp được xây dựng. Khi viết code dùng `Executable` chung cho cả hai, cần phân nhánh bằng `instanceof Method` nếu muốn đọc return type.

## 3. `getParameterTypes()`: danh sách kiểu tham số hình thức

Chữ ký:

~~~java
Class<?>[] parameterTypes = method.getParameterTypes();
~~~

Hợp đồng:

1. Trả về một mảng các đối tượng `Class` biểu diễn kiểu của **formal parameters**.
2. Thứ tự các phần tử giữ nguyên thứ tự tham số trong chữ ký method/constructor.
3. Nếu không có tham số, trả mảng độ dài `0`, không phải một danh sách tham số `null`.
4. Kết quả mô tả **kiểu khai báo sau type erasure**; không bảo tồn đầy đủ type argument của generic.
5. Với `int` hay `boolean`, phần tử tương ứng là `int.class`, `boolean.class`; với mảng là kiểu `String[].class` hoặc `int[].class`.

Ví dụ:

~~~java
public static String format(String prefix, int count) {
    return prefix.repeat(count);
}
~~~

Tra cứu:

~~~java
Method format = Api.class.getMethod("format", String.class, int.class);
Class<?>[] params = format.getParameterTypes();

System.out.println(params.length);             // 2
System.out.println(params[0] == String.class); // true
System.out.println(params[1] == int.class);    // true
~~~

**Đừng nhầm kiểu tham số hình thức với đối số truyền vào một lần gọi.** Method `format(String, int)` có hai kiểu tham số cố định; dù gọi với `"ha", 2` hay `"x", 5`, mảng `getParameterTypes()` vẫn là `[String.class, int.class]`.

### 3.1. Tra cứu overload theo kiểu chính xác

~~~java
public static void send(String value) { }
public static void send(int value) { }
~~~

Tra cứu bằng `Class.getMethod`:

~~~java
Method byText = Api.class.getMethod("send", String.class);
Method byInt  = Api.class.getMethod("send", int.class);
~~~

`getMethod` dùng tên method và các kiểu tham số để tìm public member, kể cả một số method kế thừa. Nó không tìm theo giá trị đối số runtime. Đừng dùng `Integer.class` nếu chữ ký thực sự yêu cầu primitive `int`: đây là hai `Class` khác nhau.

Nếu cần tìm method khai báo trực tiếp trong một lớp bất kể access level, có thể dùng `getDeclaredMethod`. Tuy nhiên, **tìm thấy metadata không đồng nghĩa với quyền gọi method**, đặc biệt khi có Java module boundaries và quyền truy cập bị hạn chế.

### 3.2. Tham số generic và type erasure

Ví dụ:

~~~java
public static List<String> copy(List<String> values) {
    return List.copyOf(values);
}
~~~

`getParameterTypes()[0]` trả về `List.class`, không phải một `Class<List<String>>` chứa đủ kiểu phần tử. Để mô tả cả chữ ký generic:

~~~java
Method copy = Api.class.getMethod("copy", List.class);
System.out.println(copy.getParameterTypes()[0].getTypeName());
// java.util.List

System.out.println(copy.getGenericParameterTypes()[0].getTypeName());
// java.util.List<java.lang.String>
~~~

`getGenericParameterTypes()` trả về `Type[]`, có thể gồm `ParameterizedType`, `TypeVariable` hoặc kiểu khác. Nó có thể mang thông tin generic từ chữ ký class file, nhưng không làm cho kiểu generic vốn bị erasure trở thành runtime class riêng.

### 3.3. Tham số ngầm và constructor

`getParameterTypes()` được định nghĩa cho `Executable` nói chung. Một số constructor có tham số ngầm ngoài những gì ta nhìn thấy trực tiếp trong khai báo source, chẳng hạn constructor của non-static inner class cần tham chiếu tới enclosing instance. Vì vậy, nếu mô tả constructor phức tạp, **đừng suy số lượng tham số chỉ bằng cách đếm tên hiển thị trong source**.

`getParameterCount()` là phương thức liên quan giúp biết số formal parameters mà reflection báo cáo; `getParameters()` cung cấp `Parameter[]` và một số cờ như `isImplicit()`, `isSynthetic()` khi cần giải thích nguồn gốc tham số. Tên tham số không nhất thiết được lưu sẵn: `Parameter.isNamePresent()` phụ thuộc metadata biên dịch, thường cần `javac -parameters`.

## 4. `getReturnType()`: kiểu trả về của method

Chữ ký:

~~~java
Class<?> returnType = method.getReturnType();
~~~

Phương thức này mô tả **kiểu trả về được khai báo** trong chữ ký method, không phải kiểu động của object trả về trong một lần thực thi.

| Khai báo method | Kết quả `getReturnType()` |
| --- | --- |
| `String name()` | `String.class` |
| `int count()` | `int.class` |
| `void touch()` | `void.class` |
| `String[] values()` | `String[].class` |
| `List<String> names()` | `List.class` vì type erasure |

Ví dụ:

~~~java
Method touch = Api.class.getMethod("touch");
System.out.println(touch.getReturnType() == void.class); // true

Method format = Api.class.getMethod("format", String.class, int.class);
System.out.println(format.getReturnType() == String.class); // true
~~~

Phân biệt với `Method.invoke`:

- `getReturnType()` trả `Class<?>` mô tả kiểu khai báo.
- `invoke(...)` chạy method và trả `Object`. Kết quả primitive được boxed (ví dụ `int` thành `Integer`), còn method `void` khiến `invoke` trả `null`.
- Nếu method khai báo trả `Object` nhưng một lần chạy trả instance của `String`, `getReturnType()` vẫn là `Object.class`.

Đối với generic:

~~~java
Method copy = Api.class.getMethod("copy", List.class);
System.out.println(copy.getReturnType() == List.class); // true
System.out.println(copy.getGenericReturnType().getTypeName());
// java.util.List<java.lang.String>
~~~

`getGenericReturnType()` có thể bảo tồn mô tả generic dưới dạng `Type`; `getReturnType()` vẫn là kiểu `Class` sau erasure.

## 5. `getDeclaringClass()`: member khai báo ở đâu?

Chữ ký:

~~~java
Class<?> owner = method.getDeclaringClass();
~~~

Trả về `Class` biểu diễn **lớp hoặc interface khai báo member này**, không nhất thiết là lớp mà bạn dùng để tìm method, cũng không nhất thiết là lớp của object nhận lời gọi.

Ví dụ:

~~~java
public static class Parent {
    public String category() {
        return "parent";
    }
}

public static class Child extends Parent {
}
~~~

Dù tìm method trên `Child.class`:

~~~java
Method inherited = Child.class.getMethod("category");
System.out.println(inherited.getDeclaringClass() == Parent.class); // true
~~~

Vì `category()` được khai báo ở `Parent`, `getDeclaringClass()` trả `Parent.class`. `Child` chỉ **kế thừa** method ấy.

### 5.1. Đừng nhầm với dynamic dispatch

Khi `Child` override một method của `Parent`, lời gọi instance thông qua `Method.invoke` có thể thực hiện **dynamic dispatch** dựa trên kiểu runtime của receiver:

~~~java
public static class Parent {
    public String category() { return "parent"; }
}
public static class Child extends Parent {
    @Override
    public String category() { return "child"; }
}
~~~

~~~java
Method baseMethod = Parent.class.getMethod("category");
System.out.println(baseMethod.getDeclaringClass() == Parent.class); // true
System.out.println(baseMethod.invoke(new Child()));                // child
~~~

Metadata của `baseMethod` vẫn chỉ method khai báo trong `Parent`, nhưng lời gọi trên instance `Child` chạy override tương ứng. Do đó, `getDeclaringClass()` **không dự báo chắc method body nào được chọn trong mọi lời gọi ảo**.

### 5.2. Nguồn lấy Method cũng quan trọng

- `Child.class.getMethod("category")` tra public member, có thể trả method kế thừa.
- `Child.class.getDeclaredMethod("category")` chỉ xét method do `Child` khai báo; nếu `Child` không override, sẽ không tìm thấy `category()`.
- `getMethods()` chứa các public methods được khai báo hoặc kế thừa; thứ tự mảng trả về không được bảo đảm.
- `getDeclaredMethods()` chứa những method được khai báo trực tiếp trong class/interface, không chứa inherited methods.

`getDeclaringClass()` là thuộc tính của **Method được tìm thấy**, không có nghĩa là `Class.getDeclaringClass()` mang ý nghĩa tương tự: phương thức trên `Class` nói về lớp lồng được khai báo trong lớp khác.

## 6. `isVarArgs()`: phân biệt `...` với tham số mảng

`Executable.isVarArgs()` trả `true` nếu executable được **khai báo** nhận số lượng đối số biến thiên. Đây là cờ của chữ ký, không phải phép kiểm tra tham số cuối chỉ là mảng.

Xét hai method:

~~~java
public static String join(String... parts) {
    return String.join("|", parts);
}

public static String joinArray(String[] parts) {
    return String.join("|", parts);
}
~~~

Về kiểu tham số tại runtime, cả hai có `String[].class` ở vị trí cuối. Nhưng:

~~~java
Method a = Api.class.getMethod("join", String[].class);
Method b = Api.class.getMethod("joinArray", String[].class);

System.out.println(a.getParameterTypes()[0] == String[].class); // true
System.out.println(b.getParameterTypes()[0] == String[].class); // true
System.out.println(a.isVarArgs()); // true
System.out.println(b.isVarArgs()); // false
~~~

Vậy công thức nhận diện varargs chính xác là dùng `isVarArgs()`, không phải tự kiểm tra `getParameterTypes()[last].isArray()`.

### 6.1. Chữ ký nhiều tham số

~~~java
public static void log(String level, Object... values) { }
~~~

Reflection mô tả:

- `getParameterTypes()` trả `[String.class, Object[].class]`.
- `isVarArgs()` trả `true`.
- Formal parameter count là `2`, dù lời gọi Java thông thường có thể viết `log("INFO")`, `log("INFO", 1)` hoặc `log("INFO", 1, 2)`.

`...` chỉ có thể đặt ở tham số cuối của khai báo method/constructor. Nó được biểu diễn bằng kiểu mảng khi dùng reflection để mô tả formal parameters.

### 6.2. Cờ varargs không tự chuyển đổi đối số khi gọi phản chiếu

Method:

~~~java
public static String join(String... parts) {
    return String.join("|", parts);
}
~~~

Lời gọi Java thông thường có thể viết:

~~~java
Api.join("a", "b");
~~~

Nhưng `Method.invoke(Object, Object...)` là API có tham số varargs riêng của **chính Method.invoke**. Khi gọi mục tiêu `join` bằng reflection, cần cung cấp **một đối số hình thức** kiểu `String[]` cho method mục tiêu:

~~~java
Method join = Api.class.getMethod("join", String[].class);

// Đúng: một actual argument của method mục tiêu là String[].
Object value = join.invoke(null, (Object) new String[] {"a", "b"});
System.out.println(value); // a|b
~~~

Ép kiểu `(Object)` là quan trọng: nó khiến Java compiler không trải mảng `String[]` thành danh sách argument của `Method.invoke`. Ngược lại:

~~~java
join.invoke(null, "a", "b"); // IllegalArgumentException: số đối số không khớp
~~~

`isVarArgs()==true` không khiến `Method.invoke` tự thu gom `"a"` và `"b"` vào mảng cho method đích. Đây là lỗi thường gặp khi viết dispatcher động.

## 7. Constructor: có tham số, declaring class và varargs nhưng không có return type

Các API sau hoạt động với constructor:

~~~java
Constructor<Api> ctor =
        Api.class.getConstructor(String.class, int[].class);

Class<?>[] parameters = ctor.getParameterTypes();
Class<Api> owner = ctor.getDeclaringClass();
boolean variable = ctor.isVarArgs();
~~~

Nếu class định nghĩa:

~~~java
public Api(String label, int... flags) { }
~~~

Thì:

| Câu hỏi | Kết quả |
| --- | --- |
| `ctor.getParameterTypes()[0]` | `String.class` |
| `ctor.getParameterTypes()[1]` | `int[].class` |
| `ctor.getDeclaringClass()` | `Api.class` |
| `ctor.isVarArgs()` | `true` |
| `ctor.getReturnType()` | **Không có phương thức này trên Constructor** |

Với `Constructor.newInstance(Object... initargs)`, lời gọi phản chiếu cũng phải cung cấp đối số mảng cho formal parameter varargs:

~~~java
Api instance = ctor.newInstance("demo", new int[] {1, 2, 3});
~~~

Nếu là constructor của inner class không static, đừng quên đối số enclosing instance ngầm mà reflection thấy trong chữ ký. Những trường hợp record compact constructor hoặc parameter do compiler thêm cũng cần được kiểm chứng trên `getParameterTypes()` thực tế thay vì suy đoán từ source.

## 8. Ví dụ hoàn chỉnh: mô tả chữ ký và gọi bằng reflection

Tạo một file duy nhất `ReflectionCallContractsDemo.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class ReflectionCallContractsDemo {

    public static class Parent {
        public String category() {
            return "parent";
        }

        public String inheritedOnly() {
            return "inherited";
        }
    }

    public static class Child extends Parent {
        @Override
        public String category() {
            return "child";
        }
    }

    public static class Api {
        public Api(String label, int... flags) {
            // Constructor có formal parameter cuối là int[].
        }

        public static String format(String prefix, int count) {
            return prefix.repeat(count);
        }

        public static String join(String... parts) {
            return String.join("|", parts);
        }

        public static String joinArray(String[] parts) {
            return String.join("|", parts);
        }

        public static List<String> copy(List<String> values) {
            return List.copyOf(values);
        }

        public static void touch() {
        }
    }

    static String parameters(Executable executable) {
        return Arrays.stream(executable.getParameterTypes())
                .map(Class::getTypeName)
                .collect(Collectors.joining(", ", "(", ")"));
    }

    static void printMethod(Method method) {
        System.out.printf(
                "%s#%s%s -> %s; varArgs=%s%n",
                method.getDeclaringClass().getSimpleName(),
                method.getName(),
                parameters(method),
                method.getReturnType().getTypeName(),
                method.isVarArgs());
    }

    static void printConstructor(Constructor<?> constructor) {
        System.out.printf(
                "new %s%s; varArgs=%s%n",
                constructor.getDeclaringClass().getSimpleName(),
                parameters(constructor),
                constructor.isVarArgs());
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Method format = Api.class.getMethod(
                "format", String.class, int.class);
        Method join = Api.class.getMethod(
                "join", String[].class);
        Method joinArray = Api.class.getMethod(
                "joinArray", String[].class);
        Method copy = Api.class.getMethod(
                "copy", List.class);
        Method touch = Api.class.getMethod("touch");
        Constructor<Api> constructor = Api.class.getConstructor(
                String.class, int[].class);

        printMethod(format);
        printMethod(join);
        printMethod(joinArray);
        printMethod(copy);
        printMethod(touch);
        printConstructor(constructor);

        Method inherited = Child.class.getMethod("inheritedOnly");
        System.out.println("inherited owner: "
                + inherited.getDeclaringClass().getSimpleName());

        Method base = Parent.class.getMethod("category");
        System.out.println("dynamic dispatch: "
                + base.invoke(new Child()));

        System.out.println("generic parameter: "
                + copy.getGenericParameterTypes()[0].getTypeName());
        System.out.println("generic return: "
                + copy.getGenericReturnType().getTypeName());

        System.out.println("join invoke: "
                + join.invoke(null, (Object) new String[] {"a", "b"}));

        try {
            join.invoke(null, "a", "b");
        } catch (IllegalArgumentException ex) {
            System.out.println("wrong arity detected");
        }

        Api object = constructor.newInstance(
                "tag", new int[] {1, 2});
        System.out.println("constructed: "
                + (object != null));
    }
}
~~~

Chạy:

~~~bash
javac ReflectionCallContractsDemo.java
java ReflectionCallContractsDemo
~~~

Đầu ra dự kiến:

~~~text
Api#format(java.lang.String, int) -> java.lang.String; varArgs=false
Api#join(java.lang.String[]) -> java.lang.String; varArgs=true
Api#joinArray(java.lang.String[]) -> java.lang.String; varArgs=false
Api#copy(java.util.List) -> java.util.List; varArgs=false
Api#touch() -> void; varArgs=false
new Api(java.lang.String, int[]); varArgs=true
inherited owner: Parent
dynamic dispatch: child
generic parameter: java.util.List<java.lang.String>
generic return: java.util.List<java.lang.String>
join invoke: a|b
wrong arity detected
constructed: true
~~~

Đây là ví dụ kiểm chứng bằng Java SE API ổn định; nó không yêu cầu preview feature, JVM flag đặc biệt hoặc quyền truy cập vào các lớp nội bộ của JDK.

### 8.1. Đọc đầu ra theo bốn hợp đồng

- `Api#join(java.lang.String[])` và `Api#joinArray(java.lang.String[])` có **cùng kiểu tham số**, nhưng `isVarArgs()` khác.
- `Api#touch() -> void` dùng `getReturnType() == void.class`, chứ không tạo một giá trị return object có kiểu `Void`.
- `Child.class.getMethod("inheritedOnly")` tìm được public method kế thừa, nhưng owner thực sự là `Parent`.
- `Parent.class.getMethod("category").invoke(new Child())` trả `child` do dynamic dispatch; owner của `Method` vẫn là `Parent`.
- `List<String>` trở thành `List.class` ở mảng `getParameterTypes()` và ở `getReturnType()`, nhưng metadata generic còn có thể đọc qua `Type`.
- Với `join.invoke`, mảng `String[]` là **một đối số** của method mục tiêu; đưa hai `String` rời làm phát sinh `IllegalArgumentException`.

## 9. Thiết kế hàm mô tả lời gọi có tính đến varargs

Nếu chỉ gọi `getParameterTypes()` rồi in `Class.getTypeName()`, phần cuối của varargs sẽ hiện `java.lang.String[]` chứ không phải `java.lang.String...`. Về kiểu runtime điều đó đúng, nhưng một công cụ hiển thị chữ ký Java dễ đọc có thể muốn khôi phục dấu `...` từ cờ `isVarArgs()`.

Một hàm mô tả:

~~~java
import java.lang.reflect.Executable;
import java.lang.reflect.Method;

public final class SignatureRenderer {

    public static String describe(Method method) {
        Class<?>[] types = method.getParameterTypes();
        StringBuilder signature = new StringBuilder();

        signature.append(method.getDeclaringClass().getTypeName())
                .append('#')
                .append(method.getName())
                .append('(');

        for (int i = 0; i < types.length; i++) {
            if (i > 0) {
                signature.append(", ");
            }

            Class<?> type = types[i];
            if (method.isVarArgs() && i == types.length - 1) {
                // Tham số cuối của varargs có kiểu mảng.
                signature.append(type.getComponentType().getTypeName())
                        .append("...");
            } else {
                signature.append(type.getTypeName());
            }
        }

        signature.append(") -> ")
                .append(method.getReturnType().getTypeName());

        return signature.toString();
    }
}
~~~

Ví dụ, với `join(String... parts)`, output của renderer có dạng:

~~~text
ReflectionCallContractsDemo$Api#join(java.lang.String...) -> java.lang.String
~~~

Trong hàm này:

- `getDeclaringClass()` cung cấp owner.
- `getName()` cung cấp tên method.
- `getParameterTypes()` cung cấp thứ tự và các kiểu sau erasure.
- `isVarArgs()` quyết định khi nào đổi biểu diễn tham số cuối từ `T[]` sang `T...`.
- `getReturnType()` cung cấp kiểu trả về.

Với constructor, có thể tái sử dụng phần dựng danh sách tham số qua `Executable`, nhưng **không** gọi `getReturnType()` trên constructor. Có thể trình bày bằng `new Owner(...)` hoặc tên constructor tùy nhu cầu UI.

### 9.1. Mục đích của hàm renderer

Hàm trên phục vụ **hiển thị chữ ký sơ bộ**, không phải một định dạng canonical của JVM hay bộ phân giải overload hoàn chỉnh. Nó không mô tả generic type arguments, annotations, receiver, throws clause, method type parameters hoặc synthetic/bridge metadata. Khi cần chữ ký giàu thông tin hơn:

- `Method.toGenericString()` mô tả method gồm cả type parameters.
- `Executable.getGenericParameterTypes()` và `Method.getGenericReturnType()` mô tả generic dưới dạng `Type`.
- `Method.isBridge()`, `isSynthetic()` giúp phát hiện method do compiler tạo.
- `getModifiers()` và `Modifier` giúp kiểm tra `public`, `static`, `abstract`.
- `getExceptionTypes()` và `getGenericExceptionTypes()` mô tả `throws`.

Không nên tự đưa toàn bộ các phương thức này vào cùng một renderer nếu mục tiêu chỉ là trả lời bốn câu hỏi cốt lõi.

## 10. Từ metadata đến lời gọi: ranh giới cần nhớ

Bốn API trong bài trả về **thông tin khai báo của executable**. Chúng không tự thực hiện các công đoạn kiểm tra quyền truy cập, chuyển đổi đối số hoặc tìm method body cuối cùng của một lần gọi.

### 10.1. Metadata không thay thế kiểm tra truy cập

~~~java
Method method = SomeClass.class.getDeclaredMethod("hidden");
Class<?> owner = method.getDeclaringClass();
Class<?> resultType = method.getReturnType();
~~~

Có thể đọc metadata của một method không public thông qua `getDeclaredMethod` trong một số bối cảnh, nhưng điều đó không đảm bảo bạn có thể `invoke` nó. Quyền truy cập còn phụ thuộc modifier, module exports/opens, caller và các quy tắc reflection hiện hành.

Khi cần kiểm tra quyền của một reflective object, `canAccess(receiver)` và `trySetAccessible()` là các API công khai cần cân nhắc theo đúng nhu cầu và chính sách module; **không sử dụng các thủ thuật sửa field nội bộ của `Method` hoặc phá encapsulation**. Trên JDK hiện đại, các cách dựa vào chi tiết triển khai đã lỗi thời và không được bảo đảm.

### 10.2. Reflection không tự giải quyết overload từ giá trị runtime

Một dispatcher nhận tên `"send"` và object `Integer.valueOf(3)` không thể chỉ gọi `getMethod("send", Integer.class)` rồi kỳ vọng tự tìm `send(int)`. `Class.getMethod` tra cứu các formal parameter types chính xác, trong khi một lời gọi Java thông thường có thể áp dụng unboxing hoặc overload resolution ở compile time.

Hãy xây dựng chiến lược chọn overload rõ ràng:

1. Liệt kê candidates theo tên method và số formal parameters.
2. So sánh `getParameterTypes()` với các kiểu đối số và các conversion được phép.
3. Xử lý `isVarArgs()` như một trường hợp riêng nếu hỗ trợ lời gọi biến độ dài.
4. Kiểm tra accessibility.
5. Chỉ sau đó mới gọi `Method.invoke` với đúng số actual arguments tương ứng với formal parameters.

Đừng viết một “overload resolver” chỉ bằng `getMethod(name, args.getClass())` rồi coi nó tương đương trình biên dịch Java.

### 10.3. Cẩn trọng với method do compiler sinh

Khi duyệt `getDeclaredMethods()`, một class có thể có compiler-generated methods, trong đó có bridge methods để hỗ trợ generics và covariant return.

~~~java
for (Method method : SomeClass.class.getDeclaredMethods()) {
    if (method.isBridge() || method.isSynthetic()) {
        continue; // Khi mục tiêu là chỉ mô tả API do lập trình viên khai báo.
    }
    System.out.println(method.toGenericString());
}
~~~

Việc lọc hay giữ bridge methods phụ thuộc mục tiêu. Công cụ phân tích bytecode có thể cần chúng; công cụ trình bày API cho con người thường muốn tránh nhân đôi các method tương đương. **Không phụ thuộc thứ tự do `getMethods()` hoặc `getDeclaredMethods()` trả về**; khi cần đầu ra ổn định, hãy tự sắp xếp.

## 11. Bảng phân biệt các khái niệm thường nhầm

| Câu hỏi | Cần dùng | Không được nhầm với |
| --- | --- | --- |
| Method nhận những formal parameter types nào? | `getParameterTypes()` | Kiểu thực tế của đối số trong một lần gọi |
| Bao nhiêu formal parameters? | `getParameterCount()` hoặc độ dài mảng kiểu | Số đối số viết ở lời gọi Java varargs |
| Có type arguments generic nào? | `getGenericParameterTypes()` | `Class<?>[]` sau type erasure |
| Method khai báo trả về kiểu gì? | `Method.getReturnType()` | Kiểu runtime của object return |
| Chữ ký generic trả về kiểu gì? | `getGenericReturnType()` | `getReturnType()` sau erasure |
| Ai khai báo method? | `Method.getDeclaringClass()` | Class dùng để tìm method hoặc kiểu của receiver |
| Method là varargs? | `isVarArgs()` | Chỉ xét tham số cuối có `isArray()` hay không |
| Constructor nhận tham số nào? | `Constructor.getParameterTypes()` | `Method.getReturnType()` (constructor không có) |
| Có thể gọi method thành công? | Kiểm tra access, receiver, args và `invoke` | Chỉ đọc bốn metadata methods |
| Method có bị override khi gọi? | Quy tắc dynamic dispatch của Java | `getDeclaringClass()` đơn thuần |

## 12. Các lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Kỳ vọng `getParameterTypes()` trả `List<String>`. | Trả về `Class<?>[]` sau erasure. | Dùng `getGenericParameterTypes()` để xem generic `Type`. |
| Gọi `getReturnType()` trên `Executable` hoặc `Constructor`. | API này chỉ nằm trên `Method`. | Phân nhánh `instanceof Method`. |
| Nhầm return type `void` với `Void.class`. | `void` được biểu diễn bằng `void.class`. | So sánh với `void.class`; `invoke` của method void trả `null`. |
| Dùng `Child.class` làm owner của method kế thừa. | Declaring class có thể là superclass/interface. | Đọc `getDeclaringClass()` của `Method` được tìm thấy. |
| Nghĩ `getDeclaringClass()` dự báo body khi invoke. | Method instance có dynamic dispatch theo receiver. | Phân biệt owner metadata và dispatch runtime. |
| Nhận diện varargs bằng `lastType.isArray()`. | Method thường cũng có thể nhận mảng. | Dùng `isVarArgs()`. |
| Gọi `getMethod("join", String.class)` cho `join(String...)`. | Formal parameter là `String[]`. | Truyền `String[].class` khi tra cứu. |
| Gọi `join.invoke(null, "a", "b")`. | `Method.invoke` không tự gom hai đối số vào array của target. | Dùng `join.invoke(null, (Object) new String[] {"a", "b"})`. |
| Tra overload primitive bằng wrapper class. | `int.class` và `Integer.class` khác nhau. | Tìm theo formal parameter đã khai báo. |
| Dựa vào thứ tự của `getMethods()`. | Thứ tự không được bảo đảm. | Tự sắp xếp khi cần output deterministic. |
| Đếm constructor parameter từ source và bỏ qua implicit parameter. | Một số constructor có tham số compiler đưa vào. | Kiểm tra metadata thực tế của `Constructor`. |
| Cho rằng đọc metadata đồng nghĩa được gọi private method. | Access control và module boundaries khác bước đọc signature. | Kiểm tra quyền truy cập, không phá encapsulation. |

## 13. Checklist kiểm chứng trên JDK đang dùng

Sau khi chạy file ví dụ ở mục 8:

1. `getParameterTypes()` của `format` phải trả hai kiểu theo thứ tự `String.class` và `int.class`.
2. `getReturnType()` của `format` phải là `String.class`; của `touch` phải là `void.class`.
3. `getDeclaringClass()` của `inheritedOnly` tìm qua `Child.class` phải là `Parent.class`.
4. `isVarArgs()` của `join(String...)` phải là `true`, còn `joinArray(String[])` phải là `false`.
5. `getParameterTypes()` của hai method đó đều phải chứa `String[].class`.
6. `getParameterTypes()` của `copy(List<String>)` phải chứa `List.class`, trong khi `getGenericParameterTypes()` cho thông tin `List<String>`.
7. `join.invoke(null, (Object) new String[] {"a", "b"})` phải thành công; gọi phản chiếu với hai actual arguments `"a", "b"` phải bị từ chối do số tham số không khớp.
8. `Constructor<Api>` phải có danh sách formal parameters `String.class`, `int[].class` và `isVarArgs()==true`.
9. `base.invoke(new Child())` phải cho kết quả của override trên `Child`; `base.getDeclaringClass()` vẫn là `Parent.class`.
10. Mô tả chữ ký không được phụ thuộc vào thứ tự phương thức được phản chiếu từ một mảng `Method[]`.

Có thể bật kiểm tra bằng assertion khi tự mở rộng ví dụ:

~~~java
assert Api.class.getMethod("join", String[].class).isVarArgs();
assert !Api.class.getMethod("joinArray", String[].class).isVarArgs();
assert Api.class.getMethod("touch").getReturnType() == void.class;
~~~

Vì `Class.getMethod` ném checked exception, ba assertion trên nên đặt trong method có `throws ReflectiveOperationException` (như `main` ở mục 8). Chạy với `java -ea ReflectionCallContractsDemo` để bật assertion; nếu không có `-ea`, Java thường bỏ qua biểu thức `assert`.

## 14. Bài tập tự đánh giá

### Bài 1 — Chữ ký có overload

Cho:

~~~java
public static void save(String value) { }
public static void save(int value) { }
~~~

Làm thế nào tra cứu đúng overload thứ hai?

**Đáp án:**

~~~java
Method method = Api.class.getMethod("save", int.class);
~~~

`int.class` khác `Integer.class`. `getParameterTypes()[0] == int.class`.

### Bài 2 — Array hay varargs?

Cho:

~~~java
public static void render(String[] items) { }
public static void print(String... items) { }
~~~

Cả hai có formal parameter type `String[].class`. Làm sao nhận diện method có varargs?

**Đáp án:** Dùng `isVarArgs()`: `render` trả `false`, `print` trả `true`.

### Bài 3 — Kiểu trả về là void

Cho `public static void refresh() { }`. `getReturnType()` có phải `Void.class` không?

**Đáp án:** Không. Kết quả là `void.class`. Nếu gọi bằng `Method.invoke` thành công, giá trị trả về ở API reflection là `null`.

### Bài 4 — Lớp khai báo hay lớp kế thừa?

`Base` khai báo public `run()`, `Derived extends Base` không override. Tìm `Derived.class.getMethod("run")`. `getDeclaringClass()` trả gì?

**Đáp án:** `Base.class`, bởi method được khai báo tại `Base`.

### Bài 5 — Dynamic dispatch

`Base` khai báo `String run()`, `Derived` override. `Method base = Base.class.getMethod("run")`, sau đó `base.invoke(new Derived())`. `base.getDeclaringClass()` có đổi thành `Derived.class` không?

**Đáp án:** Không. Metadata của `Method` vẫn là `Base.class`. Lời gọi instance có thể chạy override của `Derived` do dynamic dispatch.

### Bài 6 — Generic parameter types

Method nhận `List<String>`. Vì sao `getParameterTypes()[0]` là `List.class`?

**Đáp án:** Vì type erasure. Dùng `getGenericParameterTypes()` nếu cần mô tả type arguments còn được lưu trong metadata generic.

### Bài 7 — Reflective invocation varargs

Có `public static String merge(String... parts)`. Câu lệnh nào đúng?

~~~java
Method merge = Api.class.getMethod("merge", String[].class);
~~~

**Đáp án:**

~~~java
Object result = merge.invoke(null, (Object) new String[] {"x", "y"});
~~~

Phải cung cấp một actual argument kiểu `String[]` cho target. `merge.invoke(null, "x", "y")` không tự đóng gói hai string thành một mảng cho method đích.

### Bài 8 — Constructor và return type

`Constructor<?> ctor = Api.class.getConstructor(String.class)`. Có thể gọi `ctor.getReturnType()` không?

**Đáp án:** Không. Constructor có `getParameterTypes()`, `getDeclaringClass()`, `isVarArgs()` và `newInstance()`, nhưng không có `getReturnType()`. Dùng `ctor.getDeclaringClass()` nếu cần biết class được constructor khai báo.

## Tổng kết

- `getParameterTypes()` trả các `Class<?>` của formal parameters **theo thứ tự khai báo**; đây là kiểu sau erasure, không phải generic signature đầy đủ.
- `Method.getReturnType()` mô tả return type khai báo, gồm `void.class` cho `void`. Constructor không có API này.
- `getDeclaringClass()` cho biết nơi khai báo member, không nhất thiết là class đã dùng để tìm method hoặc class runtime của receiver.
- `isVarArgs()` là cờ khai báo `...`; phương thức nhận `T[]` bình thường không tự động là varargs.
- Reflection mô tả một method varargs với tham số cuối kiểu array. Khi dùng `Method.invoke`, caller phải truyền đúng một mảng như actual argument tương ứng, không được dựa vào automatic packaging của target.
- `getGenericParameterTypes()` và `getGenericReturnType()` hỗ trợ mô tả generic; `isBridge()`, `isSynthetic()` và `getModifiers()` giúp công cụ phân tích chữ ký nâng cao.
- Metadata không thay thế kiểm tra quyền truy cập, overload resolution, dynamic dispatch và việc kiểm thử hành vi chương trình.
- Các hợp đồng public Core Reflection tiếp tục hữu ích trên JDK hiện đại; không phụ thuộc những chi tiết triển khai Reflection cũ từ trước JEP 416.

## Nguồn tham khảo chính thức

1. [Oracle — Method, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Method.html): `getReturnType()`, `getParameterTypes()`, `getDeclaringClass()`, `isVarArgs()`, `invoke()`, `isBridge()`.
2. [Oracle — Executable, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Executable.html): hợp đồng chung về formal parameter types, parameter count, generic types, varargs và implicit parameters.
3. [Oracle — Constructor, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Constructor.html): metadata constructor và `newInstance()`; phân biệt với return type của Method.
4. [Oracle — Class, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): `getMethod()`, `getDeclaredMethod()`, `getMethods()` và `getDeclaredMethods()`.
5. [Oracle — The Java Language Specification, Java SE 26, §4.6 Type Erasure](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-4.html#jls-4.6): phân biệt `Class<?>` sau erasure với generic metadata.
6. [OpenJDK — JEP 416: Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi triển khai Core Reflection trong Java 18, giữ định hướng sử dụng các hợp đồng API công khai.

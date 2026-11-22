# Method.invoke với receiver và mảng đối số trong Java Reflection

## 1. Nắm đúng hai tham số của Method.invoke

Java Reflection cho phép gọi một phương thức được tìm ở runtime thông qua `java.lang.reflect.Method`. Chữ ký API:

```java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException
```

Ý nghĩa:

- `Method` đã xác định **phương thức đích**: khai báo, tên, kiểu tham số. `invoke` không tự chọn overload dựa trên runtime class của từng đối số.
- `obj` là **receiver**, đối tượng thực thi instance method. Với static method, receiver bị bỏ qua, truyền `null` thường là cách rõ ràng nhất.
- `args` là danh sách đối số thực sự của method đích, ở dạng một mảng `Object[]`. Mỗi phần tử của mảng phải tương ứng **một formal parameter** theo đúng thứ tự, kể cả khi formal parameter đó chính nó là một array.
- `invoke` trả về `Object`: primitive được boxing; `void` trả `null`; reference/array được giữ nguyên kiểu đối tượng. Method đích ném exception sẽ được bọc trong `InvocationTargetException`.

Ví dụ, method đích `int add(int a, long b)` cần hai phần tử trong `args`; method đích `void print(String[] names)` chỉ cần một phần tử, chính là một `String[]`.

Điểm gây nhầm phổ biến nhất: **`Method.invoke` có cú pháp `Object... args`, còn method đích có thể cũng khai báo `String... values`. Đó là hai tầng varargs khác nhau**, cần phân biệt rõ.

## 2. Receiver cho instance method và static method

### Instance method cần receiver tương thích

Giả sử có lớp:

```java
class Greeter {
    public String hello(String name) {
        return "Hi, " + name;
    }
}
```

Trong một phương thức có xử lý ngoại lệ Reflection:

```java
Method hello = Greeter.class.getMethod("hello", String.class);
Greeter greeter = new Greeter();
Object answer = hello.invoke(greeter, "Mai"); // "Hi, Mai"
```

Receiver phải là một instance phù hợp với lớp hoặc interface khai báo underlying method. `hello.invoke(null, "Mai")` ném `NullPointerException`; `hello.invoke(new Object(), "Mai")` ném `IllegalArgumentException`. Những lỗi này khác lỗi trả về từ body `hello`.

Với **instance method bị override**, Reflection vẫn thực hiện dynamic method lookup theo runtime class của receiver. Một `Method` lấy từ lớp cha có thể thực thi implementation override của lớp con. `Method.getDeclaringClass()` vẫn mô tả lớp chứa khai báo ban đầu, không tự đổi thành runtime class của receiver.

### Static method bỏ qua receiver

```java
class Settings {
    public static String status() { return "READY"; }
}
```

```java
Method status = Settings.class.getMethod("status");
Object a = status.invoke(null);         // "READY"
Object b = status.invoke(new Object()); // "READY"
```

Đây là các đoạn minh họa, có import `java.lang.reflect.Method` và xử lý ngoại lệ trong phương thức chứa chúng. Receiver `new Object()` không thuộc `Settings` nhưng **không bị kiểm tra về tính tương thích**, bởi static method không chạy trên object đó. Static method có thể khiến declaring class **được khởi tạo** lần đầu khi `invoke`, nên việc gọi Reflection có thể chạy static initializer.

Cần phân biệt bỏ qua **giá trị** receiver với bỏ qua **đánh giá biểu thức** receiver: trong `status.invoke(buildReceiver())`, Java vẫn chạy `buildReceiver()` trước lời gọi, sau đó Reflection bỏ qua giá trị trả về đối với static method.

Cách chọn receiver có chủ ý:

```java
Object target = Modifier.isStatic(method.getModifiers()) ? null : instance;
Object result = method.invoke(target, arguments);
```

Đây là mảnh mã, không phải chương trình hoàn chỉnh; cần có các biến `method`, `instance`, `arguments` và import `Modifier`. Khi `method` là instance, `instance` phải đúng kiểu; với static, truyền `null` diễn đạt rõ rằng không cần một đối tượng.

| Loại method | Receiver | Hành vi |
| --- | --- | --- |
| Instance | Đối tượng đúng kiểu hoặc subtype | Có thể gọi override trên runtime class |
| Instance | `null` | `NullPointerException` |
| Instance | Đối tượng không tương thích | `IllegalArgumentException` |
| Static | `null` | Hợp lệ |
| Static | Bất kỳ object, kể cả không liên quan | Giá trị receiver bị bỏ qua |

Bảng giả định quyền truy cập, các đối số khác và class initialization không gây lỗi.

## 3. Mảng Object[] của Reflection là danh sách đối số, không phải nội dung array

Với method `add(int a, long b)`, hai cách truyền tương đương:

```java
addMethod.invoke(service, 2, 5);
addMethod.invoke(service, new Object[]{2, 5});
```

Hai formal parameters nghĩa là **hai** phần tử trong `Object[]`. Khi formal parameter là array như `String[] names`, phải bọc chính array này vào một **phần tử duy nhất** của danh sách:

```java
Method join = Service.class.getMethod("join", String[].class);
Object result = join.invoke(service, new Object[]{new String[]{"a", "b"}});
```

Ở đây `join` có một formal parameter `String[]`, vì vậy `Object[]` bên ngoài có đúng một phần tử, còn `String[]` bên trong có hai phần tử. Điều này đúng dù method khai báo `join(String[] values)` hay `join(String... values)`: trong metadata, cả hai có formal parameter type `String[].class`. `join.isVarArgs()` cho biết khai báo có cờ varargs hay không, nhưng **`Method.invoke` không tự gom phần tử `String` thành mảng cho method đích**.

**Tra cứu method phải khớp chính xác signature**:

```java
Method m = Service.class.getMethod("join", String[].class);
Class<?>[] formalTypes = m.getParameterTypes();
int count = m.getParameterCount(); // 1
```

`getMethod` và `getDeclaredMethod` nhận danh sách `Class<?>` của formal parameters, không phải danh sách wrapper runtime values, và không tự chọn overload theo widening. Chẳng hạn để tìm `f(long)` phải dùng `getMethod("f", long.class)`; `getMethod("f", int.class)` không tìm ra chỉ vì `int` có thể widen sang `long` khi gọi.

## 4. Chương trình Java 17+ có thể chạy đầy đủ

Lưu chương trình sau vào **`InvokeReceiverDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class InvokeReceiverDemo {
    public static class Service {
        public String greet(String name) { return "Hello, " + name; }
        public int add(int a, long b) { return (int) (a + b); }
        public String join(String... values) { return String.join("/", values); }
        public static String label(int number) { return "ID=" + number; }
        public void noResult() { }
        public void boom() { throw new IllegalStateException("failed"); }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Service service = new Service();
        Method greet = Service.class.getMethod("greet", String.class);
        Method label = Service.class.getMethod("label", int.class);
        Method add = Service.class.getMethod("add", int.class, long.class);
        Method join = Service.class.getMethod("join", String[].class);
        Method noResult = Service.class.getMethod("noResult");
        Method boom = Service.class.getMethod("boom");

        System.out.println("instance = " + greet.invoke(service, "Ana"));
        System.out.println("static null = " + label.invoke(null, 7));
        System.out.println("static unrelated = " + label.invoke(new Object(), 7));

        Object result = add.invoke(service, Integer.valueOf(2), Integer.valueOf(5));
        System.out.println("widen = " + result + " (" +
                result.getClass().getSimpleName() + ")");
        System.out.println("isVarArgs = " + join.isVarArgs());
        System.out.println("join cast = " +
                join.invoke(service, (Object) new String[] {"a", "b"}));
        System.out.println("join wrapped = " +
                join.invoke(service, new Object[] {new String[] {"x", "y"}}));
        System.out.println("void returns null = " + (noResult.invoke(service) == null));

        try { greet.invoke(null, "Ana"); }
        catch (NullPointerException e) {
            System.out.println("null receiver = NullPointerException");
        }
        try { greet.invoke(new Object(), "Ana"); }
        catch (IllegalArgumentException e) {
            System.out.println("wrong receiver = IllegalArgumentException");
        }
        try { greet.invoke(service); }
        catch (IllegalArgumentException e) {
            System.out.println("wrong arity = IllegalArgumentException");
        }
        try { join.invoke(service, (Object[]) new String[] {"a", "b"}); }
        catch (IllegalArgumentException e) {
            System.out.println("spread array = IllegalArgumentException");
        }
        try { add.invoke(service, Long.valueOf(2), Integer.valueOf(5)); }
        catch (IllegalArgumentException e) {
            System.out.println("narrowing = IllegalArgumentException");
        }
        try { boom.invoke(service); }
        catch (InvocationTargetException e) {
            System.out.println("target cause = " +
                    e.getCause().getClass().getSimpleName() + ": " +
                    e.getCause().getMessage());
        }
    }
}
```

Dùng JDK 17 trở lên:

```bash
javac InvokeReceiverDemo.java
java InvokeReceiverDemo
```

Stdout đã được chạy và xác minh trên JDK 24:

```text
instance = Hello, Ana
static null = ID=7
static unrelated = ID=7
widen = 7 (Integer)
isVarArgs = true
join cast = a/b
join wrapped = x/y
void returns null = true
null receiver = NullPointerException
wrong receiver = IllegalArgumentException
wrong arity = IllegalArgumentException
spread array = IllegalArgumentException
narrowing = IllegalArgumentException
target cause = IllegalStateException: failed
```

Giải thích:

1. `greet` là instance method nên phải có receiver `service` đúng kiểu.
2. `label` là static method nên cả receiver `null` lẫn `new Object()` đều bị bỏ qua. Đây **không** là hành vi đúng cho instance method.
3. `add` khai báo `(int, long)`. `Integer(2)` được unbox thành `int`, `Integer(5)` unbox rồi widen từ `int` lên `long`. Kết quả `int` được boxing thành `Integer`.
4. `join` có `isVarArgs() == true` và signature chỉ nhận **một `String[]`**; hai cách gọi thành công đều truyền mảng chuỗi thành **một argument**.
5. `noResult` khai báo `void`; giá trị trả về từ Reflection là `null`.
6. Các lỗi receiver `null`, sai lớp, sai số lượng args, dùng array bị bung, hoặc chuyển `Long` sang `int` đều biểu hiện bằng loại ngoại lệ đã in.
7. `boom` ném `IllegalStateException` bên trong body; mã gọi Reflection nhận `InvocationTargetException` và lấy nguyên nhân từ `getCause()`.

## 5. Phân biệt hai tầng varargs, kể cả các dạng null

### Array của method đích phải nằm trong một ô của Object[]

Với `join(String... values)`, runtime formal parameter là `String[]`:

```java
join.invoke(service, (Object) new String[]{"a", "b"});       // đúng
join.invoke(service, new Object[]{new String[]{"a", "b"}});   // đúng
join.invoke(service, (Object[]) new String[]{"a", "b"});     // sai arity
```

Cast `(Object)` trong dòng thứ nhất ép Java coi array `String[]` là **một argument** của API `invoke`, nhờ đó tạo danh sách `Object[]` có một phần tử. Dòng thứ hai tự xây danh sách có một phần tử. Dòng thứ ba cast cả `String[]` thành `Object[]` của `invoke` (hợp lệ vì `String[]` là subtype `Object[]`) và do đó bung **hai chuỗi** thành **hai formal arguments**; `join` yêu cầu chỉ một `String[]`, dẫn tới `IllegalArgumentException`.

Viết `join.invoke(service, new String[]{"a","b"})` không có cast cũng dễ gây compiler warning “non-varargs call for last parameter” và trải array theo tầng ngoài. Với code framework cần ổn định và dễ đọc, nên luôn xây `new Object[]{...}` hoặc cast array sang `Object`.

Với `int[]`, đừng cố ép `int[]` sang `Object[]`: mảng primitive không phải subtype của `Object[]`. Ví dụ method `sum(int[] numbers)` phải nhận:

```java
sumMethod.invoke(receiver, new Object[]{new int[]{1, 2, 3}});
```

Đây là mảnh minh họa, với `sumMethod` là metadata của method nhận `int[]`. Reflection không tự biến `Integer[]` thành `int[]` hay tự unbox từng phần tử trong array.

### null receiver, null danh sách và một null argument

Các lệnh sau có ngữ nghĩa khác nhau (biến `greet`, `noResult`, `service` lấy từ ví dụ chính):

| Lời gọi | Ý nghĩa |
| --- | --- |
| `noResult.invoke(service)` | Không có argument; đúng vì method đích không tham số |
| `noResult.invoke(service, new Object[0])` | Danh sách rỗng; hợp lệ |
| `noResult.invoke(service, (Object[]) null)` | Mảng args là `null`, hợp lệ khi method đích không tham số |
| `greet.invoke(service, (Object) null)` | Một argument có giá trị `null`; body trả `"Hello, null"` |
| `greet.invoke(service, new Object[]{null})` | Tương tự: một argument `null` |
| `greet.invoke(service, (Object[]) null)` | Danh sách có 0 argument, trong khi method cần 1: `IllegalArgumentException` |
| `greet.invoke(null, "Ana")` | Receiver `null` của instance method: `NullPointerException` |

`invoke(service, null)` không cast có thể gây compiler warning hoặc được hiểu theo dạng varargs không mong muốn. Viết rõ `(Object) null` để truyền **một argument null** hoặc `new Object[0]`/`(Object[]) null` để truyền **không argument**. Nếu formal parameter là primitive (`int`, `boolean`...), một giá trị `null` không thể unbox và bị từ chối.

**Lưu ý:** khi mảng `args` của `Method.invoke` là `null` và method đích không có formal parameters, API chấp nhận điều này; không suy ra rằng mọi method có thể được gọi với danh sách `null`.

## 6. Chuyển đổi đối số và trả về

### Method invocation conversions

Java kiểm tra số lượng args và tương thích kiểu tại lời gọi `invoke`:

- Reference parameter nhận `null` hoặc reference subtype phù hợp (ví dụ `String` cho `CharSequence`).
- Primitive parameter nhận wrapper thích hợp được unbox; các chuyển đổi **widening primitive** như `int` sang `long` được phép.
- **Narrowing primitive** như `long` sang `int` không tự diễn ra. Một `String` chứa chữ số không được tự parse thành `int`.
- Các chuyển đổi áp dụng **cho mỗi phần tử `Object[]`**, không tự lan vào phần tử của một array formal parameter.

Ví dụ:

```java
Method m = Service.class.getMethod("add", int.class, long.class);
m.invoke(service, Integer.valueOf(2), Integer.valueOf(5)); // OK
m.invoke(service, Long.valueOf(2), Integer.valueOf(5));    // IllegalArgumentException
m.invoke(service, (Object) null, Integer.valueOf(5));       // IllegalArgumentException
```

Đây là mảnh code minh họa, không phải chương trình chạy độc lập. Method đích `add` không được chọn lại để khớp `Long`; `Method` đã được tra cứu theo signature `(int,long)`.

### Giá trị trả về

| Return type của method đích | Giá trị `invoke` trả |
| --- | --- |
| `String` hoặc reference type | Reference kết quả, có thể `null` |
| `int`, `long` hoặc primitive khác | Wrapper như `Integer`, `Long` |
| `void` | `null` |
| `int[]` hoặc array khác | Chính array, không boxing từng phần tử |

`method.getReturnType()` mô tả kiểu khai báo. `result.getClass()` chỉ mô tả runtime class nếu kết quả khác `null`; không phân biệt được `void` với method reference trả `null`. Với generic, `getGenericReturnType()` xem được generic signature khi metadata có sẵn; runtime invoke không kiểm tra mọi type argument đã bị erasure.

## 7. Exception: lỗi gọi sai khác lỗi bên trong method

Theo Javadoc Java 17 của `Method.invoke`:

| Lỗi | Nguyên nhân điển hình |
| --- | --- |
| `NoSuchMethodException` | Xảy ra khi `getMethod`/`getDeclaredMethod` không tìm thấy đúng chữ ký; đây là lỗi **tra cứu**, trước khi invoke |
| `IllegalAccessException` | Caller không có quyền gọi underlying method theo Java access control |
| `NullPointerException` | Receiver `null` khi underlying method là instance |
| `IllegalArgumentException` | Receiver không đúng kiểu, sai số formal/actual args hoặc một argument không chuyển đổi được sang formal type |
| `InvocationTargetException` | Method đích đã chạy và ném exception/error; đọc `getCause()` |
| `ExceptionInInitializerError` | Khởi tạo declaring class do gọi static method thất bại |
| `InaccessibleObjectException` | Có thể xuất hiện khi yêu cầu deep reflection bằng `setAccessible(true)` không được module cho phép |

Ví dụ pattern xử lý đúng gốc lỗi:

```java
try {
    method.invoke(receiver, arguments);
} catch (InvocationTargetException ex) {
    Throwable underlying = ex.getCause();
    // Xử lý/ghi log ngoại lệ của chính method đích.
} catch (IllegalAccessException ex) {
    // Kiểm tra quyền truy cập của method.
} catch (IllegalArgumentException ex) {
    // Kiểm tra receiver, arity và conversion của args.
}
```

Đây là mảnh code cần ngữ cảnh `method`, `receiver`, `arguments`. Không gộp `InvocationTargetException` thành lỗi “sai tham số Reflection”; nó là **lớp bọc quanh lỗi đã xảy ra bên trong method**. Với ứng dụng thực tế, policy xử lý checked exceptions, unchecked exceptions và `Error` ở tầng framework phải được thiết kế rõ.

### getMethod khác getDeclaredMethod và quyền truy cập

- `getMethod(name, parameterTypes...)` tìm public method theo quy tắc tra cứu, có thể thấy inherited public method.
- `getDeclaredMethod(name, parameterTypes...)` tìm method khai báo **trực tiếp** trong class, bao gồm private, không tự duyệt superclasses.
- Lấy được `Method` private **không đồng nghĩa gọi được**. `Method.invoke` có thể ném `IllegalAccessException`; `trySetAccessible()`/`setAccessible(true)` chỉ có thể nới quyền nếu quy tắc module và runtime cho phép.
- `Method.invoke` trên instance method được override có dynamic dispatch; static method không override theo nghĩa ấy. Việc truyền subtype receiver cho static method không làm chọn một static method bị hiding ở subtype.
- Nếu method đích nằm trong Java module không mở package cho caller, không dựa vào Reflection để vượt encapsulation. Ưu tiên public API hoặc cấu hình `opens` khi thực sự cần.

## 8. Một utility giảm lỗi receiver và kiểm soát signature

Đây là class Java hoàn chỉnh dùng làm helper trong dự án (không có `main`):

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public final class ReflectiveCalls {
    private ReflectiveCalls() {}

    public static Object call(Method method, Object instance, Object[] arguments)
            throws IllegalAccessException, InvocationTargetException {
        Object target = Modifier.isStatic(method.getModifiers())
                ? null
                : instance;
        return method.invoke(target, arguments);
    }
}
```

Helper này chỉ thực hiện lựa chọn receiver rõ nghĩa. Nó **không tự sửa** arity, ép kiểu tùy ý, tra cứu overload, bypass private/module access hay bắt lỗi của method đích. Trước khi dùng, mã gọi cần biết:

1. Method nào đang được yêu cầu và formal parameter types chính xác (`getParameterTypes()`).
2. Method static hay instance (`Modifier.isStatic(getModifiers())`), receiver phải đúng kiểu nếu instance.
3. `Object[]` chứa đúng một phần tử cho mỗi formal parameter, đặc biệt array formal và varargs.
4. Caller có quyền gọi method và liệu static class initialization có tác dụng phụ hay không.
5. Cách xử lý `InvocationTargetException.getCause()` và return value đã được boxing/`null`.

Khi method cần gọi đã biết trước tại compile time, lời gọi Java bình thường thường có type checking rõ ràng hơn. Reflection phù hợp khi tên/kiểu method chỉ biết tại runtime, ví dụ mapper, test runner, plugin framework hoặc dependency injection container.

## 9. Tự kiểm tra

**Câu 1.** `Method m` mô tả `static void run()`. `m.invoke(new Object())` có sai receiver không? **Không**; target bị bỏ qua. Nên dùng `m.invoke(null)` để rõ ràng.

**Câu 2.** Method đích là `void accept(String[] names)`. Có truyền hai chuỗi bằng `m.invoke(receiver, (Object[]) new String[]{"A","B"})` không? **Không**: call này tạo hai actual args `String`, trong khi formal chỉ có một `String[]`. Dùng `m.invoke(receiver, (Object) new String[]{"A","B"})` hoặc `m.invoke(receiver, new Object[]{new String[]{"A","B"}})`.

**Câu 3.** `m` mô tả `void greet(String s)`. `m.invoke(receiver, (Object) null)` truyền gì? **Một `null`**. `m.invoke(receiver, (Object[]) null)` thì sao? **Không có actual args**, thiếu tham số và thất bại.

**Câu 4.** Method trả `long`; `Method.invoke` trả loại gì? **`Object` chứa `Long`** qua boxing. Method trả `void` thì `invoke` trả `null`.

**Câu 5.** Method đích ném `IOException`. Reflection gọi phương thức này sẽ ném thẳng `IOException`? **Không**; `InvocationTargetException` bọc exception gốc, xem `getCause()`.

**Câu 6.** Đã có `Method` của instance method lớp `Base`; receiver là `Derived` override method ấy. Chạy bản nào? **Implementation override trên `Derived`**. Nếu là static method thì không có dynamic override.

**Câu 7.** Tại sao `getMethod("f", int.class)` không tìm được `f(long)` dù `Integer` có thể widen thành `long` khi `invoke`? **Tra cứu dùng formal signature chính xác; chuyển đổi giá trị chỉ diễn ra lúc gọi**.

## 10. Tài liệu chính thức

- [Java SE 17 Javadoc — Method.invoke(Object, Object...)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 Javadoc — Class.getMethod / getDeclaredMethod](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 Javadoc — Executable.isVarArgs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html)
- [Java SE 17 Javadoc — InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [JLS 17, Section 15.12.4: Runtime Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4)

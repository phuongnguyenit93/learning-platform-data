# `IllegalArgumentException` do receiver hoặc đối số không hợp lệ trong Java Reflection

## 1. Bản chất lỗi: thất bại ở bước áp dụng lời gọi phản chiếu

Khi dùng Java Reflection, chương trình thường tìm được một đối tượng `java.lang.reflect.Method`, `Constructor<?>` hoặc `Field` rồi mới thao tác trên object cụ thể. **Tìm thấy metadata không bảo đảm có thể áp dụng thành viên đó cho mọi receiver hoặc mọi danh sách đối số.**

`IllegalArgumentException` là ngoại lệ *unchecked* thường báo rằng lời gọi API reflection được đưa dữ liệu không đúng hợp đồng: receiver không thuộc kiểu được phép, sai số lượng tham số, không thể chuyển kiểu đối số, hoặc giá trị ghi vào field không phù hợp. Lỗi này có thể xuất hiện **trước khi mã của phương thức/constructor đích chạy**.

Ví dụ `Method` đại diện cho `Service.sum(int, long)` chỉ biết phương thức nào cần gọi. Để `Method.invoke` thành công, còn cần receiver là một instance thích hợp của `Service` và **hai đối số** lần lượt tương thích với `int`, `long`.

Quan trọng: **`IllegalArgumentException` do reflection kiểm tra đầu vào** khác với **`IllegalArgumentException` được chính phương thức đích ném ra**. Khi gọi qua `Method.invoke`, ngoại lệ từ phương thức đích được bọc trong `InvocationTargetException`. Phải phân biệt hai nhánh để xử lý và chẩn đoán đúng.

## 2. `Method.invoke` kiểm tra receiver ra sao?

Chữ ký cơ bản:

```java
Object result = method.invoke(receiver, arguments);
```

Đây là fragment minh họa; `method` đã được tìm trước đó. `receiver` còn gọi là *target object*:

- Với **instance method**, receiver phải là đối tượng của declaring class hoặc lớp con/implementation phù hợp. Truyền đối tượng không liên quan sẽ dẫn đến `IllegalArgumentException`.
- Với **instance method**, truyền `null` làm receiver sẽ dẫn đến **`NullPointerException`**, không phải `IllegalArgumentException`. Không nên gom hai tình huống này thành một loại lỗi.
- Với **static method**, `Method.invoke` **bỏ qua đối số receiver**; truyền `null` là cách diễn đạt rõ ràng. Không kết luận một static method sẽ lỗi chỉ vì receiver không phải object của declaring class.
- Nếu receiver có kiểu hợp lệ nhưng quyền truy cập bị từ chối, đó là một nhóm lỗi khác, thường `IllegalAccessException`.

Ví dụ fragment:

```java
class Parent {
    public String name() { return "parent"; }
}
class Child extends Parent {}
class Unrelated {}

// Đặt trong một method có throws ReflectiveOperationException:
java.lang.reflect.Method m = Parent.class.getMethod("name");

System.out.println(m.invoke(new Parent())); // parent
System.out.println(m.invoke(new Child()));  // parent
// m.invoke(new Unrelated());                // IllegalArgumentException
// m.invoke(null);                           // NullPointerException
```

`m.getDeclaringClass()` cho biết lớp khai báo method, còn `m.getModifiers()` cho biết method có `static` hay không. Một bước kiểm tra hữu ích trước khi gọi instance method là:

```java
if (!java.lang.reflect.Modifier.isStatic(m.getModifiers())) {
    if (receiver == null) {
        throw new IllegalArgumentException("Receiver phải khác null");
    }
    if (!m.getDeclaringClass().isInstance(receiver)) {
        throw new IllegalArgumentException(
                "Receiver không tương thích với " + m.getDeclaringClass().getName());
    }
}
```

Đây là **validation do ứng dụng chủ động thiết kế**, nên chính đoạn `throw new IllegalArgumentException(...)` có thể thay đổi cách phân loại lỗi `null` ở tầng ứng dụng. Nó không làm thay đổi hợp đồng chuẩn của `Method.invoke(null, ...)` đối với instance method.

## 3. Đối số: sai số lượng, sai thứ tự, sai kiểu

Để chẩn đoán một `Method.invoke` bị `IllegalArgumentException`, kiểm tra theo thứ tự:

1. **Số lượng tham số:** `method.getParameterCount()` phải khớp số lượng đối số thực tế mà reflection nhận. Không được mặc định rằng phương thức có `varargs` thì `Method.invoke` tự gom mọi đối số rời thành array.
2. **Kiểu khai báo:** dùng `method.getParameterTypes()` để biết các loại kiểu ở runtime; với generic, `getGenericParameterTypes()` giúp xem metadata khai báo, nhưng kiểm tra gọi thông thường diễn ra trên kiểu đã erasure.
3. **Giá trị `null`:** có thể truyền vào tham số reference; không hợp lệ cho tham số primitive như `int` hay `boolean`.
4. **Primitive conversion:** reflection hỗ trợ unboxing wrapper và **widening primitive** thích hợp (chẳng hạn `Short` sang `int`, `Integer` sang `long`); không tự làm narrowing (`Long` sang `int`) hoặc chuyển tùy tiện từ `String` sang số.
5. **Reference conversion:** một đối tượng cần tương thích với kiểu tham số reference. Không được nhầm `Object[]` (container chứa danh sách đối số của reflection) với `String[]` (một đối số được khai báo của method đích).

Ví dụ `sum(int, long)`:

| Lời gọi qua `Method.invoke` | Kết quả |
| --- | --- |
| `sum.invoke(service, 2, 3L)` | Hợp lệ; `Integer` unbox thành `int`, `Long` thành `long` |
| `sum.invoke(service, Short.valueOf((short) 2), Integer.valueOf(3))` | Hợp lệ; unbox rồi widening primitive |
| `sum.invoke(service, 2)` | `IllegalArgumentException` vì thiếu đối số |
| `sum.invoke(service, 2, 3L, 4)` | `IllegalArgumentException` vì thừa đối số |
| `sum.invoke(service, 2L, 3L)` | `IllegalArgumentException` vì `long` không narrowing thành `int` |
| `sum.invoke(service, null, 3L)` | `IllegalArgumentException` vì `int` không nhận `null` |
| `sum.invoke(service, "2", 3L)` | `IllegalArgumentException` vì không tự parse `String` thành `int` |

Reflection không thực hiện overload resolution như khi biên dịch lời gọi Java thông thường. Ví dụ nếu một class có `f(int)` và `f(long)`, `getMethod("f", int.class)` xác định **đúng một overload**; sau đó `invoke` không tự chọn lại overload khác chỉ vì nhận đối số `Long`. Chọn đúng chữ ký ngay lúc tra cứu.

## 4. Bẫy `Object...`: truyền tham số dạng mảng và varargs

`Method.invoke` có chữ ký `invoke(Object obj, Object... args)`. Dấu `...` này thuộc **API reflection**, không có nghĩa tham số varargs của *method đích* được đóng gói tự động.

Giả sử method đích:

```java
public String join(String... items) {
    return String.join("|", items);
}
```

Tại runtime, chữ ký thật của nó là `join(String[])`. Do đó:

```java
Method join = Service.class.getMethod("join", String[].class);

// Đúng: mảng String[] là MỘT đối số của method đích.
Object ok = join.invoke(service, (Object) new String[] {"a", "b"});
System.out.println(ok); // a|b

// Sai: đưa HAI đối số String riêng lẻ vào reflection.
// join.invoke(service, "a", "b"); // IllegalArgumentException
```

Fragment ở trên cần import `java.lang.reflect.Method`, đồng thời `Service` và `service` đã được khai báo ở ngữ cảnh phù hợp. Ép sang `(Object)` ngăn Java compiler trải `String[]` thành nhiều phần tử cho varargs `Object...` của `Method.invoke`. Cách tương đương, tường minh hơn là:

```java
join.invoke(service, new Object[] {new String[] {"a", "b"}});
```

Khi gọi method có đúng **một tham số reference** bằng giá trị `null`, viết rõ `(Object) null` hoặc `new Object[]{null}`. Truyền một `null` không ép kiểu vào vị trí varargs có thể bị diễn giải là **mảng đối số `Object[]` bằng `null`**, tức không mang cùng ý nghĩa với một đối số `null`.

## 5. `Constructor.newInstance` và `Field.get/set` cũng có ràng buộc đầu vào

Không chỉ `Method.invoke`. Các API reflection khác có thể ném `IllegalArgumentException` do giá trị đưa vào không khớp:

| API | Trường hợp có thể gây `IllegalArgumentException` | Phân biệt |
| --- | --- | --- |
| `Constructor.newInstance(args)` | Sai số lượng/kiểu đối số so với constructor đã tìm | Không có receiver; exception bên trong constructor được bọc `InvocationTargetException` |
| `Field.get(receiver)` | Receiver không phù hợp cho instance field | Receiver `null` cho instance field dẫn đến `NullPointerException` |
| `Field.set(receiver, value)` | Receiver sai kiểu hoặc giá trị ghi không thể chuyển sang kiểu field | Field `final`/không đủ quyền còn chịu quy tắc riêng, có thể `IllegalAccessException` |
| `Field.setInt(receiver, value)` | Receiver không phù hợp hoặc field không chấp nhận giá trị kiểu `int` theo quy tắc chuyển đổi của API | Không dùng `setInt` để ghi tùy ý vào mọi field |

Với field `static`, receiver bị bỏ qua theo hợp đồng của `Field.get/set`. Với instance field, phải truyền instance phù hợp. `Field#getType()` hữu ích để đọc kiểu field trước khi ghi.

`Constructor.newInstance` nhận arguments tương ứng với chữ ký constructor được tra cứu, ví dụ `getConstructor(int.class)`. Nếu một constructor có tham số `int`, truyền chuỗi `"3"` không khiến reflection tự gọi `Integer.parseInt`.

Chú ý `IllegalArgumentException` cũng có thể xuất hiện ở bước **tra cứu hoặc tạo lời gọi động** trong những API khác, nhưng bài này tập trung vào đầu vào của core reflection và cách chẩn đoán receiver/arguments.

## 6. Ví dụ Java 17+ hoàn chỉnh: 12 tình huống và kết quả

Tạo file **`ReflectArgumentDiagnostics.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectArgumentDiagnostics {
    public static final class Service {
        public int total;

        public Service() {}

        public int sum(int x, long y) {
            return x + (int) y;
        }

        public String join(String... items) {
            return String.join("|", items);
        }

        public void check(int code) {
            if (code < 0) {
                throw new IllegalArgumentException("business rule");
            }
        }
    }

    @FunctionalInterface
    interface Action {
        Object execute() throws Throwable;
    }

    private static void probe(String label, Action action) {
        try {
            System.out.println(label + " => " + action.execute());
        } catch (InvocationTargetException ex) {
            Throwable cause = ex.getCause();
            System.out.println(label + " => InvocationTargetException / cause="
                    + cause.getClass().getSimpleName() + ": " + cause.getMessage());
        } catch (Throwable ex) {
            System.out.println(label + " => " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        Service service = new Service();
        Method sum = Service.class.getMethod("sum", int.class, long.class);
        Field total = Service.class.getField("total");
        Constructor<Service> ctor = Service.class.getConstructor();
        Method check = Service.class.getMethod("check", int.class);
        Method join = Service.class.getMethod("join", String[].class);

        probe("valid widening",
                () -> sum.invoke(service, Short.valueOf((short) 2), Integer.valueOf(3)));
        probe("wrong receiver", () -> sum.invoke("not Service", 2, 3L));
        probe("wrong arity", () -> sum.invoke(service, 2));
        probe("narrowing Long to int", () -> sum.invoke(service, 2L, 3L));
        probe("null primitive", () -> sum.invoke(service, null, 3L));
        probe("null receiver", () -> sum.invoke(null, 2, 3L));
        probe("field wrong receiver", () -> total.get("not Service"));
        probe("field wrong value",
                () -> { total.set(service, "text"); return null; });
        probe("constructor wrong args", () -> ctor.newInstance(1));
        probe("target threw IllegalArgumentException",
                () -> check.invoke(service, -1));
        probe("varargs packed",
                () -> join.invoke(service, (Object) new String[] {"a", "b"}));
        probe("varargs spread", () -> join.invoke(service, "a", "b"));
    }
}
```

Biên dịch và chạy tại thư mục chứa file:

```bash
javac --release 17 ReflectArgumentDiagnostics.java
java ReflectArgumentDiagnostics
```

Output chính xác (đã kiểm chứng bằng OpenJDK 21):

```text
valid widening => 5
wrong receiver => IllegalArgumentException
wrong arity => IllegalArgumentException
narrowing Long to int => IllegalArgumentException
null primitive => IllegalArgumentException
null receiver => NullPointerException
field wrong receiver => IllegalArgumentException
field wrong value => IllegalArgumentException
constructor wrong args => IllegalArgumentException
target threw IllegalArgumentException => InvocationTargetException / cause=IllegalArgumentException: business rule
varargs packed => a|b
varargs spread => IllegalArgumentException
```

Các dòng `wrong receiver`, `wrong arity`, `narrowing` và `null primitive` cho thấy lỗi **áp dụng lời gọi**. Dòng `null receiver` chứng minh cần phân biệt `NullPointerException`. Dòng `target threw IllegalArgumentException` cho thấy chương trình đích thật sự chạy rồi ném lỗi nghiệp vụ; vì vậy bên ngoài nhận `InvocationTargetException`. Hai dòng varargs kiểm tra sự khác nhau giữa một mảng `String[]` với hai chuỗi riêng lẻ.

Trong chương trình demo, `probe` bắt `Throwable` ở nhánh cuối chỉ để in tên lỗi của các trường hợp thử nghiệm. Trong code sản phẩm, nên bắt các loại lỗi liên quan một cách có chủ đích, không tự động nuốt mọi `Error` hay `Throwable`.

## 7. Quy trình chẩn đoán từng bước

Khi stack trace trỏ vào `Method.invoke` hoặc `Field.get/set`:

1. **Xác định vị trí ném lỗi:** exception là `IllegalArgumentException` trực tiếp từ API reflection hay `InvocationTargetException` với `getCause()` là `IllegalArgumentException` do code đích?
2. **Ghi nhận metadata thành viên:** `method.toGenericString()`, `getDeclaringClass().getName()`, `getParameterTypes()`, `Modifier.isStatic(method.getModifiers())`. Với constructor, ghi chữ ký constructor; với field, ghi `field.getType()`.
3. **Kiểm tra receiver:** instance hay static? Nếu instance, có khác `null` và `getDeclaringClass().isInstance(receiver)` trả `true` không? Không dùng `receiver.getClass()` trước khi bảo đảm receiver không null.
4. **Kiểm tra số lượng và thứ tự đối số:** so `getParameterCount()` với số phần tử thực sự trong `Object[]` mà reflection nhận. Với parameter varargs của method đích, nhớ truyền *một mảng* vào vị trí cuối.
5. **Kiểm tra kiểu từng đối số:** nếu là `null`, parameter có primitive không? Nếu là wrapper, có unboxing/widening hợp lệ không? Nếu là reference, có assignable không?
6. **Tách lỗi truy cập:** `IllegalAccessException`, `InaccessibleObjectException` hoặc `ExceptionInInitializerError` cần cách xử lý khác. Không sửa bằng cách đổi receiver/ép kiểu nếu nguyên nhân là JPMS hoặc khởi tạo class.
7. **Đánh giá xử lý lỗi:** lỗi đầu vào từ framework/plugin thường cần sửa mapping/validation; lỗi từ code đích cần hiển thị hoặc xử lý `getCause()` với ngữ cảnh thích hợp.

Gợi ý log chẩn đoán khi xử lý input tin cậy, tránh log dữ liệu nhạy cảm:

```java
System.out.println("method = " + method.toGenericString());
System.out.println("declaringClass = " + method.getDeclaringClass().getName());
System.out.println("receiverType = "
        + (receiver == null ? "<null>" : receiver.getClass().getName()));
System.out.println("parameterCount = " + method.getParameterCount());
System.out.println("parameterTypes = "
        + java.util.Arrays.toString(method.getParameterTypes()));
System.out.println("argumentTypes = " + java.util.Arrays.toString(
        java.util.Arrays.stream(args)
                .map(arg -> arg == null ? "<null>" : arg.getClass().getName())
                .toArray(String[]::new)));
```

Đây là fragment cần đặt trong method nơi `method`, `receiver`, `args` (mảng `Object[]` **khác null**) đã tồn tại. Nếu `args == null`, phải xử lý riêng trước khi gọi `Arrays.stream(args)`. Với dữ liệu do bên ngoài cung cấp, ghi kiểu và số lượng thường đủ để debug; không log toàn bộ giá trị argument hoặc stack trace ra kênh công khai.

## 8. Không nhầm với các ngoại lệ reflection khác

| Ngoại lệ | Tín hiệu chính | Hướng xử lý |
| --- | --- | --- |
| `IllegalArgumentException` trực tiếp | Receiver không phù hợp, sai argument count/type, giá trị field không hợp lệ | Kiểm tra chữ ký, receiver và conversion |
| `NullPointerException` từ instance invocation | Receiver `null` cho instance method/field | Kiểm tra receiver trước khi gọi |
| `InvocationTargetException` | Method/constructor đích ném ngoại lệ | Xem `getCause()`; phân tích code đích |
| `NoSuchMethodException` / `NoSuchFieldException` | Không tìm được thành viên đúng tên/chữ ký | Kiểm tra overload, visibility và declaring class |
| `IllegalAccessException` | Không đủ quyền gọi/truy cập thành viên | Xem modifier, package/module và quyền truy cập |
| `InaccessibleObjectException` | Không thể bật deep reflection access qua `setAccessible` | Xem cấu hình `opens`/module, tránh lạm dụng workaround |
| `ExceptionInInitializerError` | Khởi tạo class (ví dụ trước khi gọi static member) thất bại | Phân tích static initializer và cause |

`Method.invoke` **không** có cơ chế tự dò tên overload, tự parse chuỗi, tự ép kiểu narrowing hay tự bỏ qua kiểm tra receiver cho instance method. Việc sửa các lỗi này thường nằm tại code xây dựng lời gọi reflection, không nằm trong logic của method đích.

## 9. Lỗi thường gặp và câu hỏi tự kiểm tra

- **Bắt mọi `IllegalArgumentException` và cho rằng method đích từ chối dữ liệu:** sai; nếu qua `Method.invoke` thì lỗi từ method đích thường được bọc `InvocationTargetException`.
- **Dùng sai receiver nhưng method tên giống nhau:** không đủ; receiver phải thuộc đúng declaring class hoặc subtype được phép.
- **Truyền `Long` vì nghĩ Java sẽ “tự ép” xuống `int`:** không; narrowing bị từ chối.
- **Gọi reflection method có `String...` bằng nhiều chuỗi rời:** không tự đóng gói; phải truyền một `String[]` ở vị trí đối số cuối.
- **Xem mọi trường hợp receiver sai đều là `IllegalArgumentException`:** receiver `null` cho instance method/field là `NullPointerException`.
- **Cố sửa `IllegalAccessException` bằng đổi kiểu argument:** không giải quyết vấn đề quyền truy cập.

Tự kiểm tra:

1. `m` biểu diễn instance method của `User`, nhưng `m.invoke(new Order())`: lỗi nào? **`IllegalArgumentException` do receiver không phù hợp**.
2. `m` biểu diễn `void f(int x)`. Gọi `m.invoke(user, null, 1)` có hợp lệ không? **Không**, vì reflection nhận hai đối số cho method có một tham số (dù từng tham số trông như thế nào).
3. `m` biểu diễn `void f(long x)`. Truyền `Integer.valueOf(1)` có hợp lệ không? **Có**, thông qua unboxing `int` rồi widening thành `long`.
4. `f` đích tự ném `IllegalArgumentException("bad")`. Caller gọi `Method.invoke` bắt gì? **`InvocationTargetException`** và có thể lấy nguyên nhân `IllegalArgumentException` bằng `getCause()`.
5. `m` biểu diễn `void f(String[] words)`. Muốn truyền `String[]` như một argument qua `invoke(Object, Object...)`? **Ép `(Object) stringArray` hoặc bọc trong `new Object[]{stringArray}`**.

Tài liệu chuẩn: [`Method.invoke` (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)), [`Constructor.newInstance`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)), [`Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html), [`InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html).
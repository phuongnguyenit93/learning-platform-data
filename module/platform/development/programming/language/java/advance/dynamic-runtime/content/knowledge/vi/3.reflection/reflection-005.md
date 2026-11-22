# 3.5 Gọi phương thức static hoặc instance bằng Method.invoke

Trong reflection, `java.lang.reflect.Method` mô tả **một phương thức đã được tra cứu**; `Method.invoke(...)` thực thi phương thức đó tại runtime. Điểm khác biệt quyết định giữa lời gọi **static** và **instance** là đối số đầu tiên (receiver): với `static`, ta thường truyền `null`; với instance method, phải truyền một đối tượng phù hợp. Các đối số thật của phương thức nằm sau receiver.

Bài này tập trung vào cách tra cứu và gọi hai loại phương thức bằng `Method.invoke`, với ví dụ Java 17+ chạy được, xử lý kiểu dữ liệu, overload, varargs, trả về và lỗi thực tế.

## 1. Đọc chính xác chữ ký `Method.invoke`

Theo Java SE API:

~~~java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException
~~~

Ý nghĩa:

- `obj`: đối tượng nhận lời gọi. **Instance method** cần receiver là instance của class/interface khai báo phương thức (hoặc một subtype phù hợp). **Static method** bỏ qua receiver này; truyền `null` để thể hiện ý định rõ ràng.
- `args`: những giá trị truyền vào **tham số được khai báo của method đích**, theo thứ tự. `Object...` là varargs của chính **API reflection**, khác với varargs nếu method đích cũng khai báo `...`.
- Giá trị trả về có kiểu khai báo `Object`: kết quả primitive được boxing (`int` thành `Integer`, `boolean` thành `Boolean`), còn method trả `void` thì kết quả `invoke` là `null`.
- `IllegalAccessException`: không được quyền gọi phương thức; `InvocationTargetException`: thân phương thức đích đã ném exception. Ngoài ra có các lỗi runtime từ receiver, số lượng/kiểu đối số, việc khởi tạo class...

Lời gọi reflection có dạng:

~~~text
                    metadata             receiver        actual arguments
                         │                    │                  │
                         ▼                    ▼                  ▼
Method method = ... ; method.invoke(    objOrNull,    arg0, arg1, ... );
                         │
                         └──> Java kiểm tra access và kiểu, rồi thực thi method đích
~~~

Đừng nhầm `invoke` với `getMethod`: `getMethod` chỉ **tìm** metadata, còn `invoke` mới **gọi** method.

## 2. Static và instance: khác nhau ở receiver và dispatch

| Khía cạnh | `static` method | Instance method |
| --- | --- | --- |
| Ví dụ khai báo | `static int add(int a, int b)` | `String hello(String name)` |
| Tra cứu | `Type.class.getMethod("add", int.class, int.class)` | `Type.class.getMethod("hello", String.class)` |
| Receiver khi gọi | `method.invoke(null, 2, 3)` | `method.invoke(instance, "An")` |
| Có cần tạo object đích? | Không | Có |
| Receiver là `null` | Hợp lệ; thực tế bị bỏ qua | `NullPointerException` |
| Thực thi override ở subclass | Static method không override theo đa hình | Có thể dispatch đến override theo **kiểu runtime của receiver** |
| Class initialization | Gọi static method có thể kích hoạt khởi tạo class khai báo method | Việc tạo/nhận instance có quy tắc initialization riêng |

Ví dụ ngắn (các câu lệnh này thuộc ngữ cảnh một phương thức có xử lý checked exception):

~~~java
Method staticMethod = Math.class.getMethod("max", int.class, int.class);
Object a = staticMethod.invoke(null, 4, 9);       // Integer(9)

Method instanceMethod = String.class.getMethod("substring", int.class);
Object b = instanceMethod.invoke("reflection", 3); // "lection"
~~~

`Math.max` là `static` nên không có receiver thực; `String.substring` là instance method nên cần một `String`. Với `invoke`, trả về được khai báo `Object` dù bạn biết kết quả tương ứng là `Integer` và `String`.

**Lưu ý về receiver static:** theo API, `obj` bị **bỏ qua** với static method, kể cả khi truyền một object khác `null`. Tuy nhiên, luôn dùng `null` cho code rõ nghĩa và tránh nhầm với cách gọi instance.

## 3. Ba bước đúng: tìm Method, chuẩn bị receiver/args, thực thi

**Bước 1 — tìm method theo tên và kiểu tham số**.

~~~java
Method m1 = Service.class.getMethod("calculate", int.class, int.class);
Method m2 = Service.class.getMethod("label", String.class);
~~~

- `getMethod` tìm phương thức `public` có thể truy cập theo cơ chế tìm kiếm API, bao gồm các phương thức `public` kế thừa.
- `getDeclaredMethod` tìm method **khai báo trực tiếp** trong class/interface, kể cả `private`; tìm ra metadata **không tự cấp quyền gọi** method đó.
- Tên và danh sách `Class<?>` kiểu tham số phải khớp chữ ký. Ví dụ `int.class` khác `Integer.class`, `String[].class` khác `String.class`. Kiểu trả về **không** là tham số của `getMethod`.
- Có thể kiểm tra method tìm thấy bằng `m.getName()`, `m.getParameterTypes()`, `m.getReturnType()`, `m.getDeclaringClass()`, `m.getModifiers()`, `m.isVarArgs()`.

**Bước 2 — xác định static/instance và chuẩn bị đối số.**

~~~java
boolean isStatic = java.lang.reflect.Modifier.isStatic(m1.getModifiers());
Object receiver = isStatic ? null : new Service();
~~~

Trong ứng dụng thực, thường bạn đã biết loại method theo contract. Nếu xử lý method động, đọc `Modifier.isStatic(...)` để tránh truyền nhầm receiver.

**Bước 3 — gọi và xử lý kết quả hoặc lỗi.**

~~~java
Object result = m1.invoke(receiver, 10, 20);
~~~

Java không dùng `args` để tự tìm “overload tốt nhất” theo các giá trị runtime. Overload đã được chọn ở **bước tra cứu Method**; `invoke` chỉ kiểm tra xem các giá trị đưa vào có phù hợp tham số của method đã chọn không.

## 4. Ví dụ hoàn chỉnh Java 17+: static, instance, override, overload, varargs, void và exception

Tạo file `ReflectInvokeDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ReflectInvokeDemo {

    public static class Service {
        public static int add(int left, int right) {
            return left + right;
        }

        public String greet(String name) {
            return "Xin chào, " + name;
        }

        public String show(int number) {
            return "int=" + number;
        }

        public String show(String text) {
            return "text=" + text;
        }

        public static String join(String... items) {
            return String.join("|", items);
        }

        public void mark() {
            System.out.println("mark() called");
        }

        public void fail() {
            throw new IllegalStateException("lỗi nghiệp vụ");
        }
    }

    public static class PoliteService extends Service {
        @Override
        public String greet(String name) {
            return "Kính chào, " + name;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Service> type = Service.class;

        // static: receiver bằng null; int trả về được boxing thành Integer
        Method add = type.getMethod("add", int.class, int.class);
        System.out.println("add static? " + Modifier.isStatic(add.getModifiers()));
        Object sum = add.invoke(null, 2, 3);
        System.out.println("add = " + sum
                + " (" + sum.getClass().getSimpleName() + ")");

        // instance: truyền object của Service
        Service service = new Service();
        Method greet = type.getMethod("greet", String.class);
        System.out.println("greet = " + greet.invoke(service, "An"));

        // instance: cùng Method, receiver là subtype -> gọi override
        System.out.println("override = " + greet.invoke(
                new PoliteService(), "Bình"));

        // overload: chọn show(int) ngay khi gọi getMethod
        Method showInt = type.getMethod("show", int.class);
        System.out.println("overload = " + showInt.invoke(service, 7));

        // Target varargs thực chất có một tham số String[]
        Method join = type.getMethod("join", String[].class);
        String[] items = { "A", "B", "C" };
        System.out.println("join = " + join.invoke(null, (Object) items));

        // void: invoke trả null
        Method mark = type.getMethod("mark");
        Object voidResult = mark.invoke(service);
        System.out.println("void result = " + voidResult);

        // Exception của target được bọc bởi InvocationTargetException
        Method fail = type.getMethod("fail");
        try {
            fail.invoke(service);
        } catch (InvocationTargetException ex) {
            Throwable cause = ex.getCause();
            System.out.println("cause = "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }
    }
}
~~~

Biên dịch và chạy (từ thư mục chứa `ReflectInvokeDemo.java`):

~~~bash
javac ReflectInvokeDemo.java
java ReflectInvokeDemo
~~~

`stdout` dự kiến:

~~~text
add static? true
add = 5 (Integer)
greet = Xin chào, An
override = Kính chào, Bình
overload = int=7
join = A|B|C
mark() called
void result = null
cause = IllegalStateException: lỗi nghiệp vụ
~~~

Đối chiếu các điểm:

1. `add.invoke(null, 2, 3)`: static method không cần instance; kết quả `int` được boxing thành `Integer`, do đó `sum.getClass().getSimpleName()` là `Integer`.
2. `greet.invoke(service, "An")`: receiver là `Service`; cùng một `Method greet`, nếu receiver là `PoliteService`, JVM thực thi override của subclass.
3. `showInt.invoke(service, 7)`: overload đã được chọn bằng `getMethod("show", int.class)`. Việc đưa chuỗi `"7"` không khiến reflection tự chọn `show(String)`.
4. `join.invoke(null, (Object) items)`: ép `String[]` thành `Object` để truyền **một đối số** đến `Method.invoke`, bởi method đích có một tham số `String[]`.
5. `mark.invoke(service)`: thực thi method trả `void` và nhận `null` từ reflection.
6. `fail.invoke(service)`: thân method ném `IllegalStateException`, được truy cập qua `InvocationTargetException.getCause()`.

Ví dụ dùng class `public` lồng trong một class `public` để method `public` có thể được tra cứu và gọi trực tiếp. Trong module/app thật, quyền truy cập còn phụ thuộc package và module boundary.

## 5. Instance method: receiver, kế thừa và override

Với method thông thường trên class:

~~~java
Method method = Parent.class.getMethod("run");
method.invoke(new Child());
~~~

Đây là **đoạn minh họa**, giả sử `Parent` có `public void run()` và `Child extends Parent` override `run()`; nó không phải chương trình độc lập. JVM sử dụng quy tắc virtual dispatch: khi receiver là `Child`, method override thích hợp có thể được gọi, dù `Method` được tìm từ `Parent.class`. Điều này khác với ý tưởng “Method luôn chạy chính xác phần thân của class mà ta dùng để getMethod”.

Receiver phải phù hợp với lớp/interface khai báo method:

| Receiver | Lời gọi instance | Kết quả |
| --- | --- | --- |
| `new Parent()` | `method.invoke(receiver)` | Hợp lệ nếu class/method access cho phép |
| `new Child()` | `method.invoke(receiver)` | Hợp lệ, có thể dispatch đến override |
| `null` | `method.invoke(null)` | `NullPointerException` |
| Object không thuộc hierarchy phù hợp | `method.invoke(new Object())` | `IllegalArgumentException` |

Một method `static` không được override như instance method, dù subclass có thể khai báo một static method cùng chữ ký để *hide*. Khi một `Method` cụ thể đại diện cho static method, gọi nó không dispatch đến method static cùng tên theo kiểu của `obj`.

Khi lời gọi instance cần thay đổi trạng thái, hãy dùng **đúng object đang sở hữu trạng thái**. Truyền `new Service()` trong mỗi lần `invoke` sẽ thao tác trên object mới, có thể không phải instance bạn dự định xử lý.

## 6. Kiểu tham số: boxing, unboxing, widening và điều không được chuyển

`Method.invoke` kiểm tra số lượng tham số và áp dụng các *method invocation conversions* được Java cho phép, bao gồm unboxing và widening primitive phù hợp. API không thực hiện arbitrary conversions.

Ví dụ với phương thức `public static long doubleValue(long input)`:

~~~java
Method twice = Example.class.getMethod("doubleValue", long.class);
Object result = twice.invoke(null, Integer.valueOf(6));
~~~

Đây là đoạn minh họa với giả định `Example.doubleValue(long)` tồn tại: `Integer` có thể được unbox thành `int` rồi widen sang `long`. Ngược lại, truyền `Long.valueOf(6)` cho parameter `int` của method khác **không** được narrowing tự động thành `int`. Chuỗi `"6"` cũng không tự chuyển thành số.

Các quy tắc cần nhớ:

- `null` chỉ có thể là giá trị hợp lệ cho tham số reference; truyền `null` cho `int`, `boolean`... sẽ lỗi.
- Với tham số primitive, reflection có thể unbox kiểu wrapper thích hợp rồi widening; không tự narrowing để tránh mất dữ liệu.
- Với tham số reference, object phải tương thích kiểu yêu cầu; không tự parse chuỗi, không tự tạo object mới từ kiểu khác.
- Tham số phải đúng **số lượng**, đúng **thứ tự**, phù hợp kiểu của method đã resolve.
- Nếu method trả primitive, `invoke` trả wrapper; nếu trả reference thì nhận object; nếu trả `void` thì `null`. Cần cast kiểu trả về khi dùng, ví dụ `int n = (Integer) method.invoke(receiver);`.
- Mảng kiểu primitive trả về vẫn là chính mảng primitive (ví dụ `int[]`), không bị chuyển từng phần tử thành `Integer`.

## 7. Overload được quyết định khi tra cứu, không phải ở `invoke`

Giả sử có:

~~~java
public String format(int value) { return "number"; }
public String format(String value) { return "text"; }
~~~

Hai khai báo là **minh họa bên trong một class**, không phải mã top-level độc lập. Muốn gọi overload nào, hãy tìm đúng:

~~~java
Method intOverload = type.getMethod("format", int.class);
Method textOverload = type.getMethod("format", String.class);
~~~

`type` ở đây là `Class<?>` của class chứa hai method. `getMethod("format", Integer.class)` sẽ không tự chọn `format(int)` nếu class không có overload nhận `Integer`, vì bước **tra cứu chữ ký** yêu cầu đúng `Class<?>` của từng tham số. Các conversion hợp lệ chỉ được áp dụng **sau khi** đã tìm thấy `Method`.

Điều này đặc biệt quan trọng khi đọc tên method và argument values từ JSON/config. Nếu chỉ có dữ liệu runtime mà không biết chữ ký, bạn phải thiết kế logic lựa chọn overload cẩn thận thay vì thử ngẫu nhiên từng `Method`. Đánh giá trường hợp `null` càng cần cẩn trọng vì nó không tiết lộ kiểu reference mong muốn.

## 8. Bẫy varargs và tham số mảng trong `invoke`

Có **hai tầng varargs độc lập**:

1. Phương thức reflection: `invoke(Object receiver, Object... args)`.
2. Method đích, ví dụ `static String join(String... words)`, về mặt chữ ký JVM là method có **một tham số `String[]`**.

Với `Method join = Service.class.getMethod("join", String[].class)` và `String[] words = {"A", "B"}`:

~~~java
join.invoke(null, (Object) words);          // Đúng: một đối số String[]
join.invoke(null, new Object[] { words }); // Đúng: args có một phần tử String[]
// join.invoke(null, words);                // Sai ý định: có thể coi từng String
//                                          // trong words là từng đối số riêng.
~~~

Hai lời gọi đầu đều đặt *một* `String[]` vào dãy đối số của target. Dòng thứ ba dễ dẫn đến `IllegalArgumentException` do sai số lượng/kiểu đối số, vì `String[]` cũng là `Object[]` và compiler có thể truyền nó như varargs array của **`Method.invoke`**. Đây là khác biệt giữa “method cần một mảng” và “API `invoke` nhận mảng các đối số”.

Với method đích **không có tham số**, dùng `method.invoke(receiver)` hoặc `method.invoke(receiver, new Object[0])` để rõ ràng. Javadoc còn cho phép `args` array bằng `null` khi target có 0 formal parameters, nhưng viết `new Object[0]` giúp tránh mơ hồ giữa “không có đối số” và “một đối số có giá trị null”.

Với method đích có **một tham số reference cần nhận `null`**, có thể viết:

~~~java
method.invoke(receiver, (Object) null);
~~~

Khi đó cast thể hiện một argument duy nhất với giá trị `null`; đây không phải kiểu gọi method đích không có đối số.

## 9. Xử lý exception: lỗi của reflection và lỗi của method đích

Không phải mọi lỗi trong `invoke` đều được bọc giống nhau. Phân biệt hai nhóm:

| Vấn đề | Exception chủ yếu | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy chữ ký ở `getMethod` | `NoSuchMethodException` | Kiểm tra tên, danh sách parameter type, public/declared |
| Method tồn tại nhưng caller không được access | `IllegalAccessException` | Kiểm tra visibility, module exports/opens, quyền runtime |
| Receiver instance bằng `null` | `NullPointerException` | Cung cấp receiver thật |
| Receiver không phù hợp, sai số lượng/kiểu argument | `IllegalArgumentException` | Kiểm tra `getDeclaringClass()`, `getParameterTypes()`, thứ tự/kiểu arg |
| Thân method đích ném exception/error | `InvocationTargetException` | Đọc `getCause()` để xác định lỗi thực |
| Static initialization thất bại khi thực thi | `ExceptionInInitializerError` | Kiểm tra lỗi khởi tạo class, static initializer |

Ví dụ đúng cách bóc lỗi **của target**:

~~~java
try {
    Object value = method.invoke(receiver, arguments);
    // xử lý value
} catch (InvocationTargetException ex) {
    Throwable original = ex.getCause();
    // log/xử lý nguyên nhân business; có thể cần ném lại theo contract
} catch (IllegalAccessException ex) {
    // xử lý trường hợp reflection không được phép gọi method
}
~~~

Đây là đoạn minh họa bên trong method có các biến `method`, `receiver`, `arguments` được tạo trước; chú ý `arguments` nên có kiểu `Object[]`. Thực tế, `NoSuchMethodException` phát sinh ở bước lookup, không phải trong `Method.invoke`. `InvocationTargetException` là wrapper có cause; việc log riêng wrapper mà bỏ qua cause sẽ làm khó chẩn đoán.

Với phương thức target trả `void` và ném exception, kết quả không bao giờ là “`null` biểu diễn lỗi”: lời gọi thất bại bằng exception trước khi trả về. Do đó không suy luận “return `null` nghĩa là invoke hỏng”.

## 10. Quyền truy cập và module Java

Tra cứu được `Method` chưa bảo đảm có quyền thực thi:

- `getMethod` trả các method `public`, nhưng **class khai báo** hoặc module/package chứa class có thể không mở truy cập cho caller trong tình huống thực tế.
- `getDeclaredMethod` có thể tìm method `private`, `protected` hoặc package-private, nhưng gọi bằng `invoke` vẫn phải qua access checks.
- `setAccessible(true)` yêu cầu bỏ qua một số kiểm tra access thông thường; từ Java 9, strong encapsulation của JPMS có thể chặn hành động này. `trySetAccessible()` có thể trả `false` khi không thể mở access; `setAccessible(true)` có thể ném `InaccessibleObjectException`.
- `exports` mở API công khai của package theo module rules; `opens` cho phép reflective access sâu hơn trong phạm vi được khai báo. Không khuyên dùng `--add-opens` như giải pháp mặc định khi chưa hiểu quyền truy cập và nhu cầu vận hành.

Trong framework/library, hãy giữ quyền truy cập tối thiểu, tôn trọng public contracts và validate các tên kiểu/phương thức đến từ input không tin cậy. Reflection cũng có thể vô tình gọi method nguy hiểm nếu ứng dụng cho phép người dùng chọn method name tùy ý mà không kiểm soát.

## 11. Hiệu năng và thực hành tốt

- **Ưu tiên gọi trực tiếp** khi biết rõ method ở compile time: `service.greet("An")` đơn giản hơn `getMethod` + `invoke`, có kiểm tra kiểu và IDE refactoring tốt hơn.
- Nếu cần reflection cho plugin/serializer/DI, **tra cứu một lần khi hợp lý**, lưu `Method` theo chữ ký và dùng lại; đừng tra cứu lại theo tên ở mỗi request chỉ vì thuận tiện.
- Tách rõ hai bước **lookup** và **invoke** để lỗi tên/chữ ký khác với lỗi thực thi.
- Kiểm tra `Modifier.isStatic(method.getModifiers())` trong các dispatcher động; đặt receiver `null` đối với static, đối tượng đúng kiểu đối với instance.
- Với code performance-sensitive, đo bằng benchmark phù hợp (JMH, warm-up, dữ liệu đại diện). `MethodHandle` có thể phù hợp cho các pipeline typed, nhưng không thể khẳng định mọi use case MethodHandle luôn nhanh hơn reflection.
- Tránh tự viết resolver overload phức tạp nếu không có contract rõ. Giới hạn những method có thể gọi để không mở quyền runtime ngoài ý muốn.
- Reflection tự nó không thay thế được synchronization hay thread safety. Một method instance thay đổi shared state vẫn cần phối hợp concurrency đúng như khi gọi trực tiếp.

## 12. Câu hỏi tự kiểm tra

1. Có `public static int sum(int,int)` và một `Method sum` đã tìm đúng chữ ký: receiver nào nên truyền? → `null`; hai giá trị số là arguments tiếp theo.
2. `greet` là instance method của `Parent`, còn receiver là `Child extends Parent` override `greet`: có thể chạy phiên bản `Child` không? → Có; virtual dispatch dựa trên kiểu runtime receiver.
3. `getMethod("sum", Integer.class, Integer.class)` có tìm thấy method khai báo `sum(int,int)` không? → Không. Lookup dùng parameter `Class<?>` chính xác; boxing/unboxing lúc invoke không thay quy tắc lookup.
4. Method đích khai báo `void` và chạy thành công thì `invoke` trả gì? → `null`.
5. Phương thức đích ném `IllegalStateException` thì caller reflection bắt gì? → `InvocationTargetException`; lấy `getCause()` là `IllegalStateException`.
6. Vì sao `m.invoke(null, words)` có thể sai khi `words` là `String[]` và target có đúng một tham số `String[]`? → Vì tầng varargs của `Method.invoke` có thể hiểu phần tử `words` là các đối số riêng; dùng `(Object) words` hoặc `new Object[]{words}`.
7. `getDeclaredMethod` đã tìm thấy private method; có thể mặc định gọi từ module khác không? → Không; access control và JPMS vẫn áp dụng.
8. Nếu `static` target method cần khởi tạo class khai báo, initialization có thể xảy ra khi nào? → Khi reflective `invoke` thực hiện method đó nếu class chưa được khởi tạo.

## Tài liệu đối chiếu

- [Java SE 21 — `Method.invoke`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [Java SE 21 — `Class.getMethod` và `getDeclaredMethod`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [Java SE 21 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Oracle Java Tutorials — Invoking Methods, gồm mảng và varargs](https://docs.oracle.com/javase/tutorial/reflect/member/methodInvocation.html)
- [Oracle Java Tutorials — Troubleshooting `Method.invoke`](https://docs.oracle.com/javase/tutorial/reflect/member/methodTrouble.html)

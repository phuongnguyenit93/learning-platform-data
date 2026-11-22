# `Constructor.newInstance` với danh sách đối số đúng kiểu

## 1. Từ chữ ký constructor đến đối số khởi tạo

Trong Java Reflection, `java.lang.reflect.Constructor<T>` biểu diễn **một constructor đã được xác định**, còn `newInstance(Object... initargs)` dùng constructor đó để tạo và khởi tạo một đối tượng.

Quy trình cơ bản:

1. Xác định đúng constructor của lớp bằng **danh sách kiểu tham số được khai báo**, theo thứ tự.
2. Chuẩn bị danh sách **giá trị đối số** với số lượng và kiểu tương thích với constructor đó.
3. Gọi `constructor.newInstance(args...)`; xử lý lỗi về số đối số, kiểu, quyền truy cập và ngoại lệ phát sinh khi khởi tạo.

Ví dụ một lớp có constructor `Order(String, long)`. Để tra cứu, cần truyền `String.class` và `long.class`. Để gọi, cần truyền một giá trị kiểu `String` và một giá trị có thể chuyển đổi hợp lệ sang `long`.

~~~java
Constructor<Order> ctor =
        Order.class.getConstructor(String.class, long.class);

Order order = ctor.newInstance("Notebook", 3L);
~~~

Đoạn trên chỉ minh họa cú pháp trong ngữ cảnh có class `Order` và khai báo/xử lý ngoại lệ. **`getConstructor` nhận kiểu; `newInstance` nhận giá trị.** Không được nhầm hai danh sách này.

## 2. Chọn constructor: phải khớp đúng kiểu đã khai báo

Các phương thức tra cứu thường dùng:

| API | Phạm vi | Cách so khớp |
| --- | --- | --- |
| `Class.getConstructor(Class<?>... parameterTypes)` | Constructor `public` của lớp | Khớp chính xác danh sách kiểu tham số được khai báo |
| `Class.getDeclaredConstructor(Class<?>... parameterTypes)` | Constructor khai báo trong lớp, kể cả non-public | Cũng khớp chính xác kiểu tham số |
| `Class.getConstructors()` | Các constructor `public` | Trả metadata để duyệt, không tự lựa chọn |
| `Class.getDeclaredConstructors()` | Các constructor khai báo trong lớp | Trả metadata để duyệt, kể cả non-public |

Ví dụ với một lớp có hai constructor `Order(String, int)` và `Order(String, long)`:

- `getConstructor(String.class, int.class)` lấy constructor thứ nhất.
- `getConstructor(String.class, long.class)` lấy constructor thứ hai.
- `getConstructor(String.class, Integer.class)` **không tự tìm** `Order(String, int)`. Nếu không có constructor đúng kiểu `Integer`, nó ném `NoSuchMethodException`.

Trình biên dịch có cơ chế **overload resolution** khi xử lý biểu thức `new Order("A", 1)`. Reflection không chạy lại thuật toán ấy khi tra cứu constructor: lời gọi `getConstructor` đòi hỏi chữ ký chính xác.

Tương tự, `getConstructor()` tìm constructor **không tham số**; không tìm thấy thì ném `NoSuchMethodException`, kể cả lớp có constructor nhận tham số hoặc constructor no-arg không `public`.

Các kiểu tham số dùng khi tra cứu là kiểu đã được **erasure** ở runtime. Nếu constructor khai báo `Order(List<String> items)`, phần kiểu tham số tra cứu là `List.class`, không tồn tại `List<String>.class`.

## 3. `newInstance` kiểm tra và chuyển đổi đối số như thế nào?

Chữ ký:

~~~java
public T newInstance(Object... initargs)
        throws InstantiationException,
               IllegalAccessException,
               IllegalArgumentException,
               InvocationTargetException
~~~

Đây là chữ ký API để giải thích, không phải đoạn khai báo phương thức cần chép vào lớp ứng dụng.

Sau khi đã có đúng `Constructor<T>`, `newInstance` yêu cầu các đối số thực tế **tương thích theo từng vị trí** với tham số hình thức của constructor. Runtime có thể tự **unboxing** wrapper và thực hiện một số **widening conversions** thích hợp; nó không tự co hẹp kiểu nguyên thủy (*narrowing*) và không chạy thuật toán chọn overload lần nữa.

| Tham số khai báo | Đối số truyền cho `newInstance` | Kết quả |
| --- | --- | --- |
| `long` | `Long.valueOf(3)` | Hợp lệ: unboxing `Long → long` |
| `long` | `Integer.valueOf(3)` | Hợp lệ: unboxing `Integer → int`, rồi widening `int → long` |
| `int` | `Long.valueOf(3)` | Không hợp lệ: phải narrowing `long → int` |
| `Number` | `Integer.valueOf(3)` | Hợp lệ: tham chiếu `Integer` là một `Number` |
| `Integer` | `Long.valueOf(3)` | Không hợp lệ: wrapper khác loại, không tự đổi sang `Integer` |
| `String` | `null` | Hợp lệ: tham chiếu có thể nhận `null` |
| `long` | `null` | Không hợp lệ: không unbox được `null` |
| `long` | `"3"` | Không hợp lệ: Reflection không parse chuỗi thành số |

Các kiểu nguyên thủy truyền trong mã gọi Java sẽ được **boxing vào Object** bởi cú pháp varargs `newInstance(Object...)`. Việc nhận wrapper ấy rồi chuyển sang tham số nguyên thủy là bước riêng của Reflection.

Lỗi do số lượng đối số sai, vị trí sai, kiểu không tương thích hoặc phép narrowing không được cho phép thường gây `IllegalArgumentException`, **không phải** `NoSuchMethodException`. `NoSuchMethodException` thuộc giai đoạn *tra cứu constructor*, trước lúc gọi `newInstance`.

### Kiểu tĩnh của biến và giá trị runtime

Nếu bạn có `Object quantity = Integer.valueOf(3)`, khi gọi `ctor.newInstance("Notebook", quantity)` thì Reflection nhìn giá trị runtime là `Integer`. Nếu constructor đã chọn nhận `long`, nó có thể unbox và widening. Tuy nhiên `getConstructor(String.class, Object.class)` không thể dùng để tìm constructor `(String, long)`, bởi tra cứu cần đúng kiểu khai báo.

Không nên lấy `arg.getClass()` rồi coi đó luôn là danh sách kiểu constructor cần tìm. Cách này thất bại với `null`, primitive (đã boxing) và overload nhận superclass hoặc interface.

## 4. Ví dụ Java 17+ chạy được

Tạo file **`ConstructorArgumentsDemo.java`**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.util.Arrays;

public class ConstructorArgumentsDemo {
    public static class Order {
        private final String summary;

        public Order(String name, long quantity) {
            if (quantity < 0) {
                throw new IllegalArgumentException("quantity must be >= 0");
            }
            summary = name + " x" + quantity;
        }

        public Order(String name, String... labels) {
            summary = name + " " + Arrays.toString(labels);
        }

        @Override
        public String toString() {
            return summary;
        }
    }

    public static void main(String[] args) throws Exception {
        Constructor<Order> numeric =
                Order.class.getConstructor(String.class, long.class);

        System.out.println("exact lookup: "
                + Arrays.toString(numeric.getParameterTypes()));
        System.out.println("widening: "
                + numeric.newInstance("Notebook", Integer.valueOf(3)));

        try {
            Order.class.getConstructor(String.class, Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("lookup(Integer): NoSuchMethodException");
        }

        try {
            numeric.newInstance("Notebook", "3");
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "invoke(String quantity): IllegalArgumentException");
        }

        try {
            numeric.newInstance("Notebook", (Object) null);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "invoke(null primitive): IllegalArgumentException");
        }

        Constructor<Order> labels =
                Order.class.getConstructor(String.class, String[].class);

        System.out.println("isVarArgs: " + labels.isVarArgs());
        System.out.println("array argument: "
                + labels.newInstance(
                        "Notebook", (Object) new String[]{"A", "B"}));

        try {
            labels.newInstance("Notebook", "A", "B");
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "expanded arguments: IllegalArgumentException");
        }

        try {
            numeric.newInstance("Notebook", -1L);
        } catch (InvocationTargetException e) {
            System.out.println(
                    "constructor threw: " + e.getCause().getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac ConstructorArgumentsDemo.java
java ConstructorArgumentsDemo
~~~

Kết quả chính xác:

~~~text
exact lookup: [class java.lang.String, long]
widening: Notebook x3
lookup(Integer): NoSuchMethodException
invoke(String quantity): IllegalArgumentException
invoke(null primitive): IllegalArgumentException
isVarArgs: true
array argument: Notebook [A, B]
expanded arguments: IllegalArgumentException
constructor threw: quantity must be >= 0
~~~

Giải thích:

1. `getConstructor(String.class, long.class)` tìm đúng chữ ký khai báo; `Integer.valueOf(3)` là **đối số gọi được** cho constructor nhận `long` vì có unboxing rồi widening.
2. `getConstructor(String.class, Integer.class)` thất bại ở **tra cứu**: không có constructor nhận `Integer`; lỗi này xảy ra trước khi tạo đối tượng.
3. `numeric.newInstance("Notebook", "3")` và `numeric.newInstance("Notebook", (Object) null)` đã xác định được constructor, nhưng **đối số sai kiểu** cho `long`, nên phát sinh `IllegalArgumentException`.
4. Constructor khai báo `String... labels` được phản chiếu như tham số **`String[]`**. Khi gọi `newInstance`, phải đưa mảng đó vào **một vị trí đối số**; `(Object) new String[]{...}` diễn đạt rõ điều này.
5. Gọi `labels.newInstance("Notebook", "A", "B")` đưa **ba đối số thực tế** cho constructor chỉ có **hai tham số khai báo** (`String`, `String[]`). Reflection không tự gom hai chuỗi vào mảng varargs của constructor đích.
6. Constructor `Order(String, long)` tự ném `IllegalArgumentException` khi số lượng âm. Reflection bọc ngoại lệ **phát sinh bên trong constructor** trong `InvocationTargetException`; lấy ngoại lệ gốc qua `getCause()`.

Ví dụ dùng lớp lồng `static` và constructor `public`, nên không cần thao tác `setAccessible` và không cần truyền enclosing instance.

## 5. Varargs: phân biệt hai lớp `...`

Điểm dễ nhầm nhất là có **hai nơi xuất hiện varargs**:

- Constructor đích: `Order(String name, String... labels)`, được biểu diễn ở runtime bằng danh sách kiểu `(String, String[])`.
- API Reflection: `Constructor.newInstance(Object... initargs)`, nhận một mảng `Object[]` chứa **các đối số dùng để gọi constructor đích**.

Mô hình:

~~~text
Constructor cần gọi: Order(String, String[])
                               ^
                               | mảng String[] là một đối số
newInstance(Object... initargs)
    Object[0] = "Notebook"
    Object[1] = new String[]{"A", "B"}
~~~

Vì vậy:

~~~java
Constructor<Order> ctor =
        Order.class.getConstructor(String.class, String[].class);

// Đúng: hai đối số của constructor đích, vị trí 2 là String[].
Order a = ctor.newInstance(
        "Notebook", (Object) new String[]{"A", "B"});

// Sai cho constructor đích: ba đối số, không tự gom thành String[].
// ctor.newInstance("Notebook", "A", "B");
~~~

Đoạn trên minh họa với class `Order` đã định nghĩa. `(Object)` giúp tránh nhầm tầng varargs của chính API `newInstance`; việc đóng gói thủ công bằng `new Object[]{"Notebook", new String[]{"A", "B"}}` cũng cho ra danh sách đối số đúng.

**Không tự mở rộng varargs đích** là quy tắc đặc biệt cần ghi nhớ: tính chất `isVarArgs() == true` của `Constructor` không khiến Reflection thực hiện cú pháp lời gọi biến số lượng như compiler.

Với constructor **không tham số**, gọi `ctor.newInstance()` hoặc `ctor.newInstance(new Object[0])` đều phù hợp. Javadoc còn cho phép mảng `initargs` là `null` khi constructor không có tham số, nhưng `newInstance()` rõ ràng và ít gây nhầm lẫn hơn.

## 6. `null`, mảng đối số và đúng thứ tự

Mỗi đối số gắn với **vị trí tham số** tương ứng:

~~~java
// Giả sử có constructor User(String name, Integer age):
Constructor<User> ctor =
        User.class.getConstructor(String.class, Integer.class);

User u = ctor.newInstance("Mai", null);
~~~

Đây là đoạn minh họa; cần có lớp `User` tương ứng. `null` hợp lệ tại vị trí `Integer`, bởi đó là kiểu tham chiếu. Nhưng `null` không hợp lệ với `int` hoặc `long`.

Phân biệt:

- `ctor.newInstance((Object) null)`: có **một đối số** thực tế với giá trị `null`.
- `ctor.newInstance((Object[]) null)`: truyền **mảng đối số `initargs` là null** vào API Reflection; chỉ dùng dạng này nếu hiểu rõ quy tắc của API, đặc biệt với constructor không tham số.
- `ctor.newInstance(new Object[]{"Mai", null})`: truyền **hai đối số** cụ thể.
- `ctor.newInstance("Mai", null)`: cú pháp tiện lợi tương ứng hai đối số cho constructor nhận `String`, `Integer`.

Nếu các đối số bị đảo vị trí, chẳng hạn `(Integer, String)` thay vì `(String, Integer)`, Reflection không tự sắp xếp lại. Nó kiểm tra lần lượt vị trí 1, 2, ... của đúng constructor đã chọn.

Với dữ liệu động (JSON, form hoặc cấu hình), **đừng suy constructor chỉ bằng các giá trị runtime**. Nên thiết kế schema ánh xạ rõ từng tham số và chuyển dữ liệu chuỗi/số sang kiểu mong muốn trước khi gọi Reflection.

## 7. Constructor không public và Java Platform Module System

`getDeclaredConstructor(...)` có thể lấy metadata cho constructor `private`, `protected` hoặc package-private, nhưng metadata không đồng nghĩa quyền gọi:

~~~java
Constructor<Example> ctor =
        Example.class.getDeclaredConstructor(String.class);

if (!ctor.canAccess(null) && !ctor.trySetAccessible()) {
    throw new IllegalAccessException(
            "Không thể mở quyền truy cập constructor");
}

Example value = ctor.newInstance("demo");
~~~

Đây là đoạn minh họa cho lớp `Example`, không phải file Java độc lập. **`Constructor.canAccess` phải nhận `null`**, bởi chưa có đối tượng đích trước khi tạo instance. `trySetAccessible()` trả `false` khi không thể bật cờ bỏ qua kiểm tra truy cập theo điều kiện của JPMS; `setAccessible(true)` có thể ném `InaccessibleObjectException`.

Khi một package thuộc **named module** không được mở thích hợp, mã Reflection từ module khác không thể tùy ý truy cập thành viên private. Các quyền `opens` hoặc `--add-opens` cần được cấu hình một cách có chủ ý; `exports` chỉ cho phép các đường truy cập public theo phạm vi export và không tự cho phép deep reflection.

Khuyến nghị: ưu tiên constructor public/factory method được hỗ trợ. Chỉ mở quyền Reflection ở nơi thực sự cần, và kiểm tra kết quả xin quyền trước khi gọi.

## 8. Constructor của inner class không static

Với non-static inner class:

~~~java
class Outer {
    class Inner {
        Inner(String message) { }
    }
}
~~~

Một instance `Outer.Inner` luôn gắn với một instance `Outer`. Vì vậy, compiler bổ sung **tham số enclosing instance** vào constructor phản chiếu. Ví dụ tra cứu thường là:

~~~java
Outer owner = new Outer();

Constructor<Outer.Inner> innerCtor =
        Outer.Inner.class.getDeclaredConstructor(
                Outer.class, String.class);

// Trong ví dụ các class cùng ngữ cảnh truy cập hợp lệ:
Outer.Inner value = innerCtor.newInstance(owner, "hello");
~~~

Đoạn này minh họa trong một ngữ cảnh Java có quyền truy cập hợp lệ; hãy đặt mã trong vị trí tương thích với visibility của các class. Truyền `"hello"` mà quên `owner` sẽ khiến số lượng/kiểu đối số không khớp. Với lớp lồng **`static`**, không có tham số enclosing instance này.

Một số constructor do compiler sinh còn có tham số ẩn/synthetic, nên khi metadata thực tế khác với mã nguồn, hãy kiểm tra `getParameterTypes()`, `getParameterCount()` và `getParameters()` thay vì chỉ đoán từ chữ ký hiển thị trong IDE.

## 9. Các nhóm lỗi phải phân biệt

| Lỗi | Xảy ra ở đâu | Cách nhận diện |
| --- | --- | --- |
| `NoSuchMethodException` | Tra cứu `getConstructor` / `getDeclaredConstructor` | Không có đúng danh sách kiểu tham số yêu cầu |
| `IllegalArgumentException` | `newInstance` | Sai số lượng/kiểu đối số, narrowing không hợp lệ, hoặc cố tạo enum bằng Reflection |
| `IllegalAccessException` | `newInstance` | Caller không có quyền truy cập constructor đang được kiểm soát |
| `InvocationTargetException` | `newInstance` | **Chính constructor đích** ném ngoại lệ; xem `getCause()` |
| `InstantiationException` | `newInstance` | Không thể tạo instance do đặc tính của lớp, ví dụ abstract class |
| `ExceptionInInitializerError` | Khởi tạo lớp lúc dùng `newInstance` | Static initializer thất bại |
| `InaccessibleObjectException` | Có thể tại `setAccessible(true)` | Không thể bật quyền deep reflection do ranh giới module |

**Phân biệt đặc biệt:** nếu đối số `newInstance` không đúng kiểu, `IllegalArgumentException` đi ra trực tiếp từ API. Nhưng nếu constructor chạy và **bản thân constructor** ném `IllegalArgumentException`, Reflection bọc nó trong `InvocationTargetException`. Đây là hai trường hợp có hướng xử lý khác nhau.

Không cố gọi reflective constructor của `enum`: `Constructor.newInstance` cấm tạo enum theo cách này, kể cả có metadata constructor. Interface, kiểu primitive và mảng cũng không có constructor thông thường để tra cứu như lớp concrete.

## 10. Trường hợp `Class.newInstance()` cũ

`Class.newInstance()` đã **deprecated từ Java 9**. Hạn chế chính:

- Chỉ gọi constructor không tham số.
- Có thể truyền thẳng ngoại lệ do constructor ném, kể cả checked exception, khiến hợp đồng ngoại lệ kém rõ ràng.
- Khả năng xử lý constructor không public không tương đương với cách lấy `Constructor` rồi kiểm soát quyền rõ ràng.

Thay:

~~~java
T value = clazz.getDeclaredConstructor().newInstance();
~~~

Đây là cú pháp minh họa khi `clazz` có kiểu `Class<T>` và caller xử lý các ngoại lệ Reflection. Nếu constructor không public, vẫn phải đáp ứng quyền truy cập theo đúng quy tắc.

## 11. Checklist để gọi `newInstance` đúng

1. **Xác định lớp có thể tạo instance**: một concrete class, không phải enum được gọi bằng Reflection; chú ý static initialization.
2. **Tra đúng constructor**: dùng `getConstructor` cho public, `getDeclaredConstructor` khi cần metadata mọi mức truy cập; truyền `Class<?>...` đúng số lượng và thứ tự.
3. **Kiểm tra chữ ký runtime**: `getParameterTypes()` và `getParameterCount()`; nếu `isVarArgs()`, tham số cuối là **mảng**.
4. **Chuẩn bị Object[] đối số**: chuyển chuỗi dữ liệu sang kiểu nghiệp vụ thật; đánh giá wrapper, unboxing, widening, `null`, inner enclosing instance.
5. **Kiểm tra quyền truy cập**: `canAccess(null)`; chỉ xin quyền mở rộng khi cần và được phép.
6. **Gọi `newInstance` rồi phân loại lỗi**: lỗi lookup, lỗi đối số, lỗi truy cập và lỗi từ constructor đích là các nhóm khác nhau.
7. **Không tự giải overload bằng thứ tự mảng**: nếu cần chọn constructor động, xây luật chọn rõ ràng và xử lý ambiguous cases; tránh lấy constructor đầu tiên từ `getConstructors()`.

### Tự kiểm tra

**Câu 1:** Constructor khai báo `(String, long)`. `getConstructor(String.class, Integer.class)` có tìm được không?  
**Không.** Tra cứu cần kiểu đúng `long.class`.

**Câu 2:** Đã tìm đúng constructor `(String, long)`. `newInstance("A", Integer.valueOf(2))` có hợp lệ không?  
**Có.** `Integer` được unbox thành `int`, sau đó widen sang `long`.

**Câu 3:** Constructor đích khai báo `(String, String...)`. Truyền ba đối số `"A", "B", "C"` vào `newInstance` có tự gom `"B", "C"` thành `String[]` không?  
**Không.** Chuẩn bị đúng hai đối số: `"A"` và một `String[]`.

**Câu 4:** `newInstance` ném `InvocationTargetException`. Có luôn là do đối số sai kiểu không?  
**Không.** Nó thường cho biết **mã constructor đã chạy và ném ngoại lệ**; lấy `getCause()` để xem lỗi gốc.

**Câu 5:** Constructor private có thể tìm bằng `getDeclaredConstructor` nghĩa là luôn gọi được?  
**Không.** Phải đáp ứng Java access control và giới hạn module.

**Ghi nhớ:** `getConstructor(...)` tìm **chữ ký chính xác**; `Constructor.newInstance(...)` thực thi **constructor đã chọn** với số lượng và kiểu giá trị phù hợp. Hiểu rõ hai bước này sẽ tránh các lỗi phổ biến về primitive/wrapper, `null`, varargs và ngoại lệ.

### Tài liệu tham khảo

- [JDK 17 — `Constructor<T>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html)
- [JDK 17 — `Class.getConstructor` và `getDeclaredConstructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Dev.java — Invoking Constructors](https://dev.java/learn/api/reflection-method-handles/reflection/constructors/)
- [Java Language Specification §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9)

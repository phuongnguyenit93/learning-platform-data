# `InstantiationException` và các kiểu Java không thể khởi tạo

`java.lang.InstantiationException` là **checked exception** (kế thừa `ReflectiveOperationException`) báo việc tạo một instance **bằng Reflection** không thành công vì kiểu đích không thể được khởi tạo theo cách đã yêu cầu. Những nguyên nhân điển hình gồm lớp `abstract`, `interface`, kiểu mảng/nguyên thủy/`void` hoặc việc gọi API cũ `Class.newInstance()` đối với lớp không có constructor không tham số.

Điều cần phân biệt: **“không tạo được đối tượng” không đồng nghĩa “luôn ném `InstantiationException`”**. Ngoại lệ thực tế phụ thuộc kiểu được phản chiếu, API dùng để tìm/gọi constructor và giai đoạn lỗi xảy ra. Với Java 17+, cách thông thường là dùng `getDeclaredConstructor(...).newInstance(...)`, không dùng `Class.newInstance()` đã deprecated.

## 1. `InstantiationException` nằm ở đâu trong Java Reflection?

Phân cấp ngoại lệ:

~~~text
java.lang.Throwable
└── java.lang.Exception
    └── java.lang.ReflectiveOperationException
        └── java.lang.InstantiationException
~~~

`InstantiationException` khác `java.lang.InstantiationError`. `InstantiationError` là `Error` liên quan đến tình trạng không tương thích khi liên kết/thực thi bytecode cố tạo một lớp trừu tượng hoặc interface; nó không phải ngoại lệ nghiệp vụ thường dùng để xử lý một lệnh tạo đối tượng qua Reflection.

Trong mã Java thông thường, viết `new AbstractService()` hoặc `new Runnable()` là lỗi **biên dịch**. Nhưng khi nhận một `Class<?>` tại runtime, trình biên dịch không biết đối tượng `Class` ấy đại diện lớp cụ thể, interface hay kiểu abstract. Phép tạo instance bằng Reflection có thể phát hiện điều kiện này **khi chạy** và ném ngoại lệ tương ứng.

## 2. Hai API `newInstance` có hành vi khác nhau

### 2.1. `Class.newInstance()`: API cũ, deprecated từ Java 9

~~~java
// Minh họa API cũ; không nên dùng cho mã mới:
Object obj = someClass.newInstance();
~~~

API này yêu cầu class có constructor không tham số (nullary/no-arg) và constructor/class đó truy cập được từ caller. Theo tài liệu Java SE, `InstantiationException` có thể xuất hiện nếu `someClass` đại diện cho lớp abstract, interface, mảng, kiểu nguyên thủy, `void` **hoặc không có constructor không tham số**. Lỗi về quyền truy cập thông thường là `IllegalAccessException`.

Vấn đề quan trọng: `Class.newInstance()` **có thể truyền thẳng một checked exception do constructor ném ra**, dù khai báo `throws` của phương thức không thể hiện ngoại lệ cụ thể đó. Điều này bỏ qua cơ chế kiểm tra checked exception của trình biên dịch tại call site; vì vậy API đã bị deprecated từ Java 9.

### 2.2. `Constructor.newInstance(...)`: cách phù hợp cho mã mới

~~~java
// Đặt trong phương thức xử lý ReflectiveOperationException,
// hoặc bắt riêng các ngoại lệ cần thiết:
Object obj = someClass.getDeclaredConstructor().newInstance();
~~~

Chuỗi thao tác gồm **hai bước có thể lỗi khác nhau**:

1. `getDeclaredConstructor()` tìm constructor **không tham số** của đúng lớp, bất kể modifier. Nếu không tồn tại, ném `NoSuchMethodException`. Nếu cần constructor có tham số, chỉ rõ parameter types tại đây, chẳng hạn `getDeclaredConstructor(String.class, int.class)`, rồi truyền giá trị cho `newInstance("A", 3)`.
2. `Constructor.newInstance(...)` kiểm tra khả năng tạo instance, quyền truy cập, đối số và thực thi constructor. Nếu **lớp abstract**, phương thức có thể ném `InstantiationException`; nếu constructor đích tự ném exception, nó sẽ được bọc trong `InvocationTargetException`, với nguyên nhân gốc truy cập qua `getCause()`.

`getDeclaredConstructor()` **tìm được cả constructor private**, nhưng tìm được không có nghĩa được phép gọi. Không đủ quyền ở bước `newInstance` thường dẫn đến `IllegalAccessException`. `setAccessible(true)` hay `trySetAccessible()` phải tuân thủ quy tắc module; `opens` và encapsulation của JPMS không bị bỏ qua tùy ý.

`getConstructor(...)` khác `getDeclaredConstructor(...)`: phương thức thứ nhất chỉ tìm **constructor public**, phương thức thứ hai tìm constructor được khai báo trực tiếp kể cả private/protected/package-private. Constructor không được kế thừa như các phương thức instance.

## 3. Bảng chẩn đoán: cùng mục tiêu, lỗi khác API

| Tình huống | `Class.newInstance()` cũ | `getDeclaredConstructor().newInstance()` hiện đại |
| --- | --- | --- |
| Lớp cụ thể, constructor không tham số public, chạy thành công | Tạo instance | Tạo instance |
| **Lớp abstract**, dù có constructor không tham số | `InstantiationException` | `InstantiationException` tại `Constructor.newInstance` |
| **Interface**, array, primitive hoặc `void` | `InstantiationException` | Thường `NoSuchMethodException` khi tìm constructor, vì không có constructor thích hợp |
| Lớp chỉ có constructor có tham số | `InstantiationException` vì không có no-arg constructor | `NoSuchMethodException` ở `getDeclaredConstructor()` |
| Constructor hiện có nhưng caller không đủ quyền gọi | `IllegalAccessException` | `IllegalAccessException` khi `Constructor.newInstance` (trừ khi được cấp quyền hợp lệ) |
| Constructor chạy rồi tự ném ngoại lệ | Ngoại lệ từ constructor có thể truyền thẳng | `InvocationTargetException` chứa ngoại lệ gốc |
| Khởi tạo static của class thất bại | Có thể là `ExceptionInInitializerError` | Có thể là `ExceptionInInitializerError` |

Bảng này tập trung các trường hợp phổ biến. Không suy luận rằng chỉ từ tên `InstantiationException` có thể biết chính xác class nào sai: luôn lưu lại **kiểu đích, constructor/chữ ký, API được gọi, và ngoại lệ gốc**. Với constructor có tham số, mismatch về số lượng hoặc loại đối số có thể tạo `IllegalArgumentException` tại `Constructor.newInstance`.

Một số kiểu có ràng buộc riêng:

- **Lớp abstract** không thể có instance trực tiếp; chỉ có thể tạo một **lớp con cụ thể**. Constructor của lớp abstract có thể tồn tại để lớp con gọi `super(...)`, nhưng bản thân abstract class vẫn không thể `newInstance`.
- **Interface** và **annotation type** không có constructor để tạo đối tượng trực tiếp. Muốn có instance thỏa interface, dùng một lớp triển khai cụ thể hoặc cơ chế proxy phù hợp.
- **`int.class`, `void.class` và các lớp mảng** không có constructor Reflection kiểu thông thường. Tạo mảng bằng `new int[3]` hoặc `Array.newInstance(int.class, 3)`, không tìm `int[].class.getDeclaredConstructor()`.
- **Lớp không có no-arg constructor** vẫn hoàn toàn có thể được khởi tạo qua constructor có tham số: `getDeclaredConstructor(String.class).newInstance("example")` nếu constructor tương ứng và quyền truy cập hợp lệ.
- **Non-static inner class** thường có tham số constructor ẩn chứa instance của enclosing class; gọi `getDeclaredConstructor()` không tham số thường không tìm thấy. Cần đọc `getParameterTypes()` và truyền enclosing instance khi gọi.
- **Enum** được Java quản lý đặc biệt. `Constructor.newInstance(...)` cố tạo enum sẽ bị từ chối bằng `IllegalArgumentException`; không dùng Reflection để tự sản xuất thêm enum constant.
- **Record** là class có thể tạo nếu gọi đúng constructor tương ứng với các component và điều kiện truy cập; record không mặc nhiên có no-arg constructor.

## 4. Ví dụ Java 17+ chạy độc lập, phân biệt các ngoại lệ

Lưu **nguyên vẹn** nội dung sau trong tệp `InstantiationExceptionDemo.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

public class InstantiationExceptionDemo {
    public static class Concrete {
        public Concrete() {}
    }

    public static abstract class AbstractTask {
        public AbstractTask() {}
    }

    public interface Contract {}

    public static class RequiresArgument {
        public RequiresArgument(String name) {}
    }

    public static class Exploding {
        public Exploding() {
            throw new IllegalStateException("ctor failed");
        }
    }

    private static void attempt(String label, Class<?> type) {
        try {
            Constructor<?> ctor = type.getDeclaredConstructor();
            ctor.newInstance();
            System.out.println(label + " -> created");
        } catch (InstantiationException e) {
            System.out.println(label + " -> InstantiationException");
        } catch (NoSuchMethodException e) {
            System.out.println(label + " -> NoSuchMethodException");
        } catch (IllegalAccessException e) {
            System.out.println(label + " -> IllegalAccessException");
        } catch (InvocationTargetException e) {
            System.out.println(label + " -> InvocationTargetException (" +
                    e.getCause().getClass().getSimpleName() + ")");
        }
    }

    @SuppressWarnings("deprecation")
    private static void tryLegacy() throws IllegalAccessException {
        try {
            RequiresArgument.class.newInstance();
        } catch (InstantiationException e) {
            System.out.println(
                    "legacy missing constructor -> InstantiationException");
        }
    }

    public static void main(String[] args) throws Exception {
        attempt("concrete", Concrete.class);
        attempt("abstract", AbstractTask.class);
        attempt("interface", Contract.class);
        attempt("array", String[].class);
        attempt("primitive", int.class);
        attempt("no-arg missing", RequiresArgument.class);
        attempt("constructor throws", Exploding.class);
        tryLegacy();
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac InstantiationExceptionDemo.java
java InstantiationExceptionDemo
~~~

Kết quả:

~~~text
concrete -> created
abstract -> InstantiationException
interface -> NoSuchMethodException
array -> NoSuchMethodException
primitive -> NoSuchMethodException
no-arg missing -> NoSuchMethodException
constructor throws -> InvocationTargetException (IllegalStateException)
legacy missing constructor -> InstantiationException
~~~

**Phân tích output:**

1. `Concrete` là lớp cụ thể, có constructor public không tham số, nên tạo được.
2. `AbstractTask` cố tình **có** constructor public không tham số. Bước `getDeclaredConstructor()` thành công, nhưng `newInstance()` vẫn ném `InstantiationException` vì lớp **abstract**. Ví dụ này cô lập đúng nguyên nhân, tránh nhầm với lỗi thiếu constructor.
3. `Contract` là interface; `String[].class` và `int.class` không có constructor không tham số kiểu class thông thường. API mới thất bại ngay ở **bước tìm constructor**, nên nhận `NoSuchMethodException`.
4. `RequiresArgument` là class cụ thể nhưng constructor yêu cầu một `String`; lookup không tham số thất bại bằng `NoSuchMethodException`.
5. `Exploding` tạo được instance về mặt kiểu, nhưng constructor ném `IllegalStateException`. API mới bọc nó thành `InvocationTargetException`, thay vì `InstantiationException`.
6. `Class.newInstance()` cũ trên `RequiresArgument` lại ném `InstantiationException` cho đúng tình huống **không có no-arg constructor**. Hai API dùng tên `newInstance` nhưng không đồng nhất hành vi lỗi.

Để tạo `RequiresArgument` đúng cách, thay vì thử constructor rỗng, chọn chữ ký thực:

~~~java
// Minh họa đặt bên trong phương thức có xử lý ReflectiveOperationException:
Constructor<InstantiationExceptionDemo.RequiresArgument> ctor =
        InstantiationExceptionDemo.RequiresArgument.class
                .getDeclaredConstructor(String.class);
InstantiationExceptionDemo.RequiresArgument obj =
        ctor.newInstance("demo");
~~~

Đoạn trên chỉ minh họa lựa chọn chữ ký, không phải một chương trình độc lập. Tương tự, để tạo đối tượng thỏa `Contract`, hãy viết lớp triển khai cụ thể `implements Contract` rồi tạo **lớp đó**.

## 5. Cách biết một kiểu có thể khởi tạo trước khi gọi

Nếu đầu vào là tên class do cấu hình/plugin cung cấp, nên kiểm tra các đặc tính căn bản của `Class<?>`:

~~~java
// Đoạn minh họa sử dụng Class<?> type bên trong một method:
int modifiers = type.getModifiers();
boolean unsuitable =
        type.isInterface()
        || type.isAnnotation()
        || type.isArray()
        || type.isPrimitive()
        || type == void.class
        || java.lang.reflect.Modifier.isAbstract(modifiers);
~~~

Đây là **lọc sớm các trường hợp hiển nhiên**; không phải một phép chứng minh có thể tạo instance. `isAnnotation()` thực ra là trường hợp con của interface, nên được ghi tường minh cho người học dễ nhận diện. Một kiểu vượt qua bộ lọc vẫn có thể thiếu constructor phù hợp, không đủ quyền, bị ràng buộc JPMS, là enum, hoặc constructor thực thi thất bại.

Khi có đầu vào dạng `Class<?>` chưa biết trước:

1. Kiểm tra nó có phải lớp cụ thể/loại được hỗ trợ theo contract của hệ thống không.
2. Xác định chữ ký constructor mong muốn: `getDeclaredConstructor(parameterTypes...)` hoặc `getConstructor(...)`. Đừng giả sử mọi lớp có no-arg constructor.
3. Chỉ yêu cầu quyền truy cập thật sự cần. Với JDK 17+ và named modules, package private/protected/private từ module khác có thể bị giới hạn dù lấy được metadata.
4. Bắt và xử lý đúng loại ngoại lệ. Nếu gặp `InvocationTargetException`, kiểm tra `getCause()` để chẩn đoán constructor đích; không che khuất nguyên nhân gốc.
5. Nếu hệ thống cần tạo object từ plugin, cân nhắc contract là interface/base class, factory method hoặc dependency injection. Dùng `type.asSubclass(ExpectedBase.class)` để kiểm tra quan hệ kiểu trước khi tạo, thay vì ép kiểu mù.
6. Ghi log lớp đích, signature đã yêu cầu, exception và cause một cách có kiểm soát; tránh ghi dữ liệu nhạy cảm từ đối số constructor.

Ví dụ xử lý rõ ràng các lỗi phản xạ (đoạn đặt trong một phương thức, không phải file độc lập):

~~~java
try {
    Object instance = type.getDeclaredConstructor().newInstance();
    // Dùng instance theo contract ứng dụng.
} catch (NoSuchMethodException e) {
    // Không có constructor không tham số.
} catch (InstantiationException e) {
    // Có constructor nhưng kiểu không thể khởi tạo (ví dụ abstract).
} catch (IllegalAccessException e) {
    // Không đủ quyền sử dụng constructor.
} catch (java.lang.reflect.InvocationTargetException e) {
    Throwable original = e.getCause();
    // Phân tích/log original và quyết định xử lý theo contract.
}
~~~

Trong ứng dụng thực, các khối xử lý trên phải thực hiện hành động có ý nghĩa (thông báo lỗi cấu hình, propagate/translate exception...), không nuốt lỗi rồi tiếp tục bằng instance `null`.

## 6. Nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`InstantiationException` xảy ra mỗi khi constructor ném lỗi.” | Constructor ném exception khi dùng `Constructor.newInstance` thường được bọc trong `InvocationTargetException`. |
| “Thiếu constructor rỗng với API mới sẽ ném `InstantiationException`.” | `getDeclaredConstructor()` không tìm được constructor ⇒ `NoSuchMethodException`. |
| “Abstract class có public constructor là tạo trực tiếp được.” | Constructor có tồn tại vẫn không thay đổi tính abstract của class. |
| “`Class.forName(...)` tạo một object của class.” | Nó trả `Class<?>` và có thể kích hoạt class initialization, nhưng không gọi constructor để tạo instance của kiểu đích. |
| “`getDeclaredConstructor` tìm được private constructor nghĩa là gọi được.” | Lookup metadata và quyền thực thi là hai vấn đề khác nhau. |
| “`InstantiationException` chính là `InstantiationError`.” | Một bên là checked reflection exception, bên kia là `Error` ở mức liên kết/thực thi. |
| “Thêm `setAccessible(true)` chữa mọi lỗi tạo object.” | Không giải quyết abstract, thiếu constructor, lỗi trong constructor; cũng không vô điều kiện vượt JPMS. |
| “Mảng và primitive có thể tạo qua constructor không tham số.” | Mảng dùng cú pháp mảng hoặc `Array.newInstance`; primitive không được khởi tạo như object qua Reflection. |

**Ghi nhớ:** hãy xét đúng **ba câu hỏi theo thứ tự**: *kiểu này có thể có instance không?* → *constructor đúng chữ ký có tồn tại và truy cập được không?* → *constructor có chạy thành công không?* Với `Constructor.newInstance`, ba nhóm lỗi điển hình tương ứng là `InstantiationException`, `NoSuchMethodException`/`IllegalAccessException`, và `InvocationTargetException`. Thực tế vẫn có những exception/error khác ở mức argument, class initialization hoặc linking nên không được dùng bảng này như danh sách đầy đủ mọi trường hợp.

**Tài liệu chính thức:** [`InstantiationException` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InstantiationException.html), [`Class.newInstance()` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#newInstance()), [`Constructor.newInstance(...)` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)).
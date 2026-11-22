# 2.1 Lấy Class qua class literal, getClass và Class.forName

Java biểu diễn mỗi kiểu đã được JVM nạp bằng một đối tượng `java.lang.Class`. Từ đối tượng đó, Reflection có thể đọc tên, superclass, interface, method, field, constructor, annotation... Ba cách thông dụng để lấy `Class` là **class literal (`SomeType.class`)**, **`object.getClass()`** và **`Class.forName(...)`**. Chúng đều cung cấp metadata kiểu, nhưng khác nhau ở chỗ **kiểu được xác định khi nào**, **cần đối tượng hiện hữu hay không**, **cách chọn class loader**, và **ảnh hưởng đến khởi tạo lớp**.

## 1. Nền tảng: kiểu khai báo, kiểu thực và đối tượng Class

Ví dụ `Number number = Integer.valueOf(42);`: biến có **kiểu khai báo** là `Number`, còn instance hiện hữu có **lớp runtime** là `Integer`. `Number.class` và `Integer.class` lần lượt mô tả hai kiểu khác nhau. Việc có `Class<Integer>` không có nghĩa đã tạo instance `Integer` bằng constructor.

Trong một class loader định nghĩa lớp, một kiểu runtime tương ứng một đối tượng `Class`. Hai cách tra cứu cùng một kiểu trong cùng ngữ cảnh sẽ trả về cùng đối tượng `Class`; vì vậy `a == b` có ý nghĩa để kiểm tra **identity của kiểu**. Ngược lại, cùng binary name nhưng do hai *defining class loader* khác nhau định nghĩa có thể là hai kiểu tách biệt, không thể tự động cast qua lại.

Cũng cần tách ba pha liên quan: **loading** nạp định nghĩa, **linking** xác minh/chuẩn bị và có thể giải quyết tham chiếu, **initialization** thực thi khởi tạo tĩnh (`static` field initializer và `static { ... }`). Lấy được `Class` không đồng nghĩa đã chạy static initializer.

## 2. Class literal: SomeType.class

Khi tên kiểu đã biết ngay trong mã Java, dùng class literal:

~~~java
Class<String> textType = String.class;
Class<Integer> boxedType = Integer.class;
Class<String[]> arrayType = String[].class;
Class<?> primitiveType = int.class;
Class<?> voidType = void.class;
~~~

Đây là biểu thức có thể dùng với class, interface, enum, annotation, array, primitive và `void`. Trình biên dịch kiểm tra tên kiểu và các phụ thuộc biên dịch; **không cần một instance**. Ví dụ khi API yêu cầu type token, `String.class` rõ ràng và an toàn kiểu hơn nhập tên chuỗi `"java.lang.String"`.

Class literal **không tự kích hoạt initialization** của lớp được tham chiếu. JVM vẫn có thể cần nạp hoặc resolve thông tin kiểu; đừng đồng nhất việc đó với chạy `static { ... }`.

Lưu ý:

- `int.class` và `Integer.class` là hai đối tượng `Class` cho **kiểu nguyên thủy** và **wrapper**; `getName()` trả `int` hoặc `java.lang.Integer`.
- `String[].class` diễn tả kiểu mảng; `String[].class.getName()` trả `[Ljava.lang.String;`, còn `getTypeName()` hiển thị dễ đọc hơn.
- Không viết `T.class` nếu `T` là tham số generic, hoặc `List<String>.class`: kiểu generic có type erasure. Dùng `List.class` nếu chỉ cần raw runtime class, hoặc `java.lang.reflect.Type`/`ParameterizedType` nếu cần lưu cấu trúc kiểu có tham số.
- `SomeType.class` là lựa chọn tự nhiên khi kiểu cố định, ví dụ đăng ký serializer, mapper, annotation processor hoặc truyền kiểu cho API Reflection.

Ví dụ type token với method generic (đoạn minh họa cần đặt bên trong một class để biên dịch):

~~~java
static <T> T checkedCast(Class<T> expected, Object value) {
    return expected.cast(value);
}
// Gọi: String s = checkedCast(String.class, "Java");
~~~

`Class.cast` thực hiện kiểm tra runtime và ném `ClassCastException` nếu `value` không tương thích, thay vì ép kiểu không được kiểm soát.

## 3. Object.getClass(): lớp thực của một instance

`getClass()` là phương thức `public final` kế thừa từ `Object`. Nó không nhận tên kiểu mà trả đúng **runtime class của đối tượng đang gọi**, kể cả khi biến tham chiếu được khai báo bằng superclass hoặc interface:

~~~java
Number n = Integer.valueOf(42);
Class<? extends Number> runtime = n.getClass();

System.out.println(runtime.getName());           // java.lang.Integer
System.out.println(n.getClass() == Number.class); // false
~~~

`n` mang kiểu tĩnh `Number` nhưng chứa một `Integer`, nên `getClass()` trả `Integer.class`. Với `List<String> list = new ArrayList<>();`, kết quả là `ArrayList.class`, không phải `List.class`; generic argument `String` cũng không nằm trong đối tượng `Class` thực lúc chạy.

Các giới hạn quan trọng:

1. **Phải có instance khác `null`**. Gọi `getClass()` trên tham chiếu `null` gây `NullPointerException`.
2. Nó chỉ quan sát kiểu hiện tại; không tìm lớp theo chuỗi, không cần lựa chọn class loader và không chủ động khởi tạo một lớp khác. Khi tạo instance bằng `new`, lớp đó thông thường đã phải được khởi tạo.
3. `obj.getClass() == Parent.class` yêu cầu lớp **chính xác** là `Parent`; một instance subclass khiến biểu thức này sai. Nếu muốn chấp nhận subclass, dùng `obj instanceof Parent` hoặc `Parent.class.isInstance(obj)`.
4. Với array instance, `new String[0].getClass() == String[].class` là `true`.

## 4. Class.forName: tìm lớp khi chỉ có tên kiểu ở runtime

Khi tên lớp đến từ file cấu hình, dữ liệu plugin hoặc metadata bên ngoài mã nguồn, sử dụng:

~~~java
Class<?> resolved = Class.forName("java.lang.String");
System.out.println(resolved == String.class); // true (cùng defining loader)
~~~

`Class.forName(String name)` trả `Class<?>` vì compiler không suy ra kiểu cụ thể từ chuỗi. Overload này dùng class loader gắn với lớp **gọi `forName`** và yêu cầu **initialize = true**. Nghĩa là nếu lớp đích chưa được khởi tạo, JVM sẽ chạy static initializer. Lời gọi có thể ném `ClassNotFoundException` (checked exception), và khởi tạo cũng có thể thất bại.

Để **chọn class loader** và **hoãn initialization**, dùng overload ba tham số:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName("com.example.Plugin", false, loader);
~~~

- `name` phải là **binary name** của lớp cần tìm.
- `initialize = false`: không chủ động khởi tạo lớp khi tìm; `true` yêu cầu khởi tạo nếu cần.
- `loader`: class loader để nạp/tìm lớp. `null` yêu cầu bootstrap class loader, không có nghĩa “tự chọn loader thích hợp”.

**Class loader quan trọng:** overload một tham số không mặc nhiên dùng **thread context class loader**; trong plugin container, application server hay môi trường nhiều loader, hãy truyền đúng loader khi cần. Hai loader có thể định nghĩa cùng `com.example.Plugin` thành hai lớp khác nhau, dù `getName()` giống hệt nhau. Khác biệt này giải thích nhiều `ClassCastException` bất ngờ.

**Cú pháp tên:** `java.util.ArrayList` là binary name hợp lệ. Nested class dùng dấu `$` như `com.example.Outer$Inner`, không dùng `Outer.Inner`. Đối với mảng, biểu diễn tên dùng dạng `[Ljava.lang.String;` hoặc `[[I`; `Class.forName("java.lang.String[]")` không phải tên mảng hợp lệ. Không thể dùng `Class.forName("int")` để lấy primitive class; dùng `int.class`.

Java 9+ còn có `Class.forName(Module module, String name)`, khác overload trên: nó **không khởi tạo lớp**, và có thể trả `null` khi không tìm được lớp trong module. Khi dùng overload này phải kiểm tra `null` trước thao tác tiếp.

## 5. Ví dụ chạy được: ba cách lấy Class và thứ tự initialization

Tạo file **ClassLookupDemo.java** (Java 17+):

~~~java
public class ClassLookupDemo {
    static class LazyType {
        static {
            System.out.println("LazyType <clinit>");
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        // Class literal chưa chạy static initializer của LazyType.
        Class<LazyType> literal = LazyType.class;
        System.out.println("literal: " + literal.getName());

        // false: tìm lớp nhưng chưa khởi tạo lớp đích.
        Class<?> deferred = Class.forName(
                "ClassLookupDemo$LazyType",
                false,
                ClassLookupDemo.class.getClassLoader());
        System.out.println("same object: " + (literal == deferred));

        // getClass trả runtime class của instance đã tồn tại.
        Number number = Integer.valueOf(42);
        Class<? extends Number> runtime = number.getClass();
        System.out.println("runtime: " + runtime.getName());

        // Overload một tham số yêu cầu khởi tạo LazyType.
        Class<?> initialized = Class.forName("ClassLookupDemo$LazyType");
        System.out.println("init same object: " + (literal == initialized));

        System.out.println("primitive: " + int.class.getName());
        System.out.println("array: " + String[].class.getName());
    }
}
~~~

Trong thư mục chứa file, chạy:

~~~bash
javac ClassLookupDemo.java
java ClassLookupDemo
~~~

Stdout của một lần chạy trong JVM mới:

~~~text
literal: ClassLookupDemo$LazyType
same object: true
runtime: java.lang.Integer
LazyType <clinit>
init same object: true
primitive: int
array: [Ljava.lang.String;
~~~

Vì `LazyType.class` không khởi tạo lớp, chương trình in tên lớp trước. `forName(..., false, loader)` trả đúng cùng đối tượng `Class` và vẫn chưa in `<clinit>`. `getClass()` cho `Integer` vì đối tượng cụ thể là `Integer`. Chỉ khi đến `Class.forName("ClassLookupDemo$LazyType")`, JVM mới thực thi static initializer, in `LazyType <clinit>` một lần. Việc khởi tạo **không tạo đối tượng `Class` thứ hai**.

Nếu `LazyType` đã được khởi tạo bởi một luồng hoặc đoạn mã trước đó, `forName(..., true, ...)` không chạy lại static initializer. Không nên dựa vào static initializer để thực hiện tác vụ muốn chạy nhiều lần.

## 6. So sánh nhanh và quyết định áp dụng

| Tiêu chí | `MyType.class` | `obj.getClass()` | `Class.forName(...)` |
| --- | --- | --- | --- |
| Đầu vào | Tên kiểu viết trong source | Instance đang có | Chuỗi binary name; có thể truyền loader |
| Khi nào biết kiểu? | Khi biên dịch | Khi chạy, dựa trên instance | Khi chạy, dựa trên cấu hình/tên |
| Cần instance? | Không | Có và khác `null` | Không |
| Kiểu kết quả thường dùng | `Class<MyType>` | `Class<? extends X>` | `Class<?>` |
| Kích hoạt khởi tạo lớp đích? | Không, chỉ vì literal | Không, chỉ vì gọi method | Overload 1 tham số: có; 3 tham số: theo `initialize` |
| Lỗi nổi bật | Lỗi biên dịch nếu tên kiểu sai | `NullPointerException` | `ClassNotFoundException`, lỗi liên kết/khởi tạo |
| Ví dụ | API nhận `String.class` | Quan sát runtime class của proxy | Lớp implement plugin được chọn từ config |

**Chọn đúng công cụ:** Khi đã biết tên kiểu trong source, ưu tiên class literal để được compiler kiểm tra. Khi cần phản ánh instance thực, dùng `getClass()`. Khi kiểu thật sự do cấu hình/runtime quyết định, dùng `forName` và chọn loader cùng thời điểm khởi tạo một cách có chủ đích. Đổi `MyType.class` thành chuỗi cố định `Class.forName("...")` thường chỉ thêm đường lỗi khi chạy.

## 7. Tình huống thực tế: kiểm tra kiểu plugin trước khi tạo instance

Giả sử tên class triển khai interface `Converter` được lưu trong cấu hình. Cần tìm lớp, xác minh nó implement interface rồi tạo instance bằng reflection. Sau đây là **chương trình hoàn chỉnh**, tự chạy được, không cần thư viện ngoài.

Tạo file **ConverterDemo.java**:

~~~java
import java.util.Locale;

public class ConverterDemo {
    public interface Converter {
        String convert(String input);
    }

    public static final class UpperConverter implements Converter {
        public UpperConverter() {
        }

        @Override
        public String convert(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        String nameFromConfig = "ConverterDemo$UpperConverter";

        Class<?> found = Class.forName(
                nameFromConfig, false, ConverterDemo.class.getClassLoader());

        Class<? extends Converter> checked = found.asSubclass(Converter.class);
        Converter converter = checked.getDeclaredConstructor().newInstance();

        System.out.println(converter.convert("java"));
    }
}
~~~

~~~bash
javac ConverterDemo.java
java ConverterDemo
~~~

Stdout:

~~~text
JAVA
~~~

Giải thích: `found` là `Class<?>` vì tên runtime không cung cấp generic type token. `asSubclass(Converter.class)` kiểm tra kiểu có gán được cho `Converter` hay không và trả `Class<? extends Converter>`; nếu không tương thích, ném `ClassCastException`. `getDeclaredConstructor().newInstance()` thực thi constructor và có thể kích hoạt khởi tạo lớp tại thời điểm này. Constructor không tham số phải tồn tại và được phép truy cập; khi dùng JPMS, `exports`, `opens` và accessibility của module/package quyết định thao tác reflection hợp lệ.

**Lưu ý bảo mật:** Không lấy tùy ý tên lớp từ input không tin cậy rồi khởi tạo: static initializer và constructor có thể thực thi mã. Hạn chế implementation được chấp nhận, quản lý class loader và chọn cơ chế plugin phù hợp như `ServiceLoader` khi cần. `asSubclass` giúp kiểm tra kiểu, **không phải sandbox bảo mật**.

## 8. Lỗi phổ biến, nguyên nhân và cách xử lý

| Lỗi / hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `NullPointerException` tại `getClass()` | Đối tượng đang là `null` | Kiểm tra `null` hoặc dùng type token từ nguồn đáng tin |
| `ClassNotFoundException` | Tên chuỗi không tìm thấy qua loader được dùng | Kiểm tra binary name, dependency, classpath/module path và loader |
| `Class.forName("int")` không chạy | Primitive không được tìm theo tên chuỗi này | Dùng `int.class` |
| `Class.forName("Outer.Inner")` không thấy nested class | Tên nested class không đúng binary name | Dùng `Outer$Inner` cùng package phù hợp |
| `NoClassDefFoundError` hoặc `LinkageError` | Thiếu dependency hoặc lỗi liên kết/phiên bản ở runtime | Xem *cause*, kiểm tra dependency/classpath, không chỉ sửa chuỗi tên |
| `ExceptionInInitializerError` | Static initializer gặp lỗi | Kiểm tra logic trong `static` block và nguyên nhân gốc |
| `ClassCastException` khi cast hoặc `asSubclass` | Runtime class không phù hợp; đôi khi có hai loader | Xác minh interface, subclass, defining loader |
| `getDeclaredConstructor().newInstance()` thất bại | Constructor không tồn tại, không thể truy cập, hoặc ném exception | Cung cấp constructor phù hợp, kiểm tra quyền truy cập/module và exception nguyên nhân |
| `obj.getClass() == Base.class` là `false` nhưng `obj instanceof Base` là `true` | Đối tượng thực sự thuộc subclass | Chọn kiểm tra **đúng lớp** hay kiểm tra **quan hệ kế thừa** theo ý định |

`ClassNotFoundException` là **checked exception** của overload tên chuỗi, buộc gọi `try/catch` hoặc khai báo `throws`. `NoClassDefFoundError` lại là **Error**, thường liên quan đến một kiểu đã tham chiếu nhưng không thể được định nghĩa/liên kết trong ngữ cảnh thực tế. Không nên bắt `Throwable` và bỏ qua tất cả vì có thể che giấu lỗi triển khai quan trọng.

Cũng đừng nhầm `getName()` với tên dễ đọc cho mọi loại kiểu. Ví dụ `String[].class.getName()` trả `[Ljava.lang.String;`. Nếu hiển thị cho người học hoặc người dùng, `getTypeName()` thường phù hợp hơn.

## 9. Câu hỏi tự kiểm tra và đáp án

1. Với `Object value = "Hello";`, `value.getClass() == Object.class` đúng không? **Sai**: runtime class là `String.class`.
2. `Sample.class` có tự chạy khối `static` của `Sample` không? **Không** chỉ vì lấy class literal.
3. `Class.forName("pkg.Plugin", false, loader)` đã trả về `Class`. Có thể tạo instance sau đó không? **Có**, nếu tìm được constructor và có quyền truy cập; lúc tạo instance, initialization có thể xảy ra.
4. Vì sao không thể viết `List<String>.class`? Vì tham số generic không tạo runtime class riêng sau **type erasure**; dùng `List.class` hoặc metadata `Type` khi cần.
5. `obj.getClass() == Parent.class` khác `obj instanceof Parent` thế nào? Biểu thức đầu đòi **đúng lớp Parent**, biểu thức sau chấp nhận object của subclass.
6. Hai lớp có cùng `getName()` đã chắc chắn là cùng kiểu? **Chưa**; còn phải xét defining class loader.
7. Khi plugin không nằm trong loader của lớp gọi, nên dùng overload nào? **`Class.forName(name, initialize, explicitLoader)`** với class loader thích hợp.

## 10. Kiến thức cần giữ

- `T.class` xác định kiểu từ source, được compiler kiểm tra, không cần instance.
- `obj.getClass()` trả runtime class của instance hiện hữu và gây lỗi nếu tham chiếu `null`.
- `Class.forName(name)` tìm theo tên runtime, dùng loader của caller và yêu cầu initialization.
- `Class.forName(name, false, loader)` cho phép kiểm soát loader và hoãn initialization để kiểm tra kiểu trước.
- `Class` là điểm bắt đầu của Reflection, **không đồng nghĩa** đã tạo instance, đã chạy static initializer hay có quyền truy cập mọi thành viên.

Ba cách lấy `Class` tương ứng ba câu hỏi khác nhau: **“Tôi biết kiểu nào ở lúc viết mã?”**, **“Đối tượng này thực sự là lớp nào?”** và **“Tên lớp được quyết định lúc chạy trỏ đến kiểu nào?”**. Phân biệt rõ chúng giúp thiết kế reflection, dependency injection, serializer và plugin architecture đúng hơn.

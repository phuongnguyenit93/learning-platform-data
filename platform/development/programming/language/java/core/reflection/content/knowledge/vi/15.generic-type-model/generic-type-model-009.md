# getGenericType, getGenericReturnType và getGenericExceptionTypes trong Java Reflection

## 1. Vì sao API generic khác API kiểu thông thường?

Java hỗ trợ generic trong source như `List<String>`, `Map<String, List<T>>`, `T extends Number` và method `<E extends Exception> void execute() throws E`. Phần lớn thao tác runtime chịu **type erasure**: nhiều vị trí generic được biểu diễn bằng kiểu thô hoặc bound của type variable. Tuy nhiên, compiler có thể lưu **generic signature metadata** trong class file, và Reflection cho phép đọc lại phần khai báo đó.

Ví dụ một field `List<String> names`:

- `field.getType()` trả `Class<?>` đại diện cho `java.util.List`.
- `field.getGenericType()` trả `Type` phản ánh `java.util.List<java.lang.String>`, thông thường là một `ParameterizedType`.
- Hai kết quả cùng nói về **một field**, nhưng khác độ chi tiết: kiểu erasure cần cho truy cập runtime và khai báo generic hữu ích cho mapper, schema generator, serializer, dependency injection.

Đối với method, phân biệt tương tự:

- `method.getReturnType()` so với `method.getGenericReturnType()`.
- `method.getExceptionTypes()` so với `method.getGenericExceptionTypes()`.

**Mục tiêu học tập:** gọi đúng API theo loại thành viên; hiểu các dạng `Type`; biết khi nào metadata còn type variable chưa được thay thế; phân biệt kiểu khai báo từ generic signature với kiểm tra kiểu đối tượng thực tế.

## 2. Ba API chính thuộc về đối tượng Reflection nào?

| API | Chủ sở hữu | Nội dung trả về |
| --- | --- | --- |
| `Field.getGenericType()` | `Field` | `Type` mô tả kiểu khai báo của **field**, kể cả parameterized type và type variable. |
| `Method.getGenericReturnType()` | `Method` | `Type` mô tả **kiểu trả về được khai báo** của method; có thể là `Class`, `ParameterizedType`, `TypeVariable` hoặc `GenericArrayType`. |
| `Executable.getGenericExceptionTypes()` | `Method` hoặc `Constructor<?>` (qua superclass `Executable`) | `Type[]` mô tả các **kiểu exception trong mệnh đề `throws`** theo thứ tự; có thể gồm type variable như `E`. |

Bộ API không-generic đi kèm:

| Không-generic | Generic | Khác biệt thực tế |
| --- | --- | --- |
| `Field.getType(): Class<?>` | `Field.getGenericType(): Type` | `List<String>` trở thành `List.class` ở `getType()`. |
| `Method.getReturnType(): Class<?>` | `Method.getGenericReturnType(): Type` | `T extends Number` trở thành `Number.class` ở `getReturnType()`. |
| `Executable.getExceptionTypes(): Class<?>[]` | `Executable.getGenericExceptionTypes(): Type[]` | `throws E` có thể trở thành `Exception.class` ở bản erasure và `TypeVariable E` ở bản generic. |

Cần tránh gọi sai loại thành viên: **`Field` không có `getGenericReturnType()`**; **`Constructor` không có kiểu trả về**; `getGenericExceptionTypes()` được kế thừa qua `Executable` và sử dụng được trên cả method lẫn constructor.

Nếu không có mệnh đề `throws` thì `getGenericExceptionTypes()` trả **mảng rỗng**, không trả `null`. Với method khai báo `void`, `getGenericReturnType()` có thể trả `void.class`; đây vẫn là một `Class<?>` ở cấp Reflection, dù `void` không phải một giá trị trả về.

## 3. Dạng `Type` quyết định cách đọc kết quả

Cả ba getter generic trong bài trả `Type` hoặc `Type[]` vì một chữ ký có thể chứa `Class<?>` (ví dụ `String`), `ParameterizedType` (`List<String>`), `TypeVariable` (`T`, `E` trong `throws E`), `WildcardType` nằm trong argument (`List<? extends T>`) hoặc `GenericArrayType` (`T[]`). Vì vậy `(Class<?>) field.getGenericType()` chỉ an toàn sau khi xác nhận đúng subtype; nó sẽ thất bại với `List<String>`.

`Type.getTypeName()` giúp in tên, nhưng một parser cần `instanceof` để đi từ `ParameterizedType` tới arguments, từ `TypeVariable` tới bounds/declaration, và từ `GenericArrayType` tới component. Trong bài này chúng ta dùng những nhánh đó để hiểu **field type, method return và declared throws**, không xây lại toàn bộ mô hình `Type` chung.

## 4. `Field.getGenericType()`: giữ thông tin trên field

Xét khai báo:

~~~java
class Container<T extends Number> {
    T current;
    java.util.List<T> history;
    java.util.List<? extends T> view;
    T[] batch;
}
~~~

Đây là mảnh code hợp lệ dùng để giải thích; các kiểu `Type` có thể được Reflection quan sát như sau:

- `current.getType()` trả `Number.class`, do erasure của `T extends Number` là bound đầu tiên `Number`. `current.getGenericType()` trả một `TypeVariable` tên `T`.
- `history.getType()` trả `List.class`; `getGenericType()` trả `ParameterizedType` chứa argument `T`.
- `view.getGenericType()` là `ParameterizedType` chứa `WildcardType` đại diện cho `? extends T`.
- `batch.getType()` trả class của mảng `Number[]`; `getGenericType()` trả `GenericArrayType` cho `T[]`.

Quan trọng: khi subclass cụ thể hóa `T`, ví dụ `class IntContainer extends Container<Integer> {}`, việc lấy field từ `Container.class` hoặc field kế thừa trên `IntContainer.class` **không tự làm `getGenericType()` biến `T` thành `Integer`**. `Field` vẫn mô tả **khai báo gốc**. Muốn áp dụng substitution `T → Integer`, framework phải tìm quan hệ generic supertype (thí dụ `getGenericSuperclass()`), xây bản đồ type variable và giải quyết đệ quy qua superclass/interface.

Ngoài ra, `getGenericType()` cho biết **kiểu khai báo**, không biết generic parameter thực của một object bất kỳ trong heap. Một instance `new Container<Integer>()` không tự mang toàn bộ tham số generic runtime để field có thể suy ra `Integer` từ nó.

## 5. `Method.getGenericReturnType()`: kiểu kết quả đã khai báo

Với method:

~~~java
class Service<T extends Number> {
    java.util.List<T> list() { return java.util.List.of(); }
    T latest() { return null; }
    <U> U echo(U value) { return value; }
}
~~~

- `list().getReturnType()`: `List.class`; `getGenericReturnType()`: `ParameterizedType` dạng `List<T>`.
- `latest().getReturnType()`: `Number.class`; `getGenericReturnType()`: `TypeVariable T` của **class**.
- `echo(Object).getReturnType()`: `Object.class`; `getGenericReturnType()`: `TypeVariable U` của **method**.

`Method.getTypeParameters()` trả type parameters do **method tự khai báo**, như `U`; `Class.getTypeParameters()` trả type parameters của class, như `T`. Khi thấy một `TypeVariable`, dùng `getGenericDeclaration()` nếu cần xác định nó thuộc class, method hay constructor nào.

Phân biệt **kiểu generic trả về khai báo** với **kiểu object trả về sau một lời gọi**: `getGenericReturnType()` không gọi method, không xét polymorphism tại một instance cụ thể và không bảo đảm người gọi nhận đúng object theo generic ở runtime. Nó là metadata dùng để phân tích API và hỗ trợ conversion.

### Bridge method có thể ảnh hưởng công cụ quét

Compiler có thể tạo **bridge method** để duy trì overriding sau erasure. Công cụ dùng `getDeclaredMethods()` đôi lúc thấy cả method source và bridge method; `method.isBridge()`/`method.isSynthetic()` có ích khi muốn chọn method nghiệp vụ. Đừng phân tích generic return type của một bridge rồi nhận nhầm đó là khai báo source mà người dùng viết. Nếu làm bytecode analysis, có thể cần giữ cả hai như hai entry khác nhau.

## 6. `getGenericExceptionTypes()`: generic ở mệnh đề `throws`

Với một generic method:

~~~java
class Worker {
    <E extends Exception> void run(E exception) throws E {
        throw exception;
    }
}
~~~

- `run(Exception).getExceptionTypes()` trả `Class<?>[]` chứa `Exception.class` do erasure của `E extends Exception`.
- `run(Exception).getGenericExceptionTypes()` trả `Type[]` chứa `TypeVariable E`, phản ánh khai báo `throws E`.
- `getGenericExceptionTypes()` của method không khai báo `throws` trả mảng rỗng.
- Nếu method khai báo `throws java.io.IOException, IllegalStateException`, hai API đều trả hai phần tử theo thứ tự, bản generic thường là các `Class<?>` vì không có type variable tại hai chỗ đó.

Điều này hữu ích cho framework biểu diễn hợp đồng lỗi ở mức source/generic nhưng **không** có nghĩa runtime kiểm tra checked exceptions theo generic khi method được gọi. Java compile-time type checking quyết định yêu cầu `catch`/`throws` cho code Java; JVM không có hệ thống checked exception enforcement ở mức `Method.invoke`. Khi gọi qua Reflection, exception từ body method được đóng trong `InvocationTargetException` và phải được xử lý riêng.

Lưu ý giới hạn ngôn ngữ: không được khai báo một generic class trực tiếp kế thừa `Throwable`; trong `throws`, type variable phải có bound phù hợp với `Throwable`. Cũng không có `throws List<IOException>`; generic exception type ở đây thường là **type variable**, không phải một parameterized collection of exceptions.

### Method và constructor đều có generic exception types

`Constructor<?>` cũng kế thừa `Executable.getGenericExceptionTypes()`. Một constructor generic có thể khai báo type parameter riêng:

~~~java
class Factory {
    <E extends java.io.IOException> Factory(E cause) throws E {
        throw cause;
    }
}
~~~

Khi tra cứu constructor theo kiểu **erasure** của `E` là `IOException.class`, `getGenericExceptionTypes()[0]` mô tả `E`; `getExceptionTypes()[0]` là `IOException.class`. Đây là metadata của **constructor**, không phải generic return type; constructor không có giá trị trả về như method.

## 7. Ví dụ Java 17+ đầy đủ và kết quả kiểm chứng

Lưu file `GenericTypeIntrospectionDemo.java`:

~~~java
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GenericTypeIntrospectionDemo {
    static class Repository<T extends Number & Comparable<T>> {
        public T value;
        public List<? extends T> view;
        public T[] batch;
        public Map<String, List<T>> grouped;

        public List<T> load() {
            return List.of();
        }

        public T current() {
            return null;
        }

        public <E extends Exception> void fail(E error) throws E {
            throw error;
        }

        public void save() throws IOException, IllegalStateException {
        }
    }

    static class LongRepository extends Repository<Long> {
    }

    static class Factory {
        public <X extends IOException> Factory(X problem) throws X {
            throw problem;
        }
    }

    static String kinds(Type type) {
        if (type instanceof ParameterizedType) {
            return "ParameterizedType";
        }
        if (type instanceof TypeVariable<?>) {
            return "TypeVariable";
        }
        if (type instanceof GenericArrayType) {
            return "GenericArrayType";
        }
        if (type instanceof WildcardType) {
            return "WildcardType";
        }
        if (type instanceof Class<?>) {
            return "Class";
        }
        return "Other";
    }

    static String names(Type[] types) {
        return Arrays.stream(types)
                .map(Type::getTypeName)
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) throws Exception {
        Field value = Repository.class.getDeclaredField("value");
        Field view = Repository.class.getDeclaredField("view");
        Field batch = Repository.class.getDeclaredField("batch");

        System.out.println("value raw=" + value.getType().getTypeName());
        System.out.println("value generic="
                + value.getGenericType().getTypeName()
                + " (" + kinds(value.getGenericType()) + ")");
        System.out.println("view generic="
                + view.getGenericType().getTypeName()
                + " (" + kinds(view.getGenericType()) + ")");
        System.out.println("batch raw=" + batch.getType().getTypeName());
        System.out.println("batch generic="
                + batch.getGenericType().getTypeName()
                + " (" + kinds(batch.getGenericType()) + ")");

        Method load = Repository.class.getDeclaredMethod("load");
        Method current = Repository.class.getDeclaredMethod("current");
        System.out.println("load return raw="
                + load.getReturnType().getTypeName());
        System.out.println("load return generic="
                + load.getGenericReturnType().getTypeName());
        System.out.println("current return generic="
                + current.getGenericReturnType().getTypeName());

        Method fail = Repository.class.getDeclaredMethod(
                "fail", Exception.class);
        System.out.println("fail throws raw="
                + names(fail.getExceptionTypes()));
        System.out.println("fail throws generic="
                + names(fail.getGenericExceptionTypes()));

        Method save = Repository.class.getDeclaredMethod("save");
        System.out.println("save throws generic="
                + names(save.getGenericExceptionTypes()));
        System.out.println("load throws count="
                + load.getGenericExceptionTypes().length);

        Constructor<?> factory = Factory.class.getDeclaredConstructor(
                IOException.class);
        System.out.println("factory throws raw="
                + names(factory.getExceptionTypes()));
        System.out.println("factory throws generic="
                + names(factory.getGenericExceptionTypes()));

        ParameterizedType parent = (ParameterizedType)
                LongRepository.class.getGenericSuperclass();
        System.out.println("concrete super argument="
                + parent.getActualTypeArguments()[0].getTypeName());
        System.out.println("inherited field generic="
                + LongRepository.class.getField("value")
                        .getGenericType().getTypeName());
    }
}
~~~

Chạy với Java 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 GenericTypeIntrospectionDemo.java
java GenericTypeIntrospectionDemo
~~~

Kết quả dự kiến:

~~~text
value raw=java.lang.Number
value generic=T (TypeVariable)
view generic=java.util.List<? extends T> (ParameterizedType)
batch raw=java.lang.Number[]
batch generic=T[] (GenericArrayType)
load return raw=java.util.List
load return generic=java.util.List<T>
current return generic=T
fail throws raw=java.lang.Exception
fail throws generic=E
save throws generic=java.io.IOException, java.lang.IllegalStateException
load throws count=0
factory throws raw=java.io.IOException
factory throws generic=X
concrete super argument=java.lang.Long
inherited field generic=T
~~~

Đối chiếu ý nghĩa:

1. `value` thuộc kiểu biến `T` với bound đầu tiên `Number`, nên erasure của field là `Number`. Phần metadata generic vẫn là `T`.
2. `view` là `ParameterizedType`; nếu cần lấy wildcard `? extends T`, ép `view.getGenericType()` sang `ParameterizedType` rồi lấy `getActualTypeArguments()[0]` và kiểm tra `instanceof WildcardType`.
3. `batch` minh họa `GenericArrayType`: class runtime của mảng đã erasure thành `Number[]`, trong generic signature vẫn là `T[]`.
4. `load()` trả về `List<T>` ở generic metadata nhưng `List.class` ở kiểu raw; `current()` có generic return type là `T`.
5. `fail(...)` dùng một type variable `E` trong `throws`, bản raw trả bound `Exception`; `save()` khai báo hai exception types thực.
6. `Factory` cho thấy constructor cũng có `getGenericExceptionTypes()` và type variable trong `throws`.
7. `LongRepository` biết đối số generic của superclass là `Long`, nhưng field kế thừa `value` vẫn do `Repository` khai báo. `Field.getGenericType()` trả `T`, **không tự resolve thành `Long`**.

Ví dụ không cần `-parameters` vì không đọc tên formal parameters. Metadata generic signature được trình biên dịch lưu trong class file và khác với cờ lưu parameter names.

## 8. Quy trình đọc chữ ký thành viên

Bắt đầu từ đúng loại member: `Field.getGenericType()` cho một field, `Method.getGenericReturnType()` cho kiểu trả về, và `Executable.getGenericExceptionTypes()` cho danh sách kiểu ở `throws` (method **hoặc** constructor). So sánh với `getType()`, `getReturnType()`, `getExceptionTypes()` khi cần erasure.

Với mỗi `Type` nhận được, kiểm tra `instanceof`. Field `Map<String,List<T>>` cần duyệt hai tầng `ParameterizedType`; return `T[]` cần `GenericArrayType.getGenericComponentType()`; `throws E` cần `TypeVariable.getGenericDeclaration()` và bounds. Nếu subclass gắn `T = Long`, phải đọc thêm generic superclass/interface và ánh xạ theo declaration; **getter của member không tự thế `T`**. Đặc biệt, `getGenericExceptionTypes()` chỉ cho những exception khai báo trong `throws`, không là danh sách đầy đủ exception thực thi có thể ném.

## 9. Erasure, generic signature và khả năng thực thi

Ba khía cạnh cần tách bạch:

- **Source declaration:** `List<String>`, `T extends Number`, `throws E`; compiler kiểm tra ràng buộc generic khi biên dịch.
- **JVM method/field descriptors:** sử dụng type sau erasure để liên kết và gọi, ví dụ `List`, `Number`, `Exception`.
- **Signature metadata:** khi có và hợp lệ, Reflection dùng nó để dựng `ParameterizedType`, `TypeVariable` hoặc các dạng `Type` khác.

Vì thế `Field.getGenericType()` không ép JVM ngăn đặt một `List<Integer>` vào field khai báo `List<String>` qua raw Reflection; compiler có kiểm tra generic nhưng runtime check trên `Field.set` chủ yếu dựa vào raw type `List`. Công cụ serializer/mapper muốn bảo đảm kiểu phần tử phải tự kiểm tra hoặc chuyển đổi theo generic metadata.

Tương tự, `Method.getGenericReturnType()` không biến giá trị trả về thành một object kiểu generic có thể kiểm tra mọi phần tử. Những công cụ phản xạ chỉ có thể phân tích **khai báo**; nếu cần đảm bảo dữ liệu runtime thỏa schema, cần validation riêng.

Ngoài ra, vì mảng `Type[]` của exceptions mô tả `throws` khai báo, nó **không thống kê mọi exception có thể ném** ở runtime: unchecked exception có thể không liệt kê, và nhiều nhánh thực thi có thể ném exception được phép bởi hệ thống kiểu mà không hiện diện như một type trực tiếp tại vị trí phản xạ.

## 10. Lưu ý với generic kế thừa, override và bridge

### Type variable thuộc declaration nào?

Cùng chuỗi `T` có thể xuất hiện ở nhiều class/method hoàn toàn khác nhau. `TypeVariable.getGenericDeclaration()` xác định declaration sở hữu `T`. Ví dụ `Repository<T>` khác với method `<T> T identity(T input)`; gộp chúng chỉ vì tên `T` giống nhau là sai.

Khi phân tích field/method kế thừa:

- `Field.getDeclaringClass()` và `Method.getDeclaringClass()` cho biết owner của khai báo gốc.
- `subclass.getGenericSuperclass()` hoặc `getGenericInterfaces()` giúp truy vết kiểu cụ thể hóa tại class con.
- `getGenericType()` và `getGenericReturnType()` vẫn báo kiểu tại **declaration**. Muốn có kiểu áp dụng trong ngữ cảnh subclass, framework phải thay type variable có ngữ cảnh.

### Bridge methods

Compiler đôi khi sinh bridge method vì erasure của override generic/covariant return. `getDeclaredMethods()` có thể trả cả method người viết và bridge; dùng `isBridge()` / `isSynthetic()` để phân biệt theo nhu cầu. Với công cụ phân tích metadata cho người học, thường nên chọn method thực; với công cụ bytecode/debug phải xem cả bridge.

Không nên kết luận một bridge có generic return type mà người dùng trực tiếp khai báo. Hãy kiểm tra declaring class, signature raw, flags và quan hệ override.

## 11. Ngoại lệ và kiểm thử các tình huống biên

Các API generic đọc thông tin class file có thể gặp dữ liệu metadata bất thường:

| Sự cố | Tác động |
| --- | --- |
| `GenericSignatureFormatError` | Generic signature trong class file không tuân định dạng hợp lệ. |
| `TypeNotPresentException` | Generic signature tham chiếu một kiểu không tìm được/không load được. |
| `MalformedParameterizedTypeException` | Không thể dựng biểu diễn parameterized type theo signature. |
| `NoSuchFieldException` hoặc `NoSuchMethodException` | Sai thành viên hoặc chữ ký raw lúc tra cứu, không phải lỗi generic metadata. |
| `ClassCastException` trong code người dùng | Ép một `Type` là `ParameterizedType`/`TypeVariable` trực tiếp sang `Class<?>` hoặc ép nhầm loại metadata. |

Tài liệu Java SE 17 mô tả ngoại lệ cụ thể trên từng getter (`Field.getGenericType`, `Method.getGenericReturnType`, `Executable.getGenericExceptionTypes`). Phân biệt lỗi đọc generic signature với lỗi tìm field/method hay lỗi gọi method.

Các trường hợp đáng thử thêm:

- Field `String plain`: cả `getType()` và `getGenericType()` thường là `String.class`.
- Field `List raw`: generic type có thể là `Class<?>` (không phải `ParameterizedType`).
- Field `List<?>`: cần duyệt wildcard, upper bound mặc định.
- Field `T[]`: phân biệt `GenericArrayType` và `Class<?>` biểu diễn array sau erasure.
- Method `void close()`: generic return type đại diện `void`, danh sách generic throws rỗng khi không khai báo.
- Method `<E extends Exception> void fail() throws E`: exception generic là `TypeVariable E`, không phải `Exception.class`.
- Class implements `Interface<String>` hoặc extends `Base<Integer>`: thử dựng bảng type variable substitution nhiều tầng.

## 12. Bài tập thực hành

1. Thêm `public Map<String, List<T>> grouped` vào output demo; phân tích `ParameterizedType` cấp ngoài và argument `List<T>` cấp trong.
2. Thêm field `List<? super T> sink`; dùng `WildcardType.getLowerBounds()` để thấy bound dưới.
3. Với `LongRepository`, viết hàm giải `T` sang `Long` từ `getGenericSuperclass()` rồi áp dụng vào field `value` mà không thay tên field.
4. Viết method `public <R> R convert(R input)`; so sánh owner của `TypeVariable R` với type variable `T` của class.
5. Thêm method `void normal()` không khai báo `throws` và xác minh `getGenericExceptionTypes().length == 0`.
6. So sánh thông tin `throws IOException`, `throws E extends IOException` và `throws IOException, IllegalStateException`; in cả raw và generic exception arrays.
7. Phát hiện bridge method khi override method trả generic hoặc covariant return, rồi thiết kế điều kiện chọn method dùng cho documentation.
8. Thử field raw `List` cạnh `List<String>` để quan sát khác biệt `Class<?>` và `ParameterizedType`.

## 13. Tham khảo

- [Java SE 17 — Field#getGenericType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#getGenericType()): kiểu khai báo generic của field và các exception liên quan.
- [Java SE 17 — Method#getGenericReturnType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getGenericReturnType()): kiểu kết quả được khai báo sau khi phân tích signature.
- [Java SE 17 — Executable#getGenericExceptionTypes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html#getGenericExceptionTypes()): các exception types theo mệnh đề `throws`; dùng cho method và constructor.
- [Java SE 17 — Type](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html): hợp đồng của các biểu diễn Type.
- [Java SE 17 — ParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html), [TypeVariable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html), [WildcardType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/WildcardType.html), [GenericArrayType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html).
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): quy tắc xóa kiểu generic khi biên dịch.

**Ghi nhớ:** API `getType()`/`getReturnType()`/`getExceptionTypes()` trả `Class` theo kiểu sau erasure; `getGenericType()`/`getGenericReturnType()`/`getGenericExceptionTypes()` trả cấu trúc `Type` mô tả **generic declaration**. Từ khai báo này tới kiểu đã cụ thể hóa trong một subclass là một bước phân giải độc lập do công cụ cần thực hiện.

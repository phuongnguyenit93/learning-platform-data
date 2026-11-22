# Type erasure và giới hạn nhìn thấy kiểu List<String> của một instance trong Java Reflection

## 1. Một đối tượng List<String> có lưu String như một kiểu runtime không?

Giả sử Java 17+ có:

```java
List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
```

Trong mã nguồn, compiler xem `List<String>` và `List<Integer>` là hai kiểu generic khác nhau để kiểm tra tính hợp lệ của `add`, `get` và phép gán. Nhưng khi hai biến chứa object được tạo từ `new ArrayList<>()` thông thường, Java chỉ có **một runtime class `java.util.ArrayList`** cho cả hai.

```java
System.out.println(names.getClass() == numbers.getClass()); // true
```

**Type erasure** là cơ chế compiler chuyển nhiều biểu diễn generic về kiểu JVM tương ứng mà không tạo một class riêng cho mỗi type argument. Do vậy, từ một instance bình thường như `new ArrayList<String>()`, `getClass()` không cho biết đối số kiểu `String` của biểu thức nguồn. Thứ tự phần tử, lớp của từng phần tử, thậm chí việc list đang rỗng cũng không tiết lộ **khai báo generic gốc**.

Cần phân biệt:

- **Runtime class của instance:** `instance.getClass()` trả `ArrayList.class` (hoặc class implementation thực tế).
- **Generic signature của một khai báo:** `Field.getGenericType()` hoặc `Method.getGenericReturnType()` có thể đọc `List<String>` từ class-file metadata nếu field/method được khai báo như vậy.
- **Dữ liệu trong collection:** duyệt phần tử và gọi `element.getClass()` chỉ cho biết lớp của các phần tử hiện tại khác `null`, không cho biết type argument được khai báo trong source.

**Thông tin generic của khai báo có thể còn; type argument gắn riêng với một instance ArrayList thông thường thì không được tự động lưu lại.** Đây là ranh giới quan trọng nhất khi dùng Reflection.

## 2. Type erasure làm gì lúc biên dịch?

Tại compile time, Java generics giúp kiểm tra type safety. Khi tạo JVM class file, compiler áp dụng erasure:

1. Type parameter không có bound, ví dụ `T` trong `class Box<T>`, thường có erasure là `Object`.
2. Type parameter có upper bound như `T extends Number` có erasure là `Number`. Nếu có nhiều bound, quy tắc erasure dùng leftmost bound.
3. Compiler có thể chèn cast tại chỗ giá trị lấy từ generic API cần được xử lý như kiểu cụ thể.
4. Compiler có thể tạo bridge method để giữ đúng overriding/đa hình sau erasure.
5. Một số generic declarations vẫn có thuộc tính `Signature` trong class file để Reflection và công cụ đọc class file có thể phân tích.

Ví dụ:

```java
List<String> names = new ArrayList<>();
names.add("An");
String first = names.get(0);
```

Sau erasure, method `List.get(int)` có kết quả mức bytecode là `Object`. Compiler chèn kiểm tra/cast cần thiết để giá trị gán cho `String first` đáp ứng yêu cầu type nguồn. Runtime object `"An"` vẫn là một `String` thực tế; erasure **không xóa lớp của phần tử**. Điều không còn được lưu trên một object `ArrayList` thường là “nó đã được tạo ra với `<String>`”.

Vì vậy, chương trình có thể giữ được generic type safety nếu toàn bộ mã được type-check chuẩn, nhưng có thể gặp **heap pollution** nếu cố ý đi qua raw type/unchecked operations hoặc bytecode không bảo đảm những quy tắc đó.

## 3. Reflection thấy được gì?

| Câu hỏi | API thích hợp | Giới hạn |
| --- | --- | --- |
| Object đang là class nào? | `object.getClass()` | Không đọc được `<String>` từ ordinary `ArrayList` instance |
| Object có implement List không? | `object instanceof List<?>` hoặc `List.class.isInstance(object)` | Không xác định kiểu generic phần tử |
| Field được khai báo kiểu nào? | `field.getType()` | Cho kiểu đã erasure, như `List.class` |
| Field được khai báo với type arguments nào? | `field.getGenericType()` | Cho metadata của *khai báo field*, không phải nội dung runtime |
| Method được khai báo trả generic type gì? | `method.getGenericReturnType()` | Không phải kiểu concrete của object mà lần gọi hiện tại trả về |
| Method nhận tham số generic nào? | `method.getGenericParameterTypes()` | Thể hiện chữ ký khai báo, không phải actual argument |
| Class khai báo generic superclass gì? | `clazz.getGenericSuperclass()` | Có thể trả type variable `E` hoặc type argument cụ thể tùy khai báo |
| Class khai báo generic interfaces gì? | `clazz.getGenericInterfaces()` | Chỉ mô tả generic declarations của class |
| Mỗi element hiện là lớp nào? | `element.getClass()` nếu khác `null` | Không chứng minh list được khai báo `List<String>` |

Ví dụ, một field khai báo `List<String> names` có thể có `getGenericType()` trả `java.util.List<java.lang.String>`. Nếu field hiện trỏ tới `new LinkedList<String>()`, `Field.getType()` vẫn là `List.class`, `Field.getGenericType()` vẫn mô tả `List<String>`, còn `field.get(instance).getClass()` cho `LinkedList.class`. Đó là **ba loại thông tin khác nhau**.

Các local variables trong method như `List<String> local` không được Java core Reflection cung cấp một API trực tiếp tương đương `Field.getGenericType()` để hỏi kiểu khai báo của biến ấy từ chính object mà nó trỏ đến. Metadata debug/bytecode có thể chứa dữ liệu khác nhưng không phải một đặc tính runtime có thể truy xuất từ mỗi object.

## 4. Chương trình Java 17+ đầy đủ, kết quả đã kiểm chứng

Lưu tệp `ErasureInstanceDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.ArrayList;
import java.util.List;

public class ErasureInstanceDemo {
    static class Holder {
        List<String> names = new ArrayList<>();
        List<Integer> numbers = new ArrayList<>();
    }
    static class Box<T> {
        T value;
    }
    static class StringBox extends Box<String> {}

    @SuppressWarnings({"rawtypes", "unchecked"})
    static void pollute(List<String> strings) {
        List raw = strings;
        raw.add(42);
    }

    public static void main(String[] args) throws Exception {
        List<String> names = new ArrayList<>();
        List<Integer> numbers = new ArrayList<>();
        System.out.println("same runtime class = "
                + (names.getClass() == numbers.getClass()));
        System.out.println("runtime class = " + names.getClass().getName());
        System.out.println("ArrayList generic superclass = "
                + names.getClass().getGenericSuperclass().getTypeName());

        Field field = Holder.class.getDeclaredField("names");
        System.out.println("field raw type = " + field.getType().getTypeName());
        Type generic = field.getGenericType();
        System.out.println("field generic type = " + generic.getTypeName());
        System.out.println("field arg = " + ((ParameterizedType) generic)
                .getActualTypeArguments()[0].getTypeName());

        Type anonSuperclass = new ArrayList<String>() {}
                .getClass().getGenericSuperclass();
        System.out.println("anonymous superclass = "
                + anonSuperclass.getTypeName());

        Type boxFieldType = Box.class.getDeclaredField("value").getGenericType();
        System.out.println("Box.value generic type = " + boxFieldType.getTypeName());
        System.out.println("Box type parameter = "
                + ((TypeVariable<?>) boxFieldType).getName());
        System.out.println("StringBox superclass = "
                + StringBox.class.getGenericSuperclass().getTypeName());

        List<String> polluted = new ArrayList<>();
        polluted.add("ok");
        pollute(polluted);
        System.out.println("size after raw add = " + polluted.size());
        System.out.println("second element runtime = "
                + ((List<?>) polluted).get(1).getClass().getSimpleName());
        try {
            String invalid = polluted.get(1);
            System.out.println(invalid);
        } catch (ClassCastException ex) {
            System.out.println("read as String = ClassCastException");
        }
        System.out.println("List<String> instanceof List<?> = "
                + (polluted instanceof List<?>));
    }
}
```

Biên dịch hướng tới Java 17; chạy trên JDK 17 trở lên:

```bash
javac --release 17 ErasureInstanceDemo.java
java ErasureInstanceDemo
```

Stdout chính xác của lần biên dịch/chạy bằng JDK 24 với `--release 17`:

```text
same runtime class = true
runtime class = java.util.ArrayList
ArrayList generic superclass = java.util.AbstractList<E>
field raw type = java.util.List
field generic type = java.util.List<java.lang.String>
field arg = java.lang.String
anonymous superclass = java.util.ArrayList<java.lang.String>
Box.value generic type = T
Box type parameter = T
StringBox superclass = ErasureInstanceDemo$Box<java.lang.String>
size after raw add = 2
second element runtime = Integer
read as String = ClassCastException
List<String> instanceof List<?> = true
```

Phân tích:

1. Hai object tạo từ `new ArrayList<>()` có chung runtime `Class<?>`. Kiểu tham số hóa của local variables không khiến JVM tạo lớp riêng.
2. `ArrayList.class` khai báo generic superclass `AbstractList<E>`; khi đọc từ instance thường, `E` là **type variable của declaration**, không phải `String` đã gắn cho biến.
3. Field `Holder.names` khai báo trực tiếp `List<String>`, nên `Field.getGenericType()` đọc được chữ ký generic; `Field.getType()` chỉ trả raw `List`.
4. `new ArrayList<String>() {}` tạo **anonymous subclass** và ghi quan hệ `extends ArrayList<String>` trong metadata. Vì vậy có thể đọc `ArrayList<String>` từ **generic superclass của anonymous subclass**.
5. Field `Box<T>.value` được khai báo bằng type variable `T`. Reflection trực tiếp trên `Box.value` thấy `T`. `StringBox extends Box<String>` mang ánh xạ `T → String` ở metadata của quan hệ superclass; Reflection không tự đổi kiểu field khi hỏi `Box.class`.
6. `pollute` cố tình sử dụng raw List để thêm `Integer` vào object được tham chiếu qua `List<String>`. Bản thân list vẫn là List runtime hợp lệ. Lỗi xảy ra muộn, khi code muốn dùng phần tử như một `String` và cast được compiler chèn thất bại.

Đừng dùng `@SuppressWarnings` như cách “sửa” heap pollution. Annotation này chỉ loại thông báo compiler ở điểm đang cố ý minh họa thao tác unchecked; nó không đổi kiểm tra runtime.

## 5. getGenericType trả Type, không phải luôn Class<?>

Các API generic reflection trả interface `java.lang.reflect.Type`. Giá trị cụ thể có thể thuộc một số họ:

- `Class<?>`: kiểu có runtime class như `String.class`, `List.class`, `int.class`, `String[].class`.
- `ParameterizedType`: khai báo `List<String>`, `Map<String, Integer>`; đọc `getRawType()` và `getActualTypeArguments()`.
- `TypeVariable<?>`: tham số kiểu chưa được thay bằng type cụ thể, ví dụ `T` trong `Box<T>`. `getBounds()` cho bound.
- `WildcardType`: thành phần wildcard như `? extends Number` hoặc `? super Integer`, truy cập upper/lower bounds.
- `GenericArrayType`: kiểu mảng có component generic non-reifiable trong chữ ký như `T[]`.

Vì vậy, không nên viết vô điều kiện:

```java
ParameterizedType generic = (ParameterizedType) field.getGenericType();
```

Nó chỉ đúng nếu `field.getGenericType()` thực sự là `ParameterizedType`. Với `String title` hoặc raw `List values`, kết quả có thể là `Class<?>`. Với `T value` trong `Box<T>`, kết quả là `TypeVariable<?>`. Cast nhầm sẽ gây `ClassCastException`.

Một utility đọc metadata có kiểm tra, biên dịch được trên Java 17:

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;

public final class GenericFieldInspector {
    private GenericFieldInspector() {}

    public static void describe(Field field) {
        Type declared = field.getGenericType();
        System.out.println("declared type: " + declared.getTypeName());
        if (declared instanceof ParameterizedType pt) {
            System.out.println("raw: " + pt.getRawType().getTypeName());
            for (Type arg : pt.getActualTypeArguments()) {
                System.out.println("argument: " + arg.getTypeName());
            }
        }
    }
}
```

Đây là class utility độc lập có thể biên dịch khi lưu vào `GenericFieldInspector.java` nhưng **không có `main`**. Gọi `describe` từ chương trình khác với `Field` đã tra cứu. Utility phân tích declared type, không kiểm tra các phần tử đang nằm trong collection.

Với `Map<String, List<Integer>>`, argument thứ hai của `Map` lại là một `ParameterizedType`. Vì vậy công cụ giải generic đầy đủ phải đi theo **cây Type**. Với `List<? extends Number>`, argument là `WildcardType`, không phải `Number.class` chính xác. Đừng chỉ cast mọi phần tử của `getActualTypeArguments()` thành `Class<?>`.

## 6. Type variable, inheritance và giới hạn của suy luận

Ví dụ:

```java
class Box<T> {
    T value;
}
class StringBox extends Box<String> { }
```

`Box.class.getDeclaredField("value").getGenericType()` cho `T` vì field **được khai báo ở Box**. Trong khi đó, `StringBox.class.getGenericSuperclass()` mô tả `Box<String>`. Để suy ra kiểu dùng cho `value` trong ngữ cảnh `StringBox`, framework phải tự resolve ánh xạ type variables, có thể phải đi qua nhiều lớp superclass/interface.

Nếu generic declaration là `class Holder<T extends Number>` thì erasure của `T` liên quan `Number`, nhưng metadata có thể vẫn biểu diễn `T` khi dùng `getGenericType()`. Cần phân biệt **erased type dùng cho JVM** với **generic declaration được Reflection đọc qua Signature**.

Không thể dùng `getClass()` của field value để tự động suy ra mapping này: nếu field chứa `null` thì thậm chí không có runtime class, còn một object có thể là subclass của kiểu declared type.

## 7. Anonymous subclass và type token giữ generic metadata ở đâu?

So sánh:

```java
ArrayList<String> ordinary = new ArrayList<>();
ArrayList<String> captured = new ArrayList<String>() {};
```

`ordinary.getClass()` là `ArrayList.class`; generic superclass trên `ArrayList` là `AbstractList<E>`. `captured.getClass()` là một **anonymous subclass riêng**, có metadata khai báo `extends ArrayList<String>`; vì vậy `captured.getClass().getGenericSuperclass()` có thể cho `ParameterizedType` của `ArrayList<String>`.

Kỹ thuật type token tận dụng ý tưởng khai báo một subclass chứa concrete generic parameter:

```java
abstract class TypeRef<T> {
    final java.lang.reflect.Type type =
            ((java.lang.reflect.ParameterizedType)
                getClass().getGenericSuperclass())
                .getActualTypeArguments()[0];
}

// Đặt các lệnh dưới đây trong một method, với import java.util.List:
TypeRef<List<String>> ref = new TypeRef<List<String>>() {};
System.out.println(ref.type.getTypeName());
// java.util.List<java.lang.String>
```

Đây là **mã minh họa**, không phải một tệp có thể chạy độc lập: phần tạo `ref` phải đặt trong một method và cần import `List`. Cách cast trong `TypeRef` giả định caller tạo **anonymous direct subclass với superclass có tham số hóa**, không tự giải quyết trường hợp nhiều tầng kế thừa hoặc subclass raw.

**Type token không đọc kiểu generic ẩn từ một instance ArrayList bình thường.** Nó giữ `Type` do **code đã khai báo tường minh trong anonymous subclass**. Khi một framework nhận `TypeRef<List<String>>` cùng một list object, type token là *metadata bổ sung do caller cấp*. Runtime collection vẫn có thể bị nhiễm phần tử sai kiểu, và cần validation khi xử lý dữ liệu không tin cậy.

## 8. Kiểm tra thực tế từng phần tử khác với xác định List<String>

Nếu nhận `Object unknown` từ API, ta có thể xác nhận nó đang là một list chỉ gồm `String` tại thời điểm duyệt:

```java
import java.util.List;

public final class ListContents {
    private ListContents() {}

    public static boolean containsOnlyStrings(Object unknown) {
        if (!(unknown instanceof List<?> items)) {
            return false;
        }
        for (Object item : items) {
            if (!(item instanceof String)) {
                return false;
            }
        }
        return true;
    }
}
```

Đây là utility class có thể biên dịch với Java 17, không có `main`. Chính sách ví dụ coi phần tử `null` là không hợp lệ; ứng dụng khác có thể muốn cho phép `null`.

Nhưng kết quả `true` **không chứng minh** source type `List<String>`:

- Một `List<Object>` cũng có thể đang chứa toàn `String`.
- Một danh sách rỗng trả `true` dù chẳng có element nào để kiểm chứng; không suy ra được source generic argument.
- Danh sách có thể bị thay đổi sau khi kiểm tra hoặc thay đổi đồng thời.
- Element runtime có subtype của kiểu khai báo; quan sát kiểu runtime không cho biết tổng thể generic declaration.
- `(List<String>) someObject` là unchecked cast trong những bối cảnh thường gặp, không tự kiểm tra tất cả phần tử. Lỗi `ClassCastException` có thể chỉ xuất hiện khi truy cập phần tử.

Đối với serialization, mapping JSON hay binding dữ liệu, nên **dùng generic declared Type/schema do caller cung cấp** để quyết định kiểu phần tử cần chuyển đổi, sau đó validation các giá trị tương ứng. Không nên chỉ lấy `instance.getClass()` rồi suy đoán.

## 9. instanceof, generic array và tính reifiable

Trong Java, `List<String>` thường **không reifiable**: type argument `String` không được JVM kiểm tra riêng cho một List runtime. Các phép sau không hợp lệ trong mã Java thông thường:

```java
// Không hợp lệ; được comment để code mẫu không gây lỗi biên dịch:
// if (obj instanceof List<String>) { }
// Class<?> type = List<String>.class;
// List<String>[] xs = new List<String>[4];
```

`obj instanceof List<?>` hợp lệ vì `List<?>` là dạng reifiable: chỉ kiểm tra xem object có implement List không. Với array như `String[]`, JVM giữ runtime component type (`getClass().getComponentType() == String.class`). `List<?>[]` có thể được tạo, nhưng từng element trong array chỉ được kiểm tra là List chứ không có generic argument cụ thể.

Đừng nhầm **array covariance** với **generic invariance**. `String[]` có thể gán cho `Object[]` và gặp `ArrayStoreException` nếu ghi object sai kiểu, nhưng `List<String>` không phải subtype của `List<Object>`. Điều này giúp hiểu vì sao Java cấm tạo trực tiếp `new List<String>[...]`: runtime array kiểm tra component class, còn generic parameter `String` đã bị erasure.

Một biểu hiện của erasure là không thể khai báo hai overload chỉ khác generic argument:

```java
// Hai overload dưới đây nếu cùng nằm trong một class sẽ bị name clash:
// void handle(List<String> strings) {}
// void handle(List<Integer> numbers) {}
```

Vì cả hai bị erasure về chữ ký JVM với một tham số `List`, không có cách chọn overload theo `<String>` hay `<Integer>` lúc chạy.

## 10. Checklist cho người viết công cụ Reflection

1. **Nếu cần runtime class**, hỏi `getClass()` và chấp nhận rằng nó chỉ phản ánh implementation, không tự tái tạo `List<String>`.
2. **Nếu cần generic declaration**, xác định *vị trí khai báo*: field, method return/parameter, constructor parameter, generic superclass hoặc interface. Dùng API `getGeneric...` tương ứng.
3. **Nếu đang cầm một Type**, kiểm tra biến thể `Class`/`ParameterizedType`/`TypeVariable`/`WildcardType`/`GenericArrayType` trước khi cast. Với generic nested types, duyệt cây Type.
4. **Nếu generic type là T**, cần phân tích quan hệ inheritance và ánh xạ TypeVariable theo context. Không lấy class của giá trị field để kết luận declaration.
5. **Nếu cần runtime type token**, yêu cầu caller khai báo nó tường minh hoặc sử dụng generic declaration của API. Đừng nghĩ `new ArrayList<String>()` thông thường tự tạo được token.
6. **Nếu cần bảo đảm dữ liệu**, định nghĩa schema và validation từng phần tử; lưu ý list rỗng, null, raw types, unchecked casts và concurrency.
7. **Nếu chẩn đoán class file**, có thể dùng `javap -v` xem attribute `Signature`. Cần kiểm tra đúng artifact và classloader đang được sử dụng; toolchain/obfuscation có thể ảnh hưởng metadata.
8. **Nếu chỉ gọi generic API với code Java bình thường**, ưu tiên type checking của compiler. Reflection phù hợp khi schema và type metadata chỉ được xác định lúc runtime.

## 11. Các lỗi phổ biến

| Nhận định | Điều đúng |
| --- | --- |
| “`List<String>` và `List<Integer>` tạo hai runtime class khác nhau” | Ordinary `new ArrayList<>()` của cả hai vẫn có runtime class `ArrayList` |
| “`getClass()` cho biết type argument `String`” | Chỉ cho runtime class implementation |
| “`Field.getGenericType()` chứng minh tất cả phần tử là String” | Nó chỉ mô tả type khai báo của field |
| “`getGenericType()` luôn cast được thành `ParameterizedType`” | Nó có thể là `Class`, `TypeVariable` hoặc loại `Type` khác |
| “Lấy phần tử đầu tiên sẽ biết generic type gốc” | Sai với list rỗng, null, subtype hoặc list khai báo `List<Object>` |
| “Anonymous subclass khiến mọi ArrayList đều có type argument runtime” | Generic signature chỉ nằm trong khai báo superclass của subclass cụ thể |
| “`instanceof List<String>` hợp lệ” | Dùng `instanceof List<?>`; không kiểm tra được `String` generic argument |
| “Unchecked cast sang `List<String>` kiểm tra toàn bộ phần tử” | Không; type pollution có thể lộ khi đọc |
| “`T extends Number` bị erasure thành Object trong mọi trường hợp” | Erasure dùng bound, với ví dụ này là `Number` |
| “Type token bảo đảm dữ liệu collection đúng schema” | Type token mô tả type được khai báo; dữ liệu phải được kiểm tra riêng |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `List<String> a = new ArrayList<>(); List<Integer> b = new ArrayList<>();`. `a.getClass() == b.getClass()` là gì? **`true`** (cùng runtime class `ArrayList`).

**Câu 2.** Field `List<String> names` có hai cách đọc `getType()` và `getGenericType()`. Chúng khác nhau thế nào? **`getType()` cho raw `List.class`; `getGenericType()` có thể cho `ParameterizedType` mô tả `List<String>`**.

**Câu 3.** Một list chỉ chứa `String` chứng minh nó được khai báo `List<String>`? **Không**. `List<Object>`, `List<CharSequence>` hoặc raw list cũng có thể chứa chỉ String.

**Câu 4.** Một anonymous `new ArrayList<String>() {}` giữ được gì? **Chữ ký generic `extends ArrayList<String>` trong class của anonymous subclass**; không phải metadata tự động trên object `ArrayList` bình thường.

**Câu 5.** `Box<T>.value` khi đọc từ `Box.class` trong chương trình ví dụ trả `String` hay `T`? **`T`**. Muốn resolve sang `String` trong ngữ cảnh `StringBox` phải phân tích superclass metadata.

**Câu 6.** Tại sao có thể xảy ra `ClassCastException` khi đọc từ `List<String>`? Một raw/unchecked operation có thể đưa `Integer` vào list; cast compiler dùng khi đọc dưới dạng String thất bại.

**Câu 7.** List rỗng có thể chứng minh type argument từ các phần tử? **Không**. Không có element nào để kiểm tra.

**Câu 8.** `obj instanceof List<?>` cho biết điều gì? **Chỉ rằng object là List runtime**, không xác minh element type.

## 13. Nguồn tài liệu chính thức

- [Java Language Specification 17, Section 4.6: Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6)
- [Java Language Specification 17, Section 4.7: Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7)
- [Java SE 17 Javadoc: Type](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html)
- [Java SE 17 Javadoc: ParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html)
- [Java SE 17 Javadoc: Field.getGenericType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Java SE 17 Javadoc: Class generic superclass and interfaces](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [JVM Specification 17, Section 4.7.9: Signature Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.9)

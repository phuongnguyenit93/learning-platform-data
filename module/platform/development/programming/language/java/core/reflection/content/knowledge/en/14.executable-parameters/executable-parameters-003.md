# `getParameterTypes()` khác `getGenericParameterTypes()` trong Java Reflection

## 1. Mục tiêu: phân biệt kiểu tham số runtime và chữ ký generic

Khi dùng Reflection trên `Method` hoặc `Constructor<?>`, hai phương thức cùng mô tả tham số của một *executable* nhưng trả về các biểu diễn khác nhau:

- **`getParameterTypes()`** trả `Class<?>[]`: các lớp/kiểu thực tế theo **chữ ký đã erasure** (kiểu mà JVM dùng làm parameter descriptor). Nó phù hợp để tra cứu method/constructor theo chữ ký và xử lý kiểu runtime.
- **`getGenericParameterTypes()`** trả `java.lang.reflect.Type[]`: các kiểu tham số theo **thông tin generic trong khai báo** nếu metadata hiện diện. Nó có thể phản ánh `List<String>`, `T`, `T[]`, `? extends Number`…, thay vì chỉ kiểu erasure.

Cả hai là thành viên của lớp cha `java.lang.reflect.Executable`, nên dùng được cho **`Method` lẫn `Constructor`**. Các mảng được trả theo thứ tự tham số, nhưng có một ngoại lệ quan trọng ở constructor có tham số ngầm (mục 7).

| Tiêu chí | `getParameterTypes()` | `getGenericParameterTypes()` |
| --- | --- | --- |
| Kiểu trả về | `Class<?>[]` | `Type[]` |
| `List<String>` | `List.class` | `ParameterizedType` biểu diễn `List<String>` |
| `T extends Number` | `Number.class` (erasure của `T`) | `TypeVariable` biểu diễn `T` |
| `T[]` | `Number[].class` nếu erasure `T` là `Number` | `GenericArrayType` cho `T[]` |
| `String[]` | `String[].class` | Thường là `Class` biểu diễn `String[]` |
| Nhận biết wildcard | Không còn wildcard trong `Class<?>` | Wildcard nằm trong `ParameterizedType`, truy cập qua `WildcardType` |
| Chọn overload / lookup | **Đúng API**: dùng các `Class<?>` erasure để tìm phương thức | Không truyền trực tiếp `Type[]` vào `getDeclaredMethod(...)` |
| Mô tả generic cho schema/serialization | Không có generic arguments | Có thể lấy generic arguments/bounds từ chữ ký |
| Phụ thuộc chữ ký generic metadata | Không cần metadata `Signature` để có erased parameter types | Thông tin generic chi tiết phụ thuộc vào generic signature được lưu trong class file |

**Không nên hiểu `getGenericParameterTypes()` là “lấy kiểu thật của object đang truyền vào”**. Cả hai đọc **khai báo của method/constructor**, không đọc dữ liệu của các instance tham số lúc ứng dụng chạy.

## 2. Căn nguyên: type erasure trong Java

Generics của Java chủ yếu thực hiện kiểm tra kiểu lúc biên dịch. Sau khi biên dịch, JVM method descriptor sử dụng các kiểu đã xóa phần lớn thông tin generic (**type erasure**). Ví dụ các khai báo:

```java
void save(java.util.List<String> values) {}
void accept(T number) {}
```

Đây là **mảnh minh họa**, và `T` phải được khai báo ở cấp class hoặc method. Nếu `T extends Number`, kiểu erasure của `T` là `Number`. `List<String>` có kiểu erasure là `List`. Phần `String` và biến kiểu `T` có thể được ghi vào thuộc tính generic signature của class file, giúp Reflection tái tạo `Type` với nhiều chi tiết hơn.

Các quy tắc cốt lõi:

1. `List<String>` và `List<Integer>` có **cùng kiểu erasure `List`**; do đó không thể có hai overload chỉ khác nhau ở hai generic arguments này.
2. Với `<T extends Number & Comparable<T>>`, erasure của `T` là **bound đầu tiên** `Number`. Với biến kiểu không có bound tường minh, bound ngầm là `Object`.
3. Nếu kiểu parameter là `T[]`, sau erasure `T` thành bound đầu tiên, nên parameter descriptor là mảng của kiểu bound ấy. Generic form vẫn có thể là `GenericArrayType`.
4. `String...` là cú pháp tham số varargs; ở JVM, kiểu tham số tương ứng là **`String[]`**. `Executable.isVarArgs()` cho biết executable có khai báo varargs hay không.
5. `getGenericParameterTypes()` không bảo đảm từng `Type` đều là một `ParameterizedType`: kiểu không generic như `int`, `String` hay `String[]` thường vẫn được biểu diễn bởi `Class<?>`.

Vì vậy hai API không mâu thuẫn: một API cung cấp danh sách kiểu cho **chữ ký runtime**, API kia giữ lại **ngữ nghĩa generic của khai báo** khi có dữ liệu.

## 3. Ví dụ Java 17+ đầy đủ, biên dịch và chạy được

Tạo tệp **`ParameterKindsDemo.java`** với mã sau (không khai báo `package`):

```java
import java.lang.reflect.*;
import java.util.*;

public class ParameterKindsDemo {
    public ParameterKindsDemo(List<Integer> values) {}

    public static <T extends Number & Comparable<T>> void analyze(
            List<String> names,
            Map<String, ? extends Number> scores,
            T value,
            T[] history,
            List<? super Integer> sink,
            String... tags) {}

    private static String kind(Type type) {
        if (type instanceof Class<?>) return "Class";
        if (type instanceof ParameterizedType) return "ParameterizedType";
        if (type instanceof TypeVariable<?>) return "TypeVariable";
        if (type instanceof GenericArrayType) return "GenericArrayType";
        if (type instanceof WildcardType) return "WildcardType";
        return "Other";
    }

    private static void describe(Executable executable) {
        System.out.println("member: " + (executable instanceof Method
                ? executable.getName() : "<init>"));
        System.out.println("varargs: " + executable.isVarArgs());
        Class<?>[] erased = executable.getParameterTypes();
        Type[] generic = executable.getGenericParameterTypes();
        for (int i = 0; i < erased.length; i++) {
            System.out.println(i + ": " + erased[i].getTypeName()
                    + " | " + generic[i].getTypeName()
                    + " | " + kind(generic[i]));
        }
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterKindsDemo.class.getDeclaredMethod(
                "analyze", List.class, Map.class, Number.class,
                Number[].class, List.class, String[].class);
        describe(method);
        Constructor<ParameterKindsDemo> constructor =
                ParameterKindsDemo.class.getDeclaredConstructor(List.class);
        describe(constructor);

        ParameterizedType map = (ParameterizedType)
                method.getGenericParameterTypes()[1];
        WildcardType wildcard = (WildcardType) map.getActualTypeArguments()[1];
        System.out.println("upper bound: "
                + Arrays.toString(wildcard.getUpperBounds()));
        TypeVariable<Method> t = method.getTypeParameters()[0];
        System.out.println("T bounds: " + Arrays.toString(t.getBounds()));
    }
}
```

Trong thư mục chứa file, chạy:

```bash
javac ParameterKindsDemo.java
java ParameterKindsDemo
```

**Kết quả đã xác minh:**

```text
member: analyze
varargs: true
0: java.util.List | java.util.List<java.lang.String> | ParameterizedType
1: java.util.Map | java.util.Map<java.lang.String, ? extends java.lang.Number> | ParameterizedType
2: java.lang.Number | T | TypeVariable
3: java.lang.Number[] | T[] | GenericArrayType
4: java.util.List | java.util.List<? super java.lang.Integer> | ParameterizedType
5: java.lang.String[] | java.lang.String[] | Class
member: <init>
varargs: false
0: java.util.List | java.util.List<java.lang.Integer> | ParameterizedType
upper bound: [class java.lang.Number]
T bounds: [class java.lang.Number, java.lang.Comparable<T>]
```

**Phân tích từng dòng:**

- Tham số 0: `List<String>` bị erasure thành `List`. `getParameterTypes()[0]` trả `List.class`; `getGenericParameterTypes()[0]` là `ParameterizedType` giữ đối số kiểu `String`.
- Tham số 1: `Map<String, ? extends Number>` bị erasure thành `Map`. Generic form giữ cả hai type arguments; phần thứ hai là `WildcardType` với upper bound `Number`.
- Tham số 2: `T` bị erasure thành `Number` bởi bound đầu tiên. Generic form là `TypeVariable` có tên `T`.
- Tham số 3: `T[]` có erasure `Number[]`, còn generic form là `GenericArrayType` mà component type là `T`.
- Tham số 4: `List<? super Integer>` bị erasure thành `List`, nhưng generic form giữ wildcard với lower bound `Integer`.
- Tham số 5: `String...` là `String[]` trên cả hai kết quả, và `isVarArgs()` là `true`. Không phải mọi `Type` ở generic array đều là cấu trúc generic phức tạp.
- Constructor nhận `List<Integer>`: hai API hoạt động giống như trên method; constructor có `ParameterizedType` cho tham số này.
- `method.getTypeParameters()[0]` lấy **biến kiểu khai báo bởi method `<T ...>`**. `getBounds()` cho biết hai bounds `Number` và `Comparable<T>`, trong khi erasure lấy bound đầu tiên.

Tên lớp triển khai cụ thể của `ParameterizedType` hay `TypeVariable` do JDK quyết định; ví dụ chỉ in các **giao diện** `Type` ổn định thay vì phụ thuộc vào tên nội bộ như `ParameterizedTypeImpl`.

## 4. Làm việc đúng với mô hình `Type`

`java.lang.reflect.Type` là giao diện chung. Các hình thái cần hiểu:

| Hình thái `Type` | Ví dụ kiểu khai báo | Cách phân tích |
| --- | --- | --- |
| `Class<?>` | `String`, `int`, `String[]`, kiểu raw `List` | `Class#getName()`, `isArray()`, `getComponentType()` |
| `ParameterizedType` | `List<String>`, `Map<String, List<Integer>>` | `getRawType()`, `getActualTypeArguments()`, `getOwnerType()` |
| `TypeVariable<?>` | `T` trong `<T extends Number>` | `getName()`, `getBounds()`, `getGenericDeclaration()` |
| `GenericArrayType` | `T[]`, `List<String>[]` trong chữ ký hợp lệ | `getGenericComponentType()` |
| `WildcardType` | `? extends Number`, `? super Integer` | `getUpperBounds()`, `getLowerBounds()` |

Một `WildcardType` thường xuất hiện **bên trong đối số kiểu của `ParameterizedType`** (ví dụ `List<? super Integer>`), không nhất thiết là `Type` trả trực tiếp cho một formal parameter; Java không cho khai báo tham số có kiểu đứng một mình là `?`.

Ví dụ kiểm tra generic arguments trong `Map<String, ? extends Number>` dựa trên `method` của chương trình ở mục 3:

```java
Type parameter = method.getGenericParameterTypes()[1];

if (parameter instanceof ParameterizedType p) {
    System.out.println(p.getRawType().getTypeName()); // java.util.Map
    for (Type argument : p.getActualTypeArguments()) {
        System.out.println(argument.getTypeName());
    }
}
```

Đây là **mảnh mã đặt trong method**. Nội dung hai argument lần lượt là `java.lang.String` và `? extends java.lang.Number`. Nếu cần đọc bound, kiểm tra `argument instanceof WildcardType` rồi dùng `getUpperBounds()`/`getLowerBounds()`. Không ép trực tiếp wildcard thành `Class<?>`.

Với `T[]`, nếu `type instanceof GenericArrayType array`, hãy kiểm tra `array.getGenericComponentType()`: ở đây là biến kiểu `T`. Nếu kiểu tham số vốn là mảng thông thường như `String[]`, `type instanceof Class<?> clazz` và `clazz.isArray()` đúng; đây là hai đường xử lý khác nhau.

### Kiểu raw và khi không có thông tin generic chi tiết

Nếu parameter được khai báo **`List values`** (raw type), `getGenericParameterTypes()` có thể trả một `Class` tương ứng `List.class`. Không có `String`/`Integer` nào để suy ra. Nếu class file thiếu hoặc không giữ được metadata generic thích hợp, API không thể tự phục hồi type arguments từ dữ liệu runtime. Cần cung cấp schema, `Type` token hoặc metadata riêng nếu logic phụ thuộc vào generic argument.

Không dùng chuỗi `type.getTypeName()` như đầu vào duy nhất để phân tích generic: định dạng chuỗi thuận tiện để hiển thị, nhưng để xây dựng schema đáng tin nên đi theo cấu trúc `ParameterizedType`, `TypeVariable`, `WildcardType` và `GenericArrayType`.

## 5. Tra cứu executable: dùng kiểu sau erasure

`Class.getDeclaredMethod(String, Class<?>...)` và `Class.getMethod(String, Class<?>...)` nhận **`Class<?>` của formal parameter types**, không nhận đối tượng `ParameterizedType`. Trong ví dụ mục 3, lệnh tra cứu đúng là:

```java
Method method = ParameterKindsDemo.class.getDeclaredMethod(
        "analyze",
        List.class,
        Map.class,
        Number.class,
        Number[].class,
        List.class,
        String[].class);
```

Đây là **mảnh mã** có thể đặt trong phương thức khai báo `throws NoSuchMethodException`. Việc truyền `Number.class`/`Number[].class` cho `T`/`T[]` tương ứng với erasure của bounded variable; `String[].class` là descriptor đúng cho varargs `String...`. `List<String>.class` hoặc `List<Integer>.class` **không tồn tại trong cú pháp class literal Java**.

Ví dụ hai khai báo sau trong cùng class **không hợp lệ**, do có cùng name và erasure:

```java
// Minh họa lỗi biên dịch: name clash (không đặt cả hai trong class thực tế)
void handle(List<String> values) {}
void handle(List<Integer> values) {}
```

Nếu đang viết bộ chọn method overload, đừng so sánh generic arguments như thể JVM phân biệt hai overload ở cùng chữ ký erasure. Dùng `Class<?>[]` để lookup, rồi kiểm tra `Type[]` cho chính sách nghiệp vụ (chẳng hạn validation/serialization).

### Chữ ký generic không phải kiểm tra kiểu động của dữ liệu

Giả sử khai báo `void save(List<String> values)`. `getGenericParameterTypes()[0]` có thể mô tả `List<String>`, nhưng không có nghĩa runtime kiểm chứng rằng từng phần tử trong một `List` luôn là `String`. Với raw types, unchecked casts hoặc reflection, dữ liệu thực tế có thể không tuân theo ý nghĩa generic ở nguồn Java. Một thư viện serializer muốn xác minh dữ liệu cần kiểm tra giá trị và chính sách riêng.

## 6. Tham số `Parameter`, tên tham số và type-use annotations

Ngoài hai mảng ở trên, `Executable` còn cung cấp:

- `getParameters()` → `Parameter[]`: metadata của từng formal parameter, tên (nếu có), modifiers, tình trạng implicit/synthetic.
- `Parameter.getType()` → `Class<?>` (erasure).
- `Parameter.getParameterizedType()` → `Type` (thông tin generic của parameter đó).
- `getAnnotatedParameterTypes()` → `AnnotatedType[]`: type-use annotations tại vị trí kiểu tham số (ví dụ chú thích `@NonNull` đặt trên type use nếu annotation hỗ trợ `ElementType.TYPE_USE` và được giữ ở runtime).
- `getParameterCount()` → số lượng formal parameters theo mô hình executable.
- `isVarArgs()` → phân biệt khai báo varargs với tham số mảng thông thường.
- `getTypeParameters()` → `TypeVariable<?>[]` được khai báo trên executable (khác với mảng `Type[]` của các tham số).

**Biên dịch bằng `javac -parameters`** giúp ghi tên tham số nguồn vào class file để `Parameter.getName()` có thể cung cấp tên thực (trong điều kiện phù hợp), và `isNamePresent()` cho biết tên có mặt. Nó **không phải là cờ bật generic signatures**. `getGenericParameterTypes()` vẫn có thể đọc generic signature của bytecode được biên dịch thông thường khi metadata đó tồn tại.

Ví dụ, nếu `method.getParameters()[0].getName()` trả tên như `arg0` thì không thể tự kết luận generic type của parameter đã biến mất; metadata tên và metadata generic là hai cơ chế khác nhau.

## 7. Bẫy tinh vi: tham số ngầm ở constructor inner class

Một số constructor có **tham số ngầm hoặc synthetic** do trình biên dịch tạo ra, đặc biệt constructor của non-static inner class. Javadoc của `Executable.getGenericParameterTypes()` cảnh báo rằng **số lượng phần tử có thể khác `getParameterTypes()`**, tùy class file có generic information hay không: khi generic information hiện diện, API có thể chỉ báo các tham số được khai báo tường minh trong source; những tham số implicit/synthetic có thể không xuất hiện trong mảng generic.

Đây là ví dụ Java 17+ độc lập. Tạo tệp **`InnerReflectionDemo.java`**:

```java
import java.lang.reflect.*;
import java.util.*;

public class InnerReflectionDemo {
    class Inner {
        Inner(List<String> names) {}
    }

    public static void main(String[] args) {
        Constructor<?> c = Inner.class.getDeclaredConstructors()[0];
        System.out.println("raw count: " + c.getParameterTypes().length);
        System.out.println("generic count: " + c.getGenericParameterTypes().length);

        for (Class<?> type : c.getParameterTypes()) {
            System.out.println("raw: " + type.getTypeName());
        }
        for (Type type : c.getGenericParameterTypes()) {
            System.out.println("generic: " + type.getTypeName());
        }
    }
}
```

Chạy:

```bash
javac InnerReflectionDemo.java
java InnerReflectionDemo
```

Kết quả đã xác minh với `javac` thông thường:

```text
raw count: 2
generic count: 1
raw: InnerReflectionDemo
raw: java.util.List
generic: java.util.List<java.lang.String>
```

Lớp `Inner` là non-static inner class nên JVM constructor nhận **tham chiếu đến instance của `InnerReflectionDemo`** để xác định enclosing instance; tham số này không được viết trong source constructor `Inner(List<String> names)`. Vì vậy `getParameterTypes()` liệt kê hai tham số runtime (`InnerReflectionDemo` và `List`), trong khi generic signature mô tả tham số khai báo tường minh là `List<String>`.

**Hệ quả:** Không mặc định rằng `getParameterTypes()[i]` luôn tương ứng với `getGenericParameterTypes()[i]` ở mọi executable; vòng `for` trong ví dụ mục 3 **được viết cho method/constructor không có tham số ngầm**, không phải một bộ phân tích generic tổng quát cho mọi constructor. Trước khi ghép chỉ số, kiểm tra độ dài và tham số implicit/synthetic; nếu cần metadata theo từng tham số, cân nhắc `getParameters()` cùng `Parameter.getParameterizedType()` và đặc điểm biên dịch của class. Các trường hợp constructor của enum, inner class hoặc bytecode được tạo bởi công cụ cần được xem xét riêng thay vì đoán tương quan chỉ số.

Chính vì sự khác biệt metadata này, một chương trình khai thác Reflection tổng quát cần tránh giả thiết hai mảng có độ dài bằng nhau. Lỗi `ArrayIndexOutOfBoundsException` hay gán nhầm generic type cho enclosing instance là hậu quả có thể xảy ra nếu cứ lặp theo chiều dài `getParameterTypes()` rồi đọc `generic[i]`.

## 8. Trường hợp khó và những ngoại lệ khi đọc generic signature

Các API generic Reflection phụ thuộc metadata chữ ký được biên dịch/cung cấp. Theo Javadoc `Executable.getGenericParameterTypes()`, một số lỗi có thể xảy ra khi đọc chữ ký của bytecode không hợp lệ hoặc không còn nhất quán:

| Ngoại lệ / Error | Nguyên nhân |
| --- | --- |
| `GenericSignatureFormatError` | Generic signature trong class file không tuân định dạng JVM |
| `TypeNotPresentException` | Generic signature tham chiếu kiểu không thể tìm thấy |
| `MalformedParameterizedTypeException` | Một parameterized type trong chữ ký không thể tạo dưới mô hình phản chiếu |

Đây không phải kết quả thông thường khi biên dịch Java chuẩn trên classpath/module path nhất quán, nhưng hữu ích khi xử lý bytecode cũ, bytecode generator, shading, version mismatch hoặc thư viện bị thiếu. Không nên dùng `catch (Exception)` để ngầm coi mọi dữ liệu signature lỗi là “không generic”; `GenericSignatureFormatError` là `Error`, không phải `Exception`.

Các lưu ý khác:

- `getDeclaredMethods()` có thể thấy **bridge/synthetic methods** do compiler tạo. Khi suy luận về API nguồn, kiểm tra `Method.isBridge()`/`isSynthetic()`; bản bridge có chữ ký sau erasure khác method nguồn.
- Raw type trong signature có thể chỉ được biểu diễn bằng `Class<?>`; `getGenericParameterTypes()` không hứa trả `ParameterizedType` cho mọi parameter.
- Với `TypeVariable`, bounds của method/class được khai báo độc lập; cùng tên `T` trong hai method không nhất thiết cùng declaration. Có thể dùng `getGenericDeclaration()` để biết biến kiểu thuộc nơi khai báo nào.
- `getGenericParameterTypes()` giữ những thông tin generic còn có trong **declaration**, không thể dựng `List<String>` từ `List<?>` do caller truyền hoặc suy ra `String` từ phần tử hiện tại.

## 9. Quy trình áp dụng khi viết framework

1. **Xác định mục đích:** cần tìm executable/gọi method theo chữ ký JVM, hay cần hiểu generic contract để chuyển đổi JSON, binding, validation?
2. **Tìm executable bằng erased types:** dùng `getDeclaredMethod(name, Class<?>...)`, `getDeclaredConstructor(Class<?>...)` hoặc liệt kê danh sách rồi lọc. Với overload, số/loại erased formal parameters là dữ kiện quan trọng.
3. **Đọc generic contract:** gọi `getGenericParameterTypes()` (hoặc `Parameter.getParameterizedType()` nếu cần metadata theo từng tham số) và phân tích `Type` theo loại thực tế.
4. **Xử lý type variables, wildcards và generic arrays:** duyệt cấu trúc `Type`; không ép mọi `Type` về `Class<?>`. Nếu cần resolve `T` trong subclass cụ thể, phải có **binding ngữ cảnh** từ generic superclass/interfaces hoặc type token; Reflection không tự thay `T` bằng type argument của mọi lời gọi.
5. **Cẩn trọng với tham số ngầm:** nếu là constructor đặc biệt, không căn theo chỉ số hai mảng trước khi xác nhận tương ứng.
6. **Kiểm tra đầu vào thật ở runtime:** chữ ký generic mô tả khai báo, còn dữ liệu thực tế cần validation riêng.
7. **Báo lỗi metadata minh bạch:** xử lý trường hợp signature không hợp lệ hoặc thiếu dependency; đừng tạo schema sai khi thông tin generic không đủ.

Ví dụ chọn đúng API:

| Mục tiêu | Ưu tiên |
| --- | --- |
| Tìm method có tham số `List<String>` trong class | `getDeclaredMethod("name", List.class)` |
| Xác định list element type khai báo | `getGenericParameterTypes()` rồi đọc `ParameterizedType.getActualTypeArguments()` |
| Tìm bound của `T extends Number` | `TypeVariable.getBounds()` |
| Kiểm tra phương thức có varargs | `Executable.isVarArgs()` |
| Phân tích type-use annotation | `getAnnotatedParameterTypes()` |
| Lấy tên tham số nguồn nếu còn metadata | `getParameters()` và `Parameter.isNamePresent()` |
| Thực hiện method với tham số tại runtime | Chuẩn bị object đúng erased types rồi gọi `Method.invoke(...)`; không dùng `ParameterizedType` làm runtime `Class` |

## 10. Sai lầm phổ biến và bài tập tự kiểm tra

| Quan niệm sai | Cách hiểu đúng |
| --- | --- |
| “Hai API chỉ khác kiểu trả về mảng, thông tin giống nhau.” | Một bên là `Class<?>` erasure; bên kia có cấu trúc `Type` mô tả generic declaration. |
| “`getGenericParameterTypes()[0]` luôn là `ParameterizedType`.” | Có thể là `Class`, `TypeVariable` hoặc `GenericArrayType`; tùy khai báo. |
| “`getParameterTypes()` cho `List<String>`.” | Kết quả là `List.class`; generic argument đã erasure. |
| “Có thể ép `Type` thành `Class<?>` cho mọi tham số.” | Cast sai với parameterized type/type variable/generic array. |
| “Hai mảng luôn dài bằng nhau.” | Constructor inner class có tham số ngầm có thể khiến kích thước khác nhau. |
| “`-parameters` mới làm generic Reflection hoạt động.” | Cờ này chủ yếu lưu **tên tham số**, không phải điều kiện chung để lưu generic signature. |
| “Metadata `List<String>` chứng minh mọi phần tử trong List runtime đều là String.” | Generic type ở khai báo không thay thế kiểm tra dữ liệu runtime. |
| “Có thể overload `handle(List<String>)` và `handle(List<Integer>)`.” | Hai chữ ký có erasure giống nhau nên clash khi cùng một phạm vi khai báo. |

**Bài tập 1.** Cho `void f(List<? extends CharSequence> x, int[] y)`. Dự đoán hai mảng từ `getParameterTypes()` và `getGenericParameterTypes()`, và giải thích vì sao `int[]` thường là `Class<?>` trong cả hai.

**Bài tập 2.** Cho `<T extends Serializable & Comparable<T>> void f(T x, T[] xs)`. Dự đoán erasure của hai parameter và cách lấy cả hai bounds. `Serializable` là bound đầu tiên trong khai báo này.

**Bài tập 3.** Dùng `ParameterizedType` để lấy `String` từ `List<String>`, rồi thay tham số bằng `List<? super Integer>` và xem lower bounds của `WildcardType`.

**Bài tập 4.** Tạo một non-static inner class có constructor nhận `List<String>`, chạy ví dụ mục 7 và lý giải sự khác biệt về số phần tử.

**Bài tập 5.** Viết logic tra cứu method `analyze` ở mục 3 bằng `getDeclaredMethod` mà không dùng bất kỳ generic `Type` nào, sau đó dùng `getGenericParameterTypes` để hiển thị danh sách kiểu khai báo đầy đủ.

**Ghi nhớ:** `getParameterTypes()` cho **`Class<?>[]` theo chữ ký đã erasure**, còn `getGenericParameterTypes()` cho **`Type[]` phản ánh generic signature khi có metadata**. Cần chọn API theo mục đích, phân tích các dạng `Type` đúng cách, và đặc biệt không mặc định hai mảng luôn tương ứng 1:1 trong constructor có tham số ngầm.

## 11. Tham khảo chính thức

- [Javadoc Java SE 17 — `Executable.getParameterTypes` và `getGenericParameterTypes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html) — ngữ nghĩa, lưu ý tham số ngầm và các ngoại lệ khi đọc chữ ký.
- [Javadoc Java SE 17 — `ParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html) — `getActualTypeArguments`, `getRawType`.
- [Javadoc Java SE 17 — `TypeVariable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html) — `getName`, `getBounds` và declaration.
- [Javadoc Java SE 17 — `GenericArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html) — generic component type.
- [Javadoc Java SE 17 — `WildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/WildcardType.html) — upper/lower bounds.
- [Javadoc Java SE 17 — `Class.getDeclaredMethod`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getDeclaredMethod(java.lang.String,java.lang.Class...)) — tra cứu method bằng danh sách `Class<?>`.
- [Java Language Specification `4.6 Erasure`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6) — quy tắc xóa generic types.
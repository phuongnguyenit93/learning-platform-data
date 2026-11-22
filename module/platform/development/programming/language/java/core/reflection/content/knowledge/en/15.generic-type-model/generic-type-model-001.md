# Class khác Type: mô hình kiểu generic trong Java Reflection

## 1. Vì sao chỉ dùng Class<?> là chưa đủ?

Trong Java, `Class<?>` mô tả một lớp, interface, enum, record, kiểu nguyên thủy hoặc kiểu mảng mà JVM biết ở thời điểm chạy. Chẳng hạn:

~~~java
Class<?> stringType = String.class;
Class<?> listType = java.util.List.class;
Class<?> arrayType = String[].class;
~~~

Nhưng khi xét Java Generics, có những cách viết kiểu mang thêm thông tin mà chỉ một đối tượng `Class<?>` không diễn đạt đủ:

~~~java
java.util.List<String>
java.util.List<? extends Number>
T
T[]
java.util.List<String>[]
~~~

Hai khai báo `List<String>` và `List<Integer>` đều có **raw class** là `List.class`, nhưng phần tử kiểu (`String` hay `Integer`) khác nhau. Muốn đọc **chữ ký generic** còn được lưu ở class file, Reflection cung cấp giao diện `java.lang.reflect.Type` và một số dạng triển khai của nó.

**Điểm cốt lõi:** `Class<?>` **là một dạng `Type`**, nhưng **không phải mọi `Type` đều là `Class<?>`**. Một `Type` có thể biểu diễn một lớp thông thường, một generic type đã được tham số hóa, biến kiểu, wildcard hoặc kiểu mảng có thành phần là kiểu generic.

Bài này giúp bạn biết khi nào dùng `Class<?>`, khi nào cần `Type`, cách phân loại các dạng `Type`, và hiểu điều gì thật sự còn tồn tại sau **type erasure**.

## 2. So sánh Class<?> và Type

| Câu hỏi | `Class<?>` | `Type` |
| --- | --- | --- |
| Vai trò | Đại diện cho một kiểu runtime đã được JVM nhận diện | Giao diện chung mô tả các kiểu trong metadata Java, bao gồm chữ ký generic |
| Có biểu diễn `String.class` không? | Có | Có, vì `Class` triển khai `Type` |
| Có chứa đối số `String` của `List<String>` không? | Không: `List.class` chỉ là kiểu thô | Có thể, qua `ParameterizedType` |
| Có thể là một biến kiểu `T` không? | Không có `Class` riêng cho mỗi `T` | Có, qua `TypeVariable<?>` |
| Có biểu diễn `? extends Number` không? | Không | Có, qua `WildcardType` |
| Có biểu diễn `T[]` không? | `Class` chỉ đại diện cho dạng mảng sau xóa kiểu | Có, qua `GenericArrayType` |
| Có các API như `getDeclaredMethods()`, `getConstructor()`, `isAssignableFrom()`? | Có | Không; `Type` chỉ có API chung như `getTypeName()` |

`Type` là một **interface**, không phải “Class nâng cấp” có tất cả hàm của `Class`. Nếu bạn có một biến kiểu `Type`, không thể gọi trực tiếp `type.getDeclaredMethods()` mà chưa chứng minh nó là `Class<?>`.

~~~java
Type type = String.class;
if (type instanceof Class<?> clazz) {
    System.out.println(clazz.getSimpleName()); // String
}
~~~

Đoạn này minh họa với import `java.lang.reflect.Type`. Pattern matching cho `instanceof` được hỗ trợ trong Java 17.

Quan hệ quan trọng:

~~~text
                    java.lang.reflect.Type (interface)
                                 |
        +------------------------+--------------------------+
        |                        |                          |
   Class<?>                 ParameterizedType           TypeVariable<?>
        |                        |                          |
   String.class           List<String>                    T
   List.class             Map<String,Integer>             E
   String[].class
        |
        +------------------------+--------------------------+
                                 |                          |
                         GenericArrayType             WildcardType
                         T[] / List<String>[]          ? extends Number
                                                       ? super Integer
~~~

Sơ đồ trên biểu diễn **các loại đối tượng Type có thể nhận được** chứ không phải cây kế thừa class cụ thể; các nhánh cuối là interface chuyên biệt cùng nằm dưới `Type`.

## 3. Năm dạng Type cần nhận diện

### 3.1. Class<?> — kiểu JVM thông thường

~~~java
Type a = String.class;         // Class
Type b = int.class;            // Class
Type c = String[].class;       // Class
Type d = java.util.List.class; // Class
~~~

`String[]` dù là kiểu mảng vẫn có `Class` runtime thật. Nếu component là một kiểu reifiable cụ thể như `String`, Java biết được class mảng tương ứng ở runtime.

Các API `Class` rất hữu ích khi bạn cần lấy constructor, method, field, kiểm tra `isInstance`/`isAssignableFrom` hoặc tạo mảng qua Reflection. `Class<?>` thích hợp với **kiểu runtime** và **kiểu đã bị xóa tham số generic**.

### 3.2. ParameterizedType — kiểu có đối số generic cụ thể

Ví dụ `List<String>`, `Map<String, Integer>` hoặc `List<? extends Number>` khi xuất hiện trong metadata khai báo:

~~~java
Type type = Sample.class.getDeclaredField("names").getGenericType();
if (type instanceof ParameterizedType p) {
    Type raw = p.getRawType();                 // List
    Type[] arguments = p.getActualTypeArguments(); // [String]
    Type owner = p.getOwnerType();            // null cho List<String>
}
~~~

Đây là mã minh họa giả định `Sample` khai báo `List<String> names`; chương trình đầy đủ ở phần 7.

- `getRawType()`: kiểu thô, thường là `Class<?>` như `List.class`.
- `getActualTypeArguments()`: các đối số kiểu theo đúng thứ tự khai báo; **mỗi phần tử là `Type`**, có thể là `Class`, `ParameterizedType`, `TypeVariable` hoặc `WildcardType`.
- `getOwnerType()`: kiểu chứa đối với một số kiểu thành viên lồng nhau; có thể là `null` khi không có owner liên quan.

Với `Map<String, List<Integer>>`, đối số thứ hai tự nó là một `ParameterizedType`. Không được giả định mọi phần tử trong `getActualTypeArguments()` đều có thể ép sang `Class<?>`.

### 3.3. TypeVariable<?> — biến kiểu T, E, K, V

Ví dụ:

~~~java
class Box<T extends Number> {
    T value;
}
~~~

`value.getGenericType()` cho ra `TypeVariable` mang tên `T`. `value.getType()` trả về **`Number.class`**, vì `Number` là giới hạn trên đầu tiên và dùng làm kiểu sau xóa (erasure).

Các API đáng chú ý:

- `getName()` trả tên biến kiểu, chẳng hạn `"T"`.
- `getBounds()` trả các giới hạn trên dạng `Type[]`; nếu không khai báo giới hạn, giới hạn mặc định là `Object`.
- `getGenericDeclaration()` cho biết `Class`, `Method` hoặc `Constructor` nào khai báo biến kiểu.
- `Class#getTypeParameters()` và `Method#getTypeParameters()` liệt kê các biến kiểu do chính đối tượng tương ứng khai báo.

Cẩn thận: `T` trong `class Box<T>` **không tự trở thành `String.class`** chỉ vì một object nào đó được gán cho biến nguồn `Box<String>`. Metadata khai báo `Box<T>` vẫn chứa `T`. Để biết một subclass khai báo rõ `extends Box<String>`, cần đọc `getGenericSuperclass()` của **subclass**, không dựa vào riêng `Box.class.getTypeParameters()`.

### 3.4. WildcardType — ký hiệu ? và các giới hạn

Ví dụ:

~~~java
List<?> anything;
List<? extends Number> numbers;
List<? super Integer> targets;
~~~

Bên ngoài, cả ba kiểu trường đều thường là `ParameterizedType` có raw type `List`. **WildcardType nằm bên trong danh sách type arguments**, chẳng hạn phần tử đầu tiên của `List<? extends Number>`.

- `getUpperBounds()` lấy giới hạn trên. Với `? extends Number`, đó là `Number`; với `?` thông thường là `Object`.
- `getLowerBounds()` lấy giới hạn dưới. Với `? super Integer`, đó là `Integer`; nếu không có giới hạn dưới, mảng này rỗng.
- Không lấy được wildcard bằng cách gọi `getGenericType()` trên trường `List<? extends Number>` rồi ép ngay sang `WildcardType`; cần đi qua `ParameterizedType#getActualTypeArguments()`.

Wildcard là một thành phần của **kiểu khai báo**, không phải một class có thể nạp bằng `Class.forName("? extends Number")`.

### 3.5. GenericArrayType — mảng có component generic

Ví dụ:

~~~java
class Bag<T> {
    T[] history;
    List<String>[] groups;
    String[] labels;
}
~~~

Khi phản chiếu generic type của từng field:

| Trường | `getType()` | `getGenericType()` |
| --- | --- | --- |
| `T[] history`, với `T extends Number` | `Number[].class` | `GenericArrayType` mô tả `T[]` |
| `List<String>[] groups` | `List[].class` | `GenericArrayType` mô tả `List<String>[]` |
| `String[] labels` | `String[].class` | `Class<?>` đại diện cho `String[]` |

`GenericArrayType#getGenericComponentType()` trả `Type` của **thành phần mảng**. Đối với `T[]`, thành phần là `TypeVariable`; đối với `List<String>[]`, thành phần là `ParameterizedType`.

**Không phải mọi mảng đều là GenericArrayType**. Mảng của một kiểu runtime reifiable như `String[]` hay `int[]` thường được biểu diễn bằng `Class<?>`.

## 4. Reflection API nào trả Class, API nào trả Type?

Các cặp API này dễ bị lẫn:

| Nhu cầu | API kiểu thô / erasure | API giữ metadata generic |
| --- | --- | --- |
| Kiểu của field | `Field.getType() -> Class<?>` | `Field.getGenericType() -> Type` |
| Kiểu trả về method | `Method.getReturnType() -> Class<?>` | `Method.getGenericReturnType() -> Type` |
| Các kiểu tham số method/constructor | `getParameterTypes() -> Class<?>[]` | `getGenericParameterTypes() -> Type[]` |
| Exception khai báo của method/constructor | `getExceptionTypes() -> Class<?>[]` | `getGenericExceptionTypes() -> Type[]` |
| Lớp cha trực tiếp | `Class.getSuperclass() -> Class<?>` | `Class.getGenericSuperclass() -> Type` |
| Các interface trực tiếp | `Class.getInterfaces() -> Class<?>[]` | `Class.getGenericInterfaces() -> Type[]` |
| Biến kiểu do class/method/constructor khai báo | Không có phép suy từ mỗi `Class<?>` thô | `getTypeParameters() -> TypeVariable<?>[]` |

Ví dụ:

~~~java
class Store {
    List<String> customers;
    List<String> load() { return customers; }
}
~~~

- `customers`: `getType() == List.class`, còn `getGenericType().getTypeName()` là `java.util.List<java.lang.String>`.
- `load()`: `getReturnType() == List.class`, còn `getGenericReturnType()` có thể mô tả đầy đủ `List<String>`.
- Nếu method có tham số `Map<String, Integer>`, dùng `getGenericParameterTypes()` để đọc các type argument. `getParameterTypes()` chỉ chứa `Map.class`.

**Lưu ý về tên:** `getTypeName()` cung cấp biểu diễn văn bản của `Type` phục vụ hiển thị/chẩn đoán. Để xử lý kiểu một cách có cấu trúc, hãy dùng `instanceof` và các phương thức chuyên biệt thay vì tách chuỗi `"<...>"` bằng regex.

## 5. Type erasure: metadata generic còn gì sau biên dịch?

Java Generics chủ yếu dùng **type erasure** để tương thích bytecode. Trong nhiều vị trí runtime, JVM thao tác với raw type và giới hạn trên của type variable. Ví dụ:

~~~java
List<String> words = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

System.out.println(words.getClass() == numbers.getClass()); // true
~~~

(Đoạn minh họa cần import `java.util.List` và `java.util.ArrayList`.)

Nếu hai object trên đều là `ArrayList`, `getClass()` không chứa thông tin `String` hay `Integer`. Java cũng không có cú pháp class literal `List<String>.class`. Hai dòng này có nội dung khác nhau:

~~~java
Class<?> raw = List.class; // đại diện kiểu runtime List
Type metadata = Store.class
        .getDeclaredField("customers").getGenericType(); // List<String>
~~~

Vậy tại sao `Field.getGenericType()` vẫn thấy `String`?

- Trình biên dịch Java có thể ghi **generic signature metadata** cho các khai báo như field, method, superclass và interface vào class file.
- Reflection đọc metadata này và xây dựng `ParameterizedType`, `TypeVariable`, `WildcardType` hoặc `GenericArrayType` tương ứng.
- Metadata mô tả **kiểu được khai báo tại vị trí đó**, không chứng minh kiểu runtime thực của toàn bộ object hoặc từng phần tử dữ liệu.

Ví dụ, field khai báo `List<String> customers` có chữ ký chứa `String`. Nhưng một object `new ArrayList<String>()` không tự mang “chứng chỉ runtime rằng mọi phần tử luôn là String”. Nếu mã dùng raw type, unchecked cast hoặc reflection để đưa sai giá trị vào collection, generic signature của field vẫn giữ nguyên.

**Giới hạn cần nhớ:** Không thể dùng `obj.getClass()` để khôi phục đối số generic đã bị xóa của một đối tượng `new ArrayList<String>()` chỉ dựa trên object đó. Muốn giữ thông tin kiểu cho serialization/deserialization, thường phải cung cấp thêm một đối tượng mô tả kiểu hoặc dùng kỹ thuật **type token**.

## 6. Cách duyệt cấu trúc Type đúng và an toàn

Một tiện ích phân loại dạng Type có thể viết:

~~~java
static String kind(Type type) {
    if (type instanceof Class<?>) return "Class";
    if (type instanceof ParameterizedType) return "ParameterizedType";
    if (type instanceof TypeVariable<?>) return "TypeVariable";
    if (type instanceof GenericArrayType) return "GenericArrayType";
    if (type instanceof WildcardType) return "WildcardType";
    throw new IllegalArgumentException("Unknown Type kind: " + type);
}
~~~

Đây là phương thức sẽ xuất hiện trong chương trình hoàn chỉnh phần 7, với import `java.lang.reflect.*`.

Một quy trình đọc kiểu có cấu trúc:

1. Nhận `Type` qua `getGenericType()`, `getGenericReturnType()`, `getGenericSuperclass()` hoặc nguồn metadata phù hợp.
2. Nếu `type instanceof Class<?>`: đây là lớp/interface/primitive/array runtime. Với array class có thể dùng `clazz.getComponentType()`.
3. Nếu `ParameterizedType`: đọc `getRawType()`, duyệt **đệ quy** từng phần tử `getActualTypeArguments()` và, khi liên quan, xét `getOwnerType()`.
4. Nếu `TypeVariable<?>`: đọc `getName()`, `getBounds()` và `getGenericDeclaration()`. Đừng mặc định biến kiểu đã được thay bằng một Class cụ thể.
5. Nếu `WildcardType`: đọc cả `getUpperBounds()` và `getLowerBounds()`.
6. Nếu `GenericArrayType`: tiếp tục xét `getGenericComponentType()`; component lại có thể là một dạng Type khác.

Ví dụ với `Map<String, List<? extends Number>>`, cấu trúc logic là:

~~~text
ParameterizedType: Map<String, List<? extends Number>>
  rawType: Class(Map)
  argument[0]: Class(String)
  argument[1]: ParameterizedType: List<? extends Number>
    rawType: Class(List)
    argument[0]: WildcardType: ? extends Number
      upperBounds: Class(Number)
~~~

Cây ví dụ giúp thấy vì sao đoạn code `(Class<?>) p.getActualTypeArguments()[1]` có thể ném `ClassCastException`: phần tử thứ hai là `ParameterizedType` chứ không phải Class.

Khi xử lý thư viện thực tế, có thể gặp generic signature thiếu hoặc không hợp lệ do class file được sinh/thay đổi. Một số thao tác Reflection liên quan generic có thể gây `TypeNotPresentException`, `MalformedParameterizedTypeException` hoặc `GenericSignatureFormatError`. Hãy dùng dữ liệu type có cấu trúc khi có thể và báo lỗi metadata rõ ràng.

## 7. Chương trình Java 17+ đầy đủ: quan sát Class và các dạng Type

Tạo **một tệp** tên `ClassVsTypeDemo.java`:

~~~java
import java.lang.reflect.*;
import java.util.List;

public class ClassVsTypeDemo {
    static class Box<T extends Number> {
        List<String> names;
        T value;
        T[] history;
        List<? extends Number> rates;
        List<String>[] groups;
        String[] labels;
    }

    static class IntegerBox extends Box<Integer> { }

    static abstract class TypeCapture<T> {
        Type capture() {
            Type parent = getClass().getGenericSuperclass();
            return ((ParameterizedType) parent).getActualTypeArguments()[0];
        }
    }

    static String kind(Type type) {
        if (type instanceof Class<?>) return "Class";
        if (type instanceof ParameterizedType) return "ParameterizedType";
        if (type instanceof TypeVariable<?>) return "TypeVariable";
        if (type instanceof GenericArrayType) return "GenericArrayType";
        if (type instanceof WildcardType) return "WildcardType";
        throw new IllegalArgumentException("Unknown Type kind: " + type);
    }

    static void describe(String name) throws ReflectiveOperationException {
        Field field = Box.class.getDeclaredField(name);
        Type generic = field.getGenericType();
        System.out.println(name + ": raw=" + field.getType().getTypeName()
                + ", generic=" + generic.getTypeName()
                + ", kind=" + kind(generic));
    }

    public static void main(String[] args) throws Exception {
        for (String name : new String[] {
                "names", "value", "history", "rates", "groups", "labels" }) {
            describe(name);
        }

        ParameterizedType listType = (ParameterizedType)
                Box.class.getDeclaredField("names").getGenericType();
        System.out.println("names argument="
                + listType.getActualTypeArguments()[0].getTypeName());

        ParameterizedType rateType = (ParameterizedType)
                Box.class.getDeclaredField("rates").getGenericType();
        WildcardType wildcard = (WildcardType)
                rateType.getActualTypeArguments()[0];
        System.out.println("rates upper="
                + wildcard.getUpperBounds()[0].getTypeName());

        TypeVariable<?> t = Box.class.getTypeParameters()[0];
        System.out.println("T bound=" + t.getBounds()[0].getTypeName());

        ParameterizedType parent = (ParameterizedType)
                IntegerBox.class.getGenericSuperclass();
        System.out.println("IntegerBox parent arg="
                + parent.getActualTypeArguments()[0].getTypeName());

        Type captured = new TypeCapture<List<String>>() { }.capture();
        System.out.println("captured=" + captured.getTypeName());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa `ClassVsTypeDemo.java`:

~~~bash
javac --release 17 ClassVsTypeDemo.java
java ClassVsTypeDemo
~~~

**Stdout đã kiểm chứng bằng JDK 21 với `--release 17`:**

~~~text
names: raw=java.util.List, generic=java.util.List<java.lang.String>, kind=ParameterizedType
value: raw=java.lang.Number, generic=T, kind=TypeVariable
history: raw=java.lang.Number[], generic=T[], kind=GenericArrayType
rates: raw=java.util.List, generic=java.util.List<? extends java.lang.Number>, kind=ParameterizedType
groups: raw=java.util.List[], generic=java.util.List<java.lang.String>[], kind=GenericArrayType
labels: raw=java.lang.String[], generic=java.lang.String[], kind=Class
names argument=java.lang.String
rates upper=java.lang.Number
T bound=java.lang.Number
IntegerBox parent arg=java.lang.Integer
captured=java.util.List<java.lang.String>
~~~

### Giải thích bằng bằng chứng trong output

**`names`:** Kiểu runtime là `List`. Generic signature giữ `String`, nên `getGenericType()` là `ParameterizedType` và `getActualTypeArguments()[0]` là `String.class`.

**`value`:** Trong khai báo `Box<T extends Number>`, `T` vẫn là biến kiểu ở metadata. `Field.getType()` cho kiểu sau erasure `Number.class`, trong khi `getGenericType()` trả `TypeVariable` mang tên `T`. Giới hạn trên được in thành `Number`.

**`history`:** Với field `T[]`, raw runtime array có component erasure `Number`, nhưng generic signature giữ component `T`, do đó `GenericArrayType`.

**`rates`:** Bên ngoài là `List<? extends Number>`, một `ParameterizedType`. Type argument nằm bên trong là `WildcardType`, có upper bound `Number`.

**`groups` và `labels`:** `List<String>[]` là `GenericArrayType` vì component `List<String>` có tham số generic. `String[]` lại là một `Class` runtime. Đây là một trong các phép so sánh dễ thấy nhất của `Class` và `Type`.

**`IntegerBox`:** Đối tượng `IntegerBox.class.getGenericSuperclass()` trả về chữ ký `Box<Integer>` trong metadata của subclass, vì vậy có thể đọc `Integer`. Điều này **khác với** việc lấy một object của `Box` không có subclass xác định và hỏi `getClass()` xem tham số `T` là gì.

**`TypeCapture`:** Anonymous subclass có khai báo generic superclass chứa `List<String>`. Phương thức `capture()` đọc chữ ký superclass đó để thu được `ParameterizedType`, giữ lại đối số `String`.

Phần output được xây từ tên kiểu chuẩn của các Type, không in tên lớp triển khai nội bộ `sun.reflect.generics.reflectiveObjects.*`, vì tên triển khai nội bộ không phải hợp đồng API công khai.

## 8. Type token: giữ thông tin List<String> khi API cần Type

Đôi khi API nhận một tham số kiểu chung để cấu hình parser, JSON serializer, dependency injection hoặc converter:

~~~java
void register(Type type) {
    // Đọc cấu trúc Type để biết kiểu dữ liệu cần xử lý.
}
~~~

Đây là ví dụ chữ ký minh họa, không phải chương trình độc lập.

Gọi `register(List.class)` chỉ cung cấp raw class; thông tin `String` không còn. Một kỹ thuật thường dùng là **generic type token** thông qua anonymous subclass:

~~~java
abstract class TypeCapture<T> {
    Type capture() {
        Type parent = getClass().getGenericSuperclass();
        return ((ParameterizedType) parent).getActualTypeArguments()[0];
    }
}

Type listOfStrings = new TypeCapture<List<String>>() {}.capture();
System.out.println(listOfStrings.getTypeName());
// java.util.List<java.lang.String>
~~~

Đoạn minh họa cần import `java.lang.reflect.Type`, `java.lang.reflect.ParameterizedType` và `java.util.List`. Phương thức `capture()` dựa trên điều kiện **subclass thực sự khai báo superclass có tham số generic**, như anonymous subclass `new TypeCapture<List<String>>() {}`. Nếu tạo subclass raw hoặc thay cấu trúc kế thừa, việc ép `(ParameterizedType)` không còn được bảo đảm.

Vì sao cách này giữ được thông tin? Trình biên dịch ghi kiểu `List<String>` vào **generic superclass signature của anonymous subclass**, nên Reflection có thể đọc nó. Nó **không khôi phục** thông tin từ một `ArrayList<String>` object bình thường đã bị erasure.

Một số thư viện cung cấp sẵn API type token, ví dụ `TypeReference<T>` hoặc `TypeToken<T>`. Đừng giả định mọi thư viện dùng cùng API hoặc cùng quy tắc equality; ý tưởng chung là lưu `Type` đã mô tả đầy đủ vào thời điểm khai báo.

## 9. Phân biệt ba thông tin thường bị đánh đồng

### Kiểu runtime của đối tượng

~~~java
Object value = java.util.List.of("a", "b");
Class<?> runtimeClass = value.getClass();
~~~

`runtimeClass` mô tả **lớp triển khai thật sự** mà JVM tạo ra cho danh sách. Nó không nói `List<String>` từ biến nguồn. Với factory `List.of`, tên lớp triển khai là chi tiết nội bộ, không nên in/so sánh tên để lập luận về generic.

### Kiểu khai báo tại một vị trí

~~~java
class Response {
    List<String> values;
}
Type declaredType = Response.class.getDeclaredField("values").getGenericType();
~~~

Chữ ký field có thể cho biết `List<String>`. Nó là **metadata của khai báo**, không phải bằng chứng rằng danh sách đang chứa đúng kiểu phần tử tại mọi thời điểm.

### Kiểu thực tế sau khi liên kết generic qua kế thừa

~~~java
class Parent<T> { }
class Child extends Parent<String> { }
Type parentSignature = Child.class.getGenericSuperclass();
~~~

`parentSignature` là `ParameterizedType` chứa `String` vì mã nguồn của **Child** đã cố định tham số kế thừa. Nếu chuỗi kế thừa phức tạp hơn, để ánh xạ biến kiểu qua nhiều cấp thường phải duyệt và thế TypeVariable bằng type argument có liên quan; không có chuyện mỗi `getGenericSuperclass()` tự giải toàn bộ chuỗi kế thừa.

Ba mục tiêu này dẫn đến ba API khác nhau. Nên đặt câu hỏi rõ: cần biết class của object, kiểu field/method được khai báo, hay type argument của một superclass/interface?

## 10. Những lỗi thường gặp và cách khắc phục

| Cách hiểu hoặc đoạn code sai | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `Class<?> c = (Class<?>) field.getGenericType();` cho mọi field | Với `List<String>` nó là `ParameterizedType`, không phải Class | Dùng `instanceof` phân nhánh theo dạng `Type` |
| So sánh `List<String>` và `List<Integer>` bằng `getType()` | Cả hai cho raw `List.class` | Dùng `getGenericType()` và đọc type arguments |
| `Class.forName("java.util.List<java.lang.String>")` | Chuỗi chứa generic signature, không phải binary name của class | Dùng `List.class` cho class, hoặc lấy `Type` từ signature/token |
| `List<String>.class` | Java không cho tạo class literal cho parameterized type | Dùng `List.class` hoặc type token khi cần `List<String>` |
| `(Class<?>) p.getActualTypeArguments()[0]` trong mọi trường hợp | Đối số có thể là `WildcardType`, `TypeVariable` hoặc `ParameterizedType` | Phân loại và xử lý đệ quy |
| Xem `TypeVariable<T>` là `T.class` | Không có class literal độc lập cho biến kiểu T | Đọc bounds và ngữ cảnh generic declaration |
| Cho rằng mọi kiểu mảng là `GenericArrayType` | `String[]` có runtime `Class` | Kiểm tra cả `Class#isArray()` và `GenericArrayType` |
| Dùng `object.getClass()` để lấy `List<String>` | Type erasure không lưu tham số generic như thuộc tính object | Giữ `Type` từ khai báo hoặc type token |
| Đoán cấu trúc từ `Type#getTypeName()` bằng tách dấu phẩy và góc | Generic type có thể lồng sâu, có owner/wildcard/array | Dùng `ParameterizedType`, `WildcardType` và API chuyên biệt |
| Cho rằng `getGenericType()` bảo đảm object chứa dữ liệu đúng generic | Metadata không tự kiểm tra phần tử ở runtime | Thực hiện kiểm tra dữ liệu ở tầng ứng dụng nếu cần |

### Type và AnnotatedType có giống nhau không?

Không. `Type` mô tả cấu trúc kiểu, còn `java.lang.reflect.AnnotatedType` cho phép kiểm tra **annotation gắn lên chính vị trí sử dụng kiểu** (*type-use annotation*). Ví dụ một field có annotation trên generic argument có thể cần `Field.getAnnotatedType()` để đọc annotation tương ứng. `AnnotatedType#getType()` trả lại đối tượng `Type` cơ sở. Đừng nhầm `Field.getAnnotations()` (annotation của declaration) với annotation của các nút bên trong type.

### Khi nào không cần generic metadata?

Nếu bài toán là gọi public method, khởi tạo đối tượng bằng constructor, kiểm tra `Class.isInstance` hoặc xử lý field `int`, `String`, việc dùng `Class<?>` thường đã đủ. Chỉ dùng chuỗi xử lý `ParameterizedType`, `TypeVariable` v.v. khi nghiệp vụ **thật sự cần phân tích chữ ký generic**.

## 11. Bài tập thực hành có đáp án

**Bài 1.** Với `List<String> names`, `field.getType()` và `field.getGenericType()` lần lượt là gì?

**Đáp án:** `List.class` và một `ParameterizedType` mô tả `List<String>`. Type argument đầu là `String.class`.

**Bài 2.** Với `class Box<T extends Number> { T value; }`, vì sao `getType()` trả `Number.class` thay vì `T.class`?

**Đáp án:** Sau type erasure, `T` có giới hạn trên là `Number`; `T` được giữ trong metadata generic dạng `TypeVariable` và không có class literal `T.class`.

**Bài 3.** Với `List<? super Integer> list`, đối tượng `Type` ngoài cùng và type argument bên trong thuộc dạng nào?

**Đáp án:** Ngoài cùng là `ParameterizedType`, argument là `WildcardType`. `getLowerBounds()[0]` cho `Integer.class`.

**Bài 4.** Vì sao `String[]` thường là `Class` trong khi `List<String>[]` thường là `GenericArrayType`?

**Đáp án:** Mảng `String[]` có component reifiable và có runtime class xác định. Component `List<String>` mang tham số generic, được biểu diễn trong generic signature; array generic đó cần `GenericArrayType`.

**Bài 5.** Một field khai báo `Map<String, List<Integer>>`. Có an toàn khi ép argument thứ hai của Map sang `Class<?>` không?

**Đáp án:** Không; argument thứ hai là một `ParameterizedType` mô tả `List<Integer>`. Cần duyệt lồng nhau.

**Bài 6.** `new ArrayList<String>().getClass()` có cho phép lấy `String.class` bằng một API trên Class của object không?

**Đáp án:** Không, generic argument đã bị erasure. Có thể giữ nó bằng generic field metadata hoặc một type token khai báo rõ `List<String>`.

**Bài 7.** Với `class Child extends Box<Integer>`, API nào giúp đọc `Integer` từ khai báo kế thừa?

**Đáp án:** `Child.class.getGenericSuperclass()`, sau đó nếu là `ParameterizedType` thì đọc `getActualTypeArguments()`.

**Bài 8.** Tại sao API serialization nên nhận `Type` thay vì chỉ nhận `Class<?>` khi cần phân tích `List<User>`?

**Đáp án:** `Class<?>` chỉ cho `List.class`; `Type` có thể giữ cả `User` bên trong generic signature/token, giúp serializer biết kiểu phần tử cần ánh xạ.

## 12. Tóm tắt để ghi nhớ

- **`Class<?>` là một `Type`**, nhưng `Type` có thể mang cấu trúc generic mà `Class<?>` không mô tả được.
- Năm dạng cốt lõi: **`Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType`**.
- **`getType()`** lấy class/erasure của field; **`getGenericType()`** có thể đọc generic signature của khai báo. Các cặp API tương tự áp dụng với method, constructor, superclass và interface.
- **Type erasure** không xóa mọi generic signature của các khai báo, nhưng nó ngăn việc suy ra type argument chỉ từ `object.getClass()` của một generic object thông thường.
- Khi phải truyền `List<String>` cho framework, hãy cung cấp `Type` giữ generic information từ metadata hoặc dùng type token; đừng cố tạo `List<String>.class`.
- Đọc `Type` bằng **phân nhánh và duyệt cấu trúc**, không ép mọi thứ sang `Class<?>` và không tự parse văn bản `getTypeName()`.

### Tài liệu Java chính thức

- [Java SE 17 — `java.lang.reflect.Type`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html).
- [Java SE 17 — `ParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html).
- [Java SE 17 — `TypeVariable`, `WildcardType`, `GenericArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/package-summary.html).
- [Java SE 17 — `Field.getGenericType()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#getGenericType()).
- [JLS 17 §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6).

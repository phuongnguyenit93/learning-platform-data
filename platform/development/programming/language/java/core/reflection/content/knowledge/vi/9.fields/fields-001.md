# Field trong Java Reflection: tên, declaring class, raw type và generic type

## 1. Mục tiêu

Khi dùng Java Reflection để khảo sát một trường dữ liệu, bốn câu hỏi nền tảng là:

1. **Tên trường là gì?** → `Field.getName()`.
2. **Lớp hoặc interface nào thực sự khai báo trường?** → `Field.getDeclaringClass()`.
3. **Kiểu runtime của trường sau khi xóa generic là gì?** → `Field.getType()`.
4. **Kiểu được khai báo trong chữ ký generic là gì?** → `Field.getGenericType()`.

Bốn thông tin này phục vụ các mục đích khác nhau. Chẳng hạn một serializer cần tên để ánh xạ thuộc tính, cần declaring class để xác định vị trí khai báo, cần raw type để biết trường có phải `List` hoặc `Map`, và cần generic type để biết `List<String>` hay `List<Integer>`. Đừng lấy kết quả của một phương thức để trả lời thay câu hỏi của phương thức khác.

Đối tượng `java.lang.reflect.Field` là **metadata mô tả khai báo trường** trong một lớp/interface. Nó không tự chứa giá trị trường của từng object. Muốn đọc giá trị cần `field.get(receiver)`; thao tác này liên quan quyền truy cập và không phải trọng tâm của bốn thuộc tính đang học.

Ví dụ:

```java
class Book {
    private String title;
    private java.util.List<String> tags;
}
```

Với `Field f = Book.class.getDeclaredField("tags")`:

| Câu hỏi | Phương thức | Kết quả |
|---|---|---|
| Tên trường? | `f.getName()` | `"tags"` |
| Ai khai báo? | `f.getDeclaringClass()` | `Book.class` |
| Raw type? | `f.getType()` | `java.util.List.class` |
| Generic type? | `f.getGenericType()` | Đối tượng `ParameterizedType` biểu diễn `java.util.List<java.lang.String>` |

Đây là ví dụ minh họa về metadata, chưa phải chương trình có hàm `main` độc lập; chương trình chạy được đầy đủ xuất hiện ở mục 8.

## 2. Từ `Class<?>` đến đối tượng `Field`

Ta lấy `Field` qua `Class<?>`, không tạo `Field` bằng `new`:

```java
Class<?> type = Book.class;
Field tags = type.getDeclaredField("tags");
```

Cần `import java.lang.reflect.Field;` và xử lý `NoSuchFieldException`.

Các API tra cứu phổ biến:

| API của `Class` | Tìm gì? | Có trường kế thừa? |
|---|---|---|
| `getDeclaredField(String name)` | Một trường do **chính** lớp/interface hiện tại khai báo, bất kể `private`, `protected`, package-private hay `public` | Không |
| `getDeclaredFields()` | Mọi trường do **chính** lớp/interface hiện tại khai báo | Không |
| `getField(String name)` | Một trường `public` theo quy tắc tìm kiếm của Reflection | Có thể có |
| `getFields()` | Các trường `public` mà kiểu nhìn thấy theo quy tắc API | Có thể có |

**Declared không có nghĩa private.** Nó chỉ cho biết trường được khai báo ngay tại kiểu đang xét. Một trường `public` trong lớp cha cũng sẽ không có mặt trong `Child.class.getDeclaredFields()` nếu `Child` không khai báo trường đó.

Với `getDeclaredField("x")`, nếu lớp hiện tại không khai báo `x`, Java ném `NoSuchFieldException`. Nếu muốn tra cứu trường kế thừa `public`, xem `getField`. Nếu cần rà soát mọi lớp cha, kể cả trường không public, phải tự duyệt qua `getSuperclass()` và gọi `getDeclaredFields()` từng lớp.

Lưu ý: Java Reflection **không cam kết thứ tự** của mảng từ `getDeclaredFields()` hoặc `getFields()`. Tool xuất schema cần thứ tự ổn định thì tự sắp xếp theo tên và quy tắc riêng. Ngoài ra compiler có thể tạo **synthetic fields**, nên một công cụ chỉ quan tâm trường nghiệp vụ đôi khi cần kiểm tra `field.isSynthetic()` trước khi xử lý.

## 3. `Field.getName()`: tên của trường

Chữ ký API:

```java
String getName()
```

`getName()` trả **tên của trường** dưới dạng `String`. Đây là tên thành viên khai báo, không phải:

- Tên class hay tên package.
- Giá trị của trường trong một object.
- Tên property của JavaBeans theo quy tắc getter/setter.
- Tên cột trong database hay tên khóa JSON do framework đặt.
- Tên gồm kiểu generic, modifier hay declaring class.

Ví dụ:

```java
class Inventory {
    private long quantity;
    public static final int MAX_ITEMS = 100;
}
```

```java
Field one = Inventory.class.getDeclaredField("quantity");
Field two = Inventory.class.getDeclaredField("MAX_ITEMS");

System.out.println(one.getName()); // quantity
System.out.println(two.getName()); // MAX_ITEMS
```

Hai đoạn trên cần được đặt cùng ngữ cảnh và import `Field`; chúng minh họa rằng tên trường không phụ thuộc field là instance hay `static final`.

Khi ánh xạ `Field` sang external schema, **không nên lấy `getName()` làm tên khóa bất biến** nếu tên source có thể đổi. Một framework có thể chủ động xử lý annotation hoặc naming strategy, ví dụ camelCase sang snake_case, nhưng `Field.getName()` tự nó không thực hiện phép biến đổi đó.

Một lớp có thể chứa những trường bị compiler sinh thêm với tên không xuất hiện như khai báo bình thường trong source. Khi cần duyệt schema nghiệp vụ, xem xét `isSynthetic()` và các quy tắc loại trừ phù hợp.

## 4. `Field.getDeclaringClass()`: kiểu khai báo thực sự

Chữ ký:

```java
Class<?> getDeclaringClass()
```

Kết quả là đối tượng `Class<?>` đại diện **kiểu đã khai báo field**, bất kể người gọi tìm field thông qua kiểu nào.

Giả sử:

```java
class Parent {
    public String id;
}

class Child extends Parent {
    public int age;
}
```

```java
Field inherited = Child.class.getField("id");
Field own = Child.class.getDeclaredField("age");

System.out.println(inherited.getDeclaringClass() == Parent.class); // true
System.out.println(own.getDeclaringClass() == Child.class);        // true
```

Vì `id` được khai báo trong `Parent`, việc tra cứu qua `Child.class` **không thay đổi** declaring class của nó.

### 4.1. Phân biệt các khái niệm gần nhau

| Biểu thức | Hỏi điều gì? |
|---|---|
| `Child.class` | `Class` được chọn làm **điểm bắt đầu tra cứu** |
| `field.getDeclaringClass()` | Lớp/interface **khai báo chính field đó** |
| `field.getDeclaringClass().getName()` | Tên đầy đủ (binary name) của lớp khai báo |
| `field.getDeclaringClass().getSimpleName()` | Tên đơn giản, thuận tiện để hiển thị nhưng không bảo đảm duy nhất |
| `field.getClass()` | Kiểu runtime của **đối tượng Reflection metadata**, không phải lớp khai báo field |
| `field.getType()` | Kiểu dữ liệu của **trường**, không phải declaring class |

Không được dùng `field.getType()` để suy ra lớp chứa field. Ví dụ trong `class User { String name; }`: declaring class của `name` là `User`, còn raw type là `String`.

### 4.2. Kế thừa, field hiding và declaring class

Java cho phép lớp con khai báo field trùng tên với lớp cha (field hiding). Hai field vẫn là **hai thành viên khác nhau**, có declaring class khác nhau, ngay cả khi tên giống hệt:

```java
class Parent {
    public String code;
}

class Child extends Parent {
    public int code;
}
```

```java
Field parentCode = Parent.class.getDeclaredField("code");
Field childCode = Child.class.getDeclaredField("code");

System.out.println(parentCode.getName().equals(childCode.getName())); // true
System.out.println(parentCode.getDeclaringClass() == Parent.class);    // true
System.out.println(childCode.getDeclaringClass() == Child.class);      // true
System.out.println(parentCode.getType() == childCode.getType());      // false
```

Đừng định danh một field chỉ bằng tên nếu quét nhiều tầng kế thừa. Một khóa nhận diện hợp lý trong hệ thống phân tích có thể gồm **declaring class và field name** (cùng ngữ cảnh class loader khi cần), vì `Parent.code` và `Child.code` là hai trường khác nhau.

Khi quét hệ thống có nhiều class loader, tên lớp dạng chuỗi cũng không đủ để xác định chính xác danh tính `Class`. Hai class loader có thể nạp những kiểu có cùng tên nhị phân nhưng khác identity.

## 5. `Field.getType()`: raw type ở runtime

Chữ ký:

```java
Class<?> getType()
```

Kết quả luôn là một `Class<?>`, mô tả **kiểu của field tại runtime sau các quy tắc erasure của generic**. Với các trường không generic, đây chính là kiểu khai báo thông thường; với tham số generic, thông tin type arguments thường không hiện diện trong kết quả `getType()`.

Ví dụ:

```java
class Data {
    String title;
    int count;
    int[] scores;
    java.util.List<String> names;
    java.util.Map<String, Integer> ages;
}
```

| Field | `getType()` | `getType().getTypeName()` |
|---|---|---|
| `title` | `String.class` | `java.lang.String` |
| `count` | `int.class` | `int` |
| `scores` | `int[].class` | `int[]` |
| `names` | `List.class` | `java.util.List` |
| `ages` | `Map.class` | `java.util.Map` |

Do `List<String>` và `List<Integer>` cùng có raw type `List.class`, chỉ so sánh `getType()` **không phân biệt** chúng. Tương tự `Map<String, Integer>` và `Map<String, Long>` đều cho `Map.class`.

Với field khai báo bằng biến kiểu:

```java
class Holder<T extends Number> {
    T value;
    T[] values;
}
```

`getType()` của `value` là `Number.class` vì erasure của `T extends Number` dùng bound đầu tiên `Number`. Với `values`, erasure là `Number[]`. Nếu `T` không có bound cụ thể thì erasure thông thường là `Object`; khi có nhiều bounds, bound đầu tiên xác định erasure.

Một điểm thực tế: `getType()` trả `Class` có thể dùng với `isPrimitive()`, `isArray()`, `getComponentType()`, `isAssignableFrom()`. Tuy nhiên kiểm tra khả năng gán kiểu bằng `Class.isAssignableFrom` là một chủ đề khác với việc phục hồi generic type arguments.

## 6. `Field.getGenericType()`: kiểu đã khai báo, bao gồm signature generic

Chữ ký:

```java
Type getGenericType()
```

`java.lang.reflect.Type` là interface chung cho nhiều dạng mô tả kiểu trong Reflection. `getGenericType()` đọc thông tin kiểu theo khai báo generic (khi có metadata cần thiết), **không tự xác định loại đối tượng hiện đang được gán vào field**.

Các dạng thường gặp:

| Dạng `Type` | Ý nghĩa | Ví dụ field |
|---|---|---|
| `Class<?>` | Kiểu không tham số hóa / primitive / array kiểu thường | `String name`, `int age`, `String[] names` |
| `ParameterizedType` | Kiểu generic đã dùng với type arguments | `List<String> tags`, `Map<String, Integer> counts` |
| `TypeVariable<?>` | Biến kiểu được khai báo ở class/method/constructor | `T value` trong `class Box<T>` |
| `GenericArrayType` | Mảng có component type là kiểu tham số hóa hoặc biến kiểu | `T[] items`, `List<String>[] groups` |
| `WildcardType` | Wildcard thường xuất hiện như type argument trong `ParameterizedType` | `List<? extends Number> numbers`: wildcard là đối số bên trong `List` |

**Chú ý:** Với `List<? extends Number> numbers`, `field.getGenericType()` cho **`ParameterizedType`** của `List<...>`; bạn chỉ gặp `WildcardType` khi lấy phần tử của `getActualTypeArguments()`. Không ép trực tiếp kết quả `getGenericType()` sang `WildcardType` trong trường hợp này.

### 6.1. `ParameterizedType`

Ví dụ:

```java
Field field = Data.class.getDeclaredField("names");
Type type = field.getGenericType();

if (type instanceof ParameterizedType parameterized) {
    Type raw = parameterized.getRawType();
    Type[] arguments = parameterized.getActualTypeArguments();
    System.out.println(raw.getTypeName());
    System.out.println(arguments[0].getTypeName());
}
```

Trong ngữ cảnh `Data.names` là `List<String>` ở mục 5, đầu ra:

```text
java.util.List
java.lang.String
```

Đây là đoạn minh họa không độc lập: cần import `Field`, `Type`, `ParameterizedType` và định nghĩa `Data`. `ParameterizedType.getRawType()` trả một `Type`; trường hợp `List<String>` nó biểu diễn `java.util.List`. Tham số `String` nằm trong `getActualTypeArguments()`.

Với kiểu lồng nhau `Map<String, List<Integer>>`, type argument thứ hai của `Map` bản thân nó là một `ParameterizedType`. Muốn lấy tới `Integer` phải đi sâu từng cấp, **không chỉ đọc một level**.

### 6.2. `TypeVariable<?>`

Với `class Box<T extends Number> { T value; }`:

- `getType()` của `value` → `Number.class`.
- `getGenericType()` của `value` → `TypeVariable<?>` có tên `T`.
- `((TypeVariable<?>) type).getBounds()` cho danh sách upper bounds đã khai báo; ví dụ trên có `Number`.

Không nhầm thông tin bound với type argument cụ thể. Biết `T extends Number` chỉ bảo đảm `T` có ràng buộc upper bound; nó **không nói** một instance nào đó đang chứa `Integer` hay `Double`.

### 6.3. `GenericArrayType`

Ví dụ:

```java
class Bag<T extends Number> {
    T[] values;
    java.util.List<String>[] groups;
}
```

- `values`: `getType()` là `Number[].class` nhưng `getGenericType()` là `GenericArrayType` với generic component type là biến `T`.
- `groups`: `getType()` là `List[].class`, còn `getGenericType()` biểu diễn một mảng có component type `List<String>`, thường là `GenericArrayType`.
- `int[]` hay `String[]` thông thường dùng `Class<?>` ở `getGenericType()` vì component không phải biến kiểu/tham số hóa.

`GenericArrayType.getGenericComponentType()` giúp truy cập kiểu phần tử tổng quát. Không nên ép `getGenericType()` của mọi trường mảng sang `Class<?>`.

### 6.4. `WildcardType`

Với trường:

```java
java.util.List<? extends Number> numbers;
```

Ta lấy wildcard từ type argument của `List`:

```java
ParameterizedType listType =
        (ParameterizedType) field.getGenericType();
Type argument = listType.getActualTypeArguments()[0];

if (argument instanceof WildcardType wildcard) {
    Type[] uppers = wildcard.getUpperBounds();
    Type[] lowers = wildcard.getLowerBounds();
    // Ở đây upper bound là Number và không có lower bound tường minh.
}
```

Đoạn này cần `field` trỏ tới trường `numbers`, cùng các import Reflection; nó không phải chương trình độc lập. Với `List<? super Integer>`, `getLowerBounds()` chứa `Integer`; upper bound mặc định là `Object`. Với `List<?>`, upper bound mặc định là `Object` và lower bounds rỗng.

### 6.5. Không tự động “giải” biến kiểu qua lớp con

Xét:

```java
class Box<T> {
    public T item;
}

class StringBox extends Box<String> {
}
```

Khi gọi:

```java
Field inherited = StringBox.class.getField("item");
System.out.println(inherited.getDeclaringClass() == Box.class); // true
System.out.println(inherited.getGenericType().getTypeName());   // T
```

Metadata của field `item` **được khai báo tại `Box<T>`**, nên `getGenericType()` cho `T`, ngay cả khi tìm nó qua `StringBox.class`. Nó không tự biến thành `String.class`.

Muốn suy ra `T = String` ở ngữ cảnh subclass, cần phân tích quan hệ generic superclass/interface (`StringBox.class.getGenericSuperclass()` trả dạng có `Box<String>`), sau đó lập ánh xạ type variables sang type arguments và áp dụng xuyên qua các tầng kế thừa. Java Reflection cung cấp dữ liệu để làm điều đó nhưng **không có một thao tác `Field.getGenericType()` tự thực hiện toàn bộ phép ánh xạ theo runtime object**.

## 7. So sánh `getType()` và `getGenericType()` trong các tình huống

| Khai báo field | Kết quả `getType().getTypeName()` | Kết quả `getGenericType().getTypeName()` |
|---|---|---|
| `String name` | `java.lang.String` | `java.lang.String` |
| `int count` | `int` | `int` |
| `String[] names` | `java.lang.String[]` | `java.lang.String[]` |
| `List<String> tags` | `java.util.List` | `java.util.List<java.lang.String>` |
| `Map<String, Integer> scores` | `java.util.Map` | `java.util.Map<java.lang.String, java.lang.Integer>` |
| `T value`, trong `T extends Number` | `java.lang.Number` | `T` |
| `T[] values`, trong `T extends Number` | `java.lang.Number[]` | `T[]` |
| `List<? extends Number> ranks` | `java.util.List` | `java.util.List<? extends java.lang.Number>` |

Các chuỗi trên là cách hiển thị điển hình của `Type.getTypeName()` trên Java 17. Chúng rất hữu ích để quan sát/log, nhưng khi **phân tích cấu trúc kiểu** hãy dùng `instanceof` với `Class`, `ParameterizedType`, `TypeVariable`, `GenericArrayType` và `WildcardType`. Không phân tích generic bằng cách tự cắt chuỗi ở dấu `<`, dấu phẩy hoặc dấu `>`: cách đó sai với type lồng nhau, nested class và nhiều loại type khác.

Một `Type` generic có thể trỏ đến class không tải được hoặc metadata chữ ký không hợp lệ; khi đọc chữ ký generic, Reflection có thể ném những lỗi như `TypeNotPresentException`, `MalformedParameterizedTypeException` hoặc `GenericSignatureFormatError` trong bối cảnh metadata hỏng/thiếu. Với tool phân tích bytecode từ nguồn không hoàn toàn kiểm soát, nên xử lý những trường hợp này có chủ đích.

## 8. Chương trình Java 17+ chạy được: quan sát đủ bốn thuộc tính

Tạo file **`FieldMetadataDemo.java`** với nội dung:

```java
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.List;
import java.util.Map;

public class FieldMetadataDemo {
    static class Parent {
        public String inheritedCode;
        public String code;
    }

    static class Box<T extends Number> extends Parent {
        private String label;
        public T value;
        public T[] values;
        public List<String> tags;
        public Map<String, List<? extends Number>> scores;
        public int[] counts;
        public int code;
    }

    static class IntegerBox extends Box<Integer> {
    }

    public static void main(String[] args) throws NoSuchFieldException {
        Field tags = Box.class.getDeclaredField("tags");

        System.out.println("Name: " + tags.getName());
        System.out.println("Declaring: "
                + tags.getDeclaringClass().getSimpleName());
        System.out.println("Raw type: " + tags.getType().getTypeName());
        System.out.println("Generic type: "
                + tags.getGenericType().getTypeName());

        ParameterizedType tagsType =
                (ParameterizedType) tags.getGenericType();
        System.out.println("Tags argument: "
                + tagsType.getActualTypeArguments()[0].getTypeName());

        Field value = Box.class.getDeclaredField("value");
        Type valueGeneric = value.getGenericType();
        TypeVariable<?> variable = (TypeVariable<?>) valueGeneric;

        System.out.println("Value raw: " + value.getType().getTypeName());
        System.out.println("Value generic: " + valueGeneric.getTypeName());
        System.out.println("Value bound: "
                + variable.getBounds()[0].getTypeName());

        Field values = Box.class.getDeclaredField("values");
        Type valuesGeneric = values.getGenericType();
        GenericArrayType genericArray = (GenericArrayType) valuesGeneric;

        System.out.println("Values raw: "
                + values.getType().getTypeName());
        System.out.println("Values generic: " + valuesGeneric.getTypeName());
        System.out.println("Array component: "
                + genericArray.getGenericComponentType().getTypeName());

        Field scores = Box.class.getDeclaredField("scores");
        ParameterizedType scoresType =
                (ParameterizedType) scores.getGenericType();
        ParameterizedType nestedList = (ParameterizedType)
                scoresType.getActualTypeArguments()[1];
        WildcardType wildcard = (WildcardType)
                nestedList.getActualTypeArguments()[0];

        System.out.println("Scores raw: "
                + scores.getType().getTypeName());
        System.out.println("Scores generic: "
                + scores.getGenericType().getTypeName());
        System.out.println("Wildcard upper: "
                + wildcard.getUpperBounds()[0].getTypeName());

        Field inherited = IntegerBox.class.getField("inheritedCode");
        Field childCode = Box.class.getDeclaredField("code");
        Field parentCode = Parent.class.getDeclaredField("code");

        System.out.println("Inherited declaring: "
                + inherited.getDeclaringClass().getSimpleName());
        System.out.println("Hidden parent declaring: "
                + parentCode.getDeclaringClass().getSimpleName());
        System.out.println("Hidden child declaring: "
                + childCode.getDeclaringClass().getSimpleName());

        Field subclassValue = IntegerBox.class.getField("value");
        System.out.println("Subclass field generic: "
                + subclassValue.getGenericType().getTypeName());
        System.out.println("Subclass generic parent: "
                + IntegerBox.class.getGenericSuperclass().getTypeName());
    }
}
```

Chạy tại thư mục chứa file, sử dụng JDK 17 hoặc mới hơn:

```bash
javac FieldMetadataDemo.java
java FieldMetadataDemo
```

Kết quả chuẩn:

```text
Name: tags
Declaring: Box
Raw type: java.util.List
Generic type: java.util.List<java.lang.String>
Tags argument: java.lang.String
Value raw: java.lang.Number
Value generic: T
Value bound: java.lang.Number
Values raw: java.lang.Number[]
Values generic: T[]
Array component: T
Scores raw: java.util.Map
Scores generic: java.util.Map<java.lang.String, java.util.List<? extends java.lang.Number>>
Wildcard upper: java.lang.Number
Inherited declaring: Parent
Hidden parent declaring: Parent
Hidden child declaring: Box
Subclass field generic: T
Subclass generic parent: FieldMetadataDemo$Box<java.lang.Integer>
```

**Phân tích kết quả:**

1. `tags.getName()` trả tên đúng theo khai báo; `getDeclaringClass()` là `Box`, mặc dù field `tags` có kiểu `List`.
2. `tags.getType()` chỉ giữ `List`. `tags.getGenericType()` giữ type argument `String`, nên metadata được biểu diễn thành `ParameterizedType`.
3. Trường `value` khai báo `T extends Number` có raw type `Number`, nhưng generic type là biến `T`; `TypeVariable.getBounds()` cho `Number`.
4. Trường `values` khai báo `T[]` có raw type `Number[]` và generic type `T[]`. `GenericArrayType.getGenericComponentType()` cho `T`.
5. Trường `scores` có generic lồng nhau; để lấy wildcard bound phải xuống qua `Map` → `List` → wildcard. Type argument `? extends Number` có upper bound `Number`.
6. `IntegerBox.class.getField("inheritedCode")` trả field của `Parent`. Cùng tên `code` ở `Parent` và `Box` tạo thành **hai Field** với declaring class khác nhau.
7. `IntegerBox.class.getField("value")` trả Field khai báo tại `Box`, nên generic type vẫn là `T`. Phần generic superclass của `IntegerBox` có `Box<Integer>`, là metadata **khác** cần xét khi giải biến kiểu.

Trong dòng cuối, `IntegerBox.class.getGenericSuperclass().getTypeName()` hiển thị tên nhị phân của lớp lồng nhau `Box` dưới dạng `FieldMetadataDemo$Box<...>`. Ký hiệu `$` là phần của tên nhị phân của nested class, không phải lỗi định dạng.

Trong ví dụ, các nested classes được dùng để đặt tất cả type trong **một file duy nhất**. Các tên hiện ra qua `getSimpleName()` là `Box`/`Parent`; phân biệt với `getName()` của `Class`, vốn bao gồm tên bao quanh và ký hiệu `$` đối với nested classes.

## 9. Trình duyệt metadata đơn giản và ổn định thứ tự

Khi xây công cụ đọc schema, ta thường muốn liệt kê field theo tên, declaring class, raw type và generic type. Một helper minh họa:

```java
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Comparator;

public final class FieldPrinter {
    public static void printDeclaredFields(Class<?> type) {
        Field[] fields = type.getDeclaredFields();
        Arrays.sort(fields, Comparator.comparing(Field::getName));

        for (Field field : fields) {
            if (field.isSynthetic()) {
                continue;
            }

            System.out.println(
                    field.getDeclaringClass().getName() + "#"
                    + field.getName() + " : "
                    + field.getType().getTypeName() + " / "
                    + field.getGenericType().getTypeName());
        }
    }
}
```

Đoạn này là **lớp tiện ích** không có `main`, cần được gọi từ một chương trình khác, ví dụ `FieldPrinter.printDeclaredFields(SomeClass.class)`. Nó chỉ **đọc metadata** và không cần `setAccessible(true)` để lấy tên/kiểu.

Việc sắp xếp bằng `Comparator.comparing(Field::getName)` đảm bảo thứ tự ổn định **trong một danh sách field khai báo của cùng class**; nếu bạn gộp field từ nhiều class trong cùng hierarchy (có thể trùng tên), hãy bổ sung declaring class vào tiêu chí sắp xếp. Code in generic type bằng `getTypeName()` phục vụ hiển thị; một bộ phân tích thật nên kiểm tra cấu trúc `Type` như ở mục 6.

`getDeclaredFields()` có thể trả field private, protected hay package-private nhưng **chỉ liệt kê metadata**. Nếu tiếp tục đọc giá trị bằng `Field.get(receiver)`, quyền truy cập cần được kiểm tra riêng. Tìm được field không đồng nghĩa có quyền sử dụng nó.

## 10. Ứng dụng thực tế của bốn thuộc tính

### 10.1. JSON mapping / object serialization

Một mapper có thể lập schema như sau:

- `getName()`: tên mặc định của property, trước khi xét annotation/naming strategy.
- `getDeclaringClass()`: tìm ra field gốc trong hierarchy, phân biệt field bị che khuất.
- `getType()`: xử lý primitive, array, enum, collection/map ở mức class.
- `getGenericType()`: đọc `List<Order>`, `Map<String, Price>` hoặc biến kiểu để quyết định cách xử lý các phần tử.

Nếu bỏ `getGenericType()`, mapper chỉ thấy `List` và có thể mất thông tin loại phần tử **được khai báo**. Nhưng nếu field khai báo `T` trong một generic superclass, chỉ `getGenericType()` **chưa đủ** để suy ra `T` là gì trong một subclass cụ thể.

### 10.2. Dependency injection / framework scanning

Một framework có thể đọc field đã đánh dấu annotation, xác định raw type để tìm bean ứng viên và dùng generic type để giải quyết các injection points như `Repository<User>`. Việc field nằm trong superclass ảnh hưởng declaring class, annotation và thứ tự xử lý.

Không suy ra rằng hai field có chung raw type sẽ có cùng ý nghĩa injection: `Repository<User>` và `Repository<Order>` có cùng raw type `Repository` nhưng khác type argument.

### 10.3. API schema / validation

Một công cụ sinh mô tả dữ liệu có thể hiển thị tên và khai báo của field; nó cần phân biệt:

- `String` với `List<String>`;
- `List<? extends Number>` với `List<Number>`;
- `T extends Number` với một kiểu cụ thể `Integer`;
- field ở lớp cha với field bị lớp con che khuất.

Những metadata đó mô tả **ràng buộc và chữ ký khai báo**, không thể tự bảo đảm trạng thái/value runtime đang thỏa mọi điều kiện nếu framework còn cho phép dữ liệu raw/unchecked.

## 11. Những lỗi phổ biến

| Sai lầm | Vì sao sai? | Cách đúng |
|---|---|---|
| Dùng `getName()` để lấy giá trị String của field | `getName()` chỉ trả tên khai báo | Muốn đọc giá trị phải dùng `get(receiver)` và xử lý quyền |
| Dùng `getType()` để phân biệt `List<String>` và `List<Integer>` | Cả hai bị erasure về `List.class` | Phân tích `getGenericType()` |
| Ép mọi `getGenericType()` thành `ParameterizedType` | Primitive, class thường, type variable hoặc generic array có loại `Type` khác | Kiểm tra `instanceof` rồi xử lý theo nhánh |
| Cho rằng `getDeclaringClass()` luôn bằng class dùng để gọi `getField` | Field public có thể kế thừa | Đọc declaring class trên chính `Field` |
| Cho rằng field bị che khuất là cùng một field | Hai lớp khai báo hai thành viên khác nhau | Phân biệt bởi declaring class và tên |
| Cho rằng `getGenericType()` của field `T` trả `String` khi subclass là `Box<String>` | Metadata lưu chữ ký khai báo tại `Box<T>` | Phân tích generic superclass/interface và ánh xạ type variables |
| Đọc wildcard bằng cách cast trực tiếp `List<? extends Number>` sang `WildcardType` | Kiểu bên ngoài là `ParameterizedType` | Lấy wildcard từ `getActualTypeArguments()` |
| Dựa vào thứ tự `getDeclaredFields()` | API không hứa thứ tự cụ thể | Tự sắp xếp |
| Cố mở private access chỉ để đọc metadata | Metadata như tên, declaring class, type không đòi đọc giá trị | Chỉ xét quyền khi thật sự `get`/`set` |
| Coi tên lớp dạng chuỗi là identity toàn cục | Class loader khác nhau có thể tạo các `Class` khác nhau cùng tên | Sử dụng `Class<?>`/loader đúng ngữ cảnh khi cần |
| Cắt chuỗi `Type.getTypeName()` để “parse” generic | Generic nested/wildcard/array làm parsing thủ công dễ sai | Phân nhánh cấu trúc `Type` |

## 12. Checklist và câu hỏi tự kiểm tra

Checklist khi khảo sát một field:

1. Xác định **lớp tra cứu** bằng `SomeClass.class`, `instance.getClass()` hoặc một nguồn `Class<?>` hợp lệ.
2. Chọn `getDeclaredField(s)` nếu cần khai báo trực tiếp; chọn `getField(s)` nếu muốn truy vấn trường public có thể kế thừa.
3. Đọc `field.getName()` và `field.getDeclaringClass()` để xác định danh tính trường.
4. Đọc `field.getType()` cho kiểu erased ở dạng `Class<?>`.
5. Đọc `field.getGenericType()` cho khai báo generic, kiểm tra `instanceof` để phân tích cấu trúc `Type`.
6. Với field `T`, nếu cần type argument cụ thể của subclass, xây ánh xạ biến kiểu qua generic hierarchy.
7. Khi muốn đọc/ghi giá trị, xử lý quyền và receiver tách khỏi metadata; không mặc định `getDeclaredField` đã cấp quyền.
8. Với scanner, quyết định cách xử lý field synthetic, field bị hiding và thứ tự liệt kê.

Tự kiểm tra:

- Field khai báo `List<String> names`: `getType()` và `getGenericType()` khác nhau thế nào?
- `Child.class.getField("id")` tìm field do `Parent` khai báo: `getDeclaringClass()` trả về đâu?
- Trong `class Box<T extends Number> { T value; T[] values; }`, raw type của hai field là gì?
- `getGenericType()` trả loại `Type` nào cho `List<? extends Number>`? Lấy `WildcardType` ở đâu?
- Khi field `T` được khai báo trong `Box<T>`, vì sao tra qua `Box<String>` theo một subclass vẫn có thể thấy `T`?
- Vì sao field `Parent.code` và `Child.code` phải được coi là hai field riêng biệt?
- Khi một công cụ chỉ cần liệt kê tên/kiểu field private, có nhất thiết gọi `setAccessible(true)` không?

**Ghi nhớ:** `Field.getName()` là **tên**, `getDeclaringClass()` là **nơi khai báo**, `getType()` là **kiểu erased dưới dạng `Class`**, còn `getGenericType()` là **kiểu theo chữ ký khai báo dưới dạng `Type`**. Bốn câu trả lời phối hợp để hiểu cấu trúc field; không câu trả lời nào tự động cho biết giá trị của field hay cấp quyền truy cập vào giá trị đó.

Tài liệu tham khảo chuẩn Java 17: [`Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html), [`Type`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html), [`ParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html), [`TypeVariable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html), [`GenericArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html), [`WildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/WildcardType.html).
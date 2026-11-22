# Không suy ra đối số kiểu tùy ý từ `getClass()` của đối tượng

## 1. Mục tiêu học tập

Trong Java Generics, kiểu `Box<String>` và `Box<Integer>` giúp trình biên dịch kiểm tra những lời gọi ở **mã nguồn**. Nhưng phương thức `Object.getClass()` không tự trả về thông tin rằng một instance cụ thể của `Box` đã được khai báo là `Box<String>` hay `Box<Integer>`. Đây là giới hạn căn bản khi suy luận **đối số kiểu** (*type arguments*) ở runtime.

Sau bài này, bạn có thể:

- Phân biệt **runtime class**, **tham số kiểu khai báo** `T` và **đối số kiểu tại chỗ sử dụng** như `String`.
- Giải thích chính xác vì sao `box.getClass()` không phục hồi một cách tổng quát đối số generic gắn với biến `Box<String>`.
- Dùng `getClass()`, `getTypeParameters()`, `Field.getGenericType()`, `getGenericSuperclass()` và `ParameterizedType` đúng phạm vi.
- Nhận biết ngoại lệ **metadata từ khai báo lớp con** hoặc anonymous subclass: đôi khi reflection đọc được `Box<String>`, nhưng không phải lúc nào cũng xác định được `T` cụ thể.
- Chỉ ra vì sao kiểu thực của giá trị bên trong (`String`) **không đủ** để chứng minh kiểu generic của container.
- Chủ động bảo toàn metadata bằng `Class<T>` hoặc mẫu **type reference** khi chương trình thực sự cần thông tin kiểu ở runtime.
- Tránh các thiết kế reflection, serializer hoặc factory dựa trên suy đoán từ `getClass()`.

Bài sử dụng **Java 17+**. Các ví dụ hoàn chỉnh đã được biên dịch, chạy và đối chiếu với output thực tế.

## 2. Ba khái niệm cần tách rời

Xét lớp:

```java
class Box<T> {
    private T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}
```

Và hai chỗ sử dụng:

```java
Box<String> word = new Box<>("Java");
Box<Integer> count = new Box<>(42);
```

Ba câu hỏi khác nhau:

| Khái niệm | Ví dụ | Có ý nghĩa gì? |
| --- | --- | --- |
| **Runtime class** | `word.getClass()` | Định nghĩa lớp của đối tượng đang chạy: `Box` |
| **Tham số kiểu trong khai báo** | `T` của `class Box<T>` | Biến kiểu trong khai báo lớp, không phải giá trị `String` hoặc `Integer` |
| **Đối số kiểu trong mã nguồn** | `Box<String>`, `Box<Integer>` | Lựa chọn kiểu của một biểu thức, biến hoặc quan hệ kế thừa để compiler kiểm tra |
| **Runtime class của giá trị** | `word.get().getClass()` | Lớp thật của một giá trị hiện chứa trong hộp: `String`, nếu giá trị khác `null` |

**Câu kết luận trung tâm:** `word.getClass()` không tương đương một phép toán tưởng tượng `getActualTypeArgument(word)`. Java không có API chuẩn nào có thể khôi phục đối số generic tùy ý của **mọi** instance chỉ bằng `Object.getClass()`.

Cả hai lệnh `new Box<>("Java")` và `new Box<>(42)` tạo đối tượng của cùng runtime class `Box`, giả sử chúng tham chiếu cùng định nghĩa class trong cùng ngữ cảnh nạp lớp. Chúng là **hai instance độc lập**, nhưng có cùng `Class` metadata cho `Box`.

## 3. Vì sao `getClass()` không khôi phục đối số generic?

Java generics chủ yếu được triển khai theo **type erasure (xóa kiểu)**. Khi `T` không có giới hạn trên tường minh, `T` có erasure là `Object`. Compiler kiểm tra kiểu ở source, rồi sinh bytecode sử dụng các JVM descriptors thích hợp.

Mã nguồn:

```java
class Box<T> {
    private T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}
```

Bản phác thảo **chỉ để hiểu cơ chế** (không phải một lớp `BoxErased` thực sự phải tồn tại):

```java
class BoxErasedSketch {
    private Object value;
    BoxErasedSketch(Object value) { this.value = value; }
    Object get() { return value; }
}
```

Ở cấp JVM descriptor, những nơi dùng `T` không giới hạn tương ứng với `Object`:

| Thành phần | Dạng trong source | Descriptor JVM |
| --- | --- | --- |
| Field | `T value` | `Ljava/lang/Object;` |
| Constructor | `Box(T value)` | `(Ljava/lang/Object;)V` |
| Getter | `T get()` | `()Ljava/lang/Object;` |

Type erasure không có nghĩa mọi `String` bị biến thành đối tượng mới thuộc `Object.class`. Một `String` lưu trong field vẫn là `String` thật, và có thể được cast về `String` khi cần. Điều biến mất khỏi runtime class chung là **đối số kiểu cụ thể của mỗi cách sử dụng** `Box<T>`.

Vì không sinh một runtime class `Box<String>` riêng, phép so sánh thông thường sau trả `true`:

```java
Box<String> a = new Box<>("A");
Box<Integer> b = new Box<>(1);
boolean sameRuntimeClass = a.getClass() == b.getClass(); // true
```

Đừng nhầm `a.getClass() == b.getClass()` với `a == b`: hai biến `a`, `b` ở ví dụ là hai đối tượng khác nhau. Ngoài ra, Java có thể từ chối so sánh trực tiếp `a == b` vì hai kiểu tham số hóa không tương thích; muốn kiểm tra identity instance bất kể kiểu nguồn, có thể gán chúng vào `Object` trước.

## 4. Chương trình đầy đủ: kiểm chứng bằng Java và reflection

Tạo tệp **`RuntimeTypeArgumentDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.List;
import java.util.Objects;

public class RuntimeTypeArgumentDemo {
    static class Box<T> {
        private T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
    }

    static final class StringBox extends Box<String> {
        StringBox(String value) { super(value); }
    }

    static <T> Box<T> makeAnonymous(T value) {
        return new Box<T>(value) {};
    }

    abstract static class TypeRef<T> {
        private final Type type;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType p)) {
                throw new IllegalStateException(
                        "Missing parameterized superclass");
            }
            type = p.getActualTypeArguments()[0];
        }

        Type getType() { return type; }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Box<String> text = new Box<>("Java");
        Box<Integer> number = new Box<>(42);

        System.out.println("same class: "
                + (text.getClass() == number.getClass()));
        System.out.println("class: " + text.getClass().getSimpleName());
        System.out.println("type parameter: "
                + Box.class.getTypeParameters()[0].getName());

        Field field = Box.class.getDeclaredField("value");
        System.out.println("erased field: "
                + field.getType().getTypeName());
        System.out.println("generic field: "
                + field.getGenericType().getTypeName());
        System.out.println("value classes: "
                + text.get().getClass().getSimpleName() + ", "
                + number.get().getClass().getSimpleName());
        System.out.println("null value: "
                + (new Box<String>(null).get() == null));

        Box<String> subclass = new StringBox("A");
        System.out.println("subclass class: "
                + subclass.getClass().getSimpleName());
        System.out.println("subclass superclass: "
                + subclass.getClass()
                        .getGenericSuperclass().getTypeName());

        Box<String> anonymous = new Box<String>("B") {};
        System.out.println("anonymous superclass: "
                + anonymous.getClass()
                        .getGenericSuperclass().getTypeName());

        Box<String> factoryBox = makeAnonymous("C");
        System.out.println("factory superclass: "
                + factoryBox.getClass()
                        .getGenericSuperclass().getTypeName());

        TypeRef<List<String>> captured = new TypeRef<List<String>>() {};
        System.out.println("captured nested type: "
                + captured.getType().getTypeName());
        System.out.println("generic list class only: "
                + List.of("X").getClass().getSimpleName());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac -Xlint:all RuntimeTypeArgumentDemo.java
java RuntimeTypeArgumentDemo
```

**Stdout đã kiểm chứng (JDK 17 ở môi trường kiểm thử):**

```text
same class: true
class: Box
type parameter: T
erased field: java.lang.Object
generic field: T
value classes: String, Integer
null value: true
subclass class: StringBox
subclass superclass: RuntimeTypeArgumentDemo$Box<java.lang.String>
anonymous superclass: RuntimeTypeArgumentDemo$Box<java.lang.String>
factory superclass: RuntimeTypeArgumentDemo$Box<T>
captured nested type: java.util.List<java.lang.String>
generic list class only: List12
```

**Chú ý tính di động của output:** dòng cuối `generic list class only: List12` cho biết tên lớp hiện thực nội bộ của `List.of("X")` trong JDK được kiểm thử; tên ấy **không phải hợp đồng API và có thể khác theo bản JDK**. Đừng sử dụng tên `List12` cho nghiệp vụ hay dùng nó để đoán kiểu phần tử.

### Đọc đúng từng bằng chứng

**`same class: true`:** `new Box<String>(...)` và `new Box<Integer>(...)` đều tạo `Box`. JVM không phải chuyên biệt hóa class theo từng đối số kiểu.

**`type parameter: T`:** `Box.class.getTypeParameters()` trả thông tin về tham số kiểu **được khai báo trong class**. Nó trả tên `T`, không trả `String` chỉ vì ta đang giữ `Box<String>`.

**`erased field: java.lang.Object`:** `Field.getType()` cho kiểu runtime bị xóa của field. Với field `T value` không bound, đây là `Object`.

**`generic field: T`:** `Field.getGenericType()` đọc metadata generic về **khai báo field**, nên có thể trả một `TypeVariable` tên `T`. Hai kết quả `Object` và `T` trả lời **hai câu hỏi khác nhau**.

**`value classes: String, Integer`:** `text.get().getClass()` và `number.get().getClass()` trả runtime class của **giá trị bên trong** chứ không trả type argument đã được gắn vào bản thân `Box`.

**`null value: true`:** với `new Box<String>(null)`, không có giá trị để gọi `getClass()`. Ngay cả nếu có giá trị, loại thực tại một thời điểm không chứng minh hợp đồng generic tổng quát.

Các dòng metadata lớp con và anonymous class được giải thích ở các phần sau; chúng là những trường hợp **có thông tin generic trong khai báo**, không bác bỏ type erasure.

## 5. Đối số kiểu của biến không phải một phần runtime identity

Hãy phân biệt:

```java
Box<String> first = new Box<>("A");
Box<CharSequence> second = new Box<>("B");
```

Một hộp `Box<CharSequence>` có thể hiện đang chứa `String` vì `String` implement `CharSequence`. Nếu bạn nhìn `second.get().getClass()`, kết quả có thể là `String.class`, nhưng điều đó không có nghĩa `second` được khai báo là `Box<String>` — nó có thể là `Box<CharSequence>`.

Ví dụ khác:

```java
Box<Number> measurement = new Box<>(Integer.valueOf(5));
Object item = measurement.get();
System.out.println(item.getClass().getSimpleName()); // Integer
```

Mặc dù giá trị thật là `Integer`, loại đối số nguồn vẫn là `Number`. Đoán `T = Integer` từ giá trị hiện tại sẽ sai.

Ngoài ra:

- Một `Box<Object>` có thể chứa `String` hôm nay, rồi `Integer` ngày mai nếu lớp có setter.
- Một `Box<String>` có thể chứa `null`, khiến `getClass()` của giá trị không dùng được.
- Một container có thể chứa subtype của kiểu đối số: quan sát subtype không chứng minh kiểu generic là subtype đó.
- Việc dùng unchecked cast hoặc raw type có thể phá hợp đồng generic, khiến kiểu giá trị không còn khớp với kiểu nguồn đã khai báo.

**Không tồn tại phép suy luận ngược tổng quát:** từ một vài giá trị runtime, không thể luôn xác định duy nhất kiểu tham số hóa mà compiler đã dùng cho biến hoặc biểu thức ở source.

## 6. `getClass()` trả cái gì chính xác?

`Object.getClass()` trả một đối tượng `java.lang.Class` đại diện cho runtime class **thực của receiver**. Nó không nhận đối số type token và không khai báo API kiểu `Class<Box<String>>` cho mọi lần gọi trên `Box<String>`.

Ví dụ:

```java
Box<String> text = new Box<>("Java");
System.out.println(text.getClass() == Box.class); // true
```

Nếu là lớp con thực sự:

```java
Box<String> special = new StringBox("Java");
System.out.println(special.getClass() == Box.class); // false
```

Trong ví dụ thứ hai, `getClass()` trả `StringBox.class` vì instance được tạo bởi constructor `StringBox`, không phải vì tham số hóa `String` khiến Java sinh class mới.

Điều này cũng đúng khi biến có kiểu interface:

```java
List<String> list = new java.util.ArrayList<>();
System.out.println(list.getClass().getName()); // java.util.ArrayList
```

Ở đây `getClass()` biết implementation runtime là `ArrayList`, không tự suy ra kiểu `String`. Một `ArrayList<Integer>` tạo trực tiếp từ cùng class loader cũng có runtime class `ArrayList`.

Không nên phụ thuộc tên lớp implementation của factory như `List.of(...)` để suy ra kiểu phần tử: Java được quyền lựa chọn implementation nội bộ khác nhau và có thể dựa vào kích thước danh sách, không phải generic type argument.

## 7. Reflection có thể đọc khai báo generic, không đọc một type argument “bí mật” của mọi instance

Một số API reflection thường bị hiểu quá mức:

| API | Đọc thông tin gì? | Có tự khôi phục `Box<String>` từ một instance `new Box<>("A")` không? |
| --- | --- | --- |
| `obj.getClass()` | Runtime class của đối tượng | Không |
| `Box.class.getTypeParameters()` | Các **type variables** khai báo trên `Box<T>` | Không; trả `T` |
| `Box.class.getDeclaredField("value").getType()` | Kiểu runtime/erasure của field | Không; trả `Object` |
| `Field.getGenericType()` | Generic type trong **khai báo field** | Không; ở `T value` trả `T` |
| `SomeSubclass.class.getGenericSuperclass()` | Generic superclass **được ghi trong khai báo lớp con** | Đôi khi trả `Box<String>` nếu lớp con khai báo như vậy |
| `getGenericInterfaces()` | Generic interfaces của **khai báo runtime class** | Đọc metadata class/interface, không phải mọi cách sử dụng instance |
| `Field.getGenericType()` trên `Box<String> field` | Metadata kiểu của **field khai báo rõ `Box<String>`** | Biết kiểu field, không kiểm chứng mọi trạng thái runtime |

Cụ thể, khi bạn khai báo:

```java
class Holder {
    Box<String> named;
}
```

Reflection có thể đọc `Holder.class.getDeclaredField("named").getGenericType()` và thấy `Box<java.lang.String>` vì **field `named` được khai báo là `Box<String>` trong source**. Nhưng nếu lấy riêng object đang nằm trong field và chỉ gọi `obj.getClass()`, thông tin tham số hóa của **field tham chiếu ban đầu** không nhất thiết còn xác định được.

Điểm này rất quan trọng trong serializer, dependency injection, mapping: metadata của **vị trí khai báo** (field, method parameter, method return type, supertype) khác metadata của **runtime instance**.

## 8. Khi metadata của lớp con có thể chứa `String`

Trong chương trình thực hành:

```java
static final class StringBox extends Box<String> {
    StringBox(String value) { super(value); }
}
```

Khi biên dịch `StringBox`, quan hệ `extends Box<String>` là **khai báo tường minh**. Class file có thể giữ generic `Signature` của quan hệ kế thừa. Vì thế:

```java
Box<String> box = new StringBox("A");
Type genericParent = box.getClass().getGenericSuperclass();
System.out.println(genericParent.getTypeName());
```

có thể in:

```text
RuntimeTypeArgumentDemo$Box<java.lang.String>
```

Tên lớp ngoài tương ứng chương trình ở phần 4. Ở đây có một chuỗi kiểm tra:

1. `box.getClass()` xác định runtime class là `StringBox`.
2. `StringBox.class.getGenericSuperclass()` đọc **khai báo kế thừa** của `StringBox`.
3. Khai báo ấy chứa `Box<String>`, do vậy reflection nhìn thấy `String`.

Đây **không** phải phép khôi phục `T` tùy ý từ một đối tượng trực tiếp của `Box<T>`. Nó là đọc một metadata tường minh đã được lưu trên lớp con. Nếu object được tạo bằng `new Box<>("A")`, runtime class của nó là `Box`, không có khai báo lớp con `extends Box<String>` để đọc.

Với cấu trúc kế thừa phức tạp như `Child<U> extends Box<List<U>>`, metadata có thể chứa **biến kiểu `U`**, không phải một loại `List<String>` cụ thể. Muốn resolve đến một kiểu cụ thể cần biết chuỗi binding của biến kiểu qua các lớp — và đôi khi không thể resolve vì thông tin nguồn không hiện diện trong khai báo runtime.

## 9. Anonymous subclass: trường hợp capture có điều kiện

Một kỹ thuật quen thuộc:

```java
Box<String> anonymous = new Box<String>("B") {};
Type t = anonymous.getClass().getGenericSuperclass();
System.out.println(t.getTypeName());
```

Trong chương trình ở phần 4, kết quả là:

```text
RuntimeTypeArgumentDemo$Box<java.lang.String>
```

Cú pháp dấu ngoặc nhọn cuối `{ }` tạo **anonymous subclass** của `Box<String>`, không đơn thuần tạo instance trực tiếp của `Box`. Compiler có class file riêng cho anonymous subclass và metadata generic của **quan hệ superclass** được ghi vào đó. Vì vậy reflection có thể đọc `String`.

So sánh cẩn thận:

```java
Box<String> ordinary = new Box<>("A");
Box<String> anonymous = new Box<String>("B") {};
```

- `ordinary.getClass()` là `Box.class`.
- `anonymous.getClass()` là một anonymous subclass khác `Box.class`.
- `anonymous.getClass().getGenericSuperclass()` có thể chứa `Box<String>` bởi chính khai báo của subclass.
- Cả hai đều dùng generics; không có cơ chế tự ghi `String` vào mọi instance của `Box`.

### Bẫy quan trọng: anonymous subclass bên trong phương thức generic

Đoạn này có vẻ tạo `Box<String>` khi gọi với chuỗi:

```java
static <T> Box<T> makeAnonymous(T value) {
    return new Box<T>(value) {};
}

Box<String> box = makeAnonymous("C");
```

Tuy nhiên class anonymous được biên dịch trong một ngữ cảnh mà superclass biểu diễn là **`Box<T>`**, không phải `Box<String>` cho từng lời gọi. Tại thời điểm biên dịch, `T` là type variable; JVM không tạo lại class anonymous mới mỗi khi `makeAnonymous` được suy luận `T = String`.

Vì vậy output thực của ví dụ đầy đủ:

```text
factory superclass: RuntimeTypeArgumentDemo$Box<T>
```

Bài học: có `ParameterizedType` trong reflection chưa đủ để kết luận **actual type argument là một `Class` cụ thể**. `getActualTypeArguments()[0]` đôi khi là `TypeVariable` như `T`, hoặc một `ParameterizedType` lồng nhau, không nhất thiết `String.class`.

## 10. `ParameterizedType` không luôn trả về `Class<?>`

Khi gọi:

```java
Type parent = StringBox.class.getGenericSuperclass();
if (parent instanceof ParameterizedType p) {
    Type argument = p.getActualTypeArguments()[0];
    System.out.println(argument.getTypeName()); // java.lang.String
}
```

`getActualTypeArguments()` có kiểu trả về `Type[]`, **không phải** `Class<?>[]`. Một phần tử của mảng có thể là:

- `Class<?>` — ví dụ `java.lang.String`;
- `ParameterizedType` — ví dụ `java.util.List<java.lang.String>`;
- `TypeVariable<?>` — ví dụ `T` trong quan hệ `Box<T>`;
- `WildcardType` — ví dụ đối số `? extends Number`;
- `GenericArrayType` — ví dụ một kiểu mảng có thành phần là type variable trong khai báo thích hợp.

Cho nên cast bừa `(Class<?>) p.getActualTypeArguments()[0]` có thể gây `ClassCastException`, hoặc lấy được một `Class` nhưng vẫn bỏ sót kiểu lồng nhau. Reflection API mô tả **cấu trúc kiểu đã khai báo**, không hứa mọi nhánh cuối đều là `Class`.

Với trường hợp metadata chứa `T` chưa được resolve, muốn xác định giá trị thực phải có binding rõ ràng từ khai báo/đối số truyền vào. Nếu binding không tồn tại ở runtime, thuật toán reflection dù phức tạp cũng không thể “đoán” chính xác cho mọi instance.

## 11. Type reference: giữ thông tin kiểu phức tạp theo chủ đích

Java cho phép khai báo một anonymous subclass **có chứa type argument cụ thể trong metadata**. Mẫu khái niệm:

```java
abstract class TypeRef<T> {
    private final Type type;

    protected TypeRef() {
        Type supertype = getClass().getGenericSuperclass();
        if (!(supertype instanceof ParameterizedType p)) {
            throw new IllegalStateException("No parameterized superclass");
        }
        type = p.getActualTypeArguments()[0];
    }

    Type type() {
        return type;
    }
}
```

Đây là đoạn trích thiết kế (cần import `Type`, `ParameterizedType` và đặt trong tệp phù hợp); chương trình hoàn chỉnh chứa `TypeRef<T>` nằm ở mục 4.

Tại điểm sử dụng **khai báo cụ thể**:

```java
TypeRef<List<String>> ref = new TypeRef<List<String>>() {};
System.out.println(ref.type().getTypeName());
```

Output trong chương trình hoàn chỉnh, với phương thức đặt tên `getType()`, là:

```text
captured nested type: java.util.List<java.lang.String>
```

Đây là lý do một số thư viện serialization cung cấp các lớp kiểu như **type token / type reference** để biểu diễn `List<String>`. Quan trọng: chúng hoạt động bằng cách **lưu metadata kiểu khi code được biên dịch**, không khôi phục mọi đối số generic chỉ từ runtime `ArrayList` ngẫu nhiên.

**Giới hạn cần nhớ:** nếu tạo `new TypeRef<T>() {}` **bên trong phương thức generic có type variable `T` chưa cụ thể**, metadata có thể chỉ giữ chữ `T`; việc gọi phương thức với `String` không tự khiến anonymous subclass trở thành `TypeRef<String>` ở runtime.

Khi dùng các framework thật, hãy tuân thủ cách đăng ký type metadata mà framework hỗ trợ và tránh mặc định rằng object runtime có thể tự mô tả đầy đủ type arguments.

## 12. Giải pháp trực tiếp cho một kiểu runtime: truyền `Class<T>`

Nếu ứng dụng cần kiểm tra dữ liệu đến từ `Object`, một giải pháp đơn giản là yêu cầu caller truyền **`Class<T>` token**.

Tạo tệp **`ExplicitTypeTokenDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

public class ExplicitTypeTokenDemo {
    static final class TypedBox<T> {
        private final Class<T> type;
        private T value;

        TypedBox(Class<T> type, T value) {
            this.type = Objects.requireNonNull(type);
            this.value = type.cast(value);
        }

        Class<T> type() { return type; }
        T value() { return value; }

        void replaceFromExternal(Object input) {
            value = type.cast(input);
        }
    }

    public static void main(String[] args) {
        TypedBox<String> words = new TypedBox<>(String.class, "Java");
        TypedBox<Integer> numbers = new TypedBox<>(Integer.class, 7);

        System.out.println("same box runtime class: "
                + (words.getClass() == numbers.getClass()));
        System.out.println("stored tokens: "
                + words.type().getSimpleName() + ", "
                + numbers.type().getSimpleName());

        try {
            words.replaceFromExternal(42);
        } catch (ClassCastException ex) {
            System.out.println("wrong scalar: "
                    + ex.getClass().getSimpleName());
        }

        List<?> values = List.class.cast(List.of(1, 2));
        System.out.println("list token accepts integers: "
                + (values.get(0) instanceof Integer));
    }
}
```

Chạy:

```bash
javac -Xlint:all ExplicitTypeTokenDemo.java
java ExplicitTypeTokenDemo
```

**Stdout đã kiểm chứng:**

```text
same box runtime class: true
stored tokens: String, Integer
wrong scalar: ClassCastException
list token accepts integers: true
```

Ở đây:

- `TypedBox<String>` và `TypedBox<Integer>` vẫn dùng **cùng runtime class `TypedBox`**.
- Mỗi **instance** lưu một field `Class<T> type` được truyền tường minh lúc khởi tạo. Đó là **trạng thái của instance**, không phải `getClass()` tự khôi phục `T`.
- `Class.cast` kiểm tra object ở runtime đối với class token tương ứng: yêu cầu `String` nhưng nhận `Integer` sẽ ném `ClassCastException`.
- `List.class` chỉ nhận biết đối tượng có là một `List` hay không. Token này không thể kiểm tra tất cả phần tử là `String`, nên `List<Integer>` cũng được chấp nhận ở mức class token `List.class`.

Điểm cuối cực kỳ quan trọng: `Class<T>` hoạt động với **lớp có thể kiểm tra ở runtime** như `String.class` hoặc `Integer.class`, không đại diện đầy đủ cho `List<String>` vì không có class literal `List<String>.class`.

Khi cần kiểm tra dữ liệu của một list raw, bạn có thể **duyệt và validate từng phần tử** trước khi công bố một `List<String>` an toàn. Type reference mô tả metadata phức tạp, nhưng metadata đơn thuần không tự xác thực dữ liệu nếu không có bước kiểm tra tương ứng.

## 13. Field, method và kiểu khai báo: biết “ở đâu” có metadata

Không phải mọi trường hợp erasure đều xóa tất cả metadata generic khỏi class file. Reflection phân biệt hai nhóm:

**Nhóm A — Type erasure/descriptor mà JVM dùng cho lời gọi.** Ví dụ field `T value` không bound có kiểu erased là `Object`. Method `T get()` có descriptor trả `Object`.

**Nhóm B — Generic `Signature` mô tả một khai báo.** Class file do `javac` tạo có thể ghi rằng `Box` khai báo `T`, field được khai báo kiểu `T`, hoặc `StringBox` khai báo `extends Box<String>`.

Bạn có thể kiểm tra trực tiếp bằng:

```bash
javap -p -s 'RuntimeTypeArgumentDemo$Box'
```

Trích kết quả từ bản chạy đã kiểm tra:

```text
class RuntimeTypeArgumentDemo$Box<T> {
  private T value;
    descriptor: Ljava/lang/Object;

  RuntimeTypeArgumentDemo$Box(T);
    descriptor: (Ljava/lang/Object;)V

  T get();
    descriptor: ()Ljava/lang/Object;
}
```

Dòng hiển thị `T` trong signature không mâu thuẫn với descriptor `Object`. `javap` có thể đọc generic metadata để trình bày khai báo; JVM descriptor vẫn dùng kiểu erased.

Để quan sát metadata của lớp con, dùng:

```bash
javap -v -p 'RuntimeTypeArgumentDemo$StringBox'
```

Tìm `Signature` mô tả quan hệ `extends Box<String>`. Bạn đang đọc **khai báo của StringBox**, không phải một thuộc tính riêng biệt được gắn vào mọi `Box<String>` tạo trực tiếp.

Một lưu ý liên quan bridge method: ghi đè generic ở lớp con đôi khi khiến compiler tạo bridge để bảo toàn quan hệ override sau erasure. Việc có bridge cũng **không** đồng nghĩa nó lưu type argument của mọi instance; bridge phục vụ dispatch/compatibility ở runtime.

## 14. Thiết kế API: chọn metadata vừa đủ, đúng nguồn tin

### Trường hợp 1 — Chỉ cần dùng kiểu ở compile time

Viết lớp/phương thức generic bình thường:

```java
static <T> T identity(T value) {
    return value;
}
```

Compiler có thể suy luận `T`; ứng dụng không cần lưu token khi không có nghiệp vụ kiểm tra kiểu runtime.

### Trường hợp 2 — Cần kiểm tra object đầu vào từ dữ liệu động

Nhận `Class<T>`, ví dụ `String.class`, rồi dùng `type.cast(value)`. Phù hợp khi type target là class có thể kiểm tra được.

### Trường hợp 3 — Cần mô tả `List<String>`, `Map<String, Integer>`

Dùng API giữ một đối tượng `Type`/`ParameterizedType` hoặc type-reference ở vị trí khai báo cụ thể. Nếu cần **xác thực dữ liệu**, phải thực hiện các bước kiểm tra phần tử và key/value phù hợp với metadata đó. Chỉ giữ `Type` không tự ngăn lỗi dữ liệu.

### Trường hợp 4 — Biết tham số generic từ khai báo subclass

Có thể đọc `getGenericSuperclass()` hoặc `getGenericInterfaces()`, xử lý `ParameterizedType`, `TypeVariable` và hierarchy. Đây là công việc đọc metadata class graph, không phải phép suy luận đơn giản từ `getClass()`.

### Trường hợp 5 — Đã có một instance `Box<T>` thông thường và không có thông tin phụ

Chấp nhận giới hạn: **không đủ dữ liệu để suy ra `T` tùy ý**. Đừng đoán bằng phần tử đầu tiên, giá trị hiện tại, tên implementation, hoặc unchecked cast. Nếu nghiệp vụ cần type argument ở runtime, sửa hợp đồng API để mang token/metadata từ đầu.

## 15. Những lỗi phổ biến và cách sửa

**Lỗi 1: Coi `getClass()` của `Box<String>` sẽ trả `Box<String>.class`.**

Không tồn tại class literal `Box<String>.class` theo cách đó. `Box.class` mô tả runtime class chung. Chọn một token riêng hoặc khai báo subclass lưu metadata nếu cần thông tin generic.

**Lỗi 2: Dùng `Box.class.getTypeParameters()[0]` và nghĩ đó là `String`.**

API ấy trả `TypeVariable` được khai báo, tên thường là `T`. Nó không phụ thuộc vào object `new Box<>("...")` đang được inspect.

**Lỗi 3: Dùng `box.get().getClass()` để khôi phục `T`.**

Giá trị có thể là subtype, có thể `null`, hoặc container có thể thay đổi nội dung. Lớp thực của phần tử không xác định được hợp đồng đối số generic.

**Lỗi 4: Coi mọi `getGenericSuperclass()` là `ParameterizedType`.**

Nó có thể trả `Class` hoặc các dạng `Type` khác tùy hierarchy. Kiểm tra kiểu bằng `instanceof` trước khi dùng `getActualTypeArguments()`.

**Lỗi 5: Ép `Type` thành `Class<?>` vô điều kiện.**

Đối số thực tế có thể là `ParameterizedType`, `TypeVariable`, wildcard hoặc generic array type. Dùng API phù hợp cho từng nhánh và luôn tính tới trường hợp không resolve được.

**Lỗi 6: Anonymous subclass trong generic factory phải bắt được kiểu `String`.**

Nếu factory khai báo `<T>` và tạo `new Box<T>() {}`, metadata ghi `Box<T>`. Runtime không tự chuyên biệt hóa class anonymous cho mỗi lần gọi.

**Lỗi 7: Đánh đồng type metadata với validation dữ liệu.**

`TypeRef<List<String>>` có thể mô tả kiểu mong muốn, nhưng danh sách nhận từ dữ liệu không kiểm soát vẫn có thể chứa `Integer`. Muốn an toàn cần kiểm tra thực tế, nhất là khi đi qua raw types/unchecked casts.

**Lỗi 8: Phụ thuộc `ArrayList`/`List.of` implementation class để biết kiểu phần tử.**

Implementation class chỉ cho biết lớp thực hiện collection. Các type arguments không được suy ra từ tên class nội bộ.

**Lỗi 9: Nhầm `Class<T>` lưu trong `TypedBox` với `TypedBox.class`.**

Field `type` có thể khác nhau trên từng instance, dù `getClass()` của mọi `TypedBox` vẫn giống nhau. Giải pháp đến từ **token được truyền tường minh**, không từ generic erasure tự đảo ngược.

## 16. Bài tập kiểm tra hiểu biết

### Bài 1 — Cùng class, khác kiểu nguồn

```java
Box<String> a = new Box<>("A");
Box<Integer> b = new Box<>(1);
```

`a.getClass() == b.getClass()` cho kết quả gì?

**Đáp án:** `true`, nếu cả hai tạo trực tiếp cùng runtime class `Box`. Kiểu generic dùng để kiểm tra compile time không sinh hai lớp runtime tách biệt.

### Bài 2 — Kiểu giá trị không xác định kiểu đối số

```java
Box<Number> number = new Box<>(Integer.valueOf(8));
```

Nếu `number.get().getClass()` là `Integer.class`, có suy ra `Box<Integer>` được không?

**Đáp án:** không; khai báo nguồn là `Box<Number>`, còn giá trị hiện tại có runtime class `Integer`.

### Bài 3 — Metadata của lớp con

Một lớp khai báo `class S extends Box<String> { ... }`. `S.class.getGenericSuperclass()` có thể cho biết gì?

**Đáp án:** khai báo superclass là `Box<String>` nhờ generic `Signature` của **class S**. Điều này không có nghĩa mọi instance được tạo trực tiếp bằng `new Box<>(...)` đều mang metadata tương tự.

### Bài 4 — Bẫy factory

Giả sử `static <T> Box<T> make(T value) { return new Box<T>(value) {}; }`. Gọi `make("text")` thì superclass signature của anonymous subclass chứa `String` hay `T`?

**Đáp án:** chứa `T` theo khai báo generic tại nơi compiler tạo anonymous class; không tự tạo signature mới theo mỗi lời gọi với type inference.

### Bài 5 — Đối số generic lồng nhau

`new TypeRef<List<String>>() {}` giữ loại metadata nào? Vì sao `List.class` chưa đủ?

**Đáp án:** giữ một `Type` biểu diễn `List<String>` trong khai báo anonymous subclass. `List.class` chỉ chỉ ra lớp/interface raw `List`; nó không mang `String` là đối số generic.

### Bài 6 — Thiết kế kiểm tra tại runtime

Một API nhận `Object` từ nguồn ngoài và mong `String`. Bạn chọn cách nào?

**Gợi ý đáp án:** nhận một `Class<String>` như `String.class`, dùng `type.cast(obj)` và xử lý `ClassCastException` phù hợp ở boundary. Không dựa vào `getClass()` của container để suy ra kiểu mong muốn.

### Bài 7 — Kiểm tra reflection an toàn

Khi lấy `Type type = someClass.getGenericSuperclass()`, có nên viết luôn `((ParameterizedType) type).getActualTypeArguments()[0]`?

**Đáp án:** không nên cast vô điều kiện. Kiểm tra `type instanceof ParameterizedType` trước; và ngay cả khi đúng, argument có thể là `TypeVariable`, `ParameterizedType`, `WildcardType` hoặc kiểu khác thay vì `Class`.

### Bài 8 — Field metadata và object metadata

Một field được khai báo `Box<String> named` có thể hiển thị `Box<String>` qua `Field.getGenericType()`. Nếu lấy object trong field rồi chỉ gọi `getClass()`, có chắc được `String` không?

**Đáp án:** không. Reflection đọc thông tin từ **chữ ký khai báo field**, trong khi `getClass()` trả runtime class của object. Hai nguồn dữ liệu khác nhau.

## 17. Checklist thực hành

Trước khi dùng `getClass()` để quyết định kiểu dữ liệu, hãy tự hỏi:

1. Mình đang cần runtime **class thực** hay **đối số kiểu generic ở source**?
2. Kiểu này có reifiable ở runtime không, hay đã bị erasure?
3. Thông tin mình đọc từ reflection thuộc **class declaration**, **field/method signature**, hay chính object?
4. Nếu `getGenericSuperclass()` trả `ParameterizedType`, argument là `Class` hay một `TypeVariable` chưa resolve?
5. Có cách hợp lý hơn để yêu cầu caller truyền `Class<T>` hoặc `Type` từ đầu không?
6. Nếu data đến từ nguồn ngoài/raw type, đã validate dữ liệu thật hay mới chỉ thu thập metadata?
7. Nếu object đang chứa `null` hoặc subtype, logic suy luận có còn đúng không?
8. Đã có ví dụ kiểm thử với hai kiểu tham số hóa tạo từ cùng class và một generic factory chưa?

## Ghi nhớ

**`Object.getClass()` nói về lớp runtime của object, không phải một phép giải mã tổng quát các đối số kiểu Java Generics.** Type erasure cho phép `Box<String>` và `Box<Integer>` dùng chung runtime class `Box`; những thông tin như `String` có thể còn trong metadata **khai báo subclass, field hoặc type reference** khi được ghi rõ từ lúc biên dịch, nhưng không phải thuộc tính tự sinh của mọi instance. Nếu bài toán thực sự cần biết kiểu runtime, hãy **truyền token hoặc metadata tường minh**, và kiểm tra dữ liệu tại nơi cần thiết, thay vì đoán kiểu generic từ `getClass()`.

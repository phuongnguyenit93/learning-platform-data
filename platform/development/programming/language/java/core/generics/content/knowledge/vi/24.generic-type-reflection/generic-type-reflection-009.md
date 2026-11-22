# Giới hạn phục hồi `T` chưa được ràng buộc và chi phí xử lý siêu dữ liệu kiểu trong Java

## Mục tiêu học tập

Java Generics cho phép viết `Box<T>`, `List<String>` và những thuật toán chỉ cần một implementation để hoạt động với nhiều kiểu. Nhưng khi chương trình cần **phản chiếu kiểu (type reflection)**, hai câu hỏi tưởng giống nhau thực ra khác hẳn:

1. “Lớp/field/method này **được khai báo** dùng kiểu gì?” — reflection có thể đọc một phần generic metadata của khai báo.
2. “Với **instance này**, type variable `T` thực sự đã được ràng buộc thành class nào ở nơi tạo/giữ object?” — thường **không thể phục hồi** nếu không có một nguồn ràng buộc tường minh.

Ngoài giới hạn thông tin, việc đi qua class hierarchy, duyệt `Type`, giải quyết `TypeVariable`, tạo/cấu trúc lại `ParameterizedType` và quét nhiều field bằng reflection có chi phí xử lý. Không nên làm việc ấy liên tục trên đường xử lý nóng (*hot path*) nếu có thể tính một lần rồi tái sử dụng metadata.

Sau bài này, bạn sẽ:

- Phân biệt runtime `Class<?>`, `Type`, `TypeVariable`, `ParameterizedType` và **type argument cụ thể của một chỗ sử dụng**.
- Chứng minh `Box<String>` và `Box<Integer>` trực tiếp đều dùng runtime class `Box`, không có token `T.class` từ generic type variable.
- Giải thích khi nào subclass hoặc anonymous subclass giữ `Signature` chứa `String`, và vì sao generic factory `<X>` lại chỉ giữ `X`.
- Thấy trường hợp **thừa kế nhiều tầng** cần map biến kiểu giữa các tầng trước khi suy ra type argument.
- Dùng `Class<T>` hoặc type reference được khai báo ở ngữ cảnh cụ thể để mang metadata chủ động.
- Hiểu `Type`/token kiểu không đồng nghĩa **kiểm tra dữ liệu lồng nhau**.
- Phân biệt chi phí truy vấn metadata, chi phí resolve hierarchy, chi phí kiểm tra từng phần tử, chi phí cache và chi phí class-loading.
- Dùng `ClassValue` cho cache theo runtime class, biết giới hạn của cache và những sai lầm khi benchmark.

**Yêu cầu:** Java 17+ (`javac`, `java`, `javap`), không dùng thư viện ngoài. Ba chương trình chạy độc lập đã được biên dịch với `-Xlint:all`; output dưới đây là kết quả đã xác minh, trừ những đoạn được ghi rõ chỉ minh họa hoặc cố tình không biên dịch.

## 1. Bốn tầng thông tin kiểu cần tách bạch

Giả sử có khai báo:

```java
class Box<T> {
    private final T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}
```

Và code sử dụng:

```java
Box<String> words = new Box<>("Java");
Box<Integer> count = new Box<>(42);
```

Hãy phân biệt:

| Tầng | Ví dụ | Có thể hỏi bằng API nào? | Giới hạn |
| --- | --- | --- | --- |
| Runtime class của object | `words.getClass()` | `Object.getClass()` | Chỉ thấy class thực `Box`, không biết `String` |
| Generic parameter **khai báo** | `T` trong `class Box<T>` | `Class.getTypeParameters()` | Nhận biến `T`, không phải binding của mọi instance |
| Generic type của một **declaration** | Field `T value`, `extends Box<String>` | `Field.getGenericType()`, `Class.getGenericSuperclass()` | Đọc chữ ký đã được lưu tại khai báo cụ thể |
| Kiểu của **giá trị đang giữ** | `words.get()` chứa `String` | `value.getClass()` nếu khác null | Không chứng minh `T`: có thể null hoặc subtype |

Ở source, compiler dùng `String` để bảo vệ lời gọi với `Box<String>`. Nhưng với class generic thông thường, JVM không tạo phiên bản runtime `Box<String>` và `Box<Integer>` độc lập. Chúng dùng cùng định nghĩa runtime class `Box`.

Điểm mấu chốt: **metadata của một khai báo khác với dữ liệu gắn trên mỗi instance**. Chẳng hạn một field được khai báo `Box<String> field` có thể giữ metadata kiểu của **field**; sau khi lấy riêng object rồi chỉ gọi `getClass()`, object ấy không tự tiết lộ rằng người dùng từng gắn nó vào field như vậy.

## 2. Type erasure không có phép đảo ngược tổng quát

Với type variable `T` không có bound tường minh, bound hiệu dụng là `Object`:

```java
class Box<T> {
    private T value;
    T get() { return value; }
}
```

Ở cấp JVM descriptor, vị trí `T` dùng dạng erased `Object`:

```text
Field T value             -> descriptor: Ljava/lang/Object;
Method T get()            -> descriptor: ()Ljava/lang/Object;
Constructor Box(T)        -> descriptor: (Ljava/lang/Object;)V
```

Class file có thể chứa thuộc tính `Signature` để công cụ reflection thấy rằng field được khai báo là `T`. Nhưng **`Signature` chứa chữ `T` không phải một bảng tra `T -> String` riêng cho từng object**.

Nếu `T extends Number`, erasure của vị trí dùng `T` thường là upper bound đầu tiên, ở đây là `Number`. Điều đó cũng **không** giúp đoán một instance dùng `Integer`, `Double` hay `BigDecimal`: một bound chỉ cho biết tập ràng buộc, không chỉ ra type argument cụ thể.

Về nguyên lý, nhiều lựa chọn ở source có thể cùng biểu diễn bằng một runtime class. Vì vậy, nếu chương trình **không lưu binding ở đâu cả**, reflection không có dữ liệu để “đảo ngược” type erasure. Không thể cải thiện giới hạn ấy chỉ bằng việc gọi nhiều API reflection hơn hoặc dựng thuật toán tìm class phức tạp hơn.

## 3. Những cú pháp bị cấm khi `T` chưa reifiable

Trong một class generic, các thao tác sau **cố ý không biên dịch**:

```java
class IllegalTypeRecovery<T> {
    Class<?> type() { return T.class; }
    T create() { return new T(); }
    boolean check(Object value) { return value instanceof T; }
}
```

Đây là tệp minh họa **negative test**, không phải chương trình cần chạy. Thử lưu tên `IllegalTypeRecovery.java` rồi dùng:

```bash
javac IllegalTypeRecovery.java
```

Trên trình biên dịch Java đã kiểm chứng, các lỗi tương ứng là:

```text
error: cannot select from a type variable
error: unexpected type
error: Object cannot be safely cast to T
3 errors
```

Vì `T` không là một runtime class literal cụ thể nên:

- Không thể viết `T.class` để lấy token.
- Không thể gọi `new T()` khi không biết class/constructor thực.
- Không thể kiểm tra `value instanceof T` với một type variable không reifiable.

Không nên thay các dòng ấy bằng unchecked casts rồi xem như đã phục hồi `T`. Nếu cần tạo/check đối tượng runtime, hãy truyền một `Class<T>` hoặc factory có hợp đồng phù hợp ngay từ chỗ gọi.

## 4. Chương trình A — Đọc metadata nào còn và metadata nào không còn

Tạo tệp **`TypeRecoveryDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.List;

public class TypeRecoveryDemo {
    static class Box<T> {
        private final T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
    }

    static final class NamedStringBox extends Box<String> {
        NamedStringBox(String value) { super(value); }
    }

    static class GenericChild<U> extends Box<List<U>> {
        GenericChild(List<U> value) { super(value); }
    }

    static final class ConcreteChild extends GenericChild<String> {
        ConcreteChild(List<String> value) { super(value); }
    }

    abstract static class TypeRef<T> {
        private final Type type;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType p)) {
                throw new IllegalStateException(
                        "Expected parameterized parent");
            }
            type = p.getActualTypeArguments()[0];
        }

        Type type() { return type; }
    }

    static <X> TypeRef<X> makeRef(X value) {
        return new TypeRef<X>() {};
    }

    public static void main(String[] args)
            throws NoSuchFieldException {
        Box<String> text = new Box<>("Java");
        Box<Integer> number = new Box<>(42);
        System.out.println("same runtime class: "
                + (text.getClass() == number.getClass()));
        System.out.println("runtime class: "
                + text.getClass().getSimpleName());

        TypeVariable<?> declared = Box.class.getTypeParameters()[0];
        Field field = Box.class.getDeclaredField("value");
        System.out.println("type variable: " + declared.getName());
        System.out.println("upper bound: "
                + declared.getBounds()[0].getTypeName());
        System.out.println("erased field: "
                + field.getType().getSimpleName());
        System.out.println("declaration type: "
                + field.getGenericType().getTypeName());
        System.out.println("values: "
                + text.get().getClass().getSimpleName() + ", "
                + number.get().getClass().getSimpleName());
        System.out.println("null has no class: "
                + (new Box<String>(null).get() == null));

        System.out.println("fixed parent: "
                + NamedStringBox.class
                        .getGenericSuperclass().getTypeName());
        System.out.println("intermediate parent: "
                + GenericChild.class
                        .getGenericSuperclass().getTypeName());
        System.out.println("concrete parent: "
                + ConcreteChild.class
                        .getGenericSuperclass().getTypeName());

        Type concreteRef = new TypeRef<List<String>>() {}.type();
        Type unresolvedRef = makeRef("hello").type();
        System.out.println("captured type: "
                + concreteRef.getTypeName());
        System.out.println("generic factory type: "
                + unresolvedRef.getTypeName());
        System.out.println("factory unresolved: "
                + (unresolvedRef instanceof TypeVariable<?>));
    }
}
```

Chạy:

```bash
javac -Xlint:all TypeRecoveryDemo.java
java TypeRecoveryDemo
```

**Stdout đã kiểm chứng:**

```text
same runtime class: true
runtime class: Box
type variable: T
upper bound: java.lang.Object
erased field: Object
declaration type: T
values: String, Integer
null has no class: true
fixed parent: TypeRecoveryDemo$Box<java.lang.String>
intermediate parent: TypeRecoveryDemo$Box<java.util.List<U>>
concrete parent: TypeRecoveryDemo$GenericChild<java.lang.String>
captured type: java.util.List<java.lang.String>
generic factory type: X
factory unresolved: true
```

Không có cảnh báo từ `javac -Xlint:all` với chương trình này.

## 5. Diễn giải kết quả: runtime class không mang `T` của mỗi object

Hai dòng đầu:

```text
same runtime class: true
runtime class: Box
```

được tạo khi hai **instance riêng biệt** `new Box<>("Java")` và `new Box<>(42)` cùng trả về runtime class `Box`. `getClass()` cho biết class thực đã tạo object chứ không khôi phục cách biến tham chiếu được tham số hóa ở source.

Các dòng kế:

```text
type variable: T
upper bound: java.lang.Object
erased field: Object
declaration type: T
```

minh họa hai lớp metadata:

- `Box.class.getTypeParameters()[0]` là `TypeVariable` biểu diễn **tham số khai báo `T`**. `getBounds()` cho biết `Object` khi không có bound khác.
- `Field.getType()` đọc **erased runtime field type**: `Object`.
- `Field.getGenericType()` đọc **generic type được khai báo cho field**: `T`.

Nhìn thấy `T` trong phản chiếu là **bằng chứng về chữ ký generic**, không phải bằng chứng rằng `T` của instance `text` đã được giải thành `String`.

## 6. Vì sao không suy từ giá trị đang chứa?

Chương trình in:

```text
values: String, Integer
null has no class: true
```

Ta có thể gọi `getClass()` trên đối tượng `text.get()` vì giá trị hiện tại là một `String`. Nhưng điều đó **không xác minh type argument của `Box`**.

Ví dụ:

```java
Box<CharSequence> a = new Box<>("Java");
Box<Number> b = new Box<>(Integer.valueOf(7));
```

Đây là đoạn minh họa dùng `Box` trong cùng ngữ cảnh class. Nếu gọi `a.get().getClass()`, kết quả là `String.class` dù type argument là `CharSequence`; còn `b.get().getClass()` là `Integer.class` dù type argument là `Number`.

Thêm các trường hợp khác:

- Một `Box<String>` có thể chứa `null`: không có object nào để hỏi runtime class.
- Một `Box<Object>` mutable có thể lần lượt chứa `String`, `Integer` rồi `List`.
- Một collection generic có thể rỗng hoặc chứa subtype của kiểu đã khai báo.
- Raw types và unchecked casts có thể làm dữ liệu không còn khớp với hợp đồng generic.

Do đó, “nhìn phần tử đầu tiên rồi chọn `T`” chỉ là **heuristic không đáng tin**. Nếu một API bắt buộc biết `T` chính xác, phải mang binding vào API bằng một token, một khai báo có metadata cụ thể, hoặc schema được cung cấp từ đầu.

## 7. Khi `getGenericSuperclass()` có thể cho biết kiểu cụ thể

Trong chương trình A:

```java
static final class NamedStringBox extends Box<String> {
    NamedStringBox(String value) { super(value); }
}
```

Khi compiler tạo class `NamedStringBox`, quan hệ **`extends Box<String>`** là một phần của **khai báo lớp con**. Generic `Signature` metadata có thể lưu quan hệ ấy để reflection xem:

```java
Type parent = NamedStringBox.class.getGenericSuperclass();
System.out.println(parent.getTypeName());
```

Với tệp `TypeRecoveryDemo.java`, kết quả:

```text
TypeRecoveryDemo$Box<java.lang.String>
```

Điều này **không mâu thuẫn với erasure**: metadata về khai báo `NamedStringBox` có `String`, còn JVM descriptors của các phương thức kế thừa vẫn dùng erased types.

Hai cách tạo phải được phân biệt:

```java
Box<String> direct = new Box<>("A");
Box<String> viaSubclass = new NamedStringBox("B");
```

- `direct.getClass()` là `Box.class`, không có subclass declaration để tìm `String`.
- `viaSubclass.getClass()` là `NamedStringBox.class`. Từ đó có thể đọc chính khai báo `extends Box<String>` của lớp con.

Nếu một object được chuyển qua nhiều biến tham chiếu có kiểu generic khác nhau mà runtime class không mang ràng buộc phù hợp, **không có cách reflection tổng quát** để khôi phục kiểu từng biến đã giữ nó.

## 8. Kế thừa nhiều tầng: metadata tồn tại nhưng chưa được giải hết

Ví dụ của chương trình A:

```java
static class GenericChild<U> extends Box<List<U>> {
    GenericChild(List<U> value) { super(value); }
}

static final class ConcreteChild extends GenericChild<String> {
    ConcreteChild(List<String> value) { super(value); }
}
```

Output:

```text
intermediate parent: TypeRecoveryDemo$Box<java.util.List<U>>
concrete parent: TypeRecoveryDemo$GenericChild<java.lang.String>
```

Hai lời gọi **khác nhau**:

- `GenericChild.class.getGenericSuperclass()` mô tả lớp cha trực tiếp của `GenericChild`: `Box<List<U>>`.
- `ConcreteChild.class.getGenericSuperclass()` mô tả lớp cha trực tiếp của `ConcreteChild`: `GenericChild<String>`.

Nếu bạn muốn tìm `Box<List<String>>` từ `ConcreteChild`, không thể chỉ lấy một `getGenericSuperclass()` rồi ép mù `getActualTypeArguments()[0]` thành `Class`.

Một resolver có căn cứ phải:

1. Đọc `ConcreteChild extends GenericChild<String>`.
2. Ghi binding `U` (được khai báo trong `GenericChild<U>`) thành `String`.
3. Đi tiếp tới `GenericChild extends Box<List<U>>`.
4. Thay `U` trong **cấu trúc `List<U>`** bằng binding `String` để thu được `List<String>`.
5. Bảo toàn owner types, nested parameterized types, wildcard và generic arrays nếu hierarchy có sử dụng chúng.

Đó là công việc **phân tích khai báo + giải thế type variables**, không phải “khôi phục type argument từ object” nếu thông tin vốn đã mất.

Cần đặc biệt chú ý: `getActualTypeArguments()` trả **`Type[]`**, không phải `Class<?>[]`. Các phần tử có thể là `Class`, `TypeVariable`, `ParameterizedType`, `WildcardType` hoặc `GenericArrayType`. Cast tất cả thành `Class<?>` sẽ không đúng cho cấu trúc như `List<U>`.

## 9. Type reference chỉ capture kiểu được ghi trong khai báo

Một mẫu thường gặp:

```java
abstract class TypeRef<T> {
    private final Type type;

    protected TypeRef() {
        Type parent = getClass().getGenericSuperclass();
        if (!(parent instanceof ParameterizedType p)) {
            throw new IllegalStateException(
                    "Expected parameterized parent");
        }
        type = p.getActualTypeArguments()[0];
    }

    Type type() { return type; }
}
```

Đây là đoạn minh họa của lớp `TypeRef`, cần imports tương ứng; chương trình A có định nghĩa đầy đủ.

Sử dụng ở một **vị trí cụ thể**:

```java
TypeRef<List<String>> ref = new TypeRef<List<String>>() {};
Type captured = ref.type();
```

Anonymous subclass mang trong khai báo `TypeRef<List<String>>`; reflection có thể đọc:

```text
java.util.List<java.lang.String>
```

Đó là **kiểu được lập trình viên/compile-time ghi rõ trong quan hệ kế thừa**, không phải kết quả đoán nội dung của một danh sách runtime.

Nếu code cần mô tả `Map<String, List<Integer>>`, một type reference khai báo đúng cấu trúc cũng có thể mang `ParameterizedType` lồng nhau. Nhưng **metadata mô tả kiểu mong đợi không tự xác minh dữ liệu thực**: một deserializer/validator vẫn phải kiểm tra key, value và từng phần tử theo quy tắc của nó.

## 10. Bẫy quan trọng: type reference tạo trong generic factory

Trong chương trình A:

```java
static <X> TypeRef<X> makeRef(X value) {
    return new TypeRef<X>() {};
}
```

Lời gọi:

```java
Type type = makeRef("hello").type();
```

cho output:

```text
generic factory type: X
factory unresolved: true
```

Nguyên nhân: anonymous subclass được biên dịch tại vị trí mà type argument vẫn là **type variable `X`** của phương thức generic. Lời gọi với `String` không làm `javac` phát sinh một anonymous class mới chuyên biệt cho `X=String`.

Đây là bẫy nghiêm trọng với những hàm tiện ích kiểu:

```java
static <T> Type inferT(T value) {
    return new TypeRef<T>() {}.type();
}
```

Hàm này chỉ capture **`T` của khai báo generic method**, không tự suy ra `String.class` của type argument trong lời gọi cụ thể. Nếu bạn cần kiểu đã được ràng buộc tại runtime, caller phải cung cấp `Class<T>` hoặc `Type` cụ thể, hoặc dùng một anonymous subclass được khai báo tại vị trí có type arguments cụ thể.

**Quy tắc nhanh:** hỏi “`T` được viết ở đâu?” Nếu `T` vẫn là biến kiểu khi compiler tạo lớp anonymous, metadata có thể chỉ giữ `T`. Nếu subclass ghi rõ `String` trong supertype declaration, metadata có cơ hội giữ `String`.

## 11. Không thể biến một `TypeVariable` chưa bind thành `Class` cụ thể

Một `TypeVariable<D>` cho biết:

- Tên biến, ví dụ `T`, `U`, `X`.
- Generic declaration đã khai báo nó (class, method hoặc constructor).
- Bounds hợp lệ, ví dụ `Number`, `Comparable<T>`.

Nó **không nhất thiết mang binding của mọi chỗ sử dụng**. Ví dụ `<T extends Number>` không cho biết `T` là `Integer`, `Long` hay `Double`.

Nếu resolver gặp một `TypeVariable` mà không có mapping tới type argument cụ thể từ những declarations đã đi qua, kết quả có thể phải **giữ nguyên TypeVariable** hoặc biểu diễn trạng thái unresolved. **Không được tự thay `T` bằng `Object` và tuyên bố đã tìm được type argument của người dùng.**

Erasure `T -> Object` là một quy tắc biên dịch JVM descriptors, không phải phép suy luận type arguments. Tương tự, thay `T extends Number` thành `Number` là một thông tin erased/bound, không chứng minh rằng caller đã chọn đúng `Number` thay vì một subtype.

Tại một cấp API, đôi khi chỉ cần erased `Class` là đủ để kiểm tra thô; khi cần **generic type chính xác**, hãy giữ lại trạng thái unresolved thay vì tạo cảm giác đã phục hồi đầy đủ.

## 12. Cơ chế thay thế: truyền `Class<T>` từ đầu

Đây là một cách thiết kế rõ ràng khi cần kiểu runtime của **một lớp cụ thể**:

```java
static <T> T require(Object input, Class<T> token) {
    if (!token.isInstance(input)) {
        throw new IllegalArgumentException("Invalid type");
    }
    return token.cast(input);
}
```

Với lời gọi:

```java
String s = require("hello", String.class);
Integer n = require(42, Integer.class);
```

compiler liên kết type parameter `T` với token truyền vào, và `Class.cast` thực hiện kiểm tra runtime theo token ấy.

**Đây không phải việc reflection tự suy ra `T`**; chính caller đã cung cấp metadata. Cách này rất thích hợp ở ranh giới I/O, plugin factory, deserialization của một kiểu class đơn lẻ hoặc cấu hình chuyển đổi dữ liệu.

Giới hạn cần nhớ:

- `Class<T>` không đại diện đầy đủ cho `List<String>`: không có `List<String>.class`.
- `Class.cast` kiểm tra kiểu runtime của **object**, không tự duyệt các phần tử generic bên trong.
- `String.class.cast(null)` trả `null`; nếu không cho phép null thì API cần quy định riêng.
- Token phải được liên kết nhất quán với kiểu `T`; raw `Class`/unchecked cast có thể phá lời bảo đảm compile-time.

## 13. Chương trình B — Validate dữ liệu theo token thay vì đoán `T`

Tạo tệp **`VerifiedBoundaryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class VerifiedBoundaryDemo {
    static <T> T require(Object candidate, Class<T> token) {
        Objects.requireNonNull(token, "token");
        if (!token.isInstance(candidate)) {
            throw new IllegalArgumentException(
                    "Expected " + token.getSimpleName());
        }
        return token.cast(candidate);
    }

    static <T> List<T> checkedCopy(List<?> input, Class<T> token) {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(token, "token");
        List<T> result = new ArrayList<>();

        for (int i = 0; i < input.size(); i++) {
            Object value = input.get(i);
            if (!token.isInstance(value)) {
                throw new IllegalArgumentException(
                        "Invalid index " + i);
            }
            result.add(token.cast(value));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println("single: "
                + require("ok", String.class));
        System.out.println("validated list: "
                + checkedCopy(List.of("A", "B"), String.class));

        try {
            checkedCopy(List.of("A", 9), String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        try {
            require(null, String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("null rejected: " + ex.getMessage());
        }

        System.out.println("list class accepts integers: "
                + List.class.isInstance(List.of(1, 2)));
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:all VerifiedBoundaryDemo.java
java VerifiedBoundaryDemo
```

**Stdout đã kiểm chứng:**

```text
single: ok
validated list: [A, B]
rejected: Invalid index 1
null rejected: Expected String
list class accepts integers: true
```

Không có cảnh báo compiler với `-Xlint:all`.

### Vì sao adapter kiểm tra từng phần tử?

`List.class.isInstance(List.of(1,2))` vẫn trả `true`: runtime object có implement `List`. Nhưng generic argument cụ thể không được JVM tái hiện qua token `List.class`.

Muốn trả một `List<String>` có thể tin cậy từ `List<?>` nhận ở ranh giới, `checkedCopy` làm ba việc tường minh:

1. Lấy từng phần tử nguồn dưới dạng `Object`.
2. Kiểm tra `token.isInstance(value)`, báo lỗi cụ thể khi gặp phần tử sai hoặc `null`.
3. Dùng `token.cast(value)` đưa giá trị đã kiểm tra vào một `ArrayList<T>` mới; trả `List.copyOf(result)`.

Đây là **validation runtime theo từng phần tử**, không phải phục hồi type argument đã mất. Nó cũng có chi phí tỷ lệ với số phần tử (`O(n)` kiểm tra, cộng chi phí sao chép), khác với việc đọc một vài metadata ở class level.

Nếu nguồn có thể bị sửa đồng thời hoặc chứa object mutable, phải thiết kế chính sách snapshot/ownership riêng. `List.copyOf` không tạo immutable sâu cho các phần tử mutable.

## 14. Vì sao đọc generic metadata có chi phí?

Các thao tác reflection không phải tất cả cùng mức độ. Đừng dùng một tuyên bố chung như “reflection luôn chậm” để kết luận mọi workload.

Có thể tách công việc thành các loại:

| Công việc | Ví dụ | Điểm chi phí chính |
| --- | --- | --- |
| Lấy class token đã có | `String.class` | Nhẹ, không quét hierarchy |
| Hỏi runtime class của object | `obj.getClass()` | Lấy class thực, không resolve generic bindings |
| Đọc generic declaration | `field.getGenericType()` | Phân tích/biểu diễn metadata tùy lớp và JDK |
| Liệt kê nhiều fields/methods | `getDeclaredFields()`, `getDeclaredMethods()` | Duyệt nhiều phần tử và có thể tạo mảng/các object mô tả |
| Duyệt hierarchy nhiều tầng | `getGenericSuperclass()` nhiều lần | Có thêm chi phí theo độ sâu và số nhánh |
| Resolve `TypeVariable` | `U -> String` qua hai lớp cha | Cần cấu trúc ánh xạ, đệ quy trên `Type` lồng nhau |
| Phân tích `ParameterizedType` | `getActualTypeArguments()` | Duyệt/cấu trúc biểu thức kiểu lồng nhau |
| Kiểm tra từng phần tử | `Class.isInstance` trong vòng lặp | Chi phí theo kích thước dữ liệu |
| Tạo/mở rộng cache | `ClassValue.get`, `computeValue` | Chi phí lookup, initial compute và lifecycle |

Một lời gọi `getGenericSuperclass()` đơn lẻ có thể hoàn toàn chấp nhận được ở bước khởi tạo. Vấn đề thường xuất hiện khi **cùng một schema/class bị phân tích lại rất nhiều lần** cho từng record hoặc request.

Một số triển khai JDK có cache nội bộ, nhưng không nên suy từ đó rằng toàn bộ pipeline resolver của ứng dụng là miễn phí. Ví dụ: nếu bạn tự tạo mapping `TypeVariable`, duyệt fields, xây descriptors cho serializer rồi bỏ đi ở mỗi request, phần việc bên ngoài cache nội bộ của JDK vẫn bị lặp lại.

**Không có con số nanosecond chung đáng tin** cho tất cả JVM/máy/cấu trúc metadata. Muốn nói một đoạn “chậm X lần”, cần đo bằng workload và cấu hình thực tế.

## 15. Mô hình chi phí đơn giản giúp chọn chỗ cache

Giả sử cùng một lớp schema cần phân tích cho `N` đối tượng.

Nếu mỗi đối tượng đều gọi lại trình phân tích hierarchy:

```text
tổng công việc ≈ N × (quét khai báo + resolve generic + áp dụng lên dữ liệu)
```

Nếu metadata được tính một lần rồi cache theo class:

```text
tổng công việc ≈ (quét khai báo + resolve generic) một lần
               + N × (lookup cache + áp dụng lên dữ liệu)
```

Đây chỉ là mô hình định hướng, **không phải benchmark hoặc công thức thời gian chính xác**. Lợi ích phụ thuộc vào kích thước hierarchy, độ phức tạp của types, số lần tái sử dụng class, contention, alloc/caching của JDK, GC và chi phí lookup.

Cache metadata giúp tránh lặp lại **phần không đổi theo class**. Nó không làm biến mất chi phí xử lý payload: nếu yêu cầu xác minh mỗi phần tử của một `List<?>`, bạn vẫn phải thực hiện kiểm tra phù hợp với dữ liệu của từng instance.

Hãy cache **sơ đồ đã được resolve**; đừng cache một kết quả suy đoán “`T=String`” chỉ từ runtime class `Box` rồi áp dụng cho mọi `Box<Integer>` có cùng class. Làm vậy vừa sai về logic vừa có thể gây heap pollution.

## 16. Thiết kế cache metadata theo `ClassValue`

`ClassValue<V>` là một cơ chế của JDK để liên kết một giá trị được tính với một runtime `Class<?>`. Đây là lựa chọn hữu ích cho metadata **thực sự phụ thuộc vào class**.

Ví dụ ý tưởng:

```java
static final ClassValue<Metadata> CACHE = new ClassValue<>() {
    @Override
    protected Metadata computeValue(Class<?> type) {
        return inspect(type);
    }
};

// Mỗi lần xử lý một đối tượng:
Metadata metadata = CACHE.get(value.getClass());
```

Đoạn trên là minh họa; `Metadata` và `inspect` cần được định nghĩa. Chương trình đầy đủ ở mục 17.

Ưu điểm của cách này:

- Truy vấn qua một `Class` key có sẵn.
- Có điểm tập trung để thực hiện việc phân tích metadata khi cần.
- Không cần duy trì thủ công một `static HashMap<Class<?>,...>` chứa keys mạnh trong một lifetime dài.
- Có thể gọi `remove(Class<?>)` khi muốn bỏ giá trị cached cho một class key.

Nhưng cần nắm giới hạn:

- **Cache chỉ tránh tính lặp metadata nếu metadata được định nghĩa đúng theo class.** Nó không giải được type argument `T` không được ghi trong class.
- `ClassValue.computeValue` có thể bị gọi nhiều hơn một lần trong một số cuộc đua concurrent/khởi tạo. Đừng đặt side effect nghiệp vụ không idempotent vào đó, hoặc suy luận rằng counter phải tăng đúng một lần trong mọi chương trình đa luồng.
- Cache tiêu thụ bộ nhớ; giá trị cached càng lớn, càng cần cân nhắc vòng đời và số lượng class phát sinh.
- Nếu metadata phụ thuộc vào cấu hình/schema version/classloader/locale ngoài `Class`, chỉ dùng `Class` làm key có thể sai. Phải xác định **key đầy đủ** hoặc tổ chức cache phù hợp.
- Không lưu reference đến một object input cụ thể trong metadata cache theo class, vì các instance của cùng class có thể có dữ liệu khác nhau.

## 17. Chương trình C — So sánh số lần phân tích trước/sau cache

Tạo tệp **`MetadataCacheDemo.java`**:

```java
import java.lang.reflect.Type;
import java.util.concurrent.atomic.AtomicInteger;

public class MetadataCacheDemo {
    static class Parent<T> {}
    static final class Child extends Parent<String> {}

    record Metadata(String className, String declaredParent) {}

    static final AtomicInteger uncachedCalls =
            new AtomicInteger();
    static final AtomicInteger cachedComputations =
            new AtomicInteger();

    static Metadata inspectFresh(Class<?> type) {
        uncachedCalls.incrementAndGet();
        Type parent = type.getGenericSuperclass();
        return new Metadata(type.getSimpleName(),
                parent == null ? "(none)" : parent.getTypeName());
    }

    static final ClassValue<Metadata> CACHE = new ClassValue<>() {
        @Override
        protected Metadata computeValue(Class<?> type) {
            cachedComputations.incrementAndGet();
            Type parent = type.getGenericSuperclass();
            return new Metadata(type.getSimpleName(),
                    parent == null ? "(none)" : parent.getTypeName());
        }
    };

    public static void main(String[] args) {
        for (int i = 0; i < 3; i++) {
            inspectFresh(Child.class);
        }
        System.out.println("fresh inspections: "
                + uncachedCalls.get());

        Metadata one = CACHE.get(Child.class);
        Metadata two = CACHE.get(Child.class);
        Metadata three = CACHE.get(Child.class);

        System.out.println("cache same reference: "
                + (one == two && two == three));
        System.out.println("cache computations: "
                + cachedComputations.get());
        System.out.println("declared parent: "
                + one.declaredParent());

        CACHE.get(String.class);
        System.out.println("after another class: "
                + cachedComputations.get());

        CACHE.remove(Child.class);
        CACHE.get(Child.class);
        System.out.println("after removal: "
                + cachedComputations.get());
    }
}
```

Chạy:

```bash
javac -Xlint:all MetadataCacheDemo.java
java MetadataCacheDemo
```

**Stdout đã kiểm chứng trong lượt chạy tuần tự:**

```text
fresh inspections: 3
cache same reference: true
cache computations: 1
declared parent: MetadataCacheDemo$Parent<java.lang.String>
after another class: 2
after removal: 3
```

Trong ví dụ:

- Ba lần gọi `inspectFresh(Child.class)` thực hiện phần thân phân tích ba lần theo cách viết của ứng dụng.
- Ba lần `CACHE.get(Child.class)` trong **một thread, không có remove** tái sử dụng một `Metadata` reference được tính ở lượt đầu.
- `CACHE.get(String.class)` đụng class key mới, làm tăng số lần tính.
- Sau `CACHE.remove(Child.class)`, lời gọi `CACHE.get(Child.class)` lại thực hiện `computeValue`.

**Đừng coi số đếm này là phép đo tốc độ.** Nó chỉ chứng minh **số lần code tự tính metadata** trong kịch bản điều khiển được. Một lookup cache cũng tốn công; việc tiết kiệm có đáng kể hay không phải đo với resolver và workload thật.

## 18. Các lựa chọn cache khác và vòng đời class loader

Một cache thông thường có thể viết:

```java
ConcurrentMap<Class<?>, Metadata> cache = new ConcurrentHashMap<>();
```

Đây là đoạn minh họa cần imports và lớp `Metadata` phù hợp. Với một hệ thống ít class, cùng một classloader sống suốt vòng đời ứng dụng, cách này có thể đủ đơn giản.

Nhưng trong hệ thống plugin, hot reload hoặc application server có thể tạo nhiều classloaders, **một cache static sống lâu giữ strong references tới `Class` và metadata liên quan** có thể góp phần làm classloader không được giải phóng.

Các cân nhắc thực tế:

| Cách lưu | Điểm mạnh | Điều cần kiểm tra |
| --- | --- | --- |
| Tính lại mỗi lần | Đơn giản, không quản lý cache | Có gây lặp phân tích khi số request lớn? |
| Biến cục bộ trong một thao tác | Tái sử dụng trong cùng request | Không tái sử dụng giữa request; tốt nếu workload nhỏ |
| `ClassValue<Metadata>` | Thiết kế cache gắn với class key của JDK | Semantics đồng thời; metadata phải phụ thuộc đúng class |
| `ConcurrentHashMap<Class<?>,Metadata>` | Linh hoạt, quen thuộc | Classloader retention, invalidation, số lượng key |
| Cache theo schema ID/version | Hợp khi metadata phụ thuộc cấu hình ngoài class | Key/đổi version, đồng bộ dữ liệu, evictions |

`ClassValue` thường đáng xem xét khi dữ liệu **thuần theo Class**. Tuy vậy, không có lựa chọn nào miễn phí hoặc đúng trong mọi hệ thống. Hãy đo lượng heap giữ lại, GC, số classloaders và hiệu quả hit rate trong điều kiện thực tế.

Nếu dùng `ClassValue` cho giá trị có **tham chiếu ra classloaders/objects bên ngoài**, vẫn cần xem xét vòng đời những thứ được tham chiếu. Không nên hứa “ClassValue không bao giờ leak”; điều đúng là nó cung cấp một cơ chế lifecycle gắn với `Class` phù hợp hơn việc giữ class keys mạnh vô thời hạn trong nhiều trường hợp.

## 19. Những thao tác nên làm một lần khi khởi tạo

Nếu ứng dụng dùng reflection để map JSON/database rows tới entity objects, một pipeline có thể:

1. Đọc metadata class/field/method một lần.
2. Resolve phần có thể resolve của generic hierarchy.
3. Kiểm tra annotation, constructor hoặc setter cần dùng.
4. Xây một immutable descriptor mô tả cách map dữ liệu.
5. Lưu descriptor vào cache theo class và schema version nếu cần.
6. Khi xử lý từng record, dùng descriptor đã chuẩn bị, chỉ làm validation/conversion thật sự phụ thuộc dữ liệu đầu vào.

Điều này vừa giảm lặp công việc, vừa tập trung logic kiểm tra lỗi metadata về giai đoạn dễ báo lỗi. Nhưng cần chú ý:

- Nếu class được nạp động, phần chuẩn bị có thể phải chạy khi plugin/schema lần đầu xuất hiện.
- Nếu metadata thay đổi theo runtime configuration, cache key/invalidation phải được thiết kế đúng.
- Nếu yêu cầu classloader unloading, không giữ tham chiếu mạnh tùy tiện từ singleton/cache không còn cần thiết.
- Không chia sẻ **mutable resolver state** cho nhiều thread nếu không có hợp đồng thread safety rõ.
- Việc dùng `ClassValue` không đồng nghĩa cache an toàn nếu `Metadata` chứa state bị sửa song song không đồng bộ.

Kết quả mong đợi: **mỗi class/schema ổn định được phân tích ít lần**, còn mỗi input vẫn được kiểm tra đúng hợp đồng tại ranh giới dữ liệu.

## 20. Phân biệt ba loại “chi phí” khi thực hiện reflection

### Chi phí phân tích metadata

Là các thao tác đọc `getGenericSuperclass()`, `getGenericInterfaces()`, `getDeclaredFields()`, `getGenericType()`, duyệt `TypeVariable` và cấu trúc hierarchy. Có thể được tính trước/cache khi phụ thuộc vào class.

### Chi phí áp dụng metadata lên từng object

Là kiểm tra null, gọi `Class.isInstance/cast`, parse dữ liệu, duyệt phần tử collection và xây kết quả. Chi phí này thường **tỷ lệ với số phần tử/fields cần xử lý**, khó loại bỏ hoàn toàn bằng cache.

### Chi phí quản lý cache

Là lookup, lazy initialization, đồng bộ nếu có, bộ nhớ giữ `Metadata`, invalidation và cache misses. Một cache khổng lồ có thể gây GC hoặc retention issues dù giảm số lần parse.

Đừng gom cả ba thành một chữ “reflection overhead”. Trong profile, có thể hot spot nằm ở **validation/serialization** hoặc công việc ứng dụng khác, chứ không phải ở `getGenericSuperclass()`.

## 21. Benchmark thế nào để không kết luận sai?

Nếu cần đánh giá một resolver thật sự, ưu tiên microbenchmark framework như **JMH** với warmup và kiểm soát JIT/GC. Không cần đo nanosecond chỉ để minh họa kiến thức; ví dụ ở mục 17 dùng counter vì mục tiêu là **định lượng số lần tính metadata trong một kịch bản**, không phải tuyên bố hiệu năng.

Quy trình hữu ích:

1. Xác định loại class metadata đại diện: lớp thường, subclass cụ thể, hierarchy nhiều tầng, generic type lồng nhau, class nạp động.
2. Tách ba workload: không cache, cache hit, cache miss/compute.
3. Warm up đủ để JVM tối ưu trước khi lấy mẫu.
4. Tiêu thụ kết quả benchmark đúng cách để tránh JIT loại bỏ công việc không quan sát được.
5. Đo throughput/latency phân phối, allocation rate, GC, CPU; không chỉ một giá trị thời gian trung bình.
6. Chạy nhiều fork/iteration có cấu hình rõ và cùng JDK/hardware.
7. Kiểm tra tính đúng của cache khi classloaders thay đổi, đa luồng hoặc schema version thay đổi.
8. So sánh với end-to-end workload để xem tối ưu resolver có thực sự đáng kể không.

Một vòng lặp gọi `System.nanoTime()` một lần quanh 1000 lời gọi reflection **không đủ đáng tin** để tuyên bố “cache nhanh hơn X lần”: ảnh hưởng của JIT, allocation, warmup, escape analysis và noise có thể lấn át khác biệt thực.

**Định hướng sản phẩm:** chỉ tối ưu sau khi có profile cho thấy metadata resolution là vấn đề có ý nghĩa. Duy trì tính đúng của generic bindings ưu tiên hơn một tối ưu nhỏ không được đo.

## 22. `getGenericSuperclass()` và các API liên quan không phải luôn trả `ParameterizedType`

Ví dụ lỗi phổ biến:

```java
ParameterizedType p =
        (ParameterizedType) someClass.getGenericSuperclass();
```

Đây là đoạn minh họa nguy hiểm: class cha có thể là một raw/non-parameterized class, hoặc `getGenericSuperclass()` trả `null` ở một số class như `Object`/interfaces; cast trực tiếp có thể gây `ClassCastException` hoặc lỗi khác.

Mẫu tốt hơn:

```java
Type parent = someClass.getGenericSuperclass();

if (parent instanceof ParameterizedType p) {
    for (Type argument : p.getActualTypeArguments()) {
        System.out.println(argument.getTypeName());
    }
} else {
    System.out.println("No parameterized direct superclass");
}
```

Đây là đoạn method minh họa, cần khai báo biến `someClass` và imports. Khi cần đi qua interface generic, còn phải đọc `getGenericInterfaces()`; không thể chỉ tìm superclass.

Tương tự, khi lấy `Type`, đừng cast ngay thành `Class<?>`. Metadata có thể là `TypeVariable` chưa resolve, wildcard hoặc `ParameterizedType` lồng nhau. Thường giải pháp tốt là thiết kế một bộ xử lý `Type` có các nhánh được định nghĩa rõ thay vì cast dựa trên một trường hợp đơn giản đang chạy được.

## 23. Chi phí của việc render metadata thành chuỗi

`Type.getTypeName()` rất hữu ích để log, debug và viết tests quan sát. Nhưng **chuỗi hiển thị không phải đối tượng kiểu có thể dùng để kiểm tra runtime**.

Ví dụ:

```java
Type complex = new TypeRef<List<String>>() {}.type();
String printed = complex.getTypeName();
```

`printed` có thể là `"java.util.List<java.lang.String>"`. Nó không phải `Class<List<String>>`, cũng không tự cung cấp mọi ràng buộc/checks cần thiết cho dữ liệu.

Nếu ứng dụng cần thực hiện các phép so sánh/resolve kiểu nhiều lần, có thể lưu **cấu trúc `Type`/descriptor đã chuẩn hóa** thay vì liên tục chuyển metadata thành chuỗi rồi parse lại. Stringification/parsing tự viết dễ bỏ sót owner types, generic arrays, wildcards, bounds và nested types.

Nên phân biệt:

- **Type object**: metadata có cấu trúc.
- **Type name string**: biểu diễn phục vụ con người/logging.
- **Class token**: runtime representation của một class/interface reifiable.
- **Data validation**: thuật toán kiểm tra object/collection theo yêu cầu nghiệp vụ.

Việc cache `getTypeName()` có thể hữu ích nếu log cùng metadata nhiều lần, nhưng đừng xem đó là nguồn đúng đắn để suy ra type arguments chưa tồn tại.

## 24. Trường hợp metadata có thể thiếu hoặc không resolve được

Ngoài type erasure, khi đọc metadata thực tế còn có thể gặp:

- Một raw class/supertype declaration không còn concrete type arguments.
- Type variable chỉ có bounds, không có binding cụ thể.
- Hierarchy qua nhiều interfaces với type variables cần substitutions.
- Generic signature metadata không hiện diện hoặc không hợp lệ trong bytecode được tạo từ công cụ khác.
- Các lớp từ classloader/plugin khác nhau, dù tên class trùng.
- Lớp được tạo động hoặc proxy có hierarchy khác class nghiệp vụ mà code mong đợi.
- Quyền truy cập/module constraints khi phản chiếu thành viên và gọi constructor/method (khác với việc chỉ đọc tên generic type).
- API nhận object không chứa thông tin gì về generic type argument của biến nguồn từng tham chiếu đến nó.

Trong những trường hợp ấy, một resolver vững chắc cần biểu diễn **unresolved** hoặc trả lỗi có ngữ cảnh. Không nên khẳng định “`T=Object`” chỉ vì bound là `Object`.

Nếu yêu cầu nghiệp vụ không thể thỏa do thiếu metadata, cách xử lý đúng là **sửa hợp đồng đầu vào** để nhận `Type`, `Class<T>` hoặc schema tường minh, không viết thêm các cast đoán mò.

## 25. Cách đối chiếu source và bytecode với `javap`

Sau khi biên dịch các chương trình đã kiểm chứng, chạy:

```bash
javap -p -s 'TypeRecoveryDemo$Box'
javap -p -s VerifiedBoundaryDemo
```

Các dấu nháy đơn quanh tên class lồng có ký tự `$` hữu ích trong Bash/PowerShell. Nếu `javap` chạy khác thư mục class file, thêm `-classpath <thư_mục>` tương ứng.

Phần output của `Box<T>`:

```text
class TypeRecoveryDemo$Box<T> {
  private final T value;
    descriptor: Ljava/lang/Object;

  TypeRecoveryDemo$Box(T);
    descriptor: (Ljava/lang/Object;)V

  T get();
    descriptor: ()Ljava/lang/Object;
}
```

Từ `VerifiedBoundaryDemo`:

```text
static <T> T require(java.lang.Object, java.lang.Class<T>);
  descriptor: (Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;

static <T> java.util.List<T> checkedCopy(java.util.List<?>, java.lang.Class<T>);
  descriptor: (Ljava/util/List;Ljava/lang/Class;)Ljava/util/List;
```

Chính sự khác nhau giữa **dòng generic method/field display** và **JVM descriptor** giúp bạn hiểu `T` được xóa trong executable signatures, trong khi metadata còn có thể mô tả declarations.

Nếu muốn xem generic metadata rõ hơn, dùng `javap -v` và tìm `Signature`. Hãy kiểm tra cả các subclass cụ thể như `TypeRecoveryDemo$NamedStringBox` và `TypeRecoveryDemo$ConcreteChild`.

**Không kết luận rằng metadata hiển thị ở `javap` là bằng chứng JVM đã tái tạo một `Box<String>` runtime class riêng.** Generic `Signature` có thể giữ khai báo nhưng method descriptors vẫn erased.

## 26. So sánh giải pháp khi cần biết kiểu

| Tình huống thực tế | Giải pháp phù hợp | Không nên làm |
| --- | --- | --- |
| Một `Box<T>` trực tiếp, chỉ có object | Chấp nhận giới hạn; thêm token/schema vào API | Đoán `T` từ `getClass()` |
| Class con `extends Box<String>` | Đọc `getGenericSuperclass()` và kiểm tra `Type` | Áp dụng kết luận cho mọi `Box<T>` |
| Subclass nhiều tầng | Duyệt hierarchy và thế `TypeVariable` có căn cứ | Chỉ gọi một cấp rồi cast về `Class` |
| Generic factory `<X>` | Truyền `Class<X>` hoặc `Type` cụ thể | Trông chờ `new TypeRef<X>() {}` thành `String` |
| Kiểu như `List<String>` | Type reference/`Type` + validation cần thiết | Dùng `List.class` để chứng minh phần tử String |
| Dữ liệu legacy `List<?>` | Kiểm tra từng phần tử rồi tạo typed copy | Unchecked cast cả list |
| Resolver dùng rất thường xuyên | Cache metadata đã resolve theo key đúng | Parse hierarchy lại cho từng record |
| Hệ thống plugin/hot-reload | Cân nhắc `ClassValue`, lifecycle, eviction | Giữ strong reference tới mọi class vô hạn |
| Cần số đo hiệu năng | Profile/JMH đại diện workload | Công bố tỷ lệ tăng tốc dựa trên vòng lặp đơn |

## 27. Những lỗi tư duy và lỗi code phổ biến

**Sai lầm 1 — “`Box<T>.getClass()` phải biết `T` vì object đã được tạo.”** Không đúng: object trực tiếp có runtime class `Box`; type argument của biến được compiler sử dụng không tự được ghi như state của object.

**Sai lầm 2 — “`getTypeParameters()[0]` trả actual type argument.”** API trả biến kiểu được **khai báo**, ví dụ `T`. Không đồng nghĩa `String`.

**Sai lầm 3 — “`getGenericSuperclass()` luôn là `ParameterizedType`.”** Không đúng. Kiểm tra `instanceof` và xử lý `Class`/`null` khi cần.

**Sai lầm 4 — “Một `ParameterizedType` chắc chắn có actual args là `Class`.”** Đối số có thể là `TypeVariable`, `ParameterizedType`, wildcard hoặc generic array type.

**Sai lầm 5 — “`new TypeRef<T>() {}` trong generic method bắt được kiểu đã suy luận ở lời gọi.”** Không đúng nếu `T` còn là type variable tại nơi subclass được biên dịch.

**Sai lầm 6 — “Biết giá trị đang là String là biết hộp có type argument String.”** Có thể là `Box<CharSequence>`, `Box<Object>`, hoặc giá trị khác trong lần xử lý khác.

**Sai lầm 7 — “Erasure của T là Object nên actual T chính là Object.”** Erasure không phải actual argument resolution; `Object` chỉ là dạng JVM sử dụng cho vị trí biến không bound.

**Sai lầm 8 — “`Class<List>` chứng minh mọi phần tử đều String.”** Không. Runtime `List` không chứa ràng buộc generic element type tự động.

**Sai lầm 9 — “Dùng unchecked cast là đủ để giải thích T.”** Không. Unchecked cast bỏ kiểm tra chứng minh, có thể đẩy lỗi sang runtime.

**Sai lầm 10 — “Cache metadata giúp phục hồi type arguments đã mất.”** Cache chỉ giữ thông tin đã tính hoặc có sẵn; nó không thêm thông tin không tồn tại.

**Sai lầm 11 — “ClassValue luôn gọi computeValue chính xác một lần trên mọi thread.”** Không nên giả định; cạnh tranh đồng thời có thể dẫn đến tính thừa. Viết hàm tính thuần/idempotent.

**Sai lầm 12 — “Cache `Class<?>` trong static map vô hạn không ảnh hưởng lifecycle.”** Có thể giữ classloaders/classes không còn dùng; cân nhắc lifetime và chính sách cache.

**Sai lầm 13 — “Đếm số lần tính metadata là đo tốc độ.”** Không. Counter chỉ cho biết số lần code chạy; chi phí mỗi thao tác/GC/JIT cần đo riêng.

**Sai lầm 14 — “Reflection luôn quá chậm và phải cache mọi thứ.”** Không có quy tắc tuyệt đối; tối ưu khi profile chứng minh hot spot và lợi ích vượt chi phí phức tạp của cache.

**Sai lầm 15 — “Metadata type name là schema validation.”** Một `Type`/chuỗi `List<String>` mô tả kỳ vọng; vẫn phải xác minh payload khi dữ liệu không đáng tin.

## 28. Bài tập thực hành có đáp án

### Bài 1 — Hai Box khác nhau

```java
Box<String> a = new Box<>("A");
Box<Integer> b = new Box<>(1);
```

**Hỏi:** `a.getClass() == b.getClass()` có thể là `true` không? Có suy ra `T` từ biểu thức đó không?

**Đáp án:** `true` khi cả hai tạo trực tiếp từ cùng class `Box`; phép so sánh không cho biết `String` hay `Integer`.

### Bài 2 — `TypeVariable` chưa resolve

Một generic method `<X> TypeRef<X> makeRef(X x)` tạo `new TypeRef<X>() {}`. Caller truyền `String`. `ref.type()` là gì?

**Đáp án:** metadata của anonymous subclass có thể giữ `X` của method declaration, không tự chuyên biệt hóa thành `String`. Chương trình A xác minh `generic factory type: X`.

### Bài 3 — Metadata lớp con

`class NamedStringBox extends Box<String>` có thể cung cấp gì qua `getGenericSuperclass()`?

**Đáp án:** khai báo `Box<String>` trên class con, vì `String` được ghi tường minh trong supertype declaration.

### Bài 4 — Kế thừa nhiều tầng

`GenericChild<U> extends Box<List<U>>` và `ConcreteChild extends GenericChild<String>`. Chỉ gọi `ConcreteChild.class.getGenericSuperclass()` đã ra `Box<List<String>>` chưa?

**Đáp án:** chưa; nó cho `GenericChild<String>`. Cần đi tiếp tới `GenericChild` và thế `U=String` trong `Box<List<U>>` để thu được cấu trúc tương ứng.

### Bài 5 — `Object` là erasure

Nếu `T` không bound, `Field.getType()` của `T field` trả `Object`. Có thể kết luận caller đã chọn `Box<Object>` không?

**Đáp án:** không. `Object` là erased field type, không phải actual type argument của một instance.

### Bài 6 — Viết API nhận token

Muốn một hàm nhận `Object` và trả `String` sau kiểm tra, nên dùng `String.class` như thế nào?

**Đáp án:** truyền `Class<T>` token vào generic method, dùng `token.isInstance`/ `token.cast`, với chính sách null rõ ràng. Không cần `T.class` trong generic method.

### Bài 7 — List lồng nhau

Một `List<Integer>` thỏa `List.class.isInstance`. Điều đó đủ xác nhận nó là `List<String>` chưa?

**Đáp án:** chưa. Token `List.class` chỉ kiểm tra interface runtime. Muốn bảo đảm danh sách toàn `String`, hãy kiểm tra phần tử hoặc dùng schema validation tương ứng.

### Bài 8 — Caching

Chạy `inspectFresh(Child.class)` ba lần rồi `CACHE.get(Child.class)` ba lần trong ví dụ C. Counter lần lượt là bao nhiêu?

**Đáp án:** `fresh inspections: 3`, `cache computations: 1` trong lượt chạy tuần tự được kiểm thử; đây không phải thời gian thực thi, và tình huống concurrent có thể khác.

### Bài 9 — Key cache sai

Một metadata resolver phụ thuộc cả `Class<?>` và phiên bản schema. Có đủ dùng `Class` làm key không?

**Đáp án:** không, nếu cùng class có thể được xử lý dưới những schema versions khác nhau. Cần cache key chứa version hoặc invalidation rõ ràng.

### Bài 10 — Classloader retention

Một `static ConcurrentHashMap<Class<?>,Metadata>` giữ các class từ plugin classloaders đã unload về mặt nghiệp vụ. Có rủi ro gì?

**Đáp án:** strong keys/values có thể giữ class và classloader reachable, góp phần ngăn giải phóng bộ nhớ. Cần xem lifecycle, eviction, cache thuộc đúng loader hoặc cân nhắc `ClassValue`.

### Bài 11 — Số đo hiệu năng

Một benchmark dùng `System.nanoTime()` một lần quanh vài lời gọi và công bố cache “nhanh hơn 100 lần”. Có đủ căn cứ không?

**Đáp án:** chưa. Cần warmup, kiểm soát JIT/GC/alloc, tiêu thụ kết quả và workload đại diện. JMH giúp giảm nhiều bẫy của microbenchmark.

### Bài 12 — Type reference như phép validation

Có `TypeRef<List<String>>` mô tả schema. Nếu dữ liệu thô có một `Integer` trong list, chỉ tạo type reference đã làm input hợp lệ chưa?

**Đáp án:** chưa. Type reference giữ metadata kỳ vọng, không tự kiểm tra payload. Cần validate/deserialize theo schema.

## 29. Checklist áp dụng trong dự án

- [ ] Phân biệt rõ **runtime class**, **generic declaration**, **binding từ superclass** và **type argument ở nơi sử dụng**.
- [ ] Không suy `T` tùy ý chỉ từ `obj.getClass()` hoặc runtime class của một phần tử.
- [ ] Không coi `TypeVariable` chưa bind là một `Class` cụ thể.
- [ ] Trước khi cast `Type`, kiểm tra dạng `Class` / `ParameterizedType` / `TypeVariable` / wildcard / generic array.
- [ ] Khi resolve hierarchy, thay type variables qua **từng tầng**, không chỉ nhìn superclass trực tiếp.
- [ ] Nếu cần runtime type, yêu cầu caller truyền `Class<T>`, `Type`, type reference hoặc schema.
- [ ] Nếu cần an toàn dữ liệu nested generic, kiểm tra phần tử/key/value theo hợp đồng.
- [ ] Không dùng unchecked cast để “giả lập” thông tin kiểu đã mất.
- [ ] Chỉ cache metadata có thể tái sử dụng theo key được định nghĩa đúng.
- [ ] Đã cân nhắc `ClassValue`, classloader lifecycle, concurrency, versioning và invalidation.
- [ ] Khi đánh giá hiệu năng, đã tách metadata resolution khỏi per-item validation và cost của cache.
- [ ] Đã profile/benchmark trên workload có ý nghĩa, không dựa vào số đếm hoặc thời gian một lượt.
- [ ] Đã đối chiếu generic `Signature` với erased JVM descriptor bằng `javap` khi cần.

## Kết luận

**Không thể phục hồi một `T` chưa được ràng buộc chỉ bằng `getClass()` hay phép reflection phức tạp hơn.** Type erasure khiến nhiều cách tham số hóa dùng chung runtime class, còn generic metadata được lưu tại **khai báo** chỉ có thể giúp giải kiểu khi tồn tại binding đủ cụ thể, như `extends Box<String>` hoặc type reference được ghi rõ. Với hierarchy nhiều tầng, cần thế các `TypeVariable` có căn cứ; nếu không có mapping, kết quả phải vẫn là **unresolved**, không đoán.

Về chi phí, metadata reflection nên được xử lý theo nhu cầu: phân tích một lần ở ranh giới phù hợp, tái sử dụng descriptor khi cùng class/schema lặp lại, và kiểm tra dữ liệu thực khi validation là bắt buộc. `ClassValue` có thể giảm số lần tự phân tích metadata theo class, nhưng cần thiết kế cache đúng vòng đời và đo hiệu năng thật trước khi tối ưu. **Ưu tiên tính đúng của generic bindings trước, rồi mới tối ưu chi phí đọc và resolve siêu dữ liệu.**

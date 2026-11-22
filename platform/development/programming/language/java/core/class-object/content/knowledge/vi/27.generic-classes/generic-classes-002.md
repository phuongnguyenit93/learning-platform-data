# Khai báo lớp `Box<T>`, trường và phương thức dùng `T` trong Java 17+

**Generic class** cho phép một lớp làm việc với nhiều kiểu dữ liệu mà vẫn được **kiểm tra kiểu tại thời điểm biên dịch**. Cú pháp mẫu:

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
~~~

`T` là **type parameter**, đại diện cho một kiểu tham chiếu do người sử dụng Box chọn khi khai báo `Box<String>`, `Box<Integer>`, `Box<Customer>`, v.v.

~~~java
Box<String> title = new Box<>("Java");
String text = title.get();       // Compiler biết kết quả là String.
title.set("Generics");          // Hợp lệ.
// title.set(123);             // Lỗi compile: int/Integer không là String.
~~~

Bài này tập trung vào **khai báo lớp `Box<T>` và thiết kế fields/constructors/methods sử dụng `T`**. Các chủ đề mở rộng như bounds, wildcards, type erasure, generic methods và restrictions được giải thích để bạn sử dụng Box đúng cách, nhưng mọi ví dụ đều quy chiếu trở lại một generic class đơn giản.

**Môi trường:** Java 17 trở lên. Những ví dụ có tên file là **chương trình độc lập**; mỗi ví dụ chứa đủ classes cần thiết, kèm lệnh `javac --release 17`, `java` và stdout dự kiến. Đoạn minh họa lỗi compiler luôn được comment hoặc tách riêng; không trộn vào chương trình cần chạy.

## 1. Kết quả học tập

Sau khi học, bạn có thể:

- Khai báo một generic class với một tham số kiểu `T`.
- Phân biệt **type parameter** `T` với **type argument** `String`.
- Dùng `T` cho instance field, constructor parameter, method parameter và return type.
- Khởi tạo `Box<String>` và `Box<Integer>` bằng cú pháp diamond `<>`.
- Giải thích cách compiler ngăn truyền sai kiểu vào `set(T)`.
- Biết `T` có phạm vi bên trong class declaration và instance members liên quan.
- Viết method đổi giá trị, lấy giá trị cũ, kiểm tra empty và chuyển đổi data.
- Hiểu sự khác nhau giữa `Box<T>` mutable và immutable Box.
- Phân biệt type parameter của **class** với type parameter của **generic method**.
- Biết static members không thể tham chiếu trực tiếp tới class type parameter `T`.
- Hiểu generic type erasure ở mức ảnh hưởng đến `new T()`, `T.class` và runtime tests.
- Không dùng raw `Box` nếu không có lý do interop legacy rõ ràng.
- Hiểu autoboxing khi dùng primitive-like values.
- Biết `Box<String>` không phải subtype của `Box<Object>`.
- Sử dụng wildcard references khi API cần đọc nhiều kiểu Box.
- Dùng bounded type parameter để gọi methods không có trên Object.
- Phân biệt null policy với type safety.
- Tránh expose mutable objects sai ownership.
- Thiết kế generic Box tương thích `equals/hashCode/toString` nếu cần.
- Viết unit-like tests chứng minh behavior và expected compile errors.

## 2. Không generic thì bất tiện gì?

Trước generics, một container có thể lưu `Object`:

~~~java
class ObjectBox {
    private Object value;

    ObjectBox(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}
~~~

Client phải cast:

~~~java
ObjectBox box = new ObjectBox("Java");
String text = (String) box.get();
~~~

Nếu box chứa Integer thay String, cast sai có thể dẫn đến `ClassCastException` tại runtime. Compiler không bảo đảm ObjectBox chỉ chứa một kiểu.

Với `Box<T>`:

~~~java
Box<String> box = new Box<>("Java");
String text = box.get();
~~~

Compiler biết contract của Box instance từ type argument String. Trường hợp cố `box.set(42)` sẽ bị từ chối sớm khi biên dịch.

**Generic mang lại compile-time type safety và giảm casts**, không tạo một class source code mới thủ công cho mỗi kiểu.

## 3. Chương trình chạy: Box đầu tiên

Tạo **`BasicBoxDemo.java`**:

~~~java
public class BasicBoxDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box<String> message = new Box<>("Java");
        Box<Integer> count = new Box<>(17);

        System.out.println("before=" + message.get());
        message.set("Generics");

        System.out.println("after=" + message.get());
        System.out.println("count=" + count.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BasicBoxDemo.java
java BasicBoxDemo
~~~

Stdout:

~~~text
before=Java
after=Generics
count=17
~~~

Cùng declaration Box<T> được dùng với String và Integer. `get()` trả đúng loại của mỗi reference `Box<String>` hoặc `Box<Integer>`.

## 4. Giải phẫu khai báo `class Box<T>`

~~~java
class Box<T> {
    private T value;
}
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| `class` | Khai báo class |
| `Box` | Tên lớp |
| `<T>` | Danh sách type parameters, ở đây có một `T` |
| `T value` | Instance field có kiểu là type parameter |
| `Box<String>` | Parameterized type với actual type argument String |
| `Box<Integer>` | Parameterized type với actual type argument Integer |

`T` không phải Java keyword, và không phải một class tên "T". Đó là một identifier đại diện cho kiểu do caller chọn.

Có thể thay tên:

~~~java
class Container<Element> {
    private Element value;
}
~~~

Nhưng theo convention Java, các tên một chữ hoa thường gặp là `T` (type), `E` (element), `K` (key), `V` (value), `R` (result). Chọn tên dễ đọc khi class có nhiều parameters.

## 5. Type parameter và type argument là hai khái niệm khác nhau

Trong declaration:

~~~java
class Box<T> {}
~~~

`T` là **type parameter**.

Ở use site:

~~~java
Box<String> words;
Box<Integer> numbers;
~~~

`String` và `Integer` là **type arguments**.

Khi type argument là String, những vị trí trong API Box sử dụng `T` được nhìn như String ở compile time:

~~~java
Box<String> box = new Box<>("A");
String value = box.get();
box.set("B");
~~~

Không có cú pháp Java dùng primitive trực tiếp cho reference type argument:

~~~java
// Box<int> error;       // Sai: primitive int không là reference type argument.
Box<Integer> correct;   // Đúng: Integer là reference type.
~~~

Autoboxing hỗ trợ viết `new Box<>(17)` khi target type là `Box<Integer>`.

## 6. Phạm vi của `T` bên trong class

Class type parameter `T` có thể dùng trong:

- Instance fields: `private T value;`
- Constructor parameters: `Box(T initial)`
- Instance method parameters: `void set(T next)`
- Instance method returns: `T get()`
- Local variables: `T previous = value;`
- Parameterized types: `List<T>` hoặc `Optional<T>`
- Nested instance/member type contexts theo quy tắc scope Java.

Không thể xem class type parameter như một global type variable để static method dùng tùy ý.

~~~java
class Box<T> {
    private T value;     // Đúng.

    T get() {
        return value;    // Đúng.
    }

    // static T shared; // Sai.
    // static T getShared() { return null; } // Sai.
}
~~~

Static member không gắn với riêng `Box<String>` hay `Box<Integer>` instance; vì vậy không thể dùng trực tiếp class parameter `T` ở static context đó.

## 7. Fields dùng `T` và ownership của dữ liệu

Ví dụ:

~~~java
class Box<T> {
    private T value;
}
~~~

Field `value` lưu:
- reference tới object nếu T là reference type;
- `null` nếu bạn cho phép;
- reference tới wrapper nếu dùng Box<Integer>, Box<Boolean>, v.v.

Generic field **không clone object** và không kiểm soát mutability. Với `Box<ArrayList<String>>`, caller và Box có thể cùng trỏ một mutable list nếu constructor lưu direct reference.

**Thiết kế:** Field nên `private`. Public mutable `T value` cho phép caller bypass validation/logic của setter. Nếu muốn read-only Box, chọn `private final T value` và không khai báo setter.

## 8. Constructor nhận tham số kiểu `T`

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }
}
~~~

Constructor name **không thêm `<T>` vào chính tên**. `T` đã được khai báo ở `class Box<T>` và nằm trong scope của constructor.

Sai:

~~~java
// Box<T>(T value) {} // Sai cú pháp constructor declaration.
~~~

Có thể có overload constructors, nhưng chú ý type erasure khi tạo overload cùng erasure signature.

Ví dụ no-arg constructor:

~~~java
Box() {
    this.value = null;
}
~~~

Chấp nhận empty state là decision của API, không phải tính chất bắt buộc của generics.

## 9. Chương trình chạy: overloaded constructors

Tạo **`BoxConstructorsDemo.java`**:

~~~java
public class BoxConstructorsDemo {
    static final class Box<T> {
        private T value;

        Box() {
            this.value = null;
        }

        Box(T value) {
            this.value = value;
        }

        boolean isEmpty() {
            return value == null;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> empty = new Box<>();
        Box<String> filled = new Box<>("Java");

        System.out.println("empty=" + empty.isEmpty());
        System.out.println("filled=" + filled.isEmpty());
        System.out.println("value=" + filled.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BoxConstructorsDemo.java
java BoxConstructorsDemo
~~~

Stdout:

~~~text
empty=true
filled=false
value=Java
~~~

Class có thể có nhiều constructors; type parameter T vẫn áp dụng nhất quán. Nếu API cấm null, hãy validate và chỉ đưa constructor chấp nhận hợp đồng đó.

## 10. Getter: method trả `T`

~~~java
T get() {
    return value;
}
~~~

Đối với `Box<String>`, compiler nhìn method `get()` trả String. Với `Box<Integer>`, compiler nhìn trả Integer.

~~~java
Box<String> words = new Box<>("hello");
String text = words.get();

// Integer wrong = words.get(); // Compile error.
~~~

Đây là compile-time view của generic API. Runtime do type erasure có thể khác về metadata, nhưng caller không cần tự cast khi dùng parameterized type đúng.

### Naming

`get()` phù hợp khi Box chỉ chứa một giá trị. Nếu field mang ý nghĩa domain, method `value()` cũng có thể rõ. Nên dùng một contract nhất quán để API dễ học.

## 11. Setter: method nhận `T`

~~~java
void set(T newValue) {
    value = newValue;
}
~~~

Với `Box<String>`, tham số `T` tương đương String ở call site; với Box<Integer> nó tương đương Integer.

Không được:

~~~java
Box<String> names = new Box<>("Mai");
// names.set(42); // Sai kiểu argument.
~~~

Nếu setter validate null, hoặc xây domain invariant, mọi call setter phải qua check. Nhưng đừng tự suy rằng generic compiler kiểm tra *nội dung* String có blank hay không: generic chỉ kiểm tra type.

## 12. Chương trình chạy: getter, setter, lỗi được ngăn từ compile time

Tạo **`GetterSetterDemo.java`**:

~~~java
public class GetterSetterDemo {
    static final class Box<T> {
        private T value;

        Box(T initial) {
            this.value = initial;
        }

        T get() {
            return value;
        }

        void set(T next) {
            value = next;
        }
    }

    public static void main(String[] args) {
        Box<String> box = new Box<>("first");

        String before = box.get();
        box.set("second");

        System.out.println(before);
        System.out.println(box.get());

        // box.set(123); // Uncomment: compile error.
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GetterSetterDemo.java
java GetterSetterDemo
~~~

Stdout:

~~~text
first
second
~~~

Uncomment `box.set(123)` để thấy javac từ chối argument không thể chuyển sang String.

## 13. Method vừa nhận vừa trả `T`: `replace`

Một generic Box có thể đổi value và trả giá trị cũ:

~~~java
T replace(T next) {
    T previous = value;
    value = next;
    return previous;
}
~~~

`T` ở cả input và output buộc cùng type contract.

### Chương trình chạy

Tạo **`ReplaceBoxDemo.java`**:

~~~java
public class ReplaceBoxDemo {
    static final class Box<T> {
        private T value;

        Box(T initial) {
            value = initial;
        }

        T replace(T next) {
            T previous = value;
            value = next;
            return previous;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<Integer> count = new Box<>(10);

        Integer old = count.replace(20);

        System.out.println("old=" + old);
        System.out.println("now=" + count.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ReplaceBoxDemo.java
java ReplaceBoxDemo
~~~

Stdout:

~~~text
old=10
now=20
~~~

Return `T` không bắt buộc là same object reference; nó là same **type parameter contract**.

## 14. Phương thức không nhất thiết phải dùng `T` ở mọi vị trí

Class generic vẫn có ordinary methods:

~~~java
class Box<T> {
    private T value;

    int descriptionLength() {
        return String.valueOf(value).length();
    }

    boolean isEmpty() {
        return value == null;
    }
}
~~~

`isEmpty()` trả boolean, không phải T. `descriptionLength()` trả int. Generics không có yêu cầu tất cả methods của generic class đều generic.

Hãy phân biệt:
- **Generic class:** class có `<T>` parameter.
- **Method uses T:** instance method lấy type parameter có sẵn.
- **Generic method:** method **khai báo một type parameter riêng**, ví dụ `<U> U convert(...)`.

## 15. Chương trình chạy: phương thức thường trong generic class

Tạo **`BoxMethodsDemo.java`**:

~~~java
public class BoxMethodsDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        boolean isEmpty() {
            return value == null;
        }

        String describe() {
            return "Box(" + value + ")";
        }
    }

    public static void main(String[] args) {
        Box<String> first = new Box<>("Java");
        Box<String> second = new Box<>(null);

        System.out.println(first.describe());
        System.out.println(first.isEmpty());
        System.out.println(second.isEmpty());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BoxMethodsDemo.java
java BoxMethodsDemo
~~~

Stdout:

~~~text
Box(Java)
false
true
~~~

Dùng `String.valueOf(value)` khi cần null-safe formatting; string concatenation với nullable reference sẽ in chữ "null" thay vì throw NPE.

## 16. Mutable Box và immutable Box: chọn ý định

**Mutable Box**:

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    void set(T next) {
        value = next;
    }
}
~~~

**Immutable-by-field Box**:

~~~java
final class ImmutableBox<T> {
    private final T value;

    ImmutableBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

`final T value` ngăn gán lại field. Nhưng nếu T là mutable object (như ArrayList), field chỉ là final reference — object bên trong vẫn có thể mutate.

Chọn mutable Box nếu lifecycle yêu cầu thay reference, còn immutable Box nếu muốn một **value holder** không thay reference sau construction.

## 17. Chương trình chạy: immutable Box tạo instance mới khi thay

Tạo **`ImmutableBoxDemo.java`**:

~~~java
public class ImmutableBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        Box<T> withValue(T next) {
            return new Box<>(next);
        }
    }

    public static void main(String[] args) {
        Box<String> before = new Box<>("A");
        Box<String> after = before.withValue("B");

        System.out.println("before=" + before.get());
        System.out.println("after=" + after.get());
        System.out.println("same instance=" + (before == after));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ImmutableBoxDemo.java
java ImmutableBoxDemo
~~~

Stdout:

~~~text
before=A
after=B
same instance=false
~~~

Method `withValue` trả một Box<T> khác; nó không mutate current Box.

## 18. Null policy cho generic Box

`T` là reference type, vì vậy null thường type-correct:

~~~java
Box<String> box = new Box<>(null);
~~~

Nếu API cấm null, dùng validation:

~~~java
Box(T value) {
    this.value = java.util.Objects.requireNonNull(
            value, "value");
}
~~~

Setter cũng phải validate:

~~~java
void set(T next) {
    value = java.util.Objects.requireNonNull(next, "value");
}
~~~

**Generic type safety không tự tạo null safety.** `Box<String>` bảo đảm đúng kind of reference ở compile time nhưng không bảo đảm khác null.

Nếu null biểu diễn empty state, ghi rõ `isEmpty()`, `getOrDefault()`, hoặc cân nhắc `Optional<T>` khi API thật sự đại diện cho “có hoặc không có giá trị”.

## 19. Chương trình chạy: kiểm tra null ở constructor và setter

Tạo **`NonNullBoxDemo.java`**:

~~~java
import java.util.Objects;

public class NonNullBoxDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = Objects.requireNonNull(value, "value");
        }

        void set(T next) {
            value = Objects.requireNonNull(next, "value");
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> box = new Box<>("Java");

        try {
            box.set(null);
        } catch (NullPointerException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("after=" + box.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 NonNullBoxDemo.java
java NonNullBoxDemo
~~~

Stdout:

~~~text
rejected=value
after=Java
~~~

Nếu setter throws trước khi gán field, Box giữ giá trị trước đó. Đây là nguyên tắc giữ invariant đơn giản.

## 20. Diamond `<>` và type inference

Hai cách thường tương đương về type:

~~~java
Box<String> first = new Box<String>("Java");
Box<String> second = new Box<>("Java");
~~~

Diamond `<>` giúp compiler suy luận type arguments của constructor expression từ ngữ cảnh và arguments.

Nhưng không được nhầm:

~~~java
var box = new Box<>("Java");
~~~

Ở đây target type không phải `Box<String>` đã khai báo, nhưng compiler vẫn có thể infer T từ constructor argument `"Java"`. Trong trường hợp constructor nhận null:

~~~java
// var box = new Box<>(null);
~~~

việc suy luận có thể dẫn đến type quá rộng so với ý định. Ưu tiên đặt declared type rõ:

~~~java
Box<String> box = new Box<>(null);
~~~

nếu null là một trạng thái được contract cho phép.

## 21. Chương trình chạy: diamond và local `var`

Tạo **`DiamondBoxDemo.java`**:

~~~java
public class DiamondBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> declared = new Box<>("Java");
        var inferred = new Box<>(17);

        System.out.println(declared.get());
        System.out.println(inferred.get());

        Integer value = inferred.get();
        System.out.println(value + 1);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 DiamondBoxDemo.java
java DiamondBoxDemo
~~~

Stdout:

~~~text
Java
17
18
~~~

`var inferred = new Box<>(17)` suy luận Box<Integer> theo argument; nó không biến Java thành dynamic typing.

## 22. Autoboxing: vì sao `Box<Integer>` nhận `17`?

Java generic type arguments phải là reference types. Primitive `int` không thể đứng trong `Box<int>`.

~~~java
Box<Integer> number = new Box<>(17);
~~~

`17` là int literal, nhưng autoboxing tạo/converts sang Integer khi cần. Getter có thể unbox:

~~~java
int value = number.get();
~~~

Tuy nhiên, nếu Box<Integer> cho phép null, tự unbox null sẽ ném `NullPointerException`.

### Performance

Dùng wrappers có thể phát sinh allocation/boxing overhead trong một số workload. Không tối ưu bằng phỏng đoán; nếu đang xử lý hàng triệu primitive values, primitive arrays hoặc specialized APIs có thể phù hợp hơn generic Box<Integer>.

## 23. Chương trình chạy: Box<Integer> và unboxing

Tạo **`BoxingBoxDemo.java`**:

~~~java
public class BoxingBoxDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<Integer> number = new Box<>(21);

        int doubled = number.get() * 2;
        System.out.println("doubled=" + doubled);

        Box<Integer> empty = new Box<>(null);
        try {
            int ignored = empty.get();
            System.out.println(ignored);
        } catch (NullPointerException ex) {
            System.out.println("cannot unbox null");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BoxingBoxDemo.java
java BoxingBoxDemo
~~~

Stdout:

~~~text
doubled=42
cannot unbox null
~~~

Box<Integer> không tự bảo vệ null. Nếu null bị cấm, constructor validation giúp tránh lỗi muộn.

## 24. Raw `Box` khác `Box<T>`

`Box raw = new Box("value")` là cách sử dụng raw type, không phải cú pháp rút gọn của `Box<String>`. Raw aliases phá bớt generic compile-time checks khi gọi setter. Code mới nên khai báo đúng type argument hoặc dùng `Box<?>` nếu API chỉ cần đọc unknown type.

## 25. Chương trình chạy: raw alias làm lỗi xuất hiện ở typed getter

Lưu **`RawBoxBoundaryDemo.java`**:

~~~java
public class RawBoxBoundaryDemo {
    static final class Box<T> {
        private T value;
        Box(T value) { this.value = value; }
        void set(T next) { value = next; }
        T get() { return value; }
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    static void legacyWrite(Box<String> typed) {
        Box raw = typed;
        raw.set(17);
    }

    public static void main(String[] args) {
        Box<String> words = new Box<>("Java");
        legacyWrite(words);
        try {
            String value = words.get();
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println("unsafe read rejected");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RawBoxBoundaryDemo.java
java RawBoxBoundaryDemo
~~~

~~~text
unsafe read rejected
~~~

Annotation chỉ cô lập việc **minh họa** unsafe legacy code; nó không phải cách sửa lỗi. Đừng cố thêm raw cast để làm một method compile được khi type arguments không khớp.

## 26. Type erasure không loại bỏ quan hệ kiểu trong source

`Box<String>` và `Box<Integer>` dùng cùng runtime declaration. Unbounded field `T value` có erased field type `Object`, còn typed getter calls có casts phù hợp. Compiler vẫn reject `words.set(17)` nếu chỉ dùng tham chiếu typed `Box<String>` đúng hợp đồng.

## 27. Hai parameterizations có cùng runtime class

~~~java
// Với declaration Box<T> ở trên:
Box<String> text = new Box<>("A");
Box<Integer> count = new Box<>(3);
boolean sameRuntimeClass = text.getClass() == count.getClass();
~~~

Đây là **fragment giải thích**, không phải source độc lập; boolean là true nếu hai đối tượng được tạo từ cùng Box declaration/classloader. Generic signature/reflection/bridge methods được giảng sâu ở phần erasure; trọng tâm ở đây là **quan hệ nhất quán giữa field kiểu T, constructor, setter và getter**, không phải cấu trúc JVM bytecode.

## 28. Không thể viết `new T()`, `T.class` hoặc `new T[]`

Các đoạn sau không hợp lệ với unbounded T:

~~~java
class Box<T> {
    // T create() { return new T(); }    // Lỗi.
    // Class<T> type() { return T.class; } // Lỗi.
    // T[] values = new T[10];            // Lỗi.
}
~~~

Lý do: `T` là type parameter, sau erasure compiler/JVM không có thông tin cần thiết để tạo đúng runtime class như vậy.

### Cách thay thế

1. **Nhận object từ caller** qua `Box(T value)`.
2. **Nhận factory** như `Supplier<? extends T>` nếu phải tạo mới.
3. **Nhận Class<T> type token** nếu API cần inspect/validate runtime type.
4. Dùng collection như `List<T>` thay vì generic array khi phù hợp.

Cũng không được giả định constructor có thể dùng `new T()` chỉ vì T có bound. Bound không cung cấp lời gọi constructor generic tự động.

## 29. Chương trình chạy: factory `Supplier<? extends T>`

Tạo **`SupplierBoxDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

public class SupplierBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        static <U> Box<U> from(Supplier<? extends U> factory) {
            Objects.requireNonNull(factory, "factory");
            return new Box<>(factory.get());
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<StringBuilder> box =
                Box.from(() -> new StringBuilder("Java"));

        System.out.println(box.get().toString());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SupplierBoxDemo.java
java SupplierBoxDemo
~~~

Stdout:

~~~text
Java
~~~

`Supplier` có nhiệm vụ tạo object; Box không cần `new T()`. Do StringBuilder mutable, Box trên chưa là deep immutable dù value field final.

## 30. Class type parameter `T` và static generic method `<U>`

Không hợp lệ:

~~~java
class Box<T> {
    // static Box<T> of(T value) { ... } // Không thể dùng class T trong static context.
}
~~~

Đúng:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
~~~

`<U>` đặt **trước return type** của static method để khai báo một method type parameter hoàn toàn riêng. Đây không phải class-level T.

Caller dùng:

~~~java
Box<String> text = Box.of("Java");
Box<Integer> number = Box.of(17);
~~~

Compiler thường infer `U` từ arguments và target context. Có thể ghi explicit invocation `Box.<String>of("Java")` khi cần.

## 31. Chương trình chạy: static generic factory

Tạo **`StaticFactoryBoxDemo.java`**:

~~~java
public class StaticFactoryBoxDemo {
    static final class Box<T> {
        private final T value;

        private Box(T value) {
            this.value = value;
        }

        static <U> Box<U> of(U value) {
            return new Box<>(value);
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> text = Box.of("Java");
        Box<Integer> count = Box.of(17);

        System.out.println(text.get());
        System.out.println(count.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 StaticFactoryBoxDemo.java
java StaticFactoryBoxDemo
~~~

Stdout:

~~~text
Java
17
~~~

Factory `Box.of` có type parameter của method, không cố tham chiếu class T từ static context.

## 32. Instance generic method có parameter mới `U`

Class có `T` cho stored value. Một method có thể thêm `U` để chuyển kiểu:

~~~java
<U> Box<U> map(java.util.function.Function<? super T, ? extends U> f) {
    return new Box<>(f.apply(value));
}
~~~

- `T` là type của giá trị hiện tại.
- `U` là type của kết quả.
- `Function<? super T, ? extends U>` cho mapper nhận được T và có thể trả subtype của U.
- Return type `Box<U>` là một Box mới.

Bạn không nhất thiết phải dùng wildcards ngay khi mới học; phiên bản `Function<T,U>` cũng minh họa được. Dạng rộng hơn được dùng nhiều trong collection/functional APIs.

## 33. Chương trình chạy: `map` từ `Box<String>` sang `Box<Integer>`

Tạo **`MapBoxDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.Function;

public class MapBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        <U> Box<U> map(Function<? super T, ? extends U> mapper) {
            Objects.requireNonNull(mapper, "mapper");
            return new Box<>(mapper.apply(value));
        }
    }

    public static void main(String[] args) {
        Box<String> text = new Box<>("Java");
        Box<Integer> length = text.map(String::length);

        System.out.println("text=" + text.get());
        System.out.println("length=" + length.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 MapBoxDemo.java
java MapBoxDemo
~~~

Stdout:

~~~text
text=Java
length=4
~~~

`map` biến đổi type argument: từ Box<String> thành Box<Integer>, không gán Integer vào chính một Box<String> cũ.

## 34. Đặt tên trùng `T` cho method type parameter có thể gây nhầm

Xét:

~~~java
class Box<T> {
    // <T> T transform(T input) { return input; }
}
~~~

Một method có thể khai báo type parameter **trùng tên T** và shadow class-level T theo lexical scope rules (khi khai báo hợp lệ), nhưng rất dễ đọc sai: method T không nhất thiết là class T.

**Tránh pattern này**. Dùng `<U>` hoặc tên có nghĩa khác cho method-level parameter:

~~~java
<U> U convert(U value) {
    return value;
}
~~~

Nếu method cần tham chiếu chính class T, không khai báo một method type parameter trùng tên: dùng `T` trực tiếp trong method signature.

## 35. Một generic method và một method sử dụng T là khác nhau

Ví dụ đặt trong `class Box<T>`:

~~~java
T echoStoredType(T value) {
    return value;
}

<U> U echoAnyType(U value) {
    return value;
}
~~~

`echoStoredType` ràng buộc argument theo class parameter T. `echoAnyType` có method type parameter U, có thể nhận loại khác với T.

Nếu `Box<String> box`:
- `box.echoStoredType("A")` hợp lệ; `box.echoStoredType(17)` compile error.
- `box.echoAnyType(17)` hợp lệ, method U được infer là Integer.

### Chương trình chạy

Tạo **`MethodTypeParameterDemo.java`**:

~~~java
public class MethodTypeParameterDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T echoStoredType(T input) {
            return input;
        }

        <U> U echoAnyType(U input) {
            return input;
        }
    }

    public static void main(String[] args) {
        Box<String> box = new Box<>("Java");

        String a = box.echoStoredType("A");
        Integer b = box.echoAnyType(17);

        System.out.println(a);
        System.out.println(b);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 MethodTypeParameterDemo.java
java MethodTypeParameterDemo
~~~

Stdout:

~~~text
A
17
~~~

Method U không thay đổi type argument của Box instance.

## 36. Có thể có nhiều type parameters

Một class có thể dùng `<K,V>` hoặc `<A,B>`:

~~~java
class Pair<A, B> {
    private final A first;
    private final B second;

    Pair(A first, B second) {
        this.first = first;
        this.second = second;
    }

    A first() {
        return first;
    }

    B second() {
        return second;
    }
}
~~~

`Box<T>` dùng một parameter vì nó chỉ cần chứa một loại dữ liệu. Khi model có hai vai trò kiểu khác nhau, đặt hai parameters rõ sẽ hữu ích.

### Đừng phức tạp hóa vô cớ

Không thêm `<T,U,V>` nếu các type parameters không thực sự mang contract. Một type parameter nên xuất hiện nơi caller có lợi từ compile-time relationship giữa fields/parameters/returns.

## 37. Chương trình chạy: Box chứa Pair

Tạo **`PairInBoxDemo.java`**:

~~~java
public class PairInBoxDemo {
    record Pair<A, B>(A first, B second) {}

    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Pair<String, Integer> pair = new Pair<>("Java", 17);
        Box<Pair<String, Integer>> box = new Box<>(pair);

        System.out.println(box.get().first());
        System.out.println(box.get().second());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 PairInBoxDemo.java
java PairInBoxDemo
~~~

Stdout:

~~~text
Java
17
~~~

Nested parameterized type `Box<Pair<String,Integer>>` vẫn được type-check đầy đủ.

## 38. Khi `Box<T>` cần một capability mới: giới hạn `T`

Một Box không bound chỉ biết operations của `Object`. Nếu object phải xử lý số, có thể dùng `class NumericBox<T extends Number>` để gọi `doubleValue()` qua giá trị field T. Bound hạn chế type arguments nhưng không tự kiểm `null`, overflow hoặc precision.

## 39. Chương trình chạy: bounded field kiểu T

Lưu **`NumericBoxBoundDemo.java`**:

~~~java
public class NumericBoxBoundDemo {
    static final class NumericBox<T extends Number> {
        private final T value;

        NumericBox(T value) {
            this.value = java.util.Objects.requireNonNull(value);
        }

        double twice() {
            return value.doubleValue() * 2;
        }
    }

    public static void main(String[] args) {
        NumericBox<Integer> integer = new NumericBox<>(7);
        NumericBox<Double> decimal = new NumericBox<>(2.5);

        System.out.println(integer.twice());
        System.out.println(decimal.twice());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 NumericBoxBoundDemo.java
java NumericBoxBoundDemo
~~~

~~~text
14.0
5.0
~~~

`NumericBox<String>` không hợp lệ vì String không phải Number. Ví dụ dùng `doubleValue()` để thể hiện type bound, **không** phải công thức tính tiền chính xác.

## 40. Một type parameter có thể có nhiều bounds

`<T extends Number & Comparable<T>>` yêu cầu đồng thời năng lực của Number và Comparable<T>; nếu có class bound nó phải đứng trước các interface bounds. Không nên thêm nhiều bounds chỉ để "generic hơn" khi Box thực tế chỉ cần giữ/trả giá trị.

## 41. Comparable có thể là bound độc lập

Với `<T extends Comparable<? super T>>`, một Box có thể gọi `value.compareTo(other)` theo natural ordering contract. Đây là **trường hợp API thật sự cần so sánh**, không phải thuộc tính mặc định của generic Box. Các kiểu intersection bounds, variance của Comparable và F-bounded patterns có phạm vi giải thích chuyên sâu riêng. Ở bài khai báo `Box<T>`, hãy chọn **bounds tối thiểu để thực hiện hành vi**.

## 42. `Box<String>` không phải `Box<Object>`

Java generic parameterized types là **invariant** đối với thông thường:

~~~java
Box<String> strings = new Box<>("Java");
// Box<Object> objects = strings; // Compile error.
~~~

Tuy String extends Object, `Box<String>` không extends `Box<Object>`.

**Vì sao?** Nếu phép gán ấy được cho phép với mutable Box:

~~~java
Box<Object> objects = strings;
objects.set(42);
String text = strings.get();
~~~

Nó phá contract String của original Box. Java ngăn ngay phép gán đầu tiên.

### Không tự cast để vượt qua

Unchecked casts có thể biến lỗi compile-time thành ClassCastException runtime. Hãy điều chỉnh API bằng wildcards nếu mục đích là nhận nhiều Box variants.

## 43. Chương trình chạy: dùng wildcard để đọc nhiều Box

Tạo **`ReadWildcardBoxDemo.java`**:

~~~java
public class ReadWildcardBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static void print(Box<?> box) {
        System.out.println(box.get());
    }

    public static void main(String[] args) {
        print(new Box<>("Java"));
        print(new Box<>(17));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ReadWildcardBoxDemo.java
java ReadWildcardBoxDemo
~~~

Stdout:

~~~text
Java
17
~~~

`Box<?>` đọc được qua `get()` và kết quả assignable to Object. Nó không cho ghi arbitrary non-null value vì compiler không biết captured type.

## 44. `? extends` để đọc subtype values

Method muốn nhận các Box chứa Number subclasses:

~~~java
static double read(Box<? extends Number> box) {
    return box.get().doubleValue();
}
~~~

Nhận được `Box<Integer>` và `Box<Double>`:

~~~java
read(new Box<>(7));
read(new Box<>(2.5));
~~~

Nhưng không được `box.set(10)` tùy ý khi parameter là `Box<? extends Number>`: actual boxed subtype chưa biết và có thể là Double, BigDecimal...

Mnemonic PECS: **Producer Extends**, **Consumer Super**. Với `Box<? extends Number>`, Box là producer của Number values cho method, chủ yếu đọc.

## 45. Chương trình chạy: producer extends

Tạo **`ExtendsWildcardBoxDemo.java`**:

~~~java
public class ExtendsWildcardBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static double read(Box<? extends Number> box) {
        return box.get().doubleValue();
    }

    public static void main(String[] args) {
        System.out.println(read(new Box<>(7)));
        System.out.println(read(new Box<>(2.5)));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ExtendsWildcardBoxDemo.java
java ExtendsWildcardBoxDemo
~~~

Stdout:

~~~text
7.0
2.5
~~~

Upper-bounded wildcard mở read API mà không phải gán `Box<Integer>` vào `Box<Number>`.

## 46. `? super` để ghi kiểu an toàn

Một method nhận `Box<? super Integer>` có thể nhận:
- `Box<Integer>`;
- `Box<Number>`;
- `Box<Object>`.

Vì tất cả storage types là supertype của Integer, method có thể ghi Integer:

~~~java
static void putInt(Box<? super Integer> box) {
    box.set(10);
}
~~~

Tuy nhiên, `box.get()` chỉ được suy luận an toàn về Object chứ không phải Integer, vì actual Box có thể là Box<Object>.

Mnemonic PECS: **Consumer Super** khi Box là nơi nhận values.

## 47. Chương trình chạy: consumer super

Tạo **`SuperWildcardBoxDemo.java`**:

~~~java
public class SuperWildcardBoxDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T next) {
            value = next;
        }
    }

    static void putInt(Box<? super Integer> box) {
        box.set(10);
    }

    public static void main(String[] args) {
        Box<Number> number = new Box<>(0);
        Box<Object> object = new Box<>("old");

        putInt(number);
        putInt(object);

        System.out.println(number.get());
        System.out.println(object.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SuperWildcardBoxDemo.java
java SuperWildcardBoxDemo
~~~

Stdout:

~~~text
10
10
~~~

`Box<? super Integer>` không phải cách biểu diễn “Box<Integer>”; đó là wildcard reference cho một Box có actual type argument thuộc các supertypes được phép.

## 48. Wildcard không thay thế class-level `T`

Nếu một method cần **giữ quan hệ chính xác giữa input và output**, type parameter riêng thường tốt hơn wildcard:

~~~java
static <T> T roundTrip(Box<T> box, T replacement) {
    T old = box.get();
    box.set(replacement);
    return old;
}
~~~

Vì cùng type parameter T xuất hiện ở Box, replacement và return, compiler kiểm tra mối liên hệ đó.

Ngược lại `Box<?>` nói “có một type argument nào đó nhưng không biết cụ thể”, hữu ích để đọc/quan sát chung.

**Hãy chọn:**
- `Box<T>` trong class để ràng buộc stored value và methods.
- `Box<?>` khi không quan tâm type argument.
- `Box<? extends X>` khi đọc values thuộc family X.
- `Box<? super X>` khi ghi values loại X.
- Method `<T>` khi cần tương quan nhiều parameters/return values.

## 49. Chương trình chạy: generic utility dùng cùng `T`

Tạo **`RoundTripBoxDemo.java`**:

~~~java
public class RoundTripBoxDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T next) {
            value = next;
        }
    }

    static <T> T replaceAndReturnOld(Box<T> box, T next) {
        T old = box.get();
        box.set(next);
        return old;
    }

    public static void main(String[] args) {
        Box<String> box = new Box<>("A");

        String old = replaceAndReturnOld(box, "B");

        System.out.println("old=" + old);
        System.out.println("new=" + box.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RoundTripBoxDemo.java
java RoundTripBoxDemo
~~~

Stdout:

~~~text
old=A
new=B
~~~

Generic helper đảm bảo values có cùng T mà không cần unchecked casts.

## 50. Type erasure có thể gây method signature clash

Vì T unbounded erases to Object:

~~~java
class Box<T> {
    // void set(T value) {}
    // void set(Object value) {}
}
~~~

Hai signatures có cùng erasure `set(Object)` nên không được overload như trên. Java compiler báo name clash.

Tương tự không overload chỉ khác type arguments:

~~~java
// void accept(Box<String> box) {}
// void accept(Box<Integer> box) {}
~~~

Cả hai erases thành cùng raw Box parameter signature. Dùng tên methods khác, một generic method hoặc cấu trúc API phù hợp.

**Ghi nhớ:** Generics cung cấp type checks ở compile time, nhưng không tạo overload khác ở JVM descriptor chỉ từ String vs Integer type arguments.

## 51. `instanceof` với generic types

Hợp lệ:

~~~java
Object value = new Box<>("Java");
boolean isBox = value instanceof Box<?>;
~~~

Không hợp lệ để test reified parameterization:

~~~java
// boolean isStringBox = value instanceof Box<String>; // Compile error.
~~~

Vì runtime class không giữ riêng Box<String>/Box<Integer> như class identity khác nhau. Tránh lập logic dựa vào type arguments bị erasure.

Có thể dùng `instanceof Box<?> box` pattern (Java 17) để kiểm tra outer shape và lấy Object từ `box.get()`:

~~~java
if (value instanceof Box<?> box) {
    Object content = box.get();
}
~~~

## 52. Chương trình chạy: `instanceof Box<?>`

Tạo **`InstanceofBoxDemo.java`**:

~~~java
public class InstanceofBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static String describe(Object input) {
        if (input instanceof Box<?> box) {
            return "boxed:" + box.get();
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Box<>("Java")));
        System.out.println(describe(17));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 InstanceofBoxDemo.java
java InstanceofBoxDemo
~~~

Stdout:

~~~text
boxed:Java
other
~~~

Java 17 `instanceof` patterns không khiến erased type arguments trở thành runtime-reifiable.

## 53. Khi cần biết runtime type: truyền `Class<T>`

Một generic Box có thể nhận runtime class token:

~~~java
class TypedBox<T> {
    private final Class<T> type;
    private final T value;

    TypedBox(Class<T> type, T value) {
        this.type = type;
        this.value = type.cast(value);
    }
}
~~~

`Class<T>` giúp thực hiện runtime checks khi data đến từ untyped boundary, nhưng:
- `Class<List<String>>` không thể diễn tả đầy đủ nested parameterized arguments bằng một simple reified Class object;
- vẫn cần null policy;
- type token chỉ làm nhiệm vụ mà API đã thiết kế, không khôi phục Java generics bị erased một cách thần kỳ.

### Chương trình chạy

Tạo **`ClassTokenBoxDemo.java`**:

~~~java
import java.util.Objects;

public class ClassTokenBoxDemo {
    static final class TypedBox<T> {
        private final Class<T> type;
        private final T value;

        TypedBox(Class<T> type, Object value) {
            this.type = Objects.requireNonNull(type);
            this.value = type.cast(value);
        }

        T get() {
            return value;
        }

        String typeName() {
            return type.getSimpleName();
        }
    }

    public static void main(String[] args) {
        TypedBox<String> text =
                new TypedBox<>(String.class, "Java");

        System.out.println(text.typeName());
        System.out.println(text.get());

        try {
            new TypedBox<>(String.class, 17);
        } catch (ClassCastException ex) {
            System.out.println("wrong runtime type");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ClassTokenBoxDemo.java
java ClassTokenBoxDemo
~~~

Stdout:

~~~text
String
Java
wrong runtime type
~~~

Class token là một giải pháp khi nhận Object từ reflection/parsing/boundary; với code generic bình thường, compile-time typing đã đủ.

## 54. Box có bảo đảm dữ liệu bên trong bất biến không?

Không. Xét:

~~~java
Box<java.util.List<String>> box = new Box<>(sourceList);
~~~

Nếu Box giữ direct reference, caller sửa sourceList thì `box.get()` cũng thấy change. Thêm `final` vào Box field chỉ chặn reassign reference, không snapshot List structure.

### Ba hướng thiết kế

1. **Document shared ownership:** Box giữ cùng reference, người sử dụng phải hiểu mutability.
2. **Immutable element API:** Box chỉ chứa immutable values như String, Integer hoặc immutable records.
3. **Explicit copier/factory:** nhận `UnaryOperator<T>`/copy function hoặc thiết kế kiểu wrapper riêng để snapshot mutable input.

Không thể viết một **generic deepCopy(T)** chính xác cho mọi arbitrary T chỉ nhờ type parameter, vì Java không biết cloning/copy contract của tất cả objects.

## 55. Chương trình chạy: generic Box và aliasing

Tạo **`AliasingBoxDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AliasingBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Box<List<String>> box = new Box<>(source);

        source.add("B");
        System.out.println(box.get());

        box.get().add("C");
        System.out.println(source);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 AliasingBoxDemo.java
java AliasingBoxDemo
~~~

Stdout:

~~~text
[A, B]
[A, B, C]
~~~

Đây là ordinary reference aliasing, không phải lỗi của generic type system. Nếu API muốn snapshot, hãy chuyển sang List.copyOf ở appropriate boundary hoặc một domain-specific wrapper.

## 56. Defensive copying cần type-specific policy

Ví dụ specialized Box cho List:

~~~java
final class ListBox<E> {
    private final java.util.List<E> value;

    ListBox(java.util.List<? extends E> input) {
        value = java.util.List.copyOf(input);
    }

    java.util.List<E> get() {
        return value;
    }
}
~~~

`List.copyOf` bảo vệ **list structure** khỏi mutations từ caller và trả unmodifiable list, nhưng **không deep-copy mutable elements**. Ngoài ra, List.copyOf không chấp nhận null elements.

Không nên ép core `Box<T>` gọi `List.copyOf` cho mọi T: không phải T nào cũng là List, và copy/immutability semantics phụ thuộc domain.

Nếu Box chứa `byte[]`, có thể tạo `BytesBox` dùng clone constructor/getter và content equality phù hợp.

## 57. Chương trình chạy: specialized ListBox<E>

Tạo **`ListBoxDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListBoxDemo {
    static final class ListBox<E> {
        private final List<E> values;

        ListBox(List<? extends E> input) {
            values = List.copyOf(input);
        }

        List<E> get() {
            return values;
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        ListBox<String> box = new ListBox<>(source);

        source.add("B");
        System.out.println("source=" + source);
        System.out.println("box=" + box.get());

        try {
            box.get().add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ListBoxDemo.java
java ListBoxDemo
~~~

Stdout:

~~~text
source=[A, B]
box=[A]
unmodifiable
~~~

Generic element parameter E và `List.copyOf` cùng bảo vệ structure, nhưng nếu E mutable, element references vẫn có thể thay đổi.

## 58. `equals`/`hashCode` cho generic Box

Nếu Box là một **value holder**, có thể implement:

~~~java
@Override
public boolean equals(Object other) {
    return other instanceof Box<?> box &&
            java.util.Objects.equals(value, box.value);
}

@Override
public int hashCode() {
    return java.util.Objects.hashCode(value);
}
~~~

Điều này so sánh `value` theo equals contract của contained type. Với mutable values, equality/hash có thể đổi sau mutation. Với arrays, Object.equals dùng array identity chứ không element content.

Nếu Box là mutable reference holder có distinct identity, override value equality có thể **không phù hợp**. Quyết định dựa trên domain semantics, không chỉ syntax.

## 59. Chương trình chạy: immutable value Box với equality

Tạo **`ValueBoxDemo.java`**:

~~~java
import java.util.Objects;

public class ValueBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Box<?> box &&
                    Objects.equals(value, box.value);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(value);
        }

        @Override
        public String toString() {
            return "Box[" + value + "]";
        }
    }

    public static void main(String[] args) {
        Box<String> first = new Box<>("Java");
        Box<String> second = new Box<>("Java");

        System.out.println("equal=" + first.equals(second));
        System.out.println("hash equal=" +
                (first.hashCode() == second.hashCode()));
        System.out.println(first);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ValueBoxDemo.java
java ValueBoxDemo
~~~

Stdout:

~~~text
equal=true
hash equal=true
Box[Java]
~~~

Nếu muốn equality phân biệt parameterized types dù stored values giống, type erasure khiến việc thiết kế phức tạp hơn. Ví dụ này định nghĩa equality theo contained value, không hứa runtime generic type argument identity.

## 60. Box generic và record generic

Java 17 cho phép generic record:

~~~java
record Box<T>(T value) {}
~~~

Code dùng:

~~~java
Box<String> box = new Box<>("Java");
String text = box.value();
~~~

Record tự tạo accessor `value()`, canonical constructor, equals/hashCode/toString dựa trên component.

### Khi nào dùng record?

- Cần immutable-by-field data carrier.
- Stored value là logical state.
- Component-based equality hợp lý.
- Không cần setter hoặc hidden instance state.
- Defensive-copy policy có thể nằm trong canonical/compact constructor.

### Khi nào dùng class?

- Cần setter/mutable state.
- Cần hidden caches/fields hoặc extends base class.
- Cần API không lộ representation là một component.
- Cần constructor/behavior/lifecycle khác value carrier.

## 61. Chương trình chạy: generic record Box<T>

Tạo **`GenericRecordBoxDemo.java`**:

~~~java
public class GenericRecordBoxDemo {
    record Box<T>(T value) {}

    public static void main(String[] args) {
        Box<String> a = new Box<>("Java");
        Box<String> b = new Box<>("Java");

        System.out.println(a.value());
        System.out.println(a.equals(b));
        System.out.println(a);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericRecordBoxDemo.java
java GenericRecordBoxDemo
~~~

Stdout:

~~~text
Java
true
Box[value=Java]
~~~

Record<T> ở ví dụ là generic reference type, không có mutable setter. Với T mutable, final component reference không tạo deep immutability.

## 62. Inheritance với generic Box

Một subclass có thể **giữ nguyên type parameter**:

~~~java
class NamedBox<T> extends Box<T> {
    private final String name;

    NamedBox(String name, T value) {
        super(value);
        this.name = name;
    }
}
~~~

Hoặc **chốt type argument**:

~~~java
class StringBox extends Box<String> {
    StringBox(String value) {
        super(value);
    }
}
~~~

Hai snippets trên yêu cầu Box base class **không final** và có accessible constructor. Nếu `Box` là final, không thể subclass dù generic type parameters ra sao.

### Quy tắc

- `NamedBox<T>` giữ generic extensibility.
- `StringBox` là một class cụ thể cố định T=String.
- Không được tự cast các parameterizations sai để “kế thừa” từ Box<Integer> sang Box<String>.

## 63. Chương trình chạy: subclass giữ T và chốt T

Tạo **`GenericSubclassBoxDemo.java`**:

~~~java
public class GenericSubclassBoxDemo {
    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static final class NamedBox<T> extends Box<T> {
        private final String name;

        NamedBox(String name, T value) {
            super(value);
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    static final class StringBox extends Box<String> {
        StringBox(String text) {
            super(text);
        }
    }

    public static void main(String[] args) {
        NamedBox<Integer> number = new NamedBox<>("count", 7);
        StringBox word = new StringBox("Java");

        System.out.println(number.name() + "=" + number.get());
        System.out.println(word.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericSubclassBoxDemo.java
java GenericSubclassBoxDemo
~~~

Stdout:

~~~text
count=7
Java
~~~

Subclass declaration quyết định liệu type parameter T còn do caller cung cấp hay bị chốt thành String.

## 64. Interface generic: `Holder<T>`

Một interface có thể định nghĩa contract:

~~~java
interface Holder<T> {
    T get();
    void set(T value);
}
~~~

Box implement:

~~~java
class Box<T> implements Holder<T> {
    private T value;

    public T get() {
        return value;
    }

    public void set(T value) {
        this.value = value;
    }
}
~~~

Vì methods của interface là public, implementations cũng phải public, không được giảm accessibility.

### Lợi ích

Client có thể viết algorithms nhận `Holder<T>` mà không phụ thuộc cụ thể Box implementation. Generic interface parameter T duy trì compile-time type relationship.

## 65. Chương trình chạy: Box implements Holder<T>

Tạo **`HolderInterfaceDemo.java`**:

~~~java
public class HolderInterfaceDemo {
    interface Holder<T> {
        T get();
        void set(T value);
    }

    static final class Box<T> implements Holder<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        @Override
        public T get() {
            return value;
        }

        @Override
        public void set(T next) {
            value = next;
        }
    }

    static <T> void replace(Holder<T> holder, T next) {
        holder.set(next);
    }

    public static void main(String[] args) {
        Holder<String> holder = new Box<>("A");

        replace(holder, "B");
        System.out.println(holder.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 HolderInterfaceDemo.java
java HolderInterfaceDemo
~~~

Stdout:

~~~text
B
~~~

`Holder<String>` có cùng type safety với Box<String>. API có thể thay Box bằng implementation khác mà không đổi contract.

## 66. Generics và static nested class

Một static nested class **không** sử dụng type parameter T của outer generic class trực tiếp:

~~~java
class Box<T> {
    static class Metadata {
        // T value; // Không hợp lệ: static nested context.
    }
}
~~~

Nhưng static nested class có thể khai báo type parameter riêng:

~~~java
class Box<T> {
    static class Metadata<U> {
        U value;
    }
}
~~~

Một ordinary non-static inner class gắn với outer instance thì có thể dùng enclosing type parameter T theo scope rules.

Không nên mở rộng Box thành một nested hierarchy phức tạp nếu chỉ cần giữ một field; nhưng hiểu static boundary giúp tránh các compile errors khó hiểu.

## 67. Reflection của `T` khác runtime value type

`Box<String>` và `Box<Integer>` chia sẻ runtime class Box; `getClass()` không tự nói parameter String hay Integer.

Một class declaration có thể mang generic signature metadata cho **type parameter declarations**, nhưng một ordinary Box instance không tự có runtime Class<String> attached chỉ vì được declared là Box<String>.

Nếu framework phải deserialize JSON vào `Box<List<User>>`, nó thường cần generic type descriptor (ví dụ `Type`, `ParameterizedType` hoặc library-specific type token) thay vì chỉ `Box.class`.

Đây là một boundary concern; với core Box<T> trong type-safe Java source, không cần reflection để get/set values.

## 68. Exception policy và invariants

Box<T> có thể là reusable container thuần túy, không biết domain của T. Vì vậy chỉ enforce những invariants **Box thật sự sở hữu**:
- non-null value nếu contract cấm null;
- immutable container nếu mục đích value holder;
- thread-safety nếu API hứa;
- lifecycle state nếu có ownership.

Các rules như “String không blank” hoặc “Integer phải dương” **không thể suy ra từ T một cách chung chung**. Muốn validate theo domain có thể:
- dùng factory method nhận `Predicate<? super T>`;
- nhận validation strategy trong constructor;
- dùng một specialized class `PositiveIntegerBox`;
- validate tại boundary trước khi tạo Box.

## 69. Chương trình chạy: validator được tiêm vào Box

Tạo **`ValidatedBoxDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.Predicate;

public class ValidatedBoxDemo {
    static final class Box<T> {
        private T value;
        private final Predicate<? super T> validator;

        Box(T initial, Predicate<? super T> validator) {
            this.validator = Objects.requireNonNull(
                    validator, "validator");
            set(initial);
        }

        void set(T candidate) {
            if (!validator.test(candidate)) {
                throw new IllegalArgumentException("invalid value");
            }
            value = candidate;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> names = new Box<>(
                "Mai", text -> text != null && !text.isBlank());

        names.set("An");
        System.out.println(names.get());

        try {
            names.set(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
        System.out.println(names.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ValidatedBoxDemo.java
java ValidatedBoxDemo
~~~

Stdout:

~~~text
An
rejected=invalid value
An
~~~

Generic container chỉ biết gọi supplied Predicate; domain quyết định thế nào là valid String. Setter không làm thay đổi value khi validation thất bại.

## 70. Thread safety của mutable Box

~~~java
class Box<T> {
    private T value;

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
~~~

Đây **không phải một concurrent container an toàn tự động**. Nếu nhiều threads đọc/ghi cùng instance, phải xác định visibility/ordering/synchronization.

Một `volatile T value` có thể cung cấp visibility/atomic reference reads-writes cho một field; nhưng các compound operations như check-then-set hoặc increment vẫn cần synchronized/atomic APIs.

Generic Box không thay thế `AtomicReference<T>` cho multi-threaded shared reference updates. Nếu cần atomic compare-and-set, `AtomicReference<T>` thường thích hợp hơn tự viết lại concurrency primitives.

## 71. Chương trình chạy: AtomicReference<T> như một thread-aware Box

Tạo **`AtomicReferenceDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicReferenceDemo {
    public static void main(String[] args) {
        AtomicReference<String> box =
                new AtomicReference<>("A");

        String old = box.getAndSet("B");

        System.out.println("old=" + old);
        System.out.println("now=" + box.get());
        System.out.println("swap=" +
                box.compareAndSet("B", "C"));
        System.out.println("final=" + box.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 AtomicReferenceDemo.java
java AtomicReferenceDemo
~~~

Stdout:

~~~text
old=A
now=B
swap=true
final=C
~~~

AtomicReference<T> là JDK generic class đã có contract concurrency rõ. Chỉ tạo custom Box<T> nếu API cần behavior khác.

## 72. Generic Box và `Optional<T>`

Cả Box<T> và Optional<T> có thể liên quan đến việc chứa một value, nhưng mục tiêu khác nhau:

- `Box<T>` là container bạn tự thiết kế, có thể mutable, có thể allow null.
- `Optional<T>` đại diện cho có/không có value theo JDK API, với methods như `isPresent`, `orElse`, `map`.
- Không cần tự viết Box nếu thực sự chỉ cần diễn đạt **return value có thể vắng mặt**.
- Không dùng Optional làm arbitrary mutable field holder chỉ vì generic.

Ví dụ method tìm dữ liệu có thể trả `Optional<User>`; còn UI editor cần mutable T reference có thể dùng StateHolder<T> hoặc một class domain khác.

## 73. Chương trình chạy: Box tự map so với Optional.map

Tạo **`BoxOptionalDemo.java`**:

~~~java
import java.util.Optional;

public class BoxOptionalDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> box = new Box<>("Java");
        Optional<String> present = Optional.of("Java");
        Optional<String> absent = Optional.empty();

        System.out.println("box=" + box.get());
        System.out.println("present length=" +
                present.map(String::length).orElse(-1));
        System.out.println("absent length=" +
                absent.map(String::length).orElse(-1));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BoxOptionalDemo.java
java BoxOptionalDemo
~~~

Stdout:

~~~text
box=Java
present length=4
absent length=-1
~~~

Optional có semantic “absence” rõ ràng. Box chỉ có ý nghĩa đó nếu API của chính bạn định nghĩa.

## 74. Generic API design: đừng lạm dụng `Object`

Không nên viết generic class nhưng đánh mất lợi ích khi public methods trả Object:

~~~java
class Box<T> {
    private T value;

    Object get() {
        return value;
    }
}
~~~

Nếu goal là preserve type, trả `T`:

~~~java
T get() {
    return value;
}
~~~

Tương tự, setter nên nhận `T` chứ không nhận Object rồi unchecked cast về T. Nếu API thật sự nhận arbitrary Object, cân nhắc bỏ generic hoặc ghi một method chuyển đổi được kiểm tra rõ.

## 75. Type parameter naming convention

Các tên thường gặp:

| Tên | Ý nghĩa thông thường |
| --- | --- |
| `T` | Type |
| `E` | Element |
| `K` | Key |
| `V` | Value |
| `R` | Result |
| `U`, `S` | Một parameter khác khi T đã được dùng |

`class Box<T>` là convention phổ biến cho một object container. Nếu class có nhiều type parameters, tên rõ giúp hiểu return/argument relationships.

### Đừng đặt `T` thành tên biến logic

~~~java
class Box<T> {
    private T value;
}
~~~

Type parameter `T` và field `value` có trách nhiệm khác nhau. Đặt field `t` vẫn hợp lệ nhưng kém truyền đạt ý nghĩa hơn.

## 76. Common compiler errors của `Box<T>`

| Sai lầm | Vì sao | Cách sửa |
| --- | --- | --- |
| `Box<int>` | Primitive không là reference type argument | `Box<Integer>` |
| `Box<String> b = new Box<Integer>(1)` | Type arguments không tương thích | Đồng nhất type |
| `Box<Object> b = new Box<String>("x")` | Generics invariant | `Box<?>` hoặc wildcard API |
| `static T value` | Class T không dùng ở static context | Instance field hoặc static `<U>` factory |
| `new T()` | T bị erased, không construct trực tiếp | Supplier/factory |
| `T.class` | Type parameter không reified Class literal | `Class<T>` token |
| `new T[10]` | Generic array creation restriction | List<T>/array factory |
| `value.someMethod()` với unbounded T | Compiler không biết method ngoài Object | Add bound/interface |
| `instanceof Box<String>` | Non-reifiable parameterization | `instanceof Box<?>` |
| Overload `set(T)` và `set(Object)` | Same erased signature | Đổi API/method names |
| Overload `accept(Box<String>)` / `accept(Box<Integer>)` | Same erased signature | Generic method/unique names |
| Raw `Box` | Mất compile-time safety | Parameterized Box |
| `get()` trả Object trong type-safe Box | Cần casts | Return T |
| Gán null vào unboxing target | Runtime NullPointerException | Null policy |
| Giữ mutable List trong final T field | Aliasing | Ownership/copying |
| Đặt method `<T>` vô ý | Shadow class T | Dùng U hoặc class T đúng |
| Override interface get() không public | Access giảm | Public method |
| Tự viết thread-safe Box bằng plain field | Visibility/races | AtomicReference/locks |

## 77. Bài tập 1 — Tự viết `Box<T>`

Yêu cầu: private field T, constructor nhận T, `get()` trả T, `set(T)` thay value.

**Đáp án:**

~~~java
class Box<T> {
    private T value;

    Box(T initial) {
        this.value = initial;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
~~~

Dùng `Box<String>` và `Box<Integer>` để kiểm tra compile-time relationship.

## 78. Bài tập 2 — Dự đoán kết quả

~~~java
Box<String> names = new Box<>("Mai");
names.set("An");
String result = names.get();
~~~

**Đáp án:** `result` là `"An"`. Setter thay field value, getter trả field mới. Nếu thêm `names.set(123)` sẽ compile error.

## 79. Bài tập 3 — Sửa sai

~~~java
// Box<int> count = new Box<>(7);
~~~

**Đáp án:** Dùng `Box<Integer> count = new Box<>(7);` vì type argument phải là reference type. Autoboxing xử lý int literal.

## 80. Bài tập 4 — Static field T

~~~java
class Box<T> {
    // static T cache; // Sai.
}
~~~

**Đáp án:** Không dùng class-level T trực tiếp từ static context. Nếu cache là per-instance, khai báo `private T cache;`. Nếu static method cần type param riêng, khai báo `static <U> ...`.

## 81. Bài tập 5 — Generic method vs class method

~~~java
class Box<T> {
    T echo(T x) { return x; }
    <U> U identity(U x) { return x; }
}
~~~

Với `Box<String> box`, `box.echo(10)` và `box.identity(10)` ra sao?

**Đáp án:** `box.echo(10)` compile error do T=String; `box.identity(10)` hợp lệ với method U=Integer.

## 82. Bài tập 6 — Type erasure

`Box<String>` và `Box<Integer>` có runtime class khác nhau không?

**Đáp án:** Không nếu được tạo từ cùng class Box declaration/class-loader context; `getClass()` thường trả cùng Class object. Type arguments vẫn được compiler kiểm tra.

## 83. Bài tập 7 — `new T()`

Một method muốn tạo object mới kiểu T trong Box. Vì sao `new T()` không hợp lệ?

**Đáp án:** T là type parameter bị erased; Java không biết constructor/runtime type tương ứng. Nhận `Supplier<? extends T>` hoặc một factory/type token strategy phù hợp.

## 84. Bài tập 8 — Invariance

Vì sao không thể gán `Box<String>` vào `Box<Object>` dù String extends Object?

**Đáp án:** Nếu được, code qua Box<Object> có thể set Integer làm Box<String> chứa sai kiểu. Java generics invariant ngăn hành vi đó.

## 85. Bài tập 9 — Producer

Method chỉ đọc giá trị Number từ Box<Integer> hoặc Box<Double>. Signature?

**Đáp án:**

~~~java
static double read(Box<? extends Number> box) {
    return box.get().doubleValue();
}
~~~

`? extends Number` mở API cho producer values. Không tự set Integer khi type argument subtype không biết.

## 86. Bài tập 10 — Consumer

Method muốn set Integer vào Box<Integer>, Box<Number> hoặc Box<Object>. Signature?

**Đáp án:**

~~~java
static void put(Box<? super Integer> box) {
    box.set(42);
}
~~~

`? super Integer` bảo đảm các storage target types có thể nhận Integer.

## 87. Bài tập 11 — Null policy

Một Box<String> non-null cho phép constructor "A", setter "B" nhưng từ chối null. Setter nên viết thế nào?

**Đáp án:**

~~~java
void set(T next) {
    value = java.util.Objects.requireNonNull(next, "value");
}
~~~

Nhớ validate ở constructor nữa. Java generics tự nó không loại null.

## 88. Bài tập 12 — Mutable component

`Box<List<String>>` có private final List reference nhưng caller giữ mutable List và thay đổi nó.

**Đáp án:** Box vẫn thấy mutation nếu dùng shared reference. `final` chặn reassign field, không chặn mutate List object. Chọn ownership/defensive-copy policy rõ.

## 89. Bài tập 13 — `map` đổi type

`Box<String> text = new Box<>("Java")`, muốn tạo `Box<Integer>` là độ dài text.

**Đáp án gợi ý:**

~~~java
Box<Integer> length = text.map(String::length);
~~~

Với method:

~~~java
<U> Box<U> map(java.util.function.Function<? super T, ? extends U> f) {
    return new Box<>(f.apply(value));
}
~~~

Đây là snippet trong body Box<T>. `U` là method type parameter, khác class T.

## 90. Bài tập 14 — Primitive performance

Một chương trình xử lý hàng triệu int values dùng `List<Box<Integer>>`. Có cần đổi chỉ vì “generics chậm” không?

**Đáp án:** Không quyết định bằng khẩu hiệu. Hãy profile. Boxing, allocations, locality có thể có chi phí; nếu workload thật sự performance-critical, xét primitive arrays/specialized structures/algorithms.

## 91. Bài tập 15 — Raw type

Một `Box<String>` được gán vào raw Box rồi raw.set(42). Sau đó get String có thể xảy ra gì?

**Đáp án:** Compiler cảnh báo unchecked call tại raw boundary; việc lấy String có thể ném ClassCastException runtime. Tránh raw types để giữ type safety.

## 92. Bài tập 16 — Interface generic

`interface Holder<T> { T get(); void set(T x); }`. `Box<T> implements Holder<T>` có phải implement methods public không?

**Đáp án:** Có. Interface abstract methods public, implementation không thể giảm access. Dùng `@Override public T get()` và `@Override public void set(T x)`.

## 93. Quy trình thiết kế Box<T> an toàn

**Bước 1 — Xác định purpose.** Holder mutable, immutable value, optional state hay domain wrapper?

**Bước 2 — Khai báo type parameter.** `class Box<T>` và áp dụng T nhất quán cho fields/constructor/getter/setter.

**Bước 3 — Đặt visibility.** Private field; public/package API có chủ đích. Tránh public mutable field.

**Bước 4 — Chọn null policy.** Cho phép null hay reject? Thực thi ở constructor và setter.

**Bước 5 — Chọn mutation policy.** Setter thay field hay `withValue` trả Box mới?

**Bước 6 — Cân nhắc generics factory.** Static `<U> Box<U> of(U)`, không dùng class T trong static method.

**Bước 7 — Chỉ thêm bounds khi cần.** Muốn `doubleValue()` thì `T extends Number`; không buộc mọi Box phải extends Number.

**Bước 8 — Chọn API khi nhận family types.** `Box<?>`, `? extends`, `? super` hoặc method `<T>` đúng quan hệ.

**Bước 9 — Tránh raw types và unchecked casts.** Giữ compiler type checks từ caller đến storage.

**Bước 10 — Xác định ownership.** T có thể là mutable object; Box có copy hay share? Document rõ.

**Bước 11 — Xác định equality/hash policy.** Mutable holder thường không cần value equality; immutable holder có thể cần.

**Bước 12 — Review concurrency.** Nếu shared updates, dùng synchronization hoặc AtomicReference<T> theo contract.

**Bước 13 — Test compile-time errors và runtime behavior.** Getter/Setter, replace, null, map, erasure/rawtypes restrictions.

## 94. Checklist cuối bài

- [ ] Tôi viết đúng `class Box<T>`.
- [ ] Tôi biết T là type parameter, String là type argument.
- [ ] Tôi khai báo field `private T value`.
- [ ] Tôi viết constructor `Box(T value)`.
- [ ] Tôi viết getter `T get()`.
- [ ] Tôi viết setter `void set(T next)`.
- [ ] Tôi viết được `T replace(T next)`.
- [ ] Tôi biết methods không dùng T cũng hợp lệ.
- [ ] Tôi biết class type parameter scope không áp dụng trực tiếp cho static members.
- [ ] Tôi viết được `static <U> Box<U> of(U)`.
- [ ] Tôi phân biệt class T và method U.
- [ ] Tôi không cố viết `new T()` hoặc `T.class`.
- [ ] Tôi hiểu `Box<String>` và `Box<Integer>` cùng runtime Box class sau erasure.
- [ ] Tôi tránh raw Box và unchecked operations.
- [ ] Tôi biết `Box<int>` sai, `Box<Integer>` đúng.
- [ ] Tôi hiểu boxing/unboxing và null runtime hazard.
- [ ] Tôi hiểu diamond `new Box<>(value)`.
- [ ] Tôi biết generic types invariant.
- [ ] Tôi dùng `Box<?>` khi chỉ cần đọc chung.
- [ ] Tôi dùng `? extends Number` khi đọc Number-family values.
- [ ] Tôi dùng `? super Integer` khi ghi Integer values.
- [ ] Tôi biết type bound `T extends Number` cho phép Number methods.
- [ ] Tôi không giả định generic T hỗ trợ phép +.
- [ ] Tôi biết generic type safety không bảo đảm domain validity.
- [ ] Tôi có null validation nếu contract yêu cầu.
- [ ] Tôi không nhầm final T reference với deep immutable value.
- [ ] Tôi xét defensive-copy đúng với actual T type.
- [ ] Tôi có policy rõ cho equals/hashCode của Box.
- [ ] Tôi biết generic record `record Box<T>(T value)` là một alternative immutable-by-field.
- [ ] Tôi biết generic class có thể implement interface `Holder<T>`.
- [ ] Tôi hiểu subclass có thể giữ T hoặc chốt String.
- [ ] Tôi không đoán thread safety từ generics.
- [ ] Tôi có thể so sánh Box<T> với AtomicReference<T>/Optional<T>.
- [ ] Tôi biết compile-time errors trong bài và dự đoán stdout của các chương trình.

**Kết luận:** `class Box<T>` là ví dụ nền tảng nhất của một generic class Java. **Một type parameter T duy trì quan hệ thống nhất giữa stored field, constructor input, getter return và setter input**, giúp compiler phát hiện sai kiểu trước khi chương trình chạy. Hãy giữ `T` trong đúng instance context, dùng static generic method `<U>` khi cần factory, tránh raw types/unchecked casts, và hiểu type erasure không làm mất lợi ích compile-time type safety. Cuối cùng, chọn null/mutation/ownership/equality/concurrency policy phù hợp: **generics kiểm tra kiểu dữ liệu, không tự kiểm soát chất lượng, tính bất biến hay an toàn luồng của dữ liệu bên trong**.

# Giới hạn tạo `new T()`, mảng generic và kiểm tra kiểu tại thời gian chạy — Java 17+

Generic type parameter như `T` giúp trình biên dịch kiểm tra kiểu, nhưng **không hoạt động như một lớp cụ thể có thể khởi tạo hay kiểm tra đầy đủ tại runtime**. Trong Java 17, generics chủ yếu sử dụng **type erasure**; vì vậy ba nhóm giới hạn có liên quan chặt chẽ:

1. Không thể trực tiếp viết `new T()`, `T.class` hoặc `new T[n]`.
2. Không thể tạo phần lớn mảng có **non-reifiable component type**, ví dụ `new List<String>[10]`.
3. Không thể yêu cầu runtime kiểm tra chính xác type argument bị xóa, ví dụ `obj instanceof List<String>` khi `obj` có kiểu Object.

Ví dụ tối thiểu cho một generic class:

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    // T value2 = new T();           // Lỗi biên dịch.
    // T[] values = new T[10];       // Lỗi biên dịch.
    // boolean test(Object x) {
    //     return x instanceof T;    // Lỗi biên dịch.
    // }
}
~~~

Tuy nhiên, Java **có các cách thay thế type-safe**: truyền một giá trị hoặc factory `Supplier<? extends T>`, truyền `Class<T>` để tạo object/mảng bằng reflection khi phù hợp, truyền array factory `IntFunction<T[]>`, hoặc dùng `List<T>` và các collection APIs thay vì generic arrays.

Đây là README kiến thức độc lập thuộc **Java Core — Class & Object / Lớp generic**, tập trung vào đề **“Giới hạn tạo new T(), mảng generic và kiểm tra kiểu tại thời gian chạy”**. Các chương trình đầy đủ sử dụng **Java 17+**, có filename, lệnh `javac --release 17`, `java` và stdout dự kiến. Mã cố ý sai được comment và phân tích riêng, không lẫn với ví dụ runnable.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao `new T()` không hợp lệ dù `T` được bound bởi một class.
- Phân biệt **compile-time type parameter** với **runtime class identity**.
- Hiểu **type erasure** và erasure của `T` không bound hoặc bounded.
- Thiết kế `Supplier<? extends T>`, `Factory<T>` và `Class<T>` để tạo objects.
- Hiểu giới hạn constructor public/no-argument và checked exceptions của reflection.
- Phân biệt `T.class` với `Class<T>` token có thể truyền từ caller.
- Hiểu vì sao không thể tạo `new T[n]` hoặc `new List<String>[n]`.
- Phân biệt **reifiable** và **non-reifiable** types.
- Nhận biết `String[]`, `List<?>[]`, `List<String>[]` khác nhau như thế nào.
- Hiểu **array covariance** và runtime `ArrayStoreException`.
- Hiểu **generic invariance** và giới hạn type checks sau erasure.
- Xây `T[]` bằng array factory `IntFunction<T[]>` khi thật sự cần array đúng runtime component type.
- Biết dùng `Array.newInstance(Class<T>, size)`, và giới hạn bảo đảm kiểu của phương pháp này.
- Hiểu vì sao `Object[]` cast sang `T[]` dễ gây vấn đề.
- Nhận diện **heap pollution**, raw types và unchecked warnings.
- Nhận diện rủi ro của generic varargs và dùng `@SafeVarargs` đúng ngữ cảnh.
- Sử dụng `List<T>` để tránh nhiều vấn đề của generic arrays.
- Biết tại sao `instanceof T` và `instanceof List<String>` không hợp lệ trong trường hợp cần runtime test non-reifiable type.
- Dùng `instanceof List<?>`, `Class.isInstance` và `Class.cast` đúng mục đích.
- Hiểu type token đơn giản `Class<T>` không thể mô tả đầy đủ `List<String>`.
- Phân biệt `Type`, `ParameterizedType` và các thư viện type reference.
- Dùng bounds/wildcards mà không suy ra sai khả năng kiểm tra runtime.
- Tránh truyền các assertions không đúng vào production bằng cast/suppress warnings.
- Viết tests minh họa lỗi compile time, `ClassCastException` và `ArrayStoreException`.
- Thiết kế API generic đúng theo yêu cầu tạo object, chứa collections, kiểm tra dữ liệu và metadata.

## 2. Gốc rễ: compile-time generics khác runtime representation

Giả sử:

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Ở nơi sử dụng:

~~~java
Box<String> text = new Box<>("Java");
String s = text.get();
~~~

Trình biên dịch dựa vào `Box<String>` để kiểm tra `get()` trả String ở source-level. Nhưng runtime thường không có riêng một lớp `Box<String>` khác lớp `Box<Integer>`. Hai instantiations dùng **cùng class declaration** `Box`.

Với `T` **không có bound**, erasure của T là Object. Ở bytecode-level, những chỗ dùng T có thể được biểu diễn bằng Object; compiler chèn casts khi cần bảo toàn hành vi của typed callers.

Với `T extends Number`, erasure của T là bound thích hợp, thường là Number. Erasure **không** có nghĩa Java không kiểm tra kiểu; ngược lại, compiler thực hiện rất nhiều kiểm tra trước khi chạy.

## 3. Chương trình chạy: `Box<String>` và `Box<Integer>` cùng Class object

Tạo **`ErasureClassDemo.java`**:

~~~java
public class ErasureClassDemo {
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
        Box<String> first = new Box<>("Java");
        Box<Integer> second = new Box<>(17);

        System.out.println("same class=" +
                (first.getClass() == second.getClass()));
        System.out.println("text=" + first.get());
        System.out.println("number=" + second.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ErasureClassDemo.java
java ErasureClassDemo
~~~

Stdout:

~~~text
same class=true
text=Java
number=17
~~~

**Kết luận:** Type arguments String và Integer mang ý nghĩa lớn tại compile time, nhưng chúng không tạo ra hai runtime Class objects độc lập.

## 4. Vì sao `new T()` là lỗi biên dịch?

Bạn có thể viết:

~~~java
class Box<T> {
    // T create() {
    //     return new T(); // Không hợp lệ.
    // }
}
~~~

`T` là một **type variable**, không phải tên một concrete class mà compiler có thể phát sinh bytecode gọi constructor phù hợp.

Các vấn đề gồm:

- Runtime erasure không xác định class thực của T từ một method generic thông thường.
- Không có lời hứa mọi type argument đều có **public no-arg constructor**.
- T có thể là interface, abstract class hoặc class không thể trực tiếp instantiate.
- Constructor có thể có parameters, bị giới hạn accessibility hoặc ném checked exceptions.
- `T extends SomeBase` chỉ cho biết subtype relation và accessible inherited APIs, **không** cho biết constructor cần gọi.
- Java generics không có C#-style constructor constraint như `where T : new()`.

Ví dụ `class Maker<T extends Number>` vẫn không thể viết `new T()`. Nếu bạn biết cụ thể muốn `new Integer(...)` thì đó là constructor hoặc factory của một concrete type, không phải thao tác trên arbitrary T.

## 5. Cách đơn giản nhất: để caller truyền object đã tạo

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Caller chịu trách nhiệm tạo/đưa object:

~~~java
Box<StringBuilder> box =
        new Box<>(new StringBuilder("Java"));
~~~

Ưu điểm:
- không cần reflection;
- hỗ trợ constructor tùy ý ở caller;
- compiler kiểm tra type argument;
- code dễ test vì dependencies/value creation explicit.

Nhược điểm:
- Box không tự chủ động tạo thêm một T nếu behavior đó là yêu cầu nghiệp vụ.

Nếu Box cần tạo mới khi gọi method, truyền factory hoặc supplier.

## 6. Chương trình chạy: truyền object vào generic constructor

Tạo **`PassedValueDemo.java`**:

~~~java
public class PassedValueDemo {
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
        StringBuilder created = new StringBuilder("Java");
        Box<StringBuilder> box = new Box<>(created);

        System.out.println(box.get());
        System.out.println("same reference=" +
                (box.get() == created));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 PassedValueDemo.java
java PassedValueDemo
~~~

Stdout:

~~~text
Java
same reference=true
~~~

Box không clone StringBuilder. Đó là reference semantics bình thường; **type safety không đồng nghĩa deep immutability**.

## 7. Cách khuyến nghị cho tạo mới: `Supplier<? extends T>`

`java.util.function.Supplier<T>` là một functional interface có method `T get()`. Caller truyền lambda hoặc method reference để chỉ định **cách tạo object**:

~~~java
class Maker<T> {
    private final java.util.function.Supplier<? extends T> factory;

    Maker(java.util.function.Supplier<? extends T> factory) {
        this.factory = java.util.Objects.requireNonNull(factory);
    }

    T create() {
        return factory.get();
    }
}
~~~

Ví dụ:

~~~java
Maker<StringBuilder> maker =
        new Maker<>(StringBuilder::new);
StringBuilder value = maker.create();
~~~

`StringBuilder::new` chỉ định constructor thực, nên không có `new T()`.

### Vì sao `? extends T`?

Factory có thể tạo subtype của T. Ví dụ khi T là CharSequence, một Supplier<StringBuilder> cũng có thể là producer phù hợp. Nếu API không cần flexibility đó, `Supplier<T>` vẫn là một signature hợp lệ.

## 8. Chương trình chạy: factory tạo object mỗi lần

Tạo **`SupplierFactoryDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

public class SupplierFactoryDemo {
    static final class Maker<T> {
        private final Supplier<? extends T> factory;

        Maker(Supplier<? extends T> factory) {
            this.factory = Objects.requireNonNull(factory);
        }

        T create() {
            return factory.get();
        }
    }

    public static void main(String[] args) {
        Maker<StringBuilder> maker =
                new Maker<>(StringBuilder::new);

        StringBuilder one = maker.create();
        StringBuilder two = maker.create();

        one.append("Java");
        two.append("Core");

        System.out.println(one);
        System.out.println(two);
        System.out.println("same reference=" + (one == two));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SupplierFactoryDemo.java
java SupplierFactoryDemo
~~~

Stdout:

~~~text
Java
Core
same reference=false
~~~

Mỗi lần gọi Supplier trong ví dụ tạo một StringBuilder mới. Tuy nhiên **Supplier không bắt buộc luôn tạo object mới**; caller có thể truyền supplier trả singleton, vì vậy hãy document contract nếu cần fresh instance.

## 9. Constructor cần arguments: dùng factory lambda

Một factory được caller cung cấp có thể capture hoặc nhận arguments:

~~~java
Maker<StringBuilder> maker =
        new Maker<>(() -> new StringBuilder("initial"));
~~~

Nếu inputs khác nhau ở từng call, dùng `Function<A,T>` thay vì Supplier:

~~~java
static <A, T> T create(
        A argument,
        java.util.function.Function<? super A, ? extends T> factory) {
    return factory.apply(argument);
}
~~~

Ví dụ `create("Java", StringBuilder::new)`.

### Lợi ích

- Không giả định có constructor trống.
- Type inference kiểm tra source/target relationship.
- Không phải chuyển checked reflection exceptions thành unchecked.
- Factory có thể tạo immutable value, record, class hoặc proxy theo policy.
- Tests có thể cung cấp fake factory.

## 10. Chương trình chạy: Function làm constructor factory

Tạo **`ParameterizedFactoryDemo.java`**:

~~~java
import java.util.function.Function;

public class ParameterizedFactoryDemo {
    static <A, T> T create(
            A argument,
            Function<? super A, ? extends T> factory) {
        return factory.apply(argument);
    }

    public static void main(String[] args) {
        StringBuilder builder =
                create("Java", StringBuilder::new);

        System.out.println(builder);
        System.out.println(builder.length());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ParameterizedFactoryDemo.java
java ParameterizedFactoryDemo
~~~

Stdout:

~~~text
Java
4
~~~

`StringBuilder::new` ở đây là constructor reference phù hợp với một String input; compile-time type checking vẫn được áp dụng.

## 11. `Class<T>`: runtime type token

Nếu bạn thực sự cần biết runtime class của T, hãy **yêu cầu caller truyền token**:

~~~java
class TypedBox<T> {
    private final Class<T> type;

    TypedBox(Class<T> type) {
        this.type = java.util.Objects.requireNonNull(type);
    }
}
~~~

Caller:

~~~java
TypedBox<String> text = new TypedBox<>(String.class);
TypedBox<Integer> numbers = new TypedBox<>(Integer.class);
~~~

Token này là object `Class<T>` với thông tin runtime class cụ thể của một **reifiable class** mà caller chọn.

Nó giải quyết một số bài toán:
- runtime `type.isInstance(obj)`;
- runtime cast `type.cast(obj)`;
- reflection tạo object/mảng theo class;
- logging/validation class name.

Nhưng `Class<T>` **không thể tự biểu diễn trọn `List<String>`**. `List.class` có tồn tại; `List<String>.class` không có cú pháp hợp lệ.

## 12. `Class<T>` và reflection tạo object

Một cách thay thế `new T()` là:

~~~java
T create() throws ReflectiveOperationException {
    return type.getDeclaredConstructor().newInstance();
}
~~~

Nó đòi một no-argument constructor phù hợp; reflection còn phải thỏa accessibility/module rules. Method có thể ném:
- `NoSuchMethodException` nếu constructor không tồn tại;
- `InstantiationException` nếu type không instantiate được;
- `IllegalAccessException` do access restrictions;
- `InvocationTargetException` nếu constructor body ném exception.

`ReflectiveOperationException` là common checked superclass cho nhiều lỗi reflection.

**Không dùng** `Class.newInstance()` cho code mới: API đó đã deprecated, và constructor invocation qua `getDeclaredConstructor().newInstance()` hoặc `getConstructor().newInstance()` diễn đạt tốt hơn.

## 13. Chương trình chạy: tạo qua `Class<T>`

Tạo **`ReflectionFactoryDemo.java`**:

~~~java
import java.lang.reflect.ReflectiveOperationException;
~~~

Đoạn import trên **cố ý không phải mã chạy** vì `ReflectiveOperationException` thuộc `java.lang`, không phải `java.lang.reflect`. Bản chương trình đầy đủ đúng sau đây không có import sai đó.

Tạo nội dung chính xác của file **`ReflectionFactoryDemo.java`**:

~~~java
public class ReflectionFactoryDemo {
    static final class Maker<T> {
        private final Class<T> type;

        Maker(Class<T> type) {
            this.type = java.util.Objects.requireNonNull(type);
        }

        T create() throws ReflectiveOperationException {
            return type.getDeclaredConstructor().newInstance();
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Maker<StringBuilder> maker =
                new Maker<>(StringBuilder.class);

        StringBuilder value = maker.create();
        value.append("Java");

        System.out.println(value);
        System.out.println(value.getClass().getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ReflectionFactoryDemo.java
java ReflectionFactoryDemo
~~~

Stdout:

~~~text
Java
StringBuilder
~~~

Ví dụ chạy được vì `StringBuilder` có public no-arg constructor. Trong API phổ thông, **Supplier** thường đơn giản, dễ test và ít liên kết reflection hơn.

## 14. Vì sao bound không làm `new T()` hợp lệ?

~~~java
abstract class Shape {}

class ShapeBox<T extends Shape> {
    // T create() { return new T(); } // Vẫn sai.
}
~~~

Dù compiler biết T là một subclass của Shape:
- concrete subtype thật có thể là Circle, Rectangle, v.v.;
- Shape có thể abstract;
- không có contract đảm bảo mọi subclass có constructor signature giống nhau;
- constructors không được thừa kế như instance methods.

Bound `T extends Shape` dùng để **truy cập APIs có trên Shape**, không phải để “phát hiện constructor”.

Nếu bạn biết cần một Shape nào đó theo factory, dùng `Supplier<? extends T>` hoặc abstract factory interface, như ở trên.

## 15. Chương trình chạy: bounded T và Supplier

Tạo **`BoundedSupplierDemo.java`**:

~~~java
import java.util.function.Supplier;

public class BoundedSupplierDemo {
    static abstract class Shape {
        abstract int sides();
    }

    static final class Triangle extends Shape {
        @Override
        int sides() {
            return 3;
        }
    }

    static final class Maker<T extends Shape> {
        private final Supplier<? extends T> factory;

        Maker(Supplier<? extends T> factory) {
            this.factory = factory;
        }

        T create() {
            return factory.get();
        }
    }

    public static void main(String[] args) {
        Maker<Triangle> maker = new Maker<>(Triangle::new);
        Triangle triangle = maker.create();

        System.out.println(triangle.sides());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BoundedSupplierDemo.java
java BoundedSupplierDemo
~~~

Stdout:

~~~text
3
~~~

Bound bảo đảm returned T có method `sides()`; Supplier quyết định constructor thực sự.

## 16. Không có `T.class`

Trong generic code:

~~~java
class Inspector<T> {
    // Class<T> type() { return T.class; } // Compile error.
}
~~~

Class literal phải là kiểu có thể biểu diễn bởi syntax của class literal thích hợp, ví dụ `String.class`, `int.class`, `String[].class` hoặc `List.class`. Type variable `T` không phải concrete class literal expression.

Tương tự:

~~~java
// Class<List<String>> t = List<String>.class; // Sai.
~~~

Thay vào đó:
- nhận `Class<T> type` từ caller;
- nhận `java.lang.reflect.Type`/type descriptor nếu cần biểu diễn parameterized type;
- hoặc không sử dụng runtime type inspection nếu compile-time API đã đủ.

## 17. Mảng trong Java có runtime component type

Array khác generic collections ở cách Java kiểm tra kiểu:

~~~java
String[] words = new String[2];
words[0] = "Java";
~~~

Runtime biết component type `String` của array object. Vì thế code:

~~~java
Object[] objects = words;
objects[0] = Integer.valueOf(17);
~~~

**Biên dịch được**, do arrays là **covariant**: String[] là subtype của Object[]. Nhưng phép gán vào array thực String[] bị runtime từ chối bằng `ArrayStoreException`.

Đây là một kiểu kiểm tra runtime mà erased generic type arguments không thể cung cấp tương tự.

## 18. Chương trình chạy: `ArrayStoreException`

Tạo **`ArrayCovarianceDemo.java`**:

~~~java
public class ArrayCovarianceDemo {
    public static void main(String[] args) {
        String[] names = {"Mai", "An"};
        Object[] objects = names;

        System.out.println("before=" + names[0]);

        try {
            objects[0] = Integer.valueOf(17);
        } catch (ArrayStoreException ex) {
            System.out.println("wrong array element type");
        }

        System.out.println("after=" + names[0]);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ArrayCovarianceDemo.java
java ArrayCovarianceDemo
~~~

Stdout:

~~~text
before=Mai
wrong array element type
after=Mai
~~~

Runtime array component check bảo vệ String[] khỏi việc lưu Integer, ngay cả khi reference được nhìn như Object[].

## 19. Vì sao `new T[n]` không được phép?

Trong generic class:

~~~java
class Store<T> {
    // T[] items = new T[10]; // Compile error: generic array creation.
}
~~~

Nếu compiler cho phép, runtime array component class phải là gì? Với `Store<String>` có thể cần String[], với `Store<Integer>` có thể cần Integer[], nhưng T bị erased.

Mảng có runtime element-type checks, còn generic T không cung cấp runtime component class cụ thể. Vì vậy Java cấm việc tạo mảng theo type variable T trực tiếp.

**Không nhầm:** Có thể khai báo một field/parameter kiểu `T[]`; điều bị giới hạn là **tạo new array với `T`**.

~~~java
class Store<T> {
    private T[] items; // Khai báo type hợp lệ.
}
~~~

Nếu caller truyền sẵn T[] hoặc factory cung cấp array phù hợp, bạn có thể lưu reference một cách type-safe.

## 20. Cách an toàn: caller truyền một mảng có sẵn

~~~java
class ArrayBox<T> {
    private final T[] values;

    ArrayBox(T[] values) {
        this.values = values;
    }
}
~~~

Caller tạo concrete array:

~~~java
ArrayBox<String> words =
        new ArrayBox<>(new String[]{"A", "B"});
~~~

**Nhưng** lưu array reference trực tiếp gây aliasing: caller có thể sửa array; getter nếu trả array trực tiếp cũng lộ mutable state. Nếu muốn snapshot, clone input và output.

Lưu ý `T[]#clone()` có kết quả runtime là same array class, và array clone là **shallow** đối với reference elements.

## 21. Chương trình chạy: nhận T[] và copy hai chiều

Tạo **`InputArrayBoxDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class InputArrayBoxDemo {
    static final class ArrayBox<T> {
        private final T[] values;

        ArrayBox(T[] input) {
            values = Objects.requireNonNull(input, "input").clone();
        }

        T[] copyValues() {
            return values.clone();
        }

        T at(int index) {
            return values[index];
        }
    }

    public static void main(String[] args) {
        String[] source = {"A", "B"};
        ArrayBox<String> box = new ArrayBox<>(source);

        source[0] = "X";
        String[] out = box.copyValues();
        out[1] = "Y";

        System.out.println("source=" + Arrays.toString(source));
        System.out.println("snapshot=" +
                Arrays.toString(box.copyValues()));
        System.out.println("first=" + box.at(0));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 InputArrayBoxDemo.java
java InputArrayBoxDemo
~~~

Stdout:

~~~text
source=[X, B]
snapshot=[A, B]
first=A
~~~

Arrays clone giúp tránh structural aliasing giữa input/output và internal array, nhưng nếu elements là mutable objects thì chúng vẫn có thể được chia sẻ.

## 22. Vì sao `new List<String>[n]` không được phép?

Type `List<String>` là **non-reifiable**: runtime không giữ đầy đủ String argument để kiểm tra một arbitrary List có đúng `List<String>` hay không.

Vì vậy:

~~~java
// List<String>[] lists = new List<String>[3]; // Compile error.
~~~

Nếu Java cho tạo array thật có runtime component type “List<String>”, runtime phải kiểm tra nội dung generic type arguments mỗi khi gán array element, nhưng Java arrays không hỗ trợ kiểm tra điều đó.

Không nhầm lỗi này với:

~~~java
java.util.List<String> list = new java.util.ArrayList<>();
~~~

Đó là **tạo một object từ generic class bằng concrete class constructor**, hoàn toàn hợp lệ. Lỗi là việc tạo một **array có component type non-reifiable**.

## 23. Reifiable type là gì?

Một type được gọi là **reifiable** khi đủ thông tin về type đó hiện diện tại runtime để kiểm tra đúng theo loại hình mà Java cho phép. Ví dụ thường gặp:

| Kiểu | Reifiable? | Ghi chú |
| --- | --- | --- |
| `String` | Có | Runtime class cụ thể |
| `String[]` | Có | Array component reifiable |
| `int[]` | Có | Primitive array |
| `List` (raw) | Có | Chỉ kiểm tra raw List |
| `List<?>` | Có | Unbounded wildcard parameterization |
| `List<String>` | Không | Runtime không kiểm tra String argument đầy đủ |
| `Map<?, ?>` | Có | All type arguments là unbounded wildcards |
| `Map<String, Integer>` | Không | Concrete generic arguments bị erased |
| `T` là type variable | Thông thường không | Không có reified actual type argument |
| `List<String>[]` | Không | Array component non-reifiable |

**Điểm quan trọng:** `List<?>` vẫn không nói phần tử là Object, String hay Integer cụ thể. Nó chỉ biểu diễn một List với unknown element type, được runtime kiểm tra theo raw List class.

## 24. Có thể tạo `new List<?>[n]`

Unbounded wildcard parameterization `List<?>` là một reifiable type, vì vậy:

~~~java
java.util.List<?>[] items =
        new java.util.List<?>[2];
~~~

hợp lệ. Mỗi phần tử array có thể chứa reference tới một List nào đó, bất kể element type argument cụ thể.

~~~java
items[0] = java.util.List.of("Java");
items[1] = java.util.List.of(17);
~~~

Đọc ra `items[0].get(0)` cho Object-typed result, không được suy ra String nếu không qua kiểm tra phù hợp.

Đây **không phải** workaround để có một “mảng List<String> được kiểm tra đầy đủ”. Type arguments của từng List vẫn unknown.

## 25. Chương trình chạy: mảng `List<?>[]` hợp lệ

Tạo **`WildcardArrayDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;

public class WildcardArrayDemo {
    public static void main(String[] args) {
        List<?>[] groups = new List<?>[2];

        groups[0] = List.of("Java", "Core");
        groups[1] = List.of(17, 21);

        System.out.println(groups[0]);
        System.out.println(groups[1]);

        Object first = groups[0].get(0);
        System.out.println("first=" + first);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 WildcardArrayDemo.java
java WildcardArrayDemo
~~~

Stdout:

~~~text
[Java, Core]
[17, 21]
first=Java
~~~

Chương trình không khẳng định elements trong mọi list đều String. Nó chỉ giữ mảng các List với unknown generic arguments.

## 26. Tại sao `Object[]` cast thành `T[]` là rủi ro?

Một pattern dễ bắt gặp:

~~~java
@SuppressWarnings("unchecked")
T[] values = (T[]) new Object[n];
~~~

Compiler cho phép unchecked cast trong generic context sau warning/suppression, nhưng **runtime array object vẫn là Object[]**, không phải một String[] thật.

Một generic method có thể vô tình trả `T[]` trong source, nhưng khi caller mong `String[]`, compiler-generated cast ở use site sẽ ném `ClassCastException`.

Ngoài vấn đề cast, cast này còn che giấu giả định type có thể bị vi phạm. Nếu bạn không có invariant rõ và không nắm exact runtime class, **tránh dùng nó như giải pháp mặc định**.

## 27. Chương trình chạy: unchecked array cast thất bại

Tạo **`UnsafeGenericArrayDemo.java`**:

~~~java
public class UnsafeGenericArrayDemo {
    @SuppressWarnings("unchecked")
    static <T> T[] badArray(int size) {
        return (T[]) new Object[size];
    }

    public static void main(String[] args) {
        try {
            String[] strings = UnsafeGenericArrayDemo.<String>badArray(2);
            System.out.println(strings.length);
        } catch (ClassCastException ex) {
            System.out.println("Object[] is not String[]");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 UnsafeGenericArrayDemo.java
java UnsafeGenericArrayDemo
~~~

Stdout:

~~~text
Object[] is not String[]
~~~

Unchecked suppression không tạo String[] thật. Việc lấy giá trị ở target `String[]` làm runtime check phân biệt actual Object[].

## 28. Thay mảng generic bằng `List<T>` nếu phù hợp

Đây là phương án đơn giản nhất cho dữ liệu nhiều phần tử generic:

~~~java
class Store<T> {
    private final java.util.List<T> values =
            new java.util.ArrayList<>();

    void add(T value) {
        values.add(value);
    }

    T get(int index) {
        return values.get(index);
    }
}
~~~

`ArrayList` nội bộ có thể dựa vào Object[] implementation detail, nhưng library duy trì generic API contract. Người sử dụng Store không phải tự cast array hay chịu unchecked array creation.

### Lợi ích

- Không cần biết runtime `Class<T>`.
- Hỗ trợ số lượng elements thay đổi.
- Các methods nhận/trả T được compiler check.
- Dễ copy unmodifiable snapshot bằng List.copyOf.
- Không cần generic array casts trong application code.

### Giới hạn

Một List<T> vẫn không kiểm tra actual type argument T tại runtime khi bị lạm dụng qua raw types/unchecked casts. Generic APIs cung cấp compile-time checks khi sử dụng đúng.

## 29. Chương trình chạy: `Store<T>` bằng ArrayList

Tạo **`ListStoreDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListStoreDemo {
    static final class Store<T> {
        private final List<T> values = new ArrayList<>();

        void add(T value) {
            values.add(value);
        }

        T get(int index) {
            return values.get(index);
        }

        int size() {
            return values.size();
        }
    }

    public static void main(String[] args) {
        Store<String> store = new Store<>();

        store.add("Java");
        store.add("Generics");

        System.out.println("size=" + store.size());
        System.out.println(store.get(0));
        System.out.println(store.get(1));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ListStoreDemo.java
java ListStoreDemo
~~~

Stdout:

~~~text
size=2
Java
Generics
~~~

Đối với generic container thông thường, List<T> thường dễ thiết kế và bảo trì hơn T[].

## 30. Cần đúng runtime array type: dùng `IntFunction<T[]>`

`java.util.function.IntFunction<T[]>` nhận độ dài và tạo array đúng type do caller lựa chọn:

~~~java
static <T> T[] makeArray(
        int size,
        java.util.function.IntFunction<T[]> arrayFactory) {
    return arrayFactory.apply(size);
}
~~~

Caller:

~~~java
String[] values = makeArray(3, String[]::new);
~~~

Compiler kiểm tra factory trả `String[]`; runtime array object thật sự có component type String.

### So với `new T[n]`

- `new T[n]`: generic implementation tự cố suy ra T runtime, không được.
- `String[]::new`: caller biết concrete component type và truyền factory explicit.
- `IntFunction<T[]>`: abstraction generic nhận quyền tạo array đúng runtime type.

Hãy validate size/null factory và cân nhắc ownership khi trả array ra ngoài.

## 31. Chương trình chạy: array factory bằng constructor reference

Tạo **`ArrayFactoryDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.function.IntFunction;

public class ArrayFactoryDemo {
    static <T> T[] create(
            int length,
            IntFunction<T[]> factory) {
        if (length < 0) {
            throw new IllegalArgumentException("length");
        }
        return Objects.requireNonNull(factory, "factory")
                .apply(length);
    }

    public static void main(String[] args) {
        String[] words = create(3, String[]::new);

        words[0] = "Java";
        words[1] = "17";
        words[2] = "Generics";

        System.out.println(Arrays.toString(words));
        System.out.println(words.getClass().getComponentType()
                .getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ArrayFactoryDemo.java
java ArrayFactoryDemo
~~~

Stdout:

~~~text
[Java, 17, Generics]
String
~~~

String[]::new cung cấp đúng runtime component class, không có generic array cast bị che giấu.

## 32. Dùng `Array.newInstance(Class<T>, int)`

Khi caller có Class<T> token, Java reflection có thể tạo array với runtime component type T:

~~~java
@SuppressWarnings("unchecked")
static <T> T[] createArray(Class<T> type, int size) {
    return (T[]) java.lang.reflect.Array.newInstance(type, size);
}
~~~

Ở đây cast vẫn **unchecked** theo compiler, nhưng có thể được biện minh bởi invariant: `Array.newInstance(type,size)` tạo một array có runtime component class từ chính token, và method chỉ trả array được tạo đó. Khi caller sử dụng token đúng với T, result có runtime array type mong muốn.

### Cẩn trọng

- `Class<T>` phải là token phù hợp và non-null.
- Token có thể trỏ tới interface/abstract class; tạo *array of that type* vẫn hợp lệ dù bạn không thể `new` instance trực tiếp.
- Không thể tạo array với non-reifiable component `List<String>` chỉ bằng `List.class`.
- Primitive Class tokens là trường hợp đặc biệt cần xem xét: API generic T là reference type, nên ví dụ này dùng reference component token.
- SuppressWarnings nên đặt đúng **cast được audit**, không đặt bừa toàn class.
- Caller vẫn có thể phá invariants bằng raw/unchecked code; không có API nào bảo vệ khỏi mọi unchecked misuse.

## 33. Chương trình chạy: array thực sự là `String[]`

Tạo **`ReflectArrayDemo.java`**:

~~~java
import java.lang.reflect.Array;
import java.util.Arrays;
import java.util.Objects;

public class ReflectArrayDemo {
    static <T> T[] create(Class<T> type, int size) {
        Objects.requireNonNull(type, "type");
        if (size < 0) {
            throw new IllegalArgumentException("size");
        }

        @SuppressWarnings("unchecked")
        T[] result = (T[]) Array.newInstance(type, size);
        return result;
    }

    public static void main(String[] args) {
        String[] values = create(String.class, 2);

        values[0] = "A";
        values[1] = "B";

        System.out.println(Arrays.toString(values));
        System.out.println("component=" +
                values.getClass().getComponentType().getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ReflectArrayDemo.java
java ReflectArrayDemo
~~~

Stdout:

~~~text
[A, B]
component=String
~~~

Với một simple runtime reference component type, token + Array.newInstance là giải pháp hợp lý nếu API bắt buộc array.

## 34. Dùng `Collection.toArray(IntFunction<T[]>)`

Một collection generic có thể chuyển thành array với factory do caller cung cấp:

~~~java
List<String> words = List.of("Java", "Core");
String[] array = words.toArray(String[]::new);
~~~

Java 11+ hỗ trợ overload `Collection.toArray(IntFunction<T[]>)`. Với Java 17, đây là cách gọn tránh tự viết cast.

### Chương trình chạy

Tạo **`ToArrayDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;

public class ToArrayDemo {
    public static void main(String[] args) {
        List<String> words = List.of("Java", "Core");
        String[] copy = words.toArray(String[]::new);

        System.out.println(Arrays.toString(copy));
        System.out.println("type=" +
                copy.getClass().getComponentType().getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ToArrayDemo.java
java ToArrayDemo
~~~

Stdout:

~~~text
[Java, Core]
type=String
~~~

Factory quyết định runtime component type; Collection chỉ cung cấp elements. Đây là mẫu tốt khi giao tiếp với APIs yêu cầu arrays.

## 35. Generic invariance khác array covariance

Giả sử Integer extends Number.

**Array:**

~~~java
Integer[] integers = {1, 2};
Number[] numbers = integers; // Hợp lệ (covariance).
// numbers[0] = 2.5;       // Runtime ArrayStoreException.
~~~

**Generic List:**

~~~java
List<Integer> integers = List.of(1, 2);
// List<Number> numbers = integers; // Compile error.
~~~

Java generic parameterized types **invariant**: `List<Integer>` không phải subtype của `List<Number>`.

Nếu mục tiêu là đọc các Numbers:

~~~java
List<? extends Number> numbers = integers;
~~~

Khi dùng wildcard extends, bạn không thể thêm arbitrary Number vì actual element type có thể Integer, BigDecimal, v.v.

**Động cơ:** Java generics kiểm tra nhiều misuse tại compile time thay vì dựa vào runtime array store checks.

## 36. Chương trình chạy: covariance và invariance cạnh nhau

Tạo **`ArrayVsGenericsDemo.java`**:

~~~java
import java.util.List;

public class ArrayVsGenericsDemo {
    public static void main(String[] args) {
        Integer[] integers = {1, 2};
        Number[] numbers = integers;

        try {
            numbers[0] = 2.5;
        } catch (ArrayStoreException ex) {
            System.out.println("array store rejected");
        }

        List<Integer> integerList = List.of(1, 2);
        List<? extends Number> numberList = integerList;

        System.out.println("list first=" + numberList.get(0));
        System.out.println("array first=" + integers[0]);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ArrayVsGenericsDemo.java
java ArrayVsGenericsDemo
~~~

Stdout:

~~~text
array store rejected
list first=1
array first=1
~~~

Một Number[] reference không thay đổi runtime component type Integer của array object.

## 37. Heap pollution là gì?

**Heap pollution** xảy ra khi một variable của **parameterized type** trỏ đến object không thuộc parameterization mà source code kỳ vọng.

Một nguồn phổ biến:
- raw types/unchecked conversions;
- unchecked casts;
- generic varargs;
- APIs legacy hoặc reflection không được validate.

Ví dụ nguy hiểm:

~~~java
List<String> words = new ArrayList<>();
List raw = words;
raw.add(42); // Unchecked warning.
String first = words.get(0); // Có thể ClassCastException.
~~~

Dù List<String> tại source-level có String contract, raw reference đã cho phép chèn Integer vào same List object.

### Heap pollution khác ArrayStoreException

- Mảng String[] biết runtime String component; gán Integer qua Object[] bị chặn ngay bằng ArrayStoreException.
- List<String> sau erasure không kiểm tra String ở runtime mỗi lần add nếu raw caller bypass generic API; lỗi thường xuất hiện muộn khi đọc String.

## 38. Chương trình chạy: raw List tạo `ClassCastException`

Tạo **`HeapPollutionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class HeapPollutionDemo {
    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        List raw = words;

        raw.add(42);

        try {
            String word = words.get(0);
            System.out.println(word);
        } catch (ClassCastException ex) {
            System.out.println("heap pollution detected");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 HeapPollutionDemo.java
java HeapPollutionDemo
~~~

Stdout:

~~~text
heap pollution detected
~~~

@SuppressWarnings chỉ ẩn warning trong minh họa; nó không sửa data. Production code nên xóa unchecked boundary hoặc validate/copy ngay tại boundary.

## 39. Generic varargs: cú pháp tiện nhưng cần thận trọng

Java varargs method như:

~~~java
static <T> void process(List<T>... lists) {}
~~~

về runtime dùng một array chứa arguments. Nhưng `List<T>` là non-reifiable, nên generic varargs có thể dẫn tới compiler warning và nguy cơ heap pollution nếu method:
- cast array sang Object[];
- ghi list sai type vào đó;
- lộ array ra ngoài để caller mutate;
- giả định nội dung arrays được reified đầy đủ.

Compiler có thể phát warning như `[varargs] Possible heap pollution from parameterized vararg type`. Hãy coi warning là tín hiệu cần audit, không phải yêu cầu “thêm SuppressWarnings cho sạch”.

## 40. Chương trình chạy: heap pollution qua varargs array

Tạo **`UnsafeVarargsDemo.java`**:

~~~java
import java.util.List;

public class UnsafeVarargsDemo {
    @SafeVarargs
    static void unsafe(List<String>... groups) {
        Object[] asObjects = groups;
        asObjects[0] = List.of(17);

        try {
            String first = groups[0].get(0);
            System.out.println(first);
        } catch (ClassCastException ex) {
            System.out.println("polluted varargs array");
        }
    }

    public static void main(String[] args) {
        unsafe(List.of("Java"));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 UnsafeVarargsDemo.java
java UnsafeVarargsDemo
~~~

Stdout:

~~~text
polluted varargs array
~~~

**Quan trọng:** `@SafeVarargs` ở đây được **cố ý dùng sai về mặt lời cam kết an toàn** để chứng minh compiler annotation không tự biến code unsafe thành safe; không được sao chép pattern này vào production. Javac có thể cảnh báo thêm về unsafe operations trong thân method tùy flags.

## 41. `@SafeVarargs` dùng khi nào?

Annotation `@SafeVarargs` là một **cam kết của tác giả method** rằng method không thực hiện unsafe operations trên generic varargs parameter.

Trong Java 17, annotation có thể áp dụng cho các kinds phù hợp như:
- static methods;
- final instance methods;
- private instance methods;
- constructors.

Nó **không** làm một public non-final overridable instance method an toàn/được phép annotate tùy ý. Compiler có thể phát sinh warnings nếu method body thực hiện thao tác nguy hiểm dù có annotation.

Để dùng đúng:
- không ghi những elements sai type vào varargs array;
- không trả/escape varargs array theo cách caller có thể mutate bất an toàn;
- không giả định component type arguments còn ở runtime;
- chỉ đọc references thông qua typed signatures;
- verify các nested mutable element data nếu domain cần.

## 42. Chương trình chạy: generic varargs an toàn (read-only)

Tạo **`SafeVarargsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeVarargsDemo {
    @SafeVarargs
    static <T> List<T> combine(
            List<? extends T>... groups) {
        List<T> result = new ArrayList<>();

        for (List<? extends T> group : groups) {
            result.addAll(group);
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> merged = combine(
                List.of("Java"), List.of("Core"));

        System.out.println(merged);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SafeVarargsDemo.java
java SafeVarargsDemo
~~~

Stdout:

~~~text
[Java, Core]
~~~

Phương thức không mutate/escape varargs array và tạo result riêng. `List.copyOf` tạo unmodifiable structural snapshot và cấm null elements, là chính sách riêng của ví dụ.

## 43. Muốn tránh generic varargs hẳn?

Có thể nhận `List<? extends List<? extends T>>` hoặc `Collection<? extends List<? extends T>>`:

~~~java
static <T> List<T> combine(
        List<? extends List<? extends T>> groups) {
    List<T> output = new ArrayList<>();
    for (List<? extends T> group : groups) {
        output.addAll(group);
    }
    return output;
}
~~~

Khi caller đã có collection of groups, dạng này có thể dễ hiểu hơn và không cần generic varargs array.

Tradeoff: call site dài hơn khi chỉ có vài groups literal, nhưng interface semantics rõ.

### Quyết định

- Varargs khi API ergonomic và code đã được audit đúng.
- Collection-of-collections khi dữ liệu vốn được tập hợp theo cấu trúc đó, hoặc muốn loại bỏ warning/caveat.

## 44. `instanceof T`: vì sao không hợp lệ?

Trong generic class:

~~~java
class Inspector<T> {
    boolean test(Object value) {
        // return value instanceof T; // Compile error.
        return false;
    }
}
~~~

`instanceof` cần runtime-checkable target type theo Java rules. `T` không được reify thành đúng actual parameterization của mọi Inspector<T> instance, nên compiler không cho kiểm tra theo type variable một cách trực tiếp.

Một cast đơn thuần `(T) obj` cũng thường là **unchecked** khi compiler không thể verify concrete T. Nếu code giữ raw/unchecked paths, lỗi có thể bộc lộ tại call site.

### Hai giải pháp chuẩn

1. Nếu chỉ kiểm tra generic **shape**, dùng `instanceof Box<?>` hoặc `instanceof List<?>`.
2. Nếu kiểm tra concrete runtime class, nhận `Class<T>` và dùng `isInstance/cast`.

Không dùng `getClass().getTypeParameters()` để suy ra actual argument String từ một arbitrary Box<String> object: nó không lưu trữ argument như vậy.

## 45. `instanceof List<String>` khác `instanceof List<?>`

Giả sử:

~~~java
Object candidate = java.util.List.of("Java");
~~~

Không được:

~~~java
// boolean result = candidate instanceof List<String>;
~~~

vì type argument String trong target `List<String>` không được runtime kiểm tra đầy đủ.

Được:

~~~java
boolean result = candidate instanceof java.util.List<?>;
~~~

`List<?>` là reifiable parameterization. Nhưng result true chỉ xác nhận candidate là List ở runtime; không chứng minh mọi element đều là String.

Một cast `(List<String>) candidate` có thể compile kèm unchecked warning, nhưng không biến list thành checked String list. Khi đọc element, compiler-inserted cast có thể ném ClassCastException.

## 46. Chương trình chạy: `instanceof List<?>` không chứng minh element type

Tạo **`InstanceofWildcardDemo.java`**:

~~~java
import java.util.List;

public class InstanceofWildcardDemo {
    static String classify(Object candidate) {
        if (candidate instanceof List<?> values) {
            return "list size=" + values.size();
        }
        return "not list";
    }

    public static void main(String[] args) {
        System.out.println(classify(List.of("Java")));
        System.out.println(classify(List.of(17)));
        System.out.println(classify("Java"));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 InstanceofWildcardDemo.java
java InstanceofWildcardDemo
~~~

Stdout:

~~~text
list size=1
list size=1
not list
~~~

Cả List<String> và List<Integer> đều pass List<?> runtime test; element type vẫn unknown.

## 47. Kiểm tra từng element thay vì tin generic type argument

Nếu input từ untyped external source phải thật sự là danh sách Strings, có thể:
1. kiểm tra outer object là `List<?>`;
2. kiểm tra từng element `instanceof String`;
3. copy vào `List<String>` mới.

Không dùng unchecked cast `(List<String>) raw` như validator.

### Chương trình chạy

Tạo **`ValidatedStringListDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ValidatedStringListDemo {
    static List<String> parseStrings(Object input) {
        if (!(input instanceof List<?> values)) {
            throw new IllegalArgumentException("not a list");
        }

        List<String> copy = new ArrayList<>();
        for (Object item : values) {
            if (!(item instanceof String text)) {
                throw new IllegalArgumentException(
                        "non-string element");
            }
            copy.add(text);
        }
        return List.copyOf(copy);
    }

    public static void main(String[] args) {
        System.out.println(parseStrings(
                List.of("Java", "Core")));

        try {
            parseStrings(List.of("Java", 17));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ValidatedStringListDemo.java
java ValidatedStringListDemo
~~~

Stdout:

~~~text
[Java, Core]
rejected=non-string element
~~~

Sau khi validate từng element, method trả một typed immutable snapshot. Đây là pattern đáng tin khi input từ JSON parsers, reflection hoặc raw legacy APIs.

## 48. Runtime `Class.isInstance` và `Class.cast`

Có `Class<T>` token, bạn có thể:

~~~java
boolean valid = type.isInstance(value);
T checked = type.cast(value);
~~~

- `isInstance(null)` trả false.
- `cast(null)` trả null; nếu API cấm null, cần `Objects.requireNonNull`.
- `Class.cast` kiểm tra runtime class assignability, ném ClassCastException khi không compatible.
- `Class<T>` với String.class kiểm tra String; Number.class chấp nhận Integer/Double objects theo subtype relation.
- Token `List.class` chỉ biết raw List, không xác thực element String.

### Không nhầm `obj.getClass() == type`

`getClass()==type` đòi exact runtime class; `type.isInstance(obj)` chấp nhận subclasses/implementations phù hợp. Đa số runtime assignability checks nên dùng `isInstance` thay vì equality của Class objects.

## 49. Chương trình chạy: runtime check với `Class<T>`

Tạo **`ClassTokenCheckDemo.java`**:

~~~java
public class ClassTokenCheckDemo {
    static <T> T checked(Class<T> type, Object value) {
        if (!type.isInstance(value)) {
            throw new IllegalArgumentException("wrong type");
        }
        return type.cast(value);
    }

    public static void main(String[] args) {
        String text = checked(String.class, "Java");
        Number number = checked(Number.class, 17);

        System.out.println(text);
        System.out.println(number);

        try {
            checked(String.class, 17);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ClassTokenCheckDemo.java
java ClassTokenCheckDemo
~~~

Stdout:

~~~text
Java
17
rejected=wrong type
~~~

Null bị từ chối do method sử dụng `isInstance(null)` false. Nếu null hợp lệ, hãy xử lý nó riêng.

## 50. Bounded T không làm generic argument reifiable

Ví dụ:

~~~java
class Numbers<T extends Number> {
    // boolean test(Object o) {
    //     return o instanceof T; // Vẫn không hợp lệ.
    // }
}
~~~

Bound bảo đảm compiler cho gọi methods trên Number ở các biến T, nhưng T có thể là Integer, Double hay BigDecimal tùy actual type argument.

Khi erasure, T được đại diện bởi upper bound Number ở nhiều vị trí. Nhưng “obj là Number” **không đủ chứng minh obj là actual T**, ví dụ Integer cần khác Double.

Do đó:
- Dùng `obj instanceof Number` nếu domain chỉ cần Number.
- Dùng `Class<T>` token nếu cần runtime concrete subtype.
- Dùng typed API nếu compile-time relationship đã đủ.

## 51. Chương trình chạy: runtime token cho bounded T

Tạo **`BoundedTokenDemo.java`**:

~~~java
import java.util.Objects;

public class BoundedTokenDemo {
    static final class NumberChecker<T extends Number> {
        private final Class<T> type;

        NumberChecker(Class<T> type) {
            this.type = Objects.requireNonNull(type);
        }

        boolean accepts(Object value) {
            return type.isInstance(value);
        }
    }

    public static void main(String[] args) {
        NumberChecker<Integer> integers =
                new NumberChecker<>(Integer.class);

        System.out.println(integers.accepts(7));
        System.out.println(integers.accepts(7.5));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BoundedTokenDemo.java
java BoundedTokenDemo
~~~

Stdout:

~~~text
true
false
~~~

`Class<Integer>` token khôi phục đúng runtime check mong muốn ở API này; bound Number một mình không làm được.

## 52. Kiểm tra `getClass()` của generic object không nói T

~~~java
Box<String> words = new Box<>("Java");
Box<Integer> numbers = new Box<>(17);
~~~

`words.getClass()` và `numbers.getClass()` là cùng Box class. `getClass().getTypeParameters()` mô tả **khai báo type variable T trên Box class**, không lưu String/Integer của individual values.

Nếu Box chứa một non-null object, `box.get().getClass()` có thể chỉ runtime class của **value**, nhưng:
- value có thể null;
- declared T có thể interface/supertype khác runtime concrete class;
- value có thể là generic List<String> nhưng getClass chỉ cho biết List implementation class, không String arguments;
- không thể dùng đó để xác định toàn bộ declared type argument T.

Nếu cần type identity của T, hãy lưu explicit token.

## 53. Chương trình chạy: runtime class của value khác generic declaration

Tạo **`ValueClassNotTypeArgumentDemo.java`**:

~~~java
public class ValueClassNotTypeArgumentDemo {
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
        Box<Number> number = new Box<>(17);

        System.out.println("box class=" +
                number.getClass().getSimpleName());
        System.out.println("value class=" +
                number.get().getClass().getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ValueClassNotTypeArgumentDemo.java
java ValueClassNotTypeArgumentDemo
~~~

Stdout:

~~~text
box class=Box
value class=Integer
~~~

Declared type parameter là Number, runtime value class là Integer, và generic Box class không tự ghi nhớ argument Number.

## 54. `Class<T>` không biểu diễn `List<String>` đầy đủ

Class literal hợp lệ:

~~~java
Class<?> rawListClass = java.util.List.class;
~~~

Không có:

~~~java
// Class<List<String>> t = List<String>.class;
~~~

Thực thể `Class` biểu diễn **runtime class/interface**, không chứa arbitrary full parameterized type arguments ở một expression như `List<String>.class`.

Nếu một framework/deserializer cần biểu diễn `List<String>`, Java Reflection có interface:
- `java.lang.reflect.Type`;
- `ParameterizedType`;
- `TypeVariable`;
- `WildcardType`;
- `GenericArrayType`.

Một số frameworks cung cấp **type token/type reference** để giữ generic type information từ một *declaration/signature* có thể phản chiếu.

**Đừng kết luận runtime mọi thông tin generic đều biến mất hoàn toàn**: một số generic signatures tồn tại trong class/method/field declarations và Reflection có thể đọc. Điều không tồn tại là một reified `List<String>` runtime class cho mỗi ordinary instance.

## 55. Chương trình chạy: Reflection đọc parameterized field declaration

Tạo **`GenericFieldReflectionDemo.java`**:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.List;

public class GenericFieldReflectionDemo {
    static final class Holder {
        List<String> values;
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Field field = Holder.class.getDeclaredField("values");
        Type declaredType = field.getGenericType();

        System.out.println("parameterized=" +
                (declaredType instanceof ParameterizedType));

        ParameterizedType type =
                (ParameterizedType) declaredType;
        System.out.println("raw=" + type.getRawType());
        System.out.println("argument=" +
                type.getActualTypeArguments()[0]);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericFieldReflectionDemo.java
java GenericFieldReflectionDemo
~~~

Stdout:

~~~text
parameterized=true
raw=interface java.util.List
argument=class java.lang.String
~~~

Reflection ở đây đọc **field signature** `List<String>`, không kiểm tra actual elements trong một arbitrary List object.

## 56. TypeReference giữ declared parameterization qua anonymous subclass

Một idiom Java phổ biến:

~~~java
abstract class TypeRef<T> {
    // Đọc generic superclass signature của anonymous subclass.
}
~~~

Caller tạo:

~~~java
new TypeRef<List<String>>() {};
~~~

Anonymous subclass declaration chứa một generic-superclass signature mà Reflection có thể đọc như `ParameterizedType`.

Đây là **type information capture từ class declaration**, không phải việc Java thay type erasure bằng reified generic runtime instances. APIs framework (Jackson, Guava, Spring...) có những abstractions tương tự, nhưng chi tiết phụ thuộc thư viện/version.

### Chương trình chạy

Tạo **`TypeReferenceDemo.java`**:

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.List;

public class TypeReferenceDemo {
    static abstract class TypeRef<T> {
        private final Type type;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType p)) {
                throw new IllegalStateException("parameterized subclass");
            }
            type = p.getActualTypeArguments()[0];
        }

        Type type() {
            return type;
        }
    }

    public static void main(String[] args) {
        TypeRef<List<String>> reference =
                new TypeRef<List<String>>() {};

        Type type = reference.type();
        ParameterizedType listType = (ParameterizedType) type;

        System.out.println("raw=" + listType.getRawType());
        System.out.println("argument=" +
                listType.getActualTypeArguments()[0]);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 TypeReferenceDemo.java
java TypeReferenceDemo
~~~

Stdout:

~~~text
raw=interface java.util.List
argument=class java.lang.String
~~~

Type reference hữu ích cho serializers và reflective generic metadata, nhưng **không** khiến JVM ngăn chèn Integer vào raw List ở runtime.

## 57. Runtime cast với `(T)` và chỗ có thể ném exception

Trong generic method:

~~~java
@SuppressWarnings("unchecked")
static <T> T unsafe(Object value) {
    return (T) value;
}
~~~

Với unbounded T, cast ở method body có thể chỉ còn Object-level sau erasure, nhưng compiler sẽ áp dụng kiểm tra kiểu phù hợp ở **caller assignment/use site**:

~~~java
String text = unsafe(17);
~~~

Khi thực thi, cast về String có thể ném ClassCastException.

Đừng nhầm việc method generic return được compile với việc runtime đã xác minh actual type T. **Unchecked cast chuyển trách nhiệm chứng minh an toàn từ compiler sang programmer**.

Nếu có `Class<T>` token, `type.cast` là lựa chọn rõ hơn để kiểm tra kiểu thật tại boundary.

## 58. Chương trình chạy: `(T)` sai gây lỗi ở caller

Tạo **`UncheckedCastDemo.java`**:

~~~java
public class UncheckedCastDemo {
    @SuppressWarnings("unchecked")
    static <T> T unsafe(Object value) {
        return (T) value;
    }

    public static void main(String[] args) {
        try {
            String text = UncheckedCastDemo.<String>unsafe(17);
            System.out.println(text);
        } catch (ClassCastException ex) {
            System.out.println("caller cast failed");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 UncheckedCastDemo.java
java UncheckedCastDemo
~~~

Stdout:

~~~text
caller cast failed
~~~

Unchecked casts chỉ nên xuất hiện ở boundary có proof/invariant được document và test, không phải cách làm im compiler khi API thiết kế sai.

## 59. Type-safe heterogeneous container dùng Class key

Một pattern đôi khi hữu ích là `Map<Class<?>, Object>`: mỗi Class token liên kết với value được kiểm tra bằng token.

~~~java
final class Favorites {
    private final Map<Class<?>, Object> values = new HashMap<>();

    public <T> void put(Class<T> type, T value) {
        values.put(type, type.cast(value));
    }

    public <T> T get(Class<T> type) {
        return type.cast(values.get(type));
    }
}
~~~

Pattern này giúp nhiều **concrete class tokens** chia sẻ một heterogeneous store, nhưng không hỗ trợ phân biệt `List<String>` với `List<Integer>` chỉ bằng List.class. Ngoài ra, constructor/put policy phải quyết định null, mutable values và concurrency.

## 60. Chương trình chạy: type-safe favorites với Class token

Tạo **`ClassKeyStoreDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ClassKeyStoreDemo {
    static final class Store {
        private final Map<Class<?>, Object> values =
                new HashMap<>();

        <T> void put(Class<T> type, T value) {
            Objects.requireNonNull(type, "type");
            values.put(type, type.cast(value));
        }

        <T> T get(Class<T> type) {
            return type.cast(values.get(type));
        }
    }

    public static void main(String[] args) {
        Store store = new Store();
        store.put(String.class, "Java");
        store.put(Integer.class, 17);

        System.out.println(store.get(String.class));
        System.out.println(store.get(Integer.class));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ClassKeyStoreDemo.java
java ClassKeyStoreDemo
~~~

Stdout:

~~~text
Java
17
~~~

Đây là runtime checked heterogeneous storage theo **Class keys**; không phải generic-array solution.

## 61. Generic array field có thể hợp lệ dù `new T[]` không hợp lệ

Một declaration:

~~~java
class ArrayHolder<T> {
    private final T[] values;

    ArrayHolder(T[] values) {
        this.values = values.clone();
    }

    T at(int index) {
        return values[index];
    }
}
~~~

là hợp lệ, vì constructor **nhận một mảng do caller tạo**; nó không tự viết `new T[n]`.

Đừng nhầm:
- `T[]` trong declaration/parameter/return → có thể hợp lệ.
- `new T[10]` → không hợp lệ.
- `String[]::new` hoặc `Array.newInstance(String.class,10)` → hợp lệ khi caller cung cấp concrete runtime component type.

Để bảo vệ internal array, constructor copy và getter nên trả copy hoặc controlled methods; phần tử mutable vẫn có thể alias.

## 62. Lỗi “generic array creation” có nhiều dạng

Các đoạn sai:

~~~java
class Holder<T> {
    // T[] first = new T[2];
    // List<T>[] second = new List<T>[2];
}

// List<String>[] names = new List<String>[2];
// Map<String,Integer>[] maps = new Map<String,Integer>[2];
~~~

Nhưng các dạng đúng bao gồm:

~~~java
String[] strings = new String[2];
List<?>[] anyLists = new List<?>[2];
List<String> names = new ArrayList<>();
~~~

Với `List<String>[]`, bạn có thể gặp legacy code tạo raw List[] rồi unchecked cast; đừng xem đó là tương đương với một runtime checked List<String>[].

## 63. Checked runtime component của array không kiểm tra List elements

Giả sử:

~~~java
List<?>[] groups = new List<?>[2];
groups[0] = List.of("Java");
groups[1] = List.of(17);
~~~

Runtime array biết component là raw/reifiable List type. Nó có thể ngăn gán một String object trực tiếp vào `groups[0]` qua Object[]:

~~~java
Object[] objects = groups;
// objects[0] = "not a list"; // Runtime ArrayStoreException.
~~~

Nhưng nó **không** ngăn groups[0] giữ `List<Integer>` thay vì `List<String>` vì array component không có String type argument.

Đây là nơi phải phân biệt hai tầng:
1. array stores list object references;
2. each list stores elements với generic compile-time contracts.

## 64. Chương trình chạy: array chỉ bảo vệ lớp ngoài

Tạo **`ListArrayComponentDemo.java`**:

~~~java
import java.util.List;

public class ListArrayComponentDemo {
    public static void main(String[] args) {
        List<?>[] groups = new List<?>[2];
        groups[0] = List.of("Java");
        groups[1] = List.of(17);

        Object[] objects = groups;

        try {
            objects[0] = "wrong outer type";
        } catch (ArrayStoreException ex) {
            System.out.println("outer type rejected");
        }

        System.out.println(groups[0]);
        System.out.println(groups[1]);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ListArrayComponentDemo.java
java ListArrayComponentDemo
~~~

Stdout:

~~~text
outer type rejected
[Java]
[17]
~~~

Runtime array check nhận biết List references nhưng không kiểm tra element parameterization.

## 65. `T...` varargs có thể khai báo, nhưng không “reify T”

Generic method:

~~~java
@SafeVarargs
static <T> void printAll(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
~~~

là cú pháp hợp lệ khi tuân thủ `@SafeVarargs` restrictions. Caller có thể truyền actual array được compiler tạo với reifiable component type ở call site; tuy nhiên implementation vẫn không được xem T như một runtime class token đáng tin.

Nếu varargs component type non-reifiable, compiler thường cảnh báo. Không dùng chính cái array `values` để lưu unrelated objects hoặc giả định an toàn khi escape references.

### Chương trình chạy

Tạo **`GenericVarargsReadDemo.java`**:

~~~java
public class GenericVarargsReadDemo {
    @SafeVarargs
    static <T> void printAll(T... values) {
        for (T value : values) {
            System.out.println(value);
        }
    }

    public static void main(String[] args) {
        printAll("A", "B");
        printAll(1, 2);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericVarargsReadDemo.java
java GenericVarargsReadDemo
~~~

Stdout:

~~~text
A
B
1
2
~~~

Generic varargs có thể hữu ích khi chỉ đọc và không làm rò array; annotating không thay proof rằng code safe.

## 66. `@SuppressWarnings("unchecked")` đúng cách

Dùng suppression trong phạm vi nhỏ nhất:

~~~java
@SuppressWarnings("unchecked")
T[] array = (T[]) Array.newInstance(type, length);
~~~

Tác giả phải có invariant chứng minh:
- array được tạo từ đúng runtime type token của T;
- references không bị thay qua raw/unchecked boundaries;
- methods không trả sai type;
- caller không được đưa type token không khớp với intended T qua unchecked code.

**Không làm:**

~~~java
// @SuppressWarnings("unchecked") // đặt trên cả class chỉ để tắt mọi cảnh báo
class HugeGenericUtility {
    // nhiều casts không được kiểm chứng...
}
~~~

Compiler warning là tín hiệu thiết kế có giới hạn; suppression chỉ là annotation, không phải runtime validator.

## 67. Khi generic interface/class dùng bound, erasure ảnh hưởng casting

Với:

~~~java
class NumberBox<T extends Number> {
    private T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Erasure của T là Number. Compiler có thể cho gọi `get().doubleValue()` trong methods vì Number có API đó. Nhưng runtime không tự biết String/Integer/Double type arguments nào được dùng cho mỗi NumberBox instance.

Nếu bạn cố cast NumberBox<Double> sang NumberBox<Integer> qua raw code, invariant vẫn có thể bị phá và ClassCastException xảy ra tại typed use site.

**Bounds làm tăng compile-time expressiveness**, không cung cấp reification.

## 68. Chương trình chạy: bounded getter dùng Number API

Tạo **`NumberBoundErasureDemo.java`**:

~~~java
public class NumberBoundErasureDemo {
    static final class NumberBox<T extends Number> {
        private final T value;

        NumberBox(T value) {
            this.value = value;
        }

        double valueAsDouble() {
            return value.doubleValue();
        }
    }

    public static void main(String[] args) {
        NumberBox<Integer> integer = new NumberBox<>(7);
        NumberBox<Double> decimal = new NumberBox<>(2.5);

        System.out.println(integer.valueAsDouble());
        System.out.println(decimal.valueAsDouble());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 NumberBoundErasureDemo.java
java NumberBoundErasureDemo
~~~

Stdout:

~~~text
7.0
2.5
~~~

Không thể viết `new T()` trong NumberBox chỉ vì upper bound Number.

## 69. Generics và overload: erasure ảnh hưởng method signatures

Hai overloads chỉ khác type arguments có thể bị **name clash**:

~~~java
// void process(List<String> words) {}
// void process(List<Integer> numbers) {}
~~~

Chúng cùng erased parameter type List, nên không thể đặt hai methods signature như thế trong cùng class.

Tương tự:
- overload `accept(T)` và `accept(Object)` trong unbounded generic class có thể trùng sau erasure;
- arrays và varargs cũng cần xét erased signatures;
- generic method declaration không tạo JVM-level overload khác chỉ nhờ type arguments.

Đây là một giới hạn **khác** với new T()/generic arrays, nhưng cùng nguồn gốc type erasure.

### Cách sửa

- đặt method names khác nhau nếu semantics khác nhau;
- dùng một generic method đúng relationship;
- dùng một parameterized strategy/factory;
- hoặc truyền `Class<T>` token nếu cần runtime selection.

## 70. Bridge methods: compiler duy trì overriding sau erasure

Ví dụ:

~~~java
interface Getter<T> {
    T get();
}

class StringGetter implements Getter<String> {
    @Override
    public String get() {
        return "Java";
    }
}
~~~

Sau erasure, interface method có descriptor tương tự Object get(), còn implementation trả String. Compiler có thể sinh **bridge method** để duy trì polymorphism/binary overriding đúng Java semantics.

Bridge methods là chi tiết compiler/runtime hỗ trợ generics. Bạn không phải tự viết chúng cho ordinary correct code.

### Không nhầm

Bridge method không khôi phục reified T runtime, không cho phép `new T()`, và không làm `instanceof List<String>` hợp lệ.

## 71. Chương trình chạy: generic interface dispatch qua bridge

Tạo **`BridgeDispatchDemo.java`**:

~~~java
public class BridgeDispatchDemo {
    interface Getter<T> {
        T get();
    }

    static final class StringGetter implements Getter<String> {
        @Override
        public String get() {
            return "Java";
        }
    }

    public static void main(String[] args) {
        Getter<String> getter = new StringGetter();

        System.out.println(getter.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BridgeDispatchDemo.java
java BridgeDispatchDemo
~~~

Stdout:

~~~text
Java
~~~

Compiler giữ contract của Getter<String> với StringGetter dù signatures sau erasure cần xử lý bổ sung.

## 72. Không dùng generic type parameters để extends Throwable

Java giới hạn classes có type parameters khi kế thừa Throwable:

~~~java
// class Failure<T> extends Exception {} // Không hợp lệ.
~~~

Bởi exception catch/throws matching có runtime semantics, còn generic class parameter không reifiable đầy đủ. Dù đây không phải mảng generic, nó cùng nhóm giới hạn **reifiable runtime typing**.

Bạn vẫn có thể:
- định nghĩa ordinary exception classes;
- trả generic Result<T> để biểu diễn success/failure bằng values;
- viết generic methods ném declared checked exception parameter theo Java rules phù hợp.

### Không cố viết `catch (T ex)`

Một type variable T không được dùng làm exception handler target như một runtime exception class.

## 73. Decision table: cách thay thế nào đúng?

| Nhu cầu | Không nên viết | Phương án phù hợp |
| --- | --- | --- |
| Nhận một value kiểu T | `new T()` | Constructor nhận T |
| Tạo T theo logic caller | `new T()` | `Supplier<? extends T>` |
| Tạo T cần argument | Giả định no-arg constructor | `Function<A, ? extends T>` / factory |
| Tạo T theo runtime class | `T.class` | `Class<T>` + reflection nếu phù hợp |
| Tạo array đúng concrete type | `new T[n]` | `IntFunction<T[]>` hoặc `Array.newInstance` |
| Chứa generic sequence | `new T[n]` | `List<T>` |
| Array các List<String> | `new List<String>[n]` | `List<List<String>>` |
| Mảng lists không quan tâm element type | Cast generic array | `new List<?>[n]` nếu thật sự cần |
| Kiểm tra runtime String | `instanceof T` | `String.class.isInstance` hoặc token |
| Kiểm tra outer List | `instanceof List<String>` | `instanceof List<?>` |
| Kiểm tra List<String> từ Object | Unchecked cast | Validate từng element rồi copy |
| Giữ metadata `List<String>` | `List<String>.class` | Type/ParameterizedType/type reference |
| Generic varargs | Tin annotation là bảo hiểm | Audit; `@SafeVarargs` chỉ khi method safe |
| Chia sẻ heterogeneous values | Raw Box | `Class<T>` key + checked cast |
| Refactor warning | Suppress mọi warning | Sửa design hoặc local documented proof |

## 74. Những lỗi compile-time phổ biến

| Sai cú pháp/ý tưởng | Lý do |
| --- | --- |
| `new T()` | Type variable không là concrete class constructor target |
| `new T[10]` | Generic array creation prohibited |
| `new List<String>[10]` | Component type non-reifiable |
| `T.class` | Type variable không có class literal |
| `List<String>.class` | Parameterized type không có class literal |
| `value instanceof T` | Runtime không kiểm tra actual T |
| `obj instanceof List<String>` | List<String> non-reifiable target |
| `Box<int>` | Generic type argument phải là reference type |
| `Box<Object> obj = new Box<String>()` | Generic invariance |
| `void f(List<String>)` và `void f(List<Integer>)` | Erased signatures trùng |
| `static T field` trong Box<T> | Class type parameter không dùng trong static context |
| `new T[]{...}` | Generic array creation |
| `class Failure<T> extends Exception` | Generic Throwable subclass bị cấm |
| `@SafeVarargs` lên ordinary overridable instance method | Annotation không hợp lệ cho loại declaration đó |

**Ghi nhớ:** “Compiler từ chối” khác với “runtime ném exception”. Viết negative examples thành code riêng khi thực sự cần quan sát javac diagnostics; không sao chép chúng vào chương trình runnable.

## 75. Những runtime failures thường gặp

| Exception/hậu quả | Nguyên nhân |
| --- | --- |
| `ArrayStoreException` | Ghi wrong runtime component type vào array qua covariant supertype reference |
| `ClassCastException` | Unchecked generic cast hoặc polluted raw/varargs data bị đọc như String/typed value |
| `NullPointerException` | Unboxing null, null token hoặc factory/array input không được kiểm tra |
| `ReflectiveOperationException` subclasses | Constructor reflection lookup/access/instantiation/invocation errors |
| `IllegalArgumentException` | `Array.newInstance`/input size invalid tùy API, hoặc domain validation |
| Corrupt logical data | Raw collections/unchecked aliases phá declared parameterized type invariant |
| Mutable aliasing | Object[]/T[]/List<T> được share mà không có ownership/copying policy |

### Phân biệt nơi phát hiện

- Compiler bắt mismatch trong typed generic source.
- Runtime array component checks bắt array store mismatch.
- Typed getter/use site có thể ném ClassCastException khi heap pollution đã xảy ra.
- Reflection cast/token có thể xác nhận runtime concrete class nhưng không validate nội dung nested generic collections.

## 76. Anti-patterns nên tránh

**SuppressWarnings toàn lớp:** Che giấu nơi các invariants chưa được chứng minh.

**Tự ép Object[] thành T[]:** Dễ nổ ở String[] call site, tạo false sense of type safety.

**Dùng raw List/Box làm interoperability default:** Làm compiler mất khả năng bảo vệ code.

**Dùng `getClass().getTypeParameters()` để suy ra caller T:** Đây là declaration metadata, không actual per-instance type argument.

**Dùng `(List<String>) obj` thay validation:** Runtime không kiểm tra String element type trong unchecked cast.

**Cho rằng `List<?>` chứa Object tùy ý có thể add:** Read works, nhưng không add arbitrary non-null elements vì captured element type unknown.

**Truyền Class<List<String>> bằng `List.class` và tin được generics đầy đủ:** Class token không biểu diễn String argument.

**Dùng @SafeVarargs mà vẫn viết vào backing varargs array:** Annotation là lời cam kết, không biến method safe.

**Dùng reflection cho mọi constructor:** Reflection có checked errors, accessibility/module restrictions và tốn complexity không cần thiết; Supplier/factory thường tốt hơn.

**Coi ArrayStoreException như validation của List<String> elements:** Array stores chỉ biết runtime component class phù hợp, không kiểm tra nested generic arguments.

**Tự xây concurrent generic array holder với unsafe casts:** Vừa có vấn đề type safety vừa có concurrency/ownership policy.

**Không test negative paths:** Generic APIs liên quan đến raw boundaries cần thử ClassCastException, ArrayStoreException, null, incorrect factories.

## 77. Bài tập 1 — Tại sao `new T()` sai?

Một generic class:

~~~java
class Maker<T> {
    // T create() { return new T(); }
}
~~~

**Đáp án:** T là type variable bị erased, không chỉ định concrete constructor; Java không có constructor constraint đảm bảo một no-arg constructor. Hãy truyền Supplier<? extends T>, factory Function, hoặc Class<T> cho nhu cầu reflection phù hợp.

## 78. Bài tập 2 — Supplier hay Class token?

Yêu cầu tạo StringBuilder qua no-arg constructor nhưng muốn API dễ test và không phụ thuộc reflection.

**Đáp án:** Supplier<StringBuilder> với `StringBuilder::new` thường tốt hơn. Reflection Class<T> có ích khi class được chọn bằng runtime token và cần reflective discovery.

## 79. Bài tập 3 — Có tạo `new List<String>[3]` được không?

**Đáp án:** Không vì List<String> non-reifiable, array requires runtime component checks. Dùng `List<List<String>>` nếu muốn 3 nhóm String values, hoặc `List<?>[]` khi chỉ cần một array of arbitrary Lists.

## 80. Bài tập 4 — Reifiable phân loại

`String[]`, `List<?>`, `List<String>`, `Map<?,?>`, `T`.

**Đáp án:** String[], List<?> và Map<?,?> là reifiable trong các trường hợp chuẩn; List<String> và type variable T không reifiable đầy đủ.

## 81. Bài tập 5 — Array covariance

~~~java
Integer[] ints = {1};
Number[] nums = ints;
// nums[0] = 2.5;
~~~

**Đáp án:** Dòng cuối compile được nhưng nếu chạy sẽ ném ArrayStoreException vì actual array là Integer[].

## 82. Bài tập 6 — Generic invariance

`List<Integer>` có gán thẳng cho `List<Number>` được không?

**Đáp án:** Không. Java generic parameterizations invariant. Dùng `List<? extends Number>` nếu chỉ cần đọc Numbers.

## 83. Bài tập 7 — Cast Object[] thành String[]

Trong generic method, `return (T[]) new Object[2]` với @SuppressWarnings unchecked. Caller nhận `String[]`.

**Đáp án:** Runtime Object[] không trở thành String[], nên cast ở call site có thể ném ClassCastException. Dùng `String[]::new` hoặc Class<String>+Array.newInstance.

## 84. Bài tập 8 — `Class<T>` token

Viết hàm nhận Object và Class<T>, chỉ trả T nếu runtime match.

**Đáp án gợi ý:**

~~~java
static <T> T checked(Class<T> type, Object value) {
    if (!type.isInstance(value)) {
        throw new IllegalArgumentException("wrong type");
    }
    return type.cast(value);
}
~~~

Lưu ý isInstance(null) trả false; validate null policy có chủ đích.

## 85. Bài tập 9 — Mảng bằng constructor reference

Tạo String[3] trong generic method dùng IntFunction<T[]>.

**Đáp án gợi ý:**

~~~java
static <T> T[] make(int count,
                     java.util.function.IntFunction<T[]> maker) {
    return maker.apply(count);
}

String[] names = make(3, String[]::new);
~~~

Factory giúp tạo String[] thật với runtime component class String.

## 86. Bài tập 10 — Outer vs inner runtime type

`obj instanceof List<?>` true với `List.of(17)`. Có thể khẳng định list chứa Strings không?

**Đáp án:** Không. Runtime test chỉ xác nhận outer List. Để bảo đảm List<String>, kiểm tra từng element và tạo validated typed copy.

## 87. Bài tập 11 — Type token đầy đủ

Tại sao `Class<List<String>> clazz = List<String>.class` sai?

**Đáp án:** Không có parameterized class literal. `List.class` chỉ biết raw List. Dùng Reflection Type/ParameterizedType hoặc framework type reference để diễn tả generic signature và validation riêng.

## 88. Bài tập 12 — Heap pollution

Raw List reference thêm Integer vào List<String>. Lỗi xảy ra ở bước add hay get?

**Đáp án:** Raw add có thể chạy với unchecked warning mà không kiểm tra String. Typed get/use site có thể ném ClassCastException do compiler-inserted cast.

## 89. Bài tập 13 — Generic varargs

Một static method nhận `List<String>...`, cast varargs array sang Object[] rồi ghi `List.of(42)`.

**Đáp án:** Unsafe, heap pollution có thể xảy ra. Không được gắn @SafeVarargs để “che chắn”; annotation là lời hứa, method vẫn sai. Tránh viết vào varargs array.

## 90. Bài tập 14 — `List<T>` hay `T[]`?

Một Store<T> cần add/get/size và số elements thay đổi.

**Đáp án:** `List<T>`/ArrayList<T> thường dễ và type-safe hơn tự tạo T[] bằng cast. Nếu giao tiếp với API buộc array đúng component type, nhận array factory hoặc Class<T> token.

## 91. Bài tập 15 — Generic bound

`class Maker<T extends Number>` có được `new T()` không?

**Đáp án:** Không. Bound chỉ cho biết T là subtype Number, không hứa concrete constructor. Đưa Supplier/Function/Class token.

## 92. Bài tập 16 — `Class.cast`

`String.class.cast("Java")` trả gì? `String.class.cast(17)` ra sao?

**Đáp án:** Trả String "Java" ở case đầu; case sau ném ClassCastException. `String.class.cast(null)` trả null, nên nếu cấm null thì validate riêng.

## 93. Bài tập 17 — Compiler và runtime responsibilities

Nêu khác biệt giữa `List<String>` type safety với `String[]` store checks.

**Đáp án:** Generic List<String> kiểm tra compile-time type arguments trong typed code, nhưng runtime erasure không kiểm tra String cho raw writes. String[] có runtime component type String, nên ghi wrong object qua Object[] gây ArrayStoreException ngay.

## 94. Bài tập 18 — Generic reflection

Một field declaration là `List<String> values`. Reflection có thể đọc được String argument từ field signature không? Điều này có chứng minh arbitrary List instance chứa Strings không?

**Đáp án:** Field.getGenericType có thể trả ParameterizedType với String argument; đó là metadata **declaration**, không phải runtime element validation. Không suy ra chất lượng của data trong arbitrary instance.

## 95. Quy trình lựa chọn API an toàn

**Bước 1 — Xác định yêu cầu.** Cần tạo object T mới, tạo array T[], hay chỉ muốn giữ danh sách values? Ba nhu cầu khác nhau.

**Bước 2 — Nếu chỉ giữ values, ưu tiên List<T>.** Không bắt buộc xây T[].

**Bước 3 — Nếu tạo object mới, ưu tiên Supplier/Function.** Caller chỉ định constructor/factory thật.

**Bước 4 — Nếu runtime class được chọn động, cân nhắc Class<T>.** Xử lý reflection failure và accessibility/module policy.

**Bước 5 — Nếu cần array đúng component type, truyền IntFunction<T[]>.** Caller viết `String[]::new`.

**Bước 6 — Nếu dùng Array.newInstance, giữ token invariant.** Suppress unchecked cast đúng chỗ, test String[] runtime class.

**Bước 7 — Nếu nhận unknown Object, kiểm tra outer shape.** `instanceof List<?>`, không cast blind sang List<String>.

**Bước 8 — Validate nested elements.** Runtime Class token chỉ xác nhận concrete class ở tầng có token; List<String> phải validate từng element nếu input untyped.

**Bước 9 — Tránh raw/unchecked boundaries.** Đưa conversion tại một boundary hẹp có proof.

**Bước 10 — Với generic varargs, audit method body.** Không corrupt/escape array, dùng @SafeVarargs chỉ khi thật sự safe.

**Bước 11 — Phân biệt type-safe và immutable.** Array/List may be mutable; xác định ownership và defensive copy.

**Bước 12 — Kiểm thử cả compile và runtime.** Positive examples + negative compiler fixtures + ClassCastException/ArrayStoreException cases.

## 96. Checklist cuối bài

- [ ] Tôi hiểu Java 17 generic type parameters chủ yếu bị type erasure.
- [ ] Tôi biết `Box<String>` và `Box<Integer>` không có runtime classes riêng.
- [ ] Tôi biết tại sao `new T()` bị cấm.
- [ ] Tôi biết `T extends Number` vẫn không cho phép `new T()`.
- [ ] Tôi dùng constructor nhận object khi không cần tự tạo T.
- [ ] Tôi biết `Supplier<? extends T>` để tạo T theo factory.
- [ ] Tôi biết `Function<A,? extends T>` cho constructor cần argument.
- [ ] Tôi hiểu Supplier không bắt buộc luôn tạo fresh object nếu contract không quy định.
- [ ] Tôi biết `Class<T>` type token.
- [ ] Tôi hiểu reflection tạo instance có checked exceptions và accessibility rules.
- [ ] Tôi không dùng `T.class`.
- [ ] Tôi không dùng `List<String>.class`.
- [ ] Tôi biết `new T[n]` bị cấm.
- [ ] Tôi biết `new List<String>[n]` bị cấm.
- [ ] Tôi phân biệt reifiable và non-reifiable types.
- [ ] Tôi biết `List<?>[]` có thể tạo khi phù hợp.
- [ ] Tôi phân biệt array covariance với generic invariance.
- [ ] Tôi giải thích được runtime ArrayStoreException.
- [ ] Tôi không cast Object[] thành T[] một cách tùy tiện.
- [ ] Tôi biết `IntFunction<T[]>`/`String[]::new`.
- [ ] Tôi biết `Array.newInstance(Class<T>,length)` và invariant của cast.
- [ ] Tôi ưu tiên `List<T>` cho generic dynamic collection.
- [ ] Tôi biết `Collection.toArray(String[]::new)`.
- [ ] Tôi nhận diện heap pollution từ raw types/casts/varargs.
- [ ] Tôi biết generic varargs có thể phát unchecked warnings.
- [ ] Tôi biết `@SafeVarargs` là lời cam kết, không tự làm method an toàn.
- [ ] Tôi không dùng `instanceof T`.
- [ ] Tôi không dùng `obj instanceof List<String>` khi target non-reifiable.
- [ ] Tôi biết `instanceof List<?>` kiểm tra outer list, không element String.
- [ ] Tôi biết validate từng element khi dữ liệu đầu vào không được type-check.
- [ ] Tôi biết `Class.isInstance` và `Class.cast`.
- [ ] Tôi biết `isInstance(null)` false và `cast(null)` trả null.
- [ ] Tôi hiểu `getClass()` không tiết lộ per-instance generic type argument.
- [ ] Tôi biết Reflection `ParameterizedType` có thể đọc declared generic metadata.
- [ ] Tôi phân biệt type reference với reified generic object type.
- [ ] Tôi biết bounded T vẫn không reified.
- [ ] Tôi không dùng unchecked suppression rộng khi chưa có proof.
- [ ] Tôi hiểu bridge methods liên quan erasure nhưng không giải quyết new T().
- [ ] Tôi hiểu generics type safety khác immutability và concurrency safety.
- [ ] Tôi có thể dự đoán stdout và phân tích compile errors của ví dụ.

**Kết luận:** Hạn chế `new T()`, `new T[]` và `instanceof T` cùng xuất phát từ sự khác biệt giữa **generic type được kiểm tra ở compile time** và **runtime type information** trong Java. Arrays kiểm tra component class tại runtime nên không thể biểu diễn một mảng có component `List<String>` non-reifiable một cách hoàn toàn an toàn. Hãy để **caller cung cấp factory hoặc type token** khi cần tạo objects/arrays, dùng **`List<T>`** khi không thực sự cần mảng, kiểm tra unknown input qua **`List<?>` + element validation**, và chỉ dùng unchecked casts/`@SafeVarargs` khi đã chứng minh invariant. Những lựa chọn này giúp giữ type safety của Java 17 mà không giả vờ rằng type erasure đã biến mất.
